---
name: coupang-search-prime-then-fetch
description: 순위조회 가속 — 검색 1회 네비로 Akamai 프라임 후 나머지 키워드는 병렬 fetch(렌더 없이)
metadata: 
  node_type: memory
  type: reference
  originSessionId: e9438a2f-e201-48d4-bf71-5cdf2500b598
  modified: 2026-09-14T06:19:44.832Z
---

쿠팡 오가닉 순위조회를 대폭 가속하는 검증된 방식(`rank.organic_ranks_batch`, 실측 diag_search 2026-09-08):

- **콜드 fetch 는 Akamai 403**(챌린지 `sec-if-cpt-container`) — `fetch('/np/search?q=')`를 바로 하면 상품 0개.
- **검색 페이지를 1회 실제 네비게이션(`browser.goto`+wait_for_selector)하면 Akamai 통과**(_abck 유효화). 그 뒤엔
  **다른 키워드도 same-origin `fetch`로 결과(HTML)가 온다**(실측 T3: status 200, 상품 60개, 1.2초).
- **병렬 fetch(Promise.all)로 여러 키워드 동시** — 실측 T5: 3키워드 총 **1.3초**(현행 네비 ~15초/키워드 대비 급가속).
- **검색 1페이지 = 상품 60개** → 스캔 50은 **1페이지면 충분**(페이지네이션 불필요, page=2 fetch는 0/불안정).
- 검색결과는 **SSR**(네비 후 DOM/프라임후 fetch HTML에 상품 있음), 별도 상품 JSON API 없음(XHR은 Akamai 센서·로깅뿐).

**차단 회피(2026-09-08 실측 — 하루 6회+ 반복 실행 시 Akamai가 fetch·네비 둘 다 차단, 아침 첫 실행은 정상):**
정당한 rate-limiting만(지문위조 금지 준수) — ①warmup이 **Akamai 신뢰 쿠키(_abck·bm_sz·ak_bmsc·bm_sv)는 유지**하고
개인화만 비움(매번 새 방문자 되어 재검증→차단되는 것 방지) ②병렬 동시수 `RANK_FETCH_CONCURRENCY=3`(버스트 완화)
③fetch 전 무작위 지연 `RANK_FETCH_JITTER_MS=400` ④챌린지 페이지(`sec-if-cpt-container` 등) 감지 시 RankBlocked로
빠른 종료(선택자 타임아웃 6초). **그래도 근본은 하루 1회 실행** — 과다 반복하면 어떤 코드로도 Akamai 차단됨([[coupang-session-short-lived]]).

**★차단 = Akamai 동적 복합 Bot Score(콜드/웜은 한 변수일 뿐 — 2026-09-14 session_events 실측):** 처음엔 "시크릿(콜드)=차단·일반(웜)=통과" 스샷을 보고 "콜드=항상 차단"으로 단정했으나 **틀림**. session_events 실측이 반박: `rank_challenge`(순위차단) 일별 = 09-09:5 → **09-10:21(피크)** → 09-11:0 → 09-12:0 → 09-13:0(+어젯밤 304검색 무차단). 즉 **같은 웜 툴도 09-10엔 21회 차단, 09-11부턴 304검색도 무탈** → 방식(콜드/웜)이 결과를 단독 결정하지 않음. 진짜 변수 = **그 시점 IP의 누적 점수**(툴 자동 스크래핑 **볼륨/최근성**이 크게 좌우 — 09-10 대량스크래핑이 피크 유발) + 세션쿠키신뢰 + 패턴. **오늘 대조 실측**: 콜드(시크릿)=Access Denied·웜(_PROFILE)=통과 → 지금 이 IP는 "콜드는 못 버티고 웜은 버티는 경계구간". **사용자 지난주 시크릿 통과**=그땐 IP점수 낮았음(수동 개인브라우저라 툴 로그엔 없어 그 시점 직접측정 불가·단정 안 함). **함의: IP점수는 볼륨 줄이면 1~2일 내 회복**(09-10피크→09-11 0) → 간격(45~75s)·서킷브레이커로 볼륨 낮추면 사무실 웜 프로필로 통과 가능. 확인은 평소(웜) 브라우저로. [[login-block-session-first-circuit-breaker]](복합 Bot Score·N회 임계치 단정 금지 원칙과 일치)

**⚠ 기본값 변경(2026-09-09 `e9dcc9c`): 이제 기본은 병렬 fetch가 아니라 직렬 네비게이션.** 샵마인 비교로 확정 — 차단 유발원은 로그인이 아니라 **공개검색 반복 스크래핑**(샵마인은 Wing만 접속, 순위 스크래핑 안 함 → 무탈). 그래서 순위는 '사람이 검색창을 하나씩 치듯' 안전하게: `config.RANK_NAV_SERIAL=True`(기본)면 `_measure`가 `organic_ranks`(goto) 순차 + 검색 간격 `RANK_NAV_DELAY_MIN/MAX_SEC`(현재 45~75s). 병렬 fetch(이 문서 방식)는 `RANK_NAV_SERIAL=False`일 때만(빠르나 봇틱, 별도 깨끗한 IP에서만 권장). 차단(RankBlocked) 감지 시 `_RANK_HALT`로 **이번 실행 순위 전면 자동중단**(rank_ok/rank_empty/rank_challenge를 session_events에 관측 기록) + track_ranks_stage 상품마다 저장 → **당일 재실행 시 남은 것부터 이어서**(is_rank_filled). **운용 권장: 순위는 별도 IP(폰 핫스팟)·주1~2회** — 순위가 막혀도 Wing 로그인/수집 IP는 무사(격리). 상세 [[login-block-session-first-circuit-breaker]].

**Why:** 순위조회가 네비게이션 렌더로 키워드당 ~15초 → 병렬 fetch로 배치당 ~1.3초(단 봇틱 → 기본은 안전한 직렬 네비).
**How to apply:** `organic_ranks_batch` = ①병렬 fetch 시도 → ②전부 비면 1회 프라임(네비) 후 재시도 → ③그래도 0이면
`RankBlocked`로 **순차 폴백**(안전). 프라임은 세션당 사실상 1회(_abck 유효 동안 재사용). 모바일은 mobile UA로 fetch.
관련: [[sales-data-api-vi-detail-search]](판매도 same-origin fetch) · [[login-policy-real-browser-only]](정식 방식) ·
파싱/광고제외/매칭은 순차 `organic_ranks`와 동일 로직 재사용.
