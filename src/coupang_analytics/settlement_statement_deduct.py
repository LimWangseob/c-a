"""위탁정산서 계정 하나 — 관리 상품 몫 계산 2부(공제 몫·입금 완료/예정/보류 나누기·검산 사유). T-25 이관(옛 `statement_managed.py`
`account()` 420~527줄 + `status_split` · 계산식·순서 그대로 · 1부 = `settlement_statement_account.py`).

계정 단위 항목(D-116 ②·settlement_managed_alloc): 배송비 줄 = 같은 주문 상품 / 상품 없으면 반품 조회 상품 · 판매자서비스이용료 = 끝난 달의
구매확정 판매로 규칙 판정(D-161) → 부과 달 순서로 쿠팡 공제를 채워 그 구매확정 달 관리 판매(배송비 제외) 비율 · 안 빠진 잔액 = 공제 예정 ·
광고비 = 날짜×캠페인 청구가능액 × 그날 광고 보고서 옵션 비율 · 밀크런 = 입고 건별 적치 수량 비율 · 우대수수료 환급 = 주문 → 상품 ·
추가지급 = 옵션 → 상품. 그 자료가 없는 공제 = 공제를 받은 줄 판매 기간의 관리 정산금 비율(D-162) · 판매 0인 달 = 관리 몫 0(D-186).
입금 완료/예정/보류 = 계정 실제 지급 비율.
"""
from __future__ import annotations

from collections import Counter

from coupang_analytics import settlement_additional_pay as AP
from coupang_analytics import settlement_managed_alloc as MA
from coupang_analytics.settlement_statement_account import (
    AD, COMP, LOGI, MILK, REL, STS, SVC, AccountBase, ad_files, milk_rows, month_add, num, ratio)


def status_split(line_info: list, gen: dict, mset: dict, settle_m: float, rates: dict, S: float):
    """관리 상품 몫을 쿠팡 지급 줄마다 나눠 입금 완료·예정·보류로 더한다(소유자 2026-10-27).
    정산금액 = 관리 상품 정산 총액(②)을 '줄 지급대상 × 그 줄 판매 달·판매 방식의 관리 상품 정산 비율' 가중으로 나눔(합 = ② 그대로) ·
    공제 = 그 줄에서 실제 빠진 항목 금액 × 항목 몫 비율 · rates = {항목: (이 판매 달부터, 비율)} — 관리 시작 전 판매 줄은 0(합 = 공제 관리 몫 그대로) ·
    줄 생성 전 몫 = 예정.
    반환: ({상태: 정산금액}, {상태: {항목: 공제}}, [(장부 줄|None, 상태, 관리 정산금액, 관리 공제)])."""
    items = [(st, pay * ratio(mset, ch, ym, S), parts, row) for st, ch, ym, pay, _rel, parts, row in line_info]
    items += [("예정", amt * ratio(mset, ch, ym, S), Counter(), None) for (ch, ym), amt in gen.items() if amt]
    wsum = sum(x[1] for x in items)
    st_settle: dict = dict.fromkeys(STS, 0.0)
    st_ded: dict = {st: Counter() for st in STS}
    line_m = []

    def rate(k: str, row) -> float:
        since, r = rates.get(k, ("", 0.0))
        return r if row is not None and str(row[3])[:7] >= since else 0.0
    for st, w, parts, row in items:
        sm = settle_m * w / wsum if wsum else 0.0
        dm = Counter({k: x * rate(k, row) for k, x in parts.items() if x})
        st_settle[st] += sm
        st_ded[st].update(dm)
        line_m.append((row, st, sm, sum(dm.values())))
    return st_settle, st_ded, line_m


def _ad_since(bill: dict, since: str) -> dict:
    return {k: x for k, x in bill.items() if f"{str(k[0])[:4]}-{str(k[0])[4:6]}" >= since}


class Account(AccountBase):
    """계정 하나 전체 — `run()` = 1부 gather → 2부 공제 → 결과 사전(옛 account() 반환과 같은 키)."""

    def due(self, k: str, since: str) -> float:
        return MA.due_since([(x[2], x[5]) for x in self.line_info], k, since)

    def line_ratio(self, ch: str, ym: str) -> float:
        return ratio(self.mset, ch, ym, self.S)

    def put(self, k: str, since: str, actual: float, covered: float, how: str, kind: str,
            fs_since: str = "", fs_actual: float = 0.0, fs_covered: float = 0.0) -> None:
        d = self.due(k, since)
        fs_since = fs_since or self.fs
        r_since, r_d = since, d
        if fs_since > since:                              # 판매 0인 달 = 자료 없는 공제의 나눌 금액·평균 양쪽에서 뺌(D-186)
            r_since, r_d = fs_since, self.due(k, fs_since)     # 입금 완료/예정 나누기도 첫 판매 달부터의 줄로(판매 0인 달 줄 = 0)
            amt, miss = MA.gap_free(actual, fs_actual, fs_covered, r_d, MA.line_share(self.deduct_lines, k, fs_since, self.line_ratio))
        else:
            amt, miss = MA.scoped(actual, d, covered)
            amt += miss * MA.line_share(self.deduct_lines, k, since, self.line_ratio)
        self.rates[k] = (r_since, amt / r_d if r_d else 0.0)
        D = self.D
        self.share[k] = (amt / D[k] if D[k] else 0.0,
                         how + (f" · 관리 시작 {self.start} 전 판매분 공제 제외" if self.active else " · 관리 상품 없음")
                         + (f" · 상품 자료 없는 {abs(miss):,.0f}원 = 공제 받은 줄 판매 기간의 관리 정산금 비율" if round(miss) else ""),
                         "관리 기간 공제 없음" if not round(d) else kind)

    # ── 물류비·재고 보상(옛 446~449) ──
    def _logi_comp(self) -> None:
        keys = ("logi", "comp", "m_logi", "m_comp")
        c_ = {k: sum(c[k] for ym, c in self.by_m.items() if ym >= self.start) for k in keys}
        f_ = {k: sum(c[k] for ym, c in self.by_m.items() if ym >= self.fs) for k in keys}
        self.put(LOGI, self.start, c_["m_logi"], c_["logi"], "상품별 물류비 리포트의 관리 상품 금액", "쿠팡 자료", self.fs, f_["m_logi"], f_["logi"])
        self.put(COMP, self.start, -c_["m_comp"], -c_["comp"], "상품별 재고 보상의 관리 상품 금액", "쿠팡 자료", self.fs, -f_["m_comp"], -f_["comp"])

    # ── 판매자서비스이용료(옛 450~470 · D-161) ──
    def svc_month(self, ym: str) -> tuple:
        """구매확정 달 관리 판매 — 상품별 파일이 다 온 달 = 그 값 · 덜 온 달 = 그 달 판매분석 · 둘 다 없음 = 계정 관리 정산금 비율(D-162)."""
        mm_, aa_ = self.msales.get(("윙", ym), (0.0, 0.0))
        if aa_ and self.pur.get(ym, 0.0) - sum(self.wconf[ym]) <= 1:
            return mm_, aa_
        _s, mm_, aa_ = self.month_share("윙", ym)
        return (mm_, aa_) if aa_ else (self.S, 1.0)

    def _svc(self) -> None:
        # 끝난 달만 구매확정 판매로 판정 · 정산 파일이 덜 온 달은 구매확정 리포트와의 차액을 '구분 모름'으로
        wconf, D = self.wconf, self.D
        self.pur = {f"{k[:4]}-{k[4:]}": sum(num(x.get("productRevenueAmount")) for x in (m_ or {}).get("purchaseReports") or [])
                    for k, m_ in (self.v.get("purchase") or {}).items()}
        conf = {ym: (wconf[ym][0], wconf[ym][1], wconf[ym][2] + max(self.pur.get(ym, 0.0) - sum(wconf[ym]), 0.0))
                for ym in set(wconf) | set(self.pur)}
        charged = MA.svc_charges(conf, month_add(self.ctx.basis[:7], -1))
        sv = self.sv = MA.svc_settle(charged, D[SVC], {ym: self.svc_month(ym) for ym in charged})
        sv_out = sv["규칙 밖"] * MA.line_share(self.deduct_lines, SVC, "", self.line_ratio)
        if D[SVC] or charged:
            sv_r = (sv["공제 관리"] + sv_out) / D[SVC] if D[SVC] else 0.0
            self.rates[SVC] = ("", sv_r)
            self.share[SVC] = (sv_r, f"구매확정 달 규칙(부과 {len(charged)}개월 {sum(charged.values()):,.0f}원) · 부과 달 순서로 쿠팡 공제를 채워 그 달 관리 판매 비율"
                               + (f" · 규칙보다 더 빠진 {sv['규칙 밖']:,.0f}원 = 공제 받은 줄 판매 기간의 관리 정산금 비율" if round(sv["규칙 밖"]) else "")
                               + (f" · 아직 안 빠진 {sv['잔액 전체']:,.0f}원 중 관리 몫 {sv['잔액 관리']:,.0f}원은 공제 예정" if round(sv["잔액 전체"]) else ""), "쿠팡 자료 비율")

    # ── 광고비·밀크런(옛 471~484) ──
    def _ads(self) -> None:
        pa, bill, have = ad_files(self.ctx.base, self.acct)
        ad = MA.ad_share(pa, _ad_since(bill, self.start), self.is_mv, have)
        a_m, a_t = (ad[0], ad[1]) if ad else (0.0, 0.0)
        adf = MA.ad_share(pa, _ad_since(bill, self.fs), self.is_mv, have) if self.fs > self.start else ad
        self.put(AD, self.start, a_m * 1.1, a_t * 1.1,
                 "날짜×캠페인 청구가능 광고비 × 그날 광고 보고서 옵션별 비율 + 부가세" + (f" · {ad[2]}" if ad and ad[2] else ""), "쿠팡 자료 비율",
                 self.fs, (adf[0] * 1.1) if adf else 0.0, (adf[1] * 1.1) if adf else 0.0)

    def _milk(self) -> None:
        base, inbound = self.ctx.base, self.v.get("inbound") or []
        since_mk = month_add(self.start, -1)                   # 밀크런 = 입고가 판매보다 먼저 — 파일·공제 둘 다 관리 시작 전달부터(D-154)
        mk = MA.milk_share(milk_rows(base, self.acct, since_mk.replace("-", "")), inbound, self.is_mv)
        k_m, k_t = (mk[0], mk[1]) if mk else (0.0, 0.0)
        fs_mk = month_add(self.fs, -1)                         # 밀크런 = 첫 판매 전달부터(D-154 와 같은 한 달 앞)
        mkf = MA.milk_share(milk_rows(base, self.acct, fs_mk.replace("-", "")), inbound, self.is_mv) if self.fs > self.start else mk
        self.put(MILK, since_mk, k_m, k_t, "밀크런마다 입고 건 상품 적치 수량 비율" + (f" · {mk[2]}" if mk and mk[2] else ""), "쿠팡 자료 비율",
                 fs_mk, mkf[0] if mkf else 0.0, mkf[1] if mkf else 0.0)

    # ── 나머지 항목·보류 해제·입금 나누기(옛 485~499) ──
    def _rest_and_status(self) -> None:
        D, share, sv = self.D, self.share, self.sv
        for k in sorted(set(D) - set(share) - {REL}):
            self.put(k, self.start, 0.0, 0.0, "쿠팡이 상품 구분 없이 준 항목", "쿠팡 자료")
        rel_m = {st: -sum(x[4] * self.line_ratio(x[1], x[2]) for x in self.line_info if x[2] >= self.start and x[0] == st)
                 for st in STS}   # 공제 부호 = 음수(받은 돈)
        if D[REL]:
            share[REL] = (sum(rel_m.values()) / D[REL], "공제 받은 줄 판매 기간의 관리 정산금 비율"
                          + (f" · 관리 시작 {self.start} 전 판매분 제외" if self.active else ""), "쿠팡 자료 비율")
        self.Dm = {k: x * share[k][0] for k, x in D.items() if round(x)}
        if round(sv["잔액 관리"]):
            self.Dm[SVC] = self.Dm.get(SVC, 0.0) + sv["잔액 관리"]
        self.pay_m = self.settle_m - sum(self.Dm.values())
        self.st_settle, self.st_ded, self.line_m = status_split(self.line_info, self.L["gen"], self.mset, self.settle_m, self.rates, self.S)
        for st in STS:
            self.st_ded[st][REL] += rel_m[st]
        if round(sv["잔액 관리"]):                          # 부과는 확정·쿠팡이 아직 안 뺀 돈 = 공제 예정(D-161)
            self.st_ded["예정"][SVC] += sv["잔액 관리"]
            self.line_m.append((None, "예정", 0.0, sv["잔액 관리"]))

    # ── 별도 입금(옛 500~507) ──
    def _extra_in(self) -> None:
        cdate, v = self.cdate, self.v
        fav_rows = [(x.get("orderId"), num(x.get("refundAmount"))) for mth in (v.get("favorable") or {}).values()
                    for x in ((mth or {}).get("rows") or [])]
        order_ym = {str(r.order_id): f"{(r.recognized or f.period_end):%Y-%m}" for f in self.files for r in f.rows if r.product_id}
        pids_g = {o: (p if not MA.pre_contract(order_ym.get(o, "9999-99"), cdate) else {"(계약 전)"}) for o, p in self.order_pids.items()}
        self.fav = MA.order_share(fav_rows, pids_g, self.mpids) if fav_rows else None
        self.add = AP.summarize(AP.months_of(self.ctx.base, self.acct, self.ctx.snaps.get(self.aid)))
        self.addm = MA.vid_share([(x["옵션ID"], num(x["지급금액"]) if not MA.pre_contract(str(x.get("지급일") or "")[:7], cdate) else 0)
                                  for x in self.add["줄"] if x["지급구분"] == AP.PAID], self.is_mv)

    # ── 쿠팡 대조 사유(옛 508~521) ──
    def _why(self) -> list:
        L, why = self.L, []
        if L["e1_bad"]:
            why.append("E1 " + "; ".join(f"{c} {m_} 정산 {a:,} vs 줄 {g:,}" for c, m_, a, g, _ in L["e1_bad"][:2]))
        if L["e2_bad"]:
            why.append(f"E2 줄 공식 다름 {len(L['e2_bad'])}줄")
        if L["e3"][0] != L["e3"][1]:
            why.append(f"E3 보류 줄 {L['e3'][0]:,} vs 보류목록 {L['e3'][1]:,}")
        if any(x[4] in ("자료 없음", "확인 필요") for x in self.u):
            why.append("④ 정산 중 판매 일부 자료 없음")
        if self.bad:
            why.append(f"지급 줄 공식 어긋남 {self.bad}")
        if self.start_note:
            why.append(self.start_note)
        return why

    def run(self) -> dict:
        self.gather()
        self._logi_comp()
        self._svc()
        self._ads()
        self._milk()
        self._rest_and_status()
        self._extra_in()
        why = self._why()
        g = self.__dict__
        out = {k: g[k] for k in ("acct", "aid", "t", "u", "L", "D", "Dm", "share", "fin", "gross", "refund", "st_settle", "st_ded",
                                 "line_m", "paid_total", "rows_out", "dup", "bad", "mpids", "tm", "tx", "prod", "mmon", "ushare",
                                 "u_sales", "um_sales", "um_settle", "settle_all", "settle_m", "pay_m", "ship", "ship_u", "ship_stats",
                                 "fav", "add", "addm", "start_note")}
        out.update({"info": self.ctx.names[self.acct], "ok": self.L["ok"] and not self.bad, "why": why, "scope": self.sc, "scope_check": self.scope_check,
                    "month_share": self.month_share, "extras": self.ctx.extras.get(self.aid, [])})
        return out


def account(ctx, acct: str) -> dict:
    """계정 하나 → 옛 account() 와 같은 결과 사전."""
    return Account(ctx, acct).run()
