"""쿠팡 자동완성(연관검색어) 실측 — 실제 Chrome + 쿠팡 홈(로그인 아님).

검색창에 키워드를 타이핑할 때 쿠팡이 내려주는 자동완성 후보의
①네트워크 엔드포인트(XHR/fetch) URL·응답구조, ②드롭다운 DOM 셀렉터를
라이브로 확인한다. 키워드 선정 후보 소스로 쓸 수 있는지 판정용.

실행: python tools/verify_autocomplete_live.py [키워드]
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
from coupang_analytics.rank import RankBlocked, warmup  # noqa: E402

_PROFILE = "data/chrome-verify"
_KEYWORD = sys.argv[1] if len(sys.argv) > 1 else "화로테이블"

# 자동완성 관련일 법한 URL 조각
_URL_HINTS = ("autocomplete", "auto-complete", "auto_complete", "suggest",
              "complete", "keyword", "relate", "related", "ac?", "/ac/")
# 검색창 셀렉터 후보
_INPUT_SEL = ["input#headerSearchKeyword", "input[name='q']",
              "input[type='search']", "input[title*='검색']", "input[placeholder*='검색']"]
# 자동완성 드롭다운 셀렉터 후보
_DROP_SEL = ["[class*='autoComplete'] li", "[class*='autocomplete'] li",
             "[class*='auto-complete'] a", "[class*='suggest'] li",
             "ul[class*='keyword'] li", "[class*='searchDropdown'] li",
             "[class*='recommend'] li"]


def main():
    print("=" * 64)
    print("  쿠팡 자동완성(연관검색어) 라이브 실측 (실제 Chrome, 로그인 아님)")
    print("=" * 64)
    print(f"  입력 키워드='{_KEYWORD}'")

    captured = []

    def on_response(resp):
        low = resp.url.lower()
        if any(h in low for h in _URL_HINTS):
            try:
                body = resp.text()
            except Exception as exc:                       # noqa: BLE001
                body = f"<본문 읽기 실패: {exc.__class__.__name__}>"
            captured.append((resp.status, resp.url, body))

    try:
        with WingBrowser(profile_dir=_PROFILE, offscreen=True) as b:
            print("  [1] Chrome 기동 + 쿠팡 홈 워밍업…")
            warmup(b)
            b.page.on("response", on_response)

            print("  [2] 검색창 탐색…")
            inp = next((s for s in _INPUT_SEL if b.page.query_selector(s)), None)
            if not inp:
                print("      ✖ 검색창 못 찾음. 홈 input 목록:")
                for el in b.page.query_selector_all("input"):
                    print(f"        id={el.get_attribute('id')} "
                          f"name={el.get_attribute('name')} "
                          f"type={el.get_attribute('type')} "
                          f"placeholder={el.get_attribute('placeholder')}")
                return
            print(f"      검색창 셀렉터 = {inp}")

            print("  [3] 키워드 타이핑(글자마다 자동완성 트리거)…")
            b.page.click(inp)
            b.page.type(inp, _KEYWORD, delay=220)
            b.page.wait_for_timeout(2800)

            print("\n=== ① 자동완성 네트워크 요청 ===")
            if captured:
                for st, url, body in captured:
                    print(f"[{st}] {url}")
                    print(body[:1800])
                    print("-" * 48)
            else:
                print("  (자동완성으로 보이는 XHR/fetch 미포착)")

            print("\n=== ② 자동완성 드롭다운 DOM ===")
            drop = next((s for s in _DROP_SEL if b.page.query_selector_all(s)), None)
            if drop:
                print(f"  드롭다운 셀렉터 = {drop}")
                for e in b.page.query_selector_all(drop)[:20]:
                    txt = (e.inner_text() or "").strip().replace("\n", " ")
                    if txt:
                        print(f"    · {txt[:50]}")
            else:
                print("  (알려진 셀렉터로 드롭다운 못 찾음 — 페이지 저장해 수동 확인 필요)")
        print("=" * 64)
        print("  [완료] 실측 종료")
        print("=" * 64)
    except RankBlocked as exc:
        print(f"  [차단] 쿠팡이 차단(Akamai): {exc}")
    except Exception as exc:                                # noqa: BLE001
        print(f"  [오류] {exc.__class__.__name__}: {str(exc)[:160]}")
        raise


if __name__ == "__main__":
    main()
