"""WING 정산 데이터 주소(화면 뒤에서 쓰는 API) — 정산 일정 조회·'엑셀 다운로드 요청'·다운로드 목록·받기.

화면 클릭 대신 **로그인된 WING 페이지 안에서 화면과 같은 주소를 같은 형식으로** 부른다(실측 2026-10-06, 사무실·
wellbing1107 — 화면에서 한 번씩 눌러 주소·본문 확인 후 직접 호출로 같은 결과 확인). 이유: 화면 기간 입력이
반영되지 않아(1월로 조회해도 기본 9~10월 표가 그대로) 엉뚱한 줄을 요청할 위험 → 주소는 기간을 정확히 받는다.
요청 수는 화면과 같다(조회 1·요청 1·목록 1·받기 1) — 차단 위험이 늘지 않음.

| 용도 | 윙 | 로켓그로스 |
|---|---|---|
| 정산 일정 | POST /tenants/msf/wing/api/payment-report/list | POST /tenants/rfm/v2/settlements/status/api |
| 요청 | POST …/msf/wing/api/common/excel/revenue-detail/request | POST …/rfm/v2/settlements/request-download/api |
| 목록 | GET …/msf/wing/api/common/excel/list | POST …/rfm/v2/settlements/download-list/api |
| 받기 | 목록의 downloadUrl (GET) | POST …/rfm/v2/settlements/download/api/v2 → {url}(S3) GET |

모양이 예상과 다르면 조용히 넘어가지 않고 SiteChangedError. 순수 변환(*_events·*_rows·*_body)은 오프라인 검증.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from .settlement_jobs import DownloadRow, Job, SettleEvent

WING_URL = "https://wing.coupang.com/tenants/msf/wing/view/payment-report-view"
RG_URL = "https://wing.coupang.com/tenants/rfm/settlements/status-new"
WING_EVENTS = "/tenants/msf/wing/api/payment-report/list"
WING_REQUEST = "/tenants/msf/wing/api/common/excel/revenue-detail/request"
WING_LIST = "/tenants/msf/wing/api/common/excel/list"
RG_EVENTS = "/tenants/rfm/v2/settlements/status/api"
RG_REQUEST = "/tenants/rfm/v2/settlements/request-download/api"
RG_LIST = "/tenants/rfm/v2/settlements/download-list/api"
RG_GET = "/tenants/rfm/v2/settlements/download/api/v2"
WING_EXCEL = "MSF_PAYMENT_REVENUE_DETAIL"
_WING_KIND = {"W": "주정산", "R": "최종액"}        # transactionCycleCode(실측: 주정산 70%=W·월별 최종액 30%=R)
_RG_REPORT = {"판매수수료": "CATEGORY_TR"}          # sellerReportType(실측) — 다른 리포트는 확인 후 추가
_KST = timedelta(hours=9)


class SiteChangedError(Exception):
    """응답 모양이 예상과 다름 — 추측으로 진행하지 않고 중단."""


class ApiBlocked(Exception):
    """403·429·HTML 응답 — 차단 의심(그 계정 즉시 중단)."""


# ── 순수 변환(오프라인 검증) ──────────────────────────────────────
def _kst_date(text: str) -> date:
    """'2026-09-06T15:00:00.000Z'(UTC) → 한국 날짜 2026-09-07. 날짜만이면 그대로."""
    s = str(text).strip()
    if "T" not in s:
        return date.fromisoformat(s)
    return (datetime.fromisoformat(s.replace("Z", "+00:00")) + _KST).date()


def _need(d: dict, *keys: str, where: str):
    miss = [k for k in keys if k not in d]
    if miss:
        raise SiteChangedError(f"{where} 응답에 {miss} 없음 — 받은 칸: {sorted(d)[:20]}")
    return [d[k] for k in keys]


def wing_events(resp: dict, account: str) -> list[SettleEvent]:
    """윙 정산현황 응답 → 정산 일정(지급일·유형·구매확정기간). 정산상태와 무관하게 기간이 끝난 건 파일이 있다."""
    (reports,) = _need(resp, "paymentReports", where="윙 정산현황")
    out = []
    for r in reports:
        pay, code, f, t = _need(r, "payDate", "transactionCycleCode", "recognitionFrom", "recognitionTo",
                                where="윙 정산현황 줄")
        if code not in _WING_KIND:
            raise SiteChangedError(f"윙 모르는 정산주기 코드: {code!r} (지급일 {pay})")
        out.append(SettleEvent(account, "윙", _WING_KIND[code], date.fromisoformat(pay), date.fromisoformat(f),
                               date.fromisoformat(t)))
    return out


def rg_events(resp: dict, account: str) -> list[SettleEvent]:
    """로켓그로스 정산현황 응답 → 정산 일정. 날짜는 UTC 로 오므로 한국 날짜로. ref = 요청에 쓰는 settlementGroupKey."""
    (reports,) = _need(resp, "settlementStatusReports", where="로켓그로스 정산현황")
    out = []
    for r in reports:
        sd, ps, pe, ratio, cycle, key = _need(
            r, "settlementDate", "settlementPeriodStartDate", "settlementPeriodEndDate", "settlementRatio",
            "settlementCycle", "settlementGroupKey", where="로켓그로스 정산현황 줄")
        if cycle != "WEEKLY":
            raise SiteChangedError(f"로켓그로스 모르는 정산주기: {cycle!r} ({key})")
        kind = "최종액" if int(float(ratio)) == 30 else "주정산"
        out.append(SettleEvent(account, "로켓그로스", kind, _kst_date(sd), _kst_date(ps), _kst_date(pe), ref=key))
    return out


def wing_events_body(start: date, end: date) -> dict:
    return {"searchDateType": "PAY_DATE", "fromDate": start.isoformat(), "toDate": end.isoformat(),
            "transactionCycle": "ALL", "paymentStatus": "ALL", "detailSearchKey": "orderId"}


def rg_events_body(start: date, end: date) -> dict:
    """한국 날짜 [start, end] → 화면이 보내는 UTC 시각(한국 0시 = 전날 15시 UTC). 끝은 end 다음날 0시까지."""
    return {"startDate": f"{start - timedelta(days=1)}T15:00:00.000Z", "endDate": f"{end}T15:00:00.000Z",
            "searchDateType": "PAYMENT"}


def wing_request_body(j: Job) -> dict:
    rng = {"start": j.period_start, "end": j.period_end}
    return {"excelType": WING_EXCEL, "recognitionDateRange": rng, "searchDateType": "CONFIRM_DATE",
            "searchDateRange": dict(rng)}


def rg_request_body(j: Job, now_ms: int) -> dict:
    if not j.ref:
        raise SiteChangedError(f"로켓그로스 요청에 정산 묶음 키(settlementGroupKey)가 없음: {j.period_start}~{j.period_end}")
    if j.report not in _RG_REPORT:
        raise SiteChangedError(f"로켓그로스 리포트 종류 코드 미확인: {j.report}")
    return {"sellerReportType": _RG_REPORT[j.report], "requestTime": str(now_ms), "settlementGroupKeys": [j.ref],
            "locale": "ko"}


def wing_request_id(resp: dict) -> str:
    ok, data = _need(resp, "success", "data", where="윙 다운로드 요청")
    if ok is not True:
        raise SiteChangedError(f"윙 다운로드 요청 거절: {resp.get('reason')!r}")
    return str(data)


def rg_request_id(resp: dict) -> str:
    rid, dup = _need(resp, "requestId", "duplicateRequest", where="로켓그로스 다운로드 요청")
    if not rid:
        raise SiteChangedError(f"로켓그로스 다운로드 요청에 requestId 없음 (중복요청={dup})")
    return str(rid)


def wing_list_rows(items: list) -> list[DownloadRow]:
    """윙 다운로드 목록 → DownloadRow(handle=downloadUrl). 주문상세(MSF_PAYMENT_REVENUE_DETAIL) 외 메뉴는 무시."""
    from .settlement_jobs import parse_condition
    out = []
    for it in items:
        typ, status, started, url, jitems = _need(it, "excelType", "status", "startedAt", "downloadUrl", "jsonItems",
                                                  where="윙 다운로드 목록 줄")
        if typ != WING_EXCEL:
            continue
        cond = " ".join(f"{x.get('key')}:{x.get('value')}" for x in json.loads(jitems or "[]"))
        ps, pe = parse_condition(cond)
        out.append(DownloadRow("윙", datetime.fromisoformat(started), str(status), "주문상세", ps, pe, handle=url))
    return out


def rg_list_body(start: datetime, end: datetime) -> dict:
    return {"requestTimeFrom": str(int(start.timestamp() * 1000)), "requestTimeTo": str(int(end.timestamp() * 1000))}


def rg_list_rows(items: list) -> list[DownloadRow]:
    """로켓그로스 다운로드 목록 → DownloadRow(req_id=requestId, handle=requestTime — 받기에 씀)."""
    names = {v: k for k, v in _RG_REPORT.items()}
    out = []
    for it in items:
        rid, rt, status, typ = _need(it, "requestId", "requestTime", "downloadStatus", "sellerReportType",
                                     where="로켓그로스 다운로드 목록 줄")
        out.append(DownloadRow("로켓그로스", datetime.fromtimestamp(int(rt) / 1000), str(status), names.get(typ, typ),
                               handle=str(rt), req_id=str(rid)))
    return out


def month_windows(start: date, end: date) -> list[tuple[date, date]]:
    """[start, end] 를 달 단위 조회 구간으로(조회 1회 = 1달)."""
    out, cur = [], start
    while cur <= end:
        nxt = (cur.replace(day=1) + timedelta(days=32)).replace(day=1)
        out.append((cur, min(end, nxt - timedelta(days=1))))
        cur = nxt
    return out


# ── 호출(라이브 전용·사무실) ──────────────────────────────────────
_CALL_JS = """
async ([method, path, body]) => {
  const x = decodeURIComponent((document.cookie.match(/XSRF-TOKEN=([^;]+)/) || [])[1] || '');
  const h = {'content-type': 'application/json', 'x-xsrf-token': x};
  if (path.startsWith('/tenants/rfm/')) h['x-rfm-portal2-request-id'] = crypto.randomUUID();
  const r = await fetch(path, {method, headers: h, body: body === null ? undefined : JSON.stringify(body)});
  return {status: r.status, ctype: r.headers.get('content-type') || '', text: await r.text()};
}
"""


def call(page, method: str, path: str, body: dict | None = None):
    """로그인된 WING 페이지 안에서 화면과 같은 방식으로 호출 → JSON. 403·429·HTML=ApiBlocked, 그 밖 오류=SiteChangedError."""
    r = page.evaluate(_CALL_JS, [method, path, body])
    st, text = r["status"], r["text"]
    if st in (403, 429) or text.lstrip().startswith("<"):
        raise ApiBlocked(f"{path} → {st} ({r['ctype']}) {text[:80]!r}")
    if st != 200:
        raise SiteChangedError(f"{path} → {st} {text[:200]!r}")
    try:
        return json.loads(text)
    except ValueError as exc:
        raise SiteChangedError(f"{path} 응답이 JSON 아님: {text[:120]!r}") from exc
