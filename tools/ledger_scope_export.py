r"""장부 DB 시험 4단계 입력 — 기존 위탁정산서 코드(import 만 · 수정 없음 D-233)로 계정마다 관리 상품 범위와 현행 코드 정산서 숫자를 뽑는다.

- 관리 범위: `Account._scope()` 의 is_mv(옵션 → 관리?) 를 장부 DB 에 나오는 옵션ID 전부에 적용 · 관리 시작 달(start) · 계약일(cdate) ·
  못 정한 상품 수(scope_check) — 판정표 = 입력 폴더(이 시험 = 안재영 정산서 입력본 · 소유자 11-16 답).
- 현행 코드 숫자: `Account.run()` + `shown()` → 1쪽 큰 숫자·공제 항목·달별 판매/정산(같은 자료로 장부 방식과 비교하는 기준).
- 네트워크 없음(구글 시트 접근 막음) · 개인 성명은 결과에 쓰지 않음(계정ID 만).
실행: python -X utf8 -W ignore tools/ledger_scope_export.py --db <장부.sqlite> --managed-output <output> --stats <정산집계.xlsx>
      --inputs <입력 폴더> --settle-only <json> --account-history <json> --basis 2026-11-15 --out <결과.json> [--exclude Difpick]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coupang_analytics import gsheet_api  # noqa: E402


class _NoNet:
    def __init__(self, *a, **k):
        raise RuntimeError("네트워크 금지 — 구글 시트 접근 시도")


gsheet_api.GSheetClient = _NoNet  # type: ignore[misc,assignment]

from coupang_analytics import settlement_statement_context as CTX  # noqa: E402
from coupang_analytics import settlement_statement_source as SRC  # noqa: E402
from coupang_analytics.settlement_statement_deduct import Account  # noqa: E402
from coupang_analytics.settlement_statement_sheets import shown  # noqa: E402

DB_OPTION_SQL = """
SELECT account_id, option_id FROM order_line WHERE option_id <> ''
UNION SELECT account_id, option_id FROM product_cost WHERE option_id <> ''
UNION SELECT account_id, option_id FROM sale_daily WHERE option_id <> ''
UNION SELECT account_id, option_id FROM option_attr WHERE option_id <> ''"""


def plain(x):
    """json 으로 쓸 수 있는 기본형(집합 → 정렬 목록 · 튜플 → 목록 · 숫자 키 → 글)."""
    if isinstance(x, dict):
        return {str(k): plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [plain(v) for v in x]
    if isinstance(x, (set, frozenset)):
        return sorted(str(v) for v in x)
    if isinstance(x, float) and x == int(x):
        return int(x)
    return x if isinstance(x, (str, int, float, bool)) or x is None else str(x)


def db_options(db: Path) -> dict:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    out: dict = {}
    for aid, opt in con.execute(DB_OPTION_SQL):
        out.setdefault(aid, set()).add(str(opt))
    con.close()
    return out


def one(ctx, acct: str, opts: set) -> dict:
    a = Account(ctx, acct)
    res = a.run()
    v = shown(res)
    return {
        "scope": a.sc, "start": a.start, "cdate": a.cdate, "scope_check": len(a.scope_check),
        "managed": sorted(o for o in opts if a.is_mv(o)), "options": len(opts),
        "shown": plain({k: v[k] for k in ("gross", "refund", "ship", "sales", "c_sales", "c_settle", "u_sales", "u_settle",
                                          "settle", "ded", "cost", "pay", "bank", "fast", "bank_col")}),
        "Dm": plain(res["Dm"]), "mmon": plain(res["mmon"]), "tm": plain(res["tm"]), "ok": bool(res["ok"]), "why": plain(res["why"]),
    }


def main(argv: list | None = None) -> int:
    p = argparse.ArgumentParser()
    for k in ("--db", "--managed-output", "--stats", "--inputs", "--settle-only", "--account-history", "--basis", "--out"):
        p.add_argument(k, required=True)
    p.add_argument("--exclude", action="append", default=[])
    a = p.parse_args(argv)
    out_dir = Path(a.out).parent
    args = CTX.StatementArgs(out=out_dir / "_ctx_out", managed_output=Path(a.managed_output), settle_dir=Path(a.managed_output) / "정산",
                             stats=Path(a.stats), basis=a.basis, inputs=Path(a.inputs), issued=a.basis,
                             settle_only=Path(a.settle_only), account_history=Path(a.account_history))
    t0 = time.time()
    opts = db_options(Path(a.db))
    ctx = CTX.load(args)
    print(f"ctx 준비 · 계정 {len(ctx.accts)} · {time.time() - t0:.0f}초", flush=True)
    res: dict = {"args": {k: str(v) for k, v in vars(a).items()}, "accounts": {}}
    for acct in ctx.accts:
        aid = SRC.aid_of(acct)
        if aid in a.exclude:
            res["accounts"][aid] = {"status": "제외(실행 인자)"}
            continue
        try:
            res["accounts"][aid] = {"status": "ok", **one(ctx, acct, opts.get(aid, set()))}
        except Exception as exc:  # noqa: BLE001 — 계정마다 오류를 결과에 남김(조용히 버리지 않음)
            res["accounts"][aid] = {"status": f"오류: {exc.__class__.__name__}: {exc}"}
        print(aid, res["accounts"][aid]["status"][:60], f"{time.time() - t0:.0f}초", flush=True)
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("저장", a.out, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
