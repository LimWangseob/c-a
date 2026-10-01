"""결과/정산 파일(파일④) 샘플 생성 — 앱이 매일 산출하는 통계+정산 파일의 구조 예시.

실데이터가 아니라 **포맷 설명용 샘플**이다(통계=상품×키워드 노출순위·판매 시계열, 정산=계약대비 정산현황).
실제 파일은 파이프라인(workbook.py)이 매 실행 생성·누적한다. 이 도구는 틀만 보여준다.

    python tools/build_result_sample.py [출력.xlsx]
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

_DL = Path.home() / "Downloads"
DEF_OUT = _DL / "결과정산_샘플.xlsx"

_HDR = PatternFill("solid", fgColor="2E75B6")
_IDF = PatternFill("solid", fgColor="548235")
_SUB = PatternFill("solid", fgColor="D9E1F2")
_UP = PatternFill("solid", fgColor="C6EFCE")
_DN = PatternFill("solid", fgColor="FFC7CE")
_WHITE = Font(color="FFFFFF", bold=True)
_RIGHT = Alignment(horizontal="right")
_CTR = Alignment(horizontal="center")
_BORDER = Border(*[Side(style="thin", color="BFBFBF")] * 4)
_NUM = "#,##0"


def _hrow(ws, r, headers, fill=_HDR):
    for c, h in enumerate(headers, 1):
        cell = ws.cell(r, c, h)
        cell.fill = fill
        cell.font = _WHITE
        cell.alignment = _CTR
        cell.border = _BORDER


def _autofit(ws):
    for c in range(1, (ws.max_column or 0) + 1):
        ml = max((len(str(ws.cell(r, c).value or "")) for r in range(1, (ws.max_row or 0) + 1)), default=6)
        ws.column_dimensions[get_column_letter(c)].width = min(44, max(9, int(ml * 1.7) + 2))


def build(path: Path) -> None:
    wb = openpyxl.Workbook()

    # ── 안내 ──
    gd = wb.active
    gd.title = "안내"
    gd.sheet_properties.tabColor = "BFBFBF"
    notes = [
        "결과/정산 파일(파일④) — 앱이 매일 자동 생성/누적 (※ 이 파일은 포맷 설명용 '샘플', 실데이터 아님)",
        "",
        "[계정목록] 전 계정/상품 한눈 요약 미러 — 사업자·상품·계정·상태·체험단효과. 상품명=쿠팡 노출상품 링크.",
        "[통계_OOO]  사업자별 시트 — 상품 블록마다 키워드 노출순위 + 판매/방문/재고 지표를 '날짜 가로'로 누적.",
        "",
        "■ 정산 = 2레이어(SSOT=OPERATION_DATA_MODEL §7). 완전 별개이나 상품코드·귀속월로 연계.",
        "[레이어① 쿠팡정산 = 쿠팡→계정 지급]",
        "  [매출]      중개(판매자배송) 매출내역 — 매출A·쿠폰B·판매수수료C·마이샵D·정산대상E(=A-B-C-D)·차감F·지급(E-F).",
        "  [판매현황]  로켓그로스 수익현황 — 매출 - 비용(쿠폰·수수료·풀필먼트·광고·리뷰) + 재고손실보상 = 이익.",
        "  [쿠팡정산]  중개 정산현황 — 지급 건별(정산일·정산유형·지급비율 70/30=쿠팡 지급분할·상태·최종지급액).",
        "[레이어② 토탈셀러정산 = 토탈셀러↔계약]",
        "  [계약정산]  쿠팡실정산 × 계약배분 → 수익(순액)·갑(상품주)/을(토탈셀러) 배분·달성률. 계약유형=셀독(OEM)/위탁.",
        "  ※ 쿠팡 지급분할 70/30 ≠ 계약 수익배분 70/30 (숫자만 같은 별개 레이어).",
        "",
        "원본 입력=운영대장(사람) · 물류=재고현황 · 이력=셀독등록원장. 결과는 읽기 전용(앱 산출).",
    ]
    for i, t in enumerate(notes, 1):
        gd.cell(i, 1, t)
    gd.column_dimensions["A"].width = 110

    # ── 계정목록 ──
    al = wb.create_sheet("계정목록")
    al.sheet_properties.tabColor = "4472C4"
    heads = ["대표자", "사업자명", "계정ID", "상품(물류)명", "체험단판매가", "체험단리뷰", "체험단택배", "상태", "체험단효과"]
    _hrow(al, 1, heads)
    for c, h in enumerate(heads, 1):
        if h in ("대표자", "사업자명", "계정ID"):
            al.cell(1, c).fill = _IDF
    rows = [
        ["송창호", "(주)웰빙곳간", "wellbing1107", "웰빙곳간 활력 볶은 맥문동 환 프리미엄 30포", "", "", "", "판매중", "판매 +38% · 순위 32→18 ↑"],
        ["조진형", "플랜잇", "plan_it", "구강세정기 B31", "계약자", "계약자", "토탈셀러", "판매중", "판매 +12% · 순위 45→40 ↑"],
        ["안재영", "휴라엘", "sg0141n", "신형타프 R008 (블랙 Free)", "", "", "", "판매중지", ""],
    ]
    band = ["FFF2CC", "DDEBF7", "E2EFDA"]
    for i, row in enumerate(rows):
        r = i + 2
        for c, v in enumerate(row, 1):
            cell = al.cell(r, c, v)
            cell.fill = PatternFill("solid", fgColor=band[i % 3])
            cell.border = _BORDER
            if c == 4 and row[7] != "판매중지":
                cell.hyperlink = "https://www.coupang.com/vp/products/0?vendorItemId=0000000000"
                cell.font = Font(color="0563C1", underline="single")
            if c == 9 and "↑" in str(v):
                cell.fill = _UP
    al.freeze_panes = "A2"
    _autofit(al)

    # ── 통계_웰빙곳간 ──
    st = wb.create_sheet("통계_웰빙곳간")
    st.sheet_properties.tabColor = "70AD47"
    dates = ["09.27", "09.28", "09.29", "09.30"]
    _hrow(st, 1, ["구분", "키워드/지표", "", "", "", ""] + dates)
    st.cell(2, 1, "웰빙곳간 활력 볶은 맥문동 환 프리미엄 30포").font = Font(bold=True)
    st.cell(2, 1).fill = PatternFill("solid", fgColor="FCE4D6")
    kw = [("노출순위", "맥문동환", [32, 25, 20, 18]), ("노출순위", "맥문동 환", [40, 38, 33, 30]),
          ("노출순위", "활력환", [55, 50, 48, 45])]
    r = 3
    for _k, name, vals in kw:
        st.cell(r, 2, name)
        for j, v in enumerate(vals):
            cell = st.cell(r, 7 + j, v)
            cell.alignment = _RIGHT
            cell.number_format = _NUM
        r += 1
    metrics = [("재고현황", [1200, 1150, 1090, 1020]), ("판매가", [19900, 19900, 19900, 18900]),
               ("판매상태", ["판매중", "판매중", "판매중", "판매중"]), ("노출수", [3200, 3550, 4100, 4800]),
               ("판매건수", [12, 15, 19, 24]), ("방문자수", [210, 245, 300, 360])]
    for name, vals in metrics:
        cell0 = st.cell(r, 2, name)
        cell0.fill = _SUB
        for j, v in enumerate(vals):
            cell = st.cell(r, 7 + j, v)
            if isinstance(v, int):
                cell.alignment = _RIGHT
                cell.number_format = _NUM
        r += 1
    st.freeze_panes = "G2"
    _autofit(st)

    _build_settlement(wb)
    wb.save(path)


def _table(wb, title, color, heads, rows, pct_col=None):
    """정산 원천/결과 시트 공통 — 헤더 + 데이터 + 숫자서식 + 테두리 + 자동폭."""
    ws = wb.create_sheet(title)
    ws.sheet_properties.tabColor = color
    _hrow(ws, 1, heads)
    for i, row in enumerate(rows):
        r = i + 2
        for c, v in enumerate(row, 1):
            cell = ws.cell(r, c, v)
            cell.border = _BORDER
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                cell.alignment = _RIGHT
                cell.number_format = _NUM
            if pct_col and c == pct_col and isinstance(v, str) and v.endswith("%") and v != "-":
                cell.fill = _UP if float(v[:-1]) >= 30 else _DN
    ws.freeze_panes = "A2"
    _autofit(ws)
    return ws


def _build_settlement(wb) -> None:
    """정산 = 2레이어 (SSOT=OPERATION_DATA_MODEL §7.1~7.3)."""
    # ── 레이어① 쿠팡정산 ──
    # 매출(중개 매출내역·msf purchase-report-view) — A~F 공식 보존
    _table(wb, "매출", "7030A0",
           ["사업자명", "상품(물류)명", "귀속월", "정산유형", "구분", "매출금액(A)", "판매자할인쿠폰(B)",
            "판매수수료(C)", "마이샵수수료(D)", "정산대상액(E=A-B-C-D)", "정산차감(F)", "최종지급예정액(E-F)"],
           [["휴라엘", "신형타프 R008", "2026-09", "주정산", "합계",
             6601500, 2422100, 414947, 0, 3764453, 0, 3764453]])
    # 판매현황(로켓그로스 수익현황·rfm/settlements) — 매출-비용=이익
    _table(wb, "판매현황", "70AD47",
           ["사업자명", "상품(물류)명", "기간", "매출", "판매자할인쿠폰", "판매수수료", "풀필먼트서비스비용",
            "광고비", "리뷰이벤트", "비용합계", "재고손실보상", "이익", "이익률", "다음정산일", "예상지급액"],
           [["(주)웰빙곳간", "웰빙곳간 활력 볶은 맥문동 환 프리미엄 30포", "2026.09.22~09.28",
             3591960, -1583840, -185391, -132844, -89732, -2220, -1994027, 0, 1597933, "44.5%", "2026-09-29", 371921]])
    # 쿠팡정산(중개 정산현황·payment-report-view) — 지급 건별
    _table(wb, "쿠팡정산", "C00000",
           ["사업자명", "계정ID", "정산일", "정산유형", "지급비율", "구매확정기간", "정산상태", "최종지급액"],
           [["휴라엘", "bws247", "2026-09-29", "주정산", "70%", "2026-08-31~08-31", "정산확정", 8896],
            ["휴라엘", "bws247", "2026-09-29", "주정산", "70%", "2026-09-01~09-06", "정산확정", 1104130],
            ["휴라엘", "bws247", "2026-09-18", "주정산", "70%", "2026-08-24~08-30", "정산확정", 358481],
            ["휴라엘", "bws247", "2026-09-01", "최종액정산", "30%", "2026-07-01~07-31", "정산확정", 341946],
            ["휴라엘", "bws247", "2026-08-31", "주정산", "70%", "2026-08-03~08-09", "정산확정", 63657]])
    # ── 레이어② 토탈셀러정산(계약정산) — 쿠팡실정산 × 계약배분 ──
    _table(wb, "계약정산", "ED7D31",
           ["사업자명", "상품(물류)명", "계약유형", "수탁자", "수익배분", "수익계산식", "귀속월",
            "쿠팡실정산액", "차감(계약기준)", "수익(순액)", "갑배분(상품주)", "을배분(토탈셀러)",
            "목표수익률", "달성률", "지급상태", "지급일"],
           [["효성", "파미젠 와사비잎 추출물 plus max 120정", "셀독(OEM)", "㈜동방이노션", "갑70/을30",
             "판매수익=당기총매출-생산원가-판매수수료-배송비-광고비-반품/환불", "2026-09",
             8400000, 5328000, 3072000, 2150400, 921600, "30%", "36.6%", "지급완료", "2026-10-15"],
            ["봉이네농원", "곶감 상품", "위탁(운영대행)", "㈜디프픽", "갑70/을30",
             "순이익=총매출-(매입원가+수입부대비용+판매수수료+광고비+결제수수료+쿠팡입고비용+기타)", "2026-09",
             4300000, 2546000, 1754000, 1227800, 526200, "-", "-", "정산예정", "2026-10-15"]],
           pct_col=14)


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEF_OUT
    build(out)
    print(f"[결과/정산 샘플] 생성: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
