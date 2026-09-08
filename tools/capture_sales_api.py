"""판매분석 데이터 API(vi-detail-search) 요청·응답 실물 캡처 — **사무실에서 1회 실행**.

목적: '엑셀 다운로드' 버튼을 사람처럼 클릭하는 대신, 페이지가 표 데이터를 받아오는 **데이터 API를
직접 fetch**로 바꾸기 위해 그 요청/응답의 **실제 형태**(URL·메서드·파라미터·응답 JSON 필드)를 뜬다.
추측 금지 원칙(fix-from-real-evidence)에 따라, 이 실물 캡처를 보고 collector.discover 를 직접-fetch로 교체한다.

동작:
- 실제 로그인 프로필로 WING 을 열고(세션 재사용, 없으면 창을 띄워 사람이 직접 로그인 — 위탁계정 무리 금지),
- 판매분석 페이지로 이동하며 그 사이 오간 데이터성 요청/응답을 모두 수집,
- URL·메서드·요청 파라미터(GET 쿼리/POST 바디)·응답 JSON 을 `output/_capture_sales_*.json` 로 저장,
- vi-detail-search 응답의 **스키마 요약**(최상위 키·리스트 경로·첫 행의 키/값)을 콘솔에 출력.

⚠️ 저장 파일에는 사업자 판매수치(본인 데이터)가 들어가니 로컬에서만 보관(`/output/`는 .gitignore). 쿠키·인증
헤더는 담지 않는다. 여러 번 반복 실행하지 말 것(계정 부하·IP 플래그).

사용: python tools/capture_sales_api.py <계정ID> [YYYY-MM-DD YYYY-MM-DD] [--click]
  날짜 생략 시 어제(D-1). --click 을 주면 '엑셀 다운로드'까지 눌러 **엑셀 내보내기 요청**도 함께 캡처
  (직접-fetch 대안 비교용). 기본은 클릭 없이 데이터 API 만 캡처.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:                       # 콘솔 인코딩과 무관하게 한글 출력
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics.browser import WING_URL, WingBrowser        # noqa: E402
from coupang_analytics.collector import _SALES_URL                 # noqa: E402
from coupang_analytics.pipeline import account_profile             # noqa: E402

# 데이터성 요청만 골라 담기 위한 URL 키워드(표 데이터 + 혹시 모를 내보내기 관련).
_KEYS = ("vi-detail-search", "business-insight", "sales-analysis",
         "download", "excel", "export", "report")
_SENSITIVE_HEADERS = ("cookie", "authorization", "x-csrf", "set-cookie")


def _safe_headers(headers: dict) -> dict:
    return {k: v for k, v in headers.items() if k.lower() not in _SENSITIVE_HEADERS}


def _schema(obj, depth: int = 0, max_depth: int = 3) -> str:
    """응답 JSON의 구조 요약(키·타입·리스트 첫 원소). 값은 짧게만 노출."""
    pad = "  " * depth
    if depth > max_depth:
        return pad + "…"
    if isinstance(obj, dict):
        lines = []
        for k, v in list(obj.items())[:30]:
            if isinstance(v, (dict, list)):
                lines.append(f"{pad}{k}:")
                lines.append(_schema(v, depth + 1, max_depth))
            else:
                sval = str(v)
                lines.append(f"{pad}{k} = {sval[:60]}")
        return "\n".join(lines)
    if isinstance(obj, list):
        head = f"{pad}[list len={len(obj)}]"
        return head if not obj else head + "\n" + _schema(obj[0], depth + 1, max_depth)
    return f"{pad}{str(obj)[:60]}"


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--click"]
    do_click = "--click" in sys.argv
    if not args:
        print("사용: python tools/capture_sales_api.py <계정ID> [YYYY-MM-DD YYYY-MM-DD] [--click]")
        return 2
    account_id = args[0]
    if len(args) >= 3:
        date_from, date_to = args[1], args[2]
    else:
        d = (date.today() - timedelta(days=1)).isoformat()
        date_from = date_to = d
    print(f"[캡처] 계정={account_id} · 기간 {date_from}~{date_to} · 엑셀클릭={do_click}")

    responses = []   # (resp) 나중에 바디를 읽는다(같은 페이지 유지 중이라 회수 가능)

    with WingBrowser(profile_dir=account_profile(account_id), offscreen=True) as b:
        def on_response(resp):
            try:
                if any(k in resp.url for k in _KEYS):
                    responses.append(resp)
            except Exception:
                pass
        b.page.on("response", on_response)

        b.goto(WING_URL)
        b.page.wait_for_timeout(1500)
        if not b.authenticated():
            print("[캡처] 세션 없음 → 창을 띄웁니다. 열린 창에서 직접 로그인하세요(최대 5분 대기).")
            b.show()
            if not b.wait_for_login(timeout=300, on_log=print, tag=account_id):
                print("[캡처] 로그인 미완료 — 중단")
                return 1
            b.hide()

        url = _SALES_URL.format(f=date_from, t=date_to)
        print(f"[캡처] 판매분석 이동: {url}")
        b.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        b.page.wait_for_timeout(8000)          # XHR·렌더 안정화

        if do_click:                            # 엑셀 내보내기 요청도 캡처(대안 비교용)
            try:
                b.page.get_by_text("엑셀 다운로드").first.click(no_wait_after=True)
                b.page.wait_for_timeout(1500)
                b.page.get_by_text("상품별 판매 리포트").first.click(no_wait_after=True)
                b.page.wait_for_timeout(6000)
                print("[캡처] 엑셀 다운로드 흐름 트리거함(내보내기 요청 캡처 시도)")
            except Exception as exc:
                print(f"[캡처] 엑셀 클릭 실패(무시): {exc.__class__.__name__}: {str(exc)[:80]}")

        # 수집한 응답의 바디를 읽어 저장
        records = []
        for resp in responses:
            req = resp.request
            rec = {"url": resp.url, "method": req.method, "status": resp.status,
                   "resource_type": req.resource_type,
                   "request_headers": _safe_headers(req.headers),
                   "post_data": req.post_data}
            try:
                rec["json"] = resp.json()
            except Exception:
                try:
                    rec["text_head"] = resp.text()[:2000]
                except Exception as exc:
                    rec["body_error"] = f"{exc.__class__.__name__}: {str(exc)[:80]}"
            records.append(rec)

        out_dir = Path("output")
        out_dir.mkdir(exist_ok=True)
        out = out_dir / f"_capture_sales_{account_id}_{time.strftime('%y%m%d_%H%M%S')}.json"
        out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[캡처] 저장: {out}  (요청 {len(records)}건)")

        # vi-detail-search 응답 스키마 요약 출력
        hits = [r for r in records if "vi-detail-search" in r["url"]]
        if not hits:
            print("[캡처] ⚠ vi-detail-search 응답이 안 잡혔습니다. 아래 잡힌 URL을 보고 데이터 API를 특정하세요:")
            for r in records:
                print(f"    - [{r['method']} {r['status']}] {r['url'][:110]}")
        for r in hits:
            print("=" * 70)
            print(f"[vi-detail-search] {r['method']} {r['status']} {r['url'][:110]}")
            if r.get("post_data"):
                print(f"  요청 바디: {r['post_data'][:300]}")
            if isinstance(r.get("json"), (dict, list)):
                print("  응답 스키마:")
                print(_schema(r["json"]))
            else:
                print(f"  응답(텍스트 앞부분): {r.get('text_head', r.get('body_error', '?'))[:300]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
