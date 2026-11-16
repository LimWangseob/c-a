"""장부 DB 시험본 입구 — 오프라인만(쿠팡 로그인·API 없음) · 원천은 읽기만 · 결과는 시험 폴더에만.

    python tools/ledger_db.py build --output <운용 output 사본> --db <새 sqlite 경로> [--exclude Difpick] [--only a,b] [--parts settle,cost,...]
    python tools/ledger_db.py verify --db <DB> [--twin <다시 만든 DB>]
    python tools/ledger_db.py judge --db <DB> --rules <판정 폴더>
    python tools/ledger_db.py statement --db <DB> --scope <관리 범위 json> --out <결과 json>

- 계획 = output/_시험_261116_장부DB/계획.md · 제외 계정·시험 계정은 인자로만(D-229).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import json  # noqa: E402
import sqlite3  # noqa: E402

from coupang_analytics import ledger_build, ledger_judge, ledger_statement, ledger_verify  # noqa: E402


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
    j = sub.add_parser("judge", help="판정 규칙 파일(규칙_*.json)을 검증 결과에 적용(D-265 · verify 뒤)")
    j.add_argument("--db", required=True, type=Path)
    j.add_argument("--rules", required=True, type=Path, help="판정 폴더(규칙_*.json · 직접판정_*.json · 표본 출력)")
    s = sub.add_parser("statement", help="DB → 위탁정산서 관리 몫 숫자(4단계 · 관리 범위 = tools/ledger_scope_export.py 결과)")
    s.add_argument("--db", required=True, type=Path)
    s.add_argument("--scope", required=True, type=Path)
    s.add_argument("--out", required=True, type=Path)
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
    elif a.cmd == "judge":
        con = sqlite3.connect(a.db)
        for line in ledger_judge.run(con, a.rules):
            print(line)
        con.close()
    elif a.cmd == "statement":
        res = ledger_statement.build(a.db, a.scope)
        a.out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"계정 {len(res)} · 관리 상품 확인 필요 {sum(r['status'] != 'ok' for r in res.values())} · 저장 {a.out}")
    print(f"끝 {time.time() - t0:.0f}초")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
