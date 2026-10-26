"""광고비 원천 월별 수집 — 1원 정산(D-116 ③④). 조회·보고서 요청·받기만(광고 설정은 건드리지 않음).

실측(벅스 2026-10-26):
- 윙 로켓그로스 광고비 내역 엑셀 = GET /tenants/rfm-portal-2/excel/cmg-settlement/{연}/{월} — 캠페인마다 광고비·**청구가능 광고비**
  (7월 378,188 → 부가세 37,819 → 청구 대상액 416,007 = 8/10~9/7 로켓그로스 지급 줄 광고비 공제 합과 원 단위 일치).
- 광고센터 매출 성장 광고 보고서(advertising.coupang.com, GraphQL /marketing-reporting/v2/graphql):
  getCampaignList(기간) → requestReport(일별·키워드·캠페인 ID 전부) → reportList(status completed) →
  GET /marketing-reporting/v2/api/excel-report?id=… (xlsx). 칸 = 날짜·광고집행 옵션ID·광고비 등(견본 벅스 7월 378,986).
  ⚠ 보고서 광고비 합(378,986)은 청구가능액(378,188)과 다름 → 상품 몫 = 캠페인 청구가능액을 보고서 옵션별 광고비 비율로 나눔.
달이 끝나고 SETTLE_DAYS 일 뒤부터 받는다(월말 계산·청구가능 확정 여유). 받은 파일은 다시 받지 않는다.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .settlement_evidence import month_windows

GQL = "/marketing-reporting/v2/graphql"
CMG_EXCEL = "https://wing.coupang.com/tenants/rfm-portal-2/excel/cmg-settlement/{y}/{m}"
PA_EXCEL = "https://advertising.coupang.com/marketing-reporting/v2/api/excel-report?id={id}"
SETTLE_DAYS = 3
_CAMPAIGNS = ("query GetCampaignListInBillboard($startDate: Int!, $endDate: Int!, $reportType: ReportType!) "
              "{ getCampaignList(startDate: $startDate, endDate: $endDate, reportType: $reportType) { id name } }")
_LIST = ("query ReportList($reportType: ReportType!, $page: Int!, $pageSize: Int!, $duration: Int!, $onlyScheduledReport: Boolean) "
         "{ reportList(data: {reportType: $reportType, page: $page, pageSize: $pageSize, duration: $duration, "
         "onlyScheduledReport: $onlyScheduledReport}) { reports { id requestDate startDate endDate dateGroup granularity "
         "campaignCount status } } }")
_REQUEST = ("mutation RequestReport($startDate: Int!, $endDate: Int!, $campaignIds: [ID], $reportType: ReportType!, "
            "$dateGroup: DateGroup!, $granularity: Granularity, $excludeIfNoClickCount: Boolean) { requestReport(data: "
            "{startDate: $startDate, endDate: $endDate, campaignIds: $campaignIds, reportType: $reportType, dateGroup: $dateGroup, "
            "granularity: $granularity, excludeIfNoClickCount: $excludeIfNoClickCount}) { id } }")


def due_months(start: date, today: date) -> list[tuple[str, date, date]]:
    """받을 달 — 시작 달부터, 끝난 지 SETTLE_DAYS 일이 지난 달까지(달 전체 기간)."""
    last = today - timedelta(days=SETTLE_DAYS + 1)
    return [(ym, date(f.year, f.month, 1), t) for ym, f, t in month_windows(date(start.year, start.month, 1), last)
            if (t + timedelta(days=1)).day == 1]


def _ymd(d: date) -> int:
    return int(f"{d:%Y%m%d}")


def pick_report(reports: list, ym: str, n_campaigns: int) -> dict | None:
    """그 달 전체·일별·키워드·캠페인 수가 같은 보고서 중 최신(실패 제외)."""
    y, m = int(ym[:4]), int(ym[4:])
    end = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
    hit = [r for r in reports if r.get("startDate") == _ymd(date(y, m, 1)) and r.get("endDate") == _ymd(end)
           and r.get("dateGroup") == "daily" and r.get("granularity") == "keyword"
           and r.get("campaignCount") == n_campaigns and r.get("status") != "error"]
    return max(hit, key=lambda r: int(r["id"])) if hit else None


def _gql(call, query: str, variables: dict) -> dict:
    r = call("POST", GQL, {"query": query, "variables": variables})
    if r.get("errors"):
        raise RuntimeError(f"광고센터 GraphQL 오류: {str(r['errors'])[:200]}")
    return r["data"]


def collect(call, get_bytes, folder: Path, acct: str, start: date, today: date) -> dict:
    """call(method, path, body) = 광고센터 화면 안 호출(처음 부를 때 광고센터를 열도록 호출부가 늦게 연결) ·
    get_bytes(url) = 로그인 세션으로 파일 받기. 반환 = 요약 {받을 것, 요청, 기다림, 받음, 캠페인 없음}."""
    folder.mkdir(parents=True, exist_ok=True)
    state_p = folder / f"{acct}_광고.json"
    state = json.loads(state_p.read_text(encoding="utf-8")) if state_p.exists() else {}
    none = set(state.get("캠페인 없음") or [])
    out: dict = {"받을 것": [], "요청": [], "기다림": [], "받음": [], "캠페인 없음": []}
    reports: list | None = None
    for ym, f, t in due_months(start, today):
        cmg = folder / f"{acct}_광고비내역_{ym}.xlsx"
        if not cmg.exists():
            cmg.write_bytes(get_bytes(CMG_EXCEL.format(y=f.year, m=f.month)))
        pa = folder / f"{acct}_매출성장광고_{ym}.xlsx"
        if pa.exists() or ym in none:
            continue
        out["받을 것"].append(ym)
        camps = _gql(call, _CAMPAIGNS, {"startDate": _ymd(f), "endDate": _ymd(t), "reportType": "pa"})["getCampaignList"] or []
        if not camps:
            none.add(ym)
            out["캠페인 없음"].append(ym)
            continue
        if reports is None:
            reports = _gql(call, _LIST, {"reportType": "pa", "page": 1, "pageSize": 50, "duration": 90,
                                         "onlyScheduledReport": False})["reportList"]["reports"] or []
        rep = pick_report(reports, ym, len(camps))
        if rep is None:
            _gql(call, _REQUEST, {"startDate": _ymd(f), "endDate": _ymd(t), "campaignIds": [c["id"] for c in camps],
                                  "reportType": "pa", "dateGroup": "daily", "granularity": "keyword",
                                  "excludeIfNoClickCount": False})
            out["요청"].append(ym)
        elif rep.get("status") == "completed":
            pa.write_bytes(get_bytes(PA_EXCEL.format(id=rep["id"])))
            out["받음"].append(ym)
        else:
            out["기다림"].append(ym)
    state_p.write_text(json.dumps({**state, "캠페인 없음": sorted(none)}, ensure_ascii=False), encoding="utf-8")
    return out
