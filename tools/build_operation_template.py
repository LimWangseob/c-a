"""셀독 운영대장 빈 틀(템플릿) 생성 — designs/OPERATION_DATA_MODEL.md.

1단계(틀 생성): 데이터 없이 시트·헤더·정의·분류코드만. 구글시트 업로드용. 기존 앱 흐름 미접촉.

레이아웃 규칙(소유자 2026-10-01):
- **좌측 = 신원(사업자명·상품명 등)** 을 두고 고정(freeze) → 스크롤해도 "누구의 어떤 상품"이 항상 보임.
- **우측 = 관리용 코드**(상품코드·바코드·대체상품코드·계약ID·체험단ID) — 같은 행 오른쪽(행별 링크 유지).
- 헤더 색상 그룹: 신원(연초록)·내용(연파랑)·관리코드(연회색). 탭 색상으로 입력/참조/안내 구분.
- '안내'·'정의'는 맨 뒤. 명칭은 기존 파일(관리대장·재고·통계) 용어.
- 신원 표시열(사업자명·상품명)은 앱이 키(계정아이디·상품코드)로 자동 채움.

    python tools/build_operation_template.py [출력경로.xlsx]
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# 그룹 태그: id(신원·좌측 고정) / content(내용) / code(관리코드·우측)
# 각 시트 컬럼은 **표시 순서**(id→content→code)로 나열. (컬럼, 그룹, 정의)
SHEETS: dict[str, list[tuple[str, str, str]]] = {
    "계정": [
        ("대표자명", "id", "계약 대표자 이름"),
        ("사업자명", "id", "사업자 상호"),
        ("비밀번호", "content", "쿠팡 로그인 비밀번호(평문 보관)"),
        ("위탁상태", "content", "관리중 / 관리중단"),
        ("관리시작일", "content", "위탁 관리 시작일"),
        ("중단일", "content", "관리중단된 날(관리중이면 공란)"),
        ("체험단주체", "content", "체험단 비용 주체(고객/셀독 등)"),
        ("비고", "content", "메모"),
        ("계정아이디", "code", "쿠팡 로그인 계정 ID(계정 키·불변). 예 wellbing1107"),
    ],
    "계약": [
        ("사업자명", "id", "(표시) 사업자 상호 — 인식용"),
        ("상품명", "id", "(표시) 내부관리 상품명 — 인식용"),
        ("계약금", "content", "계약금 금액"),
        ("계약단가", "content", "계약 단가"),
        ("약정이익", "content", "약정 이익금(정액/정률)"),
        ("계약시작일", "content", "계약 기간 시작"),
        ("계약종료일", "content", "계약 기간 종료"),
        ("귀속기준일", "content", "기간 귀속 기준(결제일/구매확정일/지급일 중 택1)"),
        ("비용부담주체", "content", "원가·광고·쿠폰 등 비용 부담 주체"),
        ("분배주기", "content", "정산 분배 주기"),
        ("세금계산서주체", "content", "세금계산서 발행 주체"),
        ("계약서위치", "content", "계약서 원본 보관 위치(소유자 PC 경로 메모)"),
        ("비고", "content", "메모"),
        ("계정아이디", "code", "대상 계정(키)"),
        ("상품코드", "code", "대상 상품(여러 건이면 행 분리·키)"),
        ("계약ID", "code", "계약 고유번호(계약 키)"),
    ],
    "관리상품": [
        ("사업자명", "id", "(표시) 사업자 상호 — 인식용"),
        ("상품명", "id", "내부관리용 상품명(셀독 관리명)"),
        ("노출상품명", "content", "쿠팡 등록 노출 상품명"),
        ("물류상품명", "content", "재고파일(물류 최초 생성) 상품명 — 재고 연결용"),
        ("카테고리", "content", "상품 분류(세부·코드 아님·필터/정렬용)"),
        ("판매방식", "content", "일반판매 / 그로스판매 / 둘다"),
        ("상품url", "content", "쿠팡 상품 링크"),
        ("계약단가", "content", "계약 단가"),
        ("판매가", "content", "판매 가격"),
        ("관리상태", "content", "판매중 / 판매중지 / 대체 / 삭제(삭제 4종)"),
        ("상품등록일", "content", "쿠팡 등록일"),
        ("비고", "content", "메모"),
        ("계정아이디", "code", "소속 계정(키)"),
        ("상품코드", "code", "셀독 상품 고유키 [분류1자][입고YYMM]-순번(예 G2608-001)·불변"),
        ("바코드", "code", "물류 바코드(없을 수 있음)"),
        ("대체상품코드", "code", "대체교체 시 새 상품코드(old→new 연결)"),
    ],
    "그로스입고": [
        ("사업자명", "id", "(표시) 사업자 상호"),
        ("상품명", "id", "(표시) 내부관리 상품명"),
        ("요청일자", "content", "그로스 입고 요청일"),
        ("요청수량", "content", "입고 요청 수량"),
        ("작업수량", "content", "실제 작업 수량"),
        ("박스", "content", "박스 수"),
        ("파레트", "content", "파레트 수"),
        ("완료일자", "content", "입고 완료일"),
        ("출고일자", "content", "출고일"),
        ("입고지", "content", "입고 창고"),
        ("비고", "content", "메모"),
        ("상품코드", "code", "대상 상품(키)"),
    ],
    "체험단": [
        ("사업자명", "id", "(표시) 사업자 상호(기존 '상호')"),
        ("상품명", "id", "(표시) 상품명(기존 '제품명')"),
        ("요청일", "content", "체험단 요청일"),
        ("키워드", "content", "체험단 키워드"),
        ("판매가", "content", "판매가"),
        ("리뷰/택배", "content", "리뷰·택배 유형"),
        ("건수", "content", "체험단 건수"),
        ("신규/추가", "content", "체험단 신규/추가"),
        ("견적서판매가", "content", "견적서 판매가"),
        ("견적서리뷰/택배", "content", "견적서 리뷰/택배"),
        ("밑작업", "content", "밑작업 여부"),
        ("포토/텍스트", "content", "리뷰 형태(포토/텍스트)"),
        ("진행여부", "content", "진행 상태"),
        ("완료일", "content", "완료일"),
        ("효과", "content", "체험단 효과"),
        ("비고", "content", "메모"),
        ("계정아이디", "code", "대상 계정(키)"),
        ("상품코드", "code", "대상 상품(키)"),
        ("체험단ID", "code", "체험단 건 고유번호"),
    ],
    "광고": [
        ("사업자명", "id", "(표시) 사업자 상호"),
        ("상품명", "id", "(표시) 내부관리 상품명"),
        ("연", "content", "집계 연도"),
        ("월", "content", "집계 월(월별은 주차 합산)"),
        ("주차", "content", "집계 주차(주 단위 입력)"),
        ("기간시작", "content", "해당 주 시작일"),
        ("기간종료", "content", "해당 주 종료일"),
        ("광고비", "content", "광고 집행비"),
        ("노출", "content", "광고 노출수"),
        ("클릭", "content", "광고 클릭수"),
        ("전환", "content", "광고 전환수"),
        ("매출", "content", "광고 매출"),
        ("비고", "content", "메모"),
        ("상품코드", "code", "대상 상품(키)"),
    ],
    "업무일지": [
        ("일자", "id", "업무 일자"),
        ("대상", "id", "계정 / 상품"),
        ("사업자명", "id", "(표시) 사업자 상호"),
        ("상품명", "id", "(표시) 상품 대상일 때 상품명"),
        ("작성자", "content", "셀독 담당자"),
        ("내용", "content", "관리내용(기존 '관리내용')"),
        ("후속조치", "content", "후속 조치사항"),
        ("계정아이디", "code", "대상 계정(키)"),
        ("상품코드", "code", "상품 대상일 때(키)"),
    ],
    "분류코드": [
        ("분류", "id", "상품코드 1자 슬롯(A~Z)"),
        ("의미", "content", "분류 의미"),
        ("비고", "content", "메모"),
    ],
}

CATEGORY_SEED = [["G", "건기식", "건강기능식품"], ["P", "공산품", "일반 공산품"], ["E", "기타", "미분류/기타"]]

STOCK_COLS = [  # 재고현황(별도 파일·물류팀) — 정의 시트에 함께 안내
    ("창고", "보관 창고(기존 재고파일)"), ("구분", "건기식/공산품 등(기존)"),
    ("바코드", "물류 바코드(없을 수 있음)"), ("상품명", "물류 상품명(물류 최초 생성·기준)"),
    ("현재고", "현재 재고 수량"), ("셀독", "채널 표시(기존)"), ("당근", "채널 표시(기존)"),
    ("자사", "채널 표시(기존)"), ("상품코드", "운영대장 상품과 수동 매핑(추가)"), ("갱신일", "재고 갱신일"),
]

# 탭 색상 — 시트별 선명한 색(소유자 이미지 팔레트 참조). 안 지정분은 회색.
TAB_COLORS = {
    "대시보드": "203864",   # 진남색(개요 허브)
    "계정": "C00000",       # 빨강
    "계약": "ED7D31",       # 주황
    "관리상품": "FFC000",   # 골드
    "그로스입고": "70AD47", # 초록
    "체험단": "4472C4",     # 파랑
    "광고": "7030A0",       # 보라
    "업무일지": "00B0F0",   # 하늘
    "분류코드": "808080",   # 회색
    "정의": "BFBFBF", "안내": "BFBFBF",  # 연회색(참조/안내)
}
_FILL = {"id": "E2EFDA", "content": "DDEBF7", "code": "F2F2F2"}  # 헤더 색(신원/내용/관리코드)

# 대시보드 요약/알림 라벨(값은 앱이 자동 갱신 — 빈 틀은 라벨만).
_DASH_SUMMARY = ["총 계정", "관리중", "관리중단", "총 상품", "판매중", "판매중지", "대체", "삭제",
                 "그로스 입고대기", "체험단 진행중", "이번달 광고비", "다가오는 정산일", "예상 지급액"]
_DASH_ALERT = ["재고 미매핑 상품", "판매중지 전환 필요", "재고 부족", "계약 만료 임박", "정산 미확정 구간"]
_DASH_NAV = ["계정", "계약", "관리상품", "그로스입고", "체험단", "광고", "업무일지", "분류코드"]

_HDR_FONT = Font(bold=True)
_TITLE_FONT = Font(bold=True, size=13)
_CENTER = Alignment(horizontal="center", vertical="center")


def _col_width(text: str) -> int:
    return max(10, min(42, int(len(text) * 2.1) + 5))


def _write_sheet(ws, cols: list[tuple[str, str, str]], seed=None) -> None:
    idcount = sum(1 for _n, g, _d in cols if g == "id")  # 선두 신원 열 수(고정용)
    for c, (name, group, _d) in enumerate(cols, 1):
        cell = ws.cell(1, c, name)
        cell.fill = PatternFill("solid", fgColor=_FILL[group])
        cell.font = _HDR_FONT
        cell.alignment = _CENTER
        ws.column_dimensions[get_column_letter(c)].width = _col_width(name)
    ws.freeze_panes = f"{get_column_letter(idcount + 1)}2"  # 헤더행 + 좌측 신원 고정
    for r, row in enumerate(seed or [], 2):
        for c, v in enumerate(row, 1):
            ws.cell(r, c, v)


GUIDE = [
    ("셀독 운영대장 — 사용 안내 (SSOT=designs/OPERATION_DATA_MODEL.md)", "title"),
    ("", ""),
    ("■ 레이아웃: 좌측=신원(사업자명·상품명, 고정) · 가운데=내용 · 우측=관리코드(상품코드·계정아이디 등)", "h"),
    ("  스크롤해도 좌측 신원이 보입니다. 신원 표시열은 앱이 키로 자동 채웁니다(사람은 키만 입력해도 됨).", ""),
    ("", ""),
    ("■ 헤더 색: 신원(연초록) · 내용(연파랑) · 관리코드(연회색). 탭 색: 입력(파랑)·참조(초록)·안내(회색).", "h"),
    ("", ""),
    ("■ 키: 계정아이디(계정) · 상품코드(상품) — 모든 시트 연결(우측 관리코드 영역).", "h"),
    ("", ""),
    ("■ 상품코드  [분류1자 A~Z][입고YYMM]-[순번3]  예) G2608-001 · 불변", "h"),
    ("  분류 1자='분류코드' 시트 참조 · 세부 카테고리는 코드 아닌 '관리상품'의 '카테고리' 컬럼.", ""),
    ("", ""),
    ("■ 상품명 3계층(관리상품): 상품명(내부관리) · 노출상품명(쿠팡) · 물류상품명(재고 기준).", "h"),
    ("  재고↔상품 = 물류상품명/바코드로 상품코드 수동 매핑 1회(띄어쓰기 변동 주의).", ""),
    ("", ""),
    ("■ 관리상태(관리상품): 판매중/판매중지/대체/삭제 — 지우지 말고 상태로(이력은 원장 보존).", "h"),
    ("", ""),
    ("■ 파일 4개: ①운영대장(이 파일) ②재고현황(물류팀·별도) ③셀독등록원장(앱) ④결과/정산(앱).", "h"),
    ("  재고현황 헤더는 '정의' 시트 하단 참고.", ""),
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
        cell.font = _HDR_FONT
        cell.alignment = _CENTER
    ws.freeze_panes = "A2"
    for c, wd in enumerate([14, 16, 82], 1):
        ws.column_dimensions[get_column_letter(c)].width = wd
    r = 2
    for sn, cols in SHEETS.items():
        for name, _g, d in cols:
            _def_row(ws, r, sn, name, d)
            r += 1
    for name, d in STOCK_COLS:
        _def_row(ws, r, "재고현황(별도)", name, d)
        r += 1


# 시트 순서(소유자 2026-10-01): 대시보드 먼저 · 자주 쓰는 운영 시트 · 계정/계약은 뒤(등록 후 드묾) · 참조/안내 맨 뒤.
SHEET_ORDER = ["관리상품", "그로스입고", "체험단", "광고", "업무일지", "계정", "계약", "분류코드"]


def _write_dashboard(ws) -> None:
    """운영 개요 허브 — 요약·알림 라벨 + 각 시트 바로가기(값은 앱이 자동 갱신·빈 틀은 라벨)."""
    for col, w in (("A", 24), ("B", 18), ("D", 20)):
        ws.column_dimensions[col].width = w
    t = ws.cell(1, 1, "셀독 운영 대시보드")
    t.font = _TITLE_FONT
    ws.cell(2, 1, "요약·알림 값은 앱이 자동 갱신(빈 틀은 라벨만). 우측 바로가기로 각 시트 이동.")
    r = 4
    ws.cell(r, 1, "■ 운영 요약").font = _HDR_FONT
    for lab in _DASH_SUMMARY:
        r += 1
        ws.cell(r, 1, lab).fill = PatternFill("solid", fgColor=_FILL["content"])
    r += 2
    ws.cell(r, 1, "■ 확인 필요").font = _HDR_FONT
    for lab in _DASH_ALERT:
        r += 1
        ws.cell(r, 1, lab).fill = PatternFill("solid", fgColor="FCE4D6")   # 연주황(알림)
    ws.cell(4, 4, "■ 바로가기").font = _HDR_FONT
    for i, sn in enumerate(_DASH_NAV, 5):
        cell = ws.cell(i, 4, f"=HYPERLINK(\"#'{sn}'!A1\",\"{sn}\")")
        cell.font = Font(color="0563C1", underline="single")
    ws.freeze_panes = "A3"


def build(path: Path) -> Path:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    dash = wb.create_sheet("대시보드")                      # 개요 허브(맨 앞)
    dash.sheet_properties.tabColor = TAB_COLORS["대시보드"]
    _write_dashboard(dash)
    for name in SHEET_ORDER:                                # 운영 시트(계정·계약은 뒤)
        ws = wb.create_sheet(name)
        ws.sheet_properties.tabColor = TAB_COLORS.get(name, "BFBFBF")
        _write_sheet(ws, SHEETS[name], CATEGORY_SEED if name == "분류코드" else None)
    for name, writer in (("정의", _write_defs), ("안내", _write_guide)):  # 참조/안내 맨 뒤
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
