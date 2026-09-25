---
name: naver-shopping-api-terminated
description: "네이버 쇼핑 검색 API(shop.json) 2026-07-31 완전 종료 — 경쟁강도 소스 소멸, 키 발급 금지, 대안=쿠팡 총상품수"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 5f7ea32f-0224-45bb-a41b-187291332b96
  modified: 2026-09-14T00:00:00.000Z
---

네이버 **쇼핑 검색 API**(`openapi.naver.com/v1/search/shop.json`)는 **2026-07-31자로 완전 종료**됐고 **공식 대체 API 없음**(2026-09-07 웹검색·와플보드 이관가이드로 확인). 함께 종료: 책·책상세·전문자료 검색. 살아남아 NAVER API HUB로 이관된 것: 뉴스·블로그·카페·웹문서·이미지·지식iN·지역·백과·검색어트렌드·Shopping Insight. 단 **Shopping Insight는 "상품 클릭 추이"만** 주고 상품수·목록·가격은 안 줌.

**결과 = 경쟁강도(키워드별 총 상품수) 소스가 네이버 쪽엔 이제 없음.**
- `kw_shopping.py`의 조회 클래스 `NaverShoppingApi`는 **삭제됨**(2026-09-14 실측) — 파일엔 `NaverShopCredentials` 데이터클래스만 UI 호환용으로 잔존(실사용 없음). 검색량은 별개 활성 API인 `kw_volume.NaverAdApi`(네이버 검색광고 키워드도구)에서 온다.
- 설정 탭 "(선택) 네이버쇼핑 키 입력"은 무의미 → **키 발급하지 말 것**(검색광고 API와 별개인 개발자센터 Client ID/Secret).
- 현재 라이브 산출: 상품수·경쟁강도 컬럼 공란, 공략우선순위=월검색량(복사). 키워드 선정은 **순수 수요(검색량)순**만 동작.

**대안(구현 보류, 사용자 결정 대기, 2026-09-07)**: 경쟁강도를 **쿠팡 검색결과 총 상품수**로 대체. `rank.py`가 이미 비로그인 쿠팡 검색을 하므로 순위 스캔에 피기백해 총 건수만 파싱하면 됨(추가 요청·IP 부담 0, 쿠팡 기준이라 프록시 오차 없음). ⚠ 착수 전 `verify_rank_live`로 쿠팡 총상품수 셀렉터 실측 검증 필요.

이 사실은 [[keyword-methodology-ai-anchor]]의 "경쟁강도 네이버쇼핑 반영"·"남은 최대 지렛대=네이버쇼핑 키" 서술을 무효화한다. [[fix-from-real-evidence]]
