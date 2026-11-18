"""위탁자 정산서(3차 형식 · 구글시트) 그리기 바탕 — 색·칸 서식·행 쌓기(Page)·쪽 나누기·Sheets API 요청 만들기.

T-38 S3: 샘플 `output\\_샘플_261115_위탁자정산서\\_sheet\\render_gsheet.py` 의 그리기 바탕을 옮김(요청 모양 같게).
네트워크 없음 · 순수 함수. 형식 규칙 = D-238·D-240·D-241 ④(넘치면 다음 쪽 · 줄 높이 압축·글자 줄이기 없음).
"""
from __future__ import annotations

import copy


class StatementLayoutError(ValueError):
    """쪽 높이 넘침·나눌 수 없는 묶음 — 그리지 않고 중단."""


# ── 3차 샘플 색 (HTML :root 그대로) ─────────────────────────────
def _rgb(h: str) -> dict:
    h = h.lstrip("#")
    return {"red": int(h[0:2], 16) / 255, "green": int(h[2:4], 16) / 255, "blue": int(h[4:6], 16) / 255}


C = {k: _rgb(v) for k, v in {
    "p": "#5b3fa0", "p2": "#efeaf8", "ink": "#1f1f24", "mute": "#6b6b78", "line": "#dcd8e6",
    "red": "#c0392b", "blue": "#1f6fb2", "amber": "#b7791f", "amber2": "#fdf3e1", "sum": "#faf9fc",
    "white": "#ffffff", "mainK": "#e4dcf5", "boxT": "#6b4b10", "boxL": "#f0dcb4", "badge": "#c0392b",
}.items()}
FONT = "Noto Sans KR"
MARGIN = 42                       # 11mm ≈ 42px (위아래·좌우 여백)
PAGE_H = 1067                     # A4 비율(폭 814px → 높이 1151px) − 위아래 여백 84px (샘플 기준)
GAP = 18                          # 여러 쪽일 때 묶음 사이 틈(위에서부터 쌓음)
SPREAD_GAP = 12                   # 한 쪽에 다 들어가는지 볼 때 묶음 사이 최소 틈
# 내용 폭 730px 을 나누는 세로 경계(px) — 카드 사이 틈·2쪽 두 표 사이 틈을 위한 좁은 칸 포함
B = [0, 11, 132, 198, 237, 247, 264, 330, 359, 371, 396, 462, 483, 493, 528, 594, 660, 719, 730]
NUM_COLS = len(B) - 1 + 2         # 좌우 여백 칸
CONTENT_W = B[-1]

MINUS = "−"
FMT_PLAIN = f'#,##0;"{MINUS}"#,##0;0'
FMT_SIGNED = f'"+"#,##0;"{MINUS}"#,##0;0'
FMT_WON = f'#,##0"원";"{MINUS}"#,##0"원";0"원"'
CIRC = "⓪①②③④⑤⑥⑦⑧⑨⑩⑪⑫"
CARD_PAD = (6, 12, 6, 12)


def col(x: int) -> int:
    """세로 경계 x(px) → 시트 열 번호(0 = 왼쪽 여백 칸)."""
    return 1 + B.index(x)


def tf(size=10, bold=False, color="ink") -> dict:
    return {"fontFamily": FONT, "fontSize": size, "bold": bold, "foregroundColor": C[color]}


def _runs_value(runs) -> tuple[str, list[dict]]:
    text, tfr, i = "", [], 0
    for t, s, b, c in runs:
        tfr.append({"startIndex": i, "format": tf(s, b, c)})
        text += t
        i += len(t)
    return text, tfr


def cell(value=None, *, size=10, bold=False, color="ink", bg=None, align="LEFT", fmt=None,
         runs=None, wrap=True, valign="MIDDLE", pad=(2, 7, 2, 7)) -> dict:
    """칸 하나(CellData). runs = [(글자, size, bold, color), ...] 이면 서식 있는 글자(value 무시)."""
    f = {"textFormat": tf(size, bold, color), "horizontalAlignment": align, "verticalAlignment": valign,
         "wrapStrategy": "WRAP" if wrap else "CLIP",
         "padding": {"top": pad[0], "right": pad[1], "bottom": pad[2], "left": pad[3]}}
    if bg:
        f["backgroundColor"] = C[bg]
    d: dict = {"userEnteredFormat": f}
    if runs:
        text, tfr = _runs_value(runs)
        d["userEnteredValue"] = {"stringValue": text}
        d["textFormatRuns"] = tfr
    elif isinstance(value, (int, float)):
        d["userEnteredValue"] = {"numberValue": value}
        f["numberFormat"] = {"type": "NUMBER", "pattern": fmt or FMT_PLAIN}
    elif value is not None and str(value).startswith("="):
        d["userEnteredValue"] = {"formulaValue": value}
    elif value is not None:
        d["userEnteredValue"] = {"stringValue": str(value)}
    return d


def _amt_color(v: int, signed: bool) -> str:
    if signed:
        return "red" if v < 0 else "blue" if v > 0 else "ink"
    return "red" if v < 0 else "ink"


def amt(v: int, *, signed=True, size=10, bold=False, bg=None, color=None) -> dict:
    """빼는 돈 빨강 · 받는 돈(부호 +) 파랑 · signed=False 는 부호 없이 검정(판매 금액·합계)."""
    return cell(v, size=size, bold=bold, color=color or _amt_color(v, signed), bg=bg, align="RIGHT",
                fmt=FMT_SIGNED if (signed and v > 0) else FMT_PLAIN, wrap=False)


def won(v: int) -> str:
    """카드 큰 숫자 글자 — 음수는 '−' 기호."""
    return f"{MINUS}{abs(v):,}원" if v < 0 else f"{v:,}원"


class Page:
    """행 단위로 쌓는다. row = {h, cells:[(x0,x1,cell)], borders:[(x0,x1,side,style,color)], bg}
    keep = 쪽을 넘겨 나눌 때 새 쪽에 다시 붙일 머리 행 수(0 = 나누지 않고 통째로 다음 쪽)."""

    def __init__(self, keep: int = 0):
        self.rows: list[dict] = []
        self.boxes: list[tuple] = []      # (r0, r1, x0, x1, style, color)
        self.keep = keep

    def row(self, h: int, cells=(), borders=(), bg=None) -> int:
        self.rows.append({"h": h, "cells": list(cells), "borders": list(borders), "bg": bg})
        return len(self.rows) - 1

    def spacer(self, h: int) -> None:
        self.row(max(int(h), 1))

    def height(self) -> int:
        return sum(r["h"] for r in self.rows)


# ── 공통 조각 ─────────────────────────────────────────────────
def head(pg: Page, title: str, sub: str, who: str) -> None:
    """제목 + 오른쪽 위탁자 줄(판매 기간·발행 줄 = 진하게 D-260) + 아래 굵은 보라 선."""
    h = 36 if who.count("\n") < 2 else 48
    lines = who.split("\n")
    who_runs = [(ln + ("\n" if i < len(lines) - 1 else ""), 9, ln.startswith("판매 기간"),
                 "ink" if ln.startswith("판매 기간") else "mute") for i, ln in enumerate(lines)]
    pg.row(h, [(0, 330, cell(runs=[(title, 17, True, "ink")], valign="BOTTOM", pad=(0, 0, 0, 0))),
               (330, 730, cell(runs=who_runs, align="RIGHT", valign="BOTTOM", pad=(0, 0, 0, 0)))])
    pg.row(22, [(0, 730, cell(sub, size=8, color="mute", valign="TOP", pad=(2, 0, 6, 0)))],
           borders=[(0, 730, "bottom", "SOLID_THICK", "p")])


def h2(pg: Page, title: str, small: str = "", x1: int = 730) -> None:
    runs = [(title, 11, True, "p")] + ([("   " + small, 9, False, "mute")] if small else [])
    pg.row(26, [(0, x1, cell(runs=runs, valign="BOTTOM", pad=(0, 0, 3, 0)))])


def th_row(pg: Page, cols: list[tuple], h=22) -> None:
    """cols = [(x0, x1, 글자, 'LEFT'|'RIGHT')]"""
    pg.row(h, [(a, b, cell(t, size=8, color="mute", align=al, valign="BOTTOM")) for a, b, t, al in cols],
           borders=[(cols[0][0], cols[-1][1], "bottom", "SOLID", "ink")])


def foot(pg: Page, text: str) -> None:
    pg.row(24, [(0, 730, cell(text, size=8, color="mute", valign="BOTTOM", pad=(5, 0, 0, 0)))],
           borders=[(0, 730, "top", "SOLID", "line")])


def numbered(no: int, name: str, color="p", extra=None) -> dict:
    runs = [(CIRC[no] + " ", 11, True, color), (name, 10, False, "ink")]
    if extra:
        runs.append(("  " + extra, 8, False, "amber"))
    return cell(runs=runs)


def name_h(name: str, chars_per_line: float, base=24, per=14) -> int:
    """글자 줄 수 추정 — 한글·기호 = 1 · 영문·숫자·공백 = 0.6 (글자 크기는 그대로 · 줄 수만 셈)."""
    w = sum(1.0 if ord(ch) > 0x2000 else 0.6 for ch in name)
    n = max(1, -(-w // chars_per_line))
    return int(max(base, 10 + per * n))


def cards_row(pg: Page, left, mid, main_runs, tall: bool) -> None:
    """카드 3개(틈 = 좁은 칸 237~247 · 483~493) · 오른쪽 = 보라 큰 카드."""
    pg.row(124 if tall else 98, [
        (0, 237, cell(runs=left, pad=CARD_PAD)),
        (247, 483, cell(runs=mid, pad=CARD_PAD)),
        (493, 730, cell(runs=main_runs, bg="p", pad=CARD_PAD)),
    ])
    pg.boxes += [(0, 0, 0, 237, "SOLID", "line"), (0, 0, 247, 483, "SOLID", "line"), (0, 0, 493, 730, "SOLID", "p")]


# ── 쪽 만들기(D-241 ④: 넘치면 다음 쪽 · 줄 높이 압축·글자 줄이기 없음) ──────────────
def _ints(total: int, n: int) -> list[int]:
    """total 을 n 개 정수로 고르게(합 = total)."""
    if n <= 0:
        return []
    q, r = divmod(total, n)
    return [q + (1 if i < r else 0) for i in range(n)]


def place(out: Page, p: Page) -> None:
    """p 의 행·상자를 out 아래에 이어 붙인다(상자 행 번호 옮김)."""
    base = len(out.rows)
    out.rows += p.rows
    out.boxes += [(base + a, base + b, x0, x1, s, c) for a, b, x0, x1, s, c in p.boxes]


def _fill(groups: list[Page], spread: bool, height: int = PAGE_H) -> Page:
    """한 쪽: spread = 묶음 사이 틈을 같게(HTML space-between) · 아니면 GAP 으로 위에서부터 쌓고 아래를 비움. 높이 = height 정확히."""
    used = sum(p.height() for p in groups)
    out = Page()
    if spread and len(groups) > 1:
        gaps = _ints(height - used, len(groups) - 1)
        tail = 0
    else:
        gaps = [GAP] * (len(groups) - 1)
        tail = height - used - sum(gaps)
    if min(gaps + [tail]) < 0:
        raise StatementLayoutError(f"쪽 높이 넘침 {used + sum(gaps)} > {height}")
    for i, p in enumerate(groups):
        if i:
            out.spacer(gaps[i - 1])
        place(out, p)
    if tail:
        out.spacer(tail)
    if out.height() != height:
        raise StatementLayoutError(f"쪽 높이 {out.height()} ≠ {height}")
    return out


def _split(p: Page, room: int) -> tuple[Page | None, Page]:
    """묶음 p 를 room 높이에 들어가는 앞부분과 나머지로(나머지 앞에 머리 keep 행 다시 붙임). 앞부분이 머리 + 2줄도 안 되면 None."""
    hdr = p.rows[:p.keep]
    acc, k = 0, 0
    for i, r in enumerate(p.rows):
        if acc + r["h"] > room:
            break
        acc += r["h"]
        k = i + 1
    k = min(k, len(p.rows) - 3)                  # 나머지에 합계 줄 + 최소 2줄(합계 줄만 다음 쪽으로 떨어지지 않게)
    if k < p.keep + 2:                           # 앞쪽에 머리 + 2줄도 못 남기면 통째로 다음 쪽
        return None, p
    a, b = Page(keep=p.keep), Page(keep=p.keep)
    a.rows = p.rows[:k]
    b.rows = [dict(r) for r in hdr] + p.rows[k:]
    return a, b


def paginate(groups: list[Page], cont_head) -> list[Page]:
    """묶음들을 쪽으로 — 다 들어가면 1쪽(space-between) · 넘치면 묶음 단위로 다음 쪽(한 묶음이 남은 자리보다 크고 나눌 수 있으면 줄 단위로 나눔 ·
    새 쪽 머리 = cont_head() '… (계속)'). 새 쪽 머리 다음에도 안 들어가고 나눌 수도 없으면 중단(샘플은 무한 반복)."""
    need = sum(p.height() for p in groups) + SPREAD_GAP * (len(groups) - 1)
    if need <= PAGE_H:
        return [_fill(groups, spread=True)]
    pages: list[Page] = []
    cur: list[Page] = []
    fresh = False                                # cur = 새 쪽 머리만 있음
    queue = list(groups)
    while queue:
        p = queue.pop(0)
        used = sum(x.height() for x in cur) + GAP * len(cur)
        if used + p.height() <= PAGE_H:
            cur.append(p)
            fresh = False
            continue
        a, rest = (_split(p, PAGE_H - used) if p.keep and not p.boxes else (None, p))
        if a is None and (not cur or fresh):
            raise StatementLayoutError("묶음 하나가 한 쪽보다 크고 나눌 수 없음")
        if a is not None:
            cur.append(a)
        pages.append(_fill(cur, spread=False))
        cur, fresh = [cont_head()], True
        queue.insert(0, rest)
    if cur:
        pages.append(_fill(cur, spread=False))
    return pages


def stack_pages(pages: list[Page]) -> Page:
    """쪽마다 위 여백 + 내용(PAGE_H) + 아래 여백 = A4 한 장 · 위아래로 이어 붙임."""
    pg = Page()
    for part in pages:
        pg.spacer(MARGIN)
        place(pg, part)
        pg.spacer(MARGIN)
    return pg


# ── 구글시트 요청 만들기 ────────────────────────────────────────
_BLANK = cell(None, bg="white")


def _row_values(r: dict) -> tuple[list[dict], list[tuple[int, int]]]:
    """한 행의 칸 값 목록(여백 칸 포함) + 병합할 열 범위들."""
    vals = [copy.deepcopy(_BLANK) for _ in range(NUM_COLS)]
    merges = []
    for x0, x1, c in r["cells"]:
        c0, c1 = col(x0), col(x1)
        vals[c0] = c
        bg = c["userEnteredFormat"].get("backgroundColor")
        for k in range(c0 + 1, c1):
            if bg:
                vals[k] = cell(None, bg=None)
                vals[k]["userEnteredFormat"]["backgroundColor"] = bg
        if c1 - c0 > 1:
            merges.append((c0, c1))
    return vals, merges



def _rng(sid: int, r0: int, r1: int, c0: int, c1: int) -> dict:
    return {"sheetId": sid, "startRowIndex": r0, "endRowIndex": r1, "startColumnIndex": c0, "endColumnIndex": c1}


def _dim(sid: int, dim: str, i: int, px: int) -> dict:
    return {"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": dim, "startIndex": i, "endIndex": i + 1},
                                          "properties": {"pixelSize": px}, "fields": "pixelSize"}}


def _border_requests(pg: Page, sid: int) -> list[dict]:
    out = []
    for ri, r in enumerate(pg.rows):
        for x0, x1, side, style, color in r["borders"]:
            out.append({"updateBorders": {"range": _rng(sid, ri, ri + 1, col(x0), col(x1)),
                                          side: {"style": style, "color": C[color]}}})
    for r0, r1, x0, x1, style, color in pg.boxes:
        b = {"style": style, "color": C[color]}
        out.append({"updateBorders": {"range": _rng(sid, r0, r1 + 1, col(x0), col(x1)),
                                      "top": b, "bottom": b, "left": b, "right": b}})
    return out


def requests_for(pg: Page, sid: int) -> list[dict]:
    """탭 하나(sheetId = sid)를 다시 그리는 batchUpdate 요청 — 크기·열 너비·칸 값/서식·행 높이·병합·테두리 순."""
    widths = [MARGIN] + [B[i + 1] - B[i] for i in range(len(B) - 1)] + [MARGIN]
    reqs = [{"updateSheetProperties": {"properties": {"sheetId": sid, "gridProperties": {
        "rowCount": len(pg.rows), "columnCount": NUM_COLS, "hideGridlines": True}},
        "fields": "gridProperties(rowCount,columnCount,hideGridlines)"}}]
    reqs += [_dim(sid, "COLUMNS", i, w) for i, w in enumerate(widths)]
    rows, row_reqs = [], []
    for ri, r in enumerate(pg.rows):
        row_reqs.append(_dim(sid, "ROWS", ri, int(r["h"])))
        vals, merges = _row_values(r)
        row_reqs += [{"mergeCells": {"range": _rng(sid, ri, ri + 1, c0, c1), "mergeType": "MERGE_ALL"}}
                     for c0, c1 in merges]
        if ri == 0:
            vals[-1] = cell(" ", bg="white")      # 오른쪽 여백 칸이 PDF 내보내기에서 잘리지 않게
        rows.append({"values": vals})
    update: dict = {"start": {"sheetId": sid, "rowIndex": 0, "columnIndex": 0}, "rows": rows,
                    "fields": "userEnteredValue,userEnteredFormat,textFormatRuns"}
    reqs.append({"updateCells": update})
    return reqs + row_reqs + _border_requests(pg, sid)
