---
name: no-silent-fallback-principle
description: "폴백은 신중히 — 모든 소스코드에서 **최대한 폴백 금지**, 불가피한 경우에만 조건부 허용. 소유자 강조(2026-09-27, 중요)."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 3588291b-3435-4968-8471-8410129d1b69
  modified: 2026-09-27T00:43:58.746Z
---

**소유자 강조(2026-09-27, 중요)**: 모든 소스코드에서 **폴백(fallback)은 신중히 처리**한다. **최대한 폴백 금지**, 불가피한 경우에만 **조건부**로 허용한다.

**Why:** 폴백은 문제(미매칭·데이터 없음·API 실패)를 **가려서** 잘못된/부정확한 결과를 정상처럼 보이게 한다. 예: 상품 링크가 pid 없을 때 `/products/0?vid`(서버오류) 또는 무조건 검색폴백으로 때우면, 근본(=그 상품을 수집해 pid 확보)을 안 고치고 넘어감. 기존 CLAUDE.md "fallback 금지(try/except pass, silent None)"의 확장.

**How to apply:**
- 폴백을 넣기 전에 **근본 해결**을 먼저 시도(데이터를 실제로 확보·정합). 예: 링크 pid 없음 → 검색폴백 대신 **수집으로 pid 확보**(#8) or **실측으로 되는 URL 찾기**.
- 폴백이 불가피하면 **조건을 좁게**(정말 그 경우만)·**로그로 명시**(왜 폴백했는지)·조용한 무시(silent None·try/except pass) 금지.
- "무조건 폴백"(unconditional) 금지 — 항상 조건부.
- 실측으로 "되는 경로"를 찾을 수 있으면 폴백보다 그걸 우선(내장 브라우저 등으로 검증).

관련: [[fix-from-real-evidence]] · CLAUDE.md 제약 "fallback 금지".
