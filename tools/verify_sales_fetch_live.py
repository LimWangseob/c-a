"""판매분석 데이터 API 직접조회(collector.fetch_sales_details)를 **라이브로 가볍게 검증**.

전체 파이프라인(쿠팡 순위 스캔) 없이 판매분석 API만 한 번 호출해, 사람 클릭·엑셀 다운로드 없이
`vi-detail-search`가 같은 세션 fetch(+x-xsrf-token)로 200을 주고 옵션 지표가 정상 파싱되는지 확인한다.
쿠팡 검색을 안 쳐서 IP 부담이 없다(판매분석 API만).

사용: python tools/verify_sales_fetch_live.py <계정ID> [YYYY-MM-DD YYYY-MM-DD]
  날짜 생략 시 어제(D-1). 세션이 살아있으면 창 없이, 없으면 창을 띄워 사람이 직접 로그인(위탁계정 무리 금지).
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics.browser import WING_URL, WingBrowser        # noqa: E402
from coupang_analytics.collector import fetch_sales_details        # noqa: E402
from coupang_analytics.pipeline import account_profile             # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("사용: python tools/verify_sales_fetch_live.py <계정ID> [YYYY-MM-DD YYYY-MM-DD]")
        return 2
    account_id = sys.argv[1]
    if len(sys.argv) >= 4:
        date_from, date_to = sys.argv[2], sys.argv[3]
    else:
        d = (date.today() - timedelta(days=1)).isoformat()
        date_from = date_to = d
    # 콘솔 + 파일 동시 출력(세션 밖에서도 결과 확인 가능). output/ 는 .gitignore.
    out_path = Path("output") / "_verify_sales_fetch.txt"
    out_path.parent.mkdir(exist_ok=True)
    _fh = out_path.open("w", encoding="utf-8")

    def log(msg=""):
        print(msg)
        _fh.write(str(msg) + "\n")
        _fh.flush()

    log(f"[검증] 계정={account_id} · 기간 {date_from}~{date_to} — 판매분석 API 직접조회만(순위 스캔 없음)")

    with WingBrowser(profile_dir=account_profile(account_id), offscreen=True) as b:
        b.goto(WING_URL)
        b.page.wait_for_timeout(1500)
        if not b.authenticated():
            log("[검증] 세션 없음 → 창을 띄웁니다. 열린 창에서 직접 로그인하세요(최대 5분).")
            b.show()
            if not b.wait_for_login(timeout=300, on_log=log, tag=account_id):
                log("[검증] 로그인 미완료 — 중단")
                _fh.close()
                return 1
            b.hide()
        try:
            metrics = fetch_sales_details(b.page, date_from, date_to, log=log)
        except Exception as exc:
            log(f"[검증] ✖ 직접조회 실패 — {exc.__class__.__name__}: {str(exc)[:200]}")
            _fh.close()
            return 1
        log(f"\n[검증] ✅ 직접조회 성공 — 옵션 {len(metrics)}개")
        for oid, m in list(metrics.items())[:20]:
            log(f"    옵션 {oid}: 노출={m.views} 판매={m.sales} 방문={m.visitors} | "
                f"등록ID={m.item_id} | 상품='{m.product_name[:24]}' 옵션명='{m.option_name[:30]}'")
        if not metrics:
            log("    (옵션 0개 — 해당 기간 판매데이터 없음이면 정상)")
    log(f"[검증] 결과 파일: {out_path}")
    _fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
