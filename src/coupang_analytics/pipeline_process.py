"""① 판매수집 — 상품/옵션 처리(_process_account·_process_option·키워드 결정·블록 정리).

pipeline_sales(로그인·발견)에서 다시 분리(대형 파일 정비, 행동 불변). run_full._finish 가 _process_account 를
호출하므로 pipeline.py 로 재수출한다. 키워드 선정(select_keywords_light·recommend_title)은 이 모듈에서
resolve 되므로 테스트 monkeypatch 는 pipeline_process 를 교체해야 한다.
의존 방향: … ← pipeline_ranks ← pipeline_sales ← pipeline_process(단방향·순환 없음).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import config
from .kw_ai import KeywordAIError, recommend_title
from .kw_recommend import (attack_priority, comp_from_idx, diagnose_exposure,
                           keyword_in_title, rank_label, select_keywords_light)
from .kw_volume import NaverAdApi
from .rank import make_matcher
from .workbook import OutputWorkbook
from .pipeline_ranks import _RANK_HALT, _best, _measure_safe
from .pipeline_sales import _ilog, _short   # 로그 헬퍼(로그인·발견 모듈과 공유·단방향)


def _fill_frozen_search_volumes(wb, biz: str, product: str, keywords: list[str],
                                naver: NaverAdApi | None, log) -> int:
    """동결 키워드 중 **검색량이 비어 있는 것만** 네이버 검색광고 API로 채운다(AI 불필요, fix ②).

    키워드가 있으면 생성(선정)은 생략(동결)하되, 직원이 결과 시트에 직접 넣어 **검색량 칸이 공란**인
    키워드는 네이버 월검색량으로 채운다(소유자 규칙 2026-09-20). 못 찾은 키워드는 공란 유지(날조 금지).
    """
    if naver is None or not keywords:
        return 0

    def _blank(v) -> bool:
        return v is None or (isinstance(v, str) and not v.strip())

    empties = [kw for kw in keywords if _blank(wb.keyword_search(biz, product, kw))]
    if not empties:
        return 0
    try:
        vols = naver.related_keywords_multi(empties)
    except Exception as exc:   # 네이버 400/429 등이 동결 상품 처리를 막지 않게 격리(공란 유지)
        log(f"  [검색량] {product} 동결 키워드 검색량 조회 실패(공란 유지) — "
            f"{exc.__class__.__name__}: {str(exc)[:80]}")
        return 0
    norm = lambda s: str(s).replace(" ", "").lower()   # 네이버는 힌트 공백 제거·대소문자 무시로 조회
    by = {norm(v.keyword): v.total for v in vols}
    n = 0
    for kw in empties:
        vol = by.get(norm(kw))
        if vol is not None and wb.set_keyword_search(biz, product, kw, vol):
            n += 1
    if n:
        log(f"  [검색량] {product} 동결 키워드 {n}개 검색량 채움(네이버)")
    return n


def _product_matcher(product):
    """상품 단위 매처(옵션 통합) — 새 서식은 상품별 노출순위라 옵션의 vid/pid를 모두 합쳐 하나로 매칭."""
    vids, pids = set(), set()
    for opt in product.options:
        vids |= set(opt.vendor_item_ids)
        pids |= set(opt.product_ids)
    return make_matcher(product_ids=pids, vendor_item_ids=vids,
                        name_substr=None if (vids or pids) else product.name)


def _block_sale_status(sale_status, vids) -> str:
    """이 블록(옵션 vid 목록)의 **쿠팡 판매상태 문자열**을 판정 — 실행일 '판매상태' 지표행 기록용.

    sale_status = {vid: 판매상태 문자열('판매중'/'부분판매중'/'판매중지'/'임시저장'/'승인반려'/'검토중')} 또는
    {vid: isSaleSuspended bool}(RFM 폴백) 둘 다 지원. 블록 vid 중 상태맵에 있는 것만 보고: **모두 같으면
    그 상태·섞이면 부분판매중·하나도 없으면 ''(미상 → 기록 생략, 옛 값 보존)**. workbook.apply_sale_status
    의 블록 판정과 같은 규칙(단일 SSOT 아님 — 여기는 실행일 이력 기록, 거기는 최신 상태 저장)."""
    if not sale_status:
        return ""

    def _one(st) -> str:
        if isinstance(st, bool):
            return "판매중지" if st else "판매중"
        return str(st or "").strip()

    known = [s for s in (_one(sale_status[v]) for v in vids if v in sale_status) if s]
    if not known:
        return ""
    uniq = set(known)
    return next(iter(uniq)) if len(uniq) == 1 else "부분판매중"


def _fill_product_metrics(wb, biz, pname, vids, kind, metrics, inv_by_vid, date_iso,
                          log=None, sale_status=None) -> None:
    """**옵션(블록) 단위** 판매지표·재고·판매상태 기록 + **vid 기준 데이터 로그**(진행 추적).

    vids = 이 블록에 속한 옵션ID 목록(단일옵션·판매자배송=상품 전 옵션, 다중옵션=그 옵션 하나). 지표는
    vi-detail-search(metrics: vid→OptionMetric)에서, 재고는 RFM 재고 API(inv_by_vid: vid→수량)에서 vid 로
    조인해 이 블록 vid 들만 합산한다. 재고행은 kind 가 로켓그로스/둘다일 때만.
    **재고 규칙(소유자 2026-09-24 개정)**: 재고현황 API에 vid 있으면 수량(0=입고됐지만 품절) · **없으면
    판매중지 여부와 무관하게 '미입고'**(실입고 안 됨). 값 출처=재고현황 API만(상품조회 stockQuantity 금지).
    **판매상태(소유자 2026-09-24)**: 쿠팡 productStatus(sale_status)를 실행일 '판매상태' 지표행에 항상 기록
    (재고칸이 아니라 별도 지표행 — 쿠팡 상태 그대로 존중, 판매중지도 재고칸엔 미입고/값)."""
    views = sales = visitors = 0
    for oid in vids:
        m = metrics.get(oid)
        if m:
            views += m.views
            sales += m.sales
            visitors += m.visitors
    wb.set_product_metric(biz, pname, config.M_SALES, date_iso, sales)
    wb.set_product_metric(biz, pname, config.M_VISITORS, date_iso, visitors)
    wb.set_product_metric(biz, pname, config.M_VIEWS, date_iso, views)
    inv_txt = ""
    if kind in config.KINDS_WITH_INVENTORY:   # 재고현황 = 로켓그로스 + 둘다(로켓그로스 파트 있음)
        matched = [oid for oid in vids if inv_by_vid and oid in inv_by_vid]
        if matched:
            qty = sum(inv_by_vid[oid] for oid in matched)
            wb.set_product_metric(biz, pname, config.M_INVENTORY, date_iso, qty)   # 0=입고됐지만 품절
            inv_txt = f"·재고 {qty}"
        else:
            # 재고현황에 없음 = 로켓그로스 등록됐으나 물류센터 **미입고**(판매중지 여부 무관 · 재고 0=품절과 구분)
            wb.set_product_metric(biz, pname, config.M_INVENTORY, date_iso, config.INV_NOT_INBOUND)
            inv_txt = "·재고 미입고"
    status = _block_sale_status(sale_status, vids)   # 실행일 판매상태(쿠팡 존중·미상은 생략)
    if status:
        wb.set_product_metric(biz, pname, config.M_SALE_STATUS, date_iso, status)
    no_metric = [v for v in vids if v not in metrics]   # 당일 지표가 없는 vid(판매 0·미노출 등)
    _ilog(log, "지표", vids, pname,
          f"노출 {views}·판매 {sales}·방문 {visitors}{inv_txt}"
          + (f"·상태 {status}" if status else "")
          + (f" ⚠지표없는vid {no_metric}" if no_metric else ""), kind=kind)


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


def _block_name(base: str, label: str) -> str:
    """블록 이름 = 등록상품명 + 옵션라벨(있을 때). 단일옵션·판매자배송(label='')은 등록상품명 그대로.

    다중옵션 상품을 옵션(vid)별 블록으로 분리할 때 각 블록의 이름을 만든다(소유자 확정: 쿠팡 등록상품명 +
    옵션라벨). 등록상품명은 안정 키(노출 SERP명 아님)라 cross-day 시계열이 안 끊긴다."""
    label = (label or "").strip()
    return f"{base} ({label})" if label else base


@dataclass
class _ProcCtx:
    """_process_account 한 계정 처리의 공유 인자(상품·옵션 루프가 이 컨텍스트로 동작)."""
    wb: OutputWorkbook
    naver: NaverAdApi
    ai_key: str | None
    browser: object
    metrics: object
    inv_by_vid: object
    date_iso: str
    grow: bool
    skip_ranks: bool
    keywords_off: bool
    log: object
    save_path: object
    sale_status: object = None   # {vid: 판매상태(문자열) 또는 isSaleSuspended(bool)} — 미입고/판매중지 구분용
    vid_meta: object = None       # {vid: (판매가, 판매시작일)} — 헤더 표시(상품판매가·로켓그로스 입고일 근사)
    pid_by_vid: object = None     # {vid: 노출상품ID(productId)} — 상품명 하이퍼링크(항목2·판매분석∪재고)


def _frozen_keywords(pctx: _ProcCtx, biz: str, pname: str, base: str, kind: str, title: str,
                     opt_vids, existing, measure, cap: dict):
    """기존 상품의 키워드 동결 경로 — 시트 키워드 그대로(grow=True면 상한 내 발굴 추가), 미기입 순위만 측정.

    반환: (keywords, ranks{키워드:순위}, track_info). 동결분은 검색량/경쟁 미측정(track_info 값 0/'').
    """
    wb, log = pctx.wb, pctx.log
    naver, ai_key, browser, grow, date_iso = pctx.naver, pctx.ai_key, pctx.browser, pctx.grow, pctx.date_iso
    keywords = list(existing)
    wb.ensure_product_block(biz, pname, kind, keywords, registered=base)   # no-op
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
            _ilog(log, "키워드", opt_vids, title, f"→ 동결 {existing} + 발굴 {[t.keyword for t in add]}")
        else:
            _ilog(log, "키워드", opt_vids, title, f"→ (동결) {keywords}")
    else:
        _ilog(log, "키워드", opt_vids, title, f"→ (동결) {keywords}")
    _fill_frozen_search_volumes(wb, biz, pname, keywords, naver, log)  # 검색량 공란만 네이버로(fix ②)
    todo = [kw for kw in keywords if not wb.is_rank_filled(biz, pname, kw, date_iso)]
    measured = measure(todo, _cap=cap) if (browser is not None and todo) else {}
    ranks = {kw: _best(measured.get(kw)) for kw in todo if kw in measured}  # 측정 실패는 공란
    track_info = [(kw, 0, "", ranks.get(kw)) for kw in keywords]   # 동결분은 검색량/경쟁 미측정
    return keywords, ranks, track_info


def _resolve_keywords(pctx: _ProcCtx, biz: str, pname: str, base: str, kind: str, title: str,
                      opt_vids, measure, measure_cb, cap: dict):
    """대표 옵션의 키워드 확정 — 기존=동결(grow면 상한 내 발굴 추가), 새 상품=AI 선정.

    반환: (keywords, ranks{키워드:순위}, track_info[(kw,vol,comp,rank)], roles{키워드:역할}).
    선정 실패(AI 깨진 JSON·네이버 400 등)는 이 상품만 건너뛰고 빈 결과 반환(판매지표는 호출부가 계속 기록).
    """
    wb, log = pctx.wb, pctx.log
    naver, ai_key, browser, grow, date_iso = pctx.naver, pctx.ai_key, pctx.browser, pctx.grow, pctx.date_iso
    try:   # 한 상품의 키워드 선정 실패가 계정 전체를 막지 않게 격리
        existing = wb.product_keywords(biz, pname)
        if existing:                                   # 기존 상품 → 동결(역할 재판정 안 함)
            kws, ranks, track_info = _frozen_keywords(pctx, biz, pname, base, kind, title,
                                                      opt_vids, existing, measure, cap)
            return kws, ranks, track_info, {}
        # 새 상품 → AI 선정(skip_ranks면 순위 없이 부분점수)
        tracks = select_keywords_light(title, naver, ai_key, browser=browser, log=log,
                                       measure_ranks=measure_cb)
        keywords = [t.keyword for t in tracks]
        wb.ensure_product_block(biz, pname, kind, keywords, registered=base)
        for t in tracks:
            wb.set_keyword_search(biz, pname, t.keyword, t.volume)
        ranks = {t.keyword: t.exposure_best for t in tracks}          # 선정단계 순위 재사용
        track_info = [(t.keyword, t.volume, t.comp_idx, t.exposure_best) for t in tracks]
        roles = {t.keyword: t.role for t in tracks if t.role}         # ④ 역할(REP/SALES/GROWTH/DEFENSE)
        _ilog(log, "키워드", opt_vids, title,
              f"→ {[f'{t.keyword}({t.role})' if t.role else t.keyword for t in tracks]}")
        return keywords, ranks, track_info, roles
    except Exception as exc:   # 이 상품만 건너뜀(판매지표·재고는 호출부가 계속 기록). 계정은 완주.
        _ilog(log, "오류", opt_vids, title,
              f"키워드 처리 실패(건너뜀, 판매지표는 기록) — {exc.__class__.__name__}: {str(exc)[:80]}")
        wb.ensure_product_block(biz, pname, kind, wb.product_keywords(biz, pname), registered=base)
        return [], {}, [], {}


def _apply_vid_meta(wb, biz: str, pname: str, kind: str, opt_vids, vid_meta, date_iso,
                    inbound_summary: str = "") -> None:
    """이 옵션(블록)의 판매가·로켓그로스 판매일·최근입고를 기록(소유자 2026-09-24).

    **판매가**=이 블록 옵션(첫 vid) salePrice → **'판매가' 지표행(재고현황 아래)에 일자별** 기록(마케팅 일환
    변동 추적). **로켓그로스 판매일**(판매시작일 근사)+**최근입고 요약**(관리대장)=로켓그로스/둘다만 → 헤더에
    묶어 표시(판매자배송은 로켓그로스 개념 없어 생략). vid_meta 비어도 최근입고(대장)는 반영."""
    price = None
    started = ""
    if vid_meta:
        for v in opt_vids:
            if v in vid_meta:
                price, started = vid_meta[v]
                break
    if isinstance(price, (int, float)) and price > 0:
        wb.set_product_metric(biz, pname, config.M_SALE_PRICE, date_iso, price)   # 판매가 지표행(일자별)
    wb.set_product_kind(biz, pname, kind)   # 판매방식(메타 col11) — 레이아웃 v4 헤더 '판매방식' 줄 표시용
    is_rg = kind in config.KINDS_WITH_INVENTORY
    inbound = started if is_rg else None
    summ = inbound_summary if (is_rg and inbound_summary) else None
    if inbound or summ:
        wb.set_product_extra(biz, pname, inbound_date=inbound, inbound_summary=summ)   # 헤더 로켓그로스 묶음


def _apply_pid(wb, biz: str, pname: str, opt_vids, pid_by_vid) -> None:
    """이 블록의 옵션 vid 중 하나로 노출상품ID(productId)를 찾아 저장(항목2 상품명 하이퍼링크).

    productId 는 상품(노출페이지) 단위라 같은 상품의 옵션 vid 는 같은 값을 공유 → 첫 매칭 vid 로 충분.
    소스=판매분석∪재고(상품조회엔 공개 productId 없음). 없으면 no-op(검색 링크 폴백 유지)."""
    if not pid_by_vid:
        return
    pid = next((pid_by_vid[v] for v in opt_vids if v in pid_by_vid), "")
    if pid:
        wb.set_product_pid(biz, pname, pid)


def _process_option(pctx: _ProcCtx, biz: str, product, base: str, kind: str, title: str,
                    i: int, opt, multi: bool) -> None:
    """상품의 옵션(vid) 한 개를 기록. 대표(i==0)=키워드/순위/지표, 2차 옵션=판매정보(지표·재고)만.

    keywords_off(①판매수집)면 대표도 지표·재고·vid만(키워드는 ②, 순위는 ③). 상품마다 저장(중단 복구).
    """
    wb, log = pctx.wb, pctx.log
    is_rep = (i == 0)
    pname = _block_name(base, opt.label if multi else "")
    opt_vids = list(opt.vendor_item_ids)
    if pctx.keywords_off or not is_rep:
        # ① 판매수집 단계, 또는 다중옵션 2차 블록 → 지표·재고·vid만(키워드/순위 없음, rank_rows=is_rep)
        wb.ensure_product_block(biz, pname, kind, wb.product_keywords(biz, pname),
                                rank_rows=is_rep, registered=base)
        wb.set_product_vids(biz, pname, opt_vids)
        _apply_pid(wb, biz, pname, opt_vids, pctx.pid_by_vid)   # 노출상품ID(항목2 하이퍼링크·판매분석∪재고)
        _apply_vid_meta(wb, biz, pname, kind, opt_vids, pctx.vid_meta, pctx.date_iso, product.inbound_summary)   # 판매가 지표행·판매일/최근입고 헤더
        _fill_product_metrics(wb, biz, pname, opt_vids, kind, pctx.metrics, pctx.inv_by_vid,
                              pctx.date_iso, log=log, sale_status=pctx.sale_status)
        wb.save(pctx.save_path)
        return
    # ── 대표 옵션(단일옵션 포함): 키워드 동결/선정 → 순위 → 지표 → 진단 ──
    naver, ai_key, browser, grow = pctx.naver, pctx.ai_key, pctx.browser, pctx.grow
    skip_ranks, date_iso = pctx.skip_ranks, pctx.date_iso
    pmatcher = {"제품": _product_matcher(product)}   # 순위 매칭 = 리스팅 전 옵션 vid(아이템위너 놓침 방지)

    def measure(kws, _m=pmatcher, _cap=None):
        return _measure_safe(browser, kws, _m, log, matched_out=_cap)   # 순위 실패해도 판매데이터 완주

    measure_cb = measure if (browser is not None and not skip_ranks) else None
    cap: dict = {}   # 매칭된 검색결과 항목(노출명) 회수용
    keywords, ranks, track_info, roles = _resolve_keywords(
        pctx, biz, pname, base, kind, title, opt_vids, measure, measure_cb, cap)

    if not skip_ranks:                             # 순위 기록(PC). 날짜지정 수집(skip_ranks)은 순위 제외
        # 차단된 실행이면 미측정(None)을 '50위'로 위장 기록하지 않고 **공란**으로 남긴다 →
        # is_rank_filled=False 유지 → 다음(쉰 IP) 실행이 그 순위만 재측정.
        blocked = _RANK_HALT["stop"]
        for kw in keywords:                        # 이미 채워진 건 건너뜀
            if kw not in ranks or wb.is_rank_filled(biz, pname, kw, date_iso):
                continue
            if ranks.get(kw) is None and blocked:  # 차단으로 못 잰 값 → 공란(재측정 대상)
                continue
            wb.set_keyword_rank(biz, pname, kw, date_iso, ranks.get(kw))
            _ilog(log, "순위", opt_vids, "", f"'{kw}': {rank_label(ranks.get(kw))}")
        # ⚠ set_display_name(노출명 교체) 중단 — 블록 이름을 등록상품명+옵션라벨로 고정(옵션 정체성 안정).
        mi = cap.get("제품")                        # 노출명은 로그로만(블록명은 등록상품명 유지)
        if mi is not None and getattr(mi, "name", ""):
            _ilog(log, "노출명", opt_vids, "", f"검색결과 노출명 = {_short(mi.name, 40)} (블록명은 등록상품명 고정)")
            wb.set_product_pid(biz, pname, getattr(mi, "product_id", ""))   # 항목3: 상품명 하이퍼링크용 productId
    wb.set_product_vids(biz, pname, opt_vids)          # 대표 옵션 vid 저장(③은 sibling_vids 합집합으로 매칭)
    _apply_pid(wb, biz, pname, opt_vids, pctx.pid_by_vid)   # 노출상품ID(항목2·판매분석∪재고·순위매칭 pid보다 완전)
    _apply_vid_meta(wb, biz, pname, kind, opt_vids, pctx.vid_meta, pctx.date_iso, product.inbound_summary)   # 판매가 지표행·판매일/최근입고 헤더
    _fill_product_metrics(wb, biz, pname, opt_vids, kind, pctx.metrics, pctx.inv_by_vid, date_iso,
                          log=log, sale_status=pctx.sale_status)
    _log_diagnose(product, track_info, ai_key, log, wb=wb, biz=biz, roles=roles, pname=pname)
    wb.save(pctx.save_path)


def _migrate_product_blocks(wb, biz: str, base: str, rep_name: str, vids_all, opts, multi: bool,
                            log) -> None:
    """정체성/마이그레이션(소유자 2026-09-20: vid=상품당 1개).

    ① **같은 vid** = 같은 상품 → 기존 블록 승계 + 이름을 등록상품명으로 정규화(set_display_name 은
       중단됐으니 이 한 번만). ② **등록상품명은 같은데 vid 가 다른**(교집합 없는) 옛 블록 = 정체성 바뀜
       → **이전 데이터 삭제하고 새로 시작**(잘못된 이력 승계 방지). vid 없는 복원 잔재 블록도 대체 삭제한다
       (단 이번에 이어쓸 블록·미매칭 상품은 보존).
    """
    vidset = set(vids_all)
    old = wb.resolve_block_name(biz, vids_all)   # 새 vid 와 교집합 있는 기존 블록(같은 vid)
    if old and old != rep_name and not wb.has_product(biz, rep_name):
        if wb.set_display_name(biz, old, rep_name):
            log(f"  [정체성] 기존 블록 '{old}' → '{rep_name}'(같은 vid·과거 이력 승계·이름 정규화)")
    new_names = {_block_name(base, o.label if multi else "") for o in opts}   # 이번에 쓸(이어쓸) 블록
    for stale in wb.blocks_with_registered_name(biz, base):
        stored = set(wb.product_vids(biz, stale))
        # ① vid 가 바뀐 옛 블록(교집합 없음) = 정체성 변경 → 삭제·새로 시작(단일옵션 동일이름도 삭제 후 재생성).
        changed_vid = bool(vidset and stored and not (vidset & stored))
        # ② 구글시트 복원 잔재: 옛 블록에 vid 가 **없는데** 이번에 vid 있는 옵션 블록을 새로 만든다 = pre-vid 잔재
        #    → 삭제. 단 **이번에 이어쓸 블록(new_names)** 과 **미매칭 상품(vidset 비었음)** 은 보존.
        legacy_novid = bool(vidset and not stored and stale not in new_names)
        if changed_vid or legacy_novid:
            if wb.delete_product_block(biz, stale):
                why = (f"vid 변경(이전 {sorted(stored)} → {vids_all})" if changed_vid
                       else f"vid 없는 옛 블록 잔재(복원분) → 옵션 블록 {vids_all} 로 대체")
                log(f"  [정체성] '{stale}' {why} → 이전 데이터 삭제·새로 시작")


def _purge_upbundle_blocks(wb, biz: str, upbundle_vids, log) -> None:
    """이번 상품조회의 **업번들(자동번들) vid** 집합으로 마스터의 옛 업번들 잔재 블록을 삭제(소유자 2026-09-24).

    업번들 옵션은 수집 단계에서 이미 추적 제외되지만(products_from_vendor_inventory), 리스팅 전체가 업번들이면
    그 상품이 추적에서 통째 빠져 마스터 블록이 **고아**로 남아 reconcile 이 '판매중지'로 표기하는 clutter 가
    생긴다. 그 잔재를 매 수집마다 정리한다. **vid 기준**(이름패턴 '(N개)' 아님 — 색상/사이즈 변형 오삭제 방지):
    블록의 vid 가 **전부** 업번들 vid 면 삭제. vid 없는 블록·일반 옵션 블록(실vid)은 보존. 상품조회 실패로
    upbundle_vids 가 비면 no-op(잘못된 삭제 방지)."""
    if not upbundle_vids or biz not in wb.wb.sheetnames:
        return
    for p in list(wb.products_of(biz)):
        vids = wb.product_vids(biz, p)
        if vids and all(v in upbundle_vids for v in vids):
            if wb.delete_product_block(biz, p):
                log(f"  [정체성] '{p}' 업번들(자동번들) 잔재 블록 삭제(vid {vids} 전부 업번들·원상품 재고공유)")


def _sweep_dead_duplicates(wb, biz: str, live_vids, log) -> None:
    """**죽은 중복 블록**만 정리 — 안전 규칙(소유자 2026-09-24). 두 조건을 **모두** 만족할 때만 삭제:

    (a) **같은 상품군(블록명 접두=옵션라벨 앞부분)에 live 형제 존재**(vid 가 이번 상품조회에 있는 블록) AND
    (b) 그 블록 vid 가 **전부 이번 상품조회(live_vids)에 없음**(코팡서 사라진 죽은 등록).

    → 재등록으로 죽은 옛 vid 유령(R601_/__/…)만 제거하고, **판매중지 단독 상품·색상/사이즈 변형·코팡에
    남아있는 vid(판매자배송 twin 포함)·신규는 전부 보존**(reconcile 이 판매중지 표기). 상품조회 실패로 live_vids
    비면 no-op(오삭제 방지). **그룹 키=마스터 블록명 접두**(등록상품명/발견명 드리프트에 무관 — vid 앵커로 live 판정).
    같은 상품군에 live 형제가 없으면(그룹 전체가 코팡서 소멸=판매중지 단독) 통째 보존."""
    if not live_vids:
        return
    groups: dict = {}   # 블록명 접두 → [블록명…] (색상/사이즈/재등록 형제가 한 군)
    for p in wb.products_of(biz):
        prefix = p.rsplit(" (", 1)[0] if " (" in p else p
        groups.setdefault(prefix, []).append(p)
    for prefix, blocks in groups.items():
        if len(blocks) < 2:
            continue   # 형제 없는 단독 블록(판매중지 단독 포함) → 보존
        has_live = any(any(v in live_vids for v in wb.product_vids(biz, b)) for b in blocks)
        if not has_live:
            continue   # 그룹 전체가 코팡서 소멸 → 판매중지 단독군 → 통째 보존
        for b in blocks:
            vids = wb.product_vids(biz, b)
            # 🔒 정책(소유자 2026-09-24): **판매자배송(NORMAL) twin 은 삭제하지 않고 보존**한다.
            # 같은 상품을 로켓그로스+판매자배송 둘 다 등록하면 vid 가 2개(RFM/NORMAL) 생기고, 추적은 RFM 만
            # 하지만 NORMAL twin 도 **코팡 상품조회에 살아있는 vid** 라 아래 'vid 전부 소멸' 조건에 안 걸린다
            # → 판매중지 표기로 남겨 보존(데이터 유실 방지). 완전 제거는 registrationType 배선이 필요한 별도 후속.
            if vids and all(v not in live_vids for v in vids):   # 코팡서 완전 소멸한 vid만(=죽은 재등록)
                if wb.delete_product_block(biz, b):
                    log(f"  [정체성] '{b}' 죽은 중복 블록 삭제(vid {vids} 상품조회에 없음·live 형제 존재)")


def _process_account(report_acc, wb, naver, ai_key, browser, metrics, inv_by_vid,
                     date_iso, grow, log, save_path, skip_ranks: bool = False,
                     keywords_off: bool = False, sale_status=None, upbundle_vids=None,
                     live_vids=None, vid_meta=None, pid_by_vid=None) -> None:
    """계정(시트) 하나: 상품마다 **옵션 블록**을 만들고 [대표=키워드/순위/지표, 2차=지표만] 기록·저장.

    다중옵션 상품은 옵션(vid)별 블록으로 분리한다 — **대표(첫 옵션)** 만 키워드 동결/선정·순위(리스팅 단위)를
    담고, 나머지 옵션 블록은 판매정보(지표·재고)만(순위행 없음). 단일옵션은 대표 하나(기존과 동일).
    - 기존 상품(대표 블록에 키워드 있음): **키워드 동결**, 순위만 조회(grow=True면 상한 내 발굴 추가).
    - 새 상품: AI 선정 + 선정단계 순위 재사용. 순위 매칭은 리스팅 전 옵션 vid(놓침 방지).
    - skip_ranks=True(날짜 지정 수집): 쿠팡 순위 조회를 제외(browser=None). 판매지표·재고만.
    - keywords_off=True(① 판매수집 단계): 모든 옵션 블록에 지표·재고·vid만(키워드는 ②, 순위는 ③).
    - upbundle_vids: 이번 상품조회의 업번들 vid 집합 → 마스터 잔재 업번들 블록 자동삭제(reconcile 전).
    - live_vids: 이번 상품조회 전체 vid 집합 → **죽은 중복 블록** 정리(같은 등록상품명 live 형제 있고 vid 소멸한
      것만·판매중지 단독/변형/신규 보존, reconcile 전). 상품조회 실패면 빈 집합(정리 skip).
    상품마다 save_path 저장 → 도중 끊겨도 이어감.
    """
    from .input_list import Option
    biz = report_acc.label   # 시트명 = 사업자명, 없으면 대표자명·계정ID(빈 시트명 KeyError 방지)
    wb.ensure_account(biz)
    _purge_upbundle_blocks(wb, biz, upbundle_vids, log)   # 옛 업번들 잔재 정리(reconcile 판매중지 표기 전)
    seen_products: list[str] = []          # 이번 대장에 존재한 옵션 블록명 — 대조로 판매중지 감지
    for product in report_acc.products:
        title = product.display_title
        kind = product.kind or config.KIND_PERSONAL
        opts = list(product.options) or [Option("")]
        multi = len(opts) > 1                           # 옵션 라벨은 **다중옵션에만** 붙인다(단일옵션=등록상품명 그대로)
        base = product.name                            # 등록상품명(vendor-inventory) = 블록 기준명
        vids_all = [oid for o in opts for oid in o.vendor_item_ids]
        rep_name = _block_name(base, opts[0].label if multi else "")
        _migrate_product_blocks(wb, biz, base, rep_name, vids_all, opts, multi, log)
        # 수집 주기·마케팅은 상품(대표) 단위. 오늘 대상 아니면 이 상품의 모든 옵션 블록을 오늘치 생략.
        if product.mkt_start or product.mkt_end or product.mkt_mon:   # 대장에 마케팅 값 있을 때만 반영
            wb.set_marketing(biz, rep_name, product.mkt_start, product.mkt_end, product.mkt_mon)
        if wb.has_marketing():
            _due, _why = wb.product_due(biz, rep_name, date_iso)
            if not _due:
                log(f"  [{title}] {_why} — 오늘 수집 생략(상품 주기)")
                for o in opts:
                    seen_products.append(_block_name(base, o.label if multi else ""))   # 있음(오늘 스킵돼도 '있음')
                continue
        # ── 옵션 블록 루프: 대표(i==0)만 키워드/순위, 나머지는 판매정보만 ──
        pctx = _ProcCtx(wb=wb, naver=naver, ai_key=ai_key, browser=browser, metrics=metrics,
                        inv_by_vid=inv_by_vid, date_iso=date_iso, grow=grow, skip_ranks=skip_ranks,
                        keywords_off=keywords_off, log=log, save_path=save_path, sale_status=sale_status,
                        vid_meta=vid_meta, pid_by_vid=pid_by_vid)
        for i, opt in enumerate(opts):
            bname = _block_name(base, opt.label if multi else "")
            seen_products.append(bname)
            _process_option(pctx, biz, product, base, kind, title, i, opt, multi)
            wb.set_product_account_id(biz, bname, report_acc.account_id)   # 항목5: 상품별 계정ID 태깅(다계정ID 사업자)
    # 죽은 중복 블록 정리(안전 규칙): live 형제 있고 vid 가 상품조회서 소멸한 잔재만 삭제(reconcile 판매중지 표기 전)
    _sweep_dead_duplicates(wb, biz, live_vids, log)
    # 대장 대조(항목⑥, 소유자 2026-09-25): **줄이 완전히 사라진 상품 = 이력 포함 완전삭제**(백업 안전망),
    # 대장에 **판매중지/취소선으로 남은(줄 존재)** 상품 = 판매중지 표기 유지. ledger_products=줄 존재 전체.
    newly, deleted = wb.reconcile_account(biz, seen_products, report_acc.ledger_products,
                                          delete_missing=True, account_id=report_acc.account_id)   # 항목5: 계정ID 스코핑
    if deleted:
        log(f"  [SYNC] [{biz}] 관리대장에서 줄이 사라진 상품 {len(deleted)}개 → 완전삭제(이력 포함·백업 보존): "
            f"{deleted[:3]}{'…' if len(deleted) > 3 else ''}")
    if newly:
        log(f"  [{biz}] 대장에 판매중지로 남은 상품 {len(newly)}개 → 판매중지 표기(유지): "
            f"{newly[:3]}{'…' if len(newly) > 3 else ''}")
    wb.save(save_path)
