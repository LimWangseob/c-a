---
name: inventory-api-rfm-search
description: "로켓그로스 재고현황(판매가능 재고수량)=inventory-health-dashboard/search API 직접조회, 실측 스키마"
metadata: 
  node_type: memory
  type: reference
  originSessionId: e9438a2f-e201-48d4-bf71-5cdf2500b598
  modified: 2026-09-24T04:55:15.635Z
---

로켓그로스 **재고현황(판매가능 재고수량)**은 재고관리 페이지가 쓰는 데이터 API를 같은 로그인 세션에서 **직접 fetch**한다([[sales-data-api-vi-detail-search]]와 동일 same-origin+XSRF 방식). **라이브 캡처 확정 2026-09-08(bf0621/명진상사, 화로테이블 R023).** `collector.fetch_inventory`/`_parse_inventory`, 배선 `pipeline._login_and_discover`(계약계정만)→`_inventory_by_product`.

- **엔드포인트**: `POST https://wing.coupang.com/tenants/rfm-inventory/inventory-health-dashboard/search`
- **바디**: `{"paginationRequest":{"pageSize":100,"pageNumber":0,"searchAfterSortValues":null},"hiddenStatus":"VISIBLE","sort":[{"sortParameter":"ORDERABLE_QUANTITY","sortDirection":"DESCENDING"}],"rrqContext":{"source":"IHD","eventType":"RRQ_SEEN","metadata":"{}"}}`
- **헤더**: `content-type: application/json` + `x-xsrf-token`=XSRF-TOKEN 쿠키값(vi-detail-search와 동일).
- **응답**: `{viProperties:[{vendorItemId, listingDetails{productId,itemId,vendorInventoryName,...}, inventoryDetails{orderableQuantity, inventoryHealthGroup, daysOfCover, overstockQuantity,...}, salesStatistics{yesterdaySales{totalPageViews,unitsSold,gmv},last7/30Days...}, pricing,...}], paginationResponse{pageNumber,pageSize,totalNumberOfElements,searchAfterSortValues}}`
- **재고현황 = `viProperties[].inventoryDetails.orderableQuantity`**(판매가능 재고). 한 상품(productId)에 vendorItem 여러 개면 vid별 재고를 **상품단위로 합산**(화로테이블 vid 3개 13+0+0=13).
- **페이지네이션**: `paginationResponse.totalNumberOfElements`로 종료(pageSize 100이면 대부분 1페이지). **계약(RFM) 계정 전용** — 개인(NORMAL)은 빈 응답.

**⚠ 미해결 실측 불일치(추적):** 이 응답 `salesStatistics.yesterdaySales.totalPageViews`=669(화로테이블, 09-07)인데 vi-detail-search는 같은 날 노출/방문 0 반환. 노출/방문 매핑 or 익일반영([[coupang-sales-data-lag]]) 재확인 필요(추측 금지 — 다른 날짜로 대조).

**🔒 재고 규칙 최종 확정(소유자 2026-09-24 — 변경 금지):**
1. **업번들(자동번들) 옵션 = 결과파일에서 완전 제외**(상품/옵션/순위/재고 전부 미표기). 판정=상품조회 `upbundlingInfo.upBundling==True`. 배경: 업번들은 2025-05 로켓그로스 자동생성 묶음(같은 단건 N개)·별도 입고 없이 원상품 재고 공유(웹가이드+원본 실증)·재고현황 API에 vid 없음(86/86). ÷수량 계산·판매중지 잔여재고 엣지를 아예 없애려 **제외** 선택(소유자). 제외해도 원상품 안 사라짐(고아번들 0·번들만 리스팅 0 실측).
2. **재고 값 = 재고현황 API `orderableQuantity`에서만.** ⛔상품조회 `stockQuantity`=등록시 임의입력값→신뢰불가·쓰지말 것. 상품조회는 RFM/업번들 **구분 용도**로만.
3. **⚠️재고칸 규칙 개정(소유자 2026-09-24 오후 — 구현 대기 [[handoff-gsheet-inventory-followup]])**: **판매중지 여부와 무관하게** 재고현황 API에 vid 있으면 값(0=품절)·**없으면 항상 "미입고"**. 옛 "판매중지→공란" 분기 **폐기**(`_block_sellable` 제거). 배경=웰빙곳간(제한계정)이 상품조회 productStatus 전부 SUSPENDED로 나와, 옛 규칙에선 판매중 관리상품도 재고 텅 빔(실측 47블록중 31공란). 미입고 vs 품절 신호=재고현황 존재여부(품절도 0으로 남음).
4. **판매상태(productStatus)는 쿠팡 그대로 존중**(우선 적용·all-SUSPENDED 보정 안 함) — 재고칸이 아니라 **실행일 "비고" 항목에 항상 표시**. ⛔상품조회 stockQuantity(재고 숫자)만 신뢰불가.
5. **판매자배송(NORMAL)** = 재고 개념 없음(공란·[재고오류] 오탐 금지).
6. **업번들 잔재 블록 = 매 수집 시 자동 삭제**(별도 도구 아님·담당자 상품변동 충돌 방지). reconcile에서 이번 상품조회 업번들 vid로 마스터 블록 삭제(vid 기반).
- 확정 근거=[[handoff-inventory-blank-260924]] 원본(_raw) 분석 6계정. 업번들 웹조사=[[fix-from-real-evidence]]. **다음=이 규칙으로 구현 설계(products_from_vendor_inventory에서 업번들 제외 + _inventory 매칭을 재고현황 존재/부재로 미입고 판정).** ⚠구현 전 [[code-health-regression-gate]] 핀 먼저.
- (참고·폐기) 이전 검토했던 "묶음 재고=재고현황[기본]÷수량"은 계산상 정확(판매중 묶음 54/54 쿠팡값 일치)했으나, 소유자가 **업번들 제외**로 결정 → 이 계산은 **미사용**.

**How:** 실패해도 수집 전체 진행(부가지표, 명시 로그). 캡처 도구=`tools/capture_inventory_api.py <계정ID>`(메타 우선저장 + JSON body만 선별 — 스트리밍 응답 무한블록 회피). 관련 [[seldoc-output-format]] [[fix-from-real-evidence]].
