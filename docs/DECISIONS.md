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
- 상태: ACTIVE (부분 SUPERSEDED by D-022 — '단일 값 API parse_password_file 은 첫 후보로' → 정리 B1 에서 함수 삭제 · D-023 — 'parse_password_rows 는 첫 후보로' → 정리 B4 에서 함수 삭제·후보 목록 로그인 규칙은 그대로 · D-385 — 로그인 시도 순서: 지난번 자동입력으로 성공한 값(지문)이 지금 대장 후보에 있으면 맨 앞)

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
- 상태: ACTIVE (부분 SUPERSEDED by D-075 — 윙 'M' 건너뜀 문구 · 부분 SUPERSEDED by D-354 — 정산 탭 '정산 시작'은 ①완료 대기 없음 · 부분 SUPERSEDED by D-362·D-372 — 회차 시각(현행 00:10~그날 24:00))

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
- 상태: ACTIVE (부분 SUPERSEDED by D-090 — (1) '진전 없는 바퀴 = 남은 칸 ❌ 로 마침'은 IP 불량이 없던 바퀴만(IP 불량 바퀴는 빈 칸 0 까지 반복)·끝 조건 추가: 성공 없이 IP 불량 15번 연속이면 ③ 마침 · 부분 SUPERSEDED by D-257 — '빈 칸' = 그 날짜에 재는 칸만(계정 3묶음 쉬는 칸 제외))

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
- 상태: ACTIVE (추정 금지 적용 범위를 정산서 전체로 확대 — D-146 · 부분 SUPERSEDED by D-148 — 쿠팡 정산예정 금액은 불가피한 경우 추정 허용 · 부분 SUPERSEDED by D-350 — 쿠팡 줄 없는 기간 = 우리 산식 예상 금액('쿠팡 미확정' 표시))

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
- 상태: ACTIVE (부분 SUPERSEDED by D-126 — 정산서 표시: ⑥ 쿠팡 별도 보상 = C 섹션·'정산·보상 합계(⑤+⑥)' → 1쪽 A~G 밖 '참고. 쿠팡 계정 전체' 줄·총액 = G 최종 지급액(입금 완료/예정)·예정 포함/체험단 표시만/우리 사업자 통보 제외/대응표 우선은 그대로 · 부분 SUPERSEDED by D-200 — 정산서 표기 명칭 '체험단 비용' → '외부 마케팅 대행비')

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
- 상태: ACTIVE (부분 SUPERSEDED by D-249 — 검색창 없는 화면이 쿠팡 접근차단 화면이면 차단 목록에 기록)

### D-091 [SETTLE_NO_DUP_RUN] 정산 중복 실행 방지 — 같은 회차 '완료'면 ① 단계 기록 시각이 바뀌어도 종료 · 18:00 시작 때 옛 정산 예약작업(매일 08:00·인자 watch) 삭제 (2026-10-21, R19)
- 결정: (1) `settlement_watch.already_done(done, key, cycle_start)` — 키가 같거나, **완료 키(①완료 시각)가 이번 회차 시작(--since 반영) 이후**면 이미 완료. (2) `app_process.prepare_auto_start`(18:00 무인 시작)가 `remove_legacy_settlement_task` 로 인자 'watch' 예약작업을 지운다(실패 시 로그·계속). install.ps1 은 '자동실행 등록=Y' 때만 지워 폴더 덮어쓰기 업데이트로는 남았음.
- 근거: 실측 output(25): 10-19·10-20·10-21 매일 08:00:02 앱 없이(부모 PID 감시 줄 없음) 정산 watch 시작 → 10-20 18:00 정산이 21:31 '완료'(키 = ①완료 18:48:17)였는데 ③ 끝(04:29)에 단계 기록이 done 으로 바뀌어 키가 달라짐 → 35계정 재로그인·전부 다시 조회(08:00~09:16+) → 그 사이 output 압축 시 `_watch.lock`·`hellojin.lock` 사용 중 오류 · 아침 정산의 비밀번호 거부가 그날 18:00 수집을 막음(반달컴퍼니 10-20 10:14 → 18:19 D-068 건너뜀). D-010 은 예약작업 폐지를 정했으나 제거가 설치 시 한 번뿐이었음. 재현 실패(P36) → 수정 → 통과(P30 수동 전체실행 --since 동작 불변 포함).
- 버린 대안: 부모 PID 없는 watch 거부(기존 시험·수동 실행 경로가 parent 없이 watch 를 씀) · 단계 기록을 ① 완료 시각으로 고정(앱 재부팅 복구·정산 대기 판정이 함께 쓰는 기록이라 범위 큼).
- 영향 범위: `settlement_watch.py`(already_done) · `tools/settlement_download.py`(cmd_watch 한 줄) · `app_process.py`(remove_legacy_settlement_task·prepare_auto_start) · `tools/verify_settlement_runtime_offline.py`(P36). 운용 PC = 재배포 후 첫 18:00 에 옛 작업 삭제 로그 확인. HQ 포팅 대상.
- 상태: ACTIVE (부분 SUPERSEDED by D-354 — 정산 탭 '정산 시작'은 같은 회차 완료여도 받음 · 부분 SUPERSEDED by D-362·D-372 — 옛 정산 예약작업 삭제 시점 '18:00 시작 때' → 00:10 시작 때(시각만))

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
- 상태: ACTIVE (부분 SUPERSEDED by D-211 — (1)의 '최근 90일 관리 계정·중단일 90일 이내' 기간 제한 폐지 → 한 번이라도 관리한 계정 전부)

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
- 상태: ACTIVE (부분 SUPERSEDED by D-380 — 통합판매현황의 같은 상품명 VID 는 관리 VID 와 등록상품·노출상품이 같을 때만 · 정산서 범위(`settlement_statement_context` managed_listings)는 그대로)

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
- 상태: ACTIVE (부분 SUPERSEDED by D-364·D-372 — 멈춤 기본 17:40·운용 PC 실행 시간대 → 23:50·조용한 시간 23:50~02:50(00:10 실행 20분 전))

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
- 상태: ACTIVE (D-205 로 24시간 만료 부분이 잠시 대체됐다가 D-207 로 복원) — D-068 의 '그날(달력 날짜)' 부분을 대체(SUPERSEDED by D-123 표기는 D-068 상태 줄에) · D-018 적용 범위를 정산·전환자 확인까지 넓힘

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
- 상태: ACTIVE (부분 SUPERSEDED by D-140 — F 표 칸 제목 · SUPERSEDED by D-146 — (추정) 표기 · 부분 SUPERSEDED by D-236 — ⑤ 참고 묶음의 별도 입금(우대수수료 환급·추가지급)·상품별로 안 오는 금액은 정산 금액에 넣고 따로 표기)

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
- 상태: ACTIVE (구현 D-153 · 부분 SUPERSEDED by D-148 — 쿠팡 정산예정 금액은 불가피한 경우 추정 허용 · 부분 SUPERSEDED by D-350 — 쿠팡 줄 없는 기간 = 우리 산식 예상 금액('쿠팡 미확정' 표시))

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
- 상태: ACTIVE (부분 SUPERSEDED by D-236 — '자료 없는 공제 = 관리 몫 없이 참고에 쿠팡 금액' 부분)

### D-154 [DEDUCTION_SCOPE_SALE_PERIOD] 위탁정산서 공제 범위 = 지급 줄 판매 기간 기준 — 관리 시작 전 판매분 제외 · 밀크런은 시작 전달부터 (2026-11-05, R94)
- 결정(소유자 2026-11-05 '판매 기간 기준 수정'): 공제 관리 몫의 범위를 지급일이 아니라 지급 줄 **판매 기간 시작 달** ≥ 관리 시작 달로 자른다. 광고비의 '쓴 달 다음 달 지급 줄부터'도 없앤다(판매 기간 달이 광고 쓴 달과 맞음). 밀크런은 입고가 판매보다 먼저라 파일·공제 둘 다 관리 시작 전달부터. 입금 칸 나누기(status_split)와 보류 해제도 같은 기준.
- 근거(19계정 달별 대조·output(30)): 판매 기간 기준 2026-06~09 합이 상품 자료와 거의 같음(물류 6월 16.74M/16.79M·9월 21.75M/21.48M · 광고 8.30M/8.27M·8.11M/8.28M · 에벤에셀 물류 3~7월 원 단위 일치). 물류비 공백 53.41M = 시작 전 판매분 20.59M + 10월 이후 자료 미도착 25.48M + 2025-11 자료 없음 7.29M + 기타 0.04M · 광고비 공백 31.06M = 시작 전 0.66M + 10월 이후 11.32M + 2025-11~2026-03 자료 없음 19.19M − 0.11M. 시험: `due_since` 없어 실패 → 수정 → 통과. 첫 재생성에서 밀크런을 시작 달부터 자르자 효성 G +31,350 — 자료 범위(시작 전달)와 어긋난 회귀라 고침.
- 재생성(기준일 2026-11-03): 자동 검산 26/26 · 독립 검산 26/26 · 대조 28/35 · 추정 문구 0건 · A·E·G 불변(G 318,432,603) · 입금 완료 276,524,713 → 276,633,949(5계정) · 참고 칸 확인 필요 금액 합 210,781,537 → 139,884,181(빠른정산 111,992,019 → 65,362,067 · 물류비 53,418,143 → 32,827,919).
- 버린 대안: 지급일 기준 유지(시작 전 판매분이 확인 필요로 잘못 잡힘) · 밀크런도 시작 달부터(입고 먼저라 관리 상품 몫이 줄어듦).
- 영향 범위: git 밖 `output\_분석_261013\정산스크립트\managed_alloc.py`(due_since)·`statement_managed.py`(account·status_split)·`test_managed_alloc.py` — 백업 `_백업\*_D154전.py`. 결과 `D:\토탈셀러\쿠팡 정산 자료\위탁정산서_20261103기준_관리상품_output30_D146\`(덮어씀). 앱 코드 변경 없음. D-140 ① '그 전 정산일'을 대체. 남은 사실: 10월 이후 자료 미도착 · 옛 달 광고 자료 미수집 · 재고 보상 0.52M·밀크런 4~9월 2.09M 차이 미확인.
- 상태: ACTIVE (부분 SUPERSEDED by D-342 — 시작 전달이 2025년이면 밀크런도 2026-01부터)

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
- 상태: ACTIVE (부분 SUPERSEDED by D-227 — ② 계약일~대장 등록일 기간 보강 → 이력 없이 지워진 상품만 쿠팡 등록 로켓그로스 상품·계약 달 이후 등록으로 되찾음 · 보강 파일 폐기 R162)

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
- 상태: ACTIVE (부분 SUPERSEDED by D-164 — ① 중 '정산 줄 없는 주 비용'은 매일 정산의 받을 파일 계획으로 · 부분 SUPERSEDED by D-363 — '매일 정산에 넣지 않음'은 매일 회차 정산 받기 완료 뒤 남은 시간에 증빙 이어받기로)

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
- 상태: ACTIVE (부분 SUPERSEDED by D-413 — ① '물류비 5종' → 6종(반출 배송 서비스비 추가))

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
- 상태: ACTIVE (부분 SUPERSEDED by D-362·D-372 — 회차 18:00~17:55 → 00:10~그날 24:00(시각만))

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
- 상태: ACTIVE (부분 SUPERSEDED by D-257 — '순위 빈 칸'·1회 재시도 = 그 날짜에 재는 칸만(쉬는 칸 제외))

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
- 상태: ACTIVE (부분 SUPERSEDED by D-362·D-372 — ② 셀독 전환자 2단계 정산 자료 받기 '매일 18시 뒤' → 매일 00:10 무인 실행과 함께(빈도 '매일' 그대로 · 시각만 · 구현 D-187) · 나머지 ①③~⑧ 그대로)
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
- 상태: ACTIVE (부분 SUPERSEDED by D-381 — ① 커서 '' = 끝은 서버 쪽 수까지 받은 뒤만 · 중복 키에 구매확정일)

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
- 상태: ACTIVE (부분 SUPERSEDED by D-324 — 리뷰 이벤트 리포트 '자료 줄 0 = 0원' 부분)

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
- 상태: ACTIVE (부분 SUPERSEDED by D-375 — ② watch 잠금 기다림(대기 바퀴 쉼 동안 시작) · ③ 대상(이번 회차 받기 완료 계정 제외) · 부분 SUPERSEDED by D-362·D-372 — 띄우는 때 18:00 무인 → 00:10 무인(시각만))

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
- 상태: ACTIVE (부분 SUPERSEDED by D-194 — 원인 = 계정 사용 불가)

### D-194 [SETTLE_UNUSABLE_ACCOUNT] hide4u 정산 500 원인 = 계정 사용 불가(소유자) · 처리 = 그대로 둠(관리 중단 90일 규칙으로 자동 제외) (2026-11-10, R124)
- 결정(소유자 2026-11-10 "계정 사용 불가임" · 처리 질문에 '그대로 둠' 선택): hide4u(장성원·온라이프) 정산 받기 500 의 원인 = 계정 사용 불가. 코드 변경 없음 — D-103 정산 대상 규칙(관리 중단 뒤 90일)대로 마지막 관리일부터 90일이 지나면 정산 대상에서 빠짐. 그때까지 매 회차 hide4u 500 실패 기록은 원인 아는 실패로 봄.
- 근거: 소유자 답 · D-193 실측(500 = hide4u 윙 부가세 상세 2026-02~09 8달만 · 3회차 16번 · 8달 모두 0원 · 광고비도 10-27부터 500) · D-135(11-04 결과 시트 실측: hide4u 는 관리대장에 줄 없음) · `settlement_accounts.accounts_from_registry`(KEEP_DAYS=90 · `managed_between`).
- 버린 대안: '사용 불가 계정' 목록을 새로 만들어 정산·로그인 대상에서 바로 빼기(소유자 선택 안 함).
- 영향 범위: 없음(문서만). 같은 처리는 다른 사용 불가 계정에도 적용할지 따로 정하지 않음.
- 상태: ACTIVE (부분 SUPERSEDED by D-199 — 원인 = '사용 불가'가 아니라 **계정 정지(승인 반려)'** · 실측상 로그인·조회는 정상·받기/광고만 500 · 처리도 '그대로 둠'→'자동 감지 표기·건너뜀'으로 대체 · 부분 SUPERSEDED by D-211 — '관리 중단 90일 규칙으로 자동 제외' 폐지)

### D-195 [SHOPMINE_PW_SYNC] 샵마인 서버에서 쿠팡 위탁 계정 '현재 비번'을 하루 1회 받아 관리대장과 대조·자동 갱신 (2026-11-10, R125)
- 결정(소유자 2026-11-10 '앱에 통합' + '리포트+관리대장 자동반영' 선택): 비번을 ①구글 관리대장과 ②샵마인 서버에 이중 관리하는데 담당 직원이 샵마인만 고쳐 대장이 어긋남 → 샵마인에 저장된 값(= 실제 쿠팡에 로그인되는 현재 비번 = 진실 소스)을 **하루 1회** 받아 관리대장과 대조하고, 다를 때 **관리대장(구글시트)의 비밀번호 열을 샵마인 현재값으로 자동 갱신**한다. 경로 = 샵마인 앱과 동일한 서버 API(`POST /sm/api/login` → AuthenticationKey → `POST /sm/api/read/market_account`). 샵마인은 시스템 프록시를 무시하고 서버 IP 16개에 직접 http 접속 → 스크립트도 ProxyHandler({})로 서버 순회(failover).
- 적용 규칙:
  - 샵마인 현재값이 **비어 있지 않을 때만** 쓴다(빈 값으로 대장을 덮지 않음). 한 계정의 비번이 적힌 **모든 대장 행**에 RAW(값 그대로)로 써서 줄마다 달랐던 값(D-190)도 한 값으로 통일 · credstore(대장값1)도 함께 갱신해 **그날 ①·정산 로그인이 바로 새 값 사용** · 값2(D-190)는 비움.
  - 샵마인에만 있는 계정(대장에 없음)은 **행을 자동 추가하지 않고 리포트만**(관리대장은 상품별 구조라 계정 행 자동 추가 금지) · 대장에만 있는 계정(샵마인 없음)도 리포트만.
  - 리포트(`output/샵마인동기화/대조_YYYYMMDD_HHMMSS.csv`) = **계정ID·상태만**(같음/다름→대장갱신/샵마인에만/대장에만/샵마인 비번 없음) · **비번 값은 로그·커밋·화면·대화·리포트 어디에도 안 씀**.
  - 샵마인 로그인 자격 = 이 PC credstore(DPAPI·사용자 전용) 키 `__shopmine_login__`(기존 `__gsheet_sa__` 와 같은 방식) · 입력은 사용자가 직접(getpass·`tools/shopmine_sync.py setup`) — Claude 는 비번을 보거나 입력하지 않음(discover 는 필드명·건수만).
  - 호출 하루 1회(QSettings `shopmine/last_sync_date` 게이트) · 앱 관리대장(구글시트) 로드 직후 실행(①·정산 로그인 전) · **실패는 비치명**(로그만 · ①②③·정산 계속) · 미설정이면 조용히 건너뜀.
  - ⚠ 샵마인 약관상 비공식 접근 제한 가능성 1회 안내함(본인 계정·본인 데이터·저빈도).
- 근거(사실): 참조 분석 `D:\rea\evidence\shopmine`(PASSWORD_STORAGE.md — MarketPassword 는 클라이언트 암호화 없이 http 로 샵마인 서버에 저장·계정 조회 API 가 비번 반환 · LOGIN.md · AUTOMATION_PLAN.md pktmon 캡처로 요청 형식 확인) · 기존 비번 흐름 재사용(`input_list.parse_password_candidates`→`app_qt._apply_pw_candidates`→credstore · `settlement_accounts.login_passwords`·`alt_key` D-190) · 관리대장 = 마스터(D-134). 미확정 = ShopmineVersion 실제값·CurrentPageNumber 1-based 여부·계정 필드명(정적분석 추정 MarketId/MarketPassword) → 사용자 자격으로 discover 1회 확정.
- 버린 대안: ①리포트만(소유자가 자동반영 선택) ②openpyxl(xlsx) 로 대장 수정(참조 스크립트 방식 — 우리 마스터는 구글시트라 gsheet_api 로 교체) ③별도 스크립트/스케줄러(앱 18시 흐름에 통합) ④샵마인 로컬 DB·캐시·엑셀에서 비번 추출(비번 없음 — 엑셀 별표 마스킹·로컬 SQLite 없음·크롬 저장소 0건, 유일 경로 = 서버 API) ⑤별도 DPAPI 저장소(앱 credstore 재사용).
- 영향 범위: 새 `src/coupang_analytics/shopmine_sync.py`(코어) · `tools/shopmine_sync.py`(CLI setup/discover/sync/selftest) · `input_list.password_column`(공개 헬퍼 추가) · `ui/app_qt.py`(`_maybe_shopmine_sync` 훅 1곳) · 게이트 `tools/verify_shopmine_sync_offline.py`(run_checks 등록). 실서버 discover/sync 는 사용자 자격으로 1회 확인(비번 미노출).
- 상태: ACTIVE (실서버 검증·로그인 원인 = D-196 · 부분 SUPERSEDED by D-385 — 자격 없음 = 조용히 건너뜀 → 하루 1번 로그 · 24시간 안 거부된 값이면 대장 안 덮음 · D-388 — setup CLI 필수 → 설정 탭 한 번 입력·필드 확인·대조 자동)

### D-196 [SHOPMINE_PW_SYNC] 샵마인 실서버 검증 완료(로그인 원인 = 비번 값 오차) · sync `--dry-run` 추가 · 마스터 실쓰기는 앱 훅/소유자만 (2026-11-10, R126)
- 결정: D-195 구현의 **실서버 로그인 거부(IsSuccess=False) 원인 = 비밀번호 '값' 오차 하나**로 확정하고(코드·요청 형식은 정답), 마무리 방식을 정한다.
  - **실서버 검증 결과(사실)**: pktmon 으로 사장님의 **정상 성공 로그인 1회**를 캡처(관리자 PowerShell `pktmon start/stop` → `etl2pcap` → `parse_capture.py`, 비번 값 마스킹) → 실제 성공 `POST /sm/api/login` 본문이 우리 `do_login` 과 **완전 일치**: 필드 5개(CompanyId·UserId·UserPassword·OsVersion·ShopmineVersion) · CompanyId=업체ID · UserId=사용자ID(비우지 않음) · OsVersion="" · ShopmineVersion=26.8.24.866 · 평문(해시·AES·salt·prefix·추가필드 없음). 유일한 차이 = UserPassword **값**(샵마인 자동로그인이라 사장님이 평소 안 치는 값 · 실제 길이 4자 ≠ 추정 12자). 계정조회 응답 필드명 `MarketId`/`MarketPassword` 확정(우리 기본값과 일치) · 계정 59건.
  - **마무리 방식**: 캡처(평문 http)의 실제 비번을 **화면 미출력로 곧장 credstore(DPAPI)에 심는 1회용 스크립트**로 심어 discover 성공 확인(비번 값은 Claude·로그·커밋에 안 남고 길이만 표기). 블라인드 재시도 금지(잠금) 원칙은 유지했고, 캡처는 성공 로그인이라 추가 실패 0.
  - **sync `--dry-run` 추가**: `run_daily_sync(..., apply=True 기본)` 에 `apply=False` 경로 · CLI `sync --dry-run` → 대조·리포트만, 관리대장·credstore 에 **쓰지 않고** 갱신 예정 건수만 보고(첫 수동 실행 안전 미리보기). 일상 자동(앱 훅)은 `apply=True` 그대로.
  - **마스터(관리대장) 실 쓰기 주체**: 사이드 세션은 실 sync 쓰기를 하지 않는다(통제 세션 전용 취지 [[feedback-control-session-only]]). 실 쓰기 = 배포 후 **앱 훅이 매일 자동**(소유자 '리포트+관리대장 자동반영' 승인 D-195) 또는 소유자/통제 세션이 수동. 첫 확인은 `sync --dry-run` 권장.
- 근거(실측): pktmon 캡처 `C:\Temp\sm.pcapng`(파싱 `D:\rea\evidence\shopmine\parse_capture.py`) → 성공 로그인 본문 = 우리 코드와 동일 · discover 출력(로그인 키 AuthenticationKey·AuthorizationCode·IsSuccess · market_account 응답 DataTable·TotalCount·PageCount 등 · 59건 · 필드 MarketId·MarketPassword 존재) · 게이트 `test_dry_run_no_write` 추가 후 run_checks 19종 초록·check_complexity 0.
- 버린 대안: ①비번 변환(해시) — REA IL·캡처 둘 다 평문 확정이라 폐기(옛 `--pw-hash` 제거 0a61d4f) ②사이드 세션이 실 sync 로 관리대장 바로 갱신 — 통제 세션 전용·마스터 오쓰기 위험으로 폐기(dry-run 까지만).
- 영향 범위: `shopmine_sync.run_daily_sync`(`apply` 매개변수 추가·기본 True·행동 불변) · `tools/shopmine_sync.py`(`--dry-run`) · 게이트 `test_dry_run_no_write`. 로그인·계정조회·필드명 코드는 변경 0(실서버에서 그대로 맞았음).
- 상태: ACTIVE (백업 추가 = D-197)

### D-197 [SHOPMINE_PW_SYNC] 비번 되쓰기 전 관리대장 백업 = 구글시트 안 탭 복제(로컬 백업 금지와 양립) (2026-11-10, R127)
- 결정: 샵마인 동기화가 관리대장(구글시트) 비밀번호 열을 **쓰기 직전에**, 그 관리대장 탭을 **같은 스프레드시트 안에** `백업_비번동기화_YYYYMMDD_HHMMSS` 로 복제해 백업한다(값·서식 그대로). 복제는 **변경이 있을 때만**(갱신 계획 비어있지 않고 `apply=True`일 때) · 변경 없는 날·`--dry-run`은 백업 안 함.
- 근거/제약: ⛔ 관리대장에는 **평문 비밀번호**가 있어 **로컬 파일 백업 금지**(공유·유출 위험·전역 CLAUDE.md). 그래서 백업을 **구글시트 안**(복제 탭)으로만 한다 — 비번이 구글 밖으로 나가지 않아 '로컬 백업 금지'와 양립. 되돌리려면 백업 탭의 비번 열을 원래 탭에 되쓰면 됨. 구현 = `GSheetClient.duplicate_sheet`(Sheets API `duplicateSheet`) · `shopmine_sync.backup_ledger`(되쓰기 직전 1회) · 게이트가 '백업이 모든 되쓰기보다 먼저·dry-run은 백업 0' 검증.
- 버린 대안: ①로컬 CSV/JSON 백업(평문 비번 유출 — 정책 위반) ②변경 셀만 로그로 적재(감사용이나 '관리대장 백업' 요청엔 전체 스냅샷이 명확) ③구글 자체 버전기록에만 의존(명시적 복제가 발견·복구 쉬움) ④오래된 백업 탭 자동 삭제(탭 삭제는 파괴적·위험 → 안 함, 소유자가 수동 정리).
- 영향 범위: `src/coupang_analytics/gsheet_api.py`(`duplicate_sheet` 1개 추가) · `src/coupang_analytics/shopmine_sync.py`(`backup_ledger` + `run_daily_sync` 되쓰기 직전 1줄) · 게이트 `tools/verify_shopmine_sync_offline.py`(FakeClient `duplicate_sheet`·순서 검증). 일상 자동(앱 훅)·수동 `sync` 모두 적용 · `--dry-run`은 백업 안 함.
- 상태: ACTIVE

### D-198 [SHOPMINE_PW_SYNC] 한 계정이 여러 줄이면 '모든 줄'을 현재값으로 통일 — '같음'은 모든 줄이 이미 현재값일 때만 (2026-11-10, R128)
- 결정: 관리대장은 한 계정의 계정ID·비번이 **여러 줄(상품마다 한 줄)에 걸쳐** 적히는 경우가 많다. 샵마인 현재값과 대조할 때, 그 계정의 **모든 줄이 이미 현재값일 때만 '같음'**으로 보고, **한 줄이라도 다르면 '다름→대장갱신'**으로 보아 그 계정의 **모든 줄을 현재값으로 통일**한다(이미 맞은 줄 포함해 그 계정 비번이 적힌 전 행에 되씀).
- 근거(사실): 담당자가 여러 줄 중 **한 줄만 새 비번으로 고치는 경우**가 실측(D-012·D-190 — DW커머스 9줄 중 일부만 다름·반달 57행≠60행). 이전 로직은 '현재값이 여러 후보 중 하나와만 같아도 같음'으로 보아 **나머지 옛값 줄을 그대로 둬**, 로그인이 옛값 줄을 집어 막힐 수 있었다('모두 변경' 요청·소유자 2026-11-10 스크린샷 (DW)커머스 3줄). `classify`: `led_pw[aid] == {sm}` 일 때만 '같음' · `updates_to_apply`: `led_pw[aid] != {sm}` 면 갱신(되쓸 행 = 그 계정의 모든 후보 행).
- 적용 제약: '모든 줄' = 계정ID·비번이 **둘 다 적힌** 행(파서 `parse_password_candidates`). 계속 줄에서 **계정ID 칸이 비어 있는(병합·생략)** 배치는 그 줄을 못 잡는다 — 현재 대장(셀독리스트)은 줄마다 계정ID를 반복(스크린샷)하므로 해당 없음. 그런 배치가 생기면 ID 전방 채움(forward-fill)을 별도로 추가해야 함(미구현·소유자 확인 대상).
- 버린 대안: ①한 줄이라도 맞으면 '같음'(기존 — 옛값 줄 잔존·로그인 거부 위험) ②계정ID가 나온 모든 행에 무조건 되씀(비번 칸이 의도적으로 빈 줄까지 채울 위험 — 현재 대장은 줄마다 채워져 있어 후보 행으로 충분).
- 영향 범위: `src/coupang_analytics/shopmine_sync.py`(`classify`·`updates_to_apply` 조건 2줄 · 행동 변경) · 게이트 `test_unify_all_rows_when_partial_match` 추가. 기존 테스트(단일/다중 줄 전부 다름)는 그대로 통과. ⚠ 실데이터 '다름' 건수가 이전 dry-run(34같음·1다름)보다 늘 수 있음(옛값 줄이 남아 있던 계정이 '다름'으로 잡힘) → 배포 전 `sync --dry-run` 재실행 권장.
- 상태: ACTIVE

### D-199 [ACCOUNT_SUSPEND] 매일 18시 로그인 직후 계정 정지(승인 반려) 감지 → 수집 건너뜀 + 관리대장 계정아이디 취소선 표기(가역) (2026-11-11, R129~)
- 결정(소유자 2026-11-11): 매일 18시 실행에서 각 계정 **로그인 성공 직후 계정 상태를 확인**해, 정상이면 수집을 진행하고 **정지(승인 반려)면 그 계정의 수집·받기·광고를 건너뛰고 다음 계정으로** 넘어간다. 정지로 판정된 계정은 **관리대장 계정아이디 칸에 취소선**을 쳐 표기한다(= input_list 가 다음 회차부터 그 계정을 제외 → 불필요한 500·시도 없음). **정상화되면 원복**(취소선 제거). 샵마인 비번 동기화(D-195)는 이미 계정 루프 전 1회 돌아 이 흐름 앞단에 있다.
- **정정(hide4u·D-194 보완)**: hide4u(장성원·온라이프, 업체코드 A01781927)는 "계정 사용 불가"(D-194)가 아니라 **계정 정지(승인 반려)**다. 실측(2026-11-11 사장님 Chrome 으로 hide4u 윙 관찰): **로그인·판매 조회·정산 '요청'은 정상**(누적 로그인 40·조회 1142·판매분석 10 정상), **정산 부가세상세 '받기'와 광고비만 영구 500**(계정이 정지라 해당 엔드포인트 차단). 즉 D-194 의 '사용 불가'는 부정확 — 정확히는 '정지(읽기는 되고 정산 받기·광고만 막힘)'.
- **감지 신호(실측 확정)**: 정지 계정은 로그인 후 윙 홈이 정상 대시보드가 아니라 **온보딩 화면**("판매 준비하기 0/2" · "판매자 정보 입력하기 **승인 반려**" · "빠르게 판매를 시작하세요")이고, **좌측 메뉴 링크가 실제 URL 이 아니라 `/unapproved/...` 로 라우팅**(가격관리=`/unapproved/PRICE_MANAGEMENT_RENEWAL`·배송관리·주문조회 등). 정산/매출 메뉴는 실제 URL 유지(그래서 조회는 됨). 판정 = 앵커 href 에 `/unapproved/` 있음 **또는** 홈에 "승인 반려" 문구 → 정지(둘 다 정상 계정엔 없음). 신호 없음·읽기 실패 = 정상(오탐=정상→정지 수집중단 보다 누락=정지→정상 기존대로 시도가 안전). KB(쿠팡 WING 도움말)엔 정지가 '제재'로만 나오고 화면 표시법은 없어 실제 윙 관찰로 신호를 정의함.
- **구현(2026-11-11)**:
  - R129(1/2): `browser.judge_suspended`(순수)·`WingBrowser.is_suspended` · `input_list.account_id_column`·`account_id_rows`(계정 **모든 행** — reader `_handle_account_row` 가 매 행 계정아이디 셀을 검사·비-취소선 행에서 acct_cancelled 풀림) · `gsheet_api.set_strike`(repeatCell·설정/해제 겸용 → 원복) · 신규 `account_suspend`(상태 파일 `_계정정지.json` = 앱이 친 취소선만 기록 → 사람이 친 해지-취소선과 구분 · `apply_strikes`=되쓰기 전 백업 먼저·여러 행 취소선) · 게이트 `verify_account_suspend_offline`(8시나리오·run_checks 20종).
  - R130(2/2a): `pipeline_sales._login_and_discover` 로그인 뒤·수집 전 게이트 → 정지면 `mark_suspended` + `AccountSuspended` 예외 · `pipeline` 두 루프에서 그 예외 = done 처리·재시도 안 함(차단/비번오류와 별개)·다음 계정. 핀 가짜 WingBrowser 에 `is_suspended` 추가.
  - **(미완·2/2b)** `ui/app_qt.py` 훅: 실행 후(또는 관리대장 로드 때) `apply_strikes` 로 상태 파일 기준 취소선 **실제 표기** + **정상화 원복**. 원복 설계 = 취소선 계정은 input_list 가 제외하므로, 정상 전환 감지는 (a) 사람이 취소선을 떼면 그 계정이 활성 복귀→로그인→정상이면 상태 파일에서 제거(앱이 검증·복원)/여전히 정지면 재표기, 또는 (b) 정지 계정까지 매 회차 로그인-재확인(미구현). D-194 처리('그대로 둠')는 이 기능으로 대체(정지 계정 자동 표기·건너뜀).
- 근거: hide4u 윙 실측(스크린샷·DOM `/unapproved/`·업체코드 A01781927) · 누적 처리기록 77회차(hide4u 로그인·조회 정상 vs 받기·광고 전부 500) · 게이트 초록(run_checks 20종).
- 버린 대안: ①500 을 정지 신호로 재분류(D-010 'ServerBusy=일시오류'와 충돌·정지와 일시 500 구분 불가) ②로그인 직후 프로브 호출로 500 유도(일시오류 오탐) ③수동 취소선만(앱 감지 없이 사람이 표기 — 소유자는 앱 감지를 선택) ④상태 컬럼에 '계정 정지' 텍스트(소유자가 취소선 선택) ⑤상품 전체 SUSPENDED 를 신호로(collector 주석상 '신규등록 불가' 제한과 모호).
- 영향 범위: `browser.py`·`input_list.py`·`gsheet_api.py`(헬퍼 추가) · 신규 `account_suspend.py`·`tools/verify_account_suspend_offline.py` · `pipeline_sales.py`·`pipeline.py`(게이트·예외 분기) · (예정) `ui/app_qt.py`(표기·원복 훅). run_checks 20종.
- 상태: ACTIVE (부분 SUPERSEDED by D-211 — 정산 받기는 건너뛰지 않음 · 판매수집 건너뜀·대장 취소선은 그대로 · 소유자 승인 D-215 · 부분 SUPERSEDED by D-362·D-372 — '매일 18시 실행' → 00:10 실행(시각만)) — 코드 구현 중(2/2b app_qt 표기·원복 훅 미완)

### D-200 [STATEMENT_MKT_AGENCY_LABEL] 위탁정산서 표기 '체험단' → '외부 마케팅 대행비' (다음 생성부터 · 기존 정산서는 다시 만들지 않음) (2026-11-11, R134)
- 결정: 위탁정산서(관리상품 양식)의 '참고. 체험단 비용' 줄 → '참고. 외부 마케팅 대행비 (위 금액에서 빼지 않음)', 설명 → '완료된 외부 마케팅 대행(리뷰비·택배대행비·상품금액) · 상세는 '외부 마케팅 대행비' 시트', 시트 이름 '체험단' → '외부 마케팅 대행비'. 금액·계산·표시만 규칙(D-088)은 그대로. 이미 만든 정산서는 다시 만들지 않고 다음 생성 때 반영(소유자 "아직 생성하지 말고 추후 생성시 반영").
- 근거: 소유자 2026-11-11 "체험단이란 표현은 적절하지 않음 → 외부 마케팅 대행비로 정산서만 바꿔줘". 실측: 쿠팡 정산 파일 138개에 '체험'·'리뷰' 0줄(쿠팡 용어 아님) · 벅스 4줄의 근거 = 웨이프로젝트 견적서 Q202606-010(품명 = 리뷰비·택배대행비·상품금액, '체험단' 낱말 없음) + KB 이체확인증 2026-06-05 3,175,000(소유자가 2026-10-19 이미지로 제공).
- 버린 대안: 리뷰 마케팅 비용(상품금액·택배대행비까지 '리뷰'로 좁게 읽힘) · 판매 촉진 비용(쿠폰·광고와 섞임) · 업체명(웨이프로젝트 대행비 — 업체 바뀌면 다시 바꿔야 함) · 앱 전체 용어 변경(관리대장 시트·결과 시트 체험단 칸 — 소유자가 '정산서만' 지정).
- 영향 범위: 정산서 스크립트(git 밖) `output/_분석_261013/정산스크립트/statement_managed.py`(795·796·826줄)·`statement_managed_sample.py`(310·311·382줄) — 사본 `_백업/D200전/`. 옛 양식 `business_statements.py`('H. 체험단 비용')·`experience.py`(관리대장 '체험단' 시트 읽기)·관리대장/앱/결과 시트 '체험단'은 그대로. 제품 칸 값은 자료 그대로라 `체험단_보충.json` 일부 줄(예: '웰시컴퍼니 체험단 진행비')은 낱말이 남음. 정산서 '체험단' 시트를 읽는 다른 코드 없음(검색 확인).
- 상태: ACTIVE

### D-201 [DEPLOY_ZIP_UTF8] 배포 zip 은 한글 이름에 UTF-8 표시 + 자동 대조 통과본만 · tar(cp949) 압축본 배포 금지 (2026-11-11, R137)
- 결정: 배포 zip(`dist\쿠팡애널리틱스_배포.zip`)은 비ASCII 이름 전부에 UTF-8 표시(0x800)가 있어야 하고, 만든 뒤 자동 대조(항목 수·이름·크기·CRC·내용 SHA-256 + Windows 탐색기 엔진·.NET 실제 풀기 → 파일 수·이름·해시 일치)를 통과한 것만 배포한다. build.bat 의 Compress-Archive 가 멈출 때 쓰던 `tar -a` 대체(이름 cp949·표시 없음)는 금지. 당장의 방법 = tar/기존 zip 을 `output\_배포검증\rezip_utf8.py`(Python zipfile · 내용 바이트 그대로 · 이름만 UTF-8)로 다시 쓰고 대조. R132 배포본을 이 방법으로 교체(내용 동일).
- 근거: 소유자 2026-11-11 "tar로 만든 zip의 한글 파일 이름이 운용 PC에서 정상으로 풀리는지 모름 → 신뢰를 못하면 적용을 할 수 없어" → "UTF-8 zip으로 다시 만들고 자동 대조해줘". 실측: R132 zip(174,294,700B) 항목 1,943 중 한글 이름 16개 UTF-8 표시 0 · cp949 원시 바이트(한국어 코드페이지 Windows 에서만 바르게 풀림) — `쿠팡애널리틱스.exe`·`정산다운로드.exe`·`_설정값.json`·`_씨앗/` 포함. 교체본(174,214,978B · SHA-256 앞 16자 c6429b4f3e3163a8): 한글 16/16 UTF-8 표시 · 옛 zip 과 1,943개 이름(cp949 해석)·크기·CRC·SHA-256 일치 · 탐색기 엔진(Shell.Application CopyHere)·Expand-Archive 각각 파일 1,782/1,782 · 빠짐 0 · 남는 것 0 · 내용 다름 0 · 한글 이름 파일 15(+폴더 1).
- 버린 대안: 운용 PC 에서 16개 이름 사람이 확인(소유자가 자동 대조 선택) · PyInstaller 부터 다시 빌드(내용이 R132 와 같다는 보장이 사라지고 8분 소요) · tar 그대로(신뢰 미확인).
- 영향 범위: `dist\쿠팡애널리틱스_배포.zip` 교체(옛 tar 본 = scratchpad 사본만) · 다음 빌드부터 압축 단계(build.bat 반영은 별도 승인 — STATE T-17) · 한계: 이 PC 는 한국어 Windows 라 비한국어 코드페이지 PC 실측은 없음(UTF-8 표시는 코드페이지와 무관한 표준 방식 · Python·.NET·탐색기 세 판독기 확인).
- 상태: ACTIVE

### D-202 [PROPOSAL_NO_WEAKENING] 개선안은 정책 결정 누락·검증 약화가 따르면 안 됨 · 신뢰 확인 안 된 방식은 적용 불가 (2026-11-11, R137)
- 결정: 속도·편의 개선안을 낼 때 ① 검증(게이트·대조·핀)을 줄이거나 건너뛰게 만드는 안 ② 필요한 정책 결정(D항목·CURRENT_RULES)을 빼고 바꾸는 안은 제시하지 않는다. 바꿔야 할 결정이 있으면 그 D항목을 안에 함께 올린다. 결과가 대상 환경에서 확인되지 않은 방식(예: 운용 PC 미확인 압축 방식)은 적용하지 않고, 먼저 자동 대조 등으로 신뢰를 확보한다.
- 근거: 소유자 2026-11-11 "tar로 만든 zip의 한글 파일 이름이 운용 PC에서 정상으로 풀리는지 모름 ==> 신뢰를 못하면 적용을 할 수 없어" · "개선안 제시시 정책 결정 누락, 검증기능 약화가 동반되면 안됨". 적용 결과: session-close 속도안 중 '같은 날 같은 내용이면 3단계 게이트 건너뜀'(시각·환경 의존 실패 놓침)·tar 압축·STATE 부분 수정·D-008 무결정 변경을 뺌(`D:\claude-global\docs\plans\session-close-speed-precheck-2026-11-11.md` 4절) · tar 본 배포 zip 은 D-201 로 교체.
- 버린 대안: 위험을 문서로 알리고 적용(소유자가 '적용 불가'로 거절) · 속도 우선으로 검증 일부 생략.
- 영향 범위: 앞으로의 모든 개선 제안(이 저장소) · STATE T-16·T-17 · CURRENT_RULES '그 밖 주제' 1줄.
- 상태: ACTIVE

### D-203 [GATE_SELFTEST_OVERLAP] 회귀 게이트 자체 검사의 '동시 실행' 판정을 걸린 시간 대신 실제 겹침(서로 기다리기)으로 (2026-11-11, R137)
- 결정: `tools/verify_run_checks_offline.py` S5 의 "1초짜리 3개를 동시 3개로 돌려 2.0초 안" 시간 판정을 지우고, 서로의 시작 표시를 기다리는 검사 3개(`_barrier_scripts` · 10초 안 못 만나면 exit 1)가 동시 3개로 모두 통과하는지로 판정한다. 하나씩(`-j 1` 경로 = `run_all(..., 1)`) 돌리면 실패해야 한다는 반대 확인(1.5초)을 새로 넣는다. 결과 순서·실패 판정·`-j 1` 판정·통과 기록 안 함은 그대로.
- 근거: 11-11 /session-close 3단계 전체 게이트에서 이 검사만 실패 → 단독 실행 통과 · 같은 내용 재실행 20종 통과(151.7s) = 간헐 실패. 재현(S5 와 같은 코드로 측정): 부하 없음 10회 1.18~1.51s · 2.0s 이상 0회 / 게이트 부하(시뮬레이션+정밀 렌더 동시) 40회 1.17~3.64s · **2.0s 이상 4회(10%)** = 동시에 돌았는데도 프로세스 기동 지연으로 시간 기준을 넘김. 수정 후 같은 부하 40회 실패 0회(최대 1.12s · 평균 0.54s) · 하나씩 실행 3/3 잡아냄.
- 버린 대안: 시간 기준 완화(부하 최대 3.64s 라 3.0s 로 늘려도 또 실패 가능 · 기준 느슨화 = 검증 약화 D-202) · 재시도 후 통과 인정(간헐 실패를 숨김) · 검사 삭제.
- 영향 범위: `tools/verify_run_checks_offline.py` S5(+`_barrier_scripts` 도우미 · 쓰지 않게 된 `import time` 제거) · `_scripts`·S6·S7·`run_checks.py` 그대로.
- 상태: ACTIVE


### D-204 [SETTLE_STATEMENT_BATCH_DESIGN] 계약서 받기·분석 + 위탁정산서 + 셀독 정산서 = 운용 PC 18시 배치 · 모두싸인 자동 로그인 · 분석 AI = Claude API · 대상 = 판매 관련 계약만 · 연장 = 문서 자동 반영 · 구글 연동 보류 (2026-11-12, R139)
- 결정(소유자 2026-11-12, T-18 제안 v2 `docs/plans/settlement-statements-batch-T18-2026-11-12.md` 7절에 대한 답 원문: "1번 수용,2번 자동로그인, 3번 수용,4번 판매와 관련된 계약으로 한정, 다른 업무위탁이나 다른 계약은 제외, 5번은 문서 자동 반영하고 연장 인정방법에서 연장 인정 의미 설명해줘, 6번 예시 수용, 7번 수용.무두싸인 실측 수용." · 앞선 지시 "지금 구글과 연동하는 부분은 보류"):
  ① 실행 PC = 운용 PC 한 곳(계약서 받기·분석·위탁정산서·셀독 정산서 모두).
  ② 모두싸인 받기 = 전용 Chrome 프로필 + **세션 만료 때 프로그램이 저장된 비밀번호로 자동 로그인**(쿠팡 ① 과 같은 실제 Chrome + CDP 자동입력 · 비밀번호는 소유자가 앱에서 직접 입력해 DPAPI credstore 에 저장 · Claude 는 비밀번호를 넣지 않음 · 2단계 인증·CAPTCHA 는 사람) · 공식 API 는 쓰지 않음(`D:\modusign\HANDOFF.md:11` 소유자 거부 기록 유지) · 못 받은 날은 다음 실행이 소급.
  ③ 계약서 분석 AI = Claude API(키 1개 추가 · modusign 이중 판독 절차의 이어하기 모드).
  ④ 셀독 정산서 대상 = **판매와 관련된 계약만** · 업무위탁(영업 위탁·운영 대행·광고 등)·투자·위임·채권·기타 계약 제외 · 계약마다 판정은 AI + 근거.
  ⑤ 계약 연장 = 연장·변경 **문서가 있으면 자동 반영**(새 종료일). 문서 없는 연장·만료 뒤 판매 계속의 처리는 미정(설명 후 소유자 답).
  ⑥ 목표 도달율의 실적 = 쿠팡 실지급 × 계약 조건(D-152 방식).
  ⑦ 셀독 정산서 = 계약자 1명 견본 먼저 → 승인 뒤 전체.
  ⑧ 구글시트 연동(정산서·정산대장 반영) = 보류 · 산출은 엑셀만.
  ⑨ 구현 전 0단계 = 모두싸인 화면 실측(조회만 · 문서함 구조·1건 받기 이메일 발송 여부).
- 근거: 이 세션 실측 — 정산 정기 1바퀴 11-11 18:54~11-12 01:38 후 소급 계속(output(36)) · 계약 DB `D:\modusign\계약서_정밀분석\전수\계약서_정밀분석_DB_전수_v4.xlsx` '제품공급(셀독·제로셀형)' 439건(계약금액 437·수익금 305·수익률 314·계약종료일 370 · '연장' 낱말 4건) · 계약 1건당 분석 약 3.5만 토큰(163,470,201 ÷ 4,673) · 9월 받기는 Claude in Chrome 일괄 ZIP·매회 이메일(`HANDOFF.md:11·57`).
- 버린 대안: 한 번에 앱에 넣기(회귀 원인 구분 불가 D-202) · 개발 PC 반자동(18시 배치 목표 미달) · 사람 로그인 재사용만(세션 만료일마다 못 받음 — 소유자가 자동 로그인 선택) · 모두싸인 API(소유자 거부) · OpenAI 분석(정확도 미실측) · Claude in Chrome 예약(결정적이지 않음).
- 영향 범위: 구현 전(코드 변경 없음). 예정 = 제안 v2 5·6절(신규 `statement/`·`contracts/`·셀독 정산서 모듈 · `settlement_download.py` 명령 · `app_process`·`app_qt` 18:00 블록 · credstore 키 2개(모두싸인 계정·Claude API)). 단계 순서 = 0 실측 → 1 위탁정산서 이관(현행 26곳 0 차이) → 2 받기·분석 → 3 계약↔계정 연결 → 4 셀독 정산서(계약자 3명 52,432,244 재현) → 5 배치·배포(통제 세션).
- 상태: ACTIVE (부분 SUPERSEDED by D-206 — ⑤ 의 '문서 없는 연장·만료 뒤 판매 계속 = 미정' 부분 · 부분 SUPERSEDED by D-399 — ① 18시 배치 시각·⑧ 구글 연동 보류·② 모두싸인 받기 시점(보류))


### D-205 [LOGIN_PW_REFUSED_UNTIL_CHANGED] 쿠팡이 거부한 비밀번호 값 = 관리대장(정산은 원장) 값이 바뀔 때까지 다시 넣지 않음(24시간 만료 폐지) · 처리기록에 '실제 거부'와 '넣지 않음' 구분 (2026-11-12, R140)
- 결정(소유자 2026-11-12 "A안으로 진행해줘" — T-22 판정 뒤 제시한 A안 = '쿠팡이 거부한 값은 관리대장(정산은 원장) 값이 바뀔 때까지 다시 넣지 않음(24시간 만료 없음) · 고친 값은 바로 시도 · 처리기록 문구를 24시간 건너뜀/실제 거부로 나눔'): (1) `login_today` 의 거부값 지문을 시간이 지나도 풀지 않음(`BLOCK_HOURS` 삭제·`_blocked` 시간 거르기 삭제·`refused_today`/`record_success` 의 now 인자 삭제). 고친 값(다른 지문)은 지금처럼 바로 시도. (2) 넣지 않고 막을 때는 `pipeline_sales.LoginPasswordBlocked`(LoginCredentialError 하위 — 처리 흐름은 그대로) · 정산 처리기록 = 실제 거부 '비밀번호 오류 — 쿠팡이 거부·고칠 때까지 다시 넣지 않음' / 막음 '비밀번호 오류 — 전에 거부된 값이라 넣지 않음(고칠 때까지)' — 둘 다 '비밀번호 오류' 계정으로 셈(`settlement_runlog.login_problems`). (3) 안내 문구(앱 로그·[실행 결과 종합] PW_HINT) '24시간' → '고칠 때까지'.
- 근거: T-22 판정 `output\_분석_261112_T22_aehee5505\판정_결과.md`(git 밖) — output(36) 로그: aehee5505 실제 입력·거부 = 11-06 20:20 · 11-08 04:04 · 11-09 06:19 · 11-10 07:42 · 11-11 13:15(5회, 24시간 풀릴 때마다 정산이 같은 출처 값을 다시 넣음) · 그 사이 9건은 '⛔ 24시간 안' 건너뜀. plan_it·gbseller808·unipang·seankim137·wavetech 도 11-03~11-11 거의 매일 1회 실제 거부. 거부 문구 303건 모두 '아이디 또는 비밀번호가 다릅니다'(잠금·휴면 문구 0). 11-12 소유자 수동 로그인 aehee5505 = 같은 문구(값 틀림 확정) · 대조 tellace83 = 대장 값 정상 로그인. 재현: 핀 D2 '거부 뒤 25시간 지나도 막음'·'2회차 = LoginPasswordBlocked' 가 옛 코드에서 실패(옛 login_today 로 25시간 전 거부값 = 막지 않음 False 확인) → 수정 → 통과 · 정산 P55 신설.
- D-068 과의 관계: D-068(2026-10-16) 은 '같은 값만 영구 금지'를 버린 대안으로 둠(사유 '다음 날 계정 상태가 풀려도 시도 안 함 — 소유자 해당일과 다름'). 이번에 실측 근거(하루 1회씩 반복 거부)로 소유자가 뒤집음. 그 사유의 경우(값은 맞는데 계정 상태 때문에 거부 · 쿠팡 쪽 비번을 대장 값으로 되돌림)는 대장 값이 안 바뀌어 다시 시도하지 않음 → 푸는 방법 미정(STATE 미해결).
- 버린 대안: B안(24시간 유지 + 같은 값 2회 거부 시 정지 — 2회째 거부가 남음) · 24시간 유지(실측 5회 반복).
- 영향 범위: `login_today.py` · `pipeline_sales.py`(LoginPasswordBlocked·막음 문구) · `tools/settlement_download.py`(_login 기록 2종) · `pipeline.py`·`run_result.py`·`settlement_runlog.py`·`settlement_accounts.py` 문구 · 시험 `pin_login_ranks` D2 · `pin_run_plan` · `verify_settlement_runtime_offline` P54 문구·P55 신설 · `transfer_login`(셀독전환 재시도는 원래 '비번 바뀐 계정만' — 변화 없음). 운용 PC 는 새 배포본 설치 뒤부터 적용. HQ 포팅 대상(로그인 공통).
- 상태: RETIRED by D-207 (소유자 취소 · D-123 24시간 규칙 복원)


### D-206 [SELDOC_CONTRACT_EXTENSION] 셀독 정산서 계약 연장 = 문서 없어도 인정 · 만료 뒤 판매가 계속되고 관리대장에 있으면 연장으로 간주 · 제로셀도 판매 관련 계약 (2026-11-12, R141)
- 결정(소유자 2026-11-12 원문: "1.문서 없는 연장,만료 뒤에도 판매가 계속되는 경우==> 연장 인정, 연장·변경 문서--> 문서가 존재할수 있음, 그렇지만 없는 경우가 많음 2. 만료뒤 판매가 계속되고 있으고 관리대장에 존재하면 연장으로 간주. 3. 제로셀도 판매 관련임."):
  ① 연장 인정 = 계약 종료일이 지난 계약을 셀독 정산서에서 진행 중으로 봄(종료일 뒤 판매도 그 계약 실적 · 목표 도달율 계속 계산 · 상태 '진행 중(연장)').
  ② 인정 근거 두 가지: (가) 연장·변경 문서가 있으면 그 새 종료일(D-204 ⑤ 그대로) (나) **문서가 없어도** 종료일 뒤에 그 계약 품목 판매가 계속되고 계약 계정이 관리대장에 있으면 **연장으로 간주**(사람 입력·승인 없이 자동 — D-070).
  ③ 셀독 정산서 대상(D-204 ④ '판매와 관련된 계약')에 **제로셀 상품공급 계약 포함**.
- 근거: 계약 DB `D:\modusign\계약서_정밀분석\전수\계약서_정밀분석_DB_전수_v4.xlsx` '제품공급(셀독·제로셀형)' 439건 중 '연장' 낱말이 있는 계약 4건뿐(이 세션 실측) — 소유자 "없는 경우가 많음"과 맞음 → 문서만으로 판정하면 대부분 '만료'로 잘못 나옴. 설명·예시 = `docs/plans/settlement-statements-batch-T18-2026-11-12.md` 10절.
- 버린 대안: 직원이 '직원 입력' 시트에 새 종료일을 적을 때만 인정(사람 입력 대기 — 대부분 빠짐) · 만료 뒤 판매 계속을 '연장 확인 필요' 표시만(실적·도달율이 실제와 어긋남).
- 영향 범위: 구현 전(코드 변경 없음) — T-18 4단계 셀독 정산서 · 계약 관리 엑셀 '연장·변경' 시트에 근거 칸(문서ID 또는 '판매 계속·관리대장 있음 — 간주'). 간주 연장의 끝(언제 '만료'로 바꿀지)·'관리대장에 있음'의 단위(계정/상품)는 구현 때 소유자 확인(STATE 미해결).
- 상태: ACTIVE


### D-207 [LOGIN_PW_24H_RESTORED] D-205(거부값 = 관리대장 값이 바뀔 때까지 안 넣음) 취소 · D-123 '거부 시각부터 24시간 뒤 다시 넣음' 복원 (2026-11-12, R142)
- 결정(소유자 2026-11-12, A안 설명을 들은 뒤 "24시간 뒤 다시 넣음,session-close" → 선택지 'A안 취소, 24시간 규칙으로' 선택): R140(D-205)의 코드·시험·안내 문구·CURRENT_RULES·CLAUDE.md 를 R140 이전(8aad2ea)과 같게 되돌린다. 거부된 값은 거부 시각부터 24시간 다시 넣지 않고, 24시간 뒤에는 다시 넣는다(D-123). 처리기록 문구 구분(실제 거부/넣지 않음)도 함께 취소.
- 근거: 설명한 D-205 의 남는 경우 — 쿠팡 쪽 비번을 관리대장 값으로 되돌렸거나 계정 상태가 풀려도 대장 값이 안 바뀌면 다시 시도하지 않음(D-068 이 같은 이유로 '같은 값 영구 금지'를 버림). 되돌림 검증 = `git diff 8aad2ea -- src tools CLAUDE.md` 차이 0.
- 버린 대안: D-205 유지 · B안(24시간 뒤 1회 더 → 또 거부면 정지).
- 남는 위험(사실): 같은 틀린 값이 24시간마다 1번씩 들어감(aehee5505 11-06~11-11 5회 · plan_it·gbseller808·unipang·seankim137·wavetech 거의 매일) — 관리대장 비밀번호를 고치는 것(T-5)으로만 멈춤.
- 영향 범위: R140 에서 바꾼 파일 전부(되돌림) · 운용 PC 영향 없음(R140 은 배포 전).
- 상태: ACTIVE


### D-208 [SELDOC_EXTENSION_END_PRODUCT] 간주 연장의 만료 = 그 계약 상품이 관리대장에서 빠진 날 · '관리대장에 있음' = 상품 단위 · 모두싸인 일괄 받기 링크 이메일은 무시 (2026-11-12, R143)
- 결정(소유자 2026-11-12 원문: "간주 연장은 관리대장에서 빠진 날 만료, 상품 기준으로, 문서싸인 이메일 발송건은 무시해."):
  ① D-206 ②(나) 간주 연장은 그 계약 품목의 **상품 줄이 관리대장에서 빠진 날** 만료(계약 기간 끝 = 그날).
  ② '관리대장에 있음'은 **상품 단위**로 본다 — 계정이 대장에 남아 있어도 그 계약 상품이 빠지면 만료.
  ③ 모두싸인 일괄 ZIP 받기 때 나가는 링크 이메일 = 무시(막지 않음·쓰지 않음·오류로 세지 않음).
- 근거: D-206 영향 범위의 '구현 때 소유자 확인' 2건(간주 연장의 끝·계정/상품 단위)에 대한 답 · 이메일 = 일괄 ZIP 마다 1통 발송(`D:\modusign\HANDOFF.md:57`) · 1건 받기는 이메일 없음(소유자 확인 "메일함 확인했는데 모두싸인 메일 안 왔음", 실측 문서 `docs/plans/modusign-live-check-T18-2026-11-12.md`).
- 버린 대안: 계정 단위(계정만 남으면 연장 계속 — 상품이 빠져도 실적이 이어짐) · 판매가 끊긴 뒤 N일 만료(판매 일시 중단과 구분 불가).
- 영향 범위: 구현 전(코드 변경 없음) — T-18 4단계 셀독 정산서·계약 관리 엑셀 '연장·변경' 시트. (Claude 해석·구현 때 확인) 판매중지(숨긴 행·취소선 D-082)는 대장에 남은 것이라 '빠짐' 아님 · 빠진 날 = 원장 상품이력(D-100)에서 그 상품이 대장에서 사라진 실행 날짜.
- 상태: ACTIVE


### D-209 [MODUSIGN_DAILY_DOWNLOAD] 모두싸인 계약서 받기 = 앱 실행일 + 못 받은 날 소급 · 그 범위 서명 완료 문서를 100건씩 전체 선택 일괄 ZIP · 다운로드 폴더 파일 사용(메일함 안 씀) · 다중 로그인 창 = '그래도 로그인하기' 자동 (2026-11-12, R143)
- 결정(소유자 2026-11-12, T-18 0단계 실측 세션 `local_426fdd96` 의 소유자 입력 원문 — 그 세션 기록에서 대조함):
  ① "메일함 확인했는데 모두싸인 메일 안 왔음 ==> 메일함 사용하지 말고 다운로드 받아서 다운로드 폴더에 생성된 파일을 사용해야 함." → 받은 파일 = Chrome 다운로드 폴더에 생긴 파일 · 메일 링크 안 씀.
  ② "1.그래도 로그인하기'를 자동으로 눌러 다른 사람의 로그인을 끊어야  해." → 자동 로그인(D-204 ②) 중 다중 로그인 감지 창이 뜨면 '그래도 로그인하기'를 자동으로 누름(같은 계정의 다른 브라우저 로그인은 끊김).
  ③ "2.기간을 정해서 모두 다운받으면 됨." → 문서ID 단위 대조 없이 날짜 범위의 서명 완료 문서를 전부 받음 · 모두싸인 내부 목록 데이터는 읽지 않음.
  ④ "당일에 있는 모든 계약을 한번에 받아줘, 최대 100개를 화면에 보여고 전체 선택하면 100건까지 받을수 있음." → 범위 목록을 100건 표시 → 전체 선택 → 상단 '다운로드' → 일괄 ZIP · 100건 넘으면 다음 100건 반복.
  ⑤ "당일은 앱이 실행되는 날짜를 의미함. 그 이전것과 특정 사유로 다운을 못한경우 소급해서 해야 함." → 범위 = 앱 실행일(한국 날짜) + 그 전에 못 받은 날 전부 · 날짜별 받기 성공 기록.
- 근거: 실측 문서 `docs/plans/modusign-live-check-T18-2026-11-12.md`(화면 구조·주소 인자 `dateRangeFrom`/`dateRangeTo`·다중 로그인 창·1건 받기 이메일 없음) · 9월 일괄 받기 절차 `D:\modusign\HANDOFF.md:19-31`.
- 버린 대안: 1건씩 받기(이메일 없음·하루 평균 약 0.4건 — 소유자가 일괄 선택) · 문서ID 단위 이어받기(소유자 '기간 전부') · 배치 전용 멤버 계정(소유자가 자동 끊기 선택) · 모두싸인 API(소유자 거부 `HANDOFF.md:11`).
- 영향 범위: 구현 전(코드 변경 없음) — T-18 2단계 [A] 받기. 구현 때 정할 것(Claude 판단·소유자 지시 아님): 날짜 기준 = 체결일(`FINISHED_AT`) 권장 · 처음 범위 시작 = 2026-09-06(9월 전체 받기 끝) · 겹쳐 다시 받은 파일 = SHA-256 같은 것 제외 · 일괄 옵션 = 9월 값(체결본 PDF·첨부 받음·감사추적 뺌·문서마다 폴더)이며 2026-11 화면 흐름은 미확인.
- 상태: ACTIVE (부분 SUPERSEDED by D-212 — 영향 범위 '구현 때 정할 것'의 처음 범위 시작 2026-09-06 → 2026-03-20)


### D-210 [SETTLE_STATEMENT_NO_STATUS_SKIP] 정산 받기 = 관리대장 상태(취소선·숨김·대장에서 빠짐)와 상관없이 로그인해 자료가 있으면 받음 · 정산서 실적 = 상태가 바뀐 그날 판매분까지 포함 (2026-11-12, R144)
- 결정(소유자 2026-11-12 원문 — D-208 의 Claude 해석 '판매중지(숨긴 행·취소선)는 빠짐 아님 · 빠진 날 = 원장 상품이력에서 사라진 날'에 대한 답: "무조건 로그인해서 자료가 있으면 다운받아야 함, 오늘오전까지 판매가되었고, 야간 배치 시점에 취소선으로 남는 것이 있을수 있음."):
  ① 18시 배치의 정산 자료 받기는 그 계정·상품의 관리대장 상태(취소선·숨김·대장에서 빠짐)로 거르지 않는다 — 로그인해서 받을 자료가 있으면 받는다.
  ② 위탁정산서·셀독 정산서 실적 = 배치 시점에 취소선·숨김·대장에서 빠짐이 된 상품도 **그날까지의 판매분**과 그 판매분으로 뒤에 들어오는 지급을 넣는다(상태가 바뀐 날 = 실적에 포함되는 마지막 날).
- 근거(사실·코드 읽기): ① 은 현행 정산 받기가 이미 그렇게 함 — 정산 계정 = 최근 90일 안에 하루라도 관리한 계정(관리중단 포함 · `settlement_accounts.py:140-172` · `KEEP_DAYS = 90` `:122`) · 계정 정지(취소선)·대장에서 계정 삭제도 원장에 '관리중단'으로 남아(`registry.py:101` "대장에서 계정 삭제") 90일 동안 받음 · 받기는 계정 단위라 상품 상태와 무관 → **코드 변경 없음**.
  ② 과 어긋나는 곳(사실·코드 읽기 · 실제 자료로 재현 전): 현행 위탁정산서의 관리 상품 = 결과 엑셀 사업자 시트 블록(`statement_managed.py:69·218` → `workbook_sales.py:48-55`) · 취소선·숨김 상품은 판매중지 블록으로 남지만, **대장에서 줄이 사라진 상품은 결과 블록이 이력째 지워져**(`workbook_lifecycle.py:44-50` 항목⑥) 그 상품 판매분 전체가 정산서에서 빠짐 · 계정 줄이 전부 사라진 계정도 같음(결과 이력 완전 삭제 · `docs/OPERATIONS_POLICY.md:14`).
- 버린 대안: 배치 시점 대장 상태로 받기·실적 대상을 거름(그날 오전 판매분이 빠짐 — 소유자 지적).
- 영향 범위: 구현 전 — T-18(T-25) 1단계에서 위 어긋남을 실제 자료로 확인(대장에서 지운 상품이 있는 계정의 정산서 값) · 4단계 셀독 정산서. (Claude 제안·소유자 승인 전) 관리 상품 출처를 결과 엑셀 대신 원장 상품이력(D-100 · 관리 기간 포함)으로 바꾸는 안. (미확인·소유자 확인 필요) 취소선(판매중지)이 된 날을 D-208 간주 연장의 만료로도 볼지 — 다시 판매 재개(취소선 해제)되면 연장이 이어지는지.
- 상태: ACTIVE


### D-211 [SETTLE_ACCOUNTS_NO_TIME_LIMIT] 정산 받기 계정 = 한 번이라도 관리한 계정 전부(관리중단 90일 제한 폐지) · 취소선이 있어도 쿠팡이 주는 자료는 모두 받음 (2026-11-12, R145)
- 결정(소유자 2026-11-12 원문: "취소선이 있더라도 정산에서는 쿠팡이 제공하는 모든 자료를 다운 받아야 함." · 90일 제한을 둘지 묻자 "90일 제한 없애고 자료 있으면 계속 받아"):
  ① 정산 받기 대상 = 셀독원장에서 한 번이라도 관리한 계정 전부(관리중 + 관리중단 · 기간 제한 없음) − 오입력 + 정산전용계정 시트의 모든 줄(관리중·관리중단).
  ② 취소선(계정 정지·상품 판매중지)·숨김·대장에서 빠짐은 정산 받기를 막지 않는다 — 받을 자료가 있는지는 쿠팡 화면·응답이 정함(D-210 ① 과 같음).
- 근거: 바꾸기 전 규칙 = `settlement_accounts.accounts_from_registry` 의 `KEEP_DAYS = 90`(관리중단 뒤 90일 지나면 제외 · D-103) · 정산 받기 코드에서 계정을 거르는 곳은 이 하나뿐(`tools/settlement_download.py`·`settlement_*`·`transfer_*` 검색) · D-199 계정 정지 건너뛰기는 판매 수집(`pipeline_sales`·`pipeline`)에만 있고 정산 받기에는 없음(`account_suspend` 를 정산 쪽에서 안 씀).
  시험: P37(`tools/verify_settlement_runtime_offline.py`)의 기대값을 먼저 바꿔 실패 확인(중단 112일 old1·173일 gone1 빠짐) → 코드 수정 → 통과.
- 버린 대안: 90일 유지(그 뒤 보류금 해제·늦은 지급이 빠질 수 있음 — 소유자 거부) · 기간 늘리기.
- 남는 영향(사실·추정 구분): (추정·코드 근거) 원장 관리 기간은 첫 동기화 날짜(2026-10월)부터 시작하므로(`registry_history.managed_between` · K_INIT 날짜) 지금은 90일 넘은 관리중단 계정이 없어 당장 대상이 늘지 않음 — 운용 PC 원장으로 확인 전. (추정) 2027-01 무렵부터 관리중단 계정이 쌓일수록 매일 로그인 계정 수가 늘어남. hide4u 같은 정지 계정은 D-194 의 '90일 뒤 자동 제외'가 없어져 매 회차 받기 500 이 계속 남음.
- 영향 범위: `src/coupang_analytics/settlement_accounts.py`(KEEP_DAYS·keep_days 인자 삭제·정산전용 시트 중단일 조건 삭제) · `tools/settlement_download.py`(설명 문구) · 시험 P37. 운용 PC 반영 = 통제 세션 배포 zip 뒤. HQ 포팅 대상(D-103 과 같음).
- 상태: ACTIVE


### D-212 [SELDOC_MATURITY_VS_END] 취소선 = 내부 판매중지(만기·계약 종료 아님) · 만기 ≠ 계약 종료 — 만기는 연장될 수 있고, 관리대장에서 상품이 삭제되면 계약 100% 종료 · 모두싸인 첫 받기 = 2026-03-20부터 (2026-11-12, R146)
- 결정(소유자 2026-11-12 원문 — D-210 의 '취소선이 된 날을 간주 연장 만료로도 볼지·판매 재개 때 연장이 이어지는지' 질문에 대한 답: "취소선은 만료 아님, 해당 상품은 내부적으로 판매를 중지한다는 의미임, 쿠팡에도 중지해야 하지만 중지를 안하는 경우도 있음, 계약 만료와는 다른 의미임. 계약이 만료되어도 상당 기간은 유지 하다가 관리대장에서 삭제되므로 관리대장에서 삭제되어 없으면 계약이 100% 종료임, 만기와 계약 종료는 서로 다름, 만기가 연장될수도 있음."):
  ① 관리대장 취소선(판매중지 · 숨긴 행 포함 D-082) = **우리 쪽 내부 판매중지 표시**. 만기도 계약 종료도 아니다 — 쿠팡에서는 판매가 계속될 수 있으므로 그 판매분은 실적에 넣는다(D-210 ②). 취소선을 풀어도 계약 상태는 바뀌지 않는다(처음부터 끝난 적 없음).
  ② **만기 ≠ 계약 종료**. 만기 = 계약서의 종료일 — 연장될 수 있다(연장 문서가 있으면 그 종료일 · 없어도 만기 뒤 판매 계속 + 관리대장에 상품이 있으면 연장 간주 D-206). **계약 종료 = 그 계약 상품이 관리대장에서 삭제된 날**(D-208 의 '빠진 날') — 이때는 100% 종료. 만기가 지나도 상당 기간 대장에 남아 있다가 삭제되는 것이 보통.
  ③ 모두싸인 계약서 첫 받기(T-18 0단계 실측 세션 `local_426fdd96` 의 소유자 입력 원문 — 그 세션 기록 검색으로 대조함: "처음 실행할때에는 2026.3.20부터 받습니다. 문서싸인에서 검색조간을 실행하는 날짜로 하고 검색된 계약서를 다운받으면 됨."): 첫 실행 = **2026-03-20 ~ 실행일** · 이후 = 문서함 날짜 검색 조건을 실행일로(+ 못 받은 날 소급 D-209 ⑤) · 검색된 계약서 전부 일괄 ZIP.
- 근거: 소유자 답 · D-208 영향 범위의 Claude 해석('판매중지는 대장에 남은 것이라 빠짐 아님')과 같은 방향 · 실측 결과 `docs/plans/modusign-live-check-T18-2026-11-12.md` 6절 5번.
- 버린 대안: 취소선 날 = 만기(쿠팡 판매가 이어지는 경우 실적이 끊김 — 소유자 거부) · 첫 받기 시작 2026-09-06(D-209 영향 범위의 Claude 판단 — 소유자가 2026-03-20 으로 정함).
- 영향 범위: 구현 전(코드 변경 없음) — T-18(T-25) 2단계 받기(첫 범위 · 2026년 체결 559건 중 3/20 이후 수백 건 → 100건씩 여러 번 · 일괄마다 링크 이메일 1통은 무시 D-208 ③ · Claude API 분석 첫 회 비용 = 계약당 약 3.5만 토큰 × 건수) · 4단계 셀독 정산서 상태 칸 = '진행 중 / 만기 지남(연장 중) / 계약 종료' 구분.
- 상태: ACTIVE


### D-213 [MODUSIGN_CONTRACT_EXCEL_BUILD] 모두싸인 검색 날짜 = 체결일 · 계약 관리 엑셀 = 첫 실행 전 정밀 분석으로 한 번 만들고 매일 받은 계약서만 행 추가 · 엑셀 대상 = 판매 관련 계약만 (2026-11-12, R147)
- 결정(소유자 2026-11-12, T-18 0단계 실측 세션 `local_426fdd96` 의 소유자 입력 원문 — 그 세션 기록 검색으로 대조함):
  ① "체결일 기준으로 해" → 문서함 검색 = 체결일(`dateFilterType=FINISHED_AT`) + `dateRangeFrom`/`dateRangeTo`.
  ② "첫 실행전에 계약서를 정밀분석해서 엑셀파일로 생성하여 놓고 매일 실행시 계약서가 존재하는 생성된 엑셀파일에 추가함." → 첫 실행 전 1회: 이미 있는 계약서(9월 받은 `D:\modusign\downloads` 분 + 2026-03-20 이후 분 D-212 ③)를 정밀 분석해 계약 관리 엑셀을 만든다 · 매일: 그날(+소급) 받은 계약서가 있으면 분석해 **그 엑셀에 행 추가**(새로 만들지 않음) · 받은 계약서가 없는 날은 엑셀을 건드리지 않음.
  ③ "판매 관련 건만 대상입니다." → 정밀 분석·매일 추가 모두 판매 관련 계약만 엑셀에 넣음(D-204 와 같음 · 제로셀 포함 D-206) · 계약서마다 AI 가 판매 관련 여부를 판정하고 근거를 남김.
- 근거: 실측 결과 `docs/plans/modusign-live-check-T18-2026-11-12.md` 6절 6~8번 · 라벨은 대부분 비어 있어 분류에 못 씀(같은 문서 6절 끝) → AI 판정 필요.
- 버린 대안: 요청일·수정일 기준 검색 · 매일 엑셀 새로 만들기.
- 영향 범위: 구현 전(코드 변경 없음) — T-18(T-25) 2단계 [B] 분석. (Claude 판단·소유자 지시 아님) 판매와 관련 없는 계약도 받아 두기는 함(엑셀에만 안 넣음) · 정밀 분석 때 이미 있는 계약 DB v4(`D:\modusign` · 계약당 약 3.5만 토큰 사용분)를 다시 쓸 수 있는지 먼저 확인.
- 상태: ACTIVE
### D-214 [SETTLE_ALL_COUPANG_DATA] 대원칙 — 판매·정산 관련 쿠팡 제공 자료(마케팅 비용 포함)는 100% 받고, 받은 자료를 분석해 정산 파일을 만든다 (2026-11-12, R148)
- 결정(소유자 2026-11-12 원문, T-24 세션 대화 — 통제 세션 기록 지시 "통제 세션에 넘겨줘"): "모든 판매와 정산과 관련 제공자료는 100% 다운받음(대원칙)" · "마케팅 비용 등 모든 쿠팡이 제공하는 100% 자료 다운받음. 그리고 다운 받은 자료를 분석해서 정산 파일을 생성함."
  ① 쿠팡(윙·로켓그로스·광고센터 등)이 주는 판매·정산 관련 자료는 종류를 가리지 않고 모두 받는다(마케팅 비용 포함) · 받는 목록에 없는 자료 = 누락(오류).
  ② 정산 파일(위탁정산서·셀독 정산서)은 받은 자료를 분석해서 만든다(받지 않은 자료로 추정하지 않음 — D-081·CURRENT_RULES §13 과 같음).
- 근거(이미 드러난 누락 — T-24 세션 실측·근거 파일 `D:\coupang-analytics\output\_분석_261112_T24_gorocket23\정산정책_대조.md`·`윙_실측_261112.txt`):
  ⓐ gorocket23 로켓그로스 월자료 3종(RG 재고변동·RG 반품내역·RG 부가세 상세) 0건 — 로켓그로스 계정 판정 `settlement_docs.vendor_from_snapshots`(정산현황 원문 settlementGroupKey 앞부분 · 원문에 줄이 없으면 '' = 윙 전용)를 `tools/settlement_download.py` `request_docs`·`collect_docs` 가 씀 → 2026-07부터 로켓그로스 정산 줄이 0건인 gorocket23(실제 로켓그로스 업체코드 A01152633·입고 11건)을 윙 전용으로 판정(코드 확인 = 통제 세션 · 0건 = T-24 실측). 같은 판정으로 빠진 계정 전수 확인 필요.
  ⓑ 로켓그로스 입고·회송 기록(입고 ID·수량·회송 사유·송장 — 윙 `/tenants/rfm-inbound/inbound/list`·`/lightning/summary?id=`)이 받는 목록(`designs/SETTLEMENT_MODULE.md` §16-2 N1~N13)에 없음.
  ⓒ 주문별 매출 2026-01~04 못 받음(T-2).
- 버린 대안: 정산서에 쓰는 자료만 골라 받기(쓰지 않는 자료가 나중에 대사에 필요할 수 있음 — 소유자 대원칙).
- 영향 범위: 구현 전(코드 변경 없음) — ⓐ 로켓그로스 계정 판정 보강 + 전수 확인 · ⓑ 입고·회송 받기 신설 · ⓒ T-2 · '쿠팡 제공 자료 전체 목록 ↔ 받는 목록' 전수 대조. 레인 E(정산) · HQ 포팅 대상.
- 상태: ACTIVE (구현 전)

### D-215 [SETTLE_SUSPENDED_STILL_DOWNLOAD] 계정 정지(승인 반려) 계정도 정산 자료는 받는다 — D-199 의 '건너뛰기'는 판매 수집에만 (2026-11-12, R148)
- 결정(소유자 2026-11-12 원문, T-24 세션): "계정정지도 다운받음으로 결정함." · D-199 상태 줄 표기안(`ACTIVE (부분 SUPERSEDED by D-211 — 정산 받기는 건너뛰지 않음 · 판매수집 건너뜀·대장 취소선은 그대로)`)에 "승인".
  ① 계정 정지로 판정된 계정도 18시 정산 받기는 그대로 한다(받을 자료가 있는지는 쿠팡 응답이 정함 — D-211 ②) · ② 판매 수집 건너뛰기·관리대장 계정아이디 취소선 표기(D-199)는 그대로.
- 근거: D-211 근거 — D-199 건너뛰기는 `pipeline_sales`·`pipeline` 에만 있고 정산 받기(`tools/settlement_download.py`·`settlement_*`)에는 없음 · gorocket23 은 매 회차 정산 로그인·조회·검증 정상(T-24 `정산정책_대조.md` 일치 항목).
- 버린 대안: 정지 계정은 정산도 건너뛰기(정지 뒤 보류금 해제·늦은 지급이 빠짐 — D-214 대원칙과 어긋남).
- 영향 범위: 코드 변경 없음(정산은 이미 D-211 대로) · D-199 상태 줄 표기만.
- 상태: ACTIVE

### D-216 [STATS_BOTH_SHIPPING_SUM] 로켓그로스+판매자배송을 같이 파는 상품 — 계정 통계 시트 판매·노출·방문 = 두 방식 합계 · ③ 순위 = 두 VID 중 하나라도 나오면 그 등수 (2026-11-12, R148)
- 결정(소유자 2026-11-12 원문, T-24 세션): 배경 "11월부터 3PL로 제고를 이동시켰어. 그래서 로켓그로스와 판매자배송이 같이 존재함." · 통계 시트 기준 3안(현행 유지 / 안내 표시 / 기준 통일) 중 "③으로"(= 기준 통일).
  ① 같은 상품에 로켓그로스(RFM)·판매자배송(NORMAL) 옵션이 같이 있으면 계정 통계 시트 블록의 판매·노출·방문 = 두 방식 합계.
  ② ③ 순위 = 두 VID 중 하나라도 검색 결과에 나오면 그 등수 — VID 매칭 유지·상품명 폴백 없음(D-030 그대로).
  ③ 2026-09-20 규칙 '둘 다 있는 상품은 로켓그로스 옵션만 VID·판매 통계로 채택'(`designs/DESIGN.md:108` · `collector.py` `products_from_vendor_inventory` 887~889줄 docstring · D번호 없음)을 이 결정으로 바꾼다.
- 근거: gorocket23 실측(T-24 `판정_결과.md`) — 로켓그로스 옵션 9-20부터 재고 0(09-24 입고 28개 전부 회송) · 판매자배송 판매 10.11~11.10 13개·278,500원(윙 원자료 = 통합판매현황 날짜별 일치) → 옛 규칙으로는 통계 시트가 매일 판매 0·순위 '50위밖'(정산·통합판매현황은 D-107 로 판매자배송 포함이라 정상).
- 버린 대안(T-24 `정산정책_대조.md` C5 의 세 안 중 나머지 둘): ① 현행 유지(로켓그로스 옵션만 — 3PL 이동 뒤 실제 판매가 통계 시트에 안 보임) ② 통계 시트에 '판매자배송 판매는 통합판매현황·정산서에 포함' 안내만 표시.
- 영향 범위: 구현 전 — 레인 A(`collector.products_from_vendor_inventory`·`pipeline_sales`) · C(`pipeline_ranks._rank_matcher` 에 두 VID) · G(통계 시트 블록). 구현 전 확인할 것(Claude 판단·소유자 지시 아님): ⓐ D-041(추적 VID 와 같은 리스팅·같은 옵션의 다른 배송방식 VID 블록 삭제)과 겹침 — 판매자배송 VID 가 추적 대상이 되면 그 규칙의 대상이 달라짐 ⓑ 재고칸(로켓그로스 재고현황 `orderableQuantity`·0 = 입고됐지만 품절 · DESIGN.md:100)과 판매자배송 재고(회사보유재고·3PL)를 블록에서 어떻게 보일지 ⓒ 관리대장 그로스 재고 역기록(D-047·D-048)은 로켓그로스 재고만 그대로인지 · 핀 시나리오 = 로켓그로스 품절 + 판매자배송 판매 / 로켓그로스 재고 있는 '둘다' 계정 회귀 없음. HQ 포팅 대상.
- 상태: ACTIVE (구현 전)


### D-217 [SETTLE_STATEMENT_IMPL_CHOICES] 정산서 배치 구현값 승인 — 관리 상품 출처 = 원장 상품이력 · 계약서 중복 = SHA-256 같으면 제외 · 판매 무관 계약 = 받아 두기만(엑셀 제외) · 모두싸인 일괄 받기 화면 = 9월과 같음 (2026-11-12, R149)
- 결정(소유자 2026-11-12 원문 — T-18 세션이 '확정 전 사항(Claude 판단)'으로 보고한 4건에 대한 답):
  ① "관리 상품 목록을 결과 엑셀 대신 원장의 상품 변경 기록에서 가져오는 방안 ==> 승인" → 위탁정산서·셀독 정산서의 관리 상품 = 셀독원장 상품이력(D-100 · 관리 기간 포함) · 결과 엑셀 블록(`workbook_sales.managed_vids`)을 쓰지 않음 → 대장에서 지운 상품도 관리 기간 판매분이 남음(D-210 ② 의 어긋남 해소 방향).
  ② "겹쳐 다시 받은 계약서 파일은 내용(SHA-256)이 같으면 빼기 ==> 승인" → 날짜 범위가 겹쳐 다시 받은 계약서는 파일 SHA-256 이 같으면 한 번만 둠(9월 받은 `D:\modusign\downloads` 분 포함).
  ③ "판매와 관련 없는 계약도 받아 두기만 하고 엑셀에는 넣지 않기 ==> 승인" → 업무위탁·투자·위임·채권·직원 관련 등도 받기는 하고 계약 관리 엑셀에는 넣지 않음(D-213 ③).
  ④ "모두싸인 일괄 받기 화면이 11월에 바뀌었는지는 아직 확인하지 않음 ==> 변경없음" → 일괄 ZIP 흐름 = 9월 방식(`D:\modusign\HANDOFF.md:19-31` · 체결본 PDF·첨부 받음·감사추적 뺌·문서마다 폴더) 그대로 구현.
- 근거: 소유자 답 · D-209·D-210·D-213 영향 범위의 Claude 판단 항목.
- 버린 대안: 결과 엑셀 블록 유지(대장에서 지운 상품 판매분이 빠짐) · 파일 이름으로 중복 판정 · 판매 무관 계약 받지 않기 · 11월 화면 재실측.
- 영향 범위: 구현 전(코드 변경 없음) — T-25 1단계(현행 26곳 대조는 지금 방식 그대로 맞춘 뒤 관리 상품 출처 변경은 별도 커밋 · 바뀐 값 목록 보고) · 2단계 받기·분석.
- 상태: ACTIVE (부분 SUPERSEDED by D-222 — ① 관리 상품 출처 '원장 상품이력' → 계정의 쿠팡 등록 로켓그로스 상품)


### D-218 [SELDOC_PERF_SALES_VS_SETTLE] 셀독 정산서의 쿠팡 실적 = 판매실적과 정산 자료를 따로 나란히 표시(합치거나 하나로 대신하지 않음) (2026-11-12, R150)
- 결정(소유자 2026-11-12 원문 — 통제 세션 대화, 연다인 견본을 본 뒤 6번 항목 · 그 세션 기록 검색으로 대조함: "쿠팡 실적은 판매실적과 정산은 별개임, 실적을 표현할때에는 쿠팡 판매실적과 정산 자료도 표현되어야 함,"):
  ① 쿠팡 판매실적(판매분석 기준 판매금액·판매수량 등)과 정산 자료(입금 완료·입금 예정·보류·보상)는 **별개**다.
  ② 셀독 정산서(계약별·계정 합계)의 실적 칸에는 두 묶음을 **따로 나란히** 보인다 — 더해서 하나로 만들거나 한쪽으로 다른 쪽을 대신하지 않는다.
- 근거: 소유자 원문 · 견본 1차(`D:\토탈셀러\쿠팡 정산 자료\셀독정산서_견본_연다인_20261103기준_261112_143537.xlsx`)의 '실적' = 정산 기준(D-152 쿠팡 실지급 × 계약 조건 13,063,096원) 하나뿐이었고 판매금액은 계약 배정 칸에만 있었음.
- 버린 대안: 실적 = 정산 기준 하나만(견본 1차) · 판매금액 하나만.
- 영향 범위: 구현 전(코드 변경 없음) — T-18(T-25) 4단계 셀독 정산서 양식 · 견본 2차(새 파일). (미해결 · 소유자 답 전) 목표 도달율이 어느 실적을 쓰는지·분모(계약금액+목표수익금 vs 목표수익금)·실적 범위(계약 품목 vs 5월 이후 등록 상품 전체 D-152)·제로리스크 확정지급 10건을 대상에 넣을지 — 이 결정으로 정해진 것 아님.
- 상태: ACTIVE

### D-219 [STATEMENTS_IN_REPO] 위탁정산서 코드 = 저장소 이관(전부 `src` · 분해) · 고정 경로 → 인자 · 손 입력 7종 → 입력 폴더 고정 이름 · 현행 26곳과 칸 값 차이 0 (2026-11-12, R152)
- 결정(소유자 2026-11-12 — 이관 계획(`docs/plans/T25-step1-statements-migration-2026-11-12.md`)의 'A안(큰 2개는 분해 없이 tools) / B안(지금 분해해 전부 src)' 질문에 원문 "B안."):
  ① git 밖 `output\_분석_261013\정산스크립트\` 본체(statement_managed·business_statements·managed_alloc·settlement_ledger·experience·additional_pay)와 입구 `run_contract_window.py` 를 `src/coupang_analytics/` 로 옮기고 괴물함수를 나눔(계산식·순서 그대로): `settlement_statement_source`(정산집계·계정→사업자·미정산) · `settlement_statement_context`(입력·공통 자료·계약 기간 보강) · `settlement_statement_account`·`settlement_statement_deduct`(계정 계산 1·2부) · `settlement_statement_sheets`·`settlement_statement_book`(엑셀) · `settlement_statements`(입구 run) · `settlement_ledger`·`settlement_managed_alloc`·`settlement_experience`·`settlement_additional_pay`. 명령 = `tools/settlement_statements.py`.
  ② 손 입력·AI 판정표 = 입력 폴더(기본 `output/정산서/입력/`) 고정 이름 — 사업자_대응표.csv · 체험단_보충.json · 쿠팡_별도보상.json · 관리시작달_차이표.xlsx · svc_digital_judge.json · ledger.json(없으면 ❌ 시작 전 중단) + contract_window_scope.json(선택 · 없으면 보강 없음 로그). 장부 기준일·관리기준 output·정산 폴더·정산집계·발행일 = 인자. 옛 기본값(정산서입력_output24) 없앰.
  ③ 원장 '정산전용상품' 시트 = 지금처럼 구글 실시간 읽기(기본) · `--settle-only <json>` 사본을 주면 그것만(대조·시험용).
- 근거(실측 · `D:\coupang-analytics\output\_분석_261112_T25_이관대조\`): output(30)·기준일 2026-11-03·같은 입력·같은 시트 사본으로 옛 코드(A) ↔ 새 코드(B) = 27개 파일 칸 값 차이 0 · 서식 차이 0 · 병합 같음(`대조_A_vs_B.md`) · 실행 로그 같음(26곳 · 정산서 없음 11 · 28/35).
  A ↔ 현행 `위탁정산서_20261103기준_관리상품_output30_D186_판매0달제외` = 발행일 칸 26 + 니코에이블·벅스 D-200 문구(시트 이름 '체험단'→'외부 마케팅 대행비'·문구 2칸)뿐 · 금액 차이 0(`대조_D186_vs_A.md`). B 검산 = 독립 검산 26/26 · '추정' 0 · 합계 6항목 현행과 같음(`검산_B_vs_D186.txt`).
  품질 지수(radon): 옛 statement_managed·business_statements MI 0.0(C) · 괴물함수 account CC 167 → 새 11개 MI 전부 A · CC 21 이상 함수 0.
- 버린 대안: A안(큰 2개 `tools/` · 분해 다음 — 소유자 'B안') · `check_complexity.KNOWN_BAD` 에 추가(게이트 약화 D-202).
- 영향 범위: 새 파일 = 위 src 11 + `tools/settlement_statements.py`·`tools/check_settlement_statements.py`(실출력 검산·게이트 밖)·`tools/verify_settlement_statements_offline.py`(옛 시험 3종 본문 그대로 + 이관 입구 · `run_checks` quick 등록). 원본 폴더는 그대로 둠(분석 스크립트 34개가 import · 백업 `_백업\T25이관전\`). 옛 양식(business_statements `main` — 사업자별 정산내역·전체계정_위탁정산서)은 관리상품 정산서 흐름이 쓰지 않아 옮기지 않음(원본 폴더에서 계속 실행 가능). 앱·배포 zip 변경 없음(5단계 `statements` 명령 전). 다음 = D-217 ① 관리 상품 출처 변경(별도 커밋).
- 상태: ACTIVE
### D-220 [RANK_CATCHUP_MISSED_DAY] 직전 실행이 ③ 순위를 못 끝냈으면(단계 기록이 지난 날짜 'sales'·'ranks') 다음 실행에서 오늘 ③·재고 역기록 뒤 그날 칸 ③ 을 1회 더 (2026-11-12, R153)
- 결정(소유자 2026-11-12 원문: "재발 방지는 (가)로" — 통제 세션이 낸 안 (가) "다음 날 실행 때 어제 단계 기록이 '완료'가 아니면 어제 칸의 ③ 순위를 자동으로 채움" · (나) "지금처럼 경고만·사람이 날짜 지정으로 채움"):
  ① 전체실행·18:00 무인·재부팅 복구(`run_stages`)가 시작할 때 마지막 단계 기록(`output/쿠팡데이타분석_실행단계.json`, 날짜 무관)을 읽어, 날짜가 오늘보다 앞이고 단계가 'sales'(① 끝)·'ranks'(② 끝)면 그날을 '못 끝낸 날'로 본다.
  ② 오늘 ③ · 재고 역기록 · 빈 칸 재시도(D-173)가 다 끝난 뒤 그날 날짜 칸으로 ③ 을 1회 돈다(채운 칸은 건너뛰어 빈 칸만 검색) → 끝나면 오늘 단계 기록 'done'.
  ③ 하지 않는 경우: 그날 'done'·기록 없음·오늘 날짜 기록(재부팅 복구 D-032 몫) · 날짜 지정 실행(D-016) · ③ 을 안 도는 실행(① 단독 등) · 중지 요청.
  ④ 실행 결과 종합의 ③ 요약은 오늘 실행 값 그대로 · 그날 칸 결과는 별도 줄 '[③ 월.일 칸] 측정 N건 · 남은 빈 칸 N개'.
- 근거: 11-11 실측(`C:\Users\user\Downloads\output (36).zip` run_log_261111_181725 2530~2551줄 · `D:\coupang-analytics\output\_분석_261112_output36\분석_결과.md`) — ② 오류(T-21)로 ③ 미실행 · 단계 기록 `{"date":"2026-11-11","stage":"sales"}` · 11-12 09:31 재부팅 복구 = "오늘 이어서 할 중단 작업이 없습니다"(D-032) → 11-11 순위 칸이 빈 채 남음. 시험: `tools/pin_run_plan.py` P12(어제 sales·ranks → 오늘 ③ 뒤 어제 칸 ③ 1회 · done·기록 없음·오늘 기록·날짜 지정·① 단독 = 안 함) 옛 코드 실패 → 통과.
- 버린 대안: (나) 경고만·사람이 날짜 지정(소유자 선택 아님) · 재부팅 복구(D-032)를 어제 진행분까지 이어받게 바꾸기(D-032 실측 사고 — 옛 칸 진행분을 이어받아 오늘 칸이 안 생김 — 재발 위험).
- 남는 영향(Claude 판단·소유자 지시 아님): 그날 칸 순위는 다음 날 검색한 값(그날 실제 순위가 아님) · 검색 수가 늘어 프록시 IP 사용·실행 시간이 늘어남(빈 칸 수만큼 · 검색 간격 45~75초) · 재부팅 복구가 다음 날 아침에 뜨면 그 실행은 계획이 없어(D-032) 채우지 않고, 그날 18:00 실행이 채움.
- 영향 범위: `src/coupang_analytics/pipeline_stages.py`(`_missed_rank_day`·`_catch_up_missed_ranks`·`run_stages`) · `pipeline_paths.read_last_run_stage` · `tools/pin_run_plan.py` P12. D-032 는 그대로(① 진행분 이어받기 규칙). 운용 PC 반영 = 배포 zip 뒤. HQ 포팅 대상.
- 상태: ACTIVE (부분 SUPERSEDED by D-248 — ① 마지막 기록 하루 → 최근 7일 안 못 끝낸 날 전부 · ④ 종합 빈 칸에 보충 칸 포함)


### D-221 [SELDOC_STATEMENT_ONE_PAGE] 셀독 정산서 = 계약자 송부용 1장 요약(계약 내용 + 쿠팡 판매·정산 요약 · 세부는 위탁정산서) · 목표 도달율 분모 = 계약금액 + 목표수익금 · 실적 범위 = 그 계정의 쿠팡 등록 로켓그로스 상품(판매자배송 겸용분 포함) (2026-11-12, R154)
- 결정(소유자 2026-11-12 원문 — 이 세션(T-18) 대화, 연다인 견본 1·2차를 본 뒤):
  ① "도달율 분모는 계약금액+목표수익금으로 해" → 목표 도달율 = 정산 기준 실적 ÷ (계약금액 + 목표수익금).
  ② "셀독 정산서는 간략하게 표현되어야 함. 계약자에게 송부해야 하는데 내용이 조잡하고 많은 정보가 있으면 이해 하기 어려줘, 시각적으로 직관적이어야 함. 세부 내용은 위탁 정산서에 판매와 정산이 있고, 셀독정산서에는 쿠팡 정산/판매 요약부분과 계약내용이 정리되면 됨. 다시 해줘.1개 시트로 해줘." → 셀독 정산서 = 시트 1장 · 계약 내용 + 쿠팡 판매 요약 + 쿠팡 정산 요약(D-218 따로 나란히) · 판매·정산 세부는 위탁정산서 · 시트에 내부용 글자(출처 셀·확인 필요·D번호) 없음.
  ③ "계약은 보냉백이지만 보냉백 판매가 부진하여 다른상품으로 추가 등록함, 그래서 계약서에 있는 상품과 관리대장에 있는 상품명을 불일치 할수 있고, 관리대장에 있는 상품을 기준으로 해야 함. 그런데 8,9,10월은 관리대장에서 등록 상품울 교체/추가하는 경우 기존 상품을 지우는 경우가 있어서 쿠팡에 등록된 상품으로 해야 하는데 조건이 로켓그로스 상품이 정산 대상 상품임. 로켓그로스 상품이면서 판매자 배송 상품도 포함 해야 함." → 셀독 정산서 실적·판매 범위 = 그 계정에 쿠팡에 등록된 **로켓그로스 상품**(같은 상품의 판매자배송 판매도 포함 · D-216 과 같은 생각) · 계약서 품목·관리대장 상품명과 달라도 됨 · 대장에서 지워진 상품도 포함.
  (참고) "연다인 계약서 업로드함, 계약서는 1건임." → 연다인 셀독 계약 = 2026-05-14 보냉백 3종 OEM 1건(20,904,400원 · 모두싸인 문서ID 88373c80-…) · 계약 DB 의 다른 연다인 계약 11건은 셀독 정산서 대상 아님.
- 근거: 소유자 원문 · 견본 3차 `D:\토탈셀러\쿠팡 정산 자료\셀독정산서_연다인_20261103기준_v3_261112_151410.xlsx`(1장·A4 1쪽 · 도달율 52.1% = 13,063,096 ÷ 25,085,280) · 소유자가 올린 계약서 PDF.
- 버린 대안: 계약별 여러 장 + 계정 합계(견본 1·2차) · 분모 = 목표수익금만(312.4%) · 범위 = 계약서 품목만 · 범위 = 관리대장 상품만(대장에서 지운 상품이 빠짐).
- 영향 범위: 구현 전(코드 변경 없음) — T-25 4단계 셀독 정산서 · 견본 4차(범위 적용). (Claude 해석·미확인) 판매자배송으로만 파는 상품은 제외 · 등록 시점 조건(계약일 이후 등록 D-152)은 유지 · 위탁정산서 관리 상품(D-217 ① 원장 상품이력)도 같은 범위로 할지는 소유자 확인 전 · 목표수익률 20% 는 계약서에 없고 D-152 조건.
- 상태: ACTIVE


### D-222 [STATEMENT_SCOPE_RG_REGISTERED] 위탁정산서 관리 상품도 셀독 정산서와 같은 범위(계정의 쿠팡 등록 로켓그로스 상품 · 판매자배송 겸용분 포함) · '계약일 이후 등록' 조건 유지 (2026-11-12, R155)
- 결정(소유자 2026-11-12 원문 — 이 세션(T-18) 대화. 질문 ① "위탁정산서의 관리 상품도 같은 범위(쿠팡 등록 로켓그로스 상품)로 할까요?" ② "'계약일 이후 등록한 상품' 조건은 그대로 둘까요?" 에 대한 답: "2건 승인, 새로운 세션에서 하자"):
  ① 위탁정산서의 관리 상품 = D-221 ③ 과 같은 범위 — 그 계정에 쿠팡에 등록된 **로켓그로스 상품**(같은 상품의 판매자배송 판매 포함) · 관리대장 상품명과 달라도 되고 대장에서 지운 상품도 포함.
  ② 등록 시점 조건(계약일 이후 등록 · D-152 '5월 이후 등록 상품')은 그대로 둔다(위탁정산서·셀독 정산서 모두).
  ③ 구현은 새 세션에서.
- 근거: 소유자 답 · 견본 4차(`D:\토탈셀러\쿠팡 정산 자료\셀독정산서_연다인_20261103기준_v4_261112_153302.xlsx`)에서 bux1004 를 같은 코드로 옛 범위·새 범위 계산 → 정산 값 원 단위 같음(빠진 상품 = 판매자배송 전용 C328, 판매·정산 0) · D-210 확인(T-25 세션): 대장에서 지운 뒤 정산 금액이 있는데 빠지는 상품 4계정 8개 3,089,065원 → 이 범위면 되살아나는지가 구현 때 확인 대상.
- 버린 대안: 관리 상품 = 원장 상품이력(D-217 ① — 8~10월 대장에서 교체하며 지운 상품 문제를 소유자가 지적) · 결과 엑셀 블록(현행).
- 영향 범위: 구현 전(코드 변경 없음) — `src/coupang_analytics/settlement_statement_*`(D-219 이관본)의 관리 상품 출처 · 로켓그로스 판정 자료 = 상품조회(RFM/NORMAL)·판매분석 '구분'(견본 4차 판정 방법). (Claude 해석·미확인) 판매자배송으로만 등록된 상품은 제외 · 로켓그로스 옵션이 등록돼 있으면 판매가 판매자배송뿐이어도 포함(진공포장기 사례). 4차 견본 양식 확정은 새 세션에서 소유자 확인.
- 상태: ACTIVE (부분 SUPERSEDED by D-227 — ① 범위를 '대장 기준 + 이력 없이 지워진 상품만 로켓그로스 등록 상품으로 되찾음'으로 좁힘)

### D-223 [STATEMENT_SCOPE_NO_CUTOFF] 위탁정산서 관리 상품 — 대장에서 지운 상품은 관리 기간을 자르지 않음 · 셀독 정산서 = 위탁정산서를 토대로(별도 계산·별도 받기 없음) (2026-11-12, R157)
- 결정(소유자 2026-11-12 원문 — T-25 이관 세션 질문 3개에 대한 답, D-222 기록 전): ① 상품명→VID 질문에 "관리대장과 상품이력을 혼합해서 관리상품을 확정하자." ② '대장에서 지운 상품의 판매는 어디까지' 질문에 보기 "기간 자르지 않음"(지운 날·지운 달까지 자르는 보기를 고르지 않음) ③ 셀독 정산서 범위 질문에 "셀독 정산서는 별도 계산하거나 다운받을 필요없이 위탁 정산서를 토대로 하면 됨." 이어서 D-222(위탁정산서 관리 상품 = 계정의 쿠팡 등록 로켓그로스 상품) 전달 뒤 보기 "멈추고 넘기기"(원장 혼합안 구현 중단 · 새 세션).
  읽는 방법(Claude): ② 한 번이라도 관리 상품이었던 상품은 대장에서 지운 뒤 판매도 관리 상품 판매로 셈(D-210 ② '그날까지'보다 넓음 — 지운 뒤 판매가 있을 때만 차이). ③ 셀독 정산서는 위탁정산서 계산 결과(관리 상품 몫)를 받아 계약 단위로 나눔 — 쿠팡 자료를 따로 받거나 다시 계산하지 않음.
- 근거: 소유자 답(이 세션 질문 도구) · 실제 자료 D-210 확인(`D:\coupang-analytics\output\_분석_261112_T25_이관대조\D210_확인.md` — 대장에서 지운 뒤 정산 금액이 있는데 빠지는 상품 4계정 8개 3,089,065원) · 원장 상품이력 조사(VID 없음 · 2026-09-20부터 · 매칭 고정으로 163개 중 108개만 VID — 공유 노트 `T25-step1-handover-2026-11-12.md`).
- 버린 대안: 지운 날까지(일 단위) · 지운 달까지(달 단위) · 셀독 정산서용 별도 계산·받기.
- 영향 범위: 구현 전 — T-25 새 세션(D-222 범위 구현 때 ②③ 함께 적용). ① 혼합안 구현은 멈춤(패치만 보관 `T25-D217-registry-history-WIP.patch` · 코드 변경 없음).
- 상태: ACTIVE (부분 SUPERSEDED by D-222 — ① 관리 상품 출처는 D-222 범위)


### D-224 [SELDOC_STATEMENT_FORMAT_V4] 셀독 정산서 양식 = 견본 4차로 확정 → 4단계 구현 진행 (2026-11-12, R158)
- 결정(소유자 2026-11-12 원문 — 이 세션(T-18) 대화, 견본 4차 보고 뒤: "4차 양식으로 확정, 진행해"): 셀독 정산서 양식 = `D:\토탈셀러\쿠팡 정산 자료\셀독정산서_연다인_20261103기준_v4_261112_153302.xlsx` 의 1장 구성(제목·계약자·기준일 → 카드 4개(목표 정산 총액·정산 기준 실적·목표 도달율·남은 금액) → 도달율 막대 → 계약 내용(체결일·계약·기간·품목 단가·수량·계약금액·목표수익률·목표수익금·목표 정산 총액) → 쿠팡 판매 요약(월별·상품별)과 쿠팡 정산 요약(입금 완료·예정·보류·보상·정산 기준 실적) 나란히 → '세부는 위탁정산서' 한 줄 · A4 세로 1쪽 · 내부용 글자 없음). 4단계(계약자별 셀독 정산서를 저장소 코드로 생성) 진행.
- 근거: 소유자 답 · D-218·D-221·D-222·D-223 ③(위탁정산서 결과를 토대로 · 별도 받기·계산 없음).
- 버린 대안: 견본 1~3차 양식.
- 영향 범위: 구현 — T-25 4단계(위탁정산서 결과 → 계약 단위 셀독 정산서 · 계약자 3명부터). D-222 범위 구현과 순서: 범위 구현(위탁정산서) 뒤 셀독 정산서가 그 결과를 받음.
- 상태: ACTIVE

### D-225 [SELDOC_STATEMENT_SOURCE_ONLY] 셀독 정산서 자료 = 위탁정산서 결과 + 계약서 분석 파일뿐 · 쿠팡 별도 받기·별도 정산 없음 · 셀독 정산서 질의 없음 · 양식은 계속 수정 보완 (2026-11-12, R159)
- 결정(소유자 2026-11-12 원문 — T-25 준비 세션 대화): "셀독정산서 관련 대원칙: 별도 쿠팡에서 다운받거나 정산 하지 않는다. 모든 자료는 위탁 정산서를 기초로 한다. 셀독 정산서에 추가로 필요한것은 계약서 분석한 파일이고, 이파일에서 필요한 항목의 데이타를 가져오면 됨. 이것으로 셀독 정산서 관련 질의는 없어야 됨, 다만 셀독 정산서 양식은 계속 수정 보완 해야 함."
  ① 쿠팡 판매·정산 숫자 = 위탁정산서 계산 결과만(쿠팡에서 따로 받거나 따로 계산하지 않음 · D-223 ③ 과 같음).
  ② 계약 내용(계약일·계약금액·수익금·수익률·품목 단가·수량 등) = 계약서 분석 파일에서 그 항목 값을 그대로 가져옴.
  ③ 셀독 정산서 구현 중 소유자에게 묻지 않음 — 값이 없거나 달라도 위 ①② 자료대로 만든다.
  ④ 양식(D-224 견본 4차)은 계속 수정·보완 대상.
- 근거: 소유자 원문 · 계약서 분석 파일 현행 = `D:\modusign\계약서_정밀분석\전수\계약서_정밀분석_DB_전수_v4.xlsx`(시트 '계약 통합' 4,673계약 · '품목' — 2026-11-12 13:33 · D:\modusign 작업공간 R39 결과) · 연다인 계약 88373c80 줄 = 계약일 2026-05-14 · 계약금액 20,904,400 · 품목 3종(YG0209 1,000개×6,402 · BG001 1,000개×5,808 · BG002 1,000개×8,694) · 수익금·수익률 빈 칸('계약 구조상 없음').
- 버린 대안: 셀독 정산서용 쿠팡 자료 별도 받기·별도 계산 · 계약 표 손 입력 파일(T-25 준비 계획 초안 S5) · 셀독 정산서 세부를 그때마다 소유자에게 확인.
- 영향 범위: 구현 전 — T-25 4단계(셀독 정산서 생성 코드)의 입력 = 위탁정산서 결과 + 위 분석 파일. (Claude 적용·사실) 견본 4차의 목표수익률 20%(목표수익금 4,180,880 · D-152 소유자 조건)는 분석 파일에 없음 → ② 대로면 셀독 정산서에 안 들어감(도달율 분모 = 계약금액 + 파일의 수익금) · 값을 넣으려면 분석 파일 쪽(D:\modusign)을 고친다. 위탁정산서 관리 상품 범위(D-222)는 이 결정 밖.
- 상태: ACTIVE

### D-226 [UI_LOG_PER_TAB] 앱 진행 로그창 = 탭별 표시 · 앱 시작 줄 = 모든 탭 공통 · 복사·지우기 = 지금 탭만 · 로그 파일은 한 파일 그대로 (2026-11-12, R160)
- 결정(소유자 2026-11-12 원문 — STATE T-19 "탭을 바꾸면 그 탭 로그" · T-19 세션 질문 답: 시작 줄 = "모든 탭에 공통 (추천)", 복사 버튼 = "지금 탭 줄만 (추천)"):
  ① 탭마다 진행 로그창 하나 — 탭을 바꾸면 그 탭의 줄만 보인다.
  ② 줄의 주인 탭: 버튼으로 시작한 작업(`run_bg`) = 누른 탭(작업 도중 다른 탭으로 옮겨도 · 작업 안 하위 스레드 줄·끝 처리·오류 줄 포함) · 버튼 누를 때 바로 나오는 줄 = 지금 탭 · 셀독전환 탭의 5초마다 읽는 진행 줄 = 셀독전환 탭 · 무인 18:00 실행·재부팅 복구 = 화면을 '전체 실행' 탭으로 옮기고 그 탭.
  ③ 앱 시작 때 줄(남은 Chrome 정리·정산 기동·입력 대장 읽기 등 어느 탭 작업도 아닌 줄) = 모든 탭 공통.
  ④ '복사' = 지금 탭 줄만(탭마다 최근 `config.UI_LOG_MAX_LINES` 줄) · '지우기' = 지금 탭만.
  ⑤ 실행 로그 파일(`output\run_log_*.log`) = 모든 탭 줄이 한 파일에 그대로(형식 변경 없음) · 로그창 보이는 규칙(첫 실행 전 숨김·설정 탭 쉴 때 숨김)은 그대로.
- 근거: 재현(고치기 전) — 화면 없이 띄운 앱에서 키워드 탭 줄과 순위 탭 줄이 두 탭 모두에 보임(로그창이 하나 `log_console`·탭 이동은 보이기/숨기기만) · 새 시험 `tools/verify_ui_log_tabs_offline.py` 7가지가 고치기 전 S1 실패 → 고친 뒤 통과.
- 버린 대안: 시작 줄을 설정 탭에만 · 복사 = 로그 파일 전체(옛 동작 — 모든 탭 줄이 섞임) · 로그 파일을 탭별로 나눔(다른 도구·사람이 보는 파일 형식 변경).
- 영향 범위: `ui/app_qt.py`(로그창·`log`·`run_bg`·`_on_finish`·`copy_log`·무인/복구 시작·`main`) · `ui/transfer_panel_qt.py`(진행 줄 주인 탭) · 게이트 `tools/run_checks.py` 1줄. 운용 PC 반영 = 새 배포 zip 뒤(통제 세션).
- 상태: ACTIVE


### D-227 [STATEMENT_MANAGED_SCOPE_RULES] 위탁정산서 관리 상품 규칙 5가지 — 대장 기준(지운 상품 포함·기간 안 자름) · 같은 상품명 다른 VID 포함 · 이력 없이 지워진 상품만 쿠팡 등록 로켓그로스 상품으로 되찾음 · 등록일 조건 = 계약 달 이후(달 단위) · 위탁자 본인 상품 제외 (2026-11-12, R161)
- 결정(소유자 2026-11-12 원문 — 이 세션(T-18) 대화: 질문 '위탁자 본인 상품도 셀까요?'에 "어떤 내용인지 설명해줘." · '판매자배송 전용 상품을 뺄까요?'에 "이전에 적용된 룰이 있어, 확인해줘" · '등록일 조건을 넣을까요?'에 "계약에 있거나 관리대장에 있는 계정" → 설명·규칙 확인 뒤 제안한 5가지에 "규칙안 5가지 승인, 기준일·달 단위도 제안대로 진행해"):
  ① 관리 상품 = 관리대장 상품 기준 — 지금 대장 상품 + 예전 대장에 있다가 지운 상품 · 지운 상품도 기간 자르지 않음(D-223 ②).
  ② 같은 상품명의 다른 VID(판매자배송·다른 수량 옵션·재등록)도 포함(D-107).
  ③ 대장에서 이력 없이 지워진 상품만 그 계정에 쿠팡 등록된 로켓그로스 상품에서 되찾음 · 같은 상품의 판매자배송 VID 포함(D-222·D-159 ②).
  ④ 등록일 조건 = '계약 달 이후 등록'(**달 단위** — 연다인 진공포장기 05-13 등록·계약 05-14 포함) · 적용 계정 = 계약이 있거나 관리대장에 있는 계정 · 계약 없이 대장에만 있는 계정의 기준일 = 그 계정이 관리대장에서 관리를 시작한 날.
  ⑤ 위탁자 본인 상품(브랜드)은 제외(D-107·D-159 ③) · 판정할 수 없거나 자료가 없으면 정산서에 '확인 필요'.
- 근거: 소유자 답 · D-221 ③ 원문("관리대장에 있는 상품을 기준으로 해야 함. 그런데 8,9,10월은 … 쿠팡에 등록된 상품으로 해야 하는데 조건이 로켓그로스 상품") · 계획서 `docs/plans/T25-scope-D222-plan-2026-11-12.md`(D-222 를 '계정의 로켓그로스 상품 전부'로 글자 그대로 적용하면 관리 정산금액 약 +5.4억 추정 — 대부분 위탁자 본인 상품 · D-210 3,089,065원 중 판매자배송 전용 2,044,407원은 계속 빠짐).
- 버린 대안: D-222 글자 그대로(계정의 로켓그로스 상품 전부 — 위탁자 본인 상품 유입) · 판매자배송 전용 상품 일괄 제외 · 등록일 하루 단위 · 등록일 조건 없음.
- 영향 범위: 구현 중 — `src/coupang_analytics/settlement_statement_account.py`(scope)·상품조회 읽기·시험 `tools/verify_settlement_statements_offline.py` · 현행 26곳 대비 바뀐 값 목록 보고 예정. D-222 를 이 규칙의 ③으로 좁힘.
- 상태: ACTIVE


### D-228 [STATEMENT_IMPL_EXISTING_AS_SPEC] 정산서 프로그램 구현 원칙 — 기존 정산서·판정표·결정 기록이 기준(재현 먼저) · 새 규칙은 '차이'로 보고 · 묻기 전에 결정 기록·예전 정산서/판정표·실제 자료 3가지를 먼저 찾음 (2026-11-12, R168)
- 결정(소유자 2026-11-12 원문 — 이 세션(T-18) 대화: "너가 그동안 output 파일을 보고 정산서 파일을 생성했는데, 이것을 프로그램으로 구현하는데 있어서 여러가지 룰을 나에게 확인을 요청하는 것은 문제가 있어. 그러면 지금까지 정산서 파일을 생성할때 어떤 기준으로 했는지 정보가 없다는 말임. 너의 의견을 제시해줘." → Claude 의견(아래 ①~③)에 "D-228 승인, 기록하고 진행해"):
  ① 기준(정답) = 이미 만든 정산서(현행 위탁정산서 26곳 등)와 그때 쓴 판정표·결정 기록(D-107·D-137·D-146·D-152·D-159·D-185·D-186 등). 프로그램은 먼저 그 결과를 재현한다(T-25 1단계 = 금액 차이 0).
  ② 새 결정이 생기면 기존 결과와 달라지는 부분만 '어느 계정·어느 상품·왜·얼마'로 보고한다(질문으로 바꾸지 않음).
  ③ 소유자에게 묻기 전에 결정 기록 · 예전 정산서/판정표 · 실제 자료 3가지를 먼저 찾는다. 셋 다 근거가 없을 때만 묻고, 그때도 근거를 남긴 판단 + '확인 필요' 표시로 진행한다(D-070 사람 승인 대기열 금지 · D-225 셀독 정산서 질의 없음과 같은 방향).
- 근거: 이 세션의 잘못(사실) — D-222 질문 전 D-107·D-159 를 찾지 않아 D-222 → D-227 로 다시 맞춤 · 되찾기 후보 201개를 D-159 판정표 대신 새로 판정하고 에벤에셀 회사 상품 13개·HB153 을 소유자에게 물음(예전 정산서·판정표로 확인 가능했던 것).
- 버린 대안: 구현 중 규칙마다 소유자 확인.
- 영향 범위: 정산서(위탁·셀독) 구현 작업 전체 · 지금 진행 중인 에벤에셀 13개·HB153 = 예전 정산서·D-159 판정표 기준으로 판정해 차이만 보고.
- 상태: ACTIVE

### D-229 [NO_HARDCODE_TO_MATCH_OUTPUT] 결과를 맞추려고 특정 계정·상품·금액 조건을 소스코드에 넣지 않음 — 규칙·입력 자료·판정표로만 결과가 나와야 함 (2026-11-12, R170)
- 결정(소유자 2026-11-12 원문 — 통제 세션 대화): "소스코드에 하드코딩을 해서 결과물이 동일하게 나오도록 조건이 들어 가면 안돼. 명심해."
  ① 기존 정산서·결과를 재현할 때(D-228)도 특정 계정 아이디·상품명·VID·금액을 코드 조건으로 넣어 결과를 같게 만들지 않는다.
  ② 결과는 결정 기록의 규칙 + 입력 자료(쿠팡 자료·관리대장·계약 분석) + 근거를 남긴 판정표(AI 판정 · 예: `관리상품_되찾기_판정.json`)로만 나온다. 개별 판정은 코드가 아닌 판정표 파일에 근거와 함께 둔다.
  ③ 규칙으로 재현되지 않는 차이는 코드로 맞추지 않고 D-228 형식('어느 계정·어느 상품·왜·얼마')으로 보고한다.
- 근거: 같은 날 소유자가 '에벤에셀 물총'(T-8 확인 건) 판정을 기존 규칙 기준으로 해 달라고 하면서 함께 준 지시 · T-25 4단계(셀독 정산서 코드)가 기존 정산표(D-146)와 차이를 맞추는 작업이라 바로 해당.
- 버린 대안: 기존 결과와 같게 나오도록 계정·상품별 예외를 코드에 둠.
- 영향 범위: 정산서(위탁·셀독) 구현 전체 · 이후 모든 코드의 결과 재현 작업 · 시험(핀)의 기대값은 설계·스펙에서 도출(코드에 특정 값 조건 넣기와 별개).
- 상태: ACTIVE

### D-230 [STATEMENT_SCOPE_SOURCE_PRIORITY] 정산 대상 상품 출처 순위 = ① 관리대장 ② 이력원장(셀독계정상품이력관리원장) ③ 계약서 ④ 쿠팡 등록 상품 (2026-11-13, R171)
- 결정(소유자 2026-11-13 원문 — 통제 세션 대화): "정산 대상 상품은 1순위는 관리대장, 2순위는 이력원장, 3순위는 계약서, 4순위는 쿠팡 등록 상품으로 함."
- 적용 방식(Claude 판단 — 기존 기록으로 정해지는 부분만 · 소유자 지시 아님): 상품 단위로 위 순위 출처에 없을 때만 아래 순위에서 찾는다(D-159 ② "이력 없는 경우에 한해" · D-227 ③ 과 같은 방식) · 위 순위에 있는 상품을 아래 순위가 빼지 않는다(D-159 ① · D-221 ③) · 출처가 다르게 말하면 위 순위를 따른다(예: 대장에 있고 계약에 없음 → 관리 · D-185 '확인 필요' 표시는 그대로).
- 근거(조사 2026-11-13 · 원문 = 통제 세션 scratchpad `scope_priority_research.md`): 이력원장 = 구글 시트 '상품이력'(D-100 · `registry_model.py:37-44` · 칸에 VID·등록상품ID 없음 · 가장 이른 기록 2026-09-20 · 대장에서 지운 상품 = 관리중단 줄로 남음 · 실측 관리중단 56줄 중 '대장에서 상품 삭제' 40줄) · 지금 정산서 코드는 '상품이력'을 읽지 않음(읽는 원장 시트 = '계정이력'·'정산전용상품'뿐 · `settlement_statement_scope.py:104-124`·`settlement_statement_context.py:61-70`) · 계약은 `관리시작달_차이표.xlsx` 계약일 하나만 읽고 품목은 안 읽음(`settlement_statement_context.py:73-79`) · 계약 DB v4 '품목' 시트에는 모델·수량 있음(4,673건 중 3,904 · 계정ID 칸 없음 · 예: 에벤에셀 공급계약 TTGW02 1,938개 · 옛 인덱스 품목 칸 빈 칸 → 11-09 차이표가 물총 계약을 놓침).
- 버린 대안: 지금 구현(D-227) 그대로(관리대장 + 날짜별 사본 + 쿠팡 등록 로켓그로스 되찾기만 · 이력원장·계약 품목 안 씀).
- 영향 범위: 위탁정산서·셀독 정산서 관리 상품 범위(`settlement_statement_account.py` `scope()`·`settlement_statement_scope.py`·`settlement_statement_context.py`) · 이력원장 이름만 있는 상품 → VID 판정표 필요(AI 판정) · 계약 품목 → 계약↔계정 연결표 필요 · D-227 ③ 되찾기는 4순위로 그대로 · 구현 전 · 세부 미정(STATE 미해결): 옛 PC 대장 파일을 1순위에 넣는지 · '정산전용상품' 시트가 2순위인지 · 3순위 계약 상품에 로켓그로스·계약 달 이후·본인 상품 제외 조건을 거는지와 계약 종류 범위.
- 상태: ACTIVE

### D-231 [STATEMENT_SCOPE_SOURCE_PRIORITY] D-230 세부 3가지 — 옛 PC 대장 = 1순위 · 원장 '정산전용상품' = 2순위(모든 계정) · 계약 품목 = 조건 없이 관리(계약 전 판매만 뺌) (2026-11-13, R173)
- 결정(소유자 2026-11-13 — 통제 세션 질문에 고른 답 · 모두 추천안):
  ① "9월 20일 전에 대장에서 지운 상품(옛 PC 대장 엑셀에만 남은 것, 예: 물총 TTGW02)도 1순위 '관리대장' 상품으로 볼까요?" → "봄" — 옛 PC 관리대장 엑셀(예: `D:\토탈셀러\미정산중 셀독전환자\26.05.29 셀독관리대장 (1).xlsx`)의 상품도 1순위 관리대장 상품.
  ② "이력원장의 '정산전용상품' 시트를 2순위로 보고 모든 계정에 쓸까요?" → "모든 계정에 씀" — '상품이력' 시트와 함께 2순위 · 대장에 있는 계정에도 적용(지금 = 대장 밖 계정만).
  ③ "대장과 이력원장에는 없고 계약서 품목에만 있는 상품은 어떻게 넣을까요?" → "계약서에 있으면 넣음" — 로켓그로스·판매자배송 가리지 않음 · 계약 전 판매는 D-185 대로 뺌 · 본인 상품 판정 안 함(4순위 조건 D-227 ④⑤ 는 4순위에만).
- 근거: D-230 조사(옛 대장·사본·원장 모두 9/20 무렵 시작 · 물총 TTGW02 는 옛 PC 대장·공급계약·쿠팡 등록 자료에만 있음 · 계약 DB v4 '품목' 시트 4,673건 중 3,904 품목 있음·계정ID 칸 없음) · D-227 ① "예전 대장에 있다가 지운 상품" 포함.
- 버린 대안: 옛 대장 안 봄(9/20 뒤 앱 기록만) · 정산전용상품 = 대장 밖 계정만(지금 방식) · 계약 품목도 4순위처럼 로켓그로스만·계약 달 이후 등록·본인 상품 제외.
- 영향 범위: D-230 구현(`settlement_statement_context.py`·`settlement_statement_scope.py`·`settlement_statement_account.py` `scope()`) · 새 입력 = 옛 대장 파일 목록 · 이력원장 이름→VID 판정표 · 계약↔계정 연결표 + 계약 품목→VID 판정표(모두 AI 판정·근거 기록 · 코드에 계정·상품 조건 금지 D-229) · 구현 뒤 현행 28곳 대비 바뀐 값을 D-228 형식으로 보고.
- 상태: ACTIVE

### D-232 [STATEMENT_SCOPE_AI_JUDGE] 정산 대상 상품 판정 = AI 가 최종 확정 · 그 뒤는 프로그램 · 일반 상품명의 의미로 쿠팡 등록·노출명과 대조(모델 코드 무시) · 시험은 3계정 (2026-11-13, R174)
- 결정(소유자 2026-11-13 원문 — 통제 세션 대화): "1.상품 판정은 AI가 최종 확정하고 그 이후부터는 프로그램이 처리, AI 판정시 프롬프트를 잘 설계해야 함. 2.28곳을 재생성 하지 말고, 3개 계정만 테스트를 진행할것. 3. 모든 구현이 완료되면 전체를 실행해서 확인하면됨(별도 진행 예정임)" · 1차 판정 보고 뒤: "1.상품명에 모델 코드가 없음 ==> 모델 코드 무시해, 2.계약 품목명이 일반 이름뿐 ==> 원래 계약서는 일반적임 상품명이 기재됨. ==> 그래서 AI가 계약서와 관리대장의 일반적인 상품명으로 쿠팡의 노출(등록) 상품명을 비교하여 확정하는 절차가 필요함, 현재 구현된 앱에서 그렇게 하고 있어. 앱에 구현된것을 확인해서 참조해."
- 구현(R174): `src/coupang_analytics/settlement_scope_judge.py`(후보·근거 모으기 · 프롬프트 `PROMPT` = 앱 `product_match_ai.MATCH_SYSTEM` 기준(의미로 판단 · 모델 코드 보조 · 꾸밈말·색상·수량 무시 · 다시 등록한 같은 상품 모두) · 답 검사 `check_answer` = 판정대상 ID·허용 출처·판정·근거·원문 그대로) · `tools/settlement_scope_judge.py`(prepare·apply) → 입력 폴더 `관리상품_출처판정.json`. 옛 대장은 계정·상품·참고 칸만 읽음(비밀번호·연락처 안 읽음).
- 구현값(Claude 판단 · 소유자 지시 아님): 출처 '확인 필요' = 정해지지 않은 것 → 4순위(되찾기)로 넘어감(벅스 속눈썹고데기 재현: 넘기지 않으면 4순위 '관리'가 빠짐) · 1~3순위 '관리' 등록상품은 그 상품의 VID 전부로 잡음(정산 파일 상품 ID ≠ 상품조회 등록상품ID — 벅스 진공포장기·보냉가방 재현).
- 근거: 3계정 시험 `D:\coupang-analytics\output\_분석_261113_D230_3계정\`(빈 판정표 = R166 과 다른 칸 0 · 판정 뒤 `바뀐값_A_vs_B.txt`).
- 버린 대안: 모델 코드 일치 요구(1차 프롬프트 — 확인 필요 과다) · 코드가 문자열 규칙으로 확정.
- 영향 범위: 정산서 도구만(앱 실행 경로에서 안 불림) · 운용 18시 배치에서 판정 갱신 방법은 T-25 5단계.
- 상태: ACTIVE

### D-233 [SETTLEMENT_APP_BOUNDARY] 정산 작업은 정산 부분에만 한정 — 앱 본래 기능은 그대로 · 역할을 구분하고 섞어 고치지 않음 (2026-11-13, R174)
- 결정(소유자 2026-11-13 원문): "지금 작업은 정산 관련 작업임, 정산 관련 작업은 앱은 매일 다운 받은 자료를 읽어서 정산서를 작성하는 것이 임무임, 정산 관련 부분에만 한정 되어야 함, 기존 앱은 본래의 기능을 수행하면 됨, 너가 정산과 앱 본래의 기능을 혼동하고 있어. 약할을 명확히 구분하고 선을 그어야 함. 동시에 여기저기 수정하면 나중에 뒤섰여서 기존 앱 기능도 오류가 발생함." · 같은 대화 "관리대장은 변경하면 안됨, 백업_계정정지_20261112_093203 시트는 삭제해줘."(삭제함 · 남은 탭 = 셀독리스트·체험단·자체 체험단).
- 적용: 정산 작업 = 받은 자료를 읽어 정산서를 만드는 코드(`settlement_*`·정산 도구·정산 시험)만 고침 · 관리대장·앱 파이프라인·UI·공용 모듈은 정산 작업에서 고치지 않음(필요하면 별도 작업·소유자 승인).
- 근거: 점검 보고 `D:\coupang-analytics\output\_분석_261113_정산_앱경계\경계점검.md`(10-20 이후 정산 커밋 105개 중 앱 동작이 바뀐 곳 6곳 B1~B6 — 모두 결정 있음(D-123·D-160·D-091·D-189·D-103·D-190·D-021·D-187) · 결정 없는 변경 0 · 이번 미커밋 변경 = 정산 전용).
- 영향 범위: 이후 모든 정산 작업 · B1~B6 을 정산 쪽으로 다시 떼어 낼지는 소유자 결정(STATE 미해결).
- 상태: ACTIVE

### D-234 [SELDOC_STATEMENT_IMPL] 셀독 정산서 코드 구현(T-25 4단계) — 계약 1건 = 1장 · 계정 계약 여럿이면 상품군 판정표로 위탁정산서 규칙 그대로 직접 합산 · 숫자 = 위탁정산서 결과 · 계약 = 계약서 분석 DB (2026-11-13, R177)
- 결정(소유자 2026-11-13 원문 — 통제 세션 대화): "가) 로 진행해" — 가) = 통제 세션 제시안 "연다인부터 끝까지 진행 · 장대익·서달원은 두 계정만 AI 판정을 한 뒤 만듦(D-232 의 3계정 시험에 2계정 추가)". 같은 날 "이 작업을 여기에서 진행해 주세요: T-25 4단계 S0~S4". 지킨 결정 = D-152·D-155·D-218·D-221·D-224·D-225·D-228·D-229·D-233.
- 구현(R177): `src/coupang_analytics/settlement_seldoc_source.py`(위탁정산서 결과·계약 DB 읽기 · 대상 계약 = DB '계약유형(소)'가 '셀독 상품공급 OEM'·'보냉백 OEM 생산공급'과 정확히 같을 때 · 그 밖 변형 = 규칙 밖 → 중단) · `settlement_seldoc_sheet.py`(견본 4차 1장·A4 세로 1쪽) · `settlement_seldoc_groups.py`(계약이 여럿인 계정 = 위탁정산서 계산 `Account` 를 관리 상품만 상품군으로 좁혀 다시 계산 · 관리 시작 달 = 계정 전체 값 고정 D-155 · 기존 계산 코드 변경 없음) · `tools/settlement_seldoc.py`(groups·make) · 시험 `tools/verify_seldoc_statements_offline.py` 8종(`run_checks` 등록 · 코드 없을 때 ImportError 실패 확인).
- 구현값(Claude 판단 · 소유자 지시 아님): ① 판매금액 = 위탁정산서 '월별 판매' 합계(배송비 제외) · 판매수량·상품별 = '상품별 판매'(정산 끝난 판매만 — 위탁정산서에 정산 중 수량 없음) → 견본 4차의 월 '수량' 칸을 '정산'(끝남·정산 중)으로 바꿈 · 상품 표 최대 8줄 ② 계약 줄 = DB 문서 제목 + 계약자·회사 명칭(갑·을 표기 안 씀) · DB 빈 값 = '없음'·'(종료일 없음)' ③ 남은 금액 0 아래로 안 내림 ④ 쿠팡 별도 보상 = 위탁정산서 줄 그대로 · 계약 여럿 계정에 보상이 있으면 나누지 못해 중단 ⑤ 서달원 상품군 판정표 = `셀독_계약상품군_판정.json`(AI 판정·근거 원문 · 옛 `seo_groups_D146.json` 기준 · 수영장 6·헬스매트 6·나머지 29 = DW커머스).
- 근거(실측): 생성 6장 `D:\토탈셀러\쿠팡 정산 자료\셀독정산서_*_20261103기준_261113_1455*.xlsx` · 서달원 4계약 G 합 26,234,968 = 계정 G(차이 0) · 같은 인자로 다시 만든 위탁정산서 3계정 = 기존 파일과 칸 차이 0 · 시험 8종·위탁정산서 시험 통과·복잡도 경고 0 · 보고 `D:\coupang-analytics\output\_분석_261113_T25_셀독정산서\S1-S3_구현보고.md`·`차이_D146_vs_셀독.md`·`S0_공제차이_원인.md`.
- D-146 표와 차이(D-228 보고 · 코드로 맞추지 않음 D-229): 연다인 실적 12,567,615(−495,481) · 장대익 8,809,102(−1,074,155) · 서달원 수영장 5,694,001(−367,979)·헬스매트 9,605,821(−165,173)·DW커머스 10,935,146(−2,717,771) — 모두 상품 자료 없는 공제 규칙 차이(D-153 ④ ↔ 11-06 소유자 "확인필요라고 기술되면 안돼"·D-186 비율 배분 · 정산대상액 E 는 상품군별로 같음) · 목표수익금 DB 빈 칸 → '없음'(연다인 도달율 60.1% vs 견본 52.1%) · 서달원 기저귀가방 계약(13,380,000)은 규칙상 대상 → 실적 0 장(D-146 은 헬스매트로 옮긴 것으로 보고 뺐음).
- 버린 대안: 계약자 1명 = 1장(서달원 계약 4건 · D-155 상품군 배분과 안 맞음) · 판매분석 수량 사용(D-225 ① 위탁정산서 결과만) · 기저귀가방 계약을 코드로 제외(D-229).
- 영향 범위: 정산서 도구만(앱 실행 경로에서 안 불림 D-233) · 운용 18시 배치 연결은 T-25 5단계 · `groups` 실행 약 7분 30초.
- 상태: ACTIVE

### D-235 [SETTLE_MATERIALITY] 정산 금액 차이 100원 이상 = '정산 금액을 바꾸는 차이' — 작다·거의 없음으로 넘기지 않음 (2026-11-15, R181)
- 결정(소유자 2026-11-15 원문): ① "천원이상이면 정산 금액을 크게 바꾸는 것임, 너가 잘못 알고 있음." ② 이어서 "1000원--> 100원으로 조정하자. 계정 위탁자 관점에서 100원도 중요하게 여김."
- 적용: 정산 분석·검산·보고에서 금액 영향 100원 이상 = '영향 있음(확정 필요)' · '작다·거의 없음·무시 가능' 표현은 100원 미만 끝전에만 · 검산 허용 오차를 정할 때 이 기준을 먼저 대조.
- 근거: Claude 가 확정 못 한 6개를 "가장 큰 것 116,445원 — 크게 안 바꿈"으로 보고한 데 대한 소유자 정정. 메모리 `feedback-settlement-1000won-material.md`.
- 버린 대안: 금액 크기로 중요도 판단(Claude 이전 판단) · 1,000원 기준(소유자가 같은 날 100원으로 조정).
- 영향 범위: 이후 모든 정산 분석·검산 보고 · 비율 배분 오차(T34 실측 WAPE 11.8~43.6%)는 이 기준을 못 맞춤 → 상품으로 나눌 수 없는 금액은 따로 표기(D-236).
- 상태: ACTIVE

### D-236 [SETTLE_ALL_COUPANG_DATA] 쿠팡이 주는 정산 자료는 전부 정산에 반영 · 상품별로 안 와서 관리 상품 몫으로 나눌 수 없는 금액은 정산서에 따로 표기 (2026-11-15, R181)
- 결정(소유자 2026-11-15 원문): "쿠팡이 제공하는 모든 자료는 정산에 반영하자. 다만, 상품별로 주지않아서 위탁상품에 해당하는 금액으로 분리가 되지 않는 부분은 별도 표기 하자. 이런 경우 금액도 정산금액에 영향을 주게 되므로 정산금액이 더해지면 문제가 되지 않지만 공제(빼는 금액)되는 것이고 금액이 크면 위탁자가 확인요구를 할수도 있음"
- 적용: 정산서 1쪽 '계정 공통 비용'(상품별로 안 나옴) 한 줄 + 2쪽 같은 번호 상세에 항목별 '쿠팡 청구 금액(계정 전체)'과 '이 정산서 반영 금액' · 반영 기준 = D-237 · 별도 입금(우대수수료 환급·추가지급)도 정산 금액에 넣음(샘플 3차).
- 근거: 87항목 분류(8묶음 · 빠짐·중복 0) `D:\coupang-analytics\output\_분석_261113_T34_비율역추적\쿠팡정산_더하기빼기_87항목_261115.xlsx` · gyi0101 재생성(지금 코드 그대로) — F 각 줄 = 상품으로 찾은 금액 + 비율로 나눈 금액(원 단위 일치 · 끝전 1원 1곳) · 보고 `…\쿠팡정산_질문4건_답변_261115.md`.
- 버린 대안: D-153 '상품 자료 없는 공제 = 관리 몫 없이 참고에 쿠팡 금액만'(정산 금액에 안 넣음) · F 안에 섞어 표시(지금 코드 · 위탁자가 확인 불가).
- 영향 범위: 정산 코드만(D-233) · 구현 전(T-38) · D-153 의 '자료 없는 공제' 부분 대체.
- 상태: ACTIVE

### D-237 [SETTLE_COMMON_ALLOC] 계정 공통 비용의 관리 상품 몫 = 판매 비중과 상품 등록 비중 중 계정 관리 측에 유리한 쪽 (2026-11-15, R181)
- 결정(소유자 2026-11-15 원문): "판매비중과 상품 등록 비중중에서 계정을 관리해주는 입장에서 유리한 부분을 적용해줘."
- 적용(Claude 판단 · 소유자 지시 아님 — 방향 확인 대기 T-40): 회사 몫 = 관리 상품 정산금 × 계약 비율(예: 7:3 · D-152) → 관리 상품에 붙는 공통 비용이 적을수록 유리 → 계정×달마다 두 비중 중 **작은 쪽** · 판매 0인 달은 판매 비중 0 → 몫 0(D-186 과 같은 결과) · 정산서에는 비율 대신 개수·기준 이름("등록 상품 10개 중 관리 상품 3개 몫") · 두 비중 중 골랐다는 문구는 안 씀.
- 근거: 지금 코드 = 관리 정산금 비율(T34 실측 오차 WAPE 43.6% · 맞춤 조합 13.1% · 개선 11.8% — 어느 쪽도 100원 기준 못 맞춤 D-235) · 계정 정액(판매자서비스이용료·구독료·비즈니스 인사이트)은 상품별 정답이 없음 → 나누는 규칙의 문제.
- 버린 대안: 판매 비중만(지금 코드) · 반영 안 함 · 전액 반영 · T34 추천 조합+A1·E1(비율 정확도 개선 — 규칙 자체를 바꿈).
- 영향 범위: 정산 코드만 · 구현 전(T-38) · 등록 비중 자료 = 쿠팡 상품조회의 달별 등록 상품 수(달별로 구할 수 있는지 구현 때 확인) · 실제 계정에서 어느 쪽이 작은지 미측정.
- 상태: ACTIVE (부분 SUPERSEDED by D-271 — 계정 단위 정액 3종(판매자서비스이용료·세이버·비즈니스 인사이트)은 그 달 등록 상품 비율만)

### D-238 [STATEMENT_LAYOUT_CONSIGNOR] 위탁자용 정산서 형식 — 쿠팡을 모르는 위탁자가 질문 없이 읽음 · 간략·명확 · 비율 표시 없음 · 1쪽 번호 = 2쪽 상세 번호·합계 같음 (2026-11-15, R181)
- 결정(소유자 2026-11-15 원문): "정산서를 시각적으로 알기 쉽게 작성해야돼. 쿠팡을 모르는 위탁자가 정산서를 받아보는데 질문이 있으면 안돼, 그렇다고 구구절절하게 설명을 해 놓으면 더 복잡하게 보여. 간략하면서도 명확해야 해" · "비율을 표시해야 해? 더 혼란 스러워." · "정산서 첫장에 나오는 금액에 대해, 두번째페이지에서 상세 내역이 나와야 함 … 서로 적용 기준이 동일해야 함." · "하단 여백을 상단과 하단이 동일하게 조정하고 … 두번째 페이지도 동일함."
- 적용(샘플 3차): 1쪽 = 카드 3개(고객 결제·쿠팡이 뺀 돈·이번 정산 금액) · 번호 1~10 계산표(줄마다 설명 한 구절 · 빼는 돈 빨강 · 받는 돈 파랑) · 계정 공통 비용 노란 칸 · '정산 금액은 어디로 갔나요'(합 = 정산 금액 · 대출 상환·빠른정산·입금 완료·예정·환급) / 2쪽 = 1~8 상품별 표(열 = 1쪽 번호 · 합계 = 1쪽) · 6 종류별 · 9 계정 공통 항목별 · 10 별도 입금 · 11 날짜별 입금 · 비율·막대 없음 · 위아래 여백 같게·그룹 사이 균등.
- 근거: 샘플 `D:\coupang-analytics\output\_분석_261113_T34_비율역추적\정산서_시각샘플_261115_3차.pdf`(원본 `정산서_시각샘플_261115.html`) · 합계 대조(가상 숫자) 모두 일치.
- 버린 대안: 비율 막대·퍼센트(1차) · 2쪽에 1쪽과 다른 묶음(수수료·쿠폰 합산 등 · 1차) · 지금 정산서(F 에 비율 배분 섞임 · 설명 문구 김).
- 영향 범위: 위탁정산서 코드(`settlement_statement*.py`)만 · 구현 전(T-38) · 샘플 최종 승인 대기(T-40) · 지금 정산서 머리 줄 수 규칙(STATE 주의)과 충돌하면 보고.
- 상태: ACTIVE

### D-239 [SETTLE_UNRESOLVED_SCOPE] 확정 못 한 6개 처리 — 10 카드 즉시할인·28 윙 라이브·71 리테일 광고 = 확인 대상에서 제외 · 23 정산차감·24 전주채권/3PM_매출채권 = 쿠팡 자료 유무 확인 뒤 결정 (2026-11-15, R181)
- 결정(소유자 2026-11-15 원문): "확정못한 6개중 10번, 28번, 71번은 제외하자." · "23번, 24번은 쿠팡이 제공하는 정산 자료를 찾을수 있는지 또는 없는지 확인해줘. 그 다음에 결정 하자."
- 확인 결과(Claude · 2026-11-15): 23 = 쿠팡 도움말 FAQ 237 "매출내역에서 정산차감액 클릭 시 상세"(쿠팡이 상세 제공 안내 · KB 47줄) · 앱은 지급 줄 사유·금액만 · 후보 = 매출내역 행별 상세다운로드(주문별 · 앱 안 받음) · 11-08 화면 코드 실측에 정산차감 주문별 API 없음. 24 = 전주채권·3PM_매출채권은 사유·금액만(상세 안내·화면 실측 없음 → 미제공 가능성[추정]) · 12줄 116,445원 중 4줄 앞선 마이너스 지급과 원 단위 짝 · 2줄 되돌림 · 2줄 수집 범위 밖 · 4줄(ljung0622 30,881·23,593 · gbseller808 23,659·10,139) 짝 없음 · 앱이 윙 지급 명세 원문을 저장 안 함(`settlement_wing_api.py:205~206` 사유·금액 2칸만) → 원문 칸 미확인.
- 버린 대안: 6개 모두 고객센터 문의(10·28·71 은 소유자 제외).
- 영향 범위: 남은 확인 = 소유자 로그인 Chrome 조회만(정산현황 미리보기 원문·정산차감 클릭 화면 · T-39) · 나머지 82개 중 72개 = 쿠팡이 주고 앱이 받음 · 쿠팡 정산 밖 2(20 하나은행 수수료·34 한진) · 위치 못 찾음 4(33·56·57·58 — 받은 자료 0원) · 금액만·상세 없음 3(31·54·63) · 비용 없음 1(72).
- 상태: ACTIVE

### D-240 [STATEMENT_LAYOUT_FINAL_GSHEET] 위탁자용 정산서 = 샘플 3차 형식으로 확정 · 구글시트로 발행(첫 탭 요약 · 둘째 탭부터 위탁자별 정산서) · 여백·색·글자 크기 = 3차 샘플과 최대한 같게 (2026-11-15, R182)
- 결정(소유자 2026-11-15 원문 — 통제 세션 대화): "2.정산서는 마지막 버젼 방식으로 확정하자." · "3.구글시트에 첫시트는 요약, 두번째 시트부터는 위탁자 정산 내역을 나와야 함. 구글시트를 사용하면 PDF 파일 정산서 처럼 멋있게 표현하는게 어렵지? 기능하면 여백과 색상, 크기를 최대한 동일하게 구현 해줘" · "3.이번에는 3명 위탁자 건을 샘플로 실제 작성해보자." · "4. 3명 위탁자 샘플이 완성되면 실제로 프로그램으로구현하자. 구현 방법과 구현 계획을 제시해줘."
- 적용: 형식 = D-238 의 샘플 3차(`D:\coupang-analytics\output\_분석_261113_T34_비율역추적\정산서_시각샘플_261115.html`·`…_3차.pdf`) · 구글시트 = 탭 1 '요약'(위탁자별 금액 표 + 탭 이동) · 탭 2~ = 위탁자 1명 = 탭 1개(1쪽 + 2쪽을 위아래로) · 3명(연다인 bux1004·장대익 bf0621·서달원 dalbong1849) 실제 숫자 샘플 먼저 → 소유자 확인 → 프로그램 구현(T-38 에 포함).
- 구현값(Claude 판단 · 소유자 지시 아님): 구글시트 칸 너비 = A4 내용 폭 730px 을 나눈 세로 경계(카드 사이·2쪽 두 표 사이 틈은 좁은 칸) · 위아래 여백 42px(11mm) · 쪽 높이 1,036px 에 맞춰 묶음 사이 틈을 같게(HTML space-between) · 번호 동그라미 = ①~⑩ 글자 · 글꼴 Noto Sans KR · 쓰기 = 앱 서비스계정(소유자가 만든 시트에 편집자 공유).
- 근거: 3차 샘플 합계 대조 일치(D-238) · 서비스계정 범위 = spreadsheets(새 파일 만들기·공유 불가 → 소유자가 빈 시트를 만들어 공유).
- 버린 대안: 엑셀/PDF 파일 발행(소유자 구글시트 지정) · 위탁자 1명 = 구글시트 파일 1개(소유자: 한 파일 첫 탭 요약).
- 영향 범위: 위탁정산서 코드(정산 코드만 D-233) · T-38 · 샘플 시트 = 소유자 시트(주소는 STATE) · 지금 결과 구글시트(`gsheet/output_url`)와 별개.
- 상태: ACTIVE

### D-241 [CONSIGNOR_STATEMENT_RULES] 위탁자 정산서 세부 규칙 9건 — 등록 비중 = 정산 기준일 등록 상품 수 · 상품 모르는 환급 = 계정 집계 후 나중에 분리 · 상품명 묶기 = AI 판정 · 넘치면 다음 쪽 · 발행 = 매월 작업일 기준(확정+예정 함께) · 달마다 새 파일 · 문의 문구 삭제 · D-237 = 작은 쪽 확정 (2026-11-15, R182)
- 결정(소유자 2026-11-15 원문 — 통제 세션 대화, Claude 질문 1~9 답): "1번 지난달 등록 상품 수 : 정산 기준 등록된 상품수로 하면 됨." · "2번 우대수수료 환급 169원 ==> 나중에 상품별로 알수가 있어? 아니면 모르면 계정별 집계에 넣어주고 나중에 상품별로 분리가 가능해지면 분리해줘." · "3번상품명은 파이썬으로 매칭하면 안돼,AI로 해줘." · "4번 2쪽이 넘으렴 다음쪽 너김" · "5번 발행시점은 매월 작업하는 일자가 기준임, 이러때 정산이 완료된것과 정산 예정인 값이 있음, 그래서 샘플 정산서에도 정산 예정 금액이 표시된 것임." · "6번 추천안 수용."(= 달마다 새 파일) · "7번 문의 문구 : 삭제" · "8번 (1)번할인쿠폰 반영해, (2)번 위탁상품 맞음, (3번) 위탁상품 맞음, (4)번 그래로 반영" · "9번 두 비중 중 작은 쪽 : 맞음"
- 적용: ① D-237 등록 비중 = 정산 기준일(작업일)에 계정에 등록된 상품 수 중 관리 상품 수(지난달 등록 수를 되살리지 않음) ② 상품을 아직 모르는 우대수수료 환급 = 10번에 계정 집계 줄로 넣고, 쿠팡 자료로 상품이 확인되면 그때 상품별로 나눔 ③ 같은 상품 다른 이름 묶기 = AI 판정(프로그램 글자 비교로 확정 금지 · 판정표에 근거) ④ 2쪽이 넘치면 다음 쪽으로(글자 줄이기·줄 높이 압축 안 함) ⑤ 발행 기준 = 매월 작업일 · 그날 기준 정산 확정분과 정산 예정분을 함께 표시 ⑥ 판매 달마다 구글시트 파일 1개 ⑦ 1쪽 아래 문의 문구 없음 ⑧ 서달원 헬스매트 할인쿠폰 +18,000 반영 · 장대익 '스탠드 HJ123' = 위탁 상품 · 서달원 상품 16258713629(9월 보관비 5,948원) = 위탁 상품(샘플·기존 판정에서 관리 밖으로 뺀 것은 잘못 → 고침 대상) · 연다인 보냉백 YG0209 반출비 그대로 반영 ⑨ D-237 '관리 측에 유리한 쪽' = 판매 비중과 등록 비중 중 작은 쪽(확정).
- 근거: 샘플 `D:\coupang-analytics\output\_샘플_261115_위탁자정산서\`(계산_보고.md · data_*.json) · 구현 계획 `docs/plans/T38-consignor-gsheet-statement-plan-2026-11-15.md` 4절.
- 버린 대안: 판매 비중만(등록 수 자료 없을 때) · 환급 169원 다음 정산서로 미루기 · 같은 날 입금 묶기·글자 줄이기 · 상품별 자료가 다 나온 달만 발행 · 한 파일 탭 덮어쓰기.
- 영향 범위: 위탁자 정산서 코드(T-38 · 정산 코드만 D-233) · ⑧-3 은 기존 위탁정산서 관리 상품 판정에도 영향(dalbong1849 16258713629 — 판정표 출처 확인 필요) · 정산 예정분 표시 방법·확정 뒤 변동 처리·매일 생성 파일 구성은 미결(STATE).
- 상태: ACTIVE (부분 SUPERSEDED by D-271 — ①⑨ 중 계정 단위 정액 3종은 그 달 등록상품 ID 비율(판매중지 포함)만 · 작은 쪽 비교 안 함)

### D-242 [CONSIGNOR_STATEMENT_DAILY] 위탁자 정산서 — 정산 예정분 표시(A안) · 보낸 뒤 확정 차이 = 다음 달 한 줄 · 매일 같은 정산서를 최신 값으로 갱신 · 달 파일은 소유자 구글 계정 권한(OAuth)으로 앱이 자동 생성 (2026-11-15, R182)
- 결정(소유자 2026-11-15 원문 — 통제 세션 대화): "5번 A, 10번 제안대로, 11번 해석 맞음, (나)로 해줘"
- 적용(Claude 제안 원문을 소유자가 고름): ① A안 = 1~8 금액에 정산 예정분 포함 · 예정분은 상품 판매 비율로 나눔(지금 위탁정산서 방식 D-148 예외) · 1쪽 큰 숫자 아래 "이 중 쿠팡 확정 전 금액 ○○원(바뀔 수 있음)" · 2쪽 상품표 예정분 회색 ② 위탁자에게 보내기 전까지 매일 최신 값 · 보내는 날 정산서 = PDF 저장·고정 · 보낸 뒤 쿠팡 확정으로 생긴 차이 = 다음 달 정산서 '지난 정산서 확정 차이 ±○○원' 한 줄 + 2쪽 상세 ③ '매일 일자별 정산서' = 같은 정산서를 매일 최신 값으로 다시 그림 · 판매 달마다 파일 1개(탭: 요약 · 위탁자별 · 맨 끝 '변경 기록') · 18시 정산 받기 뒤 정산 예정이 남은 달 파일만 다시 그림 · 다 확정된 달 = '확정' 표시 후 안 건드림 · 머리 '자료 기준일 · 정산 예정 포함' · 날짜별 기록 = PC `D:\토탈셀러\쿠팡 정산 자료\위탁자정산서\<판매달>\` 아래 날짜별 숫자 파일·PDF(시트에 날짜 탭 안 만듦) · 위탁자에게는 그 위탁자 탭 PDF 만(시트 공유 금지 — 한 파일에 다른 위탁자 정보) ④ (나) = 소유자 구글 계정으로 앱에 시트 만들기 권한 1회 허락(OAuth) → 앱이 달 파일 자동 생성.
- 근거: 서비스계정(spreadsheets 범위)은 새 파일 생성 불가 실측(2026-11-15 샘플 때 소유자가 빈 시트 만들어 공유) · D-241 ⑤⑥.
- 버린 대안: B안(예정분 상품표 한 줄 · 3차 번호 체계 바뀜) · 보낸 정산서 고쳐 다시 보냄 · 날짜마다 탭/파일 · (가) 매달 소유자가 빈 시트 생성 · (다) 공유 드라이브.
- 영향 범위: T-38 구현 · OAuth 허락 = 소유자 직접(Claude 는 동의 버튼 안 누름) · 토큰 = credstore(DPAPI) · 18시 배치 연결 = T-25 5단계와 함께.
- 상태: ACTIVE (부분 SUPERSEDED by D-251 — 1쪽 '이 중 쿠팡 확정 전 금액' 문구 → '이 중 정산 예정 금액(쿠팡 미확정 금액)' · D-258·D-259 — 1쪽 문구 · 부분 SUPERSEDED by D-362·D-372 — '18시 정산 받기 뒤' → 00:10 회차 정산 받기 뒤(시각만))

### D-243 [OUTPUT_EXPORT_SPLIT] output 분리 — 변경분 내보내기 · 운용 PC 보관 이동 · 커지는 파일을 달별로 (2026-11-15, R184)
- 결정(소유자 2026-11-15 원문 — 통제 세션 대화): "OUTPUT 파일이 계속 커지고 있어. 분리를 해야 돼 … 운용PC 에서 파일을 가져 오는데 용량이 커서 너무 오래 걸려. 너가 output 파일 생성과 분리 방안을 제시해줘" → Claude 제안 3가지에 "1·2·3 모두 추천대로 진행해줘".
- 적용: ① 내보내기 = 기준본(output (37) · 개발 PC `output\_분석_261115_output37\output\`) + **변경분**(지난 내보내기 뒤 바뀐 파일만 · 내용 같으면 뺌 · 보낸 기록 파일) + **확인용 작은 묶음**(앱 실행 로그·정산 로그·결과 엑셀·실행 단계 기록) · 한글 이름 UTF-8(D-201 방식) · 정산 증빙 포함(D-149) · 앱·정산 실행 중이면 만들지 않음 · 개발 PC 합치기 도구(받은 파일 대조) ② 운용 PC output = 지우지 않고 `보관\YYYY-MM\` 로 **이동만** — 정산집계 최신 3개만 남김 · 지난 달 이전 백업·로그 매달 · 프로그램이 읽는 파일은 옮기지 않음(항목마다 코드 확인) ③ 파일 쓰는 방식 — 정산예정기록 = 달별 파일 · 판매분석_일별 = 계정 × 달 파일(옛 파일 자동 변환).
- 근거(output (37) 실측): 풀면 1.5GB(압축 913MB) · 매출성장광고 엑셀 296개 714MB · 정산집계 75개 약 180MB · 하루 바뀐 파일 835개 147MB · 판매분석_일별 계정당 1파일을 매일 통째로 다시 씀(58MB) · 정산예정기록 1파일 19MB.
- 버린 대안: 매번 output 전체 압축(지금) · 과거 자료를 output 밖으로 옮기고 읽는 경로 바꿈(회귀 위험) · 오래된 파일 삭제(⛔output 삭제 금지).
- 영향 범위: 새 도구(내보내기·합치기·보관 이동) · `tools/settlement_download.py`(정산집계 회전·정산예정기록) · 판매분석 저장(앱 코드 — 소유자 직접 요청이라 D-233 대상 아님).
- 상태: ACTIVE (구현 R191 병합 — ① 내보내기·합치기 + ② 보관 이동(백업·로그) = ㉢ R186 `tools/output_export.py`·`output_merge.py`·`output_archive.py`·`deploy/output_내보내기.bat` · ② 정산집계 최신 3개 + ③ 정산예정기록 달별 = D-246 · ③ 판매분석_일별 달 파일 = R185 ㉡ · 보관 기준 세부(이번 달 1일 전·묶음별 최근 1개 남김) = Claude 구현값)

### D-244 [SCOPE_COST_ONLY_PRODUCTS] 판매 없이 비용만 있는 관리 상품도 관리 범위 — 비용 리포트 옵션→등록상품 짝 사용 · 판정 전엔 '확인 필요' 표시 (2026-11-15, R184)
- 결정(소유자 2026-11-15 원문): "이제는 코드 수정을 통해 모두 적용해도 되지? 코드 수정해줘" · "ⓐ 코드 수정으로 진행해줘" · 제안 ①~⑤ 에 "1·2·3 모두 추천대로 진행해줘"(⑤ 표시 포함 = Claude 추천으로 해석).
- 적용: ① 정산집계에 새 시트 '옵션별 등록상품'(비용 리포트 줄의 옵션ID→등록상품ID) ② 정산서는 그 시트를 읽음 — 없는 옛 집계면 시작 전 중단("정산집계를 다시 만드세요" · 폴백 없음) ③ 관리 VID 옵션이 있는 등록상품 = 상품 전체 관리(기존 규칙 그대로 · 판매 줄 짝은 그대로) ④ 판매 없이 비용만 있는 등록상품(상품조회·판매분석에 없음) = 출처 AI 판정 대상 ⑤ 판정 전 = 정산서 '관리 상품 확인 필요' 표시(금액 밖) · 계정·상품 조건 코드 없음(D-229).
- 근거: T-42 보고 `output\_분석_261115_T42_관리밖출처\보고.md`(dalbong1849 16258713629 보관비 8,235 · ljung0622 TTGW02 반출비 183,480 빠짐 · 원인 = 관리 상품ID 를 주문 줄 짝에서만 만듦 `settlement_statement_account.py:195~196`) · 비용 리포트 1,812개 직접 읽기 634.8초 실측(정산서마다 읽기 불가) · 짝 확인 95609464754→16258713629 · 95273555059→16157622592.
- 버린 대안: 판정표 줄만 추가(원인 남음) · 정산서마다 비용 리포트 직접 읽기(11분) · 옛 집계일 때 다른 방법으로 대신(폴백).
- 영향 범위: 정산 코드만(D-233) — `settlement_stats`·`settlement_statement_source`·`settlement_statement_account`·`settlement_scope_judge`·`tools/settlement_scope_judge.py` · T-38 S2 숫자 모듈도 같은 규칙.
- 상태: ACTIVE (구현 R185 ㉠ 5cacda6 · master 병합 R191 · 정산집계를 새로 만든 뒤부터 적용 · ⑤ 보완 D-252 · ④ 보완 D-255)

### D-245 [SETTLE_FAIL_ISOLATION] 정산 받기 — 한 달·한 곳 실패가 나머지를 막지 않음(월자료 실패 달 건너뛰기 · 밀크런/광고센터 분리) · 주문별 매출 실패 근거 파일 (2026-11-15, R185)
- 결정(소유자 2026-11-15 — 통제 세션 대화 원문 "1·2·3 모두 추천대로 진행해줘" · "오류부분도 수정해야 됨" · T-46 결함 목록 = output (37) 보고 B 7절): ① 월자료 한 종류의 한 달이 실패하면 그 달은 **그 회차 동안 다시 부르지 않고** 더 옛 달로 넘어감(회차 예산 = 받은 달 3개 그대로 · 실패 달은 다음 회차에 1번 더) ② 광고 받기 = 밀크런(윙 주소)과 광고센터(광고정산·매출성장광고)를 **따로** 세고 따로 실패 — 광고센터 500 이어도 밀크런은 최근부터 2달씩 · 실패 사유는 처리기록 '광고비' 실패 줄 · '남은 달' = 실행 뒤 다 받지 못한 달 수 ③ 주문별 매출 실패 때 `검증자료\월자료\{계정}\_실패_주문별매출_YYYYMM.json`(쪽별 줄 수·원본 건수·커서 빈칸 여부·응답 칸 이름 + 같은 키 줄 전부 · 고객 이름 칸 없음) — T-2 재현용 근거. ①②의 세부(회차 기억 = 실행 중 메모리 · 2달·3달 예산 유지)는 Claude 구현값.
- 근거(실측 · `output\_분석_261115_output37\보고_B_정산자료.md` 7절): ③ `settlement_docs.py` 종류별 `break` — 주문별 매출 4월 실패 계정은 1~3월 시도 0 · ④ hellojin 광고센터 GraphQL 500 → 밀크런 2511~2608 10달 빔(파일 2609·2610 만) · 주문별 매출 실패 달 응답은 저장되지 않고 로그에 커서 값 없음 → T-2·Difpick 중복은 **재현 불가**(받은 응답·로그로 원인 못 가림 → 코드 원인 수정 안 함 · 다음 실패 때 근거 파일이 남음 · 없으면 소유자 로그인 조회 스크립트 `output\_분석_261111_주문별매출\실측_A_1쪽멈춤.js`·`실측_B_Difpick중복.js`).
- 버린 대안: 실패하면 그 종류 멈춤(지금 — 목표 '1월부터 100%'와 다름) · 실패해도 매 바퀴 다시 부름(같은 실패 반복 · 쿠팡 요청 낭비) · 광고센터 실패 = 광고 전체 멈춤(밀크런은 광고센터와 무관).
- 영향 범위: 정산 코드만(D-233) — `settlement_docs`(`_Run.kind`·`collect(skip=)`·`fetch_order_detail` 근거) · `settlement_ads.collect(fatal=)` · `tools/settlement_download.py`(`DOC_FAILED` 회차 기억 · 광고 실패 줄) · 시험 P52 기대값(라이브 실패 달 뒤 옛 3달) · P56 신설.
- 상태: ACTIVE (부분 SUPERSEDED by D-373 — ① 월자료 실패 달 '그 회차 다시 안 부름' → 회차 3번까지)

### D-246 [SETTLE_BACKLOG_RENAME_MONTHLY] 정산 — 남은 소급 = 바퀴 끝 전 계정 다시 셈 · 계정 이름 바뀌어도 월자료·광고·정산현황 원문 이어 씀 · 정산예정기록 달별 파일 · 정산집계 최신 3개 (2026-11-15, R185)
- 결정(소유자 2026-11-15 — 통제 세션 대화 원문 "오류부분도 수정해야 됨" · "1·2·3 모두 추천대로 진행해줘" · T-46 결함 목록 = output (37) 보고 B 7절 ⑤⑥ · D-243 ③·② 정산 몫): ① [실행 결과 종합] '남은 소급' = 바퀴마다 끝에 **전 계정**(load_accounts)의 저장 자료로 다시 셈 — 판매분석(1/1~어제 빠진 날 · `_sales_left` 그대로) · 월자료(`_받은기록.json` 대비 받을 달 · RG 종류는 로켓그로스 계정만 · `settlement_docs.left_months`) · 광고(밀크런+광고센터 둘 다 받아야 그 달 끝 · `settlement_ads.left_months` — `collect` 의 '남은 달'도 같은 함수) · 받기 없음(파일만 읽음) · 계산 못 하면 '남은 소급 계산 실패 — 확인 필요' 대기 줄. ② 계정 이름 맞춤(`settlement_store.migrate_names` · 계정ID 기준)에 `검증자료\월자료\{계정}\`·`검증자료\광고\{계정}_*`·`정산현황_원문\{계정}\` 추가 — 지금 이름 쪽에 없으면 옮김 · 같은 이름이면 지금 이름 쪽 유지 + `_받은기록.json`(종류별 달 합집합)·`{계정}_광고.json`('캠페인 없음' 합집합) 합침 · 옛 쪽 겹친 파일 = `정산\보관\계정명바뀜\{옛 이름}\{월자료|광고|정산현황_원문}\` 로 이동(삭제 없음 · 빈 옛 폴더만 치움) · 요청형 월자료 작업 경로(`월자료/{계정}/…`)도 지금 이름. ③ `정산예정기록.jsonl` → 같은 폴더 `정산예정기록\YYYY-MM.jsonl`(수집일 달 · 지난 달 파일은 다시 안 씀) · 읽기 = 달 폴더가 있으면 그것만, 없으면 옛 한 파일(옮겨 온 분석 사본 호환) · 옛 파일은 첫 기록 때 임시 폴더에 달별로 나눠 쓴 뒤 이름 바꿈 → `정산\보관\YYYY-MM\` 로 이동(같은 줄은 개수만큼 빼서 중복 없음 · 끊긴 임시 폴더도 보관으로) · 읽는 곳 4곳(`settlement_ledger`·`settlement_statement_source`·`tools/settlement_download` 2곳)은 경로 인자 그대로. ④ 정산집계(`정산집계_yymmdd_HHMMSS.xlsx`)는 집계 쓸 때마다 최신 3개만 `output\정산\` · 나머지 `output\정산\보관\YYYY-MM\`(파일 이름 날짜) 로 이동 · 이름 규칙 밖 파일은 손대지 않음. 세부(폴더·보관 이름·합치는 규칙)는 Claude 구현값.
- 근거(실측): ① `settlement_runlog.Totals.add` 가 바퀴의 `left` 만 합침 · `_one_pass` 가 바퀴마다 새 RunLog · 로그인 못 한 계정·중단 바퀴·새 프로세스(22:47) 계정 빠짐(보고 B ⑤) · 재현 시험 P57(옛 코드 = 로그인 실패 계정 줄 없음). ② hide4u '(계정사용불가)' 뒤 월자료 두 폴더(19개씩)·광고 밀크런 202610 두 벌·정산현황 원문 두 폴더 · 재현 P24 (a2) · 운용 PC 사본 실행 = 한 폴더(남은 달 18 그대로)·겹친 옛 파일 21개 보관. ③ output (37) 정산예정기록 1파일 19MB(26,659줄) → 사본 변환 = 2026-10 8.4MB · 2026-11 10.8MB · 읽은 결과 10,063줄 변환 전후 같음(0.4초→0.5초). ④ 정산집계 74개(약 180MB) → 사본 실행 = 3개 남김 · 71개 보관(2026-10 47 · 2026-11 24) · 읽는 코드 검색 = 쓰기 1곳(`cmd_stats`)·정산서 도구는 `--stats` 경로 인자·ui·bat/ps1/spec 0건.
- 버린 대안: ① 그 바퀴에 돈 계정만(지금 — 적게 셈 · '다 받았다' 오판) · 남은 값을 회차 파일로 이어 받기(새 프로세스·중단 바퀴는 여전히 빠짐) ② 옛 이름 폴더도 따로 읽기(받기마다 처음부터 다시 · 분석이 갈림) · 겹친 옛 파일 삭제(⛔output 삭제 금지) ③ 한 파일 유지(내보내기 변경분이 매일 19MB) · 수집일 대신 정산일 달(같은 조회 묶음이 여러 파일로 갈림) ④ 오래된 집계 삭제(⛔).
- 영향 범위: 정산 코드만(D-233) — `tools/settlement_download.py`(`_backlog_left`·`_one_pass`·`cmd_stats`) · `settlement_docs.left_months` · `settlement_ads.left_months` · `settlement_store`(`migrate_names` 보조 · `rotate_stats` · `RG_RAW_DIRNAME`) · `settlement_forecast`(`record`·`load`·`month_dir`) · 시험 P24 (a2)·P34·P51·P57·P58. ⚠ ㉢ 내보내기 도구가 `정산예정기록.jsonl` 을 이름으로 다루면 `정산예정기록\` 폴더로 바꿔야 함(통제 세션 병합 때 확인).
- 상태: ACTIVE

### D-247 [SETTLE_SUSPENDED_PENDING] 정지 계정의 요청됨·요청예정 = 회차 완료 판단에서 뺌 · 받기는 계속 · [실행 결과 종합] '정지 계정 대기 N건 — 확인 필요' (2026-11-15, R185)
- 결정(소유자 2026-11-15 원문 — 통제 세션 질문(T-46 ⑦ 방안 A/B)에 "A안 (추천)" 선택 · 통제 세션 전달): ① 앱 상태 파일 `output\_계정정지.json`(D-199 · 읽기만)에 있는 계정의 요청예정·요청됨 작업은 회차 완료 판단 수(`_pending_jobs`)에서 뺌 ② 받기 시도는 D-215 대로 매 바퀴 계속(정상화되면 바로 받아짐) ③ [실행 결과 종합]에 '정지 계정 대기 N건 — 확인 필요(완료 판단에서 뺌 · 받기는 계속 D-215)' + 계정별 건수 따로 표시 · 판정 = '일부 실패 --> 확인 필요' · 회차 완료 상태 = '완료·실패 확인'(완료 문구 '정지 계정 받기 대기' 계정). 계정 맞춤 = 계정명 끝 '-계정ID'(display_name).
- 근거(실측): output (37) `_계정정지.json` = hide4u·zkdlsemrnjs(11-11 앱 판정) · `정산\_요청기록.json` 요청됨/요청예정 = hide4u 9건뿐 · 11-12 뒤 같은 9건 받기 500 126번 · `plan_after_pass` 'later' 반복 → 회차 '완료' 못 함(17:55·07:00 까지 · 보고 B ⑦) · 재현 시험 P59(옛 코드 대기 10건 → 9건 뺌) · 사본 실행 = 완료 판단 대기 9→0 · 다음 행동 later→done.
- 버린 대안: B안 — 같은 회차 쿠팡 500 이 N번 넘은 작업만 뺌(정지 상태 파일 없는 계정도 잡지만 판정 복잡 · 바퀴마다 500 요청 남음) · 정지 계정 받기 중단(D-215 와 다름).
- 영향 범위: 정산 코드만(D-233) — `tools/settlement_download.py`(`_open_jobs`·`_pending_jobs`·`_suspended_pending`·`_watch_failures`·요약 4곳) · `settlement_runlog.result_block(suspended=)`·`RunLog.summary(suspended=)` · 시험 P59. 앱 `account_suspend` 는 읽기만(수정 없음).
- 상태: ACTIVE

### D-248 [RANK_CATCHUP_RECENT_DAYS] 지난 칸 ③ 보충(D-220) = 최근 7일 안 ③ 을 못 끝낸 날 전부(최근 날부터) · 보충이 빈 칸을 남긴 날은 다음 실행이 다시 · 실행 결과 종합 '순위 빈 칸'에 보충 칸 빈 칸 포함 (2026-11-15, R185)
- 결정(통제 세션이 전한 소유자 승인 2026-11-15 "1·2·3 모두 추천대로 진행해줘"·"오류부분도 수정해야 됨" — 그 작업 지시 T-47 5번 · **'7일' = Claude 제안(소유자 원문 아님) — 소유자가 다른 값을 말하면 그 값**): ① 단계 기록 파일(`output/쿠팡데이타분석_실행단계.json`)에 실행 날짜별 마지막 단계 `days`(최근 14일)를 더 남긴다(맨 위 date·stage·at = 재부팅 복구·정산이 읽는 값 그대로 · 날짜 = 실행 시작일 — 자정 넘어 끝나도 그 실행 날짜). 'days' 없는 옛 파일 = 맨 위 한 날로 이어받음. ② 전체실행·무인·재부팅 복구가 오늘 ③·재고 역기록·빈 칸 재시도(D-173) 뒤, 오늘 앞 7일 안에서 단계가 'sales'·'ranks'인 날마다 그 칸 ③ 1회(최근 날부터 · 빈 칸만). 빈 칸 0 이면 그날 'done'(남으면 다음 실행이 다시). 날짜 지정·① 단독·오늘 기록·중지 요청은 안 함(D-220 ③ 그대로). ③ [실행 결과 종합] — ③ 줄 측정 값은 오늘 실행 그대로 + '지난 칸 보충 월.일 측정 N · 월.일 빈 칸 N' · 판정과 한 줄 요약 '순위 빈 칸' = 오늘 칸 + 보충 칸 빈 칸.
- 근거: output (37) 보고 A(`D:\coupang-analytics\output\_분석_261115_output37\보고_A_앱실행.md` 3-1·4-4·4-5절) — 11-13·11-14 이틀 연속 ③ 이 07:00 에 끊겨 단계 기록이 11-14 'ranks' 로 덮여 11.13(24칸)이 자동 보충 대상에서 빠짐 · 11-12 보충이 11.11 154칸을 남겼는데 다시 안 봄 · 한 줄 요약 '순위 빈 칸 0'(줄 6812)인데 11.11 칸 154칸 남음(줄 6795). 재현 `tools/pin_run_plan.py` P14(7일 안 여러 날·완료 표시·종합 빈 칸)·P15(날짜별 기록 파일) 옛 코드 실패(보충 1일만) → 통과.
- 버린 대안: 결과 워크북의 빈 칸으로 날짜 고르기(뒤에 더한 키워드의 옛 날 빈 칸까지 검색 — 11.12 4칸·11.10 31칸 · ③ 이 이미 12시간) · 범위 제한 없음(밤 시간 안에 못 끝남) · 오래된 날부터(최근 순위가 더 쓸모 있음 · 오래된 날은 7일 지나면 빠짐 — Claude 판단).
- 남는 영향(Claude 판단·소유자 지시 아님): 배포 직후 옛 파일엔 마지막 하루(11-14)만 있어 11.13·11.11 은 자동 보충 안 됨(사람이 '날짜 지정' T-20) · 보충 날이 많을수록 실행 시간·IP 사용 늘어남(③ 한 번 11.6~12.4시간 — 07:00 에 끊기면 남은 날은 다음 실행).
- 영향 범위: `src/coupang_analytics/pipeline_paths.py`(`write_run_stage` day·`run_days`·`mark_run_day`) · `pipeline_stages.py`(`_CATCHUP_DAYS`·`_missed_rank_days`·`_catch_up_missed_ranks`·`run_stages`) · `run_result.py`(`_rank_line`·`_unfilled_all`) · `tools/pin_run_plan.py` P14·P15. HQ 포팅 대상.
- 상태: ACTIVE (부분 SUPERSEDED by D-253 — 보충 범위 7일 → 3일 · 날짜 지정 실행의 날짜별 기록 = D-254 · 부분 SUPERSEDED by D-257 — 보충 = 그 날짜에 재는 칸만 · 끝까지 돈 실행도 그날 칸 빈 칸이 남으면 날짜별 기록 'ranks'(다음 실행이 보충))

### D-249 [RANK_DEAD_IP_DENIED] ③ '검색창 없음'(IP 불량 D-090) 화면이 쿠팡 접근차단 화면(Access Denied·사용권한 등)이면 차단으로 기록 — 그 IP 차단 목록 등록·차단 감지 수 · 흐름·검색 간격은 그대로 (2026-11-15, R185)
- 결정(통제 세션이 전한 소유자 승인 2026-11-15 "오류부분도 수정해야 됨" — T-47 4번 · '검색 간격·IP 정책 D-053·D-090 은 바꾸지 말 것'): 검색창이 없을 때 창의 화면에 차단 판정 단어(`_BLOCK_PAGE_MARKERS`)가 있으면 차단 — 증거 판정 단어 '검색창 없음·{단어}' · 차단 감지 수에 셈(IP 불량 수에서 뺌) · drive_rank 가 그 egress 를 차단 목록(`proxy_blocklist` · 사유 'Akamai 접근차단(검색창 없음 화면)')에 남김. 바로 새 IP·못 잰 키워드 미룸·성공 없이 15번 연속이면 마침(D-090)은 그대로. 차단 단어 없는 검색창 없음 화면은 D-090 그대로(목록에 안 남김).
- 근거: output (37) 11-15 `_순위차단\` 증거 — 판정 '검색창 없음' 14건 전부 화면 제목 'Access Denied'(예 `1115_065406_466658_홈.txt` 본문 "You don't have permission to access … on this server") · 보고 A 2-3절·4-6절 · 11-14 은 이 경우 82번(차단 감지 50번보다 많음). D-090 이 버린 대안('쿠팡 차단 확정 아님')의 전제가 이 화면엔 안 맞음. 재현 `tools/test_proxy_patch.py` `test_semi_dead_ip_denied_is_block` 옛 코드 실패 → 통과(16 PASS).
- 버린 대안: 검색창 없음 전부를 차단으로(업체 회전 IP 가 곧 바뀌는 진짜 IP 불량까지 72시간 막힘 — D-090 근거) · 15번 연속 마침 규칙에서 접근차단 빼기(D-090 바꾸지 말라는 지시).
- 남는 영향(Claude 판단): 15번 연속으로 마칠 때의 마지막 IP 는 목록에 안 남음(마치는 경로 그대로) · 11-12 이전 증거는 없어 그 날짜들도 같았는지 미확인.
- 영향 범위: `src/coupang_analytics/pipeline_ranks.py`(`_DEAD_BLOCK`·`_denied_marker`·`_semi_on_dead`·`drive_rank`) · `tools/test_proxy_patch.py`. HQ 포팅 대상.
- 상태: ACTIVE

### D-250 [APP_RUN_SUMMARY_GAPS] 앱 실행 기록 빈틈 메움 — ③ 통합판매현황 '전일' = 실행 날짜 전날 · 회사 재고현황 못 읽음 = ❌ 오류 · 앱 창을 닫으면 닫은 단계 + [실행 결과 종합] '사람 중지 --> 중단' (2026-11-15, R185)
- 결정(통제 세션이 전한 소유자 승인 2026-11-15 "오류부분도 수정해야 됨" — T-47 1·2·3번): ① ③(보충 포함)이 다시 그리는 통합판매현황의 '전일' = 그 실행 시작일의 전날(순위 탭 단독은 오늘 기준 그대로). ② 회사 재고현황을 읽다 실패(머리 못 찾음 등)하면 '❌ … 못 채움(재고현황 '탭' 읽기 실패 …)' 한 줄 → 종합 오류 수에 셈 · 값은 기존 규칙(D-156·D-157 · 주입 안 함) · 링크 미설정·서비스계정 키 없음은 안내 그대로(오류 아님). ③ 사람이 앱 창을 닫으면(closeEvent) '[앱 종료] 사람이 앱 창을 닫음 — {단계} 도중' + 도는 실행의 종합(판정 `사람 중지 --> 중단` · 그 단계 '사람이 창을 닫아 멈춤')을 바로 남김 · 순위 중지 신호 · 도는 실행이 없으면 닫힘 한 줄 · 무인이 스스로 끝낼 때는 안 씀 · 닫기를 막지 않음(D-020 그대로).
- 근거: 보고 A 4-1(11-13 06:22 `[통합판매현황] 갱신 — 전일 11.12 0개·0원 · 이번 달 누계 0원 · 계정 35개(전일 미수집 35)` 줄 5329 → 결과 구글시트 반영 · 백업 `output\_분석_261115_output37\output\백업\결과시트_261113_180021.xlsx` · 원인 `pipeline_ranks.py:274` 실행 날짜 안 넘김) · 4-2(계정목록 회사보유재고 80칸 → 0칸 11-13~ · ⚠ 만) · 4-3(11-13·11-14 로그가 순위 한 줄 중간에서 끝남 · closeEvent 없음). 재현 → 통과: `tools/pin_login_ranks.py` T47-1 · `tools/verify_registry_offline.py` R23b · `tools/verify_ui_log_tabs_offline.py` s8.
- 버린 대안: 닫기를 막고 확인 창(무인 종료·정산 함께 종료 흐름이 바뀜) · 재고현황 못 읽으면 지난 값 유지(값 규칙 D-156·D-157 바꾸지 말라는 지시).
- 남는 영향(Claude 판단): 작업 관리자 강제 종료·전원 차단·Windows 가 프로세스를 끝내는 경우는 closeEvent 가 안 와 여전히 기록 없음(07:00 종료 원인 T-50 은 소유자 확인) · ① 끝(`pipeline.py` `_finalize_run`)의 통합판매현황은 그대로 오늘 기준(① 은 18시대에 끝남).
- 영향 범위: `src/coupang_analytics/pipeline_ranks.py`(`track_ranks_stage` run_date) · `pipeline_stages.py`(run_date 넘김) · `pipeline_gsheet.py`(`inject_company_stock`) · `run_result.py`(`ACTIVE`·`close_now`·`CLOSED`) · `ui/app_qt.py`(`closeEvent`·`_auto_quit`). HQ 포팅 대상.
- 상태: ACTIVE

### D-251 [CONSIGNOR_STATEMENT_PENDING_LABEL] 위탁자 정산서 — 예정분 이름 = '정산 예정 금액(쿠팡 미확정 금액)' (2026-11-15, R191)
- 결정(소유자 2026-11-15 원문 — 통제 세션 대화 답 "정산 예정 금핵(쿠팡 미확정 금액)" · '금핵' = '금액' 오타로 읽음): 1쪽 큰 숫자 아래 줄 = '이 중 정산 예정 금액(쿠팡 미확정 금액) ○○원' — D-242 ①의 '이 중 쿠팡 확정 전 금액' 문구를 대체.
- 적용(Claude 적용 — 소유자 원문 축약): 2쪽 상품표 예정분 회색 줄 이름 = '└ 정산 예정(쿠팡 미확정)' · 금액·계산 규칙은 그대로(D-241·D-242).
- 근거: 샘플 시트·PDF real_1000~1007 다시 그림(R189) — 금액 변화 0 · 10월 json 3개 이름 말고 같음 대조 · 백업 `D:\coupang-analytics\output\_샘플_261115_위탁자정산서\_백업\명칭변경전_261115\`.
- 버린 대안: '쿠팡 확정 전 금액'(D-242 문구 — 소유자가 바꿈 · 바꾼 이유 원문 없음).
- 영향 범위: T-38 그리기 모듈(`settlement_consignor_gsheet.py` · 구현 전) · 샘플 시트·PDF(반영 끝) · CURRENT_RULES 12절.
- 상태: ACTIVE (부분 SUPERSEDED by D-258·D-259 — 1쪽 문구)

### D-252 [SCOPE_COST_ONLY_NO_OPTION] 비용만 있는 상품 짝 — 옵션ID 없는 비용 줄·상품 못 찾은 보상 줄도 '옵션별 등록상품'에 남김(조용히 빠짐 막기 · D-244 ⑤ 보완) (2026-11-16, R192)
- 결정(소유자 2026-11-16 원문 — 통제 세션 질문 '결함 1 수정 뒤 다시 빌드할지'에 "결함 1 수정 후 다시 빌드해서 배포해"): ① 비용 리포트 줄에 등록상품ID 만 있고 옵션ID 가 없으면(반출 배송 서비스비 상품 줄) 옵션ID 칸을 비운 짝을 남김 — 정산서·prepare 는 빈 칸을 등록상품마다 따로인 자리 키 `(옵션 없음) {등록상품ID}`(`settlement_statement_source.no_option_key`)로 읽음 ② 옵션으로 상품을 못 찾은 재고 손실 보상 줄('옵션 {옵션ID}' 상품 · 기존 집계 규칙 그대로)도 그 옵션ID 로 짝을 남김 — 옵션이 관리 VID 면 관리, 아니면 비용만 있는 상품과 같게 출처 판정 대상 + '관리 상품 확인 필요'(금액 밖). 묶음 줄(여러 상품·상품 없음)은 전처럼 뺌. ①②의 자리 키·'옵션 …' 상품을 판정 대상에 넣는 방식은 Claude 구현값.
- 근거(실측 · `D:\coupang-analytics\output\_배포검증\R191_261115\시뮬레이션\보고_B_정산.md` B8 ④-1): `settlement_stats._add_costs` 가 `c.option_id` 있을 때만 짝을 남김 → seankim137 16377117417 빔프로젝터거치대(반출 배송 서비스비 2,420원 · T-42 '관리 맞음')가 관리·확인 필요·판정 대상 어디에도 없음 · T-42 후보 152개 중 15개 · 관리 시작 뒤 15,894원(seankim137 2,420 + tellace83 13,474 보상 줄). 재현 = 수정 전 `aggregate` 짝 0개(집계 금액 2,420 은 있음) · 시험 `test_cost_only_scope` 두 경우 추가 → 수정 뒤 통과. 11-03 자료 28곳 다시 실행(`결과\b9_결함1수정_재실행2.log` · `b8_compare.json` ↔ `b8_compare_수정전.json`): 금액 차이 0 · 바뀐 것 = '관리 상품 확인 필요' 시트(seankim137 +1 · ljung0622 +3 · tellace83 +4줄) · 옵션별 등록상품 1,724→1,889줄 · seankim137 판정 요청에 16377117417 들어감.
- 버린 대안: 옵션ID 칸에 등록상품ID 를 넣음(VID 와 섞임) · 빈 옵션ID 하나로 읽음(한 계정 여러 상품이 한 키로 겹침) · 상품 못 찾은 보상 줄은 그대로 둠(13,474원이 조용히 빠짐 — 오류 정의).
- 영향 범위: 정산 코드만(D-233) — `settlement_stats._add_costs` · `settlement_statement_source.cost_options`·`no_option_key` · 시험 `tools/verify_settlement_statements_offline.py` `test_cost_only_scope`. 정산집계를 새로 만든 뒤부터 적용(D-244 와 같음).
- 상태: ACTIVE

### D-253 [RANK_CATCHUP_3DAYS] 지난 칸 ③ 보충 범위 = 오늘 앞 3일(D-248 의 '7일' 대체) (2026-11-16, R193)
- 결정(소유자 2026-11-16 — 통제 세션 질문 'T-52 ① 순위가 끊긴 지난 날을 다시 채우는 범위를 몇 일로 할까요?'에 "3일" 선택 · 앞 요청 원문 "수정해줘"): `pipeline_stages._CATCHUP_DAYS` = 3 — 오늘 앞 3일 안에서 ③ 을 못 끝낸 날만 자동 보충(최근 날부터 · 그 밖은 사람이 '날짜 지정' T-20). 같은 질문의 ② output 보관 이동 기준(D-243 ② Claude 구현값)은 "지금 기준 유지 (추천)" — 그대로.
- 근거: D-248 의 7일 = Claude 제안(소유자 원문 아님 · STATE T-52) · 보충 날이 많을수록 밤 실행 시간·IP 사용 늘어남(③ 한 번 11.6~12.4시간 · D-248 남는 영향). 시험 `tools/pin_run_plan.py` P14 = 범위 상수 기준(끝 날 포함 · 하루 더 앞 제외)으로 고침 → 통과.
- 버린 대안: 7일 유지(소유자가 바꿈) · 14일.
- 영향 범위: `src/coupang_analytics/pipeline_stages.py`(`_CATCHUP_DAYS`) · `tools/pin_run_plan.py` P14. HQ 포팅 대상.
- 상태: ACTIVE

### D-254 [RANK_DESIGNATED_KEEPS_DAY] 날짜 지정 실행은 오늘 날짜별 단계 기록(days[오늘])을 바꾸지 않음 — 그날 정기 ③ 미완료가 다음 실행 보충에 남게 (2026-11-16, R193)
- 결정(소유자 2026-11-16 원문 "수정해줘" — STATE T-54 를 가리킴): 날짜 지정 전체실행(`designated=True`)의 단계 기록은 맨 위 `date`·`stage`·`at` 만 지금처럼 갱신하고 `days[오늘]` 은 그대로 둔다(`write_run_stage(record_day=False)`). 정기·무인 실행은 그대로. 날짜 지정 실행이 고친 그 날 칸을 'done' 으로 표시하는 확장은 안 함(범위 밖 · Claude 판단).
- 근거(실측 · `D:\coupang-analytics\output\_배포검증\R191_261115\시뮬레이션\보고_A_앱_내보내기.md` A5): 정기 ③ 이 끊겨 오늘이 'sales' 로 남은 날 같은 날 날짜 지정 실행이 끝나면 days[오늘]='done' → 다음 날 D-248 보충에서 빠짐(옛 코드도 같음 · D-248 에 정의 없음). 재현 시험 P16(수정 전 `{'2026-11-16': 'done'}` 로 실패 → 수정 뒤 'sales' 유지 · 다음 날 보충 대상 = [오늘] · 정기 대조 = 'done'). 맨 위 값 = 정산 watch(`settlement_watch.read_marker` — 전체실행 뒤 ① 완료 신호 `ui/app_qt.py` start_settlement_watch since)·재부팅 복구(`read_run_stage`)가 읽으므로 유지.
- 버린 대안: 날짜 지정 실행이 단계 기록을 아예 안 씀(정산 watch 가 ① 완료를 못 봄) · 지정 날짜 칸을 'done' 표시(이번 범위 밖).
- 영향 범위: `src/coupang_analytics/pipeline_paths.py`(`write_run_stage` record_day) · `pipeline_stages.py`(`run_stages` 3곳) · `tools/pin_run_plan.py` P16. HQ 포팅 대상.
- 상태: ACTIVE

### D-255 [SCOPE_COST_ONLY_SOLD_EXCLUDED] prepare '비용만' 판정 대상 = 정산서와 같은 기준 — 정산 파일 주문 줄에 나온 등록상품은 뺌 · prepare `--settle-dir` 필수 (2026-11-16, R193)
- 결정(소유자 2026-11-16 원문 "수정해줘" — STATE T-53 을 가리킴): `settlement_scope_judge.targets` 의 '비용만' 대상(`settlement_statement_scope.cost_only`)이 정산 파일 주문 줄(옵션ID·등록상품ID 있는 줄)에 나온 등록상품을 뺀다 — 정산서 `_scope` 의 opt2pid 와 같은 함수(`option_products`)·같은 파일 목록(`settlement_statement_context.settle_files`). prepare(`tools/settlement_scope_judge.py`)는 `--settle-dir`(output\정산) 필수 · `파일\` 폴더 없으면 ❌ 시작 전 중단(폴백 없음). 정산집계 '상품별 월별' 칸으로 대신하는 방식은 버림(Claude 판단 · 아래 근거).
- 근거(실측 · `D:\coupang-analytics\output\_배포검증\R191_261115\시뮬레이션\보고_B_정산.md` B8 ④-2): 고치기 전 prepare 판정 대상이 옛 코드보다 740개 많고 그중 579개가 판매 있음(ski1121·Difpick 등) · 재현 = `test_cost_only_scope` 에 '비용 줄 + 주문 줄(판매·같은 달 취소)' 상품 → 수정 전 실패 · 수정 뒤 통과 · prepare 쪽 sold = 정산서 opt2pid 같은 집합 시험. 11-03 자료(`…\시뮬레이션\결과\b8_judge_targets_T53후.json`): 판정 대상 10,459 → 9,880(579 빠짐 · 판매 없는 상품 잘못 뺀 것 0) · seankim137 16377117417·tellace83 '옵션 …' 4개·ljung0622 16157622592 그대로 남음. 정산집계 칸 방식 = 같은 달 판매 뒤 취소(합 0) 줄 때문에 정산서 기준과 744개 중 34개 어긋남(`scratchpad\t53\measure_t53.json`). 정산 파일 1,323개 읽기 약 156초 더 걸림.
- 버린 대안: 정산집계 '상품별 월별' 주문 칸 0 아닌 줄(취소 합 0 상품을 놓침) · 그대로 둠(AI 판정 부담·'비용만' 이름표 틀림).
- 남는 일(사실 · 소유자 판단 필요 → STATE T-55): 빠진 579개 = 판매 줄은 있지만 상품조회·판매분석에 없는 상품 — D-244 전처럼 출처 AI 판정을 받지 않고, 정산서에서도 대장 VID·같은 상품명·판정표 '관리'가 아니면 관리 밖(표시 없음 · 예전부터의 동작) · 위탁 계정 gbseller808 29·hk66597582 18·tellace83 23·ljung0622 16 등 포함.
- 영향 범위: 정산 코드만(D-233) — `settlement_statement_scope`(`option_products`·`cost_only` sold) · `settlement_statement_account`(opt2pid 같은 식으로 바꿈) · `settlement_statement_context`(`settle_files`) · `settlement_scope_judge.targets` · `tools/settlement_scope_judge.py`(`--settle-dir`·`_sold`) · 시험 `test_cost_only_scope`.
- 상태: ACTIVE

### D-256 [SCOPE_SOLD_UNLISTED_JUDGED] 판매 줄은 있는데 상품조회·판매분석에 없는 상품도 출처 AI 판정 대상 (2026-11-16, R193)
- 결정(소유자 2026-11-16 원문 — 통제 세션 안내 'T-53 수정으로 AI 판정 대상에서 빠진 상품 579개 · 판매 기록은 있지만 상품조회·판매분석에는 없는 상품'에 "관리 상품이면 이 상품들도 AI 판정 대상에 올려줘"): prepare 판정 대상(`settlement_scope_judge.targets`)에 정산 파일 주문 줄에 나온 등록상품 중 상품조회·판매분석에 없고 관리 VID 옵션(대장 VID·같은 상품명·판정표 '관리')도 없는 것을 넣는다 — 상품명 = 정산 파일 줄 상품명 · 판매방식 = 로켓그로스 줄 있으면 RFM, 아니면 NORMAL · 등록일 빈 칸. '비용만' 이름(D-255)은 그대로(판매 줄 상품은 '비용만' 아님). 정산서 쪽 '관리 상품 확인 필요' 표시는 이번에 안 바꿈(판정표에 '관리'로 들어오면 관리 · Claude 판단 — 소유자 요청 범위 = 판정 대상).
- 근거: D-255 실측(11-03 자료 579개 = 판매 줄 있음·상품조회·판매분석에 없음 · 위탁 계정 gbseller808 29·hk66597582 18·tellace83 23·ljung0622 16 포함) · 시험 `test_cost_only_scope`(판매만 상품 8758835645·비용+판매 상품 16700000000 = 판정 대상 · 관리 VID 옵션 상품 16142251017 = 뺌 · 수정 전 코드 = 둘 다 없음).
- 버린 대안: 비용 줄 있는 판매 상품만(판매만 있는 상품이 같은 이유로 빠짐) · 정산서 '확인 필요' 표시까지(요청 밖 · 판정 대상이 늘어난 뒤 필요하면 따로).
- 영향 범위: 정산 코드만(D-233) — `settlement_statement_scope.sold_products` · `settlement_scope_judge.targets`(sold = 상품별 이름·옵션·채널) · `tools/settlement_scope_judge.py` `_sold` · 시험 `test_cost_only_scope`.
- 상태: ACTIVE

### D-257 [RANK_SPLIT_3DAY_PROMO_10D] ③ 순위 = 체험단 시작일부터 10일 매일 · 나머지는 계정 3묶음이 하루씩(3일 간격) · 안 재는 칸 = 빈 칸+옅은 회색(빈 칸 집계·재시도·보충 제외) · 그날 못 잰 칸 = 다음 실행 보충 (2026-11-16, R197)
- 결정(소유자 2026-11-16 원문 "노출 순위 검색을 체험단은 시작일로부터 10일간 노출 순위를 검색하고, 나머지는 3일간격으로 안분해서 진행해줘, 노출순위 검색 부하를 줄이는 것이 목표이므로 체함단을 제외한 나머지를 무조건 3일 간격으로 하면 부하 감소 효과가 없으므로 계정별로 안분해서 노출순위를 검색하도록 해줘. 너가 방법을 제시해줘." → 방법안(`docs/plans/rank-load-split-plan-2026-11-16.md`)에 소유자 답 "추천대로 4개 모두 진행해줘"):
  ① 재는 날 = **칸의 날짜** 기준(실행 날짜 아님 — 보충·날짜 지정·재부팅 복구·순위 탭 모두 같음): 새 규칙 시작일 전 날짜 · 체험단 시작일 ≤ 날짜 ≤ 시작일+9일(시작일 포함 10일 · 시작일 = 직원 입력 마케팅 시작일 우선, 없으면 체험단 시트 '체험단시작일' 최근 회차 D-122 — D-121 배경과 같은 기준) · 순위 기록이 한 번도 없는 키워드(새 상품·새 키워드·새 계정 첫 측정) · 그 계정 묶음 차례 = (날짜 − 시작일).일수 mod 3. 순위 제외(판매중지 등 D-114 · VID 없음 D-030)는 먼저 그대로.
  ② 계정 = 결과 사업자 시트(열쇠 = 첫 계정ID · 없으면 시트 이름) → 묶음 가·나·다: 처음 한 번 순위 대상 키워드 수가 큰 계정부터 지금 합이 가장 적은 묶음에(동률 = 앞 묶음 · 이름 순) · 숨긴 시트 `_순위묶음`(1행 시작일 · 사업자·계정ID·묶음·배정일)에 고정 · 시작일 = 새 빌드가 처음 배정한 실행 날짜 · 새 계정 = 그때 가장 가벼운 묶음 · 시트가 사라진 계정 = 줄 지움 · **자동 다시 나누기 없음**(3일 간격 보장 · 다시 나누기 = 소유자 요청 때 새 D). ③ 시작 때마다 로그 '[순위 묶음] 오늘(월.일) = 가 묶음 · 묶음별 키워드 …'.
  ③ 안 재는 칸 = 값을 쓰지 않음(빈 칸) + 옅은 회색 F2F2F2(값 없는 칸만 · 시작일 전·판매중지·VID 없음은 칠하지 않음 · 매 실행 칸 날짜로 다시 칠함) · ③ 검색 목록·바퀴 남은 빈 칸(D-053)·'순위 빈 칸 --> 확인 필요'와 1회 재시도(D-173)·지난 칸 보충(D-248·D-253)·[데이터점검] '판매중인데 순위 공란'에서 모두 빠짐(`_rank_todo` 한 곳). 결과 구글시트는 통계 미러로 같은 색.
  ④ 실패 칸: 실행이 끝까지 가도 그날 칸 빈 칸(재는 칸만)이 재시도 뒤 남으면 날짜별 기록 `days[그날]` = 'ranks'(맨 위 date·stage = 'done' 그대로 — 재부팅 복구·정산 감시 영향 없음) → 다음 실행이 오늘 ③ 뒤 그 칸 빈 칸만 보충(D-253 3일 · 다 채우면 'done'). 날짜 지정 실행은 D-254 그대로.
  ⑤ ③ 의 옛 '마케팅 상품 1개월 매일·나머지 3일 주기'(`has_marketing`·`product_due` — 마케팅 칸이 비어 꺼져 있던 규칙) 줄은 ③ 에서 이 규칙으로 바꿈 · ① 판매수집 쪽 옛 게이트(`pipeline.py`·`pipeline_process.py`)는 그대로.
- 근거(실측): 11-15 회차 ③ 대상 376칸 중 100칸 측정 · 받은 IP 71% Access Denied · 03:18 IP 불량 15번 연속 멈춤(T-56 보고 C · output (38) 보고 A 13·36·80줄) · 마스터(`D:\coupang-analytics\output\_분석_261116_output38\output\쿠팡데이타분석_통계.xlsx`) 순위 대상 키워드 376 · 31시트 → 묶음 시험 127·125·124(계정 수 해시 나누기 116~133) · 체험단 10일 안 키워드 8~64(시작일 25건) → 하루 예상 130~170(지금의 35~45% · 추정). 재현: `tools/pin_login_ranks.py` R1(배정·날짜별 묶음·체험단 10일·첫 측정·시작일 전·새/사라진 계정)·R2(쉬는 칸 검색 안 함·빈 칸 0·데이터점검 제외)·T47-1(묶음 = 실행 날짜) · `tools/pin_apply_style.py` S11(회색 칸) · `tools/pin_run_plan.py` P17(그날 빈 칸 → 'ranks' → 다음 날 보충) — 옛 코드 실패(P17 = days 'done' · 나머지 = `rank_schedule` 없음) → 통과.
- 버린 대안: 전 계정 같은 날 3일 간격(그날 부하 그대로 — 소유자 원문) · 계정 수 기준 나누기(±7%) · 매일 다시 나누기(간격이 깨짐) · 묶음을 JSON 파일에 저장(서식이 같은 값을 읽어야 함) · 쉬는 칸 '-'(옛 미측정 표시라 다시 재는 대상)·직전 값 복사(잰 값처럼 보임)·빈 칸 그대로(실패 칸과 구분 안 됨) · 실패 칸 다음 차례까지 기다림(공백 6일) · 새 키워드도 묶음 차례까지(첫 값 최대 2일 늦음 · 매뉴얼 '다음 실행부터 순위' 와 어긋남) · 검색 간격(45~75초) 변경(금지).
- 남는 영향(Claude 판단·소유자 지시 아님): 보충한 칸은 다음 날 검색한 값(D-220 과 같음) · 결과 마스터를 구글시트에서 되살리면 `_순위묶음` 이 없어 다시 처음 배정(한 주기 간격 어긋남 · 로그 '처음 배정') · 계정별 키워드가 늘어도 묶음은 안 옮김(로그로 치우침 확인) · 통합판매현황 ⑤ '계정 순위' = 판매금액 순위라 영향 없음.
- 영향 범위: 새 `src/coupang_analytics/rank_schedule.py` · `pipeline_ranks.py`(`_rank_todo`·`track_ranks_stage`) · `pipeline_stages.py`(`run_stages` 끝 기록) · `workbook_common.py`(`_RANKGRP_SHEET`·특수 시트) · `workbook.py`(특수 시트 목록·`data_quality_summary`) · `workbook_render.py`(`_style_keyword_rows` 회색) · `tools/build_staff_manual.py`(문구 3곳) · 시험 3종. `pipeline.py`·`config.py`·구글시트 코드 수정 없음. 운용 PC = 배포 zip 설치 뒤. HQ 포팅 대상.
- 상태: ACTIVE (부분 SUPERSEDED by D-362 — 체험단 외 '계정 3묶음 3일 간격' → 격일(2묶음 · 옛 3묶음 기록 보존 D-364 ⑧) · 체험단 시작일부터 10일 매일은 그대로)

### D-258 [CONSIGNOR_STATEMENT_PENDING_LABEL2] 위탁자 정산서 1쪽 큰 카드 예정분 문구 = '정산 금액중 쿠팡 미확정 금액' (2026-11-16, R198)
- 결정(소유자 2026-11-16 원문 — 통제 세션 대화, 1쪽 큰 카드 캡처와 함께): "캡처 화면에서 "이 중 정산 예정 금액(쿠팡 미확정 금액) " --> "정산 금액중 쿠팡 미확정 금액" ==> 이렇게 변경해줘, 구글 시트(4명)는 지금 변경하고, 프로그램은 별도 세션에서 변경 작업 해줘." → 1쪽 큰 카드(이번 정산 금액) 큰 숫자 아래 줄 이름 = '정산 금액중 쿠팡 미확정 금액'(소유자 원문 글자·띄어쓰기 그대로 · 뒤 금액 '○○원 (바뀔 수 있음)'은 그대로) — D-251 의 '이 중 정산 예정 금액(쿠팡 미확정 금액)' 대체.
- 바꾸지 않음(소유자 요청 = 1쪽 문구 하나): 2쪽 상품표 예정분 회색 줄 '└ 정산 예정(쿠팡 미확정)'(D-251) · 다른 화면·기존 위탁정산서의 '정산 예정' 낱말(D-153 표시 등) · 금액·계산 규칙(D-241·D-242).
- 근거: 소유자 원문(위) · 캡처 = 1쪽 큰 카드('이번 정산 금액 7,845,965원 · 별도 입금 33,890원 포함 · 이 중 정산 예정 금액(쿠팡 미확정 금액) 4,463,970원 (바뀔 수 있음)') · 샘플 시트 4명(연다인·장대익·서달원·안재영) = 통제 세션이 바꿈(이 항목과 별도).
- 버린 대안: '이 중 정산 예정 금액(쿠팡 미확정 금액)'(D-251 — 소유자가 바꿈) · 2쪽 회색 줄도 함께 바꾸기(요청 밖 · 필요하면 소유자 확인).
- 영향 범위: T-38 그리기 모듈(`settlement_consignor_gsheet.py` · 구현 전) · CURRENT_RULES 12절 · STATE T-38 줄 · 샘플 스크립트·시트(통제 세션 반영) · 기존 위탁정산서 코드(`settlement_statement*.py`) 안 바꿈(D-233).
- 상태: SUPERSEDED by D-259

### D-259 [CONSIGNOR_STATEMENT_PENDING_LABEL3] 위탁자 정산서 1쪽 큰 카드 예정분 문구 = '쿠팡 미확정 금액 포함'(D-258 같은 날 다시 바꿈) (2026-11-16, R198)
- 결정(소유자 2026-11-16 원문 — 통제 세션 대화, D-258 반영 뒤 재지시): "다시 수정해줘,정산서 문구를 "쿠팡 미확정 금액 포함"으로 변경해줘." → 1쪽 큰 카드(이번 정산 금액) 큰 숫자 아래 줄 이름 = '쿠팡 미확정 금액 포함'(소유자 원문 글자·띄어쓰기 그대로 · 뒤 금액 '○○원 (바뀔 수 있음)'은 그대로) — D-258 의 '정산 금액중 쿠팡 미확정 금액' 대체.
- 바꾸지 않음(요청 = 1쪽 문구 하나): 2쪽 상품표 예정분 회색 줄 '└ 정산 예정(쿠팡 미확정)'(D-251) · 다른 화면·기존 위탁정산서의 '정산 예정' 낱말(D-153 표시 등) · 금액·계산 규칙(D-241·D-242).
- 근거: 소유자 원문(위) · 샘플 시트 13탭 = 통제 세션이 바꿈(새 문구 7곳 · 옛 문구 0 확인 · 이 항목과 별도).
- 버린 대안: '정산 금액중 쿠팡 미확정 금액'(D-258 — 같은 날 소유자가 바꿈 · 바꾼 이유 원문 없음) · '이 중 정산 예정 금액(쿠팡 미확정 금액)'(D-251) · 2쪽 회색 줄도 함께 바꾸기(요청 밖 · 필요하면 소유자 확인).
- 영향 범위: T-38 그리기 모듈(`settlement_consignor_gsheet.py` · 구현 전) · CURRENT_RULES 12절 · STATE T-38 줄 · 샘플 스크립트·시트(통제 세션 반영) · 기존 위탁정산서 코드(`settlement_statement*.py`) 안 바꿈(D-233).
- 상태: ACTIVE

### D-260 [CONSIGNOR_STATEMENT_PDF_DELIVERY] 위탁자 정산서 발송 = 위탁자별 PDF · 첫 장 월별 요약(여러 달) · 위탁자 모음 요약·'아직 반영 안 된 부분'은 구글시트에만 · 판매 기간·발행 줄 진하게 · '검토용' 표시 없음 (2026-11-16, R199)
- 결정(소유자 2026-11-16 원문 — 통제 세션 대화): ① 엑셀 변환 확인 결과(쪽수 3→8·오른쪽 잘림·'#########') 보고 뒤 "PDF로 위탁자별 파일 다시 내보내줘" → 위탁자에게 보내는 파일 = 구글시트 탭을 PDF 로 내보내 위탁자 1명 = 파일 1개(판매 달 순서로 이어 붙임) · 엑셀(.xlsx) 변환본은 보내지 않음. ② "검토용 샘플 표시 빼고 다시 만들어줘, "판매 기간 2026-08-01 ~ 2026-08-31 · 발행 2026-11-16" ==> 진하게 해줘, 아직 반영 안된부분은 삭제해줘. 그리고 안재영님은 8월부터 판매되어 월별로 출력되는데 첫장을 추가해서 요약을 해줘, 요약은 개일별 요약임, 위탁자별 요약은 현재 구글시크에만 있어야 함." → 머리 오른쪽 '판매 기간 … · 발행 …' 줄 = 굵게(진한 글자) · '검토용 샘플' 표시 없음 · '아직 반영 안 된 부분'은 PDF 에서 뺌 · 판매 달이 여러 개인 위탁자 = PDF 첫 장에 그 위탁자 한 명의 월별 요약(달마다 판매 금액·쿠팡이 뺀 돈·계정 공통·별도 입금·이번 정산 금액·쿠팡 미확정 금액·입금 완료·입금 예정 + 합계) · 여러 위탁자를 모은 '{n}월 요약' 탭 = 구글시트에만(PDF 에 넣지 않음).
- 근거: 엑셀 변환 실측(`D:\coupang-analytics\output\_정산서_261116_안재영\_엑셀변환확인\` — 구글시트 내려받기 xlsx 를 엑셀 COM 으로 열어 PDF: 10월 안재영 3쪽→8쪽 · 반영 전 내역 5쪽→14쪽 · 인쇄 설정(A4 너비 맞춤·여백 0·쪽 나눔)이 xlsx 로 안 넘어옴 · 이미지는 원래 0개) · 반영 결과 = 샘플 시트 `115iMzI3…` 탭 '월별 요약 안재영 (sg0141n)'(gid 2110) · PDF 4개 `D:\토탈셀러\쿠팡 정산 자료\위탁자정산서_PDF_261116\`('검토용' 0 · '아직 반영 안 된' 0 · 합계 손검산 24,254,905).
- 버린 대안: 엑셀 파일 발송(모양 깨짐 · 위탁자 PC 글꼴 따라 더 달라짐 추정) · 구글시트 링크 공유(위탁자 모음 요약은 시트에만 — 소유자 원문) · '아직 반영 안 된 부분'을 PDF 에 넣기(소유자가 뺌 · 시트 탭은 남김 — 지울지는 소유자 확인 전).
- 영향 범위: T-38 그리기·발행(`settlement_consignor_gsheet.py` · 구현 전 — PDF 내보내기·위탁자별 묶기·월별 요약 첫 장 포함) · 샘플 스크립트(git 밖 `output\_샘플_261115_위탁자정산서\_sheet\render_gsheet.py`·`output\_정산서_261116_안재영\_sheet\render_gsheet.py`·`render_summary_add.py`) · CURRENT_RULES 12절. 금액·계산 규칙은 안 바뀜.
- 상태: ACTIVE

### D-261 [CONSIGNOR_STATEMENT_PENDING_SPLIT] 정산서 오류 3건(E1~E3)·판매자서비스이용료 이중 계산 방지 = 모든 위탁 정산서 프로그램에 반영 (2026-11-16, R201)
- 결정(소유자 원문 2026-11-16 — 통제 세션 대화, 통제 세션이 이 세션에 전달 · 이 세션에서 소유자가 "정책 반영하고 새 세션으로 넘겨줘"): "정산서 오류 3건은 모든 위탁 정산서에 해당되는 건으로 다시 프로그램 수정해야 돼." → 안재영 정산서에서 나온 E1~E3 와 판매자서비스이용료 이중 계산은 그 계정만의 일이 아니다. 위탁 정산서를 만드는 프로그램(T-38 새 형식, 그리고 정산 예정분을 나누는 기존 위탁정산서 코드)에 같은 검사와 수정을 넣는다. 정산 코드만 고친다(D-233).
  - ① **E1 · 정산 예정분 상품 나누기 비율 0~100%**: 판매 방식별 관리 판매 ÷ 계정 판매가 0~100% 밖이면 정산서를 만들지 않고 중단한다. 2쪽 상품 줄(이름 묶은 뒤)의 정산 예정 판매는 0 이상이어야 한다.
  - ② **E2 · 주문 자료 실제값 우선**: 윙 정산 예정 달의 `주문별매출_YYYYMM.json` 이 있고, 상품별 정산 파일 기간 밖 구매확정 줄의 합(판매·정산)이 쿠팡 정산 줄과 원 단위로 같으면 추정 대신 그 실제값(옵션별 판매·쿠폰·수수료·정산)을 쓴다.
  - ③ **E3 · 로켓그로스 기타 공제**: 추가 공제(`totalAdditionalDeductionAmount`)에서 내역 칸을 뺀 나머지는 9 계정 공통에 넣는다. 내역 칸 = 밀크런·광고·리뷰 이벤트·쿠팡 라이브·체크카드·구독·비즈니스 인사이트·판매 조정·빠른정산·쿠팡 대출. 이월 공제는 추가 공제에 들어가지 않는다.
  - ④ **판매자서비스이용료**: 쿠팡이 그 달 판매 기간 윙 줄에서 이미 뺀 금액을 먼저 쓴다. 규칙값(D-161)은 모자란 만큼만 더한다.
- 근거(실측 · 재현 시험): `output\_정산서_261116_안재영\T60_수정_보고.md` 7절(조건·방식·재현) · 시험 `_scripts\t60_check.py`(고치기 전 실패 8건 → 고친 뒤 0)·`t60_bridge.py`(쿠팡 지급 → 이번 정산 금액, 네 달 차이 0).
  - E1: sg0141n 11월 관리 비율 −54.4%(관리 판매 −270,499). 기존 방식인 달 기준 M:2026-11 로 나눠도 같은 값이 나온다.
  - E2: sg0141n 10월 쿠폰 688,249 덜 빼고 수수료 657,373 더 뺌(정산 −24,819). 서달원·연다인 10월도 같은 조건이지만 정산 금액 차이는 0.
  - E3: 4계정 로켓그로스 지급 줄 296개 중 나머지가 있는 줄 = sg0141n 11-27 줄 8,880 하나.
  - ④: 샘플 코드로는 sg0141n 9·10월에 55,000 이 두 번 들어간다.
- 미승인(Claude 판단 · T-61 ⑤ 소유자 확인 전 · 이 결정에 포함 안 함):
  - E1 에서 주문 자료가 없을 때의 나누기 = 옵션별 미확정 잔량(판매분석 결제 주 − 이미 확정된 주문) — sg0141n 11월은 쿠팡 정산 줄과 원 단위로 같았다.
  - 그때의 쿠폰·수수료 = 옵션 최근 달 실제 비율.
  - 8,880 줄 이름 '로켓그로스 기타 공제 (쿠팡 공제 사유 미표시)'.
- 버린 대안: 안재영만 고치기(소유자 원문 "모든 위탁 정산서") · 0~100% 밖 비율을 0·100% 로 잘라서 계속 만들기(근거 없는 금액이 나옴 · 중단 = D-126 자동 검산과 같은 방식) · 이월 공제를 추가 공제 내역 칸에 넣기(bux1004 16줄에서 음수 나머지가 나옴).
- 영향 범위: T-38(`settlement_consignor_month.py` 등 · 구현 전) · 저장소의 기존 위탁정산서 정산 예정분 나누기 코드(`src/coupang_analytics/settlement_statement*.py` — 어디에 해당하는지는 통제 세션이 조사 중) · 샘플 스크립트 2벌(git 밖 · 안재영 사본은 R200 에 반영 끝) · CURRENT_RULES 12·13절 · 금액: 안재영 10월 +19,269 · 11월 +342,242.
- 상태: ACTIVE (부분 SUPERSEDED by D-262 — ① '0~100% 밖 = 정산서 안 만듦' → 그 금액만 '확인 필요'로 빼고 발행 · 주문 자료 없을 때 나누기 = 그 돈이 나온 기간의 상품별 판매(승인) · 부분 SUPERSEDED by D-286 — E3 8,880 = PostPurchase 칸 · 부분 SUPERSEDED by D-405 — ① '정산 예정 판매 0 이상'은 윙만)

### D-262 [CONSIGNOR_STATEMENT_PENDING_ORDER] 정산 예정분 관리 몫 나누기 순서 = ① 주문별매출 실제값 → ② 그 돈이 나온 기간의 상품별 판매 → ③ 그래도 안 되면 그 금액만 '확인 필요'로 빼고 발행 (2026-11-16, R202)
- 결정(소유자 원문 2026-11-16 — 통제 세션 대화): 통제 세션 제안 "1. 주문별 매출이 있으면 실제 값 2. 없으면(이번 달분처럼 아직 수집 전) 판매분석 일별에서 그 돈이 나온 주문 기간을 찾아 상품별 판매 비율로 나눔(같은 주 아님) 3. 그래도 0~100% 밖이거나 맞는 주문을 못 찾으면 ⓐ 그 계정 정산서 중단 / ⓑ 그 금액만 '확인 필요'로 빼고 정산서는 발행" → 소유자 "응, 그 순서대로 진행해. 3번은 ⓑ로 해".
  - ① 주문별매출(`정산\검증자료\월자료\{계정}\주문별매출_YYYYMM.json`)이 있으면 실제 값(어느 상품·관리 몫·쿠폰·수수료).
  - ② 없으면 판매분석 일별에서 그 정산 예정 금액이 나온 주문·판매 기간의 상품별 판매로 나눔(같은 달·같은 주 전체 비율 아님).
  - ③ 그래도 관리 비율이 0~100% 밖이거나 맞는 판매를 못 찾으면 그 금액만 금액에 넣지 않고 '확인 필요'로 표시하고 정산서는 발행(D-146 방식) · 쿠팡 자료가 오면 다음 정산서 한 줄(D-238).
- 근거: 지금 28계정 코드 `settlement_statement_account.py:308-319` `month_share` = 그 달 판매분석 전체 순액 비율·범위 검사 없음 · 주문별매출 읽기 없음(통제 세션 확인) · T-63 재현 시험 `output\_정산서_261116_안재영\_scripts\t63_repro.py` 실패 4건(sg0141n 11월 윙 관리 판매 −270,499 · 10월 4,481,505 대 실제 4,537,200) · 11-03 결과 bux1004 11월 로켓그로스 115.97% · 하위 실측 `output\_분석_261116_예정분나누기\실측_보고.md`(현행 0~100% 밖 3곳 → ② 방식 0곳 · 10월 실제값 대비 오차 최대 2.1%p).
- 미승인(Claude 판단 · 이 결정에 포함 안 함 · STATE T-64·T-65): ② 세부 규칙(윙 = 판매분석 일별 결제일 순액 [S ~ E−7일] − 이미 확정 주문 · 정산 파일 줄 한 번만 · 음수 잔량 0 / 로켓그로스 = 예정 줄 기간과 같은 날짜) · 검산 기준(잔량 합 / 쿠팡 예정 0.9~1.1) · 쿠폰·수수료 비율(T-61 ⑤) · 3단계 체계(확정·입금 / 확정·입금 전 / 미확정 예상)와 ③ 예상금액 표시 위치·이름(소유자 검토 중).
- 버린 대안: ⓐ 그 계정 정산서 중단(D-261 ① · 달 초 예정분은 자료가 늦어 자주 걸리고 문제없는 달까지 멈춤 · 소유자 ⓑ 선택) · 같은 주 판매분석 비율(T-60 주별 W 방식 — 다른 계정 10월 시험 오차 큼 91white +26.9%p · oopean −70.2%p) · 0·100% 로 잘라 계속(근거 없는 금액).
- 영향 범위: `src/coupang_analytics/settlement_statement_account.py`(`month_share`·`_unsettled_share`·`ratio`) · `settlement_statement_source.py`(주문별매출 읽기·`_wing_unsettled` 판매/정산 기간 어긋남 · 256행 음수 예정 버림) · `settlement_statement_deduct.py`(`ratio` 쓰는 공제 나누기 · 85~91 `svc_month`) · `settlement_statement_book.py`(확인 필요 표시) · T-38 계획 S1 시험 · CURRENT_RULES 12·13절 · 구현 = T-63(정산 코드만 D-233).
- 상태: ACTIVE (부분 SUPERSEDED by D-269 — ③ '확인 필요'로 빼기 전에 윙은 저장 지연 분포 → 그 달 판매 비율로 채움 · 셋 다 안 되는 금액만 '확인 필요')

### D-263 [LEDGER_PRODUCT_ACCOUNT_RECORD] 장부 = 쿠팡이 주는 단위 그대로 기록 — 상품 단위 값 = 상품 내역 · 계정 단위 값 = 계정 내역 · 기간으로 한정한 둘의 합 = 정산금액 (2026-11-16, R204)
- 결정(소유자 원문 2026-11-16 — 통제 세션 대화): "1개의 상품이 판매되면 그 상품에 대한 모든 내역이 기록되어 알수 있어야 함, 그래야 정산에 반영됨, 그리고 상품별 저장이 아니고 계정별 값으로 쿠팡이 주는것은 계정별로 내역을 기록하여 정산에 반영 되도록 해야 함. 그러면 상품과 계정별 금액을 기간으로 한정하면 정산금액이 됨." → 샘플 검증 결과 보고 뒤 소유자 "지금 D-263으로 기록해줘".
  - 상품 내역 = 쿠팡이 옵션(상품) 단위로 주는 값. 상품 1개가 팔리면 판매 → 구매확정/매출인식 → 정산 줄(지급 단계별) → 그 상품의 비용·광고·보상 → 지급까지 모든 내역이 기록되어 알 수 있어야 함.
  - 계정 내역 = 쿠팡이 상품별이 아니라 계정 단위로 주는 값. 상품으로 나눠 저장하지 않고 계정 내역으로 기록해 정산에 반영.
  - 정산금액 = 기간으로 한정한 상품 내역 금액 + 계정 내역 금액.
- 근거: 샘플 검증 `D:\coupang-analytics\output\_분석_261116_예정분나누기\장부_KEY_샘플검증.md` 9절(3계정 × 2026-10 · 회차 4개) — 상품 내역 합 + 계정 내역 합 = 쿠팡 회차 지급액: roum0502 차 0 · swmall255 두 회차 ±3,713원 = 비용 이월(⑮ `totalPastCfsDeductionAmount` −3,713 / 다음 회차 `totalLastSettlementUnpaidCfsDeductionAmount` +3,713)을 계정 내역으로 넣으면 차 0 · guarisen2024 차 2원(70% 곱 반올림) · 상품 5개 전체 추적 끊김 0(8절). KEY 분석 `…\장부_KEY_그룹_분석.md`.
- 미승인(Claude 판단 · 이 결정에 포함 안 함 · STATE T-64): KEY 체계와 보완 6가지(샘플검증 5절 — 거래유형 만들어 넣기 · 윙 보류 해제 회차 KEY+pendingAmount · 노출상품ID = 속성 · 반품 배송비 옵션 = ⑱ returns 등) · 계정별 1파일+요약 · SQLite/xlsx · 섞인 계정 정산 예정분을 상품으로 나눈 값의 저장 방식 · 반출 배송 서비스비·밀크런·광고정산을 계정 내역으로 볼지의 항목별 확정(샘플에서 옵션 칸 없음 사실 · 고리 KEY 값 대조 6/6·4/4·35/35).
- 버린 대안: 옵션 칸이 없는 비용을 고리 KEY(반출ID·밀크런번호·날짜+캠페인ID)로 찾아 상품에 나눠 붙여 저장(KEY 분석 2-3절 권장이었음 — 소유자 원칙과 다름 · 고리는 칸으로만 둠) · 비용을 '정산주기 끝' 날짜만으로 회차에 맞추기(이월 줄이 빠져 ±3,713원 큰 차이 · D-235).
- 영향 범위: 미정산 장부 설계(T-64·T-66) · 위탁 정산서 계산(T-63·T-38) — 정산서에서 계정 내역의 관리 몫은 기존 D-236·D-241(계정 공통 비용) · 정산 예정분 나누기는 D-153·D-262 그대로(이 결정은 바꾸지 않음) · CURRENT_RULES 13절.
- 상태: ACTIVE

### D-264 [CONSIGNOR_STATEMENT_PENDING_ESTIMATE] 섞인 계정의 정산 예정분 = 상품별로 나눈 예상값을 정산서에 넣고 다음 달 정정(ⓑ) (2026-11-16, R205)
- 결정(소유자 원문 2026-11-16 — 통제 세션 대화): 통제 세션 제안 "ⓑ 지금 규칙(D-153·D-262): 예상값을 정산서에 넣고, 다음 달에 차이를 정정 / ⓒ 섞인 계정의 정산 예정분은 금액에서 빼고 '다음 정산서 반영'으로 표시(Claude 권장)" → 소유자 "ⓑ 예상값을 넣고 다음 달 정정".
  - 관리·비관리 상품이 섞인 계정에서 쿠팡이 계정 합계로만 준 정산 예정분 → D-262 ② 로 상품별로 나눈 예상값을 정산서 금액에 넣음 · 쿠팡 주문 단위 자료가 오면 다음 정산서에 차이 한 줄(D-238). 차이는 넘기지 않고 정정하므로 D-235(100원 이상 = 바꾸는 차이)와 맞음.
  - 한쪽 상품만 파는 계정(관리 100%·0%)은 나눌 일 없음 · D-262 ③(0~100% 밖·나눌 판매 없음 → 그 금액만 '확인 필요')은 그대로.
- 근거: `D:\coupang-analytics\output\_분석_261116_예정분나누기\미정산장부_방안.md` 3·5절 — 윙(E−8 + 정산대상 환산) 정산서 작업일 23번 오차 합 204,487원(현행 3,851,923) · 최대 113,319 · 로켓그로스 작업일 210줄 5,989,058(현행 9,859,035) · 끝난 주 최대 343,931 · 11-03 정산서 정답 7줄 오차 절댓값 2,340,897 → 406,883(fe3276 은 121,535 → 246,084 로 커짐) · 100원 이상 비율 윙 43% · 로켓그로스 53~55%(쿠팡 합계만으로는 원 단위 불가 — 상품마다 수수료·쿠폰 비율 다름) · 확정·지급 회차는 오차 0(D-263 근거).
- 미승인(이 결정에 포함 안 함 · STATE T-64): ② 세부 규칙(윙 결제 끝 E−8 · 정산대상 환산 · 시작 달 1일−30일) · 표시 문구·위치 · 검산 기준 · 실측 2건(윙 주문별매출 달 중간 조회 · 로켓그로스 예정 판매수수료 요청).
- 버린 대안: ⓒ 섞인 계정 정산 예정분을 금액에서 빼고 다음 정산서 반영(정산서 금액 오차 0 대신 그 돈이 한 회 늦게 들어감 · Claude 권장이었음 — 소유자 ⓑ 선택).
- 영향 범위: 위탁 정산서 계산 `src/coupang_analytics/settlement_statement_account.py`·`settlement_statement_source.py` 등(T-63 · 정산 코드만 D-233) · 장부 ⑤ 예상 대 실제 표(T-66) · CURRENT_RULES 12절.
- 상태: ACTIVE

### D-265 [LEDGER_AI_JUDGE_BY_TYPE] 장부 이관·검증의 AI 판정 = 같은 유형은 AI가 한 번 판정해 규칙(판정표)으로 → 파이썬이 같은 유형 줄 전부에 적용 → 규칙 밖 줄만 AI · 규칙마다 표본 재확인 (2026-11-16, R206)
- 결정(소유자 원문 2026-11-16 — 통제 세션 대화): "AI토큰을 많을 사용할것 같은데 동일유형의 자료이면 AI가 판정해서 정규화한 다음 파이썬으로 구현하면 어때?이러면 토큰을 절약 할수 있지? 알아봐줘." → 통제 세션 제안(아래 4가지 지킬 것 포함) → 소유자 "응, 그 방식으로 전달해줘".
  - 같은 유형의 자료는 AI(Claude)가 유형별로 판정해 규칙을 만들고, 파이썬이 그 규칙을 같은 유형 줄 전부에 적용한다. 어느 규칙에도 안 맞는 줄만 AI가 따로 판정한다.
  - ① 규칙은 자료 조건(칸 값·금액 관계)으로만 · 특정 계정·상품·금액 금지(D-229) · 규칙은 코드가 아니라 판정표 파일에 근거·원문과 함께 ② 규칙 적용 줄에 '규칙 R-xx 적용' 표시 · 규칙마다 표본(20줄, 20줄 미만이면 전부)을 AI가 다시 확인해 기록 ③ 규칙 밖·근거 애매 줄은 AI 판정 또는 '확인 필요'(버리지 않음) ④ 정산금액을 바꾸는 '진짜 빠짐·오류' 줄은 건마다 AI 판정.
  - 숫자로 증명되는 원인(예: 차이 = 이월 줄 금액 · 반올림 ≤ 2원 · 보류 해제 = pendingAmount)은 파이썬이 '정확히 맞는지'만 판정한다.
- 근거: 원천 약 150만 줄(보관비 66만 · 정산 파일 25만 · 배송·입출고 40만 · 판매분석 16만 — `장부_KEY_그룹_분석.md` 4-1절) → 줄마다 AI 판정 불가 · 3계정×10월 샘플에서 짝 없는 줄·차이 원인이 몇 가지 유형으로 모임(`장부_KEY_샘플검증.md` 4절) · 전역 규칙 '매칭 = AI 판정 · 프로그램은 후보 추출과 판정 결과 옮기기'(~/.claude/CLAUDE.md 2026-10-27)를 지키려고 표본 재확인을 둠.
- 버린 대안: 줄(건)마다 AI 판정(토큰 과다 · 큰 차이 1,000건이면 수십만~백만 토큰대 [추정]) · 규칙만 적용하고 AI 재확인 없음(프로그램 결과를 그대로 확정 = 전역 규칙 위반).
- 영향 범위: T-71 장부 DB 시험 계획 `D:\coupang-analytics\output\_시험_261116_장부DB\계획.md` 3절 J2·J3·J6·J7(J1 관리 상품 = 기존 판정표 재사용 · J4·J5 그대로) · 규칙 파일 `…\_시험_261116_장부DB\판정\규칙_*.json` · 이후 장부 운영 구현 · CURRENT_RULES 13절.
- 상태: ACTIVE

### D-266 [CONSIGNOR_STATEMENT_PENDING_SPLIT_RULE] 섞인 계정 정산 예정분 나누기 세부 규칙 = 윙 B8+환산 · 로켓그로스 B+환산 · 검산 1.5 이상만 '확인 필요' · 정산서 달 = 쿠팡 정산 기준 날짜의 달 · 예상 대 실제 표 도입 (2026-11-16, R209)
- 결정(소유자 2026-11-16 — 통제 세션 질문 4개에 답, 원문 = 선택한 답): "윙 B8+환산·RG B+환산 (권장)" · "검산 1.5 이상만 (권장)" · "기준 날짜 달·코드도 맞춤 (권장)" · "도입·늦음 기준 제안대로 (권장)". D-262 ②의 세부 규칙(그동안 '미승인')을 정한다.
  - ① 윙 = 판매분석 일별 순액에서 결제일 [그 달 1일−30일, 기준일−8일] 판매 − 이미 확정된 주문(정산 파일 줄 한 번만 · 옵션별 합 뒤 음수 0) → 옵션별 정산대상/판매 비율로 환산해 쿠팡 합계 정산대상을 나눔. 로켓그로스 = 예정 판매 주마다 같은 매출인식일 날짜의 상품별 판매(순액)로 나누고 같은 환산.
  - ② '확인 필요'(금액만 빼고 정산서는 발행 · D-262 ③) = 관리 비율 0~100% 밖 · 나눌 판매 없음 · 검산(남은 판매 ÷ 쿠팡이 준 판매) 1.5 이상.
  - ③ 정산서 달 = 쿠팡 정산 기준 날짜(윙 구매확정일 · 로켓그로스 매출인식일)의 달 · 지급일은 입금 표시만(D-154). 로켓그로스 예정 주를 '주 시작 달'로 가르는 코드(`settlement_statement_source.py:352`)도 기준 날짜로 가름(T-63 에서 고침).
  - ④ 예상 대 실제 표: 정산서에 넣은 상품별 예상값을 고쳐 쓰지 않고 저장(같은 회차를 다른 기준일에 다시 예상하면 새 묶음) → 쿠팡 주문 단위 자료(윙 주문별매출 · 로켓그로스 판매수수료 파일)가 오면 같은 줄에 실제값 → 관리 몫 차이를 다음 정산서 차이 한 줄(D-238 · D-264). 계정 합계는 계정 내역에, 상품별 예상은 이 표에만(D-263). 실제값이 윙 기준 달 끝+20일 · 로켓그로스 판매 주 정산일+3일까지 없으면 '확인 필요'. KEY·칸 = `미정산장부_방안.md` 9절.
- 근거: `D:\coupang-analytics\output\_분석_261116_예정분나누기\미정산장부_방안.md` 7~9절 · `_scripts\t66_sum.txt`(통제 세션이 8-1 표와 원 단위 대조) — 섞인 계정 8~10월 오차 합 윙 B8+환산 8,873,103(A 50,431,370 · A' = 현행 130,033,899 · 한 줄 최대 287,503) · 로켓그로스 B+환산 81,903,210(A 258,845,755 · 최대 414,902) · 0~100% 밖 윙 0 · 검산 0.9~1.1 은 작업일 5,321,298 을 빼고도 최대 오차 줄을 못 거름 · 정산 파일 1,261개 모두 한 달 안 → ③ 지금 영향 0원 · 결정표 `…\T64_결정표.md`.
- 버린 대안: A(가장 이른 미정산 결제일부터 · 끝 안 자름) · A'(마지막 확정 다음 날부터 = 현행) · 판매만(환불 뺌) · 검산 0.9~1.1 · 검산 안 씀 · 규칙 문장만 바꾸고 코드 그대로 · 표 보류.
- 영향 범위: T-63(정산 코드 `settlement_statement_account.py` month_share·_unsettled_share · `settlement_statement_source.py` _wing_unsettled·:352 · 정산 코드만 D-233) · T-71 정산서 생성의 'Claude 판단값' 표시 → 이 결정값 · CURRENT_RULES 12절. 남은 T-64 항목(장부 저장·실측 2건·11-03 차이 줄·T-69 확인 필요)은 미결정.
- 상태: ACTIVE (부분 SUPERSEDED by D-267 — ① 윙 결제 끝 날짜 문구 '기준일−8일' → '기준일−9일' · 부분 SUPERSEDED by D-269 — 윙 '확인 필요'는 저장 지연 분포 → 그 달 판매 비율로 채움 · 로켓그로스 B+환산 → 그 달 판매 비율)

### D-267 [CONSIGNOR_STATEMENT_PENDING_SPLIT_RULE] D-266 ① 문구 정정 — 윙 B8 결제 끝 = 기준일−9일(= 기준일 전날 E 에서 8일 뺀 날 · E−8) (2026-11-16, R210)
- 결정(소유자 2026-11-16 — 통제 세션 질문에 답, 원문 = 선택한 답): "기준일−9일로 정정 (권장)". D-266 ①의 윙 결제일 구간을 [그 달 1일−30일, **기준일−9일**]로 고친다(나머지 D-266 내용 그대로).
- 근거: T-63 세션(local_f6080011) 지적 → 통제 세션이 시뮬레이션 코드 확인 — `D:\coupang-analytics\output\_분석_261116_예정분나누기\_scripts\t66_wing.py:31` `E=D-timedelta(days=1)` · `:85` `'B8':(S0,E-timedelta(days=8),True)` · `미정산장부_방안.md:47` 'L7/L8/L9 = 결제 끝 D−1−7/8/9일' → 소유자가 고른 근거 수치(오차 합 8,873,103)는 기준일−9일 정의. D-266 본문의 '기준일−8일'은 통제 세션이 옮겨 적을 때 생긴 오기(그 정의 = B7 · 순액 오차 합 22,561,264).
- 버린 대안: 기준일−8일 그대로(근거 수치와 다름).
- 영향 범위: T-63 구현(`settlement_statement_pending.py` 새 모듈 예정) · CURRENT_RULES 12절 · T-71 정산서 생성(D-266 표시).
- 상태: ACTIVE

### D-268 [CONSIGNOR_STATEMENT_PURPOSE] 위탁정산서 목적 = 쿠팡이 정산하기 전에 예상 정산 금액을 위탁자에게 알려 계약 진행 상황을 확인 — 나누기 규칙은 '정산 끝난 달 실제'와의 예상 오차가 가장 작은 쪽으로 정함 (2026-11-17, R213)
- 결정(소유자 2026-11-17 원문): ① "쿠팡이 정산이 끝난 달의 데이타로 검증해서 결정해줘." ② (통제 세션이 '판매 다음다음 달 16일 이후에 만들면 정확'이라고 답한 데 대해) "쿠팡이 정산한 내역을 가져오려고 했으면, 너와 내가 별도 db를 구축할 필요가 없어. 우리는 쿠팡이 정산하기전에 정산 금액이 얼마인지 위탁자에게 알려줘서 계약 진행 상황을 체크하기 위함이 목적임."
- 적용: 위탁정산서·정산 장부(T-71)는 쿠팡 지급 전 '예상 금액'을 내는 것이 목적이다. 정산 예정분 관리 몫 나누기(D-262·D-266·D-267)·상품 없는 배송비(R-C3) 등 남은 규칙 결정은 쿠팡 정산이 끝난 달(현재 2026-09까지)을 정답으로 한 백테스트에서 계정×달 예상 오차(100원 이상 칸 수·오차 합·최대)가 가장 작은 안으로 정한다. '확인 필요'로 관리 몫에서 빼는 안도 빠진 실제 관리 몫 전체를 오차로 센다. 100원 이상 차이(D-235)는 예상 대 실제 표(D-266)와 다음 정산서 차이 줄(D-238)로 위탁자에게 보인다.
- 근거: 통제 세션 답(정산 회차 자료 `D:\coupang-analytics\output\_검증_261117_정산끝난달\scripts\s02_month_done.txt` — 윙 마지막 30% = 판매 다음다음 달 첫 영업일 · 로켓그로스 = 다음다음 달 15일 이내)에 대한 소유자 정정. 검증 세션(local_8419e09d) 브리프의 판정 규칙 '대안이 모든 계정·달 100원 미만이 아니면 확인 필요 유지'는 이 목적과 맞지 않아 같은 날 폐기·재판정 지시.
- 버린 대안: 쿠팡 정산이 끝난 뒤(판매 다음다음 달 16일 이후)에만 정산서 발행(목적과 다름 — 쿠팡 지급 내역 조회로 충분) · '모든 칸 100원 미만이 아니면 확인 필요'(빠진 몫이 위탁자에게 안 보여 예상 목적에 어긋남).
- 영향 범위: ⚠1 주문별매출 없는 날 윙 예정분 · ⚠2 기준일 뒤 로켓그로스 예정 주 · R-C3 배송비 · T-64 5~8 판정 기준(검증 = `D:\coupang-analytics\output\_검증_261117_정산끝난달\판정_보고.md`) · 판정 결과에 따라 D-262 ③·D-266 의 '확인 필요' 범위가 새 D항목으로 바뀔 수 있음 · D-146·D-148(정산예정 금액은 불가피하면 추정 허용) 과 함께 읽음 · 코드 변경 없음.
- 상태: ACTIVE

### D-269 [CONSIGNOR_STATEMENT_PENDING_SPLIT_RULE] 정산 끝난 달 백테스트 판정 반영 — 윙 '확인 필요'는 빼지 않고 채움(저장 지연 분포 → 그 달 판매 비율) · 로켓그로스 예정분 = 그 달 판매 비율(B+환산 되돌림) · 반품 조회 자료를 배송비 귀속에 사용 (2026-11-17, R214)
- 결정(소유자 2026-11-17 원문 — 통제 세션이 남은 결정 순서를 보고한 데 대해): "결정해 주시면 바로 진행되는 순서 ==> 쿠팡이 정산이 끝난 달의 데이타로 검증해서 결정해줘." · 판정 기준 = D-268(쿠팡 지급 전 예상 · 오차 합 최소 · '확인 필요'로 뺀 몫도 오차). 통제 세션이 검증 결과로 아래와 같이 정한다.
  - ① 윙 정산 예정분 관리 몫: 주문별매출 실제값 → D-266·D-267 B8+환산 → 그래도 D-262 ③·D-266 의 '확인 필요' 조건(검산 1.5 이상·나눌 판매 없음·주문별매출 0 등)이면 빼지 않고 **저장해 둔 결제→구매확정 지연 분포 + 정산 파일 환산(ⓒ2)** → 그것도 없으면 **그 달 판매 비율**(가장 이른 미정산 결제일부터)로 넣는다. 셋 다 안 되는 금액만 '확인 필요'.
  - ② 로켓그로스 정산 예정분 관리 몫: **그 달 판매 비율**(T-63 이전 방식)로 넣는다. 기준일 뒤 예정 주도 같은 방식으로 넣는다(D-266 의 'B+환산'과 '나눌 판매 없음 = 확인 필요'를 대체).
  - ③ 상품 줄 없는 윙 배송비(R-C3): ① 같은 주문 → ② **반품 조회 자료**(장부에 넣음)로 귀속. 둘 다 없는 줄의 처리는 D-270 수수료·공제 산출 방식 조사 뒤 정한다(지금 해당 = gbseller808 40줄 · 관리 상품 0 → 정산서 영향 0).
  - 표시·정정: 넣은 예상값은 D-153 표시('정산 예정 — 쿠팡 상품별 자료 전, 판매 비율로 배분 · 정산 파일이 나오면 바뀜') · '예상 대 실제 표'(D-266) · 실제값이 오면 다음 정산서 차이 한 줄(D-238·D-264).
- 근거(정산 끝난 달 = 2026-09 · 기준일 2026-08-02~11-02 백테스트 · `D:\coupang-analytics\output\_검증_261117_정산끝난달\판정_보고.md` · 통제 세션이 `scripts\b4_rescore.txt`·`b5_fill.txt`·`b1_sum.txt` 와 숫자 대조): 윙 계정×달×기준일 3,036칸 오차 합 — D-266 그대로 72,336,179(그중 '확인 필요'로 뺀 실제 관리 몫 54,010,698) → ① 채움 24,035,881(작업일 3·15일 200칸 3,981,043 → 1,159,043 · `b5_fill.txt:6,10,19`) · 주문별매출이 하나도 없는 날 '확인 필요' 739,902,945 대 ⓒ2 197,328,492(`b4_rescore.txt`). 로켓그로스 작업일·다음 날 조회 80칸 — B+환산 5,103,054 대 그 달 판매 비율 1,003,743 · 당일 조회 76칸 604,637(`b5_fill.txt:41,42,66`). 배송비 ③ 대체안 — 계정 관리 비율 174,442 · 확인 필요 208,872 · 같은 달 윙 관리 비율 61,554 · 반품 조회 줄 169 오차 0(`b1_sum.txt:32`).
- 버린 대안: D-266 그대로(확인 필요로 빼기 — 오차 합 3배) · 로켓그로스 B+환산(작업일 오차 5배) · 기준일 뒤 RG 주 '확인 필요'(빠진 몫 29,075,924) · 배송비 ③ 계정 관리 비율(D-162 · 오차 3배 · 공제 비율 배분은 D-153 '공제는 예정분이라도 예외 아님'과 충돌하므로 D-270 뒤 결정).
- 남는 위험(사실): 전체 기준일로 보면 RG 섞음안(새 코드+기준일 뒤 주만 그 달 비율)이 조금 더 작음(다음 날 24,160,503 · 당일 17,747,326) — 정산서를 만드는 작업일(3·15일) 기준으로 판정. 3일 정산서는 지난달 주문별매출이 아직 없어(받는 날 = 말일+15) 오차가 남음 → 달 초에 받아 16일 파일과 같은지 실측(T-74 · 소유자 로그인).
- 영향 범위: T-63 브랜치 `claude/t63-pending-rules-751c0f` 3b421fd(`settlement_statement_pending.py` — D-266 구현)를 D-269 로 고친 뒤 병합(T-73) · 결제→구매확정 지연 분포 저장 기능 새로 필요 · T-71 장부 정산서(반품 조회 자료 반영) · CURRENT_RULES 12절.
- 상태: ACTIVE (부분 SUPERSEDED by D-282 — ① 마지막 단계 "그 달 판매 비율(가장 이른 미정산 결제일부터)" · 부분 SUPERSEDED by D-284 — ① B8·ⓒ2 기준일 뒤 자료 자르지 않음)

### D-270 [SETTLE_FEE_PER_ITEM_FORMULA] 반품·취소·환불은 발생하면 반영 · 그 밖의 수수료·공제는 상품 1건당 정액·비율 산출 방식으로 계산 — 쿠팡 가이드·웹·유튜브로 산출 방식 조사 (2026-11-17, R214)
- 결정(소유자 2026-11-17 원문): "상품 반품, 취소, 환불에 따른 판매금액은 발생하면 반영하면 됨, 그외의 각종 수수료,공제건은 상품 1건당 금액이 정액 또는 비율이 있을거야. 그래야 쿠팡에서도 정산에 반영하지. 너는 웹 또는 유뷰브, 쿠팡 가이드를 참고해서 산출 방식으로 알아 내야 해. 별도 세션으로 작업 해줘."
- 적용: ① 판매금액의 반품·취소·환불 = 쿠팡 자료에 생긴 때 반영(미리 예상하지 않음). ② 판매수수료·배송비·로켓그로스 물류비·보관비 등 수수료·공제 = 항목마다 상품(옵션) 1건당 정액·비율·구간표를 찾아 상품별로 계산한다. 찾은 공식은 정산 끝난 달 실제 공제와 대조해(D-268 · 100원 이상 D-235) 맞는 항목만 정산서에 쓴다. 공식으로 못 맞추는 항목은 지금 규칙(D-236 계정 공통 비용 등) 유지.
- 근거: 소유자 지시. 조사 세션 `local_7329032d`(산출물 `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\산출방식_보고.md`) 진행 중 — 결과로 항목별 적용 범위를 새 D항목에 정한다.
- 버린 대안: 계정 합계 공제를 판매 비율로 나눔(D-162·D-237 방식 — 상품별 실제 공제와 오차).
- 영향 범위: 위탁정산서 공제 계산(D-236·D-237·D-241 과 함께 읽음) · T-71 장부 · D-269 ③ 배송비 남은 줄 · 코드 변경 없음(조사 결과 뒤).
- 상태: ACTIVE (부분 SUPERSEDED by D-278 — ① 반품·취소·환불도 반영할 때 정규화 산식 사용)

### D-271 [SETTLE_COMMON_ALLOC] 계정 단위 정액(판매자서비스이용료·세이버 구독료·비즈니스 인사이트)의 관리 상품 몫 = 그 달 등록 상품 비율(등록상품 ID 개수 · 판매중지 포함) — 판매 비중과 비교하지 않음 (2026-11-17, R215)
- 결정(소유자 2026-11-17 원문): ① 조사 세션(local_7329032d) 질문 "계정 단위 정액을 상품별로 어떻게 나눌지 정해 주셔야 합니다." 에 "등록 상품 비율로 하자." ② 같은 세션 선택 답 — 세는 단위 = "등록상품 ID 개수 (추천)" · 세는 범위 = "등록된 상품 전부". ③ 통제 세션이 D-237·D-241(작은 쪽 · 정산 기준일 등록 상품 수)과 다르다고 묻자 "11-17 답으로 바꿈". (원문 위치: 세션 기록 `C:\Users\user\.claude\projects\D--coupang-analytics\85950f53-3e9d-40cd-8c95-7d70c3d1a7db.jsonl` 2026-11-17T00:29:43Z·00:31:12Z)
- 적용: 계정 단위 정액 3종의 위탁자 몫 = 정액 × (그 달 계정 등록상품 ID 중 관리 상품 수 ÷ 그 달 계정 등록상품 ID 전체 수). 등록상품 ID 단위로 센다(옵션 ID 아님). 그 달에 등록돼 있던 상품 전부(판매중지 포함). 판매 비중과 비교해 작은 쪽을 고르지 않는다. 그 밖의 계정 공통 비용은 D-237·D-241 그대로.
- 근거: 조사 보고 `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\산출방식_보고.md` 1-1절 — 이 3종은 상품 1건당 산출 방식이 없는 계정 정액(D-270 의 '공식 불가·계정 단위').
- 버린 대안: D-237·D-241 '판매 비중과 등록 비중 중 작은 쪽 · 등록 비중 = 정산 기준일 등록 상품 수'(이 3종에 한해 대체) · 옵션 ID 개수 · 판매 중인 상품만.
- 미확인: '그 달 등록 상품 전부' 목록을 받을 자료(상품 조회 원문·장부 등) — 구현(T-38·T-71) 때 정함.
- 영향 범위: 위탁자 정산서 계정 공통 비용(T-38) · T-71 장부 정산서 · 정산 코드만(D-233) · 코드 변경 없음.
- 상태: ACTIVE

### D-272 [SETTLE_FEE_PER_ITEM_FORMULA] D-270 조사 결과 적용 범위 — 판매수수료 3종·보관비·바코드·반출비 = 상품 1건당 공식으로 계산 · 로켓그로스 입출고비·배송비 = 지금 규칙 유지(무료 대상·할인표 받기 전) (2026-11-17, R216)
- 결정(D-270 규칙 적용 — 소유자 2026-11-17 원문 "…수수료,공제건은 상품 1건당 금액이 정액 또는 비율이 있을거야… 산출 방식으로 알아 내야 해." · D-270 적용 = '정산 끝난 달 실제와 대조해 맞는 항목만 정산서에 쓴다'): 조사 세션(local_7329032d·local_86553794) 대조 결과로 통제 세션이 아래처럼 정한다.
  - 공식으로 계산(끝전 = 모두 사사오입 · VAT 따로 사사오입):
    - 윙 판매수수료 = 수량 × 사사오입(1개당 판매액 × 카테고리 비율) − 사사오입(쿠폰 × 비율) + VAT · 로켓그로스 판매수수료 = 수량 × 사사오입((단품가 − 쿠폰 ÷ 수량) × 비율) + VAT('할인적용 판매수수료율' 칸은 전부 0 → 기본율) · 윙 배송비 수수료 = 사사오입(배송료 × 3%) + VAT.
    - 보관비 = 수량 × 사사오입(개당 CBM × 일 단가: 1~30일 1,000 · 31~60일 2,000 · 61~120일 2,500 · 121~180일 3,500 · 181일~ 5,000원) · 무료 30일 · 세이버 가입 달 60일 · 31~45일 의류·신발·악세서리·스포츠용품 무료.
    - 바코드 = 입고완료 수량 × 사이즈별 정액(부착 125/175/250 · 오류 수정 400/500/700) · 반출비 = 300원 × 수량(월 20개 무료 · 쿠팡 귀책 반품 제외).
  - 비율 출처 = 옵션의 앞 달 원문 비율(전 줄 같음) → 없으면 카테고리 비율. 카테고리를 모르는 새 옵션은 '확인 필요'로 표시하고 계정 최빈 비율로 넣는다(D-268 — 빼면 오차가 더 큼).
  - 로켓그로스 입출고비·배송비: 정가 공식은 맞지만 할인(B)·무료 프로모션 규칙을 몰라 계정×달 오차 7~9%(무료 창 '+44일' 추정은 오차를 못 줄여 기각) → 무료 대상 목록·할인표를 받을 때까지 지금 규칙(정산 파일 실제값 · 예정분은 D-269) 유지.
  - 공식 없음: 광고비(옵션별 광고 보고서 실제값) · 재고 손실 보상(사건) · 계정 정액 3종(D-271).
- 근거(통제 세션이 파일 대조 · `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\`): `대조_판매수수료_요약.md` — 원문 비율 쓸 때 오차 RG −32·−5·−1 · 윙 배송비 0 · 미리 계산(M3, 2025-12~) RG 188칸 100원 이상 24칸·절대오차 0.116% · 윙 215칸 56칸·2.452%(오차 = 카테고리 모르는 새 옵션 줄) · `대조_보관비_요약.md` — 144칸 최종 S1 100원 이상 19칸·오차 합 306,538·절대오차 0.831%(줄 770,486 중 761,942 일치) · `대조_물류비_M3_요약.md` — 입출고비 M2 7.92% → M3c 7.50% · 배송비 M2 8.78% → M3b 7.48% · 바코드 36칸 100원 이상 0(`산출방식_보고.md:38`).
- 버린 대안: 판매수수료·보관비를 계정 합계에서 판매 비율로 나눔(D-162·D-237 방식) · 무료 창 '첫 진열 +44일'(창 안 줄 44~46% 유료).
- 남은 일(받을 자료 · 소유자 로그인): 로켓그로스 무료 프로모션 대상·기간 · 할인(B) 표 · 밀크런 요금표 · 재입고비 정가. 확인 필요: 윙 새 옵션 카테고리 출처 · 세이버 가입 출처 · 보관비 원문 A=0 줄 9,408개 이유 · 보관비 입력을 재고현황 날짜별로 바꾼 미리 계산 대조.
- 영향 범위: 위탁자 정산서 공제 계산(T-38) · T-71 장부 · 정산 코드만(D-233) · 코드 변경 없음.
- 상태: ACTIVE (부분 SUPERSEDED by D-274 — 근거의 배송비 M2 8.78% → 8.83%(추출 칸 밀림 정정) · 할인 B 는 카테고리 할인표로 계산됨 · 부분 SUPERSEDED by D-286 — 31~45일 무료 = 1차 의류·신발·악세서리 + 세이버 가입 달(스포츠용품 뺌))

### D-273 [SETTLE_FEE_VERIFY_ON_COUPANG] 수수료·공제 계산 방식이 확실하지 않으면 쿠팡 윙에 직접 접속해 화면으로 확인 — 로그인은 소유자 · Claude 는 화면 읽기만 (2026-11-17, R218)
- 결정(소유자 2026-11-17 원문): ① 수수료 조사 세션에서 "실제 쿠팡에 접속해서 확인하자. 너가 직접 접속해." ② 통제 세션에서 "계산 방식이 확실하지 않는 것은 쿠팡에 직접 접속해서 확인하는 것으로 하자."
- 적용: D-270·D-272 의 수수료·공제 산출 방식 중 공개 자료·정산 원문으로 확정되지 않는 것(로켓그로스 할인표·무료 프로모션·밀크런·재입고비 등)은 쿠팡 윙 화면(실제 Chrome · 소유자가 로그인한 세션)에서 확인해 기록한다. 비밀번호 입력·2차 인증은 소유자(CLAUDE.md 로그인 규칙 그대로) · Claude 는 화면 읽기·보기 전환만 하고 해지·설정·저장 버튼을 누르지 않는다 · **페이지 안 API·스크립트 직접 호출 금지**(11-17 1회 호출이 봇 차단에 걸림 — 위탁계정 위험) · 프록시 미적용 · 순위 브라우저와 동시 개방 금지 · 한 번에 한 세션만 윙 화면을 쓴다.
- 근거: 11-17 sg0141n 화면 확인으로 로켓그로스 할인 B = 2차 카테고리 × 판매가 구간 × 사이즈 표임을 확정(가전>계절가전 표 = 정산 원문 일치 · `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\윙확인_261117_할인표_가전계절가전.md`).
- 버린 대안: 공개 웹·유튜브만으로 추정(할인표·무료 프로모션은 공개 자료에 없음).
- 영향 범위: T-76(카테고리별 할인표 기록 · 계정별 프로모션 시작일) · 앞으로의 정산 계산 방식 확인 · 코드 변경 없음.
- 상태: ACTIVE (부분 SUPERSEDED by D-276 — 화면 확인 범위 '확실하지 않은 것' → 모든 수수료·공제 항목 · 윙 탭 계속 유지 · 부분 SUPERSEDED by D-277 — '한 번에 한 세션만 윙 화면' → 레인별 병렬 세션·각자 탭 하나)

### D-274 [SETTLE_FEE_PER_ITEM_FORMULA] D-272 근거 숫자 정정(배송비 추출 칸 밀림) · 로켓그로스 할인 B = 카테고리 할인표로 계산됨(유료 줄 100% 일치) — 입출고비·배송비 판정은 '부분' 그대로 (2026-11-17, R219)
- 결정(사실 정정 · D-270·D-273 적용): ① D-272 근거의 로켓그로스 배송비 M2 '8.78%'는 추출 칸 밀림(wellbing1107 배송비 원문 52개 파일 10,319줄 — '단품 판매가' 칸 때문에 판매수량·최종비용이 0으로 읽힘)이 섞인 숫자였다. 바로잡은 값 = 배송비 M2 절대오차 8.83%(100원 이상 114/134칸 · 실제 합 236,038,194 · 오차 합 +8,994,646) · M3b 7.62% · M3c 7.56%. 입출고비는 변화 없음. D-272 의 결정(입출고비·배송비 = 지금 규칙 유지)은 그대로. ② 윙 화면에서 받은 할인표 3개(홈>욕실용품 · 스포츠/레저>스포츠용품 · 가전>계절가전 ≈ 할인 B 합의 51%)로 계산하면 유료 줄이 전부 원문과 ±1원 안에서 맞는다 — 입출고비 = 수량 × 표(개별 사이즈 · 단품가 구간) · 배송비 = 표(총 사이즈 · 총 판매가 구간). 남는 차이는 실제 0원(무료 프로모션) 줄뿐(홈>욕실용품 9,734줄 · 스포츠용품 1,129줄) → 할인 B = 공식 가능 · 무료 0원 = 대상 목록 없이는 불가 · 항목 전체 판정 = 부분.
- 근거(통제 세션이 파일 대조): `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\대조_물류비_요약.md` 3·12행('11-17 정정' 표시 · 정정 전 = `_이전_1117\`) · `s14_줄일치.md` 표(유료 줄 표 일치 100.00%) · 할인표 기록 `윙확인_261117_할인표_홈욕실용품.md`·`…_스포츠레저스포츠용품.md`·`…_가전계절가전.md` · 바로잡은 추출 `_추출\배송비_정정.csv`(`s13_배송비_칸정정.py` · 검산 100%).
- 남은 일(T-76): 할인 B 합 순위 3~19위 카테고리 표 · 계정별 세이버·무료 체험·비용 제로 시작일(소유자 계정 전환) · 표 + 옵션 앞 달 단가(M2) 결합 계정×달 재대조(M4) → 그 결과로 입출고비·배송비 계산 방식을 새 D항목에 정함.
- 영향 범위: D-272 근거 줄 읽는 법 · T-76 · 코드 변경 없음.
- 상태: ACTIVE (부분 SUPERSEDED by D-286 — 근거 위치 대조_물류비_M3_요약.md 12행)

### D-275 [SESSION_CONTROL_CENTRALIZED] 새 세션 만들기는 통제 세션만 — 하위 세션은 세션·이어가기 카드를 만들지 않고 통제 세션에 보고하고 멈춤 (2026-11-17, R220)
- 결정(소유자 2026-11-17 원문): "세션 생성을 하위세션에서 하는 경우가있고 통제 세션이 하는 경우가 있어서 중복되는 일이 발생함. 너가 통제 해줘."
- 적용: 이 저장소 작업의 새 세션·이어가기 카드(start_session · own_initiative 카드 포함)는 통제 세션('Coupang Analytics' · local_8d110fe9)만 만든다. 하위 세션은 컨텍스트 한도·막힘·끝남 때 인계 파일을 갱신하고 통제 세션에 SendMessage 로 보고한 뒤 멈춘다(전역 D-014 보고 규칙 그대로). 통제 세션은 세션을 띄우기 전에 같은 일을 하는 세션·카드가 있는지(list_sessions linked) 확인하고, 같은 일의 카드는 하나만 둔다. 하위 세션 브리프에 '새 세션 직접 띄우지 말 것'을 넣는다.
- 근거: 11-17 하위 세션(local_7329032d)이 이어가기 세션(local_86553794)을 직접 띄운 것과 통제 세션 카드가 겹침 · T-76 카드 2장(task_3ed26086·task_52a7353c)이 모두 시작돼 같은 윙 화면을 두 세션이 쓸 뻔함(통제 세션이 local_66d1ed70 중단).
- 버린 대안: 하위 세션도 이어가기를 띄우되 통제 세션에 알림(지금 방식 — 중복 발생).
- 영향 범위: 모든 하위 세션 브리프 · 통제 세션 운영 · 코드 변경 없음.
- 상태: ACTIVE

### D-276 [SETTLE_FEE_VERIFY_ON_COUPANG] 수수료·공제 산출 방식은 모든 항목을 쿠팡 윙에서 직접 확인해 작성 · 접속한 윙 세션은 계속 유지 · 목표 = 정산 금액과 정산 예정 금액이 최대한 정확히 일치 (2026-11-17, R220)
- 결정(소유자 2026-11-17 원문): "그리고 쿠팡 접속했으면 계속 접속 상태를 유지해, 그래야 다른 건들도 확인 할수 있어. 모든 건을을 직접 확인해서 산출방식을 작성해야 돼. 정산 금액과 정산 예정 금액이 최대한 정확히 일치해야 함."
- 적용: ① D-273 의 '확실하지 않은 것만'을 넓혀 **수수료·공제 모든 항목**의 산출 방식을 윙 화면(비용·수수료 안내 · 정산 상세 · 도움말)에서 직접 확인해 근거(화면 위치·값)와 함께 적는다 — 정산 원문 대조로 맞은 항목도 화면 근거를 붙인다. ② 소유자가 로그인한 윙 탭은 작업이 끝나도 닫거나 로그아웃하지 않고 열어 둔다(다음 세션이 이어 씀 · 쿠팡 세션은 하루 안에 만료될 수 있음 → 풀리면 소유자에게 다시 로그인 부탁). ③ 목표 = 쿠팡 정산 금액과 우리가 낸 정산 예정 금액의 일치(D-268 예상 목적 · 100원 이상 차이 D-235). D-273 의 화면 규칙(로그인 = 소유자 · 화면 읽기만 · 페이지 안 API 호출 금지 · 한 번에 한 세션)은 그대로.
- 근거: 소유자 지시. 11-17 할인표 3개 화면 확인으로 유료 줄 100% 일치(D-274) — 화면 확인이 가장 정확한 근거임을 실측.
- 버린 대안: 불확실한 항목만 화면 확인(D-273 범위).
- 영향 범위: T-76 · 수수료 산출 보고서 `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\산출방식_보고.md` · 코드 변경 없음.
- 상태: ACTIVE

### D-277 [SETTLE_FEE_VERIFY_ON_COUPANG] 정산 항목 윙 확인은 레인별 병렬 세션으로 — 세션마다 자기 탭 하나 · 쿠팡이 제공하는 모든 자료를 찾아 정규화 산식 도출 (2026-11-17, R220)
- 결정(소유자 2026-11-17 원문): "다른 정산 항목들을 병렬로 체크하자. 쿠팡에 접속해서 필요한 자료를 확인해줘. 쿠팡이 제공하는 모든 자료를 검색해서 적용해야 해. 그래야 정규화된 산식을 도출할수 있어."
- 적용: D-273 의 '한 번에 한 세션만 윙 화면'(Claude 판단으로 넣은 줄 · 소유자 지시 아님)을 바꿔, 정산 항목 확인은 레인별 세션이 같은 로그인 Chrome 에서 **각자 새 탭 하나**로 병렬 진행한다. 레인(11-17) = A 입출고·배송 할인표(T-76 local_f3a8b001) · B 로켓그로스 기타 비용(local_11be162b) · C 판매수수료·할인 분담·계정 정액(local_884f95b3) · D 정산 일정·지급·차감·광고(local_6c4fd95d). 자료 = 윙 도움말 학습본 → 윙 화면(안내·정산 상세·요금표·공지) → 쿠팡 공식 웹. 화면 규칙(로그인 = 소유자 · 화면 읽기만 · 페이지 안 API 호출 금지 · 버튼 금지 · 빠른 연속 이동 금지 · 자기 탭만 · 탭 유지 · 내려받기는 소유자 승인)은 그대로 · 무거운 python 은 계속 한 번에 하나.
- 근거: 소유자 지시. 위험(사실): 11-17 페이지 안 API 1회 호출이 봇 차단에 걸림 → 화면 읽기·간격 규칙 유지.
- 버린 대안: 윙 화면 한 번에 한 세션(D-273 그 줄).
- 영향 범위: 레인 세션 4개 · 산출 보고서 레인별 파일(`D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\레인B_*.md`·`레인C_*.md`·`레인D_*.md` · 기존 `산출방식_보고.md` = T-76) → 통제 세션이 모아 D항목 · 코드 변경 없음.
- 상태: ACTIVE

### D-278 [SETTLE_FEE_PER_ITEM_FORMULA] 반품·취소·환불도 정규화 산출식으로 — 사건이 생긴 때 반영하되(D-270 ①) 정산 줄·수수료 환급·배송비·차감 회차·정산서 달을 산식으로 정함 (2026-11-17, R220)
- 결정(소유자 2026-11-17 원문): 통제 세션 표의 "반품·취소·환불 생기면 그때 반영 사장님 결정 D-270" 줄에 대해 "==> 이 건도 정규화된 산출식이 있어야 해."
- 적용: D-270 ① '반품·취소·환불 = 생기면 반영'(미리 예상하지 않음)은 그대로 두고, 반영할 때의 계산을 사건 유형별(취소 출고 전·후 · 반품 · 부분 반품 · 교환 · 정산 후 반품) 정규화 산식으로 정한다 — 판매액·쿠폰 음수 줄 · 판매수수료·윙 배송비 수수료 환급(끝전) · 반품 배송비(귀책별) · 로켓그로스 입출고·배송비 환불·회수비·재입고비 · 차감되는 회차 · 위탁자 정산서에서 속하는 달. 근거 = 윙 화면·정산 원문 대조(D-276·D-277 방식) · 레인 E 세션(local_3ca70f22).
- 근거: 소유자 지시.
- 버린 대안: 정산 원문에 찍힌 값을 그대로 옮기기만(산식 없음 — 정산 전 예상과 검산이 안 됨).
- 영향 범위: 위탁자 정산서 반품 처리(T-38) · T-71 장부 · 코드 변경 없음.
- 상태: ACTIVE

### D-279 [CONSIGNOR_STATEMENT_PENDING_SOURCE] 정산 예정 금액 = 쿠팡 '정산 예정' 줄이 이미 생긴 회차는 그 값 그대로 · 아직 안 붙은 공제는 규칙 경고값 · 줄 없는 기간만 우리 산식 · 지급일 아침 값 = 확정 (2026-11-17, R221)
- 결정(소유자 2026-11-17 — 통제 세션 질문 "'정산 예정 금액' 맞추는 기준을 이렇게 제안합니다: ① 쿠팡 예정 줄이 이미 생긴 회차는 그 값을 그대로 씀 ② 아직 안 붙은 공제(이용료 55,000·미납 물류비 이월·밀크런·광고비)는 규칙으로 계산해 따로 표시 ③ 줄이 없는 기간(아직 구매확정 전·이번 주)만 우리 산식 ④ 지급일 아침 값 = 확정. 이 기준을 쓸까요?" 에 선택 답 "채택 (권장)").
- 적용: ① 쿠팡 정산 예정 줄(키 = 계정·채널·정산일·비율 · 최신 스냅샷만 · 낡은 키 버림)이 있는 회차 = 그 금액 그대로 ② 그 줄에 아직 안 붙은 공제(윙 30% 줄 판매자서비스이용료 55,000 · 로켓그로스 미납 물류비 이월·밀크런·그 주 광고비×1.1)는 규칙으로 계산해 '경고값'으로 따로 표시하고 이미 들어간 것과 중복하지 않음 ③ 예정 줄이 없는 기간(구매확정 전·이번 주)만 우리 산식(D-269·D-272) · 지급일 = 기존 `payout.py` 규칙 ④ 윙 화면 머리 '예상금액'(그날 첫 줄만 보임)은 쓰지 않음 ⑤ 지급일 아침 재수집 값 = 확정. 관리 상품 몫 나누기는 D-269 그대로(이 결정은 계정 단위 예정 금액의 출처).
- 근거: 레인 D(local_6c4fd95d) `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\레인D_정산일정_지급_차감_광고.md` — sg0141n 화면(11-17) 예정 15줄 = 장부 DB(11-16) 원 단위 같음 · 전 계정 마지막 예정 = 지급: 윙 70% 67/67 · 100% 26/26 · 30% 23/24 · RG 70% 115/120 · 30% 88/92 · 100% 9/9 · 어긋남 10건 = 마지막 수집 뒤 붙은 이용료·이월 물류비·밀크런·월경계 반쪽 줄 이동(합 같음) · RG 화면 '지급 예상금액 5,239,025' = 미지급 10줄 합.
- 버린 대안: 예정 줄을 쓰지 않고 우리 산식만 · 화면 머리 '예상금액' 사용.
- 영향 범위: 위탁자 정산서 정산 예정 금액(T-38) · T-71 장부 · 정산 코드만(D-233) · 코드 변경 없음(구현 전).
- 상태: ACTIVE (부분 SUPERSEDED by D-285 — ② 로켓그로스 광고 '그 주 광고비×1.1' → 일별 청구금액 합)

### D-280 [SETTLE_SOURCE_REGISTRY] 모든 세션은 자료 출처와 받는 방식을 저장 — 앱이 매일 확인·받아 적용해 수수료 체계 등 변경을 즉시 반영 (2026-11-17, R222)
- 결정(소유자 2026-11-17 원문): "모든 세션은 자료 출처와 받는 방식을 저장해야 돼, 그리야 엡에서 다운받을때 항상 현황화를 시킬수 있어. 예를 들면 수수료 체계가 변경 되었을때 매일 체크해서 받아 적용하면 변경된건이 즉시 반영 될수 있어. 다른 항목도 동일함."
- 적용: ① 정산 산식에 쓰는 값(단가·표·비율·규칙)마다 출처(윙 메뉴 경로·화면 이름·URL 경로 / 정산 원문 파일 종류·칸 / 공개 웹 URL) · 받는 방식(화면 읽기 / 내려받기 이름 / 앱이 이미 받는 모듈) · 변경 단서(적용 시작일·공지·표 날짜) · 확인 주기를 기록한다. 레인마다 `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\자료출처_<레인>.csv`(열 = 항목,값,출처,받는방식,변경단서,확인주기,확인일) → 통제 세션이 하나의 출처 목록으로 모은다. ② 앱 기능(구현 전 · T-78): 그 목록대로 매일(또는 정한 주기) 출처를 확인해 값이 바뀌면 받아 적용하고 변경 이력(이전 값·바뀐 날)을 남긴다 — 수수료·할인표·요금표·정산 규칙 모두. 윙 화면 확인 규칙(D-273·D-276·D-277)과 로그인 정책(CONSTRAINTS)은 그대로.
- 근거: 소유자 지시 · 11-17 레인 조사에서 요율이 기간별로 바뀐 사례(기타 악세서리 입출고 표 2026-09부터 변경 · 밀크런 2025-08-01 인상 · Fee-Table 2019-11-25 기준) 확인.
- 버린 대안: 조사 때 한 번 읽은 값을 고정 사용(바뀌면 오차).
- 영향 범위: 모든 정산 조사·구현 세션 브리프 · 앱 자료 받기(T-78 · 정산 코드만 D-233) · 코드 변경 없음(구현 전).
- 상태: ACTIVE

### D-281 [SETTLE_MATCH_BY_AMOUNT] 정산 산식 정상 판정 = 금액 일치(반올림·버림 끝전만 차이) — 비율(%)로 판정하지 않음 · 비율 계산은 참고용(토큰 낭비 금지) (2026-11-17, R223)
- 결정(소유자 2026-11-17 원문): "비율표로 정상 여부를 판정하는 기준은 오류임, 정산(예정) 금액은 동일해야 함. 차이 금액이 거의 없어야 정상임(반올림, 버림 반영시). 그런데 비율로 판정을 하고 있고 비율을 계산한다고 토큰을 낭비하고 있음, 비율은 참고용임."
- 적용: 정산 산식·정산 예정 금액 검증의 정상 기준 = 줄·회차·계정×달마다 (우리 계산 금액 − 쿠팡 금액)이 반올림·버림 끝전만 남는 것. 그 밖의 차이는 해당 줄을 찾아 원인(자료 없음·규칙 모름·칸 오류)과 금액을 적고 고칠 방법을 낸다 — 남은 차이가 있으면 '정상'이 아님. 절대오차율·일치율 같은 비율(%)은 판정에 쓰지 않고 보고에도 꼭 필요할 때 한 줄 참고로만. D-268 의 '오차 합 최소' 비교는 안을 고를 때의 비교일 뿐, 고른 안도 금액이 일치하지 않으면 원인을 찾아 고쳐야 한다(정상 판정 아님). D-235(100원 이상 = 영향 있음)는 보고 기준으로 그대로.
- 근거: 소유자 지시. 11-17 레인 보고가 '7.09%·0.537%' 같은 비율로 '판정'을 내린 것에 대한 정정.
- 버린 대안: 절대오차율·일치율로 정상 판정(Claude 이전 방식).
- 영향 범위: 모든 정산 조사·검증 세션 브리프와 보고 형식 · D-268·D-272·D-274 의 비율 표현은 참고로 읽음 · 코드 변경 없음.
- 상태: ACTIVE

### D-282 [CONSIGNOR_STATEMENT_PENDING_SPLIT_RULE] 윙 '확인 필요' 채우기 마지막 단계 = 운용 시점 Ap30 그 달 판매 비율(결제일 [그 달 1일−30, 기준일−1] − 이미 확정된 판매 · 앱이 그날 가진 자료만) — D-269 ①의 '가장 이른 미정산 결제일부터'(사후값) 대체 (2026-11-17, R226)
- 결정: D-269 ① 순서(주문별매출 실제값 → B8+환산 → ⓒ2 지연 분포)의 마지막 단계를 **ⓑo**로 바꾼다. 비율 = 판매분석 일별(그 달 1일−30일 ~ 기준일−1일) 순액 − 이미 확정된 판매(앱이 받은 달의 주문별매출만 · 말일+15일 뒤) 의 관리 비율 × 쿠팡 예정 정산. 지연 분포·주문별매출·윙 정산 파일은 기준일 전에 앱이 받은 것만 쓴다. 셋 다 안 되는 금액만 '확인 필요'.
- 결정 경위(소유자 2026-11-17 원문): 통제 세션이 "무엇으로 바꿀까요?"(ⓑo 추천 · 옛 코드 비율 · 확인 필요로 남김)를 묻자 **"판단불가함"**. → D-269 를 만든 소유자 위임("쿠팡이 정산이 끝난 달의 데이타로 검증해서 결정해줘." 2026-11-17)과 D-268 기준(정산 끝난 달 실제와의 오차 합 최소)으로 통제 세션이 정함.
- 근거(`D:\coupang-analytics\output\_검증_261117_정산끝난달\판정_보고.md` 6-1b · 같은 틀로 6-1 값 원 단위 재현 확인 · 윙 3,036칸): 확인 필요 그대로(T-73 3f23e7c) 약 71,943,443 · 옛 코드 A' 54,855,548 · D-269 A(사후값 · 운용 불가) 24,035,881 · **ⓑo 23,832,621(100원 이상 324칸 · 최대 287,503 · 빠진 관리 몫 422,838)** · ⓓ1o 지연 최대 34일 24,121,235 · ⓓ2o 누적 99% 28,981,088. 운용 불가 이유 = 그 달 주문별매출(말일+15일 뒤 받음)이 있어야 시작일을 앎(`t66_wing.py:46` S_A · T-73 세션 보고).
- 버린 대안: D-269 A(운용에서 계산 불가) · A' 옛 코드(오차 2.3배) · 확인 필요로 남김(오차 3배) · ⓓ 지연 분포 시작일(ⓑo보다 큼).
- 남는 위험(사실): ⓑo 는 100원 이상 칸이 A 보다 많음(324 대 290) · 작업일 200칸 오차 합 1,340,239(A 1,159,043 보다 181,196 큼) · 쿠팡 예정 정산(T_a)을 운용에서 안다는 가정은 확인 안 함. D-281 상 고른 안도 금액 일치가 아니므로 남은 차이는 줄 단위 원인 조사 대상.
- 영향 범위: T-73 브랜치 `claude/t73-pending-d269-4ae793` 3f23e7c 의 `settlement_statement_pending.py` 에 ⓑo 단계 추가(병합 = 소유자 승인 뒤) · CURRENT_RULES 12절.
- 상태: ACTIVE

### D-283 [CONSIGNOR_STATEMENT_WING_AD_DEDUCTION] 윙 광고비 정산서 반영 = 쿠팡 줄 값 우선 · 없으면 그 주 윙(SELLER) 광고 × 1.1 을 집행 주 70% 줄 예상 공제(모자라면 다음 줄 이월) · 광고 지원금은 광고비가 줄어든 몫만 (2026-11-17, R228)
- 결정: ① 쿠팡 정산 줄에 '상품/브랜드광고비'가 있으면 그 값(D-279 그대로). ② 줄이 아직 없으면 그 주 광고센터 일별 청구(배송유형 SELLER = 윙) 합 × 1.1(부가세 포함)을 그 주 판매의 70% 정산 줄에서 공제할 예상값으로 넣고, 그 줄 지급가능액이 모자라면 모자란 만큼 다음 정산 줄(30% 줄·다음 주 70% 줄)로 이월. ③ 광고 지원금(쿠폰·크레딧)은 청구 광고비가 줄어든 몫으로만 반영하고 따로 더하지 않음(이중 반영 금지).
- 결정 경위(소유자 2026-11-17 원문): 통제 세션이 T-83 'D-283 후보'(위 ①~③)를 포함한 결정 목록을 올리자 **"제안 수용."**
- 근거: `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\레인D_윙광고공제_앱자료대조.md`(윙 광고 공제 = 로켓그로스와 같은 규칙 · 123달 중 일치 47 · 이월 일치 20 · 불일치 56 · 11계정 1년 누적 ±3원) · `레인D_윙광고공제시점_가이드.md`(공식 가이드 1·2차) · 광고센터 getDailySettlement `subtotals`(날짜×배송유형 부가세·청구금액 · T-82 866fa05 병합).
- 버린 대안: 달 합으로 공제(주 단위 정산 줄과 안 맞음) · 지원금을 따로 더함(청구액에 이미 반영 → 이중) · 광고비를 정산서에서 빼지 않음(쿠팡이 실제로 공제).
- 남는 위험(사실): 불일치 56달의 이유(지급가능액 있는데 공제 0 인 줄 · 부족분 받는 순서) 미확인 · 로켓그로스+윙 광고를 같이 하는 계정은 일별 보고서(subtotals)가 있어야 윙 몫을 주 단위로 나눔 — 이미 받은 옛 달 json 에는 subtotals 없음.
- 영향 범위: T-38 위탁자 정산서 구현(정산 코드만 D-233) · CURRENT_RULES 12절.
- 상태: ACTIVE (부분 SUPERSEDED by D-285 — ② 윙 '그 주 70% 줄' → 달 단위 · 부족분 이월 순서 미확정)

### D-284 [CONSIGNOR_STATEMENT_PENDING_SPLIT_RULE] 윙 정산 예정분 나누기 ② B8+환산 · ③ ⓒ2 도 기준일에 앱이 가진 자료만(ⓑo 와 같은 자르기) — D-269 ①의 '자르지 않음' 대체 (2026-11-17, R229)
- 결정: B8·ⓒ2 가 쓰는 주문별매출·결제→구매확정 지연 분포·저장 분포·윙 정산 파일·환산 비율을 ⓑo(D-282)와 같은 기준으로 자른다 — 주문별매출 = 기준일 전에 받은 달(말일+15 ≤ 기준일)까지 · 지연 분포 = 그 달까지 · 저장 분포는 그 '기준 달' 이하일 때만 · 윙 정산 파일 = 정산일 ≤ 기준일(정산일 모르면 확인 필요).
- 결정 경위(소유자 2026-11-17 원문): 통제 세션이 "매일 운용엔 영향 없고, 지난 정산서를 다시 만들 때(정정 T-72·백테스트)만 기준일 뒤 자료가 섞여 그때 보냈을 금액과 달라짐 · 추천 = 자름"으로 설명하자 **"T-84 자르기로 해줘"**.
- 근거: `src/coupang_analytics/settlement_statement_pending.py` `_wing_one`(c305b09 기준) — B8 = `_wing_known(orders, ym)`·`lag_pmf(base, ym)`·모든 윙 정산 파일 · ⓒ2 = `stored_pmf(base)`(더 늦은 달 분포도 씀) · ⓑo 만 `cut = min(ym, _received_ym(basis))`·`settle_date <= basis` (T-73b 보고).
- 버린 대안: 자르지 않음(다시 만들 때마다 금액이 바뀌고 백테스트 오차가 실제 운용보다 작게 나옴).
- 영향 범위: 정산 코드만(D-233) · 구현 = 세션 t84-cut 브랜치(병합 = 통제 세션) · ① 실제값(`wing_actual`)이 같은 문제를 갖는지는 그 세션이 보고만(범위 밖) · CURRENT_RULES 12절.
- 상태: ACTIVE (확장 D-292 — ① 실제값도 같은 자르기)

### D-285 [CONSIGNOR_STATEMENT_AD_DEDUCTION_PRECISION] 광고 공제 예상값 정밀화 — 로켓그로스 = 그 줄 매출기간 일별 청구금액(VAT 포함) 합 · 윙 = 달 단위 · 광고 부족분 이월 순서 = 미확정(쿠팡 줄 값만) (2026-11-17, R229)
- 결정: ① 로켓그로스 광고 공제 예상값 = 그 정산 줄 매출기간의 광고센터 **일별 청구금액(VAT 포함) 합**(D-279 의 '그 주 광고비×1.1' 대체). 일별 청구금액이 없을 때만 청구가능 합 × 1.1 을 쓰고 '±1원 가능 — 일별 자료 없음' 표시(차이 0 이 보장 안 됨을 드러냄 · 앱은 getDailySettlement `subtotals` 로 일별 값을 받음 T-82). ② 윙(SELLER) 광고 예상 공제 = **달 단위**(그 달 윙 광고 일별 청구금액 합을 그 달 정산 줄에서 공제 · 모자라면 다음 줄 이월) — D-283 ② '그 주 70% 줄' 대체. ③ 광고 부족분이 어느 줄로 가는지는 규칙으로 정하지 않음(미확정) — 쿠팡 정산 줄 값(D-279 ①)만 쓰고, 줄이 오기 전 예상값에는 '이월 순서 미확정' 표시. ④ 쿠팡 줄 값이 오면 언제나 그 값으로 바꾸고 예상과의 차이는 다음 정산서 한 줄(D-264).
- 결정 경위(소유자 2026-11-17 원문): T-87 결정 7건을 올리자 **"내가 확정하는것은 어려줘, 너가 정산금액 확정시 정확하게 할수 있는 방안으로 확정 해줘, 정확하다는 의미는 정산금액 차이가 zero 이어야 함."** → 통제 세션이 '차이 0 에 가장 가까운 근거가 있는 안'으로 정함.
- 근거: `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\T87_보고서차이_정리.md` 3절 1~3번 · `T87_근거\partD\t17_lines.csv`(로켓그로스 이월 없는 70% 줄 56개: 일별 청구금액 합 56/56 원 단위 일치 · ×1.1 은 41/56 · 나머지 ±1원 = 쿠팡이 부가세를 날마다 반올림) · `T87_근거\partD\t28_wing_lines.csv`(윙 70% 줄 배정 tellace83 5/36 일치) · `레인D_윙광고공제_월대조.csv`(123달 중 일치 47 · 이월 일치 20 · 11계정 1년 누적 ±3원) · 부족분 이월 반례 sg0141n·tellace83(T87-28).
- 버린 대안: 로켓그로스 ×1.1 그대로(±1원 차이) · 윙 주 단위 70% 줄(일치 5/36) · 부족분 이월 순서를 지금 정함(반례 있음 → 차이 0 근거 없음).
- 남는 위험(사실): 윙 달 단위도 123달 중 불일치 56달 → 차이 0 아님 · 원인(지급가능액 있는데 공제 0 인 줄 · 부족분 순서) 조사가 남음. 일별 청구금액 없는 옛 달 json(subtotals 없음)은 ①의 ×1.1 경고값.
- 영향 범위: T-38 위탁자 정산서 구현(정산 코드만 D-233) · CURRENT_RULES 12절 · D-279 · D-283 상태 줄.
- 상태: ACTIVE (보완 D-289 — ② 줄 배정 한도·광고 공제 대조 방법)

### D-286 [SETTLE_FORMULA_TEXT_CORRECTION] 결정 문구 정정 3건 — D-261 E3 8,880 = PostPurchase 칸 · D-272 보관 31~45일 무료 = 1차 의류·신발·악세서리 + 세이버 가입 달 · D-274 근거 위치 = 대조_물류비_M3_요약.md 12행 (2026-11-17, R229)
- 결정: ① D-261 E3 의 sg0141n 11-27 로켓그로스 8,880원은 '추가 공제 − 내역 칸 나머지(사유 미표시)'가 아니라 원문 `totalPostPurchaseDeductionAmount`(PostPurchase · 리뷰 이벤트) 칸. ② D-272 보관비 '31~45일 일부 카테고리 무료' = 1차 의류·신발·악세서리 + 세이버(비용 제로) 가입 달 전 카테고리 — 2차 '스포츠용품'은 뺌. ③ D-274 근거 인용 위치 = `대조_물류비_M3_요약.md` 12행(숫자 8.83%·+8,994,646 자체는 그대로).
- 결정 경위: D-285 와 같은 소유자 원문(2026-11-17 "…정산금액 차이가 zero 이어야 함").
- 근거: `T87_보고서차이_정리.md` 2절 26번(원문 칸 8,880 · 1,290,547−69,700−454,056+327,392=1,094,183 원 단위) · 4번(스포츠용품 무료 7,187줄 2,516,289원 = 전부 tellace83 세이버 가입 달 · 같은 달 다른 카테고리도 무료 · 스포츠용품 넣어도 빼도 화면 기준 차이 0 → 원인 = 세이버) · 1번(파일 대조).
- 버린 대안: 문구 그대로(원인 설명이 틀려 다른 계정·달에 잘못 적용될 위험).
- 영향 범위: 정산 산식 문서·엑셀 '정산항목_산식' · T-38 · D-261·D-272·D-274 상태 줄.
- 상태: ACTIVE

### D-287 [SETTLE_FORMULA_CONFIRMED] 산식 확정 2건 — 16 윙 주정산 70%·최종액 30% 금액 몫 · 신규-16 월경계 반쪽 줄 지급일(로켓그로스 30% 반쪽 줄 = 같은 기간 70% 지급일 + 5영업일) (2026-11-17, R231)
- 결정: ① 항목 16 = 윙 주정산 70% 금액은 구매확정일 하루 합마다 × 0.7 사사오입, 최종액 30% = 나머지(금액 몫 · 윙 100% 줄 뜻은 범위 밖). ② 신규-16 = 월 경계 주의 반쪽 줄 지급일 · 로켓그로스 30% 반쪽 줄 지급일 = 같은 기간 로켓그로스 70% 지급일 + 5영업일('각 달 묶음' 문구 대체). 엑셀 '정산항목_산식' 상태 = 확정(다음 엑셀 다시 만들 때 반영).
- 결정 경위(소유자 원문 2026-11-17): "너가 정산금액 확정시 정확하게 할수 있는 방안으로 확정 해줘, 정확하다는 의미는 정산금액 차이가 zero 이어야 함." → 차이 0 이 여러 달·계정에서 확인된 것만 통제 세션이 확정.
- 근거: `D:\coupang-analytics\output\_검증_261117_샘플산식\2차\샘플검증2_보고.md` 2절 — 16 = 2026-07·08·09 × 기존 5샘플 12칸 0원(해당 없음 3) + 후보 9계정 3달 0원 · 신규-16 = 15칸 다른 날 0회차 · RG 30% 반쪽 줄 30/30 일치 · 1차 `샘플검증_보고.md`(2026-09 5샘플 일치).
- 버린 대안: 한 달 샘플만으로 확정(T-89 1차 · 근거 부족).
- 남는 위험(사실): novanest1284 2026-08 로켓그로스 100% 달 단위 줄 지급일 = 실제 09-30 · 코드 10-07(원인 미조사 → T-97).
- 영향 범위: 정산 산식 엑셀 · T-38 · CURRENT_RULES 12절.
- 상태: ACTIVE

### D-288 [SETTLE_DECISION_DELEGATION] 정산 산식·판정의 '소유자 결정' 건 = 통제 세션(Claude)이 정산금액 차이 0 기준으로 판단·확정 — 모든 세션·앞으로 생기는 건까지 상시 적용 (2026-11-17, R231)
- 결정: ① 정산 산식·나누기 규칙·공제 배정·판정(대조) 방법·정산 자료 해석처럼 **정산금액에 영향을 주는 '소유자 결정' 건은 소유자에게 묻지 않고 통제 세션이 판단해 D항목으로 확정**한다(STATE 의 [소유자 결정] 정산 건 포함 · 이미 열린 건과 앞으로 생기는 건 모두). ② 판단 기준 = **정산금액 차이 0**: 끝난 달 쿠팡 실제 금액과 원 단위(끝전만 허용 D-281)로 맞는 것이 여러 달·계정에서 확인된 안을 고른다. 차이 0 근거가 없으면 추측으로 확정하지 않고 '미확정'으로 두며, 쿠팡 실제 줄 값을 쓰고 예상값에 미확정 표시(D-279·D-285 ③ 방식). 안끼리 차이가 같으면 가정이 적고 자료로 다시 확인할 수 있는 안. ③ 하위 세션은 결정 후보·근거를 통제 세션에 보고만 하고, 확정·D항목 기록은 통제 세션이 한다(D-275 · 단독 확정 금지). ④ 결정마다 근거(파일·줄·금액)·버린 대안·남는 위험을 적고, 소유자에게는 결과를 보고한다.
- 위임 범위 밖(소유자 몫 그대로): 로그인·비밀번호·2차 인증 · 돈 지급·송금 · 위탁자·계약자에게 정산서·자료를 보내는 일 · 되돌릴 수 없는 삭제 · 배포·운용 PC 설치 · 안전 규칙(로그인 방식·프록시·페이지 스크립트 금지 등 CLAUDE.md·CONSTRAINTS) 변경 · 계약 조건(비율·보장액 등 계약서 내용) 자체. 이 범위의 질문은 계속 소유자에게 묻는다.
- 결정 경위(소유자 원문 2026-11-17): "소유자 결정건은 너가 판단해줘, 내 판단이 잘못되면 정산시 산식을 틀려 질수 있어, 그러면 정산 금액에 차이가 발생함, 너가 판단해서 정산금액 차이가 zero가 되도록 판단하고 결정해줘. 다른 세션도 동일하게 적용하고 앞으로 발생하는 소유자 판단과 결정은 지금 설명에 근거하여 항상 적용해줘." · 앞선 위임 = 같은 날 "너가 정산금액 확정시 정확하게 할수 있는 방안으로 확정 해줘, 정확하다는 의미는 정산금액 차이가 zero 이어야 함."(D-285~D-287 경위).
- 근거: 같은 날 D-285·D-286·D-287 이 이 방식으로 확정됨(근거 = 원 단위 일치 실측).
- 버린 대안: 정산 결정마다 소유자 확인(소유자 원문 — 판단이 틀리면 산식이 틀려 정산금액 차이 발생) · 하위 세션도 각자 확정(결정 충돌·D-275 와 어긋남).
- 영향 범위: STATE 의 [소유자 결정] 정산 건(T-91·T-81·T-64·T-72·T-32·T-36 등)을 통제 세션이 차례로 판단 · 하위 세션 브리프 · CURRENT_RULES 12절·그 밖 주제.
- 상태: ACTIVE

### D-289 [CONSIGNOR_STATEMENT_AD_DEDUCTION_PRECISION] 윙 광고 예상 공제 한도 = 지급가능 − 그 줄 다른 공제(빠른정산 계정은 '한도 미정') · 광고 공제 달 대조 = 지급 순서 누적 — D-285 ② 보완 (2026-11-17, R231)
- 결정: ① 윙 광고 예상 공제를 정산 줄에 배정할 때 그 줄에서 빠질 수 있는 한도 = **지급가능액 − 그 줄의 다른 공제(빠른정산 계좌인출·성장 대출·판매자서비스이용료 등 광고보다 먼저 빠지는 공제)**. 줄 공제 = min(그 달 자기 몫 + 앞에서 남은 부족분, 한도) · 남은 몫은 부족분으로 이월. 빠른정산 계정은 인출액이 쿠팡 줄이 와야 정해지므로 줄 오기 전 예상값에 **'빠른정산 계정 — 한도 미정'** 표시. ② 광고 공제 대조(검증) 판정 = 매출달별 합이 아니라 **지급 순서 누적**으로(달 넘긴 이월은 뒤 줄에서 누적 0 이면 일치). ③ 부족분이 다음 주 70% 줄과 그 달 30% 줄 중 어디로 가는지는 계속 미확정(D-285 ③ 유지 · 쿠팡 줄 값 사용).
- 결정 경위: 소유자 2026-11-17 "①② 확정해줘" + D-288 위임.
- 근거: `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\T90_윙광고공제_차이0.md` 1·3절 · `T90_윙광고공제_줄별판정.csv`(159줄: 한도 = 지급가능 − 다른 공제 125줄 원 단위 일치 · 한도 = 지급가능 40줄 · 안 맞는 34줄 = 부족분 행선지만 다름, 쌍 합 0원) · tellace83 원 단위 예(247,536−181,637=65,899 · 90,291 = 35,355+54,936 · 7월 30% 줄 23,212 = 남은 부족분) · `T90_윙광고공제_달별판정.csv`(달 단위 불일치 56달 중 C 달 넘긴 이월 24달 = 뒤 달 누적 0) · 재현 `T90_근거\sim.py`·`cls.py`.
- 버린 대안: 한도 = 지급가능만(40/159) · 70% 줄은 자기 몫만·부족분은 30% 줄(90/159) · 같은 달 부족분만(118/159) · 부족분 행선지 규칙 지금 정함(gorocket23 6/8~14 부족 51,641 중 14,694 만 다음 줄 → 규칙 재현 안 됨).
- 남는 위험(사실): 34줄 행선지 미확정 → 회차별로는 차이가 남고 달·쌍 합으로만 0 · 자료 없음 달(seankim137 2026-05~07·gbseller808 2025-12·ygkim1 2025-10 광고 json · 91white·WBpeak 로켓그로스 줄 광고 공제 0)과 2026-10 미정산 10달은 미검증 · 'Difpick 윙 정산 줄 0'(−5,764,567)은 T-90 이 쓴 장부 시험 DB 가 `--exclude Difpick` 으로 만들어져 생긴 값일 수 있음(디프픽 = 우리 사업자 정산 계정 · 통보 대상만 제외 D-076 버린 대안·D-088 근거 10-19 원문) → 원천 정산 파일로 다시 대조.
- 영향 범위: T-38 위탁자 정산서 구현(정산 코드만 D-233) · 광고 공제 검증 스크립트 · CURRENT_RULES 12절 · D-285 상태 줄.
- 상태: ACTIVE

### D-290 [SETTLE_PAYOUT_DATE_RULE] 로켓그로스 월정산 100% 줄(기간 = 그 달 1일~말일) 지급일 = 월 마감일 + 20영업일 (2026-11-17, R231)
- 결정: 로켓그로스 100% 정산 줄 중 기간이 그 달 1일~말일 전체인 줄 = 월정산(MONTHLY) → 지급일 = 월 판매마감일 + 20영업일(`PAYOUT_RG_MONTHLY`). 주정산 월말 조각 100%(7일 이하)·70%·30% 는 그대로(주 마감일 + 20영업일 등). 판별 = 기간 모양(쿠팡 응답 `settlementCycle` 은 지급 내역에 저장되지 않음).
- 결정 경위: D-288 위임(통제 세션 판단) · T-97(T-96 관찰: novanest1284 2026-08 실제 09-30 · 코드 10-07).
- 근거: `docs/COUPANG_WING_HELP_KB.md` 93줄 "월정산 = 월 판매마감일 +20영업일(100%)" · D-075 근거(소유자 화면 실측 '월정' 08-01~08-31 → 09-30) · 장부 시험 DB(`output\_시험_261116_장부DB\장부_2차.sqlite`) 로켓그로스 1,999줄: 수정 전 다름 7줄(전부 달 전체 100% 줄 — novanest1284 2026-08 · freewin7777 2025-09·12·2026-03·06·08·09) → 수정 후 전부 일치(100% 42/42 · 70%·30% 변화 없음) · 시험 P20(월정산 3건 + 월말 조각 회귀 막이) · run_checks 25 통과(브랜치 659ae4d · 병합 fb6afa4).
- 버린 대안: 100% 줄 모두 주 마감일 + 20영업일(옛 코드 · 말일이 평일인 달 어긋남).
- 남는 위험(사실): 달 중간에 월정산↔주정산이 바뀌어 달 일부만 담긴 월정산 줄은 못 잡음(지금 자료엔 없음 · novanest1284 = 09-01 경계 전환).
- 영향 범위: `src/coupang_analytics/payout.py` `rg_payout_date` · 지급일 대조(`settlement_verify.paydates`) · D-287 ② 영향 없음 · CURRENT_RULES 12절.
- 상태: ACTIVE

### D-291 [SETTLE_SOURCE_DAILY_FETCH] 자료 출처 목록대로 받기(D-280 · T-78) 설계 판단 8건 — 매일 머리 글자+원문 대조·주 1회 전체 · 공개 웹 = 쿠키·프록시 없는 일반 연결 · 비공식 웹 자동 수집 안 함 · 공지 이미지 판독 = Claude · 적용 시작일 순서 · 광고 이번 달 일별 매일 · 목록 정정 · 교환은 T-80 뒤 (2026-11-17, R231)
- 결정: ① 주기 = 매일 머리 글자(시작일·종료일·배지) + 원문 대조(M-E) · 매주 1회 전체 표(요일 = 운용 로그로 정산 일이 가장 적은 날 · 정하기 전 일요일) · 원문에 새 카테고리 쌍이 나오면 그날 그 카테고리만 — 단 화면 전체 표를 앱이 받는 방식(Q1)은 소유자 확인 전이라, 그 전까지 주 1회 전체 표 = 하위 세션 화면 확인(D-276·D-277). ② 공개 웹 = 로그인 없는 일반 연결(쿠키·프록시 없음). ③ 비공식 웹(기사·블로그) = 자동 수집 안 함 · 참고 기록만. ④ 공지 이미지(밀크런 별지 등) = 앱은 새 글·이미지 저장 + 변경 알림만 · 판독은 Claude 세션(결과·근거를 표 파일로). ⑤ 표가 바뀌었을 때 적용 시작일 = 화면 문구 날짜 → 없으면 원문 유료 줄이 처음 어긋난 날 → 없으면 감지한 날(근거 기록 D-070). ⑥ 광고 일별 = 이번 달 1일~어제를 매일 덮어쓰기(getDailySettlement 기존 경로) · 옛 달 subtotals 다시 받기는 T-90 이 필요한 계정·달만(지금 속도). ⑦ 자료 출처 목록 정정 = 17 '일부'(끝난 달+3일 뒤만 · 옛 달 subtotals 없음) · 18·19 '받음'. ⑧ 교환(21행) = T-80 에서 교환관리 화면 확인 뒤 다시 설계 · 그때까지 받을 수 없음.
- 위임 밖(소유자 확인 대기 · 확정 아님): Q1 앱이 fee-details 화면 조작 + 화면 응답 기록 · Q2 첫 라이브 시험(sg0141n 1회·카테고리 3개) · Q8 상품 수량·categoryId 보관 = collector 변경(D-233) · Q10 도움말 FAQ 새 주소 페이지 안 호출 — 안전 규칙·앱 본래 기능 범위(D-288 범위 밖).
- 결정 경위: D-288 위임 · T-78 설계 세션 추천안(하위 세션 판단 · 소유자 지시 아님)을 통제 세션이 검토.
- 근거: `D:\coupang-analytics\docs\plans\T78-source-list-daily-fetch-design-2026-11-17.md` 7절 표(Q3~Q7·Q9·Q11·Q12 근거 칸) · 4절 코드 근거(`settlement_ads.py:44~62·175` · `settlement_verify_collect.py:146·205`) · D-274(할인표 20개 유료 줄 ±1원) · D-285(로켓그로스 광고 공제 = 줄 매출기간 일별 청구 합 → 이번 달 일별 필요).
- 버린 대안: 매일 화면 전체 훑기(접속 횟수 = 차단 위험 증가 · 원문 대조가 먼저 잡음) · 비공식 값으로 산식 변경(화면·원문 값 우선 → 차이 발생) · 옛 달 광고 전부 다시 받기(광고센터 접속만 늘림).
- 영향 범위: T-78 구현(정산 코드만 D-233 · 단계 S0~S7 · S4 = Q1·Q2 확인 뒤) · `output\_조사_261117_쿠팡수수료산출\자료출처_목록.csv` 17·18·19행 · CURRENT_RULES 12절.
- 상태: ACTIVE (보완 D-296 — Q1·Q2·Q8·Q10 소유자 답)

### D-292 [CONSIGNOR_STATEMENT_PENDING_SPLIT_RULE] 윙 정산 예정분 ① 실제값(`wing_actual`)도 기준일에 앱이 가진 자료만 — B8·ⓒ2·ⓑo 와 같은 자르기(D-284 확장 · T-91) (2026-11-17, R231)
- 결정: `_wing_one` 의 ① 실제값도 `basis_data()` 와 같은 기준으로 자른다 — 주문별매출 = `cut = min(ym, _received_ym(basis))` 앞 달까지(기준일 전에 받은 것) · 윙 정산 파일 = 정산일 ≤ 기준일. 매일 운용(만드는 날 = 기준일+1)은 금액이 그대로이고, 지난 정산서를 다시 만들 때 기준일 뒤 자료가 섞이지 않게 한다.
- 결정 경위: D-288 위임(통제 세션 판단) · T-91(T-84 세션 관찰).
- 근거: `src/coupang_analytics/settlement_statement_pending.py` 354행 `wing_actual(orders.get(ym…), wing[0], …)` = 자르지 않은 그 달 주문별매출 + 모든 윙 정산 파일 · 228~236행 `basis_data()` 는 자름(D-284) · ①은 쿠팡 예정 금액과 원 단위 같을 때만 쓰임(143행) · 11-15 정산서 실측 ① 16/16 일치(`output\_검증_261117_정산끝난달\결과_2_3.md` 21·61행) · 3일 정산서 기준 ① 19줄 대 0줄(같은 파일 27행 — 다시 만들 때 뒤 자료가 결과를 바꿈).
- 버린 대안: 그대로 둠(다시 만들 때마다 금액이 바뀌고 백테스트가 운용보다 좋게 나옴 · D-284 버린 대안과 같은 이유).
- 남는 위험(추정): '기준일+1 에 만든다' 가정은 11-15 한 사례 · 구현 뒤 11-15 정산서를 다시 만들어 ① 16줄이 그대로인지 확인 필요.
- 영향 범위: 정산 코드만(D-233) · 구현 = 별도 작업(T-91) · CURRENT_RULES 12절 · D-284 상태 줄.
- 상태: ACTIVE

### D-293 [SETTLE_FORMULA_CONFIRMED] 로켓그로스 취소 환불(43-2 입출고비 · 44-2 배송비) = 누적 사사오입(R9) · 같은 날 무료 수량 소진 순서 = 쿠팡 파일 행 순서 (2026-11-17, R231)
- 결정: ① 43-2·44-2 취소 줄 환불 = −사사오입(원 비용 × 누적 취소수량 ÷ 원 수량) − 앞 취소 줄 합 · 원 줄 = 취소 줄보다 앞선 줄(매출인식일 → 파일 기간 → 행 순) 합·수량 · 0원·유료가 섞이면 0원 줄은 뺌(R9). ② 같은 날 무료 수량(회수·재입고)이 어느 줄에 먼저 쓰이는지 = 쿠팡 파일 행 순서(발생일 → 파일 기간 → 행).
- 결정 경위: D-288 위임 · T-95 하위 세션 후보를 통제 세션이 확정.
- 근거: `D:\coupang-analytics\output\_검증_261117_묶음D_반품끝전\T95_보고.md` 1·4절 — ① 원 줄 있는 취소 12,823줄 × 2항목 전부 줄 단위 0원(레인 E 식 R1 12,816·12,746 · 오차 +5,867·+24,472 해소 · `s3_후보.csv`) ② 자료 있는 칸 전부 0원(회수 어긋남 0 · 재입고 2줄 금액 0 · `s2_순서후보.csv`) · 반품 오차 분해 합 일치(`반품오차_분해표.csv`).
- 버린 대안: 레인 E 식(줄마다 비례 · 끝전 오차) · 출고 전 취소 0 가정(원 줄 없는 252줄 = 계정 자료 시작 전 주문 → 엑셀 설명 틀림).
- 남는 위험(사실): 원 줄 없는 취소 252줄은 자료 시작 전 주문이라 미검증 · 신규-06 RG 부분 취소 VAT 끝전은 미확정(H1 267/286 · 19줄 합 −7원 · 정산서는 원문 VAT 칸 사용).
- 영향 범위: 정산 산식 엑셀 '정산항목_산식' 43-2·44-2 · T-38 · CURRENT_RULES 12절.
- 상태: ACTIVE

### D-294 [CONSIGNOR_STATEMENT_PENDING_SPLIT_RULE] 관리 몫 입금 나누기 — 이미 지급된 줄 = 그 줄 실제 관리 몫 그대로 · ②(정산 중 예상분) 잔액은 끝난 줄에 퍼뜨리지 않고 '입금 예정(지급일 미정)'으로 (2026-11-17, R231)
- 결정: 위탁자 정산서 '관리 상품 입금 내역'에서 ① 지급이 끝난 줄은 그 줄 실제 관리 정산금액만 적는다(예상분 배율 적용 안 함 · 쿠팡 줄 값 우선 D-279). ② 아직 지급 줄·gen 이 없는 예상 관리 정산 잔액은 따로 '입금 예정(지급일 미정)' 줄로 둔다.
- 결정 경위: D-288 위임 · T-96 하위 세션 관찰(코드 안 고침).
- 근거(사실·원 단위 검산): `settlement_statement_deduct.py` 20~43줄 `status_split` 이 ②를 '있는 지급 줄 + gen' 무게로 나눠 미래 판매분이 끝난 줄에 같은 배율로 퍼짐 · aehee5505 배율 1.09506 · 퍼진 금액 110,288 = 10·11월 예상 관리 정산 944,426 − 그 기간 지급 줄 827,529 − gen 6,609 = 1쪽 G 1,014,939 − 계정 입금(295,502+609,149) · 결과 1쪽 입금 완료 327,962 > 통장 실제 295,502 · 관리 100% 달 차이 aehee5505 08 +10,471 · 09 +20,523 · gorocket23 +52·+69 · 계정 전체 지급 15칸은 0원(`D:\coupang-analytics\output\_검증_261117_샘플산식\2차\샘플검증2_보고.md` '1절 결과' · `샘플검증2_1번_정산서대조.csv`).
- 버린 대안: 지금 방식(입금 완료가 통장 실제보다 커짐 = 차이).
- 남는 위험: 구현 뒤 aehee5505·gorocket23 관리 100% 달 차이 0 확인 필요 · bws247 9월 관리 줄 합 10,274 > 월별 6,890 · k2min1201 검산 ✘④ · WBpeak 는 미조사.
- 영향 범위: 정산 코드만(D-233) · 구현 = T-99 · CURRENT_RULES 12절.
- 상태: ACTIVE

### D-295 [SETTLE_FORMULA_CONFIRMED] 윙 환불 수수료(11-3) R11 · 반품 배송비 수수료(12-2) R12 · 반출비 무료 순서(48) R48 = 파일 행 순서 + 줄 최종 0 아래 금지 (2026-11-17, R231)
- 결정: ① 11-3(R11) = 같은 주문 배송비 −X/+X 맞바꿈은 0 · 전량 환불 = −원 판매 줄 수수료 · 그 밖 = 레인 E 식. ② 12-2(R12) = 어긋나던 wellbing1107 맞바꿈 쌍을 한 쌍으로 처리(233/233). ③ 48(R48) = 반출 무료 수량 순서 = 발생일 → 파일 기간 → 행(D-293 ② 를 반출비로 넓힘) · 줄 최종비용 = max(0, …). ④ 3-2·4-2·12-2 는 지금 식으로 차이 0 확인(산식 변경 없음 · 4-2 쿠팡 귀책 = 2×편도 5/5).
- 결정 경위: D-288 위임 · T-95 이어가기 세션 후보(6-6절)를 통제 세션이 확정.
- 근거: `D:\coupang-analytics\output\_검증_261117_묶음D_반품끝전\T95_보고.md` 6절 — 11-3 환불 77줄 레인 E 식 74 → R11 76 · 계정×달 40칸 중 남은 1칸 = ljung0622 2026-05 +1원(원 판매 줄 자체가 윙 판매 식과 2원 다름 · 11-3 밖 원인) · 12-2 233/233 · 계정×달 71칸 0 · 48 레인 B 13칸 −15,600 → 8칸 +2,700, 남은 칸 = 자료 없음(앞쪽 주 파일 6칸 −11,700) · A=0 원문 2칸 +14,400(미확인 원문) · oopean 은 T-77 새 파일 더하면 0 · 스크립트 `s7`~`s10`.
- 버린 대안: 레인 E 식 그대로(11-3 74/77 · 12-2 중복 수) · 반출 무료를 비용 순서로 씀.
- 남는 위험(사실): ljung0622 2026-05 +1원(윙 판매 식 2원 차이 — 별도 조사) · 48 A=0 원문 2칸 +14,400 · 4-2 표본 5건뿐(쿠팡 귀책 반품이 더 없음).
- 영향 범위: 정산 산식 엑셀 '정산항목_산식' 3-2·4-2·11-3·12-2·48 · T-38 · CURRENT_RULES 12절.
- 상태: ACTIVE

### D-296 [SETTLE_SOURCE_DAILY_FETCH] T-78 소유자 확인 4건 — Q1 앱이 윙 비용/수수료 화면(fee-details) 조작 + 화면이 받은 응답 기록 허용 · Q2 첫 라이브 시험 허용 · Q8 상품 수량·categoryId 보관 = 레인 A 별도 작업 · Q10 도움말 FAQ 새 주소 호출 보류 (2026-11-17, R231)
- 결정: ① Q1 = 앱이 로그인한 정산 세션에서 fee-details 화면의 탭·카테고리만 바꾸고(보기 전환 · 동의·신청·저장·설정 버튼 금지) 화면이 스스로 받은 응답을 `page.expect_response` 로 기록 — 페이지 안 직접 호출(fetch·javascript)은 하지 않음. ② Q2 = 첫 라이브 시험 = 사무실·소유자 있을 때 sg0141n 1계정 1회 · 카테고리 3개만 · 차단 신호 1번이라도 나오면 M-A 전체 보류 후 보고. ③ Q8 = 상품 '상품 정보 수량'·categoryId 날짜별 보관은 정산 작업(D-233)에서 하지 않고 레인 A(상품 수집) 별도 작업으로 · 그 전까지 50행 '받을 수 없음'. ④ Q10 = 도움말 FAQ 새 주소 GET 보류 · 대신 주 1회 하위 세션이 화면으로 수정일 확인.
- 결정 경위(소유자 원문 2026-11-17): "Q1 Q2 허용, Q8 분리, Q10 보류" — T-78 설계서 7절 추천안 그대로.
- 근거: `D:\coupang-analytics\docs\plans\T78-source-list-daily-fetch-design-2026-11-17.md` 7절 · D-274(할인표 유료 줄 ±1원 → 표 값 정확해야 43·44 차이 0) · 11-17 같은 화면 직접 호출 1회 차단 사례(→ 직접 호출 대신 화면 응답 기록).
- 버린 대안: 화면 글자만 읽기(칸 해석 오류 · 보조로만) · Q1 거절 시 하위 세션 주 1회 화면 확인(설계서 7절 대안).
- 영향 범위: T-78 단계 S4(fee-details) 착수 가능 · D-291 ① 의 '소유자 확인 전' 단서 해소 · 레인 A 새 할 일 · CURRENT_RULES 12절.
- 상태: ACTIVE

### D-297 [SETTLE_FORMULA_CONFIRMED] 지급 흐름·회차 묶음 B — 42 RG 줄 최종액 공식 · 신규-20 재고 손실 보상 회차 · 신규-18 100% 줄 뜻 확정 · 51·52·신규-08~10·신규-21·21·22·41 = 쿠팡 원문 값 사용 · 31 = 해당 없음 (2026-11-17, R231)
- 결정: ① 42 로켓그로스 줄 최종액 = totalPayable − 추가 공제 − 물류비 + 재고 손실 보상 + 판매조정. ② 신규-20 재고 손실 보상 = 기간에 그 달 말일이 든 줄에만 붙음. ③ 신규-18 100% 줄 뜻 = 윙 = 보류 해제 줄 + 월정산 달 줄 · 로켓그로스 = 보상 단독 줄 + 월정산 달 줄(`payout.py` 주석 정정 대상). ④ 51 미납 CFS · 52 과거 CFS · 신규-08·신규-09 환불·취소 차감 회차 · 신규-10 윙 매출 인식 · 신규-21 밀크런 공제 회차 · 21 보류 · 22 보류해제 · 41 마이너스 공제·판매조정 = 확정 줄은 쿠팡 원문 칸 값 그대로(줄 공식이 원 단위 0이라 정산금액 차이 0) · 예정 줄은 D-279. ⑤ 31 'B 주기 추가정산' = 자료에 줄 없음 → 해당 없음(생기면 경고 · 22·월정산으로 흡수).
- 결정 경위: D-288 위임 · 묶음 B 하위 세션(local_e2335c1e) 후보를 통제 세션이 확정.
- 근거: `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\미확정_병렬\B\B_보고.md`·`B_판정표.csv` — 로켓그로스 줄 공식 1,999/1,999회차 원 단위 0(`R1_RG줄공식.csv`) · 윙 줄 공식 1,227/1,229 · 신규-20 196/196(70% 154·100% 42 · `R4_재고손실보상_회차.csv`) · 신규-18 윙 보류 해제 144줄 + 월정산 15/15 · RG 보상 단독 27 + 월정산 15(`R6_*`) · 장부 시험 DB 40계정(Difpick 제외).
- 버린 대안: 엑셀 신규-21 문구 '밀크런은 70%에서, 모자라면 같은 주 30%'(30% 줄 87 중 68 반례) · 51·52 1:1 짝 공식(176/339 · 나눠 공제) · 41 KB '마이너스 공제+판매조정 = 0'(계정 합 6/20).
- 남는 위험(사실): 윙 줄 2/1,229 불일치 · 신규-17(예정 금액 확정 시점 · 어긋남 10건 절댓값 198,830)·29(추가지급 2건 · 승인일 칸 없음)·신규-22(리뷰 공제 표본 4줄) = 자료 필요 → T-93·T-80 · 남은 검산 R7·R8 → T-101.
- 영향 범위: 산식 엑셀 '정산항목_산식' · T-38 · `payout.py` 주석 · CURRENT_RULES 12절.
- 상태: ACTIVE (부분 SUPERSEDED by D-315 — ⑤ 31 = 29 추가지급과 같은 줄)

### D-298 [SETTLE_FORMULA_CONFIRMED] 묶음 A — 75 세이버 구독료 = 월 108,900 정액·일할 없음·달 마지막 주 70% 줄 공제 · 23 매출내역 F = 회차 '차감' 줄 합(따로 빼지 않음) · 24 3PM_매출채권·45 보관비 원문 A=0 = 쿠팡 원문 값 · 43·44·76-2 무료 0원 줄 = 미확정(지금 규칙 유지) (2026-11-17, R231)
- 결정: ① 75 로켓그로스 세이버 구독료 = 월 108,900원 정액 · 일할 없음 · 그 달 마지막 주 70% 줄에서 공제(모자라면 다음 회차로 나눠 공제). ② 23 매출내역 F(정산차감) = 그 달 판매 기간 윙 회차 '차감 *' 줄 합과 같은 돈 → 정산서에서 F 를 따로 빼지 않음(이중 차감 금지). ③ 24 3PM_매출채권(앞 회차 윙 음수 최종지급 회수) · 45 보관비 원문 A=0 칸 = 쿠팡 원문 값 그대로. ④ 43·44·76-2 입출고비·배송비 무료 0원 줄 = 규칙 미확정 → 지금 규칙 유지 · 쿠팡 줄 값 우선(D-279) · 예상값 '미확정' 표시.
- 결정 경위: D-288 위임 · 묶음 A 하위 세션(local_14c0eed8) 후보(보고서 4절)를 통제 세션이 확정.
- 근거: `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\미확정_병렬\A\A_보고.md` — 75 = 5계정 64줄 합 5,989,500 = 108,900×55 · 일할 0건(`a5_세이버구독료_계정.csv`) · 23 = 248칸 중 222칸 0(남은 26 = 미정산 회차 22 · ski1121 채권추심 달 경계 ±11,953,075 두 달 합 0 · ski1121 +3,974 · seankim137 2026-09 +230,722 · `a4_매출내역F_대조.csv`) · 24 = guarisen2024 52,343 · gyi0101 24,629 · ski1121 11,160 금액 일치(`a3_3PM_채권대조.csv`) · 43·44 = 0원 줄 15,076줄 · 규칙 R-44 넣어도 1,105줄(입출고 1,362,465 · 배송 2,096,725) 남음(`a9_신상품무료_규칙시험.csv`).
- 버린 대안: F 를 따로 공제(이중 차감) · 무료 0원 = 세이버 가입 탓(보관비 세이버 옵션과 겹침 0줄 → 아님) · R-44 확정(차이 남음).
- 남는 위험(사실): 23 seankim137 2026-09 +230,722·ski1121 +3,974 미설명 · 24 ljung0622 42,800·gbseller808 33,798 미설명 · 43·44 무료 대상·시작일 = 로그인 자료 필요(윙 무료 혜택·알림·공지 14계정) · 46·47·4·45·39-2·11-2·44 묶음 = 자료 필요(보고서 3절).
- 영향 범위: 산식 엑셀 · T-38 · T-81(무료 0원 전제) · CURRENT_RULES 12절.
- 상태: ACTIVE (부분 SUPERSEDED by D-318 — ④ RG 무료 0원 줄 예상 규칙)

### D-299 [SETTLE_FORMULA_CONFIRMED] 묶음 D — 53 CFS 비용 조정 = 다른 금액 안에 이미 들어감(따로 더하지 않음) · 48 원문 A=0·신규-06 부분 취소 VAT·59·60 밀크런 = 쿠팡 원문 값 · 54·56·57·58 = 해당 없음(감지만) · 17·신규-19 이용료 = 미확정(쿠팡 줄 값) (2026-11-17, R231)
- 결정: ① 53 CFS 비용 조정(totalCfsFeeAdjustment) = 그 인식일 비용 리포트 순액(정산+정산취소)×1.1 — 마이너스 물류비 날을 지급 줄에서 되돌리고 따로 환급하는 돈이라 상품 공제에 더하지 않음(이중 반영 금지). ② 48 반출비 원문 A=0 줄 · 신규-06 로켓그로스 부분 취소 VAT 끝전 · 59 밀크런 · 60 밀크런 조정액·추가금 = 쿠팡 원문 값 그대로(밀크런 공제 = 지급 줄 값 + 밀크런 엑셀 줄 배분 · 지금 코드). ③ 54 컨테이너 하차비 · 56 회송·폐기 · 57 미반출 정기 폐기 · 58 매뉴얼 처리비 = 받은 자료에 발생 0 → 해당 없음(생기면 경고). ④ 17·신규-19 판매자서비스이용료 = 차이 0 규칙 없음 → 쿠팡 줄 값 유지(D-279·D-261) · 회차 이월 모형은 참고.
- 결정 경위: D-288 위임 · 묶음 D 하위 세션(local_de14be6b) 후보를 통제 세션이 확정.
- 근거: `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\미확정_병렬\D\D_보고.md` — 53 = 43줄·13계정 +369,780 · 상세 147칸 중 119칸 0원·13칸 ±1원 · 남은 15칸 = 자료 없음 11 + 다름 4 · 54 = 지급 json 2,131줄·36계정 하차비 전부 0 · 부가서비스비 리포트 299줄 = 바코드 2종 · 밀크런 robincohs 11221974 31,350 = 원문 28,500 + 세액 2,850(관리 몫 0) · 밀크런 엑셀 이 PC 546개·48계정(산식 엑셀 '이 PC에 없음' 정정) · 이용료 누적 44/49 계정 · 회차 이월 모형 101/155 · guarisen2024 9월 −110,000 = 7월 줄 남는 돈 부족으로 밀림(모형 일치).
- 버린 대안: 53 을 상품 공제에 더함(이중 반영) · 밀크런 같은 달 대조(43/177 · 공제 달이 엑셀 달과 0~1달 어긋남) · 이용료 이월 모형 확정(101/155).
- 남는 위험(사실): 53 다름 4칸(hk66597582 2026-02-27 배송비 다시 매김 등) · 밀크런 엑셀 합 24,006,043 vs 공제 합 35,011,900(범위 다름 · 범위 맞춘 대조 인계 = 보고서 6절) · 이용료 hk66597582 가전 500만·rladygks0221·dalbong1849 기준 칸 · 밀크런 구간 표(T-94) · 부분 취소 정산 상세 1건(신규-06 규칙).
- 영향 범위: 산식 엑셀(밀크런 자료 위치 정정 포함) · T-38 · CURRENT_RULES 12절.
- 상태: ACTIVE

### D-300 [SETTLE_FORMULA_CONFIRMED] 묶음 F — 빠른정산·대출·채권추심·MCA·체크카드·이월 공제·CFS 이월 = 쿠팡 원문 값 · 하나은행 인출 수수료·매출(위수탁) 세금계산서 = 해당 없음 · 매입·3P_영중소 세금계산서·부가세 신고 = 정산금액 밖(참고) (2026-11-17, R231)
- 결정: ① 18 빠른정산 계좌인출액 · 19 빠른정산 사용액 · 25 채권추심 · 26 성장 대출 · 80 MCA 상환 · 81 체크카드 대금 상계 · 82 이월 공제(CarryOver) · 83 빠른정산 상환 = 회차 금액은 쿠팡 원문 칸 값 그대로(로켓그로스 2,131줄 전부: 최종 = 지급가능 − 추가공제 − FinalCfs + 보상 + 판매조정 원 단위 · 윙 1,298줄 공제합 = 차감사유합 → 원문 값이면 회차 최종액 차이 0). 82 예정 추정 규칙(R-CO 88/113)은 확정 안 함 — 예정값은 경고값(D-279). ② 20 하나은행 인출 수수료 · 86 매출(위수탁) 세금계산서 = 발생 0 → 해당 없음(생기면 경고). ③ 84 매입 · 85 3P_영중소 세금계산서 · 87 부가세 신고 = 정산금액 밖 — 참고만 · 85 는 32 우대수수료 환급 판정 근거로 쓰지 않음(월 짝 5/204).
- 미결(이 D 로 정하지 않음): 위탁자 정산서에서 19 빠른정산 사용액 · 26·80 대출 상환 · 81 체크카드를 '이미 받은 돈(±0)'으로 볼지 '공제'로 볼지 — 그 돈을 누가 받았는지(위탁자 본인 신청·수령 여부) 사실 확인이 먼저(소유자 · 계약 조건 범위 D-288 밖). 지금 코드 = 19 공제 844,974 · 26·80 공제 8,920,540 · 81 기타 공제 82,870.
- 결정 경위: D-288 위임 · 묶음 F 하위 세션(local_48d18fa2) 판정을 통제 세션이 확정.
- 근거: `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\미확정_병렬\F\F_보고.md`(f01~f25) — 발생 금액 18 윙 296줄 278,028,560(7계정) · 83 RG 378줄 908,021,922 · 19 seankim137 844,974 · 25 ski1121 11,953,075(장부 보류 채권압류 합과 같음) · 26 tellace83 798,784 · 80 tellace83 8,121,756 · 81 seankim137 82,870 · 82 RG 113줄 4,858,789 · 20·86 발생 0.
- 남는 위험: 35~38 로켓그로스 판매액·쿠팡지원할인·쿠폰 줄 검산 미완(인계 = 보고서 · `f18_대기후실행.sh` → `f25_RG합_지급대조.py`).
- 영향 범위: 산식 엑셀 · T-38 · CURRENT_RULES 12절.
- 상태: ACTIVE (19·26·80·81 위탁자 정산서 처리 = D-307)

### D-301 [CONSIGNOR_STATEMENT_AD_DEDUCTION_PRECISION] 묶음 C 광고 — 신규-02 추가 공제 구성 · 73 광고 세금계산서 = 광고 json 달 합 · 67·69 청구금액 = AfterCap − 지원금 − 청구조정 확정 · 62·70 대조 = 같은 지급일 줄 합 · 64·65·66·신규-01 = 원문 값 · 63·71·72 = 해당 없음 · 68 지원금 줄 배정·61 남은 4계정 = 미확정 · 광고 대조는 원천 파일로 (2026-11-17, R231)
- 결정: ① 신규-02 로켓그로스 추가 공제 = 광고 + 밀크런 + 음수 + 라이브 + 직불 + AR + MCA + BI + 구독료 + PostPurchase. ② 73 광고 세금계산서 = 광고 json 달 합. ③ 67·69 광고 청구금액(billable) = 일예산 초과 반영 후 금액(AfterCap) − 광고 지원금 − 청구 조정. ④ 62·70 로켓그로스 광고 공제 대조 = 같은 지급일 줄 합으로 판정(9/30 하루 광고가 10/1~4 줄로 옮겨 가는 월 경계 이동 포함) · 지급가능 0 이라 못 뺀 금액 = 미납(광고센터 미납 화면 값). ⑤ 64·65·66 캠페인 유형 · 신규-01 상품별 광고비 배분 = 쿠팡 원문 값. ⑥ 63 브랜드 광고 · 71 리테일 광고(ADB · 정산서 밖) · 72 파트너 캠페인 = 해당 없음(생기면 경고). ⑦ 68 지원금이 어느 줄에 배정되는지 · 61 윙 남은 4계정 = 미확정(D-289 유지). ⑧ 광고 공제 대조는 장부 시험 DB 가 아니라 원천 파일로(장부 시험 DB 에 Difpick·91white·WBpeak RG 광고 공제 빠짐).
- 결정 경위: D-288 위임 · 묶음 C 하위 세션(local_9bc65284) 후보(보고서 4절)를 통제 세션이 확정.
- 근거: `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\미확정_병렬\C\C_보고.md`(c1~c9) — 신규-02 1,282/1,282줄 원 단위 · 73 RG 146/146 · 3P 101/101 · 67·69 16,112/16,132줄(예외 20 = ski1121 원문 칸 누락) · 62/70 RG 28계정 중 17 누적 0 + 월 경계 이동 5계정(gyi0101 38,146 · robincohs 44,095 · sg0141n 13,831 · ljung0622 22,131 · oopean 49,604)은 같은 지급일 줄 합 0 · 미납 ski1121 −745,821 · theirumlab −6,986 · k2min1201 −554 · Difpick 윙 광고 8달 전부 원 단위 0(T-90 −5,764,567 = 장부 DB `--exclude` 탓 · T90 md 7절) · 61 윙 23계정 중 19 누적 0.
- 버린 대안: 달 단위 대조만(월 경계 이동을 차이로 봄) · 장부 시험 DB 로 광고 대조(빠진 계정).
- 남는 위험(사실): 61 ygkim1 +245,876 · seankim137 −47,420 · WBpeak +1,802 · 91white −1,108(미납) · 필요 자료 = 광고 json(ygkim1·WBpeak 2025-10 이전 · seankim137 2026-05~07) · 일별 광고비 정산 보고서(Difpick 2025-11~2026-08 · tellace83·nicoable 2026-09 · guarisen2024 2026-05) · 광고센터 미납 화면(ski1121·theirumlab·k2min1201·91white) — 소유자 로그인.
- 영향 범위: 산식 엑셀 · T-38 · T-90 · T-92 · CURRENT_RULES 12절.
- 상태: ACTIVE

### D-302 [SETTLE_FORMULA_CONFIRMED] 묶음 E 윙 판매·쿠폰·사건형 — 15 윙 정산대상액 식 · 1 판매액 · 2 배송비 · 5·6 판매자 쿠폰 A·B · 8 쿠팡 부담 쿠폰 = 정산 영향 0 · 77 라이브 수수료 · 79 리뷰 이벤트 1건 금액 확정 · 27·28·32·74 = 원문 값 · 7·9·10·13·14·30·34·78 = 해당 없음 (2026-11-17, R231)
- 결정: ① 15 윙 정산대상액 = 판매액 + 배송비 − 환불 − 반품배송비(원문 음수) − 판매자 쿠폰(A+B) − (판매수수료 − 마이샵 할인). ② 1 판매액 · 2 배송비 · 5·6 판매자 즉시할인·다운로드 쿠폰 = 원문 순액. ③ 8 쿠팡 부담 쿠폰 = 정산금액 영향 0(쿠팡이 부담 · 엑셀의 '더함' 문구 정정). ④ 77 쿠팡 라이브 플랫폼 수수료 = 사사오입(netGmv × 요율) 합 + 사사오입 VAT 10% · 공제 회차는 미확정(쿠팡 줄 값). ⑤ 79 리뷰 이벤트(체험단) 1건 = 지원금 2,000 + 사사오입(서비스료 200 × 1.1) = 2,220원 · 공제 회차 미확정(쿠팡 줄 값). ⑥ 27 고객보상 · 28 윙 라이브 커머스 · 32 우대수수료 환급(별도 입금) · 74 비즈니스 인사이트(예상 = 직전 정상 달 정액) = 쿠팡 원문 값. ⑦ 7 무료노출 할인 · 9 마이샵 할인 칸 · 10 멤버십·카드 할인 · 13 서비스이용료 소급 · 14 프로모션 추가 수수료 · 30 기타 수수료 칸 · 34 한진 택배비 · 78 라이브 크리에이터 수수료 = 발생 0 → 해당 없음(생기면 경고) · 33 판매자 귀책 반품 = 정산 줄 0 · 신규-05 = D-293 과 같은 줄 · 신규-07 교환 = 자료 없음 → T-80 뒤(D-291 ⑧).
- 결정 경위: D-288 위임 · 묶음 E 하위 세션(local_01b91f3e) 판정을 통제 세션이 확정.
- 근거: `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\미확정_병렬\E\E_보고.md`(e_s1~e_s5) — 15 = 1,298/1,298회차 · 줄 식 107,730/107,732(남은 2줄 = wellbing1107 맞바꿈 ±14,000 합 0) · 1 = 379/379 · 2 = 394/395 · 5·6 = 394/395·395/395(1회차 = roum0502 보류 해제 회차) · 8 = 주문별매출 16,031줄 · cfc 779줄 일치 · 77 = 299줄 · 지급 지난 28/28달 원 단위 · 79 = 91white 11,100 · tellace83 2,220 계정 합 일치 · 32 = 158,043줄 12,465,667 · 74 = 55줄 8,445,555.
- 버린 대안: 쿠팡 부담 쿠폰을 정산금액에 더함(대조 불일치).
- 남는 위험(사실): RG '리뷰-이벤트-비용' 리포트 3파일(91white·tellace83·sg0141n)이 머리줄만·줄 0인데 같은 회차 PostPurchase 공제 있음 → 앱 받기 결함 의심(D-184 '줄 0 = 0원' 판정과 충돌) · freewin7777 라이브 2026-02 json 비어 있는데 공제 347 · 74 첫 달·플랜 변경 달(T-80) · 77·79 공제 회차 규칙.
- 영향 범위: 산식 엑셀 · T-38 · T-82(받기 결함) · CURRENT_RULES 12절.
- 상태: ACTIVE

### D-303 [SETTLE_FORMULA_CONFIRMED] 로켓그로스 판매 35~38 — 판매액 = A×B · 매출금액 = 판매액 − C · 쿠팡지원할인 C = 쿠팡 부담(판매자 몫에서 안 빠짐) · 판매자 즉시할인 D·다운로드 E 합 = 지급 줄 칸과 같음 (2026-11-17, R231)
- 결정: ① 35 로켓그로스 판매액 = A(판매가) × B(수량) · 매출금액 = 판매액 − C. ② 36 쿠팡지원할인 C = 쿠팡 부담 — 그 줄 정산대상액 = 판매액 − (D+E) − 판매수수료 − VAT 로 C 는 판매자 몫에서 빠지지 않음. ③ 37 ΣD = totalSellerFundedInstantDiscount · 38 ΣE = totalSellerFundedDownloadDiscount · Σ(D+E) = totalSellerDiscount · Σ(판매수수료+VAT) = totalTakeRateAmountWithVat.
- 결정 경위: D-288 위임 · 묶음 F 하위 세션(local_48d18fa2) 후속 검산을 통제 세션이 확정(T-103 끝).
- 근거: `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\미확정_병렬\F\F_보고.md` 1·5절 · `F_35_38_RG파일별합.csv` · `F_35_38_회차대조.csv` — 로켓그로스 판매수수료 파일 1,049개 · 282,635줄: 35 = 282,635/282,635 · 지급내역 totalSales+totalRefunded = 파일 Σ판매액 1,940/1,940회차 · 36 = C 7,303줄 34,650,567(31계정) 7,303/7,303 · 37·38 = 1,940/1,940 · 판매수수료 파일 없는 지급 줄 191 = 판매 없는 회차.
- 버린 대안: C 를 판매자 공제로 봄(줄 검산 불일치).
- 영향 범위: 산식 엑셀 35~38 · T-38 · CURRENT_RULES 12절.
- 상태: ACTIVE

### D-304 [SETTLE_FORMULA_CONFIRMED] 24 3PM_매출채권 = 윙 음수 최종 회차를 같은 항목으로 되돌려 넣고 3PM 회수 줄은 공제(안 C) — 정산금액 = Σmax(회차 최종액, 0) = 쿠팡 실지급 (2026-11-17, R232)
- 결정: 윙 회차 최종액(paidAmount − totalDeductionAmount)이 음수면 그 음수만큼 '3PM_매출채권' 항목에 되돌려 넣고(공제 −|최종액|), 뒤 회차 3PM 회수 줄은 같은 항목 이름으로 공제한다. 같은 항목이라 관리 비율도 같아 짝이 있으면 서로 지워진다. 정산서 표시 = D-298 ③ 원문 값 + '이월' 문구.
- 결정 경위: D-288 위임 · T-104 ① · 묶음 G 하위 세션(local_6c7c3fc6) 후보를 통제 세션이 확정.
- 근거: `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\미확정_병렬\G\G_보고.md` ①절(g1·g6·g7) — 현행(`settlement_statement_account.py:92-102` 윙 차감 사유 전부 공제 · 3PM 전용 처리 0건) = 이중 차감(guarisen2024 −52,343 · gyi0101 −24,629 · ski1121 −11,160) · 윙 음수 최종 회차 있는 계정 5개 전부 안 C − 현금 = 0 · 안 C 는 짝 찾기 없이 식으로 항상 현금과 같음.
- 버린 대안: 안 A 현행(이중 차감) · 안 B 3PM 줄만 뺌(짝 없는 줄에서 틀림 — ljung0622 +42,800 · gbseller808 +33,798 · ski1121 −66,112).
- 영향 범위: 정산 코드(T-38 · `settlement_statement_account.py` 윙 분기) · 지금 위탁 정산서 대상 영향 = ljung0622(현행 3PM 관리 공제 54,026 → 약 +5,077) · 남은 76,598(원인 채권이 장부에 없음) = 로그인 자료(T-39·T-5) · CURRENT_RULES 12절.
- 상태: ACTIVE (부분 SUPERSEDED by D-319 — 적용 범위 = 지급 완료 회차만)

### D-305 [CONSIGNOR_STATEMENT_NEW_ITEM_WARNING] 25 채권추심 · 19 빠른정산 · 81 체크카드 · 26/80 대출·MCA = 감지 목록 + 처리 판정표(파일)에 없는 계정×항목이 생기면 '확인 필요' 줄·경고 · 80·81 은 '기타 공제'에서 따로 줄로 (2026-11-17, R232)
- 결정: 위 항목(윙 차감 사유 3종 + 로켓그로스 80·81 칸)을 감지 목록으로 두고, 처리 판정표(근거 남긴 파일 · D-229)에 없는 계정×항목이 처음 나오면 그 금액을 '확인 필요' 줄로 두고 불일치 사유·경고를 남긴다. 80 MCA·81 체크카드는 '기타 공제'에 이름 없이 섞지 않고 각각 줄로 보인다. 금액 처리(공제인지 ±0인지) = T-102 소유자 사실 확인 뒤(D-300 미결 그대로).
- 결정 경위: D-288 위임 · T-104 ⑨ · 묶음 G 후보 W1.
- 근거: `G_보고.md` ⑨절 — 지금 각 1계정에만 있음(seankim137 19 · tellace83 26 등) · 80·81 이 '기타 공제'에 섞여 있고 처음 보는 사유를 잡는 감지기가 코드에 없음.
- 버린 대안: 경고 없이 지금처럼 공제(새 위탁 계정에서 돈 주인이 다르면 정산금액이 바로 틀림).
- 영향 범위: 정산 코드(T-38) · 판정표 파일 위치는 구현 때 · CURRENT_RULES 12절.
- 상태: ACTIVE

### D-306 [CONSIGNOR_STATEMENT_RULES] 상품 못 찾은 윙 배송비(T-98) = 반품 조회로 상품 먼저 찾고 · 그래도 못 찾으면 '상품 확인 전 배송비(계정 집계)' 줄로 넣고 다음 정산서에서 나눔(D-236 · D-241 ② 방식) (2026-11-17, R232)
- 결정: 정산 확정 줄 중 상품 없는 윙 배송비는 ① 반품 조회 자료(D-269)로 같은 주문 상품을 찾아 관리 여부를 정하고, ② 못 찾으면 관리 정산금 비율로 나누지 않고 '상품 확인 전 배송비(계정 집계)' 줄로 정산서에 넣은 뒤 상품이 확인되는 다음 정산서에서 나눈다.
- 결정 경위: D-288 위임 · T-98 · 묶음 G 후보 안 3.
- 근거: `G_보고.md` T-98절 — 정산 확정 줄 중 상품 못 찾은 윙 배송비 = 40줄 232,080원 전부 gbseller808(반품 조회 0건 · 판정 대기라 지금 정산서 없음) · 11-03 wavetech 6,769원은 반품 조회로 관리 상품을 찾음(현행 비율 1 = 차이 0 · D-146 '금액 밖' = −6,769) · 지금 정산서 대상 계정 영향 0.
- 버린 대안: 현행 확정 정산금 관리 비율로 나눔(`settlement_statement_account.py:301-304` · 상품 근거 없는 배분) · D-146 금액 밖(상품을 찾을 수 있는 줄까지 빠져 −6,769).
- 영향 범위: 정산 코드(T-38) · 코드 주석 'D-162'는 번호 오기(구현 때 정정) · CURRENT_RULES 12절.
- 상태: ACTIVE (부분 SUPERSEDED by D-393 — 반품 조회로도 상품 못 찾은 윙 배송비 나눔 = 같은 달 윙 관리 비율)

### D-307 [CONSIGNOR_STATEMENT_RULES] 위탁자 정산서 처리 — 19 빠른정산 사용액 = 미리 당겨 받은 돈(18 계좌인출액과 같은 ±0 · 입금 완료) · 26 성장 대출·80 MCA 상환 · 81 체크카드 대금 상계 = 정산에서 차감(공제) (2026-11-17, R232)
- 결정(소유자 2026-11-17 원문 "빠른정산 사용액 : 미리 당겨 받은 돈, 성장 대출 · MCA 상환 : 갚는것, 정산에서 차감.체크카드 대금 상계 : 정산에서 차감." · "내 판단이 맞는지 검토후 반영해."): ① 19 빠른정산 사용액은 공제가 아니라 이미 받은 돈 — D-126 ④ 빠른정산 두 줄('빠른정산 상환 −Z' + '먼저 받은 돈 +Z')에 18 과 함께 넣는다(G 합계 불변). ② 26 쿠팡 판매자 성장 대출 · 80 판매자 자금(MCA) 상환 · 81 체크카드 대금 상계는 정산에서 차감하는 공제로 둔다(D-305 대로 각각 따로 줄 · 금액 = 쿠팡 원문 값 D-300).
- 결정 경위: T-102 소유자 사실 확인 → 통제 세션 검토(D-288 · 돈 처리라 소유자 판단을 그대로 채택).
- 검토 근거: `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\미확정_병렬\F\F_보고.md` 4절 · `F_18_19_83_빠른정산_줄.csv` — seankim137 19(3줄 844,974)는 같은 윙 줄에서 18 과 금액이 다르고(예: 2026-08-24 줄 사용액 491,416 + 계좌인출액 254,512 + 광고 424,164 = 지급가능 1,170,092 · 최종 0) 둘을 다 ±0 으로 둬도 겹쳐 세지 않음 → 소유자 사실('미리 당겨 받은 돈')과 자료가 어긋나지 않음. 26·80(tellace83 8,920,540 · 예정 910,774) · 81(seankim137 82,870)은 쿠팡이 지급 줄에서 실제로 뺀 돈이라 공제로 두면 정산금액 = 쿠팡 실지급(차이 0).
- 검토 메모(사실): 공제로 두면 대출·체크카드 금액도 계약 비율로 나뉘어 우리 몫이 그 비율만큼(7:3 계약이면 30%) 함께 줄어든다 — 소유자 결정('정산에서 차감')으로 채택.
- 버린 대안: 19 를 공제로 둠(지금 코드 · 이미 받은 돈을 비용으로 빼 위탁자 몫이 844,974 의 계약 비율만큼 적게 나옴) · 26·80·81 을 ±0 또는 위탁자 개인 공제 별도 줄(소유자 '정산에서 차감').
- 영향 범위: 정산 코드(T-38 · `settlement_statement_account.py` 윙 차감 사유 분기 — '빠른정산 사용액'을 FAST 로) · D-300 상태 줄 · D-305 금액 처리 확정 · CURRENT_RULES 12절.
- 상태: ACTIVE (부분 SUPERSEDED by D-312 — ② 26·80·81 관리 몫 배정 = 위탁자 본인 차감 · 관리 몫 0)

### D-308 [SETTLE_FORMULA_CONFIRMED] 묶음 H 검산 — 윙 줄 최종액 3가지 식(추가지급 줄 포함 1,298/1,298) · 9/30 광고 = 10/1~4 줄 이동 사실 확정 · 보상 리포트 달 = 붙는 줄의 달 · 윙 환불 = 환불 인식일 회차 · CFS최종 검산식 · RG 70% 예정 끝전 = 미확정 (2026-11-18, R233)
- 결정: ① 윙 지급 줄 검산식 = 일반 줄 `paidAmount − totalDeductionAmount` · 보류 해제 줄(정산대상 0 · pending > 0) `pendingAmount − totalDeductionAmount` · 추가지급 줄(정산대상·paid·pending 0 · 기간 = 정산일 하루 · 같은 날 additional 짝) = 추가지급 `finalRewardAmount`. 추가지급 줄은 보류 해제와 따로 표시한다(장부 적재가 지금 `release=1` 로 섞음 → 코드 보완 = T-105). ② 9/30 하루 RG 광고가 10/1~4 줄(같은 지급일)에 들어가는 이동은 사실로 확정 · RG 광고 대조·예상 = 같은 지급일 반쪽 두 줄 합(D-301 그대로) · `adSalesOffsetYearMonthBreakdown` 달 칸으로 이동분을 가르지 않음 · 이동이 언제 생기는지(9/30 외)는 미확정. ③ 신규-20 재고 손실 보상 = 보상 리포트 달이 붙는 줄의 달(전월분 아님 · 사건 발생일은 앞 달일 수 있음) — D-297 ② 보충. ④ 신규-08 윙 환불 차감 = 환불 인식일이 든 회차 정산대상에서 뺌(원 판매 회차 아님) · 신규-10 윙 확정 줄 = targetAmount. ⑤ RG 정산서 검산식 = `CFS최종 = 물류 9칸(보관·입출고·입고·바코드·하차·반품등급·반품회수·V반품처리·V반품배송) + 미납 CFS + 과거 CFS + CFS 조정 − 이월` · 51·52 금액·회차 = 원문 값(D-297 ④ 그대로) · '1:1 짝' 규칙 버림. ⑥ RG 70%·30% 몫 확정 줄 = 쿠팡 원문 값 · 검산식 = '70% + 30% = 그 주 Σ정산금액'만 · 예정 70% 몫 끝전 규칙 = **미확정**(지금 `payout.py` 121~123줄 '줄마다 사사오입' 유지 · 더 맞는 규칙 찾으면 새 D항목).
- 결정 경위: D-288 위임 · 묶음 H 하위 세션(local_dd814319) 후보(`H_보고.md`)를 통제 세션이 확정(T-104 ②④⑩ · T-101 R7·R8·51·52).
- 근거: `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\미확정_병렬\H\H_보고.md` — ① 원천 윙 1,298줄 원 단위 0(DB 남은 2줄 = roum0502 2026-10-22 16,897 · freewin7777 2026-11-13 117,960 = 추가지급 json payDate·금액 2/2) · ② 6계정 10/1~4 줄 공제 = json 9/30~10/4 합 ±1원(gyi0101·robincohs·sg0141n·oopean·nicoable·ljung0622) · 9/28~30 줄엔 9/30 없음(6/6) · breakdown 칸은 9/30 몫도 '2026-10' 표기 · ③ 보상 파일 166개 합 = 그 줄 `totalCfsInventoryCompensationAmount` 166/166 · ④ Σ정산금액 = targetAmount 347/348(1 = 회차 없음) · 환불 82/82 = 환불 인식일 회차 · ⑤ RG 2,131/2,131 원 단위 · ⑥ 70%+30% = Σ정산 796/796 · 70% 몫 끝전 방식 최고 539/840(주문+옵션 묶음) · 지금 코드 방식 472/840 — 어느 방식도 차이 0 아님.
- ⑥ 지금 규칙 유지 이유(Claude 판단): 바꿀 후보(539/840)도 차이 0 이 아니고, 차이는 같은 주 70%↔30% 사이 몇 원 이동이라 주 합·정산금액 합은 변하지 않음(합 796/796) · 30% 줄이 오면 원문 값으로 바뀜(D-279). 코드 교체 = 회귀 위험 대비 얻는 것 없음.
- 버린 대안: 윙 남은 2줄 = 월정산 달 줄(월정산 15줄은 차 0) · breakdown 칸으로 이동분 분리 · 9/28~30 줄에 9/30 포함 · 51·52 1:1 짝 · 70% 기간 합×0.7 반올림(161/840) · 내림·올림(≤130).
- 남는 위험(사실): nicoable·tellace83·roum0502(윙 광고 섞임)·91white(한도 공제) 9/30 이동 원 단위 판정 불가 · 51·52 음수 누적 잔액 9계정 원인 미확인 · 22 해제액 ≠ 원 줄 96줄(보류목록 대조 전) · 41·신규-21 미실행 → T-101.
- 영향 범위: 산식 엑셀 '정산항목_산식'(다시 만들 때) · T-38 정산서 검산 · 장부 적재 분류(T-105) · `payout.py` 88줄 주석 정정(D-297 ③ · 제안 문구 = H_보고 3절 · T-105 와 함께) · CURRENT_RULES 12절.
- 상태: ACTIVE (부분 SUPERSEDED by D-315 — ⑥ RG 70% 끝전 = 줄마다 사사오입 확정 · 지금 코드)

### D-309 [CONSIGNOR_STATEMENT_RULES] 묶음 I — 광고 미납 = 공제는 쿠팡 줄 값 그대로 + 참고 줄(금액 영향 0) · 48 반출비 예정 문구 = '개별 면제 시 줄어들 수 있음' · 신규-06 예정 표시 없음 · 판매자서비스이용료 기준 = 구매확정 달 윙 판매액(쿠폰 전 · 일반 100만/가전 500만) · 53 CFS 조정 검산 = 매출인식일 묶음 (2026-11-18, R233)
- 결정: ① 광고 미납(지급 순서 누적으로 광고 청구 > 쿠팡 공제이고 그 뒤 줄 지급가능 ≤ 0 인 몫 · 아직 안 빠진 예정분과 구분) = 공제액은 쿠팡 줄 값 그대로(D-301 · 정산금액 차이 0) + 정산서에 참고 줄 '광고비 미납 X원 — 쿠팡 정산에서 빠지지 않은 광고비(광고센터 청구 여부 확인 필요)'(금액 0 · '추정' 낱말 안 씀 D-153). 지금 코드 `settlement_managed_alloc.py` `scoped()` 가 미납과 예정분을 같은 갈래로 비율만 줄이는 것은 T-38 구현 때 나눔. ② 48 반출비 예정 줄 문구 = '반출비(예정 · 규칙 계산) — 쿠팡 개별 면제 시 줄어들 수 있음'(끝전 문구와 묶지 않음) · 신규-06 부분 취소 VAT = 예정 표시 없음(취소 줄은 쿠팡 원문이 생겨야 있음 · 원문 값 D-299 ②). ③ 판매자서비스이용료 부과 기준 = 구매확정 달 · 윙 상품 판매액(판매자 할인쿠폰 빼기 전 · 배송비·로켓그로스 제외) · 일반 ≥ 100만 또는 가전/컴퓨터/디지털 ≥ 500만 = 55,000원 1회 — 지금 코드 `svc_charges`(D-161)와 같음 → 코드 변경 없음 · D-299 의 '이용료 기준 칸 미확정'을 닫음(회차 = 쿠팡 줄 값 그대로). ④ 53 CFS 비용 조정 검산 = 조정 상세 `recognitionDate` 날의 비용 리포트 **매출인식일** 순액 × 1.1(부호 그대로) · 금액 처리는 D-299 ①(더하지 않음) 그대로. ⑤ 47 freewin7777 +800 = D-293 ② 순서로 +1,200 해소 · 남은 −400 = 2025-11 월정산 파일 없음(받을 목록) — 새 규칙 없음.
- 결정 경위: D-288 위임 · 묶음 I 하위 세션(local_71c0acc6) 후보(`I_보고.md` 7절)를 통제 세션이 확정 · ① 문구만 D-153 에 맞춰 고침.
- 근거: `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\미확정_병렬\I\I_보고.md` — ① 미납 4계정 ski1121 −745,821(디프 · 대상 밖) · theirumlab −6,986 · k2min1201 −554(관리 상품 공제 0) · 91white 윙 −1,108(관리 시작 전) → 지금 정산서 영향 0원 · ② 48 = 48칸 중 원문 A=0 2칸 +14,400(gbseller808 2026-02 +11,400 · tellace83 2026-04 +3,000) 한 방향 · 자료 없음 6칸 · 신규-06 취소 25,285줄 중 19줄 · 줄 최대 8원(ski1121) · ③ 매입 세금계산서(이용료 발행 = 정답) 185칸 중 184 일치(`i5_이용료_계산서_계정달.csv` · 통제 세션 대조: 계산서 있음 86 = 판매액 ≥100만 89 − 가전 분리로 풀린 3칸) · 쿠폰 뺀 매출 176~179 · 결제 달 158~160 · 윙+RG 합 계정 17/37 · ④ 145칸(+반출비 2칸) 매출인식일 기준 0원 124 · ±1 14 · 리포트 줄 없음 9 · 다름 0(`i8_CFS조정_매출인식일_칸별.csv` · 발생일 기준은 다름 15).
- 정정(사실): T-95 의 신규-06 '±1원' → 줄 최대 8원(ski1121 · 대상 밖) · 그 밖 계정×달 최대 2원.
- 버린 대안: ① 미납 관리 몫을 위탁자 공제로 추가(쿠팡이 안 뺀 돈 · 차이 0 위반) · 표시 없음(나중 청구 시 흔적 없음) · ② '±끝전' 공통 문구 · 48 예정에서 면제 미리 빼기(근거 칸 없음) · ③ 쿠폰 뺀 매출 · 결제 달 · 윙+RG 합 · 가전 분리 없음 · ④ 발생일 묶음.
- 남는 위험(사실): ③ 가전 판정은 categoryId 가 있어야 정확(sg0141n 2026-07 1칸 → T-100) · 매출내역 파일 겹침 같은 줄 781개 = 합산 전 중복 제거 필요(코드 `svc_charges` 입력이 중복을 빼는지 T-38 때 확인) · ① 미납 청구 경로 = 광고센터 화면 필요(T-90).
- 영향 범위: T-38 정산서(참고 줄·예정 문구 · `scoped()` 갈래 나눔) · 산식 엑셀(다시 만들 때 48·신규-06·53·이용료 문구) · CURRENT_RULES 12절.
- 상태: ACTIVE

### D-310 [HEAVY_TASK_CONCURRENCY] 무거운 실행(python 대조·게이트·하위 세션) 동시 실행 허용 — 10-10 '하나씩' 규칙 폐기 (2026-11-18, R233)
- 결정(소유자 2026-11-18 원문): "무거운 실행은 하나씩 규칙 함께 ==> 이제는 동시에 해도 돼." → 무거운 python 대조·게이트·하위 세션을 동시에 돌려도 된다. 하위 세션 브리프의 '무거운 python·게이트 하나씩(`-j 1`)' 줄을 뺀다.
- 그대로 두는 것: 런타임 병렬화 금지(단일 브라우저·위탁계정·Akamai·라이브 로그인은 한 번에 한 세션 · CLAUDE.md '병렬 개발') · 배포 빌드는 통제 세션만(D-201).
- 근거: 소유자 지시. 10-10 BSOD(0x13A) 원인 드라이버는 미확정 그대로(재발하면 그때 다시 판단).
- 버린 대안: 하나씩 유지(소유자 철회).
- 영향 범위: 메모리 `feedback-heavy-tasks-sequential.md` · STATE 주의 · 하위 세션 브리프.
- 상태: ACTIVE (부분 SUPERSEDED by D-377 — 게이트만)

### D-311 [SETTLE_DECISION_BY_DATA] 정산 산식·배정 판단 = 실측 데이터와 쿠팡 확정 금액 대조로 Claude 가 확정 — 소유자에게 결정을 묻지 않음 · 데이터로 못 가르는 건도 근거를 남겨 Claude 가 정하고 보고 — D-288 보충 (2026-11-18, R233)
- 결정(소유자 2026-11-18 원문): "너에게 정확도(쿠팡이 확정한 정산금액과 너가 산출한 금액 차이가 zero)에 대해 설명을 했어. 너가 스스로 실측데이타와 쿠팡이 정산 확정한 데이타와 검증을 할수 있을거야. 그래서 나에게 결정해달라고 문의 하는 것보다 실측데이타 검증을 통해서 확정하는 것이 더 정확해." → ① 정산 산식·나누기·공제 배정·표시는 끝난 달 쿠팡 확정 금액과 원 단위 대조로 통제 세션이 확정한다(D-288 그대로). ② 데이터로 두 안이 똑같이 맞아 가를 수 없는 건(예: 계정 합은 같고 관리 몫 배정만 다른 건)도 소유자에게 묻지 않고 통제 세션이 근거·버린 안을 적어 확정하고, 종합 보고에 '데이터로 못 가른 판단'으로 따로 적는다. ③ 하위 세션은 소유자에게 묻지 않고 실측 대조로 후보·근거를 통제 세션에 보고한다.
- 그대로 소유자 몫(D-288 범위 밖 · 행동): 로그인·비밀번호·2차 인증 · 돈 지급·송금 · 정산서·자료 발송 · 되돌릴 수 없는 삭제 · 배포·운용 PC 설치 · 안전 규칙 변경 · 계약서의 비율·보장액 자체.
- 근거: 소유자 지시 · D-287~D-309 가 이 방식(원 단위 일치)으로 확정됨.
- 버린 대안: 데이터로 못 가르는 건은 소유자 결정 대기(소유자 원문 — 묻는 것보다 검증해 확정이 정확).
- 영향 범위: 모든 정산 세션 브리프 · CURRENT_RULES 12절 · STATE 의 '소유자 결정' 정산 건.
- 상태: ACTIVE

### D-312 [CONSIGNOR_STATEMENT_RULES] D-307 재판단 — 19 빠른정산 사용액 = ±0 유지 · 26 성장 대출·80 MCA 상환·81 체크카드 상계 = 정산금액에서 차감(쿠팡 실지급과 같음)은 유지하되 '위탁자 본인 차감' 줄로 관리 몫 0(관리 몫·계약 비율 나누기에 넣지 않음) (2026-11-18, R233)
- 결정 경위(소유자 2026-11-18 원문): "빠른정산, 대출, 체크카드 건은 내가 올바르게 지시 했는지도 다시 판단해줘." · D-288 ①(공제 배정) · D-311 ②.
- 판단: ① 19 빠른정산 사용액 = 이미 당겨 받은 돈(±0) — 소유자 지시가 맞다. 같은 윙 줄에서 18 계좌인출액과 금액이 따로 나오고(seankim137 2026-08-24 줄: 사용액 491,416 + 인출 254,512 + 광고 424,164 = 지급가능 1,170,092 · 최종 0) 둘 다 ±0 으로 둬도 겹쳐 세지 않는다(F_보고 4절 · `F_18_19_83_빠른정산_줄.csv`). 공제로 두면 이미 받은 돈을 비용으로 또 빼서 위탁자·관리 몫이 844,974 만큼 틀린다. ② 26·80·81 '정산에서 차감' = 방향은 맞다 — 쿠팡이 지급 줄에서 실제로 뺀 돈이라 차감해야 계정 정산금액 = 쿠팡 실지급(차이 0). ③ 그러나 D-307 처럼 일반 공제(계정 공통 비용 → 관리 몫 비율 D-237·D-241 → 계약 7:3)로 두면 위탁자 개인 빚·개인 지출을 우리 몫이 계약 비율만큼(7:3 이면 30%) 떠안는다. 상품·주문과 연결이 없다(대출·MCA 상환 = 판매와 무관하게 70% 줄 지급가능의 약 8.1% · tellace83 26 798,784 + 80 8,121,756 + 예정 910,774 · 체크카드 = seankim137 상계 3건 82,870 · `F_26_80_대출상환_tellace83.csv`). → 정산서에 '위탁자 본인 차감(성장 대출·MCA 상환·체크카드 대금)' 줄로 따로 빼고 관리 몫 0. 계정 합계(정산금액 = 쿠팡 실지급)는 D-307 과 같고 관리 몫만 달라진다.
- 데이터로 못 가른 판단(D-311 ②): 대출·MCA 자금을 누가 받아 어디에 썼는지는 자료에 없다. 관리 상품 재고 등 관리 사업에 쓴 돈이라면 관리 몫 배정이 맞다 — 그 근거가 나오면 새 D항목으로 바꾼다.
- 버린 대안: D-307 ② 그대로 관리 몫 비율 배정(우리 몫이 위탁자 개인 빚을 나눠 짐) · 26·80·81 을 ±0(쿠팡 실지급과 차이 · 위탁자 몫이 실제 받은 돈보다 커짐).
- 영향 범위: 정산 코드(빠른정산 사용액 = FAST · 26·80·81 = 위탁자 본인 차감 줄 · 관리 몫 0) · D-305 따로 줄 그대로 · CURRENT_RULES 12절 · D-307 상태 줄.
- 상태: ACTIVE

### D-313 [SETTLE_FORMULA_CONFIRMED] 묶음 N — 조사 전 46항목 = 기존 결정(D-299~D-304·D-307·D-312)대로 확정 · 윙 판매수수료 예상 수량 = 판매수량 → 환불수량 → 판매액÷판매가 · 33·신규-07 = 감지만 · 32 = 원문 값 (2026-11-18, R233)
- 결정: ① 조사 전 46항목 = 원문 값 확정 20 · 해당 없음(감지만) 17 · 정산금액 밖 · 식 확정 류 — 새 규칙 없음(엑셀 상태만). ② 윙 판매수수료 예상식의 수량 = 판매수량, 0이면 환불수량, 그것도 0이면 판매액÷판매가 · 1개당 사사오입 × 수량. ③ 33 반품배송비 판매자 부담 = 정산금액 영향 0(판매자 계약 택배) · 신규-07 교환 = 0건 · 둘 다 감지만. ④ 32 우대수수료 환급 = 쿠팡 원문 값(다른 출처와 짝 없음 = 데이터로 못 가름 · 85 영중소 대조 최대 10/217).
- 결정 경위: D-288·D-311 · 묶음 N 하위 세션(local_054e306b) 후보를 통제 세션이 확정. ⑤ RG 취소 줄 판매수수료 VAT 예상식 = 지금 규칙(대칭 사사오입) 유지 — 전수 시험(n8)에서 원 주문 줄 있는 25,285줄 중 대칭 25,232 일치(틀림 53줄·합 −27원) > 차감식 후보 25,158(틀림 127줄·합 −264원) · 원 주문 줄 없는 231줄 대칭 231/231 · 지급 줄은 원문 값(D-299)이라 정산금액 차이 0(`미확정_병렬\N\n8.log`).
- 근거: `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\미확정_병렬\N\N_보고.md`·`N_46항목_판정.csv`(46줄 · 통제 세션 개수 대조) — 윙 줄 등식 15식 1,298/1,298 · RG 2,131/2,131 · ② 31,943 → 31,945/31,949 일치 · 새로 틀리는 줄 0 · ljung0622 2026-05 +2원 해소 · 27 1/1 · 79 4/4 · 15 1,298/1,298 · 33 반품 244건 THIRD_PARTY.
- 버린 대안: ② 수량 1 고정 사사오입(판매수량 0·환불 −2 줄 2원 차).
- 영향 범위: 정산 코드 윙 판매수수료 예상식(T-38) · 산식 엑셀 · CURRENT_RULES 12절.
- 상태: ACTIVE

### D-314 [CONSIGNOR_STATEMENT_AD_DEDUCTION_PRECISION] 묶음 K — 윙 광고 부족분 예상 행선지 = 같은 달 30% 줄(다음 달 70% 아님) · RG 광고 월 경계 이동 예상 기본 = 이동 없음(9/30 = 사건) · 광고 미납 참고 줄 = 정산서 기준일 현재 판정·뒤 줄에서 빠지면 지움 — D-289 ③ 일부·D-308 ②·D-309 ① 보충 (2026-11-18, R233)
- 결정: ① 윙 광고 예상 공제에서 M월 70% 줄들이 못 뺀 부족분은 M월 30% 줄에서 빠진다고 본다(예상값 기본 · 확정 줄은 쿠팡 값 D-279). 같은 달 30% 줄 여유가 없을 때의 행선지는 미확정('이월 순서 미확정' 표시 유지). ② RG 광고 월말 하루가 다음 달 첫 줄로 옮겨 가는 일은 9/30 한 번만 관찰(4/4) · 5/31·6/30·7/31·8/31 은 이동 없음 18/18 → 예상값 기본 = 이동 없음 · 대조는 같은 지급일 두 줄 합(D-301) 그대로. ③ D-309 ① 미납 판정 = 정산서 기준일 현재 판정 · 그 뒤 줄에서 빠지면 다음 정산서에서 참고 줄을 지운다.
- 결정 경위: D-288·D-311 · 묶음 K 하위 세션(local_415a0e27) 후보를 통제 세션이 확정.
- 근거: `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\미확정_병렬\K\K_보고.md` — ① 30% 줄 있는 101달 중 53달 원 단위(±3) 일치 + 남은 몫·30% 줄 모두 0 8달 · 30% 여유 없음 11 · 다름 29(앞뒤 달 짝 5쌍 guarisen2024 4→5월 65,413 등 · 조건 = 데이터로 못 가름 · `k1f_30줄규칙.csv`) · 다음 달 70% 줄로 가는 안은 맞는 달 없음 · ② `k4_월경계.csv` · ③ 미납 판정 8칸 중 6 맞음 · 2칸(k2min1201 RG 2026-06·07)은 뒤 09-14 줄에서 빠짐 · 놓친 칸 0(`k5_미납판정.csv`).
- 새 사실: oopean·guarisen2024 는 70% 줄 광고 공제가 그 줄 매출기간 일별 SELLER 합과 다름(6/48 · 4/34) — 달 합은 30% 줄에서 원 단위로 맞음(oopean 5/5달) → 줄 단위 예상값은 '±(같은 달 안 이동)' 가능 · WBpeak 'RG 광고 공제 0' 은 장부 시험 DB 누락(원천 RG 공제 1,483,733 = 청구 1,481,984 + 1,749) → T-71.
- 남는 위험(사실): 다름 29달 · 70% 줄 주 단위 배정 규칙 · 68·신규-01·62·67·70·신규-02 = 묶음 K 항목 3 미실행(인계 = 보고서 6절).
- 버린 대안: 부족분 = 다음 달 70% 줄 · 월말 이동을 매달 가정.
- 영향 범위: T-38 광고 예상 공제 · CURRENT_RULES 12절 · T-71(장부 DB WBpeak RG 광고 누락).
- 상태: ACTIVE

### D-315 [SETTLE_FORMULA_CONFIRMED] 묶음 J — RG 70% = 엑셀 줄마다 ×0.7 사사오입(0에서 먼 쪽) 합(지금 코드 · 893/893) · 판매조정·보류 해제·밀크런·이월 검산식 · 예정 금액 확정 = 정산일 전날 값 · 31 = 29 추가지급과 같은 줄 · 월렛 입금 = 최종지급액 − 재고 손실 보상 (2026-11-18, R233)
- 결정: ① RG 주정산 70% 몫 = 정산 엑셀 줄마다(정산취소 줄 포함) 정산대상액 × 0.7 을 사사오입(0.5 는 0에서 먼 쪽 · 음수 −x.5 → −(x+1))한 합 · 30% = Σ정산대상액 − 그 합 — 지금 코드 `payout.first_payout_70`(Decimal ROUND_HALF_UP) + 줄 단위 금액 그대로 → 코드 변경 없음 · D-308 ⑥ '미확정'을 닫음. ② 41 판매조정 검산 = 그 줄 기간의 음수일(그날 Σ정산금액 < 0) 몫 되돌림 · 마이너스 공제 시점 = 데이터로 못 가름 → 원문 값. ③ 22 보류 해제액 검산 = PENDING 줄 최종액 · 보류해제지급 · 정액보류 중 하나 또는 같은 해제일 묶음 합(보류목록 상태 P 는 해제 뒤에도 P). ④ 51·52 음수 누적 잔액 = 판매 0 인 주(지급 줄 없음) 물류비가 과거 CFS 기록 없이 뒤 줄 미납 CFS 로 붙은 것(규칙 그대로 · 원문 값). ⑤ 신규-21 밀크런 검산 = 픽업 달 묶음 합 = 세금계산서 MilkRun · 줄 배정 = 원문 값. ⑥ 82 이월 예상(R-CO · F 보고 4절 ④) 한도에서 재고 손실 보상을 뺀다 · 남은 달 끝 6줄 = 원문 값. ⑦ 17·신규-19 이용료 줄 배정 = 데이터로 못 가름 → 쿠팡 줄 값(D-299 ④ 그대로) · 검산 = 계정 누적 55,000 × 계산서 달 수. ⑧ 신규-17 정산 예정 금액 = 정산일 전날 수집한 값이 확정값과 같다 → 예정 대조·스냅숏 기준 = 정산일 전날(T-93 · T-78). ⑨ 31 'B 추가정산' = 29 추가지급과 같은 줄(D-297 ⑤ '자료에 줄 없음' 정정 · 처리 = D-308 ① 추가지급 줄). ⑩ 셀러월렛 입금(DEPOSIT) = Σ최종지급액 − 재고 손실 보상(보상은 대표계좌로 직접 입금) → 계약자·위탁자 '쿠팡 실지급' 기준 = 지급 줄 최종지급액 원문(보상 포함 · D-152 차이 0).
- 결정 경위: D-288·D-311 · 묶음 J 하위 세션(local_8a0b2a03) 후보를 통제 세션이 확정 · ① 은 통제 세션이 `J\j2_2_코드검산.log` 로 재확인(지금 코드 70% 893/893 · 30% 847/847 · 장부 840/840 · H 방식(float) 496/893 = H 시험 스크립트 반올림 오류).
- 근거: `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\미확정_병렬\J\J_보고.md`·`j1~j4_보고.md` — ② 음수일 153/153 · 줄 243/243 · 마이너스 공제 시점 최고 28/93 · ③ 149/149 · 계정 합 8/8 · ④ 9/9 계정 원 단위 · ⑤ 112/112 · 줄 배정 106/131 · ⑥ 이월 줄 103/109 · 이월 없는 줄 894/894 · ⑦ 30% 줄 51 · 부족 13 · 이유 없음 16 · 누적 29/35 계정 · ⑧ RG 137/137 · 윙 지급일 합 79/79 · 어긋남 10건 198,830 = 마지막 수집이 정산일 3~16일 전 · ⑨ 2/2 · ⑩ 691묶음 중 689(보상 123묶음 34,319,043).
- 버린 대안: ① 주문·옵션 묶음 반올림(최고 882/893) · float 반올림 · ⑥ 보상 포함 한도(R-CO 원안) · ⑨ 31 해당 없음.
- 남는 위험(사실): 데이터로 못 가름 = 41 공제 시점 · 신규-21 줄 배정 · 82 남은 6줄(세이버 조각 5줄 221,249 · gbseller808 1줄) · 17 줄 배정 → 모두 원문 값이라 확정 줄 정산금액 차이 0 · 예상값만 '미확정' · 신규-17 표본 한 달(T-93) · ski1121 월렛 753,525(디프 · 대상 밖).
- 영향 범위: 코드 변경 없음(① 시험 보강 = `tools/verify_settlement_offline.py` 음수 .5·float 경계 핀 제안 → T-105 와 함께) · 정산 예정 스냅숏 시점(T-78·T-93) · 계약자 정산 실지급 기준(D-152 확인) · 산식 엑셀 · CURRENT_RULES 12절.
- 상태: ACTIVE

### D-316 [SETTLE_FORMULA_CONFIRMED] 묶음 M — 판매수수료 비율 예상 출처 순서 · 묶음 개당 N = 옵션마다 하나 · 입출고비 = 단품가 구간 · 대형2·특대형 배송 = 수량 × 개당 요금 · 밀크런 공제 달 = 지급 줄 기간 시작 달·오래된 청구부터 · 74 = 원문 값 (2026-11-18, R233)
- 결정(예상값 산식 · 확정 줄은 쿠팡 원문 값 D-279 · 끝난 달 정산금액 차이 0): ① 윙 판매수수료 비율 출처 순서 = 그 옵션의 앞 달 비율 → 상품ID 앞 달 비율 → categoryId 표 → Fee-Table → 상품명 AI 판정 → 계정 최빈 비율(옵션·상품ID 비율은 바뀐 적 0건). ② 묶음 상품 개당 N = 옵션마다 하나(지난 정산 줄에서 역산 · 옵션명 'N개'로 정하지 않음) · 처음 나온 옵션 = N 모름 → '미확정' 표시(상품정보 수량 = T-100). ③ RG 입출고비 = 단품가 구간 그대로(÷N 없음) · 대형2·특대형 배송비 = 수량 × 개당 요금. ④ 기타 악세서리 입출고비 차이 = 말단 categoryId 차이(양말 2584·모자 2621 = 800원 표) — 표 변경 시점 아님(자료출처_목록 86행 정정). ⑤ 밀크런 공제 달 = 지급 줄 기간 시작 달 · 픽업 달 청구는 오래된 달부터 갚음 · LIGHT 단가 = 팔레트 수 할인 역산. ⑥ 74 비즈니스 인사이트 = 원문 값(첫 달·플랜 변경 일할 = 데이터로 못 가름).
- 결정 경위: D-288·D-311·D-268(예상 오차 최소) · 묶음 M 하위 세션(local_009ae6cd) 후보를 통제 세션이 확정.
- 근거: `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\미확정_병렬\M\M_보고.md` — ① categoryId 모르는 8계정 윙 8,655줄 · 앞 달 비율 4,759줄 오차 ≤1원 · 처음 나온 118상품 상품명 AI 109 일치 · 윙 전 계정 100원 이상 25칸(+340,347) → 13칸(+91,341) · ② 298옵션 전 줄 일치 · ③ 231/231 · 가구 −174,475 해소 · 화면 표+규칙 338,454/350,181줄 · ⑤ 공제 달 228/228 · 오래된 달부터 114/131 · 엑셀 줄 항등식 663/663 · LIGHT 234/234 · robincohs −31,350 재현 · ⑥ 일수 일할 0/8.
- 버린 대안: ① 계정 최빈 비율 먼저 · ② 옵션명 'N개'(N=1 옵션 46개) · ③ 입출고비 ÷N.
- 남는 위험(사실): ① 첫 달 오판 9상품(100원 이상 5칸) · 8계정 밖 지워진 상품 AI 판정 미실행(8칸 +99,988) · ② 첫 달 N=1 413줄 +314,070 · 표 없는 2차 30개 3,680만 · 처음 보는 칸 6,911줄 · ⑤ 범위 전 몫(gyi0101·ski1121·tellace83)·BOX 단가·김포 추가금 조건 · 밀크런 공제 반영일 계정마다 다름 → 받을 자료(보고서 ④).
- 영향 범위: T-38 예상값 산식 · T-100(categoryId·상품정보 수량 보관) · 자료출처_목록 86행 · 산식 엑셀 · CURRENT_RULES 12절.
- 상태: ACTIVE (부분 SUPERSEDED by D-355 — ① 출처 순서에 한 단계 추가)

### D-317 [CONSIGNOR_STATEMENT_AD_DEDUCTION_PRECISION] 묶음 K 항목 3 — 광고 지원금 = 그 달 광고 공제 예상 합에 포함(따로 줄 없음) · 캠페인 없는 지원금 = 그 달 상품별 배분 비율로 음수 배분 · RG 광고 줄 예상 = D-285 ① 기본 + '줄 배정 ±(같은 달 안)' · 판정 = 달 합·같은 지급일 합·지급 순서 누적 (2026-11-18, R233)
- 결정: ① 68 광고 지원금 = 그 달 마지막 날 'Promotion' 음수 줄로 그 날 청구에 합쳐짐 → 예상값은 그 달 광고 공제 합에 넣고 줄 배정은 쿠팡 줄 값 · 예상값에 '지원금 달 — 줄 배정 미확정' 표시. ② 신규-01 광고비 상품별 배분 합 = 그 달 json 청구가능(검산) · 캠페인 없는 지원금 줄(D-119 로 관리 몫 0 이 되던 몫)은 그 달 옵션별 배분 합 비율로 음수 배분(관리 상품 광고비가 지원금만큼 크게 잡히지 않게). ③ 62·70 RG 광고 줄 예상 = D-285 ①(그 줄 매출기간 일별 청구 합) 기본 + '줄 배정 ±(같은 달 안)' 표시 · 대조·정산서 금액 판정 = 달 합 · 같은 지급일 두 줄 합(D-301) · 지급 순서 누적(D-289). ④ 67·신규-02 = 확정 그대로(일별 보고서로 재확인). ⑤ 날짜별 광고 부가세 끝전 = 데이터로 못 가름 → json × 1.1 예상값 '±1~2원' 경고 유지.
- 결정 경위: D-288·D-311 · 통제 세션 하위 에이전트(묶음 K 항목 3 이어가기)의 후보를 통제 세션이 확정 · ② 의 지원금 음수 배분은 데이터로 못 가른 Claude 판단(쿠팡 상품별 청구액 없음).
- 근거: `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\미확정_병렬\K\K3_보고.md` — ① 10건·9계정·738,990 · 달 합·누적 9/9 차이 0(바로 5 · 앞 달 이월 2 guarisen2024 908,909 = 843,496 + 65,413 · 뒤 줄 2 k2min1201 1,184 = 153 + 1,031) · 줄 배정 사례 갈림(지원금 날 줄 1 · 다음 70% 줄 음수 1 mrc098 −202,522 · 한 줄 몰림 2) · ② 배분 합 = json 청구가능 10/10 달 · 보고서 '판매방식' 칸 3P 뿐(0/49 · 쓰지 않음) · 캠페인 없는 지원금 guarisen2024 −210,000 · quietlab −50,000 · ③ 4계정 103기간 원 단위 87 · 전 계정 387기간 일치 165 · 공제 0 72 · 다름 118 · 달 단위 158달 일치 116 + 이월 26 + 설명된 16 · ④ 67 날짜 847/847 · 캠페인 줄 2,666/2,666 · 신규-02 2,131/2,131 · ⑤ 날 청구가능×10% 사사오입 878/1,187일.
- 버린 대안: 지원금 따로 줄 · 보고서 '판매방식' 칸으로 RG/윙 가르기 · 날짜 며칠 미는 줄 배정(9/190).
- 남는 위험(사실): RG 줄 배정 '공제 0' 72·'다름' 118 기간 규칙 · 지원금 한 줄 몰림 조건 · 10월 판정 보류(tellace83 +4,878 · nicoable +8,394) → 받을 자료(보고서 표).
- 영향 범위: T-38 광고 예상 공제·상품별 광고비 배분(D-119 지원금 몫) · 산식 엑셀 · CURRENT_RULES 12절.
- 상태: ACTIVE

### D-318 [SETTLE_FORMULA_CONFIRMED] 묶음 L — RG 입출고비·배송비 무료 0원 예상 = 계정 시작 창 + 신상품(첫 진열부터 44일 미만) · 신상품 보관 31~45일도 같은 창 무료 · 윙 조건부무료 상품 반품배송비 = 상품 반품배송비 + 기본배송비 3,000 · 46·47 남은 차이 = 빠진 파일 — D-298 ④ 대체 · T-81 닫음 (2026-11-18, R233)
- 결정(예상값 산식 · 확정 줄은 쿠팡 원문 값 D-279): ① RG 입출고비·배송비 0원 줄 = (가) 계정 시작 창: 그 계정 첫 RG 출고일부터 며칠의 모든 줄 0원(끝날 = 데이터로 못 가름 · 1~4일 관찰) (나) 신상품: 옵션 첫 진열일부터 발생일까지 43일 이하 = 0원 · 45일 이상 = 유료 · 44일째 = 미확정(파일 행 순서상 0원 먼저) · 신상품 대상 선정(새 옵션 중 일부만) = 데이터로 못 가름 → 예상값에 '신상품 무료 대상 미확정' 표시. ② 신상품 무료 대상 옵션은 보관비 31~45일 구간도 같은 창(44일 이내) 무료 · 75 세이버 무료 체험(8계정) 시작·길이 = 데이터로 못 가름 → 원문 값. ③ 46·47 반품 회수·재입고 남은 차이 = 빠진 주간 반품 파일·월정산 파일(산식 차이 아님 · 받을 자료). ④ 윙 반품배송비(T-77 ⑤) = 조건부무료 상품은 상품 반품배송비 + 초도분 기본배송비 3,000 · 무료배송 상품 초도반품비 칸은 앱 자료에 없음 → 상품조회 수집 필요(T-100). ⑤ 신규-06 RG 부분 취소 VAT 예상 = 지금 규칙 유지(D-313 ⑤ · L 후보 H1 275/286 도 11줄 1원 남음 · 차이 0 규칙 없음) · 확정 줄 = 원문 VAT(D-299 ②).
- 결정 경위: D-288·D-311·D-268(예상 오차 최소) · 묶음 L 하위 세션(local_cb15a945) 후보를 통제 세션이 확정 · T-81 H1 은 ① 로 대체(관리 몫 오차가 H1 보다 작음).
- 근거: `D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\미확정_병렬\L\L_보고.md`(스크립트 l1~l13·l20) — ① 0원 15,076줄 = 계정 시작 창 428(10계정) + 신상품 14,555 + 44일 경계 203(0원 93·유료 110) · ≥45일 5,090줄 어긋남 0 · 관리 몫(l9) 입출고 100원 이상 14→12칸·절대 467,150→56,960 · 배송 25→20칸·절대 635,598→309,758 · 계정 전체 절대오차 입출고 11.85M→1.28M · 배송 15.16M→1.92M · ② 보관비 144칸 오차 +306,538→+25,004 · ③ hk66597582 −123,725 · wellbing1107 −83,825 · gbseller808 −800 · freewin7777 −400 · bux1004 −50 · ④ 옛 R1 175/193 · guarisen2024 조건부무료 4/4 · 설정 있는 111건 중 98~99 · 판정 불가 82건(초도반품비 칸 없음) · 반례 oopean 1상품·tellace83 04월 7건(설정 이력)·freewin7777 2건.
- 버린 대안: D-298 ④ '지금 규칙 유지' · T-81 H1 · R-44 단독 · 신규-06 H1(차이 0 아님 · D-313 ⑤ 와 대상 겹침).
- 남는 위험(사실): 44일 경계 203줄(입출고 104,140 · 배송 167,050) · 시작 창 끝날 · 신상품 대상 선정 · 세이버 체험 · 정가 A=0 입출고 옛 줄 6,042줄(범위 밖) → 받을 자료(보고서 6절).
- 영향 범위: T-38 RG 물류비 예상값 · T-100(초도반품비·categoryId 수집) · T-81 닫음 · 산식 엑셀 · CURRENT_RULES 12절.
- 상태: ACTIVE

### D-319 [SETTLE_FORMULA_CONFIRMED] D-304 3PM 되돌림 = '지급 완료' 윙 음수 회차에만 · 예정(지급 전) 음수 회차는 음수 그대로(곧 회수될 돈을 예정에서 빼 둠) — D-304 적용 범위 한정 (2026-11-18, R233)
- 결정: 윙 회차 최종액 음수를 '3PM_매출채권'으로 되돌리고 그 줄 지급 = 0 으로 보는 처리(D-304)는 지급 완료 줄에만 한다. 예정 줄의 음수 최종액은 그대로 두어 예정 합에서 뺀다(뒤 회차 3PM 회수 공제가 아직 자료에 없기 때문).
- 결정 경위: D-288·D-311 · 코드 반영 하위 에이전트 검증(`D:\coupang-analytics\output\_통제_261118_밤작업\코드반영\검증_보고.md`)에서 D-304 를 예정 줄까지 적용하자 oopean 계정 예정 입금 +1,813,986 · wellbing1107 관리 +9,364 가 생김 → 통제 세션 판단.
- 근거: D-304 근거(`미확정_병렬\G\G_보고.md` ①)는 지급 끝난 회차의 현금(Σmax(최종, 0)) 일치만 확인 · 예정 음수 회차를 0 으로 두면 뒤 회수 공제가 없는 동안 예정 합이 |음수|만큼 커져 끝난 뒤 실제와 차이(D-268 예상 오차) · 음수 그대로면 회수 뒤 실제와 같음.
- 버린 대안: 예정 줄에도 D-304(예정 부풂) · 예정 음수 회차에 '3PM 회수 예정' 줄을 따로 만들기(같은 금액 · 줄만 늘어남 — 필요하면 T-38 표시에서).
- 영향 범위: `settlement_statement_account.py` D-304 분기(코드 반영 브랜치) · CURRENT_RULES 12절.
- 상태: ACTIVE

### D-320 [SETTLE_FORMULA_CONFIRMED] 신규-09 RG 정산취소 줄 회차 = 자기 매출인식일이 든 파일 기간 · 22·51/52·41·신규-21 독립 재계산 보충(결정 변경 없음) · 41 예정 경고 문구 (2026-11-18, R234)
- 결정: ① 신규-09 RG '주문 정산취소' 음수 줄은 **자기 매출인식일이 든 파일 기간(주정산·최종액·월정산 모두)의 회차**에 들어간다 — 원 판매 주·발생일로 옮기지 않음 · 한 줄이 두 회차에 들어가지 않음 · 금액 = 쿠팡 원문(70% = 취소 줄 포함 줄마다 사사오입 합 D-315 ①). ② 22 보류 해제·51/52 미납 CFS·41 마이너스 공제 시점·신규-21 밀크런 회차는 D-315 ②③④·D-316 ⑤ 그대로(독립 재계산으로 같은 결론) · D-315 ④ 원인 목록에 guarisen2024(−10,627 · 같은 원인) 추가. ③ 41 예정 경고 문구(금액 영향 0 · T-38 표시용): "음수일 금액은 보통 21일 안(2~35일)에, 늦어도 그 주 70% 지급일까지 뒤 지급 줄에서 빠집니다. 줄에 남는 돈(지급가능 + 판매조정 − CFS)이 모자라면 그 한도만큼만 빠지고 나머지는 뒤 줄로 넘어갑니다."
- 결정 경위: D-288·D-311 · 하위 세션 검산1(T-101) 보고 → 통제 세션이 로그 대조 후 확정.
- 근거: `D:\coupang-analytics\output\_통제_261118_병렬2\검산1\검산1_보고.md` · ① 취소 줄 27,780/27,780 자기 매출인식일 기간 안(발생일 기간 밖 24줄) · 파일 기간 1,037 겹침 0(`v1_09f_기간겹침.log`) · 70% 줄 893/893 일치(취소 뺀 안 162/893 = 취소 없는 기간 수 · `v1_09c_취소줄_회차.log`) · 장부 취소 840기간 840/840 같음(Difpick 제외) · ② 22 보존식 윙 7계정 중 6 잔차 0 · ski1121 잔차 −3,277,380 = 미해제 PENDING 11줄과 원 단위 같음 · 51/52 줄 없는 원 기간 51곳 판매 줄 0(51/51) · 9계정 9/9 · ③ 41 8계정 65음수일: 첫 공제 음수일 뒤 2~35일(중앙 21) · 60/65 그 주 70% 지급일까지 전액 · 나머지 5 = 한도 소진(4/4) · 자기 줄 상한 규칙은 개선 없음(23/69 · 28/93) · 신규-21 픽업일 기간 정확 일치 최고 7/176.
- 버린 대안: 취소 줄을 원 판매 주로 옮김(893 중 162만 맞음) · 41 시점을 고정 규칙으로 확정(데이터로 못 가름 · 예정은 경고값).
- 영향 범위: 산식 엑셀 신규-09 = 확정 · T-38 예정 경고 문구 · CURRENT_RULES 12절 지급 흐름 줄 · 받을 자료(로그인): 41 원 음수일(nicoable · wavetech · hk66597582 · ski1121) · ski1121 보류목록 전체(선택 · 정산금액 영향 0인 3,348 차).
- 상태: ACTIVE

### D-321 [SETTLE_FETCH_SUSPECT] 정산 받기 의심 감지 — 매 정산 실행 끝에 받은 자료끼리 대조 · 다시 받기는 목록만(자동 재요청 없음) (2026-11-18, R236)
- 결정: 매 정산 실행 끝(전 계정 뒤 1번)에 받은 자료끼리 대조한다 — 비용 리포트 ↔ 지급 줄 공제 칸 · 라이브 요약 ↔ 공제(계산일 뒤 같은 금액 짝) · 광고 json subtotals 있음 · 밀크런 총 합계금액 = 발생 + 조정액 + 추가금 + 세액. 어긋나면 `output\정산\자료출처\받기의심.csv`·`다시받을목록.csv` 에 적기만 하고 자동으로 다시 요청하지 않는다(자동 재요청 = 별도 결정). 실행당 새 엑셀 400개 상한 + 파일별 기억(크기·수정 시각).
- 결정 경위: 소유자 "해야할 작업 병렬로 모두 진행해줘"(11-18) → 하위 세션 T-82 구현 · 소유자 "응, T-78 병합하고 게이트 돌려줘"(11-18) → 통제 세션이 보고를 파일과 대조 후 병합.
- 근거: `D:\coupang-analytics\output\_통제_261118_병렬2\T78_T82\T78_T82_보고.md` 1절 · 재현(output38 읽기만 · `재현_output38.log`) = D-302 4사례 모두 '받기 의심'(91white 6,660 · tellace83 2,220 · sg0141n 2,220 · freewin7777 347) + 새로 ski1121 라이브 202602 빈 json ↔ 2026-04-06 공제 20,110 · 그 밖 비용 리포트 ≈2,100개 공제 칸과 원 단위 전부 일치 · 밀크런 663줄 합 전부 일치 · 광고 subtotals 없음 540파일 = 'T-90 필요분만'(D-291 ⑥) · 확인 필요 2줄(gyi0101·ljung0622 2026-03-12 라이브 공제 ↔ 202601 요약 다름) · 브랜치 게이트 26종 통과(`게이트_최종.log`).
- 버린 대안: 의심 건 자동 재요청(다시 받아도 머리줄만이면 무한 반복 · D-184 '줄 0 = 0원' 판정 재검토가 먼저).
- 영향 범위: `settlement_fetch_check.py`(새) · `tools\settlement_download.py` run 끝 · 다시 받기(로그인) = 리뷰-이벤트 3회차 · freewin7777·ski1121 라이브 202602 → 또 머리줄만이면 D-184 재판단.
- 상태: ACTIVE (부분 SUPERSEDED by D-339 — 자동 재요청 없음 → 다시받을목록 자동 재받기)

### D-322 [SETTLE_SOURCE_DAILY_FETCH] T-78 S1~S3 구현 — 자료 출처 등록표 58행 SSOT · 원문 대조 · 광고 진행 달 일별 매일 · 공개 웹 3페이지(일반 연결) (2026-11-18, R236)
- 결정: D-280 앱 구현 1차. ① 등록표 = `settlement_sources.SOURCES`(58행 · 출처 또는 `NOT_SOURCED` 사유 · 빈틈 0) · 변경이력.csv(추가만) · 스냅숏. ② S1 원문 대조 = 받은 원문에서 새 카테고리ID·수수료율·서비스이용율 값이 나오면 변경 기록. ③ S2 광고 = 끝나지 않은 달(이번 달 1일~어제 · 받을 날 전 지난달) 일별 정산을 `{계정}_광고정산진행_{YYYYMM}.json` 에 매일 덮어씀 · `_광고_다시받기.json` 에 적힌 달만 subtotals 다시. ④ S3 공개 웹 3페이지 = 쿠키·프록시 없는 일반 연결(로그인 아님 · 프록시 금지 규칙과 충돌 없음). ⑤ 새 명령 `settlement_download.py sources`(로그인 없음 · `--hidden` = 공개 웹도 안 읽음).
- 결정 경위: D-280 · 설계 `docs\plans\T78-source-list-daily-fetch-design-2026-11-17.md` S0~S3 · 소유자 "응, T-78 병합하고 게이트 돌려줘"(11-18).
- 근거: 보고 1~2절 · 원문 1,409파일 · RG 카테고리ID 219 · 윙 옵션 786 · 한 항목 비율 값 2개 이상 = 0(지금까지 수수료율 바뀐 기록 없음) · 오류 0.
- 버린 대안: S4 fee-details 화면 조작 모듈 지금 만들기(화면 구조 기록 전 · 라이브 첫 시험 = 사무실·소유자 있을 때 `S4_라이브시험_절차.md`).
- 영향 범위: `settlement_sources.py`(새) · `settlement_ads.py` · `tools\settlement_download.py` · 시험 `verify_settlement_sources_offline.py` · 남음 = S0 등록표를 `자료출처_목록.csv` 에 합치기(통제 세션) · 공개 웹이 스크립트로 그리는 페이지면 매일 '자료 출처 실패' → 첫 `sources` 실행으로 확인 · 운용 PC = 다음 배포(T-59).
- 상태: ACTIVE

### D-323 [CONSIGNOR_STATEMENT_RULES] D-312 ② 소유자 확인 — 성장 대출·MCA 상환·체크카드 상계 = '위탁자 본인 차감' 줄·관리 몫 0 그대로 유지 (2026-11-18, R236)
- 결정: D-312 ②(26 성장 대출 · 80 MCA 상환 · 81 체크카드 상계 = 정산금액에서 차감은 하되 '위탁자 본인 차감' 줄로 관리 몫 0)를 그대로 유지한다. D-312 의 '데이터로 못 가른 Claude 판단' 표시는 이 항목으로 소유자 확인됨.
- 결정 경위(소유자 2026-11-18 원문): 통제 세션이 "D-312에서 대출·체크카드 대금의 관리 몫을 0으로 둔 것은 데이터로 가를 수 없어 제가 판단한 것 … 대출 자금을 관리 사업에 쓰셨다면 관리 몫 배정이 맞습니다"라고 묻자 **"D-312건도 너의 의견 수용."**
- 근거: D-312 판단 · 해당 계정 = tellace83(MCA·성장 대출) · seankim137(체크카드) · 판정표 `output\_통제_261118_밤작업\T106_본인차감판정\본인차감_처리판정.json`(T-106).
- 버린 대안: 대출·MCA·체크카드를 관리 몫 비율로 나눔(D-307 ② · 관리 측이 위탁자 개인 빚을 나눠 짐).
- 영향 범위: 코드 변경 없음(D-312 코드 그대로) · T-106 3계정 재계산 검산 기준 그대로 · STATE 미해결 'D-312 대출·체크카드 관리 몫 0 = Claude 판단' 줄 닫음.
- 상태: ACTIVE

### D-324 [SETTLE_FORMULA_CONFIRMED] 신규-22·79 리뷰 이벤트 공제 = 회차는 쿠팡 배정(예측 불가)·원문 값 사용 · 검산 = 계정 누계 = 사용 리뷰 × 2,220 · D-184 '리포트 줄 0 = 0원' 정정 (2026-11-18, R236)
- 결정: ① 회차 공제액 = 원문 값(RG `totalPostPurchaseDeductionAmount` · 윙 차감 사유 '리뷰 이벤트'). ② 검산 = 계정 누계 공제 = 캠페인 사용 리뷰 수 × 2,220(79번 1건 금액 D-302 ⑤). ③ 지급 전 예상 = '새 사용 리뷰 × 2,220 · 회차 미확정' 경고값(회차 추측 배정 금지 — 틀린 회차로 2,220~8,880 이동). ④ D-184 의 '리뷰 이벤트 리포트 자료 줄 0 = 0원'은 틀림 — 리포트가 0줄이어도 공제가 있을 수 있으므로 금액은 공제 칸 원문 값. 산식 엑셀 신규-22 = 미확정 → 원문 값 사용.
- 결정 경위: D-288(공제 배정·대조 방법 = 통제 세션 · 정산금액 차이 0 기준) · 소유자 11-18 "응, 백그라운드로 진행해줘"(검산 지시).
- 근거: `D:\coupang-analytics\output\_통제_261118_재개준비\신규22_리뷰공제_이월검산.md`(스크립트 `_s22\`) — 공제 6건(기존 4 + sg0141n 예정 2) 모두 붙은 회차 여력 > 공제(부분 공제 0 · 이월 칸 0) · 이월 가설 0/6(반례 5 · 애매 1) · RG 예정 스냅숏 6,261개에서 2,220 배수 이동 0 · 리포트 3개 모두 머리줄만(합 0) vs 같은 회차 공제 11,100 · 계정 누계 91white 11,100 = 5×2,220 · tellace83 2,220 = 1건 · robincohs·guarisen2024 0 = 0 · sg0141n 15,540 vs 19,980 = 2건 미배정(11-16 자료). 윙 화면(11-18 tellace83 · `윙화면_tellace83\79_리뷰이벤트_재받기.md`): 리포트 재요청도 자료 줄 0 · 상세 '리뷰 이벤트(g) 2,220'.
- 버린 대안: 지급 부족 이월 가설(반례 5) · '다음 열린 회차' 배정(1/6) · 리포트 줄 합 사용(0원 → 공제와 다름).
- 영향 범위: 산식 엑셀 신규-22·79 · CURRENT_RULES 10절 리뷰 리포트 줄 · 코드 후속(T-112: `settlement_fetch_check.py` 받기 의심에서 리뷰 3건 제외 · 계정 누계 검산) · 리뷰별 생성일 화면(로그인)이 있으면 발생일 기준 후보 재검토.
- 상태: ACTIVE

### D-325 [SETTLE_FORMULA_CONFIRMED] 74 비즈니스 인사이트 청구액 = 월정액(VAT 제외) × 12 ÷ 365 × 유료 이용일수(유료 시작일~그 달 말일) 사사오입 → × 1.1 사사오입 · 회차 공제 = 지급액 한도까지 나눠 빠짐(원문 값) (2026-11-18, R236)
- 결정: ① 달 중간 유료 시작(첫 달·플랜 변경·무료 체험 종료 다음 날) 청구 = 위 식 · 달 첫날 시작·월말 갱신 = 월정액 그대로. ② 회차별 공제액은 지급액 한도까지 여러 회차로 나뉘어 빠지므로 원문 값(예상값 = 청구액 − 이미 뺀 조각). 산식 엑셀 74 = 원문 값 사용 → 확정(청구액 식).
- 결정 경위: D-276(윙 화면 직접 확인) · D-288 · 소유자 11-18 "tellace83 로그인 했어." · "nicoable 로그인 했어."
- 근거(원 단위 일치 · 반례 0): 윙 화면·매입세금계산서 — tellace83 2026-11-09 시작 375,000×22일 = 271,233(화면) · BI_RG 2025-09 78,115(99,000×24일) · 2025-11 345,205(375,000×28일) · nicoable BI_RG 2026-10 70,225 / 77,248(89,000×24일 · 무료 체험 종료 10-07 다음 날부터 · 25일이면 73,151로 불일치) · 기존 RG 공제 85,927 · 3,617 · 379,726 · 41,589 · 93,341 설명. nicoable 20,228 = 77,248 의 첫 회차 조각(11-10 20,228 + 12-04 44,154 = 64,382 · 남은 12,866 미표시 · 12-04 회차 지급액 한도까지만). 파일: `output\_통제_261118_재개준비\윙화면_tellace83\74_비즈니스인사이트_구독내역.md` · `59_매입세금계산서_202509-12.md` · `윙화면_nicoable\74_비즈니스인사이트.md`. 정정: M_보고 4절 '8건' 중 22,973·118,701·41,589·93,341 은 csv '차' 칸 값.
- 버린 대안: 월정액 × 일수 ÷ 그 달 일수(M_보고 0/8) · 20,228 을 일할 금액으로 봄.
- 영향 범위: 산식 엑셀 74 · 정산 예정 경고값(코드 반영 = 별도 할 일) · 12-01 신규 요금제('프로' 이상 · 화면 공지) 뒤 월정액 표 갱신 필요.
- 상태: ACTIVE

### D-326 [SETTLE_FORMULA_CONFIRMED] RG 신상품 무료 = 첫 진열일(첫 입고완료일 + 1)부터 45일(2026-04~08 시작분 모두 · 8월 공지 '30일'과 달리 실제 45일) · 44일째 줄 = 원문 값 · 대상 선정 = 미확정(원문 값) (2026-11-18, R236)
- 결정: 43·44·45·76·76-2 의 신상품 무료 창 = 첫 진열일 포함 45일 — 입출고·배송 k ≤ 43 = 0원 · k = 44 = 쿠팡 줄 값 · k ≥ 45 유료 · 보관 31~45일 무료는 k ≤ 44. 첫 진열 2026-04-01~08-31 범위 밖 = 대상 아님. 대상 옵션 선정(기간 안 166개 중 30개만 대상 · 상품 단위 · 신청 방식 추정)은 데이터로 못 가름 → 쿠팡 줄 값(원문). D-318 ①의 신상품 줄을 구체화(대체 아님).
- 결정 경위: D-288 · 소유자 11-18 "응, 백그라운드로 진행해줘"(재대조 지시).
- 근거: `D:\coupang-analytics\output\_통제_261118_재개준비\신상품무료_45일_재대조.md`(스크립트 `_newfree\`) — 대상 30옵션 입출고·배송 각 19,848줄 중 첫 진열일 기준 19,755줄 원 단위 일치(어긋난 93줄 = 전부 k = 44) · 첫 입고완료일(8옵션) = 진열 하루 전 · 첫 배송완료 19,583 · 첫 주문 19,542 · 첫 결제 19,543(더 나쁨) · 7월 시작 5옵션 k ≤ 43 8,760줄 0원 · 8월 시작 7옵션 k 30~43 327줄 0원(30일 적용 시 입출고 558,900 · 배송 721,800 오차) · 윙 공지(11-18 · `윙화면_tellace83\43-45_76_신상품무료.md`) "판매 이력이 없는 신규 상품 45일간 로켓그로스 비용 0원". 남는 차: 경계 유료 110줄 271,190 · 경계 0원 93줄(정가 A 상한 371,250) · 보관 18칸 +24,474 = 신상품과 무관(원인 별도).
- 버린 대안: 첫 주문·배송·결제일 시작점 · 8월 30일 적용.
- 영향 범위: 산식 엑셀 43·44·45·76·76-2(부분 → 범위 좁힘) · 받을 자료(로그인): 입고완료 일시·배송완료 시각(경계 7옵션) · '신규 상품 프로모션' 신청 내역 화면(지금 404).
- 상태: ACTIVE

### D-327 [SETTLE_SCOPE] 2025년도 정산은 확인·작성 대상 아님 — 2026년 줄이 정상이면 2025 제외 줄은 점검하지 않음 (2026-11-18, R236)
- 결정(소유자 2026-11-18 원문): "2025년도 정산이 필요없어. 그 이후 2026년도건이 정상이면 체크 안해도 됨."
- 적용: 정산서·검산·자료 받기 확인에서 정산일·판매가 2025년인 줄(keep() 제외 줄 등)은 점검하지 않는다. 2026년 줄의 빠짐·금액 일치만 확인한다.
- 근거: 11-18 2026 점검 `D:\coupang-analytics\output\_통제_261118_재개준비\제외기간_관리범위_확인.md`(스크립트 `_scope\`) — 41계정 2026 정산 줄 3,438줄 · 1,438,843,981원 중 keep()(`settlement_ledger.py:159-166`) 제외 0줄 · 원본 재집계 = 앱 줄(계정×채널 78곳 · 3,453줄 · 1,439,707,198원 차이 0) · 제외 252줄 332,983,817원 = 전부 정산일·판매 2025.
- 버린 대안: 2025-09·10·11 초 제외 줄의 관리 범위 개별 확인(tellace83 987,141 · ski1121 96,349,098 · 경계 주 1,248,444).
- 영향 범위: CURRENT_RULES 10절 · T-72 ⓐ(2025-11 RG 물류비) 등 2025 대상 할 일 재검토 · D-165(정산 자료 2026-01부터) 와 같은 방향.
- 상태: ACTIVE

### D-328 [SETTLE_SCOPE] 2025년도에 판매된 건은 정산에 포함하지 않음 — 판매 시점 = 정산서 달 기준(윙 구매확정일 · 로켓그로스 매출인식일) (2026-11-18, R237)
- 결정(소유자 2026-11-18 원문): "2025년도에 판매된 건은 정산에 포함 하지 않음, 참고해."
- 적용: 판매 시점이 2025년인 판매 줄은 정산일이 2026년이어도 위탁정산서·셀독 정산서 금액에 넣지 않는다. 판매 시점 = 정산서 달 정의(신규-23 · D-262: 윙 = 구매확정일 · 로켓그로스 = 매출인식일 — Claude 판단: 소유자 원문에 날짜 기준이 없어 기존 정의를 따름).
- 미확정(STATE 미해결): 2025 판매와 묶인 비용(2025 달 광고비 이월·밀크런·물류비가 2026 지급 줄에서 공제된 것)을 함께 뺄지 — 금액 측정 뒤 판단(하위 세션 s1-excel-2025 측정 중). 지금 코드는 정산일 기준 keep()(`settlement_ledger.py:159-166`)이라 2026 지급 줄 안의 2025 판매 몫이 들어가 있을 수 있음 — 측정 전 코드 수정 안 함.
- 근거: 소유자 원문(위) · D-327(2025 정산 확인·작성 대상 아님)과 같은 방향 · D-165(정산 자료 2026-01부터).
- 버린 대안: 정산일 기준 2025 제외만(D-327 범위) — 2026 지급 줄 안의 2025 판매가 남음.
- 영향 범위: CURRENT_RULES 10절 · 정산서 줄 고르기(keep()) · 산식 엑셀(2025 판매 제외 표시) · T-38 41계정 대조 기준.
- 상태: ACTIVE

### D-329 [SETTLE_SCOPE] D-328 적용 = 정산 줄 단위 — 판매 기간이 2025년인 줄은 공제까지 통째로 빼고, 2026년 판매 줄은 쿠팡이 그 줄에서 뺀 비용 그대로(2025 비용 따로 떼지 않음) (2026-11-18, R237)
- 결정(소유자 2026-11-18 선택 원문): "줄 단위로 처리(추천)" — 질문 = 2026 판매 줄에 붙은 2025 비용(과거 CFS 4,530,035 · 미납 CFS 16,845 = 원문 · 2025-11·12 밀크런 약 4.4백만 · 광고 이월 약 21만 = 추정)을 어떻게 할지.
- 적용: ① 정산 줄의 판매 기간(윙 구매확정일 · RG 매출인식일 기간)이 전부 2025년이면 그 줄(판매·공제·최종) 제외 ② 2026년 판매 줄은 원문 공제 그대로 — FIFO 등 추정으로 2025 비용을 떼지 않음(D-146 추정 금지). 2025·2026 에 걸친 줄 = 0(쿠팡이 연말 줄을 '~12-31'·'01-01~'로 나눠 보냄 · 실측).
- 근거: `D:\coupang-analytics\output\_통제_261118_재개준비\1단계\1단계_보고.md` 4-1~4-3절 · `s4_①_줄.csv`(통제 세션 재합산 확인 — 267줄 · 판매 567,640,805 + 보류 해제 262,360 − 공제 296,711,676 = 최종 271,191,489) — 41계정 2026 정산 줄 3,438줄 · 1,438,843,981 중 판매 기간 전부 2025 = 267줄(윙 94줄 65,546,152 · RG 173줄 205,645,337 · 정산일 2026-01 182줄 · 02 85줄) · 지금 keep()(`settlement_ledger.py:159-166`)에 모두 들어가 있음.
- 버린 대안: 2026 판매 줄에서 2025 비용도 떼어 냄(밀크런·광고 이월 = FIFO 추정 필요 · 추정 근거를 정산서에 남겨야 함).
- 영향 범위: 위탁정산서·셀독 정산서 줄 고르기(코드 = T-117) · 이미 보낸 11-03 위탁정산서(T-72 · 재발행 = 소유자) · T-38 41계정 대조 기준 · 산식 엑셀 16·42·신규-23 표시.
- 상태: ACTIVE

### D-330 [SETTLE_FORMULA_CONFIRMED] 61 윙 광고 부족분 행선지 · 76-2 계정 시작 혜택 끝날 = 화면으로도 못 가름 → 원문 값 사용으로 닫음(예상값 표시 유지) (2026-11-18, R237)
- 결정: ① 61 윙(SELLER) PA 광고 = 확정 줄은 쿠팡 줄 값 · 30% 줄 여유가 없을 때 부족분 행선지·짝 이동 조건은 데이터·화면 모두로 못 가름 → 산식 엑셀 '부분' → **원문 값 사용** · 예상값은 지금처럼 '이월 순서 미확정' 표시(D-283·D-289 그대로). ② 76-2 계정 시작 혜택(입출고·배송 0원 기간) 끝날 = 화면에 문구 없음 → **원문 값 사용**(신상품 무료 창은 D-326 그대로 · 대상 선정 = 원문 값). 다른 계정 화면에서 시작 혜택 문구가 나오면 다시 봄.
- 결정 경위: D-288(공제 배정·대조 방법 = 통제 세션) · D-311(데이터로 못 가르는 건도 근거 남겨 확정) · 소유자 11-18 "8건을 병렬로 진행 가능하면 모두 진행해."
- 근거(sg0141n 윙 화면 11-18 · 읽기만): `D:\coupang-analytics\output\_통제_261118_재개준비\윙화면_sg0141n\61_윙광고비_회차표기.md` — 정산 현황 미리보기 차감 칸 'PRODUCT/BRAND ADVERTISING COS' = 금액만 · 청구 달·회차 표기 없음 · `76-2_시작혜택_신상품화면.md` — 로켓그로스 정산현황 홈 띠 = 세이버 무료 체험 종료일만 · '시작 혜택' 문구 없음(nicoable 11-18 같음) · 신상품 프로모션 화면 404(tellace83·sg0141n). 정산금액 영향 = 0(확정 줄 원문 값).
- 버린 대안: 앞뒤 달 짝 5쌍으로 행선지 규칙 추정(조건 못 가름 · 29달 다름) · 시작 혜택 끝날을 0원 줄 마지막 날로 추정(계정 1~4일 차 · 신상품 무료와 겹침).
- 영향 범위: 산식 엑셀 61·76-2(부분 → 원문 값 · 부분 8 → 6) · T-80 남은 확인 목록에서 해당 화면 제외.
- 상태: ACTIVE

### D-331 [SETTLE_FORMULA_CONFIRMED] 신규-03 로켓그로스 카테고리 할인표 = 확정(화면 표 57개 · 화면과 원문이 다른 칸은 원문 값) · 43 입출고비 · 44 배송비 = 원문 값 사용(묶음 첫 달 수량 = T-100 뒤 재대조) (2026-11-18, R237)
- 결정: ① 신규-03 = 확정 — 예상값은 윙 화면 할인표(2차·말단 × 사이즈 × 판매가 구간) 먼저 · 화면과 원문이 다른 칸(지금 휴대폰/액세서리 입출고 극소형 0~5천 원 = 원문 650 · 화면 600)은 원문 값. ② 43·44 '부분' → 원문 값 사용 — 확정 줄은 쿠팡 줄 값 · 남은 예상값 차(묶음 N 모름 192줄 +142,440 · 대형 예외 6줄 −41,950 · 2026-07-15 정가 그대로 4줄 −3,200)는 표 문제가 아님 · 묶음 첫 달 수량은 T-100(상품 수량 날짜별) 배포 뒤 재대조.
- 결정 경위: D-288 · D-311 · 소유자 11-18 "8건을 병렬로 진행 가능하면 모두 진행해."
- 근거: `D:\coupang-analytics\output\_통제_261118_재개준비\부분8\할인표\할인표대조_보고.md` — 2026 유료 줄(매출인식일 2026 · 정가 A>0 · 최종 F>0) 318,833줄 중 318,548줄 일치(99.911% · 입출고 99.946% · 배송 99.876%) · 표 없는 2차 0 · 처음 보는 칸 6,911 → 0 · 휴대폰 칸을 빼면 표 값 때문에 어긋난 줄 0 · 화면 표 = 11-17 20개 + 11-18 sg0141n 37개 · categoryId 없는 기타 악세서리 70옵션 = 상품명 AI 판정(판정표 `h3_말단_AI판정.csv` · 확신 중간 15옵션 원문 근거로 정정) · '앞 달 원문 칸 먼저' 방식은 100원 이상 40칸으로 화면 표 먼저(29칸)보다 나쁨.
- 버린 대안: 신규-03 부분 유지(휴대폰 1칸 원인 미상 — 원문 값 조건으로 정산 영향 0) · 앞 달 원문 칸 먼저.
- 영향 범위: 산식 엑셀 신규-03·43·44 · 기록 정정('표 없는 2차 30개' → 0 · 건강식품 말단 표 받을 것 → 필요 없음) · 예상값 코드(할인표 화면 값 = T-78 S4 주 1회 확인 대상).
- 상태: ACTIVE

### D-332 [SETTLE_FORMULA_CONFIRMED] 45 보관비 · 76 보관비 무료 혜택 = 확정 — 세이버 무료 체험 = 계정 시작 창 끝 다음 날부터 270일 · 보관 남은 18칸 +24,474 = 원인 4가지로 원 단위 설명 (2026-11-18, R237)
- 결정: ① 세이버 무료 체험 기간 = 계정 시작 창(D-318 ①) 끝 다음 날 시작 · 종료 = 시작 + 270일 → 기간 안 보관 31~60일 무료(C) · 구독료 0. ② 45 보관비 예상 = 지금 산식 + 계정 시작 창(보관 자료 첫 1~2일 B=A)도 보관에 적용 + 1개당 1.5원 끝전 = 지금 반올림(사사오입) 그대로. 정가 A=0 줄(2026-04-29 뒤 0줄)·하루 할인 빠짐(gyi0101 09-26 −163) = 원문 값. ③ 76 세이버 C 줄 0.6% 불일치(539줄) = 전부 최종 0원(B·C 나눔만 다름) → 정산금액 영향 0.
- 결정 경위: D-288 · D-311 · 소유자 11-18 "8건을 병렬로 진행 가능하면 모두 진행해."(계정 로그인 = 소유자 · 화면 읽기만).
- 근거: 파일 분석 `D:\coupang-analytics\output\_통제_261118_재개준비\부분8\보관_반품\보관_반품_보고.md`(18칸 = A=0 +18,603 · 시작 창 +3,705 · 1.5 끝전 +2,329 · 하루 할인 빠짐 −163 = +24,474 원 단위) · 윙 정산현황 홈 띠 '무료 체험 종료일'(11-17·11-18 읽기만) = 식과 6/6 일치: sg0141n 2027-01-27 · oopean 2027-02-15 · 91white 2027-03-01 · mrc098 2027-05-10 · rladygks0221 2027-05-09 · nicoable 2027-05-04(`부분8\로그인화면\윙화면_{계정}\45_76_세이버_체험종료일.md` · `윙화면_sg0141n\76-2_시작혜택_신상품화면.md`). 남은 추정 계정 = dalbong1849·wavetech 2027-05-09·05-04(로그인 막힘 · 같은 식).
- 버린 대안: 세이버 체험 = 약 9개월 고정(시작점 없이) · 시작 창을 보관에 적용하지 않음(3계정 18칸 중 +3,705 남음).
- 영향 범위: 산식 엑셀 45·76(부분 → 확정 · 부분 3 → 1) · 예상값 코드(세이버 체험 끝날 · 시작 창 보관 적용 = 정산 코드 후속) · 2027-01 뒤 세이버 유료 전환 달부터 구독료(D-298 108,900).
- 상태: ACTIVE

### D-333 [SETTLE_FORMULA_CONFIRMED] 4 윙 반품배송비 수입(구매확정 전 고객 귀책) = 원문 값 사용 · 규칙 = 판매자접수면 편도, 주문자·쿠팡CS 접수면 지금 규칙(R1) — 접수채널 칸을 앱이 받게 되면 예상값에 적용 (2026-11-18, R237)
- 결정: ① 확정 줄 = 쿠팡 원문 값(정산금액 영향 0) → 산식 엑셀 4 '부분' → **원문 값 사용**. ② 예상값 규칙(확인됨) = 반품 접수채널 '판매자접수' → 편도(등록 반품배송비 1회) · '주문자접수'·'쿠팡CS' → 지금 규칙(R1 · 왕복 등). ③ 앱은 접수채널 칸을 받지 않으므로 그 전까지 예상값 = R1 + '판매자 접수면 편도일 수 있음' 표시 · 접수채널 수집 = 새 할 일(T-118 · 앱 레인 A). ④ 초도반품비(무료배송 상품) = T-100 자료 쌓인 뒤 재대조.
- 결정 경위: D-288 · D-311 · 소유자 11-18 "8건을 병렬로 진행 가능하면 모두 진행해."(계정 로그인 = 소유자 · 화면 읽기만).
- 근거: `D:\coupang-analytics\output\_통제_261118_재개준비\부분8\로그인화면\로그인화면_보고.md` — 윙 반품 관리 화면으로 접수채널을 본 고객 귀책 18건: 판매자접수 4(oopean 3·tellace83 1) = 모두 편도 · 주문자·쿠팡CS 14(oopean 3·nicoable 5·freewin7777 2·guarisen2024 4) = 모두 편도 아님(18/18) · 화면 '배송비부담' 금액 = 등록 반품배송비(편도)만 보여 줌(정산 왕복·초도 값 아님) · 업체직송 송장·빠른 완료는 편도 신호 아님(nicoable 5건 반례) · 파일 대조 `부분8\보관_반품\보관_반품_보고.md`(2025 결제 34건 제외 153건 중 R1 136 일치).
- 버린 대안: 빠른 완료(접수 후 1시간 안)를 편도 신호로 씀(15건 중 8건 반례) · tellace83 2026-04 신청값 추정(화면 90일만 · 스냅숏 없음).
- 영향 범위: 산식 엑셀 4(부분 1 → 0 · 산식 121항목 부분·미확정 0) · 새 할 일 T-118(반품 접수채널 수집) · 예상값 코드 후속.
- 상태: ACTIVE

### D-334 [SETTLE_DATA_COMPLETE] 정산 미확정 항목에 필요한 자료는 지금 없으면 모두 받는다 (2026-11-18, R238)
- 결정(소유자 2026-11-18 원문): "미확정건은 현재 자료가 없으면 모두 받아야 됨"
- 적용: 정산식 미확정 52항목(`D:\coupang-analytics\output\_점검_261118_정산항목체크\정산식_확정_미확정_대응_1118.md` G1~G5)과 확정 항목 중 '자료 빠짐'(46·47·48·53)에 필요한 자료를 전부 받기 대상으로 둔다 — 받는 목록 = 정산 자료 등록표(`settlement_sources.SOURCES` · D-322)에 추가 · 진행률 = `정산자료_수집진행률_1118.md`. 로그인·2차 인증은 소유자, 화면 읽기 규칙(D-273·D-276·D-277)·프록시 금지 그대로.
- 근거: 소유자 원문(위) · 미확정 원인 중 G2(자료 부족 16항목)는 자료만 있으면 식으로 확정 가능(대응표).
- 버린 대안: 원문 값 + 경고 표시로만 운용(예상값 정확도가 오르지 않음).
- 영향 범위: 정산 받기 코드(레인 E·정산 코드 D-233) · T-82·T-51·T-77·T-93·T-94·T-100·T-118 · 새 할 일 T-122.
- 상태: ACTIVE

### D-335 [SETTLE_DATA_KEEP] 이미 받은 정산 자료를 다음날 수집이 덮어써 전날 자료가 사라지면 안 된다 — 수집마다 날짜별 보관 (2026-11-18, R238)
- 결정(소유자 2026-11-18 원문): "이미 받은 자료에 다음날 업데이트해서 전날 자료가 없어지는 것은 방지 해야 함."
- 적용: 같은 파일명에 덮어쓰는 정산 자료(스냅샷·예정 줄·지급 내역·광고 일별 등)는 덮어쓰기 전 값을 수집일별로 남긴다(삭제 금지 · 같은 내용이면 중복 보관 생략 가능). 어느 파일이 덮어쓰는지는 조사표(`정산자료_수집진행률_1118.md` 덮어쓰기 표)로 확정 후 코드 반영.
- 근거: 소유자 원문(위) · 예정 금액은 지급 전 값이 바뀜(D-279 '최신 스냅샷' · ljung0622 10-19~25 30% 66,692→90,131 실측 settlement_ledger.py rg_window_overlap 주석) — 전날 값이 없으면 예상값 정확도·바뀐 이유를 확인할 수 없음.
- 버린 대안: 최신 값만 유지.
- 영향 범위: 정산 받기·저장 코드(정산 코드 D-233) · output 용량(T-109 내보내기 도구) · 새 할 일 T-123.
- 상태: ACTIVE

### D-336 [SETTLE_FORMULA_APPLY] 지금까지 검증한 정산 산식을 앱에 반영한다 (2026-11-18, R238)
- 결정(소유자 2026-11-18 원문): "그리고 지금까지 검증한 정산 산식을 앱에 반영하야 함."
- 적용: 산식 엑셀 7차(`D:\coupang-analytics\output\_조사_261117_쿠팡수수료산출\쿠팡정산_항목_산식_자료.xlsx`)의 확정 47항목 식 + 미확정 항목의 경고 표시(회차 미확정·묶음 수량 미확정 등)를 정산서 계산 코드에 넣는다. 먼저 항목별 '앱 반영됨/안 됨' 대조표를 만들고, 안 된 것만 시험 먼저 → 코드. 이미 묶인 할 일 = T-121(D-331~D-333 예상값) · T-38(24 이중 차감·19·신규-17) · T-63/T-73(신규-23) · T-116(74 연결).
- 근거: 소유자 원문(위) · 11-18 점검 = 확정 식 중 앱 미반영 24·74·45·76·신규-03·신규-23 확인(`정산식_확정_미확정_대응_1118.md`).
- 버린 대안: 항목마다 따로 반영(대조표 없이) — 빠짐 확인 불가.
- 영향 범위: 정산 코드만(D-233) · 결과 맞추기 하드코딩 금지(D-229) · 11-03 정산서 재발행(T-72 · 소유자) · 새 할 일 T-124.
- 상태: ACTIVE

### D-337 [COMPANY_STOCK_OPTION_FORMAT] 재고 현황 새 양식(한다로지넷 실재고현황) 읽기 — 첫 시트·현재고(=가용재고)·옵션명 있으면 '옵션명 수량' (2026-11-18, R238)
- 결정(소유자 2026-11-18 원문): "재고 현황 파일이 변동 되었어, 파일에서 첫번째 시트를 활용해야 하고, 재고는 "현재고" 값을 사용해야 함, 그리고 "옵션명"에 값이 있는 경우에는 옵션명 + 가용재고를 표기(예시, 화이트 31)".
- 적용(`company_stock`): ① 읽을 탭 = 첫 시트(D-183 그대로). ② 머리글은 이름으로 찾음 — 수량 칸 우선순위 '현재고' → '가용재고' → '총입고수량'(새 시트에는 '현재고' 칸이 없고 '가용재고'뿐이라 가용재고를 씀) · '옵션명' 칸이 있으면 읽음. ③ 표기 = 옵션 없음('-'·빈칸) '창고 , 수량개'(옛 표기 그대로) · 옵션 있음 '창고 , 화이트 31 / 블랙 97'(옵션별 나열·합산 안 함 — 그로스 재고 '라벨 값 / 라벨 값' D-047·D-048 과 같은 방식) · 같은 창고에 옵션 줄과 '-' 줄이 섞이면 '-' 조각은 수량만('화이트 0 / 0') · 여러 창고는 지금처럼 ' / ' 로 이어 씀. ④ 머리글 위 안내 줄 '상품명 앞에 K가 붙은 것 : 3PL김포' 를 읽어 그 창고 줄의 상품명 앞 'K' 를 뗀다(안내 줄이 없으면 이름 그대로). ⑤ 옛 양식 2가지(D-141 '상품명·현재고' · 팔래트 '제품명·총입고수량')도 계속 읽음 · 수량 칸 이름을 모르면 ❌ 멈춤(폴백 없음). ⑥ 앱이 쓴 옵션 표기도 '앱 값'으로 알아봄(다음 실행에 사람 메모로 남지 않게 · D-156).
- 근거(실측 11-18·조회만): 재고 시트 탭 = ① '한다로지넷 실재고현황'(383행·6칸: 창고·상품명·옵션명·가용재고·옵션코드·바코드번호 · 4행 머리글 · '현재고' 글자 칸 0) ② 재고현황 ③ 재고현황 1022기준(참고용) ④ 건기식_260929(대략). 옛 코드 = "헤더를 찾지 못함" 으로 실패(재현 = 시험 R21e 수정 전 실패). 3PL김포 148품목 전부 이름이 'K' 로 시작 · 3PL인천 43품목 중 0 · K 를 떼면 20품목이 두 창고에 같이 있음(예 '가습기 HJ093' 김포 96·인천 810) → 안 떼면 대장 상품명과 완전 일치하는 인천 재고만 붙고 김포 재고가 빠짐. 새 코드로 실제 시트 읽기 = 379줄 → 170품목(두 창고 21·옵션 92·음수 경고 2: 헬스매트 HM001 퍼플 -3 · 공기압주입기 KS001 -1) · 관리대장 미리보기(쓰기·AI 없음) = 상품명 일치 42줄 · AI 판정 대상 91줄.
- 버린 대안: 옵션 수량 합산해 '창고 , 128개'(소유자 '옵션명 + 가용재고' 표기와 다름) · 옵션마다 '(화이트) 3PL김포 , 31개'(소유자 예시 '화이트 31' 과 다름) · K 를 떼지 않고 AI 매칭에 맡김(같은 상품 두 창고 중 하나만 고름 → 재고 누락).
- 영향 범위: `src/coupang_analytics/company_stock.py`(_stock_columns·_prefix_marks 신설·read_stock·stock_text·_auto_written) · `tools/verify_registry_offline.py` R21e · `docs/CURRENT_RULES.md` 5절. 관리대장 역기록(push_company_stock)·계정목록 회사보유재고 표기(inject_company_stock) 둘 다 같은 함수. 저장된 AI 판정(`output/_회사재고매칭.json` · 이 PC 기준 재고 이름 3종 중 2종이 새 시트에 그대로 있음)은 고른 이름이 새 시트에 없으면 다시 판정(D-157 그대로). HQ 포팅 대상.
- 상태: ACTIVE

### D-339 [SETTLE_FETCH_RETRY] 다시받을목록에 오른 정산 자료는 앱이 자동으로 다시 받는다 (2026-11-18, R238)
- 결정(소유자 2026-11-18 선택 원문): "자동으로 다시 받기 (추천)" — 질문 = D-321 '자동 재요청 없음' 때문에 빈 파일(라이브정산 2026-02 등)·광고 subtotals 빠진 540파일이 영원히 다시 안 받아짐 → 다시받을목록에 오른 것을 자동으로 다시 받을지.
- 적용: 정산 실행이 `다시받을목록.csv` 의 빈 파일·필요분(광고 subtotals = T-90 필요분)을 다음 실행에서 자동으로 다시 받는다 · 한 회차 개수 상한·차단 간격·로그인 규칙 그대로 · 다시 받아도 같은 결과(머리줄만 등)면 반복하지 않고 '확인 필요'로 남김(D-321 버린 대안의 무한 반복 우려 대응) · 받은 기록에 올라 다시 안 받던 빈 파일도 대상.
- 근거: 소유자 선택(위) · T-122 인계 `D:\coupang-analytics\output\_점검_261118_정산항목체크\T122_인계.md` 3절 2번(빈 라이브정산 2026-02 = 받은 기록에 있어 영원히 재요청 안 됨 · `_광고_다시받기.json` 을 앱이 만들지 않음).
- 버린 대안: 목록만 남기고 사람이 지시할 때만 받기(D-321 그대로).
- 영향 범위: `settlement_fetch_check.py` · `tools\settlement_download.py` · T-82 · T-90 · T-122. D-321 부분 대체.
- 상태: ACTIVE

### D-340 [WING_SCREEN_VIEW_BUTTON] 윙 화면의 조회 전용 버튼(검색·팝업 열기·'구독 관리' 보기 등)은 앱이 눌러도 됨 — 동의·신청·저장·'보고서 만들기'·상품 수정 화면은 계속 금지 (2026-11-18, R238)
- 결정(소유자 2026-11-18 선택 원문): "조회 버튼 허용 (추천)" — 질문 = 반품 접수채널·반출 박스 유형·매출내역 상세·비즈니스 인사이트 4종을 받으려면 '검색'·팝업·'구독 관리' 같은 조회만 하는 버튼이 필요.
- 적용: 화면을 바꾸기만 하고 아무것도 저장·신청·변경하지 않는 조회 버튼은 앱이 누를 수 있다 · 페이지 안 스크립트·API 직접 호출 금지(D-296 화면 응답 기록 방식) · 로그인·2차 인증 = 소유자 · 첫 실제 시험 = 소유자 로그인 한 계정 1회 · 버튼이 조회 전용인지 애매하면 누르지 않고 확인 필요.
- 근거: 소유자 선택(위) · `D:\coupang-analytics\output\_점검_261118_정산항목체크\T122_자료16종_화면근거_1118.md`(7·12·13·17번).
- 버린 대안: 4종 원문 값 + 경고만 유지.
- 영향 범위: 윙 화면 규칙 D-273·D-276·D-277 에 조회 버튼 허용을 더함(금지 목록 그대로 · 세 항목 상태 그대로) · T-118 · T-122 · CURRENT_RULES 12절.
- 상태: ACTIVE

### D-341 [SETTLE_DATA_KEEP] 상품조회 원문을 통째로 날짜별 보관 (2026-11-18, R238)
- 결정(소유자 2026-11-18 선택 원문): "원문 통째 보관" — 질문 = 상품조회 원문 통째 날짜별 보관(1년 약 1.2GB 추가 · 정산 칸은 이미 날짜별 보관 R233).
- 적용: 상품조회(_raw) 원문을 D-335 와 같은 방식(수집일별 보관 · 같은 내용 생략)으로 남긴다.
- 근거: 소유자 선택(위) · T-123 보고(용량 추정 · `product_info` 정산 칸 날짜별 보관 · 시험 verify_product_info_offline S5).
- 버린 대안: 정산에 필요한 칸만 보관(지금 방식).
- 영향 범위: 상품조회 저장 코드 · output 용량(D-335 약 3GB/년 + 1.2GB) · T-122.
- 상태: ACTIVE

### D-342 [DEDUCTION_SCOPE_2026] 공제 관리 몫의 자료 창 시작 = max(관리 시작 달, 2026-01) — 밀크런 '시작 전달부터'(D-154)도 2025 달은 넣지 않음 (2026-11-18, R238)
- 결정(통제 세션 판단 · D-288 정산금액 차이 0 기준 · D-311): D-328·D-329 로 2025 판매 줄을 공제까지 통째 뺀 뒤에는, 위탁정산서 관리 몫 공제(광고·밀크런 등 상품 구분 없는 공제)를 나눌 자료 창을 max(관리 시작 달 D-185, 2026-01)부터 잡는다. 밀크런의 '관리 시작 전달부터'(D-154)는 그 전달이 2025년이면 적용하지 않는다(안 (나)). 관리 시작 표시(D-185)는 그대로.
- 근거: T-124 진단(11-15 자료 · ljung0622 · `D:\coupang-analytics\output\_점검_261118_정산항목체크\T124_표본_전후_1118.md` 끝 절) — 4f73c86 뒤 관리 첫 판매 달이 2025-11 → 2026-01 로 밀려 D-186 '판매 0인 달' 경로로 2025-10~12 관리 광고 2,243,953 · 밀크런 353,348 이 2026 줄 공제 위에 통째 더해짐(관리 공제 −1,107,577 의 원인 · D-329 불일치) · 2025-12 밀크런은 이미 빠진 2025 줄에서 공제됨 → 안 (나) 2026-01부터 = 관리 밀크런 953,447 이 계정 공제 D(2026-01 이후 밀크런 합 2,051,220 중 관리 몫)와 원 단위로 맞음 · 안 (가) 2025-12 포함 = 1,178,054(남은 줄에 없는 비용을 관리에 매김).
- 버린 대안: (가) D-154 그대로 2025-12 포함 · 지금 새 코드(2025-10~12 공제 통째 더함) · 옛 코드(2025 자료 섞인 평균 비율).
- 영향 범위: 위탁정산서 관리 몫 공제(`settlement_managed_alloc` 계열 · T-124 브랜치 `claude/admiring-benz-75094e`) · 2025년에 관리하던 계정의 관리 공제(ljung0622 약 −2.6~−2.8백만 추정 · 고친 뒤 실측) · D-154 부분 대체.
- 상태: ACTIVE

### D-343 [STATEMENT_FIXED_FORMAT] 위탁자 정산서 형식 = 항상 같은 형식 — 항목에 값이 없으면 공란 · 41계정 형식 대조는 하지 않음 (2026-11-18, R238)
- 결정(소유자 2026-11-18 원문): "T-38 위탁자 정산서 새 형식 41계정 전체 대조 ==> 정산서 형식이 가변적이변 안됨, 항상 정산서 포멧은 동일하고 항목에 해당하는 값이 없으면 공란으로 하면 돼. 그러면 대조가 필요없어. 접근 방법이 틀렸어. 다시 검토해줘."
- 적용: 위탁자 정산서(T-38 3차 형식 · `settlement_consignor_*`)의 항목 줄은 계정·달과 상관없이 고정 목록으로 늘 같은 자리에 둔다 · 값이 없으면 공란(0·'이번 기간 없음' 줄 대신) · 계정마다 줄이 생기고 빠지는 방식(지금 `settlement_consignor_month_cost.py` `alloc_pending_costs`·`_breakdowns` 가 금액 있을 때만 줄 추가 · `settlement_consignor_gsheet_pages.py:228` '이번 기간 없음')을 없앤다. 금액 검산(합계가 맞지 않으면 시트를 쓰지 않음 · `settlement_consignor_gsheet.check`)은 그대로 — 정산서마다 만들 때 자동으로 돎.
- 근거: 소유자 원문(위) · 11-18 코드 확인(공통 비용 줄 = 금액 있는 항목만 추가 → 계정마다 형식이 달라져 41계정 대조가 필요했던 것).
- 버린 대안: 가변 형식 유지 + 41계정 전체 대조(T-38 · 3~6시간).
- 영향 범위: T-38(41계정 대조 → 할 일에서 뺌) · 위탁자 정산서 그리기·숫자 모듈 · 고정 항목 목록(산식 121항목의 '정산서에서 더하기/빼기' 칸 기준 · 목록 확정은 구현 세션이 만들어 통제 세션 확인) · 상품 줄 수(계정마다 관리 상품 수가 다름)는 소유자 확인 대기.
- 상태: ACTIVE

### D-344 [RANK_TIME_CAP] ③ 순위 시간 상한 = 두지 않음(현행 유지) (2026-11-18, R238)
- 결정(소유자 2026-11-18 원문): "T-119 순위 시간 상한 : 현행유지"
- 적용: 무인 실행 ③ 반자동 순위에 시각 상한을 넣지 않는다(T-119 후보 안 1 '05:50 멈춤'·안 2 '재고 역기록을 ② 뒤로' 모두 채택 안 함). 순서 = 지금 코드 그대로(③ 오늘 칸 → 재고 역기록 → 빈 칸 재시도 → 지난 칸 보충).
- 근거: 소유자 원문(위) · T-119 후보 메모(통제 세션 노트 `T119_순위시간상한_후보_1118.md`).
- 버린 대안: 안 1 · 안 2.
- 영향 범위: 07:00 예약 작업 강제 종료(T-57 · 운용 PC 제한 13시간 의심)가 그대로면 재고 역기록·재시도·보충이 계속 0회일 수 있음 → T-57(예약 작업 제한 재등록) 이 그 해결 경로 · T-119 할 일 닫음.
- 상태: ACTIVE

### D-345 [STATEMENT_FIXED_FORMAT] 위탁자 정산서 고정 형식 샘플 승인 — 승인된 샘플 모양이 코드 기준 (2026-11-19, R238)
- 결정(소유자 2026-11-19 원문): "샘플 승인." — 샘플 = `D:\coupang-analytics\output\_샘플_261118_고정형식정산서\고정형식_bf0621_202609.pdf`·`고정형식_dalbong1849_202610.pdf`(D-343).
- 적용(샘플에 담긴 형식 · 소유자가 따로 답하지 않은 4건은 통제 세션이 '샘플 그대로'로 판단): 1쪽 ①~⑩·'어디로 갔나요' 4줄 · 2쪽 6 종류별 9줄 · 9 계정 공통 9줄 · 10 별도 입금 2줄 · 11 날짜별 입금 · 값 0 = 공란 · 상품 줄 = 2쪽 남은 자리에 다 들어가면 2쪽, 아니면 전부 3쪽부터(한 쪽 최대 35개 · 회색 줄 함께면 19개 · 넘치면 다음 쪽) · 확정 정산서 큰 카드·6 '끝전' 줄 = 샘플대로 · 29 추가지급·31 추가정산 고정 줄 = 금액 반영 전이라 넣지 않음 · 로켓그로스 리뷰 이벤트(PostPurchase)를 9 '리뷰 이벤트' 줄에 넣음(D-324 ④ · 지금 누락).
- 근거: 소유자 원문(위) · 샘플 보고 `D:\coupang-analytics\output\_샘플_261118_고정형식정산서\T38_고정형식_샘플보고_1118.md`.
- 버린 대안: 상품 줄 늘 3쪽부터(샘플과 다름).
- 영향 범위: T-38 코드 반영(인계 `T38_고정형식_2단계_인계_1119.md` · 같은 폴더) · 위탁자 정산서 그리기·숫자 모듈.
- 상태: ACTIVE (부분 SUPERSEDED by D-349 — 10 별도 입금 고정 줄 2→3 · 추가지급 줄)

### D-346 [MEMORY_GUARD_LOG] 메모리 바닥 대책 = 지금 코드의 같은 경로를 막고, 메모리 사용을 실행 로그에 남김 (2026-11-19, R238)
- 결정(소유자 2026-11-18 원문): "메모리 오류 추정이면, 지금 코드에서 동일하개 발생시킬수있는 것에 대한 대책을 강구 하면 해결돼." · "보고보다 로그에 남겨줘. 야간에 실행되는대 내가알수가 없어."
- 적용: 운용 PC 숫자를 기다리지 않고 ① 바퀴 끝 정산 집계가 정산 프로세스에 메모리를 남기지 않게(분리·계정별) ② finally 의 MemoryError 가 오류 창·자기 종료 실패로 이어지지 않게(기록은 남김 · 폴백 금지) ③ 정산 바퀴 사이 자기 프로필 잔여 Chrome 정리 ④ 정산·앱 무인 실행 단계 경계마다 `[메모리]` 줄(프로세스·PC 사용 가능·Chrome 수·합계) · 기준선 넘으면 `⚠메모리` · [실행 결과 종합]에 그날 최고·⚠ 횟수.
- 근거: 소유자 원문(위) · 원인 분석 `D:\coupang-analytics\output\_분석_261118_output39\보고_C_원인분석.md`(집계 1.37GB·끝나도 900MB · 잔여 Chrome 207 · MemoryError 2회).
- 버린 대안: 운용 PC 메모리 숫자를 받은 뒤 원인 확정 후 수정 · 큰 할당 경로를 보고서로만 받기.
- 영향 범위: T-113(하위 세션 t113-memory-guard) · 정산 다운로드 · 앱 무인 실행 로그(`pipeline_stages.py` 등 로그 한 줄).
- 상태: ACTIVE

### D-347 [STATEMENT_FIXED_FORMAT] 고정 형식 정산서 세부 통제 판단 — 상품 표시 없는 광고비 = 9 '그 밖의 쿠팡 공제' · 6 종류 합 ≠ 합계면 차이를 마지막 줄 + 확인 필요 문장 (2026-11-19, R239)
- 결정(통제 세션 판단 · D-288 · D-345 범위 안 세부 · 정산금액 영향 0 = 줄 위치·표시만): ① '광고비 중 쿠팡이 상품을 표시하지 않은 금액'(cat ad)은 9 계정 공통의 '그 밖의 쿠팡 공제' 줄에 넣는다(고정 '상품 표시 없는 창고·운송·보상 비용' 줄은 산식 43~50·55·59·60 물류 항목이라 광고 61·62 와 맞지 않음). ② 6 창고·배송비 종류별 줄 합이 1쪽 6 합계와 1원 이상 다르면 차이를 종류별 내역 마지막 줄에 넣고 judgments 에 '확인 필요' 문장을 남긴다(숨기지 않음 · 폴백 금지).
- 근거: T-38 코드 반영 세션 보고(커밋 `ed7f388` · 승인 샘플 행 비교 차이 0 · 실자료 6건 금액 같음) · 샘플 자료엔 ①에 해당하는 금액 없음.
- 버린 대안: ① 광고비를 '상품 표시 없는' 물류 줄에 넣음(이름만 맞춤 · 항목 성격 다름).
- 영향 범위: `settlement_consignor_month_out.py`·`settlement_consignor_gsheet_fixed.py`(master `b31eb00`).
- 상태: ACTIVE

### D-348 [MEMORY_GUARD_LOG] 정산·앱 프로그램 맨 위 OPENBLAS_NUM_THREADS=1 — openpyxl 이 부르는 numpy(OpenBLAS) 메모리 약 684MB → 18MB (2026-11-19, R239)
- 결정(통제 세션 승인 · D-346 범위 '지금 코드에서 같은 메모리 바닥을 만들 경로를 막음'): `tools/settlement_download.py`·`ui/app_qt.py` 맨 위(numpy 를 부를 수 있는 import 보다 먼저)에 `os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")`. 배포본에서 numpy 빼기(spec 제외)는 쓰는 곳 확인 전이라 하지 않음.
- 근거: T-113 실측(이 노트북) — `import openpyxl` 하나로 커밋 9→703MB · `import numpy` 9→693MB · OPENBLAS_NUM_THREADS=1 이면 9→18MB(스레드 22개 · 버퍼가 스레드 수에 비례) · 배포에 numpy 포함(`dist\coupang-analytics\_internal
umpy`) · 우리 코드는 numpy 를 직접 안 씀 · 정산 바퀴 끝 '남는 900MB'의 대부분 후보(추정 · 측정 대기).
- 버린 대안: spec 에서 numpy 제외(지금은 위험) · 그대로 둠.
- 영향 범위: T-113 이어서(카드 task_33327774) · 배포 때 exe 에서 커밋 MB 확인.
- 상태: ACTIVE
### D-349 [STATEMENT_FIXED_FORMAT] 위탁자 정산서 10 별도 입금에 '추가지급 (관리 상품 몫)' 고정 줄 추가 — 쿠팡 추가지급을 정산금액에 넣음 (2026-11-19, R241)
- 결정(소유자 2026-11-19 원문 — 질문 '10번 별도 입금에 줄을 하나 더해 넣을까요?' 답): "줄 추가 (추천)". ① 10 고정 줄 2→3(우대수수료 2줄 + '추가지급 (관리 상품 몫)' · 값 없으면 공란 D-343) ② 1쪽 10 이름 '별도 입금 (우대수수료 환급·추가지급)' ③ 금액 = 추가지급 메뉴 PAID finalRewardAmount(보류 해제와 따로 D-308 ①) · 정산서 달 = 지급일 달 · 관리 몫 = `settlement_managed_alloc.vid_share`(옛 엑셀과 같음) · 날짜별 표 '쿠팡 추가지급'(지급일 없음·기준일 뒤 = '(지급일 미정)' D-294 ②).
- 근거: 새 정산서가 추가지급을 '이번 계산에 안 넣음'으로만 남김(`settlement_consignor_month_cost.py:448` · D-236 쿠팡 자료 전부 반영과 어긋남 · 현황표 `output\_점검_261118_정산항목체크\정산식_미반영_현황_1119.md` ① 29·31) · 승인 형식(D-345)에 맞는 줄 없음(8 = 재고 보상 · 10 = 우대수수료 2줄) · 실자료 roum0502 2026-10-22 16,897 · freewin7777 2026-11-13 117,960(PAID).
- 버린 대안: 넣지 않음(지금처럼 확인 필요 문장만 · 정산금액 빠짐) · 9 그 밖의 공제에 섞음(입금이라 부호·성격 다름).
- 영향 범위: T-125 A1(`settlement_consignor_month_cost.py`·`settlement_consignor_gsheet_fixed.py` FIXED_ROWS·형식 시험) · 옛 엑셀 위탁정산서 = '참고 별도 입금'에 이미 표시라 그대로.
- 상태: ACTIVE

### D-350 [SETTLE_EXPECT_VALUES] 쿠팡 정산 줄이 아직 없는 기간 = 우리 산식 예상 금액을 '정산 예정(쿠팡 미확정)'으로 정산서에 넣음 — 다음 정산서에 실제와 차이 한 줄 (2026-11-19, R241)
- 결정(소유자 2026-11-19 원문 — 질문 '쿠팡 정산 줄이 아직 없는 최근 판매분을 어떻게 적을까요?' 답): "예상 금액 넣기 (추천)". 윙 구매확정 전·로켓그로스 예정 줄 전 등 쿠팡 줄이 없는 기간은 확정한 산식(D-279 ③·D-336 · 산식 엑셀 7차)으로 예상 금액을 만들어 넣고 늘 '정산 예정(쿠팡 미확정)'으로 확정 금액과 구분한다. 쿠팡 줄이 생기면 쿠팡 값(D-279 ①) · 넣은 예상값은 예상 대 실제 표에 고정 저장 → 실제값 오면 다음 정산서에 차이 한 줄(D-264·D-266). 예상값 입력이 앱에 없으면 숫자 없이 '입력 없음 → 예상값 미확정'(T-121 그대로). '추정' 낱말은 쓰지 않음(D-153 표시 원칙).
- 근거: 정산서 목적 = 쿠팡이 정산하기 전에 예상 정산 금액을 위탁자에게 알림(D-268) · 현황표(`정산식_미반영_현황_1119.md`) F 20칸(D-081·D-146 이 막는 '줄 없는 기간 금액' 19 + D-147 1)·③ 경고 문구 대부분이 이 충돌에 걸림 · 이미 쓰는 비율 배분(D-153)·차이 정정(D-264) 틀 있음.
- 버린 대안: 쿠팡 숫자만(지금 방식 · 20칸 '안 함' 확정 · 위탁자가 들어올 돈을 미리 모름).
- 영향 범위: D-081·D-146 부분 대체(쿠팡 줄 없는 기간만 · 자료가 아예 없는 공제·계정 = 그대로 '자료 없음'·'확인 필요') · 구현 = T-126(현황표 F 20칸 + 예상값에 붙는 경고 문구 D-285·D-289·D-309·D-317) · CURRENT_RULES 13절.
- 상태: ACTIVE
### D-351 [SETTLE_ACCURACY_TARGET] 정산 정확도 목표 = 예상값까지 100% · 쿠팡이 확정한 정산은 전체 대조하지 않음(41계정 전체 대조 보류) (2026-11-19, R241)
- 결정(소유자 2026-11-19 원문): ① "전체 대조는 불합리함, 이미 쿠팡에서 정산을 확정한 건은 대조할것이 없음. 보류함" ② "몇일동안 로그인해서 장산 산식을 모두 도출했어, 이렇게 한것은 100% 목표로 한것임." — ① 지급이 끝난(쿠팡 확정) 정산은 쿠팡 원문 값 그대로라 41계정 전체 대조 실행을 하지 않는다(T-124 남은 'T-38 41계정 대조' 포함 보류). ② 예상값(D-350)도 목표는 100% — '쿠팡이 정함·데이터로 못 가름'을 이유로 미확정 표시로 끝내지 않고, 도출한 산식을 지급 끝난 과거 달로 되돌려 계산해 오차 0 을 확인하고, 오차가 남는 항목(G1 줄 배정·지급일 등)은 원인 자료를 더 찾아 규칙으로 만든다. 그 전까지만 '쿠팡 미확정' 표시 + 다음 정산서 차이 한 줄(D-264).
- 근거: 소유자 화면 확인으로 도출한 산식 121항목(엑셀 7차 · D-330~D-333 등) · 현황표 `output\_점검_261118_정산항목체크\정산식_미반영_현황_1119.md` · G1 19항목 = 금액(달 합)은 원문·산식으로 맞고 남은 것은 어느 줄·날짜에 붙는지(`정산식_확정_미확정_대응_1118.md` G1 절).
- 버린 대안: 41계정 전체 대조 야간 1회(Claude 제안 · 확정분은 쿠팡 값이라 의미 없음) · 'G1 은 100% 불가 → 다음 달 정정으로 대신'(Claude 제안 · 소유자 목표와 다름).
- 영향 범위: T-126(D-350 예상값 구현 = 과거 달 되돌림 측정 먼저 · 항목별 오차 0 목표) · T-124 남은 일에서 41계정 대조 제외.
- 상태: ACTIVE

### D-352 [GATE_SPEED] 커밋 때 빠른 검사에서 시뮬레이션 제외(푸시 전체 검사에서만) · 세션 중 문서 커밋은 모아서 (2026-11-19, R241)
- 결정(소유자 2026-11-19 원문): "G2·G3 승인" — G3 = `tools/run_checks.py` CHECKS 의 시뮬레이션(`tools/simulate_pipeline.py`) quick=False(pre-commit `--quick` 에서 빠지고 pre-push 전체 32종에는 그대로) · G2 = STATE·DECISIONS 같은 문서 커밋을 세션 중 여러 번 나누지 않고 모아서(Claude 작업 방식). G1(문서만 바뀐 커밋 게이트 생략)은 승인 안 됨 → 그대로.
- 근거: 11-19 실측 — 문서만 바꾼 커밋마다 빠른 검사 31종 147~255초 + 푸시 전체 155~203초 · 그중 시뮬레이션 단독 147~242초(가장 긴 검사) · 통과 기록(D-180)이 저장소 전체 내용 기준이라 STATE 한 줄도 다시 검사.
- 버린 대안: G1 문서 커밋 게이트 생략(소유자 미승인) · 시뮬레이션을 아예 빼기(회귀망 약화 · D-202).
- 영향 범위: `tools/run_checks.py:40` · pre-push 는 그대로 전체 · CLAUDE.md '구성' 설명은 전체 기준이라 그대로.
- 상태: ACTIVE

### D-353 [SETTLE_SAMPLE_BATCH] 정산 표본 전후 계산 = 수정마다 하지 않고 묶어서 · 읽은 자료 저장(S1 캐시)으로 원인 가르기 (2026-11-19, R241)
- 결정(소유자 2026-11-19 원문): "정산 표본 계산은 매번 하지 말고 수정건이 쌓였을때 모아서 하자." → 통제 조건 제시 뒤 "그 조건으로 진행하고 S1도 T-125 끝나면 시작해줘.(별도 세션)". ① 정산 코드 수정마다 시험·게이트는 그대로(병합 = 시험+게이트 통과) ② 표본 전후(옛 코드 vs 새 코드 · 실제 자료)는 묶어서 — 위탁자 정산서 발행 전 반드시 1회, 그 전이라도 금액이 바뀌는 수정 3건 쌓이면 1회 ③ 금액이 바뀌면 S1 저장 자료로 수정 건별 다시 돌려 원인 가름 ④ 표본 기준: 금액 계산이 바뀌는 수정만 대상 · 문구·표시만 = 시험 + 새 코드 1회(소유자 "표본 기준 그대로 진행") ⑤ S1 = 계정별로 읽어 정리한 정산 자료를 이 PC 에 계산용 복사본(캐시)으로 저장 · 원래 정산 파일이 바뀌면 자동으로 다시 읽음 · DB 아님(정산서·앱은 안 씀 · 표본·시험 도구만).
- 근거: 11-19 실측 — 계정 1~2개 표본도 자료 읽기 수십 분 × 전후 2회 · T-121 이 저장 자료(pkl)로 다시 돌린 수정 표본은 수정·표본·게이트 십여 분 · T-124 표본이 ljung0622 공제 −1,107,577 오류를 잡은 사례(표본 자체는 필요).
- 버린 대안: 수정마다 표본(시간) · 표본 없앰(회귀 위험 · D-202).
- 영향 범위: T-125(A1 표본 = 다음 묶음) · T-127 S1 도구(별도 세션 · T-125 뒤) · 하위 세션 브리프.
- 상태: ACTIVE

### D-354 [SETTLE_MANUAL_START] 정산 탭 '정산 시작' = 이번 회차 '완료' 기록·①판매수집 완료 대기 없이 바로 받음(①이 도는 중이면 대기) (2026-11-19, R241)
- 결정(소유자 2026-11-19 원문): "지금 받아야 할 자료가 많음, 정산시작 버튼 클릭시 진행 되도록 수정해줘." — 정산 탭 버튼만 `watch --manual` 로 띄워 ① D-091 '같은 회차 완료면 끝'을 건너뛰고 ② D-021 '이번 회차 ①판매수집 완료까지 대기'도 건너뜀 · ③ ①판매수집이 지금 도는 중이면(진행 파일 갱신 중) 끝날 때까지 대기(같은 계정 동시 로그인 방지 · 계정별 Chrome 사용 중 대기 D-031 그대로) · 17:55 회차 끝·앱 끄면 함께 종료(D-020)는 그대로. 18:00 무인·전체실행 버튼은 바뀌지 않음.
- 근거: 11-19 11:22 운용 PC(R241) '정산 시작' 로그 "이번 ①판매수집(2026-11-19T07:48:19) 기준 정산은 이미 끝남 … 정산 종료 → 종료" — 버튼을 눌러도 받지 않고 끝남 · 시험 P67(고치기 전 실패 → 통과 · 운용 PC 같은 상황 재현) · P27·P12 그대로 통과.
- 버린 대안: `_완료.json` 을 손으로 지우게 안내(운용 PC 파일 조작) · ①판매수집 재실행으로 새 기준 만들기(전 계정 재로그인).
- 영향 범위: `tools/settlement_download.py`(watch `--manual`) · `src/coupang_analytics/app_process.py` · `ui/settlement_status_panel_qt.py` · D-021·D-091 부분 대체(정산 탭 버튼만) · 배포 zip 재생성 필요.
- 상태: ACTIVE

### D-355 [SETTLE_FORMULA_CONFIRMED] 윙 판매수수료 예상 비율 출처 순서에 '같은 categoryId 의 같은 달 원문(윙·RG · 계정 무관 · 기준일까지 받은 것)'을 categoryId 앞 달 다음·Fee-Table 앞에 넣음 (2026-11-19, R242)
- 결정(D-288 위임 · 통제 세션 확정): D-316 ① 순서 = 옵션 앞 달 → 상품ID 앞 달 → categoryId 표(앞 달) → **같은 categoryId 의 같은 달 원문 비율(윙·RG · 다른 계정 포함 · 기준일까지 끝난 정산주기 자료만 D-282)** → Fee-Table → 상품명 AI → 계정 최빈. 기준일이 달 끝 뒤면 그 달 원문 전부가 들어감(V5b) · 달 중이면 그때까지 끝난 주기만(V5a). 계정·상품 조건 없음(D-229).
- 근거(통제 세션 파일 대조): `D:\coupang-analytics\output\_통제_261119_T96\T96_차이0_원인_보고.md` 2절 · `v5.log` · `v5_출처별.csv` — 같은 categoryId 윙·RG 비율 91/91 같음(`레인C_카테고리ID_비율표.csv` 통제 세션 재계산 91/91) · 새 출처 793/793(V5a)·951/951(V5b) 오차 0 · 215칸 중 나빠진 칸 0 · 8계정 밖 166칸 절대 28,143 → 11,643(V5a)/8,453(V5b) · seankim137 2026-08 +16,500 → 0(9128 판정 7.8 vs 원문 5.8) · nicoable 2026-05 +3,190 → V5b 0(8817 7.8 vs 6.4).
- 버린 대안: 상품명 AI '확신 중간' 칸을 계정 최빈으로 미루기(freewin7777 2칸만 보고 정하면 맞추기용 · 보고서 2-3절).
- 남는 위험(사실): freewin7777 2026-04 −7,755 · 05 −693 = categoryId 모르는 옵션의 상품명 AI 오판(지난 달 자료 없음) → 끝난 달은 원문 값(D-279) · 앞으로는 상품조회 categoryId 보관(T-100). D-316 ① 순서는 앱 코드에 아직 없음 → T-126 예상값 구현 때 이 순서로 넣음.
- 영향 범위: T-126 · D-316 ① 부분 대체(순서에 한 단계 추가) · CURRENT_RULES 12절 · 산식 엑셀 11-2.
- 상태: ACTIVE

### D-356 [STATEMENT_SPLIT] 옛 엑셀 위탁정산서 '관리 상품 입금 내역'의 RG 물류비·재고 보상 줄 나누기 = 줄마다 그 줄 공제가 갚은 정산주기 비용(지급일 전에 끝난 주기 · 오래된 것부터)의 상품별 관리 비율 (2026-11-19, R242)
- 결정(D-288 위임 · 통제 세션 확정): `settlement_statement_deduct.py` `status_split`·`put` 의 LOGI·COMP 는 전 기간 비율 하나(`rates[k]`)를 모든 줄에 곱하지 않고, 줄 공제를 지급일 순으로 그 전에 끝난 정산주기 RG 비용 리포트(상품별 관리/관리 밖)에 오래된 것부터 맞춰 그 줄의 관리 비율을 쓴다. 못 맞춘 몫(원문 자료 시작 전 비용)만 남은 비율 `(Dm − 맞춘 관리 합) / 못 맞춘 합` → 전 기간 관리 몫 합 `Dm` 그대로(계정 합계·검산 표 변화 0) · 남은 비율이 0~1 밖이면 '확인 필요'. 계정 조건 없음(D-229).
- 근거(통제 세션 파일 대조): 같은 보고서 1절 · `w7.log` — WBpeak 관리 밖 상품 RG 비용 = 정산주기 07-26 까지만(07-27 뒤 0원) → 9월 판매 줄 −11,657·10월 판매 지급 끝난 2줄 −5,369 가 현행 방식 차이(관리 입금이 그만큼 큼 · 100원 이상 D-235) · 이 두 달은 관리 밖 비용 0 이라 갚는 순서와 상관없이 새 방식 = 0(사실) · D-294 ①(지급 끝난 줄 = 그 줄 실제 관리 몫) · D-316 ⑤(밀크런 오래된 청구부터 114/131).
- 버린 대안: 줄 판매 달 비율(`by_m` · 8월 +10,471 남음 — 8월 줄이 07-26 주기 관리 밖 반출비를 갚음) · 현행 유지(9·10월 차이).
- 남는 위험(사실): 쿠팡은 어느 공제가 어느 주기 비용을 갚았는지 주지 않음 → 2~8월은 오래된 것부터가 가정 · 6~8월 확정 = RG 정산현황 지급 상세(회차별 물류비 차감·이월 · 소유자 로그인). 보고서 금액은 d0c0ec6 기준 · 현재 master(D-342 창 변경 뒤)는 9월 약 +14,590 추정 → 구현 전에 S1 표본(D-353)으로 현재 master 차이부터 재현. 새 위탁자 정산서(`settlement_consignor_month_cost.py` `logistics`)는 `line_m` 을 안 써서 영향 없음.
- 영향 범위: 정산 코드만(D-233) · `settlement_statement_deduct.py` · 구현 = T-130 · CURRENT_RULES 12절(D-294 줄).
- 상태: SUPERSEDED by D-416 (지급 끝난 줄·리포트 있는 예정 줄·보류 줄) · D-414·D-415 (비용 리포트 없는 예정 줄)

### D-357 [SELDOC_CONTRACTOR_SHEET] 셀독 계약자별 상품 현황 엑셀 — 기준 = 관리대장 계약자(사업자) · '10건 이상' = 쿠팡 계정 단위 · 계약자별 파일 안 만듦 (2026-11-19, R242)
- 결정(소유자 2026-11-19 원문 · 하위 세션 local_570604bd 에서 직접 · 통제 세션이 대화 기록 원문 대조): "대장에 있는 계약자(사업자)가 기준임, 10건 이상 기준은 쿠팡 계정 단위로 해줘.계약자별 파일은 필요 없음." — ① 명단·시트 = 관리대장 사업자(시트 1개 = 사업자 1개 · 제목에 대표자) · 대장에 없는 이름(원본 양식의 김대성)은 빠지고 대장에만 있는 사업자는 들어감 ② '전체 상품 10건 이상이면 개인 상품 중 판매 0건 제외'(소유자 11-19 지시 3)는 쿠팡 계정마다 셈 ③ 파일 하나(요약 시트 + 사업자 시트).
- 근거: 소유자 지시 1~9(11-19 · 이 세션) · 설계 `D:\coupang-analytics\output\_설계_261119_셀독고객별시트\설계안.md`(18시 ① 판매수집이 계정 전체 상품·판매·그로스 재고를 이미 받음 — `collector.py:96-106·286-289·413-417` 통제 세션 확인) · 시안 `셀독_계약자별상품현황_시안.xlsx`(요약 36사업자).
- 버린 대안: 원본 양식 이름(대표자) 기준 32시트 · 계약자 단위 10건 · 계약자별 파일.
- 남은 것(소유자 답 대기 · STATE T-132): 7일 기간 · 개인 상품 판매중만 여부 · 판매가 정의 · 판매자배송 재고 · 파일 이름·위치·보관·구글시트 · 생성 시점 · 링크 없는 상품 · 옵션 접기 · '(사업자)' = 사업자 단위로 읽음(대표자 단위면 송창호 2시트 → 1시트).
- 영향 범위: 새 단계(① 끝 · 로그인 없음 · 구현 = T-132 2단계 · 소유자 남은 답 뒤) · 셀독/개인 구분 = AI 판정 중심 + VID 고정(D-009 · D-107).
- 상태: ACTIVE

### D-358 [SELDOC_CONTRACTOR_SHEET] 셀독 계약자별 상품 현황 — 양식·자료·구글시트 확정(시안 3차 · 남은 질문 전부 제안대로) (2026-11-19, R242)
- 결정(소유자 2026-11-19 원문): 양식 = "이 항목들은 엑셀 포멧에서 삭제 해줘" · "날짜는 최근날짜가 왼쪽순으로" · "그 아래 한 줄(계정 · 기간 · 생성 시각)은 남겼습니다. ==> 삭제 해줘" · "링그 버튼은 왼쪽 상단으로" · "요약 시트도 변경해줘" · "7일합계는 오른쪽 끝으로 이동해줘" · "확인시트, 시안설명 시트는 삭제 해줘" / 남은 질문 = "제안대로 진행해줘".
- 양식(시안 `D:\coupang-analytics\output\_설계_261119_셀독고객별시트\셀독_계약자별상품현황_시안.xlsx` 15:05 = 기준): 시트 = 요약 + 사업자 시트만 · 사업자 시트 = A1 '◀ 요약으로' · 제목(사업자 + 대표자) · 칸 = 구분 · 계정ID · 상품명(쿠팡 링크) · 판매방식 · 판매상태 · 판매가(최저) · 실구매가(즉시할인 후) · 그로스 재고 · 최근 7일 일별(최근이 왼쪽) · 7일 합계(맨 오른쪽) · 셀독 행만 바탕색 · 등록상품 1줄(옵션 합산) · 숫자 요약 칸·설명 줄·옵션·VID·재고 일수·판정 근거·범례 없음 · 요약 = 사업자(링크) · 대표자 · 계정ID · 전체/셀독/개인/개인 0건(뺌) · 7일 판매 셀독/개인/합계 · 셀독 비중 + 합계 줄.
- 제안대로: ① 판매 기간 = 최근 7일 ② 개인 상품 = 판매 중인 것만(셀독 상품은 판매중지도 표시) ③ 판매가 = 판매가 + 즉시할인 후 가격(쿠폰 미반영) ④ 재고 = 그로스만 ⑤ 파일 = `output\계약자별상품현황\셀독_계약자별상품현황_yymmdd.xlsx` 매일 새 파일 ⑥ 생성 = ① 판매수집 직후(밤 8시께 · 로그인 없는 오프라인 단계) ⑦ 로그인 실패·자료 없는 계정 = 요약 사업자 이름 옆 '(로그인 실패)' 같은 짧은 표시 ⑧ 링크 없는 상품(무판매 판매자배송 개인 상품) = 그 상품만 추가 조회 ⑨ 결과 파일 상품 링크 vendorItemId 빈 값도 함께 고침 ⑩ 구글시트 = 안1(설정 탭 '구글 시트 연동'에 5번째 칸 「셀독 계약자별 상품 현황 링크」 · 매일 같은 시트 덮어쓰기 · 날짜별 기록은 PC xlsx · 새 권한 없음 · 실패 = ❌ 로그·상태 표시 후 실행 계속).
- 칸 폭(소유자 2026-11-19 원문 "구글시트에서 항목간 간력으로 조금씩만 넓혀줘. 특히 날짜별 판매건수 부분."): 모든 칸 +2 · 날짜 7칸 9 · 7일 합계 13 · 상품명 50 그대로(요약 7일 판매 3칸 +4) · 폭 표는 한 곳(상수)에 두고 엑셀·구글시트가 같이 씀(구글 = 픽셀 환산 · 매일 덮어쓸 때 폭도 다시 맞춤) · 시안 15:10 이후본이 기준.
- ⚠ 열람 대상(한 파일에 모든 사업자 자료)은 소유자 답이 따로 없음 → 내부용으로 보고 구현 · 계약자에게 공유하려면 다시 결정.
- 판정이 애매한 건·판정 근거 = 엑셀이 아니라 판정표 파일에만(전역 AI 매칭 규칙).
- 근거: 설계안 `D:\coupang-analytics\output\_설계_261119_셀독고객별시트\설계안.md`(2절 자료 출처 · 11절 구글시트 방안 — 설정 링크 4종 `ui/app_qt.py:175-180` · 범위 spreadsheets 만 `gsheet_api.py:25` 통제 세션 확인).
- 버린 대안: 원본 양식 그대로(3일 · 서식 없음) · 구글시트 안2(결과 시트 안 탭 — 이름 충돌·노출) · 안3(드라이브 폴더 새 파일 — drive 권한·OAuth 먼저).
- 영향 범위: 구현 = T-132 2단계(새 모듈 · ① 끝 단계 · 설정 탭 칸 · 상품 링크 vendorItemId) · D-357 보완.
- 상태: ACTIVE (부분 SUPERSEDED by D-361 — ⑥ 생성 시점 = 매일 06:00)

### D-359 [SELDOC_CONTRACTOR_SHEET] 셀독 계약자별 상품 현황 구현 세부 규칙 — 양식 4건 추가 · 구현 판단 6건 (2026-11-19, R242)
- 결정(소유자 2026-11-19 원문 — 양식): "1.색 농도로 진행해줘. 2.요역시트 항목명 1줄 또는 2줄로 해줘. 3.계약자별 시트에서 11.15--> 11.15일로"일" 추가 해줘." · "4. 줄간격 조금 넓혀줘, 계약자별 시트, 요약시트도 같이 해줘." → 데이터 막대 대신 색상 스케일(흰색→연보라 · 구글시트 미지원 서식 제거 · 소유자 캡처 '일부 조건부 서식이 삭제됩니다') · 요약 머리글 최대 2줄 · 날짜 머리글 '11.15일' · 데이터 줄 높이 20pt(엑셀·구글 같은 값).
- 구현 판단(Claude 판단 · 소유자 지시 아님 · 통제 세션 검토 · 설계·D-358 범위 안): ① 셀독 VID = `_매칭결과.json` ∪ `_매칭고정.json` ② 판매중지 옵션 = 대장 VID만(같은 상품명 옵션은 판매중만) ③ 날짜 지정 실행 = 만들지 않음 · 같은 날 다시 실행 = 그날 파일 교체 ④ AI 판정 = 시트에 나올 개인 상품 중 후보(모델코드 겹침 또는 낱말 2개 이상)만 · AI 실패 = 그날 개인 처리·판정표 기록 안 함(다음 실행이 다시 물음) ⑤ ⚠ 구글시트 = 등록한 파일의 탭을 전부 지우고 새로 그림 → **이 기능 전용 빈 구글시트를 등록해야 함**(다른 시트 주소를 넣으면 내용이 지워짐) · 자동 필터는 안 옮겨짐 ⑥ 요약 '개인 상품'·'개인 0건' 칸 폭 11→12.
- 근거: 구현 커밋 `a10375e` · 병합 `5c50fb2` · 검사 `tools/verify_contractor_sheet_offline.py` T1~T8(10건 경계 9/10/11 · 2계정 사업자 · 판정 3단 · 다시 실행 AI 0회 · 양식·칸 폭·링크 · 구글 ⚠/❌/교체 · 데이터 막대 0) · master 빠른 검사 32종 통과 · 복잡도 유지 · 11-17 사본 자료 결과 = 사업자 36 · 셀독 123 · 개인 108(시안과 같음 · 5.6초) · 결과 파일 링크 vendorItemId 빈 값 = 재현 안 됨(7,154 링크 중 빈 값 0 → 고치지 않음 · D-358 ⑨ 해당 없음).
- 버린 대안: 막대 유지 + 구글시트 SPARKLINE 별도 칸(칸 늘어남).
- 남은 위험: 라이브 1회 전(운용 PC) — 링크 추가 조회 로그 · 구글시트 실제 교체 · AI 판정 품질(사본은 PC 대장 26계정뿐).
- 영향 범위: `contractor_sheet*.py` · `contractor_stage.py` · `gsheet_contractor.py` · `pipeline_stages.py` · `pipeline_sales.py` · `product_info.py` · `ui/app_qt.py` 설정 칸 · 배포 zip 필요.
- 상태: ACTIVE (부분 SUPERSEDED by D-360 — 색 농도 없앰)

### D-360 [SELDOC_CONTRACTOR_SHEET] 셀독 계약자별 상품 현황 — 색 농도 전부 없앰(사업자 시트 7일 합계 · 요약 7일 판매 합계·셀독 비중 = 줄 바탕색과 같게) (2026-11-19, R242)
- 결정(소유자 2026-11-19 원문 · 하위 세션 local_9e51b683 에서 직접 · 통제 세션이 대화 기록 대조): "우측 7일합계항목에 보면 바탕색 음영 농도가 다른 항목과 다른데, 동일하게 해줘. 오늘 배포할 시트도동일하게 해야 됨, 통제 세션에도 알려줘." · "요약 시트도 다른 항목과 동일하게 해줘"(같은 세션 · 대화 기록 대조) → 색상 스케일을 모두 빼고 같은 줄의 다른 칸과 같은 바탕(사업자 시트 셀독 줄 연보라 · 개인 줄 흰색 · 요약 줄무늬). 남는 조건부 서식 = 그로스 재고 0 빨강뿐.
- 근거: 코드 `src/coupang_analytics/contractor_sheet_xlsx.py` 사업자 시트 색 농도 1줄 삭제(커밋 `01bd33f` · 병합 `943f8e4`) + 요약 2줄·색 농도 함수·상수 삭제 · `gsheet_contractor.py` 색 농도 옮기기 코드 삭제(쓰는 곳 없음 · SUPPORTED_CF = 값 비교만) · 시험 먼저 바꿔 실패 확인 → 통과(`tools/verify_contractor_sheet_offline.py` · 빠른 검사 32종) · 등록 구글시트는 하위 세션이 같은 모양으로 고침(사업자 시트 33곳 + 요약 · 그라데이션 0개 · 다시 읽어 확인 · `D:\coupang-analytics\output\_결과_261119_계약자시트_output40\보고.md` '추가(11-19)').
- 영향 범위: D-359 양식 4건 ① 대체(색 농도 없음) · 배포 zip R242b.
- 상태: ACTIVE

### D-361 [SELDOC_CONTRACTOR_SHEET] 셀독 계약자별 상품 현황 실행 = 매일 06:00(① 직후 실행 대체) · 최근 7일 = 실행일 전날까지 · 판매 기록 없는 날 = 그 날만 공란 (2026-11-19, R242)
- 결정(소유자 2026-11-19 원문): "1.오전 6시 실행으로 바꾸고 2. … 그런 계정을 '(자료 없음)'으로 표시할지, 한 날 전 기준으로 보여 줄지 정해야 합니다. ==> 값이 없으므로 해당하는 날만 공란 처리하면 됨. 3.같이 배포 파일 만들어줘." — ① 실행 시각 = 매일 06:00(로그인·브라우저 없는 오프라인 작업 · ① 판매수집 직후 실행은 없앰) ② 최근 7일 = 실행일 전날까지(06:00 실행이면 어제 포함) ③ 계정의 어느 날 판매 기록이 아예 없으면(그날 정산 받기 늦음·실패 등) 그 날 칸만 공란 · 판매 0건으로 기록된 날은 지금처럼 '-' · 다른 날·다른 칸은 그대로(계정 전체 '(자료 없음)' 표시나 하루 당기기 안 함).
- 근거(output40 실측 · 통제 세션 확인): 상품·판매가·그로스 재고 = 18:00 ① 끝 19:29 · 전날(11-18) 판매건수 = 18시 정산 받기가 11-19 01:37~02:58 기록(47계정 중 46) · 만드는 시간 엑셀 67.5초(AI 첫 판정 포함) + 구글시트 35.4초 · 06:00 엔 ③ 순위가 돌 수 있으나(11-18 회차 ③ 05:22 · 지난 칸 07:48) 이 작업은 브라우저·로그인 없음(런타임 병렬 금지 대상 아님).
- 버린 대안: 05:00(소유자 06:00 지정) · ① 직후(하루 덜 최신) · 빈 날 계정 전체 '(자료 없음)' · 한 날 당기기.
- 영향 범위: D-358 ⑥(① 직후 생성) 대체 · 구현 = T-132 · 배포 zip R242b.
- 상태: ACTIVE

### D-362 [NIGHTLY_SCHEDULE] 야간 일정 = 01:30 시작(①②③ + 정산 받기) · 정산 회차 01:30~다음 날 01:20 · 판매 다시 받기 없음 · ③ 오전 실행 허용 · 순위 3일 간격 → 격일(체험단 제외) · 계약자 현황 06:00 따로 (2026-11-19, R242 · 구현 전)
- 결정(소유자 2026-11-19 원문): "1.시작 시각: … ==> 1:30분에 시작, 판매 1번 더 받기는 없음. 2.순위는 허용, 다만 전에 3일간격에서 격일 간격으로 노출 순위 조사, 체험단 건은 제외함. 3.계약자 현황은 06시 따로 실행. 4.정산: … ==> 1: 30분에 시작해서 다음날 1:20분까지 실행됨." (앞 요청: "시작 시점을 24시로하고 판매분석, 노출 순위, 정산 데이타 다운로드를 하고, 오전 6시에 계약자별 판매 현황 시트 작업을 진행함")
- 적용: ① 무인 실행(①판매수집 → ②키워드 → ③순위)과 정산 받기 = 매일 01:30 시작(예약 작업 · 앱 안 회차) ② 정산 회차 = 01:30 ~ 다음 날 01:20(지금 18:00~17:55 대체 · 다 받으면 끝나는 방식 D-021 은 유지로 읽음 — 소유자 확인 대상) ③ 자정 직후 판매 자료 대책 = 01:30 시작으로 대신 · 판매 1번 더 받기 없음 ④ ③ 순위가 오전·낮에 도는 것 허용 ⑤ 순위 조사 간격: 체험단 아닌 상품 = 계정 묶음 3일 간격 → **격일**(D-257 '그 밖은 계정 3묶음 3일 간격' 대체) · 체험단 상품 = 지금 규칙 그대로(시작일 포함 10일 매일 D-257) ⑥ 셀독 계약자별 현황 = 06:00 따로(D-361 그대로).
- 근거: 계획 `D:\coupang-analytics\output\_설계_261119_24시시작\수정계획.md`(시각 = `settlement_watch.py:34-35` 회차 상수 · `deploy/install.ps1:198` 예약 작업 · `transfer_login.py:29-30` 셀독전환 · 날짜 칸은 시작 날짜로 계산 = 코드 변경 없음 — 통제 세션 확인) · 판매 자료 = 전날 하루치가 밤 01~02시 수집값과 18시 재수집값 46계정 중 1계정 1개 차이(11-17 · output39↔40).
- 버린 대안: 00:00 시작(쿠팡 전날 자료 생성 전 위험 · 가장 이른 기록 01:37) · 00:00 + 판매 다시 받기 · 18:00 유지.
- 남은 소유자 결정(STATE T-133): 날짜 칸 = 실행일(권장 · 코드 변경 없음) / 판매일 · 지난 칸 채우기 상한 · 바꾸는 날 빠지는 칸 처리 · 셀독전환 정산 멈춤·조용한 시간(01:10 · 01:10~04:10 꼴) · 정산 '다 받으면 끝' 유지 여부.
- 영향 범위(대체 예정 — 구현 커밋에서 상태 표기): D-021 전체 · D-257(3일 간격만) · D-187·D-179②·D-170·D-091·D-020·D-344·D-199·D-242 시각 문구 · `docs/OPERATIONS_POLICY.md` 무인 18:00 · 구현 = T-133.
- 상태: ACTIVE (구현 R243 `7049a41`(T-133) · 부분 SUPERSEDED by D-372 — 시작 01:30 → 00:10 · 정산 회차 01:30~다음 날 01:20 → 00:10~그날 24:00 · 부분 SUPERSEDED by D-374 — '다시 받기 없음'의 예외 = 노출·방문자 두 줄 08:00 아침 보충)

### D-363 [SETTLE_EVIDENCE_AUTO] 정산 증빙 받기 = 자동 정산 받기 회차에 합침(매일 무인 · 이어받기) — 사람이 낮에 누르는 배치만으로 받던 방식 보완 (2026-11-19, R242 · 구현 전)
- 결정(소유자 2026-11-19 원문): "그러면 장산 파일 다운받는것이 너무 시일이 오래 걸려, 대안 제시해줘." → (통제 세션 대안 A = 매일 회차 정산 받기가 계정마다 로그인해 있을 때 아직 안 받은 증빙도 이어서 받음 · B = 배치 멈춤 17:30 → 01:10 · C = 범위 줄이기) → "A로 하자."
- 적용: 정산 받기(`정산다운로드.exe watch` 회차)가 그 계정의 정산 자료를 다 받은 뒤 같은 로그인 세션에서 `evidence` 받을 목록(`designs/SETTLEMENT_MODULE.md` §14 · D-067) 중 아직 없는 것을 이어서 받음 · 회차 끝(D-362 01:20 · 지금은 17:55)이면 멈추고 다음 회차에 이어서 · 다 받은 것은 다시 안 받음 · 증빙 저장 위치·원본 규칙(D-061·D-067·D-145·D-149) 그대로 · 사람이 누르는 `deploy\정산증빙_전체받기.bat` 는 남김(급할 때).
- 근거: 같은 계정 동시 로그인 = 계정 프로필 사용 중이면 기다림(`tools/settlement_download.py:206` `_profile_busy`) · 정산 받기는 지금도 ③ 순위와 같은 밤에 함께 돎(11-18 정산 19:30~03:04 · ③ 19:34~05:22) · 증빙 받기 소요 실측 자료 없음(output40 에 증빙 로그 없음 → 운용 PC 로그로 재야 함).
- 버린 대안: B(배치 멈춤 01:10 · 사람 손 필요) · C(범위 줄이기) · 계정 동시 받기(런타임 병렬 금지).
- 영향 범위: 정산 받기 코드(D-233 정산 코드만) · 구현 = T-134 · 01:30 일정(T-133 · `settlement_watch.py` 회차 상수)이 master 에 들어간 뒤 구현.
- 상태: ACTIVE · 구현·병합 `4304e27`(T-134 · 세부 D-365·D-367 · 운용 설치 전)

### D-364 [NIGHTLY_SCHEDULE] 01:30 일정 세부 = 데이터 기준일 권고 승인 · 확인 도구 만들지 않음 · 체험단 S~S+9 그대로 (2026-11-19, R243 · 구현 중)
- 결정(소유자 2026-11-19 원문): "쿠팡 데이타를 기준일 기준으로 명확히 구분해서 가져와야 통계로서 의미가 있음, 데이타 관점에서 어느 시간대에 실행하면 좋은지 너가 제시해줘." → 통제 세션 권고(기준일 D = 전날 달력 하루 · D+1 01:30 일괄 수집 · 판매류 = 날짜 묶음 값이라 새벽이면 확정 · 재고·판매가 = 받는 순간 상태라 D 마감 직후 · 순위 = 측정일 D+1 로 한 날짜 안에서 끝냄) → "너의 권고대로 수정해줘. 이 건은 내일 배포하자. 지금 배포 파일이 완료 되면 수정해줘. 수정시 정확히 분석후 수정해야 함." · 이어서 "1.'01:30이 충분히 늦은지' 1주일 확인 도구를 만듭니다. ==> 구현하지 말것. 2.그대로 '시작일 포함 10일(S~S+9)'로함."
- 적용(D-362 보완): ① 날짜 칸 = 실행일(칸 D+1 · 판매 D · 코드 변경 없음) · 순위 = 측정일로 구분 ② 재고·상품정보 = 파일 이름 그대로 + 내용에 '기준일'(= ① date_to) 칸 · 수집 시각 칸 유지 ③ 셀독전환 정산 멈춤 01:10 · 조용한 시간 01:10~04:10 ④ 정산 '다 받으면 끝'(D-021) 유지 · 회차 01:30~01:20 ⑤ 바꾸는 날 빠지는 칸 = 그날 수동 전체실행(운용 안내) ⑥ 01:30 확인 도구·시작 시각 경고 = 만들지 않음 ⑦ 체험단 순위 = 시작일 포함 10일(S~S+9) 그대로 ⑧ 구현 세부(통제 세션 판단 · 소유자 지시 아님): 순위 격일 = 옛 3묶음 기록 보존 + 격일 시작일·묶음 추가(2기간) · 날짜 지정 실행 기준일 = 그 date_to · `config.py` RANK_NOTE_TEXT 에 '날짜 칸 = 그날 측정 · 판매 = 전날' · 06:00 계약자 현황은 ① 미완료면 ① 끝까지 미룸 · 지난 칸 보충 3일·시간 상한 없음 그대로.
- 근거: 판매분석 같은 날을 01~02시 수집 vs 18시 재수집 = 46계정 중 1계정 1개 차이(11-17 · output39↔40 · 통제 세션 실측) · 11-18 회차 ③ 19:34→05:22(자정 넘김) · 분석 `D:\coupang-analytics\output\_설계_261119_24시시작\분석_1단계.md`(시각 = `settlement_watch.py:34-35` · `transfer_login.py:29-30` · `deploy/install.ps1:198`).
- 버린 대안: 00:00 시작 · 판매 다시 받기 · 1주일 확인 도구(소유자 거부) · 체험단 S+1~S+10.
- 영향 범위: T-133(하위 세션 schedule-0130 구현 중 · 내일 배포) · D-362 보완.
- 상태: ACTIVE (부분 SUPERSEDED by D-368 — ① 날짜 칸 = 실행일 → 판매일 · 부분 SUPERSEDED by D-372 — ③ 셀독전환 멈춤 01:10·조용한 시간 01:10~04:10 → 23:50·23:50~02:50 · ④ 회차 01:30~01:20 → 00:10~24:00)

### D-365 [SETTLE_EVIDENCE_AUTO] 자동 증빙 받기 세부 = 정산 완료 뒤 남은 시간 · 검증·광고 포함 · 회차 끝 40분 전 새 단계 안 함 · 완료 계정도 매달 새 달분 · 같은 단계 2회차 연속 실패 = 확인 필요 (2026-11-19, R243 · 구현 전)
- 결정(소유자 2026-11-19 원문 · 통제 세션 판단 5건에 회신): "B2: 정산이 '완료'된 뒤 남은 시간에만 증빙을 받습니다. ==> 수용" · "자동 증빙에서는 검증 수집·광고 받기를 뺍니다. ==> 포함" · "회차 끝 40분 전부터는 새 단계를 시작하지 않습니다.==> 쉽게 설명해줘" → 설명 뒤 선택 "40분 전 (Recommended)" · "다 받은 계정도 매달 새 달 확정분은 다시 받습니다. ==> 쉽게 설명해줘" → 설명 뒤 선택 "매달 자동으로 받기 (Recommended)" · "같은 단계가 3회차 연속 실패하면 '확인 필요'로 올립니다. ==> 2회차로 변경."
- 적용(D-363 세부): ① 증빙 = 그 회차 정산 받기가 '완료'된 뒤 남은 시간에만(정산이 늘 먼저 · B2) ② 자동 증빙의 '정산 원본' 단계 = 지금 `cmd_evidence` 그대로 검증 수집·광고 받기 포함(뺄 것 아님) ③ 회차 끝(01:20) 40분 전 = 00:40 부터 새 계정·새 단계 시작 안 함(시험으로 고정) · 남은 것 = 다음 회차 이어서 ④ `_수집완료.json` 완료 계정도 매달 1일이 지나면 다시 대상(이미 받은 파일은 다시 요청 안 함 · 새 확정 달 몫만) ⑤ 같은 단계가 2회차 연속 실패 = '확인 필요'로 종합·로그에 올림(조용히 건너뛰기 금지).
- 근거: 하위 세션 evidence-auto 1단계 분석(`C:\Users\user\AppData\Local\Claude-Data\claude_pzs8sxrjxfjjc\side-session-notes\local_8d110fe9-77c6-4e1d-93b1-427ffdd7e35a\T134_분석_1단계.md`) — 한 단계 안의 긴 동작(환급 받기 대기 최대 20분)은 도중에 안 멈춤 · 옛 watch 가 01:30 에 `_watch.lock` 을 잡고 있으면 새 회차 정산이 통째로 안 돎(`tools/settlement_download.py:1288` '이미 떠 있음 — 종료') · 지금 코드는 `_수집완료.json` 계정을 영원히 건너뜀 · 10-15 nicoable 광고센터 마케팅 동의 창 3번 실패 실측.
- 버린 대안: 정산과 섞어 계정마다 증빙(B1 · 소급 단계가 수십 시간 밀림) · 자동 증빙에서 검증·광고 빼기(소유자 '포함') · 완료면 끝·사람이 `--redo`(㉡) · 3회차 연속 실패 기준.
- 배포 시점(소유자 2026-11-19 원문): "오늘 구현해서 배포하는 것으로 변경함." → T-134 를 오늘 구현·배포 · T-134 가 T-133 위에 얹히므로 T-133(D-364 '내일 배포')도 오늘 함께 배포(통제 세션 해석) · T-134 2단계는 T-133 병합을 기다리지 않고 지금 시작 → T-133 병합 뒤 rebase.
- 영향 범위: T-134 2단계(하위 세션 evidence-auto) · D-363 세부 · ②로 증빙 시간·메모리(검증 json 최대 17MB · D-346) 늘어남 = `[메모리]` 로그로 확인.
- 상태: ACTIVE (구현 R243 `4304e27` · 운용 PC 첫 회차 확인 전 · B2 범위 보완 = D-367 · 부분 SUPERSEDED by D-372 — ③ 멈춤 00:40 → 23:20(회차 끝 − 40분 규칙 그대로))

### D-366 [LEDGER_FRESH_READ] 관리대장 변경분 = 실행 시작 때마다 다시 읽어 반영 · 정산 회차 시작 때 정산이 스스로 대장→원장 반영+비밀번호 저장 (2026-11-19, R243 · 구현 전)
- 결정(소유자 2026-11-19 원문): "관리대장은 매번 실행시 구글시트 읽어서 가져오는지 확인해줘. 관리대장 변경분이 정확히 반영되어야 함." → 통제 세션 확인(무인·재부팅 이어하기 = 새로 켜질 때 읽음 ✓ · 켜 둔 앱 버튼 실행·06:00 계약자 현황 = 앱 켤 때 읽은 대장 그대로 ✗ · 정산 첫 바퀴 = 앱 반영 전 원장일 수 있음(추정)) → "방법 추천해줘." → 통제 세션 추천 → "너의 추천 제안 수용."
- 적용: ① 켜 둔 앱의 모든 버튼 실행 = 시작 전 확인(`ui/app_qt.py` `_require_run_inputs`)에서 `_auto_load_input` 다시 부름(입력 소스 설정 그대로 · 확인 팝업 전 · 못 읽으면 실행 안 함 D-134) · 06:00 계약자 현황 = 만들기 직전 같은 함수로 다시 읽음 · 못 읽으면 그날 한 번 알림 + 10분 뒤 다시 시도 · 한 실행은 시작 때 읽은 대장으로 끝까지(도중 변경 = 다음 실행) ② 정산 회차 첫 바퀴 계정 읽기 직전 = 정산이 스스로 대장→원장 반영 1회(`registry_ui.sync` 재사용 · `registry_lock` 으로 앱과 차례) + 대장 비밀번호 credstore 저장(앱과 같은 함수) · 못 읽으면 그 바퀴 중단(지금 '원장 오래됨'과 같음)·다음 바퀴 재시도.
- 근거: 입력 목록이 바뀌는 곳 = `ui/app_qt.py:1223`·`1291`·`ui/registry_panel_qt.py:159` 뿐(앱 시작 `ui/app_qt.py:217` · 수동 버튼) · `do_run_full` 은 `self.input_list` 그대로 씀 · 06:00 `ui/app_qt.py:1808` 도 같음 · 정산 = 바퀴마다 원장 읽음(`tools/settlement_download.py:1119`) · 원장 반영 = 앱 실행 시작 `registry_ui.presync`(01:30 동시 시작) · 비밀번호 = 대장 값(credstore) 먼저 → 원장 값(`settlement_accounts.login_passwords`) → 어제 비밀번호 먼저 넣으면 틀린 1회(5회 잠금·24시간 D-068).
- 버린 대안: 몇 분마다 자동 다시 읽기 · 파이프라인 안에서 읽기(`pipeline.py` 공유) · 정산이 앱 반영을 기다리기 · 정산이 관리대장 직접 읽기(D-103 출처 변경).
- 영향 범위: ① = 레인 H(`ui/app_qt.py`) · 오늘 배포 · ② = 정산 받기(`tools/settlement_download.py` · T-134 와 같은 파일) = T-134 병합 뒤.
- 상태: ACTIVE (① 구현 R243 `8f2a95e` · ② 구현 R243 `def15c4` — 실패 = 그 바퀴 중단·5분 뒤 재시도 · 운용 PC 첫 회차 확인 전)

### D-367 [SETTLE_EVIDENCE_AUTO] 자동 증빙 = 정산 회차가 '완료'든 '미완료'(진전 없어 다음 회차로 넘김)든 정산이 끝난 뒤 남은 시간에 받음 (2026-11-19, R243)
- 결정(소유자 2026-11-19 · 통제 세션 질문 "정산 회차가 '미완료'… 로 끝났을 때도 남은 시간에 증빙을 받을까요?"에 선택): "미완료여도 받기 (Recommended)".
- 적용: D-365 ① B2 의 '완료' = 정산 받기 회차 종료 결과 `done`(완료)·`giveup`(미완료) 둘 다 · `stop`(중단) 은 증빙 안 함 · 지금 구현(`tools/settlement_download.py` cmd_watch `_evidence_sweep` · `4304e27`) 그대로.
- 근거: `src/coupang_analytics/settlement_watch.py:35` RESULT done=완료·stop=중단·giveup=미완료 · giveup = 여러 바퀴 진전 없음으로 회차 정산 손 놓음(:127) → 증빙이 그 회차 정산 시간을 뺏지 않음 · 로그인 막힌 계정 하나로 매일 미완료가 나와도 증빙이 쌓임.
- 버린 대안: '완료'일 때만(막힌 계정 하나면 그날 증빙 0).
- 영향 범위: T-134 · D-365 ① 보완.
- 상태: ACTIVE (부분 SUPERSEDED by D-373 — '미완료(giveup)' 결과 없어짐 · 완료 뒤 증빙은 그대로 · 생성 대기만 남은 회차 증빙 = 확인 필요)

### D-368 [DATE_COLUMN] 결과 통계 시트 날짜 칸 = 판매 기준일(D-1) · 01:30 실행이어도 칸 = 전날 · 과거 칸 전체 하루 당겨 이전 · 설치는 이 변경을 끝낸 뒤 (2026-11-19, R243 · 조사 전)
- 결정(소유자 2026-11-19 원문): "판매분석은 작업시점(1:30)기준 D-1, 노출순위는 작업시점이므로 구글 데이타 분석 통계 시트(결과파일)에는 날짜가 D-1일이어야 함, 11.20일 1:30분에 실행해도 시트 날짜는 11.19일이어야 함." → 통제 세션 설명(과거 칸 = '칸 날짜 = 판매일+1' 로 일관 · 규칙만 바꾸면 11.19 칸 겹침·하루 소실 → 과거 칸 일괄 −1일 이전 필요) → 질문 "언제 반영할까요?" 에 선택 "날짜까지 끝낸 뒤 설치"(오늘 밤 R243 설치 보류 · 운용 PC 는 R241b 18:00 그대로).
- 적용: 날짜 칸 = 판매 조회일(D) · 순위 = 실행 시점(D+1 01:30 무렵) 측정값을 같은 D 칸에 · 과거 칸 전체(마스터 엑셀·결과 구글시트·통합 판매현황 등) 1회 −1일 이전 · 범위·이전 방법·'날짜 지정' 버튼 의미·순위 격일/체험단 날짜 판정 = T-137 조사 뒤 소유자 승인.
- 근거: `src/coupang_analytics/pipeline.py:149` column_dates = (판매 = 칸−1일, 칸 = 실행일) · 오늘·날짜 지정·무인 공통 · D-364 ① '날짜 칸 = 실행일(코드 변경 없음)'.
- 버린 대안: 과거 칸 그대로 두고 규칙만 변경(11.19 칸 겹침·11.18 판매 하루 소실) · 오늘 R243 먼저 설치·날짜는 다음 배포(소유자 선택 아님).
- 영향 범위: D-364 ① 부분 대체(날짜 칸 규칙) · 메모리 date-column-run-date-rule · T-137 · R243 zip 설치 보류(T-59).
- 상태: ACTIVE (부분 SUPERSEDED by D-369 — 이전 대상 문구 정정 · 세부 = D-369) · 구현 `ae26016`·병합 `002d843`(T-137 · 운용 설치 전)

### D-369 [DATE_COLUMN] 날짜 칸 D-1 세부 — 체험단 = 시작일 칸부터 10칸 · 과거 칸 당기기 = 새 판 첫 실행 때 자동 1번 · 설치 = 11-20 아침→낮 1번→11-21 01:30 · 재고 갱신 날짜 = 실제 잰 날 · 옛 날짜별 사본 = 그대로 · 이전 대상 정정 (2026-11-19, R243 · 구현 전)
- 결정(소유자 2026-11-19 · 통제 세션 질문 4개에 선택): 체험단 "시트 11.20 칸부터 10칸 (Recommended)" · 칸 당기기 "새 판 첫 실행 때 자동 1번 (Recommended)" · 설치 일정 "11-20 아침 설치→낮 1번→11-21 01:30 (Recommended)" · 기타 "둘 다 권장대로 (Recommended)".
- 적용: ① 체험단 순위 = 시작일 S 의 시트 칸 S~S+9(측정 = S+1 01:30 부터 10번) ② 과거 칸 −1일 = 새 판 첫 실행 시작 때 자동 1회 — 마스터 백업 먼저 · 사업자 시트 날짜 칸 라벨 −1(값 그대로) · 숨긴 `_수집스탬프` −1 · `_순위묶음` 시작일(B1·D1) −1 · 실패하면 그날 실행 안 함 · 두 번 당김 방지 = 숨긴 표시 + 판매분석_일별 대조(칸=판매일+1 이면 옛 기준 · +0 이면 이미 이전됨) · 결과 구글시트 = 그 실행 끝 반영 ③ 지난 칸 순위 보충·순위 묶음 갱신 날짜도 새 칸 규칙 ④ 계정목록 '그로스 재고 자동갱신 날짜' = 실제 잰 날 ⑤ 9/21~ 날짜별 사본 파일 = 옛 기준 그대로 보관 ⑥ 설치 = 11-20 아침(11-19 18:00 옛 판 회차 끝난 뒤) → 11-20 낮 전체 실행 1번(11.19 칸 = 11.19 판매) → 11-21 01:30 자동 · 그 전에 개발 PC 에서 11-20 아침 운용 사본으로 당기기 리허설.
- 정정(D-368 문구): 통합 판매현황·판매분석_일별·계약자 현황·재고 기준일 = 원래 판매일 기준 → 이전 대상 아님.
- 근거: T-137 1단계 분석 `D:\coupang-analytics\output\_설계_261119_날짜칸D-1\분석_1단계.md` — 날짜 입구 = `pipeline.py:149` 한 곳 · 실행일을 칸으로 쓰는 곳 = `pipeline_stages.py:87-90`(지난 칸 순위 보충)·`pipeline_ranks.py:280`(refresh_groups) · 이전 없이 새 판이 돌면 11.19 스탬프 '수집됨' → 판매수집 건너뜀·11-18 값 잔존(`workbook_dates.py:53-67`) · output40 실측 510건 중 '칸=판매일+1' 443·'+0' 50.
- 버린 대안: 체험단 시작일 새벽부터(시트 S-1 칸부터) · 사람이 도구로 당기기 · 11-20 낮 설치 후 바로 01:30 · 재고 날짜 = 칸 날짜.
- 영향 범위: T-137 2단계 · D-368 보완 · D-364 ⑦ 체험단 표현(측정일 → 시트 칸).
- 상태: ACTIVE · 구현 `ae26016`·병합 `002d843`(T-137 · 게이트 36 · output40 리허설 통과 · 운용 설치 전)

### D-370 [LEDGER_DB_TEST_RETIRE] T-71 정산 장부 DB 시험 = 폐기 · 코드 = 태그 보관 · 데이터 = 결정 근거 DB 만 남김 (2026-11-19, R243)
- 결정(소유자 2026-11-19 · 통제 세션 질문 "T-71 장부 DB 시험(11-18 중단)을 어떻게 정리할까요?"에 원문): "권장안으로 진행해줘" (앞서 11-18 "중단해줘").
- 적용: ① STATE T-71 = `[제외 R243]` ② 브랜치 `feat/ledger-db-test`(끝 `2a5f4fa` · master 에 없는 커밋 5개 · 약 2,900줄) = 태그 `archive/ledger-db-test`(origin 에도 푸시) 로 보관 후 로컬·origin 브랜치 삭제 · 작업 폴더 `D:\ca-wt-ledger` 삭제 ③ 데이터 `output\_시험_261116_장부DB\` = 계획·인계·분석 문서와 하위 폴더는 그대로 · 장부 DB 는 결정 근거로 쓰인 것만 남기고 나머지 삭제(목록 = 소유자 확인 뒤).
- 근거: 11-18 중단 뒤 진행 없음 · 위탁자 정산서는 master 새 정산서 코드(T-38 `settlement_consignor_month*`)로 진행 · master 코드가 이 브랜치·폴더를 쓰는 곳 0(grep) · 결정 인용 = D-290 `장부_2차.sqlite` · D-279 '장부 DB(11-16)' · 마지막 완성본 = `장부_4차.sqlite`(인계.md 11-17 19:35 V1 13/13·judge exit 0) · 6차·7차 `_중단` = 인계.md "불완전 · 쓰지 말 것".
- 버린 대안: 전부 삭제(D-265·D-279·D-290 근거 재확인 불가) · 할 일만 닫기(작업 폴더·브랜치 남음).
- 영향 범위: T-71 · D-265·D-279·D-289·D-290·D-297·D-301·D-314 의 '장부 시험 DB' 근거(남긴 DB·문서로 확인) · 다시 살릴 때 = `git branch feat/ledger-db-test archive/ledger-db-test`.
- 상태: ACTIVE · 데이터 정리 끝(소유자 11-19 '이 목록대로 삭제' · 남김 = `장부_2차.sqlite`·`장부_4차.sqlite`·문서·하위 폴더 · 삭제 = 1차·3차·5차·6차_중단2·6차_중단3·7차_중단2 + journal 9파일 약 2.4GB)

### D-371 [CONTRACTOR_DAILY] 계약자 현황 = 이번 회차 ① 판매수집 완료 뒤에만 만듦 · 모든 계정 자료 없음이면 PC 파일·구글시트 안 만듦(전날 내용 그대로) (2026-11-20, R243)
- 결정(소유자 2026-11-20 원문): "운용PC에 설치해고 앱을 실행하고 전체실행 버튼을 누르지 않았는데 "셀독 계약자 상품 현황" 파일 시트에 값이 사라졌어. 확인해줘." → 통제 세션 원인 보고·제안(① 아침 엑셀로 되돌리기 ② 코드 수정 후 다시 배포) → "둘 다 진행해줘".
- 적용: ① `contractor_stage.wait_reason` = ① 도는 중(그대로)에 더해 이번 회차(01:30~) ① 완료 기록(`_실행단계.json` · 정산과 같은 `sales_done_in_cycle`)이 없으면 미룸 → 실행 기록도 안 남겨 ① 이 끝난 뒤(전체 실행 포함) 1분 안에 만듦 · 앱 ⏸ 줄 = 미룬 이유 그대로(`ui/app_qt.py` `_contractor_tick`) ② `run_stage` = 모든 계정이 자료 없음이면 ❌ 줄 남기고 PC 파일·구글시트 안 만듦(그날 실행 기록은 남김 — 1분마다 되풀이 안 함) ③ 일부 계정만 자료 없음 = 그대로 '(로그인 실패)'·'(오늘 자료 없음)' 표시(D-358 ⑦).
- 근거: 운용 PC R243b 설치 뒤 앱을 켜자 5초 뒤 `_contractor_tick` → 06:00 지남·그날 기록 없음 → `run_daily`(자료 = 그날 01:30 이후 보관본만 · 운용 PC 자료 = 옛 판 11-19 18:00 것뿐) → 전 사업자 '(오늘 자료 없음)' 표를 구글시트에 덮어씀(되돌릴 때 반영 로그 '옛 탭 37개 지움' = 사업자 36 + 요약) · 같은 날 기록이 남아 그날 다시 안 만듦 · 01:30 실패·밤새 꺼짐 날도 같은 경로 · 재현 = `tools/verify_contractor_sheet_offline.py` T9(고치기 전 구글 반영 시도 `['URL']`)·T9b(단계 기록 없음) 실패 → 수정 후 통과 · 전체 게이트 36종 통과.
- 되돌림(11-20): 아침 파일 `output\_결과_261120_계약자시트_output41\data\계약자별상품현황\셀독_계약자별상품현황_261119.xlsx` 그대로 다시 올림(`scripts\restore_push_file.py`) · 다시 읽어 대조 = 아침 대조와 같음(탭 35 · 요약 8줄·휴라엘 6줄 다른 줄 0 · 색 규칙·칸 폭·링크 같음).
- 버린 대안: 자료 없는 계정도 전날 값으로 채우기(D-358 ⑦ 옛 값 금지) · 06:00 시각만 늦추기(설치 첫날·01:30 실패는 그대로) · 전 계정 자료 없음일 때도 실행 기록 안 남기기(1분마다 대장 다시 읽기 · 그 회차엔 자료가 안 생김).
- 영향 범위: D-361 ①(06:00 실행 · '만들지 못한 날도 기록' 은 ② 그대로 · ① 미완료 날은 기록 없이 미룸) · T-132 · T-59(R243c 다시 빌드).
- 상태: ACTIVE

### D-372 [NIGHTLY_SCHEDULE] 야간 무인 = 00:10 시작 · 정산 회차 = 00:10~그날 24:00 · 결과 날짜 칸 = 실행일 − 1(판매·노출·방문자·노출순위 모두) (2026-11-20, R244)
- 결정(소유자 2026-11-20 원문): "그럼 작업 시간을 00시 10분으로 하자. 정산 다운로드는 24시까지 실행하는 것으로 하자. 판매정보와 노출은 거의 실시간이므로 작업 하는 시점에서 전일날짜로 결과파일들의 날짜에 넣어 주면 됨. 어짜피 노출순위는 작업 시점이긴 하지만 규칙을 그렇게 정하면 돼. 이렇게 수정해서 검증후 배포 버젼 생성해줘.별도 세션으로 작어해줘."
- 적용: ① 야간 무인(①②③ + 정산 받기) 예약 작업 = 매일 00:10(`deploy/install.ps1`·`install_schedule_py.ps1` · 낮에 등록하면 첫 실행 = 다음 00:10 · 실행 제한 23시간50분 = 24:00 그대로) ② 정산 회차 = 00:10 ~ 그날 24:00(`settlement_watch.CYCLE_START` 00:10 · 끝 = 다음 회차 10분 전 규칙 그대로 → 24:00 · 24:00~00:10 = 정산 없음 → 00:10 실행과 안 겹침) · 시작 = 앱과 함께 떠서 이번 회차 ① 완료 대기(D-021 그대로) · 같은 회차 '완료'면 다시 안 받음(D-091 그대로) ③ 회차에서 파생되는 시각 = 자동 증빙 새 단계 멈춤 23:20(회차 끝 − 40분 D-365) · 셀독전환 멈춤 23:50(00:10 20분 전)·조용한 시간 23:50~02:50(D-364 ③ 시각) · 계약자 현황 06:00 = 그날 00:10 회차 자료(D-361·D-371 그대로) ④ 결과 날짜 칸 = 실행일 − 1 = 판매 기준일(D-368·D-369 구현 그대로 · 코드 변경 없음): 판매·노출·방문자 = 그날 하루 조회값 · 노출순위·재고·판매가 = 실행 때 잰 값을 같은 칸에(소유자 '규칙을 그렇게 정하면 돼') · 00:10 무인 = 방금 끝난 날 칸 · 같은 날 낮 수동 전체 실행도 같은 칸(규칙 하나) · 통합판매현황·판매분석_일별·계약자 현황 = 원래 판매일 기준(D-369 정정 그대로).
- 근거: 실측 `D:\coupang-analytics\output\_분석_261120_판매실시간\확인결과.md`(2026-11-20 13:19 · 통제 세션 · WING 화면 "매출 (오늘 오후 1:16 업데이트)"·"트래픽 및 전환율 (어제 오후 11:59 업데이트)" · 같은 API 오늘 하루 = 판매 2·노출 0·방문 0 → 판매 ≈ 실시간 · 노출·방문자 = 그날 23:59 무렵 하루 한 번) · 시각 한 곳 = `settlement_watch.py` `CYCLE_START`(나머지는 파생 — 시험 P27b 가 설치 스크립트 2개와 대조) · 재현: 시험 먼저 고침 → 고치기 전 코드 실패 3종(P27 `cycle_window` · 셀독전환 T4 `UNTIL_DEFAULT` · S2 `'01:10'`) → 수정 후 통과 · 고치는 중 발견: `transfer_login.UNTIL_DEFAULT` 가 `datetime.min` 에서 20분을 빼 00:10 이면 `OverflowError`(날짜 범위 밖) → 일반 날짜 기준으로 계산.
- 위험(사실/추정 · 정책 미결정): 00:10 = 쿠팡 23:59 갱신 뒤 약 11분 — 갱신이 늦는 날엔 전날 노출·방문자가 0 으로 기록될 수 있음(추정 · 00:10 시점 실측 없음) · 감지·보완 후보는 STATE 미해결(통제 세션 판단) — 이 항목은 감지·보완을 정하지 않음(fallback 금지).
- 버린 대안: 정산 18:00 시작 유지(지금 코드는 D-362 로 이미 01:30 시작 · 소유자 '24시까지'는 00:10 시작 회차의 끝으로 읽음) · 회차 끝 23:50 등 다른 간격(다음 회차 10분 전 규칙 그대로가 24:00 과 정확히 맞음) · 순위만 실행일 칸(소유자 '규칙을 그렇게 정하면 돼').
- 영향 범위: D-021·D-362(회차·시작 시각) · D-364 ③④ · D-365 ③(시각) 부분 대체 · D-368·D-369 규칙 재확인(대체 아님) · 코드 `settlement_watch.py`·`transfer_login.py`(+ 시각 문구: `app_process.py`·`contractor_stage.py`·`settlement_accounts.py`·`transfer_settle.py`·`config.py` RANK_NOTE_TEXT·`ui/*`·`tools/settlement_download.py`) · 설치 `deploy/*`·`INSTALL.md`·`build.bat` · 직원 안내서 `tools/build_staff_manual.py`(PDF 다시 만들기 = 통제 세션) · 시험 `verify_settlement_runtime_offline`(P27·P27b·T-134)·`verify_transfer_offline`·`verify_transfer_settle_offline`·`verify_date_basis_offline` B1 · 운용 PC = 설치.bat '등록(Y)' 다시 해야 00:10 으로 바뀜(덮어쓰기만 하면 01:30 그대로).
- 상태: ACTIVE (구현 R244 · 브랜치 `claude/nightly-0010-e45edb` · master `6c0978f` 반영 · R245c zip 포함 · 운용 PC 설치 전)

### D-373 [SETTLE_RETRY_THREE] 정산 받기 오류 = 회차마다 계정·항목별 최대 3번(처음 + 다시 2번) · 그 뒤 그 회차 더 시도 안 함 · 오류 로그(사유·시각·계정·데이터·항목·몇 번째) · 파일 생성 대기 = 오류 아님(24:00 까지) · 다 끝나면 조기 종료 (2026-11-20, R245)
- 결정(소유자 2026-11-20 원문 · 통제 세션 전달): ① "다만, 정산자료 다운로드 작업은 24시까지 이지만 모두 받아서 받을게 없으면 조기 종료 해도 됨." ② "서버 오류가 난 계정을 다시 시도할 대상으로 볼지, 끝난 것으로 볼지 확인합니다.==> 이 건은 다시 시도해야 함, 다른 항목들도 마찬가지임, 2번까지 다시 시도 하고도 오류 이면 더이상 시도하지 않음. 이런때에는 로그를 남겨줘. 로그내용은 오류사유, 시간, 계정, 데이타, 시도 항목을 남겨주면 어떤 계정의 어떤 항목이 어떤 사유로 오류가 났는지 알수 있음." ③ "비밀번호 오류는 지금 방식대로 유지해." ④ 애매한 4가지 = 소유자 "권장안대로" — (가) 한 번의 시도 = 그 계정의 그 항목을 한 번 받으려 한 것(바퀴 1번에 1회) (나) 쿠팡이 파일을 만드는 중이라 기다리는 것은 오류가 아님 — 횟수를 세지 않고 24:00까지 기다림 (다) 접속 차단(Akamai·차단 연속)도 오류로 셈 — 3번째 실패 뒤 멈춤 (라) 횟수는 회차(그날 00:10)마다 0부터.
- 적용(구현 R245 · `src/coupang_analytics/settlement_retry.py` 새 모듈 + `tools/settlement_download.py` 실패 지점 · watch 회차에서만 — 사람이 부르는 명령(run·download·evidence 등)은 지금 그대로): ⓐ 시도 항목 = 로그인 · 계정 처리(정기/소급/증빙 — 그 계정 실행이 예외로 끝남: 서버 일시 오류·차단 감지·브라우저 닫힘·파싱 등 그 밖) · 정산 파일 하나(`받기 채널 종류·리포트` + 데이터 '정산일·기간') · 광고비(밀크런·광고센터) · 월자료(종류 + 달 — D-245 ① '그 회차 다시 안 부름'을 3번까지로) ⓑ 셈 = 바퀴당 1번(같은 바퀴 두 번째 실패 안 셈 · 호출 안 15초×2 재시도는 한 시도 안 · 정기에서 로그인 실패한 계정은 같은 바퀴 소급에서 다시 로그인 안 함) · 3번째 실패 → 그 회차 그 항목 건너뜀(로그인·계정 처리 소진 = 그 계정 건너뜀 · 처리기록 '건너뜀' 줄에 이유) · 성공하면 그 항목 기록 지움 ⓒ 예외: 비밀번호 거부 = 지금 방식(24시간 안 넣음 D-012·D-068·D-123 · 계정은 매 바퀴 그대로 돎) · 로그만 그 회차 1번 / 2차 인증(otp) = 처음부터 다시 시도 안 함 · 로그만 / Akamai 챌린지·Access Denied·차단 감지 = 오류로 셈(④ 다) / 계정 사용 중·비밀번호 없음·계정 잠금 파일 = 오류 아님(지금 그대로) / 요청 대기 응답(remainingTime)·파일 목록에 아직 없음 = 오류 아님(대기) ⓓ 회차 판단(`settlement_watch.plan_after_pass`) = 연속 실패 중단 → 다음 바퀴(D-031 그대로) > 새로 한 일 → 곧 다음 바퀴 > 파일 생성 대기(3번 소진된 파일 뺌) 또는 이번 바퀴 실패·다시 시도 남은 항목 → 5분 뒤 다음 바퀴 > 그 밖 = 완료(받음·3번 소진·예외만 남음 → 24:00 전 조기 종료 · 소진·사람 조치 계정은 '완료·실패 확인' 문구에) · 옛 '진전 없음 3바퀴 → 미완료(giveup) 종료' 폐지(④ 나) ⓔ 횟수 = 회차 시작(00:10)마다 0부터 · 같은 회차 재시작(재부팅 복구)은 상태 파일 `output\정산\로그\_재시도_상태.json` 으로 이어 셈 ⓕ 오류 로그 한 건 = `output\정산\로그\재시도_오류기록.csv`(누적 · 칸: 시각·회차·실행ID·계정·시도 항목·데이터·시도(n/3)·결과(다음 바퀴에 다시 시도 / 더 시도 안 함(3번 실패) / 다시 시도 안 함)·오류사유 200자) + 정산 실행 로그 한 줄(`↻ [오류 1/3] 계정 · 항목 · 데이터 → 결과 (종류: 사유)` · 3번째 = `⛔`) · 회차 끝 [실행 결과 종합]에 '오류로 더 시도 안 한 항목' 목록 · 비밀번호·키 같은 비밀 값 없음(사유 = 예외 글자).
- 근거(코드 · 재현): 바뀌기 전 = 바퀴마다 전 계정 처음부터(`_one_pass`→`_run_both`) · 계정·항목 시도 횟수 세는 곳 없음 · 2차 인증·Akamai = 매 바퀴 다시 로그인 · 받기 중 예외(파싱) = 작업이 '요청됨'으로 남아 생성 대기로 계속 셈(상한 없음) · 진전 없음 3바퀴(`MAX_IDLE_PASSES`) = 미완료 종료 · 월자료 실패 달 = 그 회차 1번만(D-245) — 인계 `side-session-notes\…\R244_정산재시도2회_인계_1120.md`(줄 번호 = `6c0978f`). 시험 먼저: `tools/verify_settlement_runtime_offline.py` P70 신설(① 일시 오류 2번 뒤 성공 · 3번 실패 → 멈추고 로그 9칸 · 같은 바퀴 2번째 안 셈 · 재시작 이어 셈 · 다음 회차 0부터 · 비밀번호 거부/2차 인증 예외 ② 로그인 실패 종류 7가지 ③ 계정 서버 오류 3바퀴 뒤 건너뜀·2차 인증 1번만·비밀번호 매 바퀴 그대로 ④ 받기 파싱 오류 3번 뒤 안 받음·생성 대기 안 셈 ⑤ cmd_watch 3번 소진 → 24:00 전 '완료·실패 확인' · 생성 대기만 → 24:00 까지 ⑥ 월자료 실패 달 3번) → 고치기 전 코드 실패(`TRIES` 없음 · P12 `plan_after_pass` 인자) → 수정 후 통과 · 시험 중 고친 결함 2건: 받기 실패 기록 인자 순서(사유가 데이터 칸으로) · 생성 대기 수에서 '이번 바퀴 실패' 파일까지 빼던 것(`Tries.ended` 로 소진만 뺌).
- 버린 대안: 바퀴마다 전부 다시(지금 — 2차 인증·차단 계정 무한 재로그인) · 처음 오류에서 바로 멈춤(소유자 '2번까지 다시') · 파일 생성 대기도 3번으로 셈(소유자 ④ 나 아님) · 처리기록 CSV 에 '시도' 칸 추가(옛 누적 파일 머리글과 칸이 어긋남 → 별도 파일) · 시도 횟수를 메모리에만(재부팅 복구 때 0 부터 다시 = 회차 3번 넘음).
- 추가 결정(소유자 2026-11-20 원문 · 통제 세션 질문 "정산 파일 대기: '대기 계정만 30분마다'로 할까요?" → 소유자 "20분으로 해줘."): 생성 대기만 남은 회차(새로 한 일·다시 시도할 오류·연속 실패 중단 없음 · 생성 대기 > 0)는 그 뒤 **대기 바퀴**만 돎 — 받으러 갈 파일(요청예정·요청됨)이 있는 계정만 로그인해 받기만(요청예정이 남았으면 요청 + 90초 뒤 받기 · 검증·광고·소급 안 함) · 다 받은 계정·3번 소진 파일/계정·예외(비밀번호 거부·2차 인증) 계정은 로그인 0(그 계정 파일은 받을 것 수에서도 뺌 → 대기가 끝나면 24:00 전 종료) · 간격 = 20분(`WATCH_PENDING_SEC`) · 대기 바퀴 안 오류 다시 시도·연속 실패 = 5분 그대로 · 24:00 까지 · 대기 바퀴로 바뀌는 때 자동 증빙 1번(빈 시간 · D-367 '미완료여도 받기' 취지 · 23:20 멈춤 D-365) + 회차 끝에 남은 증빙 그대로 — 위 위험 ①은 이 결정으로 풂. 시험 P70 ⑤(전체 1번 뒤 대기 바퀴만·간격 20분·24:00 끝·증빙 1번·대기 끝나면 일찍 종료·대기 중 오류 = 5분) ⑦(대기 바퀴 대상 = 받을 파일 계정만 · 다 받음·비밀번호 거부·3번 소진 = 로그인 0). 남은 것(사실): 생성 대기 전 단계의 오류 다시 시도 바퀴(5분)는 지금처럼 전 계정을 돎(다 받은 계정도 로그인 — 옛 '대기' 바퀴와 같음 · 최대 3번) · CAPTCHA 판정 = 구현 안 함(감지 신호 후보만 보고 — 통제 세션 판단 11-20).
- 위험·확인 필요(사실/추정): ① (사실) 파일 생성 대기만 남으면 24:00 까지 5분마다 전 계정 바퀴를 돎(옛 = 3바퀴 뒤 끝) → 로그인 횟수 늘 수 있음 · 그 회차엔 자동 증빙(D-365·D-367 '미완료여도 받기')이 돌 시간이 없음(정산이 24:00 까지 끝나지 않음) — 대기 중 증빙을 끼워 넣을지 = 통제 세션·소유자 판단(이 항목은 정하지 않음) ② (사실) 검증 자료 조회 실패(지난 값 유지 D-161)·판매분석 ⚠·정산 예정 조회 실패는 이 셈 밖(그 단계 안에서 대기로 기록 · 다음 바퀴 계획에 따라 다시 부름 · 지금 그대로) ③ (사실) 광고비 = 한 항목(밀크런·광고센터 중 한쪽만 실패해도 1번으로 셈 · 3번 소진 = 그 회차 광고비 단계 전체 건너뜀) ④ CAPTCHA 전용 판정 코드 없음 — 사람이 통과해야 하는 화면은 '2차 인증(otp)'·'Akamai 챌린지(akamai — ④ 다 로 오류 셈)' 둘뿐.
- 영향 범위: D-245 ①(월자료 실패 달 '그 회차 다시 안 부름' → 3번까지) 부분 대체 · D-367(증빙 '미완료여도' — 미완료 결과 없어짐) 부분 대체 · D-031 ②(연속 실패 = 다음 바퀴) 그대로 · D-172 '진전 없음 --> 중단' 판정 = watch 에서 더 안 나옴(글자 규칙 그대로) · 코드 `src/coupang_analytics/settlement_retry.py`(새) · `settlement_watch.py`(`plan_after_pass` 인자 `retry` · `MAX_IDLE_PASSES`·`giveup` 삭제) · `tools/settlement_download.py`(`TRIES`·`SessionSkip.kind`·`_login`·`_run_accounts`·`cmd_download`·`_pending_jobs`·`collect_ads`·`collect_docs`/`_docs_retry`·`_watch_failures`·`_retry_count`·`cmd_watch`) · 시험 P12·P27·P29·P30·P36·P55·P59·P67·P68·P69(새 인자·이름) · P70(새).
- 보완(소유자 2026-11-20 원문 "4건 모두 고친 뒤 배포해줘" · "필요하면 병렬로 별도 세션으로 진행해줘. 수정 완료되면 최종 검증 시뮬레인션을 통해 오류 확인하고, 정상이면 배포 파일 생성해줘." · 배포 전 통합 시뮬레이션 결함 ①): 끝 상태·완료 문구의 '실패 N계정'에 이번 회차 비밀번호 거부 계정도 넣음(`Tries.given_up` 이 비밀번호 거부를 빼던 것 — 마지막 바퀴가 대기 바퀴면 그 계정이 바퀴에 안 들어가 '완료 · 모든 정산 파일 다운로드 완료'로 잘못 끝남) → 끝나는 방식(전체 바퀴·대기 바퀴)과 상관없이 같은 상태 '완료·실패 확인'·같은 문구 · 로그인 성공하면 빠짐 · 비밀번호 다시 넣지 않는 동작(24시간)은 그대로. 재현 = `output\_배포검증\R245_261120\시뮬레이션\sim_run.py` S2·S2c 실패(master `c16f99b`) → 시험 P70 ⑧ 먼저(고치기 전 실패) → 수정 후 S2·S2b·S2c 통과(사본으로 이 브랜치 코드 실행 · 시뮬레이션 폴더는 안 고침).
- 상태: ACTIVE (구현 R245 · 브랜치 `claude/laughing-khorana-ac1222` · 병합 `d72eade` · R245c zip 포함 · 운용 PC 설치 전 · 부분 SUPERSEDED by D-383 — 다시 시도 바퀴 = 전 계정 → 남은 일 바퀴(오류 단계만) · 대기 바퀴 → 남은 일 바퀴에 합침)

### D-374 [TRAFFIC_MORNING] 노출·방문자 = 매일 08:00 계정마다 한 번 더 받아 어제(D-1) 칸 두 줄만 덮어씀 · 판매·순위 칸 그대로 · 정산과 계정 잠금으로 순서 · 3번 실패 = 00:10 값 그대로 (2026-11-20, R245)
- 결정(소유자 2026-11-20 원문): "방문자, 노출건수는 오늘것은 검색했더니 정보가 없어. 너가 제시한대로 00:30분에 실행을 하면은 노출/방문자 건수는 zero가 될 확률이 높겠어. 그러면 앱의 기능을 시간대로 구분해서 실행을해야 겠어, 어떻게 하면 효과적인지 제시해줘." → 통제 세션 A(다음 날 밤 보충)·B(아침에 한 번 더)·C(시작을 늦춤) 제시 → 소유자 "B. 아침에 한 번 더". 시각 08:00 = 통제 세션 제안값(소유자가 다른 시각을 말하지 않음 · 바꾸려면 `traffic_morning.MORNING_AT` 한 곳).
- 적용: ① 00:10 무인(①②③·재고·정산)은 그대로 · 08:00 에 이번 회차 ① 이 어제 칸을 받은 계정(`_수집스탬프`)마다 다시 로그인(① 과 같은 `_login_with_candidates` · 보이는 창 · 세션 있으면 재사용) → 판매분석(vi-detail-search) 어제 하루만 조회 → 마스터·그날 스냅샷(`_통계_yymmdd`)·결과 구글시트의 어제 칸에서 **노출량(`totalPageViews`)·방문자(`totalUniqueVisitor`) 두 줄만** 덮어씀(블록 VID 중 응답에 있는 첫 VID 값 · D-031 과 같은 규칙 · 응답에 없는 블록 = 그대로) · 판매·순위·재고·판매가·판매상태·다른 날짜 칸 안 건드림 · 상품조회·재고·원문 보관·판매분석_일별 기록 안 함 ② 띄우는 곳 = 앱 1분 타이머(`ui/app_qt._morning_tick` · 06:00 계약자 현황 `_contractor_tick` 와 같은 방식) · 무인 앱(00:10 `--auto`)·재부팅 복구 앱은 ①②③ 뒤 그날 보충이 남았고 이번 회차 ① 이 끝났으면 **켜 둔 채 기다렸다가** 보충 뒤 종료(예약 작업 실행 제한 23시간50분 안 · 설치 스크립트 변경 없음) · 08:00 에 앱이 꺼져 있었으면 켠 뒤 그날 한 번 · 23:00 뒤엔 그날 새로 시작 안 함 · 그날 한 번(`output/노출방문_아침보충/_실행기록.json` · 날짜별 근거 `YYYY-MM-DD.json` = 계정별 시도·결과·바뀐 칸 전/후) ③ 겹침 막기 = 파이프라인 잠금(`output/_잠금/파이프라인.lock` · 기다리지 않음 → ①②③·날짜 지정·다른 창 실행이 돌면 끝난 뒤 다음 타이머에서 · 쥔 동안 셀독전환 새 로그인 안 함 `transfer_login.BUSY_LOCKS`) + 이 창 다른 실행 중이면 기다림 + 계정마다 정산과 같은 계정 잠금(`output/정산/_잠금/{계정ID}.lock`)을 쥔 뒤 그 계정 Chrome 이 꺼질 때까지 기다리고 엶 → 정산이 그 계정을 쓰는 중이면 그 바퀴 맨 뒤로 미루고 그래도 쓰는 중이면 30분까지 기다림(넘으면 그 번 실패) · 정산은 잠금을 못 얻으면 오류로 세지 않고 다음 바퀴에 다시(정산 코드 변경 없음 · R245 D-373 `SessionSkip` 종류 '' 그대로) ④ 실패 = 계정마다 최대 3번(처음 + 다시 2번 · D-373 과 같은 수 · 바퀴 사이 10분) · 비밀번호 거부·2차 인증·계정 정지 = 다시 안 함(D-123·D-373) · 끝내 실패한 계정 = 그 칸 00:10 값 그대로 + 로그 '❌ 노출·방문자 아침 보충 실패 — 계정 · N번 시도 · 사유'(값을 대신 채우지 않음 · fallback 금지) ⑤ 아침 값도 노출·방문 0 인데 그날 판매가 있는 계정 = ⚠ 줄(측정용 · 값은 그대로 씀) ⑥ 날짜 지정 실행과 안 섞임 — 대상 칸 = 실행일 − 1 하나(`run_day_column`) · 날짜 지정으로 다른 칸만 받은 계정은 대상 아님.
- D-362 와의 관계: D-362 '판매 1번 더 받기 없음'의 **예외 = 노출·방문자 두 줄뿐**(판매는 다시 받지 않음) → D-362 상태 줄 '부분 SUPERSEDED by D-374'.
- 근거: 실측 `D:\coupang-analytics\output\_분석_261120_판매실시간\확인결과.md`(2026-11-20 · 판매 = 낮 13:16→14:51 갱신 · '트래픽 및 전환율 (어제 오후 11:59 업데이트)' · 당일 노출·방문 0 · 전날 11-19 방문 93·조회 106 낮에 있음 · 실제 들어오는 시각은 모름) · 노출·방문자가 들어가는 곳 조사 = 마스터 사업자 시트 '노출량'·'방문자' 줄 한 곳(`pipeline_process._fill_product_metrics`) → 그날 스냅샷 = 마스터 사본 · 결과 구글시트 = 마스터 미러(`push_gsheet`) · 통합판매현황(판매분석 기록 판매금액·수량만)·계약자 현황(7일 판매수량만)·판매분석_일별 json(판매금액·수량·주문만) = 노출·방문자 없음(바꿀 것 없음) · 앱 상품 표 '최신 지표'(`app_qt._metric_at_latest`) = 마스터를 읽어 표시만 · 정산 겹침 = 정산 `session()` 이 그 계정 Chrome 사용 중이면 기다리고(`_profile_busy`) 계정 잠금을 5초만 기다림(`tools/settlement_download.py:315`) · WingBrowser 는 열 때 같은 프로필 Chrome 을 끔(`browser._kill_profile_chrome`) → 잠금 + Chrome 확인 없이 열면 정산 창을 끊음 · 시험 `tools/verify_traffic_morning_offline.py` M1~M6 + `tools/verify_ui_morning_offline.py` M7(어제 칸 두 줄만 · 정산 잠금·Chrome 중 안 들어감 · 파이프라인 잠금 중 시작 안 함 · 3번 뒤 값 유지·실패 로그 · 하루 한 번 · 날짜 지정 안 섞임 · 0 경고 · 앱 타이머·무인 종료 미룸) · 일부러 고장 낸 코드(잠금 빼기·판매 칸도 쓰기·비밀번호 거부 재시도)에서 해당 시험 실패 확인.
- 버린 대안: 예약 작업 08:00 따로 등록(설치.bat '등록(Y)' 다시·새 실행 인자·앱 두 개 → 지금 구조 = 앱 안 타이머 · 무인 앱이 08:00 까지 켜져 있으면 충분) · 다음 날 00:10 에 전날 칸 보충(A안 · 소유자 선택 아님) · 시작 시각 늦춤(C안) · 응답에 없는 블록을 0 으로 덮기(00:10 값보다 나빠질 수 없게 그대로) · 실패 계정을 전날 값·추정값으로 채우기(fallback 금지) · 정산이 쓰는 계정을 바로 실패로 셈(정산 한 계정 세션이 길 수 있어 한 번 미룬 뒤 기다림).
- 영향 범위: D-362(예외 두 줄) · D-372 무인 앱 종료 시각(①②③ 뒤 → 08:00 보충 뒤 · 그 사이 06:00 계약자 현황도 이 무인 앱이 만들 수 있음 — D-371 조건 그대로) · D-020(무인이 스스로 끝날 때 정산 계속 — 그대로 · 끝나는 시각만 늦어짐) · 코드 `src/coupang_analytics/traffic_morning.py`(새)·`ui/app_qt.py`(`_morning_tick`·`_wait_morning`·`_auto_done`·재부팅 복구 '할 일 없음' 분기) · 시험 `tools/verify_traffic_morning_offline.py`·`tools/verify_ui_morning_offline.py`·`tools/run_checks.py` 2줄 · 정산 파일(`tools/settlement_download.py`·`settlement_watch.py`·`settlement_retry.py`) 변경 없음 · 직원 안내서·`designs/FEATURE_INVENTORY.md`·`docs/OPERATIONS_POLICY.md` 문구 = 통제 세션 몫(공유 파일).
- 상태: ACTIVE (구현 R245 · 브랜치 `claude/morning-traffic-r245` · 병합 `994b144`·보완 `47b67f3` · R245c zip 포함 · 운용 PC 설치 전 · 라이브 시험 전 = 첫 08:00 운용 로그 `[노출·방문자 아침 보충]` 줄로 확인)
- 보완(2026-11-20, R245 · 통제 세션 통합 시뮬레이션 `D:\coupang-analytics\output\_배포검증\R245_261120\시뮬레이션\` S3c·S5c·S5d 결함 → 소유자 원문 "4건 모두 고친 뒤 배포해줘" · 23:50 = 통제 세션 결정(소유자 '4건 모두 고침' 승인)): ② 다른 창·무인 실행이 파이프라인 잠금을 쥔 동안 = 관리대장 다시 읽기·run_daily 안 함(잠깐 쥐어 보고 놓는 `pipe_busy` 확인을 다시 읽기 앞에 · D-366 '실행 도중 안 읽음' 취지 · ⏸ 줄 그날 한 번 · S3c 09:00~11:30 다시 읽기 149번 → 시험 M8 30분 0번) ③ 이번 회차 ① 이 끝났는데 23:00(LAST_START)을 넘겨 그날 보충을 못 하게 되면 `❌ 노출·방문자 아침 보충 못 함 — {사유} · 대상 N계정 · {칸} 칸 노출·방문자 = 00:10 값 그대로` 한 줄 + 그날 기록(한 번만 · 값 대신 채우지 않음) — ①②③ 이 23:00 뒤 끝나면 그 실행 [실행 결과 종합] 오류 현황('노출·방문자 아침 보충' 단계)에 · 무인 앱이 기다리다 넘기면 종료 전에 · 다른 실행이 파이프라인을 쥐면 그 실행 종합이 남김 ④ 도는 중이어도 23:50(`traffic_morning.STOP_NEW` 한 곳) 뒤엔 새 계정·다음 바퀴 시작 안 함(다시 시도 쉼이 23:50 을 넘겨도 안 감 · 정산 사용 중 기다림도 23:50 까지) → 받은 계정까지 마스터·스냅샷·구글시트 저장은 끝까지 · 남은 계정 = `❌ 노출·방문자 아침 보충 못 함(23:50 넘음) — 남은 N계정: …` · 00:10 무인의 다른 앱 끝내기 전에 저장을 마치기 위함(S5d 34계정 22:55 시작 → 00:10:41 끝남). 코드 `traffic_morning.py`(pipe_busy·missed_today·give_up·note_missed·STOP_NEW·_passes)·`ui/app_qt.py` `_morning_tick`·`pipeline_stages.run_stages` 끝·`run_result.MORNING` · 시험 = `verify_traffic_morning_offline` M8·M9 · `verify_ui_morning_offline` M8·M9(고치기 전 실패 5건·오류 1 확인 → 통과).

### D-375 [TRANSFER_SETTLE_WATCH_REST] 셀독전환 정산 = 정산 watch 가 대기 바퀴 사이 20분 쉬는 동안 계정 시작 가능(쉼 표시) · 그날 회차(00:10~)에 받기를 마친 계정은 재부팅 복구·같은 회차 다시 띄움 때 로그인 안 함 (2026-11-20, R245)
- 결정(소유자 2026-11-20 원문 · 통제 세션 전달): 시뮬레이션으로 확인하지 못한 것 목록("…셀독전환자 정산…")에 대해 "==> 확인하고 반영해줘." → 통제 세션 결정(배포 전 추가 검증 `D:\coupang-analytics\output\_배포검증\R245b_261120\추가검증\B_셀독전환\` 결함 B1·B2):
  B1[회귀 R245] watch 가 **대기 바퀴 사이에 쉬는 동안**엔 셀독전환이 계정을 시작할 수 있게 · 같은 계정 겹침 = 기존 계정 잠금(`output\정산\_잠금\{ID}.lock`)·Chrome 사용 중 확인으로 막음 · watch 가 바퀴를 도는 중(로그인 중)엔 지금처럼 기다림 · 대기 바퀴 20분·24:00 끝·D-373 3번 규칙 그대로 · `_watch.lock` 은 계속 쥠(이중 watch 막기) · 쉼 동안만 '쉼 표시 파일' · 잠금을 풀었다 다시 잡기 = 그 틈에 두 번째 watch 가 뜰 수 있어 버림.
  B2[D-187 부터] 그날 회차(00:10 기준 `settlement_watch.cycle_window`)에 받기를 마친 계정은 다시 대상으로 잡지 않음 · 전환 상태 파일에 '받기 완료 회차' · 받다 만 계정은 지금처럼 마저 받음 · 탭 [지금 받기] = 지금처럼(회차 기록을 무시할지는 하위 세션 판단 → 아래 ③).
- 적용(구현 R245):
  ① 쉼 표시 = `output\정산\_잠금\_watch_쉼.json`(`settlement_watch.REST_MARK_NAME` · 칸 = pid·쉼 끝·쓴 시각) — watch(`cmd_watch`)가 **생성 대기 바퀴 사이 20분 쉼(`WATCH_PENDING_SEC`)에서만** 쓰고(`_rest_open`) 깨면 지움(finally) · 대기 바퀴 중 오류 다시 시도·연속 실패 중단 쉼(5분)·전체 바퀴 사이 쉼(1분·5분)·①판매수집 완료 대기 = 표시 없음(지금처럼 기다림) · `transfer_login.busy_reason` = `_watch.lock` 이 잡혀 있어도 표시가 있고 '쓴 시각 ≤ 지금 < 쉼 끝'이면 '도는 중 아님'(파이프라인 잠금은 그대로 · 1단계 로그인 확인도 같은 함수).
  ② 남은 표시 처리 = 시각 + 잠금으로 판정(PID 는 기록용): 표시는 watch 잠금이 잡혀 있을 때만 봄(watch 가 죽으면 OS 가 잠금을 풀어 표시와 상관없이 '도는 중 아님' = 지금과 같음) · 새 watch 는 잠금을 잡자마자 남은 표시를 지움 · 쉼 끝 지남·쓴 시각보다 앞(시계 되돌림)·깨진 파일 = 쉼 아님(기다리는 쪽) — PID 로 판정하지 않은 이유: Windows PID 재사용 · Windows 의 `os.kill(pid, 0)` 은 확인이 아니라 Ctrl+C 신호(CTRL_C_EVENT = 0)를 보냄 · 살아 있는지는 OS 잠금이 이미 보여 줌.
  ③ 받기 완료 회차 = `output\정산_셀독전환\_받기완료.json`({계정ID: 회차 'YYYY-MM-DDT00:10'·시각} · 비밀번호 없음 · `로그인확인_최신.json` 과 따로 — 1단계가 그 파일 줄을 통째로 다시 씀) · 기록 조건 = 그 계정 결과 '성공' + 전환 `_요청기록.json` 에 그 계정 요청예정·요청됨 0(쿠팡 파일 생성 중·계정당 30건 넘은 몫이 남으면 = 받다 만 → 기록 없음 → 다시 띄우면 마저) · `pick_targets` = 로그인 '실패' + 이번 회차 받기 완료 계정 제외 · 시작 줄에 '이번 회차(… 00:10~) 받기 끝 N계정 제외' · 다음 회차(다음 날 00:10)엔 모두 다시 · 24:00~00:10 = 전날 회차. 탭 [지금 받기] = **같은 기록을 따름**(하위 세션 판단): 무인·버튼이 같은 명령(`app_process.transfer_settle_cmd` — 이번에 고치지 않는 파일)이라 구분하려면 그 파일을 고쳐야 함 · 사람이 누르는 경우(비밀번호를 고쳐 1단계 성공 · 앱을 닫아 그날 2단계가 안 뜸 T5c · 받다 만 계정)는 모두 기록이 없어 그대로 받음 · 그날 이미 다 받은 계정을 다시 로그인하는 것만 막음(새 정산 파일은 주·월 단위라 같은 날 다시 받아도 얻는 것이 거의 없고 비밀번호 입력만 늘어 위탁계정 위험) — 같은 날 강제로 다시 받으려면 `_받기완료.json` 을 지우면 됨(통제 세션이 버튼만 무시하게 바꾸기로 하면 새 D항목).
- 근거(재현 · 시험 먼저):
  - 재현(고치기 전 master `4ef1aaf`) = 추가검증 `python run_tr.py T1c`(원장 accC 생성 대기 하루 종일 → 전환 05:00~23:50 '정산 자동 다운로드가 도는 중' → 0계정) · `T5a`(06:30 재부팅 = 4계정 다시 로그인·비밀번호 4번) · `T5b`(끝낸 tr1 다시) — 원인 `transfer_login.py:35` BUSY_LOCKS·`busy_reason` · `settlement_download.py:1522` 회차 내내 `_watch.lock` · D-373 대기 바퀴(옛 R244 = 진전 없음 3바퀴 뒤 giveup 종료라 안 보였음) · `transfer_settle.py:78-80` pick_targets(완료 기록 없음) · `ui/app_qt.py:2332-2334` --resume 때 전환 다시 띄움.
  - 시험(설계·지시 문구에서 도출) = `verify_transfer_offline` T9(쉼 표시 판정 7가지) · `verify_settlement_runtime_offline` P71(cmd_watch: 시작 때 남은 표시 지움·전체/대기 바퀴 중 표시 없음·20분 쉼만 표시·5분 다시 시도 쉼 없음·끝나면 없음·이중 잠금 그대로) · `verify_transfer_settle_offline` S9(재부팅 전 받은 계정 = 복구 뒤 0 · 받다 만·건너뜀·하던 중 끊김 = 마저 · 낮 버튼 = 같은 기록 · 00:05 = 전날 회차 · 다음 회차 = 모두) → 고치기 전 코드 실패 확인 → 수정 후 통과 · 결과 = 고치기 전 = 새 함수·인자 없음으로 3파일 실패 · 고친 뒤 3파일 통과 · 일부러 고장 낸 코드 5가지(쉼 표시 안 봄·5분 쉼에도 표시·시작 때 안 지움·남은 요청 있어도 완료 기록·완료 계정 안 뺌) 모두 해당 시험 실패 · 재현 도구 사본(REPO = 이 브랜치 · 원본 폴더 안 고침) 10개: T1c·T5a·T5b 실패 → 통과 (T1c 전환 05:00~05:21 4계정 · T5a 복구 뒤 전환 로그인 0 · T5b 복구 뒤 accB·tr3·tr4 만) · T1a·T2b·T4 통과 그대로 · T1b·T3·T5c 확인 1건씩 = 고치기 전과 같음 · T2a = 전제 바뀜으로 실패 2건(전환이 watch 쉼 동안 05:00 에 끝나 23:50 경계에 안 감) → 전환을 23:35 에 띄운 변형 T2a2 = 통과(23:50 경계 past_until·새 계정 0·00:10 전 끝)
- 버린 대안: 쉼 동안 `_watch.lock` 을 풀었다 다시 잡기(그 틈에 두 번째 watch) · 대기 바퀴 동안 내내 전환 허용(바퀴 중 로그인과 겹침 — 통제 결정 '바퀴 도는 중엔 기다림') · 5분 다시 시도·연속 실패 쉼도 열기(차단 의심 직후 같은 IP 로 전환 로그인) · PID 살아 있음 확인(위 ②) · 완료 회차를 `로그인확인_최신.json` 줄에 넣기(1단계가 지움) · 결과 '성공'만으로 완료 기록(쿠팡 파일 생성 중인 계정을 그날 다시 안 받음 = 받다 만 계정 놓침) · 재부팅 복구 때 전환을 아예 안 띄우기(`ui/app_qt.py` — 받다 만·못 한 계정을 그날 놓침).
- 위험·확인 필요(사실/추정): (사실) 쉼 동안 시작한 전환 계정은 watch 가 깨어나도 그 계정을 끝까지 함 → watch 다음 대기 바퀴와 **다른 계정끼리** Chrome 동시(같은 사무실 IP) 몇 분 — 같은 계정은 잠금·Chrome 확인이 막음(통제 결정 범위 · 이미 아침 보충·전환 사이에도 있는 일 T1b) · (사실) 전환이 쓰는 계정을 watch 가 다음 바퀴에 만나면 Chrome 이 꺼질 때까지 기다림(`_profile_busy` until=회차 끝 · 오류로 안 셈) · (사실·이번 범위 밖) 전환 계정이 '원장 정산이 이 계정을 쓰는 중'으로 2계정 연속 건너뜀이면 BLOCK_STOP 으로 전체 중단(전부터 그대로) · 의견만(구현 안 함): (가) 2단계에서 새로 실패한 계정이 '연락 필요' 시트에 안 들어감 · (라) 23:50 에 못 한 계정은 다음 날 다시 파일 첫 계정부터.
- 영향 범위: D-187 ②(watch 잠금이 풀려야 시작 → 대기 바퀴 쉼 동안은 시작) 부분 대체 · D-187 ③(대상 = 로그인 '실패' 빼고 전부 → 이번 회차 받기 완료도 뺌) 부분 대체 · D-373 대기 바퀴(20분·24:00·3번) 그대로 · D-372 23:50 멈춤·조용한 시간 그대로 · 코드 `src/coupang_analytics/settlement_watch.py`(REST_MARK_NAME·mark_rest·clear_rest·resting) · `transfer_login.py`(WATCH_REST·busy_reason) · `transfer_settle.py`(DONE_FILE·cycle_key·load_done·mark_done·open_left·pick_targets·run) · `tools/settlement_download.py`(`_rest_open`·cmd_watch 시작 때 표시 지움) · 시험 3파일 · `ui/app_qt.py`·`app_process.py`·`designs/SETTLEMENT_MODULE.md §15` 변경 없음(§15 문구 = 통제 세션 몫 · 공유 파일).
- 상태: ACTIVE (구현 R245 · 브랜치 `claude/hopeful-taussig-27ef28` · 병합 `831c3c1` · R245c zip 포함 · 운용 PC 설치 전)

### D-376 [MASTER_SAVE_ATOMIC] 마스터·스냅샷 엑셀 저장 = 같은 폴더 임시 파일에 다 쓴 뒤 바꿔 끼우기 · 저장 도중 끊겨도 옛 마스터 그대로 · 엑셀에 열려 있으면 지금처럼 PermissionError (2026-11-20, R245)
- 결정(소유자 2026-11-20 원문): 시뮬레이션으로 확인 못 한 것 목록("…00:10에 이전 앱을 자동으로 끄는 동작…")에 대해 "==> 확인하고 반영해줘." → 통제 세션 실제 프로세스 재현 → 고칠 방법 = 통제 세션 결정(`OutputWorkbook.save` 한 곳 · 임시 파일 → `os.replace`).
- 적용: ① `OutputWorkbook.save`(`workbook.py`) = `{이름}.저장중.tmp`(같은 폴더 · 이름 고정)에 다 쓴 뒤 `os.replace` 로 바꿔 끼움 → 마스터·그날 스냅샷·진행 파일 등 이 함수를 쓰는 저장 전부(`pipeline.py:660·661`·`pipeline_ranks.py:287·613`·`traffic_morning.py`·`date_basis` 등) ② 저장 도중 오류 = 임시 파일 지우고 예외 그대로 · 강제 종료로 남은 임시 파일 = 다음 저장이 같은 이름으로 덮어써 바꿔 끼움 ③ 바꿔 끼우기가 막히면(Windows = 다른 프로세스가 마스터를 읽는 중이어도 막음) 0.5초마다 최대 60초(`REPLACE_WAIT_SEC`) 다시 시도 → 그래도 막히면(엑셀에 열림 등) 바로 쓰던 때와 같은 뜻의 PermissionError(errno 13 · 파일 = 마스터 경로)로 올리고 임시 파일 지움(마스터 그대로) ④ 임시 파일 이름 = `.xlsx` 로 안 끝나 마스터(`_master_path` 고정 이름)·스냅샷 찾기(`쿠팡데이타분석_통계_*.xlsx`·`settlement_statement_scope.SNAP`)에 안 걸림 · output 내보내기는 `.tmp` 를 이미 뺌(`output_export.skip_file`) ⑤ 같이 고친 작은 것: 좀비 Chrome 정리(`browser.reap_orphan_chrome`) 찾는 글자 = data 폴더 경로 + 구분자(`data2`·`data_old` 처럼 앞부분만 같은 폴더 안 잡음 · 프로필 경로는 `Path.resolve()` 로 늘 역슬래시) · 다른 앱 끄기(`app_process._KILL_PS`) 'N개 종료' = taskkill 종료코드 0 일 때만 셈(실측: 없는 PID = 128 → 안 셈).
- 근거: 실측 재현 `D:\coupang-analytics\output\_배포검증\R245b_261120\추가검증\A_자동종료\` B1·B2(00:10 `prepare_auto_start` → `stop_other_apps` 가 기다림 없이 `taskkill /F /T` · 바로 쓰기 = 7,866,280B 마스터가 2.1MB·4.1MB 로 잘림 · BadZipFile · 다음 실행 `date_basis.ensure_sales_date_basis` 실패 · 자동 복구 없음) · 시험 `tools/verify_workbook_save_offline.py` W1~W5 — 고치기 전 실패(W2 저장 도중 끊김 = 5,942B 마스터가 1,004B 로 잘림 · W1 openpyxl 이 마스터에 바로 씀 · W5 구분자·종료 수) · W4 엑셀 잠금 PermissionError = 고치기 전에도 통과(같은 동작 유지 확인) · 다시 시도를 빼면 W4b(다른 창이 1.5초 읽는 중) 실패 확인 · 재현 사본(REPO = 작업 폴더 · 가짜 앱 저장 줄 = 실제 `OutputWorkbook.save` · 안전장치 꼬리 = 새 종료 스크립트) 결과 = 보고 참조.
- 버린 대안: 저장 전 옛 마스터 백업 복사(7.8MB 매번 복사·깨진 뒤 복구 절차 필요) · 00:10 다른 앱 끄기 전에 저장 끝 기다리기(앱 사이 신호 필요 · 저장 중 아닌 강제 종료·정전엔 효과 없음) · 임시 파일 이름에 PID(강제 종료마다 임시 파일 쌓임) · 바꿔 끼우기 막힘 = 바로 오류(다른 창이 읽는 중에도 저장 실패 — 바로 쓰기 때보다 나빠짐).
- 영향 범위: `src/coupang_analytics/workbook.py`(레인 G · `save`·`save_tmp_path`·`_replace_into` · 핀 apply_style·정밀 렌더 그대로 통과)·`browser.py`(reap 1줄)·`app_process.py`(`_KILL_PS` 1줄) · 시험 `tools/verify_workbook_save_offline.py`·`tools/run_checks.py` 1줄 · `transfer_settle.py`·`transfer_login.py`·`settlement_download.py`·`settlement_watch.py` 변경 없음(`transfer_login.py:89`·`transfer_settle.py:253` 는 openpyxl 직접 저장이라 이 변경 밖) · 재현 도구 `run_tests.py`·`fake/common.py` 의 안전장치 꼬리 문자열은 새 종료 스크립트에 맞춰 갱신 필요(원본은 안 고침).
- 상태: ACTIVE (구현 R245 · 브랜치 `claude/morning-traffic-r245` · 병합 `572f1c2` · R245c zip 포함 · 운용 PC 설치 전)

### D-377 [GATE_ONE_PER_PC] 회귀 게이트(run_checks) = PC 전체에서 한 번에 1개 · 건너뛰기 판정은 잠금 뒤 · 검사 프로세스 낮은 우선순위 — D-310 중 게이트만 되돌림 (2026-11-20, R245)
- 결정(소유자 2026-11-20 원문): 통제 세션 질문 "노트북 과부하 대책 A~C를 반영할까요? A는 11-18 D-310 '동시에 해도 돼' 중 '검사 프로그램' 부분을 되돌립니다." → 소유자 "A~C 모두 반영 (권장)". D-310 원문("무거운 실행은 하나씩 규칙 함께 ==> 이제는 동시에 해도 돼.") 중 **게이트(`tools/run_checks.py`)만** 다시 하나씩 · 다른 무거운 실행(대조·시뮬레이션·하위 세션)은 D-310 그대로 동시 허용.
- 적용: A `run_checks.main()` 시작 때 PC 전체 잠금(`%LOCALAPPDATA%\coupang-analytics\run_checks.lock` · 작업 폴더·세션·git 훅과 상관없는 한 곳 · OS 파일 잠금 = Windows msvcrt.locking / 그 외 fcntl.flock · registry_lock.py 와 같은 방식) → 다른 게이트가 쥐고 있으면 `⏳ 다른 회귀 게이트가 돌고 있어 끝날 때까지 기다립니다 — PID · 시작 시각 · 작업 폴더` 를 보이고 끝날 때까지 기다림(시간 제한 없음) · 쥔 게이트 정보는 잠금 파일 앞부분에 적고 잠금은 떨어진 바이트(1MB 위치)에 걸어 기다리는 쪽이 읽을 수 있게 함 · 게이트가 죽으면 OS 가 잠금을 풀어 남은 파일은 막지 않음 B `--skip-if-passed`(통과 기록 check_stamp · D-180) 판정을 잠금을 얻은 **뒤에** 함 → 앞 게이트가 같은 내용으로 통과하면 뒤 게이트(pre-push 등)는 검사 없이 건너뜀 C 검사 자식 프로세스 = `BELOW_NORMAL_PRIORITY_CLASS`(`getattr(subprocess, …, 0)` · Windows 전용 · 손자 프로세스도 물려받음). 동시 검사 개수(DEFAULT_JOBS=3 · D-180)는 그대로.
- 근거: D:\rea 세션 측정 `D:\perf-log\system_20261120_1758.csv`·`D:\perf-log\top_20261120_1758.csv`(+ `slow_events_20261120_1758.txt`) — 이 세션 재집계 18:04:42~19:44:56 899회 중 느린 순간 341회 · 사용 가능 메모리 최저 351MB(19:37:51) · 요청서 집계(897회·339회·CPU 누적 1위 python)와 끝 시각 차이만 · 19:46 run_checks 2개 동시(세션 bash 1 + pre-push 훅 `--skip-if-passed=push` 1 · 각 동시 3개로 simulate_pipeline 약 790MB·verify_sales_summary_offline 약 720~750MB 등 · 게이트 1개 약 2.3GB → 2개 약 4.6GB · 16GB PC). B 재현(고치기 전 코드 · 임시 저장소·가짜 검사): 앞 게이트(전체)가 도는 중 같은 커밋 내용으로 pre-push 게이트를 띄우면 건너뛰지 않고 바로 검사 시작 → '앞 게이트가 아직 안 끝나 통과 기록이 없어서 또 돈다'는 요청서 추정이 실제로 일어남을 확인(19:46 그 건이 이 경우였는지는 그 세션 기록이 없어 미확인 · 통과 기록은 작업 폴더마다 따로라 다른 작업 폴더의 push 도 다시 돈다 — 이번 범위 밖). 시험 = `tools/verify_run_checks_offline.py` S8(기다림 표시·동시 2개 없음·잠금 뒤 건너뜀)·S9(남은 잠금 파일·죽은 게이트)·S10(우선순위 0x4000) — 고치기 전 S8 실패(기다리지 않음)·S10 실패(0x20 NORMAL) 확인 → 고친 뒤 통과.
- 버린 대안: D 동시 개수(DEFAULT_JOBS) 줄이기(이번 요청 아님 · 게이트 1개 안의 속도는 그대로 두고 2개 겹침만 막음) · 잠금 대기 시간 제한(못 얻으면 실패 처리 — 앞 게이트가 길면 훅이 거짓 실패 · 죽은 게이트는 OS 가 풀어 무한 대기 원인 아님) · 잠금 파일 존재로 판정(죽은 게이트가 남긴 파일이 막음).
- 영향 범위: `tools/run_checks.py`(`LOCK_PATH`·`_gate_lock`·`_gate`·`_LOW_PRIORITY`) · `tools/verify_run_checks_offline.py` S8~S10(같은 프로세스 안 게이트도 임시 잠금 경로) · git 훅(pre-commit·pre-push 가 같은 run_checks 를 부름 · 훅 본문 변경 없음) · `tests/test_regression_gate.py`(게이트가 돌면 기다림) · D-310(게이트만 부분 대체) · `docs/CURRENT_RULES.md` 그 밖 주제 줄 · CLAUDE.md '코드 건강 규칙' 게이트 설명 문구 = 통제 세션 몫(공유 파일) · 다른 세션 작업 폴더의 옛 run_checks 는 병합 전까지 잠금을 모름.
- 상태: ACTIVE (구현 R245 · 브랜치 `worktree-agent-a6d87334bf2006be4` · 병합 `f516485` · R245c zip 포함)

### D-378 [WORKFLOW_SPEED] 작업 시간 단축 1차 — zip 은 설치 때만 · STATE 커밋은 종료 때 1번 · 작은 일은 통제 세션 직접 · 대화 내보내기는 정리 요청 때만 · 게이트 시간 기록 (2026-11-21, R246)
- 결정(소유자 2026-11-20 원문): 통제 세션 권고 "지금은 1단계 전부와 2단계 중 I·N만 적용하는 것을 권장합니다 … 이대로 진행할까요?" → 소유자 "진행, 전역 메모리에 저장하는 방안도 검토해줘."
  - A 배포 zip = 운용 PC 에 설치하기 직전 1번만 만든다(고칠 때마다 만들지 않음). 그 1번에 지금 검증(시뮬레이션·재압축·PYZ 대조·풀기 2방식) 전부. 만들기 = 통제 세션만(D-201·D-275 그대로).
  - J STATE.md 커밋 = 세션 종료(`/session-close`) 때 1번. 세션 중간 바뀐 내용은 파일만 고치고, 다른 커밋이 있으면 거기에 같이 담는다(D-352 G2 '모아서'를 '종료 때 1번'으로 좁힘).
  - K 작은 일(파일 몇 개·문서 정리·한두 시간 안 끝나는 일) = 통제 세션이 직접 · 하위 세션 = 큰 독립 작업만 · 하위 브랜치 병합은 모아서 게이트 1번.
  - H 하위 세션 대화 내보내기·아카이브(D-015 절차) = 소유자가 정리를 요청할 때만(세션 종료 때 자동으로 하지 않음).
  - N `tools/run_checks.py` 가 게이트마다 한 줄을 `%LOCALAPPDATA%\coupang-analytics\run_checks_times.csv` 에 남긴다(시작·작업폴더·종류 빠른/전체·결과 통과/실패/건너뜀·잠금 기다린 초·걸린 초·검사 합계·검사 수·검사별 초). 못 쓰면 경고만 출력(게이트 결과 그대로).
  - I 편집 훅 = 전역 결정 `D:\claude-global` D-016(mypy 고친 파일만 · 커밋 `c596568` [R14]).
- 근거: 분석 `output\_분석_261120_작업속도\과거기록_시간분석.md`·`속도_단축_방안.md` — 대화 기록 261개: 5일(11-16~20) Claude 호출 12,204번·도구 기다림 50.4시간(9월 주 8.5시간)·세션 156개 · 커밋 1번 25초(9월) → 201초 · 게이트 검사 10종(10-01) → 39종 · 11-20 zip 6번(설치 0번 · 1번 약 18분) · STATE 커밋 하루 20~27번(11-16~19) · 아카이브 213번 2.1시간 · 전체 게이트 실측 240초(시뮬레이션 203초).
- 버린 대안: 앱을 기능별 프로그램으로 쪼개기(배포 432MB 중 382MB = 라이브러리 · 빌드 시간 80% = 이미 exe 3개라 분석 3번 → 쪼개면 늘어남) · 문서만 바뀐 커밋 게이트 생략(D-352 G1 미승인 그대로) · 편집 훅 mypy 완전 제거(유일한 형식 검사 · D-016).
- 남은 것(미승인 · STATE 미해결): B 바뀐 파일 검사만 · L 병합 검사 중복 없애기 · M 문서 다이어트 · C·E·F·G 빌드 시험 · 전역 CLAUDE.md 에 J·K·H 를 올릴지(검토안 = 이 결정 커밋 보고).
- 영향 범위: `tools/run_checks.py`(`times_path`·`_log_times`·`_gate_lock` 기다린 초) · `tools/verify_run_checks_offline.py` S8(기다린 초 기록)·S11(시간 기록 3줄·기록 실패 경고) · 운영 방식(T-59 zip 절차·STATE 커밋·세션 운영) · 앱(exe) 동작 변화 없음.
- 상태: ACTIVE

### D-379 [GATE_SPEED] 푸시 때 검사 다시 도는 원인 = git 에 안 올린 docs/plans/ → .gitignore · 안 올린 파일 있으면 게이트가 이름 경고 (2026-11-21, R246)
- 결정(소유자 2026-11-21 원문): 통제 세션 "1번과 3번으로 진행할까요?"(1 = `.gitignore` 에 `docs/plans/` · 3 = 안 올린 파일 경고) → 소유자 "1번 3번 진행해줘".
  - 1 `.gitignore` 에 `/docs/plans/` 추가(지금처럼 git 밖 · 백업 안 됨 그대로).
  - 3 `tools/run_checks.py` 가 통과 뒤 git 에 안 올린(무시 목록에도 없는) 파일이 있으면 개수·이름(앞 5개)을 경고 · `check_stamp.untracked`(`ls-files -z --others --exclude-standard` · 키에서 빠지는 docs/memory·.claude 제외). 판정 방식(키 = 작업 폴더 전체)은 그대로.
- 근거: D-378 N 시간 기록 첫 실측 — 전체 통과 직후 커밋·푸시 2번 모두 푸시가 전체 검사를 다시 돎(193.1초 · 178.2초 · `%LOCALAPPDATA%\coupang-analytics\run_checks_times.csv` 11-21 00:12·00:22 줄). 재현(커밋 직후·추적 파일 변경 없음): 작업 폴더 키 `73763f1…`(통과 기록과 같음) ≠ 커밋 키 `6fef5dd…` · `docs/plans` 빼면 같음 · 추적 파일만(add -u) 키도 같음 → 원인 = 안 올린 `docs/plans/` 10파일(11-12~17 생성). 메모리 사본 동기화는 원인 아님(docs/memory 는 이미 키에서 빠짐). 대화 기록상 푸시 1번 평균 52초(9월) → 115초(11-16~20).
- 버린 대안: 2 `docs/plans/` 커밋(STATE 'git 밖' 표기의 이유 미확인) · 키에서 안 올린 파일 통째로 빼기(그런 파일도 검사 결과에 영향 가능 → '같은 내용 통과' 판정 약화 · D-202).
- 영향 범위: `.gitignore` 1줄 · `tools/check_stamp.py`(`untracked`) · `tools/run_checks.py`(`_warn_untracked`) · `tools/verify_run_checks_offline.py` S12 · 다른 작업 폴더(worktree)에 안 올린 파일이 있어도 이제 경고로 보임.
- 상태: ACTIVE

### D-380 [SALES_SCOPE_SAME_PRODUCT] 통합판매현황 같은 상품명 VID = 관리 VID 와 등록상품(vendorInventoryId)이나 노출상품(productId)이 같을 때만 — 이름만 같은 위탁자 본인 상품·번호 모르는 VID 제외 (2026-11-22, R247)
- 결정(소유자 2026-11-22 "1.3번만 수정해줘" — 통제 세션 질문 3번 "'이름이 같다'만으로 합치지 말고, 같은 쿠팡 상품이거나 쿠팡 화면에서 같은 상품으로 나올 때만 합치도록 좁힐까요?"): D-107 ② 같은 상품명의 다른 VID 는 `sales_summary.related_vids` 에 든 VID 만 관리 상품으로 센다. related = 블록 VID + 블록 VID 와 등록상품 번호가 같은 VID + 노출상품 번호가 같은 VID. 등록상품 번호 = 판매분석 기록 '등록상품ID'(`inventory_ids` · 로그인 실패 계정·지워진 상품도 지난 기록에 남음) + `상품정보_일별`(`product_info.lookup`) · 노출상품 번호 = `_상품ID_전체.json`(`contractor_sheet.load_pid_store`). 번호 읽기 실패 = ⚠ 로그 + 블록 VID 만(넓히지 않음). 같은 질문의 1번('[자체판매상품]' 대장 줄)·2번(대장에 적은 옵션만) = 바꾸지 않음(지금대로 — 매칭된 쿠팡 상품의 모든 옵션 추적).
- 근거: 하위 조사 `output/_분석_261122_시트대조/시트대조_보고.md`(운용 사본 output42 · 11-21 00:10 회차) — D-107 로 합쳐진 같은 이름 VID 360개 중 같은 등록상품·노출상품 339 · 다른 등록상품 12(0원) · 번호 모름 9(301,010원 · 55마켓·벅스). 수정 후 같은 자료 재계산(통제 세션): 같은 이름 VID 360 → 유지 341(같은 등록상품 243 · 노출상품 같음 96 · 등록상품 다르나 노출상품 같음 2) · 제외 19 = 301,010원(bux1004 보냉백 6 · aehee5505 캠핑테이블 2 등 — 판매 기록 '등록상품ID' 로 보면 블록과 다른 등록상품) · 4/1~ 관리 합계 604,027,080 → 603,726,070 · 계산 0.5초. 첫 구현(상품정보_일별만)은 로그인 실패 계정(bux1004·aehee5505)에 보관본이 없어 같은 등록상품 25개(2,979,410원)까지 뺌 → 판매 기록 '등록상품ID' 추가로 해결(시험 T9 추가).
- 버린 대안: 상품정보_일별만으로 판정(실패 계정 자료 없음) · `_raw` 상품조회(덮어써짐 · `settlement_statement_scope.inventory` 는 workbook_sales 를 import 해 순환) · 상품명 비교 없이 번호만으로 묶기(질문 범위 밖 · 넓어짐).
- 영향 범위: `src/coupang_analytics/sales_summary.py`(inventory_ids·related_vids·scope related 인자) · `src/coupang_analytics/workbook_sales.py`(_related·refresh_sales_sheet) · `tools/verify_sales_summary_offline.py` T9 · `docs/CURRENT_RULES.md` §7 · `designs/SALES_SUMMARY.md` §4. 정산서 범위(`settlement_statement_context.py:145`·`settlement_statement_scope.py` ② = D-107 그대로)는 바꾸지 않음 — 같은 기준을 정산서에도 쓸지는 별도 판단(STATE). 운용 PC 반영 = 다음 배포 zip.
- 상태: ACTIVE

### D-381 [SETTLE_ORDER_DETAIL_PAGES] 주문별 매출 = 커서 '' 라도 서버 쪽 수까지 쪽 번호로 받음 · 앞 쪽 줄을 다시 주면 즉시 실패 · 같은 줄 키에 구매확정일(confirmDate) (2026-11-23, R248)
- 결정(소유자 2026-11-23 "2-2 … 별도 세션에서 진행" → 원인·수정 보고 뒤 "1~6 전부 수용, 진행해줘"): `settlement_docs.fetch_order_detail` 쪽 받기(`_order_pages`) ① 받은 쪽 커서가 '' 이고 **쪽 번호가 서버 쪽 수(`-page-total`) 이상**일 때만 끝 ② 커서 '' 인데 쪽이 남으면 커서 '' + 다음 쪽 번호로 쪽 수까지 부름 ③ 커서 없이 부른 2쪽 이상 응답의 줄이 모두 앞 쪽 줄이면 그 자리에서 `SiteChangedError`('쪽 번호로 못 넘김' · 헛호출 1번) ④ 같은 줄 판정 키 = 주문·유형·옵션·배송비 + `confirmDate` ⑤ 실패 근거 쪽마다 `requestPage`. 쪽 수·원본 건수 대조(D-182 ②)·size 10(D-171)은 그대로.
- 근거(하위 세션 t51-orders-evidence · 보고 `output/_분석_261123_T51_증빙/T51_증빙_원인_보고.md`): 운용 사본 output43 실패 근거 45개 전부 1쪽 응답부터 `cursorToken` '' · 서버 쪽 수 2~82 · 받은 달 분포 1~4월 여러 쪽 달 0(5~10월은 14~21/달) → 오래된 달은 서버가 커서를 안 줌 → D-182 ① 이 1쪽에서 멈춤(11-10 부터 매일 19계정 46달 3/3 같은 실패). 재현 P52 ④-d 옛 코드 '주문별 매출 202601 쪽 수 6 · 원본 10 · 줄 10 · 서로 다른 줄 10 — 맞지 않음'(운용 hk66597582 202601 과 같은 모양). Difpick 202605 = 같은 주문 CANCEL 2줄이 확정 05-04 −19,660 / 05-08 −19,659(부분 취소 2번 · 서버 반복 아님). [추정] 실서버가 커서 없이 쪽 번호로 넘겨 주는지는 미확인(11-08 gyi0101 2026-01 16쪽 실측이 근거) → 다음 회차 46달 결과로 확인 · 안 되면 ③ 문구로 바로 드러남.
- 버린 대안: 실패 사유만 남기기(해결 아님) · 커서 '' 를 계속 '끝'으로 두고 달마다 사람 조회(사람 대기열 금지 D-070) · 같은 줄 키 그대로(부분 취소 2번을 중복으로 판정).
- 영향 범위: `src/coupang_analytics/settlement_docs.py`(fetch_order_detail·_order_pages·_order_key·_order_fail) · `tools/verify_settlement_runtime_offline.py`(P52 ④-d·④-e·P56) · `docs/CURRENT_RULES.md` 주문별 매출 줄. 운용 PC 반영 = 다음 배포 zip.
- 상태: ACTIVE

### D-385 [LOGIN_PW_ORDER] 로그인 비밀번호 = 지난번 자동입력으로 성공한 값(지문)을 먼저 · 샵마인 동기화 안전장치 4종 (2026-11-23, R248)
- 결정(소유자 2026-11-23 질문 '비밀번호를 넣을 때 지난번에 성공한 값을 먼저 넣도록 바꿀까요?'·'샵마인 동기화를 켤까요? … 그 전에 안전장치' → "1~6 전부 수용, 진행해줘"): ① `_login_with_candidates`(앱 ①·아침 보충·정산·셀독전환 확인이 모두 거치는 한 곳) 후보 순서 = 지금 대장 후보 중 `_로그인실패.json` 의 성공 지문(ok_fp · HMAC · 평문 없음)과 같은 값이 맨 앞 · 나머지는 D-012 순서 · 대장에서 그 값이 사라지면 기억 무시 · 성공 지문은 앱이 자동입력해 성공했을 때만(세션 재사용·사람 입력 = 안 남김) · 같은 값에 성공·거부가 겹치면 최신 쪽. D-123 24시간·최대 2개·앞뒤 공백(D-018·D-068)은 그대로. ② 24시간 막혀서 안 넣은 값은 '거부'가 아니라 '넣지 않음' 문구. ③ 샵마인(D-195): 자격 없음 = 하루 1번 로그 · 샵마인 값이 24시간 안에 쿠팡에서 거부된 값이면 대장·저장소 안 덮고 ⚠ · 리포트에 '샵마인=대장'(값1/값2/다름 · 값 없음) · 대장을 고치면 비밀번호 후보 바로 다시 반영.
- 근거: 하위 분석 `output/_분석_261123_DW비번/DW비번_샵마인_확인.md` — dalbong1849 대장 행 46(1줄 옛 값)이 '적은 줄 먼저'(`input_list.py:253`)로 1번째 → 10-04~11-22 거부 46회(11월 16) · 맞는 값 = 행 45·48~55(9줄) · wavetech 행 65 같은 모양 20회 · 성공 기억 없음(옛 `login_today.record_success`) · 운용 사본 9-21~11-22 `[샵마인]` 줄 0 = 자격 없음으로 조용히 건너뜀(`ui/app_qt.py:1317`). 구현 `e699d72`(하위 작업 · 핀 D3 · 샵마인 시험 4종 · 게이트 39종 통과).
- 버린 대안: '적은 줄 먼저' 뒤집기(정당하게 고친 값이 1줄인 경우 깨짐) · 저장소 값1 덮어쓰기(D-190 에서 버림) · 안전장치 없이 샵마인만 켜기(샵마인에 옛 값이 있으면 맞는 9줄을 지움 — 가짜 값 재현).
- 영향 범위: `src/coupang_analytics/login_today.py`(record_success·success_first·_blocked) · `pipeline_sales.py`(_login_with_candidates·LoginPwRecentlyRefused) · `shopmine_sync.py` · `ui/app_qt.py`(_maybe_shopmine_sync) · `tools/pin_login_ranks.py` D3 · `tools/verify_shopmine_sync_offline.py`. 남는 것: 성공 기록 생기기 전 첫 로그인 1회 거부 가능 · 운용 PC 샵마인 자격 setup = 소유자. 운용 반영 = 다음 배포 zip.
- 상태: ACTIVE

### D-384 [GSHEET_PULL_BLANKS] 실행 시작 때 결과 구글시트 값으로 마스터의 빈 칸만 채움 (키워드 역머지 직전 · 이번 회차 칸 제외) (2026-11-23, R248)
- 결정(소유자 2026-11-23 "운용 마스터는 매일 처음 시작시 현행화를 해야 함, 너가 지금 구글 시트를 열어서 반영하면 운용PC에서 마스터를 현행화 하면 문제가 해결됨, 검토해줘" → 검토 '현행화 기능 없음 · 마스터→시트 한 방향' 보고 뒤 "1~6 전부 수용, 진행해줘"): `pipeline.run_full` 이 키워드 역머지(`pull_gsheet_keywords`) **직전**에 `pipeline_gsheet.pull_gsheet_blank_cells` → `gsheet_fill.fill_blank_cells`. 사업자 = 시트 이름 같은 것만 · 행 = 마스터 행 번호 그대로이되 블록 머리줄 날짜 칸·상품명·지표 글자(순위행은 키워드까지)가 시트와 모두 같을 때만(다르면 그 블록 건너뜀 + 로그) · 열 = 블록 머리줄 **날짜 글자**(D-368·D-369 위치 이동 때문) · **마스터 칸이 비었고 시트에 값이 있을 때만** · 이번 회차 칸(col_label)·마스터에 없는 날짜 칸 = 안 씀 · 로그 = 사업자별 `결과 시트 → 마스터 빈 칸 채움 N칸` + 합계 + 시트에 없는 사업자 · 읽기 실패 = ⚠ 로그 후 진행 · 저장 = D-376 경로.
- 근거: 결과 시트 반영 = 마스터 기준 값+서식 전체 교체(`gsheet_stats.push_statistics`) — 11-22 통제 세션이 시트 11.19 판매량 410칸을 썼으나 11-23 00:10 미러로 0/410(통제 세션 11-23 시트 읽기 · 머리줄 11.22 생김) · 운용 마스터 11.19 빈 칸(output43). 구현 `bbf86a1`(하위 작업 · `verify_gsheet_offline` [18] ①~⑦ · 시뮬레이션 시나리오 17 순서 fill→pull→push · 게이트 39종 통과).
- 버린 대안: 칸 위치로 대응(날짜 칸 위치 이동) · 시트 값으로 덮어쓰기(마스터 값 훼손) · 키워드 역머지와 읽기 공유(그쪽은 표시값으로 읽어 숫자가 글자 · 핀 시그니처 변경) → 읽기 1번 더 · 운용 PC 에서 개발 PC 마스터 덮어쓰기(T-155 A · 그날 회차 결과 사라질 위험).
- 영향 범위: `src/coupang_analytics/gsheet_fill.py`(새) · `pipeline_gsheet.py` · `pipeline.py` run_full(col_label 계산을 앞으로) · `tools/verify_gsheet_offline.py` [18] · `tools/simulate_pipeline.py` 17 · `tools/pin_l1_contract.py`. 남는 위험: 결과 시트가 날짜 당김(D-369) 전 기준인 채 한 번도 미러 안 됐으면 하루 어긋남(지금 시트는 판매일 기준 · 사실) · 실 시트 첫 확인 = 설치 뒤 첫 회차 로그 N칸. 운용 반영 = 다음 배포 zip(설치 직전 통제 세션이 시트 11.19 410칸 다시 씀 · T-155).
- 상태: ACTIVE

### D-382 [DEPLOY_UPDATE_STOP] 배포 업데이트 = 새 zip 을 임시 폴더에 풀고 `업데이트.bat` 실행 — 설치 폴더 앱·정산 프로그램을 스스로 멈추고 확인 뒤 덮어쓰기·설치·이어 받기 (2026-11-23, R248)
- 결정(소유자 2026-11-23 "내가 배포 파일을 운용 PC에 배포할때 정산 다운로드가 실행되고 있어서, 작업관리자로 들어가서 정산 다운로드 실행파일을 강제 종료하고 배포파일을 업데이트하고 있어. 이 문제를 해결해줘."): `deploy/업데이트.bat` → `deploy/update.ps1` ① 설치 폴더 찾기(예약 작업·바로가기 · 여러 개/없으면 묻기) ② 설치 폴더 exe 로 도는 프로세스 표시 → Y ③ 정산 → 앱 → 나머지 순서로 트리째 종료(`taskkill /F /T` · 00:10 시작 정리와 같은 방법 D-024) ④ 실행 중 0 · 덮어쓸 파일 잠금 0 일 때만 복사(⛔ `output\`·`data\`·`config.json`·`proxies.txt` 안 덮음 · 설치 폴더 파일 안 지움) + 크기·exe 내용 대조 ⑤ `install.ps1`(설치.bat 과 같음) ⑥ 정산·무인 앱을 멈췄으면 재부팅 복구(`--resume`)로 그 회차 이어 받기(같은 회차 규칙 D-091 그대로). 멈추기·잠금 실패 = 복사 안 함 + 이유 + (정산을 멈췄으면) 옛 버전으로 다시 띄움. T-59 '앱 꺼진 채 덮어쓰기' 절차를 대체.
- 근거(하위 작업 조사 · 코드): 지금 절차 = zip 을 설치 폴더에 직접 덮어쓰기 → 실행 중 exe 가 막음 · 멈추는 장치 없음. 강제 종료 영향: 잠금 = OS 잠금이라 프로세스와 함께 풀림(`registry_lock.py:7`) · `_watch_쉼.json` 다음 watch 가 지움(`tools/settlement_download.py:1536`) · 요청기록·완료·상태·마스터 = 임시 파일 → 바꿔 끼우기(`settlement_jobs.py:222`·`settlement_watch.py:109`·D-376). [추정·코드만] 바로 덮어쓰는 파일(`settlement_ads.py:211/259`·`settlement_docs.py:398`·`settlement_evidence.py:132/186`·`settlement_refetch.py:54`·처리기록 CSV 끝 줄)은 반쯤 쓴 채 남을 수 있음 · 받는 중 파일은 '받음' 전이라 다음 실행이 다시 받음. 이어 받기 = `--resume` 앱이 오늘 끊긴 단계만 + 정산 함께 띄움(`ui/app_qt.py:2331`). 구현 `dfc9738` · 시험 `tools/verify_deploy_update_offline.py`(게이트 40종 통과).
- 버린 대안: 작업관리자 강제 종료 그대로 · 설치 폴더에 zip 직접 풀기(실행 중 exe 잠금) · 정산 '멈춤 요청 파일'로 깨끗이 끝내기(`tools/settlement_download.py` 수정 필요 — 다른 세션 편집 중 · 후속 후보).
- 영향 범위: `deploy/update.ps1`·`deploy/업데이트.bat`(새) · `build.bat`(zip 루트·코드 폴더에 넣음) · `INSTALL.md` D절 · `tools/verify_deploy_update_offline.py` · `tools/run_checks.py`. 확인 못 함 = UAC·예약 작업에서 설치 폴더 찾기·`--resume` 다시 띄우기(개발 PC 에 예약 작업 없음 → 첫 운용 배포 때) · 업데이트 도중 00:10 겹침은 막지 않음.
- 상태: ACTIVE

### D-383 [SETTLE_RETRY_REST_PASS] 정산 회차 = 첫 바퀴만 전 계정 · 그 뒤 = 남은 일 바퀴(오류 단계만·못 끝낸 단계·생성 대기·밀린 소급) · 정기 = 회차 첫 바퀴 1번 · 새 요청 0 = 90초 안 기다림 (2026-11-23, R248)
- 결정(소유자 2026-11-23 "정산 다시 시도를 오류 난 계정만 돌게 고칠까요?" → "수용" · 방안 A2·D·E 제시 뒤 "1~6 전부 수용, 진행해줘"): `tools/settlement_download.py cmd_watch` — 회차 첫 바퀴만 `_one_pass`(전 계정 정기+소급) · 그 뒤 바퀴 = `_rest_pass`(`_plan_rest`): 오류 난 단계만 · '사용 중'·잠금 등으로 정기·소급을 못 끝낸 계정 = 그 단계 전부 · 파일 생성 대기 = 받기 · 소급이 일했고 밀린 소급이 남은 계정 = 소급 · 남은 일 바퀴도 새 파일이 있으면 집계. 정기(그날 정산 파일)는 회차 첫 바퀴 1번(D) · `cmd_run` 새 요청 0건이면 sleep(90) 건너뜀(E). 옛 `_wait_pass` = `_rest_pass` 로 합쳐 지움. 3번 규칙(D-373 · 전체·남은 일 바퀴 합쳐 3번)·생성 대기 20분·쉼 표시(D-375)·24:00 끝·연속 실패 = 다시 전체(D-031) 그대로. 광고 진행 달·밀린 광고 달 = 회차 1번(매출성장광고 '기다림'은 하루 늦을 수 있음 · 사실). 셀독전환 90초는 범위 밖(그대로).
- 근거: 방안 `output/_분석_261123_정산재시도/정산재시도_방안.md` — 원인 `_next_rest`(:1302)가 다시 시도할 오류 1건만 있어도 전체 바퀴 · 11-22 2바퀴 = 1바퀴 끝 '40건 처리 — 곧 다음 바퀴'(하루 1번 자료 · 새 정산 파일 0) · 3바퀴 = 오류 69건(21계정)에 53계정 4시간 26분 · 새 파일 0. 구현 보고 `output/_분석_261123_정산재시도구현/정산재시도_증빙_구현보고_1123.md` · 재현 `repro_1122.py`(다음 바퀴 로그인 45계정 → 21~40 · 정기 0) · 구현 `5627726` · 시험 P70·P71·P72(고치기 전 코드 실패·일부러 고장 낸 4종 실패 확인) · 게이트 40종. 추정 효과(11-22 기준): 완료 19:37 → 약 10:30~11:00.
- 버린 대안: A1(오류 계정은 정기+소급 전부 · 약 132분) · B(다시 해도 같은 오류는 회차 재시도에서 뺌 — D-373 ② 소유자 원문 '다른 항목들도 마찬가지임'과 어긋남).
- 영향 범위: `tools/settlement_download.py`(cmd_watch·_rest_pass·_plan_rest·_rest_run·_phase_item·cmd_request 반환·cmd_run·_wait_run) · `tools/verify_settlement_runtime_offline.py` P70·P71·P72 · `docs/CURRENT_RULES.md` 정산 바퀴 줄 · D-170 '2바퀴부터 = 소급'이 코드와 일치. 운용 반영 = 다음 배포 zip.
- 상태: ACTIVE

### D-386 [SETTLE_EVIDENCE_REUSE] 증빙 원본 = PC 에 있는 쿠팡 원본은 다시 요청 안 함(정기 비용 리포트 복사 · 정기 받기 때 증빙 원본도 저장) · 과거 원본은 병행해서 계속 받음 · 20건마다 받기 · 응답 없음 = 그 계정 중단 · D-339 다시받을목록 무인 회차 1번 (2026-11-23, R248)
- 결정(소유자 2026-11-23 E1 질문 '정기 받기 때 받아 둔 비용 리포트를 증빙 원본으로 봐도 될까요?' → "수용임, 다만 정산을 위해서는 과거 자료를 모두 받아야 됨, 그래서 병행 되어야 함. 지금까지 다운 받지 않은 정산 관련 자료는 모두 다운 받아야 함. 매일 받는 자료에는 당연히 추가해서 받아야 함, 그러면 적용된 시점부부터는 정산 관련하여 이전 자료는 받을 필요성이 없어짐." · "1~6 전부 수용, 진행해줘"): E1 비용 리포트 = 정기 받기가 원본 바이트 그대로 보관한 파일(`_keep_cost`)을 증빙 원본 폴더로 복사(`_reuse_originals` · D-187 _reuse_main 방식) · E2 정기 받기(무인·사람 `run`·`download` · 셀독전환 제외) 때 증빙 원본도 같이 저장 → 적용 뒤 새 정산 파일은 증빙 재요청 0 · 과거 원본(판매수수료·윙 등 복사 못 하는 것)은 회차 끝 증빙이 계속 받음(병행 · 다음 회차 이어 받음) · E3 요청 20건마다 받기(`EVIDENCE_BATCH`) · E4 증빙 중 응답 없음('Failed to fetch') = 그 계정 증빙 중단(`NO_RESPONSE`) · D-339 `RF.plan` 다시받을목록을 무인 회차에도 1번(`_cycle_sources` · 공개 웹은 안 읽음). 요청 간격 45~75초·404 HTML 차단 판정·증빙 시간대(D-365) 그대로.
- 근거: `output/_분석_261123_T51_증빙/T51_증빙_원인_보고.md` — 91white 106·WBpeak 180 증빙 요청 = 전부 정기 '받음'·파일 있음 · 비용 리포트 65%(2,146/3,595)는 원본 바이트 그대로 보관 · 42계정 3,595건 × 약 1분 ≈ 60시간 · 받기 = 계정 요청 다 끝난 뒤라 WBpeak 177/180 요청 중 23:20 멈춤 = 받기 0 · 91white 20:16 Failed to fetch 뒤 다음 단계 404 → 차단 처리. 구현 `76cdd1c` · 시험 P73·원본 시험·P68 · 게이트 40종. 추정 효과: 증빙 요청 3,595 → 1,449(−60%) · 남은 과거 원본 약 2회차.
- 버린 대안: 요청 간격 줄이기 · 404 HTML 판정 완화(밴 위험 ↑ · 소유자 2026-10-06 간격).
- 무인으로 못 받는 자료(소유자 판단 · 구현 보고 목록): T-122 라이브 첫 시험 필요 10종(SV-NOTICES·RG-HOME·RETURN-CHANNEL·BI-SUB·RETURN-BOX·SALES-F·REVIEW-DETAIL·AD-UNPAID·EXCHANGE·MA-FEE-DETAILS) · 규칙상 불가 4종(상품 수량 N·셀러월렛 잔액·입금 PIN·밀크런 구간·단가) · 보류 2종(T-93·도움말) · 확인 필요(광고 subtotals 2025 달 D-328 · review_gap 3줄 · gbseller808 배송비 40줄 · 로그인 못 하는 계정 자료 · 1~4월 주문별매출이 실서버에서도 안 되면 화면 실측).
- 영향 범위: `tools/settlement_download.py`(_reuse_originals·_originals_dir·cmd_request every/between·cmd_run every·_evidence_step·_cycle_sources·EVIDENCE_BATCH·NO_RESPONSE) · `tools/verify_settlement_runtime_offline.py` P73·P68 · D-061 해석(비용 리포트 = 정기 받기가 같은 쿠팡 파일을 바이트 그대로 둔 것 = 원본) · D-339(무인 연결). 남은 위험 = `source_checks` 를 watch 프로세스 안에서 돌림(메모리 · MEMLOG 로 감쌈) · 배포 시뮬레이션 S2 = 배포 전 통제 세션. 운용 반영 = 다음 배포 zip.
- 상태: ACTIVE

### D-387 [STAFF_KEYWORD_REMOVE] 직원이 결과 시트에서 지운 키워드 = 마스터에서도 지우고 그 키워드 순위 기록까지 삭제 (지금 코드 그대로 · 문서 '추가만·제거 없음' 정정) (2026-11-23, R248)
- 결정(소유자 2026-11-23 질문 '직원이 시트에서 키워드를 지우면 어떻게 할까요?' → "키워드 순위 기록 삭제해."): 실행 시작 때 직원 키워드 역머지(`gsheet_stats.merge_staff_keywords`)가 시트에서 사라진 키워드를 `wb.clear_keyword_row`로 행·순위 이력째 지우는 지금 동작을 정책으로 확정. AI 선정 키워드 동결(추가만·제거 없음)은 그대로.
- 근거: 하위 분석 `output/_분석_261123_마스터반영/마스터반영_확인.md` 6절 — 코드 `src/coupang_analytics/gsheet_stats.py:316-319`(삭제)와 문서 `docs/OPERATIONS_POLICY.md:13`·`CLAUDE.md`·`designs/GSHEET_UNIFIED.md:191`('추가만·제거 없음')이 어긋남(통제 세션 코드 대조 확인) · 코드 근거 = 소유자 09-20 '시트 값이 기준'.
- 버린 대안: 지운 키워드 기록 보존(문서 쪽) — 소유자 원문과 다름.
- 영향 범위: 코드 변경 0 · 문서 `docs/OPERATIONS_POLICY.md`·`CLAUDE.md`·`designs/GSHEET_UNIFIED.md`·`docs/CURRENT_RULES.md` 문구.
- 상태: ACTIVE

### D-388 [SHOPMINE_PW_SYNC_AUTO] 샵마인 동기화 = 앱 설정 탭에 한 번 입력 뒤 자동 (연결·필드 확인 자동 · 첫날 대조 리포트만 · 다음 날부터 반영 · 대장 값이 지난 로그인 성공값이면 안 덮음 · 거부된 자격은 다시 입력 전까지 재시도 안 함) (2026-11-23, R248)
- 결정(소유자 2026-11-23 운용 PC setup·discover·dry-run 4단계 안내에 "내가 별도 작업 없이 진행되도록 수정해줘."): ① 설정 탭 [샵마인 로그인 입력](`ui/shopmine_login_qt.py` · 비번 가림 · DPAPI 저장 · 배경 연결 확인 · 라벨 = 미입력/저장됨(계정 N건)/거부) ② 필드 자동 확인(`shopmine_sync.resolve_fields` · CLI 와 같은 `make_login`) ③ `app_daily_hook`: 첫날 = 대조 리포트만(`output/샵마인동기화/대조_*.csv` · 값 없음) · 다음 날부터 반영 ④ 거부된 샵마인 자격 = 표시 후 다시 입력 전까지 매일 로그인 안 함(잠금 방지) ⑤ **[Claude 판단 — 소유자 지시 아님 · 확인 필요]** 대장 값이 지난번 자동입력 로그인에 성공한 값(D-385 지문)이고 샵마인 값이 그와 다르면 대장 안 덮음 ⑥ 자격 없음 로그 = '설정 탭 샵마인 칸에 한 번 입력' 안내 · 배포 평문 내보내기(`--export-settings`)에 샵마인 자격 제외(시험으로 막음).
- 근거: 하위 작업 조사 — 업체ID·사용자ID·비번 없이 로그인 불가(`do_login` 5필드 · 사실) · 앱 저장소 샵마인 키 = `__shopmine_login__` 하나(키 이름만) · DPAPI = PC·사용자 전용이라 개발 PC 자격을 안전하게 옮길 방법 없음(암호 문구로 감싸면 그 문구 입력 = 같은 수고) · ⑤ 이유: D-385 안전장치는 24시간 안 거부값만 막는데, D-385 뒤 맞는 값이 먼저 들어가 옛 값이 다시 거부되지 않으므로 샵마인에 옛 값이 있으면 맞는 9줄이 지워질 수 있음 · 첫날은 성공 기억이 없어 리포트만. 구현 `2a3b368` · 시험 6종(`tools/verify_shopmine_sync_offline.py`) · 게이트 40종.
- 버린 대안: 샵마인 앱 자동로그인 파일에서 자격 꺼내기(고정 키 AES 라 가능 — 구현 안 함 · 다른 프로그램 저장 자격 추출 = 소유자 판단) · 배포 zip 에 자격 동봉(평문 금지) · CLI setup 유지.
- 영향 범위: `src/coupang_analytics/shopmine_sync.py` · `login_today.py`(proven_ok) · `ui/app_qt.py`(설정 줄·연결) · `ui/shopmine_login_qt.py`(새) · `tools/shopmine_sync.py` · `tools/verify_shopmine_sync_offline.py`. 남는 것: 소유자가 샵마인 비번을 평소 자동로그인으로만 써서 모르면 샵마인에서 확인·재설정 필요 · ShopmineVersion 고정값이 샵마인 업데이트 뒤에도 통하는지 미확인 · 샵마인에서만 비번 바꾼 계정 = 하루 1회 틀린 값 뒤 다음 날 반영. 운용 반영 = 다음 배포 zip.
- 상태: ACTIVE

### D-389 [SETTLE_FETCH_SCOPE_1123] 2025 달 광고 세부(subtotals) = 받지 않음 · 로그인 못 하는 계정 자료 = 받지 못함(로그인 풀린 뒤) · 정책 보류 2종 = 보류 그대로 (2026-11-23, R248)
- 결정(소유자 2026-11-23 무인으로 못 받는 자료 설명에 답): ① "2025년 달 광고 세부 … 받을지 판단이 필요합니다" → "제외, 받지않음." — 2025 판매 줄 정산 제외(D-328·D-329)와 같게 2025 달 광고 subtotals 는 다시받을목록·재받기 대상에서 뺌 ② "로그인 못 하는 계정의 자료 전부 … 로그인이 풀려야 받습니다" → "로그인 못하는 계정은 받지 못함." — 지금 동작 그대로(T-5 로그인 풀리면 다음 회차가 받음) ③ "(다) 보류(정책상 지금은 안 받음)" — 지급일 아침 정산현황 재조회(T-93)·윙 도움말 수정일(D-296 ④) → "보류".
- 근거: 구현 보고 `output/_분석_261123_정산재시도구현/정산재시도_증빙_구현보고_1123.md` 4절(무인으로 못 받는 자료 목록) · D-386.
- 버린 대안: 2025 달 광고 subtotals 받기(정산 제외 범위라 쓸 곳 없음).
- 영향 범위: 다시받을목록의 2025 달 광고 subtotals 줄 = 제외 표시(코드·목록 반영은 다음 정산 코드 작업 때 · STATE) · 그 밖 코드 변경 0.
- 상태: ACTIVE

### D-390 [PRODUCT_IDENTITY_SPLIT] 옵션이 나뉠 때 이력 = 같은 VID 블록으로만 · 매칭 안 된 대장 상품 = 실행 결과 '확인 필요' · 빈 칸 채움(D-384) 블록 대조에 VID · 직원 키워드 0개 날도 로그 · 옵션 분리 이력 바로잡기 도구 (2026-11-23, R248)
- 결정(소유자 2026-11-23 "11-18 LED 스탠드의 잘못 옮겨진 기록을 바로잡을까요?" → "보완해줘." · T-162 ②③④ = 통제 세션 '제가 진행' 보고에 이의 없음): ① `pipeline_process._migrate_product_blocks` 이름 바꾸기 = 대표(첫) 옵션 **자기 VID 블록에만**(다른 옵션 VID 블록을 첫 옵션 이름으로 바꾸지 않음) · 같은 VID 개명 승계·VID 교체 = 새로 시작·옛 여러 VID 블록 = 대표 승계는 그대로 ② 매칭 안 된 대장 상품 = 실행 결과 종합 '매칭 안 된 새 상품 → 확인 필요' + 목록(`run_result.py`) ③ `gsheet_fill` 블록 대조에 VID(시트 블록 머리줄+2 행 A='VID'·C=값) — 다르면 'VID 다름' 건너뜀 ④ 직원 키워드 반영 0개 날도 로그 한 줄 ⑤ `tools/fix_option_split_history.py`(로그인 없음 · 미리보기 기본 · `--apply` 백업 후 저장 · 앱 실행 중 멈춤 · 근거 = 판매분석 일별·분리 전 백업 · 근거 없는 칸 = 확인 필요).
- 근거: 운용 11-18 로그 줄 535-536(옵션 1→2 때 블랙 VID 96175143725 이력이 화이트 96175143726 블록으로) · 재현 시험(기존 A · 옵션 [B, A]) 수정 전 실패 → 수정 후 통과 · output43 사본 미리보기 = 옮길 칸 34(10.11~11.16 · 판매분석 9 + 분리 전 백업 `통계마스터_261118_180017` 25 · 확인 필요 0) · 적용 전후 44시트 전체 비교 바뀐 칸 408 = 두 블록 지표 6줄 × 34 × 2 · 그 밖 0 · 다른 계정 = 09-25 (주)웰빙곳간 사과초모식초 3개→1개 4칸(판매 0 · 근거 없음 → 확인 필요). 구현 `2c0bae9` · 시험 `tools/verify_option_split_offline.py` 10개 · 게이트 41종. 보고 `output/_분석_261123_T162/T162_보고.md`.
- 버린 대안: 이름 정한 상품은 정규화 전부 건너뛰기(옛 여러 VID 블록 승계가 바뀜) · 미매칭을 ❌ 오류로(쿠팡에 아직 없는 '[등록예정]' 상품도 있음) · 바로잡기를 앱 실행에 넣기(1회성).
- 영향 범위: `src/coupang_analytics/pipeline_process.py` · `run_result.py` · `gsheet_fill.py` · `pipeline_gsheet.py` · `tools/fix_option_split_history.py`·`tools/verify_option_split_offline.py`(새 · 빠른 검사 등록). 운용 바로잡기 순서 = 운용 output 받기 → 개발 PC 도구 `--apply` → 다음 00:10 전 고친 마스터를 운용 output 에 덮어쓰기 + 결과 구글시트 반영(안 하면 D-384 가 시트의 옛 화이트 값을 다시 채움 · VID 같아 ③으로 못 막음). '[등록예정]' 대장 상품도 매일 '확인 필요'로 잡힘(사실).
- 상태: ACTIVE

### D-391 [OWNER_ANSWERS_1123B] 샵마인 ⑤ 유지 · 옵션 묶음 수량 = 상품수정 화면 1번 보기 허용(읽기만) · 대장 마케팅 날짜 지움 = 마스터에도 반영 · gbseller808 배송비 40줄 = 다른 계정에서 도출된 산출식 적용 (2026-11-23, R248)
- 결정(소유자 2026-11-23 원문): ① 샵마인 ⑤(대장 값이 지난 로그인 성공값이면 샵마인 값으로 안 덮음 · D-388 에서 Claude 판단으로 넣음) → "그대로 둠" = 소유자 확인으로 확정 ② 옵션 묶음 수량(N) 대안 → "다른 하나는 상품수정 화면을 한 번만 보는 것 허용." = 상품수정 화면을 옵션 N 확인 목적으로 **한 번** 열어 **읽기만** 허용(저장·수정 버튼 금지 · ⛔ '상품 수정 화면 열지 말 것' 규칙의 이 목적 한정 예외) ③ 대장에서 마케팅 날짜를 지우면 → "반영해." = 마스터에서도 지움(지금은 남음 `pipeline_process.py:428` 부근) ④ gbseller808 상품 못 찾은 배송비 40줄(232,080원) → "로그인 비번 오류로 안됨, 다른 계정에서 도출된 산출식을 적용할것." = 반품 조회 대신 다른 계정 실측으로 확정된 배송비 산출식을 적용.
- 근거: 설명 `output/_분석_261123_미수집설명/미수집자료_설명.md`(D 옵션 N = 새 옵션 첫 달만 모름 192줄 +142,440원 · H gbseller808 40줄 = 배송비 줄만 있고 상품 줄 없음 · 37줄 214,674원 2025 제외 · 관리 몫 0) · 분석 `output/_분석_261123_마스터반영/마스터반영_확인.md` 6절(마케팅 날짜).
- 버린 대안: 옵션명+AI 판정(옵션명 규칙 250/298) · gbseller808 로그인 기다리기(비번 오류).
- 영향 범위: ② 소유자 로그인 화면 읽기 때(T-122·T-126) ③ `pipeline_process.py` 마케팅 날짜 반영 + 시험 ④ 정산 산식 코드(T-82) — 구현 = 다음 작업. 상품수정 화면 예외는 이 목적·1번 한정(다른 목적 = 금지 그대로).
- 상태: ACTIVE

### D-392 [MARKETING_LEDGER_CLEAR] 대장 마케팅 날짜 지움·변경 = 마스터에도 반영(D-391 ③ 구현) · 대장에 마케팅 열이 있을 때만 빈 칸 = 지움 (2026-11-23, R249)
- 결정: 관리대장에 마케팅 열이 있으면 그 칸의 빈 값 = 지움으로 마스터(set_marketing)에 반영한다. 마케팅 열이 없는 입력(셀독계정상품이력관리원장)은 값이 있을 때만 반영(기존 값 유지). 그 회차 대장 값으로 정한 상품은 저장 때 xlsx 계정목록 옛 칸 되읽기(`_sync_marketing_from_index`)가 덮지 않는다.
- 근거: 소유자 11-23 "반영해."(D-391 ③). 하위 세션 재현 — 대장에서 종료일을 바꿔도 저장 때 옛 값으로 되돌아감(실험 RESULT ('2026-09-01','2026-09-20','2026-09-30')) · 원장 입력은 마케팅 열이 없음(`registry_input.py:43`)이라 무조건 지우면 전부 사라짐. 시험 `tools/simulate_pipeline.py` 26c(고치기 전 실패 → 통과) · `tools/verify_gsheet_offline.py` [1]. 구현 커밋 729978a(브랜치 claude/amazing-proskuriakova-92dce7).
- 버린 대안: 빈 칸이면 무조건 지움(원장 입력에서 전부 사라짐).
- 영향 범위: `input_list.py`(Product.mkt_from_ledger) · `product_match.py` · `pipeline_process.py` · `workbook.py`·`workbook_meta.py`(set_marketing from_ledger) · `workbook_index.py`.
- 상태: ACTIVE

### D-393 [SETTLE_SHIP_UNKNOWN_RATIO] 같은 주문·반품 조회로도 상품을 못 찾은 윙 배송비 줄 = 그 줄 달의 '같은 달 윙 상품 정산금 관리 비율'로 나눔 · 모든 계정 똑같이 (D-391 ④ 구현) (2026-11-23, R249)
- 결정: 순서 = 같은 주문 → 반품 조회(자료 오면 그것 먼저) → 이 산식. 산식 = 그 배송비 줄 달의 윙 상품 정산금 중 관리 상품 비율. 그 달 윙 상품 정산이 없으면 관리 몫 0 · 2025 판매 줄 제외(D-328). '반품 조회 못 함'뿐 아니라 '조회했는데 반품 기록 없음' 줄에도 같은 산식을 쓴다. 계정명·금액 조건 없음(D-229).
- 근거: 소유자 11-23 "로그인 비번 오류로 안됨, 다른 계정에서 도출된 산출식을 적용할것."(D-391 ④) · 소유자 11-23 "다른 계정에서 검증된 것은 다른 계정도 동일하게 적용하면 됨." · `output/_검증_261117_정산끝난달/결과_1_배송비.md` 3절(다른 계정 반품 조회 169줄 정답 대비 오차 합: 계정 비율 174,442 · 관리 몫 0 208,872 · 같은 달 윙 비율 61,554 = 최소 · D-269). 시험 `test_d391_unknown_ship_same_month_wing_ratio`(verify_settlement_statements_offline·verify_consignor_statement_offline · 고치기 전 실패 → 통과). 지금 금액 영향 0원(gbseller808 관리 범위 판정 대기).
- 버린 대안: 계정 비율(오차 174,442) · 관리 몫 0(208,872) · '상품 확인 전 배송비' 줄로 다음 정산서까지 미룸(D-306 ②의 이 경우).
- 영향 범위: `settlement_managed_alloc.py`(wing_month_weights) · `settlement_statement_account.py` · `settlement_consignor_month_calc.py`. 판매 비중 분모(D-237)에 이 배송비 판매도 찾은 배송비 줄과 같은 방식으로 들어감(Claude 구현값).
- 상태: ACTIVE

### D-394 [SETTLE_FETCH_SCOPE] 2025 달 광고 subtotals = 받기의심 판정 '제외'·다시받기 목록에 있어도 안 받음(D-389 구현) · 리뷰 이벤트 리포트 0줄 + 공제 = '확인 필요' 안 남김(D-324 ④ 구현) · 빠른정산 ×90% 예상 = 넣지 않음 · 윙 화면 기록 SPECS 정정 (2026-11-23, R249)
- 결정: ① 2025 달 광고 subtotals = 받기의심 판정 '제외'(확인 필요 아님) · `_광고_다시받기.json` 에 적혀도 받지 않음. ② `review_gap`: 리포트 합 0 + 공제 있음 = '' · 리포트 합 ≠ 공제(합>0)·지급 줄 없음 = 그대로 확인 필요. ③ 빠른정산 예상값(18·83) = '지급가능×90%' 규칙 기각 → 지금처럼 금액 없음(계정별 '전부 인출'만 맞는 계정을 따로 넣으면 계정 조건 하드코딩 D-229). ④ 윙 화면 기록(D-340) SV-BI-SUB 응답 조각 = `/tenants/rfm-ss/api/subscription/` · '베타 버전 출시'+'다시 보지 않기' 표지 공지 팝업만 '확인'으로 닫음(그 팝업 안 금지 낱말 0·버튼 1개일 때만) · SV-RETURN-CHANNEL 버튼 = '검색 열기' → '검색'.
- 근거: 소유자 11-23 "제외, 받지않음."(D-389) · D-324 ④ · ③ 분석 `output/_분석_261123_T163_빠른정산/되돌림_요약.txt`(90% 원 단위 일치 18 = 34/99 · 83 = 12/95 · 맞는 계정 tellace83 64/64·gyi0101 52/53 = '전부 인출' · 같은 규칙이면 gbseller808 정적 0/31) · 소유자 11-23 "다른 계정에서 검증된 것은 다른 계정도 동일하게 적용하면 됨." — 전부 인출은 다른 계정에서 맞지 않아 적용 안 함(통제 세션 판단 D-288 · 차이 0 기준). ④ nicoable 화면 11-23(소유자 화면 캡처 — 팝업 표지·'확인' 1개·금지 낱말 없음 · '구독 관리'→'구독 내역 보기' · 반품 '검색 열기'→'초기화'·'검색' · 표 끝 칸 '접수채널') · tellace83 로켓그로스 홈 11-23(가상계좌 자동인출 = 빠른정산과 다른 흐름 — KB §1-15). 시험 verify_settlement_refetch_offline R2 · verify_settlement_offline P11 · verify_settlement_screen_view_offline V7~V9(고치기 전 실패 → 통과).
- 버린 대안: 빠른정산 ×90%(원 단위 불일치) · 가상계좌 자동인출 켜짐 = 전부 인출(돈 흐름이 다름 · 11-23 화면).
- 영향 범위: `settlement_fetch_check.py`·`settlement_refetch.py`·`settlement_ads.py`·`settlement_files.py`·`settlement_screen_view.py`. 남은 실측 = 팝업이 role=dialog 로 잡히는지(첫 view 실행) · 11/30 공지 끝난 뒤 팝업 없음 = '없음'으로 진행.
- 상태: ACTIVE

### D-395 [SETTLE_RUN_RESTART_FINISH] 같은 회차 정산 재시작 = 정기 1번 유지(진행 기록 파일로 이어감) · 마지막 파일 받으면 즉시 종료(빈 바퀴·20분 쉼 없음) (2026-11-23, R249)
- 결정: ① 같은 회차에 정산을 다시 켜도 D-383 '정기 = 회차 첫 바퀴 계정당 1번'을 지킨다 — 남은 일 계획·끝난 정기 단계를 회차별 파일에 남기고 재시작 때 이어간다(재시작 첫 바퀴 = 남은 일 바퀴 · 다른 회차는 0부터 · 시도 수 이어 세기 그대로). ② 받을 파일을 모두 받아 남은 일이 0이면 20분 쉬지 않고 빈 바퀴 없이 바로 '완료·실패 확인'으로 끝낸다(생성 대기·다시 시도할 일이 남았을 때만 20분 간격).
- 근거: 소유자 11-23 원문 "1번은 정기 1번 유지, 2번은 즉시 종료로 반영해줘." — T-164 배포 시뮬레이션(R249 `1777de4` · 14/14 통과) 확인 필요 2건: S4a 재시작 때 첫 바퀴가 전체 바퀴가 되어 4계정 모두 로그인·정기 다시 함(REST_PLAN·PHASE_DONE 메모리만 · cmd_watch 시작 때 비움) · 마지막 파일 뒤 20분 쉬고 로그인 0 빈 바퀴 1번 뒤 완료(R245 도 같음). 결과 `output/_배포검증/R245_261120/시뮬레이션/결과/판정_R249_도구맞춤.txt`.
- 버린 대안: 재시작 = 전체 바퀴(위탁계정 로그인 늘어남) · 마지막 뒤 20분 대기 유지.
- 영향 범위: `tools/settlement_download.py`(cmd_watch·남은 일 바퀴) + 시험·시뮬레이션 판정(S2·S4a). 구현 = T-165(하위 세션 local_6992d0c2).
- 상태: ACTIVE

### D-396 [UNMATCHED_STRUCK_NOT_CHECK] 대장 취소선·판매중지 상품이 쿠팡에서 안 찾아짐 = '매칭 안 된 새 상품'(확인 필요)에 세지 않음 (2026-11-24, R250)
- 결정: 대장에서 취소선·'판매중지' 글자·상태=판매중지/삭제로 표시한 상품(Product.discontinued)이 쿠팡 상품과 매칭되지 않으면 실행 결과 종합의 '매칭 안 된 새 상품'·판정 '확인 필요'에서 뺀다. 로그에는 "대장 취소선·판매중지 상품 N개 = 쿠팡 상품 못 찾음(블록 없음·확인 필요 아님)" 정보 줄만 남긴다. 블록 미생성(D-008)·활성 상품 미매칭 = ⚠ + '확인 필요'(T-162 ②)는 그대로.
- 근거: R249 11-24 00:10 회차 로그 `run_log_261124_001005.log` 69줄 '[입력검증] 취소선 제외: 상품 '접이식 정리함 JK0026'' · 1852줄 kc11345 미매칭 ⚠ · 3544줄 '매칭 안 된 새 상품 3개' 에 포함 · 대장 셀독리스트 AA88 = 유일한 JK0026 줄·strike=True. 소유자 11-24 원문 "쉽게 설명해줘, 그리고 반영해줘." 시험 verify_offline [35] ③-2.
- 버린 대안: 취소선 상품도 계속 확인 필요로 셈(볼 필요 없는 항목이 진짜 확인할 상품을 가림).
- 영향 범위: `pipeline_process._record_unmatched`(← `_finish_account`) · `run_result` 판정 재료(LAST_SALES['unmatched']).
- 상태: ACTIVE

### D-397 [SELDOC_ZEROSELL_AND_STATEMENT_ORDER] 셀독 정산서 대상 = 제로셀 계약 포함(D-206 ③ 재확인 · 코드 반영 전) · 정산서 2종(쿠팡 정산 = 위탁정산서 · 셀독 정산서) 생성 진행 순서 (2026-11-24, R250)
- 결정: ① 셀독 정산서 대상 계약에 제로셀 계약을 넣는다 — 지금 코드 `settlement_seldoc_source.py:23` `EXCLUDE_WORDS` 가 '제로셀'을 빼고 있어 D-206 ③("제로셀도 판매 관련임")과 어긋남 → 코드를 결정에 맞춘다(구현 = T-166). ② 정산서 2종 생성 순서 = ⑴ 소유자: 정산전용상품 '구분' 빈 칸(판정 대기 7계정) · 목표수익금 입력 위치(T-36) ⑵ Claude: 손 입력 8종·정산전용상품 최신 사본 → `output\정산서\입력\` · 셀독 상품군 판정표를 계약서 분석 DB v5 문서ID 로 다시 판정(AI 판정·근거 · 새 관리 상품 포함) ⑶ Claude: 운용 PC 최신 정산 자료로 두 종 생성·검산 → 발행(구글시트·PDF)은 그 뒤.
- 근거: 소유자 11-24 원문 "제로셀 포함, 진행 순서 제안 : 수용". 11-24 오프라인 시험(운용 PC 사본 output44 · 기준일 11-23): 위탁정산서 33곳 생성·검산 38/40(k2min1201·seankim137 = 판매 자료 일부 없음)·'확인 필요' 54칸 · 셀독 정산서 6장 중 bf0621 1장만(bux1004 = 판정표 v4 문서ID `88373c80` 가 v5 에서 다른 계약 · dalbong1849 = 새 관리 상품 16433403804 판정 없음) · 계약 DB v5 = `D:\modusign\계약서_정밀분석\전수\계약서_정밀분석_DB_전수_v5.xlsx`.
- 버린 대안: 제로셀 제외 유지(D-206 ③ 위반).
- 영향 범위: `settlement_seldoc_source.py`·셀독 판정표(`셀독_계약상품군_판정.json`)·`tools/settlement_seldoc.py` · 위탁정산서 입력 폴더.
- 상태: ACTIVE (① 구현 R251 `eccd9c6` · 병합 `98e2512`)


### D-398 [SELDOC_MANAGED_53_TARGET] 셀독 정산서 대상 = 전수 DB v6 '관리대상' 계약 53건 전부(유형 글자와 관계없음) · 벅스 보냉백 유지 · 최소보장·기타 = 일반 양식 · 정산유형은 정산서에 적지 않음(보류) · 투자형 제로셀 3건 넣기 · 발행 = 전부 맞춘 뒤 한 번에 (2026-11-24, R251)
- 결정(소유자 2026-11-24 원문 · 통제 세션 질문 카드):
  ① 신규셀독 계약 분석 v6 정리본(`D:\modusign\계약서_정밀분석\신규셀독\신규셀독_계약자_분석_20261113_v6_정리본.xlsx` · 관리대상 53건) "계약서 내용임, 적용해줘." → 53건 가운데 셀독 정산서를 만들 계약 = "53건 전부"(위탁운영 8 · 위탁판매 2 · 납품 7 포함).
  ② 정산유형으로 대상을 고르자는 제안에 "정산 유형을 정산서에 표기하는 것은 보류임." → 정산유형은 정산서 칸으로 쓰지 않는다(양식 변경 없음).
  ③ 벅스 보냉백 899eb8f0(bux1004 · v6 정산유형 '납품·공급(판매 정산 없음)') = "셀독 정산서 대상 유지"(D-221 ③ 그대로).
  ④ 정산유형 '최소보장'(와이에이치 0458f970 · 디에스유통 제로리스크 e8553b60·08c07cc0)·'기타'((DW)커머스 21cd1c30 · 유라이프 구독 2a7ec7a0 · 큰복상회 4c8baf80) = "일반 셀독 정산서로 넣기"(지금 양식 · 목표 도달율).
  ⑤ (같은 날 앞서 받은 답 · T-166) 투자형 제로셀 3건(tellace83 3e2f0da0 · ljung0622 bb8786a0 · swmall255 9dde6f10) = '넣기' · 발행 범위 = '전부 맞춘 뒤 한 번에'.
- 구현: `settlement_seldoc_source.target_kind` — 계약 DB '계약 통합' 시트 '관리대상' 칸 = '관리대상'이면 '대상', 아니면 기존 `contract_kind`(TARGET_TYPES·제로셀 D-397 · 제외 낱말 · 규칙 밖 = 중단). '관리대상' 칸 없는 옛 DB = 시작 전 중단. 계약 이름·문서ID 를 코드에 넣지 않음(D-229 · 표시는 DB 값).
- 근거: 전수 DB v6(`D:\modusign\계약서_정밀분석\전수\계약서_정밀분석_DB_전수_v6.xlsx` · 11-24 17:03) = v5 4,685 + 새 문서 5 = 4,690 · '관리대상' 53 = v6 정리본 53과 같은 문서ID · 공통 문서의 앱이 읽는 칸 바뀜 0(대조 `output\_작업_261124_계약DBv6\cmp_v6.py`·`v6_53_대조.csv`). 지금 규칙으로는 53건 중 대상 18 · 제외 2 · 규칙 밖 28(중단) · DB 에 없음 5.
- 버린 대안: 정산유형으로 대상 고르기(판매수익 분배·전액 계약자만 · 위탁운영·위탁판매·납품 제외 — 소유자 '53건 전부') · 계약유형 글자 규칙 유지 + 오늘 답만 추가.
- 영향 범위: `settlement_seldoc_source.py`·`tools/verify_seldoc_statements_offline.py`(test_managed) · 셀독 판정표 후보 `output\_작업_261124_T166_상품군판정\후보_입력_셀독\셀독_계약상품군_판정.json`(대응표 이름이 맞는 판정 없던 관리대상 20건 추가 = 대상 18 · 확인 필요 2 greatjar 74878c30·swmall255 63c8c060) · 계약 여럿 계정 상품 배정(bf0621·sg0141n·gyi0101 등) · 위탁운영 계약은 계약금액 0 → 도달율 0 표시(양식은 그대로 · 소유자 확인 필요).
- 상태: ACTIVE (구현 R251 `dd21aa3` · 병합 `98e2512` · 정산서 발행 = T-166 ④ 전부 맞춘 뒤 한 번에)


### D-399 [SETTLE_STATEMENT_BATCH_AFTER_DOWNLOAD] 정산서 배치 = 정산 자료 받기 '완료' 뒤 정산 프로그램이 따로 띄움 · 못 끝난 날 안 돌림 · 성공 계정만 생성 · 구글시트까지 자동(발송 없음) · 모두싸인 연결 보류 · 확인 필요 = 구글시트 '확인 필요' 탭·상태 카드 (2026-11-24, R252)
- 결정(소유자 2026-11-24 원문): "모두싸인 연결은 보류(추후 연결) 나머지는 진행(단계별 완성도 (설계 = D-204, 6단계)_이 되어야 함. 모든 정산파일이 다운받아지면 별도 배치 프로그램이 수행되어 진행함." · "먼저 적용계획을 제시해줘." · "병렬처리로 동시에 진행해줘." · "완료후 검증을 해줘." · 질문 카드 답: 24:00까지 못 끝난 날 = "안 돌림 (권장)" · 일부 계정 실패한 날 = "성공 계정만 생성 (권장)" · 발행 = "구글시트까지 자동" · 확인 필요 표시 = "확인필요는 로그를 분석해야 만 인식됨"·"운용자가 알수 있는 방법이 있어야 함"·"확인필요 탬에 넣어줘." · 산식 = "그동한 조사/분서간 정산을 위한 산출식이 적용되어야 해." · 계획 승인(계획 = `docs/plans/statement-batch-D399-plan-2026-11-24.md`, git 밖).
  ① 띄우는 시점 = `tools/settlement_download.py` `cmd_watch` 가 `output/정산/로그/_완료.json`(회차 받기 완료)을 쓴 직후 `정산다운로드.exe statements --cycle <key>` 분리 실행 · 재시작(--resume)으로 '이미 완료' 분기에 와도 그 회차 배치 기록이 없으면 띄움 · 24:00 미완료 종료 = 안 띄움. 앱(`ui/app_qt.py`)은 띄우지 않음(D-233 정산 작업은 정산 코드만).
  ② 순서 = 입력 확인 → 최신 정산집계(없거나 옛 형식 = stats 1회) → 위탁정산서(옛 xlsx + 새 형식 json·검산) → 검산 통과분만 위탁자정산서 구글시트 → 셀독 정산서 → 지난 결과와 차이 비교 → 보고 · 단계마다 자식 프로세스 · 회차당 1번(`output/정산서/_배치기록.json`) · 잠금 `output/정산서/_잠금/_배치.lock`.
  ③ 실패 계정·판정 없는 계약 = 그것만 건너뛰고 나머지 생성(계정·계약 단위 격리) · 입력 자체가 없을 때만 그 종류 중단.
  ④ 확인 필요(날짜·종류·ID·계정·계약·상품명·금액·사유) = 구글시트 '확인 필요' 탭(매 배치 덮어쓰기) + `output/정산서/_현재상태.txt`(상태 카드) + 보고 파일 — 로그만으로 두지 않음.
  ⑤ 운용 PC 입력 = 개발 PC 묶음(`정산서입력_YYMMDD.zip` · 손 입력·셀독 판정표·대응표·계약 DB 사본) → 운용 PC `deploy/정산서입력_반영.bat` 더하기만 · 평문 비번 원장 사본 안 만듦.
  ⑥ 산출식 = 산식 '완료' 항목은 배치 코드에 반영(코드 반영 감사 = 레인 C) · 예상값 미완료 33항목은 식 확정 전이라 넣지 않음(T-126).
  ⑦ (통제 판단 D-288) 정산일이 지났는데 최종액 회차 지급 줄이 없는 달 = '확인 필요 — 사유' 표시·그 달 상태 '확인 필요'(금액 그대로) · 23:30 뒤 시작해 00:10 정산 멈춤에 잘린 배치는 그 회차 다시 안 돎(다음 회차가 최신 자료로 생성).
- 근거: 11-24 조사 — 완료 신호 = `settlement_download.py:1801` `write_done` 한 곳 · 24:00 미완료는 안 씀(1807-1810) · 정산서 도구 3개 = exe·앱 연결 없음(spec 진입점 3개) · 계정별 격리 없음(statements:48-58·consignor:92-99·groups:123-130) · 개발 PC 실측 위탁정산서 약 21분·셀독 공통 읽기 약 7분 · 산식 121항목 = 완료 64·미완료 35·해당 없음 22(`output\_점검_261118_정산항목체크\정산식_산식미완료_1119.md`).
- 버린 대안: 운용 PC 18시 배치(D-204 ① 시각 — 지금 받기 회차 00:10 · 받기 끝나는 시각이 날마다 다름) · 앱 1분 타이머로 띄우기(무인 앱이 08:00 보충 뒤 종료 · 정산은 24:00까지) · 실패 계정 있으면 전부 중단 · 미완료 날에도 있는 자료로 생성 · 파일 생성까지만(발행은 사람) · 확인 필요 = 보고 파일만.
- 영향 범위: 레인 A `statement_batch.py`·`tools/settlement_download.py`·`deploy/정산_상태확인.bat`·`ui/settlement_status_panel_qt.py`·`tools/verify_statement_batch_offline.py`·`run_checks.py` · 레인 B `statement_jobs_consignor.py`·`settlement_statements.py`·`settlement_statement_context.py`·`tools/settlement_consignor.py`·`tools/statement_inputs_pack.py`·`deploy/정산서입력_반영.bat` · 레인 C 계산 모듈 · 레인 D `statement_jobs_seldoc.py`·`settlement_seldoc_*` · 배포 spec a_settle datas 에 `tools/check_settlement_statements.py` 추가(병합 때) · 정산 탭 화면 표시 = T-171 · 위탁자 새 달 시트 자동 만들기 = T-43 OAuth 뒤.
- 상태: ACTIVE (구현·병합 R253 — B `bffb47b`·C `a8be2c3`·D `2fe81a4`·A `8752887` · T-174 `5c085f4`·T-177 `3133c55`·산식 `e75ab0f`·`8a5e64a`·`a835727` 병합 · 세부 = D-403·D-404 · 남은 = 운용 사본 끝까지 검증(T-179) · 배포 전)

### D-400 [SELDOC_DECISIONS_4_BATCH] 셀독 정산서 결정 4건 — 투자형 카드 = 약정·지급완료 표시 · 규칙 밖 36유형 제안대로 확정 · 나머지 관리 상품 = 관리대장 기준(대장에 없으면 오류 = 확인 필요 탭) · rladygks0221 두 장 (2026-11-24, R252)
- 결정(소유자 2026-11-24 질문 카드 원문 답):
  ① 투자형 제로셀 3건(tellace83 3e2f0da0·ljung0622 bb8786a0·swmall255 9dde6f10 · 2025-10 원금 지급 끝·판매실적 무관 분할 지급) = "카드에 약정·지급완료 표시" — 셀독 정산서 카드 그대로 · 도달율 대신 약정 금액·지급 완료·남은 지급.
  ② 옛 계약 '규칙 밖' 계약유형 36개(AI 제안 대상 5·제외 29·확인 필요 2 · `규칙밖_유형_제안.csv`) = "제안대로 확정" — 확인 필요 2 = 배치에서 확인 필요로 건너뜀.
  ③ 계약 여럿 계정의 나머지 관리 상품 = "나머지 관리 상품 --> 관리대장을 기준으로 함, 계약서상의 상품은 제고가 없는 경우 다른 상품으로 대체됨. 관리대장에도 없는 상품은 오류임. 확인필요 탬에 넣어줘." (앞선 답: "나머지 상품은 셀독 정산서 실적에서 빼고 '확인 필요'로 보고하면 내가 알수 있는 방법이 없음, 운용자가 알수 있는 방법이 있어야 함. 확인필요는 로그를 분석해야 만 인식됨.") — 계약서 품목 글자에 매이지 않음 · '관리대장' 대조 = D-227 '관리대장 기준(지운 상품 포함)'에 따라 원장 계정·상품 이력까지(통제 판단 · 레인 D-2 확인).
  ④ rladygks0221 0458f970(329bc4c0 상계) = "두 장 다" — 계약별 1장 · 상계 관계 = 비고.
- 근거: 레인 D 1차 배정 후보표 `output\_작업_261124_T166_상품군판정\상품배정_1124\`(상품 166 = 대상 84·확인 필요 82 · 결정 대기 계약 0) · 투자형 양식 점검 `투자형_양식점검\`(3건 모두 2025-10 지급 끝 · 지금 카드는 도달률·남은 금액 틀림).
- 버린 대안: ① 지급 내역서 따로·셀독 정산서에서 뺌 ② 36개 목록 보고 정함 ③ 가장 최근 계약에 배정·실적에서 빼고 보고만 ④ 새 계약 1장만.
- 영향 범위: `settlement_seldoc_*`·`statement_jobs_seldoc.py`(레인 D-2 · 카드 task_c7204a45) · 판정표 후보 → 앱 판정표 반영 = 통제 세션 · D-398 ⑤(투자형 '넣기')에 양식을 더함.
- 상태: ACTIVE (구현·병합 R253 `2fe81a4` — ①②④ 코드 · ③ 대장 대조 = 상품 90개 계약 배정 AI 판정 남음(T-174) · ① 투자형 남은 지급 근거 없는 계약 = 고객용 정산서 대신 확인 필요로(D-221 ② · T-174))

### D-401 [STATEMENT_NOTE_PLACEMENT] 새 위탁정산서 판단·비고 문구 자리 = 위탁자 탭 고정 '비고' 상자(위탁자에게 보여도 되는 문장만 · PDF 포함) + 내부 탭 '{n}월 근거'(내부 판단·근거 전부 · PDF 안 냄) (2026-11-24, R253)
- 결정(소유자 2026-11-24 질문 카드 답 원문 — "(가)+(나) 둘 다 (Recommended)"): 질문 = "새 위탁정산서의 판단·비고 문구(예: '확인 필요 — 보류 해제 규칙 미확정', 비즈니스 인사이트 나누기 근거)를 어디에 보여 줄까요? … 승인하신 고정 형식 샘플(D-343)에는 이 문구를 넣을 자리가 없습니다." → ① 위탁자 탭에 고정 '비고' 상자를 두고 위탁자용 문장만 넣는다(PDF 에 나감) ② 내부 판단·근거(judgments·`_근거`·pending_detail 등)는 내부 탭 '{n}월 근거'에 둔다(PDF 로 안 나감).
- 근거: T-175 하위 세션(C-3 local_fcae46d3) 확인 — D-343 승인 샘플에 비고·판단 자리 검색 0건 · 지금 문구는 json 에만(`settlement_consignor_month_out.py` judgments·`_근거`·pending_detail) · 위탁자 탭 = 위탁자에게 가는 PDF.
- 버린 대안: (나) 내부 탭만 · (가) 위탁자 탭 비고만 · (다) 요약 탭에 '확인 필요 n건'만.
- 영향 범위: `settlement_consignor_gsheet_fixed.py`·`_pages`·`_layout`(T-126 그리기 · 74 새 경로 비고 · T-176 ②) · D-343 형식에 상자 1개 + 내부 탭 1개 추가 · 어느 문장이 '위탁자용'인지 = 구현 때 문장 종류별 표(내부 '확인 필요'·추정 문장은 위탁자 상자에 안 넣음 · D-221 ② 와 같은 원칙).
- 상태: ACTIVE (구현·병합 R253 `a835727`(0f417b9) — 위탁자용 문장 2종(정산 예정 금액 안내 · 74 남은 청구 예상값) · 나머지 전부 내부 탭 · 남은 = 상태 '확인 필요' 달의 위탁자 탭 쪽 머리 표기)

### D-402 [STATEMENT_CHECK_STATUS_HEADER] 상태 '확인 필요' 달의 위탁자 탭·PDF 머리 = '확정 전'(1쪽·2쪽·요약 같은 글자) · '확인 필요'와 사유는 내부 '{n}월 근거' 탭·확인 필요 탭만 (2026-11-24, R253)
- 결정(소유자 2026-11-24 질문 카드 답 원문 — "'확정 전'으로 통일"): 질문 = "정산 상태가 '확인 필요'인 달(예: 보류 해제 규칙 미확정 — roum0502 8·9월, ski1121 3~5월)의 위탁자용 PDF는 어떻게 할까요? 지금은 1쪽 머리에 '확정', 2쪽 머리에 '확인 필요'가 찍혀 두 쪽이 다르고, 내부 상태가 위탁자에게 보입니다." → 위탁자 탭 1쪽 머리(`who_line`)·2쪽 머리(`page2_head`)·요약 탭 머리 = '확정 전' · 정산서는 그대로 발행 · 정산 예정 포함·확정 달 글자는 그대로 · 내부 근거 탭은 '상태 확인 필요' 그대로.
- 근거: T-176 하위 세션(C-4 local_1940a414) 발견 — 1쪽 `PENDING_STATUS if pending else "확정"` · 2쪽 `d['status']` 그대로 → 확인 필요 달에 두 쪽 글자가 다름 · D-401 '내부 확인 필요 문장은 위탁자 상자에 넣지 않음'·D-221 ② 와 같은 원칙.
- 버린 대안: 두 쪽 모두 '정산 확인 중' · 확인 필요 달은 위탁자 PDF 를 만들지 않음(그 달 위탁자가 정산서를 못 받음).
- 영향 범위: `settlement_consignor_gsheet_pages.py`(`shown_status`·`_summary_status`)·`settlement_consignor_gsheet_fixed.py`(`page2_head`) · 시험 `tools/verify_consignor_statement_offline.py` test_d402_check_status_header(고치기 전 실패 → 통과) · CURRENT_RULES 위탁자 정산서 줄.
- 상태: ACTIVE (구현 R253)

### D-403 [SETTLE_STATEMENT_BATCH_DETAILS] 정산서 배치 세부 통제 판단 — 기준일·검산 실패 달·원장 읽기 · 셀독 '제외' 상품·근거 없는 상품·판정표 대조 · 시험이 실제 배치를 띄우지 않음 (2026-11-25, R253)
- 결정(통제 세션 판단 · D-288 위임 · 소유자 지시 아님 · D-399·D-400 범위 안 세부): ① 기준일·발행일 = 배치 실행일 ② 검산 실패 달 = 그 달만 구글시트에서 빼고 금액과 함께 확인 필요(`skipped`) ③ 원장 계정이력·정산전용상품 = 구글 실시간 읽기(메모리만 · 평문 사본 안 만듦 · 배치는 ledger_backup 안 넘김) ④ 셀독 상품 판정 '제외'(D-400 ② 제외 유형 품목) = 그 상품만 뺌(계정 안 막음) ⑤ 못 넣은 상품이 전부 '근거 없음'이고 실제 계산이 0 = 확인 필요 한 줄(계정 안 막음) · 관리대장에 없음(오류)·판정 없음 = 0원이어도 막음(소유자 D-400 ③) ⑥ 배정은 판정표만 따르고 코드는 매번 대장 계열 출처와 대조해 어긋나면 '판정표 갱신 필요' 한 줄 ⑦ 투자형 '남은지급확인' 계약 = 고객용 정산서 안 만들고 확인 필요(D-221 ②) ⑧ 시험은 실제 정산서 배치를 띄우지 않음(`_start_statements` 막음).
- 근거: T-177 보고(배치 꼴 실제 인자 = 0장 → 38장 · 건너뜀 111 · abort 없음 · 게이트 42종) · ⑤는 처음 판단 '판매 0원 = 금액 영향 0' 을 실제 계산으로 고침(sg0141n 근거 없음 3개 −30,938) · ⑧ 정산 런타임 시험 1회에 배치 11번(로그 128→139→150 두 번 재현 → 고친 뒤 0 · `f004f3f`).
- 버린 대안: 판매 0원 상품을 무조건 안 막음(−30,938 사례) · 코드가 대장으로 자동 배정(소유자 D-400 ③ '관리대장에도 없는 상품은 오류' · 매번 배정이 달라질 수 있음).
- 영향 범위: `statement_jobs_seldoc.py`·`settlement_seldoc_groups.py`·`statement_batch.py`·`statement_jobs_consignor.py` · 판정표(git 밖) ljung0622 18개 '제외' · CURRENT_RULES 배치 줄 · 남은 것 T-179(끝까지 실행·새 산식 금액 확인·'제외' 상품 정액 배분 몫).
- 상태: ACTIVE (구현 R253 — B `bffb47b`·D `2fe81a4`·A `8752887`·T-174 `5c085f4`·T-177 `3133c55` · 운용 사본 끝까지 검증 전 · 배포 전)

### D-404 [SETTLE_FORMULA_APPLY_R253] 산식 코드 반영 통제 판단 — 17·74·세이버 옛 경로 = D-271 · 신규-01 금액 = D-317 ② · 보류 해제 = '확인 필요' · E1 = 막는 검사 (2026-11-25, R253)
- 결정(통제 세션 판단 · D-288 위임 · 소유자 지시 아님): ① 17 판매자서비스이용료·74 비즈니스 인사이트·세이버 구독료의 옛 경로(옛 엑셀 위탁정산서) 관리 몫 = D-271(소유자 11-17 '등록 상품 비율') · 세이버·BI 는 '기타 공제'에서 떼어 따로 항목 ② 신규-01 캠페인 없는 광고 조정 = 금액 나누기 D-317 ② · 줄 위치만 D-347 ① ③ 21 보류 해제 줄이 있는 달 = 금액 그대로 '확인 필요 — 보류 해제 규칙 미확정' · 상태 '확인 필요'(정산 예정 포함이 먼저) — 차이 0 인 규칙을 하나로 못 정함(roum0502 후보 4개 0 · ski1121 0개 · 2~4월은 달로 나눌 자료 없음 · 추정 금지) ④ 산식 23 정산일 지난 최종액(30%) 회차 지급 줄 없는 달 = 금액 그대로 '확인 필요'(D-399 ⑦) ⑤ D-261 ① '정산 예정 판매 ≥ 0' 을 새 형식 검산(check)에 넣음 — 걸리는 달은 시트에서 빠짐(T-174 모의 305달 중 11달 · 계산을 D-262~D-282 순서로 맞추는 일 = T-178) ⑥ 정산 예정 기록 RG 칸 8개 저장(앞으로 기록분) · 옛 기록은 0 으로 숨기지 않고 '확인 필요'.
- 근거: 감사 표 `output\_점검_261124_산식코드반영\산식_코드반영_감사.md` · 전후(옛 엑셀 관리 지급): roum0502 +15,129 · gyi0101 +279,616 · nicoable +5,802 · 새 정산서 금액 변화 0(측정한 것) · 예정 기록 = `settlement_forecast` RG_DETAIL(output44 RG 예정 59,418줄 중 이 칸 든 기록 0).
- 버린 대안: 보류 해제액을 그대로 더함(PENDING 지급 줄 돈 757,462 를 두 번 셈) · E1 경고만(D-261 원문과 다름).
- 영향 범위: `settlement_statement_deduct.py`·`settlement_statement_account.py`·`settlement_consignor_month_*`·`settlement_forecast.py`·`settlement_consignor_gsheet.py` · 이미 낸 정산서 재발행 = 소유자(T-72).
- 상태: ACTIVE (구현·병합 R253 — `e75ab0f`·`8a5e64a`·`a835727`·`35f3a19` · 배포 전 · 부분 SUPERSEDED by D-405 — ⑤ 막는 검사 범위 = 윙)

### D-405 [CONSIGNOR_STATEMENT_PENDING_SPLIT] E1(상품 줄 정산 예정 판매 ≥ 0) = 윙만 막음 · 로켓그로스 음수(반품이 판매보다 많은 순액)는 쿠팡 값 그대로 통과 (2026-11-25, R254)
- 결정(소유자 2026-11-25 · 통제 세션 질문 카드 답 원문): "(가) 쿠팡 값 그대로 (권장)" — 질문 = 남은 6달(fe3276 10·ljung0622 10·nicoable 11·roum0502 10·11·sg0141n 11)의 로켓그로스 정산 예정 판매 음수 처리 · 카드 설명 = "로켓그로스 음수는 실제 순액과 일치하므로 그대로 두고 막지 않음. 윙은 지금처럼 막음. 옛 엑셀과 금액 차이 0." ① 새 형식 검산 E1 = 상품 줄(이름 묶은 뒤)의 **윙** 정산 예정 판매 < 0 이면 검산 실패(그 달 시트 제외) ② 로켓그로스 정산 예정 판매 음수는 금액을 바꾸지 않고 통과 ③ 'wing_c1' 칸 없는 옛 json 은 전체 예정 판매로 봄(막는 쪽).
- 근거: T-178 보고(`output\_backup\세션기록_20261125\인계노트\T178_보고_1125.md` 4절 · `T178_예정분_1125\bt.txt` — 2026-01~09 판매분석 로켓그로스 음수 119건 = 정산 파일 실제도 음수 119·원 단위 같음 110) · 통제 세션이 최종 코드로 nicoable·sg0141n 4달 다시 계산 = 보고 금액과 같음 · 시험 = 고치기 전 실패(KeyError 'wing_c1'·AttributeError 'pend_wing') → 고친 뒤 통과.
- 버린 대안: (나) 음수 옵션 0 + 나머지에 다시 나눔(상품별 금액이 실제와 달라짐 · roum0502 2달 못 풂) · (다) 그 채널 예정분 전부 빼기(sg0141n 7,942,712 등 빠짐) · 지금대로 시트에서 제외.
- 영향 범위: `settlement_consignor_month_calc.py`(pend_wing)·`settlement_consignor_month_out.py`(pending.wing_c1)·`settlement_consignor_gsheet.py`(_check_pending_sales) · CURRENT_RULES 12절 · 금액 변화 0(검산만) · E1 밖 검산 실패 달은 그대로 시트 제외.
- 상태: ACTIVE (구현 R254 · 배포 전)

### D-406 [SELDOC_ZERO_RESULT] 실적 0·목표 0원 계약의 셀독 정산서 4장 = 실적 0으로 냄 (2026-11-25, R254)
- 결정(소유자 2026-11-25 · 통제 세션 질문 카드 답 원문): "실적 0으로 냄" — 질문 = kimandco 2장(033bfd80·74fd41b0 · 목표 86,940,000·36,900,000 · 실적 0) · bf0621 d4b0be60 · gyi0101 2a7ec7a0(목표 0원)을 낼지 · 카드 설명 = "4장 모두 실적 0으로 표시된 정산서를 만듦."
- 근거: T-177 모의 표(`인계노트\T177_모의_1125\모의_표_T177.md` 9·18·22·108·111줄) — 4장 모두 지금 코드가 만드는 38장에 들어 있음 → 코드 변경 없음. kimandco 관리 상품 5개는 어느 계약 상품인지 근거 없음·판매·정산 0원 = '확인 필요' 줄 그대로(D-403 ⑤).
- 버린 대안: 안 내고 확인 필요 목록에만 · kimandco 2장만.
- 영향 범위: 없음(코드) · STATE T-179 ⑧·미해결 ④⑦ 닫음.
- 상태: ACTIVE

### D-407 [CONTRACTOR_SETTLE_PAYOUT_RATIO] 7:3 계약 정산의 현행 기준 = D-152·D-155 · 메모리의 '계정 합산이 정본' 문구는 현행 아님 (2026-11-25, R254)
- 결정(소유자 2026-11-25 · 통제 세션 질문 카드 답 원문): "D-152·D-155가 현행" — 질문 = 메모리 `settlement-statement-rules` 의 '7:3 은 계정 합산이 정본'과 D-152·D-155(상품군별 쿠팡 실지급 직접 합산) 중 어느 쪽이 맞는지.
- 근거: '쿠팡 정산' 세션 검토 요청(T-185 ④) · 소유자 10-21 "이건 쿠팡 정책을 따라야 함. 내가 결정할 사항이 아님."(소유자발언_모음 175줄).
- 버린 대안: 계정 합산이 현행.
- 영향 범위: 메모리 `settlement-statement-rules.md` 문구를 안내로 고침 · 계산 코드 변경 없음.
- 상태: ACTIVE

### D-408 [SETTLE_COMMON_ALLOC] 판매자서비스이용료 = 원래 위탁자 부담이면 관리 계약이 종료되어도 위탁자 부담 (2026-11-25, R254)
- 결정(소유자 2026-11-25 원문): "원래 위탁자 부담이면 종료 되어도 위탁자 부담임." — 질문 = 관리 계약이 끝날 때 판매자서비스이용료(계약 중 판매가 종료 뒤 구매확정되어 나온 이용료)를 위탁자가 부담하는지.
- 근거: 옛 대화(11-06 "그대로 확정하고 …" · T-185 A1)의 권고가 승인인지 불명 → 다시 물음 · 코드 확인 = `settlement_statement_deduct.py`·`settlement_statement_account.py`·`settlement_managed_alloc.py` 에서 관리 종료일로 이용료를 자르는 줄을 못 찾음(시작만 자름).
- 버린 대안: 종료 뒤 이용료를 회사 부담으로 둠.
- 영향 범위: 코드 변경 없음(현재 동작과 같다고 보임 · 종료 계정 실제 계산으로 확인은 안 함) · 같은 질문에 있던 '최종 정산 = 구매확정 끝난 뒤 마감'은 소유자가 답하지 않음 = 미결정.
- 상태: ACTIVE

### D-409 [STATEMENT_CHECK_WORDING] 옛 엑셀 정산서의 '확인 필요' 글자 = 현행 유지 (2026-11-25, R254)
- 결정(소유자 2026-11-25 원문): "현행유지" — 질문 = 옛 엑셀 정산서에 '확인 필요'라는 글자를 쓸지.
- 근거: 11-06 "정산서은 명확해야 신뢰할수 있어, 그런데 "확인필요"라고 기술되면 안돼."(D-234 인용)와 어긋나는지 T-185 A4 로 물음.
- 버린 대안: 위탁자에게 보내는 옛 엑셀에서만 글자를 뺌.
- 영향 범위: 코드 변경 없음 · 새 형식은 D-401·D-402 그대로.
- 상태: ACTIVE

### D-410 [MANAGED_SCOPE_CONTRACT_WINDOW] 관리 상품 판정 = 상품·계약자별 질문 없이 일반 규칙으로 · 지금 대장에 없어도 이전에 등록되어 판매됐으면 반영 · 특정 상품 제외 코딩 금지 (2026-11-25, R254)
- 결정(소유자 2026-11-25 원문): "관리대장에는 업는데, 이전에 등록되어 판매되고 있었으면 반영해야 함. -->  그런데 정산 관련이면 계약자별 건별상품으로 처리하지 말고 일반화 해서 적용해야 함, 특정 상품은 제외라고 코딩하면 안됨. 그래서 확인 요청한것은 적절하지 않음." · 스타떡볶이 = "반영, 셀독관리대장을 확인하면 알수있음" · 헬스매트 잔금 2,620,000 = "모름, 정산 산출식 적용으로 해결할것."
- 적용(Claude 판단 · 소유자 지시 아님): ① 상품이 관리 상품인지 소유자에게 상품별로 묻지 않고 대장(지금·옛)·원장·계약·쿠팡 등록 자료로 판정 ② '이전에 등록되어 판매' 판정은 지금 규칙 D-227·D-230 그대로 쓰고 넓히지 않음(넓힐지 = 확정된 것 없음).
- 근거(확인): 저장소 `src`·정산 도구에 해당 상품명 조건 0건 · 특정 계정 문자열 조건 0건 · 판정 결과(저장 자료 output44): bws247 스타떡볶이 = 판매 있는 옵션 3개(96057192913 305,950 · 96246507465 35,600 · 95608735187 23,600) 모두 관리 · nicoable 선풍기 F009(117,000) 관리 · Q808·그린라이트·터치펜 = `관리상품_출처판정.json` '관리'(옛 대장 근거) → 코드·판정표 변경 없음.
- 버린 대안: 상품별 포함·제외를 소유자에게 묻기 · 상품명 조건을 코드에 넣기(D-229).
- 영향 범위: T-185 A6·B1·⑤(Q808) 닫음 · 판정표 파일의 '제외' 5건·'본인상품' 145건은 근거 있는 판정(D-229 방식)이라 그대로 · bws247 관리 아님 옵션(판매 0)은 그대로.
- 상태: ACTIVE

### D-411 [CONSIGNOR_STATEMENT_RULES] 윙 반품 회수 택배비 부담 = 학습한 쿠팡 정책(귀책 주체 부담) · 정산서는 쿠팡 정산 자료에 있는 금액만 반영 (2026-11-25, R254)
- 결정(소유자 2026-11-25 원문): "너가 학습한 내용을 반영해." — 질문 = 윙 반품 상품을 가져오는 택배비를 누가 내는지(위탁자/회사/모름).
- 적용(Claude 판단 · 소유자 지시 아님): ① 부담 = 쿠팡 정책대로 귀책 주체 — 고객 변심 = 고객 · 상품 결함·상이·배송 지연 = 판매자(위탁 계정이므로 위탁자) · 쿠팡 시스템 장애 = 쿠팡 ② 정산서 = 쿠팡 정산 줄의 배송비·반품배송비 원문 값만(D-302 ①·D-279) · 쿠팡 자료에 없는 택배사 청구액은 추정해서 넣지 않음(D-146).
- 근거: `docs/COUPANG_WING_HELP_KB.md` 171줄(왕복배송비는 반품 사유 제공자 부담)·315줄(반품배송비 = 귀책 주체 부담) · 코드 = `settlement_consignor_month_calc.ships`(쿠팡 정산 파일의 윙 배송비 줄만 사용) · 택배사 청구 자료는 수집하지 않음(결정·할 일에 항목 없음).
- 버린 대안: 위탁자·회사 중 한쪽으로 고정(쿠팡 정책과 다름) · 택배비 예상액을 정산서에 넣기(근거 자료 없음).
- 영향 범위: 코드 변경 없음 · 택배사에 실제로 낸 돈을 위탁자와 별도로 정산할지는 이 결정에 없음.
- 상태: ACTIVE

### D-412 [SETTLE_STATEMENT_BATCH_AFTER_DOWNLOAD] 관리가 끝난 계정의 '최종 정산 마감 시점' 규칙 = 두지 않음(배치를 실행하면 정산서가 나옴) (2026-11-25, R254)
- 결정(소유자 2026-11-25 원문): "관리자가 배치 프로그램을 실행하면 정산서가 출력될것임 : 불필요함." — 질문 = 관리가 끝난 계정의 마지막 정산을 구매확정이 모두 끝난 뒤 마감할지.
- 근거: T-185 A1 의 남은 질문(D-408 에서 '미결정'으로 둔 것).
- 버린 대안: 구매확정이 끝난 뒤 마감 · 관리 종료일에 바로 마감.
- 영향 범위: 코드 변경 없음 · D-408(종료 뒤 이용료 = 위탁자 부담)은 그대로 · 배치를 띄우는 방식은 D-399 ① 그대로(정산 자료 받기 완료 뒤 정산 프로그램이 띄움 — 위 원문의 '관리자가 실행'으로 바꾸지 않음).
- 상태: ACTIVE

### D-413 [RG_MISSING_COST_DAILY] 정산 줄 없는 주에 받는 로켓그로스 물류비 리포트 = 6종('반출 배송 서비스비' 추가) (2026-11-25, R255)
- 결정(소유자 2026-11-25 원문): "1, 2 모두 권장안 수용, 진행해줘." — 질문 2 = '반출 배송 서비스비'를 받는 목록에 추가할지(권장 = 추가).
- 적용: `settlement_wing_api.CFS_KINDS` 5종 + '반출 배송 서비스비' = 6종. 매일 정산 계획(D-164 ①)·증빙(`settlement_evidence_web`)·받기 의심 대조(`settlement_fetch_check`)가 같은 목록을 쓴다. 판매수수료는 그대로 안 받음.
- 근거: T-183 조사(`side-session-notes` `T183_보고_1125.md` ② · output44) — 정산 줄 없는 주 39(10계정) 중 34주 = 5종 합이 갚은 금액과 일치 · 3주는 갚은 금액이 5종 합보다 큼 합 32,431(hk66597582 2,420 · jazzdream7 7,260 · kc11345 22,751) · 요청 가능한 물류비 리포트 6종 중 목록에 없던 것은 이것 하나 · 쿠팡 자료 100% 받기(D-214). 그 32,431 이 반출 배송인지는 원문 없음(추정) — 받은 뒤 확인.
- 버린 대안: 5종 유지(빠진 리포트가 있는지 확인할 방법이 없음).
- 영향 범위: 정산 코드만(D-233) · 첫 실행 요청 최대 39건, 그 뒤 새 주마다 1건 · 시험 P49(고치기 전 실패 확인) · 운용 적용 = 다음 zip(T-59).
- 상태: ACTIVE

### D-414 [STATEMENT_SPLIT] 옛 엑셀 위탁정산서 로켓그로스 물류비 '예정 줄'(비용 리포트가 아직 없는 주기)의 관리 몫 = 그 주기 판매 비율 × 직전 4주기 환산 계수 (2026-11-25, R256)
- 결정(D-288 위임 · 통제 세션 확정 · 판정 기준 D-268): 관리 몫 = 예정 줄 공제 × min(1, r × k).
  ① r = 그 정산주기 기간의 로켓그로스 판매분석 관리 판매 ÷ 전체 판매(기준일 전날까지 · D-262 ②). 그 기간 판매가 없거나 0~100% 밖이면 그 달 비율(기준일 전날까지) → 앞 달 비율.
  ② k = 비용 리포트가 있는 직전 4주기의 Σ 관리 비용 ÷ Σ(주기 비용 × 그 주기 r)(상한 9 · 분모 0 이면 k = 1).
  ③ 시작기 = 비용 리포트가 있는 앞 주기 중 '관리 판매 비율 > 0 이고 관리 비용 > 0' 인 주기가 하나도 없으면 k = 1. 계정 조건 없음(D-229).
  비용 리포트가 이미 있는 예정 줄과 지급 끝난 줄은 이 결정에 없음(J `a4f1812` 방식 = 구현 때 대조 뒤 확정).
- 근거(예측 시점에 앱이 가진 자료만 · 7계정 · 2026-03~10 · h 1~5주 앞 · 하위 세션 `output\_분석_261125_T130예정줄\재비교_예측시점\보고.md` + 통제 세션이 자료만 읽어 따로 짠 코드로 같은 값 재현 `통제_독립재계산\결과.log`): 계정×달 오차 절댓값 합 = B(줄 판매 비율·그 주기) 54,202,346 · D 누적+시작기 18,248,962 · D 8주기+시작기 15,768,971 · **D 4주기+시작기 13,197,233**(최대 592,597 · B 3,497,812) · 기준일 묶음 단위 B 50,208,636 ↔ 15,940,096. ljung0622 를 빼도 B 보다 작음(6,367,301 ↔ 7,419,778 = −14% · 기준일 묶음 −6%) · 어느 계정 하나를 빼도 B 보다 작음. 구간 나눠 시험: 3~6월에서 잰 구간들 중 4주기가 가장 작고 7~10월에도 가장 작음(8,433,503 ↔ B 19,261,985 · 누적 11,925,001) → 맞춰 고른 값이 아님. 지금 방식(누적 비율 A) = 56,516,854.
- 버린 대안: 지금 방식(A) · B(ljung0622 에서 관리 몫을 크게 넘겨 잡음) · D 누적(전체 +38% · ljung0622 뺀 합은 5,584,891 로 4주기보다 작음) · D 8주기 · 시작기 규칙 없음(7~10월 10,752,518 로 나빠짐).
- 남는 위험(사실): 100원 이상 칸 수는 B 가 더 적음(131 대 138) · 시작기 규칙은 오차를 본 뒤 넣은 것이고 3~6월만 보면 없는 쪽이 작음(4,414,390 ↔ 4,763,730) · 4주기가 B 보다 나쁜 계정 = 91white·gyi0101 · ljung0622 를 빼면 누적이 4주기보다 작음 · 7계정뿐(D-353) · 관리 판정은 지금 값 · 판매분석은 대부분 소급 수집 · 예정 줄 공제 ≠ 그 주기 비용일 수 있음(70/30 두 줄·이월) · 오차 0 이 아님 = 예상값은 '정산 예정(쿠팡 미확정)' 표시와 다음 정산서 차이 줄(D-264·D-266) 그대로.
- 영향 범위: 정산 코드만(D-233) · 구현 = T-130(J `a4f1812` 위 · 아직 안 함) · 옛 엑셀 위탁정산서만(새 형식 영향 없음 = D-356 본문) · CURRENT_RULES 12절 · 발행분 재발행 = 소유자 T-72.
- 상태: ACTIVE (구현 R257 · 부분 SUPERSEDED by D-415 — ② 환산 구간 '직전 4주기' → '직전 3주기' · 근거의 '4주기 최소' 문장)

### D-415 [STATEMENT_SPLIT] D-414 정정 — 예정 줄 환산 계수 구간 = 직전 4주기가 아니라 직전 3주기 (2026-11-25, R256)
- 결정(D-288 위임 · 통제 세션): D-414 ② 의 k = 비용 리포트가 있는 직전 **3주기**로 계산한다. ①③ 과 나머지는 D-414 그대로.
- 근거: D-414 는 구간 4·6·8·10·13·17·26·전체만 재고 4(시험 범위의 끝값)를 최소라고 확정함 = 통제 세션 실수. 1·2·3·5 를 더 재니(`output\_분석_261125_T130예정줄\재비교_예측시점\통제_독립재계산\결과.log` · `ind4.py`): 실제 정산서 모양인 계정×달×기준일 단위에서 3주기가 전체 14,990,101(4주기 15,940,096 · 누적 19,486,961 · B 50,208,636) · 3~6월 5,626,839 · 7~10월 9,363,262 모두 잰 구간(1·2·3·4·5·6·8·전체) 중 최소 · ljung0622 뺀 값 6,579,525(B 7,811,699 = −16% · 4주기 7,380,757). 계정×달×h 단위는 1주기 10,989,945 < 2주기 11,118,678 < 3주기 11,720,468 < 4주기 13,197,233(3주기 ljung0622 뺀 값 5,288,002 · B 7,419,778).
- 버린 대안: 1주기(계정×달×h 는 최소이나 기준일 단위 16,709,818·최대 719,946 으로 나빠짐) · 2주기(기준일 단위 16,016,210) · 4주기(D-414) · 누적.
- 남는 위험: 3주기 기준일 단위 최대 오차 520,100(2주기 453,123 · 5주기 427,240) · 100원 이상 칸 227/391(B 219) · D-414 의 나머지 위험 그대로(7계정·시작기 규칙 사후 · 소급 수집). 91white·gyi0101 에서 B 보다 나쁜지는 3주기로 다시 안 잼.
- 영향 범위: D-414 와 같음(구현 전 · T-130).
- 상태: ACTIVE (구현 R257)

### D-416 [STATEMENT_SPLIT] 옛 엑셀 위탁정산서 로켓그로스 물류비·재고 보상 = 지급 끝난 줄은 쿠팡 원문이 적은 갚은 정산주기마다 그 주기 비용 리포트의 관리 상품 금액 · D-414·D-415 구현과 세부 규칙 (2026-11-25, R257)
- 결정(D-288 위임 · 통제 세션 확정 · 병합 = 소유자 2026-11-25 "권장안 ①로 진행해줘"):
  ① 지급 끝난 줄 물류비 = Σ 갚은 금액 × 그 주기 비용 리포트 관리 비율. 갚은 주기 = `cfsDeductionDetails` + 자기 주기 몫(공제 − 미납 칸). `cfsFeeAdjustmentDetails` 인식일 줄은 비율에서 뺌(공제에서 되돌리고 따로 환급 · D-299). 재고 보상 = 자기 주기 보상 리포트 관리 비율.
  ② 관리 몫 합 = 그 실제 합 + 예정·보류 줄. 비용 리포트 없는 예정 줄 = D-414·D-415 · 비용 리포트 있는 예정 줄·보류 줄 = 전 기간 비율 그대로.
  ③ 상세 없는 줄 · 리포트 없는 주기 · 쿠팡 줄 칸과 5원 넘게 다른 주기 · 갚은 금액보다 적은 리포트 = 전 기간 비율 그대로 + '확인 필요' 금액 표시. 계정 조건 없음(D-229).
  ④ D-414·D-415 에 글로 없던 것: 앞 주기 = 쿠팡 줄과 맞는 2026 리포트만 · 상품 미표기 비용 = 그 주기 r 만큼 관리(시작기 판정은 상품 표시된 비용만) · 판매분석에 빠진 날이 있는 기간도 '비율 못 냄'으로 보고 그 달 → 앞 달 · 2026-01 까지 못 내면 전 기간 비율 + '확인 필요'(7계정 0건).
- 근거: 통제 세션이 output44 지급내역 50파일을 따로 읽음 = 공제 줄 1,013/1,013 상세 합 = 미납 칸(미납 있는 줄 470/470 · 어긋남 0). 하위 세션 원문 손계산(엔진 함수 없이 지급내역 JSON·비용 xlsx 직접 읽음) ↔ 구현: WBpeak 64줄 1,086,827 · oopean 30줄 800,444 · 줄 최대 차 0.0(`output\_분석_261125_T130예정줄\구현\3_J대조표.log` · 표본 1회 = claude-global D-023). 예정 줄 = 통제 `ind4.py` 와 묶음 391·230개 최대 차 0(`2_대조.log` · 기준일 단위 14,990,101 · ljung0622 뺌 6,579,525). 시험 `test_t130_cfs_periods`·`test_t130_cfs_lines`·`test_t130_plan_lines`(고치기 전 66,667 ≠ 30,000 실패 → 통과).
- 금액(기준일 2026-11-23): 비용 리포트 없는 예정 줄 19,965,545 중 관리 2,739,111 → 7,342,254(7계정 · 관리 입금 −4,603,143 · 다른 줄 변화 0). 지급 끝난 줄 = 관리 금액 바뀌는 계정 14(`T130_대조_전후_1125.md` 1-나절).
- 3주기로 새로 잰 것(D-415 '다시 안 잼' 보충): 기준일 단위 B(판매 비율) 대비 91white 402,917 → 468,764(+16% 나쁨) · gyi0101 3,748,460 → 2,984,299(−20% · 최대 오차는 231,150 → 385,896 으로 커짐).
- 버린 대안: D-356 오래된 비용부터 맞추기(전제 '쿠팡은 어느 주기를 갚았는지 주지 않음'이 원문과 다름) · 전 기간 비율(WBpeak 2026-09 49,709 ↔ 원문 5,952).
- 남는 위험: 예정 줄이 맞는지는 비용 리포트가 나온 뒤에만 확인(차이 = 다음 정산서 D-264·D-266) · ljung0622 줄 비율 0.02~0.81 로 크게 움직임 · 주기 일부만 갚은 줄 = 주기 비율(쿠팡이 상품별 순서를 안 줌) · 셀독 계약 상품군은 상품군별 r·k 라 합이 계정 값과 다를 수 있음(금액 안 잼) · 마이너스 물류비 환급의 관리 몫(합 118,540)은 이 결정에 없음.
- 영향 범위: 정산 코드만(D-233) · `settlement_statement_cfs.py`(새 파일)·`settlement_statement_deduct.py`·`settlement_statement_account.py` · 옛 엑셀 위탁정산서·셀독 상품군 · 새 형식 위탁정산서 영향 없음 · 발행분 재발행 = 소유자 T-72 · 병합 = 내용만 한 커밋(하위 커밋 `a4f1812`·`7c748f7` 이력은 올리지 않음 — 실제 이름) · 운용 적용 = 다음 zip(T-59).
- 상태: ACTIVE

### D-417 [CONSIGNOR_STATEMENT_AD_DEDUCTION_PRECISION] 새 형식 위탁정산서 — 쿠팡이 윙 지급 줄에서 이미 뺀 광고비의 달·날짜 위치 = 줄의 판매 달(윙 청구액까지) · 넘는 금액 = 앞 달 모자란 몫 (2026-11-25, R258)
- 결정(D-288 위임 · 통제 세션 확정 · 병합 = 소유자 2026-11-25 "1, 2 모두 권장안대로 진행해줘"): ① 윙 지급 줄 차감 사유 '…광고비'(쿠팡 달 표시 없음)는 그 줄의 판매 달 광고로 보고 그 달 윙 청구액(광고정산 json `summary.nonRod.totalFinalAmount` · 부가세 포함)까지 그 줄 날짜에 둔다. ② 넘는 금액 = 앞 달에 모자랐던 몫(같은 금액인 달 먼저 → 오래된 달 · 지급일 빠른 줄부터). ③ 못 가르는 금액(앞 달 몫도 아님 · 청구 자료 없는 달) = 위치에 넣지 않고 '확인 필요'. ④ 정산 금액·1~9 줄·옛 엑셀은 그대로(날짜별 표·'어디로 갔나요'·광고 검산만 바뀜).
- 근거: 고치기 전 mrc098 2026-04 66,000 · 05 127,478 이 '지급일 미정'(원문 = 05-26~07-01 윙 줄 5개 DONE 에서 이미 뺌) → 고친 뒤 미정 0 · 광고 검산 차 66,000·127,477.9 → 0·−0.1. 통제 세션이 output44 원문만 따로 셈: 윙 광고 차감 24계정 · 달을 걸친 줄 0 · 사유 이름 1종(459건) · 판매 달 합만으로는 108달 중 53달이 청구와 다름(이월) · nicoable 2026-10 청구 1,291,803 − 뺀 1,006,429 = 285,374. 전후 2계정 16달을 통제 세션이 다시 계산(전 = master 8c526d7 · 후 = 999dddc) = 정산 금액 변화 0 · 하위 세션 비교 117줄과 같음. 시험 `test_t186_wing_ad_deducted`·`test_t186_wing_ad_carry`·`test_t186_ad_wing_bills_file`.
- 버린 대안: 로켓그로스 칸만 더함(고치기 전) · 판매 달만 씀(이월 달에 같은 오류) · 오래된 미납부터 전부 갚은 것으로 봄(91white 2026-04 1,108 이 남아 있어도 10월 줄은 자기 청구 8,086 그대로).
- 남는 위험(사실): 이월 줄 안에서 어느 날짜 줄이 앞 달 몫인지는 쿠팡 표시가 없음(판단 = 지급일 빠른 줄부터) · 청구 자료 없는 달(seankim137 2026-05~07 등)과 WBpeak 2026 1,802·ygkim1 2026-01~02 는 '확인 필요' 그대로 · 일부만 빠진 달의 안 빠진 몫이 빠진 날짜에 얹힘(nicoable 2026-10 161,236 · 전부터) = T-186 ② 에서 처리.
- 영향 범위: 정산 코드만(D-233) · `settlement_consignor_month_wingad.py`(새 파일)·`settlement_consignor_month_calc.py`·`settlement_consignor_month.py`·`settlement_statement_account.py` · D-289 ② 의 '지급 순서 누적' 을 검산에서 위치에도 씀 · 운용 적용 = 다음 zip(T-59).
- 상태: ACTIVE
