"""위탁자 정산서(3차 형식 · 구글시트) 내용 — 위탁자 탭(1쪽 요약 + 2쪽 상세)·달 요약 탭을 행 묶음(Page)으로 만든다.

T-38 S3: 샘플 `output\\_샘플_261115_위탁자정산서\\_sheet\\render_gsheet.py` 의 1쪽·2쪽·요약 탭을 옮김(요청 모양 같게).
숫자는 입력 자료 그대로(계산 안 함 · 카드 '쿠팡이 뺀 돈'·요약 합계만 더하기). 문구 = D-238·D-241 ⑦(문의 문구 없음)·
D-242(머리 '자료 기준일 · 정산 예정 포함')·D-251(2쪽 '└ 정산 예정(쿠팡 미확정)')·D-259(1쪽 '쿠팡 미확정 금액 포함')·
D-260(판매 기간·발행 줄 진하게 · '검토용' 표시 없음).
"""
from __future__ import annotations

from coupang_analytics.settlement_consignor_gsheet_layout import (
    CIRC, MARGIN, Page, amt, cards_row, cell, foot, h2, head, name_h, numbered, paginate, place, stack_pages, th_row, won,
)

PENDING_STATUS = "정산 예정 포함"
PENDING_ROW = "└ 정산 예정(쿠팡 미확정)"                  # D-251
PENDING_CARD = "쿠팡 미확정 금액 포함"                     # D-259
DESC = {
    1: "고객 결제 금액 (취소·반품 뺀 금액)", 2: "우리가 걸어 둔 할인", 3: "상품 분류별 수수료 (부가세 포함)",
    4: "쿠팡이 대신 내 준 할인 → 우리 몫", 5: "이 상품들에 쓴 쿠팡 광고", 6: "쿠팡 창고 보관·입출고·배송·반품",
    7: "쿠팡 창고로 보낸 운송", 8: "쿠팡 창고에서 잃어버린 재고 → 쿠팡이 줌",
}
NAME = {1: "판매 금액", 2: "판매자 할인쿠폰", 3: "쿠팡 판매수수료", 4: "쿠팡 부담 할인", 5: "광고비",
        6: "창고·배송비 (로켓그로스)", 7: "창고 입고 운송비 (밀크런)", 8: "재고 분실·파손 보상"}
SHORT = {1: "판매 금액", 2: "할인쿠폰", 3: "판매수수료", 4: "쿠팡 부담 할인", 5: "광고비", 6: "창고·배송비",
         7: "입고 운송비", 8: "재고 보상"}
PCOLS = [(132, 198), (198, 264), (264, 330), (330, 396), (396, 462), (462, 528), (528, 594), (594, 660), (660, 730)]
SCOLS = [(0, 132, "위탁자 · 쿠팡 계정", "LEFT"), (132, 237, "판매 금액\n(1)", "RIGHT"),
         (237, 330, "쿠팡이\n뺀 돈", "RIGHT"), (330, 396, "계정 공통\n비용 (9)", "RIGHT"), (396, 462, "별도 입금\n(10)", "RIGHT"),
         (462, 528, "이번 정산\n금액", "RIGHT"), (528, 594, "입금 완료", "RIGHT"), (594, 660, "입금 예정", "RIGHT"), (660, 730, "정산서", "RIGHT")]
SUMMARY_SIGNED = [False, True, True, True, False, False, False]
NARROW_PAD = {"top": 2, "right": 4, "bottom": 2, "left": 2}


def pending(d: dict) -> bool:
    return d.get("status") == PENDING_STATUS


def line_amounts(d: dict) -> dict[int, int]:
    return {x["no"]: x["amount"] for x in d["lines"]}


def separate_total(d: dict) -> int:
    return sum(x["amount"] for x in d["separate"])


def coupang_took(d: dict) -> int:
    """카드·요약 '쿠팡이 뺀 돈' = 상품 정산액 + 9 계정 공통 − 1 판매 금액."""
    return d["product_subtotal"] + d["common"]["total_applied"] - line_amounts(d)[1]


def who_line(d: dict, issued: str) -> str:
    return (f"{d['company']} (대표 {d['ceo']}) · 쿠팡 계정 {d['account']}\n"
            f"판매 기간 {d['period_start']} ~ {d['period_end']} · 발행 {issued}\n"
            f"자료 기준일 {d['basis_date']} · " + (PENDING_STATUS if pending(d) else "확정"))


def sep_label(d: dict) -> str:
    return " · ".join(dict.fromkeys(x["name"].split(" (")[0].split(" — ")[0].split(" 중 ")[0] for x in d["separate"])) or "없음"


# ── 1쪽 ───────────────────────────────────────────────────────
def _p1_cards(d: dict, L: dict[int, int]) -> Page:
    pg = Page()
    sep_total = separate_total(d)
    took = coupang_took(d)
    main_runs = [("이번 정산 금액\n", 9, False, "mainK"), (f"{d['settle_amount']:,}원", 21, True, "white")]
    if sep_total:
        main_runs.append((f"\n별도 입금 {sep_total:,}원 포함", 9, False, "mainK"))
    if d.get("pending_total"):
        main_runs.append((f"\n{PENDING_CARD}\n{d['pending_total']:,}원 (바뀔 수 있음)", 9, True, "white"))
    cards_row(pg, [("고객이 결제한 금액\n", 9, False, "mute"), (f"{L[1]:,}원", 15, True, "ink")],
              [("쿠팡이 뺀 돈 (수수료·비용)\n", 9, False, "mute"), (won(took), 15, True, "red" if took < 0 else "ink")],
              main_runs, tall=bool(d.get("pending_total")))
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
    has_sep = bool(d["separate"])
    pg.row(26, [(0, 264, numbered(10, f"별도 입금 ({sep_label(d)})" if has_sep else "별도 입금")),
                (264, 594, cell("쿠팡페이가 대표 계좌로 직접 보냄" if has_sep else "이번 기간 없음", size=8, color="mute")),
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
    h2(pg, "정산 금액은 어디로 갔나요", f"통장과 맞춰 보실 때 · 아래 합 = {d['settle_amount']:,} · 날짜별 상세는 2쪽 11번")
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


# ── 2쪽 ───────────────────────────────────────────────────────
def _prow(pg: Page, label_cell: dict, vals: list, *, h: int, bold=False, bg=None, mute=False, borders=()) -> None:
    cells = [(0, 132, label_cell)]
    for i, (a, b) in enumerate(PCOLS):
        c = amt(vals[i], signed=i not in (0, 8), size=8, bold=bold, bg=bg, color="mute" if mute else None)
        c["userEnteredFormat"]["padding"] = dict(NARROW_PAD)
        cells.append((a, b, c))
    pg.row(h, cells, borders=list(borders))


def page2_head(d: dict, title: str = "정산 상세") -> Page:
    pg = Page()
    head(pg, title, "1쪽 번호와 같은 번호 · 합계 줄 = 1쪽 금액" + (" · 회색 줄 = 그중 정산 예정 금액(쿠팡 미확정 · 바뀔 수 있음)" if pending(d) else ""),
         f"{d['company']} · {d['account']} · {d['period_start'][:7]}" + (f" · {PENDING_STATUS}" if pending(d) else ""))
    return pg


def _p2_products(d: dict, L: dict[int, int]) -> Page:
    pg = Page(keep=2)
    h2(pg, "1 ~ 8 상품별 상세", "회색 줄 = 그중 정산 예정 금액(쿠팡 미확정)" if pending(d) else "")
    hdr = [(0, 132, cell("상품", size=8, color="mute", valign="BOTTOM", pad=(2, 4, 2, 4)))]
    for i, (a, b) in enumerate(PCOLS):
        t = f"{i + 1}\n{SHORT[i + 1]}" if i < 8 else "상품 정산액\n(1 ~ 8)"
        hdr.append((a, b, cell(t, size=7, color="mute", align="RIGHT", valign="BOTTOM", pad=(2, 3, 2, 1))))
    pg.row(36, hdr, borders=[(0, 730, "bottom", "SOLID", "ink")])
    line = [(0, 730, "bottom", "SOLID", "line")]
    for p in d["products"]:
        vals = [p[f"c{i}"] for i in range(1, 9)] + [p["subtotal"]]
        pp = p.get("pending")
        _prow(pg, cell(p["name"], size=8, pad=(2, 4, 2, 4)), vals, h=name_h(p["name"], 11.5, per=13),
              borders=[] if pp else line)
        if pp:
            _prow(pg, cell(PENDING_ROW, size=8, color="mute", pad=(0, 4, 2, 10)), [pp[f"c{i}"] for i in range(1, 9)] + [pp["subtotal"]],
                  h=20, mute=True, borders=line)
    tot = [L[i] for i in range(1, 9)] + [d["product_subtotal"]]
    _prow(pg, cell("합계 (= 1쪽)", size=8, bold=True, bg="sum", pad=(2, 4, 2, 4)), tot, h=26, bold=True, bg="sum",
          borders=[(0, 730, "top", "SOLID_MEDIUM", "ink")])
    pl = [x["pending"] for x in d["lines"]]
    if any(pl):
        _prow(pg, cell(PENDING_ROW, size=8, color="mute", bg="sum", pad=(0, 4, 2, 10)), pl + [sum(pl)], h=20, mute=True, bg="sum")
    return pg


def _side_cells(rows: list[tuple], i: int, xs: tuple[int, int, int]) -> tuple[list, list]:
    """좌우 두 표 중 한쪽의 i 번째 줄 칸·테두리(마지막 줄 = 합계)."""
    x0, xm, x1 = xs
    nm, v, pend = rows[i]
    is_sum = i == len(rows) - 1
    bg = "sum" if is_sum else None
    cells = [(x0, xm, cell(nm, bold=is_sum, bg=bg, color="mute" if pend else "ink")),
             (xm, x1, amt(v, bold=is_sum, bg=bg, color="mute" if pend else None))]
    bord = (x0, x1, "top", "SOLID_MEDIUM", "ink") if is_sum else (x0, x1, "bottom", "SOLID", "line")
    return cells, [bord]


def _p2_kinds_separate(d: dict, L: dict[int, int]) -> Page:
    """6 종류별(왼쪽) · 10 별도 입금(오른쪽) — 가운데 틈 359~371."""
    pg = Page(keep=2)
    pg.row(26, [(0, 359, cell(runs=[("6 창고·배송비 종류별", 11, True, "p")], valign="BOTTOM", pad=(0, 0, 3, 0))),
                (371, 730, cell(runs=[("10 별도 입금", 11, True, "p")], valign="BOTTOM", pad=(0, 0, 3, 0)))])
    pg.row(22, [(0, 264, cell("종류", size=8, color="mute", valign="BOTTOM")), (264, 359, cell("금액", size=8, color="mute", align="RIGHT", valign="BOTTOM")),
                (371, 594, cell("내용", size=8, color="mute", valign="BOTTOM")), (594, 730, cell("금액", size=8, color="mute", align="RIGHT", valign="BOTTOM"))],
           borders=[(0, 359, "bottom", "SOLID", "ink"), (371, 730, "bottom", "SOLID", "ink")])
    left = [(k["name"], k["amount"], bool(k.get("pending"))) for k in d["rg_kinds"]] or [("이번 기간 없음", 0, False)]
    right = [(s["name"], s["amount"], False) for s in d["separate"]] or [("이번 기간 없음", 0, False)]
    left.append(("합계 (= 1쪽 6)", L[6], False))
    right.append(("합계 (= 1쪽 10)", separate_total(d), False))
    for i in range(max(len(left), len(right))):
        cells, bords = [], []
        for rows, xs in ((left, (0, 264, 359)), (right, (371, 594, 730))):
            if i < len(rows):
                c, b = _side_cells(rows, i, xs)
                cells += c
                bords += b
        hs = [name_h(rows[i][0], 15, base=26, per=16) for rows in (left, right) if i < len(rows)]
        pg.row(max(hs), cells, borders=bords)
    return pg


def _p2_common(d: dict) -> Page:
    cm = d["common"]
    pg = Page(keep=2)
    h2(pg, "9 계정 공통 비용", "쿠팡이 상품별 금액 없이 계정 전체로만 청구한 비용")
    th_row(pg, [(0, 396, "항목", "LEFT"), (396, 594, "쿠팡 청구 금액 (계정 전체)", "RIGHT"), (594, 730, "이 정산서 반영", "RIGHT")])
    for it in cm["items"] or [{"name": "이번 기간 없음", "coupang_amount": 0, "applied_amount": 0}]:
        nm = it["name"] + (" · 정산 예정(쿠팡 미확정 · 바뀔 수 있음)" if it.get("pending") else "")
        pg.row(name_h(nm, 28, base=26, per=17), [(0, 396, cell(nm, bg="amber2")), (396, 594, amt(it["coupang_amount"], signed=False, bg="amber2")),
                                                 (594, 730, amt(it["applied_amount"], bg="amber2"))], borders=[(0, 730, "bottom", "SOLID", "line")])
    pg.row(28, [(0, 396, cell("합계 (= 1쪽 9)", bold=True, bg="sum")),
                (396, 594, amt(cm["total_coupang"], signed=False, bold=True, bg="sum")),
                (594, 730, amt(cm["total_applied"], bold=True, bg="sum"))], borders=[(0, 730, "top", "SOLID_MEDIUM", "ink")])
    return pg


def _p2_deposits(d: dict) -> Page:
    pg = Page(keep=2)
    h2(pg, "11 정산 금액 입금 내역", "1쪽 '어디로 갔나요'의 날짜별 상세")
    th_row(pg, [(0, 132, "날짜", "LEFT"), (132, 594, "내용", "LEFT"), (594, 730, "금액", "RIGHT")])
    for dp in d["deposits"]:
        pg.row(name_h(dp["desc"], 38, base=26, per=17), [(0, 132, cell(dp["date"])), (132, 594, cell(dp["desc"])), (594, 730, amt(dp["amount"], signed=False))],
               borders=[(0, 730, "bottom", "SOLID", "line")])
    pg.row(28, [(0, 594, cell("합계 (= 1쪽 이번 정산 금액)", bold=True, bg="sum")),
                (594, 730, amt(sum(x["amount"] for x in d["deposits"]), signed=False, bold=True, bg="sum"))],
           borders=[(0, 730, "top", "SOLID_MEDIUM", "ink")])
    return pg


def page2_groups(d: dict, issued: str) -> list[Page]:
    """2쪽 묶음: 머리 · 1~8 상품별 · 6 종류별/10 별도 입금 · 9 계정 공통 · 11 입금 내역 · 바닥 줄."""
    L = line_amounts(d)
    bottom = Page()
    foot(bottom, f"쿠팡이 주는 정산 항목은 모두 확인했고, 금액이 생긴 항목만 표시했습니다 · 쿠팡 원본과 원 단위 대조 완료 · 발행 {issued}")
    return [page2_head(d), _p2_products(d, L), _p2_kinds_separate(d, L), _p2_common(d), _p2_deposits(d), bottom]


def consignor_sheet(d: dict, issued: str) -> tuple[Page, int]:
    """위탁자 탭 하나 = 1쪽 + 2쪽(넘치면 다음 쪽 D-241 ④) → (위아래 여백 붙인 전체, 쪽 수)."""
    pages = (paginate(page1_groups(d, issued), lambda: page2_head(d, "쿠팡 판매 정산서 (계속)"))
             + paginate(page2_groups(d, issued), lambda: page2_head(d, "정산 상세 (계속)")))
    return stack_pages(pages), len(pages)


# ── 요약 탭 ───────────────────────────────────────────────────
def flow_sum(d: dict, word: str) -> int:
    return sum(f["amount"] for f in d["flow"] if word in f["name"])


def _summary_head(ds: list[dict], issued: str) -> Page:
    period = sorted({f"{d['period_start']} ~ {d['period_end']}" for d in ds})
    basis = sorted({d["basis_date"] for d in ds})
    pg = Page()
    head(pg, "위탁자 정산 요약", "위탁자별 정산서는 이 달 요약 다음 탭들 · 모든 금액은 쿠팡이 준 정산 자료 기준(원 단위)",
         f"판매 기간 {' / '.join(period)}\n위탁자 {len(ds)}명 · 발행 {issued}\n자료 기준일 {' / '.join(basis)} · "
         + (PENDING_STATUS if any(pending(d) for d in ds) else "확정"))
    return pg


def _summary_cards(ds: list[dict], tot_pend: int) -> Page:
    tot_sale = sum(line_amounts(d)[1] for d in ds)
    tot_settle = sum(d["settle_amount"] for d in ds)
    main_runs = [("이번 정산 금액 (합계)\n", 9, False, "mainK"), (f"{tot_settle:,}원", 21, True, "white")]
    if tot_pend:
        main_runs.append((f"\n{PENDING_CARD}\n{tot_pend:,}원 (바뀔 수 있음)", 9, True, "white"))
    pg = Page()
    cards_row(pg, [("위탁자\n", 9, False, "mute"), (f"{len(ds)}명", 15, True, "ink")],
              [("고객이 결제한 금액 (합계)\n", 9, False, "mute"), (f"{tot_sale:,}원", 15, True, "ink")],
              main_runs, tall=bool(tot_pend))
    return pg


def summary_values(d: dict) -> list[int]:
    """요약 표 한 줄 숫자 = 판매 금액 · 쿠팡이 뺀 돈 · 9 · 10 · 이번 정산 금액 · 입금 완료 · 입금 예정."""
    return [line_amounts(d)[1], coupang_took(d), d["common"]["total_applied"], separate_total(d), d["settle_amount"],
            flow_sum(d, "완료"), flow_sum(d, "예정")]


def _summary_num_cells(vals: list[int], *, total: bool) -> list[tuple]:
    out = []
    for (a, b, _, _), v, sg in zip(SCOLS[1:8], vals, SUMMARY_SIGNED):
        c = amt(v, signed=sg, size=9, bold=True if total else (a == 462), bg="sum" if total else None)
        c["userEnteredFormat"]["padding"] = dict(NARROW_PAD)
        out.append((a, b, c))
    return out


def _summary_table(ds: list[dict], gids: list[int]) -> Page:
    pg = Page()
    h2(pg, "위탁자별 정산 금액", "이름을 누르면 그 위탁자 정산서로 이동")
    pg.row(36, [(a, b, cell(t, size=8, color="mute", align=al, valign="BOTTOM", pad=(2, 4, 2, 4))) for a, b, t, al in SCOLS],
           borders=[(0, 730, "bottom", "SOLID", "ink")])
    sums = [0] * 7
    for d, gid in zip(ds, gids):
        vals = summary_values(d)
        sums = [a + b for a, b in zip(sums, vals)]
        cells = [(0, 132, cell(runs=[(f"{d['company']}\n", 9, False, "ink"), (f"{d['ceo']} · {d['account']}", 8, False, "mute")], pad=(2, 4, 2, 4)))]
        cells += _summary_num_cells(vals, total=False)
        cells.append((660, 730, cell(f'=HYPERLINK("#gid={gid}","보기 →")', size=9, color="p", align="RIGHT", pad=(2, 4, 2, 4))))
        pg.row(40, cells, borders=[(0, 730, "bottom", "SOLID", "line")])
    cells = [(0, 132, cell("합계", bold=True, bg="sum", pad=(2, 4, 2, 4)))] + _summary_num_cells(sums, total=True)
    cells.append((660, 730, cell(None, bg="sum")))
    pg.row(30, cells, borders=[(0, 730, "top", "SOLID_MEDIUM", "ink")])
    return pg


def _summary_tips(ds: list[dict], tot_pend: int) -> Page:
    pg = Page()
    h2(pg, "읽는 법")
    tips = ["· 판매 금액 − 쿠팡이 뺀 돈 + 별도 입금 = 이번 정산 금액",
            "· 쿠팡이 뺀 돈 = 할인쿠폰·판매수수료·광고비·창고·배송비 등 − 쿠팡 부담 할인·재고 보상 + 계정 공통 비용",
            "· 입금 완료 + 입금 예정 외의 차이 = 빠른정산으로 먼저 받은 돈·쿠팡 대출 상환 등(각 정산서 1쪽 '어디로 갔나요')"]
    if tot_pend:
        tips.append("· 정산 예정 포함: 쿠팡 상품별 정산 파일이 아직 없는 판매 기간은 쿠팡 정산 예정 금액을 넣음 — 정산 예정 금액(쿠팡 미확정): "
                    + " · ".join(f"{d['ceo']} {d.get('pending_total') or 0:,}" for d in ds) + " (쿠팡 확정 때 바뀔 수 있음)")
    for t in tips:
        pg.row(name_h(t, 70, base=22, per=14), [(0, 730, cell(t, size=9, color="mute"))])
    return pg


def summary_sheet(ds: list[dict], gids: list[int], issued: str) -> Page:
    """달 요약 탭(구글시트에만 · PDF 발송 안 함 D-260) — 줄 수가 적어 늘리지 않음(위에서부터 · 틈 24)."""
    tot_pend = sum(d.get("pending_total") or 0 for d in ds)
    bottom = Page()
    foot(bottom, "검산: 위탁자마다 1쪽 금액 = 2쪽 상세 합계 · 입금 내역 합계 = 이번 정산 금액 (원 단위 일치 확인 후 발행)")
    groups = [_summary_head(ds, issued), _summary_cards(ds, tot_pend), _summary_table(ds, gids), _summary_tips(ds, tot_pend), bottom]
    out = Page()
    out.spacer(MARGIN)
    for i, p in enumerate(groups):
        if i:
            out.spacer(24)
        place(out, p)
    out.spacer(MARGIN)
    return out
