"""장부 DB(시험본) 오프라인 시험 — 실제 자료·개인정보·로그인 없음 · 기대값 = 결정·계획 문장에서 도출(코드에서 뽑지 않음).

- 계획 `output/_시험_261116_장부DB/계획.md` V1 = 다시 돌려도 같은 결과 → 같은 내용이면 넣는 순서가 달라도 표 해시가 같아야 함.
- D-235 차이 구간 = 0 · 1~99 · 100 이상(100원 이상 = 정산 금액을 바꾸는 차이).
- 기존 DB 를 덮어쓰지 않음(원천·결과 보존 · 다시 만들 땐 새 경로).

    python tools/verify_ledger_offline.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coupang_analytics import ledger_schema as LS  # noqa: E402

FAILS: list[str] = []


def check(cond: bool, what: str) -> None:
    print(("  ✅ " if cond else "  ❌ ") + what)
    if not cond:
        FAILS.append(what)


def _fill(con, rows: list) -> None:
    con.executemany("INSERT INTO sale_daily VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()


def t_hash_order_independent(tmp: Path) -> None:
    print("[V1] 같은 내용 = 같은 해시(넣는 순서 무관) · 내용이 다르면 다른 해시")
    rows = [("acc1", "윙", "111", "2026-10-01", 1, 10000, 1, "", "", 1, "d1"),
            ("acc1", "윙", "222", "2026-10-02", 2, 20000, 2, "", "", 1, "d2")]
    a, b, c = (LS.create(tmp / n) for n in ("a.sqlite", "b.sqlite", "c.sqlite"))
    _fill(a, rows)
    _fill(b, list(reversed(rows)))
    _fill(c, [rows[0], rows[1][:5] + (20001,) + rows[1][6:]])
    check(LS.all_hashes(a) == LS.all_hashes(b), "순서만 다른 두 DB 의 표 해시 같음")
    check(LS.table_hash(a, "sale_daily") != LS.table_hash(c, "sale_daily"), "금액 1원 다르면 해시 다름")
    check(set(LS.all_hashes(a)) == set(LS.TABLES) - LS.HASH_SKIP, "해시 대상 = 실행 기록(run_meta) 뺀 모든 표")
    for con in (a, b, c):
        con.close()


def t_no_overwrite(tmp: Path) -> None:
    print("[원천·결과 보존] 있는 DB 파일은 다시 만들지 않음")
    LS.create(tmp / "x.sqlite").close()
    try:
        LS.create(tmp / "x.sqlite")
        check(False, "있는 파일에 create → 중단")
    except FileExistsError:
        check(True, "있는 파일에 create → FileExistsError")


def t_round_carry(tmp: Path) -> None:
    """D-263 · 샘플검증 9절: 지급 가능액을 밀크런이 다 써서 그 주 비용을 못 뺀 회차 — 이월 줄(PastCfs)을 계정 내역에 넣으면 차 0."""
    from coupang_analytics import ledger_verify as LV
    print("[V4] 로켓그로스 회차 = 상품 합 × 70% + 비용(상품 줄 + 세액) + 계정 내역(밀크런·이월)")
    con = LS.create(tmp / "r.sqlite")
    con.execute("INSERT INTO src_file VALUES (1,'p','t','A',1,'h','반영',0,0,0,'')")
    con.execute("INSERT INTO order_line(account_id, sale_type, order_no, item_key, txn_type, seq, option_id, recognized, "
                "settle, src, file_id, src_row) VALUES ('A','로켓그로스','o1','v1','주문 정산',1,'v1','2026-10-07',13713,"
                "'판매수수료',1,2)")
    rk = "2026-11-06|2026-10-05|2026-10-11|70"
    con.execute("INSERT INTO pay_round(account_id, sale_type, round_key, settle_date, period_start, period_end, ratio, "
                "payable, final, file_id, src_pos) VALUES ('A','로켓그로스',?,'2026-11-06','2026-10-05','2026-10-11',70,"
                "9599,0,1,'[0]')", (rk,))
    for kind, amt, n in (("입출고비", -1225, 3), ("배송비", -2150, 4)):
        con.execute("INSERT INTO product_cost(account_id, kind, nat_key, option_id, cycle_end, amount, sign, file_stage, "
                    "file_id, sheet, src_row) VALUES ('A',?,?,'v1','2026-10-11',?,-1,'주정산',1,?,?)",
                    (kind, f"k{n}", amt, kind, n))
    ent = [("cycle:2026-10-11", "비용 세액 입출고비", "지급 구성", -123, "a"), ("cycle:2026-10-11", "비용 세액 배송비", "지급 구성", -215, "b"),
           (rk, "totalMilkRunDeductionAmount", "지급 구성", -9599, "c"), (rk, "totalWarehousingFeeDeductionAmount", "대조용", 1348, "d"),
           (rk, "totalFulfillmentFeeDeductionAmount", "대조용", 2365, "e")]
    for k, item, role, amt, pos in ent:
        con.execute("INSERT INTO account_entry(account_id, sale_type, round_key, item, role, amount, file_id, src_pos) "
                    "VALUES ('A','로켓그로스',?,?,?,?,1,?)", (k, item, role, amt, pos))
    LV.v4_rounds(con)
    q = "SELECT diff FROM check_result WHERE check_name='V4 RG 최종(상품 내역 + 계정 내역)'"
    check(con.execute(q).fetchone()[0] == -3713, "이월 줄 없으면 계산 −3,713 vs 최종 0 → 차이 −3,713(100 이상)")
    con.execute("INSERT INTO account_entry(account_id, sale_type, round_key, item, role, amount, file_id, src_pos) "
                "VALUES ('A','로켓그로스',?,'totalPastCfsDeductionAmount','지급 구성',3713,1,'f')", (rk,))
    con.execute("DELETE FROM check_result")
    LV.v4_rounds(con)
    check(con.execute(q).fetchone()[0] == 0, "이월 줄(PastCfs −3,713 → +3,713) 넣으면 차 0")
    q2 = "SELECT diff FROM check_result WHERE check_name='V4 RG 비용 = ⑮ 비용 칸'"
    check(con.execute(q2).fetchone()[0] == 0, "상품 비용 줄(VAT 별도) + 세액 = ⑮ 비용 칸 합(3,713)")
    con.close()


def t_bucket() -> None:
    print("[D-235] 차이 구간")
    check(LS.bucket(0) == "0", "0원 = '0'")
    check(LS.bucket(2) == "1~99" and LS.bucket(-99) == "1~99", "2원·−99원 = '1~99'(반올림 끝전)")
    check(LS.bucket(100) == "100 이상" and LS.bucket(-3713) == "100 이상", "100원·−3,713원 = '100 이상'")
    check(LS.bucket(None) == "비교 못 함", "비교 대상 없음 = '비교 못 함'(0으로 세지 않음)")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        t_hash_order_independent(tmp)
        t_no_overwrite(tmp)
        t_round_carry(tmp)
    t_bucket()
    print(f"\n장부 DB 시험: 실패 {len(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
