"""정산 월자료(D-161 2단계 · D-170 소급 단계 · D-171) — 조회만으로 받는 달 단위 근거 자료와 RG 반품내역.

designs/SETTLEMENT_MODULE.md §16-2 N3~N7·N10. 실측(gyi0101 2026-11-08 · 소유자 로그인 Chrome · 조회만):
| 종류 | 주소 | 응답 | '받음' 판정 |
|---|---|---|---|
| 매입세금계산서(N3) | POST /tenants/finance/wing/taxinvoice 폼 from·to·year·month | HTML 표 12칸 · 쪽 넘김 없음 | 머리글 12칸 그대로 |
| 위수탁세금계산서(N4) | GET /tenants/finance/wing/consignment/taxinvoice?page&from&to&year&month&ipId= | HTML 표 10칸 | 머리글 10칸 그대로 |
| 라이브정산(N5) | GET /tenants/live/api/marketplace/settlement/deduction/summary/list · raw/list(&pageIndex) | JSON | 상세 합 = 요약 합(netGmv·amount) |
| 주문별매출(N10) | POST /tenants/msf/wing/api/payment-report/order-detail-page-total → order-detail | JSON · ⛔size 10 고정 | 쪽 수와 줄 수·중복 없음·마지막 빈 쪽 |
| RG재고변동(N6) | GET /tenants/rfm-inventory/excel/reconciliation/report/{년}/{월(앞 0 없음)} | xlsx 시트 2 | 시트 2개·머리글·'내역 발생 일자' 가 그 달 |
| RG반품내역(N7) | GET /tenants/rfm-inventory/excel/v2/skureturns/{업체코드}/{시작ms}/{끝ms} | xlsx · 기간 무시(매번 전체 이력) | 시트·머리글 10칸 |
- 주문별매출: size 11·20·100 = 응답 없음 · 50 = 400 · 10 = 0.5초(실측). 2쪽부터 앞 응답 cursorToken(빈 값일 수 있음)을 넘김.
- 저장하지 않는 칸: 주문별매출 customerName · 라이브 creatorName·creatorNameToken·creatorId(고객·크리에이터 개인).
"""
from __future__ import annotations

import calendar
import gzip
import io
import json
import re
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

from .settlement_wing_api import _CALL_JS, ApiBlocked, ServerBusy, SiteChangedError

FROM = date(2026, 1, 1)
BUDGET_MONTHS = 3                 # 회차당 계정당 종류마다 받는 달 수(D-170)
ORDER_PAGE_SIZE = 10              # ⛔ 주문별매출 쪽 크기 — 다른 값은 응답 없음/400(실측 D-171)
# 달이 끝나고 며칠 뒤부터 받나 [추정] — 세금계산서 발행일 = 말일(실측) · 라이브 계산일 = 다음 달 25일(실측 2026-01 → 02-25)
LAG_DAYS = {"매입세금계산서": 15, "위수탁세금계산서": 15, "라이브정산": 35, "주문별매출": 15, "RG재고변동": 15}
KINDS = tuple(LAG_DAYS)
RG_KINDS = ("RG재고변동",)        # 로켓그로스 계정(업체코드 있음)만
RETURNS = "RG반품내역"            # 하루 1번 최신본 덮어쓰기(D-171)
LEDGER = "_받은기록.json"

TAX = "/tenants/finance/wing/taxinvoice"
CONSIGN = "/tenants/finance/wing/consignment/taxinvoice"
LIVE = "/tenants/live/api/marketplace/settlement/deduction"
ORDER = "/tenants/msf/wing/api/payment-report/order-detail"
RECON = "https://wing.coupang.com/tenants/rfm-inventory/excel/reconciliation/report/{y}/{m}"
RETURNS_URL = "https://wing.coupang.com/tenants/rfm-inventory/excel/v2/skureturns/{v}/{s}/{e}"
TAX_HEAD = ("상호(공급자)", "사업자등록번호(공급자)", "상호(공급받는자)", "사업자등록번호(공급받는자)", "발행내용", "발행번호",
            "공급가액", "세액", "합계", "발행일", "esero전송상태", "조회")
CONSIGN_HEAD = ("주문번호", "상호(공급받는 자)", "사업자등록번호(공급받는 자)", "발행내용", "발행번호", "공급가액", "세액", "합계",
                "발행일", "세금계산서확인")
RETURNS_HEAD = ("접수일자", "유형", "반품번호", "주문번호", "옵션 ID", "등록상품명,옵션명", "고객 반품 사유", "검수번호", "검수 등급",
                "처리상태")
RECON_SHEETS = ("1. 재고이관 상세", "2. 입고관련")
NO_ROWS = "발행 내역이 없습니다"
_LIVE_DROP = ("creatorName", "creatorNameToken", "creatorId")
_KST = timedelta(hours=9)


def due_months(kind: str, today: date) -> list[tuple[str, date, date]]:
    """받을 달 [(YYYYMM, 1일, 말일)] — FROM 부터 말일+LAG_DAYS 가 지난 달까지 · **최근 달부터**(소급과 같은 순서)."""
    return months_after(LAG_DAYS[kind], today)


def months_after(lag_days: int, today: date) -> list[tuple[str, date, date]]:
    """FROM 부터 말일+lag_days 가 지난 달 [(YYYYMM, 1일, 말일)] · 최근 달부터(요청형 월자료도 같은 규칙)."""
    out: list[tuple[str, date, date]] = []
    y, m = FROM.year, FROM.month
    while True:
        last = date(y, m, calendar.monthrange(y, m)[1])
        if last + timedelta(days=lag_days) >= today:
            return out[::-1]
        out.append((f"{y}{m:02d}", date(y, m, 1), last))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def call_html(page, method: str, path: str, body: str | None = None) -> str:
    """WING 화면 주소를 페이지 안에서 불러 HTML 글자 그대로(세금계산서 화면은 JSON 이 아님). 403·429·Access Denied = 차단."""
    r = page.evaluate(_CALL_JS, [method, path, body])
    st, text = r["status"], r["text"]
    if st in (500, 502, 503, 504):
        raise ServerBusy(f"{path} → {st} 서버 일시 오류")
    if st in (403, 429) or "Access Denied" in text[:2000]:
        raise ApiBlocked(f"{path} → {st} 차단 의심 {text[:80]!r}")
    if st != 200:
        raise SiteChangedError(f"{path} → {st} {text[:200]!r}")
    return text


class _Tables(HTMLParser):
    """표(table)마다 [줄[칸 글자]] — th·td 둘 다 칸."""

    def __init__(self):
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
            self._depth += 1
        elif tag == "tr" and self._depth:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.tables[-1].append(self._row)
            self._row = None
        elif tag == "table" and self._depth:
            self._depth -= 1

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def parse_invoice_table(html: str, head: tuple) -> list[dict]:
    """세금계산서 화면 HTML → 줄 [{머리글: 글자}]. 머리글이 head 와 다르면 화면 변경(SiteChangedError) · '발행 내역이 없습니다' = []."""
    p = _Tables()
    p.feed(html)
    for t in p.tables:
        if t and tuple(t[0]) == head:
            rows = [r for r in t[1:] if r]
            if len(rows) == 1 and NO_ROWS in rows[0][0]:
                return []
            bad = [r for r in rows if len(r) != len(head)]
            if bad:
                raise SiteChangedError(f"세금계산서 줄 칸 수가 머리글과 다름: {bad[0][:3]}")
            return [dict(zip(head, r)) for r in rows]
    raise SiteChangedError(f"세금계산서 표 머리글이 예상과 다름: {[t[0] for t in p.tables if t][:2]}")


def _won(s: str) -> int:
    return int(re.sub(r"[^\d-]", "", s) or 0)


def _invoices(rows: list[dict]) -> dict:
    return {"줄": rows, "공급가액 합": sum(_won(r["공급가액"]) for r in rows), "세액 합": sum(_won(r["세액"]) for r in rows)}


def fetch_purchase_tax(html_call, f: date, t: date, gap=lambda: None) -> dict:
    body = f"from={f}&to={t}&year={f.year}&month={f.month:02d}"
    return _invoices(parse_invoice_table(html_call("POST", TAX, body), TAX_HEAD))


def fetch_consign_tax(html_call, f: date, t: date, gap=lambda: None, max_pages: int = 50) -> dict:
    """쪽 끝까지(빈 쪽 또는 같은 줄 반복에서 멈춤 — 쪽 넘김 실측 없음[추정]) · 같은 발행번호+주문번호는 한 번."""
    rows: list[dict] = []
    seen: set = set()
    for page in range(1, max_pages + 1):
        if page > 1:
            gap()
        q = f"?page={page}&from={f}&to={t}&year={f.year}&month={f.month:02d}&ipId="
        got = parse_invoice_table(html_call("GET", CONSIGN + q, None), CONSIGN_HEAD)
        new = [r for r in got if (r["발행번호"], r["주문번호"]) not in seen]
        if not new:
            return _invoices(rows)
        seen |= {(r["발행번호"], r["주문번호"]) for r in new}
        rows += new
    raise SiteChangedError(f"위수탁 세금계산서 {max_pages}쪽 넘음 — 쪽 넘김 방식 확인 필요")


def fetch_live(call, ym: str, gap=lambda: None) -> dict:
    """라이브 정산 요약 + 상세(쪽 끝까지) · 크리에이터 칸 제외 · 상세 합 = 요약 합(netGmv·amount)이어야 받음."""
    q = f"month={ym}&vendorType=ALL&excelDataType=0&forExcel=0&vendorId="
    summ = _live_data(call("GET", f"{LIVE}/summary/list?{q}", None))
    raw: list = []
    page = 1
    while True:
        gap()
        d = _live_data(call("GET", f"{LIVE}/raw/list?{q}&pageIndex={page}", None))
        raw += [{k: v for k, v in x.items() if k not in _LIVE_DROP} for x in d.get("data") or []]
        if page >= int((d.get("page") or {}).get("pageTotal") or 0):
            break
        page += 1
    for k in ("netGmv", "amount"):
        a, b = sum(x.get(k) or 0 for x in summ), sum(x.get(k) or 0 for x in raw)
        if a != b:
            raise SiteChangedError(f"라이브 정산 {ym} 상세 합({k} {b})이 요약 합({a})과 다름 — 다 못 받음")
    return {"요약": summ, "상세": raw}


def _live_data(r: dict):
    if not r.get("successful"):
        raise SiteChangedError(f"라이브 정산 응답 실패: {str(r)[:120]}")
    return r.get("rData")


def fetch_order_detail(call, f: date, t: date, gap=lambda: None) -> dict:
    """주문별 매출(구매확정일 기준 한 달) — 쪽 수 조회 → 1쪽부터 빈 쪽 또는 커서 '' 까지(size 10) · 고객 이름 칸 제외.
    원본 건수(쪽마다 rawRecordSize 합)가 쪽 수와 맞고(10×(쪽−1) < 원본 ≤ 10×쪽) 같은 주문·유형이 두 번 없어야 받음.
    줄 수 ≤ 원본 건수 — 상품+추가배송료는 서버가 한 줄로 합쳐 줌(금액 합산 · 실측 11-09 oopean 2026-08 원본 481·줄 478)."""
    q = {"confirmStart": f.isoformat(), "confirmEnd": t.isoformat(), "searchDateType": "CONFIRM_DATE",
         "searchDateStart": f.isoformat(), "searchDateEnd": t.isoformat()}
    pages = int(call("POST", f"{ORDER}-page-total", {**q, "size": ORDER_PAGE_SIZE}))
    rows: list = []
    raw, cursor = 0, ""
    for page in range(1, pages + 2):
        gap()
        r = call("POST", ORDER, {**q, "page": page, "size": ORDER_PAGE_SIZE, "cursorToken": cursor})
        got = r.get("orderDetails") or []
        if not got:
            break
        raw += _raw_size(r, len(got), f"{f:%Y%m} {page}쪽")
        rows += [{k: v for k, v in x.items() if k != "customerName"} for x in got]
        cursor = r.get("cursorToken") or ""
        if not cursor:      # 커서 '' = 다음 쪽 없음 — ''로 또 부르면 서버가 처음부터 다시 줌(실측 11-09 bf0621 1쪽 달 3개)
            break
    else:
        raise SiteChangedError(f"주문별 매출 {f:%Y%m} 쪽 수({pages}) 뒤에도 줄이 더 옴 — 다 받았는지 모름")
    keys = {(x.get("orderId"), x.get("transactionType"), x.get("vendorItemId"), x.get("shippingFeeId")) for x in rows}
    if not (ORDER_PAGE_SIZE * (pages - 1) < raw <= ORDER_PAGE_SIZE * pages or pages == raw == 0) or len(keys) != len(rows):
        raise SiteChangedError(f"주문별 매출 {f:%Y%m} 쪽 수 {pages} · 원본 {raw} · 줄 {len(rows)} · 서로 다른 줄 {len(keys)} — 맞지 않음")
    total = {k: sum(x.get(k) or 0 for x in rows) for k in ("productGmv", "deliveryGmv", "trAmountIncVat", "apAmount")}
    return {"쪽 수": pages, "원본 건수": raw, "줄 수": len(rows), "합계": total, "줄": rows}


def _raw_size(r: dict, n_rows: int, where: str) -> int:
    """한 쪽의 원본 건수(rawRecordSize) — 없거나 받은 줄보다 적으면 응답 모양이 바뀐 것."""
    n = r.get("rawRecordSize")
    if not isinstance(n, int) or n < n_rows:
        raise SiteChangedError(f"주문별 매출 {where} 원본 건수 {n!r} · 줄 {n_rows} — 응답 모양 다름")
    return n


def _xlsx(body: bytes):
    import openpyxl
    try:
        return openpyxl.load_workbook(io.BytesIO(body), read_only=True)
    except Exception as exc:  # noqa: BLE001 — 열리지 않으면 받은 게 아님(어떤 형식 오류든 같은 판정)
        raise SiteChangedError(f"엑셀이 열리지 않음: {exc.__class__.__name__}") from exc


def check_recon(body: bytes, f: date, t: date) -> int:
    """RG 재고변동 엑셀 — 시트 2개·각 시트 첫 줄 '내역 발생 일자' = 그 달 · 시트1 머리글(등록상품 ID…) → 시트1 상품 줄 수."""
    wb = _xlsx(body)
    if tuple(wb.sheetnames[:2]) != RECON_SHEETS:
        raise SiteChangedError(f"재고변동 시트가 예상과 다름: {wb.sheetnames}")
    want = f"{f:%Y.%m.%d} ~ {t:%Y.%m.%d}"
    n = 0
    for name in RECON_SHEETS:
        rows = [[c for c in r if c not in (None, "")] for r in wb[name].iter_rows(values_only=True)]
        if not rows or want not in " ".join(map(str, rows[0])):
            raise SiteChangedError(f"재고변동 '{name}' 기간이 {want} 아님: {rows[0] if rows else '빈 시트'}")
        head = next((i for i, r in enumerate(rows) if r[:3] == ["등록상품 ID", "옵션 ID", "SKU ID"]), None)
        if head is None:
            raise SiteChangedError(f"재고변동 '{name}' 머리글(등록상품 ID·옵션 ID·SKU ID) 없음")
        if name == RECON_SHEETS[0]:
            n = sum(1 for r in rows[head + 1:] if r and str(r[0]).isdigit())
    return n


def check_returns(body: bytes) -> int:
    """RG 반품내역 엑셀 — 시트 'Excel Data'·머리글 10칸 → 반품 줄 수(접수일자가 날짜인 줄)."""
    wb = _xlsx(body)
    if "Excel Data" not in wb.sheetnames:
        raise SiteChangedError(f"반품내역 시트가 예상과 다름: {wb.sheetnames}")
    rows = [[c for c in r if c not in (None, "")] for r in wb["Excel Data"].iter_rows(values_only=True)]
    head = next((i for i, r in enumerate(rows) if tuple(r) == RETURNS_HEAD), None)
    if head is None:
        raise SiteChangedError("반품내역 머리글(접수일자…처리상태 10칸)이 예상과 다름")
    return sum(1 for r in rows[head + 1:] if r and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(r[0])))


def returns_url(vendor: str, today: date) -> str:
    """기간 인자는 무시되지만(매번 전체 이력·실측) 화면과 같은 모양으로 — 2025-01-01 ~ 어제(한국 시각 ms)."""
    return RETURNS_URL.format(v=vendor, s=_kst_ms(date(2025, 1, 1)), e=_kst_ms(today) - 1)


def vendor_from_snapshots(folder: Path) -> str:
    """로켓그로스 정산현황 원문(D-164 하루 1번·`정산현황_원문/{계정}/*.json.gz`)의 settlementGroupKey 앞부분 = 업체코드.
    최근 원문부터 보고 하나로 정해지면 그 값 · 여러 개면 '' (추측 금지 — unlisted_row_events 와 같은 규칙) · 원문 없음 = ''(윙 전용)."""
    for f in sorted(folder.glob("*.json.gz"), reverse=True) if folder.exists() else []:
        try:
            with gzip.open(f, "rt", encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            continue
        keys = {(r.get("settlementGroupKey") or "").split("-")[0] for part in ("조회", "예정") for q in rec.get(part) or []
                for r in (q.get("응답") or {}).get("settlementStatusReports") or []} - {""}
        if keys:
            return keys.pop() if len(keys) == 1 else ""
    return ""


def _kst_ms(d: date) -> int:
    return int((datetime(d.year, d.month, d.day) - _KST - datetime(1970, 1, 1)).total_seconds() * 1000)


def _fetch(kind: str, call, html_call, get_bytes, ym: str, f: date, t: date, gap) -> tuple[bytes, str, str]:
    """한 종류·한 달 받기 → (저장할 바이트, 확장자, 결과 요약). 판정 실패 = SiteChangedError(저장 안 함)."""
    if kind == "RG재고변동":
        body = get_bytes(RECON.format(y=f.year, m=f.month))
        return body, "xlsx", f"상품 {check_recon(body, f, t)}줄"
    if kind == "매입세금계산서":
        d = fetch_purchase_tax(html_call, f, t, gap)
    elif kind == "위수탁세금계산서":
        d = fetch_consign_tax(html_call, f, t, gap)
    elif kind == "라이브정산":
        d = fetch_live(call, ym, gap)
    else:
        d = fetch_order_detail(call, f, t, gap)
    n = len(d.get("줄") or d.get("상세") or [])
    return json.dumps(d, ensure_ascii=False).encode("utf-8"), "json", f"{n}줄"


class _Run:
    """한 계정 월자료 받기의 상태 — 받은 기록(_받은기록.json)·결과·실패 격리."""

    def __init__(self, folder: Path, note, fatal: tuple, now):
        folder.mkdir(parents=True, exist_ok=True)
        self.folder, self.note, self.fatal, self.now = folder, note, fatal, now
        self.lp = folder / LEDGER
        self.led: dict = json.loads(self.lp.read_text(encoding="utf-8")) if self.lp.exists() else {}
        self.out: dict = {"받음": [], "실패": [], "남은 달": 0, "파일": []}

    def save(self, name: str, body: bytes, key: str, sub: str = "") -> None:
        tmp = self.folder / (name + ".tmp")
        tmp.write_bytes(body)
        tmp.replace(self.folder / name)
        self.out["파일"].append(self.folder / name)
        stamp = self.now().isoformat(timespec="seconds")
        if sub:
            self.led.setdefault(key, {})[sub] = stamp
        else:
            self.led[key] = stamp
        self.lp.write_text(json.dumps(self.led, ensure_ascii=False, indent=1), encoding="utf-8")

    def attempt(self, label: str, fn):
        """fn() → 결과 · 차단(fatal)은 그대로 올림 · 그 밖 오류 = 실패 목록에 남기고 None(근거 자료 한 종류 실패가 정산 전체를
        막지 않게 — D-120 과 같은 격리)."""
        try:
            return fn()
        except self.fatal:
            raise
        except Exception as exc:  # noqa: BLE001 — 위 설명
            self.out["실패"].append(f"{label}: {exc.__class__.__name__}: {str(exc)[:120]}")
            self.note(f"월자료 {label} 실패 — {exc.__class__.__name__}: {str(exc)[:120]}")   # 본문까지(11-08 이름만 남아 원인 못 봄)
            return None

    def kind(self, kind: str, today: date, since: str, fetch, gap) -> None:
        """한 종류 — 받은 기록에 없는 달을 최근부터 이번 회차 남은 예산만큼 · 실패하면 그 종류는 이번 회차 멈춤."""
        got = self.led.get(kind) or {}
        todo = [m for m in due_months(kind, today) if m[0] not in got]
        used = sum(1 for s in got.values() if since and s >= since)
        for ym, f, t in list(todo[:max(0, BUDGET_MONTHS - used)]):
            r = self.attempt(f"{kind} {ym}", lambda ym=ym, f=f, t=t: fetch(kind, ym, f, t))
            gap()
            if r is None:
                break
            body, ext, msg = r
            self.save(f"{kind}_{ym}.{ext}", body, kind, ym)
            self.out["받음"].append(f"{kind}_{ym}.{ext}({msg})")
            todo = [m for m in todo if m[0] != ym]
        self.out["남은 달"] += len(todo)

    def returns(self, vendor: str, today: date, get_bytes) -> None:
        """RG 반품내역 — 하루 1번 최신본 덮어쓰기(기간 무시·매번 전체 이력)."""
        if str(self.led.get(RETURNS) or "")[:10] == today.isoformat():
            return
        body = get_bytes(returns_url(vendor, today))
        n = check_returns(body)
        self.save(f"{RETURNS}_최신.xlsx", body, RETURNS)
        self.out["받음"].append(f"{RETURNS}_최신.xlsx(반품 {n}줄)")


def collect(call, html_call, get_bytes, folder: Path, today: date, *, vendor: str = "", since: str = "",
            gap=lambda: None, page_gap=None, note=lambda m: None, fatal: tuple = (ApiBlocked,), now=datetime.now) -> dict:
    """월자료 받기(소급 단계 · D-170). 종류마다 받은 기록에 없는 달을 최근부터 — **회차(since 이후) 계정당 종류별 BUDGET_MONTHS 달**.
    종류 하나가 실패하면 그 종류만 이번 회차 멈춤(다음 회차가 이어서)·차단(fatal)은 그대로 올림. RG 반품내역 = 업체코드 있는
    계정만 하루 1번 최신본 덮어쓰기. gap = 종류·달 사이 쉼 · page_gap = 한 자료 안 쪽 넘김 쉼(없으면 gap — 주문별 매출은 10건씩이라
    큰 계정은 쪽이 많음). 반환 = {'받음': [파일 이름·요약], '실패': [...], '남은 달': n, '파일': [저장 경로]}."""
    run = _Run(folder, note, fatal, now)

    def fetch(kind, ym, f, t):
        return _fetch(kind, call, html_call, get_bytes, ym, f, t, page_gap or gap)
    for kind in KINDS:
        if kind not in RG_KINDS or vendor:
            run.kind(kind, today, since, fetch, gap)
    if vendor:
        run.attempt(RETURNS, lambda: run.returns(vendor, today, get_bytes))
    return run.out
