"""판매분석 화면의 내부 XHR(웹 API) 캡처 — 로그인 세션에서 '직접 호출' 경로 확정용.

목적: 쿠팡 OpenAPI(판매자 키) 없이, **위탁 로그인 세션의 쿠키**로 판매분석 데이터를 주는
내부 API(예: `vi-detail-search`)의 **URL·메서드·요청바디·응답 형태**를 1회 실측해 확정한다.
이후 collector 가 엑셀 다운로드 대신 그 API 를 같은 세션(page.context.request)으로 직접 호출한다.

- 로그인된 실제 세션이 필요(사무실). 세션 없으면 저장된 비번으로 자동입력 후 사람이 2차인증 통과.
- **네트워크를 로컬 파일로만 기록**하고 외부로 전송하지 않는다. 응답 본문은 앞부분 샘플만 저장.
- ShopMine 등 외부 툴은 실행·의존하지 않는다(우리 브라우저로 우리 세션만 관찰).

실행: python tools/capture_sales_xhr.py <계정ID> [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--seconds 25]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics.browser import WING_URL, WingBrowser  # noqa: E402
from coupang_analytics.credstore import CredStore  # noqa: E402
from coupang_analytics.pipeline import account_profile  # noqa: E402

_SALES_URL = ("https://wing.coupang.com/tenants/business-insight/sales-analysis"
              "?start_date={f}&end_date={t}")
_SKIP = (".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2", ".ttf", ".ico",
         ".map", ".woff2", ".mp4", ".webp")


def _looks_api(url: str) -> bool:
    """쿠팡 도메인의 비정적 응답을 전부 캡처(데이터 XHR을 놓치지 않도록 넓게)."""
    u = url.lower()
    if "coupang.com" not in u:
        return False
    return not any(u.split("?")[0].endswith(ext) for ext in _SKIP)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("account_id")
    ap.add_argument("--from", dest="date_from", default=None)
    ap.add_argument("--to", dest="date_to", default=None)
    ap.add_argument("--seconds", type=int, default=25, help="XHR 관찰 시간(초)")
    ap.add_argument("--manual", action="store_true",
                    help="자동입력 건너뛰고 사람이 직접 로그인(자동제출 Access Denied 회피 — 권장)")
    args = ap.parse_args()
    dt = args.date_to or date.today().isoformat()
    df = args.date_from or dt

    out_dir = Path(ROOT) / "capture"
    out_dir.mkdir(exist_ok=True)
    records: list[dict] = []
    posts: dict[str, str] = {}

    def on_request(req):
        if _looks_api(req.url) and req.method != "GET":
            data = req.post_data
            if data:
                posts[req.url] = data[:2000]

    def on_response(resp):
        if not _looks_api(resp.url):
            return
        rec = {"method": resp.request.method, "status": resp.status, "url": resp.url,
               "content_type": resp.headers.get("content-type", "")}
        if "json" in rec["content_type"]:
            try:
                body = resp.text()
                rec["body_len"] = len(body)
                rec["body_sample"] = body[:2000]   # 앞부분 샘플만(형태 확인용)
            except Exception as exc:   # 진단 도구 — 읽기 실패도 명시 기록(무음 아님)
                rec["body_error"] = f"{exc.__class__.__name__}"
        records.append(rec)

    pw = None if args.manual else (CredStore().get_password(args.account_id) or None)
    print(f"== 판매분석 XHR 캡처 — 계정 {args.account_id}, 기간 {df}~{dt}"
          f"{' (수동 로그인)' if args.manual else ''} ==")
    with WingBrowser(profile_dir=account_profile(args.account_id), offscreen=False) as b:
        b.goto(WING_URL)
        b.page.wait_for_timeout(1500)
        if not b.authenticated():
            if pw and b.autofill_login(args.account_id, pw, on_log=print):
                print("  자동입력·제출 — 2차인증/봇챌린지 뜨면 그 창에서 처리하세요")
            else:
                print("  열린 창에서 직접 로그인하세요…")
            if not b.wait_for_login(timeout=300, on_log=print, tag=args.account_id):
                print("  로그인 미완료 — 중단")
                return
        b.page.on("request", on_request)
        b.page.on("response", on_response)
        print("  판매분석 이동 → XHR 관찰 중…")
        b.goto(_SALES_URL.format(f=df, t=dt))
        time.sleep(args.seconds)

    for r in records:   # 요청 바디(POST) 연결
        if r["url"] in posts:
            r["post_data"] = posts[r["url"]]

    out = out_dir / f"sales_xhr_{args.account_id}_{dt}.json"
    out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  캡처 {len(records)}건 → {out}")
    for r in records:
        print(f"   [{r['status']}] {r['method']} {r['url'][:100]}"
              + (f"  (json {r.get('body_len','?')}B)" if "json" in r["content_type"] else ""))
    print("\n  → 이 목록에서 상품별×옵션별 노출/판매/방문이 담긴 API 를 골라 collector 직접호출로 전환합니다.")


if __name__ == "__main__":
    main()
