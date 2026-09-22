# 코드 건강 정비 런북 (회귀 차단 + 썩음 정리)

> 목적: 잦은 수정으로 4개 파일이 비대·괴물함수화되고 회귀("과거 정상→오류")가 반복됨. 이 문서는 **측정된 데이터**와
> **실행 계획**을 담아, 새 세션이 그대로 이어받아 진행하게 한다. 소유자 지시 순서(4단계)를 따른다.
> 작성 2026-09-22. 기준 커밋 `dbcb11f`(폴더/경로 재설계 + 복원 버그2 + config.json). 작업트리 깨끗.

## 0. 핵심 결론 (먼저 읽기)
- **누더기는 전 코드가 아니라 4개 파일에 집중**: `pipeline.py`·`workbook.py`·`app_qt.py`·`app.py`. 나머지 25+ 모듈은 **건강(radon MI = A)** → **건드리지 말 것**.
- 문제는 **죽은 코드가 아니라**(vulture 신뢰도 80%서 1건) **거대 함수 + 회귀 방어장치 0**(pytest·tests/·git 훅 전무).
- 처방 = **전면 재작성 아님**(로직은 맞고 검증 통과). **"회귀 게이트 세팅 → 제자리 분해"**.
- **측정도구 설치됨**: `vulture`, `radon`(pip). pytest는 미설치(현재 테스트=수동 스크립트 3개).

## 1. 측정 리포트 (2026-09-22, 재현 명령은 §6)

### 1-1. 크기 (총 12,382줄)
| 파일 | 줄 수 |
|---|---|
| src/coupang_analytics/pipeline.py | 1933 |
| ui/app_qt.py | 1617 |
| src/coupang_analytics/workbook.py | 1576 |
| ui/app.py | 911 |
| collector.py | 740 · input_list.py 556 · browser.py 520 · rank.py 514 · gsheet_index.py 491 (그 외 전부 <420) |

### 1-2. 유지보수지수 radon MI (낮을수록 썩음: A>B>C)
- **C (0.00)**: `pipeline.py`, `workbook.py`, `app_qt.py`  ← 최악
- **C (8.51)**: `app.py`
- **나머지 전부 A (21~100)** — 정상. (collector 21.7, input_list 25.8, browser 28.8, rank 31.2 … appconfig 84, apppaths 78)

### 1-3. 복잡도 radon CC (전체 평균 B/5.5=정상. 괴물 함수만 문제)
| 함수 | 등급(CC) | 파일 |
|---|---|---|
| `run_full` | **F (75)** | pipeline.py:1111 |
| `_process_account` | **F (72)** | pipeline.py:753 |
| `_login_and_discover` | **F (54)** | pipeline.py:447 |
| `_track_ranks_semi` | F (45) | pipeline.py:1787 |
| `apply_style` | **F (52)** | workbook.py:993 |
| `_assemble_candidates` | F (45) | kw_recommend.py:161 |
| `_parse_grid` | F (41) | input_list.py:213 |
| `_assign` | E (40) | product_match.py:75 |
| `do_run_full` | E (33/34) | app_qt.py:1032 · app.py:438 |
| `_build_index` D29 · `normalize_date_columns` D26 · `set_display_name` D21 | D | workbook.py |
| `track_ranks_stage` D27 · `select_keywords_stage` D25 | D | pipeline.py |
| `wait_for_login` D27 (browser) · `organic_ranks_batch` D25 (rank) · `write_ledger_inventory` D22 (input_list) | D | (단발성, 우선순위 낮음) |

### 1-4. 죽은 코드 vulture
- 신뢰도 80%: **1건**(`detail_images.py:149` ternary). 60%: 59건(대부분 오탐=동적호출·미사용인자).
- 알려진 사문화(가드로 미호출): `pipeline._backfill_ranks`/`_measure_unfilled_once`, `kw_shopping.py`(네이버쇼핑 API 종료). vulture가 못 잡음(참조는 남아서). 분해 중 함께 제거 검토.

### 1-5. 테스트/훅 인프라 = 없음
- pytest·`tests/`·`pytest.ini`·git 훅 **전무**. 테스트=수동 스크립트 3개:
  - `tools/verify_offline.py` — **16.4s** (⚠[6] Phase B가 실 OpenAI/네이버 API 호출 의심 → 느리고 불안정)
  - `tools/verify_gsheet_offline.py` — 1.0s
  - `tools/simulate_pipeline.py` — 8.4s (모킹 14시나리오)
  - 합 ~26s. 전부 `python tools/X.py`로 실행, `[통과]/[실패]` 출력.

### 1-6. 회귀 출처 (git log 최근 20)
- **되돌림 반복**: 판매상태 RFM↔productStatus 3회(`51c042b` 되돌림 → `871706a` 재적용), 키워드 로직(`69e7561`→`53174ef` 되돌림). 막을 게이트가 없어 회귀가 반복 유입.

## 2. 진단
①4개 파일이 비대·괴물함수라 한 가지 고치면 다른 분기가 깨짐 ②커밋 전 회귀를 잡을 게이트 0 ③근거 없는 되돌림.
→ 처방 = **정리(제자리 분해) + 회귀 게이트**. 전면 재작성은 위험(하드코딩된 엣지케이스·정책 다수).

## 3. 4단계 실행 계획

### 단계 1 — 테스트 게이트 + 3계층 훅  ✅ 완료 (2026-09-22)
- [x] `tools/run_checks.py` 신설 = 3 스크립트 **서브프로세스** 순차 실행(하나 죽어도 나머지 계속)·하나라도 실패 시 exit 1·요약. `--quick`=빠른 2종(시뮬+구글시트, pre-commit용). 전체 **16.9s**(<30s).
- [x] **verify_offline 실 API 제거**: [6]을 **결정적 모킹**으로 교체 — `kw_ai._ask`/`_client`(OpenAI)와 `_FakeNaver`(네이버) **경계만** 페이크, 실제 `select_keywords_light` 로직(후보조립→판정→압축→AI선정) 그대로 실행. 판정/선정 페이크는 프롬프트 안 후보를 되받아(echo) 일관 유지. **16.4→3.3s·결정적.** 실 API 실증은 `VERIFY_REAL_API=1` 옵트인(기존 경로 보존).
- [x] **3계층 훅**(`tools/install_hooks.py`가 SSOT·`.git/hooks/`에 기록·`--status`/`--uninstall`):
  1. **pre-commit**: 스테이징 .py `py_compile` + `run_checks.py --quick`(시뮬+구글시트, ~12s).
  2. **pre-push**: `run_checks.py`(전체) + `check_complexity.py`(품질).
  3. **품질 게이트** `tools/check_complexity.py`: 4파일(KNOWN_BAD) **밖** 파일이 MI **C로 추락 시 차단**(exit 1) + 4파일 밖 새 **D+(CC≥21) 괴물함수 경고**(현재 7개=기존 단발성). radon 미설치면 조언만(통과).
- 수용기준 ✅: `run_checks.py` 초록 + 훅이 문법오류 스테이징 커밋을 실제 차단(실증 완료·로그 head 불변).

### 단계 2 — CLAUDE.md 규칙 + 메모리  ✅ 완료 (2026-09-22)
- [x] CLAUDE.md에 "코드 건강 규칙 (회귀 방지)" 섹션 추가(커밋 전 게이트·실 API 금지·CC≤15·파일≤600·되돌림 근거 메모·건강 파일 미접촉·행동 불변 분해).
- [x] 메모리(feedback) [[code-health-regression-gate]] 저장([[fix-from-real-evidence]]·[[commit-with-design-and-memory]] 연결) + [[handoff-code-health]]·MEMORY.md 갱신.

### 단계 3 — 썩음 측정  ✅ 완료 (이 문서 §1). 판정 = **정리(분해)**.

### 단계 4 — 나쁜 파일부터: 행동 고정 → 제자리 분해
순서(썩음순): **① pipeline.py → ② workbook.py → ③ app_qt.py → ④ app.py.**
각 파일 공통 절차:
1. **핀 테스트 보강**: 그 파일의 핵심 행동을 `simulate_pipeline`/`verify_offline`이 이미 덮는지 확인, 얇으면 시나리오 추가(먼저!).
2. **분해**(제자리·행동 불변):
   - `pipeline.py`(1933) → **모듈 분리** 제안: `pipeline_sales.py`(①로그인·발견·판매수집·`_login_and_discover`/`_process_account`), `pipeline_ranks.py`(③ `track_ranks_stage`/`_track_ranks_semi`/자동순위), `pipeline_gsheet.py`(`_push_gsheet`/`push_ledger_inventory`/`restore_master_from_gsheet`), `pipeline.py`=오케스트레이터(`run_full`을 단계 호출자로 축소). **`run_full` F75·`_process_account` F72를 작은 함수로 추출**(계정 루프·옵션 루프·지표기록·마이그레이션 분리).
   - `workbook.py`(1576) → `apply_style` F52를 렌더 헬퍼로 쪼개기, 인덱스/날짜정규화 분리 검토(단 openpyxl 상태 결합 주의).
   - `app_qt.py`/`app.py` → `do_run_full` E33 공통 로직을 백엔드/헬퍼로 빼 UI 중복 축소.
3. **매 추출 후 `run_checks.py` 통과**(초록 유지가 절대 규칙). 커밋은 작게·자주.
- 수용기준: 파일 MI가 C→B이상, 괴물 함수 CC가 F→C이하, 검증 3종 계속 초록.

#### pipeline.py 진행 (2026-09-22, 커밋 05ac18b~66bb61f)
- ✅ **`run_full` F(75)→C(15)**: `_column_label`·`_reconcile_ledger_accounts`·`_finish`(+`_RunCtx`)·
  `_collect_session_first`/`_collect_with_login`·`_init_run_state`(+`_RunInit`)·`_validate_or_raise`·
  `_finalize_run` 추출. run_full=오케스트레이터(검증→초기화→컬럼→2패스 수집→대조→마무리).
- ✅ **`_process_account` F(72)→C(18)**: `_ProcCtx`+`_process_option`(C14)·`_resolve_keywords`(C11)·
  `_frozen_keywords`(C18)·`_migrate_product_blocks`(C16) 추출.
- ✅ **핀 테스트 보강 완료(2026-09-22)**: `tools/pin_login_ranks.py` 신설 — `_login_and_discover`·
  `_track_ranks_semi` 를 **실제 코드로** 오프라인 구동(경계만 페이크: `WingBrowser`=`_FakeWing`,
  collector 함수, rank 헬퍼). 13시나리오로 제어흐름 고정: **A**세션재사용·**B**NeedLogin(1차 미제출)·
  **C**LoginBlocked·**D**LoginCredentialError(재시도 없음)·**E**otp 건너뜀·**F**반자동 1회 재시도 회복·
  **G**discover PWTimeout→상품조회 vid 계속·**H**Failed to fetch 1회 재시도·**I**상품조회 실패→판매분석 폴백·
  **J**반자동 순위 정상·**K**차단→쿨다운 재개·**L**쿨다운 초과→당일 중단(halt)·**M**키워드 없는 2차 블록 건너뜀.
  `run_checks.py`(quick 포함)에 4번째로 배선, 전체 게이트 27.9s(<30s)·결정적. **이제 두 함수 분해 시 회귀 감지됨.**
- ⬜ **남은 괴물(분해 대상)**: `_login_and_discover` F(54)·`_track_ranks_semi` F(45)·`track_ranks_stage` D(27)·
  `select_keywords_stage` D(25). 핀 커버 확보 → §START HERE 2번대로 제자리 분해(이른 return·예외 제어흐름 보존).
  파일 MI 는 이 둘이 F 라 아직 C(0.00).
- **모듈 분리**(pipeline_sales/ranks/gsheet)는 함수 CC 정리 후 별도 단계로(지금은 제자리 분해로 충분).

#### ⭐다음 세션 착수 레시피 (START HERE — pipeline.py 마저)
0. **환경 확인**: `python tools/install_hooks.py --status`(둘 다 '설치됨'), `python tools/run_checks.py`(초록) 먼저.
   커밋 기준선 = `66bb61f`(분해7/N) 또는 `e19e551`(문서). 미푸시 커밋 9개 있음.
1. **⚠핀 테스트 먼저(필수)**: `_login_and_discover`·`_track_ranks_semi`는 **simulate 가 통째로 페이크**
   (`tools/simulate_pipeline.py`의 `_fake_login_and_discover`·`_fake_track_ranks_semi`로 `_install_fakes`가
   교체) → **실제 코드가 오프라인에서 0% 실행됨.** 지금 추출하면 회귀를 못 잡는다. 먼저 커버를 붙일 것:
   - **방법**: 실제 함수를 돌리되 **경계만** 페이크. `_login_and_discover`는 `WingBrowser`(현재 `_FakeBrowser`는
     빈 스텁 → `goto`/`page.wait_for_timeout`/`authenticated`/`autofill_login`/`wait_for_login`/`classify_login`/
     `show`/`hide`/`page.url` 를 갖도록 확장)와 collector 함수(`fetch_vendor_inventory`/`discover`/`fetch_inventory`/
     `sale_status_by_vid`/`fetch_sales_roster`) 를 페이크로. 검증할 분기: **세션재사용**(authenticated=True)·
     **NeedLogin**(login=False+미인증)·**LoginBlocked**(classify 'blocked')·**LoginCredentialError**(classify
     'error', 재시도 안 함)·**otp 건너뜀**(classify 'otp'→None 반환)·**반자동 1회 재시도**(semi)·**discover 없음**
     (PWTimeout→vendor_products로 계속)·**Failed to fetch 1회 재시도**. `_track_ranks_semi`는
     `_prefill_search`/`_submit_search`/`_wait_results_loaded`/`_all_pages`/`organic_ranks`를 페이크로 실제 함수 구동.
   - 이 핀 테스트를 `verify_offline` 또는 `simulate`에 **추가하고 게이트 초록** 확인 후에만 분해.
2. **분해(핀 초록 유지)**: `_login_and_discover` F54 = 로그인 국면(세션판정·자동입력·wait·분류·반자동재시도)을
   `_ensure_login(...)`로, 발견 국면(vendor/discover/inventory/scope/augment)을 `_discover_products(...)`로 분리.
   이른 return(4-튜플)·예외(NeedLogin/LoginBlocked/LoginCredentialError) **제어흐름 절대 보존**. `_track_ranks_semi`
   F45 = 키워드 루프·쿨다운재개·차단중단을 헬퍼로. 목표 CC≤C, 게이트 매 추출마다 초록.
3. 파일 MI 가 B 이상 되면 (이 두 F 제거 시) **수용기준 달성** → workbook.py(`apply_style` F52)로 이동.
4. **라이브 검증 남김**: 로그인/순위는 오프라인 핀으로도 100% 못 잡으니, 분해 후 사무실에서 ①판매수집·③순위
   1회 라이브 확인 권장(정책 엣지케이스 실측). 근거 없는 되돌림 금지([[fix-from-real-evidence]]).

## 4. 실행 순서 (권장)
1. **단계 1·2 먼저**(게이트·훅·규칙) — 이후 모든 수정에 회귀 자동 차단. (반나절)
2. 그다음 **단계 4를 파일 하나씩**, 새 세션마다 한 파일(또는 한 함수군)씩·게이트 초록 유지. pipeline.py부터.
3. 각 세션 종료 시 이 문서 체크박스 갱신 + 메모리 반영([[commit-with-design-and-memory]]).

## 5. 안전 규칙 (지킬 것)
- **A등급(건강) 파일은 건드리지 말 것**(불필요 변경=새 회귀).
- **행동 불변 분해**: 로직 바꾸지 말고 위치만 옮기기. 정책·엣지케이스(로그인 판정·Akamai·날짜라벨·옵션분리·매칭 게이트) 보존.
- **매 단계 게이트 통과** 없이는 다음 진행 금지.
- 되돌림은 반드시 **실측 근거 메모**와 함께([[fix-from-real-evidence]]).

## 6. 측정 재현 명령
```
# 크기
wc -l src/coupang_analytics/*.py ui/*.py | sort -rn
# 유지보수지수(MI) — C가 썩음
python -m radon mi src/coupang_analytics ui -s
# 복잡도(CC) — D+ 괴물함수
python -m radon cc src/coupang_analytics ui -s -n D
# 죽은 코드
python -m vulture src/coupang_analytics --min-confidence 80
# 테스트 게이트(현재 수동)
python tools/verify_offline.py && python tools/verify_gsheet_offline.py && python tools/simulate_pipeline.py
```
(vulture·radon는 pip 설치됨. 없으면 `python -m pip install vulture radon`.)

## 7. 현재 상태 / 맥락
- 직전 세션에서 폴더/경로 재설계·복원 버그2·config.json 완료(커밋 `dbcb11f`). 배포본 빌드됨(`dist/쿠팡애널리틱스_배포.zip`, 폴더 `coupang-analytics`, 씨앗 마스터 포함). ⚠라이브 배포·오염 마스터 정리 미완(별건).
- 관련 메모리: [[handoff-code-health]] [[fix-from-real-evidence]] [[commit-with-design-and-memory]] [[recommend-new-session-when-degraded]] [[exe-packaging-deploy]].
