"""세션 관측(observability) — 추측 대신 실측을 위한 상태 테이블 + 이벤트 로그(평문 SQLite).

**의사결정·관측용 조언 저장소**이지 재개 권위가 아니다(재개 권위=`쿠팡데이타분석_진행중.json`,
세션 blob=DPAPI `SessionStore`). 깨져도 다시 채워지며, **비밀값(비번·쿠키·토큰)은 절대 저장하지 않는다**.

두 테이블:
- `account_session_state` : 계정별 현재 상태 1행(READY/REAUTH_REQUIRED/ACCOUNT_BLOCKED/AUTH_ENV_BLOCKED/DISABLED).
- `session_events`        : 관측 이벤트 append-only(시각·계정·유형·실패분류·최종URL(쿼리 제거)·상태코드·리다이렉트여부·소요ms).

`failure_type_of(code, detail)`가 `browser.classify_login()`의 (코드, 상세)를 세분 실패분류로 매핑한다
(로그인 탐지 코드는 건드리지 않고 그 출력을 해석 — 함정 재발 방지). `is_global_signal()`은 그중
환경/전역 신호(IP·챌린지·레이트)만 골라 전역 서킷 후보로 표시한다.

관측 기록은 **best-effort**: 실패해도 수집을 막지 않고 사유만 print(무음 pass 아님).
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from . import config

# ── 상태(5개로 단순화) ──────────────────────────────────────────
STATE_READY = "READY"                    # 세션 정상 · 수집 가능
STATE_REAUTH_REQUIRED = "REAUTH_REQUIRED"  # 세션 만료/2차인증 필요 — 정상 재인증 대상
STATE_ACCOUNT_BLOCKED = "ACCOUNT_BLOCKED"  # 그 계정만의 문제(비번오류·계정잠금·90일휴면·OTP5회잠금)
STATE_AUTH_ENV_BLOCKED = "AUTH_ENV_BLOCKED"  # 환경/전역 차단(Akamai 접근차단·봇챌린지·레이트) — 전역 서킷 후보
STATE_DISABLED = "DISABLED"              # 운영에서 의도적으로 제외(사람이 지정)

# ── 실패 분류(taxonomy) ─────────────────────────────────────────
FAIL_BAD_CREDENTIAL = "AUTH_BAD_CREDENTIAL"  # 계정 스코프
FAIL_ACCOUNT_LOCKED = "ACCOUNT_LOCKED"       # 계정 스코프(보안관리자 잠금)
FAIL_DORMANT_90D = "DORMANT_90D"             # 계정 스코프(90일 미로그인 휴면)
FAIL_MFA_LOCKED = "MFA_LOCKED"               # 계정 스코프(인증번호 5회 오류 잠금)
FAIL_MFA_REQUIRED = "MFA_REQUIRED"           # 정상 재인증(2차인증 입력칸)
FAIL_SESSION_EXPIRED = "SESSION_EXPIRED"     # 정상 재인증(폼 지속/세션 만료)
FAIL_RATE_LIMITED = "RATE_LIMITED"           # 전역 신호(현재 로그인 단계 관측 신호 없음 — 데이터API용 예비)
FAIL_CHALLENGE_PAGE = "CHALLENGE_PAGE"       # 전역 신호(Akamai 봇 챌린지 오버레이)
FAIL_ACCESS_BLOCKED = "ACCESS_BLOCKED"       # 전역 신호(Akamai 전면 차단 Access Denied)
FAIL_NETWORK_ERROR = "NETWORK_ERROR"         # 일시(상태 변경 안 함)
FAIL_UNKNOWN = "UNKNOWN_AUTH_ERROR"          # 미상(상태 변경 안 함)

# 전역(환경) 서킷 후보 — 이것만 IP 차원 신호로 취급(계정 스코프 오류는 전역 중단시키지 않음)
_GLOBAL_SIGNALS = frozenset({FAIL_ACCESS_BLOCKED, FAIL_CHALLENGE_PAGE, FAIL_RATE_LIMITED})
# 계정 연속실패 카운터를 올리는 계정 스코프 실패
_ACCOUNT_FAILURES = frozenset({FAIL_BAD_CREDENTIAL, FAIL_ACCOUNT_LOCKED, FAIL_DORMANT_90D, FAIL_MFA_LOCKED})

_STATE_FOR_FAILURE = {
    FAIL_SESSION_EXPIRED: STATE_REAUTH_REQUIRED,
    FAIL_MFA_REQUIRED: STATE_REAUTH_REQUIRED,
    FAIL_BAD_CREDENTIAL: STATE_ACCOUNT_BLOCKED,
    FAIL_ACCOUNT_LOCKED: STATE_ACCOUNT_BLOCKED,
    FAIL_DORMANT_90D: STATE_ACCOUNT_BLOCKED,
    FAIL_MFA_LOCKED: STATE_ACCOUNT_BLOCKED,
    FAIL_ACCESS_BLOCKED: STATE_AUTH_ENV_BLOCKED,
    FAIL_CHALLENGE_PAGE: STATE_AUTH_ENV_BLOCKED,
    FAIL_RATE_LIMITED: STATE_AUTH_ENV_BLOCKED,
    # NETWORK_ERROR·UNKNOWN 은 일시적일 수 있어 상태를 바꾸지 않는다(이벤트만 기록)
}


def failure_type_of(code: str, detail: str = "") -> str:
    """browser.classify_login()의 (코드, 상세) → 세분 실패분류. 로그인 탐지 코드는 건드리지 않고 해석만.

    code error 는 #input-error 메시지 4종을 문자열로 넘기므로 여기서 세분한다(문구는 CLAUDE.md 실측).
    """
    d = detail or ""
    if code == "blocked":
        return FAIL_ACCESS_BLOCKED
    if code == "akamai":
        return FAIL_CHALLENGE_PAGE
    if code == "otp":
        return FAIL_MFA_REQUIRED
    if code == "form":
        return FAIL_SESSION_EXPIRED   # 폼 지속 = 세션 만료/재렌더
    if code == "error":
        if ("보안관리자" in d) or ("잠금처리" in d):
            return FAIL_ACCOUNT_LOCKED
        if ("인증번호를 5번" in d) or ("5번 잘못" in d):
            return FAIL_MFA_LOCKED
        if ("90일" in d) or ("로그인 이력이 없" in d) or ("사용이 중지" in d):
            return FAIL_DORMANT_90D
        return FAIL_BAD_CREDENTIAL
    return FAIL_UNKNOWN


def is_global_signal(failure_type: str) -> bool:
    """이 실패분류가 환경/전역(IP·챌린지·레이트) 신호인지 — 전역 서킷 후보 판정."""
    return failure_type in _GLOBAL_SIGNALS


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_url(url: str | None) -> str | None:
    """최종 URL 을 저장하되 쿼리·프래그먼트(개인정보 가능)를 제거하고 길이 제한."""
    if not url:
        return None
    try:
        s = urlsplit(url)
        return urlunsplit((s.scheme, s.netloc, s.path, "", ""))[:200]
    except Exception:
        return url[:200]


def _db_path(db_path: str | None) -> Path:
    return Path(db_path or config.SESSION_STATE_DB)


def _connect(db_path: str | None):
    p = _db_path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p), timeout=5.0)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=5000")
    con.execute(
        "CREATE TABLE IF NOT EXISTS account_session_state ("
        " account_id TEXT PRIMARY KEY,"
        " state TEXT,"
        " last_session_ok_at TEXT,"
        " last_collection_at TEXT,"
        " last_auth_at TEXT,"
        " last_auth_required_at TEXT,"
        " last_failure_at TEXT,"
        " failure_type TEXT,"
        " consecutive_account_failures INTEGER DEFAULT 0,"
        " global_block_signal INTEGER DEFAULT 0,"
        " updated_at TEXT)")
    con.execute(
        "CREATE TABLE IF NOT EXISTS session_events ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " ts TEXT, account_id TEXT, event_type TEXT, failure_type TEXT,"
        " final_url TEXT, http_status INTEGER, auth_redirect INTEGER, elapsed_ms INTEGER)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_events_acc ON session_events(account_id)")
    con.execute(
        "CREATE TABLE IF NOT EXISTS keepwarm_runs ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " started_at TEXT, finished_at TEXT,"
        " attempted INTEGER, alive INTEGER, expired INTEGER,"
        " app_only INTEGER, challenge INTEGER, error INTEGER)")
    return con


def _apply(account_id: str, event_type: str, *, state: str | None = None,
           stamp_fields: tuple[str, ...] = (), failure_type: str | None = None,
           inc_account_failures: bool = False, reset_account_failures: bool = False,
           global_signal: bool = False, final_url: str | None = None,
           http_status: int | None = None, auth_redirect: bool | None = None,
           elapsed_ms: int | None = None, db_path: str | None = None) -> None:
    """상태 행 upsert + 이벤트 1건 기록(한 트랜잭션). 실패는 print 후 삼킴(관측이 수집 막지 않음)."""
    now = _now()
    try:
        with closing(_connect(db_path)) as con, con:
            row = con.execute(
                "SELECT consecutive_account_failures FROM account_session_state WHERE account_id=?",
                (account_id,)).fetchone()
            fails = (row[0] if row and row[0] is not None else 0)
            if reset_account_failures:
                fails = 0
            elif inc_account_failures:
                fails += 1
            # 갱신할 컬럼 구성(지정된 것만 덮어씀)
            sets = {"updated_at": now, "consecutive_account_failures": fails}
            if state is not None:
                sets["state"] = state
            for f in stamp_fields:
                sets[f] = now
            if failure_type is not None:
                sets["failure_type"] = failure_type
                sets["last_failure_at"] = now
            sets["global_block_signal"] = 1 if global_signal else 0
            cols = ["account_id"] + list(sets.keys())
            vals = [account_id] + list(sets.values())
            placeholders = ",".join("?" * len(cols))
            updates = ",".join(f"{c}=excluded.{c}" for c in sets)
            con.execute(
                f"INSERT INTO account_session_state ({','.join(cols)}) VALUES ({placeholders}) "
                f"ON CONFLICT(account_id) DO UPDATE SET {updates}", vals)
            con.execute(
                "INSERT INTO session_events (ts,account_id,event_type,failure_type,final_url,"
                "http_status,auth_redirect,elapsed_ms) VALUES (?,?,?,?,?,?,?,?)",
                (now, account_id, event_type, failure_type, _safe_url(final_url),
                 http_status, (None if auth_redirect is None else int(auth_redirect)), elapsed_ms))
    except Exception as exc:   # 관측 실패는 치명적 아님 — 사유만 남기고 진행
        print(f"[세션관측] 기록 실패({exc.__class__.__name__}: {str(exc)[:80]}) — 수집엔 영향 없음")


# ── 파이프라인/킵얼라이브에서 부르는 관측 훅 ──────────────────────
def observe_session_ok(account_id, *, final_url=None, auth_redirect=None,
                       elapsed_ms=None, db_path=None) -> None:
    """세션 재사용 성공(로그인 없이 대시보드 도달) — READY."""
    _apply(account_id, "session_ok", state=STATE_READY,
           stamp_fields=("last_session_ok_at",), reset_account_failures=True,
           final_url=final_url, auth_redirect=auth_redirect, elapsed_ms=elapsed_ms, db_path=db_path)


def observe_reauth_required(account_id, *, final_url=None, db_path=None) -> None:
    """세션 만료로 로그인 대기열로 미룸(자동제출 안 함) — REAUTH_REQUIRED."""
    _apply(account_id, "reauth_required", state=STATE_REAUTH_REQUIRED,
           stamp_fields=("last_auth_required_at",), final_url=final_url, db_path=db_path)


def observe_auth_success(account_id, *, final_url=None, elapsed_ms=None, db_path=None) -> None:
    """로그인(재인증) 성공 — READY, 계정 연속실패 리셋."""
    _apply(account_id, "auth_success", state=STATE_READY,
           stamp_fields=("last_auth_at", "last_session_ok_at"), reset_account_failures=True,
           final_url=final_url, elapsed_ms=elapsed_ms, db_path=db_path)


def observe_auth_failure(account_id, failure_type, *, final_url=None, db_path=None) -> None:
    """로그인(재인증) 실패 — 실패분류→상태 매핑, 계정스코프면 연속실패++, 전역신호면 표시."""
    _apply(account_id, "auth_failure",
           state=_STATE_FOR_FAILURE.get(failure_type),   # None 이면 상태 유지
           failure_type=failure_type,
           inc_account_failures=(failure_type in _ACCOUNT_FAILURES),
           global_signal=is_global_signal(failure_type),
           final_url=final_url, db_path=db_path)


def observe_collection_done(account_id, *, db_path=None) -> None:
    """그 계정 수집 완료 — 마지막 수집시각 갱신(상태는 READY 유지)."""
    _apply(account_id, "collection_done", state=STATE_READY,
           stamp_fields=("last_collection_at",), db_path=db_path)


def observe_collection_empty(account_id, *, db_path=None) -> None:
    """판매 데이터 없음(정상) — 세션은 정상이라 READY, 수집시각은 갱신하지 않음."""
    _apply(account_id, "collection_empty", state=STATE_READY, db_path=db_path)


def record_event(account_id, event_type, *, failure_type=None, final_url=None,
                 http_status=None, auth_redirect=None, elapsed_ms=None, db_path=None) -> None:
    """상태를 바꾸지 않고 이벤트만 기록(측정 도구·킵얼라이브 프로브 등 관측 전용)."""
    _apply(account_id, event_type, failure_type=failure_type, final_url=final_url,
           http_status=http_status, auth_redirect=auth_redirect, elapsed_ms=elapsed_ms,
           db_path=db_path)


def set_state(account_id, state, db_path=None) -> None:
    """계정 상태를 사람이 직접 지정(예: 중지 계정 DISABLED, 복귀 시 재평가). 이벤트도 남김."""
    _apply(account_id, "state_set", state=state, db_path=db_path)


# keep-warm 터치 결과(문자열) → 계정 상태. CHALLENGE(환경/일시)는 상태 안 바꿈.
_KEEPWARM_STATE = {
    "AUTH_SSO_SUCCESS": STATE_READY, "APP_ONLY": STATE_READY,
    "EXPIRED": STATE_REAUTH_REQUIRED,
}


def observe_keepwarm(account_id, outcome, *, reached_idp=None, final_url=None,
                     alive=False, db_path=None) -> None:
    """keep-warm 1터치를 이벤트로 남기고 생존여부로 상태 갱신(다음 패스가 죽은 세션을 안 두드리게).

    alive 면 READY(+세션OK시각·연속실패 리셋), EXPIRED 면 REAUTH_REQUIRED, CHALLENGE 면 상태 유지.
    """
    _apply(account_id, f"keepwarm_{outcome.lower()}",
           state=_KEEPWARM_STATE.get(outcome),
           stamp_fields=("last_session_ok_at",) if alive else (),
           reset_account_failures=alive,
           final_url=final_url, auth_redirect=reached_idp, db_path=db_path)


def accounts_in_states(states, db_path=None) -> set[str]:
    """현재 상태가 주어진 집합에 속하는 계정ID 집합(keep-warm/수집 제외 판정용)."""
    states = tuple(states)
    if not states:
        return set()
    try:
        with closing(_connect(db_path)) as con:
            q = ("SELECT account_id FROM account_session_state WHERE state IN (%s)"
                 % ",".join("?" * len(states)))
            return {r[0] for r in con.execute(q, states)}
    except Exception as exc:
        print(f"[세션관측] 상태 조회 실패({exc.__class__.__name__})")
        return set()


def is_disabled(account_id, db_path=None) -> bool:
    """사람이 중지(DISABLED)로 표시한 계정인지 — 수집/로그인 시도 자체를 건너뛰기용."""
    return account_id in accounts_in_states((STATE_DISABLED,), db_path)


def record_keepwarm_run(started_at: str, counts: dict, db_path=None) -> None:
    """keep-warm 1회 패스 요약 기록(run_id·시작/종료·시도/유지/만료/앱온리/챌린지/오류)."""
    try:
        with closing(_connect(db_path)) as con, con:
            con.execute(
                "INSERT INTO keepwarm_runs (started_at,finished_at,attempted,alive,expired,"
                "app_only,challenge,error) VALUES (?,?,?,?,?,?,?,?)",
                (started_at, _now(), counts.get("attempted", 0), counts.get("alive", 0),
                 counts.get("expired", 0), counts.get("app_only", 0),
                 counts.get("challenge", 0), counts.get("error", 0)))
    except Exception as exc:
        print(f"[세션관측] keepwarm run 기록 실패({exc.__class__.__name__})")


def snapshot(db_path=None) -> list[dict]:
    """계정별 현재 상태 전체를 dict 리스트로 반환(리포트·UI용). 없으면 빈 리스트."""
    try:
        with closing(_connect(db_path)) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT * FROM account_session_state ORDER BY updated_at DESC").fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        print(f"[세션관측] 조회 실패({exc.__class__.__name__})")
        return []


def recent_events(account_id=None, limit=50, db_path=None) -> list[dict]:
    """최근 이벤트 목록(계정 지정 시 그 계정만). 리포트·디버깅용."""
    try:
        with closing(_connect(db_path)) as con:
            con.row_factory = sqlite3.Row
            if account_id:
                rows = con.execute(
                    "SELECT * FROM session_events WHERE account_id=? ORDER BY id DESC LIMIT ?",
                    (account_id, limit)).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM session_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        print(f"[세션관측] 이벤트 조회 실패({exc.__class__.__name__})")
        return []
