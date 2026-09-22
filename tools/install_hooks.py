"""git 훅 설치/제거 — 회귀 게이트를 커밋/푸시에 자동 연결한다(버전관리 재설치용).

3계층(designs/CODE_HEALTH_PLAN.md §단계1):
  1) pre-commit  : 스테이징된 .py 문법 컴파일 + `run_checks.py --quick`(시뮬+구글시트, 빠른 오프라인).
  2) pre-push    : `run_checks.py`(전체 3종) + `check_complexity.py`(MI 회귀 차단·괴물함수 경고).

훅 본문은 이 파일이 유일 출처(SSOT)다. 새 PC/재설치:
    python tools/install_hooks.py            # 설치(.git/hooks/ 에 기록)
    python tools/install_hooks.py --uninstall
    python tools/install_hooks.py --status

훅을 건너뛰고 커밋해야 하면(응급) `git commit --no-verify`. 상시 우회는 금지(회귀 유입).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

_MARK = "# coupang-analytics-hook"   # 우리가 설치한 훅 식별(덮어쓰기/제거 판단)

PRE_COMMIT = f"""#!/bin/sh
{_MARK} pre-commit — 회귀 게이트(빠른). 재설치: python tools/install_hooks.py
set -e
files=$(git diff --cached --name-only --diff-filter=ACM -- '*.py')
if [ -n "$files" ]; then
  python -m py_compile $files
fi
python tools/run_checks.py --quick
"""

PRE_PUSH = f"""#!/bin/sh
{_MARK} pre-push — 회귀 게이트(전체)+품질. 재설치: python tools/install_hooks.py
set -e
python tools/run_checks.py
python tools/check_complexity.py
"""

HOOKS = {"pre-commit": PRE_COMMIT, "pre-push": PRE_PUSH}


def _hooks_dir() -> Path:
    try:
        out = subprocess.run(["git", "rev-parse", "--git-path", "hooks"],
                             cwd=str(ROOT), capture_output=True, text=True, check=True)
        p = Path(out.stdout.strip())
    except Exception:
        p = ROOT / ".git" / "hooks"
    if not p.is_absolute():
        p = ROOT / p
    return p


def _is_ours(path: Path) -> bool:
    return path.exists() and _MARK in path.read_text(encoding="utf-8", errors="replace")


def install() -> int:
    hooks = _hooks_dir()
    hooks.mkdir(parents=True, exist_ok=True)
    for name, body in HOOKS.items():
        path = hooks / name
        if path.exists() and not _is_ours(path):
            print(f"  ⚠ {name}: 기존(우리 것 아님) 훅 존재 → 건드리지 않음. 수동 병합 필요: {path}")
            continue
        path.write_text(body, encoding="utf-8", newline="\n")
        path.chmod(0o755)
        print(f"  ✅ 설치: {path}")
    print("완료 — 이제 커밋 시 빠른 검증, 푸시 시 전체+품질 게이트가 자동으로 돕니다.")
    print("(응급 우회: git commit --no-verify — 상시 사용 금지)")
    return 0


def uninstall() -> int:
    hooks = _hooks_dir()
    for name in HOOKS:
        path = hooks / name
        if _is_ours(path):
            path.unlink()
            print(f"  🗑 제거: {path}")
        elif path.exists():
            print(f"  · {name}: 우리 훅 아님 → 유지")
        else:
            print(f"  · {name}: 없음")
    return 0


def status() -> int:
    hooks = _hooks_dir()
    print(f"훅 폴더: {hooks}")
    for name in HOOKS:
        path = hooks / name
        state = "설치됨(우리 것)" if _is_ours(path) else ("있음(다른 훅)" if path.exists() else "없음")
        print(f"  {name}: {state}")
    return 0


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--uninstall":
        return uninstall()
    if arg == "--status":
        return status()
    return install()


if __name__ == "__main__":
    raise SystemExit(main())
