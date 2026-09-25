---
name: commit-with-design-and-memory
description: 코드 커밋 시 설계서(SSOT)·메모리도 함께 반영 — 누락 방지(사용자 지시)
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 8a4b00cb-6de8-4812-90b5-bc5034ea3f37
  modified: 2026-09-13T10:17:10.191Z
---

코드를 커밋할 때는 **같은 흐름에서 설계서와 메모리도 함께 갱신**한다. 코드만 커밋하고 문서/메모리를 미루지 않는다.

- **설계서**: `designs/DESIGN.md`(정책·구조 SSOT), 관련 시 `designs/KEYWORD_SELECTION.md`·`designs/GSHEET_UNIFIED.md`. 로직/정책이 바뀌면 해당 절 + §0 최신요약에 반영.
- **인계**: `HANDOFF.md §0`(최신 세션) — 무엇을 왜 바꿨는지·다음 할 일.
- **메모리**: 새 사실/함정/핸드오프는 `memory/*.md` + `MEMORY.md` 인덱스 한 줄.

**Why:** 코드·설계서·메모리가 어긋나면 다음 세션이 오판하거나 누락한다. 사용자가 반복 강조한 원칙(SSOT 일관성).
**How to apply:** 커밋 단위로 "코드 → 설계서/HANDOFF → 메모리"를 한 세트로 처리. 문서 갱신은 코드와 같은 커밋 또는 바로 뒤 문서 커밋으로. 관련 [[respond-in-korean]] [[fix-from-real-evidence]].
