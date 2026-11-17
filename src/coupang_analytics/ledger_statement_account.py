"""장부 DB(시험본) → 위탁정산서 계정 단위 값의 관리 상품 몫(4단계 2차 · 광고·밀크런·서비스이용료·기타 공제).

- 계정 단위 값 = ④ 지급 회차(pay_round)의 공제 칸 · 윙 '차감 …' 줄 — 항목 묶음은 현행 정산서 코드의 `deductions()` 와 같게
  (윙: 사유에 '광고' → 광고비 · 빠른정산 사용액 → 빠른정산 계좌인출액(D-312 ①) · 성장 대출 → 위탁자 본인 차감 · 나머지 = 기타 ·
  지급 끝난 음수 회차 = 3PM 되돌림(D-304·D-319) / 로켓그로스: 광고·밀크런·빠른정산·MCA·체크카드·물류비·보상 칸 · 추가 공제 나머지 = 기타).
  다만 정액 3종 중 세이버 구독료·비즈니스 인사이트(로켓그로스 칸)는 기타에서 따로 뺀다(D-271).
- 관리 몫 규칙(지금 결정):
  - 광고비 = 날짜×캠페인 청구가능액 × 그날 광고 보고서 옵션 광고비 비율 × 1.1(D-140·D-119 · ⑦ ratio_src '광고 보고서').
  - 밀크런 = 밀크런마다 입고 건 적치 수량 비율(D-140 · 관리 시작 전달부터 D-154 · ratio_src '입고 적치').
  - 위 두 항목의 상품 자료 없는 공제 = 공제 받은 줄 판매 기간의 관리 정산금 비율(D-162) · 판매 0인 달 = 0(D-186).
  - 판매자서비스이용료·세이버 구독료·비즈니스 인사이트 = 그 달 등록상품 ID 중 관리 상품 수 ÷ 전체(판매중지 포함 · D-271).
    '그 달' = 공제 받은 줄의 판매 기간 시작 달 · 등록 = 상품조회 등록일(createdOn) ≤ 그 달 말일(삭제된 상품은 자료에 없음 → 확인 사항).
  - 그 밖의 계정 공통 비용(기타·보류·3PM·정액보류·채권추심 등) = 줄마다 판매 비중(관리 정산금 비율)과 등록 비중 중 작은 쪽(D-237·D-241 ⑨).
  - 위탁자 본인 차감 = 0(D-312 ②) · 물류비·재고 보상 = 상품별 비용(`ledger_statement.costs`)이라 여기서 다루지 않음.
- 관리 정산금 비율 = 정산 파일 주문 줄(확정분)의 (판매 방식, 쿠팡 정산 기준 날짜 달) 관리 정산 ÷ 전체 정산 — 정산 예정분 나누기
  (D-266·D-269)는 넣지 않음(그 달 확정 줄이 없으면 계정 전체 관리 정산 비율).
결과 = {"items": {항목: {"D": 계정 전체, "due": 관리 시작 뒤, "m": 관리 몫, "rule": 규칙, "note": 설명}}, "lines": …, "reg": …}.
"""
from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict

from . import settlement_managed_alloc as MA
from .ledger_src import RATIO_AD, RATIO_INBOUND, RATIO_REG
from .ledger_statement import _in_scope, _mine, _order_lines, _returns, _ship_kinds
from .settlement_statement_account import month_add

# 항목 이름 = 현행 정산서 코드(master `settlement_statement_account.py` D-312·D-304 반영본)와 같은 글자(대조용 · 이 브랜치의 옛 사본엔 일부 없음)
AD, LOGI, MILK, SVC, ETC, COMP, REL, FAST = ("광고비", "로켓그로스 물류비(입출고·배송·보관·반품)", "밀크런(창고 입고 운송비)",
                                             "판매자서비스이용료", "기타 공제", "재고 분실·파손 보상(쿠팡이 줌)", "보류됐다 풀린 돈",
                                             "빠른정산 계좌인출액")
PM3, OWN = "3PM_매출채권", "위탁자 본인 차감"
OWN_LOAN, OWN_MCA, OWN_CARD = f"{OWN} — 성장 대출", f"{OWN} — MCA 상환", f"{OWN} — 체크카드 대금"
WING_KEY = {"빠른정산 사용액": FAST, "쿠팡 판매자 성장 대출": OWN_LOAN}

SUB, BI = "세이버 구독료", "비즈니스 인사이트"
FLAT = (SVC, SUB, BI)                                  # D-271 정액 3종
OWN_KEYS = (OWN_LOAN, OWN_MCA, OWN_CARD)
RG_COL = {AD: "totalAdSalesDeductionAmount", MILK: "totalMilkRunDeductionAmount", FAST: "totalArFactoringDeductionAmount",
          OWN_MCA: "totalMerchantCashAdvanceDeductionAmount", OWN_CARD: "totalDebitCardDeductionAmount",
          SUB: "totalSubscriptionFeeDeductionAmount", BI: "totalBusinessInsightsDeductionAmount"}
RG_ADD, RG_ADJ = "totalAdditionalDeductionAmount", "totalSalesAdjustment"
RG_LOGI, RG_COMP = "totalFinalCfsFeeDeductionAmount", "totalCfsInventoryCompensationAmount"
CH = {"윙": "윙", "로켓그로스": "로켓그로스"}


def _entries(con: sqlite3.Connection, aid: str) -> dict:
    """(판매 방식, 회차 KEY) → {항목: 금액(원문 부호 — 장부는 '지급 구성' 공제를 음수로 둠 → 되돌림)}."""
    out: dict = defaultdict(Counter)
    for st, rk, item, role, amt in con.execute(
            "SELECT sale_type, round_key, item, role, amount FROM account_entry WHERE account_id=?", (aid,)):
        out[(st, rk)][item] += -amt if role == "지급 구성" else amt
    return out


def deduct_lines(con: sqlite3.Connection, aid: str) -> list:
    """[(판매 방식, 판매 기간 시작 달, 상태, 공제 Counter(+ = 빠지는 돈), 보류 해제액)] — 현행 `deductions()` 와 같은 묶음 + 정액 3종 따로."""
    ent = _entries(con, aid)
    out = []
    q = ("SELECT sale_type, round_key, period_start, status, release, payable, pending FROM pay_round "
         "WHERE account_id=? ORDER BY settle_date, round_key")
    for st, rk, ps, status, release, payable, pending in con.execute(q, (aid,)):
        e, parts = ent.get((st, rk), Counter()), Counter()
        if st == "윙":
            for item, x in e.items():
                if item.startswith("차감 "):
                    why = item[3:]
                    parts[AD if "광고" in why else WING_KEY.get(why, why)] += x
            rest = e.get("totalDeductionAmount", 0) - sum(parts.values())
            if rest:
                parts[ETC] += rest
            pay, rel = (0 if release else (payable or 0)), (pending or 0)
            neg = pay + rel - sum(parts.values())
            if status == "DONE" and neg < 0:
                parts[PM3] += neg
        else:
            rel = 0
            for k, col in RG_COL.items():
                parts[k] += e.get(col, 0)
            parts[ETC] += e.get(RG_ADD, 0) - sum(parts.values()) - e.get(RG_ADJ, 0)
            parts[LOGI] += e.get(RG_LOGI, 0)
            parts[COMP] -= e.get(RG_COMP, 0)
        out.append((st, ps[:7], status, Counter({k: v for k, v in parts.items() if v}), rel))
    return out


def settle_ratio(con: sqlite3.Connection, aid: str, sc: dict) -> dict:
    """(판매 방식, 달) → [관리 정산, 전체 정산] — 정산 파일 주문 줄(확정분) · 달 = 정산 기준 날짜 달 · 관리 = 관리 시작·계약 달 이후 관리 줄."""
    rows = _order_lines(con, aid)
    kinds = _ship_kinds(rows, _returns(con, aid), sc)
    out: dict = defaultdict(lambda: [0, 0])
    for st, order, _ik, _tx, opt, pid, day, _s, _c, _f, settle in rows:
        if not day:
            continue
        m = out[(st, day[:7])]
        m[1] += settle
        mine = _mine(sc, opt, pid) if opt else kinds.get((st, order), set()) == {True}
        if mine and _in_scope(sc, day):
            m[0] += settle
    return dict(out)


def reg_ratio(con: sqlite3.Connection, aid: str, sc: dict) -> dict:
    """달 → (관리 등록상품 수, 전체 등록상품 수) — 상품조회 등록일 ≤ 그 달 말일(판매중지 포함 D-271) · 관리 = 옵션이 관리 옵션이거나
    등록상품이 관리 등록상품. 키 = 등록일이 있는 달 ~ 오늘 쓰는 달(호출 쪽이 고름)."""
    prods: dict = {}
    for inv, opt, day in con.execute("SELECT link_key, option_id, day FROM ratio_src WHERE account_id=? AND kind=?", (aid, RATIO_REG)):
        p = prods.setdefault(inv, [day, False])
        p[0] = min(p[0], day) if day else p[0]
        p[1] = p[1] or opt in sc["mopts"] or inv in sc["mpids"]
    return {"prods": prods}


def reg_share(reg: dict, ym: str) -> tuple:
    n = [(m, d) for d, m in reg["prods"].values() if d and d[:7] <= ym]
    return sum(1 for m, _ in n if m), len(n)


def _have(con: sqlite3.Connection, aid: str) -> set:
    q = "SELECT path FROM src_file WHERE account_id=? AND kind LIKE '광고 보고서%' AND status='반영'"
    return {p.rsplit("_", 1)[-1][:6] for (p,) in con.execute(q, (aid,))}


def ad_amounts(con: sqlite3.Connection, aid: str, sc: dict, since: str):
    """광고 상품 자료 몫 = MA.ad_share(현행 정산서와 같은 계산) · 입력 = ratio_src '광고 보고서' + account_entry '광고 청구가능'."""
    pa = [(d.replace("-", ""), camp, opt, val) for d, camp, opt, val in con.execute(
        "SELECT day, link_key, option_id, value FROM ratio_src WHERE account_id=? AND kind=?", (aid, RATIO_AD)) if d and camp]
    bill: Counter = Counter()
    for d, camp, amt in con.execute("SELECT occur_date, link_key, amount FROM account_entry WHERE account_id=? "
                                    "AND item LIKE '광고 청구가능%'", (aid,)):
        if d[:7] >= since:
            bill[(int(d.replace("-", "")), camp)] += -amt
    return MA.ad_share(pa, dict(bill), lambda v: v in sc["mopts"], _have(con, aid))


def milk_amounts(con: sqlite3.Connection, aid: str, sc: dict, since: str):
    """밀크런 상품 자료 몫 = MA.milk_share · 밀크런 금액 = 총 합계금액 + 취소수수료(파일 달 ≥ since) · 입고 = ratio_src '입고 적치'."""
    q = ("SELECT e.link_key, e.amount, f.path FROM account_entry e JOIN src_file f USING(file_id) "
         "WHERE e.account_id=? AND e.item IN ('밀크런 총 합계금액', '밀크런 취소수수료') ORDER BY e.file_id, e.src_pos")
    rows: Counter = Counter()
    for seq, amt, path in con.execute(q, (aid,)):
        if path.rsplit("_", 1)[-1][:6] >= since.replace("-", ""):
            rows[seq] += -amt
    inbound: dict = {}
    for seq, opt, qty, flag in con.execute("SELECT link_key, option_id, value, flag FROM ratio_src WHERE account_id=? AND kind=?",
                                           (aid, RATIO_INBOUND)):
        s = inbound.setdefault(seq, {"milkrunSeq": seq, "cancelled": bool(flag), "skus": []})
        s["skus"].append({"vendorItemId": opt, "stowedQty": qty})
    return MA.milk_share(list(rows.items()), list(inbound.values()), lambda v: v in sc["mopts"])


def account_values(con: sqlite3.Connection, aid: str, sc: dict, fs: str) -> dict:
    """계정 하나 → 항목별 계정 전체·관리 시작 뒤·관리 몫. sc = `ledger_statement.with_products()` 결과 · fs = 관리 첫 판매 달(D-186)."""
    lines = deduct_lines(con, aid)
    sr = settle_ratio(con, aid, sc)
    tot = [sum(v[0] for v in sr.values()), sum(v[1] for v in sr.values())]
    S = tot[0] / tot[1] if tot[1] else 0.0

    def r_sales(ch: str, ym: str) -> float:
        m, a = sr.get((ch, ym), (0, 0))
        return m / a if a else S
    reg = reg_ratio(con, aid, sc)

    def r_reg(ym: str) -> float:
        m, a = reg_share(reg, ym)
        return m / a if a else 0.0
    start = sc["start"]
    D: Counter = Counter()
    for _ch, _ym, _st, parts, rel in lines:
        D.update(parts)
    dl = [(ch, ym, parts) for ch, ym, _st, parts, _r in lines]

    def due(k: str, since: str) -> float:
        return sum(p.get(k, 0) for _c, ym, p in dl if ym >= since)

    def lshare(k: str, since: str, rate) -> float:
        d = due(k, since)
        return sum(p.get(k, 0) * rate(c, ym) for c, ym, p in dl if ym >= since) / d if d else 0.0
    items: dict = {}

    def product_item(k: str, since: str, got, f_since: str, got_f, how: str) -> None:
        """현행 `Account.put()` 와 같은 순서 — 상품 자료 몫(scoped) + 자료 없는 공제 × 줄 비율 · 판매 0인 달 뺌(gap_free · D-186)."""
        a_m, a_t, note = got if got else (0.0, 0.0, "")
        d = due(k, since)
        if f_since > since:
            fm, ft = (got_f[0], got_f[1]) if got_f else (0.0, 0.0)
            amt, miss = MA.gap_free(a_m, fm, ft, due(k, f_since), lshare(k, f_since, r_sales))
        else:
            amt, miss = MA.scoped(a_m, d, a_t)
            amt += miss * lshare(k, since, r_sales)
        items[k] = {"D": D.get(k, 0), "due": d, "m": amt, "rule": "D-140·D-162·D-186", "note": f"{how} · 상품 자료 {a_t:,.0f}원 중 관리 {a_m:,.0f}원"
                    + (f" · 상품 자료 없는 {miss:,.0f}원 = 줄 판매 기간 관리 정산 비율" if round(miss) else "") + (f" · {note}" if note else "")}

    def x11(g):
        return (g[0] * 1.1, g[1] * 1.1, g[2]) if g else None
    f_ad = max(fs, start)
    ad = x11(ad_amounts(con, aid, sc, start))
    product_item(AD, start, ad, f_ad, x11(ad_amounts(con, aid, sc, f_ad)) if f_ad > start else ad, "광고 보고서 옵션 비율 × 1.1")
    mk_since, mk_f = month_add(start, -1), month_add(f_ad, -1)
    mk = milk_amounts(con, aid, sc, mk_since)
    product_item(MILK, mk_since, mk, mk_f, milk_amounts(con, aid, sc, mk_f) if mk_f > mk_since else mk,
                 "입고 적치 수량 비율(관리 시작 전달부터 D-154)")
    for k in FLAT:
        if D.get(k):
            m = sum(p.get(k, 0) * r_reg(ym) for _c, ym, p in dl if ym >= start)
            items[k] = {"D": D[k], "due": due(k, start), "m": m, "rule": "D-271", "note": "그 달 등록상품 ID 중 관리 상품 수 ÷ 전체(판매중지 포함)"}
    for k in sorted(set(D) - set(items) - {LOGI, COMP}):
        if k in OWN_KEYS:
            items[k] = {"D": D[k], "due": due(k, start), "m": 0.0, "rule": "D-312 ②", "note": "위탁자 본인 차감 — 관리 몫 0"}
            continue
        f_since = max(fs, start)
        m = sum(p.get(k, 0) * min(r_sales(c, ym), r_reg(ym)) for c, ym, p in dl if ym >= f_since)
        items[k] = {"D": D[k], "due": due(k, start), "m": m, "rule": "D-237·D-241 ⑨·D-186",
                    "note": "줄 판매 기간 관리 정산 비율과 등록 비율 중 작은 쪽"}
    regm = {ym: reg_share(reg, ym) for ym in sorted({ym for _c, ym, _p in dl})}
    return {"items": items, "S": S, "ratio": {f"{c}|{ym}": v for (c, ym), v in sr.items()}, "reg": regm,
            "lines": [(c, ym, st, dict(p), rel) for c, ym, st, p, rel in lines], "fs": fs}
