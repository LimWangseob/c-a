---
name: pipeline-3stage-separation
description: 수집 파이프라인 3단계 분리 — ①판매수집(로그인) ②키워드선정 ③순위조회(②③ 로그인불필요·순위 예외격리)
metadata: 
  node_type: memory
  type: project
  originSessionId: ce978d95-b706-416b-80ab-fa6930e1cbcc
  modified: 2026-09-08T13:13:24.473Z
---

수집을 **3단계 독립 실행**으로 분리(2026-09-08). 이전 monolithic `run_full`(계정마다 로그인→판매→키워드→순위를 한 묶음)은 순위 차단/크래시가 판매수집까지 중단시켜서 갈랐다.

- **① 판매수집**(로그인 필요): `run_full(keywords_off=True)`. 상품 발견·제목·**상품ID(vendorItemId)**·판매/노출/방문/재고. vid는 결과엑셀 **숨김시트 `_상품ID`**에 저장(`workbook.set_product_vids`/`product_vids`). 키워드·순위 없음.
- **② 키워드 선정**(로그인 불필요): `pipeline.select_keywords_stage(naver, ai_key, grow)`. 최신 워크북 로드→상품별 키워드 선정, **순위 조회 없음**(`select_keywords_light(measure_ranks=None)`). 키워드 이미 있으면 스킵(사람이 미리 입력해둔 것도 재사용). 쿠팡 자동완성(비로그인)만 접촉.
- **③ 노출순위 조회**(로그인 불필요): `pipeline.track_ranks_stage()`. 상품ID(vid)로 검색결과 매칭(`_vid_matcher`, product 객체 없이)→순위 기록(워크북 최신 일자). **예외격리**(`_measure_safe`: browser 죽음/차단도 공란·완주). **측정 실패는 `'-'`(미노출) 오기록하지 않고 공란 유지 — 측정된 키워드만 기록** → 차단났던 순위도 ③ 재실행 시 재조회(`'-'` 박히면 `is_rank_filled`로 영영 스킵되던 버그 해결, 정밀 시뮬 `tools/simulate_stages.py` 발견).
- **전체실행**(①→②③ 통합)은 `run_full` 유지. UI **`app_qt`·`app.py` 폴백 둘 다 버튼 4개**(①②③+전체). (전체실행 탭 순위버튼은 `track_btn` — 순위조회 탭 `rank_btn`과 이름 구분).
- 순서: **① 먼저**(상품·vid 발견 선행 — ②는 제목, ③은 vid 필요), ②③은 ①이후 **순서무관**.
- ②③은 `_load_latest_wb`(마스터 우선, 없으면 진행중)로 결과 워크북을 읽어 동작. 워크북 순회 헬퍼 `products_of`/`latest_date`/`account_sheets`.

**Why:** 순위조회는 로그인 불필요(비로그인 쿠팡 검색)인데 monolithic이라 순위 차단/크래시가 로그인 판매수집까지 죽였다(2026-09-08 라이브 `TargetClosedError` 실측 — 6상품 연속 순위차단 후 rank_browser 사망→전체 중단). 분리로 순위 실패가 판매 안 막고, 순위는 IP 좋을 때 ③만 독립 재시도한다.
**How to apply:** 매일 **① 판매수집**(사무실 로그인, 날짜지정)→**② 키워드**(첫날/신상품만, 로그인불필요)→**③ 순위**(IP 휴식 좋을 때, 로그인불필요). 사람이 ② 후 결과엑셀에서 키워드 검수·수정하고 ③만 돌려도 된다. 관련 [[seldoc-output-format]] [[coupang-search-prime-then-fetch]] [[coupang-session-short-lived]].
