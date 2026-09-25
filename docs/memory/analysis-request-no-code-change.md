---
name: analysis-request-no-code-change
description: "피드백 — 사용자가 \"분석해줘\"라고 하면 분석만. 코드/파일 수정 금지(요청 전까지). 수정과 분석을 명확히 구분."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d8fb41f6-bdf5-4fe4-8e5b-ec34a7da65a4
  modified: 2026-09-19T12:53:09.615Z
---

사용자가 **분석을 요구하면 분석만** 한다. 코드·파일 수정으로 넘어가지 말 것(명시적 수정 요청 전까지).

**Why:** 2026-09-19 사용자가 재고/판매/VID 로직 분석을 요청했는데, 내가 "로그 남겨줘"를 수정 요청으로 오해해 `_fill_product_metrics` 수정에 착수함 → 사용자가 "분석을 요구했어, 수정을 요구한 것이 아님. 요구사항을 명확히 수행해줘"라고 정정.

**How to apply:**
- "분석해줘/설명해줘/알려줘/왜/어떻게" = 읽기·설명만. 파일 편집·커밋 금지.
- "로그 남겨줘/추가해줘/고쳐줘/반영해줘/구현해줘" 같은 명시적 동사가 있어도, 같은 메시지가 전체적으로 "요구사항 분석"이면 **먼저 분석으로 처리하고 구현 여부를 확인**한다.
- 요구사항(원함)·현재 코드 사실·미확정(캡처/확인 필요)을 분리해 제시. 추정 금지([[fix-from-real-evidence]]).
- 큰 아키텍처 변경(예: VID 출처 변경)은 반드시 분석·승인 후 착수.

관련 [[fix-from-real-evidence]] [[recommend-new-session-when-degraded]]
