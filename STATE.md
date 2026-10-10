# STATE

<!-- 누적 금지. 매 세션 종료 시 /session-close 가 전체 덮어쓰기. 100줄 이하. 핸드오프 SSOT. -->

- BUILD_TAG: R5
- 갱신: 2026-10-10
- 마지막 커밋: 이 STATE 커밋([R5]) ← 930aa59 (D-022·FEATURE_INVENTORY) ← 0a5d5d3 (B2) ← d55c397 (B1) ← ba16147 (D-020·D-021 정산 수명) ← a07c681 (D-019) ← 8d53a06 (D-018) ← fc4d13e·7cf16cf·4ce026f (D-017 workbook 분리). 전부 origin/master 푸시.
- 배포본: `dist\쿠팡애널리틱스_배포.zip` (10/10 16:00 빌드·ba16147 기준 = D-016~D-021 포함. 이후 B1·B2 는 미배포 도구·문서만이라 재빌드 불필요). **운용 PC 미배포**(운용 PC 는 D-016 까지 반영된 상태로 10/10 01:04 실행 확인).
- 세션 핸드오프: STATE.md 단일. 시작 = STATE+DECISIONS 읽고 git log/status 대조 3줄 요약. 종료=`/session-close`.

## 현재 Step
**기능 전수 목록 기반 정리(D-022) 진행 중 — B1·B2 완료, 다음 = B3.** 순서·근거 SSOT = `designs/FEATURE_INVENTORY.md` §6.
⚠ 무거운 작업(게이트·빌드·에이전트·e2e)은 **하나씩**(10/10 BSOD — 메모 feedback-heavy-tasks-sequential).

## 이번 세션 완료 (R4→R5, 2026-10-10)
- **D-017** workbook.py 1585줄 MI C → mixin 3개(meta·dates·lifecycle) 분리, 596줄 MI B · KNOWN_BAD 제외. 멤버 144개 바이트코드 지문 차이 0.
- **D-018** 관리대장 비번 앞뒤 공백 제거 후 입력 + `[비번] ⚠ 행 … 공백` 경고. 원인 실측: DW 39·42~48행·플랜잇 22행 = 새 비번+끝 공백(10/04~ DW 판매 공란).
- **D-019** 날짜 지정 실행: 칸별 이력 없는 옛 칸은 판매값 있는 계정 로그인 생략(10.04~10.08 채우기 로그인 24→4계정).
- **D-020** 앱을 사람이 닫거나 강제 종료하면 정산도 종료(`watch --parent`·`watch_parent`·무인 자체 종료=`_앱정상종료.json` 표시면 계속).
- **D-021** 정산 회차 = 18:00 앱과 함께 기동 → 이번 회차 ①완료 기록까지 대기 → 받기 → 다 받으면/다음 날 17:55 종료. D-010 SUPERSEDED. 정산 탭 [정산 시작] 단일 경로로 통합.
- **D-022** 기능 목록 `designs/FEATURE_INVENTORY.md`(운영 기능·목표·게이트·오류 E1~E7·죽은 코드·중복) + 정리 범위 결정. **B1** Tk `ui/app.py`+`parse_password_file` 삭제(−896줄) · **B2** 일회성 도구 10개 삭제(−1,155줄).
- 전역 규칙: `~/.claude/CLAUDE.md` "오류 정의"(목표 결과가 안 나오면 오류) 추가.
- 분석: (DW)커머스 10.04~10.09 판매 공란 = 로그인 거부(끝 공백) · 노트북 BSOD 0x13A(15:18·30일 내 첫 건·원인 드라이버 미확정).

## 다음 작업 (우선순위)
1. **B3** 쓰기만 하는 저장소 삭제: `session_store`·`wing_session`·`collector.save_discovered`(호출처 재확인 후). `keyword_store` 는 키워드 탭 유지라 남김.
2. **B4** 테스트 전용 함수 삭제: `product_match.scope_to_ledger`·`input_list.parse_password_rows`·`payout.estimate`·`registry.managed_between`·`proxy_manager` 미사용 메서드 12개(테스트를 운영 함수로 전환).
3. **B5** 게이트 시나리오를 **운영 조합**(run_full keywords_off=True·skip_ranks=True → select_keywords_stage → track_ranks_stage(semi=True))으로 이전 → 운영에서 안 도는 분기 삭제(`pipeline.py:446-469·739-740·774-775`, `pipeline_process.py:321-355`, `track_ranks_stage(semi=False)`, `organic_ranks_batch` 경로, `_wait_user_search`, `_semi_retry_login`). simulate 1~9·11~14·핀 F·N·O·O2 가 이 분기를 검증 중 → 먼저 이전.
4. **B6** 중복 통합: 야간 조립 3벌(`start_auto`·`start_resume`·`_full_pipeline_task`)→백엔드 1개 + `--auto`/`--resume` 게이트 · 절전 2벌 → `power` · 정산 중지 2벌 → `stop_settlement` · 18:00 옛 정산 예약작업 제거 · `deploy/정산_지금실행.bat`.
5. **오류 E1~E7 일괄 수정**(FEATURE_INVENTORY §2): E1 직원 입력 키워드 역머지를 ②에 연결 · E2 마스터 복원 SA 경로 · E3 예약작업 13h 제한 → 23h50m(운용 PC 설치.bat 예약작업 재등록 필요) · E4 정산_상태확인.bat · E5 06:00 문구 · E6(B2 로 해소) · E7 게이트 설명 문구.
6. 운용 PC: 재배포(⚠ 이번 한 번은 작업 관리자에서 `정산다운로드.exe` 직접 종료 후 폴더 덮어쓰기) → 대장 비번 정리(DW 40행 새 값·공백 제거·반달 맞는 비번) → 날짜 지정 10-04~10-09 **전체 실행**(판매+순위·하나씩·18:00 과 겹치지 않게) → 첫 18:00 로그 확인.

## 미해결 이슈
- (소유자 확인) `reusable_coupang/` = 다른 프로젝트용 독립 패키지(앱 미사용) 유지/삭제 · 루트 `login_source_260904/`·`src - 복사본/` = git 밖 로컬 사본(지우면 복구 불가) 삭제 여부.
- (사실) 반달(mrc098) 57·60행은 공백만 다른 같은 값이고 그 값이 10/10 거부 → 대장 비번 자체가 틀림. 하성진(lslfgh) = 로그인 추가단계에서 미완료(비번 문제 아님).
- (사실) E3: `deploy/install.ps1:201` ExecutionTimeLimit 13h — 07:00 넘는 실행이면 스케줄러가 앱 종료 → D-020 상 정산도 종료. 지금까지 18:00 실행은 ~20:30 종료라 미발현.
- (미확인) BSOD 0x13A 원인 드라이버 — `C:\Windows\MEMORY.DMP`(16.9GB) 분석은 관리자+WinDbg 필요(미실시). 비치명 커널 보고서 193(그래픽)·144(USB3)·15F·19C 존재.
- (미확인) 앱이 띄운 정산의 작업 묶음 분리(CREATE_BREAKAWAY_FROM_JOB) 허용 여부 — 첫 18:00 로그 '분리 불가' 경고 여부로 확인.
- (미확인) 윙 1원/55,001 차이 원인 · 정산 ②층(계약금액 입력·손실 분담) 미구현 · 윙 'M' 받기 방법.

## 주의
- 런타임 병렬 금지(단일 브라우저·위탁계정·Akamai). master 병합·빌드=통제 직렬. 편집은 worktree+브랜치.
- 재배포 = 폴더 덮어쓰기→앱 재시작. output·data·config.json·proxies.txt 보존. 배포 zip 에 키·프록시 자격증명 평문 → 외부 공유 금지.
- 결과시트·관리대장 분석은 앱 서비스계정으로 읽기만(비번 값 출력 금지·지문 비교만).
- DECISIONS: 현재 **D-022**까지. D-010=SUPERSEDED by D-021, D-013=SUPERSEDED by D-015.
- `.git/worktrees/cleanup-b1` 메타 폴더가 권한 문제로 남음 → 다음 세션 `git worktree prune` 재시도.
