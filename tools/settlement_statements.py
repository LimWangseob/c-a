"""위탁정산서(관리 상품만) 만들기 — 명령줄 입구. 계산 = `src/coupang_analytics/settlement_statements.py`(T-25 이관 · 행동 불변).

    python tools/settlement_statements.py --out <출력 폴더> --managed-output <관리기준 output> --settle-dir <output/정산>
        --stats <정산집계.xlsx> --basis YYYY-MM-DD [--inputs <입력 폴더>] [--issued YYYY-MM-DD] [--settle-only <json>]

- 입력 폴더(기본 `output/정산서/입력`) 고정 이름 = settlement_statement_context.REQUIRED (+ 선택 contract_window_scope.json).
- 장부 기준일 = 받은 지급 줄의 정산일이 빠지지 않는 날(D-137 ⑤) · 관리기준 = 마지막 정상 실행의 결과(D-137 ⑥).
- `--settle-only` 를 안 주면 원장 '정산전용상품' 시트를 구글에서 실시간으로 읽음(옛 동작).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coupang_analytics import settlement_statements as ST  # noqa: E402


def _args(argv: list[str] | None = None) -> ST.ARGS:
    ap = argparse.ArgumentParser(description="위탁정산서(관리 상품만) 만들기")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--managed-output", required=True, type=Path)
    ap.add_argument("--settle-dir", required=True, type=Path)
    ap.add_argument("--stats", required=True, type=Path)
    ap.add_argument("--basis", required=True)
    ap.add_argument("--inputs", type=Path, default=ROOT / "output" / "정산서" / "입력")
    ap.add_argument("--issued", default=f"{date.today():%Y-%m-%d}")
    ap.add_argument("--settle-only", type=Path)
    ap.add_argument("--supp", type=Path)
    ap.add_argument("--snap", type=Path)
    a = ap.parse_args(argv)
    date.fromisoformat(a.basis)
    date.fromisoformat(a.issued)
    return ST.ARGS(out=a.out, managed_output=a.managed_output, settle_dir=a.settle_dir, stats=a.stats, basis=a.basis,
                   inputs=a.inputs, issued=a.issued, settle_only=a.settle_only, supp=a.supp, snap=a.snap)


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    args = _args(argv)
    try:
        ST.run(args)
    except FileNotFoundError as exc:
        print(f"❌ 시작 전 중단 — {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
