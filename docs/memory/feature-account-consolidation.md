---
name: feature-account-consolidation
description: ✅시트명 변경 계정 자동 일원화 구현(2026-09-25). 대장에서 담당자가 사업자명 바꾸면 계정ID 동일·시트만 옛 이름으로 고아(판매중지 오분류)→매 실행 계정ID 기준 전 계정 자동 병합(이력 보존)+구글시트 계정목록/통계 옛 이름 연동 삭제(이름 매칭). merge_account+_consolidate_renamed_accounts+delete_renamed_accounts.
metadata:
  node_type: memory
  type: project
  originSessionId: d8c440ae-0a9a-47f8-a6d2-d96209afecc7
  modified: 2026-09-25T01:45:39.623Z
---

**배경(소유자 시사점)**: 관리대장의 모든 정보(사업자명·대표자 등)는 담당자가 수시로 바꾼다 → 항상 작업 시 재작업 전제. 대장에서 이름이 바뀌면 **계정ID는 그대로**인데 결과 워크북 시트만 옛 이름으로 남아 **고아**가 됨(대조 시 활성 사업자명 목록에 없어 전 상품 판매중지로 오분류·키워드 공란). 실측 사례 = **이종훈 → 원더폴리**(비고 판매중지·키워드 없음).

**구현(2026-09-25)**:
- `workbook.merge_account(src, dst)` + `_copy_product_block(src, product, dst)`:
  - **dst 없음** → src 를 dst 로 rename(시트 title + 메타시트 `_상품ID`/`_중단`/`_마케팅`/`_계정정보` 의 사업자 컬럼 이관, reindex).
  - **dst 존재** → src 상품 중 **dst 에 없는 것만** 이력 보존 이관(dst 상품=더 최신, 유지) 후 `delete_account(src)`. 이관 = 키워드·**일자별 순위/검색량/판매지표**·vid·판매방식(kind)·판매상태·판매중지 플래그·마케팅·입고요약·판매일. 반환=이관 상품 수.
- `pipeline._consolidate_renamed_accounts(wb, input_list, log)`: 대장 (계정ID → 현재 사업자명 label) 맵 기준으로 워크북 전 시트 스캔, 계정ID가 대장에 있고 시트명이 현재 이름과 다르면 `merge_account`. **`_reconcile_ledger_accounts` 맨 앞**(삭제/판매중지 판정 **전**)에서 호출 → 옛 이름이 판매중지로 오분류되기 전에 흡수. **매 실행 자동**(일회성 수술 아님)이라 전 계정 전수 대응.

## ⚠구글시트 계정목록·통계 시트 연동 삭제(2026-09-25, 소유자: 결과파일에 이종훈·원더폴리 2행 잔존)
merge_account 는 **워크북 시트만** 정리한다. 구글시트 `계정목록`은 `plan_sync` 가 **행을 삭제하지 않아**(desired에 없으면 판매중지 표기·유지) 옛 이름 행이 그대로 남는다 → 명시적 삭제 필요.
- `_consolidate_renamed_accounts` 가 일원화한 **옛 이름 [(옛사업자명, 계정ID)…]** 반환 → `_reconcile_ledger_accounts`(이제 `(removed, renamed)` 튜플 반환)→`_finalize_run(renamed_accounts=)`→`_push_gsheet(renamed_accounts=)` 로 전달.
- `gsheet_index.delete_renamed_accounts(client, renamed)`: 계정목록 **옛 이름 행 + 옛 통계 시트** 제거. **⚠매칭키=사업자명(B열)+계정ID(D열) 동시 일치**. `delete_accounts` 의 계정ID 단독 매칭은 병합 후 옛·새 계정이 **같은 계정ID를 공유**하므로 살아남을 새 이름 행(+직원 마케팅 E~G)까지 지운다 → 반드시 이름 매칭. 새 이름 행/시트는 이후 `push_statistics`·`sync_index` 가 미러링·갱신. CC 낮추려 `_delete_index_rows_by_name` 헬퍼 분리.
- 검증 verify_gsheet_offline[3e]: 이종훈·원더폴리가 계정ID(oopean)·대표자 같아도 옛 이름 '이종훈' 행·통계 시트만 삭제·원더폴리 보존.

**드리프트 탐지**: ledger 없이도 마스터 내 두 시트가 같은 계정ID면 드리프트(진단용). 로컬 dev 마스터(Sep 18)는 드리프트 0(이종훈 드리프트는 이후 대장 변경으로 라이브 gsheet/운용PC 마스터에만 존재).

**일회성 이종훈 수정 불필요**: 이 노트북엔 복구본 마스터가 없고(운용PC에만), 이제 자동 일원화가 매 실행 처리하므로 라이브 gsheet 수작업 재수술 대신 **다음 운용 실행이 이력 보존한 채 이종훈→원더폴리 자동 병합**. 재배포 필요.

**검증**: verify_offline[16](rename 분기·병합 분기·없는 상품만 이관·이력[순위/검색량/판매중지/판매] 보존·src 삭제·왕복 정합). 게이트 6종+복잡도 초록(pipeline·workbook A/B 유지).

**남은일**: 운용 PC 재배포 → 다음 실행에서 이종훈→원더폴리 자동 병합 라이브 확인.

관련: [[handoff-3decisions-260924]] [[fix-from-real-evidence]] [[input-ledger-format]] [[seldoc-output-format]] [[commit-with-design-and-memory]].
