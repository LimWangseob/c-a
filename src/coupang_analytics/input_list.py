"""입력 분석용 엑셀 파싱 (계정·상품·옵션 계층).

필수 컬럼: 대표자명 | 사업자명 | 계정아이디 | 상품명
선택 컬럼: 옵션 | vendorItemId | productId  (옵션별 추적용)
- `계정아이디` 채워진 행 = 새 계정. `상품명` 채워진 행 = 새 상품.
- 옵션별 추적: 상품 아래 `옵션`(+vendorItemId) 행을 나열. 한 옵션에 vid 여러 개면 콤마 구분.
- 옵션 행이 없으면 상품에 기본 옵션 1개(라벨 "", vid 세트=상품행 vid).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

from . import config


@dataclass
class Option:
    label: str                                   # 옵션명(예: 그린). 단일/통합이면 ""
    vendor_item_ids: list[str] = field(default_factory=list)
    product_ids: list[str] = field(default_factory=list)


@dataclass
class Product:
    name: str                       # 등록 상품명(입력·리포트 기준, 짧을 수 있음)
    options: list[Option] = field(default_factory=list)
    title: str = ""                 # 고객이 보는 전체 노출제목(발견 시 채움). 비면 name 사용
    kind: str = ""                  # 계약 상품(로켓그로스)/개인 상품(판매자배송) — 발견 시 API로 판별
    mkt_start: str = ""             # 마케팅 시작일(관리대장 입력) — 그 상품만 매일 수집·비고·배경색
    mkt_end: str = ""               # 마케팅 종료일
    mkt_mon: str = ""               # 모니터링 종료일(이후 수집 중단)

    @property
    def display_title(self) -> str:
        """키워드 씨앗·제목처방에 쓸 대표 제목 — 전체 노출제목이 있으면 그것, 없으면 등록명."""
        return self.title or self.name


@dataclass
class Account:
    account_id: str
    representative: str
    business_name: str
    products: list[Product] = field(default_factory=list)

    @property
    def label(self) -> str:
        return self.business_name or self.representative or self.account_id


@dataclass
class InputList:
    accounts: list[Account]
    errors: list[str]
    struck: list[str] = field(default_factory=list)   # 취소선으로 제외된 계정/상품(해지·품절·판매중지)


def _norm(value) -> str:
    return str(value).strip() if value is not None else ""


def _split_ids(value) -> list[str]:
    return [t for t in re.split(r"[,\s;]+", _norm(value)) if t.isdigit()]


# 헤더가 1행이 아닐 수 있음(예: 셀독 관리대장은 1행=예시값, 2행=실제 헤더). 상단 몇 행을 스캔.
_HEADER_SCAN_ROWS = 8


def _find_header_row(rows: list, match) -> tuple[list[str], int]:
    """상단 _HEADER_SCAN_ROWS 행 중 match(정규화헤더)가 참인 첫 행을 헤더로 반환.
    반환: (정규화 헤더 셀 리스트, 0-based 행 인덱스). 못 찾으면 ([], -1)."""
    for r in range(min(len(rows), _HEADER_SCAN_ROWS)):
        header = [_norm(c) for c in rows[r]]
        if match(header):
            return header, r
    return [], -1


def _alias_index(norm_header: list[str], aliases) -> int | None:
    for i, h in enumerate(norm_header):
        if h in aliases:
            return i
    return None


def _column_index(header: list[str]) -> dict[str, int]:
    """컬럼 위치 해석 — **가져오는 값 = 사업자·계정ID·상품**(필수 3개는 앞서 존재 확인됨).

    대표자명은 **선택**(있으면 빈 사업자명 시트의 라벨 폴백에만 사용). 옵션/vendorItemId/productId 는
    이 관리대장에 없고 실제 미사용(vid 는 라이브 판매수집에서 확보)이라 **파싱하지 않는다**(입력 정리).
    """
    idx: dict[str, int] = {}
    for name in (config.IN_COL_BUSINESS, config.IN_COL_ACCOUNT_ID, config.IN_COL_PRODUCT):
        idx[name] = header.index(name)
    if config.IN_COL_REPRESENTATIVE in header:      # 대표자명은 선택
        idx[config.IN_COL_REPRESENTATIVE] = header.index(config.IN_COL_REPRESENTATIVE)
    norm = [h.lower().replace(" ", "") for h in header]   # 마케팅·상태 컬럼(선택)은 별칭으로 탐색
    for key, aliases in (("mkt_start", config.IN_ALIASES_MKT_START),
                         ("mkt_end", config.IN_ALIASES_MKT_END),
                         ("mkt_mon", config.IN_ALIASES_MKT_MON),
                         ("status", config.IN_ALIASES_STATUS)):
        i = _alias_index(norm, aliases)
        if i is not None:
            idx[key] = i
    return idx


def _cell(row, i):
    return row[i] if (i is not None and len(row) > i) else None


def _norm_date(v) -> str:
    """마케팅 날짜 셀 → 문자열. 엑셀 날짜(datetime)면 YYYY-MM-DD, 아니면 일반 정규화."""
    from datetime import date as _d, datetime as _dtm
    if isinstance(v, _dtm):
        return v.date().isoformat()
    if isinstance(v, _d):
        return v.isoformat()
    return _norm(v)


def _finalize(product: Product | None) -> None:
    """옵션이 하나도 없는 상품엔 기본 옵션(라벨 "") 1개를 채운다."""
    if product is not None and not product.options:
        product.options.append(Option(""))


_ID_ALIASES = ("계정아이디", "아이디", "id", "계정id", "account", "accountid")
_PW_ALIASES = ("비밀번호", "비번", "password", "pw", "passwd")


def parse_password_file(path: str | Path) -> dict[str, str]:
    """계정아이디+비밀번호 컬럼이 있는 엑셀 → {계정아이디: 비밀번호}. 계정 블록/전용파일 모두 지원."""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))

    def _match(header: list[str]) -> bool:
        norm = [h.lower().replace(" ", "") for h in header]
        return _alias_index(norm, _ID_ALIASES) is not None and _alias_index(norm, _PW_ALIASES) is not None

    header, hrow = _find_header_row(rows, _match)
    if hrow < 0:
        raise ValueError("비밀번호 파일에 '계정아이디'/'비밀번호' 컬럼이 필요합니다(상단 8행 내 헤더 없음).")
    norm = [h.lower().replace(" ", "") for h in header]
    i_id, i_pw = _alias_index(norm, _ID_ALIASES), _alias_index(norm, _PW_ALIASES)
    out: dict[str, str] = {}
    for row in rows[hrow + 1:]:
        aid = _norm(_cell(row, i_id))
        raw = _cell(row, i_pw)
        pw = str(raw) if raw is not None else ""
        if aid and pw:
            out[aid] = pw
    return out


_DISCONTINUED = ("판매중지", "판매중단", "판매종료", "판매불가")   # 대장 텍스트 마커(판매부진=계속 판매라 제외)


def _is_discontinued(name: str) -> bool:
    """상품명에 판매중지 계열 마커가 있으면 True → 추적 제외(쿠팡 판매중지분)."""
    n = str(name)
    return any(m in n for m in _DISCONTINUED)


def _status_discontinued(status) -> bool:
    """관리대장 '상태' 컬럼 값이 판매중지/삭제 계열이면 True.

    취소선과 **병행**하는 감지원 — 취소선이 없어도 이 컬럼 값으로 계정/상품 제외를 판정한다(둘 중 하나면 제외).
    부분일치(예 '판매중지'·'일시중지'·'삭제됨'). 빈 값·'정상'·'판매중'·'판매부진'은 제외 아님.
    """
    n = str(status).replace(" ", "") if status is not None else ""
    if not n:
        return False
    return any(m in n for m in config.IN_STATUS_DISCONTINUED)


def _cell_struck(ws, row_no: int, col0: int | None) -> bool:
    """그 셀에 취소선(strike) 서식이 있으면 True. 취소선 = 해지·품절·판매중지 → 제외 표시."""
    if col0 is None:
        return False
    try:
        return bool(getattr(ws.cell(row_no, col0 + 1).font, "strike", False))
    except Exception:
        return False


def _load_for_parse(path):
    """(워크시트, 취소선감지가능?) 반환.

    값은 반드시 read_only 로도 안전하게 읽힌다. 취소선(strike) 서식은 read_only=False 로드가 필요한데,
    한컴 셀이 저장한 파일은 openpyxl 스타일 로드가 깨질 수 있다(IndexError). 그때는 read_only 로 값만 읽고
    취소선 감지는 생략(strike_ok=False) — 크래시 대신 우아하게 축소.
    """
    try:
        wb = openpyxl.load_workbook(path, data_only=True)     # 스타일(취소선) 포함 로드
        return wb[wb.sheetnames[0]], True
    except Exception:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)  # 견고 로드(취소선 감지 생략)
        return wb[wb.sheetnames[0]], False


_REQUIRED = (config.IN_COL_BUSINESS, config.IN_COL_ACCOUNT_ID, config.IN_COL_PRODUCT)


def _parse_grid(rows: list, *, strike_fn=None, emit_strike_warning: bool = False) -> InputList:
    """계정/상품 그리드(값 2차원)를 파싱하는 **공용 코어** — 파일(openpyxl)·구글시트(API rows) 공용.

    - `strike_fn(row_no_1based, col0)->bool`: 취소선 감지기(파일=openpyxl, 구글시트=read_grid_struck; 없으면 None).
    - 제외(해지/판매중지) 감지 = **취소선(있으면) 또는 상태 컬럼 값(IN_STATUS_DISCONTINUED) 또는 상품명 마커**.
      → 파일·구글시트 **양쪽 다 취소선을 읽는다**(구글시트도 Sheets API로 취소선 조회 가능). 상태 컬럼은 병행 감지원.
    - `emit_strike_warning`: 파일인데 취소선을 못 읽었을 때만 경고 추가(API 경로는 불필요 → False).
    """
    header, hrow = _find_header_row(rows, lambda h: all(name in h for name in _REQUIRED))
    if hrow < 0:
        missing = [n for n in _REQUIRED if not any(n in [_norm(c) for c in r] for r in rows[:_HEADER_SCAN_ROWS])]
        raise ValueError(f"입력 상단 {_HEADER_SCAN_ROWS}행에서 헤더를 찾지 못했습니다. "
                         f"누락 필수 컬럼: {', '.join(missing) or '(부분 일치)'}")
    idx = _column_index(header)
    i_rep = idx.get(config.IN_COL_REPRESENTATIVE)   # 선택(없으면 None → 라벨 폴백에서만 무시)
    i_biz = idx[config.IN_COL_BUSINESS]
    i_acct, i_prod = idx[config.IN_COL_ACCOUNT_ID], idx[config.IN_COL_PRODUCT]
    i_opt = i_vid = i_pid = None                     # 옵션/vid/pid 미파싱(입력 정리 — 라이브에서 vid 확보)
    i_ms, i_me, i_mm = idx.get("mkt_start"), idx.get("mkt_end"), idx.get("mkt_mon")   # 마케팅(선택)
    i_status = idx.get("status")                     # 상태 컬럼(선택) — 판매중지/삭제 감지

    def _struck_cell(row_no: int, col0) -> bool:
        return bool(strike_fn(row_no, col0)) if strike_fn is not None else False

    accounts: list[Account] = []
    by_id: dict[str, Account] = {}          # 같은 계정ID 재등장 시 상품을 이어 붙이기 위한 색인
    errors: list[str] = []
    struck: list[str] = []                   # 제외(취소선/상태/판매중지)된 계정·상품
    current_rep = ""
    current_acct: Account | None = None
    current_prod: Product | None = None
    acct_cancelled = False                    # 현재 계정이 해지/삭제 → 아래 상품·옵션 전부 제외
    prod_cancelled = False                    # 현재 상품이 품절/중지 → 아래 옵션 제외

    for row_no, row in enumerate(rows[hrow + 1:], start=hrow + 2):
        rep, biz = _norm(_cell(row, i_rep)), _norm(_cell(row, i_biz))
        acct, prod = _norm(_cell(row, i_acct)), _norm(_cell(row, i_prod))
        opt = _norm(_cell(row, i_opt))
        vids, pids = _split_ids(_cell(row, i_vid)), _split_ids(_cell(row, i_pid))
        status_disc = _status_discontinued(_cell(row, i_status)) if i_status is not None else False

        if rep:
            current_rep = rep
        if acct:
            # 계정 제외 = 상태 컬럼(판매중지/삭제) 또는 취소선(파일). → 계정 전체 제외.
            if status_disc or _struck_cell(row_no, i_acct):
                _finalize(current_prod)
                acct_cancelled = True
                prod_cancelled = False
                current_acct = current_prod = None
                reason = "상태=판매중지/삭제" if status_disc else "취소선(해지)"
                struck.append(f"계정 '{acct}'({biz or current_rep}) — {reason}")
            else:
                acct_cancelled = False
                prod_cancelled = False
                if acct in by_id:               # 같은 계정ID 재등장 → 기존 계정에 상품 이어붙임(분리·누락 방지)
                    current_acct = by_id[acct]
                    if not current_acct.business_name and biz:   # 뒤 행에 사업자명 있으면 채움
                        current_acct.business_name = biz
                else:
                    # 정체성=계정ID(필수). 사업자명이 비어도 라벨은 계정ID로 폴백되므로 치명오류 아님
                    # (빈 사업자명은 validate_input_list 가 경고로만 알림).
                    current_acct = Account(acct, current_rep, biz)
                    by_id[acct] = current_acct
                    accounts.append(current_acct)
        if acct_cancelled:                      # 제외된 계정 아래 행은 전부 건너뜀
            continue
        if prod:
            _finalize(current_prod)             # 이전 상품 마감(옵션 없으면 기본옵션)
            # 상품 제외 = 상태 컬럼 / 상품명 마커 / 취소선 중 하나라도 → 추적 제외
            if status_disc or _is_discontinued(prod) or _struck_cell(row_no, i_prod):
                prod_cancelled = True
                current_prod = None
                reason = ("상태=판매중지/삭제" if status_disc else
                          "판매중지" if _is_discontinued(prod) else "취소선(품절/중지)")
                struck.append(f"상품 '{prod}' — {reason}")
            else:
                prod_cancelled = False
                current_prod = Product(prod, mkt_start=_norm_date(_cell(row, i_ms)),
                                       mkt_end=_norm_date(_cell(row, i_me)),
                                       mkt_mon=_norm_date(_cell(row, i_mm)))
                if current_acct is None:
                    errors.append(f"{row_no}행: 소속 계정 없이 상품 '{prod}'")
                else:
                    current_acct.products.append(current_prod)
        if prod_cancelled:                      # 제외된 상품 아래 옵션 행 건너뜀
            continue
        # 옵션 행 (옵션명 또는 vid 가 있으면 현재 상품의 옵션)
        if opt or vids or pids:
            if current_prod is None:
                errors.append(f"{row_no}행: 소속 상품 없이 옵션/ID")
            else:
                current_prod.options.append(Option(opt, vids, pids))
    _finalize(current_prod)

    if emit_strike_warning:   # 파일인데 취소선을 못 읽었음을 알림(수동 확인 유도). 값 파싱은 정상.
        struck.append("⚠ 취소선 자동감지 불가(엑셀 스타일 비호환) — 해지/품절은 '상태' 컬럼 또는 수동 확인 필요")
    # 리포트 기준 시드: 상품/옵션/ID는 판매분석 리포트가 제공하므로 계정만 있으면 유효.
    valid = [a for a in accounts if a.account_id]
    return InputList(accounts=valid, errors=errors, struck=struck)


def parse_input_list(path: str | Path) -> InputList:
    """PC 엑셀(관리대장 다운로드본) 파싱. 취소선(있으면)+상태 컬럼으로 해지/판매중지 감지."""
    ws, strike_ok = _load_for_parse(path)   # strike_ok=False면 취소선 자동감지 불가(한컴 스타일 비호환)
    rows = list(ws.iter_rows(values_only=True))
    strike_fn = (lambda row_no, col0: _cell_struck(ws, row_no, col0)) if strike_ok else None
    return _parse_grid(rows, strike_fn=strike_fn, emit_strike_warning=not strike_ok)


def parse_input_rows(rows: list, strike_grid: list | None = None) -> InputList:
    """구글시트(Sheets API) 값 격자 → InputList. 제외 감지 = **취소선(strike_grid 있으면) 또는 상태 컬럼**.

    strike_grid: read_grid_struck 가 준 [행][열] bool 격자(rows 와 인덱스 정렬). None 이면 상태 컬럼만 사용.
    """
    def strike_fn(row_no: int, col0) -> bool:   # row_no=1based 시트행 → 격자 인덱스 row_no-1
        r = row_no - 1
        if not strike_grid or r < 0 or r >= len(strike_grid) or col0 is None:
            return False
        srow = strike_grid[r]
        return bool(srow[col0]) if 0 <= col0 < len(srow) else False

    return _parse_grid([list(r) for r in rows],
                       strike_fn=(strike_fn if strike_grid else None), emit_strike_warning=False)


def parse_password_rows(rows: list) -> dict[str, str]:
    """구글시트 값 격자에서 {계정아이디: 비밀번호} 추출(관리대장 rows 재사용, 파일 재조회 없음).

    비번은 관리대장(입력)에만 존재 → 읽는 즉시 DPAPI 저장·메모리 폐기가 호출부 책임(결과시트엔 저장 안 함).
    """
    def _match(header: list[str]) -> bool:
        norm = [h.lower().replace(" ", "") for h in header]
        return _alias_index(norm, _ID_ALIASES) is not None and _alias_index(norm, _PW_ALIASES) is not None

    header, hrow = _find_header_row(rows, _match)
    if hrow < 0:
        return {}                                   # 비번 컬럼 없으면 빈 dict(치명 아님 — credstore 기존값 사용)
    norm = [h.lower().replace(" ", "") for h in header]
    i_id, i_pw = _alias_index(norm, _ID_ALIASES), _alias_index(norm, _PW_ALIASES)
    out: dict[str, str] = {}
    for row in rows[hrow + 1:]:
        aid = _norm(_cell(row, i_id))
        raw = _cell(row, i_pw)
        pw = str(raw) if raw is not None else ""
        if aid and pw:
            out[aid] = pw
    return out


def read_ledger_rows(url_or_id: str, *, store=None, sa_path=None) -> tuple[str, list, list]:
    """관리대장(구글시트)을 서비스계정으로 열어 **본체 시트의 (값 격자, 취소선 격자)** 를 (시트명, rows, strike_grid)로 반환.

    본체 = 필수 헤더(사업자명·계정아이디·상품명)를 가진 시트. '셀독'·'리스트'가 든 시트명을 우선 조회해
    API 호출을 최소화한다. 못 찾으면 ValueError(사유 명시 — fallback 금지).
    취소선(strike_grid)은 파일 파서와 동일하게 해지/판매중지 감지에 쓴다(상태 컬럼과 OR).
    """
    from . import gsheet_api   # 지연 임포트(구글 라이브러리 미설치 환경에서 파일 파싱만 쓸 때 영향 없게)
    client = gsheet_api.GSheetClient(url_or_id, store=store, sa_path=sa_path)
    titles = client.sheet_titles()
    if not titles:
        raise ValueError("스프레드시트에 시트가 없습니다.")
    ordered = sorted(titles, key=lambda t: 0 if ("셀독" in t or "리스트" in t) else 1)
    for t in ordered:
        rows, strike_grid = client.read_grid_struck(t)
        _, hrow = _find_header_row(rows, lambda h: all(name in h for name in _REQUIRED))
        if hrow >= 0:
            return t, rows, strike_grid
    raise ValueError("관리대장에서 필수 헤더(사업자명·계정아이디·상품명)를 가진 시트를 찾지 못했습니다 "
                     f"(확인한 시트: {', '.join(titles)}).")


class InputValidationError(Exception):
    """입력 파일에 치명적 이상이 있어 작업을 시작할 수 없음(시작 전 차단)."""


def validate_input_list(il: InputList) -> tuple[list[str], list[str]]:
    """작업 시작 전 입력 검증 → (치명적, 경고) 목록.

    치명적(시작 차단): 파서 구조오류·유효계정 0개·계정ID 빈칸·시트명 충돌(다른 계정이 같은 시트명 → 덮어씀).
    경고(진행하되 알림): 사업자명 빈칸(→대표자명/계정ID 대체)·상품 0개 계정(수집 시 건너뜀).
    """
    fatals: list[str] = list(il.errors)     # 파서가 잡은 구조 오류
    warnings: list[str] = []
    accts = il.accounts
    if not accts:
        fatals.append("유효한 계정이 하나도 없습니다(입력 파일/헤더 확인).")
    if any(not (a.account_id or "").strip() for a in accts):
        fatals.append("계정ID가 빈 계정이 있습니다.")
    labels: dict[str, set[str]] = {}        # 시트명(label) → 그 이름을 쓰는 계정ID들
    for a in accts:
        labels.setdefault(a.label, set()).add(a.account_id)
    for name, ids in labels.items():
        if len(ids) > 1:                    # 서로 다른 계정이 같은 시트명 → 데이터 덮어씀
            fatals.append(f"시트명 충돌: '{name}' 을 서로 다른 계정({', '.join(sorted(ids))})이 공유 "
                          "→ 시트 덮어씀. 사업자명/대표자명으로 구분하세요.")
    for a in accts:
        if not (a.business_name or "").strip():
            warnings.append(f"계정 '{a.account_id}' 사업자명 없음 → 시트명 '{a.label}'(대표자명/계정ID) 사용.")
        if not a.products:
            warnings.append(f"계정 '{a.account_id}'({a.label}) 상품 0개 → 수집 시 건너뜀.")
    for s in il.struck:                       # 취소선으로 제외된 항목을 알림(감지 결과 노출)
        warnings.append(f"취소선 제외: {s}")
    return fatals, warnings
