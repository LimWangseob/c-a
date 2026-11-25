"""위탁자 정산서(3차 형식) → 구글시트 그리기 · 검산 · 탭 PDF 내보내기 (T-38 S3).

샘플 `output\\_샘플_261115_위탁자정산서\\_sheet\\render_gsheet.py`·`export_pdf.py` 를 저장소 모듈로 옮김.
- `build_statement(ds, issued)` = 순수 함수: 자료 dict 목록 → 탭 구성(이름·gid·순서) + 탭마다 Sheets API batchUpdate 요청.
  칸 값은 서식과 함께 `updateCells` 요청 안에 들어간다(값만 따로 쓰는 values.update 호출 없음 — 샘플과 같음).
- `check(d)` = 합계 검산 → 어긋남 목록. 하나라도 있으면 `build_statement`·`write_statement` 가 예외로 중단.
- `write_statement(client, ds, issued)` = 기존 시트(client 가 가리키는 스프레드시트)의 탭을 지우고 다시 그림('변경 기록' 탭만 맨 끝에 남김 · D-242 ③).
  client = `gsheet_api.GSheetClient` 모양(`meta(refresh=True)`·`batch_update(requests)`). 새 파일 만들기(D-242 ④ OAuth)는 아직 없음.
- `export_tab_bytes(session, spreadsheet_id, gid)` = 탭 하나를 A4 PDF 로(session = 인증된 HTTP 세션 · `.get(url, timeout=)`).
  위탁자별 PDF 묶기(D-260) = `settlement_consignor_pdf`.
형식 규칙 = D-238·D-240·D-241·D-242·D-251·D-259·D-260·D-343 고정 형식 (docs/CURRENT_RULES.md 12절).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from coupang_analytics.settlement_consignor_gsheet_layout import C, Page, requests_for
from coupang_analytics.settlement_consignor_gsheet_fixed import consignor_sheet
from coupang_analytics.settlement_consignor_gsheet_pages import evidence_sheet, pending, summary_sheet

FIRST_GID = 1000                 # 탭 gid = 1000 부터 차례로(요약 → 위탁자들 → 다음 달 요약 …)
TMP_GID = 990000                 # 옛 탭을 다 지우는 동안 남겨 둘 임시 탭
TMP_TITLE = "_tmp_render"
KEEP_TABS = ("변경 기록",)         # D-242 ③ 맨 끝 탭 — 다시 그려도 지우지 않음(매일 이어 쓰는 기록)
TAB_COLOR = {"summary": "p", "consignor": "p2", "evidence": "mute"}
PDF_QUERY = ("size=A4&portrait=true&fitw=true&gridlines=false&printtitle=false&sheetnames=false"
             "&pagenum=UNDEFINED&top_margin=0&bottom_margin=0&left_margin=0&right_margin=0&horizontal_alignment=CENTER")


class StatementCheckError(ValueError):
    """검산 실패 — 시트를 쓰지 않고 중단."""


@dataclass
class TabPlan:
    title: str
    gid: int
    kind: str                    # "summary" | "consignor" | "evidence"(달 근거 · 내부용 D-401 ②)
    data: list[dict] | dict      # summary·evidence = 그 달 위탁자 자료 목록 · consignor = 위탁자 자료 1개
    member_gids: list[int] = field(default_factory=list)   # summary 만: 위탁자 탭 gid(요약 표 '보기 →' 링크)
    page: Page | None = None
    pages: int = 0
    requests: list[dict] = field(default_factory=list)


@dataclass
class StatementPlan:
    issued: str
    tabs: list[TabPlan]

    def months(self) -> list[str]:
        return sorted({t.data["period_start"][:7] for t in self.tabs if isinstance(t.data, dict)})

    def pdf_gids(self) -> list[int]:
        """PDF 로 내보낼(위탁자에게 보낼) 탭 = 위탁자 탭만 · 요약(D-260)·'{n}월 근거'(D-401 ②) = 시트에만."""
        return [t.gid for t in self.tabs if t.kind == "consignor"]


# ── 검산(어긋나면 중단) ─────────────────────────────────────────
def _check_lines(d: dict, L: dict[int, int]) -> list[str]:
    errs = []
    if sorted(L) != list(range(1, 9)) or len(d["lines"]) != 8:
        errs.append("lines 1~8 아님")
    if sum(L.values()) != d["product_subtotal"]:
        errs.append(f"1~8 합 {sum(L.values())} ≠ 상품 정산액 {d['product_subtotal']}")
    return errs


def _check_product_columns(d: dict, L: dict[int, int], P: dict[int, int]) -> list[str]:
    errs = []
    for i in range(1, 9):
        s = sum(p[f"c{i}"] for p in d["products"])
        if s != L.get(i):
            errs.append(f"상품표 {i}열 합 {s} ≠ 1쪽 {L.get(i)}")
        ps = sum((p.get("pending") or {}).get(f"c{i}", 0) for p in d["products"])
        if ps != P.get(i):
            errs.append(f"상품표 {i}열 확정 전 합 {ps} ≠ 1쪽 {i} 확정 전 {P.get(i)}")
    return errs


def _check_product_rows(d: dict) -> list[str]:
    errs = []
    for p in d["products"]:
        if sum(p[f"c{i}"] for i in range(1, 9)) != p["subtotal"]:
            errs.append(f"상품 '{p['name']}' 소계 불일치")
        pp = p.get("pending")
        if pp and sum(pp[f"c{i}"] for i in range(1, 9)) != pp["subtotal"]:
            errs.append(f"상품 '{p['name']}' 확정 전 소계 불일치")
    return errs


def _check_pending_sales(d: dict) -> list[str]:
    """E1: 2쪽 상품 줄(이름 묶은 뒤)의 윙 정산 예정 판매 ≥ 0(D-405 — 로켓그로스 음수 = 반품 순액 그대로 · 관리 비율 0~100% 밖 = D-262 ③ · 계산 쪽).
    'wing_c1' 없는 옛 json = 전체 예정 판매로 봄(막는 쪽)."""
    wing = [(p["name"], pp.get("wing_c1", pp["c1"])) for p in d["products"] if (pp := p.get("pending"))]
    return [f"E1 상품 '{name}' 윙 정산 예정 판매 {v:,} < 0" for name, v in wing if v < 0]


def _check_common_pending(d: dict, L: dict[int, int], P: dict[int, int]) -> list[str]:
    errs = []
    if d["rg_kinds"] and sum(k["amount"] for k in d["rg_kinds"]) != L.get(6):
        errs.append("6 종류별 합 ≠ 1쪽 6")
    cm = d["common"]
    if sum(i["applied_amount"] for i in cm["items"]) != cm["total_applied"]:
        errs.append("9 반영 합 불일치")
    if sum(i["coupang_amount"] for i in cm["items"]) != cm["total_coupang"]:
        errs.append("9 청구 합 불일치")
    pt = sum(P.values()) + sum(i["applied_amount"] for i in cm["items"] if i.get("pending"))
    if pt != (d.get("pending_total") or 0):
        errs.append(f"확정 전 금액 {d.get('pending_total')} ≠ 1~8 확정 전 + 9 확정 전 {pt}")
    if pending(d) != bool(d.get("pending_total") or d.get("pending_detail")):
        errs.append("상태(status)와 확정 전 금액이 안 맞음")
    return errs


def _check_settle(d: dict) -> list[str]:
    errs = []
    st = d["product_subtotal"] + d["common"]["total_applied"] + sum(x["amount"] for x in d["separate"])
    if st != d["settle_amount"]:
        errs.append(f"정산 금액 {d['settle_amount']} ≠ 계산 {st}")
    for k in ("flow", "deposits"):
        s = sum(x["amount"] for x in d[k])
        if s != d["settle_amount"]:
            errs.append(f"{k} 합 {s} ≠ 정산 금액 {d['settle_amount']}")
    return errs


def check(d: dict) -> list[str]:
    """위탁자 자료 1개 합계 검산 → 어긋남 목록(빈 목록 = 통과).

    1쪽 1~8 = 2쪽 상품표 열 합(확정 전 포함) · 상품 소계 · 상품 줄 정산 예정 판매 ≥ 0(D-261 E1) · 6 종류별 · 9 반영/청구 · 확정 전 금액 · 상태 ·
    정산 금액 = 상품 정산액 + 9 + 10 · 어디로 갔나요(flow)·입금 내역(deposits) 합 = 정산 금액."""
    L = {x["no"]: x["amount"] for x in d["lines"]}
    P = {x["no"]: x.get("pending", 0) for x in d["lines"]}
    return (_check_lines(d, L) + _check_product_columns(d, L, P) + _check_product_rows(d)
            + _check_pending_sales(d) + _check_common_pending(d, L, P) + _check_settle(d))


def check_all(ds: list[dict]) -> list[str]:
    """여러 위탁자 검산 — 어긋남마다 '계정 YYYY-MM: 내용'."""
    return [f"{d['account']} {d['period_start'][:7]}: {e}" for d in ds for e in check(d)]


# ── 탭 구성 · 요청 ─────────────────────────────────────────────
def month_label(d: dict) -> str:
    return f"{int(d['period_start'][5:7])}월"


def tab_title(d: dict) -> str:
    return f"{month_label(d)} {d['ceo']} ({d['account']})"


def plan_tabs(ds: list[dict]) -> list[TabPlan]:
    """판매 달 순서 · 달마다 '{n}월 요약' → 위탁자 탭들(넘겨준 순서) → '{n}월 근거'(D-401 ②) · gid = 1000 부터."""
    out: list[TabPlan] = []
    gid = FIRST_GID
    for m in sorted({d["period_start"][:7] for d in ds}):
        md = [d for d in ds if d["period_start"][:7] == m]
        summary = TabPlan(f"{month_label(md[0])} 요약", gid, "summary", md)
        out.append(summary)
        for i, d in enumerate(md, start=1):
            out.append(TabPlan(tab_title(d), gid + i, "consignor", d))
        summary.member_gids = [gid + i for i in range(1, len(md) + 1)]
        out.append(TabPlan(f"{month_label(md[0])} 근거", gid + len(md) + 1, "evidence", md))
        gid += len(md) + 2
    return out


def build_statement(ds: list[dict], issued: str) -> StatementPlan:
    """자료 → 탭 구성 + 탭마다 batchUpdate 요청(네트워크 없음). 검산 어긋남 하나라도 있으면 StatementCheckError."""
    errs = check_all(ds)
    if errs:
        raise StatementCheckError("검산 실패: " + " / ".join(errs))
    tabs = plan_tabs(ds)
    for t in tabs:
        if t.kind == "summary":
            assert isinstance(t.data, list)
            t.page, t.pages = summary_sheet(t.data, t.member_gids, issued), 1
        elif t.kind == "evidence":
            assert isinstance(t.data, list)
            t.page, t.pages = evidence_sheet(t.data, issued), 1
        else:
            assert isinstance(t.data, dict)
            t.page, t.pages = consignor_sheet(t.data, issued)
        t.requests = requests_for(t.page, t.gid)
    return StatementPlan(issued, tabs)


def setup_requests(old_sheet_ids: list[int], tabs: list[TabPlan]) -> list[dict]:
    """탭 다시 만들기: 임시 탭 → 옛 탭 삭제 → 새 탭(맨 앞부터 순서·색) → 임시 탭 삭제 (batchUpdate 1회).
    old_sheet_ids 에 없는 탭(`KEEP_TABS`)은 새 탭들 뒤 = 맨 끝에 그대로 남는다."""
    reqs: list[dict] = [{"addSheet": {"properties": {"sheetId": TMP_GID, "title": TMP_TITLE}}}]
    reqs += [{"deleteSheet": {"sheetId": sid}} for sid in old_sheet_ids]
    for i, t in enumerate(tabs):
        reqs.append({"addSheet": {"properties": {"sheetId": t.gid, "title": t.title, "index": i,
                                                 "tabColor": C[TAB_COLOR[t.kind]]}}})
    reqs.append({"deleteSheet": {"sheetId": TMP_GID}})
    return reqs


def _old_tabs(meta: dict, tabs: list[TabPlan]) -> list[int]:
    """지울 옛 탭 gid — `KEEP_TABS` 는 뺌. 남길 탭 gid 가 새로 만들 탭과 겹치면 쓰기 전에 중단."""
    props = [s["properties"] for s in meta["sheets"]]
    used = {t.gid for t in tabs} | {TMP_GID}
    clash = [f"{p['title']}(gid {p['sheetId']})" for p in props if p["title"] in KEEP_TABS and p["sheetId"] in used]
    if clash:
        raise StatementCheckError(f"남길 탭 번호가 새 탭과 겹침 {clash} — 시트를 쓰지 않음")
    return [p["sheetId"] for p in props if p["title"] not in KEEP_TABS]


def write_statement(client, ds: list[dict], issued: str, *, allow_multi_month: bool = False,
                    log: Callable[[str], None] | None = None) -> StatementPlan:
    """기존 스프레드시트(client)의 탭을 지우고 정산서 탭을 다시 그린다('변경 기록' 탭은 맨 끝에 남김). 검산 실패 = 아무것도 안 씀.

    판매 달마다 파일 1개(D-241 ⑥) — 여러 달 자료는 allow_multi_month=True(샘플 시트 다시 그리기)일 때만."""
    plan = build_statement(ds, issued)
    months = plan.months()
    if len(months) > 1 and not allow_multi_month:
        raise StatementCheckError(f"판매 달이 여러 개 {months} — 달마다 파일 1개(D-241 ⑥)")
    client.batch_update(setup_requests(_old_tabs(client.meta(refresh=True), plan.tabs), plan.tabs))
    for t in plan.tabs:
        client.batch_update(t.requests)
        if log is not None:
            log(f"✔ {t.title} gid={t.gid} — {len(t.page.rows) if t.page else 0}행 · {t.pages}쪽")
    return plan


# ── 탭 PDF 내보내기(확인·발송용) ───────────────────────────────
def pdf_export_url(spreadsheet_id: str, gid: int) -> str:
    """탭 하나 → A4 세로·너비 맞춤·여백 0·눈금선 없음 PDF 내보내기 주소."""
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=pdf&gid={gid}&{PDF_QUERY}"


def export_tab_bytes(session, spreadsheet_id: str, gid: int, *, timeout: int = 120) -> bytes:
    """session(인증된 HTTP 세션 — 예 google.auth AuthorizedSession)으로 탭 PDF 를 받음. 실패 = 예외."""
    r = session.get(pdf_export_url(spreadsheet_id, gid), timeout=timeout)
    if r.status_code != 200 or r.content[:4] != b"%PDF":
        raise RuntimeError(f"PDF 내보내기 실패 gid={gid}: HTTP {r.status_code} {r.headers.get('content-type')} {len(r.content)}바이트")
    return r.content
