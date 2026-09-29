---
name: handoff-hui-ledger-stage2-ui-260929
description: 정산(셀독등록원장) 2단계 UI(2-1·2-3·2-4) 구현·master 병합 완료(2026-09-29·H_ui). 남은 것=사무실 라이브.
metadata:
  node_type: memory
  type: project
  originSessionId: ca66c120-700c-4053-a270-0aad80debf5e
  modified: 2026-09-29T00:33:38.177Z
---

**정산 2단계 UI 전부 구현·master 병합 완료(2026-09-29·H_ui 레인·통합 병합).** 편집=`ui/` 만. master HEAD=`c5d5036`(origin push·게이트 9종 초록). 남은 것=**사무실 라이브**(원장 실제 쓰기·이전 비번 1회 로그인)뿐.

## 커밋
- `c385b8c` — 2-1 원장 카드·[미리보기]/[반영]·실행 시작 3곳 run_sync 트리거 + `run_full(registry_url=)` · 2-4 입력소스 '원장' · 2-3 불일치 목록.
- `5a1b827` — 2-3 [이전 비밀번호로 1회 시도] 버튼 연결 + 원장 로드 실패 로그 문구 명확화.
- DECISIONS 2줄(`49c86ff` 2-4 폴백 · `15fd143` 2-3 흐름·로그 문구, 통합이 기록).

## 새 파일(둘 다 MI A·app_qt 비대 방지)
- `ui/registry_ui.py` — Qt 없는 도우미(로직).
- `ui/registry_panel_qt.py` — 설정 탭 '셀독등록원장' 카드 믹스인(화면).

## 동작
- **2-1**: 설정 탭 원장 링크(`registry/url`·config.json 공유·설치 이식). [원장 미리보기]=dry_run · [원장 반영]=확인창 후 `run_sync`. 실행 시작(`_full_pipeline_task`·`start_auto`·`start_resume`)의 `backup_sources` 직후 자동 반영 1회(원장+대장 링크 둘 다 있을 때·비치명)+`run_full(registry_url=)`(무인 쿨다운 재개의 두 번째 run_full 포함). ②만·③만 버튼·②③ 단계 제외.
- **2-4**: 입력소스 라디오 '원장(관리중만)'(`input/source='registry'`). 자동 로드 실패 시 `== [입력] 원장 로드 실패 → 관리대장으로 전환: 이유 ==` 로그 후 구글 관리대장 폴백(선택한 입력소스는 원장 유지·소유자 승인). 반영 성공 시 원장으로 입력 재구성.
- **2-3**: 비번불일치 목록에서 계정 선택 시 [이전 비밀번호로 1회 시도] 활성 → `previous_password`(없으면 안내 후 중단) → 확인창 → `pipeline.try_login_once` 1회(배타·재시도 없음·비번 로그 없음) → 성공 시 `write_coupang_check({aid:('확인됨',오늘)})` + "쿠팡은 아직 이전 비밀번호(대장만 변경됨)" 안내, 실패 시 중단.
- `app.py`(예비 Tkinter UI)는 반영+`registry_url` 전달만.

## 검증
게이트 9종+복잡도 초록 · import OK · 오프라인 점검 19건(가짜 로그인·가짜 원장·임시 설정, 실제 설정·API 미접촉).

## 남음
- ⏳ **사무실 라이브**: 원장 실제 쓰기(쿠팡확인 실채움)·이전 비번 1회 로그인 확인.
- 오프라인 점검 스크립트는 세션 임시폴더라 소멸 — 다시 만들 땐 `registry_panel_qt.QtCore` 를 IniFormat 임시 QSettings 로 바꿔치기(실제 앱 설정 미접촉)·폴백 시 `_apply_input_gsheet(persist=False)` 가 입력소스(원장) 유지하는지 확인.
- H_ui 다음 후보: `ui/app_qt.py`(약 1690줄·MI C) 탭별 모듈 분리(행동 불변·이번 믹스인 방식 재사용).
- 관련=[[handoff-ledger-stage2-260928]]·[[feature-ledger-registry]]·[[handoff-session-260929]]·[[no-silent-fallback-principle]].
