"""셀독 정산서 1장 그리기 — 견본 4차(D-224 · `셀독정산서_연다인_20261103기준_v4_261112_153302.xlsx`) 구성 그대로.

20열 × 폭 4.6 · A4 세로 1쪽(가로·세로 1쪽 맞춤) · 제목 → 카드 4개 → 도달율 막대 → 계약 내용 → 쿠팡 판매 요약(왼쪽)·쿠팡 정산 요약(오른쪽)
따로 나란히(D-218) → 상품별 → '세부는 위탁정산서' 한 줄. 내부용 글자(출처·확인 필요·D번호) 없음(D-221 ②).
4차와 다른 칸(자료가 위탁정산서뿐이라 바꿈 · D-225): 월별 '수량' 칸 → '정산'(끝남·정산 중) · 판매수량 = 정산 끝난 판매 수량 ·
품목·월·상품 줄 수 = 자료 줄 수(아래 줄이 그만큼 밀림) · 계약 = DB 문서 제목 + 계약자·회사 명칭.
"""
from __future__ import annotations

import math
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from coupang_analytics.settlement_seldoc_source import Contract, Perf, goal_total, reach

SHEET = "셀독 정산서"
PURPLE, GRAY, BLACK, LIGHT, LINE = "5B3FA0", "595959", "000000", "EDE7F6", "D0C8E6"
WON, WON_VAT, WON_GOAL, EA, PLAIN, PCT = ('#,##0"원"', '#,##0"원  (VAT 포함)"', '#,##0"원  (계약금액 + 목표수익금)"', '#,##0"개"', "#,##0",
                                         "0.0%")
BAR, MAX_PRODUCTS = 20, 8
FOOT = "판매·정산 세부 내역은 위탁정산서를 참고하세요."
THIN = Border(bottom=Side(style="thin", color=LINE))
HEAD_LINE = Border(bottom=Side(style="medium", color=PURPLE))
CARD = Border(left=Side(style="thick", color="FFFFFF"))
CARDS = (("목표 정산 총액", "계약금액 + 목표수익금", BLACK, WON), ("정산 기준 실적", "쿠팡 정산 기준", PURPLE, WON),
         ("목표 도달율", "실적 ÷ 목표 정산 총액", PURPLE, PCT), ("남은 금액", "목표까지 남은 금액", BLACK, WON))


def put(ws, r: int, c1: int, c2: int, v=None, *, size=10, bold=False, color=BLACK, fill=None, fmt=None, align="left", border=None,
        rows: int = 1):
    """r 행(부터 rows 줄) c1~c2 칸 병합(한 칸이면 병합 안 함) · 맑은 고딕 · 가운데 세로 정렬 · 줄바꿈.
    병합은 한 번만 — 같은 칸을 겹쳐 병합하면 엑셀이 파일을 '복구'하며 병합을 지움."""
    for rr in range(r, r + rows):
        for c in range(c1, c2 + 1):
            x = ws.cell(rr, c)
            if fill:
                x.fill = PatternFill("solid", fgColor=fill)
            if border is not None:
                x.border = border
    if c2 > c1 or rows > 1:
        ws.merge_cells(start_row=r, start_column=c1, end_row=r + rows - 1, end_column=c2)
    x = ws.cell(r, c1, v)
    x.font = Font(name="맑은 고딕", size=size, bold=bold, color=color)
    x.alignment = Alignment(horizontal=align, vertical="center", wrap_text=True)
    if fmt:
        x.number_format = fmt
    return x


def _head(ws, c: Contract, pf: Perf, basis: str, issued: str) -> None:
    put(ws, 1, 1, 20, SHEET, size=20, bold=True, color=PURPLE)
    put(ws, 2, 1, 20, f"계약자  {pf.label}     기준일  {basis}     발행일  {issued}", color=GRAY)
    target, result = goal_total(c.amount, c.profit), pf.result
    rate = reach(result, c.amount, c.profit)
    vals = (target, result, rate, max(target - result, 0))
    for k, ((title, note, color, fmt), v) in enumerate(zip(CARDS, vals)):
        c1 = 1 + 5 * k
        put(ws, 4, c1, c1 + 4, title, size=9, bold=True, color=GRAY, fill=LIGHT, align="center", border=CARD)
        put(ws, 5, c1, c1 + 4, v, size=16, bold=True, color=color, fill=LIGHT, fmt=fmt, align="center", border=CARD)
        put(ws, 6, c1, c1 + 4, note, size=8, color=GRAY, fill=LIGHT, align="center", border=CARD)
    put(ws, 8, 1, 20, f"목표 도달율  {rate:.1%}", size=11, bold=True)
    filled = min(BAR, max(0, round(rate * BAR)))
    for k in range(1, BAR + 1):
        ws.cell(9, k).fill = PatternFill("solid", fgColor=PURPLE if k <= filled else LIGHT)
    put(ws, 10, 1, 5, "0", size=8, color=GRAY)
    put(ws, 10, 6, 15, f"{result:,}원 / {target:,}원", size=8, color=GRAY, align="center")
    put(ws, 10, 16, 20, "100%", size=8, color=GRAY, align="right")
    for r, h in ((1, 34), (4, 18), (5, 30), (6, 16), (9, 20)):
        ws.row_dimensions[r].height = h


def _section(ws, r: int, c1: int, c2: int, text: str) -> None:
    put(ws, r, c1, c2, text, size=12, bold=True, color=PURPLE, border=HEAD_LINE)
    ws.row_dimensions[r].height = 22


def _row(ws, r: int, label: str, value, *, fmt=None, bold=False) -> int:
    put(ws, r, 1, 5, label, bold=True, color=GRAY, border=THIN)
    put(ws, r, 6, 20, value, bold=bold, fmt=fmt, border=THIN)
    return r + 1


def _none(v, fmt: str):
    return (v, fmt) if v is not None else ("없음", None)


def _goal_text(c: Contract) -> str:
    if c.rate is None and c.profit is None:
        return "없음"
    rate = f"{c.rate:g}%" if c.rate is not None else "없음"
    return f"{rate}  ·  " + (f"{c.profit:,}원" if c.profit is not None else "없음")


def _contract(ws, r: int, c: Contract) -> int:
    _section(ws, r, 1, 20, "계약 내용")
    r = _row(ws, r + 1, "계약 체결일", c.signed or "없음")
    r = _row(ws, r, "계약", f"{c.title or '없음'} (계약자 {c.party or c.rep or '없음'} · 회사 {c.company or '없음'})")
    r = _row(ws, r, "계약 기간", f"{c.signed} ~ {c.end}" if c.end else f"{c.signed} ~ (종료일 없음)")
    items = c.items or [("없음", None, None)]
    put(ws, r, 1, 5, "품목", bold=True, color=GRAY, border=THIN, rows=len(items) + 1)
    for c1, c2, t in ((6, 11, "품목"), (12, 16, "단가 (VAT 포함)"), (17, 20, "수량")):
        put(ws, r, c1, c2, t, size=9, bold=True, color=GRAY, fill=LIGHT, align="center")
    for k, (name, price, qty) in enumerate(items, 1):
        put(ws, r + k, 6, 11, name, border=THIN)
        pv, pf_ = _none(price, WON)
        qv, qf = _none(qty, EA)
        put(ws, r + k, 12, 16, pv, fmt=pf_, align="right", border=THIN)
        put(ws, r + k, 17, 20, qv, fmt=qf, align="right", border=THIN)
    r += len(items) + 1
    r = _row(ws, r, "계약금액", c.amount, fmt=WON_VAT)
    r = _row(ws, r, "목표수익률 · 목표수익금", _goal_text(c))
    return _row(ws, r, "목표 정산 총액", goal_total(c.amount, c.profit), fmt=WON_GOAL, bold=True)


def _month_label(ym: str, basis: str) -> str:
    """'2026-06' → '6월'(기준일과 같은 해) · '2025-12' → '2025년 12월'."""
    if not (len(ym) >= 7 and ym[5:7].isdigit()):
        return ym
    m = int(ym[5:7])
    return f"{m}월" if ym[:4] == basis[:4] else f"{ym[:4]}년 {m}월"


def _sales(ws, r: int, pf: Perf, basis: str) -> int:
    """왼쪽 = 쿠팡 판매 요약(판매금액·판매수량·월별) · 끝난 다음 행."""
    _section(ws, r, 1, 9, "쿠팡 판매 요약")
    note = f"정산 대상 상품 · 판매 기간 {pf.period} · 수량·상품별 = 정산 끝난 판매"
    put(ws, r + 1, 1, 9, note, size=8, color=GRAY)
    ws.row_dimensions[r + 1].height = _name_height(note, per_line=34, line=12.0)   # 9열·8pt — 둘째 줄이 잘리지 않게
    put(ws, r + 2, 1, 4, "판매금액", bold=True, color=GRAY)
    put(ws, r + 2, 5, 9, pf.sales, size=12, bold=True, color=PURPLE, fmt=WON, align="right")
    put(ws, r + 3, 1, 4, "판매수량", bold=True, color=GRAY)
    put(ws, r + 3, 5, 9, pf.qty, size=12, bold=True, fmt=EA, align="right")
    for c1, c2, t in ((1, 3, "월"), (4, 5, "정산"), (6, 9, "판매금액(원)")):
        put(ws, r + 4, c1, c2, t, size=9, bold=True, color=GRAY, fill=LIGHT, align="center")
    months = pf.months or [("없음", None, "")]
    for k, (ym, amt, st) in enumerate(months, r + 5):
        put(ws, k, 1, 3, _month_label(ym, basis) if amt is not None else ym, size=9, align="center", border=THIN)
        put(ws, k, 4, 5, st, size=9, align="center", border=THIN)
        put(ws, k, 6, 9, amt, size=9, fmt=PLAIN, align="right", border=THIN)
    return r + 5 + len(months)


def _settle(ws, r: int, pf: Perf) -> int:
    """오른쪽 = 쿠팡 정산 요약(입금 완료·예정·보류·보상·정산 기준 실적) · 끝난 다음 행."""
    _section(ws, r, 12, 20, "쿠팡 정산 요약")
    put(ws, r + 1, 12, 20, "쿠팡 지급 기준 · 단위 원 (입금 예정은 바뀔 수 있음)", size=8, color=GRAY)
    extras = [(f"보상 ({k})", v) for k, v in pf.extras] or [("보상", 0)]
    rows = [("입금 완료", pf.done), ("입금 예정", pf.due), ("보류", pf.hold)] + extras
    for k, (label, v) in enumerate(rows, r + 2):
        put(ws, k, 12, 16, label, bold=True, color=GRAY, border=THIN)
        put(ws, k, 17, 20, v, fmt=PLAIN, align="right", border=THIN)
    k = r + 2 + len(rows)
    put(ws, k, 12, 16, "정산 기준 실적", bold=True, color=PURPLE, fill=LIGHT)
    put(ws, k, 17, 20, pf.result, size=11, bold=True, color=PURPLE, fill=LIGHT, fmt=PLAIN, align="right")
    return k + 1


def _name_height(name: str, per_line: float = 22, line: float = 15.0) -> float:
    """글이 칸 폭(기본 = 상품명 5열·9pt)을 넘으면 줄 수만큼 높임 — 병합 칸은 엑셀이 높이를 맞추지 않음."""
    units = sum(1.5 if ord(ch) > 0x2E80 else 0.8 for ch in name)
    return line * max(1, math.ceil(units / per_line))


def _products(ws, r: int, pf: Perf) -> int:
    for c1, c2, t in ((1, 5, "상품"), (6, 7, "수량"), (8, 9, "판매금액(원)")):
        put(ws, r, c1, c2, t, size=9, bold=True, color=GRAY, fill=LIGHT, align="center")
    ps = list(pf.products)
    if len(ps) > MAX_PRODUCTS:
        rest = ps[MAX_PRODUCTS - 1:]
        ps = ps[:MAX_PRODUCTS - 1] + [(f"그 밖 {len(rest)}개 상품", sum(x[1] for x in rest), sum(x[2] for x in rest))]
    for k, (name, q, amt) in enumerate(ps or [("없음", None, None)], r + 1):
        put(ws, k, 1, 5, name, size=9, border=THIN)
        put(ws, k, 6, 7, q, size=9, fmt=PLAIN, align="right", border=THIN)
        put(ws, k, 8, 9, amt, size=9, fmt=PLAIN, align="right", border=THIN)
        ws.row_dimensions[k].height = _name_height(str(name))
    return r + 1 + max(len(ps), 1)


def _page(ws, last: int) -> None:
    ws.print_area = f"A1:T{last}"
    ps = ws.page_setup
    ps.orientation, ps.paperSize, ps.fitToWidth, ps.fitToHeight = "portrait", ws.PAPERSIZE_A4, 1, 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    m = ws.page_margins
    m.left = m.right = 0.5
    m.top = m.bottom = 0.6
    m.header = m.footer = 0.5
    ws.print_options.horizontalCentered = True
    ws.sheet_view.showGridLines = False


def write(path: Path, c: Contract, pf: Perf, basis: str, issued: str) -> Path:
    """계약 1건 = 셀독 정산서 1장(새 파일 · 있으면 덮어쓰지 않고 FileExistsError)."""
    if path.exists():
        raise FileExistsError(path)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = SHEET
    for k in range(20):
        ws.column_dimensions[chr(65 + k)].width = 4.6
    _head(ws, c, pf, basis, issued)
    r = _contract(ws, 12, c) + 1
    r = max(_sales(ws, r, pf, basis), _settle(ws, r, pf)) + 1
    r = _products(ws, r, pf) + 1
    put(ws, r, 1, 20, FOOT, size=9, color=GRAY, align="center")
    _page(ws, r)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
