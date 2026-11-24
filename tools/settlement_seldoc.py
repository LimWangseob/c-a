"""셀독 정산서 만들기 — 명령줄 껍데기(T-25 4단계 · 본체 = `src/coupang_analytics/statement_jobs_seldoc.py` · 배치 D-399 와 같은 코드).
계약 1건 = 파일 1개·시트 1장 · 계산 없음: 숫자 = 위탁정산서 결과 파일(D-225 ①).

1) 계약이 여럿인 계정(서달원 등)만 — 계약별 상품군 위탁정산서(D-155 · 위탁정산서와 같은 규칙 · 범위만 상품군):
    python tools/settlement_seldoc.py groups --accounts a,b --out <상품군 정산서 폴더> --managed-output … --settle-dir … --stats …
        --basis YYYY-MM-DD [--inputs <위탁정산서 입력 폴더>] [--issued …] [--settle-only …] [--account-history …]
2) 셀독 정산서:
    python tools/settlement_seldoc.py make --statements <위탁정산서 결과 폴더> [--group-statements <상품군 정산서 폴더>]
        --out <출력 폴더> --basis YYYY-MM-DD --issued YYYY-MM-DD [--accounts a,b] [--isolate]
3) 셀독 입력 1회 준비(복사만 · 원본 그대로 · 덮어쓰기 없음):
    python tools/settlement_seldoc.py inputs --from <판정표·대응표가 있는 폴더> --db <계약서 분석 DB> [--to <셀독 입력 폴더>]

셀독 입력 폴더 기본 = output\\정산서\\입력_셀독\\ (사업자_대응표.csv · 셀독_계약상품군_판정.json · 계약 DB 사본 계약서_정밀분석_DB*.xlsx 1개)
· --seldoc-inputs·--db = 덮어쓰기용 · --accounts 없음 = 판정표·이름 후보가 있는 계정 전부.
손 실행 기본 = 막는 사유(판정 없음·DB 에 없는 계약·위탁정산서/상품군 정산서 없음 등)가 하나라도 있으면 ❌ 시작 전 중단(파일 안 만듦) ·
--isolate = 배치처럼 그 계약만 건너뛰고 나머지를 만듦(건너뛴 사유 출력).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coupang_analytics import settlement_seldoc_source as SS  # noqa: E402
from coupang_analytics import statement_jobs_seldoc as JOB  # noqa: E402


def _common(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--db", type=Path, help="계약서 분석 DB(기본 = 셀독 입력 폴더의 사본)")
    ap.add_argument("--seldoc-inputs", type=Path, help=f"셀독 입력 폴더(기본 = {JOB.default_inputs(ROOT)})")
    ap.add_argument("--accounts", default="", help="쉼표로 나눈 계정ID(없으면 판정표·이름 후보가 있는 계정 전부)")
    ap.add_argument("--basis", required=True)
    ap.add_argument("--issued", default=f"{date.today():%Y-%m-%d}")
    ap.add_argument("--isolate", action="store_true", help="막힌 계약만 건너뛰고 나머지를 만듦(배치와 같음)")


def _opts(a, **kw) -> dict:
    return {"root": ROOT, "seldoc_inputs": a.seldoc_inputs, "db": a.db, "basis": a.basis, "issued": a.issued,
            "accounts": [x.strip() for x in a.accounts.split(",") if x.strip()] or None, "strict": not a.isolate, **kw}


def _report(res: dict) -> int:
    for s in res["skipped"]:
        print(f"  건너뜀 {s['id']} — {s['reason']}")
    if res["abort"]:
        print(f"❌ {res['abort']}")
        return 1
    return 0


def make(argv: list) -> int:
    ap = argparse.ArgumentParser(prog="settlement_seldoc.py make")
    _common(ap)
    ap.add_argument("--statements", required=True, type=Path)
    ap.add_argument("--group-statements", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    return _report(JOB.run_job(_opts(a, statements=a.statements, group_statements=a.group_statements, out=a.out, steps=("make",))))


def groups(argv: list) -> int:
    ap = argparse.ArgumentParser(prog="settlement_seldoc.py groups")
    _common(ap)
    ap.add_argument("--out", required=True, type=Path, help="상품군 정산서 폴더")
    ap.add_argument("--managed-output", required=True, type=Path)
    ap.add_argument("--settle-dir", required=True, type=Path)
    ap.add_argument("--stats", required=True, type=Path)
    ap.add_argument("--inputs", type=Path, default=ROOT / "output" / "정산서" / "입력", help="위탁정산서 입력 폴더")
    for k in ("--settle-only", "--supp", "--snap", "--account-history"):
        ap.add_argument(k, type=Path)
    ap.add_argument("--only", default="")
    a = ap.parse_args(argv)
    g = {k: getattr(a, k) for k in JOB.GROUP_KEYS if k != "only"}
    g["only"] = tuple(x.strip() for x in a.only.split(",") if x.strip())
    return _report(JOB.run_job(_opts(a, out=a.out, group_statements=a.out, groups=g, steps=("groups",))))


def inputs(argv: list) -> int:
    ap = argparse.ArgumentParser(prog="settlement_seldoc.py inputs")
    ap.add_argument("--from", dest="src", required=True, type=Path, help="판정표·사업자 대응표가 있는 폴더")
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--to", type=Path, default=JOB.default_inputs(ROOT))
    a = ap.parse_args(argv)
    for line in JOB.install_inputs(a.to, a.src, a.db):
        print(f"  {line}")
    print(f"셀독 입력 준비 끝 → {a.to}")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    argv = list(sys.argv[1:] if argv is None else argv)
    cmds = {"make": make, "groups": groups, "inputs": inputs}
    if not argv or argv[0] not in cmds:
        print("사용: settlement_seldoc.py make|groups|inputs …")
        return 2
    try:
        return cmds[argv[0]](argv[1:])
    except SS.SeldocInputError as exc:
        print(f"❌ {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
