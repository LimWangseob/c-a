"""네이버 쇼핑 API 자격증명 dataclass만 보존.

⚠️ 네이버쇼핑 검색 API(shop.json)는 2026-07-31자로 종료됨(대체 없음) → 조회 클래스(NaverShoppingApi)는
삭제. `NaverShopCredentials`는 설정 탭의 (선택) 쇼핑 키 입력 UI 호환을 위해서만 남긴다(실사용 없음).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class NaverShopCredentials:
    client_id: str
    client_secret: str
