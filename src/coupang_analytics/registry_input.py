"""셀독등록원장 — 원장 → 앱 입력 변환(2단계 앱 연계). SSOT=designs/LEDGER_REGISTRY.md §10-1.

- `to_input_list(reg, as_of)`: 관리중 계정·상품으로 InputList 구성(입력소스=원장, 2-4).
- `password_map(reg)`: 관리중 계정의 비밀번호 맵(credstore 저장용 — InputList 엔 비밀번호 칸이 없음).
- `previous_password(reg, account_id)`: 계정이력의 직전 비밀번호([이전 비밀번호로 1회 시도], 2-3).

원장은 지우지 않으므로 InputList.ledger_products·ledger_account_ids 엔 **관리중단 포함 원장 전체 줄**을 넣는다
(pipeline ⑥ 완전삭제가 결과 이력을 지우지 않게). 비밀번호 값은 로그에 남기지 않는다(§9).
"""
from __future__ import annotations

from .input_list import Account, InputList, Option, Product, _inbound_summary
from .registry_core import Registry, _order, _replay_status
from .registry_history import as_of as _as_of
from .registry_model import ITEM_ACCT_ID, K_CONFIRMED, K_EDIT, SHEET_ACCT, ST_ACTIVE

_FAR_FUTURE = "9999-12-31"
_PW = "비밀번호"
# 원장 그로스 열 → input_list._inbound_summary 키. '요청일자'는 원장에 열이 없어 요약에서 빠진다(§10-1 (b)).
_INBOUND_KEYS = (("inb_reqqty", "그로스 요청수량"), ("inb_workqty", "그로스 작업수량"),
                 ("inb_box", "그로스 박스"), ("inb_pallet", "그로스 파레트"),
                 ("inb_shipdate", "그로스 출고일자"))


def _view(reg: Registry, at: str | None) -> tuple[dict, dict]:
    """(그날 원장 줄 {(계정,상품): 항목}, 그날 계정 중단 여부 {계정: bool}). at=None 이면 현재."""
    day = at or _FAR_FUTURE
    rows = _as_of(reg, day)                       # 원장·이력 불일치면 RegistryIntegrityError(폴백 없음)
    st = _replay_status(reg.history, day)
    acct_stopped = {aid: st.acct.get(aid, (False, ""))[0] for aid, _ in rows}
    return rows, acct_stopped


def _inbound(d: dict) -> str:
    return _inbound_summary([d.get(col, "") for _, col in _INBOUND_KEYS],
                            {key: i for i, (key, _) in enumerate(_INBOUND_KEYS)})


def to_input_list(reg: Registry, as_of: str | None = None, *, on_log=None) -> InputList:
    """관리상태=관리중 계정·상품 → InputList(as_of=YYYY-MM-DD 면 그날 기준).

    관리중단 계정은 제외, 관리중 계정 안의 관리중단 상품도 제외(§10 '관리중만'). 마케팅 날짜(mkt_*)는 원장에
    없어 비운다(기존 결과시트 read_marketing 역머지 경로가 채움). 최근입고 요약엔 '요청일자'가 빠진다."""
    log = on_log or (lambda m: None)
    rows, acct_stopped = _view(reg, as_of)
    accounts: dict[str, Account] = {}
    all_ids: set = set()
    for (aid, prod), d in rows.items():
        all_ids.add(aid)
        if acct_stopped[aid]:
            continue
        a = accounts.get(aid)
        if a is None:
            a = accounts[aid] = Account(aid, d.get("대표자명", ""), d.get("사업자명", ""))
        if not prod:
            continue
        a.ledger_products.add(prod)                # 관리중단 상품도 '줄 존재' → 완전삭제 대상 아님
        if d["관리상태"] == ST_ACTIVE:
            a.products.append(Product(prod, options=[Option("")], inbound_summary=_inbound(d)))
    il = InputList(accounts=list(accounts.values()), errors=[], ledger_account_ids=all_ids)
    n_prod = sum(len(a.products) for a in il.accounts)
    log(f"== [원장] 입력 구성{f'({as_of} 기준)' if as_of else ''} — 관리중 {len(il.accounts)}계정·{n_prod}상품 "
        f"(원장 전체 {len(all_ids)}계정). 원장에 없는 항목: 마케팅 날짜(결과시트 역머지 사용)·그로스 요청일자 ==")
    return il


def password_map(reg: Registry) -> dict[str, str]:
    """현재 관리중 계정 → 비밀번호(원장 값·원문). 빈 비밀번호 계정은 넣지 않는다."""
    rows, acct_stopped = _view(reg, None)
    out: dict[str, str] = {}
    for (aid, _), d in rows.items():
        pw = d.get(_PW, "")
        if not acct_stopped[aid] and pw and aid not in out:
            out[aid] = pw
    return out


def previous_password(reg: Registry, account_id: str) -> str | None:
    """계정이력에서 **직전 비밀번호** — 최신 '수정(비밀번호)' 이력부터 거슬러 현재 값과 다르고 빈 값 아닌 이전값.

    승인된 계정아이디 변경(확인완료)은 옛 아이디 이력까지 이어 본다. 원장에 없는 계정·변경 이력 없음 = None."""
    rows = reg.account_rows(account_id)
    if not rows:
        return None
    current = rows[0].acct.get(_PW, "")
    ids = {account_id}
    for h in sorted((h for h in reg.history if h.sheet == SHEET_ACCT), key=_order, reverse=True):
        if h.kind == K_CONFIRMED and h.item == ITEM_ACCT_ID and h.new in ids:
            ids.add(h.old)
        elif h.kind == K_EDIT and h.item == _PW and h.account_id in ids and h.old and h.old != current:
            return h.old
    return None
