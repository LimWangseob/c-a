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
    inbound_summary: str = ""       # 로켓그로스 최근입고 요약(관리대장) — 헤더 '최근입고 : …'(소유자 2026-09-24)
    discontinued: bool = False      # 대장 판매중지/취소선(#8 2026-09-27): 수집은 하되 ③순위만 제외
    sale_status: str = ""           # 발견 상품의 쿠팡 판매상태(판매중/부분판매중/판매중지 등) — 중복 리스팅 중 판매중지 제외용(2026-09-29)

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
    # 항목⑥(2026-09-25): 이 계정의 관리대장에 **줄이 존재하는 모든 상품명**(활성 + 판매중지/취소선 포함).
    # `products`(활성만)와 달리, "줄이 사라진 상품(=대장에 없음)"과 "줄은 있으나 비활성(=판매중지 유지)"을
    # 구분해 ⑥ 완전삭제 판정에 쓴다(줄 존재=삭제 대상 아님·유지).
    ledger_products: set = field(default_factory=set)

    @property
    def label(self) -> str:
        return self.business_name or self.representative or self.account_id


@dataclass
class InputList:
    accounts: list[Account]
    errors: list[str]
    struck: list[str] = field(default_factory=list)   # 취소선으로 제외된 계정/상품(해지·품절·판매중지)
    ledger_account_ids: set = field(default_factory=set)   # 관리대장에 **줄이 존재하는** 모든 계정ID
    #  (판매중지/취소선 포함 — '줄이 사라진' 계정과 구분해 완전삭제 판정에 씀, 2026-09-17)


def _norm(value) -> str:
    return str(value).strip() if value is not None else ""


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
                         ("status", config.IN_ALIASES_STATUS),
                         ("inb_reqdate", config.IN_ALIASES_INB_REQDATE),
                         ("inb_reqqty", config.IN_ALIASES_INB_REQQTY),
                         ("inb_workqty", config.IN_ALIASES_INB_WORKQTY),
                         ("inb_box", config.IN_ALIASES_INB_BOX),
                         ("inb_pallet", config.IN_ALIASES_INB_PALLET),
                         ("inb_donedate", config.IN_ALIASES_INB_DONEDATE),
                         ("inb_shipdate", config.IN_ALIASES_INB_SHIPDATE)):
        i = _alias_index(norm, aliases)
        if i is not None:
            idx[key] = i
    return idx


def _inbound_summary(row, idx: dict) -> str:
    """관리대장 입고 컬럼을 **2줄** 요약으로(레이아웃 v4 헤더 로켓그로스 pos5·pos6, 소유자 2026-09-24).

    L1 `그로스요청일자 : {요청일자} · 출고일 : {출고일자}` / L2 `요청수량 : {요청수량} · 작업수량 : {작업수량}
    · 박스 : {박스} · 파레트 : {파레트}` — 값 있는 항목만. '\n' 조인. 완료일자는 미표기. 전부 비면 ''."""
    def _v(key):
        return _norm(_cell(row, idx.get(key)))
    l1 = []
    for key, label in (("inb_reqdate", "그로스요청일자"), ("inb_shipdate", "출고일")):
        v = _v(key)
        if v:
            l1.append(f"{label} : {v}")
    l2 = []
    for key, label in (("inb_reqqty", "요청수량"), ("inb_workqty", "작업수량"),
                       ("inb_box", "박스"), ("inb_pallet", "파레트")):
        v = _v(key)
        if v:
            l2.append(f"{label} : {v}")
    line1, line2 = " · ".join(l1), " · ".join(l2)
    if not line1 and not line2:
        return ""
    return f"{line1}\n{line2}"


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


def _is_real_product_name(name: str) -> bool:
    """상품명 칸 값이 **실제 상품명**인지(소유자 2026-09-26). 글자(한글·영문·숫자)가 하나라도 있어야 True.

    담당자가 빈 칸 표시로 넣는 자리표시('--'·'-'·'.'·'·'·공백 등, 구두점/기호만)는 상품명이 아님 → False.
    False 인 행은 추적 상품으로 만들지 않는다(블록·시트·계정목록 생성 제외·ledger_products 미포함으로 기존
    잔재 블록도 reconcile 삭제). 실상품명은 규격·영문(BG001 등) 때문에 반드시 글자를 포함한다."""
    return bool(re.search(r"[0-9A-Za-z가-힣]", str(name or "")))


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

    - `strike_fn(row_no_1based, col0)->bool`: 취소선 감지기(파일=openpyxl, 구글시트=read_strike_grid; 없으면 None).
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
    st = _ParseState()
    i_rep = idx.get(config.IN_COL_REPRESENTATIVE)   # 선택(없으면 None → 라벨 폴백에서만 무시)
    i_biz = idx[config.IN_COL_BUSINESS]
    i_acct, i_prod = idx[config.IN_COL_ACCOUNT_ID], idx[config.IN_COL_PRODUCT]
    # 옵션/vid/pid 는 이 관리대장에 없고 미사용(vid 는 라이브 판매수집에서 확보) → 파싱하지 않음.
    i_status = idx.get("status")                     # 상태 컬럼(선택) — 판매중지/삭제 감지

    def _struck_cell(row_no: int, col0) -> bool:
        return bool(strike_fn(row_no, col0)) if strike_fn is not None else False

    for row_no, row in enumerate(rows[hrow + 1:], start=hrow + 2):
        rep, biz = _norm(_cell(row, i_rep)), _norm(_cell(row, i_biz))
        acct, prod = _norm(_cell(row, i_acct)), _norm(_cell(row, i_prod))
        # #C(2026-09-27): 담당자가 상품명 칸에 "담당자명\n\n(노출명 전체)" 처럼 **여러 줄**로 입력하면 정체성 키가
        # 오염돼 대장명 블록 + 노출명 블록이 중복 생성됨(실측: 비엔케이·브릿지웍스). → **첫 줄(담당자 상품명)만** 채택.
        if "\n" in prod:
            prod = prod.split("\n")[0].strip()
        status_disc = _status_discontinued(_cell(row, i_status)) if i_status is not None else False
        if rep:
            st.current_rep = rep
        if acct:
            _handle_account_row(st, acct, biz, status_disc, _struck_cell(row_no, i_acct))
        if st.acct_cancelled:                   # 제외된 계정 아래 행은 전부 건너뜀
            continue
        if prod:
            _handle_product_row(st, prod, acct, row, row_no, idx, status_disc, _struck_cell(row_no, i_prod))
    _finalize(st.current_prod)

    if emit_strike_warning:   # 파일인데 취소선을 못 읽었음을 알림(수동 확인 유도). 값 파싱은 정상.
        st.struck.append("⚠ 취소선 자동감지 불가(엑셀 스타일 비호환) — 해지/품절은 '상태' 컬럼 또는 수동 확인 필요")
    _dedupe_ledger_products(st.accounts, st.struck)
    # 리포트 기준 시드: 상품/옵션/ID는 판매분석 리포트가 제공하므로 계정만 있으면 유효.
    valid = [a for a in st.accounts if a.account_id]
    return InputList(accounts=valid, errors=st.errors, struck=st.struck, ledger_account_ids=st.ledger_ids)


class _ParseState:
    """_parse_grid 한 번의 파싱 상태(계정/상품 누적·현재 위치). 계정행/상품행 헬퍼가 공유·변경한다."""
    def __init__(self):
        self.accounts: list[Account] = []
        self.by_id: dict[str, Account] = {}   # 같은 계정ID 재등장 시 상품 이어붙이기 색인
        self.errors: list[str] = []
        self.struck: list[str] = []           # 제외(취소선/상태/판매중지)된 계정·상품
        self.ledger_ids: set = set()          # 관리대장에 줄이 존재하는 모든 계정ID(판매중지/취소선 포함)
        self.current_rep = ""
        self.current_acct: Account | None = None
        self.current_prod: Product | None = None
        self.acct_cancelled = False           # 현재 계정 해지/삭제 → 아래 상품 전부 제외


def _handle_account_row(st: "_ParseState", acct: str, biz: str, status_disc: bool, acct_struck: bool) -> None:
    """계정ID 셀이 있는 행 처리 — 제외(상태/취소선)면 계정 취소, 아니면 신규/재등장 계정 지정."""
    st.ledger_ids.add(acct)   # 판매중지/취소선이어도 '줄은 존재' → 완전삭제 대상 아님
    if status_disc or acct_struck:              # 계정 제외(상태 판매중지/삭제 또는 취소선) → 계정 전체 제외
        _finalize(st.current_prod)
        st.acct_cancelled = True
        st.current_acct = st.current_prod = None
        reason = "상태=판매중지/삭제" if status_disc else "취소선(해지)"
        st.struck.append(f"계정 '{acct}'({biz or st.current_rep}) — {reason}")
        return
    st.acct_cancelled = False
    if acct in st.by_id:                        # 같은 계정ID 재등장 → 기존 계정에 상품 이어붙임(분리·누락 방지)
        st.current_acct = st.by_id[acct]
        if not st.current_acct.business_name and biz:   # 뒤 행에 사업자명 있으면 채움
            st.current_acct.business_name = biz
    else:
        # 정체성=계정ID(필수). 사업자명이 비어도 라벨은 계정ID로 폴백되므로 치명오류 아님
        # (빈 사업자명은 validate_input_list 가 경고로만 알림).
        st.current_acct = Account(acct, st.current_rep, biz)
        st.by_id[acct] = st.current_acct
        st.accounts.append(st.current_acct)


def _handle_product_row(st: "_ParseState", prod: str, acct: str, row, row_no: int, idx: dict,
                        status_disc: bool, prod_struck: bool) -> None:
    """상품명 셀이 있는 행 처리 — 비상품 자리표시 제외·판매중지(#8)는 수집 포함(순위만 제외)·마케팅/입고 파싱."""
    _finalize(st.current_prod)                  # 이전 상품 마감(옵션 없으면 기본옵션)
    # 상품명이 아닌 자리표시('--' 등)는 추적 상품으로 만들지 않는다(소유자 2026-09-26):
    # 블록·시트·계정목록 생성 제외 + ledger_products 미포함 → 기존 잔재 블록도 reconcile 삭제.
    if not _is_real_product_name(prod):
        who = acct or (st.current_acct.account_id if st.current_acct else "?")
        st.struck.append(f"상품명 아님 '{prod}' (계정 {who}) — 제외")
        st.current_prod = None
        return
    if st.current_acct is not None:
        st.current_acct.ledger_products.add(prod)   # ⑥: 줄 존재(활성+판매중지/취소선) 전체 — 완전삭제 판정용
    # #8(2026-09-27): 판매중지/취소선도 **수집 대상에 포함**(discontinued=True)하고 ③순위만 제외한다.
    disc = bool(status_disc or _is_discontinued(prod) or prod_struck)
    st.current_prod = Product(prod, mkt_start=_norm_date(_cell(row, idx.get("mkt_start"))),
                              mkt_end=_norm_date(_cell(row, idx.get("mkt_end"))),
                              mkt_mon=_norm_date(_cell(row, idx.get("mkt_mon"))),
                              inbound_summary=_inbound_summary(row, idx), discontinued=disc)
    if st.current_acct is None:
        st.errors.append(f"{row_no}행: 소속 계정 없이 상품 '{prod}'")
    else:
        st.current_acct.products.append(st.current_prod)
    if disc:
        reason = ("상태=판매중지/삭제" if status_disc else
                  "판매중지" if _is_discontinued(prod) else "취소선(품절/중지)")
        st.struck.append(f"상품 '{prod}' — {reason} (수집·순위만 제외)")


def _dedupe_ledger_products(accounts: list, struck: list) -> None:
    """대장 중복 정책(2026-09-20 소유자): 한 계정에 **같은 상품명 2줄 이상**이면 담당자 오입력 → 첫 줄만 추적.

    정체성 키=공백정리 상품명(앞뒤·중간 연속공백 무시·대소문자 유지 — 서로 다른 상품을 과합치지 않게 보수적)."""
    for a in accounts:
        seen: set[str] = set()
        kept: list = []
        removed = 0
        for p in a.products:
            key = " ".join(str(p.name).split())
            if key and key in seen:
                removed += 1
                continue
            seen.add(key)
            kept.append(p)
        if removed:
            a.products = kept
            struck.append(f"[대장 중복] 계정 {a.account_id or a.business_name}: 같은 상품명 중복 {removed}줄 제거"
                          f"(첫 줄만 추적) — 담당자 오입력")


def _tok(s: str) -> list:
    return [t for t in _norm(s).split() if t]


def build_idf(names: list):
    """상품명 corpus 로 IDF 가중함수 생성 — 흔한 규격·브랜드어(120정·프리미엄·MAX·웰빙곳간)는 df↑→가중↓,
    상품 핵심어(베타글루칸·알부민·맥문동)는 df↓→가중↑. corpus 가 넓어야(전체 상품명) 규격어가 제대로 눌린다."""
    import math
    df: dict = {}
    for nm in names:
        for t in set(_tok(nm)):
            df[t] = df.get(t, 0) + 1
    n = max(1, len(names))
    return lambda t: math.log((n + 1) / (df.get(t, 1) + 0.5))


def _best_inventory_match(prod: str, cands: list, w) -> tuple:
    """상품명 `prod`를 **사업자 내 후보** [(상품명, 재고), …]에 매칭. (재고, 매칭명, 방식) 또는 (None,None,None).

    `w`=IDF 가중함수(전체 상품명 corpus 기반). ①정확(공백제거) → ②**대장상품의 최고가중(핵심) 토큰**(예 '베타글루칸')
    을 덮는 후보만 후보군으로 좁힌 뒤(공통 규격어만 겹치는 '알부민' 오매칭 배제), **대장상품 토큰 가중 재현율**
    최고를 고른다(후보의 여분 토큰은 감점 안 함=노출명이 짧아도 OK). 임계·2등 마진 미달이면 미매칭(오기록 방지·보존).
    """
    def dz(s: str) -> str:
        return _norm(s).replace(" ", "")
    pn = dz(prod)
    ptok = set(_tok(prod))
    if not pn or not ptok or not cands:
        return None, None, None
    for name, inv in cands:                          # ① 정확(공백제거 완전일치)
        if dz(name) == pn:
            return inv, name, "정확"
    pden = sum(w(t) for t in ptok) or 1.0
    top = max(ptok, key=w)                               # prod 최고가중(가장 희소=핵심) 토큰
    elig = [(name, inv) for name, inv in cands if top in set(_tok(name))]
    pool, strict = (elig, False) if elig else (cands, True)
    scored = sorted(((sum(w(t) for t in (ptok & set(_tok(name)))) / pden, name, inv)
                     for name, inv in pool), key=lambda x: x[0], reverse=True)
    best = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    margin = 0.15 if strict else 0.05                    # 핵심어 덮은 후보군이면 마진 완화
    if best[0] >= 0.55 and (best[0] - second) >= margin:
        return best[2], best[1], f"재현{best[0]:.2f}{'' if strict else '·핵심'}"
    return None, None, None


def _find_growth_column(header: list) -> int | None:
    """AD '그로스 재고 (…기준/자동갱신…)' 컬럼 — 괄호 딸린 것만(BW '그로스재고'·BV '그로스재고최소수량'과 구분).
    첫 갱신 후 헤더가 '(자동갱신 MM.DD)'로 바뀌므로 '기준' 또는 '갱신' 하나만 있으면 그 컬럼으로 인식."""
    def _nz(s: str) -> str:
        return str(s or "").replace("\n", "").replace(" ", "")
    return next((i for i, c in enumerate(header)
                 if "그로스" in _nz(c) and "재고" in _nz(c)
                 and ("기준" in _nz(c) or "갱신" in _nz(c))), None)


def _growth_idf(values: list, first: int, i_prod: int, inv_by_biz: dict):
    """IDF corpus = 모든 대장 상품명 + 워크북 후보명 → 규격·브랜드어(120정·프리미엄·MAX)를 눌러 상품 핵심어 부각
    (작은 재고후보 집합만으로 계산하면 df 동률로 오매칭)."""
    corpus = [_norm(_cell(values[r], i_prod)) for r in range(first, len(values))
              if _norm(_cell(values[r], i_prod))]
    for items in inv_by_biz.values():
        corpus += [nm for nm, _ in items]
    return build_idf(corpus)


def _growth_col_values(values, first, i_biz, i_acct, i_prod, ad, inv_by_biz, w):
    """AD 열 새 값 열 생성 — 계정(사업자) 내 상품명 유사도 매칭으로 최신 재고, **미매칭·개인상품·비상품은 기존값
    보존**(공란으로 안 덮음). 반환 (col_out, 갱신 수, 매칭 로그)."""
    col_out: list[list] = []
    cur_biz = ""
    updated = 0
    matches: list[str] = []                              # 로그용(대장상품 → 매칭 → 재고·방식)
    for r in range(first, len(values)):
        row = values[r]
        biz, acct, prod = _norm(_cell(row, i_biz)), _norm(_cell(row, i_acct)), _norm(_cell(row, i_prod))
        if acct and biz:                                 # 계정 행 → 이후 상품의 소속 사업자
            cur_biz = biz
        new = _cell(row, ad)
        if prod:                                         # 계정(사업자) 내 등록/노출 상품명 유사도 매칭
            inv, mname, how = _best_inventory_match(prod, inv_by_biz.get(_norm(cur_biz), []), w)
            if inv is not None:
                new = inv
                updated += 1
                matches.append(f"{prod[:22]} → {str(mname)[:22]} = {inv} ({how})")
        col_out.append([new if new not in (None,) else ""])
    return col_out, updated, matches


def write_ledger_inventory(client, wb, on_log=None, *, sheet: str = "셀독리스트") -> int:
    """관리대장(입력 구글시트)의 **'그로스 재고 (…기준)' 컬럼(AD)** 을 워크북 최신 재고로 역기록. 갱신 상품 수 반환.

    - 대상 컬럼 = 헤더에 '그로스'+'재고'+'기준' 인 컬럼(‘그로스재고최소수량’·BW ‘그로스재고’와 구분). 사용자 확정.
    - `parse_input_rows` 와 **동일 규칙**으로 행을 훑어(계정아이디 행에서 사업자 추적, 상품명 행=상품),
      (현재 사업자, 상품명)→워크북 최신 재고 매칭 → 그 상품 행의 AD 셀만 갱신.
    - **미매칭·재고 없음(개인상품·미수집)·비상품 행은 기존값 보존**(공란으로 안 덮음, 직원 다른 컬럼 미접촉).
    - 헤더 라벨을 '그로스 재고 (자동갱신 MM.DD)'로 갱신(‘8.26 기준’ 정적문구 제거). AD 데이터열 + 헤더 = 쓰기 2회.
    - ⚠ 서비스계정(SA)에 이 관리대장 **편집 권한**이 있어야 씀(없으면 403 → 호출부가 비치명 처리).
    """
    from datetime import datetime
    from openpyxl.utils import get_column_letter
    log = on_log or (lambda m: None)
    values, _ = client.read_grid(sheet)
    if not values:
        log(f"  [관리대장] '{sheet}' 시트가 비어 역기록 생략")
        return 0
    header, hrow = _find_header_row(values, lambda h: all(n in h for n in _REQUIRED))
    if hrow < 0:
        log("  [관리대장] 헤더(사업자명·계정아이디·상품명) 못 찾음 — 역기록 생략")
        return 0
    idx = _column_index(header)
    i_biz, i_acct, i_prod = idx[config.IN_COL_BUSINESS], idx[config.IN_COL_ACCOUNT_ID], idx[config.IN_COL_PRODUCT]

    ad = _find_growth_column(header)
    if ad is None:
        log("  [관리대장] '그로스 재고 (…기준/자동갱신)' 컬럼을 못 찾아 역기록 생략")
        return 0

    inv_by_biz = wb.inventory_by_biz()                   # {사업자: [(상품명, 재고)]} — 사업자 내 유사도 매칭
    first = hrow + 1                                      # 0-based 첫 데이터행
    w = _growth_idf(values, first, i_prod, inv_by_biz)
    col_out, updated, matches = _growth_col_values(values, first, i_biz, i_acct, i_prod, ad, inv_by_biz, w)
    letter = get_column_letter(ad + 1)                   # 0-based → 열문자
    client.write_values(sheet, col_out, start=f"{letter}{first + 1}")     # 첫 데이터행(1-based)
    client.write_values(sheet, [[f"그로스 재고 (자동갱신 {datetime.now():%m.%d})"]],
                        start=f"{letter}{hrow + 1}")     # 헤더 라벨 = 갱신일자
    for m in matches[:60]:                               # 매칭 내역(사용자 검증용, 특히 유사도 매칭 확인)
        log(f"    [재고매칭] {m}")
    log(f"  [관리대장] '그로스 재고'({letter}열) 갱신 — {updated}개 상품 재고 기록(미매칭·개인상품은 기존값 보존)")
    return updated


def parse_input_list(path: str | Path) -> InputList:
    """PC 엑셀(관리대장 다운로드본) 파싱. 취소선(있으면)+상태 컬럼으로 해지/판매중지 감지."""
    ws, strike_ok = _load_for_parse(path)   # strike_ok=False면 취소선 자동감지 불가(한컴 스타일 비호환)
    rows = list(ws.iter_rows(values_only=True))
    strike_fn = (lambda row_no, col0: _cell_struck(ws, row_no, col0)) if strike_ok else None
    return _parse_grid(rows, strike_fn=strike_fn, emit_strike_warning=not strike_ok)


def parse_input_rows(rows: list, strike_grid: list | None = None) -> InputList:
    """구글시트(Sheets API) 값 격자 → InputList. 제외 감지 = **취소선(strike_grid 있으면) 또는 상태 컬럼**.

    strike_grid: read_strike_grid 가 준 [행][열] bool 격자(rows 와 인덱스 정렬). None 이면 상태 컬럼만 사용.
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
        rows = client.read_values(t)                          # 값은 검증된 경로(대용량 시트 안전)
        _, hrow = _find_header_row(rows, lambda h: all(name in h for name in _REQUIRED))
        if hrow >= 0:
            # 취소선은 사용된 행까지만 서식을 읽어 페이로드를 줄인다(관리대장 1000+행 전체 서식 = 과대·실패 위험)
            strike_grid = client.read_strike_grid(t, max_rows=len(rows))
            return t, rows, strike_grid
    raise ValueError("관리대장에서 필수 헤더(사업자명·계정아이디·상품명)를 가진 시트를 찾지 못했습니다 "
                     f"(확인한 시트: {', '.join(titles)}).")


class InputValidationError(Exception):
    """입력 파일에 치명적 이상이 있어 작업을 시작할 수 없음(시작 전 차단)."""


def validate_input_list(il: InputList) -> tuple[list[str], list[str]]:
    """작업 시작 전 입력 검증 → (치명적, 경고) 목록.

    치명적(시작 차단): 파서 구조오류·유효계정 0개·계정ID 빈칸.
    경고(진행하되 알림): **같은 사업자명 다계정ID(항목5: 한 시트로 병합)**·사업자명 빈칸(→대표자명/계정ID
    대체)·상품 0개 계정(수집 시 건너뜀).

    ⚠ 항목5(소유자 2026-09-25): 예전엔 '같은 시트명(label)을 여러 계정ID가 공유'를 **치명 오류로 차단**했다
    (시트 덮어씀 방지). 이제 한 사업자에 계정ID가 여럿인 경우가 정상(다계정ID)이라, **한 시트로 병합**하고
    상품마다 계정ID를 태깅한다 → 치명 대신 `[SYNC]` 경고로 알린다(덮어쓰지 않고 상품 누적).
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
        if len(ids) > 1:                    # 같은 사업자명(label) 다계정ID → 한 시트로 병합(항목5, 덮어쓰기 아님)
            warnings.append(f"[SYNC] 다계정ID 사업자 '{name}': 계정ID {len(ids)}개"
                            f"({', '.join(sorted(ids))}) 를 한 시트로 병합(상품별 계정ID 태깅).")
    for a in accts:
        if not (a.business_name or "").strip():
            warnings.append(f"계정 '{a.account_id}' 사업자명 없음 → 시트명 '{a.label}'(대표자명/계정ID) 사용.")
        if not a.products:
            warnings.append(f"계정 '{a.account_id}'({a.label}) 상품 0개 → 수집 시 건너뜀.")
    for s in il.struck:                       # 취소선으로 제외된 항목을 알림(감지 결과 노출)
        warnings.append(f"취소선 제외: {s}")
    return fatals, warnings
