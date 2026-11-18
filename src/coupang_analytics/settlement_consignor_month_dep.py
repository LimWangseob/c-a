"""위탁자 정산서 3차 형식 — 11 날짜별 입금 · '어디로 갔나요'. T-38 S2(샘플 `s03_compute.py` deposits·_dep_rows 를 나눔 · 계산식·순서 그대로).

날짜별 표 = 이 달 판매 지급 줄의 관리 몫 정산금액(줄 정산금액 × 판매 방식별 관리 비율) − 이 달 비용을 쿠팡이 실제로 뺀 지급 줄의 관리 몫.
빠른정산 = 기존 계산의 지급 줄 공제 항목 '빠른정산'(로켓그로스 AR 상환 + 윙 빠른정산 사용액 · 이미 받은 돈 ±0 · D-312 ①) → '(빠른정산)' 줄.
성장 대출·MCA·체크카드 = 위탁자 본인 차감(관리 몫 0 · D-312 ②) → 이 표에 넣지 않음.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from coupang_analytics import settlement_statement_account as AC
from coupang_analytics.settlement_consignor_month_calc import MonthState, cum_round

FAST = "(빠른정산)"
NO_DATE = "(지급일 미정)"
FAV = "쿠팡페이"


def _channel_ratio(st: MonthState) -> dict:
    r_ch = {}
    for ch in ("윙", "로켓그로스"):
        tot = sum(c for p, c in st.settle_by_ch[ch].items())
        man = sum(c for p, c in st.settle_by_ch[ch].items() if st.is_m(p))
        r_ch[ch] = man / tot if tot else 0.0
    return r_ch


def _pay_items(st: MonthState, r_ch: dict) -> list:
    items = []
    pay_ch: Counter = Counter()
    for stt, ch, ym, pay, _rel, _parts, row in st.d["line_info"]:
        if ym == st.m:
            items.append(((row[2], row[3], row[4], ch, row[5]), stt, pay * r_ch[ch]))
            pay_ch[ch] += pay
    for (ch, ym), amt in st.d["L_gen"].items():
        if ym == st.m and amt:
            items.append(((NO_DATE, ym, "", ch, ""), "예정", amt * r_ch[ch]))
            pay_ch[ch] += amt
    for ch in ("윙", "로켓그로스"):
        tot = sum(st.settle_by_ch[ch].values())
        st.chk.append({"검사": f"{ch} 이 달 판매 기간 지급 줄 정산금액 합 = 이 달 상품별 정산금액 합(계정 전체 · 확정+예정)", "값": [pay_ch[ch], round(tot)],
                       "차이": round(pay_ch[ch] - tot)})
    st.pay_ch = pay_ch
    return items


def _fast_moves(st: MonthState, dep: Counter, status: dict, r_ch: dict, k: float) -> None:
    """빠른정산 상환(이 달 판매 지급 줄 · 이미 먼저 받은 돈) → 그 날짜 줄에서 빼고 '(빠른정산)' 줄로."""
    for key, row, r, parts in st.line_parts():
        if str(row[3])[:7] != st.m:
            continue
        a = parts.get(AC.FAST, 0.0)
        if round(a):
            am = k * a * r_ch[r["채널"]]
            dep[(key[0], status.get(key, "?"), "fast")] -= am
            dep[(FAST, "빠른정산", "fast")] += am
            st.fast["계정 전체"] += a
            st.fast["관리 몫"] += am
            st.fast["지급일"].append(str(row[2]))


def _cost_locs(st: MonthState, dep: Counter, status: dict, lines8: dict, applied: list) -> None:
    """비용 = 분류마다 쿠팡이 실제로 뺀 지급 줄 비율로 나눔 · 아직 안 뺀 몫 = 날짜 미정 예정."""
    cat_cost: Counter = Counter()
    for cat, no in (("ad", 5), ("cfs", 6), ("milk", 7), ("comp", 8)):
        cat_cost[cat] = -lines8[no]
    for (_n, _a, cat), ap in zip(st.common_items, applied):
        cat_cost[cat] += -ap
    st.unlocated = Counter()
    for cat, cost in cat_cost.items():
        if not round(cost):
            continue
        locs = st.loc.get(cat) or []
        coupang_total = st.coupang_cat.get(cat, 0.0)
        located = sum(a for _, a in locs)
        frac = located / coupang_total if coupang_total else 0.0
        frac = min(frac, 1.0) if frac >= 0 else 0.0
        for key, a in locs:
            dep[(key[0], status.get(key, "?"), "cost:" + cat)] -= cost * frac * (a / located if located else 0)
        if abs(1 - frac) > 1e-9:
            st.unlocated[cat] += cost * (1 - frac)


def deposits(st: MonthState, lines8: dict, applied: list) -> None:
    r_ch = _channel_ratio(st)
    items = _pay_items(st, r_ch)
    E_m = lines8["E"]
    wsum = sum(x[2] for x in items)
    status = {key: row[6].split(" ·")[0] for key, row, _r in st.lines()}
    dep: Counter = Counter()
    for key, stt, w in items:
        dep[(key[0], stt, "in")] += E_m * w / wsum if wsum else 0.0
        status.setdefault(key, stt)
    _fast_moves(st, dep, status, r_ch, E_m / wsum if wsum else 0.0)
    _cost_locs(st, dep, status, lines8, applied)
    st.dep_raw = dep
    _cash_reference(st)


def _cash_reference(st: MonthState) -> None:
    """참고 대조: 이 달 판매 기간 지급 줄의 실제 지급액(계정 전체) ↔ 이 정산서 쿠팡 몫(별도 입금 뺀 금액)."""
    sept = {key for key, row, _r in st.lines() if str(row[3])[:7] == st.m}
    actual = sum(AC.num(r.get("최종지급액")) for key, _row, r in st.lines() if key in sept)
    parts: Counter = Counter()
    for _s, _ch, ym, _pay, _rel, pt, _row in st.d["line_info"]:
        if ym == st.m:
            parts.update(pt)
    etc = parts.pop(AC.ETC, 0.0)
    located = [(key, a) for ls in st.loc.values() for key, a in ls]
    on_sept = sum(a for key, a in located if key in sept)
    off_sept = sum(a for key, a in located if key not in sept)
    st.cash = {"이 달 판매 기간 지급 줄 실제 지급액 합(계정 전체)": actual, "그 줄 정산금액 합": sum(st.pay_ch.values()),
               "그 줄에서 빠진 공제(판매 조정 제외)": sum(parts.values()), "그중 이 달 비용": on_sept,
               "다른 달 비용(이 달 줄에서 빠짐)": sum(parts.values()) - on_sept,
               "이 달 비용이 다른 달 판매 기간 줄에서 빠짐": off_sept, "판매 조정·음수 공제(환불 회수 · 날짜만 옮김)": etc}


def _dep_desc(dt: str, stt: str, a: int, fdates: list) -> str:
    if dt == FAST:
        return f"빠른정산으로 먼저 받은 돈 (쿠팡이 {' · '.join(x[5:] for x in fdates)} 지급에서 상환으로 뺌)"
    if dt == NO_DATE:
        return "이 달 비용 중 쿠팡이 아직 안 뺀 금액 (다음 지급에서 빠질 예정)"
    if stt == "지급 완료":
        return "쿠팡 입금 완료" if a > 0 else "이 달 비용을 쿠팡이 이 날 지급에서 뺌"
    return "쿠팡 입금 예정 (쿠팡 일정)" if a > 0 else "이 달 비용을 쿠팡이 이 날 지급에서 뺄 예정"


def _fav_rows(st: MonthState, sep_total: int) -> list:
    fav: dict = defaultdict(float)
    for dt, ts, a in st.fav_rows:
        fav[(dt, ts)] += a
    fk = sorted(fav)
    rows = []
    for (dt, ts), a in zip(fk, cum_round([fav[k] for k in fk], sep_total)):
        if a:
            done = ts == "TRANSFER_COMPLETE"
            rows.append({"date": dt, "desc": f"{FAV} 우대수수료 환급 (대표 계좌)" + ("" if done else " · 예정"), "amount": a,
                         "_status": "지급 완료" if done else "예정"})
    return rows


def dep_rows(st: MonthState, net_coupang: int, sep_int: list) -> list:
    """날짜별 표 줄 — 쿠팡 몫(원 단위 누적 반올림 = 정산 금액 − 10) + 쿠팡페이 환급 줄(10)."""
    by: dict = defaultdict(float)
    for (dt, stt, _kind), a in st.dep_raw.items():
        by[(dt, stt)] += a
    for _cat, a in st.unlocated.items():
        by[(NO_DATE, "예정")] -= a
    keys = sorted(by, key=lambda k: (k[0].startswith("("), k[0]))
    fdates = sorted(set(st.fast["지급일"]))
    rows = [{"date": dt, "desc": _dep_desc(dt, stt, a, fdates), "amount": a, "_status": stt}
            for (dt, stt), a in zip(keys, cum_round([by[k] for k in keys], net_coupang)) if a]
    rows += _fav_rows(st, sum(a for _, a in sep_int))
    rows.sort(key=lambda r: (r["date"].startswith("("), r["date"]))
    return rows


def _flow_plan(plan: list) -> dict:
    dates = sorted({r["date"] for r in plan if not r["date"].startswith("(")})
    return {"name": "쿠팡 입금 예정", "desc": (" · ".join(d[5:] for d in dates) + " 입금 예정 (쿠팡 일정)") if dates else "쿠팡 일정",
            "amount": sum(r["amount"] for r in plan)}


def _flow_parts(rows: list) -> tuple[int, list, int, int]:
    coupang = [r for r in rows if not r["desc"].startswith(FAV)]
    done = sum(r["amount"] for r in coupang if r["_status"] == "지급 완료")
    plan = [r for r in coupang if r["_status"] not in ("지급 완료", "빠른정산")]
    fast = sum(r["amount"] for r in coupang if r["_status"] == "빠른정산")
    favs = sum(r["amount"] for r in rows if r["desc"].startswith(FAV))
    return done, plan, fast, favs


def flow(st: MonthState, rows: list) -> list:
    """'어디로 갔나요' 고정 4줄(값 없으면 0 · D-343) — 입금 완료 · 빠른정산으로 먼저 받음 · 입금 예정 · 쿠팡페이 환급(날짜별 표 줄의 상태로 묶음).
    rows 의 '_status' 는 지움."""
    done, plan, fast, favs = _flow_parts(rows)
    out = [{"name": "쿠팡 입금 완료", "desc": f"{st.basis}까지 쿠팡이 지급한 돈 (이 달 비용 뺀 뒤)", "amount": done},
           {"name": "빠른정산으로 먼저 받음", "desc": "쿠팡 빠른정산으로 미리 받은 돈 (뒤 지급일에 상환으로 빠짐)", "amount": fast},
           _flow_plan(plan),
           {"name": "쿠팡페이 환급", "desc": "대표 계좌로 들어온 우대수수료 환급 (10번)", "amount": favs}]
    for r in rows:
        r.pop("_status")
    return out
