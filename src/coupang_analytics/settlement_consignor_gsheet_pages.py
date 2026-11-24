"""위탁자 정산서(3차 형식 · 구글시트) 공용 이름·금액 도우미 + 달 요약 탭(행 묶음 Page).
위탁자 탭(1쪽 + 2쪽 · 고정 형식 D-343) = `settlement_consignor_gsheet_fixed`. 달 '{n}월 근거' 탭(내부용 · PDF 안 냄 · D-401 ②) = `evidence_sheet`.

T-38 S3: 샘플 `output\\_샘플_261115_위탁자정산서\\_sheet\\render_gsheet.py` 의 1쪽·2쪽·요약 탭을 옮김(요청 모양 같게).
숫자는 입력 자료 그대로(계산 안 함 · 카드 '쿠팡이 뺀 돈'·요약 합계만 더하기). 문구 = D-238·D-241 ⑦(문의 문구 없음)·
D-242(머리 '자료 기준일 · 정산 예정 포함')·D-251(2쪽 '└ 정산 예정(쿠팡 미확정)')·D-259(1쪽 '쿠팡 미확정 금액 포함')·
D-260(판매 기간·발행 줄 진하게 · '검토용' 표시 없음).
"""
from __future__ import annotations

import json

from coupang_analytics.settlement_consignor_gsheet_layout import MARGIN, Page, amt, cards_row, cell, foot, h2, head, name_h, place, text_lines

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


# ── '{n}월 근거' 탭(D-401 ② · 내부용 · PDF 안 냄) ─────────────────────
EVIDENCE_SUB = "내부용 — 위탁자에게 보내지 않음(PDF 안 냄 · D-401 ②) · 판단 문장·계정 공통 나누기·정산 예정 원천·근거 전부"
CHUNK = 3000                     # 칸 하나 글자 수(긴 근거는 여러 행으로 나눔)


def _js(v) -> str:
    return json.dumps(v, ensure_ascii=False, default=str, separators=(", ", ": "))


def _text_rows(pg: Page, text: str, x0: int = 11, size: int = 8, color: str = "ink") -> None:
    for i in range(0, max(len(text), 1), CHUNK):
        part = text[i:i + CHUNK]
        pg.row(8 + 13 * text_lines(part, 60), [(x0, 730, cell(part, size=size, color=color, valign="TOP", pad=(2, 4, 2, 4)))])


def _section(pg: Page, title: str, items: list[str]) -> None:
    pg.row(22, [(0, 730, cell(title, size=9, bold=True, color="p", valign="BOTTOM", pad=(0, 0, 2, 0)))],
           borders=[(0, 730, "bottom", "SOLID", "line")])
    for t in items or ["(없음)"]:
        _text_rows(pg, t, color="ink" if items else "mute")


def common_lines(d: dict) -> list[str]:
    """9 계정 공통 = 쿠팡 원문 항목 → 관리 몫(비중) · 비고(예: 74 남은 청구) — 금액 있는 줄만."""
    cm = d["common"]
    out = [f"적용 비중: {cm['basis_text']}"]
    for it in cm["items"]:
        if it["coupang_amount"] or it["applied_amount"] or it.get("note"):
            parts = " · ".join(f"{x['name']} {x['coupang_amount']:,} → {x['applied_amount']:,}" for x in it.get("parts") or [])
            out.append(f"{it['name']}: 쿠팡 청구 {it['coupang_amount']:,} → 반영 {it['applied_amount']:,}" + (f" (원문 {parts})" if parts else "")
                       + (f" · 비고 {it['note']}" if it.get("note") else ""))
    return out


def _evidence_block(d: dict) -> Page:
    pg = Page()
    h2(pg, f"{d['company']} · {d['ceo']} · {d['account']}", f"상태 {d['status']} · 이번 정산 금액 {d['settle_amount']:,}원")
    _section(pg, "판단", [f"{i}. {t}" for i, t in enumerate(d["judgments"], start=1)])
    _section(pg, "9 계정 공통 — 쿠팡 원문 항목·관리 몫 나누기", common_lines(d))
    _section(pg, "정산 예정 원천 (pending_detail)", [_js(x) for x in d["pending_detail"]])
    _section(pg, "근거 (_근거)", [f"{k}: {_js(v)}" for k, v in d["_근거"].items()])
    _section(pg, "위탁자 탭 '비고'에 넣은 문장", list(d["remarks"]))
    return pg


def evidence_sheet(ds: list[dict], issued: str) -> Page:
    """달 '{n}월 근거' 탭 — 그 달 위탁자마다 판단·근거(위탁자 탭 '비고'에 안 넣는 내부 문장 전부) · 쪽 나누기 없음(PDF 안 냄)."""
    period = sorted({f"{d['period_start']} ~ {d['period_end']}" for d in ds})
    top = Page()
    head(top, f"{int(ds[0]['period_start'][5:7])}월 근거", EVIDENCE_SUB, f"판매 기간 {' / '.join(period)}\n위탁자 {len(ds)}명 · 발행 {issued}")
    out = Page()
    out.spacer(MARGIN)
    for i, p in enumerate([top] + [_evidence_block(d) for d in ds]):
        if i:
            out.spacer(24)
        place(out, p)
    out.spacer(MARGIN)
    return out
