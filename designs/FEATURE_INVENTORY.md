# 기능 목록(인벤토리) — 무엇이 있고·실제로 쓰이고·무엇이 지키는가

> 작성 2026-10-10 (master `ba16147` 기준) · 목적 = 소유자 지시 "현재 구현된 기능을 전부 나열 → 불필요·유사중복 통합·삭제 →
> 소스 단순화로 '고치면 다른 기능이 깨지는' 회귀를 끊는다".
> 근거 = 조사 3회(핵심·정산/원장·UI/tools, grep·AST 기반) + **✔ = 이 세션에서 직접 재확인**. 삭제는 항목마다 재확인 후 진행.
> 오류 정의(전역 규칙): 목표 결과가 안 나오면 오류(로그상 정상이어도).

## 0. 실제로 배포·실행되는 것

| 구분 | 내용 |
|---|---|
| 배포 exe 3개 | `쿠팡애널리틱스.exe`(=`ui/app_qt.py`) · `정산다운로드.exe`(=`tools/settlement_download.py`) · `쿠팡진단.exe`(=`tools/verify_login_discover_live.py`) — `coupang_analytics.spec` |
| 예약작업 2개 | 18:00 `--auto`(무인) · 로그온 `--resume`(재부팅 복구) — `deploy/install.ps1` |
| **배포 안 됨** | `ui/app.py`(Tk 폴백, spec 이 tkinter 제외) · `ui/app_integrated.py`(통합앱 셸, 어디서도 참조 없음) |
| 핵심 사실 ✔ | 운영의 모든 `run_full` 호출(①버튼·전체실행·`--auto`·`--resume`)은 **`keywords_off=True, skip_ranks=True, sales_semi=True`** 고정, ③은 **`semi=True`** 고정 → `run_full` 안의 키워드·순위 분기와 자동(offscreen) 순위 분기는 **운영에서 실행되지 않음** |

## 1. 운영 기능 (app_qt) — 목표 결과 · 진입점 · 게이트

게이트: ✓ 목표 결과 검증 · △ 일부/시그니처만 · ✗ 없음

### 1-1. 야간 무인·실행
| 기능 | 목표 결과 | 진입점 | 게이트 |
|---|---|---|---|
| ① 판매수집 | 계정별 판매·노출·방문·재고·판매상태·가격·pid → 통계 마스터·스냅샷·결과시트 | ①버튼·전체실행·`--auto`·`--resume` → `run_full` | ✓ simulate 10·15·16(운영 조합) · ⚠시나리오 1~9·11~14 는 **운영과 다른 경로(keywords_off=False)** 를 검증 |
| ② 키워드 선정 | 상품당 4개·기존 키워드 동결 | ②버튼·전체실행·무인 → `select_keywords_stage` | ✓ simulate 10·verify_offline [6][23](모킹) |
| ③ 반자동 순위 | 자동 타이핑+Enter·쿨다운·노출명/pid 갱신 | ③버튼·전체실행·무인 → `track_ranks_stage(semi=True)` | ✓ pin_login_ranks J~Q2 |
| 실행 모드(이어서/오늘 다시/새 통계/날짜 지정) | 칸·재개 규칙 | 전체실행 탭 → `plan_run_mode`·`column_dates` | ✓ pin_run_plan P1~P8 |
| `--auto` 조립(①→재개→②→③→재고 역기록→종료) | 끝까지 완주 후 종료 | `start_auto` | △ 단계별만 · **조립(재개·쿨다운·단계 기록) ✗** |
| `--resume` 재부팅 복구 | 남은 단계만 이어서 | `start_resume` | **✗** |
| 정산 자동 수집(D-020·D-021) | 18:00 함께 기동·①완료 대기·다 받으면/17:55 종료·사람이 앱 끄면 함께 종료 | main(`--auto`/`--resume`)·정산 탭 | ✓ runtime P25~P27·e2e |

### 1-2. 로그인·매칭·출력
| 기능 | 목표 결과 | 게이트 |
|---|---|---|
| 세션 우선 → 반자동 로그인·서킷브레이커·비번오류 재시도 금지 | 차단·잠금 없이 로그인 | ✓ pin A~E·simulate 3·7·8 |
| 대장 비번 후보(D-012)·공백 제거(D-018) | 맞는 값으로 로그인 | ✓ verify_offline [37]·gsheet [15][16] |
| 매칭(VID 고정→동명→AI 의미→규칙 대체·색상 필터) | 대장 상품 = 쿠팡 VID | ✓ verify_offline [35][36] |
| 노출상품명 현행화(D-015) | 블록명 = 현행 노출명 | ✓ verify_offline [38] |
| 통계 마스터·서식(워크북 7모듈) | 블록·지표·하이퍼링크 | ✓ pin_apply_style·verify_render_precision |
| 결과시트 반영(통계 미러·계정목록 동기화/삭제) | 시트 = 마스터 | ✓ verify_gsheet [3]~[12] |
| 관리대장 입력(SA·취소선/상태) | 대장 → 입력 목록 | ✓ verify_gsheet [1][1b][1c] |
| 작업 전 백업(SA 값 스냅샷) | 결과시트 사본 | ✓ verify_gsheet [13] |
| 회사보유재고 → 대장 AB | 재고 역기록 | ✓ verify_registry t21·t23 |
| 그로스 재고 → 대장 AD | 재고 역기록 | △ 시그니처만 |
| 쿠팡확인 → 원장 기록 | 원장 값 | △ 산출만 [28] |
| 원장 동기화(미리보기/반영·presync) | 대장 → 원장 이력 | ✓ verify_registry t1~t22 · presync ✗ |
| 이전 비번 1회 로그인(원장 패널) | 불일치 계정 확인 | △ |

### 1-3. 수동 탭(사람이 쓸 때만)
| 탭/기능 | 목표 결과 | 게이트 |
|---|---|---|
| 판매 분석 탭 | 최신 판매·순위 표 | ✗ |
| 키워드 추천 탭(추천·상품명 추천·저장) | 상위 8개·제목 | ✗ · ⚠저장한 키워드를 **아무도 안 읽음**(`keyword_store.load_all/get` 호출 0) |
| 순위 조회 탭 | 키워드 1개 즉시 순위 | ✗ · ③과 **다른 구현**(offscreen·프록시 없음) |
| 상세 이미지 탭 | 내 Chrome 상품 탭 → 이미지 저장 | ✗(라이브 도구만) |
| 설정 탭(키·SA·링크 4·입력 소스·순위 간격·프록시·저장) | 설정 보존·적용 | 대부분 ✗ |
| `--export-settings`/`--import-settings` | 배포 설정 이식 | ✗ |

## 2. ⛔ 확인된 오류 (목표 결과가 안 나옴)

| # | 오류 | 근거 | 영향 |
|---|---|---|---|
| E1 ✔ | **직원이 결과시트에 입력한 키워드가 반영 안 됨** | `pipeline.py:739-740` 역머지는 `keywords_off=False` 일 때만 — 운영은 늘 True·②에도 호출 없음. 통계 시트는 매번 전체 교체 | 직원 입력 키워드가 덮어써짐(소실) |
| E2 ✔ | **마스터 복원이 막힌 경로 사용** | `pipeline_gsheet.restore_master_from_gsheet` 가 공개 export(`gsheet.download_xlsx`) — 같은 파일 백업 주석: 결과시트는 401(2026-10-02 실측) | 마스터 없는 PC(재설치)에서 과거 시계열 복원 실패 → 새 통계로 시작 |
| E3 ✔ | **18:00 예약작업 13시간 제한** | `deploy/install.ps1:201` `-ExecutionTimeLimit 13h`(재부팅 복구 작업도 같은 설정) | 07:00 넘게 돌면 스케줄러가 앱 강제 종료 = '무인 강제 종료 금지' 위반 · D-020 상 **정산도 함께 종료** |
| E4 ✔ | **정산 상태확인 bat 오안내** | `deploy/정산_상태확인.bat:19-23` 이 없앤 예약작업을 조회 → "정산 자동 다운로드가 안 돕니다" | 정상인데 고장으로 안내 |
| E5 | install.ps1·설치 안내 문구 "06:00 자동 종료" | `install.ps1:196,199,203,228` — 06:00 강제 종료는 2026-09-23 폐지 | 잘못된 안내 |
| E6 | `tools/simulate_stages.py` 고장 | `:106` `P.organic_ranks_batch` — pipeline_ranks 로 이동됨 → AttributeError(게이트 밖) | 도구 실행 불가 |
| E7 | 게이트 설명 문구 불일치 | `run_checks.py` "9종/8종"·`install_hooks.py` "3종" vs 실제 16/15종 | 안내 오류 |

## 3. 죽은 코드·중복 (삭제·통합 후보)

### 3-1. 운영에서 실행되지 않는 분기 (✔ 핵심 사실 기반)
- `run_full` 인라인 키워드·순위: `pipeline.py:446-469`(인라인 drive_rank)·`:739-740`(→E1 은 ②로 재연결)·`:774-775`, `pipeline_process.py:321-355`(`_resolve_keywords`·`_frozen_keywords`·`_log_diagnose`)·`_select_keywords_for_skipped`·wb `title_cache`.
- 자동(offscreen) 순위: `track_ranks_stage(semi=False)`(`pipeline_ranks.py:349-390`)·`_measure_product_auto`·`_measure*`.
- 설정으로 꺼진 레거시: `organic_ranks_batch` 병렬 경로(`RANK_NAV_SERIAL=True`)·`_wait_user_search`(`RANK_SEMI_AUTOSUBMIT=True`)·`_semi_retry_login`(unattended 항상 False).
- ⚠ 이 분기들을 **게이트 시나리오(simulate 1~9·11~14·핀 F·N·O·O2)가 검증 중** → 삭제와 함께 시나리오를 **운영 조합으로 이전**해야 함(그래야 게이트가 운영 경로를 지킴 — 회귀 반복의 구조적 원인).

### 3-2. 쓰기만 하고 읽지 않음
- ✅ 삭제(B3): `session_store`(쿠키 저장)·`wing_session` · `collector.save_discovered`(`data/discovered/*.json`). 유지: `keyword_store`(키워드 탭 저장).

### 3-3. 테스트만 쓰는 함수
- `product_match.scope_to_ledger` · `input_list.parse_password_rows` · `payout.estimate` · `settlement_amount.py` 전체 · `settlement_parse` Insights 파서 · `registry.managed_between` · `proxy_manager` 미사용 메서드 12개.

### 3-4. 중복 구현
| 중복 | 내용 | 정리안 |
|---|---|---|
| UI 2벌 | `ui/app.py`(Tk·미배포·동작 이미 갈라짐) vs `app_qt` | app.py 삭제 |
| 야간 조립 3벌 | `start_auto`·`start_resume`·`_full_pipeline_task` 가 ①→②→③→역기록을 각자 조립 | 백엔드 함수 1개로 → `--auto`/`--resume` 게이트 공백도 해소 |
| 절전 방지 2벌 | `power.keep_awake` vs `app_qt._prevent_sleep` | power 로 통일 |
| 순위 구현 3벌 | ③반자동 · 순위 조회 탭(offscreen) · 자동/병렬(미사용) | 미사용 삭제 · 탭은 ③ 경로 재사용 또는 탭 삭제 |
| 키워드 점수 2벌 | 키워드 탭 `_score` vs ② 100점 | 탭 유지 여부에 따라 |
| 구글시트 내려받기 2벌 | 공개 export(복원) vs SA(백업) | SA 로 통일(=E2 수정) |
| 비번 경로 5개 | 후보(운영)·rows(테스트)·file(Tk)·원장 이전값·credstore | 운영 경로 하나로 |
| 정산 중지 2벌 | `app_process.stop_settlement` vs 패널 `_kill_settlement` | stop_settlement 로 |
| 옛 정산 예약작업 제거 3곳 | 18:00 매번·install.ps1·remove_autorun | 18:00 매번 제거는 삭제 가능 |
| 정산 실행 bat | `정산_지금실행.bat`(run — 회차·부모감시와 무관) | watch 로 통일 또는 삭제 |

### 3-5. 일회성 도구(임무 완료)
`normalize_dates`·`rebuild_workbook`+`reflect_log_to_excel`·`recover_keywords`·`rebuild_index`/`relink_index`/`relink_index_inplace`·`registry_backfill`(실행 완료)·`simulate_stages`(고장)·`tools/upload_to_gdrive.bat`(rclone 폐기).
보류(소유자 확인): `diag_inv_hidden`·`test_rank_images_live`·`probe_proxy_pool`·`migrate_to_operation_ledger`·`build_*` 4종·`install_schedule_py.*`.

## 4. 배포 안 된 신규 도메인 (죽은 코드 아님 — 연결 여부 결정 필요)
- `app_integrated.py` + 계약(`contract_store`)·채권자(`creditor_store`)·업무일지(`worklog_store`)·CS(`cs_*`) — 로컬 JSON 으로만 동작, 운영 앱에서 접근 불가. 게이트 4종이 검증.
- 소싱(`sourcing*`) — UI 없음(테스트만).
- 정산 '계약자 정산' 시트 — 계약금액 입력 기능이 없어 늘 빈칸(설계상 '나중에 입력' = 정산 ②층 미구현).

## 5. 게이트 공백 (운영 기능인데 목표 결과를 지키는 테스트 없음)
`--auto`/`--resume` 조립 · 설정 저장/내보내기/가져오기/자동 로드 폴백 · 그로스 재고 역기록 · 쿠팡확인 원장 기록 · 원장 presync · 마스터 복원 · 판매분석 엑셀 다운로드 폴백 · 정산 중지 · 수동 탭 4개.

### 5-1. 조사 밖에서 추가 발견
- `reusable_coupang/`(git 8파일) — 앱이 import 안 함. 다른 프로젝트용으로 일부러 뽑은 **독립 패키지**(README·커밋 6904991) → 죽은 코드 아님·유지 여부는 소유자 확인.
- `tests/test_regression_gate.py` — pytest 로 게이트(run_checks --quick)를 돌리는 진입점(DECISIONS 기록) → 유지.
- 루트 `login_source_260904/`·`src - 복사본/` — **git 밖(.gitignore) 로컬 사본**. 저장소와 무관·지우면 복구 불가 → 소유자 확인 후 처리.

## 6. 소유자 결정·진행 (2026-10-10, D-022)
- 결정: 수동 탭 4개(판매 분석·키워드 추천·순위 조회·상세 이미지) **유지** · 신규 도메인(통합앱·계약·채권자·업무일지·CS·소싱) **유지(나중 연결)** ·
  정산 금액 식(`settlement_amount`)·Insights 파서 = 정산 ②층 설계 자산이라 유지 · 죽은 코드·중복 정리 **진행** · 오류 E1~E7 은 정리 뒤 **한꺼번에 수정**.
- 순서(묶음마다 호출처 재확인 → 물리 삭제 → 게이트 → 커밋):
  - ✅ B1 Tk `ui/app.py` + `parse_password_file` (−896줄, d55c397)
  - ✅ B2 일회성 도구 10개 (−1,155줄, 0a5d5d3)
  - ✅ B3 쓰기만 하는 저장소: `session_store`·`wing_session`·`collector.save_discovered` (키워드 탭 유지라 `keyword_store` 는 유지) — 계정당 배송관리 페이지 추가 이동 1회도 함께 사라짐
  - ⏳ B4 테스트 전용 함수: `product_match.scope_to_ledger`·`parse_password_rows`·`payout.estimate`·`registry.managed_between`·`proxy_manager` 미사용 메서드
  - ⏳ B5 운영에서 안 도는 분기(§3-1) — **먼저 게이트 시나리오를 운영 조합으로 이전**(게이트가 운영 경로를 지키게) 후 삭제
  - ⏳ B6 중복 통합(§3-4): 야간 조립 3벌→백엔드 1개(+`--auto`/`--resume` 게이트) · 절전 2벌 · 정산 중지 2벌 · 18:00 옛 예약작업 제거 · `정산_지금실행.bat`
  - ⏳ 오류 E1~E7 일괄 수정(§2)
