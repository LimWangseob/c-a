r"""상시 세션 keep-warm — 앱과 무관하게 로그인된 세션을 살려둔다(재로그인·차단 근본 축소).

차단 근본원인 = 세션이 방치로 죽어 매번 재로그인 → 로그인 POST가 Akamai에 걸림. 이 스크립트를
**Windows 작업 스케줄러로 25분마다** 돌리면(앱을 안 열어둬도) 세션이 계속 살아 재로그인 자체가 줄어든다.
안전 GET 만 하며 로그인 시도·지문위조 없음(만료 계정은 폼만 뜨고 건너뜀). 관측층에 결과가 자동 기록된다.

- 대상 = `data/profiles/` 아래 실제 로그인 프로필이 있는 계정(세션이 있어야 데울 수 있음).
- **TTL 측정 중인 코호트(`data/ttl_cohort.json`의 미프로브 계정)는 자동 제외** — 데우면 측정 오염.

사용:
    python tools/keepwarm.py --once           # 1회 패스(작업 스케줄러용)
    python tools/keepwarm.py --loop [분]       # 포그라운드 연속(기본 25분 간격)
    python tools/keepwarm.py --status          # 대상/제외 계정만 표시(브라우저 안 엶)

작업 스케줄러 등록(25분마다, 로그인 세션에서):
    schtasks /Create /TN coupang-keepwarm /SC MINUTE /MO 25 /F ^
      /TR "cmd /c cd /d D:\coupang-analytics && python tools\keepwarm.py --once >> output\keepwarm.log 2>&1"
    (해제: schtasks /Delete /TN coupang-keepwarm /F)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from coupang_analytics import config  # noqa: E402
from coupang_analytics.session_keepalive import keepwarm_once  # noqa: E402

_PROFILES_DIR = Path("data/profiles")
_COHORT_PATH = Path("data/ttl_cohort.json")


def profile_accounts() -> list[str]:
    """로그인 프로필이 있는 계정(=세션 보유 가능) 목록."""
    if not _PROFILES_DIR.exists():
        return []
    # '_' 로 시작하는 내부·테스트 프로필(_repro_* 등)은 실제 계정이 아니므로 제외
    return sorted(d.name for d in _PROFILES_DIR.iterdir()
                  if d.is_dir() and not d.name.startswith("_"))


def cohort_exclude() -> set[str]:
    """TTL 측정 중(미프로브) 코호트 계정 — keep-warm 제외(측정 오염 방지)."""
    if not _COHORT_PATH.exists():
        return set()
    try:
        plan = json.loads(_COHORT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {aid for aid, e in plan.items() if e.get("probed_at") is None}


def _once(log=print) -> None:
    ids = profile_accounts()
    exclude = cohort_exclude()
    if not ids:
        log("[keepwarm] 대상 프로필 없음(data/profiles 비어있음) — 먼저 계정 로그인 필요")
        return
    if exclude:
        log(f"[keepwarm] TTL 측정 코호트 제외: {', '.join(sorted(exclude))}")
    alive, total = keepwarm_once(ids, on_log=log, exclude=exclude)
    log(f"[keepwarm] {time.strftime('%Y-%m-%d %H:%M:%S')} — {total}계정 중 {alive}개 유지"
        f"(만료 {total - alive}). DB={config.SESSION_STATE_DB}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--status":
        ids, ex = profile_accounts(), cohort_exclude()
        print(f"대상 프로필 {len(ids)}개: {', '.join(ids) or '(없음)'}")
        print(f"제외(측정 코호트) {len(ex)}개: {', '.join(sorted(ex)) or '(없음)'}")
        print(f"실제 keep-warm 대상: {len([a for a in ids if a not in ex])}개")
    elif args and args[0] == "--loop":
        interval = int(args[1]) * 60 if len(args) > 1 else config.SESSION_KEEPALIVE_MIN * 60
        print(f"[keepwarm] 연속 모드 — {interval // 60}분 간격 (Ctrl+C 로 종료)")
        try:
            while True:
                _once()
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n[keepwarm] 종료")
    elif args and args[0] == "--once":
        _once()
    else:
        print(__doc__)
