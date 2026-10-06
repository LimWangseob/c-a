---
name: keep-existing-app-running-until-integrated
description: 통합 앱 완성 전까지 기존 앱(쿠팡 수집·순위·엑셀/구글시트)은 무중단 운영 — 신규 구현은 기존 런타임을 깨지 말 것
metadata:
  node_type: memory
  type: feedback
  originSessionId: c48bfd01-5750-43b7-bf3c-9d574e709d12
  modified: 2026-10-05T14:23:11.829Z
---

통합(멀티플랫폼) 앱이 완성되기 전까지 **기존 앱은 계속 운영**되어야 한다(소유자 2026-10-05). 신규 도메인 구현이 기존 앱의 야간 무인 실행·수집·순위·엑셀/구글시트 산출을 **깨뜨리면 안 된다**.

**Why:** 통합 앱은 미완성이고, 그 사이에도 관리 쿠팡 계정들의 일일 운영(판매수집·순위·통계·재고 역기록)은 멈추면 안 됨. 기존 앱이 현재 유일한 운영 수단.

**How to apply:**
- 신규 도메인 모듈은 **greenfield**(기존 파일 미수정)로 추가 → 기존 런타임과 분리. 배선 전까지는 **휴면 코드**(아무 데서도 import 안 됨)여야 안전. [[impl-d8-absorb-ledger-261005]]가 그 예(src/에서 참조 0·런타임 불변 실측).
- 공유 L0/L1(`browser`·`collector`·`rank`·`registry_*`·`workbook`·`gsheet*`·`pipeline`)은 **행동 불변**이 원칙. 꼭 수정해야 하면 핀/게이트가 기존 동작을 덮는지 먼저 확인(통제 세션). [[code-health-regression-gate]]
- UI/파이프라인 **배선**은 기존 7탭·무인 `--auto`를 보존하며 **추가**로(홈 시안도 "기존 위에 끼워 넣기"·[[feedback-design-extend-not-redo]]). 기존 흐름 교체·전체 재작성 금지.
- Wave 2(쓰기·라이브 수집·배선)가 위험 구간 — 여기서 특히 기존 운영 경로를 건드리지 않게 주의.
- 게이트(`run_checks` 13종)·복잡도는 기존 앱 회귀 방지막. 커밋 전 초록 유지.
