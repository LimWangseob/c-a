"""셀독등록원장 — 이름 변경(상품명·계정아이디) 보류·승인·반려. SSOT=designs/LEDGER_REGISTRY.md §6.

이름이 바뀌면 기계에는 '삭제 1 + 신규 1'로 보인다. 추측 병합은 다른 상품끼리 이력을 섞으므로 자동 병합하지 않고
'확인필요'로 보류 → 담당자가 이력 시트 확인상태에 승인/반려 → 다음 실행이 반영한다.
"""
from __future__ import annotations

from difflib import SequenceMatcher

from . import config
from .registry_core import Registry, _Run
from .registry_model import (C_APPROVE, C_PENDING, C_REJECT, ITEM_ACCT_ID, K_CONFIRMED, K_REJECTED,
                             K_RENAME_ACCT, K_RENAME_PROD, SHEET_ACCT, SHEET_PROD, HistRow)


# ── 확인(승인/반려) 처리 ────────────────────────────────────────
def _resolved_nos(reg: Registry) -> set:
    out = set()
    for h in reg.history:
        if h.kind in (K_CONFIRMED, K_REJECTED) and h.note.startswith("#"):
            out.add((h.sheet, int(h.note[1:].split()[0])))
    return out


def _resolve_confirmations(ctx: _Run) -> None:
    done = _resolved_nos(ctx.reg)
    for h in list(ctx.reg.history):
        if h.kind not in (K_RENAME_PROD, K_RENAME_ACCT) or (h.sheet, h.no) in done:
            continue
        if h.confirm == C_APPROVE:
            _apply_rename(ctx, h)
        elif h.confirm == C_REJECT:
            _close_rename(ctx, h, K_REJECTED, f"#{h.no} 반려")


def _close_rename(ctx: _Run, h: HistRow, kind: str, note: str) -> None:
    ctx.emit(h.sheet, kind, h.account_id, product=h.product, item=h.item, old=h.old, new=h.new,
             source=h.source, note=note)


def _apply_rename(ctx: _Run, h: HistRow) -> None:
    reg, snap = ctx.reg, ctx.snap
    if h.kind == K_RENAME_PROD:
        new_in_ledger = h.new in getattr(snap.accounts.get(h.account_id), "products", {})
        ok = (h.account_id, h.old) in reg.rows and (h.account_id, h.new) not in reg.rows and new_in_ledger
    else:
        ok = bool(reg.account_rows(h.old)) and not reg.account_rows(h.new) and h.new in snap.accounts
    if not ok:
        ctx.warnings.append(f"이력 #{h.no} 승인했으나 대장 상태가 바뀌어 적용 불가 → 반려 처리")
        _close_rename(ctx, h, K_REJECTED, f"#{h.no} 적용불가")
        return
    if h.kind == K_RENAME_PROD:
        row = reg.rows.pop((h.account_id, h.old))
        row.product = h.new
        reg.rows[row.key] = row
    else:
        for row in reg.account_rows(h.old):
            del reg.rows[row.key]
            row.account_id = h.new
            reg.rows[row.key] = row
    _close_rename(ctx, h, K_CONFIRMED, f"#{h.no} 승인")


# ── 이름 변경 의심(보류) ─────────────────────────────────────────
def _pending_pairs(reg: Registry, kind: str) -> set:
    done = _resolved_nos(reg)
    return {(h.account_id if kind == K_RENAME_PROD else "", h.old, h.new) for h in reg.history
            if h.kind == kind and (h.sheet, h.no) not in done}


def _rejected_pairs(reg: Registry, sheet: str) -> set:
    return {(h.account_id if sheet == SHEET_PROD else "", h.old, h.new) for h in reg.history
            if h.sheet == sheet and h.kind == K_REJECTED}


def _pair_by_similarity(removed: list[str], added: list[str], skip: set, scope: str) -> list[tuple[str, str]]:
    cands = sorted(((SequenceMatcher(None, o, n).ratio(), o, n) for o in removed for n in added
                    if (scope, o, n) not in skip), reverse=True)
    used_o, used_n, pairs = set(), set(), []
    for score, o, n in cands:
        if score < config.REGISTRY_RENAME_SIM or o in used_o or n in used_n:
            continue
        used_o.add(o)
        used_n.add(n)
        pairs.append((o, n))
    return pairs


def _hold_renames(ctx: _Run, sheet: str, kind: str, item: str, scope: str,
                  pairs: list[tuple[str, str]], source_of) -> tuple[set, set]:
    """이름 변경 의심 쌍을 '확인필요'로 한 번만 기록하고, (보류할 옛 이름들, 새 이름들) 반환."""
    pending = _pending_pairs(ctx.reg, kind)
    for o, n in pairs:
        if (scope, o, n) in pending:
            continue
        aid = scope if sheet == SHEET_PROD else n
        ctx.emit(sheet, kind, aid, product=(n if sheet == SHEET_PROD else ""), item=item, old=o, new=n,
                 source=source_of(n), confirm=C_PENDING)
        ctx.warnings.append(f"{item} 변경 의심 '{o}' → '{n}' — 원장 {sheet} 확인상태에서 승인/반려 필요")
    return {o for o, _ in pairs}, {n for _, n in pairs}


def _account_rename_pairs(reg: Registry, snap, removed: list[str], added: list[str]) -> list[tuple[str, str]]:
    """계정아이디만 바뀜 = 사업자명·대표자명이 같은 **1:1** 쌍(반려된 쌍 제외)."""
    rejected = _rejected_pairs(reg, SHEET_ACCT)
    same = []
    for o in removed:
        orow = reg.account_rows(o)[0].acct
        key = (orow.get("사업자명"), orow.get("대표자명"))
        same += [(o, n) for n in added
                 if key[0] and ("", o, n) not in rejected
                 and key == (snap.accounts[n].fields["사업자명"], snap.accounts[n].fields["대표자명"])]
    return [(o, n) for o, n in same
            if sum(1 for x, _ in same if x == o) == 1 and sum(1 for _, y in same if y == n) == 1]


def _hold_account_renames(ctx: _Run) -> tuple[set, set]:
    reg, snap = ctx.reg, ctx.snap
    removed = [a for a in reg.account_ids() if a not in snap.accounts and not ctx.acct_stopped(a)]
    added = [a for a in snap.accounts if not reg.account_rows(a)]
    pairs = _account_rename_pairs(reg, snap, removed, added)
    return _hold_renames(ctx, SHEET_ACCT, K_RENAME_ACCT, ITEM_ACCT_ID, "", pairs,
                         lambda n: snap.ref("계정아이디", snap.accounts[n].row_no))
