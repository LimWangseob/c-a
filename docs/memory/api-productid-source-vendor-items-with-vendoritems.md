---
name: api-productid-source-vendor-items-with-vendoritems
description: "노출상품ID(productId)의 유일 범용 소스=WING vendor-inventory-items-with-vendorItems/{vendorInventoryId} GET (2026-09-28 라이브 실측 확정)"
metadata:
  node_type: memory
  type: reference
  originSessionId: 3588291b-3435-4968-8471-8410129d1b69
  modified: 2026-09-28T08:01:35.340Z
---

**노출상품ID(공개 productId)를 vendorItemId별로 주는 WING API를 라이브 실측 확정(2026-09-28, 소유자 DevTools 캡처).**

**엔드포인트**:
`GET https://wing.coupang.com/tenants/seller-web/v2/vendor-inventory/vendor-inventory-items-with-vendorItems/{vendorInventoryId}?hasProgressiveDiscountRule=true&queryNonVariationJustificationProof=true&queryMpnProof=true`
- 경로 파라미터 `{vendorInventoryId}` = 등록상품ID(상품 레벨). **상품조회(vendor-inventory/search) 응답의 `vendorInventoryId` 필드로 이미 확보** → 상품마다 1회 호출.
- 메서드 GET · 헤더: 로그인 세션 쿠키 + `x-xsrf-token`(XSRF-TOKEN 쿠키). 상품조회와 동일 인증.

**응답**: `{success, data:[…], message}`. data = **옵션(vendorItem)별 1개**. 옵션마다:
- `vendorInventoryId` · `vendorInventoryItemId` · `vendorItemId`(옵션ID) · **`productId`(=화면 노출상품ID)** · `itemId`
- `registrationType`(NORMAL/RFM) · `stockQuantity` · `salePrice`/`originalPrice`/`finalPrice`/`couponAmount` · `status`
- `displaySalesInfoDto.extData`: **`WINNER_AT`(아이템위너)** vs **`LOSER_AT`(위너 아님)** + `BUYBOX_ID` + `LATEST_SALES_AT` → **아이템위너 상태도 이 API로 판정 가능**.
- 이미지(`vendorInventoryItemImageDtos`: REPRESENTATION/DETAIL) · 속성(색상·사이즈) 등.

**핵심 의의(#1/#2 상품링크)**:
- **productId 는 상품조회(search) 응답엔 없음**(전수 확정) → 재고/판매분석 `listingDetails.productId` 또는 **이 엔드포인트**에서만.
- 재고/판매분석은 로켓그로스 재고·판매 있는 상품만 커버 → **순수 판매자배송·무판매 상품은 productId 공백**(검색링크 폴백).
- **이 엔드포인트는 판매방식·판매여부 무관 전 옵션 productId 제공**(실측: NORMAL vid 95462666213·RFM vid 95468098380 모두 productId=9555958648 동일) → **모든 상품의 정상 상품링크(`/vp/products/{productId}?vendorItemId={vid}`) 생성 가능**.
- 같은 노출상품(둘다=NORMAL+RFM)은 두 옵션이 **동일 productId 공유**(=한 노출 상품).

**✅도입 완료(2026-09-28·소유자 "전 상품" 선택)**: `collector.fetch_product_ids(page, vendor_inventory_ids, log)` 신설(GET 헬퍼 `_GET_JSON_JS`·URL `_VI_ITEMS_URL`·상품마다 1 GET·비200/파싱실패는 로그 명시+그 상품만 건너뜀·전체 비중단). `pipeline_sales._discover_products`가 상품조회 listings 의 `vendor_inventory_id` 전량으로 호출→`_pid_by_vid(inv_pids, metrics, item_pids)` **병합 우선순위=전상품(item_pids) > 재고 > 판매분석**. 기존 `workbook.product_url`(pid+vid→`/vp/products/{pid}?vendorItemId={vid}`)이 그대로 정규 링크 생성. 핀 verify_offline[26]. 비용=계정당 N GET(WING 로그인 API라 ③순위 SERP 같은 Akamai 차단위험 낮음). ⚠라이브 확인·재배포 남음. SSOT=collector.py·pipeline_sales.py.

관련 [[feature-vid-source-from-product-list]]·[[analysis-output8-260927]]·[[verify-by-data-not-status]]·[[sales-data-api-vi-detail-search]]·[[inventory-api-rfm-search]].
