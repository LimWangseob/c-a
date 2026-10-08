"""정산 지급일 6종 (POLICY `PAYOUT_*`). SSOT=designs/SETTLEMENT_MODULE.md §3.

정산 주 = 월~일. 주가 월 경계를 넘으면 월별로 행이 나뉘지만 **지급일은 그 주 마감일(일요일) 기준으로 같다**
(골든: 2026-08-31 단독 행과 09-01~09-06 행 모두 09-29). 공휴일 집합은 인자로 받는 순수 계산(holiday_kr).
계산 지급일·금액은 **예측값**(`is_estimate=True`) — 실지급은 쿠팡 API/파일 값이 정본.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from .holiday_kr import add_business_days, next_business_day

PAYOUT_MP_WEEKLY_1ST = "PAYOUT_MP_WEEKLY_1ST"       # 윙 주정산 70%: 주 마감일 + 15영업일
PAYOUT_MP_WEEKLY_FINAL = "PAYOUT_MP_WEEKLY_FINAL"   # 윙 최종액 30%: 매출인식월 익익월 1일(보정 없음)
PAYOUT_MP_MONTHLY = "PAYOUT_MP_MONTHLY"             # 윙 월정산 100%: 월 마감일 + 15영업일
PAYOUT_RG_WEEKLY_1ST = "PAYOUT_RG_WEEKLY_1ST"       # 로켓그로스 주정산 70%: 주 마감일 + 20영업일
PAYOUT_RG_WEEKLY_FINAL = "PAYOUT_RG_WEEKLY_FINAL"   # 로켓그로스 2차 30%: 판매마감월 익익월 첫 영업일(월걸침 주=rg_payout_date)
PAYOUT_RG_MONTHLY = "PAYOUT_RG_MONTHLY"             # 로켓그로스 월정산 100%: 월 마감일 + 20영업일

# policy → (기준, 영업일 수(월말 최종액=0·미사용), 지급 비율)
_RULES: dict[str, tuple[str, int, Decimal]] = {
    PAYOUT_MP_WEEKLY_1ST: ("week", 15, Decimal("0.7")),
    PAYOUT_MP_WEEKLY_FINAL: ("month_final_calendar", 0, Decimal("0.3")),
    PAYOUT_MP_MONTHLY: ("month", 15, Decimal("1")),
    PAYOUT_RG_WEEKLY_1ST: ("week", 20, Decimal("0.7")),
    PAYOUT_RG_WEEKLY_FINAL: ("month_final_business", 0, Decimal("0.3")),
    PAYOUT_RG_MONTHLY: ("month", 20, Decimal("1")),
}
POLICIES = tuple(_RULES)


@dataclass(frozen=True)
class PayoutEstimate:
    policy: str
    date: date
    amount: int | None = None
    is_estimate: bool = True          # 계산값=예측용·실지급은 API/파일이 정본


def week_sunday(d: date) -> date:
    """그 날짜가 속한 정산 주(월~일)의 마감일(일요일). 월 경계 분할 행도 원래 주의 일요일."""
    return d + timedelta(days=6 - d.weekday())


def _month_start(ym: str) -> date:
    try:
        y, m = (int(x) for x in str(ym).split("-"))
        return date(y, m, 1)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"월 형식은 'YYYY-MM' 이어야 함: {ym!r}") from exc


def _add_months(first: date, n: int) -> date:
    y, m = divmod(first.month - 1 + n, 12)
    return date(first.year + y, m + 1, 1)


def _month_end(ym: str) -> date:
    return _add_months(_month_start(ym), 1) - timedelta(days=1)


def payout_date(policy: str, *, week_end: date | None = None, revenue_month: str | None = None,
                holidays) -> date:
    """지급일. 주정산(_WEEKLY_1ST)=week_end(주 마감일 또는 분할 행 마감일 → 그 주 일요일로 맞춤) 필요,
    월 기준(_MONTHLY·_WEEKLY_FINAL)=revenue_month('YYYY-MM') 필요. 누락·미지 policy = ValueError."""
    if policy not in _RULES:
        raise ValueError(f"알 수 없는 지급 정책: {policy!r} — {', '.join(POLICIES)}")
    basis, days, _ratio = _RULES[policy]
    if basis == "week":
        if week_end is None:
            raise ValueError(f"{policy} 는 week_end(정산 주 마감일)가 필요함")
        return add_business_days(week_sunday(week_end), days, holidays)
    if revenue_month is None:
        raise ValueError(f"{policy} 는 revenue_month('YYYY-MM')가 필요함")
    if basis == "month":
        return add_business_days(_month_end(revenue_month), days, holidays)
    first = _add_months(_month_start(revenue_month), 2)            # 익익월 1일
    return first if basis == "month_final_calendar" else next_business_day(first, holidays)


def rg_payout_date(ratio: int, period_start: date, period_end: date, holidays) -> date:
    """로켓그로스 정산현황 한 줄의 지급일 — 쿠팡 도움말 「로켓그로스 상품의 정산은 어떻게 되나요?」 1.1 + 실측 629/629
    (2026-10-08, 운용 PC 13계정 정산현황 지급일 전부 일치):
    - 70%·100% = 그 주 마감일(일) + 20영업일 (100% = 월말 조각이 한 번에 지급된 줄·비율은 쿠팡 응답값을 그대로 씀)
    - 30%, 월이 바뀌는 주(월요일과 일요일의 달이 다름)의 조각 = 주 마감일 + **25영업일**
    - 30%, 그 밖 = 매출인식 달의 익익월 첫 영업일(PAYOUT_RG_WEEKLY_FINAL)
    ⚠ 영업일 공휴일 집합은 쿠팡 기준과 같아야 함(실측: 2026-05-01·07-17 도 비영업일). 모르는 비율 = ValueError."""
    if ratio in (70, 100):
        return payout_date(PAYOUT_RG_WEEKLY_1ST, week_end=period_end, holidays=holidays)
    if ratio != 30:
        raise ValueError(f"로켓그로스 지급비율은 70·30·100 중 하나여야 함: {ratio!r}")
    monday = period_start - timedelta(days=period_start.weekday())
    if monday.month != week_sunday(period_end).month:
        return add_business_days(week_sunday(period_end), 25, holidays)
    return payout_date(PAYOUT_RG_WEEKLY_FINAL, revenue_month=f"{period_start:%Y-%m}", holidays=holidays)


def _half_up(x: Decimal) -> int:
    return int(x.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def first_payout_70(policy: str, rows: list[int]) -> int:
    """정산 기간 70% 금액(실측 2026-10-06 화면 원 단위 일치):
    윙 = 전체 합계 × 70% 사사오입(8/24~30 주: 337,770 → 236,439) /
    로켓그로스 = **줄마다** 70% 사사오입 합(8/3~9 주: 줄별 합 551,901 → 30% 236,467 일치)."""
    if policy.startswith("PAYOUT_MP"):
        return _half_up(Decimal(sum(rows)) * Decimal("0.7"))
    return sum(_half_up(Decimal(a) * Decimal("0.7")) for a in rows)


def payout_amount(policy: str, row_amounts) -> int:
    """지급 비율 금액(예측값 — 실지급은 쿠팡 화면·파일이 정본). 실측 확정(2026-10-06·화면 원 단위 일치):
    - 70%(주정산) = first_payout_70 — 윙=전체×70%, 로켓그로스=줄별 70% 합.
    - 로켓그로스 30% = 전체 − 줄별 70% 합(row_amounts = 그 주 줄 금액들, 788,368 → 236,467).
    - **윙 최종액 30% = 그 달 합계 − (주별 70% 의 합)** — row_amounts = **주별 정산 합계 목록**(파일의
      정산예정일별 묶음). 8월: [49,721·16,364·11,191·337,770] → 415,046 − 290,533 = 124,513(화면 일치;
      전체×30% 는 124,514 로 1원 틀림).
    - 월정산 100% = 전체.
    ⚠ 옛 규칙 '모든 비율 행 단위 반올림 후 합산'은 실측과 불일치해 폐기(2026-10-06)."""
    if policy not in _RULES:
        raise ValueError(f"알 수 없는 지급 정책: {policy!r}")
    rows = []
    for a in row_amounts:
        if isinstance(a, bool) or not isinstance(a, int):
            raise TypeError(f"행 금액은 정수(원)여야 함: {a!r}")
        rows.append(a)
    ratio = _RULES[policy][2]
    if ratio == 1:
        return sum(rows)
    if policy == PAYOUT_MP_WEEKLY_FINAL:                # 주별 합계마다 70% 를 뺀 나머지
        return sum(rows) - sum(_half_up(Decimal(w) * Decimal("0.7")) for w in rows)
    first = first_payout_70(policy, rows)
    return first if ratio == Decimal("0.7") else sum(rows) - first


def estimate(policy: str, *, holidays, week_end: date | None = None, revenue_month: str | None = None,
             row_amounts=None) -> PayoutEstimate:
    """지급일(+선택: 비율 금액) 예측 묶음 — is_estimate=True."""
    amount = payout_amount(policy, row_amounts) if row_amounts is not None else None
    return PayoutEstimate(policy, payout_date(policy, week_end=week_end, revenue_month=revenue_month,
                                              holidays=holidays), amount)
