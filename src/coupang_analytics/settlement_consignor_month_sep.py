"""위탁자 정산서 3차 형식 — 10 별도 입금(D-236 · 정산 금액에 넣음): 우대수수료 환급 2줄 + 추가지급 1줄(D-343 고정 3줄).
`settlement_consignor_month_cost.py` 에서 옮김(T-125 A1 · 파일 MI 유지 · 우대수수료 계산 그대로) · 추가지급 = 소유자 11-19 "줄 추가 (추천)".
"""
from __future__ import annotations

from coupang_analytics import settlement_additional_pay as AP
from coupang_analytics import settlement_managed_alloc as MA
from coupang_analytics.settlement_consignor_month_calc import MonthState
from coupang_analytics.settlement_statement_account import num

# 10 고정 3줄(D-343 · 추가지급 줄 = 소유자 11-19 "줄 추가 (추천)" · T-125 A1)
SEP_NAMES = ("우대수수료 환급 (관리 상품 몫)", "우대수수료 환급 (상품 확인 전 · 계정 전체)", "추가지급 (관리 상품 몫)")


# ── 10 별도 입금 ──
def _fav_split(st: MonthState, rows: list) -> tuple[float, float, float]:
    """우대수수료 환급 줄 → (관리 몫, 상품 모르는 주문 금액, 계정 전체) · 날짜별 표 줄(st.fav_rows)."""
    st.fav_rows = []
    m = unk = tot = 0.0
    for x in rows:
        a = num(x.get("refundAmount"))
        tot += a
        pids = sorted(st.order_pids.get(str(x.get("orderId"))) or [])
        dt = x.get("realTransferDateStr") or x.get("expectedTransferDateStr")
        if pids:
            sh = sum(st.is_m(p) for p in pids) / len(pids)
            m += a * sh
            st.fav_rows.append((dt, x.get("transferStatus"), a * sh))
        else:
            unk += a
            st.fav_rows.append((dt, x.get("transferStatus"), a))
    return m, unk, tot


def _additional(st: MonthState) -> float:
    """10 추가지급(D-236 · D-308 ① finalRewardAmount · 보류 해제와 따로) — 이 달 지급일 PAID 줄 · 관리 몫 = 옛 엑셀과 같은 옵션 → 관리 VID
    (`MA.vid_share`) · 날짜별 표 줄(st.add_rows: 지급 끝 = 지급일 · 그 밖 = 지급일 미정 D-294 ②)."""
    st.add_rows = []
    rows = [x for x in st.d["add"]["줄"] if x["지급구분"] == AP.PAID]
    nodate = [x for x in rows if not x.get("지급일")]
    if nodate:
        st.j.append(f"확인 필요: 추가지급 지급일 없는 {len(nodate)}줄 {sum(num(x['지급금액']) for x in nodate):,.0f}원 — 정산서 달을 못 정해 넣지 않음")
    tot = m = 0.0
    for x in rows:
        day = str(x.get("지급일") or "")[:10]
        if day[:7] != st.m:
            continue
        am = MA.vid_share([(x["옵션ID"], num(x["지급금액"]))], lambda v: bool(st.is_mv.get(v)))[0]
        tot, m = tot + num(x["지급금액"]), m + am
        st.add_rows.append((day if day <= st.basis else None, am))
    st.addpay = {"계정 전체": tot, "관리 몫(옵션 → 관리 VID)": m, "줄": len(st.add_rows)}
    if st.add_rows:
        st.j.append(f"10 추가지급 = 이 달 지급 {len(st.add_rows)}줄 계정 전체 {tot:,.0f}원 중 관리 옵션 {m:,.0f}원(쿠팡 추가지급 메뉴 finalRewardAmount · "
                    "옵션 → 관리 VID · D-236 · D-308 ①)")
    return m


def _sep_notes(st: MonthState) -> None:
    ex = [x for x in st.d["extras"] if str(x.get("일자"))[:7] == st.m]
    if ex:
        st.j.append(f"확인 필요: 이 달 쿠팡 별도 보상 {ex} — 이번 계산에 안 넣음")


def separate(st: MonthState) -> None:
    """10 별도 입금 = 우대수수료 환급(D-236 · 정산 금액에 넣음) — 주문 → 상품 관리 몫 · 상품 모르는 주문 = 계정 전체 금액(D-241 ②)."""
    fav = (st.d["v"].get("favorable") or {}).get(st.mk) or {}
    rows = fav.get("rows") or []
    m, unk, tot = _fav_split(st, rows)
    if (fav.get("totalCount") or 0) != len(rows):
        st.j.append(f"확인 필요: 우대수수료 환급 {st.mk} 목록 {len(rows)}줄 ≠ 쿠팡 전체 건수 {fav.get('totalCount')}")
    st.fav = {"계정 전체": tot, "관리 몫(주문 → 상품)": m, "상품 모르는 주문(계정 전체 금액 그대로)": unk, "건수": len(rows)}
    st.sep = [(SEP_NAMES[0], m), (SEP_NAMES[1], unk), (SEP_NAMES[2], _additional(st))]     # 늘 3줄 · 값 없으면 0(D-343)
    if round(unk):
        st.j.append(f"우대수수료 환급 중 주문이 아직 정산 파일에 없는 {unk:,.0f}원 = 상품을 몰라 계정 전체 금액 그대로 10 에 넣음"
                    "(D-241 ② · 쿠팡 자료로 상품이 확인되면 그때 상품별로 나눔)")
    _sep_notes(st)
