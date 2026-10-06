---
name: impl-d10-cs-tracker-261005
description: 구현 Wave1 — D10 문의/CS 수동 트래커 1단계 오프라인 구현(cs_model·cs_store·cs_gsheet·게이트 14종 초록·master 병합됨)
metadata:
  node_type: memory
  type: project
  originSessionId: c48bfd01-5750-43b7-bf3c-9d574e709d12
  modified: 2026-10-05T14:35:41.929Z
---

**구현 Wave1 두 번째 — D10 문의/CS 수동 트래커 1단계(오프라인·수집 0·4-C)**. IMPL_PLAN Wave1 추천 2번째. K 레인, worktree `d10-cs-tracker`(브랜치 `worktree-d10-cs-tracker`). SSOT=`designs/DOMAIN_D10_CS.md`(§9.1 구현 완료 표기).

## 무엇을 (3모듈 greenfield·기존 파일 미수정·registry_lock 재사용·config.py 미접촉)
- `src/coupang_analytics/cs_model.py` — 시트(문의·문의이력·열람기록)·문의유형(상품문의/배송/교환반품/기타)·상태(접수/진행/보류/완료)·이벤트 kind(진행/보류/재개/완료/재개방/응대)·`STATE_MAP`·Inquiry/Event/CSLog 데이터클래스·`validate_inquiry`/`validate_event`(보류=사유 필수)·`mask_inquiry(role)`(고객이름·연락처 가림·`CS_RAW_ROLES`=대표·CS담당 **제안**).
- `src/coupang_analytics/cs_store.py` — 순수 로직: `parse_log`(격자→CSLog)·`status_of`(이벤트 replay·'접수' 기본·응대는 상태 불변)·`open_inquiries`(완료 제외·계정 필터)·`stats`(접수/완료/보류·평균처리일·보류율·계정별)·`check_integrity`(번호 연속·고아 문의ID)·`next_inquiry_id`(Q-0000).
- `src/coupang_analytics/cs_gsheet.py` — 구글시트 IO: `load_log`·`init_sheets`(서식·유형/변동유형 드롭다운)·`open_inquiry`(접수)·`add_event`(이벤트 append)·`record_access`(열람 감사·항목명만·원문 없음)·잠금·dry_run·**로컬 백업 없음**(개인정보 유출 방지·§3.3).
- 게이트 `tools/verify_cs_offline.py` 신규(10시나리오·FakeClient·실 API 0)·`run_checks.py` CHECKS 1줄(13→14종).

## 검증·구현 정정
게이트 **14종 전부 초록**(full)·복잡도/건강 초록. 상태 replay(진행→보류→재개→응대[불변]→완료→재개방)·무결성(번호/고아)·가림·통계·열람 로그·로그에 고객 원문 없음·dry_run 0 전부 검증.
- **정정(IO reconcile 필요)**: 상품·고객이름·연락처=**선택**(D10 §1.1 "상품 비우면 계정 전체" 우선 채택·IO 05-1은 상품 필수로 표기해 상충). 필수=판매처·위탁계정·문의유형·문의내용. '접수'는 이벤트 아닌 문의 존재로 기본 상태.

## 남은 것 (통합/선행)
- **UI(H_ui)**: 05-1 목록·05-2 상세/응대·05-3 접수·05-4 통계(`ui/cs_panel_qt`).
- **config 설정키**: 문의 시트 URL(통합). 현재 client 인자식이라 미설정도 동작.
- **CS_RAW_ROLES 소유자 확정**(Q4 개인정보 권한)·**IO 05-1 상품 필수/선택 reconcile**.
- **2단계 수집**(cs_collect): 샵마인 CS 경계(Q1·U4)·WING 문의 경로(Q2) 확인 후·읽기만. 응대 쓰기(Q3)=보류.

**master 병합됨**(기존 런타임 코드 불변·휴면 코드·기존 앱 무영향·[[keep-existing-app-running-until-integrated]]).

[[handoff-session-261005]] · [[impl-d8-absorb-ledger-261005]](같은 Wave1·registry 패턴 재사용) · [[app-scope-no-orders-shopmine]](CS 범위) · [[io-definition-spec]]
