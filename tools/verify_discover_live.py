"""판매분석 수집(discover) 라이브 실 테스트 — 기존 로그인 세션 재사용(신규 로그인 X).

이미 로그인해 둔 프로필의 세션이 살아있으면 그 세션으로 실제 판매분석 리포트를 내려받아
상품·옵션·vendorItemId 발견 + 지표 파싱까지 '진짜로' 수행한다(로그인/2차인증 불필요).
세션이 모두 만료됐으면 → 신규 로그인이 필요(사무실에서 앱 실행)하다고 판명된다.

실행: python tools/verify_discover_live.py [계정ID ...]   (인자 없으면 아래 기본 후보 순회)
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics.browser import WING_URL, WingBrowser  # noqa: E402
from coupang_analytics.collector import discover  # noqa: E402
from coupang_analytics.pipeline import account_profile  # noqa: E402

# 어제(9/2) 쿠키 흔적이 있던 계정들(세션 유효성은 실제 열어봐야 확정)
_CANDIDATES = ["bandu11", "wellbing1107", "WBpeak", "quietlab", "roum0502", "seankim137"]
_DAYS = 7   # 최근 N일(판매분석은 기간 합계)


def _session_live(b) -> bool:
    """이미 로그인된 세션인지만 확인(로그인 시도·제출 없음 → 2차인증 안 뜨고 계정 무영향)."""
    b.goto(WING_URL)
    for _ in range(6):                 # 최대 ~12초 폴링(대시보드 리다이렉트/로딩 대기)
        b.page.wait_for_timeout(2000)
        if b.authenticated():
            return True
    return False


def _scan(account_id: str) -> bool:
    """세션 통과 여부만 안전하게 확인(수집 안 함)."""
    with WingBrowser(profile_dir=account_profile(account_id), offscreen=True) as b:
        if _session_live(b):
            print(f"  [통과] {account_id} — 로그인 세션 살아있음")
            return True
        code, detail = b.classify_login()
        print(f"  [만료] {account_id} — 상태[{code}]: {detail[:50]} (로그인 시도 안 함)")
        return False


def _discover_one(account_id: str, date_from: str, date_to: str) -> bool:
    """세션 통과 계정만 판매분석 수집(로그인 시도 없음). 만료면 조용히 건너뜀."""
    with WingBrowser(profile_dir=account_profile(account_id), offscreen=True) as b:
        if not _session_live(b):
            print(f"  [건너뜀] {account_id} — 세션 만료(로그인 필요, 여기선 시도 안 함)")
            return False
        print(f"  [통과] {account_id} — 로그인 없이 수집 시도")
        products, metrics = discover(b.page, date_from, date_to)
    active = [p for p in products
             if any((m := metrics.get(oid)) and (m.views or m.sales or m.visitors)
                    for opt in p.options for oid in opt.vendor_item_ids)]
    print(f"  [실증] {account_id}: 상품 {len(products)}개 · 옵션 {len(metrics)}개 · 활동 상품 {len(active)}개")
    for p in products[:3]:
        oid = p.options[0].vendor_item_ids[0] if p.options and p.options[0].vendor_item_ids else None
        m = metrics.get(oid) if oid else None
        s = f"노출 {m.views}/판매 {m.sales}/방문 {m.visitors}" if m else "(지표 없음)"
        print(f"        - {p.name[:32]} [옵션 {len(p.options)}개] 대표옵션 {s}")
    return True


def main():
    args = sys.argv[1:]
    scan_only = "--scan" in args
    ids = [x for x in args if x != "--scan"] or _CANDIDATES
    to = date.today()
    date_from, date_to = (to - timedelta(days=_DAYS)).isoformat(), to.isoformat()
    print("=" * 60)
    mode = "세션 통과 계정 스캔(수집 안 함)" if scan_only else "통과 계정만 판매분석 수집"
    print(f"  {mode}  |  기간 {date_from} ~ {date_to}")
    print("  * 로그인 시도·제출 없음 → 2차인증 안 뜨고 계정에 영향 없음")
    print("=" * 60)
    live, done = [], 0
    for aid in ids:
        print(f"\n[{aid}] 세션 확인 중…")
        try:
            if scan_only:
                if _scan(aid):
                    live.append(aid)
            elif _discover_one(aid, date_from, date_to):
                live.append(aid)
                done += 1
        except Exception as exc:
            print(f"  [오류] {aid}: {exc.__class__.__name__}: {str(exc)[:120]}")
    print("\n" + "=" * 60)
    if scan_only:
        print(f"  [스캔 결과] 통과 계정 {len(live)}개: {live if live else '없음'}")
        print("  → 통과 계정만 수집하려면: python tools/verify_discover_live.py " + " ".join(live) if live
              else "  → 통과 계정 없음. 로그인 필요(사무실).")
    else:
        print(f"  [완료] 통과 계정 {len(live)}개 중 수집 성공 {done}개: {live if live else '없음'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
