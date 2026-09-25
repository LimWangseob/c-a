---
name: login-policy-real-browser-only
description: "로그인 정책 고정 — 실제 Chrome 자동입력만, HTTP 위장 로그인 금지(재논쟁 금지)"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 4ca6f1ec-575b-4e8e-8476-c3c67cf979b3
  modified: 2026-09-05T04:52:25.969Z
---

쿠팡 윙 로그인은 **실제 Chrome + CDP 자동입력만** 허용(정책 고정: DESIGN.md §4, CLAUDE.md 제약).

**Why:** 사용자(59세, 판매 수익=노후생계)가 "샵마인처럼 자동·편리한 로그인"을 강하게 요구해 여러 번 재논쟁했다. 샵마인의 핵심은 사실 **숨긴 실제 Chromium(WebView2)** 자동로그인이고, HTTP 폼-POST(위장헤더+`_abck`)는 보조/폴백이며 브라우저가 씨딩한 `_abck` 없이는 통과도 안 된다. 우리 라이브 실측: 2026-09-03 실제 Chrome 제출도 Akamai Access Denied. 2026-09-05 실제 Chrome **자동입력이 창 없이·2차인증 없이 성공** 확인.

**How to apply:**
- ⛔ `http_login.py`(requests + UA/sec-ch-ua/Sec-Fetch 위장 + Keycloak 폼POST + `_abck` 재생) **도입·연결 금지**(정책 위반 + 기술적 불가). 파일이 남아있어도 파이프라인에 연결 말 것.
- ✅ `WingBrowser`(실제 Chrome+CDP) + `autofill_login`, 프로필 재사용, `authenticated()`(윙 대시보드 URL + KEYCLOAK_IDENTITY 쿠키 둘 다) 판정.
- 브라우저 **기본 숨김(offscreen)**, 2차인증 등 사람 필요 시에만 **로그로 예고 후** 표시. 완료 팝업 없이 로그 기록.
- **rank_browser 와 로그인 브라우저 동시 open 금지**(sync playwright 1개/스레드 — 중첩 시 "Playwright Sync API inside the asyncio loop" 에러). 로그인 브라우저 닫힌 뒤 계정마다 순위 브라우저 별도 open.
- `WingBrowser.__enter__`가 실행 전 그 프로필 잔여 Chrome 자동 정리(프로필 잠금→포트 미개방 방지).
- 세션 영속(SessionStore, DPAPI) + 킵얼라이브(`session_keepalive`)로 재로그인·2차인증 빈도↓.

관련: [[login-2fa-location-based]] [[coupang-session-short-lived]] [[shopmine-architecture]]
