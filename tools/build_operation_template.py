"""셀독 운영대장 빈 틀(템플릿) 생성 — designs/OPERATION_DATA_MODEL.md.

1단계(틀): 데이터 없이 시트·헤더·정의·분류코드. 구글시트 업로드용. 기존 앱 흐름 미접촉.
스키마(소유자 2026-10-01 확정):
- 좌측=신원(사업자명·상품(물류)명) 고정 · 우측=관리코드(상품코드·계정아이디 등)는 **숨김**(자동연동 키로 유지).
- 헤더 진한 바탕+흰 글씨(신원 초록·내용 파랑·코드 회색)·탭 선명색·안내/정의 맨 뒤.
- 파생(derived) 열은 원본(관리상품·계정·재고)에서 수식 연동(전환 도구가 수식+잠금 적용, 빈 틀은 헤더만).

컬럼 정의: (이름, 그룹 id|content|code, 옵션, 정의). 옵션: num·date·link·derived. code 그룹=숨김.

    python tools/build_operation_template.py [출력경로.xlsx]
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

_THIN = Border(*(Side(style="thin", color="BFBFBF"),) * 4)  # 좌/우/상/하 셀 구분선

SHEETS: dict[str, list[tuple[str, str, str, str]]] = {
    "관리상품": [
        ("사업자명", "id", "derived", "(표시·자동) 계정아이디로 계정에서 연동"),
        ("카테고리", "content", "", "상품 분류(세부·코드 아님)"),
        ("판매방식", "content", "", "일반판매/그로스판매/둘다"),
        ("계약단가", "content", "num", "계약 단가(원)"),
        ("상품(물류)명", "id", "link", "상품명=물류 상품명(일원화)·쿠팡 링크 걸림(원본)"),
        ("옵션ID", "content", "", "쿠팡 옵션ID(vendorItemId 등)"),
        ("노출상품명", "content", "", "쿠팡 등록 노출명"),
        ("판매가", "content", "num", "판매가(원)"),
        ("재고현황", "content", "derived,num", "(표시·자동) 재고관리 시트에서 연동"),
        ("그로스재고", "content", "num", "로켓그로스 재고(앱 자동갱신·원본)"),
        ("상품등록일", "content", "date", "쿠팡 등록일"),
        ("관리상태", "content", "", "판매중/판매중지/대체/삭제"),
        ("비고", "content", "", "메모"),
        ("계정아이디", "code", "", "소속 계정(키·숨김)"),
        ("상품코드", "code", "", "셀독 상품 고유키 [분류][입고YYMM]-순번(숨김)"),
        ("바코드", "code", "", "물류 바코드(숨김)"),
        ("대체상품코드", "code", "", "대체교체 old→new(숨김)"),
    ],
    "재고관리": [
        ("창고", "content", "", "보관 창고"),
        ("구분", "content", "", "건기식/공산품 등"),
        ("상품명", "id", "", "물류 상품명(물류 최초 생성·기준·원본)"),
        ("재고현황", "content", "num", "현재 재고 수량(원본·물류)"),
        ("그로스재고", "content", "derived,num", "(표시·자동) 관리상품에서 연동"),
        ("셀독", "content", "", "채널 표시"),
        ("당근", "content", "", "채널 표시"),
        ("자사", "content", "", "채널 표시"),
        ("갱신일", "content", "date", "재고 갱신일"),
        ("바코드", "code", "", "물류 바코드(숨김)"),
        ("상품코드", "code", "", "운영대장 상품 매핑(숨김)"),
    ],
    "그로스입고": [
        ("사업자명", "id", "derived", "(표시·자동) 상품코드로 관리상품에서 연동"),
        ("상품(물류)명", "id", "derived", "(표시·자동) 상품코드로 관리상품에서 연동"),
        ("재고현황", "content", "derived,num", "(표시·자동) 재고관리에서 연동"),
        ("그로스재고", "content", "derived,num", "(표시·자동) 관리상품에서 연동"),
        ("요청일자", "content", "date", "그로스 입고 요청일"),
        ("요청수량", "content", "num", "입고 요청 수량"),
        ("작업수량", "content", "num", "실제 작업 수량"),
        ("박스", "content", "num", "박스 수"),
        ("파레트", "content", "num", "파레트 수"),
        ("완료일자", "content", "date", "입고 완료일"),
        ("출고일자", "content", "date", "출고일"),
        ("입고지", "content", "", "입고 창고"),
        ("비고", "content", "", "메모"),
        ("상품코드", "code", "", "대상 상품(키·숨김)"),
    ],
    "체험단": [
        ("사업자명", "id", "derived", "(표시·자동) 계정아이디로 계정에서 연동"),
        ("상품(물류)명", "id", "derived", "(표시·자동) 상품코드로 관리상품에서 연동"),
        ("요청일", "content", "date", "체험단 요청일"),
        ("키워드", "content", "", "체험단 키워드"),
        ("판매가", "content", "num", "판매가(원)"),
        ("리뷰/택배", "content", "", "리뷰·택배 유형"),
        ("건수", "content", "num", "체험단 건수"),
        ("신규/추가", "content", "", "체험단 신규/추가"),
        ("견적서판매가", "content", "num", "견적서 판매가(원)"),
        ("견적서리뷰/택배", "content", "", "견적서 리뷰/택배"),
        ("밑작업", "content", "", "밑작업 여부"),
        ("포토/텍스트", "content", "", "리뷰 형태"),
        ("진행여부", "content", "", "진행 상태"),
        ("완료일", "content", "date", "완료일"),
        ("효과", "content", "", "체험단 효과"),
        ("비고", "content", "", "메모"),
        ("계정아이디", "code", "", "대상 계정(키·숨김)"),
        ("상품코드", "code", "", "대상 상품(키·숨김)"),
        ("체험단ID", "code", "", "체험단 건 번호(숨김)"),
    ],
    "광고": [
        ("사업자명", "id", "derived", "(표시·자동) 상품코드로 관리상품에서 연동"),
        ("상품(물류)명", "id", "derived", "(표시·자동) 상품코드로 관리상품에서 연동"),
        ("연", "content", "", "집계 연도"),
        ("월", "content", "", "집계 월(월별=주차 합산)"),
        ("주차", "content", "", "집계 주차(주 입력)"),
        ("기간시작", "content", "date", "해당 주 시작"),
        ("기간종료", "content", "date", "해당 주 종료"),
        ("광고비", "content", "num", "광고 집행비(원)"),
        ("노출", "content", "num", "노출수"),
        ("클릭", "content", "num", "클릭수"),
        ("전환", "content", "num", "전환수"),
        ("매출", "content", "num", "광고 매출(원)"),
        ("비고", "content", "", "메모"),
        ("상품코드", "code", "", "대상 상품(키·숨김)"),
    ],
    "업무일지": [
        ("일자", "id", "date", "업무 일자"),
        ("사업자명", "id", "derived", "(표시·자동) 계정아이디로 계정에서 연동"),
        ("상품(물류)명", "id", "derived", "(표시·자동) 상품코드로 관리상품에서 연동"),
        ("작성자", "content", "", "셀독 담당자"),
        ("내용", "content", "", "관리내용"),
        ("후속조치", "content", "", "후속 조치사항"),
        ("상태", "content", "", "진행/완료/보류"),
        ("계정아이디", "code", "", "대상 계정(키·숨김)"),
        ("상품코드", "code", "", "상품 대상 시(키·숨김)"),
    ],
    "계정관리": [
        ("대표자명", "id", "", "계약 대표자"),
        ("사업자명", "id", "", "사업자 상호"),
        ("사업자등록번호", "content", "", "갑 사업자등록번호"),
        ("계정아이디", "content", "", "쿠팡 로그인 계정 ID(계정 키)"),
        ("비밀번호", "content", "", "쿠팡 로그인 비번(평문)"),
        ("위탁상태", "content", "", "관리중/관리중단"),
        ("관리시작일", "content", "date", "위탁 관리 시작일"),
        ("중단일", "content", "date", "관리중단일(관리중이면 공란)"),
        ("판매가주체", "content", "", "체험단 판매가 부담 주체(계약자 등)"),
        ("리뷰비주체", "content", "", "체험단 리뷰비 부담 주체"),
        ("비고", "content", "", "메모"),
    ],
    "계약서": [
        ("사업자명", "id", "", "사업자 상호(갑)"),
        ("대표자명", "id", "", "계약 대표자(갑)"),
        ("상품명", "id", "", "계약 상품(표시)"),
        ("적용플랫폼", "content", "", "쿠팡/스마트스토어/자사몰 등 판매 채널"),
        ("계약서종류", "content", "", "위탁운영/OEM 등"),
        ("계약일자", "content", "date", "계약서 작성일"),
        ("계약기간시작", "content", "date", "계약 시작"),
        ("계약기간종료", "content", "date", "계약 종료"),
        ("수탁자", "content", "", "을 상호(㈜디프픽·㈜동방이노션 등)"),
        ("수탁자대표자", "content", "", "을 대표자명"),
        ("수탁자사업자번호", "content", "", "을 사업자등록번호"),
        ("수익배분", "content", "", "예 갑70/을30"),
        ("수익기준", "content", "", "순이익/판매수익"),
        ("수익계산식", "content", "", "수익 계산 공식(총매출 차감항목)"),
        ("계약금", "content", "num", "계약금(원)"),
        ("계약단가", "content", "num", "계약 단가(원)"),
        ("계약수량", "content", "num", "계약 수량(OEM)"),
        ("계약금액", "content", "num", "계약 총액(원·OEM)"),
        ("광고비부담", "content", "", "광고비 부담 주체"),
        ("재고배송부담", "content", "", "재고·배송·반품 부담 주체"),
        ("정산시점", "content", "", "예 플랫폼 정산 후 7일"),
        ("정산계좌", "content", "", "정산/송금 계좌(OEM 선결제 등)"),
        ("결제조건", "content", "", "선결제/플랫폼 정산 후 지급 등"),
        ("귀속기준일", "content", "", "결제/구매확정/지급 중"),
        ("해지조건", "content", "", "자동연장·해지제한·목표수익률 판단 등"),
        ("특약", "content", "", "특약 사항(대체매칭 등)"),
        ("계약서위치", "content", "", "원본 보관 위치(PC)"),
        ("비고", "content", "", "메모"),
        ("계정아이디", "code", "", "대상 계정(키·숨김)"),
        ("상품코드", "code", "", "대상 상품(키·숨김)"),
        ("계약ID", "code", "", "계약 번호(숨김)"),
    ],
    "분류코드": [
        ("분류", "id", "", "상품코드 1자 슬롯(A~Z)"),
        ("의미", "content", "", "분류 의미"),
        ("비고", "content", "", "메모"),
    ],
}

CATEGORY_SEED = [["G", "건기식", "건강기능식품"], ["P", "공산품", "일반 공산품"], ["E", "기타", "미분류/기타"]]

SHEET_ORDER = ["관리상품", "재고관리", "그로스입고", "체험단", "광고", "계정관리", "계약서", "업무일지", "분류코드"]
# 탭 바탕색 = 연한 톤(2026-10-01 소유자 요청: 조금 연하게)
TAB_COLORS = {"대시보드": "8EAADB", "통합상세조회": "F4B6C2", "관리상품": "FFE08A", "재고관리": "F4B183",
              "그로스입고": "A9D08E", "체험단": "A9C0E8", "광고": "C3A6DD", "업무일지": "A6DDF5",
              "계정관리": "F0A6A6", "계약서": "F6C09A", "분류코드": "C9C9C9", "정의": "DCDCDC", "안내": "DCDCDC"}
_FILL = {"id": "548235", "content": "2E75B6", "code": "808080"}
_DASH_LBL = "DDEBF7"
_DASH_SUMMARY = ["총 계정", "관리중", "관리중단", "총 상품", "판매중", "판매중지", "대체", "삭제",
                 "그로스 입고대기", "체험단 진행중", "이번달 광고비", "다가오는 정산일", "예상 지급액"]
_DASH_ALERT = ["재고 미매핑 상품", "판매중지 전환 필요", "재고 부족", "계약 만료 임박", "정산 미확정 구간"]
_DASH_NAV = ["통합상세조회", "관리상품", "재고관리", "그로스입고", "체험단", "광고", "계정관리", "계약서", "업무일지", "분류코드"]

_HDR_FONT = Font(bold=True)
_HDR_FONT_W = Font(bold=True, color="FFFFFF")
_TITLE_FONT = Font(bold=True, size=13)
_CENTER = Alignment(horizontal="center", vertical="center")


def _col_width(text: str) -> int:
    return max(10, min(42, int(len(text) * 2.1) + 5))


def _write_sheet(ws, cols: list[tuple[str, str, str, str]], seed=None) -> None:
    idcount = sum(1 for _n, g, _o, _d in cols if g == "id")
    for c, (name, group, _opts, _d) in enumerate(cols, 1):
        cell = ws.cell(1, c, name)
        cell.fill = PatternFill("solid", fgColor=_FILL[group])
        cell.font = _HDR_FONT_W
        cell.alignment = _CENTER
        cell.border = _THIN
        letter = get_column_letter(c)
        ws.column_dimensions[letter].width = _col_width(name)
        if group == "code":                         # 관리코드 = 숨김(자동연동 키로만 유지)
            ws.column_dimensions[letter].hidden = True
    ws.freeze_panes = f"{get_column_letter(idcount + 1)}2"
    for r, row in enumerate(seed or [], 2):
        for c, v in enumerate(row, 1):
            ws.cell(r, c, v).border = _THIN


GUIDE = [
    ("셀독 운영대장 — 사용 안내 (SSOT=designs/OPERATION_DATA_MODEL.md)", "title"),
    ("", ""),
    ("■ 좌측=신원(사업자명·상품(물류)명, 고정) · 가운데=내용 · 우측=관리코드(상품코드·계정아이디 등, 숨김).", "h"),
    ("  관리코드는 숨겨져 있지만 자동연동 키로 쓰입니다(화면엔 안 보임).", ""),
    ("", ""),
    ("■ 자동연동: 파생 항목(사업자명·상품(물류)명·현재고·그로스재고)은 원본(관리상품·계정·재고)에서 수식으로 자동 갱신.", "h"),
    ("  이 항목들은 잠겨 있어 직접 수정 불가 — 원본 시트에서만 고치면 연결된 곳이 함께 바뀜.", ""),
    ("", ""),
    ("■ 상품명 = 물류 상품명으로 일원화(상품(물류)명). 상품(물류)명 셀에 쿠팡 링크. 세부 카테고리는 '카테고리' 컬럼.", "h"),
    ("■ 상품코드  [분류1자 A~Z][입고YYMM]-[순번3]  예) G2608-001 · 불변(숨김 키).", "h"),
    ("■ 관리상태: 판매중/판매중지/대체/삭제 — 지우지 말고 상태로(이력은 원장 보존).", "h"),
    ("■ 숫자=원 단위 정수 콤마·우측정렬 · 날짜=YYYY-MM-DD(시간 제외) · 계정별 바탕색으로 구분.", "h"),
    ("", ""),
    ("■ 파일 4개: ①운영대장(이 파일) ②재고현황(물류팀) ③셀독등록원장(앱) ④결과/정산(앱·통계+정산).", "h"),
]


def _write_guide(ws) -> None:
    ws.column_dimensions["A"].width = 112
    for r, (text, kind) in enumerate(GUIDE, 1):
        cell = ws.cell(r, 1, text)
        if kind == "title":
            cell.font = _TITLE_FONT
        elif kind == "h":
            cell.font = _HDR_FONT


def _def_row(ws, r: int, sheet: str, name: str, d: str) -> None:
    ws.cell(r, 1, sheet)
    ws.cell(r, 2, name)
    ws.cell(r, 3, d)


def _write_defs(ws) -> None:
    for c, h in enumerate(["시트", "항목", "정의"], 1):
        cell = ws.cell(1, c, h)
        cell.fill = PatternFill("solid", fgColor=_FILL["content"])
        cell.font = _HDR_FONT_W
        cell.alignment = _CENTER
    ws.freeze_panes = "A2"
    for c, wd in enumerate([14, 16, 82], 1):
        ws.column_dimensions[get_column_letter(c)].width = wd
    r = 2
    for sn, cols in SHEETS.items():
        for name, _g, _o, d in cols:
            _def_row(ws, r, sn, name, d)
            r += 1


def _write_dashboard(ws) -> None:
    for col, w in (("A", 24), ("B", 18), ("D", 20)):
        ws.column_dimensions[col].width = w
    ws.cell(1, 1, "셀독 운영 대시보드").font = _TITLE_FONT
    ws.cell(2, 1, "요약·알림 값은 앱이 자동 갱신(빈 틀은 라벨만). 우측 바로가기로 각 시트 이동.")
    r = 4
    ws.cell(r, 1, "■ 운영 요약").font = _HDR_FONT
    for lab in _DASH_SUMMARY:
        r += 1
        ws.cell(r, 1, lab).fill = PatternFill("solid", fgColor=_DASH_LBL)
    r += 2
    ws.cell(r, 1, "■ 확인 필요").font = _HDR_FONT
    for lab in _DASH_ALERT:
        r += 1
        ws.cell(r, 1, lab).fill = PatternFill("solid", fgColor="FCE4D6")
    ws.cell(4, 4, "■ 바로가기").font = _HDR_FONT
    for i, sn in enumerate(_DASH_NAV, 5):
        cell = ws.cell(i, 4, f"=HYPERLINK(\"#'{sn}'!A1\",\"{sn}\")")
        cell.font = Font(color="0563C1", underline="single")
    ws.freeze_panes = "A3"


def _col(sheet: str, name: str) -> str:
    """SHEETS 스키마에서 컬럼명 → 열 문자(통합상세조회 수식용)."""
    for i, (n, _g, _o, _d) in enumerate(SHEETS[sheet], 1):
        if n == name:
            return get_column_letter(i)
    raise KeyError(f"{sheet}.{name}")


def _dlk(sheet: str, ret: str, key: str, keyref: str) -> str:
    """선택상품/상품코드(keyref)로 sheet에서 ret 값을 끌어오는 INDEX/MATCH."""
    return (f"=IFERROR(INDEX('{sheet}'!{_col(sheet, ret)}:{_col(sheet, ret)},"
            f"MATCH({keyref},'{sheet}'!{_col(sheet, key)}:{_col(sheet, key)},0)),\"-\")")


# 통합상세조회 패널 블록: (블록명, [(라벨, 원본시트, 값컬럼, 키컬럼, keyref)])
_DETAIL_BLOCKS = [
    ("기본정보", [("사업자명", "관리상품", "사업자명", "상품(물류)명", "$B$2"),
               ("노출상품명", "관리상품", "노출상품명", "상품(물류)명", "$B$2"),
               ("판매방식", "관리상품", "판매방식", "상품(물류)명", "$B$2"),
               ("카테고리", "관리상품", "카테고리", "상품(물류)명", "$B$2"),
               ("관리상태", "관리상품", "관리상태", "상품(물류)명", "$B$2")]),
    ("가격", [("계약단가", "관리상품", "계약단가", "상품(물류)명", "$B$2"),
            ("판매가", "관리상품", "판매가", "상품(물류)명", "$B$2")]),
    ("재고", [("재고현황", "관리상품", "재고현황", "상품(물류)명", "$B$2"),
            ("그로스재고", "관리상품", "그로스재고", "상품(물류)명", "$B$2")]),
    ("그로스입고", [("요청일자", "그로스입고", "요청일자", "상품코드", "$B$3"),
               ("요청수량", "그로스입고", "요청수량", "상품코드", "$B$3"),
               ("완료일자", "그로스입고", "완료일자", "상품코드", "$B$3"),
               ("출고일자", "그로스입고", "출고일자", "상품코드", "$B$3")]),
    ("체험단", [("키워드", "체험단", "키워드", "상품코드", "$B$3"),
             ("건수", "체험단", "건수", "상품코드", "$B$3"),
             ("요청일", "체험단", "요청일", "상품코드", "$B$3")]),
    ("광고", [("광고비", "광고", "광고비", "상품코드", "$B$3"),
            ("매출", "광고", "매출", "상품코드", "$B$3")]),
    ("계약", [("계약서종류", "계약서", "계약서종류", "상품코드", "$B$3"),
            ("수익배분", "계약서", "수익배분", "상품코드", "$B$3"),
            ("정산시점", "계약서", "정산시점", "상품코드", "$B$3")]),
]
_DETAIL_NUM = {"계약단가", "판매가", "재고현황", "그로스재고", "요청수량", "건수", "광고비", "매출"}
_DETAIL_EDIT = {"노출상품명", "판매방식", "카테고리", "관리상태", "키워드"}  # 수정→원본반영(Apps Script)
_LBL_FILL = PatternFill("solid", fgColor="DDEBF7")
_SEL_FILL = PatternFill("solid", fgColor="FCE4D6")
_BLK_FILL = PatternFill("solid", fgColor="A9D08E")
_EDT_FILL = PatternFill("solid", fgColor="FFF2CC")


def _write_detail_view(ws) -> None:
    """통합상세조회 — 상품 선택 시 전 시트 항목 자동취합(읽기) + C열 수정입력(→원본반영 Apps Script)."""
    for col, w in (("A", 16), ("B", 46), ("C", 20)):
        ws.column_dimensions[col].width = w
    t = ws.cell(1, 1, "통합 상세조회 — 관리상품에서 상품명 클릭(또는 B2 선택) → 전 시트 항목 자동취합 · C열 수정→원본 반영")
    t.font = _TITLE_FONT
    ws.merge_cells("A1:C1")
    ws.cell(2, 1, "상품 선택 ▶").font = _HDR_FONT
    ws.cell(2, 1).fill = _LBL_FILL
    sel = ws.cell(2, 2, "")
    sel.fill = _SEL_FILL
    nmcol = _col("관리상품", "상품(물류)명")
    dv = DataValidation(type="list", formula1=f"=관리상품!${nmcol}$2:${nmcol}$1000", allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(sel)
    ws.cell(2, 3, "← 관리상품 상품명 클릭(Apps Script) 또는 드롭다운").font = Font(italic=True, color="808080")
    ws.cell(3, 1, "상품코드(자동)").font = _HDR_FONT
    ws.cell(3, 1).fill = _LBL_FILL
    ws.cell(3, 2, _dlk("관리상품", "상품코드", "상품(물류)명", "$B$2"))   # 타 시트 매칭 키
    for c, h in enumerate(("항목", "내용(읽기·자동)", "수정입력"), 1):
        cell = ws.cell(4, c, h)
        cell.fill = PatternFill("solid", fgColor="2E75B6")
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = _CENTER
        cell.border = _THIN
    for cell in (ws.cell(2, 1), ws.cell(2, 2), ws.cell(2, 3), ws.cell(3, 1), ws.cell(3, 2)):
        cell.border = _THIN
    r = 5
    for bname, items in _DETAIL_BLOCKS:
        bh = ws.cell(r, 1, bname)
        bh.fill = _BLK_FILL
        bh.font = Font(bold=True)
        bh.alignment = _CENTER
        bh.border = _THIN
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
        r += 1
        for lbl, sheet, ret, key, keyref in items:
            la = ws.cell(r, 1, lbl)
            la.fill = _LBL_FILL
            la.font = Font(bold=True)
            la.border = _THIN
            vc = ws.cell(r, 2, _dlk(sheet, ret, key, keyref))
            vc.border = _THIN
            if lbl in _DETAIL_NUM:
                vc.alignment = Alignment(horizontal="right")
                vc.number_format = "#,##0"
            ec = ws.cell(r, 3)
            ec.border = _THIN
            if lbl in _DETAIL_EDIT:
                ec.fill = _EDT_FILL
            r += 1
    ws.freeze_panes = "A5"


def build(path: Path) -> Path:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    dash = wb.create_sheet("대시보드")
    dash.sheet_properties.tabColor = TAB_COLORS["대시보드"]
    _write_dashboard(dash)
    detail = wb.create_sheet("통합상세조회")               # 대시보드 다음 위치
    detail.sheet_properties.tabColor = TAB_COLORS["통합상세조회"]
    _write_detail_view(detail)
    for name in SHEET_ORDER:
        ws = wb.create_sheet(name)
        ws.sheet_properties.tabColor = TAB_COLORS.get(name, "BFBFBF")
        _write_sheet(ws, SHEETS[name], CATEGORY_SEED if name == "분류코드" else None)
    for name, writer in (("정의", _write_defs), ("안내", _write_guide)):
        ws = wb.create_sheet(name)
        ws.sheet_properties.tabColor = TAB_COLORS.get(name, "BFBFBF")
        writer(ws)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("운영대장_템플릿.xlsx")
    p = build(out)
    print(f"[완료] 운영대장 템플릿: {p}")
    print(f"  시트: 대시보드 · {' · '.join(SHEET_ORDER)} · 정의 · 안내")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
