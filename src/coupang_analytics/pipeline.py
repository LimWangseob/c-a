"""전체 실행 오케스트레이션(`run_full`) — **계정별로 처음부터 끝까지 완결 + 이어서 하기 지원**.

계정마다 [로그인(방금 연 세션) → 판매분석 발견·지표 → 키워드 → 순위]를 완결하고 다음 계정으로.
결과는 통합 워크북 1개에 누적하고, 진행 중엔 `쿠팡데이타분석_진행중.xlsx`(+`.json` 상태)에
저장하며, 전부 끝나면 날짜·시각이 붙은 최종본으로 이름을 바꾼다. 이어서 할 때는 완료 계정을
건너뛰고, 미완료 계정은 키워드 재사용 + 이미 조회한 순위 건너뛰기로 끊긴 지점부터 이어간다.
순위 조회는 부하가 크므로 순차로 지연을 두며, 차단되면 공란 처리하고 계속 진행한다.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from . import config
from .browser import WING_URL, WingBrowser
from .input_list import Account, InputList
from . import wing_session
from .kw_ai import KeywordAIError, recommend_title
from .kw_recommend import (attack_priority, comp_from_idx, diagnose_exposure,
                           keyword_in_title, rank_label, select_keywords_light)
from .kw_volume import NaverAdApi
from .rank import RankBlocked, make_matcher, organic_ranks, organic_ranks_batch, warmup
from .session_store import SessionStore
from .workbook import OutputWorkbook

_PROFILE = "data/chrome-pipeline"   # 검색 순위용(비로그인)
_PROFILES_DIR = "data/profiles"     # 계정별 로그인 프로필
# 진행 중(미완료) 통합 엑셀 + 진행 상태(같은 날 크래시 복구용). 완료되면 상태파일 삭제.
_PARTIAL_XLSX = f"{config.OUTPUT_FILE_PREFIX}_진행중.xlsx"
_PROGRESS_JSON = f"{config.OUTPUT_FILE_PREFIX}_진행중.json"
# 통계 마스터(지속형) — 매일 실행이 이어써서 날짜 컬럼을 누적하고 키워드를 동결한다.
_MASTER_XLSX = f"{config.OUTPUT_FILE_PREFIX}_통계.xlsx"


def _partial_path(out_dir: str | Path) -> Path:
    return Path(out_dir) / _PARTIAL_XLSX


def _progress_path(out_dir: str | Path) -> Path:
    return Path(out_dir) / _PROGRESS_JSON


def _master_path(out_dir: str | Path) -> Path:
    return Path(out_dir) / _MASTER_XLSX


def _snapshot_path(out_dir: str | Path, now: datetime) -> Path:
    """그날 완료본 스냅샷(감사·백업용). 마스터가 손상돼도 날짜별 본이 남는다."""
    return Path(out_dir) / f"{config.OUTPUT_FILE_PREFIX}_통계_{now.strftime('%y%m%d')}.xlsx"


def master_exists(out_dir: str | Path = "output") -> bool:
    """이어쓸 통계 마스터가 있는지(UI가 '기존 통계에 추가' 옵션 노출 여부 판단)."""
    return _master_path(out_dir).exists()


def resumable_progress(out_dir: str | Path = "output") -> dict | None:
    """이어서 할 수 있는 진행 상태가 있으면 그 메타(dict)를, 없으면 None 반환.

    반환 예: {"date_from","date_to","started_at","done":[계정ID...]}. UI 팝업 문구에 사용.
    진행 엑셀과 상태파일이 **둘 다** 있어야 재개 가능으로 본다.
    """
    meta_path, xlsx_path = _progress_path(out_dir), _partial_path(out_dir)
    if not (meta_path.exists() and xlsx_path.exists()):
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(meta.get("done"), list):
        return None
    return meta


def _save_progress(out_dir, date_from, date_to, started_at, done,
                   carry=False, grow=False, skip=False) -> None:
    _progress_path(out_dir).write_text(
        json.dumps({"date_from": date_from, "date_to": date_to, "started_at": started_at,
                    "done": list(done), "carry": carry, "grow": grow, "skip": skip},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")


def account_profile(account_id: str) -> str:
    """계정별 로그인 프로필 경로 (한 번 로그인하면 재사용)."""
    return f"{_PROFILES_DIR}/{account_id}"


def _product_matcher(product):
    """상품 단위 매처(옵션 통합) — 새 서식은 상품별 노출순위라 옵션의 vid/pid를 모두 합쳐 하나로 매칭."""
    vids, pids = set(), set()
    for opt in product.options:
        vids |= set(opt.vendor_item_ids)
        pids |= set(opt.product_ids)
    return make_matcher(product_ids=pids, vendor_item_ids=vids,
                        name_substr=None if (vids or pids) else product.name)


def _best(pair) -> int | None:
    """(ranks_pc, ranks_mobile) → 최상위 순위(없으면 None). 새 서식은 상품 단일 매처라 값 1개."""
    if not pair:
        return None
    pc, mo = pair
    vals = [v for v in (*pc.values(), *mo.values()) if v]
    return min(vals) if vals else None


def _measure(browser, keywords, matchers, log):
    """키워드들의 순위를 **병렬 fetch로 한 번에** 측정 → {키워드: (ranks_pc, ranks_mobile)}. 실패 시 순차 폴백.

    모바일은 RANK_INCLUDE_MOBILE=True 일 때만 측정한다(기본 제외 — 요청사항. `_set_mobile`/mobile 경로는 보존).
    select_keywords_light 의 measure_ranks 콜백 겸 키워드 동결 시 순위 측정에도 쓴다.
    """
    if not keywords:
        return {}
    try:
        pc = organic_ranks_batch(browser, keywords, matchers, log=log)
        mo = (organic_ranks_batch(browser, keywords, matchers, mobile=True, log=log)
              if config.RANK_INCLUDE_MOBILE else {})
    except RankBlocked:
        log("  [노출측정] 병렬 fetch 실패(차단/빈응답) → 순차 방식으로 폴백")
        pc, mo = {}, {}
        for kw in keywords:
            try:
                pc[kw] = organic_ranks(browser, kw, matchers, log=log)
                if config.RANK_INCLUDE_MOBILE:
                    mo[kw] = organic_ranks(browser, kw, matchers, mobile=True, log=log)
            except RankBlocked:
                log("  [노출측정] 쿠팡 검색 차단(과다 실행 시 Akamai) — 남은 순위 공란, 잠시 후/내일 재시도")
                break
    return {kw: (pc.get(kw, {}), mo.get(kw, {})) for kw in keywords}


def _measure_safe(browser, keywords, matchers, log):
    """순위 측정 예외 안전 래퍼 — 조회 중 browser 가 죽거나(TargetClosedError) 어떤 예외가 나도
    공란 처리하고 계속(순위는 부가지표, 실패가 전체 실행을 막지 않게)."""
    if not keywords:
        return {}
    try:
        return _measure(browser, keywords, matchers, log)
    except Exception as exc:
        log(f"  [순위] 측정 실패(공란 처리) — {exc.__class__.__name__}: {str(exc)[:80]}")
        return {}


def _vid_matcher(vids):
    """상품 고유ID(vendorItemId) 목록으로 검색결과 상품을 매칭 — ③ 순위조회는 product 객체 없이 vid만 안다."""
    return {"제품": make_matcher(vendor_item_ids=set(str(v) for v in vids if v))}


def _load_latest_wb(out: Path):
    """최신 결과 워크북 로드 — 마스터 우선, 없으면 진행중. (wb, path) 또는 (None, None)."""
    for p in (_master_path(out), _partial_path(out)):
        if p.exists():
            return OutputWorkbook.load(p), p
    return None, None


def _login_and_discover(a: Account, date_from, date_to, get_password, log):
    """계정 하나: (필요시) 로그인 → **같은 신선한 세션**에서 즉시 판매분석 발견 + 지표.

    반환: (report_account[활동 상품만] | None, {옵션ID: OptionMetric}, {옵션ID: 재고수량}).
    로그인 미완료면 (None, {}, {}) 반환 → 호출부가 건너뛰고 다음 계정으로(막힘 없음).
    """
    from .collector import (discover, save_discovered,  # 지연 import
                            fetch_inventory, InventoryFetchError)
    from playwright.sync_api import TimeoutError as PWTimeout  # 판매데이터 없음 판별용
    pw = get_password(a.account_id) if get_password else None
    # 기본은 **창 숨김**(offscreen). 로그인/2차인증이 필요할 때만 잠깐 창을 띄운다.
    with WingBrowser(profile_dir=account_profile(a.account_id), offscreen=True) as b:
        b.goto(WING_URL)
        b.page.wait_for_timeout(1500)
        if b.authenticated():
            log(f"  [{a.label}] 세션 재사용 → 이미 로그인됨 (창 안 뜸)")
        else:
            shown = {"v": False}

            def _need_user():   # 2차인증·봇챌린지 등 사람이 꼭 필요할 때만 창을 띄운다(1회)
                if not shown["v"]:
                    shown["v"] = True
                    log(f"  [{a.label}] ⚠ 로그인 창을 잠시 띄웁니다(2차인증/직접로그인 필요). 놀라지 마세요")
                    b.show()

            if pw and b.autofill_login(a.account_id, pw, on_log=log):
                log(f"  [{a.label}] ID/비번 자동입력·제출 — 창 숨긴 채 로그인 확인 중"
                    " (2차인증 필요할 때만 창 표시)")
            else:
                _need_user()   # 비번 없음/자동입력 실패 → 직접 로그인해야 하니 창 표시
                log(f"  [{a.label}] 직접 로그인이 필요해 창을 띄웠습니다")
            if not b.wait_for_login(timeout=300, on_log=log, tag=a.account_id, on_need_user=_need_user):
                log(f"  [{a.label}] 로그인 미완료 — 이 계정 건너뜀")
                return None, {}, {}
            b.hide()   # 로그인 끝나면 다시 숨김
        try:
            products, metrics = discover(b.page, date_from, date_to, log)   # 같은 세션에서 즉시 수집
        except PWTimeout:   # '엑셀 다운로드'/데이터 미표시 = 판매(수집) 상품 없음(정상)
            log(f"  [{a.label}] 판매분석 데이터 없음 — 정상(수집할 상품 없음), 건너뜀")
            return None, {}, {}
        # 로켓그로스(계약) 상품이 있으면 같은 세션에서 재고현황도 직접조회(개인계정은 재고 없음 → 생략)
        inventory: dict[str, int] = {}
        if any(p.kind == config.KIND_CONTRACT for p in products):
            try:
                inventory = fetch_inventory(b.page, log)
                log(f"  [{a.label}] 재고현황 {len(inventory)}개 옵션 조회")
            except InventoryFetchError as exc:   # 부가지표 — 실패해도 수집 전체는 진행(사유 명시)
                log(f"  [{a.label}] ⚠ 재고현황 조회 실패(계속) — {str(exc)[:120]}")
        _persist_session(a, b, log)                                 # 세션 3요소+쿠키 영속(부가)
    save_discovered(a.account_id, products)
    # 활동(조회/판매/방문>0) 있는 상품만 추적 대상으로
    active = [p for p in products
              if any((m := metrics.get(oid)) and (m.views or m.sales or m.visitors)
                     for opt in p.options for oid in opt.vendor_item_ids)]
    log(f"  [{a.label}] 상품 {len(products)}개 발견, 활동 {len(active)}개 추적")
    return Account(a.account_id, a.representative, a.business_name, active), metrics, inventory


def _persist_session(a: Account, b, log) -> None:
    """로그인 성공 세션(3요소+쿠키[_abck 포함])을 영속 — 재사용·생존검증·데이터 HTTP 호출용.

    수집이 이미 끝난 뒤의 **부가 작업**이라, 실패해도 수집 결과엔 영향이 없다(사유를 명시 로그).
    ⚠️ is_alive/extract_vendor_id 의 엔드포인트는 사무실 라이브에서 최종 검증 대상.
    """
    try:
        alive = wing_session.is_alive(b.page)
        vid = wing_session.extract_vendor_id(b.page)
        SessionStore().save(a.account_id, wing_session.capture(b.context, vid))
        log(f"  [세션] 저장됨 (생존검증={alive}, vendorId={'추출' if vid else '미확인'})")
    except Exception as exc:
        log(f"  [세션] 영속 스킵 — {exc.__class__.__name__}: {str(exc)[:60]}")


def _inventory_by_product(products, inv_by_vid: dict) -> dict:
    """{옵션ID(vendorItemId): 재고수량} → {상품명: 상품의 모든 vid 재고 합산}.

    한 상품(productId)에 vendorItem 여러 개면(재등록 등) 판매가능 재고를 합산해 상품단위 재고현황으로.
    매칭되는 vid가 하나도 없으면 그 상품은 넣지 않음(재고현황 공란).
    """
    out: dict[str, int] = {}
    if not inv_by_vid:
        return out
    for p in products:
        vals = [inv_by_vid[oid] for opt in p.options for oid in opt.vendor_item_ids if oid in inv_by_vid]
        if vals:
            out[p.name] = sum(vals)
    return out


def _fill_product_metrics(wb, biz, product, metrics, inventory, date_iso) -> None:
    """상품단위 판매지표 기록 — 계약(로켓그로스)=판매량/방문자/노출량/재고현황, 개인=전체판매량/전체노출량.

    옵션 지표를 상품 단위로 합산한다. 재고현황(판매가능 수량)은 inventory[상품명](Phase2 rfm-inventory)에서.
    """
    views = sales = visitors = 0
    for opt in product.options:
        for oid in opt.vendor_item_ids:
            m = metrics.get(oid)
            if m:
                views += m.views
                sales += m.sales
                visitors += m.visitors
    if product.kind == config.KIND_CONTRACT:
        wb.set_product_metric(biz, product.name, config.M_SALES, date_iso, sales)
        wb.set_product_metric(biz, product.name, config.M_VISITORS, date_iso, visitors)
        wb.set_product_metric(biz, product.name, config.M_VIEWS, date_iso, views)
        inv = inventory.get(product.name) if inventory else None
        if inv is not None:
            wb.set_product_metric(biz, product.name, config.M_INVENTORY, date_iso, inv)
    else:
        wb.set_product_metric(biz, product.name, config.M_TOTAL_SALES, date_iso, sales)
        wb.set_product_metric(biz, product.name, config.M_TOTAL_VIEWS, date_iso, views)


def _log_diagnose(product, track_info, ai_key, log) -> None:
    """진단(제목포함×순위)·공략우선순위·권고제목을 **로그로** 남긴다(새 서식엔 미기록, 셀러 참고용).

    track_info: [(키워드, 검색량, 경쟁정도, 순위)]. 새 서식은 검색량·순위만 기록하고, 이 분석은 로그로 제공.
    """
    if not track_info:
        return
    title = product.display_title
    for kw, vol, comp, rank in track_info:
        diag = diagnose_exposure(keyword_in_title(kw, title), rank, None)
        log(f"  [진단] '{kw}': {diag} · 공략우선순위 {attack_priority(vol, comp_from_idx(comp))}"
            f" · 순위 {rank_label(rank)}")
    kws_by_vol = [kw for kw, _v, _c, _r in sorted(track_info, key=lambda x: x[1], reverse=True)]
    try:
        rec = recommend_title(title, kws_by_vol, api_key=ai_key)
    except KeywordAIError as exc:
        log(f"  [제목] 권고제목 생성 실패 — {exc.__class__.__name__}: {str(exc)[:60]}")
        rec = ""
    cov = round(sum(1 for kw, *_ in track_info if keyword_in_title(kw, title)) / len(track_info) * 100)
    log(f"  [제목] 현재: {title}")
    log(f"  [제목] 커버리지 {cov}% → 권고: {rec or '(생성실패)'}")


def _process_account(report_acc, wb, naver, ai_key, browser, metrics, inventory,
                     date_iso, grow, log, save_path, skip_ranks: bool = False,
                     keywords_off: bool = False) -> None:
    """계정(시트) 하나: 상품마다 [키워드 동결/선정 → 순위(PC) → 상품지표+재고 → 진단로그] 후 저장.

    - 기존 상품(시트에 키워드 있음): **키워드 동결**, 순위만 조회(grow=True면 상한 내 발굴 추가).
    - 새 상품: AI 선정 + 선정단계 순위 재사용. 순위는 상품 단위(옵션 통합, PC).
    - skip_ranks=True(날짜 지정 수집): 쿠팡 순위 조회를 제외(browser=None). 키워드는 있으면 재사용,
      없으면 순위 없이(네이버+AI 부분점수) 선정. 판매지표·재고만 채운다(차단 회피).
    - keywords_off=True(① 판매수집 단계): 키워드·순위 없이 지표·재고·상품ID만 기록(키워드는 ②, 순위는 ③).
    상품마다 save_path 저장 → 도중 끊겨도 이어감.
    """
    biz = report_acc.label   # 시트명 = 사업자명, 없으면 대표자명·계정ID(빈 시트명 KeyError 방지)
    wb.ensure_account(biz)
    for product in report_acc.products:
        title = product.display_title
        kind = product.kind or config.KIND_PERSONAL
        if keywords_off:                               # ① 판매수집 단계 — 지표·재고·상품ID만
            wb.ensure_product_block(biz, product.name, kind, wb.product_keywords(biz, product.name))
            wb.set_product_vids(biz, product.name,
                                [oid for opt in product.options for oid in opt.vendor_item_ids])
            _fill_product_metrics(wb, biz, product, metrics, inventory, date_iso)
            wb.save(save_path)
            continue
        pmatcher = {"제품": _product_matcher(product)}

        def measure(kws, _m=pmatcher):
            return _measure_safe(browser, kws, _m, log)   # 순위 실패해도 판매데이터 완주

        measure_cb = measure if (browser is not None and not skip_ranks) else None
        existing = wb.product_keywords(biz, product.name)
        if existing:                                   # 기존 상품 → 키워드 동결
            keywords = list(existing)
            wb.ensure_product_block(biz, product.name, kind, keywords)   # no-op
            if grow and len(existing) < config.KW_MAX_TRACK and browser is not None:
                want = min(config.KW_ADD_PER_DAY, config.KW_MAX_TRACK - len(existing))
                found = select_keywords_light(title, naver, ai_key, browser=browser, log=log,
                                              n=want, measure_ranks=measure, exclude=set(existing))
                add = [t for t in found if t.keyword not in existing][:want]
                if add:
                    wb.add_product_keywords(biz, product.name, [t.keyword for t in add])
                    for t in add:
                        wb.set_keyword_search(biz, product.name, t.keyword, t.volume)
                    keywords += [t.keyword for t in add]
                    log(f"  [키워드] {title} → 동결 {existing} + 발굴 {[t.keyword for t in add]}")
                else:
                    log(f"  [키워드] {title} → (동결) {keywords}")
            else:
                log(f"  [키워드] {title} → (동결) {keywords}")
            todo = [kw for kw in keywords if not wb.is_rank_filled(biz, product.name, kw, date_iso)]
            measured = measure(todo) if (browser is not None and todo) else {}
            ranks = {kw: _best(measured.get(kw)) for kw in todo if kw in measured}  # 측정 실패는 공란
            track_info = [(kw, 0, "", ranks.get(kw)) for kw in keywords]   # 동결분은 검색량/경쟁 미측정
        else:                                          # 새 상품 → AI 선정(skip_ranks면 순위 없이 부분점수)
            tracks = select_keywords_light(title, naver, ai_key, browser=browser, log=log,
                                           measure_ranks=measure_cb)
            keywords = [t.keyword for t in tracks]
            wb.ensure_product_block(biz, product.name, kind, keywords)
            for t in tracks:
                wb.set_keyword_search(biz, product.name, t.keyword, t.volume)
            ranks = {t.keyword: t.exposure_best for t in tracks}          # 선정단계 순위 재사용
            track_info = [(t.keyword, t.volume, t.comp_idx, t.exposure_best) for t in tracks]
            log(f"  [키워드] {title} → {keywords}")

        if not skip_ranks:                             # 순위 기록(PC). 날짜지정 수집(skip_ranks)은 순위 제외
            for kw in keywords:                        # 이미 채워진 건 건너뜀
                if kw in ranks and not wb.is_rank_filled(biz, product.name, kw, date_iso):
                    wb.set_keyword_rank(biz, product.name, kw, date_iso, ranks.get(kw))
                    log(f"  [순위] '{kw}': {rank_label(ranks.get(kw))}")
        wb.set_product_vids(biz, product.name,   # 상품 고유ID 저장(③ 순위조회 상품 매칭용)
                            [oid for opt in product.options for oid in opt.vendor_item_ids])
        _fill_product_metrics(wb, biz, product, metrics, inventory, date_iso)
        _log_diagnose(product, track_info, ai_key, log)
        wb.save(save_path)


def run_full(input_list: InputList, naver: NaverAdApi, out_dir: str = "output",
             ai_key: str | None = None, date_from: str | None = None, date_to: str | None = None,
             get_password=None, resume: bool = False, carry_forward: bool = False,
             grow_keywords: bool = False, skip_ranks: bool = False,
             keywords_off: bool = False, on_log=None) -> Path:
    """계정별 end-to-end 완결 + **같은 날 이어서 하기** + **통계 마스터 이어쓰기(cross-day)**.

    실행 모드(하루 1회 실행 전제):
    - **새 통계(fresh)**: `carry_forward=False`. 빈 워크북에서 상품마다 키워드를 선정(첫날). 마스터가
      이미 있으면 보관(백업)한 뒤 새로 시작한다.
    - **통계 이어쓰기(carry_forward=True)**: 마스터(`쿠팡데이타분석_통계.xlsx`)를 불러와 **기존 키워드를
      동결**하고 오늘 날짜 컬럼만 채운다(시계열 의미 유지). `grow_keywords=True`면 상한(KW_MAX_TRACK) 안에서
      상품당 하루 최대 KW_ADD_PER_DAY개 **새 키워드만 발굴 추가**(기존은 절대 제거 안 함).
    - **같은 날 크래시 복구(resume=True)**: `진행중.xlsx`(+`.json`)를 읽어 완료 계정은 건너뛰고 끊긴
      지점부터 이어간다. 진행 상태에 carry/grow 플래그가 있어 그 모드 그대로 재개된다.

    완료되면 마스터를 갱신하고 그날 스냅샷(`쿠팡데이타분석_통계_yymmdd.xlsx`)을 남긴 뒤 진행파일을 지운다.
    키워드는 AI로 도출하므로 `ai_key` 필수(없으면 KeywordAIError). 한 계정이 막혀도 그 계정만 건너뛴다.
    """
    log = on_log or (lambda m: None)
    if not ai_key:
        raise KeywordAIError("OpenAI(ChatGPT) API 키가 없어 키워드 추출을 할 수 없습니다. "
                             "설정 탭에서 OpenAI API 키를 입력한 뒤 다시 실행하세요.")
    now = datetime.now()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    partial, prog = _partial_path(out), _progress_path(out)

    master = _master_path(out)
    meta = resumable_progress(out) if resume else None
    if meta:                                   # 같은 날 크래시 복구 — 기간·완료계정·진행엑셀·모드 복원
        date_from, date_to = meta["date_from"], meta["date_to"]
        started_at = meta["started_at"]
        done = set(meta["done"])
        carry = bool(meta.get("carry", False))
        grow = bool(meta.get("grow", False))
        skip_ranks = bool(meta.get("skip", False))   # 재개 시 순위제외 모드도 그대로 유지
        wb = OutputWorkbook.load(partial)
        log(f"== 이어서 실행({'통계이어쓰기' if carry else '새통계'}) — 완료 {len(done)}개 건너뜀, "
            f"기간 {date_from}~{date_to} ==")
    else:                                      # 새 실행(오늘)
        date_to = date_to or now.strftime("%Y-%m-%d")
        date_from = date_from or date_to
        started_at = now.strftime("%Y-%m-%d %H:%M:%S")
        done = set()
        carry = carry_forward and master.exists()
        grow = grow_keywords and carry
        if carry_forward and not master.exists():
            log("== 통계 마스터가 없어 '새 통계'로 시작합니다 ==")
        if carry:
            wb = OutputWorkbook.load(master)   # 기존 통계 이어쓰기(키워드 동결 + 오늘 컬럼)
            log(f"== 통계 이어쓰기 — 마스터 로드, 오늘({date_to}) 컬럼 추가"
                f"{' · 새 키워드 발굴 추가' if grow else ' · 키워드 동결'} ==")
        else:
            if not carry_forward and master.exists():   # 명시적 '새 통계' → 기존 마스터 보관(백업)
                bak = out / f"{config.OUTPUT_FILE_PREFIX}_통계_보관_{now.strftime('%y%m%d_%H%M%S')}.xlsx"
                master.rename(bak)
                log(f"== 기존 통계 마스터를 보관함: {bak.name} ==")
            wb = OutputWorkbook.empty()
            log(f"== 새 통계 시작 — {len(input_list.accounts)}개 계정, 기간 {date_from}~{date_to} ==")
        for p in (partial, prog):
            if p.exists():
                p.unlink()
        wb.save(partial)                       # 크래시 복구 기준선(carry면 마스터 내용 포함)
        _save_progress(out, date_from, date_to, started_at, done, carry, grow, skip_ranks)

    # 일자 컬럼 라벨 = 서식과 동일한 yy.mm.dd(단일일). 범위면 from~to.
    if date_from == date_to:
        try:
            col_label = datetime.strptime(date_to, "%Y-%m-%d").strftime("%y.%m.%d")
        except ValueError:
            col_label = date_to
    else:
        col_label = f"{date_from}~{date_to}"
    log(f"== 수집 대상 구간(컬럼): {col_label} ==")

    accounts = input_list.accounts
    total = len(accounts)
    for i, a in enumerate(accounts, 1):
        if a.account_id in done:                  # 완료 계정 → 건너뜀
            log(f"== [{i}/{total}] {a.label} — 이미 완료, 건너뜀 ==")
            continue
        log(f"== [{i}/{total}] {a.label} (계정ID: {a.account_id}) ==")
        try:   # 한 계정의 어떤 오류(로그인·수집·워크북쓰기)도 전체를 막지 않게 계정 전체를 격리
            report_acc, metrics, inv_by_vid = _login_and_discover(a, date_from, date_to, get_password, log)
            if report_acc is None:      # 로그인 미완료/데이터 없음 → 다음 계정(전체 안 막힘)
                continue

            # 자동완성(키워드 후보)·순위 모두 비로그인 쿠팡 세션이 필요하다. 로그인 브라우저가 닫힌 뒤 별도로
            # 연다(중첩 금지 — sync playwright 충돌 방지). 활동 상품이 있을 때만 열고, 그 한 세션에서
            # 키워드 선정(자동완성)→순위까지 재사용한다(warmup 먼저 = 쿠팡 오리진 로드, same-origin fetch).
            if report_acc.products:
                # 재고현황: {옵션ID:수량} → {상품명: 상품 vid 합산}(상품당 vendorItem 여러 개일 수 있음)
                inventory = _inventory_by_product(report_acc.products, inv_by_vid)
                if skip_ranks or keywords_off:
                    # 순위 제외(날짜지정) 또는 판매수집 전용(①): 쿠팡 순위 브라우저 안 열고(차단 접촉 0)
                    # 판매지표·재고·상품ID만(keywords_off) 또는 + 키워드(재사용/부분점수 선정)만 기록
                    _process_account(report_acc, wb, naver, ai_key, None, metrics, inventory,
                                     col_label, grow, log, partial, skip_ranks=skip_ranks,
                                     keywords_off=keywords_off)
                else:
                    with WingBrowser(profile_dir=_PROFILE, offscreen=True) as rank_browser:
                        warmup(rank_browser)
                        _process_account(report_acc, wb, naver, ai_key, rank_browser, metrics, inventory,
                                         col_label, grow, log, partial)
            else:                                        # 활동 상품 0개 → Chrome 개방 생략, 시트도 생략
                log(f"  [{a.label}] 활동 상품 0개 — 시트·키워드·순위 생략")

            done.add(a.account_id)                    # 이 계정 완료 확정
            _save_progress(out, date_from, date_to, started_at, done, carry, grow, skip_ranks)
            wb.save(partial)
            log(f"  [{a.label}] 완료 — 진행 {len(done)}/{total} (진행 저장: {partial.name})")
        except Exception as exc:
            first = (str(exc).splitlines() or [""])[0][:250]
            log(f"  [{a.label}] 처리 오류: {exc.__class__.__name__}: {first} — 건너뜀")
            continue

    # 전부 완료 → 통계 마스터 갱신 + 그날 스냅샷 저장, 진행 상태 정리
    snapshot = _snapshot_path(out, now)
    wb.apply_style()         # 가독성 서식(헤더 고정·상품 구분·정렬) — 최종본에만
    wb.save(master)          # 다음 날 이어쓸 마스터
    wb.save(snapshot)        # 그날 백업본(감사용)
    for p in (partial, prog):
        if p.exists():
            p.unlink()
    log(f"== 완료: 마스터 {master.name} · 스냅샷 {snapshot.name} (성공 {len(done)}/{total} 계정) ==")
    return snapshot


def select_keywords_stage(naver: NaverAdApi, ai_key: str | None, out_dir: str = "output",
                          grow: bool = False, on_log=None) -> Path | None:
    """② 키워드 선정 전용 — 최신 워크북 로드, 상품별 키워드(**순위 조회 없음**) 선정·기록. 로그인 불필요.

    ①(판매수집)로 상품이 이미 워크북에 있어야 한다. 기존 키워드가 있으면 동결(grow=True면 상한 내 발굴
    추가), 없으면 새로 선정한다. 쿠팡 순위는 조회하지 않는다(measure_ranks=None) — 순위는 ③에서.
    자동완성(쿠팡, 비로그인)만 쓰므로 로그인 브라우저는 열지 않는다.
    """
    log = on_log or (lambda m: None)
    if not ai_key:
        raise KeywordAIError("OpenAI(ChatGPT) API 키가 없어 키워드 선정을 할 수 없습니다. "
                             "설정 탭에서 OpenAI API 키를 입력한 뒤 다시 실행하세요.")
    out = Path(out_dir)
    wb, path = _load_latest_wb(out)
    if wb is None:
        log("== 키워드 선정: 결과 워크북이 없습니다 — 먼저 ①(판매데이터 수집)을 실행하세요 ==")
        return None
    log(f"== 키워드 선정 시작(순위 조회 없음) — {path.name} ==")
    with WingBrowser(profile_dir=_PROFILE, offscreen=True) as browser:
        warmup(browser)
        for biz in wb.account_sheets():
            for pname in wb.products_of(biz):
                existing = wb.product_keywords(biz, pname)
                if existing and not grow:                  # 이미 키워드 있음(사람 입력 포함) → 동결, 스킵
                    log(f"  [{biz}] {pname} → 키워드 있음, 건너뜀(동결) {existing}")
                    continue
                try:
                    if grow and existing:                  # 상한 내 발굴 추가
                        want = min(config.KW_ADD_PER_DAY, config.KW_MAX_TRACK - len(existing))
                        if want <= 0:
                            continue
                        tracks = select_keywords_light(pname, naver, ai_key, browser=browser, log=log,
                                                       n=want, measure_ranks=None, exclude=set(existing))
                        new = [t for t in tracks if t.keyword not in existing][:want]
                        if new:
                            wb.add_product_keywords(biz, pname, [t.keyword for t in new])
                            for t in new:
                                wb.set_keyword_search(biz, pname, t.keyword, t.volume)
                            log(f"  [{biz}] {pname} → 발굴 추가 {[t.keyword for t in new]}")
                    else:                                  # 새 상품 → 선정
                        tracks = select_keywords_light(pname, naver, ai_key, browser=browser,
                                                       log=log, measure_ranks=None)
                        wb.add_product_keywords(biz, pname, [t.keyword for t in tracks])
                        for t in tracks:
                            wb.set_keyword_search(biz, pname, t.keyword, t.volume)
                        log(f"  [{biz}] {pname} → 키워드 {[t.keyword for t in tracks]}")
                except KeywordAIError as exc:
                    log(f"  [{biz}] {pname} 키워드 선정 실패(건너뜀) — {str(exc)[:80]}")
            wb.save(path)
    log("== 키워드 선정 완료 ==")
    return path


def track_ranks_stage(out_dir: str = "output", on_log=None) -> Path | None:
    """③ 노출순위 조회 전용 — 최신 워크북 로드, 상품(고유ID)+키워드로 순위 측정·기록. 로그인 불필요.

    ①(상품ID)·②(키워드)가 이미 워크북에 있어야 한다. 상품마다 저장된 vendorItemId 로 검색결과에서 내
    상품을 찾아 오가닉 순위를 기록한다(가장 최근 일자 컬럼). 예외 안전 — 차단·browser 죽음도 공란 처리.
    """
    log = on_log or (lambda m: None)
    out = Path(out_dir)
    wb, path = _load_latest_wb(out)
    if wb is None:
        log("== 순위 조회: 결과 워크북이 없습니다 — 먼저 ①②를 실행하세요 ==")
        return None
    log(f"== 노출순위 조회 시작 — {path.name} ==")
    if config.RANK_HUMAN_SERIAL:
        log(f"  [모드] 사람속도 직렬(동시성1·요청간격 {config.RANK_FETCH_JITTER_MIN_MS/1000:.1f}"
            f"~{config.RANK_FETCH_JITTER_MS/1000:.1f}s) — 버스트 없이 차단 회피")
    with WingBrowser(profile_dir=_PROFILE, offscreen=True) as browser:
        warmup(browser)
        for biz in wb.account_sheets():
            date = wb.latest_date(biz)
            if not date:
                continue
            for pname in wb.products_of(biz):
                vids = wb.product_vids(biz, pname)
                keywords = wb.product_keywords(biz, pname)
                if not (vids and keywords):                # 상품ID나 키워드 없으면 건너뜀
                    continue
                todo = [kw for kw in keywords if not wb.is_rank_filled(biz, pname, kw, date)]
                if not todo:
                    continue
                measured = _measure_safe(browser, todo, _vid_matcher(vids), log)
                for kw in todo:
                    if kw not in measured:            # 측정 실패(예외·차단) → 공란 유지(다음에 재시도)
                        continue
                    r = _best(measured.get(kw))       # 정상 측정: 미노출이면 '-', 노출이면 'N위'
                    wb.set_keyword_rank(biz, pname, kw, date, r)
                    log(f"  [{biz}] {pname} '{kw}': {rank_label(r)}")
            wb.save(path)
    log("== 노출순위 조회 완료 ==")
    return path
