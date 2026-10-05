## 현재 상태 · 프로젝트 방향
- [⭐⭐새 세션 진입점(2026-10-05 최신): 안정성·배포·결과시트복구 + 커머스 판로 멀티플랫폼 설계](handoff-session-261005.md) — master HEAD=3b7a0ae·게이트10 초록. 설계 전부 구현 보류. 남은 선행=U3 WING정산API·U4 샵마인 CS경계·쿠팡 쓰기 엔드포인트(라이브/소유자)·운용PC 설정URL 교정(사람).
- [⭐도메인 설계 10건 + 멀티플랫폼 대확장(2026-10-05)](domain-design-elaboration-261005.md) — 설계 심화(구현 보류)·병렬 에이전트. 1차=D2·D8 2·3+흡수·D10 CS·H UI 화면 / 2차=멀티플랫폼(쿠팡+스마트스토어·샵마인=주문배송만)+배치수집+정산3층+D3 등록·D4 변경+프로세스개요. SSOT=designs/PLATFORM_INTEGRATION·SETTLEMENT_MODEL·PROCESS_OVERVIEW·DOMAIN_D2/D3/D4/D8/D10·UI_SCREENS. ⭐선행: ~~U1 스마트스토어 API~~ **보류**·~~U2 kw→L1(M1)~~ **완료(2026-10-05·핀 등재)**·남은=U3 WING정산API·U4 샵마인 CS경계·쿠팡 쓰기 엔드포인트 라이브캡처(사무실 라이브·소유자 확인).
- [⭐새 세션 진입점(2026-10-04 최신): 안정성 6종 수정+설정일원화 병합+배포본 생성](handoff-session-261004.md) — master HEAD=6d6937d·게이트 초록. 이중제출·백업401·전원억제(야간 멈춤 차단·라이브 확인됨)·sheet_id방어·로그인대기90초·18시원인. **⭐최우선 미해결=설정 URL 저장소 분열**(18:00 무인이 옛 URL 써서 결과시트 반영 404/400·올바른 URL4개는 메모에). dist 직접운용 금지.
- [새 세션 진입점(2026-10-02): egress 회전+차단IP목록+이미지OFF실험](handoff-session-261002.md) — master 7d27720. 순위 3경로 회전. 밤샘 규모검증 남음.
- [노출순위 프록시 라이브 실측(2026-10-02)](proxy-live-test-261002.md) — DataImpulse 한국 주거용(회전)=통과 100%·Decodo 고정ISP=번아웃·코드 무결. 세팅=proxies.txt+config.json proxy/enabled.
- [프록시 통합(계정별 고정·a-모델)·소유자 하드닝본 적용·기본 OFF·미커밋(2026-10-01)](proxy-integration-off-261001.md) — fail-closed·CDP인증 source==Proxy만·SOCKS규칙·rendezvous·_resolve_proxy(계정별 스킵). 게이트 10종+복잡도+test 5종 초록. 라이브 미검증·밴 위험 상존.
- [⚠IP 정책은 맥락별로 반대(혼동 금지 SSOT)](proxy-ip-policy-by-context.md) — 로그인/수집=고정 IP(신뢰·2차인증), 노출순위(비로그인)=sticky 회전 여러 개(볼륨 번아웃 회피). 10-01 "회전 금지" 추론을 10-02 실측이 반증. "고정=신뢰"는 로그인에만 유효.
- [노출순위 egress 재회전+차단IP목록 구현(2026-10-02)](proxy-rotation-design-261002.md) — 브랜치 proxy-egress-rotation·게이트 초록·미커밋. 차단 egress 기록(TTL72h)→이력IP 선제skip→새 sticky로 재회전. 남은=proxies.txt sessid 여러 줄·라이브·site3.
- [⭐운영대장 4파일 데이터모델 2단계 전환도구(2026-10-01)](handoff-operation-data-model-261001.md) — 소유자 9요구 전부 반영·전환도구3종·수식연동/셀잠금/계약서보강. 커밋 70df784 **푸시 대기(분류기 차단)**. 남은=3단계 앱배선(input_list 다중시트). SSOT=designs/OPERATION_DATA_MODEL.md.
- [⭐새 세션 진입점: 현재 상태 SSOT(2026-09-29)](handoff-session-260929-continued.md) — 매칭 5원인·AI 의미매칭·회사보유재고·정산 2단계·원장 이름규칙·괴물함수 전멸·배포 spec 버그수정. master HEAD=3dc1cf0·게이트9 초록. **최우선=운용PC 재배포**(zip 준비됨)·라이브(사무실).
- [H_ui 화면 수정 10건+점검 규칙(2026-09-30)](handoff-hui-ui-fixes-260930.md) — 7커밋 병합요청·순위간격 입력은 통합 배선 필요·실제 App 점검 시 QSettings 교체 필수(레지스트리 오염 사고 교훈).
- [괴물함수 전멸(2026-09-29)](monster-functions-extinct-260929.md) — browser.wait_for_login·rank.organic_ranks_batch 분해→전체 D+ 0. 핀=FakeBrowser 대체라 위치만 이동. 라이브 실측 남음.
- [커머스 전과정 앱 아키텍처+세션분리](handoff-architecture-parallel-260928.md) — L0플랫폼/L1데이터백본/L2도메인/L3조립·UI 4계층. SSOT=docs/ARCHITECTURE.md·PARALLEL_DEV.md. 통합=병합·도메인=worktree 레인.
- [도메인 분리·연계·통제 설계](handoff-domain-design-260928.md) — 도메인9(D1분석~D9통계). SSOT=docs/DOMAIN_DESIGN.md. 백본 이원화(분석/통계 + 원장). 신규도메인 구현은 별도 세션.
- [셀독등록원장(정산) 설계·1·2단계](feature-ledger-registry.md) — 대장과 별도로 쌓는 원장(시트5·이력3·관리중단+중단일·비번 원문). registry_*.py. 2단계(앱연계) 병합 완료. 라이브 대기.
- [판매상태 불일치 경고(구현완료)](feature-sale-status-mismatch-flag.md) — 대장=판매중지인데 쿠팡=판매중이면 실행날짜칸 적색. 소스=상품조회 productStatus.
- [VID 출처=상품조회/수정](feature-vid-source-from-product-list.md) — vid를 vendor-inventory/search 상품명매칭. vid=헤더 이름칸. 옵션분리·블록명=등록명+옵션라벨·③=sibling_vids.

- [⭐디자인 컨셉 확정: 참고 대시보드 스타일·보라(2026-10-03·앱 적용 보류)](decision-design-concept-261003.md) — 회색 바탕+흰 둥근 카드·보라 단일 강조·아이콘 사이드바·기간 알약·알약 막대 그래프. 시안 "디자인 컨셉 확정" 보드가 기준.
- [⭐저장소 결정: 구글시트로 시작 + 규칙 4가지(2026-10-02·구현 보류)](decision-storage-gsheet-4rules.md) — 돈·재고 원장=앱만 추가 · 채권자 파일 분리 · 저장 계층 한 곳 · 쓰기 PC 하나. 창고 동시 입력 시작 시 DB 이전 재판단.
- [⭐⭐사업 맥락: 위탁관리·회사수익 정산·채권자 370명/300억 상환(2026-10-02)](business-context-consignment-creditors.md) — 기능 대중소 분류의 전제. 상환 배분은 법률 검토 후 소유자 결정·앱은 계산/기록/감사. 고객 CS 범위 미결.
- [⭐앱 범위: 주문·배송=샵마인, 우리=상품등록+관리·통계+문의CS(2026-10-02·CS는 10-05 수정)](app-scope-no-orders-shopmine.md) — 주문/배송/클레임 안 만듦(D5·D6 범위밖). **문의(CS)는 10-05부로 범위 안=신규 D10**. 상품등록은 우리 앱. 홈 시안 캔버스 링크 포함.

## 실행·운영
- [재부팅 자동복구](reboot-recovery.md) — 야간 재부팅 시 --resume(로그온 트리거)로 판매수집 스킵·순위부터. Windows 자동로그인 필요.
- [실행 UI=app_qt·상시가동](runtime-ui-and-always-on.md) — app.py 아님. 설정탭=파일/API키+구글시트 카드(순위값 UI 없음·config.py만). 무인 --auto 야간모드.

## 작업 원칙(피드백)
- [폴백 최소화 원칙(중요)](no-silent-fallback-principle.md) — 폴백 신중히·최대한 금지·불가피할 때만 조건부(로그 명시). 근본 해결/실측 우선.
- [분석 요청=코드 수정 금지](analysis-request-no-code-change.md) — "분석해줘"면 분석만, 명시 수정요청 전까지 편집·커밋 금지.
- [시안 "적용"=기존 위에 끼워 넣기(다시 짜기 금지)](feedback-design-extend-not-redo.md) — 홈 시안 통째 교체를 소유자가 정정(2026-10-05). 공간 부족은 줄 수·여백으로.
- [진단명령=사용자PC 콘솔창 뜸](diagnostic-commands-pop-consoles.md) — 확인 명령 최소화, PowerShell은 bash 감싸지 말고 직접.
- [쉬운 말·전문용어 금지](plain-language-no-jargon.md) — 군사·조어 싫어함, 평범한 한국어.
- [한글 일원화](respond-in-korean.md) — 모든 응답·산출물 한글.
- [실측 근거 수정](fix-from-real-evidence.md) — 추측 금지, 진단로그+파일/이벤트 확인 후 실오류 근거로.
- [데이터로 검증(상태값 아님)](verify-by-data-not-status.md) — 상태 표기보다 실데이터로 판정.
- [커밋=코드+설계서+메모리 동시](commit-with-design-and-memory.md) — 코드 커밋 시 DESIGN/HANDOFF·메모리 같이 갱신.
- [커밋마다 4묶음 자동화](commit-4bundle-automation.md) — pre-commit 훅이 외부 메모리를 docs/memory 미러링·DECISIONS 경고. 새 클론은 install_hooks 1회.
- [코드 건강 규칙(회귀 방지)](code-health-regression-gate.md) — 커밋 전 run_checks 초록 필수·테스트서 실API 금지(모킹)·CC≤15/파일≤600·건강파일 미접촉·되돌림은 근거.
- [판단 흐려지면 새 세션 권고](recommend-new-session-when-degraded.md) — 긴 세션 조짐 시 능동적으로 /clear 권고.

## 로그인·세션(정책)
- [로그인 정책 고정](login-policy-real-browser-only.md) — 실제 Chrome+CDP 자동입력만, HTTP 위장로그인 금지, 창 기본숨김.
- [로그인 2차인증=위치기반](login-2fa-location-based.md) — 사무실만 OTP 없이 통과, 집=2차인증(5회오류 계정잠금). skip_on_otp=배치서 건너뜀.
- [로그인 차단=세션우선+서킷브레이커](login-block-session-first-circuit-breaker.md) — Akamai 차단은 로그인 POST서 표면화, 연속3회면 로그인 생략.
- [쿠팡 세션 하루내 만료](coupang-session-short-lived.md) — 세션 재사용 무인수집 전제 깨짐, 매 실행 재로그인(사무실).
- [OpenAPI 불가(위탁운영)](coupang-openapi-not-available-consignment.md) — 위탁계정이라 판매자 API키 발급불가 → WING 세션이 유일 경로.
- [샵마인 아키텍처 실증](shopmine-architecture.md) — .NET+WebView2(실제 Chromium)+SQLite, 지문위조 아님.

## 입력·수집·데이터
- [노출상품ID(productId) 범용 소스 API](api-productid-source-vendor-items-with-vendoritems.md) — vendor-inventory-items-with-vendorItems/{id}가 옵션별 productId+아이템위너 제공. 상품조회 search엔 pid 없음.
- [입력=셀독 관리대장](input-ledger-format.md) — 헤더 2행·vid/pid 없음, 구글시트 원본, 취소선·상태컬럼 제외. 여러줄 셀=첫줄만. 그로스재고 역기록(AD열).
- [대장 스코핑 추적](ledger-scoped-tracking.md) — 추적범위=대장 상품만, product_match.scope_to_ledger로 매칭.
- [판매데이터 API 직접조회](sales-data-api-vi-detail-search.md) — vi-detail-search POST(x-xsrf-token), 지표매핑 확정, 당일 무활동 상품 vid 보강.
- [재고현황 API(로켓그로스)](inventory-api-rfm-search.md) — inventory-health-dashboard/search POST, orderableQuantity=판매가능재고, 계약계정전용.
- [쿠팡 판매데이터 익일반영](coupang-sales-data-lag.md) — 당일 리포트 0행은 정상, 수집은 D-1 이전.

## 키워드
- [키워드 방법론(AI 앵커)](keyword-methodology-ai-anchor.md) — 4소스→핵심/연관판정→Score→AI종합선정(OpenAI)→순위진단→권고제목. 띄어쓰기 변형은 별개(쿠팡 동일 아님).
- [매일 통계·키워드 동결](daily-stats-keyword-freeze.md) — 첫날 동결(마스터 이어쓰기), 상한7·하루2 발굴, 직원입력도 동결.
- [네이버쇼핑 API 종료](naver-shopping-api-terminated.md) — shop.json 2026-07-31 종료 → 경쟁강도 소스 소멸.
- [Wing 키워드데이터 구독게이팅](wing-keyword-data-subscription-gated.md) — 순위(N위)는 Wing에 없음, 오가닉노출은 무료.

## 순위(노출조회)
- [파이프라인 3단계 분리](pipeline-3stage-separation.md) — ①판매수집(로그인) ②키워드선정 ③순위조회(②③ 로그인불필요).
- [순위 안티차단=서킷브레이커](rank-antiblock-circuit-breaker.md) — 트래픽최소화+서킷브레이커(cooldown 900s·MAX2), 검색간격 45~75s(config.py만).
- [반자동 순위+정확 노출명](semi-auto-rank-and-exposed-name.md) — 앱이 자동입력+Enter·화면만 읽음. 차단=쿨다운재개. 계약명=검색결과 정확명(vid 앵커).
- [순위 프라임 후 fetch](coupang-search-prime-then-fetch.md) — 콜드fetch 403, 검색1회 프라임 후 fetch(기본은 직렬).
- [쿠팡=붙여넣기 차단·타이핑만](coupang-blocks-paste-requires-typing.md) — 붙여넣기=차단, 한 글자씩 타이핑=통과.
- [순위 차단=50위 placeholder](rank-blocked-placeholder-50.md) — "50위"는 차단/미측정 혼동 placeholder, 차단시 공란화.
- [지문 정합(1·2단계)](fingerprint-consistency.md) — 실제 Chrome153·webdriver false·전부 정합. TLS/JA3(3단계)=보류.
- [핵심요구: 정확등수 매일](session-handoff-exact-rank-required.md) — 상품×키워드 정확 N위 매일(근사 불가). 해법=반자동.

## 출력·구글시트·배포
- [상세페이지 이미지 추출(A안 CDP attach)](detail-image-extraction.md) — 사용자 실제 Chrome에 붙어 대표+상세 이미지만 DOM 스코핑 추출. src/detail_images.py.
- [출력=셀독 서식](seldoc-output-format.md) — 시트=사업자, 상품블록, 키워드 노출순위, 재고, 일자 가로, apply_style 서식고정, 목차/마케팅.
- [구글시트 통합 스펙](gsheet-unified-spec.md) — 입력=관리대장·출력=결과시트(계정목록 미러+통계). 계정목록 11열(회사재고·그로스재고 포함). SSOT=designs/GSHEET_UNIFIED.md.
- [exe 배포(다른 PC)](exe-packaging-deploy.md) — build.bat→PyInstaller onedir→zip(폴더째). 무설정 설치(설정 자동이식). Defender 오탐=보안제외 먼저.
- [날짜컬럼=실행날짜 규칙](date-column-run-date-rule.md) — 라벨=작업실행일, 순위=실행일·판매=전일(D-1) 같은컬럼, 미실행일=날짜만+공란.

## 참조
- [입출력 정의서 v1(파일 칸↔화면 칸 1:1)](io-definition-spec.md) — 앱이 읽고/쓰는 128칸을 화면·필수·형식·검사·민감과 1:1. 구현 시 SSOT=designs/IO_DEFINITION.md. 현재 정의/시안만(구현 보류). 5영역 배정 ✅(계약·사업·채권자→D8·마케팅→D1·문의CS→신규 D10·소유자 2026-10-05).
- [정산 도메인 지식(D8 구현 입력)](settlement-domain-knowledge.md) — 지급일 규칙6·공휴일/영업일·금액식3·파싱·불변식·운영위탁 계약. SSOT=designs/COUPANG_SETTLEMENT_DOMAIN.md + coupang_golden_cases.json(100%통과=완료). 미구현.
- [쿠팡 공식 운영지식](coupang-official-reference.md) — 상품등록·주문·배송·수수료·SEO/ID(productId 가변/vendorItemId 불변).
- [상품명 규약: 대장=담당자명·결과=노출명](product-name-convention-ledger-vs-result.md) — 결과파일 긴 이름=쿠팡 노출명(정상). "낡았다" 오판 금지.
