"""라이브 A/B — 노출순위 이미지 ON vs OFF (프록시 경유).

목적: 이미지 끄기가 ①차단을 유발하는가 ②트래픽을 얼마나 줄이는가 실측.
- 각 모드에 서로 다른 깨끗한 sticky 프록시(sessid) 배정(IP 평판 확보).
- 검색마다 rank._load_results 로 실제 타이핑+Enter 로드 → 차단 여부 판정.
- CDP Network 로 검색당 실제 전송 바이트(encodedDataLength) + 이미지 비중 측정(CORS 무관 정확).

실행: PYTHONPATH=src python tools/test_rank_images_live.py
⚠ 실제 쿠팡에 프록시로 접속한다(③ 비로그인 공개검색). 로그인·수집 아님.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from coupang_analytics import config, proxy_pool, rank          # noqa: E402
from coupang_analytics.browser import WingBrowser               # noqa: E402
from coupang_analytics.pipeline_paths import _PROFILE           # noqa: E402

KEYWORDS = ["캠핑타프", "무선이어폰", "텀블러"]
NAV_DELAY_SEC = 40          # 검색 사이 간격(두 모드 동일 — 이미지 변수만 비교)


def _attach_network_meter(browser):
    """CDP Network 로 검색당 실제 전송 바이트 측정. 반환 (reset, read)."""
    cdp = browser.context.new_cdp_session(browser.page)
    cdp.send("Network.enable")
    st = {"tot": 0, "img": 0, "rtype": {}}

    def _on_resp(p):
        st["rtype"][p.get("requestId")] = p.get("type")

    def _on_fin(p):
        n = p.get("encodedDataLength") or 0
        st["tot"] += n
        if st["rtype"].get(p.get("requestId")) == "Image":
            st["img"] += n

    cdp.on("Network.responseReceived", _on_resp)
    cdp.on("Network.loadingFinished", _on_fin)

    def reset():
        st["tot"] = 0
        st["img"] = 0
        st["rtype"].clear()

    def read():
        return dict(tot=st["tot"], img=st["img"])

    return reset, read


def run_mode(px, block_images: bool):
    label = "OFF(이미지없음)" if block_images else "ON(이미지있음)"
    print(f"\n=== 모드: 이미지 {label} ===", flush=True)
    rows = []
    with WingBrowser(profile_dir=_PROFILE, offscreen=True, proxy=px, block_images=block_images) as b:
        try:
            rank.warmup(b)
        except Exception as e:
            print(f"  warmup 실패/차단: {type(e).__name__}: {str(e)[:80]}", flush=True)
        reset, read = _attach_network_meter(b)
        for i, kw in enumerate(KEYWORDS):
            reset()
            blocked = loaded = False
            try:
                loaded = bool(rank._load_results(b, kw, log=lambda m: None))
            except rank.RankBlocked:
                blocked = True
            except Exception as e:
                print(f"  [{kw}] 예외 {type(e).__name__}: {str(e)[:80]}", flush=True)
            time.sleep(1.0)   # loadingFinished 이벤트 수신 여유
            mb = read()
            print(f"  [{kw}] blocked={blocked} loaded={loaded} "
                  f"총={mb['tot']//1024}KB 이미지={mb['img']//1024}KB "
                  f"(이미지비중 {100*mb['img']//max(mb['tot'],1)}%)", flush=True)
            rows.append((kw, blocked, loaded, mb["tot"], mb["img"]))
            if i < len(KEYWORDS) - 1:
                time.sleep(NAV_DELAY_SEC)
    return rows


def main():
    config.PROXY_ENABLED = True
    config.PROXY_ALLOW_AUTH = True
    proxy_pool.reset_cache()
    pool = proxy_pool.rank_proxy_pool_urls()
    if len(pool) < 2:
        print(f"프록시 풀이 {len(pool)}개 — 2개 이상 필요(proxies.txt sessid 여러 줄)", flush=True)
        return
    # 깨끗한 egress(진단에서 통과한 sessid)를 우선 배정 — 막힌 IP로 측정 무효화 방지.
    # 인자로 sessid 2개 지정 가능: python tools/test_rank_images_live.py s04 s05
    import re as _re
    want = sys.argv[1:3] if len(sys.argv) >= 3 else ["s04", "s05"]
    def _by_sess(tag):
        return next((u for u in pool if _re.search(rf'sessid\.{tag}\b', u)), None)
    px_on = _by_sess(want[0]) or pool[0]
    px_off = _by_sess(want[1]) or pool[1]
    print(f"프록시 풀 {len(pool)}개 · ON=sessid[0] OFF=sessid[1] · 간격 {NAV_DELAY_SEC}s · 키워드 {len(KEYWORDS)}개", flush=True)

    on = run_mode(px_on, block_images=False)
    off = run_mode(px_off, block_images=True)

    def summ(rows):
        nb = sum(1 for r in rows if r[1])
        nl = sum(1 for r in rows if r[2])
        avg = sum(r[3] for r in rows) // max(len(rows), 1)
        aimg = sum(r[4] for r in rows) // max(len(rows), 1)
        return nb, nl, avg, aimg

    onb, onl, ont, oni = summ(on)
    ofb, ofl, oft, ofi = summ(off)
    print("\n================ 요약 ================", flush=True)
    print(f"이미지 ON : 차단 {onb}/{len(on)} · 로드성공 {onl}/{len(on)} · 검색당 평균 총 {ont//1024}KB(이미지 {oni//1024}KB)", flush=True)
    print(f"이미지 OFF: 차단 {ofb}/{len(off)} · 로드성공 {ofl}/{len(off)} · 검색당 평균 총 {oft//1024}KB(이미지 {ofi//1024}KB)", flush=True)
    if ont:
        print(f"트래픽 절감: 검색당 {max(ont-oft,0)//1024}KB (~{100*max(ont-oft,0)//max(ont,1)}%)", flush=True)
    print(f"차단 관련성: ON 차단 {onb} vs OFF 차단 {ofb} "
          f"→ {'OFF에서 차단 증가(이미지 끄기 의심)' if ofb > onb else '유의미한 차이 없음(이미지 끄기 안전 추정)'}", flush=True)


if __name__ == "__main__":
    main()
