---
name: feature-settlement-status-monitoring
description: 창 없는 정산 자동 다운로드(watch)의 실행 상태를 heartbeat 파일 + app_qt 정산 탭 상태 카드로 모니터링
metadata:
  node_type: memory
  type: project
  originSessionId: c48bfd01-5750-43b7-bf3c-9d574e709d12
  modified: 2026-10-07T04:59:14.137Z
---

정산 자동 다운로드(`tools/settlement_download.py`, console=False·창 없음)를 운용 PC에서 **살아있나·뭘 하나** 확인하는 모니터링(2026-10-07 구현·게이트 초록·미라이브).

- **heartbeat 파일**: `settlement_runlog.RunLog.heartbeat(status, detail)` 가 고정 경로 `output/정산/로그/_현재상태.txt` 에 **덮어쓴다**(append 아님·임시파일→os.replace). 매 호출마다 '갱신' 시각이 바뀌어 **생존 신호**. 비번·구매자명 미기록(내용 300자 컷). watch 는 매 폴링(5분)마다·실행 시작/예외에 기록, `main()` 도 시작/완료에 기록(수동 run 도 모니터링). ⚠'갱신'은 실제 `datetime.now()`(lg.now 아님).
- **앱 상태 화면**: `ui/settlement_status_panel_qt.py` (`SettlementStatusMixin` + 순수 리더 `read_settlement_status(로그폴더)`). app_qt **정산 탭 맨 위** 카드 — 색 배지(작동중 녹/대기중 파/완료 남/오류 빨/없음 회)·마지막 활동(N분 전)·**멈춤 의심**(작동중·대기중인데 STALE_SEC=12분 무변화=빨간 경고, 야간 멈춤 조기 포착)·오늘 집계(정상/건너뜀/대기/실패/차단)·최근 로그 25줄·[새로고침][로그폴더]·5초 자동새로고침. 마지막 활동=상태 갱신시각과 최신 실행_*.log mtime 중 최신.
- **사람용 .bat**: `deploy/정산_상태확인.bat` (더블클릭 → 현재상태+작업등록여부+프로세스+최신 로그 끝 25줄). build.bat 가 dist 로 복사.
- **⚠Qt 지연 import 필수**: 회귀 pytest 게이트는 **PySide6 없는 Python312** 에서 돎 → `settlement_status_panel_qt` 는 `from PySide6` 를 **메서드 안(_settlement_status_card·__main__)에서 지연 import**. 순수 리더는 Qt 없이 import·검증. 모듈 top 에 PySide6 두면 게이트 ModuleNotFoundError(실측 재발방지).
- **spec 등록**: `coupang_analytics.spec` `_ui_hidden` 에 `settlement_status_panel_qt` 추가(함정#9: UI 모듈 누락=런타임 ModuleNotFoundError).
- **게이트 핀**: `verify_settlement_offline.py` P11(heartbeat 덮어쓰기)·P14(heartbeat↔리더 계약·멈춤 의심·오늘 집계). 결정적·오프라인.
- **표시 조건**: 새 빌드 배포 + 새 정산다운로드.exe 1회 실행 후부터 값이 참(그 전=없음/준비 전). 기존 야간 파이프라인 행동 불변(순수 추가·읽기 전용).

관련: [[settlement-batch-download-decisions]] · [[runtime-ui-and-always-on]] · [[exe-packaging-deploy]] · [[code-health-regression-gate]]
