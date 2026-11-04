# D-091~D-120 감사 결과

커버리지: docs/DECISIONS.md 654~866행 전체(213행) 열람, 대체 확인용 867~1020행 전체 열람, 판정 블록 30개(대조 기준 커밋 162e378, 저장소 수정·실행 없음).

| 분류 | 개수 | D번호 |
|---|---|---|
| OK | 18 | D-091, 096, 097, 099, 100, 101, 103, 104, 105, 107, 109, 110, 112, 113, 114, 115, 118, 120 |
| STATUS_MISSING | 2 | D-093, 102 |
| MARK_MISSING | 9 | D-092, 094, 098, 106, 108, 111, 116, 117, 119 |
| OWNER_POLICY | 1 | D-095 |
| STALE | 0 | - |
| MISMATCH | 0 | - |

경로 생략: `src/…` = `src/coupang_analytics/`, `git밖/` = `output/_분석_261013/정산스크립트/`(git 추적 안 함, 파일 존재는 실제 확인).

## OK 표

| D번호 | 태그 | 근거(파일:행 또는 식별자) |
|---|---|---|
| D-091 | SETTLE_NO_DUP_RUN | src/settlement_watch.py:70 `already_done`(키 같음 또는 완료 키 ≥ cycle_start) · tools/settlement_download.py:788 · src/app_process.py:186,205 `remove_legacy_settlement_task`(prepare_auto_start 안) · P36 존재 |
| D-096 | KW_VOLUME_DAILY_REFRESH | src/pipeline_process.py:18 `_refresh_search_volumes` · src/pipeline.py:849 호출(`_select_product_keywords` 안) · workbook.py:514 무조건 덮어씀 · `_fill_frozen_search_volumes` 검색 0건(대체 완료) |
| D-097 | SALES_BACKFILL_60 | src/sales_summary.py:18 `BACKFILL_PER_DAY = 60` · 뒤 항목 변경 없음 |
| D-099 | SALES_MISSING_NAMES | src/sales_dashboard.py:102,107 · src/workbook_sales_dash.py:96,179,213~216 · src/workbook_sales.py:178 `_missing_names` |
| D-100 | REGISTRY_RENAME | 코드 `셀독등록원장` 검색 0건(src·ui·tools .py) · `셀독계정상품이력관리원장` 24건 · src/registry_model.py:20~24 시트 이름 5개 유지 · designs/LEDGER_REGISTRY.md:5 |
| D-101 | SALES_RANK_ALL_ACCOUNTS | src/workbook_sales_dash.py:184~218(전 계정·`i if a.amount else "-"`·미수집 회색) · src/sales_dashboard.py:266 정렬. 비고: 같은 파일 3~4행 머리 주석 '판매 없음·미수집 한 줄씩'은 낡은 주석(코드엔 '판매 없음' 줄 없음) |
| D-103 | SETTLE_ACCOUNTS_FROM_REGISTRY | src/settlement_accounts.py:106 `SYNC_MAX_AGE_H = 26`,:123 `accounts_from_registry` · tools/settlement_download.py:133~138,:716~718(종료 ❌ 이유) · src/registry.py:63,90 · src/registry_model.py:95 · src/registry_settle.py:15~16 · tools/registry_settle_import.py 존재 |
| D-104 | SALES_CHART_NO_OVERLAP | src/workbook_sales_dash.py:29~30 `XL_ROW_PT = 15`·`G_ROW_PX = 20`,:192,:283~293(rows−1 × 행 높이) |
| D-105 | SALES_FROM_APRIL_MONTHLY | src/sales_summary.py:15 `FIRST_DAY` · `BACKFILL_FROM` 코드 0건(tools/verify_sales_summary_offline.py:51 '없음 확인' 1건뿐) · src/sales_dashboard.py:242 `_month_kpis` · src/workbook_sales_dash.py:99~104. D-128·D-131은 ① 맨 위에 줄 추가로 월별 누계 줄과 충돌 없음 |
| D-107 | SALES_SCOPE_WHOLE_LISTING | src/sales_summary.py:127,140 · src/workbook_sales.py:81~84. D-139가 같은 범위 승계 |
| D-109 | INDEX_DROP_PROMO_END | src/gsheet_index.py:27~33 `N_COLS = 9`,:323 `_HEADS`,:327,:629,:648,:433,:475 · :861 호출. D-122는 시작일 값의 출처만 변경(열 구조 무관) |
| D-110 | SALES_RANK_RECENT_MONTH | src/sales_dashboard.py:19,85,171(key 없이 일별 합만) · src/workbook_sales_dash.py:188~200 · tools/build_staff_manual.py:213 |
| D-112 | TRANSFER_LOGIN_NIGHT | src/transfer_login.py:29~30,109,120,129,144,183,208 · tools/settlement_download.py:834 `--start`. 비고: 같은 파일 4행 주석 'D-068 그날'은 D-123 뒤 낡은 표현 |
| D-113 | SHEET_LINK_ABSOLUTE | src/gsheet.py:40~47 · src/gsheet_index.py:159 · src/gsheet_stats.py:137,251 · 상대 `#gid` 실사용 0건(주석만). 비고: 프로그램 후보 `gsheet.sh`는 오탐(`gsheet.sheet_link` 잘림). 수정 뒤 휴대폰 실측 결과는 CLAUDE.md:96 에 '휴대폰 웹은 탭은 열리나 행 위치는 무시'로만 있음 — 앱 실측 기록은 찾지 못함(검색어 `모바일`: STATE.md·DECISIONS 807행 이후 해당 없음) |
| D-114 | RANK_INCLUDE_REJECTED | src/workbook_common.py:112 · src/workbook_meta.py:265~275 · pin S7 |
| D-115 | WING_CYCLE_EXTRA | src/settlement_wing_api.py:39,94~97,126 · tools/settlement_download.py:299 · P38 |
| D-118 | SETTLE_SNAPSHOT_WINDOW_DEDUP | git밖/settlement_ledger.py:41 `rg_window_overlap`,:214 70:30 검산 · git밖/run_statements_at.py · 정정 폴더·지급예정_정정표 실재. 비고: 후보는 전부 오탐(git 밖). `collect_snapshot.py`는 찾지 못했으나 '1회용' 근거 서술일 뿐. 미결 사실: '17계정 정정 통보 필요(소유자 확인)'가 STATE.md에 없음 — 통보 여부 확인 필요 |
| D-120 | SETTLE_COLLECT_SAFETY | src/settlement_ads.py:`MAX_MONTHS = 2`·collect `call_/bytes_/report_` 앞 gap·'남은 달' · src/settlement_verify_collect.py:95,113~121,144~147 · tools/settlement_download.py:488,509,512 |

## OK 외 항목

### D-092 [COMPANY_STOCK_HEADER]
- 판정: MARK_MISSING (부분 대체: D-141)
- 원문 인용: D-092 "재고현황 시트는 지금처럼 '현재고' 칸만 쓰고" / D-141 "상품별 '상품명·현재고'(옛) · 팔래트/박스 줄 '제품명(판매처 제품명)·총입고수량'(새)"
- 코드 근거: src/company_stock.py:73 `"현재고" in c or "총입고수량" in c`. 핵심 동작(머리글 startswith·자동갱신)은 유지 :120,:208~210
- 제안: D-092 상태 줄에 `ACTIVE (부분 SUPERSEDED by D-141 — 재고현황 읽는 칸)` 표기. '셀독·당근·자사 칸 안 씀'이 새 양식에서도 그대로인지(새 양식에 그 칸이 없을 수 있음)는 확인 필요
- 확신도: 중간

### D-093 [PRUNE_STALE_ACCOUNT_ID]
- 판정: STATUS_MISSING
- 원문 인용: 668~672행에 '- 상태:' 줄 없음
- 코드 근거: src/workbook_lifecycle.py:134 `prune_account_ids`(남는 게 0이면 안 지움) · src/pipeline.py:316(`_sync_ledger_state` → `_reconcile_ledger_accounts`) · simulate_pipeline.py:860 시나리오 27. 코드 동작 유효
- 비고: D-134 뒤 PC 엑셀 입력이면 `_reconcile_ledger_accounts` 가 먼저 return 해서 이 정리도 건너뜀(src/pipeline.py from_file 분기). D-134 본문은 '계정 삭제·판매중지 표기'만 말함 — 의도 범위인지 확인 필요(결정 뒤집기 아님)
- 제안: `- 상태: ACTIVE` 추가
- 확신도: 높음

### D-094 [SALES_DASHBOARD]
- 판정: MARK_MISSING (여러 부분 대체: D-097, D-098, D-105, D-107, D-110)
- 원문 인용과 대체 범위:
  - "계정당 하루 최대 30일" ← D-097 "D-094 의 30일에서 상향"
  - "⑥상품 상위 20 × 8주 금액 열지도"·⑤ "8주 글자 미니 그래프"·"비중" ← D-098 "물리 삭제"
  - "②월별 막대(1월~이번 달" ← D-105 "4월부터(시작일 상수 하나)"
  - "③ 집계 기준 = 관리 상품(…VID…)" ← D-107 "블록 VID 와 상품명이 같은 다른 VID … 도 포함"
  - "⑤계정 순위(이번 달 누계 순" ← D-110 "최근 1개월(어제까지 30일) 누계 — 이번 달 누계 대신"
  - "숨긴 열 9칸"·"addChart 3개" ← D-098에서 ⑤ 막대 추가 후 현재 13칸·4개(대체 D번호가 숫자를 직접 적지는 않음)
- 코드 근거: src/sales_summary.py:18 · src/workbook_sales_dash.py:33 `DATA_WIDTH = 13`,:189~195,:241~249 · ProductHeat 검색 0건. 소급 규칙·④ 기간 값·첫 시트 순서는 유지(src/pipeline_sales.py:167, src/sales_dashboard.py:117, src/workbook_sales.py:230). 비고: src/workbook_sales.py:221 주석 '차트 3개'는 낡음
- 제안: D-094 상태 줄에 `ACTIVE (부분 SUPERSEDED by D-097 — 하루 상한 · D-098 — ⑤⑥ 구성 · D-105 — 월 시작 · D-107 — 관리 상품 범위 · D-110 — ⑤ 기간)` 표기
- 확신도: 높음

### D-095 [REGISTRY_SEPARATE_FILE]
- 판정: OWNER_POLICY
- 원문 인용: "코드로 '원장 링크 = 관리대장 주소' 거부(소유자 미결정 — STATE 제안)"
- 코드 근거: 이 PC config.json:4 `registry/url` 은 결정의 파일 ID 앞부분(1Fb_G1)과 같음. 운용 PC 설정은 여기서 확인 불가. 거부 코드 없음(검색어 `원장 링크.*관리대장`·`관리대장.*원장 링크`·`url ==`, 대상 registry*.py·ui/registry*.py·ui/app_qt.py — 안내 문구만 나옴). 현재 STATE.md(54줄)에는 이 제안이 없음(검색어 `원장`: 45행 한 건, 무관)
- 소유자에게 물을 것: ① 운용 PC 설정 탭 원장 링크가 지금도 별도 파일인지 ② 관리대장 주소를 넣으면 막는 가드를 만들지, 안 만들지
- 제안: 답을 받기 전 상태 변경 없음. 제안이 STATE에서 사라졌으므로 STATE 미해결에 다시 올림
- 확신도: 중간

### D-098 [SALES_DASHBOARD_V2]
- 판정: MARK_MISSING (부분 대체: D-101, D-110)
- 원문 인용: D-098 "이번 달 누계 **가로 막대 차트**(판매 있는 계정·1위 맨 위)" · "'판매 없음 N계정: …'" / D-101 "D-098 의 '판매 있는 계정만'을 이 부분만 바꿈"·"'판매 없음 N계정' 줄은 삭제" / D-110 "'이번 달 누계(1일~어제)'에서 **최근 1개월 = 어제 포함 30일**"
- 코드 근거: src/workbook_sales_dash.py:184~218. 나머지(2줄 상세·freeze A3·폭 W·값 축 0)는 유지 src/workbook_sales.py:133,185, src/workbook_sales_dash.py:283~293,318
- 제안: D-098 상태 줄에 `ACTIVE (부분 SUPERSEDED by D-101 — ⑤ 대상 계정·판매 없음 줄 · D-110 — ⑤ 기간)` 표기. 프로그램 후보 mentioned_by(D-101) 정탐
- 확신도: 높음

### D-102 [SALES_DETAIL_ACCOUNT_BLOCK]
- 판정: STATUS_MISSING
- 원문 인용: 730~734행에 '- 상태:' 줄 없음
- 코드 근거: src/workbook_sales.py:33~35 `_BLOCK_FILLS`(D9E2F3/EEF3FB·E2EFDA/F3F9EF)·`_EDGE`(medium·595959),:153,:163,:167 · src/gsheet_stats.py:27,75 SOLID_MEDIUM. 코드 동작 유효
- 제안: `- 상태: ACTIVE` 추가
- 확신도: 높음

### D-106 [INDEX_SHEET_LAYOUT_V2]
- 판정: MARK_MISSING (부분 대체: D-109)
- 원문 인용: D-106 "결과 구글시트 '계정목록' = 10열" · "I 체험단 종료일(직원 입력) · J 체험단효과" / D-109 "'체험단 종료일' 열 삭제 → 9열(직원 입력 열 없음)"
- 코드 근거: src/gsheet_index.py:33 `N_COLS = 9`,:323. 나머지(상태 E·2행 고정·그로스 2줄·폭 130~190)는 유지 :29,:277,:305,:334,:338~341
- 제안: D-106 상태 줄에 `ACTIVE (부분 SUPERSEDED by D-109 — 열 수·체험단 종료일 열)` 표기
- 확신도: 높음

### D-108 [PROMO_END_NO_CADENCE]
- 판정: MARK_MISSING (부분 대체: D-109, D-121)
- 원문 인용: D-108 "종료일은 그대로 저장돼 '체험단중/종료' 상태·기간 배경색에만 쓰인다" / D-109 "'체험단 종료일' 열 삭제" / D-121 "옛 '마케팅 기간(시작~종료) 연주황'·… 물리 삭제(`_mkt_cols`·`_promo_cols`·`_FILL_MKT`·`_StyleCtx.mkt_fill`)"
- 코드 근거: 핵심(게이팅 판정) 유지 src/workbook_meta.py:531~542 `(3, 5)`. 기간 배경은 src/workbook_render.py:411 `_promo_fills`(시작일 7일)로 바뀜, 상태 판정 `_mkt_status` 는 종료일을 계속 씀 src/workbook_meta.py:515
- 제안: D-108 상태 줄에 `ACTIVE (부분 SUPERSEDED by D-109 — 계정목록 입력 칸 · D-121 — 기간 배경색)` 표기. 프로그램 후보 mentioned_by(D-109) 정탐
- 확신도: 중간(D-109가 D-108을 직접 대체한다고 적지는 않음)

### D-111 [TRANSFER_LOGIN_CHECK]
- 판정: MARK_MISSING (부분 대체: D-112)
- 원문 인용: D-111 "17:40 이후 새 계정 안 함 … 차단 2연속 전체 중단" / D-112 "전체 중단 = 차단뿐 아니라 **차단·미완료·오류 2계정 연속**" · "멈춤 시각(기본 17:40) = 시작 뒤 처음 오는 그 시각"
- 코드 근거: src/transfer_login.py:30 `BLOCK_STOP`,:120,:208,:230(D-112 동작). 나머지(파일 읽기·탭·명령)는 유지 src/transfer_accounts.py:95,132 · ui/app_qt.py:236 · ui/transfer_panel_qt.py:20
- 비고: "2단계(정산 다운로드·자동 실행 빈도)는 미결정" — 뒤 D항목 없음, STATE.md에도 없음(검색어 `셀독전환`·`2단계`). 미결 유지 여부를 소유자에게 확인 필요
- 제안: D-111 상태 줄에 `ACTIVE (부분 SUPERSEDED by D-112 — ④ 중단 조건·멈춤 시각)` 표기
- 확신도: 중간

### D-116 [SETTLE_MANAGED_SCOPE]
- 판정: MARK_MISSING (부분 대체: D-119, D-124, D-140)
- 원문 인용과 대체 범위:
  - D-116 "**광고비 = … 옵션ID별 광고비(실값)**" ← D-119 "날짜×캠페인 청구가능액 × 그날 매출 성장 보고서 옵션 광고비 비율" · D-119 근거 "상품별 청구액은 어느 화면에도 없음"
  - D-116 "입금 완료/예정/보류 = 계정 실제 지급 비율" ← D-124 버린 대안 "계정 실제 입금 비율 한 번 배분" · D-124 ③ "**쿠팡 지급 줄마다** 나눠 더함"(D-126이 이 규칙 승계)
  - D-116 ② 항목 몫을 공제에 비율로 적용하는 부분 ← D-140 "비율 × 계정 전체 금지"
- 코드 근거: git밖/statement_managed.py:191 `status_split`,:377 `MA.scoped`,:394 `MA.ad_share` · git밖/managed_alloc.py:63,110. 정산전용상품 판정은 유지 statement_managed.py:75. 비고: statement_managed.py:10 머리 설명 '입금 완료/예정/보류 = 계정 실제 지급'은 낡음. 앱 쪽 ③ 수집 5종은 D-117로 구현됨. 후보 `_261026` 은 오탐(경로 일부)
- 제안: D-116 상태 줄에 `ACTIVE (부분 SUPERSEDED by D-119 — 광고비 몫 · D-124/D-126 — 입금 배분 · D-140 — 공제 비율 적용)` 표기
- 확신도: 높음

### D-117 [SETTLE_COLLECT_1WON]
- 판정: MARK_MISSING (부분 대체 가능성: D-126 — 기존 D-119 표기는 정상)
- 원문 인용: D-117 "(1) … 정산서(git 밖 `additional_pay.py`)에 금액 + '확인 필요(첫 실제 자료로 칸 확정)' / 없으면 '없음'" / D-126 "쿠팡 정산 밖 별도 입금(우대수수료 환급·추가지급 — **있을 때만**)"
- 코드 근거: git밖/statement_managed.py:690~696(있을 때만 1쪽 표시) · git밖/additional_pay.py:48 상태값 '없음'은 내부에 남음. 앱 수집은 전부 유효 src/settlement_verify_collect.py:44,55~58,82,89,144~147 · src/settlement_ads.py · tools/settlement_download.py:484~489. 후보 `additional_pay.py` 는 오탐(git 밖 실재)
- 제안: D-117 상태 줄의 기존 표기에 `· (1) 정산서 표시 방식은 D-126` 추가 검토. 표기 방식만의 차이라 소유자 판단으로 생략 가능
- 확신도: 낮음

### D-119 [AD_COST_DAY_CAMPAIGN]
- 판정: MARK_MISSING (부분 대체: D-140, 확장: D-137)
- 원문 인용: D-119 "계정 광고비 공제 × (관리 몫 / 청구가능 합)" · "보고서에 없는 날·캠페인 청구액은 메모(관리 몫 0)" / D-140 "D-124 ③·D-119·D-137 의 비율 적용 부분을 대체" · "광고비 = 청구가능 × 옵션 비율 + 부가세 10%, 쓴 달 다음 달 지급 줄부터" / D-137 "보고서 파일을 아직 못 받은 달의 청구는 관리 몫 0 으로 치지 않고 비율 계산에서 뺀다" · "D-119 를 넓힘"
- 코드 근거: 수집 부분 유효 src/settlement_ads.py `_DAILY`·collect, `CMG_EXCEL` 검색 0건. 공제 계산은 D-140 동작 git밖/statement_managed.py:377,394~395(`a_m * 1.1`) · git밖/managed_alloc.py:63,110. 후보 `managed_alloc.py` 등은 오탐(git 밖 실재)
- 제안: D-119 상태 줄에 `ACTIVE (부분 SUPERSEDED by D-140 — 계정 공제에 비율 적용 · D-137 — 못 받은 달·캠페인 없는 줄)` 표기. 같은 이유로 D-137 상태 줄도 D-140 표기 대상(이 구간 밖, 해당 구간 담당과 대조)
- 확신도: 높음
