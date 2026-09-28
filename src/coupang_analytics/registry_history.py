"""셀독등록원장 — 과거 시점 복원(as_of)·관리기간(managed_between)·무결성 점검. SSOT=designs/LEDGER_REGISTRY.md §7·§8.

현재 원장에서 효력일이 기준일보다 늦은 이력을 **최신부터 거꾸로 되돌려** 그날의 원장을 만든다. 되돌릴 때 현재 값이
그 이력의 '변경값'과 달라야 할 이유가 없으므로, 다르면 손수정·누락으로 보고 무결성 오류로 알린다.
"""
from __future__ import annotations

import copy

from .registry_core import Registry, RegistryIntegrityError, _order, _replay_status, _row_status
from .registry_model import (HISTORY_SHEETS, ITEM_ACCT_ID, ITEM_PROD_NAME, K_CONFIRMED, K_EDIT, K_INIT,
                             K_NEW_ACCT, K_NEW_PROD, K_RESUME, K_STOP, SHEET_ACCT, SHEET_GROWTH, SHEET_PROD,
                             HistRow)


# ── 과거 시점 복원·무결성 ────────────────────────────────────────
def _undo_acct_edit(rows: dict, h: HistRow, errors: list) -> None:
    for k, r in rows.items():
        if k[0] == h.account_id:
            if r.acct.get(h.item, "") != h.new:
                errors.append(f"계정이력 #{h.no} {h.account_id} {h.item}: 원장 값 '{r.acct.get(h.item)}' ≠ 이력 '{h.new}'")
            r.acct[h.item] = h.old


def _undo_growth_edit(rows: dict, h: HistRow, errors: list) -> None:
    r = rows.get((h.account_id, h.product))
    if r is None or r.growth.get(h.item, "") != h.new:
        errors.append(f"그로스이력 #{h.no} {h.account_id}/{h.product} {h.item}: 원장과 불일치")
    else:
        r.growth[h.item] = h.old


def _undo_new_product(rows: dict, h: HistRow, errors: list) -> None:
    if rows.pop((h.account_id, h.product), None) is None:
        errors.append(f"상품이력 #{h.no} {h.account_id}/{h.product}: 원장에 줄 없음")


def _undo_new_account(rows: dict, h: HistRow, errors: list) -> None:
    rows.pop((h.account_id, ""), None)
    if any(k[0] == h.account_id for k in rows):
        errors.append(f"계정이력 #{h.no} {h.account_id}: 계정 등록 이전인데 줄이 남음")


_UNDO = {
    (SHEET_ACCT, K_EDIT): _undo_acct_edit,
    (SHEET_GROWTH, K_EDIT): _undo_growth_edit,
    (SHEET_PROD, K_INIT): _undo_new_product,
    (SHEET_PROD, K_NEW_PROD): _undo_new_product,
    (SHEET_ACCT, K_INIT): _undo_new_account,
    (SHEET_ACCT, K_NEW_ACCT): _undo_new_account,
}


def _undo(rows: dict, h: HistRow, errors: list) -> None:
    """이력 1줄을 되돌린다. 되돌리기 전 현재 값이 그 이력의 '변경값'과 같아야 한다(아니면 오류 수집).
    관리중단·재개·보류·반려는 원장 값을 바꾸지 않으므로(상태는 이력에서 계산) 되돌릴 것이 없다."""
    fn = _UNDO.get((h.sheet, h.kind))
    if fn is not None:
        fn(rows, h, errors)
    elif h.kind == K_CONFIRMED:
        _undo_rename(rows, h)


def _undo_rename(rows: dict, h: HistRow) -> None:
    if h.item == ITEM_PROD_NAME and (h.account_id, h.new) in rows:
        r = rows.pop((h.account_id, h.new))
        r.product = h.old
        rows[r.key] = r
    elif h.item == ITEM_ACCT_ID:
        for k in [k for k in rows if k[0] == h.new]:
            r = rows.pop(k)
            r.account_id = h.old
            rows[r.key] = r


def _rewind(reg: Registry, at: str) -> tuple[dict, list]:
    rows = {k: copy.deepcopy(r) for k, r in reg.rows.items()}
    errors: list[str] = []
    for h in sorted(reg.history, key=_order, reverse=True):
        if h.eff > at:
            _undo(rows, h, errors)
    return rows, errors


def as_of(reg: Registry, at: str) -> dict:
    """그 날짜(YYYY-MM-DD, 그날 끝 기준)의 원장을 되살린다 → {(계정아이디, 상품명): 항목 dict}.

    그로스 재고·쿠팡확인은 이력이 없어 복원 대상이 아니다(결과에 포함하지 않음).
    """
    rows, errors = _rewind(reg, at)
    if errors:
        raise RegistryIntegrityError("과거 복원 중 원장·이력 불일치: " + " / ".join(errors[:5]))
    st = _replay_status(reg.history, at)
    out = {}
    for k, r in rows.items():
        status, stop = _row_status(st, *k)
        out[k] = {"계정아이디": k[0], "상품명": k[1], **r.acct, **r.growth, "관리상태": status, "중단일": stop}
    return out


def managed_between(reg: Registry, start: str, end: str) -> list[str]:
    """기간(YYYY-MM-DD~YYYY-MM-DD)에 **하루라도 관리중이던 계정**(현재 관리중단 포함). 계정아이디 변경은 이어짐."""
    opened: dict[str, str] = {}
    spans: dict[str, list] = {}
    for h in sorted((h for h in reg.history if h.sheet == SHEET_ACCT), key=_order):
        aid = h.account_id
        if h.kind == K_CONFIRMED and h.item == ITEM_ACCT_ID:
            if h.old in opened:
                opened[h.new] = opened.pop(h.old)
            spans[h.new] = spans.pop(h.old, []) + spans.get(h.new, [])
        elif h.kind in (K_INIT, K_NEW_ACCT, K_RESUME):
            opened.setdefault(aid, h.eff)
        elif h.kind == K_STOP and aid in opened:
            spans.setdefault(aid, []).append((opened.pop(aid), h.eff))
    for aid, s in opened.items():
        spans.setdefault(aid, []).append((s, "9999-12-31"))
    return sorted(a for a, iv in spans.items() if any(s <= end and e >= start for s, e in iv))


def check_integrity(reg: Registry) -> None:
    """① 시트별 이력 번호 1..n 연속 ② 이력 전체를 되돌리면 빈 원장(= 원장 값이 이력과 일치). 어긋나면 예외."""
    problems = []
    for sheet in HISTORY_SHEETS:
        nos = sorted(h.no for h in reg.history if h.sheet == sheet)
        if nos != list(range(1, len(nos) + 1)):
            missing = sorted(set(range(1, (nos[-1] if nos else 0) + 1)) - set(nos))
            problems.append(f"{sheet} 번호 누락/중복(누락 {missing[:5]})")
    rows, errors = _rewind(reg, "0000-00-00")
    problems += errors[:5]
    if rows:
        problems.append(f"이력에 없는 원장 줄 {len(rows)}개(예 {next(iter(rows))})")
    if problems:
        raise RegistryIntegrityError("원장 무결성 오류 — 동기화 중단: " + " / ".join(problems))
