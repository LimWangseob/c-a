"""실제 Chrome + CDP 제어 (쿠팡 Akamai 봇탐지 통과용).

Playwright 가 브라우저를 '띄우면' webdriver 흔적으로 로그인이 막힌다. 그래서 실제 Chrome 을
`--remote-debugging-port` 로 구동(자동화·위장 플래그 없음)하고 CDP 로 연결한다.
- 최초 로그인: 창을 보이게 띄우고 사람이 직접(또는 자동입력) 로그인한다.
- 이후 재사용: 같은 프로필 폴더(`--user-data-dir`)로 다시 열어 로그인 세션을 그대로 잇는다.
  (쿠키만 주입한 새 브라우저는 데이터 API 가 403 이라 불가 → 반드시 사람이 로그인한 프로필 재사용)
"""
from __future__ import annotations

import ctypes
import os
import socket
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from . import config
from .proxy_manager import ProxyConfigurationError, ProxyNode

# 콘솔 없는 실행(작업 스케줄러의 무인 --auto = pythonw)에서 보조 명령(파워셸·taskkill·크롬 실행)이
# 검은 콘솔창을 잠깐 띄웠다 닫는 것을 막는 플래그. 앱을 터미널에서 직접 켜면 이미 창이 있어 원래 안 뜨지만,
# 무인 실행 땐 이게 없으면 명령마다 창이 깜빡인다. Windows 전용(다른 OS에선 0 = 효과 없음, GUI 창은 그대로 뜸).
_NO_CONSOLE = getattr(subprocess, "CREATE_NO_WINDOW", 0)

WING_URL = "https://wing.coupang.com/"
# Keycloak SSO 인증 성공 후에만 설정되는 쿠키. (seller-uid 는 로그인 폼 단계에도 있어 오판 유발 → 제외)
_AUTH_COOKIES = ("KEYCLOAK_IDENTITY",)
# 실제 2차 인증(인증번호 입력)일 때만 나타나는 입력칸. (참고: 로그인 폼 JS 의 "인증번호를 5번…"
# 문자열은 입력칸이 아니라 #input-error 로 뜨는 '잠금' 오류 메시지 → OTP 단계와 구분해야 함)
_OTP_SELECTORS = ("input[name='otp']", "#otp", "input[autocomplete='one-time-code']")
# 로그인 폼에 깔린 Akamai 봇 챌린지 오버레이(평소 display:none, 챌린지 시 노출).
_AKAMAI_OVERLAY = "#sec-overlay"
# Akamai 전면 차단 페이지 마커(자동입력·자동제출이 봇으로 탐지돼 authenticate 요청이 거부될 때).
_BLOCK_MARKERS = ("Access Denied", "errors.edgesuite.net", "You don't have permission", "Reference #")
_CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    str(Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe"),
]


def find_chrome() -> str:
    for p in _CHROME_CANDIDATES:
        if Path(p).exists():
            return p
    raise FileNotFoundError("설치된 Google Chrome 을 찾지 못했습니다.")


def _free_port() -> int:
    """빈 TCP 포트 할당(로그인마다 포트 충돌 방지)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _kill_profile_chrome(profile_dir: str) -> int:
    """이 user-data-dir 를 쓰는 잔여 Chrome 만 종료(이전 실행에서 안 닫힌 것). 종료 수 반환.

    같은 프로필로 Chrome 이 이미 떠 있으면 새 실행이 기존 인스턴스로 넘어가 **디버깅 포트가 안 열려**
    실패한다(그 계정 창이 좀비로 남으면 다음 실행이 막힘). 사용자의 일반 브라우징(다른 프로필)은 안 건드린다.
    """
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
          "Where-Object { $_.CommandLine -and "
          "$_.CommandLine.ToLower().Contains($env:SM_PROFILE.ToLower()) } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; 'K' }")
    env = dict(os.environ)
    env["SM_PROFILE"] = profile_dir
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=15, env=env,
                           creationflags=_NO_CONSOLE)
    except Exception as exc:   # 정리 실패는 치명적 아님 — 사유만 남기고 진행(무음 아님)
        print(config.format_log(f"[browser] 잔여 Chrome 정리 건너뜀({exc.__class__.__name__})"))
        return 0
    return r.stdout.count("K")


def reap_orphan_chrome(data_dir: str = "data") -> int:
    """우리 자동화가 띄운 **잔여(좀비) Chrome 을 전부** 종료. 종료 수 반환. 앱 시작 시 1회 호출.

    `__exit__`의 `_kill_tree`는 정상 종료 때만 돈다. 앱이 taskkill/F·크래시로 죽으면 그 순간 열려 있던
    Chrome 이 좀비로 남는다(과거 246개 누적). 이걸 다음 앱 시작 때 싹 정리해 **누적을 원천 차단**한다.
    우리 프로필 루트(`data\\profiles`·`data\\chrome-pipeline` 등 이 설치의 data 폴더) 경로를 `--user-data-dir`
    로 쓰고 `--remote-debugging-port` 로 뜬 Chrome 만 종료 → 사용자의 일반 브라우징(기본 프로필)은 안 건드린다.
    """
    base = str(Path(data_dir).resolve()).lower()
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
          "Where-Object { $_.CommandLine -and "
          "$_.CommandLine.ToLower().Contains($env:SM_DATA) -and "
          "$_.CommandLine.Contains('--remote-debugging-port') } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; 'K' }")
    env = dict(os.environ)
    env["SM_DATA"] = base
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=15, env=env,
                           creationflags=_NO_CONSOLE)
    except Exception as exc:   # 정리 실패는 치명적 아님 — 사유만 남기고 진행(무음 아님)
        print(config.format_log(f"[browser] 좀비 Chrome 정리 건너뜀({exc.__class__.__name__})"))
        return 0
    return r.stdout.count("K")


def _wait_port(port: int, timeout: float = 20.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.3)
    raise TimeoutError(f"Chrome 디버깅 포트({port})가 열리지 않았습니다.")


def _center_pos(w: int, h: int) -> tuple[int, int]:
    """화면 정중앙 좌상단 좌표(Windows). 로그인 창이 화면 밖으로 숨지 않도록."""
    u = ctypes.windll.user32
    u.SetProcessDPIAware()
    sw, sh = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    return max(0, (sw - w) // 2), max(0, (sh - h) // 2)


def is_logged_in(url: str) -> bool:
    """윙 대시보드 도달 = 로그인. xauth(로그인)·sso(전환 리다이렉트) 는 아직 미완."""
    return ("wing.coupang.com" in url) and ("xauth" not in url) and ("/sso/" not in url)


class _LoginWait:
    """wait_for_login 폴링 루프가 반복 사이에 유지하는 상태(행동 불변 분해용)."""
    __slots__ = ("err_streak", "guided", "form_since", "blocked_since")

    def __init__(self) -> None:
        self.err_streak = 0
        self.guided: set[str] = set()
        self.form_since: float | None = None
        self.blocked_since: float | None = None


class WingBrowser:
    """실제 Chrome 세션 하나를 감싸는 컨텍스트 매니저."""

    def __init__(self, profile_dir: str | Path, port: int | None = None, offscreen: bool = True,
                 proxy: str | None = None, block_images: bool = False):
        self.profile_dir = str(Path(profile_dir).resolve())
        self._block_images = block_images   # True=이미지 로드 안 함(노출순위 트래픽 절감 실험·기본 False)
        self.port = port                 # None 이면 빈 포트 자동 할당
        self.offscreen = offscreen
        self._proc: subprocess.Popen | None = None
        self._pw = None
        self._browser = None
        self.context = None
        self.page = None
        # 계정별 고정 프록시(a-모델). proxy=정규화된 URL 문자열 or None(무프록시).
        # 서버(scheme://host:port)만 --proxy-server 로 쓰고, 자격증명은 CDP 인증에 쓴다.
        self._proxy_server: str | None = None
        self._proxy_user: str | None = None
        self._proxy_pass: str | None = None
        self._proxy_protocol: str | None = None
        self._proxy_cdp = None
        if proxy:
            try:
                node = ProxyNode(raw_url=proxy)
            except (ProxyConfigurationError, TypeError) as exc:
                raise ProxyConfigurationError(f"WingBrowser proxy 설정이 유효하지 않습니다: {exc}") from exc

            self._proxy_protocol = node.protocol
            # Chromium은 socks5h 스킴을 별도로 쓰지 않는다. SOCKS5 자체가 프록시 측
            # name resolution을 사용하므로 Chrome 인수에는 socks5:// 로 통일한다.
            if node.protocol in {"socks5", "socks5h"}:
                if node.username is not None:
                    raise ProxyConfigurationError(
                        "WingBrowser/Chrome의 SOCKS5 프록시는 user:password 인증을 지원하지 않습니다. "
                        "인증 없는 SOCKS5(IP 허용 방식) 또는 HTTP(S) 인증 프록시를 사용하세요."
                    )
                host = f"[{node.host}]" if ":" in node.host and not node.host.startswith("[") else node.host
                self._proxy_server = f"socks5://{host}:{node.port}"
            elif node.protocol in {"http", "https"}:
                self._proxy_server = node.endpoint
            else:
                raise ProxyConfigurationError(
                    f"WingBrowser에서 지원하지 않는 프록시 스킴입니다: {node.protocol}"
                )

            self._proxy_user = node.username
            self._proxy_pass = node.password
            if self._proxy_user is not None and not getattr(config, "PROXY_ALLOW_AUTH", False):
                raise ProxyConfigurationError(
                    "자격증명 프록시가 설정되었지만 PROXY_ALLOW_AUTH=False 입니다. "
                    "HTTP(S) 인증 프록시를 사용하려면 PROXY_ALLOW_AUTH=True로 설정하거나, "
                    "자격증명이 필요 없는 프록시를 사용하세요."
                )

    def __enter__(self) -> "WingBrowser":
        Path(self.profile_dir).mkdir(parents=True, exist_ok=True)
        killed = _kill_profile_chrome(self.profile_dir)   # 이 프로필의 잔여 Chrome 정리(포트 미개방 방지)
        if killed:
            print(config.format_log(f"[browser] 이 프로필의 잔여 Chrome {killed}개 정리(프로필 잠금 해제)"))
            time.sleep(1.0)
        self.port = self.port or _free_port()   # 빈 포트 자동 할당(충돌 방지)
        args = [
            find_chrome(),
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.profile_dir}",
            "--no-first-run", "--no-default-browser-check",
            "--disable-session-crashed-bubble", "--hide-crash-restore-bubble",  # '복원' 창 억제
            "--disable-features=InfiniteSessionRestore",
        ]
        if self._proxy_server:                       # 계정별 고정 프록시(a-모델) — IP 고정
            args.append(f"--proxy-server={self._proxy_server}")
            print(config.format_log(f"[browser] 프록시 경유: {self._redacted_proxy()}"))
        if self._block_images:                       # 이미지 로드 안 함(노출순위 트래픽 절감 실험·기본 OFF)
            args.append("--blink-settings=imagesEnabled=false")
        if self.offscreen:
            args += ["--window-position=-2400,-2400", "--window-size=1280,900"]
        else:
            cx, cy = _center_pos(1200, 900)   # 로그인 창은 화면 정중앙
            args += [f"--window-position={cx},{cy}", "--window-size=1200,900"]
        args.append("about:blank")
        self._proc = subprocess.Popen(args, creationflags=_NO_CONSOLE)
        # ⚠ 24/365 상시가동 안정성: __enter__ 도중 예외가 나면 파이썬은 __exit__ 를 부르지 않는다 →
        # 이미 띄운 Chrome(_proc)·playwright 가 좀비로 남아 상시가동 중 로그인 실패·포트경쟁이 반복되면
        # 계속 누적된다(reap_orphan_chrome 은 앱 시작 때만 돎). 그래서 실패 시 여기서 직접 정리 후 재전파.
        try:
            try:
                _wait_port(self.port)
            except TimeoutError:
                if self._proc.poll() is not None:   # Chrome 이 즉시 종료 = 기존 인스턴스로 넘어감(프로필 잠금)
                    raise RuntimeError(
                        "Chrome 디버깅 포트가 안 열립니다 — 같은 프로필로 Chrome 이 이미 실행 중일 수 "
                        f"있습니다. 모든 Chrome 창을 닫고 다시 실행하세요. (프로필: {self.profile_dir})") from None
                raise
            self._pw = sync_playwright().start()
            self._browser = self._connect_cdp()     # ECONNRESET 등 재시도
            self.context = self._browser.contexts[0]
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            self._maybe_setup_proxy_auth()
            return self
        except BaseException:
            self.__exit__(None, None, None)          # _pw.stop() + _kill_tree() → 좀비 누수 차단
            raise

    def __exit__(self, *exc) -> None:
        if self._proxy_cdp is not None:
            try:
                self._proxy_cdp.detach()
            except Exception:
                pass
            self._proxy_cdp = None
        try:
            if self._pw:
                self._pw.stop()
        except Exception as e:  # CDP 연결 해제 실패는 사유만 남기고 계속
            print(config.format_log(f"[browser 정리] pw {e.__class__.__name__}"))
        self._kill_tree()

    # ── 계정별 고정 프록시(a-모델) ──────────────────────────────────
    def _redacted_proxy(self) -> str:
        """로그용 자격증명 가린 프록시 표기(평문 금지)."""
        if not self._proxy_server:
            return "직접연결"
        if self._proxy_user:
            # scheme://host:port → scheme://***:***@host:port
            scheme, rest = self._proxy_server.split("://", 1)
            return f"{scheme}://***:***@{rest}"
        return self._proxy_server

    def _maybe_setup_proxy_auth(self) -> None:
        """HTTP(S) user:pass 프록시 인증에만 응답한다.

        CDP ``Fetch.authRequired`` 는 프록시 인증과 원격 서버의 HTTP 인증을 모두
        전달할 수 있으므로 ``authChallenge.source == "Proxy"`` 인 경우에만 프록시
        자격증명을 제공한다. 웹사이트 자체 인증 challenge에는 자격증명을 보내지 않는다.
        """
        if self._proxy_user is None:
            return
        if self._proxy_protocol not in {"http", "https"}:
            raise ProxyConfigurationError(
                "자격증명 기반 프록시 인증은 WingBrowser에서 HTTP(S) 프록시에만 지원됩니다."
            )
        if not getattr(config, "PROXY_ALLOW_AUTH", False):
            # __init__ 에서 이미 차단하지만, 런타임 설정 변경에도 fail-closed 보장.
            raise ProxyConfigurationError(
                "자격증명 프록시 사용 중 PROXY_ALLOW_AUTH=False 입니다."
            )

        user, pw = self._proxy_user, self._proxy_pass or ""
        cdp = self.context.new_cdp_session(self.page)
        cdp.send("Fetch.enable", {"handleAuthRequests": True, "patterns": [{"urlPattern": "*"}]})

        def _on_auth(params):
            request_id = params.get("requestId")
            if not request_id:
                return
            challenge = params.get("authChallenge") or {}
            source = challenge.get("source")
            try:
                if source == "Proxy":
                    response = {
                        "response": "ProvideCredentials",
                        "username": user,
                        "password": pw,
                    }
                else:
                    # 웹사이트(Server) 인증 challenge에는 프록시 자격증명을 절대 전송하지 않는다.
                    response = {"response": "Default"}
                cdp.send("Fetch.continueWithAuth", {
                    "requestId": request_id,
                    "authChallengeResponse": response,
                })
            except Exception as exc:
                print(config.format_log(
                    f"[browser] 프록시 인증 처리 실패({exc.__class__.__name__})"
                ))

        def _on_paused(params):   # 인증 외 요청은 내용 변경 없이 그대로 통과
            request_id = params.get("requestId")
            if not request_id:
                return
            try:
                cdp.send("Fetch.continueRequest", {"requestId": request_id})
            except Exception as exc:
                print(config.format_log(
                    f"[browser] Fetch 요청 재개 실패({exc.__class__.__name__})"
                ))

        cdp.on("Fetch.authRequired", _on_auth)
        cdp.on("Fetch.requestPaused", _on_paused)
        self._proxy_cdp = cdp

    # ── 창 숨김/표시 (실행 중 위치 이동 — headless 아님, Akamai 통과 유지) ──
    def _set_bounds(self, bounds: dict) -> None:
        cdp = self.context.new_cdp_session(self.page)
        try:
            win = cdp.send("Browser.getWindowForTarget")
            cdp.send("Browser.setWindowBounds", {"windowId": win["windowId"], "bounds": bounds})
        finally:
            cdp.detach()

    def show(self) -> None:
        """숨긴 창을 화면 정중앙으로 이동·표시하고 **맨 앞으로** 가져온다(로그인/2차인증/반자동 등 사람 조작용)."""
        cx, cy = _center_pos(1200, 900)
        self._set_bounds({"left": cx, "top": cy, "width": 1200, "height": 900, "windowState": "normal"})
        self.to_front()

    def to_front(self) -> None:
        """창을 최소화 해제 + 맨 앞으로(포커스). 다른 창에 가려 못 찾는 것 방지. 실패해도 무해."""
        try:
            self.page.bring_to_front()   # CDP Target 활성화 → 창이 앞으로
        except Exception as exc:
            print(config.format_log(f"[browser] to_front 스킵({exc.__class__.__name__})"))

    def hide(self) -> None:
        """창을 화면 밖으로 이동(숨김). 실제 Chrome 은 살아있어 세션·Akamai 통과 유지."""
        self._set_bounds({"left": -2400, "top": -2400, "width": 1280, "height": 900, "windowState": "normal"})

    def _connect_cdp(self, tries: int = 6, delay: float = 1.0):
        """CDP 연결 재시도 — Chrome 디버그 서버 준비 전/포트 전환 시 ECONNRESET 대응."""
        last = None
        for _ in range(tries):
            try:
                return self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}")
            except Exception as exc:
                last = exc
                time.sleep(delay)
        raise last

    def _kill_tree(self) -> None:
        """Chrome 프로세스 트리 전체 종료(자식 렌더러까지). 안 그러면 Chrome 이 쌓여 메모리 먹통."""
        if not self._proc:
            return
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(self._proc.pid)],
                           capture_output=True, timeout=15, creationflags=_NO_CONSOLE)
        except Exception:
            try:
                self._proc.kill()
            except Exception as e:
                print(config.format_log(f"[browser 정리] kill {e.__class__.__name__}"))

    # ── 동작 ────────────────────────────────────────────────
    def goto(self, url: str, timeout: float = 30000) -> str:
        self.page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        return self.page.url

    def _open_urls(self) -> list[str]:
        urls = []
        for pg in self.context.pages:
            if not pg.is_closed():
                try:
                    urls.append(pg.url)
                except Exception:
                    continue
        return urls

    def authenticated(self) -> bool:
        """로그인 완료 판정(견고): 윙 대시보드 도달(xauth/sso 아님) AND KEYCLOAK_IDENTITY 쿠키.

        폼 단계(xauth)에서는 URL 조건이 False → 쿠키가 새어도 오판 안 함. 세션 재사용 시엔 즉시 True.
        """
        if not any(is_logged_in(u) for u in self._open_urls()):
            return False
        try:
            names = {c["name"] for c in self.context.cookies()}
        except Exception:
            return False
        return any(n in names for n in _AUTH_COOKIES)

    def _overlay_visible(self, selector: str) -> bool:
        """오버레이 요소가 실제로 노출(display:none 아님)인지."""
        try:
            el = self.page.query_selector(selector)
            return bool(el and el.is_visible())
        except Exception:
            return False

    def _page_blocked(self) -> bool:
        """현재 페이지가 Akamai 전면 차단(Access Denied) 페이지인지."""
        try:
            blob = (self.page.title() or "") + " " + (self.page.inner_text("body")[:400] or "")
        except Exception:
            return False
        return any(m in blob for m in _BLOCK_MARKERS)

    def classify_login(self) -> tuple[str, str]:
        """현재 화면을 원인코드로 분류. (code, 사람용 상세) 반환.

        code: success | error | blocked | akamai | otp | form | transition | unknown
        - error   : #input-error 에 메시지 표시(비번오류·계정잠금·90일휴면·OTP5회잠금) = 확정 실패
        - blocked : Akamai 전면 차단(Access Denied) = 자동입력/자동제출이 봇으로 탐지됨 → 수동 로그인 필요
        - akamai  : Akamai 봇 챌린지 오버레이 노출 = 사람이 창에서 통과 필요
        - otp     : 실제 인증번호 입력칸 존재 = 사람이 휴대폰 인증번호 입력
        - form    : ID/비번 폼(#username)만 존재 = 자동입력 대기 또는 제출 거부로 재렌더
        """
        try:
            if self.authenticated():
                return "success", "로그인 완료(윙 대시보드 + 인증쿠키)"
        except Exception:
            pass
        try:
            url = self.page.url
        except Exception:
            return "unknown", "화면 확인 불가"
        try:
            if self._page_blocked():
                return ("blocked", "Akamai 접근 차단(Access Denied) — 자동입력·자동제출이 봇으로 "
                        "탐지됨. 열린 창에서 wing.coupang.com 재접속 후 사람이 직접 로그인하세요")
            err = self.page.query_selector("#input-error")
            msg = err.inner_text().strip() if err else ""
            if msg:
                return "error", msg[:120]
            if self._overlay_visible(_AKAMAI_OVERLAY):
                return "akamai", "Akamai 봇 챌린지 표시됨 — 열린 창에서 사람이 통과해야 함"
            if any(self.page.query_selector(s) for s in _OTP_SELECTORS):
                return "otp", "2차 인증(인증번호) 입력칸 — 열린 창에 휴대폰 인증번호를 직접 입력하세요"
            if self.page.query_selector("#username"):
                return "form", "ID/비번 폼(#username) — 자동입력 대기 또는 제출 거부로 폼 재렌더"
            if "xauth" in url or "/sso/" in url:
                return "transition", f"인증 전환 중: {url[:60]}"
            return "unknown", f"현재: {url[:60]}"
        except Exception:
            return "unknown", f"현재: {url[:60]}"

    def login_state(self) -> str:
        """대기 중 화면 상태 진단(사람 안내용 한 줄)."""
        code, detail = self.classify_login()
        prefix = {"error": "⚠ 오류", "blocked": "⛔ 접근차단", "akamai": "⛔ 봇 챌린지",
                  "otp": "🔑 2차 인증", "form": "📝 폼", "transition": "…전환", "success": "✅"}.get(code, "…")
        return f"{prefix}: {detail}"

    def snapshot_login(self, tag: str, out_dir: str | Path = "capture") -> Path | None:
        """현재 로그인 화면을 HTML+스크린샷+URL 로 저장(원인 확정 증거). 실패해도 진단은 계속."""
        try:
            d = Path(out_dir); d.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%y%m%d_%H%M%S")
            base = d / f"login_{tag}_{ts}"
            base.with_suffix(".url.txt").write_text(self.page.url, encoding="utf-8")
            base.with_suffix(".html").write_text(self.page.content(), encoding="utf-8")
            try:
                self.page.screenshot(path=str(base.with_suffix(".png")))
            except Exception:
                pass
            return base
        except Exception as exc:
            print(config.format_log(f"[snapshot_login] 실패({exc.__class__.__name__})"))
            return None

    def _login_frame(self, timeout_ms: int = 20000):
        """로그인 폼(#username)이 있는 프레임을 나타날 때까지 대기(리다이렉트 감안). 없으면 None."""
        end = time.time() + timeout_ms / 1000
        while time.time() < end:
            for fr in self.page.frames:
                try:
                    if fr.query_selector("#username"):
                        return fr
                except Exception:
                    continue
            try:
                self.page.wait_for_timeout(400)
            except Exception:
                time.sleep(0.4)
        return None

    def _check_remember_me(self, fr, log) -> None:
        """로그인 폼에 '로그인 상태 유지'(Keycloak rememberMe) 체크박스가 있으면 체크.

        켜지면 Keycloak 이 KEYCLOAK_IDENTITY 를 **지속쿠키**로 발급 → 브라우저 종료·전원 off 후에도
        재로그인 없이 세션 복원 가능(현재는 세션쿠키라 종료 시 소멸 = 매번 재로그인→차단 유발).
        폼에 없으면(realm 미지원) 사유만 로그(무음 아님). 제어흐름은 바꾸지 않는다.
        """
        cb = fr.query_selector("#rememberMe") or fr.query_selector("input[name='rememberMe']")
        if cb is None:
            log("  [자동입력] '로그인 상태 유지' 체크박스 없음(이 폼 미지원) — 지속쿠키화 불가")
            return
        try:
            if not cb.is_checked():
                cb.check()
            log("  [자동입력] '로그인 상태 유지' 체크(세션 지속쿠키화 시도 — 전원off 후 복원 목적)")
        except Exception as exc:
            log(f"  [자동입력] 로그인 상태 유지 체크 실패({exc.__class__.__name__}) — 계속 진행")

    def _type_field(self, el, value: str) -> None:
        """로그인 입력칸에 value 를 **사람처럼 한 글자씩 실제 키보드로** 친다(붙여넣기/fill 아님).

        쿠팡은 붙여넣기(비신뢰 input)를 감지하므로 신뢰 키입력으로. 실패/불일치면 fill 로 폴백(로그인은 반드시 채워야 함).
        ID/비번은 ASCII 라 IME 조합 불필요(jamo=False)."""
        from . import human_typing
        try:
            el.click()
            self.page.keyboard.press("Control+a")
            self.page.keyboard.press("Delete")
            human_typing.type_focused(self.page, value, jamo=False)
            if el.input_value() == value:
                return
        except Exception:
            pass
        try:
            el.fill(value)                     # 타이핑 실패/불일치 → 폴백(로그인 필수 입력)
        except Exception:
            pass

    def autofill_login(self, account_id: str, password: str, on_log=None) -> bool:
        """로그인 폼에 ID/비번 자동입력 후 제출. 폼(#username) 못 찾으면 False(수동 폴백)."""
        log = on_log or (lambda m: None)
        fr = self._login_frame()
        if fr is None:
            log("  [자동입력] 로그인 폼(#username)을 못 찾음 — 창에서 직접 입력하세요")
            return False
        try:
            u = fr.query_selector("#username")
            p = fr.query_selector("#password")
            if not (u and p):
                return False
            self._type_field(u, account_id)   # 붙여넣기(fill) 아닌 **실제 키보드 타이핑**(쿠팡 키입력 체크 통과)
            self._type_field(p, password)
            self._check_remember_me(fr, log)   # 로그인 상태 유지 → 인증쿠키 지속쿠키화(전원off 복원)
            btn = fr.query_selector("#kc-login")
            if btn:
                btn.click()          # 전송 버튼 클릭 = 폼 제출
            else:
                p.press("Enter")     # 버튼 못 찾으면 Enter 키로 폼 제출
            return True
        except Exception as exc:
            log(f"  [자동입력] 실패({exc.__class__.__name__}) — 창에서 직접 입력하세요")
            return False

    def wait_for_login(self, timeout: float = 300.0, poll: float = 2.0, on_log=None,
                       tag: str = "login", form_warn_after: float = 25.0, on_need_user=None,
                       blocked_grace: float = 60.0, skip_on_otp: bool = False) -> bool:
        """사람이 로그인할 때까지 대기. 완료 시 True.

        원인을 즉시 확정하도록 화면을 분류(classify_login)해서:
        - error(비번오류·계정잠금 등): 확정 실패 → 5분 안 기다리고 즉시 중단 + 증거 스냅샷.
        - akamai/otp: 사람이 창에서 처리해야 함 → 안내 1회 + 계속 대기.
        - form 이 form_warn_after 초 이상 지속: 제출 거부(봇 차단) 의심 → 안내 1회.
        `on_need_user`: 사람 조작이 필요한 상태(2차인증·봇챌린지·차단·폼 지속) 최초 감지 시 1회 호출
        (숨긴 창을 그때만 표시하는 용도). 자동입력만으로 로그인되면 호출되지 않는다.
        """
        log = on_log or (lambda m: None)
        end = time.time() + timeout
        last_log = 0.0
        st = _LoginWait()
        while time.time() < end:
            try:
                if self._browser and not self._browser.is_connected():
                    log("  [로그인감지] 브라우저 창이 닫힘 — 미완료")
                    return False
                verdict = self._react_login(st, tag, form_warn_after, blocked_grace,
                                            skip_on_otp, on_need_user, log)
                if verdict is not None:
                    return verdict
                if time.time() - last_log > 12:
                    log(f"  [로그인감지] 대기 중… {self.login_state()}")
                    last_log = time.time()
            except Exception as exc:  # 전환 중 일시 오류는 무시하고 재시도
                if time.time() - last_log > 12:
                    log(f"  [로그인감지] 대기 중… ({exc.__class__.__name__})")
                    last_log = time.time()
            time.sleep(poll)
        self.snapshot_login(tag)
        log("  [로그인감지] 5분 초과 — 미완료 (증거 스냅샷 저장)")
        return False

    def _react_login(self, st: "_LoginWait", tag, form_warn_after, blocked_grace,
                     skip_on_otp, on_need_user, log):
        """폴링 1회: 화면 분류 후 반응. True=완료·False=중단·None=계속 대기."""
        code, detail = self.classify_login()
        if code == "success":     # 윙 대시보드 도달 + 인증쿠키 = 로그인 완료(견고)
            return True
        if code == "error":       # 확정 실패 — 2회 연속 확인 후 즉시 중단
            st.err_streak += 1
            if st.err_streak == 1:
                log(f"  [로그인감지] ⚠ 로그인 거부: {detail}")
            if st.err_streak >= 2:
                snap = self.snapshot_login(tag)
                where = f" (증거: {snap}.html/.png)" if snap else ""
                log("  [로그인감지] 확정 실패 — 자동 재시도 중단(계정잠금 방지)."
                    f" 원인=위 오류 메시지{where}")
                return False
        else:
            st.err_streak = 0

        if code == "form":
            self._react_form(st, tag, form_warn_after, on_need_user, log)
            return None
        st.form_since = None
        return self._react_blocked_otp(st, code, detail, tag, blocked_grace,
                                       skip_on_otp, on_need_user, log)

    def _react_form(self, st: "_LoginWait", tag, form_warn_after, on_need_user, log):
        """폼이 계속 남아있으면(제출 거부·봇차단 의심) 1회 안내."""
        st.form_since = st.form_since or time.time()
        if (time.time() - st.form_since > form_warn_after) and "form" not in st.guided:
            st.guided.add("form")
            self.snapshot_login(tag)
            if on_need_user:
                on_need_user()
            log("  [로그인감지] 폼이 계속 남아있음 — 제출이 거부돼 폼으로 되돌아왔을 "
                "가능성(오류 메시지 없는 봇 차단 의심). 열린 창에서 직접 로그인해 보세요")

    def _react_blocked_otp(self, st: "_LoginWait", code, detail, tag, blocked_grace,
                           skip_on_otp, on_need_user, log):
        """차단(Akamai)·2차인증 화면 반응. False=중단·None=계속 대기."""
        if code == "blocked":
            # Akamai 접근차단은 IP 플래그라 사람 재로그인도 대부분 못 뚫는다(실측 2026-09-08).
            # 창 1회 표시로 기회를 주되, 300초 무한대기(→사람이 창 수동종료→다음 계정 전환 중
            # Playwright 드라이버 EPIPE 크래시) 대신 grace 후 스스로 건너뛴다.
            if st.blocked_since is None:
                st.blocked_since = time.time()
                self.snapshot_login(tag)
                if on_need_user:
                    on_need_user()
                log(f"  [로그인감지] {detail}")
            elif time.time() - st.blocked_since > blocked_grace:
                log("  [로그인감지] Akamai 접근 차단 지속 — 이 계정 건너뜀"
                    " (무한대기·창 수동종료 방지, 잠시 후/내일 재시도)")
                return False
        elif code == "otp" and skip_on_otp:
            # 2차 인증(인증번호) 화면 = 사람이 휴대폰 번호를 입력해야 함. 배치(전체실행)에서는
            # 대기하지 않고 **즉시 이 계정을 건너뛴다**(다음 계정 진행·이 계정은 미완료로 다음에 재시도).
            self.snapshot_login(tag)
            log("  [로그인감지] 2차 인증(인증번호) 필요 — 대기하지 않고 이 계정 건너뜀"
                " (다음 계정 진행, 이 계정은 나중에 재시도)")
            return False
        elif code in ("akamai", "otp") and code not in st.guided:
            st.guided.add(code)
            self.snapshot_login(tag)
            if on_need_user:
                on_need_user()
            log(f"  [로그인감지] {detail}")
        return None
