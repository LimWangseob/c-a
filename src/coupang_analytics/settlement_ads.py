"""광고비·밀크런 원천 월별 수집 — 1원 정산(D-116 ③④⑤). 조회·보고서 요청·받기만(광고 설정은 건드리지 않음).

실측(벅스 2026-10-26):
- 광고센터 일별 광고비 정산내역 = GraphQL getDailySettlement(기간, settlementDomain SELLER) — **날짜 × 캠페인** 소진 광고비·
  예산 초과 차감 후·**청구가능 광고비**(쿠팡이 주는 가장 작은 청구 단위 — 상품별 청구액은 없음). 7월 청구가능 378,188(7/12·13·14
  일예산 초과 750 차감) + 부가세 37,819 = 416,007 = 8/10~9/7 로켓그로스 광고비 공제 합 · 6월 244,347 = 6월분 공제 합(원 단위).
- 광고센터 매출 성장 광고 보고서(advertising.coupang.com, GraphQL /marketing-reporting/v2/graphql):
  getCampaignList(기간) → requestReport(일별·키워드·캠페인 ID 전부) → reportList(status completed) →
  GET /marketing-reporting/v2/api/excel-report?id=… (xlsx — 큰 보고서는 탭 구분 글자 text/csv 로 옴·report_xlsx 로 엑셀로 바꿔 저장). 칸 = 날짜·광고집행 옵션ID·광고비 등(견본 벅스 7월 378,986).
  ⚠ 보고서 광고비는 정산 소진액보다 날마다 2~9원 큼(끝전) → 상품 몫 = 날짜×캠페인 청구가능액 × 그날 보고서 옵션 광고비 비율(D-119).
- 윙 로켓그로스 밀크런 내역 엑셀 = GET /tenants/rfm-portal-2/excel/milkrun-settlement?searchYear&searchMonth&milkrunId&feeType —
  밀크런번호·픽업일·발생금액·세액·조정액 등(상품 없음 → 입고 내역 milkrunSeq 로 상품 수량과 이음, settlement_verify_collect).
달이 끝나고 SETTLE_DAYS 일 뒤부터 받는다(월말 계산·청구가능 확정 여유). 받은 파일은 다시 받지 않는다.
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import date, timedelta
from pathlib import Path

import openpyxl

from .settlement_evidence import month_windows
from .settlement_wing_api import SiteChangedError

GQL = "/marketing-reporting/v2/graphql"
MILK_EXCEL = "https://wing.coupang.com/tenants/rfm-portal-2/excel/milkrun-settlement?searchYear={y}&searchMonth={m}&milkrunId=&feeType="
PA_EXCEL = "https://advertising.coupang.com/marketing-reporting/v2/api/excel-report?id={id}"
SETTLE_DAYS = 3
FROM = date(2025, 11, 1)        # 받는 시작 달 — 2026 첫 지급에 걸친 2025-11분부터(D-166 · D-161 ④ 2025-12 에서 앞당김)
MAX_MONTHS = 2                  # 하루(한 번 실행) 계정당 받는 달 수 — 밀린 달은 최근 달부터 날마다 나눠서(판매 소급 하루 60일과 같은 방식·D-120)
_CAMPAIGNS = ("query GetCampaignListInBillboard($startDate: Int!, $endDate: Int!, $reportType: ReportType!) "
              "{ getCampaignList(startDate: $startDate, endDate: $endDate, reportType: $reportType) { id name } }")
_LIST = ("query ReportList($reportType: ReportType!, $page: Int!, $pageSize: Int!, $duration: Int!, $onlyScheduledReport: Boolean) "
         "{ reportList(data: {reportType: $reportType, page: $page, pageSize: $pageSize, duration: $duration, "
         "onlyScheduledReport: $onlyScheduledReport}) { reports { id requestDate startDate endDate dateGroup granularity "
         "campaignCount status } } }")
_DAILY = ("mutation DailySettlement($startDate: Int!, $endDate: Int!, $settlementDomain: SettlementDomain!) "
          "{ getDailySettlement(startDate: $startDate, endDate: $endDate, settlementDomain: $settlementDomain) { "
          "summary { total { deliveredAdcost deliveredAdcostAfterCap billableAmount totalFinalAmount } "
          "rocketGrowth { billableAmount vat totalFinalAmount } nonRod { billableAmount vat totalFinalAmount } } "
          "items { date campaignId campaignName adType deliveredAdcost deliveredAdcostAdj deliveredAdcostAfterCap "
          "promotionAdjustment billableAdjustment billableAmount } } }")
_REQUEST = ("mutation RequestReport($startDate: Int!, $endDate: Int!, $campaignIds: [ID], $reportType: ReportType!, "
            "$dateGroup: DateGroup!, $granularity: Granularity, $excludeIfNoClickCount: Boolean) { requestReport(data: "
            "{startDate: $startDate, endDate: $endDate, campaignIds: $campaignIds, reportType: $reportType, dateGroup: $dateGroup, "
            "granularity: $granularity, excludeIfNoClickCount: $excludeIfNoClickCount}) { id } }")


def due_months(start: date, today: date) -> list[tuple[str, date, date]]:
    """받을 달 — 시작 달부터, 끝난 지 SETTLE_DAYS 일이 지난 달까지(달 전체 기간)."""
    last = today - timedelta(days=SETTLE_DAYS + 1)
    return [(ym, date(f.year, f.month, 1), t) for ym, f, t in month_windows(date(start.year, start.month, 1), last)
            if (t + timedelta(days=1)).day == 1]


def _ad_done(folder: Path, acct: str, ym: str, none: set) -> bool:
    """광고센터 그 달 끝 = 광고정산 json + (캠페인 없음 | 매출성장광고 엑셀)."""
    return (folder / f"{acct}_광고정산_{ym}.json").exists() and (ym in none or (folder / f"{acct}_매출성장광고_{ym}.xlsx").exists())


def _left(folder: Path, acct: str, months: list, none: set) -> int:
    return sum(1 for ym, _f, _t in months if not ((folder / f"{acct}_밀크런_{ym}.xlsx").exists() and _ad_done(folder, acct, ym, none)))


def left_months(folder: Path, acct: str, start: date, today: date) -> int:
    """저장된 파일만 보고 남은 달 수(밀크런·광고센터 둘 다 받아야 그 달 끝) — collect 의 '남은 달'과 같은 판정 ·
    받기 없이 전 계정 다시 셈([실행 결과 종합] 남은 소급 — 로그인 못 한 계정 포함 · T-46 ⑤)."""
    state_p = Path(folder) / f"{acct}_광고.json"
    state = json.loads(state_p.read_text(encoding="utf-8")) if state_p.exists() else {}
    return _left(Path(folder), acct, due_months(start, today), set(state.get("캠페인 없음") or []))


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


def _report_cell(v: str):
    """글자 보고서 칸 → 숫자면 숫자(엑셀 보고서와 같게 — 정산서가 숫자 칸만 읽음)."""
    if not v:
        return None
    if re.fullmatch(r"-?\d[\d,]*(\.\d+)?", v):
        x = float(v.replace(",", ""))
        return int(x) if x.is_integer() else x
    return v


def report_xlsx(body: bytes) -> bytes:
    """매출 성장 광고 보고서 응답 → 엑셀 바이트. 큰 보고서 = 쿠팡이 탭 구분 글자로 줌(운용 PC 2026-11-03 실측) — 칸이 다르면 저장 안 함."""
    if body[:2] == b"PK":
        return body
    try:
        rows = list(csv.reader(io.StringIO(body.decode("utf-8-sig"), newline=""), delimiter="\t"))
    except UnicodeDecodeError as exc:
        raise SiteChangedError(f"광고 보고서 글자 응답을 못 읽음: {body[:60]!r}") from exc
    if not rows or not {"날짜", "캠페인 ID", "광고집행 옵션ID", "광고비"} <= set(rows[0]):
        raise SiteChangedError(f"광고 보고서 칸이 예상과 다름: {body[:60]!r}")
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet()
    ws.append(rows[0])
    for r in rows[1:]:
        ws.append([_report_cell(v) for v in r])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _gql(call, query: str, variables: dict) -> dict:
    r = call("POST", GQL, {"query": query, "variables": variables})
    if r.get("errors"):
        raise RuntimeError(f"광고센터 GraphQL 오류: {str(r['errors'])[:200]}")
    return r["data"]


def collect(call, get_bytes, folder: Path, acct: str, start: date, today: date, *, gap=lambda: None,
            max_months: int = MAX_MONTHS, get_report=None, fatal: tuple = ()) -> dict:
    """call(method, path, body) = 광고센터 화면 안 호출(처음 부를 때 광고센터를 열도록 호출부가 늦게 연결) ·
    get_bytes(url) = 로그인 세션으로 파일 받기 · get_report(url) = 보고서 받기(글자 응답 허용, 없으면 get_bytes) · gap() = 원격 요청마다 먼저 쉼(차단 방지). 받을 게 남은 달은 최근 달부터
    max_months 개만 — 밀크런(윙 주소)과 광고센터(광고정산·매출성장광고)는 **따로** 세고 따로 실패(한쪽 오류가 다른 쪽 달을 막지 않음 ·
    D-245 · 실측 11-15 hellojin 광고센터 500 → 밀크런 10달 빔). 실패 = '실패' 목록에 사유를 남기고 그쪽만 이번 실행 멈춤 · fatal(차단)은 올림.
    반환 = 요약 {받을 것, 요청, 기다림, 받음, 캠페인 없음, 실패, 남은 달(이번 실행 뒤 다 받지 못한 달), 파일(이번에 저장한 경로)}."""
    folder.mkdir(parents=True, exist_ok=True)
    state_p = folder / f"{acct}_광고.json"
    state = json.loads(state_p.read_text(encoding="utf-8")) if state_p.exists() else {}
    none = set(state.get("캠페인 없음") or [])
    out: dict = {"받을 것": [], "요청": [], "기다림": [], "받음": [], "캠페인 없음": [], "실패": [], "남은 달": 0, "파일": []}
    reports: list | None = None

    raw_call, raw_bytes, raw_report = call, get_bytes, get_report or get_bytes

    def call_(method, path, body):
        gap()
        return raw_call(method, path, body)

    def bytes_(url):
        gap()
        return raw_bytes(url)

    def report_(url):
        gap()
        return raw_report(url)

    def milk_p(ym: str) -> Path:
        return folder / f"{acct}_밀크런_{ym}.xlsx"

    def ad_done(ym: str) -> bool:
        return _ad_done(folder, acct, ym, none)

    def milk_month(ym: str, f: date, t: date) -> None:
        milk_p(ym).write_bytes(bytes_(MILK_EXCEL.format(y=f.year, m=f.month)))
        out["파일"].append(milk_p(ym))

    def ad_month(ym: str, f: date, t: date) -> None:
        nonlocal reports
        daily = folder / f"{acct}_광고정산_{ym}.json"
        if not daily.exists():
            d = _gql(call_, _DAILY, {"startDate": _ymd(f), "endDate": _ymd(t), "settlementDomain": "SELLER"})["getDailySettlement"]
            daily.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            out["파일"].append(daily)
        pa = folder / f"{acct}_매출성장광고_{ym}.xlsx"
        if pa.exists() or ym in none:
            return
        out["받을 것"].append(ym)
        camps = _gql(call_, _CAMPAIGNS, {"startDate": _ymd(f), "endDate": _ymd(t), "reportType": "pa"})["getCampaignList"] or []
        if not camps:
            none.add(ym)
            out["캠페인 없음"].append(ym)
            return
        if reports is None:
            reports = _gql(call_, _LIST, {"reportType": "pa", "page": 1, "pageSize": 50, "duration": 90,
                                          "onlyScheduledReport": False})["reportList"]["reports"] or []
        rep = pick_report(reports, ym, len(camps))
        if rep is None:
            _gql(call_, _REQUEST, {"startDate": _ymd(f), "endDate": _ymd(t), "campaignIds": [c["id"] for c in camps],
                                   "reportType": "pa", "dateGroup": "daily", "granularity": "keyword",
                                   "excludeIfNoClickCount": False})
            out["요청"].append(ym)
        elif rep.get("status") == "completed":
            pa.write_bytes(report_xlsx(report_(PA_EXCEL.format(id=rep["id"]))))
            out["받음"].append(ym)
            out["파일"].append(pa)
        else:
            out["기다림"].append(ym)
    months = list(reversed(due_months(start, today)))
    for what, fn, todo in (("밀크런", milk_month, [m for m in months if not milk_p(m[0]).exists()]),
                           ("광고센터", ad_month, [m for m in months if not ad_done(m[0])])):
        for ym, f, t in todo[:max_months]:
            try:
                fn(ym, f, t)
            except fatal:
                raise
            except Exception as exc:  # noqa: BLE001 — 그쪽(밀크런|광고센터)만 이번 실행 멈춤 · 사유 그대로 남김
                out["실패"].append(f"{what} {ym}: {exc.__class__.__name__}: {str(exc)[:120]}")
                break
    out["남은 달"] = _left(folder, acct, months, none)
    state_p.write_text(json.dumps({**state, "캠페인 없음": sorted(none)}, ensure_ascii=False), encoding="utf-8")
    return out
