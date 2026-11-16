"""③ 노출순위 '재는 날' — 체험단 10일 매일 · 나머지는 계정 3묶음이 하루씩 돌아가며(3일 간격) (D-257).

소유자 2026-11-16 "노출 순위 검색을 체험단은 시작일로부터 10일간 노출 순위를 검색하고, 나머지는 3일간격으로 안분해서
진행해줘 … 계정별로 안분해서 노출순위를 검색하도록 해줘" → 방법안(`docs/plans/rank-load-split-plan-2026-11-16.md`) 추천대로 승인.

칸(사업자·상품·키워드·날짜)의 **날짜** 기준(실행 날짜 아님 — 보충·날짜 지정도 같은 규칙)으로, 아래 중 하나면 그날 잰다.
  ① 새 규칙 시작일 전 날짜  ② 체험단 시작일 ≤ 날짜 ≤ 시작일+9일  ③ 순위 기록이 한 번도 없는 키워드
  ④ 그 계정 묶음의 차례 = (날짜 − 시작일).일수 mod 3
계정(사업자 시트 · 열쇠 = 첫 계정ID, 없으면 시트 이름) → 묶음은 숨긴 시트 `_순위묶음`에 한 번 고정(옮기지 않음).
새 계정 = 키워드 합이 가장 적은 묶음 · 사라진 계정 = 줄 지움 · 자동 다시 나누기 없음.
안 재는 칸 = 빈 칸 + 옅은 회색(값 없는 칸만) — ③ 대상·빈 칸 집계·재시도·지난 칸 보충·데이터점검에서 빠진다.
"""
from __future__ import annotations

from datetime import date, timedelta

from .workbook_common import _COL_KW, _RANKGRP_SHEET, _norm, _parse_date

GROUPS = 3                      # 묶음 수 = 간격 일수(소유자 '3일간격')
PROMO_DAYS = 10                 # 체험단 시작일 포함 매일 재는 날 수(소유자 '시작일로부터 10일간')
NAMES = ("가", "나", "다")       # 묶음 이름(로그·숨긴 시트)
REST_RGB = "F2F2F2"             # 안 재는 칸 배경(옅은 회색 · 방법안 2-1)
_CACHE = "_rank_plan_cache"     # 워크북 객체에 붙이는 읽기 캐시(서식이 칸마다 묻기 때문 · refresh 가 갈아 끼움)


class RankPlan:
    """숨긴 시트 `_순위묶음` 내용 — start = 새 규칙 시작일(없으면 아직 배정 전 = 매일) · groups = {열쇠: 묶음 0~2}."""

    def __init__(self, start: date | None = None, groups: dict | None = None, names: dict | None = None,
                 assigned: dict | None = None):
        self.start = start
        self.groups: dict[str, int] = dict(groups or {})
        self.names: dict[str, str] = dict(names or {})        # 열쇠 → 사업자 시트 이름(보기용)
        self.assigned: dict[str, str] = dict(assigned or {})  # 열쇠 → 배정일 ISO(보기용)

    def group_on(self, day: date) -> int | None:
        """그날 차례인 묶음(시작일 전·배정 전 = None)."""
        if self.start is None or day is None or day < self.start:
            return None
        return (day - self.start).days % GROUPS


def account_key(wb, biz: str) -> str:
    """계정 열쇠 = 그 사업자 시트의 첫 계정ID(사업자 이름이 바뀌어도 같은 묶음) · 없으면 시트 이름."""
    return _norm(wb.account_id_of(biz)) or _norm(biz)


def _read(wb) -> RankPlan:
    if _RANKGRP_SHEET not in wb.wb.sheetnames:
        return RankPlan()
    ws = wb.wb[_RANKGRP_SHEET]
    plan = RankPlan(start=_parse_date(ws.cell(1, 2).value))
    for r in range(3, ws.max_row + 1):
        key, grp = _norm(ws.cell(r, 2).value), _norm(ws.cell(r, 3).value)
        if key and grp in NAMES:
            plan.groups[key] = NAMES.index(grp)
            plan.names[key] = _norm(ws.cell(r, 1).value)
            plan.assigned[key] = _norm(ws.cell(r, 4).value)
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
    for c, h in enumerate(("사업자", "계정ID", "묶음", "배정일"), 1):
        ws.cell(2, c, h)
    for i, key in enumerate(sorted(plan.groups, key=lambda k: (plan.groups[k], plan.names.get(k, ""), k)), 3):
        ws.cell(i, 1, plan.names.get(key, ""))
        ws.cell(i, 2, key)
        ws.cell(i, 3, NAMES[plan.groups[key]])
        ws.cell(i, 4, plan.assigned.get(key, ""))
    setattr(wb, _CACHE, plan)


def _rank_keyword_count(wb, biz: str) -> int:
    """그 계정의 순위 대상 키워드 수(판매중지 등 제외 · VID 있는 상품만 · 묶음 무게)."""
    return sum(len(wb.product_keywords(biz, p)) for p in wb.products_of(biz)
               if not wb.rank_suppressed(biz, p) and wb.sibling_vids(biz, p))


def assign(weights: dict[str, int], groups: dict[str, int]) -> dict[str, int]:
    """기존 배정은 그대로 두고, 새 열쇠만 무게 큰 것부터 지금 합이 가장 적은 묶음에(동률 = 앞 묶음 · 이름 순)."""
    out = {k: g for k, g in groups.items() if k in weights}
    loads = [0] * GROUPS
    for k, g in out.items():
        loads[g] += weights[k]
    for k in sorted((k for k in weights if k not in out), key=lambda k: (-weights[k], k)):
        g = loads.index(min(loads))
        out[k] = g
        loads[g] += weights[k]
    return out


def refresh_groups(wb, today: date, log=None) -> RankPlan:
    """③ 시작 때 — 시작일(처음이면 오늘)·새 계정 배정·사라진 계정 줄 지움 → 숨긴 시트에 저장 · 로그 한 줄."""
    log = log or (lambda m: None)
    plan = _read(wb)
    weights: dict[str, int] = {}
    names: dict[str, str] = {}
    for biz in wb.account_sheets():
        key = account_key(wb, biz)
        weights[key] = weights.get(key, 0) + _rank_keyword_count(wb, biz)
        names[key] = biz
    new = [k for k in weights if k not in plan.groups]
    groups = assign(weights, plan.groups)
    start = plan.start or today
    assigned = {k: (plan.assigned.get(k) or today.isoformat()) for k in groups}
    fresh = RankPlan(start, groups, names, assigned)
    _write(wb, fresh)
    loads = [sum(weights[k] for k, g in groups.items() if g == i) for i in range(GROUPS)]
    g = fresh.group_on(today)
    head = f"오늘({today.month:02d}.{today.day:02d}) = {NAMES[g]} 묶음" if g is not None else "오늘은 시작 전(전부 잼)"
    loads_txt = " · ".join(f"{NAMES[i]} {loads[i]}" for i in range(GROUPS))
    new_txt = (" · 새 계정 " + ", ".join(f"{names[k]}→{NAMES[groups[k]]}" for k in new)) if new and plan.groups else ""
    first = f" · 처음 배정(시작일 {start.isoformat()})" if not plan.groups else ""
    log(f"  [순위 묶음] {head} · 묶음별 키워드 {loads_txt}{first}{new_txt} · 체험단 시작 {PROMO_DAYS}일·새 키워드는 매일")
    return fresh


def promo_start(wb, biz: str, product: str) -> date | None:
    """체험단 시작일 = 직원 입력 마케팅 시작일 우선 · 없으면 체험단 시트 자동값(D-086·D-122) — D-121 배경과 같은 기준."""
    return _parse_date(wb.marketing_of(biz, product)[0] or wb.promo_start_of(biz, product))


def ever_measured(wb, biz: str, product: str, keyword: str) -> bool:
    return any(wb.is_rank_filled(biz, product, keyword, lbl) for lbl in wb._date_col.get(biz, {}))


def is_due(plan: RankPlan, group: int | None, day: date | None, promo: date | None, measured: bool) -> bool:
    """그날 재는가(순수 판정) — 시작일 전·체험단 10일·첫 측정 전·배정 전 = 잼 · 그 밖 = 묶음 차례만."""
    if day is None:
        return True
    turn = plan.group_on(day)
    if turn is None:
        return True
    if promo and promo <= day <= promo + timedelta(days=PROMO_DAYS - 1):
        return True
    if not measured or group is None:
        return True
    return turn == group


def due_keywords(wb, biz: str, product: str, keywords: list, date_label: str) -> list:
    """keywords 중 그 날짜 칸을 재는 것만(순서 유지)."""
    plan = load_plan(wb)
    day = _parse_date(date_label)
    if not keywords or day is None or plan.group_on(day) is None:
        return list(keywords)
    group, promo = plan.groups.get(account_key(wb, biz)), promo_start(wb, biz, product)
    return [kw for kw in keywords if is_due(plan, group, day, promo, ever_measured(wb, biz, product, kw))]


def rest_cells(wb, ws, biz: str, product: str, rows) -> set[tuple[int, int]]:
    """회색으로 칠할 (행, 열) — 순위 대상 상품의 키워드 줄 중 **비어 있고** 그 날짜가 안 재는 날인 칸."""
    plan = load_plan(wb)
    if plan.start is None or wb.rank_suppressed(biz, product) or not wb.sibling_vids(biz, product):
        return set()
    group, promo = plan.groups.get(account_key(wb, biz)), promo_start(wb, biz, product)
    cols = [(c, _parse_date(lbl)) for lbl, c in wb._date_col.get(biz, {}).items()]
    out: set[tuple[int, int]] = set()
    for r in rows:
        kw = _norm(ws.cell(r, _COL_KW).value)
        if not kw:
            continue
        vals = {c: ws.cell(r, c).value for c, _d in cols}
        measured = any(v not in (None, "", "-") for v in vals.values())
        for c, d in cols:
            if vals[c] in (None, "", "-") and not is_due(plan, group, d, promo, measured):
                out.add((r, c))
    return out


def any_due(wb, biz: str, product: str, date_label: str) -> bool:
    """그 상품의 키워드 중 하나라도 그 날짜에 재는가(데이터점검용)."""
    kws = wb.product_keywords(biz, product)
    return bool(due_keywords(wb, biz, product, kws, date_label)) if kws else True


__all__ = ["GROUPS", "PROMO_DAYS", "NAMES", "REST_RGB", "RankPlan", "account_key", "assign", "refresh_groups",
           "load_plan", "is_due", "due_keywords", "rest_cells", "any_due", "promo_start", "ever_measured"]
