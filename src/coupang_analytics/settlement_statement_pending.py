"""위탁정산서 정산 예정분 관리 몫 나누기 — 쿠팡이 계정 합계로만 준 정산 중 판매를 관리 상품 몫으로 나눔(T-63 · T-73 · D-262 · D-264 · D-266 · D-267 · D-269 · D-282).

쿠팡 예정 줄 금액(계정 합계)은 그대로 두고 관리 몫만 나눔(D-279 ① · 나눈 조각 합 = 쿠팡 금액).
윙(D-269 ①): ① 주문별매출 실제값 → ② B8+환산(D-266 ① · D-267) → ③ ②가 '확인 필요' 조건(0~100% 밖 · 나눌 판매 없음 · 검산 1.5 이상 · 지연 자료 없음)이면
  빼지 않고 ⓒ2 = 저장해 둔 결제→구매확정 지연 분포 + 윙 정산 파일 환산(이미 확정 주문 빼기 없음) → 그것도 안 되면 ⓑo(D-282) =
  판매분석 일별 [그 달 1일−30일, 판매 끝] − 이미 확정의 관리 비율 × 쿠팡 예정 → 셋 다 안 되는 금액만 '확인 필요'.
  ①②③④ 모두 기준일에 앱이 가진 자료만(`basis_data` · T-84 · ① = D-292): 주문별매출 = 기준일 전에 받은 달(cut 앞 달 · ① = 그 달이 받은 달일 때만) ·
  윙 정산 파일 = 정산일 ≤ 기준일 · 지연 분포 = cut 앞 달 · 저장 분포 = '기준 달' ≤ cut 만 · 정산일 모르는 윙 정산 파일이 있으면 '확인 필요'.
- ① 그 달(기준일 전에 받은 달) `검증자료/월자료/{계정}/주문별매출_YYYYMM.json` 줄 중 구매확정일이 윙 정산 파일 기간 밖인 줄의 합(판매 = productGmv + deliveryGmv ·
  정산 = apAmount)이 쿠팡 예정과 원 단위 같을 때만 · 상품 없는 줄(배송비·취소) = 같은 주문 상품 줄 수 비율(못 찾으면 그 예정분 관리 비율).
- ② 윙 B8: 판매분석 일별 윙 순액(결제일) [그 달 1일−30일, E−8일] − 이미 구매확정된 판매(cut 앞 달 주문별매출 productGmv(결제일) + 그 주문 밖 윙
  정산 파일 줄(한 번만 · 구매확정일에서 결제→구매확정 지연 분포로 결제일에 나눔)) · 옵션 합 뒤 음수 0. E = 예정 판매 기간 끝(기준일 전날 또는 그 달 말일 중 이른 날)
  → 진행 중 달 결제 끝 = 기준일−9일(D-267). 환산 = 옵션별 정산대상/판매(cut 앞 달 주문별매출 · 결제일 ≥ 시작−60일 · 없는 옵션 = 계정 비율 · 계정 비율도 없으면 판매 그대로).
- 지연 분포 = cut 앞 모든 계정 주문별매출 주문 줄 · 계산할 때마다 `검증자료/결제확정_지연분포.json` 에 '기준 달' = cut 으로 저장(더 늦은 달 것이 있으면 그대로 · D-269 ①).
로켓그로스(D-269 ②): 예정 판매 주마다 그 달 판매분석(기간 M:YYYY-MM · 없으면 그 달 주별 W:) 로켓그로스 판매 비율(T-63 이전 방식) · 기준일 뒤 주도 같음 ·
  주가 달을 걸치면 날짜의 달로 나눔(D-266 ③ · 그 달 날짜들 판매분석 일별 순액 비율) · 그 달 판매 없음·0~100% 밖 = 그 금액만 '확인 필요'.
나누기 결과 = 옵션별 조각(`Split` · T-178) — 관리 몫 = 그중 관리 옵션 합(`managed` · 옛 엑셀 위탁정산서) · 새 형식 위탁자 정산서(`settlement_consignor_month_calc`)는
  같은 조각을 상품 줄로 씀(`wing_one`·`rg_month`).
근거 = `output/_검증_261117_정산끝난달/판정_보고.md` 6절·6-1b(ⓑo)(`scripts/b2_wing.py` C2 · `b5_fill.py`) · `output/_분석_261116_예정분나누기/미정산장부_방안.md` 7~8절.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from coupang_analytics import settlement_stats as SS
from coupang_analytics.settlement_docs import LAG_DAYS

CHECK_MAX = 1.5                       # 검산(남은 판매 ÷ 쿠팡 판매) 이 값 이상 = 확인 필요(D-266 ②)
WING_BACK, WING_CUT, RATE_BACK = 30, 8, 60
PMF_FILE = "결제확정_지연분포.json"           # 저장해 둔 결제→구매확정 지연 분포(D-269 ①)
WING, RG = "윙", "로켓그로스"
SD_LAG = LAG_DAYS["주문별매출"]       # 주문별매출 받는 날 = 말일 + 이 날수 뒤(앱 규칙 · D-282 ⓑo 자료 시점)


class Split(NamedTuple):
    """정산 예정 줄 하나를 옵션으로 나눈 결과 — why(확인 필요 사유)가 있으면 opts 는 빈 사전 · 조각 합 = 쿠팡 예정 금액."""
    opts: dict                        # {옵션: (판매, 정산대상)} — 상품을 못 찾은 조각 = 옵션 ''
    how: str = ""
    why: str = ""
    cf: dict = {}                     # ① 실제값만 {옵션: (판매자 할인쿠폰, 판매수수료)} · ②③④ = 빈 사전(쿠팡이 안 줌)


def managed(sp: Split, is_mv) -> tuple[float, float, str, str]:
    """(관리 판매, 관리 정산, 근거, 확인 필요 사유)."""
    return sum(s for v, (s, _e) in sp.opts.items() if is_mv(v)), sum(e for v, (_s, e) in sp.opts.items() if is_mv(v)), sp.how, sp.why


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


def save_pmf(base: Path, ym: str, pmf: tuple) -> None:
    """지연 분포 저장 — 저장된 것이 더 늦은 달 분포면 그대로(D-269 ①)."""
    p = Path(base) / "검증자료" / PMF_FILE
    if not pmf or (p.is_file() and json.loads(p.read_text(encoding="utf-8")).get("기준 달", "") > ym):
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"기준 달": ym, "분포": [list(x) for x in pmf]}, ensure_ascii=False), encoding="utf-8")


def stored_pmf(base: Path, cut: str) -> tuple:
    """저장해 둔 지연 분포 — 파일 없거나 '기준 달'이 cut 보다 늦으면(기준일 뒤 자료 · T-84) 빈 묶음(그때 ⓒ2 는 '지연 자료 없음')."""
    p = Path(base) / "검증자료" / PMF_FILE
    j = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    return tuple((int(k), float(v)) for k, v in j.get("분포") or []) if j.get("기준 달", "") <= cut else ()


def _conv(pos: dict, rate: dict, acc: float | None) -> dict:
    """정산대상 환산 뒤 옵션별 비율 — 옵션 판매 × 옵션 정산대상/판매(없으면 계정 비율 · 그것도 없으면 1)."""
    w = {v: y * rate.get(v, acc if acc is not None else 1.0) for v, y in pos.items()}
    t = sum(w.values())
    return {v: y / t if t else 0.0 for v, y in w.items()}


def _rates(pairs) -> tuple[dict, float | None]:
    """[(옵션, 판매, 정산대상)] → ({옵션: 정산대상/판매}, 계정 비율)."""
    s: dict = defaultdict(float)
    a: dict = defaultdict(float)
    for v, x, y in pairs:
        s[v] += x
        a[v] += y
    tot = sum(s.values())
    return {v: a[v] / s[v] for v in s if s[v]}, (sum(a.values()) / tot if tot else None)


def _judge(mm: float, pt: float, s: float | None) -> str:
    """'확인 필요' 사유 — 금액으로 적음(D-281) · mm = 관리 판매 · pt = 나눌 판매 · s = 쿠팡 판매(검산 안 하면 None)."""
    if not pt:
        return "나눌 판매 없음(그 기간 판매분석 판매 0)"
    if not 0 <= mm / pt <= 1:
        return f"관리 판매 {mm:,.0f}원 · 나눌 판매 {pt:,.0f}원 — 관리 몫이 0~100% 밖"
    if s and pt / s >= CHECK_MAX:
        return f"검산 — 남은 판매 {pt:,.0f}원이 쿠팡 판매 {s:,.0f}원의 {CHECK_MAX}배 이상"
    return ""


# ── ① 윙 주문별매출 실제값 ──
def _ap(r: dict) -> float:
    return float(r.get("apAmount") or 0)


def _order_opts(rows: list, pend: list):
    """줄 → [(옵션, 몫)] 함수 — 상품 줄 = 그 옵션 · 상품 없는 줄(배송비·취소) = 같은 주문 상품 줄 수 비율(못 찾으면 예정분 옵션 판매 비율 · False 표시)."""
    by_o: dict = defaultdict(list)
    for r in rows:
        if r.get("vendorItemId") is not None:
            by_o[str(r["orderId"])].append(str(r["vendorItemId"]))
    opt = [r for r in pend if r.get("vendorItemId") is not None]
    tot = sum(gmv(r) for r in opt)
    rest = [(str(r["vendorItemId"]), gmv(r) / tot) for r in opt] if tot else [("", 1.0)]

    def opts(r: dict) -> tuple[list, bool]:
        if r.get("vendorItemId") is not None:
            return [(str(r["vendorItemId"]), 1.0)], True
        o = by_o.get(str(r["orderId"]))
        return ([(v, 1 / len(o)) for v in o], True) if o else (rest, False)
    return opts


def _actual_vals(r: dict) -> tuple:
    """(판매, 정산대상, 판매자 할인쿠폰, 판매수수료)."""
    return gmv(r), _ap(r), float(r.get("sfcAmount") or 0), float(r.get("trAmountIncVat") or 0)


def wing_actual(rows: list, periods: list, s: float, e: float) -> Split | None:
    """옵션별 실제값(판매·정산·쿠폰·수수료 · D-261 ② E2) 또는 None(파일 기간 밖 줄 합이 쿠팡 예정과 원 단위 다름)."""
    pend = [r for r in rows if not any(a <= str(r["confirmDate"])[:10] <= b for a, b in periods)]
    if not pend or round(sum(gmv(r) for r in pend)) != round(s) or round(sum(_ap(r) for r in pend)) != round(e):
        return None
    of = _order_opts(rows, pend)
    got: dict = defaultdict(lambda: [0.0] * 4)
    loose = 0
    for r in pend:
        ks, found = of(r)
        loose += not found
        for v, k in ks:
            got[v] = [g + x * k for g, x in zip(got[v], _actual_vals(r))]
    return Split({v: (g[0], g[1]) for v, g in got.items()},
                 f"주문별매출 실제값 — 정산 파일 기간 밖 구매확정 {len(pend)}줄(쿠팡 예정과 원 단위 같음)"
                 + (f" · 상품 못 찾은 줄 {loose}개 = 예정분 관리 비율" if loose else ""), "", {v: (g[2], g[3]) for v, g in got.items()})


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


def _file_rates(file_rows: list, s0: date) -> tuple[dict, float | None]:
    """윙 정산 파일 줄 옵션별 정산대상/판매(구매확정일 ≥ 시작−60일 · 줄 한 번만) — ⓒ2 환산(D-269 ①)."""
    since = s0 - timedelta(days=RATE_BACK)
    seen = {(str(r.order_id), str(r.option_id), r.sales): r.settle for r in file_rows if r.option_id and r.recognized and r.recognized >= since}
    return _rates((v, sl, st) for (_o, v, sl), st in seen.items())


def wing_b8(daily: dict, known: list, file_rows: list, pmf: tuple, win: tuple, s: float, e: float, is_mv, how: tuple) -> Split:
    """옵션별 조각 — win = (그 달, 판매 끝 last) · how = (이름, 환산 함수(s0) → (옵션 비율, 계정 비율))."""
    ym, last = win
    if s <= 0:
        return Split({}, "", f"나눌 판매 없음(쿠팡 예정 판매 {s:,.0f}원 — 0 이하)")
    s0 = _d(ym + "-01") - timedelta(days=WING_BACK)
    end = last - timedelta(days=WING_CUT)
    kp, ok = _wing_sub(known, file_rows, pmf, s0)
    if not ok:
        return Split({}, "", "결제→구매확정 지연 자료 없음")
    pos = _wing_residual(daily, kp, s0, end)
    pt = sum(pos.values())
    mm = sum(y for v, y in pos.items() if is_mv(v))
    why = _judge(mm, pt, s)
    if why:
        return Split({}, "", why)
    rate, acc = how[1](s0)
    cv = _conv(pos, rate, acc)
    return Split({v: (s * y / pt, e * cv[v]) for v, y in pos.items()},
                 f"{how[0]} — 결제일 {s0}~{end} 판매분석 일별 − 이미 구매확정 · 남은 판매 {pt:,.0f}원(쿠팡 판매 {s:,.0f}원) 중 관리 {mm:,.0f}원")


# ── ③-2 윙 ⓑo 운용 시점 그 달 판매 비율(D-282) ──
def _received_ym(basis: date) -> str:
    """기준일 전에 앱이 받은 주문별매출 달의 끝(이 달 앞 달까지) — 받는 날 = 정산서 만드는 날(기준일+1) · 말일+15 < 받는 날
    (`settlement_docs.months_after` LAG_DAYS 주문별매출 15) ⇔ 말일 ≤ 기준일−15 ⇔ 달 < (기준일−14일)의 달."""
    return str(basis - timedelta(days=SD_LAG - 1))[:7]


def basis_data(orders: dict, files: list, base, ym: str, basis: date) -> tuple:
    """기준일에 앱이 가진 자료만(D-282 · T-84 — B8·ⓒ2·ⓑo 공통) → ((cut, 주문별매출 줄(cut 앞 달 · 기준일 전에 받은 것), 윙 정산 파일 줄(정산일 ≤ 기준일),
    지연 분포(cut 앞 달)), 확인 필요 사유) · 정산일 모르는 윙 정산 파일이 있으면 자료 없이 사유만."""
    nodate = sum(f.settle_date is None for f in files if f.channel == WING)
    if nodate:
        return (), f"정산일 모르는 윙 정산 파일 {nodate}개(기준일 전 자료인지 모름)"
    cut = min(ym, _received_ym(basis))
    _p, wrows = _basis_wing(files, basis)
    return (cut, _wing_known(orders, cut), wrows, lag_pmf(str(base), cut)), ""


def _basis_wing(files: list, basis: date) -> tuple[list, list]:
    """정산일 ≤ 기준일 윙 정산 파일 → (기간 목록, 정산 줄) — ①·B8·ⓒ2·ⓑo 공통(정산일 모르는 파일은 basis_data 가 먼저 거름)."""
    return _wing_files([f for f in files if f.channel == WING and f.settle_date <= basis])


def wing_ops(daily: dict, got: tuple, win: tuple, s: float, e: float, is_mv) -> Split:
    """ⓑo — 판매분석 일별 윙 순액 결제일 [그 달 1일−30일, 판매 끝] − 이미 확정된 판매(got = basis_data: 기준일 전에 받은 주문별매출 + 기준일까지 정산된 윙 정산 파일 ·
    지연 분포도 받은 달로만)의 관리 비율 × 쿠팡 예정 판매·정산(D-282) → 옵션별 조각."""
    ym, last = win
    cut, known, wrows, pmf = got
    s0 = _d(ym + "-01") - timedelta(days=WING_BACK)
    kp, ok = _wing_sub(known, wrows, pmf, s0)
    if not ok:
        return Split({}, "", f"결제→구매확정 지연 자료 없음({cut} 앞 달 주문별매출 · 기준일 전에 받은 것 없음)")
    pos = _wing_residual(daily, kp, s0, last)
    pt = sum(pos.values())
    mm = sum(y for v, y in pos.items() if is_mv(v))
    if not pt:
        return Split({}, "", f"나눌 판매 없음(결제일 {s0}~{last} 판매분석 일별 − 이미 확정 = 남은 판매 0원 · 쿠팡 예정 판매 {s:,.0f}원)")
    why = _judge(mm, pt, None)
    if why:
        return Split({}, "", why)
    return Split({v: (s * y / pt, e * y / pt) for v, y in pos.items()},
                 f"윙 ⓑo 그 달 판매 비율(운용 시점 · 주문별매출 {cut} 앞 달까지) — 결제일 {s0}~{last} 판매분석 일별 − 이미 확정 · 남은 판매 {pt:,.0f}원 중 관리 {mm:,.0f}원")


# ── 로켓그로스 그 달 판매 비율(D-269 ②) ──
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


def month_weights(periods: dict, ch: str, ym: str) -> dict:
    """그 달 판매분석(기간 M:YYYY-MM · 없으면 그 달 주별 W:) 판매 방식 옵션별 판매 {옵션: 금액} — T-63 이전 방식."""
    keys = [f"M:{ym}"] if f"M:{ym}" in periods else [k for k in periods if k.startswith(f"W:{ym}")]
    w: dict = defaultdict(float)
    for k in keys:
        for v, o in (periods[k].get("옵션") or {}).items():
            if o.get("구분") == ch:
                w[str(v)] += float(o.get("판매금액") or 0)
    return w


def rg_month(periods: dict, line: tuple, is_mv) -> Split:
    """로켓그로스 예정 (달, 판매, 정산대상) → 그 달 판매 비율로 나눈 옵션별 조각(D-269 ②) · 그 달 판매 없음·관리 몫 0~100% 밖 = 확인 필요."""
    ym, s, e = line
    w = month_weights(periods, RG, ym)
    aa, mm = sum(w.values()), sum(a for v, a in w.items() if is_mv(v))
    why = _judge(mm, aa, None)
    if why:
        return Split({}, "", why)
    return Split({v: (s * a / aa, e * a / aa) for v, a in w.items() if a}, f"{ym} 판매분석 판매 {aa:,.0f}원 중 관리 {mm:,.0f}원")


def _month_parts(a: date, b: date) -> list:
    out, x = [], a
    while x <= b:
        nxt = date(x.year + (x.month == 12), x.month % 12 + 1, 1)
        out.append((x, min(b, nxt - timedelta(days=1))))
        x = nxt
    return out


def _week_fracs(daily: dict, parts: list) -> tuple[list, str]:
    """달을 걸친 주 → 달별 몫(그 달 날짜들 판매분석 일별 순액 비율 · D-266 ③) · 한 달 주 = [1]."""
    if len(parts) == 1:
        return [1.0], ""
    nets = [_rg_net(daily, *p) for p in parts]
    miss = sum(m for _n, m in nets)
    tot = sum(sum(n.values()) for n, _m in nets)
    if miss or tot <= 0:
        return [], f"달을 걸친 판매 주 — 판매분석 일별 {'빠진 날 %d일' % miss if miss else '순액 합 0 이하'}(달별로 못 나눔)"
    return [sum(n.values()) / tot for n, _m in nets], ""


def rg_week(daily: dict, periods: dict, week: tuple, is_mv) -> list:
    """예정 판매 주 1개 → [(달, 판매, 정산대상, 관리 판매, 관리 정산, 근거, 확인 필요 사유)] — 달 = 날짜의 달(D-266 ③) · 비율 = 그 달 판매 비율(D-269 ②)."""
    s0, e0, sales, amt = week
    parts = _month_parts(_d(s0), _d(e0))
    fr, why = _week_fracs(daily, parts)
    if why:
        return [(s0[:7], float(sales or 0), float(amt), 0.0, 0.0, "", why)]
    out = []
    for (a, b), f in zip(parts, fr):
        ym, ps, pe = str(a)[:7], (sales or 0) * f, amt * f
        ms, me, how, bad = managed(rg_month(periods, (ym, ps, pe), is_mv), is_mv)
        out.append((ym, ps, pe, ms, me, "" if bad else f"로켓그로스 그 달 판매 비율 — 판매 주 {s0}~{e0} 중 {a}~{b} · {how}", bad))
    return [x for x in out if round(x[1]) or round(x[2])]


# ── 계정 하나 ──
def _wing_files(files: list) -> tuple[list, list]:
    """윙 정산 파일 → (기간 목록, 정산 줄(중복 제거))."""
    wfiles = [f for f in files if f.channel == WING]
    return [(str(f.period_start), str(f.period_end)) for f in wfiles], [r for f, r in SS._order_rows(wfiles, [])]


def split(acct) -> list:
    """계정의 정산 예정 줄(acct.u) → [(판매 방식, 달, 판매, 정산대상, 관리 판매, 관리 정산, 근거, 확인 필요 사유)]."""
    c = acct.ctx
    basis = _d(c.basis)
    daily = (c.daily or {}).get(acct.aid) or {}
    periods = (c.periods or {}).get(acct.aid) or {}
    orders = order_months(c.base, acct.acct)
    out = []
    for ch, ym, s, e, kind, note, *rest in acct.u:
        if kind in ("자료 없음", "확인 필요") or ym == "-":
            out.append((ch, ym, s, e, 0.0, 0.0, f"{kind} — {note}", ""))
        elif ch == WING:
            out.append((ch, ym, s, e, *managed(wing_one(c.base, (ym, s, e), orders, daily, acct.is_mv, basis, acct.files), acct.is_mv)))
        else:
            out += [(ch, *x) for wk in (rest[0] if rest else []) for x in rg_week(daily, periods, wk, acct.is_mv)]
    return out


def wing_one(base, line: tuple, orders: dict, daily: dict, is_mv, basis: date, files: list) -> Split:
    """① 실제값 → ② B8+환산 → ③ ⓒ2(저장 지연 분포 + 정산 파일 환산) → ④ ⓑo(운용 시점 그 달 판매 비율 D-282) → 안 되면 확인 필요(D-269 ①)."""
    ym, s, e = line
    have, why = basis_data(orders, files, base, ym, basis)      # ①·B8·ⓒ2·ⓑo = 기준일에 앱이 가진 자료만(T-84 · D-292)
    if why:
        return Split({}, "", f"①·B8·ⓒ2·ⓑo: {why}")
    if ym < _received_ym(basis):                                # ① = 기준일 전에 받은 그 달 주문별매출 · 정산일 ≤ 기준일 윙 정산 파일 기간(D-292)
        got = wing_actual(orders.get(ym.replace("-", "")) or [], _basis_wing(files, basis)[0], s, e)
        if got:
            return got
    nxt = date(int(ym[:4]) + (ym[5:] == "12"), int(ym[5:]) % 12 + 1, 1)
    win = (ym, min(nxt - timedelta(days=1), basis - timedelta(days=1)))
    cut, known, wrows, pmf = have
    save_pmf(base, cut, pmf)
    b8 = wing_b8(daily, known, wrows, pmf, win, s, e, is_mv, ("윙 B8+환산", lambda s0: _known_rates(known, s0)))
    if not b8.why:
        return b8
    c2 = wing_b8(daily, [], wrows, pmf or stored_pmf(base, cut), win, s, e, is_mv,
                 ("윙 ⓒ2 저장 지연 분포+정산 파일 환산(B8 확인 필요 조건 — %s)" % b8.why, lambda s0: _file_rates(wrows, s0)))
    if not c2.why:
        return c2
    bo = wing_ops(daily, have, win, s, e, is_mv)
    return bo if not bo.why else Split({}, "", f"B8: {b8.why} · ⓒ2: {c2.why} · ⓑo: {bo.why}")
