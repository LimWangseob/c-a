"""장부 DB 검증 V2~V7 — 결과는 check_result 표에 쓰고 요약 줄을 돌려준다(V1 = 두 번 빌드한 DB 의 표 해시 비교 · same_hashes).

- V4 회차 대조(D-263): 상품 내역(회차 기간) + 계정 내역(회차 KEY) = 쿠팡 지급내역 금액.
  윙: 구매확정일이 기간 안인 주문상세 줄 정산금액 합 = targetAmount → × 지급비율(반올림) = paidAmount → − 차감 사유 = 최종지급액.
  로켓그로스: 매출인식일이 기간 안인 판매수수료 줄 정산대상액 합 × 지급비율 = totalPayableAmount
  → + 그 주(정산주기 끝 = 기간 끝) 상품 비용·보상 + 비용 세액·반출 배송 서비스비 + 회차 KEY 지급 구성(이월·추가 공제·조정) = 최종.
  비용은 ⑮ 의 비용 칸(대조용)이 있는 회차에 붙인다(70%·30% 중 쿠팡이 뺀 회차). '정산줄없음' 비용은 다음 회차 이월 줄로 들어가므로 뺀다.
- 차이 구간 = D-235(0 · 1~99 · 100 이상). 100 이상 = J7 원인 판정 대상(판정 전 cause 빈 칸).
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

from .ledger_schema import all_hashes, bucket

CFS_REF = ("totalStorageFeeDeductionAmount", "totalFulfillmentFeeDeductionAmount", "totalWarehousingFeeDeductionAmount",
           "totalBarcodeLabelingFeeDeductionAmount", "totalContainerUnloadingFeeDeductionAmount",
           "totalCreturnGradingFeeDeductionAmount", "totalCreturnReverseShippingFeeDeductionAmount",
           "totalVreturnHandlingFeeDeductionAmount", "totalVreturnShippingFeeDeductionAmount",
           "totalCfsInventoryCompensationAmount")
_INS = "INSERT OR REPLACE INTO check_result VALUES (?,?,?,?,?,?,?,?)"


def same_hashes(a: sqlite3.Connection, b: sqlite3.Connection) -> dict[str, bool]:
    ha, hb = all_hashes(a), all_hashes(b)
    return {t: ha[t] == hb.get(t) for t in ha}


def _put(con, name: str, acc: str, subj: str, exp, act, cause: str = "") -> int | None:
    diff = None if exp is None or act is None else int(act) - int(exp)
    con.execute(_INS, (name, acc, subj, exp, act, diff, bucket(diff), cause))
    return diff


def v2_coverage(con) -> list[str]:
    st = con.execute("SELECT status, COUNT(*) FROM src_file GROUP BY status ORDER BY status").fetchall()
    gap = con.execute("SELECT file_id, path, rows_read, rows_loaded, rows_skipped FROM src_file WHERE status='반영' "
                      "AND rows_read != rows_loaded + rows_skipped").fetchall()
    for fid, path, rr, rl, rs in gap:
        _put(con, "V2 줄 수(읽음 = 넣음 + 뺌)", "", path, rr, rl + rs)
    errs = con.execute("SELECT path, note FROM src_file WHERE status='오류'").fetchall()
    for path, note in errs:
        con.execute(_INS, ("V2 읽기 오류", "", path, None, None, None, "확인 필요", note))
    return [f"V2 원천: {dict(st)} · 줄 수 안 맞는 파일 {len(gap)} · 읽기 오류 {len(errs)}"]


def v3_keys(con) -> list[str]:
    l1 = con.execute("SELECT COUNT(*) FROM check_result WHERE check_name='L1 같은 KEY 금액 다름'").fetchone()[0]
    dup_cost = con.execute(
        "SELECT account_id, kind, nat_key, cycle_end, file_stage, COUNT(*) FROM product_cost "
        "GROUP BY account_id, kind, nat_key, cycle_end, file_stage HAVING COUNT(*) > 1").fetchall()
    for acc, kind, nat, cyc, stage, n in dup_cost:
        con.execute(_INS, ("V3 비용 KEY 겹침", acc, f"{kind}|{cyc}|{stage}|{nat}", 1, n, n - 1, "확인 필요", ""))
    dup_round = con.execute("SELECT account_id, round_key FROM pay_round WHERE round_key LIKE '%#%'").fetchall()
    for acc, rk in dup_round:
        con.execute(_INS, ("V3 회차 KEY 겹침", acc, rk, None, None, None, "확인 필요", ""))
    multi = con.execute(
        "SELECT account_id, option_id, COUNT(DISTINCT product_id) FROM option_attr WHERE product_id != '' "
        "GROUP BY account_id, option_id HAVING COUNT(DISTINCT product_id) > 1").fetchall()
    for acc, vid, n in multi:
        con.execute(_INS, ("V3 노출상품ID 2개 이상(J6)", acc, vid, 1, n, n - 1, "확인 필요", ""))
    inv = con.execute(
        "SELECT account_id, option_id, COUNT(DISTINCT inventory_id) FROM option_attr WHERE inventory_id != '' "
        "GROUP BY account_id, option_id HAVING COUNT(DISTINCT inventory_id) > 1").fetchall()
    for acc, vid, n in inv:
        con.execute(_INS, ("V3 등록상품ID 2개 이상", acc, vid, 1, n, n - 1, "확인 필요", ""))
    return [f"V3 KEY: 같은 KEY 금액 다름 {l1} · 비용 KEY 겹침 {len(dup_cost)} · 회차 KEY 겹침 {len(dup_round)} · "
            f"노출상품ID 2개 이상 옵션 {len(multi)} · 등록상품ID 2개 이상 옵션 {len(inv)}"]


def _line_sums(con, acc: str, src: str) -> list[tuple[str, int]]:
    return con.execute("SELECT recognized, settle FROM order_line WHERE account_id=? AND src=?", (acc, src)).fetchall()


def _period_sum(lines: list, ps: str, pe: str) -> int:
    return sum(s for d, s in lines if ps <= d <= pe)


def _entries(con, acc: str, rk: str, role: str) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for item, amt in con.execute("SELECT item, amount FROM account_entry WHERE account_id=? AND round_key=? AND role=?",
                                 (acc, rk, role)):
        out[item] += amt
    return out


def _wing(con, r: tuple, lines: list) -> None:
    acc, rk, ps, pe, ratio, release, tgt, payable, final, pending = r
    ded = sum(_entries(con, acc, rk, "지급 구성").values())
    subj = f"윙 {rk}"
    if release:      # 하루짜리 100% = 보류 해제(pendingAmount) 또는 윙 추가지급(payDate = 정산일 · 샘플검증 5절 3)
        add = con.execute("SELECT COALESCE(SUM(amount),0) FROM product_cost WHERE account_id=? AND kind='윙 추가지급' "
                          "AND occur_date=?", (acc, ps)).fetchone()[0]
        _put(con, "V4 윙 보류 해제·추가지급 최종", acc, subj, final, (pending or 0) + int(add) + ded)
        return
    s = _period_sum(lines, ps, pe)
    if not any(ps <= d <= pe for d, _ in lines) and tgt:
        _put(con, "V4 윙 상품 합 = targetAmount", acc, subj, tgt, s, "후보: 그 기간 정산 파일 줄 없음(받기 전 기간)")
        return
    _put(con, "V4 윙 상품 합 = targetAmount", acc, subj, tgt, s)
    calc_pay = round((tgt or 0) * ratio / 100)
    _put(con, "V4 윙 지급액 = target × 비율", acc, subj, payable, calc_pay)
    if final is not None:
        _put(con, "V4 윙 최종 = 지급액 − 차감", acc, subj, final, (payable or 0) + ded)
        _put(con, "V4 윙 최종(상품 내역부터)", acc, subj, final, round(s * ratio / 100) + ded)


def _rg_costs(con, acc: str, pe: str) -> int:
    prod = con.execute("SELECT COALESCE(SUM(amount),0) FROM product_cost WHERE account_id=? AND cycle_end=? "
                       "AND file_stage != '정산줄없음' AND kind NOT LIKE '윙%' AND kind != '라이브 수수료'",
                       (acc, pe)).fetchone()[0]
    acct = con.execute("SELECT COALESCE(SUM(e.amount),0) FROM account_entry e JOIN src_file f USING(file_id) "
                       "WHERE e.account_id=? AND e.round_key=? AND e.role='지급 구성' AND f.path NOT LIKE '%정산줄없음%'",
                       (acc, f"cycle:{pe}")).fetchone()[0]
    return int(prod) + int(acct)


def _rg(con, r: tuple, lines: list) -> None:
    acc, rk, ps, pe, ratio, _rel, _tgt, payable, final, _p = r
    subj = f"로켓그로스 {rk}"
    s = _period_sum(lines, ps, pe)
    if not any(ps <= d <= pe for d, _ in lines) and payable:
        _put(con, "V4 RG 지급액 = 상품 합 × 비율", acc, subj, payable, 0, "후보: 그 기간 정산 파일 줄 없음(받기 전 기간)")
        return
    _put(con, "V4 RG 지급액 = 상품 합 × 비율", acc, subj, payable, round(s * ratio / 100))
    ref = _entries(con, acc, rk, "대조용")
    has_cfs = any(ref.get(k) for k in CFS_REF)
    costs = _rg_costs(con, acc, pe) if has_cfs else 0
    if has_cfs:
        cfs_ref = -sum(ref.get(k, 0) for k in CFS_REF if k != "totalCfsInventoryCompensationAmount") \
            + ref.get("totalCfsInventoryCompensationAmount", 0)
        _put(con, "V4 RG 비용 = ⑮ 비용 칸", acc, subj, cfs_ref, costs)
    pay = sum(_entries(con, acc, rk, "지급 구성").values())
    if final is not None:
        _put(con, "V4 RG 최종(상품 내역 + 계정 내역)", acc, subj, final, (payable or 0) + costs + pay)


def v4_rounds(con) -> list[str]:
    rounds = con.execute("SELECT account_id, round_key, period_start, period_end, ratio, release, target, payable, final, "
                         "pending, sale_type FROM pay_round ORDER BY account_id, sale_type, round_key").fetchall()
    cache: dict[tuple, list] = {}
    for r in rounds:
        acc, st = r[0], r[10]
        src = "주문상세" if st == "윙" else "판매수수료"
        lines = cache.setdefault((acc, src), _line_sums(con, acc, src))
        (_wing if st == "윙" else _rg)(con, r[:10], lines)
    out = ["V4 회차 대조(차이 구간 = 건수):"]
    for name, b, n in con.execute("SELECT check_name, bucket, COUNT(*) FROM check_result WHERE check_name LIKE 'V4%' "
                                  "GROUP BY check_name, bucket ORDER BY check_name, bucket"):
        out.append(f"  {name} · {b}: {n}")
    return out


def v5_month(con) -> list[str]:
    q = ("SELECT account_id, substr(recognized,1,7), SUM(settle) FROM order_line WHERE src='주문별매출' "
         "GROUP BY account_id, substr(recognized,1,7)")
    n = 0
    for acc, ym, s in con.execute(q).fetchall():
        key = f"month:{ym.replace('-', '')}|%"
        ref = con.execute("SELECT SUM(amount), COUNT(*) FROM account_entry WHERE account_id=? AND round_key LIKE ? "
                          "AND item='매출내역 apAmount'", (acc, key)).fetchone()
        _put(con, "V5 주문별매출 달 합 = 매출내역 apAmount", acc, ym, ref[0] if ref[1] else None, s)
        n += 1
    rows = con.execute("SELECT bucket, COUNT(*) FROM check_result WHERE check_name LIKE 'V5%' GROUP BY bucket").fetchall()
    return [f"V5 달 대조 {n}건: {dict(rows)}"]


def v6_double(con) -> list[str]:
    dup = con.execute("SELECT p.line_id, p.stage, p.settle_date, COUNT(*) FROM order_pay p GROUP BY p.line_id, p.stage, "
                      "p.settle_date HAVING COUNT(*) > 1").fetchall()
    for lid, stage, sd, n in dup:
        con.execute(_INS, ("V6 같은 줄 같은 지급 2번", "", f"{lid}|{stage}|{sd}", 1, n, n - 1, bucket(n - 1), ""))
    return [f"V6 두 번 세기: 같은 주문 줄이 같은 지급 단계·정산일에 2번 이상 {len(dup)}"]


def v7_links(con) -> list[str]:
    q = ("SELECT a.account_id, a.order_no, a.item_key, a.txn_type FROM order_line a WHERE a.src='주문별매출' "
         "AND NOT EXISTS (SELECT 1 FROM order_line b WHERE b.src='주문상세' AND b.account_id=a.account_id "
         "AND b.order_no=a.order_no AND (b.option_id=a.option_id OR a.option_id=''))")
    miss = con.execute(q).fetchall()
    for acc, order, item, tt in miss:
        con.execute(_INS, ("V7 주문별매출 줄 → 정산 파일 짝 없음", acc, f"{order}|{item}|{tt}", None, None, None,
                           "확인 필요", ""))
    return [f"V7 주문별매출 줄 중 정산 파일 짝 없음 {len(miss)}(시점 차이·기간 밖 포함 → J3)"]


INDEXES = ("CREATE INDEX IF NOT EXISTS ix_pc_cycle ON product_cost(account_id, cycle_end)",
           "CREATE INDEX IF NOT EXISTS ix_pc_kind ON product_cost(account_id, kind, occur_date)",
           "CREATE INDEX IF NOT EXISTS ix_ae_round ON account_entry(account_id, round_key, role)",
           "CREATE INDEX IF NOT EXISTS ix_ol_src ON order_line(account_id, src, order_no)")


def run(con: sqlite3.Connection) -> list[str]:
    for ddl in INDEXES:           # 색인 = 조회 속도만(표 내용·해시 그대로)
        con.execute(ddl)
    con.execute("DELETE FROM check_result WHERE check_name LIKE 'V%'")
    out = []
    for f in (v2_coverage, v3_keys, v4_rounds, v5_month, v6_double, v7_links):
        out += f(con)
        con.commit()
    return out
