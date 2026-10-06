"""홈 '변동 추이' 집계 — 결과 통계 마스터(엑셀)를 **날짜별 합계**로 읽는 조회 전용 로직(Qt 없음).

시안 홈 보드(Main)의 변동 추이 카드: 탭 = 노출순위·판매현황·방문자·검색량(=노출량).
- 노출순위: 막대 = 그날 **1페이지 안**(정확 순위 ≤ `config.RANK_ORGANIC_PER_PAGE`)에 든 키워드 수 · 아래 = 평균 순위.
- 그 외: 그날 전 사업자·전 상품의 지표 합계.
값이 하나도 없는 날(미실행·중단)은 0 이 아니라 **None(공란)** — 결과 파일의 '미실행=공란' 규칙과 같다.

읽기 방식은 기존 app_qt 판매 분석 탭과 동일(OutputWorkbook 인덱스 읽기·쓰기 없음). 집계는 순수 데이터
(`DayData`)에서 하므로 엑셀 없이 검증된다(tools/verify_home_trend_offline.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from coupang_analytics import config
from coupang_analytics.workbook_common import _parse_date

RANK = "노출순위"
# 탭 이름 → 지표행 이름(노출순위는 키워드 순위행에서 따로 집계)
METRICS: dict[str, str | None] = {RANK: None, "판매현황": config.M_SALES,
                                  "방문자": config.M_VISITORS, "검색량": config.M_VIEWS}
UNITS = {RANK: "개", "판매현황": "건", "방문자": "명", "검색량": "회"}
PERIODS = {"7d": "최근 7일", "14d": "최근 14일", "month": "이번 달"}
PAGE1 = config.RANK_ORGANIC_PER_PAGE      # 검색 1페이지 상품수(실측) — 이 안에 든 키워드 수를 센다


@dataclass
class DayData:
    label: str                                    # 결과 파일의 날짜 라벨(예 '09.16')
    sums: dict[str, float] = field(default_factory=dict)   # {지표행: 합계} — 값이 하나라도 있는 지표만
    ranks: list[int] = field(default_factory=list)          # 그날 정확 순위 전부(위밖·공란·차단 제외)


@dataclass(frozen=True)
class DayPoint:
    day: date
    label: str
    value: float | None
    sub: str = ""                                  # 막대 아래 보조(노출순위=평균 순위)


# ── 엑셀 → DayData (어댑터) ──────────────────────────────────────
def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    s = str(v or "").replace(",", "").strip()
    try:
        return float(s) if s else None
    except ValueError:
        return None


def collect(wb) -> dict[date, DayData]:
    """OutputWorkbook → {날짜: DayData}. 전 사업자 시트를 합친다(같은 날짜는 한 칸)."""
    wanted = {m for m in METRICS.values() if m}
    out: dict[date, DayData] = {}
    for biz in wb.account_sheets():
        ws = wb.wb[biz]
        metric_rows = [(m, r) for (b, _p, m), r in wb._metric_row.items() if b == biz and m in wanted]
        kw_rows = [r for (b, _p, _k), r in wb._kw_row.items() if b == biz]
        for label, col in wb._date_col.get(biz, {}).items():
            d = _parse_date(label)
            if d is None:
                continue
            day = out.setdefault(d, DayData(label=str(label)))
            for m, r in metric_rows:
                v = _num(ws.cell(row=r, column=col).value)
                if v is not None:
                    day.sums[m] = day.sums.get(m, 0) + v
            for r in kw_rows:
                n = wb._rank_num(ws.cell(row=r, column=col).value)
                if n is not None:
                    day.ranks.append(n)
    return out


def load_master(path) -> dict[date, DayData]:
    from coupang_analytics.workbook import OutputWorkbook
    return collect(OutputWorkbook.load(path))


# ── 순수 집계 ───────────────────────────────────────────────────
def last_day(daily: dict[date, DayData]) -> date | None:
    """값이 하나라도 있는 마지막 날(빈 날짜 칸만 있는 날은 제외)."""
    days = [d for d, x in daily.items() if x.sums or x.ranks]
    return max(days) if days else None


def period_range(period: str, end: date) -> tuple[date, date]:
    if period == "7d":
        return end - timedelta(days=6), end
    if period == "14d":
        return end - timedelta(days=13), end
    if period == "month":
        return end.replace(day=1), end
    raise ValueError(f"알 수 없는 기간: {period}")


def value_of(day: DayData | None, tab: str) -> tuple[float | None, str]:
    """그날 탭 값과 보조 문구. 데이터 없음 = (None, '')."""
    if day is None:
        return None, ""
    if tab == RANK:
        if not day.ranks:
            return None, ""
        avg = round(sum(day.ranks) / len(day.ranks))
        return sum(1 for n in day.ranks if n <= PAGE1), f"평균 {avg}위"
    metric = METRICS.get(tab)
    if metric is None:
        raise ValueError(f"알 수 없는 추이 종류: {tab}")
    return day.sums.get(metric), ""


def series(daily: dict[date, DayData], tab: str, start: date, end: date) -> list[DayPoint]:
    """start~end 의 **모든 달력 날짜** 점(없는 날=None) — 막대가 빠지지 않고 빈 트랙으로 보이게."""
    out = []
    d = start
    while d <= end:
        day = daily.get(d)
        v, sub = value_of(day, tab)
        out.append(DayPoint(d, day.label if day else d.strftime("%m.%d"), v, sub))
        d += timedelta(days=1)
    return out


def delta_pct(cur, prev) -> int | None:
    """증감률(%·반올림). 비교 불가(어느 한쪽 없음·이전 0) = None."""
    if cur is None or prev is None or prev == 0:
        return None
    return round((cur - prev) / prev * 100)


def week_compare(daily: dict[date, DayData], tab: str, end: date) -> tuple[float | None, float | None, int | None]:
    """마지막 날 값 vs **지난주 같은 요일** 값(시안 '지난주 같은 요일 대비') → (현재, 이전, 증감%)."""
    cur, _ = value_of(daily.get(end), tab)
    prev, _ = value_of(daily.get(end - timedelta(days=7)), tab)
    return cur, prev, delta_pct(cur, prev)
