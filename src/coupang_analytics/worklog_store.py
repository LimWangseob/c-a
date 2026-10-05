"""업무일지 원장 — 위탁 운영 기록(append 전용·상태는 줄 자체). SSOT=designs/DOMAIN_D8_SETTLEMENT_PHASE23.md §4.2·IO 11-4.

registry 패턴 중 **추가만·최신 위·번호 연속**만 차용한다(개정·as_of 복원 불필요 — 순수 운영 로그).
상태(진행/완료/보류)는 줄의 상태 칸이며 이력 replay 하지 않는다(사람이 시트에서 바꿈). '7일 넘은 진행'은
저장 값이 아니라 렌더 시 계산한다(is_overdue). D10 문의(CS)와 혼동 금지 — 업무일지=내부 운영 기록.

쓰기(append)는 registry_lock 으로 잠근다(같은 PC 직렬·DEFAULT_LOCK 는 원장과 별도 파일). 실패는 예외로 전파한다
(silent 금지·[[no-silent-fallback-principle]]). 구글시트 클라이언트는 덕타이핑(GSheetClient 와 같은 메서드).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from .registry_lock import registry_lock
from .registry_model import canon

SHEET = "업무일지"
DEFAULT_LOCK = "output/_업무일지.lock"      # 상대경로 = 앱 set_workdir(data_root) 기준·셀독원장 잠금과 분리
OVERDUE_DAYS = 7                            # 진행 상태가 이 날수를 넘으면 렌더에서 '지연' 표시(IO 11-4)

WL_ACTIVE = "진행"
WL_DONE = "완료"
WL_HOLD = "보류"
STATUS_CHOICES = (WL_ACTIVE, WL_DONE, WL_HOLD)

# 번호 자동 · 일자/작성자 자동(앱) · 나머지 사람 입력(IO 11-4 6칸 = 일자·작성자·위탁계정·상품·내용·후속조치·상태)
HEADER = ("번호", "일자", "작성자", "위탁계정", "상품", "내용", "후속조치", "상태")

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class WorklogError(Exception):
    """업무일지 입력·원장이 규칙에 맞지 않음(아무것도 쓰지 않음)."""


@dataclass
class WorklogEntry:
    """업무일지 1줄. 상품이 비면 '계정 전체'(IO 11-4). date/author 는 앱이 채운다."""
    no: int
    date: str
    author: str
    account_id: str
    product: str
    content: str
    followup: str
    status: str


@dataclass
class Worklog:
    entries: list[WorklogEntry]      # 시트 순서(최신이 위)

    def next_no(self) -> int:
        return max((e.no for e in self.entries), default=0) + 1


# ── 검증 ─────────────────────────────────────────────────────────
def _validate(account_id: str, content: str, status: str) -> None:
    if not account_id:
        raise WorklogError("업무일지 '위탁계정'은 필수입니다")
    if not content:
        raise WorklogError("업무일지 '내용'은 필수입니다")
    if status not in STATUS_CHOICES:
        raise WorklogError(f"업무일지 '상태' 값 '{status}' 은 허용값 아님 — {', '.join(STATUS_CHOICES)}")


def check_integrity(wl: Worklog) -> None:
    """번호가 1..n 연속이어야 한다(누락·중복 = 누가 줄을 지웠거나 손수정 → 쓰기 중단)."""
    nos = sorted(e.no for e in wl.entries)
    if nos != list(range(1, len(nos) + 1)):
        raise WorklogError(f"업무일지 번호가 1..n 연속이 아님(누락/중복): {nos[:10]}")


# ── 읽기 ─────────────────────────────────────────────────────────
def _cellmap(header: list, row: list) -> dict:
    return {h: (row[i] if i < len(row) else "") for i, h in enumerate(header)}


def _entry_from_row(d: dict) -> WorklogEntry:
    raw_no = str(d.get("번호", "")).strip()
    try:
        no = int(raw_no)
    except ValueError as exc:
        raise WorklogError(f"업무일지 '번호' 칸이 숫자가 아님: '{raw_no}'") from exc
    return WorklogEntry(no=no, date=str(d.get("일자", "")), author=str(d.get("작성자", "")),
                        account_id=str(d.get("위탁계정", "")), product=str(d.get("상품", "")),
                        content=str(d.get("내용", "")), followup=str(d.get("후속조치", "")),
                        status=str(d.get("상태", "")))


def load(client) -> Worklog:
    """시트 → Worklog. 시트가 없으면 빈 원장(최초). 빈 줄은 건너뛴다."""
    if SHEET not in client.sheet_titles():
        return Worklog([])
    grid = client.read_values(SHEET) or []
    if not grid:
        return Worklog([])
    header = [str(h) for h in grid[0]]
    entries = [_entry_from_row(_cellmap(header, row)) for row in grid[1:] if any(str(c).strip() for c in row)]
    return Worklog(entries)


# ── 렌더 계산('7일 넘은 진행') ────────────────────────────────────
def is_overdue(entry: WorklogEntry, *, today: date) -> bool:
    """진행 상태인데 일자가 today - OVERDUE_DAYS 보다 이르면 지연(렌더 표시용·저장 안 함)."""
    if entry.status != WL_ACTIVE or not _ISO_DATE.fullmatch(entry.date or ""):
        return False
    return entry.date < (today - timedelta(days=OVERDUE_DAYS)).isoformat()


def overdue(wl: Worklog, *, today: date) -> list[WorklogEntry]:
    return [e for e in wl.entries if is_overdue(e, today=today)]


# ── 쓰기(append) ─────────────────────────────────────────────────
def _line(e: WorklogEntry) -> list[str]:
    return [str(e.no), e.date, e.author, e.account_id, e.product, e.content, e.followup, e.status]


_HEADER_BG = {"red": 0xB7 / 255, "green": 0xC9 / 255, "blue": 0xE8 / 255}


def _format_requests(gid: int) -> list[dict]:
    """헤더 고정·굵게·배경·상태 칸 선택목록·기본 필터(registry 서식 관례와 동일, 축소판)."""
    c_status = HEADER.index("상태")
    return [
        {"updateSheetProperties": {"properties": {"sheetId": gid, "gridProperties": {"frozenRowCount": 1}},
                                   "fields": "gridProperties.frozenRowCount"}},
        {"repeatCell": {"range": {"sheetId": gid, "startRowIndex": 0, "endRowIndex": 1,
                                  "startColumnIndex": 0, "endColumnIndex": len(HEADER)},
                        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "backgroundColor": _HEADER_BG}},
                        "fields": "userEnteredFormat(textFormat,backgroundColor)"}},
        {"setDataValidation": {"range": {"sheetId": gid, "startRowIndex": 1,
                                         "startColumnIndex": c_status, "endColumnIndex": c_status + 1},
                               "rule": {"condition": {"type": "ONE_OF_LIST",
                                                      "values": [{"userEnteredValue": v} for v in STATUS_CHOICES]},
                                        "strict": False, "showCustomUi": True}}},
        {"setBasicFilter": {"filter": {"range": {"sheetId": gid, "startRowIndex": 0,
                                                 "startColumnIndex": 0, "endColumnIndex": len(HEADER)}}}},
    ]


def init_sheet(client, log=None) -> None:
    """업무일지 시트를 만들고(없으면) 헤더·서식을 한 번 건다."""
    log = log or (lambda m: None)
    ids = client.ensure_sheets([SHEET])
    client.write_values(SHEET, [list(HEADER)], raw=True)
    client.batch_update(_format_requests(ids[SHEET]))
    log(f"== [업무일지] 시트 생성·서식 적용: {SHEET} ==")


def _insert_top(client, lines: list[list[str]]) -> None:
    """헤더 아래(맨 위)에 새 줄을 끼워 넣는다 — 최신이 위, 기존 줄 보존."""
    gid = client.sheet_id(SHEET)
    client.batch_update([{"insertDimension": {"range": {"sheetId": gid, "dimension": "ROWS",
                                                        "startIndex": 1, "endIndex": 1 + len(lines)},
                                              "inheritFromBefore": False}}])
    client.write_values(SHEET, lines, start="A2", raw=True)


def append(client, *, account_id: str, content: str, status: str, author: str, product: str = "",
           followup: str = "", now: datetime | None = None, dry_run: bool = False, on_log=None,
           lock_path: str | Path = DEFAULT_LOCK) -> WorklogEntry:
    """업무일지에 한 줄 추가(최신이 위). 일자·작성자·번호는 앱이 채운다. 값이 규칙에 안 맞으면 WorklogError.

    반환 = 추가된(또는 미리보기면 추가될) WorklogEntry. dry_run 이면 쓰지 않고 줄만 돌려준다.
    쓰기는 원장 잠금 안에서만 — 다른 업무일지 쓰기가 끝나지 않으면 RegistryLockError(아무것도 안 씀)."""
    log = on_log or (lambda m: None)
    now = now or datetime.now()
    _validate(account_id, content, status)
    entry_date = now.date().isoformat()
    with _lock(dry_run, lock_path, log):
        wl = load(client)
        check_integrity(wl)
        entry = WorklogEntry(no=wl.next_no(), date=entry_date, author=canon(author),
                             account_id=account_id, product=product, content=content,
                             followup=followup, status=status)
        if not dry_run:
            if SHEET not in client.sheet_titles():
                init_sheet(client, log)
            _insert_top(client, [_line(entry)])
    log(f"== [업무일지] {'미리보기(저장 안 함) ' if dry_run else ''}#{entry.no} {account_id}"
        + (f"/{product}" if product else "") + f" [{status}] ==")
    return entry


def _lock(dry_run: bool, lock_path, log):
    from contextlib import nullcontext
    return nullcontext() if dry_run else registry_lock(lock_path, on_log=log)
