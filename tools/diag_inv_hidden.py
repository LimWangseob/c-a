"""재고 조회 hiddenStatus 값 실험 — 어떤 값이 전 옵션 재고를 주는지 라이브로 확인.

배경: fetch_inventory 는 hiddenStatus:"VISIBLE" 만 조회 → ⚠️등록가능·❗중지 옵션이 빠져 그 옵션 재고 공란
(2026-09-22 실측). "HIDDEN"=0개라 값이 틀림. 이 스크립트가 여러 hiddenStatus 값으로 같은 계정 재고를
조회해 **vid 개수**를 비교 → 전량을 주는 값을 찾는다. **로그인 세션 재사용**(profile) — 최근 로그인했으면
재로그인 없이 붙는다. 사무실에서 실행.

    python tools/diag_inv_hidden.py [계정ID]   # 기본 nicoable
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

from coupang_analytics import config  # noqa: E402
from coupang_analytics.browser import WingBrowser, WING_URL  # noqa: E402
from coupang_analytics.collector import _INV_FETCH_JS, _parse_inventory, _parse_inventory_roster  # noqa: E402
from coupang_analytics.credstore import CredStore  # noqa: E402
from coupang_analytics.pipeline import account_profile  # noqa: E402
import json  # noqa: E402


def _payload(hidden, page_size=2000):
    p = {"paginationRequest": {"pageSize": page_size, "pageNumber": 0, "searchAfterSortValues": None},
         "sort": [{"sortParameter": "ORDERABLE_QUANTITY", "sortDirection": "DESCENDING"}],
         "rrqContext": {"source": "IHD", "eventType": "RRQ_SEEN", "metadata": "{}"}}
    if hidden is not None:           # None = hiddenStatus 필드 자체를 뺀다(전량 기대)
        p["hiddenStatus"] = hidden
    return p


def main():
    acct = sys.argv[1] if len(sys.argv) > 1 else "nicoable"
    pw = CredStore().get_password(acct)
    print(f"== 재고 hiddenStatus 실험 — 계정 {acct} ==")
    with WingBrowser(profile_dir=account_profile(acct), offscreen=False) as b:
        b.show()
        b.goto(WING_URL)
        b.page.wait_for_timeout(1500)
        if not b.authenticated():
            print("  세션 만료 → 자동입력 로그인 시도(2차인증 시 창에서 처리)")
            if pw and b.autofill_login(acct, pw, on_log=lambda m: print("   " + m)):
                b.wait_for_login(timeout=300, on_log=lambda m: print("   " + m), tag=acct,
                                 on_need_user=lambda: b.show(), skip_on_otp=True)
        if not b.authenticated():
            print("  [중단] 로그인 안 됨"); return
        b.goto(WING_URL)
        b.page.wait_for_timeout(1200)
        from coupang_analytics.collector import fetch_vendor_inventory
        listings = fetch_vendor_inventory(b.page, lambda m: None)
        res = b.page.evaluate(_INV_FETCH_JS, _payload("VISIBLE"))
        data = json.loads(res.get("body", "{}"))
        props = data.get("viProperties") or []
        rfm = {str(p.get("vendorItemId") or ""): _parse_inventory([p]).get(str(p.get("vendorItemId")))
               for p in props}
        # productStatus 원문 분포(검토중 등 미확인 enum 확인)
        from collections import Counter
        pst = Counter(L.product_status or "(빈)" for L in listings)
        print(f"\n[상품조회] 리스팅 {len(listings)}개 · productStatus 분포: {dict(pst)}")
        print(f"[RFM재고] {len(rfm)}vid")
        # ── 리스팅별 전체 구조: 같은 옵션의 RFM/NORMAL/무효/검토중 묶임 확인 ──
        print("\n[리스팅별 옵션 구조] (재고=RFM 매칭 / -=RFM없음):")
        for L in listings:
            regs = Counter(o.registration_type for o in L.options)
            print(f"  ▶ 리스팅 invId={L.vendor_inventory_id} · productStatus={L.product_status!r}"
                  f" · 옵션{len(L.options)}({dict(regs)}) · {L.product_name[:22]!r}")
            for o in L.options:
                inv = rfm.get(o.vendor_item_id)
                mark = f"재고 {inv}" if o.vendor_item_id in rfm else "-(RFM없음)"
                print(f"      vid={o.vendor_item_id} [{o.registration_type}/{o.valid}/{o.status}]"
                      f" {o.item_name!r} {o.sale_price}원 → {mark}")
    print("\n== 끝 ==")


if __name__ == "__main__":
    main()
