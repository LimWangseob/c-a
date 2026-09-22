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
        # ── 상품조회(블록 vid 출처) 옵션 전부 ──
        from coupang_analytics.collector import fetch_vendor_inventory
        listings = fetch_vendor_inventory(b.page, lambda m: None)
        vi_opts = []   # (vendorItemId, vendorInventoryItemId, itemName, salePrice, regType, valid, status, 상품명)
        for L in listings:
            for o in L.options:
                vi_opts.append((o.vendor_item_id, o.vendor_inventory_item_id, o.item_name,
                                o.sale_price, o.registration_type, o.valid, o.status, L.product_name))
        vi_vids = {o[0] for o in vi_opts}
        # ── RFM 재고 전부 + 첫 항목 구조 ──
        res = b.page.evaluate(_INV_FETCH_JS, _payload("VISIBLE"))
        data = json.loads(res.get("body", "{}"))
        props = data.get("viProperties") or []
        rfm_vids = {str(p.get("vendorItemId") or "") for p in props}
        print(f"\n[상품조회] 옵션 {len(vi_opts)}개 · [RFM재고] 항목 {len(props)}개")
        print("[RFM 첫 항목 필드]:", list(props[0].keys()) if props else "없음")
        # RFM 항목의 id 후보들(vendorItemId 외에 매칭키 있나) + 이름/가격
        print("[RFM 항목 5개 — id 후보]:")
        for p in props[:5]:
            ids = {k: p.get(k) for k in p if "id" in k.lower() or "Id" in k}
            print(f"   {ids} · name={str(p.get('vendorItemName') or p.get('itemName') or p.get('productName'))[:20]!r}")
        # 상품조회에만 있고 RFM엔 없는 옵션(=재고 공란 원인) — 이름·가격으로 RFM에 짝이 있나
        print(f"\n[상품조회에만·RFM 없음] {len(vi_vids - rfm_vids)}개 vid:")
        rfm_by_name = {}
        for p in props:
            nm = str(p.get("vendorItemName") or p.get("itemName") or "")
            rfm_by_name.setdefault(nm, []).append((str(p.get('vendorItemId')), _parse_inventory([p]).get(str(p.get('vendorItemId')))))
        for o in vi_opts:
            if o[0] in rfm_vids:
                continue
            twin = rfm_by_name.get(o[2] or "", [])
            print(f"   상품조회 vid={o[0]} vInvItemId={o[1]} 이름={o[2]!r} 가격={o[3]} 구분={o[4]} valid={o[5]} status={o[6]}"
                  f"  → RFM 동명 항목: {twin}")
    print("\n== 끝 ==")


if __name__ == "__main__":
    main()
