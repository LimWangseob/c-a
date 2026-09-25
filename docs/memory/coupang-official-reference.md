---
name: coupang-official-reference
description: 쿠팡 공식 운영지식 압축참조(상품등록·주문·배송반품·수수료정산·SEO/ID). 핵심기능 밖 배경지식 — 필요 시 상세 재수집
metadata: 
  node_type: memory
  type: reference
  originSessionId: fd9529df-6f22-4998-bfda-be5db28b97c5
  modified: 2026-09-11T00:09:45.667Z
---

핵심 기능(로그인·판매수집·키워드·순위·서식) 밖의 **쿠팡 공식 운영지식 압축**. 상세가 필요하면 그때 WING/공식문서로 재수집.

- **상품등록**: WING 14단계. 규격=상품명 100자·옵션 200·이미지 500×500 흰배경·searchTags 20개. 엑셀 일괄등록 가능. 판매불가 품목 존재. Open API 스키마=골격(위탁은 UI 경로).
- **주문관리**: 발주서(shipmentBox) 단위. 상태 ACCEPT→INSTRUCT→DEPARTURE→DELIVERING→FINAL_DELIVERY. 취소는 결제완료/상품준비중만. 정산=구매확정 기준.
- **배송/반품**: 출고소요일 기준. 판매자점수(정시출고 99·배송 95). 로켓그로스 입고=바코드/낱개포장/회송 80%. 반품비=사유 제공자 부담.
- **수수료/정산**: 판매수수료 4~10.9%(할인가 기준). 주정산 70/30·월정산 15영업일. 로켓그로스 요금·서비스료 55,000. (수치는 시점 변동)
- **SEO·ID모델**: 검색=카테고리+상품명+검색어+옵션(중복어 금지). 랭킹=실적+선호+경쟁력+정확도(SEO만 아님). **productId 가변 / vendorItemId 불변** → 변경추적은 vendorItemId 기준. [[ledger-scoped-tracking]] [[seldoc-output-format]]
