커버리지: docs/DECISIONS.md 230~444행 전체 열람, 판정 블록 30개(D-031~D-060). 대조 기준 master(감사 중 162e378 → 69fba38 로 이동, 다른 세션 커밋). 뒤 항목은 D-064·074·075·076·081·084·089·090·091·093·094·097·103·106·115·124·125·126·134·135 를 읽음(일부 긴 줄은 앞 1,500자까지, D-064 (4)는 별도 확인). 테스트·앱은 실행하지 않았고 코드 대조만 했다. "동작 확인"은 정적 대조 결과다.

분류별 개수: OK 19 · STATUS_MISSING 0 · MARK_MISSING 8 · STALE 1 · MISMATCH 0 · OWNER_POLICY 2

## OK

| D번호 | 태그 | 근거 |
|---|---|---|
| D-031 | STATS_AS_IS_SETTLE_RETRY_PUBLIC_PROXY | pipeline_process.py:76-82(첫 VID 값·합산 없음) · settlement_watch.py:112-113(stopped→later) · tools/settlement_download.py:188-201(_profile_busy until) · proxy_pool.py:130-135 · 호출 pipeline.py:819, ui/app_qt.py:1415·1511. 비고: CLAUDE.md:27 낡은 문구는 D-034 항목 참고 |
| D-032 | RESUME_SAME_COLUMN_ONLY | pipeline.py:123-134(날짜 칸 다르면 이어받지 않음·carry). 비고: `_진행중.json` 오탐(실행 중 생기는 파일) |
| D-033 | KW_TAB_FIX | kw_metrics.py:33(검색어 전달) · manual_keywords.py:14·40(매칭고정으로 블록 찾기) · keyword_store.py 없음. 비고: `keyword_store.py`·`_매칭고정.json` 오탐(의도적 삭제·실행 중 파일). 검색어 `keyword_store` 는 manual_keywords.py:3 설명문에만 있음 |
| D-037 | HQ_ASSET_REMOVED | ui/ 에 app_integrated·theme_qt·panel_kit 없음 · tools/run_checks.py 에 verify_contract/worklog/cs/creditor 0건 · registry_lock·registry_model·apppaths 유지. 비고: 후보 14건 전부 오탐(의도적 삭제 또는 HQ 쪽 파일 shell.py·theme.py) |
| D-038 | CLEANUP_REUSABLE_PKG | reusable_coupang/ 없음 · src/ui/tools 검색 `reusable_coupang` 0건 · 로컬 domain/*·worktree-* 브랜치 0개 · master..origin/domain/h-ui = 0, ..d8-ledger = 0. 비고: `docs/COUPANG_ACCESS.md` 오탐(HQ 저장소에 있음). 원격 domain/h-ui·d8-ledger 는 남아 있으나 미병합 커밋 없음 |
| D-040 | VIDLESS_UNCOLLECTED | pipeline.py:339-340 · pipeline_process.py:370-393(메타 있음·VID 없음·대장에 없음·계정 스코핑) |
| D-041 | TWIN_VID_PURGE | pipeline_process.py:309-330·411 · pipeline_sales.py:402-403(live_all_vids 사전) |
| D-042 | LEDGER_LABEL_ONELINE | input_list.py:80-83(_one_line)·103-107(account_labels)·492-497 · company_stock.py:126-131. 비고: '남은 것'(유사도 탈락)은 D-047 이 해소(대체가 아니라 미결 해소라 표기 선택 사항) |
| D-044 | KW_BLANK_KEEP | ui/app_qt.py start_auto(1630~) 에 grow 전달 없음(grep 결과 grow 는 1580~1617·1752~1760 뿐) · pipeline_stages.py:42 grow 기본 False |
| D-045 | SHARED_EXPOSED_LABEL | pipeline_process.py:221·414 · product_naming.py:23-29·42 |
| D-046 | LEDGER_FULL_TEXT_MATCH | input_list.py:40·344·358 · product_match_ai.py:93-101(_full·_line_texts)·39-42(지시문)·137. 비고: D-079 헤더 변형은 확장이며 모순 없음 |
| D-048 | GROWTH_PER_OPTION | input_list.py:513-525(_inventory_text, 블록 1개=숫자·여러 개=옵션별 함께·없으면 '-') · workbook_meta.py:318-326(inventory_cell) |
| D-049 | REP_SWAP_MERGE_KW | pipeline_process.py:452-463 · workbook_lifecycle.py:298-322(합치기·빈 날짜 칸만·옛 칸 삭제). 비고: move_keywords 는 dst 에 키워드 칸이 없으면 무변경이나 pipeline_process.py:173 이 대표 블록 칸을 먼저 만들어 경로 유지 |
| D-051 | EXPOSED_NAME_WING_MODIFY | collector.py:574-590 · pipeline_sales.py:486-496·498-520(판매분석 → 30일 → 상품수정 화면 → ❌) |
| D-054 | SETTLE_VERIFY_RENAME | settlement_store.py:86-93·96-120(_keep_newer_verify·수집일 최근 것 하나) |
| D-055 | SETTLE_WITH_MANUAL_FULL_RUN | ui/app_qt.py:1601(since=누른 시각)·2067(무인 since 없음) · app_process.py:31-48 · tools/settlement_download.py:770-771. 비고: D-091 already_done 도 cycle_start(--since 반영) 기준이라 모순 없음(settlement_watch.py:71-80) |
| D-057 | RANK_PROFILE_PER_IP | pipeline_ranks.py:38·42-49(_rank_profile)·109~124(skip_pairs)·39·193-199(_next_round 5분 대기). 비고: '미확정'(쿠키 vs 지문) 판정 기록은 이번 범위에서 못 찾음 |
| D-058 | PROXY_IDENTITY_FOLLOWS_IP | pipeline_ranks.py:52·56-78·135 · CLAUDE.md:54. ② 자동완성·탭은 미적용(_identity_follows_ip 호출처 pipeline_ranks.py:135 뿐) = 결정문의 '별도 사이클'과 일치. 비고: `_rank_egress.txt` 오탐(런타임 파일) |
| D-060 | SETTLE_UNSETTLED_SOURCE | 상태 줄 표기 있음·D-081 원문과 일치("D-060 의 로켓그로스 부분 … 을 대체") · 윙 부분은 D-081 이 유지 · business_statements.py:247(_wing_unsettled)·349(_rg_unsettled) 존재. 비고: 후보 3건 오탐(git 밖 output\ 스크립트) |

## OK 외 항목

### D-034 [TEXT_TRUTH_F3467]
- 판정: STALE(코드 동작은 결정과 같고, 결정이 없앤 낡은 문구가 일부 남음. 대체 결정 없음, 의도적 변경 아님)
- 원문: "(F3) … 고정 문구 '7개' 폐지" · "(F4) 프록시 기본값 설명을 실제 … 에 맞춤" · 제목 "낡은 주석"
- 코드 근거:
  - 맞는 부분: ui/app_qt.py:861-865(config 값 표시) · config.py:313('설정 없음 → 기본 ON') · proxy_pool.py:126(_SKIP_MSG) · ui/app_qt.py:816·1780(③ 안내)
  - 남은 문구: config.py:82 "순위추적은 KW_MAX_TRACK(=7)개/상품 안쪽" (실제 config.py:125 = 10)
  - 남은 문구: CLAUDE.md:27 "노출순위 프록시(③순위 전용·기본 OFF)" (CLAUDE.md:50 은 "키 없으면 ON", D-031 은 ②·탭도 적용)
  - 남은 문구: config.py:49 "사람이 직접 검색한" (③은 앱이 자동 타이핑)
- 제안: 결정 표기 변경 없음. 위 3곳 문구 현행화를 별도 작업으로 등록.
- 확신도: 높음(문구 존재) · config.py:49 는 중간(반자동 스캔 설명으로 읽을 여지 있음)

### D-035 [R0_HQ_SPLIT]
- 판정: OWNER_POLICY
- 원문: "R0 는 그 형식을 바꿀 때 HQ 에 알리고 양쪽 DECISIONS 에 기록"
- 근거:
  - STATE.md:29 "HQ 알림: D-079~D-141" = 미처리 누적
  - D:\commerce-hq\docs\R0_DATA_CONTRACT.md 검색어 `통합판매현황`·`판매분석_일별`·`판매분석_기간`·`_매칭결과` 0건 (D-047·D-056·D-064 가 알림 필요로 적은 형식 변경이 계약 문서에 없음)
  - 공유 잠금: src/ui/tools 검색어 `coupang-shared` 0건. 다만 "HQ D0 요청 시" 조건부이고 HQ STATE.md:39 가 "미전달"이라 이 부분은 결정과 어긋나지 않음
- 소유자 질문: HQ 재설계 중에도 R0 형식 변경 알림 의무를 유지하나? 유지하면 누적분을 언제 전달하나?
- 제안: 소유자 답을 받기 전에는 표기 변경 없이 STATE 미해결 유지.
- 확신도: 중간

### D-036 [R0_TRANSITION_ROLE]
- 판정: OWNER_POLICY(코드로 판정 불가, 다만 기록과 실제 운영이 어긋남)
- 원문: "이관 기간 R0 는 매일 운영을 유지하고 치명 오류 수정만 한다(새 기능 추가 안 함 — 새 기능 요청은 HQ 로 안내)" · "R0 에서 고친 것은 R0 STATE.md '포팅 필요'에 남겨"
- 근거:
  - 이후 R0 에 새 기능이 계속 추가됨: D-064(통합판매현황)·D-094(대시보드)·D-111(전환자 로그인 확인)·D-117(1원 정산 수집) 등
  - D-064 (4) 원문 "진행 위치 = R0(… HQ 전환 전)" 은 그 건만의 예외이고 D-036 표기는 없음
  - CLAUDE.md:82 는 지금도 "치명 오류 수정만"이라고 적음
  - STATE.md 검색어 `포팅`·`은퇴` 0건(HQ 언급은 29행 '알림'뿐)
  - HQ STATE.md:34 재설계 진행 중, '"R0 시트 읽기 안 함(종료함)" 뜻(미확인)'
- 소유자 질문: ① R0 '치명 수정만·새 기능 금지'가 아직 유효한가? ② R0 은퇴 계획은 유지인가? ③ '포팅 필요' 기록을 계속 하나?
- 제안: 답에 따라 새 D항목 + D-036 상태 줄에 부분 SUPERSEDED 표기, CLAUDE.md:82 갱신. `_raw` 형식 유지 조항은 코드상 지켜짐(pipeline_sales.py:45-60).
- 확신도: 높음(어긋남 사실) · 처리 방향은 소유자 판단

### D-039 [SETTLE_DEDUP_ROWS]
- 판정: MARK_MISSING(부분)
- 원문 D-039: "기존 규칙(같은 이름 파일 1회·윙 최종액은 주정산 없는 주만)은 그대로."
- 원문 D-074: "윙 최종액 파일 줄을 빼는 조건을 '같은 정산예정일의 주정산 파일이 있음'에서 '같은 정산예정일 이고 구매확정일이 그 주정산 파일 기간 안'으로 좁힌다"
- 코드 근거: 핵심 결정(겹친 줄 1회·파일 안 반복 전부)은 settlement_stats.py:126-137 에 있음. 최종액 조건은 :123-125 _in_weekly(D-074). 같은 함수 docstring :118-119 는 옛 표현 유지.
- 제안: D-039 상태 줄에 "ACTIVE (윙 최종액 제외 조건 부분 SUPERSEDED by D-074)" 표기. 핵심은 유지. D-039 는 기존 규칙을 인용했을 뿐이라 표기 생략도 가능.
- 확신도: 중간

### D-043 [REP_SWAP_MOVE_KW]
- 판정: MARK_MISSING(부분)
- 원문 D-043: "대표(names[0])에 키워드가 없고 다른 옵션 블록에 있으면 … 새 대표로 옮기고"
- 원문 D-049: "D-043 을 일반 규칙으로 넓힌다 … 새 대표에 키워드가 있어도 move_keywords 로 합친다"
- 코드 근거: pipeline_process.py:456-460 은 대표 키워드 유무를 조건으로 보지 않음(has_keyword_section(old)만 확인).
- 제안: D-043 상태 줄에 "ACTIVE (적용 조건 '대표에 키워드 없음' 부분 SUPERSEDED by D-049 — 대표에 키워드가 있어도 합침)" 표기.
- 확신도: 높음

### D-047 [GROWTH_BY_AI_MATCH]
- 판정: MARK_MISSING(부분)
- 원문 D-047: "역기록(write_ledger_inventory)은 대장 줄 → 그 VID 의 첫 VID 블록 → 최신 숫자 재고" · "미결(소유자 확인 대기): 대장 한 줄이 옵션 여러 개를 가리키면 … 지금은 대표(첫) 옵션 재고 — 합계 여부."
- 원문 D-048: "D-047 미결의 답. … 옵션 블록 여러 개면 … '라벨 값 / 라벨 값' … 합산하지 않는다." · "D-047 의 '첫 VID 블록' 은 … 회귀였음 → 이 결정으로 해소"
- 코드 근거: input_list.py:518-525. 나머지 핵심은 유지(match_anchor.py:64-68, pipeline_sales.py:461-468). 검색어 `_best_inventory_match`·`_growth_idf` 0건 = 결정대로 물리 삭제.
- 제안: D-047 상태 줄에 "ACTIVE (옵션 여러 개 줄의 '첫 VID 블록' 부분 SUPERSEDED by D-048 — 옵션별 함께 표기)" 표기.
- 비고: `_growth_idf` 오탐(삭제가 결정 내용) · `output/_매칭결과.json` 오탐(실행 중 생기는 파일)
- 확신도: 높음

### D-050 [INDEX_TITLE_COUNT]
- 판정: MARK_MISSING(부분·경미) — 확인 필요
- 원문 D-050: "현재 수(판매중지 제외)로 쓴다"
- 원문 D-135: "계정목록 제목 '상품 N개' = 판매중지·상품 없는 계정 줄 제외."
- 코드 근거: gsheet_index.py:371-374(D-135 주석 포함)·875(증분마다 갱신 유지).
- 제안: 뒤집힘이 아니라 세어 넣는 범위가 좁아진 것이라 표기는 선택. 하면 "ACTIVE (제목 상품 수 범위 부분 SUPERSEDED by D-135 — 상품 없는 계정 줄도 제외)".
- 확신도: 낮음

### D-052 [SETTLE_MONTHLY_FAILED_COMMENT]
- 판정: MARK_MISSING(부분·경미) — 확인 필요
- 기존 표기(D-075 월정산 부분)는 정확함.
- 원문 D-052: "(3) 정산 계정 파일에서 # 으로 시작하는 줄은 주석(건너뜀)."
- 원문 D-103: "설정 settlement/account_source 기본 registry · file 이면 옛 파일."
- 코드 근거: settlement_accounts.py:38-39 는 유지. tools/settlement_download.py:92·133-136 에 따라 기본 경로에서는 계정 파일을 쓰지 않아 (3)은 file 모드에서만 작동. (2) 실패 표시는 유지(settlement_watch.py:121-130, ui/settlement_status_panel_qt.py:28).
- 제안: 상태 줄에 "(3)은 D-103 이후 account_source=file 일 때만 적용" 추가. 대체가 아니라 적용 범위 축소라 표기는 선택.
- 부수: settlement_wing_api.py:127 docstring "윙 'M'·로켓그로스 'MONTHLY'" 는 D-075 이후 낡음(실제 :39 = B, :41 = 빈 값).
- 비고: `_완료.json` 오탐(런타임 파일)
- 확신도: 낮음

### D-053 [RANK_PASSES_CONN_EVIDENCE]
- 판정: MARK_MISSING(부분·경미) — 확인 필요
- 원문 D-053: "한 바퀴가 끝나면 남은 빈 칸만 다시 도는 바퀴를 빈 칸 0 또는 중지 요청까지 반복" · "위험: 모든 IP 가 계속 막히면 ③이 끝나지 않음"
- 원문 D-090: "(3) 성공 없이 IP 불량이 15번 이어지면 쿠팡 화면 구조 변경·프록시 전체 불량 의심으로 ③ 마침" · "(2) … 측정 불가로 마침 규칙에 걸리지 않고"
- 코드 근거: D-053 본체는 있음(pipeline_ranks.py:204-216·318-334·575-607·628-643, ui/app_qt.py:1682·1888-1890). 추가된 종료 경로는 :791-806. 종료 조건에 D-090 이 더해졌으나 D-053 상태 줄에 표기 없음.
- 제안: 상태 줄에 "ACTIVE (종료 조건에 D-090 추가 — IP 불량 15연속이면 마침)" 표기. 표기는 선택.
- 부수: ui/app_qt.py start_auto docstring·주석의 "차단 시 쿨다운/자동재개"·"자체 서킷브레이커(쿨다운 MAX·연속차단)"는 D-030·D-053 과 다른 낡은 문구.
- 확신도: 낮음(표기 필요성) · 높음(문구가 낡았다는 사실)

### D-056 [SALES_GMV_DAILY]
- 판정: MARK_MISSING(부분)
- 원문 D-056: "운용 PC 재배포 후 첫 18:00 부터 쌓임(과거 날짜 소급 없음)."
- 원문 D-094: "output/판매분석_일별/{계정}.json 을 2026-04-01~어제까지 채운다 … 하루씩 … 최근 날짜부터 거꾸로" (상한은 D-097 로 60일)
- 코드 근거: pipeline_sales.py:116(_record_sales_backfill) · sales_summary.py:18(BACKFILL_PER_DAY = 60). 핵심 기록 규칙은 유지(sales_history.py:22-32, report.py:50-51, pipeline_sales.py:115·127-135).
- 제안: D-056 상태 줄에 "ACTIVE (‘과거 날짜 소급 없음’ 부분 SUPERSEDED by D-094 — 2026-04-01부터 소급)" 표기.
- 확신도: 중간(대상 문구가 결정 칸이 아니라 영향 범위 칸에 있음)

### D-059 [SETTLE_CONSIGNOR_STATEMENT]
- 판정: MARK_MISSING(부분) — 소유자 확인 포함
- 원문 D-059: "사업자별 정산서 = '위탁 판매 정산서' 1시트 … A 판매 내역 … B 차감 … C 순지급액 … D. 쿠팡 미정산 … E 지급 기록"
- 원문 D-126: "제목 = '{사업자} (대표 {대표자})님 쿠팡 판매 정산내역서' … 큰 숫자 = A 판매금액 · E 정산대상액 · F 쿠팡 공제 · G 최종 지급액"
- 근거(git 밖 스크립트, output\_분석_261013\정산스크립트\):
  - business_statements.py:500 "위탁 판매 정산서" 양식이 남아 있음
  - statement_managed.py:597 "쿠팡 판매 정산내역서" = 새 양식
  - D-059 상태 줄은 ACTIVE 뿐이고, 옛 양식과 새 양식의 적용 범위가 기록되지 않음
- 소유자 질문: 현행 정산서는 D-126 양식뿐인가, 전체 계정 정산 요약·전달 파일 구조는 D-059 그대로인가?
- 제안: 확인 후 D-059 상태 줄에 "ACTIVE (1쪽 머리·항목 구성 부분 SUPERSEDED by D-126 — 첫 시트 요약 등 나머지 범위는 확인 후 명시)" 표기.
- 비고: 후보 3건 오탐(git 밖 output\ 스크립트, 실제 파일 존재)
- 확신도: 중간

## 범위 밖 참고
- D-093 블록(668~673행 부근)은 상태 줄 없이 다음 항목으로 넘어가는 것으로 보임. 해당 구간 담당자 확인 대상.
