"""진단 — 노출순위 프록시 풀의 각 egress 가 지금 차단되는지 실측.

A/B(이미지) 가 전부 차단으로 무효 → 원인 규명: sessid 고정 IP 들이 막혔는지, no-sessid(회전)는
통과하는지. 각 후보로 ①실제 egress IP 에코 ②쿠팡 1검색 차단여부 를 찍는다.

실행: PYTHONPATH=src python tools/probe_proxy_pool.py
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from coupang_analytics import config, proxy_pool, rank, proxy_blocklist   # noqa: E402
from coupang_analytics.browser import WingBrowser                         # noqa: E402
from coupang_analytics.pipeline_paths import _PROFILE                     # noqa: E402

KW = "캠핑타프"


def main():
    config.PROXY_ENABLED = True
    config.PROXY_ALLOW_AUTH = True
    proxy_pool.reset_cache()
    pool = proxy_pool.rank_proxy_pool_urls()
    if not pool:
        print("프록시 풀 비어있음", flush=True)
        return
    # no-sessid(아침 방식) = 첫 줄에서 ;sessid.sNN 제거
    no_sessid = re.sub(r';sessid\.[^;:@]+', '', pool[0])
    candidates = [("no-sessid(회전)", no_sessid)] + [
        (re.search(r'sessid\.(\w+)', u).group(1) if re.search(r'sessid\.(\w+)', u) else f"n{i}", u)
        for i, u in enumerate(pool)
    ]
    print(f"후보 {len(candidates)}개 (no-sessid + sessid {len(pool)}개) · 각 1검색", flush=True)
    clean = 0
    for name, url in candidates:
        egress = None
        blocked = loaded = False
        try:
            with WingBrowser(profile_dir=_PROFILE, offscreen=True, proxy=url, block_images=False) as b:
                egress = proxy_blocklist.resolve_egress_ip(b)
                try:
                    rank.warmup(b)
                    loaded = bool(rank._load_results(b, KW, log=lambda m: None))
                except rank.RankBlocked:
                    blocked = True
                except Exception as e:
                    print(f"  [{name}] 검색예외 {type(e).__name__}: {str(e)[:60]}", flush=True)
        except Exception as e:
            print(f"  [{name}] 연결예외 {type(e).__name__}: {str(e)[:60]}", flush=True)
        tag = "차단" if blocked else ("통과" if loaded else "미로드(결과없음/기타)")
        if loaded and not blocked:
            clean += 1
        print(f"  [{name}] egress={egress or '?'}  {tag}", flush=True)
        time.sleep(12)
    print(f"\n요약: 통과 egress {clean}/{len(candidates)}", flush=True)
    if clean:
        print("→ 일부 IP는 깨끗 = 회전/선제skip 이 유효(drive_rank 가 통과 IP 찾아감)", flush=True)
    else:
        print("→ 전부 차단 = 현재 풀 평판 전반 나쁨(업체/시간대 문제 — 코드/이미지 아님)", flush=True)


if __name__ == "__main__":
    main()
