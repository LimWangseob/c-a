"""장부 DB(시험본) 표 정의 — 쿠팡 정산 자료를 쿠팡이 주는 단위 그대로 SQLite 에 옮긴다(D-263).

- 상품 내역 = 옵션(상품) 단위 값: ① sale_daily · ② order_line(+order_pay) · ③ product_cost.
- 계정 내역 = 계정 단위 값: ④ pay_round · account_entry(역할 '지급 구성' / '대조용').
- ⑤ pending_est = 정산 예정분 상품별 예상 → 실제 · ⑥ option_attr = 옵션 짝(KEY 연결용·금액 없음).
- 모든 자료 줄에 원천 위치(file_id + sheet + src_row)를 둔다. 판정(judgment)은 Claude 판정표를 옮긴 것.
- 계획 = output/_시험_261116_장부DB/계획.md · KEY = output/_분석_261116_예정분나누기/장부_KEY_그룹_분석.md 3절.
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

SCHEMA_VERSION = "1"

TABLES: dict[str, str] = {
    "run_meta": """run_meta(k TEXT PRIMARY KEY, v TEXT NOT NULL)""",
    "src_file": """src_file(
        file_id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE, kind TEXT NOT NULL, account_id TEXT,
        size INTEGER NOT NULL, sha256 TEXT NOT NULL, status TEXT NOT NULL,      -- 반영 · 생략 · 제외 · 오류
        rows_read INTEGER NOT NULL DEFAULT 0, rows_loaded INTEGER NOT NULL DEFAULT 0,
        rows_skipped INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '')""",
    "src_skip": """src_skip(
        file_id INTEGER NOT NULL, reason TEXT NOT NULL, n INTEGER NOT NULL,
        PRIMARY KEY(file_id, reason))""",
    "account": """account(
        account_id TEXT PRIMARY KEY, vendor_ids TEXT NOT NULL DEFAULT '', names TEXT NOT NULL DEFAULT '',
        excluded INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '')""",
    "option_attr": """option_attr(
        account_id TEXT NOT NULL, option_id TEXT NOT NULL, sale_type TEXT NOT NULL DEFAULT '',
        inventory_id TEXT NOT NULL DEFAULT '', product_id TEXT NOT NULL DEFAULT '', item_id TEXT NOT NULL DEFAULT '',
        sku_id TEXT NOT NULL DEFAULT '', src_kind TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
        PRIMARY KEY(account_id, option_id, sale_type, inventory_id, product_id, item_id, sku_id, src_kind))""",
    "sale_daily": """sale_daily(
        account_id TEXT NOT NULL, sale_type TEXT NOT NULL, option_id TEXT NOT NULL, pay_date TEXT NOT NULL,
        qty INTEGER NOT NULL, amount INTEGER NOT NULL, orders INTEGER NOT NULL, inventory_id TEXT NOT NULL DEFAULT '',
        collected TEXT NOT NULL DEFAULT '', file_id INTEGER NOT NULL, src_pos TEXT NOT NULL,
        PRIMARY KEY(account_id, sale_type, option_id, pay_date))""",
    "order_line": """order_line(
        line_id INTEGER PRIMARY KEY, account_id TEXT NOT NULL, sale_type TEXT NOT NULL, order_no TEXT NOT NULL,
        item_key TEXT NOT NULL, txn_type TEXT NOT NULL, seq INTEGER NOT NULL,   -- seq = 같은 KEY·같은 날 n번째 줄
        option_id TEXT NOT NULL DEFAULT '', product_id TEXT NOT NULL DEFAULT '', inventory_id TEXT NOT NULL DEFAULT '',
        recognized TEXT NOT NULL DEFAULT '', paid_date TEXT NOT NULL DEFAULT '', cycle_end TEXT NOT NULL DEFAULT '',
        qty INTEGER NOT NULL DEFAULT 0, gross INTEGER NOT NULL DEFAULT 0, sales INTEGER NOT NULL DEFAULT 0,
        coupon INTEGER NOT NULL DEFAULT 0, fee INTEGER NOT NULL DEFAULT 0, settle INTEGER NOT NULL DEFAULT 0,
        src TEXT NOT NULL,                                                       -- 주문상세 · 판매수수료 · 주문별매출 · 라이브정산
        file_id INTEGER NOT NULL, sheet TEXT NOT NULL DEFAULT '', src_row INTEGER NOT NULL,
        UNIQUE(account_id, sale_type, order_no, item_key, txn_type, recognized, seq, src))""",
    "order_pay": """order_pay(
        line_id INTEGER NOT NULL, file_id INTEGER NOT NULL, src_row INTEGER NOT NULL, stage TEXT NOT NULL,
        settle_date TEXT NOT NULL, period_start TEXT NOT NULL, period_end TEXT NOT NULL,
        PRIMARY KEY(file_id, src_row))""",
    "product_cost": """product_cost(
        cost_id INTEGER PRIMARY KEY, account_id TEXT NOT NULL, kind TEXT NOT NULL, nat_key TEXT NOT NULL,
        option_id TEXT NOT NULL DEFAULT '', inventory_id TEXT NOT NULL DEFAULT '', order_no TEXT NOT NULL DEFAULT '',
        txn_type TEXT NOT NULL DEFAULT '', occur_date TEXT NOT NULL DEFAULT '', cycle_end TEXT NOT NULL DEFAULT '',
        settle_type TEXT NOT NULL DEFAULT '', amount INTEGER NOT NULL, sign INTEGER NOT NULL,   -- sign −1 공제 · +1 받는 돈
        file_stage TEXT NOT NULL DEFAULT '', settle_date TEXT NOT NULL DEFAULT '',
        file_id INTEGER NOT NULL, sheet TEXT NOT NULL, src_row INTEGER NOT NULL,
        UNIQUE(file_id, sheet, src_row))""",
    "pay_round": """pay_round(
        round_id INTEGER PRIMARY KEY, account_id TEXT NOT NULL, sale_type TEXT NOT NULL, round_key TEXT NOT NULL,
        settle_date TEXT NOT NULL, period_start TEXT NOT NULL, period_end TEXT NOT NULL, ratio REAL NOT NULL,
        status TEXT NOT NULL DEFAULT '', release INTEGER NOT NULL DEFAULT 0,       -- release 1 = 윙 보류 해제 회차
        target INTEGER, payable INTEGER, deduction INTEGER, final INTEGER, pending INTEGER,
        file_id INTEGER NOT NULL, src_pos TEXT NOT NULL,
        UNIQUE(account_id, sale_type, round_key))""",
    "account_entry": """account_entry(
        entry_id INTEGER PRIMARY KEY, account_id TEXT NOT NULL, sale_type TEXT NOT NULL, round_key TEXT NOT NULL,
        item TEXT NOT NULL, role TEXT NOT NULL,                                    -- 지급 구성 · 대조용
        amount INTEGER NOT NULL, link_key TEXT NOT NULL DEFAULT '', occur_date TEXT NOT NULL DEFAULT '',
        file_id INTEGER NOT NULL, src_pos TEXT NOT NULL,
        UNIQUE(file_id, src_pos, item))""",
    "pending_est": """pending_est(
        account_id TEXT NOT NULL, basis TEXT NOT NULL, sale_type TEXT NOT NULL, round_key TEXT NOT NULL,
        option_id TEXT NOT NULL, method TEXT NOT NULL, est INTEGER NOT NULL, actual INTEGER, note TEXT NOT NULL DEFAULT '',
        PRIMARY KEY(account_id, basis, sale_type, round_key, option_id))""",
    "judgment": """judgment(
        kind TEXT NOT NULL, subject TEXT NOT NULL, verdict TEXT NOT NULL, reason TEXT NOT NULL,
        quote TEXT NOT NULL DEFAULT '', judge TEXT NOT NULL, table_file TEXT NOT NULL,
        PRIMARY KEY(kind, subject))""",
    "check_result": """check_result(
        check_name TEXT NOT NULL, account_id TEXT NOT NULL, subject TEXT NOT NULL,
        expected INTEGER, actual INTEGER, diff INTEGER, bucket TEXT NOT NULL, cause TEXT NOT NULL DEFAULT '',
        PRIMARY KEY(check_name, account_id, subject))""",
}

# 표마다 내용 해시를 낼 때의 정렬 순서(같은 자료 → 같은 해시 · V1).
ORDER_BY: dict[str, str] = {
    "src_file": "path", "src_skip": "file_id, reason", "account": "account_id",
    "option_attr": "account_id, option_id, sale_type, inventory_id, product_id, item_id, sku_id, src_kind",
    "sale_daily": "account_id, sale_type, option_id, pay_date",
    "order_line": "account_id, sale_type, order_no, item_key, txn_type, recognized, seq, src",
    "order_pay": "file_id, src_row", "product_cost": "file_id, sheet, src_row",
    "pay_round": "account_id, sale_type, round_key", "account_entry": "file_id, src_pos, item",
    "pending_est": "account_id, basis, sale_type, round_key, option_id", "judgment": "kind, subject",
    "check_result": "check_name, account_id, subject",
}
HASH_SKIP = {"run_meta"}          # 실행 시각 등 → 해시 대상 아님


def bucket(diff: int | None) -> str:
    """차이 구간(D-235): 0 · 1~99 · 100 이상 · 비교 못 함."""
    if diff is None:
        return "비교 못 함"
    d = abs(int(diff))
    return "0" if d == 0 else ("1~99" if d < 100 else "100 이상")


def create(path: Path) -> sqlite3.Connection:
    """새 DB 파일을 만든다(있으면 지우지 않고 중단 — 다시 만들 땐 호출 쪽이 새 경로를 고름)."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"장부 DB 가 이미 있음: {path} — 새 경로로 만드세요")
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    for ddl in TABLES.values():
        con.execute(f"CREATE TABLE {ddl}")
    con.execute("INSERT INTO run_meta VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
    con.commit()
    return con


def table_hash(con: sqlite3.Connection, table: str, skip_cols: tuple = ()) -> str:
    """표 내용 해시(정렬 고정). file_id 처럼 실행마다 같은 순서로 붙는 번호는 그대로 포함."""
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})") if r[1] not in skip_cols]
    h = hashlib.sha256()
    for row in con.execute(f"SELECT {', '.join(cols)} FROM {table} ORDER BY {ORDER_BY[table]}"):
        h.update(repr(row).encode("utf-8"))
    return h.hexdigest()


def all_hashes(con: sqlite3.Connection) -> dict[str, str]:
    return {t: table_hash(con, t) for t in TABLES if t not in HASH_SKIP}
