"""네이버 쇼핑 검색 OpenAPI — 키워드별 총 등록 상품수(공급) 조회.

경쟁강도 = 상품수(공급) ÷ 월검색량(수요). 상품수는 네이버 개발자센터 오픈API(쇼핑 검색)에서
`total`(총 검색결과 수)로 얻는다. 쿠팡과 네이버는 등록 상품이 다르지만 **경쟁 비율은 유사**하다는
전제의 프록시다(값은 '네이버 기준'으로 표기). 검색광고 API 키와 **별개**(Client ID/Secret).
자격증명은 그 PC에만 두고 공유·git 금지.
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

_URL = "https://openapi.naver.com/v1/search/shop.json"


@dataclass
class NaverShopCredentials:
    client_id: str
    client_secret: str


class NaverShoppingApi:
    def __init__(self, creds: NaverShopCredentials):
        self.creds = creds

    def product_count(self, query: str) -> int:
        """키워드의 네이버쇼핑 총 등록 상품수(공급). 호출 실패 시 예외 전파(조용한 폴백 없음)."""
        r = requests.get(
            _URL,
            headers={"X-Naver-Client-Id": self.creds.client_id,
                     "X-Naver-Client-Secret": self.creds.client_secret},
            params={"query": query, "display": 1}, timeout=15)
        r.raise_for_status()
        return int(r.json().get("total", 0))
