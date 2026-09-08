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
    """이름·별칭으로 컬럼 위치 해석(필수 4개는 앞서 존재 확인됨)."""
    idx: dict[str, int] = {}
    for name in (config.IN_COL_REPRESENTATIVE, config.IN_COL_BUSINESS,
                 config.IN_COL_ACCOUNT_ID, config.IN_COL_PRODUCT):
        idx[name] = header.index(name)
    norm = [h.lower().replace(" ", "") for h in header]
    for key, aliases in (("option", config.IN_ALIASES_OPTION),
                         ("vendor", config.IN_ALIASES_VENDOR_ITEM_ID),
                         ("product_id", config.IN_ALIASES_PRODUCT_ID)):
        i = _alias_index(norm, aliases)
        if i is not None:
            idx[key] = i
    return idx


def _cell(row, i):
    return row[i] if (i is not None and len(row) > i) else None


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


def parse_input_list(path: str | Path) -> InputList:
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    required = (config.IN_COL_REPRESENTATIVE, config.IN_COL_BUSINESS,
                config.IN_COL_ACCOUNT_ID, config.IN_COL_PRODUCT)
    header, hrow = _find_header_row(rows, lambda h: all(name in h for name in required))
    if hrow < 0:
        missing = [n for n in required if not any(n in [_norm(c) for c in r] for r in rows[:_HEADER_SCAN_ROWS])]
        raise ValueError(f"입력 파일 상단 {_HEADER_SCAN_ROWS}행에서 헤더를 찾지 못했습니다. "
                         f"누락 필수 컬럼: {', '.join(missing) or '(부분 일치)'}")
    idx = _column_index(header)
    i_rep, i_biz = idx[config.IN_COL_REPRESENTATIVE], idx[config.IN_COL_BUSINESS]
    i_acct, i_prod = idx[config.IN_COL_ACCOUNT_ID], idx[config.IN_COL_PRODUCT]
    i_opt, i_vid, i_pid = idx.get("option"), idx.get("vendor"), idx.get("product_id")

    accounts: list[Account] = []
    errors: list[str] = []
    current_rep = ""
    current_acct: Account | None = None
    current_prod: Product | None = None

    for row_no, row in enumerate(rows[hrow + 1:], start=hrow + 2):
        rep, biz = _norm(_cell(row, i_rep)), _norm(_cell(row, i_biz))
        acct, prod = _norm(_cell(row, i_acct)), _norm(_cell(row, i_prod))
        opt = _norm(_cell(row, i_opt))
        vids, pids = _split_ids(_cell(row, i_vid)), _split_ids(_cell(row, i_pid))

        if rep:
            current_rep = rep
        if acct:
            current_acct = Account(acct, current_rep, biz)
            if not current_rep and not biz:
                errors.append(f"{row_no}행: 계정 '{acct}' 대표자명/사업자명이 모두 비어 있음")
            accounts.append(current_acct)
        if prod:
            _finalize(current_prod)
            current_prod = Product(prod)
            if current_acct is None:
                errors.append(f"{row_no}행: 소속 계정 없이 상품 '{prod}'")
            else:
                current_acct.products.append(current_prod)
        # 옵션 행 (옵션명 또는 vid 가 있으면 현재 상품의 옵션)
        if opt or vids or pids:
            if current_prod is None:
                errors.append(f"{row_no}행: 소속 상품 없이 옵션/ID")
            else:
                current_prod.options.append(Option(opt, vids, pids))
    _finalize(current_prod)

    # 리포트 기준 시드: 상품/옵션/ID는 판매분석 리포트가 제공하므로 계정만 있으면 유효.
    valid = [a for a in accounts if a.account_id]
    return InputList(accounts=valid, errors=errors)
