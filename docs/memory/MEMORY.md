## 진입점 (최신 먼저)
- ⭐⭐**현재 핸드오프 SSOT = repo `STATE.md`**(2026-10-08 session-kit 전역 전환부터). 아래 handoff-* 메모리는 **아카이브**(recall만·새로 만들지 않음). 세션 종료=`/session-close`.
- [기록용: 구현 Wave1 통합 2026-10-06](handoff-session-261006.md) — 도메인 전용 세션 정책·master 통합·게이트15
- [⭐화면 시안 2026-10-06: 메뉴 v3.3 대13·중84·정의서137칸](handoff-design-mockup-261006.md) · [시안 승격1(공용위젯+홈추이)](impl-home-trend-widgets-261006.md)
- 구현 Wave1 1단계(전부 master 병합·남은=UI·config키·2·3단계): [D8흡수원장3종](impl-d8-absorb-ledger-261005.md) · [D10 CS트래커](impl-d10-cs-tracker-261005.md) · [D2 소싱](impl-d2-sourcing-261006.md) · [통합앱 셸](impl-integrated-app-shell-261005.md)
- [도메인 설계10+멀티플랫폼 2026-10-05](domain-design-elaboration-261005.md) — SSOT=designs/PLATFORM_INTEGRATION·SETTLEMENT_MODEL·DOMAIN_D2~D10·UI_SCREENS
- 이전 진입점(기록): [10-05](handoff-session-261005.md)·[10-04 설정URL분열](handoff-session-261004.md)·[09-30 H_ui](handoff-hui-ui-fixes-260930.md)·[운영대장4파일](handoff-operation-data-model-261001.md)·[아키텍처4계층](handoff-architecture-parallel-260928.md)·[도메인분리](handoff-domain-design-260928.md)

## 사업·범위·결정
- [⭐⭐사업 맥락: 커머스 판로·위탁관리·사업4종·채권자 370명/300억](business-context-consignment-creditors.md) · [앱 범위: 주문배송=샵마인·우리=등록+관리+통계+CS(D10)](app-scope-no-orders-shopmine.md)
- [디자인 컨셉(보라)·통합앱 적용](decision-design-concept-261003.md) · [저장소=구글시트+규칙4](decision-storage-gsheet-4rules.md) · [입출력 정의서137칸](io-definition-spec.md)
- [정산 D8 확정 사실(운용·API·규칙 — 상태는 STATE.md)](settlement-batch-download-decisions.md) · [정산 도메인 지식 D8](settlement-domain-knowledge.md) · [셀독등록원장](feature-ledger-registry.md)
- [판매상태 불일치 경고](feature-sale-status-mismatch-flag.md) · [VID 출처=상품조회·옵션분리](feature-vid-source-from-product-list.md)
- [⭐셀독 정산서 규칙: 저장=D:\토탈셀러\쿠팡 정산 자료·원천=앱 수집분만·쿠팡 실지급→계약 7:3(계정 합산)](settlement-statement-rules.md)

## 작업 원칙(피드백·정책)
- [⛔불변·전역: 메모리30~50줄·CLAUDE.md<200·핸드오프=STATE.md·DECISIONS D-번호 append-only·종료=/session-close·커밋[R{n}]](policy-memory-to-claudemd-200line.md) — session-kit 전역 일원화. SSOT=전역 CLAUDE.md
- [⭐정확도 우선·레인 간 요청 규칙](feedback-accuracy-over-speed-and-lane-handoff.md) · [⭐도메인별=전용 세션(worktree)](policy-per-domain-sessions.md) · [통합 전 기존 앱 무중단](keep-existing-app-running-until-integrated.md)
- [시안 적용=더하기(재작성 금지)](feedback-design-extend-not-redo.md) · [분석 요청=수정 금지](analysis-request-no-code-change.md) · [실측 근거 수정](fix-from-real-evidence.md) · [데이터로 검증](verify-by-data-not-status.md)
- [폴백 최소화](no-silent-fallback-principle.md) · [코드 건강 게이트](code-health-regression-gate.md) · [괴물함수 전멸](monster-functions-extinct-260929.md) · [판단 흐려지면 새 세션](recommend-new-session-when-degraded.md)
- [커밋=코드+설계+메모리](commit-with-design-and-memory.md) · [커밋 4묶음 자동화](commit-4bundle-automation.md) · [쉬운 말](plain-language-no-jargon.md) · [한글](respond-in-korean.md) · [진단명령 최소화](diagnostic-commands-pop-consoles.md)

## 실행·로그인
- [실행 UI=app_qt·상시가동·설정일원화](runtime-ui-and-always-on.md) · [재부팅 복구 --resume](reboot-recovery.md) · [파이프라인 동시실행 방지(교차프로세스잠금)](feature-pipeline-single-run-lock.md)
- [로그인=실제 Chrome+CDP만](login-policy-real-browser-only.md) · [2차인증=위치기반](login-2fa-location-based.md) · [차단=세션우선+서킷브레이커](login-block-session-first-circuit-breaker.md) · [세션 하루내 만료](coupang-session-short-lived.md)
- [OpenAPI 불가→WING 세션](coupang-openapi-not-available-consignment.md) · [샵마인=WebView2](shopmine-architecture.md)

## 입력·수집
- [입력=셀독 관리대장(헤더2행·여러줄=첫줄)](input-ledger-format.md) · [대장 스코핑·AI 매칭+VID 고정(D-009)](ledger-scoped-tracking.md) · [판매 API vi-detail-search](sales-data-api-vi-detail-search.md) · [재고 API orderableQuantity](inventory-api-rfm-search.md)
- [판매데이터 익일반영](coupang-sales-data-lag.md) · [productId 소스 API](api-productid-source-vendor-items-with-vendoritems.md) · [상품명 규약(대장=담당자·결과=노출명)](product-name-convention-ledger-vs-result.md)

## 키워드·순위
- [키워드 방법론(AI앵커)·띄어쓰기=별개](keyword-methodology-ai-anchor.md) · [매일 통계·키워드 동결](daily-stats-keyword-freeze.md) · [네이버쇼핑 API 종료](naver-shopping-api-terminated.md) · [Wing 키워드 구독게이팅](wing-keyword-data-subscription-gated.md)
- [파이프라인 3단계](pipeline-3stage-separation.md) · [핵심=정확 등수 매일](session-handoff-exact-rank-required.md) · [반자동 순위+노출명](semi-auto-rank-and-exposed-name.md) · [안티차단·간격45~75s](rank-antiblock-circuit-breaker.md)
- [붙여넣기 차단·타이핑만](coupang-blocks-paste-requires-typing.md) · [프라임 후 fetch](coupang-search-prime-then-fetch.md) · [50위 placeholder](rank-blocked-placeholder-50.md) · [지문 정합1·2](fingerprint-consistency.md)
- [⚠IP 정책 맥락별 반대](proxy-ip-policy-by-context.md) · [프록시 라이브 실측](proxy-live-test-261002.md) · [egress 회전+차단IP](proxy-rotation-design-261002.md) · [프록시 통합 초기](proxy-integration-off-261001.md)

## 출력·배포·참조
- [출력=셀독 서식](seldoc-output-format.md) · [날짜컬럼=실행날짜](date-column-run-date-rule.md) · [구글시트 통합 스펙](gsheet-unified-spec.md) · [상세 이미지 추출(CDP)](detail-image-extraction.md)
- [exe 배포·Defender 제외](exe-packaging-deploy.md) · [쿠팡 공식 운영지식](coupang-official-reference.md) · [정산 실행흐름(①뒤 기동·다 받으면 종료 D-010)·상태 카드](feature-settlement-status-monitoring.md)
