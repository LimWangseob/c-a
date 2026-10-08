"""정산 검증 — 우리 정산 파일·쿠팡 지급 내역을 쿠팡의 다른 장부(검증 자료)와 계정마다 자동 대조(순수 로직).

기준은 2026-10-08 nicoable 실측(화면·응답 원 단위 확인)으로 확정한 규칙:
- RG계산식: 로켓그로스 최종지급액 = 지급액(H) − 추가 상계(I) − 이번 정산 물류비(J) + 재고 손실 보상(K) + 매출 조정
  (J='이번 정산 비용'은 기납부·미납 조정을 이미 반영 — 629/629 일치)
- RG입금: 지급일별 Σ(최종지급액 − 재고 손실 보상) = 그날 월렛 입금 합(19/19) — 보상은 월렛이 아니라
  대표 정산 계좌로 정산일 별도 입금(쿠팡 도움말 7.4·2.1, 2026-10-08 확인)
- 월렛장부: 입금 합 − 인출 합 = 잔액(조회 시작 전 내역이 있으면 다를 수 있음)
- 윙판매: 우리 윙 파일 월 합(매출·판매자쿠폰·수수료·정산대상액) = 매출내역 (월=구매확정일)
- 윙지급: 정산현황 월별(지급액·정산차감·최종지급액) = 매출내역(정산대상액·정산차감·최종지급예정액), 지급 회차는 지급완료
- 윙부가세: 우리 윙 (매출 − 판매자쿠폰) 월 합 = 부가세 신고내역 월 합계
- RG부가세: 우리 로켓그로스 판매액(A×B)·판매자쿠폰 월 합 = 로켓그로스 부가세(카드+현금+기타·판매자쿠폰)
판정: 일치 · 다름 · 미정산(최근 달 — 정산 전 몫이 빠져 다를 수 있음) · 자료 없음 · 확인 필요.
"""
from __future__ import annotations

from collections import defaultdict

OK, DIFF, PENDING, NODATA, CHECK, CONFIRMED = "일치", "다름", "미정산", "자료 없음", "확인 필요", "확인됨"
HELP_RG = "쿠팡 도움말 「로켓그로스 상품의 정산은 어떻게 되나요?」"
HEAD = ["계정", "대조", "기준", "항목", "우리(계산)", "쿠팡", "차이", "판정", "비고"]
_RECENT_MONTHS = 2


def _row(acct, kind, basis, item, ours, theirs, note="", recent=False) -> dict:
    diff = (round(ours) - round(theirs)) if ours is not None and theirs is not None else None
    verdict = NODATA if diff is None else OK if diff == 0 else PENDING if recent else DIFF
    return {"계정": acct, "대조": kind, "기준": basis, "항목": item, "우리(계산)": ours, "쿠팡": theirs, "차이": diff,
            "판정": verdict, "비고": note}


def _recent(ym: str, collected: str) -> bool:
    """수집일 기준 최근 2개월(그 달 포함) — 정산이 덜 끝난 달."""
    y, m = int(collected[:4]), int(collected[5:7])
    yy, mm = int(ym[:4]), int(ym[-2:])
    return (y - yy) * 12 + (m - mm) < _RECENT_MONTHS


# ── 로켓그로스 ───────────────────────────────────────────────────
def rg_formula(acct: str, amounts: list) -> list[dict]:
    """RG계산식 — 다른 줄만 하나씩, 맞는 줄은 개수 요약 1줄."""
    out, same = [], 0
    for r in amounts:
        calc = (r.get("totalPayableAmount") or 0) - (r.get("totalAdditionalDeductionAmount") or 0) \
            - (r.get("totalFinalCfsFeeDeductionAmount") or 0) + (r.get("totalCfsInventoryCompensationAmount") or 0) \
            + (r.get("totalSalesAdjustment") or 0)
        if round(calc) == round(r["최종지급액"] or 0):
            same += 1
        else:
            out.append(_row(acct, "RG계산식", f"정산일 {r['정산일']}", f"{r['기간 시작']}~{r['기간 끝']} {r['지급비율']}%",
                            calc, r["최종지급액"], "H−I−J+K+매출조정"))
    return [_row(acct, "RG계산식", f"{same + len(out)}줄", "일치 줄 수", same, same + len(out))] + out


def _deposits(wallet: list) -> dict:
    out: dict = defaultdict(float)
    for h in wallet:
        if h.get("walletEventType") == "DEPOSIT":
            d = str(h.get("paymentDate") or "")
            out[f"{d[:4]}-{d[4:6]}-{d[6:8]}"] += h.get("amount") or 0
    return out


def rg_wallet(acct: str, amounts: list, vdata: dict | None) -> list[dict]:
    """RG입금(지급일별) + 월렛장부 + 재고 손실 보상(지급 경로 미확인)."""
    if not vdata or vdata.get("wallet") is None:
        return [_row(acct, "RG입금", "-", "월렛 내역", None, None, "검증 자료 없음")]
    collected = vdata["수집일"]
    dep, by_day = _deposits(vdata["wallet"]), defaultdict(lambda: [0.0, 0.0])
    for r in amounts:
        by_day[r["정산일"]][0] += r["최종지급액"] or 0
        by_day[r["정산일"]][1] += r.get("totalCfsInventoryCompensationAmount") or 0
    out = []
    for d in sorted(by_day):
        fin, comp = by_day[d]
        if d >= collected:
            out.append({**_row(acct, "RG입금", f"지급일 {d}", "최종−보상 ↔ 월렛 입금", fin - comp, None), "판정": PENDING})
            continue
        out.append(_row(acct, "RG입금", f"지급일 {d}", "최종−보상 ↔ 월렛 입금", fin - comp, dep.get(d, 0.0),
                        f"보상 {comp:,.0f} 제외" if comp else ""))
    total_in = sum(dep.values())
    total_out = sum(h.get("amount") or 0 for h in vdata["wallet"] if h.get("walletEventType") == "WITHDRAWAL")
    out.append(_row(acct, "월렛장부", f"~{collected}", "입금−인출 ↔ 잔액", total_in - total_out, vdata.get("wallet_balance"),
                    "다르면 조회 시작(2025-01) 전 내역 영향 가능"))
    comp_all = sum(r.get("totalCfsInventoryCompensationAmount") or 0 for r in amounts)
    if comp_all:
        out.append({**_row(acct, "재고손실보상", "전체", "정산현황 보상 합", comp_all, None,
                           f"대표 정산 계좌로 정산일 별도 입금(월렛 아님) — {HELP_RG} 7.4"), "판정": CONFIRMED})
    return out


# ── 윙 ──────────────────────────────────────────────────────────
def _purchase(vdata: dict) -> dict:
    """매출내역 → {YYYYMM: {매출·쿠폰·수수료·정산대상·차감·최종}} (조회 실패한 달 = None)."""
    out: dict = {}
    for ym, resp in (vdata.get("purchase") or {}).items():
        if resp is None:
            out[ym] = None
            continue
        c: dict = defaultdict(float)
        for r in resp.get("purchaseReports") or []:
            for k, f in (("매출", "revenueAmount"), ("쿠폰", "sellerDiscountCoupon"), ("수수료", "feeAmount"),
                         ("정산대상", "apAmount"), ("차감", "deductionAmount"), ("최종", "finalPaidAmount")):
                c[k] += r.get(f) or 0
        out[ym] = c
    return out


def wing_sales(acct: str, ours: dict, vdata: dict | None) -> list[dict]:
    """ours = {YYYYMM: {매출·쿠폰·수수료·정산대상}} (우리 윙 파일, 월=구매확정일)."""
    if not vdata:
        return [_row(acct, "윙판매", "-", "매출내역", None, None, "검증 자료 없음")]
    pr, out = _purchase(vdata), []
    for ym in sorted(set(pr) | set(ours)):
        o, t = ours.get(ym, {}), pr.get(ym)
        if t is None:
            out.append(_row(acct, "윙판매", ym, "매출내역", None, None, "그 달 조회 실패"))
            continue
        if not any(o.values()) and not any(t.values()):
            continue
        for k in ("매출", "쿠폰", "수수료", "정산대상"):
            out.append(_row(acct, "윙판매", ym, k, o.get(k, 0), t[k], recent=_recent(ym, vdata["수집일"])))
    return out


def wing_pay(acct: str, amounts: list, vdata: dict | None) -> list[dict]:
    """정산현황(윙) 월별 지급·차감·최종 ↔ 매출내역 + 지급일 지난 회차의 지급완료 여부."""
    if not vdata:
        return []
    pr = _purchase(vdata)
    by: dict = defaultdict(lambda: defaultdict(float))
    out = []
    for r in amounts:
        ym = r["기간 시작"][:7].replace("-", "")
        by[ym]["정산대상"] += r.get("paidAmount") or 0
        by[ym]["차감"] += r.get("totalDeductionAmount") or 0
        by[ym]["최종"] += r["최종지급액"] or 0
        if r["정산일"] < vdata["수집일"] and r.get("지급상태") not in (None, "DONE"):
            out.append({**_row(acct, "윙지급", f"정산일 {r['정산일']}", "지급상태", None, None, str(r.get("지급상태"))),
                        "판정": CHECK})
    for ym in sorted(set(by) | set(pr)):
        if pr.get(ym) is None:
            continue
        for k in ("정산대상", "차감", "최종"):
            if by[ym][k] or pr[ym][k]:
                out.append(_row(acct, "윙지급", ym, k, by[ym][k], pr[ym][k], recent=_recent(ym, vdata["수집일"])))
    return out


# ── 부가세 ────────────────────────────────────────────────────────
def vat(acct: str, wing_ours: dict, rg_ours: dict, vdata: dict | None) -> list[dict]:
    """wing_ours={YYYYMM:{매출,쿠폰}} · rg_ours={YYYYMM:{판매액,쿠폰}} (우리 파일)."""
    if not vdata:
        return []
    out, collected = [], vdata["수집일"]
    for r in ((vdata.get("wing_vat") or {}).get("paymentMethodReports") or []):
        ym, o = r["yearMonth"], wing_ours.get(r["yearMonth"], {})
        mine = o.get("매출", 0) - o.get("쿠폰", 0)
        if mine or r.get("total"):
            out.append(_row(acct, "윙부가세", ym, "매출−판매자쿠폰", mine, r.get("total") or 0, recent=_recent(ym, collected)))
    for r in ((vdata.get("rg_vat") or {}).get("vatResponseAggregatedDtos") or []):
        ym = r["yearMonth"].replace("-", "")
        o = rg_ours.get(ym, {})
        paid = (r.get("creditCardPaymentAmountAgg") or 0) + (r.get("cashPaymentAmountAgg") or 0) \
            + (r.get("otherPaymentAmountAgg") or 0)
        if o.get("판매액") or paid:
            out.append(_row(acct, "RG부가세", ym, "판매액", o.get("판매액", 0), paid, recent=_recent(ym, collected)))
            out.append(_row(acct, "RG부가세", ym, "판매자쿠폰", o.get("쿠폰", 0), r.get("sellerFundedCouponAggAmount") or 0,
                            recent=_recent(ym, collected)))
    return out


def holds(acct: str, vdata: dict | None) -> list[dict]:
    """보류목록·추가지급 — 있으면 '확인 필요'(정산 금액을 바꾸는 항목)."""
    if not vdata:
        return []
    n_pend = sum((v or {}).get("totalRecordCount") or 0 for v in (vdata.get("pending") or {}).values())
    n_add = sum(len((v or {}).get("reports") or []) for v in (vdata.get("additional") or {}).values())
    return [{**_row(acct, k, vdata["기간"][0] + "~", "건수", n, 0), "판정": OK if n == 0 else CHECK}
            for k, n in (("보류", n_pend), ("추가지급", n_add))]


def _date_group(acct: str, label: str, rows: list, calc) -> list[dict]:
    """한 묶음의 지급일 대조 — calc(r)=계산/캘린더 날짜('YYYY-MM-DD') 또는 None(기준 없음). 요약 1줄 + 다른 줄."""
    same, bad, none = 0, [], []
    for r in rows:
        want = calc(r)
        if want is None:
            none.append(_row(acct, "지급일", f"정산일 {r['정산일']}", f"{label} {r['기간 시작']}~{r['기간 끝']}", None, None,
                             "캘린더에 없음"))
        elif want == r["정산일"]:
            same += 1
        else:
            bad.append(_row(acct, "지급일", f"정산일 {r['정산일']}", f"{label} {r['기간 시작']}~{r['기간 끝']} {r['지급비율']}%",
                            0, 1, f"{'캘린더' if '캘린더' in label else '계산'} {want}"))
    if not rows:
        return []
    return [_row(acct, "지급일", "요약", label, same, len(rows) - len(none), "일치 줄 수 / 전체")] + bad + none


def _calendar_lookup(calendar: list):
    """윙 정산현황 줄 → 그 기간을 포함하는 캘린더 회차의 지급일(70%=W 주정산·30%=R 최종액)."""
    def find(r):
        code = {70: "W", 30: "R"}[int(float(r["지급비율"]))]
        hits = [c for c in calendar if c.get("transactionCycleCode") == code and c.get("recognitionFrom")
                and c["recognitionFrom"] <= r["기간 시작"] and r["기간 끝"] <= c["recognitionTo"]]
        return hits[0]["start"][:10] if len(hits) == 1 else None
    return find


def paydates(acct: str, amounts_wing: list, amounts_rg: list, holidays, calendar: list | None = None) -> list[dict]:
    """지급일 대조. 윙=쿠팡 정산캘린더 날짜(30% 최종액 포함·공휴일 불필요 — 소유자 지시 2026-10-08, nicoable 18/18),
    캘린더 없으면 규칙(70%만·주 마감+15영업일). 로켓그로스=payout.rg_payout_date(공휴일 필요·629/629).
    윙 100%(보류 해제 지급)는 대상 아님. 공휴일이 필요한데 없으면 '자료 없음' 1줄."""
    from datetime import date as _d

    from . import payout as P
    wing = [r for r in amounts_wing if int(float(r["지급비율"])) in (70, 30)]
    out: list = []
    if calendar is not None:
        out += _date_group(acct, "윙(캘린더)", wing, _calendar_lookup(calendar))
        wing = []
    need_hol = bool(amounts_rg) or any(int(float(r["지급비율"])) == 70 for r in wing)
    if need_hol and holidays is None:
        return out + [_row(acct, "지급일", "-", "공휴일", None, None, "공휴일 자료 없음 — 앱 설정 탭에서 공휴일 API 키 등록")]
    out += _date_group(acct, "로켓그로스", amounts_rg, lambda r: P.rg_payout_date(
        int(float(r["지급비율"])), _d.fromisoformat(r["기간 시작"]), _d.fromisoformat(r["기간 끝"]), holidays).isoformat())
    out += _date_group(acct, "윙 70%", [r for r in wing if int(float(r["지급비율"])) == 70], lambda r: P.payout_date(
        P.PAYOUT_MP_WEEKLY_1ST, week_end=_d.fromisoformat(r["기간 끝"]), holidays=holidays).isoformat())
    return out


def failures(acct: str, vdata: dict | None) -> list[dict]:
    return [{**_row(acct, "조회실패", vdata["수집일"], f, None, None), "판정": NODATA}
            for f in ((vdata or {}).get("조회 실패") or [])]


def build(acct: str, wing_ours: dict, rg_ours: dict, amounts_wing: list, amounts_rg: list,
          vdata: dict | None, holidays=None) -> list[dict]:
    """계정 하나의 검증 줄 전부."""
    return (rg_formula(acct, amounts_rg) + rg_wallet(acct, amounts_rg, vdata) + wing_sales(acct, wing_ours, vdata)
            + wing_pay(acct, amounts_wing, vdata) + vat(acct, wing_ours, rg_ours, vdata) + holds(acct, vdata)
            + paydates(acct, amounts_wing, amounts_rg, holidays, (vdata or {}).get("calendar"))
            + failures(acct, vdata))


def month_sums(files: list, order_rows) -> tuple[dict, dict]:
    """우리 파일 → (윙 {계정:{YYYYMM:{매출,쿠폰,수수료,정산대상}}}, RG {계정:{YYYYMM:{판매액,쿠폰}}}).
    윙은 집계와 같은 줄 선택 규칙(order_rows=settlement_stats._order_rows·최종액 파일은 주정산 없는 주만)."""
    wing: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    rg: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for f, r in order_rows([f for f in files if f.channel == "윙"], []):
        m = wing[r.account][f"{(r.recognized or f.period_end):%Y%m}"]
        m["매출"] += r.sales
        m["쿠폰"] += r.coupon
        m["수수료"] += r.fee
        m["정산대상"] += r.settle
    for f in files:
        if f.channel == "윙":
            continue
        for r in f.rows:
            m = rg[r.account][f"{(r.recognized or f.period_end):%Y%m}"]
            m["판매액"] += r.gross
            m["쿠폰"] += r.coupon
    return wing, rg


def build_all(files: list, amounts: list, vdatas: dict, order_rows, holidays=None) -> list[dict]:
    """모든 계정의 검증 줄. amounts=[{계정,채널,…}] · vdatas={계정: 검증 자료}(계정명=파일 이름 글자 규칙)."""
    wing, rg = month_sums(files, order_rows)
    accts = sorted(set(wing) | set(rg) | {a["계정"] for a in amounts} | set(vdatas))
    out: list = []
    for a in accts:
        aw = [r for r in amounts if r["계정"] == a and r["채널"] == "윙"]
        ar = [r for r in amounts if r["계정"] == a and r["채널"] == "로켓그로스"]
        out += build(a, wing.get(a, {}), rg.get(a, {}), aw, ar, vdatas.get(a), holidays)
    return out


# ── 계좌 입금(지급월별) ───────────────────────────────────────────
INFLOW_HEAD = ["계정", "지급월", "윙 지급", "RG 월렛 입금", "RG 월렛 인출", "재고 손실 보상", "물류비 환급", "쿠팡 지급 합계",
               "대표계좌 입금 합계", "비고"]


def _refund_day(period_start: str) -> str:
    """마이너스 물류비 환급일 = 매출인식 달의 익월 21일(주말·공휴일이면 다음 영업일 — 날짜는 표시용 근사)."""
    y, m = int(period_start[:4]), int(period_start[5:7])
    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return f"{y}-{m:02d}-21"


def _inflow_amounts(m: dict, notes: dict, amounts_wing: list, amounts_rg: list, t: str) -> None:
    for r in amounts_wing:
        if r["정산일"] <= t and r.get("지급상태") in (None, "DONE"):
            m[r["정산일"][:7]]["윙 지급"] += r["최종지급액"] or 0
    for r in amounts_rg:
        comp = r.get("totalCfsInventoryCompensationAmount") or 0
        if comp and r["정산일"] <= t:
            m[r["정산일"][:7]]["재고 손실 보상"] += comp
        adj = r.get("totalCfsFeeAdjustment") or 0
        day = _refund_day(r["기간 시작"])
        if adj and day <= t:
            m[day[:7]]["물류비 환급"] += adj
            notes[day[:7]].append(f"물류비 환급 {day[5:]}경")


def _inflow_wallet(m: dict, wallet: list) -> None:
    for h in wallet:
        d = str(h.get("paymentDate") or "")
        kind = {"DEPOSIT": "RG 월렛 입금", "WITHDRAWAL": "RG 월렛 인출"}.get(h.get("walletEventType"))
        if kind:
            m[f"{d[:4]}-{d[4:6]}"][kind] += h.get("amount") or 0


def _inflow_row(acct: str, ym: str, c: dict, notes: list, has_wallet: bool) -> dict:
    row = {"계정": acct, "지급월": ym, **{k: c.get(k, 0) for k in INFLOW_HEAD[2:7]}}
    base = c.get("윙 지급", 0) + c.get("재고 손실 보상", 0) + c.get("물류비 환급", 0)
    row["쿠팡 지급 합계"] = base + c.get("RG 월렛 입금", 0)
    row["대표계좌 입금 합계"] = base + c.get("RG 월렛 인출", 0)
    note = sorted(set(notes))
    if not has_wallet:
        row["RG 월렛 입금"] = row["RG 월렛 인출"] = None
        note.append("월렛 자료 없음(검증 자료 수집 전) — 합계에 RG 월렛 미포함")
    row["비고"] = " · ".join(note)
    return row


def inflows(acct: str, amounts_wing: list, amounts_rg: list, vdata: dict | None, *, today) -> list[dict]:
    """쿠팡이 실제로 내보낸 돈을 지급월별로(쿠팡 도움말 로켓그로스 정산 2.1·2.5·7.4):
    윙 지급(대표계좌 직접·지급일 지난 회차) · RG 월렛 입금/인출(인출=대표계좌로 이체) · 재고 손실 보상(대표계좌·정산일) ·
    마이너스 물류비 환급(totalCfsFeeAdjustment·대표계좌·익월 21일). 쿠팡 지급 합계=윙+월렛 입금+보상+환급,
    대표계좌 입금 합계=윙+월렛 인출+보상+환급(월렛 잔액은 아직 대표계좌에 없음). 지급일이 오늘 이후면 제외."""
    m: dict = defaultdict(lambda: defaultdict(float))
    notes: dict = defaultdict(list)
    _inflow_amounts(m, notes, amounts_wing, amounts_rg, today.isoformat())
    wallet = (vdata or {}).get("wallet")
    _inflow_wallet(m, wallet or [])
    return [_inflow_row(acct, ym, m[ym], notes[ym], wallet is not None) for ym in sorted(m)]


def inflows_all(amounts: list, vdatas: dict, *, today) -> list[dict]:
    accts = sorted({a["계정"] for a in amounts} | set(vdatas))
    out: list = []
    for a in accts:
        out += inflows(a, [r for r in amounts if r["계정"] == a and r["채널"] == "윙"],
                       [r for r in amounts if r["계정"] == a and r["채널"] == "로켓그로스"], vdatas.get(a), today=today)
    return out
