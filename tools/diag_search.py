"""검색 순위 가속 종합 진단 — 모든 가속 가설을 실측 기록(추정 배제). 비로그인, 계정 위험 없음.

각 테스트의 status·본문길이·상품수(ProductUnit)·소요시간을 output/_diag_search.txt 에 상세 기록한다.
이 결과만 보고 병렬 fetch 채택 여부/방식을 확정한다.

  T1 콜드 fetch(사전 검색 없이)            — Akamai 챌린지인지
  T2 검색 네비게이션(프라임) + DOM 상품수·소요 — 기준(현행 방식)
  T3 프라임 후 단일 fetch(다른 키워드)      — 네비로 Akamai 풀리면 fetch 되는가
  T4 프라임 후 fetch(같은 키워드 2페이지)    — 페이지네이션 fetch 되는가
  T5 프라임 후 병렬 fetch 3키워드 + 소요     — 병렬 가속 실측
  T6 Akamai 쿠키(워밍업 후 / 네비 후)        — 프라임 효과 근거

사용: python tools/diag_search.py
"""
from __future__ import annotations

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
from coupang_analytics.rank import _ITEM_SEL, warmup     # noqa: E402

_SEARCH = "https://www.coupang.com/np/search?q={q}&page={p}"

# fetch 1건 → 파싱해 상품수/챌린지 여부 반환
_FETCH_ONE = r"""
async (url) => {
  const s = performance.now();
  const r = await fetch(url, {credentials:'include', headers:{accept:'text/html,application/xhtml+xml'}});
  const t = await r.text();
  const doc = new DOMParser().parseFromString(t, 'text/html');
  const pu = doc.querySelectorAll("li[class*='ProductUnit_productUnit']").length;
  return {status:r.status, len:t.length, productUnit:pu,
          vp:(t.match(/\/vp\/products\//g)||[]).length,
          challenge: t.includes('sec-if-cpt-container')||t.includes('behavioral-content'),
          denied:/Access Denied|errors\.edgesuite/.test(t), ms: Math.round(performance.now()-s)};
}
"""

# 여러 url 병렬 fetch → 각 상품수
_FETCH_PARALLEL = r"""
async ({urls}) => {
  const one = async (url) => {
    const r = await fetch(url, {credentials:'include', headers:{accept:'text/html'}});
    const t = await r.text();
    const doc = new DOMParser().parseFromString(t, 'text/html');
    return {url, status:r.status, productUnit: doc.querySelectorAll("li[class*='ProductUnit_productUnit']").length, len:t.length};
  };
  const s = performance.now();
  const res = await Promise.all(urls.map(one));
  return {ms: Math.round(performance.now()-s), res};
}
"""

_AKAMAI = ("_abck", "bm_sz", "ak_bmsc", "bm_mi", "bm_sv")


def main() -> int:
    out = Path("output") / "_diag_search.txt"
    out.parent.mkdir(exist_ok=True)
    fh = out.open("w", encoding="utf-8")

    def pr(m=""):
        print(m)
        fh.write(str(m) + "\n")
        fh.flush()

    def cookie_summary(ctx):
        ck = {c["name"]: c.get("value", "") for c in ctx.cookies() if c["name"] in _AKAMAI}
        return ", ".join(f"{k}(len={len(v)})" for k, v in ck.items()) or "(없음)"

    def do(label, fn):
        try:
            fn()
        except Exception as exc:
            pr(f"  {label} ✖ 오류: {exc.__class__.__name__}: {str(exc)[:120]}")

    kw1, kw2, kw3 = "화로테이블", "바베큐테이블", "캠핑화로테이블"
    pr("[종합진단] 검색 순위 가속 가설 실측")
    try:
        with WingBrowser(profile_dir="data/chrome-pipeline", offscreen=True) as b:
            warmup(b)
            pr(f"\n[T6-a] 워밍업(홈) 후 Akamai 쿠키: {cookie_summary(b.context)}")

            def t1():
                r = b.page.evaluate(_FETCH_ONE, _SEARCH.format(q=quote(kw1), p=1))
                pr(f"\n[T1 콜드 fetch '{kw1}'] status={r['status']} len={r['len']} 상품수={r['productUnit']} "
                   f"vp={r['vp']} 챌린지={r['challenge']} denied={r['denied']} ({r['ms']}ms)")
            do("[T1]", t1)

            def t2():
                t0 = time.time()
                b.page.goto(_SEARCH.format(q=quote(kw1), p=1), wait_until="domcontentloaded", timeout=30000)
                b.page.wait_for_selector(_ITEM_SEL, timeout=15000)
                dom = len(b.page.query_selector_all(_ITEM_SEL))
                pr(f"\n[T2 네비게이션(프라임) '{kw1}'] DOM 상품수={dom} · 소요={time.time()-t0:.1f}s (현행 방식 기준)")
            do("[T2]", t2)

            pr(f"[T6-b] 네비게이션 후 Akamai 쿠키: {cookie_summary(b.context)}")

            def t3():
                r = b.page.evaluate(_FETCH_ONE, _SEARCH.format(q=quote(kw2), p=1))
                pr(f"\n[T3 프라임 후 fetch(다른키워드 '{kw2}')] status={r['status']} len={r['len']} "
                   f"상품수={r['productUnit']} vp={r['vp']} 챌린지={r['challenge']} ({r['ms']}ms)")
                pr(f"     → {'✅ 프라임 후 fetch 성공' if r['productUnit'] > 0 else '❌ 여전히 챌린지/빈응답'}")
            do("[T3]", t3)

            def t4():
                r = b.page.evaluate(_FETCH_ONE, _SEARCH.format(q=quote(kw1), p=2))
                pr(f"\n[T4 프라임 후 fetch(같은키워드 2페이지 '{kw1}')] status={r['status']} "
                   f"상품수={r['productUnit']} ({r['ms']}ms)")
            do("[T4]", t4)

            def t5():
                urls = [_SEARCH.format(q=quote(k), p=1) for k in (kw1, kw2, kw3)]
                r = b.page.evaluate(_FETCH_PARALLEL, {"urls": urls})
                pr(f"\n[T5 프라임 후 병렬 fetch 3키워드] 총소요={r['ms']}ms")
                for x in r["res"]:
                    pr(f"     status={x['status']} 상품수={x['productUnit']} len={x['len']} · {x['url'][-40:]}")
                ok = all(x["productUnit"] > 0 for x in r["res"])
                pr(f"     → {'✅ 병렬 fetch 전부 상품 확보 → 병렬 가속 채택 가능' if ok else '❌ 일부/전부 실패'}")
            do("[T5]", t5)
    except Exception as exc:
        import traceback
        pr(f"[종합진단] ✖ 치명 오류 — {exc.__class__.__name__}: {exc}")
        pr(traceback.format_exc()[:1000])
        fh.close()
        return 1
    pr(f"\n[종합진단] 결과 파일: {out}")
    fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
