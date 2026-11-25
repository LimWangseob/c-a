"""로켓그로스 지급 줄의 물류비·재고 보상 → 줄마다 관리 상품 몫(T-130 · D-294 ① · 계정 조건 없음 D-229). 순수 함수 + 비용 리포트 읽기.

쿠팡 원문(output44 실측): 줄 물류비 공제 = 자기 정산주기 몫(공제 − 미납 칸) + 미납 상세 `cfsDeductionDetails`(갚은 정산주기·금액 · 공제 줄
1,013/1,013 합 일치). 줄의 관리 몫 = 갚은 주기마다 그 주기 비용 리포트(`파일/비용`)의 상품별 관리 비율.
쿠팡 줄 비용 칸 합 = 그 주기 리포트 합(808/808) · `cfsFeeAdjustmentDetails` 인식일(마이너스 물류비 날)은 쿠팡이 공제에서 되돌리고 대표계좌로
따로 환급(D-299 ①) → 공제에 든 비용 = 리포트 − 인식일 줄. 두 값이 안 맞거나 리포트가 없는 주기는 비율을 내지 않고 돌려줘 호출부가
'확인 필요'로 드러낸다(추정 금지).
예정 줄(그 주기 비용 리포트가 아직 없음)의 관리 비율 = min(1, r × k)(D-414 · D-415) — r = `sale_ratio`(그 주기 판매분석 로켓그로스 관리 ÷ 전체),
k = `plan_rate`(비용 리포트 있는 직전 3주기 환산 · 시작기 = 1).
"""
from __future__ import annotations

import glob
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from coupang_analytics import settlement_files as SF
from coupang_analytics import settlement_statement_pending as PEND
from coupang_analytics.settlement_consignor_month_cost import CFS_FEES as FEES
from coupang_analytics.settlement_ledger import SALE_FROM
from coupang_analytics.settlement_statement_account import month_add, num

FINAL, UNPAID, UNPAID_ONE = ("totalFinalCfsFeeDeductionAmount", "totalLastSettlementUnpaidCfsDeductionAmount",
                             "lastSettlementUnpaidCfsDeductionAmount")
ADJUST, COMP = "totalCfsFeeAdjustment", "totalCfsInventoryCompensationAmount"
TOL = 5.0                              # 시트·날마다 VAT 를 원 단위로 떨군 끝전(실측 최대 3.3원)
PLAN_WEEKS, PLAN_MAX = 3, 9.0          # 예정 줄 환산 = 비용 리포트 있는 직전 3주기(D-415) · 상한 9(D-414 ②)


def kst_day(s: str) -> str:
    """쿠팡 시각(UTC · '2026-04-18T15:00:00Z') → 한국 날짜 'YYYY-MM-DD'."""
    return (datetime.fromisoformat(str(s).replace("Z", "+00:00")) + timedelta(hours=9)).date().isoformat()


def paid_periods(r: dict) -> list | None:
    """지급 줄 → [(갚은 정산주기 끝, 금액)] · 합 = 줄 물류비 공제. 미납 칸 없음·상세 합 ≠ 미납 칸 = None(상세 없는 줄).
    공제 < 미납 상세 = 이 줄이 다음 지급으로 넘긴 이월이 물류비 칸에서 빠져 있음(실측 gbseller808 이월 243,588) — 어느 주기인지 쿠팡이 안 줌 = None."""
    if UNPAID not in r:
        return None
    unpaid, fin = num(r.get(UNPAID)), num(r.get(FINAL))
    det = [(kst_day(x["settlementPeriodEndDate"]), num(x.get(UNPAID_ONE))) for x in r.get("cfsDeductionDetails") or []]
    if round(sum(x for _e, x in det)) != round(unpaid) or round(fin - unpaid) < 0:
        return None
    return [(e, x) for e, x in [*det, (r["기간 끝"], fin - unpaid)] if round(x)]


@dataclass
class Period:
    """정산주기 하나 — 리포트 줄 [(매출인식일, 등록상품ID, VAT 포함 금액)] · 쿠팡 줄 비용 칸 합·조정 합 · 인식일 · 갚은 합."""
    lines: list | None = None
    has_row: bool = False
    fees: float = 0.0
    adjust: float = 0.0
    days: set = field(default_factory=set)
    paid: float = 0.0

    def base(self) -> list:
        """쿠팡이 공제한 비용 줄 = 리포트 − 인식일(따로 환급) 줄."""
        return [x for x in self.lines or [] if x[0] not in self.days]

    def why(self) -> str:
        """비율을 못 쓰는 까닭 · '' = 쿠팡 줄 칸과 리포트가 맞음."""
        if self.lines is None:
            return "비용 리포트 없음"
        total = sum(x[2] for x in self.base())
        if self.has_row and abs(total - self.fees - self.adjust) > TOL:
            return "비용 리포트 합 ≠ 쿠팡 줄 비용 칸"
        if self.paid - total > TOL or round(total) <= 0:
            return "갚은 금액보다 적은 비용 리포트"
        return ""

    def shares(self, managed) -> tuple[float, float]:
        """(관리 비율, 상품을 모르는 비율) — managed(등록상품ID, 매출인식 달)."""
        total, m, unk = 0.0, 0.0, 0.0
        for day, pid, x in self.base():
            total += x
            if pid.startswith("("):
                unk += x
            elif managed(pid, day[:7]):
                m += x
        return m / total, unk / total

    def refund(self, managed) -> tuple[float, float]:
        """인식일 줄 = 공제 밖 환급(관리 몫, 리포트 전체) — 받은 돈 +."""
        xs = [x for x in self.lines or [] if x[0] in self.days]
        return -sum(x for d, p, x in xs if managed(p, d[:7])), -sum(x for _d, _p, x in xs)


def _sheet_lines(name: str, rows: list) -> list:
    """요약형 시트 1장 → [(매출인식일, 등록상품ID, VAT 포함 금액)] · 상세 합 ≠ 요약 합계면 오류(집계 `_summary_lines` 와 같은 검사)."""
    hi = next((i for i, r in enumerate(rows[:15]) if r and SF._norm(r[0]) == "정산유형"), None)
    if hi is None:
        raise SF.SettlementParseError(f"비용 리포트 '{name}': 상세 머리글(정산유형) 없음")
    top, sub = [SF._norm(c) for c in rows[hi]], [SF._norm(c) for c in rows[hi + 1]]
    ai, pi, mi = SF._col(sub, SF._COST_AMOUNT, name), SF._col(top, SF._COST_PRODUCT, name), SF._col(top, ("매출인식일",), name)
    g: Counter = Counter()
    for r in rows[hi + 2:]:
        if ai < len(r) and str(r[ai] or "").strip():
            g[SF.parse_date(r[mi], name).isoformat(), SF._cost_pid(r[pi], name)] += SF.parse_int(r[ai], name)
    total, tax = SF.parse_int(rows[3][1], name), SF.parse_int(rows[3][2], name)
    if sum(g.values()) != total:
        raise SF.SettlementParseError(f"비용 리포트 '{name}': 상세 합 {sum(g.values())} ≠ 요약 합계 {total}")
    f = 1 + tax / total if total else 1.0
    return [(d, p, x * f) for (d, p), x in sorted(g.items())]


def day_lines(sheets: dict) -> list:
    """물류비 리포트 시트들 → [(매출인식일, 등록상품ID, VAT 포함 금액)](날·상품 묶음 · 시트 세액 = 금액 비율 · 수량 안내·리뷰 시트 제외)."""
    out: list = []
    for name, rows in sheets.items():
        if not any(SF._QTY_NOTICE in {SF._norm(c) for c in r} for r in rows[:20]) and SF._review_rows(name, rows) is None:
            out += _sheet_lines(name, rows)
    return out


def read_costs(base: Path, acct: str) -> tuple[dict, dict, dict]:
    """계정 비용 리포트 → ({정산주기 끝: 물류비 줄}, {정산주기 끝: 재고 보상 [(옵션ID, 달, 금액)]}, {물류비 정산주기 끝: 시작})."""
    logi: dict = {}
    comp: dict = {}
    starts: dict = {}
    for p in sorted((base / "파일" / "비용").glob(glob.escape(SF._token(acct, "계정명")) + "_*.xlsx")):     # 계정명의 '[ ]' = 글자 그대로
        m = SF.parse_file_name(p.name)
        end = m["period_end"].isoformat()
        sheets = SF.read_sheets(p)
        if m["report"].startswith("재고"):
            comp.setdefault(end, []).extend((x.option_id, x.month, float(x.ex_vat)) for x in SF.rg_cost_lines(sheets, acct, m["period_end"]))
        elif not m["report"].startswith("리뷰"):
            logi.setdefault(end, []).extend(day_lines(sheets))
            starts[end] = max(starts.get(end, ""), m["period_start"].isoformat())
    return logi, comp, starts


def periods(rows: list, logi: dict) -> dict:
    """로켓그로스 지급 줄 원본 전부 + 물류비 리포트 → {정산주기 끝: Period}."""
    out: dict = defaultdict(Period)
    for e, xs in logi.items():
        out[e].lines = xs
    for r in rows:
        p = out[r["기간 끝"]]
        if any(k in r for k in FEES):                   # 예정 기록 줄(비용 칸 저장 안 함)은 대조에 안 씀
            p.has_row = True
        p.fees += sum(num(r.get(k)) for k in FEES)
        p.adjust += num(r.get(ADJUST))
        p.days |= {str(x["recognitionDate"])[:10] for x in r.get("cfsFeeAdjustmentDetails") or [] if round(num(x.get("totalReconciledCfsAmount")))}
        for e, x in paid_periods(r) or []:
            out[e].paid += x
    return dict(out)


# ── 예정 줄(비용 리포트가 아직 없는 주기) — D-414 · D-415 ──
def _sale_share(daily: dict, managed, a: date, b: date, cut: date) -> float | None:
    """[a, b](cut 까지) 판매분석 일별 로켓그로스 관리 ÷ 전체 판매 — 그 기간 없음·빠진 날·판매 없음·0~100% 밖 = None · managed(옵션, 달)."""
    t = m = 0.0
    for x, y in PEND._month_parts(a, min(b, cut)):
        net, miss = PEND._rg_net(daily, x, y)
        if miss:
            return None
        t += sum(net.values())
        m += sum(v for o, v in net.items() if managed(o, str(x)[:7]))
    return m / t if t > 0 and 0 <= m <= t else None


def sale_ratio(daily: dict, managed, start: str, end: str, cut: date) -> float | None:
    """정산주기 → r(D-414 ①) = 그 주기 기간 비율 → 못 내면 그 달 → 앞 달 …(2026-01 까지) · cut = 기준일 전날 · 아무 달도 못 내면 None."""
    r, ym = _sale_share(daily, managed, date.fromisoformat(start), date.fromisoformat(end), cut), end[:7]
    while r is None and ym >= SALE_FROM[:7]:
        first, nxt = date.fromisoformat(ym + "-01"), date.fromisoformat(month_add(ym, 1) + "-01")
        r, ym = _sale_share(daily, managed, first, nxt - timedelta(days=1), cut), month_add(ym, -1)
    return r


def plan_rate(r: float, past: list) -> float:
    """예정 줄 관리 비율 = min(1, r × k) · past = 비용 리포트 있는 앞 주기(오래된 것부터) [(비용, 관리 비율, 상품 미표기 비율, 그 주기 r)] ·
    k(D-414 ② · D-415) = 직전 3주기 Σ관리 비용 ÷ Σ(비용 × r) · 상한 9 · 분모 0 = 1 · 상품 미표기 비용 = 그 주기 r 몫.
    시작기(③) = 앞 주기 전부에 '관리 판매 비율 > 0 이고 관리 비용 > 0' 인 주기가 없음 → k = 1."""
    last = past[-PLAN_WEEKS:]
    base = sum(t * q for t, _m, _u, q in last)
    k = 1.0
    if base and any(m > 0 and q > 0 for _t, m, _u, q in past):
        k = min(sum(t * (m + u * q) for t, m, u, q in last) / base, PLAN_MAX)
    return min(1.0, r * k)
