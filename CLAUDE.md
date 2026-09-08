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

## 현재 상태 · 다음 검증
- v1 전체 조립 완료. 순차 로그인 **자동입력 + 견고한 완료판정 + 즉시·확정 진단(`classify_login`)**까지 구현됨.
- ✅ 검증됨: 입력 엑셀에 `비밀번호` 컬럼 → 로드 시 자동 저장(`[비번] 29개 저장됨`). ID/비번 **자동입력·제출 정상 동작**.
- 🔎 **로그인 폼 JS 정밀분석 완료(원본 캡처는 클린업으로 삭제, 결과는 아래 정리)**: 로그인 폼은 **ID/비번 단일 단계**(별도 OTP 페이지 없음). `#input-error`에 뜰 수 있는 메시지 4종 = ①비번오류(Keycloak 기본) ②`시스템 보안관리자가 직접 잠금처리한 계정입니다` ③`인증번호를 5번 잘못 입력하셨습니다…고객센터` ④`지난 90일동안 로그인 이력이 없어 계정 사용이 중지…`. **핵심 정정**: "인증번호"는 *입력칸이 아니라* OTP 5회 오류 **잠금 오류 메시지** → 평상시 로그인에 OTP 단계 없음. 폼엔 Akamai 챌린지 오버레이 `#sec-overlay`(평소 `display:none`) + `#incogniaRequestToken`가 깔려 있음.
- 📍 **2차 인증은 위치/환경 기반 조건부(step-up)**: **사무실(신뢰 환경)에서만 OTP 없이 통과**, 집 등 낯선 환경은 **2차 인증(인증번호) 요구**. 따라서 **로그인 테스트는 사무실에서만** 가능. 인증번호 5회 오류 시 계정 잠김 → 낯선 환경에서 반복 로그인 시도 금지.
- ✅ **원인 확정(2026-09-03 라이브 실 테스트)**: 자동입력·자동제출(`#kc-login` 클릭) 시 `xauth.coupang.com/.../login-actions/authenticate` 요청이 **Akamai에 전면 차단** — 화면에 `Access Denied` + `errors.edgesuite.net` + `Reference #…`. 즉 **자동 제출이 봇으로 탐지됨**(HANDOFF §5 원인 후보 ②확정). 오늘 우리 반복 자동 접속(순위·세션스캔 여러 번)이 IP 플래그를 올렸을 수도. **대응 = 수동 로그인**(지문위조 금지라 우회 없음).
  - 코드 반영: `classify_login`에 `blocked` 코드 추가(`_BLOCK_MARKERS`로 Access Denied 페이지 즉시 감지 → 5분 대기 안 함), `wait_for_login`이 `blocked` 안내, 실 테스트 스크립트에 `--manual`(자동입력 건너뛰고 사람이 직접 로그인) 추가.
  - 권장 흐름: 자동입력이 걸리면 그 창에서 `wing.coupang.com` 재접속 → **사람이 직접 타이핑 로그인**. Akamai 플래그는 몇 분~십수 분 뒤 완화.
- ⚠️ **세션 짧게 만료 + 통과 계정 0개 확인(2026-09-03)**: 이전 로그인 6계정 세션 전부 만료(`classify_login`=`form`, Access Denied 아님=진짜 만료). 현재 2차인증 없이 되는 세션이 없어 discover 라이브는 보류. **계정은 위탁 관리분이라 무리한 로그인/2차인증 시도 금지** — 사무실 신뢰환경에서 2차인증 없이 로그인 완료되는 세션이 생겼을 때 그 자리에서 즉시 수집(`run_full` 계정단위 설계가 이걸 보장). 세션 확인 도구(로그인 시도 없음, 안전): `python tools/verify_discover_live.py --scan [계정ID …]`.
- ✅ **작업순서 변경 완료(계정단위 건별)**: `run_full`을 계정단위 end-to-end로 재작성. 방금 로그인한 신선한 세션에서 바로 수집 → **세션 만료 재로그인 문제 제거**. 워크북 `empty()`/`add_account()` 추가, `_login_and_discover()` 신설, `_track_ranks(warmup_first=)` 추가. UI는 '순차 로그인' 버튼 제거하고 '전체 실행' 하나로 통합(`get_password` 전달). (구 2단계 `_discover_accounts` 제거)
- ✅ **재개(이어서) 지원**: 진행 중엔 `output/쿠팡데이타분석_진행중.xlsx`(+`.json` 상태)에 저장, 완료 시 타임스탬프 최종본으로 rename+상태삭제. UI 팝업(이어서/새로/취소). `resume=True`면 **완료 계정 건너뛰고**, 미완료 계정은 **키워드 재사용(진행 엑셀의 노출순위 행에서 복원, API 재호출 X) + 이미 조회된 순위 (상품×키워드) 건너뛰기**로 끊긴 지점부터. 순위는 **키워드마다 저장**(`_track_ranks_resume`). 계정 완료 확정 시 `done`에 기록. 워크북 `has_product`/`ensure_product_block`/`product_keywords`/`is_rank_filled` 추가. 판매지표는 멱등이라 재수집 무해. 로그인은 세션 마커로 이미 재사용.
- ✅ **정밀분석·클린업 완료**: pyflakes/vulture 무결(죽은코드 0). 죽은 모듈 삭제(`session.py`·`mapping.py`), 미사용 함수 제거(pipeline `login_all_sequential`/`login_account`/`run_pipeline`/`_track_ranks`(원본)/`_extract_keywords`/마커시스템, browser `inject_cookies`/`logged_in`, workbook `create`/`add_account`, collector `collect_day`, report `parse_vendor_item_report`/`sum_metrics`/`ItemMetric`, credstore `has`/`delete`/`accounts`, config `PRODUCT_METRICS`/`ACCOUNT_DELAY_*`). **로그인 마커(`.wing_logged_in`) 폐지** — 이제 완료판정은 `authenticated()`(세션)+`progress.json`(재개)만. 작업파일 삭제: `capture/`·`output/` 옛산출물·`designs/DESIGN.html`(SSOT는 `DESIGN.md`). `data/`(세션 25프로필) 보존.
- ✅ **2차 최적화·한글화**: 미사용 상수/메서드 추가 제거(browser `SALES_ANALYSIS_URL`·`storage_state`), `_fill_sales` 단일계정 시그니처로 단순화(어색한 `[report_acc]`/`{id:metrics}` 래핑 제거), 옛 설계 설명(storage_state 저장·쿠키주입) 독스트링을 현재(프로필 재사용)로 교체, 서술형 영문(end-to-end·bigram·fallback·override·광고depth 등) 전면 한글화. pyflakes·vulture 0 유지.
- ✅ **로그인 판정(`authenticated()`) 분석 = 현행 유지가 최선**: 2중 방어 구조라 적정. (1) `authenticated()` = 윙 대시보드 URL 도달 + `KEYCLOAK_IDENTITY` 쿠키(둘 다) → 로그인 '완료 시점' 판정용 경량 프록시. (2) 세션이 실제 수집에 유효한지의 **궁극 판정은 `discover()`의 데이터 API 성공**(만료 세션이면 403/리다이렉트로 실패→그 계정만 건너뜀). 쿠키 이름만 확인하는 한계는 URL 조건(대시보드 실도달)이 보완하고, Playwright `context.cookies()`는 만료 쿠키를 안 돌려줌. → authenticated()를 더 무겁게(데이터 API 직접 probe) 만들 필요 없음(discover가 이미 그 역할).
- ✅ **시뮬레이션 검증(`tools/simulate_pipeline.py`)**: 브라우저·로그인·네이버API·순위조회를 가짜로 대체하고 `run_full` 실제 로직을 돌려 3시나리오 통과 — ①정상 전체실행(최종본·값 기록) ②크래시→이어서(완료계정 건너뜀·키워드 재사용·계정 내부 순위 이어가기·진행파일 정리) ③로그인 실패 계정 건너뛰기. 실행: `python tools/simulate_pipeline.py`.
- ✅ **로그인 불필요 부분 실증(가짜 아님, 실제 실행)**:
  - `tools/verify_offline.py` — 입력엑셀 파싱(실파일: 계정35·상품79) · 제목 시드 · 워크북 xlsx 왕복 · credstore DPAPI 암복호화 왕복 · 리포트 파서 · **네이버 검색광고 API 실호출**('텀블러' 연관 699개 수신). 모두 통과.
  - `tools/verify_rank_live.py` — **실제 Chrome + 쿠팡 비로그인 검색**: 1페이지 60항목=광고10+오가닉50 파싱·광고 제외, `organic_rank`='텀블러' 1위 산출. 실증 후 좀비 Chrome 0개(`_kill_tree` 정상).
  - 라이브 **로그인/판매분석 수집**은 사무실에서(§5·2차인증 위치기반).
- 남은 개선: 단일일자 수집, 대량 실행 속도/스코프, 사무실에서 판매분석 발견→키워드→순위→통합엑셀 라이브 검증.

## 환경
- Windows, Python, Playwright(sync) + 실제 Google Chrome. 키(설정 탭에서 1회 입력→credstore 자동 로드): **필수** 네이버 검색광고 API + **OpenAI(ChatGPT) API**(키워드 AI 필수, 없으면 실행 중단).
- ⛔ **네이버쇼핑 검색 API(shop.json)는 2026-07-31자로 완전 종료**(대체 없음) — 경쟁강도 소스 소멸. 설정 탭 "(선택) 네이버쇼핑 키"는 무의미(발급 불필요), `kw_shopping.py`는 죽은 엔드포인트. 경쟁강도 대안=쿠팡 검색결과 총 상품수(구현 보류, HANDOFF §4-1).
