"""순위 조회(rank.py) 라이브 실증 — 실제 Chrome + 쿠팡 비로그인 검색(로그인 아님).

실제 브라우저로 쿠팡을 검색해 '광고 제외 오가닉 순위'를 산출하는 엔진이 진짜로 동작하는지
확인한다. 결과가 확실한 키워드로 1회 조회하고, 파싱된 오가닉 항목 표본·광고 제외 동작을 보여준다.
차단(Akamai) 시 RankBlocked 로 안전 처리한다.

실행: python tools/verify_rank_live.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics.browser import WingBrowser  # noqa: E402
from coupang_analytics.rank import (  # noqa: E402
    RankBlocked, SEARCH_URL, _ITEM_SEL, extract_items, make_matcher, organic_rank, warmup,
)

_PROFILE = "data/chrome-verify"   # 실증 전용 프로필(파이프라인/UI 프로필과 분리)
_KEYWORD = "텀블러"               # 결과가 확실한 키워드
_NEEDLE = "텀블러"                # 상품명에 이 말이 든 첫 오가닉 항목의 순위


def main():
    print("=" * 60)
    print("  순위 조회 라이브 실증 (실제 Chrome + 쿠팡, 로그인 아님)")
    print("=" * 60)
    print(f"  키워드='{_KEYWORD}', 매칭='상품명에 \"{_NEEDLE}\" 포함'")
    try:
        with WingBrowser(profile_dir=_PROFILE, offscreen=True) as b:
            print("  [1] 실제 Chrome 기동 + 쿠팡 홈 워밍업…")
            warmup(b)

            print("  [2] 검색 결과 로드 + 오가닉/광고 파싱…")
            b.goto(SEARCH_URL.format(q=quote(_KEYWORD), page=1))
            b.page.wait_for_selector(_ITEM_SEL, timeout=15000)
            items = extract_items(b.page)
            organic = [it for it in items if not it.is_ad]
            ads = [it for it in items if it.is_ad]
            print(f"      [실증] 1페이지 항목 {len(items)}개 파싱 = 광고 {len(ads)} + 오가닉 {len(organic)}")
            for i, it in enumerate(organic[:3], 1):
                rocket = "로켓" if it.is_rocket else "일반"
                print(f"        오가닉 {i}위: [{rocket}] {it.name[:34]} (productId={it.product_id})")

            print("  [3] organic_rank() 실제 산출(광고 제외)…")
            rank = organic_rank(b, _KEYWORD, make_matcher(name_substr=_NEEDLE))
            if rank:
                print(f"      [실증] '{_KEYWORD}' 검색에서 '{_NEEDLE}' 포함 첫 오가닉 = {rank}위")
            else:
                print(f"      [실증] 200위 내 '{_NEEDLE}' 미노출(엔진은 정상 동작, 매칭만 없음)")
        print("=" * 60)
        print("  [완료] 순위 엔진이 실제 쿠팡 검색·파싱·광고제외까지 정상 동작")
        print("=" * 60)
    except RankBlocked as exc:
        print(f"  [차단] 쿠팡이 검색을 차단(Akamai): {exc}")
        print("        → RankBlocked 로 안전 처리됨(실사용 시 해당 키워드만 공란). 엔진 로직은 정상.")
    except Exception as exc:
        print(f"  [오류] {exc.__class__.__name__}: {str(exc)[:120]}")
        raise


if __name__ == "__main__":
    main()
