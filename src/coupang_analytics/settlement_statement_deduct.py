"""위탁정산서 계정 하나 — 관리 상품 몫 계산 2부(공제 몫·입금 완료/예정/보류 나누기·검산 사유). T-25 이관(옛 `statement_managed.py`
`account()` 420~527줄 + `status_split` · 계산식·순서 그대로 · 1부 = `settlement_statement_account.py`).

계정 단위 항목(D-116 ②·settlement_managed_alloc): 배송비 줄 = 같은 주문 상품 / 상품 없으면 반품 조회 상품 · 판매자서비스이용료·비즈니스 인사이트·세이버 구독료
(계정 정액) = 그 달 등록 상품 비율(D-271 · 새 정산서와 같은 상품표 `reg_rows`) · 이용료 규칙 판정(D-161 끝난 달 구매확정 판매)의 안 빠진 잔액 = 공제 예정 ·
광고비 = 날짜×캠페인 청구가능액 × 그날 광고 보고서 옵션 비율 · 밀크런 = 입고 건별 적치 수량 비율 · 우대수수료 환급 = 주문 → 상품 ·
추가지급 = 옵션 → 상품. 그 자료가 없는 공제 = 공제를 받은 줄 판매 기간의 관리 정산금 비율(D-162) · 판매 0인 달 = 관리 몫 0(D-186).
입금 완료/예정/보류 = 계정 실제 지급 비율.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, timedelta

from coupang_analytics import settlement_additional_pay as AP
from coupang_analytics import settlement_ledger as SL
from coupang_analytics import settlement_managed_alloc as MA
from coupang_analytics import settlement_statement_cfs as CFS
from coupang_analytics.settlement_consignor_month_cost import reg_rows
from coupang_analytics.settlement_statement_account import (
    AD, BI, COMP, LOGI, MILK, OWN, REL, SAVER, STS, SVC, AccountBase, ad_files, late_final_notes, milk_rows, month_add, num, ratio)


def status_split(line_info: list, gen: dict, mset: dict, settle_m: float, rates: dict, S: float, exact: dict | None = None):
    """관리 상품 몫을 쿠팡 지급 줄마다 나눠 입금 완료·예정·보류로 더한다(소유자 2026-10-27).
    정산금액 = 그 줄 실제 관리 몫 '줄 지급대상 × 그 줄 판매 달·판매 방식의 관리 상품 정산 비율'(배율 없음 · D-294 ①) ·
    관리 상품 정산 총액(②) 중 지급 줄·줄 생성 전 몫에 없는 잔액 = '입금 예정(지급일 미정)' 한 줄(끝난 줄에 퍼뜨리지 않음 · D-294 ②) ·
    공제 = 그 줄에서 실제 빠진 항목 금액 × 항목 몫 비율 · rates = {항목: (이 판매 달부터, 비율)} — 관리 시작 전 판매 줄은 0(합 = 공제 관리 몫 그대로) ·
    exact = {(id(장부 줄), 항목): 관리 공제} 가 있는 줄·항목은 비율 대신 그 값(지급 끝난 줄의 물류비·재고 보상 실제 관리 몫 · 비용 리포트 없는 예정 줄 물류비 예상 몫 · T-130) ·
    줄 생성 전 몫 = 예정.
    반환: ({상태: 정산금액}, {상태: {항목: 공제}}, [(장부 줄|None, 상태, 관리 정산금액, 관리 공제)])."""
    items = [(st, pay * ratio(mset, ch, ym, S), parts, row) for st, ch, ym, pay, _rel, parts, row in line_info]
    items += [("예정", amt * ratio(mset, ch, ym, S), Counter(), None) for (ch, ym), amt in gen.items() if amt]
    rest = settle_m - sum(x[1] for x in items)
    if round(rest):
        items.append(("예정", rest, Counter(), None))
    st_settle: dict = dict.fromkeys(STS, 0.0)
    st_ded: dict = {st: Counter() for st in STS}
    line_m = []

    def rate(k: str, row) -> float:
        since, r = rates.get(k, ("", 0.0))
        return r if row is not None and str(row[3])[:7] >= since else 0.0
    for st, sm, parts, row in items:
        dm = Counter({k: (exact or {}).get((id(row), k), x * rate(k, row)) for k, x in parts.items() if x})
        st_settle[st] += sm
        st_ded[st].update(dm)
        line_m.append((row, st, sm, sum(dm.values())))
    return st_settle, st_ded, line_m


def _ad_since(bill: dict, since: str) -> dict:
    return {k: x for k, x in bill.items() if f"{str(k[0])[:4]}-{str(k[0])[4:6]}" >= since}


class Account(AccountBase):
    """계정 하나 전체 — `run()` = 1부 gather → 2부 공제 → 결과 사전(옛 account() 반환과 같은 키)."""
    exact: dict = {}                # {(id(장부 줄), 항목): 관리 공제} — _cfs_lines 가 계정마다 새로 만듦
    cfs_why: list = []              # 줄 원문·리포트로 못 정한 물류비·보상 = '확인 필요' 사유
    plan_in: tuple | None = None    # 예정 줄 물류비 입력(예정 줄 · 주기 · 주기 시작) — 계약 묶음 나누기(settlement_seldoc_groups)가 다시 씀
    plan_how = f"그 주기 로켓그로스 판매 비율 × 직전 {CFS.PLAN_WEEKS}주기 물류비 환산"

    def due(self, k: str, since: str) -> float:
        return MA.due_since([(x[2], x[5]) for x in self.line_info], k, since)

    def line_ratio(self, ch: str, ym: str) -> float:
        return ratio(self.mset, ch, ym, self.S)

    def win(self, ym: str = "") -> str:
        """공제 관리 몫 자료 창 시작 = max(그 달(기본 관리 시작 달), 2026-01) — 2025 판매 줄은 공제까지 빠짐(D-329 · D-342) · 관리 시작 표시(D-185)는 self.start 그대로."""
        return max(ym or self.start, SL.SALE_FROM[:7])

    def reg(self, ym: str) -> float | None:
        """D-271 계정 정액 관리 몫 = 그 달 등록 상품 비율(등록상품 ID 중 관리 ÷ 전체 · 판매중지 포함) — 새 정산서와 같은 상품표
        (정산 기준일 상품조회 사본 · `reg_rows`) · 계약 전 달 = 0 · 상품조회 자료 없음 = None."""
        inv = self.ctx.inv.get(self.aid) or {}
        if not inv:
            return None
        pre = MA.pre_contract(ym, self.cdate)
        memo = self.__dict__.setdefault("_reg_memo", {})
        if pre not in memo:
            rows = reg_rows(inv, self.mpids, self.is_mv, pre)
            memo[pre] = (sum(r["관리"] for r in rows), len(rows))
        mm, n = memo[pre]
        return mm / n

    def fixed_fee(self, k: str) -> float:
        """계정 정액(D-271) — 관리 시작 뒤 공제 받은 줄마다 그 줄 판매 달 등록 비율 · rates·share 를 채우고 관리 몫 합을 돌려줌."""
        since, D = self.win(), self.D
        due = self.due(k, since)
        got = sum(parts.get(k, 0.0) * (self.reg(ym) or 0.0) for _ch, ym, parts in self.deduct_lines if ym >= since)
        self.rates[k] = (since, got / due if due else 0.0)
        self.reg("9999-12")                                   # 계약 뒤 달 비율(설명 글) — 상품표를 한 번 만들어 둠
        mm, n = self._reg_memo[False]
        self.share[k] = (got / D[k] if D[k] else 0.0,
                         f"계정 정액 = 그 달 등록 상품 비율 {mm}/{n}(등록상품 ID · 판매중지 포함 · 정산 기준일 상품조회 · D-271)"
                         + (f" · 관리 시작 {self.start} 전 판매분 공제 제외" if self.active else " · 관리 상품 없음"),
                         "관리 기간 공제 없음" if not round(due) else "등록 상품 비율")
        return got

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
        c_ = {k: sum(c[k] for ym, c in self.by_m.items() if ym >= self.win()) for k in keys}
        f_ = {k: sum(c[k] for ym, c in self.by_m.items() if ym >= self.fs) for k in keys}
        self.put(LOGI, self.win(), c_["m_logi"], c_["logi"], "상품별 물류비 리포트의 관리 상품 금액", "쿠팡 자료", self.fs, f_["m_logi"], f_["logi"])
        self.put(COMP, self.win(), -c_["m_comp"], -c_["comp"], "상품별 재고 보상의 관리 상품 금액", "쿠팡 자료", self.fs, -f_["m_comp"], -f_["comp"])
        self._cfs_lines()

    # ── 물류비·재고 보상 — 지급 끝난 줄 = 그 줄 실제 관리 몫(T-130 · D-294 ①) · 비용 리포트 없는 예정 줄 물류비 = 예상 몫(D-414 · D-415) ──
    def _is_mpid(self, pid: str, ym: str) -> bool:
        return pid in self.mpids and not MA.pre_contract(ym, self.cdate)

    def _lines_with(self, st: str, *keys) -> list:
        """그 상태 지급 줄 중 이 항목 공제가 있는 줄 [(판매 달, 공제 항목, 장부 줄)]."""
        return [(x[2], x[5], x[6]) for x in self.line_info if x[0] == st and any(round(x[5].get(k, 0.0)) for k in keys)]

    def _cfs_lines(self) -> None:
        """지급 끝난 줄: 물류비 = 쿠팡 상세가 적은 갚은 정산주기마다 그 주기 비용 리포트 관리 비율 · 재고 보상 = 자기 주기 보상 리포트 관리 비율.
        예정 줄 물류비 = 비용 리포트 없는 주기면 `_plan_logi`. 관리 몫 합도 그 합(+ 나머지 줄 = put 의 전 기간 비율).
        그 밖 예정·보류 줄 · 상세 없는 줄 · 리포트와 안 맞는 주기 = put 비율 그대로 + 지급 끝난 줄이면 '확인 필요'(D-146 추정 금지)."""
        done, plan = self._lines_with(STS[0], LOGI, COMP), self._lines_with(STS[1], LOGI)
        self.exact, self.cfs_why = {}, []
        if not self.active or not (done or plan):
            return
        raw = {id(row): r for row, r in self.lines}
        rows = {json.dumps(r, sort_keys=True, ensure_ascii=False, default=str): r for r in self.ctx.led.rg_rows(self.aid)}
        logi, comp, starts = CFS.read_costs(self.ctx.base, self.acct)
        per, miss = CFS.periods(list(rows.values()), logi), {LOGI: Counter(), COMP: Counter()}
        self._plan_logi([(parts[LOGI], row, raw[id(row)]) for _ym, parts, row in plan if raw[id(row)]["기간 끝"] not in logi], per, starts)
        self._done_lines(done, raw, per, (comp, rows.values()), miss)
        for k, how in ((LOGI, "쿠팡 상세가 적은 갚은 정산주기 비용 리포트"), (COMP, "자기 정산주기 재고 보상 리포트")):
            if done or any(key[1] == k for key in self.exact):
                self._cfs_share(k, how, miss[k])

    def _done_lines(self, done: list, raw: dict, per: dict, comp: tuple, miss: dict) -> None:
        for ym, parts, row in done:
            r = raw.get(id(row)) or {}
            if round(parts.get(LOGI, 0.0)):
                self.exact[(id(row), LOGI)] = self._cfs_logi(per, ym, parts[LOGI], row, r, miss[LOGI])
            if round(parts.get(COMP, 0.0)):
                self.exact[(id(row), COMP)] = self._cfs_comp(*comp, parts[COMP], row, r, miss[COMP])

    def _plan_logi(self, plan: list, per: dict, starts: dict) -> None:
        """비용 리포트가 아직 없는 주기의 예정 줄 물류비 관리 몫 = 공제 × min(1, r × k)(D-414 · D-415) — 앞 주기 = 쿠팡 줄과 맞는 리포트가 있는 2026 주기 ·
        판매분석으로 r 을 못 내는 줄 = 전 기간 비율 그대로 + '확인 필요'."""
        if not plan:
            return
        self.plan_in, lost = (plan, per, starts), 0.0
        for (amt, row, _raw), rate in zip(plan, self.plan_shares(), strict=True):
            if rate is None:
                lost += amt
            else:
                self.exact[(id(row), LOGI)] = amt * rate
        if round(lost):
            self.cfs_why.append(f"확인 필요 — {LOGI} 예정 줄 {lost:,.0f}원은 판매분석 로켓그로스 판매로 관리 비율을 못 내 전 기간 비율 그대로(D-414 ①)")

    def plan_shares(self) -> list:
        """예정 줄마다 관리 비율(못 냄 = None)."""
        got = self.plan_rates(lambda v, ym: self.is_mv(v) and not MA.pre_contract(ym, self.cdate), self._is_mpid)
        return [None if x is None else x[1] for x in got]

    def plan_rates(self, sold, cost) -> list:
        """예정 줄마다 (r, min(1, r × k)) · 판매분석으로 r 을 못 냄 = None — sold(옵션, 달)·cost(등록상품ID, 달) = 관리 판정."""
        assert self.plan_in is not None
        plan, per, starts = self.plan_in
        daily, cut = self.ctx.daily.get(self.aid) or {}, date.fromisoformat(str(self.ctx.basis)[:10]) - timedelta(days=1)
        memo: dict = {}

        def r_of(start: str, end: str) -> float | None:
            if (start, end) not in memo:
                memo[start, end] = CFS.sale_ratio(daily, sold, start, end, cut)
            return memo[start, end]
        past = [(e, sum(x[2] for x in p.base()), *p.shares(cost), r_of(starts[e], e) or 0.0)
                for e, p in sorted(per.items()) if e >= SL.SALE_FROM and not p.why()]
        rs = [(r_of(str(raw["기간 시작"])[:10], str(raw["기간 끝"])[:10]), raw["기간 끝"]) for _amt, _row, raw in plan]
        return [None if r is None else (r, CFS.plan_rate(r, [x[1:] for x in past if x[0] < end])) for r, end in rs]

    def _rate(self, k: str, row) -> float:
        since, r = self.rates[k]
        return r if str(row[3])[:7] >= since else 0.0

    def _cfs_logi(self, per: dict, ym: str, amt: float, row, r: dict, miss: Counter) -> float:
        paid = CFS.paid_periods(r) if r else None
        if paid is None:
            miss["갚은 정산주기 상세 없음"] += amt
            return amt * self._rate(LOGI, row)
        got = 0.0
        for end, x in paid:
            why = per[end].why()
            if why:
                miss[f"{end} 주기 {why}"] += x
                got += x * self._rate(LOGI, row)
                continue
            m, unk = per[end].shares(self._is_mpid)
            got += x * (m + unk * self.line_ratio("로켓그로스", ym))       # 상품 미표기 줄 = 공제 받은 줄 판매 기간 관리 비율(D-162)
        return got

    def _cfs_comp(self, comp: dict, rows, amt: float, row, r: dict, miss: Counter) -> float:
        end = str(r.get("기간 끝") or "")
        xs = comp.get(end) or []
        total = sum(x for _o, _ym, x in xs)
        if not xs or abs(total - sum(num(y.get(CFS.COMP)) for y in rows if y["기간 끝"] == end)) > 1:
            miss[f"{end} 주기 재고 보상 리포트 " + ("≠ 쿠팡 줄" if xs else "없음")] += amt
            return amt * self._rate(COMP, row)
        pairs = self.ctx.cost_opts.get(self.aid) or {}

        def pid(o: str) -> str:
            p = str((pairs.get(o) or ("",))[0])
            return p if p and not p.startswith("옵션 ") else self.opt2pid.get(o, p)
        return amt * sum(x for o, ym, x in xs if self._is_mpid(pid(o), ym)) / total

    def _cfs_share(self, k: str, how: str, miss: Counter) -> None:
        D, by = self.D, defaultdict(float)
        for x in self.line_info:
            amt = x[5].get(k, 0.0)
            by[x[0] if (id(x[6]), k) in self.exact else "나머지"] += self.exact.get((id(x[6]), k), amt * self._rate(k, x[6]))
        if not round(D[k]):
            self.exact = {key: v for key, v in self.exact.items() if key[1] != k}
            return
        _r, text, kind = self.share[k]
        self.share[k] = (sum(by.values()) / D[k], f"지급 끝난 줄 = {how}의 관리 상품 금액(관리 {by[STS[0]]:,.0f}원 · T-130)"
                         + (f" · 비용 리포트 없는 예정 줄 = {self.plan_how}"
                            f"(관리 {by[STS[1]]:,.0f}원 · D-414·D-415)" if STS[1] in by else "")
                         + (f" · 예정·보류 줄 = {text}" if round(by["나머지"]) else ""), kind)
        if round(sum(miss.values())):
            self.cfs_why.append(f"확인 필요 — {k} 지급 끝난 줄 {sum(miss.values()):,.0f}원은 쿠팡 원문으로 관리 몫을 못 정해 전 기간 비율 그대로("
                                + " · ".join(f"{w} {x:,.0f}원" for w, x in sorted(miss.items()) if round(x)) + ")")

    # ── 판매자서비스이용료(옛 450~470 · D-161) ──
    def svc_month(self, ym: str) -> tuple:
        """구매확정 달 관리 판매 — 상품별 파일이 다 온 달 = 그 값 · 덜 온 달 = 파일 + 정산 예정분 나눈 값(D-262 · '확인 필요' 금액 뺌) ·
        둘 다 없음 = 계정 관리 정산금 비율(D-162)."""
        mm_, aa_ = self.msales.get(("윙", ym), (0.0, 0.0))
        if aa_ and self.pur.get(ym, 0.0) - sum(self.wconf[ym]) <= 1:
            return mm_, aa_
        p = self.upend.get(("윙", ym)) or [0.0, 0.0, 0.0]
        mm_, aa_ = mm_ + p[1], aa_ + p[0]
        return (mm_, aa_) if aa_ else (self.S, 1.0)

    def _svc(self) -> None:
        # 끝난 달만 구매확정 판매로 판정 · 정산 파일이 덜 온 달은 구매확정 리포트와의 차액을 '구분 모름'으로
        wconf, D = self.wconf, self.D
        self.pur = {f"{k[:4]}-{k[4:]}": sum(num(x.get("productRevenueAmount")) for x in (m_ or {}).get("purchaseReports") or [])
                    for k, m_ in (self.v.get("purchase") or {}).items()}
        conf = {ym: (wconf[ym][0], wconf[ym][1], wconf[ym][2] + max(self.pur.get(ym, 0.0) - sum(wconf[ym]), 0.0))
                for ym in set(wconf) | set(self.pur)}
        charged = MA.svc_charges(conf, month_add(self.ctx.basis[:7], -1))
        if self.reg(self.win()) is not None:                 # D-271 등록 비율 · 규칙 잔액(D-161 공제 예정)도 그 부과 달 등록 비율
            self.sv = MA.svc_settle(charged, D[SVC], {ym: (self.reg(ym) or 0.0, 1.0) for ym in charged})
            if D[SVC] or charged:
                self.fixed_fee(SVC)
                if round(self.sv["잔액 전체"]):
                    r, how, kind = self.share[SVC]
                    self.share[SVC] = (r, how + f" · 아직 안 빠진 규칙 부과(D-161) {self.sv['잔액 전체']:,.0f}원 중 관리 몫 "
                                       f"{self.sv['잔액 관리']:,.0f}원은 공제 예정", kind)
            return
        sv = self.sv = MA.svc_settle(charged, D[SVC], {ym: self.svc_month(ym) for ym in charged})   # 상품조회 자료 없음 = D-161 판매 비율
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
        ad = MA.ad_share(pa, _ad_since(bill, self.win()), self.is_mv, have)
        a_m, a_t = (ad[0], ad[1]) if ad else (0.0, 0.0)
        adf = MA.ad_share(pa, _ad_since(bill, self.fs), self.is_mv, have) if self.fs > self.win() else ad
        self.put(AD, self.win(), a_m * 1.1, a_t * 1.1,
                 "날짜×캠페인 청구가능 광고비 × 그날 광고 보고서 옵션별 비율 + 부가세" + (f" · {ad[2]}" if ad and ad[2] else ""), "쿠팡 자료 비율",
                 self.fs, (adf[0] * 1.1) if adf else 0.0, (adf[1] * 1.1) if adf else 0.0)

    def _milk(self) -> None:
        base, inbound = self.ctx.base, self.v.get("inbound") or []
        since_mk = self.win(month_add(self.start, -1))         # 밀크런 = 입고가 판매보다 먼저 — 파일·공제 둘 다 관리 시작 전달부터(D-154 · 2025 달이면 2026-01부터 D-342)
        mk = MA.milk_share(milk_rows(base, self.acct, since_mk.replace("-", "")), inbound, self.is_mv)
        k_m, k_t = (mk[0], mk[1]) if mk else (0.0, 0.0)
        fs_mk = self.win(month_add(self.fs, -1))               # 밀크런 = 첫 판매 전달부터(D-154 와 같은 한 달 앞 · D-342)
        mkf = MA.milk_share(milk_rows(base, self.acct, fs_mk.replace("-", "")), inbound, self.is_mv) if fs_mk > since_mk else mk
        self.put(MILK, since_mk, k_m, k_t, "밀크런마다 입고 건 상품 적치 수량 비율" + (f" · {mk[2]}" if mk and mk[2] else ""), "쿠팡 자료 비율",
                 fs_mk, mkf[0] if mkf else 0.0, mkf[1] if mkf else 0.0)

    # ── 나머지 항목·보류 해제·입금 나누기(옛 485~499) ──
    def _rest_and_status(self) -> None:
        D, share, sv = self.D, self.share, self.sv
        for k in [k for k in D if k.startswith(OWN)]:     # 위탁자 본인 차감 = 관리 몫 0(D-312 ②)
            self.rates[k] = ("", 0.0)
            share[k] = (0.0, "위탁자 개인 대출 상환·체크카드 대금 — 쿠팡이 계정 정산에서 뺀 돈 · 관리 상품 몫 0(D-312)", OWN)
        for k in (BI, SAVER):                               # 74 비즈니스 인사이트·세이버 구독료 = 계정 정액(D-271)
            if D[k] and self.reg(self.win()) is not None:
                self.fixed_fee(k)
        for k in sorted(set(D) - set(share) - {REL}):
            self.put(k, self.win(), 0.0, 0.0, "쿠팡이 상품 구분 없이 준 항목"
                     + (" · 상품조회 자료 없어 D-271 등록 비율 못 씀" if k in (BI, SAVER) else ""), "쿠팡 자료")
        rel_m = {st: -sum(x[4] * self.line_ratio(x[1], x[2]) for x in self.line_info if x[2] >= self.start and x[0] == st)
                 for st in STS}   # 공제 부호 = 음수(받은 돈)
        if D[REL]:
            share[REL] = (sum(rel_m.values()) / D[REL], "공제 받은 줄 판매 기간의 관리 정산금 비율"
                          + (f" · 관리 시작 {self.start} 전 판매분 제외" if self.active else ""), "쿠팡 자료 비율")
        self.Dm = {k: x * share[k][0] for k, x in D.items() if round(x)}
        if round(sv["잔액 관리"]):
            self.Dm[SVC] = self.Dm.get(SVC, 0.0) + sv["잔액 관리"]
        self.pay_m = self.settle_m - sum(self.Dm.values())
        self.st_settle, self.st_ded, self.line_m = status_split(self.line_info, self.L["gen"], self.mset, self.settle_m, self.rates, self.S, self.exact)
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
        if self.ucheck:
            why.append(f"④ 정산 예정분 관리 몫 확인 필요 {len(self.ucheck)}건(정산대상 {sum(x[3] for x in self.ucheck):,.0f}원은 관리 몫에 안 넣음 · D-262 ③)")
        if self.bad:
            why.append(f"지급 줄 공식 어긋남 {self.bad}")
        if self.start_note:
            why.append(self.start_note)
        why += self.cfs_why
        if self.old_fc:
            why.append(f"확인 필요 — 정산 예정 기록 {len(self.old_fc)}줄(T-175 전 저장 · 비즈니스 인사이트·세이버·라이브·리뷰 칸 없음)의 "
                       f"기타 공제 {sum(self.old_fc):,.0f}원에 계정 정액(D-271)이 섞였을 수 있음 — 관리 몫 = 줄 비율(D-162) · 다음 정산 수집부터 나눔")
        judged = self.ctx.own_judge.get(self.aid, {})
        why += [f"확인 필요 — 처리 판정표에 없는 {k} {x:,.0f}원(D-305)" for k, x in sorted(self.watch.items()) if round(x) and k not in judged]
        return why

    def run(self) -> dict:
        self.gather()
        self._logi_comp()
        self._svc()
        self._ads()
        self._milk()
        self._rest_and_status()
        self._extra_in()
        why = self._why() + late_final_notes(self.L["gen"], self.v, self.ctx.basis)    # 정산일 지난 최종액 회차 없음(산식 23)
        g = self.__dict__
        out = {k: g[k] for k in ("acct", "aid", "t", "u", "L", "D", "Dm", "share", "fin", "gross", "refund", "st_settle", "st_ded",
                                 "line_m", "paid_total", "rows_out", "dup", "bad", "mpids", "tm", "tx", "prod", "mmon", "ushare",
                                 "u_sales", "um_sales", "um_settle", "ucheck", "settle_all", "settle_m", "pay_m", "ship", "ship_u", "ship_stats",
                                 "fav", "add", "addm", "start_note", "sv")}
        out.update({"info": self.ctx.names[self.acct], "ok": self.L["ok"] and not self.bad, "why": why, "scope": self.sc, "scope_check": self.scope_check,
                    "extras": self.ctx.extras.get(self.aid, [])})
        return out


def account(ctx, acct: str) -> dict:
    """계정 하나 → 옛 account() 와 같은 결과 사전."""
    return Account(ctx, acct).run()
