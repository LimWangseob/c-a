"""WING 세션 검증·회수 (합법 경로 — 실제 로그인 브라우저 컨텍스트만 사용).

ShopMine 의 `IsLoginOneTimeAsync`(생존검증) + `DoAfterLoginJobsAsync`(vendorId 추출) + 세션 3요소
회수에 대응하되, **HTTP 폼-POST 로그인/브라우저 위장 헤더/봇쿠키 회피는 하지 않는다**(정책: 지문위조 금지).
- `is_alive` : 로그인된 그 브라우저 컨텍스트의 요청으로 알림 API 가 OK 를 주는지(가벼운 생존 체크).
- `extract_vendor_id` : 배송관리 페이지 HTML 에서 vendorId 추출(WING 데이터 API 호출용).
- `capture` : 세션 3요소 + 전체 쿠키(_abck 등 포함)를 blob 으로 회수 → SessionStore 로 영속.

⚠️ 엔드포인트·정규식은 ShopMine 실측 기반이나 쿠팡 변경 시 깨질 수 있어 **사무실 라이브 1회 검증** 필요.
값(쿠키·토큰)은 로그·출력에 남기지 않는다.
"""
from __future__ import annotations

import re
import time

_NOTIFICATION_URL = "https://wing.coupang.com/winglayout/bell/notification/find?_={t}"
_DELIVERY_URL = "https://wing.coupang.com/tenants/sfl-portal/delivery/management"
_VENDOR_RE = re.compile(r"vendorId:\s*'([^']*)'")
_SESSION_TOKENS = ("WebSessionId", "PCID", "OAuthTokenRequestState")


def is_alive(page) -> bool:
    """로그인 세션 생존 여부 — 알림 API 응답에 'OK' 포함 여부(같은 컨텍스트라 세션 쿠키 사용).

    전체 대시보드 로드보다 가벼운 프록시. 네트워크 오류는 예외로 전파(무음 아님).
    """
    resp = page.context.request.get(_NOTIFICATION_URL.format(t=int(time.time() * 1000)))
    if not resp.ok:
        return False
    return "OK" in resp.text()


def extract_vendor_id(page) -> str | None:
    """배송관리 페이지 HTML 에서 vendorId 추출. 못 찾으면 None(호출부가 로그·판단)."""
    page.goto(_DELIVERY_URL, wait_until="domcontentloaded", timeout=30000)
    m = _VENDOR_RE.search(page.content())
    return m.group(1) if m else None


def capture(context, vendor_id: str | None = None) -> dict:
    """세션 3요소 + 전체 쿠키를 회수(SessionStore.save 용 blob). 값은 반환만, 출력 금지."""
    cookies = context.cookies()
    tokens = {c["name"]: c["value"] for c in cookies if c.get("name") in _SESSION_TOKENS}
    return {"vendor_id": vendor_id, "tokens": tokens, "cookies": cookies}
