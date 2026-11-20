---
name: feedback-heavy-tasks-sequential
description: 무거운 실행(python 대조·하위 세션) 동시 허용 = D-310 · 단 회귀 게이트만 PC 전체 1개 = D-377(2026-11-20)
metadata:
  type: feedback
---

현행 = `docs/DECISIONS.md` D-310 (소유자 2026-11-18 원문 "무거운 실행은 하나씩 규칙 함께 ==> 이제는 동시에 해도 돼.").

**Why:** 2026-10-10 BSOD(0x13A) 뒤 '하나씩'이었으나 소유자가 11-18 철회. 원인 드라이버는 미확정 — 재발하면 다시 판단(Intel Arc 드라이버·mdsched·덤프 분석 제안).

**How to apply:** 대조 python·하위 세션 동시 실행 가능. 회귀 게이트(run_checks)는 PC 전체 1개(잠금 대기·D-377 · 소유자 11-20 'A~C 모두 반영 (권장)' · 근거 노트북 메모리 최저 351MB). 런타임 병렬화 금지(브라우저·위탁계정 로그인 한 번에 하나)와 배포 빌드 통제 세션만(D-201)은 그대로. 관련: [[code-health-regression-gate]]
