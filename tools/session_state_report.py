"""세션 관측 리포트 — `session_state` SQLite 를 사람이 읽기 좋게 출력(로그인 0회·안전).

사용:
    python tools/session_state_report.py                # 계정별 현재 상태 표
    python tools/session_state_report.py --events       # 최근 이벤트 40건
    python tools/session_state_report.py --events 계정ID # 그 계정 이벤트

비밀값(비번·쿠키·토큰)은 애초에 저장되지 않으므로 이 리포트에도 없다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

try:   # 콘솔/리다이렉트가 cp949 여도 한글/기호 출력 크래시 방지
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from coupang_analytics import session_state  # noqa: E402


def _states() -> None:
    rows = session_state.snapshot()
    if not rows:
        print("(기록 없음 — 아직 관측 이벤트가 없습니다)")
        return
    print(f"{'계정':<18}{'상태':<18}{'세션OK':<20}{'수집':<20}{'실패분류':<20}{'연속실패':>6}")
    print("-" * 102)
    for r in rows:
        print(f"{(r['account_id'] or ''):<18}{(r['state'] or ''):<18}"
              f"{(r['last_session_ok_at'] or '-'):<20}{(r['last_collection_at'] or '-'):<20}"
              f"{(r['failure_type'] or '-'):<20}{(r['consecutive_account_failures'] or 0):>6}")


def _events(account_id: str | None) -> None:
    rows = session_state.recent_events(account_id=account_id, limit=40)
    if not rows:
        print("(이벤트 없음)")
        return
    for r in rows:
        extra = []
        if r["failure_type"]:
            extra.append(r["failure_type"])
        if r["auth_redirect"] is not None:
            extra.append(f"redirect={'Y' if r['auth_redirect'] else 'N'}")
        if r["final_url"]:
            extra.append(r["final_url"])
        print(f"{r['ts']}  {(r['account_id'] or ''):<16}{(r['event_type'] or ''):<20}"
              f"{'  '.join(extra)}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--events":
        _events(args[1] if len(args) > 1 else None)
    else:
        _states()
