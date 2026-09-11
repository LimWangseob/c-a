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
- `ui/app_qt.py` — **PySide6(Qt) GUI + Windows 11 Fluent 스타일(QSS)** — 기본 UI(설정/키워드추천/순위조회/전체실행 탭). 백엔드 로직은 그대로 호출, 로그/완료는 시그널로 GUI 스레드 전달. `ui/app.py`는 동일 기능 Tkinter 폴백.

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
- **지문 위조(stealth/fingerprint spoofing) 코드 금지** — 계정정지 위험 + 분류기 차단. 실제 Chrome 수동/자동입력만.
- 폼에 `incogniaRequestToken`(Incognia 기기지문) + Akamai → **자동입력 100% 통과 보장 없음**. 2차인증/CAPTCHA는 열린 창에서 사람이 처리(수동 폴백).
- 비밀번호 = **DPAPI로 이 PC 전용 암호화**(`%LOCALAPPDATA%\coupang-analytics\creds.json`). 공유 파일·git·출력물에 평문 금지.
- 쿠키 주입한 새 브라우저는 판매분석 데이터API가 Akamai에 막힘 → **수집은 사람이 로그인한 그 세션/프로필 재사용에서만**.
- fallback 금지(try/except pass, silent None). 응답 한국어.

## 현재 상태
- v1 완성·운용 중. 3단계(①판매수집(로그인) ②키워드선정 ③순위조회) 분리, 계정단위 end-to-end, 재개(`진행중.xlsx`+`.json`)·통계 마스터 이어쓰기·서킷브레이커 구현.
- **순위조회 = 자동 + 반자동**: 자동=비로그인 검색(차단 시 중단·다음 실행이 이어서). 반자동=앱이 창을 띄우고 키워드 안내→**사람이 그 창에서 직접 검색→앱은 화면만 읽어 순위 산출**(자동 네비 0 → 차단 회피, 사무실 밖 검증 가능). 매칭 시 계약상품명을 검색결과 **정확 노출명으로 갱신**(정체성=vendorItemId 앵커라 이름 바뀌어도 시계열 키 안정).
- 라이브 검증됨: 비로그인 순위·**반자동 end-to-end('텀블러' 1위+정확명 저장)**·오프라인 파싱. **로그인/판매수집 라이브는 사무실에서만**(2차인증 위치기반 §아래, 위탁계정이라 무리한 로그인 금지).
- 검증도구: `python tools/simulate_pipeline.py`(모킹 9시나리오), `tools/verify_offline.py`, `tools/verify_rank_live.py`.

**로그인 2차인증**: ID/비번 단일 단계(별도 OTP 페이지 없음). 2차인증은 **위치/환경 기반 조건부**(사무실=OTP 없이 통과, 낯선 환경=인증번호 요구·5회 오류 시 계정잠김). 자동제출이 Akamai에 차단되면 그 창에서 사람이 직접 타이핑 로그인(지문위조 금지라 우회 없음).

## 환경
- Windows, Python, Playwright(sync) + 실제 Google Chrome. 키(설정 탭에서 1회 입력→credstore 자동 로드): **필수** 네이버 검색광고 API + **OpenAI(ChatGPT) API**(키워드 AI 필수, 없으면 실행 중단).
- ⛔ **네이버쇼핑 검색 API(shop.json)는 2026-07-31자로 완전 종료**(대체 없음) — 경쟁강도 소스 소멸. 설정 탭 "(선택) 네이버쇼핑 키"는 무의미(발급 불필요), `kw_shopping.py`는 죽은 엔드포인트. 경쟁강도 대안=쿠팡 검색결과 총 상품수(구현 보류, HANDOFF §4-1).
