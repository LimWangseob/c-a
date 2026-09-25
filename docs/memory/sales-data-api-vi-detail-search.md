---
name: sales-data-api-vi-detail-search
description: 판매분석 수집을 사람 클릭·엑셀다운로드 대신 vi-detail-search 데이터 API 직접 fetch로 — 실측 스키마
metadata: 
  node_type: memory
  type: reference
  originSessionId: e9438a2f-e201-48d4-bf71-5cdf2500b598
  modified: 2026-09-14T00:00:00.000Z
---

판매분석 수집은 '엑셀 다운로드' 버튼 클릭이 아니라 화면이 쓰는 **데이터 API를 같은 로그인 세션에서
직접 fetch**한다(자동완성 [[login-policy-real-browser-only]]의 same-origin fetch와 동일 정식 방식, 위장로그인 아님).
`collector.fetch_sales_details` / `_parse_vendor_items`. **실측 확정 2026-09-07(gbseller808), 마스터 실값 대조 일치.**

- **엔드포인트**: `POST https://wing.coupang.com/tenants/rfm-ss/api/business-insight/vi-detail-search`
- **바디**: `{"startDate":"YYYY-MM-DD","endDate":"YYYY-MM-DD","registrationTypes":["NORMAL","RFM"],"pageNumber":0,"pageSize":N,"sortBy":"GMV","sortOrder":"DESC","includeSoldVICount":true}`
- **헤더(필수)**: `content-type: application/json` + **`x-xsrf-token`** = `XSRF-TOKEN` 쿠키값(axios withCredentials 패턴 — JS로 `document.cookie`에서 읽어 되보냄, HttpOnly 아님). cookie는 credentials:'include'로 자동. baggage·sentry-*는 텔레메트리라 불필요.
- **응답**: `{vendorItems:[{vendorItemDetails{vendorItemId,productName,itemName,itemId}, businessInsightsMetricsResponse{totalPageViews,totalUnitsSold,totalUniqueVisitor,…}}], soldVICount, paginationDetails{pageSize,pageNumber,totalResults,totalPages}}`
- **지표 매핑(실측 대조 확정)**: 노출건수=`totalPageViews` · 판매건수=`totalUnitsSold` · 방문자건수=`totalUniqueVisitor`. 옵션ID=`vendorItemId`(str), 상품명=`productName`, 옵션명=`itemName`(제목+", 옵션"), 등록상품ID=`itemId`. 페이지네이션 totalPages 따라 전 페이지 수집.

**Why:** 클릭→드롭다운→비동기 다운로드→파일감시는 느리고(계정당 수십초) 취약. 직접 fetch가 빠르고 안정적.
**How:** page(로그인된 wing 페이지)에서 `page.evaluate` fetch. 실패 시 로그 남기고 옛 엑셀 다운로드로 폴백(`report.parse_by_option`). Akamai가 실세션만 허용 → 반드시 사람이 로그인한 프로필 재사용([[coupang-session-short-lived]]). 관련 판매데이터 익일반영 [[coupang-sales-data-lag]].

**⚠️ 반환 범위 = 조회기간에 활동(조회/방문/판매) 있은 상품만(2026-09-13 확정).** `sold=0`이어도 `views>0`이면 vid와 함께 반환(캡처 `_capture_sales_gbseller808`). ∴ **당일(D-1) 완전 무활동 상품은 응답에 없어 vid 없음** → 대장에 있어도 `scope_to_ledger` 미매칭(지표 기본0·vid 공란). 별도 등록상품조회(카탈로그) API 없음(도입 안 함). **vid 보강(2026-09-13 구현)**: 대장에 있는데 당일 미매칭이면 `collector.fetch_sales_roster(page, 최근 config.SALES_VID_WINDOW_DAYS=30일)`로 vid·상품명 roster 확보 + 그로스는 재고 API(`_parse_inventory_roster`=`inventory-health-dashboard`의 `creturnConfigViewDto.productName`, 판매무관)로 vid 확보 → `product_match.augment_unmatched`가 미매칭만 채움. **⚠ 30일 조회 지표는 미반영(당일 것만 기록).** **라이브 검증 완료(2026-09-14 밤샘 ③ 반자동 실행)**: vid 없던 상품(웰빙곳간 알부민 등)이 상품명 매칭 폴백으로 순위 잡힘·노출명 17건 갱신 확인. 관련 [[semi-auto-rank-and-exposed-name]].
