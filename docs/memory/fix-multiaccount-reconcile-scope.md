---
name: fix-multiaccount-reconcile-scope
description: ✅다계정ID reconcile 교차 오염 버그 수정(2026-09-26)+정밀 렌더 검증 신설. 한 사업자 시트에 계정ID 여럿일 때 계정 B 처리가 계정 A 상품 판매중지/삭제하던 버그→reconcile_account(account_id=) 스코핑. tools/verify_render_precision.py 게이트 편입.
metadata:
  node_type: memory
  type: project
  originSessionId: c16f3da3-27f9-41ca-bf1d-0a9ab5b96704
  modified: 2026-09-25T16:00:09.313Z
---

**정밀 렌더 시뮬레이션이 실제 버그 발견·수정(2026-09-26, 소유자 "각 시트·항목·값 정밀 시뮬 검증" 요청).**

**Why:** 항목5(사업자명 그룹핑)로 한 사업자 시트에 여러 계정ID 상품이 섞일 수 있는데, `_process_account` 끝의 `reconcile_account`가 **시트 전체 상품**을 대조해 seen/ledger에 없는 걸 판매중지/완전삭제했다. 다계정ID 사업자(예: 로움컨설팅 loum1[타프]·loum2[매트])에서 **계정 B(매트) 처리 시 계정 A(타프)가 판매중지/삭제**됨. 실운용(파서로 `ledger_products` 채워짐)에선 **완전삭제=데이터 유실**. 정밀 시뮬(타프가 '⛔ 판매중지' 소헤더로 렌더·계정목록서 누락)로 포착.

**How(수정):** `workbook.reconcile_account(..., account_id="")` 스코핑 추가 — `product_account_id(biz,p)`가 그 계정ID(또는 미태깅 '')인 상품만 대조. 다른 계정 소속 상품은 건너뜀. `pipeline._process_account`가 `report_acc.account_id` 전달. `_reconcile_ledger_accounts`의 비활성 경로(account_id='')는 전체 대조 유지(후방호환). 핀 verify_offline[24].

**정밀 렌더 검증 도구(신설·상시 게이트):** `tools/verify_render_precision.py` — run_full 을 목킹으로 end-to-end 실행(다계정ID 한 사업자·다중옵션·마케팅·로켓그로스/개인) 후 렌더 xlsx 를 **셀 단위 29항목** 대조: 제목(대표자·사업자·계정ID)·상품블록(상품명+쿠팡링크·VID·판매방식·로켓그로스)·지표행 값(노출310·판매27·방문88·재고45·판매가19900·판매상태, 항목별 다른 값으로 정확 매핑)·키워드 순위/검색량·다중옵션 분리(대표=키워드/2차=판매정보만)·상품별 계정ID·상품군색(같은 등록명=같은색·다른상품=다른색)·계정목록(열순서 대표자·사업자·계정ID·상품·상태·체험단효과·상품별 계정ID·통계 점프 링크)·gsheet 미러(상품명 쿠팡 외부링크 =HYPERLINK·다계정=한 밴드). `run_checks.py` 7번째 게이트로 편입.

**교훈:** 다계정ID(사업자명 그룹핑) 도입 후 **시트단위 순회 로직은 계정ID 스코핑 필수**(reconcile 외에도 유사 패턴 점검 대상). 정밀 시뮬(렌더 결과 셀단위 대조)이 값 assert만으론 못 잡는 교차 오염을 포착.

관련: [[feature-business-name-grouping]] [[feature-product-coupang-link]] [[handoff-9items-spec-260925]] [[fix-from-real-evidence]] [[code-health-regression-gate]].
