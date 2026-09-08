"""HTTP 폼-POST 기반 쿠팡 로그인 (ShopMine 방식).

Keycloak 리디렉션 체인 자동 추적 → ID/PW 제출 → 2FA 콜백 → 세션 영속.
"""
from __future__ import annotations

import re
import time
from typing import Callable, Optional
from urllib.parse import urljoin

import requests

# ShopMine 실측 브라우저 위장 헤더
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0",
    "sec-ch-ua": '"Chromium";v="150", "Microsoft Edge";v="150", "Not?A_Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}

class LoginError(Exception):
    pass

class TwoFactorRequired(Exception):
    pass

class HttpLoginEngine:
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update(HEADERS)
        self.session.max_redirects = 10

    def _get_login_page(self) -> str:
        """WING → Keycloak 로그인 페이지 URL 획득."""
        resp = self.session.get("https://wing.coupang.com/", allow_redirects=False)
        if resp.status_code in (301, 302):
            loc = resp.headers.get("Location")
            if loc:
                return self._follow_redirects(urljoin(resp.url, loc))
        if "wing.coupang.com" in resp.url and "xauth" not in resp.url:
            return resp.url   # 이미 로그인됨
        raise LoginError("로그인 페이지 획득 실패")

    def _follow_redirects(self, url: str) -> str:
        resp = self.session.get(url, allow_redirects=False)
        while resp.status_code in (301, 302):
            loc = urljoin(resp.url, resp.headers.get("Location", ""))
            resp = self.session.get(loc, allow_redirects=False)
        return resp.url

    def _extract_form_data(self, html: str) -> dict:
        """kc-form-login에서 action, input 필드 추출."""
        action = re.search(r'<form[^>]*action="([^"]+)"', html)
        inputs = {}
        for name, value in re.findall(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"', html):
            inputs[name] = value
        return {"action": action.group(1) if action else None, "inputs": inputs}

    def _extract_vendor_id(self) -> Optional[str]:
        resp = self.session.get("https://wing.coupang.com/tenants/sfl-portal/delivery/management")
        m = re.search(r"vendorId:\s*'([^']*)'", resp.text)
        return m.group(1) if m else None

    def _capture_session(self) -> dict:
        cookies = self.session.cookies.get_dict()
        tokens = {k: cookies[k] for k in ("PCID", "WebSessionId", "OAuthTokenRequestState") if k in cookies}
        cookie_list = [{"name": k, "value": v} for k, v in cookies.items()]
        return {"vendor_id": self._extract_vendor_id(), "tokens": tokens, "cookies": cookie_list}

    def is_alive(self) -> bool:
        t = int(time.time() * 1000)
        resp = self.session.get(f"https://wing.coupang.com/winglayout/bell/notification/find?_={t}")
        return resp.status_code == 200 and "OK" in resp.text

    def login(self, account_id: str, password: str,
              on_2fa: Optional[Callable[[str, str], str]] = None) -> dict:
        """전체 로그인 실행. on_2fa는 (account_id, prompt) -> code 반환."""
        # 1. 로그인 페이지로 이동
        login_page = self._get_login_page()
        if "wing.coupang.com" in login_page and "xauth" not in login_page:
            return self._capture_session()   # 이미 로그인됨

        resp = self.session.get(login_page)
        if resp.status_code != 200:
            raise LoginError(f"Keycloak 폼 로드 실패: {resp.status_code}")
        form = self._extract_form_data(resp.text)
        if not form["action"]:
            raise LoginError("로그인 폼 action 없음")

        # 2. ID/PW 제출
        data = form["inputs"].copy()
        data.update({"username": account_id, "password": password})
        submit_url = urljoin(login_page, form["action"])
        resp = self.session.post(submit_url, data=data, allow_redirects=False)

        # 3. 리디렉션 처리
        if resp.status_code not in (301, 302):
            raise LoginError("로그인 제출 실패 (리디렉션 없음)")

        location = urljoin(submit_url, resp.headers.get("Location", ""))
        # 2FA 감지 (mfa/otp 키워드 또는 응답 본문에 otp 입력 필드)
        if "mfa" in location or "otp" in location:
            if on_2fa is None:
                raise TwoFactorRequired("2차 인증 필요")
            mfa_resp = self.session.get(location)
            # OTP 입력 폼 action 추출
            otp_action = re.search(r'<form[^>]*action="([^"]+)"', mfa_resp.text)
            if not otp_action:
                raise LoginError("2FA 폼 action 없음")
            code = on_2fa(account_id, "2차 인증번호를 입력하세요")
            otp_url = urljoin(location, otp_action.group(1))
            # OTP 제출 (추가 필드는 필요시 파싱)
            otp_data = {"otp": code, "rememberMe": "on"}
            resp = self.session.post(otp_url, data=otp_data, allow_redirects=False)
            if resp.status_code in (301, 302):
                location = urljoin(otp_url, resp.headers.get("Location", ""))
                resp = self.session.get(location, allow_redirects=False)
            else:
                raise LoginError("2FA 제출 실패")

        # 4. 최종 대시보드 도달
        while resp.status_code in (301, 302):
            loc = urljoin(resp.url, resp.headers.get("Location", ""))
            resp = self.session.get(loc, allow_redirects=False)

        if "wing.coupang.com" in resp.url and "xauth" not in resp.url:
            return self._capture_session()
        raise LoginError("로그인 실패: 최종 리디렉션 실패")