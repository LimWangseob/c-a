---
name: coupang-openapi-not-available-consignment
description: 쿠팡 판매자 OpenAPI로 UI 로그인 탈출 불가 — 위탁 운영이라 각 계정 API 키 보유·발급 불가
metadata: 
  node_type: memory
  type: project
  originSessionId: 86f546fd-73d2-44f3-882b-81f410401898
  modified: 2026-09-09T04:23:04.863Z
---

쿠팡 판매자 OpenAPI(상품·주문·재고 등, 무료)로 WING UI 로그인을 대체하자는 안은 **불가 확정**(2026-09-09 사용자).

**Why:** 이 프로그램이 다루는 28개 계정은 **위탁 운영분**이라 각 판매자 계정의 OpenAPI 액세스키를 우리가 보유·발급할 수 없다(타인 계정에 상시 자격증명을 만드는 권한 문제). 따라서 API로 탈출할 수 없고 **WING 브라우저 세션이 유일한 데이터 경로**.

**How to apply:** 근본 해결책 논의에서 "OpenAPI 전환"은 제안하지 말 것. API로 인증을 없앨 수 없으므로 **세션 관리(재사용 강화·TTL 실측·검증된 keep-warm)가 유일한 레버**가 된다 → 이게 세션 전략을 더 중심으로 만든다. 관련=[[login-block-session-first-circuit-breaker]] · [[login-block-session-first-circuit-breaker]] · [[login-policy-real-browser-only]].
