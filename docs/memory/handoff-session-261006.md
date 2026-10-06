---
name: handoff-session-261006
description: 새 세션 진입점(2026-10-06 최신) — 구현 Wave1 통합일. D8흡수원장·D10 CS·D2소싱·통합앱 셸+보라테마·정산(배치다운로드·윙30%) master 통합. 도메인 전용 세션 정책 가동
metadata:
  node_type: memory
  type: project
  originSessionId: c48bfd01-5750-43b7-bf3c-9d574e709d12
  modified: 2026-10-06T06:42:35.030Z
---

**새 세션 진입점 — 현재 상태 SSOT (2026-10-06)**. 통합(통제) 세션 기준. master HEAD=이 문서 반영 커밋(직전 a733473)·게이트 15종+복잡도0 초록.

## 오늘 한 일 (전부 master 병합·greenfield·기존 app_qt 미접촉)
**도메인 전용 세션 정책([[policy-per-domain-sessions]]) 가동** — 통제 세션이 공유파일·master 병합 직렬 담당, 도메인은 worktree 레인/Agent에서 구현→통제 리뷰 후 병합. 오늘 D2 소싱(Agent)·D8 정산(피어 세션)·H_ui 시안(피어)이 병렬로 돌았다.

- **D8 흡수 원장 3종**([[impl-d8-absorb-ledger-261005]]): worklog_store·contract_store·creditor_store(오프라인·기록전용·가림·registry_lock 재사용).
- **D10 CS 수동 트래커**([[impl-d10-cs-tracker-261005]]): cs_model·cs_store·cs_gsheet(문의+이벤트 replay·개인정보 가림·통계·수집0).
- **D2 소싱 1단계**([[impl-d2-sourcing-261006]]): sourcing·sourcing_score(L1만 호출·AI 제외=계층·오프라인).
- **통합 앱 실행 셸**([[impl-integrated-app-shell-261005]]): `python ui/app_integrated.py`(v3.3 사이드바13+신규 도메인 작동 패널·로컬 JSON). **확정 보라 디자인 적용**(`ui/theme_qt.py`·흰 사이드바·보라 강조·[[decision-design-concept-261003]]). 기존 app_qt는 청록 유지·미접촉.
- **정산(D8 피어 세션)**: ①70/30 금액 실측 재확정(윙=전체×70%·RG=줄별70%합·**윙 최종액 30%=월합계−주별70%합** 124,513 확정)·②정산 **파일 배치 다운로드 별도 프로그램** `tools/settlement_download.py`(probe→request→다음날 download→stats·`settlement_wing_api.py`=화면 뒤 WING 정산 주소 직접 호출[로그인 세션 same-origin fetch·collector 패턴·정책 준수]·settlement_runlog)·반자동 로그인/계정별 lock/reap미호출/차단감지/scrub_pii. **✅라이브 검증(wellbing1107 2026-01: 요청 17/17·차단0·같은날 4,967줄·검산경고0)**·파일 생성 대기 약 1분. 다른 계정·기간 규모 확대는 사무실에서. 계약서 정산은 소유자 보류.
- **H_ui 시안**([[handoff-design-mockup-261006]]): 메뉴 v3.3 대13·중84 전화면·IO_DEFINITION 137칸·UI_SCREENS 정합. 시안=claude.ai 아티팩트.

## 게이트/규율
`python tools/run_checks.py`(15종) 초록 필수·`check_complexity`(복잡도/건강) 초록. 커밋마다 pre-commit 훅이 메모리 docs/memory 미러+게이트. 공유파일(config·pipeline·browser·collector·CLAUDE.md·designs·DECISIONS·run_checks·L1핀)·master 병합=통제 직렬. 런타임 병렬 금지.

## 다음(새 세션에서) — 무엇을 어디서
1. **통제 후속(오프라인·지금 가능)**: L1_CONTRACT §9에 밑줄 누수 등재(D2 sourcing 시그니처 핀·정산 pipeline_sales._ensure_login·account_profile·collector._fresh_download_dir/_wait_new_xlsx 공개화 판단). pin_l1_contract에 D8/D10/D2 퍼사드 시그니처 핀.
2. **준비된 도메인 배정(오프라인)**: 남은 Wave1 오프라인은 대부분 소진. P 어댑터·J 수집 골격은 통제 동반. H_ui 화면 승격(기존 7탭)·theme 세부(기간알약·비교배지·알약막대).
3. **소유자 결정 대기**: 정산 ②지급일 불일치 2건(캘린더·화면값 정본·§3 재확정은 실데이터 후)·③계약금액 출처(소유자 or 계약원장).
4. **사무실 라이브**: ✅정산 다운로드=라이브 됨(wellbing1107 1계정 검증·WING 정산 same-origin fetch로 U3 해소)→남은 건 **다른 계정·기간 규모 확대**(야간/사무실). 쓰기 도메인(D3 등록·D4 변경)은 **쿠팡 쓰기 엔드포인트 라이브 캡처** 선행 후 배정.
5. ⚠운용 PC 설정 URL 4개 교정(설정 탭 저장)은 사람 조치(옛 핸드오프 미해결·[[handoff-session-261004]]).

새 worktree 세션은 `IMPL_PLAN`·`DOMAIN_*`·`PARALLEL_DEV` 읽기가 출발점(메모리 자동주입 안 됨)·`install_hooks` 1회.

[[policy-per-domain-sessions]] · [[keep-existing-app-running-until-integrated]] · [[domain-design-elaboration-261005]] · [[handoff-design-mockup-261006]]
