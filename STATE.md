# STATE

<!-- 누적 금지. 매 세션 종료 시 /session-close 가 전체 덮어쓰기. 100줄 이하. 핸드오프 SSOT. -->

- BUILD_TAG: R6
- 갱신: 2026-10-10
- 마지막 커밋: 이 STATE 커밋([R6]) ← 78b8417 (B4·D-023) ← f2766e2 (B3) ← 8b148de (R5 세션 종료) ← 930aa59 (D-022) ← 0a5d5d3 (B2) ← d55c397 (B1). 전부 origin/master 푸시.
- 배포본: `dist\쿠팡애널리틱스_배포.zip` (10/10 16:00 빌드·ba16147 기준 = D-016~D-021 포함). **B3·B4 는 미포함**(B3=계정당 배송관리 페이지 추가 이동 1회 제거라 런타임 변화 있음 → 재배포 전 재빌드 권장). **운용 PC 미배포**.
- 세션 핸드오프: STATE.md 단일. 시작 = STATE+DECISIONS 읽고 git log/status 대조 3줄 요약. 종료=`/session-close`.

## 현재 Step
**기능 전수 목록 기반 정리(D-022) 진행 중 — B1~B4 완료, 다음 = B5.** 순서·근거 SSOT = `designs/FEATURE_INVENTORY.md` §6.
⚠ 무거운 작업(게이트·빌드·에이전트·e2e)은 **하나씩**(10/10 BSOD — 메모 feedback-heavy-tasks-sequential).
⚠ 편집은 worktree+브랜치(`git worktree add -b cleanup/bN D:/ca-worktree/cleanup-bN master`) → 게이트 → ff 병합·푸시 → worktree 제거.

## 이번 세션 완료 (R5→R6, 2026-10-10)
- **B3** 쓰기만 하는 저장소 삭제(f2766e2): `session_store.py`·`wing_session.py`·`collector.save_discovered`·`pipeline_sales._persist_session`. 런타임 변화 = 수집 뒤 배송관리 페이지 이동 1회·`[세션] 저장됨` 로그 사라짐. `session_state`(관측)·`keyword_store` 유지.
- **B4** 테스트 전용 함수 삭제(78b8417): `product_match.scope_to_ledger`(테스트→`_rule_scope`=운영 `build_tracked(_assign)`)·`input_list.parse_password_rows`(테스트→`_first_pw`=운영 `parse_password_candidates` 첫 후보)·`proxy_manager` 미사용 메서드 12개+`active_count`·미사용 import(`requests` 등). 운영 동작 변화 없음.
- **D-023** `payout.estimate`·`registry.managed_between` = 정산 ②층 설계 자산으로 유지(소유자 선택).
- 문서: L1_CONTRACT(`save_discovered`·`parse_password_*` 제거)·DESIGN §4.4·DOMAIN_DESIGN·ARCHITECTURE·PARALLEL_DEV·PLATFORM_INTEGRATION·PROCESS_OVERVIEW·DOMAIN_D4·CLAUDE.md(proxy_manager 설명)·FEATURE_INVENTORY §3-2·§3-3·§6.
- 게이트: B3·B4 각각 전체 16종 통과 + 복잡도 경고 0 + pre-commit/pre-push 재통과.
- `.git/worktrees/cleanup-b1` 잔재 = 소유자가 수동 삭제 완료(git worktree 목록에 없음 확인).

## 다음 작업 (우선순위)
1. **B5** 운영에서 안 도는 분기 삭제 — **먼저 게이트 시나리오를 운영 조합으로 이전**(run_full keywords_off=True·skip_ranks=True → select_keywords_stage → track_ranks_stage(semi=True)). 대상(FEATURE_INVENTORY §3-1): `pipeline.py` 인라인 키워드·순위(446-469·739-740·774-775 — 줄 번호는 B3 이후 재확인), `pipeline_process.py:321-355`(`_resolve_keywords`·`_frozen_keywords`·`_log_diagnose`)·`_select_keywords_for_skipped`·wb `title_cache`, `track_ranks_stage(semi=False)`·`_measure_product_auto`·`_measure*`, `organic_ranks_batch` 경로, `_wait_user_search`, `_semi_retry_login`. 현재 이 분기를 검증 중인 게이트 = simulate 1~9·11~14·핀 F·N·O·O2 → 이전 먼저. ⚠ 가장 큰 단계 — 시나리오 이전과 분기 삭제를 별도 커밋으로.
2. **B6** 중복 통합: 야간 조립 3벌(`start_auto`·`start_resume`·`_full_pipeline_task`)→백엔드 1개 + `--auto`/`--resume` 게이트 · 절전 2벌 → `power` · 정산 중지 2벌 → `stop_settlement` · 18:00 옛 정산 예약작업 제거 · `deploy/정산_지금실행.bat`.
3. **오류 E1~E7 일괄 수정**(FEATURE_INVENTORY §2): E1 직원 입력 키워드 역머지를 ②에 연결 · E2 마스터 복원 SA 경로 · E3 예약작업 13h 제한 → 23h50m(운용 PC 설치.bat 예약작업 재등록 필요) · E4 정산_상태확인.bat · E5 06:00 문구 · E7 게이트 설명 문구.
4. 운용 PC: **재빌드**(B3 포함) → 재배포(⚠ 이번 한 번은 작업 관리자에서 `정산다운로드.exe` 직접 종료 후 폴더 덮어쓰기) → 대장 비번 정리(DW 40행 새 값·공백 제거·반달 맞는 비번) → 날짜 지정 10-04~10-09 **전체 실행**(판매+순위·하나씩·18:00 과 겹치지 않게) → 첫 18:00 로그 확인(`[세션] 저장됨` 줄 없음이 정상).

## 미해결 이슈
- (사실·범위 밖 보류) `designs/DESIGN.md` §4.4 의 `session_keepalive` 설명 = 모듈 없음(낡은 문단). `ProxyNode` 건강 필드(consecutive_failures·latency_ms 등)·`ProxyManager(max_failures,verify_url)` 인자는 이제 쓰는 곳 없음(`__repr__`만) — 정리 후보.
- (사실·범위 밖) `pipeline_sales.py` 상단 import 다수 미사용(ruff F401: `dataclass`·`recommend_title`·`kw_recommend` 6개 등) — 재수출 여부 확인 후 정리 후보.
- (소유자 확인) `reusable_coupang/` = 다른 프로젝트용 독립 패키지(앱 미사용) 유지/삭제 · 루트 `login_source_260904/`·`src - 복사본/` = git 밖 로컬 사본(지우면 복구 불가) 삭제 여부.
- (사실) 반달(mrc098) 57·60행은 공백만 다른 같은 값이고 그 값이 10/10 거부 → 대장 비번 자체가 틀림. 하성진(lslfgh) = 로그인 추가단계에서 미완료(비번 문제 아님).
- (사실) E3: `deploy/install.ps1:201` ExecutionTimeLimit 13h — 07:00 넘는 실행이면 스케줄러가 앱 종료 → D-020 상 정산도 종료. 지금까지 18:00 실행은 ~20:30 종료라 미발현.
- (미확인) BSOD 0x13A 원인 드라이버 — `C:\Windows\MEMORY.DMP` 분석은 관리자+WinDbg 필요(미실시).
- (미확인) 앱이 띄운 정산의 작업 묶음 분리(CREATE_BREAKAWAY_FROM_JOB) 허용 여부 — 첫 18:00 로그 '분리 불가' 경고 여부로 확인.
- (미확인) 윙 1원/55,001 차이 원인 · 정산 ②층(계약금액 입력·손실 분담) 미구현 · 윙 'M' 받기 방법.

## 주의
- 런타임 병렬 금지(단일 브라우저·위탁계정·Akamai). master 병합·빌드=통제 직렬.
- 재배포 = 폴더 덮어쓰기→앱 재시작. output·data·config.json·proxies.txt 보존. 배포 zip 에 키·프록시 자격증명 평문 → 외부 공유 금지.
- 결과시트·관리대장 분석은 앱 서비스계정으로 읽기만(비번 값 출력 금지·지문 비교만).
- DECISIONS: 현재 **D-023**까지. D-010=SUPERSEDED by D-021, D-013=SUPERSEDED by D-015.
- pre-commit 훅이 `docs/memory` 미러를 자동 동기화(줄바꿈 경고 다수 = 내용 변경 아님) — 커밋 후 `git show --stat` 으로 의도 파일만 들어갔는지 확인.
- PowerShell 에서 폴더 삭제 = `Remove-Item -Recurse -Force <경로>`(cmd 의 `rmdir /s /q` 는 안 됨).
