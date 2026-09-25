---
name: semi-auto-rank-and-exposed-name
description: 반자동 순위조회(사람이 검색·앱이 화면만 읽음=차단회피) + 계약상품명을 검색결과 정확 노출명으로 갱신(vid 앵커로 시계열 키 안정). 2026-09-11 구현·검증
metadata: 
  node_type: memory
  type: project
  originSessionId: fd9529df-6f22-4998-bfda-be5db28b97c5
  modified: 2026-09-14T00:00:00.000Z
---

**반자동 순위조회 = 정확등수 차단 난제의 실질 해법**(2026-09-11 구현). 자동(현행)과 반자동을 UI에서 분리:
- **자동**: 앱이 비로그인 검색으로 순위 조회(현행, Akamai 차단 제약 그대로).
- **반자동**: 앱이 **보이는 Chrome 창**을 띄우고 키워드를 로그로 안내 → **사람이 직접 그 창의 쿠팡 검색창에 입력·검색** → 앱은 그 결과 화면 DOM만 읽어(`parse_serp_rank`, 네비 0) 저장 vendorItemId로 순위 산출·저장. **우리가 자동 네비게이션을 안 하므로 봇차단이 원천적으로 안 생김 → 사무실 밖에서도 검증 가능.** [[session-handoff-exact-rank-required]] [[rank-antiblock-circuit-breaker]]

**구현 위치**: `pipeline.track_ranks_stage(semi=, should_stop=)` + `_track_ranks_semi`/`_wait_user_search`(q 일치·상품존재 폴링, 타임아웃/중지 시 공란=다음에 이어서). `rank.parse_serp_rank`(네비 없이 현재 SERP만 파싱). UI(app_qt·app)에 `③ 순위(자동)`/`③ 순위(반자동)`/`반자동 중지` 버튼(반자동은 `threading.Event`로 중지). 재개(`is_rank_filled`)·상품별 저장 골격 재사용.

**계약상품명 = 검색결과 정확 노출명으로 갱신**(요구2). 순위 매칭 시 그 항목의 실제 노출명을 회수(`organic_ranks(matched_out=)`)해 `wb.set_display_name`으로 표시명 교체. **상품 정체성을 vendorItemId에 앵커**해 이름이 바뀌어도 시계열 키가 안 깨짐: `set_display_name`=헤더행 C셀 값+인메모리 키(_metric_row/_kw_row/_vid_row)+숨김시트 상품명만 이동(행/병합 불변). `resolve_block_name(biz, vids)`로 ①판매수집이 매일 다른 발견명을 넘겨도 vid로 기존 블록을 찾아 재사용(중복 블록·시계열 단절 방지). `_process_account`는 상품마다 `pname = wb.resolve_block_name(...) or product.name` 사용.

**철회**: "계약상품명 하단에 (등록상품ID) 표시" 요구는 철회됨 — 순위조회는 이미 숨김시트 vendorItemId로 매칭하므로 보이는 ID 불필요(사용자 확인).

**⚠️ 반자동 운용 함정(2026-09-11 실측)**: 사용자는 **반드시 앱/스크립트가 자동으로 여는 그 Chrome 창**(쿠팡 홈이 저절로 뜨는 창)에서 검색해야 한다. 평소 쓰던 다른 Chrome에 치면 그 창은 우리 CDP 컨텍스트가 아니라 영영 감지 안 됨(로그가 "입력 대기 중"만 반복). `_wait_user_search`는 `browser.context.pages` 전 탭을 스캔하고 `_search_q`가 `?component=&q=…` 형식을 파싱한다(진단으로 확인: 뜬 창 검색 시 context.pages에 /np/search URL 즉시 잡힘).

**인식실패 진단·수정(2026-09-11 라이브 재현)**: 기계(q매칭·`extract_items` 셀렉터 `li[class*='ProductUnit_productUnit']`·`parse_serp_rank`)는 **정상**(warmup 후 실측 60개 추출·순위 산출 확인). "인식 못 함"의 진짜 원인은 **q는 일치하는데 `extract_items`가 빈 경우**(쿠팡 차단/권한없음 페이지 "사용권한이 없습니다"가 사람 화면에 뜸, 또는 로딩 지연/네비 중 "Execution context destroyed")를 예전 코드가 구분 못 하고 무조건 "안내 키워드로 검색하세요"라고 떠서(+예외 `except: pass`로 원인 숨김) 올바로 검색한 사용자가 오해한 것. **수정**: `_wait_user_search`가 상황별 안내(차단페이지→새로고침/대기 안내 `_looks_blocked`, q불일치→안내키워드, 없음→입력대기)를 주고 extract 예외 사유를 로그에 노출. ⚠️ 자동 goto는 warmup(신뢰쿠키 유지) 없이 콜드면 즉시 "사용권한 없음"으로 차단됨(반자동은 사람이 in-page로 검색해 통과).

**⭐stale URL 버그 = "인식 못 함"의 실제 주범(2026-09-11 라이브 앱 진단 확정)**: `connect_over_cdp` 장기 연결에서 **사람이 창에서 직접 검색하면 Playwright 가 그 네비게이션 이벤트를 놓쳐 캐시 `pg.url` 이 이전(홈) URL 로 고착**된다. 그러면 `_search_q(pg.url)`=None → 앱이 검색을 아예 못 보고 "입력 대기 중"만 반복. **증거**: 실행 중 앱은 "입력 대기 중"인데, 같은 Chrome(포트 확인 후)에 **별도 프로세스로 CDP 연결하면 `contexts[0].pages`에 최신 q 가 정상적으로 보였다**(예: q='홈짐매프'). 진단법: chrome 프로세스 커맨드라인에서 `--remote-debugging-port`/`--user-data-dir` 추출 → `curl /json` 또는 별도 `connect_over_cdp` 로 실제 탭/q 확인(앱 방해 없음, 읽기전용). **수정**: `_live_url(pg)`=렌더러 `location.href` 직접 evaluate(캐시 대신, 실패 시 pg.url 폴백) + `_all_pages`=모든 컨텍스트×탭 순회. extract_items 는 원래 라이브 DOM 이라 무관. ⚠️ 함정2(동시 확인): 사용자가 **안내 키워드와 다른 말**을 검색하면(예 「홈짐매트」 안내인데 '홈짐매프' 오타/'바닥소음방지매트') 당연히 매칭·반환 안 됨 — 새 코드는 이 경우 "지금 열린 검색결과:'X'(안내 키워드로 검색)"로 정확 안내. **코드 반영 후 앱 재시작해야 적용**.

**⭐자동검색(Enter까지 자동) 옵션 도입 — 사용자 명시 요청(2026-09-11)**: 사용자가 "클릭도 앱이 하게, 손 안 대게" 요청 → 반자동 창(사람이 쓰던 신뢰 세션)에서 앱이 키워드 자동입력 후 **Enter(사이트 JS 검색=사람 조작에 가깝게)까지 자동** 실행하고 결과 기록. `config.RANK_SEMI_AUTOSUBMIT=True`(기본). ⚠️ **이는 "사람이 직접 검색" 원칙의 사용자 승인 하 완화**임 — 자동 제출은 Akamai 봇탐지·위탁계정 플래그 위험이 있어 안전장치 필수로 넣음: 키워드 간 사람속도 간격(RANK_NAV_DELAY_MIN/MAX_SEC = **45~75s**, 2026-09-14 실측 하향 — 이전 25~50/90~150 기록은 폐기 [[rank-antiblock-circuit-breaker]]), 결과 완전로드 대기(`_wait_results_loaded`=q일치+readyState complete+상품존재, `RANK_SEMI_AUTO_WAIT_SEC=40`). **차단 대응은 즉시 하드중단이 아니라 쿨다운-재개(2026-09-11 이후 현재)**: 연속 미감지/차단 `RANK_SEMI_AUTO_MAX_MISS`(3)회 → **긴 쿨다운(`RANK_SEMI_COOLDOWN_SEC=1800`=30분) 후 자동 재개**, 재개 후 1개라도 측정되면 카운터 리셋. 진전 없는 쿨다운이 `RANK_SEMI_COOLDOWN_MAX`(4)회 연속이면 그때 당일 중단(IP 회복불가 판단·위탁계정 잠금방지). 확정 접근차단 페이지("사용권한 없음")는 즉시 미스=MAX로 단축. 중단분은 공란→다음 실행이 이어서.

**⚠ 간격 로직(2026-09-14 개선)**: 검색 간 대기는 `time.sleep`(비중단)에서 **`_interruptible_sleep`로 바꾸고 '검색 앞'으로 이동**(`measured_any` 게이트) → 대기 중 '반자동 중지' 즉시 반응 + **첫 검색 전·마지막 검색 뒤 자투리 대기 제거**. `RANK_SEMI_AUTOSUBMIT=False`면 예전처럼 사람이 Enter(자동채움만). 관련: `_submit_search`(Enter+버튼/폼 폴백)·`_prefill_search`(검색창 자동입력, 제출 안 함). [[login-block-session-first-circuit-breaker]] [[rank-antiblock-circuit-breaker]]

**반자동은 50위 초과도 실제 등수 기록**(2026-09-11): 자동은 `RANK_SCAN_MAX=50` 상한이나, 반자동은 이미 떠 있는 페이지 1장만 읽어 트래픽/차단 부담이 없으므로 `config.RANK_SCAN_MAX_SEMI=300`으로 로드된 페이지 오가닉 전부를 세어 **51위 이상도 그 등수로 기록**(라이브 검증: 51위 상품이 기본 max50→None="50위"로 뭉개짐 vs 반자동 max300→51 정확). `_track_ranks_semi`에서 `parse_serp_rank(pg, matcher, max_rank=config.RANK_SCAN_MAX_SEMI)`.

**검증**: `tools/simulate_pipeline.py` 시나리오 9(노출명 rename+vid 앵커 dedup+save/load 왕복 키안정) 추가·통과, 1~8 회귀 통과. pyflakes·vulture 0. **라이브 end-to-end 통과(2026-09-11 집)**: 실제 '텀블러' 검색 60개→1위 오가닉 vid 매칭→parse_serp_rank 순위=1+정확노출명 회수→set_display_name 계약상품명 갱신→저장/재로드 키안정 PASS. '소음방지매트' 60개→미노출도 정상 판정. 미커밋(사용자 요청 시 커밋).
