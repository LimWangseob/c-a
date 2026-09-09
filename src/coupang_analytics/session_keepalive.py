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
from typing import NamedTuple

from . import config
from . import session_state
from .browser import WING_URL, WingBrowser
from .pipeline import account_profile

# keep-warm 터치 결과 분류 — 단순 redirect 여부가 아니라 "IdP 인증요청이 실제로 일어났는지"까지 구분.
# (Keycloak: SSO Idle 은 인증요청/refresh-token 요청 시 갱신 → APP_ONLY 는 갱신 안 됐을 수 있음)
OUT_AUTH_SSO_SUCCESS = "AUTH_SSO_SUCCESS"  # IdP(xauth/oidc) 거쳐 세션 유효 복귀 = Idle 갱신 신호(가장 강)
OUT_APP_ONLY = "APP_ONLY"                  # 유효하나 IdP 미접촉(WING 로컬응답) = Idle 갱신 불확실
OUT_EXPIRED = "EXPIRED"                    # 세션 만료(로그인 폼) — keep-warm 실패
OUT_CHALLENGE = "CHALLENGE"                # Akamai 차단/봇 챌린지
# IdP(Keycloak/xauth) 접촉을 나타내는 URL 마커. login-actions(=credential POST)는 GET-only 흐름엔 안 나옴.
_IDP_MARKERS = ("xauth", "/sso/", "openid-connect", "login-actions")


class TouchResult(NamedTuple):
    alive: bool          # 세션 유효(대시보드 도달 + 인증쿠키)
    outcome: str         # 위 OUT_* 분류
    reached_idp: bool    # 접속 중 IdP(xauth/oidc)로 리다이렉트가 실제 있었는지
    final: str           # 최종 URL


def touch_session(account_id: str, wait_ms: int = 1200) -> TouchResult:
    """프로필을 열어 WING 접속(안전 GET, 로그인 시도 없음) 후 결과를 분류해 반환.

    분류(redirect 유무만이 아니라 IdP 접촉+유효성 조합):
    - CHALLENGE        : Akamai 차단/챌린지(classify_login blocked/akamai)
    - AUTH_SSO_SUCCESS : 유효 + IdP 접촉(리다이렉트) = 인증요청이 일어나 Idle 갱신 신호(가장 강)
    - APP_ONLY         : 유효하나 IdP 미접촉 = WING 로컬응답, Idle 갱신 불확실
    - EXPIRED          : 무효(로그인 폼)
    """
    seen: list[str] = []
    with WingBrowser(profile_dir=account_profile(account_id), offscreen=True) as b:
        b.page.on("framenavigated",
                  lambda fr: seen.append(fr.url) if fr == b.page.main_frame else None)
        b.goto(WING_URL)
        b.page.wait_for_timeout(wait_ms)
        alive = b.authenticated()
        code = b.classify_login()[0]   # blocked/akamai 구분용(alive 면 'success')
        final = b.page.url
    reached = any(any(m in (u or "") for m in _IDP_MARKERS) for u in seen)
    if code in ("blocked", "akamai"):
        outcome = OUT_CHALLENGE
    elif alive:
        outcome = OUT_AUTH_SSO_SUCCESS if reached else OUT_APP_ONLY
    else:
        outcome = OUT_EXPIRED
    return TouchResult(alive, outcome, reached, final)


def keepwarm_once(account_ids, on_log=print, exclude=(), stop_check=None) -> dict:
    """계정들 세션을 1회씩 살려둠(결과 분류를 관측 이벤트로 기록). 카운트 dict 반환.

    반환: {attempted, alive, expired, app_only, challenge, error}.
    exclude    : 제외할 계정(예: TTL 측정 코호트 — 건드리면 측정 오염).
    stop_check : () -> bool, True 면 중단(스레드 종료 신호).
    """
    ids = [a for a in account_ids if a not in set(exclude)]
    c = {"attempted": 0, "alive": 0, "expired": 0, "app_only": 0, "challenge": 0, "error": 0}
    for aid in ids:
        if stop_check and stop_check():
            break
        c["attempted"] += 1
        try:
            r = touch_session(aid)
            session_state.record_event(   # 관측만(백그라운드 프로브 — 파이프라인 상태를 덮지 않음)
                aid, f"keepwarm_{r.outcome.lower()}", final_url=r.final, auth_redirect=r.reached_idp)
            if r.alive:
                c["alive"] += 1
            if r.outcome == OUT_EXPIRED:
                c["expired"] += 1
            elif r.outcome == OUT_APP_ONLY:
                c["app_only"] += 1
            elif r.outcome == OUT_CHALLENGE:
                c["challenge"] += 1
        except Exception as exc:          # best-effort — 사유만 남기고 다음 계정
            c["error"] += 1
            on_log(f"[세션유지] {aid} 확인 실패: {exc.__class__.__name__}")
    return c


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
        c = keepwarm_once(ids, on_log=self._log, exclude=self._exclude_fn(),
                          stop_check=self._stop.is_set)
        self._log(f"[세션유지] {c['attempted']}계정 중 {c['alive']}개 유지"
                  f"(만료 {c['expired']}·IdP미접촉 {c['app_only']}·챌린지 {c['challenge']}). "
                  f"다음 확인 {self._interval // 60}분 뒤")
