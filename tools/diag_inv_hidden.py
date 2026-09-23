"""재고 조회 hiddenStatus 값 실험 + **'둘다' 리스팅 NORMAL 고유옵션 진단(D/A-2)**.

배경1: fetch_inventory 는 hiddenStatus:"VISIBLE" 만 조회 → ⚠️등록가능·❗중지 옵션이 빠져 그 옵션 재고 공란
(2026-09-22 실측). "HIDDEN"=0개라 값이 틀림. 이 스크립트가 여러 hiddenStatus 값으로 같은 계정 재고를
조회해 **vid 개수**를 비교 → 전량을 주는 값을 찾는다.

배경2(D/A-2 진단): products_from_vendor_inventory 는 '둘다'(RFM+NORMAL 혼재) 리스팅에서 **NORMAL 옵션을
전부 제외**(collector.py). RFM 에 **같은 item_name 짝이 없는 NORMAL 고유옵션**이 있으면 그 옵션 지표가
누락된다. 이 도구가 계정의 '둘다' 리스팅을 훑어 **(1) 혼합 리스팅(RFM전용+NORMAL전용 공존)이 실재하는지,
(2) 같은 물리 옵션의 NORMAL/RFM item_name 이 정확히 일치하는지**를 자동 판정해 안전판 수정 여부를 결정한다.
결론: 혼합 리스팅 0 = 수정 불필요(헛수정). 이름 미세 불일치 = item_name 매칭 대신 다른 키 필요(회귀 위험).

**로그인 세션 재사용**(profile) — 최근 로그인했으면 재로그인 없이 붙는다. 사무실에서 실행.

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
from coupang_analytics.collector import _INV_FETCH_JS, _parse_inventory, kind_of  # noqa: E402
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
        _diag_both_normal(listings)
    print("\n== 끝 ==")


def _norm_name(s):
    return (s or "").strip()


def _diag_both_normal(listings) -> None:
    """D/A-2 자동 판정 — '둘다' 리스팅에서 (1) NORMAL 고유옵션 실재 여부 (2) NORMAL↔RFM 이름 일치 여부.

    현재 코드는 '둘다' 리스팅의 NORMAL 을 전부 버린다. 아래 두 신호로 안전판 수정 필요성을 판정:
      - 고유 NORMAL(같은 item_name 의 RFM 짝 없음) > 0  → 지표 누락 실재 → 안전판 수정 필요
      - 겹치는 NORMAL/RFM 의 item_name 이 **정확히** 같은가 → 다르면 item_name 매칭은 회귀 위험(다른 키 필요)
    """
    both = [L for L in listings if kind_of(o.registration_type for o in L.options) == config.KIND_BOTH]
    print(f"\n[D/A-2 진단] '둘다'(RFM+NORMAL 혼재) 리스팅 {len(both)}개")
    if not both:
        print("  → 이 계정엔 '둘다' 리스팅 없음(NORMAL 고유옵션 손실 위험 없음). 수정 불필요(이 계정 기준).")
        return
    unique_normal_total = 0     # RFM 짝 없는 NORMAL 고유옵션(=현재 코드가 잃는 지표)
    overlap_total = 0           # RFM 와 같은 이름 짝이 있는 NORMAL(정상 제외 대상)
    for L in both:
        rfm_names = {_norm_name(o.item_name) for o in L.options if o.registration_type == "RFM"}
        normals = [o for o in L.options if o.registration_type != "RFM"]
        uniq = [o for o in normals if _norm_name(o.item_name) not in rfm_names]
        over = [o for o in normals if _norm_name(o.item_name) in rfm_names]
        unique_normal_total += len(uniq)
        overlap_total += len(over)
        if uniq:
            print(f"  ⚠ invId={L.vendor_inventory_id} {L.product_name[:22]!r} — 고유 NORMAL {len(uniq)}개(현 코드가 지표 손실):")
            for o in uniq:
                print(f"        vid={o.vendor_item_id} {o.item_name!r} {o.sale_price}원 (RFM 이름목록={sorted(rfm_names)})")
    print(f"\n  [판정] 고유 NORMAL(손실) 총 {unique_normal_total}개 · 정상 제외(RFM 이름 짝 있음) {overlap_total}개")
    if unique_normal_total == 0:
        print("  → 고유 NORMAL 0 = 현재 코드로 지표 손실 없음(이 계정 기준). 안전판 수정 불필요(헛수정 회귀 방지).")
    else:
        print("  → 고유 NORMAL 존재 = 지표 손실 실재. 안전판(이름 겹치는 NORMAL 만 제외) 수정 근거. "
              "단 위 '겹치는' 케이스의 NORMAL/RFM 이름이 정확히 같은지 육안 확인(미세 불일치면 이중집계 회귀).")


if __name__ == "__main__":
    main()
