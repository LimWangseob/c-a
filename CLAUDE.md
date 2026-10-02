# coupang-analytics

관리 쿠팡 판매자 계정들의 **상품별×일자별** 지표(노출순위·노출건수·판매건수·방문자)를 수집해
통합 엑셀(`쿠팡데이타분석_yymmdd_시분초.xlsx`)을 생성하는 **Windows 데스크톱 GUI(.exe, PyInstaller)**.

## 실행
```
cd D:\coupang-analytics
python ui/app_qt.py     # 기본 UI = PySide6(Qt) + Windows 11 Fluent 스타일
# python ui/app.py      # 폴백(Tkinter 버전, 동일 기능)
```
설계 SSOT: `designs/DESIGN.md`, `designs/KEYWORD_SELECTION.md`, `designs/GSHEET_UNIFIED.md`.

## 아키텍처 (핵심 모듈)
- `src/coupang_analytics/browser.py` — **실제 Chrome + CDP** 제어(`WingBrowser`). Akamai 봇탐지 통과 핵심.
- `pipeline.py` — `run_full`(계정마다 로그인→판매분석발견→[플래그 따라] 키워드/순위, 통합엑셀 1개 누적+**계정마다 중간저장**, 한 계정 실패해도 다음 진행). **재부팅 복구**: `write_run_stage`/`read_run_stage`가 `_실행단계.json`에 오늘 단계(sales=①완료·ranks=②완료·done) 기록 → 앱 `--resume`(로그온 트리거)가 이 마커+`resumable_progress`(①진행중)로 **판매수집 건너뛰고 순위부터** 이어서(중단분 없으면 즉시 종료). **전체실행은 단계별**: `run_full(keywords_off,sales_semi,skip_ranks)`[①판매] → `select_keywords_stage`[②] → `track_ranks_stage(semi)`[③](§현재 상태). 종료 시 `push_ledger_inventory`(그로스 재고 역기록)·`_push_gsheet`(구글시트). **매일 통계(cross-day)**: `carry_forward=True`면 단일 마스터(`쿠팡데이타분석_통계.xlsx`)를 이어써 **키워드 동결+날짜 컬럼 누적**, `grow_keywords=True`면 상한(`KW_MAX_TRACK=7`)·하루(`KW_ADD_PER_DAY=2`) 내 새 키워드만 발굴(기존 제거 안 함). `resume`·`redo_today`=실행모드. **날짜 컬럼(2026-09-16 확정)**: 라벨=**작업 실행날짜**(`run_full(date_label=)`, `_run_dates()`가 D-1판매조회와 분리 반환)·형식=**년도 없는 '월.일'**(예 09.16, 당분간·`%m.%d`), 순위=실행날짜·판매=전일(D-1) 데이터를 **같은 컬럼**에. 새벽 넘겨도 진행중 파일의 `date_label`로 시작일 기준 고정. **미실행/중단 날짜=날짜만 표기·값 공란**(`workbook.normalize_date_columns`+`ensure_date` 갭필로 시트별 첫날~마지막일 연속 유지·`apply_style`마다 멱등, 소급도구 `tools/normalize_dates.py`). 과거 D-1 라벨은 재라벨 안 함(앞으로만·경계에 빈 하루 정상). SSOT=`designs/DESIGN.md §일자 컬럼`.
- `input_list.py` — 입력 파싱(`parse_input_list`/`parse_input_rows`, 구글대장 `read_ledger_rows`, 비번 `parse_password_file`) + **그로스 재고 역기록**(`write_ledger_inventory`: 관리대장 AD열에 재고 씀, 매칭키=계정+등록상품명 유사도 `_best_inventory_match`).
- `collector.py`(판매분석 **데이터 API 직접조회** `fetch_sales_details`=`vi-detail-search` POST 주경로, `x-xsrf-token` 필요; 실패 시 엑셀 다운로드 폴백) · `report.py`(엑셀 폴백 파서 `parse_by_option` + `OptionMetric`) · `workbook.py`(통합 출력·등록상품명 보존·재고매칭 공급).
- `detail_images.py` — **상세페이지 이미지 추출(A안 CDP attach·ad-hoc)**: 앱이 브라우저를 안 띄우고, 사용자가 디버그포트(9222)로 띄운 **자기 warm·로그인 Chrome에 `extract_via_cdp`로 붙어**(connect_over_cdp) 현재 상품 탭 DOM만 읽어 **대표/갤러리+상세설명 이미지만** 저장(pw.stop()=연결만 해제·Chrome 유지). ⚠추천/리뷰도 같은 `vendor_inventory` URL이라 **DOM 컨테이너 스코핑**(상세=`.product-detail-content,.vendor-item`·대표=`div.product-image`)이 정밀도 핵심. 순수 로직 `extract_from_page(page,…)`. ⛔새 프로필로 코팡 접근=사무실 IP Akamai Access Denied(그래서 사용자 세션에 붙는 A안). SSOT=`designs/DESIGN.md §5.3`.
- `rank.py`(비로그인 오가닉 순위) · `kw_*`(키워드: AI 앵커·판정·선정=**OpenAI ChatGPT** + 네이버 검색광고 API 검색량 + 쿠팡 자동완성 `kw_suggest`; ⛔`kw_shopping.py`=네이버쇼핑 API 종료로 죽은 엔드포인트) · `human_typing/human_mouse`(사람같은 입력) · `credstore.py`(DPAPI 암호화).
- **노출순위 프록시**(③순위 전용·기본 OFF): `proxy_manager.py`(스레드세이프 풀·URL 정규화·CDP/Playwright 어댑터) · `proxy_pool.py`(`rank_proxy_or_skip`=fail-closed, OFF=None·오류=순위 스킵·직접연결 안 함 · `pick_rank_proxy`=egress 회전선택) · `proxy_blocklist.py`(차단 egress IP 목록·72h TTL·`resolve_egress_ip` 브라우저 IP에코) · `pipeline_ranks.drive_rank`(순위 브라우저 수명+egress 회전+차단이력 선제skip·신호 `_RANK_HALT["rotate"]`) · `config.apply_proxy_override`/`apply_rank_images_override`(config.json `proxy/*`·`rank/block_images` 런타임 토글) · `browser.WingBrowser(proxy=,block_images=)`(`--proxy-server`+CDP Fetch 인증 source=="Proxy"만·`--blink-settings=imagesEnabled=false`). URL=`proxies.txt`(gitignore·sessid 여러 줄=고정 sticky IP 풀).
- **구글 시트 통합**(입력=관리대장 구글시트·출력=결과 구글시트, SSOT=`designs/GSHEET_UNIFIED.md`): `gsheet_api.py`(서비스계정 Sheets API v4 클라이언트 `GSheetClient` read/write/`ensure_sheet(s)`/`batch_update`/`read_grid`, SA키=credstore `__gsheet_sa__`·DPAPI, 403/404/429 한국어) · `gsheet.py`(공개시트 xlsx export 읽기 폴백) · `input_list`에 `read_ledger_rows`/`parse_input_rows`(관리대장 직접 파싱, **삭제/판매중지=취소선(`read_strike_grid`로 Sheets API 취소선 조회) 또는 대장 '상태' 컬럼** — 파일 경로와 동일 OR 판정) · `gsheet_index.py`(결과 **`계정목록`**(공백 없음) 증분 동기화 `sync_index`·`plan_sync`: **자동열 A(대표자)·B(사업자)·C(계정ID)·D(상품)·H(상태)·I(체험단효과)** — ⚠**항목④(2026-09-26): 계정ID를 상품 왼쪽(C)으로 스왑**·밴드는 사업자명 기준(다계정ID=한 밴드)·셀폭 내용길이 자동맞춤·신규는 계정그룹 끝 insertDimension·**직원 입력 마케팅 E~G(체험단) 절대 미접촉**·안정키=B열(사업자) note(계정ID+등록명)·옛 시트 자동 마이그레이션: `_ensure_rep_column`(7→8열 대표자 삽입)+`_ensure_column_order`(옛 상품C·계정ID D → moveDimension으로 계정ID를 C로); **계정 삭제(2026-09-17)**: 관리대장에서 **줄이 사라진 계정=완전 삭제**(`delete_accounts`가 계정목록 행+통계 시트 제거·워크북은 `delete_account`), 대장에 **판매중지로 남은 건 유지+경고**(줄 존재 판정=`InputList.ledger_account_ids`); **마케팅 역머지** `read_marketing`(헤더기반 열탐지)/`apply_marketing`; `roster_from_workbook`) · `gsheet_stats.py`(사업자별 **통계 시트 = openpyxl 마스터 미러링**: `worksheet_to_requests`로 각 시트를 batchUpdate 번역·**전체 교체**, `push_statistics`; **직원 입력 키워드 역머지** `read_staff_keywords`/`merge_staff_keywords`). 파이프라인 `run_full(gsheet_output_url=)` → 시작 시 `_pull_gsheet_keywords`(직원 키워드 역머지), 최종 저장 직후 `_push_gsheet`(통계 미러링 + 계정목록 동기화). **①②③ 개별 실행도 모두 반영**(`select_keywords_stage`·`track_ranks_stage`도 `gsheet_output_url=` 받아 저장 후 `_push_gsheet`). **그로스 재고 역기록**=`push_ledger_inventory`가 입력 관리대장 AD열에 씀(입력 URL=`gsheet/input_url`). gsheet 실패는 로그로 명시·xlsx는 보존·비치명적. UI는 `gsheet/output_url`(app_qt=QSettings, app.py 폴백=winreg로 공유) 전달.
- `ui/app_qt.py` — **PySide6(Qt) GUI + Windows 11 Fluent 스타일(QSS)** — 기본 UI(설정/키워드추천/순위조회/**상세이미지**/전체실행 탭). "상세 이미지" 탭=CDP attach 이미지 추출([쿠팡용 크롬 실행]=디버그포트 전용 영속 프로필 `data/chrome-images`→사용자가 그 Chrome서 로그인·상품 열기→[이미지 추출]=run_bg로 CDP attach→탐색→추출→폴더 열기). 설정 탭 "구글 시트 연동" 카드(SA키·입출력 링크·연결확인·관리대장에서 불러오기·**기본 입력 소스 라디오**=구글시트(기본)/PC엑셀(선택), QSettings `input/source`; 무인 자동로드 `_auto_load_input`가 이 값을 따름, gsheet 실패 시 PC 폴백)·**💾 설정값 저장 버튼**(명시 저장). 백엔드 로직은 그대로 호출, 로그/완료는 시그널로 GUI 스레드 전달. `ui/app.py`는 동일 기능 Tkinter 폴백(PySide6 없이 `_shared_setting`=winreg로 app_qt QSettings 공유).

## ⚠️ 이미 해결한 함정 — 다시 깨지 말 것
1. **로그인 완료 판정**: `WingBrowser.authenticated()` = **윙 대시보드 URL 도달(xauth/sso 아님) AND `KEYCLOAK_IDENTITY` 쿠키** 둘 다.
   - `seller-uid` 쿠키는 **로그인 폼(xauth) 단계에도 존재** → 단독 사용 시 오판(과거 버그). 절대 단독 판정 금지.
   - URL 단독 판정도 금지(전환 중 transient `wing.coupang.com`).
2. **포트**: `WingBrowser(port=None)` → `_free_port()`로 **로그인마다 빈 포트 자동 할당**. 고정 포트 재사용 시 `ECONNRESET`. `_connect_cdp()` 6회 재시도 있음.
3. **프로세스 정리**: `__exit__` → `_kill_tree()`(`taskkill /F /T`). 안 하면 Chrome 쌓여 **메모리 먹통**(과거 246개 좀비).
4. **복원창 억제**: `--hide-crash-restore-bubble` 등 플래그 필수.
5. **로그인 창**: 화면 정중앙(`_center_pos`). 화면 밖으로 숨으면 입력 불가(과거 버그).
6. **자동입력**: `WingBrowser.autofill_login()` — 리다이렉트 후 폼(#username/#password/#kc-login)을 프레임까지 탐색해 채우고 제출. 로그인 폼은 **xauth.coupang.com Keycloak 표준 폼**.
7. **비밀번호 출처**: 입력 파일(`쿠팡 계정과 등록 상품리스트(분석용).xlsx`)에 **`비밀번호` 컬럼 존재**. `load_input`이 로드 시 `_store_passwords_from`으로 **자동 저장**(credstore). 별도 파일 불필요.
8. **콘솔창 깜빡임(2026-09-16 해결)**: 무인 `--auto`는 콘솔 없는 `pythonw`로 실행돼, browser.py의 보조 명령(파워셸 Chrome정리·taskkill·Chrome실행)이 명령마다 검은 콘솔창을 잠깐 띄웠다 닫음(계정마다 반복=번갈아 깜빡임). 직접 실행(터미널)은 이미 콘솔이 있어 안 뜸 — **방식은 동일**, 실행방법 차이. 해결=browser.py의 subprocess 4곳에 `creationflags=_NO_CONSOLE(=CREATE_NO_WINDOW)`. GUI 창은 그대로 뜸.
9. **폴더/경로 = 개발·운용 동일·평평한 한 폴더, output·data·config=삭제 금지(2026-09-21 해결)**: 예전엔 배포 폴더 위치/이름이 노트북과 달라, 재배포·재설치 시 상태(`output/`·`data/`)를 못 찾아 ①구글시트 복원(오염·중복)·②cold 프로필(차단)을 유발(2026-09-20 18:00 실측, `C:\쿠팡애널리틱스`서 실행돼 마스터 못 찾음). 해결=**개발(노트북)·운용(PC) 폴더 구조를 동일**하게 — 한 폴더(`coupang-analytics`, 폴더명도 동일) 안에 코드 + `output/`·`data/`·`config.json`(**삭제 금지·보존**)을 두고 **상대경로**로 쓴다. `apppaths.data_root()`=base_dir(=앱 폴더·frozen이면 exe 폴더·개발이면 repo 루트), env `COUPANG_DATA_ROOT`로 재지정 가능. `set_workdir()`가 그 폴더로 chdir. 설정은 `appconfig`(config.json, 비밀 아님만·키는 credstore)에 저장·시작 시 레지스트리와 동기화(`_sync_config_and_registry`). **배포=`coupang-analytics\`(코드+상태 한 폴더), 업데이트=새 zip 의 그 폴더를 같은 자리에 덮어쓰기**(output·data·config.json 은 zip 에 없어 보존). build.bat 이 **씨앗(`_씨앗\`)** 에 노트북 통계 마스터를 동봉→install.ps1 이 **첫 설치 때만** output 으로 복사(업데이트는 기존 보존). ⚠순위 크롬 프로필(data\chrome-pipeline)은 캐시 포함 수백MB·신뢰쿠키 교차이전 제한이라 zip 미동봉(운용 PC는 자기 data 폴더[휴지통 복원 등] 사용·야간 실행으로 자동 warm). onedir 폴더명=`coupang-analytics`(spec COLLECT·exe 이름은 쿠팡애널리틱스.exe 유지). SSOT=`apppaths.py`·`appconfig.py`.
10. **미서명 PyInstaller exe = Windows Defender 오탐(!ml)으로 자동 삭제(2026-09-22 해결)**: 배포 exe 는 코드서명이 없어 Defender ML 이 **오탐**(Wacatac/Wacapew `!ml`)으로 자동 격리·삭제(실제 바이러스 아님). 실측: 다른 PC 설치 시 `쿠팡애널리틱스.exe` 삭제됨. **해결=Defender 검사 제외**: (a) `deploy/0_먼저실행_보안제외.bat`(관리자·**압축 풀기 전** 실행 → `Add-MpPreference -ExclusionPath`. **build.bat 이 zip 루트+폴더에 항상 동봉**) (b) `install.ps1`이 설치 시 `$root` 를 제외 추가(설치 후 업데이트·재검사 때 재격리 방지) (c) `첫실행_설정안내.txt` 0)단계=보안제외 먼저. ⚠제외는 **반드시 압축 풀기 전에**(exe 는 푸는 순간 삭제). UPX 미사용(오탐 요인 아님). 근본 해결=코드서명(인증서 비용·사내 소수 PC엔 과함).

## 제약 (보안·정책)
- **🔒 로그인 정책 고정(DESIGN §4 — 변경 금지)**: **실제 Chrome + CDP 자동입력만.** ⛔ HTTP 폼-POST 위장 로그인(`requests`+UA/sec-ch-ua/Sec-Fetch 위장 + Akamai `_abck` 재생, 옛 `http_login.py` 방식) **도입 금지**(정책 위반 + 라이브에서 Akamai 차단으로 실제 불가). 브라우저는 **기본 숨김**(offscreen), 2차인증 등 사람 필요 시에만 **로그로 예고 후** 표시. **rank_browser와 로그인 브라우저를 동시에 열지 말 것**(sync playwright 는 한 스레드에 1개 — 중첩 시 "asyncio loop" 에러). `WingBrowser.__enter__`는 실행 전 그 프로필의 **잔여 Chrome 자동 정리**(프로필 잠금→포트 미개방 방지). 판매데이터 없음은 **정상 처리**(오류 아님).
- **지문/TLS 위조(stealth/fingerprint spoofing) = 하드 금지 아님·소유자 판단(2026-09-14 정정)**. 자기 상품 순위 확인은 위법 아님. 단 **정직한 실무 조언(소유자 보호)**: Akamai가 지문 불일치를 가장 잘 잡아 **위탁계정 밴 위험이 최대**(샵마인도 미사용=실제 Chromium) → 안전·유효한 것부터(실제 타이핑·마우스 입력 재현=허용·구현됨), 지문 쪽은 비핵심 컨텍스트 테스트+협의로 신중히. Claude가 일방적으로 금지하지 말 것.
  - **진행 승인(2026-09-14 소유자)**: 낮은위험 1·2단계 착수 = **①UA·클라이언트힌트 정합**(하드코딩 UA↔userAgentData 불일치 제거·실제 크롬 버전 일치) + **②자동화 흔적 정리**(webdriver 등 점검). 고위험 3단계(TLS/JA3·`_abck` 재생)는 별도 협의. 원칙=**정합(진짜에 맞추기)** 위주, 실효성은 핫스팟 A/B로 검증.
- **🔒 순위 조회 정책(2026-09-15 고정, DESIGN §5.2·§4.6)**: 쿠팡 순위는 **반자동(보이는 창에서 앱이 자동 타이핑+Enter, 화면만 읽음)만.** ⛔ **offscreen 자동 순위검색(공개 SERP 직접 fetch/네비)은 폐기**(라이브 실증 warm IP서 0/237 전멸 vs 반자동 237/237 완주). `_backfill_ranks`/`_measure_unfilled_once`/`_count_unfilled_ranks`(offscreen 순위백필)는 폐기·**물리 삭제**(2026-09-26). **전체실행 = ①반자동 → ②키워드선정(offscreen 노출측정 없음·단 쿠팡 자동완성=연관검색어는 사용) → ③반자동, offscreen 전무.** 무인 `--auto`는 `skip_ranks=True`라 노출측정 없음(이미 안전).
- **🔌 노출순위 프록시(2026-10-01, 기본 OFF→운용 ON)**: ③순위(비로그인 공개검색)만 프록시 뒤로 보냄. ⛔ **로그인·판매수집엔 절대 미적용**(위탁계정 밴 위험). **fail-closed**(ON인데 유효 프록시 없음=순위만 스킵·직접연결 우회 금지). URL=`proxies.txt`(gitignore, 평문 금지)·토글=`config.json proxy/enabled`·인증=`proxy/allow_auth`(HTTP user:pass만, SOCKS5 user:pass 거부). **라이브 실측(2026-10-02)**: DataImpulse 한국 주거용(회전 sticky)=통과(발견율 100%·하드차단 0)·Decodo 고정ISP=번아웃(≈7검색 뒤 영구차단)·**코드(CDP Fetch 인증)는 무결**. 원인=순수 IP 평판. SSOT=[[proxy-integration-off-261001]]·[[proxy-live-test-261002]].
  - **egress 재회전 + 차단 egress IP 목록(2026-10-02 구현·[[proxy-rotation-design-261002]])**: 차단 시 쿨다운 전에 **새 egress 로 회전**(`RANK_PROXY_ROTATE_MAX`)·소진 시 기존 쿨다운→당일중단. 차단당한 **실제 egress IP**(브라우저 IP에코)를 `rank_blocked_ips.json`(gitignore·72h TTL)에 기록→(재)기동 시 이력 IP **선제 skip**. 3경로(자동·반자동·전체실행) 전부. `drive_rank`·`proxy_blocklist`·`pick_rank_proxy`·신호 `_RANK_HALT["rotate"]`. proxies.txt=**sessid 여러 줄**(DataImpulse `;sessid.sNN`=서로 다른 고정 sticky IP 풀, 5~10줄 권장). 플래그/프록시 OFF면 기존 동작 동일.
  - **이미지 OFF 실험**: `config.json rank/block_images`=순위 이미지 로드 끔(`--blink-settings`·기본 OFF=이미지 켬). **라이브 판정 불가**(egress 평판 수분 변동으로 변수 분리 불가·깨끗IP가 이미지ON인데도 차단). 이미지≈SERP 60%(절감 잠재력)·**기본 OFF 유지**('이미지끄기=봇신호' 추정 반증 못함)·밤샘 규모로만 재검증.
  - **🔒 IP 정책=맥락별 반대([[proxy-ip-policy-by-context]])**: 로그인/수집=고정 IP(신뢰·2차인증)·순위(비로그인)=sticky 회전 여러 개(볼륨 번아웃 회피). "고정=신뢰"는 로그인에만 유효 — 순위에 옮기지 말 것(10-01 "회전 금지" 추론을 10-02 실측이 반증).
- **🔒 비밀번호 1회 오류 = 재시도 금지(2026-09-15, 계정잠금 방지)**: `classify_login()='error'`(#input-error=비번오류·계정잠금·휴면)이면 반자동 재시도를 건너뛰고 `LoginCredentialError`로 그 계정을 `done` 처리 → 야간 재개·같은 날 자동 재개가 **비번을 다시 제출하지 않음**(위탁계정 5회 오류=잠금). 소프트 차단(폼 정체·Akamai)만 반자동 1회 재시도. 비번 수정 후 새 실행에서 재시도.
- 폼에 `incogniaRequestToken`(Incognia 기기지문) + Akamai → **자동입력 100% 통과 보장 없음**. 2차인증/CAPTCHA는 열린 창에서 사람이 처리(수동 폴백).
- 비밀번호 = **DPAPI로 이 PC 전용 암호화**(`%LOCALAPPDATA%\coupang-analytics\creds.json`). 공유 파일·git·출력물에 평문 금지.
- 쿠키 주입한 새 브라우저는 판매분석 데이터API가 Akamai에 막힘 → **수집은 사람이 로그인한 그 세션/프로필 재사용에서만**.
- fallback 금지(try/except pass, silent None). 응답 한국어.

## 코드 건강 규칙 (회귀 방지 — 2026-09-22, SSOT=`designs/CODE_HEALTH_PLAN.md`)
> 배경: 잦은 수정으로 4파일(`pipeline.py`·`workbook.py`·`app_qt.py`·`app.py`)이 비대·괴물함수화되고
> "과거 정상→오류" 회귀가 반복됨. 이를 막는 게이트를 뒀다. **아래는 매 작업에서 지킨다.**
> ✅ **정비 완료(2026-09-22)**: 4파일의 **D/E/F 괴물함수 전멸(전부 C 이하·헬퍼 분해·행동 불변)**, 핀 3종
> 신설(pin_login_ranks·pin_apply_style·pin_run_plan). 남은=**모듈 분리로 MI C→B**(대형파일 포화·별도 단계)·**라이브 검증**. 상세=`designs/CODE_HEALTH_PLAN.md`.
- **커밋/푸시 전 게이트 통과 필수**: `python tools/run_checks.py`(전체 **8종**·오프라인·결정적)가 초록이어야 함.
  git 훅이 자동 검사(pre-commit=`--quick`[시뮬+핀3+구글시트+**정밀렌더검증**], pre-push=전체+`check_complexity.py`).
  8종 = 시뮬레이션·핀3(로그인발견/apply_style/실행모드)·구글시트오프라인·**정밀렌더검증(verify_render_precision, 2026-09-26)**·**셀독등록원장(verify_registry_offline, 2026-09-28)**·오프라인실증.
  **새 PC/클론 후 `python tools/install_hooks.py` 1회**. 응급 우회(`--no-verify`)는 **상시 금지**(회귀 유입).
- **테스트에서 실 API 금지**: 검증 3종은 로그인·OpenAI·네이버 **호출 없이** 돈다. `verify_offline`의 [6]
  키워드 선정도 **기본은 결정적 모킹**(경계만 페이크). 실 API 실증이 필요하면 `VERIFY_REAL_API=1`로 옵트인.
- **새 함수 CC ≤ 15 지향 · 파일 ≤ ~600줄 지향**: `check_complexity.py`가 4파일 밖에서 새 D+(CC≥21)
  괴물함수를 경고하고, 건강하던 파일이 MI **C로 떨어지면 차단**(exit 1). 건강(A/B) 파일은 그대로 유지.
- **A등급(건강) 파일은 건드리지 말 것**: 불필요 변경=새 회귀. 4개 썩은 파일 수정 시 **핀 테스트 먼저**
  (그 행동을 `simulate_pipeline`/`verify_offline`이 덮는지 확인, 얇으면 시나리오 추가 후 분해).
- **되돌림/정책 변경은 실측 근거 메모 필수**(플립플롭 방지, [[fix-from-real-evidence]]). 판매상태 소스·키워드
  로직처럼 왕복(A→B→A)한 이력이 있음 — 근거 없는 되돌림 금지.
- **분해는 행동 불변**(로직 바꾸지 말고 위치만): 정책·엣지케이스(로그인 판정·Akamai·날짜라벨·옵션분리·매칭
  게이트) 보존. 매 추출 후 게이트 초록 유지, 커밋은 작게·자주.

## 병렬 개발 (응답 대기 단축 — SSOT=`docs/PARALLEL_DEV.md`)
> 여러 세션이 **코드 편집만** 병렬. ⚠**런타임은 병렬화 금지**(단일 브라우저·위탁계정·Akamai·단일 마스터/시트 → 실행은
> 야간 단일 순차·라이브 테스트도 한 번에 한 세션). 상세·레인표·병합 프로토콜=`docs/PARALLEL_DEV.md`.
- **격리**: 세션마다 **자기 worktree+브랜치**에서 편집(master 직접 편집 금지). **비겹침 레인**(다른 파일집합)이라 merge 깨끗.
- **레인(편집 소유)**: A 수집/판매(`collector`·`pipeline_sales`·`pipeline_process`·`product_match`·`report`) · B 키워드(`kw_*`·`keyword_store`) · C 순위(`rank`·`pipeline_ranks`) · D 이미지(`detail_images`) · E 원장/정산(`registry_*`·`input_list`) · F 구글시트(`gsheet*`·`pipeline_gsheet`) · G 워크북(`workbook*`) · H UI(`ui/*`).
- **공유=직렬화**(한 번에 한 세션 or 통합 세션): `config.py`·`pipeline.py`·`browser.py`·`credstore.py`·`CLAUDE.md`·`designs/`·`docs/DECISIONS.md`. 레인이 config 값 필요하면 통제 세션에 요청(직접 편집 금지).
- **충돌 핫스팟**: 게이트/핀 파일(`tools/verify_offline.py` 등)=핀 함수 append+등록 1줄만 충돌 · DECISIONS/메모리=append-only.
- **병합**: 각 레인 `run_checks` 초록 후 push → **master 병합은 직렬**(한 브랜치씩·게이트 재실행). **2~3레인이 최적**(7레인 통제 관료제 불필요).

## 현재 상태 (상세는 각 메모·SSOT·git, 최신순)
- **✅반자동 순위 자동제출 이중 검색요청 제거(2026-10-02, SSOT=DESIGN §5.2·[[semi-auto-rank-and-exposed-name]])**: `_submit_search(browser, kw)`가 Enter 후 URL q 일치를 `RANK_SUBMIT_CONFIRM_SEC`(2.0s) 확인 → 네비 시작됐으면 버튼/폼 submit 폴백 **생략**(예전엔 무조건 재제출 = 키워드당 검색 2회·IP 소모). Enter 미통과 레이아웃만 폴백. 외부 리뷰 교차검증서 유일한 실질 결함(나머지는 낡은 ZIP 오판). 재현→수정→핀2종(Q·Q2)·게이트10 초록.
- **🔌 노출순위 egress 재회전+차단IP목록+이미지OFF실험(2026-10-02, 메모 [[proxy-rotation-design-261002]])**: 차단 시 새 egress 회전·차단 egress IP 72h 기록→이력 IP 선제 skip·3경로(자동·반자동·전체실행) 전부. proxies.txt=sessid 여러 줄. 이미지OFF 실험 플래그(기본 OFF). **실측**: 풀이 변동적(9개 중 3개만 순간 clean)→회전/목록이 유효·이미지ON/OFF는 IP노이즈로 판정불가(이미지≈SERP60%). 게이트10+복잡도+핀11 초록. ⚠남음=밤샘 규모검증.
- **🔌 노출순위 프록시 라이브 실측(2026-10-02, 메모 [[proxy-live-test-261002]])**: ③순위를 프록시 뒤로 보내 사무실 IP Akamai 차단 회피. **DataImpulse 한국 주거용(회전 sticky)=통과**(발견율 100%·하드차단 0·실주거 IP[LG·교육망]), **Decodo 전용ISP 고정IP=번아웃**(≈7검색 뒤 영구차단). 원인=순수 IP 평판(고정 플래그 대역 vs 실주거 회전)·**코드 무결**(같은 코드로 DataImpulse 통과). 운용=`proxies.txt`(gitignore·DataImpulse URL)·`config.json proxy/enabled=true`. ⚠**남음**: 첫 밤샘 271개 규모 검증·GB 데이터요금 확인·드물게 나쁜 회전IP=그 순간 공란(서킷브레이커+다음날 재측정이 보완). 아키텍처=사무실 1대로 ①②(무프록시)+③(프록시)·집IP 불필요.
- **✅매칭 5원인·AI 의미매칭·회사보유재고·정산2단계(2026-09-29, SSOT=DESIGN §0-000000000·[[handoff-session-260929]]·[[analysis-unmatched-blank-products-260929]])**: `product_match._assign` 해소 사다리(괄호정확→본문명우선→타이브레이커[판매중지제외·모델코드·동명병합]→AI 폴백 `augment_ai`·확신없으면 공란). `Product.sale_status` 신설. 회사보유재고=재고현황→대장 AB 역기록(`company_stock`·설정 `stock/url`). 정산2단계=D8+H_ui. ⚠라이브·운용PC 재배포 남음.
- **🆕셀독등록원장 1단계(2026-09-28, SSOT=LEDGER_REGISTRY.md·[[feature-ledger-registry]])**: 대장과 별도로 쌓는 원장(시트5·이력3·관리중단+중단일·비번원문 예외). `registry_*.py`·`tools/registry_sync.py`·설정 `registry/url`. 기존 흐름 미접촉. ⚠라이브 미실행(원장 시트 SA 편집공유 대기)·앱연계(2단계) 남음.
- **✅대장↔결과 정합성 근본수정(2026-09-27, [[input-ledger-format]])**: 상품명 칸 여러줄 셀→`input_list._parse_grid` 첫줄만 채택·죽은 옵션파싱 물리삭제. 커밋 5cc64a6.
- **✅코드건강 대정비 Tier A/B(2026-09-26, [[handoff-code-health-tierA-260926]]·[[deadcode-cleanup-260925]])**: 4파일 D+ 괴물함수 전멸(제자리 분해)·pipeline.py→6모듈·workbook.py→4모듈(전부 A/B, 코어만 C 허용)·죽은코드 물리삭제(offscreen 순위백필 등). 행동불변 확증(정밀렌더31/0·시뮬78/0). SSOT=CODE_HEALTH_PLAN §8.
- **✅결과파일 이미지 9이슈(2026-09-26, 메모 handoff-9issues-images-260926)**: 상품군 그룹키=블록명base·판매가/판매상태 지표행 자가치유·빈키워드행 낡은순위 삭제·비고소헤더=대장 판매상태·**상품명 링크=vid 기반**(`/vp/products/{pid|0}?vendorItemId={vid}`·미입고/판매자배송 커버)·'--' 등 비상품행 파싱제외.
- **✅소유자 9+6요구(2026-09-25~26, 메모 handoff-9items-spec-260925·feature-business-name-grouping·fix-multiaccount-reconcile-scope·fix-gsheet-movedimension-merge-400)**: ⑤**사업자명 기준 그룹핑**(같은 사업자 다계정ID=한 시트·계정ID=상품속성 col12)·⑥이력무관 완전삭제(줄 사라지면)·④계정목록 열순서(C=계정ID·D=상품)+폭·체험단효과 I열·다계정ID reconcile 스코핑(`account_id=`)·정밀렌더검증 게이트 편입·라이브 400(moveDimension×병합) 수정.
- **⏳상품 블록 헤더 레이아웃 v4(2026-09-24 확정·미구현, 메모 handoff-block-layout-redesign)**: 좌 A:B=라벨칸(상품명·VID·판매방식·로켓그로스3줄 세로병합)·C:F=값. vid=숨김 메타(`_상품ID` col3 재활성). workbook.py 11곳 대변경→**새 세션 핀 먼저·단계별**. SSOT=DESIGN §2.3.
- **✅3대 결정(2026-09-24, 메모 handoff-3decisions-260924)**: ①계정목록 상태=대장상태만 ②체험단효과 I열(직전→최신 점비교) ③로켓그로스 입고7컬럼→헤더 '최근입고' 요약.
- **✅구글시트 공통 재시도(2026-09-24)**: `GSheetClient._exec`가 일시오류(timeout·429·5xx) 지수백오프 재시도(MAX4)·영구오류(403/404/400) 즉시실패. 전 단계 적용. SSOT=gsheet_api.py.
- **🔒재고 규칙(2026-09-24, 메모 handoff-inventory-blank-260924·[[inventory-api-rfm-search]])**: 업번들 옵션=완전제외(`upBundling`)·재고값=재고현황 API `orderableQuantity`만(⛔상품조회 `stockQuantity` 신뢰불가)·vid 있으면 값(0=품절)·없으면 "미입고"·판매상태(productStatus)=지표행 기록·업번들/죽은중복 블록 자동 sweep(vid 앵커·NORMAL twin 보존)·응답원문(_raw gzip) 상시보관. SSOT=DESIGN §0-00000.
- **🔒VID 출처=상품조회(`vendor-inventory/search`)(2026-09-20, [[feature-vid-source-from-product-list]])**: 전상품·전옵션에서 등록명 매칭으로 vid 확보(폴백=판매분석). vid=헤더 이름칸 꼬리·옵션분리(대표=첫옵션 키워드+순위·2차=판매정보만)·블록명=등록명+옵션라벨·③매칭=sibling_vids. 라이브 검증됨. SSOT=DESIGN §0-00000·§2.3·§8-G.
- **판매상태 불일치 경고(2026-09-17, [[feature-sale-status-mismatch-flag]])**: 대장=판매중지인데 쿠팡=판매중이면 최신 날짜칸 적색(C00000).

### 운영 정책 (상시 유효)
- **전체실행 = ①반자동 → ②키워드선정(offscreen 없음) → ③반자동, offscreen 전무(2026-09-15)**. 무인 `--auto`도 동일 조합(18:00 시작). **⚠무인 종료=강제종료 금지(소유자 2026-09-23)** — ①②③+재고역기록 완주 후에만 `_auto_done`(옛 06:00 강제종료 폐지). 서킷브레이커로 스스로 끝남. SSOT=DESIGN §0-0.
- **순위조회 = 자동+반자동**(현재 기본=반자동 autosubmit, 앱이 타이핑+Enter·화면만 읽음·최대300위). 차단=쿨다운 재개(`RANK_SEMI_COOLDOWN_SEC=1800`×MAX4, 초과 시 당일중단). 매칭 시 노출명 갱신(vid 앵커). **순위=판매중 상품만**(`rank_suppressed`: 판매중지·임시저장·취소선 제외).
- **검색 간격 = `RANK_NAV_DELAY_MIN/MAX_SEC` 현재 45~75s(config.py만·설정탭 UI 없음)**. 35~55는 IP 태움 실측(2026-09-28 되돌림). 무차단 지속 확인 후에만 단계적 재하향(한 번에 낮추면 즉시 차단).
- **키워드 이원화**: `product_keywords` 비면 AI 선정·1건이라도 있으면 동결(직원 입력 포함, `_pull_gsheet_keywords` 역머지·추가만·제거 없음). **띄어쓰기=별개 키워드**(쿠팡서 순위 다름).
- **관리대장 그로스 재고 역기록(AD열)**(매칭키=계정+등록상품명 유사도)·**계정 추가/삭제 반영**(줄 사라지면 완전삭제·판매중지로 남으면 유지·`ledger_account_ids`). ⚠삭제=되돌릴 수 없음. SSOT=DESIGN §0-0.
- **대장↔쿠팡 정밀 매칭**(2026-09-18): 느슨 매칭 금지→핵심어 재현율·마진 게이트(`_RECALL_MIN`·`_MARGIN`), 미달=미매칭(오매칭보다 안전). vid 앵커로 안정.
- **재부팅 자동복구(2026-09-16)**: 야간 재부팅 시 '로그온' 트리거 `--resume`→판매수집 스킵·순위부터. Windows 자동로그인 필요.
- **로그인 2차인증**: ID/비번 단일단계(별도 OTP 페이지 없음). 2차인증=위치/환경 기반(사무실=OTP없이 통과·낯선환경=인증번호·5회오류 잠금). Akamai 차단 시 사람이 직접 타이핑(지문위조 금지라 우회 없음).
- 라이브 검증됨: 반자동 밤샘 무인 완주(2026-09-14: 22계정·271키워드·10.5h·차단0). **로그인/판매수집 라이브=사무실만**(위탁계정·2차인증 위치기반).
- 구글시트 `계정목록` 서식: 제목줄 동일색(B7C9E8)+사업자별 밴드8색(판매중지 행도 밴드색·값 보존). SSOT=GSHEET_UNIFIED.md.
- 검증도구: `tools/simulate_pipeline.py`(14시나리오)·`verify_offline.py`·`verify_gsheet_offline.py`·`verify_render_precision.py`(셀단위·게이트)·`verify_registry_offline.py`·`verify_rank_live.py`.

## 환경
- Windows, Python, Playwright(sync) + 실제 Google Chrome. 키(설정 탭에서 1회 입력→credstore 자동 로드): **필수** 네이버 검색광고 API + **OpenAI(ChatGPT) API**(키워드 AI 필수, 없으면 실행 중단).
- ⛔ **네이버쇼핑 검색 API(shop.json)는 2026-07-31자로 완전 종료**(대체 없음) — 경쟁강도 소스 소멸. 설정 탭 "(선택) 네이버쇼핑 키"는 무의미(발급 불필요), `kw_shopping.py`는 죽은 엔드포인트. 경쟁강도 대안=쿠팡 검색결과 총 상품수(구현 보류, HANDOFF §4-1).
