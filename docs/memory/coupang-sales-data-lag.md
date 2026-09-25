---
name: coupang-sales-data-lag
description: 쿠팡 판매분석은 당일 데이터를 익일 이후 생성 — 당일 단일 조회는 리포트 0행(정상)
metadata: 
  node_type: memory
  type: project
  originSessionId: 4ca6f1ec-575b-4e8e-8476-c3c67cf979b3
  modified: 2026-09-06T00:20:31.771Z
---

쿠팡 판매분석 '상품별 판매 리포트'(VENDOR_ITEM_METRICS)는 **당일 데이터를 익일 이후에야 생성**한다.
→ 조회 종료일이 오늘/미래면 헤더만 있고 **데이터 행 0개**인 빈 리포트가 내려온다(버그 아님, 정상).

**실증(2026-09-06):** 당일 단일(09-06~09-06) 3계정 모두 0행(파일 3707B, 헤더만). 반면 3일 범위
(09-04~09-06)는 상품 2행. 파일을 직접 열어 확인 — 헤더 파싱은 정상, 차이는 날짜 범위뿐.

**How to apply:** 수집은 **어제(D-1) 이전** 날짜로. `collector.discover`가 0행 시 종료일≥오늘이면
"당일 데이터 미생성" 경고를 로그로 명시함. UI '당일' 옵션을 D-1로 매핑할지 검토 여지 있음.
관련 [[fix-from-real-evidence]], [[coupang-session-short-lived]].
