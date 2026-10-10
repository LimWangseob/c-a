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


def test_apply_proxy_override_default_on() -> None:
    """config.apply_proxy_override: config.json proxy/* 런타임 적용 — 미설정=기본 ON, false=OFF."""
    from coupang_analytics import appconfig
    saved = (config.PROXY_ENABLED, config.PROXY_RANK_URL, config.PROXY_ALLOW_AUTH)
    orig_get = appconfig.get
    try:
        # 미설정(모든 키 빈값) → 기본 ON
        appconfig.get = lambda k, d="": d
        config.apply_proxy_override()
        assert config.PROXY_ENABLED is True, "미설정 기본값이 ON이 아님(2번 정책)"
        assert config.PROXY_RANK_URL == "" and config.PROXY_ALLOW_AUTH is False
        # proxy/enabled=false → OFF, rank_url/allow_auth 반영
        vals = {"proxy/enabled": "false", "proxy/rank_url": "http://1.2.3.4:8080", "proxy/allow_auth": "true"}
        appconfig.get = lambda k, d="": vals.get(k, d)
        config.apply_proxy_override()
        assert config.PROXY_ENABLED is False
        assert config.PROXY_RANK_URL == "http://1.2.3.4:8080"
        assert config.PROXY_ALLOW_AUTH is True
    finally:
        appconfig.get = orig_get
        config.PROXY_ENABLED, config.PROXY_RANK_URL, config.PROXY_ALLOW_AUTH = saved
        proxy_pool.reset_cache()


def test_pick_rank_proxy_rotation() -> None:
    """proxy_pool.pick_rank_proxy: egress 회전 — 안 쓴 노드 반환·전부 tried면 exhausted·OFF=off."""
    saved_en = config.PROXY_ENABLED
    orig_urls = proxy_pool.rank_proxy_pool_urls
    proxy_pool.reset_cache()
    try:
        # OFF = 회전 안 함
        config.PROXY_ENABLED = False
        assert proxy_pool.pick_rank_proxy(set()) == (None, True, "off")
        # ON + 3노드 풀(주입)
        config.PROXY_ENABLED = True
        pool = ["http://a:8080", "http://b:8080", "http://c:8080"]
        proxy_pool.rank_proxy_pool_urls = lambda: list(pool)
        u1, ok1, st1 = proxy_pool.pick_rank_proxy(set())
        assert ok1 and st1 == "ok" and u1 in pool
        # 결정적: 같은 tried면 같은 선택
        assert proxy_pool.pick_rank_proxy(set())[0] == u1, "첫 선택이 결정적이지 않음"
        # u1 제외 → 다른 노드
        u2, ok2, st2 = proxy_pool.pick_rank_proxy({u1})
        assert ok2 and st2 == "ok" and u2 != u1 and u2 in pool
        # 전부 시도 → exhausted(직접연결 안 함)
        assert proxy_pool.pick_rank_proxy(set(pool)) == (None, False, "exhausted")
        # ON인데 풀 비었음 → error(fail-closed)
        proxy_pool.rank_proxy_pool_urls = lambda: []
        assert proxy_pool.pick_rank_proxy(set()) == (None, False, "error")
    finally:
        proxy_pool.rank_proxy_pool_urls = orig_urls
        config.PROXY_ENABLED = saved_en
        proxy_pool.reset_cache()


def test_proxy_blocklist() -> None:
    """proxy_blocklist: egress IP 기록·조회·TTL 만료·IP 파싱."""
    import os
    import tempfile
    import time as _time

    from coupang_analytics import proxy_blocklist as bl

    # IP 파싱(에코 응답)
    assert bl.parse_ip('{"ip":"203.0.113.9"}') == "203.0.113.9"
    assert bl.parse_ip("198.51.100.7\n") == "198.51.100.7"
    assert bl.parse_ip("no ip here") is None

    orig_path = bl._path
    saved_ttl = config.RANK_PROXY_BLOCKLIST_TTL_SEC
    fd, tmp = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.unlink(tmp)   # 아직 없음 상태로 시작
    try:
        bl._path = lambda: tmp
        assert bl.load() == {}, "초기 로드는 빈 목록"
        assert bl.is_blocked("1.2.3.4") is False
        # 기록 → 조회
        bl.record("1.2.3.4", "Akamai Access Denied")
        assert bl.is_blocked("1.2.3.4") is True
        assert bl.is_blocked("9.9.9.9") is False
        assert bl.count() == 1
        # 재기록 → count 증가
        bl.record("1.2.3.4", "재차단")
        assert (bl.entry("1.2.3.4") or {}).get("count") == 2
        # TTL 만료 → 로드 시 제거
        config.RANK_PROXY_BLOCKLIST_TTL_SEC = 1
        data = bl.load()
        data["1.2.3.4"]["last_ts"] = _time.time() - 10   # 10초 전(>1초 TTL)
        bl.save(data)
        assert bl.load() == {}, "TTL 지난 항목이 안 지워짐"
    finally:
        bl._path = orig_path
        config.RANK_PROXY_BLOCKLIST_TTL_SEC = saved_ttl
        if os.path.exists(tmp):
            os.unlink(tmp)


class _FakeCM:
    """drive_rank 가 여는 WingBrowser 대체(실제 Chrome 안 띄움)."""
    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return "BROWSER"

    def __exit__(self, *a):
        return False


def test_drive_rank_rotation() -> None:
    """pipeline_ranks.drive_rank: egress 선제 skip(차단이력) + 차단 시 재회전(상한) + 기록 — 오프라인."""
    from coupang_analytics import pipeline_ranks as PR
    from coupang_analytics import proxy_blocklist as bl

    saved = (config.PROXY_ENABLED, config.RANK_PROXY_ROTATE_ON_BLOCK,
             config.RANK_PROXY_PRECHECK_EGRESS, config.RANK_PROXY_ROTATE_MAX)
    orig = (PR.WingBrowser, proxy_pool.rank_proxy_pool_urls,
            bl.resolve_egress_ip, bl.is_blocked, bl.record, bl.entry)
    proxy_pool.reset_cache()
    try:
        config.PROXY_ENABLED = True
        config.RANK_PROXY_ROTATE_ON_BLOCK = True
        config.RANK_PROXY_PRECHECK_EGRESS = True
        PR.WingBrowser = _FakeCM
        proxy_pool.rank_proxy_pool_urls = lambda: ["http://a:1", "http://b:1", "http://c:1"]
        bl.entry = lambda ip, data=None: {"last": "T", "count": 1}

        # ── 시나리오 1: 첫 egress 가 차단이력 → skip, 다음 깨끗한 IP 로 진행(run_once 1회) ──
        egress_seq = ["1.1.1.1", "2.2.2.2"]
        bl.resolve_egress_ip = lambda browser, log=None: egress_seq.pop(0)
        bl.is_blocked = lambda ip, data=None: ip == "1.1.1.1"
        recorded: list = []
        bl.record = lambda ip, reason="": recorded.append(ip)
        calls: list = []

        def _ok(b, e) -> bool:
            calls.append(e)
            return False

        PR.drive_rank(offscreen=True, run_once=_ok, log=lambda m: None)
        assert calls == ["2.2.2.2"], f"차단이력 IP skip 실패: {calls}"
        assert recorded == [], "선제 skip 인데 차단기록이 생김"

        # ── 시나리오 2: 매 실행 차단(True) → 회전 상한까지 재회전 + egress 기록 ──
        config.RANK_PROXY_ROTATE_MAX = 2
        ips = iter(["10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4"])
        bl.resolve_egress_ip = lambda browser, log=None: next(ips)
        bl.is_blocked = lambda ip, data=None: False
        recorded2: list = []
        bl.record = lambda ip, reason="": recorded2.append(ip)
        runs: list = []

        def _blocked(b, e) -> bool:
            runs.append(e)   # 항상 차단
            return True

        PR.drive_rank(offscreen=False, run_once=_blocked, log=lambda m: None)
        # 첫 실행 + 회전 2회 = run_once 3회, 매번 egress 기록, 그 뒤 회전 소진으로 종료
        assert len(runs) == 3, f"회전 상한 동작 오류(run_once {len(runs)}회)"
        assert recorded2 == runs, f"차단 egress 기록 누락: {recorded2} vs {runs}"
    finally:
        (config.PROXY_ENABLED, config.RANK_PROXY_ROTATE_ON_BLOCK,
         config.RANK_PROXY_PRECHECK_EGRESS, config.RANK_PROXY_ROTATE_MAX) = saved
        (PR.WingBrowser, proxy_pool.rank_proxy_pool_urls,
         bl.resolve_egress_ip, bl.is_blocked, bl.record, bl.entry) = orig
        proxy_pool.reset_cache()


def test_rank_block_images() -> None:
    """WingBrowser(block_images) 저장 + config.apply_rank_images_override(config.json 토글)."""
    from coupang_analytics import appconfig
    # __init__ 가 이미지 플래그만 저장(Chrome 실행은 __enter__ 라 여기선 안 뜸)
    assert WingBrowser("x", block_images=True)._block_images is True
    assert WingBrowser("x")._block_images is False
    saved = config.RANK_BLOCK_IMAGES
    orig_get = appconfig.get
    try:
        appconfig.get = lambda k, d="": ("on" if k == "rank/block_images" else d)
        config.apply_rank_images_override()
        assert config.RANK_BLOCK_IMAGES is True, "rank/block_images=on 인데 적용 안 됨"
        appconfig.get = lambda k, d="": d   # 미설정 → 기본 OFF(이미지 유지)
        config.apply_rank_images_override()
        assert config.RANK_BLOCK_IMAGES is False, "미설정 기본이 OFF가 아님"
    finally:
        appconfig.get = orig_get
        config.RANK_BLOCK_IMAGES = saved


def test_semi_block_rotate_signal() -> None:
    """③ 반자동 _semi_on_miss: 확정 차단 시 회전 가능하면 쿨다운(30분 sleep) 생략·halted 로 drive_rank 에 새 IP 요청,
    회전 불가 + 쿨다운 상한 0 이면 즉시 당일중단(halted)·sleep 안 함. (옛 인라인 _rank_cooldown 핀을 운영 경로로 이전·D-022 B5)"""
    from coupang_analytics import pipeline_ranks as PR
    import coupang_analytics.config as C
    orig_can, orig_sleep = PR.rotation_can_rotate, PR._interruptible_sleep
    saved_max = C.RANK_SEMI_COOLDOWN_MAX
    slept: list = []
    try:
        PR._interruptible_sleep = lambda *a, **k: slept.append(a)
        # 회전 가능 → halted(새 egress 로 재개)·쿨다운 sleep 없음
        PR.rotation_can_rotate = lambda: True
        st = PR._SemiState()
        PR._semi_on_miss(st, "kw", True, lambda: False, lambda m: None)
        assert st.halted is True and st.cooldowns == 0 and not slept, (st, slept)
        # 회전 불가 + 쿨다운 상한 0 → 즉시 당일중단(halted)·sleep 없음
        PR.rotation_can_rotate = lambda: False
        C.RANK_SEMI_COOLDOWN_MAX = 0
        st = PR._SemiState()
        PR._semi_on_miss(st, "kw", True, lambda: False, lambda m: None)
        assert st.halted is True and st.cooldowns == 1 and not slept, (st, slept)
    finally:
        PR.rotation_can_rotate, PR._interruptible_sleep = orig_can, orig_sleep
        C.RANK_SEMI_COOLDOWN_MAX = saved_max


def main() -> None:
    tests = [
        test_fail_closed,
        test_rank_allocation,
        test_socks_rules,
        test_http_auth_and_challenge_source,
        test_rank_proxy_or_skip,
        test_apply_proxy_override_default_on,
        test_pick_rank_proxy_rotation,
        test_proxy_blocklist,
        test_drive_rank_rotation,
        test_rank_block_images,
        test_semi_block_rotate_signal,
    ]
    for test in tests:
        test()
        print(f"[PASS] {test.__name__}")
    print(f"ALL PASS: {len(tests)}")


if __name__ == "__main__":
    main()
