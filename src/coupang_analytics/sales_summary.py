"""통합 판매현황 집계(순수 로직·오프라인) — SSOT=designs/SALES_SUMMARY.md(소유자 2026-10-15·2026-10-21).

상세표 = 계정→상품(윙/로켓그로스 구분) **일별** 판매수량·판매금액, **최근 31일·최신이 왼쪽**(2026-10-21 개편 —
주간·월별 구역은 상단 대시보드 차트가 대신·sales_dashboard). 원천 = 판매분석 저장(sales_history) 일별 기록.
값이 없는 날 = None(**미수집**) — 판매 0(0, 0)과 구분한다. 집계 기준 = **관리 상품**(결과 사업자 시트 블록의 VID,
판매중지 블록 포함)만 — scope(). 일별 소급(2026-04-01~) 계획 = plan_backfill.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

FIRST_DAY = date(2026, 1, 1)   # 월별 시작(소유자 2026-10-15 '2026.1.1부터')
WEEKS = 8                       # 주간 기간 수(기간 조회·대시보드 주간 선)
DETAIL_DAYS = 31                # 상세표 일별 칸 수(최근 31일·최신이 왼쪽 — 소유자 2026-10-21)
BACKFILL_FROM = date(2026, 4, 1)   # 일별 소급 시작(소유자 2026-10-21 '4/1부터')
BACKFILL_PER_DAY = 30              # 계정당 하루 최대 조회 일수(같은 세션 API — 차단 위험 줄이기)


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


def plan_backfill(existing: dict, yesterday: date, today: date | None = None,
                  first: date = BACKFILL_FROM, limit: int = BACKFILL_PER_DAY) -> list[str]:
    """일별 기록이 없는 날 ['YYYY-MM-DD'] — **최근 날짜부터 거꾸로**(어제 → first), 이미 있는 날은 빼고 최대 limit 개.
    오늘 이미 받은 기록(수집 시각이 오늘 — ① 하루치·앞선 실행의 소급 포함)만큼 limit 에서 빼서 '계정당 하루 최대'를 지킴."""
    stamp = (today or yesterday + timedelta(days=1)).isoformat()
    used = sum(1 for r in existing.values() if str((r or {}).get("수집", "")).startswith(stamp))
    out: list[str] = []
    d = yesterday
    while d >= first and len(out) < limit - used:
        if d.isoformat() not in existing:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return out


def scope(store: dict, managed: dict | None) -> dict:
    """{계정: {키: 기록}} → 관리 상품(VID)만 남긴 사본. managed = {계정ID: VID 집합}(결과 사업자 시트 블록) ·
    None = 거르지 않음. managed 에 없는 계정(결과 파일에 없는 계정)은 뺀다."""
    if managed is None:
        return store
    out: dict = {}
    for aid, recs in store.items():
        if aid not in managed:
            continue
        vids = managed[aid]
        out[aid] = {k: {**r, "옵션": {v: o for v, o in (r.get("옵션") or {}).items() if v in vids}}
                    for k, r in recs.items()}
    return out


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


def build(daily: dict, labels: dict, yesterday: date, days: int = DETAIL_DAYS) -> Summary:
    """상세표(일별·최근 days 일·최신이 왼쪽). daily = {계정: {'YYYY-MM-DD': 기록}}(scope 로 거른 것) ·
    labels = {계정ID: 표시명}. 저장에만 있는 계정도 표시(표시명 = 계정ID — 거르지 않은 경우)."""
    labels = dict(labels)
    for aid in daily:
        labels.setdefault(aid, aid)
    cols = [Col(f"D:{d.isoformat()}", f"{d:%m.%d}") for d in (yesterday - timedelta(days=i) for i in range(days))]

    def day_rec(aid, key):
        return (daily.get(aid) or {}).get(key[2:])
    return Summary(yesterday, [_section(f"상세 — 일별 판매 (최근 {days}일 · 최신이 왼쪽 · 관리 상품만)",
                                        cols, day_rec, labels)])
