"""위탁정산서 정산 예정분 관리 몫 나누기 — 쿠팡이 계정 합계로만 준 정산 중 판매를 관리 상품 몫으로 나눔(T-63 · D-261 · D-262 · D-264 · D-266 · D-267).

순서(D-262): ① 윙 주문별매출 실제값 → ② 윙 B8+환산 · 로켓그로스 B+환산(D-266 ①) → ③ 관리 비율 0~100% 밖 · 나눌 판매 없음 ·
검산(남은 판매 ÷ 쿠팡 판매) 1.5 이상 = 그 금액만 관리 몫에 넣지 않고 '확인 필요'(정산서는 발행 · D-262 ③ · D-266 ②).
- ① 그 달 `검증자료/월자료/{계정}/주문별매출_YYYYMM.json` 줄 중 구매확정일이 윙 정산 파일 기간 밖인 줄의 합(판매 = productGmv + deliveryGmv ·
  정산 = apAmount)이 쿠팡 예정과 원 단위 같을 때만 · 상품 없는 줄(배송비·취소) = 같은 주문 상품 줄 수 비율(못 찾으면 그 예정분 관리 비율).
- ② 윙 B8: 판매분석 일별 윙 순액(결제일) [그 달 1일−30일, E−8일] − 이미 구매확정된 판매(앞 달 주문별매출 productGmv(결제일) + 그 주문 밖 윙
  정산 파일 줄(한 번만 · 구매확정일에서 결제→구매확정 지연 분포로 결제일에 나눔)) · 옵션 합 뒤 음수 0. E = 예정 판매 기간 끝(기준일 전날 또는 그 달 말일 중 이른 날)
  → 진행 중 달 결제 끝 = 기준일−9일(D-267 — D-266 본문 '기준일−8일' 정정).
  환산 = 옵션별 정산대상/판매(앞 달 주문별매출 · 결제일 ≥ 시작−60일 · 없는 옵션 = 계정 비율 · 계정 비율도 없으면 판매 그대로).
- ② 로켓그로스 B: 예정 판매 주마다 같은 날짜(매출인식일 = 판매분석 일별 날짜 · 당김 0일) 로켓그로스 순액 · 환산 = 판매수수료 정산 파일 최근 70일
  옵션별 정산대상/판매 · 주가 달을 걸치면 날짜의 달로 나눔(그 달 날짜들 판매 비율 · D-266 ③) · 일별 빠진 날 = 확인 필요.
근거 = `output/_분석_261116_예정분나누기/미정산장부_방안.md` 7~8절 · `_scripts/t66_wing.py`·`t66_rg.py`(같은 정의 · 섞인 계정 오차 합 윙 887만).
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from coupang_analytics import settlement_stats as SS

CHECK_MAX = 1.5                       # 검산(남은 판매 ÷ 쿠팡 판매) 이 값 이상 = 확인 필요(D-266 ②)
WING_BACK, WING_CUT, RATE_BACK, RG_RATE_DAYS = 30, 8, 60, 70
WING, RG = "윙", "로켓그로스"


def _d(s) -> date:
    return date.fromisoformat(str(s)[:10])


def _days(a: date, b: date):
    while a <= b:
        yield a
        a += timedelta(days=1)


def gmv(r: dict) -> float:
    return float(r.get("productGmv") or 0) + float(r.get("deliveryGmv") or 0)


def order_months(base: Path, acct: str) -> dict:
    """{YYYYMM: [주문별매출 줄]} — 없으면 빈 사전."""
    d = base / "검증자료" / "월자료" / acct
    if not d.is_dir():
        return {}
    return {p.stem.rsplit("_", 1)[-1]: json.loads(p.read_text(encoding="utf-8")).get("줄") or [] for p in sorted(d.glob("주문별매출_*.json"))}


@lru_cache(maxsize=32)
def lag_pmf(base: str, ym: str) -> tuple:
    """결제→구매확정 지연(일) 분포 — 그 달 앞 모든 계정 주문별매출 주문 줄(상품 있는 줄) · ((일, 비율), …)."""
    c: Counter = Counter()
    for p in Path(base).glob("검증자료/월자료/*/주문별매출_*.json"):
        if p.stem.rsplit("_", 1)[-1] < ym.replace("-", ""):
            for r in json.loads(p.read_text(encoding="utf-8")).get("줄") or []:
                if r.get("transactionType") == "ORDER" and r.get("vendorItemId") is not None:
                    c[(_d(r["confirmDate"]) - _d(r["paidDate"])).days] += 1
    n = sum(c.values())
    return tuple(sorted((k, v / n) for k, v in c.items())) if n else ()


def _conv(pos: dict, rate: dict, acc: float | None, is_mv) -> float:
    """정산대상 환산 뒤 관리 비율 — 옵션 판매 × 옵션 정산대상/판매(없으면 계정 비율 · 그것도 없으면 1)."""
    w = {v: y * rate.get(v, acc if acc is not None else 1.0) for v, y in pos.items()}
    t = sum(w.values())
    return sum(y for v, y in w.items() if is_mv(v)) / t if t else 0.0


def _rates(pairs) -> tuple[dict, float | None]:
    """[(옵션, 판매, 정산대상)] → ({옵션: 정산대상/판매}, 계정 비율)."""
    s: dict = defaultdict(float)
    a: dict = defaultdict(float)
    for v, x, y in pairs:
        s[v] += x
        a[v] += y
    tot = sum(s.values())
    return {v: a[v] / s[v] for v in s if s[v]}, (sum(a.values()) / tot if tot else None)


def _judge(share: float | None, chk: float | None) -> str:
    if share is None:
        return "나눌 판매 없음(그 기간 판매분석 판매 0)"
    if not 0 <= share <= 1:
        return f"관리 비율 {share:.1%} — 0~100% 밖"
    if chk is not None and chk >= CHECK_MAX:
        return f"검산 {chk:.2f} — 남은 판매가 쿠팡 판매의 {CHECK_MAX} 배 이상"
    return ""


# ── ① 윙 주문별매출 실제값 ──
def _ap(r: dict) -> float:
    return float(r.get("apAmount") or 0)


def _order_frac(rows: list, pend: list, is_mv):
    """줄 → 관리 비율 함수 — 상품 줄 = 0/1 · 상품 없는 줄(배송비·취소) = 같은 주문 상품 줄 수 비율(못 찾으면 예정분 관리 비율 · None 표시)."""
    by_o: dict = defaultdict(list)
    for r in rows:
        if r.get("vendorItemId") is not None:
            by_o[str(r["orderId"])].append(is_mv(str(r["vendorItemId"])))
    opt = [r for r in pend if r.get("vendorItemId") is not None]
    tot = sum(gmv(r) for r in opt)
    base_sh = sum(gmv(r) for r in opt if is_mv(str(r["vendorItemId"]))) / tot if tot else 0.0

    def frac(r: dict) -> tuple[float, bool]:
        if r.get("vendorItemId") is not None:
            return (1.0 if is_mv(str(r["vendorItemId"])) else 0.0), True
        o = by_o.get(str(r["orderId"]))
        return (sum(o) / len(o), True) if o else (base_sh, False)
    return frac


def wing_actual(rows: list, periods: list, s: float, e: float, is_mv) -> tuple | None:
    """(관리 판매, 관리 정산, 근거) 또는 None(파일 기간 밖 줄 합이 쿠팡 예정과 원 단위 다름)."""
    pend = [r for r in rows if not any(a <= str(r["confirmDate"])[:10] <= b for a, b in periods)]
    if not pend or round(sum(gmv(r) for r in pend)) != round(s) or round(sum(_ap(r) for r in pend)) != round(e):
        return None
    frac = _order_frac(rows, pend, is_mv)
    got = [(gmv(r), _ap(r), *frac(r)) for r in pend]
    loose = sum(not found for *_x, found in got)
    return (sum(g * f for g, _a, f, _k in got), sum(a * f for _g, a, f, _k in got),
            f"주문별매출 실제값 — 정산 파일 기간 밖 구매확정 {len(pend)}줄(쿠팡 예정과 원 단위 같음)"
            + (f" · 상품 못 찾은 줄 {loose}개 = 예정분 관리 비율" if loose else ""))


# ── ② 윙 B8+환산 ──
def _wing_known(orders: dict, ym: str) -> list:
    return [r for m, rs in orders.items() if m < ym.replace("-", "") for r in rs]


def _wing_sub(known: list, file_rows: list, pmf: tuple, s0: date) -> tuple[dict, bool]:
    """이미 구매확정된 판매 {옵션: {결제일: 금액}} · 지연 분포가 필요한데 없으면 False."""
    kp: dict = defaultdict(lambda: defaultdict(float))
    koids = {str(r["orderId"]) for r in known}
    for r in known:
        if r.get("vendorItemId") is not None:
            kp[str(r["vendorItemId"])][str(r["paidDate"])[:10]] += float(r.get("productGmv") or 0)
    seen = {(str(r.order_id), str(r.option_id), r.sales): r.recognized for r in file_rows
            if r.option_id and r.recognized and str(r.order_id) not in koids and r.recognized >= s0}
    if seen and not pmf:
        return kp, False
    for (_o, vid, sl), rec in seen.items():
        for lag, p in pmf:
            kp[vid][str(rec - timedelta(days=lag))] += sl * p
    return kp, True


def _wing_residual(daily: dict, kp: dict, s0: date, end: date) -> dict:
    """옵션별 남은 판매 = 결제일 [s0, end] 판매분석 일별 윙 순액 − 이미 구매확정 · 옵션 합 뒤 음수 0(빼고 양수만)."""
    res: dict = defaultdict(float)
    for x in _days(s0, end):
        for v, o in ((daily.get(str(x)) or {}).get("옵션") or {}).items():
            if o.get("구분") == WING:
                res[str(v)] += float(o.get("판매금액") or 0)
        for v, k in kp.items():
            res[v] -= k.get(str(x), 0.0)
    return {v: y for v, y in res.items() if y > 0}


def _known_rates(known: list, s0: date) -> tuple[dict, float | None]:
    since = str(s0 - timedelta(days=RATE_BACK))
    return _rates((str(r["vendorItemId"]), float(r.get("productGmv") or 0), _ap(r)) for r in known
                  if r.get("vendorItemId") is not None and str(r["paidDate"])[:10] >= since)


def wing_b8(daily: dict, orders: dict, file_rows: list, pmf: tuple, ym: str, last: date, s: float, e: float, is_mv) -> tuple:
    """(관리 판매, 관리 정산, 근거, 확인 필요 사유)."""
    if s <= 0:
        return 0.0, 0.0, "", "나눌 판매 없음(쿠팡 예정 판매 0 이하 — 주문별매출 실제값 없음)"
    s0 = _d(ym + "-01") - timedelta(days=WING_BACK)
    end = last - timedelta(days=WING_CUT)
    known = _wing_known(orders, ym)
    kp, ok = _wing_sub(known, file_rows, pmf, s0)
    if not ok:
        return 0.0, 0.0, "", "결제→구매확정 지연 자료(주문별매출) 없음"
    pos = _wing_residual(daily, kp, s0, end)
    pt = sum(pos.values())
    share = sum(y for v, y in pos.items() if is_mv(v)) / pt if pt else None
    why = _judge(share, pt / s)
    if why or share is None:
        return 0.0, 0.0, "", why
    rate, acc = _known_rates(known, s0)
    return (s * share, e * _conv(pos, rate, acc, is_mv),
            f"윙 B8+환산 — 결제일 {s0}~{end} 판매분석 일별 − 이미 구매확정 · 남은 판매 {pt:,.0f}(검산 {pt / s:.2f}) 중 관리 {share:.1%}", "")


# ── ② 로켓그로스 B+환산 ──
def _rg_net(daily: dict, a: date, b: date) -> tuple[dict, int]:
    net: dict = defaultdict(float)
    miss = 0
    for x in _days(a, b):
        rec = daily.get(str(x))
        if rec is None:
            miss += 1
            continue
        for v, o in (rec.get("옵션") or {}).items():
            if o.get("구분") == RG:
                net[str(v)] += float(o.get("판매금액") or 0)
    return net, miss


def rg_rates(files: list, last: date) -> tuple[dict, float | None]:
    return _rates((str(r.option_id), r.sales, r.settle) for f in files if f.channel == RG and f.period_end >= last - timedelta(days=RG_RATE_DAYS)
                  for r in f.rows if r.option_id)


def _month_parts(a: date, b: date) -> list:
    out, x = [], a
    while x <= b:
        nxt = date(x.year + (x.month == 12), x.month % 12 + 1, 1)
        out.append((x, min(b, nxt - timedelta(days=1))))
        x = nxt
    return out


def _rg_head(parts: list, sales) -> str:
    """주 전체 검사 — 일별 빠진 날 · 나눌 판매 없음(순액 합 0 이하) · 검산 1.5 이상."""
    miss = sum(m for _p, _n, m in parts)
    if miss:
        return f"판매분석 일별 빠진 날 {miss}일"
    tot = sum(sum(n.values()) for _p, n, _m in parts)
    return _judge(1.0 if tot > 0 else None, tot / sales if sales else None)


def _rg_part(p: tuple, net: dict, frac: float, week: tuple, rates: tuple, is_mv) -> tuple:
    s0, e0, sales, amt = week
    ps, pe = (sales or 0) * frac, amt * frac
    pt = sum(net.values())
    share = sum(y for v, y in net.items() if is_mv(v)) / pt if pt else None
    why = _judge(share, None)
    if why or share is None:
        return str(p[0])[:7], ps, pe, 0.0, 0.0, "", why
    pos = {v: y for v, y in net.items() if y > 0}
    return (str(p[0])[:7], ps, pe, ps * share, pe * _conv(pos, rates[0], rates[1], is_mv),
            f"로켓그로스 B+환산 — 판매 주 {s0}~{e0} 중 {p[0]}~{p[1]} 같은 날짜 판매분석 일별 관리 {share:.1%}", "")


def rg_week(daily: dict, week: tuple, last: date, rates: tuple, is_mv) -> list:
    """예정 판매 주 1개 → [(달, 판매, 정산대상, 관리 판매, 관리 정산, 근거, 확인 필요 사유)] — 달 = 날짜의 달(D-266 ③)."""
    s0, e0, sales, amt = week
    a, b = _d(s0), min(_d(e0), last)
    parts = [(p, *_rg_net(daily, *p)) for p in _month_parts(a, b)]
    head = _rg_head(parts, sales) if parts else "나눌 판매 없음(판매 주가 기준일 뒤)"
    if head:
        return [(s0[:7], float(sales or 0), float(amt), 0.0, 0.0, "", head)]
    tot = sum(sum(n.values()) for _p, n, _m in parts)
    out = [_rg_part(p, net, sum(net.values()) / tot, week, rates, is_mv) for p, net, _m in parts]
    return [x for x in out if round(x[1]) or round(x[2])]


# ── 계정 하나 ──
def split(acct) -> list:
    """계정의 정산 예정 줄(acct.u) → [(판매 방식, 달, 판매, 정산대상, 관리 판매, 관리 정산, 근거, 확인 필요 사유)] — 계약 전 달 처리는 부르는 쪽."""
    c = acct.ctx
    basis = _d(c.basis)
    daily = (c.daily or {}).get(acct.aid) or {}
    orders = order_months(c.base, acct.acct)
    wfiles = [f for f in acct.files if f.channel == WING]
    periods = [(str(f.period_start), str(f.period_end)) for f in wfiles]
    wrows = [r for f, r in SS._order_rows(wfiles, [])]
    rates = rg_rates(acct.files, basis - timedelta(days=1))
    out = []
    for ch, ym, s, e, kind, note, *rest in acct.u:
        if kind in ("자료 없음", "확인 필요") or ym == "-":
            out.append((ch, ym, s, e, 0.0, 0.0, f"{kind} — {note}", ""))
        elif ch == WING:
            out.append((ch, ym, s, e, *_wing_one(c, ym, s, e, orders, periods, wrows, daily, acct.is_mv, basis)))
        else:
            for wk in (rest[0] if rest else []):
                out += [(ch, *x) for x in rg_week(daily, wk, basis - timedelta(days=1), rates, acct.is_mv)]
    return out


def _wing_one(c, ym: str, s: float, e: float, orders: dict, periods: list, wrows: list, daily: dict, is_mv, basis: date) -> tuple:
    got = wing_actual(orders.get(ym.replace("-", "")) or [], periods, s, e, is_mv)
    if got:
        return (*got, "")
    nxt = date(int(ym[:4]) + (ym[5:] == "12"), int(ym[5:]) % 12 + 1, 1)
    last = min(nxt - timedelta(days=1), basis - timedelta(days=1))
    return wing_b8(daily, orders, wrows, lag_pmf(str(c.base), ym), ym, last, s, e, is_mv)
