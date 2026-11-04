커버리지: D:\coupang-analytics\docs\DECISIONS.md 867~1020행 전체 열람(파일 끝, 1021행은 빈 줄) · 판정 블록 22개(D-121~D-142, 파일 순서 D-141 → D-140 → D-142) · 코드 대조 = 현재 작업 트리(src/, ui/, tools/, designs/, git 밖 output\_분석_261013\정산스크립트\) 읽기만 · 시험 실행 안 함

## 요약
- OK 15 · MARK_MISSING 6 · STATUS_MISSING 1 · STALE 0 · MISMATCH 0 · OWNER_POLICY 0
- OK 외: D-121, D-124, D-126, D-128, D-135, D-137 (MARK_MISSING) · D-138 (STATUS_MISSING)
- 구간 밖 부수 발견: D-119 도 같은 표기 누락(아래 D-137 항목)

## OK 표

| D번호 | 태그 | 근거(파일:행 또는 식별자) |
|---|---|---|
| D-122 | PROMO_START_COLUMN | promo_sheet.py:15 `_START_COL`, :39 `_start_iso`, :59 `parse_promo_rows`, :122 `max(...)` 가장 최근 회차 · tools/verify_offline.py:1760 [13b] · D-086 상태 줄 표기 있음(DECISIONS.md:624). 비고: `patch_promo_start.py` = 일회용 scratchpad 오탐 |
| D-123 | LOGIN_PW_TRIM_ALL_AND_24H_BLOCK | pipeline_sales.py:203 후보 strip·중복 합침 · login_today.py:27 `BLOCK_HOURS = 24`, :74~76 `_blocked`·`fp_at` · settlement_accounts.py:68 비교 전 strip · 호출처 3곳 같은 함수(pipeline_sales.py:108, tools/settlement_download.py:210, transfer_login.py:172) · D-068 상태 줄 표기 있음(DECISIONS.md:500) |
| D-125 | ADCENTER_NAV_SETTLE | settlement_evidence_web.py:33 `NAV_RETRIES = 4`, :280 `_eval_settled`, open_adcenter `/relay/` 벗어남 30초 대기·PwTimeout 기록 후 진행 · tools/verify_settlement_runtime_offline.py:1681 P44 |
| D-127 | STATEMENT_NEG_COLUMN_NOTE | git 밖 statement_managed.py:609~611 `neg_note`, :624 '※ 마이너스 사유는 아래 G 설명', :625 높이 max(34, 16×줄 수). 비고: 본문 '배분은 바꾸지 않음'은 이 결정의 범위 설명이라 D-140 ⑤ 와 모순으로 보지 않음. 오탐: statement_managed*.py = git 밖 |
| D-129 | SALES_RECORD_INVENTORY_ID | report.py:52 `inventory_id` · collector.py:271 · sales_history.py:64 '등록상품ID' · sales_summary.py:95, :102 `_before_inventory_id`(M: 만 재조회). 오탐: 판매현황_집계 xlsx = 소유자 파일 |
| D-130 | SALES_SUMMARY_OWN_PRODUCTS | workbook_sales_dash.py:114 '셀독 관리 상품', :153 `_own_lines`, sales_dashboard.py:222 `sales_scale`(ID 수·매출 발생·no_id). 대체 부분은 상태 줄에 표기됨(D-131·D-132) · `scope(outside=)` 삭제 확인 sales_summary.py:140. 오탐: `own_scale` = D-139 가 `sales_scale` 로 대체 |
| D-131 | SALES_SUMMARY_CUMULATIVE_RECEIVED | sales_dashboard.py:190 `cumulative`, :204 `_month_received`, :69 `cum` · workbook_sales_dash.py:143 `_cum_text` · tools/verify_sales_summary_offline.py:620 T13. 오탐: `own_scale` 동일 |
| D-132 | SALES_SUMMARY_OWN_INCLUDES_MANAGED | 남은 부분 = 결과 계정 전체 범위: workbook_sales.py:82 `all_d, all_p`, :89 · 상태 줄 표기 정확(소제목 → D-136, 안 나온 관리 상품 → D-139). `unseen_products`·`own_scale` 저장소 전체 검색 0건(DECISIONS 제외) = 의도된 삭제(D-139) |
| D-133 | SALES_SUMMARY_OWN_CATALOG_COUNT | SUPERSEDED by D-136 표기 있음 · `record_catalog|load_catalog|등록상품수\.json` 저장소 전체 검색 0건(DECISIONS 제외) = 물리 삭제 확인. 오탐: missing_* 전부 의도된 삭제 |
| D-134 | LEDGER_GSHEET_FAIL_STOP | ui/registry_ui.py:21 `auto_load_input` · ui/app_qt.py:1226, :1641~1644 무인 종료 · input_list.py:73 `from_file`, :586 · pipeline.py `_reconcile_ledger_accounts` from_file 건너뜀 · tools/verify_offline.py:2421, :2480. 비고 2건은 아래 '확인 필요' |
| D-136 | SALES_SUMMARY_OWN_ANALYTICS_COUNT | workbook_sales_dash.py:157 소제목 원문 일치 · sales_scale 달 기록 전체 ID 수 · 대체 부분 상태 줄 표기됨(D-139). 오탐: `own_scale`·`unseen_products` = D-139 삭제 |
| D-139 | SALES_SUMMARY_TWO_SCALES_ANALYTICS | sales_dashboard.py:222 `sales_scale`, :67 `mine` · workbook_sales.py:88~89 범위만 다른 두 호출 · workbook_sales_dash.py:128~131 계정목록 괄호, :137 `_count_text` · tools/verify_sales_summary_offline.py:580 T12 · designs/SALES_SUMMARY.md:54 일치. 오탐: `unseen_products` = 이 결정이 삭제 |
| D-141 | COMPANY_STOCK_PALLET_FORMAT | company_stock.py:67 `_stock_columns`, :79 `_split_pallet`, :91 `read_stock`(같은 창고 합산) · tools/verify_registry_offline.py:869~872 새 양식 시험 |
| D-140 | STATEMENT_DEDUCTION_SCOPE | git 밖 managed_alloc.py:110 `scoped` · statement_managed.py:227 `_month_add`, 관리 시작 `start`·`since_ad`, `put`(1% 이하 '실값'·'일부 추정'·'추정'), `a_m * 1.1`, :669 '공제 완료분·공제 예정분'. 오탐: 스크립트·백업·결과 폴더 = git 밖(스크립트 실재 확인) |
| D-142 | DECISIONS_INDEX_FROZEN_SPLIT | docs/decisions/frozen-pre-2026-10-08.md 136,122B(결정 본문 값과 일치) · docs/DECISIONS_INDEX.md 있음 · DECISIONS.md:127 안내 줄 · CLAUDE.md:7 ⑤ · 둘 다 스테이지됨(git status A/M). 오탐: `decisions-index.py` = 전역 훅 ~/.claude/hooks 에 실재 · frozen 파일 실재 |

## OK 외 항목

### D-121 [PROMO_START_FADE_7D]
- 판정: MARK_MISSING (대체: D-122, 범위: 시작일 대체 출처 '요청일')
- 원문 인용: D-121 "없으면 관리대장 '체험단' 시트 요청일(D-086 자동 시작일·체험단효과와 같은 기준)" / D-122 "요청일로 대신하지 않음", "사업자 시트 7일 배경(D-121) 모두 이 값 기준"
- 코드 근거: 7일 배경 자체는 유효 — workbook_render.py:24~25 `_PROMO_BASE`·`_PROMO_DAYS`, :400, :411 `_promo_fills`. 시작일 값은 promo_sheet.py:15 `_START_COL`('체험단시작일') 기준. D-122 상태 줄은 D-086 만 언급.
- 제안: D-121 상태 줄에 `ACTIVE (부분 SUPERSEDED by D-122 — 자동 시작일 = 요청일 부분)` 표기
- 비고(오탐): `_promo_cols` = D-121 이 물리 삭제한 식별자. workbook_common.py:83 `mkt_fill` 은 `_IdxStyle`(계정목록) 소속이라 삭제 대상 `_StyleCtx.mkt_fill` 과 다름.
- 확신도: 높음

### D-124 [STATEMENT_LAYOUT_RECONCILE]
- 판정: MARK_MISSING (대체: D-140, 범위: ③ 줄별 공제 배분)
- 원문 인용: D-124 ③ "공제 = 그 줄에서 실제 빠진 항목 × 항목 관리 비율" / D-140 "D-124 ③·D-119·D-137 의 비율 적용 부분을 대체."
- 코드 근거: statement_managed.py `put` → `MA.scoped`(상품별 자료 금액 그대로, 자료 없는 공제만 비율), 상품별 자료 없는 항목만 줄별 `line_rt`.
- 제안: D-124 상태 줄에 '③ 공제 배분 SUPERSEDED by D-140' 추가. 현재 표기는 'SUPERSEDED by D-126 (…이어받음)'으로 전부 대체처럼 읽히나 실제로는 부분 대체이므로, 형식을 `ACTIVE (부분 SUPERSEDED by D-126 — …· D-140 — …)` 로 맞출지 함께 판단 요청. 상태 줄 '줄별 배분 … 이어받음' 문구가 D-140 뒤로는 일부 맞지 않음.
- 비고(오탐): statement_managed.py·견본 xlsx·폴더명 식별자 = git 밖.
- 확신도: 높음(대체 사실) · 중간(형식 변경 제안)

### D-126 [STATEMENT_AG_FLOW_FASTPAY]
- 판정: MARK_MISSING (대체: D-140, 범위: F 표 칸 제목)
- 원문 인용: D-126 ③ "F 쿠팡 공제 내역(빠른정산 제외 | 입금 완료분·입금 예정분·합계)" / D-140 ⑥ "F 쿠팡 공제 내역 칸 제목 = 공제 완료분·공제 예정분(돈이 들어온 것이 아님)"
- 코드 근거: statement_managed.py:669 `("공제 완료분", "공제 예정분", "합계")`. 입금 완료분·입금 예정분 문구는 스크립트 검색 0건. 나머지 핵심 유지: :597 제목, :681 참고 묶음, :511 `SumMismatch`, :675~677 빠른정산 두 줄, :168 `totalArFactoringDeductionAmount`, :48 '빠른정산 계좌인출액' · '서명|용어 풀이' 검색 0건(⑥ 삭제 확인).
- 제안: D-126 상태 줄에 `ACTIVE (부분 SUPERSEDED by D-140 — F 표 칸 제목)` 표기. D-140 본문의 대체 목록에는 D-126 이 없으므로 범위는 소유자 승인 시 확정.
- 비고: D-126 영향 범위의 '(추정)' 표기 대안 '소유자 답 대기'는 STATE 다음 작업 7에도 남은 미결이며 이 감사에서 판정하지 않음.
- 확신도: 높음

### D-128 [SALES_SUMMARY_SCALE_ROWS]
- 판정: MARK_MISSING (대체: D-139, 범위: '관리 상품 등록 수' 산출 기준)
- 원문 인용: D-128 "관리 상품 등록 수 = 같은 로스터의 상품 줄(다중옵션 2차 블록 제외·판매중지 포함)" / D-139 버린 대안 "D-128 '관리 상품 등록 수 = 계정목록 수'(소유자 '2가지 모두 판매분석')"
- 코드 근거: workbook_sales_dash.py:128~131 — 값 = `d.mine` 의 `ids`(판매분석 등록상품ID 수), 로스터 수는 괄호 `계정목록 {prods}개`. workbook_sales.py:88. 현재 상태 줄은 D-131 만 언급. 계정 수·로스터 집계(`managed_counts` workbook_sales.py:58)는 유지.
- 제안: D-128 상태 줄을 `ACTIVE (누적 매출금액 계산 SUPERSEDED by D-131 · 관리 상품 등록 수 값 SUPERSEDED by D-139 — 로스터 수는 괄호 표시로 유지)` 로 표기
- 비고: STATE 의 'D-132·D-133·D-136 왕복 후 확정'에서 이 세 항목의 표기는 정확했고, 누락은 왕복 대상 밖이던 D-128 쪽이다.
- 확신도: 높음

### D-135 [INDEX_ACCOUNTS_FROM_LEDGER]
- 판정: MARK_MISSING (후속 해소: D-139, 범위: 본문 '미결' 한 건. 결정 내용 대체는 아님)
- 원문 인용: D-135 "미결: 대장에 있으나 쿠팡 등록·매칭이 안 된 상품 줄 … 계정목록에 표시할지는 소유자 확인 후 결정." / D-139 "대장에만 있고 쿠팡에 안 맞는 줄은 넣지 않음(D-135 미결 해소)."
- 코드 근거: 핵심 동작은 유지 — workbook_lifecycle.py:125 `roster_only_accounts`, pipeline.py:354, gsheet_index.py:371 `_title_request`, tools/verify_offline.py:2457, tools/verify_gsheet_offline.py:369.
- 제안: D-135 상태 줄에 `ACTIVE (미결 항목은 D-139 에서 해소)` 표기. 본문 수정 금지라 상태 줄만.
- 확신도: 중간(분류상 '대체'가 아니라 '미결 해소'이므로 표기 필요 여부는 판단 대상)

### D-137 [STATEMENT_REAL_AD_MILK_RULES]
- 판정: MARK_MISSING (대체: D-140, 범위: 비율 적용 부분 — 정확한 범위는 확인 필요)
- 원문 인용: D-140 "D-124 ③·D-119·D-137 의 비율 적용 부분을 대체." / D-137 상태 "- 상태: ACTIVE"
- 코드 근거: D-137 ①② 는 코드에 살아 있음 — managed_alloc.py:63 `ad_share(… have)`, :94~95 캠페인 없는 조정·못 받은 달 제외. ③ statement_managed.py:126 `_txt_num`, :134 `_milk_rows`. 바뀐 것은 그 결과를 쓰는 방식 — `put(AD, since_ad, a_m * 1.1, …)` 로 관리 금액을 그대로 쓰고 `MA.scoped` 로 자료 없는 공제만 비율 적용. ④~⑥ 은 재생성 운영 절차로 코드 판정 대상이 아니며 모순 없음.
- 제안: D-137 상태 줄에 `ACTIVE (부분 SUPERSEDED by D-140 — 비율 × 계정 전체 공제 적용 부분. ①~⑥ 규칙 자체는 유지)` 표기. '비율 적용 부분'이 어디까지인지 정산 세션 또는 소유자 확인 후 문구 확정.
- 부수 발견(구간 밖): D-119(DECISIONS.md:853~858)도 상태 줄이 '상태: ACTIVE' 뿐이고 D-140 의 대체 언급이 없음. 같은 표기 필요. D-119 담당 구간 결과와 대조 요망.
- 비고(오탐): managed_alloc·test_managed_alloc = git 밖.
- 확신도: 높음(표기 누락) · 중간(범위)

### D-138 [AD_REPORT_TEXT_RESPONSE]
- 판정: STATUS_MISSING
- 원문 인용: 988~992행 뒤 바로 빈 줄·D-139. 색인도 'D-138 ?' (docs/DECISIONS_INDEX.md:143)
- 코드 근거: 결정 동작 전부 존재 — settlement_ads.py:83 `report_xlsx`(PK 그대로, 칸 4개 확인, 실패 시 `SiteChangedError`), :169 호출 · tools/settlement_download.py:384 `_get_bytes(text_ok)`, :387, :509 보고서 받기에서만 `text_ok=True` · tools/verify_settlement_runtime_offline.py:1757 P45. 뒤 항목의 대체 없음(`D-138` 전체 검색: 제목 줄뿐). STATE 8행 배포본 포함 기록.
- 제안: D-138 끝에 `- 상태: ACTIVE` 추가. 라이브 미실측·운용 PC 미설치는 본문에 이미 있음(STATE 첫 실행 확인 항목 4).
- 확신도: 높음

## 확인 필요(분류 밖 관찰, 위 판정에 영향 없음)
- D-134 / ui/app_qt.py:560 입력 칸 안내문 "비우면 PC 엑셀 사용": 현재 동작은 소스가 gsheet 면 링크 없음 = 오류·실행 안 함(registry_ui.py:21 이하, verify_offline.py:2438 ("gsheet", "")). 안내문이 D-134 와 달라 보임. 코드 동작은 결정과 일치하고 문구만 낡은 것으로 추정. 확신도 중간.
- D-134 / 소스 미설정 경계: `auto_load_input` 은 src 가 빈 값이면 PC 엑셀로 내려감. app_qt.py:574~576 의 '미설정 = gsheet' 저장은 설정 탭 생성 때 실행되고, 호출 순서상 :203 자동 로드가 탭 생성(:230)보다 앞이라 설정값이 한 번도 없는 첫 시작에서는 PC 엑셀로 읽을 가능성이 있음. 코드 읽기 기반 추정이며 실행 확인 안 함. 설정이 저장된 운용 PC 에는 해당 없음. 확신도 낮음.
- D-140 남은 사실 '관리 시작 달은 자동 판정이라 계약 시작일과 다를 수 있음(미대조)'은 본문에 미해결로 기록돼 있어 판정 대상에서 뺐다. 필요하면 소유자에게 물을 항목.
