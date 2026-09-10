# HANDOFF — coupang-analytics 인수인계 (2026-09-09 갱신 · ①라이브 버그·차단 전면 수정, 9/28 수집 후 "이어서" 대기)

> 새 세션 읽기 순서: **이 문서(§0 최신 세션 먼저) → `CLAUDE.md`(제약·함정) → `designs/KEYWORD_SELECTION.md`·`designs/DESIGN.md`(SSOT) → 메모리(`MEMORY.md`)**.
> 이 문서는 **지금 이어서 할 일** 중심의 연속성 문서다. §1~ 이하 상당수는 **구(舊) 서식 시절 서술**이라 셀독 서식으로 대체된 부분이 있음 — 충돌 시 **§0과 메모리(`seldoc-output-format`·`input-ledger-format`·`inventory-api-rfm-search`)가 우선**.

## 0-A. 최신 세션 (2026-09-09) — ⭐새 세션은 여기부터·"이어서"로 재개

**오늘 한 일 = 라이브 전체실행(①)에서 터진 버그·차단 전면 수정 (커밋 순서)**:
`b16493b`(순위 사람속도 직렬모드) → `40f4513`(앱 시작시 좀비Chrome 전역정리 reap) → `fe4d1ee`(빈 사업자명 크래시 수정+계정 전체 격리) → `90c0713`(계정ID 병합=데이터손실 수정 + 시작전 입력검증) → `cfaacba`(로그인 차단 대응: 세션우선 2패스 + 서킷브레이커).

**수정 내역(전부 라이브 실증 또는 시뮬 검증)**:
1. **크래시**: 빈 사업자명 계정(seankim137) → 빈 시트명 `KeyError`로 ① 전체가 [5/35]에서 죽어 30계정 미수집. → 시트명 `.label`(사업자명 or 대표자명 or 계정ID) 폴백 + **계정 처리 전체를 try/except 격리**(한 계정 오류가 전체 안 막음). 라이브 재실행서 정해성 정상 수집 확인.
2. **데이터 손실**: 같은 계정ID가 여러 행에 흩어지면 파서가 별개 Account로 분리 → run_full이 첫 항목만 처리, 나머지 done-skip으로 상품 누락(dalbong1849 4상품중 3개 등). → `parse_input_list` **계정ID 병합**. 실파일 35행→**28계정·상품 79개 전부 보존**.
3. **시작 전 입력검증**(`validate_input_list`): 치명적(계정0·시트명충돌 등)=차단, 경고(빈 사업자명·상품0개)=진행. run_full 시작 시 호출. 실파일=치명적0·경고3.
4. **좀비 Chrome**: 앱 강제종료·크래시 시 남던 좀비 → `browser.reap_orphan_chrome()`가 **앱 시작 시 우리 프로필 chrome 전역 정리**(사용자 일반 Chrome 안 건드림).
5. **순위 사람속도 직렬모드**(`config.RANK_HUMAN_SERIAL=True`): 동시 fetch(버스트=봇신호) 대신 동시성1·간격0.7~1.8s. (③ 미검증=아침 IP)
6. **로그인 차단 대응**(핵심): Akamai 차단은 **로그인 POST에서만** 발생(데이터API·세션재사용 GET은 안 막힘). 반복 자동로그인이 IP 태움 → **세션우선 2패스**(세션 살아있는 계정 먼저 다 수집, 세션 만료는 대기열) + **서킷브레이커**(연속 Akamai차단 3회면 이후 로그인 생략). 메모리 [[login-block-session-first-circuit-breaker]].

**⏸ 재개 상태(다음 세션 최우선)**: 오늘 ①이 **9/28계정 수집 후 중단**(오전 반복실행으로 IP 플래그 → 로그인 차단, 앱 16/28에서 닫힘). **`output/쿠팡데이타분석_진행중.xlsx`(+.json)에 9계정 저장, 최종본 미생성.** 완료계정=WBpeak·luxsong8·sg0141n·wellbing1107·seankim137·plan_it·hk66597582·quietlab·roum0502. 날짜=2026-09-08, 새통계 모드.

### 다음 세션 "이어서" 절차 (쉰 IP=아침 권장)
1. **시작 클린**: 진행중 파일 보존됨·앱 미실행·좀비Chrome 0(이 세션 종료 시 정리함). 확인만: `Get-CimInstance Win32_Process -Filter "Name='chrome.exe'"` 우리프로필 0.
2. **앱 실행** `python ui/app_qt.py` (시작 시 reap 자동). 설정탭 → 입력엑셀 `D:\토탈셀러\셀독\토탈셀러_셀독 관리 대장 (3).xlsx` 열기(`[입력] 28계정` 확인) → 키 자동로드.
3. **① 판매수집** → 날짜 **2026-09-08**(진행중과 동일) → 팝업 **"이어서"** → 검증 통과 후 **완료 9계정 건너뛰고** 세션우선 2패스로 나머지 ~19계정. 로그에 `세션 만료 → 로그인 대기열`·`로그인 필요 계정 N개`·(차단 다발 시)`로그인 생략`·`완료 — 진행 N/28` 확인. 로그인 창 뜨면 사람이 직접.
4. 28계정 완주 시 최종본(`쿠팡데이타분석_통계.xlsx` + 스냅샷) 생성·진행파일 정리. 못 딴 계정 있으면 로그 `⚠ 로그인 못한 계정…` — 다음날 재실행 시 수집.
5. 이어서 **② 키워드선정**(로그인 불필요) → **③ 노출순위**(로그인 불필요, 직렬모드·아침IP).

### 남은 근본 과제
- **세션 keep-warm(A안, 미착수)**: 매일 가벼운 인증 GET으로 세션 유지 → 로그인을 거의 0으로 → 차단 원천 소멸. 세션 수명·갱신 엔드포인트 실측 필요. (서킷브레이커는 피해차단이지 완전수집 보장 아님)
- **③ 순위 라이브**: 아침 쉰 IP에서 직렬모드 실검증(오늘 IP 플래그로 미검증).
- **판매 -1(음수)** 관측 지속(복숭아·안전화 등) — 반품 순액 여부 단일일자 대조.

---

## 0. 이전 세션 요약 (2026-09-08 저녁)
이번 세션: **파이프라인 3단계 분리 재설계**(사용자 요청) + 서식 보완 + 순위 예외격리 + 차단회피. **커밋됨**: `6959b6e`(초기) → `af40d60`(예외격리·상품ID·차단회피·서식) → `afff41d`(3단계 백엔드) → `cd8e199`(UI 메뉴).

**핵심 — 3단계 독립 실행** (상세=메모리 `pipeline-3stage-separation`):
- **① 판매수집**(로그인): `run_full(keywords_off=True)`. 상품 발견·제목·**상품ID(vendorItemId)**·판매/노출/방문/재고. vid는 결과엑셀 **숨김시트 `_상품ID`**에 저장(`workbook.set_product_vids`/`product_vids`).
- **② 키워드 선정**(로그인 불필요): `pipeline.select_keywords_stage(naver, ai_key, grow)`. 최신 워크북 로드→상품별 키워드, **순위 조회 없음**(`select_keywords_light(measure_ranks=None)`). 키워드 있으면 스킵(사람 수동입력도 재사용).
- **③ 노출순위 조회**(로그인 불필요): `pipeline.track_ranks_stage()`. vid로 검색결과 매칭(`_vid_matcher`)→순위(최신 일자). **예외격리**(`_measure_safe`: browser 죽어도 공란·완주).
- **전체실행**(①→②③)은 `run_full` 유지. UI **app_qt·app.py 폴백 둘 다 버튼 4개**(①②③+전체). ⚠ app_qt 순위버튼 이름충돌(전체실행탭이 순위조회탭 `rank_btn` 덮어씀) → `track_btn`으로 수정.
- 순서: ① 먼저(상품발견 선행), ②③은 ①이후 순서무관.

**그밖에 이번 세션**:
- ✅ **재고현황 라이브 실증**: bf0621 화로테이블 재고 13(예상 일치). `tools/verify_login_discover_live.py bf0621`(3-tuple+재고출력로 복구).
- ✅ **버그수정 2건**: pipeline 로그인미완료 `return None,{}`→`None,{},{}`(3-tuple 오분류 방지, 실전 검증됨). verify_login_discover_live stale 2-tuple.
- ✅ **순위조회 예외격리**(`_measure_safe`): 순위 중 browser 죽음(`TargetClosedError`)이 판매수집·전체실행을 중단시키던 문제 제거(2026-09-08 라이브 크래시 실측 근거). **측정 실패(예외·차단)는 순위 공란 유지** — `set_keyword_rank(None)`의 `'-'`(미노출) 오기록 방지 위해 **측정된 키워드만 기록**(`track_ranks_stage`+`_process_account` 동결). 그래서 차단났던 순위도 **다음에 ③만 재실행하면 재조회**(`'-'` 박히면 `is_rank_filled=True`로 영영 스킵되던 버그 해결). 정밀 3단계 시뮬 `tools/simulate_stages.py`(18항목)가 발견·검증.
- ✅ **차단회피**: 동시 3→2·지터 400→800ms·**차단시 백오프 30초 재시도1회**. **라이브 확인: 백오프 작동하나 오늘 IP 심하게 플래그면 무력**(근본=하루1회·IP 휴식).
- ✅ **날짜지정 순위제외**(`skip_ranks`): 날짜 **직접지정** 실행=순위 제외(판매만·차단 접촉0), 어제(D-1) 자동=순위 포함(첫날 선정용).
- ✅ **EPIPE 크래시 조사**: 로그인창 사람닫힘→다음계정 전환시 Playwright 드라이버 EPIPE(driver→client 파이프, **Python 못잡음**). 재현 2회 실패(특수 타이밍 race — 추측 코드수술 안함). 방어=`browser.wait_for_login` blocked(Akamai) 무한대기 폐지→60초 grace 후 건너뜀. 안전판=크래시해도 진행중파일 재개(실증).
- ✅ **셀독 서식 재현·보완**(`workbook.apply_style`): 병합(제목A:G·지표블록A:B/C:F세로·키워드C:E가로)·팔레트(상품명 살구FBE2D5·G라벨 연파랑D9E9FA·키워드헤더 회색E8E8E8)·thin테두리·맑은고딕·#,##0. 보완: 비고=검색량색(회색), 계약상품=상품명색(살구), **상품 상하 굵은(thick) 구분선**(하단은 다음 빈행 top으로 — 병합 하위셀 border 유실 회피). ⚠ 서식파일 `셀독 판매 데이터_서식.xlsx`는 **한컴 셀**(openpyxl `IndexError`로 못읽음 → zip raw XML 파싱).
- ✅ **키워드 4개**(`KW_TRACK_N=4`).

### 🔬 라이브 검증 결과(2026-09-08 밤, 사무실) — 3단계 실행 실증
- **① 판매수집**: 계정 1 **(주)웰빙곳간 완전 성공** — 세션 재사용 로그인, 상품 39옵션 발견, 노출/판매/방문 지표, **재고현황 52옵션 조회**(로켓그로스 inventory API 라이브 OK), 세션저장(생존검증 True)·상품ID(vid) 저장·진행중 저장. **계정단위 격리 실증**: 이후 계정들 로그인 차단(Akamai)이 **다음 계정 진행을 안 막음**. ⚠ **오늘 IP 플래그로 자동제출 로그인이 `xauth login-actions/authenticate`에서 차단/정체** → 세션 재사용 계정만 수집됨(1/11 성공 후 중단). **다계정 수집은 세션 신선/IP 휴식(아침) 필요** — 예측대로.
- **② 키워드 선정**(로그인 불필요): **완전 성공** — 진행중 워크북(계정1) 대상, 고유상품 **22개 전부 키워드 기록·실패 0**, ~12.5분. 쿠팡 자동완성·네이버 연관·AI 핵심연관판정·점수압축(예: 68→6) 정상. (39옵션이 상품명 중복으로 22 고유상품)
- **③ 노출순위 조회**(로그인 불필요): **메커니즘 실증**(프라임+병렬 fetch·"50위 밖"과 차단 구분·**차단 감지→30초 백오프 재시도**·순차 폴백) — 단 **오늘 IP 플래그로 순위 데이터 무의미**(측정분 전부 "50위 밖", 곧 차단 다발). **저장 전 중단 → 순위 전량 공란 유지**(87키워드 filled 0) = **내일 아침 ③만 재실행하면 전량 재조회**되는 이상적 상태.
- ⚠ **관측된 함정(다음 세션 유의)**:
  1. **앱 2개 동시 실행 위험**: 사용자가 2번째 인스턴스를 수동 기동해 거기서 ③을 누름 → **②가 저장(계정단위 끝에 1회 `wb.save`)하기 전** 워크북을 읽어 조회대상 0개로 6초 만에 "완료"(오작동 아님, 순서 문제). GUI가 **실행 중 다른 단계/중복 인스턴스를 막도록** 개선 검토. **②③는 계정단위 끝에만 저장**하므로 중간 중단 시 그 단계 산출 미저장(설계상 정상, 인지 필요).
  2. **판매 -1(음수 판매건수)** 1건 관측(웰빙곳간 퀘르세틴…) — 반품 순액 음수 가능성, 단일일자 실측 대조 필요(추측 금지).
- **정리 상태(이 세션 종료 시점)**: 좀비 Chrome 0·앱 미실행·`쿠팡데이타분석_진행중.xlsx`에 계정1(①판매+재고+vid, ②키워드22, ③순위공란) 보존. **다음 세션: 아침 IP 휴식 후 ③ 재실행으로 순위 채우기 + 세션 신선한 다계정 ① 수집.**

### 🔎 차단 근본대책 조사·구현(2026-09-08 밤)
- **Wing 세션에 순위 공식데이터 있나? → 조사 완료(라이브 캡처, 계정1)**: **키워드별 순위(N위)는 Wing에 없음**(응답 `position`/`rank` 0 — 스크래핑 전용 지표). 키워드별 노출/클릭(`KEYWORD_DAILY`)은 **유료구독(Business Insights Pack 월5만원) 게이팅**(이 계정 미구독). 무료로 나오는 검색계열(vi-detail-search의 `srpClick`/`srpClickShare`, `traffic-insight` organic 노출)은 **미구독 계정에선 값이 게이팅(0)일 수 있음 — 사용자 실분석상 "유료"** → **무료 대체 경로 폐기**. ⚠ 인증 API 표면은 오늘도 계정1 정상(막힌 건 비로그인 검색·자동로그인 POST뿐). 메모리 [[wing-keyword-data-subscription-gated]].
- **근본원인 = IP·기기 평판**(아침 정상→오후 반복실행 후 차단). 근본레버=전용 깨끗한 IP·하루1회·영속 프로필(위조 금지라 우회 불가).
- **채택·구현: 순위 "사람속도 직렬 모드"**(`config.RANK_HUMAN_SERIAL=True`) — `organic_ranks_batch`가 **동시 fetch(버스트=봇신호) 대신 동시성1·요청간격 0.7~1.8s 무작위**로 조회. fetch라 요청당 ~0.3s로 **여전히 빠름**(22상품 ≈ 2~2.5분 예상). config 한 줄로 빠른 병렬 복귀 가능. `RANK_FETCH_JITTER_MIN_MS=700` 신설. pyflakes 0·simulate_stages 18/18·라이브 미검증(내일 아침 IP에서). (사용자가 선택 안 한 대안: 핵심키워드만 매일=88→22쿼리, 저빈도, 구독 정공법.)

### 다음 할 일
1. **🔬 사무실 라이브 검증(3단계) — ①②는 실증 완료(위 참조), ③ 순위는 IP 휴식(아침) 재실행 필요.** 전제=사무실(신뢰환경, 2차인증 없이 로그인). 절차:
   - **앱 실행**: `python ui/app_qt.py`. 설정탭 → 입력엑셀 열기(`D:\토탈셀러\셀독\토탈셀러_셀독 관리 대장 (3).xlsx`, 비번 자동저장) → 네이버·OpenAI 키 확인(credstore 자동로드).
   - **① 판매수집** 버튼 → 날짜 **어제(D-1)** → (마스터 없어 새 통계) → 로그인(세션재사용/자동입력, 2차인증만 창) → 확인: 상품 발견·판매/노출/방문·**재고(계약상품)**·상품ID 저장. 결과=`output/쿠팡데이타분석_통계.xlsx`.
   - **② 키워드 선정** 버튼(**로그인 불필요**) → 확인: 상품별 키워드 4개·검색량·**순위 공란**(②는 순위 조회 안 함).
   - **③ 노출순위 조회** 버튼(**로그인 불필요**) → 확인: 순위 기록. **오늘 IP 나쁘면 차단→공란이 정상**, 내일 ③만 재실행하면 재조회(예외/차단은 `'-'` 안 박고 공란 유지).
   - **결과엑셀** 열어 서식(병합·상품명 살구/G라벨 연파랑/키워드헤더 회색·상품 상하 굵은 구분선)·상품ID 숨김시트(`_상품ID`)·단계별 값 확인.
   - 확인 포인트: 단계 독립성, 예외격리(③ 차단나도 판매·키워드 보존), 재고현황, 셀독 서식. 로그=`output/run_log_*.log`. 좀비정리는 정상완료(exit0) 자동. 사전 검증 완료=정밀 시뮬 `tools/simulate_stages.py` 18/18.
2. **⚠ 미해결 실측 불일치(추적)**: 재고 API `salesStatistics.yesterdaySales.totalPageViews` vs vi-detail-search 노출/방문 — **단일일자 대조 필요**. 이번 7일합계 조회는 vi-detail-search 정상값(화로테이블 노출4074/방문3273) 반환 → 매핑오류보다 **익일반영 지연**([[coupang-sales-data-lag]]) 쪽. (추측 금지, D-2 등 실측)
3. (선택) 단일일자 수집 UX, 대량 실행 속도. (app.py 폴백 ①②③ 배선은 완료 — 커밋 86dc892)

### ⚠️ 운영 교훈
- **오늘(2026-09-08) IP 심하게 플래그**: 순위·**로그인 자동제출까지** Akamai Access Denied. 순위는 하루1회·IP 휴식 후. 3단계 분리로 순위 실패가 판매수집 안 막음(구조적 격리).
- **좀비 Chrome 정리**: 명령줄에 `remote-debugging-port`/`data\profiles`/`chrome-pipeline` 포함 chrome.exe만 kill(사용자 실제 Chrome=기본프로필 보존). 정상완료(exit0)면 스스로 정리. 캡처도구·앱 동시실행 금지(같은 프로필 충돌).

## 1. 목표(요약)
관리 쿠팡 판매자 계정들의 **상품별×일자별 지표**(노출순위 PC/모바일·노출건수·판매건수·방문자)를 수집하고,
**키워드 선정 → 순위 진단 → 노출제목 처방**까지 해서 통합 엑셀 1개(`쿠팡데이타분석_yymmdd_시분초.xlsx`)를 만든다.
비개발자 담당자가 각 PC에서 실행하는 **Windows 데스크톱 GUI**(기본 UI = **PySide6 `ui/app_qt.py`**; Tkinter `ui/app.py`는 폴백).

## 2. 지금 동작하는 것 (검증됨)
- **계정단위 end-to-end**(`pipeline.run_full`): 계정마다 [로그인(신선 세션)→판매분석 발견/지표→키워드→순위→진단·제목처방] 완결 후 다음 계정, 통합엑셀 누적 + 계정마다 중간저장 + 재개("이어서") 지원.
- **매일 통계(cross-day, 키워드 동결)**: 하루 1회 실행하는 시계열 통계. 단일 마스터 `output/쿠팡데이타분석_통계.xlsx`에 **날짜 컬럼만 누적**하고 **첫날 정한 키워드를 종료까지 동결**(재선정 안 함 → 순위 추세 비교 가능). `run_full(carry_forward=True)`=마스터 로드·동결·오늘 컬럼, `grow_keywords=True`=상한 `KW_MAX_TRACK=7`·하루 `KW_ADD_PER_DAY=2`개 **새 키워드만** 추가(기존 절대 제거 안 함). 완료 시 마스터 갱신 + 그날 스냅샷(`_통계_yymmdd.xlsx`). UI 팝업 3분기(크래시 이어서 / 마스터 있으면 기존추가·새통계 / 첫 실행). 상세=메모리 `daily-stats-keyword-freeze`.
- **판매분석 수집(데이터 API 직접조회, 사람 클릭 없음)**: `collector.fetch_sales_details`가 화면이 쓰는 **`vi-detail-search` API를 같은 로그인 세션에서 직접 POST fetch**(same-origin + `x-xsrf-token`=XSRF-TOKEN 쿠키). 실측확정·마스터 실값 대조 일치(2026-09-07). 지표: 노출=totalPageViews·판매=totalUnitsSold·방문=totalUniqueVisitor. 실패 시 로그 남기고 **옛 엑셀 다운로드로 폴백**(`download_report`+`parse_by_option` — 안전판, 라이브 확인됨). **함정: `_PAGE_SIZE`를 크게(200) 주면 서버 400 → 검증값 20 유지.** 상세=메모리 `sales-data-api-vi-detail-search`. 도구: 캡처 `tools/capture_sales_api.py`, 라이브검증 `tools/verify_sales_fetch_live.py`.
- **전체 노출제목 복원**: 리포트 '상품명'이 잘려와도(`…화로`처럼 '테이블' 누락) `collector._display_title`이 옵션명 첫 콤마 앞으로 복원 → `Product.display_title`(키워드 씨앗·제목처방 기준).
- **키워드 선정(핵심어 → 여러 방안 후보수집 → AI 최종선정, 페이즈A 완료)** — `kw_recommend.select_keywords_light(..., browser=)`:
  1. `kw_ai.analyze_product` → 용도·대표 core·**정체성 목록(identities)**·앵커(화로테이블=바베큐테이블=…, 구성부품 바베큐그릴·화로대 스탠드는 제외).
  2. **후보 4소스 합집합**(`_assemble_candidates`): ①앵커 네이버 연관(≥500) ②**쿠팡 자동완성**(`kw_suggest`, core·정체성 시드로 쿠팡 실수요 검색어, 네이버로 검색량 측정 ≥30) ③AI 조합생성(≥30) ④**네이버 2단계 확장**(1차 후보 검색량 상위 `KW_EXPAND2_N=6`개 재시드).
  3. `kw_ai.judge_keywords` → **핵심/연관/탈락** 1차 필터(형제 상품군·거대 일반어·타사 브랜드 탈락).
  4. **Keyword Score 압축 + 실노출 승격 + AI 최종선정(페이즈B)**: 후보를 **부분점수(관련성35·구매의도25·검색량20, 노출 제외)로 상위 `KW_SCORE_POOL_N=6`개 압축**(핵심 core 항상 포함) → **압축분만 쿠팡 오가닉 순위 측정**(`organic_ranks`) → 노출점수(15)·**전체 100점**(추세5는 데이터 없어 0, 만점95)·**등급 A/B/C/D** → `kw_ai.select_keywords`가 점수·등급·**쿠팡 실노출**·클릭·comp_idx·관련도 JSON을 종합해 **5개 우선순위 확정, 첫 항목=core**. `_ask temperature=0`(재현성).
  - **쿠팡 요청량 제어**: 후보 전량이 아닌 **압축 6개만** 노출 측정하고, 그 옵션별 순위를 워크북 순위에 **재사용**(재조회 없음 — `select_keywords_light(measure_ranks=)`→`rank_cache`→`_track_ranks_resume`). 재개(캐시 없음) 땐 직접 조회.
  - 자동완성·노출측정 모두 쿠팡 세션 필요 → `pipeline.run_full`이 rank_browser를 **키워드 선정 단계부터** 열어 자동완성·측정·순위 세션 공유.
  - 실측(화로테이블, `verify_keywords_live` — 노출측정 없이): 화로테이블·캠핑화로테이블·바베큐테이블·야외바베큐테이블·캠핑화로.
- **순위 진단**(`kw_recommend.keyword_in_title`/`diagnose_exposure`/`attack_priority`): 키워드마다 제목포함 × PC/모바일 순위 → **노출불가(제목미포함)/마케팅필요/양호**. 공략우선순위=검색량÷경쟁강도.
- **노출제목 처방**(`pipeline._prescribe_title` + `kw_ai.recommend_title`): 상품마다 현재제목·**권고제목(쿠팡 공식 상품명 기준: 옵션분리·나열금지·판촉어금지·50자)**·제목커버리지·권고검색태그.
- **엑셀 컬럼**(`workbook`): 키워드 행 = 월검색량·모바일비중·**월클릭수·네이버경쟁정도·키워드점수·등급**·연관도·제목포함·공략우선순위·진단(죽은 상품수·경쟁강도 컬럼 제거); 상품 행 = 현재/권고제목·커버리지·검색태그; 옵션 행 = 노출건수·판매건수·방문자건수; 노출순위 = 키워드×옵션 PC/모바일.
- **검증 도구(전부 실제 실행, 통과)**: `tools/simulate_pipeline.py`(파이프라인 3시나리오, 네트워크 없음), `tools/verify_prescribe.py`(제목복원·제목포함·진단·워크북 왕복 14/14), `tools/verify_keywords_live.py`(OpenAI+네이버+**쿠팡 자동완성**으로 키워드 선정 실증), `tools/verify_suggest_live.py`·`tools/verify_autocomplete_live.py`(쿠팡 자동완성 엔드포인트 실측), `tools/verify_offline.py`, `tools/verify_rank_live.py`(실제 Chrome 비로그인 순위).
- ✅ **사무실 라이브 전체실행 재검증(2026-09-07, "새로 시작", 3계정)**: end-to-end 파이프라인 전 구간이 실데이터로 정상 작동 확인. 결과 `output/쿠팡데이타분석_260907_112432.xlsx`(성공 2/3 계정).
  - 로그인: 3계정 모두 **세션 재사용(창 안 뜸)** — 사무실 신뢰환경. 세제곱(limws0652)은 세션 유효하나 D-1(9/6) 판매데이터 없음 → **정상 건너뜀**(대시보드 메뉴 정상 렌더로 세션 유효 확인, 세션문제 아님).
  - 명진상사(화로테이블·장난감총)·글로벌셀러창업연구소(안전화): 다운로드→파싱→키워드→순위→진단→제목처방 완결.
  - 키워드: 세 상품 서로 다른 카테고리인데 정체성 조합·롱테일(`탄피배출너프건` 실제 PC/모바일 35위 노출)·수요순 선정 일관 작동. 제목 잘림 복원(`…캠`→`캠핑 화로 테이블`)도 정상.
  - **진단 4분류 전부 실측**: 양호 / 노출됨(제목미포함·제목추가권장) / 마케팅필요(미노출) / 노출불가(제목미포함).
  - 계정별 중간저장·최종본 rename·진행파일 정리 정상. **좀비 Chrome 0** (실행 후 정리 확인).
  - ⚠ `vi-detail-search 25s 미수신` 경고는 데이터 없음과 무관(명진상사·글로벌은 경고 후 다운로드 버튼 발견됨) — 그냥 API 응답 대기 타임아웃이 25s로 짧을 뿐. 오탐이지만 무해.
  - **실시간 로그 미러링 추가**: `app_qt._append_log`가 GUI 콘솔과 동일 내용을 `output/run_log_yymmdd_hhmmss.log`로도 기록(실행별 1파일, `.gitignore`의 `/output/` 제외로 git 안 올라감). 세션 밖에서 로그 tail·검수용.
  - **2차 실행(14:27, 성공 3/3)에서 추가 관측된 특성 3건**:
    - ⚠ **순위 조회 간헐 차단**: `작업화` 1건이 Akamai에 `차단됨 — 공란` 처리됨(바로 다음 `안전화`는 정상). 전면 차단 아닌 간헐적 차단이고 '공란' 처리 로직은 정상. **원인=오늘 반복 실행(2회×상품마다 5키워드×PC/모바일)으로 IP 봇 플래그 상승**. → **하루에 반복 전체실행 자제**(순위 데이터 구멍·차단 유발).
    - **AI 키워드/제목 재현성 낮음**: 같은 상품·날짜인데 1차↔2차 키워드/권고제목이 상당히 다름(gpt-4o 비결정성). → ✅ **해결됨(페이즈A): `kw_ai._ask temperature=0`**.
    - **오가닉 순위 시점 변동성**: `탄피배출너프건` PC/모바일 35위(1차)→미노출(2차). RANK_SCAN_MAX=50 경계 근처 키워드는 조회 시점마다 노출/미노출 오감(쿠팡 검색결과 실시간 변동). 데이터 해석 시 감안.

## 3. 핵심 config 값 (`src/coupang_analytics/config.py`)
```
KW_AI_MODEL       = gpt-4o     # OpenAI(ChatGPT). credstore __openai__. _ask temperature=0(재현성)
KW_TRACK_N        = 5          # 상품당 추적 키워드 수(AI 최종선정 개수)
KW_GEN_N          = 40         # AI 조합 생성 후보 수
KW_EXPAND2_N      = 6          # 네이버 2단계 확장: 1차 후보 검색량 상위 몇 개를 재시드로 재조회할지
KW_TRACK_MIN_VOLUME = 30       # 배치 추적 검색량 하한(롱테일 살림). 추천 탭은 KW_MIN_VOLUME=500 밴드
KW_MAX_TRACK      = 7          # 통계 유지 중 상품당 추적 키워드 상한(첫날 KW_TRACK_N=5, 이후 발굴 추가 상한)
KW_ADD_PER_DAY    = 2          # '발굴 추가' 켠 날 상품당 하루 최대 추가 개수
KW_SCORE_POOL_N   = 6          # 페이즈B: 부분점수 상위 몇 개만 쿠팡 실노출 측정(요청량·IP제어, 6~7)
KW_SCORE_W_*      = 35/25/20/15/5  # 점수 가중: 관련성·구매의도·검색량·쿠팡노출·추세(추세는 데이터없어 0)
KW_GRADE_A/B/C    = 72/54/36   # 등급 경계(총점 95 만점 기준)
RANK_SCAN_MAX     = 50         # 오가닉 50위까지 스캔(속도). 밖(None)='50위 밖'(미노출 아님 — 뒤쪽 순위, rank_label)
RANK_PAGE_DELAY   = 1.0~2.5    # 페이지 간 지연(축소). KW_QUERY_DELAY=1.5~3.0. (병목은 페이지 로딩 ~20s — IP 스로틀링)
RANK_GOOD_THRESHOLD = 20       # 이 순위 이내면 진단 '양호'(노출점수 ≤20 구간 경계에도 사용)
```

## 4. 남은 작업 (우선순위)
> 키워드 선정 종합 개편 계획: **`~/.claude/plans/quiet-swimming-anchor.md`** (페이즈 A·B 완료, C 남음). 사용자 확정 방법론: 핵심어 AI추출 → 여러 방안 후보수집 → **AI 최종선정** → (쿠팡 실노출) → 상품명 개선.

1. ✅ **페이즈 B 완료(2026-09-07)** — Keyword Score 100점제(관련성35·구매의도25·검색량20·쿠팡노출15·추세5=데이터없어0) + 등급 A/B/C/D + **쿠팡 실노출 선정 승격**(부분점수로 6개 압축 → `organic_ranks` 측정 → AI가 종합해 최종5, 측정 순위는 워크북 재사용). comp_idx·clicks 되살려 점수·엑셀 반영, 죽은 상품수·경쟁강도 컬럼 제거. **사용자 결정**: 최종선정=**AI 유지**(점수는 입력지표), 압축=**6개(더 좁게)**. 상세=계획 페이즈B. **남은 것=사무실 라이브 로그 확인**.
2. ⭐ **페이즈 C — 시계열 양식·상품명**: 사용자 `_new_` 양식(`output/쿠팡데이타분석_new_260907_142714.xlsx` 참고 = 어제/7일전/30일전 순위·판매 델타 **가로 펼침**, 상품명(옵션포함)·검색키워드·일자별 지표)으로 `workbook` 확장. **사용자 1차 요청 = 일자별 판매량·노출건수만**(순위·검색량은 뒤로). 점수기반 상품명(`recommend_title`). **추세5점 = 여기서 시계열(어제/7일/30일 순위 델타) 생기면 되살릴 수 있음**.
3. **사무실 통합 라이브(페이즈 A 실계정 확인)**: "새로 시작" 전체실행 → 로그에서 `[자동완성]` 후보합류·AI 최종선정·재현성 확인. (자동완성·AI선정 자체는 `verify_keywords_live`로 실증 완료 — 이건 실계정 통합 확인용.)
4. **(보류) 리뷰수·평점·판매가·할인율 수집** — 상품 페이지 스크래핑(라이브 셀렉터 미검증). 기본 off·명시 로그, 순위조회 때 피기백.
5. **(보류) KIPRIS 상표 자동검증** — 권고제목 타사 상표 배제 정밀화.
6. **(참고) 네이버쇼핑 검색 API 2026-07-31 완전 종료** → 경쟁강도 소스 소멸(상세는 메모리 `naver-shopping-api-terminated`). `kw_shopping.py`는 죽은 엔드포인트, **네이버쇼핑 키 발급 금지**. 경쟁강도 대안은 페이즈 B(쿠팡 실노출 + `comp_idx`)로 흡수.

## 5. 반드시 지킬 제약 (상세는 CLAUDE.md)
- **🔒 로그인**: 실제 Chrome+CDP 자동입력만. HTTP 위장로그인/지문위조 **금지**. 브라우저 기본 숨김, 2차인증 등 사람 필요 시에만 표시. rank_browser와 로그인 브라우저 **동시 개방 금지**(sync playwright 1스레드 1개).
- **위탁 계정**: 인증번호 5회 오류 시 계정 잠김 → 낯선 환경(집) 반복 로그인 금지. **집에서도 세션 살아있으면 되지만 로그인 창 뜨면 중단**.
- **비밀번호**: DPAPI 이 PC 전용. git·출력물 평문 금지.
- **fallback 금지**(try/except pass·silent None). **응답 한국어.**
- **오류 수정은 추측 금지** — 진단로그+파일/이벤트 직접확인 후 실오류 근거로만(메모리 `fix-from-real-evidence`).

## 6. 실행 · 검증
```bash
cd D:\coupang-analytics
python ui/app_qt.py     # 기본 UI(PySide6). 설정→입력엑셀 열기(비번 자동저장)→키 확인→전체 실행
```
- **매일 운영**: 첫날=팝업 없이(또는 '새 통계 시작') 실행 → 마스터 생성·키워드 선정. **둘째날부터** 팝업에서 **"예(기존 통계에 추가)"** → 키워드 동결하고 오늘 컬럼만 누적. 키워드를 늘리고 싶을 때만 '새 키워드 발굴 추가' 체크(상한7·하루2).
  - ⚠️ 방법론/코드를 크게 바꿔 **키워드를 새로 뽑고 싶으면** '새 통계 시작'(기존 마스터는 `_통계_보관_*`로 자동 보관). 크래시 "이어서"는 그날 모드(동결/발굴) 그대로 재개.
- 로그인 창이 뜨면(세션 만료) 중단(위탁계정). 수집 대상일은 **어제(D-1) 이전**(당일 데이터는 익일 반영 — 메모리 `coupang-sales-data-lag`).
- 검증(네트워크 없음): `python tools/simulate_pipeline.py` · `python tools/verify_prescribe.py`
- 키워드 실증(OpenAI+네이버 실호출, 로그인 불필요): `python tools/verify_keywords_live.py "상품 제목"`
- 정적: `python -m pyflakes src/coupang_analytics/` (무결 유지)

## 7. 최근 세션 변경 요약 (무엇이 바뀌었나)
- (2026-09-10) **AI 프롬프트 경량화 + 호출 최적화**(사용자 2건 인계 중 ②; ①itemscout=로그인필수 유료SaaS라 드롭). **실호출량 재산정: 정상 운영일 AI=`recommend_title` 하나뿐(하루~79콜), ①~④는 새상품/발굴만**(동결). "3만콜" 전제는 ~400배 과대. 반영:
  - **프롬프트 5종 경량화**(`kw_ai.py`) — 사용자 초안 채택하되 **`identities`(정체성) 필수 복원**(2026-09-07 실측픽스 보호), `attributes` 신규 병기. 출력 JSON 스키마화: analyze `{core,use,identities,attributes,anchors}` / generate `{candidates}` / judge `{judged:[{k,label,match}]}` / select `{selected:[{k,role,priority}]}` / title `{title,primary_keyword}`.
  - **③ match(0~1) 채택, AI intent는 드롭**(네이버 실클릭 intent 유지 — 이중계산·토큰 방지). `judge_keywords`→`{kw:(tier,match)}`, `_score_relevance(tier,match)`가 티어 내 미세조정(핵심35×(0.7+0.3·match)). **④ role**(REP/SALES/GROWTH/DEFENSE)=`TrackKeyword.role`, **로그로 소비**(셀독 서식 컬럼 불변). `select_keywords`→`[(kw,role)]`.
  - **⑤ 제목 캐시**(`pipeline._log_diagnose`+`workbook.title_cache`/`set_title_cache`, `_상품ID` 숨김시트 col4/5 키워드서명·권고제목): 키워드 동일 시 `recommend_title` AI 재호출 생략 → **동결 상품 매일 79콜→≈0**.
  - **보류**: `①+②③` 통합(판정풀이 네이버·쿠팡 소스와 섞여 구조상 불가/첫날만 절감). `_assemble_candidates` 반환 8튜플(+attributes,matches).
  - **검증**: pyflakes·vulture 0 · simulate_pipeline(8시나리오)·simulate_stages(18/0) 통과 · `_ask` 목킹 파싱계약 14/14. ✅ **라이브 OpenAI 회귀검증 통과(2026-09-10, 쿼터 회복 후)**: 화로테이블 케이스 = 문서 베이스라인과 일치(화로테이블·숯불테이블·캠핑화로테이블·바베큐테이블 전부 핵심, 첫=REP) → identities 복원·role 태깅 정상.
  - (2026-09-10 후속) **정보성/형태단독어 배제 강화**(사용자 실증 지적 — 맥문동 상품에 '환'·'맥문동효능'·'폐에좋은음식'·'위에좋은음식'이 뽑힘: 사람이 살 때 안 치는 검색어). 근본원인=analyze가 `core=환`(형태 단독어)으로 잡아 네이버가 효능·음식 연관어를 쏟음. 3겹 수정: ①analyze — **형태·단위어 단독 금지**(환·정·세트 → '맥문동환' 형태 강제), identities에서 형태단독어·거대일반어 제외, attributes에서 핵심성분/수식어/수량 제외. ③judge — **대전제 '구매의도 있어야 CORE/RELATED'** 복원 + 정보성/증상성(효능·~에좋은음식·~증상) 명시 DROP. ④select — 정보성·형태단독어는 검색량 커도 선정 금지. **실증 결과**: 맥문동 → core=맥문동환, 최종 [핵심]맥문동환(REP)·볶은맥문동·[연관]맥문동·맥문동구매·볶음맥문동(정보성 전부 제거). 화로테이블 회귀 없음 재확인.
  - (2026-09-10 후속2) **니치 상품 자기정체성 후보 보호 + base 성분 포함**(사용자 실증 — 레몬버베나 상품에 '건강식품·건강기능식품·건기식' 거대일반어만 뽑힘). 원인 2개: ⓐ레몬버베나가 초니치라 네이버 앵커연관이 3개(레몬버베나추출물50·레몬버베나정19·레몬버베나추출물정18)뿐인데 검색량 하한(①≥500·조합≥30)에 다 걸려 **상품 자기 이름조차 후보에서 탈락→빈 결과** ⓑanalyze가 base '레몬버베나' 없이 긴 '레몬버베나추출물정'만 잡음. 수정: ①`kw_recommend._assemble_candidates` — **상품 자기 정체성(core+identities+anchors)은 검색량 하한 무관 항상 후보 포함**(네이버가 값 준 것만, `anchor_rel` 재사용). ②analyze — identities/anchors에 **핵심 성분 base와 주요 형태 모두 포함**(레몬버베나·레몬버베나추출물·레몬버베나정). 참고: 거대일반어(건강식품 등) 배제는 앞 커밋 judge 강화로 이미 동작(화면은 수정 전 산출물). **실증**: 레몬버베나 → 최종 레몬버베나추출물정(REP)·레몬버베나(월2320)·레몬버베나추출물·레몬버베나정(거대일반어 전멸). 맥문동·화로테이블 회귀 없음.
  - (2026-09-10 후속3) **AI 토큰 절감 ③ 후보 풀 축소**(사용자 "토큰 너무 빨리 소진" — 신규 전체실행은 상품당 judge가 최대 소비처, 맥문동 실측 후보 ~1120개 전량 판정). `KW_GEN_N 40→20`, `KW_JUDGE_POOL_N=30`: judge 전 후보를 상위 30으로 축소하되 **순수 검색량 컷 금지**(거대 broad 어가 상위 차지→DROP→중검색 상품어 밀어냄, 맥문동 6→2 붕괴 실측) → **상품 인접어(정체성 토큰 포함) 우선 → 검색량** 순 + 정체성 강제포함. 실측: 판정 1120→30(~97%↓) 품질 유지. ⚠️ **가장 큰 지렛대는 매일 carry_forward(동결) 운영**(첫날만 전체 AI, 이후 매일 ~0) — 코드 아닌 운영. ②모델 mini화는 사용자 미채택(보류).
- (2026-09-08) **출력 서식 = 셀독 전면 재설계**(사용자 `셀독 판매 데이터_서식.xlsx`): `workbook.py` 새로 작성 — **시트=사업자**, 상품 블록 **계약(로켓그로스)=판매량·방문자·노출량·재고현황 / 개인=전체판매량·전체노출량**, 키워드별 **노출순위(PC 단일)**·검색량, 일자 가로 누적. 상품구분은 vi-detail-search **registrationType(RFM/NORMAL) 자동판별**(collector). **모바일 순위 제외**(`RANK_INCLUDE_MOBILE=False`, `_set_mobile`/mobile 경로 **보존**). 순위=상품단위(옵션 통합). 점수/진단/권고제목은 서식 미기록·**로그로만** 제공. 키워드 동결·발굴(grow) 유지. config 구 서식 상수 제거, shop 파라미터 제거. **Phase2 남음=재고현황(rfm-inventory API)** — `tools/capture_inventory_api.py`로 캡처 후 `_fill_product_metrics` 재고 배선. 검증: simulate 4시나리오·verify_prescribe 27/0·pyflakes/vulture 0. 메모리 `seldoc-output-format`.
- (2026-09-08) **순위조회 병렬 fetch + AI/네이버 단축**(실측 근거):
  - 순위: `organic_ranks_batch`(검색 1회 프라임→병렬 fetch, 60/페이지=1페이지) — 6키워드 순위측정 ~72s→**~3s**(실측). 실패 시 순차 폴백. 메모리 `coupang-search-prime-then-fetch`.
  - 네이버: `related_keywords_multi` **배치 병렬**(ThreadPoolExecutor 4, 429 재시도, sleep 제거).
  - **AI judge 병렬화**: KW_JUDGE_BATCH 40→20 + 배치 동시실행(gpt-4o 유지, 품질 무손실) — judge 30s→~10s 예상(mini는 출력바운드라 효과 없어 미채택).
  - **차단 회피(정당한 rate-limit, 지문위조 아님)**: warmup이 Akamai 신뢰쿠키(_abck 등) 유지(개인화만 비움), 병렬 동시수 6→3, fetch 지터 400ms, 챌린지페이지 감지→선택자 6초 빠른실패. **단 근본은 하루 1회** — 과다 반복 시 Akamai 차단(오늘 6회+ 실행으로 오후 차단됨, 아침 첫 실행은 정상). 메모리 `coupang-search-prime-then-fetch`.
  - **단계별 타이밍 로그**(`_timed` → `[시간] …`)로 병목 실측: **judge=26.6s**(압도적), analyze 7.2s, generate 3.9s, select 1.2s, 네이버 각 0.7~3s.
  - → **judge·generate를 `KW_AI_MODEL_FAST=gpt-4o-mini`**로(분류·후보생성, 후보는 네이버·판정으로 걸러짐). analyze·select·recommend는 gpt-4o 유지. 품질 우려 시 config 한 줄로 되돌림. 예상 judge 26.6s→~6s.
- (2026-09-07) **순위조회 속도개선 + 로그/포맷 개선**(사용자 요청 6건):
  - #1 속도: 지연 축소(페이지 1~2.5s·키워드 1.5~3s) + **스캔 50**(사용자 선택, "50위 밖" 표기)·**모바일 유지**. **✅ 속도 원인 확정(2026-09-08 아침 실행, 구간 타이머)**: 정상시 goto ~1.5s·셀렉터 ~0.1s → **3계정 ~3분 20초**(어젯밤 ~23분은 goto가 ~20s로 튄 **환경적 지연**, 코드 아님 — 회복됨). 타이밍 로그는 이제 **goto/셀렉터 >5s일 때만** `[느림]`으로 경고(평상시 조용). **✅ 병렬 fetch 순위조회 구현·실증(2026-09-08, `diag_search`)**: 콜드 fetch 는 Akamai 403 → **검색 1회 네비로 프라임 후 병렬 fetch**(3키워드 1.3초, 60개/페이지=1페이지). `rank.organic_ranks_batch`(프라임-재시도-폴백), `_measure` 배치 closure, `select_keywords_light` 일괄 측정. 실패 시 순차 폴백. 상세=메모리 `coupang-search-prime-then-fetch`. 도구 `tools/diag_search.py`·`tools/verify_rank_fetch_live.py`. `[노출측정] … 노출순위`(최상위→노출순위), 상품 로그에 그날 노출/판매/방문, 권고제목 브랜드 맨앞 유지·쿠팡 가이드 강화(kw_ai `_TITLE_SYSTEM`). ⚠️ **리소스 차단은 도입했다 되돌림** — `browser.goto`가 이미 `domcontentloaded`라 이미지 로드를 안 기다려 이득 없이 가로채기 오버헤드만 늘었음(실측 개선 미미). **라이브 진단(2026-09-07)**: 결과는 정상(화로테이블 여전히 1위), 병목은 **쿠팡 검색 페이지 로딩 ~20s/페이지**이고 스캔 50이 100과 시간 비슷 → **오늘 반복 실행으로 IP 스로틀링** 정황. 근본 가속은 검색 JSON API(캡처 hang은 새 프로필 탓 추정 — 재시도 시 기존 rank 프로필 사용) 또는 **하루 1회 실행(휴식된 IP)**. 검색은 캡처 미완이라 SSR/API 여부 미확정.
  - #2 로그 제목 잘림 제거(전체 표시). #3 로그 타임스탬프에 1/60초 프레임 추가(`app_qt`). #4 `collector.discover`가 쿠팡 라이브 판매상품 제목(API productName)을 로그에 표시(입력 파일명 무시 명시). #5 `kw_suggest.collect_suggestions`가 후보를 개수만이 아니라 **목록으로** 로그.
  - #6 포맷=현행(long) 유지 + **가독성 서식**(`workbook.apply_style`: 헤더 강조·고정(F2), 상품 구분선, 상품메타 음영, 정렬, 너비) — 최종본에만 적용(pipeline finalize). 미리보기 `output/쿠팡데이타분석_통계_가독성미리보기.xlsx`.
- (2026-09-07) **판매분석 수집 = 데이터 API 직접조회로 전환**(사람 클릭 제거): `collector.fetch_sales_details`/`_parse_vendor_items`/`SalesFetchError` 신설, `discover`가 직접 fetch 우선 + 엑셀 다운로드 폴백. `tools/capture_sales_api.py`로 실물 캡처 후 `vi-detail-search` 스키마 확정(메모리 참조). ✅ **라이브 검증됨(2026-09-07 gbseller808, `tools/verify_sales_fetch_live.py`)**: fetch 200·XSRF·파싱 실값 일치(250→노출3/방문2, 260→노출1/방문1). **함정: `pageSize` 크게(200) 주면 서버 400 → 검증값 `_PAGE_SIZE=20` 유지(페이지네이션으로 커버).** 엑셀 폴백(`download_report`+`parse_by_option`)은 안전판으로 유지 — 멀티페이지·다계정 무사 확인 후 제거 가능. ⚠️ `tools/verify_offline.py`는 Phase A 스테일(select_track_keywords)로 ImportError — 별도 태스크로 분리(이번 작업 무관).
- (2026-09-07) **순위 표현 구분**: `None`(스캔 상한 밖)을 "미노출"이 아니라 **"{RANK_SCAN_MAX}위 밖"**으로(`rank_label`). 진단: 제목미포함→`노출불가(제목미포함)`(진짜 미노출) / 제목포함+스캔밖→`마케팅필요(N위 밖)`. **RANK_SCAN_MAX 50→100**(사용자 기준).
- (2026-09-07) **매일 통계·키워드 동결(cross-day)**: `run_full`에 `carry_forward`·`grow_keywords` 추가. 단일 마스터 이어쓰기(날짜 컬럼 누적) + 첫날 키워드 동결 + 상한(7)·하루(2) 발굴 추가. `_master_path`/`_snapshot_path`/`master_exists`, `_save_progress`/`resumable_progress`에 carry·grow 플래그, `_account_keywords(grow=)`(동결/발굴), `workbook.add_product_keywords`, `select_keywords_light(exclude=)`, `_record_track` 헬퍼. UI(app_qt·app.py) 3분기 팝업 + '발굴 추가' 옵션. 완료 시 마스터+스냅샷 저장. 검증: `simulate_pipeline` 시나리오4(동결·누적·발굴) 추가.
- (2026-09-07) **페이즈 B = 선정 지능화**(계획 `~/.claude/plans/quiet-swimming-anchor.md`):
  - `kw_recommend`: Keyword Score(`_keyword_score`/`_partial_score`/`_score_*`/`_grade`/`comp_from_idx`) 신설. `select_keywords_light`를 **부분점수 압축(KW_SCORE_POOL_N=6) → 압축분만 실노출 측정(`measure_ranks` 콜백) → 전체점수·등급 → AI 선정** 구조로 재작성. `TrackKeyword`에 clicks·comp_idx·score·grade·exposure_best·ranks_pc/ranks_mobile 추가(products·comp 제거).
  - `kw_ai.select_keywords`: 프롬프트에 **점수·등급·쿠팡 실노출** 지표 추가(노출 좋은 밀착 키워드 우대).
  - `pipeline`: `_account_keywords`가 측정 콜백(`organic_ranks`) 구성 + 신규 지표 기록 + **rank_cache 반환**. `_track_ranks_resume(rank_cache=)`가 **선정단계 측정 재사용**(재조회 없음, 재개 땐 직접 조회). 공략우선순위=`comp_from_idx` 반영.
  - `config`: `KW_SCORE_*`/`KW_GRADE_*` 추가. SUPP_METRICS에 `월클릭수·네이버경쟁정도·키워드점수·등급` 추가, 죽은 `상품수·경쟁강도` 제거.
  - 검증: pyflakes/vulture 0, `simulate_pipeline` 3시나리오(점수·등급·구매의도 기록 확인), `verify_prescribe` 21/21(점수·등급·노출·comp_from_idx 단위검증). **남은 것=사무실 라이브 통합 확인**.
- (2026-09-07) **키워드 선정 개편 = 페이즈 A**(계획 `~/.claude/plans/quiet-swimming-anchor.md`): 구조를 **핵심어 AI추출 → 여러 방안 후보수집 → AI 최종선정**으로.
  - 신설 [kw_suggest.py](src/coupang_analytics/kw_suggest.py): **쿠팡 자동완성**(엔드포인트 `www.coupang.com/n-api/web-adapter/search?keyword=` — 실측확정, 반환=쿠팡 인기순) 후보 수집. rank_browser 세션에서 직접 fetch(same-origin, Akamai 쿠키 실림).
  - `kw_recommend._assemble_candidates`에 **후보 4소스**(앵커연관 + 쿠팡자동완성 + AI조합 + 네이버 2단계확장 `KW_EXPAND2_N=6`) 합류. **최종선정을 수요순 규칙(select_track_keywords 폐기)에서 AI 종합판단(`kw_ai.select_keywords`)으로 교체** — 후보군 지표(검색량·클릭·comp_idx·관련도)를 AI가 보고 5개 우선순위 확정(첫 항목=core).
  - `kw_ai._ask` **temperature=0**(재현성 — HANDOFF 옛 §4-6 개선항목 해결). `pipeline.run_full`이 rank_browser를 **키워드 선정 단계부터** 개방(자동완성·순위 세션 공유).
  - 검증: pyflakes/vulture 0, `simulate_pipeline` 3시나리오, [verify_keywords_live.py](tools/verify_keywords_live.py)(자동완성 포함 라이브 실증 통과), [verify_suggest_live.py](tools/verify_suggest_live.py)·[verify_autocomplete_live.py](tools/verify_autocomplete_live.py).
  - **남은 검증**: 사무실 전체실행으로 통합 라이브(자동완성 후보 합류·AI선정 로그 확인). **페이즈 B**(Keyword Score 점수제·실노출 선정 승격), **페이즈 C**(일자별 시계열 양식) 미착수.
- (2026-09-07) **실시간 로그 미러링**: `app_qt._append_log`가 GUI 콘솔 로그를 `output/run_log_*.log`로도 기록(§2 참조).
- 키워드 방법론 대개편: 토큰→AI 앵커→**용도+core+정체성**; 판정 이진→**핵심/연관/탈락**; 씨앗 잘림 복원; **조합생성+검색량 하한 30**으로 롱테일 회복; 선정 **수요순**(니치우선 폐기); 화로대(스탠드)≠테이블 구분.
- 신규: 순위 **진단**(제목포함×순위), **제목 처방**(쿠팡기준 권고제목·커버리지·검색태그), 엑셀 컬럼 확장.
- 다운로드: 계정별 격리 폴더 + 파싱후 즉시삭제(충돌·PermissionError 해결). report.py 워크북 핸들 close.
- 로그: 모든 줄에 `[YYYYMMDD_HHMMSS]` 타임스탬프(`app_qt._append_log`).
- 속도: KW_TRACK_N 8→5, RANK_SCAN_MAX 100→50.

## 8. 겪은 함정 (반복 금지 — 핵심만; 전체는 CLAUDE.md §⚠️)
1. 로그인 완료 판정 = `authenticated()`(윙 대시보드 URL + `KEYCLOAK_IDENTITY` 쿠키) **둘 다**. `seller-uid` 단독·URL 단독·폴더존재 판정 금지.
2. Playwright sync는 한 스레드 1개 — rank_browser는 로그인 브라우저 닫힌 뒤 계정별로 개방.
3. 포트 고정 재사용 금지(`_free_port()`), `__exit__`에서 `_kill_tree()`로 좀비 Chrome 방지.
4. openpyxl `read_only`는 `.close()` 필수(안 하면 다음 계정 파일잠금 — 이미 `report.parse_by_option`에서 close + 폴더 즉시삭제).
5. 판매분석 당일 데이터는 익일 반영 — 당일 조회 0행은 정상(D-1 이전으로).
6. "이어서" 실행은 옛 키워드 재사용 → 방법론 바꾼 뒤엔 "새로 시작".
