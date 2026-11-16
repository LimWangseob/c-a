"""장부 DB 시험본 입구 — 오프라인만(쿠팡 로그인·API 없음) · 원천은 읽기만 · 결과는 시험 폴더에만.

    python tools/ledger_db.py build --output <운용 output 사본> --db <새 sqlite 경로> [--exclude Difpick] [--only a,b] [--parts settle,cost,...]

- 계획 = output/_시험_261116_장부DB/계획.md · 제외 계정·시험 계정은 인자로만(D-229).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import sqlite3  # noqa: E402

from coupang_analytics import ledger_build, ledger_verify  # noqa: E402


def _args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="장부 DB 시험본")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="원천 → 새 DB")
    b.add_argument("--output", required=True, type=Path, help="운용 output 폴더(사본)")
    b.add_argument("--db", required=True, type=Path)
    b.add_argument("--exclude", default="", help="쉼표로 나눈 제외 계정ID")
    b.add_argument("--only", default="", help="쉼표로 나눈 계정ID 만(시험용)")
    b.add_argument("--parts", default=",".join(ledger_build.PARTS), help="읽을 묶음(기본 전부)")
    v = sub.add_parser("verify", help="검증 V2~V7(+ --twin 이 있으면 V1 표 해시 비교)")
    v.add_argument("--db", required=True, type=Path)
    v.add_argument("--twin", type=Path, help="같은 입력으로 다시 만든 DB(V1)")
    return ap.parse_args(argv)


def _set(s: str) -> frozenset[str]:
    return frozenset(x.strip() for x in s.split(",") if x.strip())


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except AttributeError:
        pass
    a = _args(argv)
    t0 = time.time()
    if a.cmd == "build":
        rep = ledger_build.build(a.output, a.db, exclude=_set(a.exclude), only=_set(a.only),
                                 parts=tuple(p for p in a.parts.split(",") if p))
        for line in rep:
            print(line)
    elif a.cmd == "verify":
        con = sqlite3.connect(a.db)
        if a.twin:
            same = ledger_verify.same_hashes(con, sqlite3.connect(a.twin))
            print(f"V1 다시 만든 DB 표 해시 같음: {sum(same.values())}/{len(same)} · 다른 표 {[t for t, ok in same.items() if not ok]}")
        for line in ledger_verify.run(con):
            print(line)
        con.close()
    print(f"끝 {time.time() - t0:.0f}초")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
