"""셀독 운영대장 빈 틀(템플릿) 생성 — designs/OPERATION_DATA_MODEL.md §4 의 7시트 + 분류코드 + 안내.

1단계(틀 생성): 데이터 없이 시트·헤더·분류코드 초기값만. 구글시트에 업로드해 사용.
기존 앱 흐름 미접촉(독립 도구). 재현 가능(헤더 바뀌면 여기만 고쳐 재실행).

    python tools/build_operation_template.py [출력경로.xlsx]
    (기본: 운영대장_템플릿.xlsx)
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# 시트명 → 헤더 목록 (SSOT=designs/OPERATION_DATA_MODEL.md §4). 순서 유지.
SHEETS: dict[str, list[str]] = {
    "계정": ["계정ID", "대표자", "사업자", "계정아이디", "비밀번호", "위탁상태",
             "관리시작일", "중단일", "체험단주체", "비고"],
    "계약": ["계약ID", "계정ID", "상품코드", "계약금", "계약단가", "약정이익",
             "계약시작일", "계약종료일", "귀속기준일", "비용부담주체", "분배주기",
             "세금계산서주체", "계약서위치", "비고"],
    "상품": ["상품코드", "계정ID", "물류명", "바코드", "내부관리명", "노출명", "카테고리",
             "판매방식", "상품url", "계약단가", "판매가", "상태", "대체상품코드",
             "등록일", "비고"],
    "그로스입고": ["상품코드", "요청일자", "요청수량", "작업수량", "박스", "파레트",
                   "완료일자", "출고일자", "입고지", "비고"],
    "체험단": ["체험단ID", "계정ID", "상품코드", "요청일", "키워드", "판매가", "리뷰/택배",
               "건수", "신규/추가", "견적_판매가", "견적_리뷰", "밑작업", "포토/텍스트",
               "진행여부", "완료일", "효과", "비고"],
    "광고": ["상품코드", "연", "월", "주차", "기간시작", "기간종료", "광고비", "노출",
             "클릭", "전환", "매출", "비고"],
    "업무일지": ["일자", "작성자", "대상", "계정ID", "상품코드", "내용", "후속조치"],
    "분류코드": ["분류", "의미", "비고"],
}

# 분류코드 초기값(상품코드 첫 자리 A~Z 슬롯. 나머지는 운영 중 할당).
CATEGORY_SEED = [
    ["G", "건기식", "건강기능식품"],
    ["P", "공산품", "일반 공산품"],
    ["E", "기타", "미분류/기타"],
]

# 안내(README) 시트 내용.
GUIDE = [
    ["셀독 운영대장 — 사용 안내 (designs/OPERATION_DATA_MODEL.md SSOT)"],
    [""],
    ["■ 키(모든 시트 연결)"],
    ["  계정ID = 계정 고유키 · 상품코드 = 상품 고유키(불변)"],
    ["  두 키로 모든 시트가 연결됩니다(계정/상품 기준 필터·링크 이동)."],
    [""],
    ["■ 상품코드 체계  [분류1자][입고YYMM]-[순번3]   예) G2608-001"],
    ["  1자 분류 = '분류코드' 시트 참조(A~Z 확장) · 입고YYMM = 물류 최초 입고 연월 · 순번 = 001~"],
    ["  불변 키 — 상품명/계정/노출명이 바뀌어도 코드는 고정. 대체교체 시 새 코드 + '대체상품코드'로 연결."],
    ["  세부 카테고리는 코드가 아니라 '상품' 시트의 '카테고리' 컬럼으로 관리."],
    [""],
    ["■ 상품명 3계층(상품 시트)"],
    ["  물류명 = 재고파일(물류 최초 생성·기준) · 내부관리명 = 셀독 관리용 · 노출명 = 쿠팡 등록명"],
    ["  재고↔상품 연결 = 물류명/바코드로 상품코드 수동 매핑 1회 후 고정(띄어쓰기 변동 주의)."],
    [""],
    ["■ 상태(상품 시트) = 판매중 / 판매중지 / 대체 / 삭제  (지우지 말고 상태로 — 이력은 원장이 보존)"],
    [""],
    ["■ 파일 구성(스프레드시트 4개): ①운영대장(이 파일) ②재고현황(물류팀) ③셀독등록원장(앱) ④결과/정산(앱)"],
    ["  재고현황은 물류팀이 별도 편집(비번 격리). 통계/정산/원장은 앱이 생성·관리."],
    [""],
    ["■ 서식: 앱이 주기적으로 컬럼 자동폭 + 계정/블럭 바탕색을 적용(사람 입력 값은 미접촉)."],
]

_HDR_FILL = PatternFill("solid", fgColor="B7C9E8")
_HDR_FONT = Font(bold=True)
_TITLE_FONT = Font(bold=True, size=13)


def _write_sheet(ws, headers: list[str], seed: list[list] | None = None) -> None:
    for c, h in enumerate(headers, 1):
        cell = ws.cell(1, c, h)
        cell.fill = _HDR_FILL
        cell.font = _HDR_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        # 컬럼 폭 = 헤더 길이 기반(한글 가중). 데이터가 없으니 헤더 기준 자동폭 근사.
        width = max(10, min(40, int(len(h) * 2.1) + 4))
        ws.column_dimensions[get_column_letter(c)].width = width
    ws.freeze_panes = "A2"           # 헤더 고정
    for r, row in enumerate(seed or [], 2):
        for c, v in enumerate(row, 1):
            ws.cell(r, c, v)


def _write_guide(ws) -> None:
    ws.column_dimensions["A"].width = 100
    for r, row in enumerate(GUIDE, 1):
        cell = ws.cell(r, 1, row[0])
        if r == 1:
            cell.font = _TITLE_FONT
        elif row[0].startswith("■"):
            cell.font = _HDR_FONT


def build(path: Path) -> Path:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)             # 기본 시트 제거
    _write_guide(wb.create_sheet("안내"))
    for name, headers in SHEETS.items():
        ws = wb.create_sheet(name)
        _write_sheet(ws, headers, CATEGORY_SEED if name == "분류코드" else None)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("운영대장_템플릿.xlsx")
    p = build(out)
    print(f"[완료] 운영대장 템플릿 생성: {p}")
    print(f"  시트: 안내 + {' · '.join(SHEETS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
