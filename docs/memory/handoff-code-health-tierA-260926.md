---
name: handoff-code-health-tiera-260926
description: "코드건강 재점검(2026-09-26) — vulture/radon 측정으로 회귀 확증(9이슈 대량수정 부작용 D+ 8개 재유입), Tier A(제자리 분해+게이트 구멍 수정) 완료·게이트 초록. Tier B(모듈 분리 MI C→B) 다음."
metadata:
  node_type: memory
  type: project
  originSessionId: 3588291b-3435-4968-8471-8410129d1b69
  modified: 2026-09-26T07:44:55.626Z
---

소유자 요청 "전체 소스코드 점검(누더기·과거 정상→오류)" + "Tier A+B 연속" 지시로 착수. **Tier A 완료·미커밋 상태에서 커밋 진행**(이 메모 시점).

## 측정으로 회귀 확증 (재현=`designs/CODE_HEALTH_PLAN.md §6`)
- **크기 폭증(9/22→9/26·9이슈 부작용)**: pipeline 1933→2684(+751)·workbook 1576→2460(+884)·collector 740→840(MI A→B).
- **MI**: pipeline·workbook·app_qt = **C(0.00)** 포화(모듈 분리 전엔 안 오름)·app B(11.54).
- **⚠D+ 8개 재유입**(9/22 "4파일 D/E/F 전멸"이 깨짐·전부 9이슈 신규/대폭수정 함수): pipeline `preflight_sync_check` D28·`_discover_products` D26·`_semi_track_product` D21 / workbook `_reindex` D27·`_migrate_keyword_col` D27·`_index_row` D23·`promo_effect` D22·`_regroup_sheet_blocks` D21.
- **원인=게이트 구멍**: `check_complexity.py` 가 4파일(KNOWN_BAD) **내부** D+ 를 경고조차 안 함 → 무저항 유입. 죽은코드는 vulture 80% 1건뿐(삼항식).
- **판정**: 삭제 아님·전면재작성 아님 → **제자리 분해 + 게이트 구멍 메우기 + 모듈 분리**.

## Tier A(저위험·회귀 즉시 차단) — ✅ 완료
- **8개 D 함수 행동 불변 제자리 분해**(전부 ≤C·게이트 매 단계 초록):
  - workbook: `_regroup_sheet_blocks`→+`_snapshot_blocks`/`_rewrite_blocks` · `promo_effect`→+`_promo_series_ba`/`_promo_sales_part`/`_promo_rank_part` · `_reindex`→+`_scan_meta_vids`/`_reindex_meta_rows`/`_reindex_sheet` · `_migrate_keyword_col`→+`_kw_migrate_targets`/`_apply_kw_migrate` · `_index_row`→+`_idx_name_cell`/`_idx_status`/`_idx_promo_cell`.
  - pipeline: `preflight_sync_check`→+`_preflight_summary`/`_log_preflight` · `_discover_products`→+`_discover_inventory`/`_pid_by_vid`/`_log_discover_summary` · `_semi_track_product`→+`_semi_prep_product`(가드/준비)+루프만 본체.
- **게이트 구멍 수정**(`tools/check_complexity.py`): 4파일 MI C 허용하되 **D+ 0 유지가 규칙**(재유입=exit 1 차단·`bad_monsters`)·건강 파일 기존 D+ 7개(input_list `_parse_grid` F45·kw_recommend `_assemble_candidates` F45·`select_keywords_light` E32·product_match `_assign` E40·browser `wait_for_login` D27·rank `organic_ranks_batch` D25·input_list `write_ledger_inventory` D22)는 경고 유지.
- **죽은 삼항식 제거**: `detail_images.py:149` `best[key][1] if False else src`→`src`.
- **검증**: 게이트 7종(run_checks)+`check_complexity`(exit 0) 초록. `radon cc -n D <4파일>`=빈결과. 행동 불변(핀 3종·simulate·verify_render 불변 통과).

## Tier B(모듈 분리·MI C→B) — ✅ pipeline 완전 해소, 🔄 workbook 남음
- ✅ **pipeline 6모듈 전부 A/B**(원래 2684줄 C 몬스터): pipeline.py **A(20.94)**·pipeline_sales A(41)·pipeline_process A(27)·pipeline_ranks **B(14.93)**·pipeline_gsheet A·pipeline_paths A. 커밋 `f90d913`(A)·`7b08dc2`(B1·B2)·`f28e34f`(B3)·`d7c54f8`(B4·B5). 게이트 7종+복잡도 초록.
- **재배선 규칙(교훈)**: 이동 함수가 **내부 호출**하는 심볼은 **이동한 모듈**에서 monkeypatch. 이중 소속(warmup·WingBrowser·select_keywords_light·recommend_title)은 관련 모듈 전부 patch. run_full 이 호출(_login_and_discover 등)=P 재수출 유효. 핀이 oracle(틀리면 게이트 red). 의존 DAG: paths←gsheet←ranks←sales←process←pipeline.
- ✅ **workbook 렌더/인덱스 분리 완료(6a·6b 커밋)**: workbook 2460 → workbook.py 1501(C·KNOWN_BAD) + `workbook_common`(A 51.5·상수·헬퍼·dataclass) + `workbook_render`(A 23.2·apply_style·_style_*·_v4_*·regroup·migration·팔레트상수) + `workbook_index`(A 37.3·_build_index·_index_row·_idx_*·promo_effect). `class OutputWorkbook(_RenderMixin, _IndexMixin)`. monkeypatch 재배선 0(블랙박스·핀 oracle). 게이트 7종+복잡도 초록·행동 불변. 커밋 `4b421a1`.
  - ⚠**workbook.py 코어(1501) 는 여전히 C**(응집 데이터모델) — 추가 분해=diminishing returns 로 **보류**(복잡도 게이트는 KNOWN_BAD 통과·실제 rot=복잡 렌더는 A급 모듈로 해소). 굳이 B 원하면 setter/getter mixin 추가 분리(저위험).
- **⚠라이브 검증**: pipeline_sales(로그인·Akamai·수집) 오프라인 핀 100% 미커버 → 사무실 ①판매수집 1회 라이브 확인 권고.

## 남은 것
- workbook.py mixin 분리(위·새 세션 권고). 라이브 검증(운용 PC 재배포)은 [[handoff-9issues-images-260926]] 체크리스트 그대로 유효(별건).

관련: [[handoff-code-health]] [[code-health-regression-gate]] [[fix-from-real-evidence]] [[commit-with-design-and-memory]] [[handoff-9issues-images-260926]].
