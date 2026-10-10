---
name: feature-settlement-status-monitoring
description: 정산 자동 다운로드 = 18:00 앱과 함께 기동·①완료까지 대기·다 받으면/다음 날 17:55 종료(D-021)·앱을 사람이 끄면 함께 종료(D-020)·정산 탭 시작/중지 + heartbeat 상태 카드
metadata:
  node_type: memory
  type: project
  originSessionId: c48bfd01-5750-43b7-bf3c-9d574e709d12
  modified: 2026-10-08T00:47:35.900Z
---

정산 자동 다운로드(`tools/settlement_download.py`, console=False·창 없음)를 운용 PC에서 **앱으로 켜고/끄고·상태를 보는** 기능(2026-10-07 구현·게이트15+복잡도 초록·미라이브).

## ⭐현행 = D-010(2026-10-09 소유자): ①판매수집 뒤 앱이 기동·다 받으면 종료
- 18:00 `--auto` 앱 시작 시 `app_process.prepare_auto_start`: 이전 앱 창·정산 프로그램 종료 + 옛 정산 예약작업(인자 `watch`) 삭제 → reap 이 그 Chrome 정리. 예약작업·`tools/settlement_watch_register.ps1` 폐기(install.ps1 도 등록 안 함).
- ①완료(야간 재시도 포함) 직후 `start_settlement_watch`(창 없음·`CREATE_BREAKAWAY_FROM_JOB` 우선 — 앱이 ③ 뒤 끝나도 정산 생존, 불가 시 경고). `--resume` 도 ①이 끝나 있으면 기동.
- `cmd_watch`: ① 진행 중(_진행중.json 20분 내)엔 대기 → 바퀴 → `settlement_watch.plan_after_pass(stopped, work, pending, waits, idle)`: again(60s)/later(5분)/**done='✅ 모든 정산 파일 다운로드 완료'→종료**/stop(연속실패 중단)·giveup(진전없음 3바퀴)→기록 후 종료. `output/정산/로그/_완료.json`(키=①완료 시각)로 같은 ① 기준 재실행 방지. 배지 '완료'/'종료'.
- HTTP **500=서버 일시 오류**(ServerBusy·15s×2 후 계정 '대기')·윙 주기 **'M'**=그 줄만 건너뛰고 '확인 필요'(novanest1284). ⚠ breakaway 가능 여부·첫 18:00 로그로 확인 필요.

## (대체됨) 24시간 감시 모델(2026-10-07 — D-010 으로 대체)
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

## 2026-10-08 라이브 수정(운용 PC 기록 근거)
- **반출비 받기 실패 16건**(D8): '쿠팡귀책' 두 번째 시트=금액 없는 수량표 → '반출비 청구 제외 수량(B)' 머리글 시트만 제외. 16/16 일치.
- **18:00 전체 중단 근본 해결**(통제): 앱 시작 `reap_orphan_chrome`이 정산 Chrome 을 종료 → `TargetClosedError`를 '차단'·연속 2실패로 세어 전체 중단되던 것 → `_is_browser_closed`로 **일시적(WAIT·재시도)** 처리(bad 미증가·차단 로그 미오염). Chrome 사망 자체는 reap 특성이라 잔존하나 무해화. 핀 P15.
- **watch 상태 2중 기록**(통제): main() 시작 heartbeat 를 watch 엔 건너뜀 → 2번째 watch(잠금 실패 즉시 종료)가 실제 실행 상태 안 덮음.
- **merge --src**(D8): 노트북 자료가 운용 PC `output\정산\정산\`로 들어가 미사용 → `정산다운로드.exe merge --src output\정산\정산` 로 통합(재배포 후 [중지]→merge→[시작]).

관련: [[settlement-batch-download-decisions]] · [[runtime-ui-and-always-on]] · [[exe-packaging-deploy]] · [[code-health-regression-gate]]

**2026-10-10 갱신(D-020·D-021, D-010 SUPERSEDED)**: 회차 18:00~다음 날 17:55(`settlement_watch.cycle_window`). 앱 main(`--auto`/`--resume`)이 시작하면서 `start_settlement_watch`(`watch --parent 앱PID`) → 정산은 이번 회차 ①완료 기록(`_실행단계.json` at≥회차 시작)까지 대기 → 받기 → 다 받으면 종료·17:55 종료. 무인이 스스로 끝나면(`_auto_quit`→`_앱정상종료.json`) 정산 계속, 사람이 닫음/작업관리자 종료면 `watch_parent`가 정산+Chrome 종료. 정산 탭 [정산 시작]도 같은 한 경로. ⚠ install.ps1 예약작업 13h 제한(E3)이 07:00 넘는 실행을 끊으면 정산도 함께 종료 — FEATURE_INVENTORY E3 수정 대기.
