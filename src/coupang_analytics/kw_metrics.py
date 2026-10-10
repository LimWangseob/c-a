"""키워드의 쿠팡 1페이지 경쟁 지표.

쿠팡은 총 상품수를 노출하지 않으므로, 상품수 대신 **1페이지 경쟁 신호**를 쓴다.
- 로켓비율: 오가닉 중 로켓/로켓그로스 비중(높을수록 판매자배송 진입 어려움)
- 광고수: 1페이지 광고 상품 수(높을수록 경쟁 과열)
1요청(page=1)만 사용해 저부하. rank.py 인프라(실제 Chrome + 광고/로켓 판별)를 재사용한다.
"""
from __future__ import annotations

from dataclasses import dataclass

from .browser import WingBrowser
from .rank import _load_results, extract_items


@dataclass
class KeywordCompetition:
    keyword: str
    organic_count: int   # 1페이지 오가닉 수
    ad_count: int        # 1페이지 광고 수
    rocket_count: int    # 오가닉 중 로켓 수
    found: bool          # 결과 페이지 정상 로드 여부

    @property
    def rocket_ratio(self) -> float:
        return self.rocket_count / self.organic_count if self.organic_count else 0.0


def page1_competition(browser: WingBrowser, keyword: str) -> KeywordCompetition:
    """키워드의 쿠팡 검색 1페이지 경쟁 지표. 결과 없음이면 found=False.
    ⚠ `_load_results` 는 검색창에 **검색어를 타이핑**한다(2026-09-13~) → URL 이 아니라 검색어를 넘긴다(F1·D-033 — 예전엔
    검색 URL 문자열 전체를 쳐서 엉뚱한 결과로 경쟁을 계산했음)."""
    if not _load_results(browser, keyword):
        return KeywordCompetition(keyword, 0, 0, 0, found=False)
    items = extract_items(browser.page)
    organic = [it for it in items if not it.is_ad]
    return KeywordCompetition(
        keyword=keyword,
        organic_count=len(organic),
        ad_count=sum(1 for it in items if it.is_ad),
        rocket_count=sum(1 for it in organic if it.is_rocket),
        found=True,
    )
