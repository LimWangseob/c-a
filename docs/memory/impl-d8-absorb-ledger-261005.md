---
name: impl-d8-absorb-ledger-261005
description: 구현 Wave1 착수 — D8 흡수 원장 3종(업무일지·계약·채권자) 1단계 오프라인 구현(E 레인 worktree·게이트 13종 초록·미병합)
metadata:
  node_type: memory
  type: project
  originSessionId: c48bfd01-5750-43b7-bf3c-9d574e709d12
  modified: 2026-10-05T14:15:55.067Z
---

**구현 Wave1 첫 산출 — D8 흡수 원장 3종 1단계(오프라인·읽기/기록)**. 설계 동결 후 첫 실제 구현(IMPL_PLAN Wave1 추천 1차). E 레인, worktree `d8-ledger-absorb`(브랜치 `worktree-d8-ledger-absorb`), **미병합**(master=e4f6b15). 커밋 3개(f4fc471 worklog → 계약 → 채권자).

## 무엇을
세 greenfield 모듈 + 각 오프라인 게이트. **기존 파일 미수정**(병합 충돌 0)·`registry_lock` 재사용·**config.py 미접촉**(클라이언트·인자 주입식). SSOT=`designs/DOMAIN_D8_SETTLEMENT_PHASE23.md §4`(§10.5에 구현 완료 표기).
- `src/coupang_analytics/worklog_store.py` — 업무일지(IO 11-4). append 전용·replay 없음·상태(진행/완료/보류) 줄 자체·`is_overdue`('7일 넘은 진행' 렌더 계산)·번호 연속. `append()`.
- `src/coupang_analytics/contract_store.py` — 계약(IO 11-3). 계약=(위탁계정, 사업) 버전 이력(최초/개정/해지)·`as_of`(효력일≤기준일 최신 내용·registry 패턴)·`status`(유효/만료/해지 replay)·`expiring_soon`(30일 전)·`view(role)` 민감 가림(정산계좌·수탁자군=대표/정산담당). `record()`. 수수료·약정이익금은 셀독등록원장 아닌 여기(원장 책임 분리).
- `src/coupang_analytics/creditor_store.py` — 채권자(IO 12-x). **기록 전용**(배분 계산=R1 법률 보류로 미구현). 돈 원장 append·정정=반대기록(음수)·`balance`/`balances` replay(확정−상환)·2단계 가림(`mask_master`: 이름·연락처=대표/정산담당·**상환계좌=대표만**)·`record_access` 열람 로그(감사·항목명만·원문 없음)·별도 스프레드시트 4시트(채권자·채권상환·응대기록·열람기록)·**로컬 백업 안 만듦**(원문 유출 방지·§4.3).
- 게이트: `tools/verify_{worklog,contract,creditor}_offline.py` 신규(FakeClient·실 API 0)·`tools/run_checks.py` CHECKS에 3줄 등록(append-only, 10→13종).

## 검증
게이트 **13종 전부 초록**(full)·`check_complexity` 초록(신규 3파일 A/B·괴물함수 0). 각 모듈 쓰기=`registry_lock`(전용 lock 파일)·dry_run=쓰기 0·번호 1..n 무결성=다음 쓰기 차단·검증 실패=쓰기 0·로그에 원문 없음.

## 남은 것(통합 세션/선행 미결)
- **병합**: worktree 브랜치 → master 직렬 병합(게이트 재실행). run_checks.py·DECISIONS·designs/는 append-only라 충돌 적음.
- **UI 배선(H_ui)**: 11-3 계약·11-4 업무일지·12-x 채권자 화면. 모듈은 데이터·계산만 제공(직접 import 금지).
- **config 설정키**(§8·통합): `contract/url`·`creditor/url`(별도 파일)·`worklog`는 운영대장 탭. 현재 모듈은 client+url 인자식이라 미설정도 동작.
- **L1/핀**(통합): 퍼사드 pipeline/ui 노출 시 `pin_l1_contract` 등재.
- **2·3단계**: 계약 수익식 스키마 확정 후 `settlement.py` 달성률+`contract_achievement[]` 골든 · 채권자 배분 규칙(법률→소유자) 확정 후 `creditor_settlement`.

[[handoff-session-261005]] · [[feature-ledger-registry]](재사용 원천 registry 패턴) · [[business-context-consignment-creditors]](채권자 법률·가림) · [[io-definition-spec]] · [[no-silent-fallback-principle]]
