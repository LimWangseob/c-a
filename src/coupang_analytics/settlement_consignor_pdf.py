"""위탁자별 정산서 PDF 묶기(D-260 · 소유자 11-16 "PDF로 위탁자별 파일 다시 내보내줘").

위탁자 1명 = PDF 1개: 판매 달 순서로 그 위탁자 탭을 이어 붙임 · 판매 달이 여러 개면 첫 장 = 그 위탁자 한 명의 월별 요약.
여러 위탁자를 모은 '{n}월 요약' 탭·'{n}월 근거' 탭(D-401 ②)·'변경 기록' 탭은 넣지 않는다(위탁자 탭만 = `StatementPlan.pdf_gids` 와 같은 원칙).
월별 요약 = 샘플 `output\\_정산서_261116_안재영\\_sheet\\render_gsheet.py` person_summary_sheet 를 옮김(숫자 = 달 자료 그대로 합산만).
달마다 시트 파일 1개(D-241 ⑥)라 월별 요약은 마지막 판매 달 파일에 임시 탭으로 그려 내보낸 뒤 지운다(파일 탭 구성 = D-242 ③ 그대로).
내보낸 탭이 자료와 같은 달·같은 금액인지, 위탁자에게 안 보낼 글자가 없는지 PDF 글자로 확인 — 하나라도 어긋나면 파일을 만들지 않는다.
발송은 하지 않는다(D-399).
"""
from __future__ import annotations

import json
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

from coupang_analytics import settlement_consignor_gsheet as GS
from coupang_analytics.settlement_consignor_gsheet_layout import (
    MARGIN, PAGE_H, Page, amt, cards_row, cell, foot, h2, head, name_h, place, requests_for)
from coupang_analytics.settlement_consignor_gsheet_pages import (
    NARROW_PAD, PENDING_CARD, _summary_status, line_amounts, shown_status, summary_values)

SUMMARY_GID = 990001             # 월별 요약 임시 탭(내보낸 뒤 지움)
FORBIDDEN = ("검토용", "아직 반영 안 된", "반영 전 내역", "확인 필요", "내부용")     # D-260 ② · D-401 · D-402
MCOLS = [(0, 132, "판매 달", "LEFT"), (132, 237, "판매 금액\n(1)", "RIGHT"), (237, 330, "쿠팡이\n뺀 돈", "RIGHT"),
         (330, 396, "계정 공통\n비용 (9)", "RIGHT"), (396, 462, "별도 입금\n(10)", "RIGHT"), (462, 528, "이번 정산\n금액", "RIGHT"),
         (528, 594, "쿠팡 미확정\n금액", "RIGHT"), (594, 660, "입금 완료", "RIGHT"), (660, 730, "입금 예정", "RIGHT")]
MSIGNED = [False, True, True, True, False, False, False, False]


class ConsignorPdfError(ValueError):
    """그 위탁자 PDF 를 만들지 않음(사유)."""


# ── 첫 장 월별 요약 ────────────────────────────────────────────
def summary_title(d: dict) -> str:
    return f"월별 요약 {d['ceo']} ({d['account']})"


def _month(d: dict) -> str:
    return d["period_start"][:7]


def _pend(d: dict) -> int:
    return d.get("pending_total") or 0


def ordered(ds: list[dict]) -> list[dict]:
    """판매 달 순서 — 한 위탁자 계정 · 달마다 자료 1개가 아니면 중단."""
    out = sorted(ds, key=_month)
    if len({d["account"] for d in out}) != 1:
        raise ConsignorPdfError(f"한 위탁자 자료가 아님 {sorted({d['account'] for d in out})}")
    if len({_month(d) for d in out}) != len(out):
        raise ConsignorPdfError(f"{out[0]['account']}: 같은 판매 달 자료가 둘 이상 {[_month(d) for d in out]}")
    return out


def _cards(ds: list[dict]) -> Page:
    tot_pend = sum(_pend(d) for d in ds)
    main = [("이번 정산 금액 (합계)\n", 9, False, "mainK"), (f"{sum(d['settle_amount'] for d in ds):,}원", 21, True, "white")]
    if tot_pend:
        main.append((f"\n{PENDING_CARD}\n{tot_pend:,}원 (바뀔 수 있음)", 9, True, "white"))
    pg = Page()
    cards_row(pg, [("판매 달\n", 9, False, "mute"), (f"{len(ds)}개월", 15, True, "ink")],
              [("고객이 결제한 금액 (합계)\n", 9, False, "mute"), (f"{sum(line_amounts(d)[1] for d in ds):,}원", 15, True, "ink")],
              main, tall=bool(tot_pend))
    return pg


def _values(d: dict) -> list[int]:
    """판매 금액 · 쿠팡이 뺀 돈 · 9 · 10 · 이번 정산 금액 · 쿠팡 미확정 금액 · 입금 완료 · 입금 예정."""
    v = summary_values(d)
    return [*v[:5], _pend(d), *v[5:]]


def _row_cells(vals: list[int], *, total: bool) -> list[tuple]:
    out = []
    for (a, b, _t, _al), v, sg in zip(MCOLS[1:], vals, MSIGNED):
        c = amt(v, signed=sg, size=9, bold=total or a == 462, bg="sum" if total else None)
        c["userEnteredFormat"]["padding"] = dict(NARROW_PAD)
        out.append((a, b, c))
    return out


def _table(ds: list[dict]) -> Page:
    pg = Page()
    h2(pg, "판매 달별 정산 금액", "달마다 자세한 내용은 다음 장부터")
    pg.row(36, [(a, b, cell(t, size=8, color="mute", align=al, valign="BOTTOM", pad=(2, 4, 2, 4))) for a, b, t, al in MCOLS],
           borders=[(0, 730, "bottom", "SOLID", "ink")])
    sums = [0] * 8
    for d in ds:
        vals = _values(d)
        sums = [x + y for x, y in zip(sums, vals)]
        sub = f"{d['period_start'][5:].replace('-', '.')}~{d['period_end'][5:].replace('-', '.')} · {shown_status(d)}"
        label = cell(runs=[(f"{GS.month_label(d)}\n", 10, True, "ink"), (sub, 7, False, "mute")], pad=(2, 4, 2, 4))
        pg.row(40, [(0, 132, label), *_row_cells(vals, total=False)], borders=[(0, 730, "bottom", "SOLID", "line")])
    pg.row(30, [(0, 132, cell("합계", bold=True, bg="sum", pad=(2, 4, 2, 4))), *_row_cells(sums, total=True)],
           borders=[(0, 730, "top", "SOLID_MEDIUM", "ink")])
    return pg


def _tips(ds: list[dict]) -> Page:
    pg = Page()
    h2(pg, "읽는 법")
    tips = ["· 판매 금액 − 쿠팡이 뺀 돈 + 별도 입금 = 이번 정산 금액",
            "· 쿠팡이 뺀 돈 = 할인쿠폰·판매수수료·광고비·창고·배송비 등 − 쿠팡 부담 할인·재고 보상 + 계정 공통 비용",
            "· 입금 완료 + 입금 예정 외의 차이 = 빠른정산으로 먼저 받은 돈·쿠팡 대출 상환 등(달별 정산서 1쪽 '어디로 갔나요')"]
    if any(_pend(d) for d in ds):
        tips.append("· 쿠팡 미확정 금액: 쿠팡 상품별 정산 파일이 아직 없는 판매 기간의 금액입니다 — 이번 정산 금액에 포함되어 있고, 쿠팡이 확정하면 바뀔 수 있습니다")
    for t in tips:
        pg.row(name_h(t, 70, base=22, per=14), [(0, 730, cell(t, size=9, color="mute"))])
    return pg


def month_summary_sheet(ds: list[dict], issued: str) -> Page:
    """한 위탁자의 판매 달별 요약 한 쪽(여러 달일 때만 · D-260 ②)."""
    ds = ordered(ds)
    d0 = ds[0]
    if len(ds) < 2:
        raise ConsignorPdfError(f"{d0['account']}: 판매 달이 하나면 월별 요약 첫 장 없음(D-260 ②)")
    basis = sorted({d["basis_date"] for d in ds})
    top, bottom = Page(), Page()
    head(top, "쿠팡 판매 정산서 — 월별 요약", "판매 달마다 정산서가 다음 장부터 이어집니다 · 모든 금액은 쿠팡이 준 정산 자료 기준(원 단위)",
         f"{d0['company']} (대표 {d0['ceo']}) · 쿠팡 계정 {d0['account']}\n"
         f"판매 기간 {d0['period_start']} ~ {ds[-1]['period_end']} · 발행 {issued}\n자료 기준일 {' / '.join(basis)} · {_summary_status(ds)}")
    foot(bottom, "검산: 달별 금액 = 각 달 정산서 1쪽 금액 · 합계 = 달별 금액의 합 (원 단위 일치 확인 후 발행)")
    out = Page()
    out.spacer(MARGIN)
    for i, p in enumerate([top, _cards(ds), _table(ds), _tips(ds), bottom]):
        if i:
            out.spacer(24)
        place(out, p)
    out.spacer(MARGIN)
    if out.height() > PAGE_H + 2 * MARGIN:
        raise ConsignorPdfError(f"{d0['account']}: 월별 요약이 한 쪽을 넘음({len(ds)}개월)")
    return out


# ── 내보내기 · 글자 확인 · 묶기 ──────────────────────────────────
def _titles(client) -> dict:
    return {s["properties"]["title"]: s["properties"]["sheetId"] for s in client.meta(refresh=True)["sheets"]}


def _text(body: bytes) -> str:
    from pypdf import PdfReader
    return "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(body)).pages)


def _need(body: bytes, wants: list[str], what: str) -> bytes:
    text = _text(body)
    miss = [w for w in wants if w not in text]
    bad = [w for w in FORBIDDEN if w in text]
    if miss:
        raise ConsignorPdfError(f"{what}: 시트 탭이 자료와 다름 — PDF 에 {miss} 없음(시트를 다시 그린 뒤 내보낼 것)")
    if bad:
        raise ConsignorPdfError(f"{what}: 위탁자에게 안 보낼 글자 {bad} 있음")
    return body


def _month_tab(session, client, d: dict) -> bytes:
    what = f"{d['account']} {_month(d)}"
    gid = _titles(client).get(GS.tab_title(d))
    if gid is None:
        raise ConsignorPdfError(f"{what}: 시트에 '{GS.tab_title(d)}' 탭 없음")
    body = GS.export_tab_bytes(session, client.spreadsheet_id, gid)
    return _need(body, [f"판매 기간 {d['period_start']} ~ {d['period_end']}", f"{d['settle_amount']:,}원"], what)


def _summary_tab(session, client, ds: list[dict], issued: str) -> bytes:
    """월별 요약 임시 탭 → 내보내기 → 지움(실패해도 지움 · 앞 실행이 끊겨 남은 같은 탭은 먼저 지움)."""
    page, title = month_summary_sheet(ds, issued), summary_title(ds[0])
    drop = [{"deleteSheet": {"sheetId": SUMMARY_GID}}]
    stale = drop if SUMMARY_GID in _titles(client).values() else []
    client.batch_update([*stale, {"addSheet": {"properties": {"sheetId": SUMMARY_GID, "title": title}}}])
    try:
        client.batch_update(requests_for(page, SUMMARY_GID))
        body = GS.export_tab_bytes(session, client.spreadsheet_id, SUMMARY_GID)
    finally:
        client.batch_update(drop)
    return _need(body, ["월별 요약", f"{sum(d['settle_amount'] for d in ds):,}원"], f"{ds[0]['account']} 월별 요약")


def pdf_name(ds: list[dict]) -> str:
    """예 '위탁자정산서_안재영_sg0141n_8~11월.pdf'(샘플 이름 · 해가 바뀌면 'YYYY-MM~YYYY-MM')."""
    a, b = _month(ds[0]), _month(ds[-1])
    span = GS.month_label(ds[0]) if a == b else f"{int(a[5:])}~{int(b[5:])}월" if a[:4] == b[:4] else f"{a}~{b}"
    return f"위탁자정산서_{ds[0]['ceo']}_{ds[0]['account']}_{span}.pdf"


def _bodies(session, clients: dict, ds: list[dict], issued: str) -> list[bytes]:
    months = [_month_tab(session, clients[_month(d)], d) for d in ds]
    if len(ds) == 1:
        return months
    return [_summary_tab(session, clients[_month(ds[-1])], ds, issued), *months]


def consignor_pdf(session, clients: dict, ds: list[dict], issued: str, out_dir: Path) -> Path:
    """한 위탁자 PDF 1개 저장. clients = {판매 달: 그 달 시트 클라이언트(GSheetClient 모양 · spreadsheet_id)} ·
    session = 인증된 HTTP 세션. 어긋남 = ConsignorPdfError(파일 안 만듦)."""
    from pypdf import PdfReader, PdfWriter
    ds = ordered(ds)
    who = ds[0]["account"]
    errs = GS.check_all(ds)
    if errs:
        raise ConsignorPdfError(f"{who}: 검산 실패 {' / '.join(errs)}")
    lack = [_month(d) for d in ds if _month(d) not in clients]
    if lack:
        raise ConsignorPdfError(f"{who}: 그 달 시트 없음 {lack}")
    try:
        bodies = _bodies(session, clients, ds, issued)
    except RuntimeError as exc:
        raise ConsignorPdfError(f"{who}: {exc}") from exc
    w = PdfWriter()
    for b in bodies:
        for p in PdfReader(BytesIO(b)).pages:
            w.add_page(p)
    buf = BytesIO()
    w.write(buf)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / pdf_name(ds)
    path.write_bytes(buf.getvalue())
    return path


# ── 실행(위탁자 여럿) ───────────────────────────────────────────
def load_data(folder: Path, accounts: list[str] | None = None, months: list[str] | None = None) -> dict:
    """위탁자정산서 json 폴더 → {계정ID: [달 자료]} · 고른 계정ID 가 없으면 중단."""
    out: dict = {}
    for p in sorted(folder.glob("*_??????.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if not months or _month(d) in months:
            out.setdefault(d["account"], []).append(d)
    missing = [a for a in accounts or [] if a not in out]
    if missing or not out:
        raise ConsignorPdfError(f"자료 없음 {missing or folder}")
    return {a: out[a] for a in accounts or out}


def run(folder: Path, sheets: dict, issued: str, out_dir: Path, *, session, client_for: Callable,
        accounts: list[str] | None = None, months: list[str] | None = None, log: Callable[[str], None] = print) -> tuple[list, list]:
    """위탁자마다 PDF 1개 → ([만든 파일], [(계정ID, 사유)]) — 위탁자 하나가 막히면 그 위탁자만(나머지는 계속)."""
    from coupang_analytics.gsheet_api import GSheetError
    data = load_data(folder, accounts, months)
    clients = {m: client_for(u) for m, u in sheets.items()}
    made, failed = [], []
    for acct, ds in data.items():
        try:
            made.append(consignor_pdf(session, clients, ds, issued, out_dir))
            log(f"✅ {made[-1]}")
        except (ConsignorPdfError, GSheetError) as exc:
            failed.append((acct, str(exc)))
            log(f"❌ {acct} PDF 안 만듦 — {exc}")
    return made, failed
