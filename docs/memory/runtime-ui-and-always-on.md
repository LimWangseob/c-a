---
name: runtime-ui-and-always-on
description: "실제 실행 UI=app_qt.py(app.py 아님), 24/365 상시가동 전제, 설정탭은 파일/API키만"
metadata: 
  node_type: memory
  type: project
  originSessionId: 4c9cd574-1676-4798-ba82-659441c10186
  modified: 2026-09-22T20:23:33.542Z
---

**실제 실행 UI = `ui/app_qt.py`(PySide6)**. 탭 4개(설정·키워드 추천·순위 조회·전체 실행) + 하단 로그 패널. 실행 로그 미러 `output/run_log_*.log`는 app_qt 만 생성(app.py엔 없음)이라 사용자는 app_qt 를 쓴다. **Tkinter `ui/app.py`(폴백)도 `80b062e`에서 app_qt 와 동작 일치**(설정탭 정리·당일=D-1·로그 상한). app.py는 `--auto` 무인모드·로그파일 미러 없음(콘솔만), gsheet는 `output_url`만 winreg로 공유.

**전체실행 UX(app_qt)**: 전체실행 탭에서 **실행 모드 3택** + **수집 기간(당일=어제/기간)** 선택 후 실행. ⚠ 실제 위젯은 `QRadioButton`이 아니라 **배타 `QButtonGroup`에 묶인 `QCheckBox`**(모드=`cb_resume`/`cb_redo`/`cb_newall`, 기간=`cb_today`/`cb_range`) — 시각은 체크박스, 동작은 라디오. `cb_grow`=새 키워드 발굴 추가. 진짜 QRadioButton은 설정탭 입력소스 쌍뿐(app.py Tkinter는 진짜 Radiobutton, `run_mode`=resume/redo/newall).
- **실행 모드 3택(2026-09-14 소유자 재정의)**: ①**이어서 하기**(기본·`resume`): 오늘 하다 만 것 이어서(완료계정 건너뜀)·없으면 오늘 컬럼 추가. ②**오늘 처음(다시) 하기**(`redo_today`): 어제까지·키워드 동결 **유지**하되 **오늘 컬럼·완료스탬프 초기화** 후 전 계정 오늘분 재수집. ③**전체 새로 시작**(carry_forward=False): 마스터 백업 후 빈 통계(시계열 끊김·확인창 경고). ⚠ 옛 "처음부터(새 통계)"가 ②로 오해되던 걸 분리. 구현=`run_full(redo_today=)`·`workbook.reset_date_column(라벨)`/`clear_sales_stamps`.

**⚠️ 설정 탭 = 파일·API 키 + 구글시트 카드만(순위 세부값 입력 UI 없음 — 2026-09-14 재확정)**: 카드1 "파일·API 키"(입력 엑셀·네이버 키·OpenAI 키), 카드2 "구글 시트 연동"(SA키·입력링크·**입력소스 라디오**=구글시트(기본)/PC엑셀·출력링크). **순위 간격/쿨다운을 실행 중 조정하는 입력란은 없다.** 이력: `740abda`가 옛 세부값 입력 UI를 제거 → `75f804d`가 순위 간격/쿨다운 입력란을 잠시 **재도입** → **이후 사용자가 다시 삭제**(2026-09-14 실측: app_qt에 RANK_NAV_DELAY/COOLDOWN 관련 위젯 0, `app_qt.py:251` 주석이 제거 명시). **∴ 모든 순위/키워드 세부값 조정은 오직 `config.py` 에서** 한다(RANK_NAV_DELAY_MIN/MAX_SEC 등). ⛔ "설정탭에서 실행 중 간격 조정 가능"이라고 안내하지 말 것(그 기능 없음).

**무인 야간 운용(2026-09-12 `50e6673`, 요구=퇴근후 18:00~익일 06:00 사람개입 0)**: app_qt `--auto` 모드. Windows **작업 스케줄러**(`deploy/install_schedule.ps1`→매일 18:00 `--auto` 실행·WakeToRun). **⚠종료 정책(소유자 2026-09-23 개정): 06:00 강제 종료 폐지 — 어떤 경우에도 강제 종료 금지, ①②③+재고역기록 모든 처리를 완주한 뒤에만 `_auto_done`으로 종료**. 옛 `_schedule_auto_stop`/`_auto_stop`(06:00에 순위 중간 중단+60초 뒤 강제종료)은 삭제(미처리분 발생). 순위·로그인 자체 서킷브레이커(쿨다운 MAX·연속차단)로 스스로 끝나 무한대기 없음. 무인 시퀀스(**2026-09-15 반자동 조합으로 개정** — 전체실행과 동일·offscreen 전무): `run_full(keywords_off=True, sales_semi=True, skip_ranks=True)`(①**반자동** 판매수집만·보이는 신뢰 창 자동입력 로그인=Akamai 통과율↑)→**[차단 등 미완료 남으면 30분 쿨다운 후 남은 계정만 sales_semi=True·resume=True 1회 재개(`LOGIN_NIGHT_RESUME`·`=1800`, 밤 1회만·루프 없음=위탁계정 잠금방지)]**→`select_keywords_stage()`(②키워드선정·노출측정 없음·부족분 4개까지 보충)→`track_ranks_stage(semi=True)`(③반자동 autosubmit). **무인이어도 처리방식은 전부 반자동**(옛 offscreen 자동로그인 폐기). 2차인증은 사무실=신뢰 IP면 없이 통과, 낯선 환경서 뜨면 사람없어 그 계정 건너뜀. 스케줄러 설치=`deploy/install_schedule.ps1`(매일 18:00 `--auto`·WakeToRun·**완주 후 종료·강제종료 없음**). 팝업 0(로그로만), 입력 엑셀 마지막 경로 QSettings(`file/input`) 자동로드, 로그인 차단/2차인증 계정은 건너뜀(안 멈춤), 실행 중 `SetThreadExecutionState`로 절전 방지. ⚠️전제: 18:00에 PC 켜짐/절전(완전off 불가), 첫 1회 수동으로 입력·키 세팅. ⚠️한계: Akamai 로그인차단·순위차단은 무인으로 못 뚫음(지문위조 금지)→차단분 공란·다음날 이월(완전수집 보장 아님). 검토 시 확인된 무인 블로커 4개(스케줄러 없음·전체실행 확인팝업·입력 미자동로드·전체실행 내부 ③=자동순위)를 이 커밋이 닫음. 관련 [[login-block-session-first-circuit-breaker]] [[semi-auto-rank-and-exposed-name]] [[exe-packaging-deploy]].

**24/365 상시가동 전제**: 앱을 끄지 않고 계속 켜둔다(수동 실행, 스케줄러·자동루프 없음). `740abda`에서 상시가동 누수 3건 보완 — ①로그 콘솔 `setMaximumBlockCount(config.UI_LOG_MAX_LINES=5000)`(메모리) ②`WingBrowser.__enter__` 실패 시 `__exit__` 직접 호출로 좀비 Chrome 차단(reap 은 시작 때만 돎) ③로그 파일 20MB 회전(`UI_LOG_FILE_MAX_BYTES`). 관련 [[login-policy-real-browser-only]] [[seldoc-output-format]].
