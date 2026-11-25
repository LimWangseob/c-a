"""쿠팡 확정 장부 월별 엑셀(`월별/{YYYY-MM}.xlsx`) — 계정·채널별 판매·수수료·정산대상·공제 항목별·최종지급·확정 여부·확정일·못 닫는 사유(D-419 ②).

금액 = 쿠팡 원문 합(지급 줄·정산 파일) · 관리 몫 없음. 검산 = 정산대상(지급 줄) + 보류 해제 + 추가지급 + 보상·판매조정 − 공제 − 최종지급액(0 이어야 함).
"""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from pathlib import Path

import openpyxl
from openpyxl.styles import Font

from coupang_analytics import settlement_confirmed_read as CR
from coupang_analytics import settlement_files as SF
from coupang_analytics import settlement_ledger as SL
from coupang_analytics import settlement_stats as SS

HEAD = ["계정ID", "계정명", "채널", "판매액", "판매자할인쿠폰", "판매수수료", "정산대상(정산 파일)", "정산대상(지급 줄)", "보류 해제·추가지급",
        "재고 보상·판매조정(+)", "공제 합계", "최종지급액", "검산 차이", "확정 여부", "확정일", "마지막 확인(수집일)", "못 닫는 사유", "다시 열린 이력"]
UNREAD = "원본 대조 못 함"              # 원본 파일을 못 읽은 달의 사유(정산 파일 합 칸 = 빈 칸)
AMOUNT_TO = HEAD.index("검산 차이") + 1
# 로켓그로스 공제 칸(쿠팡 원문 이름 → 엑셀 이름) · 추가공제 안의 항목 = 앞 묶음, 나머지 = '추가공제 그 밖'
RG_EXTRA = {"totalAdSalesDeductionAmount": "광고비", "totalMilkRunDeductionAmount": "밀크런",
            "totalNegativeDeductionAmount": "마이너스 정산 상계", "totalCoupangLiveDeductionAmount": "라이브",
            "totalDebitCardDeductionAmount": "체크카드", "totalArFactoringDeductionAmount": "빠른정산",
            "totalMerchantCashAdvanceDeductionAmount": "MCA 상환", "totalBusinessInsightsDeductionAmount": "비즈니스 인사이트",
            "totalSubscriptionFeeDeductionAmount": "세이버 구독", "totalPostPurchaseDeductionAmount": "리뷰 이벤트"}
RG_REST, RG_LOGI, WING_REST = "추가공제 그 밖", "로켓그로스 물류비", "윙 공제 그 밖"


def _wing(m) -> tuple[Counter, Counter]:
    """(합계, 공제 항목별) — 윙. 공제 항목 = 차감 사유 원문 이름 · 사유 합 ≠ 공제 합이면 '윙 공제 그 밖'."""
    s: Counter = Counter()
    d: Counter = Counter()
    for r in m.rows[SF.CH_WING]:
        ded = SL._num(r.get("totalDeductionAmount"))
        named: Counter = Counter()
        for x in r.get("차감 사유") or []:
            named[f"윙 {x.get('사유') or '(사유 없음)'}"] += SL._num(x.get("금액"))
        named[WING_REST] += ded - sum(named.values())
        d.update(named)
        s["공제"] += ded
        s["최종"] += SL._num(r["최종지급액"])
        s["대상"] += 0 if SL.extra_round(r) else SL._num(r.get("paidAmount"))
        s["해제"] += SL._num(r["최종지급액"]) if SL.additional(r) else SL._num(r.get("pendingAmount"))
    return s, d


def _rg(m) -> tuple[Counter, Counter]:
    s: Counter = Counter()
    d: Counter = Counter()
    for r in m.rows[SF.CH_RG]:
        extra, logi = SL._num(r.get("totalAdditionalDeductionAmount")), SL._num(r.get("totalFinalCfsFeeDeductionAmount"))
        named = Counter({name: SL._num(r.get(k)) for k, name in RG_EXTRA.items()})
        named[RG_REST] += extra - sum(named.values())
        named[RG_LOGI] += logi
        d.update(named)
        s["공제"] += extra + logi
        s["최종"] += SL._num(r["최종지급액"])
        s["대상"] += SL._num(r.get("totalPayableAmount"))
        s["보상"] += SL._num(r.get("totalCfsInventoryCompensationAmount")) + SL._num(r.get("totalSalesAdjustment"))
    return s, d


def _sales(m) -> dict:
    """채널 → 정산 파일 합(판매액·쿠폰·수수료·정산대상) — 윙 = 집계와 같은 줄 고르기."""
    files = m.settle_files()
    out: dict = {ch: Counter() for ch in (SF.CH_WING, SF.CH_RG)}
    wing = [r for _f, r in SS._order_rows([f for f in files if f.channel == SF.CH_WING], [])]
    for r in wing + [r for f in files if f.channel == SF.CH_RG for r in f.rows]:
        out[r.channel].update({"판매": r.sales, "쿠폰": r.coupon, "수수료": r.fee, "정산": r.settle})
    return out


def _state(e: dict) -> list:
    hist = " / ".join(f"{h['날']} {h['종류']}" + (f"(옛 확정일 {h['확정일']} · 보관 {h['보관'] or '없음'})" if h.get("확정일") else "")
                      for h in e["이력"])
    return [e["상태"], e["확정일"], e["수집일"], " / ".join(e["사유"]), hist]


def rows(pairs: list) -> tuple[list, list]:
    """(머리 줄, 줄들) — pairs = [(Month, 장부 기록)]. 공제 항목 칸 = 그 달에 0 이 아닌 항목만(이름 순)."""
    raw = []
    for m, e in pairs:
        sales = {} if any(w.startswith(UNREAD) for w in e["사유"]) else _sales(m)
        for ch, (s, d) in ((SF.CH_WING, _wing(m)), (SF.CH_RG, _rg(m))):
            f = sales.get(ch)
            if not (m.rows[ch] or f):
                continue
            check = s["대상"] + s["해제"] + s["보상"] - s["공제"] - s["최종"]
            raw.append(([m.aid, m.acct, ch, *(f[k] if f is not None else None for k in ("판매", "쿠폰", "수수료", "정산")), s["대상"], s["해제"], s["보상"], s["공제"], s["최종"],
                         round(check, 2), *_state(e)], d))
    names = sorted({n for _r, d in raw for n, v in d.items() if round(v)})
    return [*HEAD[:AMOUNT_TO], *(f"공제: {n}" for n in names), *HEAD[AMOUNT_TO:]], [
        [*r[:AMOUNT_TO], *(d[n] for n in names), *r[AMOUNT_TO:]] for r, d in raw]


def write(root: Path, idx: dict, ym: str, pairs: list, on_log) -> None:
    """바뀐 달만 다시 씀(지문 = 장부 기록의 '월별') — 파일이 열려 있어 못 쓰면 로그에 남기고 다음 배치가 다시 씀."""
    head, body = rows(pairs)
    mark = hashlib.sha256(json.dumps([head, body], ensure_ascii=False, default=str).encode()).hexdigest()
    p = root / CR.MONTHS / f"{ym}.xlsx"
    if idx["월별"].get(ym) == mark and p.is_file():
        return
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = ym
    ws.append(head)
    for r in body:
        ws.append(r)
    for c in ws[1]:
        c.font = Font(bold=True)
    for row in ws.iter_rows(min_row=2, min_col=4, max_col=len(head) - (len(HEAD) - AMOUNT_TO)):
        for c in row:
            c.number_format = "#,##0"
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = ws.dimensions
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    wb.save(tmp)
    wb.close()
    try:
        os.replace(tmp, p)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        on_log(f"❌ 월별 장부 {p} 못 씀(열려 있는지 확인) — {exc}")
        return
    idx["월별"][ym] = mark
