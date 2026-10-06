---
name: policy-per-domain-sessions
description: 정책(고정) — 도메인별 작업은 각자 전용 세션(worktree 레인)에 할당해 진행. 한 세션에 여러 도메인 몰지 말 것
metadata:
  node_type: memory
  type: feedback
  originSessionId: c48bfd01-5750-43b7-bf3c-9d574e709d12
  modified: 2026-10-06T00:08:39.275Z
---

**정책(소유자 2026-10-06 고정): 도메인별 작업은 각 도메인 전용 세션에 할당해 진행한다.** 한 세션이 여러 도메인을 몰아서 구현하지 않는다(이번 세션이 D8+D10+통합셸을 한 번에 한 것을 계기로 고정).

**Why:** 도메인이 섞이면 세션이 비대·판단 흐려짐([[recommend-new-session-when-degraded]])·회귀 추적 어려움. 레인 분리로 비겹침 병합·독립 검증·책임 명확.

**How to apply:**
- 작업 착수 전 **도메인→레인→세션** 배정부터. 레인 소유 파일집합은 `docs/PARALLEL_DEV.md`(E 원장/정산·I 소싱·J 수집·P 어댑터·K CS·D3 등록·D4 변경·F 구글시트·G 워크북·H UI …). 구현 SSOT·순서=`docs/IMPL_PLAN.md`.
- **각 도메인 세션 = 자기 worktree+브랜치**(master 직접 편집 금지·비겹침 레인이라 merge 깨끗). 새 worktree는 `python tools/install_hooks.py` 1회·메모리 자동주입 안 되니 `IMPL_PLAN`·`DOMAIN_*`·`PARALLEL_DEV` 읽기가 출발점.
- **통제(통합) 세션**이 공유 파일(`config.py`·`pipeline.py`·`browser.py`·`collector.py`·`credstore.py`·`CLAUDE.md`·`designs/`·`DECISIONS`·`run_checks.py`·L1 핀)과 **master 병합을 직렬**로 담당. 레인은 공유 값 필요 시 통제에 요청(직접 편집 금지).
- **런타임(라이브)은 병렬 금지**(단일 위탁 세션·Akamai·단일 마스터/시트) — 코드 편집만 병렬. 라이브 테스트는 한 번에 한 세션·사무실.
- 메커니즘: 통제 세션이 준비된(오프라인·비겹침) 도메인을 **Agent(worktree 격리)로 배정**→레인에서 구현·게이트 초록·커밋→**통제가 리뷰 후 직렬 병합**. 공유 자원 접점(P 어댑터·J 수집)은 통제 동반.
- 착수 가능 판정: 선행 미결(§IMPL_PLAN 3) 없는 **오프라인·읽기** 도메인부터. 쓰기·라이브는 Wave2(선행 해소 후).
- 기존 앱 무중단은 그대로([[keep-existing-app-running-until-integrated]]) — 레인도 greenfield·휴면·공유 L0/L1 행동 불변.

[[recommend-new-session-when-degraded]] · [[keep-existing-app-running-until-integrated]] · [[handoff-architecture-parallel-260928]]
