## 진입점 (최신 먼저)
- [⭐⭐새 세션 진입점 2026-10-06: 구현 Wave1 통합(D8흡수·D10CS·D2소싱·통합앱+보라테마·정산 배치다운로드·윙30%)](handoff-session-261006.md) — 도메인 전용 세션 정책 가동·master 통합·게이트15종. 다음=L1핀·사무실 라이브(정산 probe·쿠팡 쓰기 캡처)·소유자결정(정산 지급일·계약금액)
- [⭐화면 시안 진입점 2026-10-06: 메뉴 v3.3 대13·중84 전 화면·정의서 137칸·시안 v32](handoff-design-mockup-261006.md) — 시안 주소·보관사본+생성스크립트·메뉴 SSOT=시안 A 보드
- [시안 세부 승격 1차: 공용 위젯+홈 변동 추이(실데이터)](impl-home-trend-widgets-261006.md) — widgets_qt 재사용·verify 미등록·1페이지=60 확인 대상
- [구현 Wave1: D2 소싱 1단계](impl-d2-sourcing-261006.md) — 도메인 전용 세션 첫 배정·master 병합. 남은=L1핀·라이브·UI 02-x
- [구현 Wave1: D10 CS 수동 트래커 1단계](impl-d10-cs-tracker-261005.md) — K 레인·master 병합. 남은=UI·config키·2단계 수집
- [구현 Wave1: D8 흡수 원장 3종(업무일지·계약·채권자)](impl-d8-absorb-ledger-261005.md) — E 레인·master 병합. 남은=UI·config키·2·3단계
- [통합 앱 실행 셸 1차 ui/app_integrated.py](impl-integrated-app-shell-261005.md) — 사이드바13+신규 도메인 패널·기존 app_qt 미접촉. 남은=theme_qt·7탭 승격
- [도메인 설계 10건+멀티플랫폼 확장 2026-10-05](domain-design-elaboration-261005.md) — SSOT=designs/PLATFORM_INTEGRATION·SETTLEMENT_MODEL·DOMAIN_D2~D10·UI_SCREENS
- 이전 진입점(기록): [10-05 설계완료→구현착수](handoff-session-261005.md) · [10-04 설정URL 분열(미해결)](handoff-session-261004.md) · [09-30 H_ui·QSettings 교체 필수](handoff-hui-ui-fixes-260930.md)
- [운영대장 4파일 데이터모델 2단계 전환도구](handoff-operation-data-model-261001.md) — 커밋 70df784 푸시 대기. 남은=3단계 앱배선. SSOT=OPERATION_DATA_MODEL.md
- [아키텍처 4계층+세션분리](handoff-architecture-parallel-260928.md) · [도메인 분리·연계·통제](handoff-domain-design-260928.md) — SSOT=docs/ARCHITECTURE·PARALLEL_DEV·DOMAIN_DESIGN

## 사업·범위·결정
- [⭐⭐사업 맥락: 커머스 판로·위탁관리·사업4종·채권자 370명/300억](business-context-consignment-creditors.md) — 상환 배분=법률 검토 후 소유자·앱은 계산/기록/감사
- [앱 범위: 주문·배송=샵마인, 우리=등록+관리·통계+문의CS(D10)](app-scope-no-orders-shopmine.md) — D5·D6 범위밖
- [디자인 컨셉 확정(보라)·통합앱 적용됨 2026-10-06](decision-design-concept-261003.md) — 회색 바탕·흰 카드·보라·흰 사이드바. ui/theme_qt.py 적용·기존 app_qt는 청록 유지
- [저장소=구글시트로 시작+규칙4](decision-storage-gsheet-4rules.md) — 원장=앱만 추가·채권자 분리·저장계층 한 곳·쓰기 PC 하나
- [입출력 정의서 137칸(파일↔화면 1:1)](io-definition-spec.md) — SSOT=designs/IO_DEFINITION.md·도메인 배정 확정
- [정산 배치다운로드·월집계·계약자 정산금액 2026-10-06](settlement-batch-download-decisions.md) — 지급일 실측 불일치 2건
- [정산 도메인 지식(D8)](settlement-domain-knowledge.md) — SSOT=COUPANG_SETTLEMENT_DOMAIN.md+골든케이스
- [셀독등록원장 설계·1·2단계](feature-ledger-registry.md) — 대장과 별도 원장·라이브 대기
- [판매상태 불일치 경고](feature-sale-status-mismatch-flag.md) · [VID 출처=상품조회·옵션분리](feature-vid-source-from-product-list.md)

## 작업 원칙(피드백·정책)
- [⛔불변: 메모리→CLAUDE.md 이관·CLAUDE.md 200라인 이하(넘으면 색인+분리)](policy-memory-to-claudemd-200line.md) — 모든 세션 공통·영구. SSOT=전역 CLAUDE.md
- [⭐정확도 우선·레인 간 요청 규칙(소유자 2026-10-06)](feedback-accuracy-over-speed-and-lane-handoff.md) — 환경 사실은 확인 후 보고(못 하면 추정 분리)·브랜치 master 맞춘 뒤 착수·공유/배포 요청은 단위 끝에 한 번·결정은 받은 세션이 통합에 즉시 전달
- [⭐도메인별 작업=도메인 전용 세션(worktree 레인)](policy-per-domain-sessions.md) — 공유파일·병합은 통제 세션 직렬
- [통합 앱 완성 전 기존 앱 무중단](keep-existing-app-running-until-integrated.md) — 신규 greenfield·배선 전 휴면
- [시안 "적용"=기존 위에 더하기(다시 짜기 금지)](feedback-design-extend-not-redo.md)
- [분석 요청=코드 수정 금지](analysis-request-no-code-change.md) · [실측 근거로 수정](fix-from-real-evidence.md) · [데이터로 검증](verify-by-data-not-status.md)
- [폴백 최소화](no-silent-fallback-principle.md) · [코드 건강 게이트](code-health-regression-gate.md) · [괴물함수 전멸 기록](monster-functions-extinct-260929.md)
- [커밋=코드+설계서+메모리](commit-with-design-and-memory.md) · [커밋 4묶음 자동화(install_hooks 1회)](commit-4bundle-automation.md)
- [쉬운 말·전문용어 금지](plain-language-no-jargon.md) · [한글 일원화](respond-in-korean.md) · [진단명령=콘솔창 뜸·최소화](diagnostic-commands-pop-consoles.md)
- [판단 흐려지면 새 세션 권고](recommend-new-session-when-degraded.md)

## 실행·로그인
- [실행 UI=app_qt·상시가동·설정탭 일원화](runtime-ui-and-always-on.md) · [재부팅 자동복구 --resume](reboot-recovery.md)
- [파이프라인 동시 실행 방지(교차 프로세스 잠금)](feature-pipeline-single-run-lock.md) — 열어둔 GUI+18:00 무인 동시 run_full 차단·유휴 GUI는 잠금 안 쥠(무인 항상 실행)·⚠라이브 미검증
- [로그인=실제 Chrome+CDP만(위장 금지)](login-policy-real-browser-only.md) · [2차인증=위치기반(사무실만)](login-2fa-location-based.md)
- [로그인 차단=세션우선+서킷브레이커](login-block-session-first-circuit-breaker.md) · [쿠팡 세션 하루내 만료](coupang-session-short-lived.md)
- [OpenAPI 불가(위탁)→WING 세션 유일](coupang-openapi-not-available-consignment.md) · [샵마인=WebView2 실증](shopmine-architecture.md)

## 입력·수집
- [입력=셀독 관리대장(헤더2행·여러줄=첫줄)](input-ledger-format.md) · [대장 스코핑 추적](ledger-scoped-tracking.md)
- [판매데이터 API vi-detail-search](sales-data-api-vi-detail-search.md) · [재고 API(RFM) orderableQuantity](inventory-api-rfm-search.md) · [판매데이터 익일반영](coupang-sales-data-lag.md)
- [productId 소스 API](api-productid-source-vendor-items-with-vendoritems.md) · [상품명 규약: 대장=담당자명·결과=노출명](product-name-convention-ledger-vs-result.md)

## 키워드·순위
- [키워드 방법론(AI 앵커)·띄어쓰기=별개](keyword-methodology-ai-anchor.md) · [매일 통계·키워드 동결](daily-stats-keyword-freeze.md)
- [네이버쇼핑 API 종료](naver-shopping-api-terminated.md) · [Wing 키워드 구독게이팅](wing-keyword-data-subscription-gated.md)
- [파이프라인 3단계](pipeline-3stage-separation.md) · [핵심요구=정확 등수 매일](session-handoff-exact-rank-required.md)
- [반자동 순위+정확 노출명](semi-auto-rank-and-exposed-name.md) · [안티차단 서킷브레이커·간격 45~75s(설정탭 덮어쓰기)](rank-antiblock-circuit-breaker.md)
- [붙여넣기 차단·타이핑만](coupang-blocks-paste-requires-typing.md) · [프라임 후 fetch](coupang-search-prime-then-fetch.md) · [50위 placeholder](rank-blocked-placeholder-50.md) · [지문 정합 1·2단계](fingerprint-consistency.md)
- [⚠IP 정책 맥락별 반대(로그인=고정·순위=회전)](proxy-ip-policy-by-context.md) · [프록시 라이브 실측](proxy-live-test-261002.md) · [egress 회전+차단IP](proxy-rotation-design-261002.md) · [프록시 통합(초기 기록)](proxy-integration-off-261001.md)

## 출력·배포·참조
- [출력=셀독 서식](seldoc-output-format.md) · [날짜컬럼=실행날짜](date-column-run-date-rule.md) · [구글시트 통합 스펙](gsheet-unified-spec.md)
- [상세 이미지 추출(CDP attach)](detail-image-extraction.md) · [exe 배포·Defender 보안제외](exe-packaging-deploy.md) · [쿠팡 공식 운영지식](coupang-official-reference.md)
- [정산 다운로드 상태 모니터링(heartbeat+앱 상태카드)](feature-settlement-status-monitoring.md) — 창 없는 watch 생존·상태 색 배지·멈춤 의심. Qt 지연import 필수(게이트 PySide6 없음)
