"""pytest 진입점 — 이 프로젝트의 회귀 게이트는 `tools/run_checks.py`(오프라인·결정적·로그인/실API 없음)다.

pytest 를 돌리면 여기서 그 게이트(빠른 검증 5종: 시뮬·핀3·구글시트)를 실행한다. 목적:
  1) 게이트를 표준 `pytest` 로도 실행할 수 있게 하고,
  2) pytest 가 수집할 테스트가 하나도 없어 'no tests ran'(exit 5)로 오탐 차단되던 것을 없앤다.
전체 6종은 `python tools/run_checks.py`(pre-push 훅)에서 돈다.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_regression_gate_quick():
    """회귀 게이트 빠른 검증(run_checks --quick)이 초록이어야 한다."""
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "run_checks.py"), "--quick"],
        cwd=str(ROOT),
    )
    assert proc.returncode == 0, "회귀 게이트(run_checks.py --quick) 실패 — 회귀 가능"
