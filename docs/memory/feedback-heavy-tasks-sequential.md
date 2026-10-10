---
name: feedback-heavy-tasks-sequential
description: 무거운 작업(게이트 run_checks·빌드·조사 에이전트·e2e)은 동시에 여러 개 돌리지 말고 하나씩 — 2026-10-10 동시 실행 중 노트북 BSOD
metadata:
  type: feedback
---

게이트(`tools/run_checks.py`)·배포 빌드(build.bat)·조사 에이전트·실제 프로세스 e2e 같은 무거운 작업은 **한 번에 하나씩** 실행한다(병렬 에이전트 여러 개 + 게이트 동시 실행 금지).

**Why:** 2026-10-10 15:18 노트북이 BSOD 0x13A(KERNEL_MODE_HEAP_CORRUPTION)로 재부팅 — 직전에 조사 에이전트 3개 + 게이트가 동시에 돌던 중(30일 내 첫 BSOD). 0x13A 자체는 커널 드라이버/RAM 원인(일반 프로그램이 직접 못 일으킴)이라 원인 드라이버는 미확정(MEMORY.DMP 분석=관리자+WinDbg 필요·미실시)이지만, 소유자가 "하나씩 실행"을 지시.

**How to apply:** 백그라운드 에이전트는 하나 끝난 뒤 다음을 띄우고, 그동안엔 가벼운 읽기(grep·파일 읽기)만. 게이트·빌드는 단독 실행. 재발 시 Intel Arc 그래픽 드라이버 업데이트·메모리 진단(mdsched)·덤프 분석을 소유자에게 제안. 관련: [[code-health-regression-gate]]
