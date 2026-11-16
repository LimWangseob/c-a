"""장부 DB 빌드 — 원천(운용 output 사본) → 새 SQLite. 묶음(part)마다 이관 모듈을 차례로 부른다(무거운 실행 하나씩).

- 같은 입력 → 같은 DB 내용(표 해시 · V1). 실행 기록(run_meta)만 시각이 다르다.
- 계정 표 = 원천에서 본 계정ID·표기·vendorId(정산현황 원문 link_key 앞부분)를 모은 것(표기 2개 계정 = J2 판정 후보).
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from . import ledger_load_account, ledger_load_cost, ledger_load_sales, ledger_load_settle, ledger_schema
from .ledger_src import Registry

PARTS = ("settle", "cost", "account", "sales")
_VENDOR_KEY = re.compile(r"^([A-Z]\d{8})-\d{4}-\d{2}-\d{2}")


def _accounts(con: sqlite3.Connection, exclude: frozenset[str]) -> None:
    seen: dict[str, set] = defaultdict(set)
    for acc, path in con.execute("SELECT account_id, path FROM src_file WHERE account_id IS NOT NULL"):
        for part in Path(path).parts:
            base = part.split("_", 1)[0].split(".", 1)[0]
            if base.endswith(f"-{acc}"):
                seen[acc].add(base)       # 계정 표기(이름-상호-계정ID) — 표기 2개 이상 = J2 후보
    for acc, label in con.execute("SELECT account_id, link_key FROM account_entry WHERE item='표기'"):
        seen[acc].add(label)
    vids: dict[str, set] = defaultdict(set)
    for acc, key in con.execute("SELECT DISTINCT account_id, link_key FROM account_entry WHERE item LIKE '원문 %'"):
        m = _VENDOR_KEY.match(key or "")
        if m:
            vids[acc].add(m.group(1))     # 정산현황 원문 link_key = vendorId-기간시작-기간끝 …
    rows = [(a, ",".join(sorted(vids.get(a, ()))), json.dumps(sorted(x for x in v if x), ensure_ascii=False), int(a in exclude),
             "제외 계정(실행 인자)" if a in exclude else "") for a, v in sorted(seen.items())]
    con.executemany("INSERT INTO account VALUES (?,?,?,?,?)", rows)


def build(output: Path, db: Path, exclude: frozenset[str], only: frozenset[str], parts: tuple[str, ...]) -> list[str]:
    output = Path(output)
    settle = output / "정산"
    if not settle.is_dir():
        raise FileNotFoundError(f"정산 폴더 없음: {settle}")
    con = ledger_schema.create(db)
    meta = {"input": str(output), "exclude": ",".join(sorted(exclude)), "only": ",".join(sorted(only)),
            "parts": ",".join(parts), "started": f"{datetime.now():%Y-%m-%d %H:%M:%S}"}
    con.executemany("INSERT INTO run_meta VALUES (?,?)", sorted(meta.items()))
    reg = Registry(con, output, exclude, only)
    if "settle" in parts:
        ledger_load_settle.load(con, reg, settle)
    if "cost" in parts:
        ledger_load_cost.load(con, reg, settle)
    if "account" in parts:
        ledger_load_account.load(con, reg, settle)
    if "sales" in parts:
        ledger_load_sales.load(con, reg, output)
    _accounts(con, exclude)
    con.execute("INSERT INTO run_meta VALUES ('finished', ?)", (f"{datetime.now():%Y-%m-%d %H:%M:%S}",))
    hashes = ledger_schema.all_hashes(con)
    con.executemany("INSERT INTO run_meta VALUES (?,?)", [(f"hash:{t}", h) for t, h in sorted(hashes.items())])
    con.commit()
    out = summary(con)
    con.close()
    return out


def summary(con: sqlite3.Connection) -> list[str]:
    lines = ["[원천 파일]"]
    for kind, status, n, rr, rl, rs in con.execute(
            "SELECT kind, status, COUNT(*), SUM(rows_read), SUM(rows_loaded), SUM(rows_skipped) FROM src_file "
            "GROUP BY kind, status ORDER BY kind, status"):
        lines.append(f"  {kind} · {status}: 파일 {n} · 읽은 줄 {rr or 0:,} · 넣은 줄 {rl or 0:,} · 뺀 줄 {rs or 0:,}")
    lines.append("[표]")
    for t in ledger_schema.TABLES:
        lines.append(f"  {t}: {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:,}")
    return lines
