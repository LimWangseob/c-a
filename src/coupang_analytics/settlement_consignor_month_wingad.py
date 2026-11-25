"""위탁자 정산서 3차 형식 — 5 광고비 중 쿠팡이 지급 줄에서 이미 뺀 금액의 달·위치와 아직 안 뺀 몫(T-186). `settlement_consignor_month_calc.ads` 가 부름 · st = MonthState.

윙 지급 줄 차감 사유 '…광고비' 에는 달 표시가 없고, 로켓그로스 달 표시(adSalesOffsetYearMonthBreakdown)는 광고 달이 아니라 그 줄의 판매 달(원문 862/862) →
둘 다 광고센터 청구금액(광고정산 json summary)과 맞춤: 줄의 판매 달 = 광고 달(그 달 청구까지) + 남고 모자란 금액만 누적으로 옮김(D-285 ② · D-289 ② · D-301 · D-308 ②).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from coupang_analytics.settlement_statement_account import num

TOL = 2                     # 청구 ↔ 공제 끝전 ±2원 = 다 빠진 것(D-281)


def _take(ls: list, amt: float) -> list:
    """줄 [[지급 줄 key, 금액]] 에서 amt 만큼 앞부터 떼어 냄 — 같은 부호 줄에서만."""
    out = []
    for x in ls:
        part = min(x[1], amt) if amt > 0 else max(x[1], amt)
        if part * amt > 0:
            out.append((x[0], part))
            x[1] -= part
            amt -= part
    return out


def _border(own: dict, m: str, bills: dict) -> list:
    """달 경계 주 — 이 달 줄(판매 기간 끝 = 달 끝)과 같은 지급일인 바로 다음 날 시작 줄(다음 달 · 청구 자료 있을 때만)."""
    ends = {(str(k[0]), str(date.fromisoformat(str(k[2])[:10]) + timedelta(days=1))) for k, _a in own[m]}
    return [x for n, ls in own.items() if n > m and n in bills for x in ls if (str(x[0][0]), str(x[0][1])[:10]) in ends]


def _settle(owed: list, ls: list, extra: float, got: dict) -> float:
    """그 달 청구를 넘는 금액 → 앞 달 모자란 몫(같은 금액인 달 먼저 → 오래된 달) · 남은 넘침을 돌려줌."""
    for x in sorted(owed, key=lambda o: o[1] != extra):
        part = min(max(extra, 0), x[1])
        got[x[0]] += _take(ls, part)
        x[1] -= part
        extra -= part
    return extra


def _move(over: list, border: list, short: float) -> list:
    """rg: 모자란 몫 ← 앞 달에서 더 빠진 줄 ← 같은 지급일 다음 달 첫 줄."""
    moved = _take(over, short)
    return moved + _take(border, short - sum(a for _key, a in moved))


def ad_months(bills: dict, lines: list, rg: bool = False) -> tuple[dict, list]:
    """지급 줄 광고 공제 → ({광고 달: [(지급 줄 key, 금액)]}, 못 가른 것 [(key, 판매 달, 금액)]) · T-186.
    bills = {달: 광고 청구금액} · lines = [(판매 달, key, 공제액)] · 광고 달 = 줄의 판매 달(달 단위 D-285 ②) · 그 달 청구를 넘는 금액 = 앞 달 모자란 몫
    (지급 순서 누적 D-289 ②). 앞 달 몫도 아닌 금액·청구 자료 없는 달 줄 = 윙: 못 가름 · 로켓그로스(rg): 쿠팡 달 표시대로 그 달.
    rg = 달 경계 이동(D-301 · D-308 ②): 모자란 달 ← 앞 달에서 더 빠진 몫(마지막 주 줄부터) ← 같은 지급일 다음 달 첫 줄."""
    own, home = defaultdict(list), {}
    for m, key, a in lines:
        own[m].append([key, a])
        home[key] = m
    got: dict = defaultdict(list)
    owed: list = []                                       # [달, 아직 안 빠진 청구] 오래된 달부터
    over: list = []                                       # rg: 앞 달들에서 청구보다 더 빠진 줄
    unknown: list = []
    for m in sorted({*bills, *own}):
        ls = sorted(own[m], key=lambda x: str(x[0][0]))
        if m not in bills:
            unknown += [(key, m, a) for key, a in ls]
            continue
        bill, total = bills[m], sum(a for _key, a in ls)
        mine = min(max(total, min(bill, 0)), max(bill, 0))  # 이 달 몫 = 청구액까지(청구 부호 안에서)
        extra, short = _settle(owed, ls, total - mine, got), bill - mine
        back = sorted(ls, key=lambda x: str(x[0][1]), reverse=True) if rg else ls
        rest = _take(back, extra)
        got[m] += [(key, a) for key, a in ls if a]
        if rg:
            moved = _move(over, _border(own, m, bills), short)
            got[m] += moved
            short -= sum(a for _k, a in moved)
            over += [list(x) for x in rest]
        else:
            unknown += [(key, m, a) for key, a in rest]
        owed = [x for x in [*owed, [m, short]] if x[1] > 0]
    if not rg:
        return got, unknown
    for key, a in [*over, *((key, a) for key, _m, a in unknown)]:
        got[home[key]] += [(key, a)] if a else []
    return got, []


def _note(st, ch: str, mine: list, unknown: list) -> None:
    late = [(key, a) for key, a in mine if str(key[1])[:7] != st.m]
    if late:
        what = "그 달 지급 줄에서 모자란" if ch == "윙" else "그 달 지급 줄 밖에서 빠진"
        st.j.append(f"5 광고비 — {st.m} {ch} 광고 청구 중 {what} {sum(a for _key, a in late):,.0f}원은 다른 달 지급 줄에서 빠진 이월로 봄("
                    + " · ".join(f"{key[0]} {a:,.0f}" for key, a in late) + " · 쿠팡 광고 달 표시 없음 · 지급 순서 누적 D-289 ②)")
    for key, m, a in unknown:
        if m == st.m:
            st.j.append(f"확인 필요: {ch} 지급 줄 {key} 광고 차감 {a:,.0f} — 달 표시 없음 · 광고 청구 자료로 어느 달 광고인지 못 가름(위치에 안 넣음 · 금액은 광고 청구 자료 기준)")


def _rest_note(st, ch: str, bill: float, done: float, lines: list) -> None:
    rest = bill - done
    if rest <= TOL:
        return
    if any(m > st.m and a for m, _key, a in lines):
        st.j.append(f"확인 필요: {st.m} {ch} 광고 청구 {bill:,.0f} 중 {rest:,.0f}원을 뺀 지급 줄을 못 찾음 — 뒤 달 지급 줄에 광고 공제가 있지만 이 달 몫인지 "
                    "쿠팡 표시가 없음(미납일 수 있음 D-309) · 날짜별 표 '지급일 미정'으로 둠")
    else:
        st.j.append(f"5 광고비 — {st.m} {ch} 광고 청구 {bill:,.0f} 중 {rest:,.0f}원은 쿠팡이 아직 안 뺌 → 날짜별 표 '지급일 미정'(예정)")


def ad_deducted(st, rg_lines: list) -> tuple[float, float]:
    """쿠팡이 지급 줄에서 뺀 이 달 광고비 → 위치(loc) · (뺀 합, 날짜별 표 나누는 분모 = 다 빠졌거나 청구를 모르면 뺀 합 · 안 빠진 몫이 있으면 청구액).
    rg_lines = 로켓그로스 줄 [(달 표시, key, 금액)] — 공제 0 인 줄도(달 경계 주 찾기)."""
    wing = [(str(row[3])[:7], key, num(x.get("금액"))) for key, row, r in st.lines() if r["채널"] == "윙"
            for x in r.get("차감 사유") or [] if "광고" in (x.get("사유") or "") and num(x.get("금액"))]
    deducted, billed = 0.0, 0.0
    for ch, lines in (("윙", wing), ("로켓그로스", rg_lines)):
        bills = st.d["ad_bills"][ch]
        got, unknown = ad_months(bills, lines, rg=ch != "윙")
        done = sum(a for _key, a in got[st.m])
        st.loc["ad"] += got[st.m]
        deducted += done
        billed += bills.get(st.m, float("nan"))          # 청구 모름 = nan → 분모는 뺀 합
        _note(st, ch, got[st.m], unknown)
        if st.m in bills:
            _rest_note(st, ch, bills[st.m], done, lines)
    return deducted, billed if abs(billed - deducted) > TOL else deducted
