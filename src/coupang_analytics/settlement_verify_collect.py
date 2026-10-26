"""정산 검증 자료 수집(조회만) — 쿠팡의 다른 장부로 우리 정산 파일·지급액을 대조하기 위한 원자료.

소유자 요구(2026-10-08): 통장 없이 정산 금액을 검증. 실측(nicoable 2026-10-08)으로 확인한 쿠팡 메뉴·주소:
| 장부 | 화면(먼저 열어야 함) | 주소 |
|---|---|---|
| 로켓그로스 월렛 입출금·잔액 | 로켓그로스 정산현황 | POST /tenants/rfm/v2/wallet/histories/search/api · GET …/wallet/balance/api |
| 윙 매출내역(월별) | 정산 > 매출내역 | POST /tenants/msf/wing/api/purchase-report/list |
| 윙 부가세 신고내역 | 정산 > 부가세 신고내역 | POST /tenants/msf/wing/api/payment-method/list {from,to=YYYYMM} |
| 로켓그로스 부가세 | 로켓그로스 부가세 화면 | GET /tenants/rfm/api/settlements/vat/search?fromYearMonth&toYearMonth |
| 보류목록 / 추가지급(월별) | 정산 > 보류목록 / 추가지급 | POST …/payment-pending-report/list · …/additional-payment-report/list |
| 윙 정산캘린더(지급일·예정) | 정산 현황 > 정산캘린더 | POST /tenants/msf/wing/api/payout-date-calendar/payout-dates (폼 startDate·endDate) |
| 우대수수료 환급(주문별·결제/취소일 달마다) | 정산 > 우대수수료 환급조회 | GET …/favorablefee/refund/list/data?page&pageSize&from&to&dateType |
| 로켓그로스 입고 내역(밀크런번호·상품 수량) | 로켓그로스 > 입고관리 | GET /tenants/rfm-inbound/data/inbound/search?pagingSize&pageIndex |
| 상품 없는 배송비 주문의 반품(주문번호별) | 주문/배송 > 주문조회 > 주문상세 '반품정보' | GET /tenants/sfl-portal/return/delivery/{주문번호} |
⚠ 매출내역 등은 그 화면을 연 상태에서 불러야 한다(다른 화면에서 부르면 504 — 실측). 오늘 이후 날짜를 넣으면 504(실측)
→ 월 끝은 어제까지. 서버 일시 오류(ServerBusy)는 그 항목만 '조회 실패'로 남기고 다음 항목 진행.
개인정보(계좌·예금주)는 저장하지 않는다.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from .settlement_files import _SHIP_MARK
from .settlement_wing_api import RG_URL, ServerBusy, SiteChangedError

_W = "https://wing.coupang.com"
SALES_URL = f"{_W}/tenants/finance/wing/contentsurl/sales-report"
PENDING_URL = f"{_W}/tenants/finance/wing/contentsurl/payments-pending"
ADDITIONAL_URL = f"{_W}/tenants/msf/wing/view/additional-payment-report-view"
WING_VAT_URL = f"{_W}/tenants/finance/wing/contentsurl/proportion-sales"
RG_VAT_URL = f"{_W}/tenants/rfm/settlements/vat-report"
CALENDAR_URL = f"{_W}/tenants/msf/wing/view/payout-date-calendar"
PURCHASE = "/tenants/msf/wing/api/purchase-report/list"
PENDING = "/tenants/msf/wing/api/payment-pending-report/list"
ADDITIONAL = "/tenants/msf/wing/api/additional-payment-report/list"
WING_VAT = "/tenants/msf/wing/api/payment-method/list"
RG_VAT = "/tenants/rfm/api/settlements/vat/search"
WALLET_HIST = "/tenants/rfm/v2/wallet/histories/search/api"
WALLET_BAL = "/tenants/rfm/v2/wallet/balance/api"
CALENDAR = "/tenants/msf/wing/api/payout-date-calendar/payout-dates"   # 윙 정산캘린더(폼 본문·과거~미래 지급일)
# 우대수수료 환급 주문별(D-116) — 엑셀(FAVORABLE_FEE_DETAIL)과 같은 칸을 화면 조회로 바로(요청·생성 대기 없음). 실측(벅스 2026-10-26):
# 다른 윙 화면에서 불러도 됨 · 한 달 넘으면 400 · pageSize 500 허용 · 줄마다 큰 localeProperty → 아래 칸만 저장.
FAVORABLE = "/tenants/finance/wing/integrated/favorablefee/refund/list/data"
FAV_KEEP = ("orderId", "transactionDateStr", "expectedTransferDateStr", "realTransferDateStr", "refundAmount", "companyScale",
            "transferStatus", "taxBillIssueTarget")
CALENDAR_AHEAD = timedelta(days=70)
WALLET_FROM = date(2025, 1, 1)          # 월렛 장부(입금−인출=잔액) 대조용 — 소급 시작보다 넉넉히
PENDING_FROM = date(2025, 1, 1)         # 보류목록 = 보류일 기준 — 2026 지급 줄의 보류가 2025 에 잡힌 것까지(D-083)
# 상품 없는 윙 배송비 줄 = 구매확정 전 반품의 고객 부담 왕복배송비(D-116) → 그 주문의 반품 상품. 실측(벅스 2026-10-26): 주문번호 검색은
# 기간 무관 · 다른 윙 화면에서도 됨 · 없는 주문 = 200 빈 본문. 응답엔 고객 이름·연락처·주소·고객이 쓴 글이 있어 아래 칸만 저장.
# 입고 내역(D-116 밀크런 몫 = 입고 건별 상품 수량 비율) — 실측(벅스 2026-10-26) 34건 한 쪽 · 실제 입고 수량 = stowedQty.
INBOUND = "/tenants/rfm-inbound/data/inbound/search"
RETURN_DELIVERY = "/tenants/sfl-portal/return/delivery"
RET_KEEP = ("cancelId", "orderId", "receiptDate", "returnDate", "returnStatus", "requestSolution", "reasonCode", "reasonCodeName",
            "faultType", "returnDeliveryPriceBurden", "deliveryChargeType", "returnDeliveryPrice", "estimatedRefundPrice",
            "cancelCountSum", "productShipmentType")
RET_ITEM_KEEP = ("vendorItemId", "vendorItemName", "unitPrice", "price", "quantity", "cancelQuantity")
_PII = ("bank", "owner", "accountnumber")


def months(start: date, today: date) -> list[tuple[str, date, date]]:
    """[(YYYYMM, 1일, 끝)] — 끝은 그 달 말일과 어제 중 이른 날(오늘 이후 날짜는 서버가 시간초과). 어제 이후 달은 없음."""
    last, out = today - timedelta(days=1), []
    y, m = start.year, start.month
    while date(y, m, 1) <= last:
        end = min(date(y, m, calendar.monthrange(y, m)[1]), last)
        out.append((f"{y}{m:02d}", date(y, m, 1), end))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def scrub(obj):
    """계좌·예금주 등 개인정보 칸 제거(재귀)."""
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items() if not any(p in k.lower() for p in _PII)}
    if isinstance(obj, list):
        return [scrub(x) for x in obj]
    return obj


def orphan_ship_orders(files: list) -> list[str]:
    """윙 정산 파일들 → 배송비 줄(금액 있음)만 있고 상품 줄이 어느 파일에도 없는 주문번호(정렬)."""
    prod = {r.order_id for f in files for r in f.rows if r.product_id}
    return sorted({r.order_id for f in files for r in f.rows
                   if _SHIP_MARK.fullmatch(r.option_id or "") and (r.sales or r.settle) and r.order_id not in prod})


def returns_to_ask(orders: list[str], old: dict) -> list[str]:
    """이미 저장한 주문(반품 기록·반품 없음 [])은 다시 조회하지 않음 — 새 주문과 조회 실패(None)만."""
    return [o for o in orders if old.get(o) is None]


def collect(call, open_page, start: date, today: date, *, note=lambda m: None, gap=lambda: None,
            orders: list[str] = ()) -> dict:
    """call(method, path, body)→JSON · open_page(url) — 호출부가 차단 검사·재시도 포함해 넘김.
    반환 = 검증 원자료 dict(개인정보 제거). 항목별 실패는 '조회 실패' 목록에 남기고 계속(차단은 호출부 예외로 중단)."""
    data: dict = {"수집일": today.isoformat(), "기간": [start.isoformat(), (today - timedelta(days=1)).isoformat()],
                  "조회 실패": []}
    mlist = months(start, today)

    def safe(label, fn):
        try:
            return fn()
        except (ServerBusy, SiteChangedError) as exc:
            data["조회 실패"].append(f"{label}: {exc.__class__.__name__}: {str(exc)[:120]}")
            note(f"검증 자료 {label} 조회 실패 — {exc.__class__.__name__}")
            return None
        finally:
            gap()

    open_page(CALENDAR_URL)
    data["calendar"] = safe("정산캘린더", lambda: call("POST", CALENDAR, f"startDate={start - timedelta(days=7)}"
                                                                         f"&endDate={today + CALENDAR_AHEAD}"))
    open_page(RG_URL)
    data["wallet"] = safe("월렛 내역", lambda: _wallet(call, WALLET_FROM, today))
    bal = safe("월렛 잔액", lambda: call("GET", WALLET_BAL, None))
    data["wallet_balance"] = ((bal or {}).get("content") or {}).get("balanceAmount") if bal else None
    if mlist:
        open_page(RG_VAT_URL)
        q = f"?fromYearMonth={mlist[0][0][:4]}-{mlist[0][0][4:]}&toYearMonth={mlist[-1][0][:4]}-{mlist[-1][0][4:]}"
        data["rg_vat"] = safe("로켓그로스 부가세", lambda: call("GET", RG_VAT + q, None))
        open_page(WING_VAT_URL)
        data["wing_vat"] = safe("윙 부가세", lambda: call("POST", WING_VAT, {"from": int(mlist[0][0]), "to": int(mlist[-1][0])}))
    data["purchase"] = _monthly(call, open_page, safe, SALES_URL, "매출내역", mlist,
                                lambda ym, f, t: (PURCHASE, {"fromDate": f.isoformat(), "toDate": t.isoformat()}))
    open_page(PENDING_URL)
    data["pending"] = {"전체": safe("보류목록", lambda: _pending(call, PENDING_FROM, today - timedelta(days=1)))}
    data["additional"] = _monthly(call, open_page, safe, ADDITIONAL_URL, "추가지급", mlist,
                                  lambda ym, f, t: (ADDITIONAL, {"fromDate": f.isoformat(), "toDate": t.isoformat(),
                                                                 "taxInvoiceIssueType": None, "requestStatusType": None,
                                                                 "orderId": None, "page": 1, "pageSize": 100}))
    data["favorable"] = {ym: safe(f"우대수수료 환급 {ym}", lambda f=f, t=t: _favorable(call, f, t)) for ym, f, t in mlist}
    data["inbound"] = safe("입고 내역", lambda: _inbound(call))
    if orders:
        data["returns"] = {o: safe(f"반품 조회 {o}", lambda o=o: _returns(call, o)) for o in orders}
    return scrub(data)


def _wallet(call, start: date, today: date) -> list:
    out: list = []
    page = 0
    while True:
        r = call("POST", WALLET_HIST, {"startDate": start.isoformat(), "endDate": today.isoformat(),
                                       "walletEventType": None, "pageNumber": page, "pageSize": 50})
        out += r.get("walletHistories") or []
        page += 1
        if page >= (r.get("totalPage") or 0):
            return out


def _pending(call, start: date, end: date) -> dict:
    """보류목록 — 보류일 기준 긴 기간 한 번(실측 2026-10-19: 2025-01~2026-10 한 번 = 달마다 조회 합) · 쪽 끝까지."""
    rows: list = []
    page = 1
    while True:
        r = call("POST", PENDING, {"from": start.isoformat(), "to": end.isoformat(), "year": start.year,
                                   "month": start.month, "commerceType": "3PM", "searchType": "PENDING_DATE",
                                   "pendingType": "ALL", "pendingYn": "ALL", "page": page, "pageSize": 100})
        rows += r.get("pendingReports") or []
        if page >= (r.get("totalPageCount") or 0):
            return {"from": start.isoformat(), "to": end.isoformat(), "totalRecordCount": len(rows), "pendingReports": rows}
        page += 1


def _favorable(call, start: date, end: date) -> dict:
    """우대수수료 환급 — 결제/취소일 한 달(어제까지) · 쪽 끝까지 → {totalCount, rows[FAV_KEEP 칸]}."""
    rows: list = []
    page = 1
    while True:
        r = call("GET", f"{FAVORABLE}?page={page}&pageSize=500&from={start.isoformat()}&to={end.isoformat()}"
                        "&dateType=TRANSACTION", None)
        rows += [{k: x.get(k) for k in FAV_KEEP} for x in r.get("dtos") or []]
        if page >= (r.get("totalPage") or 0):
            return {"totalCount": r.get("totalCount") or len(rows), "rows": rows}
        page += 1


def _inbound(call) -> list:
    """로켓그로스 입고 전부(0쪽부터 끝까지) → 밀크런번호·상태·상품 수량만."""
    out: list = []
    page = 0
    while True:
        r = call("GET", f"{INBOUND}?pagingSize=50&pageIndex={page}", None)
        for x in r.get("content") or []:
            st = x.get("latestShipmentStatus") or {}
            out.append({"shipmentId": x.get("shipmentId"), "milkrunSeq": x.get("milkrunSeq"), "shipmentType": x.get("shipmentType"),
                        "createdAt": x.get("createdAt"), "fcCode": x.get("fcCode"),
                        "pickupDate": (x.get("milkrunShipmentInfo") or {}).get("pickupDateYYYYMMDD"),
                        "statusId": st.get("statusId"), "cancelled": st.get("shipmentCancelled"),
                        "skus": [{"vendorItemId": (k.get("plannedSku") or {}).get("vendorItemId"),
                                  "skuName": (k.get("plannedSku") or {}).get("cachedSkuName"),
                                  "requestedQty": (k.get("plannedSku") or {}).get("requestedQty"),
                                  "receivedQty": k.get("receivedQty"), "stowedQty": k.get("stowedQty")}
                                 for k in x.get("skuDetails") or []]})
        page += 1
        if page >= ((r.get("pagination") or {}).get("totalPages") or 0):
            return out


def _returns(call, order: str) -> list:
    """주문 하나의 반품 접수 목록(RET_KEEP·상품 RET_ITEM_KEEP 칸만). 빈 본문(반품 없음) = []."""
    try:
        recs = call("GET", f"{RETURN_DELIVERY}/{order}", None)
    except SiteChangedError as exc:
        if str(exc).endswith("JSON 아님: ''"):
            return []
        raise
    return [{**{k: x.get(k) for k in RET_KEEP},
             "items": [{k: i.get(k) for k in RET_ITEM_KEEP} for i in x.get("omsSimpleOrderItemDtos") or []]} for x in recs or []]


def _monthly(call, open_page, safe, url, label, mlist, req) -> dict:
    open_page(url)
    out = {}
    for ym, f, t in mlist:
        path, body = req(ym, f, t)
        out[ym] = safe(f"{label} {ym}", lambda path=path, body=body: call("POST", path, body))
    return out
