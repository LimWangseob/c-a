# 이미 해결한 함정 (PITFALLS)

> 📦 2026-11-05 `CLAUDE.md` 에서 **원문 그대로** 옮김(D-151·대조표=`docs/decisions/claudemd-move-2026-11-05.md`). ⛔세션에 자동으로 안 읽힘 — 해당 작업 전에 직접 읽는다. 상시 규칙 한 줄 요약은 `CLAUDE.md` '상시 규칙' 절. 결정이 어긋나면 `docs/DECISIONS.md` 가 기준(뒤 항목 우선)이고, 어긋남은 작업 전에 보고한다.

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
9. **폴더/경로 = 개발·운용 동일·평평한 한 폴더, output·data·config=삭제 금지(2026-09-21 해결)**: 예전엔 배포 폴더 위치/이름이 노트북과 달라, 재배포·재설치 시 상태(`output/`·`data/`)를 못 찾아 ①구글시트 복원(오염·중복)·②cold 프로필(차단)을 유발(2026-09-20 18:00 실측, `C:\쿠팡애널리틱스`서 실행돼 마스터 못 찾음). 해결=**개발(노트북)·운용(PC) 폴더 구조를 동일**하게 — 한 폴더(`coupang-analytics`, 폴더명도 동일) 안에 코드 + `output/`·`data/`·`config.json`(**삭제 금지·보존**)을 두고 **상대경로**로 쓴다. `apppaths.data_root()`=base_dir(=앱 폴더·frozen이면 exe 폴더·개발이면 repo 루트), env `COUPANG_DATA_ROOT`로 재지정 가능. `set_workdir()`가 그 폴더로 chdir. 설정은 `appconfig`(config.json, 비밀 아님만·키는 credstore)에 저장·시작 시 레지스트리와 동기화(`_sync_config_and_registry`). **배포=`coupang-analytics\`(코드+상태 한 폴더), 업데이트=새 zip 의 그 폴더를 같은 자리에 덮어쓰기**(output·data·config.json·proxies.txt 는 coupang-analytics\ 직접엔 없어 **덮어써도 보존**). build.bat 이 **씨앗(`_씨앗\`)** 에 노트북 통계 마스터 + **검증된 `config.json`(링크4·입력소스·순위간격·프록시 토글 전부) + `proxies.txt`(프록시 자격증명)** 를 동봉→install.ps1 이 **첫 설치 때만** 루트/`output`으로 복사(업데이트는 기존 보존). **설정 이식=노트북에서 💾 저장으로 config.json 확정 → build.bat 이 그 파일을 씨앗으로 담음 → 운용 PC 복사만**(과거 `_설정값.json` qsettings 재생성은 프록시 키 누락 결함이 있어, config.json 통째 전달이 권위·`_설정값.json`은 credstore 키[네이버·OpenAI·SA] 전용으로 유지). 2026-10-05 전환. ⚠순위 크롬 프로필(data\chrome-pipeline)은 캐시 포함 수백MB·신뢰쿠키 교차이전 제한이라 zip 미동봉(운용 PC는 자기 data 폴더[휴지통 복원 등] 사용·야간 실행으로 자동 warm). onedir 폴더명=`coupang-analytics`(spec COLLECT·exe 이름은 쿠팡애널리틱스.exe 유지). SSOT=`apppaths.py`·`appconfig.py`.
10. **미서명 PyInstaller exe = Windows Defender 오탐(!ml)으로 자동 삭제(2026-09-22 해결)**: 배포 exe 는 코드서명이 없어 Defender ML 이 **오탐**(Wacatac/Wacapew `!ml`)으로 자동 격리·삭제(실제 바이러스 아님). 실측: 다른 PC 설치 시 `쿠팡애널리틱스.exe` 삭제됨. **해결=Defender 검사 제외**: (a) `deploy/0_먼저실행_보안제외.bat`(관리자·**압축 풀기 전** 실행 → `Add-MpPreference -ExclusionPath`. **build.bat 이 zip 루트+폴더에 항상 동봉**) (b) `install.ps1`이 설치 시 `$root` 를 제외 추가(설치 후 업데이트·재검사 때 재격리 방지) (c) `첫실행_설정안내.txt` 0)단계=보안제외 먼저. ⚠제외는 **반드시 압축 풀기 전에**(exe 는 푸는 순간 삭제). UPX 미사용(오탐 요인 아님). 근본 해결=코드서명(인증서 비용·사내 소수 PC엔 과함).
