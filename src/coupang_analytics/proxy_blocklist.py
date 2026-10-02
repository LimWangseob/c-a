"""노출순위(③) egress IP 차단목록 — 차단 이력이 있는 egress IP를 기억해 재사용을 피한다.

왜 필요한가
-----------
Model A(여러 sticky 세션)에서 proxies.txt 각 줄은 **게이트웨이**일 뿐, 쿠팡 Akamai가 보는 **실제
egress IP** 는 그 뒤에서 세션(sessid)마다 다르다. "차단당한 IP를 skip"하려면 게이트웨이 URL이 아니라
**실제 egress IP** 를 알고 기억해야 한다. 그래서:

* ``resolve_egress_ip(browser)`` — 브라우저(프록시 경유) 자신이 보는 공인 IP를 에코 사이트로 확인.
  (coupang 이 아니라 ipify 등 → 쿠팡 평판을 태우지 않음. 브라우저가 직접 찍어야 Chrome egress와 일치.)
* ``record(ip, reason)`` — 차단당한 egress IP 를 파일에 기록(시각·횟수·사유).
* ``is_blocked(ip)`` — 그 IP 가 (미만료) 차단이력에 있는지.
* 만료: ``RANK_PROXY_BLOCKLIST_TTL_SEC``(기본 72h) 지난 항목은 로드 시 제거 — 주거용 IP 는 회복되므로
  영구 낙인 금지(풀이 말라붙는 것 방지).

저장 위치: ``data_root()/RANK_PROXY_BLOCKLIST_FILE``(gitignore·운영 상태·비밀 아님). 런타임은 단일 세션
직렬이라 경합이 없지만, 쓰기는 temp+os.replace 로 원자적으로 한다(중단 시 파일 손상 방지).
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
from datetime import datetime
from typing import Optional

from . import config

# ipify/ifconfig 응답에서 첫 IPv4 또는 IPv6 추출.
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6 = re.compile(r"\b(?:[0-9A-Fa-f]{1,4}:){2,7}[0-9A-Fa-f]{0,4}\b")


def _path() -> str:
    name = getattr(config, "RANK_PROXY_BLOCKLIST_FILE", "rank_blocked_ips.json")
    try:
        from . import apppaths

        return os.path.join(apppaths.data_root(), name)
    except Exception:
        return name


def _ttl_sec() -> float:
    return float(getattr(config, "RANK_PROXY_BLOCKLIST_TTL_SEC", 259200))


def parse_ip(text: str) -> Optional[str]:
    """에코 응답 문자열에서 공인 IP 하나를 뽑는다. 못 찾으면 None."""
    if not text:
        return None
    m = _IPV4.search(text)
    if m:
        return m.group(0)
    m = _IPV6.search(text)
    return m.group(0) if m else None


def load() -> dict:
    """차단목록 로드 + 만료 항목 제거. {ip: {first, last, last_ts, count, last_reason}}."""
    path = _path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        # 손상/부분쓰기 파일은 빈 목록으로(다음 record 때 재생성). 조용한 폴백 아님 — 재기록됨.
        return {}
    if not isinstance(data, dict):
        return {}
    now = time.time()
    ttl = _ttl_sec()
    return {
        ip: rec
        for ip, rec in data.items()
        if isinstance(rec, dict) and (now - float(rec.get("last_ts", 0) or 0)) < ttl
    }


def save(data: dict) -> None:
    """원자적 저장(temp+replace)."""
    path = _path()
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def is_blocked(ip: Optional[str], data: Optional[dict] = None) -> bool:
    """ip 가 (미만료) 차단이력에 있으면 True. data 를 넘기면 그걸, 아니면 load()."""
    if not ip:
        return False
    d = data if data is not None else load()
    return ip in d


def entry(ip: Optional[str], data: Optional[dict] = None) -> Optional[dict]:
    """ip 의 차단 기록(first/last/count/last_reason) 반환 — 로그용. 없으면 None."""
    if not ip:
        return None
    d = data if data is not None else load()
    return d.get(ip)


def record(ip: Optional[str], reason: str = "") -> dict:
    """차단당한 egress IP 기록(있으면 count++·last 갱신). 갱신된 전체 dict 반환."""
    d = load()
    if not ip:
        return d
    now = time.time()
    nowstr = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rec = d.get(ip)
    if not isinstance(rec, dict):
        rec = {"first": nowstr, "count": 0}
    rec["last"] = nowstr
    rec["last_ts"] = now
    rec["count"] = int(rec.get("count", 0) or 0) + 1
    if reason:
        rec["last_reason"] = reason
    d[ip] = rec
    save(d)
    return d


def count(data: Optional[dict] = None) -> int:
    """현재 (미만료) 차단 IP 개수 — 종료 요약 로그용."""
    d = data if data is not None else load()
    return len(d)


def resolve_egress_ip(browser, log=None) -> Optional[str]:
    """브라우저(프록시 경유) 자신이 보는 공인 egress IP. 에코 URL을 순서대로 시도, 모두 실패 시 None.

    브라우저가 직접 찍어야 Chrome 의 ``--proxy-server`` egress 와 일치한다(별도 requests 로 찍으면
    sticky 세션이 달라 egress 가 어긋날 수 있음). coupang 이 아니라 ipify 등이라 평판을 태우지 않는다.
    """
    urls = getattr(config, "RANK_PROXY_EGRESS_ECHO_URLS",
                   ("https://api.ipify.org?format=json",))
    for url in urls:
        try:
            browser.page.goto(url, wait_until="domcontentloaded", timeout=15000)
            text = browser.page.evaluate(
                "() => document.body ? document.body.innerText : ''") or ""
            ip = parse_ip(text)
            if ip:
                return ip
        except Exception as exc:
            if log:
                host = url.split("//")[-1].split("/")[0]
                log(config.format_log(
                    f"  [프록시] egress 확인 실패({host}: {exc.__class__.__name__}) — 다음 경로 시도"))
            continue
    return None


__all__ = [
    "parse_ip", "load", "save", "is_blocked", "entry", "record", "count",
    "resolve_egress_ip",
]
