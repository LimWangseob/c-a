"""새 키워드 로직(핵심 AI추출 → 여러방안 후보수집 → AI 최종선정)을 실제 제목에 라이브로 돌려 단계별로 찍는다.

쿠팡 **로그인 불필요** — OpenAI + 네이버 검색광고 API + **쿠팡 자동완성(비로그인)** 사용(credstore 자동 로드).
목적: 쿠팡 자동완성이 후보에 합류하고, AI가 후보군 지표를 종합해 최종 5개를 뽑는지 실증.
사용: python tools/verify_keywords_live.py ["제목1" "제목2" ...]  (인자 없으면 기본 2제목)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics.browser import WingBrowser                      # noqa: E402
from coupang_analytics.credstore import CredStore                      # noqa: E402
from coupang_analytics.kw_ai import analyze_product, generate_keywords  # noqa: E402
from coupang_analytics.kw_recommend import (keyword_in_title,          # noqa: E402
                                            select_keywords_light)
from coupang_analytics.kw_volume import NaverAdApi, NaverCredentials   # noqa: E402
from coupang_analytics.rank import warmup                              # noqa: E402

_DEFAULT_TITLES = [
    "디프 원형 바베큐 그릴 캠핑 화로 테이블",
    "초경량 통풍성 다용도 안전화 편안한 가벼운 작업화",
]


def _run(title: str, api: NaverAdApi, ak: str, browser) -> None:
    print("\n" + "=" * 70)
    print(f"제목: {title}")
    print("=" * 70)
    use, core, identities, anchors = analyze_product(title, api_key=ak)
    print(f"[1] 용도: {use}")
    print(f"[1] 대표 core: {core} · 정체성: {identities}")
    gen = generate_keywords(title, use, identities, api_key=ak)
    print(f"[2] AI 조합 생성 {len(gen)}개: {gen[:20]}")
    # 실제 배치 경로: 앵커연관 + 쿠팡 자동완성 + AI 조합생성 + 네이버 2단계 확장 → 판정 → AI 최종선정
    picked = select_keywords_light(title, api, ak, browser=browser, log=lambda m: print(m))
    print(f"[4] AI 최종선정 {len(picked)}개 (첫 항목=core, 우선순위순):")
    for t in picked:
        mark = "◆제목포함" if keyword_in_title(t.keyword, title) else "✕제목없음"
        print(f"      [{t.relevance or '?'}] {t.keyword}  (월{t.volume}/모{t.mobile_share}%) {mark}")


def main() -> int:
    titles = sys.argv[1:] or _DEFAULT_TITLES
    store = CredStore()
    nj = store.get_password("__naver__")
    ak = store.get_password("__openai__")
    if not nj or not ak:
        print("네이버/OpenAI 키가 credstore에 없습니다 — 앱 설정 탭에서 키를 먼저 저장하세요.")
        return 2
    d = json.loads(nj)
    api = NaverAdApi(NaverCredentials(d["customer_id"], d["api_key"], d["secret_key"]))
    # 쿠팡 자동완성(비로그인)용 실제 Chrome — 쿠팡 홈 워밍업 후 same-origin fetch
    with WingBrowser(profile_dir="data/chrome-verify", offscreen=True) as b:
        warmup(b)
        for t in titles:
            try:
                _run(t, api, ak, b)
            except Exception as exc:
                print(f"  [실패] {exc.__class__.__name__}: {str(exc)[:120]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
