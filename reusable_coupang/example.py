"""reusable_coupang 사용 예제 — 실제로 로그인/순위조회를 돌려보는 데모.

⚠️ 실제 쿠팡에 접속·로그인합니다. 함부로 대량 실행하지 말 것(계정 밴/IP 차단 위험).
    비밀번호는 예제라 인자로 받지만, 실전에선 OS 자격증명 관리자/DPAPI 등 안전 저장소에서 그때만 받아 넘길 것.

실행(패키지 상위 폴더에서):
    python -m reusable_coupang.example login  <프로필폴더> <아이디> <비번>
    python -m reusable_coupang.example rank   <프로필폴더> <키워드> <vendorItemId>
"""
from __future__ import annotations

import sys

from .auto_login import WingBrowser, WING_URL
from .rank_search import warmup, organic_ranks, make_matcher


def demo_login(profile_dir: str, account_id: str, password: str) -> None:
    """보이는 창을 띄워 자동 로그인 → 완료 여부 출력. 2차인증이 뜨면 그 창에서 사람이 처리."""
    # offscreen=False: 로그인은 사람이 볼 수 있게 창을 띄운다(2차인증 대비).
    with WingBrowser(profile_dir=profile_dir, offscreen=False) as b:
        b.goto(WING_URL)
        if b.authenticated():
            print("이미 로그인됨(프로필 세션 재사용).")
            return
        b.autofill_login(account_id, password, on_log=print)   # ID/비번 자동입력·제출
        # 자동입력만으로 안 되면(2차인증/봇챌린지) 창을 표시하고 사람이 처리하도록 대기.
        ok = b.wait_for_login(on_log=print, on_need_user=b.show)
        print("로그인 완료 ✅" if ok else "로그인 미완료 ❌ (원인은 위 로그 참고)")


def demo_rank(profile_dir: str, keyword: str, vendor_item_id: str) -> None:
    """비로그인 검색으로 특정 vendorItemId 의 오가닉 순위를 조회해 출력."""
    # offscreen=True: 순위조회는 창 없이(무인). 로그인 불필요.
    with WingBrowser(profile_dir=profile_dir, offscreen=True) as b:
        warmup(b)                                              # 홈 1회 방문(Akamai 신뢰 쿠키 유지)
        matchers = {"대상상품": make_matcher(vendor_item_ids={vendor_item_id})}
        ranks = organic_ranks(b, keyword, matchers, log=print)
        r = ranks.get("대상상품")
        print(f"'{keyword}' 오가닉 순위: {r if r is not None else '상한 밖(미노출)'}")


def main(argv: list[str]) -> int:
    if len(argv) >= 5 and argv[1] == "login":
        demo_login(argv[2], argv[3], argv[4])
        return 0
    if len(argv) >= 5 and argv[1] == "rank":
        demo_rank(argv[2], argv[3], argv[4])
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
