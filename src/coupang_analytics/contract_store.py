"""계약 원장 — 계약서 버전 이력·as_of 복원·유효/만료/해지 replay·민감 가림. SSOT=DOMAIN_D8_SETTLEMENT_PHASE23 §4.1·IO 11-3.

계약은 개정될 수 있어 **버전 이력**(계약 = (위탁계정, 사업) 꼬리표 단위·개정=새 버전 줄)으로 쌓는다. 그 시점의 유효
계약 = 효력일 ≤ 기준일인 최신 내용 버전(registry as_of 패턴). 유효/만료/해지는 이력에서 계산한다(계약기간·해지 버전).
'30일 전부터 만료 예정'은 저장 값이 아니라 렌더 계산(expiring_soon). 3단계 계약 정산(settlement.achievement)의 입력
저장소다 — 수수료·약정이익금은 셀독등록원장이 아니라 여기에 둔다(원장 책임 분리).

민감(가림·IO 11-3): 정산계좌·수탁자군은 기본 가림, 원문은 대표/정산담당만(view). 로그·백업에 원문 금지.
쓰기는 registry_lock(셀독원장과 별도 lock 파일). 실패는 예외로 전파(silent 금지). 클라이언트는 덕타이핑(GSheetClient).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .registry_lock import registry_lock
from .registry_model import canon

SHEET = "계약"
DEFAULT_LOCK = "output/_계약.lock"
EXPIRING_DAYS = 30                          # 계약기간 끝 이 날수 안이면 '만료 예정'(IO 11-3 검사규칙)

KIND_INIT = "최초"
KIND_AMEND = "개정"
KIND_TERMINATE = "해지"
CONTENT_KINDS = (KIND_INIT, KIND_AMEND)     # 내용(13칸) 스냅샷을 담는 버전(해지는 표식만)

ST_VALID = "유효"
ST_EXPIRED = "만료"
ST_TERMINATED = "해지"

# 내용 칸(IO 11-3 13칸을 원자 필드로 분해). 위탁계정·사업은 키(열 별도)라 여기에 없음.
CONTENT_FIELDS = (
    "사업자명", "대표자명", "대상상품", "계약서종류", "적용플랫폼",
    "계약일자", "계약기간시작", "계약기간끝",
    "수익배분", "수익기준", "수익계산식",
    "계약금", "계약단가", "계약수량", "계약금액",
    "광고비부담", "재고배송부담",
    "정산시점", "결제조건", "귀속기준일",
    "정산계좌", "수탁자", "수탁자대표자", "수탁자사업자번호",
    "해지조건", "특약", "계약서위치",
)
# 민감(가림) — 원문은 대표/정산담당만. 로그·결과·백업 평문 금지(IO 11-3).
MASKED_FIELDS = ("정산계좌", "수탁자", "수탁자대표자", "수탁자사업자번호")
RAW_VIEW_ROLES = ("대표", "정산담당")
MASK = "●●●●"

# 필수(IO 11-3) — 신규/개정 내용 버전에서 반드시 채워져야 함.
_REQUIRED = ("사업자명", "대표자명", "계약일자", "계약기간시작", "계약기간끝",
             "수익배분", "수익기준", "수익계산식")

HEADER = ("번호", "효력일", "변동유형", "위탁계정", "사업", *CONTENT_FIELDS, "비고")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class ContractError(Exception):
    """계약 입력·원장이 규칙에 맞지 않음(아무것도 쓰지 않음)."""


@dataclass
class ContractVersion:
    """계약 1버전. fields = CONTENT_FIELDS 전체(해지 버전은 비어 있을 수 있음)."""
    no: int
    eff: str
    kind: str
    account_id: str
    business: str
    fields: dict = field(default_factory=dict)
    note: str = ""

    @property
    def key(self) -> tuple[str, str]:
        return (self.account_id, self.business)


@dataclass
class ContractLedger:
    versions: list[ContractVersion] = field(default_factory=list)

    def keys(self) -> list[tuple[str, str]]:
        return list(dict.fromkeys(v.key for v in self.versions))

    def next_no(self) -> int:
        return max((v.no for v in self.versions), default=0) + 1


def _order(v: ContractVersion) -> tuple[str, int]:
    """시간순 키 — 같은 효력일이면 번호가 큰(나중 제출) 버전이 뒤."""
    return (v.eff, v.no)


# ── 검증 ─────────────────────────────────────────────────────────
def _validate(account_id: str, business: str, fields: dict) -> None:
    if not account_id:
        raise ContractError("계약 '위탁계정'은 필수입니다")
    if not business:
        raise ContractError("계약 '사업'(꼬리표)은 필수입니다")
    for f in _REQUIRED:
        if not str(fields.get(f, "")).strip():
            raise ContractError(f"계약 필수 칸 '{f}' 이(가) 비었습니다")
    s, e = str(fields.get("계약기간시작", "")), str(fields.get("계약기간끝", ""))
    if _ISO_DATE.fullmatch(s) and _ISO_DATE.fullmatch(e) and not e > s:
        raise ContractError(f"계약기간 끝({e})이 시작({s})보다 뒤여야 합니다")


def check_integrity(ledger: ContractLedger) -> None:
    """번호가 1..n 연속이어야 한다(누락·중복 = 누가 줄을 지웠거나 손수정 → 쓰기 중단)."""
    nos = sorted(v.no for v in ledger.versions)
    if nos != list(range(1, len(nos) + 1)):
        raise ContractError(f"계약 원장 번호가 1..n 연속이 아님(누락/중복): {nos[:10]}")


# ── 상태 계산(이력 replay) ───────────────────────────────────────
def _content_at(ledger: ContractLedger, key: tuple[str, str], at: str) -> ContractVersion | None:
    content = [v for v in ledger.versions if v.key == key and v.kind in CONTENT_KINDS and v.eff <= at]
    return max(content, key=_order) if content else None


def status(ledger: ContractLedger, key: tuple[str, str], at: str) -> str | None:
    """그 날짜 기준 계약 상태(유효/만료/해지). 아직 시작 전(내용 버전 없음)이면 None."""
    latest = _content_at(ledger, key, at)
    if latest is None:
        return None
    term = [v for v in ledger.versions
            if v.key == key and v.kind == KIND_TERMINATE and v.eff <= at and _order(v) >= _order(latest)]
    if term:
        return ST_TERMINATED
    end = str(latest.fields.get("계약기간끝", ""))
    if _ISO_DATE.fullmatch(end) and end < at:
        return ST_EXPIRED
    return ST_VALID


def as_of(ledger: ContractLedger, key: tuple[str, str], at: str) -> dict | None:
    """그 날짜의 유효 계약 내용(+상태). 아직 계약 전이면 None. 민감 칸은 원문(표시용 가림은 view)."""
    latest = _content_at(ledger, key, at)
    if latest is None:
        return None
    return {"위탁계정": key[0], "사업": key[1], **latest.fields, "상태": status(ledger, key, at)}


def expiring_soon(ledger: ContractLedger, key: tuple[str, str], *, today: date, within: int = EXPIRING_DAYS) -> bool:
    """유효 계약인데 계약기간 끝이 within 일 안이면 True(렌더 표시용·저장 안 함)."""
    at = today.isoformat()
    if status(ledger, key, at) != ST_VALID:
        return False
    latest = _content_at(ledger, key, at)
    end = str(latest.fields.get("계약기간끝", "")) if latest else ""
    return bool(_ISO_DATE.fullmatch(end)) and at <= end <= (today + timedelta(days=within)).isoformat()


# ── 가림(민감) ───────────────────────────────────────────────────
def view(contract: dict, *, role: str) -> dict:
    """as_of 결과를 역할에 맞게 가린다 — 대표/정산담당만 민감 칸 원문, 그 외 ●●●●(값 있을 때만)."""
    if role in RAW_VIEW_ROLES:
        return dict(contract)
    out = dict(contract)
    for f in MASKED_FIELDS:
        if str(out.get(f, "")).strip():
            out[f] = MASK
    return out


# ── 읽기 ─────────────────────────────────────────────────────────
def _cellmap(header: list, row: list) -> dict:
    return {h: (row[i] if i < len(row) else "") for i, h in enumerate(header)}


def _version_from_row(d: dict) -> ContractVersion:
    raw_no = str(d.get("번호", "")).strip()
    try:
        no = int(raw_no)
    except ValueError as exc:
        raise ContractError(f"계약 원장 '번호' 칸이 숫자가 아님: '{raw_no}'") from exc
    return ContractVersion(no=no, eff=str(d.get("효력일", "")), kind=str(d.get("변동유형", "")),
                           account_id=str(d.get("위탁계정", "")), business=str(d.get("사업", "")),
                           fields={f: str(d.get(f, "")) for f in CONTENT_FIELDS}, note=str(d.get("비고", "")))


def load(client) -> ContractLedger:
    if SHEET not in client.sheet_titles():
        return ContractLedger()
    grid = client.read_values(SHEET) or []
    if not grid:
        return ContractLedger()
    header = [str(h) for h in grid[0]]
    vers = [_version_from_row(_cellmap(header, row)) for row in grid[1:] if any(str(c).strip() for c in row)]
    return ContractLedger(vers)


# ── 쓰기(버전 추가) ──────────────────────────────────────────────
def _line(v: ContractVersion) -> list[str]:
    return [str(v.no), v.eff, v.kind, v.account_id, v.business,
            *[v.fields.get(f, "") for f in CONTENT_FIELDS], v.note]


_HEADER_BG = {"red": 0xB7 / 255, "green": 0xC9 / 255, "blue": 0xE8 / 255}


def _format_requests(gid: int) -> list[dict]:
    return [
        {"updateSheetProperties": {"properties": {"sheetId": gid, "gridProperties": {"frozenRowCount": 1}},
                                   "fields": "gridProperties.frozenRowCount"}},
        {"repeatCell": {"range": {"sheetId": gid, "startRowIndex": 0, "endRowIndex": 1,
                                  "startColumnIndex": 0, "endColumnIndex": len(HEADER)},
                        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "backgroundColor": _HEADER_BG}},
                        "fields": "userEnteredFormat(textFormat,backgroundColor)"}},
        {"setBasicFilter": {"filter": {"range": {"sheetId": gid, "startRowIndex": 0,
                                                 "startColumnIndex": 0, "endColumnIndex": len(HEADER)}}}},
    ]


def init_sheet(client, log=None) -> None:
    log = log or (lambda m: None)
    ids = client.ensure_sheets([SHEET])
    client.write_values(SHEET, [list(HEADER)], raw=True)
    client.batch_update(_format_requests(ids[SHEET]))
    log(f"== [계약] 시트 생성·서식 적용: {SHEET} ==")


def _insert_top(client, lines: list[list[str]]) -> None:
    gid = client.sheet_id(SHEET)
    client.batch_update([{"insertDimension": {"range": {"sheetId": gid, "dimension": "ROWS",
                                                        "startIndex": 1, "endIndex": 1 + len(lines)},
                                              "inheritFromBefore": False}}])
    client.write_values(SHEET, lines, start="A2", raw=True)


def _canon_fields(fields: dict) -> dict:
    return {f: canon(fields.get(f, "")) for f in CONTENT_FIELDS}


def record(client, *, account_id: str, business: str, fields: dict | None = None, eff: str,
           terminate: bool = False, note: str = "", dry_run: bool = False, on_log=None,
           lock_path: str | Path = DEFAULT_LOCK) -> ContractVersion:
    """계약 버전 1줄 추가(최신이 위). 첫 버전=최초·이후=개정·terminate=해지. 내용 버전은 필수 칸·기간을 검증.

    eff = 효력일(YYYY-MM-DD·이 버전이 유효해지는 날). 반환 = 추가된(미리보기면 추가될) ContractVersion.
    쓰기는 원장 잠금 안에서만 — 다른 계약 쓰기가 끝나지 않으면 RegistryLockError(아무것도 안 씀)."""
    log = on_log or (lambda m: None)
    fields = fields or {}
    if not _ISO_DATE.fullmatch(str(eff)):
        raise ContractError(f"계약 효력일 '{eff}' 은 YYYY-MM-DD 형식이 아닙니다")
    if not terminate:
        _validate(account_id, business, fields)
    elif not (account_id and business):
        raise ContractError("계약 해지에도 위탁계정·사업은 필요합니다")
    with _lock(dry_run, lock_path, log):
        ledger = load(client)
        check_integrity(ledger)
        existing = [v for v in ledger.versions if v.key == (account_id, business)]
        kind = KIND_TERMINATE if terminate else (KIND_AMEND if existing else KIND_INIT)
        ver = ContractVersion(no=ledger.next_no(), eff=eff, kind=kind, account_id=account_id,
                              business=business, fields={} if terminate else _canon_fields(fields), note=note)
        if not dry_run:
            if SHEET not in client.sheet_titles():
                init_sheet(client, log)
            _insert_top(client, [_line(ver)])
    log(f"== [계약] {'미리보기(저장 안 함) ' if dry_run else ''}#{ver.no} {account_id}/{business} [{kind}] ==")
    return ver


def _lock(dry_run: bool, lock_path, log):
    from contextlib import nullcontext
    return nullcontext() if dry_run else registry_lock(lock_path, on_log=log)
