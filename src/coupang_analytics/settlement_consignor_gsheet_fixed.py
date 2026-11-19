"""위탁자 정산서(3차 형식 · 구글시트) 위탁자 탭 — 고정 형식(D-343): 항목 줄은 계정·달과 상관없이 늘 같은 자리 · 값 없으면 공란.

승인 샘플(소유자 11-19 "샘플 승인." · `output\\_샘플_261118_고정형식정산서\\_render_fixed_sample.py`)의 1쪽·2쪽을 옮김.
고정 줄 이름·순서 = 숫자 모듈이 늘 채워 넘김(6 종류별 9 · 9 계정 공통 9 · 10 별도 입금 3 · 어디로 갔나요 4) — 개수가 다르면 그리지 않고 중단.
쪽: 1쪽 = 요약 · 2쪽 = 고정 표(6|9 · 10|11) · 상품 줄 = 2쪽 남은 자리에 전부 들어가면 2쪽, 아니면 전부 3쪽부터(2쪽엔 안내 + 합계 ·
넘치면 '상품별 상세 (계속)' D-241 ④). 문구 = D-238·D-241 ⑦·D-242·D-251·D-259·D-260(머리·카드·회색 줄).
"""
from __future__ import annotations

from coupang_analytics.settlement_consignor_gsheet_layout import (
    CIRC, GAP, PAGE_H, Page, StatementLayoutError, _fill, cards_row, cell, foot, h2, head, name_h, numbered, paginate, stack_pages, th_row, won,
)
from coupang_analytics.settlement_consignor_gsheet_layout import amt as _amt
from coupang_analytics.settlement_consignor_gsheet_pages import (
    DESC, NAME, NARROW_PAD, PCOLS, PENDING_CARD, PENDING_ROW, SHORT, coupang_took, line_amounts, separate_total, who_line,
)

FIXED_ROWS = {"rg_kinds": 9, "common": 9, "separate": 3, "flow": 4}      # 10 = 우대수수료 2 + 추가지급 1(소유자 11-19 "줄 추가 (추천)")
FOOT = "항목은 계정·달과 상관없이 늘 같은 자리에 있고, 금액이 없는 항목은 비워 두었습니다 · 쿠팡 원본과 원 단위 대조 완료"


def amt(v: int, **kw) -> dict:
    """값 없으면(0) 공란 — D-343."""
    return _amt(v, **kw) if v else cell(None, bg=kw.get("bg"))


def fixed_shape(d: dict) -> None:
    """고정 줄 개수 확인 — 옛 가변 자료(금액 있는 줄만)면 그리지 않고 중단(줄이 어긋나 다른 항목 자리에 그려지는 것 막음)."""
    got = {"rg_kinds": len(d["rg_kinds"]), "common": len(d["common"]["items"]), "separate": len(d["separate"]), "flow": len(d["flow"])}
    if got != FIXED_ROWS:
        raise StatementLayoutError(f"{d['account']} {d['period_start'][:7]}: 고정 형식 줄 수 아님(D-343) {got} ≠ {FIXED_ROWS}")


# ── 1쪽(고정) ──────────────────────────────────────────────
def _p1_cards(d: dict, L: dict[int, int]) -> Page:
    pg = Page()
    sep_total = separate_total(d)
    took = coupang_took(d)
    pend = d.get("pending_total") or 0
    main_runs = [("이번 정산 금액\n", 9, False, "mainK"), (f"{d['settle_amount']:,}원", 21, True, "white"),
                 (f"\n별도 입금 포함 {sep_total:,}원" if sep_total else "\n별도 입금 포함", 9, False, "mainK"),
                 (f"\n{PENDING_CARD}\n{pend:,}원 (바뀔 수 있음)" if pend else f"\n{PENDING_CARD}", 9, True, "white")]
    cards_row(pg, [("고객이 결제한 금액\n", 9, False, "mute"), (f"{L[1]:,}원", 15, True, "ink")],
              [("쿠팡이 뺀 돈 (수수료·비용)\n", 9, False, "mute"), (won(took), 15, True, "red" if took < 0 else "ink")],
              main_runs, tall=True)
    return pg


def _p1_table(d: dict, L: dict[int, int]) -> Page:
    pg = Page()
    h2(pg, "어떻게 계산했나요", "번호마다 2쪽에 같은 번호의 상세가 있습니다")
    th_row(pg, [(0, 264, "항목", "LEFT"), (264, 594, "설명", "LEFT"), (594, 730, "금액", "RIGHT")])
    line = [(0, 730, "bottom", "SOLID", "line")]
    for no in range(1, 9):
        pg.row(26, [(0, 264, numbered(no, NAME[no])), (264, 594, cell(DESC[no], size=8, color="mute")),
                    (594, 730, amt(L[no], signed=no != 1))], borders=line)
    pg.row(28, [(0, 594, cell(runs=[("상품 정산액", 10, True, "ink"), ("  1 ~ 8 합계 · 2쪽 상품별 표의 합계와 같음", 8, False, "mute")], bg="sum")),
                (594, 730, amt(d["product_subtotal"], signed=False, bold=True, bg="sum"))],
           borders=[(0, 730, "top", "SOLID_MEDIUM", "ink")])
    cm = d["common"]
    pg.row(36, [(0, 264, cell(runs=[(CIRC[9] + " ", 11, True, "amber"), ("계정 공통 비용", 10, False, "ink"), ("  상품별로 안 나옴", 8, False, "amber")], bg="amber2")),
                (264, 594, cell(f"쿠팡이 계정 전체로만 청구한 비용 중 관리 상품 몫 ({cm['basis_text']})", size=8, color="mute", bg="amber2")),
                (594, 730, amt(cm["total_applied"], bg="amber2"))], borders=line)
    pg.row(26, [(0, 264, numbered(10, "별도 입금 (우대수수료 환급·추가지급)")),
                (264, 594, cell("쿠팡페이 환급(대표 계좌) · 쿠팡 추가지급", size=8, color="mute")),
                (594, 730, amt(separate_total(d)))], borders=line)
    pg.row(32, [(0, 594, cell(runs=[("이번 정산 금액", 11, True, "ink"), ("  상품 정산액 − 9 + 10", 8, False, "mute")], bg="p2")),
                (594, 730, amt(d["settle_amount"], signed=False, bold=True, size=11, bg="p2"))])
    return pg


def _p1_common_box(d: dict) -> Page:
    """9 설명 상자(노란 칸)."""
    pg = Page()
    cm = d["common"]
    bx = "amber2"
    pg.row(24, [(0, 730, cell("9. 계정 공통 비용이란", bold=True, color="boxT", bg=bx, pad=(6, 11, 0, 11)))])
    pg.row(38, [(0, 730, cell(f"쿠팡이 상품별 금액 없이 계정 전체로만 청구한 비용입니다. 관리 상품 몫만 반영했습니다({cm['basis_text']}). "
                              "항목별 쿠팡 청구 금액은 2쪽 9번에서 확인하실 수 있습니다.", size=9, color="boxT", bg=bx, valign="TOP", pad=(1, 11, 2, 11)))])
    bl = [(11, 719, "bottom", "SOLID", "boxL")]
    pg.row(26, [(0, 11, cell(None, bg=bx)), (11, 594, cell("쿠팡 청구 금액 (계정 전체)", bg=bx, pad=(2, 7, 2, 7))),
                (594, 730, amt(cm["total_coupang"], signed=False, bg=bx))], borders=bl)
    pg.row(28, [(0, 11, cell(None, bg=bx)), (11, 594, cell("이 정산서 반영 (관리 상품 몫)", bold=True, bg=bx, pad=(2, 7, 2, 7))),
                (594, 730, amt(cm["total_applied"], bold=True, bg=bx))], borders=bl)
    pg.row(8, [(0, 730, cell(None, bg=bx))])
    pg.boxes.append((0, 4, 0, 730, "SOLID_MEDIUM", "amber"))
    return pg


def _p1_flow(d: dict) -> Page:
    pg = Page()
    h2(pg, "정산 금액은 어디로 갔나요", "통장과 맞춰 보실 때 · 아래 합 = 이번 정산 금액 · 날짜별 상세는 2쪽 11번")
    r0 = len(pg.rows)
    pg.row(6)
    dash = [(11, 719, "bottom", "DASHED", "line")]
    for f in d["flow"]:
        pg.row(26, [(11, 198, cell(f["name"], pad=(2, 7, 2, 7))), (198, 594, cell(f["desc"], size=8, color="mute")),
                    (594, 730, amt(f["amount"], signed=False))], borders=dash)
    pg.row(28, [(11, 594, cell("합계 = 이번 정산 금액", bold=True, bg="sum", pad=(2, 7, 2, 7))),
                (594, 730, amt(sum(f["amount"] for f in d["flow"]), signed=False, bold=True, bg="sum"))],
           borders=[(11, 719, "top", "SOLID_MEDIUM", "ink")])
    pg.row(6)
    pg.boxes.append((r0, len(pg.rows) - 1, 0, 730, "SOLID", "line"))
    return pg


def page1_groups(d: dict, issued: str) -> list[Page]:
    """1쪽 묶음: 머리 · 카드 3개 · 계산표(1~10) · 9 설명 상자 · 어디로 갔나요. 아래 문의 문구 없음(D-241 ⑦)."""
    L = line_amounts(d)
    top = Page()
    head(top, "쿠팡 판매 정산서", "관리 상품만 정산합니다 · 모든 금액은 쿠팡이 준 정산 자료 기준(원 단위)", who_line(d, issued))
    return [top, _p1_cards(d, L), _p1_table(d, L), _p1_common_box(d), _p1_flow(d)]


# ── 2쪽(고정 표) ─────────────────────────────────────────────
def page2_head(d: dict, title: str = "정산 상세") -> Page:
    pg = Page()
    head(pg, title, "1쪽 번호와 같은 번호 · 합계 줄 = 1쪽 금액 · 회색 = 정산 예정 금액(쿠팡 미확정 · 바뀔 수 있음)",
         f"{d['company']} · {d['account']} · {d['period_start'][:7]} · {d['status']}")
    return pg


def _side_title(pg: Page, left: str, right: str) -> None:
    pg.row(26, [(0, 359, cell(runs=[(left, 11, True, "p")], valign="BOTTOM", pad=(0, 0, 3, 0))),
                (371, 730, cell(runs=[(right, 11, True, "p")], valign="BOTTOM", pad=(0, 0, 3, 0)))])


def _p2_kinds_common(d: dict, L: dict[int, int]) -> Page:
    """6 종류별(왼쪽 9줄 고정) | 9 계정 공통(오른쪽 9줄 고정)."""
    pg = Page()
    _side_title(pg, "6 창고·배송비 종류별", "9 계정 공통 비용")
    hdr = [(0, 264, cell("종류", size=8, color="mute", valign="BOTTOM")), (264, 359, cell("금액", size=8, color="mute", align="RIGHT", valign="BOTTOM")),
           (371, 528, cell("항목", size=8, color="mute", valign="BOTTOM")),
           (528, 660, cell("쿠팡 청구 금액\n(계정 전체)", size=7, color="mute", align="RIGHT", valign="BOTTOM")),
           (660, 730, cell("이 정산서\n반영", size=7, color="mute", align="RIGHT", valign="BOTTOM"))]
    pg.row(30, hdr, borders=[(0, 359, "bottom", "SOLID", "ink"), (371, 730, "bottom", "SOLID", "ink")])
    for k, c in zip(d["rg_kinds"], d["common"]["items"]):
        pend = bool(k.get("pending"))
        pg.row(max(26, name_h(c["name"], 12.5, base=26, per=14)),
               [(0, 264, cell(k["name"], size=9, color="mute" if pend else "ink")),
                (264, 359, amt(k["amount"], size=9, color="mute" if pend and k["amount"] else None)),
                (371, 528, cell(c["name"], size=9, bg="amber2")),
                (528, 660, amt(c["coupang_amount"], signed=False, size=9, bg="amber2")),
                (660, 730, amt(c["applied_amount"], size=9, bg="amber2"))],
               borders=[(0, 359, "bottom", "SOLID", "line"), (371, 730, "bottom", "SOLID", "line")])
    pg.row(28, [(0, 264, cell("합계 (= 1쪽 6)", bold=True, bg="sum")), (264, 359, amt(L[6], bold=True, bg="sum")),
                (371, 528, cell("합계 (= 1쪽 9)", bold=True, bg="sum")),
                (528, 660, amt(d["common"]["total_coupang"], signed=False, bold=True, bg="sum")),
                (660, 730, amt(d["common"]["total_applied"], bold=True, bg="sum"))],
           borders=[(0, 359, "top", "SOLID_MEDIUM", "ink"), (371, 730, "top", "SOLID_MEDIUM", "ink")])
    return pg


def _sep_dep_cells(left: list, right: list, i: int) -> tuple[list, list, list]:
    cells, bords, hs = [], [], [26]
    if i < len(left):
        nm, v, s = left[i]
        cells += [(0, 264, cell(nm, size=9, bold=s, bg="sum" if s else None)), (264, 359, amt(v, size=9, bold=s, bg="sum" if s else None))]
        bords.append((0, 359, "top", "SOLID_MEDIUM", "ink") if s else (0, 359, "bottom", "SOLID", "line"))
        hs.append(name_h(nm, 18, base=26, per=14))
    if i < len(right):
        dt, desc, v, s = right[i]
        if s:
            cells += [(371, 660, cell(desc, size=9, bold=True, bg="sum")), (660, 730, amt(v, signed=False, size=9, bold=True, bg="sum"))]
            bords.append((371, 730, "top", "SOLID_MEDIUM", "ink"))
        else:
            cells += [(371, 462, cell(dt, size=9)), (462, 660, cell(desc, size=8)), (660, 730, amt(v, signed=False, size=9))]
            bords.append((371, 730, "bottom", "SOLID", "line"))
            hs.append(name_h(desc, 17, base=26, per=13))
    return cells, bords, hs


def _p2_sep_dep(d: dict) -> Page:
    """10 별도 입금(왼쪽 3줄 고정) | 11 날짜별 입금(오른쪽 · 날짜 목록) — 넘치면 줄 단위로 다음 쪽(머리 2줄 반복)."""
    pg = Page(keep=2)
    _side_title(pg, "10 별도 입금", "11 정산 금액 입금 내역 (날짜별)")
    pg.row(22, [(0, 264, cell("내용", size=8, color="mute", valign="BOTTOM")), (264, 359, cell("금액", size=8, color="mute", align="RIGHT", valign="BOTTOM")),
                (371, 462, cell("날짜", size=8, color="mute", valign="BOTTOM")), (462, 660, cell("내용", size=8, color="mute", valign="BOTTOM")),
                (660, 730, cell("금액", size=8, color="mute", align="RIGHT", valign="BOTTOM"))],
           borders=[(0, 359, "bottom", "SOLID", "ink"), (371, 730, "bottom", "SOLID", "ink")])
    left = [(s["name"], s["amount"], False) for s in d["separate"]] + [("합계 (= 1쪽 10)", separate_total(d), True)]
    right = [(dp["date"], dp["desc"], dp["amount"], False) for dp in d["deposits"]]
    right.append(("", "합계 (= 1쪽 이번 정산 금액)", sum(x["amount"] for x in d["deposits"]), True))
    for i in range(max(len(left), len(right))):
        cells, bords, hs = _sep_dep_cells(left, right, i)
        pg.row(max(hs), cells, borders=bords)
    return pg


# ── 1~8 상품별 ────────────────────────────────────────────────
def _prow(pg: Page, label_cell: dict, vals: list, *, h: int, bold=False, bg=None, mute=False, borders=()) -> None:
    cells = [(0, 132, label_cell)]
    for i, (a, b) in enumerate(PCOLS):
        c = amt(vals[i], signed=i not in (0, 8), size=8, bold=bold, bg=bg, color="mute" if (mute and vals[i]) else None)
        c["userEnteredFormat"]["padding"] = dict(NARROW_PAD)
        cells.append((a, b, c))
    pg.row(h, cells, borders=list(borders))


def _product_head(pg: Page, label_cell: dict) -> None:
    hdr = [(0, 132, label_cell)]
    for i, (a, b) in enumerate(PCOLS):
        t = f"{i + 1}\n{SHORT[i + 1]}" if i < 8 else "상품 정산액\n(1 ~ 8)"
        hdr.append((a, b, cell(t, size=7, color="mute", align="RIGHT", valign="BOTTOM", pad=(2, 3, 2, 1))))
    pg.row(36, hdr, borders=[(0, 730, "bottom", "SOLID", "ink")])


def _product_totals(pg: Page, d: dict, L: dict[int, int]) -> None:
    """합계(= 1쪽) + 회색 '정산 예정' 합계 줄(늘 있음 · 값 없으면 공란)."""
    _prow(pg, cell("합계 (= 1쪽)", size=8, bold=True, bg="sum", pad=(2, 4, 2, 4)), [L[i] for i in range(1, 9)] + [d["product_subtotal"]],
          h=26, bold=True, bg="sum", borders=[(0, 730, "top", "SOLID_MEDIUM", "ink")])
    pl = [x["pending"] for x in d["lines"]]
    _prow(pg, cell(PENDING_ROW, size=8, color="mute", bg="sum", pad=(0, 4, 2, 10)), pl + [sum(pl)], h=20, mute=True, bg="sum")


def _products(d: dict, L: dict[int, int]) -> Page:
    pg = Page(keep=2)
    h2(pg, "1 ~ 8 상품별 상세", "회색 줄 = 그중 정산 예정 금액(쿠팡 미확정)")
    _product_head(pg, cell("상품", size=8, color="mute", valign="BOTTOM", pad=(2, 4, 2, 4)))
    line = [(0, 730, "bottom", "SOLID", "line")]
    for p in d["products"]:
        pp = p.get("pending")
        _prow(pg, cell(p["name"], size=8, pad=(2, 4, 2, 4)), [p[f"c{i}"] for i in range(1, 9)] + [p["subtotal"]],
              h=name_h(p["name"], 11.5, per=13), borders=[] if pp else line)
        if pp:
            _prow(pg, cell(PENDING_ROW, size=8, color="mute", pad=(0, 4, 2, 10)), [pp[f"c{i}"] for i in range(1, 9)] + [pp["subtotal"]],
                  h=20, mute=True, borders=line)
    _product_totals(pg, d, L)
    return pg


def _products_moved(d: dict, L: dict[int, int], first_page: int) -> Page:
    """상품 줄이 2쪽에 안 들어갈 때 2쪽 그 자리 = 안내 + 합계 줄(= 1쪽)."""
    pg = Page()
    h2(pg, "1 ~ 8 상품별 상세", f"상품 {len(d['products'])}개 — 상품별 줄은 {first_page}쪽부터 · 아래는 합계(= 1쪽)")
    _product_head(pg, cell("", size=8))
    _product_totals(pg, d, L)
    return pg


# ── 쪽 ────────────────────────────────────────────────────────
def _height(groups: list[Page]) -> int:
    return sum(p.height() for p in groups) + GAP * (len(groups) - 1)


def _pages(groups: list[Page], cont) -> list[Page]:
    """위에서부터 쌓음(GAP) · 넘치면 다음 쪽(D-241 ④ · '(계속)' 머리)."""
    return [_fill(groups, spread=False)] if _height(groups) <= PAGE_H else paginate(groups, cont)


def _foot(issued: str) -> Page:
    pg = Page()
    foot(pg, f"{FOOT} · 발행 {issued}")
    return pg


def detail_pages(d: dict, issued: str) -> list[Page]:
    """2쪽 고정 표 + 상품 줄(2쪽에 다 들어가면 2쪽 · 아니면 전부 그다음 쪽부터)."""
    L = line_amounts(d)
    fixed = [page2_head(d), _p2_kinds_common(d, L), _p2_sep_dep(d)]
    prod = _products(d, L)
    if _height(fixed + [prod, _foot(issued)]) <= PAGE_H:
        return [_fill(fixed + [prod, _foot(issued)], spread=False)]
    p2 = _pages(fixed + [_products_moved(d, L, 3), _foot(issued)], lambda: page2_head(d, "정산 상세 (계속)"))
    if len(p2) > 1:                                  # 11 입금 줄이 많아 2쪽이 넘침 → 상품 시작 쪽 번호 다시
        p2 = _pages([page2_head(d), _p2_kinds_common(d, L), _p2_sep_dep(d), _products_moved(d, L, 2 + len(p2)), _foot(issued)],
                    lambda: page2_head(d, "정산 상세 (계속)"))
    grp = [page2_head(d, "상품별 상세 (1 ~ 8)"), prod, _foot(issued)]
    return p2 + _pages(grp, lambda: page2_head(d, "상품별 상세 (계속)"))


def consignor_sheet(d: dict, issued: str) -> tuple[Page, int]:
    """위탁자 탭 하나 = 1쪽 + 2쪽(+ 상품 쪽) → (위아래 여백 붙인 전체, 쪽 수)."""
    fixed_shape(d)
    pages = paginate(page1_groups(d, issued), lambda: page2_head(d, "쿠팡 판매 정산서 (계속)")) + detail_pages(d, issued)
    return stack_pages(pages), len(pages)
