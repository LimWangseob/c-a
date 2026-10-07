---
name: feature-pipeline-single-run-lock
description: 파이프라인 동시 실행 방지 — run_bg(pipelinelock=True)가 교차 프로세스 잠금(output/_잠금/파이프라인.lock)
metadata:
  node_type: memory
  type: project
  originSessionId: c48bfd01-5750-43b7-bf3c-9d574e709d12
  modified: 2026-10-07T13:48:54.433Z
---

열어둔 GUI와 18:00 무인(--auto)이 **동시에** 파이프라인(계정 로그인·마스터 쓰기)을 돌려 충돌하는 것을 막는 교차 프로세스 잠금(2026-10-07 구현·게이트 초록·⚠라이브 미검증).

- **기존 문제**: `_run_active`는 **한 앱 안**에서만 막는 플래그. 교차 프로세스 가드 없음 → 두 인스턴스(24h 열어둔 모니터링 GUI + 스케줄러 18:00 `--auto`)가 동시에 run_full → 마스터 꼬임·같은 계정 동시 로그인 위험.
- **수정**: `app_qt.run_bg(pipelinelock=True)`가 스레드 시작 전 `registry_lock(output/_잠금/파이프라인.lock, wait_sec=0)` 획득, worker finally에서 해제(프로세스 죽어도 OS 자동 해제). 못 얻으면 "다른 창/무인 실행 중" 로그 + on_done 호출(무인은 정상 종료)·실행 건너뜀.
- **6경로**에 적용: 전체실행(_full_pipeline_task)·판매수집·키워드 stage·순위 stage·무인 `--auto`·재부팅복구 `--resume`.
- **핵심 성질**: **유휴 GUI는 잠금을 안 쥠**(실행 중에만 보유) → 열어둔 모니터링 GUI가 있어도 18:00 무인은 **항상 실행**됨. 둘이 **동시에 돌 때만** 두 번째가 차단. 스테이지(②③)는 잠긴 task 안에서 **직접 호출**이라 재획득 없음(자기 교착 없음).
- **정산과 무관**: 정산 다운로드는 별도 잠금(`_watch.lock`) + `sales_in_progress`로 조율 → 이 파이프라인 잠금과 독립.
- 검증: 앱 로드 OK·동시 획득 거부·해제 후 재획득(offscreen·임시 데이터루트). run_checks 15종·복잡도 0. ⚠**남은 것=라이브**(실제 18:00 GUI 열린 상태 상호작용).

관련: [[runtime-ui-and-always-on]]·[[feature-settlement-status-monitoring]]·[[login-block-session-first-circuit-breaker]]
