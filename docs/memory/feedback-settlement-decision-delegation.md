---
name: feedback-settlement-decision-delegation
description: "정산 산식·판정의 '소유자 결정' 건은 통제 세션이 정산금액 차이 0 기준으로 판단·확정 — 현행 = D-288"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 34675877-7aaf-4408-b123-211cdb04be89
  modified: 2026-11-17T09:17:22.669Z
---

현행 = **D-288** (`D:\coupang-analytics\docs\DECISIONS.md`) · 요약 = `docs/CURRENT_RULES.md` 12절·그 밖 주제.

소유자 원문(2026-11-17): "소유자 결정건은 너가 판단해줘 … 너가 판단해서 정산금액 차이가 zero가 되도록 판단하고 결정해줘. 다른 세션도 동일하게 적용하고 앞으로 발생하는 소유자 판단과 결정은 지금 설명에 근거하여 항상 적용해줘."

**Why:** 소유자 판단이 틀리면 산식이 틀려 정산금액 차이가 생김.
**How to apply:** 범위(위임 안/밖)·판단 기준은 D-288 원문을 읽고 따른다. 하위 세션은 후보만 보고. [[feedback-no-human-approval-queues]] · [[feedback-settlement-1000won-material]]
