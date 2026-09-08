"""병렬 fetch 순위조회(organic_ranks_batch) 라이브 검증 — 비로그인 검색만(계정 위험 없음).

병렬 fetch 방식이 ①실제로 되는지 ②기존 순차(organic_ranks)와 순위가 **일치**하는지 ③얼마나 빠른지 확인.
결과는 콘솔 + `output/_verify_rank_fetch.txt`.

사용: python tools/verify_rank_fetch_live.py [키워드1 키워드2 ...]  (생략 시 기본 3개)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics.browser import WingBrowser                       # noqa: E402
from coupang_analytics.rank import make_matcher, organic_ranks, organic_ranks_batch, warmup  # noqa: E402

# 이름에 이 문자열이 들어간 첫 오가닉 상품의 순위를 잰다(로그인 불필요 — 이름 매칭).
_DEFAULT_KWS = ["화로테이블", "바베큐테이블", "캠핑화로테이블"]
_MATCH = "테이블"


def main() -> int:
    kws = sys.argv[1:] or _DEFAULT_KWS
    out = Path("output") / "_verify_rank_fetch.txt"
    out.parent.mkdir(exist_ok=True)
    fh = out.open("w", encoding="utf-8")

    def pr(m=""):
        print(m)
        fh.write(str(m) + "\n")
        fh.flush()

    matchers = {"대상": make_matcher(name_substr=_MATCH)}   # 이름에 '테이블' 포함되는 첫 오가닉 순위
    pr(f"[검증] 키워드 {kws} · 매칭='{_MATCH}'")
    try:
        with WingBrowser(profile_dir="data/chrome-pipeline", offscreen=True) as b:
            warmup(b)

            t0 = time.time()
            batch = organic_ranks_batch(b, kws, matchers, log=pr)
            t_batch = time.time() - t0
            pr(f"\n[병렬 fetch] {t_batch:.1f}s (키워드 {len(kws)}개, PC)")
            for kw in kws:
                pr(f"    {kw}: {batch.get(kw)}")

            # 순차(기존) 방식과 비교(같은 매처, PC)
            t1 = time.time()
            seq = {kw: organic_ranks(b, kw, matchers, log=pr) for kw in kws}
            t_seq = time.time() - t1
            pr(f"\n[순차 navigation] {t_seq:.1f}s")
            for kw in kws:
                pr(f"    {kw}: {seq.get(kw)}")

            match = all(batch.get(k) == seq.get(k) for k in kws)
            pr(f"\n[결과] 순위 일치: {'✅ 동일' if match else '❌ 불일치(확인 필요)'}"
               f" · 속도: 병렬 {t_batch:.1f}s vs 순차 {t_seq:.1f}s"
               f" ({t_seq / t_batch:.1f}배 빠름)" if t_batch else "")
    except Exception as exc:
        import traceback
        pr(f"[검증] ✖ 오류 — {exc.__class__.__name__}: {exc}")
        pr(traceback.format_exc()[:1200])
        fh.close()
        return 1
    pr(f"[검증] 결과 파일: {out}")
    fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
