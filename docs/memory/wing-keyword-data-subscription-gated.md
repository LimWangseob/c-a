---
name: wing-keyword-data-subscription-gated
description: "Wing 로그인 세션의 키워드/검색 데이터 — 순위(N위)는 없음, 키워드별은 유료구독 게이팅, 오가닉 검색노출은 무료 1차데이터"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 769928de-55b1-4f20-8d55-96b5e259654c
  modified: 2026-09-11T06:42:49.813Z
---

2026-09-08 라이브 캡처(계정 wellbing1107, 인증세션)로 확정. "순위 스크래핑을 Wing 공식 데이터로 대체 가능한가?" 조사 결과:

- **키워드별 "순위 위치(N위)": Wing이 제공하지 않음.** vi-detail-search 등 응답에 `position`/`rank` 필드 0회. 오가닉 순위 위치는 본질적으로 스크래핑 전용 지표.
- **키워드별 노출/클릭(`KEYWORD_DAILY` 도메인): 존재하나 유료구독 게이팅.** `metadata/business-insights`에 KEYWORD_DAILY 있으나, Business Insights Pack(월 5만원) 구독 필요. 미구독 계정(`isSubscribed=False`, `NOT_SUBSCRIBED`)은 검색어 탭이 페이월 → 키워드 엔드포인트 미발화. 구독 시 필드는 재캡처 필요.
- **무료로 지금도 나오는 검색 1차 데이터(로그인 안전경로, Akamai 차단 안 됨):**
  - `business-insight/vi-detail-search`(이미 호출): 상품별 `searchVolume·srpClick·srpClickShare`(검색유입·검색결과페이지 클릭·클릭점유율) — 상품 단위 집계.
  - `traffic-insight/distribution/summary/without-subscription`: 출처별(`trafficSourceName=search`, `trafficSourceGroup=internal_organic`) `impression·glanceViews·addToCart·order·conversionRate` + Mix/Variance — 오가닉 검색 노출 집계.
  - `business-insight/vendor-summary`: 계정 전체 검색요약.

**Business Insights 상품 정보(2026-09-11 웹조사)**: 쿠팡 '비즈니스 인사이트' = **2025-09-07 유료 구독 출시**(베이직 5만·스탠다드 9.9만·프리미엄 37.5만원/월, 정산금서 차감; 스탠다드=상위3카테고리, 프리미엄=전카테고리). 제공: 유입경로·검색어·검색노출수·클릭률·전환율·구매퍼널·경쟁상품비교. **일부 기능은 베타 무료 체험 중이나 베타 종료 시 유료 전환 가능(사전 공지 예정)** → 위 "무료 1차 데이터"는 **현재 무료지만 확정 종료일 없음/기한 보장 없음**(정책 변동 리스크, 네이버쇼핑처럼 확정종료일 아님). **접속=로그인 세션 데이터 API라 수시·반복 호출 가능·Akamai 무관, 갱신은 매일 1회(실시간 아님)**. 병목은 세션 확보(로그인)뿐. 출처: etnews 20250825000150, openads 16208.

**함의**: 오늘 유일하게 잘 막히는 게 [[coupang-search-prime-then-fetch]] 비로그인 순위 스크래핑(③). 위 무료 1차 데이터는 인증 세션 API라 오늘도 계정1에서 정상(로그인 API는 안 막힘 — 막힌 건 비로그인 검색·자동로그인 POST뿐). → 노출 진단을 srpClick/srpClickShare + traffic-insight 오가닉으로 하면 순위 스크래핑 의존을 줄여 근본적으로 안전. 키워드별 정밀 필요 시 구독이 정공법. 관련 근본대책=[[login-policy-real-browser-only]] 제약 하 IP평판 관리.
