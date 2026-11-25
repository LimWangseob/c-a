"""위탁자 정산서 3차 형식 — 한 달 계산 상태(MonthState) + 1~4 판매(확정·정산 예정) + 5 광고비. T-38 S2(샘플 `s03_compute.py` Month 의
__init__·공통 도구·sales·_ships·_option_weights·pending_sales·ads 를 단계별 함수로 나눔 · 계산식·순서 그대로).

관리 판정 = 기존 위탁정산서 계산과 같게: 판매·물류비·재고 보상(등록상품 단위 자료) = mpids · 광고·밀크런·정산 예정(옵션 단위 자료) = is_mv(VID).
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from coupang_analytics import settlement_managed_alloc as MA
from coupang_analytics import settlement_statement_pending as PEND
from coupang_analytics.settlement_statement_account import num


def jl(v):
    """쿠팡 원문 칸(JSON 글 또는 dict) → 값 · 빈 칸 = None · 글인데 JSON 이 아니면 오류(조용히 넘기지 않음)."""
    if v is None or v == "":
        return None
    return json.loads(v) if isinstance(v, str) else v


def kst_month(iso: str) -> str:
    """'2026-08-31T15:00:00Z' → KST 달 '2026-09'."""
    t = datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S") + timedelta(hours=9)
    return f"{t:%Y-%m}"


def cum_round(xs: list, target: int) -> list:
    """누적 반올림 — 칸 합 = target(끝전은 마지막 칸)."""
    out, acc, prev = [], 0.0, 0
    for x in xs:
        acc += x
        out.append(round(acc) - prev)
        prev = round(acc)
    if out:
        out[-1] += target - sum(out)
    return out


def pct(x: float) -> str:
    return "100%" if abs(x - 1) < 1e-12 else f"{x * 100:.1f}%"


def month_end(m: str) -> date:
    y, mo = int(m[:4]), int(m[5:])
    return date(y + (mo == 12), mo % 12 + 1, 1) - timedelta(days=1)


class MonthState:
    """계정 1개 × 판매 달 1개 계산 상태. src = `settlement_consignor_month.account_source()` 결과."""

    def __init__(self, src: dict, month: str, judge):
        d = self.d = src
        self.aid, self.acct = d["aid"], d["acct"]
        self.m, self.mk = month, month.replace("-", "")
        self.base, self.basis = Path(d["base"]), d["basis"]
        self.mpids, self.opt2pid, self.is_mv = set(d["mpids"]), d["opt2pid"], dict(d["is_mv"])
        self.added = list(judge.added.get(self.aid, []))           # 관리 상품 추가 판정(판정표 · 소유자 원문 근거)
        self.judge = judge
        self.mpids |= {str(x["등록상품ID"]) for x in self.added}
        self.pre = MA.pre_contract(month, d["cdate"])
        self.j: list = []            # judgments
        self.chk: list = []          # checks
        self._vid_map()
        self.ext_used: set = set()
        self.m_extra: set = set()                              # 등록상품ID 모르는 관리 옵션('옵션 {vid}')
        self.names = self._names()
        self.files = {(f[1], f[3], f[4]) for f in d["files_meta"]}   # 상품별 정산 파일이 있는 (판매 방식, 기간)
        self.cols: dict = defaultdict(lambda: [0.0] * 9)     # pid → c1..c8 (index 1..8) · 정산 예정분 포함
        self.pend: dict = defaultdict(lambda: [0.0] * 9)     # pid → 그중 정산 예정분(쿠팡 확정 전)
        self.pend_wing: Counter = Counter()                   # pid → 그중 윙 정산 예정 판매(E1 검산 · D-405)
        self.allsales: Counter = Counter()                    # pid → 판매금액(관리 여부 무관 · 확정+예정)
        self.rgsales: Counter = Counter()                     # pid → 로켓그로스 판매(확정+예정) — 상품 자료 전 창고 비용 나누기
        self.common: list = []                                # (이름, 쿠팡 금액(+=빼는 돈), 위치 분류)
        self.loc: dict = defaultdict(list)                    # 분류 → [(지급 줄 key, 쿠팡이 실제 뺀 금액)]
        self.pend_info: list = []                             # 정산 예정분 방법·원천
        self.pend_check: list = []                            # 못 나눠 금액에서 뺀 정산 예정분(D-262 ③) — {판매 방식·판매·정산·사유}
        self.pend_cost: dict = {}                             # 6·7·8 상품 자료 전 금액(계정 전체 · 빼는 돈 +)
        self.pend_cost_m: dict = {}                           # 그중 관리 몫(정산서 반영 · 부호 = 정산서)
        self.ad_note = ""
        self.ad_alloc_share: float | None = None              # 그 달 광고비 상품별 배분 중 관리 몫(D-317 ②)
        self.fast = {"계정 전체": 0.0, "관리 몫": 0.0, "지급일": []}
        self.own: Counter = Counter()                         # 위탁자 본인 차감(D-312 ② · 관리 몫 0) — 항목 → 계정 금액
        self.missing: dict = {}
        self.settle_by_ch = {"윙": Counter(), "로켓그로스": Counter()}

    def _vid_map(self) -> None:
        d = self.d
        self.vid2pid = dict(self.opt2pid)
        for pid, p in d["inventory"].items():
            for v in p["types"]:
                self.vid2pid.setdefault(str(v), str(pid))
        for rec in d["periods"].values():
            for v, o in (rec.get("옵션") or {}).items():
                if o.get("등록상품ID"):
                    self.vid2pid.setdefault(str(v), str(o["등록상품ID"]))
        add_p = {str(x["등록상품ID"]) for x in self.added}
        for v, p in self.vid2pid.items():                     # 추가 판정 상품의 옵션 = 관리 옵션
            if p in add_p:
                self.is_mv[v] = True

    def _names(self) -> dict:
        names = {}
        for p in sorted(self.d["prows"], key=lambda r: str(r["월(매출인식)"])):
            if p["상품명"]:
                names[str(p["등록상품ID"])] = p["상품명"]
        for pid, p in self.d["inventory"].items():
            names.setdefault(str(pid), p["name"])
        return names

    # ── 공통 도구 ──
    def managed(self, pid: str) -> bool:
        return (not self.pre) and pid in self.mpids

    def is_m(self, pid: str) -> bool:
        """관리 상품 = mpids(판정표 추가 포함) 또는 옵션 단위 자료로 관리 판정된 상품(ext_used · 등록상품ID 모르는 관리 옵션)."""
        return self.managed(pid) or ((not self.pre) and (pid in self.ext_used or pid in self.m_extra))

    def vid_pid(self, vid: str) -> str:
        return self.vid2pid.get(str(vid), "")

    def vid_managed(self, vid: str, unit: str = "vid") -> bool:
        pid = self.vid_pid(vid)
        if unit == "vid" and str(vid) in self.is_mv:
            return (not self.pre) and bool(self.is_mv[str(vid)])
        return self.managed(pid) if pid else (not self.pre) and bool(self.is_mv.get(str(vid)))

    def managed_vid(self, vid: str, unit: str = "vid") -> tuple[str, bool]:
        pid, m = self.vid_pid(vid), self.vid_managed(vid, unit)
        if m and pid and pid not in self.mpids:
            self.ext_used.add(pid)
        return pid, m

    def lines(self):
        """쿠팡 지급 줄 → (key, 장부 줄, 원본 줄)."""
        for row, r, _parts in self.d["lines"]:
            yield (row[2], row[3], row[4], r["채널"], row[5]), row, r

    def line_parts(self):
        """쿠팡 지급 줄 → (key, 장부 줄, 원본 줄, 기존 계산의 공제 항목 Counter — D-304·D-312 반영)."""
        for row, r, parts in self.d["lines"]:
            yield (row[2], row[3], row[4], r["채널"], row[5]), row, r, parts

    def pend_line(self, row, r) -> bool:
        """이 달 판매 기간 지급 줄 중 상품별 정산 파일이 아직 없는 줄 = 정산 예정(쿠팡 계산 · 상품별 자료 전)."""
        return str(row[3])[:7] == self.m and (r["채널"], str(row[3]), str(row[4])) not in self.files


# ── 1~4 + 배송비 ──
def sales(st: MonthState) -> None:
    st.ship_stats = 0
    for p in st.d["prows"]:
        if str(p["월(매출인식)"])[:7] == st.m:
            _sales_row(st, p)
    ships(st)


def _sales_row(st: MonthState, p: dict) -> None:
    pid = str(p["등록상품ID"])
    if pid.startswith("옵션 "):
        pid = st.opt2pid.get(pid[3:], pid)

    def g(c):
        return p[c] or 0
    if pid == "배송비":
        st.ship_stats += g("쿠팡 정산금액 합계(부가비용 차감 전)")
        return
    s, cp, fee, sett = g("윙 판매액") + g("로켓그로스 매출금액"), g("판매자할인쿠폰"), g("판매수수료(VAT포함)"), g("쿠팡 정산금액 합계(부가비용 차감 전)")
    if pid.startswith("("):
        if s or sett:
            st.j.append(f"상품 미표기 판매 줄 {pid} 판매 {s:,} — 확인 필요")
        return
    st.allsales[pid] += s
    st.rgsales[pid] += g("로켓그로스 매출금액")
    if st.managed(pid):
        c = st.cols[pid]
        c[1] += s
        c[2] -= cp
        c[3] -= fee
        c[4] += sett - (s - cp - fee)


AD_NOCAMP = "ad:nocamp"        # 신규-01 캠페인 없는 광고 조정·지원금(D-317 ② 비중 · 9 그 밖의 쿠팡 공제 D-347 ①)
SHIP_EST = "상품 모름(같은 주문·반품 조회 없음) → 이 달 윙 상품 정산금 비율로 나눔(D-391 ④)"


def ships(st: MonthState) -> None:
    """상품 없는 윙 배송비 줄 = 같은 주문 상품 → 없으면 반품 조회 상품(기존 코드 _split 과 같은 규칙)."""
    rows = st.d["file_rows"]
    order_pids = defaultdict(set)
    for x in rows:
        if x[6]:
            order_pids[x[5]].add(x[6])
    st.order_pids = order_pids
    found = {}
    for x in rows:
        _fi, ch, _kind, _ps, pe, oid, pid, opt, _pn, _qty, s, cp, fee, sett, rec, _rk, _gross = x
        if not pid and ch == "윙" and (s or sett):
            found[(oid, opt, rec, s, sett)] = (oid, s, cp, fee, sett, (rec or pe)[:7])
    st.ship_m = [0, 0]
    st.ship_all = [0, 0]
    st.ship_w = MA.wing_month_weights(st.d["prows"], st.m, st.opt2pid)
    unk: list = []
    for item in found.values():
        if item[5] == st.m:
            _ship_one(st, item, unk)
    if unk:
        st.j.append(f"확인 필요: 상품을 못 찾은 배송비 줄 {len(unk)}개 판매 {sum(u[1] for u in unk):,} — 금액에 넣지 않음")
    st.chk.append({"검사": "배송비 정산금액(파일 줄) = 정산집계 '배송비' 줄", "값": [round(st.ship_all[1]), st.ship_stats],
                   "차이": round(st.ship_all[1]) - st.ship_stats})


def _ship_pids(st: MonthState, oid: str) -> tuple[list, str]:
    pids = sorted(st.order_pids.get(oid) or [])
    if pids:
        return pids, "같은 주문 상품"
    returns = st.d["v"].get("returns") or {}
    vids = [str(i.get("vendorItemId")) for r_ in returns.get(oid) or [] for i in r_.get("items") or []]
    if not vids:
        return [], SHIP_EST
    return sorted({st.vid_pid(v) for v in vids if st.vid_pid(v)}), "반품 조회 상품"


def _ship_one(st: MonthState, item: tuple, unk: list) -> None:
    oid, s, cp, fee, sett, _ym = item
    st.ship_all[0] += s
    st.ship_all[1] += sett
    pids, how = _ship_pids(st, oid)
    ks = {p: 1 / len(pids) for p in pids} or (st.ship_w if how == SHIP_EST else {})    # 주문 안 상품마다 같은 몫
    if not ks:
        unk.append((oid, s, sett))
        return
    for pid, k in ks.items():
        st.allsales[pid] += s * k
        if st.managed(pid):
            c = st.cols[pid]
            c[1] += s * k
            c[2] -= cp * k
            c[3] -= fee * k
            c[4] += (sett - (s - cp - fee)) * k
            st.ship_m[0] += s * k
            st.ship_m[1] += sett * k
    if len(pids) > 1 or how != "같은 주문 상품":
        st.j.append(f"배송비 줄 주문 {oid} 판매 {s:,} → {how} {','.join(pids)}")


def settle_by_channel(st: MonthState) -> None:
    """판매 방식별 정산금액(상품) — 지급 줄 나누기용."""
    for p in st.d["prows"]:
        if str(p["월(매출인식)"])[:7] == st.m:
            pid = str(p["등록상품ID"])
            if pid.startswith("옵션 "):
                pid = st.opt2pid.get(pid[3:], pid)
            st.settle_by_ch["윙"][pid] += p["윙 정산금액"] or 0
            st.settle_by_ch["로켓그로스"][pid] += p["로켓그로스 정산대상액"] or 0


# ── 1~4 정산 예정분(D-242 A안 · 나누기 = settlement_statement_pending — 옛 엑셀 위탁정산서와 같은 코드 · D-261~D-292 · T-178) ──
def _pend_split(st: MonthState, ch: str, s: float, e: float) -> PEND.Split:
    """계정 합계로만 온 정산 예정분 → 옵션별 조각 — 윙 = ① 주문별매출 실제값 → B8+환산 → ⓒ2 → ⓑo · 로켓그로스 = 그 달 판매 비율(D-269 ②)."""
    if ch == PEND.RG:
        return PEND.rg_month(st.d["periods"], (st.m, s, e), st.vid_managed)
    return PEND.wing_one(st.base, (st.m, s, e), st.d["orders"], st.d["daily"], st.vid_managed, date.fromisoformat(st.basis), st.d["files"])


def _option_names(st: MonthState) -> dict:
    """옵션 → 상품명(판매분석 기간·일별 · 없으면 주문별매출)."""
    nm = {str(r["vendorItemId"]): r.get("vendorItemName") or "" for rs in st.d["orders"].values() for r in rs if r.get("vendorItemId") is not None}
    for recs in (st.d["periods"], st.d["daily"]):
        nm.update({str(v): o["상품"] for k in sorted(recs) for v, o in (recs[k].get("옵션") or {}).items() if o.get("상품")})
    return nm


def _pend_rg(st: MonthState, pl: list, s: float, e: float, sp: PEND.Split) -> tuple:
    """(옵션 → (쿠폰, 수수료) 함수, 추정, 방법 글)."""
    ls = [r for _key, _row, r in pl if r["채널"] == PEND.RG and num(r.get("지급비율")) in (70, 100)]
    cp = sum(num(r.get("totalSellerDiscount")) for r in ls)
    fee = sum(num(r.get("totalTakeRateAmountWithVat")) for r in ls)
    how = ("판매·정산 = 쿠팡 정산 줄(정산현황·매출내역 조회) · 2·3 = 그 판매 기간 지급비율 70 줄의 판매자 할인(totalSellerDiscount)·"
           "판매수수료(totalTakeRateAmountWithVat) 합 · 4 = 정산 − (판매 − 2 − 3)")
    st.chk.append({"검사": "정산 예정 로켓그로스: 판매 − 쿠폰 − 수수료 − 정산 (쿠팡 정산 줄 · 원 단위)", "값": [s, cp, fee, e],
                   "차이": round(s - cp - fee - e)})

    def cf(v: str) -> tuple[float, float]:
        k = sp.opts[v][1] / e if e else sp.opts[v][0] / s
        return cp * k, fee * k
    return cf, False, how


def _pend_wing(st: MonthState, s: float, e: float, sp: PEND.Split) -> tuple:
    """(옵션 → (쿠폰, 수수료) 함수, 추정, 방법 글) — 실제값(sp.cf)이 있으면 그대로(D-261 ② E2) · 없으면 (판매 − 정산)을 확정 줄 쿠폰:수수료 비율로."""
    if sp.cf:
        return sp.cf.__getitem__, False, "쿠팡 실제 주문 금액(주문별매출): 2 = sfcAmount · 3 = trAmountIncVat · 4 = 정산 − (판매 − 2 − 3)"
    conf = [r for _key, row, r in st.lines() if r["채널"] == "윙" and row[6] == "지급 완료" and r.get("saleAmount") is not None]
    fin = [r for r in conf if num(r.get("지급비율")) == 30] or conf
    C = sum(num(r.get("sellerDiscountCoupon")) for r in fin)
    F = sum(num(r.get("salesFee")) for r in fin)
    how = (f"추정: 판매·정산 = 쿠팡 정산 줄(예정 줄은 정산대상액만) · (판매 − 정산) {s - e:,.0f} 을 이 계정 확정 윙 지급 줄(최종액 {len(fin)}줄) "
           f"쿠폰 {C:,.0f} : 수수료 {F:,.0f} 비율로 2·3 에 나눔 · 4 = 0")

    def cf(v: str) -> tuple[float, float]:
        gap = sp.opts[v][0] - sp.opts[v][1]
        return (gap * C / (C + F), gap * F / (C + F)) if (C + F) else (0.0, gap)
    return cf, True, how


def _pend_alloc(st: MonthState, ch: str, sp: PEND.Split, cf) -> dict:
    """옵션별 조각 → 상품 줄(1~4) · 계정 합계 {판매·쿠폰·수수료·쿠팡 부담 할인·정산·관리 판매}."""
    nm, t = _option_names(st), Counter()
    for v, (s, e) in sp.opts.items():
        cp, fee = cf(v)
        c4 = e - (s - cp - fee)
        pid, m = st.managed_vid(v)
        key = pid or f"옵션 {v}"
        st.names.setdefault(key, nm.get(v) or key)
        if not pid and m:
            st.m_extra.add(key)
        st.allsales[key] += s
        if ch == PEND.RG:
            st.rgsales[key] += s
        st.settle_by_ch[ch][key] += e
        t.update({"판매": s, "쿠폰": cp, "수수료": fee, "쿠팡 부담 할인": c4, "정산": e, "관리": s if m else 0.0})
        if m:
            for i, val in ((1, s), (2, -cp), (3, -fee), (4, c4)):
                st.cols[key][i] += val
                st.pend[key][i] += val
            if ch != PEND.RG:
                st.pend_wing[key] += s
    return t


def cross_weeks(us: list, m: str) -> list:
    """정산 예정 줄 중 달을 걸친 로켓그로스 판매 주 → '확인 필요' 문장(신규-23 감지 · 금액은 그대로)."""
    return [f"확인 필요: 로켓그로스 정산 예정 판매 주 {w[0]}~{w[1]} 가 달을 걸침 — 이 정산서는 주 시작 달 {m} 에 전부 넣음(신규-23 · 날짜 달 나누기 없음)"
            for x in us if x[0] == "로켓그로스" and len(x) > 6 for w in x[6] or () if str(w[0])[:7] != str(w[1])[:7]]


def pending_sales(st: MonthState) -> None:
    us = [x for x in st.d["u"] if x[1] == st.m and (x[2] or x[3])]
    # 신규-23: 새 정산서 로켓그로스 예정 = 주 시작 달 키(옛 위탁정산서는 날짜의 달로 나눔 D-266 ③) — 쿠팡 주 기간은 달 끝에서 잘림
    # (output44 지급 줄 3,469·예정 줄 522 중 달 걸친 주 0) → 걸친 주가 나오면 나누지 않고 알림(금액 그대로 · 쿠폰·수수료 나누기 없이 판매만 나누면 검산 어긋남)
    st.j += cross_weeks(us, st.m)
    pl = [(key, row, r) for key, row, r in st.lines() if st.pend_line(row, r)]
    for x in us:
        ch, _ym, s, e, kind, note = x[:6]
        sp = _pend_split(st, ch, s, e)
        if sp.why:                                            # D-262 ③ — 그 금액만 빼고 발행
            st.pend_check.append({"판매 방식": ch, "판매": s, "정산": e, "사유": sp.why})
            st.j.append(f"확인 필요: {st.m} {ch} 정산 예정 판매 {s:,}·정산 {e:,} — {sp.why}(금액 넣지 않음 · 쿠팡 상품별 자료가 오면 다음 정산서에 반영 · D-262 ③)")
            continue
        cf, est, how = _pend_rg(st, pl, s, e, sp) if ch == PEND.RG else _pend_wing(st, s, e, sp)
        t = _pend_alloc(st, ch, sp, cf)
        st.pend_info.append({"항목": f"1~4 {ch} 정산 예정 (상품별 정산 파일 전)", "추정": est, "방법": how, "원천": f"{kind} · {note}",
                             "계정 전체": {"판매": s, "쿠폰": round(t["쿠폰"]), "수수료": round(t["수수료"]), "쿠팡 부담 할인": round(t["쿠팡 부담 할인"]), "정산": e},
                             "상품 나눈 기준": f"{sp.how} · 관리 = 옵션(VID) 관리 판정", "그중 관리 판매": round(t["관리"])})


# ── 5 광고비 ──
def _ad_cost(st: MonthState, pa: list) -> dict:
    cost: dict = defaultdict(lambda: defaultdict(float))
    for dt, camp, vid, c in pa:
        if str(int(float(dt)))[:6] == st.mk and vid not in (None, ""):
            cost[(int(float(dt)), str(int(float(camp))))][str(int(float(vid)))] += c
    return cost


def _ad_bill(st: MonthState, bill: dict, have: set, cost: dict) -> dict:
    t = dict.fromkeys(("charged", "prod_all", "prod_m", "nocamp", "miss"), 0.0)
    t["bill_m"] = 0
    for (dt, camp), b in bill.items():
        if str(int(float(dt)))[:6] != st.mk:
            continue
        t["bill_m"] += 1
        t["charged"] += b
        if camp == "":
            t["nocamp"] += b
            continue
        cv = cost.get((int(float(dt)), str(camp)))
        tot = sum(cv.values()) if cv else 0.0
        if not tot or st.mk not in have:
            t["miss"] += b
            continue
        _ad_split(st, cv, b, tot, t)
    return t


def _ad_split(st: MonthState, cv: dict, b: float, tot: float, t: dict) -> None:
    for vid, c in cv.items():
        pid, m = st.managed_vid(vid)
        t["prod_all"] += b * c / tot
        if m and pid:
            st.cols[pid][5] -= b * c / tot * 1.1
            t["prod_m"] += b * c / tot
        elif m:
            t["miss"] += b * c / tot            # 관리 옵션인데 상품 모름 → 공통
            t["prod_all"] -= b * c / tot


def _ad_deducted(st: MonthState) -> float:
    deducted = 0.0
    for key, _row, r in st.lines():
        br = jl(r.get("adSalesOffsetYearMonthBreakdown"))
        if isinstance(br, dict) and br.get(st.m):
            st.loc["ad"].append((key, num(br[st.m])))
            deducted += num(br[st.m])
    for key, row, r in st.lines():
        if r["채널"] == "윙":
            for x in r.get("차감 사유") or []:
                if "광고" in (x.get("사유") or "") and str(row[3])[:7] == st.m:
                    st.j.append(f"확인 필요: 윙 지급 줄 {key} 광고 차감 {x.get('금액')} — 달 표시 없음(위치만 · 금액은 광고 청구 자료 기준)")
    return deducted


def ads(st: MonthState) -> None:
    pa, bill, have = st.d["ads"]
    t = _ad_bill(st, bill, have, _ad_cost(st, pa))
    charged_v = t["charged"] * 1.1
    deducted = _ad_deducted(st)
    st.chk.append({"검사": "광고 청구(청구가능액×1.1) ↔ 쿠팡이 지급 줄에서 뺀 이 달 광고비(adSalesOffsetYearMonthBreakdown)",
                   "값": [round(charged_v, 1), deducted], "차이": round(charged_v - deducted, 1)})
    if not t["bill_m"] and st.mk not in have and bill:
        st.ad_note = f"{int(st.m[5:])}월 광고 청구 자료 아직 없음 — 5 광고비 0 으로 둠(바뀔 수 있음 · 쿠팡 광고 청구·공제가 나오면 다시 계산)"
    unattributed = charged_v - t["prod_all"] * 1.1
    # 신규-01 · D-317 ② 캠페인 없는 조정·지원금 = 그 달 옵션별 배분 합 비율(관리 배분 ÷ 전체 배분) · 줄 위치 = 9 '그 밖의 쿠팡 공제'(D-347 ①)
    st.ad_alloc_share = t["prod_m"] / t["prod_all"] if t["prod_all"] else None
    nocamp = t["nocamp"] * 1.1 if st.ad_alloc_share is not None else 0.0
    if round(nocamp):
        st.common.append((f"광고비 중 캠페인 없는 조정·지원금 (그 달 상품별 광고비 배분 비율 {pct(st.ad_alloc_share)} · D-317 ②)", nocamp, AD_NOCAMP))
    elif round(t["nocamp"]):
        st.j.append(f"확인 필요: {st.m} 캠페인 없는 광고 조정 {t['nocamp'] * 1.1:,.0f}원 — 이 달 상품별 광고비 배분이 없어 D-317 ② 비율을 못 구함 · "
                    "상품 표시 없는 광고비와 같은 비중으로 둠")
    unattributed -= nocamp
    if round(unattributed):
        why = []
        if st.mk not in have and t["charged"]:
            why.append("이 달 광고 보고서(상품별) 파일이 이 PC 에 없음")
        if t["nocamp"] and not round(nocamp):
            why.append(f"캠페인 없는 조정 {t['nocamp'] * 1.1:,.0f}")
        st.common.append(("광고비 중 쿠팡이 상품을 표시하지 않은 금액" + (f" ({' · '.join(why)})" if why else ""), unattributed, "ad"))
    st.ad = {"charged": charged_v, "deducted": deducted, "prod_all": t["prod_all"] * 1.1, "prod_m": t["prod_m"] * 1.1,
             "nocamp": t["nocamp"] * 1.1, "have_report": st.mk in have, "판단": st.ad_note}
