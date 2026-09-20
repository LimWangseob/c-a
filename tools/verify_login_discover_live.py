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

from coupang_analytics import config  # noqa: E402
from coupang_analytics.credstore import CredStore  # noqa: E402
from coupang_analytics.input_list import parse_input_list  # noqa: E402
from coupang_analytics.pipeline import _login_and_discover  # noqa: E402

_REAL_INPUT = Path(r"D:\토탈셀러\셀독\토탈셀러_셀독 관리 대장 (3).xlsx")
_DAYS = 7


def _log(msg: str) -> None:
    """표준 로그 포맷으로 출력(config.format_log = '[YYYY-MM-DD HH:MM:SS.mmm] 메시지')."""
    print(config.format_log(msg))


def _load_input():
    """앱(app_qt)과 **동일하게** 입력을 로드한다 — input/source=gsheet 면 관리대장 구글시트,
    아니면 마지막 PC 엑셀(없으면 _REAL_INPUT). 반환 (InputList|None, 출처설명)."""
    try:
        from PySide6.QtCore import QSettings
        st = QSettings("coupang-analytics", "ui")
        src = st.value("input/source", "", type=str)
        url = st.value("gsheet/input_url", "", type=str)
        file_path = st.value("file/input", "", type=str)
    except Exception:
        src, url, file_path = "", "", ""
    if src == "gsheet" and url:                       # 앱과 동일: 구글시트 관리대장 우선
        from coupang_analytics.input_list import read_ledger_rows, parse_input_rows
        title, rows, strike = read_ledger_rows(url, store=CredStore())
        return parse_input_rows(rows, strike), f"구글시트 관리대장({title})"
    path = file_path or (str(_REAL_INPUT) if _REAL_INPUT.exists() else "")
    if path and Path(path).exists():
        return parse_input_list(path), path
    return None, None


def main():
    args = sys.argv[1:]
    manual = "--manual" in args
    args = [x for x in args if x != "--manual"]
    try:
        il, src_desc = _load_input()
    except Exception as exc:
        print(f"[중단] 입력(관리대장) 로드 실패: {exc.__class__.__name__}: {exc}")
        return
    if il is None or not il.accounts:
        print("[중단] 입력에서 계정을 찾지 못함 — 앱 설정 탭에서 관리대장(구글시트/PC엑셀)을 먼저 지정하세요.")
        return
    print(f"[입력] {src_desc} — 계정 {len(il.accounts)}개")

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

    # ⚠ 읽기 전용: 마스터/구글시트를 건드리지 않는다(정체·지표만 조회·출력). vid 출처 변경(상품조회/수정)
    # 실동작·판매상태(productStatus) 확인용. 4튜플 = (계정, {vid:지표}, {vid:재고}, {vid:판매상태}).
    # 표준 로그 포맷(_log)으로 파이프라인 로그를 받는다 → 모든 줄에 [YYYY-MM-DD HH:MM:SS.mmm] 시각.
    report_acc, metrics, inv_by_vid, sale_status = _login_and_discover(a, date_from, date_to, get_pw, _log)

    print("-" * 60)
    if report_acc is None:
        _log("[결과] 로그인 미완료 → 수집 못 함 (위 [로그인감지] 로그가 원인)")
        return
    multi = [p for p in report_acc.products if len(p.options) > 1]
    novid = [p for p in report_acc.products if not any(o.vendor_item_ids for o in p.options)]
    _log(f"[실증] 추적 상품 {len(report_acc.products)}개(대장 매칭) · "
         f"다중옵션 {len(multi)}개 · vid 미확보 {len(novid)}개 · 판매지표 옵션 {len(metrics)}개")
    # 판매상태 = RFM isSaleSuspended(True=판매중지·False=판매중·없음=미상[개인상품 등]). productStatus 는 안 씀(상수).
    def _sale(vid):
        v = sale_status.get(vid) if vid else None
        return "판매중지" if v is True else ("판매중" if v is False else "미상")
    _log("[vid 출처=상품조회/수정] 각 상품 옵션별 vid·판매상태(RFM)·지표 (grep 키=vid=…):")
    for p in report_acc.products:
        for o in p.options:
            vid = o.vendor_item_ids[0] if o.vendor_item_ids else ""
            m = metrics.get(vid) if vid else None
            metric_txt = f"노출 {m.views}·판매 {m.sales}·방문 {m.visitors}" if m else "지표 0(당일 판매·노출 없음)"
            inv_txt = f"·재고 {inv_by_vid[vid]}" if (vid and vid in inv_by_vid) else ""
            lbl = f"({o.label})" if o.label else ""
            _log(f"  vid={vid or '없음'} [{p.kind}] {p.name[:30]}{lbl} "
                 f"판매상태={_sale(vid)} {metric_txt}{inv_txt}")
    # 판매상태(§2.3) = RFM isSaleSuspended(로켓그로스만). productStatus 는 판매상태 소스 아님(라이브서 전부 SUSPENDED 상수).
    print("-" * 60)
    if sale_status:
        n_stop = sum(1 for v in sale_status.values() if v is True)
        n_on = sum(1 for v in sale_status.values() if v is False)
        _log(f"[판매상태] RFM 기준 vid {len(sale_status)}개 — 판매중지 {n_stop} · 판매중 {n_on}")
    else:
        _log("[판매상태] 없음 (로켓그로스 재고 없음 등). 판매자배송(개인)은 RFM에 없어 미상.")
    # 재고현황(RFM) — 계약(로켓그로스) 상품만. 옵션(vid)별 재고를 상품단위로 합산해 확인.
    inv_by_product: dict[str, int] = {}
    for p in report_acc.products:
        vals = [inv_by_vid[oid] for opt in p.options for oid in opt.vendor_item_ids if oid in inv_by_vid]
        if vals:
            inv_by_product[p.name] = sum(vals)
    print("-" * 60)
    if inv_by_vid:
        _log(f"[재고] 옵션(vid) {len(inv_by_vid)}개 · 상품 {len(inv_by_product)}개 (판매가능 수량)")
        for name, qty in list(inv_by_product.items())[:8]:
            _log(f"  · {name[:40]} → 재고 {qty}")
    else:
        _log("[재고] 재고현황 없음 (개인계정이거나 계약상품 미보유/조회 실패)")
    print("=" * 60)
    _log("[완료] 로그인→상품조회/수정(vid)+판매분석(지표) 라이브 실 테스트 (읽기 전용·마스터 미변경)")
    print("=" * 60)


if __name__ == "__main__":
    main()
