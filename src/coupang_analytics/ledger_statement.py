"""장부 DB(시험본) → 위탁정산서 숫자(관리 상품 몫) — 계획 5절 · 4단계 1차 = 정산 확정분 + 상품별 비용.

- 관리 상품 범위 = `tools/ledger_scope_export.py` 결과 json(기존 정산서 코드의 is_mv · 관리 시작 달 · 계약일 — 판정표 = 입력 폴더).
  범위를 정하지 못한 계정(오류·판정 대기·못 정한 상품 있음)은 '관리 상품 확인 필요'로 표시하고 숫자는 그대로 낸다(가리지 않음).
- 관리 = 등록상품 단위(D-116 ① "관리 VID 가 있는 등록상품은 상품 전체를 관리") — 줄의 등록상품(윙 상품ID · 로켓그로스 등록상품ID =
  inventory_id 칸 · 비용 리포트도 같은 칸)이 관리 옵션의 등록상품이면 관리 · 등록상품 칸 없는 줄은 옵션으로(관리 옵션 + 그 등록상품의 옵션).
- 정산 확정분 = 정산 파일 주문 줄(② order_line · 윙 주문상세 / 로켓그로스 판매수수료) 중 관리 줄 · 달 = 쿠팡 정산 기준 날짜(윙 구매확정일 ·
  로켓그로스 매출인식일)의 달(D-266 ③) · 관리 시작 달 이후(D-154·D-185) · 계약 시작일 달 앞 판매 뺌(D-185 ② — 달 단위 · 날짜 단위 아님).
  배송비 줄(옵션 없음) = 같은 주문의 상품 줄이 모두 관리면 관리 · 섞이면 '배송비 섞인 주문'으로 따로 셈(금액에 넣지 않음 · 확인 필요).
  같은 주문에 상품 줄이 없으면 반품 조회(④ '반품 조회 옵션' 주문>옵션)의 상품을 따라감(D-116 ②) · 반품 조회도 없으면
  '배송비 상품 못 찾음'으로 따로 셈(금액에 넣지 않음 · 비율로 나누지 않음 D-146).
- 상품별 비용(③ product_cost) = 관리 옵션 줄 그대로(VAT 별도) + 세액 = 그 계정·정산주기·종류의 쿠팡 세액(④ '비용 세액 …')을 상세 줄 금액 비율로
  나눈 값(쿠팡 자료 비율 D-153 ①) · 달 = 정산주기 끝 날짜의 달.
- 반출 배송 서비스비(④ 계정 내역 · 고리 = '반출ID>대표 등록상품 ID' · 박스 단위) = 대표 등록상품(없으면 같은 반출ID 의 반출비
  상품 줄 ③)이 모두 관리면 관리 몫 ·
  섞이거나 못 찾으면 금액 밖 '확인 필요'(목록 4번째 칸 · 비율로 나누지 않음 D-146).
- 계정 단위 값(광고·밀크런·서비스이용료·기타 공제·정산 예정분)은 이 1차에 없음 — 2차(D-236·D-241·D-262·D-266)에서.
결과 = {계정ID: {"status", "check", "months": {YYYY-MM: {...}}, "total": {...}}} — 숫자는 원 단위 정수.
"""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

SETTLE_SRC = ("주문상세", "판매수수료")
COST_TAX_PREFIX = "비용 세액 "
OUTBOUND_SHIP = "반출 배송 서비스비 리포트"     # ④ 계정 내역 item(박스 단위 · link_key = 반출ID)
OUTBOUND_KIND = "반출비"                        # ③ 같은 반출의 상품 줄(nat_key 에 '반출ID=')
CONF_KEYS = ("gross", "refund", "ship", "sales", "coupon", "fee", "settle", "ship_mixed", "ship_unknown", "ship_fee")
RETURN_ITEM = "반품 조회 옵션"


def load_scope(path: Path) -> dict:
    """scope json → {계정ID: {"ok", "managed": set, "start": 'YYYY-MM', "cdate": 'YYYY-MM-DD'|'' , "check": [사유]}}."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))["accounts"]
    out = {}
    for aid, r in raw.items():
        if r.get("status") != "ok":
            out[aid] = {"ok": False, "managed": set(), "start": "", "cdate": "", "check": [str(r.get("status"))]}
            continue
        check = []
        if r["scope_check"]:
            check.append(f"못 정한 상품 {r['scope_check']}개")
        if not r["managed"]:
            check.append(f"관리 옵션 0 ({r['scope']})")
        out[aid] = {"ok": True, "managed": set(r["managed"]), "start": str(r["start"] or "")[:7],
                    "cdate": str(r["cdate"] or "")[:10], "check": check, "scope": r["scope"]}
    return out


def _month_in(sc: dict, ym: str) -> bool:
    """관리 시작 달 이후 · 계약 시작일 달 앞 뺌(D-154·D-185 ② "계약 시작일 달 앞의 관리 상품 판매는 뺀다" — 달 단위)."""
    return ym >= sc["start"] and (not sc["cdate"] or ym >= sc["cdate"][:7])


def _in_scope(sc: dict, day: str) -> bool:
    return bool(day) and _month_in(sc, day[:7])


def products(con: sqlite3.Connection, aid: str, managed: set) -> tuple:
    """(관리 등록상품 집합, 관리 옵션 집합) — 옵션 → 등록상품 짝 = 정산 파일 주문 줄 + 비용 리포트 줄(현행 정산서 opt2pid·cost_opts 와 같은 출처)."""
    o2p: dict = defaultdict(set)
    q = (f"SELECT option_id, product_id, inventory_id FROM order_line WHERE account_id=? AND option_id<>'' "
         f"AND src IN ({','.join('?' * len(SETTLE_SRC))}) UNION SELECT option_id, '', inventory_id FROM product_cost "
         f"WHERE account_id=? AND option_id<>''")
    for opt, pid, inv in con.execute(q, (aid, *SETTLE_SRC, aid)):
        if pid or inv:
            o2p[opt].add(pid or inv)
    mpids = {p for o in managed for p in o2p.get(o, ())}
    return mpids, set(managed) | {o for o, ps in o2p.items() if ps & mpids}


def _mine(sc: dict, opt: str, pid: str) -> bool:
    """관리 줄? — 등록상품 칸 있으면 등록상품으로 · 없으면 옵션으로(D-116 ①)."""
    return pid in sc["mpids"] if pid else opt in sc["mopts"]


def _order_lines(con: sqlite3.Connection, aid: str):
    q = (f"SELECT sale_type, order_no, item_key, txn_type, option_id, COALESCE(NULLIF(product_id, ''), inventory_id), "
         f"recognized, sales, coupon, fee, settle "
         f"FROM order_line WHERE account_id=? AND src IN ({','.join('?' * len(SETTLE_SRC))})")
    return con.execute(q, (aid, *SETTLE_SRC)).fetchall()


def _returns(con: sqlite3.Connection, aid: str) -> dict:
    """주문번호 → {반품 조회 옵션ID} — 상품 줄 없는 배송비 주문의 상품 찾기(D-116 ②)."""
    out: dict = defaultdict(set)
    q = "SELECT link_key FROM account_entry WHERE account_id=? AND item=?"
    for (lk,) in con.execute(q, (aid, RETURN_ITEM)):
        order, _, opt = lk.partition(">")
        out[order].add(opt)
    return out


def _ship_kinds(rows: list, ret: dict, sc: dict) -> dict:
    """(판매방식, 주문) → {관리 여부} — 같은 주문 상품 줄 · 없으면 반품 조회 상품(D-116 ②)."""
    kinds: dict = defaultdict(set)
    for st, order, _ik, _tx, opt, pid, *_r in rows:
        if opt:
            kinds[(st, order)].add(_mine(sc, opt, pid))
    for st, order, _ik, _tx, opt, *_r in rows:
        if not opt and (st, order) not in kinds and order in ret:
            kinds[(st, order)] = {o in sc["mopts"] for o in ret[order]}
    return kinds


def confirmed(con: sqlite3.Connection, aid: str, sc: dict) -> dict:
    """{달: {gross·refund·ship·sales·coupon·fee·settle·ship_mixed·ship_unknown}} — 관리 몫 정산 확정분."""
    rows = _order_lines(con, aid)
    kinds = _ship_kinds(rows, _returns(con, aid), sc)
    out: dict = defaultdict(lambda: dict.fromkeys(CONF_KEYS, 0))
    for st, order, _ik, _tx, opt, pid, day, sales, coupon, fee, settle in rows:
        if not _in_scope(sc, day):
            continue
        m = out[day[:7]]
        if opt:
            if not _mine(sc, opt, pid):
                continue
            m["gross" if sales >= 0 else "refund"] += sales
        else:                                    # 배송비 줄
            k = kinds.get((st, order), set())
            if k != {True}:
                if True in k:
                    m["ship_mixed"] += settle
                elif not k:
                    m["ship_unknown"] += settle
                continue
            m["ship"] += sales
            m["ship_fee"] -= fee
        m["sales"] += sales
        m["coupon"] -= coupon
        m["fee"] -= fee
        m["settle"] += settle
    return dict(out)


def _cost_tax(con: sqlite3.Connection, aid: str) -> dict:
    """(정산주기 끝, 종류) → 쿠팡 세액(음수) — ④ '비용 세액 {종류}' (round_key = 정산주기 끝 가정 아님: occur_date 칸 사용)."""
    out: dict = defaultdict(int)
    q = "SELECT item, round_key, occur_date, amount FROM account_entry WHERE account_id=? AND item LIKE ?"
    for item, rk, occ, amt in con.execute(q, (aid, COST_TAX_PREFIX + "%")):
        out[(occ or rk, item[len(COST_TAX_PREFIX):])] += amt
    return out


def _outbound_products(con: sqlite3.Connection, aid: str) -> dict:
    """반출ID → {(옵션ID, 등록상품)} — 같은 반출의 반출비 상품 줄."""
    out: dict = defaultdict(set)
    q = "SELECT nat_key, option_id, inventory_id FROM product_cost WHERE account_id=? AND kind=?"
    for nk, opt, inv in con.execute(q, (aid, OUTBOUND_KIND)):
        for part in nk.split("|"):
            if part.startswith("반출ID="):
                out[part[len("반출ID="):]].add((opt, inv))
    return out


def _outbound(con: sqlite3.Connection, aid: str, sc: dict, tot: dict, man: dict, unk: dict) -> None:
    """반출 배송 서비스비(계정 내역) → 반출ID 로 반출비 상품 줄을 찾아 모두 관리면 관리 몫 · 섞임/못 찾음 = unk(금액 밖)."""
    link = _outbound_products(con, aid)
    q = "SELECT round_key, amount, link_key FROM account_entry WHERE account_id=? AND item=?"
    for rk, amt, lk in con.execute(q, (aid, OUTBOUND_SHIP)):
        cyc = rk.split(":", 1)[1]
        out_id, _, rep = lk.partition(">")
        prods = {("", p) for p in rep.split(",") if p} or link.get(out_id, set())
        key = (cyc, OUTBOUND_SHIP)
        tot[key] += amt
        if not _in_scope(sc, cyc):
            continue
        mine = {_mine(sc, o, p) for o, p in prods}
        if mine == {True}:
            man[key] += amt
        elif True in mine or not mine:
            unk[key] += amt


def costs(con: sqlite3.Connection, aid: str, sc: dict) -> dict:
    """{달: {종류: [관리 VAT 별도, 관리 세액 나눔, 계정 전체 VAT 별도, 관리 섞임·못 찾음(금액 밖)]}} — 상품별 비용."""
    tot: dict = defaultdict(int)
    man: dict = defaultdict(int)
    unk: dict = defaultdict(int)
    q = "SELECT kind, option_id, inventory_id, COALESCE(NULLIF(cycle_end, ''), occur_date), amount FROM product_cost WHERE account_id=?"
    for kind, opt, inv, cyc, amt in con.execute(q, (aid,)):     # 정산주기 끝 없는 줄(라이브 수수료) = 발생일
        tot[(cyc, kind)] += amt
        if _mine(sc, opt, inv) and _in_scope(sc, cyc):
            man[(cyc, kind)] += amt
    _outbound(con, aid, sc, tot, man, unk)
    tax = _cost_tax(con, aid)
    out: dict = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0]))
    for (cyc, kind), t in tot.items():
        m = man.get((cyc, kind), 0)
        x = out[cyc[:7]][kind]
        x[2] += t
        x[3] += unk.get((cyc, kind), 0)
        if not m:
            continue
        x[0] += m
        tx = tax.get((cyc, kind), 0)
        x[1] += round(tx * m / t) if t else 0
    return {ym: {k: list(v) for k, v in d.items()} for ym, d in out.items()}


NO_DATA_CHECKS = {"V4 RG 지급액 = 상품 줄별 × 비율": "RG 정산 파일 없음", "V4 윙 상품 합 = targetAmount": "윙 정산 파일 없음",
                  "V4 RG 비용 = ⑮ 비용 칸": "RG 비용 리포트 없음"}
NO_DATA_RULES = ("R-J7-01 적용", "R-J7-02 적용")


def _months(a: str, b: str) -> list:
    y, m = int(a[:4]), int(a[5:7])
    out = []
    while f"{y:04d}-{m:02d}" <= b[:7]:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def no_data(con: sqlite3.Connection, aid: str, sc: dict) -> dict:
    """{달: [사유]} — 판정 규칙 R-J7-01·02(쿠팡 지급은 있는데 상품별 자료를 받기 전) 회차의 기간 달 중 관리 시작 달 이후.
    이 달은 금액을 0 으로 통과시키지 않고 '자료 없음·확인 필요'(D-146)로 표시한다(계약 시작일 달 앞 달은 D-185 ② 로 뺌)."""
    q = (f"SELECT check_name, subject, expected FROM check_result WHERE account_id=? AND cause IN ({','.join('?' * len(NO_DATA_RULES))}) "
         f"AND check_name IN ({','.join('?' * len(NO_DATA_CHECKS))})")
    out: dict = defaultdict(list)
    for ck, subj, exp in con.execute(q, (aid, *NO_DATA_RULES, *NO_DATA_CHECKS)):
        sale, rest = subj.split(" ", 1)
        p = rest.split("|")
        for ym in _months(p[1], p[2]):
            if _month_in(sc, ym):
                out[ym].append(f"{NO_DATA_CHECKS[ck]} {sale} {p[1]}~{p[2]} {p[3]}% · 쿠팡 계정 전체 {exp:,}원")
    return dict(out)


def with_products(con: sqlite3.Connection, aid: str, sc: dict) -> dict:
    """범위 + 관리 등록상품(mpids)·관리 옵션(mopts) — confirmed·costs 입력."""
    mpids, mopts = products(con, aid, sc["managed"])
    return {**sc, "mpids": mpids, "mopts": mopts}


def account_numbers(con: sqlite3.Connection, aid: str, sc: dict) -> dict:
    sc = with_products(con, aid, sc)
    conf = confirmed(con, aid, sc)
    cost = costs(con, aid, sc)
    nod = no_data(con, aid, sc)
    tot = dict.fromkeys(CONF_KEYS, 0)
    for m in conf.values():
        for k in CONF_KEYS:
            tot[k] += m[k]
    cost_tot: dict = defaultdict(lambda: [0, 0, 0, 0])
    for d in cost.values():
        for k, v in d.items():
            cost_tot[k] = [a + b for a, b in zip(cost_tot[k], v)]
    check = list(sc["check"]) + [f"자료 없음·확인 필요(D-146) {ym}" for ym in sorted(nod)]
    status = "관리 상품 확인 필요" if sc["check"] else ("자료 없음 달 있음" if nod else "ok")
    return {"status": status, "check": check, "start": sc["start"], "cdate": sc["cdate"],
            "months": {ym: {"confirmed": conf.get(ym), "cost": cost.get(ym), "no_data": nod.get(ym)}
                       for ym in sorted(set(conf) | set(cost) | set(nod))},
            "total": {"confirmed": tot, "cost": dict(cost_tot)}}


def build(db: Path, scope_json: Path) -> dict:
    scope = load_scope(scope_json)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    out = {}
    for aid, sc in sorted(scope.items()):
        if not sc["ok"]:
            out[aid] = {"status": "관리 상품 확인 필요", "check": sc["check"]}
            continue
        out[aid] = account_numbers(con, aid, sc)
    con.close()
    return out
