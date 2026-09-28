"""셀독등록원장 — 핵심 자료구조(원장·이력 상태 계산·실행 컨텍스트). SSOT=designs/LEDGER_REGISTRY.md.

관리상태(관리중/관리중단)는 원장에 저장된 값이 아니라 **이력에서 계산**한다(_replay_status).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .registry_model import (HISTORY_SHEETS, ITEM_ACCT_ID, ITEM_PROD_NAME, ITEM_STATUS, K_CONFIRMED, K_INIT,
                             K_NEW_ACCT, K_NEW_PROD, K_REJECTED, K_RESUME, K_STOP, SHEET_ACCT, SHEET_PROD,
                             ST_ACTIVE, ST_STOPPED, HistRow, LedgerSnapshot, RegRow)


class RegistryGuardError(Exception):
    """대장이 비정상(계정 급감 등)이라 원장 반영을 중단함."""


class RegistryIntegrityError(Exception):
    """원장·이력이 서로 맞지 않음(이력 번호 누락·손수정 등) — 동기화 중단."""


_OPENERS = (K_INIT, K_NEW_ACCT, K_NEW_PROD, K_RESUME)
_SHEET_ORDER = {s: i for i, s in enumerate(HISTORY_SHEETS)}


def _order(h: HistRow):
    """이력 시간순 키 — 같은 실행 안에선 확인 처리(이름 변경)가 먼저 일어난다."""
    return (h.ts, 0 if h.kind in (K_CONFIRMED, K_REJECTED) else 1, _SHEET_ORDER[h.sheet], h.no)


@dataclass
class _State:
    acct: dict = field(default_factory=dict)      # 계정아이디 → (중단여부, 중단일)
    prod: dict = field(default_factory=dict)      # (계정아이디, 상품명) → (중단여부, 중단일)


def _replay_status(history: list[HistRow], at: str | None = None) -> _State:
    """이력을 시간순으로 적용해 계정·상품 관리상태를 계산(at 이 있으면 효력일 ≤ at 까지만)."""
    st = _State()
    for h in sorted(history, key=_order):
        if at is not None and h.eff > at:
            continue
        if h.kind == K_CONFIRMED and h.item == ITEM_ACCT_ID:
            _rename_state_account(st, h.old, h.new)
        elif h.kind == K_CONFIRMED and h.item == ITEM_PROD_NAME:
            if (h.account_id, h.old) in st.prod:
                st.prod[(h.account_id, h.new)] = st.prod.pop((h.account_id, h.old))
        elif h.kind in _OPENERS or h.kind == K_STOP:
            flag = (True, h.eff) if h.kind == K_STOP else (False, "")
            if h.sheet == SHEET_ACCT:
                st.acct[h.account_id] = flag
            elif h.sheet == SHEET_PROD:
                st.prod[(h.account_id, h.product)] = flag
    return st


def _rename_state_account(st: _State, old: str, new: str) -> None:
    if old in st.acct:
        st.acct[new] = st.acct.pop(old)
    for (aid, p) in [k for k in st.prod if k[0] == old]:
        st.prod[(new, p)] = st.prod.pop((aid, p))


def _row_status(st: _State, aid: str, prod: str) -> tuple[str, str]:
    a_stop, a_date = st.acct.get(aid, (False, ""))
    p_stop, p_date = st.prod.get((aid, prod), (False, ""))
    dates = [d for s, d in ((a_stop, a_date), (p_stop, p_date)) if s]
    return (ST_STOPPED, min(dates)) if dates else (ST_ACTIVE, "")


@dataclass
class Registry:
    rows: dict = field(default_factory=dict)          # (계정아이디, 상품명) → RegRow
    history: list = field(default_factory=list)       # HistRow (시트별 번호 1..n)

    def account_ids(self) -> list[str]:
        return list(dict.fromkeys(k[0] for k in self.rows))

    def account_rows(self, aid: str) -> list[RegRow]:
        return [r for k, r in self.rows.items() if k[0] == aid]

    def row_status(self, aid: str, prod: str) -> tuple[str, str]:
        return _row_status(_replay_status(self.history), aid, prod)

    def next_no(self, sheet: str) -> int:
        return max((h.no for h in self.history if h.sheet == sheet), default=0) + 1


# ── 실행 컨텍스트 ────────────────────────────────────────────────
class _Run:
    def __init__(self, reg: Registry, snap: LedgerSnapshot, now: datetime):
        self.reg, self.snap = reg, snap
        self.ts = now.strftime("%Y-%m-%d %H:%M:%S")
        self.eff = now.strftime("%Y-%m-%d")
        self.run_id = now.strftime("R%y%m%d-%H%M%S")
        self.events: list[HistRow] = []
        self.warnings: list[str] = list(snap.warnings)
        self.state = _replay_status(reg.history)

    def biz_of(self, aid: str) -> str:
        sa = self.snap.accounts.get(aid)
        if sa and sa.fields.get("사업자명"):
            return sa.fields["사업자명"]
        rows = self.reg.account_rows(aid)
        return rows[0].acct.get("사업자명", "") if rows else ""

    def emit(self, sheet: str, kind: str, aid: str, **kw) -> HistRow:
        h = HistRow(sheet=sheet, run_id=self.run_id, ts=self.ts, eff=self.eff, account_id=aid,
                    biz=self.biz_of(aid), kind=kind, no=self.reg.next_no(sheet), **kw)
        self.reg.history.append(h)
        self.events.append(h)
        self.state = _replay_status(self.reg.history)
        return h

    def acct_stopped(self, aid: str) -> bool:
        return self.state.acct.get(aid, (False, ""))[0]

    def prod_stopped(self, aid: str, prod: str) -> bool:
        return self.state.prod.get((aid, prod), (False, ""))[0]


def _stop_item() -> dict:
    return {"item": ITEM_STATUS, "old": ST_ACTIVE, "new": ST_STOPPED}


def _resume_item() -> dict:
    return {"item": ITEM_STATUS, "old": ST_STOPPED, "new": ST_ACTIVE}
