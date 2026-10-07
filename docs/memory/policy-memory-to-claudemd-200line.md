---
name: policy-memory-to-claudemd-200line
description: ⛔불변 정책(모든 세션 공통) — 메모리 많으면 CLAUDE.md로 이관·CLAUDE.md 200라인 이하·넘으면 색인+분리
metadata:
  node_type: memory
  type: feedback
  originSessionId: c48bfd01-5750-43b7-bf3c-9d574e709d12
  modified: 2026-10-07T13:24:50.086Z
---

⛔**불변·영구 정책(소유자 2026-10-07·반드시 적용·모든 세션 공통)**. SSOT=전역 `~/.claude/CLAUDE.md` "메모리·CLAUDE.md 관리" 절.

**규칙:**
1. 메모리가 많아 한 세션에서 **전부 읽기 어려우면**, 핵심 내용을 **CLAUDE.md로 이관(통합)** — 메모리는 색인·보조로.
2. **CLAUDE.md는 200라인 이하 유지.** 넘으면 **색인(목차)만 남기고 상세는 별도 파일로 분리**·색인에서 링크(전역·프로젝트 둘 다).

**Why:** 메모리 파일이 많아지면(현재 81개) 한 세션에서 다 못 읽어 맥락 누락. 항상 로드되는 CLAUDE.md에 핵심을 두되 비대해지지 않게 200라인 상한+색인으로 관리.

**How to apply:** 매 세션/작업 종료 시 전역·프로젝트 CLAUDE.md 줄 수 점검(`wc -l`). 200 초과면 색인화+분리. 메모리 비대 시 핵심을 CLAUDE.md로 승격. 되돌리거나 완화 금지(불변).

적용 현황(2026-10-07): 전역 48줄·프로젝트 123줄·MEMORY.md 58줄 — 모두 200 이하(분리 불요). 메모리 81개는 비대 신호 → `consolidate-memory`로 주기 정리. 관련 [[commit-with-design-and-memory]]·[[code-health-regression-gate]].
