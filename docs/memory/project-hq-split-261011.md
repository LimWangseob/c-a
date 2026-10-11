---
name: project-hq-split-261011
description: 2026-10-11 본부 앱을 별도 저장소 D:\commerce-hq(HQ)로 분리 — 이 저장소(R0)=쿠팡 분석 앱+정산 다운로드 전용 독립 세션
metadata:
  node_type: memory
  type: project
  originSessionId: 8aeb9ec9-4d1e-4c5b-84b2-ae9d5ff75d79
  modified: 2026-10-11T00:49:48.704Z
---

소유자 결정(2026-10-11): 메인 화면(샵마인·쿠팡윙형)·위탁계정·위탁상품·나↔계정 정산·문의/CS·채권자 상환은 **별도 저장소 `D:\commerce-hq`(HQ)** 의 도메인 세션 그룹(D0 홈·통제 · D1~D5)에서 만든다. **이 저장소(R0)는 앱+정산 다운로드만 하는 독립 세션** — HQ 통제 밖. R0 결정 = D-035, HQ 결정 = HQ `docs/DECISIONS.md` D-001~D-004.

**Why:** 한 저장소에서 세션을 나누면 STATE·DECISIONS·공유 파일이 충돌하고 R0(매일 운영) 독립성이 깨짐.

**How to apply:**
- R0 데이터 형식(결과시트·관리대장·원장·재고현황·통계 마스터·`_실행단계.json`·run_log·정산 파일)을 바꾸면 **HQ 에 알리고 양쪽 DECISIONS 기록**(HQ `docs/R0_DATA_CONTRACT.md`).
- HQ 도 쿠팡 직접 접속(소유자 선택) → **PC 공유 잠금**(`%LOCALAPPDATA%\coupang-shared\locks\`)을 HQ 와 같은 규칙으로 R0 에도 구현해야 함(HQ D0 요청 시·HQ `docs/COUPANG_ACCESS.md`). 그 전엔 HQ 쿠팡 접속 금지.
- R0 의 통합앱 자산(셸·테마·계약/업무일지/CS/채권자 모듈·패널·검증 4종)은 HQ D0 이전 완료 알림 후 R0 에서 물리 삭제(STATE 다음 작업 0번).
- 신규 도메인 기능 요청이 R0 세션에 오면 HQ 로 안내(R0 = 앱·정산만).
