"""위탁자 정산서 3차 형식 — 11 날짜별 입금 · '어디로 갔나요'. T-38 S2(샘플 `s03_compute.py` deposits·_dep_rows 를 나눔 · 계산식·순서 그대로).

날짜별 표 = 이 달 판매 지급 줄의 관리 몫 정산금액(줄 정산금액 × 판매 방식별 관리 비율) − 이 달 비용을 쿠팡이 실제로 뺀 지급 줄의 관리 몫.
빠른정산 = 기존 계산의 지급 줄 공제 항목 '빠른정산'(로켓그로스 AR 상환 + 윙 빠른정산 사용액 · 이미 받은 돈 ±0 · D-312 ①) → '(빠른정산)' 줄.
성장 대출·MCA·체크카드 = 위탁자 본인 차감(관리 몫 0 · D-312 ②) → 이 표에 넣지 않음.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from coupang_analytics import settlement_ledger as SL
from coupang_analytics import settlement_statement_account as AC
from coupang_analytics.settlement_consignor_month_calc import AD_NOCAMP, MonthState, cum_round

FAST = "(빠른정산)"
NO_DATE = "(지급일 미정)"
FAV = "쿠팡페이"
ADD = "쿠팡 추가지급 (10번)"
# 참고 대조 — 줄 공식(지급액 = 정산금액 + 보류 해제 − 공제)에서 '그 줄 정산금액 합'과 다른 쿠팡 원문 금액(T-179 ⑩ · output44 30달 원 단위 설명)
GEN, RELEASE = "지급 줄 생성 전 정산금액(아직 지급 줄 없음)", "보류 해제액(윙 pendingAmount)"
NEGATIVE, EXTRA = "지급 끝난 윙 음수 최종 회차(0 지급 · 다음 회차 3PM 회수 D-304)", "윙 추가지급 줄(10번 · D-308 ①)"


def _channel_ratio(st: MonthState) -> dict:
    r_ch = {}
    for ch in ("윙", "로켓그로스"):
        tot = sum(c for p, c in st.settle_by_ch[ch].items())
        man = sum(c for p, c in st.settle_by_ch[ch].items() if st.is_m(p))
        r_ch[ch] = man / tot if tot else 0.0
    return r_ch


def hold_release_notes(line_info: list, month: str) -> list[str]:
    """윙 보류 해제 지급 줄(보류 해제액 = pendingAmount · 판매 시작 달 = month) → '확인 필요 — 보류 해제 규칙 미확정' 한 줄(21 · T-176 ①).
    해제액을 어느 판매 달 정산 금액에 더할지 규칙이 없음(T-175 후보 대조: 차이 0 후보가 하나로 안 정해짐 · 통제 11-24 D-288 · 추정 금지)
    → 금액은 지금 그대로(해제액 안 더함 · 숫자 지어내지 않음) · 상태 '확인 필요'(out.month_status)."""
    cnt: Counter = Counter()
    amt: Counter = Counter()
    for stt, ch, ym, _pay, rel, _parts, _row in line_info:
        if ch == "윙" and ym == month and round(rel):
            cnt[stt] += 1
            amt[stt] += rel
    if not cnt:
        return []
    order = sorted(cnt, key=lambda s: (AC.STS.index(s) if s in AC.STS else len(AC.STS), s))
    by = " · ".join(f"{s} {cnt[s]}건 {amt[s]:,.0f}원" for s in order)
    return [f"확인 필요 — 보류 해제 규칙 미확정(해제 {sum(cnt.values())}건 · 합 {sum(amt.values()):,.0f}원 · {by}) — "
            "이 달 금액은 해제액을 더하지 않은 지금 값 그대로(규칙 확정 전 · D-288)"]


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
    st.late = AC.late_final_notes(st.d["L_gen"], st.d["v"], st.basis, st.m)    # 정산일 지난 최종액 회차 없음 = 확인 필요(산식 23 · 상태 = out)
    st.hold = hold_release_notes(st.d["line_info"], st.m)                       # 보류 해제 줄 = 확인 필요(21 · T-176 · 상태 = out)
    st.j += st.late + st.hold
    for ch in ("윙", "로켓그로스"):
        tot = sum(st.settle_by_ch[ch].values()) + sum(x["정산"] for x in st.pend_check if x["판매 방식"] == ch)
        st.chk.append({"검사": f"{ch} 이 달 판매 기간 지급 줄 정산금액 합 = 이 달 상품별 정산금액 합(계정 전체 · 확정+예정 · 확인 필요로 뺀 예정분 포함)", "값": [pay_ch[ch], round(tot)],
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
        cat_cost["ad" if cat == AD_NOCAMP else cat] += -ap       # 캠페인 없는 광고 조정 = 광고 공제 지급 줄 위치(신규-01)
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


def _cash_extras(st: MonthState) -> dict:
    """참고 대조에서 '그 줄 정산금액 합'과 실제 지급액 사이의 쿠팡 원문 금액 — 이 달 판매 기간(GEN = 아직 줄 없음 · 나머지 = 지급 줄 칸)."""
    wing = [(row, r) for _key, row, r in st.lines() if str(row[3])[:7] == st.m and r["채널"] == "윙"]
    neg = [AC.num(r.get("최종지급액")) for row, r in wing if row[6].split(" ·")[0] == AC.STS[0]]
    return {GEN: sum(a for (_ch, ym), a in st.d["L_gen"].items() if ym == st.m), RELEASE: sum(x[4] for x in st.d["line_info"] if x[2] == st.m),
            NEGATIVE: sum(x for x in neg if x < 0), EXTRA: sum(AC.num(r.get("최종지급액")) for _row, r in wing if SL.additional(r))}


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
               **_cash_extras(st),
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


def _add_rows(st: MonthState, add_total: int) -> list:
    """10 추가지급 → 날짜별 줄 '쿠팡 추가지급' — 지급 끝(지급일 ≤ 기준일) = 그 날짜 · 그 밖 = '(지급일 미정)'(D-294 ② · T-125 A1)."""
    by: dict = defaultdict(float)
    for day, a in st.add_rows:
        by[day or NO_DATE] += a
    ks = sorted(by)
    return [{"date": dt, "desc": ADD + ("" if dt != NO_DATE else " · 입금 예정"), "amount": a, "_status": "예정" if dt == NO_DATE else "지급 완료"}
            for dt, a in zip(ks, cum_round([by[k] for k in ks], add_total)) if a]


def dep_rows(st: MonthState, net_coupang: int, sep_int: list) -> list:
    """날짜별 표 줄 — 쿠팡 몫(원 단위 누적 반올림 = 정산 금액 − 10) + 쿠팡페이 환급 줄(10 우대수수료 2줄) + 쿠팡 추가지급 줄(10 셋째 줄)."""
    by: dict = defaultdict(float)
    for (dt, stt, _kind), a in st.dep_raw.items():
        by[(dt, stt)] += a
    for _cat, a in st.unlocated.items():
        by[(NO_DATE, "예정")] -= a
    keys = sorted(by, key=lambda k: (k[0].startswith("("), k[0]))
    fdates = sorted(set(st.fast["지급일"]))
    rows = [{"date": dt, "desc": _dep_desc(dt, stt, a, fdates), "amount": a, "_status": stt}
            for (dt, stt), a in zip(keys, cum_round([by[k] for k in keys], net_coupang)) if a]
    rows += _fav_rows(st, sum(a for _, a in sep_int[:2])) + _add_rows(st, sep_int[2][1])
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
