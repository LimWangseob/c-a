"""단일 계정 로그인 + 판매분석 수집(discover) 라이브 실 테스트.

계정 하나만 로그인 창을 띄워 로그인(비번 자동입력 + 2차인증은 사람이 처리)한 뒤, 방금 그
세션으로 판매분석 리포트를 실제로 내려받아 상품·옵션·지표 발견까지 수행한다. run_full 이
계정마다 쓰는 실제 로직(_login_and_discover)을 그대로 1계정에만 돌리는 실 테스트다.

**사무실에서 사람이 직접 실행**한다(로그인 창의 2차 인증은 사람만 가능).

사용:
  python tools/verify_login_discover_live.py               # 입력엑셀 첫 계정(비번 자동입력)
  python tools/verify_login_discover_live.py <계정ID>       # 특정 계정
  python tools/verify_login_discover_live.py <계정ID> --manual  # 자동입력 안 함, 사람이 직접 로그인
  python tools/verify_login_discover_live.py --list        # 계정 목록만 출력

자동 제출이 Akamai 봇 차단(Access Denied)에 걸리면 --manual 로 사람이 직접 타이핑해 로그인한다.
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

from coupang_analytics.credstore import CredStore  # noqa: E402
from coupang_analytics.input_list import parse_input_list  # noqa: E402
from coupang_analytics.pipeline import _login_and_discover, _inventory_by_product  # noqa: E402

_REAL_INPUT = Path(r"D:\토탈셀러\셀독\토탈셀러_셀독 관리 대장 (3).xlsx")
_DAYS = 7


def main():
    args = sys.argv[1:]
    manual = "--manual" in args
    args = [x for x in args if x != "--manual"]
    if not _REAL_INPUT.exists():
        print(f"[중단] 입력 엑셀 없음: {_REAL_INPUT}")
        return
    il = parse_input_list(str(_REAL_INPUT))
    if not il.accounts:
        print("[중단] 입력 엑셀에서 계정을 찾지 못함")
        return

    if args and args[0] == "--list":
        print("계정 목록(계정ID / 사업자명 / 상품수):")
        for a in il.accounts:
            print(f"  {a.account_id}  |  {a.business_name}  |  상품 {len(a.products)}개")
        return

    target = args[0] if args else il.accounts[0].account_id
    a = next((x for x in il.accounts if x.account_id == target), None)
    if a is None:
        print(f"[중단] 계정ID '{target}' 를 입력엑셀에서 찾지 못함 (--list 로 확인)")
        return

    to = date.today()
    date_from, date_to = (to - timedelta(days=_DAYS)).isoformat(), to.isoformat()
    store = CredStore()
    # --manual 이면 비번을 주지 않아 자동입력을 건너뛰고 사람이 직접 로그인(봇 차단 회피)
    get_pw = (lambda aid: None) if manual else (lambda aid: store.get_password(aid))
    has_pw = (not manual) and bool(store.get_password(a.account_id))

    print("=" * 60)
    print("  로그인 + 판매분석 수집(discover) 라이브 실 테스트")
    print("=" * 60)
    print(f"  대상 계정 : {a.account_id}  ({a.business_name})")
    print(f"  로그인 방식: {'자동입력' if has_pw else '수동(창에서 직접 입력)'}"
          f"{' [--manual]' if manual else ''}")
    print(f"  수집 기간 : {date_from} ~ {date_to} (최근 {_DAYS}일 합계)")
    print("  → 잠시 후 로그인 창이 화면 중앙에 뜹니다. 2차 인증이 뜨면 그 창에서 처리하세요.")
    print("=" * 60)

    report_acc, metrics, inv_by_vid = _login_and_discover(a, date_from, date_to, get_pw, print)

    print("-" * 60)
    if report_acc is None:
        print("  [결과] 로그인 미완료 → 수집 못 함 (위 [로그인감지] 로그가 원인)")
        return
    active = [p for p in report_acc.products
             if any((m := metrics.get(oid)) and (m.views or m.sales or m.visitors)
                    for opt in p.options for oid in opt.vendor_item_ids)]
    print(f"  [실증] 수집 성공 — 발견 상품 {len(report_acc.products)}개 · "
          f"옵션(vendorItemId) {len(metrics)}개 · 활동 상품 {len(active)}개")
    for p in report_acc.products[:5]:
        oid = p.options[0].vendor_item_ids[0] if p.options and p.options[0].vendor_item_ids else None
        m = metrics.get(oid) if oid else None
        s = f"노출 {m.views}/판매 {m.sales}/방문 {m.visitors}" if m else "(지표 없음)"
        print(f"        - {p.name[:34]} [옵션 {len(p.options)}] 대표 {s}")
    # 재고현황(Phase2 rfm-inventory) — 계약(로켓그로스) 상품만. 상품단위 vid 합산 결과 확인.
    inv_by_product = _inventory_by_product(report_acc.products, inv_by_vid)
    print("-" * 60)
    if inv_by_vid:
        print(f"  [재고] 옵션(vid) {len(inv_by_vid)}개 · 상품 {len(inv_by_product)}개 (판매가능 수량)")
        for name, qty in inv_by_product.items():
            print(f"        · {name[:40]} → 재고 {qty}")
    else:
        print("  [재고] 재고현황 없음 (개인계정이거나 계약상품 미보유/조회 실패)")
    print("=" * 60)
    print("  [완료] 로그인→판매분석 수집 실 테스트 성공")
    print("=" * 60)


if __name__ == "__main__":
    main()
