"""상세페이지 이미지 추출 라이브 검증 — detail_images.extract_from_page 실측(단독=WingBrowser 워밍업).

앱 자체는 A안(CDP attach)으로 사용자 실제 Chrome 세션에 붙지만, 이 단독 도구는 붙을 사용자 Chrome 이
없으므로 WingBrowser 로 워밍업+이동해 '사람이 연 상태'를 재현한 뒤 동일한 순수 로직을 호출한다.

반자동 실제 흐름(앱: 사람이 창에서 상품을 연다)을 재현하기 위해, 여기선 홈 워밍업 후
상품 URL 을 열어 '사람이 연 상태'를 만든 뒤, 앱과 **동일한 추출 로직**을 호출한다.

사용:
  python tools/verify_detail_images_live.py <상품 상세 URL>
  python tools/verify_detail_images_live.py <URL> --out D:/some/folder

⚠ 순위 라이브와 동일하게 깨끗한 IP(핫스팟) 권장. 콜드 프로필 첫 방문은 Access Denied 가능(홈 워밍업으로 우회).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics.browser import WingBrowser  # noqa: E402
from coupang_analytics import config, detail_images  # noqa: E402

_PROFILE = ROOT / "data" / "chrome-images"
_HOME = "https://www.coupang.com/"


def main():
    args = [a for a in sys.argv[1:] if a]
    out = ROOT / "output" / "상세이미지"
    if "--out" in args:
        i = args.index("--out")
        out = Path(args[i + 1])
        args = args[:i] + args[i + 2:]
    if not args:
        print("사용: python tools/verify_detail_images_live.py <상품 상세 URL> [--out 폴더]")
        return
    url = args[0]

    def log(m):
        print(config.format_log(m))   # 표준 로그 포맷([YYYY-MM-DD HH:MM:SS.mmm] 메시지)

    with WingBrowser(profile_dir=str(_PROFILE), offscreen=False) as b:
        log("[워밍업] 쿠팡 홈 방문(_abck 확보)...")
        b.goto(_HOME, timeout=45000)
        time.sleep(3.0)
        log(f"[열기] {url}")
        b.goto(url, timeout=45000)
        time.sleep(3.0)
        if b.page.title() == "Access Denied":
            log("[중단] Access Denied — 차단됨. 깨끗한 IP(핫스팟)에서 재시도하세요.")
            sys.exit(1)
        # 순수 추출 로직은 Playwright Page 를 받는다(앱은 CDP attach 로 같은 함수 사용).
        res = detail_images.extract_from_page(b.page, out, log=log)

    print("\n===== 결과 =====")
    print(f"상품ID={res.product_id}  제목={res.title!r}")
    print(f"저장폴더={res.out_dir}")
    print(f"대표/갤러리 {len(res.gallery)}장 · 상세 {len(res.detail)}장 · 실패 {res.skipped}")


if __name__ == "__main__":
    main()
