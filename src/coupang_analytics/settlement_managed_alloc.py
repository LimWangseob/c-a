"""관리 상품 몫 배분 — 쿠팡이 계정 단위로만 주는 항목을 상품 자료로 나눔(D-116 ②·D-117). 순수 함수(입력 = 쿠팡 원자료에서 뽑은 값).

각 함수는 (관리 몫, 계정 전체, 메모) 를 돌려준다. 자료가 없으면 None 을 돌려 호출부가 금액 없이 '확인 필요'로 두게 한다(D-146).
"""
from __future__ import annotations

from collections import Counter
from typing import Any


def _split(flags: list[bool]) -> float:
    """상품 여럿이면 관리 상품 개수 비율(같은 주문 안 — 쿠팡이 주문 단위로만 준 금액)."""
    return sum(flags) / len(flags) if flags else 0.0


def ship_split(ship_rows: list, order_pids: dict, mpids: set, returns: dict, is_managed_vid) -> dict:
    """윙 배송비 줄(주문번호, 판매액, 정산금액) → 관리/제외/확인 필요 금액.
    같은 주문의 상품 줄이 있으면 그 상품을 따르고, 없으면(구매확정 전 반품의 왕복배송비) 반품 조회의 반품 상품을 따른다."""
    out: dict[str, Any] = {"관리": [0.0, 0.0], "제외": [0.0, 0.0], "확인 필요": [0.0, 0.0], "근거": Counter()}

    def put(share: float, sales: float, settle: float) -> None:
        out["관리"][0] += sales * share
        out["관리"][1] += settle * share
        out["제외"][0] += sales * (1 - share)
        out["제외"][1] += settle * (1 - share)
    for order, sales, settle in ship_rows:
        pids = order_pids.get(order)
        if pids:
            put(_split([p in mpids for p in sorted(pids)]), sales, settle)
            out["근거"]["같은 주문 상품"] += 1
            continue
        rec = returns.get(order)
        vids = [str(i.get("vendorItemId")) for x in rec or [] for i in x.get("items") or []]
        if vids:
            put(_split([is_managed_vid(v) for v in vids]), sales, settle)
            out["근거"]["반품 조회 상품"] += 1
        else:
            out["확인 필요"][0] += sales
            out["확인 필요"][1] += settle
            out["근거"]["반품 자료 없음" if rec is None else "반품 기록 없음"] += 1
    return out


SVC_FEE = 55000.0
SVC_GENERAL, SVC_DIGITAL = 1_000_000, 5_000_000


def svc_charges(sales: dict, last_closed: str) -> dict:
    """판매자서비스이용료 부과(D-161) — sales = {구매확정 달 YYYY-MM: (일반, 가전, 구분 모름)} (윙 상품 판매액 − 환불·쿠폰 전·배송비 제외).
    일반 ≥ 100만 또는 가전 ≥ 500만 = 55,000원 1회(더하지 않고 따로 봄) · 구분 모름 = 일반으로 봄 · 끝나지 않은 달은 판정하지 않음."""
    return {ym: SVC_FEE for ym, (gen, dig, unk) in sales.items()
            if ym <= last_closed and (gen + unk >= SVC_GENERAL or dig >= SVC_DIGITAL)}


def svc_settle(charges: dict, paid: float, sales: dict) -> dict:
    """부과 달 순서로 쿠팡 실제 공제를 채워 관리 몫을 나눔(D-161) — sales = {구매확정 달: (관리 판매, 전체 판매)} · 부과 달은 빠짐없이 줄 것.
    잔액 = 아직 안 빠진 부과(정산 예정금에서 차감) · 규칙 밖 = 부과보다 더 빠진 쿠팡 금액."""
    left = max(paid, 0.0)
    out = {"공제 관리": 0.0, "잔액 전체": 0.0, "잔액 관리": 0.0, "규칙 밖": 0.0}
    for ym in sorted(charges):
        fee = charges[ym]
        got = min(left, fee)
        left -= got
        mm, aa = sales[ym]
        out["공제 관리"] += got * mm / aa
        out["잔액 전체"] += fee - got
        out["잔액 관리"] += (fee - got) * mm / aa
    out["규칙 밖"] = left + min(paid, 0.0)
    return out


def line_share(lines: list, k: str, since: str, ratio) -> float:
    """상품 자료 없는 공제의 관리 몫(D-162) — lines = [(판매 방식, 판매 기간 시작 달, 공제 항목)] · ratio(판매 방식, 달) = 그 줄 판매 기간의 관리 정산금 비율.
    공제를 받은 줄마다 나눠 더한 값 / 그 공제 합 = 공제 1원당 관리 몫."""
    due = sum(parts.get(k, 0.0) for _, ym, parts in lines if ym >= since)
    return sum(parts.get(k, 0.0) * ratio(ch, ym) for ch, ym, parts in lines if ym >= since) / due if due else 0.0


def _key(d, camp) -> tuple:
    return int(float(d)), str(int(float(camp)))


def ad_share(pa_rows: list, billable: dict, is_managed_vid, have: set | None = None) -> tuple | None:
    """광고(D-119): 보고서 줄(날짜, 캠페인 ID, 광고집행 옵션ID, 광고비) · billable = {(날짜, 캠페인 ID): 청구가능 광고비}.
    쿠팡 청구 최소 단위(날짜×캠페인)마다 청구가능액을 그날 보고서 옵션별 광고비 비율로 나눔. 보고서에 없는 날·캠페인 = 메모(관리 몫 0).
    캠페인 ID 가 빈 칸("")인 조정 = 그 달 캠페인 청구액의 관리 비율로 나눔.
    have = 보고서 파일을 받은 달(YYYYMM) — 그 밖의 달 청구는 비율 계산에서 뺌(아직 못 받은 달을 관리 몫 0 으로 치지 않게)."""
    if not billable:
        return None
    cost = _ad_cost(pa_rows, is_managed_vid)
    m = t = 0.0
    miss = []
    mon: dict = {}                                     # 달 → [관리 몫, 캠페인 청구 합]
    wait: dict = {}                                    # 보고서 아직 없는 달 → 뺀 청구액
    for (d, camp), b in list(billable.items()):
        if have is not None and str(int(float(d)))[:6] not in have:
            wait[str(int(float(d)))[:6]] = wait.get(str(int(float(d)))[:6], 0.0) + b
            continue
        if camp == "":
            continue
        t += b
        mm, aa = cost.get(_key(d, camp), (0.0, 0.0))
        mo = mon.setdefault(str(int(float(d)))[:6], [0.0, 0.0])
        mo[1] += b
        if aa:
            m += b * mm / aa
            mo[0] += b * mm / aa
        elif b:
            miss.append(f"{d}·{camp}")
    for (d, camp), b in billable.items():              # 캠페인 없는 조정(광고 프로모션 할인 등) = 그 달 캠페인 청구 관리 비율
        if camp != "" or (have is not None and str(int(float(d)))[:6] not in have):
            continue
        t += b
        mm, aa = mon.get(str(int(float(d)))[:6], (0.0, 0.0))
        if aa:
            m += b * mm / aa
        elif b:
            miss.append(f"{d}·캠페인 없음")
    return m, t, _ad_note(miss, wait)


def _ad_cost(pa_rows: list, is_managed_vid) -> dict:
    """(날짜, 캠페인 ID) → [관리 옵션 광고비, 전체 광고비] — 그날 광고 보고서."""
    cost: dict = {}
    for d, camp, vid, c in pa_rows:
        cm = cost.setdefault(_key(d, camp), [0.0, 0.0])
        cm[1] += c
        cm[0] += c if is_managed_vid(str(int(float(vid)))) else 0.0
    return cost


def _ad_note(miss: list, wait: dict) -> str:
    note = ("보고서에 없는 날·캠페인 " + ", ".join(miss[:5]) + (f" 외 {len(miss) - 5}" if len(miss) > 5 else "")) if miss else ""
    if wait:
        note = " · ".join(x for x in (note, "보고서 아직 없는 달 " + ", ".join(f"{k} {v:,.0f}원" for k, v in sorted(wait.items()))
                                      + " — 비율에서 뺌") if x)
    return note


def scoped(actual: float, due: float, covered: float) -> tuple[float, float]:
    """공제 관리 몫(D-140·D-146) — (관리 몫, 상품 자료 없는 공제). due = 관리 시작 뒤 쿠팡이 뺀 합 · covered = 상품별 자료 범위 전체 ·
    actual = 그 자료의 관리 상품 몫(그대로). 자료 없는 공제는 나누지 않고 돌려줘 호출부가 '확인 필요'로 둔다. 자료가 공제보다 많으면 공제액까지만."""
    if not due:
        return 0.0, 0.0
    if covered and abs(covered) > abs(due):
        return actual * due / covered, 0.0
    return actual, due - covered


def due_since(lines: list, k: str, since: str) -> float:
    """관리 시작 뒤 공제(D-154) — lines = [(판매 기간 시작 달 YYYY-MM, 공제 항목)]. 시작 전 판매분은 시작 뒤에 지급돼도 뺌."""
    return sum(parts.get(k, 0.0) for ym, parts in lines if ym >= since)


def milk_share(milk: list, inbound: list, is_managed_vid) -> tuple | None:
    """밀크런 줄(밀크런번호, 금액) · 입고 내역(milkrunSeq·cancelled·skus[vendorItemId·stowedQty·requestedQty]).
    밀크런마다 그 밀크런 입고 건들의 상품 적치 수량(없으면 요청 수량) 비율."""
    if not milk:
        return None
    qty: dict = {}
    for s in inbound:
        if s.get("cancelled") or not s.get("milkrunSeq"):
            continue
        q = qty.setdefault(str(s["milkrunSeq"]), [0.0, 0.0])
        for k in s.get("skus") or []:
            n = k.get("stowedQty") or k.get("requestedQty") or 0
            q[1] += n
            q[0] += n if is_managed_vid(str(k.get("vendorItemId"))) else 0
    m = t = 0.0
    miss = []
    for seq, amt in milk:
        t += amt
        mm, aa = qty.get(str(seq), (0.0, 0.0))
        if aa:
            m += amt * mm / aa
        else:
            miss.append(str(seq))
    return m, t, ("입고 내역 없는 밀크런 " + ", ".join(miss)) if miss else ""


def order_share(rows: list, order_pids: dict, mpids: set) -> tuple:
    """주문 단위 금액(주문번호, 금액 — 우대수수료 환급) → 그 주문 상품을 따름. 상품 모르는 주문 = 메모."""
    m = t = unk = 0.0
    for order, amt in rows:
        t += amt
        pids = order_pids.get(str(order))
        if pids:
            m += amt * _split([p in mpids for p in sorted(pids)])
        else:
            unk += amt
    return m, t, f"정산 원본에 상품 없는 주문 {unk:,.0f}원" if unk else ""


def vid_share(rows: list, is_managed_vid) -> tuple:
    """옵션 단위 금액(옵션ID, 금액 — 추가지급) → 관리 옵션이면 관리 몫."""
    m = sum(a for v, a in rows if is_managed_vid(str(v)))
    return m, sum(a for _, a in rows), ""


def contract_start(auto: str, contract: str | None, known: bool) -> tuple[str, str]:
    """관리 시작 달(D-185) → (시작 달 YYYY-MM, 정산서 '확인 필요' 문구 · 같으면 '').
    auto = 자동 판정 달(관리 상품 첫 판매·첫 물류비 · 활동 없으면 '') · contract = 관리 상품과 품목이 맞는 계약일(YYYY-MM-DD ·
    못 찾으면 None) · known = 계정이 계약 대조 표에 있음. 규칙 = 자동·계약 중 이른 달 + 계약 전 판매 제외 — 자동이 더 빠르면 그 앞 판매가
    빠지므로 결과는 계약 달."""
    if not auto:
        return "", ""
    if not known:
        return auto, f"관리 시작 {auto} = 자동 판정(관리 상품 첫 판매) · 계약 대조 표에 없음 — 확인 필요"
    if not contract:
        return auto, f"관리 시작 {auto} = 자동 판정(관리 상품 첫 판매) · 관리 상품과 맞는 계약 못 찾음 — 확인 필요"
    cm = contract[:7]
    if cm == auto:
        return cm, ""
    if auto < cm:
        return cm, f"관리 시작 {cm} = 계약 {contract} · 자동 판정 {auto}(첫 판매)보다 늦음 — 계약 전 판매 제외 · 확인 필요"
    return cm, f"관리 시작 {cm} = 계약 {contract} · 자동 판정 {auto}(첫 판매)보다 이름 — 확인 필요"


def pre_contract(ym: str, contract: str | None) -> bool:
    """그 달(YYYY-MM)이 계약 달 앞이면 True — 계약 전 판매는 관리 상품으로 보지 않음(D-185 ②)."""
    return bool(contract) and ym < str(contract)[:7]


def gap_free(actual: float, fs_actual: float, fs_covered: float, due_fs: float, share_fs: float) -> tuple[float, float]:
    """판매 0인 달(계약 달 ~ 관리 첫 판매 전 · D-186) 을 뺀 공제 관리 몫 → (관리 몫, 상품 자료 없는 공제).
    상품 자료 없는 공제는 첫 판매 달부터의 공제(due_fs)·상품 자료(fs_covered)·평균 비율(share_fs)로만 나눈다 — 판매 0인 달은 그 달 관리
    비율이 0 이라 몫 0(나눌 금액·평균 양쪽에서 뺌). actual − fs_actual = 판매 0인 달의 상품별 관리 금액(쿠팡 자료) = 그대로 더함."""
    amt, miss = scoped(fs_actual, due_fs, fs_covered)
    return amt + miss * share_fs + (actual - fs_actual), miss
