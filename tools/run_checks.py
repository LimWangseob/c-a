"""회귀 게이트 — 오프라인 검증 3종을 순차 실행하고 하나라도 실패하면 exit 1.

용도: 커밋/푸시 전(git 훅) 또는 수동으로 회귀를 잡는다. 모두 **로그인·실 API 없이** 결정적으로 돈다
(verify_offline [6]도 기본은 결정적 모킹 — 실 API는 VERIFY_REAL_API=1 옵트인).

    python tools/run_checks.py           # 전체 3종 (pre-push, <30s)
    python tools/run_checks.py --quick   # 빠른 2종만 (pre-commit, <10s)

각 스크립트는 실패 시 non-zero로 끝난다(assert/SystemExit). 여기선 하나가 죽어도 나머지를 계속
돌려 **전체 결과를 한 번에** 보여주고, 실패가 하나라도 있으면 최종 exit 1.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

# (표시명, 스크립트, quick 포함 여부) — quick=커밋 전 빠른 것만
CHECKS = [
    ("시뮬레이션(파이프라인 14시나리오)", "tools/simulate_pipeline.py", True),
    ("핀(로그인·발견·반자동순위 실제코드)", "tools/pin_login_ranks.py", True),
    ("핀(apply_style 서식 출력)", "tools/pin_apply_style.py", True),
    ("핀(실행모드 결정 plan_run_mode)", "tools/pin_run_plan.py", True),
    ("구글시트 오프라인 검증", "tools/verify_gsheet_offline.py", True),
    ("오프라인 실증(워크북·매칭·키워드선정)", "tools/verify_offline.py", False),
]

# 자식 콘솔창 억제(무인/pythonw 실행 시 검은 창 깜빡임 방지, Windows 전용)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(name: str, script: str) -> tuple[bool, float, str]:
    started = time.monotonic()
    proc = subprocess.run(
        [sys.executable, script],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=_NO_WINDOW,
    )
    dur = time.monotonic() - started
    return proc.returncode == 0, dur, (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    quick = "--quick" in sys.argv[1:]
    checks = [c for c in CHECKS if not quick or c[2]]
    label = "빠른 검증(--quick)" if quick else "전체 검증"
    print("=" * 64)
    print(f"  회귀 게이트 — {label} ({len(checks)}종)")
    print("=" * 64)
    results: list[tuple[str, bool, float, str]] = []
    for name, script, _ in checks:
        print(f"▶ {name} …", flush=True)
        ok, dur, out = _run(name, script)
        results.append((name, ok, dur, out))
        print(f"  {'✅ 통과' if ok else '❌ 실패'}  ({dur:.1f}s)")
        if not ok:                       # 실패 시 원인 파악용으로 마지막 출력만 표시
            tail = "\n".join(out.rstrip().splitlines()[-20:])
            print("  ── 실패 출력(마지막 20줄) " + "─" * 30)
            for line in tail.splitlines():
                print("  │ " + line)
            print("  " + "─" * 52)
    total = sum(d for _, _, d, _ in results)
    failed = [n for n, ok, _, _ in results if not ok]
    print("=" * 64)
    if failed:
        print(f"  ❌ 실패 {len(failed)}종: {', '.join(failed)}  (총 {total:.1f}s)")
        print("=" * 64)
        return 1
    print(f"  ✅ 전부 통과 ({len(results)}종, 총 {total:.1f}s)")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
