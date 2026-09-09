"""세션 킵얼라이브 — 앱이 켜져 있는 동안 로그인된 세션을 살려둔다(재로그인·2차인증 빈도↓).

**로그인이 아니다.** 이미 로그인된 계정 프로필의 **숨긴 실제 Chrome으로 윙 대시보드만 잠깐 방문**해
"아직 사용 중"이라는 정상 신호를 줘서 세션 만료 시계를 미룬다(비번·2차인증·창 없음, 지문위조 아님).
만료돼 로그인 폼이 뜨는 계정은 **로그인 시도하지 않고** 그냥 "만료"로 기록하고 지나간다.

주의: 전체 실행 중에는 같은 프로필을 동시에 열면 충돌하므로 `pause_check`로 그때는 건너뛴다.
"""
from __future__ import annotations

import threading

from . import config
from . import session_state
from .browser import WING_URL, WingBrowser
from .pipeline import account_profile


class KeepAlive:
    """백그라운드 스레드로 주기적으로 세션을 살려둔다. start()/stop()."""

    def __init__(self, account_ids_fn, on_log, pause_check=None, interval_sec: int | None = None):
        self._ids_fn = account_ids_fn                 # () -> list[str]
        self._log = on_log or (lambda m: None)
        self._pause_check = pause_check or (lambda: False)
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
        alive = 0
        for aid in ids:
            if self._stop.is_set():
                return
            try:
                with WingBrowser(profile_dir=account_profile(aid), offscreen=True) as b:
                    b.goto(WING_URL)
                    b.page.wait_for_timeout(1200)
                    ok = b.authenticated()    # 대시보드 도달=세션 살아있음(방문 자체가 만료 시계를 미룸)
                    # 관측만(백그라운드 프로브 — 파이프라인이 정한 상태를 덮지 않음). WING 접속이
                    # 실제 재인증 리다이렉트를 거쳤는지(=keep-warm 유효성)도 최종 URL로 힌트 기록.
                    redirected = any(s in (b.page.url or "") for s in ("xauth", "/sso/"))
                    session_state.record_event(
                        aid, "keepalive_alive" if ok else "keepalive_expired",
                        final_url=b.page.url, auth_redirect=redirected)
                    if ok:
                        alive += 1
            except Exception as exc:          # 백그라운드 best-effort — 사유만 남기고 다음 계정
                self._log(f"[세션유지] {aid} 확인 실패: {exc.__class__.__name__}")
        self._log(f"[세션유지] {len(ids)}계정 중 {alive}개 세션 유지됨 "
                  f"(만료 {len(ids) - alive}개는 다음 실행 때 로그인). 다음 확인 {self._interval // 60}분 뒤")
