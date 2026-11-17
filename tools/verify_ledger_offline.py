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


def t_statement(tmp: Path) -> None:
    """계획 5절 · D-185(관리 시작 달·계약 전 판매 뺌) · D-266 ③(달 = 쿠팡 정산 기준 날짜의 달) · D-153 ①(세액은 쿠팡 자료 비율)."""
    from coupang_analytics import ledger_statement as ST
    print("[정산서 숫자] 관리 옵션만 · 관리 시작 달·계약일 · 배송비 섞인 주문 · 비용 세액 비율")
    con = LS.create(tmp / "st.sqlite")
    ol = ("INSERT INTO order_line(account_id,sale_type,order_no,item_key,txn_type,seq,option_id,recognized,sales,coupon,fee,settle,"
          "src,file_id,src_row) VALUES (?,?,?,?,?,1,?,?,?,0,0,?,'주문상세',1,?)")
    rows = [("A", "윙", "o1", "k1", "판매", "M1", "2026-08-31", 1000, 900),     # 관리 · 8월
            ("A", "윙", "o1", "k0", "판매", "", "2026-08-31", 3000, 2700),       # o1 배송비(상품 줄 모두 관리)
            ("A", "윙", "o2", "k2", "판매", "M1", "2026-09-01", 2000, 1800),     # 관리 · 9월(기준 날짜 달)
            ("A", "윙", "o2", "k3", "판매", "X9", "2026-09-01", 5000, 4500),     # 관리 밖
            ("A", "윙", "o2", "k4", "판매", "", "2026-09-01", 3000, 2700),       # o2 배송비 = 섞인 주문
            ("A", "윙", "o3", "k5", "판매", "M1", "2026-07-31", 7000, 6300),     # 관리 시작 달 앞
            ("A", "윙", "o4", "k6", "판매", "M1", "2026-08-04", 4000, 3600)]     # 계약일 앞이지만 계약 달 → 넣음(D-185 ② 달 단위)
    con.executemany(ol, [r + (i,) for i, r in enumerate(rows)])
    pc = ("INSERT INTO product_cost(account_id,kind,nat_key,option_id,cycle_end,amount,sign,file_id,sheet,src_row) "
          "VALUES ('A','보관비',?,?,'2026-09-07',?,-1,1,'s',?)")
    con.executemany(pc, [("n1", "M1", -300, 1), ("n2", "X9", -700, 2)])
    con.execute("INSERT INTO account_entry(account_id,sale_type,round_key,item,role,amount,occur_date,file_id,src_pos) "
                "VALUES ('A','로켓그로스','r1','비용 세액 보관비','대조용',-100,'2026-09-07',1,'p')")
    sc = ST.with_products(con, "A", {"ok": True, "managed": {"M1"}, "start": "2026-08", "cdate": "2026-08-05", "check": []})
    conf = ST.confirmed(con, "A", sc)
    check(set(conf) == {"2026-08", "2026-09"}, "달 = 기준 날짜 달 · 관리 시작 달 앞(7월) 없음")
    check(conf["2026-08"]["sales"] == 8000 and conf["2026-08"]["settle"] == 7200,
          "8월 = 관리 1,000 + 관리만 든 주문 배송비 3,000 + 계약일(08-05) 앞이지만 계약 달 4,000(D-185 ② 달 단위)")
    sc_early = {**sc, "start": "2026-07"}         # 자동 판정 달이 계약 달보다 빠른 계정
    check("2026-07" not in ST.confirmed(con, "A", sc_early), "관리 시작 달이 빨라도 계약 시작일 달(8월) 앞 7월 판매 뺌(D-185 ②)")
    check(conf["2026-09"]["sales"] == 2000 and conf["2026-09"]["ship_mixed"] == 2700,
          "9월 = 관리 2,000만 · 관리 밖 상품 뺌 · 섞인 주문 배송비는 금액 밖 따로(2,700)")
    cost = ST.costs(con, "A", sc)
    check(cost["2026-09"]["보관비"] == [-300, -30, -1000, 0], "보관비 관리 −300 · 세액 −100 × 300/1,000 = −30 · 계정 전체 −1,000")
    cr = "INSERT INTO check_result VALUES (?, 'A', ?, ?, 0, ?, '100 이상', ?)"
    con.executemany(cr, [("V4 RG 지급액 = 상품 줄별 × 비율", "로켓그로스 2026-09-05|2026-08-25|2026-09-02|70", 5000, -5000, "R-J7-01 적용"),
                         ("V4 RG 비용 = ⑮ 비용 칸", "로켓그로스 2026-08-20|2026-07-28|2026-08-03|70", -800, 800, "R-J7-02 적용"),
                         ("V4 RG 지급액 = 상품 줄별 × 비율", "로켓그로스 2026-09-12|2026-09-03|2026-09-09|70", 900, -900, "R-J7-03 적용")])
    nd = ST.account_numbers(con, "A", sc)
    check(set(k for k, v in nd["months"].items() if v["no_data"]) == {"2026-08", "2026-09"} and nd["status"] == "자료 없음 달 있음",
          "자료 받기 전 회차(R-J7-01·02)가 걸친 관리 달 = '자료 없음·확인 필요'(D-146) · 0원 통과 안 함")
    check(len(nd["months"]["2026-08"]["no_data"]) == 2, "계약 달(8월)에 걸친 회차는 계약일 앞에서 끝나도 넣음(달 단위) · 끝전 규칙(R-J7-03)은 자료 없음 아님")
    nd_early = ST.account_numbers(con, "A", sc_early)
    check("2026-07" not in nd_early["months"], "계약 시작일 달 앞(7월)은 자료 없음 달로도 안 셈(D-185 ②)")
    r = ST.account_numbers(con, "A", {**sc, "managed": set(), "check": ["관리 옵션 0"]})
    check(r["status"] == "관리 상품 확인 필요" and r["total"]["confirmed"]["sales"] == 0, "범위 못 정함 → '관리 상품 확인 필요'(가리지 않음)")
    con.close()


def t_statement_links(tmp: Path) -> None:
    """D-116 ①(관리 VID 있는 등록상품 = 상품 전체) · D-116 ②(상품 없는 배송비 = 반품 조회 상품) · 반출 배송 서비스비 = 대표 등록상품
    (없으면 같은 반출ID 반출비 줄) · 못 찾으면 금액 밖(D-146)."""
    from coupang_analytics import ledger_statement as ST
    print("[정산서 숫자] 등록상품 단위 관리 · 반품 조회 배송비 · 반출 배송 대표 상품")
    con = LS.create(tmp / "st2.sqlite")
    ol = ("INSERT INTO order_line(account_id,sale_type,order_no,item_key,txn_type,seq,option_id,inventory_id,recognized,sales,coupon,"
          "fee,settle,src,file_id,src_row) VALUES ('A',?,?,?,'판매',1,?,?,'2026-09-10',?,0,?,?,?,1,?)")
    rows = [("로켓그로스", "o1", "k1", "M1", "P1", 1000, 0, 900, "판매수수료"),     # 관리 옵션 · 등록상품 P1
            ("로켓그로스", "o2", "k2", "M2", "P1", 2000, 0, 1800, "판매수수료"),    # 같은 등록상품 P1 의 다른 옵션 → 관리
            ("로켓그로스", "o3", "k3", "X9", "P9", 5000, 0, 4500, "판매수수료"),    # 관리 밖
            ("윙", "o4", "k4", "", "", 6000, 198, 5802, "주문상세"),             # 상품 줄 없는 배송비 · 반품 조회 = M2 → 관리
            ("윙", "o5", "k5", "", "", 3000, 99, 2901, "주문상세")]              # 상품 줄 · 반품 조회 모두 없음 → 금액 밖
    con.executemany(ol, [r + (i,) for i, r in enumerate(rows)])
    ae = ("INSERT INTO account_entry(account_id,sale_type,round_key,item,role,amount,link_key,occur_date,file_id,src_pos) "
          "VALUES ('A',?,?,?,?,?,?,'2026-09-07',1,?)")
    con.executemany(ae, [("", "order:o4", ST.RETURN_ITEM, "연결", 0, "o4>M2", "r1"),
                         ("로켓그로스", "cycle:2026-09-07", ST.OUTBOUND_SHIP, "지급 구성", -2200, "B1>P1", "b1"),    # 대표 = 관리
                         ("로켓그로스", "cycle:2026-09-07", ST.OUTBOUND_SHIP, "지급 구성", -2800, "B2>", "b2"),      # '-' → 반출비 줄 P1
                         ("로켓그로스", "cycle:2026-09-07", ST.OUTBOUND_SHIP, "지급 구성", -1000, "B3>P1,P9", "b3"),  # 섞임 → 금액 밖
                         ("로켓그로스", "cycle:2026-09-07", ST.OUTBOUND_SHIP, "지급 구성", -500, "B4>", "b4")])      # 못 찾음 → 금액 밖
    con.execute("INSERT INTO product_cost(account_id,kind,nat_key,option_id,inventory_id,cycle_end,amount,sign,file_id,sheet,src_row) "
                "VALUES ('A','반출비','반출ID=B2|옵션ID=M2','M2','P1','2026-09-07',-300,-1,1,'s',1)")
    sc = ST.with_products(con, "A", {"ok": True, "managed": {"M1"}, "start": "2026-08", "cdate": "", "check": []})
    check(sc["mpids"] == {"P1"} and "M2" in sc["mopts"], "관리 옵션 M1 의 등록상품 P1 → 같은 등록상품 옵션 M2 도 관리(D-116 ①)")
    m = ST.confirmed(con, "A", sc)["2026-09"]
    check(m["gross"] == 3000 and m["ship"] == 6000 and m["ship_fee"] == -198 and m["settle"] == 8502,
          "판매 = M1 1,000 + M2 2,000 · 배송비 6,000(반품 조회 상품 M2 = 관리 D-116 ②) · 배송비 수수료 −198 따로")
    check(m["ship_unknown"] == 2901, "상품 줄·반품 조회 모두 없는 배송비 = 금액 밖 '확인 필요'(2,901 · 비율로 나누지 않음 D-146)")
    ob = ST.costs(con, "A", sc)["2026-09"][ST.OUTBOUND_SHIP]
    check(ob[0] == -5000 and ob[3] == -1500 and ob[2] == -6500,
          "반출 배송 = 대표 P1 −2,200 + 대표 없음→반출비 줄 P1 −2,800 = −5,000 · 섞임·못 찾음 −1,500 금액 밖 · 계정 전체 −6,500")
    con.close()


def t_statement_account(tmp: Path) -> None:
    """계정 단위 값(4단계 2차): 윙 차감 묶음(광고·빠른정산 사용액 D-312 ①·이용료·나머지 = 기타·지급 끝난 음수 = 3PM D-304) ·
    로켓그로스 추가 공제 나머지 = 기타(세이버 따로 D-271) · 광고 = 청구액 × 보고서 옵션 비율 × 1.1(D-140) · 이용료 = 등록 비율(D-271) ·
    기타 = 판매 비중·등록 비중 중 작은 쪽(D-237·D-241 ⑨)."""
    from coupang_analytics import ledger_statement as ST
    from coupang_analytics import ledger_statement_account as SA
    print("[정산서 숫자] 계정 단위 값 — 묶음·광고 비율·등록 비율·작은 쪽")
    con = LS.create(tmp / "st3.sqlite")
    con.executemany("INSERT INTO pay_round(account_id,sale_type,round_key,settle_date,period_start,period_end,ratio,status,release,"
                    "payable,pending,file_id,src_pos) VALUES ('A',?,?,'2026-10-01','2026-09-01','2026-09-07',100,?,0,?,0,1,?)",
                    [("윙", "w1", "DONE", 50000, "p1"), ("로켓그로스", "g1", "", 0, "p2")])
    ae = ("INSERT INTO account_entry(account_id,sale_type,round_key,item,role,amount,link_key,occur_date,file_id,src_pos) "
          "VALUES ('A',?,?,?,?,?,?,?,1,?)")
    con.executemany(ae, [("윙", "w1", "차감 상품/브랜드광고비", "지급 구성", -1000, "", "", "a1"),
                         ("윙", "w1", "차감 빠른정산 사용액", "지급 구성", -500, "", "", "a2"),
                         ("윙", "w1", "차감 판매자서비스이용료", "지급 구성", -55000, "", "", "a3"),
                         ("윙", "w1", "totalDeductionAmount", "대조용", 56700, "", "", "a4"),
                         ("로켓그로스", "g1", "totalAdditionalDeductionAmount", "대조용", 10000, "", "", "a5"),
                         ("로켓그로스", "g1", "totalAdSalesDeductionAmount", "지급 구성", -3000, "", "", "a6"),
                         ("로켓그로스", "g1", "totalMilkRunDeductionAmount", "지급 구성", -2000, "", "", "a7"),
                         ("로켓그로스", "g1", "totalSubscriptionFeeDeductionAmount", "지급 구성", -1000, "", "", "a8"),
                         ("", "date:2026-09-05", "광고 청구가능 PA", "대조용", -1000, "101", "2026-09-05", "a9")])
    con.execute("INSERT INTO src_file(file_id,path,kind,account_id,size,sha256,status) VALUES "
                "(2,'광고/A_매출성장광고_202609.xlsx','광고 보고서(매출성장광고)','A',1,'x','반영')")
    rs = "INSERT INTO ratio_src(account_id,kind,link_key,option_id,day,value,flag,file_id,src_pos) VALUES ('A',?,?,?,?,?,'',2,?)"
    con.executemany(rs, [("광고 보고서", "101", "901", "2026-09-05", 300, "r1"), ("광고 보고서", "101", "909", "2026-09-05", 100, "r2"),
                         ("등록상품", "801", "901", "2026-08-01", 0, "r3"), ("등록상품", "809", "909", "2026-08-01", 0, "r4")])
    con.execute("INSERT INTO order_line(account_id,sale_type,order_no,item_key,txn_type,seq,option_id,inventory_id,recognized,sales,coupon,"
                "fee,settle,src,file_id,src_row) VALUES ('A','윙','o1','k1','판매',1,'901','801','2026-09-03',1000,0,100,900,'주문상세',1,1)")
    lines = {x[0]: dict(x[3]) for x in SA.deduct_lines(con, "A")}
    w = lines["윙"]
    check(w == {SA.AD: 1000, SA.FAST: 500, SA.SVC: 55000, SA.ETC: 200, SA.PM3: -6700},
          "윙 차감 = 광고 1,000 · 빠른정산 사용액 → 계좌인출액 500 · 이용료 55,000 · 나머지 기타 200 · 지급 끝난 음수 −6,700 = 3PM")
    g = lines["로켓그로스"]
    check(g == {SA.AD: 3000, SA.MILK: 2000, SA.SUB: 1000, SA.ETC: 4000}, "로켓그로스 추가 공제 10,000 − 광고·밀크런·세이버 = 기타 4,000")
    sc = ST.with_products(con, "A", {"ok": True, "managed": {"901"}, "start": "2026-09", "cdate": "", "check": []})
    it = SA.account_values(con, "A", sc, "2026-09")["items"]
    check(round(it[SA.AD]["m"]) == 3725, "광고 = 청구 1,000 × 보고서 관리 비율 300/400 × 1.1 = 825 + 상품 자료 없는 공제(4,000 − 1,100) × 줄 관리 정산 비율 1.0(D-162)")
    check(round(it[SA.SVC]["m"]) == 27500, "이용료 55,000 × 등록상품 1/2(D-271)")
    check(round(it[SA.SUB]["m"]) == 500, "세이버 1,000 × 등록상품 1/2(D-271 · 기타에서 따로)")
    check(round(it[SA.ETC]["m"]) == 2100, "기타 (200 + 4,000) × min(판매 비중 1.0, 등록 비중 0.5)(D-237·D-241 ⑨)")
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
        t_statement(tmp)
        t_statement_links(tmp)
        t_statement_account(tmp)
    t_rg_line_pay()
    t_bucket()
    print(f"\n장부 DB 시험: 실패 {len(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
