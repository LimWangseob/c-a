"""셀독 계약자별 상품 현황 — 엑셀 서식(시안 `output/_설계_261119_셀독고객별시트/셀독_계약자별상품현황_시안.xlsx` 15:10 이후본 = 기준).

시안 생성기(`시안_생성.py`)의 서식·칸 폭 상수를 그대로 옮겼다(D-358 양식·칸 폭). 칸 폭 표는 여기 한 곳이고 구글시트도
같은 워크북을 그대로 옮기므로(gsheet_contractor → gsheet_stats.worksheet_to_requests · 폭 1 = 7픽셀 + 여백 5) 같은 폭이 된다.
- 시트 = '요약' + 관리대장 사업자 시트(그 밖의 시트 없음 · 판정 근거·확인 필요는 판정표 파일에만).
- 사업자 시트: A1 '◀ 요약으로' · 2행 제목(사업자 + 대표자) · 3행 머리글 · 4행부터 등록상품 1줄 · 셀독 행만 연보라 ·
  날짜 = 최근이 왼쪽 7칸 · 7일 합계 = 오른쪽 끝 · 틀 고정 3행·C열.
- 요약: 사업자(시트 링크) · 대표자 · 계정ID · 전체/셀독/개인/개인 0건(뺌) · 7일 판매 셀독/개인/합계 · 셀독 비중 + 합계 줄.
"""
from __future__ import annotations

import re

import openpyxl
from openpyxl.formatting.rule import CellIsRule, ColorScaleRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins

from .contractor_sheet import Biz, Report

SUMMARY = "요약"
C_HEAD, C_HEAD2, C_SEL, C_LINE = "4B2E83", "6A4BA8", "EEE8FA", "D9D3E6"
C_MUTED, C_RED = "7A7290", "C62828"
FN = "맑은 고딕"
_s = Side(style="thin", color=C_LINE)
BOX = Border(left=_s, right=_s, top=_s, bottom=_s)
F_BODY = Font(name=FN, size=10)
F_LINK = Font(name=FN, size=10, color="1F4FB5", underline="single")
F_LINKB = Font(name=FN, size=10, bold=True, color="1F4FB5", underline="single")
F_HEAD = Font(name=FN, size=10, bold=True, color="FFFFFF")
CEN = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center")
RIGHT = Alignment(horizontal="right", vertical="center")
NUM = '#,##0;[Red]-#,##0;"-"'
WON = '#,##0"원";[Red]-#,##0"원";"-"'

# 칸 폭(소유자 11-19 4차 "구글시트에서 항목간 간력으로 조금씩만 넓혀줘. 특히 날짜별 판매건수 부분." · D-358) — 한 곳.
D_HEAD = ["구분", "계정ID", "상품명 (클릭 → 쿠팡 상품 페이지)", "판매방식", "판매상태",
          "판매가\n(최저)", "실구매가\n(즉시할인 후)", "그로스\n재고"]   # + 날짜 7칸(최근이 왼쪽) + 7일 합계(오른쪽 끝)
D_W = [9, 15, 50, 19, 11, 13, 14, 10]
D_DAY_W, D_SUM_W = 9, 13
DAY_FMT = "{:%m.%d}일"                     # 날짜 머리글 '11.15일'(소유자 11-19 "11.15--> 11.15일로")
# 요약 머리글 = 1~2줄(소유자 11-19 "요역시트 항목명 1줄 또는 2줄로 해줘" — 구글시트에서 '전체 상품 (등록상품)'이 3줄로 잘림)
# → '전체 상품'으로 줄이고 · 줄마다 칸 폭 안에 들어가게 개인 상품·개인 0건 칸을 11→12 로 조금 넓힘.
S_HEAD = ["No", "계약자 (사업자)\n클릭 → 시트", "대표자", "계정ID", "전체 상품", "셀독\n상품", "개인 상품\n(표시)",
          "개인 0건\n(뺌)", "7일 판매\n셀독", "7일 판매\n개인", "7일 판매\n합계", "셀독\n비중"]
S_W = [7, 28, 16, 26, 12, 9, 12, 12, 13, 13, 14, 11]
HEAD_H, ROW_H = 40, 20                     # 머리글(2줄) · 데이터 줄 높이(포인트 · 소유자 11-19 "줄간격 조금 넓혀줘" 15→20)
# 조건부 서식 = 구글시트도 지원하는 것만(소유자 11-19 '구글시트에서 일부 기능 미지원' — 데이터 막대 없음):
# 색 농도(흰색 → 연보라 · 값이 클수록 진하게 · "색 농도로 진행해줘") + 그로스 재고 0 빨강(cellIs).
C_SCALE_LO, C_SCALE_HI = "FFFFFF", "B39DDB"
NO_LINK = "  (링크 없음 · 상품ID 미수집)"


def _scale(end_type: str = "max", end_value=None) -> ColorScaleRule:
    """색 농도 2색(0 = 흰색 → 최댓값(또는 end_value) = 연보라) — 구글도 같은 규칙(gsheet_contractor 가 옮김)."""
    return ColorScaleRule(start_type="num", start_value=0, start_color=C_SCALE_LO,
                          end_type=end_type, end_value=end_value, end_color=C_SCALE_HI)


def _fill(c: str) -> PatternFill:
    return PatternFill("solid", fgColor=c)


def sheet_names(bizs: list[Biz]) -> dict[str, str]:
    """사업자명 → 시트 이름(엑셀 금지문자 `\\ / * ? : [ ]` → '_' · 31자 · 앞뒤 작은따옴표 뺌 · 겹치면 ' (2)')."""
    used = {SUMMARY}
    out: dict[str, str] = {}
    for b in bizs:
        base = re.sub(r"[\\/*?:\[\]]", "_", b.name).strip("'")[:31] or "사업자"
        name, n = base, 1
        while name in used:
            n += 1
            tail = f" ({n})"
            name = base[:31 - len(tail)] + tail
        used.add(name)
        out[b.name] = name
    return out


def _link(title: str) -> str:
    return "#'" + title.replace("'", "''") + "'!A1"


def product_url(pid: str, vid: str) -> str | None:
    """쿠팡 상품 페이지 — productId·VID 둘 다 있을 때만(workbook_meta.product_url 규칙 · 검색 링크 대체 없음)."""
    return f"https://www.coupang.com/vp/products/{pid}?vendorItemId={vid}" if pid and vid else None


def _heads(ws, row: int, hs: list[str], widths: list[int]) -> None:
    for c, h in enumerate(hs, 1):
        x = ws.cell(row, c, h)
        x.font, x.fill, x.alignment, x.border = F_HEAD, _fill(C_HEAD), CEN, BOX
    ws.row_dimensions[row].height = HEAD_H
    for c, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(c)].width = w


def _page(ws) -> None:
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins = PageMargins(left=0.3, right=0.3, top=0.4, bottom=0.4)
    ws.sheet_view.showGridLines = False
    ws.sheet_view.zoomScale = 90


def _row_values(it) -> list:
    return (["셀독" if it.sel else "개인", it.acc, it.name, it.method, it.status, it.price, it.real,
             it.growth if it.growth is not None else "－"] + list(reversed(it.d7)) + [it.s7])


def _put_row(ws, r: int, it) -> None:
    vals = _row_values(it)
    ws.row_dimensions[r].height = ROW_H
    for k, v in enumerate(vals, 1):
        x = ws.cell(r, k, v)
        x.font, x.border = F_BODY, BOX
        x.alignment = LEFT if k in (2, 3) else (CEN if k in (1, 4, 5) else RIGHT)
        x.number_format = WON if k in (6, 7) else ("#,##0" if k == 8 else (NUM if k > 8 else "General"))
    if it.status != "판매중":
        ws.cell(r, 5).font = Font(name=FN, size=10, color=C_RED)
    url = product_url(it.pid, it.vid)
    if url:
        ws.cell(r, 3).hyperlink = url
        ws.cell(r, 3).font = F_LINK
    else:
        ws.cell(r, 3).value = f"{it.name}{NO_LINK}"
    if it.sel:
        for k in range(1, len(vals) + 1):
            ws.cell(r, k).fill = _fill(C_SEL)
        ws.cell(r, 1).font = Font(name=FN, size=10, bold=True, color=C_HEAD)
    else:
        ws.cell(r, 1).font = Font(name=FN, size=10, color=C_MUTED)
    ws.cell(r, len(vals)).font = Font(name=FN, size=10, bold=True)


def biz_sheet(ws, b: Biz, days) -> None:
    """사업자 시트(시안 contractor_sheet 와 같은 모양)."""
    _page(ws)
    ws["A1"] = "◀ 요약으로"
    ws["A1"].hyperlink = _link(SUMMARY)
    ws["A1"].font = F_LINKB
    ws["A2"] = f"{b.name}  상품 현황   (대표자 {', '.join(b.reps)})"
    ws["A2"].font = Font(name=FN, size=16, bold=True, color=C_HEAD)
    ws.row_dimensions[2].height = 28
    hs = D_HEAD + [DAY_FMT.format(d) for d in reversed(days)] + ["7일\n합계"]
    hr = 3
    _heads(ws, hr, hs, D_W + [D_DAY_W] * len(days) + [D_SUM_W])
    s7c = len(hs)
    for k in range(len(D_HEAD) + 1, s7c):
        ws.cell(hr, k).fill = _fill(C_HEAD2)
    r = hr
    for it in b.rows:
        r += 1
        _put_row(ws, r, it)
    if r > hr:
        col = lambda k: f"{get_column_letter(k)}{hr + 1}:{get_column_letter(k)}{r}"   # noqa: E731
        ws.conditional_formatting.add(col(8), CellIsRule(operator="equal", formula=["0"],
                                                         font=Font(bold=True, color=C_RED)))
        ws.auto_filter.ref = f"A{hr}:{get_column_letter(len(hs))}{r}"
    ws.freeze_panes = ws.cell(hr + 1, 4)


def _summary_row(ws, r: int, i: int, b: Biz, linked: dict[str, str]) -> None:
    sr = [x for x in b.rows if x.sel]
    pr = [x for x in b.rows if not x.sel]
    vals = [i, b.title, ", ".join(b.reps), ", ".join(b.accs), b.total, len(sr), len(pr), b.dropped,
            sum(x.s7 for x in sr), sum(x.s7 for x in pr), f"=I{r}+J{r}", f'=IF(K{r}>0,I{r}/K{r},"")']
    ws.row_dimensions[r].height = ROW_H
    for k, v in enumerate(vals, 1):
        x = ws.cell(r, k, v)
        x.font, x.border = F_BODY, BOX
        x.alignment = CEN if k == 1 else (LEFT if k in (2, 3, 4) else RIGHT)
        x.number_format = "0%" if k == 12 else NUM
        if r % 2 == 0:
            x.fill = _fill("FAF8FD")
    ws.cell(r, 2).hyperlink = _link(linked[b.name])
    ws.cell(r, 2).font = F_LINKB


def summary_sheet(ws, bizs: list[Biz], linked: dict[str, str]) -> None:
    """요약 시트(시안 summary_sheet 와 같은 모양 · 사업자 이름 옆 '(로그인 실패)' 같은 표시 D-358 ⑦)."""
    _page(ws)
    ws["A1"] = "셀독 계약자별 상품 현황"
    ws["A1"].font = Font(name=FN, size=20, bold=True, color=C_HEAD)
    hr = 3
    _heads(ws, hr, S_HEAD, S_W)
    r = hr
    for i, b in enumerate(bizs, 1):
        r += 1
        _summary_row(ws, r, i, b, linked)
    end = r
    r += 1
    ws.row_dimensions[r].height = ROW_H
    for k in range(1, len(S_HEAD) + 1):
        x = ws.cell(r, k)
        x.fill, x.border, x.alignment = _fill(C_HEAD2), BOX, RIGHT
        x.font = Font(name=FN, size=10, bold=True, color="FFFFFF")
    ws.cell(r, 2, "합계").alignment = LEFT
    for k in (5, 6, 7, 8, 9, 10, 11):
        L = get_column_letter(k)
        ws.cell(r, k, f"=SUM({L}{hr + 1}:{L}{end})").number_format = NUM
    ws.cell(r, 12, f'=IF(K{r}>0,I{r}/K{r},"")').number_format = "0%"
    if end > hr:
        ws.conditional_formatting.add(f"K{hr + 1}:K{end}", _scale())
        ws.conditional_formatting.add(f"L{hr + 1}:L{end}", _scale(end_type="num", end_value=1))
        ws.auto_filter.ref = f"A{hr}:{get_column_letter(len(S_HEAD))}{end}"
    ws.freeze_panes = ws.cell(hr + 1, 3)


def build_workbook(rep: Report) -> openpyxl.Workbook:
    """보고서 → 워크북(요약 + 사업자 시트 · 모든 사업자 시트를 만들고 요약에서 링크)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = SUMMARY
    ws.sheet_properties.tabColor = C_HEAD
    linked = sheet_names(rep.bizs)
    summary_sheet(ws, rep.bizs, linked)
    for b in rep.bizs:
        s = wb.create_sheet(linked[b.name])
        s.sheet_properties.tabColor = "9C7FD6"
        biz_sheet(s, b, rep.days)
    return wb


__all__ = ["SUMMARY", "D_W", "D_DAY_W", "D_SUM_W", "S_W", "build_workbook", "product_url", "sheet_names"]
