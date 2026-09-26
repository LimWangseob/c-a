---
name: fix-gsheet-movedimension-merge-400
description: ✅라이브 버그수정(2026-09-26) — 계정목록 ④열이동(_ensure_column_order moveDimension)이 제목 병합(A1:I1) 가로질러 Google 400. 병합해제→이동→재병합 한 배치로 수정. FakeClient 병합제약 모델링해 재현·게이트. 로컬/통계는 정상·계정목록만 미갱신이었음(무손실).
metadata:
  node_type: memory
  type: project
  originSessionId: c16f3da3-27f9-41ca-bf1d-0a9ab5b96704
  modified: 2026-09-26T00:17:41.992Z
---

**증상(실측)**: 운용 PC 새 코드 첫 실행(2026-09-26 02:13·03:14·07:11 3회) 로그 `단계='계정목록 동기화' · GSheetError status=400 · Invalid requests[0].moveDimension`(로그는 소스에서 "requests[0].m"까지 절단). 통계 25시트 미러링 완료 후 계정목록 동기화에서만 실패.

**Why:** 항목④(계정ID→C 열이동)의 `gsheet_index._ensure_column_order`가 `moveDimension`으로 계정ID 열을 옮기는데, 계정목록 **1행 제목이 A1:I1(N_COLS) 로 병합**돼 있어 **그 병합을 가로지르는 열 이동을 Google 이 거부**(병합보다 좁은 이동이 병합을 쪼갬). 증분 경로에서 단일요청 "m" 배치는 이것뿐(=확정).

**How(수정):** `_ensure_column_order`가 moveDimension **전에 제목 병합 해제 → 이동 → 재병합**을 한 배치로. 엣지(옛 8열 시트)는 재병합이 그리드 벗어나지 않게 `appendDimension`으로 **N_COLS 먼저 확장**. 순서=appendDimension→unmergeCells(row1,0..N_COLS)→moveDimension→mergeCells(row1,0..N_COLS). unmergeCells 는 범위 겹치는 병합만 제거(없으면 no-op).

**게이트 미포착 → 재현 추가:** verify_gsheet 의 `_FakeClient` 가 moveDimension 을 단순 적용만 하고 **병합 제약 미모델**이라 오프라인 통과·라이브 거부(fake↔live 갭). → FakeClient 에 `_merges` 추적(mergeCells/unmergeCells 반영)+**moveDimension 이 병합(폭>1) 가로지르면 raise**(400 재현) 추가. 핀 verify_gsheet[11]: 제목 병합 있는 옛 8열 시트 → 병합해제·열이동·재병합·N_COLS 확장으로 무오류 수렴(수정 전이면 raise).

**영향 범위(무손실)**: 로컬 마스터·스냅샷·구글 **통계 25시트**는 정상(새 포맷·상품군 정렬 치유·쿠팡링크 40/40·⑥완전삭제 14건·계정ID열 C 적용 확인). **구글 계정목록 탭만** 미갱신이었음(옛 포맷 유지). 데이터 유실 없음.

**즉시 우회(코드 없이)**: 구글 결과시트 `계정목록` 탭 삭제 → 다음 실행이 `_full_build`로 새 포맷 생성(빈 시트라 moveDimension 없음·400 없음). ⚠단 계정목록 직원 마케팅 E~G 입력은 삭제 전 백업.

관련: [[feature-business-name-grouping]] [[feature-product-coupang-link]] [[fix-multiaccount-reconcile-scope]] [[fix-from-real-evidence]] [[gsheet-unified-spec]].
