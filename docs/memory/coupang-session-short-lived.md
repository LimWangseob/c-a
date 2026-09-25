---
name: coupang-session-short-lived
description: 쿠팡 윙 로그인 세션은 하루 이내 만료 → 세션 재사용 수집 전제가 자주 깨지고 매 실행 재로그인 필요
metadata: 
  node_type: memory
  type: project
  originSessionId: 35a0e9d9-5949-42c2-86de-2607b83e66bc
  modified: 2026-09-03T00:14:59.468Z
---

쿠팡 윙 로그인 세션(프로필 쿠키)은 **하루도 안 돼 만료**된다. 실측: 2026-09-02 로그인한 6개
계정 프로필이 2026-09-03 확인 시 전부 만료 — `WingBrowser` 로 열면 대시보드가 아니라 로그인
폼(`classify_login`=`form`, #username)으로 리다이렉트됨(12초 폴링해도 동일 → 대기부족 오판 아님).

**의미:** "사람이 한 번 로그인 → 이후 세션 재사용으로 무인 수집"이라는 전제가 자주 깨진다.
실행 때마다(거의 매일) 계정별 **신규 로그인**이 필요하고, 그 로그인은 [[login-2fa-location-based]]
때문에 **사무실에서 + 2차 인증**을 사람이 처리해야 한다. 지문위조 금지라 자동 우회 불가.

**How to apply:** discover(판매분석 수집) 라이브 검증/실행은 "그 세션에서 방금 로그인한 직후"에만
확실히 된다(그래서 `run_full` 이 계정단위로 로그인→수집을 붙여 둔 것). 오래된 프로필로 무인 수집을
가정하지 말 것. 세션 유효성은 항상 `authenticated()` 로 먼저 확인(만료면 그 계정 건너뜀/재로그인).
확인 도구: `python tools/verify_discover_live.py [계정ID …]`.
