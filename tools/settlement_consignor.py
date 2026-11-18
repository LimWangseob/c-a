"""위탁자 정산서(3차 형식 · 구글시트) 만들기 — 명령줄 입구(T-38). 숫자 = `settlement_consignor_month` · 그리기 = `settlement_consignor_gsheet`.

    python tools/settlement_consignor.py --out <출력 폴더> --managed-output <관리기준 output> --settle-dir <output/정산>
        --stats <정산집계.xlsx> --basis YYYY-MM-DD [--inputs <입력 폴더>] [--issued YYYY-MM-DD] [--settle-only <json>]
        [--account-history <json>] [--accounts 계정ID,계정ID] [--month YYYY-MM] [--sheet <구글시트 주소>]

- 계정마다 기존 위탁정산서 계산(Account.run)을 한 번 돌려 판매 달마다 자료를 만든다(--month 를 주면 그 달만).
  자료 = `<out>/위탁자정산서/<계정ID>_<YYYYMM>.json` · 요약 = `<out>/위탁자정산서/_요약.json`.
- 검산 = 숫자 쪽(`failed_checks` · 1원 이상 차이) + 그리기 쪽(`check` · 합계 맞음). 하나라도 어긋나면 시트를 쓰지 않고 끝 코드 1.
- --sheet = 검산이 모두 통과하고 판매 달이 하나(--month)일 때만 그 시트의 탭을 전부 지우고 다시 그린다(D-241 ⑥ 달마다 파일 1개).
  새 달 파일 만들기(소유자 OAuth · D-242 ④)는 아직 없음(T-43). 시트 주소는 인자로만 받음(설정 파일에 안 넣음 · 계획 2절).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coupang_analytics import settlement_consignor_gsheet as GS  # noqa: E402
from coupang_analytics import settlement_consignor_month as CM  # noqa: E402
from coupang_analytics import settlement_statement_context as CTX  # noqa: E402
from coupang_analytics import settlement_statement_source as SRC  # noqa: E402

OUT_DIR = "위탁자정산서"


def _args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="위탁자 정산서(3차 형식 · 구글시트) 만들기")
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
    ap.add_argument("--account-history", type=Path)
    ap.add_argument("--accounts", default="", help="쉼표로 나눈 계정ID(비면 정산집계의 전 계정)")
    ap.add_argument("--month", default="", help="판매 달 YYYY-MM(비면 계정의 모든 판매 달)")
    ap.add_argument("--sheet", default="", help="다시 그릴 구글시트 주소·ID(검산 통과 · --month 하나일 때만)")
    a = ap.parse_args(argv)
    date.fromisoformat(a.basis)
    date.fromisoformat(a.issued)
    if a.month:
        date.fromisoformat(f"{a.month}-01")
    if a.sheet and not a.month:
        ap.error("--sheet 는 --month 와 함께(판매 달마다 시트 파일 1개 · D-241 ⑥)")
    return a


def statement_args(a: argparse.Namespace) -> CTX.StatementArgs:
    return CTX.StatementArgs(out=a.out, managed_output=a.managed_output, settle_dir=a.settle_dir, stats=a.stats, basis=a.basis,
                             inputs=a.inputs, issued=a.issued, settle_only=a.settle_only, supp=a.supp, snap=a.snap,
                             account_history=a.account_history)


def pick_accounts(accts: list[str], wanted: list[str]) -> list[str]:
    """정산집계 계정 이름 목록에서 계정ID 로 고름(비면 전부) · 못 찾은 ID 가 있으면 중단(조용히 빼지 않음)."""
    if not wanted:
        return list(accts)
    by_id = {SRC.aid_of(a): a for a in accts}
    missing = [w for w in wanted if w not in by_id]
    if missing:
        raise ValueError(f"정산집계에 없는 계정ID: {missing}")
    return [by_id[w] for w in wanted]


def statement_failures(data: dict) -> list[str]:
    """숫자 쪽 검산(1원 이상 차이) + 그리기 쪽 검산(합계) — 빈 목록 = 통과."""
    out = [f"{c['검사']} 차이 {c.get('차이', c.get('검산(실제 = 정산금액 − 공제 − 판매 조정)'))}" for c in CM.failed_checks(data)]
    return out + GS.check(data)


def account_months(src: dict, month: str) -> list[str]:
    months = CM.sale_months(src)
    return [month] if month else months


def build_all(ctx, accts: list[str], month: str, judge: CM.ConsignorJudge, log=print) -> list[dict]:
    """계정 × 판매 달 → [{account, month, data, failures}] (계정마다 기존 계산 1번)."""
    out = []
    for acct in accts:
        src = CM.account_source(ctx, acct)
        for m in account_months(src, month):
            data = CM.build_month(None, src, m, judge)
            fails = statement_failures(data)
            out.append({"account": src["aid"], "month": m, "data": data, "failures": fails})
            log(f"{'✅' if not fails else '❌'} {src['aid']} {m} 정산 {data['settle_amount']:,} · 확정 전 {data['pending_total']:,}"
                + (f" · 검산 실패 {len(fails)}" if fails else ""))
    return out


def summary_row(r: dict) -> dict:
    d = r["data"]
    return {"계정": r["account"], "달": r["month"], "상태": d["status"], "판매 금액": d["lines"][0]["amount"],
            "상품 정산액": d["product_subtotal"], "9 반영": d["common"]["total_applied"],
            "10 별도": sum(x["amount"] for x in d["separate"]), "이번 정산 금액": d["settle_amount"],
            "확정 전": d["pending_total"], "검산 실패": r["failures"]}


def save(results: list[dict], out: Path) -> Path:
    folder = out / OUT_DIR
    folder.mkdir(parents=True, exist_ok=True)
    for r in results:
        p = folder / f"{r['account']}_{r['month'].replace('-', '')}.json"
        p.write_text(json.dumps(r["data"], ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (folder / "_요약.json").write_text(json.dumps([summary_row(r) for r in results], ensure_ascii=False, indent=1, default=str),
                                     encoding="utf-8")
    return folder


def write_sheet(sheet: str, results: list[dict], issued: str, log=print) -> None:
    from coupang_analytics.gsheet_api import GSheetClient   # 시트를 쓸 때만(오프라인 실행은 구글 모듈 안 읽음)
    plan = GS.write_statement(GSheetClient(sheet, on_log=log), [r["data"] for r in results], issued, log=log)
    log(f"✅ 시트 반영 — 탭 {len(plan.tabs)}개")


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    a = _args(argv)
    try:
        ctx = CTX.load(statement_args(a))
    except FileNotFoundError as exc:
        print(f"❌ 시작 전 중단 — {exc}")
        return 1
    accts = pick_accounts(ctx.accts, [x.strip() for x in a.accounts.split(",") if x.strip()])
    results = build_all(ctx, accts, a.month, CM.load_judge(inputs=a.inputs))
    folder = save(results, a.out)
    bad = [r for r in results if r["failures"]]
    print(f"자료 {len(results)}개 → {folder} · 검산 실패 {len(bad)}개")
    if bad:
        print("❌ 검산 실패가 있어 시트를 쓰지 않음")
        return 1
    if a.sheet:
        write_sheet(a.sheet, results, a.issued)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
