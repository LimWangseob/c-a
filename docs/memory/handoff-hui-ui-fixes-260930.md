---
name: handoff-hui-ui-fixes-260930
description: H_ui(ui/*) 2026-09-30 화면 수정 10건 커밋·병합 요청 + 실제 App 점검 시 레지스트리 오염 방지 규칙(사고 교훈).
metadata:
  node_type: memory
  type: project
  originSessionId: 8123580e-8010-4a4a-9583-e2f74aaf0de9
  modified: 2026-09-30T00:35:43.671Z
---

**통합 세션의 앱 화면 전수분석 → H_ui 수정 10건 완료(2026-09-30)**. 브랜치 domain/h-ui 커밋 7개 `9eef2e9`~`d63341c`(3d2ee1c 위·병합 요청함).
- 모드/기간 체크박스→라디오 · 탭 고정높이 제거→탭/로그 QSplitter + 설정 탭 작업 결과 로그 유지(탭 이동 시 해제·"첫 실행 전 숨김" 소유자 규칙 유지)
- 설정 탭 '회사 재고·셀독등록원장 설정' 안내+[정산 탭 열기] · 재고현황 링크 미설정 적색 경고(두 곳) · 정산 탭 부제(정산 계산은 준비 중·탭명 '정산' 유지)
- 공휴일 키 `__holiday_kr__`(holiday_source.CRED_KEY)+[연결 확인]·설정 이식에 포함
- 입력·결과 링크 연결 상태 줄(시작 시 뒤에서 check_access·무인 --auto 제외·로그창 안 켬)
- 순위 검색 간격 입력 → `rank/nav_delay_min|max`(정수 문자열·config.json+QSettings). **파이프라인 배선=통합(config.py)** — 미배선이면 화면 값이 적용 안 됨.
- 판매 분석 탭 '최고 순위' 열 — 실데이터에 옛 '50위' 자리표시 잔재가 많이 보임(걸러낼지 미결).

**점검 규칙(사고 교훈)**: 실제 `app_qt.App` 을 오프스크린으로 띄워 점검할 땐 `QtCore.QSettings` 를 "(org,app) 인자면 임시 ini" 하위클래스로 **교체**하고 `app_qt.appconfig` 도 가짜로. `setDefaultFormat/setPath` 만으론 실제 레지스트리를 읽고 씀 → 2026-09-30 가짜 stock/url 이 노트북 레지스트리에 써졌다가(config.json 엔 없었음=원래 미설정 확인) 삭제·복구함.
다음 H_ui 후보: app_qt.py 2009줄(MI C) 탭별 분리(믹스인 방식). 관련=[[handoff-session-260929-continued]]·[[runtime-ui-and-always-on]]

**설정 일원화(2026-10-03·소유자 "흩어진 설정 전부 설정으로")**: 구글시트 링크 4개(관리대장·결과·재고현황·원장)를 설정 탭 '구글 시트 연동' 카드에만 둠(`app_qt._GS_LINKS`·`_gs_edits`) — 9/29 정산 탭 이동을 되돌림(근거=소유자 지시). 정산 탭은 상태줄+[설정에서 변경]+실행 버튼만. 노출순위 프록시 토글(`proxy/enabled`·`proxy/allow_auth`·`rank/block_images`, 새 `ui/proxy_panel_qt.py`)·상세이미지 저장 폴더도 설정 탭으로. 실행 탭의 실행모드·수집기간·키워드발굴은 "그 실행의 선택"이라 실행 탭에 유지. 검사=scratchpad check_settings_hub.py(22건)+게이트10 초록. 미커밋(소유자 확인 대기)·DECISIONS 기록은 통합 세션 요청 필요.
