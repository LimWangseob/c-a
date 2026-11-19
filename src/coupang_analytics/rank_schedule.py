"""③ 노출순위 '재는 날' — 체험단 10일 매일 · 나머지는 계정 2묶음이 하루씩 번갈아(격일) (D-362 · 처음 D-257 3일 간격).

소유자 2026-11-16 "노출 순위 검색을 체험단은 시작일로부터 10일간 노출 순위를 검색하고, 나머지는 3일간격으로 안분해서
진행해줘 … 계정별로 안분해서 노출순위를 검색하도록 해줘" → 방법안(`docs/plans/rank-load-split-plan-2026-11-16.md`) 추천대로 승인.
소유자 2026-11-19 "전에 3일간격에서 격일 간격으로 노출 순위 조사, 체험단 건은 제외함"(D-362) → 나머지 = 2묶음 격일.

칸(사업자·상품·키워드·날짜)의 **날짜** 기준(실행 날짜 아님 — 보충·날짜 지정도 같은 규칙)으로, 아래 중 하나면 그날 잰다.
칸 날짜 = 판매 기준일(D-368 · 실행일 전날) — 체험단 = 시작일 칸부터 10칸(측정 = 시작일 다음 날 01:30 부터 10번 D-369 ①) ·
옛 기준 칸을 하루 당길 때 `_순위묶음` 시작일도 같이 당겨(date_basis) 같은 실행일 = 같은 묶음.
  ① 묶음 규칙 시작일 전 날짜  ② 체험단 시작일 ≤ 날짜 ≤ 시작일+9일  ③ 순위 기록이 한 번도 없는 키워드
  ④ 그 계정 묶음의 차례 — 격일 시작일부터 = (날짜 − 격일 시작일).일수 mod 2 · 그 전(3일 간격 기간) = (날짜 − 시작일) mod 3
**두 기간 보존**(통제 세션 11-19): 3일 간격으로 잰 지난 칸은 그때 규칙(옛 묶음)으로 계속 판정해 회색이 그대로 남는다.
숨긴 시트 `_순위묶음` = A1·B1 시작일(3일 간격) · C열 옛 묶음(가·나·다) — **옛 코드가 읽는 칸은 그대로 둠**(되돌려도 안전) ·
C1·D1 격일 시작일 · E열 격일 묶음(가·나) · F열 격일 배정일. 계정 열쇠 = 첫 계정ID(없으면 시트 이름) · 묶음은 한 번 고정.
새 계정 = 키워드 합이 가장 적은 묶음 · 사라진 계정 = 줄 지움 · 자동 다시 나누기 없음.
안 재는 칸 = 빈 칸 + 옅은 회색(값 없는 칸만) — ③ 대상·빈 칸 집계·재시도·지난 칸 보충·데이터점검에서 빠진다.
"""
from __future__ import annotations

from datetime import date, timedelta

from .workbook_common import _COL_KW, _RANKGRP_SHEET, _norm, _parse_date

GROUPS = 2                      # 묶음 수 = 간격 일수(소유자 '격일' D-362)
PROMO_DAYS = 10                 # 체험단 시작일 포함 매일 재는 날 수(소유자 '시작일로부터 10일간' · 바꿀 곳은 여기 하나)
NAMES = ("가", "나")             # 격일 묶음 이름(로그·숨긴 시트 E열)
OLD_GROUPS = 3                  # 3일 간격 기간(D-257 · 격일 시작일 전 날짜 판정에만)
OLD_NAMES = ("가", "나", "다")   # 3일 간격 묶음 이름(숨긴 시트 C열 · 옛 코드와 같은 칸)
REST_RGB = "F2F2F2"             # 안 재는 칸 배경(옅은 회색 · 방법안 2-1)
_CACHE = "_rank_plan_cache"     # 워크북 객체에 붙이는 읽기 캐시(서식이 칸마다 묻기 때문 · refresh 가 갈아 끼움)


class RankPlan:
    """숨긴 시트 `_순위묶음` 내용 — start·groups = 3일 간격 기간(옛 · {열쇠: 0~2}) · start2·groups2 = 격일({열쇠: 0~1}).
    둘 다 없으면 아직 배정 전 = 매일."""

    def __init__(self, start: date | None = None, groups: dict | None = None, names: dict | None = None,
                 assigned: dict | None = None, start2: date | None = None, groups2: dict | None = None,
                 assigned2: dict | None = None):
        self.start, self.start2 = start, start2
        self.groups: dict[str, int] = dict(groups or {})
        self.groups2: dict[str, int] = dict(groups2 or {})
        self.names: dict[str, str] = dict(names or {})          # 열쇠 → 사업자 시트 이름(보기용)
        self.assigned: dict[str, str] = dict(assigned or {})    # 열쇠 → 3일 간격 배정일 ISO(보기용)
        self.assigned2: dict[str, str] = dict(assigned2 or {})  # 열쇠 → 격일 배정일 ISO(보기용)

    def turn(self, day: date | None) -> tuple[int, int] | None:
        """그날 (기간 묶음 수, 차례인 묶음) — 격일 시작일부터 = (2, …) · 그 전 3일 간격 기간 = (3, …) · 그 밖 = None(매일)."""
        if day is None:
            return None
        if self.start2 is not None and day >= self.start2:
            return GROUPS, (day - self.start2).days % GROUPS
        if self.start is not None and day >= self.start:
            return OLD_GROUPS, (day - self.start).days % OLD_GROUPS
        return None

    def group_of(self, key: str, period: int) -> int | None:
        return (self.groups2 if period == GROUPS else self.groups).get(key)


def account_key(wb, biz: str) -> str:
    """계정 열쇠 = 그 사업자 시트의 첫 계정ID(사업자 이름이 바뀌어도 같은 묶음) · 없으면 시트 이름."""
    return _norm(wb.account_id_of(biz)) or _norm(biz)


def _read(wb) -> RankPlan:
    if _RANKGRP_SHEET not in wb.wb.sheetnames:
        return RankPlan()
    ws = wb.wb[_RANKGRP_SHEET]
    plan = RankPlan(start=_parse_date(ws.cell(1, 2).value), start2=_parse_date(ws.cell(1, 4).value))
    for r in range(3, ws.max_row + 1):
        key = _norm(ws.cell(r, 2).value)
        if not key:
            continue
        old, new = _norm(ws.cell(r, 3).value), _norm(ws.cell(r, 5).value)
        if old in OLD_NAMES:
            plan.groups[key] = OLD_NAMES.index(old)
            plan.assigned[key] = _norm(ws.cell(r, 4).value)
        if new in NAMES:
            plan.groups2[key] = NAMES.index(new)
            plan.assigned2[key] = _norm(ws.cell(r, 6).value)
        if old in OLD_NAMES or new in NAMES:
            plan.names[key] = _norm(ws.cell(r, 1).value)
    return plan


def load_plan(wb) -> RankPlan:
    """읽기(캐시) — 같은 워크북 객체에서는 refresh_groups 가 새로 쓸 때까지 한 번만 읽는다."""
    plan = getattr(wb, _CACHE, None)
    if plan is None:
        plan = _read(wb)
        setattr(wb, _CACHE, plan)
    return plan


def _write(wb, plan: RankPlan) -> None:
    if _RANKGRP_SHEET in wb.wb.sheetnames:
        del wb.wb[_RANKGRP_SHEET]
    ws = wb.wb.create_sheet(_RANKGRP_SHEET)
    ws.sheet_state = "hidden"
    ws.cell(1, 1, "시작일")
    ws.cell(1, 2, plan.start.isoformat() if plan.start else None)
    ws.cell(1, 3, "격일 시작일")
    ws.cell(1, 4, plan.start2.isoformat() if plan.start2 else None)
    for c, h in enumerate(("사업자", "계정ID", "묶음", "배정일", "격일 묶음", "격일 배정일"), 1):
        ws.cell(2, c, h)
    keys = sorted(set(plan.groups) | set(plan.groups2),
                  key=lambda k: (plan.groups2.get(k, GROUPS), plan.names.get(k, ""), k))
    for i, key in enumerate(keys, 3):
        ws.cell(i, 1, plan.names.get(key, ""))
        ws.cell(i, 2, key)
        if key in plan.groups:
            ws.cell(i, 3, OLD_NAMES[plan.groups[key]])
            ws.cell(i, 4, plan.assigned.get(key, ""))
        if key in plan.groups2:
            ws.cell(i, 5, NAMES[plan.groups2[key]])
            ws.cell(i, 6, plan.assigned2.get(key, ""))
    setattr(wb, _CACHE, plan)


def _rank_keyword_count(wb, biz: str) -> int:
    """그 계정의 순위 대상 키워드 수(판매중지 등 제외 · VID 있는 상품만 · 묶음 무게)."""
    return sum(len(wb.product_keywords(biz, p)) for p in wb.products_of(biz)
               if not wb.rank_suppressed(biz, p) and wb.sibling_vids(biz, p))


def assign(weights: dict[str, int], groups: dict[str, int], n: int = GROUPS) -> dict[str, int]:
    """기존 배정은 그대로 두고, 새 열쇠만 무게 큰 것부터 지금 합이 가장 적은 묶음에(동률 = 앞 묶음 · 이름 순). n = 묶음 수."""
    out = {k: g for k, g in groups.items() if k in weights}
    loads = [0] * n
    for k, g in out.items():
        loads[g] += weights[k]
    for k in sorted((k for k in weights if k not in out), key=lambda k: (-weights[k], k)):
        g = loads.index(min(loads))
        out[k] = g
        loads[g] += weights[k]
    return out


def refresh_groups(wb, today: date, log=None) -> RankPlan:
    """③ 시작 때 — 격일 시작일(처음이면 오늘)·새 계정 격일 배정·사라진 계정 줄 지움 → 숨긴 시트에 저장 · 로그 한 줄.
    3일 간격 기간(시작일·옛 묶음)은 지난 칸 판정용으로 그대로 둠(새 계정을 옛 기간에 넣지 않음 · 사라진 계정만 뺌)."""
    log = log or (lambda m: None)
    plan = _read(wb)
    weights: dict[str, int] = {}
    names: dict[str, str] = {}
    for biz in wb.account_sheets():
        key = account_key(wb, biz)
        weights[key] = weights.get(key, 0) + _rank_keyword_count(wb, biz)
        names[key] = biz
    new = [k for k in weights if k not in plan.groups2]
    groups2 = assign(weights, plan.groups2)
    start2 = plan.start2 or today
    old = {k: g for k, g in plan.groups.items() if k in weights}
    fresh = RankPlan(plan.start, old, names, {k: plan.assigned.get(k, "") for k in old}, start2, groups2,
                     {k: (plan.assigned2.get(k) or today.isoformat()) for k in groups2})
    _write(wb, fresh)
    log(_refresh_log(fresh, weights, new, today, first=not plan.groups2))
    return fresh


def _refresh_log(fresh: RankPlan, weights: dict[str, int], new: list[str], today: date, first: bool) -> str:
    """refresh_groups 로그 한 줄 — 오늘 묶음 · 묶음별 키워드 수 · 처음 배정 / 새 계정."""
    groups2, names = fresh.groups2, fresh.names
    loads = [sum(weights[k] for k, g in groups2.items() if g == i) for i in range(GROUPS)]
    t = fresh.turn(today)
    head = (f"이번 칸({today.month:02d}.{today.day:02d}) = {NAMES[t[1]]} 묶음(격일)" if t and t[0] == GROUPS
            else "이번 칸은 격일 시작 전(전부 잼)")   # today = 이 실행의 칸 날짜(실행일 전날 D-368)
    loads_txt = " · ".join(f"{NAMES[i]} {loads[i]}" for i in range(GROUPS))
    new_txt = (" · 새 계정 " + ", ".join(f"{names[k]}→{NAMES[groups2[k]]}" for k in new)) if new and not first else ""
    first_txt = f" · 처음 배정(격일 시작일 {fresh.start2.isoformat()})" if first and fresh.start2 else ""
    return f"  [순위 묶음] {head} · 묶음별 키워드 {loads_txt}{first_txt}{new_txt} · 체험단 시작 {PROMO_DAYS}일·새 키워드는 매일"


def promo_start(wb, biz: str, product: str) -> date | None:
    """체험단 시작일 = 직원 입력 마케팅 시작일 우선 · 없으면 체험단 시트 자동값(D-086·D-122) — D-121 배경과 같은 기준."""
    return _parse_date(wb.marketing_of(biz, product)[0] or wb.promo_start_of(biz, product))


def ever_measured(wb, biz: str, product: str, keyword: str) -> bool:
    return any(wb.is_rank_filled(biz, product, keyword, lbl) for lbl in wb._date_col.get(biz, {}))


def is_due(plan: RankPlan, key: str, day: date | None, promo: date | None, measured: bool) -> bool:
    """그날 재는가(순수 판정) — 규칙 시작 전·체험단 10일·첫 측정 전·그 기간 배정 전 = 잼 · 그 밖 = 그 기간 묶음 차례만."""
    turn = plan.turn(day)
    if turn is None or day is None:
        return True
    if promo and promo <= day <= promo + timedelta(days=PROMO_DAYS - 1):
        return True
    group = plan.group_of(key, turn[0])
    if not measured or group is None:
        return True
    return turn[1] == group


def due_keywords(wb, biz: str, product: str, keywords: list, date_label: str) -> list:
    """keywords 중 그 날짜 칸을 재는 것만(순서 유지)."""
    plan = load_plan(wb)
    day = _parse_date(date_label)
    if not keywords or plan.turn(day) is None:
        return list(keywords)
    key, promo = account_key(wb, biz), promo_start(wb, biz, product)
    return [kw for kw in keywords if is_due(plan, key, day, promo, ever_measured(wb, biz, product, kw))]


def rest_cells(wb, ws, biz: str, product: str, rows) -> set[tuple[int, int]]:
    """회색으로 칠할 (행, 열) — 순위 대상 상품의 키워드 줄 중 **비어 있고** 그 날짜가 안 재는 날인 칸."""
    plan = load_plan(wb)
    if (plan.start is None and plan.start2 is None) or wb.rank_suppressed(biz, product) \
            or not wb.sibling_vids(biz, product):
        return set()
    key, promo = account_key(wb, biz), promo_start(wb, biz, product)
    cols = [(c, _parse_date(lbl)) for lbl, c in wb._date_col.get(biz, {}).items()]
    out: set[tuple[int, int]] = set()
    for r in rows:
        kw = _norm(ws.cell(r, _COL_KW).value)
        if not kw:
            continue
        vals = {c: ws.cell(r, c).value for c, _d in cols}
        measured = any(v not in (None, "", "-") for v in vals.values())
        for c, d in cols:
            if vals[c] in (None, "", "-") and not is_due(plan, key, d, promo, measured):
                out.add((r, c))
    return out


def any_due(wb, biz: str, product: str, date_label: str) -> bool:
    """그 상품의 키워드 중 하나라도 그 날짜에 재는가(데이터점검용)."""
    kws = wb.product_keywords(biz, product)
    return bool(due_keywords(wb, biz, product, kws, date_label)) if kws else True


__all__ = ["GROUPS", "PROMO_DAYS", "NAMES", "OLD_GROUPS", "OLD_NAMES", "REST_RGB", "RankPlan", "account_key", "assign",
           "refresh_groups", "load_plan", "is_due", "due_keywords", "rest_cells", "any_due", "promo_start",
           "ever_measured"]
