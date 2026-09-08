"""kw_suggest 라이브 검증 — 쿠팡 자동완성 엔드포인트 직접 호출(타이핑 없이 fetch).

실제 Chrome으로 쿠팡 홈을 연 뒤, kw_suggest.fetch_suggestions/collect_suggestions가
브라우저 세션에서 자동완성 API를 직접 호출해 후보를 가져오는지 실증한다.

실행: python tools/verify_suggest_live.py [시드 ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics.browser import WingBrowser  # noqa: E402
from coupang_analytics.kw_suggest import collect_suggestions, fetch_suggestions  # noqa: E402
from coupang_analytics.rank import RankBlocked, warmup  # noqa: E402

_PROFILE = "data/chrome-verify"
_SEEDS = sys.argv[1:] or ["화로테이블", "고기굽는테이블", "안전화"]


def main():
    print("=" * 64)
    print("  kw_suggest 라이브 검증 (자동완성 직접 fetch, 로그인 아님)")
    print("=" * 64)
    try:
        with WingBrowser(profile_dir=_PROFILE, offscreen=True) as b:
            print("  [1] Chrome 기동 + 쿠팡 홈 워밍업(same-origin fetch용)…")
            warmup(b)

            print("  [2] 시드별 자동완성 직접 호출…")
            for seed in _SEEDS:
                sug = fetch_suggestions(b, seed)
                print(f"      '{seed}' → {len(sug)}개")
                for s in sug:
                    print(f"          · {s}")

            print("  [3] collect_suggestions(붙임/띄움 변형) 순서보존 합집합…")
            variants = []
            for s in _SEEDS[:1]:
                variants += [s, s.replace(" ", ""), " ".join(s)]
            combined = collect_suggestions(b, variants, log=lambda m: print(m))
            print(f"      합집합 {len(combined)}개: {combined}")
        print("=" * 64)
        print("  [완료] 직접 호출 방식 정상 — kw_suggest 사용 가능")
        print("=" * 64)
    except RankBlocked as exc:
        print(f"  [차단] 쿠팡이 차단(Akamai): {exc}")
    except Exception as exc:                                # noqa: BLE001
        print(f"  [오류] {exc.__class__.__name__}: {str(exc)[:160]}")
        raise


if __name__ == "__main__":
    main()
