"""셀독등록원장 — 열 정의·값 정규화·관리대장 파서(원장용 스냅샷). SSOT=designs/LEDGER_REGISTRY.md.

관리대장(셀독리스트)을 **원장 비교용 스냅샷**으로 읽는다. 기존 `input_list._parse_grid`(수집 대상 추출)와 달리
취소선·삭제된 계정/상품도 **줄 존재·중지 여부**를 그대로 담고, 계약금·체험단주체·그로스 원값을 함께 읽는다.
헤더 탐지·취소선·자리표시 판정 헬퍼는 input_list 것을 재사용한다(같은 대장 규칙).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from openpyxl.utils import get_column_letter

from . import config
from .input_list import (_PW_ALIASES, _REQUIRED, _alias_index, _cell, _find_header_row, _is_discontinued,
                         _is_real_product_name, _norm, _status_discontinued)

# ── 시트·열 ──────────────────────────────────────────────────────
SHEET_MAIN = "셀독원장"
SHEET_ACCT = "계정이력"
SHEET_PROD = "상품이력"
SHEET_GROWTH = "그로스이력"
SHEET_SYNC = "동기화기록"
HISTORY_SHEETS = (SHEET_ACCT, SHEET_PROD, SHEET_GROWTH)
ALL_SHEETS = (SHEET_MAIN, *HISTORY_SHEETS, SHEET_SYNC)

ST_ACTIVE = "관리중"
ST_STOPPED = "관리중단"

ACCOUNT_FIELDS = ("대표자명", "사업자명", "비밀번호", "계약금", "체험단주체")
GROWTH_FIELDS = ("그로스 요청수량", "그로스 작업수량", "그로스 박스", "그로스 파레트",
                 "그로스 완료일자", "그로스 출고일자")
STOCK_FIELD = "그로스 재고"

MAIN_HEADER = ("관리상태", "중단일", "대표자명", "사업자명", "계정아이디", "비밀번호", "계약금", "체험단주체",
               "상품명", STOCK_FIELD, *GROWTH_FIELDS, "등록일", "최종변경일", "쿠팡확인", "쿠팡확인일")

_HIST_COMMON_HEAD = ("번호", "실행번호", "일시", "효력일", "계정아이디", "사업자명")
_HIST_COMMON_TAIL = ("변동유형", "항목", "이전값", "변경값", "출처", "확인상태", "확인자", "확인일", "비고")
HIST_HEADER = {
    SHEET_ACCT: (*_HIST_COMMON_HEAD, *_HIST_COMMON_TAIL),
    SHEET_PROD: (*_HIST_COMMON_HEAD, "상품명", *_HIST_COMMON_TAIL),
    SHEET_GROWTH: (*_HIST_COMMON_HEAD, "상품명", *_HIST_COMMON_TAIL),
}
SYNC_HEADER = ("실행번호", "실행일시", "대장 계정", "대장 상품", "원장 계정", "원장 상품", "신규계정", "신규상품",
               "계정수정", "그로스수정", "관리중단", "재개", "확인필요", "결과")

# ── 변동유형·확인상태 ────────────────────────────────────────────
K_INIT = "최초등록"
K_NEW_ACCT = "신규계정"
K_NEW_PROD = "신규상품"
K_EDIT = "수정"
K_STOP = "관리중단"
K_RESUME = "재개"
K_RENAME_PROD = "상품명변경"
K_RENAME_ACCT = "계정아이디변경"
K_CONFIRMED = "확인완료"
K_REJECTED = "반려"

C_AUTO = "자동반영"
C_PENDING = "확인필요"
C_APPROVE = "승인"
C_REJECT = "반려"
CONFIRM_CHOICES = (C_AUTO, C_PENDING, C_APPROVE, C_REJECT)

# 쿠팡확인 값(§4-1) — ①판매수집 로그인 결과. 이력 없음(최신값만).
COUPANG_CHECK_VALUES = ("확인됨", "미등록", "판매중(불일치)", "판매중지", "로그인실패", "비밀번호불일치")

ITEM_STATUS = "관리상태"
ITEM_PROD_NAME = "상품명"
ITEM_ACCT_ID = "계정아이디"


_NUM_COMMA = re.compile(r"-?\d{1,3}(,\d{3})+(\.\d+)?")
_DATE_TEXT = re.compile(r"(\d{2}|\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})\.?")


def _canon_date_text(s: str) -> str:
    """'26.8.18'·'26.08.18.'·'2026/8/18' → '2026-08-18'. 실제 날짜가 아니면 원문 그대로."""
    m = _DATE_TEXT.fullmatch(s)
    if not m:
        return s
    y, mo, d = (int(g) for g in m.groups())
    try:
        return date(y + 2000 if y < 100 else y, mo, d).isoformat()
    except ValueError:
        return s


def canon(v) -> str:
    """비교·저장용 정규화 — 표기만 다른 값을 같게 만든다: 앞뒤·연속 공백, 90.0, 날짜객체, 천단위 쉼표 숫자,
    날짜 글자(26.8.18 등 → YYYY-MM-DD). 실측(2026-09-28): 같은 대장을 엑셀 백업은 31508400·2026-08-18,
    구글시트 표시값은 31,508,400·26.8.18 로 읽어 가짜 '수정' 이력이 생겼음. '불가'·'전량' 등 글자는 그대로."""
    if v is None:
        return ""
    if isinstance(v, datetime):
        v = v.date()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = " ".join(str(v).split())
    if _NUM_COMMA.fullmatch(s):
        s = s.replace(",", "")
    if s.endswith(".0") and s[:-2].lstrip("-").isdigit():
        s = s[:-2]
    return _canon_date_text(s)


def canon_pw(v) -> str:
    """비밀번호는 원문 그대로(공백 정리·숫자 변환 안 함 — 로그인 값이 바뀌면 안 됨)."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v)


# ── 데이터 ───────────────────────────────────────────────────────
@dataclass
class HistRow:
    """이력 1줄(계정이력·상품이력·그로스이력 공통). product 는 계정이력에선 ''."""
    sheet: str
    run_id: str
    ts: str
    eff: str
    account_id: str
    biz: str
    kind: str
    product: str = ""
    item: str = ""
    old: str = ""
    new: str = ""
    source: str = ""
    confirm: str = C_AUTO
    confirmer: str = ""
    confirm_date: str = ""
    note: str = ""
    no: int = 0


@dataclass
class RegRow:
    """원장 1줄(계정×상품). 관리상태·중단일은 이력에서 계산한다(저장 열은 렌더 결과)."""
    account_id: str
    product: str
    acct: dict = field(default_factory=dict)
    growth: dict = field(default_factory=dict)
    stock: str = ""
    registered: str = ""
    changed: str = ""
    coupang: str = ""
    coupang_date: str = ""

    @property
    def key(self) -> tuple[str, str]:
        return (self.account_id, self.product)


@dataclass
class SnapProduct:
    name: str
    row_no: int
    growth: dict
    stock: str
    stopped: bool
    reason: str = ""


@dataclass
class SnapAccount:
    account_id: str
    row_no: int
    fields: dict
    field_rows: dict = field(default_factory=dict)
    products: dict = field(default_factory=dict)      # 이름 → SnapProduct (대장 순서)
    appearances: int = 0
    stopped_appearances: int = 0
    reason: str = ""

    @property
    def stopped(self) -> bool:
        return self.appearances > 0 and self.stopped_appearances == self.appearances


@dataclass
class LedgerSnapshot:
    sheet: str
    accounts: dict = field(default_factory=dict)      # 계정아이디 → SnapAccount (대장 순서)
    warnings: list = field(default_factory=list)
    cols: dict = field(default_factory=dict)          # 원장 항목 → 대장 열(0-based)

    def ref(self, item: str, row_no: int) -> str:
        """이력 '출처' — 대장 시트·셀 위치(예 '셀독리스트 AJ15')."""
        col = self.cols.get(item)
        return f"{self.sheet} {get_column_letter(col + 1)}{row_no}" if col is not None else f"{self.sheet} {row_no}행"


# ── 관리대장 파서 ────────────────────────────────────────────────
_OPT_ALIASES = {
    "대표자명": (config.IN_COL_REPRESENTATIVE,),
    "비밀번호": _PW_ALIASES,
    "계약금": ("계약금",),
    "체험단주체": ("체험단주체",),
    "그로스 요청수량": config.IN_ALIASES_INB_REQQTY,
    "그로스 작업수량": config.IN_ALIASES_INB_WORKQTY,
    "그로스 박스": config.IN_ALIASES_INB_BOX,
    "그로스 파레트": config.IN_ALIASES_INB_PALLET,
    "그로스 완료일자": config.IN_ALIASES_INB_DONEDATE,
    "그로스 출고일자": config.IN_ALIASES_INB_SHIPDATE,
    "상태": config.IN_ALIASES_STATUS,
}


def _ledger_columns(header: list[str]) -> tuple[dict, list[str]]:
    """헤더 이름으로 열 위치를 찾는다(열이 옮겨져도 동작). 같은 이름이 여럿이면 **앞쪽**(그로스 구역)."""
    cols = {"사업자명": header.index(config.IN_COL_BUSINESS),
            "계정아이디": header.index(config.IN_COL_ACCOUNT_ID),
            "상품명": header.index(config.IN_COL_PRODUCT)}
    norm = [h.lower().replace(" ", "") for h in header]
    for item, aliases in _OPT_ALIASES.items():
        i = _alias_index(norm, aliases)
        if i is not None:
            cols[item] = i
    stock = next((i for i, h in enumerate(norm) if h.startswith("그로스재고")), None)
    if stock is not None:
        cols[STOCK_FIELD] = stock
    missing = [k for k in (*ACCOUNT_FIELDS, STOCK_FIELD, *GROWTH_FIELDS) if k not in cols]
    return cols, missing


def _strike_fn(strike_grid):
    def struck(row_no: int, col0) -> bool:
        r = row_no - 1
        if not strike_grid or col0 is None or r < 0 or r >= len(strike_grid):
            return False
        srow = strike_grid[r]
        return bool(srow[col0]) if 0 <= col0 < len(srow) else False
    return struck


def _take_account(snap: LedgerSnapshot, row, row_no: int, aid: str, rep: str, stop_reason: str) -> SnapAccount:
    a = snap.accounts.get(aid)
    if a is None:
        a = SnapAccount(aid, row_no, {f: "" for f in ACCOUNT_FIELDS})
        snap.accounts[aid] = a
    a.appearances += 1
    if stop_reason:
        a.stopped_appearances += 1
        a.reason = stop_reason
    cols = snap.cols
    values = {"대표자명": rep, "사업자명": canon(_cell(row, cols["사업자명"])),
              "비밀번호": canon_pw(_cell(row, cols.get("비밀번호"))),
              "계약금": canon(_cell(row, cols.get("계약금"))),
              "체험단주체": canon(_cell(row, cols.get("체험단주체")))}
    for f, v in values.items():
        if v and not a.fields[f]:                  # 첫 값 우선(같은 계정 재등장 시 빈 칸만 채움)
            a.fields[f] = v
            a.field_rows[f] = row_no
    return a


def _take_product(snap: LedgerSnapshot, a: SnapAccount, row, row_no: int, name: str, status_disc: bool,
                  on_account_row: bool, struck) -> None:
    if not _is_real_product_name(name):
        snap.warnings.append(f"{row_no}행 상품명 아님 '{name}' (계정 {a.account_id}) — 제외")
        return
    if name in a.products:
        snap.warnings.append(f"{row_no}행 같은 상품명 중복 '{name}' (계정 {a.account_id}) — 첫 줄만 사용")
        return
    cols = snap.cols
    reason = ""
    if struck(row_no, cols["상품명"]):
        reason = f"대장 취소선 {snap.ref('상품명', row_no).split(' ', 1)[1]}"
    elif status_disc and not on_account_row:
        reason = "대장 상태 컬럼"
    elif _is_discontinued(name):
        reason = "상품명 판매중지 표기"
    a.products[name] = SnapProduct(
        name, row_no, {g: canon(_cell(row, cols.get(g))) for g in GROWTH_FIELDS},
        canon(_cell(row, cols.get(STOCK_FIELD))), bool(reason), reason)


def parse_ledger(rows: list, strike_grid: list | None = None, sheet: str = "셀독리스트") -> LedgerSnapshot:
    """관리대장 값 격자(+취소선 격자) → LedgerSnapshot. 헤더 못 찾으면 ValueError(동기화 중단)."""
    header, hrow = _find_header_row(rows, lambda h: all(n in h for n in _REQUIRED))
    if hrow < 0:
        raise ValueError(f"관리대장 상단에서 헤더(사업자명·계정아이디·상품명)를 찾지 못했습니다 — 시트 '{sheet}'")
    cols, missing = _ledger_columns(header)
    snap = LedgerSnapshot(sheet, cols=cols)
    if missing:
        snap.warnings.append(f"관리대장에 없는 열(빈 값으로 처리): {', '.join(missing)}")
    struck = _strike_fn(strike_grid)
    cur: SnapAccount | None = None
    cur_rep = ""
    for row_no, row in enumerate(rows[hrow + 1:], start=hrow + 2):
        rep = canon(_cell(row, cols.get("대표자명")))
        cur_rep = rep or cur_rep
        status_disc = _status_discontinued(_cell(row, cols.get("상태"))) if "상태" in cols else False
        aid = _norm(_cell(row, cols["계정아이디"]))
        if aid:
            stop = ("대장 상태 컬럼" if status_disc else
                    "대장 취소선" if struck(row_no, cols["계정아이디"]) else "")
            cur = _take_account(snap, row, row_no, aid, cur_rep, stop)
        name = _norm(_cell(row, cols["상품명"])).split("\n")[0].strip()
        name = " ".join(name.split())
        if not name:
            continue
        if cur is None:
            snap.warnings.append(f"{row_no}행 소속 계정 없이 상품 '{name}' — 제외")
            continue
        _take_product(snap, cur, row, row_no, name, status_disc, bool(aid), struck)
    return snap
