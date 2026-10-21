---
name: feedback-redraw-needs-account-prune
description: 운용 PC 출력 사본 마스터로 통합판매현황을 다시 그려 구글에 올리면 D-093 정리 전 오입력 계정ID(비밀번호 같은 값)가 노출됨 — 2026-10-21 실제 노출
metadata:
  node_type: memory
  type: feedback
  originSessionId: 6be20ba8-d756-4d15-a875-d3f0c3ae7a08
  modified: 2026-10-21T06:01:17.248Z
---

운용 PC 출력 사본(예: Downloads `output (N).zip`)의 통계 마스터로 통합판매현황을 다시 그려 구글에 반영하면, D-093 정리(`prune_account_ids` — pipeline 의 `_reconcile_ledger_accounts` 에서만 실행)를 거치지 않은 오입력 계정ID 가 계정 라벨로 그대로 나간다. 2026-10-21 14:58 유라이프 계정ID 칸의 비밀번호 같은 값이 결과 구글시트 통합판매현황 3칸에 노출(직후 다른 세션 반영본으로 덮임·버전 기록에는 남음).

**Why:** 계정 라벨 = `account_labels(owb)` = 마스터 `_계정정보` 의 계정ID 전부. 사본 마스터는 정리 전 상태일 수 있다.

**How to apply:**
- 사본으로 다시 그리기 전에 대장 계정ID 로 `prune_account_ids` 를 적용하거나, 그린 결과에서 대장에 없는 계정ID 가 라벨에 있는지 **올리기 전에** 검사(값 출력 없이 개수만).
- 결과 구글시트 반영은 한 세션만(동시 반영 금지 — 10-21 두 세션이 같은 분에 반영). 반영 담당을 정하고 다른 세션은 요청만.
- 관련: [[feature-sales-summary-first-sheet]] · [[input-ledger-format]]
