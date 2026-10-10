# L1 데이터 백본 — 공개 API 계약 (L1_CONTRACT)

> L2 도메인 / L3 조립이 부르는 **L1 데이터 백본의 공개 진입점**을 계약으로 고정한다.
> 도메인 세션이 병렬로 편집하다 L1 시그니처를 바꾸면(파라미터 추가·삭제·이름변경·필수화, 함수 삭제)
> `tools/pin_l1_contract.py`(run_checks 게이트 편입)가 즉시 빨개진다.
> 계층 정의=`docs/ARCHITECTURE.md`, 운영=`docs/PARALLEL_DEV.md`.
>
> ⚠ 이 목록은 **실측(호출처 grep, 2026-09-28)** 으로 확정 — "도메인/조립이 실제 부르는 것"만 계약이다.
> 계약은 **정직한 최소 표면**이다. 여기 없는 함수는 내부용이니 밖에서 부르지 말 것(부르면 계약 확장 제안).

## 계약을 지키는 법(핀 비교 방식)
- 핀은 시그니처 **전체 문자열**(타입힌트·한글 기본값 표기)이 아니라 각 파라미터의
  **(종류, 이름, 기본값 유무)** 만 비교한다 = 계약 파괴는 잡되 타입힌트 정리 같은 무해한 변경엔 안 깨짐.
- 구조 표기: `P`=위치/키워드 겸용 · `K`=키워드 전용 · `A`=`*args` · `W`=`**kwargs` · `O`=위치 전용, 뒤 `0/1`=기본값 없음/있음.
- **시그니처를 의도적으로 바꿀 때**: 이 문서 + `pin_l1_contract.py` 골든값을 같이 고친다(계약 변경은 명시적으로).

## 1. collector (수집) — 호출처: pipeline_sales
| 공개 진입점 | 파라미터 구조 |
|---|---|
| `discover(page, date_from, date_to, log=None)` | P:page:0 P:date_from:0 P:date_to:0 P:log:1 |
| `fetch_sales_roster(page, date_from, date_to, log=None)` | P:page:0 P:date_from:0 P:date_to:0 P:log:1 |
| `fetch_vendor_inventory(page, log=None)` | P:page:0 P:log:1 |
| `fetch_inventory(page, log=None)` | P:page:0 P:log:1 |
| `fetch_product_ids(page, vendor_inventory_ids, log=None)` | P:page:0 P:vendor_inventory_ids:0 P:log:1 |
| `products_from_vendor_inventory(listings, log=None)` | P:listings:0 P:log:1 |
| `sale_status_by_vid(listings, log=None)` | P:listings:0 P:log:1 |
| `reset_raw()` · `raw_dumps()` | (인자 없음) |
| `kind_of(registration_types)` · `sale_status_of(product_status)` · `vid_meta_of(listings)` | 판정 유틸 |
- 데이터/예외 타입: `VendorInventoryOption`·`VendorInventoryListing`·`SalesFetchError`·`InventoryFetchError`·`VendorInventoryFetchError`.
- ⛔ **`fetch_sales_details` 는 계약 아님**(collector 내부 `discover`/`fetch_sales_roster` 전용). 밖에서 부르지 말 것.

## 2. input_list (입력/대장 파싱·재고 역기록) — 호출처: ui·pipeline·collector·product_match
| 공개 진입점 | 파라미터 구조 |
|---|---|
| `parse_input_list(path)` | P:path:0 |
| `parse_input_rows(rows, strike_grid=None)` | P:rows:0 P:strike_grid:1 |
| `read_ledger_rows(url_or_id, *, store=None, sa_path=None)` | P:url_or_id:0 K:store:1 K:sa_path:1 |
| `write_ledger_inventory(client, wb, on_log=None, *, sheet='셀독리스트')` | P:client:0 P:wb:0 P:on_log:1 K:sheet:1 |
| `validate_input_list(il)` | P:il:0 |
| `build_idf(names)` | P:names:0 (← product_match 가 IDF 가중 사용) |
- 데이터/예외 타입: `Account`·`Product`·`Option`·`InputList`·`InputValidationError`.

## 3. workbook.OutputWorkbook (출력/워크북) — 호출처: pipeline_process·pipeline·pipeline_ranks (ui 는 직접 호출 안 함)
계약 표면 = `OutputWorkbook` 클래스. 핵심 기록/조회 메서드는 파라미터 구조까지, 나머지 실사용 메서드(총 55개)는 존재를 고정.

**핵심(구조 고정):** `load`·`empty`·`save`·`apply_style`·`ensure_product_block`·`set_product_metric`·`set_keyword_rank`·`add_product_keywords`·`reconcile_account`·`delete_account`·`delete_product_block`·`apply_sale_status`.

**실사용 전체(존재 고정, 발췌):** 기록=`set_product_kind/extra/pid/vids`·`set_display_name`·`set_product_account_id`·`set_discontinued`·`set_marketing`·`set_keyword_search`·`set_title_cache`·`ensure_account`·`mark_sales_collected`·`merge_account`·`sync_discontinued_from_ledger`·`reset_date_column`·`clear_sales_stamps`·`pad_keyword_rows` / 조회=`product_keywords`·`has_product`·`products_of`·`account_sheets`·`account_ids_of`·`account_id_of`·`latest_date`·`is_rank_filled`·`rank_suppressed`·`sibling_vids`·`product_vids`·`resolve_block_name`·`blocks_with_registered_name`·`keyword_search`·`title_cache`·`has_marketing`·`product_due`·`account_due`·`status_of`·`representative_of`·`product_account_id`·`product_roster`·`inventory_by_biz`·`data_quality_summary`.
- 전체 목록·골든 구조는 `tools/pin_l1_contract.py`(`WB_CONTRACTS`·`WB_PRESENT`)가 SSOT.

## 4. gsheet_index (계정목록 동기화) — 호출처: pipeline_gsheet·ui
| 공개 진입점 | 파라미터 구조 |
|---|---|
| `roster_from_workbook(wb, stats_gids)` | P:wb:0 P:stats_gids:0 |
| `sync_index(client, desired, *, sheet='계정목록', on_log=None)` | P:client:0 P:desired:0 K:sheet:1 K:on_log:1 |
| `delete_accounts(client, removed, *, sheet='계정목록', on_log=None)` | P:client:0 P:removed:0 K:sheet:1 K:on_log:1 |
| `delete_renamed_accounts(client, renamed, *, sheet='계정목록', on_log=None)` | P:client:0 P:renamed:0 K:sheet:1 K:on_log:1 |
| `read_marketing(client, *, sheet='계정목록')` · `apply_marketing(accounts, marketing_map)` | 직원 마케팅 역머지 |
| `plan_sync(existing, desired)` · `marketing_key(account_id, product)` | 계획·키 |

## 5. gsheet_stats (통계 시트 미러링) — 호출처: pipeline_gsheet
| 공개 진입점 | 파라미터 구조 |
|---|---|
| `push_statistics(client, wb, *, on_log=None)` | P:client:0 P:wb:0 K:on_log:1 |
| `merge_staff_keywords(client, wb, *, on_log=None)` | P:client:0 P:wb:0 K:on_log:1 |
| `read_staff_keywords(client, wb)` · `worksheet_to_requests(ws, sheet_id, index_gid=None)` | 역머지·셀 변환 |

## 6. pipeline_gsheet (구글시트 연동·백업·복원) — 호출처: pipeline·pipeline_ranks·ui
| 공개 진입점 | 파라미터 구조 |
|---|---|
| `push_gsheet(wb, output_url, log, removed_accounts=None, renamed_accounts=None)` | P:wb:0 P:output_url:0 P:log:0 P:removed_accounts:1 P:renamed_accounts:1 |
| `pull_gsheet_keywords(wb, output_url, log)` | P:wb:0 P:output_url:0 P:log:0 |
| `backup_sources(out_dir='output', *, input_url=None, output_url=None, on_log=None)` | P:out_dir:1 K:input_url:1 K:output_url:1 K:on_log:1 |
| `restore_master_from_gsheet(out_dir, url, on_log=None)` | P:out_dir:0 P:url:0 P:on_log:1 |
| `push_ledger_inventory(input_url, log, out_dir='output')` | P:input_url:0 P:log:0 P:out_dir:1 |
| `push_company_stock(stock_url, input_url, log)` | P:stock_url:0 P:input_url:0 P:log:0 |
- `pipeline.py` 가 `push_gsheet`·`pull_gsheet_keywords`·`backup_sources`·`restore_master_from_gsheet`·`push_ledger_inventory`·`push_company_stock` 를 **재수출**(ui·스케줄러·도구는 `coupang_analytics.pipeline.X` 로 씀).

## 6-b. company_stock (회사보유재고 역기록·판매자배송) — 호출처: ui(H_ui 카드/야간)·pipeline_gsheet
| 공개 진입점 | 파라미터 구조 |
|---|---|
| `run_company_stock(stock_url, input_url, *, dry_run=False, on_log=None, stock_client=None, ledger_client=None)` | P:stock_url:0 P:input_url:0 K:dry_run:1 K:on_log:1 K:stock_client:1 K:ledger_client:1 |
- 재고현황 시트→관리대장 '회사보유재고' 열('창고 , 수량개') 역기록. UI [미리보기](dry_run)/[반영] 직접 호출·야간은 `pipeline_gsheet.push_company_stock`(비치명 래퍼) 경유. 실패=예외(폴백 없음)·호출부가 비치명 처리. 설정키 `stock/url`(입력 URL은 기존 `gsheet/input_url`).

## 7. registry 계열 (셀독등록원장) — 호출처: tools 전용(live 미연동·2단계 앱 연계 대비 선고정)
| 모듈.진입점 | 파라미터 구조 |
|---|---|
| `registry.sync(reg, snap, *, now)` | P:reg:0 P:snap:0 K:now:0 |
| `registry.Registry` | 원장 상태 객체 |
| `registry_gsheet.run_sync(client, read_ledger, *, now=None, log=None, dry_run=False, backup_dir='output/백업', lock_path='output/_원장.lock')` | P:client:0 P:read_ledger:0 K:now:1 K:log:1 K:dry_run:1 K:backup_dir:1 K:lock_path:1 |
| `registry_gsheet.run_backfill(client, snapshots, *, log=None, dry_run=False, backup_dir='output/백업', lock_path='output/_원장.lock')` | P:client:0 P:snapshots:0 K:log:1 K:dry_run:1 K:backup_dir:1 K:lock_path:1 |
| `registry_gsheet.load_registry(client)` · `save_registry(client, reg, res, now)` | 읽기·쓰기 |
| `registry_model.parse_ledger(rows, strike_grid=None, sheet='셀독리스트')` | P:rows:0 P:strike_grid:1 P:sheet:1 |
| `registry_gsheet.write_coupang_check(client, checks, *, dry_run=False, on_log=None, lock_path='output/_원장.lock')` **(2단계)** | P:client:0 P:checks:0 K:dry_run:1 K:on_log:1 K:lock_path:1 |
| `registry.previous_password(reg, account_id)` **(2단계·registry_input)** | P:reg:0 P:account_id:0 |
| `registry.to_input_list(reg, as_of=None, *, on_log=None)` **(2단계)** | P:reg:0 P:as_of:1 K:on_log:1 |
| `registry.password_map(reg)` **(2단계)** | P:reg:0 |
| `registry_model.COUPANG_CHECK_VALUES` **(2단계·상수 6종)** | 쿠팡확인 값 오타 방지 |
- ⚠ registry_core/apply/history/rename 는 registry 패밀리 **내부 전용**(외부 호출 없음) — 계약 아님.
- 2단계 신규는 `registry_input.py`(원장→앱 입력 변환)에 구현·`registry.py` 재수출. 호출처=통합(pipeline 2-2 배선)·H_ui(UI).
- **원장 동시 쓰기 잠금(2단계)**: `registry_lock.registry_lock(path='output/_원장.lock', *, wait_sec=None, on_log=None)`(컨텍스트 매니저·OS 파일 잠금·크래시 자동해제)·`registry.RegistryLockError`(재수출). run_sync·run_backfill·write_coupang_check 가 함수 안에서 읽기→비교→쓰기 전체를 잠금(dry_run 제외). **같은 PC 안에서만** 보호(PC간 잠금=운용 원칙: 운용PC 한 대·야간 순차).

## 7-b. rank (순위 조회 프리미티브) — 호출처: 도메인(kw_recommend·kw_metrics)+조립(pipeline_sales·process·ranks·pipeline)
> R4 확정(2026-09-28·DOMAIN_DESIGN §5.3): `rank` 를 `collector` 와 함께 **L1 조회 프리미티브**로 규정.
> 순위를 가져오는 순수 조회 수단(비즈니스 로직 아님)이라 여러 계층이 공유 → "도메인→L1" 합법.

| 공개 진입점 | 파라미터 구조 |
|---|---|
| `warmup(browser)` | P:browser:0 |
| `make_matcher(product_ids=None, vendor_item_ids=None, name_substr=None)` | P:product_ids:1 P:vendor_item_ids:1 P:name_substr:1 |
| `human_type_query(page, text)` | P:page:0 P:text:0 |
| `organic_ranks(browser, keyword, matchers, max_rank=…, mobile=…, log=None, matched_out=None)` | P:browser:0 P:keyword:0 P:matchers:0 P:max_rank:1 P:mobile:1 P:log:1 P:matched_out:1 |
| `organic_ranks_batch(browser, keywords, matchers, max_rank=…, mobile=…, log=None)` | P:browser:0 P:keywords:0 P:matchers:0 P:max_rank:1 P:mobile:1 P:log:1 |
| `organic_rank(browser, keyword, matches, max_rank=…)` | P:browser:0 P:keyword:0 P:matches:0 P:max_rank:1 |
| `extract_items(page)` · `parse_serp_rank(page, matchers, max_rank=…)` | SERP 파싱 |
- 데이터/예외 타입: `SearchItem`·`RankBlocked`.
- **규율**: rank 는 순수 조회만(순위 도메인 고유 로직은 `pipeline_ranks`=조립).

## 7-d. kw 조회 프리미티브 (검색량·자동완성·경쟁신호) — 호출처: 도메인(kw_recommend·D1 분석·D2 소싱)+조립
> U2 확정(2026-10-05·DOMAIN_DESIGN §5.3·R4 동형): `kw_volume`·`kw_suggest`·`kw_metrics` 를 **L1 조회 프리미티브**로 규정.
> 외부 데이터를 가져오는 순수 조회 수단(네이버 검색량·쿠팡 자동완성·1페이지 경쟁 신호)이라 여러 도메인(D1 분석·D2 소싱)이 공유 → "도메인→L1" 합법. **선정/추천 비즈니스 로직(`kw_ai`·`kw_recommend`)은 L2(D1)에 남긴다.**

| 모듈·진입점 | 파라미터 구조 |
|---|---|
| `kw_volume.parse_credentials_file(path)` | P:path:0 |
| `kw_volume.NaverAdApi.related_keywords(self, hint)` | P:self:0 P:hint:0 |
| `kw_volume.NaverAdApi.related_keywords_multi(self, hints)` | P:self:0 P:hints:0 |
| `kw_suggest.fetch_suggestions(browser, prefix)` · `collect_suggestions(browser, seeds, log=None)` | 쿠팡 자동완성 |
| `kw_metrics.page1_competition(browser, keyword)` | P:browser:0 P:keyword:0 |
- 데이터/예외 타입: `kw_volume.NaverAdApi`·`NaverCredentials`·`KeywordVolume` · `kw_suggest.SuggestError` · `kw_metrics.KeywordCompetition`.
- **규율**: kw 조회 프리미티브는 순수 조회만(키워드 선정·점수화·추천 로직은 D1 `kw_ai`/`kw_recommend`). `kw_metrics`→`rank`(L1→L1·§9 밑줄 누수는 별도 정리).

## 7-c. pipeline_sales (로그인 진입점) — 호출처: UI(H_ui)
| 공개 진입점 | 파라미터 구조 |
|---|---|
| `try_login_once(account_id, password, *, on_log=None)` **(2단계)** | P:account_id:0 P:password:0 K:on_log:1 |
- 2-3 [이전 비밀번호로 1회 시도]용 — 한 계정 반자동 1회 로그인(A안·재시도 없음·발견 안 함·비번 로그 금지). `pipeline.try_login_once` 로 재수출. 나머지 로그인 심볼(_login_and_discover 등)은 내부 전용·계약 아님.

## 8. 정리 완료 기록 — 밑줄 진입점의 공개화 (2026-09-28)
소유자 결정으로 "내부용(밑줄) 문패인데 프로덕션이 부르던" 3건을 정식 공개 이름으로 정리:
- `pipeline_gsheet._push_gsheet` → **`push_gsheet`** (호출처 pipeline.py·pipeline_ranks.py + pipeline 재수출)
- `pipeline_gsheet._pull_gsheet_keywords` → **`pull_gsheet_keywords`** (호출처 pipeline.py + 재수출)
- `input_list._build_idf` → **`build_idf`** (호출처 product_match.py)

행동 불변(이름만 변경)·게이트 9종+복잡도 초록으로 확증.

## 9. 남은 계약 누수(정리 후보 — 별도 사이클)
아래는 **테스트/도구**가 L1 내부 심볼(밑줄)에 의존하는 경우다. 프로덕션 계약은 아니나 정리 대상:
- `gsheet_stats.py` 가 `workbook`(=workbook_common) 내부 상수/함수 `_COL_KW`·`_COL_METRIC`·`_COL_NAME`·`_LABEL_DATE`·`_LABEL_KEYWORD`·`_SPECIAL_SHEETS`·`_key` import.
- `registry_model.py` 가 `input_list` 내부 심볼(`_alias_index`·`_find_header_row`·`_is_discontinued` 등) import — registry 패밀리 내부지만 밑줄 의존.
- `kw_metrics.py` 가 `rank._load_results`(밑줄) 직접 import — rank·kw_metrics 둘 다 L1 조회 프리미티브(2026-10-05·U2)라 이제 **L1 내부 의존**(계약 위반 아님)이나 밑줄 심볼이라 `load_results` 공개화는 여전히 정리 후보.
- `registry_apply.py` 가 `product_match._base_name`(밑줄)·`company_stock.name_key` import — 매칭 규칙 1(색상별)·4(이름 정규화)를 원장 이름변경 감지에 **같은 규칙으로 한 곳에서** 재사용(2026-09-29). `_base_name` 공개화(또는 공용 규칙 모듈로 승격)가 정리 후보.
- 도구: `collector._raw_add`·`OutputWorkbook._FILL_*`/`_key`/`_date_col`·`gsheet_index._auto_cells_request` 등을 pin/verify 도구가 직접 참조.

SSOT = 이 문서 + `tools/pin_l1_contract.py`(골든값·자동 검증).
