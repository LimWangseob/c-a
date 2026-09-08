"""로켓그로스 재고현황 API(rfm-inventory) 요청·응답 실물 캡처 — **사무실에서 1회 실행**.

새 서식의 '재고현황(판매가능 재고수량)'을 vi-detail-search처럼 **데이터 API 직접조회**로 채우기 위해,
재고관리 페이지가 부르는 데이터 API의 실제 형태(URL·메서드·바디·응답 필드)를 뜬다(추측 금지 원칙).

동작: 실제 로그인 프로필로 재고관리 페이지 이동 → 오간 XHR/fetch 중 상품/재고를 담은 JSON을 찾아
       URL·메서드·바디·응답을 output/_capture_inventory_*.json 에 저장 + 콘솔 요약.

사용: python tools/capture_inventory_api.py <로켓그로스계정ID>
⚠️ 위탁계정 반복 실행 금지. 재고현황은 로켓그로스(계약) 계정에만 있음.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics.browser import WING_URL, WingBrowser        # noqa: E402
from coupang_analytics.pipeline import account_profile             # noqa: E402

_INVENTORY_URL = "https://wing.coupang.com/tenants/rfm-inventory/management/list"
_SENSITIVE = ("cookie", "authorization", "set-cookie")


def main() -> int:
    if len(sys.argv) < 2:
        print("사용: python tools/capture_inventory_api.py <로켓그로스계정ID>")
        return 2
    account_id = sys.argv[1]
    print(f"[캡처] 계정={account_id} — 로켓그로스 재고현황 API 탐색")
    # 메타데이터만 즉시 수집(body 읽기 없음 — 끝나지 않는 롱폴/스트리밍 응답에서 resp.json()/text()가
    # 무한 블록되는 것을 회피). body는 아래에서 JSON content-type인 응답만 골라 읽는다.
    metas: list[dict] = []
    resp_by_id: dict[int, object] = {}
    with WingBrowser(profile_dir=account_profile(account_id), offscreen=True) as b:
        def on_response(resp):
            try:
                if resp.request.resource_type not in ("xhr", "fetch"):
                    return
                req = resp.request
                ct = (resp.headers.get("content-type") or "").lower()   # 헤더는 body 대기 없이 즉시 가용
                rid = id(resp)
                resp_by_id[rid] = resp
                metas.append({"_id": rid, "url": resp.url, "method": req.method,
                              "status": resp.status, "content_type": ct,
                              "request_headers": {k: v for k, v in req.headers.items()
                                                  if k.lower() not in _SENSITIVE},
                              "post_data": req.post_data})
            except Exception:
                pass
        b.page.on("response", on_response)

        b.goto(WING_URL)
        b.page.wait_for_timeout(1500)
        if not b.authenticated():
            print("[캡처] 세션 없음 → 창을 띄웁니다. 직접 로그인하세요(최대 5분).")
            b.show()
            if not b.wait_for_login(timeout=300, on_log=print, tag=account_id):
                print("[캡처] 로그인 미완료 — 중단")
                return 1
            b.hide()

        ts = time.strftime("%y%m%d_%H%M%S")
        out_dir = Path("output")
        out_dir.mkdir(exist_ok=True)

        print(f"[캡처] 재고관리 이동: {_INVENTORY_URL}")
        b.page.goto(_INVENTORY_URL, wait_until="domcontentloaded", timeout=60000)
        try:                                    # SPA 데이터 로드까지 기다림(홈 리다이렉트/지연 진단)
            b.page.wait_for_load_state("networkidle", timeout=25000)
        except Exception:
            print("[캡처] networkidle 미도달(25s) — 계속")
        b.page.wait_for_timeout(4000)
        b.page.remove_listener("response", on_response)   # 이후 새 응답 수집 중단(안정적으로 처리)

        # 페이지 실측 — 최종 URL(홈으로 튕겼는지)·본문 텍스트·스크린샷(재고 API 미출현 원인 파악)
        print(f"[캡처] 최종 URL: {b.page.url}")
        try:
            body_txt = b.page.inner_text("body")
            print(f"[캡처] 본문 텍스트(앞 800자):\n{body_txt[:800]}")
        except Exception as exc:
            print(f"[캡처] 본문 텍스트 실패: {exc.__class__.__name__}")
        shot = out_dir / f"_capture_inventory_{account_id}_{ts}.png"
        try:
            b.page.screenshot(path=str(shot), full_page=True)
            print(f"[캡처] 스크린샷: {shot}")
        except Exception as exc:
            print(f"[캡처] 스크린샷 실패: {exc.__class__.__name__}")
        print(f"[캡처] XHR/fetch 응답 {len(metas)}건 관측")

        # ① 메타데이터(URL·메서드·상태·타입·요청바디)를 body 없이 먼저 저장 — 무조건 확보(hang 무관).
        records = [{k: v for k, v in m.items() if k != "_id"} for m in metas]
        meta_out = out_dir / f"_capture_inventory_meta_{account_id}_{ts}.json"
        meta_out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[캡처] 메타 저장: {meta_out}")
        print("\n=== 관측된 XHR/fetch 전체(재고 API 특정용) ===")
        for r in records:
            print(f"    [{r['method']} {r['status']} {r['content_type'][:24]}] {r['url'][:100]}")

        # ② body는 '재고/상품 데이터 API로 보이는 URL'과 일치하는 JSON 응답만 읽음
        #    (무관한 롱폴/알림 스트림은 손대지 않아 resp.json() 무한블록 회피).
        url_pat = re.compile(r"inventory|stock|sellable|quantity|management|item|product|vendor|rfm", re.I)
        print("\n=== 재고 후보 body 수집 ===")
        for m, r in zip(metas, records):
            if "json" not in m["content_type"] or not url_pat.search(m["url"]):
                continue
            resp = resp_by_id.get(m["_id"])
            try:
                r["json"] = resp.json()
            except Exception as exc:
                r["body_error"] = f"{exc.__class__.__name__}"
                continue
            body = json.dumps(r["json"], ensure_ascii=False)
            hit = any(k in body for k in ("inventory", "재고", "stock", "sellable", "vendorItem", "quantity"))
            mark = "★재고후보" if hit else "  "
            print(f"  {mark} [{r['method']} {r['status']}] {r['url'][:110]}")
            if r.get("post_data"):
                print(f"       요청바디: {str(r['post_data'])[:250]}")
            print(f"       응답앞부분: {body[:400]}")

        out = out_dir / f"_capture_inventory_{account_id}_{ts}.json"
        out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[캡처] 저장: {out}  (요청 {len(records)}건)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
