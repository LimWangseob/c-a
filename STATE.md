# STATE

<!-- 누적 금지. 매 세션 종료 시 /session-close 가 전체 덮어쓰기. 100줄 이하. 핸드오프 SSOT. -->

- BUILD_TAG: R7
- 갱신: 2026-10-10
- 마지막 커밋: 이 STATE 커밋([R7]) ← 124738a (B5-2 분기 삭제) ← 798ffb4 (B5-1 게이트 이전) ← d656e4f (R6 세션 종료). 전부 origin/master 푸시.
- 배포본: `dist\쿠팡애널리틱스_배포.zip` (10/10 16:00 빌드·ba16147 기준 = D-016~D-021 포함). **B3·B4·B5 미포함** → 재배포 전 **재빌드 필수**. **운용 PC 미배포**.
- 세션 핸드오프: STATE.md 단일. 시작 = STATE+DECISIONS 읽고 git log/status 대조 3줄 요약. 종료=`/session-close`.

## 현재 Step
**기능 전수 목록 기반 정리(D-022) 진행 중 — B1~B5 완료, 다음 = B6(중복 통합).** 순서·근거 SSOT = `designs/FEATURE_INVENTORY.md` §3-4·§6.
⚠ 무거운 작업(게이트·빌드·에이전트·e2e)은 **하나씩**(10/10 BSOD — 메모 feedback-heavy-tasks-sequential).
⚠ 편집은 worktree+브랜치(`git worktree add -b cleanup/b6 D:/ca-worktree/cleanup-b6 master`) → 게이트 → `git merge --ff-only` → 푸시(pre-push=전체 게이트) → `git worktree remove` + `git branch -d`.

## 이번 세션 완료 (R6→R7, 2026-10-10)
- **B5-1**(798ffb4, 코드 무변경): `tools/simulate_pipeline.py` 시나리오 1~16 전부 **운영 조합**(헬퍼 `_run1`=run_full 운영 인자 · `_run2`=select_keywords_stage · `_run3`=track_ranks_stage · `_ops`=①→②→③)으로. 크래시·오류 주입은 계정 발견 단계로. `verify_offline` [23] 동결 규칙=② `pipeline._select_product_keywords`. `verify_render_precision`=운영 조합 뒤 마스터 검증. 기존 코드로 게이트 16종 통과 확인 후 커밋.
- **B5-2**(124738a, 순 −727줄): 운영에서 안 돌던 분기 물리 삭제.
  - `run_full`: 인라인 키워드·순위(`_finish` drive_rank 분기·`_select_keywords_for_skipped`·역머지 호출) + 인자 `naver`·`grow_keywords`·`skip_ranks`·`keywords_off`(진행 파일 grow·skip 키도). 새 시그니처 `run_full(input_list, out_dir, ai_key, …, sales_semi, …)`.
  - `pipeline_process`: 대표 옵션 키워드/순위 분기·`_resolve_keywords`·`_frozen_keywords`·`_log_diagnose`·`_product_matcher` → 모든 옵션 블록 = ① 판매정보만.
  - `pipeline_ranks`: `track_ranks_stage(semi=False)`+`semi` 인자·`_measure*`·`_measure_product_auto`·`_rank_cooldown`·`RankHalt`·`_RANK_HALT`·`_best`·병렬 경로·`_wait_user_search`·`RANK_SEMI_AUTOSUBMIT` 분기.
  - `workbook_meta.title_cache/set_title_cache` 삭제(숨김 시트 4·5열 헤더 '(미사용)'·위치 유지). config 상수 5개 삭제.
  - UI `app_qt` 호출 8곳(run_full 4·track_ranks_stage 4) 갱신. 핀 N·O·O2 삭제·`test_proxy_patch` 회전 핀을 ③ `_semi_on_miss` 로 이전.
  - 문서: CLAUDE.md·DESIGN·GSHEET_UNIFIED·L1_CONTRACT·FEATURE_INVENTORY §1·§2·§3-1·§6.
- 검증: 게이트 16종(커밋 전·pre-commit·pre-push) + 복잡도 경고 0 + UI offscreen import 스모크. **실운용 검증 없음**(운용 PC 재배포 후 첫 18:00 로그로 확인).

## 다음 작업 (우선순위)
1. **B6 중복 통합**(FEATURE_INVENTORY §3-4) — UI(app_qt) 변경 큼·**핀 먼저**:
   - 야간 조립 3벌(`app_qt.start_auto`·`start_resume`·`_full_pipeline_task`: ①→재개→②→③→재고 역기록 각자 조립) → 백엔드 함수 1개 + `--auto`/`--resume` 조립 게이트 신설(현재 게이트 공백 §5).
   - 절전 방지 2벌(`power.keep_awake` vs `app_qt._prevent_sleep`) → power 로 통일.
   - 정산 중지 2벌(`app_process.stop_settlement` vs 패널 `_kill_settlement`) → stop_settlement.
   - 18:00 매번 옛 정산 예약작업 제거 코드 삭제(install.ps1·remove_autorun 은 유지) · `deploy/정산_지금실행.bat` watch 통일 또는 삭제.
2. **오류 E1~E7 일괄 수정**(FEATURE_INVENTORY §2): **E1** `pull_gsheet_keywords`(현재 호출처 없음)를 ② `select_keywords_stage` 시작에 연결 · E2 마스터 복원 SA 경로 · E3 예약작업 13h → 23h50m(운용 PC 설치.bat 재등록 필요) · E4 정산_상태확인.bat · E5 06:00 문구 · E7 게이트 설명 문구. (E6 = B2 로 해소)
3. 운용 PC: **재빌드**(B3·B4·B5 포함) → 재배포(⚠ 이번 한 번은 작업 관리자에서 `정산다운로드.exe` 직접 종료 후 폴더 덮어쓰기) → 대장 비번 정리(DW 40행 새 값·공백 제거·반달 맞는 비번) → 날짜 지정 10-04~10-09 **전체 실행**(하나씩·18:00 과 겹치지 않게) → 첫 18:00 로그 확인(`[세션] 저장됨` 줄 없음·순위 단계 정상이 정상).

## 미해결 이슈
- (사실) `_semi_retry_login` 은 **운영 경로** — 정산 다운로드 `--hidden`(18:00 watch)이 `_ensure_login(semi=False)` → `unattended=True` 로 탐. FEATURE_INVENTORY 의 '안 돎' 기재는 정정함. 삭제 대상 아님.
- (사실·정리 후보) 호출처 없음: `rank.organic_ranks`·`organic_ranks_batch`(L1_CONTRACT 공개 API라 B5 에서 유지) · `pipeline_gsheet.pull_gsheet_keywords`(E1 에서 ②로 연결 예정) · `kw_recommend.select_keywords_light(measure_ranks=)` 는 이제 늘 None · `app_qt.do_track_ranks(semi)` 인자 미사용 · `run_full(sales_semi=False)`(운영은 늘 True) · config `RANK_HUMAN_SERIAL`·`RANK_FETCH_*`·`RANK_BLOCK_*`(rank.py 병렬 경로 전용).
- (사실·범위 밖) `pipeline_sales.py` 상단 import 다수 미사용(kw_ai·kw_recommend·NaverAdApi·make_matcher·OutputWorkbook 등) — 재수출 여부 확인 후 정리 후보. `DESIGN.md §4.4` `session_keepalive` 낡은 문단. `ProxyNode` 건강 필드·`ProxyManager(max_failures,verify_url)` 미사용.
- (소유자 확인) `reusable_coupang/` 유지/삭제 · 루트 `login_source_260904/`·`src - 복사본/`(git 밖 로컬 사본·지우면 복구 불가) 삭제 여부.
- (사실) 반달(mrc098) 57·60행은 공백만 다른 같은 값이고 그 값이 10/10 거부 → 대장 비번 자체가 틀림. 하성진(lslfgh) = 로그인 추가단계 미완료(비번 문제 아님).
- (사실) E3: `deploy/install.ps1:201` ExecutionTimeLimit 13h — 07:00 넘는 실행이면 앱 종료 → D-020 상 정산도 종료. 지금까지 18:00 실행은 ~20:30 종료라 미발현.
- (미확인) BSOD 0x13A 원인 드라이버(`C:\Windows\MEMORY.DMP` 분석 = 관리자+WinDbg, 미실시).
- (미확인) 앱이 띄운 정산의 작업 묶음 분리(CREATE_BREAKAWAY_FROM_JOB) 허용 여부 — 첫 18:00 로그 '분리 불가' 경고 여부로 확인.
- (미확인) 윙 1원/55,001 차이 원인 · 정산 ②층(계약금액 입력·손실 분담) 미구현 · 윙 'M' 받기 방법.

## 주의
- 런타임 병렬 금지(단일 브라우저·위탁계정·Akamai). master 병합·빌드=통제 직렬.
- 재배포 = 폴더 덮어쓰기→앱 재시작. output·data·config.json·proxies.txt 보존. 배포 zip 에 키·프록시 자격증명 평문 → 외부 공유 금지.
- 결과시트·관리대장 분석은 앱 서비스계정으로 읽기만(비번 값 출력 금지·지문 비교만).
- DECISIONS: 현재 **D-023**까지(이번 세션 신규 없음). D-010=SUPERSEDED by D-021, D-013=SUPERSEDED by D-015.
- 진행 파일(`_진행중.json`)은 이제 grow·skip 키를 쓰지 않음(옛 파일의 키는 무시됨 — 호환 문제 없음).
- pre-commit 훅이 `docs/memory` 미러를 자동 동기화(줄바꿈 경고 다수 = 내용 변경 아님) — 커밋 후 `git show --stat` 으로 의도 파일만 들어갔는지 확인.
- PowerShell 폴더 삭제 = `Remove-Item -Recurse -Force <경로>`. 스크립트 편집은 bash heredoc 따옴표가 깨질 수 있어 scratchpad `.py` 파일로 작성 후 실행이 안전.
