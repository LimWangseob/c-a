"""채권자 원장 — 채권/상환 기록·잔액 replay·가림·열람 로그. SSOT=DOMAIN_D8_SETTLEMENT_PHASE23 §4.3·SETTLEMENT_MODEL §3.3·IO 12-x.

⚠ 법률 민감(파산 전 특정 채권자 우선 변제는 취소될 수 있음). **배분 기준은 법률 검토 후 소유자가 정하고 앱은
계산·기록·감사만** 한다([[business-context-consignment-creditors]]). 규칙 미확정이라 이 모듈은 **기록(채권확정·수동 상환
입력)만** 구현한다 — 상환 배분 계산(creditor_settlement)은 보류(R1). 잘못은 지우지 않고 **반대 기록**으로 정정한다.

돈 원장: append-only·잔액 = 이력 replay(채권확정 누적 − 상환 누적). registry 금액 replay 변형.
민감(가림·IO 12-x): 이름·연락처 = 대표/정산담당만 원문 · **상환계좌 = 대표만**. 그 외는 ●●●● 로 가린다.
열람 로그(감사) = 원문을 본 사람·시각·항목을 별도 append 기록. **앱 로그·결과·git·로컬 백업에 원문 금지**
→ 이 모듈은 로컬 백업을 만들지 않는다(관리대장 평문 비번 로컬 백업 생략 선례와 동일). 별도 스프레드시트·공유 최소.
쓰기는 registry_lock(채권자 전용 lock 파일). 실패는 예외로 전파(silent 금지). 클라이언트는 덕타이핑(GSheetClient).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .registry_lock import registry_lock

SHEET_MASTER = "채권자"
SHEET_LEDGER = "채권상환"
SHEET_CONTACT = "응대기록"
SHEET_ACCESS = "열람기록"
ALL_SHEETS = (SHEET_MASTER, SHEET_LEDGER, SHEET_CONTACT, SHEET_ACCESS)
DEFAULT_LOCK = "output/_채권자.lock"

MV_CLAIM = "채권확정"
MV_REPAY = "상환"
MOVEMENT_TYPES = (MV_CLAIM, MV_REPAY)

# 민감(가림) — 항목 → 원문을 볼 수 있는 역할. 상환계좌는 대표만(IO 12-x).
NAME_CONTACT_ROLES = ("대표", "정산담당")
ACCOUNT_ROLES = ("대표",)
MASKED_MASTER = {"이름": NAME_CONTACT_ROLES, "연락처": NAME_CONTACT_ROLES, "상환계좌": ACCOUNT_ROLES}
MASK = "●●●●"

H_MASTER = ("번호", "이름", "연락처", "상환계좌")
H_LEDGER = ("번호", "채권자번호", "일자", "유형", "금액", "비고")
H_CONTACT = ("번호", "채권자번호", "일자", "작성자", "내용")
H_ACCESS = ("번호", "일시", "열람자", "채권자번호", "항목")
_HEADERS = {SHEET_MASTER: H_MASTER, SHEET_LEDGER: H_LEDGER, SHEET_CONTACT: H_CONTACT, SHEET_ACCESS: H_ACCESS}

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_CID = re.compile(r"C-(\d+)")


class CreditorError(Exception):
    """채권자 입력·원장이 규칙에 맞지 않음(아무것도 쓰지 않음)."""


@dataclass
class Creditor:
    no: str                 # C-0000
    name: str
    contact: str
    account: str


@dataclass
class Movement:
    no: int
    creditor_id: str
    date: str
    kind: str               # 채권확정 / 상환
    amount: int             # 정정은 반대 부호(음수 허용)
    note: str = ""


# ── 금액·검증 ────────────────────────────────────────────────────
def parse_amount(v) -> int:
    """'1,200,000'·' -5000 '·12000 → 정수. 숫자가 아니면 CreditorError(정정=음수 허용)."""
    s = " ".join(str(v).split()).replace(",", "")
    if not re.fullmatch(r"-?\d+", s):
        raise CreditorError(f"채권/상환 금액이 정수가 아님: '{v}'")
    return int(s)


def _validate_date(d: str) -> None:
    if not _ISO_DATE.fullmatch(str(d)):
        raise CreditorError(f"일자 '{d}' 은 YYYY-MM-DD 형식이 아닙니다")


# ── 읽기 ─────────────────────────────────────────────────────────
def _cellmap(header: list, row: list) -> dict:
    return {h: (row[i] if i < len(row) else "") for i, h in enumerate(header)}


def _rows(client, sheet: str) -> list[dict]:
    if sheet not in client.sheet_titles():
        return []
    grid = client.read_values(sheet) or []
    if not grid:
        return []
    header = [str(h) for h in grid[0]]
    return [_cellmap(header, r) for r in grid[1:] if any(str(c).strip() for c in r)]


def load_creditors(client) -> list[Creditor]:
    return [Creditor(str(d.get("번호", "")), str(d.get("이름", "")), str(d.get("연락처", "")),
                     str(d.get("상환계좌", ""))) for d in _rows(client, SHEET_MASTER)]


def _movement_from(d: dict) -> Movement:
    raw_no = str(d.get("번호", "")).strip()
    try:
        no = int(raw_no)
    except ValueError as exc:
        raise CreditorError(f"채권상환 '번호' 칸이 숫자가 아님: '{raw_no}'") from exc
    return Movement(no=no, creditor_id=str(d.get("채권자번호", "")), date=str(d.get("일자", "")),
                    kind=str(d.get("유형", "")), amount=parse_amount(d.get("금액", "0")),
                    note=str(d.get("비고", "")))


def load_movements(client) -> list[Movement]:
    return [_movement_from(d) for d in _rows(client, SHEET_LEDGER)]


# ── 잔액(replay) ─────────────────────────────────────────────────
def balance(movements: list[Movement], creditor_id: str, *, as_of: str | None = None) -> int:
    """채권확정 누적 − 상환 누적(as_of 있으면 그날까지). 정정(반대 부호)은 자연히 반영된다."""
    claim = repay = 0
    for m in movements:
        if m.creditor_id != creditor_id or (as_of is not None and m.date > as_of):
            continue
        if m.kind == MV_CLAIM:
            claim += m.amount
        elif m.kind == MV_REPAY:
            repay += m.amount
    return claim - repay


def balances(movements: list[Movement], *, as_of: str | None = None) -> dict[str, int]:
    ids = list(dict.fromkeys(m.creditor_id for m in movements))
    return {cid: balance(movements, cid, as_of=as_of) for cid in ids}


# ── 무결성 ───────────────────────────────────────────────────────
def _check_seq(client, sheet: str) -> None:
    nos = sorted(int(str(d.get("번호", "")).strip() or 0) for d in _rows(client, sheet))
    if nos != list(range(1, len(nos) + 1)):
        raise CreditorError(f"{sheet} 번호가 1..n 연속이 아님(누락/중복): {nos[:10]}")


def check_integrity(client) -> None:
    """채권상환·응대·열람 시트의 번호가 각각 1..n 연속이어야 한다(돈 원장은 지우면 안 됨)."""
    for sheet in (SHEET_LEDGER, SHEET_CONTACT, SHEET_ACCESS):
        _check_seq(client, sheet)


# ── 가림(민감) ───────────────────────────────────────────────────
def mask_master(creditor: Creditor | dict, *, role: str) -> dict:
    """채권자 민감 칸을 역할에 맞게 가린다 — 이름/연락처=대표·정산담당, 상환계좌=대표만. 번호는 공개.
    순수 함수(I/O 없음) — 원문 열람 시 record_access 로 감사 기록을 남기는 건 호출부 책임."""
    d = creditor if isinstance(creditor, dict) else {"번호": creditor.no, "이름": creditor.name,
                                                      "연락처": creditor.contact, "상환계좌": creditor.account}
    out = dict(d)
    for item, roles in MASKED_MASTER.items():
        if role not in roles and str(out.get(item, "")).strip():
            out[item] = MASK
    return out


# ── 쓰기 공통 ────────────────────────────────────────────────────
_HEADER_BG = {"red": 0xB7 / 255, "green": 0xC9 / 255, "blue": 0xE8 / 255}


def _format_requests(gid: int, ncol: int) -> list[dict]:
    return [
        {"updateSheetProperties": {"properties": {"sheetId": gid, "gridProperties": {"frozenRowCount": 1}},
                                   "fields": "gridProperties.frozenRowCount"}},
        {"repeatCell": {"range": {"sheetId": gid, "startRowIndex": 0, "endRowIndex": 1,
                                  "startColumnIndex": 0, "endColumnIndex": ncol},
                        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "backgroundColor": _HEADER_BG}},
                        "fields": "userEnteredFormat(textFormat,backgroundColor)"}},
    ]


def init_sheets(client, log=None) -> None:
    """채권자 전용 스프레드시트에 시트 4개를 만들고 헤더·서식을 한 번 건다(별도 파일·공유 최소)."""
    log = log or (lambda m: None)
    ids = client.ensure_sheets(list(ALL_SHEETS))
    reqs: list[dict] = []
    for sheet, header in _HEADERS.items():
        client.write_values(sheet, [list(header)], raw=True)
        reqs += _format_requests(ids[sheet], len(header))
    client.batch_update(reqs)
    log(f"== [채권자] 시트 {len(ALL_SHEETS)}개 생성·서식: {', '.join(ALL_SHEETS)} ==")


def _insert_top(client, sheet: str, line: list[str]) -> None:
    gid = client.sheet_id(sheet)
    client.batch_update([{"insertDimension": {"range": {"sheetId": gid, "dimension": "ROWS",
                                                        "startIndex": 1, "endIndex": 2},
                                              "inheritFromBefore": False}}])
    client.write_values(sheet, [line], start="A2", raw=True)


def _next_seq(client, sheet: str) -> int:
    nos = [int(str(d.get("번호", "")).strip() or 0) for d in _rows(client, sheet)]
    return max(nos, default=0) + 1


def _lock(dry_run: bool, lock_path, log):
    from contextlib import nullcontext
    return nullcontext() if dry_run else registry_lock(lock_path, on_log=log)


def _ensure(client, log) -> None:
    if SHEET_MASTER not in client.sheet_titles():
        init_sheets(client, log)


# ── 쓰기(채권자·채권/상환·응대·열람) ─────────────────────────────
def _next_cid(client) -> str:
    nums = [int(m.group(1)) for d in _rows(client, SHEET_MASTER) if (m := _CID.fullmatch(str(d.get("번호", ""))))]
    return f"C-{max(nums, default=0) + 1:04d}"


def record_creditor(client, *, name: str, contact: str, account: str, dry_run: bool = False,
                    on_log=None, lock_path: str | Path = DEFAULT_LOCK) -> Creditor:
    """채권자 1명 등록(번호 C-0000 자동). 이름·연락처·상환계좌 필수(IO 12-x). 원문은 시트에 저장(별도 파일)."""
    log = on_log or (lambda m: None)
    if not (str(name).strip() and str(contact).strip() and str(account).strip()):
        raise CreditorError("채권자 이름·연락처·상환계좌는 모두 필수입니다")
    with _lock(dry_run, lock_path, log):
        check_integrity(client)
        cid = _next_cid(client)
        cr = Creditor(cid, name, contact, account)
        if not dry_run:
            _ensure(client, log)
            _insert_top(client, SHEET_MASTER, [cr.no, cr.name, cr.contact, cr.account])
    log(f"== [채권자] {'미리보기 ' if dry_run else ''}등록 {cid} (이름·연락처·계좌 값 생략) ==")
    return cr


def record_movement(client, *, creditor_id: str, kind: str, amount, date: str, note: str = "",
                    dry_run: bool = False, on_log=None, lock_path: str | Path = DEFAULT_LOCK) -> Movement:
    """채권확정·상환 1건 기록(지우지 않고 추가만·정정=반대 기록으로 음수 입력). 금액=정수.
    채권자번호가 명부에 없으면 CreditorError. 쓰기는 잠금 안에서만."""
    log = on_log or (lambda m: None)
    if kind not in MOVEMENT_TYPES:
        raise CreditorError(f"유형 '{kind}' 은 허용값 아님 — {', '.join(MOVEMENT_TYPES)}")
    amt = parse_amount(amount)
    _validate_date(date)
    with _lock(dry_run, lock_path, log):
        check_integrity(client)
        if not any(str(d.get("번호", "")) == creditor_id for d in _rows(client, SHEET_MASTER)):
            raise CreditorError(f"채권자번호 '{creditor_id}' 가 명부에 없습니다")
        mv = Movement(no=_next_seq(client, SHEET_LEDGER), creditor_id=creditor_id, date=date,
                      kind=kind, amount=amt, note=note)
        if not dry_run:
            _ensure(client, log)
            _insert_top(client, SHEET_LEDGER, [str(mv.no), mv.creditor_id, mv.date, mv.kind, str(mv.amount), mv.note])
    log(f"== [채권자] {'미리보기 ' if dry_run else ''}#{mv.no} {creditor_id} {kind} (금액 생략) ==")
    return mv


def record_contact(client, *, creditor_id: str, content: str, author: str, now: datetime | None = None,
                   dry_run: bool = False, on_log=None, lock_path: str | Path = DEFAULT_LOCK) -> int:
    """응대 기록 1줄 추가(append). 반환 = 번호. 내용 필수."""
    log = on_log or (lambda m: None)
    now = now or datetime.now()
    if not str(content).strip():
        raise CreditorError("응대 '내용'은 필수입니다")
    with _lock(dry_run, lock_path, log):
        check_integrity(client)
        no = _next_seq(client, SHEET_CONTACT)
        if not dry_run:
            _ensure(client, log)
            _insert_top(client, SHEET_CONTACT, [str(no), creditor_id, now.date().isoformat(), author, content])
    log(f"== [채권자] {'미리보기 ' if dry_run else ''}응대 #{no} {creditor_id} ==")
    return no


def record_access(client, *, actor: str, creditor_id: str, items: str, now: datetime | None = None,
                  dry_run: bool = False, on_log=None, lock_path: str | Path = DEFAULT_LOCK) -> int:
    """열람 기록 1줄(감사) — 누가·언제·어떤 채권자의 어떤 민감 항목을 원문으로 봤는지. 원문 값은 적지 않는다(항목명만)."""
    log = on_log or (lambda m: None)
    now = now or datetime.now()
    with _lock(dry_run, lock_path, log):
        check_integrity(client)
        no = _next_seq(client, SHEET_ACCESS)
        if not dry_run:
            _ensure(client, log)
            _insert_top(client, SHEET_ACCESS, [str(no), now.strftime("%Y-%m-%d %H:%M:%S"), actor, creditor_id, items])
    log(f"== [채권자] {'미리보기 ' if dry_run else ''}열람기록 #{no} {actor}→{creditor_id} [{items}] ==")
    return no
