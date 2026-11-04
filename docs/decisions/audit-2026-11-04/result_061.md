커버리지: docs/DECISIONS.md 445~653행 전체 열람(209행), D-061~D-090 30블록 전부 판정. 뒤 항목 대조용으로 D-094·098·103·105·106·108·109·116·122·123·124·126·137 원문과 D-021 해당 구절 열람. 코드 대조 기준 = 커밋 162e378(R87) 작업 트리, 읽기만 함(프로그램·테스트 실행 안 함).

분류별 개수: OK 19 · STATUS_MISSING 1 · MARK_MISSING 7 · OWNER_POLICY 2 · 확인 필요 1 · STALE 0 · MISMATCH 0

## 1. OK 표

D-번호 | 태그 | 근거(파일:행 또는 식별자)
---|---|---
D-061 | SETTLE_EVIDENCE_ORIGINALS | 운영 원칙 기록. 구현은 D-062·D-067로 이어짐(settlement_evidence.py:1~21, designs/SETTLEMENT_MODULE.md §14 "가공 파일 금지·D-061"). 모순 없음. "전 계정 수집 미완"은 D-067로 해소
D-063 | SALES_EXCEL_MENU | collector.py:690~691 `menu="상품별 판매"`·:743 `get_by_text(menu)`, settlement_evidence_web.py:31 SALES_MENUS, tools/pin_login_ranks.py:774. 비고: designs/DESIGN.md:496 은 아직 옛 이름 '상품별 판매 리포트'(문서만 낡음, 정리 후보)
D-065 | SETTLE_VERIFY_RULES | 실측 규칙·소유자 결정 기록. SSOT = designs/SETTLEMENT_MODULE.md:230 §13, payout.py:104, docs/COUPANG_WING_HELP_KB.md:120 §1-13, 평문 = SETTLEMENT_MODULE §14 머리 "평문 보관(D-065)". 뒤 항목의 대체 없음
D-066 | SETTLE_PAYOUT_ROUNDING | payout.py:104~108 first_payout_70, settlement_stats.py:233 `_day_sums`·:249~252 30% 계산, designs/SETTLEMENT_MODULE.md:68
D-067 | SETTLE_EVIDENCE_ALL | settlement_evidence.py:21, settlement_evidence_web.py, tools/settlement_download.py:547 EVIDENCE_JOBS·:565 cmd_evidence 9단계·:831 --redo, deploy/정산증빙_전체받기.bat, build.bat:29. 비고: bat 안내문 "계정 파일 비밀번호 자동 입력, 2차인증은 사람"은 D-068·D-076·D-103과 다른 옛 문구(표시 문구만, 정리 후보). 저장 위치 문제는 아래 D-062 참조
D-068 | LOGIN_PW_REFUSED_SAME_DAY | login_today.py:24·:47(HMAC), browser.py:37·:469 2단계 otp, workbook_sales.py:156 `소계 — ⚠`, pipeline.py:664~666·:675. '그날' 부분 표기 있음(D-123), 코드도 fp_at 시각 기준(login_today.py:11). 비고: pipeline.py:691 로그 "오늘은 같은 값을 다시 넣지 않음"은 24시간과 어긋나는 문구(표시만)
D-069 | REGISTRY_CHECK_PENDING_RENAME | registry_gsheet.py:168 `_pending_renames`·:190 `_plan_checks`·:231, tools/verify_registry_offline.py:629. 비고: 결정문 "§6은 그대로"는 D-070 이전 시점 서술. 코드는 D-070 뒤에도 '모름·AI 장애'로 남은 확인필요에 대해 그대로 동작하므로 충돌 아님
D-071 | REGISTRY_AUTO_ACCOUNT_JUDGE | registry_judge.py:90 judge_account(절반 기준·0.75 일치), registry_rename.py:37 `_auto_resolve_pending`·:90 `_move_account`·:162 `_judge_account_pairs`, registry_gsheet.py:431 `_mark_auto_resolved`, tools/verify_registry_offline.py:284
D-072 | COMPANY_STOCK_MATCH | company_stock_match.py:1~14 4단계·:25 CACHE_FILE·:133 '없음'은 그날만·:136 ask_ai(후보 6개·장애 시 기존값 유지), company_stock.py:140·:162, tools/verify_registry_offline.py:922. 뒤 D-092·D-141은 머리글·재고 양식 건이라 매칭 규칙을 대체하지 않음
D-073 | SETTLE_WALLET_AUTO_WITHDRAWAL | settlement_verify.py:57 `_WITHDRAW`·:87·:315, tools/verify_settlement_runtime_offline.py:595~599
D-074 | SETTLE_WING_MONTH_BOUNDARY | settlement_stats.py:92 `_weekly_windows`·:102 `_in_weekly`(날짜 없는 줄 = 옛 규칙)·:123~125·:215·:248
D-075 | SETTLE_MONTHLY_CYCLE | settlement_wing_api.py:36·:40 `_WING_KIND`·`_RG_KIND`, settlement_stats.py:222·:226, payout.py:17·:20. 비고: D-021 본문이 "'M' 건너뜀 … D-010 의 처리 규칙은 그대로"라고 쓰는데 D-021 상태는 ACTIVE만 → 구간 밖 항목이라 해당 구간 판정에 넘김
D-079 | LEDGER_HEADER_VARIANTS | input_list.py:86 `_rep_name`·:97 `_header_name`·:114 `_find_header_row`, registry_model.py:17·:308, tools/verify_offline.py:1942
D-080 | ACCOUNT_RENAME_KEEPS_HISTORY | pipeline.py:743 early_renamed·:792, workbook_lifecycle.py:209 merge_history_from·:175·:202, gsheet_index.py:768 find_renamed_orphans, pipeline_gsheet.py:338, gsheet_stats.py:182 `max(maxr, fr + 1)`, tools/restore_renamed_history.py
D-084 | RANK_UNCOLLECTED_AND_OPTION | pipeline.py:280 `_ensure_today_columns`·:786, workbook_meta.py:265~ rank_suppressed. D-089는 보완(대체 아님), D-114는 "무관 — 그대로"라고 명시
D-085 | SETTLE_AMOUNTS_BY_PAYDATE | settlement_store.py:30 `_by_paydate`·:46·:51·:62, settlement_forecast.py record(묶음)·load, verify_settlement_runtime_offline.py:691. D-116·D-118 언급은 대체가 아니라 전제 인용
D-086 | PROMO_START_FROM_LEDGER | promo_sheet.py:84·:102, workbook_meta.py:450·:456 '체험단 시작(자동)'·:467·:476, pipeline.py:788, ui/app_qt.py:1211. 부분 대체 표기 있음(D-087·D-122). 비고: promo_sheet.py:7 "직원이 계정목록에 시작일을 넣으면 그 값이 우선"은 D-087 뒤 낡은 설명(실제 우선값 = 관리대장 마케팅 시작일, workbook_index.py:58)
D-089 | RANK_PWFAIL_TODAY_COL | pipeline.py:670 `_pw_failed`·:785~786, tools/simulate_pipeline.py:839
D-090 | RANK_DEAD_IP | pipeline_ranks.py:343·:346 `_DEAD_STREAK_STOP = 15`·:349·:590·:758·:776·:791 `_semi_on_dead`·:800 '검색창 없음'·:680 요약 'IP 불량(화면 안 열림)', tools/test_proxy_patch.py:384

## 2. OK 외 항목

### D-062 [SETTLE_KEEP_ORIGINALS] — OWNER_POLICY
- 판정: 핵심 기능 `--originals`는 코드에 있음. 다만 '구매자명 원본의 보관 장소' 제한이 D-067 이후 실제 운용과 어긋나 소유자 확인 필요.
- 원문: D-062(457행) "원본 폴더에는 구매자명이 있음 — 소유자 로컬 증빙 폴더에만 지정" · (456행 버린 대안) "원본 기본 보관(운용 PC 에 구매자명 파일 상시 누적 — 개인정보 최소화 위반)". D-067(489행) "운용 PC 실행 파일 `정산증빙_전체받기.bat`". D-068(498행) "output 폴더가 분석용으로 밖에 보내짐".
- 코드 근거: tools/settlement_download.py:60·:406~408·:828(옵션 동작 일치) · :566~571 cmd_evidence 가 ORIGINALS 를 증빙 폴더로 지정 · deploy/정산증빙_전체받기.bat `evidence --out "%~dp0output\정산\증빙"` · designs/SETTLEMENT_MODULE.md §14 "운용 PC … 저장 = output\정산\증빙\증빙_{사업자}_쿠팡원본\". 전달 압축에서 증빙 폴더를 빼는 코드 없음(검색: `make_archive|zipfile|ZipFile`을 tools·deploy·src·ui 에서 검색, 해당 없음. 전달은 코드 밖 수동 절차로 추정).
- 소유자에게 물을 것: (1) 운용 PC output 아래 구매자명 원본 보관을 허용하는가. (2) output 을 분석용으로 보낼 때 `정산\증빙`을 빼는가.
- 제안: 허용이면 D-062 상태 줄에 부분 SUPERSEDED by D-067('소유자 로컬 증빙 폴더에만' 부분) 표기. 불허면 저장 위치 변경을 새 D항목으로.
- 확신도: 중간(문구 충돌은 확실, 소유자 D-067 근거 "운용PC에서 동일 자료를 계정별로"가 묵시 승인인지는 미확인)

### D-064 [SALES_SUMMARY_FIRST_SHEET] — MARK_MISSING
- 판정: 뒤 항목이 시트 구성·기간 범위를 대체했는데 표기 없음(상태 줄 ACTIVE만, 프로그램 후보의 mentioned_by 에도 잡히지 않음. D-094 본문이 D-064를 번호로 부르지 않기 때문).
- 원문: D-064 "세로 3구역 [1. 전일] → [2. 주간(월~일) 최근 8주·이번 주 누계] → [3. 월별 2026-01~이번 달 누계]" · "처음엔 1월~이번 달·최근 8주 소급". D-094 "아래 = 상세표(일별 건수·금액·최근 31일 …) — 옛 주간·월별 구역 삭제" · "집계 기준 = 관리 상품". D-105 "`sales_summary.FIRST_DAY` = 2026-04-01 하나로 월별 기간 조회·대시보드 월 … 통일".
- 코드 근거: sales_summary.py:3 "주간·월별 구역은 상단 대시보드 차트가 대신"·:15 FIRST_DAY·:17 DETAIL_DAYS, workbook_sales.py:4~5. 유지되는 부분: 첫 시트·특수 시트(workbook_common.py:123~124), 기간 저장(sales_history.py:37·:40), ① 끝·③ 시작 갱신(pipeline.py:649, pipeline_ranks.py:274), '미수집' 구분.
- 추가 사실: (a) pipeline_sales.py:142 설명문 "처음엔 1월~이번 달"은 D-105 뒤 낡음(실제는 sales_summary.py:71·:87 first=FIRST_DAY). (b) D-064 '남은 단계' 3)비대장 계정 조회·4)앱 '판매 현황' 탭은 코드에 없음(검색: `_record_sales_periods` 호출처 pipeline_sales.py:113 뿐·settlement_download.py 없음 / ui/*.py 에서 "판매 현황" 0건 / designs/SALES_SUMMARY.md:84~85 표에만 남음). 폐기인지 보류인지 어느 항목에도 없음 → 소유자 확인 대상.
- 제안: D-064 상태 줄에 부분 SUPERSEDED by D-094(세로 3구역·집계 범위)·D-105(시작 달 1월→4월) 표기. 남은 단계 3·4는 STATE 미해결로 올려 소유자 확인.
- 확신도: 높음(대체), 남은 단계 처리는 소유자 판단

### D-070 [REGISTRY_AUTO_RENAME_JUDGE] — MARK_MISSING (지정 후보)
- 판정: D-071이 일부 대체를 본문에 적었으나 D-070 상태 줄은 ACTIVE만.
- 원문: D-070(510행) "계정아이디 변경 의심은 사람 승인 유지." D-071(517행) "D-070 의 '계정아이디는 사람 승인 유지'를 대체."
- 코드 근거: registry_rename.py:157 `if ctx.judge: pairs = _judge_account_pairs(...)`·:162, :37~ `_auto_resolve_pending` 계정 분기. 나머지 상품명 자동 판단은 현행(registry_judge.py:51, registry_apply.py:116, ui/registry_ui.py:63).
- 제안: D-070 상태 줄에 "ACTIVE (부분 SUPERSEDED by D-071 — 계정아이디 사람 승인 유지 부분)" 표기.
- 확신도: 높음

### D-076 [SETTLE_LOGIN_LEDGER_PW] — MARK_MISSING
- 판정: D-103이 '정산 계정 파일' 부분을 대체했는데 표기 없음(후보에 없던 신규 발견. D-103이 D-076을 번호로 부르지 않음).
- 원문: D-076(552행) "②정산 계정 파일 값" · "정산 대상 계정 목록은 그대로 정산 계정 파일." D-103(737행) "정산 계정 = 셀독원장의 최근 90일 관리 계정 … + '정산전용계정' 시트 … 비밀번호 = 원장 값" · "설정 `settlement/account_source` 기본 registry · file 이면 옛 파일."
- 코드 근거: settlement_accounts.py:68~86 설명문 "관리대장에 없는 계정 … 원장 값(D-103 — 옛 정산 계정 파일 대신)", tools/settlement_download.py:133~138 기본 registry·:233. '관리대장 값 먼저' 순서는 유지. 비고: settlement_download.py:235 메시지 "비밀번호 없음(관리대장·정산 계정 파일 모두)"는 옛 문구.
- 제안: D-076 상태 줄에 부분 SUPERSEDED by D-103(②정산 계정 파일 값·계정 목록 출처 → 원장, `account_source=file` 일 때만 옛 파일) 표기.
- 확신도: 높음

### D-077 [STATEMENT_FAST_SETTLEMENT] — MARK_MISSING
- 판정: 빠른정산 표시 위치·처리가 D-126으로 바뀌었고 범위도 D-116으로 바뀌었는데 표기 없음.
- 원문: D-077(559행) "②E '[참고] 빠른정산 상환 차감' … ③'F. 빠른정산(셀러월렛) 내역'" · "실제 받은 돈(E 쿠팡 지급 계 + F 원금, 수수료 전)". D-126 "④ **빠른정산(셀러월렛) 상환은 공제가 아니라 이미 받은 돈** = G 표에 '빠른정산 상환 −Z' … + '빠른정산으로 먼저 받은 돈 +Z'". D-116 "위탁정산서는 **관리 상품만**".
- 코드 근거(git 밖, output\_분석_261013\정산스크립트): statement_managed.py:525·:675~677(G 표 두 줄)·:623(비고). 옛 양식 코드는 business_statements.py:15·:90·:506 에 남아 있음(statement_managed 가 라이브러리로 import, :34). 앱 코드 src/ 대상 아님.
- 제안: D-077 상태 줄에 부분 SUPERSEDED by D-126(정산서 표시 구조 — 머리·E·F 섹션) 표기. 유지 부분: 빠른정산 금액 원천·확정 정산금액 불변.
- 확신도: 중간(소유자 2026-10-16 요구 '표기' 자체는 유지되고 양식만 바뀜)

### D-078 [SETTLE_FORECAST_RECORD] — MARK_MISSING
- 판정: 수집·정확도 시트는 현행. "정산서 예정액 변경 보류" 조항을 D-081이 풀었는데 표기 없음(후보에 없던 신규 발견).
- 원문: D-078(566행) "**정산서 '정산 예정액'은 정확도가 확인될 때까지 바꾸지 않는다**" · (569행) "다음 단계 = … 공제 반영 규칙 확정 → 정산서 적용(D-번호 새로)". D-081(587행) "로켓그로스 = 쿠팡 정산현황 **예정 줄**(D-078 `정산예정기록.jsonl`, 계정별 마지막 수집일)에서 …".
- 코드 근거: 현행 = settlement_forecast.py:16~17(AHEAD_DAYS 70)·:18·:27, settlement_store.py:22, tools/settlement_download.py:306·:324·:644, settlement_stats.py:316~318. 정산서 사용 = business_statements.py:39 `settlement_forecast as FC`. 낡은 설명 = settlement_forecast.py:7 "정산서 '정산 예정액'에 쓰는 것은 정확도가 확인된 뒤(분석 후 적용)".
- 제안: D-078 상태 줄에 부분 SUPERSEDED by D-081('정산서 예정액 변경 보류' 부분 — 로켓그로스 ④는 예정 줄 사용) 표기.
- 확신도: 중간~높음(D-081 근거 ①~③이 D-078의 '정확도 확인'에 해당하는지는 해석이지만, 정산서 적용 사실은 확실)

### D-081 [SETTLE_UNSETTLED_COUPANG_ONLY] — OWNER_POLICY
- 판정: 앱 코드 부분은 현행. '추정 금지'가 뒤 항목들의 '추정' 표기와 어디까지 공존하는지는 사업 정책이라 코드로 판정 불가.
- 원문: D-081(587행 제목) "쿠팡이 계산한 숫자만(추정 금지)", 근거 "소유자 … 정산이 100% 일치되도록·추정은 안됨". D-116 "정산 중 판매 = 확정되면 쿠팡 상품별 값, 그 전엔 같은 달 관리 판매 비율 '추정' 표시". D-126 "남은 사실: 광고비·밀크런 일부 '(추정)' … '(추정)' 표기 대안(정산 확정분만 넣기 권장)은 소유자 답 대기."
- 코드 근거: 앱 = settlement_forecast.py:18·:27~28 `_RG_TARGET`·:37 rg_target·:46 rg_sales(값 추가·계산 일치). 정산서(git 밖) = statement_managed.py:10·:383·:756 '추정' 라벨 존재.
- 소유자에게 물을 것: D-081의 '추정 금지'는 계정 전체 ④에만 적용이고 관리 상품 배분(D-116)의 '추정' 표시는 별도 허용인가. D-126이 남긴 '(추정)' 대안 답변도 함께.
- 제안: 답을 받기 전 표기 변경 없음. 범위 한정이면 새 D항목으로 관계 명시.
- 확신도: 중간. D-060 쪽 대체 표기는 있음(443행, 프로그램 후보 정상).

### D-082 [LEDGER_HIDDEN_ROWS] — STATUS_MISSING (지정 후보)
- 판정: 상태 줄 없음. 597행 영향 범위 다음 줄이 바로 598행 `### D-083`(빈 줄도 없음). docs/DECISIONS_INDEX.md:87 도 '?' 로 표시.
- 코드 근거(결정 내용은 모두 현행): gsheet_api.py:105~110 hiddenByUser만·:348, input_list.py:606 apply_hidden_rows·:657, workbook_lifecycle.py:12·:57 vids_of, pipeline.py:292 `_match_results`·:301·:320·:791, 시험 tools/verify_gsheet_offline.py:105~131·tools/verify_offline.py:1198. 대체하는 뒤 항목 없음(검색: `D-082`·`LEDGER_HIDDEN` → 597행 밖 DECISIONS.md 0건).
- 비고: git 밖 business_statements.py:18 이 D-083 내용을 "D-082"로 잘못 인용.
- 제안: D-082 끝에 "- 상태: ACTIVE" 추가 후 색인 재생성(소유자 승인 후, 다른 세션 커밋과 겹치지 않게).
- 확신도: 높음

### D-083 [SETTLE_LEDGER_100] — 확인 필요 (MARK_MISSING 후보)
- 판정: 수집·판정은 현행. 정산서 안 'G. 쿠팡 정산 장부' 섹션이 새 양식에 살아 있는지가 불명확.
- 원문: D-083(599행) "정산서(D-059)에 'G. 쿠팡 정산 장부(조회 시점)'·'쿠팡 정산 장부' 시트·전체 요약 '정산 100% 일치' 칸". D-126 "G = E − F" · "⑥ 삭제: 서명란·용어 풀이·쿠팡 자료와 대조·…".
- 코드 근거: 앱 = settlement_verify_collect.py:49·:139·:163, tools/settlement_download.py:57·:280·:352, verify_settlement_runtime_offline.py:1209. 정산서(git 밖) = statement_managed.py:64 `B.Ledger`·:777·:809~815 '정산 100% 일치' 유지. 다만 statement_managed.py 에서 `쿠팡 정산 장부`·`쿠팡 자료와 대조` 검색 0건 → 'G' 글자는 최종 지급액으로 재사용, 장부 섹션은 옛 business_statements.py:92 쪽에만 남음. '쿠팡 자료와 대조'가 곧 G 섹션인지는 미확인.
- 제안: 정산 세션에서 사실 확인 후, 맞으면 D-083 상태 줄에 부분 SUPERSEDED by D-126(정산서 안 G 섹션 부분 — 판정·전체 요약은 유지) 표기.
- 확신도: 낮음

### D-087 [PROMO_START_INDEX_COL] — MARK_MISSING
- 판정: 시작일 자동 칸·되읽기 금지는 현행. 제목에 있는 '종료일·모니터링 종료일 직원 입력 유지'가 D-106·D-109로 대체됐고 열 위치도 바뀌었는데 표기 없음.
- 원문: D-087(627행) "구글 G열" · "체험단 종료일·모니터링 종료일(H·I)은 지금처럼 직원 입력·앱 미접촉." D-106 "H 체험단 시작일(자동 D-087) · I 체험단 종료일(직원 입력) · J 체험단효과. '모니터링 종료일' 열 삭제". D-109 "H 체험단 시작일(자동) · I 체험단효과. '체험단 종료일' 열 삭제."
- 코드 근거: gsheet_index.py:31 COL_MKT_START = 7(H)·:32 COL_PROMO = 8·:179·:433 read_marketing(시작일 안 읽음 유지), workbook_index.py:114 회수·:233 표시. 로컬 '계정 목록'은 7~9열 유지(workbook_index.py:190·:233, D-106 "마스터 xlsx … `계정 목록`은 그대로"). 비고: gsheet_index.py:61~75 IndexRow 주석의 열 글자(J·K·E·F·G)는 D-106 전 위치라 낡음.
- 제안: D-087 상태 줄에 부분 SUPERSEDED by D-106(구글 열 위치·모니터링 종료일)·D-109(체험단 종료일) 표기.
- 확신도: 높음

### D-088 [STATEMENT_NOTIFY_RULES] — MARK_MISSING
- 판정: 규칙 다수는 살아 있으나 범위(D-116)와 표 구조(D-126)가 바뀌었는데 표기 없음. 앱 코드 아님(본문 "앱 코드 아님").
- 원문: D-088(634행) "**총 정산금액 ⑤ = 확정(70%·30% 지급분) + 쿠팡 정산 예정 전부**" · "'H. 체험단 비용' 섹션" · "C 섹션에 줄마다 + '정산·보상 합계(⑤+⑥)'" · "요약 ② 칸·B 섹션 '기타 조정' → **'쿠팡 지원 할인(가산)'**". D-116 "위탁정산서는 **관리 상품만**". D-126 "큰 숫자 = **A 판매금액 · E 정산대상액 · F 쿠팡 공제 · G 최종 지급액**" · "'A − B 판매자 할인쿠폰 − C 판매수수료 + D 쿠팡 지원 할인 = E − F = G'" · "참고 묶음 … 체험단 …".
- 코드 근거(git 밖): 유지 = statement_managed.py:795·:810 우리 사업자 제외, :703 "참고. 체험단 비용 (위 금액에서 빼지 않음)", :714 쿠팡 별도 보상, :656 'D 쿠팡 지원 할인'. 옛 ⑤·⑥·H 번호 = business_statements.py:88 등 옛 양식에만. 자료 파일 존재 확인: D:\토탈셀러\쿠팡 정산 자료\체험단_보충.json·쿠팡_별도보상.json.
- 제안: D-088 상태 줄에 부분 SUPERSEDED by D-116(계정 전체 → 관리 상품 범위)·D-126(⑤⑥·H·요약 칸 표 구조) 표기. 유지 부분: 체험단 표시만·우리 사업자 제외·별도 보상 정산 외·대응표 우선.
- 확신도: 중간(어디까지 대체인지는 정산 세션 확인 권장)

## 3. 프로그램 후보 비고(FALSE_POSITIVE)

- D-061·D-065 xlsx 파일명, `_20261013`·`_261015`·`_vs_`: 소유자 로컬 결과물 파일명·폴더명 조각(D:\토탈셀러 아래). 저장소 파일 아님.
- D-067 `deploy/정산증빙_전체받기.bat`: 실제 있음(deploy 폴더 목록, build.bat:29). 나머지 `_수집결과.json`·`_수집완료.json`·`_요청기록.json`은 실행 중 생성(settlement_evidence.py:21, settlement_store.py:18).
- D-068 `output/_로그인실패.json`: 실행 중 생성(login_today.py:24).
- D-072 `output/_회사재고매칭.json`: 실행 중 생성(company_stock_match.py:25).
- D-078·D-081 `정산예정기록.json`: 후보 추출이 잘린 것. 실제 `.jsonl`(settlement_forecast.py:16, settlement_store.py:22).
- D-082 `_매칭결과.json`: 실행 중 생성(match_anchor.py, pipeline.py:295).
- D-077·D-081·D-083·D-088 `business_statements`·`settlement_ledger`·`experience.py`·`_rg_*` 등: git 밖 output\_분석_261013\정산스크립트 아래(business_statements.py·settlement_ledger.py·experience.py 존재 확인). D-081이 삭제했다는 `_rg_last_month`·`_vat_months`는 후보 그대로 '없음'이 맞는 동작.
- D-088 `체험단_보충.json`·`쿠팡_별도보상.json`: D:\토탈셀러\쿠팡 정산 자료\ 에 존재.
- D-068·D-086·D-075·D-060의 대체 언급: 표기가 이미 있어 후보 정상, 추가 조치 없음.

## 4. 구간 밖·참고

- 문구만 낡은 곳(동작 영향 없음, 정리 사이클 후보): designs/DESIGN.md:496, deploy/정산증빙_전체받기.bat 안내문, pipeline.py:691, pipeline_sales.py:142, promo_sheet.py:7, settlement_forecast.py:7, settlement_download.py:235, gsheet_index.py:61~75 주석.
- D-021: 본문에 'M' 건너뜀 규칙 유지 구절이 있고 상태 줄은 ACTIVE만. D-075가 대체했을 가능성 → D-001~D-030 구간 판정과 대조 필요.
- D-071·D-072의 규칙 단계 자동 확정은 전역 규칙 '매칭 기본 = AI 매칭(소유자 2026-10-27)'보다 앞선 앱 설계. 그 전역 규칙이 앱 런타임까지 적용되는지는 이 감사에서 판정하지 않음(소유자 판단 사항으로만 기록).
- 폐기·변경 확정 없음. 위 제안은 모두 소유자 승인 전 제안.
