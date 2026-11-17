---
name: feedback-heavy-tasks-sequential
description: 무거운 실행(게이트·python 대조·하위 세션) 동시 실행 허용 — 현행 = D-310(2026-11-18) · 옛 '하나씩'(10-10 BSOD) 폐기
metadata:
  type: feedback
---

현행 = `docs/DECISIONS.md` D-310 (소유자 2026-11-18 원문 "무거운 실행은 하나씩 규칙 함께 ==> 이제는 동시에 해도 돼.").

**Why:** 2026-10-10 BSOD(0x13A) 뒤 '하나씩'이었으나 소유자가 11-18 철회. 원인 드라이버는 미확정 — 재발하면 다시 판단(Intel Arc 드라이버·mdsched·덤프 분석 제안).

**How to apply:** 게이트·대조 python·하위 세션 동시 실행 가능. 런타임 병렬화 금지(브라우저·위탁계정 로그인 한 번에 하나)와 배포 빌드 통제 세션만(D-201)은 그대로. 관련: [[code-health-regression-gate]]
