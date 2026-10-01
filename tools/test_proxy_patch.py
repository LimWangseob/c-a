"""프록시 통합 수정본의 오프라인 스모크 테스트.

실제 네트워크/Chrome을 사용하지 않는다.
실행: `PYTHONPATH=src python tools/test_proxy_patch.py` 또는 `pytest`(test_* 함수 자동 수집).
"""
from __future__ import annotations

import sys
from pathlib import Path

# pytest 로 수집될 때 PYTHONPATH 가 없어도 import 되도록 src 를 경로에 추가(verify_offline 과 동일 패턴).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from coupang_analytics import config, proxy_pool
from coupang_analytics.browser import WingBrowser
from coupang_analytics.proxy_manager import ProxyConfigurationError, ProxyManager, ProxyNode


def expect_error(fn, message: str) -> None:
    try:
        fn()
    except ProxyConfigurationError:
        return
    raise AssertionError(message)


def test_fail_closed() -> None:
    old_en = config.PROXY_ENABLED
    old_file = config.PROXY_FILE
    old_map = dict(config.PROXY_ACCOUNT_MAP)
    try:
        config.PROXY_ENABLED = True
        config.PROXY_FILE = "__definitely_missing_proxy_file__.txt"
        config.PROXY_ACCOUNT_MAP = {}
        expect_error(proxy_pool.load_manager, "빈 프록시 설정이 fail-open 됨")
        expect_error(
            lambda: proxy_pool.proxy_for_account(None, "acct"),
            "ON + manager=None이 직접연결로 우회됨",
        )
    finally:
        config.PROXY_ENABLED = old_en
        config.PROXY_FILE = old_file
        config.PROXY_ACCOUNT_MAP = old_map


def test_pool_allocation() -> None:
    old_en = config.PROXY_ENABLED
    old_map = dict(config.PROXY_ACCOUNT_MAP)
    try:
        config.PROXY_ENABLED = True
        config.PROXY_ACCOUNT_MAP = {"fixed": "http://10.0.0.9:8080"}
        mgr = ProxyManager()
        mgr.load_proxies([
            "http://10.0.0.1:8080",
            "http://10.0.0.2:8080",
            "http://10.0.0.9:8080",
        ])

        assert proxy_pool.proxy_for_account(mgr, "fixed") == "http://10.0.0.9:8080"
        normal = proxy_pool.proxy_for_account(mgr, "normal")
        assert normal != "http://10.0.0.9:8080", "전용 프록시가 일반 계정에 배정됨"
        assert normal == proxy_pool.proxy_for_account(mgr, "normal"), "배정이 결정적이지 않음"

        selected = next(n for n in mgr.proxies if n.raw_url == normal)
        selected.is_active = False
        changed = proxy_pool.proxy_for_account(mgr, "normal")
        assert changed != normal, "비활성 프록시가 계속 배정됨"
    finally:
        config.PROXY_ENABLED = old_en
        config.PROXY_ACCOUNT_MAP = old_map


def test_socks_rules() -> None:
    node = ProxyNode("socks5://127.0.0.1")
    assert node.port == 1080, f"SOCKS 기본 포트 오류: {node.port}"

    old_auth = config.PROXY_ALLOW_AUTH
    try:
        config.PROXY_ALLOW_AUTH = False
        wb = WingBrowser(".", proxy="socks5h://127.0.0.1:1080")
        assert wb._proxy_server == "socks5://127.0.0.1:1080"
        expect_error(
            lambda: WingBrowser(".", proxy="socks5://user:secret@127.0.0.1:1080"),
            "SOCKS5 user/pass가 허용됨",
        )
    finally:
        config.PROXY_ALLOW_AUTH = old_auth


def test_http_auth_and_challenge_source() -> None:
    old_auth = config.PROXY_ALLOW_AUTH
    try:
        config.PROXY_ALLOW_AUTH = False
        expect_error(
            lambda: WingBrowser(".", proxy="http://user:secret@127.0.0.1:8080"),
            "PROXY_ALLOW_AUTH=False인데 HTTP 인증 프록시가 허용됨",
        )

        config.PROXY_ALLOW_AUTH = True
        wb = WingBrowser(".", proxy="http://user:secret@127.0.0.1:8080")
        assert "secret" not in wb._redacted_proxy()

        class FakeCDP:
            def __init__(self):
                self.sent = []
                self.handlers = {}

            def send(self, method, payload=None):
                self.sent.append((method, payload or {}))
                return {}

            def on(self, event, handler):
                self.handlers[event] = handler

            def detach(self):
                pass

        class FakeContext:
            def __init__(self, cdp):
                self.cdp = cdp

            def new_cdp_session(self, page):
                return self.cdp

        cdp = FakeCDP()
        wb.context = FakeContext(cdp)
        wb.page = object()
        wb._maybe_setup_proxy_auth()

        # 웹사이트 자체 인증: Default, 프록시 비밀번호 전송 금지
        cdp.handlers["Fetch.authRequired"]({
            "requestId": "server-1",
            "authChallenge": {"source": "Server"},
        })
        method, payload = cdp.sent[-1]
        assert method == "Fetch.continueWithAuth"
        assert payload["authChallengeResponse"] == {"response": "Default"}

        # Proxy 인증에서만 자격증명 제공
        cdp.handlers["Fetch.authRequired"]({
            "requestId": "proxy-1",
            "authChallenge": {"source": "Proxy"},
        })
        method, payload = cdp.sent[-1]
        assert method == "Fetch.continueWithAuth"
        auth = payload["authChallengeResponse"]
        assert auth["response"] == "ProvideCredentials"
        assert auth["username"] == "user" and auth["password"] == "secret"
    finally:
        config.PROXY_ALLOW_AUTH = old_auth


def test_resolve_proxy_skips_per_account() -> None:
    """pipeline_sales._resolve_proxy: 프록시 설정 오류는 전체중단이 아니라 그 계정만 스킵(직접연결 안 함)."""
    from coupang_analytics import pipeline_sales as ps
    saved_en, saved_map = config.PROXY_ENABLED, dict(config.PROXY_ACCOUNT_MAP)
    try:
        logs: list[str] = []
        # OFF = 무프록시 정상(True, None)
        config.PROXY_ENABLED = False
        ps._PROXY_MGR_LOADED = False
        assert ps._resolve_proxy("acct1", logs.append) == (True, None)
        # ON + 빈 설정(유효 프록시 없음) = fail-closed 로 (False, None) 스킵 · 예외 전파 안 함
        config.PROXY_ENABLED = True
        config.PROXY_ACCOUNT_MAP = {}
        ps._PROXY_MGR_LOADED = False
        assert ps._resolve_proxy("acct2", logs.append) == (False, None)
        assert any("프록시" in m for m in logs)
    finally:
        config.PROXY_ENABLED, config.PROXY_ACCOUNT_MAP = saved_en, saved_map
        ps._PROXY_MGR_LOADED = False


def main() -> None:
    tests = [
        test_fail_closed,
        test_pool_allocation,
        test_socks_rules,
        test_http_auth_and_challenge_source,
        test_resolve_proxy_skips_per_account,
    ]
    for test in tests:
        test()
        print(f"[PASS] {test.__name__}")
    print(f"ALL PASS: {len(tests)}")


if __name__ == "__main__":
    main()
