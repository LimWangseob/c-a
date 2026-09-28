"""셀독등록원장 — 대장 스냅샷을 원장 줄·이력으로 반영(계정·상품 추가/수정/관리중단/재개). SSOT=designs/LEDGER_REGISTRY.md §4.
"""
from __future__ import annotations

from .registry_core import _resume_item, _Run, _stop_item
from .registry_model import (ACCOUNT_FIELDS, GROWTH_FIELDS, ITEM_PROD_NAME, K_EDIT, K_INIT, K_NEW_ACCT,
                             K_NEW_PROD, K_RENAME_PROD, K_RESUME, K_STOP, SHEET_ACCT, SHEET_GROWTH, SHEET_PROD,
                             RegRow, SnapAccount, SnapProduct)
from .registry_rename import _hold_renames, _pair_by_similarity, _rejected_pairs


# ── 반영 ─────────────────────────────────────────────────────────
def _new_row(ctx: _Run, sa: SnapAccount, sp: SnapProduct | None) -> RegRow:
    row = RegRow(sa.account_id, sp.name if sp else "", acct=dict(sa.fields),
                 growth=dict(sp.growth) if sp else {g: "" for g in GROWTH_FIELDS},
                 stock=sp.stock if sp else "", registered=ctx.eff, changed=ctx.eff)
    ctx.reg.rows[row.key] = row
    return row


def _add_product(ctx: _Run, sa: SnapAccount, sp: SnapProduct, kind: str) -> None:
    _new_row(ctx, sa, sp)
    ctx.emit(SHEET_PROD, kind, sa.account_id, product=sp.name, source=ctx.snap.ref("상품명", sp.row_no))
    if sp.stopped and not sa.stopped:
        ctx.emit(SHEET_PROD, K_STOP, sa.account_id, product=sp.name, source=sp.reason, **_stop_item())


def _add_account(ctx: _Run, sa: SnapAccount, initial: bool) -> None:
    ctx.emit(SHEET_ACCT, K_INIT if initial else K_NEW_ACCT, sa.account_id,
             source=ctx.snap.ref("계정아이디", sa.row_no))
    for sp in sa.products.values():
        _add_product(ctx, sa, sp, K_INIT if initial else K_NEW_PROD)
    if not sa.products:
        _new_row(ctx, sa, None)                   # 상품 없는 계정도 원장에 보이게(상품명 공란 줄)
    if sa.stopped:
        ctx.emit(SHEET_ACCT, K_STOP, sa.account_id, source=sa.reason, **_stop_item())


def _update_account_fields(ctx: _Run, sa: SnapAccount) -> None:
    rows = ctx.reg.account_rows(sa.account_id)
    for f in ACCOUNT_FIELDS:
        old, new = rows[0].acct.get(f, ""), sa.fields[f]
        if old == new:
            continue
        ctx.emit(SHEET_ACCT, K_EDIT, sa.account_id, item=f, old=old, new=new,
                 source=ctx.snap.ref(f, sa.field_rows.get(f, sa.row_no)))
        for r in rows:
            r.acct[f] = new
            r.changed = ctx.eff


def _update_account_status(ctx: _Run, sa: SnapAccount) -> None:
    was = ctx.acct_stopped(sa.account_id)
    if sa.stopped and not was:
        ctx.emit(SHEET_ACCT, K_STOP, sa.account_id, source=sa.reason, **_stop_item())
    elif not sa.stopped and was:
        ctx.emit(SHEET_ACCT, K_RESUME, sa.account_id, source=ctx.snap.ref("계정아이디", sa.row_no),
                 **_resume_item())


def _update_product(ctx: _Run, sa: SnapAccount, sp: SnapProduct) -> None:
    row = ctx.reg.rows[(sa.account_id, sp.name)]
    for g in GROWTH_FIELDS:
        old, new = row.growth.get(g, ""), sp.growth[g]
        if old != new:
            ctx.emit(SHEET_GROWTH, K_EDIT, sa.account_id, product=sp.name, item=g, old=old, new=new,
                     source=ctx.snap.ref(g, sp.row_no))
            row.growth[g] = new
            row.changed = ctx.eff
    row.stock = sp.stock                              # 그로스 재고 = 최신값만(이력 없음·최종변경일 불변)
    if sa.stopped:
        return                                        # 계정 중단 중엔 상품 개별 상태를 따로 판정하지 않음
    was = ctx.prod_stopped(sa.account_id, sp.name)
    if sp.stopped and not was:
        ctx.emit(SHEET_PROD, K_STOP, sa.account_id, product=sp.name, source=sp.reason, **_stop_item())
    elif not sp.stopped and was:
        ctx.emit(SHEET_PROD, K_RESUME, sa.account_id, product=sp.name,
                 source=ctx.snap.ref("상품명", sp.row_no), **_resume_item())


def _update_account(ctx: _Run, sa: SnapAccount) -> None:
    aid = sa.account_id
    _update_account_fields(ctx, sa)
    _update_account_status(ctx, sa)
    existing = {r.product for r in ctx.reg.account_rows(aid)}
    removed = [p for p in existing if p and p not in sa.products and not ctx.prod_stopped(aid, p)]
    added = [p for p in sa.products if p not in existing]
    pairs = _pair_by_similarity(removed, added, _rejected_pairs(ctx.reg, SHEET_PROD), aid)
    held_old, held_new = _hold_renames(ctx, SHEET_PROD, K_RENAME_PROD, ITEM_PROD_NAME, aid, pairs,
                                       lambda n: ctx.snap.ref("상품명", sa.products[n].row_no))
    for name, sp in sa.products.items():
        if name in held_new:
            continue
        if name in existing:
            _update_product(ctx, sa, sp)
        else:
            _add_product(ctx, sa, sp, K_NEW_PROD)
    if sa.stopped:
        return
    for p in removed:
        if p not in held_old:
            ctx.emit(SHEET_PROD, K_STOP, aid, product=p, source="대장에서 상품 삭제", **_stop_item())
