"""세션 킵얼라이브 — 로그인된 세션을 주기적으로 살려둔다(재로그인·2차인증·차단 빈도↓).

**로그인이 아니다.** 이미 로그인된 계정 프로필의 **숨긴 실제 Chrome으로 윙 대시보드만 잠깐 방문**해
"아직 사용 중"이라는 정상 신호를 줘서 세션 만료 시계(Idle)를 미룬다(비번·2차인증·창 없음, 지문위조 아님).
만료돼 로그인 폼이 뜨는 계정은 **로그인 시도하지 않고** 그냥 "만료"로 기록하고 지나간다(안전 GET).

두 가지 방식으로 쓴다:
- `KeepAlive` : 앱이 켜져 있는 동안 백그라운드 스레드로(전체 실행 중엔 `pause_check`로 건너뜀).
- `keepwarm_once` : 앱과 무관하게 **1회 패스**(Windows 작업 스케줄러 등에서 `tools/keepwarm.py`로 호출)
  → 앱을 안 열어둬도 세션을 유지해 **재로그인 자체를 줄인다**(차단 근본책의 상시 실행 조각).

`touch_session` 은 프로필 하나를 열어 WING 접속·생존확인·리다이렉트감지까지 한 단위. TTL 측정 도구도 재사용.
"""
from __future__ import annotations

import threading

from . import config
from . import session_state
from .browser import WING_URL, WingBrowser
from .pipeline import account_profile


def touch_session(account_id: str, wait_ms: int = 1200) -> tuple[bool, bool, str]:
    """프로필을 열어 WING 접속 후 (alive, redirected, final_url) 반환. 로그인 시도 없음(안전 GET).

    alive      : 윙 대시보드 도달 + 인증쿠키(세션 살아있음). 방문 자체가 만료 시계를 미룬다.
    redirected : 접속 중 xauth/sso 로 리다이렉트가 있었는지(=WING 접속이 Keycloak 을 쳐 Idle 을
                 갱신할 여지가 있는지 = keep-warm 유효성 힌트).
    """
    seen: list[str] = []
    with WingBrowser(profile_dir=account_profile(account_id), offscreen=True) as b:
        b.page.on("framenavigated",
                  lambda fr: seen.append(fr.url) if fr == b.page.main_frame else None)
        b.goto(WING_URL)
        b.page.wait_for_timeout(wait_ms)
        alive = b.authenticated()
        final = b.page.url
    redirected = any(("xauth" in u or "/sso/" in u) for u in seen)
    return alive, redirected, final


def keepwarm_once(account_ids, on_log=print, exclude=(), stop_check=None) -> tuple[int, int]:
    """계정들 세션을 1회씩 살려둠(관측 이벤트 기록). (살아있음 수, 대상 수) 반환.

    exclude    : 제외할 계정(예: TTL 측정 중인 코호트 — 건드리면 측정 오염).
    stop_check : () -> bool, True 면 중단(스레드 종료 신호).
    """
    ids = [a for a in account_ids if a not in set(exclude)]
    alive = 0
    for aid in ids:
        if stop_check and stop_check():
            break
        try:
            ok, redirected, final = touch_session(aid)
            session_state.record_event(   # 관측만(백그라운드 프로브 — 파이프라인 상태를 덮지 않음)
                aid, "keepalive_alive" if ok else "keepalive_expired",
                final_url=final, auth_redirect=redirected)
            if ok:
                alive += 1
        except Exception as exc:          # best-effort — 사유만 남기고 다음 계정
            on_log(f"[세션유지] {aid} 확인 실패: {exc.__class__.__name__}")
    return alive, len(ids)


class KeepAlive:
    """백그라운드 스레드로 주기적으로 세션을 살려둔다(앱이 켜져 있는 동안). start()/stop()."""

    def __init__(self, account_ids_fn, on_log, pause_check=None, interval_sec: int | None = None,
                 exclude_fn=None):
        self._ids_fn = account_ids_fn                 # () -> list[str]
        self._log = on_log or (lambda m: None)
        self._pause_check = pause_check or (lambda: False)
        self._exclude_fn = exclude_fn or (lambda: ())  # () -> iterable[str] (측정 코호트 등 제외)
        self._interval = interval_sec or config.SESSION_KEEPALIVE_MIN * 60
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.is_running():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._log(f"[세션유지] 켜짐 — {self._interval // 60}분마다 세션을 살려둡니다(로그인 아님).")

    def stop(self) -> None:
        self._stop.set()
        self._log("[세션유지] 꺼짐")

    def _run(self) -> None:
        self._tick()                          # 켜자마자 1회
        while not self._stop.wait(self._interval):
            self._tick()

    def _tick(self) -> None:
        if self._pause_check():
            self._log("[세션유지] 전체 실행 중 — 이번 주기는 건너뜀")
            return
        ids = list(self._ids_fn() or [])
        if not ids:
            return
        alive, total = keepwarm_once(ids, on_log=self._log, exclude=self._exclude_fn(),
                                     stop_check=self._stop.is_set)
        self._log(f"[세션유지] {total}계정 중 {alive}개 세션 유지됨 "
                  f"(만료 {total - alive}개는 다음 실행 때 로그인). 다음 확인 {self._interval // 60}분 뒤")
