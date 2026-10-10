# STATE

<!-- 누적 금지. 매 세션 종료 시 /session-close 가 전체 덮어쓰기. 100줄 이하. 핸드오프 SSOT. -->

- BUILD_TAG: R8
- 갱신: 2026-10-10
- 마지막 커밋: 이 STATE 커밋([R8]) ← a2fd142 (E1~E7 수정) ← 6850dff (B6 중복 통합) ← 60d747a (R7 세션 종료). 전부 origin/master 푸시.
- 배포본: `dist\쿠팡애널리틱스_배포.zip` (**10/10 18:34 재빌드·a2fd142 기준 = B3~B6·E1~E7 포함**, 172MB). zip 확인: `정산_지금실행.bat` 없음·install.ps1 23h50m. **운용 PC 미배포**.
- 세션 핸드오프: STATE.md 단일. 시작 = STATE+DECISIONS 읽고 git log/status 대조 3줄 요약. 종료=`/session-close`.

## 현재 Step
**정리(D-022) B1~B6 + 오류 E1~E7 전부 완료 → 다음 = 운용 PC 재배포(사람 조치)·첫 18:00 로그 검증.**
⚠ 무거운 작업(게이트·빌드·에이전트·e2e)은 **하나씩**(10/10 BSOD — 메모 feedback-heavy-tasks-sequential).
⚠ 편집은 worktree+브랜치 → 게이트 → `git merge --ff-only` → 푸시(pre-push=전체 게이트) → worktree·브랜치 삭제.

## 이번 세션 완료 (R7→R8, 2026-10-10)
- **B6**(6850dff·D-024): 전체실행·`--auto`·`--resume` 의 ①→②→③→재고 역기록 조립 3벌 → `pipeline_stages.run_stages` 1개(복구 계획 `plan_resume_stages`·UI 는 `StagePlan` 만). 단계 기록 = **실제로 끝난 단계**(① 끝=sales·② 끝=ranks·③ 중지 없이 끝=done·① 단독은 없음)·재고 역기록은 ③까지 갔으면 함. 핀 P9~P11(`pin_run_plan`) = `--auto`/`--resume` 게이트 공백 해소. `_prevent_sleep`→`power.keep_awake`. 정산 중지 = `app_process.stop_settlement`(트리 종료 `taskkill /T` — 정산 Chrome 까지) 하나로·패널 `_kill_settlement` 삭제. 18:00 옛 정산 예약작업 제거 코드 삭제(install.ps1 은 유지). `deploy/정산_지금실행.bat` 삭제(소유자 선택).
- **E1~E7**(a2fd142·D-025):
  - E1 직원 키워드 역머지 `pull_gsheet_keywords` 를 **① `run_full` 시작**에 무조건 호출(② 시작안은 ① 끝 결과시트 전체 교체 뒤라 소실 → 정정). simulate 17(재현 실패→통과).
  - E2 마스터 복원 = 서비스계정 + 저장 타입 그대로(`read_values(unformatted=True)`)·`gsheet.download_xlsx` 삭제. verify_gsheet[17]. **실측(읽기만)**: 공개 export 401 재현·SA 복원 성공(사업자 24·숫자 3,140칸 숫자 유지·apply_style→저장→재로드 정상).
  - E3 예약작업 제한 13h → **23h50m**(install.ps1·install_schedule_py.ps1) · E4 `정산_상태확인.bat` 이 18:00 `--auto` 작업 조회(cmd 로 두 분기 실행 확인) · E5 '06:00 자동 종료' 문구 정정(설치 안내·INSTALL.md) · E7 게이트 개수 표기 제거(run_checks·install_hooks·CLAUDE.md).
- 검증: 게이트 16종(커밋 전·pre-commit·pre-push 각 회) + 복잡도 경고 0 + UI offscreen import + 정산 트리 종료 실제 프로세스 e2e + PowerShell 구문 검사 0 오류. **실운용 검증 없음**.
- 재빌드: 첫 두 번 `dist\coupang-analytics\_internal\aiohttp\_websocket` 삭제 거부(빈 폴더·핸들 잡힘 추정)로 실패 → 옛 산출물 폴더를 `dist\coupang-analytics_old_stuck` 로 이름 바꿔 비키고 성공.

## 다음 작업 (우선순위)
1. **운용 PC 재배포**(사람): ⚠ 작업 관리자에서 `정산다운로드.exe` 직접 종료(옛 코드는 앱 종료 감시 없음) → 새 zip 의 `coupang-analytics\` 덮어쓰기 → **설치.bat 실행·자동실행 등록 Y**(E3 23h50m 반영 + 옛 정산 예약작업 정리) → 폴더에 남은 옛 `정산_지금실행.bat` 직접 삭제(덮어쓰기로 안 지워짐).
2. 대장 비번 정리(DW 40행 새 값·반달 맞는 비번) → 날짜 지정 10-04~10-09 **전체 실행**(하나씩·18:00 과 겹치지 않게).
3. 첫 18:00 로그 확인: ① 시작 `[구글시트] 직원 입력 키워드 반영`(있을 때)·'[단계] ② / ③' 로그·끝난 단계 기록·정산 '①판매수집 완료 대기'→받기·`[세션] 저장됨` 줄 없음.
4. (정리 후보·소유자 판단) 아래 '호출처 없음' 목록 · `reusable_coupang/`·git 밖 로컬 사본 2개.

## 미해결 이슈
- (사실) `dist\coupang-analytics_old_stuck\` — 삭제 거부된 옛 빌드 산출물(빈 `_websocket` 폴더 잠김). 재부팅 후 지우면 됨. 다음 빌드에는 영향 없음(빌드는 `dist\coupang-analytics\` 사용).
- (사실) 빌드한 exe 는 실행 스모크를 하지 않음(GUI·`--auto` 가 실제 파이프라인을 띄움) — 코드는 offscreen import·게이트로만 확인.
- (사실·정리 후보) 호출처 없음: `rank.organic_ranks`·`organic_ranks_batch`(L1 공개 API) · `kw_recommend.select_keywords_light(measure_ranks=)` 늘 None · `app_qt.do_track_ranks(semi)` 인자 미사용 · `run_full(sales_semi=False)`(운영은 늘 True) · config `RANK_HUMAN_SERIAL`·`RANK_FETCH_*`·`RANK_BLOCK_*` · `pipeline_sales.py` 상단 import 다수 미사용 · `DESIGN.md §4.4` `session_keepalive` 낡은 문단 · `ProxyNode` 건강 필드·`ProxyManager(max_failures,verify_url)` 미사용.
- (사실) `_semi_retry_login` 은 운영 경로(정산 `--hidden` watch) — 삭제 대상 아님.
- (사실) E1 의 역머지는 '시트 값 기준 동기화'(시트에서 지운 키워드는 워크북에서도 비움) — 전날 결과시트 반영이 실패했다면 다음 ① 역머지가 그 날 새 키워드를 지울 수 있음(원래 설계의 위험·D-025 버린 대안 b 참고). 결과시트 반영 실패 로그가 보이면 확인 필요.
- (사실) 반달(mrc098) 대장 비번 자체가 틀림(10/10 거부) · 하성진(lslfgh) = 로그인 추가단계 미완료.
- (소유자 확인) `reusable_coupang/` 유지/삭제 · 루트 `login_source_260904/`·`src - 복사본/`(git 밖·지우면 복구 불가).
- (미확인) BSOD 0x13A 원인 드라이버(MEMORY.DMP 분석 미실시).
- (미확인) 앱이 띄운 정산의 작업 묶음 분리(CREATE_BREAKAWAY_FROM_JOB) 허용 여부 — 첫 18:00 로그 '분리 불가' 경고 여부.
- (미확인) 윙 1원/55,001 차이 원인 · 정산 ②층(계약금액 입력·손실 분담) 미구현 · 윙 'M' 받기 방법.

## 주의
- 런타임 병렬 금지(단일 브라우저·위탁계정·Akamai). master 병합·빌드=통제 직렬.
- 재배포 = 폴더 덮어쓰기→앱 재시작. output·data·config.json·proxies.txt 보존. 배포 zip 에 키·프록시 자격증명 평문 → 외부 공유 금지.
- 결과시트·관리대장 분석은 앱 서비스계정으로 읽기만(비번 값 출력 금지·지문 비교만).
- DECISIONS: 현재 **D-025**까지(이번 세션 D-024·D-025). D-010=SUPERSEDED by D-021, D-013=SUPERSEDED by D-015.
- 단계 조립 수정은 `pipeline_stages.run_stages` 한 곳 + `pin_run_plan` P9~P11. UI(app_qt)에 조립을 다시 만들지 말 것.
- pre-commit 훅이 `docs/memory` 미러를 자동 동기화 — 커밋 후 `git show --stat` 으로 의도 파일만 들어갔는지 확인.
- 스크립트 편집은 scratchpad `.py` 로(heredoc 이스케이프·CRLF 깨짐 주의 — bat/ps1 은 CRLF·BOM 유지). 콘솔 출력 깨지면 `PYTHONIOENCODING=utf-8`.
