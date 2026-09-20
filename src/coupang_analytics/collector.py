"""판매분석 상품별 리포트 자동 다운로드 + 파싱 (Q1).

로그인된 실제 Chrome(browser.WingBrowser 또는 CDP 연결 page)에서 판매분석을 열고
'엑셀 다운로드 > 상품별 판매 리포트'를 눌러 리포트를 받는다.
날짜는 URL 파라미터: ?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD.
다운로드는 비동기(서버 생성→폴링) blob 방식이라 Playwright download 이벤트로 안 잡힌다.
→ CDP로 다운로드 폴더를 지정하고 폴더에 새 xlsx 가 생기는지 감시한다.
page 는 **실제 로그인 세션의 페이지**여야 한다(쿠키 주입 세션은 데이터 API 가 막혀 UI 미로드).

**진단 로그**: 모든 단계에 log 를 남겨, 실패 시 어디서 막혔는지(XHR 미수신/버튼 미발견/다운로드 미생성/
다른 폴더로 저장 등) 원인 파악이 되게 한다. log 는 호출부(pipeline)가 UI 로그로 넘긴다.
"""
from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout

from . import config
from .input_list import Option, Product
from .report import OptionMetric, parse_by_option

_DISCOVERED_DIR = Path("data") / "discovered"

_SALES_URL = ("https://wing.coupang.com/tenants/business-insight/sales-analysis"
              "?start_date={f}&end_date={t}")
_LOAD_WAIT_MS = 6000       # 데이터 안정화 대기
_DOWNLOAD_WAIT_S = 150     # 비동기 리포트 생성·다운로드 폴링(최대 초)

# ── 데이터 API 직접 조회(사람 클릭 없이) ──────────────────────────
# 판매분석 화면이 표를 채울 때 쓰는 그 API(vi-detail-search)를 **같은 로그인 세션에서 same-origin
# fetch**로 직접 호출한다(자동완성 kw_suggest 와 동일한 정식 방식 — 위장로그인 아님). 실측 확정(2026-09-07):
#   POST /tenants/rfm-ss/api/business-insight/vi-detail-search
#   body {startDate,endDate,registrationTypes:["NORMAL","RFM"],pageNumber,pageSize,sortBy,sortOrder,includeSoldVICount}
#   응답 {vendorItems:[{vendorItemDetails{vendorItemId,productName,itemName,itemId},
#         businessInsightsMetricsResponse{totalPageViews,totalUnitsSold,totalUniqueVisitor,…}}], paginationDetails}
# 헤더: axios withCredentials 라 XSRF-TOKEN 쿠키를 x-xsrf-token 으로 되보내야 한다(쿠키에서 읽어 넣음).
_SALES_API = "https://wing.coupang.com/tenants/rfm-ss/api/business-insight/vi-detail-search"
# 로켓그로스 재고현황(판매가능 재고수량) — 재고관리 페이지가 부르는 데이터 API(라이브 캡처 확정).
_INVENTORY_API = "https://wing.coupang.com/tenants/rfm-inventory/inventory-health-dashboard/search"
# 상품조회/수정(전 상품·전 옵션 나열) — vid 출처. '상품조회/수정' 화면이 부르는 데이터 API(라이브 캡처 확정 2026-09-20).
#   POST /tenants/seller-web/v2/vendor-inventory/search
#   응답 봉투 {success, data:{productList:[…], pagination:{page,countPerPage,totalCount,totalPages}}, message}
#   리스팅=productName·vendorInventoryId·registrationType·productStatus·status·vendorInventoryItems[]
#   옵션=vendorItemId(=vid)·itemName·registrationType·valid·status·salePrice·vendorInventoryItemId
# vi-detail-search 는 **당일 판매활동 상품만** 잡히지만 이 API 는 판매 유무 무관 전 상품을 준다 → vid 출처.
_VENDOR_INVENTORY_API = "https://wing.coupang.com/tenants/seller-web/v2/vendor-inventory/search"
_PAGE_SIZE = 20            # 실측 정상값(캡처와 동일). 크게(200) 주면 서버가 400 → 검증된 20 유지, 페이지네이션으로 커버
_INV_PAGE_SIZE = 100       # 재고 search 1차 페이지 크기(검증된 안전값). pageNumber 무시(안 넘어감) 시 아래 큰 pageSize 로 전량 재요청
_INV_PAGE_MAX = 2000       # 페이지 미진행 시 전량 1회 재요청할 최대 pageSize(주석: 재고 search 는 큰 pageSize 허용·실제개수로 축소)

# axios withCredentials 라 XSRF-TOKEN 쿠키를 x-xsrf-token 으로 되보내야 한다(쿠키에서 읽어 넣음).
_POST_JSON_JS = """
async (payload) => {
  const m = document.cookie.match(/(?:^|;\\s*)XSRF-TOKEN=([^;]+)/);
  const token = m ? decodeURIComponent(m[1]) : '';
  const r = await fetch('%s', {
    method: 'POST', credentials: 'include',
    headers: {'content-type': 'application/json',
              'accept': 'application/json, text/plain, */*',
              'x-xsrf-token': token},
    body: JSON.stringify(payload),
  });
  return {status: r.status, body: await r.text(), hasToken: !!token};
}
"""
_FETCH_JS = _POST_JSON_JS % _SALES_API
_INV_FETCH_JS = _POST_JSON_JS % _INVENTORY_API
_VI_FETCH_JS = _POST_JSON_JS % _VENDOR_INVENTORY_API

_VI_PAGE_SIZE = 50         # 상품조회 countPerPage(캡처와 동일값). page 1→totalPages 반복.
# 전량 수집 핵심 파라미터(캡처 확정): exposureStatus="ALL"(아이템위너 누락 방지)·salesMethod="ALL"·
# productStatus=["ALL"]·displayDeletedProduct=false. sortMethod 는 결과 순서만 바꾼다.
_VI_SEARCH_BASE = {
    "searchKeywordType": "ALL", "searchKeywords": "", "salesMethod": "ALL",
    "productStatus": ["ALL"], "exposureStatus": "ALL", "exposureStatuses": [],
    "displayDeletedProduct": False, "displayCategoryCodes": [],
    "saleEndDateSearchType": "ALL", "shippingFeeSearchType": "ALL", "shippingMethod": "ALL",
    "stockSearchType": "ALL", "bundledShippingSearchType": "ALL", "upBundleSearchOption": "ALL",
    "qualityEnhanceTypes": [], "coupangAttributeOptimized": False,
    "listingStartTime": None, "listingEndTime": None,
    "sortMethod": "SORT_BY_ITEM_LEVEL_UNIT_SOLD", "locale": "ko_KR",
    "countPerPage": _VI_PAGE_SIZE,
}


class SalesFetchError(Exception):
    """판매분석 데이터 API 직접조회 실패(비200·파싱실패 등). 호출부가 로그 후 엑셀 다운로드로 폴백."""


class InventoryFetchError(Exception):
    """로켓그로스 재고현황 API 직접조회 실패(비200·파싱실패 등). 계약 계정에만 존재."""


class VendorInventoryFetchError(Exception):
    """상품조회/수정(vendor-inventory/search) 직접조회 실패(비200·success=false·파싱실패 등). vid 출처."""


@dataclass
class VendorInventoryOption:
    """상품조회/수정 응답의 옵션(vendorInventoryItems[]) 레벨 필드.

    vendor_item_id 가 vid(정체성) — 이후 시계열 추적의 앵커. registration_type 으로 둘다 판별
    (한 리스팅에 RFM·NORMAL 옵션 혼재 → RFM 만 채택). ⚠ valid(VALID/INVALID)의 **의미는 미확정**
    (캡처엔 값만·정의 없음). 삭제 상품은 요청 displayDeletedProduct=false 로 이미 제외되므로 INVALID≠폐기일
    가능성이 큼 — 실데이터로 의미 파악 전엔 필터하지 않는다(라이브 로그로 관측)."""
    vendor_item_id: str          # 옵션ID = vid(정체성 앵커)
    item_name: str               # 옵션명(색상/사이즈/등급 라벨)
    registration_type: str       # NORMAL(판매자배송)/RFM(로켓그로스) — 옵션 단위 둘다 판별
    valid: str = ""              # VALID / INVALID (의미 미확정 — 라이브 관측 대상, 필터 안 함)
    status: str = ""            # 옵션 승인/상태
    sale_price: int = 0          # 판매가
    vendor_inventory_item_id: str = ""   # 등록옵션ID(내부)


@dataclass
class VendorInventoryListing:
    """상품조회/수정 응답의 리스팅(productList[]) 레벨 필드 + 옵션 목록.

    product_name=등록상품명(대장 매칭키) · vendor_inventory_id=등록상품ID(내부, 옵션 그룹핑키).
    ⚠노출상품ID(productId)는 이 응답에 없음 → 그룹핑은 vendor_inventory_id 로(리스팅 단위).
    product_status=ON_SALE/PARTIAL_ON_SALE/판매중지 — NORMAL 포함 전상품 판매상태(경고 개선 소스)."""
    product_name: str            # 등록상품명(대장 매칭키)
    vendor_inventory_id: str     # 등록상품ID(내부) = 옵션 그룹핑키
    registration_type: str       # 리스팅 레벨 등록타입
    product_status: str          # ON_SALE / PARTIAL_ON_SALE(부분판매중) / 판매중지
    status: str = ""            # APPROVED 등
    options: list[VendorInventoryOption] = field(default_factory=list)


def kind_of(registration_types) -> str:
    """옵션들의 registration_type 목록 → 상품 구분(순수·테스트 가능).

    RFM=로켓그로스, NORMAL=판매자배송. 전부 RFM=로켓그로스 · RFM 없음=판매자배송 · **RFM과 NORMAL 섞임=둘 다**
    (한 상품을 로켓그로스와 판매자배송으로 동시 운영). NORMAL 명시가 있어야 '둘 다'로 본다(빈 값은 판매자배송으로).
    """
    types = list(registration_types)
    has_rfm = any(t == "RFM" for t in types)
    has_seller = any(t == "NORMAL" for t in types)
    if has_rfm and has_seller:
        return config.KIND_BOTH
    return config.KIND_CONTRACT if has_rfm else config.KIND_PERSONAL


def sale_status_of(product_status: str) -> str:
    """상품조회/수정 `productStatus` 원문 → 판매상태 문자열('판매중'/'부분판매중'/'판매중지'). 빈값이면 '' (미상).

    **화면(상품조회/수정)의 판매/승인 상태와 일치하는 신뢰 소스**(라이브 실측 2026-09-20 nicoable/sg0141n).
    실제 원문 enum: **ON_SALE=판매중 · PARTIAL_ON_SALE=부분판매중 · SUSPENDED=판매중지**. 그 외(DRAFT=임시저장·
    REJECTED=승인반려 등 미판매 상태)는 '판매중'이 아니므로 apply_sale_status 판정상 **판매중지로 묶는다**
    (경고는 대장=판매중지·쿠팡=판매중일 때만 뜨므로 안전). NORMAL(판매자배송) 상품도 이 필드로 커버된다.
    ⚠ 계정 전체가 SUSPENDED 로 나올 수 있음(wellbing1107 처럼 '신규 등록 불가' 제한 계정) — 필드 정상."""
    s = (product_status or "").strip()
    if not s:
        return ""
    u = s.upper()
    if "PARTIAL" in u or s.startswith("부분"):
        return "부분판매중"
    if u in ("ON_SALE", "ONSALE", "SALE", "SELLING", "ON") or s == "판매중":
        return "판매중"
    return "판매중지"


def sale_status_by_vid(listings: list["VendorInventoryListing"], log=None) -> dict[str, str]:
    """{옵션ID(vid): 판매상태문자열} — 상품조회 productStatus(**전 상품·판매자배송 포함**)를 옵션 vid 로 편다.

    한 리스팅의 모든 옵션 vid 는 그 리스팅 productStatus 를 공유(리스팅 단위 상태). 값이 빈 리스팅은 제외.
    관측한 **원문 productStatus → 해석** 대응표를 로그로 남긴다(계정별 실제 enum 확인용). 화면과 일치하는
    판매상태 소스([[sale_status_of]])."""
    out: dict[str, str] = {}
    seen: dict[str, str] = {}
    for listing in listings:
        st = sale_status_of(listing.product_status)
        seen[listing.product_status or "(빈값)"] = st or "(미상)"
        if not st:
            continue
        for o in listing.options:
            if o.vendor_item_id:
                out[o.vendor_item_id] = st
    if log and seen:
        log("  [상품조회] 판매상태(productStatus→해석): "
            + ", ".join(f"{k}={v}" for k, v in seen.items()))
    return out


def _num(value) -> int:
    """지표 정수화(응답은 3.0 같은 실수). None/빈값은 0."""
    if value in (None, ""):
        return 0
    return int(round(float(value)))


def _parse_vendor_items(items: list[dict]) -> dict[str, OptionMetric]:
    """vi-detail-search 의 vendorItems → {옵션ID(vendorItemId): OptionMetric}.

    노출건수=totalPageViews · 판매건수=totalUnitsSold · 방문자건수=totalUniqueVisitor
    (라이브 실측 대조로 확정 — 2026-09-07 gbseller808). 옵션ID 없는 항목은 건너뛴다.
    """
    out: dict[str, OptionMetric] = {}
    for vi in items:
        d = vi.get("vendorItemDetails") or {}
        m = vi.get("businessInsightsMetricsResponse") or {}
        oid = str(d.get("vendorItemId") or "").strip()
        if not oid:
            continue
        out[oid] = OptionMetric(
            option_id=oid,
            product_name=str(d.get("productName") or "").strip(),
            option_name=str(d.get("itemName") or "").strip(),
            item_id=str(d.get("itemId") or "").strip(),
            views=_num(m.get("totalPageViews")),
            sales=_num(m.get("totalUnitsSold")),
            visitors=_num(m.get("totalUniqueVisitor")),
            registration_type=str(d.get("registrationType") or "").strip(),
        )
    return out


def fetch_sales_details(page, date_from: str, date_to: str, log=None) -> dict[str, OptionMetric]:
    """판매분석 데이터 API(vi-detail-search)를 **직접 fetch**해 {옵션ID: OptionMetric} 반환(클릭·다운로드 없음).

    page 는 **로그인된 wing.coupang.com 세션 페이지**여야 한다(same-origin + 세션쿠키 + XSRF 토큰).
    페이지네이션(paginationDetails.totalPages)을 따라 전 페이지를 모은다. 비200/파싱실패는 SalesFetchError.
    """
    log = log or (lambda m: None)
    all_items: list[dict] = []
    page_num = 0
    while True:
        payload = {"startDate": date_from, "endDate": date_to,
                   "registrationTypes": ["NORMAL", "RFM"],
                   "pageNumber": page_num, "pageSize": _PAGE_SIZE,
                   "sortBy": "GMV", "sortOrder": "DESC", "includeSoldVICount": True}
        res = page.evaluate(_FETCH_JS, payload)
        status, body = res.get("status"), res.get("body", "")
        if status != 200:
            raise SalesFetchError(
                f"vi-detail-search 응답 status={status}"
                f"{' (XSRF 토큰 없음)' if not res.get('hasToken') else ''} — page {page_num}"
                f" · 응답본문: {str(body)[:300]}")
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise SalesFetchError(f"vi-detail-search 응답 JSON 파싱 실패: {exc}") from exc
        items = data.get("vendorItems") or []
        all_items.extend(items)
        pg = data.get("paginationDetails") or {}
        total_pages = int(pg.get("totalPages") or 1)
        log(f"  [수집] vi-detail-search p{page_num + 1}/{total_pages} — 옵션 {len(items)}개 "
            f"(누적 {len(all_items)}, 총 {pg.get('totalResults', '?')})")
        if not items or page_num + 1 >= total_pages:
            break
        page_num += 1
    return _parse_vendor_items(all_items)


def _parse_inventory(vi_props: list[dict]) -> dict[str, int]:
    """재고 search 의 viProperties → {옵션ID(vendorItemId): 판매가능 재고수량(orderableQuantity)}.

    orderableQuantity = 주문가능(판매가능) 재고수량 = 서식의 '재고현황'(라이브 캡처 확정, bf0621).
    한 상품(productId)에 vendorItem 여러 개일 수 있어 호출부가 상품 단위로 합산한다.
    """
    out: dict[str, int] = {}
    for vp in vi_props:
        oid = str(vp.get("vendorItemId") or "").strip()
        if not oid:
            continue
        inv = vp.get("inventoryDetails") or {}
        out[oid] = _num(inv.get("orderableQuantity"))
    return out


def _parse_inventory_roster(vi_props: list[dict]) -> dict[str, str]:
    """재고 search 의 viProperties → {옵션ID(vendorItemId): 등록상품명}. **판매 무관 전 로켓그로스 상품**.

    상품명 = creturnConfigViewDto.productName(우선) 또는 listingDetails.vendorInventoryName(폴백).
    그로스 상품은 판매 0이어도 재고 목록에 있어 vid·상품명을 준다(라이브 캡처 확인, bf0621) → vid 보강 소스."""
    out: dict[str, str] = {}
    for vp in vi_props:
        oid = str(vp.get("vendorItemId") or "").strip()
        if not oid:
            continue
        cr = vp.get("creturnConfigViewDto") or {}
        ld = vp.get("listingDetails") or {}
        name = str(cr.get("productName") or ld.get("vendorInventoryName") or "").strip()
        if name:
            out[oid] = name
    return out


def _parse_inventory_status(vi_props: list[dict]) -> dict[str, bool]:
    """재고 search 의 viProperties → {옵션ID(vendorItemId): 판매중지여부(isSaleSuspended)}.

    listingDetails.isSaleSuspended = True → 그 옵션 판매중지, False → 판매중(라이브 캡처 확정).
    한 상품(productId)에 옵션(vid) 여러 개면 호출부가 상품단위로 합쳐 판매중/부분판매중/판매중지를 판정한다.
    필드가 없는 옵션(옛 응답/개인상품)은 넣지 않는다(미상 → 경고 안 뜸)."""
    out: dict[str, bool] = {}
    for vp in vi_props:
        oid = str(vp.get("vendorItemId") or "").strip()
        if not oid:
            continue
        ld = vp.get("listingDetails") or {}
        susp = ld.get("isSaleSuspended")
        if isinstance(susp, bool):
            out[oid] = susp
    return out


def fetch_inventory(page, log=None) -> tuple[dict[str, int], dict[str, str], dict[str, bool]]:
    """로켓그로스 재고현황 API(inventory-health-dashboard/search)를 **직접 fetch**.

    반환: ({옵션ID: 판매가능 재고수량}, {옵션ID: 등록상품명}, {옵션ID: 판매중지여부}). 상품명 맵은
    **판매 무관 vid 보강 소스**(그로스 상품은 판매 0이어도 재고 목록에 있어 vid·상품명을 준다 → 미매칭
    대장 상품 vid 보강에 사용). 판매중지여부 맵은 대장↔쿠팡 판매상태 불일치 경고에 쓴다(isSaleSuspended).
    page 는 **로그인된 wing.coupang.com 세션 페이지**(same-origin + 세션쿠키 + XSRF). 계약(RFM) 계정 전용
    — 개인(NORMAL) 계정은 로켓그로스 재고가 없어 빈 dict(정상). 비200/파싱실패는 InventoryFetchError.
    페이지네이션: pageNumber 로 넘기다가 **안 넘어가면(재고 API가 pageNumber 무시)** 큰 pageSize 로 전량 1회 재요청.
    ⚠ 상품별 재고를 빠짐없이 잡기 위함 — 재고 적은 옵션이 정렬 하위로 밀려 상위 100 밖에 있으면 그 상품 재고현황이 공란이 되던 문제 해결.
    """
    log = log or (lambda m: None)
    names: dict[str, str] = {}   # {vid: 등록상품명} — 판매 무관 그로스 상품 roster(vid 보강용)
    status: dict[str, bool] = {}  # {vid: isSaleSuspended} — 대장↔쿠팡 판매상태 불일치 경고용

    def _fetch(page_size: int, page_num: int) -> tuple[list, int]:
        payload = {"paginationRequest": {"pageSize": page_size, "pageNumber": page_num,
                                         "searchAfterSortValues": None},
                   "hiddenStatus": "VISIBLE",
                   "sort": [{"sortParameter": "ORDERABLE_QUANTITY", "sortDirection": "DESCENDING"}],
                   "rrqContext": {"source": "IHD", "eventType": "RRQ_SEEN", "metadata": "{}"}}
        res = page.evaluate(_INV_FETCH_JS, payload)
        status, body = res.get("status"), res.get("body", "")
        if status != 200:
            raise InventoryFetchError(
                f"inventory search 응답 status={status}"
                f"{' (XSRF 토큰 없음)' if not res.get('hasToken') else ''} — page {page_num}"
                f" · 응답본문: {str(body)[:300]}")
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise InventoryFetchError(f"inventory search 응답 JSON 파싱 실패: {exc}") from exc
        pg = data.get("paginationResponse") or {}
        return data.get("viProperties") or [], int(pg.get("totalNumberOfElements") or 0)

    out: dict[str, int] = {}
    page_num = 0
    total = 0
    while True:
        props, total = _fetch(_INV_PAGE_SIZE, page_num)
        if page_num == 0 and props:
            # vid 보강용 진단(1회): 재고 응답이 상품명/ID를 담는지 확인. 필드'명'만 로그(값 아님=민감정보 X).
            s0 = props[0]
            log(f"  [재고·진단] viProperty 필드: {sorted(s0.keys())}")
            for k, v in s0.items():
                if isinstance(v, dict):
                    log(f"  [재고·진단]   .{k} 하위: {sorted(v.keys())}")
            hit = [c for c in ("productName", "productId", "itemName", "itemId", "vendorItemName", "skuId")
                   if c in s0 or any(isinstance(v, dict) and c in v for v in s0.values())]
            log(f"  [재고·진단] 상품식별 후보 필드: {hit or '없음 — vid 보강엔 다른 소스 필요'}")
        before = len(out)
        out.update(_parse_inventory(props))
        names.update(_parse_inventory_roster(props))
        status.update(_parse_inventory_status(props))
        total = total or len(out)
        log(f"  [재고] search p{page_num + 1} — {len(props)}개 (누적 {len(out)}/{total})")
        if not props or len(out) >= total or len(out) == before:
            break            # 빈 페이지 / 목표 도달 / 페이지 미진행(새 항목 0개)
        page_num += 1

    # pageNumber 가 안 먹혀 상위 일부만 모였고 아직 남았으면 → 큰 pageSize 로 전량 1회 재요청(커서 대신).
    if len(out) < total:
        big = min(total, _INV_PAGE_MAX)
        try:
            props, _ = _fetch(big, 0)
        except InventoryFetchError as exc:   # 큰 pageSize 거부 → 상위분 유지(회귀 없음)
            log(f"  [재고] ⚠ 전량 재요청 실패(pageSize {big}) — 상위 {len(out)}/{total}개만 유지 · {str(exc)[:80]}")
            return out, names, status
        full = _parse_inventory(props)
        if len(full) > len(out):
            log(f"  [재고] 전량 재요청(pageSize {big}) → {len(full)}개 확보(이전 상위 {len(out)}개)")
            return full, _parse_inventory_roster(props), _parse_inventory_status(props)
        log(f"  [재고] ⚠ 전량 재요청도 {len(full)}개 — 상위 {len(out)}/{total}개만 유지(무한루프 방지)")
    return out, names, status


def _parse_vendor_inventory(product_list: list[dict]) -> list[VendorInventoryListing]:
    """vendor-inventory/search 의 productList → [VendorInventoryListing].

    옵션은 **필터 없이 그대로** 담는다(valid=INVALID 포함) — valid 의미가 미확정이라 필터/합산 판단은
    다운스텝으로 미룬다(수집 단계는 데이터를 있는 그대로 반영·조용한 폴백 금지). vendor_item_id 없는 옵션만 건너뛴다."""
    out: list[VendorInventoryListing] = []
    for p in product_list:
        options: list[VendorInventoryOption] = []
        for it in (p.get("vendorInventoryItems") or []):
            vid = str(it.get("vendorItemId") or "").strip()
            if not vid:
                continue
            options.append(VendorInventoryOption(
                vendor_item_id=vid,
                item_name=str(it.get("itemName") or "").strip(),
                registration_type=str(it.get("registrationType") or "").strip(),
                valid=str(it.get("valid") or "").strip(),
                status=str(it.get("status") or "").strip(),
                sale_price=_num(it.get("salePrice")),
                vendor_inventory_item_id=str(it.get("vendorInventoryItemId") or "").strip(),
            ))
        out.append(VendorInventoryListing(
            product_name=str(p.get("productName") or "").strip(),
            vendor_inventory_id=str(p.get("vendorInventoryId") or "").strip(),
            registration_type=str(p.get("registrationType") or "").strip(),
            product_status=str(p.get("productStatus") or "").strip(),
            status=str(p.get("status") or "").strip(),
            options=options,
        ))
    return out


def fetch_vendor_inventory(page, log=None) -> list[VendorInventoryListing]:
    """상품조회/수정 데이터 API(vendor-inventory/search)를 **직접 fetch**해 전 상품·전 옵션 목록 반환.

    vi-detail-search 가 당일 판매활동 상품만 잡는 것과 달리 이 API 는 **판매 유무 무관 계정의 전 등록상품**을
    나열한다 → 당일 판매 0 상품도 등록상품명 매칭으로 정확한 vid 확보 가능(vid 출처). NORMAL(판매자배송)
    상품도 포함해 판매상태(productStatus)를 준다.

    page 는 **로그인된 wing.coupang.com 세션 페이지**여야 한다(same-origin + 세션쿠키 + XSRF 토큰).
    페이지네이션(data.pagination.totalPages)을 따라 page 1→N 을 모은다. 비200/success=false/파싱실패는
    VendorInventoryFetchError. ⚠재고(stockQuantity)는 이 소스에서 쓰지 않는다(등록시 임의값·부정확) —
    재고는 fetch_inventory(RFM API)만 사용."""
    log = log or (lambda m: None)
    all_listings: list[VendorInventoryListing] = []
    page_num = 1
    while True:
        payload = dict(_VI_SEARCH_BASE, page=page_num)
        res = page.evaluate(_VI_FETCH_JS, payload)
        status, body = res.get("status"), res.get("body", "")
        if status != 200:
            raise VendorInventoryFetchError(
                f"vendor-inventory/search 응답 status={status}"
                f"{' (XSRF 토큰 없음)' if not res.get('hasToken') else ''} — page {page_num}"
                f" · 응답본문: {str(body)[:300]}")
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise VendorInventoryFetchError(f"vendor-inventory/search 응답 JSON 파싱 실패: {exc}") from exc
        if data.get("success") is False:
            raise VendorInventoryFetchError(
                f"vendor-inventory/search success=false — page {page_num} · message={data.get('message')!r}")
        d = data.get("data") or {}
        product_list = d.get("productList") or []
        listings = _parse_vendor_inventory(product_list)
        all_listings.extend(listings)
        pg = d.get("pagination") or {}
        total_pages = int(pg.get("totalPages") or 1)
        opt_count = sum(len(l.options) for l in listings)
        log(f"  [상품조회] vendor-inventory/search p{page_num}/{total_pages} — 상품 {len(listings)}개"
            f"(옵션 {opt_count}, 누적 상품 {len(all_listings)}, 총 {pg.get('totalCount', '?')})")
        if not product_list or page_num >= total_pages:
            break
        page_num += 1
    return all_listings


def _folder_snapshot(d: Path) -> list[str]:
    """폴더 내 파일명+크기 목록(진단용)."""
    try:
        return [f"{p.name}({p.stat().st_size}B)" for p in sorted(d.iterdir()) if p.is_file()][-8:]
    except Exception as exc:
        return [f"<목록실패:{exc.__class__.__name__}>"]


def _fresh_download_dir(out: Path, log) -> Path:
    """이번 다운로드 전용 빈 하위폴더를 만든다.

    쿠팡은 매 계정 **같은 파일명**으로 리포트를 내려주는데, 직전 계정 파일이 폴더에 남아 있으면
    이름 충돌로 새 파일이 안 생기거나(감지 실패), 그 파일을 우리가 파싱하며 잠가 삭제도 막힌다
    (PermissionError, 라이브 실측). → 매 다운로드를 **격리된 빈 폴더**로 받아 충돌·잠금을 원천 차단.
    파싱 직후 discover 가 그 폴더를 바로 지우므로 평소엔 쌓이지 않는다. 남은 옛 폴더가 있으면 조용히
    정리(실행 중 OS 가 잠깐 파일을 잡아 실패해도 무해 — 다음 기회에 지워짐, 로그로 시끄럽게 하지 않음).
    """
    for old in out.glob("dl_*"):
        shutil.rmtree(old, ignore_errors=True)
    dl_dir = out / f"dl_{time.strftime('%Y%m%d_%H%M%S')}"
    dl_dir.mkdir(parents=True, exist_ok=True)
    return dl_dir


def _wait_new_xlsx(dl_dir: Path, timeout: float, log, events, page) -> Path:
    """빈 전용 폴더(dl_dir)에 완료된 .xlsx 가 나타날 때까지 대기.

    폴더가 비어 있어 새 파일=이번 다운로드로 확정. 대기 중 폴더/이벤트를 6초마다 로그,
    타임아웃 시 이벤트·기본 다운로드폴더·페이지 본문까지 남겨 원인을 좁힌다.
    """
    start = time.time()
    deadline = start + timeout
    log(f"  [수집] 다운로드 대기 시작(최대 {int(timeout)}s) — 감시 폴더: {dl_dir.name}")
    last_report = 0.0
    while time.time() < deadline:
        done = list(dl_dir.glob("*.xlsx"))
        part = list(dl_dir.glob("*.crdownload"))
        if done:
            newest = max(done, key=lambda p: p.stat().st_mtime)
            size = newest.stat().st_size
            time.sleep(1.0)
            if size > 0 and newest.stat().st_size == size:      # 크기 안정 = 완료
                log(f"  [수집] ✅ 다운로드 감지: {newest.name} ({size}B, {int(time.time()-start)}s 만에)")
                return newest
        if time.time() - last_report > 6:                       # 6초마다 진행 로그
            state = "다운로드중(.crdownload)" if part else ("완료대기" if events else "미시작")
            log(f"  [수집] …대기 {int(time.time()-start)}s · 상태={state} · 폴더={_folder_snapshot(dl_dir)} · 이벤트={events or '없음'}")
            last_report = time.time()
        time.sleep(1.0)
    # 타임아웃 — 원인 단서 최대한 남김
    log(f"  [수집] ⏱ 다운로드 타임아웃({int(timeout)}s). 폴더 최종={_folder_snapshot(dl_dir)}")
    log(f"  [수집] 다운로드 이벤트 전체: {events or '없음 → 클릭이 다운로드를 트리거하지 못함(버튼/메뉴 오클릭 의심)'}")
    home_dl = Path.home() / "Downloads"
    other = [p.name for p in home_dl.glob("*.xlsx") if p.stat().st_mtime >= start - 5] if home_dl.exists() else []
    if other:
        log(f"  [수집] ⚠ 리포트가 기본 다운로드 폴더로 샜을 수 있음: {home_dl} → {other[-5:]} (CDP 경로 미적용 의심)")
    log(f"  [수집] 페이지 본문(앞 180자): {_body_head(page)}")
    raise TimeoutError("리포트 다운로드 대기 시간 초과")


def download_report(page, date_from: str, date_to: str,
                    out_dir: str | Path = "data/reports", log=None) -> Path:
    """판매분석 상품별 리포트 다운로드 → 저장 파일 경로. 각 단계 로그."""
    log = log or (lambda m: None)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dl_dir = _fresh_download_dir(out, log)             # ① 격리 폴더: 잠금·이름충돌 차단
    client = page.context.new_cdp_session(page)
    # ② 다운로드 이벤트 구독 — 클릭이 실제 다운로드를 트리거했는지/완료됐는지 즉시 로그
    events: list[str] = []

    def _on_begin(p):
        msg = f"시작:{p.get('suggestedFilename', '?')}"
        events.append(msg)
        log(f"  [수집] ▷ 다운로드 {msg} (url={str(p.get('url',''))[:60]})")

    def _on_progress(p):
        st = p.get("state", "?")
        if st in ("completed", "canceled"):
            events.append(f"진행:{st}")
            log(f"  [수집] ▷ 다운로드 진행={st}")

    client.send("Page.enable")
    client.send("Browser.setDownloadBehavior", {
        "behavior": "allow", "downloadPath": str(dl_dir.resolve()), "eventsEnabled": True})
    client.on("Page.downloadWillBegin", _on_begin)
    client.on("Browser.downloadProgress", _on_progress)
    client.send("Page.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(dl_dir.resolve())})
    log(f"  [수집] CDP 다운로드 폴더 지정: {dl_dir.resolve()}")

    url = _SALES_URL.format(f=date_from, t=date_to)
    log(f"  [수집] 판매분석 이동: {url}")
    try:  # 데이터 API 응답 대기 → 데이터 로드 보장
        with page.expect_response(lambda r: "vi-detail-search" in r.url, timeout=25000):
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        log("  [수집] vi-detail-search 응답 수신(데이터 로드됨)")
    except PWTimeout:
        log(f"  [수집] ⚠ vi-detail-search 25s 내 미수신 — 데이터 미로드 가능. 현재 URL: {page.url}")

    try:
        btn = page.get_by_text("엑셀 다운로드").first
        btn.wait_for(state="visible", timeout=30000)
    except PWTimeout:
        log(f"  [수집] ✖ '엑셀 다운로드' 버튼 30s 내 못 찾음 — 페이지 구조 변경/데이터 없음 의심. "
            f"URL: {page.url} · 본문: {_body_head(page)}")
        raise
    log("  [수집] '엑셀 다운로드' 버튼 발견 → 데이터 안정화 대기 후 클릭")
    page.wait_for_timeout(_LOAD_WAIT_MS)
    btn.click(no_wait_after=True)                     # 드롭다운(페이지 이동 아님)
    log("  [수집] '엑셀 다운로드' 클릭 완료 → 드롭다운 메뉴 대기")

    try:
        item = page.get_by_text("상품별 판매 리포트").first
        item.wait_for(state="visible", timeout=10000)
    except PWTimeout:
        log(f"  [수집] ✖ '상품별 판매 리포트' 메뉴 10s 내 못 찾음(드롭다운 미노출?). 본문: {_body_head(page)}")
        raise
    log("  [수집] '상품별 판매 리포트' 메뉴 발견 → 클릭(다운로드 트리거)")
    item.click(no_wait_after=True)                    # 비동기 다운로드 트리거
    return _wait_new_xlsx(dl_dir, _DOWNLOAD_WAIT_S, log, events, page)


def _body_head(page) -> str:
    try:
        return page.inner_text("body")[:180].replace("\n", " ")
    except Exception as exc:
        return f"<본문읽기실패:{exc.__class__.__name__}>"


def _uniquify_labels(raw: list[str]) -> list[str]:
    """라벨 문자열들을 유일하게(중복이면 '_' 덧붙임). 단일 옵션 처리는 호출부 몫."""
    labels, seen = [], set()
    for r in raw:
        lbl = r
        while lbl in seen:
            lbl += "_"
        seen.add(lbl)
        labels.append(lbl)
    return labels


def _unique_labels(opts: list[OptionMetric]) -> list[str]:
    """옵션 라벨을 유일하게. 단일 옵션은 "" (상품 전체), 복수는 옵션명(빈/중복은 ID 보정)."""
    if len(opts) == 1:
        return [""]
    return _uniquify_labels([o.option_name or o.option_id[-4:] for o in opts])


def _display_title(product_name: str, opts: list[OptionMetric]) -> str:
    """고객이 보는 전체 노출제목을 복원한다.

    리포트 '상품명'(product_name)은 짧게 잘려오는 경우가 있어(예: '…화로'로 '테이블' 누락),
    옵션명(option_name)의 **첫 콤마 앞 세그먼트**(= 제목, 그 뒤는 옵션·규격)를 후보로 삼아
    가장 긴 제목을 쓴다. 예: '…화로 테이블, 우드, 48cm' → '…화로 테이블'.
    """
    cands = [product_name]
    for o in opts:
        seg = (o.option_name or "").split(",")[0].strip()
        if seg:
            cands.append(seg)
    return max(cands, key=len)


def discover(page, date_from: str, date_to: str, log=None) -> tuple[list[Product], dict[str, OptionMetric]]:
    """상품·옵션·vendorItemId 발견 + 옵션별 판매지표 반환.

    기본은 **데이터 API 직접조회**(fetch_sales_details — 사람 클릭·다운로드 없음). API가 실패하면
    사유를 로그로 남기고 **엑셀 다운로드로 폴백**(조용한 폴백 아님 — 명시 로그). 각 단계 로그.
    """
    log = log or (lambda m: None)
    log(f"  [수집] 판매분석 발견 시작 (기간 {date_from}~{date_to}) — 데이터 API 직접조회")
    try:
        metrics = fetch_sales_details(page, date_from, date_to, log)
    except SalesFetchError as exc:
        log(f"  [수집] ⚠ 데이터 API 직접조회 실패 — {exc} → 엑셀 다운로드로 폴백")
        path = download_report(page, date_from, date_to, log=log)
        size = path.stat().st_size
        metrics = parse_by_option(path)
        shutil.rmtree(path.parent, ignore_errors=True)   # 파싱 끝난 다운로드 폴더 즉시 정리
        log(f"  [수집] (폴백) 리포트 파싱: 옵션(행) {len(metrics)}개 (파일 {size}B)")
    else:
        log(f"  [수집] 데이터 API 직접조회 완료: 옵션 {len(metrics)}개")
    if not metrics:
        # 헤더는 정상인데 데이터 행이 0 → 파서 문제 아님. 원인을 명확히 진단.
        today = date.today().isoformat()
        if date_to >= today:
            log(f"  [수집] ⚠ 데이터 행 0개 — 조회 종료일({date_to})이 오늘({today}) 이상입니다. "
                "쿠팡 판매분석은 **당일 데이터를 익일 이후** 생성하므로 오늘/미래 구간은 빈 리포트가 정상. "
                "→ 어제 이전 날짜로 다시 실행하세요.")
        else:
            log(f"  [수집] ⚠ 데이터 행 0개 — 해당 기간({date_from}~{date_to}) 판매분석 데이터가 없습니다"
                "(그 기간 노출·판매 기록이 없거나 계정에 활성 상품 없음).")
    products = _products_from_metrics(metrics)
    for p in products:
        # 입력 파일의 상품명이 아니라 **쿠팡에서 실제 판매 중인 상품 제목**(API productName)을 분석 대상으로 쓴다.
        oms = [metrics[vid] for opt in p.options for vid in opt.vendor_item_ids if vid in metrics]
        v = sum(o.views for o in oms); s = sum(o.sales for o in oms); vi = sum(o.visitors for o in oms)
        log(f"  [상품] 쿠팡 판매상품 제목(키워드 분석 대상): {p.title}  [{p.kind}]")
        log(f"         (옵션 {len(p.options)}개 · 해당일 노출 {v} · 판매 {s} · 방문 {vi})")
    log(f"  [수집] 발견 상품 {len(products)}개 (옵션 {len(metrics)})")
    return products, metrics


def _products_from_metrics(metrics: dict) -> list[Product]:
    """{옵션ID(vid): OptionMetric} → 상품 목록(등록상품ID/상품명으로 그룹, 옵션=vid). 지표 로깅 없음.

    discover(지표+로그)와 fetch_sales_roster(vid 보강 전용, 지표 미사용)가 공유하는 순수 그룹핑."""
    groups: dict[str, list[OptionMetric]] = {}
    for m in metrics.values():
        groups.setdefault(m.item_id or m.product_name, []).append(m)
    out: list[Product] = []
    for opts in groups.values():
        labels = _unique_labels(opts)
        options = [Option(label=lbl, vendor_item_ids=[o.option_id]) for lbl, o in zip(labels, opts)]
        title = _display_title(opts[0].product_name, opts)
        kind = kind_of(o.registration_type for o in opts)   # 로켓그로스/판매자배송/둘 다(API 자동 판별)
        out.append(Product(name=opts[0].product_name, options=options, title=title, kind=kind))
    return out


def products_from_vendor_inventory(listings: list[VendorInventoryListing],
                                   log=None) -> list[Product]:
    """상품조회/수정 리스팅 → **발견 Product 목록**(대장 매칭용). vi-detail-search 대체 vid 출처.

    리스팅 1개 = Product 1개(그룹키=vendor_inventory_id — 이 응답에 productId 없음). 옵션(vid)=Option.
    당일 판매 0 상품도 나오므로(전 상품 나열) 대장 상품 vid 를 누락 없이 확보한다.

    **둘다(RFM+NORMAL 혼재) 리스팅은 로켓그로스(RFM) 옵션만** 채택한다(vid·통계를 로켓그로스로 —
    소유자 §0-00000; 같은 옵션이 NORMAL·RFM 2 vid 로 존재해 판매자배송분을 빼야 중복 제거). 단 구분(kind)은
    **원본 전 옵션으로 판별**해 '둘다'를 보존한다(재고행 대상·표기 유지). vid 없는 옵션·옵션 0개 리스팅은 제외.
    ⚠재고(stockQuantity)는 이 소스에서 안 씀 — 재고는 fetch_inventory(RFM API)만.
    """
    log = log or (lambda m: None)
    out: list[Product] = []
    dropped_norm = 0
    skipped = 0
    for listing in listings:
        if not listing.options:
            skipped += 1
            continue
        kind = kind_of(o.registration_type for o in listing.options)   # 전 옵션 판별(둘다 보존)
        opts = listing.options
        if kind == config.KIND_BOTH:
            rfm = [o for o in listing.options if o.registration_type == "RFM"]
            dropped_norm += len(listing.options) - len(rfm)
            opts = rfm or listing.options            # 안전판: RFM 0개면(이론상 없음) 원본 유지
        labels = [""] if len(opts) == 1 else _uniquify_labels(
            [o.item_name or o.vendor_item_id[-4:] for o in opts])
        options = [Option(label=lbl, vendor_item_ids=[o.vendor_item_id])
                   for lbl, o in zip(labels, opts)]
        name = listing.product_name
        out.append(Product(name=name, options=options, title=name, kind=kind))
    if dropped_norm:
        log(f"  [상품조회] 둘다 상품 판매자배송(NORMAL) 옵션 {dropped_norm}개 제외(vid=로켓그로스만)")
    if skipped:
        log(f"  [상품조회] 옵션 없는 리스팅 {skipped}개 제외")
    # valid=INVALID 옵션 관측 로그 — 이 필드의 **의미가 미확정**(캡처엔 값만·정의 없음)이라, 실데이터로
    # 뜻을 파악하려고 개수+예시(상품명·옵션명·리스팅 판매상태)를 남긴다(라이브에서 INVALID 가 무엇인지 판단).
    invalid = [(l.product_name, o.item_name, l.product_status)
               for l in listings for o in l.options if o.valid == "INVALID"]
    if invalid:
        ex = [f"{nm[:14]}·{it[:10]}·상태={ps}" for nm, it, ps in invalid[:3]]
        log(f"  [상품조회] valid=INVALID 옵션 {len(invalid)}개(의미 미확정·라이브 확인용) 예: {ex}")
    log(f"  [상품조회] 발견 상품 {len(out)}개(판매 무관 전 상품·vid 출처)")
    return out


def fetch_sales_roster(page, date_from: str, date_to: str, log=None) -> list[Product]:
    """최근 기간 판매분석에서 **vid·상품명 roster 만** 확보(지표는 호출부가 쓰지 않음 — vid 보강 전용).

    당일(D-1) 판매·방문이 0이라 당일 조회에 안 잡힌 대장 상품의 vid 를, 넓은 기간(config.SALES_VID_WINDOW_DAYS)
    으로 확보하기 위함. vi-detail-search 는 그 기간에 조회/방문/판매가 있은 상품을 반환한다. ⚠ 여기서 얻은 지표는
    넓은기간 합계라 **쓰지 않는다**(당일 지표만 기록). 비200/파싱실패는 SalesFetchError(호출부가 로그 후 계속)."""
    log = log or (lambda m: None)
    products = _products_from_metrics(fetch_sales_details(page, date_from, date_to, log))
    log(f"  [수집·보강] 최근기간({date_from}~{date_to}) roster {len(products)}개 상품(vid 확보용, 지표 미반영)")
    return products


def save_discovered(account_id: str, products: list[Product]) -> Path:
    """발견한 상품·옵션·vendorItemId 를 사이드카 JSON 으로 저장(원본 입력 미변경)."""
    _DISCOVERED_DIR.mkdir(parents=True, exist_ok=True)
    data = [{"name": p.name,
             "options": [{"label": o.label, "vendorItemId": o.vendor_item_ids} for o in p.options]}
            for p in products]
    path = _DISCOVERED_DIR / f"{account_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
