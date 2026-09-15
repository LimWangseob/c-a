"""reusable_coupang — 재사용 가능한 쿠팡 '자동 로그인' + '자동 노출순위 검색' 모듈 묶음.

다른 프로젝트에서:
    from reusable_coupang import WingBrowser, organic_ranks, make_matcher, parse_serp_rank

구성:
- auto_login.py   : 실제 Chrome + CDP 자동 로그인(Akamai 통과). 핵심 = WingBrowser.
- rank_search.py  : 쿠팡 검색 오가닉 순위 산출(광고 제외). 자동 검색(organic_ranks) + 반자동 파싱(parse_serp_rank).
- human_typing.py : 사람처럼 한 글자씩 실제 키보드 입력(한글 CDP IME 조합). 로그인·검색어 공용.
- human_mouse.py  : 사람처럼 마우스 이동·스크롤·호버(클릭 없음).
- config.py       : 타이핑 리듬·순위 스캔·상호작용 스위치(값 조정).

의존: playwright(sync) + 실제 설치된 Google Chrome. (일부 Windows 전용 — README 참고.)
"""
from .auto_login import WingBrowser, reap_orphan_chrome, find_chrome, WING_URL
from .rank_search import (
    organic_rank, organic_ranks, parse_serp_rank, make_matcher, extract_items,
    warmup, human_type_query, SearchItem, RankBlocked, HOME_URL, SEARCH_URL,
)

__all__ = [
    "WingBrowser", "reap_orphan_chrome", "find_chrome", "WING_URL",
    "organic_rank", "organic_ranks", "parse_serp_rank", "make_matcher", "extract_items",
    "warmup", "human_type_query", "SearchItem", "RankBlocked", "HOME_URL", "SEARCH_URL",
]
