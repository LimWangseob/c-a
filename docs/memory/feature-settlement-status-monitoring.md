---
name: feature-settlement-status-monitoring
description: 정산 자동 다운로드 = 24h 감시(판매수집 중만 정지)·app_qt 정산 탭 시작/중지 버튼 + heartbeat 상태 카드
metadata:
  node_type: memory
  type: project
  originSessionId: c48bfd01-5750-43b7-bf3c-9d574e709d12
  modified: 2026-10-07T08:10:11.469Z
---

정산 자동 다운로드(`tools/settlement_download.py`, console=False·창 없음)를 운용 PC에서 **앱으로 켜고/끄고·상태를 보는** 기능(2026-10-07 구현·게이트15+복잡도 초록·미라이브).

## 24시간 감시 모델(2026-10-07 소유자 — 옛 "①완료 후 1회·17:40 멈춤" 모델 물리 삭제)
- `settlement_watch.plan_watch(busy, busy_why, sales_at, last_sales_at)` 순수 판정: **①판매수집 진행 중이면 정지, 아니면 실행**. `sales_in_progress(_진행중.json)`=① 지금 도는지(mtime ~20분 내=진행 중·`SALES_STALE_MIN`). `read_marker(_실행단계.json)`=①완료 시각.
- `cmd_watch` 루프: 받을 게 있으면(소급·`_sweep_work_count`>0) 짧게 쉬고(`WATCH_CATCHUP_REST_SEC=60`) **바로 다음 바퀴**(2026-01~오늘 밀린 정산 다 받음). 받을 것 없으면 **다음 ①판매수집 완료까지 대기**(정상 하루 1회·`last_sales_at`). 즉 **소급=연속→소진 후 하루1회 자동 전환**(로그인 줄어 계정 보호). 계정별 `_profile_busy` 건너뜀이 추가 안전장치.
- ⛔삭제: `decide`·`cycle_start`·`STOP_HM`·`FALLBACK`·`load/save_last_cycle`·`WATCH_STATE`(17:40 주기). **전체실행(①②③)은 18:00 1회 그대로**(정산만 24h라 "다음날 앱 방법" 변경 없음).
- **app_qt 정산 탭 [정산 시작]/[정산 중지] 버튼**: 시작=`정산다운로드.exe watch`(frozen)/python(dev) 별도 프로세스(CREATE_NO_WINDOW·lock으로 1개만)·중지=taskkill(frozen 이름·dev PID)+`_settle_write_status`가 _현재상태.txt에 '중지됨' 직접 기록. 계정별 heartbeat('실행 중: 계정명')로 어느 계정인지 표시.

- **heartbeat 파일**: `settlement_runlog.RunLog.heartbeat(status, detail)` 가 고정 경로 `output/정산/로그/_현재상태.txt` 에 **덮어쓴다**(append 아님·임시파일→os.replace). 매 호출마다 '갱신' 시각이 바뀌어 **생존 신호**. 비번·구매자명 미기록(내용 300자 컷). watch 는 매 폴링(5분)마다·실행 시작/예외에 기록, `main()` 도 시작/완료에 기록(수동 run 도 모니터링). ⚠'갱신'은 실제 `datetime.now()`(lg.now 아님).
- **앱 상태 화면**: `ui/settlement_status_panel_qt.py` (`SettlementStatusMixin` + 순수 리더 `read_settlement_status(로그폴더)`). app_qt **정산 탭 맨 위** 카드 — 색 배지(작동중 녹/대기중 파/완료 남/오류 빨/없음 회)·마지막 활동(N분 전)·**멈춤 의심**(작동중·대기중인데 STALE_SEC=12분 무변화=빨간 경고, 야간 멈춤 조기 포착)·오늘 집계(정상/건너뜀/대기/실패/차단)·최근 로그 25줄·[새로고침][로그폴더]·5초 자동새로고침. 마지막 활동=상태 갱신시각과 최신 실행_*.log mtime 중 최신.
- **사람용 .bat**: `deploy/정산_상태확인.bat` (더블클릭 → 현재상태+작업등록여부+프로세스+최신 로그 끝 25줄). build.bat 가 dist 로 복사.
- **⚠Qt 지연 import 필수**: 회귀 pytest 게이트는 **PySide6 없는 Python312** 에서 돎 → `settlement_status_panel_qt` 는 `from PySide6` 를 **메서드 안(_settlement_status_card·__main__)에서 지연 import**. 순수 리더는 Qt 없이 import·검증. 모듈 top 에 PySide6 두면 게이트 ModuleNotFoundError(실측 재발방지).
- **spec 등록**: `coupang_analytics.spec` `_ui_hidden` 에 `settlement_status_panel_qt` 추가(함정#9: UI 모듈 누락=런타임 ModuleNotFoundError).
- **게이트 핀**: `verify_settlement_offline.py` P11(heartbeat 덮어쓰기)·P14(heartbeat↔리더 계약·멈춤 의심·오늘 집계). 결정적·오프라인.
- **표시 조건**: 새 빌드 배포 + 새 정산다운로드.exe 1회 실행 후부터 값이 참(그 전=없음/준비 전). 기존 야간 파이프라인 행동 불변(순수 추가·읽기 전용).

관련: [[settlement-batch-download-decisions]] · [[runtime-ui-and-always-on]] · [[exe-packaging-deploy]] · [[code-health-regression-gate]]
