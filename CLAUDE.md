# coupang-analytics

관리 쿠팡 판매자 계정들의 **상품별×일자별** 지표(노출순위·노출건수·판매건수·방문자)를 수집해
통합 엑셀(`쿠팡데이타분석_yymmdd_시분초.xlsx`)을 생성하는 **Windows 데스크톱 GUI(.exe, PyInstaller)**.

## 실행
```
cd D:\coupang-analytics
python ui/app_qt.py     # 기본 UI = PySide6(Qt) + Windows 11 Fluent 스타일
# python ui/app.py      # 폴백(Tkinter 버전, 동일 기능)
```
설계 SSOT: `designs/DESIGN.md`, `designs/KEYWORD_SELECTION.md`.

## 아키텍처 (핵심 모듈)
- `src/coupang_analytics/browser.py` — **실제 Chrome + CDP** 제어(`WingBrowser`). Akamai 봇탐지 통과 핵심.
- `pipeline.py` — `run_full`(**계정단위 end-to-end**: 계정마다 로그인→판매분석발견→키워드→순위 완결 후 다음 계정, 통합엑셀 1개에 누적+**계정마다 중간저장**, 한 계정 실패해도 다음 진행). **매일 통계(cross-day)**: `carry_forward=True`면 단일 마스터(`쿠팡데이타분석_통계.xlsx`)를 이어써 **키워드 동결+날짜 컬럼 누적**(시계열 의미), `grow_keywords=True`면 상한(`KW_MAX_TRACK=7`)·하루(`KW_ADD_PER_DAY=2`) 내 새 키워드만 발굴 추가(기존 절대 제거 안 함). `resume=True`는 같은 날 크래시 복구.
- `input_list.py` — 입력 엑셀 파싱(`parse_input_list`, `parse_password_file`).
- `collector.py`(판매분석 **데이터 API 직접조회** `fetch_sales_details`=`vi-detail-search` POST, `x-xsrf-token` 필요; 실패 시 엑셀 다운로드 폴백/발견) · `report.py`(엑셀 폴백 파서 `parse_by_option` + `OptionMetric`) · `workbook.py`(통합 출력).
- `rank.py`(비로그인 오가닉 순위) · `kw_*`(키워드: AI 앵커추출·관련성판정=**OpenAI ChatGPT** + 네이버 검색광고 API 검색량 + `kw_shopping.py` 네이버쇼핑 상품수→경쟁강도) · `credstore.py`(DPAPI 암호화).
- **구글 시트 통합**(입력=관리대장 구글시트·출력=결과 구글시트, SSOT=`designs/GSHEET_UNIFIED.md`): `gsheet_api.py`(서비스계정 Sheets API v4 클라이언트 `GSheetClient` read/write/`ensure_sheet(s)`/`batch_update`/`read_grid`, SA키=credstore `__gsheet_sa__`·DPAPI, 403/404/429 한국어) · `gsheet.py`(공개시트 xlsx export 읽기 폴백) · `input_list`에 `read_ledger_rows`/`parse_input_rows`(관리대장 직접 파싱, **삭제/판매중지=취소선(`read_strike_grid`로 Sheets API 취소선 조회) 또는 대장 '상태' 컬럼** — 파일 경로와 동일 OR 판정) · `gsheet_index.py`(결과 **`계정목록`**(공백 없음) 증분 동기화 `sync_index`·`plan_sync`: **자동열 A·B·C·G만**·신규는 계정그룹 끝 insertDimension·삭제=상태만⛔·**직원 입력 마케팅 D~F 절대 미접촉**·안정키=A열 note; **마케팅 역머지** `read_marketing`/`apply_marketing`; `roster_from_workbook`) · `gsheet_stats.py`(사업자별 **통계 시트 = openpyxl 마스터 미러링**: `worksheet_to_requests`로 각 시트를 batchUpdate 번역·**전체 교체**, `push_statistics`; **직원 입력 키워드 역머지** `read_staff_keywords`/`merge_staff_keywords`). 파이프라인 `run_full(gsheet_output_url=)` → 시작 시 `_pull_gsheet_keywords`(직원 키워드 역머지), 최종 저장 직후 `_push_gsheet`(통계 미러링 + 계정목록 동기화). **①②③ 개별 실행도 모두 반영**(`select_keywords_stage`·`track_ranks_stage`[자동·반자동]도 `gsheet_output_url=` 받아 저장 후 `_push_gsheet`). gsheet 실패는 로그로 명시·xlsx는 보존·비치명적. UI는 `gsheet/output_url`(app_qt=QSettings, app.py 폴백=winreg로 공유) 전달.
- `ui/app_qt.py` — **PySide6(Qt) GUI + Windows 11 Fluent 스타일(QSS)** — 기본 UI(설정/키워드추천/순위조회/전체실행 탭). 설정 탭 "구글 시트 연동" 카드(SA키·입출력 링크·연결확인·관리대장에서 불러오기·**기본 입력 소스 라디오**=구글시트(기본)/PC엑셀(선택), QSettings `input/source`; 무인 자동로드 `_auto_load_input`가 이 값을 따름, gsheet 실패 시 PC 폴백). 백엔드 로직은 그대로 호출, 로그/완료는 시그널로 GUI 스레드 전달. `ui/app.py`는 동일 기능 Tkinter 폴백(PySide6 없이 `_shared_setting`=winreg로 app_qt QSettings 공유).

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

## 제약 (보안·정책)
- **🔒 로그인 정책 고정(DESIGN §4 — 변경 금지)**: **실제 Chrome + CDP 자동입력만.** ⛔ HTTP 폼-POST 위장 로그인(`requests`+UA/sec-ch-ua/Sec-Fetch 위장 + Akamai `_abck` 재생, 옛 `http_login.py` 방식) **도입 금지**(정책 위반 + 라이브에서 Akamai 차단으로 실제 불가). 브라우저는 **기본 숨김**(offscreen), 2차인증 등 사람 필요 시에만 **로그로 예고 후** 표시. **rank_browser와 로그인 브라우저를 동시에 열지 말 것**(sync playwright 는 한 스레드에 1개 — 중첩 시 "asyncio loop" 에러). `WingBrowser.__enter__`는 실행 전 그 프로필의 **잔여 Chrome 자동 정리**(프로필 잠금→포트 미개방 방지). 판매데이터 없음은 **정상 처리**(오류 아님).
- **지문/TLS 위조(stealth/fingerprint spoofing) = 하드 금지 아님·소유자 판단(2026-09-14 정정)**. 자기 상품 순위 확인은 위법 아님. 단 **정직한 실무 조언(소유자 보호)**: Akamai가 지문 불일치를 가장 잘 잡아 **위탁계정 밴 위험이 최대**(샵마인도 미사용=실제 Chromium) → 안전·유효한 것부터(실제 타이핑·마우스 입력 재현=허용·구현됨), 지문 쪽은 비핵심 컨텍스트 테스트+협의로 신중히. Claude가 일방적으로 금지하지 말 것.
  - **진행 승인(2026-09-14 소유자)**: 낮은위험 1·2단계 착수 = **①UA·클라이언트힌트 정합**(하드코딩 UA↔userAgentData 불일치 제거·실제 크롬 버전 일치) + **②자동화 흔적 정리**(webdriver 등 점검). 고위험 3단계(TLS/JA3·`_abck` 재생)는 별도 협의. 원칙=**정합(진짜에 맞추기)** 위주, 실효성은 핫스팟 A/B로 검증.
- 폼에 `incogniaRequestToken`(Incognia 기기지문) + Akamai → **자동입력 100% 통과 보장 없음**. 2차인증/CAPTCHA는 열린 창에서 사람이 처리(수동 폴백).
- 비밀번호 = **DPAPI로 이 PC 전용 암호화**(`%LOCALAPPDATA%\coupang-analytics\creds.json`). 공유 파일·git·출력물에 평문 금지.
- 쿠키 주입한 새 브라우저는 판매분석 데이터API가 Akamai에 막힘 → **수집은 사람이 로그인한 그 세션/프로필 재사용에서만**.
- fallback 금지(try/except pass, silent None). 응답 한국어.

## 현재 상태
- v1 완성·운용 중. 3단계(①판매수집(로그인) ②키워드선정 ③순위조회) 분리, 계정단위 end-to-end, 재개(`진행중.xlsx`+`.json`)·통계 마스터 이어쓰기·서킷브레이커 구현.
- **순위조회 = 자동 + 반자동**: 자동=비로그인 검색(차단 시 중단·다음 실행이 이어서, 쿨다운 900s·MAX 2). **반자동(현재 기본 autosubmit)**=앱이 신뢰 세션 창에서 키워드를 **한 글자씩 자동 타이핑+Enter까지 자동**(손 안 대도 됨) → 화면만 읽어 순위 산출(최대 300위). `RANK_SEMI_AUTOSUBMIT=False`면 옛 방식(사람이 Enter). 차단 시 **하드중단이 아니라 쿨다운-재개**(`RANK_SEMI_COOLDOWN_SEC=1800`×`MAX=4`, 초과 시 당일중단). 매칭 시 계약상품명을 검색결과 **정확 노출명으로 갱신**(정체성=vendorItemId 앵커라 이름 바뀌어도 시계열 키 안정).
- **검색 간격 = `RANK_NAV_DELAY_MIN/MAX_SEC`(현재 45~75s, `config.py`에서만 조정 — 설정탭 입력 UI 없음)**. 90~150(과보수)에서 하향(2026-09-14 실측: 밤샘 대기가 총시간 ~86%). 무차단 유지 시 30~50 추가 하향 검토(단계적).
- 라이브 검증됨: 비로그인 순위·오프라인 파싱·**반자동 밤샘 무인 완주(2026-09-14: 22계정·271키워드·10.5h·차단 0건, 48개 1~50위, vid없는 상품 상품명 폴백 작동)**. **로그인/판매수집 라이브는 사무실에서만**(2차인증 위치기반 §아래, 위탁계정이라 무리한 로그인 금지). ⚠ 순위 라이브는 **핫스팟(깨끗한 IP)** 권장(사무실 IP Akamai 차단 이력).
- **구글시트 `계정목록` 서식(2026-09-14)**: 제목줄 **전체 동일색**(B7C9E8)·사업자별 **밴드 8색**(중간채도·웜↔쿨 교대 대비)·**판매중지 행도 사업자 밴드색**(값 보존). SSOT=`designs/GSHEET_UNIFIED.md`.
- **키워드 출처 이원화(값 있으면 동결·없으면 AI)**: 상품별 키워드는 ①AI 자동 선정 또는 ②**직원이 결과 통계 시트에 직접 입력**. 규칙=`product_keywords`가 비지 않으면 AI 선정 생략·동결(사람 입력 포함). 직원 입력은 실행 시작 시 `_pull_gsheet_keywords`가 통계 시트 키워드 영역을 워크북으로 **역머지**(위치기반 파싱, G='노출 순위' 없어도 잡음) → 그 상품 AI 생략, 종료 시 미러링(전체 교체)돼도 보존. **추가만·제거 없음**(동결 원칙).
- 검증도구: `python tools/simulate_pipeline.py`(모킹 9시나리오), `tools/verify_offline.py`, `tools/verify_gsheet_offline.py`(구글통합 7종), `tools/verify_rank_live.py`.

**로그인 2차인증**: ID/비번 단일 단계(별도 OTP 페이지 없음). 2차인증은 **위치/환경 기반 조건부**(사무실=OTP 없이 통과, 낯선 환경=인증번호 요구·5회 오류 시 계정잠김). 자동제출이 Akamai에 차단되면 그 창에서 사람이 직접 타이핑 로그인(지문위조 금지라 우회 없음).

## 환경
- Windows, Python, Playwright(sync) + 실제 Google Chrome. 키(설정 탭에서 1회 입력→credstore 자동 로드): **필수** 네이버 검색광고 API + **OpenAI(ChatGPT) API**(키워드 AI 필수, 없으면 실행 중단).
- ⛔ **네이버쇼핑 검색 API(shop.json)는 2026-07-31자로 완전 종료**(대체 없음) — 경쟁강도 소스 소멸. 설정 탭 "(선택) 네이버쇼핑 키"는 무의미(발급 불필요), `kw_shopping.py`는 죽은 엔드포인트. 경쟁강도 대안=쿠팡 검색결과 총 상품수(구현 보류, HANDOFF §4-1).
