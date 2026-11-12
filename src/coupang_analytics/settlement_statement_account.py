"""위탁정산서 계정 하나 — 관리 상품 몫 계산 1부(지급 줄·관리 범위·상품별 자료·정산 중 판매). T-25 이관(옛 `statement_managed.py`
`account()` 270~418줄을 메서드로 나눔 · 계산식·순서 그대로 · 2부 = `settlement_statement_deduct.py`).

- 관리 상품 = 대장 VID(결과 엑셀 + 날짜별 사본 — 지운 상품 포함) + 판매분석 노출 상품명이 같은 VID(D-107) + 이력 없이 지운
  로켓그로스 상품에서 되찾은 VID(`settlement_statement_scope` · 소유자 2026-11-12 규칙 ①~⑤). 정산 원본 옵션ID(=VID)로 등록상품ID 를 찾아
  관리 VID 가 하나라도 있는 등록상품은 상품 전체를 관리로 본다. 대장 밖 계정 = 원장 '정산전용상품' 시트(구분 '관리').
- 상품별 쿠팡 자료(정확): 끝난 판매의 판매금액·쿠폰·수수료·정산금액 · 계약 달 앞 판매 = 관리 밖(D-185 ②).
- 정산 중 판매 = 쿠팡 상품별 자료 전까지 같은 달 관리 판매 비율(D-148 예외).
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl

from coupang_analytics import settlement_files as SF
from coupang_analytics import settlement_ledger as SL
from coupang_analytics import settlement_managed_alloc as MA
from coupang_analytics import settlement_statement_scope as SCOPE
from coupang_analytics import settlement_stats as SS
from coupang_analytics import settlement_statement_source as SRC

AD, LOGI, MILK, SVC, ETC, COMP, REL, FAST = ("광고비", "로켓그로스 물류비(입출고·배송·보관·반품)", "밀크런(창고 입고 운송비)",
                                             "판매자서비스이용료", "기타 공제", "재고 분실·파손 보상(쿠팡이 줌)", "보류됐다 풀린 돈",
                                             "빠른정산 계좌인출액")
STS = ("지급 완료", "예정", "보류")


def num(v) -> float:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def verify_json(base: Path, acct: str) -> dict:
    p = base / "검증자료" / f"{acct}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def xlsx_rows(p: Path) -> list:
    rows = list(openpyxl.load_workbook(p, read_only=True).active.iter_rows(values_only=True))
    if not rows:
        return []
    h = [str(x or "").strip() for x in rows[0]]
    return [dict(zip(h, r)) for r in rows[1:] if r and any(x is not None for x in r)]


def ad_files(base: Path, acct: str) -> tuple[list, dict, set]:
    """검증자료/광고 — (보고서 줄[(날짜, 캠페인 ID, 광고집행 옵션ID, 광고비)], {(날짜, 캠페인 ID): 청구가능 광고비}, 보고서 받은 달). 없으면 ([], {}, set())."""
    d, tok = base / "검증자료" / "광고", SF._token(acct, "계정명")
    pa = [(r.get("날짜"), r.get("캠페인 ID"), r.get("광고집행 옵션ID"), num(r.get("광고비")))
          for p in sorted(d.glob(f"{tok}_매출성장광고_*.xlsx")) for r in xlsx_rows(p) if r.get("날짜") and r.get("캠페인 ID")]
    bill: Counter = Counter()
    for p in sorted(d.glob(f"{tok}_광고정산_*.json")):
        for it in json.loads(p.read_text(encoding="utf-8")).get("items") or []:
            cid = it.get("campaignId")                    # 없음 = 캠페인 없는 조정(광고 프로모션 할인 등)
            bill[(int(it["date"]), str(int(float(cid))) if cid not in (None, "") else "")] += num(it.get("billableAmount"))
    have = {p.stem.rsplit("_", 1)[-1] for p in d.glob(f"{tok}_매출성장광고_*.xlsx")}
    return pa, dict(bill), have


def _txt_num(v) -> float:
    """밀크런 엑셀 금액 = 글자('14960', '-2,400')로 들어옴(2026-11-02 output(29) 실측)."""
    try:
        return float(str(v).replace(",", "")) if v not in (None, "") else 0.0
    except ValueError:
        return 0.0


def milk_rows(base: Path, acct: str, since: str = "") -> list:
    """since = 'YYYYMM' — 그 달 뒤 밀크런 파일만."""
    d, tok = base / "검증자료" / "광고", SF._token(acct, "계정명")
    return [(str(r.get("밀크런번호")), _txt_num(r.get("총 합계금액")) + _txt_num(r.get("취소수수료")))
            for p in sorted(d.glob(f"{tok}_밀크런_*.xlsx")) if p.stem[-6:] >= since for r in xlsx_rows(p) if r.get("밀크런번호")]


def payout_lines(led, aid: str, L: dict) -> tuple[list, list]:
    """쿠팡 지급 줄(장부 줄 순서) → [(장부 줄, 원본 줄)] · 모든 칸이 같은 원본 줄이 또 나오면 한 번만."""
    pool: dict = defaultdict(list)
    for r in [{**r, "채널": "윙"} for r in led.wing_rows(aid)] + [{**r, "채널": "로켓그로스"} for r in led.rg_rows(aid)]:
        pool[(r["채널"], *SL._key(r), round(num(r["최종지급액"])))].append(r)
    keep, dup, seen = [], [], set()
    for row in L["rows"]:
        r = pool[(row[1], *row[2:6], round(row[9]))].pop(0)
        sig = json.dumps(r, sort_keys=True, ensure_ascii=False, default=str)
        (dup if sig in seen else keep).append((row, r))
        seen.add(sig)
    return keep, dup


def deductions(r: dict) -> tuple[float, float, Counter]:
    """지급 줄 1개 → (정산금액, 보류 해제액, 공제 항목별 Counter(+ = 빠지는 돈))."""
    parts: Counter = Counter()
    if r["채널"] == "윙":
        for x in r.get("차감 사유") or []:
            why = x.get("사유") or ETC
            parts[AD if "광고" in why else why] += num(x.get("금액"))
        rest = num(r.get("totalDeductionAmount")) - sum(parts.values())
        if round(rest):
            parts[ETC] += rest
        return (0.0 if SL.release(r) else num(r.get("paidAmount"))), num(r.get("pendingAmount")), parts
    ad, mr = num(r.get("totalAdSalesDeductionAmount")), num(r.get("totalMilkRunDeductionAmount"))
    ar = num(r.get("totalArFactoringDeductionAmount"))        # 빠른정산(셀러월렛) 상환 — 추가공제 안(KB §1-14)
    # 판매 조정(totalSalesAdjustment)은 추가공제에도 같은 금액으로 들어 있어 서로 지워짐(줄 공식 E2 와 같은 결과)
    parts.update({AD: ad, MILK: mr, FAST: ar,
                  ETC: num(r.get("totalAdditionalDeductionAmount")) - ad - mr - ar - num(r.get("totalSalesAdjustment")),
                  LOGI: num(r.get("totalFinalCfsFeeDeductionAmount")), COMP: -num(r.get("totalCfsInventoryCompensationAmount"))})
    return num(r.get("totalPayableAmount")), 0.0, parts


LEDGER, SETTLE_ONLY = "관리대장 상품", "원장 정산전용상품"


def scope(ctx, aid: str) -> tuple[str, set, set, dict]:
    """(범위, 관리 VID, 관리 노출 상품명, 관리 등록상품ID 직접 지정) — 관리대장(+ 되찾은 로켓그로스 상품) > 원장 정산전용상품."""
    if aid in ctx.ledger:
        r = ctx.rg.get(aid) or {"vids": set(), "got": [], "check": []}
        sc = LEDGER + (f" + 되찾은 로켓그로스 상품 {len(r['got'])}개" if r["got"] else "") + (
            f"(확인 필요 {len(r['check'])}개)" if r["check"] else "")
        return sc, set(ctx.ledger[aid]) | r["vids"], ctx.listings.get(aid) or set(), {}
    marks = ctx.settle_only.get(aid) or {}
    if not marks:
        return "관리 상품 자료 없음" + (f"({ctx.settle_only_err})" if ctx.settle_only_err else ""), set(), set(), {}
    if any(v not in ("관리", "본인상품") for v in marks.values()):
        return f"판정 대기(원장 정산전용상품 구분 빈 칸 {sum(v not in ('관리', '본인상품') for v in marks.values())}줄)", set(), set(), marks
    return SETTLE_ONLY, set(), set(), marks


def ratio(mset: dict, ch: str, ym: str, S: float) -> float:
    """그 줄 판매 기간의 관리 정산금 비율 — 그 달 자료가 없으면 계정 관리 정산금 비율."""
    m, a = mset.get((ch, ym), (0.0, 0.0))
    return m / a if a else S


def month_add(ym: str, n: int) -> str:
    """'YYYY-MM' + n 달 — 관리 상품이 없으면 그대로('9999-99')."""
    if ym.startswith("9999"):
        return ym
    i = int(ym[:4]) * 12 + int(ym[5:]) - 1 + n
    return f"{i // 12:04d}-{i % 12 + 1:02d}"


class AccountBase:
    """계정 하나의 계산 상태(옛 account() 지역 변수 = 속성). 메서드 호출 순서 = 옛 코드 줄 순서."""

    def __init__(self, ctx, acct: str):
        self.ctx, self.acct = ctx, acct
        self.aid = SRC.aid_of(acct)

    # ── 지급 줄(옛 270~291) ──
    def _payouts(self) -> None:
        c, acct, aid = self.ctx, self.acct, self.aid
        self.L = c.led.account(acct, SRC.per_dict(c.per), c.un[acct], c.rgf.get(aid, {}), c.aps[acct])
        self.t, self.u = c.tot[acct], c.un[acct]
        lines, self.dup = payout_lines(c.led, aid, self.L)
        self.D: Counter = Counter()
        self.rows_out, self.bad = [], 0
        self.line_info: list = []          # (상태, 판매 방식, 판매 시작 달, 정산금액, 보류 해제액, 공제 항목, 장부 줄) — 관리 상품 입금 나누기용
        for row, r in lines:
            pay, rel, parts = deductions(r)
            self.line_info.append((row[6].split(" ·")[0], r["채널"], str(row[3])[:7], pay, rel, parts, row))
            final = num(r["최종지급액"])
            self.bad += round(pay + rel - sum(parts.values())) != round(final)
            self.D.update(parts)
            self.D[REL] -= rel
            self.rows_out.append((row[2], row[3], row[4], row[1], row[5], row[6].split(" ·")[0], pay + rel, sum(parts.values()), final))
        self.fin: Counter = Counter()
        for x in self.rows_out:
            self.fin[x[5]] += x[8]
        self.fin["예정"] += self.L["buckets"]["줄 생성 전"]
        self.paid_total = sum(self.fin.values())
        self.u_sales, self.u_settle = sum(x[2] for x in self.u), sum(x[3] for x in self.u)
        self.settle_all = self.t["settle"] + self.u_settle

    # ── 관리 범위(옛 293~302) ──
    def _scope(self) -> None:
        c, aid = self.ctx, self.aid
        self.sc, self.vids, self.mnames, self.marks = scope(c, aid)
        self.scope_check = (c.rg.get(aid) or {}).get("check", [])            # 관리 상품인지 못 정한 상품(금액 밖 · 정산서에 표시)
        self.known, self.cdate = aid in c.contracts, c.contracts.get(aid)     # D-185 — 계약 달 앞 판매 = 관리 상품 아님
        self.vid_name = SCOPE.vid_names((c.daily, c.periods), aid)
        self.files = c.files.get(aid, [])
        self.opt2pid = {str(r.option_id): str(r.product_id) for f in self.files for r in f.rows if r.option_id and r.product_id}
        self.mpids = {pid for o, pid in self.opt2pid.items() if self.is_mv(o)} | {p for p, k in self.marks.items() if k == "관리"}

    def is_mv(self, v: str) -> bool:
        return v in self.vids or self.vid_name.get(v) in self.mnames or self.marks.get(self.opt2pid.get(v, "")) == "관리"

    # ── 배송비 줄(옛 303~319) ──
    def _ships(self) -> None:
        self.order_pids: dict = defaultdict(set)
        ships: dict = {}                   # 같은 배송비 줄이 주정산·최종액 등 여러 파일에 나옴 → 줄 내용으로 한 번만(실측 웰빙곳간 6,769)
        for f in self.files:
            for r in f.rows:
                if r.product_id:
                    self.order_pids[str(r.order_id)].add(str(r.product_id))
                elif f.channel == "윙" and (r.sales or r.settle):
                    ships[(str(r.order_id), r.option_id, r.recognized, r.sales, r.settle)] = (
                        str(r.order_id), r.sales, r.settle, f"{(r.recognized or f.period_end):%Y-%m}")
        ship_rows = [x[:3] for x in ships.values() if not MA.pre_contract(x[3], self.cdate)]
        self.v = verify_json(self.ctx.base, self.acct)
        self.ship = MA.ship_split(ship_rows, self.order_pids, self.mpids, self.v.get("returns") or {}, self.is_mv)
        for _o, s_, e_, ym_ in ships.values():                 # 계약 전 배송비 = 관리 밖(D-185 ②)
            if MA.pre_contract(ym_, self.cdate):
                self.ship["제외"][0] += s_
                self.ship["제외"][1] += e_
                self.ship["근거"]["계약 전"] += 1

    # ── 상품별 월별(옛 321~370) ──
    def _products(self) -> None:
        h, prow = self.ctx.st["data"]["상품별 월별"]
        ix = {c: h.index(c) for c in h}
        self.tm: Counter = Counter()
        self.tx: Counter = Counter()
        self.ship_stats = 0.0
        self.by_m: dict = defaultdict(Counter)        # 판매 달 → 물류비·재고 보상(상품 있는 줄 전체 'logi'·'comp' / 관리 'm_logi'·'m_comp')
        self.mmon: dict = defaultdict(lambda: [0.0, 0.0])
        self.msales: dict = defaultdict(lambda: [0.0, 0.0])
        self.wconf: dict = defaultdict(lambda: [0.0, 0.0, 0.0])   # 윙 구매확정 달 → [일반, 가전, 구분 모름] 판매(D-161)
        self.mset: dict = defaultdict(lambda: [0.0, 0.0])      # (판매 방식, 판매 달) → [관리 상품 정산금액, 전체 정산금액]
        self.prod: dict = {}
        self.raw_s: Counter = Counter()                        # 자동 판정 달 후보(계약 전 포함) — 달별 관리 상품 판매·물류비 합
        self.raw_l: Counter = Counter()
        for row in prow:
            if row[0] != self.acct:
                continue
            pid = str(row[ix["등록상품ID"]])
            if pid.startswith("옵션 "):
                pid = self.opt2pid.get(pid[3:], pid)
            if pid.startswith("("):                                  # (여러 상품)·(상품 미표기) 물류비 묶음
                continue
            self._product_row(row, ix, pid)

    def _product_row(self, row, ix: dict, pid: str) -> None:
        def g(c: str):
            return row[ix[c]] or 0
        ws, rs = g("윙 판매액"), g("로켓그로스 매출금액")
        settle = g("쿠팡 정산금액 합계(부가비용 차감 전)")
        ym = str(row[ix["월(매출인식)"]])[:7]
        if pid == "배송비":                                       # 주문·반품 상품을 따라 아래에서 나눔
            self.ship_stats += settle
            return
        lg, cp = g("로켓그로스 물류비(VAT포함)"), g("재고 손실 보상")
        if pid in self.mpids:
            self.raw_s[ym] += ws + rs
            self.raw_l[ym] += lg
        m = pid in self.mpids and not MA.pre_contract(ym, self.cdate)
        (self.tm if m else self.tx).update({"sales": ws + rs, "coupon": g("판매자할인쿠폰"), "fee": g("판매수수료(VAT포함)"),
                                            "settle": settle, "logi": g("로켓그로스 물류비(VAT포함)"),
                                            "comp": g("재고 손실 보상")})
        self._month_sums(pid, ym, m, (ws, rs), (g("윙 정산금액"), g("로켓그로스 정산대상액")), (lg, cp))
        if m:
            self.mmon[ym.replace("-", "")][0] += ws + rs
            self.mmon[ym.replace("-", "")][1] += settle
        e = self.prod.setdefault((pid, m), [row[ix["상품명"]] or pid, 0, 0, 0, m])   # 계약 전 판매는 '제외한 상품'(D-185)
        e[1] += g("윙 수량") + g("로켓그로스 수량")
        e[2] += ws + rs
        e[3] += settle

    def _month_sums(self, pid: str, ym: str, m: bool, sales: tuple, settles: tuple, lc: tuple) -> None:
        """달별 판매(윙·로켓그로스)·구매확정 구분(D-161)·정산금액·물류비/보상 — 전체와 관리(m) 몫."""
        ws, rs = sales
        lg, cp = lc
        for ch, s_ in (("윙", ws), ("로켓그로스", rs)):
            self.msales[(ch, ym)][1] += s_
            self.msales[(ch, ym)][0] += s_ if m else 0
        self.wconf[ym][2 if pid in self.ctx.unjudged[self.aid] else 1 if (self.ctx.svc_judge.get(pid) or {}).get("가전") else 0] += ws
        for ch, c_ in (("윙", settles[0]), ("로켓그로스", settles[1])):
            self.mset[(ch, ym)][1] += c_
            self.mset[(ch, ym)][0] += c_ if m else 0
        self.by_m[ym].update({"logi": lg, "comp": cp, "m_logi": lg if m else 0, "m_comp": cp if m else 0})

    # ── 관리 상품 판매액·취소 + 배송비 나누기(옛 371~384) ──
    def _gross_and_ship(self) -> None:
        self.gross = self.refund = 0.0      # 관리 상품 판매액(+)·취소·반품(−) — 정산 집계와 같은 줄(중복 제거)로
        for _f, r in SS._order_rows(self.files, []):
            if r.product_id and str(r.product_id) in self.mpids and not MA.pre_contract(f"{(r.recognized or _f.period_end):%Y-%m}", self.cdate):
                if r.sales >= 0:
                    self.gross += r.sales
                else:
                    self.refund += r.sales
        tm, tx, ship = self.tm, self.tx, self.ship
        for k in ("관리", "제외"):
            (tm if k == "관리" else tx).update({"sales": ship[k][0], "settle": ship[k][1]})
        ship_r = tm["settle"] / (tm["settle"] + tx["settle"]) if tm["settle"] + tx["settle"] else 0.0   # 상품을 모르는 배송비 = 확정 정산금의 관리 비율(D-162)
        tm.update({"sales": ship["확인 필요"][0] * ship_r, "settle": ship["확인 필요"][1] * ship_r})
        tx.update({"sales": ship["확인 필요"][0] * (1 - ship_r), "settle": ship["확인 필요"][1] * (1 - ship_r)})
        self.ship_u = (ship["확인 필요"][0] * ship_r, ship["확인 필요"][1] * ship_r)   # 위 관리 몫 — 검산·배송비 줄에도 같은 값
        tm["other"] = tm["sales"] - tm["coupon"] - tm["fee"] - tm["settle"]

    # ── 정산 중 판매(옛 386~410) ──
    def month_share(self, ch: str, ym: str, gate: bool = True) -> tuple[float, float, float]:
        if gate and MA.pre_contract(ym, self.cdate):             # 계약 전 달 = 관리 몫 0(D-185 ②)
            return 0.0, 0.0, 0.0
        recs = self.ctx.periods.get(self.aid) or {}
        keys = [f"M:{ym}"] if f"M:{ym}" in recs else [k for k in recs if k.startswith(f"W:{ym}")]
        mm = aa = 0.0
        for k in keys:
            for vv, o in (recs[k].get("옵션") or {}).items():
                if o.get("구분") == ch:
                    aa += num(o.get("판매금액"))
                    mm += num(o.get("판매금액")) if self.is_mv(str(vv)) else 0
        return (mm / aa if aa else 0.0), mm, aa

    def _unsettled_share(self) -> None:
        t, tm = self.t, self.tm
        self.ushare = []
        for ch, ym, s, e_, *_ in self.u:
            sh, _mm, aa_ = self.month_share(ch, ym)
            if not aa_ and not MA.pre_contract(ym, self.cdate):  # 그 달 판매분석 없음 = 상품별 확정 정산금의 관리 비율(D-162)
                sh = tm["settle"] / t["settle"] if t["settle"] else 0.0
            self.ushare.append((ch, ym, s, e_, sh, s * sh, e_ * sh))
            self.mset[(ch, ym)][1] += e_
            self.mset[(ch, ym)][0] += e_ * sh
            self.mmon[ym.replace("-", "")][0] += s * sh
            self.mmon[ym.replace("-", "")][1] += e_ * sh
        self.um_sales, self.um_settle = sum(x[5] for x in self.ushare), sum(x[6] for x in self.ushare)
        self.settle_m = tm["settle"] + self.um_settle
        self.S = self.settle_m / self.settle_all if self.settle_all else 0.0

    # ── 관리 시작 달(옛 411~418·429) ──
    def _start(self) -> None:
        # 공제 관리 몫(D-140·D-162): 관리 상품 첫 달 전 공제 = 0 · 상품별 자료 금액 그대로 · 자료 없는 공제 = 공제를 받은 줄 판매 기간의 관리 정산금 비율
        self.active = ([f"{k[:4]}-{k[4:]}" for k, (s_, _e) in self.mmon.items() if round(s_)]
                       + [ym for ym, c in self.by_m.items() if round(c["m_logi"])])
        self.start = min(self.active) if self.active else "9999-99"
        raw = {ym for ym, x in self.raw_s.items() if round(x)} | {ym for ym, x in self.raw_l.items() if round(x)}
        raw |= {ym for ch, ym, s, *_ in self.u if round(s * self.month_share(ch, ym, False)[0])}   # 정산 중 판매(상품별 자료 전)
        st_, self.start_note = MA.contract_start(min(raw) if raw else "", self.cdate, self.known)   # D-185 — 자동·계약 중 이른 달 · 계약 전 판매 제외
        if st_:
            self.start = st_
        self.share: dict = {}
        self.rates: dict = {}
        self.deduct_lines = [(x[1], x[2], x[5]) for x in self.line_info]
        self.fs = min(self.active) if self.active else self.start     # 관리 첫 판매 달(계약 전 판매 뺀 뒤) — 그 앞 = 판매 0인 달(D-186)

    def gather(self) -> None:
        """1부 — 지급 줄 → 관리 범위 → 배송비 → 상품별 → 판매액·배송비 나누기 → 정산 중 판매 → 관리 시작 달."""
        self._payouts()
        self._scope()
        self._ships()
        self._products()
        self._gross_and_ship()
        self._unsettled_share()
        self._start()
