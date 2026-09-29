---
name: monster-functions-extinct-260929
description: 전체 코드베이스 D+ 괴물함수 전멸(browser.wait_for_login·rank.organic_ranks_batch 분해 완료·2026-09-29)
metadata:
  node_type: memory
  type: project
  originSessionId: 93970391-cf4e-47e6-aacd-5dc2d38dfb72
  modified: 2026-09-29T08:13:00.673Z
---

2026-09-29(통합 세션): 마지막 남은 D+ 괴물함수 2개를 **행동 불변** 분해 → `tools/check_complexity.py` 경고 **0개**(전체 코드베이스 D+ 전멸).

- `browser.wait_for_login`(D27→C이하, 커밋 d9d1393): 폴링 루프 상태를 `_LoginWait` 상태객체로 묶고, 화면 분류 반응을 `_react_login`(성공/오류/폼/차단 분기)→`_react_form`·`_react_blocked_otp`로 추출. 보존 엣지케이스=로그인 완료 판정(대시보드+KEYCLOAK_IDENTITY 쿠키)·error 2연속 즉시중단(계정잠금 방지)·form 경고 1회·blocked grace 후 건너뜀·otp skip·akamai/otp 1회 안내.
- `rank.organic_ranks_batch`(D25→C이하, 커밋 9d70368): URL 생성 루프→`_batch_urls`, 4중 중첩 채점 루프→`_score_batch` 추출. **시그니처 불변**(L1 계약 유지)·프라임/백오프 재시도·광고제외 오가닉 채점(상한 도달·매처 소진 break) 보존.

⚠**핀은 두 함수를 FakeBrowser로 대체**(본문 미실행)라 오프라인 게이트가 본문을 안 돌림 → 반드시 **위치만 이동**(CLAUDE.md 규칙). 라이브(로그인·순위) 실측은 사무실/핫스팟 다음 실행서 확인 남음.

검증: 게이트 9종+복잡도 초록·simulate_pipeline 14시나리오·4모듈 import OK. 문서=[[handoff-session-260929-continued]]·CODE_HEALTH_PLAN §1-3·DECISIONS 2026-09-29.

⚠별건: `tools/simulate_stages.py`는 이전 세션 kw_recommend 분해 이후 stale(kw 검색량 단언 IndexError)로 **기존 고장**(browser/rank 무관·게이트 9종 미포함). 별도 정리 필요. 규칙 [[code-health-regression-gate]].
