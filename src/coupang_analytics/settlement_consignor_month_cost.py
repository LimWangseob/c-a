"""위탁자 정산서 3차 형식 — 6 창고·배송비 · 7 밀크런 · 8 재고 보상 · 6·7·8 상품 자료 전 금액 나누기 · 9 계정 공통 · 비중 · 10 별도 입금.
T-38 S2(샘플 `s03_compute.py` logistics·milkrun·compensation·alloc_pending_costs·other_common·shares·separate 를 나눔).

샘플 뒤 확정 규칙(그대로 따름): D-299 ① CFS 비용 조정 = 물류비 리포트 안에 이미 있음(9 에 더하지 않음) · D-299 ④ 판매자서비스이용료 =
쿠팡 지급 줄 값만(규칙 예상값 안 넣음) · D-312 ② 성장 대출·MCA·체크카드 = 위탁자 본인 차감(관리 몫 0 · 9 에 안 넣음) ·
D-304·D-319 지급 끝난 윙 음수 회차 3PM 되돌림 = 기존 계산의 공제 항목 그대로 · D-271 계정 정액 3종 = 등록 비중.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from coupang_analytics import settlement_files as SF
from coupang_analytics import settlement_managed_alloc as MA
from coupang_analytics import settlement_statement_account as AC
from coupang_analytics.settlement_consignor_month_calc import MonthState, jl, kst_month, pct
from coupang_analytics.settlement_statement_account import num

CFS_FEES = ("totalStorageFeeDeductionAmount", "totalFulfillmentFeeDeductionAmount", "totalWarehousingFeeDeductionAmount",
            "totalBarcodeLabelingFeeDeductionAmount", "totalContainerUnloadingFeeDeductionAmount",
            "totalCreturnGradingFeeDeductionAmount", "totalCreturnReverseShippingFeeDeductionAmount",
            "totalVreturnHandlingFeeDeductionAmount", "totalVreturnShippingFeeDeductionAmount")
KINDS = (("입출고비", "입출고비 (창고에 넣고 꺼냄)"), ("배송비", "고객 배송비"), ("보관비", "보관비 (오래 둘수록 비쌈)"),
         ("바코드 부가 서비스", "바코드 붙이기"), ("반품회수비", "반품 회수비"), ("반품재입고비", "반품 재입고비"),
         ("반출비", "창고에서 빼내는 비용 (반출)"), ("반출 배송 서비스비 리포트", "반출 배송비"))
PEND_KIND = "종류별 내역 전 (정산 예정·쿠팡 미확정)"
OTHER_BR = {"subscriptionFeeOffsetYearMonthBreakdown": "로켓그로스 세이버 구독료",
            "businessInsightsOffsetYearMonthBreakdown": "비즈니스 인사이트 이용료",
            "coupangLiveOffsetYearMonthBreakdown": "쿠팡 라이브 수수료"}
OWN_BR = {"debitCardOffsetYearMonthBreakdown": AC.OWN_CARD}          # D-312 ② 체크카드 = 위탁자 본인 차감
RG_NOTE_KEYS = ("totalPostPurchaseDeductionAmount", "totalCoupangLiveDeductionAmount", "totalDebitCardDeductionAmount",
                "totalSubscriptionFeeDeductionAmount", "totalBusinessInsightsDeductionAmount", "totalCarryOverSettlementDeductionAmount")
# 계정 단위 정액 3종(D-271) — 9 반영 비중 = 등록 비중(판매 비중과 비교 안 함)
FIXED_FEE_CATS = ("w:" + AC.SVC, "o:subscriptionFeeOffsetYearMonthBreakdown", "o:businessInsightsOffsetYearMonthBreakdown")
PM3_BACK = f"윙 지급 차감 — {AC.PM3} (지급 끝난 음수 회차 되돌림 · D-304)"


# ── 6 창고·배송비 ──
def _cfs_report(st: MonthState) -> float:
    st.kinds = Counter()
    tot_all = 0
    for p in st.d["rg_cost_rows"]:
        if str(p["월(매출인식)"])[:7] != st.m:
            continue
        pid = str(p["등록상품ID"])
        amt = p["물류비 합계(VAT포함)"] or 0
        tot_all += amt
        if pid.startswith("("):
            if amt:
                st.common.append((f"창고·배송비 중 쿠팡이 상품을 표시하지 않은 금액 ({pid})", amt, "cfs"))
            continue
        if st.managed(pid):
            st.cols[pid][6] -= amt
            ks = 0
            for k, _nm in KINDS:
                st.kinds[k] += p[k] or 0
                ks += p[k] or 0
            if ks != amt:
                st.j.append(f"확인 필요: {pid} 물류비 종류 합 {ks} ≠ 합계 {amt}")
    return tot_all


def _cfs_pending_line(st: MonthState, key, row, r, fees: float, acc: dict) -> None:
    """상품별 리포트 전 판매 기간: 종류별 칸 0 · 지난 기간 칸 0 · 쿠팡이 계산한 공제(totalFinalCfsFeeDeductionAmount)만 있음."""
    fin = num(r.get("totalFinalCfsFeeDeductionAmount")) - num(r.get("totalLastSettlementUnpaidCfsDeductionAmount"))
    if round(fees) or round(num(r.get("totalPastCfsDeductionAmount"))) or not round(fin):
        return
    acc["pend"] += fin
    acc["lines"].append(f"{row[2]} 지급({row[3]}~{row[4]} · {row[5]}%) {fin:,.0f}")
    st.loc["cfs"].append((key, fin))
    # 이월 공제 = 공제가 그 줄 지급액보다 커서 다음 지급으로 넘긴 금액(KB 122 · 그 줄 최종지급액 0) → 이 판매 기간 창고 비용의 남은 몫(샘플 판단)
    carry = num(r.get("totalCarryOverSettlementDeductionAmount"))
    if round(carry):
        acc["pend"] += carry
        acc["lines"].append(f"{row[2]} 지급 줄 이월 공제 {carry:,.0f}(다음 지급으로 넘김 · 확인 필요)")
        st.j.append(f"확인 필요: {row[2]} 지급({row[3]}~{row[4]}) 줄 이월 공제 {carry:,.0f}원 = 그 줄 공제(창고비·밀크런)가 지급액보다 커서 "
                    "쿠팡이 다음 지급으로 넘긴 금액 → 6 창고·배송비 확정 전에 넣고 지급일 미정으로 둠(Claude 판단)")


def _cfs_details(st: MonthState, key, r, acc: dict) -> None:
    for x in jl(r.get("cfsDeductionDetails")) or []:
        if kst_month(x["settlementPeriodStartDate"]) == st.m and num(x.get("lastSettlementUnpaidCfsDeductionAmount")):
            st.loc["cfs"].append((key, num(x["lastSettlementUnpaidCfsDeductionAmount"])))
    for x in jl(r.get("cfsFeeAdjustmentDetails")) or []:
        if str(x.get("recognitionDate") or "")[:7] == st.m and num(x.get("totalReconciledCfsAmount")):
            acc["adj"] += num(x["totalReconciledCfsAmount"])
            st.loc["cfs"].append((key, num(x["totalReconciledCfsAmount"])))


def logistics(st: MonthState) -> None:
    tot_all = _cfs_report(st)
    acc = {"own": 0.0, "adj": 0.0, "pend": 0.0, "lines": []}
    for key, row, r in st.lines():
        if r["채널"] != "로켓그로스":
            continue
        fees = sum(num(r.get(k)) for k in CFS_FEES)
        if str(row[3])[:7] == st.m:
            acc["own"] += fees
            now = fees + num(r.get("totalPastCfsDeductionAmount"))     # 이 줄 자기 기간 비용 중 지금 뺀 몫(나머지는 뒤 줄로 미룸)
            if round(now):
                st.loc["cfs"].append((key, now))
        if st.pend_line(row, r):
            _cfs_pending_line(st, key, row, r, fees, acc)
        _cfs_details(st, key, r, acc)
    own, adj, pend = acc["own"], acc["adj"], acc["pend"]
    st.chk.append({"검사": "상품별 물류비 리포트(이 달) 합 = 이 달 판매 기간 지급 줄의 창고·배송비 칸 합", "값": [tot_all, own], "차이": tot_all - own})
    if round(adj):        # D-299 ① CFS 비용 조정 = 물류비 리포트 순액 안에 이미 있음 → 9 에 더하지 않음(위치만 날짜별 표에)
        st.j.append(f"창고·배송비 정산 조정(cfsFeeAdjustmentDetails) {adj:,.0f}원 = 상품별 물류비 리포트 순액에 이미 들어 있어 9 계정 공통에 "
                    "더하지 않음(D-299 ① 이중 반영 금지) · 쿠팡이 뺀 지급 줄 위치만 날짜별 표에 씀")
    if round(pend):
        st.pend_cost["cfs"] = pend
        st.pend_info.append({"항목": "6 창고·배송비 — 상품별 물류비 리포트 전", "추정": False,
                             "방법": "쿠팡 정산 줄의 창고비 공제(totalFinalCfsFeeDeductionAmount · 쿠팡 계산) → 이 달 로켓그로스 상품 판매(확정+예정) 비율로 나눔",
                             "원천": " · ".join(acc["lines"]), "계정 전체": round(pend)})
    st.cfs = {"product_report": tot_all, "line_fees": own, "adjust": adj, "pending": pend}


# ── 7 밀크런 ──
def _milk_by_date(st: MonthState) -> dict:
    by_date = defaultdict(list)
    for key, row, r in st.lines():
        if num(r.get("totalMilkRunDeductionAmount")) and str(row[2]) > f"{st.m}-31":
            by_date[str(row[2])].append((key, num(r["totalMilkRunDeductionAmount"])))
    return by_date


def _milk_nofile(st: MonthState, by_date: dict) -> None:
    """밀크런 파일 없음 → 달 끝 뒤 첫 밀크런 공제 지급일 금액(쿠팡 정산 줄 · 9월 실측: 파일 합 = 달 끝 뒤 첫 공제일 합)."""
    dt = min(by_date, default="")
    total = sum(a for _, a in by_date[dt]) if dt else 0.0
    if dt:
        st.loc["milk"] += by_date[dt]
        st.pend_cost["milk"] = total
        st.pend_info.append({"항목": "7 밀크런 — 이 달 밀크런 파일 없음", "추정": True,
                             "방법": "달 끝 뒤 첫 밀크런 공제 지급일의 공제 합(쿠팡 정산 줄) → 이 달 로켓그로스 상품 판매(확정+예정) 비율로 나눔 · 확인 필요(파일 없음)",
                             "원천": f"{dt} 지급 줄 밀크런 공제 {total:,.0f}", "계정 전체": round(total)})
        st.j.append(f"확인 필요: {st.m} 밀크런 파일 없음 → {dt} 지급 줄 밀크런 공제 {total:,.0f}원을 이 달 밀크런으로 보고 판매 비율로 나눔(파일 나오면 입고 수량 비율로 다시 계산)")
    st.chk.append({"검사": "밀크런 파일 없음 → 달 끝 뒤 첫 밀크런 공제 지급일 금액 사용", "값": [total, total], "차이": 0,
                   "공제 지급일": dt or "없음", "파일": "없음"})
    st.milk = {"file_total": 0.0, "deducted": total, "pending": total}


def _milk_qty(st: MonthState) -> dict:
    qty: dict = defaultdict(lambda: defaultdict(float))
    for s in st.d["v"].get("inbound") or []:
        if s.get("cancelled") or not s.get("milkrunSeq"):
            continue
        for k in s.get("skus") or []:
            qty[str(s["milkrunSeq"])][str(k.get("vendorItemId"))] += k.get("stowedQty") or k.get("requestedQty") or 0
    return qty


def _milk_alloc(st: MonthState, rows: list) -> tuple[float, list]:
    qty = _milk_qty(st)
    total = 0.0
    miss: list = []
    for seq, amt in rows:
        total += amt
        q = qty.get(seq)
        t = sum(q.values()) if q else 0
        if not t:
            miss.append((seq, amt))
            continue
        for vid, n in q.items():
            pid, m = st.managed_vid(vid)
            if m and pid:
                st.cols[pid][7] -= amt * n / t
            elif m:
                miss.append((f"{seq}:{vid}", amt * n / t))
    return total, miss


def milkrun(st: MonthState) -> None:
    p = st.base / "검증자료" / "광고" / f"{SF._token(st.acct, '계정명')}_밀크런_{st.mk}.xlsx"
    by_date = _milk_by_date(st)
    if not p.exists():
        _milk_nofile(st, by_date)
        return
    rows = [(str(r.get("밀크런번호")), AC._txt_num(r.get("총 합계금액")) + AC._txt_num(r.get("취소수수료")))
            for r in AC.xlsx_rows(p) if r.get("밀크런번호")]
    total, miss = _milk_alloc(st, rows)
    if miss and round(sum(x[1] for x in miss)):
        st.common.append((f"밀크런 중 쿠팡 입고 내역이 없는 금액 (밀크런 {', '.join(str(x[0]) for x in miss)})", sum(x[1] for x in miss), "milk"))
    # 밀크런 공제 위치: 쿠팡 달 표시는 '공제한 지급 줄의 판매 기간 달'이라 밀크런 달과 다름 → 이 달 파일 합과 원 단위로 같은 한 지급일을 찾음
    ded, hit = 0.0, ""
    for dt in sorted(by_date):
        if round(sum(a for _, a in by_date[dt])) == round(total):
            ded, hit = total, dt
            st.loc["milk"] += by_date[dt]
            break
    st.chk.append({"검사": "밀크런 파일(이 달 픽업) 합 = 쿠팡이 한 지급일에 뺀 밀크런 합(원 단위로 같은 날을 찾음)",
                   "값": [total, ded], "차이": total - ded, "공제 지급일": hit or "못 찾음", "파일": str(p)})
    if total and not hit:
        st.j.append(f"확인 필요: 이 달 밀크런 {total:,.0f}원을 뺀 쿠팡 지급일을 원 단위로 못 찾음 — 날짜별 표에서 '아직 안 뺀 금액'으로 둠")
    st.milk = {"file_total": total, "deducted": ded, "pending": 0.0}


# ── 8 재고 분실·파손 보상 ──
def _comp_report(st: MonthState) -> tuple[list, float]:
    tok = SF._token(st.acct, "계정명")
    files = []
    for p in sorted((st.base / "파일" / "비용").glob(f"{tok}_*_재고-손실-보상_*.xlsx")):
        meta = SF.parse_file_name(p.name)
        if f"{meta['period_end']:%Y-%m}" == st.m:
            files.append((p, meta))
    total = 0
    unk = 0
    for p, meta in files:
        for cl in SF.rg_cost_lines(SF.read_sheets(p), st.acct, meta["period_end"]):
            if cl.kind != SF.COMPENSATION:
                continue
            total += cl.ex_vat
            pid, m = st.managed_vid(cl.option_id, "pid")
            if m and pid:
                st.cols[pid][8] += cl.ex_vat
            elif m or not pid:
                unk += cl.ex_vat
    if unk:
        st.common.append(("재고 보상 중 쿠팡이 상품을 표시하지 않은 금액", -unk, "comp"))
    return files, total


def compensation(st: MonthState) -> None:
    files, total = _comp_report(st)
    paid = 0.0
    src = []
    for key, row, r in st.lines():
        c = num(r.get("totalCfsInventoryCompensationAmount"))
        if c and str(row[4])[:7] == st.m:
            paid += c
            src.append(f"{row[2]} 지급({row[3]}~{row[4]}) {c:,.0f}")
            st.loc["comp"].append((key, -c))
    pend = 0.0
    if not files and round(paid):
        # 이 달 정산 주기 재고 손실 보상 리포트 없음 → 판매 기간 끝이 이 달인 지급 줄의 보상 칸(쿠팡 계산 · 확정 전)
        pend = paid
        st.pend_cost["comp"] = -paid
        st.pend_info.append({"항목": "8 재고 보상 — 이 달 재고 손실 보상 리포트 없음", "추정": False,
                             "방법": "판매 기간 끝이 이 달인 지급 줄의 보상 칸(totalCfsInventoryCompensationAmount) → 이 달 로켓그로스 상품 판매(확정+예정) 비율로 나눔",
                             "원천": " · ".join(src), "계정 전체": round(paid)})
    st.chk.append({"검사": "재고 손실 보상 리포트(이 달 정산 주기 파일) 합 + 리포트 전 금액 = 이 달 지급 줄 보상 칸", "값": [total, pend, paid],
                   "차이": total + pend - paid, "파일": [str(p) for p, _ in files]})
    st.comp = {"report": total, "paid": paid, "pending": pend}


# ── 6·7·8 상품 자료 전 금액 나누기 ──
def alloc_pending_costs(st: MonthState) -> None:
    tot = sum(st.rgsales.values())
    for col, cat in ((6, "cfs"), (7, "milk"), (8, "comp")):
        a = st.pend_cost.get(cat, 0.0)
        if not round(a):
            continue
        if not tot:
            st.j.append(f"확인 필요: {st.m} {cat} 상품 자료 전 금액 {a:,.0f} — 이 달 로켓그로스 판매가 없어 나누지 못함(계정 공통으로)")
            st.common.append((f"{cat} 상품 자료 전 금액(나눌 판매 없음)", a, cat))
            continue
        man = 0.0
        for key, s in st.rgsales.items():
            if st.is_m(key):
                v = -a * s / tot
                st.cols[key][col] += v
                st.pend[key][col] += v
                man += v
        st.pend_cost_m[cat] = man
        if cat == "cfs":
            st.kinds[PEND_KIND] += -man


# ── 9 그 밖의 계정 공통 ──
def _breakdowns(st: MonthState, key, r) -> None:
    for k, nm in OTHER_BR.items():
        br = jl(r.get(k))
        if isinstance(br, dict) and br.get(st.m):
            st.common.append((nm, num(br[st.m]), "o:" + k))
            st.loc["o:" + k].append((key, num(br[st.m])))
    for k, nm in OWN_BR.items():
        br = jl(r.get(k))
        if isinstance(br, dict) and br.get(st.m):
            st.own[nm] += num(br[st.m])


def _wing_deductions(st: MonthState, key, r, parts: Counter) -> None:
    """윙 차감 사유(이 달 판매 기간 줄) — 광고(5)·빠른정산(이미 받은 돈 D-312 ①)·성장 대출(위탁자 본인 차감 D-312 ②) 밖 = 9 계정 공통 ·
    지급 끝난 음수 회차 되돌림(D-304·D-319) = 기존 계산 공제 항목의 3PM_매출채권 − 원문 3PM 차감."""
    raw_pm3 = 0.0
    for x in r.get("차감 사유") or []:
        why = x.get("사유") or "기타 공제"
        item = AC.WING_KEY.get(why, why)
        if why == AC.PM3:
            raw_pm3 += num(x.get("금액"))
        if "광고" in why or "빠른정산" in why or item == AC.FAST:
            continue
        if item.startswith(AC.OWN):
            st.own[item] += num(x.get("금액"))
            continue
        st.common.append((f"윙 지급 차감 — {why}", num(x.get("금액")), "w:" + why))
        st.loc["w:" + why].append((key, num(x.get("금액"))))
    back = parts.get(AC.PM3, 0.0) - raw_pm3
    if round(back):
        st.common.append((PM3_BACK, back, "w:" + AC.PM3))
        st.loc["w:" + AC.PM3].append((key, back))


def _rg_notes(st: MonthState, key, row, r) -> None:
    st.own[AC.OWN_MCA] += num(r.get("totalMerchantCashAdvanceDeductionAmount"))     # D-312 ② MCA 상환 = 위탁자 본인 차감
    for k in RG_NOTE_KEYS:
        if k == "totalCarryOverSettlementDeductionAmount" and st.pend_line(row, r):
            continue                                  # 정산 예정 줄 이월 공제 = 6 확정 전에서 처리(logistics)
        if num(r.get(k)):
            st.j.append(f"이 달 판매 기간 지급 줄 {key} {k} = {num(r.get(k)):,.0f} (달 표시 칸으로 따로 처리됨 여부 확인)")


def other_common(st: MonthState) -> None:
    watch: Counter = Counter()
    for key, row, r, parts in st.line_parts():
        _breakdowns(st, key, r)
        in_m = str(row[3])[:7] == st.m
        if r["채널"] == "윙" and in_m:
            _wing_deductions(st, key, r, parts)
        if in_m and r["채널"] == "로켓그로스":
            _rg_notes(st, key, row, r)
        if in_m:
            watch.update(AC.watched(r))
    judged = st.d["own_judge"]
    st.j += [f"확인 필요 — 처리 판정표에 없는 {k} {x:,.0f}원(이 달 판매 기간 지급 줄 · D-305)" for k, x in sorted(watch.items())
             if round(x) and k not in judged]
    _svc_reference(st)


def _svc_reference(st: MonthState) -> None:
    """판매자서비스이용료 = 쿠팡 지급 줄 값만(D-299 ④) — D-161 규칙 값은 참고로만 남김(정산 금액에 안 넣음)."""
    w = st.d["wconf"].get(st.m, (0.0, 0.0, 0.0))
    conf = {st.m: (w[0], w[1], w[2] + max(st.d["pur"].get(st.m, 0.0) - sum(w), 0.0))}
    ch = MA.svc_charges(conf, AC.month_add(st.basis[:7], -1))
    line = sum(a for n, a, c in st.common if c == "w:" + AC.SVC)
    st.svc = {"구매확정 판매(일반·가전·모름)": conf[st.m], "규칙 참고값(D-161 · 정산 금액에 안 넣음)": ch.get(st.m, 0),
              "쿠팡 지급 줄 값(반영 · D-299 ④)": line}
    if ch.get(st.m) and not round(line):
        st.j.append(f"판매자서비스이용료: 이 달 판매 기간 쿠팡 지급 줄에 공제 없음(쿠팡 줄 없음) → 0 (D-299 ④ 쿠팡 줄 값만 · "
                    f"D-161 규칙 참고값 {ch[st.m]:,.0f}원은 넣지 않음)")


# ── 비중(D-237 · D-241 ①⑨ · D-271) ──
def _reg_rows(st: MonthState) -> list:
    rows = []
    for pid, p in sorted(st.d["inventory"].items(), key=lambda kv: (kv[1]["created"], kv[0])):
        opts = {str(v): {"구분": t, "관리": bool(st.is_mv.get(str(v)))} for v, t in p["types"].items()}
        in_m = str(pid) in st.mpids
        m = (not st.pre) and (in_m or any(o["관리"] for o in opts.values()))
        why = []
        if in_m:
            why.append("관리 상품 목록(정산 파일 판매 상품 · 판정표 추가 포함)")
        if any(o["관리"] for o in opts.values()):
            why.append(f"옵션 관리 판정 {sum(o['관리'] for o in opts.values())}/{len(opts)}(관리대장 VID·노출명)")
        rows.append({"등록상품ID": str(pid), "이름": p["name"], "등록일": p["created"], "관리": m, "근거": " · ".join(why) or "관리 아님", "옵션": opts})
    return rows


def shares(st: MonthState) -> None:
    tot = sum(st.allsales.values())
    man = sum(v for p, v in st.allsales.items() if st.is_m(p))
    st.sales_share = man / tot if tot else 0.0
    sold = [p for p, v in st.allsales.items() if round(v)]
    st.sold_n, st.sold_m = len(sold), sum(1 for p in sold if st.is_m(p))
    rows = _reg_rows(st)
    n, mm = len(rows), sum(r["관리"] for r in rows)
    st.reg_share = mm / n if n else None
    st.reg = {"구함": bool(n), "기준": f"정산 기준일 {st.basis} 상품조회 사본(`_raw/{st.aid}_vendor_inventory_p1.json.gz` · 쿠팡 전체 건수와 같음) · D-241 ①",
              "등록 상품 수": n, "관리 상품 수": mm, "비중": st.reg_share, "상품별": rows}
    st.share = min(st.sales_share, st.reg_share) if st.reg_share is not None else st.sales_share
    reg_txt = f"등록 비중 {mm}/{n}={pct(st.reg_share)}" if n else "등록 비중 자료 없음"
    st.basis_text = f"판매 비중 {pct(st.sales_share)} · {reg_txt} 중 작은 쪽"


def item_share(st: MonthState, cat: str) -> float:
    """9 항목의 반영 비중 — 계정 정액 3종 = 등록 비중(D-271 · 등록 자료 없으면 D-241 작은 쪽) · 그 밖 = D-241 작은 쪽."""
    if cat in FIXED_FEE_CATS and st.reg_share is not None:
        return st.reg_share
    return st.share


# ── 10 별도 입금 ──
def _fav_split(st: MonthState, rows: list) -> tuple[float, float, float]:
    """우대수수료 환급 줄 → (관리 몫, 상품 모르는 주문 금액, 계정 전체) · 날짜별 표 줄(st.fav_rows)."""
    st.fav_rows = []
    m = unk = tot = 0.0
    for x in rows:
        a = num(x.get("refundAmount"))
        tot += a
        pids = sorted(st.order_pids.get(str(x.get("orderId"))) or [])
        dt = x.get("realTransferDateStr") or x.get("expectedTransferDateStr")
        if pids:
            sh = sum(st.is_m(p) for p in pids) / len(pids)
            m += a * sh
            st.fav_rows.append((dt, x.get("transferStatus"), a * sh))
        else:
            unk += a
            st.fav_rows.append((dt, x.get("transferStatus"), a))
    return m, unk, tot


def _sep_notes(st: MonthState) -> None:
    add = [x for x in st.d["add"]["줄"] if str(x.get("지급일") or "")[:7] == st.m]
    if add:
        st.j.append(f"확인 필요: 이 달 추가지급 {len(add)}줄 — 이번 계산에 안 넣음")
    ex = [x for x in st.d["extras"] if str(x.get("일자"))[:7] == st.m]
    if ex:
        st.j.append(f"확인 필요: 이 달 쿠팡 별도 보상 {ex} — 이번 계산에 안 넣음")


def separate(st: MonthState) -> None:
    """10 별도 입금 = 우대수수료 환급(D-236 · 정산 금액에 넣음) — 주문 → 상품 관리 몫 · 상품 모르는 주문 = 계정 전체 금액(D-241 ②)."""
    fav = (st.d["v"].get("favorable") or {}).get(st.mk) or {}
    rows = fav.get("rows") or []
    m, unk, tot = _fav_split(st, rows)
    if (fav.get("totalCount") or 0) != len(rows):
        st.j.append(f"확인 필요: 우대수수료 환급 {st.mk} 목록 {len(rows)}줄 ≠ 쿠팡 전체 건수 {fav.get('totalCount')}")
    st.fav = {"계정 전체": tot, "관리 몫(주문 → 상품)": m, "상품 모르는 주문(계정 전체 금액 그대로)": unk, "건수": len(rows)}
    st.sep = []
    if round(m):
        st.sep.append(("우대수수료 환급 (카드 수수료 우대분 · 쿠팡페이)", m))
    if round(unk):
        st.sep.append(("우대수수료 환급 — 상품 확인 전 (계정 전체 금액)", unk))
        st.j.append(f"우대수수료 환급 중 주문이 아직 정산 파일에 없는 {unk:,.0f}원 = 상품을 몰라 계정 전체 금액 그대로 10 에 넣음"
                    "(D-241 ② · 쿠팡 자료로 상품이 확인되면 그때 상품별로 나눔)")
    _sep_notes(st)
