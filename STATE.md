# STATE

<!-- 누적 금지. 매 세션 종료 시 /session-close 가 전체 덮어쓰기. 100줄 이하. 핸드오프 SSOT. -->

- BUILD_TAG: R1
- 갱신: 2026-10-08
- 마지막 커밋: e8da71e (문서 크기 상한 정책 구체화 — 메모리 30~50줄·CLAUDE.md<200줄)
- 세션 핸드오프 전환: 이번 세션부터 **STATE.md가 단일 핸드오프**(옛 handoff-session-*.md 메모리는 아카이브·recall만)

## 현재 Step
session-kit 전역 전환(STATE.md·D-001 DECISIONS·[R{n}] 커밋·/session-close 스킬) 진행 중 + 정산 라이브 검증 대기.

## 이번 세션 완료 (최근 → 과거)
- 문서 크기 상한 정책(메모리 30~50줄·CLAUDE.md<200줄·DECISIONS append-only)·MEMORY.md 60→38줄 정리 — 전역/프로젝트 CLAUDE.md
- 정산: 24h 감시 모델(plan_watch·sales_in_progress)·탭 실행/중지 버튼·전용 상태카드(heartbeat)·18:00 전체중단 근본수정(TargetClosedError=일시적)·watch 상태 2중기록 방지
- 파이프라인 동시 실행 방지(교차프로세스 잠금·열어둔 GUI+18:00 무인)
- 재배포 시 운용 PC 구글시트 URL 보존(_import_settings 기존값 미덮음)
- D8 병합(ff): 반출비 쿠팡귀책 시트 제외(받기 실패 16건)·merge --src 폴더합치기·로켓그로스 비용 상품별 집계
- 운용 PC: 최신 zip 배포·merge --src 실행 완료(요청 192·파일 103 통합 확인)

## 다음 작업 (우선순위)
1. **오늘 18:00 정산 라이브 검증** — reap 로 Chrome 닫혀도 '차단'으로 안 멈추고 일시정지→재개되는지 로그 확인(output\정산\로그\ "브라우저가 닫힘(일시적…재시도)")
2. 운용 PC 설정 URL 4개 교정 확인(config.json 권위·재배포해도 보존되는지)
3. L1 핀·사무실 라이브: 정산 probe·쿠팡 쓰기 엔드포인트 캡처(U3 WING 정산 API·U4 샵마인 CS 경계)
4. 소유자 결정 대기: 정산 지급일 규칙·계약금액(골든케이스)·CS(D10) 2단계 수집

## 미해결 이슈
- (확인된 사실) 18:00 앱 시작 reap_orphan_chrome 이 정산 Chrome 종료 → TargetClosedError. (b) 수정으로 '차단'·전체중단은 막았으나 **Chrome 사망 자체는 잔존**(일시적 재시도로 흡수). 근본차단(reap 가 정산 프로필 미종료)은 browser.py 변경 필요·보류.
- (미확인) 10-07 18:02:45 두 번째 Chrome 닫힘 원인(앱 로그 미확보). 오늘 18:00 로그로 재확인 필요.
- (대기) 정산 지급일 실측 불일치 2건(9월 최종 11/2·RG 30%) — 소유자 확인.

## 주의
- 런타임 병렬 금지(단일 브라우저·위탁계정·Akamai). master 병합·빌드=통제 직렬.
- 정산다운로드.exe=console 없음 → 결과는 output\정산\로그\ 로만 확인. PowerShell 실행은 `.\정산다운로드.exe`.
- 운용 PC 재배포=폴더 덮어쓰기→앱 재시작. output·data·config.json·proxies.txt 는 보존(덮어써도).
- DECISIONS 전환: 전환 전 한 줄 기록은 동결 아카이브(재작성 금지). 신규는 D-001 블록.
