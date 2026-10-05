"""문의/CS 원장 — 구글시트 입출력(시트 생성·서식·읽기·append)·잠금. SSOT=designs/DOMAIN_D10_CS.md §6·§7.

registry_gsheet 평행. 문의 접수·이벤트(응대/상태)·열람 기록을 **최신이 위**로 append 한다. 쓰기는 registry_lock
(CS 전용 lock 파일). 로그에는 문의ID·상태만 남기고 **고객 이름·연락처 원문은 적지 않는다**(cs_model 가림은 표시용).
개인정보 원문 열람은 record_access 로 감사 기록(항목명만). 로컬 백업은 만들지 않는다(개인정보 유출 방지·§3.3).
클라이언트는 덕타이핑(GSheetClient). 실패는 예외로 전파(silent 금지).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from . import cs_model as M
from . import cs_store as S
from .registry_lock import registry_lock

DEFAULT_LOCK = "output/_문의.lock"
_HEADER_BG = {"red": 0xB7 / 255, "green": 0xC9 / 255, "blue": 0xE8 / 255}


# ── 읽기 ─────────────────────────────────────────────────────────
def load_log(client) -> M.CSLog:
    grids = {s: (client.read_values(s) if s in client.sheet_titles() else []) for s in M.ALL_SHEETS}
    return S.parse_log(grids)


# ── 시트 생성·서식 ───────────────────────────────────────────────
def _validation(gid: int, col: int, values) -> dict:
    return {"setDataValidation": {
        "range": {"sheetId": gid, "startRowIndex": 1, "startColumnIndex": col, "endColumnIndex": col + 1},
        "rule": {"condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": v} for v in values]},
                 "strict": False, "showCustomUi": True}}}


def _format_requests(gid: int, header) -> list[dict]:
    reqs: list[dict] = [
        {"updateSheetProperties": {"properties": {"sheetId": gid, "gridProperties": {"frozenRowCount": 1}},
                                   "fields": "gridProperties.frozenRowCount"}},
        {"repeatCell": {"range": {"sheetId": gid, "startRowIndex": 0, "endRowIndex": 1,
                                  "startColumnIndex": 0, "endColumnIndex": len(header)},
                        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "backgroundColor": _HEADER_BG}},
                        "fields": "userEnteredFormat(textFormat,backgroundColor)"}},
    ]
    if "문의유형" in header:
        reqs.append(_validation(gid, header.index("문의유형"), M.INQUIRY_TYPES))
    if "변동유형" in header:
        reqs.append(_validation(gid, header.index("변동유형"), M.EVENT_KINDS))
    return reqs


def init_sheets(client, log=None) -> None:
    """문의·문의이력·열람기록 시트를 만들고 헤더·서식·선택목록을 한 번 건다."""
    log = log or (lambda m: None)
    ids = client.ensure_sheets(list(M.ALL_SHEETS))
    reqs: list[dict] = []
    for sheet, header in M.HEADERS.items():
        client.write_values(sheet, [list(header)], raw=True)
        reqs += _format_requests(ids[sheet], header)
    client.batch_update(reqs)
    log(f"== [문의] 시트 {len(M.ALL_SHEETS)}개 생성·서식: {', '.join(M.ALL_SHEETS)} ==")


def _insert_top(client, sheet: str, line: list[str]) -> None:
    gid = client.sheet_id(sheet)
    client.batch_update([{"insertDimension": {"range": {"sheetId": gid, "dimension": "ROWS",
                                                        "startIndex": 1, "endIndex": 2},
                                              "inheritFromBefore": False}}])
    client.write_values(sheet, [line], start="A2", raw=True)


def _lock(dry_run: bool, lock_path, log):
    from contextlib import nullcontext
    return nullcontext() if dry_run else registry_lock(lock_path, on_log=log)


def _ensure(client, log) -> None:
    if M.SHEET_INQUIRY not in client.sheet_titles():
        init_sheets(client, log)


# ── 쓰기(접수·이벤트·열람) ───────────────────────────────────────
def open_inquiry(client, *, marketplace: str, account_id: str, type: str, content: str, product: str = "",
                 asker_name: str = "", contact: str = "", now: datetime | None = None, dry_run: bool = False,
                 on_log=None, lock_path: str | Path = DEFAULT_LOCK) -> M.Inquiry:
    """문의 1건 접수(문의ID Q-0000 자동·최신이 위). 필수 칸(판매처·위탁계정·유형·내용) 검증. 로그에 고객 원문 없음."""
    log = on_log or (lambda m: None)
    now = now or datetime.now()
    M.validate_inquiry(marketplace, account_id, type, content)
    with _lock(dry_run, lock_path, log):
        clog = load_log(client)
        S.check_integrity(clog)
        q = M.Inquiry(id=S.next_inquiry_id(clog), received=now.strftime("%Y-%m-%d %H:%M:%S"),
                      marketplace=marketplace, account_id=account_id, product=product, type=type,
                      asker_name=asker_name, contact=contact, content=content)
        if not dry_run:
            _ensure(client, log)
            _insert_top(client, M.SHEET_INQUIRY, [q.id, q.received, q.marketplace, q.account_id, q.product,
                                                  q.type, q.asker_name, q.contact, q.content])
    log(f"== [문의] {'미리보기 ' if dry_run else ''}접수 {q.id} {account_id} [{type}] (고객 원문 생략) ==")
    return q


def add_event(client, *, inquiry_id: str, kind: str, author: str, note: str = "", now: datetime | None = None,
              dry_run: bool = False, on_log=None, lock_path: str | Path = DEFAULT_LOCK) -> M.Event:
    """문의 이벤트 1건 추가(진행/보류/재개/완료/재개방/응대·append). 보류는 사유 필수. 문의ID 없으면 CSError."""
    log = on_log or (lambda m: None)
    now = now or datetime.now()
    M.validate_event(kind, note)
    with _lock(dry_run, lock_path, log):
        clog = load_log(client)
        S.check_integrity(clog)
        if inquiry_id not in clog.inquiry_ids():
            raise M.CSError(f"문의ID '{inquiry_id}' 가 명부에 없습니다")
        ev = M.Event(no=clog.next_event_no(), inquiry_id=inquiry_id, ts=now.strftime("%Y-%m-%d %H:%M:%S"),
                     author=author, kind=kind, note=note)
        if not dry_run:
            _ensure(client, log)
            _insert_top(client, M.SHEET_EVENT, [str(ev.no), ev.inquiry_id, ev.ts, ev.author, ev.kind, ev.note])
    log(f"== [문의] {'미리보기 ' if dry_run else ''}이력 #{ev.no} {inquiry_id} [{kind}] ==")
    return ev


def record_access(client, *, actor: str, inquiry_id: str, items: str, now: datetime | None = None,
                  dry_run: bool = False, on_log=None, lock_path: str | Path = DEFAULT_LOCK) -> int:
    """개인정보 원문 열람 감사 — 누가·언제·어떤 문의의 어떤 항목을 봤는지(항목명만·원문 값 없음)."""
    log = on_log or (lambda m: None)
    now = now or datetime.now()
    with _lock(dry_run, lock_path, log):
        clog = load_log(client)
        S.check_integrity(clog)
        no = max((int(str(d[0]).strip() or 0) for d in (client.read_values(M.SHEET_ACCESS) or [])[1:]
                  if d and str(d[0]).strip().isdigit()), default=0) + 1
        if not dry_run:
            _ensure(client, log)
            _insert_top(client, M.SHEET_ACCESS, [str(no), now.strftime("%Y-%m-%d %H:%M:%S"), actor, inquiry_id, items])
    log(f"== [문의] {'미리보기 ' if dry_run else ''}열람기록 #{no} {actor}→{inquiry_id} [{items}] ==")
    return no
