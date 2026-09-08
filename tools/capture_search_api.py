"""쿠팡 검색결과 데이터 API 존재 여부 캡처 — **순위조회 속도 개선용, 라이브 1회**.

지금 순위조회는 검색 HTML 페이지를 통째로 렌더링하며 100위까지 스캔해 느리다. 판매수집을 vi-detail-search
JSON 직접조회로 바꿔 빨라졌듯, 검색결과도 **JSON API가 있으면 렌더링 없이 직접 받아** 대폭 빨라진다.
이 도구는 비로그인 쿠팡 검색 페이지에서 오간 요청을 모두 떠서 **상품 목록을 주는 JSON 엔드포인트**를 찾는다.

동작: 비로그인 rank 프로필로 쿠팡 홈 워밍업 → 검색 이동 → XHR/fetch·문서 요청을 URL·타입·JSON여부로 수집
→ `output/_capture_search_*.json` 저장 + 상품ID(vp/products)가 담긴 응답을 콘솔에 요약.

사용: python tools/capture_search_api.py [검색어]   (생략 시 '화로테이블')
⚠️ 비로그인이라 계정 위험 없음. 다만 반복 실행은 IP 플래그 위험 → 1~2회만.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics.browser import WingBrowser        # noqa: E402
from coupang_analytics.rank import warmup                # noqa: E402

_SEARCH = "https://www.coupang.com/np/search?q={q}&page=1"


def main() -> int:
    keyword = sys.argv[1] if len(sys.argv) > 1 else "화로테이블"
    out_txt = Path("output") / "_capture_search_result.txt"
    out_txt.parent.mkdir(exist_ok=True)
    _fh = out_txt.open("w", encoding="utf-8")

    def pr(msg=""):
        print(msg)
        _fh.write(str(msg) + "\n")
        _fh.flush()

    pr(f"[캡처] 검색어='{keyword}' — 검색결과 JSON API 탐색(비로그인)")
    try:
        _run(keyword, pr)
    except Exception as exc:
        import traceback
        pr(f"[캡처] ✖ 오류 — {exc.__class__.__name__}: {exc}")
        pr(traceback.format_exc()[:1500])
        _fh.close()
        return 1
    pr(f"[캡처] 결과 텍스트: {out_txt}")
    _fh.close()
    return 0


def _run(keyword: str, pr) -> None:
    responses = []
    with WingBrowser(profile_dir="data/chrome-capture-search", offscreen=True) as b:
        warmup(b)   # 쿠팡 홈(쿠키 초기화 + Akamai 쿠키 확보)

        def on_response(resp):
            try:
                rt = resp.request.resource_type
                if rt in ("xhr", "fetch", "document") or "search" in resp.url:
                    responses.append(resp)
            except Exception:
                pass
        b.page.on("response", on_response)

        b.page.goto(_SEARCH.format(q=quote(keyword)), wait_until="domcontentloaded", timeout=30000)
        b.page.wait_for_timeout(6000)

        records = []
        for resp in responses:
            u = resp.url
            rt = resp.request.resource_type
            rec = {"url": u, "method": resp.request.method, "status": resp.status, "type": rt}
            ctype = (resp.headers or {}).get("content-type", "")
            rec["content_type"] = ctype
            if "json" in ctype:
                try:
                    body = resp.text()
                    rec["has_products"] = "vp/products" in body or "productId" in body
                    rec["json_head"] = body[:400]
                except Exception as exc:
                    rec["body_error"] = f"{exc.__class__.__name__}"
            records.append(rec)

        out = Path("output") / f"_capture_search_{time.strftime('%y%m%d_%H%M%S')}.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        pr(f"[캡처] 저장: {out}  (요청 {len(records)}건)")

        pr("\n=== JSON 응답(상품 포함 여부) ===")
        json_recs = [r for r in records if "json" in r.get("content_type", "")]
        if not json_recs:
            pr("  JSON 응답 없음 → 검색결과는 SSR HTML(별도 상품 API 없음)일 가능성.")
            pr("  이 경우 속도개선은 ①이미지·폰트·CSS 로딩 차단 ②스캔깊이·지연 조정으로.")
        for r in json_recs:
            mark = "★상품포함" if r.get("has_products") else ""
            pr(f"  [{r['method']} {r['status']}] {mark} {r['url'][:120]}")
            if r.get("has_products"):
                pr(f"     응답앞부분: {r.get('json_head','')[:200]}")
        pr("\n=== document(HTML) 응답 ===")
        for r in records:
            if r["type"] == "document":
                pr(f"  [{r['method']} {r['status']}] {r['url'][:120]}")


if __name__ == "__main__":
    sys.exit(main())
