"""통합판매현황 상단 대시보드 그리기·차트(엑셀·구글) — SSOT=designs/SALES_SUMMARY.md §5-1(소유자 2026-10-21).

①요약 표 → ②월별 막대·③주간 선·④일별 막대(차트) → ⑤계정 순위 표(8주 미니 그래프 ▁▂▃▅▇ 글자) → ⑥상품 상위 20 × 8주
열지도(금액 단계별 **고정 채움색** — 구글 미러가 조건부서식을 못 옮김). 집계 = sales_dashboard(순수).
차트 자료 = 같은 시트 오른쪽 **숨긴 열** · 차트 설정(JSON) = 그 첫 칸(1행)에 저장 → ① openpyxl 은 파일을 다시 열면
차트를 버리므로 OutputWorkbook.load 가 restore_charts 로 다시 붙이고 ② 구글 반영도 같은 설정으로 addChart.
⚠ 구글은 고정 열(A:C)과 비고정 열에 걸친 병합을 400 으로 거부 → 병합은 D 열부터의 짝(D:E·F:G…)만.
"""
from __future__ import annotations

import json

from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import column_index_from_string, get_column_letter

from .workbook_sales import _FILL_HEAD, _FILL_SEC, _FILL_SUB, _FILL_TOTAL, _FN, SALES_SHEET, _cell

SPEC_PREFIX = "차트설정:"
CHART_ROWS = 15                 # 차트 한 줄이 차지하는 행 수(행 20px × 15 > 차트 높이 280px)
DATA_WIDTH = 9                  # 숨긴 차트 자료 열 수(월 3 · 빈칸 · 주 2 · 빈칸 · 일 2)
_W_HALF, _W_FULL, _H = 520, 1048, 280
_BAND_LAST = 11                 # 구역 제목 띠 끝 열(K)
_GREEN, _RED, _GRAY = "1E8E3E", "C00000", "9AA7B6"
_C_DONE, _C_PART, _C_LINE, _C_DAY = "4472C4", "A9C4EB", "2F5597", "5B9BD5"
# 열지도 단계(표 안 최대 금액 대비 비율 상한, 채움색, 글자색)
_HEAT = ((0.2, "EAF1FB", None), (0.4, "C9DCF2", None), (0.6, "9DC3E6", None),
         (0.8, "5B9BD5", "FFFFFF"), (9.9, "2F75B5", "FFFFFF"))


def write_dashboard(ws, d, r: int, data_col: int) -> int:
    """대시보드를 r 행부터 그리고 다음 빈 행 반환. 차트 자료·설정 = data_col 부터 숨긴 열."""
    r = _kpis(ws, r, d) + 2
    r, specs = _charts(ws, r, d, data_col)
    r = _ranks(ws, r + 1, d) + 2
    r = _heat(ws, r, d)
    ws.cell(1, data_col, SPEC_PREFIX + json.dumps(specs, ensure_ascii=False))
    for c in range(data_col, data_col + DATA_WIDTH):
        ws.column_dimensions[get_column_letter(c)].hidden = True
    add_xl_charts(ws, specs)
    return r


# ── 표 ───────────────────────────────────────────────────────
def _band(ws, r, title):
    _cell(ws, r, 1, title, font=Font(name=_FN, size=12, bold=True), fill=_FILL_SEC)
    for c in range(2, _BAND_LAST + 1):
        _cell(ws, r, c, None, fill=_FILL_SEC)


def _pair(ws, r, c, v, **kw):
    """D:E 같은 두 칸 짝(병합) — 비고정 열 안에서만."""
    _cell(ws, r, c, v, **kw)
    _cell(ws, r, c + 1, None, fill=kw.get("fill"), box=kw.get("box", False))
    ws.merge_cells(start_row=r, start_column=c, end_row=r, end_column=c + 1)


def _head(ws, r, heads: list, pairs: list) -> None:
    for c, h in enumerate(heads, 1):
        _cell(ws, r, c, h, bold=True, fill=_FILL_HEAD, box=True, center=True)
    for i, h in enumerate(pairs):
        _pair(ws, r, 4 + 2 * i, h, bold=True, fill=_FILL_HEAD, box=True, center=True)


def pct_text(v: float | None, signed: bool = True) -> tuple[str, str | None]:
    """비율 → ('▲ 12.3%', 초록) · ('▼ 5.0%', 빨강) · 비교 불가 = ('—', 회색)."""
    if v is None:
        return "—", _GRAY
    if not signed:
        return f"{v * 100:.1f}%", None
    if round(v * 1000) == 0:
        return "0.0%", None
    return (f"▲ {v * 100:.1f}%", _GREEN) if v > 0 else (f"▼ {-v * 100:.1f}%", _RED)


def _kpis(ws, r, d) -> int:
    _band(ws, r, "① 요약 — 관리 상품 기준(결과 사업자 시트의 상품·판매중지 포함 · 상세표 합계와 같음)")
    _head(ws, r + 1, ["구분", "판매금액(원)", "수량"], ["증감"])
    _cell(ws, r + 1, 6, "비교 기준", bold=True, fill=_FILL_HEAD, box=True)
    for k in d.kpis:
        r += 1
        _cell(ws, r + 1, 1, f"{k.title} {k.span}", bold=True, fill=_FILL_TOTAL, box=True)
        _cell(ws, r + 1, 2, k.amount, bold=True, fill=_FILL_TOTAL, box=True, num=True)
        _cell(ws, r + 1, 3, k.qty, fill=_FILL_TOTAL, box=True, num=True)
        text, color = pct_text(k.change) if k.basis else ("", None)
        _pair(ws, r + 1, 4, text or None, bold=True, fill=_FILL_TOTAL, box=True, center=True, color=color)
        note = " · ".join(x for x in (k.basis, f"미수집 {k.missing}계정 제외" if k.missing else "") if x)
        _cell(ws, r + 1, 6, note or None, color="595959")
    r += 2
    _cell(ws, r, 1, "미수집 계정(전일)", bold=True, fill=_FILL_SUB, box=True)
    _cell(ws, r, 2, f"{d.missing_today} / {d.accounts_total} 계정", bold=True, fill=_FILL_SUB, box=True,
          color=_RED if d.missing_today else None)
    _cell(ws, r, 3, None, fill=_FILL_SUB, box=True)
    return r


def _ranks(ws, r, d) -> int:
    _band(ws, r, "⑤ 계정 순위 — 이번 달 누계 판매금액 순")
    _head(ws, r + 1, ["계정", "최근 8주 추이(오래된 주 → 최신 · ▁ 적음 █ 많음 · '·' 미수집)", "순위"],
          ["이번 달 누계", "지난달 같은 기간", "증감", "비중"])
    r += 1
    for i, a in enumerate(d.accounts, 1):
        r += 1
        fill = _FILL_SUB if i % 2 == 0 else None
        _cell(ws, r, 1, a.label, fill=fill, box=True)
        _cell(ws, r, 2, a.spark, font=Font(name=_FN, size=12, color=_C_LINE), fill=fill, box=True)
        _cell(ws, r, 3, i if a.amount is not None else None, fill=fill, box=True, center=True)
        _pair(ws, r, 4, a.amount if a.amount is not None else "미수집", fill=fill, box=True, num=True,
              color=None if a.amount is not None else _GRAY)
        _pair(ws, r, 6, a.prev if a.prev is not None else "미수집", fill=fill, box=True, num=True,
              color=None if a.prev is not None else _GRAY)
        text, color = pct_text(a.change)
        _pair(ws, r, 8, text, fill=fill, box=True, center=True, color=color)
        _pair(ws, r, 10, pct_text(a.share, signed=False)[0], fill=fill, box=True, center=True)
    return r


def heat_style(v: int | None, top: int) -> tuple[PatternFill | None, str | None]:
    """열지도 칸 채움·글자색 — 금액 ÷ 표 안 최대 금액 단계별 고정색 · 0/미수집 = 채움 없음."""
    if not v or not top:
        return None, (_GRAY if v is None else None)
    ratio = v / top
    for limit, fg, font in _HEAT:
        if ratio <= limit:
            return PatternFill("solid", fgColor=fg), font
    return None, None


def _heat(ws, r, d) -> int:
    _band(ws, r, f"⑥ 상품 상위 {len(d.products) or 20} — 최근 8주 판매금액(오래된 주 → 최신 · 진할수록 많음)")
    _head(ws, r + 1, ["계정", "상품", "구분"], [*d.week_labels, "8주 합계"])
    top = max((v or 0 for p in d.products for v in p.weeks), default=0)
    r += 1
    for p in d.products:
        r += 1
        for c, v in enumerate((p.account, p.product, p.kind), 1):
            _cell(ws, r, c, v, box=True, color=_GRAY if c == 1 else None)
        for i, v in enumerate(p.weeks):
            fill, color = heat_style(v, top)
            _pair(ws, r, 4 + 2 * i, "미수집" if v is None else v, fill=fill, box=True, num=True, color=color)
        _pair(ws, r, 4 + 2 * len(p.weeks), p.total, bold=True, fill=_FILL_TOTAL, box=True, num=True)
    if not d.products:
        r += 1
        _cell(ws, r, 1, "최근 8주 판매 기록 없음", color=_GRAY)
    r += 1
    _cell(ws, r, 1, "색 단계 = 표 안 최대 주간 금액의 ~20% · ~40% · ~60% · ~80% · 그 이상 · '미수집' = 그 주 자료 없음",
          color="595959")
    return r


# ── 차트 자료·설정 ─────────────────────────────────────────────
def _charts(ws, r, d, data_col) -> tuple[int, list]:
    _band(ws, r, "② 월별 · ③ 주간(최근 8주·월~일) · ④ 일별(최근 31일) 판매금액(원) — 관리 상품")
    top = r + 1
    mc, wc, dc = data_col, data_col + 4, data_col + 7
    _table(ws, top, mc, ("월", "완료 월", "진행 중(누계)"),
           [(p.label, None if p.partial else p.amount, p.amount if p.partial else None) for p in d.months])
    _table(ws, top, wc, ("주(월요일)", "판매금액"), [(p.label, p.amount) for p in d.weeks])
    _table(ws, top, dc, ("일", "판매금액"), [(p.label, p.amount) for p in d.days])
    nm, nw, nd = top + len(d.months), top + len(d.weeks), top + len(d.days)
    specs = [
        {"type": "bar", "title": "② 월별 판매금액", "row": top, "col": 1, "w": _W_HALF, "h": _H, "stacked": True,
         "cat": [top, nm, mc], "series": [[top, nm, mc + 1], [top, nm, mc + 2]], "colors": [_C_DONE, _C_PART]},
        {"type": "line", "title": "③ 주간 판매금액(최근 8주)", "row": top, "col": 3, "w": _W_HALF, "h": _H,
         "cat": [top, nw, wc], "series": [[top, nw, wc + 1]], "colors": [_C_LINE]},
        {"type": "bar", "title": "④ 일별 판매금액(최근 31일)", "row": top + CHART_ROWS, "col": 1, "w": _W_FULL,
         "h": _H, "cat": [top, nd, dc], "series": [[top, nd, dc + 1]], "colors": [_C_DAY], "skip": 2},
    ]
    return top + 2 * CHART_ROWS, specs


def _table(ws, r, c, heads, rows) -> None:
    for i, h in enumerate(heads):
        ws.cell(r, c + i, h)
    for j, row in enumerate(rows, 1):
        for i, v in enumerate(row):
            x = ws.cell(r + j, c + i, v)
            if i:
                x.number_format = "#,##0"


def read_specs(ws) -> list:
    """시트 1행에 저장한 차트 설정 — 없으면 빈 목록."""
    for row in ws.iter_rows(min_row=1, max_row=1, values_only=True):
        for v in row:
            if isinstance(v, str) and v.startswith(SPEC_PREFIX):
                return json.loads(v[len(SPEC_PREFIX):])
    return []


def add_xl_charts(ws, specs: list) -> None:
    for sp in specs:
        ch = BarChart() if sp["type"] == "bar" else LineChart()
        ch.title = sp["title"]
        ch.title.overlay = False                                   # 제목이 그림 위로 겹치지 않게
        ch.varyColors = False                                      # 점·막대마다 다른 색 안 씀
        ch.width, ch.height = sp["w"] / 37.8, sp["h"] / 37.8      # 픽셀 → cm
        ch.visible_cells_only = False                              # 자료 열이 숨김이어도 그림
        for r1, r2, c in sp["series"]:
            ch.add_data(Reference(ws, min_col=c, min_row=r1, max_row=r2), titles_from_data=True)
        r1, r2, c = sp["cat"]
        ch.set_categories(Reference(ws, min_col=c, min_row=r1 + 1, max_row=r2))
        if sp.get("stacked"):
            ch.grouping, ch.overlap = "stacked", 100
        if len(sp["series"]) == 1:
            ch.legend = None
        else:
            ch.legend.position, ch.legend.overlay = "b", False
        ch.x_axis.delete = ch.y_axis.delete = False
        if sp.get("skip"):
            ch.x_axis.tickLblSkip = sp["skip"]                     # 일별 31칸 = 날짜 글자 하나 걸러
        for s, color in zip(ch.series, sp["colors"]):
            if sp["type"] == "bar":
                s.graphicalProperties.solidFill = color
            else:
                s.graphicalProperties.line.solidFill = color
                s.smooth = False
                s.marker.symbol = "circle"
                s.marker.graphicalProperties.solidFill = color
                s.marker.graphicalProperties.line.solidFill = color
        ws.add_chart(ch, f"{get_column_letter(sp['col'])}{sp['row']}")


def restore_charts(xwb) -> None:
    """파일을 다시 열면(openpyxl) 차트가 빠짐 → 저장해 둔 설정으로 다시 붙임(OutputWorkbook.load)."""
    if SALES_SHEET not in xwb.sheetnames:
        return
    ws = xwb[SALES_SHEET]
    if not ws._charts:
        add_xl_charts(ws, read_specs(ws))


# ── 구글시트 ──────────────────────────────────────────────────
def gsheet_requests(ws, gid: int, old_chart_ids: list) -> tuple[list, list]:
    """(먼저 보낼 요청 = 옛 차트 삭제, 나중 요청 = 숨긴 열 + 차트 추가) — 미러(worksheet_to_requests)는 둘 다 못 옮김."""
    first = [{"deleteEmbeddedObject": {"objectId": i}} for i in old_chart_ids]
    later = _hidden_columns(ws, gid) + [{"addChart": {"chart": _g_chart(sp, gid)}} for sp in read_specs(ws)]
    return first, later


def _hidden_columns(ws, gid: int) -> list:
    def dim(s, e, hidden):
        return {"updateDimensionProperties": {
            "range": {"sheetId": gid, "dimension": "COLUMNS", "startIndex": s, "endIndex": e},
            "properties": {"hiddenByUser": hidden}, "fields": "hiddenByUser"}}
    reqs = [dim(0, ws.max_column, False)]                         # 지난 실행의 숨김 잔재 초기화
    for letter, d in ws.column_dimensions.items():                # 다시 연 파일은 열 묶음(min~max)으로 읽힘
        if d.hidden:
            lo = d.min or column_index_from_string(letter)        # 이번에 그린 시트 = min 없음(저장 때 채워짐)
            reqs.append(dim(lo - 1, min(d.max or lo, ws.max_column), True))
    return reqs


def _g_chart(sp: dict, gid: int) -> dict:
    from .gsheet_stats import _rgb_to_color

    def grid(r1, r2, c):
        return {"sheetId": gid, "startRowIndex": r1 - 1, "endRowIndex": r2, "startColumnIndex": c - 1,
                "endColumnIndex": c}
    series = [{"series": {"sourceRange": {"sources": [grid(*s)]}}, "targetAxis": "LEFT_AXIS",
               "colorStyle": {"rgbColor": _rgb_to_color(color)}} for s, color in zip(sp["series"], sp["colors"])]
    basic = {"chartType": "COLUMN" if sp["type"] == "bar" else "LINE",
             "legendPosition": "BOTTOM_LEGEND" if len(series) > 1 else "NO_LEGEND", "headerCount": 1,
             "axis": [{"position": "BOTTOM_AXIS"}, {"position": "LEFT_AXIS"}],
             "domains": [{"domain": {"sourceRange": {"sources": [grid(*sp["cat"])]}}}], "series": series}
    if sp.get("stacked"):
        basic["stackedType"] = "STACKED"
    return {"spec": {"title": sp["title"], "hiddenDimensionStrategy": "SHOW_ALL", "basicChart": basic},
            "position": {"overlayPosition": {
                "anchorCell": {"sheetId": gid, "rowIndex": sp["row"] - 1, "columnIndex": sp["col"] - 1},
                "widthPixels": sp["w"], "heightPixels": sp["h"]}}}
