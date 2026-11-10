---
name: feature-transfer-settlement
description: "미정산 셀독전환자 ①②103계정 정산 — 1단계 로그인 확인(D-111·D-112) · 2단계 정산 자료 받기 매일 18시 뒤 구현(D-187 R121) · 현행·상세 = 문서"
metadata:
  type: project
---

미정산 계약자 중 셀독 전환자(①52·②51)의 쿠팡 정산금을 미정산 원금에서 공제하려는 기능. 위치 안내만(정책 본문은 문서):
- 현행 규칙 = `docs/CURRENT_RULES.md` '그 밖 주제' 셀독전환자 줄 · 원문 = D-111·D-112·D-179②·D-187 · 설계 = `designs/SETTLEMENT_MODULE.md` §15.
- 코드 = `transfer_accounts.py`·`transfer_login.py`(1단계)·`transfer_settle.py`(2단계) · 시험 = `tools/verify_transfer_offline.py`·`tools/verify_transfer_settle_offline.py`.
- 결과 = `output/정산_셀독전환/`(로그인확인_*.xlsx · 정산/ · 셀독전환_정산내역_누적.xlsx). 미정산 원장 반영은 앱 밖.
- 남은 일 = STATE '다음 작업'(돌릴 PC 결정·로그인확인_최신.json 복사·새 zip).

**Why:** 2단계 빈도 충돌(주1회 vs 매일)은 D-179②로 '매일 18시 뒤' 확정·R121 구현 — 옛 '미결정' 메모가 남아 있으면 잘못 재질문하게 됨. **How to apply:** 이 기능 작업 전 위 문서부터 읽는다. [[settlement-batch-download-decisions]] [[feedback-control-session-only]]
