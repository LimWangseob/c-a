---
name: feature-vid-source-from-product-list
description: "VID 출처=상품조회/수정(vendor-inventory/search)로 변경 + 옵션 분리 + 판매상태 productStatus. 1~7단계 구현 완료(2026-09-20·오프라인 검증 통과·라이브 확인 남음). vid 출처=(A) 헤더 이름칸. 블록명=등록상품명+옵션라벨. 대표=첫 옵션(과거이력 승계)·2차=지표만. 판매상태=판매자배송 포함 전 상품 커버."
metadata: 
  node_type: memory
  type: project
  originSessionId: d8fb41f6-bdf5-4fe4-8e5b-ec34a7da65a4
  modified: 2026-09-20T01:26:34.691Z
---

**소유자 요구(2026-09-19, 분석 단계·미구현):**

1. **재고 공란 로그**: 추적 상품의 vid가 재고조회(inventory-health-dashboard/search) 응답에 없어 재고가 공란 처리될 때 **로그로 남겨** 진단 가능하게. 현재 `_fill_product_metrics`는 `inv is None`이면 조용히 미기록(로그 없음).

2. **합산 이유(설명 완료)**: 한 상품=여러 옵션(색상/용량, 각 vendorItemId). 쿠팡 API는 옵션(vid)별 지표 제공 → 상품 단위 관리라 옵션 지표를 합산. 재고도 동일.

3. **둘다(로켓그로스+판매자배송) 처리 요구**: 둘다 상품은 **VID를 로켓그로스(RFM) 옵션 것으로**, **판매통계도 로켓그로스 옵션만 반영**(판매자배송 옵션 제외). 현재는 판매통계=전 옵션 합산·VID=전 옵션 저장·재고만 RFM. → RFM 옵션만 집계로 변경 필요.

4. **VID 출처 변경(핵심)**: 최초 VID를 **판매분석(vi-detail-search)이 아니라 "상품조회/수정"(`wing.coupang.com/vendor-inventory/list`)에서** 가져온다. 상품조회는 계정의 **모든 등록상품(판매 유무 무관)** 을 보여주므로, **상품명 매칭으로 정확한 vid를 확보해 구글시트/마스터에 저장**. 현재 vi-detail-search는 **당일 판매활동 상품만** 잡혀 당일 판매 0 상품은 vid 누락→roster 보강(불안정)→재고 공란/오매칭의 근본 원인.
   - 4-1. "대장 상품에 vid 부여"에 대한 소유자 의문: 이름 매칭이 부정확하면 엉뚱한 vid. "대장 상품"=관리대장(셀독리스트)의 추적 대상(위탁분). 정확 매칭 위해 상품조회 전체목록에서 매칭 후 **vid를 정체성으로 고정**(이후 vid로만 추적).

5. **요구 종합**: vid 출처=상품조회/수정. 판매분석은 지표(노출·판매·방문) 소스로만.

**구현 전 필요(미확보):** `vendor-inventory/list` **데이터 API 실캡처** — 필드 확인(vid·등록상품명·registrationType·재고·판매/승인상태). feature-sale-status 메모의 "2단계 숙제"와 동일 소스. 소유자가 캡처 제공 예정("상세자료 필요하면 요구해").

**추가 요구(2026-09-19-2):**
- **대장 역기록 금지**: 관리대장은 **프로그램이 수정하면 안 되는 항목**(읽기 전용 입력). vid/제목을 대장에 써넣는 "대장 역기록" 안은 **폐기**. vid 확정·저장은 **결과(마스터/구글시트)에만**. ⚠확인필요: 기존 '그로스 재고 역기록'(대장 AD열 쓰기, push_ledger_inventory)도 금지 대상인지 소유자 확인.
- **옵션별 통계표 분리안(검토 요청)**: 옵션 상품(색상·사이즈·등급 다름)은 **옵션(vid)별로 통계표 1 set**를 추가 → 1블록=1vid=유일. 이 경우 **키워드조회·노출순위는 생략**. 근거=검색 노출순위는 리스팅(productId) 단위라 옵션 공통(옵션별 순위 중복). 이러면 vid 정체성 명확·옵션별 재고/판매 개별표시(재고1,2 혼동 해소)·합산 불필요.
  - 결정필요: ①"옵션상품"=한 리스팅+옵션(순위공통) 확정? ②순위 완전생략 vs 대표옵션1개만 순위유지? ③단일옵션 상품은 기존(키워드+순위) 유지? ④옵션 많은 계정 행 급증 허용?(유라이프 408옵션) ⑤옵션 라벨(색상/사이즈) 표기.

**확정 결정(2026-09-19-3):** ①대장 '재고' 항목은 수정 가능(그로스 재고 역기록 유지)·대장 역기록(vid/제목)만 금지 ②vid는 **숨김 `_상품ID` 시트 저장 금지 → 결과 파일(통계 시트/구글시트)에 저장·읽기** ③옵션 분리는 **다중옵션에만** ④**대표 옵션 1개만 키워드+노출순위 유지**, 나머지 옵션 블록은 **판매정보만·순위 제외** ⑤한 리스팅(productId) 아래 여러 옵션(vid) 맞음 ⑥옵션 라벨(색상/사이즈/등급)을 상품명 옆 표기 ⑦행 3~4배 일부 증가 허용.

**⭐과거 캡처 증거(output/_capture_inventory_bf0621_260908_143018.json, 명진상사 화로테이블 RFM):** **재고 API(inventory-health-dashboard/search) 응답이 옵션 분리에 필요한 필드 대부분 제공**: `vendorItemId`(옵션별 유일)·`listingDetails.productId`(리스팅=옵션 그룹)·`vendorInventoryName`(상품명)·`vendorInventoryItemName`(옵션 라벨 예:'우드 one size 48cm')·`inventoryDetails.orderableQuantity`(재고)·`isSaleSuspended`(판매상태)·`salesStatistics.{yesterday/7일/30일}Sales`(노출=totalPageViews·판매=unitsSoldBeforeExcludingCancellations·gmv). **⚠방문자(uniqueVisitor)는 재고 API에 없음**(vi-detail-search에만). productStatus.actionsNeeded에 'ALMOST_OUT_OF_STOCK' 경보도 있음.
- 함의: **로켓그로스 상품은 재고 API가 이미 전량 나열(판매 유무 무관)** → vid 출처로 충분. **vendor-inventory/list 별도 캡처 사실상 불필요**(로켓그로스 대상 한정). 순수 판매자배송(NORMAL)은 재고 API에 없음(둘다=로켓그로스만이면 무관).

**확정(2026-09-19-4):** ①**방문자 필요** → 재고 API엔 없으니 vi-detail-search를 vid로 조인(노출·판매·방문자=vi-detail, 재고·상태·옵션목록=재고 API) ②**vid=구글시트에서만 저장·읽기**(숨김시트 금지·마스터 저장 안 함) → ⚠②③ 오프라인 단계가 gsheet 의존 생김 ③**대표 옵션=첫 옵션** ④**순수 판매자배송(NORMAL) 상품 있음** → 재고 API에 없어 완전목록 vid 소스 없음(vendor-inventory/list 캡처 미보유) → 로켓그로스만 재고 API로 충족·NORMAL은 vi-detail(활동기반) 한계 남음 ⑤그로스 재고 역기록 현행 유지.
**⭐상품조회/수정 스크린샷 확인(2026-09-19, 소유자 제공 3장):** URL=`wing.coupang.com/vendor-inventory/list`. 이 화면이 **전 상품·전 옵션(판매유무·판매방식 무관)** 을 제공 = 요구 소스 확정. 제공 필드:
- 상품(리스팅) 레벨: **등록상품명**·판매방식·**등록상품ID**(내부, 예 16214728991)·쿠팡전체판매량(30일)·내판매량·노출상태(아이템위너)·판매가·**판매/승인상태**(판매중/부분판매중/판매중지)·**재고수량**(예 177 부분품절).
- 옵션(펼침) 레벨: **옵션명**(색상/사이즈/등급, 예 '베이지 25x16.5x20.5cm 1개')·**판매방식**(로켓그로스/판매자배송)·내판매량·판매/승인상태·**재고수량**(옵션별, 0품절/177)·출고일·**옵션ID=vendorItemId(vid)**·**노출상품ID=productId**(고객노출, 예 9557485279).
- **ID 3종 구분**: 등록상품ID(내부)≠**노출상품ID=productId**(리스팅·검색/순위 기준)≠**옵션ID=vid**(정체성).
- **둘다 실증**: 보냉백 BG001(노출상품ID 9557485279)의 같은 옵션 '베이지…'가 판매자배송(vid 95467377159·재고0·판매중지)+로켓그로스(vid 95501572184·재고177·판매중) **2 vid**로 존재 → '둘다=로켓그로스만'이면 vid …184 선택·…159 제외.
- 상단 **'엑셀 대량 수정'** 버튼=전 상품 옵션ID 포함 대량 엑셀(대안 데이터 소스 후보).
- 함의: 이 페이지로 **매칭(등록상품명)·그룹(노출상품ID)·옵션분리(옵션ID)·판매방식·재고·상태**를 로켓그로스+판매자배송 **모두** 확보 가능. 일자별 노출·판매·방문자는 여전히 vi-detail-search(30일 집계만 이 페이지에 있음).
**⭐API 스펙 완전 확보(2026-09-20, 소유자 실캡처 — 사무실PC 원격, DevTools):** 구현에 필요한 자료 전부 모임. 더 캡처 불필요.
- **엔드포인트**: `POST https://wing.coupang.com/tenants/seller-web/v2/vendor-inventory/search`, `Content-Type: application/json`, 세션 쿠키 + x-xsrf-token(vi-detail-search와 동일 패턴 [[sales-data-api-vi-detail-search]]).
- **요청 본문(JSON)**: `{searchKeywordType:"ALL", searchKeywords:"", salesMethod:"ALL", productStatus:["ALL"], exposureStatus:"ALL", exposureStatuses:[], displayDeletedProduct:false, displayCategoryCodes:[], saleEndDateSearchType:"ALL", shippingFeeSearchType:"ALL", shippingMethod:"ALL", stockSearchType:"ALL", bundledShippingSearchType:"ALL", upBundleSearchOption:"ALL", qualityEnhanceTypes:[], coupangAttributeOptimized:false, listingStartTime:null, listingEndTime:null, sortMethod:"SORT_BY_ITEM_LEVEL_UNIT_SOLD", locale:"ko_KR", countPerPage:50, page:1}`. ⚠전량 수집 핵심=`exposureStatus:"ALL"`(NON_ITEM_WINNER면 아이템위너 누락)·`salesMethod:"ALL"`·`productStatus:["ALL"]`·`displayDeletedProduct:false`.
- **페이지네이션**: `page` 1→N 증가, 응답 `pagination.totalPages`까지 반복(countPerPage=50).
- **응답 봉투**: `{success:true, data:{productList:[…], pagination:{page,countPerPage,totalCount,totalPages}}, message}`.
- **리스팅 레벨 필드**(`productList[]`): `productName`=⭐등록상품명(대장 매칭키)·`vendorInventoryId`=⭐등록상품ID(내부)=옵션 그룹핑키·`registrationType`(NORMAL=판매자배송/RFM=로켓그로스)·`productStatus`(ON_SALE/PARTIAL_ON_SALE=부분판매중/판매중지)=⭐판매상태(전상품·NORMAL포함)·`status`(APPROVED)·`representativeImage`·`itemUnitSoldAgg`.
- **옵션 레벨 필드**(`vendorInventoryItems[]`): `vendorItemId`=⭐vid(정체성)·`itemName`=⭐옵션명(라벨)·`registrationType`=⭐둘다판별(RFM만 채택)·`valid`(VALID/INVALID·필터후보)·`status`·`salePrice`·`vendorInventoryItemId`(등록옵션ID 내부)·`stockQuantity`(=재고, **안 씀**·부정확).
- **⚠노출상품ID(productId)는 응답에 없음** → 그룹핑은 `vendorInventoryId`로(리스팅 단위). 순위는 검색결과서 vid 매칭이라 productId 불요.
- **재고는 이 소스에서 제외(2026-09-20 소유자)**: 등록시 임의입력값이라 부정확 → 재고=RFM 재고 API([[inventory-api-rfm-search]])만, 이 소스는 vid·옵션·판매방식·상태·매칭 전용.
- **판매상태 경고 개선여지**: `productStatus`가 NORMAL 포함 전상품 커버 → [[feature-sale-status-mismatch-flag]]의 판매자배송 미상 한계 해소 가능(현재는 RFM isSaleSuspended만).

## ✅구현 완료(2026-09-20·오프라인 검증 통과·⚠라이브 확인 남음)

**⭐마이그레이션 정책(2026-09-20-2 소유자): vid=상품당 1개(2개 경우 없음). 첫 적용 시 vid가 기존과 다르면 이전 데이터 삭제하고 새로 시작.** `_process_account` 마이그레이션 = ①같은 vid(교집합)=같은 상품 → 기존 블록 승계+등록상품명 정규화(resolve_block_name+set_display_name) ②등록상품명 같은데 vid 다름(교집합 없음)=정체성 변경 → `delete_product_block`으로 삭제·새로 시작(workbook `blocks_with_registered_name`+`delete_product_block` 신설, 저장 vid 없는 블록은 삭제 안 함). 검증 simulate[12](day1 vidOLD→day2 vidNEW=09.01 이력 소멸)·verify_offline[12](단일 블록 삭제·나머지 온전). ※이는 옛 '대표옵션 과거이력 승계'를 **같은 vid일 때만** 승계로 정밀화한 것. **계정 삭제(관련 시트 제거)=기존 구현으로 이미 처리**(run_full이 대장서 사라진 계정 판정→workbook.delete_account[시트·메타]+gsheet delete_accounts[계정목록 행·통계 시트], verify_offline[10]·verify_gsheet[3c] 통과·새 코드 불요).

1~6단계 코드 구현·커밋. 결정 반영: **vid 출처=(A) 헤더 이름칸 'VID :' 꼬리**(인메모리 `_block_vids`·`_reindex` 파싱·`set_product_vids`=이름칸 즉시 렌더·숨김 `_상품ID` vid 3열 폐지, 무손실 이관). **블록명=등록상품명+옵션라벨**(다중옵션만·단일=등록명). **대표(첫)옵션=키워드+순위·과거 합산이력 승계**(마이그레이션이 옛 블록을 vid로 찾아 대표 옵션명으로 리네임)·**2차 옵션=판매정보만**(`ensure_product_block(rank_rows=False,registered=base)`·`has_keyword_section`로 ②·pad 건너뜀). ③ 순위 매칭=**`sibling_vids`**(같은 등록상품명 옵션 vid 합집합=아이템위너가 어느 옵션이든 놓치지 않음, 정확순위 최우선요구 [[session-handoff-exact-rank-required]]). **set_display_name(노출명 교체) 중단**(블록명 고정). 지표=옵션(vid)별(합산 제거, 노출/판매/방문=vi-detail·재고=RFM). `_login_and_discover`가 `fetch_vendor_inventory`를 vid 출처로(폴백=판매분석 발견). **②③ gsheet 의존 안 생김**(vid가 마스터 이름칸에 있어 오프라인 마스터만 읽음 — 옛 경고는 (A) 이전 잔재). **7단계(판매상태 productStatus화)=되돌림**(라이브 실측 2026-09-20 wellbing1107): productStatus 전 옵션 SUSPENDED 상수(활성 상품도)·valid 전 옵션 INVALID 상수 → 판매상태 구분 불가. RFM isSaleSuspended(판매중지42·판매중10)만 신뢰 → **판매상태 소스=RFM 유지**(판매자배송 미상 한계 그대로). productStatus/valid=관측 로그 전용. 커밋 51c042b. ⭐**라이브 검증(2026-09-20)**: 로그인→상품조회 51리스팅→47상품·대장17→매칭14·vid80·옵션분리·판매분석지표·RFM재고52 **전부 정상**(vid 출처 변경 자체는 완벽 동작). 검증=verify_offline[8·12]·simulate[11 다중옵션][9 노출명중단]·verify_gsheet 통과. ⚠**라이브(사무실)**: vendor-inventory 실응답 필드·마이그레이션 실동작·sibling 순위매칭 최종 확인.

## ⭐구현 계획(2026-09-20 조사 완료·소유자 승인 후 착수) — 함수 앵커 확인됨

문서 반영 완료(커밋 f38122c): DESIGN §0-00000·§2.3·§8-G, CLAUDE.md. **1·2단계 코드 착수 완료(pipeline 미배선·현재 동작 무영향).** 아래 순서.

1. **✅ 완료 — collector.py 상품조회/수정 fetch 신설**:
   - `fetch_vendor_inventory(page, log) -> list[VendorInventoryListing]` 신설(참고 패턴=`fetch_sales_details`·`fetch_inventory`, **same-origin fetch + x-xsrf-token** 재사용). `POST /tenants/seller-web/v2/vendor-inventory/search`, 본문=`_VI_SEARCH_BASE`(§0-00000 JSON), `page` 1→N 루프(`data.pagination.totalPages`). 비200/`success:false`/파싱실패=`VendorInventoryFetchError`.
   - 데이터 구조 `VendorInventoryListing`(product_name·vendor_inventory_id·registration_type·product_status·status·options[])·`VendorInventoryOption`(vendor_item_id=vid·item_name·registration_type·valid·status·sale_price). 파서 `_parse_vendor_inventory` — 옵션은 **valid=INVALID 포함 그대로**(폐기·합산은 다운스텝 판단·수집단계 조용한 폴백 금지), vid 빈 옵션만 제외. 재고(stockQuantity)는 안 씀.
2. **✅ 완료 — 대장↔리스팅 매칭**: `collector.products_from_vendor_inventory(listings, log) -> list[Product]` 변환기(리스팅 1개=Product 1개·그룹키=`vendorInventoryId`·productId 없음·옵션=Option(vid)). **둘다=RFM 옵션만** 채택(같은 옵션 NORMAL vid 제거)하되 **kind는 전 옵션 판별해 '둘다' 보존**(재고행 대상). 라벨=단일옵션 ""·복수 itemName(`_uniquify_labels` 공유). → 기존 정밀매칭 `product_match.scope_to_ledger`/`augment_unmatched`([[ledger-scoped-tracking]]) **코드 무변경** 재사용(당일 판매 0 상품도 잡힘). 오프라인 통합 테스트 통과(둘다=RFM만·비관리 미배정·단일옵션 라벨"").
3. **workbook.py — 옵션 분리 블록**: `ensure_product_block` [workbook.py:367] 확장 — **다중옵션 상품만** 옵션(vid)별 통계표 1 set, `vendorInventoryId`로 그룹. 대표=**첫 옵션**만 `add_product_keywords`[437](키워드+순위), 나머지 옵션 블록은 **판매정보만·순위행 없음**. 옵션 라벨(`itemName`)을 상품명 옆 표기. **둘다=`registrationType=="RFM"` 옵션만** 채택(NORMAL 중복 제외). 단일옵션은 기존 유지.
4. **vid 저장 위치=구글시트만**: 숨김 `_상품ID` 시트/마스터 저장 금지(소유자 확정). ②③ 오프라인 단계가 vid를 gsheet에서 읽어야 함 → **읽기/쓰기 위치 설계 필요**(통계 시트 어디에·gsheet_stats). ⚠오프라인 단계에 gsheet 의존 새로 생김.
5. **소스 조인(기존 유지)**: 재고=`fetch_inventory`[212] RFM API(로켓그로스만)·노출/판매/**방문자**=`fetch_sales_details`[123]·vid로 조인. `_fill_product_metrics`[pipeline.py:504]·`_inventory_by_product`[473]는 vid 기준으로 재정렬.
6. **pipeline 배선**: `_login_and_discover`[pipeline.py:315]가 `fetch_vendor_inventory`도 호출 → `_process_account`[565]/`_fill_product_metrics`[504]로 전달. `run_full`[877]·`select_keywords_stage`[1155]·`track_ranks_stage`[1219] 모두 vid=gsheet 읽기 반영.
7. **판매상태 경고 개선(선택)**: `productStatus`로 판매자배송 포함 판정([[feature-sale-status-mismatch-flag]] 개선여지) — `apply_sale_status`[workbook.py:702] 대체/보강.
8. **검증**: `tools/simulate_pipeline.py`(옵션분리·둘다=RFM만·다중/단일 시나리오)·`tools/verify_offline.py`(옵션블록 왕복).

**⚠새 세션 주의**: ①라이브 fetch/검증은 **사무실 세션 필요**(집=2차인증). ②vid=gsheet만 저장이 오프라인 단계 의존을 만드니 읽기 실패 시 폴백 설계. ③`valid=INVALID`·재고 제외(RFM만)·productId 없음(그룹=vendorInventoryId) 세 지점 실수 주의. ④행 3~4배 증가 허용(소유자). ⑤착수 전 소유자 최종 승인 확인.

## ⭐gsheet-only 정체성 재설계 (2026-09-20 소유자 결정 — 3단계부터 gsheet-only·⚠새 세션에서 구현·(A)/(B) 확인 선행)

**소유자 2026-09-20 결정 2건:** ①3단계 옵션블록 정체성을 **처음부터 gsheet-only**로 설계(기존 vid 앵커 재사용 안 함) ②이 큰 변경(3~6단계=하나의 정체성 재설계)은 **설계 확정 후 새 세션에서 구현**(마스터 손상 위험 최소화). 이번 세션은 1·2단계 코드(커밋 764f69b) + 이 설계만.

**⚠핵심 모순 → (A) 확정(소유자 2026-09-20):** 통계 시트 = 마스터 openpyxl 시트의 **전체 교체 미러**(`gsheet_stats.worksheet_to_requests` updateCells 전량 교체). → gsheet 통계에 보이는 값은 전부 마스터에서 옴. vid가 마스터에 없으면 전체교체 미러로는 gsheet 통계에 나타날 수 없다. **소유자 결정=(A).**
- **✅(A) 확정** — vid의 **유일 출처(source of truth)를 통계 블록 이름칸(헤더 C셀)의 표시값** "VID : a / b"로 삼는다(지금도 `_display_name`이 렌더 중). **숨김 `_상품ID` 시트의 vid 열(3열) 폐지**(정체성 출처에서 제외). ③ 순위조회는 이 이름칸에서 vid를 파싱(gsheet/마스터 공통). 마스터 xlsx 셀엔 **보이는 표시값**으로 남는 것 허용(대장 역기록과 무관). gsheet 미러로 자동 노출.
  - ⚠구현 핵심: 지금은 이름칸 "VID : …"가 `product_vids`(=`_META_SHEET` 3열)에서 **렌더만** 되고 출처는 숨김시트다. (A)는 **반대로** — 이름칸이 출처, `product_vids`/`resolve_block_name`이 **이름칸 파싱**으로 동작해야 한다(`_reindex`가 헤더 C셀 꼬리에서 vid 복원). `_META_SHEET` 3열 write 제거.
  - `_META_SHEET`의 나머지 열(등록상품명 6열·판매상태 7열·제목캐시 4·5열)은 **vid 아님 → 마스터 유지 가능**(폐지 대상은 vid 3열만).
- (B)별도 보조 gsheet 시트·(C)미러 비교체 = **채택 안 함**(기록만).

**블록 정체성(cross-day 안정 키):** vid-source-change 후 블록명 = **등록상품명(productName)** = 안정(대장 등록명, 매일 바뀌는 노출 SERP명 아님). 옵션 라벨(itemName)도 안정. → 마스터 블록 키 = **(사업자, 등록상품명+옵션라벨)** 조합, **cross-day 안정에 vid 불필요**. ⚠단 기존 `set_display_name`(블록명을 노출명으로 교체)은 **중단**해야 등록명 키가 안정 — 노출명은 로그/별도 표시열로만(결정 필요).

**단계별 변경 요지(새 세션 구현 순서):**
- **step4(선행·(A) 확정):** vid 출처=**통계 블록 이름칸(헤더 C셀) "VID : …" 표시값**. `set_product_vids`=헤더 C셀 꼬리 렌더로 변경(현행 `_display_name` 로직을 저장 시 확정)·`_META_SHEET` vid 3열 **write 제거**. `product_vids`/`resolve_block_name`=헤더 C셀 파싱으로 재구현(`_reindex`가 C셀 "VID : a / b"에서 vid 복원해 `_vid_row`/인메모리 인덱스 구성). ③ 순위조회는 gsheet에서 같은 이름칸 파싱. `registered_name`(6열)·`sale_status`(7열)·`title_cache`(4·5열)는 vid 아님 → `_META_SHEET` 유지.
- **step3(워크북 옵션블록):** `ensure_product_block(..., *, option_label="", rank_rows=True)` 확장 — option_label→헤더 C "등록상품명 (라벨)", rank_rows=False→키워드 소헤더·순위행 생략(판매정보만). 블록 키=호출부가 조합명 전달. 다중옵션만 분리·단일옵션 기존 유지·둘다=RFM만(step2 완료).
- **step5(소스 조인):** `_fill_product_metrics` 합산 제거→옵션(vid) 개별 지표. 노출/판매/방문자=vi-detail(vid join)·재고=RFM API(vid별)·vid·옵션·상태=vendor-inventory.
- **step6(파이프라인 옵션 루프):** `_process_account`가 상품→옵션 단위 분해(다중옵션만), 대표=첫 옵션에만 키워드·순위·진단, 나머지 옵션은 지표만. `resolve_block_name` 대체(등록명+라벨 키).
- **step7(판매상태 경고 개선):** `productStatus`(NORMAL 포함)로 판정 → `apply_sale_status`를 vid 재고맵 대신 리스팅 productStatus 기반 보강(판매자배송 커버, [[feature-sale-status-mismatch-flag]] 한계 해소).
- **step5/6(③ 순위매칭):** 검색결과 매칭은 여전히 vid 앵커 → ③이 vid를 (A)통계셀/(B)보조시트에서 읽음. 읽기 실패 폴백=등록상품명.
- **마이그레이션:** 옛 `_상품ID` vid열 → (A)면 이름칸 VID 표시 이미 있음(무해)·(B)면 1회 이관. 옛 단일블록(옵션합산)→다중옵션 분리는 **앞으로만**(과거 컬럼 소급 안 함).
- **step8 검증:** simulate_pipeline(옵션분리·둘다=RFM만·다중/단일)·verify_offline(옵션블록 왕복)·gsheet vid 읽기 폴백.

**분석 결론(2026-09-19):** #5(vid 출처=상품조회/수정)+옵션 분리안이면 vid 1:1·누락/오매칭/합산문제 대부분 해소. 매칭은 상품명 기반 유지(정밀매칭 [[ledger-scoped-tracking]]). **대장 역기록 없이** 결과에만 vid 저장. 1·2단계 코드 완료(커밋 764f69b)·3~6단계=gsheet-only 정체성 재설계(위)·**(A)/(B) 소유자 확인 후 새 세션 착수**([[analysis-request-no-code-change]]).

관련 [[feature-sale-status-mismatch-flag]] [[ledger-scoped-tracking]] [[sales-data-api-vi-detail-search]] [[inventory-api-rfm-search]] [[seldoc-output-format]]
