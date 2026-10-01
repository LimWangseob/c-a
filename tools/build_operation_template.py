"""셀독 운영대장 빈 틀(템플릿) 생성 — designs/OPERATION_DATA_MODEL.md.

1단계(틀 생성): 데이터 없이 시트·헤더·정의·분류코드만. 구글시트 업로드용. 기존 앱 흐름 미접촉.
- 각 시트 좌측에 **계정·상품 신원(사업자명·상품명)** 을 두고 **고정(freeze)** → 스크롤해도 "누구의 어떤 상품"이 항상 보임.
- 명칭은 **기존 파일(관리대장·재고·통계) 용어** 채택. 각 항목 정의는 '정의' 시트.
- 신원 표시열(사업자명·상품명)은 앱이 키(계정아이디·상품코드)로 자동 채움(사람은 키만 입력해도 됨).

    python tools/build_operation_template.py [출력경로.xlsx]
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# 시트 정의: name -> (고정할 좌측 신원/키 열 수, [(컬럼, 정의), ...])
# 명칭은 기존 파일 용어 우선. '(표시)'=앱이 키로 자동 채우는 인식용 열.
SHEETS: dict[str, tuple[int, list[tuple[str, str]]]] = {
    "계정": (3, [
        ("계정아이디", "쿠팡 로그인 계정 ID(계정 키·불변). 예 wellbing1107"),
        ("대표자명", "계약 대표자 이름"),
        ("사업자명", "사업자 상호"),
        ("비밀번호", "쿠팡 로그인 비밀번호(평문 보관)"),
        ("위탁상태", "관리중 / 관리중단"),
        ("관리시작일", "위탁 관리 시작일"),
        ("중단일", "관리중단된 날(관리중이면 공란)"),
        ("체험단주체", "체험단 비용 주체(고객/셀독 등)"),
        ("비고", "메모"),
    ]),
    "계약": (5, [
        ("계약ID", "계약 고유번호(계약 키)"),
        ("계정아이디", "대상 계정(키)"),
        ("사업자명", "(표시) 사업자 상호 — 인식용"),
        ("상품코드", "대상 상품(여러 건이면 행 분리·키)"),
        ("상품명", "(표시) 내부관리 상품명 — 인식용"),
        ("계약금", "계약금 금액"),
        ("계약단가", "계약 단가"),
        ("약정이익", "약정 이익금(정액/정률)"),
        ("계약시작일", "계약 기간 시작"),
        ("계약종료일", "계약 기간 종료"),
        ("귀속기준일", "기간 귀속 기준(결제일/구매확정일/지급일 중 택1)"),
        ("비용부담주체", "원가·광고·쿠폰 등 비용 부담 주체"),
        ("분배주기", "정산 분배 주기"),
        ("세금계산서주체", "세금계산서 발행 주체"),
        ("계약서위치", "계약서 원본 보관 위치(소유자 PC 경로 메모)"),
        ("비고", "메모"),
    ]),
    "상품": (3, [
        ("상품코드", "셀독 상품 고유키 [분류1자][입고YYMM]-순번(예 G2608-001)·불변"),
        ("계정아이디", "소속 계정(키)"),
        ("사업자명", "(표시) 사업자 상호 — 인식용"),
        ("물류상품명", "재고파일(물류 최초 생성) 상품명 — 재고 연결용"),
        ("바코드", "물류 바코드(없을 수 있음)"),
        ("상품명", "내부관리용 상품명(셀독 관리명)"),
        ("노출상품명", "쿠팡 등록 노출 상품명"),
        ("카테고리", "상품 분류(세부·코드 아님·필터/정렬용)"),
        ("판매방식", "일반판매 / 그로스판매 / 둘다"),
        ("상품url", "쿠팡 상품 링크"),
        ("계약단가", "계약 단가"),
        ("판매가", "판매 가격"),
        ("관리상태", "판매중 / 판매중지 / 대체 / 삭제(삭제 4종)"),
        ("대체상품코드", "대체교체 시 새 상품코드(old→new 연결)"),
        ("상품등록일", "쿠팡 등록일"),
        ("비고", "메모"),
    ]),
    "그로스입고": (3, [
        ("상품코드", "대상 상품(키)"),
        ("사업자명", "(표시) 사업자 상호"),
        ("상품명", "(표시) 내부관리 상품명"),
        ("요청일자", "그로스 입고 요청일"),
        ("요청수량", "입고 요청 수량"),
        ("작업수량", "실제 작업 수량"),
        ("박스", "박스 수"),
        ("파레트", "파레트 수"),
        ("완료일자", "입고 완료일"),
        ("출고일자", "출고일"),
        ("입고지", "입고 창고"),
        ("비고", "메모"),
    ]),
    "체험단": (5, [
        ("체험단ID", "체험단 건 고유번호"),
        ("계정아이디", "대상 계정(키)"),
        ("사업자명", "(표시) 사업자 상호(기존 '상호')"),
        ("상품코드", "대상 상품(키)"),
        ("상품명", "(표시) 상품명(기존 '제품명')"),
        ("요청일", "체험단 요청일"),
        ("키워드", "체험단 키워드"),
        ("판매가", "판매가"),
        ("리뷰/택배", "리뷰·택배 유형"),
        ("건수", "체험단 건수"),
        ("신규/추가", "체험단 신규/추가"),
        ("견적서판매가", "견적서 판매가"),
        ("견적서리뷰/택배", "견적서 리뷰/택배"),
        ("밑작업", "밑작업 여부"),
        ("포토/텍스트", "리뷰 형태(포토/텍스트)"),
        ("진행여부", "진행 상태"),
        ("완료일", "완료일"),
        ("효과", "체험단 효과"),
        ("비고", "메모"),
    ]),
    "광고": (3, [
        ("상품코드", "대상 상품(키)"),
        ("사업자명", "(표시) 사업자 상호"),
        ("상품명", "(표시) 내부관리 상품명"),
        ("연", "집계 연도"),
        ("월", "집계 월(월별은 주차 합산)"),
        ("주차", "집계 주차(주 단위 입력)"),
        ("기간시작", "해당 주 시작일"),
        ("기간종료", "해당 주 종료일"),
        ("광고비", "광고 집행비"),
        ("노출", "광고 노출수"),
        ("클릭", "광고 클릭수"),
        ("전환", "광고 전환수"),
        ("매출", "광고 매출"),
        ("비고", "메모"),
    ]),
    "업무일지": (5, [
        ("일자", "업무 일자"),
        ("작성자", "셀독 담당자"),
        ("대상", "계정 / 상품"),
        ("계정아이디", "대상 계정(키)"),
        ("사업자명", "(표시) 사업자 상호"),
        ("상품코드", "상품 대상일 때(키)"),
        ("상품명", "(표시) 상품 대상일 때 상품명"),
        ("내용", "관리내용(기존 '관리내용')"),
        ("후속조치", "후속 조치사항"),
    ]),
    "분류코드": (1, [
        ("분류", "상품코드 1자 슬롯(A~Z)"),
        ("의미", "분류 의미"),
        ("비고", "메모"),
    ]),
}

CATEGORY_SEED = [["G", "건기식", "건강기능식품"], ["P", "공산품", "일반 공산품"], ["E", "기타", "미분류/기타"]]

# 참고: 재고현황(별도 파일·물류팀) 헤더 — 정의 시트에 함께 안내(이 템플릿은 운영대장만 생성).
STOCK_COLS = [
    ("창고", "보관 창고(기존 재고파일)"), ("구분", "건기식/공산품 등(기존)"),
    ("바코드", "물류 바코드(없을 수 있음)"), ("상품명", "물류 상품명(물류 최초 생성·기준)"),
    ("현재고", "현재 재고 수량"), ("셀독", "채널 표시(기존)"), ("당근", "채널 표시(기존)"),
    ("자사", "채널 표시(기존)"), ("상품코드", "운영대장 상품과 수동 매핑(추가)"),
    ("갱신일", "재고 갱신일"),
]

GUIDE = [
    ("셀독 운영대장 — 사용 안내 (SSOT=designs/OPERATION_DATA_MODEL.md)", "title"),
    ("", ""),
    ("■ 키: 계정아이디(계정) · 상품코드(상품) — 모든 시트가 이 둘로 연결", "h"),
    ("  각 시트 좌측의 사업자명·상품명은 '표시용'(인식용)이며 앱이 키로 자동 채웁니다. 좌측 열은 고정(freeze)돼 스크롤해도 보입니다.", ""),
    ("", ""),
    ("■ 상품코드  [분류1자 A~Z][입고YYMM]-[순번3]  예) G2608-001", "h"),
    ("  분류 1자 = '분류코드' 시트 참조 · 입고YYMM = 물류 최초 입고 연월 · 순번 001~. 불변 키(이름 바뀌어도 고정).", ""),
    ("  세부 카테고리는 코드가 아니라 '상품' 시트의 '카테고리' 컬럼으로.", ""),
    ("", ""),
    ("■ 상품명 3계층(상품 시트): 물류상품명(재고 기준) · 상품명(내부관리) · 노출상품명(쿠팡 등록)", "h"),
    ("  재고↔상품 = 물류상품명/바코드로 상품코드 수동 매핑 1회 후 고정(띄어쓰기 변동 주의).", ""),
    ("", ""),
    ("■ 관리상태(상품): 판매중/판매중지/대체/삭제 — 지우지 말고 상태로(이력은 원장이 보존)", "h"),
    ("", ""),
    ("■ 파일 4개: ①운영대장(이 파일) ②재고현황(물류팀·별도) ③셀독등록원장(앱) ④결과/정산(앱)", "h"),
    ("  재고현황 헤더는 '정의' 시트 하단 참고. 통계/정산/원장은 앱이 생성·관리.", ""),
    ("", ""),
    ("■ 서식: 앱이 컬럼 자동폭 + 계정/블럭 바탕색을 주기 적용(사람 입력 값 미접촉).", "h"),
]

_HDR_FILL = PatternFill("solid", fgColor="B7C9E8")
_ID_FILL = PatternFill("solid", fgColor="E3ECF7")   # 신원/키 열 헤더(연한 강조)
_HDR_FONT = Font(bold=True)
_TITLE_FONT = Font(bold=True, size=13)
_CENTER = Alignment(horizontal="center", vertical="center")


def _col_width(text: str) -> int:
    return max(10, min(42, int(len(text) * 2.1) + 5))


def _write_sheet(ws, idcols: int, cols: list[tuple[str, str]], seed=None) -> None:
    for c, (name, _d) in enumerate(cols, 1):
        cell = ws.cell(1, c, name)
        cell.fill = _ID_FILL if c <= idcols else _HDR_FILL
        cell.font = _HDR_FONT
        cell.alignment = _CENTER
        ws.column_dimensions[get_column_letter(c)].width = _col_width(name)
    # 헤더 1행 + 좌측 신원/키 열 고정 → 스크롤해도 "누구의 어떤 상품" 보임
    ws.freeze_panes = f"{get_column_letter(idcols + 1)}2"
    for r, row in enumerate(seed or [], 2):
        for c, v in enumerate(row, 1):
            ws.cell(r, c, v)


def _write_guide(ws) -> None:
    ws.column_dimensions["A"].width = 108
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
        cell.fill = _HDR_FILL
        cell.font = _HDR_FONT
        cell.alignment = _CENTER
    ws.freeze_panes = "A2"
    for c, wd in enumerate([14, 16, 80], 1):
        ws.column_dimensions[get_column_letter(c)].width = wd
    r = 2
    for sn, (_idc, cols) in SHEETS.items():
        for name, d in cols:
            _def_row(ws, r, sn, name, d)
            r += 1
    for name, d in STOCK_COLS:                     # 재고현황(별도 파일) 헤더도 사전에 수록
        _def_row(ws, r, "재고현황(별도)", name, d)
        r += 1


def build(path: Path) -> Path:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _write_guide(wb.create_sheet("안내"))
    _write_defs(wb.create_sheet("정의"))
    for name, (idcols, cols) in SHEETS.items():
        _write_sheet(wb.create_sheet(name), idcols, cols,
                     CATEGORY_SEED if name == "분류코드" else None)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("운영대장_템플릿.xlsx")
    p = build(out)
    print(f"[완료] 운영대장 템플릿: {p}")
    print(f"  시트: 안내 · 정의 · {' · '.join(SHEETS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
