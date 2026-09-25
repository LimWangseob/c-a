---
name: handoff-code-health
description: ⭐코드 건강 정비 인계(2026-09-22) — 회귀 게이트+제자리 분해 **완료**(4파일 D/E/F 괴물함수 전멸·전부 C 이하·푸시됨). 남은=모듈 분리(MI B)·라이브 검증. 새 세션은 designs/CODE_HEALTH_PLAN.md 먼저.
metadata: 
  node_type: memory
  type: project
  originSessionId: 89086b56-f291-4370-bba6-14f384f3ff5a
  modified: 2026-09-22T04:46:48.369Z
---

**새 세션 인계 — 코드 건강 정비(회귀 차단 + 썩음 정리).** 소유자: "소스가 누더기·과거정상→오류 반복." 4단계 방법론
(테스트+3계층 훅 → CLAUDE.md/메모리 규칙 → vulture/radon 측정 → 나쁜 파일 핀테스트→제자리 재작성)으로 진행.

**⭐ 새 세션은 [designs/CODE_HEALTH_PLAN.md](designs/CODE_HEALTH_PLAN.md)를 먼저 읽어라** — 측정 리포트 전체 + 실행 런북 + 재현 명령 + 체크박스가 거기 있다.

> ✅ **완료 상태(2026-09-22)**: 아래 측정은 착수 시점 기준선. **4개 나쁜 파일의 괴물함수는 이제 전부 C 이하로 정리됨**(§진행 상황). 파일 MI 만 여전히 C(대형파일 radon 포화 — 모듈 분리 필요). `_assemble_candidates`/`_parse_grid`/`_assign` 은 **A등급(건강) 파일**이라 규칙상 미접촉(그대로 둠).

## 측정 결론 (착수 기준선 · 2026-09-22, 커밋 dbcb11f)
- **썩음=4개 파일 집중**(radon MI C): `pipeline.py`(1933)·`workbook.py`(1576)·`app_qt.py`(1617)·`app.py`(911). **나머지 25+ 모듈은 A(건강) → 손대지 말 것.**
- **괴물 함수**(radon CC F/E, 착수 시점): `run_full` F75·`_process_account` F72·`_login_and_discover` F54·`_track_ranks_semi` F45(pipeline), `apply_style` F52(workbook), `do_run_full` E33(app_qt/app) → **전부 정리 완료**. `_assemble_candidates` F45·`_parse_grid` F41·`_assign` E40 은 건강 파일이라 미접촉.
- **죽은 코드 아님**(vulture 80%서 1건). 처방=**전면 재작성 아님·제자리 분해**.
- **인프라 0**: pytest·tests/·git 훅 전무. 테스트=수동 스크립트 3개(verify_offline 16.4s[⚠실API 의심]·verify_gsheet 1.0s·simulate 8.4s). **vulture·radon는 pip 설치 완료.**
- **회귀 출처**: git log에 되돌림 반복(판매상태 RFM↔productStatus 3회·키워드 로직) — 막을 게이트가 없었음.

## 진행 상황
- ✅ **단계1·2 완료(2026-09-22)**: 회귀 게이트 `tools/run_checks.py`(전체 3종 16.9s·`--quick` 시뮬+구글시트) + `tools/check_complexity.py`(MI 회귀 차단·괴물함수 경고) + `tools/install_hooks.py`(pre-commit=문법+quick·pre-push=전체+품질) + `verify_offline` [6] **결정적 모킹**(16.4→3.3s·실API는 `VERIFY_REAL_API=1` 옵트인) + CLAUDE.md "코드 건강 규칙" 섹션 + 메모리 [[code-health-regression-gate]]. 훅이 깨진 커밋 차단 실증 완료. 규칙=[[code-health-regression-gate]].
- ✅ **단계4 완료 — 4개 나쁜 파일의 D/E/F 괴물함수 전멸(전부 C 이하, 2026-09-22, 커밋 05ac18b~09f3a46, 원격 푸시됨)**. `radon cc <4파일> -n D` = 빈결과.
  - **pipeline.py**: run_full F75→C15·_process_account F72→C18(05ac18b~66bb61f) · _login_and_discover F54→오케(96d7205: _ensure_login/_fresh_login/_semi_retry_login/_resolve_login_failure + _discover_products/_run_discover/_augment_vids) · _track_ranks_semi F45→오케(5e6185e: _SemiState + _semi_track_product/_semi_search_one/_semi_on_miss/_semi_record) · select_keywords_stage D25→B9·track_ranks_stage D25→C14(80ce11f: _select_product_keywords·_measure_product_auto).
  - **workbook.py**: apply_style F52→A3(3388f35: _StyleCtx + _sty_cell/merge/edge + _style_sheet/_style_block/_style_metric_rows/_style_keyword_rows/_flag_sale_mismatch/_style_block_edges) · _build_index D29·normalize_date_columns D26·set_display_name D21 전부 정리(8f5e810: _IdxStyle/_index_row·_normalize_sheet_dates/_rebuild_date_grid·_rekey_block).
  - **app_qt.py·app.py**: do_run_full E33/E34→C16/18(5f38502) — 실행모드 로직을 **순수 백엔드로 공통화**(pipeline: plan_run_mode/RunPlan·run_title·run_log_labels) + 각 UI _require_run_inputs·_full_pipeline_task(스냅샷 인자). app_qt=단계마커+재고역기록·app.py=미포함(폴백 기존동작).
  - **핀 3개 신설**: pin_login_ranks(16시나리오·경계만 페이크·실제함수 구동)·pin_apply_style(S1~6 서식 골든값)·pin_run_plan(P1~7 실행모드·라벨). **게이트=run_checks 6종**(quick 5종).
- ⬜ **다음 세션(성격 다른 별도 작업)**: ①**모듈 분리**로 4파일 MI C→B(대형파일 radon 포화라 함수 쪼개기론 안 오름·pipeline_sales/ranks/gsheet 등. ⚠테스트가 P._login_and_discover 등을 **이름으로 가로채기** 하므로 함수 이동 시 가로채기 지점 재배선 필수) → ②**라이브 검증**(로그인·순위 사무실 1회). 착수 레시피=designs/CODE_HEALTH_PLAN.md §단계4.

## 안전규칙
- A등급 파일 미접촉·행동 불변(위치만 이동·정책/엣지케이스 보존)·게이트 통과 없이 다음 금지.

관련: [[fix-from-real-evidence]] [[commit-with-design-and-memory]] [[recommend-new-session-when-degraded]] [[respond-in-korean]] [[plain-language-no-jargon]] [[exe-packaging-deploy]].
