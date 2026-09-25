---
name: seldoc-output-format
description: "출력 서식 = 셀독(시트=사업자, 상품블록 계약/개인, 키워드 노출순위 PC, 재고현황, 일자 가로)"
metadata: 
  node_type: memory
  type: project
  originSessionId: e9438a2f-e201-48d4-bf71-5cdf2500b598
  modified: 2026-09-23T04:08:39.532Z
---

출력 워크북은 **셀독 서식**(사용자 `셀독 판매 데이터_서식.xlsx` 기준, 2026-09-08 전면 재설계). `workbook.py` 새로 작성.

- **시트 = 사업자명**(계정), 한 시트에 상품 블록 여러 개 세로로.
- 열: A=상품구분(계약/개인)·사업자명 · C=상품명/키워드 · F=검색량 · **G=지표라벨** · H~=일자(가로 누적).
- 상품 블록: 헤더(구분·상품명·날짜) + 지표행 — **계약(로켓그로스)=판매량·방문자·노출량·재고현황**,
  **개인(판매자배송)=전체판매량·전체노출량** + 키워드 소헤더 + 키워드별 **노출순위(PC 단일)**·검색량.
- **상품구분은 API로 자동 판별**: vi-detail-search registrationType RFM=계약, NORMAL=개인.
- **재고현황=판매가능 재고수량**(로켓그로스). rfm-inventory API 직접조회 **배선 완료**(2026-09-08) — [[inventory-api-rfm-search]].
- **모바일 노출순위 제외**(`config.RANK_INCLUDE_MOBILE=False`) — 단 `rank._set_mobile`/`organic_ranks(mobile=)` **모듈은 보존**(재사용).
- **키워드 동결**: 시트에 키워드 있으면 AI 선정 건너뛰고 순위만(carry-forward). 발굴 추가(grow)는 상한7·하루2.
- **키워드 없어도 4 순위행 유지(2026-09-15 사용자 요구)**: `ensure_product_block`은 키워드가 `KW_TRACK_N`(=4) 미만이면 **이름 공란 + `M_RANK` 인 빈 순위행으로 4행을 채움**(키워드 없어도 블록 4행 유지·공란 OK). 빈 행은 `_kw_row`에 안 잡혀(로드 조건 `M_RANK and name`) '키워드 없음' 판정 유지→②가 선정. `add_product_keywords`는 새 행 삽입 전 **빈 행부터 재사용**(`_kw_block_rows`로 탐색·블록 4행 초과 팽창 방지). 또 **`pad_keyword_rows(min_rows=KW_TRACK_N)`** 신설. **빈행 대신 실제 키워드로(추가 요구)**: `select_keywords_stage`가 4개 미만 상품을 **KW_TRACK_N까지 보충 선정**(동결분 제외·부족분만·grow는 상한7) 후 남은 자리만 빈행 패딩. 4개 이상 동결. 전체실행은 키워드 없는 상품도 ②산정→③순위(①→②→③). **적용완료 2026-09-15(② 라이브 2회)**: 전 상품 4행(실제 키워드 4개=100상품), 실키워드 4미만 2상품뿐(와사비잎 3=니치·토탈사이언스 0=브랜드명뿐 앵커불가→수동)·마스터·구글시트 반영.
- 순위는 **상품 단위**(옵션 통합 매처). 점수/등급/진단/권고제목은 서식에 안 넣고 **로그로만** 제공(참고용).
- **시각 서식**(`apply_style`, 2026-09-08): 병합(제목 A:G·지표블록 구분 A:B/상품명 C:F 세로·키워드명 C:E 가로)·팔레트(상품명 상품군 배경=**살구 FBE2D5 ↔ 민트 E2EFDA 교대**, G지표라벨·순위=**연파랑 D9E9FA**, 키워드소헤더·비고=**회색 E8E8E8**)·thin 테두리·맑은 고딕·`#,##0`·freeze H2·**상품 상하 굵은(thick) 구분선**(하단은 다음 빈행 top으로 — 병합 하위셀 border 유실 회피). ⚠ 서식파일 `셀독 판매 데이터_서식.xlsx`는 **한컴 셀**(openpyxl `IndexError`로 못읽음 → zip raw XML 파싱).
- **상품군 배경색 교대(2026-09-23·소유자, 커밋 2e78b49)**: 같은 등록상품명(대표+옵션 변형) = 한 상품군 = 한 배경색, 인접 상품군은 살구↔민트 교대로 **시각 구분**. 그룹 판정=`_style_block_edges` 굵은선 그룹과 동일(regs 연속). `_StyleCtx.f_prod2`·`_style_metric_rows(prod_fill)`. 핀 pin_apply_style[S8]. ⚠아래 "서식 영구 고정" 원칙의 **소유자 승인 예외**(색만 추가·구조/병합/테두리 불변).
- **상품ID 저장**: `_상품ID` **숨김시트**에 (사업자,상품)→vendorItemId 매핑(`set_product_vids`/`product_vids`) — ③ 순위조회의 상품 매칭용. [[pipeline-3stage-separation]].
- **목차 시트**(2026-09-12 `f07ed7f`·`f284d0e`, 대안 A): 첫 시트 `계정 목록` = 전 계정 하이퍼링크 점프(`#'사업자'!A1`)+요약. `apply_style` 끝에 `_build_index()`가 멱등 재생성. **열=대표자·사업자·상품명(링크)·계정ID·체험단3·상태(2026-09-17 대표자 컬럼 A 추가, 8열)**. 계정ID·대표자는 숨김 `_계정정보` 시트((사업자)→계정ID 2열·판매수집일 **3열**·**대표자 4열**, `set_account_id`/`account_id_of`·`set_representative`/`representative_of`, pipeline `_finish`·목차 로스터에서 저장). ⚠대표자는 4열(3열 판매수집일과 충돌 회피). ⚠️**비밀번호는 어떤 경우도 출력 워크북에 저장·표시 금지**(공유·gdrive 업로드 산출물 → DPAPI credstore만). 특수시트 `_SPECIAL_SHEETS=(_상품ID·목차·_계정정보)`는 `account_sheets`·`_reindex`·`apply_style`·simulate `_sheets`에서 일괄 제외. 계정 많을 때(100개) 탐색용.
- **마케팅 기능**(2026-09-12 `ae05d2b`~`8a00ae4`): **계정 목록=상품 단위**(사업자·상품명(→블록 헤더행 링크)·계정ID·**마케팅 시작/종료/모니터링종료(노랑칸 직접입력)**·상태·순위공란). 입력은 숨김 `_마케팅` 시트에 보존(`_sync_marketing_from_index`가 재생성 전 회수, 헤더 가드로 옛 레이아웃 오독 방지). 상태=예정/마케팅중/모니터링/종료(`_mkt_status`, `_parse_date` 유연). **효과**: 사업자 시트 키워드 소헤더 **비고(G)** = 마케팅중이면 '🔴 마케팅중'(멱등, kh 탐지를 C='키워드'만으로 변경) + **마케팅 시작~종료 일자컬럼 배경 연주황(FCE4D6)**. **수집주기**(`account_cadence`/`account_due`, run_full 1차패스 게이팅): 마케팅+1개월 상품 있으면 계정 매일·그외 3일1회·모니터링종료후 중단. ⚠ **마케팅 설정 있을 때만(`has_marketing()`) 게이팅**(미설정=현행 매일). 특수시트에 `_마케팅` 추가.
- **순위 공란 원인**(2026-09-12 확인): 공란=미측정(다음 ③ 재측정 대상)이지 '순위 없음' 아님(순위없음=`50위` 기록). ①vid 없는 상품=전부 공란(그날 미활동/판매수집 미완, 최다), ②vid 있는 상품 부분공란=③이 키워드 순서대로 재다 차단/중단→뒤쪽 키워드부터 공란. 개선=vid 커버리지↑(재고 API 상품명필드 확인 후 대장매칭, `fetch_inventory`에 구조 진단로그 추가됨)·③ 완주.
- **이름칸 2줄화**(2026-09-11 `ff51dd2`): 헤더 C = **1줄 쿠팡 full 제목 + 2줄 vendorItemId**, C 폭 10→36. ⚠️C 셀 값은 상품 **키**(시계열 정체성)인데 실제로 **내부 개행 상품명**이 있어(`…\n\n(&picks…)`) '첫 줄 파싱' 금지 → 이름/vid를 **보이지 않는 구분자 U+2063(`config.NAME_ID_SEP`)** 로 분리, 키=항상 구분자 앞(`workbook._key`). `_display_name`(제목⟨SEP⟩\nvid)을 **`apply_style`이 저장 직전 렌더링**(멱등; vid는 저장시점 확정이라 `ensure_product_block` 시점 아님). `_reindex`·`set_display_name`은 `_key` 기반. vid 없으면 이름만 1줄. C 셀을 상품명으로 읽는 모든 코드(검증도구 포함)는 `NAME_ID_SEP` 앞부분을 취할 것.

**⚑⚑ 서식 영구 고정 — 절대 원칙(2026-09-10 재확인): 어떠한 경우에도 서식 포맷을 변경하지 말 것. 데이터만 바뀐다.** 워크북을 수정·저장하는 모든 코드(파이프라인 단계·복구도구·신규 스크립트)는 저장 직전 반드시 `wb.apply_style()`를 호출해 샘플 첫시트 표준으로 수렴시킨다. 셀 너비·병합·테두리·행높이·틀고정을 개별적으로 건드리는 코드를 새로 추가하지 말 것(항상 apply_style 한 곳에서만 관리). 이 규칙 위반이 "시트마다 서식 섞임"의 유일한 원인이었음.

**⚑ 서식 영구 고정(2026-09-10 사용자 요청 `6030ab4`) — 절대 원칙: 포맷 고정, 데이터만 변경:**
- 표준 = **샘플 `쿠팡데이타분석_통계_샘플 서식.xlsx` 첫 시트**(한컴 저장본, openpyxl 못읽음 → raw XML로 추출). 열너비 A11·B6·C10·D9·E9·**F13.75**·G14·H(일자)11, **제목행 높이 21**, 틀고정 **H2**(A~G·1행 고정, H~ 일자만 오른쪽 스크롤 누적).
- **`apply_style` 멱등화**: 각 시트 기존 병합 전부 해제(희소 병합셀은 정규 Cell로 먼저 실체화해 unmerge KeyError 방지) 후 표준대로 재병합 → 몇 번 돌려도 동일 서식으로 수렴. 시트마다 병합·테두리·너비 섞이던 문제 원인=②/③/반영이 저장 시 apply_style 미호출이었음 → **select_keywords_stage·track_ranks_stage·tools/reflect_log_to_excel 모두 저장 전 apply_style 호출**(run_full은 원래 완료 시 호출). ⚠ **워크북 수정 후 저장하는 모든 신규 코드는 반드시 저장 전 `wb.apply_style()` 호출**할 것.
- 순위 표기: 찾으면 `N위`, **못 찾으면 `{그 페이지에서 센 개수}위밖`**(예 '44위밖'·'59위밖' — 소유자 2026-09-23·커밋 1d18c72·`set_keyword_rank(scanned=)`; 옛 '50위 고정'은 A-1 버그로 폐기). `-`(구 placeholder)·차단/미측정은 `is_rank_filled`가 미채움→③ 재측정. [[bugfixes-260923-source-review]].

**Why:** 사용자 실제 관리 서식. **How:** config M_*/CONTRACT·PERSONAL_METRICS/KIND_*, workbook `ensure_product_block(kind, keywords)`·`set_product_metric`·`set_keyword_rank/search`·`apply_style`. 관련 [[daily-stats-keyword-freeze]] [[sales-data-api-vi-detail-search]] [[coupang-search-prime-then-fetch]] [[pipeline-3stage-separation]].
