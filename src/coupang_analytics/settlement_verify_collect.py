"""정산 검증 자료 수집(조회만) — 쿠팡의 다른 장부로 우리 정산 파일·지급액을 대조하기 위한 원자료.

소유자 요구(2026-10-08): 통장 없이 정산 금액을 검증. 실측(nicoable 2026-10-08)으로 확인한 쿠팡 메뉴·주소:
| 장부 | 화면(먼저 열어야 함) | 주소 |
|---|---|---|
| 로켓그로스 월렛 입출금·잔액 | 로켓그로스 정산현황 | POST /tenants/rfm/v2/wallet/histories/search/api · GET …/wallet/balance/api |
| 윙 매출내역(월별) | 정산 > 매출내역 | POST /tenants/msf/wing/api/purchase-report/list |
| 윙 부가세 신고내역 | 정산 > 부가세 신고내역 | POST /tenants/msf/wing/api/payment-method/list {from,to=YYYYMM} |
| 로켓그로스 부가세 | 로켓그로스 부가세 화면 | GET /tenants/rfm/api/settlements/vat/search?fromYearMonth&toYearMonth |
| 보류목록 / 추가지급(월별) | 정산 > 보류목록 / 추가지급 | POST …/payment-pending-report/list · …/additional-payment-report/list |
⚠ 매출내역 등은 그 화면을 연 상태에서 불러야 한다(다른 화면에서 부르면 504 — 실측). 오늘 이후 날짜를 넣으면 504(실측)
→ 월 끝은 어제까지. 서버 일시 오류(ServerBusy)는 그 항목만 '조회 실패'로 남기고 다음 항목 진행.
개인정보(계좌·예금주)는 저장하지 않는다.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from .settlement_wing_api import RG_URL, ServerBusy, SiteChangedError

_W = "https://wing.coupang.com"
SALES_URL = f"{_W}/tenants/finance/wing/contentsurl/sales-report"
PENDING_URL = f"{_W}/tenants/finance/wing/contentsurl/payments-pending"
ADDITIONAL_URL = f"{_W}/tenants/msf/wing/view/additional-payment-report-view"
WING_VAT_URL = f"{_W}/tenants/finance/wing/contentsurl/proportion-sales"
RG_VAT_URL = f"{_W}/tenants/rfm/settlements/vat-report"
PURCHASE = "/tenants/msf/wing/api/purchase-report/list"
PENDING = "/tenants/msf/wing/api/payment-pending-report/list"
ADDITIONAL = "/tenants/msf/wing/api/additional-payment-report/list"
WING_VAT = "/tenants/msf/wing/api/payment-method/list"
RG_VAT = "/tenants/rfm/api/settlements/vat/search"
WALLET_HIST = "/tenants/rfm/v2/wallet/histories/search/api"
WALLET_BAL = "/tenants/rfm/v2/wallet/balance/api"
WALLET_FROM = date(2025, 1, 1)          # 월렛 장부(입금−인출=잔액) 대조용 — 소급 시작보다 넉넉히
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


def collect(call, open_page, start: date, today: date, *, note=lambda m: None, gap=lambda: None) -> dict:
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
    data["pending"] = _monthly(call, open_page, safe, PENDING_URL, "보류목록", mlist,
                               lambda ym, f, t: (PENDING, {"from": f.isoformat(), "to": t.isoformat(), "year": f.year,
                                                           "month": f.month, "commerceType": "3PM",
                                                           "searchType": "PENDING_DATE", "pendingType": "ALL",
                                                           "pendingYn": "ALL", "page": 1, "pageSize": 100}))
    data["additional"] = _monthly(call, open_page, safe, ADDITIONAL_URL, "추가지급", mlist,
                                  lambda ym, f, t: (ADDITIONAL, {"fromDate": f.isoformat(), "toDate": t.isoformat(),
                                                                 "taxInvoiceIssueType": None, "requestStatusType": None,
                                                                 "orderId": None, "page": 1, "pageSize": 100}))
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


def _monthly(call, open_page, safe, url, label, mlist, req) -> dict:
    open_page(url)
    out = {}
    for ym, f, t in mlist:
        path, body = req(ym, f, t)
        out[ym] = safe(f"{label} {ym}", lambda path=path, body=body: call("POST", path, body))
    return out
