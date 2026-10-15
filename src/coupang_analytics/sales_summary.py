"""통합 판매현황 집계(순수 로직·오프라인) — SSOT=designs/SALES_SUMMARY.md(소유자 2026-10-15).

계정별·상품별 판매수량·판매금액(윙/로켓그로스 구분)을 **전일 · 주간(월~일) · 월별** 세 구역으로 만든다.
원천 = 판매분석 저장(sales_history): 전일 = 일별 기록, 주·월 = 기간별 기록(쿠팡이 준 기간 합계 그대로).
값이 없는 기간 = None(**미수집**) — 판매 0(0, 0)과 구분한다. 최신 칸이 왼쪽(결과 파일 날짜 칸과 같은 방향).
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

FIRST_DAY = date(2026, 1, 1)   # 월별 시작(소유자 2026-10-15 '2026.1.1부터')
WEEKS = 8                       # 주간 칸 수(이번 주 누계 포함)


@dataclass(frozen=True)
class Col:
    key: str      # 'D:YYYY-MM-DD' · 'W:YYYY-MM-DD'(월요일) · 'M:YYYY-MM'
    label: str


@dataclass
class Row:
    product: str
    kind: str                                       # 윙 · 로켓그로스
    values: dict = field(default_factory=dict)      # {열 키: (수량, 금액)}


@dataclass
class AccountBlock:
    aid: str
    label: str
    rows: list = field(default_factory=list)        # 판매 있는 상품만(판매 0 상품은 생략)
    total: dict = field(default_factory=dict)       # {열 키: (수량, 금액) | None(미수집)}


@dataclass
class Section:
    title: str
    cols: list
    accounts: list
    total: dict = field(default_factory=dict)       # {열 키: (수량, 금액)} — 받은 계정만 합침
    missing: dict = field(default_factory=dict)     # {열 키: 미수집 계정 수}


@dataclass
class Summary:
    yesterday: date
    sections: list


# ── 기간 계산 ─────────────────────────────────────────────────
def month_key(d: date) -> str:
    return f"M:{d:%Y-%m}"


def week_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _month_range(y: int, m: int, yesterday: date) -> tuple[date, date]:
    start = date(y, m, 1)
    return start, min(date(y, m, calendar.monthrange(y, m)[1]), yesterday)


def periods(yesterday: date, weeks: int = WEEKS, first: date = FIRST_DAY) -> list[tuple[str, str, date, date]]:
    """표시·조회할 기간 (키, 표시, 시작, 끝) — 달: first 달~어제 달(최신 먼저) · 주: 어제 주부터 weeks 개(최신 먼저).
    이번 달·이번 주의 끝 = 어제(누계)."""
    out = []
    mon = week_monday(yesterday)
    for i in range(weeks):
        s = mon - timedelta(weeks=i)
        out.append((f"W:{s.isoformat()}", f"{s:%m.%d}주", s, min(s + timedelta(days=6), yesterday)))
    y, m = yesterday.year, yesterday.month
    while (y, m) >= (first.year, first.month):
        s, e = _month_range(y, m, yesterday)
        out.append((month_key(s), f"{s.year % 100:02d}년 {m}월", s, e))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out


def plan_periods(existing: dict, yesterday: date, weeks: int = WEEKS, first: date = FIRST_DAY) -> list[tuple[str, str, str]]:
    """조회해야 할 기간 [(키, 시작, 끝)] — 아직 없거나, 받은 끝이 지금 계산한 끝보다 이른 것(이번 달·주 누계·막 끝난 기간).
    마감된 기간(받은 끝 = 기간 끝)은 다시 조회하지 않는다. 달 먼저(오래된 것부터) → 주."""
    need = []
    for key, _label, s, e in periods(yesterday, weeks, first):
        got = (existing.get(key) or {}).get("조회기간") or ["", ""]
        if got[1] < e.isoformat():
            need.append((key, s.isoformat(), e.isoformat()))
    months = sorted(k for k in need if k[0].startswith("M:"))
    weeks_ = sorted((k for k in need if k[0].startswith("W:")), reverse=True)
    return months + weeks_


# ── 집계 ──────────────────────────────────────────────────────
def _rows_of(rec: dict | None) -> dict | None:
    """기록 하나 → {(상품, 구분): (수량, 금액)} (옵션 합산). 기록 없음 = None(미수집)."""
    if rec is None:
        return None
    out: dict = {}
    for o in (rec.get("옵션") or {}).values():
        k = (o.get("상품") or "-", o.get("구분") or "-")
        q, a = out.get(k, (0, 0))
        out[k] = (q + int(o.get("판매수량") or 0), a + int(o.get("판매금액") or 0))
    return out


def _section(title: str, cols: list, recs_of, labels: dict) -> Section:
    sec = Section(title, cols, [])
    for aid in sorted(labels, key=lambda a: labels[a]):
        blk = AccountBlock(aid, labels[aid])
        per_row: dict = {}
        for c in cols:
            got = _rows_of(recs_of(aid, c.key))
            if got is None:
                blk.total[c.key] = None
                continue
            blk.total[c.key] = (sum(q for q, _a in got.values()), sum(a for _q, a in got.values()))
            for k, v in got.items():
                per_row.setdefault(k, {})[c.key] = v
        blk.rows = [Row(p, kind, vals) for (p, kind), vals in per_row.items() if any(q or a for q, a in vals.values())]
        blk.rows.sort(key=lambda r: (-sum(a for _q, a in r.values.values()), r.product, r.kind))
        sec.accounts.append(blk)
    for c in cols:
        have = [b.total[c.key] for b in sec.accounts if b.total.get(c.key) is not None]
        sec.total[c.key] = (sum(q for q, _a in have), sum(a for _q, a in have))
        sec.missing[c.key] = sum(1 for b in sec.accounts if b.total.get(c.key) is None)
    return sec


def build(daily: dict, period_recs: dict, labels: dict, yesterday: date,
          weeks: int = WEEKS, first: date = FIRST_DAY) -> Summary:
    """daily = {계정: {'YYYY-MM-DD': 기록}} · period_recs = {계정: {키: 기록}} · labels = {계정ID: 표시명}(위탁계정 전체).
    저장에만 있는 계정도 표시(표시명 = 계정ID)."""
    labels = dict(labels)
    for aid in list(daily) + list(period_recs):
        labels.setdefault(aid, aid)
    ps = periods(yesterday, weeks, first)
    day_cols = [Col(f"D:{yesterday.isoformat()}", f"{yesterday:%m.%d}")]
    week_cols = [Col(k, lb) for k, lb, _s, _e in ps if k.startswith("W:")]
    month_cols = [Col(k, lb) for k, lb, _s, _e in ps if k.startswith("M:")]
    def day_rec(aid, key):
        return (daily.get(aid) or {}).get(key[2:])

    def per(aid, key):
        return (period_recs.get(aid) or {}).get(key)

    day = _section(f"1. 전일 {yesterday:%m.%d}", day_cols, day_rec, labels)
    return Summary(yesterday, [day, _section("2. 주간 (월~일)", week_cols, per, labels),
                               _section("3. 월별", month_cols, per, labels)])
