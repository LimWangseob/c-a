"""위탁자 정산서(3차 형식 · 구글시트) 만들기 — 명령줄 입구(T-38). 숫자 = `settlement_consignor_month` · 그리기 = `settlement_consignor_gsheet` ·
고르기·검산·저장·시트 쓰기 본체 = `src/coupang_analytics/statement_jobs_consignor.py`(배치에서도 부름 · 이 파일은 인자만).

    python tools/settlement_consignor.py --out <출력 폴더> --managed-output <관리기준 output> --settle-dir <output/정산>
        --stats <정산집계.xlsx> --basis YYYY-MM-DD [--inputs <입력 폴더>] [--issued YYYY-MM-DD] [--settle-only <json>]
        [--accounts 계정ID,계정ID] [--month YYYY-MM] [--sheet <구글시트 주소>]

- 계정마다 기존 위탁정산서 계산(Account.run)을 한 번 돌려 판매 달마다 자료를 만든다(--month 를 주면 그 달만).
  자료 = `<out>/위탁자정산서/<계정ID>_<YYYYMM>.json` · 요약 = `<out>/위탁자정산서/_요약.json`.
- 검산 = 숫자 쪽(`failed_checks` · 1원 이상 차이) + 그리기 쪽(`check` · 합계 맞음). 하나라도 어긋나면 시트를 쓰지 않고 끝 코드 1.
  계정 하나가 예외를 내면 그 계정만 '못 만듦'으로 알리고 나머지는 계속 만든다(못 만듦이 있어도 시트를 쓰지 않고 끝 코드 1).
- --sheet = 검산이 모두 통과하고 판매 달이 하나(--month)일 때만 그 시트의 탭을 전부 지우고 다시 그린다(D-241 ⑥ 달마다 파일 1개).
  새 달 파일 만들기(소유자 OAuth · D-242 ④)는 아직 없음(T-43). 시트 주소는 인자로만 받음(설정 파일에 안 넣음 · 계획 2절).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coupang_analytics import settlement_consignor_month as CM  # noqa: E402
from coupang_analytics import settlement_ledger as SL  # noqa: E402
from coupang_analytics import settlement_statement_context as CTX  # noqa: E402
from coupang_analytics.statement_jobs_consignor import (  # noqa: E402,F401 — 본체 = src(exe 에서도 부름 · 시험이 이 이름으로 부름)
    OUT_DIR, account_months, build_all, pick_accounts, save, statement_failures, summary_row, write_sheet)


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
    ap.add_argument("--accounts", default="", help="쉼표로 나눈 계정ID(비면 정산집계의 전 계정)")
    ap.add_argument("--month", default="", help="판매 달 YYYY-MM(비면 계정의 모든 판매 달)")
    ap.add_argument("--sheet", default="", help="다시 그릴 구글시트 주소·ID(검산 통과 · --month 하나일 때만)")
    a = ap.parse_args(argv)
    date.fromisoformat(a.basis)
    date.fromisoformat(a.issued)
    if a.month:
        date.fromisoformat(f"{a.month}-01")
        if SL.sold_2025(a.month):
            ap.error(f"--month {a.month} = 2025년 판매 달 — 정산에 넣지 않음(D-328 · {SL.SALE_FROM} 부터)")
    if a.sheet and not a.month:
        ap.error("--sheet 는 --month 와 함께(판매 달마다 시트 파일 1개 · D-241 ⑥)")
    return a


def statement_args(a: argparse.Namespace) -> CTX.StatementArgs:
    return CTX.StatementArgs(out=a.out, managed_output=a.managed_output, settle_dir=a.settle_dir, stats=a.stats, basis=a.basis,
                             inputs=a.inputs, issued=a.issued, settle_only=a.settle_only, supp=a.supp, snap=a.snap)


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
    results, failed = build_all(ctx, accts, a.month, CM.load_judge(inputs=a.inputs))
    folder = save(results, a.out)
    bad = [r for r in results if r["failures"]]
    print(f"자료 {len(results)}개 → {folder} · 검산 실패 {len(bad)}개" + (f" · 못 만듦 {len(failed)}건" if failed else ""))
    if bad or failed:
        print("❌ 검산 실패·못 만든 계정이 있어 시트를 쓰지 않음")
        return 1
    if a.sheet:
        write_sheet(a.sheet, results, a.issued)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
