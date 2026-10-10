"""① 판매수집 — 상품/옵션 처리(_process_account·_process_option·블록 정리) + ② 동결 키워드 검색량 채우기.

pipeline_sales(로그인·발견)에서 다시 분리(대형 파일 정비, 행동 불변). run_full._finish 가 _process_account 를
호출하므로 pipeline.py 로 재수출한다. 키워드 선정·순위는 이 모듈에 없다(②=pipeline.select_keywords_stage·
③=pipeline_ranks.track_ranks_stage — 인라인 경로는 D-022 B5 에서 삭제).
의존 방향: … ← pipeline_sales ← pipeline_process(단방향·순환 없음).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import config
from .kw_volume import NaverAdApi
from .workbook import OutputWorkbook
from .pipeline_sales import _ilog   # 로그 헬퍼(로그인·발견 모듈과 공유·단방향)


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

    vids = 이 블록에 속한 옵션ID 목록. 판매량·방문자·노출량은 vi-detail-search(metrics: vid→OptionMetric) **조회값
    그대로**(합산 안 함·D-031), 재고는 RFM 재고 API(inv_by_vid: vid→수량)를 이 블록 vid 로 조인. 재고행은 kind 가
    로켓그로스/둘다일 때만.
    **재고 규칙(소유자 2026-09-24 개정)**: 재고현황 API에 vid 있으면 수량(0=입고됐지만 품절) · **없으면
    판매중지 여부와 무관하게 '미입고'**(실입고 안 됨). 값 출처=재고현황 API만(상품조회 stockQuantity 금지).
    **판매상태(소유자 2026-09-24)**: 쿠팡 productStatus(sale_status)를 실행일 '판매상태' 지표행에 항상 기록
    (재고칸이 아니라 별도 지표행 — 쿠팡 상태 그대로 존중, 판매중지도 재고칸엔 미입고/값)."""
    # 조회값 그대로(D-031 — 합치지 않음): 블록 VID 중 판매분석에 잡힌 **첫 VID** 의 값. 지금은 블록당 VID 가 1개라
    # 대부분 그 값 그대로이고, 옛 블록처럼 VID 가 여러 개여도 더하지 않는다.
    m = next((metrics[oid] for oid in vids if oid in metrics), None)
    views, sales, visitors = (m.views, m.sales, m.visitors) if m else (0, 0, 0)
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
    metrics: object
    inv_by_vid: object
    date_iso: str
    log: object
    save_path: object
    sale_status: object = None   # {vid: 판매상태(문자열) 또는 isSaleSuspended(bool)} — 미입고/판매중지 구분용
    vid_meta: object = None       # {vid: (판매가, 판매시작일)} — 헤더 표시(상품판매가·로켓그로스 입고일 근사)
    pid_by_vid: object = None     # {vid: 노출상품ID(productId)} — 상품명 하이퍼링크(항목2·판매분석∪재고)


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


def _process_option(pctx: _ProcCtx, biz: str, product, base: str, kind: str, i: int, opt, pname: str) -> None:
    """상품의 옵션(vid) 한 개 = 블록 하나에 ① 판매정보(지표·재고·판매가·판매상태·vid)만 기록·저장(중단 복구).

    키워드는 ②(select_keywords_stage), 순위는 ③(track_ranks_stage)에서. 대표(i==0)만 키워드·순위 행 자리를 둔다
    (rank_rows=is_rep — 다중옵션 2차 블록은 판매정보만)."""
    wb, log = pctx.wb, pctx.log
    is_rep = (i == 0)
    opt_vids = list(opt.vendor_item_ids)
    wb.ensure_product_block(biz, pname, kind, wb.product_keywords(biz, pname),
                            rank_rows=is_rep, registered=base)
    if is_rep and wb.ensure_keyword_section(biz, pname):   # 예전 2차 블록이 대표가 됨 → 키워드·순위 칸 생성
        log(f"  [키워드칸] '{pname}' 대표 블록에 키워드 칸이 없어 추가(옵션 구성 변경) — ②에서 키워드 채움")
    wb.set_product_vids(biz, pname, opt_vids)      # 대표 옵션 vid 저장(③은 sibling_vids 합집합으로 매칭)
    _apply_pid(wb, biz, pname, opt_vids, pctx.pid_by_vid)   # 노출상품ID(항목2 하이퍼링크·판매분석∪재고)
    _apply_vid_meta(wb, biz, pname, kind, opt_vids, pctx.vid_meta, pctx.date_iso, product.inbound_summary)   # 판매가 지표행·판매일/최근입고 헤더
    _fill_product_metrics(wb, biz, pname, opt_vids, kind, pctx.metrics, pctx.inv_by_vid,
                          pctx.date_iso, log=log, sale_status=pctx.sale_status)
    wb.save(pctx.save_path)

def _block_names(wb, biz: str, product, base: str, opts, multi: bool, log) -> list[str]:
    """옵션별 블록 이름 = **쿠팡 노출상품명**(판매분석 productName·현행) + 옵션라벨(다중옵션만) — 상품명 현행화(D-013).

    소유자 2026-10-09: 검색 노출을 위해 상품명을 바꿔도 VID 는 같다 → 같은 VID 의 기존 블록을 새 이름으로 바꿔
    **이력 승계**(set_display_name). ①에서 노출명을 못 찾으면(30일 판매분석에도 없음) **오류로 기록**(_fill_exposed_names)하고
    여기선 임시로 기존 이름(등록상품명이 바뀌었으면 새 등록상품명·처음이면 등록상품명)을 두며, 그날 ③순위 검색 노출명으로
    현행화한다(product_naming.rename_to_exposed). 다른 상품 블록이 이미 그 이름이면 바꾸지 않고(병합 방지) 경고."""
    disp = " ".join((getattr(product, "exposed_name", "") or "").split())
    out: list[str] = []
    for o in opts:
        label = o.label if multi else ""
        vids = set(o.vendor_item_ids)
        old = wb.resolve_block_name(biz, list(vids))
        reg_changed = bool(old) and wb.registered_name(biz, old) not in ("", base)
        if disp:
            want = _block_name(disp, label)
        elif old and not reg_changed:
            want = old
        else:
            want = _block_name(base, label)
        taken = wb.has_product(biz, want) and want != old and not (set(wb.product_vids(biz, want)) & vids)
        if taken:                                       # 다른 상품 블록이 그 이름 → 기존/등록명 유지(병합 방지)
            log(f"  [상품명] ⚠ '{want}' 은 이미 다른 상품 블록 이름 — 기존 이름 유지")
            want = old or _block_name(base, label)
        elif old and old != want:
            if wb.set_display_name(biz, old, want):
                log(f"  [상품명] 현행화 '{old}' → '{want}'(같은 VID·이력 승계)")
            else:
                want = old
        if wb.has_product(biz, want):
            wb.set_registered_name(biz, want, base)    # 등록상품명 최신화(다음 실행의 '등록명 바뀜' 판정 기준)
        out.append(want)
    return out


def _migrate_product_blocks(wb, biz: str, base: str, rep_name: str, vids_all, opts, multi: bool,
                            log, names: list[str] | None = None) -> None:
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
    new_names = set(names or [_block_name(base, o.label if multi else "") for o in opts])   # 이번에 쓸(이어쓸) 블록
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


def _skip_unmatched(wb, biz: str, product, seen_products: list, unmatched: list) -> bool:
    """미매칭(VID 없음) 상품은 블록을 만들지·쓰지 않는다(D-008, 소유자 2026-10-08: 쿠팡 상품이면 VID 는 반드시 있다 →
    VID 없는 블록 = 매칭 실패 오류. 예전엔 대장명으로 블록을 만들어 판매자배송·0·'50위밖' 기본값이 실제 값처럼 보였다).
    대장명은 unmatched 에 기록(로그). 같은 이름의 **VID 있는 기존 블록**은 오늘만 못 찾은 것이라 seen 에 넣어
    판매중지 표기·삭제를 막는다(오늘 칸은 공란). 반환 True = 이 상품 건너뜀."""
    if any(o.vendor_item_ids for o in product.options):
        return False
    unmatched.append(product.name)
    if wb.has_product(biz, product.name) and wb.product_vids(biz, product.name):
        seen_products.append(product.name)
    return True


def _purge_vidless_blocks(wb, biz: str, seen_products, account_id: str, live_vids, log) -> list[str]:
    """VID 없는 잔재 블록 정리(D-008) — 이번 실행에 기록 안 됐고(seen 아님) VID 도 없는 블록 = 매칭 실패 잔재.
    예: 대장 '문어발선풍기m10 (대체요망)' 이름으로 만들어졌다가 9/29 VID 블록 '문어발선풍기 M10' 으로 매칭된 뒤에도
    등록명이 달라 _migrate_product_blocks 가 못 지우고 남은 것(이름 기반 순위로 '50위밖' 이 계속 찍혔다).
    ⚠ 이번 상품조회 실패(live_vids 비어 있음)면 건너뜀 — 구글시트 복원 마스터는 숨김 메타(VID)가 없어 정상 블록도
    VID 가 비어 보인다(오삭제 방지). 다계정ID 스코핑: 그 계정ID 소속(또는 미태깅)만. 반환=삭제한 블록명."""
    if not live_vids:
        return []
    seen = set(seen_products)
    acct = (account_id or "").strip()
    removed: list[str] = []
    for p in list(wb.products_of(biz)):
        if p in seen or wb.product_vids(biz, p):
            continue
        if acct and wb.product_account_id(biz, p) not in ("", acct):
            continue
        if wb.delete_product_block(biz, p):
            removed.append(p)
    if removed:
        log(f"  [정체성] [{biz}] VID 없는 잔재 블록 {len(removed)}개 삭제(매칭 실패 잔재·D-008): "
            f"{removed[:3]}{'…' if len(removed) > 3 else ''}")
    return removed


def _process_account(report_acc, wb, metrics, inv_by_vid, date_iso, log, save_path, sale_status=None,
                     upbundle_vids=None, live_vids=None, vid_meta=None, pid_by_vid=None) -> None:
    """계정(시트) 하나(① 판매수집): 상품마다 **옵션 블록**을 만들고 판매정보(지표·재고·vid)를 기록·저장.

    다중옵션 상품은 옵션(vid)별 블록으로 분리한다 — **대표(첫 옵션)** 블록만 키워드·순위 행 자리를 두고
    (키워드는 ②, 순위는 ③), 나머지 옵션 블록은 판매정보만. 단일옵션은 대표 하나.
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
    unmatched: list[str] = []              # 쿠팡 상품과 매칭 안 된 대장 상품명(D-008: 블록 미생성)
    for product in report_acc.products:
        if _skip_unmatched(wb, biz, product, seen_products, unmatched):
            continue
        title = product.display_title
        kind = product.kind or config.KIND_PERSONAL
        opts = list(product.options) or [Option("")]
        multi = len(opts) > 1                           # 옵션 라벨은 **다중옵션에만** 붙인다(단일옵션=등록상품명 그대로)
        base = product.name                            # 등록상품명(vendor-inventory) = 블록 기준명
        vids_all = [oid for o in opts for oid in o.vendor_item_ids]
        names = _block_names(wb, biz, product, base, opts, multi, log)   # 노출상품명 현행화(D-013)
        rep_name = names[0]
        _migrate_product_blocks(wb, biz, base, rep_name, vids_all, opts, multi, log, names)
        # 수집 주기·마케팅은 상품(대표) 단위. 오늘 대상 아니면 이 상품의 모든 옵션 블록을 오늘치 생략.
        if product.mkt_start or product.mkt_end or product.mkt_mon:   # 대장에 마케팅 값 있을 때만 반영
            wb.set_marketing(biz, rep_name, product.mkt_start, product.mkt_end, product.mkt_mon)
        if wb.has_marketing():
            _due, _why = wb.product_due(biz, rep_name, date_iso)
            if not _due:
                log(f"  [{title}] {_why} — 오늘 수집 생략(상품 주기)")
                seen_products.extend(names)          # 있음(오늘 스킵돼도 '있음')
                continue
        # ── 옵션 블록 루프: 대표(i==0)만 키워드·순위 행 자리, 나머지는 판매정보만 ──
        pctx = _ProcCtx(wb=wb, metrics=metrics, inv_by_vid=inv_by_vid, date_iso=date_iso, log=log,
                        save_path=save_path, sale_status=sale_status, vid_meta=vid_meta, pid_by_vid=pid_by_vid)
        for i, opt in enumerate(opts):
            bname = names[i]
            seen_products.append(bname)
            _process_option(pctx, biz, product, base, kind, i, opt, bname)
            wb.set_product_account_id(biz, bname, report_acc.account_id)   # 항목5: 상품별 계정ID 태깅(다계정ID 사업자)
            # #8(2026-09-27): 대장 판매중지/취소선도 수집(위에서 지표·재고·판매가·판매상태 채움)하되 ③순위만 제외.
            # rank_suppressed(is_discontinued) 가 순위를 건너뛴다. 재판매(취소선 해제)면 False 로 해제.
            wb.set_discontinued(biz, bname, product.discontinued)
    _finish_account(wb, biz, report_acc, seen_products, unmatched, live_vids, log)
    wb.save(save_path)


def _finish_account(wb, biz: str, report_acc, seen_products, unmatched, live_vids, log) -> None:
    """계정 루프 뒤 마무리(행동 불변 분해 — _process_account 복잡도 C 유지): 미매칭 경고 → 죽은 중복·VID 없는
    잔재 정리 → 대장 대조(완전삭제·판매중지 표기) 로그."""
    if unmatched:
        log(f"  ⚠ [{biz}] 쿠팡 상품과 매칭 안 된 대장 상품 {len(unmatched)}개 — 블록 미생성(D-008·대장 상품명/쿠팡 등록 "
            f"확인 필요): {unmatched[:5]}{'…' if len(unmatched) > 5 else ''}")
    # 죽은 중복 블록 정리(안전 규칙): live 형제 있고 vid 가 상품조회서 소멸한 잔재만 삭제(reconcile 판매중지 표기 전)
    _sweep_dead_duplicates(wb, biz, live_vids, log)
    _purge_vidless_blocks(wb, biz, seen_products, report_acc.account_id, live_vids, log)   # VID 없는 잔재(D-008)
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
