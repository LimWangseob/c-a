"""정산 화면 데이터 주소(API) 실측 기록 — 정산 2단계 ②용 **읽기 전용 관찰 도구**. SSOT=designs/SETTLEMENT_MODULE.md §9.

WING 정산 화면(정산현황·매출내역·로켓그로스 정산현황·부가 리포트 탭)이 어떤 데이터 주소를 부르는지 `[미확인]`이라,
**사무실에서 사람이 직접** 한 계정으로 로그인한 뒤 정산 메뉴를 눌러 보는 동안 브라우저가 주고받는 요청을 기록한다.

- 앱과 같은 반자동 로그인(보이는 창·비번 자동입력·2차인증은 사람). 도구는 **아무 요청도 스스로 보내지 않는다**(관찰만).
- 기록 = 방식·주소 경로·질의 **이름**·요청 본문 **키 이름**·응답 **구조**(키 이름·자료형). 금액·상품명·주문번호 같은
  **값은 저장하지 않는다**. 엑셀 다운로드는 파일 이름·주소만 기록(파일은 저장하지 않음).
- 결과 = `output/_diag/settlement_endpoints_{계정}_{시각}.json` + 화면 요약(정산 관련 주소 우선).

사용(사무실):
  python tools/diag_settlement_endpoints.py <계정ID>
  → 보이는 창에서 로그인 확인 후, 정산 메뉴를 차례로 누르고(엑셀 다운로드 버튼 포함) 콘솔에서 Enter.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

_HINTS = ("settle", "revenue", "sales", "fee", "rfm", "milk", "ad", "cfs", "fulfil", "payment", "commission")
_MAX_DEPTH = 4


def _key_label(k: str) -> str:
    """키가 데이터처럼 생겼으면(숫자 ID·날짜) 자리표시로 — ID/날짜를 키로 쓰는 응답에서 값 노출 방지."""
    if re.fullmatch(r"\d{5,}", k):
        return "<숫자키>"
    if re.fullmatch(r"\d{4}[-./]?\d{2}([-./]?\d{2})?", k):
        return "<날짜키>"
    return k


def shape(obj, depth: int = 0):
    """JSON 값 → 구조만(키 이름·자료형). 목록은 첫 원소 구조 + 길이. 값은 버린다(데이터 모양 키도 자리표시)."""
    if depth >= _MAX_DEPTH:
        return type(obj).__name__
    if isinstance(obj, dict):
        out: dict = {}
        for k, v in obj.items():
            out.setdefault(_key_label(str(k)), shape(v, depth + 1))
        return out
    if isinstance(obj, list):
        return {"__list__": len(obj), "item": shape(obj[0], depth + 1) if obj else None}
    return type(obj).__name__


def body_keys(post_data: str | None):
    """요청 본문 → 키 구조(JSON 이면 shape, 폼이면 이름 목록, 그 외 길이만)."""
    if not post_data:
        return None
    try:
        return shape(json.loads(post_data))
    except ValueError:
        if "=" in post_data:                          # 폼(a=1&b=2)만 이름 추출 — 일반 텍스트를 이름으로 오인하면 값 노출
            return {"__form__": sorted({k for k, _ in parse_qsl(post_data, keep_blank_values=True)})}
        return {"__text_len__": len(post_data)}


def entry(method: str, url: str, status: int, rtype: str, ctype: str, post_data, payload, err: str = "") -> dict:
    u = urlsplit(url)
    return {"method": method, "host": u.netloc, "path": u.path,
            "query": sorted({k for k, _ in parse_qsl(u.query, keep_blank_values=True)}),
            "status": status, "type": rtype, "content_type": ctype.split(";")[0],
            "request": body_keys(post_data), "response": shape(payload) if payload is not None else None,
            **({"body_error": err} if err else {})}


def likely_settlement(e: dict) -> bool:
    p = e["path"].lower()
    return any(h in p for h in _HINTS)


def summarize(entries: list) -> list[str]:
    seen, lines = set(), []
    for e in sorted(entries, key=lambda e: (not likely_settlement(e), e["path"])):
        k = (e["method"], e["host"], e["path"])
        if k in seen:
            continue
        seen.add(k)
        mark = "★" if likely_settlement(e) else " "
        lines.append(f"{mark} {e['method']:6} {e['status']} {e['host']}{e['path']}"
                     + (f"  ?{','.join(e['query'])}" if e["query"] else ""))
    return lines


def _on_response(entries: list):
    def handler(resp):
        req = resp.request
        if req.resource_type not in ("xhr", "fetch") or "coupang.com" not in req.url:
            return
        ctype = resp.headers.get("content-type", "")
        payload, err = None, ""
        if "json" in ctype:
            try:
                payload = resp.json()
            except Exception as exc:                  # 본문을 못 읽으면 그 사실을 기록(조용히 버리지 않음)
                err = f"{exc.__class__.__name__}: {str(exc)[:80]}"
        entries.append(entry(req.method, req.url, resp.status, req.resource_type, ctype, req.post_data, payload, err))
    return handler


def _on_download(downloads: list):
    def handler(dl):
        downloads.append({"url_path": urlsplit(dl.url).path, "file": dl.suggested_filename})
        dl.cancel()                                   # 파일은 받지 않음(값 비저장)
    return handler


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1].startswith("-"):
        print(__doc__)
        return 2
    account_id = argv[1]
    from coupang_analytics import config
    from coupang_analytics.browser import WingBrowser
    from coupang_analytics.credstore import CredStore
    from coupang_analytics.input_list import Account
    from coupang_analytics.pipeline_sales import (LoginBlocked, LoginCredentialError, _ensure_login,
                                                  account_profile)

    def log(m: str) -> None:
        print(config.format_log(m))
    pw = CredStore().get_password(account_id)
    if not pw:
        log(f"계정 {account_id} 비밀번호가 저장돼 있지 않음 — 앱에서 관리대장을 한 번 불러온 뒤 다시 실행")
        return 1
    entries: list = []
    downloads: list = []
    with WingBrowser(profile_dir=account_profile(account_id), offscreen=False) as b:
        try:
            ok = _ensure_login(b, Account(account_id, "", ""), pw, log, login=True, semi=True)
        except (LoginBlocked, LoginCredentialError) as exc:   # 비번 오류=재시도 금지 정책 그대로(여기서 끝냄)
            log(f"로그인 중단: {exc.__class__.__name__} — 재시도하지 않음(아무것도 기록하지 않음)")
            return 1
        if not ok:
            log("로그인 미완료 — 종료(아무것도 기록하지 않음)")
            return 1
        b.context.on("response", _on_response(entries))
        b.page.on("download", _on_download(downloads))
        b.show()
        log("기록 시작 — 보이는 창에서 정산 메뉴(정산현황·매출내역·로켓그로스 정산현황·부가 리포트 탭·엑셀 다운로드)를 "
            "차례로 눌러 주세요. 다 누르셨으면 이 콘솔에서 Enter")
        input()
        b.page.wait_for_timeout(1500)                 # 마지막 응답 수신 여유
    out = ROOT / "output" / "_diag" / f"settlement_endpoints_{account_id}_{datetime.now():%y%m%d_%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"account": account_id, "entries": entries, "downloads": downloads},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"기록 {len(entries)}건·다운로드 {len(downloads)}건 → {out}")
    for line in summarize(entries):
        print("  " + line)
    for d in downloads:
        print(f"  ⬇ {d['url_path']}  ({d['file']})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
