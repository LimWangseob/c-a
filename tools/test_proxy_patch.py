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
    old_en, old_file, old_rank = config.PROXY_ENABLED, config.PROXY_FILE, config.PROXY_RANK_URL
    proxy_pool.reset_cache()
    try:
        config.PROXY_ENABLED = True
        config.PROXY_FILE = "__definitely_missing_proxy_file__.txt"
        config.PROXY_RANK_URL = ""
        expect_error(proxy_pool.load_manager, "빈 프록시 설정이 fail-open 됨")
        expect_error(
            lambda: proxy_pool.rank_proxy(None),
            "ON + manager=None이 직접연결로 우회됨",
        )
    finally:
        config.PROXY_ENABLED, config.PROXY_FILE, config.PROXY_RANK_URL = old_en, old_file, old_rank
        proxy_pool.reset_cache()


def test_rank_allocation() -> None:
    """노출순위 프록시 선택 — PROXY_RANK_URL 명시 우선·없으면 풀 결정적(활성만)."""
    old_en, old_rank = config.PROXY_ENABLED, config.PROXY_RANK_URL
    proxy_pool.reset_cache()
    try:
        config.PROXY_ENABLED = True
        mgr = ProxyManager()
        mgr.load_proxies([
            "http://10.0.0.1:8080",
            "http://10.0.0.2:8080",
            "http://10.0.0.9:8080",
        ])
        # 명시 URL = 그 프록시 고정
        config.PROXY_RANK_URL = "http://10.0.0.9:8080"
        assert proxy_pool.rank_proxy(mgr) == "http://10.0.0.9:8080"
        # 명시 없음 = 풀에서 결정적 선택
        config.PROXY_RANK_URL = ""
        pick = proxy_pool.rank_proxy(mgr)
        assert pick and pick == proxy_pool.rank_proxy(mgr), "rank 배정이 결정적이지 않음"
        # 선택 노드 비활성화 → 다른 활성 노드로
        selected = next(n for n in mgr.proxies if n.raw_url == pick)
        selected.is_active = False
        assert proxy_pool.rank_proxy(mgr) != pick, "비활성 프록시가 계속 배정됨"
    finally:
        config.PROXY_ENABLED, config.PROXY_RANK_URL = old_en, old_rank
        proxy_pool.reset_cache()


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


def test_rank_proxy_or_skip() -> None:
    """proxy_pool.rank_proxy_or_skip: 노출순위 프록시 오류는 전체중단이 아니라 순위 스킵(직접연결 안 함)."""
    saved_en, saved_file, saved_rank = config.PROXY_ENABLED, config.PROXY_FILE, config.PROXY_RANK_URL
    proxy_pool.reset_cache()
    try:
        logs: list[str] = []
        # OFF = 무프록시 정상(None, True)
        config.PROXY_ENABLED = False
        proxy_pool.reset_cache()
        assert proxy_pool.rank_proxy_or_skip(logs.append) == (None, True)
        # ON + 유효 프록시 없음 = fail-closed 로 (None, False) 순위 스킵 · 예외 전파 안 함
        config.PROXY_ENABLED = True
        config.PROXY_FILE = "__definitely_missing_proxy_file__.txt"
        config.PROXY_RANK_URL = ""
        proxy_pool.reset_cache()
        assert proxy_pool.rank_proxy_or_skip(logs.append) == (None, False)
        assert any("프록시" in m for m in logs)
    finally:
        config.PROXY_ENABLED, config.PROXY_FILE, config.PROXY_RANK_URL = saved_en, saved_file, saved_rank
        proxy_pool.reset_cache()


def main() -> None:
    tests = [
        test_fail_closed,
        test_rank_allocation,
        test_socks_rules,
        test_http_auth_and_challenge_source,
        test_rank_proxy_or_skip,
    ]
    for test in tests:
        test()
        print(f"[PASS] {test.__name__}")
    print(f"ALL PASS: {len(tests)}")


if __name__ == "__main__":
    main()
