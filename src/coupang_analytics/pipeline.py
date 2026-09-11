"""전체 실행 오케스트레이션(`run_full`) — **계정별로 처음부터 끝까지 완결 + 이어서 하기 지원**.

계정마다 [로그인(방금 연 세션) → 판매분석 발견·지표 → 키워드 → 순위]를 완결하고 다음 계정으로.
결과는 통합 워크북 1개에 누적하고, 진행 중엔 `쿠팡데이타분석_진행중.xlsx`(+`.json` 상태)에
저장하며, 전부 끝나면 날짜·시각이 붙은 최종본으로 이름을 바꾼다. 이어서 할 때는 완료 계정을
건너뛰고, 미완료 계정은 키워드 재사용 + 이미 조회한 순위 건너뛰기로 끊긴 지점부터 이어간다.
순위 조회는 부하가 크므로 순차로 지연을 두며, 차단되면 공란 처리하고 계속 진행한다.
"""
from __future__ import annotations

import json
import random
import time
from datetime import datetime
from pathlib import Path

from . import config
from .browser import WING_URL, WingBrowser
from .input_list import Account, InputList, InputValidationError, validate_input_list
from . import wing_session
from . import session_state
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


# 순위 차단(Akamai 챌린지) 감지 시 이번 실행의 순위 조회를 전면 중단(더 두드리지 않음). 실행마다 리셋.
_RANK_HALT = {"stop": False}
# 서킷브레이커 — 이번 실행에 쓴 cooldown 횟수(상한 초과 시 당일 중지). 실행마다 리셋.
_RANK_CB = {"cooldowns": 0}
_RANK_TELEMETRY_ID = "__rank__"   # 순위 응답 관측용 합성 계정ID(session_events 에 rank_* 이벤트)


def _reset_rank_state() -> None:
    """실행 시작 시 순위 차단 상태 초기화 — halt 플래그 해제 + 서킷브레이커 cooldown 카운터 리셋."""
    _RANK_HALT["stop"] = False
    _RANK_CB["cooldowns"] = 0


def _rank_cooldown(browser, log, reason: str) -> bool:
    """이상징후 → 신규검색 중지 → 충분한 cooldown → (홈 1회 = 소량 정상요청). 재개 가능하면 True.

    cooldown 반복이 상한(RANK_COOLDOWN_MAX) 초과면 당일 중지(False). 우회 재요청은 하지 않는다 —
    호출부가 True면 같은 검색을 1회 재측정(=probe)해 정상 여부를 확인한다.
    """
    _RANK_CB["cooldowns"] += 1
    if _RANK_CB["cooldowns"] > config.RANK_COOLDOWN_MAX:
        _RANK_HALT["stop"] = True
        log(f"  [노출측정] ⛔ 이상징후 반복({reason}) — cooldown {config.RANK_COOLDOWN_MAX}회 초과, "
            "당일 중지. 쉰 시간/IP에 다시 실행하면 남은 것부터 이어서")
        return False
    cd = config.RANK_COOLDOWN_SEC
    log(f"  [노출측정] ⚠ 이상징후 감지({reason}) → 신규검색 즉시 중지, {cd // 60}분 cooldown 후 "
        f"probe(재측정)로 상태확인 (cooldown {_RANK_CB['cooldowns']}/{config.RANK_COOLDOWN_MAX})")
    time.sleep(cd)
    try:
        warmup(browser)          # 홈 1회(신뢰쿠키 갱신) = 소량 정상요청
    except Exception:
        pass
    return True


class RankHalt(Exception):
    """순위 조회 중 차단 감지 → 즉시 중단 신호. `.partial` = 중단 전까지 측정된 {키워드:(pc,mo)}."""
    def __init__(self, partial=None):
        super().__init__("순위 차단 감지 — 중단")
        self.partial = partial or {}


def _measure_nav_serial(browser, keywords, matchers, log, matched_out=None):
    """기본(안전) 순위 측정 — **사람처럼 검색창을 하나씩** 직렬 네비게이션 + 랜덤 간격(RANK_NAV_DELAY).

    **서킷브레이커**: 이상징후(응답시간 급증 RANK_SLOW_ABS_SEC↑ · 403/429/Akamai 챌린지 RankBlocked)를
    감지하면 신규검색을 즉시 중지하고 충분한 cooldown(RANK_COOLDOWN_SEC) 후 같은 검색을 1회 재측정(probe)한다.
    정상이면 재개, 또 이상이면 cooldown 반복(상한 RANK_COOLDOWN_MAX)→초과 시 당일 중지(_RANK_HALT)+RankHalt.
    우회 재요청은 하지 않는다. 각 응답은 관측층에 기록(rank_ok/rank_empty/rank_challenge).
    matched_out 를 주면 매칭된 검색결과 항목(정확 노출명 포함)을 채워 호출부가 노출명 갱신에 쓴다.
    """
    pc: dict = {}
    for i, kw in enumerate(keywords):
        if _RANK_HALT["stop"]:
            break
        if i > 0:   # 검색 사이 사람 간격(버스트 제거 = 차단 회피)
            d = random.uniform(config.RANK_NAV_DELAY_MIN_SEC, config.RANK_NAV_DELAY_MAX_SEC)
            log(f"  [노출측정] 다음 검색까지 {d:.0f}s 대기(사람 속도)")
            time.sleep(d)
        while True:   # 이상징후 → cooldown 후 같은 kw 재측정(probe). 반복 상한 초과면 당일 중지.
            try:
                t0 = time.monotonic()
                r = organic_ranks(browser, kw, matchers, log=log, matched_out=matched_out)
                dt = time.monotonic() - t0
                if dt >= config.RANK_SLOW_ABS_SEC:      # 응답시간 급증 = 이상징후(조기감지)
                    if not _rank_cooldown(browser, log, f"응답 {dt:.0f}s 급증"):
                        raise RankHalt({k: (pc[k], {}) for k in pc})
                    continue                            # cooldown 후 같은 kw 재측정(probe)
                pc[kw] = r
                session_state.record_event(
                    _RANK_TELEMETRY_ID, "rank_ok" if any(v is not None for v in r.values()) else "rank_empty")
                break
            except RankBlocked:                         # 403/429/Akamai 챌린지 = 이상징후
                session_state.record_event(_RANK_TELEMETRY_ID, "rank_challenge")
                if not _rank_cooldown(browser, log, "차단(403/Challenge)"):
                    raise RankHalt({k: (pc[k], {}) for k in pc})
                continue                                # cooldown 후 같은 kw 재측정(probe)
    return {kw: (pc.get(kw, {}), {}) for kw in keywords}


def _measure(browser, keywords, matchers, log, matched_out=None):
    """키워드들의 순위 측정 → {키워드: (ranks_pc, ranks_mobile)}.

    기본 = 직렬 네비게이션(RANK_NAV_SERIAL, 안전). False면 (구) 병렬 fetch 경로(빠르나 봇틱).
    이번 실행에 이미 차단 감지(_RANK_HALT)면 즉시 빈 결과(더 두드리지 않음).
    모바일은 RANK_INCLUDE_MOBILE=True 일 때만(기본 제외).
    matched_out(선택)엔 매칭된 검색결과 항목이 담겨 노출명 갱신에 쓰인다(직렬 경로에서만).
    """
    if not keywords or _RANK_HALT["stop"]:
        return {}
    if config.RANK_NAV_SERIAL:
        return _measure_nav_serial(browser, keywords, matchers, log, matched_out)
    try:   # (구) 병렬 fetch 경로 — 옵션
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


def _measure_safe(browser, keywords, matchers, log, matched_out=None):
    """순위 측정 예외 안전 래퍼(run_full 경로) — 어떤 예외가 나도 공란 처리하고 계속(순위는 부가지표).

    차단(RankHalt)이면 부분결과를 돌려주고, 이후 _measure 는 _RANK_HALT 로 자동 no-op → 그 실행의
    나머지 순위는 안 두드린다(자동 중단). track_ranks_stage(③)는 RankHalt 를 직접 잡아 중단·저장한다.
    """
    if not keywords:
        return {}
    try:
        return _measure(browser, keywords, matchers, log, matched_out)
    except RankHalt as h:
        return h.partial
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


class NeedLogin(Exception):
    """세션이 없어 로그인이 필요한 계정(세션우선 1차 패스에서 뒤로 미룸)."""


class LoginBlocked(Exception):
    """Akamai 로그인 차단(Access Denied) — 서킷브레이커 카운트 대상."""


def _login_and_discover(a: Account, date_from, date_to, get_password, log, login: bool = True):
    """계정 하나: (필요시) 로그인 → **같은 신선한 세션**에서 즉시 판매분석 발견 + 지표.

    반환: (report_account[활동 상품만] | None, {옵션ID: OptionMetric}, {옵션ID: 재고수량}).
    로그인 미완료면 (None, {}, {}) 반환 → 호출부가 건너뛰고 다음 계정으로(막힘 없음).
    login=False(세션우선 1차): 세션 없으면 자동제출하지 않고 **NeedLogin** 을 던져 뒤로 미룬다
    (반복 자동로그인 = IP 차단 유발이라, 세션 살아있는 계정을 먼저 다 수집). Akamai 차단 시 LoginBlocked.
    """
    from .collector import (discover, save_discovered,  # 지연 import
                            fetch_inventory, InventoryFetchError)
    from .product_match import scope_to_ledger
    from playwright.sync_api import TimeoutError as PWTimeout  # 판매데이터 없음 판별용
    pw = get_password(a.account_id) if get_password else None
    # 기본은 **창 숨김**(offscreen). 로그인/2차인증이 필요할 때만 잠깐 창을 띄운다.
    with WingBrowser(profile_dir=account_profile(a.account_id), offscreen=True) as b:
        b.goto(WING_URL)
        b.page.wait_for_timeout(1500)
        if b.authenticated():
            log(f"  [{a.label}] 세션 재사용 → 이미 로그인됨 (창 안 뜸)")
            session_state.observe_session_ok(a.account_id, final_url=b.page.url)   # 관측(제어흐름 불변)
        elif not login:            # 세션우선 1차 패스 — 자동제출 안 하고 로그인 대기열로 미룸
            session_state.observe_reauth_required(a.account_id, final_url=b.page.url)
            raise NeedLogin()
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
                code, detail = b.classify_login()
                ftype = session_state.failure_type_of(code, detail)   # 세분 실패분류(탐지코드는 불변)
                session_state.observe_auth_failure(a.account_id, ftype, final_url=b.page.url)
                if code == "blocked":   # Akamai 차단 → 서킷브레이커가 세도록 신호
                    log(f"  [{a.label}] Akamai 로그인 차단 — 이 계정 건너뜀")
                    raise LoginBlocked()
                log(f"  [{a.label}] 로그인 미완료 — 이 계정 건너뜀")
                return None, {}, {}
            session_state.observe_auth_success(a.account_id, final_url=b.page.url)
            b.goto(WING_URL)                     # 신선 로그인 후 wing 안착(인증 리다이렉트 완료 대기)
            b.page.wait_for_timeout(1500)        # 페이지 안정 — discover fetch 가 진행중 네비에 중단(Failed to fetch)되는 것 방지
            b.hide()   # 로그인 끝나면 다시 숨김
        try:
            products, metrics = discover(b.page, date_from, date_to, log)   # 같은 세션에서 즉시 수집
        except PWTimeout:   # '엑셀 다운로드'/데이터 미표시 = 판매(수집) 상품 없음(정상)
            log(f"  [{a.label}] 판매분석 데이터 없음 — 정상(수집할 상품 없음), 건너뜀")
            session_state.observe_collection_empty(a.account_id)
            return None, {}, {}
        except Exception as exc:   # 신선 로그인 직후 페이지 미안착 → fetch 중단(Failed to fetch). wing 재안착 후 1회 재시도
            if "Failed to fetch" not in str(exc):
                raise
            log(f"  [{a.label}] discover fetch 중단(Failed to fetch) — wing 재안착 후 1회 재시도")
            b.goto(WING_URL)
            b.page.wait_for_timeout(2500)
            try:
                products, metrics = discover(b.page, date_from, date_to, log)
            except PWTimeout:
                log(f"  [{a.label}] 판매분석 데이터 없음 — 정상(수집할 상품 없음), 건너뜀")
                session_state.observe_collection_empty(a.account_id)
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
        session_state.observe_collection_done(a.account_id)         # 관측: 이 계정 수집 완료 시각
    save_discovered(a.account_id, products)
    # 추적 범위 = 입력 대장 상품(위탁 관리분)만. 대장↔발견을 매칭해 노출제목·vid·구분 부여,
    # 미매칭(휴면 등)은 대장명으로 추적(지표·재고 공란). 판매중지/취소선 상품은 입력 파싱에서 이미 제외됨.
    tracked, n_match = scope_to_ledger(a.products, products)
    log(f"  [{a.label}] 발견 {len(products)}개 · 대장 {len(a.products)}개 → 추적 {len(tracked)}개(매칭 {n_match})")
    return Account(a.account_id, a.representative, a.business_name, tracked), metrics, inventory


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


def _fill_product_metrics(wb, biz, product, metrics, inventory, date_iso, pname=None) -> None:
    """상품단위 판매지표 기록 — 기본 판매량/방문자/노출량(계약·개인 공통), 재고현황은 로켓그로스(계약)만.

    옵션 지표를 상품 단위로 합산한다. 재고현황(판매가능 수량)은 inventory[상품명](Phase2 rfm-inventory)에서.
    pname = 워크북 블록 이름(정확 노출명으로 갱신됐을 수 있음). inventory 는 발견명(product.name)으로 키.
    """
    pname = pname or product.name
    views = sales = visitors = 0
    for opt in product.options:
        for oid in opt.vendor_item_ids:
            m = metrics.get(oid)
            if m:
                views += m.views
                sales += m.sales
                visitors += m.visitors
    wb.set_product_metric(biz, pname, config.M_SALES, date_iso, sales)
    wb.set_product_metric(biz, pname, config.M_VISITORS, date_iso, visitors)
    wb.set_product_metric(biz, pname, config.M_VIEWS, date_iso, views)
    if product.kind == config.KIND_CONTRACT:   # 재고현황은 로켓그로스만
        inv = inventory.get(product.name) if inventory else None
        if inv is not None:
            wb.set_product_metric(biz, pname, config.M_INVENTORY, date_iso, inv)


def _log_diagnose(product, track_info, ai_key, log, wb=None, biz=None, roles=None, pname=None) -> None:
    """진단(제목포함×순위)·공략우선순위·역할·권고제목을 **로그로** 남긴다(새 서식엔 미기록, 셀러 참고용).

    track_info: [(키워드, 검색량, 경쟁정도, 순위)]. 새 서식은 검색량·순위만 기록하고, 이 분석은 로그로 제공.
    roles: {키워드: 역할}(REP/SALES/GROWTH/DEFENSE) — 새 상품 AI 선정 시에만. 동결 상품은 None.
    권고제목(⑤): 키워드 서명이 캐시와 같으면 AI 재호출 없이 재사용(동결 상품 매일 재생성 방지).
    """
    if not track_info:
        return
    title = product.display_title
    pname = pname or product.name
    roles = roles or {}
    for kw, vol, comp, rank in track_info:
        diag = diagnose_exposure(keyword_in_title(kw, title), rank, None)
        role = f" · 역할 {roles[kw]}" if kw in roles else ""
        log(f"  [진단] '{kw}': {diag} · 공략우선순위 {attack_priority(vol, comp_from_idx(comp))}"
            f" · 순위 {rank_label(rank)}{role}")
    kws_by_vol = [kw for kw, _v, _c, _r in sorted(track_info, key=lambda x: x[1], reverse=True)]
    sig = "|".join(sorted(kw for kw, *_ in track_info))   # 키워드 집합 서명(순서 무관)
    rec = ""
    if wb is not None and biz is not None:                 # ⑤ 캐시 재사용(키워드 동일 → 같은 제목)
        csig, ctitle = wb.title_cache(biz, pname)
        if csig == sig and ctitle:
            rec = ctitle
    if not rec:
        try:
            rec = recommend_title(title, kws_by_vol, api_key=ai_key)
        except KeywordAIError as exc:
            log(f"  [제목] 권고제목 생성 실패 — {exc.__class__.__name__}: {str(exc)[:60]}")
            rec = ""
        if rec and wb is not None and biz is not None:
            wb.set_title_cache(biz, pname, sig, rec)
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
        vids0 = [oid for opt in product.options for oid in opt.vendor_item_ids]
        # 상품 정체성 = vendorItemId 앵커. 이미 있는 블록(③이 정확 노출명으로 바꿔뒀을 수 있음)을 vid 로
        # 찾아 그 이름으로 이어간다(발견명이 매일 달라도 중복 블록·시계열 단절 방지). 없으면 발견명 사용.
        pname = wb.resolve_block_name(biz, vids0) or product.name
        if keywords_off:                               # ① 판매수집 단계 — 지표·재고·상품ID만
            wb.ensure_product_block(biz, pname, kind, wb.product_keywords(biz, pname))
            wb.set_product_vids(biz, pname, vids0)
            _fill_product_metrics(wb, biz, product, metrics, inventory, date_iso, pname)
            wb.save(save_path)
            continue
        pmatcher = {"제품": _product_matcher(product)}

        def measure(kws, _m=pmatcher, _cap=None):
            return _measure_safe(browser, kws, _m, log, matched_out=_cap)   # 순위 실패해도 판매데이터 완주

        measure_cb = measure if (browser is not None and not skip_ranks) else None
        cap: dict = {}   # 매칭된 검색결과 항목(정확 노출명) 회수용
        try:   # 한 상품의 키워드 선정 실패(AI 깨진 JSON·네이버 400 등)가 계정 전체를 막지 않게 격리
            existing = wb.product_keywords(biz, pname)
            if existing:                                   # 기존 상품 → 키워드 동결
                keywords = list(existing)
                wb.ensure_product_block(biz, pname, kind, keywords)   # no-op
                if grow and len(existing) < config.KW_MAX_TRACK and browser is not None:
                    want = min(config.KW_ADD_PER_DAY, config.KW_MAX_TRACK - len(existing))
                    found = select_keywords_light(title, naver, ai_key, browser=browser, log=log,
                                                  n=want, measure_ranks=measure, exclude=set(existing))
                    add = [t for t in found if t.keyword not in existing][:want]
                    if add:
                        wb.add_product_keywords(biz, pname, [t.keyword for t in add])
                        for t in add:
                            wb.set_keyword_search(biz, pname, t.keyword, t.volume)
                        keywords += [t.keyword for t in add]
                        log(f"  [키워드] {title} → 동결 {existing} + 발굴 {[t.keyword for t in add]}")
                    else:
                        log(f"  [키워드] {title} → (동결) {keywords}")
                else:
                    log(f"  [키워드] {title} → (동결) {keywords}")
                todo = [kw for kw in keywords if not wb.is_rank_filled(biz, pname, kw, date_iso)]
                measured = measure(todo, _cap=cap) if (browser is not None and todo) else {}
                ranks = {kw: _best(measured.get(kw)) for kw in todo if kw in measured}  # 측정 실패는 공란
                track_info = [(kw, 0, "", ranks.get(kw)) for kw in keywords]   # 동결분은 검색량/경쟁 미측정
                roles = {}                                     # 동결 상품은 역할 재판정 안 함
            else:                                          # 새 상품 → AI 선정(skip_ranks면 순위 없이 부분점수)
                tracks = select_keywords_light(title, naver, ai_key, browser=browser, log=log,
                                               measure_ranks=measure_cb)
                keywords = [t.keyword for t in tracks]
                wb.ensure_product_block(biz, pname, kind, keywords)
                for t in tracks:
                    wb.set_keyword_search(biz, pname, t.keyword, t.volume)
                ranks = {t.keyword: t.exposure_best for t in tracks}          # 선정단계 순위 재사용
                track_info = [(t.keyword, t.volume, t.comp_idx, t.exposure_best) for t in tracks]
                roles = {t.keyword: t.role for t in tracks if t.role}         # ④ 역할(REP/SALES/GROWTH/DEFENSE)
                log(f"  [키워드] {title} → {[f'{t.keyword}({t.role})' if t.role else t.keyword for t in tracks]}")
        except Exception as exc:   # 이 상품만 건너뜀(판매지표·재고는 아래에서 계속 기록). 계정은 완주.
            log(f"  [{biz}] {title} 키워드 처리 실패(건너뜀, 판매지표는 기록) — "
                f"{exc.__class__.__name__}: {str(exc)[:80]}")
            wb.ensure_product_block(biz, pname, kind, wb.product_keywords(biz, pname))
            keywords, ranks, track_info, roles = [], {}, [], {}

        if not skip_ranks:                             # 순위 기록(PC). 날짜지정 수집(skip_ranks)은 순위 제외
            # 차단된 실행이면 미측정(None)을 '50위'로 위장 기록하지 않고 **공란**으로 남긴다 →
            # is_rank_filled=False 유지 → 다음(쉰 IP) 실행이 그 순위만 재측정. (차단 아닌 실 미노출만 RANK_SCAN_MAX 기록)
            blocked = _RANK_HALT["stop"]
            for kw in keywords:                        # 이미 채워진 건 건너뜀
                if kw not in ranks or wb.is_rank_filled(biz, pname, kw, date_iso):
                    continue
                if ranks.get(kw) is None and blocked:  # 차단으로 못 잰 값 → 공란(재측정 대상)
                    continue
                wb.set_keyword_rank(biz, pname, kw, date_iso, ranks.get(kw))
                log(f"  [순위] '{kw}': {rank_label(ranks.get(kw))}")
            mi = cap.get("제품")                        # 매칭된 항목 → 계약상품명을 검색결과 정확 노출명으로
            if mi is not None and getattr(mi, "name", ""):
                if wb.set_display_name(biz, pname, mi.name):
                    log(f"  [노출명] 계약상품명 갱신 → {mi.name}")
                    pname = mi.name.strip()            # 이후 저장도 새 이름으로
        wb.set_product_vids(biz, pname, vids0)          # 상품 고유ID 저장(③ 순위조회 상품 매칭용)
        _fill_product_metrics(wb, biz, product, metrics, inventory, date_iso, pname)
        _log_diagnose(product, track_info, ai_key, log, wb=wb, biz=biz, roles=roles, pname=pname)
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
    _reset_rank_state()          # 이번 실행 순위 차단 플래그·서킷브레이커(cooldown) 초기화
    if not ai_key:
        raise KeywordAIError("OpenAI(ChatGPT) API 키가 없어 키워드 추출을 할 수 없습니다. "
                             "설정 탭에서 OpenAI API 키를 입력한 뒤 다시 실행하세요.")
    # 시작 전 입력 검증 — 경고는 알리고 진행, 치명적 이상은 시작 차단(작업 도중 크래시·데이터 손실 예방)
    fatals, warns = validate_input_list(input_list)
    for w in warns:
        log(f"  [입력검증] ⚠ {w}")
    if fatals:
        for f in fatals:
            log(f"  [입력검증] ✖ {f}")
        raise InputValidationError("입력 파일 검증 실패 — 위 항목을 고친 뒤 다시 시작하세요.")
    log(f"[입력검증] 통과 — 계정 {len(input_list.accounts)}개 · "
        f"상품 {sum(len(a.products) for a in input_list.accounts)}개"
        + (f" · 경고 {len(warns)}건(진행)" if warns else ""))
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

    def _finish(a: Account, report_acc, metrics, inv_by_vid) -> None:
        """발견 결과를 워크북에 기록 + 진행 저장(1·2차 패스 공통). report_acc=None이면 무동작."""
        if report_acc is None:      # 로그인 미완료/데이터 없음 → 다음 계정(전체 안 막힘)
            return
        # 자동완성(키워드 후보)·순위 모두 비로그인 쿠팡 세션이 필요하다. 로그인 브라우저가 닫힌 뒤 별도로
        # 연다(중첩 금지 — sync playwright 충돌 방지). 활동 상품이 있을 때만 열고, 그 한 세션에서
        # 키워드 선정(자동완성)→순위까지 재사용한다(warmup 먼저 = 쿠팡 오리진 로드, same-origin fetch).
        if report_acc.products:
            inventory = _inventory_by_product(report_acc.products, inv_by_vid)
            if skip_ranks or keywords_off:
                # 순위 제외(날짜지정) 또는 판매수집 전용(①): 쿠팡 순위 브라우저 안 열고(차단 접촉 0)
                _process_account(report_acc, wb, naver, ai_key, None, metrics, inventory,
                                 col_label, grow, log, partial, skip_ranks=skip_ranks,
                                 keywords_off=keywords_off)
            else:
                with WingBrowser(profile_dir=_PROFILE, offscreen=True) as rank_browser:
                    warmup(rank_browser)
                    _process_account(report_acc, wb, naver, ai_key, rank_browser, metrics, inventory,
                                     col_label, grow, log, partial)
        else:                                        # 대장 상품 0개 → Chrome 개방 생략, 시트도 생략
            log(f"  [{a.label}] 대장 상품 0개 — 시트·키워드·순위 생략")
        done.add(a.account_id)                    # 이 계정 완료 확정
        _save_progress(out, date_from, date_to, started_at, done, carry, grow, skip_ranks)
        wb.save(partial)
        log(f"  [{a.label}] 완료 — 진행 {len(done)}/{total} (진행 저장: {partial.name})")

    # ── 1차 패스: 세션 살아있는 계정 먼저 수집(로그인 없음 → 차단 위험 0). 세션 만료는 로그인 대기열로. ──
    #   반복 자동로그인이 Akamai IP 차단을 유발하므로, 로그인 없는 계정을 먼저 다 확보한다.
    login_needed: list[tuple[int, Account]] = []
    for i, a in enumerate(accounts, 1):
        if a.account_id in done:                  # 완료 계정 → 건너뜀
            log(f"== [{i}/{total}] {a.label} — 이미 완료, 건너뜀 ==")
            continue
        log(f"== [{i}/{total}] {a.label} (계정ID: {a.account_id}) ==")
        try:   # 한 계정의 어떤 오류(수집·워크북쓰기)도 전체를 막지 않게 계정 전체를 격리
            report_acc, metrics, inv_by_vid = _login_and_discover(
                a, date_from, date_to, get_password, log, login=False)
            _finish(a, report_acc, metrics, inv_by_vid)
        except NeedLogin:                         # 세션 없음 → 뒤로 미룸(자동제출 안 함)
            login_needed.append((i, a))
            log(f"  [{a.label}] 세션 만료 → 로그인 대기열(세션 있는 계정 먼저 수집 후 처리)")
        except Exception as exc:
            first = (str(exc).splitlines() or [""])[0][:250]
            log(f"  [{a.label}] 처리 오류: {exc.__class__.__name__}: {first} — 건너뜀")

    # ── 2차 패스: 로그인 필요 계정 — 서킷브레이커(연속 Akamai 차단 K회면 이후 로그인 생략). ──
    if login_needed:
        log(f"== 로그인 필요 계정 {len(login_needed)}개 처리(세션우선 수집 완료) ==")
    blocks = 0
    attempted = 0
    for i, a in login_needed:
        if blocks >= config.LOGIN_BLOCK_CIRCUIT:  # IP가 이미 플래그됨 → 더 두드리지 않음(더 태우기 방지)
            log(f"== [{i}/{total}] {a.label} — Akamai 차단 지속(연속 {blocks}회)으로 로그인 생략 "
                "→ 잠시 후/내일(쉰 IP) 이어서 수집 ==")
            continue
        if attempted > 0:   # 로그인 사이에 사람 간격(몰아치기=IP 플래그 방지). 첫 로그인엔 대기 없음
            pace = random.uniform(config.LOGIN_PACE_MIN_SEC, config.LOGIN_PACE_MAX_SEC)
            if pace > 0:
                log(f"  [페이싱] 다음 로그인까지 {pace:.0f}s 대기(로그인 몰아치기=차단 회피)")
                time.sleep(pace)
        attempted += 1
        log(f"== [{i}/{total}] {a.label} (계정ID: {a.account_id}) — 로그인 시도 ==")
        try:
            report_acc, metrics, inv_by_vid = _login_and_discover(
                a, date_from, date_to, get_password, log, login=True)
            blocks = 0                            # 로그인 성공 → 연속 차단 카운터 리셋
            _finish(a, report_acc, metrics, inv_by_vid)
        except LoginBlocked:                      # Akamai 차단 → 서킷브레이커 카운트
            blocks += 1
            log(f"  [{a.label}] 로그인 차단 누적 {blocks}/{config.LOGIN_BLOCK_CIRCUIT}")
        except Exception as exc:
            first = (str(exc).splitlines() or [""])[0][:250]
            log(f"  [{a.label}] 처리 오류: {exc.__class__.__name__}: {first} — 건너뜀")

    uncollected = [a for _, a in login_needed if a.account_id not in done]
    if uncollected:
        log(f"== ⚠ 로그인 못한 계정 {len(uncollected)}개(세션만료+Akamai차단): "
            f"{', '.join(a.label for a in uncollected)} — 쉰 IP(내일 등)에 재실행 시 수집됨 ==")

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
                except Exception as exc:   # 한 상품 실패(AI·네이버 400 등)가 나머지 상품·계정 선정을 안 막게 격리
                    log(f"  [{biz}] {pname} 키워드 선정 실패(건너뜀) — {exc.__class__.__name__}: {str(exc)[:80]}")
            wb.save(path)
    wb.apply_style()   # 추가한 키워드 행까지 표준 서식 고정(시트간 서식 섞임 방지)
    wb.save(path)
    log("== 키워드 선정 완료 ==")
    return path


def track_ranks_stage(out_dir: str = "output", on_log=None, semi: bool = False,
                      should_stop=None) -> Path | None:
    """③ 노출순위 조회 전용 — 최신 워크북 로드, 상품(고유ID)+키워드로 순위 측정·기록. 로그인 불필요.

    ①(상품ID)·②(키워드)가 이미 워크북에 있어야 한다. 상품마다 저장된 vendorItemId 로 검색결과에서 내
    상품을 찾아 오가닉 순위를 기록한다(가장 최근 일자 컬럼). 예외 안전 — 차단·browser 죽음도 공란 처리.
    매칭 시 계약상품명을 검색결과의 **정확한 노출명**으로 갱신한다.
    semi=True 면 **반자동** — 앱이 창을 띄우고 키워드를 안내, 사람이 직접 검색하면 그 화면만 읽어 순위 산출
    (자동 네비게이션 없음 → 차단 회피). should_stop() 이 참이면 중도 중단.
    """
    log = on_log or (lambda m: None)
    out = Path(out_dir)
    wb, path = _load_latest_wb(out)
    if wb is None:
        log("== 순위 조회: 결과 워크북이 없습니다 — 먼저 ①②를 실행하세요 ==")
        return None
    if semi:
        return _track_ranks_semi(wb, path, log, should_stop or (lambda: False))
    log(f"== 노출순위 조회 시작 — {path.name} ==")
    _reset_rank_state()          # 이번 실행 차단 플래그·서킷브레이커(cooldown) 초기화
    if config.RANK_NAV_SERIAL:
        log(f"  [모드] 사람속도 직렬 네비게이션(검색 간격 {config.RANK_NAV_DELAY_MIN_SEC}"
            f"~{config.RANK_NAV_DELAY_MAX_SEC}s) — 버스트 없이 차단 회피. 차단 감지 시 즉시 중단(이어서 재개)")
    halted = False
    with WingBrowser(profile_dir=_PROFILE, offscreen=True) as browser:
        warmup(browser)
        for biz in wb.account_sheets():
            if halted:
                break
            date = wb.latest_date(biz)
            if not date:
                continue
            for pname in wb.products_of(biz):
                vids = wb.product_vids(biz, pname)
                keywords = wb.product_keywords(biz, pname)
                if not (vids and keywords):                # 상품ID나 키워드 없으면 건너뜀
                    continue
                # 이미 채워진 키워드는 건너뜀 = **중단 지점부터 이어서**(당일 재작업 시 남은 것만)
                todo = [kw for kw in keywords if not wb.is_rank_filled(biz, pname, kw, date)]
                if not todo:
                    continue
                cap: dict = {}
                try:
                    measured = _measure(browser, todo, _vid_matcher(vids), log, matched_out=cap)
                except RankHalt as h:              # 차단 감지 → 부분결과만 기록하고 전면 중단
                    measured = h.partial
                    halted = True
                except Exception as exc:           # 그 외 예외 → 공란(다음에 재시도)
                    log(f"  [순위] 측정 실패(공란) — {exc.__class__.__name__}: {str(exc)[:80]}")
                    measured = {}
                for kw in todo:
                    if kw not in measured:            # 측정 안 됨(중단·실패) → 공란 유지(다음에 이어서)
                        continue
                    r = _best(measured.get(kw))       # 정상 측정: 미노출이면 '-', 노출이면 'N위'
                    wb.set_keyword_rank(biz, pname, kw, date, r)
                    log(f"  [{biz}] {pname} '{kw}': {rank_label(r)}")
                mi = cap.get("제품")                   # 매칭된 항목 → 계약상품명 정확 노출명 갱신
                if mi is not None and getattr(mi, "name", "") and wb.set_display_name(biz, pname, mi.name):
                    log(f"  [노출명] 계약상품명 갱신 → {mi.name}")
                wb.save(path)   # **상품마다 저장** → 중단돼도 여기까지 보존(재실행 시 이어서)
                if halted:
                    break
    wb.apply_style()   # 저장본 서식 항상 표준으로 고정
    wb.save(path)
    if halted:
        log("== ⛔ 노출순위 중단(쿠팡 검색 차단 감지) — 진행분 저장됨. "
            "쉰 IP/시간에 다시 실행하면 남은 것부터 이어서 조회합니다 ==")
        return path
    log("== 노출순위 조회 완료 ==")
    return path


def _search_q(url: str) -> str | None:
    """검색결과 URL 이면 q(디코드·공백제거) 반환, 아니면 None."""
    from urllib.parse import unquote
    if "/np/search" not in url or "q=" not in url:
        return None
    for part in url.split("?", 1)[-1].split("&"):
        if part.startswith("q="):
            return unquote(part[2:]).replace("+", " ").replace(" ", "")
    return None


# 쿠팡 차단/권한없음 페이지 마커(실측: "요청하신 페이지의 사용권한이 없습니다 … 제한된 페이지").
_BLOCK_PAGE_MARKERS = ("사용권한", "제한된", "Access Denied", "Denied", "죄송")


def _looks_blocked(pg) -> bool:
    """현재 페이지가 쿠팡 차단/권한없음 안내 페이지로 보이는가(사람이 그 창에서 봤을 화면)."""
    try:
        txt = pg.inner_text("body")[:400]
    except Exception:
        try:
            txt = pg.title() or ""
        except Exception:
            return False
    return any(m in txt for m in _BLOCK_PAGE_MARKERS)


def _live_url(pg) -> str:
    """페이지의 **현재 렌더러 실제 URL**(location.href 직접 읽기).

    실측(2026-09-11): connect_over_cdp 장기 연결에서 사용자가 창에서 직접 검색하면 Playwright 가 그
    네비게이션 이벤트를 놓쳐 캐시된 `pg.url` 이 이전(홈) URL 로 **고착**되는 일이 있다(별도 연결로는 최신
    q 가 보이는데 앱은 "입력 대기 중"만 반복). 캐시 대신 렌더러에서 location.href 를 직접 읽어 이를 회피.
    """
    try:
        u = pg.evaluate("() => location.href")
        if u:
            return u
    except Exception:
        pass
    try:
        return pg.url or ""
    except Exception:
        return ""


def _all_pages(browser):
    """연결된 브라우저의 **모든 컨텍스트×모든 탭**(방어적). 단일 컨텍스트라도 전부 순회. 실패 시 browser.page."""
    ctxs = []
    try:
        b = browser.context.browser
        ctxs = list(b.contexts) if b else [browser.context]
    except Exception:
        ctxs = [browser.context] if browser.context else []
    pages = []
    for ctx in ctxs:
        try:
            pages.extend(ctx.pages)
        except Exception:
            continue
    return pages or [browser.page]


def _wait_user_search(browser, kw: str, log, should_stop, timeout: float = 300.0):
    """사용자가 뜬 창에서 kw 를 직접 검색할 때까지 대기(폴링). 감지되면 **그 페이지**를, 타임아웃/중지면 None.

    **여러 탭 전부**를 스캔한다(프로필 복원 탭·사용자가 연 새 탭이 browser.page 와 달라도 인식).
    URL 이 /np/search 이고 q(디코드·공백무시)가 kw 와 같고 상품이 떠 있는 첫 탭을 그 검색으로 인정한다
    (이전/다른 키워드 잔여결과를 잘못 기록하지 않도록 q 일치 요구). 자동 네비게이션은 하지 않는다.

    안내를 **상황별로 정확히** 준다(과거엔 q 가 실제로 맞아도 무조건 "안내 키워드로 검색하세요"라고 떠서
    올바로 검색한 사용자가 '인식 못 함'으로 오해했다 — 실측 재현):
    - q 일치인데 상품 목록이 비면: **차단(권한없음) 페이지**인지, 단순 **로딩 대기**인지 구분해 알린다.
    - q 불일치 검색결과만 있으면: 안내 키워드로 검색하라고 알린다.
    - 검색결과가 아예 없으면: 검색창에 입력하라고 알린다.
    """
    from .rank import extract_items
    want = kw.replace(" ", "")
    deadline = time.time() + timeout
    last = 0.0
    while time.time() < deadline:
        if should_stop():
            return None
        pages = _all_pages(browser)   # 모든 컨텍스트×탭 순회(사용자가 연 새 탭·창도 포함)
        other_qs: list[str] = []      # 안내와 다른 키워드로 열린 검색결과
        matched_empty = False         # 안내 키워드로 검색은 됐으나 상품이 안 잡힘(차단/로딩)
        matched_blocked = False       # 그 중 차단/권한없음 페이지로 보임
        err_reason = ""               # extract 예외 원인(있으면 로그에 노출 — 조용히 삼키지 않음)
        for pg in pages:
            q = _search_q(_live_url(pg))   # 캐시 pg.url 대신 렌더러 실제 location.href(이벤트 놓침 방지)
            if q is None:
                continue
            if q != want:
                other_qs.append(q)
                continue
            try:
                items = extract_items(pg)
            except Exception as exc:
                err_reason = f"{exc.__class__.__name__}: {str(exc)[:60]}"
                items = []
            if items:
                return pg
            matched_empty = True
            if _looks_blocked(pg):
                matched_blocked = True
        if time.time() - last > 15:
            if matched_blocked:
                log(f"    …「{kw}」 검색은 인식됐으나 **쿠팡 차단(사용권한 없음) 페이지**가 떴습니다 — "
                    "그 창을 새로고침(F5)하거나 잠시 후 다시 검색하세요(자동 우회 없음)")
            elif matched_empty:
                extra = f" [{err_reason}]" if err_reason else ""
                log(f"    …「{kw}」 검색은 인식됐으나 상품 목록이 아직 안 보입니다 — "
                    f"페이지가 다 뜰 때까지 잠시 기다리거나 새로고침 해주세요{extra}")
            elif other_qs:
                log(f"    …「{kw}」 대기 — 지금 열린 검색결과: {', '.join(repr(q) for q in other_qs)}"
                    " (안내된 키워드로 그 창에서 검색해야 인식됩니다)")
            else:
                log(f"    …「{kw}」 입력 대기 중 — **뜬 Chrome 창**의 쿠팡 검색창에 입력·검색하세요"
                    " (다른 브라우저 아님, 중지는 '반자동 중지')")
            last = time.time()
        time.sleep(1.0)
    return None


# 반자동 창 식별용 — 우리가 연 창에만 하단 빨간 띠(모든 페이지·검색결과에 계속 표시). 다른 Chrome 창엔 없어
# 여러 창 중 이 창을 한눈에 찾게 한다. Akamai 탐지와 무관(우리 창 UI 표식일 뿐, 지문위조·행동위장 아님).
_SEMI_BANNER_JS = r"""(() => {
  const ID='__semi_marker__';
  function add(){
    if(document.getElementById(ID))return;
    const d=document.createElement('div');
    d.id=ID;
    d.textContent='★ 반자동 순위조회 창 — 이 창에서 검색하세요 ★';
    d.style.cssText='position:fixed;left:0;right:0;bottom:0;z-index:2147483647;'
      +'background:#ff3b30;color:#fff;font:bold 18px sans-serif;text-align:center;'
      +'padding:10px;box-shadow:0 -2px 10px rgba(0,0,0,.4);pointer-events:none';
    (document.body||document.documentElement).appendChild(d);
  }
  add();
  try{new MutationObserver(add).observe(document.documentElement,{childList:true,subtree:true});}catch(e){}
  setInterval(add,1000);
})();"""


def _track_ranks_semi(wb, path, log, should_stop) -> Path:
    """반자동 순위조회 — 앱이 창을 띄우고 키워드를 안내, 사람이 직접 검색한 화면만 읽어 순위 산출·기록.

    우리가 검색(네비게이션)을 하지 않으므로 Akamai 봇차단이 안 생긴다. 상품마다 저장 → 중단해도 이어서.
    """
    from .rank import parse_serp_rank
    log("== 반자동 노출순위 시작 — 뜬 Chrome 창의 쿠팡 검색창에 '안내되는 키워드'를 직접 입력·검색하세요 ==")
    with WingBrowser(profile_dir=_PROFILE, offscreen=False) as browser:
        try:
            browser.page.add_init_script(_SEMI_BANNER_JS)   # 이후 모든 네비/검색결과에 빨간 띠(창 식별)
        except Exception:
            pass
        browser.show()
        try:
            browser.goto("https://www.coupang.com/")   # 검색창 제공(검색은 사람이 직접)
        except Exception:
            pass
        try:
            browser.page.evaluate(_SEMI_BANNER_JS)          # 현재(홈) 페이지에도 즉시 표시
        except Exception:
            pass
        browser.show()   # goto 후 다시 중앙·맨앞으로
        log("  [반자동] ⬆ 창 여러 개 중 **하단에 빨간 띠('반자동 순위조회 창')**가 있는 창에서 검색하세요")
        for biz in wb.account_sheets():
            if should_stop():
                break
            date = wb.latest_date(biz)
            if not date:
                continue
            for pname in wb.products_of(biz):
                if should_stop():
                    break
                vids = wb.product_vids(biz, pname)
                keywords = wb.product_keywords(biz, pname)
                if not (vids and keywords):
                    continue
                todo = [kw for kw in keywords if not wb.is_rank_filled(biz, pname, kw, date)]
                if not todo:
                    continue
                matcher = _vid_matcher(vids)
                for kw in todo:
                    if should_stop():
                        break
                    browser.to_front()   # 키워드마다 창을 앞으로(다른 창에 가려 못 찾는 것 방지)
                    log(f"  🔎 [{biz}] {pname} — (맨 앞 창의) 쿠팡 검색창에 입력·검색: 「{kw}」")
                    pg = _wait_user_search(browser, kw, log, should_stop)
                    if pg is None:
                        log(f"  [반자동] '{kw}' 미감지/중지 — 공란(다음에 이어서)")
                        continue
                    try:
                        # 반자동은 이미 떠 있는 페이지 1장만 읽으므로 트래픽·차단 부담이 없다 →
                        # 50위 상한 없이 로드된 페이지의 오가닉 전부를 세어 **50위를 넘어도 실제 등수 기록**.
                        res = parse_serp_rank(pg, matcher, max_rank=config.RANK_SCAN_MAX_SEMI)
                    except Exception as exc:
                        log(f"  [반자동] '{kw}' 파싱 실패(공란) — {exc.__class__.__name__}: {str(exc)[:80]}")
                        continue
                    rank, mi = res.get("제품", (None, None))
                    wb.set_keyword_rank(biz, pname, kw, date, rank)
                    log(f"  [{biz}] {pname} '{kw}': {rank_label(rank)}")
                    if mi is not None and getattr(mi, "name", "") and wb.set_display_name(biz, pname, mi.name):
                        log(f"  [노출명] 계약상품명 갱신 → {mi.name}")
                        pname = mi.name.strip()   # 이후 저장도 새 이름으로
                    wb.save(path)
    wb.apply_style()
    wb.save(path)
    log("== 반자동 노출순위 종료 — 진행분 저장됨(중단 시 다음 실행이 남은 것부터 이어서) ==")
    return path
