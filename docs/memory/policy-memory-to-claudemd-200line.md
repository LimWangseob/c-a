---
name: policy-memory-to-claudemd-200line
description: ⛔불변 정책(모든 세션 공통) — 메모리 많으면 CLAUDE.md로 이관·CLAUDE.md 200라인 이하·넘으면 색인+분리
metadata:
  node_type: memory
  type: feedback
  originSessionId: c48bfd01-5750-43b7-bf3c-9d574e709d12
  modified: 2026-10-08T02:48:07.495Z
---

⛔**불변·영구 정책(소유자 2026-10-07·반드시 적용·모든 세션 공통)**. SSOT=전역 `~/.claude/CLAUDE.md` "메모리·CLAUDE.md 관리" 절.

**규칙(2026-10-08 session-kit 반영으로 구체화):**
1. **메모리(MEMORY.md 색인)는 항상 30~50줄.** 50줄 초과분은 **CLAUDE.md로 이관**(또는 색인 통합)해 50줄 이하로 되돌림. 메모리=색인·보조, 상세는 개별 파일(recall).
2. **CLAUDE.md는 항상 200줄 미만.** 넘으면 **색인만 남기고 상세는 별도 파일로 분리**·색인에서 링크/참조(전역·프로젝트 둘 다).
3. **DECISIONS 추가 전용** — 기존 항목 수정·삭제 금지, 뒤집을 땐 새 항목 + 기존에 `SUPERSEDED by …`. 확정 정책만(미승인 제안은 핸드오프/미해결로).
4. **세션 시작**: 핸드오프·DECISIONS 먼저 읽고 git 상태 대조해 3줄 요약 후 착수. **세션 종료**: 확정 정책 반영 + 핸드오프 갱신 + 검증·커밋.

**Why:** 메모리 파일이 많아지면(83개) 한 세션에서 다 못 읽어 맥락 누락. 항상 로드되는 MEMORY.md/CLAUDE.md를 수치 상한으로 lean 유지하고 상세는 recall. session-kit(소유자 업로드)의 세션 핸드오프·DECISIONS 규율을 흡수.

**How to apply:** 매 세션/작업 종료 시 `wc -l`로 MEMORY.md(≤50)·전역/프로젝트 CLAUDE.md(<200) 점검. 초과 시 색인 통합/분리. 되돌림·완화 금지(불변). ⛔session-kit의 session-close 스킬은 그대로 설치 안 함(verify가 `ruff/mypy --strict/cycle_audit.py`로 이 프로젝트 게이트 `tools/run_checks.py`와 불일치) — 개념만 흡수.

적용 현황(2026-10-08): 전역 CLAUDE.md 56줄·프로젝트 127줄·MEMORY.md 38줄 — 전부 상한 이하. 관련 [[commit-with-design-and-memory]]·[[code-health-regression-gate]].
