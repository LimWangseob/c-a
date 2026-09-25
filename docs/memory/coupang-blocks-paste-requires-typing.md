---
name: coupang-blocks-paste-requires-typing
description: 쿠팡 Akamai는 붙여넣기(비신뢰 input)를 차단·실제 키보드 타이핑만 통과 — 검색어는 글자별 신뢰 키입력+미세랜덤간격
metadata: 
  node_type: memory
  type: project
  originSessionId: a4a8b96f-6732-4514-894c-0ec2551ccdaf
  modified: 2026-09-14T06:47:50.577Z
---

**실측(사용자, 2026-09-13 — 중요):** 같은 IP·같은 키워드('맥문동환')라도 **검색창에 붙여넣기(복사/붙여넣기)하면 쿠팡 차단 페이지("사용권한이 없습니다")가 뜨고, 한 글자씩 직접 타이핑하면 통과**했다. → 쿠팡 Akamai는 검색어 입력이 **실제 키보드 입력인지(신뢰 키이벤트·글자별 타이밍)** 를 짧은 쿼리로 체크한다.

**대응(구현 `69ae85b`):** 붙여넣기/직접 URL 이동 폐지 → **사람처럼 한 글자씩 실제 키보드 타이핑**.
- `rank.human_type_query(page, text)`: 검색창 포커스+기존값(Ctrl+A·Delete) 삭제 후 **글자별 신뢰 키입력**(`page.keyboard.type(ch)` — ASCII는 keydown/keypress/keyup, 한글은 음절 단위 insertText=신뢰 input). 글자마다 **미세 랜덤 간격** `_human_key_delay()`(0.07~0.19s + 12% 확률 망설임 0.18~0.45s) = 사람 타이핑 리듬.
- **자동(전체실행) 순위**: `rank._load_results`가 1페이지는 `browser.goto(검색URL)` 대신 **검색창 타이핑+Enter**(`_await_query_navigated`로 URL q 일치 대기), 2페이지+는 URL 폴백(스캔50=1페이지라 드묾). 검색창 못 찾으면 URL 폴백.
- **반자동(③)**: `_prefill_search`가 네이티브 value setter(옛 `_PREFILL_JS`) 대신 `human_type_query`로 타이핑. 자동제출은 긴 dwell 대신 타이핑 후 짧은 사람 멈춤(0.5~1.4s) 뒤 Enter.

**CDP IME 자모 단위 조합 구현(`ed1665c`, 공용 `human_typing.py`):** 한글을 실제 IME처럼 **자모 단위**로 입력.
음절→자모 분해(복합모음 ㅘ=ㅗ+ㅏ·복합종성 ㄺ=ㄹ+ㄱ 등 포함) → 자모마다 `Input.dispatchKeyEvent`(keyCode **229**=Process) keydown + `Input.imeSetComposition`(조합 텍스트 갱신=compositionupdate) → 음절 완성 시 `Input.insertText` 커밋(compositionend). ASCII는 `keyboard.type`(keydown 발생). 글자마다 미세 랜덤 간격. **전 11172개 한글 음절 조합 정확성 검증(불일치 0).** 스위치=`config.TYPE_JAMO_IME`(기본 True).
- 순위: `rank.human_type_query`가 type_focused(자모 IME) 후 **입력값 검증** → 어긋나면 음절단위→URL 순 자동 폴백(깨져도 안전).
- **로그인**: `browser.autofill_login`이 ID/비번을 `fill`(붙여넣기) 대신 `_type_field`로 실제 타이핑(불일치 시 fill 폴백). ID/비번=ASCII라 jamo=False.

**실제 Chrome 라이브 검증(2026-09-13, 내가 직접 테스트):**
- **타이핑 메커니즘 완전 작동**: 중립 input·쿠팡 실제 React 검색창 모두 값='맥문동환' 정확. 이벤트열=진짜 IME와 동일(자모마다 `keydown[isTrusted=true]`+compositionstart/update+input). **navigator.webdriver=False**(자동화로 안 잡힘), window.chrome 존재, ko-KR·Win32.
- **로그인 타이핑도 작동**: WING 로그인폼에 더미 id/비번(특수문자 포함) 실제 키보드로 정확히 입력(제출 안 함).
- **그러나 사무실 IP는 검색 제출 시 여전히 차단**(홈은 통과·검색결과만 "사용권한" 차단) → 차단은 **입력방식보다 IP 평판/차원**. 타이핑이 차단을 실제 완화하는지는 **깨끗한 IP(핫스팟)** 에서만 판별 가능.

**진짜 키보드처럼 보이게 개선(`7165852`):**
- 속도 **초중급자**로 하향(config.TYPE_KEY_DELAY_MIN/MAX=0.14~0.38·평균~0.26s/키 + 22% 망설임 + 5% 긴멈춤). "너무 빠르다" 피드백 반영.
- 조합 keydown에 **물리 키 code**(2벌식, ㄱ=KeyR 등) + keyCode 229 + shift modifier → 실측 keydown code ''→'KeyA/KeyO/KeyR'(진짜 IME keydown과 동일).
- **판별 가능성 답**: JS 표준상 유일 신호=`isTrusted`인데 CDP 키입력은 true라 하드웨어 키보드와 **직접 구분 불가**. 남은 미세신호=compositionend만 isTrusted=false(insertText 커밋), code 채움으로 keydown은 완전 정상.

**compositionend[F] 근본원인·한계(실측 확정):** CDP `imeSetComposition`/`insertText`는 렌더러-브라우저 경계(RenderWidgetHostImpl)에서 플랫폼 IME(TSF/Imm32)를 우회해 Blink에 직접 디스패치 → **커밋 단계의 신뢰 compositionend를 CDP로는 못 만든다**(insertText=종료[F], 빈문자=[F]+값소실, Enter/재확정=종료 없음). 탐지 우선순위=IP/TLS지문 > keydown타이밍 > IME이상, compositionend[F]는 리눅스IME/웹뷰서도 관측돼 단독 즉시차단 트리거로는 약함(FP위험). **진짜 완결은 OS 네이티브 주입뿐인데**, 제안된 IMM32 `WM_IME_*` PostMessage(3단계)는 현대 Chromium이 TSF 기본이라 무시될 공산 + 조합문자열이 메시지에 안 실림(HIMC 필요) → **그대로는 난망, PoC 필수**.

**2단계 구현(`aee1b9d`): 어절 단위 단일 조합 커밋** — 연속 한글을 한 조합 세션으로(`_ime_run`), 어절 끝 insertText 1회 → compositionend[F]가 음절 N개 → **어절당 1개**로 축소. 라이브 검증: '맥문동환' 값 정확·compositionend 4→1. compositionupdate(자모별)는 전부 trusted 유지.

**커밋단위 스위치(`70426e3`):** `config.TYPE_JAMO_COMMIT_MODE` = `"eojeol"`(기본, 어절 1회 커밋) / `"syllable"`(음절마다 커밋). 탐지 로직 미지 → **핫스팟 A/B 비교용**. `type_dwell`(글자수+2초)로 입력 후 Enter 전 사람 멈춤. **설계서 정식 반영: `designs/DESIGN.md §4.8`(검색어·로그인 입력=사람 타이핑, 🔒 고정).**

**작업 순서(합의):** ①핫스팟(클린 IP) 검증 먼저 → ②(완료, 어절커밋) → ③극단시에만 PostMessage PoC(TSF/HIMC 문제로 비권장, 그 시점이면 IP/TLS지문이 더 유력).

값 검증+폴백(음절→URL/fill)이 있어 조합 실패해도 입력 자체는 보장. 타이핑 후 Enter 전 멈춤=`config.type_dwell(kw)`(글자수+2초). 관련 [[semi-auto-rank-and-exposed-name]]

**★마우스/스크롤도 사람처럼(2026-09-14 소유자 지시 "최대한 사람처럼", 정책변경 [[rank-antiblock-circuit-breaker]]):** 타이핑에 이어 **실제 브라우저 마우스 입력**도 재현 — `human_mouse.py`(`config.RANK_HUMAN_INTERACT`=기본 True). ①`approach_search`=타이핑 직전 커서를 검색창으로 **곡선 이동**(2차 베지어+수직 오프셋 arc·ease-in-out·미세 손떨림·25% 오버슈트→보정) ②`browse_serp`=결과 로드 후 **읽는 멈춤→상품 타일 1~2개 호버→읽는 리듬 스크롤**(여러 번 나눠 굴림+멈춤+가끔 되올림). **클릭은 절대 안 함**(상품 페이지 이탈 방지=순위 파싱 무영향). 배선=`rank._load_results`(자동)+`pipeline._prefill_search`/반자동 결과후. 전부 best-effort try/except(실패해도 검색 무영향). **지문위조 아님**(타이핑과 같은 실제 Input 이벤트). **로컬 검증(set_content 페이지): mousemove 118·wheel 2·전부 isTrusted=True.** ⚠ **차단 완화 실효성은 미검증** — 깨끗한 IP(핫스팟)에서 `RANK_HUMAN_INTERACT` on/off A/B로 판정할 것(효과 가정 금지 [[fix-from-real-evidence]]).

관련: [[rank-antiblock-circuit-breaker]] [[semi-auto-rank-and-exposed-name]] [[coupang-search-prime-then-fetch]] [[fix-from-real-evidence]]
