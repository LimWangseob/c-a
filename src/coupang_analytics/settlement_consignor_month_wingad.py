"""위탁자 정산서 3차 형식 — 5 광고비 중 쿠팡이 윙 지급 줄에서 이미 뺀 금액의 달·위치(T-186). `settlement_consignor_month_calc.ads` 가 부름 · st = MonthState.

윙 지급 줄 차감 사유 '…광고비' 에는 광고 달 표시가 없음(로켓그로스는 adSalesOffsetYearMonthBreakdown 에 있음) → 광고센터 윙 청구금액(광고정산 json
summary.nonRod)과 지급 순서 누적으로 맞춤(D-285 ② · D-289 ②).
"""
from __future__ import annotations

from collections import defaultdict

from coupang_analytics.settlement_statement_account import num


def _take(ls: list, amt: float) -> list:
    """줄 [[지급 줄 key, 금액]] 에서 amt 만큼 앞(지급일 빠른 줄)부터 떼어 냄 — 같은 부호 줄에서만."""
    out = []
    for x in ls:
        part = min(x[1], amt) if amt > 0 else max(x[1], amt)
        if part * amt > 0:
            out.append((x[0], part))
            x[1] -= part
            amt -= part
    return out


def wing_ad_months(bills: dict, lines: list) -> tuple[dict, list]:
    """윙 지급 줄 광고 차감(쿠팡 달 표시 없음) → ({광고 달: [(지급 줄 key, 금액)]}, 못 가른 것 [(key, 판매 달, 금액)]) · T-186.
    bills = {달: 윙 광고 청구금액} · lines = [(판매 달, key, 차감액)] · 광고 달 = 줄의 판매 달(달 단위 D-285 ②) · 그 달 청구를 넘는 금액 = 앞 달 모자란 몫
    (지급 순서 누적 D-289 ② · 같은 금액인 달 먼저 → 오래된 달) · 앞 달 몫도 아닌 금액·청구 자료 없는 달 줄 = 못 가름."""
    own = defaultdict(list)
    for m, key, a in lines:
        own[m].append([key, a])
    got: dict = defaultdict(list)
    owed: list = []                                       # [달, 아직 안 빠진 윙 청구] 오래된 달부터
    unknown: list = []
    for m in sorted({*bills, *own}):
        ls = sorted(own[m], key=lambda x: str(x[0][0]))
        if m not in bills:
            unknown += [(key, m, a) for key, a in ls]
            continue
        bill, total = bills[m], sum(a for _key, a in ls)
        mine = min(max(total, min(bill, 0)), max(bill, 0))  # 이 달 몫 = 청구액까지(청구 부호 안에서)
        extra = total - mine
        for x in sorted(owed, key=lambda o: o[1] != extra):
            part = min(max(extra, 0), x[1])
            got[x[0]] += _take(ls, part)
            x[1] -= part
            extra -= part
        unknown += [(key, m, a) for key, a in _take(ls, extra)]
        got[m] += [(key, a) for key, a in ls if a]
        owed = [x for x in [*owed, [m, bill - mine]] if x[1] > 0]
    return got, unknown


def _wing_lines(st) -> list:
    """윙 지급 줄 차감 사유 중 광고 → [(판매 달, 지급 줄 key, 금액)]."""
    return [(str(row[3])[:7], key, num(x.get("금액"))) for key, row, r in st.lines() if r["채널"] == "윙"
            for x in r.get("차감 사유") or [] if "광고" in (x.get("사유") or "") and num(x.get("금액"))]


def wing_ad_deducted(st) -> float:
    """쿠팡이 윙 지급 줄에서 뺀 이 달 광고비 → 위치(loc) · 합. 못 가른 이 판매 달 줄 = '확인 필요'."""
    got, unknown = wing_ad_months(st.d["ad_wing"], _wing_lines(st))
    st.loc["ad"] += got[st.m]
    late = [(key, a) for key, a in got[st.m] if str(key[1])[:7] != st.m]
    if late:
        st.j.append(f"5 광고비 — {st.m} 윙 광고 청구 중 그 달 지급 줄에서 모자란 {sum(a for _key, a in late):,.0f}원은 뒤 달 지급 줄에서 빠진 이월로 봄("
                    + " · ".join(f"{key[0]} {a:,.0f}" for key, a in late) + " · 쿠팡 달 표시 없음 · 지급 순서 누적 D-289 ②)")
    for key, m, a in unknown:
        if m == st.m:
            st.j.append(f"확인 필요: 윙 지급 줄 {key} 광고 차감 {a:,.0f} — 달 표시 없음 · 윙 광고 청구 자료로 어느 달 광고인지 못 가름(위치에 안 넣음 · 금액은 광고 청구 자료 기준)")
    return sum(a for _key, a in got[st.m])
