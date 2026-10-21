"""셀독계정상품이력관리원장 — 동기화 진입점(대장 → 원장 + 이력)과 공개 API. SSOT=designs/LEDGER_REGISTRY.md.

원칙: 원장 줄은 지우지 않는다 · 이력은 추가만 · 관리상태는 이력에서 계산 · 이름 변경은 자동 병합하지 않고
'확인필요'로 보류 · 대장 계정 급감이면 반영 중단. 구성: registry_core(자료구조)·registry_rename(이름 변경)·
registry_apply(반영)·registry_history(복원·무결성)·registry_gsheet(구글시트 입출력).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from . import config
from .registry_apply import _add_account, _update_account
from .registry_core import Registry, RegistryGuardError, RegistryIntegrityError, _Run, _stop_item
from .registry_history import as_of, check_integrity, managed_between
from .registry_input import password_map, previous_password, to_input_list
from .registry_lock import RegistryLockError
from .registry_model import (C_PENDING, ITEM_STATUS, K_EDIT, K_INIT, K_MISTAKE, K_NEW_ACCT, K_NEW_PROD, K_RESUME,
                             K_STOP, SHEET_ACCT, SHEET_GROWTH, SHEET_PROD, ST_ACTIVE, ST_MISTAKE, ST_STOPPED,
                             LedgerSnapshot, valid_account_id)
from .registry_rename import _hold_account_renames, _resolve_confirmations


@dataclass
class SyncResult:
    registry: Registry
    events: list
    summary: dict
    warnings: list


def _guard_drop(ctx: _Run) -> None:
    active = [a for a in ctx.reg.account_ids() if not ctx.acct_stopped(a)]
    if len(active) < config.REGISTRY_DROP_MIN:
        return
    present = sum(1 for a in active if a in ctx.snap.accounts and not ctx.snap.accounts[a].stopped)
    if present < len(active) * config.REGISTRY_DROP_GUARD:
        raise RegistryGuardError(
            f"관리대장 계정 급감 — 원장 관리중 {len(active)}개 중 대장에 {present}개만 있음"
            f"(기준 {config.REGISTRY_DROP_GUARD:.0%}). 대장 일부 유실 의심으로 반영 중단 — 대장 확인 필요")


def _summary(ctx: _Run) -> dict:
    ev = ctx.events

    def cnt(pred) -> int:
        return sum(1 for e in ev if pred(e))
    return {
        "대장 계정": len(ctx.snap.accounts),
        "대장 상품": sum(len(a.products) for a in ctx.snap.accounts.values()),
        "원장 계정": len(ctx.reg.account_ids()),
        "원장 상품": sum(1 for k in ctx.reg.rows if k[1]),
        "신규계정": cnt(lambda e: e.sheet == SHEET_ACCT and e.kind in (K_INIT, K_NEW_ACCT)),
        "신규상품": cnt(lambda e: e.sheet == SHEET_PROD and e.kind in (K_INIT, K_NEW_PROD)),
        "계정수정": cnt(lambda e: e.sheet == SHEET_ACCT and e.kind == K_EDIT),
        "그로스수정": cnt(lambda e: e.sheet == SHEET_GROWTH),
        "관리중단": cnt(lambda e: e.kind == K_STOP),
        "재개": cnt(lambda e: e.kind == K_RESUME),
        "확인필요": cnt(lambda e: e.confirm == C_PENDING),
    }


def _mark_mistaken(ctx: _Run) -> None:
    """원장에 이미 들어간 형식 오류 계정ID(실측 10-19 유라이프 계정아이디 칸에 비밀번호)를 '오입력'으로 한 번 표시 —
    줄·이력은 지우지 않고(무결성 유지) 상태만 바꿔 정산·로그인 대상에서 뺀다(D-103)."""
    done = ctx.reg.mistaken_ids()
    for aid in ctx.reg.account_ids():
        if valid_account_id(aid) or aid in done:
            continue
        old = ST_STOPPED if ctx.acct_stopped(aid) else ST_ACTIVE
        ctx.emit(SHEET_ACCT, K_MISTAKE, aid, item=ITEM_STATUS, old=old, new=ST_MISTAKE,
                 source="계정아이디 형식 오류(영문·숫자 아님) — 정산·로그인 제외")


def sync(reg: Registry, snap: LedgerSnapshot, *, now: datetime, judge=None) -> SyncResult:
    """대장 스냅샷을 원장에 반영하고 이번 실행의 이력 줄을 돌려준다(reg 를 제자리 갱신).

    원장이 비어 있으면 최초 구축(변동유형=최초등록). 급감이면 RegistryGuardError(아무것도 안 바꿈).
    """
    ctx = _Run(reg, snap, now)
    ctx.judge = judge   # 상품명 변경 자동 판단(D-070) — None 이면 확인필요(사람 승인)
    initial = not reg.rows
    if not initial:
        _guard_drop(ctx)
    _resolve_confirmations(ctx)
    held_old, held_new = (set(), set()) if initial else _hold_account_renames(ctx)
    for aid, sa in snap.accounts.items():
        if aid in held_new:
            continue
        if not valid_account_id(aid):              # 형식 오류 계정ID = 원장에 넣지 않음(D-103 · 값은 경고에 안 씀)
            ctx.warnings.append(f"대장 {sa.row_no}행 계정아이디 형식 오류(영문·숫자 아님 — 비밀번호 등 오입력 의심) → "
                                "원장 반영 안 함·대장 확인 필요")
            continue
        if reg.account_rows(aid):
            _update_account(ctx, sa)
        else:
            _add_account(ctx, sa, initial)
    _mark_mistaken(ctx)
    for aid in reg.account_ids():
        if aid not in snap.accounts and aid not in held_old and not ctx.acct_stopped(aid):
            ctx.emit(SHEET_ACCT, K_STOP, aid, source="대장에서 계정 삭제", **_stop_item())
    return SyncResult(reg, ctx.events, _summary(ctx), ctx.warnings)


__all__ = ["Registry", "RegistryGuardError", "RegistryIntegrityError", "RegistryLockError", "SyncResult", "as_of",
           "check_integrity", "managed_between", "password_map", "previous_password", "sync", "to_input_list"]
