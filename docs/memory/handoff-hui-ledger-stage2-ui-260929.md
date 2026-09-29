---
name: handoff-hui-ledger-stage2-ui-260929
description: H_ui 레인 인계(2026-09-29) — 셀독등록원장 2단계 UI(2-1·2-3·2-4) 구현·master 병합 완료. 남은 것=사무실 라이브 확인뿐. 새 H_ui 세션 착수점.
metadata:
  node_type: memory
  type: project
  originSessionId: 8123580e-8010-4a4a-9583-e2f74aaf0de9
  modified: 2026-09-29T00:26:14.640Z
---

**H_ui 레인(ui/*, worktree D:\ca-worktree\H_ui, 브랜치 domain/h-ui)이 원장 2단계 화면 연결을 끝냈다. 전부 master 병합·푸시 완료(통합 세션, master=15fd143).**
커밋: c385b8c(2-1·2-4·2-3 목록) · 5a1b827(2-3 버튼·폴백 로그 문구). 결정 기록=DECISIONS 2026-09-29 (정산 2-4·H_ui)·(정산 2-3·H_ui) 두 줄(통합이 기록).

## 구조(어디 있나)
- `ui/registry_ui.py` — Qt 없는 도우미(app_qt·app 공용·MI A): load·sync·presync(비치명)·load_input·previous_password·try_previous_password·password_mismatch_accounts. 원장 로직은 registry/registry_gsheet/pipeline.try_login_once **호출만**.
- `ui/registry_panel_qt.py` — `RegistryPanelMixin`(App 이 상속·MI A): 설정 탭 '셀독등록원장' 카드·버튼 핸들러·`_apply_input_registry`·`_registry_presync`. app_qt 비대화 억제용 분리.
- `ui/app_qt.py` 연결: 입력소스 라디오 3개(gsheet/file/registry)·`_auto_load_input` 원장 분기·실행 3곳(do_run_full·start_auto·start_resume) backup_sources 직후 `_registry_presync` + `run_full(registry_url=)`·`registry/url` 을 `_CONFIG_SHARED_KEYS`·`_EXPORT_QKEYS` 에 추가.
- `ui/app.py`(Tk 예비): presync + registry_url 전달만(2-3/2-4 화면 없음·통합 승인).

## 확정 동작
- 2-1: [원장 미리보기]=dry_run(쓰기 없음) · [원장 반영]=확인창 후 실행. 실행 시작 자동 반영은 원장 링크+대장 링크 둘 다 있을 때만·실패해도 로그 후 진행. 반영 실패해도 registry_url 은 run_full 에 넘김(쿠팡확인 기록은 별개). ②만·③만 버튼·②③ 단계엔 없음(인자 없음·쿠팡확인 안 씀).
- 2-4: 입력소스=원장이면 관리중만 로드+비번 DPAPI 저장. 실행 시작 반영 성공 시 원장으로 입력 재구성(작업 스레드·화면 위젯 미접촉). **실패 시 "== [입력] 원장 로드 실패 → 관리대장으로 전환: 이유 ==" 로그 후 구글 관리대장**(소유자 승인 폴백), 이때 `_apply_input_gsheet(persist=False)` 로 **선택한 입력소스(원장)는 유지**.
- 2-3(A안): 불일치 목록에서 계정 선택 시 버튼 활성 → previous_password(없으면 안내·중단) → 확인창 → `pipeline.try_login_once` 1회(배타 실행·재시도 없음·비번 로그 없음) → 성공 시 `write_coupang_check({aid:('확인됨',오늘)})`(그 계정 모든 줄)+"쿠팡은 아직 이전 비밀번호(대장만 변경됨)" 안내·목록 새로고침 / 실패 시 중단.

## 검증·남은 것
- 게이트 9종+check_complexity 초록·import OK·오프라인 점검 19건(가짜 로그인·가짜 원장·**임시 ini 설정** — 실제 QSettings 미접촉. 스크립트는 세션 scratchpad라 소멸, 필요하면 재작성: registry_panel_qt.QtCore 를 IniFormat QSettings 로 바꿔치기).
- ⚠ **남은 것 = 사무실 라이브만**: 원장 링크 등록 → [원장 미리보기]/[원장 반영] → ①판매수집 후 쿠팡확인 채움 확인 → 비번불일치 계정 있으면 [이전 비밀번호로 1회 시도].
- 설계서 `designs/LEDGER_REGISTRY.md §10-1` 에 H_ui 완료 표기+낡은 줄번호(app_qt 1130·1202…) 정리는 **공유 파일이라 통합 세션에 요청함**(2026-09-29) — 반영됐는지 새 세션에서 확인.
- H_ui 다음 후보: app_qt.py(약 1690줄·MI C) 탭별 모듈 분리(행동 불변·믹스인 방식이 이번에 검증됨).

관련=[[handoff-ledger-stage2-260928]]·[[feature-ledger-registry]]·[[no-silent-fallback-principle]]·[[login-policy-real-browser-only]]
