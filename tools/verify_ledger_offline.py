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
    q = "SELECT diff FROM check_result WHERE check_name='V4 RG 최종 = 지급액 + 비용 + 계정 내역'"
    check(con.execute(q).fetchone()[0] == -3713, "이월 줄 없으면 계산 −3,713 vs 최종 0 → 차이 −3,713(100 이상)")
    con.execute("INSERT INTO account_entry(account_id, sale_type, round_key, item, role, amount, file_id, src_pos) "
                "VALUES ('A','로켓그로스',?,'totalPastCfsDeductionAmount','지급 구성',3713,1,'f')", (rk,))
    con.execute("DELETE FROM check_result")
    LV.v4_rounds(con)
    check(con.execute(q).fetchone()[0] == 0, "이월 줄(PastCfs −3,713 → +3,713) 넣으면 차 0")
    q2 = "SELECT diff FROM check_result WHERE check_name='V4 RG 비용 = ⑮ 비용 칸'"
    check(con.execute(q2).fetchone()[0] == 0, "상품 비용 줄(VAT 별도) + 세액 = ⑮ 비용 칸 합(3,713)")
    con.close()


def t_carry_over_plus(tmp: Path) -> None:
    """2단계 J7 실측: 이월 칸(CarryOver) = 이번 회차에서 못 뺀 비용을 다음으로 넘긴 금액 → 비용 칸에서 뺀 만큼 되돌려 더한다."""
    from coupang_analytics import ledger_verify as LV
    from coupang_analytics.ledger_load_account import AccountLoader
    print("[이월] 로켓그로스 CarryOver 칸 = 더하는 칸(지급 구성 +)")
    con = LS.create(tmp / "carry.sqlite")
    con.execute("INSERT INTO src_file VALUES (1,'p','t','A',1,'h','반영',0,0,0,'')")
    rk = "2026-11-13|2026-10-12|2026-10-18|70"
    row = {"totalPayableAmount": 10000, "totalStorageFeeDeductionAmount": 6000,
           "totalCarryOverSettlementDeductionAmount": 6000, "totalMilkRunDeductionAmount": 10000}
    AccountLoader(con, None)._pay_entries("A", "로켓그로스", rk, row, 1, "[0]")  # type: ignore[arg-type]
    got = dict(con.execute("SELECT item, amount FROM account_entry WHERE role='지급 구성'").fetchall())
    check(got.get("totalCarryOverSettlementDeductionAmount") == 6000, "이월 6,000 → 지급 구성 +6,000(빼기 아님)")
    check(got.get("totalMilkRunDeductionAmount") == -10000, "밀크런 공제 10,000 → 지급 구성 −10,000")
    con.execute("INSERT INTO pay_round(account_id, sale_type, round_key, settle_date, period_start, period_end, ratio, "
                "payable, final, file_id, src_pos) VALUES ('A','로켓그로스',?,'2026-11-13','2026-10-12','2026-10-18',70,"
                "10000,0,1,'[0]')", (rk,))
    con.execute("INSERT INTO order_line(account_id, sale_type, order_no, item_key, txn_type, seq, option_id, recognized, "
                "settle, src, file_id, src_row) VALUES ('A','로켓그로스','o1','v1','주문 정산',1,'v1','2026-10-13',14286,"
                "'판매수수료',1,2)")
    con.execute("INSERT INTO product_cost(account_id, kind, nat_key, option_id, cycle_end, amount, sign, file_stage, "
                "file_id, sheet, src_row) VALUES ('A','보관비','k1','v1','2026-10-18',-6000,-1,'주정산',1,'보관비',9)")
    LV.v4_rounds(con)
    q = "SELECT diff FROM check_result WHERE check_name=?"
    check(con.execute(q, ("V4 RG 최종 = 지급액 + 비용 + 계정 내역",)).fetchone()[0] == 0,
          "지급 10,000 − 보관비 6,000 − 밀크런 10,000 + 이월 6,000 = 최종 0 → 차 0")
    check(con.execute(q, ("V4 RG 비용 = ⑮ 비용 칸",)).fetchone()[0] == 0, "보관비 줄 −6,000 = ⑮ 보관비 칸 6,000")
    con.close()


def t_rg_line_pay() -> None:
    """2단계 실측(1,732회차 차 0): 쿠팡은 줄마다 반올림 — 첫 지급 = 사사오입(줄 × 비율) · 나머지 = 줄 − 사사오입(줄 × (100 − 비율))."""
    from coupang_analytics.ledger_verify import rg_line_pay
    print("[RG 지급액] 줄별 반올림 70/30/100")
    check(rg_line_pay(13713, 70) == 9599 and rg_line_pay(13713, 30) == 4114, "13,713원: 70% = 9,599 · 30% = 4,114")
    check(rg_line_pay(15, 70) == 11 and rg_line_pay(15, 30) == 4, "15원: 70% = 10.5 → 11(사사오입) · 30% = 15 − 11 = 4")
    lines = [13713, 15, 9999, -2501, 7]
    check(all(rg_line_pay(x, 70) + rg_line_pay(x, 30) == x for x in lines), "줄마다 70% + 30% = 줄 금액(1원도 안 샘)")
    check(all(rg_line_pay(x, 100) == x for x in lines), "100% = 줄 그대로")
    check(sum(rg_line_pay(x, 70) for x in (15, 15)) == 22 and round(30 * 70 / 100) == 21,
          "줄별 합(11+11=22) ≠ 합계 × 비율(21) — 합계로 곱하면 1원씩 어긋남")


def _judge_db(tmp: Path):
    con = LS.create(tmp / "j.sqlite")
    con.execute("INSERT INTO src_file VALUES (1,'p','t','A',1,'h','반영',0,0,0,'')")
    con.execute("INSERT INTO order_line(account_id, sale_type, order_no, item_key, txn_type, seq, option_id, recognized, "
                "settle, src, file_id, src_row) VALUES ('A','윙','o1','v1','주문',1,'v1','2026-09-01',1000,'주문상세',1,2)")
    for rk, ps, pe in (("r1", "2026-08-01", "2026-08-07"), ("r2", "2026-09-01", "2026-09-07")):
        con.execute("INSERT INTO pay_round(account_id, sale_type, round_key, settle_date, period_start, period_end, ratio, "
                    "target, file_id, src_pos) VALUES ('A','윙',?,'x',?,?,100,5000,1,?)", (rk, ps, pe, rk))
    rows = [("V4 윙 상품 합 = targetAmount", "A", "윙 r1", 5000, 0, -5000, "100 이상", ""),
            ("V4 윙 상품 합 = targetAmount", "A", "윙 r2", 5000, 1000, -4000, "100 이상", "")]
    con.executemany("INSERT INTO check_result VALUES (?,?,?,?,?,?,?,?)", rows)
    con.commit()
    return con


def _rule(params: dict) -> dict:
    return {"id": "R-J7-01", "applies": {"check_names": ["V4 윙 상품 합 = targetAmount"], "buckets": ["100 이상"]},
            "condition": {"name": "before_first_line", "params": params}, "verdict": "받기 전 기간",
            "basis": "시험", "quote": "시험", "judged_by": "Claude", "date": "2026-11-16"}


def t_judge(tmp: Path) -> None:
    """D-265: 규칙 = 자료 조건만(계정·금액 파라미터 금지) · 적용 줄 'R-xx 적용' · 표본 파일 · 규칙 밖 줄은 남김."""
    import json
    from coupang_analytics import ledger_judge as LJ
    print("[판정 D-265] 규칙 파일 적용")
    folder = tmp / "판정"
    folder.mkdir()
    (folder / "규칙_J7.json").write_text(json.dumps({"rules": [_rule({"account_id": "A"})]}), encoding="utf-8")
    try:
        LJ.load_rules(folder)
        check(False, "계정 조건 파라미터 → 중단(D-229)")
    except ValueError:
        check(True, "계정 조건 파라미터 → 중단(D-229)")
    (folder / "규칙_J7.json").write_text(json.dumps({"rules": [_rule({})]}), encoding="utf-8")
    con = _judge_db(tmp)
    LJ.run(con, folder)
    got = dict(con.execute("SELECT subject, cause FROM check_result").fetchall())
    check(got["윙 r1"] == "R-J7-01 적용", "기간 끝(08-07) < 정산 파일 첫 줄(09-01) · 계산 0 → 'R-J7-01 적용'")
    check(got["윙 r2"] == "", "기간 안에 줄 있는 회차는 규칙 밖(원인 비움 → 규칙밖.json)")
    smp = json.loads((folder / "표본_R-J7-01.json").read_text(encoding="utf-8"))
    check(smp["적용 줄"] == 1 and len(smp["표본"]) == 1, "표본 파일 = 적용 줄(20줄 미만이면 전부)")
    left = json.loads((folder / "규칙밖.json").read_text(encoding="utf-8"))
    check([x["subject"] for x in left] == ["윙 r2"], "규칙밖.json = 남은 줄")
    con.close()


def t_cost_report_before(tmp: Path) -> None:
    """R-J7-02 '비용 리포트 받기 전 주기' = 그 주기 비용 줄 0 + 그 계정 비용 리포트 첫 주기보다 앞 · 중간에 빠진 주기는 규칙 밖."""
    from coupang_analytics import ledger_judge as LJ
    print("[판정 R-J7-02] 받기 전 주기만 · 중간 빠짐은 규칙 밖")
    con = LS.create(tmp / "cost_before.sqlite")
    con.execute("INSERT INTO src_file VALUES (1,'p','t','A',1,'h','반영',0,0,0,'')")
    for rk, pe in (("r1", "2025-11-09"), ("r3", "2026-01-11")):      # r1 = 첫 비용 주기(12-07) 앞 · r3 = 중간(12-07 뒤)
        con.execute("INSERT INTO pay_round(account_id, sale_type, round_key, settle_date, period_start, period_end, ratio, "
                    "file_id, src_pos) VALUES ('A','로켓그로스',?,'x',?,?,70,1,?)", (rk, pe, pe, rk))
        con.execute("INSERT INTO account_entry(account_id, sale_type, round_key, item, role, amount, file_id, src_pos) "
                    "VALUES ('A','로켓그로스',?,'totalStorageFeeDeductionAmount','대조용',500,1,?)", (rk, rk))
    con.execute("INSERT INTO product_cost(account_id, kind, nat_key, cycle_end, amount, sign, file_id, sheet, src_row) "
                "VALUES ('A','보관비','k','2025-12-07',-10,-1,1,'보관비',9)")
    con.executemany("INSERT INTO check_result VALUES (?,?,?,?,?,?,?,?)",
                    [("V4 RG 비용 = ⑮ 비용 칸", "A", f"로켓그로스 {rk}", -500, 0, 500, "100 이상", "") for rk in ("r1", "r3")])
    hit = LJ.c_cost_report_missing(con, con.execute("SELECT * FROM check_result").fetchall(), {})
    check({k[2] for k in hit} == {"로켓그로스 r1"}, "첫 비용 주기(12-07) 앞 r1 = 적용 · 중간 주기 r3(비용 줄 0) = 규칙 밖")
    con.close()


class _Reg:
    def __init__(self):
        self.skips: list = []

    def skip(self, fid, reason, n=1):
        self.skips.append((reason, n))

    def done(self, fid, read, loaded):
        self.read, self.loaded = read, loaded


def t_live_amount(tmp: Path) -> None:
    """J4 실측: 라이브정산 상세 줄 수수료 = `amount`(VAT 별도) · 상세 totalAmount 는 빈 칸 → 0원으로 넣으면 오류."""
    import json
    from coupang_analytics.ledger_load_sales import SalesLoader
    print("[라이브정산] 상세 수수료 = amount 칸(VAT 별도)")
    con = LS.create(tmp / "live.sqlite")
    f = tmp / "라이브정산_202601.json"
    f.write_text(json.dumps({"상세": [{"orderId": 1, "vendorItemId": 11, "orderOrCancel": "O", "amount": 626,
                                     "totalAmount": None, "calculationDate": "20260225"}],
                            "요약": [{"platformFee": 626, "vat": 63, "totalAmount": 689}]}), encoding="utf-8")
    reg = _Reg()
    loader = SalesLoader(con, reg)  # type: ignore[arg-type]
    loader._live(f, 1, "A")
    amt = con.execute("SELECT amount FROM product_cost WHERE kind='라이브 수수료'").fetchone()[0]
    check(amt == -626, "상세 amount 626 → 공제 −626(totalAmount 빈 칸이어도 0 아님)")
    check(reg.read == 2 and reg.loaded == 1 and reg.skips[0][1] == 1, "요약 1줄 = 뺀 줄(생략 · 중복)")
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
        t_carry_over_plus(tmp)
        t_judge(tmp)
        t_cost_report_before(tmp)
        t_live_amount(tmp)
    t_rg_line_pay()
    t_bucket()
    print(f"\n장부 DB 시험: 실패 {len(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
