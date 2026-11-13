"""정산 대상 상품 출처 AI 판정 — 준비(prepare) · 반영(apply) (D-230 · D-231 · 모듈 = `coupang_analytics.settlement_scope_judge`).

  python tools/settlement_scope_judge.py prepare --managed-output <output 폴더> --inputs <입력 폴더> --out <요청 폴더>
      --old-ledger <옛 대장.xlsx> [...] --history <원장 상품이력 사본.json> --contract-db <계약 DB v4.xlsx> [--accounts a,b,c]
  → <요청 폴더>/프롬프트.md + 요청_<계정ID>.json(계정마다) — AI 가 프롬프트대로 답_<계정ID>.json 을 쓴다.
  python tools/settlement_scope_judge.py apply --requests <요청 폴더> --answers <답 폴더> --out <입력 폴더>/관리상품_출처판정.json
  → 답 검사(판정대상 ID·출처·판정·근거·원문 그대로) 통과한 계정만 판정표에 씀(같은 계정 옛 항목은 바꿈 · 다른 계정은 그대로).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coupang_analytics import sales_history, sales_summary  # noqa: E402
from coupang_analytics import settlement_scope_judge as J  # noqa: E402
from coupang_analytics import settlement_statement_scope as SCOPE  # noqa: E402


def _people(inputs: Path) -> dict:
    with (inputs / "사업자_대응표.csv").open(encoding="utf-8-sig") as f:
        return {r["계정ID"]: (r["사업자"], r["대표자"]) for r in csv.DictReader(f) if r.get("계정ID")}


def prepare(a) -> int:
    people = _people(a.inputs)
    want = [x.strip() for x in a.accounts.split(",")] if a.accounts else sorted(people)
    ledger = SCOPE.ledger_vids(a.managed_output)
    stores = (sales_history.load_daily(a.managed_output), sales_history.load_periods(a.managed_output))
    listings = sales_summary.managed_listings(stores, ledger)
    inv = SCOPE.inventory(a.managed_output)
    old = J.old_ledger_rows(a.old_ledger, set(people))
    hist = J.history_rows(json.loads(a.history.read_text(encoding="utf-8")))
    cons = J.contract_rows(a.contract_db, {k: people[k] for k in want if k in people})
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "프롬프트.md").write_text(J.PROMPT, encoding="utf-8")
    for aid in want:
        vids, names, vname = ledger.get(aid) or set(), listings.get(aid) or set(), SCOPE.vid_names(stores, aid)

        def is_mv(v: str, vids=vids, names=names, vname=vname) -> bool:
            return v in vids or vname.get(v) in names
        tg = J.targets(aid, inv, SCOPE.sales_groups(stores[1].get(aid) or {}), is_mv, vname)
        pk = J.packet(aid, people.get(aid, ("", "")), tg, old.get(aid, []), hist.get(aid, []), cons.get(aid, []))
        (a.out / f"요청_{aid}.json").write_text(json.dumps(pk, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{aid}: 판정대상 {len(tg)} · 옛대장 {len(pk['근거자료']['① 옛대장'])} · 이력원장 {len(pk['근거자료']['② 이력원장'])}"
              f" · 계약서 {len(pk['근거자료']['③ 계약서'])}")
    return 0


def apply(a) -> int:
    book = json.loads(a.out.read_text(encoding="utf-8")) if a.out.is_file() else {"계정": {}}
    bad = 0
    for req in sorted(a.requests.glob("요청_*.json")):
        pk = json.loads(req.read_text(encoding="utf-8"))
        aid = pk["계정"]["계정ID"]
        ans_p = a.answers / f"답_{aid}.json"
        if not ans_p.is_file():
            print(f"❌ {aid}: 답 파일 없음 {ans_p}")
            bad += 1
            continue
        got, errs = J.check_answer(pk, json.loads(ans_p.read_text(encoding="utf-8")))
        if errs:
            print(f"❌ {aid}: 답 검사 실패 {len(errs)}건 — 판정표에 안 넣음\n   " + "\n   ".join(errs))
            bad += 1
            continue
        book["계정"][aid] = got
        print(f"✅ {aid}: {len(got)}건(관리 {sum(e['판정'] == '관리' for e in got.values())})")
    book["판정자"] = "AI(프롬프트 = settlement_scope_judge.PROMPT) · 검사 = check_answer"
    a.out.write_text(json.dumps(book, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(description="정산 대상 상품 출처 AI 판정 준비·반영")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--managed-output", required=True, type=Path)
    p.add_argument("--inputs", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--old-ledger", nargs="+", required=True, type=Path)
    p.add_argument("--history", required=True, type=Path)
    p.add_argument("--contract-db", required=True, type=Path)
    p.add_argument("--accounts", default="")
    q = sub.add_parser("apply")
    q.add_argument("--requests", required=True, type=Path)
    q.add_argument("--answers", required=True, type=Path)
    q.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    return prepare(a) if a.cmd == "prepare" else apply(a)


if __name__ == "__main__":
    raise SystemExit(main())
