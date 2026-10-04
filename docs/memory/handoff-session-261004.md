---
name: handoff-session-261004
description: 새 세션 진입점(2026-10-04~05) — 안정성 6종+설정일원화 병합·배포본. 설정 URL 저장소 분열=코드보강 완료(_cfg_save_shared st.sync, config.json이 권위)·남은 조치=운용 PC 설정 탭에서 원장/재고 URL 입력+저장
metadata:
  node_type: memory
  type: project
  originSessionId: 4fe6962f-d330-4a48-9bbd-087ab89e7bb2
  modified: 2026-10-04T20:41:09.712Z
---

**새 세션 진입점 — 현재 상태 SSOT (2026-10-04)**

master HEAD=`6d6937d`(origin 동기화·clean). 게이트 10종+복잡도+핀 전부 초록.

## 이 세션에서 한 일 (전부 커밋·푸시 완료)
외부 리뷰·라이브 로그 분석을 거쳐 안정성 6종 수정 + H_ui 설정일원화 병합:
1. **반자동 순위 이중 검색요청 제거**(`69e2bb5`): `_submit_search(browser,kw)` Enter 후 URL q 확인→네비 시작됐으면 폼 submit 폴백 생략([[semi-auto-rank-and-exposed-name]]).
2. **백업 401 근본수정**(`f3183b9`): `backup_sources` 결과시트=SA(Sheets API) 값 스냅샷·관리대장=평문비번이라 로컬백업 생략([[gsheet-unified-spec]]).
3. **야간 ~10h 멈춤 근본차단(전원억제)**(`2d27af7`): ③반자동 보이는 창이 야간 디스플레이 꺼짐에 `bring_to_front` 무한대기(22:31→08:25 실측). `power.keep_awake`(SetThreadExecutionState ES_DISPLAY_REQUIRED)를 WingBrowser 수명에 연결. Playwright sync라 to_front 타임아웃 불가→디스플레이 안 꺼지게 해서 조건 제거([[semi-auto-rank-and-exposed-name]]).
4. **링크 중복붙여넣기 방어**(`2d27af7`): `sheet_id_from_url`이 `…/d/https://…/d/<ID>/edit` 중복에서 'https'를 ID로 잡아 404나던 것→finditer로 `://` 뒤 스킴 제외·실제 ID 마지막 채택([[gsheet-unified-spec]]).
5. **전체실행 로그인 대기 300→90초**(`77e1b95`): `LOGIN_ATTENDED_WAIT_SEC=90`. 위탁계정이라 2차인증 불가→OTP는 이미 skip_on_otp 즉시건너뜀·이 값은 사람이 못 푸는 상태 상한. 대기만 줄 뿐 제출 안 늘어 차단無([[login-2fa-location-based]]).
6. **18시 무인 즉시종료 원인규명+메시지**(`77e1b95`): 입력 gsheet URL 옛것→403/404→PC엑셀 폴백(미설정)→종료. do_auto 메시지 명확화.
7. **H_ui 설정일원화 병합**(`274d3b0`·256d932): 구글시트 링크4·프록시 토글(신규 `ui/proxy_panel_qt.py`)·이미지폴더를 **설정 탭에서만**. 정산 탭=상태+실행만. 2026-09-29 '정산탭 링크' 되돌림([[runtime-ui-and-always-on]]).
8. 소유자 결정 기록(`45cd9eb`·`d70ec09`·`fd491e2`·`6d6937d`): 운영DB=구글시트+4규칙·앱범위(주문/배송=샵마인 범위밖)·R2 저장소 확정·앱 디자인 컨셉·설정일원화. 전부 **구현 보류**([[handoff-operation-data-model-261001]] 계열·[[decision-design-concept-261003]]).

## 설정 URL 저장소 분열 — 코드 보강 완료(2026-10-05) + 운용 PC 조치 대기
**증상(10-03 실측)**: 무인 완주했으나 구글시트 반영 전부 실패 — 결과반영 404·회사재고 400·그로스역기록 404. 수집은 PC엑셀 폴백으로 됨.
**메커니즘 규명(이 세션)**: 무인·UI는 URL을 **QSettings**에서 읽음(app_qt:1520·1549·_stock_url·_registry_presync). 시작 시 `_sync_config_and_registry`가 **config.json을 권위로** QSettings에 밀어넣고 `st.sync()`. `appconfig.set`=즉시 `write_text`(동기). → **config.json만 올바르면 매 시작(무인 포함) QSettings 자동 교정**. 분열 원인=QSettings가 config.json보다 지연 + dist 재빌드가 config.json 삭제 시 옛 QSettings로 복원.
**한 일(커밋 예정)**: `_cfg_save_shared`에 **QSettings `st.sync()` 추가**(설정 탭 저장이 즉시 디스크 flush → config.json 지워져도 QSettings 최신 보존). 게이트 10종 초록. ⚠이 노트북=코드작업용, **운용은 별도 PC**라 노트북 config.json 교정은 운용 무관(안 함).
**⭐운용 PC 즉시 조치(사람이 해야 함)**: 설정 탭에서 아래 4개 입력 후 **💾 저장 → 앱 재시작**. 특히 원장·재고가 옛/빈값.
- 입력(관리대장) `1oF93KfPwGrvjOSxNsW2kHSwiRTDsuCSyFmtheobXF1Y`
- 출력(통계) `1BzzlNd7sM3fMEgajsPW5xqxtaVdyhyf8xnWFlpPx7E0`
- 원장(셀독등록원장_자동화용) `1Fb_G1Jz3EmYbu_SnDVPXiMmO7In7vq6d_lfFPriQYq0`
- 재고현황(재고 현황) `1Cdzn4QVfcJIiPwxXyIQ4llRaTpaDmC60KEdRkJN5k4g`
- (SA로 4개 접근 확인됨·SA=`sheet-bot@totalseller-sheets.iam.gserviceaccount.com`)
⚠**dist 빌드폴더에서 직접 운용 금지**(재빌드가 config·output 삭제·함정 #9). 운용=zip을 별도 폴더에 install.ps1로. 설정일원화(256d932) UI 반영하려면 운용 PC에 재배포 필요(현 배포본은 미포함).

## 배포본
`D:\coupang-analytics\dist\쿠팡애널리틱스_배포.zip`(10-03 12:30, 156MB) = **핵심 6종 포함·설정일원화(256d932)는 미포함**(병합이 빌드 뒤). 설정 UI까지 넣으려면 재빌드(앱 닫고). 재배포 시: 보안제외 먼저·proxies.txt 수동·proxy config·전원옵션(디스플레이/절전 안함).

## 게이트/커밋 규칙
커밋 전 `python tools/run_checks.py`(10종) 초록. 새 클론=`install_hooks.py` 1회. 커밋=코드+설계서+메모리+DECISIONS 동시. bash commit -F 파일(멀티라인). 공유파일(CLAUDE.md·DECISIONS·designs)·master 병합=통합 세션 직렬.

[[runtime-ui-and-always-on]] · [[gsheet-unified-spec]] · [[semi-auto-rank-and-exposed-name]] · [[login-2fa-location-based]] · [[exe-packaging-deploy]]
