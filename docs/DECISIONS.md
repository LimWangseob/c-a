# DECISIONS — 확정된 정책·설계·구조 결정 (SSOT)

## 형식 (2026-10-08 session-kit 전환 — D-번호 블록)
```
### D-xxx [POLICY_TAG] 제목 (YYYY-MM-DD, R{n})
- 결정 / 근거(실측·로그·코드) / 버린 대안 / 영향 범위 / 상태: ACTIVE | SUPERSEDED by D-xxx
```
추가 전용·번호 연속. 기존 항목 수정·삭제 금지(뒤집으면 새 항목 + 기존에 `SUPERSEDED by D-xxx`).

## 항목 (신규·D-번호)

### D-001 [SESSION_KIT] 세션 관리 전역 일원화 (2026-10-08, R1)
- 결정: 핸드오프=STATE.md 한 곳 · DECISIONS=D-번호 블록 · 커밋=`[R{n}]` · 세션 종료=`/session-close`(전역 스킬) · 메모리 30~50줄·CLAUDE.md<200줄 상한.
- 근거: 소유자 업로드 session-kit + "전환하여 일원화(병행 금지)" 지시. handoff 메모리 난립·형식 혼재 방지.
- 버린 대안: (a)개념만 흡수=자동 강제 없음 (b)병행 설치=STATE+handoff 이원화 — 소유자 일원화 선택. kit verify(ruff/mypy --strict/cycle_audit)는 프로젝트 게이트와 불일치해 `run_checks`로 일반화.
- 영향 범위: ~/.claude/CLAUDE.md · ~/.claude/skills/session-close · STATE.md · docs/DECISIONS.md · 프로젝트 CLAUDE.md
- 상태: ACTIVE (옛 루트 HANDOFF.md 삭제 — 핸드오프 = STATE.md 한 곳 마무리·소유자 D-179)

### D-002 [SETTLE_ERRORS] 쿠팡 서버 일시 오류(5xx)는 차단이 아님 (2026-10-08, R3)
- 결정: 쿠팡 502·503·504 = 일시 오류(api 15초×2 재시도 → 받기 파일/계정 단위 '대기'·연속 실패에 안 셈). 차단은 403·429·차단 화면만.
- 근거: 2026-10-08 매출내역 504 HTML 응답이 ApiBlocked 로 오분류된 실측(통제 `_is_browser_closed`·`_run_accounts` 구조 위 except 한 줄).
- 버린 대안: 모든 비정상 응답=차단(일시 5xx까지 연속실패로 세어 전체 중단 유발).
- 영향 범위: tools/settlement_download.py(api 재시도·받기/계정 '대기')
- 상태: ACTIVE

### D-003 [SETTLE_VERIFY] 정산 검증 기준 (2026-10-08, R3)
- 결정: 로켓그로스 최종지급액 = H−I−J+K+매출조정(J='이번 정산 비용'=기납부·미납 물류비 반영) · 지급일별 최종−재고손실보상 = 월렛 입금.
- 근거: nicoable 실데이터 629/629·19/19 원 단위 + 소유자 화면 3건 확인.
- 버린 대안: 기납부 별도 차감식(238줄 불일치 원인).
- 영향 범위: settlement_verify·settlement_verify_collect
- 상태: ACTIVE

### D-004 [SETTLE_RG_PAYDATE] 로켓그로스 지급일 규칙 (2026-10-08, R3)
- 결정: RG 지급일 = 70%·100% 주마감+20영업일 / 30% 월걸침 주 +25영업일 / 30% 일반 익익월 첫 영업일. 영업일 공휴일 집합은 쿠팡 기준(실측: 2026-05-01 근로자의날·07-17 제헌절도 비영업일).
- 근거: 쿠팡 도움말 1.1 + 운용 PC 629/629 실측(옛 일률식은 월걸침 30% 2/88).
- 버린 대안: 30% 일률 익익월 첫 영업일(월걸침 86줄 불일치).
- 영향 범위: payout.rg_payout_date·검증시트 RG 지급일 대조·holiday_kr(공휴일 주입)
- 상태: ACTIVE (보강 — D-179: 쿠팡 비영업일 05-01·07-17 을 공휴일 집합에 해마다 늘 더함 `holiday_kr.COUPANG_OFF_DAYS`)

### D-005 [SETTLE_COMPENSATION] 재고 손실 보상 지급 경로 (2026-10-08, R3)
- 결정: 재고 손실 보상 = 대표 정산 계좌로 정산일 별도 입금 · 월렛 미포함. 정산현황 최종지급액엔 포함되나 월렛 입금엔 미포함.
- 근거: 쿠팡 판매자 도움말 7.4·2.1(helpseller 15892170571289) + 월렛 대조 19/19 · nicoable 3건 225,982.
- 버린 대안: 지급 경로 미확인 '확인 필요' 표시(도움말 확인으로 '확인됨' 전환).
- 영향 범위: settlement_verify 보상 처리·계좌 입금 시트
- 상태: ACTIVE

### D-006 [SETTLE_INFLOW] 계약자 '사업자 계좌 입금' 근거 (2026-10-08, R3)
- 결정: 계약자 정산의 '사업자 계좌 입금' = 계좌 입금 시트(윙 지급 + 월렛 인출 + 보상 + 물류비 환급[익월 21일]) · 월렛 잔액은 미인출(입금 아님).
- 근거: nicoable 검산 — 쿠팡 지급 합계 22,579,136 = 윙 최종 + RG 최종, 대표계좌와의 차이 = 월렛 잔액 1,546,312.
- 버린 대안: 월렛 잔액까지 입금으로 집계(미인출이라 실입금 아님).
- 영향 범위: settlement_stats 계좌 입금 시트·계약 정산(②층·소유자 결정 대기)
- 상태: ACTIVE

### D-007 [SETTLE_CALENDAR] 윙 지급일 정본 = 쿠팡 정산캘린더 (2026-10-08, R3)
- 결정: 윙 지급일 정본 = 쿠팡 정산캘린더(POST /tenants/msf/wing/api/payout-date-calendar/payout-dates) 원본 조회 — 규칙 계산 대신. 30% 포함·공휴일 집합 불필요.
- 근거: 소유자 지시('정산캘린더 활용') + nicoable 18/18 + 9월 최종 2026-11-02(11/1 일→다음영업일)·6월 최종 08-03(8/1 토) 캘린더 일치(소유자 캡처와 동일). STATE 미해결 '9월 최종 11/2 불일치' 해소.
- 버린 대안: 규칙 계산(골든 PAYOUT_MP_WEEKLY_FINAL '보정 없음'이 2026 실측 29줄 불일치 — 골든 수정은 통제 판단·검증이 캘린더를 써서 비급).
- 영향 범위: settlement_verify 윙 지급일 대조(30% 포함)·검증자료 수집 캘린더 1회 조회 추가(계정당). ⚠연관: designs/coupang_golden_cases.json PAYOUT_MP_WEEKLY_FINAL 기준 미수정(통제 판단 대기)
- 상태: ACTIVE (영향 범위의 골든 미결은 D-147 에서 해소 — 윙 최종액 지급일 규칙·골든 삭제)

### D-008 [NO_VIDLESS_BLOCK] VID 없는 블록 = 오류 — 미매칭 상품은 블록 미생성·잔재 정리 (2026-10-08, R3)
- 결정: 쿠팡에 등록된 상품이면 VID 는 반드시 있으므로 **VID 없는 블록은 만들지 않는다**. ① 괄호 포함일치는 본문 핵심어도 그 제목에 있어야 매칭(`product_match._paren_agrees`). ② 미매칭(VID 없음) 대장 상품은 블록 미생성·로그 경고(`pipeline_process._skip_unmatched`, 같은 이름의 VID 블록은 보존). ③ 이번 실행에 기록 안 됐고 VID 도 없는 잔재 블록은 삭제(`_purge_vidless_blocks`, 상품조회 실패 시·다른 계정ID 소속은 미접촉).
- 근거: 소유자 지시("VID가 없는 상품은 존재하지 않음, 오류임" 2026-10-08). 결과시트 실측 VID 없는 블록 7개 원인 확정 — 봄날 '크리스마스트리 R060 (골드)'가 색상 괄호로 풍선세트(96127398979)를 가져가 진짜 풍선세트 줄 미매칭(앱 매칭 함수로 재현) · 웨이브텍 'm10 (대체요망)' 9/28 미매칭→9/29 M10(95306328866) 매칭 후 옛 블록 잔존(로그) · 케이씨 정리함 JK0026 쿠팡 상품조회에 없음(전 계정 원문) · 하성진 로그인 실패로 원문 없음. 잔재는 판매자배송·0·'50위밖' 기본값을 실제 값처럼 보였다. 수정 후 과거 원문 24계정 80줄 재매칭: 봄날 2줄만 변경(풍선세트 정매칭)·나머지 불변. 게이트 16종·복잡도 경고 0·verify_offline[35].
- 버린 대안: (a) 미매칭도 대장명 블록 유지 + '미매칭' 표기(소유자: VID 없는 블록 자체가 오류) (b) VID 없는 블록 무조건 삭제(구글시트 복원 마스터는 숨김 메타가 없어 정상 블록도 VID 가 비어 보여 대량 오삭제 위험 → 상품조회 성공 시·이번 미기록 블록만).
- 영향 범위: product_match(괄호 규칙)·pipeline_process(_process_account·신규 _skip_unmatched/_purge_vidless_blocks/_finish_account)·designs/DESIGN.md §정밀매칭. 이전 설계 '미매칭=대장명으로 추적(통계 공란)'을 대체. ⚠ 미매칭 대장 상품은 결과·계정목록에서 사라지고 로그(⚠ 쿠팡 상품과 매칭 안 된 대장 상품)로만 보인다.
- 상태: ACTIVE

### D-009 [AI_MATCH_ANCHOR] 대장↔쿠팡 매칭 = AI 중심 + VID 고정 (2026-10-09, R3)
- 결정: 대장 상품 ↔ 쿠팡 등록상품 매칭을 **AI 가 결정**한다. 순서 = ①**VID 고정**(`output/_매칭고정.json`, 이전 확정 VID 가 지금도 쿠팡 상품조회에 있으면 그대로·AI 호출 없음·상품조회 실패일은 스냅샷 유지·VID 사라지거나 고정 상품이 판매중지면 재매칭·대장명 바꾸면 재매칭) ②괄호/이름 **정확일치** ③**AI 선택**(줄마다 후보 추림·등록명/노출명/옵션/판매상태·글자 규칙 결과는 참고 후보·같은 종류 없을 때만 null) ④AI 장애 시 글자 규칙 대체(로그·고정 안 함). 고정 = 정확일치·AI 확신 high/medium(low 는 매칭하되 매일 재판단). 마무리 공통 = 색상 필터(`build_tracked`)·동명 판매중 리스팅 함께(별도 블록)·다른 상품 두 줄이 한 후보면 우선순위 높은 줄만(경고). 대장명은 `Product.ledger_name` 으로 이월.
- 근거: 소유자 지시(2026-10-09 "파이썬이 상품명을 인식 못함 → AI 가 의미까지 분석해 매칭·관리대장 상품 95%는 쿠팡 등록상품·두 이름이 있으면 가장 유사한 상품 선택"·고정 여부 질문에 "고정함"). 실측: 10/09 봄날 '크리스마스트리 R060 (골드)' ↔ WING 등록명 '크리스마스 미니트리' 를 글자 규칙이 못 잡아 보강 경로(색상 필터 없음)로 실버·판매자배송 VID(96125939551·…553)가 섞임(원문 `woolins_vendor_inventory`). 운용 PC 10/09 원문 21계정 69줄 평가(실 OpenAI): 68줄 매칭·64 기존 동일·5 개선(트리 골드 로켓그로스 96125939552 만·LED 스탠드 판매자배송 중복 제거·코골이/DYM046/W200)·미매칭 1=케이씨 정리함(쿠팡에 없음). 게이트 16종·verify_offline[36]·복잡도 경고 0.
- 버린 대안: (a) 기존 정밀 규칙 우선 + AI 는 남은 미매칭만(기존 — 약칭·다른 등록명을 놓치고 보강 경로가 색상 무시) (b) 매일 처음부터 AI 매칭(소유자 '고정' 선택·AI 실패일 블록 삭제 위험) (c) 낮은 확신은 미매칭(소유자 '최대한 매칭' — 대신 고정 안 함).
- 영향 범위: 신규 `product_match_ai.py`·`match_anchor.py`, `pipeline_sales._match_to_ledger`(+`_roster_candidates`=상품조회 실패일만), `product_match.build_tracked`(scope_to_ledger 공통 마무리), `input_list.Product.ledger_name`, `pipeline.run_full` 이 `anchor_file` 전달. 삭제: `product_match.augment_unmatched/augment_ai`, `kw_ai.match_products`, `pipeline_sales._augment_vids/_augment_ai_match`. 계정당 OpenAI 1회(고정 안 된 줄이 있을 때만). ⚠ 첫 실행은 전 줄이 AI 판단(이후 고정). 기존 결과 블록 중 잘못 섞였던 VID 블록(봄날 트리 실버·판매자배송 '(9551)'·'(골드, Free_)', LED 스탠드 '(블랙_)')은 더 매칭되지 않아 다음 실행 reconcile ⑥(대장에 그 이름 없음)으로 이력과 함께 삭제된다.
- 상태: ACTIVE (부분 SUPERSEDED by D-011 — ③ '글자 규칙 결과는 참고 후보' → AI 에 보여 주지 않음(AI 장애 때 글자 규칙으로만 씀)·② 정확일치 = 대장 전체명/괄호 뺀 본문/괄호 속 이름 ↔ 등록명 또는 노출명 · 전역 'AI 매칭' 규칙의 예외로 ④ AI 장애 때 글자 규칙 임시 매칭 유지 — 소유자 확인 D-179)

### D-010 [SETTLE_LIFECYCLE] 정산 다운로드 = ①판매수집 뒤 앱이 기동·다 받으면 종료 (2026-10-09, R3)
- 결정: ①18:00 무인 앱이 시작되면 **이전 앱 창·정산 프로그램을 종료**하고 옛 정산 예약작업(로그온+08:00, 인자 `watch`)을 지운다(`app_process.prepare_auto_start` → 이어서 reap 이 그 Chrome 정리). ②**①판매수집(야간 1회 재시도 포함)이 끝나면 앱이 정산을 띄운다**(`start_settlement_watch`·창 없음·작업 묶음 분리 `CREATE_BREAKAWAY_FROM_JOB`, 불가 시 경고 후 그대로)·재부팅 복구(--resume)도 ①이 끝나 있으면 띄움. ③정산은 ②③와 병행하고, **모든 정산 파일을 받으면 '✅ 모든 정산 파일 다운로드 완료'를 기록하고 정상 종료**(`settlement_watch.plan_after_pass`). 연속 실패/차단 중단·진전 없는 대기 3바퀴 초과도 기록 후 종료(다음 ①완료 뒤 이어서). 같은 ①완료 기준 '완료'면 다시 돌지 않음(`output/정산/로그/_완료.json`). ④윙 지급내역 등 **HTTP 500 = 서버 일시 오류**(15초×2 재시도 후 그 계정 '대기'·차단으로 안 셈). ⑤윙 정산주기 **'M'(월정산 추정)** 은 그 줄만 건너뛰고 '확인 필요' 기록(계정 실패 금지·모르는 다른 코드는 여전히 중단).
- 근거: 소유자 지시(2026-10-09 "정산 실행 중 18시가 되면 앱이 하나 더 실행 → 18시 앱 실행 시 기존 정산 종료·판매수집 완료 후 정산 기동·순위 끝나도 계속·다 받으면 로그 남기고 정상 종료")·질문 답("정산 예약작업 삭제"·"500=서버 오류로 처리"). 실측(output(16) 10/08·10/09): 10/08 18:00:53·18:24·18:26 앱 시작 reap 으로 정산 Chrome 닫힘(대기로 흡수) · 10/09 00:41·00:44·12:01 지급내역 조회 500(HTML/빈 본문)이 차단·실패로 세어져 연속 2계정 중단 → 12:01 이후 정산 정지 · 노바네스트 'M' 이 10/08 18:29·10/09 11:53 계정 실패(중단 원인 1) · 옛 watch 는 중단(rc=1)을 '받을 정산 없음'으로 착각해 다음 ①완료까지 대기.
- 버린 대안: (a) 24시간 감시 유지(2026-10-07 결정 — 18:00 이중 실행·하루 종일 상주) (b) 정산 예약작업 유지(소유자 '삭제' 선택·시작마다 43계정 재로그인) (c) 500 계속 차단 취급(소유자 '서버 오류' 선택).
- 영향 범위: 신규 `src/coupang_analytics/app_process.py`, `settlement_watch.py`(plan_watch/24h 대기 → plan_after_pass·완료 기록), `tools/settlement_download.py cmd_watch`, `settlement_wing_api`(500·'M'), `ui/app_qt.py`(main·start_auto·start_resume), `ui/settlement_status_panel_qt.py`(명령 공유·배지 '종료'), `deploy/install.ps1`(정산 예약작업 등록 제거·남은 것 삭제)·첫실행 안내. 2026-10-07 '24시간 감시' 운용을 대체. ⚠ 운용 PC 재배포 필요·작업 묶음 분리 가능 여부는 첫 18:00 로그로 확인.
- 상태: SUPERSEDED by D-021(기동 시점·종료 규칙 — 18:00 이전 앱·정산 종료·예약작업 제거·HTTP 500·윙 'M' 처리는 D-021 에서 유지) · 윙 'M' 건너뜀 부분은 SUPERSEDED by D-075(월정산도 받음)

### D-011 [MATCH_ORDER] AI 매칭 판단 순서 = ①상품명 동일 ②문구 전체의 의미 (2026-10-09, R3)
- 결정: D-009 매칭의 판단 순서를 명시한다. ①**상품명 동일** — 대장 전체명·괄호 뺀 본문·괄호 속 이름(4자 이상) 중 하나가 쿠팡 **등록명 또는 노출명**과 공백·대소문자 무시 완전히 같으면 AI 없이 확정(같은 등록명 여러 리스팅=판매중 우선·동명 병합 유지 / 서로 다른 상품이 같은 이름이면 ②로 / 색상만 다른 대장 줄은 같은 상품 공유). ②**의미 매칭** — 글자 모양이 아니라 '무엇을 하는 어떤 종류의 상품인가'(용도·대상·형태)로 AI 가 판단(프롬프트 재작성·글자가 겹쳐도 의미가 다르면 다른 상품·모델코드는 보조 근거). 글자 규칙 결과는 AI 에 **보여 주지 않음**(글자 쏠림 방지·AI 장애 시 대체로만). 후보 150개 이하 계정은 전부 보내고, 그보다 많으면 **의미 유사도(OpenAI 임베딩 text-embedding-3-small)** 상위 15 + 글자 유사 5(보조)로 추림(임베딩 실패=글자 추리기·로그).
- 근거: 소유자 지시(2026-10-09 "AI로 매칭 시 첫째 상품명이 동일한지, 둘째 글자보다 전체적인 단어 문구의 의미로 매칭"). 실데이터(운용 PC 10/09 원문 21계정 69줄·실 OpenAI): 69줄 모두 기존 정답과 같은 VID·상품명 동일 41→61줄(노출명·본문 비교 추가)·AI 의미 7줄(코골이·HS0300→HS0030·DYM046·트리→미니트리·W200·빨래줄 R20→R020·마시는 알부민)·미매칭 1(케이씨 정리함=쿠팡에 없음). verify_offline[36]⑧·게이트 16종.
- 버린 대안: (a) 글자 규칙 결과를 '규칙 후보'로 AI 에 표시(D-009 초안 — 글자 쏠림) (b) 큰 계정을 글자 유사로만 추림(글자 안 겹치는 같은 상품 누락).
- 영향 범위: `product_match_ai`(MATCH_SYSTEM·_apply_exact·_candidate_ids·openai_embed·SEND_ALL_MAX 150), `pipeline_sales._match_to_ledger`(embed 전달). D-009 의 ③ 세부를 보완(D-009 는 ACTIVE 유지).
- 상태: ACTIVE

### D-012 [LEDGER_PW_CANDIDATES] 로그인 비밀번호 = 매 실행 현재 관리대장 값·줄마다 다르면 차례로 시도 (2026-10-09, R3)
- 결정: 계정아이디·비밀번호·상품명은 **매 실행 관리대장을 다시 읽어** 쓴다(앱 시작·자동 로드마다). 한 계정의 여러 줄(상품마다 한 줄)에 비밀번호가 **서로 다르면** 후보로 모두 남기고(`input_list.parse_password_candidates`·적은 줄에 적힌 값 먼저·같으면 위쪽 행), 로그인 시 첫 값이 **'비밀번호가 다릅니다'(LoginCredentialError)로 거부될 때만** 다음 값으로 1회 더(`pipeline_sales._login_with_candidates`·실행당 최대 2개 `PW_MAX_TRIES`). 후보가 1개면 지금과 같다(재시도 없음). 로드마다 '[비번] ⚠ 계정: 값1=행… · 값2=행…' 경고, 성공 시 '✅ N번째 값으로 로그인 성공'. 대장 비번 칸이 빈 계정은 PC 저장값 유지(소유자 선택). 단일 값 API(`parse_password_rows`·`parse_password_file`)는 마지막 줄 → 첫 후보로 변경.
- 근거: 소유자 지시(2026-10-09 "항상 현재 관리대장 비밀번호로 로그인·비밀번호가 바뀌어도 반영 안 됨·계정아이디/비밀번호/상품명 매번 비교")·질문 답("다른 값을 차례로 시도"·"빈 칸=예전 저장값"). 실측(관리대장 SA 읽기·값 미출력·지문 비교): (DW)커머스 9줄 중 40행만 다른 값·반달컴퍼니 57행≠60행 → 앱은 마지막 줄 값을 써 10/09 둘 다 '아이디 또는 비밀번호가 다릅니다'(정산 쪽 로그인은 같은 날 성공). 새 순서로는 두 계정 모두 10/09 실패 값이 아닌 값을 먼저 시도. 게이트 16종·verify_gsheet[15]·verify_offline[37].
- 버린 대안: (a) 다르면 로그인 안 하고 경고만(수집 공백) (b) 첫 줄 값 고정(DW 는 첫 줄도 옛 값) (c) 마지막 줄 값(기존·실패 원인).
- 영향 범위: `input_list`(PwCandidate·parse_password_candidates·read_xlsx_rows), `pipeline_sales`(_pw_list·_login_with_candidates), `ui/app_qt.py`(_apply_pw_candidates·_account_pw 가 후보 목록 반환·미사용 _store_passwords_from 삭제). ⚠ 값이 갈린 계정은 실행당 틀린 제출이 최대 1회 늘 수 있음 — 대장 정리 시 해소. 2026-09-15 '비번 1회 오류=재시도 금지'는 후보가 1개일 때 그대로 유지.
- 상태: ACTIVE (부분 SUPERSEDED by D-022 — '단일 값 API parse_password_file 은 첫 후보로' → 정리 B1 에서 함수 삭제 · D-023 — 'parse_password_rows 는 첫 후보로' → 정리 B4 에서 함수 삭제·후보 목록 로그인 규칙은 그대로)

### D-013 [EXPOSED_NAME] 결과 블록 이름 = 현행 쿠팡 노출상품명·같은 VID 개명 시 이력 승계 (2026-10-09, R3)
- 결정: 결과(통계 시트·계정목록) 블록 이름 = **쿠팡 노출상품명**(판매분석 productName·고객이 검색으로 보는 이름) + 옵션라벨(다중옵션만). 매 실행 추적 상품의 노출명을 확인(당일 판매분석 → 없으면 최근 30일 판매분석 1회 보충, `pipeline_sales._fill_exposed_names` → `Product.exposed_name`)하고, **같은 VID 의 기존 블록 이름이 다르면 새 이름으로 바꿔 이력 승계**(`pipeline_process._block_names` → `set_display_name`). 노출명을 모르는 날은 기존 이름 유지(등록명으로 되돌림 금지) — 단 등록상품명 자체가 바뀌면 새 등록상품명. 다른 상품 블록이 이미 그 이름이면 바꾸지 않고 경고(병합 방지). 등록상품명은 숨김 메타에 계속 최신화(`set_registered_name`).
- 근거: 소유자 지시(2026-10-09 "상품명은 때론 변경돼 — 노출순위가 낮아 검색에 걸리도록 바꿈·VID 는 동일·결과파일엔 변경된 상품명이 기술돼야(현행화)") + 기존 규약(결과=쿠팡 노출 상품명, 메모 product-name-convention). 실측(10/09 마스터 118블록·원문): 노출명 확인 44블록 중 40블록이 등록명≠노출명(예 '기저귀가방 CHMM01' vs '기저귀가방 출산선물 캔버스 백 …') → 결과가 노출명이 아니었음. 미리보기: 34블록 이름 현행화. 게이트 16종·verify_offline[38]·시뮬 day4(등록명 변경=갱신) 유지.
- 버린 대안: (a) 블록명=등록상품명 고정(2026-09 '노출명 교체 중단' — 검색용 개명 미반영·규약 불일치) (b) 순위 검색결과(SERP) 이름 사용(광고·표기 변형) (c) 모르는 날 등록명으로 표시(날마다 이름이 오락가락).
- 영향 범위: `input_list.Product.exposed_name`, `pipeline_sales._fill_exposed_names`(빈 것이 있을 때만 30일 판매분석 1회 추가 조회), `pipeline_process._block_names`·`_process_option(pname)`·`_migrate_product_blocks(names)`. 첫 실행에 기존 블록 다수가 긴 노출명으로 이름이 바뀜(이력·키워드·순위 유지).
- 상태: SUPERSEDED by D-015

### D-014 [RANK_NOTE] 통계 시트마다 1행 노출순위 조사 범위 안내 (2026-10-09, R3)
- 결정: 모든 통계(사업자) 시트 1행 H열에 '* (참고) 상품별로 노출순위를 조사하지만, 동일상품의 옵션 상품과 판매중지건은 노출순위를 조사 안함.' 을 파랑 굵게 표시(`config.RANK_NOTE_TEXT/COLOR`·`workbook_render` 제목행). 실제 규칙과 일치(2차 옵션 블록=순위행 없음·판매중지/취소선=rank_suppressed).
- 근거: 소유자 지시(2026-10-09 캡처 — 한 시트에 손으로 적은 안내가 매 미러링 전체 교체로 유지 안 됨·"모든 시트에 명시·판매중지건 추가·색상 동일"). verify_offline[38].
- 버린 대안: 시트에 수동 입력(미러링 때 사라짐).
- 영향 범위: `config.py`·`workbook_render.py`(apply_style 마다 멱등 기록).
- 상태: ACTIVE

### D-015 [EXPOSED_NAME_STRICT] 노출명 현행화 = 필수 — 못 찾으면 오류·③검색 노출명으로 그날 현행화 (2026-10-09, R3)
- 결정: D-013 을 대체. 결과 블록 이름 = 현행 쿠팡 노출상품명(+옵션라벨)이며 **반드시 현행화**한다. 출처 순서: ①당일 판매분석(productName 이 잘리면 옵션명 앞부분으로 복원 `_display_title`) → ①최근 30일 판매분석 보충 → **③순위 검색결과에서 그 상품(같은 VID)이 잡히면 그 노출명(첫 콤마 앞 제목)으로 그날 바로 개명**(`product_naming.rename_to_exposed`·상품 하나의 키워드 기록을 다 끝낸 뒤·같은 등록상품명의 옵션 블록도 라벨 유지해 함께·자동/반자동 순위 둘 다). ①에서 못 찾으면 '❌ [상품명] 노출명 확인 실패' **오류로 기록**(임시로 기존 이름 유지). 같은 VID 개명=set_display_name 이력 승계·다른 상품 블록과 이름 충돌이면 바꾸지 않고 경고. 등록상품명이 바뀌면 그 이름으로(기존 핀).
- 근거: 소유자 지시(2026-10-09 "노출명이 매칭 안 되면 오류임, 반드시 노출명은 현행화 해야 함" — D-013 의 '모르면 기존 이름 유지'를 거부). 실측: 노출명 출처인 판매분석은 그 기간 조회·판매가 있는 상품만 나옴(10/09 당일 44/118) → 검색결과 노출명(로그 '[노출명] 검색결과 노출명 = …')을 추가 출처로. verify_offline[38]·게이트 16종.
- 버린 대안: 모르는 날 기존 이름 조용히 유지(D-013 — 소유자 거부).
- 영향 범위: 신규 `product_naming.py`, `pipeline_ranks`(_measure_product_auto·_semi_track_product/_semi_record), `pipeline_sales._fill_exposed_names`(오류 기록·복원 제목), `pipeline_process._block_names`. ⚠ 판매중지(순위 제외)이면서 30일 판매·조회도 없는 상품은 노출명을 얻을 경로가 없어 오류 기록만 남음.
- 상태: ACTIVE (부분 SUPERSEDED by D-051 — 노출명 출처 순서: 판매분석(당일·30일) 다음에 윙 상품수정 화면 노출상품명 추가·❌ 오류는 그것까지 없을 때)

### D-016 [DESIGNATED_DATE] 날짜 지정 실행 = 그 날짜 칸을 빈 칸만 채움(판매=전날·순위=지금) (2026-10-10, R3)
- 결정: UI '날짜 지정'(옛 '기간' from~to 대체·날짜 하나)으로 실행하면 **그 날짜 칸**에 기록한다. 판매=그 날짜의 **전날** 판매분석(`column_dates`·'오늘' 실행과 같은 칸 규칙), 노출순위=**실행 시점에 측정한 값**을 그 칸에(전체실행 ③·순위 단독 둘 다 `track_ranks_stage(date_label=)`), **빈 칸만** 채움(판매=계정별 **칸별 수집 이력**으로 이미 수집한 칸은 로그인·수집 생략 · 순위=채워진 키워드 건너뜀). 오늘 다른 날짜로 진행하던 작업은 이어받지 않음(`plan_run_mode(designated=True)`). '오늘'·무인·재개 실행은 기존 동작 그대로(순위 단독 '오늘'=가장 최근 칸).
- 근거: 소유자 질문·지시(2026-10-10 "10.09 작업 중 중단·지금 10.10 — 날짜를 지정하면 그 날짜 칸에, 판매통계·노출순위 값은 실행시점 기준") + 질문 답("판매=지정 칸의 전날(10/08)"·"빈 칸만 채움"). 조사: 옛 '기간' 모드는 칸=끝 날짜·판매=그 날짜(칸 규칙과 하루 어긋남)이고 ③순위는 날짜와 무관하게 **최신 칸**에 기록(10.10 칸이 있으면 10.09 지정해도 10.10 에 들어감)·수집 완료 표시가 계정당 마지막 날짜 하나뿐이라 10.10 실행 뒤 10.09 지정 시 전 계정 재수집. 확인: 날짜 넘긴 중단 작업은 오늘 시작분만 이어받으므로 다음 날 실행은 새 작업(라벨=오늘)·날짜 지정 불필요. 시뮬 시나리오 15·핀 P8·verify_offline[38]·게이트 16종.
- 버린 대안: (a) 판매=실행시점 전날(10/09) — 같은 칸 안에서 계정마다 기준일이 섞이고 10.10 칸과 중복(소유자 선택 아님) (b) 그 칸 전부 다시 수집(전체 로그인·검색 — 소유자 선택 아님) (c) 기간 합계 모드 유지(칸 규칙과 불일치·사용 사례 없음).
- 영향 범위: `pipeline.column_dates`·`plan_run_mode(designated)`, `pipeline_ranks._rank_date`·`track_ranks_stage/_track_ranks_semi(date_label)`, `workbook.mark_sales_collected/has_sales/clear_sales_stamps`(칸별 이력 3열·판매수집일=최신 유지), `ui/app_qt.py`(날짜 지정 UI·`_run_dates`·전체실행/순위 단독). ⚠ 새 이력은 이번 배포 이후 수집분부터 쌓임 — 배포 전 수집한 칸을 10.10 실행 뒤 지정하면 그 계정은 한 번 재수집(같은 데이터 덮어씀·무해).
- 상태: ACTIVE (부분 SUPERSEDED by D-032 — 다른 칸 진행분 불이음은 날짜 지정 전용이 아니라 당일·무인도 공통)

---

## 전환 전 결정 (동결 아카이브)
2026-10-08 이전 한 줄 기록은 `docs/decisions/frozen-pre-2026-10-08.md`로 내용 그대로 옮겼다(D-142). 다른 문서가 `docs/DECISIONS.md(2026-09-29 …)`처럼 날짜로 가리키는 기록은 그 파일에 있다.

### D-017 [WORKBOOK_SPLIT] workbook.py 코어 mixin 분리로 MI C→B·복잡도 게이트 보호 대상 편입 (2026-10-10, R5)
- 결정: `OutputWorkbook` 코어(workbook.py 1585줄·MI C 0.00)를 **잘라 붙이기만**(로직 무변경)으로 mixin 3개에 나눈다 — `workbook_meta.py`(`_MetaMixin`·숨김 메타시트 상품 속성 38메서드) · `workbook_dates.py`(`_DateMixin`·날짜 칸·수집 이력·측정 주기 16메서드) · `workbook_lifecycle.py`(`_LifecycleMixin`·대장 대조·판매중지 동기화·삭제·병합 7메서드). 결과 workbook.py 596줄 **MI B(18.83)**·새 모듈 전부 A. `tools/check_complexity.KNOWN_BAD` 에서 **workbook.py 제외** → 앞으로 MI C 추락 커밋은 차단.
- 근거: 소유자 지시(2026-10-10 "C부터 진행" = 800줄 초과 파일 모듈 분리·계획 승인) + KNOWN_BAD 제외 선택. 실측 — 분리 전 radon MI C(0.00)·4대형 파일 중 유일한 C(pipeline_ranks·collector·pipeline 은 B). 행동 불변 증거: 단계마다 `OutputWorkbook` 멤버 144개 바이트코드 지문을 7e119b4 대비 대조 → 차이 0 · 이동 메서드 전역 참조 미정의 0 · 게이트 16종·복잡도 초록 · 음성 테스트(옛 C 파일 → check_complexity exit 1). 외부 호출처 수정 0(외부 import=OutputWorkbook·_norm·_key·_unmerge_all·상수뿐·내부 monkeypatch 0).
- 버린 대안: (a) 보류 유지(2026-09-26 판단 "인위적·효과 대비 낮음" — 소유자가 실행 선택) (b) pipeline_ranks·collector·pipeline 도 분리(이미 MI B·건강 파일 미접촉 규칙) (c) KNOWN_BAD 유지(재비대 감지 못함 — 소유자 선택 아님).
- 영향 범위: `src/coupang_analytics/workbook.py`·`workbook_meta.py`·`workbook_dates.py`·`workbook_lifecycle.py`(신규), `tools/check_complexity.py`(KNOWN_BAD), `designs/CODE_HEALTH_PLAN.md §8-3 6c`. 런타임 동작·출력물 무변경(배포는 다음 빌드에 자연 포함·PyInstaller 정적 import 추적). ⚠ workbook.py 의 D+ 괴물함수는 이제 다른 건강 파일처럼 경고(차단은 MI C).
- 상태: ACTIVE

### D-018 [LEDGER_PW_TRIM] 관리대장 비밀번호 앞뒤 공백은 떼고 입력·뗀 행은 경고 (2026-10-10, R5)
- 결정: `input_list.parse_password_candidates` 가 비번 칸 값의 **앞뒤 공백(스페이스·탭·  등)을 떼고** 후보로 쓴다(PC 엑셀·구글 대장·Tk 폴백 모든 경로가 이 함수를 거침). 공백만 있는 칸=빈 칸(저장값 유지). 공백만 다른 값은 한 후보로 합침. 뗀 행은 `PwCandidate.trimmed` 로 남겨 앱이 `[비번] ⚠ {계정}: 관리대장 행 … 비밀번호 앞뒤에 공백이 있어 떼고 입력합니다. 대장에서 공백을 지워 주세요` 를 기록. 대장 원문은 바꾸지 않음(읽기만).
- 근거: 소유자 승인(2026-10-10 "코드 쪽 방지책 승인"). 실측 — (DW)커머스 판매량 10.04~10.09 공란 원인 분석: 10/03 까지 로그인 성공한 값(지문 1ab2130e)은 대장 40행에만 남고, 39·42~48행은 **새 값+끝 공백 1칸(13자)** 이라 그대로 타이핑돼 10/04 부터 매 실행 "아이디 또는 비밀번호가 다릅니다". 같은 끝 공백이 플랜잇 22행(9/28 부터 거부)·반달 57행에도 있음. 코드: 비번을 strip 없이 읽어(`input_list.py`) `autofill_login` 이 한 글자씩 입력. 재현 테스트 verify_gsheet_offline[16] 실패 → 수정 → 통과 · 게이트 16종·복잡도 초록 · 실제 대장 읽기(지문만): DW 값2·플랜잇·반달 공백 제거 확인.
- 버린 대안: (a) 대장 정리만 요청(같은 실수 재발 시 또 며칠 공란) (b) 공백 그대로 두고 경고만(로그인 계속 실패) (c) 원문·공백뗀 값 둘 다 시도(오답 제출 늘어 잠금 위험). 실제 비번이 공백으로 시작·끝나는 경우는 지원하지 않음(사례 없음·쿠팡 정책 미확인).
- 영향 범위: `src/coupang_analytics/input_list.py`(PwCandidate.trimmed·parse_password_candidates), `ui/app_qt.py`(_apply_pw_candidates 경고), `tools/verify_gsheet_offline.py`(t16). D-012 후보 순서(적은 줄 먼저)는 그대로 — DW 는 40행 옛 값이 값1이라 실행마다 1회 거부 후 값2(새 값)로 시도. ⚠ 반달(mrc098)은 57·60행이 공백만 다른 같은 값이고 그 값이 10/10 에 이미 거부됨 → 이 수정과 무관하게 **대장 비번 자체가 틀림**(담당자 확인 필요).
- 상태: ACTIVE

### D-019 [DESIGNATED_SKIP_FILLED] 날짜 지정 실행 — 칸별 이력 없는 옛 칸은 판매값 있는 계정 로그인 생략 (2026-10-10, R5)
- 결정: 날짜 지정(D-016) 실행에서 그 칸의 칸별 수집 이력(`_수집스탬프` 3열)이 없는 계정도, **그 계정 상품의 판매 지표 칸에 값이 하나라도 있으면** 이미 수집된 것으로 보고 로그인·판매수집을 생략한다(`workbook.sales_filled`·`run_full(designated=)`·`_RunCtx.designated`). 값이 하나도 없으면 지금처럼 수집. **날짜 지정일 때만** 적용 — '오늘'·무인·재개 실행은 기존(스탬프만) 그대로. UI 는 '날짜 지정' 라디오면 `designated=True` 전달(app_qt).
- 근거: 소유자 결정(2026-10-10 "코드 보완 후 채우기"·"판매·순위 둘 다"). 실측 — 칸별 이력은 10/10 01:04 실행부터 쌓여 10.04~10.08 은 이력이 없음 → 기존 코드로 날짜 지정 시 날짜마다 24계정 전부 재로그인(5일 ≈ 120회 불필요 로그인·차단/2차인증 위험). 운용 마스터(zip 사본)에 새 판정 적용 결과 로그인 대상 = 날짜마다 4계정(DW·플랜잇·하성진·안재현)·10.09 는 3계정 = 판매 공란 시트 집계와 일치. 시뮬 시나리오 16(이력 없는 옛 칸: 값 있는 계정 생략·빈 계정 수집·'오늘' 모드 대조=기존 동작) 실패→통과·게이트 16종·복잡도 초록.
- 버린 대안: (a) 그대로 날짜마다 전 계정 재수집(로그인 과다) (b) 모든 실행에 값 판정 적용('오늘' 실행이 계정 중간 실패로 칸 일부만 찬 경우 재실행이 그 계정을 건너뛰는 회귀 위험) (c) 스탬프 소급 생성 도구(일회성·판정 근거는 결국 같은 값).
- 영향 범위: `src/coupang_analytics/pipeline.py`(run_full·_RunCtx·_collect_session_first), `workbook_dates.py`(sales_filled), `ui/app_qt.py`(do_run_full→_full_pipeline_task), `tools/simulate_pipeline.py`(시나리오 16). 판정은 "값 있음=수집됨" 한 방향 — 공란은 다시 수집(틀려도 로그인 1회 더·데이터 누락 없음). Tk 폴백(app.py)은 날짜 지정 UI 가 없어 무변경.
- 상태: ACTIVE

### D-020 [SETTLE_STOP_WITH_APP] 앱을 사람이 끄면(배포 등) 정산 프로그램도 함께 종료 (2026-10-10, R5)
- 결정: 앱이 정산을 띄울 때 자기 PID 를 넘기고(`watch --parent PID`), 정산이 그 PID 를 감시(`app_process.watch_parent`·프로세스 핸들 대기)한다. 앱이 **무인으로 스스로 끝날 때**(`_auto_quit` — ①②③ 완주·재부팅 복구 할 일 없음 등)는 표시 파일(`output/정산/로그/_앱정상종료.json`·앱 PID)을 남기고, 이 표시가 없는 앱 종료 = **사람이 창을 닫거나 작업 관리자로 강제 종료** → 정산이 사유를 상태 파일에 쓰고 자기와 자식 Chrome 을 종료(`kill_self_tree`). 정산 탭 [정산 시작]도 같은 한 경로(`start_settlement_watch`)로 띄운다(따로 있던 두 번째 실행 코드 삭제).
- 근거: 소유자 지시(2026-10-10 "재배포를 위해 앱을 강제 종료하면 정산다운로드도 종료돼야") + 실측(작업 관리자에 앱 종료 뒤 `정산다운로드.exe` 121MB 잔존·운용 로그상 07:15 까지 요청 중 — 앱과 분리 기동 `CREATE_BREAKAWAY_FROM_JOB` 이라 남음). 재현 테스트 P26 실패→통과·실제 프로세스 e2e: 사람 종료 0.5s 뒤 정산 종료·무인 정상 종료 15s 뒤에도 계속·게이트 16종.
- 버린 대안: (a) 앱 closeEvent 에서만 정산 종료(작업 관리자 강제 종료는 못 잡음) (b) 배포 스크립트가 정산 종료(배포=폴더 덮어쓰기라 스크립트 없음) (c) 작업 묶음 분리 해제(무인 완주 뒤 정산 계속이 깨짐).
- 영향 범위: `src/coupang_analytics/app_process.py`(settlement_watch_cmd(parent_pid)·mark_app_finished·app_finished_normally·watch_parent·kill_self_tree), `tools/settlement_download.py`(--parent·_watch_app), `ui/app_qt.py`(_auto_quit 표시), `ui/settlement_status_panel_qt.py`(_settle_start 단일 경로), `tools/verify_settlement_runtime_offline.py`(P25·P26). ⚠ 지금 운용 PC 에서 도는 정산은 옛 코드(감시 없음)로 떠 있어 재배포 때 한 번은 작업 관리자에서 직접 종료 필요.
- 상태: ACTIVE

### D-021 [SETTLE_CYCLE] 정산 = 18:00 앱과 함께 기동·①완료까지 대기·다 받으면 종료·다음 날 17:55 종료 (2026-10-10, R5)
- 결정: 회차 = **18:00 ~ 다음 날 17:55**(`settlement_watch.cycle_window`). 18:00 무인(`--auto`)·재부팅 복구(`--resume`) 앱이 **시작하면서 정산도 띄운다**(① 뒤 기동 코드 2곳 삭제). 정산은 **이번 회차의 ①판매수집 완료 기록**(`_실행단계.json` stage∈sales/ranks/done·at ≥ 회차 시작 — `sales_done_in_cycle`)이 생길 때까지 대기 → 받기 → **다 받으면 바로 종료**(소유자 선택) · 못 다 받아도 **17:55 이후 새 요청·새 계정 안 함 후 종료**(`until_at`=회차 끝) → 18:00 둘 다 다시 기동(기존 18:00 정리 = 남은 앱·정산 종료는 안전장치로 유지). 앱이 ①②③을 끝내고 종료해도 정산은 계속(D-020 표시). HTTP 500=서버 일시 오류·윙 'M' 건너뜀 등 D-010 의 처리 규칙은 그대로.
- 근거: 소유자 지시(2026-10-10 "단순하게: 18시 앱과 정산다운로드 실행 → 정산은 대기하다 판매수집 완료되면 시작 → 앱 ①②③ 완료돼도 계속 → 다음 날 17:55 종료 후 18시 둘 다 실행") + 질문 답("다 받으면 바로 종료"). 테스트 P27(가짜 시계로 실제 cmd_watch: ① 미완료·지난 회차 기록=대기만 하다 17:55 종료·19:30 ① 완료 뒤 받기·다 받으면 종료)·e2e(정산 '①판매수집 완료 대기' 상태 확인)·게이트 16종·복잡도 초록(cmd_watch C12 — 3회째 수정이라 제자리 재작성).
- 버린 대안: (a) D-010 유지(① 뒤 앱이 기동 — 소유자 요구와 기동 시점 다름) (b) 다 받아도 17:55 까지 상주(소유자 선택 아님) (c) 정산 전용 예약작업 부활(D-010 에서 폐지·실행 경로 둘).
- 영향 범위: `settlement_watch.py`(CYCLE_START·cycle_window·sales_done_in_cycle), `tools/settlement_download.py`(cmd_watch 재작성·_watch_wait_reason·_sleep_until), `app_process.py`(시작 로그·설명), `ui/app_qt.py`(main 에서 auto/resume 시 start_settlement_watch·① 뒤 기동 삭제).
- 상태: ACTIVE (부분 SUPERSEDED by D-075 — 윙 'M' 건너뜀 문구)

### D-022 [CLEANUP_SCOPE] 기능 전수 목록 기반 정리 — 유지 범위·삭제 순서·오류 일괄 수정 (2026-10-10, R5)
- 결정: 기능 SSOT = `designs/FEATURE_INVENTORY.md`(무엇이 있고·운영에서 쓰이고·게이트가 지키는가). 유지 = 수동 탭 4개(판매 분석·키워드 추천·순위 조회·상세 이미지)·신규 도메인(통합앱 셸·계약·채권자·업무일지·CS·소싱 — 나중 연결)·정산 ②층 설계 자산(`settlement_amount`·Insights 파서). 정리 = 배포 안 되는 Tk 앱·일회성 도구·쓰기만 하는 저장소·테스트 전용 함수·운영에서 안 도는 분기·중복 구현을 **묶음 단위(B1~B6)로 호출처 재확인 → 물리 삭제 → 게이트 → 커밋**. 운영에서 안 도는 분기는 **게이트 시나리오를 운영 조합으로 먼저 이전**한 뒤 삭제. 확인된 오류 E1~E7 은 정리 뒤 일괄 수정.
- 근거: 소유자 지시(2026-10-10 "모든 기능을 나열 → 불필요·유사중복 통합·영구 삭제 → 소스 단순화로 고칠 때마다 다른 기능이 깨지는 오류 반복을 끊자") + 선택 답(탭 4개 유지·신규 도메인 유지·정리 진행·오류는 나중에 동시 수정). 조사 근거: 운영 run_full 호출은 전부 keywords_off=True·skip_ranks=True·③ semi=True 고정 ✔ → 게이트 시나리오 다수가 **운영에서 안 도는 경로**를 검증(회귀가 게이트를 빠져나가는 구조적 원인).
- 버린 대안: (a) 전체 재작성(전역 규칙 금지·엣지케이스 폐기) (b) 목록만 두고 보류(소유자 선택 아님) (c) 신규 도메인 삭제(소유자 선택 아님).
- 영향 범위: B1(ui/app.py·parse_password_file)·B2(tools 일회성 10개) 완료, B3~B6·E1~E7 은 FEATURE_INVENTORY §6 순서대로. 로컬 사본 폴더(git 밖)·reusable_coupang 은 소유자 확인 대상.
- 상태: ACTIVE (부분 SUPERSEDED by D-037 — 통합앱·계약·채권자·업무일지·CS 유지 → HQ 이전 후 삭제 · SUPERSEDED by D-038 — reusable_coupang 삭제)

### D-023 [CLEANUP_KEEP_SETTLE2] 정리 B4 — `payout.estimate`·`registry.managed_between` 은 정산 ②층 설계 자산으로 유지 (2026-10-10, R5)
- 결정: B4(테스트 전용 함수 삭제)에서 `payout.estimate`(미래 지급일·금액 추정)·`registry.managed_between`(기간 중 관리한 계정)은 **삭제하지 않고 유지**. D-022 의 '정산 ②층 설계 자산 유지'(`settlement_amount`·Insights 파서)와 같은 범주로 본다. 나머지 B4(`scope_to_ledger`·`parse_password_rows`·`proxy_manager` 미사용 메서드 12개+`active_count`)는 삭제.
- 근거: 두 함수는 지금 테스트만 호출(호출처 grep: `verify_settlement_offline.py:145`·`verify_registry_offline.py` R12)이지만, 설계서가 ②층 입력으로 지정 — `designs/SETTLEMENT_MODEL.md` §92(관리 기간=`managed_between`)·§139(`estimate`)·`designs/DOMAIN_D8_SETTLEMENT_PHASE23.md` §131~132(예상 달성일=`estimate`·관리 기간=`managed_between`). 소유자 선택(2026-10-10 "둘 다 유지").
- 버린 대안: (a) 둘 다 삭제(②층 구현 때 재작성 필요·설계서와 불일치) (b) `managed_between` 만 유지.
- 영향 범위: `designs/FEATURE_INVENTORY.md` §3-3·§6 B4. 코드 변경 없음(두 함수와 테스트 그대로).
- 상태: ACTIVE

### D-024 [CLEANUP_B6_MERGE] 정리 B6 — 단계 조립 단일화·정산 중지 일원화·`정산_지금실행.bat` 삭제 (2026-10-10, R8)
- 결정: ①전체실행·무인(`--auto`)·재부팅 복구(`--resume`)의 ①→②→③→재고 역기록 조립을 `pipeline_stages.run_stages` 하나로(UI 는 `StagePlan` 만 정함·복구 계획=`plan_resume_stages`). 세 벌이 갈라져 있던 규칙은 **단계 기록 = 실제로 끝난 단계**로 맞춤: ① 끝=sales(중지 요청이 있어도 ①이 끝났으면 기록 — 정산 D-021 이 이 기록을 봄) · ② 끝=ranks · ③을 중지 없이 끝냄=done · ① 단독은 기록 없음 · **재고 역기록은 ③까지 갔으면 함**(예전 전체실행 방식 — 무인에서 ③ 도중 사람이 중지한 경우만 달라짐). ③ 날짜 칸은 전체실행만 ①과 같은 칸 지정, 무인·복구는 최신 칸(기존 그대로). ②절전 방지 = `power.keep_awake` 하나(`app_qt._prevent_sleep` 삭제·같은 API). ③정산 중지 = `app_process.stop_settlement` 하나로(정산 탭 [정산 중지]도) — 그 정산이 띄운 Chrome 까지 **트리 종료**(`taskkill /F /T`)로 바꿈. ④18:00 마다 옛 정산 예약작업을 지우던 코드 삭제(install.ps1·자동실행_삭제가 계속 지움). ⑤`deploy/정산_지금실행.bat`(회차·앱 종료 감시와 무관하게 `run` 으로 즉시 실행) 삭제 — 수동 실행은 정산 탭 [정산 시작](watch·①완료 대기) 하나.
- 근거: 소유자 지시 D-022(중복 통합) + ⑤는 소유자 선택(2026-10-10 "삭제"). 핀 P9~P11(가짜 단계로 순서·단계 기록·야간 1회 재개·중지)·게이트 16종·복잡도 경고 0·실제 프로세스 e2e(가짜 settlement_download.py 와 그 자식 → stop_settlement 후 둘 다 종료)·UI offscreen import.
- 버린 대안: (a) 세 벌 유지(한 곳만 고치면 갈라지는 회귀 구조) (b) 단계 기록을 무인식 '중지 시 생략'으로 통일(①이 끝났는데 정산이 시작 못 함) (c) 정산 중지를 Stop-Process 그대로(패널에서 끄면 정산 Chrome 잔존 — 18:00 reap 은 앱의 순위 Chrome 까지 끄므로 패널에서 못 씀) (d) bat 을 watch 로(즉시 실행 기능이 사라져 존재 이유 없음).
- 영향 범위: `src/coupang_analytics/pipeline_stages.py`(신규), `ui/app_qt.py`(_full_pipeline_task·_stages_task·start_auto·start_resume·_prevent_sleep 삭제), `src/coupang_analytics/app_process.py`(_KILL_PS 트리 종료·stop_settlement(tag)·remove_legacy_settlement_task 삭제), `ui/settlement_status_panel_qt.py`(_kill_settlement 삭제), `deploy/정산_지금실행.bat`(삭제)·`build.bat`·`deploy/첫실행_설정안내.txt`, `tools/pin_run_plan.py`(P9~P11). ⚠ 운용 PC 재배포(폴더 덮어쓰기)는 옛 `정산_지금실행.bat` 을 지우지 않음 → 직접 삭제. 재배포 때 설치.bat 실행(E3 재등록과 함께)으로 옛 정산 예약작업도 정리됨.
- 상태: ACTIVE (부분 SUPERSEDED by D-091 — ④ 18:00 옛 예약작업 제거 복원)

### D-025 [FIX_E1_E7] 오류 E1~E7 일괄 수정 — 직원 키워드 역머지는 ① 시작·마스터 복원 SA·예약작업 23시간50분 (2026-10-10, R8)
- 결정: **E1** 직원이 결과시트에 넣은 키워드 역머지(`pull_gsheet_keywords`)를 **① `run_full` 시작에 무조건** 호출(원래 설계 위치 복원). FEATURE_INVENTORY 의 '② 시작에 연결' 안은 버림 — ①이 끝날 때 결과시트를 전체 교체(`push_gsheet`)하므로 ② 시점엔 이미 덮어써짐. **E2** 마스터 복원(`restore_master_from_gsheet`)을 공개 export → **서비스계정 + 저장 타입 그대로(`read_values(unformatted=True)`)** 로, 호출처가 없어진 `gsheet.download_xlsx` 삭제(구글시트 내려받기 2벌 통일). **E3** 18:00·재부팅 복구 예약작업 실행 제한 13시간 → **23시간50분**(다음 날 18:00 실행만 막지 않게). **E4** `정산_상태확인.bat` 이 없앤 정산 예약작업 대신 18:00 야간 무인 작업(--auto)을 조회. **E5** '06:00 자동 종료' 문구 → '다 끝나면 스스로 종료'(install.ps1·install_schedule_py.ps1·첫실행 안내·INSTALL.md). **E7** 게이트 개수 표기 제거(run_checks·install_hooks·CLAUDE.md — 늘 때마다 어긋남).
- 근거: E1 재현 시나리오 simulate 17 실패(['push'] — 역머지 없음)→수정 후 통과(['pull','push']·직원 키워드 보존)·B5-2 에서 지운 주석 "미러링 전에 워크북에 들어가야 종료 시 전체 교체돼도 보존". E2 실측(읽기만): 공개 export=401·SA 스냅샷=표시값이라 숫자 704칸이 글자 → UNFORMATTED 로 복원 시 사업자 시트 24·숫자 3,140칸 숫자 유지·apply_style→저장→재로드 정상, 게이트 verify_gsheet[17]. E3 근거=FEATURE_INVENTORY §2(07:00 넘는 실행이면 스케줄러가 앱 종료 → D-020 상 정산도 종료)·PowerShell 구문 검사 0 오류. E4 bat 블록을 cmd 로 실행해 등록/미등록 두 분기 확인. 게이트 16종.
- 버린 대안: (a) E1 을 ② 시작에(위 이유로 소실) (b) E1 을 ①②③ 시작마다(시트 반영이 실패한 날 다음 단계 역머지가 시트에 없는 키워드를 지우는 위험 증가 — 동기화는 삭제도 반영) (c) E2 를 표시값 스냅샷 그대로(숫자가 글자로 들어가 이후 계산·비교 오류) (d) E3 제한 없음(다음 날 18:00 실행이 '이미 실행 중'으로 막힐 수 있음).
- 영향 범위: `pipeline.py`(run_full 역머지 호출), `pipeline_gsheet.py`(restore·_download_gsheet_via_sa(unformatted)), `gsheet_api.py`(read_values(unformatted)), `gsheet.py`(download_xlsx 삭제), `deploy/install.ps1`·`install_schedule_py.ps1`·`정산_상태확인.bat`·`첫실행_설정안내.txt`·`INSTALL.md`, `tools/run_checks.py`·`install_hooks.py`, 게이트 `simulate_pipeline.py`(17)·`verify_gsheet_offline.py`(17). ⚠ E3 은 운용 PC 에서 **설치.bat 재실행(자동실행 등록 Y)** 해야 반영.
- 상태: ACTIVE

### D-026 [CLEANUP_B7_DEAD] 정리 B7 — 호출처 없는 잔여 코드 물리 삭제(노출측정·병렬 순위·늘 고정인 인자) (2026-10-10, R9)
- 결정: 호출처가 없거나 운영에서 늘 같은 값인 코드를 지운다 — ①`rank.organic_ranks`·`organic_ranks_batch` 와 그 둘만 쓰던 헬퍼(`_BATCH_FETCH_JS`·`_pages_for`·`_prime_search`·`_batch_urls`·`_score_batch`·`_set_mobile`·`_chrome_major`), 그 전용 config(`RANK_INCLUDE_MOBILE`·`RANK_ORGANIC_PER_PAGE`·`RANK_HUMAN_SERIAL`·`RANK_FETCH_CONCURRENCY/JITTER_MIN_MS/JITTER_MS`·`RANK_BLOCK_BACKOFF_SEC/RETRIES`) — L1 공개 API 에서도 뺌(L1_CONTRACT·pin_l1_contract). ②`kw_recommend.select_keywords_light(measure_ranks=)`(늘 None) → 노출측정 분기 삭제(`_score_pool` = 부분점수만·결과 동일). ③`run_full(sales_semi)`(늘 True → ① 로그인은 늘 반자동)·`run_title(sales_semi)`·`do_run_full(sales_semi)` · `run_log_labels(skip_ranks)`·`do_run_full` 의 `skip_ranks`(늘 False) · `do_track_ranks(semi)`(미사용). ④`pipeline_sales.py` 미사용 import 11개. ⑤`ProxyNode` 건강 필드 6개(`consecutive_failures`·`latency_ms`·`last_verified`·`last_error`·`success_count`·`failure_count`)·`ProxyManager(max_failures, strategy, verify_url)`·`_index`(노드 선택은 proxy_pool). ⑥DESIGN §4.4 '세션 킵얼라이브' 문단(모듈이 존재한 적 없음)을 사실대로 정정.
- 근거: 소유자 지시(2026-10-10 "1번 B7로 진행해" — 직전 보고의 '호출처 없는 잔여 코드' 목록). 항목마다 grep·AST 로 호출처 재확인(rank.py 내부 호출 그래프 포함). `_login_and_discover(semi=False)`·`_ensure_login(semi=False)` 는 정산 무인 경로가 써서 **유지**(run_full 의 인자만 삭제). 게이트 16종·복잡도 경고 0·UI offscreen import.
- 버린 대안: (a) `organic_ranks` 를 L1 공개 API 로 계속 유지(호출처 0·offscreen 순위는 정책상 폐기 — 남기면 다시 쓰일 위험) (b) `sales_semi=False` 경로 유지(운영에서 안 도는 분기 = 게이트를 빠져나가는 회귀 구조, D-022 와 같은 이유).
- 영향 범위: `rank.py`(530→274줄), `config.py`, `kw_recommend.py`, `pipeline.py`, `pipeline_stages.py`, `pipeline_sales.py`, `proxy_manager.py`, `proxy_pool.py`, `ui/app_qt.py`, 게이트 `pin_run_plan`(P7)·`pin_l1_contract`·`simulate_pipeline`·`verify_offline`, 문서 DESIGN·KEYWORD_SELECTION·PLATFORM_INTEGRATION·L1_CONTRACT·FEATURE_INVENTORY·CLAUDE.md.
- 상태: ACTIVE

### D-027 [CLEANUP_B8_HELD_TOOLS] 보류 도구 결정 — `test_rank_images_live` 삭제·나머지 7종 유지 (2026-10-10, R9)
- 결정: FEATURE_INVENTORY §3-5 '보류(소유자 확인)' 도구 중 `tools/test_rank_images_live.py`(순위 이미지 ON/OFF 라이브 A/B)만 **삭제**. `diag_inv_hidden`·`probe_proxy_pool`·`migrate_to_operation_ledger`·`build_operation_template`·`build_inventory_template`·`build_result_sample`·`build_product_card_demo`·`deploy/install_schedule_py.bat/.ps1` 은 **유지**. 순위 이미지 끄기 설정(`rank/block_images`·기본 OFF)은 그대로 둔다(도구만 삭제).
- 근거: 소유자 선택(2026-10-10 "2번 삭제, 나머지 유지"). 삭제 도구는 참조처 없음(git grep: STATE·FEATURE_INVENTORY 목록뿐). Claude 제안(diag_inv_hidden·build_product_card_demo 삭제)은 소유자가 유지로 결정.
- 버린 대안: (a) Claude 제안(1·8번도 삭제) (b) 전부 유지.
- 영향 범위: `tools/test_rank_images_live.py`(삭제)·`designs/FEATURE_INVENTORY.md` §3-5·`STATE.md`.
- 상태: ACTIVE

### D-028 [FIX_RANK_KW_LOSS] 순위 공란·키워드 칸 누락 근본 수정 — 이어서 하기 기준 파일·③ 날짜 칸 이름·대표 블록 키워드 칸 (2026-10-10, R10)
- 결정: ①'이어서 하기'는 진행 파일과 마스터 중 **나중에 저장된 것**을 기준으로 이어간다(`pipeline._resume_source`). ②③ 날짜 칸 이름은 ①과 같은 규칙 `pipeline_paths.column_label`('2026-10-09'→'10.09')로 만든다(`_rank_date`). ③대표 옵션 블록에 키워드 소헤더가 없으면 지표행 아래에 끼워 넣는다(`OutputWorkbook.ensure_keyword_section`, `_process_option` 대표일 때).
- 근거: 결과시트 읽기(SA): 10.09 칸 순위 값 = 25시트 전체 0개(10.08 은 169개)·키워드 칸 없는 블록 42개(옵션 라벨 없는 단독 블록 포함 — DW 빔프로젝터·원룸 공기청정기, 노트북 10-02 마스터에선 키워드 칸 있었음). 재현: (1) ① 미완료 계정이 남아 진행 파일이 ②③ 이전 상태로 남은 뒤 같은 날 '이어서 하기' → 앞 실행 키워드 `['kw1','kw2']`·순위 `3위` 소멸(simulate 18 실패→통과) (2) 옵션 2개→1개로 바뀌면 남은 2차 블록이 키워드 칸 없이 대표가 됨(simulate 19 실패→통과) (3) 전체실행(사람)·날짜 지정이 ③에 ISO 를 넘겨 '2026-09-02' 별도 칸 생성·채운 칸 재측정(simulate 20 실패→통과). 게이트 16종·복잡도 0. 기존 테스트 2곳(simulate 15·verify_offline [38])은 ISO 별도 칸을 기대값으로 고정하고 있어 실제 칸 이름('월.일')으로 정정. ⚠ 운용 PC 로그 미확인 — 10.09 공란이 (1) 경로였는지는 로그(`output
un_log_*.log`)로 확인 필요.
- 버린 대안: (a) ②③ 저장 때 진행 파일도 함께 저장(저장 지점이 많아 누락 위험) (b) 키워드 칸 없는 블록을 지우고 새로 만들기(판매 이력 손실) (c) 2차 옵션 블록에도 키워드 칸(순위는 상품 단위 — 소유자 확정 설계 유지).
- 영향 범위: `pipeline.py`(_resume_source·_column_label), `pipeline_paths.py`(column_label), `pipeline_ranks.py`(_rank_date), `workbook.py`(ensure_keyword_section), `pipeline_process.py`(_process_option), `tools/simulate_pipeline.py`(18·19·20·15 정정), `tools/verify_offline.py`([38] 정정).
- 상태: ACTIVE

### D-029 [LOGIN_NO_SKIP] ① 로그인 서킷브레이커 폐지 — 차단돼도 전 계정 시도·① 끝에 미완료 계정 즉시 1회 재시도·야간 30분 재개 폐지 (2026-10-10, R10)
- 결정: ① 로그인 패스에서 연속 차단(옛 `LOGIN_BLOCK_CIRCUIT=3`)이어도 남은 계정을 **건너뛰지 않는다**. 세션우선·로그인 패스가 끝나면 **완료 안 된 모든 계정**(차단·로그인 미완료·2차인증·처리 오류 — 비번 오류·의도적 생략은 완료 처리라 제외)을 **바로 1회 재시도**(`pipeline._not_done`·`_collect_with_login(pace_first)`). 무인 전용이던 '30분 쿨다운 후 1회 재개'(`pipeline_stages._night_resume`·`StagePlan.night_resume`·`LOGIN_NIGHT_RESUME*`)는 이 재시도로 대체해 삭제(모든 실행 공통). 로그인 사이 간격(45~120초)·비번 오류 재시도 금지·Akamai 차단 감지는 그대로.
- 근거: 소유자 지시(2026-10-10 "단 1개의 계정도 누락되면 안됨", "30분 쉬지 말고 ① 끝난 뒤 바로 남은 계정 다시 시도") + 선택 답("멈추지 않고 끝까지 시도 + 끝나면 실패 계정 즉시 재시도"). simulate 8 을 새 기대값으로 다시 씀(실패→통과: 차단 계정마다 로그인 2회·첫 시도만 막힌 계정은 재시도에서 수집·미수집 있으면 진행 파일 유지). 게이트 16종·복잡도 0.
- 버린 대안: (a) 서킷브레이커 유지(누락 발생) (b) 실패 계정 0 이 될 때까지 무한 반복(IP 차단 지속 시 끝나지 않음) (c) 야간 30분 재개 유지(소유자 지시와 다름·재시도 중복).
- 위험(소유자 감수): 차단된 IP 로 남은 계정 로그인을 계속 두드려 그 IP 가 더 오래 막힐 수 있다(로그인 간격으로 완화).
- 영향 범위: `pipeline.py`(_collect_with_login·_not_done·run_full), `pipeline_stages.py`, `config.py`(LOGIN_BLOCK_CIRCUIT·LOGIN_NIGHT_RESUME* 삭제), `ui/app_qt.py`(start_auto), `tools/simulate_pipeline.py`(8·가짜 로그인 block_once·시도 횟수), `tools/pin_run_plan.py`(P11 삭제). 정책 문구 CLAUDE.md·DESIGN·FEATURE_INVENTORY.
- 상태: ACTIVE

### D-030 [RANK_NO_HALT_VID_REQUIRED] ③ 순위 — 쿨다운·당일 중단 폐지·차단 시 프록시 풀 무제한 회전·VID 없음=오류 (2026-10-10, R10)
- 결정: ③ 반자동 순위에서 차단 판정(연속 미로딩 `RANK_SEMI_AUTO_MAX_MISS` 또는 차단 페이지) 시 **30분 쿨다운·쿨다운 4회 초과 당일 중단을 하지 않는다**. 프록시 ON 이면 **새 egress 로 막힌 키워드부터 다시**(`drive_rank` — 회전 횟수 제한 없음·풀 한 바퀴 뒤엔 차단 이력 IP 도 재사용·끝=남은 키워드 없음·중지 요청·프록시 설정 오류), 프록시 OFF/회전 불가면 **쉬지 않고 다음 키워드**(막힌 칸 공란 → 다음 실행이 채움). 매칭은 **VID 정확 매칭만** — VID 없는 상품은 ❌오류로 기록하고 검색하지 않음(상품명 부분일치 폴백 삭제). 종료 요약 = 측정·차단감지·IP 전환·VID 없음·검색간격. config `RANK_SEMI_COOLDOWN_SEC/MAX`·`RANK_PROXY_ROTATE_MAX`·`RANK_PROXY_LAUNCH_MAX_ATTEMPTS` 삭제.
- 근거: 소유자 지시(2026-10-10 "VID 가 없으면 오류임 — 모든 상품은 VID 가 있음", "30분 쉬고 다시·그날 멈춤 = 적용하지 말 것") + 선택 답("프록시 풀을 돌려가며 계속 재시도"). 핀 K·L 을 새 기대값으로 다시 씀·핀 R 신설(실패→통과), test_proxy_patch 회전 2종 갱신(11 PASS), 게이트 16종·복잡도 0.
- 버린 대안: (a) 쿨다운 유지(소유자 지시와 다름) (b) 프록시 없을 때 무한 재시도(같은 IP 로 같은 키워드 반복 = 차단만 연장) (c) VID 없으면 상품명 폴백 유지(다른 상품을 내 상품으로 오인 가능·소유자 판단 '소스 오류').
- 위험(소유자 감수): 모든 egress 가 막혀 있으면 ③이 끝나지 않고 계속 돈다(다음 날 18:00 시작 정리가 끝냄). 차단 IP 재사용으로 그 IP 평판이 더 나빠질 수 있다.
- 영향 범위: `pipeline_ranks.py`(drive_rank·_run_on_egress(skip_blocked)·_rank_matcher·_SemiState·_semi_prep_product·_semi_on_miss·요약), `config.py`, `tools/pin_login_ranks.py`(J·K·L·R), `tools/test_proxy_patch.py`. 문서 CLAUDE.md·DESIGN.
- 상태: ACTIVE (부분 SUPERSEDED by D-053 — '새 egress 로 막힌 키워드부터 다시' → 다음 키워드부터·막힌 키워드는 다음 바퀴·진전 없는 바퀴는 남은 칸 ❌ 로 마침 · D-057 — '풀 한 바퀴 뒤엔 차단 이력 IP 도 재사용' → 이번 실행에 막힌 (주소, IP)는 건너뜀·쓸 IP 없으면 5분 대기 · D-090 — 끝 조건 추가: 성공 없이 IP 불량 15번 연속이면 ③ 마침)

### D-031 [STATS_AS_IS_SETTLE_RETRY_PUBLIC_PROXY] 판매지표 조회값 그대로·정산 연속 실패=다음 바퀴·앱 사용 중 대기·공개 검색 전부 프록시 (2026-10-10, R10)
- 결정: (1) 판매량·방문자·노출량은 **합산하지 않고 조회값 그대로** — 블록 VID 중 판매분석에 잡힌 첫 VID 의 값(`_fill_product_metrics`; 지금은 블록당 VID 1개라 대부분 그 값). (2) 정산 자동 수집에서 연속 2계정 실패/차단이면 **종료하지 않고 이번 바퀴만 멈춘 뒤 잠시 뒤 다음 바퀴**(`settlement_watch.plan_after_pass` stopped→'later'·회차 끝 17:55 까지) — **프록시는 쓰지 않음**(소유자 선택 '정책 유지' — 🔒 로그인·판매수집 프록시 금지, 2차인증 위치 기반). (3) 앱이 그 계정 Chrome 을 쓰는 중이면 **건너뛰지 않고 끝날 때까지 기다렸다가 이어서**(`_profile_busy(until=회차 끝)`·직접 실행은 기존 60초). (4) 비로그인 쿠팡 공개 검색은 **전부** 노출순위 프록시 적용 — ② 쿠팡 자동완성(`select_keywords_stage`)·키워드 추천 탭·순위 조회 탭(`proxy_pool.public_search_proxy` = config.json 적용 + ③과 같은 선택). 프록시 오류면 직접연결로 우회하지 않고 ②는 자동완성 후보만 건너뜀·탭은 오류 안내.
- 근거: 소유자 지시(2026-10-10 "판매량·방문자를 합계하면 안 되고 조회된 값 그대로", "앱이 그 계정 Chrome 을 쓰고 있으면 대기하다가 앱이 그 계정을 종료하면 다시 시작", "② 자동완성·키워드 탭·순위 조회 탭 프록시 적용") + 선택 답(정산 프록시: "정책 유지·프록시 안 씀"). 테스트: simulate 21(합계 14→7)·22(프록시 전달·오류 시 자동완성만 건너뜀)·정산 P12 정정('stop'→'later')·P28 신설(사용 중 대기) — 전부 실패→통과. 게이트 16종·복잡도 0·UI import.
- 버린 대안: (a) 정산 로그인에 프록시(2차인증·계정 잠금 위험 — 소유자 미선택) (b) 앱 사용 중이면 건너뜀(누락) (c) 여러 VID 값 합산 유지(소유자 지시와 다름).
- 영향 범위: `pipeline_process.py`, `settlement_watch.py`, `tools/settlement_download.py`(_profile_busy·session·_run_accounts), `proxy_pool.py`(public_search_proxy), `pipeline.py`(select_keywords_stage), `ui/app_qt.py`(do_recommend·do_rank), 테스트 simulate 21·22·verify_settlement_runtime P12·P28. CLAUDE.md 프록시 범위.
- 상태: ACTIVE

### D-032 [RESUME_SAME_COLUMN_ONLY] 이어서 하기 = 오늘 시작 + 같은 날짜 칸의 진행분만 (2026-10-10, R10)
- 결정: `plan_run_mode` 는 오늘 시작한 진행분이라도 **날짜 칸(date_label)이 이번 실행 칸과 다르면 이어받지 않는다** — 날짜 지정뿐 아니라 '당일' 전체실행·18:00 무인(`start_auto`)도 공통. 이 경우 마스터에 이번 칸을 새로 추가해 수집한다(carry). 재부팅 복구(`--resume`)는 끊긴 그 실행을 복구하는 것이라 진행분 칸 그대로(변경 없음).
- 근거: 운용 PC 로그·파일 실측(output (17).zip, 2026-10-10): `_진행중.json` = started_at 2026-10-10 01:05·date_label 2026-10-09·완료 25(하성진 미완료). 01:04 전체실행('오늘 것만 다시', 칸 10.09)의 ③이 206건 측정·마스터(06:54)에는 10.09 순위 206개 정상 — 그런데 결과시트는 10.09 순위 0개·10.10 칸 없음 → 같은 날 다음 실행(18:00 무인 추정 — 그 로그는 zip 에 없음)이 이 진행분(③ 이전 01:57 상태)을 '오늘 진행분'으로 이어받아 (a) 마스터·결과시트를 덮어 206개 소멸(D-028 경로·이미 수정) (b) 칸 이름 10.09 를 그대로 써 10.10 수집 자체가 안 됨(이번 수정). 핀 P8 에 '당일 실행 ≠ 진행분 칸 → 오늘 칸 새로' 추가(실패→통과)·P4 는 칸이 다른 진행분을 이어받는 것을 기대값으로 고정하고 있어 같은 칸 기준으로 정정. 게이트 16종.
- 함께 확인(로그): 09.29(16건)·10.03(0건)·10.06(22건) 순위가 적은 날 = 옛 '쿨다운 4회 후 당일 중단'(D-030 에서 폐지). 10-09 18:00 실행 로그는 ③ 2건 기록 뒤 20:33:00 에 종료 메시지 없이 끊김(원인 미확인 — 앱 창 닫힘·프로세스 종료 추정, Windows 이벤트 로그 필요). 운용 PC 는 예전 빌드(로그 문구 '블록명은 등록상품명 고정'·'30분 쿨다운 후 1회 재개').
- 버린 대안: (a) 진행분 칸을 계속 따름(오늘 칸 수집 누락) (b) 칸이 다르면 진행 파일 삭제(그 지정 실행의 미완료 계정 정보 손실 — 다시 그 날짜를 지정하면 이어받을 수 있게 남김).
- 영향 범위: `pipeline.py`(plan_run_mode), `tools/pin_run_plan.py`(P4·P8). CLAUDE.md 운영 정책 한 줄.
- 상태: ACTIVE

### D-033 [KW_TAB_FIX] 키워드 추천 탭 — 경쟁 조회는 검색어로(F1)·[저장]은 결과파일 블록 추가+결과시트 반영(F2) (2026-10-11, R10)
- 결정: (F1) `kw_metrics.page1_competition` 은 `_load_results` 에 **검색어**를 넘긴다(예전엔 검색 URL 문자열 전체를 넘겨, 2026-09-13 '검색창 타이핑' 전환 뒤로 URL 글자를 검색해 경쟁 지표·추천 점수가 틀렸음). (F2) 키워드 탭 [선택 키워드 저장]은 `manual_keywords.apply_manual_keywords` 로 **결과파일의 그 상품 블록에 키워드 추가**(기존 유지·상한 `KW_MAX_TRACK`·이미 있는 키워드 건너뜀) 후 저장·**결과 구글시트 반영**(시트가 키워드 기준 — 안 하면 다음 ① 역머지가 지움). 대장명→블록은 ①이 남긴 `_매칭고정.json`(대장 줄→VID)으로 찾고 다중옵션이면 키워드 칸 있는 대표 블록. 매칭 기록·결과파일·블록이 없으면 저장하지 않고 이유를 팝업. 쓰기만 하던 `keyword_store`(data/keywords.json) 삭제.
- 근거: 소유자 지시(2026-10-11 "F1, F2도 수정해줘"). 재현: F1 테스트가 '캠핑 타프' 대신 `https://www.coupang.com/np/search?q=…` 로 검색함을 확인(실패→수정 후 통과)·F2 simulate 23(저장 시 블록 키워드 추가·결과시트 반영·매칭 없는 상품 거부) 신설 통과. 게이트 16종·복잡도 0·UI import. UI 는 `run_bg(btn=저장 버튼, exclusive, pipelinelock)`(버튼 없이 exclusive 면 실행 중 표시가 안 풀리는 문제 회피).
- 버린 대안: (a) keyword_store 를 ②에서 읽기(파일·결과시트·마스터 3곳에 키워드 기준이 생김) (b) 저장 시 기존 키워드 교체(순위 이력 삭제 위험 — 추가만, 빼려면 결과시트에서 지움).
- 영향 범위: `kw_metrics.py`, `manual_keywords.py`(신규), `keyword_store.py`(삭제), `ui/app_qt.py`(_kw_tab·save_keywords), 테스트 verify_offline(F1)·simulate 23. 문서 FEATURE_INVENTORY·PARALLEL_DEV.
- 상태: ACTIVE

### D-034 [TEXT_TRUTH_F3467] 안내 문구·설명을 실제 동작에 맞춤 — 키워드 상한·프록시 기본값·③ 안내·낡은 주석 (2026-10-11, R10)
- 결정: (F3) '새 키워드 발굴 추가' 체크박스·툴팁의 상한·하루 개수를 **config 실제 값**(`KW_MAX_TRACK`=10·`KW_ADD_PER_DAY`=2)으로 표시(고정 문구 '7개' 폐지)·CLAUDE.md 도 10. (F4) 프록시 기본값 설명을 실제(config.json `proxy/enabled` 키 없으면 ON — 소유자 2026-10-01 '2번'·설정 탭과 같은 해석)에 맞춤: config 모듈 값 False 는 '적용 전 값'임을 명시, ON 로그에 '(설정 없음 → 기본 ON)' 표시, **ON 인데 쓸 프록시가 없으면 ❌ 로그**(그 검색 건너뜀·칸 공란·proxies.txt 또는 설정 탭에서 끄기 안내 — `proxy_pool._SKIP_MSG`). 동작(키 없으면 ON·fail-closed)은 바꾸지 않음. (F6) ③ 버튼 툴팁·시작 로그·docstring 을 '앱이 자동 타이핑·Enter'로(예전 '직접 검색하세요'). (F7) `app_qt.main` 의 '옛 정산 예약작업 제거' 주석 삭제(그 코드는 B6·D-024 에서 삭제됨).
- 근거: 소유자 지시(2026-10-11 "F3, F4, F6, F7도 수정해줘"). F3 값 출처 = 2026-09-20 커밋 69e7561('상한 10')·설계서 DESIGN/KEYWORD_SELECTION=10. F4 = 프록시 ON·프록시 없음 상태에서 실행해 ❌ 문구·'(설정 없음 → 기본 ON)' 확인. 게이트 16종·test_proxy_patch 11·복잡도 0·UI import.
- 버린 대안: (a) F3 상한을 7 로 되돌림(09-20 결정과 다름) (b) F4 기본값을 OFF 로 변경(소유자 10-01 결정과 다름·운용 PC 순위가 직접 IP 로 나감).
- 영향 범위: `ui/app_qt.py`, `config.py`(주석·ON 로그), `proxy_pool.py`(❌ 문구), CLAUDE.md.
- 상태: ACTIVE

### D-035 [R0_HQ_SPLIT] 본부 앱을 별도 저장소(HQ)로 분리 — R0 = 앱·정산 전용 독립 세션 (2026-10-11, R10)
- 결정: 메인 화면(샵마인·쿠팡 윙형)·위탁계정 관리·위탁상품 관리·나↔계정 정산·문의/CS·채권자 상환은 **별도 저장소 `D:\commerce-hq`(HQ)** 에서 도메인 세션 그룹(D0 홈·통제 · D1 위탁계정 · D2 위탁상품 · D3 계정 정산 · D4 문의/CS · D5 채권자 🔒)으로 만든다. 이 저장소(R0)는 **쿠팡 분석 앱 + 정산 다운로드만** 하는 독립 세션이다(HQ 통제 밖). 둘의 관계: (1) HQ 는 R0 데이터를 읽는다(HQ `docs/R0_DATA_CONTRACT.md` — 결과시트·관리대장·원장·재고현황·통계 마스터·실행단계·run_log·정산 파일) → **R0 는 그 형식을 바꿀 때 HQ 에 알리고 양쪽 DECISIONS 에 기록** (2) HQ 도 쿠팡에 직접 접속(소유자 선택) → HQ `docs/COUPANG_ACCESS.md` 공동 규약: **PC 공유 잠금**(`%LOCALAPPDATA%\coupang-shared\locks\` — 계정·로그인 간격 45~120초·공개 검색)·R0 계정 프로필 공유·R0 가 이미 모으는 데이터는 HQ 가 재수집 안 함 (3) R0 에 배포 안 된 채 남은 통합앱 자산(셸·보라 테마·공용 위젯·로컬 시트·계약/업무일지/CS/채권자 저장 모듈·패널·오프라인 검증 4종)은 HQ 로 이전 → **HQ D0 가 이전 완료를 알리면 R0 에서 물리 삭제**.
- 근거: 소유자 지시(2026-10-11 "별도의 독립된 신규 프로젝트(도메인세션 그룹)를 만들자 … 현재 세션은 다른 세션과 독립적으로 앱과 정산 다운로드 기능만") + 선택 답(폴더 `D:\commerce-hq`·HQ 도 쿠팡 직접 접속·자산 이전 후 R0 삭제·CS·채권자 포함). HQ 저장소 첫 커밋 02141c7(설계 문서·HQ D-001~D-004).
- 버린 대안: (a) R0 저장소 안에서 세션만 나눔(STATE·DECISIONS·공유 파일 충돌) (b) HQ 는 R0 데이터만 읽기(Claude 추천 — 소유자 미선택).
- 영향 범위: R0 — `CLAUDE.md`(분리 안내)·`STATE.md`(삭제·공유 잠금 대기). 공유 잠금은 **HQ 와 같은 규칙으로 동시에** R0 에 구현해야 함(HQ D0 요청 시 R0 세션이 `browser`/`pipeline_sales`/`settlement_download` 에 적용 — 그 전엔 HQ 쿠팡 접속 금지).
- 상태: ACTIVE (부분 SUPERSEDED by D-144 — R0 형식 변경 시 HQ 알림·양쪽 DECISIONS 기록 의무)

### D-036 [R0_TRANSITION_ROLE] HQ 가 R0 기능 전부를 이관해 새로 구축 — 이관 기간 R0 = 운영 유지·치명 수정만·전환 후 은퇴 (2026-10-11, R10)
- 결정: HQ(`D:\commerce-hq`)가 **R0 기능 전부**(①②③·통계 원장·결과시트·18:00 무인·실행 모드·복구)와 **정산 다운로드·계정 정산**을 '필요한 기능만 이관해 새롭게 구축'한다(HQ D-005 — 코드+테스트를 기능 단위로 옮겨 정리·화면/메뉴는 새로·제외 = 판매분석 엑셀 다운로드 대체 경로). 이관 기간 **R0 는 매일 운영을 유지하고 치명 오류 수정만** 한다(새 기능 추가 안 함 — 새 기능 요청은 HQ 로 안내). R0 에서 고친 것은 R0 `STATE.md` '포팅 필요'에 남겨 HQ D0 가 반영. HQ 의 이관 검증은 R0 가 저장하는 원본 응답(`output\_raw\*.json.gz`) **오프라인 재생 비교(그림자 검증)** 를 쓰므로 **`_raw` 저장 형식과 보관을 유지**한다. HQ 에서 ①②③·정산·무인이 모두 완료되면 18:00 예약작업을 HQ 로 바꾸고 **R0 은퇴**(저장소 보존).
- 근거: 소유자 지시(2026-10-11 "신규 도메인에는 현재 앱 기능과 정산 기능도 추가 — 불필요한 기능은 제외하고 필요한 기능만 이관해서 새롭게 구축") + 선택 답. HQ 커밋 d6e6efa(이관표 `docs/MIGRATION.md`·세션 D0~D7·HQ D-005).
- 버린 대안: (a) R0 도 계속 기능 추가(두 곳 동시 개발 = 이관 대상이 계속 움직임) (b) 전환 전 R0 즉시 중단(운영 공백).
- 영향 범위: R0 `CLAUDE.md`(분리 안내)·`STATE.md`(포팅 필요 목록) · D-035 의 '자산 이전 후 삭제'·'공유 잠금'은 그대로 유효.
- 상태: ACTIVE (부분 SUPERSEDED by D-144 — 이관 기간 치명 오류 수정만·새 기능 금지)

### D-037 [HQ_ASSET_REMOVED] HQ 로 옮긴 통합앱 자산 18개를 R0 에서 물리 삭제 (2026-10-11, R10)
- 결정: HQ D0 가 이전을 마친 통합앱 자산을 R0 에서 물리 삭제한다 — `ui/app_integrated.py`·`theme_qt.py`·`panel_kit.py`·`local_sheet_client.py`·`contract/worklog/cs/creditor_panel_qt.py` · `src/coupang_analytics/contract_store.py`·`worklog_store.py`·`cs_model.py`·`cs_store.py`·`cs_gsheet.py`·`creditor_store.py` · `tools/verify_{contract,worklog,cs,creditor}_offline.py` + `run_checks.CHECKS` 의 그 4줄. 유지 = `registry_lock.py`·`registry_model.py`·`apppaths.py`(R0 운영이 씀).
- 근거: 소유자 지시(2026-10-11 "모두 이관했으면 삭제해") · HQ 커밋 2fa6717(D-008)·HQ STATE '다음 작업 1'. 실측: 18개 모두 HQ 짝 파일 존재, import·`sys.path` 줄 제외 본문 비교 = 15개 차이 0줄, `app_integrated`↔`shell.py`·`theme_qt`↔`theme.py` 는 파일 이름을 가리키는 주석 3줄만 다름. R0 운영 코드(파이프라인·app_qt·spec) 참조 0건(grep — 자산끼리 참조와 게이트 4줄뿐).
- 버린 대안: 두 곳에 사본 유지(어긋남 — D-004 가 이미 버림).
- 영향 범위: R0 게이트 구성(원장 4종 제거)·`CLAUDE.md`·`designs/FEATURE_INVENTORY.md`·`docs/PARALLEL_DEV.md`·`STATE.md`. 운영 앱 동작 변화 없음.
- 상태: ACTIVE

### D-038 [CLEANUP_REUSABLE_PKG] `reusable_coupang/` 물리 삭제 · 옛 R0 도메인 작업 폴더 13개 정리 (2026-10-11, R10)
- 결정: (1) `reusable_coupang/`(git 8파일 — 예전에 뽑은 로그인·순위 독립 패키지)을 물리 삭제한다. 다른 쇼핑몰에서 재사용할 로그인·프록시·순위 모듈은 HQ 공통 엔진(`hq/web`·HQ D-007)으로 R0 최신 코드에서 새로 나눠 만든다. (2) 옛 R0 도메인 작업 폴더(worktree) 13개와 그 브랜치(`domain/d1-analysis`~`d9-stats`·`worktree-*` 4개)를 정리한다. `domain/h-ui` 는 **master 미병합 커밋 54172b7(통합앱 홈 변동 추이·공용 위젯 732줄)** 이 있어 HQ D0 가 가져갈 때까지 유지.
- 근거: 소유자 지시(2026-10-11 "둘 다 삭제해"). 실측: `reusable_coupang` 을 import·참조하는 코드 0건(문서 3곳만) · HQ `docs/COUPANG_ACCESS.md` §6 이 이미 '뒤처진 추출본이라 쓰지 않음'으로 정함. 13개 작업 폴더 = master 대비 미병합 커밋 0·미커밋 변경 0(`git rev-list --count master..<branch>`·`git status`).
- 버린 대안: 남겨 둠(뒤처진 사본이 HQ 이관 때 잘못 참조될 위험).
- 영향 범위: `designs/FEATURE_INVENTORY.md`·`STATE.md` · 운영 앱 동작 변화 없음.
- 상태: ACTIVE

### D-039 [SETTLE_DEDUP_ROWS] 정산 집계 '같은 줄 1회' = 여러 파일에 겹친 줄만 — 한 파일 안 반복 줄은 진짜 거래로 전부 반영 (2026-10-12, R10)
- 결정: 정산 집계의 중복 제거를 `settlement_stats._order_rows` 한 곳에서 한다. 같은 줄(계정·주문·옵션·유형·날짜·금액·수량)이 **여러 파일에** 있으면 한 번만(정확히는 '한 파일에 가장 많이 나온 횟수까지') 반영하고, **한 파일 안에서 반복된 줄은 전부** 반영한다. 정산집계(`aggregate`)와 검증 월합(`settlement_verify.month_sums`)이 같은 규칙을 쓴다. 기존 규칙(같은 이름 파일 1회·윙 최종액은 주정산 없는 주만)은 그대로.
- 근거: 소유자 지시(2026-10-12 "중복이 있을 수 있음 — 분석해서 1번만 반영"). 운용 PC 실데이터(output (18).zip — 정산 파일 966·비용 리포트 1,351) 분석: 같은 기간 파일 중복 0·비용 리포트 중복 0·지급내역 중복 0. 옛 코드는 `aggregate` 에서 줄 키가 같으면 무조건 1회만 셌는데, 지운 94줄은 모두 **한 파일 안의 '주문 정산취소 수량 -1' 개당 줄**(ski1121 한 주문 40줄 등)이었고, 그 9개 파일 모두 **줄 전부 합계만 쿠팡 정산현황(판매액+환불−수수료)과 원 단위 일치**(중복 제거 합계는 9/9 불일치 · 같은 식으로 반복 줄 없는 로켓그로스 파일 769/769 일치). 즉 옛 코드는 진짜 취소를 지워 **gyi0101 +21,643·ski1121 +760,284·Difpick +95,323(합 +877,250원) 부풀려 집계**. 재현 테스트 `verify_settlement_offline` P10(옛 코드 실패 `{'A': 0}` → 수정 후 통과) · 실데이터 재집계: 3계정만 위 금액만큼 감소·나머지 26계정 변화 0.
- 버린 대안: (a) 줄 키에 행 번호를 넣어 중복 제거 사실상 끄기(여러 파일에 겹친 진짜 중복까지 두 번 셈) (b) 그대로 두기(정산금액 과다 = 오류).
- 영향 범위: `settlement_stats.py`(_order_rows·aggregate) · `tools/verify_settlement_offline.py` P10 · 정산집계 '경고' 시트 문구('여러 파일에 겹친 같은 줄'은 실제로 겹칠 때만). **HQ 포팅 필요**(MIGRATION #23).
- 상태: ACTIVE (부분 SUPERSEDED by D-074 — 함께 적은 기존 규칙 '윙 최종액은 주정산 없는 주만' → 같은 정산예정일이고 구매확정일이 주정산 파일 기간 안인 줄만 뺌·여러 파일 겹친 줄 1회 규칙 자체는 그대로)

### D-040 [VIDLESS_UNCOLLECTED] 미수집(로그인 실패) 계정도 VID 없는 잔재 블록 정리 — 메타 있음·VID 없음·대장에 없는 블록만 (2026-10-12, R12)
- 결정: ① 끝 `_reconcile_ledger_accounts` 에서 미수집 계정마다 `pipeline_process.purge_uncollected_vidless` 로, **숨김 메타 행 있음(등록명 기록) + VID 없음 + 대장 줄(ledger_products)에 블록명·등록명 둘 다 없음** 인 블록을 삭제한다(다계정ID 스코핑). 메타 행 없는 블록(구글시트 복원 마스터)은 VID 를 알 수 없어 미접촉. 대장에 있는 VID 없는 블록(하성진 '토탈사이언스')은 수집 성공 시 D-008 경로가 처리.
- 근거: 결과시트 점검(10-12) — 하성진(lslfgh·매번 로그인 실패) 시트에 벅스 상품명 블록 3개(보냉백 BG001·YG0209(판매부진)·변신큐브 A003)·VID 없음·계정ID 미태깅. D-008 정리는 수집 성공 계정(`_finish_account`)만이라 계속 잔존. 재현 verify_offline [B1] 실패→통과. 운용 PC 마스터(10-11 23:38)에 전 계정 미수집 가정 최악 실행 = 그 3개만 삭제.
- 버린 대안: (a) VID 없는 블록 무조건 삭제(복원 마스터 대량 오삭제 — D-008 이 버림) (b) 수집될 때까지 방치(로그인 실패 계정은 영원히 남음).
- 영향 범위: `pipeline.py`(_reconcile_ledger_accounts)·`pipeline_process.py`(purge_uncollected_vidless)·`tools/verify_offline.py` [B1]. **HQ 포팅 필요**.
- 상태: ACTIVE

### D-041 [TWIN_VID_PURGE] 추적 VID 와 같은 리스팅·같은 옵션의 다른 배송방식 VID 블록(추적 안 됨) = 이력과 함께 삭제 (2026-10-12, R12)
- 결정: ① 계정 처리 시작(`_process_account`, 업번들 정리 옆)에 `_purge_twin_blocks` — 블록 VID 가 **전부** 이번 추적 VID 와 같은 (리스팅ID·옵션명)의 다른 VID(판매자배송↔로켓그로스)이고 추적 VID 를 하나도 갖지 않으면 삭제(다계정ID 스코핑). 판정 자료 = 상품조회 `live_all_vids` 를 {vid: (vendorInventoryId, itemName)} 사전으로 확장(`in`·빈값 판정은 집합과 동일 — 기존 사용처 무변경). 상품조회 실패·옛 형식(집합)이면 정리 안 함. 2026-09-24 정책('NORMAL twin 은 보존 — 완전 제거는 registrationType 배선이 필요한 별도 후속')의 그 후속.
- 근거: 소유자 선택(2026-10-12 '자동 정리 규칙 추가'). 실측 (DW)커머스 원문(10-11): 'PHARMIZEN…기능성 영양제' 블록 = VID 96075356361(NORMAL)·10.03 이후 공란 / 추적 = 같은 리스팅 16389437656·옵션 '1개 60정'의 RFM 96075356358 → 옛 블록이 노출명을 차지해 이름 현행화 실패('이미 다른 상품 블록 이름') + 대장명과 같아 매 실행 판매중지 표기·해제 반복 + ③ 4회 검색 낭비. 운용 PC 원문 24계정 적용 = 이 1블록만 삭제. 재현 verify_offline [B3] 실패→통과.
- 버린 대안: 옛 블록 유지·판매중지 고정(노출명 현행화 불가 — 소유자 미선택).
- 영향 범위: `pipeline_process.py`(_purge_twin_blocks·_sweep_dead_duplicates 주석)·`pipeline_sales.py`(live_all_vids 값)·`tools/verify_offline.py` [B3]. **HQ 포팅 필요**.
- 상태: ACTIVE

### D-042 [LEDGER_LABEL_ONELINE] 대장 사업자명·대표자명 = 한 줄 이름 · 역기록(그로스 재고·회사재고)도 파싱과 같은 계정 라벨 (2026-10-12, R12)
- 결정: (1) 대장 사업자명·대표자명 셀은 줄바꿈·연속 공백을 공백 하나로(`input_list._one_line`) — 계정 라벨=결과 시트 이름. (2) 그로스 재고 역기록(`_growth_col_values`)·회사재고(`company_stock._ledger_rows`)는 계정 줄의 사업자를 **파싱과 같은 라벨**(`input_list.account_labels` = 사업자명 → 대표자명 → 계정ID)로 정한다(예전 = 계정ID·사업자명 둘 다 있는 줄에서만 바꿔 사업자명 빈 계정은 바로 위 계정 이름).
- 근거: 결과시트 점검(10-12) — 시트명 '봄날의햇살⏎주식회사'(대장 셀 줄바꿈 그대로) · 회사재고 로그 '주식회사 브릿지웍스 / 전동눈썹정리기 HS0300'(실제 최문석)·'비엔케이미디어 / 토탈사이언스'(실제 하성진). 확인: 회사재고는 상품명 매칭이라 **표시만** 틀림, 그러나 그로스 재고 역기록은 최문석(워크북 재고 69·0)을 '주식회사 브릿지웍스' 재고에서 찾아 **역기록 0건**(10-11 로그 [재고매칭]에 최문석 상품 없음). 재현 verify_offline [B4·3] 실패→통과. 실대장+운용 마스터: 봄날 → '봄날의햇살 주식회사' 일원화(계정ID 동일·상품 2개 이력 이관).
- 남은 것(별도·소유자 결정 대기): 최문석 상품은 라벨이 맞아도 그로스 역기록 **이름 유사도** 매칭에서 탈락(대장 'HS0300' vs 쿠팡 'HS0030' 오타·'자동손세정기 HB153(젤타입…)' 재현율 미달) → ①의 매칭고정(대장 줄→VID)으로 찾는 방식은 STATE 미해결.
- 버린 대안: 줄바꿈 시트명 유지 + 대장만 사람이 고침(다음 줄바꿈 입력에 재발).
- 영향 범위: `input_list.py`·`company_stock.py`·`tools/verify_offline.py` [B4·3]. 첫 실행에 봄날의햇살 결과 시트·계정목록 이름이 '봄날의햇살 주식회사'로 바뀜(`_consolidate_renamed_accounts` 이력 보존) → **HQ 알림**(R0_DATA_CONTRACT 결과시트 시트명)·**HQ 포팅 필요**.
- 상태: ACTIVE

### D-043 [REP_SWAP_MOVE_KW] 쿠팡 옵션 순서가 바뀌어 대표 옵션이 바뀌면 옛 대표의 키워드·검색량·순위 이력을 새 대표로 이동 (2026-10-12, R12)
- 결정: ① 상품 처리 끝(`_carry_rep_keywords`)에서 대표(names[0])에 키워드가 없고 다른 옵션 블록에 있으면 `OutputWorkbook.move_keywords` 로 키워드·검색량·날짜별 순위를 새 대표로 옮기고 옛 블록의 키워드 칸(소헤더·순위행)을 지운다 → 옛 블록 = 판매정보만(③ 중복 검색 없음·계정목록 1줄).
- 근거: 소유자 선택(2026-10-12 '새 대표로 키워드 복사'). 실측 최문석 '디프 스마트 호신용…팔찌 경보기': 같은 등록명 리스팅 2개(16398349751·16382079839)가 옵션 '1개'·'1개 #2'로 묶임 → 10-10 대표가 '(1개 #2)'→'(1개)'로 바뀌어 새 대표 키워드 0개(② AI 선정 빈 결과·자동완성 0)·옛 대표만 ③ 검색. 이력 이동은 소유자 안('순위 이력은 옛 블록에 남음')에서 ③ 중복 검색을 막으려 키워드 칸까지 옮김(이력 손실 없음 — 운용 마스터 적용 결과 이동 전후 동일). 재현 simulate 24 실패→통과.
- 버린 대안: (a) 키워드 있는 블록을 대표로 고정(소유자 미선택) (b) 키워드만 복사·옛 블록 유지(③ 같은 키워드 2회 검색).
- 영향 범위: `workbook_lifecycle.py`(move_keywords·_drop_keyword_section)·`pipeline_process.py`(_carry_rep_keywords)·`tools/simulate_pipeline.py` 24. **HQ 포팅 필요**.
- 상태: ACTIVE (부분 SUPERSEDED by D-049 — 적용 조건 '대표에 키워드 없음', 대표에 키워드가 있어도 합침)

### D-044 [KW_BLANK_KEEP] 키워드 4칸 중 빈칸 = 유지(설계) · 18:00 무인은 발굴 추가 없음 (2026-10-12, R12)
- 결정: 첫 선정 때 키워드가 4개 미만이면 남는 칸은 빈 순위행으로 둔다(2026-09-15 '4행 유지·공란 OK'). 18:00 무인 실행은 '새 키워드 발굴 추가'(grow)를 쓰지 않는다(지금과 같음). 빈칸은 직원이 결과시트에 키워드를 적으면 다음 실행에 반영.
- 근거: 소유자 선택(2026-10-12 '지금대로'). 원인 확인: (DW) 원룸 공기청정기·효성 와사비·최문석 팔찌 #2·플랜잇 와사비 = 첫 선정 3개, 비엔케이 빨래줄 = 2개 · `start_auto` 가 grow 미전달(기본 False).
- 버린 대안: (a) 4개 미만 상품만 매일 보충 (b) 무인 발굴 추가 켜기(③ 검색·IP 소모 증가).
- 영향 범위: 코드 변경 없음.
- 상태: ACTIVE

### D-045 [SHARED_EXPOSED_LABEL] 대장 여러 줄이 같은 노출명(한 상품의 다른 옵션)을 나누면 '노출명 (옵션)' (2026-10-12, R12)
- 결정: 한 계정에서 대장 여러 줄의 추적 상품이 같은 노출명을 가지면(`pipeline_process._shared_exposed`) 다중옵션 상품과 같게 블록 이름 = '노출명 (옵션라벨)'. ③ 검색 노출명 현행화(`product_naming.rename_to_exposed`)도 같은 제목의 다른 라벨 블록이 있으면 라벨 유지(`_shares_title` — 없으면 ①·③이 이름을 번갈아 바꿈). 같은 VID 블록 개명이라 이력 승계.
- 근거: 소유자 지시(2026-10-12 "다른 상품과 동일하게 처리 — 기본 + 옵션"). 실측 휴라엘 '신형타프 R008 (블랙 Free)'·'(베이지 Free)' = 리스팅 16337885026 의 두 옵션 → 블랙만 노출명·베이지는 '이미 다른 상품 블록 이름' 경고로 등록명 유지. 운용 매칭고정 24계정 중 해당 = 이 1건. 재현 verify_offline [타프] 실패→통과.
- 버린 대안: 지금대로(먼저 잡은 줄만 노출명·경고).
- 영향 범위: `pipeline_process.py`·`product_naming.py`·`tools/verify_offline.py`. 휴라엘 두 블록 이름이 바뀜(결과시트). **HQ 포팅 필요**.
- 상태: ACTIVE

### D-046 [LEDGER_FULL_TEXT_MATCH] 대장 상품명 칸 전체 문구(괄호 전부)로 ① 매칭 — 괄호 용도(옵션·노출명·메모)는 AI 판단 (2026-10-12, R12)
- 결정: 대장 상품명 칸의 **전체 문구**(여러 줄=한 줄로)를 `Product.ledger_text` 로 보존하고, ① 매칭의 상품명 동일 판정(`_line_texts`=첫 줄·첫 줄 본문·**칸 전체의 괄호 속 이름 전부**)·AI 질문·의미 추리기(임베딩)에 쓴다. AI 지시문에 '괄호가 두 개일 수 있음(옵션 + 노출명)·본문은 보통 내부 관리명·괄호마다 의미로 판단' 추가. 블록 기준·매칭고정 키·결과 이름은 지금처럼 **첫 줄**(2026-09-27 #C 중복 블록 방지 유지).
- 근거: 소유자 설명(2026-10-12 "'전동눈썹정리기 HS0300'=쿠팡 내부관리 상품명, 괄호 안=쿠팡 노출 상품명 · 괄호는 옵션 또는 노출명 두 용도·2개일 수도·AI 분석으로 판단"). 실대장 87줄 = 괄호 53줄(여러 줄 31·괄호 2개 3)·예외(PHARMIZEN 은 괄호 쪽이 쿠팡 등록명·'(대체요망)'=메모) → 규칙이 아니라 AI 판단. 원인: 파싱이 여러 줄 칸의 첫 줄만 남겨 둘째 줄 노출명이 AI·상품명 동일 판정에 전달 안 됨. 재현 verify_offline [괄호] 실패→통과·[36]·[C] 유지. 매칭고정된 기존 줄은 AI 재호출이 없어 결과 불변 — 새 줄·재매칭부터 적용.
- 버린 대안: (a) 괄호 용도를 규칙(길이·색상어)으로 판정(예외 다수) (b) 블록 기준도 전체 문구로(중복 블록 재발).
- 영향 범위: `input_list.py`(ledger_text)·`product_match_ai.py`(_full·_line_texts·build_request·임베딩·지시문)·`tools/verify_offline.py`. **HQ 포팅 필요**.
- 상태: ACTIVE

### D-047 [GROWTH_BY_AI_MATCH] 관리대장 그로스 재고 역기록 = ① AI 매칭 결과(대장 줄→VID)로 블록 재고 · 이름 유사도 삭제 (2026-10-12, R12)
- 결정: ①이 계정마다 매칭 결과 **전부**(고정 여부 무관·색상 필터 후 VID)를 `output/_매칭결과.json` {계정ID: {대장 첫 줄 키: [VID…]}} 에 저장(`match_anchor.save_match_result`·매칭고정과 별도). 역기록(`write_ledger_inventory`)은 대장 줄 → 그 VID 의 첫 VID 블록 → 최신 숫자 재고. 매칭 결과 없음(미매칭·미수집 계정 첫날)·재고 없음(개인상품)은 기존값 보존 + 결과 없는 상품 ⚠ 로그. 이름 유사도 매칭(`_best_inventory_match`·`_growth_idf`) 물리 삭제.
- 근거: 소유자 지시(2026-10-12 "AI 로 매칭이 안 되는데 파이썬 유사도에서 매칭이 될까? AI 로 유사도 포함 매칭"). 실측: 최문석 '전동눈썹정리기 HS0300'(내부관리명)↔워크북 'HS0030' 이름 유사도 탈락 → 역기록 0건. 매칭고정에는 AI 확신 low·규칙 대체가 빠져 결과 파일을 별도로 둠. 실데이터(운용 마스터+실대장, 쓰기 없음): 기록 34→61줄·값이 바뀌는 25줄은 모두 옛 방식이 매칭 못 해 옛 값·손 메모가 남던 줄(예 PHARMIZEN '현재: 0개(840개 반영대기중)'→767·최문석 69·0). 재현 verify_offline [역기록] 실패→통과.
- 미결(소유자 확인 대기): 대장 한 줄이 옵션 여러 개를 가리키면(에벤에셀 '기저귀가방 CL01' = 베이지 0·베이비 39) 지금은 대표(첫) 옵션 재고 — 합계 여부.
- 버린 대안: (a) 매칭 결과 없으면 이름 유사도로 보충(AI 가 못 맞춘 줄을 글자 유사로 = 오매칭 위험) (b) 매칭고정 파일만 사용(low·규칙 매칭 누락).
- 영향 범위: `match_anchor.py`·`pipeline_sales.py`(_save_match_result)·`input_list.py`(_growth_col_values·write_ledger_inventory)·`tools/verify_offline.py`. 새 파일 `output/_매칭결과.json` → **HQ 알림**(R0_DATA_CONTRACT)·**HQ 포팅 필요**. `workbook.inventory_by_biz` 는 R0 사용처가 없어졌으나 L1 공개 API 계약(핀)이라 유지.
- 상태: ACTIVE (부분 SUPERSEDED by D-048 — 옵션 여러 개 줄의 '첫 VID 블록', 옵션별 함께 표기)

### D-048 [GROWTH_PER_OPTION] 그로스 재고 역기록 — 대장 한 줄이 옵션 여러 개를 가리키면 옵션별로 함께 표기(합산 안 함) (2026-10-12, R12)
- 결정: D-047 미결의 답. ① 매칭 결과의 VID 가 **블록 하나**면 그 최신 숫자 재고(지금과 같음), **옵션 블록 여러 개**면 결과 시트 블록 순서대로 '라벨 값 / 라벨 값'(예 '핑크 S 0 / 그레이 S 미입고 / 블루 S 0'·재고행 없는 옵션 '-')을 대장 칸에 쓴다(`input_list._inventory_text`·`OutputWorkbook.inventory_cell`). 합산하지 않는다.
- 근거: 소유자 지시(2026-10-12 "결과 시트에 옵션별 상품에도 재고현황이 있어 옵션별로 모두 표시하면 합산할 필요 없음" → 선택 1번 '옵션별로 함께 쓰기'). 실측(운용 마스터): 다중옵션 22상품 모두 옵션 블록마다 재고현황 행 · 수량 묶음(1개·2개·3개)은 한 옵션만 숫자·나머지 '미입고' · 색상/사이즈(속싸개·CL01 베이지 0/베이비 39·CL02·허리보호대)는 옵션마다 다름. D-047 의 '첫 VID 블록' 은 첫 옵션이 미입고인 상품(웰빙곳간 알파CD '3개'=미입고·'1개'=331)에서 역기록이 멈추는 회귀였음 → 이 결정으로 해소. 재현 verify_offline [역기록] 실패→통과. 실데이터: 다중옵션 대장 줄 숫자 → 옵션별 문구로 바뀜(예 알부민 '1개 120정 418 / 2개 120정 미입고 / 3개 120정 미입고').
- 버린 대안: (a) 숫자 있는 첫 옵션 값 하나(색상별 재고 누락) (b) 다중옵션 줄 미기록(기존값 유지).
- 영향 범위: `input_list.py`·`workbook_meta.py`(inventory_cell — product_inventory 가 재사용)·`tools/verify_offline.py`. 관리대장 '그로스 재고' 칸에 숫자 대신 글자가 들어가는 줄이 생김(직원 수식이 있으면 확인 필요). **HQ 포팅 필요**.
- 상태: ACTIVE

### D-049 [REP_SWAP_MERGE_KW] 대표 아닌 옵션 블록에 남은 키워드 칸 = 새 대표로 합치고 삭제 (모든 다중옵션 상품 공통) (2026-10-12, R12)
- 결정: D-043 을 일반 규칙으로 넓힌다. ① 상품 처리 끝(`_carry_rep_keywords`)에서 대표(names[0]) 아닌 옵션 블록에 키워드 칸이 있으면 **새 대표에 키워드가 있어도** `move_keywords` 로 합친다 — 대표에 없는 키워드만 추가, 같은 키워드는 대표의 **빈 날짜 칸만** 옛 값으로 채움(같은 날 둘 다 있으면 대표 값 유지)·검색량 빈칸 보충 → 옛 블록 키워드 칸 삭제(판매정보만).
- 근거: 소유자 지시(2026-10-12 "발견한 계정·상품만이 아니라 유사 유형 모두 적용"). 운용 마스터 전수: 키워드 칸이 두 블록에 있는 상품 3건 — 최문석 팔찌(새 대표 0개·D-043 대상)·에벤에셀 CL01(옛 대표 4키워드 8일·새 대표 4키워드 2일)·고로켓 팜픽(옛 10일·새 2일) → ③ 같은 상품 2번 검색·계정목록 2줄. 적용 결과 3건 모두 대표 1블록(CL01 5키워드·팜픽 7키워드)·남은 중복 0·렌더 정상. 재현 verify_offline [C1+] 실패→통과·simulate 24 유지.
- 버린 대안: 새 대표가 키워드 0개일 때만(D-043 범위 — 2건 미해결).
- 영향 범위: `workbook_lifecycle.move_keywords`·`pipeline_process._carry_rep_keywords`·`tools/verify_offline.py`. **HQ 포팅 필요**.
- 상태: ACTIVE

### D-050 [INDEX_TITLE_COUNT] 계정목록 제목 '상품 N개' = 증분 동기화마다 갱신 (2026-10-12, R12)
- 결정: 결과 구글시트 `계정목록` 제목(A1)을 최초 생성뿐 아니라 **매 증분 동기화**에서도 현재 수(판매중지 제외)로 쓴다(`gsheet_index._title_request` 공통).
- 근거: 결과시트 점검(10-12) '상품 76개' ≠ 88줄 — 원인 = 제목은 `_full_build_requests`(최초 생성)에서만 써서 첫 생성 값 고정(운용 마스터로 다시 계산하면 84). 재현 verify_gsheet_offline [3b] 실패→통과.
- 영향 범위: `gsheet_index.py`·`tools/verify_gsheet_offline.py`.
- 상태: ACTIVE (부분 SUPERSEDED by D-135 — 제목 '상품 N개' 세는 범위: 판매중지 제외 → 판매중지·상품 없는 계정 줄 제외·증분 동기화마다 갱신은 그대로)

### D-051 [EXPOSED_NAME_WING_MODIFY] 노출명 출처에 윙 상품수정 화면 노출상품명 추가 — 판매 여부 무관 (2026-10-12, R12)
- 결정: D-015 출처 순서 = 당일 판매분석 → 최근 30일 판매분석 → **윙 상품수정 화면 `displayProductName`**(`/tenants/seller-web/vendor-inventory/modify?vendorInventoryId=` GET·읽기만·appData 에서 추출 `collector.fetch_display_names`) → 그래도 없으면 ❌ + ③ 검색 노출명. 상품조회의 vid→등록상품ID(`live_all_vids`)로 판매분석에 없는 추적 상품만, 등록상품당 GET 1회(약 170KB·3초). 실패 상품은 로그·다음 상품 진행.
- 근거: 소유자 지시(2026-10-12 "로그인해 상품조회하면 판매 여부와 관계없이 모든 상품 조회 가능 — 다시 적용·직접 접속 진단 허용"). 라이브 진단(반달컴퍼니 로그인은 소유자가 직접·Claude 는 읽기만): 상품조회 목록 열=‘등록상품명’·`vendor-inventory/search` productName=등록상품명·펼치기(옵션) API `items-with-vendorItems`·당일출고·속성보완 응답엔 상품 이름 없음(옵션명·노출상품ID만) → 상품수정 화면 appData 에 `sellerProductName`='허리보호대 LN112'·`displayProductName`='디프 허리 교정 보호대 헬스 벨트'(판매 1개·대장 괄호 노출명과 일치). 대상 = 10-11 로그 ❌ 21블록(웰빙곳간 16·스타냉동밀키트·DYM046·w200·허리보호대·BG002 — 모두 30일 판매 없음). 재현 verify_offline [노출명] 실패→통과·[38] 유지·`_fill_exposed_names` 분해(복잡도 경고 0).
- 버린 대안: (a) 대장 괄호 노출명 사용(담당자 입력·낡을 수 있음) (b) 공개 상품 페이지(비로그인 Akamai·프록시 정책).
- 영향 범위: `collector.py`(fetch_display_names·parse_display_name)·`pipeline_sales.py`(_match_to_ledger vinv_by_vid·_fill_exposed_names·_fill_from_roster·_fill_from_modify_page)·`tools/verify_offline.py`. **HQ 포팅 필요**.
- 상태: ACTIVE

### D-052 [SETTLE_MONTHLY_FAILED_COMMENT] 정산 — 로켓그로스 월정산 줄 건너뜀 · 완료 표시에 실패 계정 수 · 계정 파일 # 주석 줄 (2026-10-12, R12)
- 결정: (1) 로켓그로스 정산현황 `settlementCycle='MONTHLY'` 줄은 윙 'M'(D-010)과 같게 **그 줄만 건너뛰고** 처리기록 '확인 필요'(`_RG_UNSUPPORTED`·`unsupported_cycles` 가 윙·로켓그로스 공통) — 모르는 다른 주기는 그대로 중단. 월정산 파일 받기 기능은 별도 결정. (2) 한 바퀴 뒤 '완료' 판정 때 이번 실행에서 **실패로 끝난 계정**(실패·차단 뒤 정상 기록 없음·`RunLog.unresolved_failures`)이 있으면 문구 = '✅ 받을 수 있는 정산 파일 다운로드 완료 — 실패 N계정(단계별) 확인 필요', 상태 카드 = **'완료·실패 확인'**(앱 배지 주황 '받을 수 있는 것은 받음 — 실패 계정 확인 필요'), `_완료.json` 에 failed 수 저장(다음 '이미 끝남' 실행도 같은 표시). (3) 정산 계정 파일에서 `#` 으로 시작하는 줄은 주석(건너뜀).
- 근거: 소유자 선택(2026-10-12 정산 수정 1·2·3 전부). 실측 운용 PC 10-12 01:38~05:56 정산: 노바네스트 `SiteChangedError: 로켓그로스 모르는 정산주기: 'MONTHLY' (A01371646-2026-07-01-2026-07-31)` → 계정 실패(정상 18·대기 4) · 로그인 실패 10(사용 안 함 8계정·비번 바뀐 2계정)인데 '✅ 모든 정산 파일 다운로드 완료'·상태 '완료 · 이미 모두 받음'. 실제 처리기록 747줄 재생 = 실패로 끝난 계정 11(로그인 10·계정 1) 정확히 산출. 계정 파일 '#' 미지원 = '#id' 로그인 시도(STATE R11). 재현 verify_settlement_runtime P29 실패→통과·P12·P14·P27 유지.
- 버린 대안: (a) 월정산 줄 오류 유지(나머지 정산 파일까지 막힘) (b) 실패 계정 있으면 '미완료' 종료(받을 것은 다 받았는데 다음 회차까지 재시도만 반복·로그인 실패 반복은 잠금 위험).
- 영향 범위: `settlement_wing_api.py`·`settlement_accounts.py`·`settlement_runlog.py`·`settlement_watch.py`·`tools/settlement_download.py`·`ui/settlement_status_panel_qt.py`·`tools/verify_settlement_runtime_offline.py`. **HQ 포팅 필요**.
- 상태: ACTIVE (로켓그로스 월정산 줄 건너뜀 부분은 SUPERSEDED by D-075 — 월정산도 받음 · D-103 — (3) 계정 파일 '#' 주석 줄은 옛 계정 파일(settlement/account_source=file)일 때만·기본 계정 출처 = 원장)

### D-053 [RANK_PASSES_CONN_EVIDENCE] ③ 순위 — 막힌 키워드는 뒤로 미루고 바퀴 반복으로 빈 칸 0 까지 · 프록시 연결 장애 ≠ 차단 · 차단 증거 저장 · 빈 칸 남으면 '완료' 아님 (2026-10-13, R12)
- 결정: (1) 차단·미로딩된 키워드는 **이번 바퀴에서 뒤로 미루고 다음 키워드로**(프록시면 새 IP 도 다음 키워드부터). 한 바퀴가 끝나면 **남은 빈 칸만 다시 도는 바퀴**를 빈 칸 0 또는 중지 요청까지 반복(쿨다운·당일 중단 없음 = D-030 유지). 진전 있는 바퀴 끝마다 결과 저장+구글시트 반영(`track_ranks_stage` on_pass). 차단도 연결 장애도 없는데 한 바퀴 진전이 없으면(검색결과가 안 나오는 키워드) 남은 칸을 ❌ 로 기록하고 마침(무한 반복 방지). (2) **프록시 연결 장애는 차단과 구분**: IP 확인(에코 2곳) 모두 실패 = 그 IP 로 검색하지 않고 다음 IP·차단 목록에 안 남김, 검색 중 크롬 연결 오류 화면(chrome-error://)도 '연결 장애'(차단 집계·차단 목록 제외). 연속 3번이면 5분 쉬고 다음 IP 는 확인 실패여도 실제 검색 화면으로 판정(에코 서비스 장애로 영영 못 도는 것 방지). 연속 미로딩 회전은 IP 를 바꾸되 차단 목록엔 안 남김(증거 없음). (3) 차단 판정마다 **증거**(판정 단어·주소·제목·본문 앞 1500자 txt + 화면 png)를 `output/_순위차단/` 에 최근 20건 보관·로그에 판정 단어와 파일명. (4) 끝 요약 = 측정·**빈 칸**·차단·**연결 장애**·IP 전환·바퀴 수, 빈 칸이 남으면 전체실행/무인 끝 문구 = '⚠ 순위 빈 칸 N개 남음'(`pipeline_ranks.LAST_RANK`)·'✅ 완료' 아님.
- 근거: 소유자 목표(2026-10-13 "공란, 종료 안됨, 모두 정상 수행이 목표" + 선택 "프록시 연결 장애는 차단과 구분"·"코드에서 확인된 문제 수정"). 실측(운용 PC 10-12 18:33 시작 ③ 로그·output (19)(20)): 19:51~20:55 IP 확인 실패·페이지 미로딩(프록시 연결 장애)을 차단으로 집계·차단 목록 등록 · 21:01~22:06 진짜 차단은 막힌 키워드마다 다른 IP 에서 결국 성공 · 22:06~다음 날 11:14 '밀키트' 한 키워드만 차단 569회·IP 198개(그 키워드부터 다시 규칙에 갇힘 → 뒤 45상품 미검색·IP 전환 614회) · 기록 37/약 220칸인데 '✅ 완료' 표시 · 증거 없어 원인 확정에 별도 통제 실험(노트북 같은 프록시로 타프·밀키트 정상, 소유자 운용 PC 밀키트 정상 확인) 필요했음. 재현: 핀 K(차단 뒤 다음 키워드·다음 바퀴)·L(번갈아 시도·빈 칸 집계)·K2(새 IP 는 다음 키워드부터)·K3(측정 불가 ❌ 종료)·K4(증거 20건) 실패→통과, test_proxy_patch 연결 장애 2종(12 PASS), 게이트 12종·복잡도 경고 0.
- 버린 대안: (a) D-030 '막힌 키워드부터 다시' 유지(실측 13시간 갇힘) (b) 막힌 키워드 N번 뒤 공란 확정(소유자 목표 '공란 없음'과 다름) (c) 연결 장애도 차단으로 집계(건강한 IP 를 차단 목록에 올리고 원인 판단을 흐림) (d) 차단 시 쿨다운(소유자 거부·D-030).
- 위험: 모든 IP 가 계속 막히면 ③이 끝나지 않음(D-030 과 같음 — 다음 날 18:00 시작 정리가 끝냄). 연결 장애 연속이면 5분씩 쉼.
- 영향 범위: `pipeline_ranks.py`(drive_rank halt_reason·_run_on_egress conn·_conn_trouble·_block_marker·_save_block_evidence·_connection_down·_SemiState·_track_ranks_semi 바퀴·_semi_one_pass·_semi_next_pass·_rank_todo·_unfilled·_semi_on_miss·LAST_RANK·요약), `pipeline_stages.py`(LAST_RANK 비움), `ui/app_qt.py`(끝 문구), `tools/pin_login_ranks.py`·`tools/test_proxy_patch.py`·`tools/simulate_pipeline.py`. **HQ 포팅 필요**.
- 상태: ACTIVE (부분 SUPERSEDED by D-090 — (1) '진전 없는 바퀴 = 남은 칸 ❌ 로 마침'은 IP 불량이 없던 바퀴만(IP 불량 바퀴는 빈 칸 0 까지 반복)·끝 조건 추가: 성공 없이 IP 불량 15번 연속이면 ③ 마침)

### D-054 [SETTLE_VERIFY_RENAME] 정산 계정명 맞춤에 검증 자료 포함 — 예전 이름 검증 자료 = 수집일 최근 것 하나만 (2026-10-13, R12)
- 결정: `settlement_store.migrate_names` 가 `output/정산/검증자료/{계정명}.json` 의 계정명도 바꿈표에 넣고 지금 이름으로 옮긴다. 검증 자료는 매번 전체 기간을 다시 담는 스냅샷이라 합치지 않고, 두 이름이 다 있으면 **수집일이 최근인 쪽 하나**(같으면 지금 이름 쪽)만 남긴다. 계정 파일에 없는 계정 파일은 그대로.
- 근거: 운용 PC output (20)(10-13) 실측 — 10-12 19:56 정산 계정 파일 `aehee5505`·`hk66597582` 줄 3열이 비밀번호와 같아 이름 없음 처리 → 받은 파일·금액은 새 이름으로 맞춰졌으나("[계정명 맞춤] … 파일 계정명 3개") 검증 자료는 예전 이름(`손애희-55마켓-…`·`강혁-디케이유니버스-…`)이 남아 정산집계 '계좌 입금'에 두 계정이 두 번(13줄·RG 월렛 입금 +37,290,705원)·'검증'에도 중복. 재현: 핀 P24(e) 실패→통과 · 실자료 사본에 적용 후 재집계 = 계좌 입금 307→294줄·중복 이름 0·RG 월렛 입금 2,835,839,299→2,798,548,594 · 게이트 12종·복잡도 경고 0.
- 버린 대안: (a) 집계 단계에서 이름 중복을 걸러냄(원인 파일이 남아 다른 소비처도 계속 오염) (b) 금액처럼 키 병합(스냅샷이라 합칠 단위 없음·옛 수집본 섞임 — 실측 예전 이름 쪽이 윙 지급 등 빠진 옛 수집본).
- 영향 범위: `src/coupang_analytics/settlement_store.py`(migrate_names·_keep_newer_verify), `tools/verify_settlement_runtime_offline.py` P24(e). 운용 PC 는 재배포 후 첫 정산 실행(load_accounts) 때 자동 정리. **HQ 포팅 필요**.
- 상태: ACTIVE

### D-055 [SETTLE_WITH_MANUAL_FULL_RUN] 사람이 누른 전체실행도 정산 함께 기동 — 그 실행의 ①판매수집 완료 뒤 받기 · 순위는 1페이지 유지 (2026-10-13, R12)
- 결정: (1) 앱 '전체실행' 버튼(①②③)을 누르면 18:00 무인과 같은 정산 자동 수집(watch)을 함께 띄운다(`start_settlement_watch(since=누른 시각)`). 정산은 `--since` 시각 **뒤에 끝난 ①판매수집**(단계 기록 sales/done)만 기다렸다가 받는다 — 같은 회차의 앞선 ① 기록으로 바로 받거나 '이미 끝남'으로 종료하지 않음. 끝 = 다 받으면·17:55(D-021)·사람이 앱을 끄면 함께(D-020). '판매수집'(① 단독) 버튼은 ① 완료 기록을 남기지 않아(run_stages) 띄우지 않음. 18:00 무인·재부팅 복구·정산 탭 버튼은 그대로(`--since` 없음). 이미 정산이 떠 있으면 정산 쪽 잠금이 둘째를 끝냄. (2) 노출순위는 지금처럼 **1페이지만** 읽고, 못 찾으면 그 페이지에서 실제로 센 개수로 'N위밖'(변경 없음).
- 근거: 소유자 지시(2026-10-13 "정산 다운로드 무인 실행 가능하게·전체실행 시 동시에 실행·판매수집 대기 후 자동 실행", 순위 질문 답 "지금처럼 1페이지만"). 코드 확인: 정산은 `--auto`/`--resume` 때만 기동(app_qt main)·전체실행 버튼 경로엔 없음. 재현 verify_settlement_runtime P30(14:00 수동 실행·새벽 ① 완료 기록 → --since 없으면 바로 '이미 끝남' 종료) 실패→통과·P25~P29 유지·게이트 12종·복잡도 0. 순위: 운용 마스터(output 20) '위밖' 칸 = 50위밖 다수(1페이지 광고 제외 상품 보통 50개)·10-12 로그 미발견 16건 중 '50위밖' 15·'60위밖' 1 = 실제 센 개수(고정값 아님).
- 버린 대안: (a) ① 단독 실행에도 기동(① 완료 기록이 없어 17:55 까지 대기만) (b) 회차 시작(18:00) 기준 대기 유지(낮 수동 실행 때 새벽 ① 기준으로 판정) (c) 순위 2페이지까지 읽기(소유자 미선택·요청 증가).
- 영향 범위: `app_process.py`(settlement_watch_cmd·start_settlement_watch since), `tools/settlement_download.py`(--since·cmd_watch), `ui/app_qt.py`(do_run_full), `tools/verify_settlement_runtime_offline.py` P30. **HQ 포팅 필요**.
- 상태: ACTIVE

### D-056 [SALES_GMV_DAILY] 판매분석 판매금액(totalGmv) 날짜별 누적 — output/판매분석_일별/{계정ID}.json (2026-10-13, R12)
- 결정: ① 판매수집이 계정마다 판매분석(vi-detail-search) 하루치(D-1) 조회를 마치면 옵션별 판매금액·판매수량·주문·구분(윙/로켓그로스)·상품명을 날짜 키로 쌓는다(`sales_history.record`). 하루 단위 조회만(넓은 기간 vid 보강 조회 제외)·판매금액 모르는 출처(엑셀 폴백=gmv None) 제외·같은 날 재실행=그날 교체·판매 0인 날도 빈 기록·원자적 저장·저장 실패는 비치명(로그). `OptionMetric` 에 gmv(없으면 None)·orders 추가(기존 지표 불변).
- 근거: 소유자 요청(2026-10-13 "판매분석 금액 날짜별로 쌓도록") — 쿠팡 정산이 판매보다 늦어 사업자별 정산내역의 로켓그로스 미정산을 부가세×비율로 추정(8월 백테스트 합계 −2.5%·소규모 계정 최대 +82%)해야 했음. 응답의 totalGmv 를 버리고 원문(_raw)도 매번 덮어써 하루치만 남던 상태. 실측: 운용 PC output (20) 원문은 하루치 조회와 30일 보강 조회가 한 파일 묶음에 섞임(계정 24/27) → 하루치 조회 결과만 기록해야 함. 재현·검증: verify_sales_history_offline(S1~S3)·핀 S(실제 `_login_and_discover`) 실패→통과 · 실원문 하루치 27계정 판매금액·옵션 수 원 단위 일치(합 4,875,640원) · 게이트 13종·복잡도 경고 0.
- 버린 대안: (a) 원문(_raw) 파일을 날짜별로 보관(조회 두 종류가 섞여 하루치 구분 불가·용량) (b) 판매수량×판매가로 금액 계산(쿠폰·할인 반영 안 됨) (c) 결과 통계 마스터에 금액 칸 추가(결과시트 서식·HQ 계약 변경 범위 큼).
- 영향 범위: `report.OptionMetric`(gmv·orders), `collector._parse_vendor_items`, `pipeline_sales._login_and_discover`·`_record_sales_history`, 신규 `sales_history.py`, `tools/verify_sales_history_offline.py`(게이트 등록)·`tools/pin_login_ranks.py` 핀 S. 운용 PC 재배포 후 첫 18:00 부터 쌓임(과거 날짜 소급 없음). **HQ 포팅 필요**(새 출력 파일).
- 상태: ACTIVE (부분 SUPERSEDED by D-094 — '과거 날짜 소급 없음' → 2026-04-01부터 하루씩 소급(같은 로그인 세션·그 뒤 하루 상한·시작일 변경은 D-094 상태 줄))

### D-057 [RANK_PROFILE_PER_IP] ③ 순위 — 프록시 주소(sessid)마다 순위 프로필 따로 · 이번 실행에 막힌 (주소, IP) 재사용 금지 · 주소가 전부 막힌 IP 면 새 IP 대기 (2026-10-13, R12)
- 결정: (1) 순위 브라우저 프로필 = 프록시 주소마다 따로 `data/chrome-rank/<sessid>`(sessid 없으면 주소 해시·자격증명은 경로에 안 넣음, 프록시 없으면 기존 `data/chrome-pipeline`) — 'IP 하나 = 기기 하나'. (2) 차단 판정(차단 페이지) 난 (주소, egress IP)는 그 주소가 아직 같은 IP 를 주는 동안 **검색하지 않고 건너뜀**(IP 확인만). (3) 한 바퀴 동안 검색한 주소가 하나도 없으면(전부 막힌 IP·연결 장애) 업체가 새 IP 를 줄 때까지 5분 대기 후 다시 확인(D-030 의 '차단 뒤 쉼'과 다름 — 쓸 IP 가 없을 때만). D-053 의 바퀴 반복·빈 칸 0 까지는 유지.
- 근거: 실측 운용 PC 10-13 18:00 ③(19:02~21:16): IP 87번 열어 77번 첫 검색 즉시 차단·성공 21·차단 85 · 이번 실행에 막힌 IP 재사용 55번 중 53번 즉시 차단 · 처음 쓰는 IP 도 32개 중 24개 즉시 차단(20:09 이후 전부) · 프록시 주소 8개가 약 45분씩 같은 IP(19:02~19:49 같은 8개 반복) · 증거 화면 = 쿠팡 실제 차단 페이지('사용권한'·Ref). **통제 실험(노트북, 같은 proxies.txt → 같은 IP)**: 운용 PC 가 21:01~21:16 막힌 IP 3개(211.241.214.88·210.206.230.51·49.165.138.156)·같은 키워드로 21:27~21:30 노트북 프로필 검색 = 3/3 정상(상품 60) → 막히는 건 IP 가 아니라 운용 PC 순위 프로필 신분. 새 빈 프로필+프록시 첫 검색 정상(21:34, 60개). 정산 로그인과는 무관(순위 차단 19:11 시작 < 정산 로그인 19:25 · 10-12 순위 차단 중 정산 로그인 35/35 정상). 재현 test_proxy_patch `test_drive_rank_profile_per_ip` 실패(막힌 IP 반복·프로필 1개)→통과·13 PASS·게이트 13종·복잡도 0. 소유자 선택 '1번(IP 마다 프로필 따로)'.
- 버린 대안: (a) 막히면 쿠키만 비우고 새 IP(매번 낯선 방문자) (b) 막힌 IP 계속 재사용(실측 53/55 헛 검색·비용) (c) 운용 PC 확인 실험 먼저(소유자 미선택).
- 미확정: 신분 중 쿠키인지 그 PC 브라우저 지문까지인지는 미분리 — 프로필 분리 뒤에도 새 IP 첫 검색 차단이 이어지면 지문 쪽(운용 PC 재검증 필요). 첫 밤 `[순위요약]`·IP 별 성공 수로 판정.
- 영향 범위: `pipeline_ranks.py`(_rank_profile·_run_on_egress skip_pairs·drive_rank pairs/ran·_next_round·_rank_single_open), `tools/test_proxy_patch.py`. 디스크: 프로필 최대 8개(캐시 포함 각 수백MB 가능). **HQ 포팅 필요**.
- 상태: ACTIVE

### D-058 [PROXY_IDENTITY_FOLLOWS_IP] 🔒 프록시 쓰는 비로그인 브라우저 = 흔적(쿠키·저장소)은 같은 IP 동안만 — IP 바뀌면 비우고 시작 (설계 원칙) (2026-10-13, R12)
- 결정: (1) **설계 원칙**: 프록시로 IP 를 바꾸는 비로그인 공개검색 브라우저는 **'IP 하나 = 흔적 하나'** — 같은 IP 가 이어지는 동안 흔적 누적(신용), 그 프로필이 지난번과 다른 IP 로 나가면 **쿠팡 접속 전에 흔적을 비우고** 시작. 매번 비우기(같은 IP 에서 새 방문자가 계속 생김)도, 계속 누적(흔적이 IP 를 따라다님)도 아님. 앞으로 프록시를 쓰는 기능은 이 원칙을 기본으로 설계. **로그인·판매수집·정산은 해당 없음** = 고정 IP + 흔적 유지(위탁계정·2차인증 위치 기반·[[proxy-ip-policy-by-context]]). (2) 구현(③ 순위): `_identity_follows_ip` — IP 확인(ipify·쿠팡 아님) 뒤 프로필 폴더의 `_rank_egress.txt`(마지막 IP)와 다르면 쿠키 전체 + `Storage.clearDataForOrigin`(www.coupang.com·coupang.com, all) 비우고 IP 기록. 같은 IP 면 그대로. 비우기 실패 = ⚠ 로그 후 진행(IP 기록 안 남겨 다음에 다시). D-057(주소마다 프로필·막힌 (주소,IP) 재사용 금지) 위에 얹음.
- 근거: 소유자 지시(2026-10-13 "프록시 설계 시 프로필 클리어 방식이 기본" → 누적/클리어 비교 후 "수정내용 정책반영"). 실측 비교: 누적+IP 고정(09-14 사무실 IP 밤샘 271키워드 차단 0)=좋음 · 누적+IP 계속 바뀜(10-13 운용 PC 87번 중 77번 첫 검색 차단)=나쁨 · 다른 프로필+같은 IP(노트북 3/3)·빈 프로필+프록시(21:34 1/1)=좋음 · 빈 프로필+사무실 IP 상품 페이지=막힘(예전 상세 이미지) → '항상 비움'도 안전하지 않음. D-057 만으론 업체가 주소마다 약 45분마다 IP 를 바꿔 한 프로필이 밤새 IP 15개 안팎을 옮겨 다님(빈틈). 재현 test_proxy_patch `test_rank_identity_follows_ip` 실패→통과(14 PASS)·실제 Chrome 확인(쿠팡 쿠키 2→0·같은 IP 재호출 시 그대로)·게이트 13종·시뮬 112·복잡도 0. 설계 실수 기록: 프록시 도입(10-01~02) 때 사무실 단일 IP 시절의 '신뢰 쿠키 보존'(`rank.warmup`)을 그대로 둠.
- 버린 대안: (a) 매 실행·매 IP 비우기(같은 IP 에서도 새 방문자 반복) (b) 누적 유지(10-13 실측) (c) 프로필 폴더 통째 삭제(캐시까지 지워 데이터·시간 비용↑ — 쿠키·저장소만으로 충분).
- 미확정: 빈 프로필 성공 근거 1회 — 첫 밤 'IP 당 성공 수'·'새 IP 첫 검색 차단 비율(77/87)'로 판정. 개선 없으면 쿠키가 아닌 PC 브라우저 지문 의심.
- 영향 범위: `pipeline_ranks.py`(_identity_follows_ip·_run_on_egress), `tools/test_proxy_patch.py`, CLAUDE.md 프록시 정책. ② 자동완성·키워드/순위 조회 탭(공개검색 프록시 D-031)은 IP 1개·짧은 사용이라 이번엔 미적용(같은 원칙 적용 대상 — 별도 사이클). **HQ 포팅 필요**.
- 상태: ACTIVE

### D-059 [SETTLE_CONSIGNOR_STATEMENT] 사업자별 정산서 양식 = 위탁 판매 정산서(2번 위탁정산서형) · 첫 시트 = 전체 계정 정산 요약 (2026-10-14, R13)
- 결정: 사업자별 정산서 = '위탁 판매 정산서' 1시트(머리: 정산서 번호·발행일·정산기간·계약자·채널·수수료 조건 → A 판매 내역(월·윙/로켓그로스) → B 차감(판매수수료·할인쿠폰·기타 조정·로켓그로스 물류비·재고 손실 보상) → C 순지급액(확정·정산 예정·총 정산금액) → **D. 쿠팡 미정산(정산 예정) 목록** → E 지급 기록(쿠팡 지급·대표계좌 입금 + 광고비·선정산 상환 '참고') → 증빙·검증·계약자 확인란). 통합 파일 첫 시트 = 전체 계정 정산 요약(① 판매 → ② 비용 → ③ 확정 → ④ 쿠팡 미정산 → ⑤ 총), 이어서 사업자마다 위탁정산서. 사업자별 전달 파일 = 위탁정산서 + 상세 시트.
- 근거: 소유자 2026-10-14 웹·유튜브 양식 5종(거래명세서·위탁정산서·다중시트·대시보드·손익계산서) 샘플 비교 후 '2번 위탁정산서형 확정·D 용어 변경·첫 시트 전체 요약' 지시. 30곳 생성·각 정산서 확정/총액 = 전체 요약 30/30 일치·①−②=③·③+④=⑤ 원 단위.
- 버린 대안: 1번 거래명세서형(차감 근거 약함) · 3번 다중시트(수식) · 4번 대시보드(증빙 약함) · 5번 손익계산서 단독.
- 영향 범위: 앱 코드 아님 — `output/_분석_261013/정산스크립트/business_statements.py`(분석 스크립트·git 밖) · 결과 `D:\토탈셀러\쿠팡 정산 자료\위탁정산서_20261014\`. 앱 기능화·HQ 포팅은 미정.
- 상태: ACTIVE (부분 SUPERSEDED by D-126 — 사업자별 정산서 1쪽 'A 판매 → B 차감 → C 순지급 → D 미정산 → E 지급 기록 → 증빙·계약자 확인란' → A − B − C + D = E − F = G 흐름·큰 숫자마다 내역 표·서명란 삭제)

### D-060 [SETTLE_UNSETTLED_SOURCE] 쿠팡 미정산(정산 예정) 산출 — 윙 = 매출내역 · 로켓그로스 = 판매분석 판매금액 × 수수료율(실측) / 없으면 부가세 × 과거 비율(추정) (2026-10-14, R13)
- 결정: 정산 파일에 아직 없는 판매를 정산서 '정산 예정'에 넣는다. 윙 = 검증자료 매출내역(purchase) 월 정산대상액 − 정산 파일 몫('확정'). 로켓그로스 = 판매분석(vi-detail-search/쿠팡 '기간별 판매' 파일) 판매금액 × (1 − 실측 수수료율)('실측') — 라이브 자료 없으면 부가세 결제합계 × 계정 과거 정산 비율('추정'). 구분 칸에 확정/실측/추정 표시·쿠폰 없음 가정은 비고에.
- 근거(실측): 윙 매출내역 정산대상액 = 정산 파일 87/87 원 단위 일치(2026-03~07). 판매분석 totalGmv: 로켓그로스 = 정산 파일 매출금액 기준(에벤에셀 7월 0원·8월 1,000원 차·쿠폰 전) · 윙은 다른 기준(주문일·7월 −4.6%·8월 −27%) · 하루 조회 합 = 기간 조회 · 웨이브텍 8/17~9/6 판매분석 날짜 = 정산 파일 매출인식일 21/21 일치. 부가세×비율 추정 8월 백테스트 합계 −2.5%(소규모 계정 최대 +82%). 소유자 지시: 이용진 건 실측 수집·예정 금액·총액 반영.
- 버린 대안: 윙에도 판매분석 사용(기준 다름) · 미정산 제외(정산 지연만큼 계약자 정산 누락).
- 영향 범위: 분석 스크립트(`business_statements.py` `_wing_unsettled`·`_rg_unsettled`·실측 JSON 옵션) · D-056(판매금액 날짜별 누적)이 쌓이면 추정 → 실측 전환 가능.
- 상태: ACTIVE — 로켓그로스 부분(부가세×비율·판매분석×수수료율) SUPERSEDED by D-081

### D-061 [SETTLE_EVIDENCE_ORIGINALS] 정산 증빙 = 쿠팡에서 직접 내려받은 원본 파일 (2026-10-14, R13)
- 결정: 계약자 정산 증빙·대사 자료는 쿠팡 윙에서 받은 원본 파일로 구성한다 — 로켓그로스 정산현황 '판매수수료 리포트'(주정산별·요청 후 정산관리 엑셀 다운로드 목록에서 받기)·비용 리포트·윙 정산 주문상세·판매분석 '기간별 판매'/'상품별 판매'(엑셀 다운로드). 운용 PC 수집본(구매자명 지운 사본)은 계산 입력용, 증빙 원본 아님.
- 근거: 소유자 2026-10-13 "쿠팡 제공 다운로드 파일로 생성", "원래 사용하던 파일이 증빙자료가 되어야 함". 실측: 웨이브텍 판매분석 기간별 파일 36일 = 데이터 조회값·합계 22개·281,600원 = 화면·상품별 파일 일치.
- 버린 대안: 데이터 주소 조회값만으로 증빙(쿠팡 원본 아님) · 운용 PC 사본(구매자명 제거본).
- 운영 사실: 다운로드는 대표 로그인 세션에서만(Claude 는 비밀번호 입력·로그인 안 함) · Chrome '여러 파일 자동 다운로드' 허용 필요(차단 시 화면 버튼도 막힘) · 세션은 수 시간 뒤 만료 · 로켓그로스 리포트 요청 간격 45~75초.
- 영향 범위: 증빙 폴더 `D:\토탈셀러\쿠팡 정산 자료\사업자별_정산내역_20261013\증빙_웨이브텍_쿠팡원본\`·`증빙_웨이브텍_이용진_미정산_일자별_261013.xlsx`. 전 계정 원본 수집 절차는 미완(다음 작업).
- 상태: ACTIVE

### D-062 [SETTLE_KEEP_ORIGINALS] 정산 다운로드 `--originals <폴더>` = 받은 쿠팡 원본을 받은 그대로 증빙 폴더에 복사 (2026-10-14, R13)
- 결정: `tools/settlement_download.py` request·download·run 에 `--originals <폴더>` 옵션 추가. 지정하면 받은 파일(윙 주문상세·로켓그로스 판매수수료·비용 리포트)을 구매자명 지우기 전 바이트 그대로 그 폴더에 복사(이름 = 정산 파일 이름 규칙). 집계용 사본(구매자명 제거)·비용 폴더·요청 기록 처리는 그대로. 지정 안 하면 지금 동작과 같음(운용 PC 자동 실행 영향 없음).
- 근거: D-061(증빙 = 쿠팡 원본) — 기존 코드는 판매수수료·윙 원본을 사본 만든 뒤 지움(`_fetch_one` scrub_pii → raw.unlink). 소유자 2026-10-14 "판매현황 조사처럼 앱이 로그인해서 수집"(2번 선택·코드 수정 승인) — Claude 는 비밀번호를 보거나 입력하지 않고 앱이 계정 파일로 로그인. 핀 P31(원본 바이트 동일·사본 불변·미지정=폴더 없음) 재현 실패→구현→통과·게이트 13종 초록.
- 버린 대안: 소유자 브라우저 로그인 후 Claude 수동 다운로드(소유자가 앱 로그인 방식 선택) · 원본 기본 보관(운용 PC 에 구매자명 파일 상시 누적 — 개인정보 최소화 위반).
- 영향 범위: `tools/settlement_download.py`(전역 ORIGINALS·`_fetch_one` 3줄·인자 1개) · `tools/verify_settlement_runtime_offline.py` P31. 원본 폴더에는 구매자명이 있음 — 소유자 로컬 증빙 폴더에만 지정. 판매분석 파일(기간별·상품별)은 이 도구 범위 밖.
- 상태: ACTIVE (부분 SUPERSEDED by D-145 — 원본을 소유자 로컬 증빙 폴더에만 두는 제한)

### D-063 [SALES_EXCEL_MENU] 판매분석 엑셀 받기 = 메뉴 '상품별 판매'·'기간별 판매'(실측) · `collector.download_report(menu=)` (2026-10-14, R13)
- 결정: `collector.download_report` 에 `menu` 인자(기본 '상품별 판매')를 두어 '엑셀 다운로드' 드롭다운의 '상품별 판매'·'기간별 판매' 둘 다 받는다. 정산 증빙(D-061)용 판매분석 원본은 이 함수로 계정 로그인 세션(앱 로그인·D-062 방식)에서 월별로 받는다.
- 근거(실측): 2026-10-14 wavetech 판매분석 화면 '엑셀 다운로드' 클릭 후 새로 보인 항목 = ['기간별 판매', '상품별 판매'] — 기존 코드가 찾던 '상품별 판매 리포트'는 화면에 없어 데이터 API 실패 시 예비 경로(엑셀 폴백)가 항상 실패하던 잠복 결함. 핀 X(실측 메뉴 페이크) 재현 실패→수정→통과·게이트 13종 초록. 소유자 지시 "판매분석 월별 파일도 받아·누락 안 됨".
- 버린 대안: 판매분석 데이터 주소 조회값으로 증빙 대체(D-061 — 쿠팡 원본 아님) · 증빙 스크립트에 다운로드 코드 복제(중복).
- 영향 범위: `src/coupang_analytics/collector.py`(download_report 인자·메뉴 글자) · `tools/pin_login_ranks.py` 핀 X. ①판매수집 기본 경로(데이터 API)는 불변 — 그 경로 실패 시 엑셀 폴백이 이제 실제로 동작.
- 상태: ACTIVE

### D-064 [SALES_SUMMARY_FIRST_SHEET] 통합 판매현황 = 결과 파일 첫 시트 · 계정·상품별 수량·금액(윙/로켓그로스) · 전일·주(월~일)·월 세로 3구역 · 매일 배치 (2026-10-15, R13)
- 결정: (1) 결과 파일(통계 마스터 xlsx + 결과 구글시트) **첫 시트 `통합판매현황`**(기존 시트 한 칸씩 오른쪽·파일 열면 이 시트) — 위탁계정 **계정→상품(옵션 합산)** 줄, **판매수량·판매금액**, **윙/로켓그로스 줄 나눔**, **세로 3구역 [1. 전일] → [2. 주간(월~일) 최근 8주·이번 주 누계] → [3. 월별 2026-01~이번 달 누계]**, 구역마다 전체 합계·미수집 계정 수·계정 소계, 판매 0 상품 생략, 최신 칸 왼쪽. 받지 못한 기간 = **'미수집'**(0 과 구분). 특수 시트(`_SPECIAL_SHEETS`)로 등록 — 사업자 시트 미러링·삭제 정리·색인 대상 아님. (2) 원천 = **판매분석(주문 기준)**, 정산 파일과 섞지 않음. 전일 = 일별 기록(D-056), 주·월 = **기간 합계를 쿠팡에서 그대로 조회해 저장**(`output/판매분석_기간/{계정ID}.json`·키 `M:YYYY-MM`·`W:월요일`) — ① 판매수집이 로그인한 같은 세션에서 처음엔 1월~이번 달·최근 8주 소급, 그 뒤엔 이번 달·이번 주 누계와 막 끝난 기간만(마감된 기간 재조회 없음·조회 사이 1~2.5초·실패하면 그 계정 남은 조회만 멈춤·어떤 실패도 ① 수집을 막지 않음). (3) 매일 배치 = ① 끝(`_finalize_run`)·③ 시작(`track_ranks_stage`)에서 다시 그림 → 저장 → 결과 구글시트에 시트 반영 후 index 0 으로 이동. (4) 진행 위치 = **R0**(밤마다 계정에 로그인해 쌓는 건 R0 뿐·HQ 전환 전) — 새 코드는 새 파일(`sales_summary`·`workbook_sales`)로 분리, HQ 포팅 대상. (5) 순서 = 판매현황 먼저, 정산 파일 전수 조사·보강은 R13 정산서 증빙 단계 뒤. 남은 단계: 3) 비대장 위탁계정(정산 watch 가 같은 조회) 4) 앱 '판매 현황' 탭 5) 정산 파일 전수 조사·전체 받기·매일 보강.
- 근거: 소유자 2026-10-15 요청("월별·주간별·일자별 통합 판매현황·결과파일 첫 번째 시트·기존 시트 오른쪽으로·매일 배치") + 답("계정별 상품별 판매수량·판매금액·윙/로켓그로스 나눔", "월·주·전일", "위탁계정 전체", "진행 위치·순서는 Claude 가 정함", 시트 배치 '세로 3구역' 선택). 사실: 판매분석 API 는 아무 기간 합계를 한 번에 줌(D-060 '하루 조회 합 = 기간 조회'), 운용 PC 일별 기록 = 10-12 부터 21계정(1/1~10/11 없음). 설계 중 발견: `apply_style` 이 매번 '계정 목록'을 맨 앞에 다시 만듦 → 통합판매현황 뒤로 놓게 수정 · `_reindex` 가 특수 시트를 이름으로 직접 걸러 등록 필요. 시험: verify_sales_summary_offline T1~T6 신설(게이트 등록) · 핀 A 가 기간 조회 중 브라우저 오류로 ① 수집이 깨지는 결함을 잡아 수정(모든 예외 비치명·로그) · 시뮬·정밀 렌더 검증의 특수 시트 목록에 새 시트 추가+'첫 시트=통합판매현황·둘째=계정 목록' 확인 · 운용 PC 마스터 사본 실데이터: 첫 시트·사업자 시트 25개 불변·10-12 전일 293개·5,801,890원·미수집 5계정 · 게이트 14종·복잡도 경고 0.
- 버린 대안: (a) 가로 한 표(소유자 미선택) (b) 일별 기록을 더해 주·월 계산(로그인 실패한 날이 영구 구멍) (c) 정산 파일 매출로 판매현황(매출인식일 기준·늦음) (d) HQ 에서만 구현(데이터 수집 주체가 R0·전환 전).
- 영향 범위: 신규 `sales_summary.py`·`workbook_sales.py`·`tools/verify_sales_summary_offline.py` · `sales_history.py`(record_period·load_daily·load_periods) · `pipeline_sales.py`(_record_sales_periods) · `pipeline.py`(_finalize_run) · `pipeline_ranks.py`(track_ranks_stage) · `pipeline_gsheet.py`(push_gsheet) · `workbook_common.py`(_SALES_SHEET) · `workbook.py`(_reindex) · `workbook_index.py`(_build_index 위치·활성 시트) · `tools/run_checks.py`·`simulate_pipeline.py`·`verify_render_precision.py`. 설계 = `designs/SALES_SUMMARY.md`. **HQ 포팅·R0_DATA_CONTRACT 알림 필요**(결과 파일 첫 시트·새 폴더 `output/판매분석_기간/`). 첫 운용 실행은 계정당 기간 조회 약 18회(1회성 소급·계정당 약 1분).
- 상태: ACTIVE (부분 SUPERSEDED by D-094 — 세로 3구역·집계 범위 · SUPERSEDED by D-105 — 시작 달 1월 → 4월 · 남은 단계 4 앱 '판매 현황' 탭 = 만들지 않음(결과 구글시트 첫 화면으로 충분·RETIRED by D-179) · 단계 3 비대장 계정 수집 = 정산 실행이 함 D-165)

### D-065 [SETTLE_VERIFY_RULES] 정산 증빙 원본 = 평문 보관(소유자 결정) · 통장↔쿠팡 원본 정밀 검증 규칙(실측) · 지급 증빙 목록 (2026-10-15, R13)
- 결정: (1) 사업자 증빙 폴더(`D:\토탈셀러\쿠팡 정산 자료\…\증빙_{사업자}_쿠팡원본\`)의 쿠팡 원본(구매자명 포함 주문상세 등)은 **평문 그대로 보관**(암호 압축 안 함). (2) 통장 대사는 입금을 네 갈래로 나눠 맞춘다 — 윙 지급(대표계좌 직접) · 로켓그로스 월렛 인출 · 재고 손실 보상(월렛을 거치지 않고 대표계좌 직접 'F/B') · 우대수수료 환급(쿠팡페이 별도, 매월 ≈2일·≈17일). 쿠팡 정산 화면 어디에도 없는 입금은 소유자 확인으로 분류(예: 니코에이블 08/20 3,414,944 = 화재 보상금). (3) 검산 규칙(실측·원 단위): 윙 70% = **구매확정일 하루 합 사사오입**(14/14), 30% = 기간 정산금액 − 그 기간 70% 몫들 · 로켓그로스 70% = **주문 단위 사사오입**(20주/20), 30% = 나머지 · 로켓그로스 줄 최종지급액 = 정산대상 − (광고비+밀크런+마이너스일) − 물류비(CFS) + 재고 손실 보상 + 판매조정(39/39) · 환불>판매인 날(마이너스일)은 100%를 다음 70% 지급에서 공제하고 판매조정 줄이 70/30 몫을 되돌림 · 광고비·밀크런·물류비는 지급액 한도까지 공제하고 남으면 다음 지급으로 이월 · 윙 광고비(SELLER)·판매자서비스이용료 5만+VAT 는 윙 지급 명세에서 공제. (4) 지급 증빙(쿠팡 원본·화면 인쇄) 목록 = 윙 정산현황 지급 명세(금액 클릭으로 펼친 매출 상세내역 — 달마다 PDF; '미리보기'는 구매자 이름 화면이라 인쇄 안 함) · 로켓그로스 가상계좌 거래내역('전체' PDF) · 우대수수료 환급 엑셀(한 달씩 요청 → 정산관리 엑셀 다운로드 목록에서 받기) · 광고센터 월별 광고비 정산내역 보고서(PDF) · 로켓그로스 광고비 내역·밀크런 내역(달마다 PDF) · 정산 줄 없는 주의 비용 리포트(묶음 키로 요청).
- 근거: 소유자 2026-10-15 "보관은 평문으로", "08/20 3,414,944 = 화재 보상금", "메뉴얼 학습 내용으로 통장과 다운로드 파일 정밀 검증·70/30 감안·필요한 내역 다운로드". 실측(니코에이블): 통장 22건 26,139,506 = 윙 12건 9,092,491 + 월렛 인출 3건 13,260,663 + 재고 손실 보상 3건 225,982 + 우대수수료 환급 3건 145,426(환급 497건) + 화재 보상 3,414,944 — 쿠팡 정산분 22,579,136 원 단위 일치·불일치 0. 광고센터 SELLER 6~8월 공급가 335,921×1.1=369,514 = 윙 광고비 공제 합 · 물류비 원본 995,394(5/11~17 바코드 13,200 포함) = 공제 925,979 + 이월 69,415. 도움말 학습 = `docs/COUPANG_WING_HELP_KB.md`.
- 버린 대안: 암호 압축 보관(소유자 평문 선택 — 도움말의 '다운로드 자료 암호화 보관' 권고와 다름을 알고 결정) · 70%를 기간 합에 반올림(윙 9/18 1원·로켓그로스 9/7~13 7원 불일치) · 파이썬 기본 반올림(짝수 맞춤 — 1원 차이).
- 영향 범위: 니코에이블 증빙 폴더 `지급증빙_메뉴원본\`(PDF 23·엑셀 2·월렛 PDF 2 = 27개)·`정산원본_앱수집\`(41 + 5/11~17 비용 리포트 5 = 46개) · 대사표 `대사_니코에이블_통장입금_vs_쿠팡원본_261015.xlsx` · 정밀검증 `정밀검증_니코에이블_쿠팡원본_70-30_261015.xlsx` · 수집·검증 스크립트는 세션 작업 폴더(운용 PC 전 계정 '증빙' 명령으로 옮길 대상 — 다음 작업) · `docs/COUPANG_WING_HELP_KB.md` §1-13. HQ 포팅 대상(정산 검산 규칙).
- 상태: ACTIVE

### D-066 [SETTLE_PAYOUT_ROUNDING] 윙 70% = 구매확정일 하루 합마다 사사오입(기간 전체×70% 폐기) · 쿠팡 정산 계산 방식 SSOT = SETTLEMENT_MODULE §13 (2026-10-15, R13)
- 결정: (1) `payout.first_payout_70` = 묶음마다 70% 사사오입 합 — 윙 묶음 = **구매확정일 하루 합**(`settlement_stats._day_sums`가 하루 합 목록을 넘김), 로켓그로스 묶음 = 줄(주문). 윙 최종액 30% = 그 달 합계 − 하루 합마다 70% 의 합. 2026-10-06 아카이브 줄의 '윙70%=전체×70%사사오입·윙 최종액 30%=주합계 기준' 규칙을 대체. (2) 쿠팡 정산 계산 방식 전체(입금 네 갈래·윙 지급·로켓그로스 정산 줄 공식·마이너스일·이월·통장 다리·혼동 금지) SSOT = `designs/SETTLEMENT_MODULE.md` §13(D-065 실측 규칙을 정책으로 정리).
- 근거: 앱 수집 전 계정(output/정산 + 증빙 수집분) 윙 70% 지급 76건 실측 비교 — 하루 합 사사오입 75건 일치 vs 기간 전체×70% 56건(웰빙곳간·고로켓·DW·니코에이블에서 1원 차이). 니코에이블 9/18 정산대상 458,973 → 쿠팡 지급 명세 321,282(전체×70%=321,281). 불일치 1건 = 웰빙곳간 3/23(같은 날 지급 2건 — 원인 미확인). 재현: 핀 `payout_amount(MP_1ST,[17622,222411,148185,70755])==321282` 실패 → 수정 → 통과·기존 앵커 `[337770]==236439`·P9 집계 시험 유지.
- 버린 대안: 기간 전체×70%(56/76) · 주문 줄마다(윙은 맞지 않음 — 주문별 반올림은 10/15 179,460 건 등 다수 불일치) · 파이썬 `round`(짝수 맞춤).
- 영향 범위: `src/coupang_analytics/payout.py`(first_payout_70·payout_amount 설명) · `src/coupang_analytics/settlement_stats.py`(`_day_sums` 신설·윙 주정산·`_final_lines`) · `tools/verify_settlement_offline.py`(P2 핀) · `designs/SETTLEMENT_MODULE.md` §3 금액 반올림·§13. 계산값은 예측·대조용(정산 집계 '지급액 검산' 시트) — 실지급은 쿠팡 값이 정본이라 정산서 금액은 불변. **HQ 포팅 대상**.
- 상태: ACTIVE

### D-067 [SETTLE_EVIDENCE_ALL] 정산 증빙 원본 전체 받기 = `정산다운로드.exe evidence`(전 위탁계정·계정별 폴더·이어받기) · 받을 파일 목록 SSOT = SETTLEMENT_MODULE §14 (2026-10-15, R13)
- 결정: 정산다운로드에 `evidence` 명령 추가 — 계정마다 `--out` 아래 `증빙_{사업자}_쿠팡원본\`에 (1) 정산 원본(run --originals 와 같은 파일·**증빙 전용 요청 기록** `output\정산\증빙\_요청기록.json` 이라 매일 정산에 '받음'인 파일도 원본을 다시 받음) (2) 정산 줄 없는 주의 비용 리포트(정산 줄 '미납 CFS' 기간 → 묶음 키 요청) (3) 판매분석 기간별·상품별 월별 원본(누락 검사) (4) 우대수수료 환급 엑셀 (5) 윙 지급 명세 PDF (6) 월렛 거래내역 PDF (7) 로켓그로스 광고비·밀크런 PDF (8) 광고센터 월별 광고비 정산 보고서 PDF. 단계마다 정상/실패/없음 기록(차단만 그 계정 중단)·`_증빙목록.csv`·`_수집결과.json`·모두 정상이면 `_수집완료.json`(다시 실행 시 건너뜀·`--redo` 로 다시). 운용 PC 실행 파일 `정산증빙_전체받기.bat`(2026-01-01~오늘·17:30 멈춤). 받을 파일·방식·내용 표 = `designs/SETTLEMENT_MODULE.md` §14.
- 근거: 소유자 2026-10-15 "운용PC에서 동일 자료를 계정별로·모든 계정·나중에 다시 받는 일 없게 최대한 모든 자료", "그동안 변경된 내용을 적용해서 다운받아야 할 파일과 방식, 내용 최종 점검". 각 단계 = 같은 날 니코에이블에서 실제로 받히고 통장 대사(D-065)에 쓰인 방식 그대로(임시 스크립트 → 모듈 `settlement_evidence`·`settlement_evidence_web`). 핀 P32(사업자 폴더·월 구간·정산 줄 없는 주=니코에이블 5/11~17·누락 검사·완료 표시·이어받기) 통과. **라이브 시험(니코에이블 2026-09-01~10-15·4회)**: 1회차에서 윙 원본 생성 지연(5분+)·환급 엑셀 생성 전 받기(400)·숨은 검색 버튼·광고센터 창 닫기 실패 → 메뉴 뒤 마저 받기·환급 요청/받기 분리(FINISHED 확인)·보이는 버튼·안내 창 X 일반화 + 동의 창 제목 정확 일치(배너 문장 오인 실측)·월렛 안내 창 닫고 재시도·단계 이어받기로 고침 → 최종 전 단계 정상·`_수집완료.json`·환급 엑셀 지급일 합 = 통장(27,342·24,342·93,742).
- 버린 대안: 매일 정산(watch)에 증빙 단계 끼워 넣기(야간 시간·차단 위험 증가 — 1회성 전체 받기 + 이어받기로 충분) · 앱 정산 기록 재사용(이미 '받음'이라 원본 재요청 불가) · 화면 캡처 PNG(쿠팡 화면 인쇄 PDF 로 대체).
- 영향 범위: 신규 `src/coupang_analytics/settlement_evidence.py`·`settlement_evidence_web.py` · `tools/settlement_download.py`(evidence 명령·`--out`·`--redo`) · `tools/verify_settlement_runtime_offline.py` P32 · `deploy/정산증빙_전체받기.bat`·`build.bat` · `designs/SETTLEMENT_MODULE.md` §14. 매일 정산·앱 동작 불변. 계정당 약 1~1.5시간(요청 간격 45~75초). HQ 포팅 대상.
- 상태: ACTIVE

### D-068 [LOGIN_PW_REFUSED_SAME_DAY] 쿠팡이 거부한 비밀번호 = 그날 다시 넣지 않음(앱·정산 공통) · 2단계 인증 화면 인식 · 로그인 실패 사유를 통합판매현황·실행 요약에 표시 (2026-10-16, R13)
- 결정: (1) 로그인에서 '아이디 또는 비밀번호가 다릅니다' 등으로 거부된(classify 'error') 비밀번호 값은 **그날 다시 넣지 않는다** — 앱 재실행·'오늘 처음(다시)'·재부팅 복구·정산 프로그램 모두(`pipeline_sales._fresh_login` 한 경로). 다음 날 다시 시도. 관리대장(정산은 계정 파일)에서 **고친 값**은 거부된 값이 아니므로 그날 바로 시도. 대장 줄마다 비번이 다른 계정(D-012)은 거부된 값을 건너뛰고 다음 값만 넣음. 기록 = `output/_로그인실패.json`(계정·날짜·사유·거부된 값의 **HMAC 지문** — 키는 이 PC credstore(DPAPI)·비밀번호 원문 저장 없음). (2) 2단계 인증 '방법 선택' 화면(xauth·'2단계 인증' 글자, 인증번호 칸 없음)을 `classify_login` 이 `otp` 로 판정 → 기다리지 않고 바로 건너뜀(위탁계정은 사람 인증 불가). (3) 그날 실패 사유(로그인 비밀번호 오류·2단계 인증 필요·로그인 차단·로그인 미완료)를 결과 파일 통합판매현황 계정 소계 줄에 `소계 — ⚠ 사유`로, ① 끝 로그에 계정별 사유로 표시하고 완료 줄은 '수집 성공 N/M · 비밀번호 오류 K'(비밀번호 오류 계정을 성공에서 뺌).
- 근거: 소유자 2026-10-16 "로그인 재시도후 오류이면 해당일 재시도 하지 않음", "결과시트 판매현황에 '로그인 비밀번호 오류'와 같이 간단히 사유 명시". 실측 output(22)·capture.zip: 같은 틀린 값 재제출 plan_it 26회(09-28~)·gyi0101 13회(10-13~·앱 5+정산 8)·dalbong1849 첫 값 14회 — 실행 안 재시도만 막혀 있었음. 캡처 259건 분류: lslfgh 59건·nihaoha 16건·nicoable 2건 = 전부 '2단계 인증(휴대폰번호로 인증하기)' 화면인데 앱은 '인증 전환 중'으로 보고 매번 시간초과 후 '세션만료+Akamai차단'으로 보고(사실과 다름). 10-15 요약 '성공 27/28·실패 하성진 1'인데 플랜잇·유라이프도 미수집. 재현: 핀 D2(같은 날 2회차 자동입력 1회 기대) 옛 코드 실패 → 수정 → 통과 · 핀 E2(실측 화면 글자 → otp) · 판매현황 T4 사유 표시.
- 버린 대안: 같은 값만 영구 금지(다음 날 계정 상태가 풀려도 시도 안 함 — 소유자 '해당일'과 다름) · 그날 계정 전체 금지(대장 비번을 고쳐도 다음 날까지 못 받음) · 비밀번호 sha256 저장(output 폴더가 분석용으로 밖에 보내짐 — 약한 비번 역산 위험 → PC 전용 키 HMAC).
- 영향 범위: 신규 `src/coupang_analytics/login_today.py` · `pipeline_sales.py`(_fresh_login·_ensure_login·_resolve_login_failure) · `browser.py`(classify_login 2단계 화면) · `pipeline.py`(① 끝 사유 로그·완료 줄) · `workbook_sales.py`(소계 사유) · `tools/pin_login_ranks.py` 핀 D2·E2 · `tools/verify_sales_summary_offline.py` T4. 정산 프로그램은 같은 `_ensure_login` 을 써서 자동 적용. HQ 포팅 대상.
- 상태: ACTIVE · '그날(달력 날짜)' 부분은 SUPERSEDED by D-123(거부 시각부터 24시간)

### D-069 [REGISTRY_CHECK_PENDING_RENAME] 원장 상품명 변경 '확인필요' 중 = 쿠팡확인을 옛 이름 줄에 기록 (2026-10-16, R13)
- 결정: 원장 상품이력에 승인·반려 안 된 '상품명변경'(확인필요)이 있으면, 대장 새 이름으로 계산한 쿠팡확인·확인일을 **원장 옛 이름 줄**에 쓴다(`registry_gsheet._pending_renames` → `_plan_checks` 별칭). 이름 변경 보류·승인 규칙(LEDGER_REGISTRY §6)은 그대로 — 승인하면 그 줄이 새 이름으로 이어진다.
- 근거: 소유자 2026-10-16 "원장 쿠팡확인 매일 2건 빠짐 — 원인 분석해서 수정". 실측(원장 백업 261015_191049): 상품이력 #92 '코골이 방지 기구'→'코골이 방지 기구('·#105 '팔찌경보기'→'팔찌경보기 JN104' 가 2026-09-30부터 '확인필요' → 새 이름 줄이 원장에 없어 매 실행 '원장에 없는 대상 2건'·쿠팡확인 미기록. 앱 파싱·원장 파싱 모두 대장 이름을 같게 읽음(파서 차이 아님). 재현: R17b 옛 코드 0줄 → 수정 → 1줄·무결성 유지.
- 버린 대안: 확인필요를 자동 승인(다른 상품끼리 이력 섞일 위험 — §6 원칙 위배) · 새 이름 줄을 임시로 추가(승인 전 중복 줄·무결성 깨짐).
- 영향 범위: `src/coupang_analytics/registry_gsheet.py`(write_coupang_check·_plan_checks·_pending_renames) · `tools/verify_registry_offline.py` R17b. ⚠ 사람 조치: 원장 상품이력 #92·#105 승인/반려(승인 전엔 원장 상품명이 옛 이름). HQ 포팅 대상.
- 상태: ACTIVE

### D-070 [REGISTRY_AUTO_RENAME_JUDGE] 원장 상품명 변경 의심 = 사람 승인 대신 자동 판단(글자 규칙 → 쿠팡 상품번호 → AI) · 남은 확인필요도 자동 처리 (2026-10-16, R13)
- 결정: 대장 상품명이 바뀐 것으로 보이는 쌍(유사도 쌍·기존 `확인필요`)을 앱이 자동 판단해 바로 반영한다 — ①띄어쓰기·대소문자·괄호·문장부호만 다름 = 같은 상품 ②앱 매칭 고정 기록에서 두 이름의 VID 겹침 = 같음/안 겹침 = 다름 ③AI(OpenAI) 같음/다름/모름. 같음 = 이름변경(이력·등록일 이어짐·이력 비고에 근거) · 다름 = 옛 줄 관리중단 + 새 줄 신규 · 모름·AI 장애만 `확인필요`로 남기고 다음 실행에서 다시 판단. 자동 처리한 기존 `확인필요` 줄은 확인상태(승인/반려)·확인자 `AI 자동`·확인일을 채운다. 사람이 넣은 승인/반려가 있으면 그게 우선. 계정아이디 변경 의심은 사람 승인 유지. LEDGER_REGISTRY §6 '자동 병합 금지'를 이 범위에서 대체(근거를 남기는 판단 병합).
- 근거: 소유자 2026-10-16 "이런 유사건은 AI 가 판단해서 보정하고 자동 진행하도록 — 내가 승인과 보류를 인지하지 못해". 실측: #92('코골이 방지 기구'→'코골이 방지 기구(')·#105('팔찌경보기'→'팔찌경보기 JN104')가 9-30부터 16일간 미처리 → 쿠팡확인 매일 누락(D-069). 두 쌍 모두 이름 변경 전후 VID 동일(94632081597·96117125727) = 같은 상품이었음. 시험 R17c: 글자 규칙 무보류(AI 호출 없음)·AI 같음 이름 이어짐·AI 다름 관리중단+신규·AI 장애만 확인필요 → 다음 실행 자동 승인·원래 줄 표시·재처리 없음·무결성.
- 버린 대안: 확인필요 유지 + 알림(소유자가 승인 흐름 자체를 원치 않음) · 무조건 같은 상품으로 병합(다른 용량·색상 상품 이력 섞임) · 무조건 다른 상품(이름 오타 수정마다 이력 끊김).
- 영향 범위: 신규 `src/coupang_analytics/registry_judge.py` · `registry.py`(sync judge) · `registry_core.py`(_Run.judge) · `registry_apply.py`(_rename_row·_judge_pairs) · `registry_rename.py`(_auto_resolve_pending·_apply_rename note) · `registry_gsheet.py`(run_sync judge·_mark_auto_resolved) · `ui/registry_ui.py`(rename_judge — OpenAI 키·매칭 고정 기록) · `tools/verify_registry_offline.py` R17c · `designs/LEDGER_REGISTRY.md` §4 표·§6-1. HQ 포팅 대상.
- 상태: ACTIVE (부분 SUPERSEDED by D-071 — 계정아이디 사람 승인 유지 부분)

### D-071 [REGISTRY_AUTO_ACCOUNT_JUDGE] 원장 계정아이디 변경 의심도 자동 판단(원장·대장 자료) — 사람 승인 대기열 0 (2026-10-16, R13)
- 결정: 사업자명·대표자명이 같은 1:1 계정아이디 변경 의심 쌍(새 쌍·기존 `확인필요`)을 앱이 판단해 바로 반영 — ①대소문자·기호만 다름 = 같은 계정 ②두 계정 상품이 절반 이상 같음 = 같은 계정·상품이 다름 = 다른 계정 ③한 쪽이 상품 없음 → 비밀번호 같고 아이디 비슷(유사도 ≥0.75·오타 수정) = 같은 계정, 그 밖 = 다른 계정. 같은 계정 = 원장 줄 전부 새 아이디로 이동(등록일·이력 이어짐·이력 비고 근거) · 다른 계정 = 옛 계정 관리중단 + 새 계정 신규(근거가 부족할 때 이력을 섞지 않는 쪽). 판단 불가 경우가 없어 보류 0. 기존 확인필요는 원래 줄 확인상태·확인자 `AI 자동`·확인일 채움(D-070 과 같은 표시). D-070 의 '계정아이디는 사람 승인 유지'를 대체.
- 근거: 소유자 2026-10-16 "계정아이디 변경 의심도 자동으로 — 반영해줘"(D-070 보고에 이어). AI 는 계정아이디 판단 재료가 없어 원장(상품·비밀번호)·대장 자료로 판단. 실측: 원장 계정이력 확인필요 0건(사례 없음). 시험 R9b: 상품 같음=줄 이동·상품 다름=관리중단+신규·판단 없이 생긴 확인필요(오타·비번 같음) → 다음 실행 자동 승인·무결성.
- 버린 대안: 사람 승인 유지(소유자가 대기열을 인지 못함 — D-070 근거) · AI 판단(아이디 문자열만으로는 근거 없음) · 비밀번호만으로 같은 계정 판정(담당자가 여러 계정에 같은 비번을 씀).
- 영향 범위: `src/coupang_analytics/registry_judge.py`(judge_account) · `registry_rename.py`(_judge_account_pairs·_move_account·_auto_resolve_pending 계정 분기) · `tools/verify_registry_offline.py` R9b · `designs/LEDGER_REGISTRY.md` §4 표·§6-1. 앱 경로(registry_ui.sync — judge 있을 때)만 자동, 수동 도구는 기존 보류. HQ 포팅 대상.
- 상태: ACTIVE (전역 'AI 매칭' 규칙의 예외로 규칙 판단 유지 — 소유자 확인 D-179)

### D-072 [COMPANY_STOCK_MATCH] 회사보유재고 매칭 = 상품명 일치 → 괄호 앞/안·색상별 줄 → 모델번호 → AI (2026-10-16, R13)
- 결정: 재고현황 → 관리대장 '회사보유재고'·계정목록 표기 매칭을 '동일 상품명(공백·대소문자 무시)'에서 단계 판단으로 넓힌다 — ①상품명 일치 ②대장 이름의 괄호 앞·괄호 안 각각이 재고현황 이름(또는 재고현황 괄호 앞 이름)과 일치 — 재고현황에 색상별 줄이 있으면 대장 괄호 안 색상과 같은 줄, 없으면 그 상품 줄 전부를 '(색상) 창고 , 수량개 / …'로 ③모델번호(영문+숫자·숫자 앞 0 무시) — 대장 이름, 없으면 ① 매칭된 쿠팡 상품명에서 — 재고현황에 그 번호 상품이 **하나뿐일 때만** ④AI(OpenAI) — 이름 비슷한 후보 6개 중 **같은 모델·같은 용량**만(번호 한 글자 달라도 다른 상품·브랜드 표기 차이는 같음), 결과는 `output/_회사재고매칭.json`에 저장(고른 이름이 재고현황에 있는 동안 재사용·'없음'은 그날만). 계정목록 표기(apply_to_workbook)는 규칙+저장 결과만(AI 호출 없음). AI 장애 = 로그 후 그 상품 기존값 유지.
- 근거: 소유자 2026-10-16 "재고현황에 대해서는 수정을 안 했어"(10-16 로그 분석 후). 실측: 10-16 05:10 회사재고 미매칭 40줄 중 21줄이 재고현황에 있음(괄호 설명 18·모델번호 표기 3) — 9-30 기능 도입 후 매칭 47~49줄에 머묾. 함정 실측: JK8602↔JK8601·M28↔M10·BG002↔BG001(유사도 0.78~0.91 이지만 다른 모델) → 유사도 매칭 금지·번호 일치만. 대장 오타 'HS0300' = 쿠팡 상품명·재고 'HS0030'. 미리보기(실데이터·쓰기 없음): 규칙만 74줄(미매칭 19) → AI 포함 76줄(테아닌·마시는 알부민 추가, 함정 3개 미선택)·미매칭 17 = 재고현황에 없음. 공용 openai_ask 가 'L번호' 줄 수로 응답 한도를 정해 처음엔 잘림 → 같은 형식으로 맞춤.
- 버린 대안: 이름 유사도 최고값 채택(번호 다른 모델 오매칭) · 대장 상품명 정리 요청(담당자 입력 습관·괄호=노출명 규칙 D-046) · 재고현황 쪽 이름 바꾸기(회사 재고 시트는 읽기 전용).
- 영향 범위: 신규 `src/coupang_analytics/company_stock_match.py` · `company_stock.py`(_ledger_rows 계정ID·apply_to_workbook·_match_rows·write_company_stock·run_company_stock 선택 인자) · `pipeline_gsheet.py`(push_company_stock·inject_company_stock — 쿠팡 상품명·OpenAI 키·저장 결과) · `tools/verify_registry_offline.py` R21b · `tools/pin_l1_contract.py` · `designs/DESIGN.md` 회사보유재고. HQ 포팅 대상.
- 상태: ACTIVE (부분 SUPERSEDED by D-157 — 괄호·색상·모델번호 규칙은 확정 → 후보로만)

### D-073 [SETTLE_WALLET_AUTO_WITHDRAWAL] 로켓그로스 월렛 인출 = 수동(WITHDRAWAL)·자동(AUTO_WITHDRAWAL) 둘 다 (2026-10-16, R13)
- 결정: 정산 집계의 '계좌 입금'(RG 월렛 인출·대표계좌 입금 합계)과 검증 '월렛장부'(입금−인출 ↔ 잔액)에서 월렛 이벤트 `AUTO_WITHDRAWAL`(자동 인출)도 인출로 센다(`settlement_verify._WITHDRAW`).
- 근거: 소유자 2026-10-16 "정산파일 모두 내려받았음 — 계정별 정산 내역 분석·정리" 중 발견. 실측 output(23) 검증자료 27계정 월렛 내역: 자동 인출을 빼면 효성 101,654,006·웰빙곳간 290,571,027·에벤에셀 299,077,259·디프 1,323,333,867 등 14계정이 '인출 0/부족'으로 월렛장부 '다름'·대표계좌 입금 과소. 자동 인출 포함 시 26계정 입금−인출=쿠팡 잔액 원 단위 일치(벅스만 −19,950 — 미확인). 재현: P21 자동 인출 시험 옛 코드 실패(인출 0) → 수정 → 통과.
- 버린 대안: 잔액으로 역산(인출 시점·월별 대표계좌 입금을 알 수 없음).
- 영향 범위: `src/coupang_analytics/settlement_verify.py`(_WITHDRAW·rg_wallet·_inflow_wallet) · `tools/verify_settlement_runtime_offline.py` P21 · `designs/SETTLEMENT_MODULE.md` §13. 정산 원본·지급 계산 불변(통장 대사 표시만). HQ 포팅 대상.
- 상태: ACTIVE

### D-074 [SETTLE_WING_MONTH_BOUNDARY] 윙 최종액↔주정산 중복 제외 = 정산예정일 + 구매확정일이 주정산 파일 기간 안일 때만 (2026-10-16, R13)
- 결정: 정산 집계(`settlement_stats._order_rows`·지급액 검산 `_final_lines`)가 윙 최종액 파일 줄을 빼는 조건을 '같은 정산예정일의 주정산 파일이 있음'에서 '같은 정산예정일 **이고** 구매확정일이 그 주정산 파일 기간 안'으로 좁힌다(`_weekly_windows`·`_in_weekly`). 날짜 없는 줄(배송비 등)은 옛 규칙 유지. 다운로드 계획(월 안 주정산은 월별 파일로 대체)은 그대로.
- 근거: 소유자 2026-10-16 "8월 누락 원인 조사 → 1번 수정". 실측 output(23): 웰빙곳간·로움·hk66597582·휴라엘·유라이프 8월 윙 매출이 쿠팡 매출내역보다 13,460·38,460·6,000·13,900·29,360 적음 = 각 계정 8/31 구매확정분과 원 단위 일치. 쿠팡 지급 내역 9/29 정산일 = '8/31~8/31'(정산대상 웰빙곳간 11,890·로움 33,975·hk 5,802 = 검증 정산대상 차이와 일치)·'9/1~9/6' 두 줄인데 받은 주정산 파일은 9/1~9/6 뿐(8/31 은 8월 최종액으로 대체) → 옛 규칙이 8/31 줄을 양쪽에서 뺌. 월 경계가 주 중간인 달마다 반복·자가 회복 안 됨. 재현: P10 옛 코드 실패(8/31 빠짐) → 수정 → 통과(합계·월 귀속·검증 월합·9/29 '8/31' 70% 8,323 = 쿠팡 지급액). 실데이터 재집계: 윙판매 다름 25→9·윙부가세 8→3(남은 것 = 노바네스트 파일 없음).
- 버린 대안: 8/31 주정산 파일도 받기(다운로드 계획 변경 — 같은 주문 두 파일·이중 집계 위험 증가) · 최종액 파일만 쓰기(주정산 파일이 있는 최근 주의 70% 지급 검산 불가).
- 영향 범위: `src/coupang_analytics/settlement_stats.py` · `tools/verify_settlement_offline.py` P10 · `designs/SETTLEMENT_MODULE.md` §13. 위탁정산서·계약자 정산금액(정산 집계 기반)이 그 계정 8/31 몫만큼 늘어남. HQ 포팅 대상.
- 상태: ACTIVE

### D-075 [SETTLE_MONTHLY_CYCLE] 월정산 계정 정산 파일 받기 — 윙 'M'·로켓그로스 'MONTHLY' = 주정산과 같은 요청(그 달 전체) (2026-10-16, R13)
- 결정: 윙 정산주기 `M` = '월정산'(100%) — 주정산과 같은 엑셀 요청(revenue-detail·구매확정일 그 달 1일~말일), 로켓그로스 `MONTHLY` = '월정산' — 같은 request-download(settlementGroupKey·리포트 9종). 지급액 검산 = 윙 PAYOUT_MP_MONTHLY·로켓그로스 PAYOUT_RG_MONTHLY(100%). 'M'·'MONTHLY' 를 건너뛰고 '확인 필요'로 남기던 D-010/D-052 의 해당 부분을 대체.
- 근거: 소유자 2026-10-16 "노바네스트 로그인 했어"(소유자 Chrome 로그인 → Claude 화면 확인). 실측: 윙 정산현황 '월정산' 줄(정산일 2026-09-21·지급비율 100%·구매확정기간 2026-08-01~08-31·최종지급액 350,275 = 쿠팡 매출내역 8월 397,500−47,225)의 '엑셀 다운로드 요청' = 같은 주소 `/tenants/msf/wing/api/common/excel/revenue-detail/request` → 다운로드 목록 '[중개] 정산현황 주문 상세 내역'·'구매확정일:2026-08-01 - 2026-08-31'·FINISHED. 로켓그로스 정산현황 '월정' 줄(정산일 2026-09-30·매출인식 08-01~08-31·100%·9,263)의 엑셀 다운로드 = 리포트 9종 같은 메뉴·`/tenants/rfm/v2/settlements/request-download/api` → 목록 '판매수수료 리포트' 생성 중. 시험 P1·P29 기대 갱신·P10 월정산 100%.
- 버린 대안: 계속 건너뜀(노바네스트 윙 매출 14건 '다름'·정산 파일 0) · 월정산 전용 별도 다운로더(같은 요청이라 불필요).
- 영향 범위: `src/coupang_analytics/settlement_wing_api.py`(_WING_KIND·_RG_KIND) · `settlement_stats.py`(payout_lines 월정산) · `tools/verify_settlement_runtime_offline.py` P1·P29 · `tools/verify_settlement_offline.py` P10. 운용 PC 재배포 후 노바네스트 대기 6건 → 다운로드. HQ 포팅 대상.
- 상태: ACTIVE

### D-076 [SETTLE_LOGIN_LEDGER_PW] 정산 로그인 비밀번호 = 앱과 같은 관리대장 값 먼저 · 관리대장에 없는 계정만 정산 계정 파일 (2026-10-16, R13)
- 결정: 정산 프로그램(watch·run·evidence 공통 `session`)의 로그인 비밀번호를 `settlement_accounts.login_passwords` 로 정한다 — ①앱이 관리대장을 읽을 때마다 이 PC 암호 저장소(credstore·DPAPI)에 계정ID별로 저장한 값(관리대장 값) ②정산 계정 파일 값. 둘 다 있고 다르면 관리대장 → 파일 순서로 최대 2개(앱 ①과 같은 `_login_with_candidates` — '비밀번호가 다릅니다'일 때만 다음 값·D-012 상한·그날 거부된 값은 D-068 이 다시 안 넣음). 관리대장에 없는 계정(정산만 하는 계정)은 파일 값. 로그에 출처만 표기(값 없음). 정산 대상 계정 목록은 그대로 정산 계정 파일.
- 근거: 소유자 2026-10-16 "정산 파일 다운로드시 로그인은 앱에서처럼 관리대장의 계정과 비번을 이용해서 로그인". 실측: 정산 계정 파일과 관리대장 비번이 따로 관리돼 정산만 실패하는 계정이 생김(gyi0101 정산 거부 8회 — 앱과 별개 제출). 시험 P33(대장 우선·다르면 대장→파일·대장에 없으면 파일·값 노출 없음).
- 버린 대안: 정산 계정 목록도 관리대장으로(디프·디프픽 등 대장에 없는 정산 계정이 빠짐) · 계정 파일만(소유자 요청과 다름).
- 영향 범위: `src/coupang_analytics/settlement_accounts.py`(login_passwords) · `tools/settlement_download.py`(session·_login) · P33. ⚠ 운용 PC 는 앱이 관리대장을 한 번 읽어야 저장소에 값이 생김(18:00 실행·앱 시작 자동 로드). HQ 포팅 대상.
- 상태: ACTIVE (부분 SUPERSEDED by D-103 — 정산 계정 파일 값·계정 목록 출처, account_source=file 일 때만 옛 파일)

### D-077 [STATEMENT_FAST_SETTLEMENT] 위탁정산서 = 빠른정산(셀러월렛) 있으면 머리 표시 + 'F. 빠른정산 내역' (2026-10-16, R13)
- 결정: 위탁정산서(D-059 양식)에 빠른정산이 있는 사업자만 ①머리 '빠른정산: 사용 — 먼저 받은 원금 N원' ②E '[참고] 빠른정산 상환 차감'(옛 '선정산 상환' = 로켓그로스만 → 윙 '빠른정산 계좌인출액' + 로켓그로스 ArFactoring) ③'F. 빠른정산(셀러월렛) 내역' — 정산월별 윙·로켓그로스 상환(= 먼저 받은 원금)·받는 곳(하나은행 셀러월렛 계좌·체크카드, 대표계좌 아님)·수수료(하나은행 선공제·셀러월렛/하나은행 내역 확인)·실제 받은 돈(E 쿠팡 지급 계 + F 원금, 수수료 전). 확정 정산금액(C)·총 정산금액은 그대로(받는 시점·경로만 다름). 전체 요약 열 '선정산 상환 차감' → '빠른정산 상환(윙+로켓그로스)'.
- 근거: 소유자 2026-10-16 "빠른정산 건이 있는 경우에는 정산양식에 표기해줘". 조사 = `docs/COUPANG_WING_HELP_KB.md` §1-14. 실측(output(23) 재집계): 원더풀리 192,765,047·유라이프 95,941,464·글로벌셀러 82,662,262·스마트플라자 26,013,859 = 합계 397,382,632. 위탁정산서_20261016 30곳 재생성·검산 ①−②=③·③+④=⑤ 일치.
- 버린 대안: 빠른정산 원금을 정산금액에서 빼기(쿠팡 정산 기준과 달라짐 — 받은 경로만 다름) · 수수료 추정치를 금액으로 넣기(하나은행 실제 내역 없음 — 안내만).
- 영향 범위: 정산서 스크립트 `output/_분석_261013/정산스크립트/business_statements.py`(git 밖·분석 작업 스크립트 — read_stats 빠른정산·_consignor_fast·COLS) · 결과 `D:\토탈셀러\쿠팡 정산 자료\위탁정산서_20261016\`. HQ 정산서 포팅 시 같은 규칙.
- 상태: ACTIVE (부분 SUPERSEDED by D-126 — 표시 위치: 머리 '빠른정산: 사용'·E '[참고] 빠른정산 상환 차감'·'F. 빠른정산 내역' → G 표 '빠른정산 상환 −Z'·'빠른정산으로 먼저 받은 돈 +Z' 두 줄 + 비고 '입금 완료 중 빠른정산'·금액 원천(윙 빠른정산 계좌인출액·로켓그로스 ArFactoring)은 그대로)

### D-078 [SETTLE_FORECAST_RECORD] 정산 예정 = 쿠팡이 미리 만든 정산 줄을 수집일별로 기록 → 정산일 지나면 실제와 대조 → 확인 후 정산서 적용 (2026-10-16, R13)
- 결정: 정산 조회(watch·run 공통 `read_events`)가 기존 '오늘까지' 조회에 더해 오늘 뒤 70일 구간을 조회해, 쿠팡 정산현황의 앞으로의 정산 줄(윙 정산대상·공제·예정 최종지급액 / 로켓그로스 지급대상·광고비·밀크런·빠른정산·물류비·보상·판매조정·예정 최종지급액)을 `output/정산/정산예정기록.jsonl` 에 수집일별로 쌓는다(지난 정산 = 기존 지급 내역 그대로·받을 파일 계획 불변·미래 구간 실패는 그 계정 정산을 막지 않음). 정산 집계에 '예정 정확도'(정산일 지난 줄: 예정 ↔ 실제 칸별·며칠 전 예정)·'예정 정확도 요약'(미리 본 일수별 최종지급액 일치율) 시트. **정산서 '정산 예정액'은 정확도가 확인될 때까지 바꾸지 않는다**(소유자 지시 '분석 후 적용').
- 근거: 소유자 2026-10-16 "로켓그로스 예정액 개선 진행 — 정확한 금액인지 분석 후 적용·광고비·물류비 등 차감해야 하는 것도 반영해 최대한 100% 맞도록". 백테스트(output(23)): 윙 예정(매출내역 정산대상) 6~8월 62계정월 원 단위 일치(노바네스트 제외) · 로켓그로스 추정(부가세×비율) 7월 합계 +10.1%·8월 −2.5%·계정별 −28%~+103% → 추정 대신 쿠팡 계산값 필요. 노바네스트 화면: 미래 정산 줄(2026-11-03·463원) 존재 확인. 기존 자료엔 미래 줄이 없음(조회 끝 = 오늘·정산캘린더엔 금액 없음) → 수집부터. 시험 P34.
- 버린 대안: 추정식 보정(계정별 오차 큼·공제 반영 불가) · 바로 정산서 적용(정확도 미검증).
- 영향 범위: 신규 `src/coupang_analytics/settlement_forecast.py` · `settlement_store.py`(FORECAST) · `settlement_stats.py`(write_stats forecast 시트) · `tools/settlement_download.py`(_read_forecast·_save_amounts·cmd_stats) · P34. 계정당 조회 약 +6회(윙·로켓그로스 각 미래 3달). 다음 단계 = 정산일이 지나며 쌓인 '예정 정확도'로 공제 반영 규칙 확정 → 정산서 적용(D-번호 새로). HQ 포팅 대상.
- 상태: ACTIVE (부분 SUPERSEDED by D-081 — '정산서 정산 예정액은 정확도 확인까지 바꾸지 않음' → 로켓그로스 ④ 미정산 = 정산현황 예정 줄 정산대상)

### D-079 [LEDGER_HEADER_VARIANTS] 관리대장 개편 헤더 '대표자 (사업자)'·'상품명(관리상품명, 노출상품명)' 수용 · 대표자 = 괄호 앞 이름 · 플랜잇 삭제 (2026-10-19, R15)
- 결정: 대장 헤더 비교 이름을 `input_list._header_name` 한 곳에서 맞춘다 — 괄호 앞이 '상품명'이면 '상품명', '대표자'면 '대표자명'(그 밖 헤더는 그대로). 공통 헤더 탐색 `_find_header_row` 가 쓰므로 앱 파싱·그로스 재고 역기록·회사보유재고·원장이 함께 읽는다. 대표자 값은 `_rep_name` = 한 줄 → 괄호 앞 이름('송창호⏎(웰빙곳간)' → '송창호', 괄호 앞이 비면 한 줄 전체) — 앱(`_parse_grid`)·원장(`registry_model.parse_ledger`) 공통. 상품명 칸 = '관리상품명⏎(노출상품명)' → 블록 기준 = 첫 줄(관리상품명), 칸 전체 문구 = AI 매칭 근거(D-046 그대로). 플랜잇(plan_it) 대장 줄 삭제 = 소유자 의도 → 기존 규칙대로 다음 실행에 완전 삭제.
- 근거: 소유자 2026-10-19 "대표자 헤더는 대표자(사업자)로 구성됨 → 수정", "상품명 → 상품명(관리상품명, 노출상품명) 변경", "플렌잇은 삭제". 실측(관리대장 10-19 읽기): 옛 코드 = '누락 필수 컬럼: 상품명'으로 대장 전체 읽기 실패(18:00 무인 중단 원인) · 헤더만 '대표자 (사업자)'였을 때 대표자 28계정 전부 빈칸·lslfgh 시트 이름 '하성진'→'lslfgh'. 수정 후 실제 대장 = 계정 28·상품 89·오류 0·대표자 빈칸 0·lslfgh='하성진'·회사재고 Y열·그로스 재고 Z열 인식. 핀 `t1_ledger_header_variants` 재현 실패 → 수정 → 통과 · 게이트 14종 초록.
- 버린 대안: 담당자에게 헤더 되돌리기 요청(소유자가 새 구성 확정) · 헤더 전부 괄호 제거 비교(그로스 재고 (…) 등 각자 규칙과 충돌 위험 — 상품명·대표자만).
- 영향 범위: `src/coupang_analytics/input_list.py`(`_header_name`·`_rep_name`·`_find_header_row`·`_parse_grid`) · `src/coupang_analytics/registry_model.py`(대표자 값) · `tools/verify_offline.py` 핀. HQ 포팅 대상(대장 헤더 형식). 옛 '대표자명'·'상품명' 헤더도 그대로 동작.
- 상태: ACTIVE

### D-080 [ACCOUNT_RENAME_KEEPS_HISTORY] 대장 사업자명 변경 = ① 수집 전에 일원화 · 같은 상품은 이력 합침(빈 칸만·옛 키워드 복원) · 구글 옛 이름 잔재 자동 정리 · 빈 시트 반영 400 수정 (2026-10-19, R16)
- 결정: (1) `run_full` 이 직원 키워드 역머지 직후·① 수집 전에 `_consolidate_renamed_accounts` 를 돌려(목차 로스터보다 먼저) 옛 시트를 새 이름으로 바꾼다 — 실행 끝 일원화는 그대로 두되 앞 결과(`early_renamed`)를 구글 정리 목록에 합친다. (2) `merge_account`(dst 있음) = `merge_history_from` — 같은 상품(이름 같음 또는 VID 겹침)은 dst 빈 칸만 옛 값으로 채우고(dst 값 우선) 옛 키워드를 추가(동결 키워드 복원·제거 없음), dst 에 없는 상품은 블록째 복제. 합친 상품 수를 반환해 일원화 로그·구글 정리 목록이 빠지지 않게. (3) `push_gsheet` 가 매번 `find_renamed_orphans` 로 구글에만 남은 통계 시트(마스터 없음) 중 계정목록 계정ID 가 마스터에 있는 것을 옛 이름 잔재로 정리(계정 확인 못 하면 로그만). (4) `worksheet_to_requests` 그리드 = 고정보다 한 줄·한 칸 크게(상품 0개 시트 400 방지). (5) 복구 도구 `tools/restore_renamed_history.py`(옛 결과 파일 → 새 파일 저장·지금 없는 옛 상품은 되살리지 않음).
- 근거: 소유자 2026-10-19 "관리대장 변경으로 싱크가 맞지 않음 — 동일계정 다른 시트 분리·공란·미처리 분석, 로그 있으면 정정". 실측(운용 PC output 10-19 zip): 날짜별 결과 파일 대조로 이력 손실 6건 — 09-22 이종훈→원더폴리(8일)·10-02 백성민→케이씨메뉴팩처(17일)·10-12 봄날의햇살⏎주식회사(10일)·10-16 최문석→셀와니(29일)·안재현→피에스이(26일)·원더폴리→원더풀리(33일). 원인 코드 = 옛 merge_account 의 '같은 상품 건너뜀' + 옮긴 0개면 로그·정리 목록 없음 + ① 이 새 이름 빈 시트를 먼저 만들고 ② 가 AI 로 키워드 재선정(셀와니 손세정기 → 주방세제디스펜서). 구글 반영 실패 10-16~10-19 8회 = "You can't freeze all visible rows"(꿈꾸는아재 1행·고정 H2) → 그 뒤 시트·계정목록 동기화 중단 → 구글 결과에 옛 이름 시트 4개 잔존(최문석·안재현·원더폴리·봄날의햇살⏎주식회사)·계정목록 10.15 상태. 재현 실패 → 수정 → 통과: 시뮬 시나리오 24·`t1_merge_account`(C)·gsheet [3f]·[5] · 게이트 14종·복잡도 초록. 복구 시험: 셀와니 날짜 3→26·값 109→709, 원더풀리 3→26, 케이씨메뉴팩처 17→26 등·최근 3일 값 불변.
- 버린 대안: 실행 끝 일원화만 유지하고 병합만 고침(② 가 빈 블록에 새 키워드를 고르는 문제는 남음) · 구글 옛 시트 수동 삭제(다음 이름 변경 때 재발).
- 영향 범위: `pipeline.py`(run_full 순서) · `workbook_lifecycle.py`(`merge_history_from`·`_fill_block_history`·`_merge_target`·`_copy_product_block(other)`) · `pipeline_gsheet.py`·`gsheet_index.py`(`find_renamed_orphans`) · `gsheet_stats.py`(그리드) · `tools/restore_renamed_history.py` · 시뮬·verify_offline·verify_gsheet_offline. HQ 포팅 대상(계정 이름 변경 이력 보존).
- 상태: ACTIVE

### D-081 [SETTLE_UNSETTLED_COUPANG_ONLY] 정산서 ④ 미정산 = 쿠팡이 계산한 숫자만(추정 금지) · 로켓그로스 = 정산현황 예정 줄 정산대상 · 예정 줄에 판매액·환불·수수료·할인 칸 저장 (2026-10-19, R16)
- 결정: (1) 위탁정산서 ④(정산 예정)에는 쿠팡이 계산한 값만 넣는다 — 윙 = 매출내역 정산대상액(구매확정분, D-060 '확정' 그대로) · 로켓그로스 = 쿠팡 정산현황 **예정 줄**(D-078 `정산예정기록.jsonl`, 계정별 마지막 수집일)에서 정산 파일이 없는 판매 주마다 정산대상 = 판매액 + 환불액 − 판매수수료(VAT 포함) − 판매자할인(정산 줄 칸) · 그 칸이 없는 옛 기록 = 70% + 30% 지급대상 합 · 70% 줄만 있으면 70% 금액만('30% 줄 아직 없음' 표기, ÷0.7 안 함). 예정 줄이 없는 계정(로그인 실패)·정산 파일과 예정 줄 사이 빈 판매 기간 = **금액 없이** '자료 없음'·'확인 필요'. 구매확정(윙)·매출인식(로켓그로스) 전 판매는 쿠팡이 아직 계산하지 않았으므로 넣지 않는다. D-060 의 로켓그로스 부분(부가세×비율 '추정'·판매분석×수수료율 '실측')을 대체 — 그 코드 경로와 '실측 미정산.json' 옵션은 정산서 스크립트에서 삭제. (2) 정산 예정 기록(`settlement_forecast._KEEP`)에 로켓그로스 `totalSalesAmount`·`totalRefundedAmount`·`totalTakeRateAmountWithVat`·`totalSellerDiscount` 를 추가하고 `rg_target`·`rg_sales` 로 계산(쿠팡 칸 더하기·빼기만).
- 근거: 소유자 2026-10-19 "쿠팡 메뉴얼(도움말)에 기초하여 정산이 100% 일치되도록·추정은 안됨". 도움말: 매출 인식 = 구매확정(FAQ 132) · 매출내역 정산대상액·최종지급예정액(104) · 정산현황 정산상태 '예정'(223 — 정산차감 시 예상금액이 바뀔 수 있음) · 로켓그로스 70%/30% 지급(333). 실측(output(24)·2026-10-19): ① 정산 파일 있는 로켓그로스 70% 지급 줄 737/737 = 판매액+환불−수수료−할인이 판매수수료 리포트 정산대상과 원 단위 일치 ② 쿠팡 예정 30% 줄 = 정산대상 − 실제 70% 지급 20/20 원 단위 ③ 판매 주가 끝난 예정 값은 수집일(10-16~19)이 달라도 199/199 불변 ④ 옛 추정(부가세×비율) 9·10월 97,733,087 vs 쿠팡 예정 줄 90,097,571(+8.5%·계정별 −100%~+136%·로움 5,477,471 누락). 시험 P34(칸 저장·정산대상 22,030 = 정산 파일·칸 없으면 계산 안 함) 재현 실패 → 수정 → 통과·게이트 14종.
- 버린 대안: 판매분석 판매액 × 계정 비율(9/7 주 백테스트 합계 +1.1%·작은 계정 +93%~+124% — 추정) · 70% ÷ 0.7(주문별 사사오입이라 역산이 원 단위로 안 맞음) · 예정 줄 없는 계정을 부가세로 채우기(추정).
- 영향 범위: `src/coupang_analytics/settlement_forecast.py`(_KEEP·rg_target·rg_sales) · `tools/verify_settlement_runtime_offline.py` P34 · 정산서 스크립트 `output/_분석_261013/정산스크립트/business_statements.py`(git 밖 — `_settled_weeks`·`_rg_week`·`_rg_gap`·`_rg_unsettled` 교체, `_rg_last_month`·`_vat_months`·RATIO_MONTHS·LIVE 삭제). 판매액 칸은 **운용 PC 재배포 후** 수집분부터 저장(그 전 기록은 지급대상 합으로 같은 정산대상). 쿠팡 예정값은 정산일 전 정산차감·취소로 바뀔 수 있어(FAQ 223) 매 정산서는 최신 수집 기준·'예정 정확도' 시트로 계속 대조. HQ 포팅 대상.
- 상태: ACTIVE (추정 금지 적용 범위를 정산서 전체로 확대 — D-146 · 부분 SUPERSEDED by D-148 — 쿠팡 정산예정 금액은 불가피한 경우 추정 허용)

### D-082 [LEDGER_HIDDEN_ROWS] 관리대장 숨긴 행 = 그 상품 판매중지 · 계정 줄이 전부 숨겨지면 대장에 없는 계정 · 판매중지 동기화는 ① 매칭 VID 로도 대조 (2026-10-19, R16)
- 결정: (1) `read_ledger_rows` 가 **사용자가 숨긴 행**(rowMetadata.hiddenByUser — 필터로 가려진 행 hiddenByFilter 는 제외)을 읽어 `apply_hidden_rows` 로 반영: 숨긴 줄 = 그 줄 상품명 칸 취소선과 같음(판매중지·수집/순위 제외·이력 보존), 한 계정의 줄이 **전부** 숨겨지면 그 줄들을 빈 줄로(대장에 없는 계정 → 완전 삭제 대상·비밀번호 후보 제외). (2) `sync_discontinued_from_ledger(vids_of=)` — 이름(블록명·등록명)으로 못 찾은 블록은 ① 매칭 결과(`_매칭결과.json` 대장명 → VID)의 VID 겹침으로 대장 판매중지/활성을 따른다(`run_full` 이 `_match_results(out)` 를 넘김).
- 근거: 소유자 2026-10-19 "하성진이 없는데 너는 존재한다고 판단" → 실측: 관리대장 75행(lslfgh·대표자 하성진)은 **숨긴 행**(hiddenByUser)이라 화면엔 없고 데이터엔 있음. 숨긴 행 = 40(헬스매트 HM001)·41(빈 줄)·56(문어발선풍기 m10)·75. 소유자 선택 "숨김=판매중지 취급"(계정 줄 숨김 = 대장에 없음). 첫 구현(계정아이디 있는 줄 숨김 = 계정 블록 제외)은 실제 대장이 **상품 줄마다 계정아이디를 반복**해 40·56행 숨김에 (DW)커머스·웨이브텍 상품 블록이 통째로 빠짐(실측 86상품) → '계정 줄이 전부 숨김'일 때만 계정 제외로 수정(실측 27계정·88상품·lslfgh 없음·헬스매트/문어발 판매중지). 대조 중 발견: kc11345 '맛있는 마시는 알부민' 대장 취소선인데 결과 판매중 — 블록 등록명이 쿠팡 이름이라 이름 대조 실패. 재현 실패 → 수정 → 통과: gsheet [1d]·verify_offline [25] · 게이트 14종·복잡도 초록. 결과 반영 후 대장↔결과 차이 0(온라이프 상품 0개 = 시트 없음 정상).
- 버린 대안: 숨긴 행 = 완전 삭제(이력 손실 — 소유자 비선택) · 필터 숨김도 포함(필터 한 번에 계정 대량 삭제 위험) · 계정아이디 있는 줄만 계정 줄로 판단(이 대장 형식에서 오판).
- 영향 범위: `gsheet_api.py`(`hidden_rows_from_response`·`read_hidden_rows`) · `input_list.py`(`apply_hidden_rows`·`read_ledger_rows`) · `workbook_lifecycle.py`(`sync_discontinued_from_ledger(vids_of)`·`_ledger_vids`) · `pipeline.py`(`_match_results`·`_reconcile_ledger_accounts(vids_by_acct)`) · 테스트 2종. 회사재고·그로스 재고 역기록은 값 직접 읽기라 숨긴 줄에도 그대로 씀(쓰기 대상 줄 위치 불변·무해). HQ 포팅 대상(대장 숨긴 행 의미).
- 상태: ACTIVE
### D-083 [SETTLE_LEDGER_100] 쿠팡 정산 장부(조회 시점) = 정산금액을 지급 완료·보류·지급 예정·줄 생성 전으로 나누고 계정마다 원 단위 판정 · 보류목록 2025-01~ 한 번 조회 · 지급 내역 2025-11~ 기록 (2026-10-19, R16)
- 결정: (1) 정산서(D-059)에 'G. 쿠팡 정산 장부(조회 시점)'·'쿠팡 정산 장부' 시트·전체 요약 '정산 100% 일치' 칸 — 쿠팡 숫자만: 지급 완료(정산현황 지급상태 DONE·로켓그로스 지난 줄 최종지급액) · 보류 중(정산일 지난 PENDING 줄 = 보류목록 P, 사유 AML·채권압류·계좌오류) · 보류 예정(보류목록 P 중 지급일이 앞) · 지급 예정(쿠팡 예정 줄 최종지급액·공제 반영) · 쿠팡 줄 생성 전(정산대상 − 70% — 30%·최종액 줄 생성 전·진행 중인 달 이번 주 구매확정분) · 공제. 판정 E1 정산금액 = 지급대상(로켓그로스 = 정산 파일 있는 판매 주마다 70%+30%·월정산 100%, 지급된 주인데 파일 없으면 '받기 누락' · 윙 = 달마다 정산 파일 + ④ 매출내역 = 지급 줄 지급대상) · E2 줄마다 최종지급액 = 윙 지급대상 + 보류해제 − 공제 / 로켓그로스 지급대상 − 추가공제 − 물류비 + 보상 + 판매조정 · E3 정산현황 보류 줄 = 보류목록 보류 중 · ④에 '자료 없음·확인 필요'가 없을 것 — 모두 맞으면 '일치'. 범위 = 정산 파일이 있는 판매 기간 + ④ 예정 기간(2025 에 70·30 모두 지급된 판매 기간 제외). 입금 확인(월렛·대표계좌, D-065)은 판정과 별개로 표시. (2) 수집: 보류목록 = 보류일 2025-01-01~어제를 한 번(`settlement_verify_collect._pending`·쪽 끝까지, 달마다 조회 폐지) · 정산 일정 조회 `read_events(amounts_from=2025-11-01)` = 지급 내역만 2025-11 부터 기록하고 받을 파일 계획은 시작일부터(2025 일정이 '요청예정'으로 남아 watch 가 끝나지 않는 위험 차단).
- 근거: 소유자 2026-10-19 "지급 보류 계정도 도움말 기준으로·정산금액 100% 정확·기 지급과 정산 예정 포함 조회 시점에 100%·가용 자료 총동원", "추가로 필요한 부분은 너가 받아줘", "앞으로 정산할 금액이 100% 일치하는지도 알려줘". 도움말 FAQ 132·223·238·333. 실측(output(24)+보충 조회 2026-10-19): 윙 지급 줄 743/743 = 지급대상+보류해제−공제 · 로켓그로스 정산 파일 있는 판매 주 = 70%+30% 지급대상(2025-11~12 보충 줄로 웰빙곳간·고로켓 전 주 일치 — 줄이 더 많던 10/20~11/02 판매분은 2025 에 다 지급돼 파일 없음 = 범위 밖) · 보류목록 = 정산현황 보류 줄: 와이에이치 1,301,867·로움 1,758,783·디프픽 12,399,401(AML) 원 단위, 비엔케이 6,649,111 = 지난 보류 5,470,271 + 앞으로의 보류 1,178,840 · 원더폴리 보류 줄 251,978 은 보류일 2025-12(보류목록 2026-01~ 조회라 0건 → 2025-01~ 한 번 조회 시 10건·월별 조회 합과 같음 실측). 로켓그로스 정산 줄 응답엔 상태 칸이 없음(실측 8칸) → 로켓그로스 보류·미입금은 월렛 대조로만(슈카새우 8/31·9/1·벅스 8/31·에벤에셀 10/7 87,326 = 월렛 재조회도 0건 — 입금 미확인). 시험 P18(기간 한 번·2쪽·2025-01~어제)·P35(지급 내역 2025-11~·계획은 시작일부터) 재현 실패 → 수정 → 통과·게이트 14종.
- 버린 대안: 보류목록 2025 를 달마다(계정당 하루 +12회 조회) · 정산 조회 시작 자체를 2025-11 로(2025 일정이 받을 목록에 남음) · 월 단위 로켓그로스 대조(월 경계 주 때문에 틀린 '다름').
- 영향 범위: `src/coupang_analytics/settlement_verify_collect.py`(PENDING_FROM·_pending — `pending` = {"전체": …}, `settlement_verify.holds` 그대로 동작) · `tools/settlement_download.py`(AMOUNTS_FROM·read_events) · P18·P35 · 정산서 스크립트(git 밖) `business_statements.py`(G·장부 시트·판정 출력·보충 폴더 인자) + 신규 `settlement_ledger.py`. **운용 PC 재배포 후** 매일 정산이 2025 보류·2025-11~ 지급 줄을 쌓음(그 전엔 보충 폴더로 대신). 정산서를 만들 때마다 '정산 100% 일치 N/M곳'과 불일치 사유를 보고. HQ 포팅 대상.
- 상태: ACTIVE

### D-084 [RANK_UNCOLLECTED_AND_OPTION] 로그인 실패 계정도 그날 날짜 칸 생성(③ 순위 측정) · 다중옵션 대표 블록이 판매중지여도 같은 상품 옵션이 판매 중이면 순위 측정 (2026-10-19, R16)
- 결정: (1) `run_full` ① 끝에 `_ensure_today_columns` — 미수집(로그인 실패) 계정 시트에도 그날 날짜 칸을 만든다(판매 칸 공란 = 미수집). ③ 순위는 로그인이 필요 없어 그 칸에 측정된다. (2) `rank_suppressed` — 대장 판매중지(취소선·숨김)는 그대로 제외, 쿠팡 상태가 판매중지여도 **같은 등록명의 다른 옵션 블록이 판매중/부분판매중**이면 제외하지 않는다(키워드는 대표 블록에만 있음·③ 은 형제 옵션 VID 전체로 매칭).
- 근거: 소유자 2026-10-19 "공란 분석 · 에벤에셀 기본+옵션 — 기본 판매중지라 노출순위 안 됨·옵션은 키워드 생략 → 둘 다 노출순위를 알 수 없음". 실측: 10-18 실행 ③ 에서 반달컴퍼니·와이에이치·유라이프 검색 0건 — 비밀번호 거부(D-068)로 미수집 → 그날 칸 없음 → `_rank_date` 가 최신 칸(10.16, 이미 채움)을 보고 건너뜀 → 10.17·10.18 순위 공란. 에벤에셀 기저귀 백팩: 대표(베이비 One size, 키워드 5) 판매중지 → rank_suppressed · 옵션(베이지) 부분판매중 · 2차 옵션은 키워드 없음(설계) → 순위 없음. 결과 파일 전체에서 이 조건 해당 = 에벤에셀 1건. 재현 실패 → 수정 → 통과: 시뮬 시나리오 25 · verify_offline [8] 다중옵션 · 게이트 14종·복잡도 초록.
- 버린 대안: 2차 옵션 블록에도 키워드 행 추가(블록 구조 변경·계정목록 1상품 1줄 원칙과 충돌) · 대표 옵션을 판매 중인 옵션으로 자동 교체(키워드·순위 이력 이동 필요·D-043 대표 승계 경로 재사용 범위 큼).
- 영향 범위: `pipeline.py`(`_ensure_today_columns`) · `workbook_meta.py`(`rank_suppressed`) · 시뮬·verify_offline. 지난 날짜(10.17·10.18) 순위는 소급 측정 불가 — 판매는 비밀번호 수정 후 날짜 지정 실행(D-016)으로 채울 수 있음.
- 상태: ACTIVE

### D-085 [SETTLE_AMOUNTS_BY_PAYDATE] 쿠팡 지급 내역·정산 예정 기록 = 정산일 단위로 줄 묶음 저장(같은 키 여러 줄 전부) — 보류 해제 100% 줄 누락 수정 (2026-10-19, R16)
- 결정: (1) `settlement_store.save_amounts`·`merge_amount_file` = (정산일·기간·비율) 키 덮어쓰기를 버리고 **정산일 단위 바꿔 끼움**(그 정산일을 조회하면 그날 줄 묶음 전체로 교체 · 같은 키 여러 줄 전부 보관 · 합치기는 같은 정산일이면 이 PC 묶음 우선). (2) `settlement_forecast.record` = 한 번 조회의 줄 묶음에 '묶음' 번호, `load` = (수집일·계정·채널·정산일)마다 마지막 묶음의 줄 전부(묶음 없는 옛 기록은 예전처럼 정산 줄마다 마지막 값).
- 근거: 실측 2026-10-19(디프 윙 정산현황 5월 조회만): 정산일 5/12 '2026-04-29~04-29 100%' 줄 23개·5/4 같은 키 42개 — 줄 번호 없음(payableSummarySeqList 빈 목록) → 옛 저장은 키마다 1줄만 남겨 보류 해제 지급이 빠짐(5/12: 보류목록 2,872,330 vs 저장 63,428 = 2,808,902 누락 → 장부 E3 '다름'). 같은 구조 계정 5곳(와이에이치 7/20·디프 5/4·5/12·6/16·디프픽 7/20·원더폴리 2/13·에벤에셀 2/2). 시험 P24(c2 같은 키 2줄 보관·다시 조회해도 안 늘어남·바뀌면 그날 묶음 교체·다른 정산일 그대로 / c3 합치기 정산일 단위·이 PC 우선)·P34(같은 날 같은 키 2줄·다시 조회 = 마지막 묶음) 재현 실패([63428]) → 수정 → 통과·게이트 14종.
- 버린 대안: 줄 내용(금액)까지 키에 넣기(같은 금액 두 줄이면 다시 사라짐·금액이 바뀌면 옛 줄이 남음) · 쿠팡 내부 번호(없음).
- 영향 범위: `src/coupang_analytics/settlement_store.py`(_by_paydate·_write_amounts·save_amounts·merge_amount_file) · `src/coupang_analytics/settlement_forecast.py`(record·load) · P24·P34. 운용 PC 재배포 후 다음 조회부터 바로 잡힘(정산일 단위 교체라 옛 1줄짜리 정산일도 다시 조회되면 전부로). 지급액 합(검증 '윙지급'·'RG입금'·계좌 입금)이 보류 해제 지급만큼 늘어 쿠팡 화면과 같아짐. HQ 포팅 대상.
- 상태: ACTIVE

### D-086 [PROMO_START_FROM_LEDGER] 체험단 시작일 = 관리대장 '체험단' 시트 요청일 자동 연결(링크 VID → 대표 블록·최근 회차) · 수집 주기와 분리 저장 · 직원 입력 우선 (2026-10-19, R16)
- 결정: 앱이 관리대장을 불러올 때 '체험단' 시트를 읽어(`promo_sheet.read_promo_sheet` → `InputList.promo`) ① 끝에 `apply_promo_starts` 로 결과 블록에 체험단 시작일을 넣는다. 연결 = 링크의 vendorItemId → productId 순(이름 아님), 2차 옵션 블록이면 같은 등록명 대표 블록, 같은 상품 여러 회차면 **가장 최근 요청일**. 저장 = `_마케팅` 6열 '체험단 시작(자동)'(`set_promo_start`) — 수집 주기 게이팅(`has_marketing`=3~5열)을 켜지 않는다. `promo_effect` 시작일 = 직원 입력(계정목록 체험단 시작일) 우선, 없으면 자동값. 매 반영 때 자동값을 비우고 다시 채움. 체험단 시트를 못 읽으면 `promo=None` → 기존 자동값 유지(로그).
- 근거: 소유자 2026-10-19 "1번 체험단 시작일 자동 연결 진행". 실측: 계정목록 체험단 칸 0/88 → 체험단효과 전부 공란 · 체험단 시트 53건(요청일 26.08.11~10.08·링크 VID). **기존 마케팅 칸(3열)에 넣으면 `has_marketing` 이 켜져 마케팅 없는 상품이 전부 3일 주기 수집으로 바뀜**(`product_cadence` every3) → 별도 칸. 실제 데이터 반영 시험: 52줄 → 23개 상품 연결·결과에 없는 상품 8줄(대장 외 위탁자·다른 옵션 VID)·has_marketing False · 효과 계산 5건(55마켓 순위 50→12 ↑ 등)·18건은 시작일 전 측정 이력이 없어 공란(정상). 재현 실패 → 수정 → 통과: verify_offline [13b] · 시뮬 시나리오 26(체험단 반영 뒤 다음 날도 매일 수집) · 게이트 14종·복잡도 초록.
- 버린 대안: 기존 마케팅 시작일 칸에 저장(수집 주기 3일화 — 매일 통계 중단) · 상호+제품명 이름 매칭(표기 제각각 — '(주)슈카새우'·'㈜슈카새우') · 첫 회차 기준(추가 회차 효과를 못 봄 — 소유자 미결정 시 최근 회차로 두고 보고).
- 영향 범위: 신규 `promo_sheet.py` · `workbook_meta.py`(`set_promo_start`·`promo_start_of`·`clear_promo_starts`) · `workbook_index.py`(promo_effect 시작일) · `input_list.py`(`InputList.promo`) · `pipeline.py`(run_full 반영) · `ui/app_qt.py`(관리대장 불러올 때 체험단 시트 읽기 — 원장 입력 소스일 땐 읽지 않음) · 테스트 2종. 결과 계정목록 체험단 시작일 칸(직원 입력)은 건드리지 않음 — 자동 시작일은 체험단효과 계산에만 쓰임. HQ 포팅 대상.
- 상태: ACTIVE — 단, "계정목록 체험단 시작일 칸 미접촉·직원 입력 우선" 부분은 SUPERSEDED by D-087 · '시작일 = 요청일' 부분은 SUPERSEDED by D-122

### D-087 [PROMO_START_INDEX_COL] 계정목록 '체험단 시작일' 칸 = 관리대장 체험단 시트 요청일(앱이 채움·되읽지 않음) · 종료일·모니터링 종료일은 직원 입력 유지 (2026-10-19, R16)
- 결정: 결과 계정목록(구글 G열·로컬 '계정 목록')의 '체험단 시작일' 칸을 **자동 칸**으로 바꾼다 — 값 = 결과 블록의 체험단 시작일(D-086 자동값, 관리대장 마케팅 시작일이 있으면 그 값), 없으면 비움. 이 칸은 **되읽지 않는다**(`read_marketing` 시작일 무시·로컬 `_sync_marketing_from_index` 는 기존 숨김값 유지) — 되읽으면 마케팅 시작일이 돼 `has_marketing` 이 켜지고 마케팅 없는 상품이 3일 주기 수집으로 바뀐다. 체험단 종료일·모니터링 종료일(H·I)은 지금처럼 직원 입력·앱 미접촉.
- 근거: 소유자 2026-10-19 "체험단 시트에서 요청일이 결과 계정목록의 '체험단 시작일' 칸과 매칭됨"(D-086 보고의 '시작일 칸 미접촉' 정정). 실측: 계정목록 시작일 칸 0/88 입력 — 직원 입력 칸으로 쓰이지 않음. 되읽기 경로 2곳(구글 `read_marketing` → 앱 입력 마케팅 · 로컬 계정 목록 회수) 확인. 재현 실패 → 수정 → 통과: verify_gsheet_offline [3]·[4]·[6] · verify_offline [13b](로컬 표시·저장/재로드 뒤 has_marketing False) · 게이트 14종·복잡도 초록.
- 버린 대안: 시작일 칸 되읽기 유지(3일 주기 수집 켜짐) · 새 '체험단 시작일(자동)' 칸 추가(칸 이동·마이그레이션 필요 — 소유자가 기존 칸과 같다고 지정).
- 영향 범위: `gsheet_index.py`(`IndexRow.promo_start`·`_auto_cells_request` G열·`roster_from_workbook`·`read_marketing`) · `workbook_index.py`(로컬 계정 목록 표시·회수) · 테스트 3종. D-086 '직원 입력 우선·시작일 칸 미접촉' 부분 대체. HQ 포팅 대상.
- 상태: ACTIVE (부분 SUPERSEDED by D-106 — 구글 열 위치·모니터링 종료일 · SUPERSEDED by D-109 — 체험단 종료일)

### D-088 [STATEMENT_NOTIFY_RULES] 위탁정산서 통보 규칙 — 정산 예정 포함·차이 사유 표기 · 체험단 표시만 · 우리 사업자 제외 · 쿠팡 별도 보상 ⑥ · '쿠팡 지원 할인(가산)' · 대응표 소유자 확정 우선 (2026-10-19, R16)
- 결정: 위탁정산서(D-059·D-077·D-081·D-083)를 계약자에게 통보할 때: (1) **총 정산금액 ⑤ = 확정(70%·30% 지급분) + 쿠팡 정산 예정 전부**(어제 조회 기준·추정 없음). 취소·반품은 다음 정산에 반영. 정산서 D·쿠팡 미정산 시트·요약 3행에 예정액이 실제와 달라질 수 있는 사유 6가지(취소·반품 · 정산차감 · 광고비·밀크런·물류비 상계·이월 · 지급 보류 · 판매자서비스이용료 · 조회 뒤 구매확정분)를 짧게 적는다. (2) **체험단 비용** = 관리대장 두 번째 시트 '체험단'(SA 읽기만) + `D:\토탈셀러\쿠팡 정산 자료\체험단_보충.json`(시트에 없는 견적서·이체 근거 건) → 'H. 체험단 비용' 섹션·'체험단 비용' 시트. 부담 '고객' = 계약자, '디프픽' = 우리. **정산금액에서 차감하지 않고 표시만** · 진행 여부 '완료'만 합계(빈칸 = 진행 전 따로) · '고객10 디프픽20' = 건수 비율 · 정산 대상 아닌 상호 = 전체 파일 '정산 대상 아닌 체험단' 시트. (3) **디프(ski1121)·디프픽 = 우리 사업자** → 계산은 같게, 개별 정산서는 `_우리사업자(통보 제외)\` 폴더 · 전체 요약 위탁 합계에서 빼고 '우리 사업자(통보 제외)' 시트. (4) **⑥ 쿠팡 별도 보상(정산 외)** = 쿠팡 정산현황·재고 손실 보상·월렛에 없는 쿠팡 입금(화재 보상금 등)을 `쿠팡_별도보상.json`(사업자·계정ID·일자·금액·입금처·근거)에서 읽어 C 섹션에 줄마다 + '정산·보상 합계(⑤+⑥)'. ⑤와 100% 판정은 그대로. (5) 요약 ② 칸·B 섹션 '기타 조정' → **'쿠팡 지원 할인(가산)'**(= 판매−쿠폰−수수료와 쿠팡 정산금액 차이, 전체 = 로켓그로스 쿠팡지원할인 13,566,407 원 단위). (6) 사업자명은 출력 폴더 `사업자_대응표.csv` 가 우선 — 소유자가 확정한 이름은 그 줄을 고쳐 출처 '소유자 확인(날짜)'. 정산서를 만들 때마다 '정산 100% 일치 N/M곳'과 불일치 사유를 보고(D-083).
- 근거: 소유자 2026-10-19 "예정 금액을 포함해 전체 정산 금액에 반영·차이 사유 간단히 기술", "고객 = 계약자·디프픽 = 우리 부담·정산 내역에 구분 포함"(답: 둘 다 표시만·완료만·별도 목록), "디프와 디프픽은 우리 사업자라 통보 대상에서 빼줘", "연다인님 화재보상금 받은 금액도 정산내역에 포함"(통장 2026-08-20 쿠팡풀필먼트서 8,697,763 — bux1004 정산현황·보상·월렛에 없음 실측), "쿠팡 지원 할인(가산)으로 바꿔줘", "hk66597582 = 디케이유니버스(강혁) 맞아". 실측 결과 `위탁정산서_20261018기준\`: 위탁 28곳 + 우리 2곳 · 검산 ①−②=③·③+④=⑤ · ⑤ 1,606,706,009 · ⑥ 12,112,707(벅스 8,697,763·니코에이블 3,414,944[D-065 확인분]) · 체험단 완료 고객 26,308,033·우리 6,512,590 · **정산 100% 일치 26/28**(✘ 유라이프 gyi0101·글로벌셀러 gbseller808 = 비밀번호 오류로 기준일 조회 못 함 → 2025-11 로켓그로스 E1 다름).
- 버린 대안: 체험단 고객 부담을 정산금액에서 차감(소유자 '표시만') · 화재 보상금을 ⑤에 합산(쿠팡 정산 자료에 없어 100% 판정이 깨짐) · 우리 사업자 정산서 삭제(계산 검증용으로 보관).
- 영향 범위: 앱 코드 아님 — 정산서 스크립트(git 밖) `output/_분석_261013/정산스크립트/business_statements.py`(FORECAST_NOTE·OWN_BUSINESSES·EXTRAS/_extras·COLS ⑥·C/H 섹션) · `experience.py`(신규) · `settlement_ledger.py`. 자료 `D:\토탈셀러\쿠팡 정산 자료\체험단_보충.json`·`쿠팡_별도보상.json`. HQ 정산서 포팅 시 같은 규칙.
- 상태: ACTIVE (부분 SUPERSEDED by D-126 — 정산서 표시: ⑥ 쿠팡 별도 보상 = C 섹션·'정산·보상 합계(⑤+⑥)' → 1쪽 A~G 밖 '참고. 쿠팡 계정 전체' 줄·총액 = G 최종 지급액(입금 완료/예정)·예정 포함/체험단 표시만/우리 사업자 통보 제외/대응표 우선은 그대로)

### D-089 [RANK_PWFAIL_TODAY_COL] 비밀번호 오류 계정도 그날 날짜 칸 생성(③ 순위 측정) — D-084 가 비밀번호 오류 계정에 적용되지 않던 것 보완 (2026-10-21, R19)
- 결정: `run_full` ① 끝 `_ensure_today_columns` 대상 = 미수집 계정(`_not_done`) **+ 이번 실행 비밀번호 오류 계정**(`_pw_failed(ctx)`). 비밀번호 오류 계정은 재시도 금지(D-068)를 위해 '처리됨'(done)으로 표시돼 `_not_done` 에 안 들어가므로 따로 더한다. 판매 칸은 공란(미수집), 순위는 ③ 에서 측정.
- 근거: 소유자 2026-10-21 output(25) 공란 분석 → "A, B, C 모두 수정". 실측 10-20 실행: 유라이프(계정아이디 칸 값이 바뀌어 거부)·반달컴퍼니(비밀번호 오류) 시트 최신 칸 = 10.16 — 10.17~10.20 칸 없음 → 판매·순위 모두 공란. 로그에 `[미수집] 날짜 칸` 줄 없음(D-084 미작동) · `pipeline.py` 비밀번호 오류 → `done.add` · `_not_done` 은 done 제외. D-084 를 만든 원인 계정이 바로 이 둘이었음. 재현 실패(시뮬 시나리오 26 '그날 칸 [09.01]') → 수정 → 통과(시나리오 25·26).
- 버린 대안: 비밀번호 오류 계정을 done 에서 빼기(같은 날 재개·재실행이 거부된 비밀번호를 다시 넣음 — D-068·계정 잠금 위험).
- 영향 범위: `pipeline.py`(run_full 한 곳) · `tools/simulate_pipeline.py`(pw_fail 주입·시나리오 26). 지난 날짜(10.17~10.20) 순위는 소급 불가. HQ 포팅 대상.
- 상태: ACTIVE

### D-090 [RANK_DEAD_IP] ③ 순위 — 쿠팡 화면에 검색창이 없는 IP = IP 불량: 키워드를 쓰지 않고 바로 새 IP · 바퀴 '장애 있음'으로 끝까지 반복 · 증거 화면 저장 (2026-10-21, R19)
- 결정: (1) 새 IP 로 연 직후와 키워드 입력 실패 때 쿠팡 검색창이 있는지 본다(`_search_box_present`, 15초 여유·크롬 연결 오류 화면이면 기존 연결 장애 처리). 없으면 **IP 불량**(`_semi_on_dead`): 증거 화면(`output/_순위차단`, 판정 '검색창 없음') 저장 · 즉시 다른 IP·다음 키워드로 전환하고 못 잰 키워드는 뒤로 미뤄 **한 바퀴를 다 돈 뒤 빈 칸만 재검색**(차단과 같은 규칙 · 소유자 2026-10-21 지시) · 회전 가능하면 새 IP(차단 목록엔 안 남기고 이번 실행만 그 (주소, IP) 건너뜀) · 회전 불가(프록시 OFF)면 기존 미로딩 처리. (2) IP 불량이 있었던 바퀴는 '장애 있음' → "진전 없음·차단 없음 = 측정 불가로 마침" 규칙에 걸리지 않고 빈 칸 0 까지 반복(D-053). (3) 성공 없이 IP 불량이 15번 이어지면 쿠팡 화면 구조 변경·프록시 전체 불량 의심으로 ③ 마침(❌ 로그·무한 회전 방지). (4) 순위 요약에 'IP 불량(화면 안 열림) N회'.
- 근거: 실측 10-20 밤(output 25): IP 69개 중 31개가 처음부터 검색창 없음('검색창 못찾음→URL 폴백') → 그 IP 검색 92건 전부 '결과 미로딩'(검색창 있는 IP 의 미로딩은 4건뿐) · 정상 IP 28개는 8~13회 검색 뒤 '사용권한' 차단 · IP 불량 하나마다 키워드 3개(약 4~5분) 소모(밤새 약 2시간) · 4바퀴째(04:05~04:27) IP 5개 연속 불량 → 진전 0·차단 0 → "차단·연결 장애 아님"으로 오판해 빈 칸 12개(웨이브텍 4·셀와니 4·더이룸랩 2·55마켓 1·꿈꾸는아재 1) 남기고 마침. 재현(test_proxy_patch test_semi_dead_ip — 수정 전 함수 없음) → 수정 → 통과 15/15.
- 버린 대안: 미로딩 전부를 '장애'로 보기(검색결과가 원래 안 나오는 키워드면 밤새 무한 반복) · IP 불량을 차단 목록(72h)에 기록(쿠팡 차단 확정 아님 — 업체 회전 IP 가 곧 바뀜).
- 영향 범위: `pipeline_ranks.py`(`_search_box_present`·`_semi_on_dead`·`_semi_search_one`·`_semi_track_product`·`_track_ranks_semi`·`drive_rank`·`_SemiState`·요약 로그) · `tools/test_proxy_patch.py`. 3경로(전체실행·무인·순위 탭 반자동) 공통. HQ 포팅 대상.
- 상태: ACTIVE

### D-091 [SETTLE_NO_DUP_RUN] 정산 중복 실행 방지 — 같은 회차 '완료'면 ① 단계 기록 시각이 바뀌어도 종료 · 18:00 시작 때 옛 정산 예약작업(매일 08:00·인자 watch) 삭제 (2026-10-21, R19)
- 결정: (1) `settlement_watch.already_done(done, key, cycle_start)` — 키가 같거나, **완료 키(①완료 시각)가 이번 회차 시작(--since 반영) 이후**면 이미 완료. (2) `app_process.prepare_auto_start`(18:00 무인 시작)가 `remove_legacy_settlement_task` 로 인자 'watch' 예약작업을 지운다(실패 시 로그·계속). install.ps1 은 '자동실행 등록=Y' 때만 지워 폴더 덮어쓰기 업데이트로는 남았음.
- 근거: 실측 output(25): 10-19·10-20·10-21 매일 08:00:02 앱 없이(부모 PID 감시 줄 없음) 정산 watch 시작 → 10-20 18:00 정산이 21:31 '완료'(키 = ①완료 18:48:17)였는데 ③ 끝(04:29)에 단계 기록이 done 으로 바뀌어 키가 달라짐 → 35계정 재로그인·전부 다시 조회(08:00~09:16+) → 그 사이 output 압축 시 `_watch.lock`·`hellojin.lock` 사용 중 오류 · 아침 정산의 비밀번호 거부가 그날 18:00 수집을 막음(반달컴퍼니 10-20 10:14 → 18:19 D-068 건너뜀). D-010 은 예약작업 폐지를 정했으나 제거가 설치 시 한 번뿐이었음. 재현 실패(P36) → 수정 → 통과(P30 수동 전체실행 --since 동작 불변 포함).
- 버린 대안: 부모 PID 없는 watch 거부(기존 시험·수동 실행 경로가 parent 없이 watch 를 씀) · 단계 기록을 ① 완료 시각으로 고정(앱 재부팅 복구·정산 대기 판정이 함께 쓰는 기록이라 범위 큼).
- 영향 범위: `settlement_watch.py`(already_done) · `tools/settlement_download.py`(cmd_watch 한 줄) · `app_process.py`(remove_legacy_settlement_task·prepare_auto_start) · `tools/verify_settlement_runtime_offline.py`(P36). 운용 PC = 재배포 후 첫 18:00 에 옛 작업 삭제 로그 확인. HQ 포팅 대상.
- 상태: ACTIVE

### D-092 [COMPANY_STOCK_HEADER] 관리대장 회사보유재고 열 = '회사보유재고'로 시작하는 열 · 앱이 머리글을 '회사보유재고 (자동갱신 MM.DD)'로 갱신 (2026-10-21, R20)
- 결정: `company_stock._ledger_rows` 가 공백을 뺀 머리글이 '회사보유재고'로 **시작**하는 열을 찾는다(예 '회사보유재고 (10.20기준)'). 역기록할 때마다(미리보기 제외) 머리글을 그로스 재고 열과 같은 방식으로 '회사보유재고 (자동갱신 MM.DD)'로 바꾼다(같은 날·같은 값이면 쓰기 없음). 재고현황 시트는 지금처럼 '현재고' 칸만 쓰고 셀독·당근·자사 칸은 쓰지 않는다(소유자 확인).
- 근거: 소유자 2026-10-21 "그로스 재고 열처럼 열 이름 끝 날짜를 앱이 (자동갱신 MM.DD)로 바꿔줘", "재고 시트는 최신·셀독/당근/자사 구분 사용 안 함". 실측: 10-20 03:10 까지 역기록 정상(73줄 매칭) → 직원이 머리글을 '회사보유재고 (10.20기준)'로 바꾼 뒤 10-21 04:29 `ValueError: 관리대장에 '회사보유재고' 열이 없음`(이름 완전 일치 비교). 재현 실패(verify_registry_offline R21) → 수정 → 통과.
- 버린 대안: 이름 완전 일치 유지 + 직원에게 머리글 고정 요청(다시 바뀌면 또 멈춤).
- 영향 범위: `company_stock.py`(_ledger_rows·write_company_stock) · `tools/verify_registry_offline.py`(R21). HQ 포팅 대상.
- 상태: ACTIVE (부분 SUPERSEDED by D-141 — 재고현황 읽는 칸 '현재고'만 → 새 양식(팔래트/박스 줄)은 '총입고수량'을 창고별 합산·셀독/당근/자사 칸 안 씀은 그대로)

### D-093 [PRUNE_STALE_ACCOUNT_ID] 결과 파일 계정ID = 관리대장에 있는 것만 — 대장에 없고 어느 상품에도 태그 안 된 계정ID 는 매 실행 제거(오입력 값 노출 방지) (2026-10-21, R21)
- 결정: `run_full` 대장 대조(`_reconcile_ledger_accounts`)에서 대장 계정마다 `prune_account_ids(사업자, 대장 계정ID 전체)` — 그 사업자 `_계정정보` 계정ID 중 **대장에 없고 상품 태그에도 없는** 것을 빼고 `_수집스탬프` 그 행도 지운다(남는 계정ID 가 0 이면 안 지움). 로그에는 지운 값을 남기지 않는다. 시트 제목(A1)·통합판매현황 계정 이름이 이 목록을 쓰므로 함께 정리된다. 결과 구글시트에 이미 보이던 4칸(유라이프 A1·통합판매현황 3줄)은 10-21 직접 정리.
- 근거: 실측 10-20 실행 — 관리대장 유라이프 계정아이디 칸에 비밀번호 값이 들어가 그 값으로 로그인(거부) · `set_account_id` 는 누적만 해서 결과 파일 계정ID 가 'gyi0101 / (비밀번호 값)' 이 됨 → 결과 구글시트 유라이프 제목·통합판매현황 3줄에 노출. 대장을 고친 뒤에도 남음(10-21 점검). 재현 실패(시뮬 시나리오 27 '남은 개수 2') → 수정 → 통과(제목·통합판매현황·숨김 시트 어디에도 없음·이력 보존).
- 버린 대안: 결과 구글시트 칸만 직접 정리(18:00 실행이 마스터 값으로 다시 씀) · 계정ID 를 매번 대장 값으로 덮어쓰기(다계정ID·계정ID 변경 이력 태그와 충돌).
- 영향 범위: `workbook_lifecycle.py`(prune_account_ids) · `pipeline.py`(_reconcile_ledger_accounts 한 곳) · `tools/simulate_pipeline.py`(시나리오 27). 운용 PC 재배포 후 첫 실행에서 마스터 정리 — 그 전 18:00 실행은 구글 제목에 그 값을 다시 쓸 수 있음. 노출된 유라이프 비밀번호는 변경 권고. HQ 포팅 대상.
- 상태: ACTIVE (사람이 PC 엑셀을 고른 실행은 계정ID 정리도 안 함 = 의도 범위 — 소유자 확인 D-179)

### D-094 [SALES_DASHBOARD] 통합판매현황 = 위 대시보드(요약·월/주/일 차트·계정 순위·상품 상위 20 열지도) + 아래 일별 상세표(최근 31일·최신 왼쪽) · 집계 기준 = 관리 상품 · 일별 판매 2026-04-01부터 소급 (2026-10-21, R22)
- 결정: ① `output/판매분석_일별/{계정}.json` 을 2026-04-01~어제까지 채운다 — ① 판매수집의 **같은 로그인 세션**에서 `fetch_sales_details(page, d, d)` 하루씩(로그인 추가 없음), **최근 날짜부터 거꾸로**, 이미 있는 날 제외, **계정당 하루 최대 30일**(그날 수집 시각이 찍힌 기록 수를 뺌), 조회 사이 1~2.5초, 실패하면 그 계정 소급 중단(다음 실행이 이어서·비치명·로그). 소급이 끝난 뒤에도 매일 빠진 날을 자동 보충(`sales_summary.plan_backfill`·`pipeline_sales._record_sales_backfill`). ② 첫 시트 `통합판매현황` 위 = 대시보드: ①요약(전일·지난주[끝난 월~일, 그 전주 대비]·이번 달 누계[**지난달 같은 기간** 1~N일 대비, 짧으면 말일·일별 기준]·미수집 계정 수·증감 ▲초록/▼빨강) ②월별 막대(1월~이번 달·진행 중 달 구분) ③주간 선(끝난 8주) ④일별 막대(31일) ⑤계정 순위(이번 달 누계 순·지난달 같은 기간·증감·비중·8주 글자 미니 그래프 ▁▂▃▅▇) ⑥상품 상위 20 × 8주 금액 열지도(5단계 고정 채움색). 아래 = 상세표(일별 건수·금액·최근 31일·최신이 왼쪽·계정 소계·전체 합계·미수집) — 옛 주간·월별 구역 삭제. ③ **집계 기준 = 관리 상품**(결과 사업자 시트 블록의 VID = 관리대장 상품, 판매중지 블록 포함·`workbook_sales.managed_vids`·`sales_summary.scope`) — 대시보드 합계 = 상세표 합계. 결과 파일에 없는 계정·상품은 빠짐. ④ 계정 하나의 기간 값 = 그 기간 일별이 모두 있으면 일별 합, 아니면 쿠팡 기간 합계(조회기간 정확히 같은 것), 둘 다 없으면 미수집(합계에서 빼고 수 표시). 증감 % = 두 기간 모두 받은 계정끼리. ⑤ 차트 자료 = 상세표 오른쪽 숨긴 열 9칸·설정 JSON = 그 첫 칸 1행 → 엑셀은 `OutputWorkbook.load` 가 차트를 다시 붙임(openpyxl 은 열 때 차트를 버림), 구글은 `push_sales_sheet` 가 옛 차트 삭제(`GSheetClient.chart_ids`)→값·서식→열 숨김→addChart 3개(SHOW_ALL)→index 0.
- 근거: 소유자 2026-10-21 시안(요약 카드·월별 막대·주간 선·계정 순위) 확정 + 요구 1~5(4/1 소급·지난달 같은 기간·대시보드 ①~⑥·상세표 31일 최신 왼쪽·관리 상품 기준). 일별 저장이 10월 중순부터만 있어 소급 필요. 실측(오프라인): verify_sales_summary_offline T1~T11 통과(소급 계획·소급 수집·관리 상품 필터·31일 최신 왼쪽·지난달 같은 기간·대시보드 값·엑셀 차트 3개 다시 열어도 유지·구글 delete/addChart/숨김) · 실제 Excel(COM)로 다시 연 파일 차트 3개 그림 확인(PNG). openpyxl 차트 버림 = 재현(load 후 _charts 0) → 복원으로 해결.
- 버린 대안: SPARKLINE 수식(엑셀에서 깨짐) · 조건부서식 열지도(구글 미러가 못 옮김) · 진행률 대비 이번 달 비교(소유자 = 지난달 같은 기간) · 차트 자료 별도 숨김 시트(구글 미러 대상 아님) · 판매분석 전체 상품 기준(상세·대시보드 합 불일치 — 소유자 '관리 상품' 선택, 바꾸려면 `refresh_sales_sheet` 의 `scope(…, managed)` 를 None 으로).
- 영향 범위: `sales_summary.py`(plan_backfill·scope·build 31일) · 신규 `sales_dashboard.py`·`workbook_sales_dash.py` · `workbook_sales.py`(managed_vids·refresh·write·push) · `pipeline_sales.py`(_record_sales_backfill·호출 순서) · `gsheet_api.py`(chart_ids) · `workbook.py`(load → restore_charts) · `tools/verify_sales_summary_offline.py`(T3~T5 갱신·T7~T11 신규) · `designs/SALES_SUMMARY.md`. ① 야간 시간: 소급 기간(약 7일 밤) 계정당 +약 1~1.5분. HQ `R0_DATA_CONTRACT` 알림·포팅 대상(첫 시트 구조·일별 저장 범위).
- 상태: ACTIVE (부분 SUPERSEDED by D-097 — 하루 상한 · SUPERSEDED by D-098 — ⑤⑥ 구성 · SUPERSEDED by D-105 — 월 시작 · SUPERSEDED by D-107 — 관리 상품 범위 · SUPERSEDED by D-110 — ⑤ 기간)

### D-095 [REGISTRY_SEPARATE_FILE] 셀독등록원장 = 별도 파일 '셀독등록원장_자동화용'만 — 설정 탭 '원장 링크'에 관리대장 주소 금지 · 10-20 대장 안에 잘못 생긴 원장 시트 5개 삭제 (2026-10-21, R23)
- 결정: 원장 링크(config `registry/url`)는 `셀독등록원장_자동화용`(…/d/1Fb_G1Jz3EmYbu_SnDVPXiMmO7In7vq6d_lfFPriQYq0) 하나. 관리대장 주소를 넣으면 18:00 실행이 대장 파일 안에 원장 시트 5개(셀독원장·계정이력·상품이력·그로스이력·동기화기록 — 셀독원장에 비밀번호 칸 사본)를 새로 만들고 원래 원장은 갱신이 멈춘다. 10-20 에 생긴 5개는 소유자 지시로 10-21 삭제(구글 버전 기록으로 복구 가능 · 하루치 '최초 등록'만 있어 잃는 이력 없음). 운용 PC 설정 탭 링크는 소유자가 원래 주소로 되돌림.
- 근거: 소유자 2026-10-21 "셀독등록원장_자동화용 주소임 · 삭제해줘". 실측: 운용 PC 로그 10-20 10:06 `셀독등록원장 연결 확인 OK — '[셀독] 관리 대장'` → 18:00 `[원장] … 신규계정 27 · 신규상품 93`·`시트 5개 생성` · 원래 원장 동기화기록 51회 마지막 = R261019-180029(10-19 18:00) · 운용 PC 백업 원장_261018·261019 와 같은 파일.
- 버린 대안: 대장 안 원장 유지(비밀번호 사본·원래 이력과 분리) · 코드로 '원장 링크 = 관리대장 주소' 거부(소유자 미결정 — STATE 제안).
- 영향 범위: 운용 설정(config.json `registry/url`)·관리대장 시트 구성. 코드 변경 없음.
- 상태: ACTIVE (코드 가드 미결은 D-150 에서 해소 — 가드 없음)

### D-096 [KW_VOLUME_DAILY_REFRESH] 키워드 검색량 = 매 실행(② 단계) 네이버에서 새로 받아 덮어씀 — 2026-09-20 '빈 칸만 채움' 규칙 대체 (2026-10-21, R25)
- 결정: ② 키워드 단계(`_select_product_keywords`)에서 동결 키워드 **전부**의 검색량을 매 실행 네이버 검색광고 키워드도구로 다시 받아 결과 파일 '검색량' 칸(F열)을 덮어쓴다(`pipeline_process._refresh_search_volumes`). 값 = 네이버 '월간 검색수' PC+모바일 합(조회 시점 기준 최근 한 달·'< 10' = 9). 네이버가 돌려주지 않은 키워드·조회 실패면 기존값 유지(날조 금지·비치명). 새로 선정·발굴한 키워드는 지금처럼 선정 때 받은 값.
- 근거: 소유자 2026-10-21 "이미 값이 있는 키워드 다시 받지 않음 ==> 매일 앱 실행시 매번 다시 조사해줘". 분석: 예전 규칙(2026-09-20, 코드 주석 '소유자 규칙')은 빈 칸만 채워 등록 시점 값이 계속 남음(계절 상품 차이·칸에 기준 날짜 없음). 재현 실패(verify_offline [23] (D) '값 있는 키워드도 다시 조회해야: []') → 수정 → 통과.
- 버린 대안: 주 1회 갱신(소유자 '매일') · 날짜별 이력 누적(요청 범위 밖 — 필요 시 별도).
- 영향 범위: `pipeline_process.py`(_fill_frozen_search_volumes → _refresh_search_volumes) · `pipeline.py`(호출·재수출 1줄씩) · `tools/verify_offline.py`([23] D). 네이버 호출 = 상품마다 하루 1회 묶음(쿠팡 부담 없음). HQ 포팅 대상.
- 상태: ACTIVE

### D-097 [SALES_BACKFILL_60] 일별 판매 소급 상한 = 계정당 하루 60일(D-094 의 30일에서 상향) (2026-10-21, R26)
- 결정: `sales_summary.BACKFILL_PER_DAY` 30 → 60. 그 밖의 소급 규칙(① 같은 로그인 세션·최근 날짜부터 거꾸로·이미 있는 날 제외·조회 사이 1~2.5초·실패 시 그 계정 중단·그날 수집 기록 수를 빼서 하루 상한 지킴)은 D-094 그대로.
- 근거: 소유자 2026-10-21 "60일로 해줘"(선택지: 30 유지 약 7일 밤 / 60 약 4일 밤 / 100 약 3일 밤 중 선택). 4/1~10/20 = 203일 → 60일씩 4일 밤. 시험 T7 을 60일 기준으로 먼저 바꿔 실패 확인 → 상수 변경 → 통과.
- 버린 대안: 30일 유지(약 7일 밤) · 100일(같은 창 조회가 몰려 차단 위험 가장 큼).
- 영향 범위: `sales_summary.py`(상수 1줄) · `tools/verify_sales_summary_offline.py`(T7) · `designs/SALES_SUMMARY.md` · CLAUDE.md 운영 정책 한 줄. 추정: 소급 기간 밤마다 계정당 +약 2~3분(27계정 약 1시간~1시간 20분·실측 아님) — 첫 18:00 로그로 확인. 새 배포 zip 필요(10-21 12:07 zip 은 30일).
- 상태: ACTIVE (부분 SUPERSEDED by D-167 — 정산 실행 소급 한시 150일, 다 채우면 60일 복귀)

### D-098 [SALES_DASHBOARD_V2] 통합판매현황 2차 — ⑥ 열지도 삭제 · 상세 = 한 건 2줄(수량·금액) · ⑤ = 가로 막대 + 5칸 표 · 열 고정 해제 · 모든 도식 같은 왼쪽 끝·같은 폭 W (2026-10-21, R27)
- 결정: ① ⑥ 상품 상위 20 열지도·⑤ 글자 미니 그래프·'지난달 같은 기간'·'비중' 칸 **물리 삭제**. ② 일별 상세표 = 날짜 1칸(31일·최신 왼쪽·모두 같은 너비)·한 건 2줄(수량 줄·금액 줄)·구분 칸 '로켓그로스·수량'·전체 합계/계정 소계도 2줄·미수집 계정 수 1줄. ③ ⑤ = 이번 달 누계 **가로 막대 차트**(판매 있는 계정·1위 맨 위) + 표 5칸(순위·계정·이번 달 누계·지난주·전주 대비 ▲초록/▼빨강) + '판매 없음 N계정: …'·'미수집 N계정: 이름(사유)' 한 줄씩. ④ 시트 **열 고정 해제**(행 1~2만). ⑤ ② 월별 = 진행 중 달 연한 색(쌓기·다른 계열 0)·자료 없는 달 빈칸 · ④ 일별 = 전 계정 받은 날 파랑·일부 미수집 회색·자료 없는 날 빈칸 · 값 축 0부터. ⑥ **시각 균형**: 대시보드 전체 = 같은 왼쪽 끝(A)·같은 폭 W(A~J) — 차트 위치·폭을 W 비율로 저장, 엑셀(열 너비 1 = 6pt·OneCellAnchor 오프셋)·구글(int(너비×7+5)px·anchorCell+offsetXPixels)이 각자 자기 열 픽셀로 계산. 집계 기준 = 관리 상품 유지(D-094).
- 근거: 소유자 2026-10-21 실제 구글 결과 시트(13:23 반영본)·시안 확인 후 "시안대로 진행·기준은 관리 상품 유지". 실측: 구글 ② 월별 차트 안 보임 = 고정 열 3개(A:C≈610px) 구역 안 배치(A12·520px) — 주간 차트(C12)만 보임. 엑셀 열 너비 실측(COM): 28→168pt·46→276pt·16→96pt·12→72pt(= 6pt/글자)·행 16.5pt. 결과(오프라인·Excel COM): 차트 4개 왼쪽 0pt·오른쪽 1044pt = A~J 오른쪽 끝 · 구글 요청도 열 픽셀 합 W 와 오른쪽 끝 일치(T5) · 다시 열어도 4개(T11) · verify_sales_summary_offline T1~T11 통과.
- 버린 대안: 열 고정 유지 + 차트를 D열 뒤로(대시보드가 오른쪽으로 치우침) · 픽셀 고정 크기(엑셀 6pt/글자·구글 7px+5 가 달라 한쪽만 맞음) · 일별 미수집 날 0 막대(판매 0 과 구분 안 됨).
- 영향 범위: `workbook_sales_dash.py`(재작성 — 3회째 큰 변경) · `workbook_sales.py`(_write_section 2줄·_two_rows·열 너비·freeze A3) · `sales_dashboard.py`(AccountRank 지난주·전주·ProductHeat/spark 삭제) · `tools/verify_sales_summary_offline.py`(T4·T5·T10·T11) · `designs/SALES_SUMMARY.md` §5·§5-1 · CLAUDE.md 운영 정책 한 줄. 결과 시트 다시 그리기 = 운용 PC 자료 가진 세션. 새 배포 zip 필요.
- 상태: ACTIVE (부분 SUPERSEDED by D-101 — ⑤ 대상 계정·판매 없음 줄 · SUPERSEDED by D-110 — ⑤ 기간)

### D-099 [SALES_MISSING_NAMES] 통합판매현황 미수집 계정 = 사업자명을 괄호로 표시 (2026-10-21, R28)
- 결정: 미수집 계정이 있으면 이름(사업자명·계정ID 뺌·중복 없이)을 함께 보인다 — ① '미수집 계정(전일)' = '2 / 26 계정 (유라이프, 반달컴퍼니)' · ① 비교 기준 = '미수집 2계정(유라이프, 반달컴퍼니) 제외' · ⑤ 순위 아래 = '미수집 N계정: 유라이프(사유)' · 일별 상세표 '미수집 계정 수' 줄 B칸 = '유라이프 5일, 반달컴퍼니 3일'(31일 중 빠진 일수 많은 순 — 날짜 칸은 좁아 개수만). 미수집이 없으면 괄호 없음.
- 근거: 소유자 2026-10-21 — 오늘 반영본에 '미수집 계정(전일) 2 / 26 계정'만 보여 어느 계정인지 물음(실제 = 유라이프 gyi0101·반달컴퍼니 mrc098, 10.19 일별 기록 없음). 시험 T11 에 이름 표시 확인 추가(통과).
- 버린 대안: 날짜 칸마다 이름(칸 너비 12 로 잘림) · 계정ID 표시(소유자 예시 = 사업자명).
- 영향 범위: `sales_dashboard.py`(short_name·missing_names·Kpi.missing_names·Dashboard.missing_today_names) · `workbook_sales_dash.py`(paren·① 미수집 칸 B~J 병합) · `workbook_sales.py`(_missing_names) · `tools/verify_sales_summary_offline.py`(T11) · `designs/SALES_SUMMARY.md` §5-1.
- 상태: ACTIVE

### D-100 [REGISTRY_RENAME] 셀독등록원장 → '셀독계정상품이력관리원장_자동화' (파일·화면·설명 이름만) · 빈 '시트1' 삭제 (2026-10-21, R29)
- 결정: 구글시트 파일 제목을 '셀독계정상품이력관리원장_자동화'로 바꾸고(10-21 서비스계정으로 변경), 코드·설계의 이름 표기를 '셀독계정상품이력관리원장'으로 통일한다(화면 글자·로그·설명문·게이트 이름·LEDGER_REGISTRY.md). **링크(파일 ID)·설정 키 `registry/url`·모듈 이름 `registry_*`·시트 이름 5개(셀독원장·계정이력·상품이력·그로스이력·동기화기록)는 그대로** — 코드는 이름이 아니라 링크로 파일을 찾고, 시트 이름은 HQ 로 옮긴 원장 코드(D-025)도 쓰기 때문. 쓰지 않던 빈 '시트1' 삭제(구글 버전 기록으로 복구 가능).
- 근거: 소유자 2026-10-21 "셀독등록원장 명칭을 셀독계정상품이력관리원장_자동화로 변경 · 시트 정리 · 소스코드에도 반영". 용도 = 계정이력(삭제=관리중단 포함)·계정별 상품 변경이력 보관(D-095 와 같은 파일).
- 버린 대안: 시트 이름까지 변경(코드·HQ 이관 코드·무결성 점검 경로 동시 변경 필요 — 이득 대비 회귀 위험).
- 영향 범위: 코드 동작 변경 없음(문자열·주석) · 운용 PC 설정 탭 원장 링크는 같은 주소. DECISIONS 옛 항목의 '셀독등록원장' 표기는 추가 전용 규칙상 그대로 둠(= 같은 파일). HQ 알림 대상(이름만).
- 상태: ACTIVE

### D-101 [SALES_RANK_ALL_ACCOUNTS] 통합판매현황 ⑤ 계정 순위 = 전 계정 표시(판매 0·미수집 포함) (2026-10-21, R30)
- 결정: ⑤ 가로 막대 차트와 5칸 표에 결과 파일의 **모든 계정**을 보인다 — 판매금액 순 → 판매 0 → 미수집. 순위 번호는 판매 있는 계정만, 판매 0·미수집은 '-'. 미수집 칸 = '미수집'(회색). 표 아래 '판매 없음 N계정' 줄은 삭제(표에 나옴), '미수집 N계정: 이름(사유)' 줄은 유지(사유 표시). D-098 의 '판매 있는 계정만'을 이 부분만 바꿈.
- 근거: 소유자 2026-10-21 "계정별 순위와 시트는 모든 계정을 보여줘"(실제 구글 반영본 확인 후). 시험 T11: 표 3계정(a1 1위·a3 '-' 0·a2 '-' 미수집)·차트 범주 3개 확인(통과).
- 버린 대안: 판매 있는 계정만 + 판매 없음 한 줄(D-098 — 소유자가 전 계정 요청).
- 영향 범위: `workbook_sales_dash._ranks` · `tools/verify_sales_summary_offline.py`(T11) · `designs/SALES_SUMMARY.md` §5-1. 일별 상세표는 이미 전 계정 소계를 보임(상품 줄은 31일 중 판매 있는 상품만 — D-064 그대로).
- 상태: ACTIVE

### D-102 [SALES_DETAIL_ACCOUNT_BLOCK] 통합판매현황 일별 상세표 = 계정마다 한 블록(같은 색 계열 + 바깥 굵은 테두리) (2026-10-21, R31)
- 결정: 일별 상세표에서 계정 하나(소계 2줄 + 상품 줄들)를 한 블록으로 — 소계 = 진한 색·상품 = 같은 계열 연한 색, 계정마다 파랑(D9E2F3/EEF3FB)·초록(E2EFDA/F3F9EF) 번갈아, 블록 바깥 변만 굵은 테두리(medium·595959)·안쪽 가는 선 유지. 전체 합계·미수집 계정 수 줄은 그대로(노랑).
- 근거: 소유자 2026-10-21 "계정별 상품별 동일 그룹은 1개의 블럭으로 … 테두리선을 진하게 또는 소계와 상품리스트와 판매내역을 같은 색상으로 구분해서 계정별로 시각적으로 구분"(구글 반영본 화면 — 소계만 회색·상품 흰색이라 계정 경계가 안 보임). 둘 다 적용. 시험 T4(계정마다 다른 색·소계/상품 같은 계열·바깥만 굵게) 통과 · Excel 그림으로 확인.
- 버린 대안: 테두리만 또는 색만(소유자 '또는' — 둘 다 적용해도 서로 방해 없음) · 계정마다 다른 색 여러 개(27계정이면 색이 많아 산만).
- 영향 범위: `workbook_sales.py`(_BLOCK_FILLS·_EDGE·_outline·_write_section) · `tools/verify_sales_summary_offline.py`(T4) · `designs/SALES_SUMMARY.md` §5. 구글 미러 = 배경색·SOLID_MEDIUM 테두리 그대로 옮김(gsheet_stats._borders).
- 상태: ACTIVE

### D-103 [SETTLE_ACCOUNTS_FROM_REGISTRY] 정산 다운로드 계정·비밀번호 = 셀독계정상품이력관리원장(셀독원장 + 정산전용계정 시트) · 원장 동기화 26시간 넘으면 정산 중단 · 계정아이디 형식 오류 = '오입력' (2026-10-21, R32)
- 결정: (1) 정산 계정 = 셀독원장의 최근 90일 관리 계정(관리중 + 관리중단 뒤 90일 이내) − 오입력 + '정산전용계정' 시트(관리중 또는 중단일 90일 이내)·비밀번호 = 원장 값·중복 = 셀독원장 우선(`accounts_from_registry`). 설정 `settlement/account_source` 기본 registry · file 이면 옛 파일. (2) 원장 마지막 동기화가 26시간보다 오래면 정산 계정 구성 중단·상태 카드 '종료 ❌ 이유'(옛 파일로 대신하지 않음). (3) 원장 파일에 '정산전용계정'(사람 편집)·'정산전용이력'(앱이 매 동기화 변경 기록) 시트 추가 · 정산 계정 파일의 정산전용 11계정을 옮김(`tools/registry_settle_import.py` · 한 단어 이름 = 사업자명). (4) 계정아이디 형식 오류(영문·숫자 시작·영문·숫자·._@- 외 문자) = 대장에서 새로 들어와도 원장에 안 넣고 경고 · 이미 들어간 것은 '오입력' 이력 1회(상태 오입력·정산·로그인·입력 제외) · 로그에서 가림.
- 근거: 소유자 2026-10-21 "정산파일 다운로드시 셀독계정상품이력관리원장_자동화에서 계정과 비밀번호를 가져와 로그인 · 변경이력을 매일 점검해 현황화" → 검토 의견(조건 4가지) → "제안한 순서대로 2번부터 진행". 실측: 정산 계정 파일 35 ↔ 원장 33 — 관리대장 4계정(가디즌·온라이프·꿈꾸는아재·더이룸랩) 정산 누락 · 정산만 하는 11계정 원장에 없음 · 원장에 계정아이디가 비밀번호 값인 줄 1개(10-19 대장 오입력 · 계정 44개 중 형식 위반 이 1개뿐). 시험: verify_registry_offline R24(오입력)·R25(정산전용 시트·이력) · verify_settlement_runtime_offline P37(계정 구성·90일·중복·신선도).
- 버린 대안: 계정아이디에 비밀번호가 포함되면 오입력(정상 계정도 걸림 — 비밀번호에 계정ID 를 넣는 계정 2개 실측) · 정산전용 계정을 셀독원장 줄로 추가(무결성 점검·관리대장 동기화가 관리중단으로 돌림) · 원장 실패 시 옛 파일로 대신(폴백 금지).
- 영향 범위: `registry_model`(K_MISTAKE·ST_MISTAKE·valid_account_id) · `registry_core`(상태 재생·mistaken_ids) · `registry`(sync 형식 검사·_mark_mistaken) · `registry_gsheet`(_sync_settle_sheet·로그 가림) · 신규 `registry_settle.py`·`tools/registry_settle_import.py` · `settlement_accounts`(accounts_from_registry·last_sync_time) · `tools/settlement_download`(load_accounts 출처·watch 실패 상태) · 시험 3개 · LEDGER_REGISTRY §14. 운용 PC: 원장 링크 원복(D-095) 뒤 첫 18:00 동기화부터 · 표시 이름 11계정이 원장 기준으로 바뀌어 정산 기록·파일 이름이 새 이름으로 맞춰짐(설계된 자동 이름 맞춤) · 관리중단 90일 이내 4계정(lslfgh·plan_it·seankim137·unipang)이 새로 정산 대상. HQ 포팅 대상.
- 상태: ACTIVE

### D-104 [SALES_CHART_NO_OVERLAP] 통합판매현황 차트 높이 = 비워 둔 행 − 1줄(구글 행 20px·엑셀 15pt 기준) — ⑤ 막대 차트가 아래 표를 덮던 결함 수정 (2026-10-21, R33)
- 결정: 차트 높이 계산의 행 높이를 구글 20px(실측)·엑셀 15pt(행 높이 하한 — 실측 16.5pt PC 도 안전)로 바꾸고, 높이 = (차트 아래 비워 둔 행 수 − 1) × 행 높이. ⑤ 막대 차트의 비워 둘 행 수도 20px 기준으로 계산.
- 근거: 소유자 2026-10-21 "계정별 순위 도표와 세부 내역이 겹쳐서 보여"(구글 화면 캡처). 구글 실측(b1d5fd9 반영본): ⑤ 차트 44행·높이 756px = (37−1)×21px, 비워 둔 44~80행 = 37×20px = 740px → 표 머리줄·1위 줄을 16px 덮음(전 계정 26개로 늘어 행이 많아지자 21px−20px 차이가 쌓임). 시험 재현: '차트 아래 끝 ≤ 아래 내용 줄'(구글 20px·엑셀 15pt, 계정 26개) — 수정 전 '756 > 740' 실패 → 수정 후 통과. Excel COM 실측(계정 26개): ⑤ 차트 아래 끝 1270.5pt < 표 머리줄 1342.5pt.
- 버린 대안: 행 높이를 시트에 직접 지정(미러가 1행 높이만 옮김 — 구글 반영 요청 추가 필요·과함).
- 영향 범위: `workbook_sales_dash.py`(XL_ROW_PT·G_ROW_PX·geometry 설명) · `tools/verify_sales_summary_offline.py`(_free_rows_below·_many_accounts_wb·T5·T11) · `designs/SALES_SUMMARY.md` §5-1. 차트가 조금 낮아짐(②③④ 엑셀 231→210pt·구글 294→280px).
- 상태: ACTIVE

### D-105 [SALES_FROM_APRIL_MONTHLY] 통합판매현황 판매 실적 = 4월부터(시작일 상수 하나) · ① 요약에 월별 누계 줄 (2026-10-21, R34)
- 결정: ① `sales_summary.FIRST_DAY` = 2026-04-01 하나로 월별 기간 조회·대시보드 월(② 월별 차트·① 월별 누계)·일별 소급 시작을 통일(`BACKFILL_FROM` 물리 삭제). 1~3월 기간 기록은 파일에 남겨 두되 읽지·조회하지 않음(표시 안 함). ② ① 요약 = 전일·지난주·이번 달 누계 → 미수집 계정(전일) → '월별 누계' 머리줄 → 4월~이번 달 한 줄씩(판매금액·수량·증감·비교 기준). 끝난 달 = 전월(통째) 대비, 진행 중 달 '10월 누계 10.01~10.DD' = 지난달 같은 기간 대비(이번 달 누계와 같은 값), 시작월(4월) = 비교 없음. 미수집 계정이 섞인 달은 비교 기준 칸에 '미수집 N계정(이름) 제외'.
- 근거: 소유자 2026-10-21 "요약시트에 월별 누계도 포함해줘. 그리고 판매 실적은 4월부터 해줘. 연관되는 부분도 검토해줘". 검토: (a) 월별 수량 = 일별 다 있으면 일별 합, 아니면 쿠팡 기간 합계 — 둘 다 옵션별 판매수량을 저장(sales_history.record·record_period)하므로 수량도 같은 출처 (b) 관리 상품 기준 = scope 가 일별·기간 기록 모두에 적용 → 월 합계도 관리 상품(상세표·요약과 같음) (c) 요약 줄이 늘어 차트가 아래로 밀려도 차트 위치는 행 기준이라 그대로 맞고, 시험 '차트 아래 끝 ≤ 다음 내용 줄'(구글 20px·엑셀 15pt·계정 26개) 통과 (d) 지난달 같은 기간 계산·소급 시작일과 같은 상수. 시험 T1(4~10월 7개·상수 하나)·T7·T10(월별 누계 값·비교 기준)·T11(① 월별 줄·4월 전 달 없음) 통과.
- 버린 대안: 1~3월 기간 기록 삭제(되돌릴 수 없음·불필요) · 4월 줄도 3월 대비(3월 = 시작월 밖이라 표시 안 하는 값과 비교하게 됨) · 진행 중 달도 전월 통째 대비(누계 대 한 달 전체라 늘 감소로 보임).
- 영향 범위: `sales_summary.py`(FIRST_DAY·BACKFILL_FROM 삭제) · `sales_dashboard.py`(month_kpis·_month_kpis) · `workbook_sales_dash.py`(_kpis·_kpi_head·_kpi_row) · `tools/verify_sales_summary_offline.py`(T1·T7·T10·T11) · `designs/SALES_SUMMARY.md`. 매일 기간 조회 = 4월부터(1~3월 조회 없음). 구글 반영 = 계정ID 정리 후 운용 세션.
- 상태: ACTIVE (부분 SUPERSEDED by D-161 · D-165 — '1~3월 기간 기록은 읽지·조회하지 않음' 중 조회: 정산 실행은 2026-01-01부터 조회·수집 · 표시·① 판매수집은 4월부터 그대로)

### D-106 [INDEX_SHEET_LAYOUT_V2] 결과 구글시트 '계정목록' = 10열(상태=상품명 오른쪽·모니터링 종료일 삭제) · 행 고정 2 매번 보정 · 그로스재고 헤더 2줄 · 회사보유재고 칸 안 줄바꿈 (2026-10-21, R36)
- 결정: ① 열 배치 = A 대표자 · B 사업자 · C 계정ID · D 상품명 · **E 상태** · F 회사보유재고 · G 그로스재고 · H 체험단 시작일(자동 D-087) · I 체험단 종료일(직원 입력) · J 체험단효과. '모니터링 종료일' 열 삭제 — 계정목록에서 더 읽지 않음(mkt_mon = ''). ② 옛 11열 시트는 sync 때 자동 이전(`_ensure_status_layout`: 제목 병합·열 고정 해제 선커밋 → 모니터링 열 삭제[값 개수 로그] → 상태 열 이동 → 제목 재병합[장식·비치명]·헤더 라벨 판정·멱등). ③ 증분 동기화마다 제목·헤더 **2행 고정**(행만 — 열 고정은 제목 병합과 400). ④ 그로스재고 헤더 = '그로스재고⏎(자동갱신 MM.DD)' 2줄(헤더 행 줄바꿈 허용·세로 가운데). ⑤ 회사보유재고 칸 = 칸 안 줄바꿈 + 폭 130~190px(옵션 여러 개도 옆 칸으로 넘지 않음).
- 근거: 소유자 2026-10-21(화면 캡처) "1. 계정목록 두번째줄 제목은 틀고정 2. 상태 컬럼을 상품명 다음으로 3. 모니터링 종료일 삭제 4. 그로스재고 (자동갱신 10.20) 2줄로 5. 회사보유재고가 칸을 넘어감 → 해당 칸에 표시·약간 넓혀서". 실측(결과 시트 API): 행 고정 0(전체 생성 때만 걸고 증분은 안 걸었음) · 모니터링 종료일 93행 전부 빈 칸(삭제로 잃는 값 0) · 체험단 종료일도 0칸. 시험 [6d](옛 11열 → 10열 이전·값 함께 이동·재병합·멱등·행 고정·헤더 2줄)·[6](E 상태·F 줄바꿈)·[4](모니터링 되읽지 않음) 통과.
- 버린 대안: 모니터링 열을 숨김(직원이 계속 입력하면 읽지도 않는 값이 쌓임) · 회사보유재고 폭을 내용에 맞춰 크게(소유자: 너무 넓으면 보기 안 좋음) · 열 고정 추가(제목 병합과 충돌 400).
- 영향 범위: `gsheet_index.py`(열 상수·_HEADS·_auto_cells_request·_stock_cell·_header_request·_freeze_rows_request·_ensure_stock_columns 판정=라벨·_ensure_status_layout 신설·read_marketing) · `tools/verify_gsheet_offline.py`([3]·[4]·[6]·[6d]·가짜 클라이언트 열 삭제) · `designs/GSHEET_UNIFIED.md`. 수집 주기(product_cadence)의 모니터링 종료 'stop' 은 관리대장 '모니터링종료일' 열(있으면)만 남음. 마스터 xlsx 숨김 시트(_마케팅)·`계정 목록`은 그대로.
- 상태: ACTIVE (부분 SUPERSEDED by D-109 — 열 수·체험단 종료일 열)

### D-107 [SALES_SCOPE_WHOLE_LISTING] 통합판매현황 관리 상품 = 상품 전체 — 블록 VID 와 상품명이 같은 다른 VID(판매자배송·다른 수량 옵션·재등록)도 포함 · 위탁자 본인 상품은 계속 제외 (2026-10-21, R38)
- 결정: 집계 범위 = 관리 계정(결과 파일 계정)의 관리 상품. 관리 상품 판정 = ① 결과 사업자 시트 블록 VID(판매중지 블록 포함·D-094) ② 그 VID 로 팔린 판매 기록(일별·기간 저장 전부)의 **상품명**과 같은 상품명으로 팔린 같은 계정의 다른 VID. 상품명 비교 = 공백 정리 후 완전 일치(`sales_summary.managed_listings`·`scope(…, listings)`). 다른 계정의 같은 상품명은 무관.
- 근거: 소유자 2026-10-21 "판매현황 통계는 관리계정별, 관리상품만 반영 — 위탁자 본인이 등록한 상품도 많음" + 3안 중 "(가) 상품 전체". 실측(운용 PC 10-21 사본·일별 189계정일): 관리 VID 19,279,760원 · 위탁자 본인 등 다른 상품 40,542,430원(계속 제외) · **같은 상품명·다른 VID 2,847,140원이 빠져 있었음**(원더풀리 파미젠 윙 933,100·벅스 이큐나라 윙 520,000·파미젠 2개 옵션 359,000 등). 9월 기간 합계 34,331,100 → 47,358,370(늘어난 상위 = 휴라엘 넥메딕스 윙 2,345,000·니코에이블 기저귀가방 윙/로켓그로스 1,697,390·파미젠 윙 1,383,200 — 전부 관리 상품의 판매자배송·같은 옵션). 판매 기록엔 등록상품 번호가 없고 관리대장 등록명은 판매 기록 상품명과 다름(108개 중 12개만 같음) → 판매 기록 상품명으로 묶음.
- 버린 대안: (나) 대장에 적힌 옵션만(배송방식 무관) · (다) 지금처럼 블록 VID 만 · 등록명(대장)으로 묶기(판매 기록 상품명과 대부분 달라 못 묶음).
- 한계(사실): 관리 VID 가 판매 기록에 한 번도 없으면(4/1 이후 판매 0) 그 상품의 다른 VID 판매도 못 묶음 — 관리 VID 판매가 생기면 그때부터 묶임. 위탁자가 관리 상품과 **똑같은 상품명**으로 따로 등록한 상품은 구분 불가(같은 상품으로 셈).
- 영향 범위: `sales_summary.py`(managed_listings·scope) · `workbook_sales.refresh_sales_sheet` · `tools/verify_sales_summary_offline.py`(T9) · `designs/SALES_SUMMARY.md`. 정산서(git 밖·쿠팡 정산 세션)는 별도 — '7:3 계정 합산'과 '개인상품 제외' 규칙의 관계는 정산 세션 확인 필요.
- 상태: ACTIVE

### D-108 [PROMO_END_NO_CADENCE] 계정목록 '체험단 종료일'만 적어도 수집·순위 주기는 그대로(매일) — 수집 주기 게이팅은 시작일·모니터링 종료일만으로 판정 (2026-10-21, R39)
- 결정: `OutputWorkbook.has_marketing()`(3일 주기 게이팅 활성 조건)은 숨김 `_마케팅` 시트의 **시작(3열)·모니터링종료(5열)** 만 본다. 종료(4열)만 있는 상품은 게이팅을 켜지 않는다. 종료일은 그대로 저장돼 '체험단중/종료' 상태·기간 배경색에만 쓰인다.
- 근거: 소유자 2026-10-21 "체험단 종료일 문제 수정해줘". 재현(simulate 26b): 직원이 계정목록 b1 상품에 '체험단 종료일'만 입력 → 수정 전 `has_marketing()=True` → `account_due`·`product_due` 게이팅이 켜져 마케팅 없는 상품이 3일 주기(판매·순위 건너뜀)로 바뀜(D-087 이 시작일에서 막은 것과 같은 구조가 종료일에 남아 있었음). 수정 후 has_marketing=False·09.03 판매·순위 모두 수집. 실측(10-21 결과 시트): 체험단 종료일 0칸 — 아직 영향 없었음.
- 버린 대안: 계정목록 종료일 칸을 읽지 않기(직원 기록이 체험단 상태 표시에 쓰이지 못함) · 종료일 열 삭제(소유자 요구 아님).
- 영향 범위: `workbook_meta.has_marketing` · `tools/simulate_pipeline.py`(시나리오 26b). 직원 매뉴얼 '체험단 종료일 = 지금은 비워 두세요' 안내 해제.
- 상태: ACTIVE (부분 SUPERSEDED by D-109 — 계정목록 '체험단 종료일' 열 삭제(새 시트엔 직원 입력 없음) · D-121 — 종료일 기간 배경색(옛 '마케팅 기간 연주황') 삭제·has_marketing = 시작/모니터링종료만 판정은 그대로)

### D-109 [INDEX_DROP_PROMO_END] 결과 구글시트 '계정목록' '체험단 종료일' 열 삭제 → 9열(직원 입력 열 없음) (2026-10-21, R40)
- 결정: 계정목록 = A 대표자 · B 사업자 · C 계정ID · D 상품명(클릭 이동) · E 상태 · F 회사보유재고 · G 그로스재고 · H 체험단 시작일(자동) · I 체험단효과. '체험단 종료일' 열 삭제. 옛 시트(10열·11열)는 sync 때 `_ensure_status_layout` 이 옛 직원 입력 열('모니터링 종료일'·'체험단 종료일')을 오른쪽부터 지우고(값 개수 로그) 상태 열을 E 로 옮김. `read_marketing`·`apply_marketing` 는 계약(L1 핀) 유지 — 새 시트에선 직원 입력 열이 없어 빈 dict, 이전 전 옛 시트의 종료일만 읽음.
- 근거: 소유자 2026-10-21 "그럼 종료일은 시트에서 항목 삭제하자"(D-108 후 종료일 = 체험단 시작일[자동]과 함께 쓰이지 않아 상태 표시에도 안 쓰이는 단순 기록 칸이라는 설명에 대해). 실측(10-21 결과 시트): 체험단 종료일 0칸 — 지워도 잃는 값 없음. 시험 [6d](11열→9열·10열→9열·값 함께 이동·지운 값 개수 로그·멱등)·[3](데이터 행 기록 9열 안)·[6](바탕색 A~G+I) 통과.
- 버린 대안: 열은 두고 숨기기(직원이 계속 입력 시 의미 없는 값 누적) · 종료일을 체험단 상태 계산에 연결(소유자 요구 아님).
- 영향 범위: `gsheet_index.py`(열 상수·_HEADS·_mkt_fill_request·_drop_obsolete_columns·_ensure_status_layout·read_marketing 라벨) · `tools/verify_gsheet_offline.py` · `designs/GSHEET_UNIFIED.md` · CLAUDE.md. ⚠ 운용 PC 가 옛 버전이면 옛 열 위치로 써서 칸이 어긋남 → 구글 시트 이전은 새 버전 첫 실행에서 자동(노트북에서 먼저 적용하지 않음).
- 상태: ACTIVE

### D-110 [SALES_RANK_RECENT_MONTH] 통합판매현황 ⑤ 계정 순위 = 최근 1개월(어제까지 30일) 누계 — 이번 달 누계 대신 (2026-10-22, R46)
- 결정: ⑤ 가로 막대·5칸 표의 금액과 정렬 기준을 '이번 달 누계(1일~어제)'에서 **최근 1개월 = 어제 포함 30일**(`sales_dashboard.recent_month`·`RECENT_DAYS = 30`)로 바꾼다. 띠·차트 제목에 기간(예 '09.21~10.20')을 보인다. 값 = 30일 일별 기록 합 — 하루라도 없으면 그 계정 '미수집'(쿠팡 기간 합계 추가 조회 없음 · ① 의 이번 달 누계·월별 누계·지난주·전주 대비는 그대로).
- 근거: 소유자 2026-10-22 "통합판매현황 시트에서 5번 이번달 누계를 최근 1개월간 누계(전계정)로 변경해줘"(⑤ 차트 캡처). 실측(10-21 결과 시트 '미수집 계정 수' 줄): 09.20~10.20 31일 일별 기록이 유라이프·와이에이치 빼고 전 계정에 있음 → 30일 일별 합으로 충분(두 계정은 이번 달 누계에서도 미수집). 시험 T10(a1 = 9/21~30 1,000×10 + 10/1~20 1,500×20 = 40,000)·T11(표 머리줄 '최근 1개월 누계(원)'·차트 제목 기간) 실패 재현 → 수정 후 통과.
- 버린 대안: 달력 기준 한 달(지난달 같은 날 다음날~어제 — 달마다 28~31일로 길이가 달라짐) · 쿠팡 기간 합계 'R:' 키 추가 조회(① 로그인 세션에 조회 1회 추가 — 일별 소급이 이미 덮어 불필요) · 30일 중 받은 날만 합산(빠진 날이 있는 계정이 작게 보여 순위 왜곡).
- 영향 범위: `sales_dashboard.py`(recent_month·Dashboard.rank_span·build) · `workbook_sales_dash._ranks`(띠·차트 제목·표 머리줄) · `tools/verify_sales_summary_offline.py` T10·T11 · `designs/SALES_SUMMARY.md` §5-1 · `tools/build_staff_manual.py` 5쪽·FAQ 문구. 결과 구글시트 반영 = 새 버전 실행 때(통제 세션).
- 상태: ACTIVE

### D-111 [TRANSFER_LOGIN_CHECK] 미정산 셀독전환자 ①②계정 정산 — 1단계 = 로그인 확인 전용 명령·탭 · 정산 계정(원장)·기록과 분리 (2026-10-22, R47)
- 결정: ① 입력 = 셀독전환자 파일(설정 `transfer/file`)의 ①·② 시트 103계정(`transfer_accounts.read_transfer_file` — 머리줄 이름으로 칸·계정명 중복 = 중단·비번 공백 = 떼고 경고). ② 비밀번호 = 파일 값 먼저 → 관리대장 저장 값(빈 칸이면 관리대장), 최대 2개(D-012)·D-068 그대로. ③ `정산다운로드.exe transfer-login`(`transfer_login.run`) = 앱 ①과 같은 로그인 함수로 로그인만 확인 → `output/정산_셀독전환/` 결과 JSON·엑셀('로그인 결과'·'연락 필요'). ④ 안전 = 앱 파이프라인·정산 watch 잠금 확인(돌면 멈춤)·17:40 이후 새 계정 안 함·계정 사이 45~75초·차단 2연속 전체 중단·프록시 없음. ⑤ 앱 '셀독전환 정산' 탭(시작·성공 안 된 계정만 다시·중지·결과 폴더)이 결과·로그 파일을 3초마다 읽어 표시(배포 exe 콘솔 없음). ⑥ 원장(D-103) 정산 계정·`output/정산` 기록·정산 상태 화면과 섞지 않음(계정 출처·목적 다름 — 미정산 원금 공제용).
- 근거: 소유자 2026-10-22(셀독 전환자 파일 분석 세션 전달·이 세션 질문 답) "정상 로그인 되는지부터 확인" · "비번 빈 계정 = 관리대장 비번 적용" · "비번 오류로 접속이 불가한 것은 별도로 리스트 작성(개별 연락)". 실측(노트북 파일): ①52·②51 = 103계정·계정명 형식 오류 0·중복 0·비번 공백 1(jljhome1)·이 PC 기준 비번 없음 10(운용 PC 관리대장 저장 값은 다를 수 있음). 시험 verify_transfer_offline T1~T7(파일·오류·비번 후보·실행/엑셀·멈춤·잠금 감지·판정 분류)·결과 파일 비밀번호 0건.
- 버린 대안: 정산 계정 출처에 'transfer' 추가(원장 정산 기록·상태 화면·이름 변경 이전과 섞임) · 파일 비번 무시하고 관리대장만(②는 대부분 관리대장에 없음) · 로그인 확인을 18:00 흐름에 자동 편입(1단계는 소유자 확인용·로그인 103회 추가 = IP 위험).
- 영향 범위: 신규 `transfer_accounts.py`·`transfer_login.py`·`ui/transfer_panel_qt.py`·`tools/verify_transfer_offline.py` · `app_process.transfer_login_cmd/start_transfer_login` · `tools/settlement_download.py`(명령 1개 전달) · `ui/app_qt.py`(탭 1줄) · `tools/run_checks.py` · `designs/SETTLEMENT_MODULE.md §15` · `designs/FEATURE_INVENTORY.md`. 2단계(정산 다운로드·자동 실행 빈도)는 미결정.
- 상태: ACTIVE (부분 SUPERSEDED by D-112 — ④ 멈춤·중단: '17:40 이후 새 계정 안 함' → 시작 뒤 처음 오는 17:40 에 멈춤 + 17:40~20:40 시작·새 계정 안 함·'차단 2연속 전체 중단' → 차단/미완료/오류 2계정 연속 · 2단계 정산 자료 받기 빈도 = 매일 18시 뒤(소유자 D-179) · 2단계 구현 = D-187)

### D-112 [TRANSFER_LOGIN_NIGHT] 셀독전환자 로그인 확인 — 밤에 이어 하기(--start)·운용 PC 실행 시간대 피함·차단/미완료/오류 2연속 중단·같은 틀린 비번 재시도 금지 (2026-10-22, R48)
- 결정: ① `--start HH:MM` = 그 시각까지 기다렸다 시작. 멈춤 시각(기본 17:40) = 시작 뒤 처음 오는 그 시각(밤 시작 = 다음 날 17:40). ② 17:40~20:40(QUIET_HOURS 3 — 운용 PC 18:00 ①판매수집·정산 로그인 시간대)엔 시작·새 계정 안 함 — 이 PC 잠금으로는 다른 PC 를 못 봐서 시각으로 피함(같은 사무실 IP 동시 로그인 방지). ③ 전체 중단 = 차단뿐 아니라 **차단·미완료·오류 2계정 연속**. ④ 재시도 = 성공·'비밀번호 맞음 — 2단계 인증 필요' 제외 · 비밀번호 오류는 시도한 값의 지문(login_today.fingerprint HMAC)과 지금 후보가 다를 때만 · 결과 JSON 에 지문 저장(비밀번호 값 아님). ⑤ 2단계 인증 사유 = '비밀번호 맞음 — 2단계 인증 필요(계약자 휴대폰 인증번호 — 연락 필요)'.
- 근거: 소유자 2026-10-22 "나머지는 18시 이후에 이어서 처리되도록" · "비밀번호 맞음(인증번호 필요) 9도 연락이 필요한 건". 실측(오늘 14:23~15:10 28계정): 15:08 Akamai 차단 화면 → '미완료(unknown)'로 기록돼 차단 2연속 장치가 안 셈 · 다음 계정 브라우저 연결 오류(ECONNREFUSED) · 비번 오류 14·인증번호 9·성공 3. 운용 PC ① 끝 = 10-15~18 18:44~19:06(그 뒤 정산 로그인). 옛 멈춤 판정(시:분 비교)은 밤 시작 시 즉시 멈춤. 시험 T5·T7·T8 재현 → 수정 후 통과. 오늘 결과 JSON 28건에 지문 보강·인증번호 사유 9건 갱신 → 재시도 대상 77(미확인 75·미완료 2).
- 버린 대안: 운용 PC 정산 자동 수집 끝에 이어 붙이기(오늘 밤 배포·파일 복사 필요 — 2단계 때 검토) · 비번 오류도 다시(같은 틀린 값 재제출 = 계정 잠금 위험·D-068 은 그날만 막음) · 차단만 셈(실측상 차단이 미완료로 끝남).
- 영향 범위: `transfer_login.py`(deadline_of·in_quiet·wait_until·pick/_retry_needed·save_result 지문·run) · `tools/settlement_download.py`(--start) · `tools/verify_transfer_offline.py` T5·T7·T8 · `designs/SETTLEMENT_MODULE.md §15`.
- 상태: ACTIVE

### D-113 [SHEET_LINK_ABSOLUTE] 결과 구글시트 시트 사이 링크 = 파일 전체 주소(`…/edit?gid=X#gid=X&range=A행`) — 모바일 시트 앱에서도 열리게 (2026-10-23, R50)
- 결정: 계정목록 상품명 → 사업자 시트 블록 링크와 사업자 시트 1행 '👈 계정목록으로 이동' 링크를 상대 주소 `#gid=…&range=…` 대신 **파일 전체 주소 + 탭**(구글 '시트 링크 복사' 형식 `https://docs.google.com/spreadsheets/d/<파일ID>/edit?gid=X#gid=X` + `&range=A행`)으로 만든다(`gsheet.sheet_link`). 파일 ID 가 없으면 링크를 만들지 않고 예외(상대 링크로 조용히 대체 금지). 계정목록은 매 실행 모든 행의 자동 칸을, 사업자 시트는 통째로 다시 쓰므로 새 버전 첫 실행에서 기존 링크도 모두 바뀜. 엑셀(xlsx) 파일 안 링크는 그대로(엑셀 내부 위치 링크).
- 근거: 소유자 2026-10-23 "결과파일을 모바일에서 열고 계정목록에서 상품명을 클릭하면 해당 시트로 이동해야 하는데 안됨 · 시트 상단 계정목록 클릭도 안됨". 코드 = 두 곳 모두 `=HYPERLINK("#gid=…")` 상대 링크(gsheet_index._product_cell·gsheet_stats._cell_value). 상대 링크는 PC 브라우저에서만 같은 파일 안 이동으로 처리됨(모바일 앱 동작은 공식 문서로 확정 못 함 — 소유자 휴대폰 실측으로 확인 필요). 시험: verify_gsheet_offline [5]·[6](전체 주소·파일 ID 없으면 예외)·정밀렌더·L1 계약 핀(worksheet_to_requests 선택 인자 doc_id 추가) 재현→수정→통과·게이트 15종.
- 버린 대안: 상대 링크 유지 + 사용 안내(앱에서 안 됨) · 링크 대신 시트 목록 안내(이동 불가).
- 영향 범위: `gsheet.py`(sheet_link) · `gsheet_index.py`(_product_cell·_auto_cells_request·_build_requests_for_plan·_full_build_requests·sync_index) · `gsheet_stats.py`(_cell_value·worksheet_to_requests·push_statistics) · 시험 3종·핀 · `designs/GSHEET_UNIFIED.md`. HQ R0_DATA_CONTRACT: 링크 형식만 바뀜(시트·열 구조 동일).
- 상태: ACTIVE

### D-114 [RANK_INCLUDE_REJECTED] 쿠팡 판매상태 '승인반려' 상품도 노출순위 조사 — 순위 제외는 판매중지·임시저장·검토중·대장 취소선만 (2026-10-26, R51)
- 결정: ③ 노출순위 조사 대상에서 빼는 쿠팡 판매상태(`workbook_common._NOT_SELLING_STATUSES`)에서 '승인반려'를 뺀다 → 승인반려 상품은 순위를 잰다. 판매중지·임시저장·검토중·대장 취소선(숨김)은 지금처럼 제외. 판매 정보 수집은 원래부터 상태와 무관.
- 근거: 소유자 2026-10-26 "승인반려인 경우에도 노출순위는 조회되어야 함". 실측(output(26)·결과 시트): 휴라엘 '디프 노브라 누드브라 실리콘 니플패치 원형 10매'(vid 96205126338) 판매상태 10.20 판매중 → 10.21~ 승인반려, 노출순위 10.21~10.25 빈 칸(③ 로그에 이 상품 순위 줄 없음 = rank_suppressed). 시험 pin_apply_style S7(승인반려 → 순위 조사) 재현→수정→통과.
- 버린 대안: 빈 칸 대신 '순위 제외(승인반려)' 표시만(소유자 요구 = 조사).
- 영향 범위: `workbook_common.py`(_NOT_SELLING_STATUSES) · `workbook_meta.rank_suppressed` 설명 · `pipeline_ranks` 주석 · `tools/pin_apply_style.py` · CLAUDE.md 운영 정책 줄. D-084(대표 판매중지여도 옵션 판매중이면 순위)와 무관 — 그대로. 순위 키워드 수가 승인반려 상품만큼 늘어남(③ 시간 소폭 증가).
- 상태: ACTIVE (2026-09-22 '판매중/부분판매중만 순위' 중 승인반려 부분을 대체)


### D-115 [WING_CYCLE_EXTRA] 윙 정산주기 코드 'B' = 추가정산 — 받기 방법 미확인 → 그 줄만 건너뛰고 처리기록 '확인 필요' · 계정 전체 중단 금지 (2026-10-26, R54)
- 결정: `settlement_wing_api._WING_UNSUPPORTED` 에 `'B': '추가정산'` 추가 → 윙 정산현황에 B 줄이 있어도 그 줄만 건너뛰고(D-010) 처리기록에 '확인 필요 — 받기 방법 미확인 정산주기 추가정산 코드 'B' …'를 남기며, 같은 계정의 다른 주기(주정산·최종액·월정산)는 계속 받는다. 다른 모르는 코드는 지금처럼 SiteChangedError(사이트 변경 감지).
- 근거: 소유자 2026-10-26 "B 코드 건 쿠팡 정산 세션에 전달"(통제 세션 경유). 실측(운용 PC output(26) `정산/로그/처리기록_누적.csv`): roum0502 10-22 12:47·10-22 22:14·10-23 02:37·10-23 21:53·10-24 22:43·10-25 21:56 매번 `SiteChangedError: 윙 모르는 정산주기 코드: 'B' (지급일 2026-10-22)` → 계정 전체 실패. 같은 자료 검증자료 일정에 `transactionCycleCode 'B'` = 제목 '[추가정산] 10/20 ~ 10/20'·시작 2026-10-22(코드 B 전체 1건·다른 계정 없음). 시험 verify_settlement_runtime_offline P38 재현(수정 전 실패)→수정→통과 · run_checks 15종 초록.
- 버린 대안: B 를 주정산처럼 받기 — 추가정산 파일을 같은 '엑셀 다운로드 요청'으로 받을 수 있는지 실측 근거 없음(틀리면 엉뚱한 파일·누락을 정상으로 기록).
- 영향 범위: `settlement_wing_api.py`(상수 1개) · `tools/verify_settlement_runtime_offline.py`(P38). 추가정산 금액 자체는 지급 내역(정산현황 지급 줄)에는 그대로 들어오므로 정산 장부·정산서 금액은 영향 없음(파일 받기만 미확인). 받기 방법이 확인되면 `_WING_KIND` 로 옮김.
- 상태: ACTIVE

### D-116 [SETTLE_MANAGED_SCOPE] 위탁정산서 = 관리 상품만 · 계정 단위 항목 배분 기준 · 1원 정산용 수집 5종 추가 (2026-10-26, R55)
- 결정(소유자가 Claude 에 판단 위임 후 "순서대로 진행" 승인, 2026-10-26):
  ① 위탁정산서는 **관리 상품만**(D-107 범위 = 결과 블록 VID + 같은 노출 상품명 VID). 정산 원본 **옵션ID = 판매분석 VID** 로 등록상품ID 를 찾아, 관리 VID 가 있는 등록상품은 상품 전체를 관리로 본다(정산 등록상품명 ≠ 노출상품명이라 이름 대응 금지). 관리대장 밖 정산 계정은 원장 '정산전용상품' 시트(구분 관리|본인상품)로 판정.
  ② 쿠팡이 계정 단위로만 주는 항목의 몫: **광고비 = 광고센터 매출 성장 광고 보고서의 광고집행 옵션ID별 광고비(실값)** · **판매자서비스이용료 = 그 달 판매금액(배송비 제외) 비율** · **밀크런 = 입고 건별 상품 입고 수량 비율** · **우대수수료 환급 = 주문번호 → 그 주문 상품(실값·위탁자 몫)** · **상품 없는 윙 배송비 줄 = 구매확정 전 반품의 고객 부담 왕복배송비 → 주문조회로 찾은 반품 상품을 따라감** · 정산 중 판매 = 확정되면 쿠팡 상품별 값, 그 전엔 같은 달 관리 판매 비율 '추정' 표시 · 입금 완료/예정/보류 = 계정 실제 지급 비율.
  ③ 1원 정산을 위해 정산 수집에 추가(순서): ①추가지급 금액 정산서 반영 ②우대수수료 환급 주문별 엑셀(FAVORABLE_FEE_DETAIL)을 매일 수집 ③상품 없는 배송비 주문 → 주문조회(주문상세·반품정보)로 반품 상품 저장 ④광고센터 매출 성장 광고 보고서(상품 단위) 월별 ⑤밀크런 엑셀 + 로켓그로스 입고 내역.
- 근거: 실측 — 정산 원본 옵션ID↔판매분석 VID 대응(1,006 파일·판매분석에 없는 옵션 1.25억은 거의 유라이프=판매 기록 없음) · 관리 상품 정산 22%(대장 안 20계정 12.28억 중 2.76억) · 상품 없는 배송비 238줄 1,441,000원(6,000·7,000원 230줄·배송완료→확정 7일 미만 209줄), 벅스 윙 주문조회 2건 = 진공포장기 J0058 반품완료(8/6·6/1)·배송비부담 고객·반품배송비 3,000(무료배송 초도 3,000 포함 6,000) · 매출내역 상세에도 상품 없음 · 반품 관리 목록은 8/4 접수건이 8/1~8/30 검색에 0건(목록 신뢰 불가) · 우대수수료 환급조회 칸 = 주문번호·결제/취소일·지급처리일·예상지급일·환급액, 안내문 '우대수수료율 초과 카드수수료를 가맹점에 환급·쿠팡은 반영하여 판매정산' · 광고 보고서 칸 = 날짜·광고집행 옵션ID·광고전환매출발생 옵션ID·광고비 등(벅스 7월 378,986원·옵션 3개) · KB §1-1(추가지급은 추가지급 메뉴에만)·§1-6·§1-2·§2(배송비 종류·반품비 부담)·§12-2.
- 버린 대안: 계정 합계로 7:3·정산서 작성(위탁자 본인 상품 섞임) · 상품명으로 정산↔판매분석 대응(등록명≠노출명) · 광고비를 판매 비율로 배분(상품별 실값이 있음) · 반품 관리 목록 엑셀로 반품 상품 찾기(오래된 반품 미표시) · 배송비 줄을 비율 배분으로 영구 처리.
- 영향 범위: 정산서 스크립트(git 밖 `output/_분석_261013/정산스크립트`, 견본 `D:\토탈셀러\쿠팡 정산 자료\정산서_견본_261026\`) · 정산 수집(`tools/settlement_download.py`·`settlement_verify_collect`·`settlement_evidence_web`) — ③~⑤ 는 화면 실측 후 구현. 알려진 오류(별건): 10/18 기준 정산서 지급 예정 = 기준일 스냅샷에 12-01 로켓그로스 지급 줄이 모든 칸 같게 두 번 → 21계정 10,712,684원 과다(장부가 같은 키 줄 전부 유지·D-085) → 같은 줄 두 번은 한 번만 세도록 수정 필요.
- 상태: ACTIVE (부분 SUPERSEDED by D-119 — 광고비 몫 · SUPERSEDED by D-124 — 입금 배분(D-126 이 승계) · SUPERSEDED by D-126 — 입금 배분 · SUPERSEDED by D-140 — 공제 비율 적용 · SUPERSEDED by D-146 — 정산 중 판매 비율 추정)

### D-117 [SETTLE_COLLECT_1WON] 1원 정산용 수집 5종 구현 — 화면이 쓰는 조회를 실측해 매일/월별 수집 · 개인정보 칸 제외 · 광고 보고서 광고비 ≠ 청구액 (2026-10-26, R57)
- 결정(D-116 ③ 구현): (1) 추가지급 = 이미 수집(`additional`) — 칸 이름은 윙 화면 코드(AdditionalPaymentReportRow)로 확정(지급금액 `finalRewardAmount`·지급구분 `PAID`·지급항목 VENDOR_ITEM/DELIVERY_FEE·옵션ID `vendorItemId`), 정산서(git 밖 `additional_pay.py`)에 금액 + '확인 필요(첫 실제 자료로 칸 확정)' / 없으면 '없음'. (2) 우대수수료 환급 = 엑셀(FAVORABLE_FEE_DETAIL) 요청·10분 대기 대신 **같은 칸을 주는 화면 조회** GET `…/favorablefee/refund/list/data`(결제/취소일 한 달·pageSize 500)를 매일 검증 자료 `favorable` 에 저장(엑셀 원본은 증빙 `evidence` 그대로). (3) 상품 없는 윙 배송비 주문 → GET `/tenants/sfl-portal/return/delivery/{주문번호}` 를 새 주문·조회 실패만 매일 조회해 `returns` 에 누적 — 반품 상품(옵션ID)·사유·배송비 부담·returnDate·반품배송비만 저장(고객 이름·연락처·주소·고객 글 제외). (4) 광고비 원천 월별(달 끝 +3일) `settlement_ads` — 윙 로켓그로스 광고비 내역 엑셀(캠페인별 청구가능 광고비) + 광고센터 매출 성장 광고 보고서(getCampaignList → requestReport 일별·키워드·캠페인 전부 → 완료되면 excel-report 받기), 받을 달이 있을 때만 광고센터를 연다. (5) 밀크런 내역 엑셀 월별 + 로켓그로스 입고 내역(`inbound` — 밀크런번호·상품별 요청/적치 수량) 매일.
- 근거(벅스 bux1004 화면 실측 2026-10-26, 읽기 전용): 추가지급 전 기간 0건·응답 {reports,page,pageSize,totalPages} · 환급 9월 결제분 67건 1,282원 한 번(3개월 조회 = 400·다른 화면에서도 됨)·엑셀 칸(주문번호·결제/취소일·예상지급일·지급처리일·환급액·상태·세금계산서)과 같음 · 반품 2건(16102026647963·24100193844976) = J0058 옵션 95425233537·고객 부담·returnDate 8/6·6/1 = 정산 배송비 줄 구매확정일, 없는 주문 = 200 빈 본문 · 10/18 입력에서 상품 없는 배송비 주문 237건(238줄) = 점검 스크립트와 같음 · 광고: 7월 보고서 합 378,986 vs 윙 광고비 내역 광고비 378,938·**청구가능 378,188 + 부가세 37,819 = 416,007 = 8/10~9/7 로켓그로스 지급 줄 광고비 공제 8줄 합(원 단위)** · GraphQL 문장 3개 서버 검증(조회 2종 정상·보고서 요청은 변수 형식 오류로만 검증 — 실제 요청 안 함) · 밀크런 엑셀 밀크런번호 11322007 = 입고 내역 milkrunSeq · 실제 입고 수량 = stowedQty(receivedQty 0). 시험 P39~P42 재현 실패 → 구현 → 통과 · run_checks 초록.
- 버린 대안: 환급 엑셀 요청을 매일(10분+ 대기·달마다 요청) · 반품 관리 목록(오래된 반품 안 나옴 — D-116) · 주문상세 전체 저장(개인정보) · 광고 보고서 광고비 ×1.1 을 상품 공제로(청구가능과 달라 1원 안 맞음).
- 영향 범위: `settlement_verify_collect.py`(favorable·returns·inbound·orphan_ship_orders·returns_to_ask) · 신규 `settlement_ads.py` · `settlement_evidence_web.open_adcenter`(분리) · `tools/settlement_download.py`(collect_verify 반품 누적·collect_ads) · P39~P42. **운용 PC 재배포 후** 수집 시작(그 전 정산서는 해당 항목 '자료 없음'·비율 배분 '추정'). 광고비 상품 몫 = 캠페인 청구가능액을 보고서 옵션별 광고비 비율로 나누는 안 → 소유자 확인 대기(D-116 ② '실값'과의 관계). 실제 첫 수집(광고센터 열기·보고서 요청)은 운용 PC 로그로 확인 필요. HQ 포팅 대상.
- 상태: ACTIVE — 단, (4)의 '윙 로켓그로스 광고비 내역 엑셀(캠페인 청구가능)'과 광고비 상품 몫 안은 SUPERSEDED by D-119 · D-126 — (1) 정산서 1쪽 추가지급 = 있을 때만 '참고. 쿠팡 정산 밖 별도 입금'에 표시(없으면 '없음' 줄 안 씀)·수집 규칙은 그대로

### D-118 [SETTLE_SNAPSHOT_WINDOW_DEDUP] 기준일 스냅샷 로켓그로스 달 경계 겹침 제거 · 70:30 검산 · 10/18 정산서 정정본(장부 기준일 고정) (2026-10-26, R59)
- 결정: (1) 정산서 스크립트(git 밖) `settlement_ledger.py` 에 `rg_window_overlap` 추가 — 스냅샷 로켓그로스 줄에서 첫 달이 아닌 1일 지급 줄이 같은 키(정산일·기간·비율)로 짝수 벌이면 뒤 조회(그 달 조회) 절반만 남김. 같은 조회 안 같은 키 여러 줄(D-085 보류 해제)은 그대로. (2) 장부 판정 E1 에 70:30 검산 추가 — 끝난 판매 주(기간 끝 ≤ 장부 기준일) 30% 지급대상 ≈ 70% 지급대상 × 3/7, 허용 max(100원, 1%) 넘으면 '다름'(같은 줄 2벌 = 2배로 잡힘). (3) 10/18 기준 정산서 정정본 = `D:\토탈셀러\쿠팡 정산 자료\위탁정산서_20261018기준_정정\`(원본 폴더 보존) + `지급예정_정정표_261026.xlsx`. (4) 정산서를 다시 만들 때는 장부 기준일을 스냅샷 조회일로 고정(`정산스크립트\run_statements_at.py YYYY-MM-DD <business_statements 인자>`) — `business_statements.py` 는 `Ledger(today=datetime.now())` 라 나중에 돌리면 조회 뒤 정산일 줄이 '지난 줄(보류)'로 바뀜.
- 근거: 실측 `정산_기준일조회_261018` — 21계정 12-01 로켓그로스 줄이 키마다 정확히 2벌(1회용 `collect_snapshot.py` 가 `month_windows` 10·11·12월 응답을 거르지 않고 이어 붙임 · `rg_events_body` 조회 끝 = 다음 달 1일 0시 한국 → 11월 조회에 12-01 줄 포함). 쿠팡 화면 중복 아님(12월 조회만 보면 키마다 1줄). 앱 `read_events` 는 `ws<=지급일<=we` 로 거르고 저장은 정산일 단위 교체·예정 기록은 마지막 묶음(D-085)이라 2벌 안 생김 → 앱 수정 없음. 니코에이블 10/5~11 주 70% 646,163 × 3/7 = 276,927 ≈ 30% 줄 276,920(1줄). ljung0622 10/19~25 30% 줄은 두 조회 사이 66,692 → 90,131 로 바뀌어 '모든 칸 같음' 기준(10,712,684원)으로는 66,692 가 남음. 70:30 검산 실측 167주 차 최대 11원. 시험 `test_settlement_ledger.py` 원본 실패(예정 655,509 과다) → 수정 후 통과. 재현: 원본 폴더와 장부 기준일 10-19 재생성 = 30계정 전 칸 같음(26/28) · 10-26 그대로 실행 = 16/28(10-22 줄이 보류로). 정정 결과: 바뀐 칸 = '지급 예정(최종)'만(①~⑥·⑤ 그대로) · 위탁 합계 80,169,568 → 69,399,363(−10,770,205) · 디프픽 −9,171 · 니코에이블 3,304,858 → 2,794,510 · 정정본 필요 위탁 17계정 · 정산 100% 일치 26/28(✘ 유라이프·글로벌셀러 비밀번호 오류, 이전과 같음).
- 버린 대안: 모든 칸이 같은 줄만 한 번 세기(조회 사이 금액이 바뀐 ljung0622 66,692 남음 · 같은 조회 안 같은 금액 보류 해제 줄까지 지울 위험 = D-085 가 버린 안) · 앞 조회 값 남기기(앱 규칙 = 지급일이 속한 달 조회와 다름) · 진행 중 주까지 70:30 검산(70%·30% 줄이 서로 다른 달 조회에서 와 늘 '다름').
- 영향 범위: 앱 코드 아님 — 정산서 스크립트(git 밖) `output/_분석_261013/정산스크립트/settlement_ledger.py`(rg_window_overlap·Ledger.__init__·account E1) · `test_settlement_ledger.py`·`run_statements_at.py`(신규). 위탁자에게 10/18 정산서를 이미 보냈다면 17계정 정정 통보 필요(소유자 확인). 앞으로 스냅샷 조회 스크립트를 다시 쓸 땐 앱처럼 조회 달 밖 지급일 줄을 거를 것. HQ 정산서 포팅 시 같은 규칙.
- 상태: ACTIVE (17계정 정정 통보 필요 없음 — 10/18 기준 정산서는 위탁자에게 안 보냄·소유자 확인 D-179)

### D-119 [AD_COST_DAY_CAMPAIGN] 광고비 관리 상품 몫 = 날짜×캠페인 청구가능액 × 그날 매출 성장 보고서 옵션 광고비 비율 · 수집 = 광고센터 일별 광고비 정산내역(월별 엑셀 대체) (2026-10-26, R60)
- 결정(소유자 2026-10-26 "날짜 단위로 바꿔서 진행"): (1) 수집 `settlement_ads` — 달마다 광고센터 GraphQL getDailySettlement(기간, settlementDomain SELLER)를 `{계정}_광고정산_{YYYYMM}.json` 으로 저장(날짜·캠페인 ID·소진 광고비·예산 초과 차감 후·청구가능 광고비 + 로켓그로스/판매자배송 요약). 윙 로켓그로스 광고비 내역 엑셀(월·캠페인 단위·ID 없음) 받기는 뺌. 매출 성장 보고서 요청·받기와 밀크런 엑셀은 그대로. (2) 정산서(git 밖 `managed_alloc.ad_share`·`statement_managed`) — 날짜×캠페인마다 청구가능액을 그날 보고서의 광고집행 옵션별 광고비 비율로 나눠 관리 옵션 몫을 더하고, 계정 광고비 공제 × (관리 몫 / 청구가능 합). 보고서에 없는 날·캠페인 청구액은 메모(관리 몫 0).
- 근거(벅스 실측 2026-10-26): 쿠팡이 주는 청구 최소 단위 = 날짜×캠페인(상품별 청구액은 어느 화면에도 없음 — 정산내역 items 칸 확인). 7월 소진 378,938 → 7/12·13·14 일예산 초과 750(150+78+522) 차감 → 청구가능 378,188 + 부가세 37,819 = 416,007 = 로켓그로스 지급 줄 광고비 공제 8줄 합 · 6월 청구 대상액 244,347 = 6월분 공제 4줄 합(원 단위). 보고서 옵션 광고비는 정산 소진액보다 매일 2~9원 큼(7월 +48). 같은 7월을 월 비율과 날짜 비율로 나누면 옵션별 −27~+19원 차이 — 예산 초과 차감이 특정 날에만 생겨 날짜 단위가 맞음. 캠페인 안 옵션이 모두 관리(또는 모두 관리 밖)면 비율과 무관하게 정확, 섞인 캠페인만 비율 배분(쿠팡 자료로 더 정확한 방법 없음). 시험 P41(정산내역 저장·다시 안 받음)·test_managed_alloc(7월 실값: 576583 몫 74,402) 재현 실패 → 수정 → 통과 · run_checks 초록.
- 버린 대안: 월·캠페인 청구가능 × 월 보고서 비율(D-117 — 예산 초과 차감 날짜가 섞임) · 보고서 광고비 ×1.1 그대로(청구액과 안 맞음) · 계정 광고비를 관리 정산 비율로(상품 자료 무시).
- 영향 범위: `settlement_ads.py`(_DAILY·collect — CMG_EXCEL 삭제) · `tools/verify_settlement_runtime_offline.py` P41 · git 밖 `managed_alloc.py`·`statement_managed.py`·`test_managed_alloc.py`. 운용 PC 재배포 후 수집. 관리 상품과 관리 밖 상품을 한 캠페인에 섞지 않으면 비율 없이 정확(운영 권고). HQ 포팅 대상.
- 상태: ACTIVE (부분 SUPERSEDED by D-137 — 못 받은 달·캠페인 없는 줄 · SUPERSEDED by D-140 — 계정 공제에 비율 적용)

### D-120 [SETTLE_COLLECT_SAFETY] 정산 수집 보강 안전장치(운용 PC 설치 전) — 광고비 원천 하루 계정당 2개월·요청마다 쉼 · 검증 새 항목 예상 밖 오류 = 그 항목만 조회 실패 (2026-10-26, R64)
- 결정(소유자 2026-10-26 "권장대로 진행해줘" — 통제 세션 검토): (1) `settlement_ads.collect` — 받을 게 남은 달을 **최근 달부터 한 실행에 계정당 MAX_MONTHS=2개월**만(남은 달 수를 처리기록에 '남은 달 N(다음 실행에)') · 원격 요청(밀크런 엑셀·일별 정산내역·캠페인 목록·보고서 목록/요청·보고서 받기)마다 먼저 쉼(정산 LOOKUP_GAP_SEC 3~8초). (2) `settlement_verify_collect.collect(fatal=…)` — D-116 새 항목(우대수수료 환급·입고 내역·반품 조회)은 차단(fatal — 앱은 BlockDetected·기본 ApiBlocked) 외 **모든 예외**도 그 항목만 '조회 실패'로 남기고 계속(시간 초과·응답 모양 변경이 계정 실패 → 연속 2계정 정산 전체 중단으로 번지지 않게). 기존 항목은 지금처럼(ServerBusy·SiteChangedError).
- 근거: 첫 실행에 계정 ~30 × 밀린 9개월 × 요청 4~5종이 쉼 없이 나가면 사무실 IP·위탁 로그인 세션 Akamai 차단 위험(통제 세션 검토) · 새 항목은 실측 1계정(벅스)뿐이라 다른 계정 응답 모양이 다를 수 있음. 시험 P43(9개월 → 첫날 9·8월·다음 날 7·6월·남은 달 7→5·요청마다 쉼 먼저 / 환급 TimeoutError·입고 응답 모양·반품 KeyError = 조회 실패 4건·추가지급 등 계속·차단은 올라감) 재현 실패 → 수정 → 통과 · P41 순서(최근 달부터) 갱신 · run_checks 초록.
- 버린 대안: 첫 실행에 전부(차단 위험) · 새 항목도 기존 safe 만(예상 밖 오류가 계정 실패로) · 모든 항목을 넓게 잡기(기존 항목 동작 변경 — 범위 밖).
- 영향 범위: `settlement_ads.py`(MAX_MONTHS·collect gap/max_months·남은 달) · `settlement_verify_collect.py`(safe_new·fatal) · `tools/settlement_download.py`(collect_verify fatal=BlockDetected·collect_ads gap·처리기록 문구) · P41·P43. 운용 PC 재배포 후 적용.
- 상태: ACTIVE

### D-121 [PROMO_START_FADE_7D] 결과 사업자 시트 일자 칸 = 체험단 시작일부터 7일 배경(시작일 진하게 → 날마다 옅게 → 8일째 없음) (2026-10-27, R66)
- 결정(소유자 2026-10-27 "관리대장 두번째 시트인 체험단 시트에서 체험단 시작일을 결과 파일에 표시 … 체험단 시작일은 진하게 하고 점차 연하게 … 종료 시점은 1주일(7일)"): 상품 블록의 일자 칸(날짜 머리줄·지표·키워드 소헤더·순위 줄 전부 같은 칸)을 체험단 시작일 칸 = FFC000(진한 주황노랑)에서 하루마다 흰색 쪽으로 1/7씩 옅게(FFC924·FFD249·FFDB6D·FFE492·FFEDB6·FFF6DB) 칠하고 **시작일 포함 7일 뒤(8일째)부터 배경 없음**. 시작일 = 직원 입력 시작일(_마케팅 3열) 우선·없으면 관리대장 '체험단' 시트 요청일(D-086 자동 시작일·체험단효과와 같은 기준). 결과 구글시트는 통계 미러링(`worksheet_to_requests`)으로 같은 색.
- 근거: 실측 10-26 마스터 — 직원 입력 시작일 0/27·자동 시작일 25/27 → 옛 배경(직원 입력 기간만 사용)은 늘 비어 있었음. 핀 S4(시작일~+6일 7단계 색·전날/8일째 없음·직원 입력 우선) 재현 실패 → 수정 → 통과 · 실데이터 비엔케이미디어 10.15 FFC000 → 10.21 FFF6DB · 10.22 없음 · 구글 반영 요청에 색 포함 · run_checks 15종·복잡도 초록.
- 버린 대안: 옛 '마케팅 기간(시작~종료) 연주황'·'시작일~+1개월 노출순위 배경'(2026-09-24) 유지 — 직원 입력 칸이 없어져(D-109) 쓰이지 않고 새 요구와 겹침 → 물리 삭제(`_mkt_cols`·`_promo_cols`·`_FILL_MKT`·`_StyleCtx.mkt_fill`) · 시작일 하나만 칠하기(요구와 다름).
- 영향 범위: `workbook_render.py`(`_promo_fills`·`_style_block`/`_style_metric_rows`/`_style_keyword_rows`) · `workbook_common._StyleCtx` · `tools/pin_apply_style.py` S4 · DESIGN.md · GSHEET_UNIFIED.md. 체험단중 표시·체험단효과·수집 주기(has_marketing)는 그대로. 운용 PC 재배포 후 적용.
- 상태: ACTIVE (부분 SUPERSEDED by D-122 — 자동 시작일 = 요청일 부분)

### D-122 [PROMO_START_COLUMN] 체험단 시작일 = 관리대장 '체험단' 시트 '체험단시작일' 칸(옛 '진행여부') · 요청일 안 씀 · 빈 칸 줄 제외 (2026-10-27, R67)
- 결정(소유자 2026-10-27 "체험단 시트에서 요청일은 체험단 업체에 의뢰하는 날짜이므로 체험단 시작일이 아님 … '체험단시작일' 항목(구 진행여부)을 기준으로 변경 … 공란은 제외"): `promo_sheet.parse_promo_rows` 가 헤더 '체험단시작일'(띄어쓰기 무시)·'링크' 행을 찾고, 시작일 = 그 칸 값. '9.17' 처럼 년도 없는 값 = 그 줄 요청일의 해(시작이 요청보다 앞 날짜면 다음 해)·요청일도 없으면 오늘과 가까운 해. 옛 표기 '09.17 완료' 는 앞 날짜만 · 빈 칸·'완료'만 = 그 줄 제외(요청일로 대신하지 않음) · '체험단시작일' 칸이 없는 시트 = 연결 0(요청일 대체 없음). 같은 상품 여러 회차 = 가장 최근 시작일. 계정목록 '체험단 시작일'·체험단효과·사업자 시트 7일 배경(D-121) 모두 이 값 기준.
- 근거: 실측(관리대장 체험단 시트 10-27): 헤더 3행 = … 포토/텍스트 · **체험단시작일** · 완료여부 · 비고 / 76줄 중 체험단시작일 값 23줄(9.17·9.18·9.19·10.12·10.21·10.22) · 53줄 빈 칸. 새 기준 연결 11개 상품(결과에 없는 상품 2줄: (DW)커머스 햄스트링기구·건강만점 컬리케일) — 요청일 기준 25개 중 14개는 시작일 없음으로 바뀜(예 55마켓 캠핑 테이블·와이에이치 공기청정기 10.08 → 없음), 비엔케이미디어 10.15 → 10.21, 벅스 큐브 10.08 → 10.12, 니코에이블 기저귀가방 09.15 → 09.19. 재현: verify_offline [13b] 새 시트 모양에서 옛 코드 실패(요청일 08.11·09.10·09.25 채택) → 수정 → 통과.
- 결과 구글시트 즉시 반영(일회용 `scratchpad\patch_promo_start.py --apply`): 계정목록 H·I 25줄 + 일자 칸 배경 177요청(옛 시작일 색 지움·새 시작일 7일 칠함) · 읽어 확인 = 비엔케이미디어 10.21 FFC000 → 10.26 FFEDB6 · 55마켓 색 없음. 체험단효과는 마스터(10-25까지) 기준 — 새 버전 다음 실행에서 다시 계산.
- 버린 대안: 체험단시작일 비면 요청일로 대신(소유자 '공란은 제외') · '완료여부' 칸 사용(날짜 없음).
- 영향 범위: `promo_sheet.py`(`_START_COL`·`_start_iso`·`parse_promo_rows`) · `tools/verify_offline.py` [13b] · 설명 문구(`gsheet_index.py` 주석·`tools/build_staff_manual.py`·`tools/pin_apply_style.py` 주석·DESIGN·CLAUDE.md). 운용 PC = 새 zip 설치 전엔 밤 실행이 요청일 기준으로 되돌림. HQ 포팅 대상.
- 상태: ACTIVE — D-086 의 '시작일 = 요청일' 부분을 대체(SUPERSEDED by D-122 표기는 D-086 상태 줄에)

### D-123 [LOGIN_PW_TRIM_ALL_AND_24H_BLOCK] 비밀번호 앞뒤 공백 떼기 = 앱·정산·전환자 확인 공통 · 거부된 값은 거부 시각부터 24시간 다시 넣지 않음(달력 날짜 기준 폐지) (2026-10-27, R69)
- 결정(소유자 2026-10-27 "대장은 성공했는데 정산은 실패한 원인 파악 … 둘 다 고치고"): (1) 공용 로그인 `pipeline_sales._login_with_candidates` 가 후보마다 앞뒤 공백을 떼고 공백만 다른 값은 하나로 합친다 — 앱 ①·정산·셀독전환자 확인 모두 같은 함수. 정산 `settlement_accounts.login_passwords` 도 대장 저장값·원장 값을 공백 뗀 뒤 비교(같으면 1개)·설명 문구 '정산 계정 파일' → '원장'(D-103 이후 실제 출처). 원장은 계속 대장 원문 그대로 저장(로그인 때만 뗌). (2) D-068 '그날 다시 넣지 않음'을 **거부 시각부터 24시간**으로 바꾼다(`login_today.BLOCK_HOURS`·지문별 거부 시각 `fp_at`·옛 기록 fps 는 at 을 거부 시각으로 읽음). 고친 값은 지금처럼 바로 시도. 로그인 실패 사유 표시(reasons_today)는 그대로 날짜 기준.
- 근거: output(27) 실측 — (DW)커머스 dalbong1849 대장 41행=값1(틀림)·40·43~50행=값2(맞음, 앞뒤 공백). 앱 ① 18:21 값1 거부 → 값2(공백 뗌·D-018) 성공. 정산 02:26 후보 = 저장값(대장 첫 후보=값1) + 원장 값(대장 40행 원문 = 값2+공백) → 둘 다 거부. 원장 백업 비교(값 미출력): 원장 값 ≠ 값2, 공백 떼면 = 값2. 원장 34계정 중 공백 계정 = dalbong1849·plan_it. 자정 문제: plan_it 22:32 2회 → 04:33 2회(6시간에 틀린 입력 4회)·unipang 23:39 → 05:58·dalbong 18:21 → 02:26 2회 — 달력 날짜가 바뀌어 같은 밤 정산이 다시 넣음(쿠팡 5회 오류 = 잠금). 재현: verify_offline [37]·verify_settlement P33·핀 D2 새 항목이 옛 코드에서 실패 → 수정 → 통과. 실데이터 시뮬: 수정 뒤 dalbong 정산 후보 2번째 = 앱 ① 성공 값 · 어젯밤 기록으로 plan_it·unipang·dalbong·wavetech = 10-28 02:00 에도 막힘(24시간 안)·gbseller808(00:04 거부) = 10-28 02:00 다시 시도 가능.
- 버린 대안: 운영일(18:00 기준) 날짜로 바꾸기(오후 수동 실행에서 1시간 만에 다시 넣는 경계 남음) · 원장에 공백 뗀 값 저장(원장 원문 보존 원칙 LEDGER_REGISTRY §9 와 충돌) · 대장만 고치기(같은 실수 재발).
- 영향 범위: `login_today.py`(`_blocked`·`record_failure/record_success/refused_today` now 인자) · `pipeline_sales.py`(후보 정리·막힘 문구) · `settlement_accounts.py` · `tools/settlement_download.py` 주석 · 시험 3종(verify_offline [37]·verify_settlement P33·pin_login_ranks D2). HQ 포팅 대상(로그인 공통).
- 상태: ACTIVE — D-068 의 '그날(달력 날짜)' 부분을 대체(SUPERSEDED by D-123 표기는 D-068 상태 줄에) · D-018 적용 범위를 정산·전환자 확인까지 넓힘

### D-124 [STATEMENT_LAYOUT_RECONCILE] 위탁정산서 1쪽 = 큰 숫자 ①~④와 표가 1원까지 맞는 구조 · 정산 확정/예정 · 입금 완료/예정 · 글씨 검정·바탕색 구분 (2026-10-27, R71)
- 결정(소유자 2026-10-27 견본 검토 4회 확정): ① 큰 숫자 = ① 판매금액 · ② 쿠팡 정산 총액 · ③ 쿠팡 공제 · ④ **실제 입금 총액**(② − ③ = ④, 아래 줄에 입금 완료 + 입금 예정). ② 1번 표 = **정산 확정 | 정산 예정 | 합계** 세 칸(정산 예정분 쿠폰·수수료는 '쿠폰·수수료 등(쿠팡 계산 합계)' 한 줄). ③ 2번 표 = **입금 완료 | 입금 예정 | 합계** 세 칸 — 관리 상품 몫을 **쿠팡 지급 줄마다** 나눠 더함(정산금액 = ② × 줄 지급대상·그 줄 판매 달·판매 방식 관리 정산 비율 가중, 공제 = 그 줄에서 실제 빠진 항목 × 항목 관리 비율, 줄 생성 전 몫 = 예정) · 부록 '관리 상품 입금 내역'(지급일별, 상태별 합계 = 1쪽). ④ 금액 칸 = 위에서 아래로 더하고 빼면 그대로 맞는 숫자만, 참고 숫자는 설명 칸·'참고. 합계에 들어가지 않은 금액' 묶음. ⑤ 만들 때 **자동 검산**(칸·줄 합계 ≠ 큰 숫자면 그 정산서 만들지 않고 SumMismatch) · 끝전 = 정산·공제 줄 각각 반올림, 입금 완료·보류 칸 반올림, 입금 예정 = 합계 − 완료 − 보류. ⑥ 머리 = 사업자·쿠팡 계정·판매 기간·기준일 각 줄·진하게. ⑦ 글씨 전부 검정·한 단계 크게(본문 11), 구분은 바탕색, 음수만 [Red] 숫자 서식. 용어 '정산 확정'(쿠팡이 금액 확정·입금과 별개) / '정산 예정'.
- 근거: 소유자 지적 — ①판매금액이 표 첫 줄과 다름(정산 중 판매가 설명에만) · '+29,010' 참고 금액이 합계처럼 보임 · '정산 완료+정산 예정=정산 총액' 흐름 요구 · 2번 표가 입금 완료/예정 세부 없음·④ 입금 총액 없음. 실측(니코에이블): 옛 '계정 입금 비율' 배분 입금 완료 13,502,578·예정 1,638,635 → 줄별 배분 12,064,470·3,076,743(합 15,141,213 동일 — 정산 예정분 관리 비율 ≈97% vs 확정분 ≈55% 를 반영). 독립 검산 20계정 20/20 일치. 검산이 (DW)커머스에서 합계 0·상태 사이 ±30,008 오간 공제 항목 누락을 잡음 → 줄로 표시하게 수정.
- 버린 대안: 판매금액에 '정산 중 포함' 문구만(혼란) · 2번 표를 정산 확정/예정으로 나눔(쿠팡 70%/30% 지급 때문에 확정분에도 입금 예정이 섞여 '받은 돈/받을 돈'이 안 나옴) · 계정 실제 입금 비율 한 번 배분(세부 내역 없음·판매 달별 관리 비율 차이 무시).
- 영향 범위: git 밖 `output\_분석_261013\정산스크립트\statement_managed.py`(shown·status_split·managed_lines·book) — 견본 `D:\토탈셀러\쿠팡 정산 자료\정산서_견본_261026\정산서_샘플_니코에이블_한상현_관리상품_261027_v5.xlsx`. 전 계정 정산서 폴더(`위탁정산서_20261018기준_관리상품\`)는 아직 옛 양식 — 다시 만들어야 함.
- 상태: ACTIVE (부분 SUPERSEDED by D-126 — 1쪽 큰 숫자·표 구성 ①~④ 부분 — 정산 확정/예정·입금 완료/예정 줄별 배분·자동 검산·끝전·글씨 규칙은 D-126 이 그대로 이어받음 · SUPERSEDED by D-140 — ③ 공제 배분)

### D-125 [ADCENTER_NAV_SETTLE] 광고센터 새 창 = relay 를 벗어난 최종 주소까지 기다린 뒤 화면 조작 · 이동 중 'Execution context was destroyed' = 쉬고 다시(처음 포함 4번) (2026-10-28, R72)
- 결정: `settlement_evidence_web.open_adcenter` 가 새 창 domcontentloaded 뒤 주소가 `/relay/` 를 벗어날 때까지(최대 30초, 넘으면 기록하고 진행) 기다리고 다시 domcontentloaded 를 기다린다. 안내·동의 창 닫기 evaluate(`_CLOSE_POPUP`·`_CLOSE_TITLED`)는 `_eval_settled` 로 감싸 'Execution context was destroyed' 일 때만 domcontentloaded 대기 + 3초 쉬고 다시(`NAV_RETRIES = 4`, 처음 포함) · 다른 오류·상한 초과는 그대로 올림(광고비 단계 실패 기록). 동의·이동 버튼 안 누름(D-067)·하루 계정당 2개월·요청마다 쉼(D-120)은 그대로.
- 근거: 운용 PC output(28) 10-27 23:48~ 오류 로그 '광고비' 블록 43개 전부 같은 줄 — `collect_ads` → `settlement_ads.collect`(_gql 첫 호출) → `open_adcenter` 286줄 `q.evaluate(_CLOSE_POPUP)` → `Page.evaluate: Execution context was destroyed, most likely because of a navigation`. 10-26 실측 탭 주소 = 새 창이 `relay/wing/home` → `marketing/dashboard/...` 로 한 번 더 이동 → domcontentloaded(relay 화면)+8초 뒤 evaluate 가 이동 도중에 걸림. 영향 = 계정마다 밀크런 202609 만 받고 광고 일별 정산에서 멈춤 → `done()` 미충족·과거 달 진행 없음. 재현: `verify_settlement_runtime_offline` P44(가짜 창 relay→dashboard·evaluate 2번 사라짐)가 옛 코드에서 같은 286줄 같은 오류로 실패 → 수정 → 통과(3번째 정상·계속 사라지면 4번 뒤 오류·다른 오류는 1번에 올림).
- 버린 대안: 8초 고정 대기를 늘리기(이동 시각이 PC·네트워크마다 달라 또 걸림) · 모든 Playwright 오류 재시도(진짜 화면 변경·차단을 가림) · 광고 GraphQL 호출(API.call evaluate)까지 재시도(보고서 요청이 두 번 갈 수 있음 — 이번 증거는 창 열기에서만).
- 영향 범위: `src/coupang_analytics/settlement_evidence_web.py`(`_eval_settled`·`NAV_RETRIES`·`open_adcenter` — `adcenter_monthly` 도 같은 함수 사용) · `tools/verify_settlement_runtime_offline.py` P44. 운용 PC = 새 zip 설치 후 적용 · 설치 뒤 첫 실행에서 처리기록 '광고비' 줄 정상 확인 필요(라이브 미실측).
- 상태: ACTIVE

### D-126 [STATEMENT_AG_FLOW_FASTPAY] 위탁정산서 1쪽 = 쿠팡 매출내역식 A − B − C + D = E − F = G 흐름 · 큰 숫자마다 자기 내역 표 · 빠른정산 = 입금 완료 (2026-10-28, R74)
- 결정(소유자 2026-10-27~28 견본 v6~v8 검토 확정): ① 제목 = '{사업자} (대표 {대표자})님 쿠팡 판매 정산내역서' · 머리 4줄(사업자·쿠팡 계정·판매 기간·기준일) 진하게 한 줄씩. ② 큰 숫자 = **A 판매금액 · E 정산대상액 · F 쿠팡 공제 · G 최종 지급액** + '비고 (참고)' 칸(입금 완료 X / 입금 예정 Y / 입금 완료 중 빠른정산 Z) · 아래 흐름 한 줄 'A − B 판매자 할인쿠폰 − C 판매수수료 + D 쿠팡 지원 할인 = E − F = G'. ③ 큰 숫자마다 자기 내역 표, 합계 줄 = 위 큰 숫자: A 내역(a 상품 판매액·b 배송비·c 취소·반품·정산 예정 판매 | 정산 확정·정산 예정·합계) → E = A − B − C + D(같은 세 칸) → F 쿠팡 공제 내역(빠른정산 제외 | 입금 완료분·입금 예정분·합계) → G = E − F(입금 완료·입금 예정·합계). ④ **빠른정산(셀러월렛) 상환은 공제가 아니라 이미 받은 돈** = G 표에 '빠른정산 상환 −Z'(쿠팡이 지급 줄에서 뺀 칸대로 완료/예정) + '빠른정산으로 먼저 받은 돈 +Z'(전부 입금 완료) 두 줄 → G 합계 불변·입금 완료에 Z 포함. 원천 = 로켓그로스 `totalArFactoringDeductionAmount`·윙 차감 사유 '빠른정산 계좌인출액'(기타 공제에서 분리). ⑤ 참고 묶음은 간격 + '▼ 아래는 참고 자료입니다 — 위 정산 금액(A~G)에 들어가지 않습니다' 아래: 상품 모르는 배송비 · 쿠팡 정산 밖 별도 입금(우대수수료 환급·추가지급 — **있을 때만**) · 체험단 · 계정 전체 참고. ⑥ 삭제: 서명란·용어 풀이·쿠팡 자료와 대조·큰 숫자 아래 설명 줄·범위 줄. ⑦ 자동 검산(D-124 ⑤)에 'a+b+c(+정산 예정) = A'·'E + F (+ 빠른정산 두 줄) = G' 추가. 라벨은 '=' 로 시작하지 않음(엑셀 #NAME?).
- 근거: 소유자 지적 — 상단 합계와 하단 세부 불일치 · 쿠팡 매출내역처럼 처리 흐름 요구 · 판매금액 내역에 판매액·배송비·취소만 · 빠른정산 상환이 공제로 보이면 원더폴리 입금 완료 20,271 처럼 '돈을 덜 받은' 것으로 읽힘(실제는 셀러월렛으로 5,052,520 먼저 입금). 시뮬레이션(2026-10-28, output(28) 관리기준·기준일 2026-10-28 → 새 폴더 재생성): 생성기 자동 검산 24/24 · 독립 검산(블록별 칸·가로 합 = 합계 줄 = 큰 숫자 · G표 E/F 줄 = E/F · 상환 + 먼저 받은 돈 = 0 · 비고 숫자 = G표) **24/24** · 기존 결과 폴더와 1쪽 셀 24/24 동일 · `test_managed_alloc` OK · 정산 대조 31/34(✘ 글로벌셀러 비번·노바네스트 ④·로움 E2 1줄). 빠른정산 계정: 원더폴리 5,052,520(입금 완료 5,072,791) · 유라이프 6,096,682(6,685,998) · 명진상사 152,654.
- 버린 대안: D-124 ①~④ 큰 숫자(소유자: 상단 금액과 상세 내용이 서로 안 맞아 보임) · 빠른정산 상환을 쿠팡 공제 F 에 넣기(입금 완료가 실제 받은 돈보다 작게 보임) · 빠른정산을 비고에만 적기(입금 완료/예정 합이 G 와 안 맞음).
- 영향 범위: git 밖 `output\_분석_261013\정산스크립트\statement_managed.py`(deductions·status_split·shown·book) — 백업 `_백업\statement_managed_A-G전.py`·`_빠른정산전.py` · 견본 `D:\토탈셀러\쿠팡 정산 자료\정산서_견본_261026\정산서_샘플_니코에이블_한상현_관리상품_261028_v8.xlsx` · 결과 `D:\토탈셀러\쿠팡 정산 자료\위탁정산서_20261028기준_관리상품_output28\`(24곳+요약). 앱 코드 변경 없음. 남은 사실: 광고비·밀크런 일부 '(추정)'(D-125 설치 뒤 수집되면 실값) · 입금 마이너스 3곳(효성 완료 −27,469·비엔케이미디어 완료 −4,965·반달컴퍼니 예정 −7,698 = 추정 광고비 배분 탓으로 추정) · '(추정)' 표기 대안(정산 확정분만 넣기 권장)은 소유자 답 대기.
- 상태: ACTIVE (부분 SUPERSEDED by D-140 — F 표 칸 제목 · SUPERSEDED by D-146 — (추정) 표기)

### D-127 [STATEMENT_NEG_COLUMN_NOTE] 위탁정산서 입금 완료·입금 예정 칸이 마이너스면 숫자는 그대로 두고 사유 설명 자동 표시 (2026-10-28, R75)
- 결정(소유자 2026-10-28 '1번으로 반영'): G 표 입금 완료·입금 예정 칸이 마이너스일 때만 ① 1쪽 비고 칸에 '※ 마이너스 사유는 아래 G 설명' ② G 최종 지급액 줄 설명에 '※ {칸} 마이너스 = 광고비·물류비 등 비용이 그 지급에서 먼저 빠지고, 관리 상품 판매대금은 다음(입금 완료일 때)/앞선(입금 예정일 때) 지급에 들어감 — 계정 통장 입금은 다른 상품 대금에서 빠져 마이너스 아님 · 최종 지급액 G 기준'. 숫자·지급 회차 배분(D-124 줄별 배분)은 바꾸지 않음. 비고 칸 높이 = 줄 수 × 16(최소 34).
- 근거(output(28)·기준일 10-28 시뮬레이션): 효성 입금 완료 −27,469 = E 입금 완료 0(관리 상품 판매 전부 정산 예정) − 광고비 27,316·밀크런 125·기타 28(광고비·밀크런 = 계정 전체 × 0.2% 추정) · 비엔케이미디어 입금 완료 −4,965 = E 0 − 광고비 4,965(1.6% 추정) · 반달컴퍼니 입금 예정 −7,698 = E 예정 58,615 − 로켓그로스 물류비 190,135(실값) + 재고 보상 126,667 − 기타 2,845 → **반달은 실값 물류비라 광고 수집 뒤에도 남음**(D-126 '추정 광고비 탓' 은 효성·비엔케이미디어에만 해당). 세 곳 모두 G 합계는 플러스. 반영 뒤 독립 검산 24/24 · 1쪽 숫자 변화 없음(설명만 3곳) · 정산 대조 31/34 그대로.
- 버린 대안: 마이너스를 다음 칸으로 넘기기(실제 지급 회차와 달라져 통장 대조 근거 약해짐) · 그대로 두기(위탁자가 돌려줄 돈으로 오해).
- 영향 범위: git 밖 `output\_분석_261013\정산스크립트\statement_managed.py` book()(백업 `_백업\statement_managed_마이너스설명전.py`) · 결과 `D:\토탈셀러\쿠팡 정산 자료\위탁정산서_20261028기준_관리상품_output28\` 다시 씀. 앱 코드 변경 없음.
- 상태: ACTIVE

### D-128 [SALES_SUMMARY_SCALE_ROWS] 통합판매현황 ① 요약 맨 위 = 셀독 관리 계정 수 · 관리 상품 등록 수(판매중지 따로) · 누적 매출금액(4월~ 월별 누계 합) (2026-11-02, R77)
- 결정(소유자 2026-11-02 "원문자1 요약 부분에 셀독관리계정수: 000개, 관리상품 등록갯수: 000개, 누적매출금액: 000원 추가"): ① 요약 띠 바로 아래 세 줄(라벨 A·값 B~J). 계정 수 = 결과 계정목록과 같은 로스터(`product_roster`)의 계정ID 수 — 상품 0개 계정 포함. 관리 상품 등록 수 = 같은 로스터의 상품 줄(다중옵션 2차 블록 제외·판매중지 포함)·'판매 중 N · 판매중지 M' 함께. 누적 매출금액 = 아래 '월별 누계'(4월~어제·D-105) 금액 합 — 미수집 계정 기간이 있으면 '미수집 계정 기간 제외' 표시. 구글 결과 시트는 통계 미러링으로 같은 줄.
- 근거: 소유자 요청 화면(① 요약 표). 결과 구글시트 10-29 기준 직접 집계 = 계정 33 · 상품 109(판매 중 101·판매중지 8) · 4/1~10/28 433,146,540원. 실데이터 시험(운용 PC 10-26 마스터): 계정 30 · 상품 96(88·8) · 424,646,660원 = 월별 누계 합과 일치. 재현: verify_sales_summary T12 가 옛 코드에서 실패(세 줄 없음) → 수정 → 통과 · 게이트 15종·복잡도 초록.
- 버린 대안: 계정목록 제목처럼 판매중지 제외 상품 수만(소유자 '등록 갯수' — 판매중지도 등록 상품이라 함께 보이고 따로 표시) · 정산 금액으로 누적(① 요약은 판매분석 주문 기준 — 정산과 기준이 다름).
- 영향 범위: `sales_dashboard.Dashboard.managed` · `workbook_sales.managed_counts`·`refresh_sales_sheet` · `workbook_sales_dash._scale_rows` · `tools/verify_sales_summary_offline.py` T12 · `designs/SALES_SUMMARY.md` · CLAUDE.md. 직원 매뉴얼 ① 요약 화면(스크린샷 좌표)은 다음 매뉴얼 갱신 때. HQ 포팅 대상.
- 상태: ACTIVE (누적 매출금액 계산만 SUPERSEDED by D-131 · 관리 상품 등록 수 값 SUPERSEDED by D-139 — 로스터 수는 괄호 표시로 유지)

### D-129 [SALES_RECORD_INVENTORY_ID] 판매분석 기록(일별·기간)에 등록상품ID 저장 · 저장 전에 받은 달은 한 번 다시 조회 (2026-11-02, R78)
- 결정(소유자 2026-11-02 "앱이 등록상품ID도 저장하게 고쳐줘, 10월 자료는 다운로드"): 판매분석(vi-detail-search) 응답의 `vendorItemDetails.inventoryId` 를 `OptionMetric.inventory_id` 로 받아 `output/판매분석_일별`·`판매분석_기간` 옵션마다 '등록상품ID' 칸으로 저장(없으면 빈 칸). `sales_summary.plan_periods` 는 옵션이 있는데 '등록상품ID' 칸이 없는 **달(M:)** 기록을 한 번 다시 조회(빈 칸이면 저장 후 기록이라 다시 안 받음 — 무한 재조회 없음·주는 다시 안 받음). 10월분은 Claude 가 직접 받지 않음(위탁계정 비밀번호 로그인 = 하지 않는 일) → 새 zip 설치 뒤 첫 밤 ① 판매수집 같은 세션에서 4~10월이 등록상품ID 와 함께 다시 들어옴.
- 근거: 소유자 9월 판매현황 파일(`셀독 9월 판매현황_집계_0901-0927.xlsx`) 상품 수 = 등록상품ID 546(상품명 333). 앱 기록엔 상품명·VID 만 있어 10월을 같은 단위로 셀 수 없었음(현재 상품조회로 VID 연결 시 옛 로켓그로스 VID 다수 미연결 — 에벤에셀 75옵션). 실측(운용 PC 10-26 응답 원문): 판매분석 `inventoryId` 16개 중 14개가 9월 파일 등록상품ID 와 일치·15개가 상품조회 vendorInventoryId 와 일치(`itemId` 는 다른 번호). 재현: verify_sales_history S4·verify_sales_summary T1 새 항목이 옛 코드에서 실패 → 수정 → 통과 · 게이트 15종·복잡도 초록. 실데이터 계획: 운용 PC 기록으로 첫 밤 다시 받을 조회 260건(30계정·계정당 약 9건).
- 버린 대안: 현재 상품조회 목록으로 VID→등록상품ID 연결(삭제·교체된 옛 VID 미연결) · 옛 `item_id`(itemId) 재사용(다른 번호 — 엑셀 폴백의 '등록상품ID' 와 뜻이 섞임).
- 영향 범위: `report.OptionMetric.inventory_id` · `collector._parse_vendor_items` · `sales_history._options` · `sales_summary.plan_periods`·`_before_inventory_id` · 시험 2종 · `designs/SALES_SUMMARY.md`. R0 데이터 형식 추가(옵션에 '등록상품ID' 칸) → HQ `R0_DATA_CONTRACT` 알림 대상.
- 상태: ACTIVE

### D-130 [SALES_SUMMARY_OWN_PRODUCTS] 통합판매현황 ① 요약에 위탁자 직접 관리 상품(관리 상품 외) 2줄 — 쿠팡 판매분석 기준 상품 등록 수·누적 매출 (2026-11-02, R80)
- 결정(소유자 2026-11-02 "관리상품 이외에 계정별로 본인이 직접 관리하는 상품도 추가 … 각 계정별 상품등록수와 매출금액 … 쿠팡의 판매분석을 기준 … 2줄(제목포함하면 4줄)"): ① 요약 맨 위를 소제목 **'셀독 관리 상품'** + D-128 3줄, 그 아래 소제목 **'위탁자 직접 관리 상품(관리 상품 외) — 쿠팡 판매분석 기준'** + 2줄로. ① 상품 등록 수 = 결과 파일 계정의 관리 상품 밖 옵션(`sales_summary.scope(outside=True)`)이 4월~어제 판매분석 **달(M:) 기록**에 나온 **등록상품ID** 수(그로스·판매자배송 같은 ID = 1개 · 9월 판매현황 파일과 같은 단위)·'매출 발생'(그 ID 기간 매출 > 0 — 9월 파일 223 과 같은 기준)·등록상품ID 모르는 옵션은 세지 않고 개수 표시. ② 누적 매출금액 = 관리 상품 밖 저장으로 만든 대시보드의 월별 누계 합(관리 상품 누적과 같은 계산·미수집 계정 기간 제외 표시).
- 근거: 소유자 요청 · 9월 판매현황 파일 기준 검토(상품 수 = 판매분석에 나온 등록상품ID·판매 발생 = 매출 > 0 — 9월 파일 실측 223 일치). 실데이터 시험(운용 PC 10-26 마스터): 직접 관리 누적 1,591,002,770원 + 관리 424,646,660원 ≈ 전체 상품 합(2,014,414,830원·일별 합 기준)과 같은 규모 · 상품 등록 수 = 기존 기록에 등록상품ID 없어 '0개(모르는 옵션 5,984개 제외)' — 새 zip 첫 밤 D-129 재조회로 채워짐. 재현: verify_sales_summary T12(소제목 2줄 + 직접 관리 2줄·같은 ID 두 옵션 = 1·ID 모름 따로)가 옛 코드에서 실패 → 수정 → 통과 · 게이트 15종·복잡도 초록.
- 버린 대안: 상품명 기준(9월 파일 546 과 단위 다름) · 쿠팡 등록 목록(상품조회) 전체(대량 등록·판매종료 포함 — 판매분석 기준 아님) · 계정별 표 추가(소유자 '2줄').
- 영향 범위: `sales_summary.scope(outside=)` · `sales_dashboard.Dashboard.own`·`own_scale` · `workbook_sales.refresh_sales_sheet` · `workbook_sales_dash._scale_rows`·`_managed_lines`·`_own_lines`·`_line` · 시험 T12 · `designs/SALES_SUMMARY.md` · CLAUDE.md. HQ 포팅 대상.
- 상태: ACTIVE (누적 매출금액 계산 SUPERSEDED by D-131 · '관리 상품 외' 범위 SUPERSEDED by D-132)

### D-131 [SALES_SUMMARY_CUMULATIVE_RECEIVED] 통합판매현황 ① 누적 매출금액 = 계정별 받은 날 전부 합 — 하루 빠진 계정의 그 달을 통째로 빼지 않음·빠진 날 표시 (2026-11-02, R82)
- 결정(소유자 2026-11-02 "그날 판매 자료가 하루라도 빠진 계정은 이번 달 금액 전체가 '누적 매출금액'에서 빠집니다 ==> 누락되지 않도록 해줘"): ① 맨 위 '누적 매출금액' 두 줄(셀독 관리 D-128·위탁자 직접 관리 D-130) = 계정마다 달마다 **받은 날 전부** 합 — (가) 일별 기록이 있는 날 합 (나) 쿠팡 기간 합계(그 달 1일~받은 끝) + 그 뒤 일별 기록 중 **더 많은 날을 덮는 쪽**(같으면 일별 = 월별 누계와 같은 우선). 빠진 날은 0 으로 채우지 않고 값 칸에 '빠진 날: 사업자 N일'(많은 순 5곳·외 N계정)로 표시. 문구 = 'X원 (04.01~어제 · 계정별 받은 날 전부 합 · 빠진 날: …)'. 아래 월별 누계 줄·②~⑤ 차트·상세표는 그대로(달 값 = 다 받았을 때만·미수집 표시 — D-105).
- 근거: 시뮬레이션 검증(실데이터 운용 PC output 27·10-26 마스터) — 옛 계산(누적 = 월별 누계 합)은 한 계정이라도 그 달 하루가 빠지면 그 계정의 그 달 전체를 뺌: 웨이브텍(비번 오류·10/25 빠짐) 10월 관리 상품 124,900원 누락 · 그날 ① 전(29계정 전일 미수집)이면 10월 69,705,970원 통째 누락(424,646,660 → 354,940,690). 수정 후 = 424,771,560원(① 전·후 같음·+124,900 = 웨이브텍 10월 몫) · 직접 관리 1,591,002,770원 · 관리 + 직접 = 전체(2,015,774,330) 일치 · 빠진 날 없는 달은 옛 값과 같음(4~9월). 재현: verify_sales_summary T13(하루 빠진 계정·기간 합계 + 그 뒤 일별)이 옛 코드에서 실패(70,000 ≠ 100,000) → 수정 → 통과 · 게이트·복잡도 초록.
- 버린 대안: 아래 월별 누계 줄·② 차트도 같은 방식(요청 범위 밖·전월 대비 증감이 부분 수집 계정으로 왜곡 — 필요하면 별도 결정) · 빠진 날을 앞뒤 평균으로 채움(추정값을 실적에 섞음) · 그대로 두고 '제외' 표시만(소유자 '누락되지 않도록').
- 영향 범위: `sales_dashboard.cumulative`·`_month_received`·`Dashboard.cum`·`own_scale`(4번째 = 빠진 날) · `workbook_sales_dash._managed_lines`·`_own_lines`·`_cum_text` · `tools/verify_sales_summary_offline.py` T13 · `designs/SALES_SUMMARY.md` · CLAUDE.md. HQ 포팅 대상.
- 상태: ACTIVE

### D-132 [SALES_SUMMARY_OWN_INCLUDES_MANAGED] 통합판매현황 ① 위탁자 직접 관리 상품 = 셀독 관리 상품 포함(결과 계정 판매분석 전체) · 판매분석에 안 나온 관리 상품도 더함 (2026-11-04, R84)
- 결정(소유자 2026-11-04 "위탁자 직접 관리 상품에는 우리회사 관리상품도 모두 포함해줘"): 소제목 = '위탁자 직접 관리 상품(셀독 관리 상품 포함) — 쿠팡 판매분석 기준'. ① 상품 등록 수 = 결과 파일 계정의 판매분석 달 기록 **전체** 옵션의 등록상품ID 수 + 판매분석에 한 번도 안 나온 관리 상품 수(문구 'N개 (… 등록상품ID A + 판매분석에 안 나온 관리 상품 B · 매출 발생 …)'·B 없으면 생략). ② 누적 매출금액 = 결과 계정 전체(관리 + 관리 밖) 받은 날 전부 합(D-131 같은 계산). 셀독 관리 3줄(D-128)은 그대로. '안 나옴' = 블록 VID·블록 상품명 둘 다 기록에 없음(옵션 블록은 등록명으로 묶어 상품 하나).
- 근거: 등록상품ID 출처 실측(output 29 원문): 판매분석 `inventoryId` = 상품조회 `vendorInventoryId` 1,574/1,574(100%)·`itemId` 와 일치 0. 판매분석 = 활동 있는 상품만 — 등록 목록 7,651 vs 달 기록 ID 1,315(23계정·와이에이치 4,928 vs 719·55마켓 2,237 vs 4). 안 나온 관리 상품 판정(10-29 스냅샷 111묶음): VID 만 23(꿈꾸는아재 등 블록 VID ≠ 판매분석 VID 로 과대) · VID+상품명 5 · 원문 등록상품ID 3 → 렌더 시점 가능한 VID+상품명 채택(최대 2개 과대). 실데이터 값(결과 시트 11-03): 관리 457,343,210 + 직접 1,655,813,590 = 새 누적 2,113,156,800원. 재현: T12·T13 새 기대값이 옛 코드에서 실패 → 수정 → 통과 · 게이트·복잡도 초록.
- 버린 대안: VID 만 비교(판매 중 상품을 두 번 셈) · 쿠팡 등록 목록(상품조회) 전체(D-130 '판매분석 기준'·대량 등록 포함) · 판매분석에 나온 것만 세기(소유자 '모두'·관리 상품 일부 빠짐).
- 영향 범위: `sales_summary.scope`(outside 삭제) · `sales_dashboard.own_scale`(unseen) · `workbook_sales.unseen_products`·`refresh_sales_sheet` · `workbook_sales_dash._own_lines` · `tools/verify_sales_summary_offline.py` T12·T13 · `designs/SALES_SUMMARY.md` · CLAUDE.md. HQ 포팅 대상.
- 상태: ACTIVE (소제목 문구 SUPERSEDED by D-136 · 안 나온 관리 상품 더하기 SUPERSEDED by D-139)

### D-133 [SALES_SUMMARY_OWN_CATALOG_COUNT] 통합판매현황 ① 위탁자 직접 관리 상품(관리 상품 포함) — 상품 등록 수 = 계정별 쿠팡 상품조회 전체 (2026-11-04, R84)
- 결정(소유자 2026-11-04 "위탁자 직접 관리 상품(관리 상품 포함)으로 변경하고 상품등록수와 누적매출금액에도 관리상품 포함 계정별로 모든 상품을 포함해줘"): 소제목 = '위탁자 직접 관리 상품(관리 상품 포함) — 계정별 쿠팡 전체 상품'. 상품 등록 수 = 결과 계정마다 쿠팡 상품조회(`vendor-inventory/search`·판매중지 등 전 상태·삭제 상품 제외) 등록상품ID 수의 합 — ① 로그인 때 `output/등록상품수.json` 에 계정별 저장. 상품조회를 못 받은 계정(로그인 실패 등)은 판매분석 달 기록의 등록상품ID 수로 대신하고 '상품조회 못 받은 N계정은 판매분석 기준' 표시. 매출 발생 수·누적 매출금액은 판매분석 그대로(누적 = 결과 계정 전체·D-131·D-132).
- 근거: 소유자에게 보고한 실측 — 판매분석은 활동 있는 상품만(23계정 등록 목록 7,651 vs 판매분석 ID 1,315·와이에이치 4,928 vs 719·55마켓 2,237 vs 4) → '모든 상품' 은 상품조회만 가능. 상품조회는 계정마다 이미 전 페이지를 받고 있어 추가 조회 0. 재현: T12 새 기대값이 옛 코드에서 실패(record_catalog 없음) → 수정 → 통과. 첫 실행 전 값은 없음(운용 PC 재배포 후 첫 ①부터 채워짐·표시 수는 2,033 → 약 8천 규모로 커짐 예상).
- 버린 대안: D-132 판매분석 ID + 안 나온 관리 상품(활동 없는 상품 빠짐 — `unseen_products` 물리 삭제) · D-130 '판매분석 기준 유지'(소유자 '모든 상품'으로 뒤집음).
- 영향 범위: `sales_history.record_catalog`·`load_catalog` · `pipeline_sales._record_catalog`·`_discover_products` · `sales_dashboard.own_scale` · `workbook_sales.refresh_sales_sheet` · `workbook_sales_dash._own_lines` · 시험 T12·T13 · `designs/SALES_SUMMARY.md` · CLAUDE.md. HQ 포팅 대상.
- 상태: SUPERSEDED by D-136 (배포 전 되돌림·코드 물리 삭제)

### D-134 [LEDGER_GSHEET_FAIL_STOP] 구글 관리대장을 못 읽으면 오류·실행 중단 — PC 엑셀로 대신 돌리지 않음 · PC 엑셀 입력은 계정 삭제 안 함 (2026-11-04, R84)
- 결정(소유자 2026-11-04 "구글 계정을 못읽는 경우는 오류로 처리하고 엑셀로 돌려지면 안됨. error 처리해야하고 실행이 중단 되어야 함"): 입력 소스가 구글(관리대장·원장)인데 읽지 못하면(인터넷·링크 없음·권한) ❌ 로그를 남기고 실행하지 않는다(무인 = 바로 종료). PC 엑셀 폴백 삭제. 원장 소스 실패 → 구글 관리대장 전환은 유지(둘 다 구글). 설정에서 사람이 PC 엑셀을 입력 소스로 고른 경우만 엑셀로 실행 — 그때는 옛 파일일 수 있어 계정 삭제·판매중지 표기를 하지 않는다(`InputList.from_file`).
- 근거: 운용 PC 10-30 19:12 `oauth2.googleapis.com` 이름 풀이 실패 → 옛 PC 엑셀(26계정·82상품, 정상 33계정·113상품) 폴백 → 19:48 9계정(더이룸랩·꿈꾸는아재·가디즌·노바루트·문득·가을하늘 마켓·숨쉬는마음센터·김앤코·큰복상회) '관리대장에서 삭제됨 → 결과 완전 삭제'. 11-01 도 같은 폴백(run_log_261101_180006). 재현: 시험 D-134 2종이 옛 코드에서 실패 → 수정 → 통과.
- 버린 대안: 폴백은 두고 삭제만 금지(소유자 '실행 중단') · PC 엑셀 입력 소스 자체 제거(요청 범위 밖).
- 영향 범위: `registry_ui.auto_load_input`(신설) · `app_qt._auto_load_input`·`start_auto`·전체실행 입력 안내 · `input_list.InputList.from_file`·`parse_input_list` · `pipeline._reconcile_ledger_accounts` · `tools/verify_offline.py` · CLAUDE.md. HQ 포팅 대상. ⚠ 18:00 에 구글이 잠깐 끊겨도 그날 밤 실행 없음(재시도·재실행 없음).
- 상태: ACTIVE

### D-135 [INDEX_ACCOUNTS_FROM_LEDGER] 결과 계정목록 계정 = 관리대장 — 시트 없이 남은 줄 삭제·계정 수·제목 상품 수 정합 (2026-11-04, R84)
- 결정(소유자 2026-11-04 "계정목록은 관리대장의 목록을 가져오면 됨"): 구글 관리대장으로 실행할 때 사업자 시트 없이 `_계정정보` 에만 남은 계정 중 관리대장에 줄이 없는 계정을 결과(마스터·계정목록)에서 삭제. 대장에 있는 미수집 계정은 유지. ① '셀독 관리 계정 수' 는 그 결과로 대장 계정 수와 같아짐. 계정목록 제목 '상품 N개' = 판매중지·상품 없는 계정 줄 제외.
- 근거: 결과 시트 11-03 실측 — 계정 수 35 vs 수집 32 vs 대장 33(11-04). 초과 3 = 온라이프(hide4u)·플랜잇(plan_it)·하성진(lslfgh·대장 86행 숨김): 11-01 로그 `[SYNC] 대장O·결과X(신규/미수집) 3` 옛 엑셀 폴백이 로스터에 넣음 · 삭제 고리는 `account_sheets()` 만 돌아 시트 없는 줄은 영구 잔존. 제목 105 vs 판매 중 101(빈 계정 줄이 세어짐·1개 차이는 미확인). 재현: 시험 D-135 가 옛 코드에서 실패 → 수정 → 통과.
- 미결: 대장에 있으나 쿠팡 등록·매칭이 안 된 상품 줄(11-04 기준 9줄·브릿지웍스 등록 대기 4 등)을 계정목록에 표시할지는 소유자 확인 후 결정.
- 버린 대안: ① 계정 수만 대장 수로 바꾸기(계정목록 줄은 그대로 남음).
- 영향 범위: `workbook_lifecycle.roster_only_accounts`(신설) · `pipeline._reconcile_ledger_accounts` · `gsheet_index._title_request` · `tools/verify_offline.py`·`verify_gsheet_offline.py` · CLAUDE.md. HQ 포팅 대상.
- 상태: ACTIVE (본문 미결 해소 — D-139: 대장에만 있고 쿠팡에 안 맞는 상품 줄은 계정목록에 넣지 않음)

### D-136 [SALES_SUMMARY_OWN_ANALYTICS_COUNT] 통합판매현황 ① 위탁자 직접 관리 상품(관리 상품 포함) — 상품 등록 수 = 판매분석 데이터 (2026-11-04, R84)
- 결정(소유자 2026-11-04 "쿠팡 상품조회의 계정별 전체 등록 상품을 합산합니다. 판매중지 상품도 포함됩니다.==> 판매분석 데이타로 변경해줘"): 소제목 = '위탁자 직접 관리 상품(관리 상품 포함) — 쿠팡 판매분석 기준'. 상품 등록 수 = 결과 계정 4월~어제 판매분석 달 기록 전체 옵션의 등록상품ID 수 + 판매분석에 안 나온 관리 상품 수(D-132 계산·소유자 '관리 상품 포함' 유지). 누적 매출금액 = 결과 계정 전체(D-131·D-132) 그대로. 상품조회 기반 집계(D-133)는 저장 파일·코드 모두 배포 전 물리 삭제.
- 근거: 소유자 지시 — 상품조회 합산(10-29 원문 시험 7,901개)은 대량 등록·판매중지까지 들어가 D-130 의 판매분석 기준과 다름. D-133 은 커밋·배포 전이라 운용 영향 없음. 재현: T12·T13 이 판매분석 기준 기대값으로 옛 코드(D-133)에서 실패 → 수정 → 통과.
- 버린 대안: 상품조회 전체 합산(D-133) · 판매분석에 나온 ID 만 세기(관리 상품 일부 빠짐 — 소유자 '관리 상품 포함').
- 영향 범위: `sales_dashboard.own_scale` · `workbook_sales.unseen_products`·`refresh_sales_sheet` · `workbook_sales_dash._own_lines` · 시험 T12·T13 · `designs/SALES_SUMMARY.md` · CLAUDE.md. HQ 포팅 대상.
- 상태: ACTIVE (안 나온 관리 상품 더하기 SUPERSEDED by D-139)

### D-137 [STATEMENT_REAL_AD_MILK_RULES] 위탁정산서 실제 광고·밀크런 배분 규칙 — 캠페인 없는 조정 = 그 달 관리 비율 · 보고서 못 받은 달 = 비율에서 뺌 · 밀크런 글자 금액 읽기 · 기준일·관리기준 고르는 법 (2026-11-04, R83)
- 결정(소유자 2026-11-04 '2번 진행'): ① 광고 청구 자료의 캠페인 없는 줄(campaignId 없음 — 광고 프로모션 할인·청구 조정)은 그 달 캠페인 청구액의 관리 상품 비율로 나눈다. ② 보고서 파일을 아직 못 받은 달의 청구는 관리 몫 0 으로 치지 않고 비율 계산에서 뺀다(전부 못 받았으면 '추정' 유지). 파일을 받았는데 그 날·캠페인이 없으면 지금처럼 메모(관리 몫 0, D-119). ③ 밀크런 엑셀 금액 = 글자('14960')라 숫자로 읽는다. ④ 재생성 때 **정산집계는 원본보다 늦어야** 한다 — 뒤에 받은 원본이 있으면 `settlement_download.cmd_stats` 를 그 output 폴더에서 다시 돌린다. ⑤ **기준일 = 받은 지급 줄의 정산일이 빠지지 않는 날** — 만든 뒤 대조로 확인(E1 이 70:30 으로 어긋나면 기준일이 이름, E3 보류가 늘면 기준일이 늦음). ⑥ **관리기준 = 마지막 정상 실행의 결과** — 인터넷 끊김 등으로 수집 0 인 실행 뒤의 마스터는 쓰지 않고 그날 스냅샷을 쓴다.
- 근거(실측): output(29) 광고 청구 5,940,428(유라이프) 등 6~7월 보고서 미수집 → 옛 코드에서 관리 몫 0 → 비엔케이미디어 광고비 286,104 전액 0(입금 마이너스가 사라져 보임). 캠페인 없는 줄 3건: (DW)커머스 6월 −66,377(425,451 − 66,377 = 청구 359,074 = 쿠팡 요약 일치)·에벤에셀 6월 −2,132·문득 7월 −221 — 옛 코드는 생성 중단. 밀크런: 금액 글자라 합계 0 → 전 계정 '추정'이었음, 고친 뒤 입고 내역과 밀크런 번호 100% 일치. 정산집계: output(29) 04:32 집계 뒤 원본 14개 → 자동 검산이 (DW)커머스 57,490 차이를 잡음. 기준일: output(30) 11-02 = 14/35(11-03 지급 70% 줄 빠짐) → 11-03 = 28/35, output(29) 10-30 = 23/35(E3) → 10-29 = 30/35. 관리기준: output(29) 마스터 = 10-31 끊김 실행이 PC 엑셀 26계정으로 덮어씀 → 정산서 20곳 → 261029 스냅샷 = 26곳. 시험 `test_managed_alloc`(재현 후 통과).
- 버린 대안: 못 받은 달을 계정 판매 비율로 채움(실값·추정이 한 숫자에 섞임) · 캠페인 없는 줄을 계정 전체 비율로(달마다 관리 비율이 달라 부정확).
- 영향 범위: git 밖 `output\_분석_261013\정산스크립트\managed_alloc.py`(ad_share have)·`statement_managed.py`(_ad_files·_txt_num·_milk_rows)·`test_managed_alloc.py` — 백업 `_백업\`. 결과 `D:\토탈셀러\쿠팡 정산 자료\위탁정산서_20261103기준_관리상품_output30\`(26곳 · 독립 검산 26/26 · 대조 28/35). D-119 를 넓힘.
- 상태: ACTIVE (부분 SUPERSEDED by D-140 — D-140 이 적은 '비율 적용 부분', ①~⑥ 규칙 자체는 유지)

### D-138 [AD_REPORT_TEXT_RESPONSE] 큰 매출 성장 광고 보고서가 글자(text/csv)로 오면 엑셀로 바꿔 저장 · 칸이 다르면 저장 안 함 (2026-11-04, R83)
- 결정: `settlement_ads.report_xlsx` — 응답이 엑셀이면 그대로, 탭 구분 글자면 칸 이름(날짜·캠페인 ID·광고집행 옵션ID·광고비)을 확인하고 숫자 칸을 숫자로 바꿔 같은 파일명 `.xlsx` 로 저장. 칸이 다르거나 못 읽으면 저장하지 않고 SiteChangedError(그 계정 광고비 단계 실패 기록). `_get_bytes(text_ok=True)` 는 보고서 받기(`collect(get_report=)`)에서만 — 밀크런·정산 원본은 그대로 엑셀만 받는다.
- 근거: 운용 PC output(30) 처리기록 광고비 실패 — 꿈꾸는아재·디프픽 202604 `SiteChangedError: 파일 받기 실패: 200 text/csv; charset=utf-8 b'"날짜"\t"…`. 받는 달을 최근부터 처리해 실패한 달이 막히면 그 계정 그 앞 달도 못 받음(꿈꾸는아재 청구 8,824,001·디프픽 6,222,385 보고서 없음). 재현: `verify_settlement_runtime_offline` P45 가 옛 코드에서 실패 → 수정 → 통과 · P41(엑셀 보고서) 그대로 통과.
- 버린 대안: 파일을 .csv 로 저장(받음 판정·정산서 읽기까지 두 형식을 다뤄야 함) · 어떤 글자 응답이든 저장(오류 안내문이 보고서로 저장될 위험).
- 영향 범위: `src/coupang_analytics/settlement_ads.py` · `tools/settlement_download.py`(_get_bytes·collect_ads 호출) · `tools/verify_settlement_runtime_offline.py` P45. ⚠ 실제 글자 응답은 앞 60바이트만 확인(라이브 미실측) — 칸 구성은 엑셀 보고서와 같다고 가정, 다르면 위 검사로 실패 기록됨. 운용 PC = 새 zip 설치 후 적용 · 첫 실행 처리기록 광고비 줄 확인.
- 상태: ACTIVE

### D-139 [SALES_SUMMARY_TWO_SCALES_ANALYTICS] 통합판매현황 ① 상품 수·누적 매출 2가지(관리 상품만·계정별 전체) — 둘 다 순수 판매분석 기준 · 계정목록 상품 줄은 지금 기준 유지 (2026-11-04, R84)
- 결정(소유자 2026-11-04 "순수하게 판매분석에 나온 것을 기준으로 상품수와 누적매출금액을 산출해줘. 상품수와 누적매출금액을 산출은 2가지임, 하나는 관리상품만, 또 하나는 계정별 모든 상품으로 판매분석기준으로 적용하면 됨" · "계정목록의 상품 줄 ==> 계정 목록을 기준으로 해줘"): ①'관리 상품 등록 수'·'누적 매출금액' = 판매분석 달 기록 중 **관리 상품 범위**(계정목록 상품 = 결과 블록 VID + 같은 상품명·D-107)의 등록상품ID 수·받은 날 전부 합 ②'위탁자 직접 관리 상품(관리 상품 포함)' 2줄 = 같은 계산·**결과 계정 전체 상품**. 두 줄 모두 `sales_dashboard.sales_scale` 한 함수(범위만 다름). 판매분석에 안 나온 상품은 어느 쪽도 세지 않음(`unseen_products` 물리 삭제). 관리 상품 줄 괄호에 '계정목록 N개: 판매 중 · 판매중지' 를 함께 표시(판매분석 수와 다름을 보이기 위해). 계정목록 상품 줄 = 지금 기준 유지 — 대장에만 있고 쿠팡에 안 맞는 줄은 넣지 않음(D-135 미결 해소).
- 근거: 소유자 지시. 관리 상품 수는 옵션 재등록·판매자배송으로 한 상품이 여러 등록상품ID 일 수 있어 계정목록 109 와 값이 다를 수 있음(판매분석에 안 나온 상품은 빠지고 같은 상품명 다른 ID 는 따로 셈) — 그래서 괄호로 함께 표시. 재현: T12·T13 새 기대값이 옛 코드에서 실패 → 수정 → 통과.
- 버린 대안: D-128 '관리 상품 등록 수 = 계정목록 수'(소유자 '2가지 모두 판매분석') · D-132/D-136 안 나온 관리 상품 더하기(소유자 '순수하게') · D-133 상품조회.
- 영향 범위: `sales_dashboard.sales_scale`(own_scale 대체)·`Dashboard.mine` · `workbook_sales.refresh_sales_sheet` · `workbook_sales_dash._managed_lines`·`_count_text`·`_own_lines`·`_scale_rows` · 시험 T12·T13 · `designs/SALES_SUMMARY.md` · CLAUDE.md. HQ 포팅 대상.
- 상태: ACTIVE

### D-141 [COMPANY_STOCK_PALLET_FORMAT] 재고 현황 새 양식(팔래트/박스 줄) 읽기 — 총입고수량을 창고별 합산 (2026-11-04, R84)
- 결정(소유자 2026-11-04 "업로드 파일은 재고 현황임, 이파일을 분석해서 다시 반영해줘"): `read_stock` 이 두 양식을 읽는다 — 상품별 '상품명·현재고'(옛) · 팔래트/박스 줄 '제품명(판매처 제품명)·총입고수량'(새). 같은 창고·같은 제품 줄은 합산. 한 팔래트 두 상품 줄('슬라이딩선반 YG0197 / 발열장갑 W009'·'45 / 96')은 이름·수량 개수가 같을 때 나눠 각각 더함. 옵션 칸('N'·빈 칸)은 쓰지 않음. 매칭(D-072)·표기('창고 , 수량개')·미매칭 기존값 유지는 그대로.
- 근거: 구글 재고 시트 Sheet1 이 '재고현황 26.11.04 기준' 새 양식으로 바뀌어 옛 코드는 "헤더를 찾지 못함"으로 실패(재현·업로드 파일과 구글 Sheet1 677품목 차이 0). 실측: 데이터 729줄(3PL김포 422·비고 전부 '3PL김포 검수중' / 김포2 253·'재확인필요' / 3PL인천 54) · 혼합 줄 2 · '-' 1 · 음수 7품목 · 옛 탭 합계 127,032 → 새 110,514. 재현: R21 새 양식 시험이 옛 코드에서 실패 → 수정 → 통과. 11-04 실제 반영(이 PC·앱과 같은 `run_company_stock`·AI 포함): 관리대장 120줄 중 매칭 87·변경 73·미매칭 33(기존값 유지).
- 버린 대안: 총입고수량 대신 '총박스수×박스별 입고수량' 계산(혼합·낱개 줄은 빈 칸·입력값과 어긋나는 줄 10건 — 소유자 파일의 총입고수량이 기준) · 비고 '검수중·재확인필요' 줄 제외(그러면 재고 대부분이 사라짐).
- 영향 범위: `company_stock._stock_columns`·`_split_pallet`(신설)·`read_stock` · `tools/verify_registry_offline.py` R21 · CLAUDE.md. HQ 포팅 대상.
- 상태: ACTIVE (부분 SUPERSEDED by D-156 — 미매칭 줄 '기존값 유지' → '재고원장 없음' 표기)

### D-140 [STATEMENT_DEDUCTION_SCOPE] 위탁정산서 공제 관리 몫 = 비율 × 계정 전체 금지 — 관리 시작 전 공제 0 · 상품별 자료 금액 그대로 · 자료 없는 공제만 추정 표시 · F 표 칸 제목 공제 완료분/공제 예정분 (2026-11-04, R85)
- 결정(소유자 2026-11-04 '1~3번대로 고쳐서' · '공제 완료분·공제 예정분'): ① 관리 시작 달 = 관리 상품 첫 판매 또는 첫 물류비가 나온 달(계정별 자동). 그 전 정산일의 지급 줄 공제 = 관리 몫 0. ② 물류비·재고 보상·광고비·밀크런은 상품별 자료의 관리 상품 **금액 그대로**(광고비 = 청구가능 × 옵션 비율 + 부가세 10%, 쓴 달 다음 달 지급 줄부터 · 밀크런 파일 = 관리 시작 전달부터) — `managed_alloc.scoped`. ③ 관리 시작 뒤인데 상품별 자료가 없는 공제만 그 항목의 관리 비율로 나누고 설명에 금액을 적음, 표시 = 1% 이하 '실값' · 일부면 '일부 추정' · 전부면 '추정'. 자료가 공제보다 많으면 공제된 금액까지만. ④ 상품별 자료가 전혀 없는 항목(기타 공제·빠른정산 상환 등)은 지급 줄마다 그 판매 달 관리 정산 비율 × 줄 금액의 합. ⑤ 입금 완료/예정 나누기 = 관리 시작 전 줄 0, 그 뒤 줄은 ②·③ 몫 비율, ④ 항목은 줄별 비율. ⑥ F 쿠팡 공제 내역 칸 제목 = 공제 완료분·공제 예정분(돈이 들어온 것이 아님) · G 표는 입금 완료·입금 예정 유지.
- 근거: 소유자 지적 '너무 큰 금액이 공제'. 벅스(연다인) 실측 — 지급 줄 물류비 9,590,559(2025-12~2026-01 약 607만 집중) vs 상품별 리포트 합 3,839,721(그 시기 리포트 상품 = 발열내의뿐, 관리 상품 물류비 = 2026-06 부터), 옛 계산 = 비율 55.7% × 9,590,559 = 5,343,976. 광고비 6·7월 청구 660,354 = 7~9월 지급 줄 공제 합(1원 일치) · 관리 몫 614,496 인데 옛 계산 = 93.1% × 1,719,140 = 1,599,755. 고친 뒤 G 45,969 → 3,874,364. 빠른정산: 평균 비율을 곱하니 원더폴리 11,168,903 으로 E 7,791,904 초과 → 줄별 비율로 5,650,208. 재생성 output(30)·기준일 11-03: 자동 검산 26/26 · 독립 검산 26/26 · 대조 28/35 · 그 뒤 `test_managed_alloc` OK. '(실값)' 표시가 비율만 실제고 곱한 금액은 아니었음을 정정.
- 버린 대안: 비율 유지·표시만 추정(금액 오류가 남음) · 자료 없는 공제 전부 0(관리 기간 공제가 위탁자에게 안 잡힘) · 빠른정산에 관리 기간 평균 비율(E 초과) · 기간별 고정 지급일 매핑으로 공제와 판매 달 맞추기(쿠팡 공제 시점이 항목마다 달라 근거 부족).
- 영향 범위: git 밖 `output\_분석_261013\정산스크립트\statement_managed.py`(_month_add·_milk_rows·status_split·account)·`managed_alloc.py`(scoped)·`test_managed_alloc.py` — 백업 `_백업\statement_managed_관리시작전공제전.py` 등 · 결과 `D:\토탈셀러\쿠팡 정산 자료\위탁정산서_20261103기준_관리상품_output30\`(수정본으로 덮어씀). 앱 코드 변경 없음. 남은 사실: 광고비·물류비·밀크런 추정 합 약 2,968만(휴라엘 833만·웰빙곳간 638만·(DW)커머스 343만·니코에이블 326만 — 원인 미조사) · 관리 시작 달은 자동 판정이라 계약 시작일과 다를 수 있음(미대조). D-124 ③·D-119·D-137 의 비율 적용 부분을 대체.
- 상태: ACTIVE (부분 SUPERSEDED by D-146 — 자료 없는 공제 추정 표시 · D-154 — 관리 시작 판정 기준 · SUPERSEDED by D-185 — 관리 시작 달 정의(자동 판정 달 vs 계약 시작일 달 → 이른 달·계약 전 판매 제외))

### D-142 [DECISIONS_INDEX_FROZEN_SPLIT] DECISIONS 색인 도입 · 동결 구간을 별도 파일로 이동 — 세션 시작은 색인만 읽음 (2026-11-04, R87)
- 결정(소유자 2026-11-04 전역 규칙 'DECISIONS 색인'·'DECISIONS 정합성' 승인·시범 대상 = 이 저장소): ① `docs/DECISIONS_INDEX.md`(자동 생성·직접 수정 금지, `decisions-index.py`)를 쓴다. 세션 시작은 색인만 읽고 작업과 관련된 D번호·태그의 원문만 찾아 읽는다. ② '전환 전 결정' 한 줄 기록 181줄을 `docs/decisions/frozen-pre-2026-10-08.md`로 내용 그대로 옮긴다. 원래 자리에는 안내 줄만 남긴다.
- 근거: `docs/DECISIONS.md` 실측 448,601B(D-140 병합 후) 중 동결 구간 136,122B(30%). 색인 생성기 --init 결과 항목 141개 = D블록 141개. 옮긴 구간 바이트 동일·기존 D블록 141개 해시 불변을 스크립트로 확인.
- 버린 대안: 완전 대체 항목까지 별도 파일로 이동(4개 약 2.4%뿐·효과 작음) · 날짜 기준 이동(ACTIVE 는 오래돼도 유효) · `PARTIALLY SUPERSEDED` 새 표기(기존 `ACTIVE (부분 SUPERSEDED by D-xxx — 범위)` 유지).
- 영향 범위: `docs/DECISIONS.md` · `docs/DECISIONS_INDEX.md`(신규) · `docs/decisions/frozen-pre-2026-10-08.md`(신규) · `CLAUDE.md` 불변 정책 ⑤. 앱 코드 변경 없음. 추가 전용 원칙의 예외는 동결 구간 이동뿐(전역 규칙).
- 상태: ACTIVE

### D-143 [DECISIONS_AUDIT_MARKS] 전수 감사 A·B절 25건 상태 표기 반영 — 상태 줄 4개 추가 · 부분 대체 표기 21개 (2026-11-05, R88)
- 결정(소유자 2026-11-05 'A·B절 반영 승인'): `docs/decisions/audit-2026-11-04.md` A절(D-082·D-093·D-102·D-138 상태 줄 추가)·B절(D-010·D-016·D-021·D-022·D-024·D-043·D-047·D-064·D-070·D-076·D-087·D-094·D-098·D-106·D-116·D-119·D-121·D-124·D-126·D-128·D-137 부분 대체 표기)를 상태 줄에 반영한다. 본문은 바꾸지 않는다. D-124 는 '전부 대체'로 읽히던 표기를 부분 대체로 고친다. 대체 항목이 여럿이면 색인이 번호를 모두 읽도록 범위마다 `SUPERSEDED by D-xxx` 를 쓴다.
- 근거: 감사 판정(코드 읽기 대조·실행 확인 아님) + 반영 전 상태 줄 재확인·대체한 쪽 원문 재대조. 스크립트 검증 — 바뀐 줄은 상태 줄 21개·추가 줄은 상태 줄 4개와 이 항목뿐.
- 버린 대안: C·D절까지 함께 반영(범위 확인 전) · 본문 수정(추가 전용 위반) · D-124 를 SUPERSEDED 로 유지(실제로는 부분 대체).
- 영향 범위: `docs/DECISIONS.md` 상태 줄 · `docs/DECISIONS_INDEX.md` 재생성 · `docs/decisions/audit-2026-11-04.md` 상태 표시 · STATE. 앱 코드 변경 없음. C~F절과 소유자 판단 6건은 미반영.
- 상태: ACTIVE

### D-144 [R0_HQ_RULES_NOT_APPLIED] R0 '치명 오류 수정만·새 기능 금지'와 형식 변경 시 HQ 알림 의무를 적용하지 않음 (2026-11-05, R89)
- 결정(소유자 2026-11-05 D-036·D-035 질문에 각각 '적용 금지'): ① D-036 의 '이관 기간 R0 = 치명 오류 수정만·새 기능 추가 안 함'을 적용하지 않는다. ② D-035 의 'R0 형식을 바꿀 때 HQ 에 알리고 양쪽 DECISIONS 에 기록' 의무를 적용하지 않는다. 쌓여 있던 HQ 알림(D-079~D-141)도 전달하지 않는다. 이 두 조항만 바꾼다 — HQ 분리·R0 은퇴 계획·'포팅 필요' 기록·`_raw` 형식 유지·공유 잠금은 답을 받지 않았으므로 그대로 둔다.
- 근거: 감사 E절. 실측 — D-036 이후에도 R0 에 새 기능이 계속 추가됨(D-064·D-094·D-111·D-117) · HQ `R0_DATA_CONTRACT.md` 에 관련 형식 언급 0건 · STATE 다음 작업 8 'HQ 알림' 미처리 누적.
- 버린 대안: 의무 유지 후 누적분 일괄 전달(소유자 '적용 금지') · D-035·D-036 전체 폐기(질문 범위 밖).
- 영향 범위: `CLAUDE.md` 분리 안내 · STATE 다음 작업. 코드 변경 없음.
- 상태: ACTIVE

### D-145 [EVIDENCE_ORIGINALS_OPERATING_PC] 구매자명이 든 쿠팡 원본을 운용 PC output 아래 둘 수 있음 (2026-11-05, R89)
- 결정(소유자 2026-11-05 '원본을 둬도 무방함'): 운용 PC `output/정산/증빙/` 아래 구매자명 원본 보관을 허용한다. D-062 의 '소유자 로컬 증빙 폴더에만' 제한을 이 범위에서 대체한다.
- 근거: 감사 E절. D-067 실행 파일 `deploy/정산증빙_전체받기.bat` 이 이미 운용 PC output 아래에 저장 — 기록과 실제 운용이 어긋나 있었다.
- 버린 대안: 저장 위치를 output 밖으로 옮김(소유자 '무방').
- 영향 범위: 코드 변경 없음. output 을 밖으로 보낼 때 이 폴더를 빼는지는 답을 받지 않아 STATE 미해결로 남긴다.
- 상태: ACTIVE (output 외부 전달 시 포함은 D-149)

### D-146 [NO_ESTIMATE_ALL] 추정 금지를 위탁정산서 전체에 적용 — 쿠팡 자료에 없는 금액은 넣지 않음 (2026-11-05, R89)
- 결정(소유자 2026-11-05 '추정금지는 모두 적용'): D-081 의 추정 금지를 ④ 미정산만이 아니라 위탁정산서 전체에 적용한다. 자료 없는 공제·정산 중 판매의 비율 추정과 '(추정)' 표기를 쓰지 않는다. 자료가 없으면 D-081 과 같이 금액 없이 '자료 없음'·'확인 필요'로 둔다.
- 근거: 감사 E절. D-081 '추정은 안됨'과 D-116·D-126·D-140 의 '추정' 표시가 공존하고 있었고, `statement_managed.py`·`managed_alloc.py`(git 밖)에 '추정' 라벨이 남아 있다. '금액 없이 확인 필요' 방식은 D-081 본문 규칙을 그대로 넓힌 것이다.
- 버린 대안: ④ 에만 적용(소유자 '모두') · 추정 유지·표기만 변경 · 자료 없는 공제를 0 으로 침(D-140 이 버린 안 — 금액 없음과 다름).
- 영향 범위: git 밖 `output/_분석_261013/정산스크립트/statement_managed.py`·`managed_alloc.py` · 정산서 재생성. **구현 미완** — 지금 나와 있는 정산서(`위탁정산서_20261103기준_관리상품_output30`)는 이 결정 전 산출물이라 추정 금액이 들어 있다. 정산 세션 담당. 비율 배분(D-119·D-137 광고비 몫 등)이 추정에 해당하는지는 구현 때 항목별로 소유자 확인.
- 상태: ACTIVE (구현 D-153 · 부분 SUPERSEDED by D-148 — 쿠팡 정산예정 금액은 불가피한 경우 추정 허용)

### D-147 [WING_FINAL_DATE_CALENDAR_ONLY] 윙 최종액 30% 지급일 계산 규칙·골든 삭제 — 지급일은 쿠팡 정산캘린더만 (2026-11-05, R89)
- 결정(소유자 2026-11-05 D-007 질문에 '그럼 지워줘'): `payout.py` 의 익익월 1일 계산(`month_final_calendar`)과 골든 `PAYOUT_MP_WEEKLY_FINAL` 지급일 3줄을 삭제한다. `payout_date(PAYOUT_MP_WEEKLY_FINAL)` 은 ValueError. 정책 상수와 30% 금액 계산(`payout_amount`)은 `settlement_stats` 가 쓰므로 유지한다.
- 근거: D-007 — 골든 '보정 없음'이 2026 실측 29줄과 불일치, 지급일 정본 = 쿠팡 정산캘린더. 호출처 조사 — 지급일 계산을 부르는 운영 코드 0건(시험만). 시험 P2 핀이 옛 코드에서 실패 → 삭제 → 통과 · `verify_settlement_offline`(골든 12 → 9)·`verify_settlement_runtime_offline` 통과.
- 버린 대안: 다음 영업일 보정으로 고침(캘린더가 정본이라 규칙이 불필요) · 그대로 둠(틀린 기준이 골든에 남음) · 정책 상수까지 삭제(30% 금액 계산이 깨짐).
- 영향 범위: `src/coupang_analytics/payout.py` · `designs/coupang_golden_cases.json` · `tools/verify_settlement_offline.py` · `designs/SETTLEMENT_MODULE.md` · `designs/COUPANG_SETTLEMENT_DOMAIN.md` · `designs/DOMAIN_D8_SETTLEMENT_PHASE23.md`.
- 상태: ACTIVE

### D-148 [NO_ESTIMATE_FORECAST_EXCEPTION] 추정 금지의 예외 — 쿠팡 정산예정 금액은 불가피한 경우 추정 허용 (2026-11-05, R90)
- 결정(소유자 2026-11-05 '쿠팡에서 정산예정 금액은 불가피한 경우 추정 허용'): D-146·D-081 의 추정 금지에 예외 하나를 둔다. 쿠팡 정산예정 금액을 쿠팡 값으로 얻을 수 없어 불가피한 경우에만 추정을 허용한다. 그 밖의 금액은 D-146 그대로 추정하지 않는다.
- 근거: 소유자 답(D-146 구현 범위 질문). '불가피'의 구체 기준과 추정 금액의 표시 방식은 답에 없다 — 구현 때 항목별로 소유자 확인.
- 버린 대안: 추정 금지 예외 없이 전체 적용(소유자 예외 지정).
- 영향 범위: git 밖 `output/_분석_261013/정산스크립트/statement_managed.py`·`managed_alloc.py` 구현 범위. 코드 변경 없음.
- 상태: ACTIVE

### D-149 [EVIDENCE_ORIGINALS_EXPORT_INCLUDED] output 을 밖으로 보낼 때 정산 증빙 폴더를 포함한다 (2026-11-05, R90)
- 결정(소유자 2026-11-05 '밖으로 보낼 때 정산\증빙 폴더 포함해줘'): output 외부 전달 시 구매자명 원본이 든 `정산/증빙` 폴더를 빼지 않고 포함한다.
- 근거: D-145 범위 밖으로 남긴 미결의 답. 저장소 코드 검색(src·tools·ui·deploy 의 압축 호출·증빙 제외 문구) 결과 이 폴더를 제외하는 코드가 없어 지금 동작과 같다.
- 버린 대안: 전달 때 폴더 제외(소유자 '포함').
- 영향 범위: 코드 변경 없음. 전달받는 쪽에 구매자명 원본이 함께 간다.
- 상태: ACTIVE

### D-150 [REGISTRY_LINK_NO_GUARD] 원장 링크 코드 가드를 만들지 않음 — 설정에 넣은 링크를 따른다 (2026-11-05, R90)
- 결정(소유자 2026-11-05 D-095 질문에 '가드 없이 넣은 원장 링크를 따른다'): 설정 탭 원장 링크에 코드로 거부 조건을 두지 않는다. 앱은 넣은 링크를 그대로 따른다.
- 근거: D-095 버린 대안에 '소유자 미결정'으로 남은 건의 답. 현재 코드에 거부 로직이 없어 지금 동작과 같다.
- 버린 대안: 관리대장 주소 거부 가드(소유자 불필요).
- 영향 범위: 코드 변경 없음. 관리대장 주소를 넣으면 D-095 의 사고(대장 파일 안 원장 시트 5개 생성)가 다시 날 수 있다. 운용 PC 링크 값은 이 PC 에서 확인 불가.
- 상태: ACTIVE

### D-151 [CLAUDEMD_SPLIT] 프로젝트 CLAUDE.md 를 색인+상시 규칙으로 축소 — 상세는 원문 그대로 문서로 이동 (2026-11-05, R91)
- 결정(소유자 2026-11-05 '축소할 때 그간 결정된 정책이 삭제되면 안 된다'·전역 규칙 200줄 미만·20KB 미만): `CLAUDE.md` 에는 머리 정책·실행·문서 지도·상시 규칙 한 줄 요약·코드 건강 규칙·병렬 개발·환경만 남긴다. 아키텍처 = `docs/ARCHITECTURE.md`(기존 문서 뒤에 추가), 함정 = `docs/PITFALLS.md`, 제약 = `docs/CONSTRAINTS.md`, 운영 정책 = `docs/OPERATIONS_POLICY.md`, 현재 상태 = `docs/STATUS_HISTORY.md`(동결). 이후 진행 상황은 `CLAUDE.md` 에 쌓지 않고 `STATE.md`·DECISIONS 에 쓴다.
- 근거: 최근 세션 첫 응답 입력 89,111(10-10) → 105,140(11-05) 토큰으로 증가(transcript usage 실측). `CLAUDE.md` 59,590B 가 매 세션 자동으로 읽힘. 내용 줄 141개 전부 원문 일치 확인 — 대조표 `docs/decisions/claudemd-move-2026-11-05.md`(제거 0건).
- 버린 대안: 요약해서 다시 쓰기(엣지케이스 유실) · `@` 가져오기(자동으로 읽혀 축소 효과 없음) · `DESIGN.md` 에 합치기(121KB 라 찾기 어려움) · 중복 제거(이번 범위에서 0건).
- 영향 범위: 코드 동작 변경 없음. 상세가 자동으로 안 읽히므로 세션은 문서 지도를 보고 해당 문서를 직접 읽어야 한다. 코드 주석·옛 설계서의 'CLAUDE.md' 참조는 그대로 두고 문서 지도로 연결. 옮기며 발견한 어긋남 5건은 고치지 않음(대조표·STATE 미해결).
- 상태: ACTIVE

### D-152 [CONTRACTOR_SETTLE_PAYOUT_RATIO] 연다인·장대익·서달원 계약자 정산 = 쿠팡 실지급 × 계약 조건 · 원가 계산 없음 (2026-11-05, R92)
- 결정(소유자 2026-11-04 대화): ① 계약자별 등록 상품 = 관리대장 기준(계약 상품별로 팔리지 않으므로 계약 상품에 묶지 않음) ② 기준 금액 = 쿠팡 실지급(정산서 최종 지급액) ③ 판매분 원가는 계산하지 않고 실지급을 비율로 나눔 ④ 장대익 = 갑 70 : 을 30 ⑤ 서달원 = 아기수영장 7:3·헬스매트 9:1·나머지 상품은 DW커머스 계약(계약금 14,000,000 + 약 30% = 목표 정산금 18,200,000 달성 시 종료, 그전 회사 몫 없음) ⑥ 연다인 = 원금 대비 수익금 20% 보장(보장 총액 25,085,280)·회사 수익 없음·정산 대상 = 2026년 5월 이후 등록 상품·쿠팡 화재 보상금 8,697,763(2026-08-20 쿠팡풀필먼트서비스 입금) 수익 포함.
- 근거: 소유자 지시 원문('원가 계산은 하지 말고, 수익은 판매 금액을 비율로 나누는 것임'·'쿠팡 실지급 기준 맞음'·'연다인은 수익금 원금 대비 20% 보장 조건임. 회사 수익은 없음'·'5월부터 등록한 상품을 기준으로'·'쿠팡화재로 배상 받는 금액으로 수익에 포함'). 계약서 6건 원문·페이지 이미지 대조. 11-03 기준 결과 = 실지급 합계 47,692,781·갑 42,094,845·을 5,597,936. 연다인 재계산은 기존 범위로 3,874,364 재현 후 범위만 교체.
- 버린 대안: 계약금 먼저 회수 후 초과분 배분(소유자 지시 전 권장안) · 판매수량 × 생산단가(계약 제4조 문구·계약에 없는 상품 원가 없음) · 판매금액 기준 배분(소유자 '실지급 기준 맞음').
- 영향 범위: 세 계약자 정산표만. 산출물 `D:\토탈셀러\쿠팡 정산 자료\계약자별_정산표_연다인_장대익_서달원_20261103기준_최종_화재보상포함.xlsx`·`정산서_벅스_연다인_bux1004_5월등록상품_20261103기준.xlsx`, 재생성 스크립트 `D:\토탈셀러\쿠팡 정산 자료\계약자별_정산표_스크립트\`. 앱 코드·위탁정산서 생성 코드 변경 없음. 다른 계약자에 같은 방식을 쓸지는 미정. `D:\modusign` D-019·D-020 의 판매분 원가 공제 규칙과 다르며 그쪽 기록은 건드리지 않음. 표에 추정분이 있어 D-146·D-148 판단 필요(STATE 미해결).
- 상태: ACTIVE (부분 SUPERSEDED by D-155 — 서달원 상품군 실지급 계산(계정 합계 비율 배분 → 직접 합산)·최종 산출물 파일)

### D-153 [NO_ESTIMATE_SCOPE_IMPL] 추정 금지 구현 범위 — 쿠팡 자료 비율 배분 유지 · 불가피 = 계정 합계로만 오는 정산 중 판매 · 자료 없는 공제 = 관리 몫 없이 참고에 쿠팡 금액 (2026-11-05, R93)
- 결정(소유자 2026-11-05 '추천안대로 진행'): ① 쿠팡 자료 비율 배분(광고 옵션 비율·캠페인 없는 조정·서비스이용료 판매 비율·밀크런 적치 수량·주문 안 상품 개수·입금 완료/예정/보류 칸 나누기)은 추정이 아니다. 유지하되 표시는 '실값'이 아니라 '쿠팡 자료 비율'로 쓰고 나눈 자료를 적는다. ② D-148 의 '불가피' = 쿠팡이 계정 합계로만 주는 정산 중 판매뿐이다. 상품별 정산 자료가 나오기 전까지 판매분석 관리 판매 비율로 나눈다. 공제는 예정분이라도 예외가 아니다. 그 달 판매분석이 없으면 금액 없이 확인 필요. ③ 표시 = '정산 예정 — 쿠팡 상품별 자료 전, 판매 비율로 배분 · 정산 파일이 나오면 바뀜'. '추정' 낱말은 쓰지 않으며 이 금액은 D-148 예외로 남는다. ④ 상품 자료 없는 공제(물류비·광고비·밀크런·재고 보상의 자료 없는 부분·기타 공제·빠른정산 상환·보류 해제 등)는 관리 몫에 넣지 않고 F·G 에서 뺀다. 1쪽 참고 묶음 '상품 자료 없는 금액 — 확인 필요'에 쿠팡 금액만 적는다. 0 으로 처리한 것이 아니며 계산 근거 시트의 관리 몫 칸 = '자료 없음'.
- 근거: 측정(옛 코드·output(30)·기준일 11-03) — 26/26 재현. 비율 추정 공제 절대값 합 약 4,500만(물류 14,141,685·광고 13,752,961·빠른정산 12,714,315·밀크런 1,787,536·보상 1,071,055·보류 해제 770,656·기타 525,351). 쿠팡 자료 비율 중 비율이 실제 작동하는 금액은 작음: 섞인 캠페인 청구 2,907,049(관리 1,056,103)·서비스이용료 931,164·밀크런 섞인 입고 0·여러 상품 주문 배송비 0. 정산 중 판매 계정 전체 149,562,967 → 관리 몫 판매 92,697,283·정산 45,513,357 = 쿠팡이 상품별로 주지 않음. 시험 test_managed_alloc 재현 실패(scoped TypeError) → 수정 → 통과.
- 재생성(기준일 2026-11-03·정산집계_261103_224131): 자동 검산 26/26 · 독립 검산 26/26 · 대조 28/35(전과 같음) · 정산서 '추정' 문구 0건(파일 27개). 합계 A·E 불변 · G 290,066,781 → 318,432,603(+28,365,822) · 입금 완료 260,568,717 → 276,524,713 · 입금 예정 28,671,110 → 41,080,910.
- 버린 대안: 비율 배분까지 전부 제거(상품별 청구액이 쿠팡에 없어 광고·서비스이용료를 못 나눔) · 정산 중 판매 제외(소유자 예외 D-148) · 공제 예정분까지 예외에 넣음 · 참고 금액도 숨김.
- 영향 범위: git 밖 `output\_분석_261013\정산스크립트\statement_managed.py`(put·status_split 의 plain 가중 삭제·nodata·표시 문구)·`managed_alloc.py`(scoped 인자 변경)·`test_managed_alloc.py` — 백업 `_백업\*_D146전.py`. 결과 `D:\토탈셀러\쿠팡 정산 자료\위탁정산서_20261103기준_관리상품_output30_D146\`(26곳+요약). 옛 output30 폴더는 그대로 둠(보내면 안 됨). 앱 코드 변경 없음. 남은 사실: G 는 공제 자료가 없는 만큼 실제보다 크게 보일 수 있음 · 빠른정산 상환이 빠져 입금 완료가 줄어든 계정 있음(원더폴리 5,645,405 → 1,230,663) · 공제 자료 공백 원인(시점 차이 여부) 달별 대조 안 함.
- 상태: ACTIVE

### D-154 [DEDUCTION_SCOPE_SALE_PERIOD] 위탁정산서 공제 범위 = 지급 줄 판매 기간 기준 — 관리 시작 전 판매분 제외 · 밀크런은 시작 전달부터 (2026-11-05, R94)
- 결정(소유자 2026-11-05 '판매 기간 기준 수정'): 공제 관리 몫의 범위를 지급일이 아니라 지급 줄 **판매 기간 시작 달** ≥ 관리 시작 달로 자른다. 광고비의 '쓴 달 다음 달 지급 줄부터'도 없앤다(판매 기간 달이 광고 쓴 달과 맞음). 밀크런은 입고가 판매보다 먼저라 파일·공제 둘 다 관리 시작 전달부터. 입금 칸 나누기(status_split)와 보류 해제도 같은 기준.
- 근거(19계정 달별 대조·output(30)): 판매 기간 기준 2026-06~09 합이 상품 자료와 거의 같음(물류 6월 16.74M/16.79M·9월 21.75M/21.48M · 광고 8.30M/8.27M·8.11M/8.28M · 에벤에셀 물류 3~7월 원 단위 일치). 물류비 공백 53.41M = 시작 전 판매분 20.59M + 10월 이후 자료 미도착 25.48M + 2025-11 자료 없음 7.29M + 기타 0.04M · 광고비 공백 31.06M = 시작 전 0.66M + 10월 이후 11.32M + 2025-11~2026-03 자료 없음 19.19M − 0.11M. 시험: `due_since` 없어 실패 → 수정 → 통과. 첫 재생성에서 밀크런을 시작 달부터 자르자 효성 G +31,350 — 자료 범위(시작 전달)와 어긋난 회귀라 고침.
- 재생성(기준일 2026-11-03): 자동 검산 26/26 · 독립 검산 26/26 · 대조 28/35 · 추정 문구 0건 · A·E·G 불변(G 318,432,603) · 입금 완료 276,524,713 → 276,633,949(5계정) · 참고 칸 확인 필요 금액 합 210,781,537 → 139,884,181(빠른정산 111,992,019 → 65,362,067 · 물류비 53,418,143 → 32,827,919).
- 버린 대안: 지급일 기준 유지(시작 전 판매분이 확인 필요로 잘못 잡힘) · 밀크런도 시작 달부터(입고 먼저라 관리 상품 몫이 줄어듦).
- 영향 범위: git 밖 `output\_분석_261013\정산스크립트\managed_alloc.py`(due_since)·`statement_managed.py`(account·status_split)·`test_managed_alloc.py` — 백업 `_백업\*_D154전.py`. 결과 `D:\토탈셀러\쿠팡 정산 자료\위탁정산서_20261103기준_관리상품_output30_D146\`(덮어씀). 앱 코드 변경 없음. D-140 ① '그 전 정산일'을 대체. 남은 사실: 10월 이후 자료 미도착 · 옛 달 광고 자료 미수집 · 재고 보상 0.52M·밀크런 4~9월 2.09M 차이 미확인.
- 상태: ACTIVE

### D-155 [CONTRACTOR_NO_ESTIMATE] 계약자 정산표에도 추정 금지 적용 — 서달원 상품군 = 직접 합산 · 정산 중 금액만 D-148 예외 · 재등록 7개 = 근거 있는 판정 (2026-11-05, R96)
- 결정(소유자 2026-11-05 '계약자 정산표에도 추정 금지를 적용해'): D-146·D-148·D-153 을 D-152 계약자 정산표에도 적용한다. ① 서달원 상품군 실지급 = 계정 합계 비율 배분을 폐기하고 정산서와 같은 규칙으로 범위만 상품군으로 바꿔 직접 합산(관리 시작 달은 계정 전체 값으로 고정). ② 정산 예정(10·11월 정산 중) 금액만 D-148 예외로 판매 비율 배분·'정산 예정' 표시. ③ 연다인 재등록 7개(판매 240,950원)는 쿠팡 등록일이 없어 등록일 자체는 알 수 없으나 금액은 쿠팡 값이므로, 포함 여부를 근거(계약 보냉백과 같은 상품명·판매분석 첫 판매 2026-07 이후·등록상품ID 가 5월 등록 상품보다 뒤)와 함께 판정으로 남긴다.
- 근거: `계약자별_정산표_스크립트\run_seo_groups.py` 실행 — 정산서 기준 재현 G 29,485,891 · 상품군 합 E 33,609,453 일치 · 공제 5항목 일치 · G 끝전 1원. 옛 비율 배분 오류 실측: 판매분석 10·11월 수영장·헬스매트 판매 0원인데 옛 식은 정산 중 금액을 두 상품군에도 나눔 · 광고 옵션 2개(95322412626·95189065026)는 모두 아기수영장인데 옛 식은 광고비를 상품군 전체에 나눔. 변경: 수영장 8,070,596 → 6,061,980 · 헬스매트 8,899,156 → 9,770,994 · 나머지 12,516,139 → 13,652,917 · 서달원 회사 몫 3,311,095 → 2,795,693 · DW 목표까지 5,683,861 → 4,547,083 · 세 계약자 회사 몫 합계 6,276,072 → 5,760,670.
- 버린 대안: 상품군 금액을 전부 '확인 필요'·미배분(직접 합산이 가능하므로 불필요) · 재등록 7개 제외(금액은 쿠팡 값이고 근거가 충분).
- 영향 범위: 세 계약자 정산표만. `build2.py`·`run_seo_groups.py`·`seo_groups_D146.json`(git 밖) · 산출물 `D:\토탈셀러\쿠팡 정산 자료\계약자별_정산표_연다인_장대익_서달원_20261103기준_D146_상품군직접합산.xlsx`. 앱 코드·`statement_managed.py` 변경 없음. 표는 공제 확인 필요 금액 미반영 상태라 발송 판단은 소유자.
- 상태: ACTIVE

### D-156 [COMPANY_STOCK_NONE_LABEL] 회사보유재고 미매칭 = '재고원장 없음' 표기 — 기존값 유지 폐기 · AI 판단 못 한 줄만 기존값 (2026-11-05, R96)
- 결정(소유자 2026-11-05 '회사 제고 미매칭시 기존값유지는 적절하지 않음. 재고 원장에 없는 경우 재고원장 없음으로 표기해줘'): 관리대장 회사보유재고 칸과 계정목록 표기에서, 규칙·AI 로 재고현황에 없다고 판정한 상품 = `재고원장 없음`. 옛 값을 남기지 않는다. 단 AI 장애·AI 없는 실행·AI 답에서 빠진 줄은 '없다'고 확인된 것이 아니므로 기존값 유지 + 별도 로그(`AI 판단 못 함`)·`StockResult.undecided`. 사람이 적은 메모(빈 칸·재고원장 없음·앱 표기 '창고 , 수량개'가 아닌 값)는 유지(소유자 2026-11-05 '유지해줘'·`StockResult.memo`). 계정목록은 대장 메모를 읽지 않아 없음 판정이면 재고원장 없음으로 표시.
- 근거: 11-05 05:56 로그 미매칭 31줄과 첫 탭 대조(재고 시트 3개 탭 전체 낱말 검색): 지금 칸 값 중 `검단 , 1,020개`(와이어 빨래줄 R20) 등은 어느 탭에도 없는 상품의 오래된 값. 재현: R21 기대값 변경 후 옛 코드 실패 → 수정 → 통과.
- 버린 대안: AI 실패도 재고원장 없음(재고가 있어도 없다고 적게 됨) · 기존값 유지(소유자 부적절 판정).
- 영향 범위: `company_stock.py`(STOCK_NONE·undecided·write_company_stock·apply_to_workbook·로그)·`company_stock_match.py`(judged_none·ask_ai 빠진 줄 처리) · `tools/verify_registry_offline.py` R21·R21c. D-141 의 '미매칭 기존값 유지' 부분을 대체. HQ 포팅 대상. 운용 PC 적용 = zip 재빌드·설치 후. 묶음 이름 줄(꿈꾸는아재 긴팔 4종·반팔 11종·김앤코 루노르 제품)은 대장 줄을 코드별로 나누는 담당자 작업으로 수용(소유자 2026-11-05)·지금은 메모 유지. 실제 반영(2026-11-05 14:21·이 PC·첫 탭·AI 포함): 120줄 = 매칭 87·미매칭 24·메모 유지 9·변경 96·다른 열 변경 0.
- 상태: ACTIVE

### D-157 [COMPANY_STOCK_AI_JUDGE] 회사보유재고 판정 = AI — 규칙은 후보만·상품명 완전 일치만 그대로 · 쿠팡 상품명을 함께 판단 (2026-11-05, R96)
- 결정(소유자 2026-11-05 '상품명은 AI로 판정하기로 했어. 직원이 명확하게 하지 않는 경우가 있음'): 괄호 앞/안·색상별 줄·모델번호 규칙은 AI 에게 맨 앞 후보로 보일 뿐 확정하지 않는다. AI 없이 쓰는 것은 상품명 완전 일치뿐. 후보의 색상·사이즈 줄은 한 후보로 묶어 보이고, 줄당 후보 10개·30줄씩 나눠 묻는다. AI 를 못 쓰면 규칙 값으로 넘어가지 않고 기존값 유지(계정목록은 공란). 저장된 판정은 규칙 후보가 달라지면(새 색상·사이즈 줄) 다시 판정. 관리대장 이름을 코드별로 나눠 달라는 담당자 요청은 하지 않는다(세션 내 권고 철회).
- 근거(실측 11-05 첫 탭 677품목·대장 121줄): ①모델번호 규칙이 `드라이기거치대 Y003` 에 `안전화 Y003` 재고를 붙여 14:21 대장에 틀린 값 기록(첫 탭에 드라이기거치대 없음). ②`코골이 방지 기구` = 쿠팡 상품명 `코골이 방지 비강확장기 숨통박사…` 인데, 14:21 반영은 이 PC 에 `_매칭고정.json` 이 없어 AI 가 대장 이름만 보고 후보에서 `비강확장기 HR-01BK` 를 못 받음. ③AI 지시문의 '같은 모델번호' 때문에 모델번호 없는 재고 `거북목교정기` 를 놓침 → 한쪽에 번호가 없으면 종류·용도로 판단하게 수정. 미리보기(쿠팡 상품명 포함·실제 AI): 전체 121 = 완전 일치 62·AI 매칭 25·없음 34·판단 못 함 0, 현재 대장과 달라지는 줄 = 코골이(→3PL김포 2,682개)·드라이기(→재고원장 없음) 2줄. 시험 R21d 추가.
- 버린 대안: 규칙 1~3 확정 유지(실제 오판 발생) · 직원에게 대장 정리 요청(소유자 기각) · 줄 전체 AI 판정(완전 일치는 판단할 것이 없고 비용·흔들림만 늘어남).
- 영향 범위: `company_stock_match.py`(EXACT·_shortlist·_label·_ask_batch·from_cache rule·지시문)·`company_stock.py`(_match_rows·apply_to_workbook)·`pipeline_gsheet.py`(매칭 고정 기록 없음 경고) · `tools/verify_registry_offline.py` R21d. 새 코드 첫 실행 전에는 운용 PC 저장 판정이 없어 첫 계정목록에서 규칙 후보 줄이 공란일 수 있음(같은 실행 끝 관리대장 역기록이 판정 저장 → 다음 실행부터 채워짐). 남은 한계 = 묶음 이름(긴팔 4종·반팔 11종·루노르 제품·안전화 JH)은 재고 탭 이름만으론 어느 코드인지 AI 도 못 정함(칸의 메모 유지).
- 상태: ACTIVE

### D-159 [MANAGED_SCOPE_CONTRACT_WINDOW] 관리 상품 = 관리대장 우선 · 대장에서 이력 없이 바뀐 상품만 계약일~대장 등록일 기간으로 보강 · 위탁자 브랜드 제외 (2026-11-05, R96)
- 결정(소유자 2026-11-05): ① 관리 상품은 관리대장이 우선이다. 계약서 상품과 실제 등록 상품이 다를 수 있기 때문이다. ② 대장에서 등록상품을 바꾸며 이전 상품을 지워 이력이 없는 경우에 한해, 쿠팡 등록일과 계약일을 비교해 관리 상품을 찾는다. 기간 = 2026-03-20 이후 셀독 계열 계약 중 가장 이른 계약일 ~ 대장 상품 중 가장 늦은 등록일(에벤에셀·니코에이블 지시를 전 계정에 적용). ③ 위탁자 브랜드 상품은 제외한다. ④ 3월 20일 전에 등록된 대장 상품은 대장 우선이라 유지한다.
- 구현 판단(소유자 답을 넓혀 적용한 부분): 제로리스크·투자·위임장 계약은 기간에서 뺌 · 외부 프로그램(API_OVERLINK) 등록은 위탁자 등록으로 보고 제외 · 히카마 제외(D-023②)·미니선풍기 포함(D-023①) 유지 · 기간 안이어도 회사 상품·대장 유사 근거가 없는 상품 7개(판매금액 6,196,010·귤·사과 등)는 제외(소유자 2026-11-05 '제외해줘').
- 근거: 등록일 = `_raw/*_vendor_inventory` createdOn(9,274상품) · 등록상품ID 시간순 역전 0건 → 삭제 상품도 ID 로 판단 · 계약일 = 모두싸인 인덱스 3개 + 11-05 다운로드 331건 제목. 재생성(기준일 2026-11-03·정산집계_261103_224131): 독립 검산 26/26 · 추정 문구 0건 · 대조 28/35(전과 같음) · 변경 4계정만 = 니코에이블 G 16,614,077 → 28,476,841 · 비엔케이미디어 2,071,748 → 6,836,488 · 와이에이치 4,018,369 → 4,216,238 · 벅스 4,215,866 → 4,140,353(15L 보냉백 추가로 판매·공제가 함께 늘어 G 는 줄어듦).
- 버린 대안: 3월 20일 이후 등록 상품 전체 정산(소유자 '다시 지시'로 대체) · 2026-03-20 전 계약까지 기간에 포함(에벤에셀 2024년 상품 유입) · 위탁자 브랜드 포함 · 근거 없는 상품까지 전부 포함.
- 영향 범위: git 밖 `output\_분석_261013\정산스크립트\run_contract_window.py`(statement_managed.py 수정 없이 scope 보강)·`contract_window_candidates.py`·`contract_window_classify.py`·`contract_window_scope.py`·`contract_window_scope_20261105.json`. 결과 `D:\토탈셀러\쿠팡 정산 자료\위탁정산서_20261103기준_관리상품_output30_D146_계약기간\` · 판정표 `D:\토탈셀러\쿠팡 정산 자료\계약기간_관리상품_판정표_20261105.xlsx`. 계약자 정산표(D-152)는 금액 변화 없음(장대익·서달원 변경 없음·연다인은 5월 범위 정산서 사용). 앱 코드 변경 없음. 셀독 계열 3/20 이후 계약이 없는 계정은 보강되지 않음(모두싸인 밖 계약·웨이브텍 등 미확인).
- 번호: 처음 D-155 로 기록 → [CONTRACTOR_NO_ESTIMATE] 와 번호 중복이라 D-159 로 변경(소유자 2026-11-06). 내용 변경 없음.
- 상태: ACTIVE

### D-158 [PROMO_FILL_CLEAR] 체험단 7일 배경 — 7일 밖 일자 칸 색을 매 실행 지움 · 체험단 시트를 한 줄도 인식 못 하면 기존 시작일 유지 (2026-11-05, R96)
- 결정(소유자 2026-11-05 '체험단 진행을 보여주도록 색상을 넣었는데, 중간에 다시 조금 진하게 처리되었어' → 수정 승인 '둘 다 진행해줘'): 사업자 시트 일자 칸은 체험단 7일 구간 밖이면 매 실행 색을 지운다(지표·키워드 줄 모두). 시트에 내용이 있는데 체험단 줄을 한 줄도 인식 못 하면 시작일을 지우지 않고(None) ❌ 로그를 남긴다. 완전히 빈 시트는 0줄(오류 아님).
- 근거(output (31) 날짜별 보관본 비엔케이미디어): `_sty_cell` 이 색 없을 때 칸을 안 지워, 값은 날짜 따라 옆 칸으로 옮겨 가는데 색은 물리 칸에 남음. 10.28~ 8일째 이후에도 FFF6DB 지속 → 11.02·03 로그 '체험단 시트 0줄 → 시작일 연결 0개'(시작일 11개 전부 삭제)로 재도색이 멈춰 색이 하루 한 칸씩 밀림(11.03 = 10.23 FFC000) → 11.04 시작일 복귀(10.21)로 10.21~27만 재도색, 밀린 잔상이 10.28 FFE492·10.29 FFEDB6 로 남아 '다시 진해짐'. output (31) 7일 밖 색 남은 블록 = 253 중 12. 핀 S4b 재현 실패 → 수정 → 통과.
- 미확인: 11.02·03 이 0줄이 된 이유 — `promo_sheet.py` 는 10-27 이후 변경 없음, 11.04 = 36줄·지금 = 40줄 정상. 그 이틀 머리글이 달랐을 가능성(추정·구글 버전 기록으로 확정 가능).
- 버린 대안: 잔상 일회성 정리만(같은 일 재발) · 0줄이면 실행 중단(체험단 표시 때문에 수집 전체를 멈출 이유 없음).
- 영향 범위: `workbook_render.py`(`_NO_FILL`·`_style_metric_rows`·`_style_keyword_rows`) · `promo_sheet.py`(`read_promo_sheet` log) · `ui/app_qt.py` 호출 1줄 · `tools/pin_apply_style.py` S4b · `tools/verify_offline.py` [13b]. 구글 결과 시트는 `worksheet_to_requests` 가 서식 전체 교체라 새 코드 다음 실행에서 함께 지워짐. 운용 PC = zip 재빌드·설치 후 적용.
- 상태: ACTIVE

### D-160 [COUPON_DAILY_SNAPSHOT] 윙 할인쿠폰 목록 수집·재고현황 날짜별 보관 (2026-11-06, R96)
- 결정(소유자 2026-11-06 '앱에 쿠폰 목록 수집 넣어줘'·'재고현황 날짜별 보관 적용해'): ① 판매수집의 로그인 세션에서 윙 할인쿠폰 목록과 쿠폰별 옵션을 읽기만 하여(same-origin GET) 사용 금액 0 포함 전부를 응답 전체로 output/쿠폰목록_일별/{계정}/{날짜}.json.gz 에 쌓는다. ② 재고현황 응답 원문도 추가 조회 없이 output/재고현황_일별/{계정}/{날짜}.json.gz 에 쌓는다. 파일은 덮어쓰지 않는다. 쿠폰은 그날 완료본이 있으면 재조회하지 않고, 부분본만 있으면 다시 받아 완료본을 새로 쓴다. 재고는 같은 날 재수집 시 시각 붙은 파일을 추가한다. 조회 간격 = 기간 조회와 같은 _PERIOD_GAP_SEC. 실패는 그 계정 쿠폰 조회만 멈추고 로그를 남기며 ① 수집은 계속한다.
- 근거: 3계정 쿠폰 대조(쿠팡_쿠폰산식_검증_3계정_261106.md) — 사전 고정 규칙 유지·시작일 아닌 날 2,518/2,570줄. 윙 쿠폰 재현 오차 휴라엘·서달원 0.00% · 니코에이블 −7.17%(목록 밖 쿠폰). 재고현황 pricing 스냅샷 쿠폰 91.0% 일치(쿠팡_정산예정금_항목별산식_261106.md). _raw 는 실행마다 덮어써 과거값이 남지 않음.
- 버린 대안: 칸을 골라 저장(수량 곱 쿠폰 구분 칸을 아직 못 찾아 전체 보관) · 같은 날 교체(덮어쓰기 금지) · _raw 파일명에 날짜 추가(기존 소비처 영향).
- 영향 범위: pipeline_sales(_login_and_discover·_dump_raw), wing_coupons·daily_snapshot 신설, 게이트 1종 추가. ① 수집 시간 증가(상한 약 50분 추정·라이브 측정 전). 로그인·프록시·브라우저 정책 불변.
- 미확인: 앱 코드의 라이브 호출 없음 · requestStartAt·requestEndAt 값 형식 · 90일 초과 조회 가능 여부 · 수량 곱 쿠폰 구분 칸.
- 상태: ACTIVE

### D-161 [SETTLE_DOWNLOAD_ALL_2026] 정산 자료 100% 받기 — 2026-01부터 · 기존 정산 다운로드에 추가 · 판매분석 수집만 1월부터(표시는 4월 유지) · 광고·밀크런은 2025-12부터 (2026-11-07, R97)
- 결정(소유자 2026-11-07): ① 목표 = 쿠팡이 제공하는 정산 관련 자료를 2026-01부터 100% 내려받기 · 용도 = 쿠팡 정산, 특히 현재 정산 예정금액 산출. ② 받는 방식 = 기존 앱(정산 다운로드 `tools/settlement_download.py` 매일 실행)에 추가. ③ 판매분석은 **수집만** 2026-01-01부터(정산전용 계정 포함) — 결과 시트 대시보드·월별 표시는 D-105 그대로 4월부터. ④ 로켓그로스 광고비·밀크런은 2025-12분도 받는다(2026-01 지급 공제 근거). ⑤ 다운로드 작업은 이 앱 세션들에서 진행('셀독 관리대장 쿠팡 매출 매칭' 세션 범위에서 분리).
- 근거: 누락 조사 `output\_분석_261013\정산스크립트\쿠팡_정산자료_수집누락_조사_261107.md`(output (31) 11-05 수집본 전수 집계 + 코드 대조) — 정산전용 11계정 판매분석 없음(윙 줄 없는 판매 = 말일 기준 그 달 윙 정산의 33~73%) · 판매분석 일별 04-01부터(`sales_summary.FIRST_DAY`) · 쿠폰 수집은 판매수집 세션에만(`pipeline_sales.py:131`) · 광고 `due_months` 2026-01부터 · 매일 실행 `cmd_run` 에 증빙 원본 없음.
- 버린 대안: 수집·표시 모두 1월부터(대시보드 D-105 변경 — 소유자 선택 안 함) · 광고·밀크런 2026-01부터만(1월 지급 공제 근거 없음) · 별도 다운로드 프로그램.
- 영향 범위: `tools/settlement_download.py`·`settlement_*`·`settlement_ads`(due_months)·`sales_summary`/`pipeline_sales`(수집 시작일 분리)·`wing_coupons`. 실제 수집은 운용 PC 재배포 후. 화면 조회 주소 실측이 필요한 항목(세금계산서·매출내역 상세·부가세 상세·정산차감 상세·반품·추가정산 B·PostPurchase)은 소유자가 직접 로그인한 화면에서 조회만 확인(Claude 비밀번호 로그인 금지). 사람 조치: 로그인 막힌 7계정·셀러월렛(대표 본인 로그인).
- 상태: ACTIVE (부분 SUPERSEDED by D-166 — 광고·밀크런 시작 달 2025-12 → 2025-11)

### D-162 [SETTLE_EVIDENCE_ONCE_THEN_MONTHLY] 정산 증빙 원본 = 매일 받지 않음 · 운용 PC에서 한 번 전체 받기(이어받기) 후 매달 지난달 확정분 추가 (2026-11-07, R97)
- 결정(소유자 2026-11-07 '정책 저장해줘' — 통제 세션 권장안 승인): ① 증빙 원본(D-067 `evidence` — 정산 원본·정산 줄 없는 주 비용·판매분석 월별 원본·우대수수료 환급 엑셀·윙 지급 명세 PDF·로켓그로스 월렛 PDF·광고비/밀크런 PDF·광고센터 월별 PDF)은 매일 정산(`watch`/`cmd_run`)에 넣지 않는다. ② 운용 PC에서 2026-01부터 **한 번 전체 받기**(이어받기·여러 날/주말에 나눠 실행) ③ 이후 **매달 한 번** 지난달 확정분만 추가로 받는다. ④ 매일 바뀌는 값(월렛·환급·지급/예정 줄)은 지금처럼 매일 JSON 으로 받는다.
- 근거: D-067 실측 계정당 1~1.5시간 × 정산 50계정 = 50~75시간(하루 정산 창 18:00~다음 날 17:55·D-021 안에 불가) · 계정당 원격 요청·화면 조작 수십 회 추가 = 위탁 로그인 세션 차단 위험(D-067 이 같은 이유로 매일 방식을 버림·D-120 상한) · 증빙 전용 요청 기록이라 매일 돌리면 이미 받은 원본을 날마다 재요청 · 지급 끝난 달 자료는 바뀌지 않음 · 화면 조작(PDF 인쇄·광고센터 새 창·생성 지연) 실패가 잦음(라이브 시험 4회 수정). 사실: output (31)에 `output\정산\증빙\_요청기록.json` 없음 → 운용 PC 미실행 · 이 PC 6계정 중 완료는 니코에이블 1개(조사 = `output\_분석_261013\정산스크립트\쿠팡_정산자료_수집누락_조사_261107.md`).
- 버린 대안: 매일 정산에 증빙 단계 추가(위 시간·차단·중복) · 증빙 원본 안 받기(D-061 증빙 = 쿠팡 원본·100% 목표 D-161).
- 영향 범위: 운용 PC 실행 절차(`deploy/정산증빙_전체받기.bat`·`정산다운로드.exe evidence`) · 매달 추가 실행을 앱이 자동으로 할지(예약·기간 지정)는 구현 단계에서 정함(D-161 후속). 매일 정산 동작 불변.
- 상태: ACTIVE (부분 SUPERSEDED by D-164 — ① 중 '정산 줄 없는 주 비용'은 매일 정산의 받을 파일 계획으로)

### D-163 [FAST_SETTLEMENT_SOURCE] 빠른정산(셀러월렛) 자료 = 원금은 쿠팡 정산 자료에서 · 하나은행 수수료·실입금일은 대표에게 요청 · 추정 수수료 칸 없음 (2026-11-07, R97)
- 결정(소유자 2026-11-07 '정책 저장해줘'): ① 빠른정산으로 미리 받은 **원금**은 앱이 매일 받는 쿠팡 지급 내역에서 뽑는다 — 윙 = 지급 명세 차감 사유 '빠른정산 계좌인출액' · 로켓그로스 = `totalArFactoringDeductionAmount`(+ 월별 내역 `arFactoringOffsetYearMonthBreakdown`). ② 하나은행 수수료·실제 인출/입금일·셀러월렛 계좌 거래내역은 쿠팡 정산 자료에 없고 셀러월렛(sellerwallet.coupangpay.com)은 **사업자 대표 본인 로그인·본인인증**이라 앱·Claude 가 받지 않는다 → 필요하면 해당 대표에게 화면·엑셀을 요청. ③ 추정 하나은행 수수료 칸은 넣지 않는다(추정 금지 D-146 · D-077 '수수료 추정치를 금액으로 넣기' 버린 대안과 같음).
- 근거: output (31) 쿠팡지급내역에서 추출한 `D:\토탈셀러\쿠팡 정산 자료\빠른정산_상환내역_261107.xlsx` — 10-16 파일(`빠른정산_상환내역_261016.xlsx`)과 유라이프 2026-01·02·05 윙·로켓그로스 금액 원 단위 일치(같은 방식 확인) · 2026 원금 = 꿈꾸는아재 591,868,075 · 원더풀리 201,587,463 · 유라이프 99,657,263 · 글로벌셀러 82,662,262 · 스마트플라자 30,506,931 · 가디즌 21,255,254 · seankim137 6,787,738(꿈꾸는아재·가디즌·seankim137 은 10-16 파일에 없던 계정 — 빠진 이유 미확인·금액 확인 필요) · KB §1-14(셀러월렛 다운로드 방법 공개 자료 없음).
- 버린 대안: 셀러월렛 자동 수집(대표 본인 인증·다른 도메인 — 위탁 계정 로그인 정책 밖) · 수수료 추정치 표시.
- 영향 범위: 빠른정산 상환내역 파일(git 밖 분석 산출물) · 위탁정산서 'F. 빠른정산 내역'(D-077) 원천 그대로. 앱 코드 변경 없음. 7계정 대표에게 셀러월렛 내역 요청은 사람 조치.
- 상태: ACTIVE

### D-164 [RG_MISSING_COST_DAILY] 로켓그로스 빠진 비용 리포트 = 매일 정산 계획에 넣음(정산 줄 없는 주 물류비·조회에 없는 지급 줄) · 원인 확인용 정산현황 원문 하루 1번 (2026-11-08, R99)
- 결정(소유자 2026-11-08 — D-161 1단계 ④ 질문에 '원인 확인용 저장 + 매일 정산에 넣기' 선택): ① 정산 줄 없는 주의 물류비(미납 CFS 로만 보이는 주·D-065)를 매일 정산(`cmd_run` → `read_events`)의 받을 파일 계획(요청기록 jobs)에 넣는다 — 유형 `정산줄없음`·리포트 = 물류비 5종(미납 CFS 상세에 종류가 없어 전부·판매수수료 없음)·정산일 = 그 비용을 처음 공제한 줄의 정산일·조회 시작(2025-11-01) 전에 시작한 주는 만들지 않음. ② 지급 내역(저장분)엔 있는데 그날 정산현황 조회 일정엔 없는 로켓그로스 줄 중 비용 금액이 있는 것(0원 줄)을 그 주 일정으로 넣는다 — 요청 키 = 업체코드-시작-끝(업체코드가 하나로 정해지지 않으면 만들지 않음). ③ 같은 주·리포트는 jobs 키로 한 번만 요청(재요청은 기존 규칙). ④ 원인(조사 *2) 확인용으로 로켓그로스 정산현황 응답 원문(최근 70일과 겹치는 지난 조회 구간 + 예정 조회)을 계정마다 하루 1번 `output\정산\정산현황_원문\{계정}\{날짜}.json.gz` 에 남긴다. 증빙 전체 받기(`evidence`)의 같은 단계는 그대로(D-162).
- 근거: 실데이터 대조(output (31) 11-05 수집본 지급 내역 + 요청기록에 새 규칙 적용) — 조회에 없는 지급 줄 4주 = hk66597582 09-21~27 반출배송 5,500 · theirumlab 09-28~30 보관비 3,147·10-01~04 보관비 4,197 · luxsong8 09-14~20 반출비 63,690+반출배송 36,520 = **113,054원(조사 문서와 원 단위 일치)** · 비용 없는 quietlab 0원 줄은 제외 · 정산 줄 없는 주 9계정 37주(니코에이블 5/11~17 13,200 = D-065 실측 포함) → 첫 실행 요청 약 185+9건(이후 0). 오프라인 검증 P49(순수 규칙·계획·요청 키·원문 하루 1번).
- 버린 대안: 매달 증빙 실행에만 맡김(D-162 그대로 — 정산 예정금 입력이 한 달 늦음) · 원인 확인 전 수정 보류(0원 줄은 저장된 지급 내역에서 바로 찾을 수 있어 원인과 무관하게 받을 수 있음) · 정산 줄 없는 주에 판매수수료도 요청(판매 없는 주 — 요청만 늘어남).
- 영향 범위: `settlement_wing_api`(CFS_KINDS·missing_week_events·unlisted_row_events) · `settlement_jobs`(MISSING_KIND·reports_for) · `settlement_evidence_web`(CFS_KINDS 공용) · `tools/settlement_download.py`(read_events·_rg_extra_events·_read_forecast 반환). 받은 비용 리포트는 기존 비용 폴더·집계(`rg_cost_lines`)로 들어감. 운용 PC 재배포 후 적용. (미확인) 원문 파일 크기·쌓이는 양 — 원인 확인 뒤 저장을 끌지 결정.
- 상태: ACTIVE

### D-165 [SETTLE_SALES_COLLECT_SCOPE] 정산 실행의 판매분석·쿠폰 수집 = 정산 계정 전부(정산전용 포함)·2026-01-01부터 · ① 판매수집은 4/1 기준 그대로 (2026-11-08, R99)
- 결정(소유자 2026-11-08 — D-161 ③ 구현 범위 질문에 '정산 50계정 전부' 선택): ① 정산 실행(`cmd_run`)이 계정마다 판매분석 월·주 합계와 일별 소급을 `sales_summary.COLLECT_FROM`=2026-01-01부터 받는다(관리대장 계정의 1~3월 포함) · 상한·저장은 ①과 같음(계정당 하루 60일·오늘 ① 이 받은 날 포함·같은 파일) · 이미 받은 날은 다시 안 부름. ② 윙 할인쿠폰(D-160 `wing_coupons.record_day`)도 정산 실행에서 받는다(그날 완료본 있으면 건너뜀). ③ 앱 ① 판매수집은 지금처럼 `FIRST_DAY`=4/1 기준(수집 시간 불변) · 결과 시트 표시도 4/1부터(D-105·대시보드는 first=FIRST_DAY 로 거름).
- 근거: 조사 B-2(1~3월 월 합계 없는 8계정·정산전용 11계정 판매분석 없음) · `sales_dashboard.build·cumulative·sales_scale` 이 모두 FIRST_DAY 로 걸러 1~3월 기록이 표시에 안 섞임(코드 확인) · 오프라인 검증 P47(정산 실행 = 3/31부터 거꾸로 60일·1~3월 월 합계·쿠폰 · ① 은 1~3월 안 부름).
- 버린 대안: 정산전용 11계정만(관리대장 8계정 1~3월 월 합계 빈 채로) · ① 판매수집도 1월부터(① 수집 시간 계정당 최대 수 분 증가).
- 영향 범위: `sales_summary`(COLLECT_FROM) · `pipeline_sales`(_record_sales_periods·_record_sales_backfill 에 first 인자) · `tools/settlement_download.py`(collect_sales). 처음 약 6일은 정산 실행이 계정당 최대 수 분 길어짐(정산전용 계정 1/1~어제 약 311일 ÷ 60). 운용 PC 재배포 후 적용.
- 상태: ACTIVE (부분 SUPERSEDED by D-167 — 정산 실행 일별 소급 상한 계정당 하루 60일 → 한시 150일 · 1월까지 다 받으면 60일 자동 복귀)

### D-166 [SETTLE_ADS_FROM_2025_11] 광고비·밀크런 원천 수집 시작 = 2025-11 (D-161 의 2025-12 에서 한 달 앞당김) (2026-11-08, R100)
- 결정(소유자 2026-11-08 '응, 11월 광고도 넣고'): `settlement_ads.FROM` = 2025-11-01. 광고정산 json·매출성장광고·밀크런 모두 2025-11 달부터 받는다. 하루 계정당 2달(D-120)·이미 받은 달 건너뜀은 그대로.
- 근거: gyi0101 라이브 조회 — 광고센터 GraphQL(relay 경유)·밀크런 GET 이 2025-11·12 달 자료를 실제로 줌(조사 `쿠팡_정산자료_실측_261108.md`) · 2026 첫 정산 줄에 2025-11 판매분 몫이 있음(AMOUNTS_FROM 2025-11-01 과 같은 이유). (미확인) 11월 광고비가 어느 지급 줄에서 공제됐는지 — gyi0101 달별 광고 합과 연속 지급일 합 대조 실패.
- 버린 대안: 2025-12 유지(11월 광고 공제분 근거 빠짐).
- 영향 범위: `settlement_ads`(FROM) · 계정당 1달 추가 요청(첫 회차). 운용 PC 재배포 후 적용.
- 상태: ACTIVE

### D-167 [SETTLE_SALES_BACKFILL_150_TEMP] 정산 실행의 판매분석 소급 상한 = 한시 계정당 150일 → 1월까지 다 받으면 60일로 자동 복귀 (2026-11-08, R100)
- 결정(소유자 2026-11-08 AskUserQuestion '한시 150일'): 정산 실행(`collect_sales`)의 일별 소급 상한을 150일로 올린다. 대상 계정의 2026-01-01~어제가 모두 채워지면 그 계정은 D-097 의 60일 규칙으로 돌아간다(코드가 자동 판정 — 사람이 되돌릴 필요 없음). ① 판매수집의 소급은 60일 그대로.
- 근거: o32 실측 — 35계정 1/1~3/31 각 90일 없음 · 정산전용 16계정 1/1~ 기록 전무(약 311일) → 60일이면 약 6회차, 150일이면 약 3회차. 소급 조회 사이 쉼 1~2.5초(`_PERIOD_GAP_SEC`)라 150일 ≈ 계정당 약 7분 [추정].
- 버린 대안: 60일 유지(따라잡기 약 6일) · 상한 없이 한 번에(계정당 최대 약 15분·몰아치기 위험).
- 영향 범위: `sales_summary`(정산용 상한 상수)·`pipeline_sales._record_sales_backfill`(limit 인자)·`tools/settlement_download.py`(collect_sales). 1바퀴가 길어지는 문제는 designs/SETTLEMENT_MODULE.md §16-3 정기/소급 단계 분리(승인 필요)와 함께 본다.
- 상태: ACTIVE

### D-168 [RUN_RESULT_SUMMARY_LOG] 앱 로그·정산 로그 끝에 [실행 결과 종합] 블록 — 로그만 보고 정상 수행 여부 판단 (2026-11-08, R100)
- 결정(소유자 2026-11-08 '앱과 정산앱도 로그에 종합적인 실행 결과를 출력' · AskUserQuestion '넣기·파일 전부 나열'): 두 로그 끝에 같은 모양의 블록 — 판정(정상 완료/일부 실패 확인 필요/중단) · 전체 작업 계정(수·이름) · 비밀번호 오류로 수집 안 된 계정 · 사람 조치 필요 계정(2단계 인증·24시간 재입력 금지 등) · 오류 현황(단계별 건수·계정) · 이번 실행에서 받은 파일 전부(경로) · (정산) 남은 소급.
- 근거: 지금 정산 `RunLog.summary()` = 계정별 건수와 '[비정상] 단계 결과: N건'뿐(계정 이름·전체 수·파일·판정 없음) · 앱 로그는 '수집 성공 33/34'·'[순위요약]'이 흩어져 있고 '완료 — 종료'로 끝남(o32 로그 확인).
- 버린 대안: 파일 수만 표시(소유자가 파일 전부 나열 선택).
- 영향 범위: `settlement_runlog`(summary) · `tools/settlement_download.py`(회차 끝) · 앱 파이프라인 끝(`pipeline.py` — 공유 파일·통제 세션 편집). 비밀번호 값은 출력 금지(계정 이름·사유만).
- 상태: ACTIVE (부분 SUPERSEDED by D-172 — 판정 문구 표기)

### D-169 [FAST_SETTLEMENT_USAGE_CHECK] 빠른정산 이용 여부를 계정마다 하루 1번 조회해 검증 원자료에 저장 (2026-11-08, R100)
- 결정(소유자 2026-11-08 '응, 넣고'): WING `GET /tenants/seller-wallet-web/fast-settlement/available-services`(조회만) 결과를 검증 원자료(`collect_verify`)의 한 항목으로 저장한다 — 어느 계정이 빠른정산·팩토링을 쓰는지(셀러월렛 내역을 요청할 대표 목록 근거). 원금(상환액)은 D-163 그대로 지급 내역에서.
- 근거: gyi0101 실측 응답 `["FAST_SETTLEMENT","FACTORING"]` · o32 2026 상환액 있는 계정 7(tellace83·oopean·gyi0101·gbseller808·luxsong8·guarisen2024·seankim137) · RG 월별 내역 합 = 공제액(322줄 어긋남 0) · gyi0101 2026-01 매입 세금계산서 10줄 공급자 = 쿠팡·쿠팡페이·CFS·로지스틱스(하나은행·빠른정산 줄 없음 → 수수료는 세금계산서로 확인 불가 · 금융 수수료 면세 [추정]).
- 버린 대안: 세금계산서로 수수료 간접 확인(해당 줄 없음) · 셀러월렛 자동 조회(대표 PIN·D-163).
- 영향 범위: `settlement_verify_collect`(항목 1개·실패 = 지난 값 유지) · 하루 계정당 조회 1회. 운용 PC 재배포 후 적용.
- 상태: ACTIVE

### D-170 [SETTLE_REGULAR_THEN_BACKFILL] 정산 실행 = 한 프로그램 안 '정기(1바퀴)→소급(2바퀴~)' 두 단계 · 회차별 계정 예산 (2026-11-08, R101)
- 결정(소유자 2026-11-08 AskUserQuestion '제안대로'): 정산 실행(`watch`→`cmd_run`)을 두 단계로 나눈다. **1바퀴 = 정기**(전 계정 — 지급 내역·정산 예정·새 정산 파일 요청/받기·검증 원자료·광고 지난 달 등 그날 정산에 필요한 것만). **2바퀴부터 = 소급**(전 계정 다시 — 판매분석 1월~·광고 밀린 달·월자료 밀린 달)을 회차(18:00~17:55) 단위 **계정별 예산** 안에서: 판매분석 150일(D-167)·월자료 종류별 3달·부가세 상세 요청 4건. 별도 앱으로 나누지 않는다. 종료·이어받기(소급 다 받으면 '완료'·아니면 17:55·다음 회차 이어받음)는 지금과 같다.
- 근거: designs/SETTLEMENT_MODULE.md §16-3 — 계정마다 Chrome 프로필·로그인 세션·`_요청기록.json`·잠금·상태 카드가 하나(런타임 병렬 금지) · 지금 `cmd_run` 은 계정마다 [정산 파일→검증→광고→판매분석 소급]을 이어서 해 소급 150일을 넣으면 1바퀴 약 +6시간 [추정·코드 근거] → 뒤 계정 그날 파일 지연.
- 버린 대안: 지금 방식(계정마다 소급 끼우기) · 소급 전용 별도 앱(같은 계정 동시 접속 위험).
- 영향 범위: `tools/settlement_download.py`(cmd_run 단계 분리 — 새 단계는 별도 모듈) · 상태 카드 '남은 소급' 표시 · D-167 의 '1바퀴 길어짐' 문제 해소.
- 상태: ACTIVE

### D-171 [SETTLE_DOCS_SCOPE] 정산 자료 2단계 받을 범위 확정 — 매출내역 상세 제외 · RG 반품내역 하루 1번 · 보류 4종도 모두 받기 · 주문별 JSON 은 쪽 크기 10 (2026-11-08, R101)
- 결정(소유자 2026-11-08 AskUserQuestion): ① 매출내역 상세(`MSF_PURCHASE_REVENUE_DETAIL`) **제외**. ② RG 반품내역(N7) = **하루 1번** 받아 최신본으로 덮어쓰기. ③ 보류 제안했던 4종 = **모두 받는다**('모두 받아야 돼, 응답 2회 없으면 원인 파악') — 매출 주문별 JSON(`payment-report/order-detail`)·RG 상품별 사이즈 리포트(`PRODUCT_SIZE_COMPARISON`)·프로모션 추가 수수료(`payment-report/promotion-fee`)·리뷰 이벤트 캠페인 목록(`manage-review-campaign/campaigns`). ④ 주문별 JSON 은 **size 10 고정** + `cursorToken` 이어받기 + 쪽 사이 쉼 · 고객 이름 칸 저장 제외.
- 근거: ① gyi0101 2026-01 매출내역 상세 = 이미 받는 윙 최종액 주문상세와 449줄·주문 151·금액 4종 동일(구매자명 칸만 차이 · `쿠팡_정산파일_내용검증_261108.md`). ③④ 2026-11-08 2차 실측(`쿠팡_정산자료_실측_261108.md` 5절): 응답 없음 원인 = 쪽 크기 — size 10 = 0.5~0.8초 200 · 11·20·100 = 응답 없음 · 50 = 400. size 10 으로 2026-01 전체 16쪽 151줄 → 주문 151·수수료 466,121·정산금액 3,480,779·판매액 3,952,600(상품 3,924,600+배송비 28,000) 모두 기존 파일과 일치.
- 버린 대안: 4종 보류(소유자 거부) · RG 반품 달 1번(소유자 하루 1번 선택).
- 영향 범위: designs/SETTLEMENT_MODULE.md §16-2(N10~N13 추가)·새 모듈 `settlement_docs.py`/`collect_docs` · 하루 계정당 조회 증가(주문별 JSON 은 달마다 수십 쪽).
- 상태: ACTIVE

### D-172 [RUN_VERDICT_CAUSE_ARROW] [실행 결과 종합] 판정 = '원인 --> 결과' 전부 표기 — "일부 실패 --> 확인 필요"·"진전 없음 --> 중단" (2026-11-08, R104)
- 결정(소유자 2026-11-08 '확인필요와 중단만 표시 하면 안됨 … 화살표 포함 전부 기술'): 판정 줄·한 줄 요약(`==>`)·상태 카드 '결과 종합:'에 결과만 쓰지 않고 **원인 --> 결과**를 화살표까지 그대로 쓴다 — `일부 실패 --> 확인 필요`(일부 실패해서 확인이 필요함) · `진전 없음 --> 중단`(진전이 없어서 중단됨). '(전체)' 연속 실패 중단이 안 풀린 경우 = `연속 실패 --> 중단`(같은 규칙 적용 — 원인이 진전 없음이 아니므로 Claude 가 원인 이름을 붙임). 정상은 `정상 완료` 그대로.
- 근거: R103 구현값 = '일부 실패 — 확인 필요'·'중단'(원인 없음 — 진전 없음 종료와 연속 실패 중단이 같은 글자라 로그로 구분 안 됨, `settlement_runlog.verdict`). watch 의 중단 종료는 `plan_after_pass` 가 'giveup'(N바퀴 진전 없음)일 때만 생김(연속 실패는 'later' = 다음 바퀴) → stopped = 진전 없음.
- 버린 대안: 결과만 표시(소유자 거부) · 연속 실패 중단도 '진전 없음 --> 중단'으로 통일(원인이 다름 — 로그를 보고 잘못 판단).
- 영향 범위: `settlement_runlog.verdict`(정산 쪽) · 앱 쪽 [실행 결과 종합](`pipeline.py` 끝 — 통제 세션 구현 때 같은 표기). 핀 P54.
- 상태: ACTIVE

### D-173 [APP_RUN_SUMMARY_RANK_RETRY] 앱 [실행 결과 종합] 구현 · ③ 순위 빈 칸 = 모든 처리 끝난 뒤 1회 재시도 → 남으면 '순위 빈 칸 --> 확인 필요' (2026-11-08, R104)
- 결정(소유자 2026-11-08 AskUserQuestion 답 '차단 등으로 일부 상품 순위를 못 잰 경우에는 모든 실행이 완료된 후 미완료된 건을 다시(1회) 시도하고 오류이면 "순위 빈 칸--> 확인 필요" 표시' · zip = '앱 쪽 종합까지 끝낸 뒤'): ③ 순위 뒤 재고 역기록까지 끝났는데 빈 칸이 남았으면 ③을 **1회만** 더 돌린다(채운 칸은 ③이 건너뜀 · 중지 요청이면 안 함). 그래도 남으면 판정 `순위 빈 칸 --> 확인 필요`. 앱 [실행 결과 종합](D-168 앱 쪽) 판정 = D-172 '원인 --> 결과' — `정상 완료` / `일부 실패 --> 확인 필요` / `순위 빈 칸 --> 확인 필요`(둘 다면 `일부 실패·순위 빈 칸 --> 확인 필요`) / `사람 중지 --> 중단` / `오류 발생 --> 중단`.
- 근거: ③은 이미 바퀴 반복으로 빈 칸만 다시 돌지만(D-053) 진전 없는 바퀴·IP 불량 연속이면 빈 칸을 남기고 끝남(`_semi_next_pass`) · 다시 부르면 `_rank_todo` 가 빈 칸만 고름(코드 확인 11-08). 앱 끝 로그는 '[무인 자동 실행] 완료 — 종료'·'[순위요약]'·'수집 성공 N/M'이 흩어져 있었음(D-168 근거).
- 버린 대안: 순위 빈 칸을 정상 완료로 두고 숫자만(소유자 거부) · 재시도 여러 번(소유자 1회) · 앱 끝 블록을 UI(app_qt)에 둠(전체실행·무인·복구가 갈라짐 → 단계 조립 단일 구현 `pipeline_stages` 에 둠).
- 영향 범위: 새 모듈 `run_result.py`(RunSummary·LAST_SALES) · `pipeline_stages.run_stages`(블록·재시도) · `pipeline.py`(① 끝 LAST_SALES 몇 줄) · 오류 줄 규칙(Claude 구현값 — '❌' 줄 · ②·재고 역기록은 '실패' 줄도 · ③ 재시도 땐 첫 회 줄 버림 · ③ 빈 칸 ❌ 는 '순위 빈 칸' 원인으로 묶음) · 핀 P11 · simulate 3·26. 운용 PC = R104 zip 설치 뒤.
- 상태: ACTIVE

### D-174 [DECISIONS_MARKS_R106] 빠진 부분 대체 표기 2건 — D-141←D-156 · D-152←D-155 (2026-11-08, R106)
- 결정(소유자 2026-11-08 AskUserQuestion '2건만 반영'): D-141 상태 줄 = `ACTIVE (부분 SUPERSEDED by D-156 — 미매칭 줄 '기존값 유지' → '재고원장 없음' 표기)` · D-152 상태 줄 = `ACTIVE (부분 SUPERSEDED by D-155 — 서달원 상품군 실지급 계산(계정 합계 비율 배분 → 직접 합산)·최종 산출물 파일)`. 두 항목 본문은 고치지 않는다(추가 전용).
- 근거: `py -3.12 ~/.claude/hooks/decisions-index.py . --check` 경고 1건(11-08 실행 · 대상 = D-141 상태 줄). D-156 영향 범위가 D-141 의 '미매칭 기존값 유지' 부분을 바꾼다고 명시. D-155 결정 ① = 서달원 상품군 실지급을 '계정 합계 비율 배분 → 직접 합산'으로 바꿈 · 산출물 `…_최종_화재보상포함.xlsx` → `…_D146_상품군직접합산.xlsx` · D-152 영향 범위의 미결('표에 추정분이 있어 D-146·D-148 판단 필요')을 D-155 가 해소.
- 버린 대안: 감사 `docs/decisions/audit-2026-11-04.md` C절 13건까지 함께 반영(범위 확인이 필요해 이번엔 STATE 미해결로만 재등록) · 표기 안 함(`--check` 경고가 남음).
- 영향 범위: `docs/DECISIONS.md` 상태 줄 2개 · 색인 `docs/DECISIONS_INDEX.md` 재생성. 코드 동작 변경 없음.
- 상태: ACTIVE

### D-175 [CURRENT_RULES_14] `docs/CURRENT_RULES.md` 도입 — 14묶음 주제별 현행 규칙 · 세션 시작은 이 파일 · 문서 7곳 낡은 규칙 구절을 링크로 (2026-11-08, R106)
- 결정(소유자 2026-11-08 `D:\claude-global\docs\plans\NEXT_SESSION_PLAN.md` 세션 2 지시 · 링크화 AskUserQuestion '7곳 모두 바꿈'): ① `docs/CURRENT_RULES.md` = 14묶음(비밀번호·로그인 · ③ 노출순위·프록시 · 매칭·노출상품명 · 관리대장 입력·결과 계정목록 · 회사보유재고·그로스 재고 · 체험단 · 통합판매현황 구조·범위 · 통합판매현황 ① 요약 · 정산 기동·종료 · 정산 수집 범위 · 정산 증빙 원본 · 위탁정산서 구조·공제 · 추정 금지 · 실행 결과 종합)마다 현행 규칙 5줄 + 근거 D번호. 정책이 바뀌는 커밋에서 그 주제 줄을 함께 고친다. ② 세션 시작 = STATE.md + CURRENT_RULES(프로젝트 `CLAUDE.md` ⑤ 고침) · 색인은 검색용. ③ 낡은 규칙 구절 7곳(`docs/OPERATIONS_POLICY.md:9`·`:13` · `docs/ARCHITECTURE.md:63` · `designs/DESIGN.md:161`·`:523`·`:423` · `designs/DOMAIN_D4_PRODUCT_MANAGE.md:15` · `designs/IO_DEFINITION.md:223`)을 현행 구절 + 'CURRENT_RULES §N · D번호'로 바꾼다. 정책 문장은 지우지 않는다(DESIGN.md:161 은 문단 유지·'[폐기 …]' 머리표만).
- 근거: 전역 `D:\claude-global` D-003(DECISIONS 30KB 넘는 저장소는 CURRENT_RULES). 이 저장소 DECISIONS 374,873B·색인 32,171B(11-08) · 세션 시작 첫 응답 입력 89,111(10-10)~105,140(11-05) 토큰(D-151 실측). 줄마다 원문 대조 = `docs/decisions/current-rules-2026-11-08.md`(하위 작업이 118블록 원문 읽고 초안 · 통합 세션이 6줄 근거 보정). 7곳 = 2026-11-08 분석 보고(`D:\claude-global\docs\plans\COUPANG_POLICY_CLEANUP.md`) — 유사도 매칭 5곳(`_best_inventory_match` 는 `src/` 에 없음·.pyc 만) · '순위조회 = 자동+반자동'(`docs/CONSTRAINTS.md:9` offscreen 자동 순위검색은 폐기) · DESIGN.md '그 키워드부터 다시'(보고 줄 422 → 실제 423 · D-053 '뒤로 미루고 다음 키워드'). `decisions-index.py . --check` 경고 0.
- 버린 대안: 색인만 유지(제목만으로 현행을 알 수 없는 항목 약 26%) · 7곳 문단 통째 삭제(축소는 이동만 허용 규칙) · designs/ 는 그대로 둠(소유자 7곳 모두 선택).
- 영향 범위: 문서만 — `docs/CURRENT_RULES.md`(신규 약 13KB) · `docs/decisions/current-rules-2026-11-08.md`(대조표) · `CLAUDE.md` ⑤ · 위 7곳. 코드 동작 변경 없음. 메모리 5건에 '현행 = D-xxx' 표시(57f6020 미러).
- 상태: ACTIVE
### D-176 [DECISIONS_MARKS_R107] 빠진 부분 대체 표기 2건 — D-105←D-161·D-165 · D-165←D-167 (2026-11-08, R107)
- 결정(소유자 2026-11-08 'D-165·D-105 표기 누락 2건도 반영해줘'): D-105 상태 줄 = `ACTIVE (부분 SUPERSEDED by D-161 · D-165 — '1~3월 기간 기록은 읽지·조회하지 않음' 중 조회: 정산 실행은 2026-01-01부터 조회·수집 · 표시·① 판매수집은 4월부터 그대로)` · D-165 상태 줄 = `ACTIVE (부분 SUPERSEDED by D-167 — 정산 실행 일별 소급 상한 계정당 하루 60일 → 한시 150일 · 1월까지 다 받으면 60일 자동 복귀)`. 두 항목 본문은 고치지 않는다(추가 전용).
- 근거: R106 CURRENT_RULES 대조 발견(`docs/decisions/current-rules-2026-11-08.md` 발견 모음 3·4 · `--check` 는 본문에 대체 동사가 없어 못 잡음). 원문 — D-105 결정 ① '1~3월 기간 기록은 파일에 남겨 두되 읽지·조회하지 않음(표시 안 함)' · D-161 결정 ③ '판매분석은 수집만 2026-01-01부터 … 표시는 D-105 그대로 4월부터' · D-165 결정 ① '`sales_summary.COLLECT_FROM`=2026-01-01부터 … 상한·저장은 ①과 같음(계정당 하루 60일…)' · D-167 결정 '정산 실행(`collect_sales`)의 일별 소급 상한을 150일로 … 1월까지 다 받으면 D-097 의 60일 규칙으로'.
- 버린 대안: 표기 안 함(색인에서 D-105·D-165 가 '유효'로만 보여 현행을 잘못 읽음).
- 영향 범위: `docs/DECISIONS.md` 상태 줄 2개 · 색인 재생성. `docs/CURRENT_RULES.md` §7(소급 상한 = D-167)·§8(표시 시작 = D-165)은 이미 현행 기준이라 그대로. 코드 동작 변경 없음.
- 상태: ACTIVE
### D-177 [DECISIONS_MARKS_R108] 감사 C절 13건 원문 대조 — 부분 대체 표기 12건 · D-135 미결 해소 메모 1건 (2026-11-08, R108)
- 결정(소유자 2026-11-08 '이어서 감사 C절 13건도 원문 대조해서 반영해줘'): `docs/decisions/audit-2026-11-04.md` C절 13건을 두 항목 원문(결정·영향 범위)과 지금 코드로 대조해 상태 줄만 고친다(본문은 고치지 않음·추가 전용). 부분 표기 12건 = D-009←D-011 · D-015←D-051 · D-030←D-053/D-057/D-090(기존 D-053 표기 넓힘) · D-039←D-074 · D-056←D-094 · D-059←D-126 · D-077←D-126 · D-078←D-081 · D-088←D-126 · D-092←D-141 · D-108←D-109/D-121 · D-111←D-112. D-135 = 'SUPERSEDED' 아님 → `ACTIVE (본문 미결 해소 — D-139: …)` 메모(색인에서 유효·참고 D-139). 각 범위 문구 = 해당 항목 상태 줄.
- 근거(원문 대조): D-011 영향 범위 'D-009 의 ③ 세부를 보완(ACTIVE 유지)'이라 썼으나 버린 대안 (a) '글자 규칙 결과를 규칙 후보로 AI 에 표시(D-009 초안)' = D-009 ③ '글자 규칙 결과는 참고 후보'가 바뀜 · D-051 'D-015 출처 순서 = … → 윙 상품수정 화면 → 그래도 없으면 ❌' · D-057 (2) 막힌 (주소, IP) 건너뜀 ↔ D-030 '풀 한 바퀴 뒤엔 차단 이력 IP 도 재사용' · D-090 (3) 'IP 불량 15번 이어지면 ③ 마침' ↔ D-030 '회전 횟수 제한 없음·끝=…' · D-053 (1) '진전 없으면 남은 칸 ❌ 로 마침' · D-039 결정 '기존 규칙(… 윙 최종액은 주정산 없는 주만)은 그대로' ↔ D-074 조건 좁힘 · D-056 영향 범위 '과거 날짜 소급 없음' ↔ D-094 ① 2026-04-01부터 소급 · D-078 '정산서 정산 예정액은 정확도가 확인될 때까지 바꾸지 않는다' ↔ D-081 (1) 로켓그로스 = 정산현황 예정 줄 · D-092 '재고현황 시트는 현재고 칸만' ↔ D-141 '총입고수량' 양식(`company_stock.py:79` 두 칸만 찾음·셀독/당근/자사 참조 0) · D-108 '종료일은 상태·기간 배경색에만' ↔ D-109 열 삭제·D-121 버린 대안 '마케팅 기간 연주황 … 물리 삭제' · D-111 ④ '17:40 이후·차단 2연속' ↔ D-112 ①②③ · D-135 미결 ↔ D-139 '(D-135 미결 해소)'. 정산서 3건은 지금 정산서 스크립트(git 밖 `output\_분석_261013\정산스크립트\statement_managed.py` 860줄)로 확인: 1쪽 흐름 A~G(:657·:668) · 빠른정산 = G 표 두 줄(:717~:719)·비고(:665)·'F. 빠른정산 내역' 0건 · 쿠팡 별도 보상 = '참고. 쿠팡 계정 전체' 줄(:750)·'정산·보상' 0건 · 체험단 표시만(:739)·우리 사업자 통보 제외(:846) 그대로.
- 표기 안 한 것: D-088←D-116 — 관리 상품만은 정산서 대상 범위를 바꿨지만 D-088 규칙(예정 포함·체험단 표시만·우리 사업자 제외·대응표 우선)은 새 정산서에 그대로라 뒤바뀐 규칙이 없음 · D-088 (1) 예정액 차이 사유 6가지 문구가 지금 정산서에 남았는지는 확인 못 함(`statement_managed.py` 에 'FORECAST_NOTE' 0건 — 어느 결정이 뺐는지 원문 없음 → 표기하지 않음·STATE 미해결).
- 버린 대안: 감사 표대로 D-039·D-135 생략(D-039 는 결정 문장 안에 바뀐 규칙이 그대로 있어 단독으로 읽으면 틀림 · D-135 는 '미결'이 아직 열린 것으로 읽힘) · D-135 를 'SUPERSEDED' 로 표기(대체 아님).
- 영향 범위: `docs/DECISIONS.md` 상태 줄 13개 · 색인 재생성 · `docs/decisions/audit-2026-11-04.md` C절 아래 반영 메모 1줄. `docs/CURRENT_RULES.md` 는 이미 현행 번호 기준이라 그대로. 코드 동작 변경 없음.
- 상태: ACTIVE
### D-178 [DECISIONS_MARKS_R109] 감사 D절 5건 원문 대조 — 범위가 좁아진 부분 표기 5건 (2026-11-08, R109)
- 결정(소유자 2026-11-08 '이어서 감사 D절 5건도 반영해줘'): `docs/decisions/audit-2026-11-04.md` D절('표기 생략 가능') 5건을 두 항목 원문과 지금 코드로 대조해 상태 줄만 고친다(본문은 고치지 않음·추가 전용). 표기 = D-012←D-022/D-023 · D-050←D-135 · D-052←D-103(기존 D-075 표기 뒤에 이어 붙임) · D-053←D-090 · D-117←D-126(기존 D-119 표기 뒤에 이어 붙임). 각 범위 문구 = 해당 항목 상태 줄. 핵심 결정은 다섯 건 모두 유효(범위·곁가지 문장만 바뀜)이라 '부분' 표기만.
- 근거(원문 대조): D-012 결정 끝 '단일 값 API(`parse_password_rows`·`parse_password_file`)는 마지막 줄 → 첫 후보로 변경' ↔ D-022 영향 범위 'B1(ui/app.py·parse_password_file) … 완료' · D-023 '나머지 B4(… `parse_password_rows` …)는 삭제' — 지금 `src/`·`tools/`·`ui/` 에 두 함수 0건(git 밖 사본 `login_source_260904\`·`src - 복사본\` 에만 남음) · D-050 '현재 수(판매중지 제외)' ↔ D-135 '제목 상품 N개 = 판매중지·상품 없는 계정 줄 제외'(`gsheet_index._title_request` 설명 줄 같음) · D-052 (3) '정산 계정 파일에서 # 줄은 주석' ↔ D-103 (1) 기본 출처 registry·file 이면 옛 파일(`tools/settlement_download.py:136` 기본 'registry'·`settlement_accounts.py:38` '#' 처리 남음) · D-053 (1) '차단도 연결 장애도 없는데 한 바퀴 진전이 없으면 남은 칸 ❌ 로 마침' ↔ D-090 (2) 'IP 불량이 있었던 바퀴는 장애 있음 → 그 규칙에 걸리지 않고 빈 칸 0 까지 반복'·(3) '성공 없이 IP 불량 15번 → ③ 마침' · D-117 (1) '정산서에 금액 + … / 없으면 없음' ↔ D-126 ⑤ '쿠팡 정산 밖 별도 입금(우대수수료 환급·추가지급 — 있을 때만)' — 지금 정산서 `statement_managed.py:729` `add["상태"] == "있음"` 일 때만 1쪽에 씀(`additional_pay.py` 는 '없음' 상태를 그대로 돌려줌).
- 버린 대안: 감사 표대로 5건 모두 표기 생략(각 항목을 혼자 읽으면 지금 없는 함수·바뀐 세는 범위·바뀐 끝 조건을 현행으로 읽음 — 표기 비용은 상태 줄 1줄).
- 영향 범위: `docs/DECISIONS.md` 상태 줄 5개 · 색인 재생성 · `docs/decisions/audit-2026-11-04.md` D절 아래 반영 메모 1줄. `docs/CURRENT_RULES.md` 는 이미 현행 번호 기준이라 그대로. 코드 동작 변경 없음.
- 상태: ACTIVE
### D-179 [AUDIT_E_OWNER_ANSWERS] 감사 E절 '추적이 끊긴 미결' 8건 소유자 답 — 판매 현황 탭 안 만듦 · 전환자 2단계 매일 18시 뒤 · 10/18 정산서 안 보냄 · HANDOFF.md 삭제 · 05-01·07-17 늘 비영업일 · AI 매칭 예외 유지 · PC 엑셀 계정ID 정리 안 함 · 관리 시작 달은 차이 표 뒤 (2026-11-08, R111)
- 결정(소유자 2026-11-08 'STATE 미해결 … 감사 E절 8건 … 해결해줘' → 질문 8개 답):
  ① D-064 남은 단계 4 앱 '판매 현황' 탭 = **만들지 않음**(결과 구글시트 첫 화면 통합판매현황으로 충분). 단계 3 비대장 계정 판매 수집은 정산 실행이 이미 함(D-165).
  ② D-111 2단계(셀독 전환자 103계정 정산 자료 받기) 빈도 = **매일 18시 뒤**. 구현은 아직 없음(STATE 다음 작업).
  ③ D-118 = 10/18 기준 위탁정산서는 위탁자에게 **안 보냄** → 17계정 정정 통보 필요 없음(종결).
  ④ D-001 = 루트 `HANDOFF.md`(2026-09-14 이후 안 고침·'새 세션 읽기 순서' 안내가 남아 있던 옛 인계 문서) **삭제**(git 기록에 남음). 같이 고친 참조 = `docs/DOMAIN_DESIGN.md:72` · 메모리 2건(`commit-with-design-and-memory.md`·`recommend-new-session-when-degraded.md`, repo `docs/memory/` 사본 포함). 통제 세션 전용 파일의 참조(`CLAUDE.md:87`·`designs/DOMAIN_D2_SOURCING.md:168` 'HANDOFF §4-1' — 그 절은 원래 없었음)는 STATE 미해결.
  ⑤ D-004 = 쿠팡 비영업일 2026-05-01(근로자의날)·07-17(제헌절)을 **해마다 늘** 공휴일 집합에 더한다(특일정보 API·캐시 결과와 무관) — `holiday_kr.COUPANG_OFF_DAYS` · `holidays()` 반환에 합침(캐시 파일에는 API 결과만 저장).
  ⑥ D-009·D-071 = 전역 '매칭 기본 = AI 매칭' 규칙의 **예외로 지금처럼** — 앱 자동 매칭은 AI 장애 날만 글자 규칙 임시 매칭(고정 안 함)·계정아이디 바뀜 판단은 규칙 판단 유지. (D-072 회사보유재고는 D-157 로 이미 AI 판정.)
  ⑦ D-093 = 사람이 PC 엑셀을 고른 실행은 계정ID 정리도 **안 함**(`pipeline.py:332~334` 먼저 return — 지금 동작이 의도 범위).
  ⑧ D-140 관리 시작 달 = 결정 보류 — Claude 가 계정별 '자동 판정 달(첫 판매·첫 물류비) vs 계약 시작일 달' 차이 표를 먼저 만들어 보여 준 뒤 소유자가 정함(STATE 다음 작업).
- 근거: 감사 `docs/decisions/audit-2026-11-04.md` E절 '추적이 끊긴 미결' · 조사표 `docs/decisions/remaining-survey-2026-11-08.md` B절(원문 인용·코드 줄) · 소유자 답(질문 화면 2회·8문항). ⑤ 재현: `tools/verify_settlement_offline.py` P1·`tools/verify_settlement_runtime_offline.py` P22 기대값에 05-01·07-17 추가 → 옛 코드 AssertionError → 수정 → 두 검증 통과.
- 버린 대안: ① 이 앱이나 HQ 에 탭 만들기 · ② 주 1회·보류 · ④ 동결 자료로 옮기기·그대로 두기 · ⑤ 운용 PC 캐시 먼저 확인·API 그대로 · ⑥ 상품 매칭만 AI 강제·둘 다 AI · ⑦ PC 엑셀이어도 정리 · ⑧ 지금처럼 자동 확정·계약 시작일 달로 바로 변경(소유자 미선택).
- 영향 범위: `src/coupang_analytics/holiday_kr.py`(COUPANG_OFF_DAYS·holidays) · 시험 2개 · `HANDOFF.md` 삭제 · `docs/DOMAIN_DESIGN.md` · 메모리 2건 · 상태 줄 9개(D-001·004·009·064·071·093·111·118·140) · `docs/CURRENT_RULES.md` §3·§4·그 밖 주제. 운용 PC 재배포 후 지급일 대조에 적용(배포 zip = 통제 세션).
### D-180 [GATE_SPEED] 회귀 게이트 동시 실행(기본 3개) · 같은 내용 통과 기록이 있으면 훅이 다시 안 돌림 · 쿠폰 검사 실 세션 DB 수정 버그 (2026-11-08, R112)
- 결정(소유자 2026-11-08 '1·2·4 적용'): ① `tools/run_checks.py` 가 검사를 동시에 실행(기본 3개, `-j 1` = 예전처럼 하나씩). 가장 오래 걸리는 시뮬레이션(목록 맨 앞)부터 시작하고, 판정(하나라도 실패면 exit 1·실패 출력 마지막 20줄)은 그대로. ② 검사가 통과하면 그때 작업 폴더 내용의 키(임시 인덱스로 만든 git 트리 해시·`docs/memory`·`.claude` 제외)를 `git rev-parse --git-path checks-pass.json` 에 기록(`tools/check_stamp.py`). pre-commit = `--quick --skip-if-passed`(지금 작업 폴더 키가 빠른/전체 통과 기록과 같으면 건너뜀), pre-push = `--skip-if-passed=push`(올라갈 커밋마다 그 내용 키가 전체 통과 기록과 같으면 건너뜀). 내용이 한 글자라도 다르면 그대로 검사 — `--no-verify` 와 달리 검사하지 않은 내용은 통과시키지 않음. 검사 도중 내용이 바뀌면 기록 안 함. 옵션 없이 직접 돌리는 `run_checks.py`(/session-close 3단계)는 늘 실제 검사. ③ 게이트 자체 검증 `tools/verify_run_checks_offline.py` 를 CHECKS 에 추가(빠른 검사 포함). ④ `verify_coupon_snapshot_offline.py` S7 이 실제 `data/session_state.db` 를 고치던 것 → 다른 검사처럼 임시 DB 로 바꾸고, 실 DB 를 건드리면 실패하는 단언 추가. ⑤ `check_stamp` 와 자체 검증의 git 호출은 훅이 넘기는 저장소 지정 변수(`git rev-parse --local-env-vars`: GIT_DIR·GIT_INDEX_FILE 등)를 빼고 실행(자체 검증 S7).
- 근거(실측 2026-11-08): 하나씩 = 16종 합계 약 209초(시뮬레이션 107초) · /session-close 1회에 같은 검사가 3번(3단계 전체 → pre-commit --quick 179초 → pre-push 전체). 동시 3개 = 전체 16종 88.7초·17종 91.5초, 같은 내용 재실행 = 건너뜀 1초. 동시 실행 실패·결과 차이 0(8개·3개 각 1회 이상). 시뮬레이션 프로파일 = 실제 엑셀 저장 512회 59초·열기 131회 69초(실제 코드 경로라 이번 범위 밖). 쿠폰 버그 = 빈 작업 폴더에서 검사 1회 → `data/session_state.db` 생김(수정 전 재현) → 수정 후 안 생김 · 임시 DB 전환을 빼면 새 단언이 실패. ⑤ = 첫 커밋 시도(pre-commit 안)에서 자체 검증의 임시 저장소 git 명령이 훅의 GIT_INDEX_FILE·GIT_DIR 을 물려받아 작업 폴더 인덱스를 덮어쓰고 공유 설정에 core.bare=true 를 씀(커밋은 실패·생기지 않음, 즉시 core.bare=false·인덱스 reset 으로 복구, 잘못 섞인 커밋·ref 0) → 미끼 저장소로 재현(인덱스 바뀜) → 수정 후 안 바뀜 · 수정을 빼면 S7 실패.
- 버린 대안: 빠른 검사 목록을 CLAUDE.md 설명(시뮬+핀3+구글시트+정밀렌더)대로 되돌리기·시뮬레이션을 푸시 때만(소유자 선택 안 함 — 지금 목록 그대로 유지) · 커밋 훅 검사 생략(회귀 유입) · 동시 8개(경합으로 시뮬레이션 142초까지 늘어 3개보다 느림).
- 영향 범위: `tools/run_checks.py`(run_all·_already_passed·main(argv)) · 신규 `tools/check_stamp.py`·`tools/verify_run_checks_offline.py` · `tools/install_hooks.py`(훅 본문 — 새 PC/작업 폴더는 `python tools/install_hooks.py` 다시 실행해야 반영) · `tools/verify_coupon_snapshot_offline.py` · `CLAUDE.md` 게이트 줄. 검사 내용·범위 변경 없음.
- 상태: ACTIVE

### D-181 [GSHEET_QUOTA] 실행 시작 구글 읽기 = 여러 시트 묶어 읽기 · 429 는 합 100초 기다림 — 직원 키워드 10-11 부터 미반영 해소 (2026-11-09, R113)
- 결정: ① `GSheetClient.read_values_batch`(values.batchGet · 20시트당 요청 1번)를 새로 두고, 결과 시트 백업·마스터 복원(`_download_gsheet_via_sa`)과 직원 키워드 읽기(`read_staff_keywords`)가 시트마다 읽지 않고 묶어 읽는다. ② 공통 재시도 `_exec` 에서 429(분당 한도)만 10·20·30·40초(합 100초) 기다린다 — 다른 일시 오류(시간 초과·5xx)는 1·2·4·8초 그대로.
- 근거(실측): 앱 로그 10-11~11-08 회차 거의 매일 '직원 키워드 읽기 실패: 구글 API 쿼터 초과(429) (AI 선정으로 진행)' — 성공은 10-21 1번(`output (33).zip` 로그 전수 grep). 이 PC·같은 서비스계정·같은 결과 시트로 실행 시작 순서 재현(읽기만, 11-09): 백업 37회 + 직원 키워드 28회째(합 65회·49초) 429 → 재시도 1·2·4·8초(합 15초)로는 분당 한도(서비스계정 읽기 60회/분)가 안 풀려 4번 다 실패. 고친 뒤 같은 재현 = 6회·7.9초·429 0 · 직원 키워드 상품 114·키워드 471 = 옛 방식 단독 결과와 완전 같음 · 백업 값(표시값·저장값) 5개 시트 시트별 읽기와 같음. 시험 `verify_gsheet_offline` [8b] 는 옛 코드에서 실패·새 코드에서 통과.
- 버린 대안: 실패 사유 문구만 남기기(소유자 11-09 — 원인 해결 아님) · 재시도 횟수만 늘리기(매일 1~2분 멈춤·근본 원인=요청 수 그대로) · 직원 키워드 읽기를 백업 앞으로 옮기기(그래도 시트당 1회라 다른 읽기와 겹치면 재발).
- 영향 범위: `src/coupang_analytics/gsheet_api.py`(read_values_batch·_exec 429 기다림) · `gsheet_stats.read_staff_keywords` · `pipeline_gsheet._download_gsheet_via_sa`(백업·복원) · `tools/verify_gsheet_offline.py`(가짜 클라이언트 3곳·[8b]). 직원 키워드 반영 규칙(소유자 확정 2026-09-20 '시트 값이 기준')·백업 대상은 그대로.
- 상태: ACTIVE

### D-182 [SETTLE_ORDER_DETAIL] 주문별 매출 = 응답 cursorToken '' 이면 끝 · 쪽 수 대조는 원본 건수(rawRecordSize 합)로 · 월자료 실패 처리기록에 메시지 본문까지 (2026-11-09, R113)
- 결정: `settlement_docs.fetch_order_detail` ① 받은 쪽의 `cursorToken` 이 빈 값이면 그 쪽에서 멈춘다(빈 쪽까지 가는 기존 끝내기도 유지). ② 쪽 수 대조는 받은 줄 수가 아니라 쪽마다 `rawRecordSize` 를 더한 원본 건수로 한다(10×(쪽−1) < 원본 ≤ 10×쪽 · 줄 수 ≤ 원본 · `rawRecordSize` 없거나 줄보다 적으면 SiteChangedError · 중복 확인 그대로). 결과에 '원본 건수' 를 남긴다. ③ `_Run.attempt` 처리기록 한 줄에 실패 클래스 이름과 함께 메시지 본문(120자)을 남긴다.
- 근거(실측 — 11-09 소유자가 로그인한 Chrome 에서 조회만·size 10): 11-08 실행 월자료 주문별매출 실패 12건(1쪽 달 10 · 2쪽 이상 2). ① 명진상사 bf0621: 2026-07(8줄)·08(10줄)·09(3줄) 모두 1쪽 `cursorToken` '' · '' 로 2쪽을 부르면 서버가 처음부터 다시 시작해 같은 줄을 또 줌 → 옛 코드 '쪽 수(1) 뒤에도 줄이 더 옴'. 고친 순서대로 실제 서버에서 3달 = 요청 1번·확인 통과 · 줄 수·정산금액 합(231,936·289,920·57,014)이 쿠팡 정산 주문상세 엑셀과 같음. ② 원더풀리 oopean 2026-08: 쪽 수 49 · 5·29·31쪽 `rawRecordSize` 10 인데 9줄(두 번 조회해 같은 쪽) · 원본 481·줄 478(ORDER 476·배송비 CANCEL 2) · 줄어든 3건 = 상품+'<추가배송료>' 가 한 줄로 합쳐진 주문(예 4101887367207 = 38,693+9,670 = API 48,363 · 13101886220566 = 5,212+3,868 = 9,080) · ORDER 정산금액 합 12,885,833 = 엑셀 상품 12,868,427 + 추가배송료 17,406 · 날짜별 줄 수 20일 모두 엑셀과 같음 → 빠진 데이터 0, 옛 확인(줄 478 > 480 이어야)이 틀려 실패. 엑셀 기준 추가배송료 원본(476+3+2=481)도 API 와 같음. 가디즌 guarisen2024 2026-08(같은 날 확인): 쪽 수 4 · 2쪽 10건→9줄·3쪽 10건→8줄 · 원본 32·줄 29 · 합쳐진 것 = 상품+'<기본배송료>'(예 4102208453047 = 13,218+2,901 = API 16,119) · 같은 주문이라도 상품과 배송비가 다른 쪽에 걸리면 두 줄로 옴(3102094813557) → 서버는 같은 쪽 안의 배송비 건(기본·추가)을 상품 줄에 합침 · 엑셀 0원 아닌 건 32(상품 27·배송료 5)·정산금액 합 3,912,429 = API 와 같음 · 마지막 쪽 커서는 '' 아님(5쪽 빈 쪽으로 끝). ③ 실패 메시지 본문은 `out["실패"]` 에만 담기고 `tools/settlement_download.collect_docs` 가 쓰지 않아 처리기록엔 클래스 이름만 남았다(원인 파악 지연). 시험 `verify_settlement_runtime_offline` [P52] ④-b(커서 '')·④-c(합쳐진 줄·rawRecordSize 없음)는 옛 코드에서 실패·새 코드에서 통과.
- 버린 대안: 실패 사유 문구만 남기기(소유자 11-09 — 원인 해결 아님) · 같은 줄이 다시 오면 그 쪽을 버리고 끝내기(서버 신호 대신 추측 · 진짜 중복을 가림) · `pages` 쪽까지만 부르기(쪽 수가 틀린 경우를 못 잡음) · 줄 수 조건을 느슨하게(예 ±몇 줄) 하기(근거 없는 허용치 — 서버가 준 원본 건수로 정확히 대조).
- 확인 범위: 11-08 실패 12건 = ① 1쪽 달 10건(bf0621 실측) + ② 2쪽 이상 2건(oopean·guarisen2024 실측) — 전부 실제 응답으로 원인 확인.
- 영향 범위: `src/coupang_analytics/settlement_docs.py`(fetch_order_detail·_raw_size·_Run.attempt 기록) · `tools/verify_settlement_runtime_offline.py`(P52 ④ 가짜 응답에 rawRecordSize · ④-b · ④-c). size 10 고정(D-171)·중복 확인은 그대로.
- 상태: ACTIVE

### D-183 [COMPANY_STOCK_FIRST_TAB] 회사보유재고 = 재고현황 시트의 늘 첫 탭만 읽음(링크 gid 안 씀) · 3PL인천 수량도 지금처럼 총입고수량 (2026-11-09, R114)
- 결정(소유자 2026-11-09 "재고 표기 방식이 과거로 회귀 했어 · 확인 후 앱에 반영" → 선택지 답 '항상 첫 탭'·'지금처럼 총입고수량'): `company_stock.resolve_tab(client)` = 파일의 첫 탭. 설정에 넣은 재고현황 링크의 gid 는 쓰지 않는다(링크는 파일을 찾는 데만). 새 재고 탭은 맨 앞에 둔다. 관리대장 역기록(`run_company_stock`)·계정목록 표기(`pipeline_gsheet` 회사재고 주입) 둘 다 같은 함수. 첫 탭 오른쪽(L·M칸) '3PL인천창고 출고가능한 정확한 수량 (11/4기준) - 출처: 이벗매니저' 표(28품목)는 읽지 않음 — 3PL인천도 '총입고수량' 창고별 합산(D-141 그대로).
- 근거(실측 11-09·조회만): 재고 시트 탭 = ① `재고현황`(gid 1090789433·26.11.03 기준·730행·창고 3PL인천 54·3PL김포 421·김포2 253줄 → 676품목) ② `재고현황 1022기준(참고용)`(gid 1599921532·680품목·옛 창고 '검단') ③ `건기식_260929(대략)`. 운용 PC 앱 로그(`C:\Users\user\Downloads\output (33).zip`) — 11-06 20:09 ~ 11-09 06:49 회사재고 줄 10번 모두 `재고현황 '재고현황 1022기준(참고용)' 680품목`(대장 역기록 11-07·11-08·11-09 + 계정목록 표기). 관리대장 셀독리스트 '회사보유재고 (자동갱신 11.09)' 125줄 중 '검단' 들어간 칸 74 · 첫 탭에는 '검단' 창고가 없음 → 둘째 탭 값. 앱 코드는 링크 gid 탭을 읽으므로(옛 규칙 2026-09-29 '링크 gid 탭'·`docs/decisions/frozen-pre-2026-10-08.md:83`) 운용 PC 설정 링크가 둘째 탭 gid 를 가리킨 것으로 판단(설정 파일 자체는 이 PC 에서 못 봄 — 추정). 재현: 가짜 시트(첫 탭 새 양식·둘째 탭 '참고용')에 `?gid=2` 링크 → 옛 코드 = '재고현황 1022기준(참고용)' · 새 코드 = 첫 탭. 실제 시트: gid 1599921532·1090789433 링크 둘 다 새 코드에서 `재고현황` 676품목.
- 옆 표 대조(참고·안 씀): 28품목 중 같음 11 · 다름 17(예 발열장갑 W009 옆 480 vs 총입고 960 · 발열양말 W007 0 vs 480 · 공기압주입기 KS001 32 vs 76 · 햄스트링기구 R010 1,513 vs 1,500).
- 버린 대안: 링크 탭 + 탭 이름 '참고용'이면 ❌ 거부(링크를 사람이 또 고쳐야 함) · 코드 그대로 두고 운용 PC 링크만 고치기(같은 사고 재발) · 3PL인천 = 옆 표 우선(소유자 '지금처럼 총입고수량').
- 영향 범위: `src/coupang_analytics/company_stock.py`(resolve_tab 인자 url 제거·`_GID` 삭제·머리말) · `src/coupang_analytics/pipeline_gsheet.py`(호출 1곳) · `tools/verify_registry_offline.py` R21(늘 첫 탭·둘째 탭 링크로 run_company_stock) · `designs/DESIGN.md`. 운용 PC 적용 = 새 zip 설치 뒤(그 전까지는 설치본이 계속 참고용 탭을 읽음 — 운용 PC 설정 링크를 첫 탭 링크로 바꾸면 지금 설치본에서도 바로 바뀜). HQ 포팅 대상.
- 상태: ACTIVE

### D-184 [SETTLE_REVIEW_EVENT] 로켓그로스 리뷰 이벤트 비용 리포트(PPIR) = 실측 모양(요약 없음·6·7행 머리글)으로 읽음 · 자료 줄 0 = 0원으로 받기 끝 · 정산 차감액과 다르면 '확인 필요' (2026-11-09, R115)
- 결정(소유자 2026-11-09 '1·2번 승인'): ① `settlement_files.rg_cost_totals`·`rg_cost_lines` 가 리뷰 이벤트 리포트(머리글 줄에 '정산유형'·'리뷰 이벤트 수수료')를 알아봄 — 자료 줄 0 = 시트 합 0원·상품 줄 없음 → 받기 완료(같은 오류 반복 안 함). 자료 줄이 있는 리포트는 아직 본 적이 없어 금액 칸(할인적용금액(A-B-C)·VAT 포함 여부)·상품 칸을 추측하지 않고 오류(파일은 `_받는중` 에 남음). ② 받은 뒤 리포트 합 ↔ 그 정산 줄(같은 정산일·기간) 지급 내역의 `totalPostPurchaseDeductionAmount` 대조 — 다르면 처리기록 '대기 · 확인 필요 — 리뷰 이벤트 리포트 N원 ≠ 정산 차감 M원'. 차감액의 정산서 처리(상품 배분)는 소유자 결정 전 — 이 결정 범위 밖.
- 근거(실측): 운용 PC `C:\Users\user\Downloads\output (33).zip` 11-08 실행 — 91white(10-05~10-11)·sg0141n(09-28~09-30) 리포트 둘 다 시트 '리뷰 이벤트' 7행×18열, 1~5행 빈칸·6행 머리글·7행 하위 머리글(발생금액(A)·할인금액(B)·무료 프로모션 금액(C)·할인적용금액(A-B-C))·자료 줄 0 → 옛 파서 '3행 정산주기(종료일) 요약 머리글 없음' 오류. 같은 묶음 차감액 6,660·2,220원(정산현황 원문) = 리뷰 1건 2,220원(sg0141n 캠페인 인센티브 2,000+수수료 200). sg0141n 소유자 로그인 Chrome 조회만: 화면 `status-new.js` 엑셀 버튼 요청 본문 = `{sellerReportType, requestTime, settlementGroupKeys}` — 우리 요청과 같음 · 다운로드 목록 요청 7458ee63 PPIR COMPLETED · 리뷰 이벤트 관리 화면에 리뷰별 청구 조회 없음 → 쿠팡 리포트 쪽 공백(요청 방식 원인 아님). 재현: `verify_settlement_offline` [P11] 옛 코드 실패(운용 PC 와 같은 오류) → 새 코드 통과 · 실제 두 파일 = 0원·'확인 필요'(6,660·2,220).
- 버린 대안: 다시 요청(화면과 같은 요청이라 같은 결과로 판단) · 자료 줄 있는 리포트도 할인적용금액 칸 합으로 받기(VAT·상품 칸 미실측 — 추측) · 캠페인 누적 리뷰 수로 상품 배분(주별 숫자 아님 — 소유자 결정 대기).
- 영향 범위: `src/coupang_analytics/settlement_files.py`(`_review_rows`·`review_gap`·`REVIEW_FIELD`·rg_cost_totals/rg_cost_lines 분기) · `tools/settlement_download.py`(`_keep_cost` 리뷰 이벤트 대조 1곳) · `tools/verify_settlement_offline.py` [P11]. 운용 PC 적용 = 새 zip 설치 뒤 — 남아 있는 두 요청(요청됨)은 다음 받기에서 완료·확인 필요로 바뀜.
- 상태: ACTIVE

### D-185 [MANAGED_START_CONTRACT] 위탁정산서 관리 시작 달 = 자동 판정 달과 계약 시작일 달 중 이른 달 · 계약 전 판매는 뺌 · 차이 나는 계정은 정산서에 '확인 필요' (2026-11-09, R117)
- 결정(소유자 2026-11-09 — 차이 표를 보고 'D-179 ⑧ 보기 3번으로 해줘, 계약 전 판매는 빼줘'): ① 관리 시작 달 = 자동 판정 달(관리 상품 첫 판매·첫 물류비 중 이른 달)과 계약 시작일 달 중 이른 달. ② 계약 시작일 달 앞의 관리 상품 판매는 정산서에서 뺀다. ③ 두 달이 다르거나 맞는 계약을 못 찾은 계정은 정산서에 '확인 필요'를 적는다.
- 읽는 방법(Claude — 답 두 개를 함께 적용): 자동 판정 달이 계약 달보다 빠른 계정(휴라엘 sg0141n 2026-02 vs 2026-08)은 ②로 계약 달 앞 판매가 빠지므로, 판매·공제 모두 계약 달부터가 된다. 계약 달이 빠른 계정(케이씨메뉴팩처·벅스·효성·(DW)커머스·비엔케이미디어·에벤에셀·슈카새우)은 공제 범위가 계약 달부터로 넓어진다(그 사이 판매 0). 맞는 계약을 못 찾은 6계정(gorocket23·wellbing1107·WBpeak·mrc098·oopean·wavetech)은 자동 판정 달 그대로 + '확인 필요'. 계약 달 = 차이 표 '계약일(관리 상품과 맞는 계약)' 칸(AI 판정 · 품목 대조 근거) — 달 단위(D-154 와 같은 단위).
- 근거: 차이 표 `D:\토탈셀러\쿠팡 정산 자료\관리시작달_차이표_D179_20261109.xlsx`(정산서 `위탁정산서_20261103기준_관리상품_output30_D161_서비스이용료` 26계정 · 모두싸인 인덱스 3개 + 11-05 계약 4건) — 차이 큼 1(sg0141n 계약 전 2~7월 관리 판매 106,451,754원·정산금액 60,834,374원) · 확인 필요 8 · 1~2달 3 · 같음/거의 같음 6 · 달 같고 품목 다름 1 · 관리 판매 없음 7. 자동 판정 달 = 26계정 모두 첫 판매 달(물류비 먼저 0). 관리 시작 달은 지금 공제 범위만 자르고(D-154) 판매금액은 달로 자르지 않음(`statement_managed.py` account).
- 버린 대안: 자동 판정 그대로(D-179 ⑧ 보기 1) · 계약 시작일 달로만(보기 2) · 계약 전 판매도 정산서에 남기기(소유자 '빼줘').
- 영향 범위: git 밖 `output\_분석_261013\정산스크립트\statement_managed.py`(account 관리 시작 달·판매 달 거르기·확인 필요 표시) — 정산서 재생성 필요(다음 세션). 앱 코드 변경 없음. D-140 ① 관리 시작 달 정의를 대체. 계약자 정산표(D-152·D-155)도 정산서 재생성 뒤 영향 확인 필요.
- 상태: ACTIVE (부분 SUPERSEDED by D-186 — 판매 0인 달(계약 달~관리 첫 판매 전)의 공제 배분)

### D-186 [GAP_MONTH_DEDUCTION] 판매 0인 달(계약 달 ~ 관리 첫 판매 전)의 상품 구분 없는 공제 = 관리 몫 0 — 나눌 금액·평균·입금 나누기 모두에서 뺌 · 그 달 상품별 관리 금액은 그대로 (2026-11-09, R119)
- 결정(소유자 2026-11-09 '판매 0인 달은 평균에서 빼줘 → 제외가 정당한지 먼저 판단' → 검토·시험 계산 뒤 '실제 스크립트에 반영하고 26곳 다시 만들어줘'): 관리 시작 달(D-185)이 관리 첫 판매 달보다 빠른 계정에서 ① 상품 자료 없는 공제(기타 공제·보류 해제 등과 물류비·광고비 중 상품별 자료 없는 부분)는 관리 첫 판매 달부터의 공제·상품 자료·평균 비율로만 나눈다. 판매 0인 달은 그 달 관리 비율이 0 이라 몫 0 이다. ② 그 기간 상품별 쿠팡 자료로 잡히는 관리 상품 금액(광고·밀크런·물류·재고 보상)은 그대로 더한다. ③ 입금 완료/예정 나누기도 첫 판매 달부터의 지급 줄로 한다.
- 근거: 검토 `output\_분석_261013\정산스크립트\D185_판매0달_평균제외_검토_261109.md`.
  - 평균에서만 빼면 판매 0인 달 공제에 판매 있는 달 비율이 붙어 위탁자에게 더 물린다.
  - 그대로 두면 비율 0 이 평균을 깎아 판매 있는 달 몫까지 줄인다(D-185 판의 왜곡: 슈카새우 +299,974 · 에벤에셀 −689,542 · 효성 +14,082 · 벅스 +241).
  - 스크립트 규칙 문구 '공제를 받은 줄 판매 기간의 관리 정산금 비율'·D-154·D-146 과 맞는다.
  - 시험 계산(4계정)과 재생성: D-185 전 판과 비교해 휴라엘 외 모든 계정의 공제·G·입금 칸이 1원까지 같다(판매 0인 달 관리 상품 자료 0원).
  - 재생성 `D:\토탈셀러\쿠팡 정산 자료\위탁정산서_20261103기준_관리상품_output30_D186_판매0달제외\` = 독립 검산 26/26 · 정산 100% 일치 28/35 · 추정 0.
  - 시험 `test_managed_alloc`(gap_free 3개) = 옛 코드 실패 → 통과.
- 버린 대안: 판매 0인 달을 평균에서만 빼기(과다 청구) · D-185 판 그대로(희석 왜곡) · 달별로 따로 나누기(판매 달 기준 상품 자료와 판매 기간 기준 지급 줄이 어긋나 음수 달이 생김 — 근거 없는 처리 규칙 필요).
- 영향 범위: git 밖 `output\_분석_261013\정산스크립트\managed_alloc.py`(gap_free) · `statement_managed.py`(put 첫 판매 달 창·물류/보상/광고/밀크런 첫 판매 달 값·rates) · `test_managed_alloc.py` · 백업 `_백업\*_D186전.py`. 앱 코드·배포 zip 변경 없음. 계약자 정산표 금액 = D-185 전과 같음.
- 상태: ACTIVE

### D-187 [TRANSFER_SETTLE_DAILY] 셀독전환자 정산 2단계 = 정산 자료 받기 `transfer-settle` — 18:00 무인 앱이 함께 띄워 앱·정산 자동 수집이 끝난 뒤 받음 · 로그인 '실패' 계정은 무인으로 다시 안 넣음 · 원장 정산 파일은 복사 · 누적 엑셀 (2026-11-10, R121)
- 결정(소유자 D-179② '매일 18시 뒤' 의 구현 · 설계 `designs/SETTLEMENT_MODULE.md` §15 '2단계' 1~8):
  ① `정산다운로드.exe transfer-settle [--parent PID]` = 18:00 무인·재부팅 복구 앱이 정산 자동 수집과 함께 띄움(설정 `transfer/daily` — 탭 체크 '1' 켬·'0' 끔 · 빈 값 = 1단계 결과 `로그인확인_최신.json` 이 있는 PC 만 켬: 없는 PC 는 비밀번호 오류로 알려진 계정을 몰라 틀린 비번을 한 번 더 넣게 됨) + 탭 [지금 받기]. 작업 묶음에서 분리해 띄워 앱이 ③ 뒤 끝나도 계속 · 사람이 앱을 끄면 함께 종료(D-020 과 같은 `--parent`) · [정산 중지]·18:00 시작 정리 = 함께 끝남(같은 exe).
  ② 기다림 = 17:40~20:40(1단계 QUIET) · 앱 파이프라인 잠금 · 정산 자동 수집(watch) 잠금이 모두 풀려야 계정 시작 · 계정마다 다시 확인(돌면 5분마다 기다림 — 중단 아님) · 멈춤 = 시작 뒤 처음 오는 17:40.
  ③ 대상 = 파일 ①② 중 로그인 확인 결과가 성공·미확인·차단·건너뜀 — **'실패'(비밀번호 오류·2단계 인증·비밀번호 없음)는 무인으로 다시 넣지 않음**(비번을 고친 뒤 사람이 1단계 '성공 안 된 계정만 다시').
  ④ 계정 하나 = 1단계와 같은 로그인·판정(`transfer_login.logged_in` — 결과를 `로그인확인_최신.json` 에 갱신·지문만) → 원장 정산과 같은 `cmd_request`·`cmd_download`(정산현황 2026-01-01~ · 요청 계정당 한 실행 30건 · 90초 · 받기) · 계정 사이 45~75초 · 차단·미완료·오류 2계정 연속 = 중단 · 계정 잠금·Chrome 프로필 확인 = 원장 정산과 같은 것.
  ⑤ 원장 정산 기록(`output\정산\파일\`·`파일\비용\`)에 같은 정산일·채널·유형·리포트·기간 파일이 있고 이름 끝이 계정ID·앞부분에 전환자 대표자명 또는 사업자명이 칸 그대로 있으면 **요청하지 않고 복사**(처리기록 '받기 — 원장 정산 기록에 같은 파일').
  ⑥ 저장 = `output/정산_셀독전환/정산/`(정산 계정과 같은 모양 · `settlement_store.use_base`) · 누적 파일 = 실행 끝마다 `output/정산_셀독전환/셀독전환_정산내역_누적.xlsx`(안내·계정별 요약·지급 내역·상품별 정산 — 상품 칸 = 쿠팡 파일 원본 상품 ID·옵션 ID(VID)·상품명·옵션명 · 돈 합계 = 지급 내역) · 열려 있어 못 바꾸면 ❌ 종료 코드 3.
  ⑦ 1단계·2단계는 같은 잠금(`output/정산_셀독전환/_잠금/_실행.lock`)으로 한 번에 하나.
- 근거: 소유자 D-179②(2026-11-08 질문 답 '매일 18시 뒤'). 실측(2026-11-10 이 PC):
  - 전환자 파일 ①52·②51 = 103계정. 이 PC 1단계 결과 60계정 = 성공 4 · 실패 49(비번 오류 24·2단계 인증 15·비번 없음 10) · 차단 5 · 건너뜀 2 · 미확인 43 → 2단계 대상 54.
  - 원장 정산(`C:\Users\user\Downloads\output (33).zip` 요청기록 45계정)과 겹치는 전환자 = 12계정(①7·②5) · 1단계 성공 4 중 3.
  - 이미 받는 정산 파일 칸 = 윙 주문상세 '상품 ID·상품명·옵션 ID·옵션명'·로켓그로스 판매수수료 '등록상품 ID·옵션ID·등록상품명·옵션명'(웰빙곳간 실파일) → 새 쿠팡 자료 종류 없이 §15 상품 식별 칸 충족.
  - 시험 `tools/verify_transfer_settle_offline.py` S1~S8(설계 §15 기대 동작에서 도출). HEAD 판(`git archive`)에서 실행 = `transfer_settle` ImportError · 옛 `settlement_download`·`app_process`·`transfer_login` 위에서는 S5(REUSE_FROM 없음)·S7(transfer_settle_cmd 없음)·S8(잠금 없이 파일 오류로 진행) 실패 → 새 코드 통과 · `run_checks` 18종 초록 · `check_complexity` 경고 0.
- 버린 대안:
  - 원장 정산 watch 안에서 회차 '완료' 뒤 이어 돌기(소급이 여러 회차 걸리면 며칠 동안 안 돎 · 핵심 루프 수정).
  - 이 PC 상시 반복 프로세스(18:00 무인 시작 정리가 끝냄 · 재부팅에 사라짐).
  - 로그인 '실패' 계정도 비번 지문이 바뀌면 무인 재시도(다른 PC 는 지문 키가 달라 '바뀜'으로 보여 같은 틀린 비번을 다시 넣음).
  - 빈 설정 = 모든 PC 에서 켬(1단계 결과가 없는 운용 PC 에서 비번 오류 24계정에 한 번씩 더 넣음 — 시험 S2 로 막음).
  - 겹치는 계정도 따로 요청(같은 계정 요청 두 배 · 원장 정산 쪽 대기시간 응답 위험).
  - 계정ID 끝만으로 원장 파일 찾기('plan_it'·'it' 구분 못 함 → 다른 계정 파일 섞임).
  - 요청 상한 500(윙 다운로드 목록이 최근 30건만 보여 앞 요청을 못 받고 3일 뒤 재요청 반복).
  - 판매분석·검증 원자료·광고·월자료까지 받기(§15 범위 밖 · 앱 판매분석 폴더와 섞임).
- 영향 범위:
  - 신규 `src/coupang_analytics/transfer_settle.py` · `tools/verify_transfer_settle_offline.py`.
  - `transfer_login.py`(RUN_LOCK·logged_in/_judge 분리·main_cli 잠금 — 1단계 동작 불변 T1~T8 통과).
  - `tools/settlement_download.py`(transfer-settle 명령·_use_transfer_store·_transfer_work·_reuse_main·REUSE_FROM — 원장 정산 실행은 REUSE_FROM 없음 = 그대로) · `settlement_store.use_base`.
  - `app_process`(_settle_program_cmd·_spawn_detached·transfer_settle_cmd·start_transfer_settle) · `ui/app_qt.py`(18:00/재부팅 블록 2줄·import) · `ui/transfer_panel_qt.py`(2단계 카드) · `tools/run_checks.py`.
  - `designs/SETTLEMENT_MODULE.md §15` · `designs/FEATURE_INVENTORY.md` · `docs/CURRENT_RULES.md` 그 밖 주제.
  - 운용 PC 반영 = 배포 zip(통제 세션). 라이브(로그인·다운로드) 실행 없음.
- 상태: ACTIVE

### D-188 [SETTLE_VAT_HEAD] 윙 부가세 상세 파일 = 둘째 칸 머리글 빈칸(~2026-04 달)과 '옵션 ID'(2026-05 달~) 둘 다 같은 칸으로 읽음 · 머리글 오류 기록에 머리글 11칸 전부 (2026-11-10, R122)
- 결정(소유자 2026-11-10 '오류 A 고쳐줘'): `settlement_docs_request` 의 윙 부가세 상세(`MSF_PAYMENT_METHOD_DETAIL`) 머리글 판정이 둘째 칸 빈칸 한 가지만 받던 것을 빈칸·'옵션 ID' 두 모양으로 받는다(`WING_HEADS`). 나머지 칸 이름·순서·기간 판정·화면 월 합계 대조는 그대로(칸이 밀리면 합계 대조가 '실패'로 잡음). 머리글이 둘 다 아니면 지금처럼 '실패'(저장 안 함)이고, 기록에 앞 3줄의 11칸을 모두 남긴다(옛 6칸).
- 근거(실측 — `C:\Users\user\Downloads\output (34).zip` 11-09 19:11~11-10 09:49 운용 PC):
  - 윙 부가세 상세 받기 170번 중 158번 '머리글이 예상과 다름'(11-09 회차 오류 119건 중 106건) · 정상 12번.
  - 정상 12 = 모두 2026-02~04 달 파일 · 실패 = 모두 2026-05~09 달 파일(판매 없어 머리글만 있는 달 49건 포함) → 달에 따라 모양이 다름.
  - 받아 저장된 gorocket23 2026-04 파일과 11-08 실측 표본(gyi0101 2026-01) 머리글 = `주문번호 · (빈칸) · 매출인식일 · 항목유형 · 과세유형 · 신용카드(판매) …` · 실패 기록의 머리글 = `주문번호 · 옵션 ID · 매출인식일 · 항목유형 · 과세유형 · 신용카드(판매)` · 둘째 칸 값은 둘 다 옵션 ID 숫자.
  - 실패한 파일은 저장되지 않아 2026-05 이후 모양의 7~11번째 칸 이름은 미확인([추정] 같음) — 다르면 새 기록에 11칸이 다 남는다.
  - 시험 `tools/verify_settlement_runtime_offline.py` P53 에 '옵션 ID' 파일·머리글만 있는 달·다른 둘째 칸 이름(실패 유지) 추가 → 옛 코드에서 운용 PC 와 같은 오류로 실패 재현 → 새 코드 통과.
- 버린 대안: 둘째 칸 이름을 보지 않기(다른 파일을 잘못 받을 위험) · 첫 칸만 확인(칸이 바뀌어도 모름).
- 영향 범위: `src/coupang_analytics/settlement_docs_request.py`(`WING_HEADS`·`_rows`) · 시험 P53. '요청됨'으로 남은 윙 부가세 상세 208건(11-10 09:36 기준)은 새 zip 설치 뒤 다음 바퀴에 다시 받음(재요청 아님).
- 상태: ACTIVE

### D-189 [LEGACY_TASK_ELEVATE] 옛 정산 예약작업(인자 watch) = 사람이 켠 앱 시작 때도 지움 · 일반 권한으로 못 지우면 관리자 확인 창(UAC)으로 지우고 남은 수를 다시 셈 · 무인(18:00·재부팅 복구)은 확인 창을 띄우지 않음 · 실패 사유는 그대로 기록 (2026-11-10, R122)
- 결정(소유자 2026-11-10 '옛 정산 예약작업 — 너가 시작시 제거하고 시작해. 기능 추가'): `app_process.remove_legacy_settlement_task(log, elevate)` —
  ① 18:00 무인 시작(`prepare_auto_start`)은 지금처럼 일반 권한으로만 시도(D-091).
  ② 사람이 직접 켠 실행(`--auto`·`--resume` 아님)은 시작 때 시도하고, 못 지운 작업이 있으면 관리자 PowerShell 을 확인 창으로 띄워 지운 뒤(최대 300초 대기) 남은 수를 다시 센다.
  ③ 실패 기록 = 쿠팡 아닌 Windows 예외 문구 그대로(옛 '실패(권한)' 단정 문구 폐기).
- 근거:
  - 운용 PC 11-09 18:00 실행 로그 `[시작] ⚠ 옛 정산 예약작업 1개 삭제 실패(권한)` · 11-10 08:00 `정산다운로드.exe watch` 실제 실행(`output\정산\로그\실행_261110_080001.log` '이미 떠 있음 — 이 실행은 종료').
  - 그 작업을 만든 옛 `tools/settlement_watch_register.ps1`(fabfa9a) 첫 줄 '관리자 PowerShell 에서 실행' — 관리자가 만든 작업은 일반 권한 앱이 못 지움 [추정 — 옛 코드가 예외 문구를 버려 운용 PC 실제 문구 미기록 · 이번부터 기록].
  - 옛 코드는 예외 문구 없이 '권한'으로 적음 → 시험 P36 에 실패 사유 기록·관리자 삭제 성공·확인 창 취소(남음)·앱 시작 연결 추가 → 옛 코드 실패 재현 → 새 코드 통과. PowerShell 3개 명령 구문 검사 0오류 · 이 PC 의 watch 작업 수 = 0(삭제 명령·확인 창은 이 PC 에서 실행 안 함).
- 버린 대안:
  - 18:00 무인에서도 확인 창(누를 사람 없음 · 화면을 가려 반자동 창 작업 방해).
  - 정산 exe 가 예약작업으로 뜬 것을 알아채고 끝내기(뜨는 경로 판별이 불확실 · 작업은 남음).
  - '0_먼저실행_보안제외.bat'(관리자)에서 지우기(요청 = 앱 시작 때 · 이 파일은 CP949 원문이라 이번엔 안 고침).
- 영향 범위: `src/coupang_analytics/app_process.py`(`_ps` timeout 인자·`_LEGACY_MATCH`·`_LEGACY_COUNT_PS`·`_elevated_ps`·`_remove_legacy_elevated`) · `ui/app_qt.py` main(사람이 켠 실행 1줄·import) · 시험 P36 · `docs/CURRENT_RULES.md` 9절.
- 상태: ACTIVE

### D-190 [SETTLE_PW_LEDGER2] 정산 로그인 후보에 관리대장 값2 추가 — 순서 대장 값1 → 원장 값 → 대장 값2 · 최대 2개 · 앱이 대장을 읽을 때 값2 를 이 PC 암호 저장소에 함께 저장 (2026-11-10, R123)
- 결정(소유자 2026-11-10 '지금 발생한 문제점을 모두 해결'): `settlement_accounts.save_ledger_alternates`(앱 `_apply_pw_candidates` 에서 호출 — PC 엑셀·구글시트 대장 공용)가 줄마다 값이 다른 계정의 둘째 값을 키 `{계정ID}#대장값2` 로 저장(한 값이 되면 비움) · `login_passwords` = 대장 값1 → 원장 → 대장 값2 중복 없이 앞 2개(D-012 상한 유지). 원장이 값1 과 다르면 지금처럼 원장이 둘째(옛 동작 그대로) · 원장이 값1 과 같거나 비면 값2 가 둘째. 거부된 값의 24시간 금지(D-123)는 그대로(`_login_with_candidates` 공용).
- 근거(사실 — 코드·로그):
  - 정산 로그 '[비번] … wavetech: 관리대장' 표시 = `login_passwords` 분기상 원장 값이 비었거나 대장 값1 과 같을 때만 · 앱 저장소 = 대장 값1 만(`ui/app_qt.py` `c[0]`).
  - 앱 ① 11-09 18:34 '2번째 비밀번호 값으로 로그인 성공' · 정산 11-09 02:33·11-10 04:24 실제 입력 → '아이디 또는 비밀번호가 다릅니다'(`C:\Users\user\Downloads\output (34).zip` 실행·처리기록) → 정산은 틀린 값1 만 알았음.
  - dalbong1849 = '관리대장·원장 값이 다름' · 11-10 00:54 값1 24시간 금지 → 원장 값으로 00:55 로그인 성공 → 원장 둘째 순서를 유지해야 함.
  - 시험 P33 에 값2 순서·원장 우선 유지·저장/비움·실제 DPAPI 저장소 왕복 추가 → 옛 코드 실패(alt_key 없음) → 새 코드 통과.
- 버린 대안: 값 3개 모두 시도(D-012 최대 2 위반·틀린 입력 늘어남) · 값2 를 원장보다 먼저(dalbong1849 옛 동작 바뀜) · 앱이 성공한 값으로 저장소 값1 을 덮어쓰기(다음 대장 읽기 때 다시 값1 로 덮여 순서에 따라 달라짐).
- 영향 범위: `src/coupang_analytics/settlement_accounts.py` · `ui/app_qt.py`(`_apply_pw_candidates` 3줄·import) · 시험 P33. 셀독전환자(`transfer_accounts.login_passwords`)는 안 바꿈.
- 상태: ACTIVE

### D-191 [SETTLE_FETCH_FAIL_EVIDENCE] 정산 파일 받기 실패 기록 = 목록 줄 상태·생성 시각 + 받은 주소(호스트·경로만) + 오류 화면 제목·본문 글자 300자 — 원인 판정 근거 (2026-11-10, R123)
- 결정(소유자 2026-11-10 '쿠팡 서버 오류가 아닐 수 있음·원인 분석 필요' · '모두 해결' · '추정 금지'): `tools/settlement_download.py` `_get_bytes` 실패 문구에 주소(물음표 뒤 값 없음)·오류 화면 제목·본문(스크립트·스타일 뺌) 300자 · `_fetch_one` 이 앞에 목록 줄 상태·생성 시각을 붙임(처리기록 사유 200자 안에 먼저 들어가게 · 전체는 `오류_*.log`). 받기 판단·재시도 방식은 바꾸지 않음(원인 미확정 — 근거가 모이면 새 D 항목).
- 근거(사실 — output (34)):
  - '파일 받기 실패: 500 text/html' 20건(윙 부가세 상세 18 · RG 2). 같은 계정·달이 11-09·11-10 두 번 다 실패(hide4u 8달·dalbong1849 08·gorocket23 07·gyi0101 07·09) → 일시 오류 판정은 틀렸음(R122 보고 정정).
  - 큰 파일 아님: 검증 원자료 화면 월 합계 gyi0101 07 = 375,000원(그 계정 가장 작은 달) · hide4u 8달 모두 0원인데 다른 계정의 0원 달(bws247·greatjar)은 받아짐. 목록 상태는 완료(아니면 받기 시도 안 함 · `_match_one`).
  - 옛 기록 = 응답 앞 60바이트(`<!DOCTYPE html>…<meta http-equiv="c`)뿐 → 원인 판정 불가.
  - 시험 P45 에 500 HTML 화면 → 제목·본문·주소 기록·토큰 미기록 · 목록 줄 상태·시각 추가 → 옛 코드 실패(60바이트만) → 새 코드 통과.
- 버린 대안: 500 이 나면 바로 재요청(원인 모름 — 같은 계정·달이 계속 실패하면 요청만 늘어남) · 오류 화면 HTML 통째 저장(처리기록이 커지고 필요한 건 문구).
- 영향 범위: `tools/settlement_download.py`(`_get_bytes`·`_fail_text`·`_fetch_one`·import 3) · 시험 P45.
- 상태: ACTIVE (부분 SUPERSEDED by D-193 — 근거의 500 건수·계정 정정 · 결정은 그대로)

### D-192 [STOCK_MATCH_KOREAN_REASON] 회사보유재고 저장 AI 판정 중 근거가 한국어가 아닌 것 = 다시 판정 (2026-11-10, R123)
- 결정(소유자 2026-11-10 '모두 해결'): `company_stock_match.from_cache` 가 고른 재고가 있는 저장 판정이라도 근거(따옴표 안 상품명 빼고)에 한글이 없으면 None → 다시 AI 판정(근거 한국어 지시 그대로). 빈 근거·한국어 근거는 그대로 재사용.
- 근거(사실 — output (34) `_회사재고매칭.json` 85건): 영어 근거 13건 = 모두 날짜 2026-10-17~11-04 · 근거 한국어 지시가 들어간 R96(4350b90, 2026-11-05) 뒤 판정 65건은 모두 한국어 → AI 호출은 정상, 옛 저장값 재사용이 원인. 다시 판정 대상 = 재고를 고른 7건(재고 없음 6건은 원래 그날만 유효라 이미 매일 다시 물음). 시험 `verify_registry_offline` t21d 에 영어 근거 재판정·한국어 근거 재사용 추가 → 옛 코드 실패 → 새 코드 통과.
- 버린 대안: 저장 근거 글자만 번역(판정은 R96 전 기준 그대로 남음) · 저장값 전부 삭제(65건 불필요 재호출).
- 영향 범위: `src/coupang_analytics/company_stock_match.py`(`from_cache`·`_korean_why`) · 시험 t21d. 다시 판정한 7건은 결과가 바뀔 수 있음(현행 판정 기준) — 첫 실행 로그 '[회사재고] 매칭 … ← AI' 줄로 확인.
- 상태: ACTIVE

### D-193 [SETTLE_FETCH_FAIL_EVIDENCE] D-191 근거 정정 — 정산 파일 받기 500 = hide4u 한 계정 · 윙 부가세 상세 8달만 (2026-11-10, R124)
- 결정(소유자 2026-11-10 '추정 금지 · 테스트로 검증'): D-191 의 기록 방식(목록 줄 상태·시각·주소·오류 화면 문구)은 그대로 · D-191 근거의 '500 20건 · dalbong1849·gorocket23·gyi0101·RG 포함'은 틀린 집계라 이 항목으로 고침. 받기·재시도 방식은 바꾸지 않음(원인 미확정).
- 근거(사실 — output (34) `output\정산\로그\실행_*.log` 에서 '파일 받기 실패: 500' 줄만 셈):
  - 실행_261109_144346 4건(11-09 17:00 · 2026-06~09) · 실행_261109_191154 4건(11-09 20:18 · 06~09) · 실행_261110_072049 8건(11-10 09:35 · 02~09) = 16번 시도 · 모두 장성원-온라이프-hide4u 윙 부가세 상세 · 계정·달 기준 8개(2026-02~09). 다른 계정·RG 의 500 은 0건.
  - 틀린 원인: 앞 집계가 줄 안의 '500' 글자만 찾아 머리글 오류 줄(숫자에 500 이 든 줄)까지 셈. dalbong1849·gorocket23·gyi0101 은 머리글 오류(D-188 대상).
  - 대조 실측(이 PC · 소유자가 로그인한 Chrome · 조회만): gyi0101 2026-07·09 받기 주소 = 200 · zip 정상 · 2026-07 파일 머리글 11칸 = D-188 두 번째 모양과 같음. 받기 주소 s3Key 모양 4개 같음 → 주소 글자 문제 아님.
  - hide4u 는 광고비 조회도 10-27부터 500(hellojin 과 둘 · STATE 11-08 이상 (b)) · 소유자 2026-11-10 이 PC 에서 hide4u 로그인 안 됨 → 오류 화면 문구 실측 못 함.
- 버린 대안: 다른 계정으로 재현(500 이 hide4u 에만 나서 재현 안 됨) · 원인 추정으로 받기 방식 변경(근거 없음).
- 영향 범위: 문서만(DECISIONS·STATE 미해결 줄) · 시험 P45 설명 줄. 원인 판정 = 새 zip(R123) 첫 회차 `오류_*.log` 의 hide4u 줄(오류 화면 제목·본문).
- 상태: ACTIVE
