---
name: feature-business-name-grouping
description: ✅항목5 사업자명 기준 그룹핑 구현(2026-09-25·라이브 남음). 같은 사업자명 다계정ID를 한 시트로·계정ID를 상품(줄) 속성으로·판매수집 스탬프 계정 단위화(둘째 계정 스킵 버그 해결)·계정목록 밴드 사업자명 기준·일원화 다계정 인지. 커밋 S1~S5.
metadata:
  node_type: memory
  type: project
  originSessionId: c16f3da3-27f9-41ca-bf1d-0a9ab5b96704
  modified: 2026-09-25T13:58:00.481Z
---

**항목5(소유자 2026-09-25 확정: 그룹키=사업자명만·계정ID=상품 줄 속성·계정마다 따로 로그인·수집)**. 예전 "사업자명 1개=계정ID 1개=시트 1개" 가정을 폐지. 예시=로움컨설팅 2계정ID → 한 시트. 커밋 S1~S5(master), 게이트 6종+복잡도 초록. ⚠**라이브 확인·운용 PC 재배포 남음**.

**착수 전 소유자 확정 2건(AskUserQuestion)**: ①입력 검증 완화=허용+`[SYNC]` 경고(예전 치명 차단=시트 덮어씀 방지) ②수집 단위=계정ID마다 따로 로그인·수집(스탬프 계정 단위화).

**구현(계층별)**:
- **workbook(S1)**: `set_account_id`=계정ID **집합 누적**(`_계정정보` col2 ' / ' 조인·덮어쓰기 폐지)·`account_ids_of(biz)` 전체·`account_id_of`=첫 개(후방호환). `set/product_account_id`=상품별 계정ID(**메타 `_상품ID` col12**). 판매수집 스탬프를 사업자 단위→**계정ID 키 새 숨김시트 `_수집스탬프`**(mark_sales_collected/has_sales/sales_collected_on/clear_sales_stamps 전부·`_STAMP_SHEET` `_SPECIAL_SHEETS`+`_reindex` 스킵). `account_due(biz,iso,account_id)` 그 계정 상품만 판정. `delete_account` 스탬프 정리·`_copy_product_block` 계정ID 이관.
- **pipeline(S1)**: `_process_account` 옵션 블록마다 `set_product_account_id(biz, bname, a.account_id)`. 스탬프·account_due 호출을 `a.label`→`a.account_id`. (⚠`_sheets` 테스트 헬퍼에 `_수집스탬프`·`_중단` 특수시트 제외 추가.)
- **input_list(S2)**: `validate_input_list` 시트명 충돌 fatal → `[SYNC]` 다계정ID 병합 warning.
- **gsheet_index(S3)**: `roster_from_workbook` 계정ID=`product_account_id`(상품별)·밴드를 계정ID→**사업자명 기준**(`band_by_biz`, 다계정ID=한 밴드). plan_sync/sync_index 는 account_id 를 이미 1급 키로 다뤄 호환(밴드값=사업자 밴드).
- **workbook 엑셀(S4)**: `_index_row` D열=`product_account_id`(상품별)·엑셀·구글 패리티.
- **일원화 다계정 인지(S5)**: `_consolidate_renamed_accounts`가 시트의 대장-존재 계정ID들이 **모두 한 사업자명 동의 시만** merge_account, **발산하면 자동 병합 보류+`[SYNC]` 경고**(수동 확인). 옛 이름 잔재=(옛사업자명, 각 계정ID) 전부 반환. 단일 rename(이종훈→원더폴리)은 기존과 동일(회귀).

**핀(감시)**: verify_offline[17](한 시트·집합 누적·상품별 계정ID·계정 스탬프 둘째 계정 버그·왕복·삭제·엑셀 D열)·[18](검증 완화)·[19](일원화 다계정: 단일 rename·무변경·발산 보류). verify_gsheet_offline[6b](상품별 계정ID·다계정=한 밴드·다른 사업자=다른 밴드·안정키).

**한계**: 발산(한 시트 두 계정이 서로 다른 사업자명)=자동 분리 안 함(경고만·수동). 미수집 다계정ID 사업자는 계정목록에 첫 계정ID 1행(수집 후 상품별 태깅 정상).

관련: [[handoff-9items-spec-260925]] [[feature-account-consolidation]] [[gsheet-unified-spec]] [[seldoc-output-format]] [[code-health-regression-gate]].
