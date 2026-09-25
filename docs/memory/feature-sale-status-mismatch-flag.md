---
name: feature-sale-status-mismatch-flag
description: "구현완료(2026-09-17) — 관리대장=판매중지인데 쿠팡=판매중/부분판매중 불일치면 결과파일 실행날짜칸에 \"판매중\" 진한적색. collector~apply_style 전구간 배선·오프라인 실증 통과. 라이브(①판매수집 로그인)로 최종 확인 남음."
metadata: 
  node_type: memory
  type: project
  originSessionId: 2e84ec15-ec5e-47e8-a0f5-e93a370e0385
  modified: 2026-09-20T01:48:44.530Z
---

## ✅ 상태출처=productStatus 확정(2026-09-20 라이브 다계정 검증) — 판매자배송 커버
**결론**: 상품조회/수정 `productStatus` = **화면 판매/승인상태와 일치하는 신뢰 소스**(전 상품·판매자배송 포함). 실제 enum: **ON_SALE=판매중·PARTIAL_ON_SALE=부분판매중·SUSPENDED=판매중지·DRAFT=임시저장·REJECTED=승인반려**. `sale_status_of`(ON_SALE→판매중·PARTIAL→부분판매중·그외→판매중지)·`sale_status_by_vid`→`_login_and_discover` 판매상태 소스(상품조회 실패 시 RFM `isSaleSuspended` 폴백)·`apply_sale_status`(문자열/bool). 커밋 871706a. **판매자배송(개인) 상품도 커버**(옛 RFM-only 한계 해소).
- ⚠**주의(교훈)**: 처음 wellbing1107 **한 계정만** 보고 "productStatus 전부 SUSPENDED 상수라 무용"이라 오판→되돌림(51c042b)했다가, 다계정(nicoable ON_SALE4/…·sg0141n ON_SALE6/…)으로 정상 변동 확인→**재적용**(871706a). wellbing1107 은 '신규 상품 등록 불가' 제한계정이라 전부 SUSPENDED 였을 뿐. **한 계정만 보고 필드 판단 금지**([[fix-from-real-evidence]]).
- **한계 해소**: 옛 출처=RFM 재고 API `isSaleSuspended`(로켓그로스만)라 판매자배송(개인) 상품은 미상(경고 안 뜸)이었음. 소유자 확인(상품조회/수정에 전 상품 판매중/판매중지 표시됨) → **상태 출처를 `vendor-inventory/search`의 `productStatus`(전 상품·판매자배송 포함)로 확대**. [[feature-vid-source-from-product-list]] 7단계로 구현.
- `collector.sale_status_of`(원문 enum→판매중/부분판매중/판매중지·방어적: 부분→판매중→그외=판매중지, 오판=경보누락 방향)·`sale_status_by_vid(listings)→{vid:상태문자열}`(원문→해석 로그). `_login_and_discover`가 상품조회 성공이면 productStatus 문자열맵, 실패면 RFM bool맵을 4번째로 반환.
- `apply_sale_status`가 **문자열·bool 둘 다 수용**(bool→True=판매중지·False=판매중 정규화). 나머지(판정·표시·gsheet)는 그대로. ⚠원문 enum 미확정=라이브 로그로 확인 후 매핑 정합성 점검. 검증=verify_offline[8] 확장.

## ✅ 구현 완료(2026-09-17) — 계획대로 착수·오프라인 실증 통과
- **collector.py**: `_parse_inventory_status(vi_props)→{vid: isSaleSuspended}` 신설(listingDetails.isSaleSuspended, bool 아닌 값·vid 없음 제외). `fetch_inventory`가 **3튜플 (재고, 상품명, 판매상태)** 반환(모든 return 갱신).
- **pipeline.py**: `_login_and_discover`가 4튜플(…, inv_status) 반환(모든 return/2호출부 갱신). `_finish(…, inv_status)`가 `report_acc.products` 있을 때 `wb.apply_sale_status(a.label, inv_status)` 1회 호출(마스터 전체에 vid 대조·①판매수집 세션에서만 확보).
- **workbook.py**: `_상품ID` 7열=`판매상태(쿠팡)`. `set_sale_status`/`sale_status`/`sale_active`(∈{판매중,부분판매중}) + `apply_sale_status(biz,{vid:suspended})`(전부중지=판매중지·전부아님=판매중·섞임=부분판매중·맵에없음=미상생략, 반환=반영수). `apply_style` 키워드 소헤더 블록 뒤에 `if is_disc and sale_active(...)`면 최신 날짜칸에 "판매중" C00000·굵게(멱등).
- **gsheet**: `worksheet_to_requests`의 `_text_format`가 foregroundColor+bold 미러링 → 결과시트 자동 반영(확인).
- **실증**: 상태파서·판정4종(판매중/부분/중지/미상)·렌더·멱등·비중지시무경고 전부 통과. 기존 verify_offline 회귀 없음.
- **⚠남음(라이브)**: isSaleSuspended 실재 필드 확인은 ①판매수집 로그인 라이브에서만(사무실). 개인상품(판매자배송)은 재고 API에 상태 없어 미상=경고 안 뜸(2단계 vendor-inventory/list 숙제).
- **✅개선여지 확정(2026-09-20 API스펙 확보·미구현)**: 2단계 숙제였던 `vendor-inventory/search` 응답의 리스팅 `productStatus`(ON_SALE/PARTIAL_ON_SALE/판매중지)가 **NORMAL(판매자배송) 포함 전상품** 판매상태를 제공. VID 출처 변경([[feature-vid-source-from-product-list]]) 구현 시 이 필드로 판정하면 **판매자배송 상품 경고 커버 가능** → 위 개인상품 미상 한계 해소. DESIGN §2.3·§0-00000.

---
**요구(2026-09-17 소유자)**: 관리대장과 쿠팡 실제 판매상태가 **불일치**할 때 결과파일에 경고 표시.

- **판정**: 결과파일에서 그 상품이 **"⛔ 판매중지"**(관리대장 기준 `is_discontinued`=취소선/상태/대장에서 빠짐)인데, **쿠팡 실제 "판매/승인상태" = 판매중 또는 부분판매중**이면 불일치.
- **표시**: 그 상품 **판매중지 행(키워드 소헤더, G="⛔ 판매중지")**의 **현재 작업 실행날짜 컬럼 셀**(판매중지 라벨 오른쪽=최신 날짜칸)에 **"판매중"을 진한 적색·굵게**. 마스터 xlsx에 넣으면 구글시트 미러링(`gsheet_stats.worksheet_to_requests`)으로 결과시트에도 반영.
- **목적**: 담당자가 관리대장↔쿠팡 상태 불일치를 확인·정정.

**쿠팡 상태 출처(소유자 확인)**: 쿠팡 Wing **상품관리→상품조회/수정**(`wing.coupang.com/vendor-inventory/list`)의 **"판매/승인상태"** 칸 = **판매중 / 부분판매중 / 판매중지** 등. 소유자: "VID값 구할 때 그 상품 상태도 함께 보여주고 있으니 그 값을 체크하면 됨."
- 후보 필드: 재고 API(`inventory-health-dashboard/search`) viProperty의 `listingDetails.isSaleSuspended`(bool)·`productStatus`(라이브 캡처에서 확인됨). isSaleSuspended=False→판매중, True→판매중지. **부분판매중**=상품의 옵션 중 일부만 suspended → 상품에 vid 여러 개일 때 하나라도 isSaleSuspended=False면 최소 부분판매중.
- ⚠단, isSaleSuspended는 **로켓그로스(계약) 재고 API에만** 있음. **판매자배송(개인) 상품**엔 없어서, 그런 상품 상태를 잡으려면 **`vendor-inventory/list` API를 새로 fetch**해야 할 수 있음(기존 `fetch_inventory` 패턴처럼 same-origin+XSRF). **구현 착수 시 실제 캡처로 필드 확정 필요**(소유자: "상세자료 필요하면 요구해").

**구현 범위(전 구간)**: collector(상태 수집: isSaleSuspended 또는 vendor-inventory/list 신규) → pipeline(상태 전달) → workbook(상품별 쿠팡 판매상태 저장 + is_discontinued와 비교) → `apply_style`(불일치면 실행날짜칸에 "판매중" 적색굵게) → gsheet 미러링 자동.

## 구현 계획(2026-09-17 조사 완료·파일:줄 앵커) — 새 세션이 이대로 착수

**핵심 통찰**: 우리가 깃발 달 상품(대장=판매중지지만 쿠팡=판매중)은 **아직 쿠팡 재고목록에 살아있는 상품**이다 → 그 vid가 **마스터에도 있고 방금 받은 재고 상태맵에도 있다**. **vid로 매칭**해 상태를 채우면 판매중지(대장에서 빠진) 상품도 커버된다. `_process_account`는 대장 상품만 순회하므로, **계정 단위 상태맵을 마스터 전체 상품에 vid로 적용**하는 게 맞다.

1. **collector.py — 상태 수집**:
   - `_parse_inventory_roster`([collector.py:176](src/coupang_analytics/collector.py)) 옆에 `_parse_inventory_status(vi_props) -> {vid: isSaleSuspended(bool)}` 신설(`vp["listingDetails"]["isSaleSuspended"]` 읽음). ⚠라이브 캡처로 필드 실재 확인(진단 로그엔 있었음).
   - `fetch_inventory`([collector.py:194](src/coupang_analytics/collector.py), 반환 `(inventory, names)` @L25-26·40·44)를 `(inventory, names, status)` 3튜플로 확장(또는 별도 함수).
2. **pipeline.py — 배선**:
   - `_login_and_discover` L431 `inventory, inv_names = fetch_inventory(...)` → `+ inv_status`. 반환 튜플([pipeline.py:454](src/coupang_analytics/pipeline.py) `return Account(...), metrics, inventory`)에 `inv_status` 추가 → 호출부(run_full 계정 루프)까지 전달.
   - `_process_account`([pipeline.py:564](src/coupang_analytics/pipeline.py))에서 계정 순회 끝(또는 `reconcile_account` L672 근처)에 **`wb.apply_sale_status(biz, inv_status)`** 1회 호출(대장 상품만 도는 set_product_vids 지점 아님 — 마스터 전체에 vid 매칭).
3. **workbook.py — 저장+판정+렌더**:
   - _META_SHEET(_상품ID, 현재 col1~6, `set_registered_name`=col6 @[workbook.py:593])에 **col7='판매상태(쿠팡)'** 추가. `set_sale_status(biz,product,status)`·`sale_status(biz,product)`·`sale_active(biz,product)`(status∈{판매중,부분판매중}) 신설.
   - `apply_sale_status(biz, {vid:suspended})`: 마스터 각 상품의 `product_vids`를 상태맵과 대조 → 전부 suspended=판매중지·전부 아님=판매중·섞임=부분판매중·맵에 vid 없음=미상(None). set_sale_status로 저장.
   - **렌더**: `apply_style`의 키워드 소헤더(head) 블록, `is_disc` 처리([workbook.py:883-892]) 뒤 **날짜칸 스타일 루프(L893-894) 다음에**: `if is_disc and self.sale_active(ws.title, nm): 최신날짜컬럼=self._date_col[ws.title][self.latest_date(ws.title)]; ws.cell(kh, 그컬럼).value="판매중"; font=Font(bold=True,color='C00000')`(진한 적색). gsheet 미러링은 값+서식 자동 반영.
4. **⚠판매자배송(개인) 상품**: 재고 API(로켓그로스)엔 isSaleSuspended 없음 → status=미상=깃발 안 뜸(1단계 한계). 소유자 예시(디케이유니버스 디프자동손세정기)가 개인상품이면 **`vendor-inventory/list` API 신규 fetch 필요**(2단계, `fetch_inventory` 패턴). 착수 시 그 상품이 로켓그로스인지 먼저 확인.
5. **검증**: tools/simulate_pipeline.py에 시나리오 추가(대장 판매중지+상태맵 판매중→"판매중" 셀), tools/verify_offline.py 워크북 왕복.

관련 [[seldoc-output-format]] [[inventory-api-rfm-search]] [[input-ledger-format]] [[date-column-run-date-rule]] [[gsheet-unified-spec]]
