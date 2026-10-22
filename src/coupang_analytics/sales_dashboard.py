"""통합 판매현황 상단 대시보드 집계(순수 로직·오프라인) — SSOT=designs/SALES_SUMMARY.md §5-1(소유자 2026-10-21).

① 요약(전일·지난주·이번 달 누계·미수집 계정) ② 월별 ③ 주간(최근 8주) ④ 일별(최근 31일) ⑤ 계정 순위
(최근 1개월 누계·지난주·전주 대비 — 2026-10-21 2차: ⑥ 상품 열지도·글자 그래프 삭제·D-098 · 최근 1개월 D-110).
입력 = sales_summary.scope 로 **관리 상품만** 거른 저장(상세표와 같은 기준 → 합계 일치).
계정 하나의 기간 값 = 그 기간 일별 기록이 **모두 있으면 일별 합**, 아니면 쿠팡 기간 합계(조회기간이 정확히 같은 것),
둘 다 없으면 **미수집**(합계에서 빼고 개수로 표시). 증감 % = 두 기간 **모두 받은 계정끼리** 비교(빠진 계정이 증감을 왜곡 안 함).
'지난달 같은 기간' = 이번 달 1~N일 vs 지난달 1~N일(지난달이 짧으면 말일까지·일별 기록으로).
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from .sales_summary import FIRST_DAY, WEEKS, _rows_of, month_key, week_monday

DAYS = 31        # ④ 일별 막대 칸 수
RECENT_DAYS = 30  # ⑤ 계정 순위 '최근 1개월' = 어제까지 30일(소유자 2026-10-22·D-110)


@dataclass
class Point:
    label: str
    qty: int
    amount: int
    missing: int = 0          # 그 기간 미수집 계정 수(= 전체 계정 수면 자료 없음 → 빈 칸)
    partial: bool = False     # 진행 중 기간(이번 달 누계)


@dataclass
class Kpi:
    title: str
    span: str                 # 'MM.DD~MM.DD'
    qty: int
    amount: int
    change: float | None      # 비율(0.123 = +12.3%) · None = 비교 불가
    basis: str                # 비교 기준 설명
    missing: int = 0
    missing_names: tuple = ()  # 미수집 계정 이름(사업자명·소유자 2026-10-21 '어느 계정인지 괄호로')


@dataclass
class AccountRank:
    aid: str
    label: str
    amount: int | None        # 최근 1개월 누계(None = 미수집)
    week: int | None          # 지난주(끝난 월~일)
    prev_week: int | None     # 그 전주
    change: float | None      # 지난주 vs 그 전주


@dataclass
class Dashboard:
    yesterday: date
    kpis: list
    missing_today: int        # 전일 미수집 계정 수
    accounts_total: int
    months: list
    weeks: list
    days: list
    accounts: list            # 최근 1개월 누계 금액 순(미수집 = 맨 뒤)
    missing_today_names: tuple = ()   # 전일 미수집 계정 이름
    month_kpis: tuple = ()    # ① 월별 누계(시작월~이번 달·전월 대비 — 진행 중 달은 지난달 같은 기간 대비·D-105)
    rank_span: tuple = ()     # ⑤ 최근 1개월 (시작, 끝)


# ── 기간 ──────────────────────────────────────────────────────
def last_full_week(yesterday: date) -> date:
    """끝난 마지막 주(월~일)의 월요일 — 어제가 일요일이면 이번 주."""
    return week_monday(yesterday + timedelta(days=1)) - timedelta(weeks=1)


def prev_month_same(yesterday: date) -> tuple[date, date]:
    """지난달 같은 기간(1일 ~ 어제와 같은 날짜, 지난달이 짧으면 말일)."""
    first = (yesterday.replace(day=1) - timedelta(days=1)).replace(day=1)
    last = calendar.monthrange(first.year, first.month)[1]
    return first, first.replace(day=min(yesterday.day, last))


def recent_month(yesterday: date) -> tuple[date, date]:
    """⑤ 최근 1개월(어제까지 RECENT_DAYS 일) — 월초에도 한 달치가 보이도록(이번 달 누계 대신·D-110)."""
    return yesterday - timedelta(days=RECENT_DAYS - 1), yesterday


def _month_spans(yesterday: date, first: date) -> list[tuple[str, str, date, date, bool]]:
    out = []
    y, m = first.year, first.month
    while (y, m) <= (yesterday.year, yesterday.month):
        s = date(y, m, 1)
        end = date(y, m, calendar.monthrange(y, m)[1])
        label = f"{m}월" if y == yesterday.year else f"{y % 100:02d}.{m}월"
        out.append((month_key(s), label, s, min(end, yesterday), end > yesterday))
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    return out


def short_name(label: str) -> str:
    """'사업자 (계정ID)' → '사업자'(미수집 이름 표시용)."""
    return label.rsplit(" (", 1)[0] if label.endswith(")") and " (" in label else label


def missing_names(aids, labels, vals) -> tuple:
    """값 None(미수집)인 계정의 사업자명 — 등장 순서·중복 없이."""
    return tuple(dict.fromkeys(short_name(labels[a]) for a, v in zip(aids, vals) if v is None))


def _span(s: date, e: date) -> str:
    return f"{s:%m.%d}~{e:%m.%d}"


# ── 계정 하나의 기간 값 ────────────────────────────────────────
def range_rows(day_recs: dict, per_recs: dict, s: date, e: date, key: str | None = None) -> dict | None:
    """{(상품, 구분): (수량, 금액)} — 일별이 모두 있으면 일별 합 · 아니면 기간 합계(조회기간 = [s, e]) · 없으면 None."""
    recs = [day_recs.get((s + timedelta(days=i)).isoformat()) for i in range((e - s).days + 1)]
    if all(r is not None for r in recs):
        out: dict = {}
        for r in recs:
            for k, (q, a) in (_rows_of(r) or {}).items():
                q0, a0 = out.get(k, (0, 0))
                out[k] = (q0 + q, a0 + a)
        return out
    p = per_recs.get(key) if key else None
    if p and list(p.get("조회기간") or []) == [s.isoformat(), e.isoformat()]:
        return _rows_of(p)
    return None


def _total(rows: dict | None) -> tuple[int, int] | None:
    if rows is None:
        return None
    return sum(q for q, _a in rows.values()), sum(a for _q, a in rows.values())


def _point(label: str, vals: list, partial: bool = False) -> Point:
    have = [v for v in vals if v is not None]
    return Point(label, sum(q for q, _a in have), sum(a for _q, a in have), len(vals) - len(have), partial)


def change(cur: list, prev: list) -> float | None:
    """두 기간 모두 받은 계정끼리 금액 증감 비율 — 짝이 없거나 이전 0 이면 None."""
    pairs = [(c[1], p[1]) for c, p in zip(cur, prev) if c is not None and p is not None]
    base = sum(p for _c, p in pairs)
    return (sum(c for c, _p in pairs) - base) / base if pairs and base else None


# ── 대시보드 ──────────────────────────────────────────────────
def build(daily: dict, period_recs: dict, labels: dict, yesterday: date, weeks: int = WEEKS,
          first: date = FIRST_DAY, days: int = DAYS) -> Dashboard:
    """daily·period_recs = scope 로 거른 저장 · labels = {계정ID: 표시명}(결과 파일 계정)."""
    aids = sorted(labels, key=lambda a: labels[a])

    def acct(aid, s, e, key=None):
        return range_rows(daily.get(aid) or {}, period_recs.get(aid) or {}, s, e, key)

    def per_acct(s, e, key=None):
        return [_total(acct(aid, s, e, key)) for aid in aids]

    lw = last_full_week(yesterday)
    wk = [lw - timedelta(weeks=i) for i in range(weeks)][::-1]           # 오래된 주 → 최신 주
    wk_key = {m: f"W:{m.isoformat()}" for m in wk + [lw - timedelta(weeks=1)]}
    m_s, (pm_s, pm_e) = yesterday.replace(day=1), prev_month_same(yesterday)
    day_v = per_acct(yesterday, yesterday)
    lw_v, pw_v = (per_acct(m, m + timedelta(days=6), wk_key[m]) for m in (lw, lw - timedelta(weeks=1)))
    mo_v, pm_v = per_acct(m_s, yesterday, month_key(m_s)), per_acct(pm_s, pm_e)
    rm = recent_month(yesterday)
    rm_v = per_acct(*rm)                                                 # 일별 합만(쿠팡 기간 합계 조회 없음)
    def kpi(title, s, e, cur, prev, basis):
        return _kpi(title, s, e, cur, prev, basis, missing_names(aids, labels, cur))
    kpis = [kpi("전일", yesterday, yesterday, day_v, None, ""),
            kpi("지난주(월~일)", lw, lw + timedelta(days=6), lw_v, pw_v,
                f"그 전주 {_span(lw - timedelta(weeks=1), lw - timedelta(days=1))} 대비"),
            kpi("이번 달 누계", m_s, yesterday, mo_v, pm_v, f"지난달 같은 기간 {_span(pm_s, pm_e)} 대비")]
    spans = _month_spans(yesterday, first)
    month_vals = [per_acct(s, e, k) for k, _lb, s, e, _part in spans]
    months = [_point(lb, v, part) for (_k, lb, _s, _e, part), v in zip(spans, month_vals)]
    week_pts = [_point(f"{m:%m.%d}", per_acct(m, m + timedelta(days=6), wk_key[m])) for m in wk]
    day_pts = [_point(f"{d:%m.%d}", per_acct(d, d)) for d in
               (yesterday - timedelta(days=i) for i in range(days - 1, -1, -1))]
    return Dashboard(yesterday, kpis, sum(v is None for v in day_v), len(aids), months, week_pts, day_pts,
                     _ranks(aids, labels, rm_v, lw_v, pw_v), missing_names(aids, labels, day_v),
                     tuple(_month_kpis(spans, month_vals, mo_v, pm_v, (pm_s, pm_e), kpi)), rm)


def _month_kpis(spans, vals, mo_v, pm_v, pm_span, kpi):
    """① 월별 누계 줄 — 끝난 달 = 전월(통째) 대비 · 진행 중 달 = 지난달 같은 기간 대비(이번 달 누계와 같은 값) ·
    시작월 = 비교 없음. 금액·수량·미수집 = 그 달 값(일별 다 있으면 일별 합, 아니면 쿠팡 기간 합계)."""
    for i, ((_k, label, s, e, partial), cur) in enumerate(zip(spans, vals)):
        if partial:
            yield kpi(f"{label} 누계", s, e, mo_v, pm_v, f"지난달 같은 기간 {_span(*pm_span)} 대비")
        elif i == 0:
            yield kpi(label, s, e, cur, None, "")
        else:
            ps, pe = spans[i - 1][2], spans[i - 1][3]
            yield kpi(label, s, e, cur, vals[i - 1], f"전월 {_span(ps, pe)} 대비")


def _kpi(title, s, e, cur, prev, basis, names=()) -> Kpi:
    p = _point("", cur)
    return Kpi(title, _span(s, e) if s != e else f"{s:%m.%d}", p.qty, p.amount,
               change(cur, prev) if prev is not None else None, basis, p.missing, names)


def _ranks(aids, labels, cur, week, prev_week) -> list:
    def amt(v):
        return v[1] if v is not None else None
    out = [AccountRank(aid, labels[aid], amt(c), amt(w), amt(p), change([w], [p]))
           for aid, c, w, p in zip(aids, cur, week, prev_week)]
    out.sort(key=lambda r: (r.amount is None, -(r.amount or 0), r.label))
    return out
