"""인증 쿠키 종류 점검 — KEYCLOAK_IDENTITY 가 세션쿠키냐 지속쿠키냐(전원 off 생존 판별).

로그인 0회·읽기전용(프로필의 Chrome Cookies SQLite 를 immutable 로 열어 name/만료만 확인, 값 미복호화).
Remember Me 적용 전후 대조용:
    (Remember Me 켜고 사무실 로그인 후) python tools/check_auth_cookies.py <계정ID ...>
    → KEYCLOAK_IDENTITY 가 '지속(만료 …)' 로 바뀌면 성공(전원off·재부팅 후 세션 복원 가능).
인자 없으면 data/profiles 의 모든 계정 점검.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_PROFILES_DIR = Path("data/profiles")
_COOKIE_SUBPATHS = ("Default/Network/Cookies", "Default/Cookies", "Network/Cookies", "Cookies")
# 로그인 유지의 핵심 + 참고용 쿠키
_WATCH = ("KEYCLOAK_IDENTITY", "KEYCLOAK_IDENTITY_LEGACY", "KEYCLOAK_REMEMBER_ME",
          "KEYCLOAK_SESSION", "seller-uid", "_abck")


def _cookie_db(account_id: str) -> Path | None:
    base = _PROFILES_DIR / account_id
    for sub in _COOKIE_SUBPATHS:
        p = base / sub
        if p.exists():
            return p
    return None


def _fmt_expiry(has_expires: int, expires_utc: int) -> str:
    if not (has_expires and expires_utc):
        return "세션쿠키(브라우저 종료·전원off 시 소멸 → 재로그인 필요)"
    # Chrome expires_utc = 1601-01-01 부터의 마이크로초
    dt = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=expires_utc)
    left = (dt - datetime.now(timezone.utc)).total_seconds() / 3600
    return f"지속쿠키(만료 {dt.astimezone().strftime('%Y-%m-%d %H:%M')} = {left:.1f}h 후)"


def check(account_id: str) -> None:
    db = _cookie_db(account_id)
    if db is None:
        print(f"=== {account_id} === (프로필/쿠키 DB 없음 — 미로그인)")
        return
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
        placeholders = ",".join("?" * len(_WATCH))
        q = ("SELECT name,host_key,has_expires,is_persistent,expires_utc FROM cookies "
             "WHERE host_key LIKE '%coupang%' AND name IN (" + placeholders + ")")
        rows = con.execute(q, _WATCH).fetchall()
        con.close()
    except Exception as exc:
        print(f"=== {account_id} === 읽기 실패({exc.__class__.__name__})")
        return
    print(f"=== {account_id} ===")
    if not rows:
        print("  (감시 쿠키 없음)")
    order = {n: i for i, n in enumerate(_WATCH)}
    for name, host, has_exp, _persist, exp in sorted(rows, key=lambda r: order.get(r[0], 99)):
        mark = "★" if name == "KEYCLOAK_IDENTITY" else " "
        print(f" {mark}{name:<24}{host:<22}{_fmt_expiry(has_exp, exp)}")


def _all_accounts() -> list[str]:
    if not _PROFILES_DIR.exists():
        return []
    return sorted(d.name for d in _PROFILES_DIR.iterdir()
                  if d.is_dir() and not d.name.startswith("_"))


if __name__ == "__main__":
    accounts = sys.argv[1:] or _all_accounts()
    if not accounts:
        print("점검할 프로필이 없습니다(data/profiles 비어있음).")
    for a in accounts:
        check(a)
    print("\n★ KEYCLOAK_IDENTITY 가 '지속쿠키'면 전원off·재부팅 후 재로그인 없이 세션 복원 가능(목표).")
