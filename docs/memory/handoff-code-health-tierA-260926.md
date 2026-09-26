---
name: handoff-code-health-tiera-260926
description: "코드건강 재점검(2026-09-26) — vulture/radon 측정으로 회귀 확증(9이슈 대량수정 부작용 D+ 8개 재유입), Tier A(제자리 분해+게이트 구멍 수정) 완료·게이트 초록. Tier B(모듈 분리 MI C→B) 다음."
metadata:
  node_type: memory
  type: project
  originSessionId: 3588291b-3435-4968-8471-8410129d1b69
  modified: 2026-09-26T06:22:09.555Z
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

## Tier B(모듈 분리·MI C→B) — 🔄 다음(이 세션 이어서 or 새 세션)
- **왜**: 함수 CC 낮춰도 pipeline(2684)·workbook(2460)·app_qt(1630)=MI C 포화 → 파일을 쪼개야 B↑.
- **계획**(SSOT `designs/CODE_HEALTH_PLAN.md §8-3`·§3단계4): pipeline→`pipeline_sales.py`/`pipeline_ranks.py`/`pipeline_gsheet.py`+오케스트레이터·workbook→렌더/인덱스·날짜 분리(⚠openpyxl 상태결합).
- **⚠핀 가로채기 재배선 위험**: `simulate_pipeline._install_fakes` 가 `pipeline.X` monkeypatch·import → 함수 이동 시 import 경로·페이크 대상 갱신 필요. **파일 하나씩·작은 커밋·매 추출 게이트 초록**.

## 남은 것
- Tier B 착수(위). 라이브 검증(운용 PC 재배포)은 [[handoff-9issues-images-260926]] 체크리스트 그대로 유효(별건).

관련: [[handoff-code-health]] [[code-health-regression-gate]] [[fix-from-real-evidence]] [[commit-with-design-and-memory]] [[handoff-9issues-images-260926]].
