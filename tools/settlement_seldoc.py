"""셀독 정산서 만들기 — 명령줄 입구(T-25 4단계 · 계약 1건 = 파일 1개·시트 1장). 계산 없음: 숫자 = 위탁정산서 결과 파일(D-225 ①).

1) 계약이 여럿인 계정(서달원 등)만 — 계약별 상품군 위탁정산서(D-155 · 위탁정산서와 같은 규칙 · 범위만 상품군):
    python tools/settlement_seldoc.py groups --db <계약서 분석 DB> --seldoc-inputs <셀독 입력 폴더> --accounts a,b
        --out <상품군 정산서 폴더> --managed-output … --settle-dir … --stats … --basis YYYY-MM-DD --inputs <위탁정산서 입력 폴더>
        [--issued …] [--settle-only …] [--account-history …]          (뒤 인자 = tools/settlement_statements.py 와 같음)
2) 셀독 정산서:
    python tools/settlement_seldoc.py make --statements <위탁정산서 결과 폴더> [--group-statements <상품군 정산서 폴더>]
        --db <계약서 분석 DB> --seldoc-inputs <셀독 입력 폴더> --out <출력 폴더> --basis YYYY-MM-DD --issued YYYY-MM-DD --accounts a,b

셀독 입력 폴더 고정 이름 = 사업자_대응표.csv · 셀독_계약상품군_판정.json(계약자↔계정·상품↔계약 AI 판정 · 근거 원문).
판정표 없음·판정 없는 대상 계약·DB 에 없는 계약·위탁정산서/상품군 정산서 없음 = ❌ 시작 전 중단(파일 안 만듦).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from coupang_analytics import settlement_seldoc_groups as G  # noqa: E402
from coupang_analytics import settlement_seldoc_sheet as SH  # noqa: E402
from coupang_analytics import settlement_seldoc_source as SS  # noqa: E402
from coupang_analytics.settlement_statement_book import safe_name  # noqa: E402


def _common(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--seldoc-inputs", required=True, type=Path)
    ap.add_argument("--accounts", required=True, help="쉼표로 나눈 계정ID")


def _jobs(a) -> tuple[list, dict]:
    judge = SS.load_judge(a.seldoc_inputs)
    people = SS.load_people(a.seldoc_inputs)
    aids = [x.strip() for x in a.accounts.split(",") if x.strip()]
    return SS.plan(people, SS.load_contracts(a.db), judge, aids), judge


def _statement(a, job) -> Path:
    if job.split:
        if a.group_statements is None:
            raise SS.SeldocInputError(f"시작 전 중단 — {job.aid} 계약이 {job.contract.doc_id} 등 여럿 — --group-statements 필요")
        p = G.group_path(a.group_statements, job.aid, job.contract.doc_id)
        if not p.is_file():
            raise SS.SeldocInputError(f"시작 전 중단 — {job.aid} 계약 {job.contract.doc_id} 상품군 정산서 없음 {p}")
        return p
    found = sorted(a.statements.glob(f"정산서_*_{job.aid}_관리상품.xlsx"))
    if len(found) != 1:
        raise SS.SeldocInputError(f"시작 전 중단 — {job.aid} 위탁정산서 {len(found)}개(1개여야 함) · {a.statements}")
    return found[0]


def _perf(a, job):
    pf = SS.read_statement(_statement(a, job))
    if pf.aid != job.aid:
        raise SS.SeldocInputError(f"시작 전 중단 — {job.aid} 위탁정산서의 쿠팡 계정이 {pf.aid}")
    if job.split and any(x for _, x in pf.extras):
        raise SS.SeldocInputError(f"시작 전 중단 — {job.aid} 쿠팡 별도 보상(상품 구분 없음)은 계약별로 나눌 수 없음")
    return pf


def _name(job, basis: str, stamp: str) -> str:
    c = job.contract
    first = safe_name(c.items[0][0])[:14] if c.items else "품목없음"
    tag = f"{c.signed[2:].replace('-', '')}_{first}" + (f"외{len(c.items) - 1}" if len(c.items) > 1 else "")
    who = safe_name(job.people[1] or job.people[0])
    return f"셀독정산서_{who}_{tag}_{basis.replace('-', '')}기준_{stamp}.xlsx"


def make(argv: list) -> int:
    ap = argparse.ArgumentParser(prog="settlement_seldoc.py make")
    _common(ap)
    ap.add_argument("--statements", required=True, type=Path)
    ap.add_argument("--group-statements", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--basis", required=True)
    ap.add_argument("--issued", default=f"{date.today():%Y-%m-%d}")
    a = ap.parse_args(argv)
    date.fromisoformat(a.basis)
    date.fromisoformat(a.issued)
    jobs, _judge = _jobs(a)
    perfs = [_perf(a, j) for j in jobs]                        # 모두 읽고 맞는지 본 뒤에만 파일을 씀
    stamp = datetime.now().strftime("%y%m%d_%H%M%S")
    for j, pf in zip(jobs, perfs):
        p = SH.write(a.out / _name(j, a.basis, stamp), j.contract, pf, a.basis, a.issued)
        c = j.contract
        target = SS.goal_total(c.amount, c.profit)
        print(f"{j.aid} {c.doc_id[:8]} {c.signed} 목표 {target:,} · 실적 {pf.result:,} · 도달율 {SS.reach(pf.result, c.amount, c.profit):.1%}"
              f" · 남은 {max(target - pf.result, 0):,} → {p}")
    print(f"셀독 정산서 {len(jobs)}개 → {a.out}")
    return 0


def groups(argv: list) -> int:
    import settlement_statements as ST
    ap = argparse.ArgumentParser(prog="settlement_seldoc.py groups")
    _common(ap)
    a, rest = ap.parse_known_args(argv)
    args = ST._args(rest)
    jobs, judge = _jobs(a)
    for aid, doc, p, g in G.run(args, jobs, judge, args.out):
        print(f"  {aid} {doc[:8]} G {g:,} → {p}")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ("make", "groups"):
        print("사용: settlement_seldoc.py make|groups …")
        return 2
    try:
        return (make if argv[0] == "make" else groups)(argv[1:])
    except (SS.SeldocInputError, FileNotFoundError, FileExistsError) as exc:
        msg = str(exc)
        print(f"❌ {msg}" if "시작 전 중단" in msg else f"❌ 시작 전 중단 — {msg}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
