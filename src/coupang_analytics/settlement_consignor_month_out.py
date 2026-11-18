"""위탁자 정산서 3차 형식 — 원 단위 상품표 · 9 계정 공통 반영 · 자동 검산 · 판단 문장 · 결과 dict 조립.
T-38 S2(샘플 `s03_compute.py` build·_checks·_judgments 를 나눔 · 계산식·순서 그대로). 상품 줄 묶기 = `_names` · 날짜별 입금 = `_dep`.
"""
from __future__ import annotations

from collections import Counter

from coupang_analytics import settlement_statement_account as AC
from coupang_analytics.settlement_consignor_month_calc import MonthState, cum_round, month_end, pct
from coupang_analytics.settlement_consignor_month_cost import KINDS, PEND_KIND, RG_REVIEW_CAT, item_share
from coupang_analytics.settlement_consignor_month_dep import FAST, dep_rows, deposits, flow
from coupang_analytics.settlement_consignor_month_names import name_groups

LINE_NAMES = ("판매 금액", "판매자 할인쿠폰", "쿠팡 판매수수료", "쿠팡 부담 할인", "광고비", "창고·배송비(로켓그로스)",
              "창고 입고 운송비(밀크런)", "재고 분실·파손 보상")
# 9 계정 공통 고정 9줄(D-343 · 승인 샘플 11-19) — 분류(cat) → 줄 키. 목록에 없는 윙 차감 사유·광고 미표시 = '그 밖의 쿠팡 공제'
COMMON_ROWS = (("svc", "판매자서비스이용료"), ("saver", "로켓그로스 세이버 구독료"), ("bi", "비즈니스 인사이트 이용료"),
               ("live", "쿠팡 라이브 수수료"), ("review", "리뷰 이벤트 (체험단)"), ("pm3", "3PM 매출채권"), ("collect", "채권추심"),
               ("noprod", "상품 표시 없는 창고·운송·보상 비용"), ("etc", "그 밖의 쿠팡 공제"))
CAT_ROW = {"w:" + AC.SVC: "svc", "o:subscriptionFeeOffsetYearMonthBreakdown": "saver", "o:businessInsightsOffsetYearMonthBreakdown": "bi",
           "o:coupangLiveOffsetYearMonthBreakdown": "live", RG_REVIEW_CAT: "review", "w:" + AC.PM3: "pm3", "w:채권추심": "collect",
           "cfs": "noprod", "milk": "noprod", "comp": "noprod"}


# ── 원 단위 상품표(열마다 합계 = 반올림(소수 합) · 상품 칸 = 누적 반올림 · 확정 전 몫도 같은 방식) ──
def _group_sums(st: MonthState, merged: dict) -> tuple[dict, dict]:
    vals = {n: [0.0] * 9 for n in merged}
    pvals = {n: [0.0] * 9 for n in merged}
    for n, pids in merged.items():
        for p in pids:
            for k in range(1, 9):
                vals[n][k] += st.cols[p][k]
                pvals[n][k] += st.pend[p][k]
    return vals, pvals


def _round_col(names: list, vals: dict, k: int, into: dict) -> int:
    tot = round(sum(vals[n][k] for n in names))
    for n, v in zip(names, cum_round([vals[n][k] for n in names], tot)):
        into[n][k] = v
    return tot


def product_table(st: MonthState, merged: dict) -> dict:
    vals, pvals = _group_sums(st, merged)
    names = sorted((n for n in merged if any(abs(vals[n][k]) > 1e-9 for k in range(1, 9))),
                   key=lambda n: (-vals[n][1], n))          # 판매 금액 큰 순 · 금액 전혀 없는 상품은 뺌
    t = {"names": names, "int": {n: [0] * 9 for n in names}, "pint": {n: [0] * 9 for n in names}, "lines8": {}, "pend8": {}}
    for k in range(1, 9):
        t["lines8"][k] = _round_col(names, vals, k, t["int"])
        t["pend8"][k] = _round_col(names, pvals, k, t["pint"])
    L = t["lines8"]
    L["E"] = L[1] + L[2] + L[3] + L[4]
    return t


def _product_row(t: dict, n: str) -> dict:
    v, pv = t["int"][n], t["pint"][n]
    row = {"name": n, **{f"c{k}": v[k] for k in range(1, 9)}, "subtotal": sum(v[1:9])}
    if any(pv[1:9]):
        row["pending"] = {**{f"c{k}": pv[k] for k in range(1, 9)}, "subtotal": sum(pv[1:9])}
    return row


def rg_kinds(st: MonthState, line6: int) -> list:
    """6 종류별 = 고정 9줄(8 종류 + 정산 예정 · 값 없으면 0 · D-343) · 원 단위 = 누적 반올림(합 = 1쪽 6 · 끝전 줄 없음)."""
    keys = [k for k, _nm in KINDS] + [PEND_KIND]
    raw = [-st.kinds[k] for k in keys]
    if abs(sum(raw) - line6) >= 1:
        st.j.append(f"확인 필요: 6 종류별 합 {sum(raw):,.0f} ≠ 1쪽 6 {line6:,} — 차이는 누적 반올림으로 마지막 줄(종류별 내역 전)에 들어감")
    names = [nm for _k, nm in KINDS] + [PEND_KIND]
    return [{"name": nm, "amount": a, **({"pending": True} if k == PEND_KIND else {})} for k, nm, a in zip(keys, names, cum_round(raw, line6))]


def common_row(cat: str) -> str:
    if cat in CAT_ROW:
        return CAT_ROW[cat]
    if cat.startswith("w:") and "라이브" in cat:
        return "live"
    if cat.startswith("w:") and "리뷰" in cat:
        return "review"
    return "etc"


def common_out(st: MonthState) -> tuple[list, list]:
    """9 계정 공통 — 반영 = −반올림(쿠팡 금액 × 항목 비중 · D-241 작은 쪽 / 계정 정액 3종 = 등록 비중 D-271) → 고정 9줄로 합침(D-343 · 원문 항목 = parts)."""
    st.common_items = [(n, a, c) for n, a, c in st.common if round(a)]
    applied = [-round(a * item_share(st, c)) for n, a, c in st.common_items]
    rows = {k: {"key": k, "name": nm, "coupang_amount": 0, "applied_amount": 0, "parts": []} for k, nm in COMMON_ROWS}
    for (n, a, c), ap in zip(st.common_items, applied):
        r = rows[common_row(c)]
        r["coupang_amount"] += round(a)
        r["applied_amount"] += ap
        r["parts"].append({"name": n, "coupang_amount": round(a), "applied_amount": ap})
    return list(rows.values()), applied


def coupang_by_cat(st: MonthState) -> Counter:
    """분류별 쿠팡이 지급 줄에서 실제로 뺀 계정 금액(날짜별 표 위치 비율의 분모)."""
    c: Counter = Counter()
    c["ad"] = st.ad["deducted"]
    c["milk"] = st.milk["deducted"]
    c["cfs"] = st.cfs["line_fees"] + st.cfs["adjust"] + st.cfs["pending"]
    c["comp"] = -st.comp["paid"]
    for _n, a, cat in st.common_items:
        if cat.startswith(("o:", "w:", "r:", "svc")):
            c[cat] += a
    return c


# ── 자동 검산 ──
def _col_checks(out: dict, lines8: dict) -> list:
    c = []
    for k in range(1, 9):
        s = sum(p[f"c{k}"] for p in out["products"])
        c.append({"검사": f"2쪽 상품별 {k}열 합 = 1쪽 {k}", "값": [s, lines8[k]], "차이": s - lines8[k]})
        ps = sum((p.get("pending") or {}).get(f"c{k}", 0) for p in out["products"])
        pk = out["lines"][k - 1]["pending"]
        c.append({"검사": f"2쪽 상품별 {k}열 확정 전 합 = 1쪽 {k} 확정 전", "값": [ps, pk], "차이": ps - pk})
    return c


def _check(name: str, a, b) -> dict:
    return {"검사": name, "값": [a, b], "차이": a - b}


def checks(st: MonthState, out: dict, lines8: dict) -> list:
    sub = sum(p["subtotal"] for p in out["products"])
    s = out["product_subtotal"] + out["common"]["total_applied"] + sum(x["amount"] for x in out["separate"])
    pt = sum(x["pending"] for x in out["lines"]) + sum(x["applied_amount"] for x in out["common"]["items"] if x.get("pending"))
    c = _col_checks(out, lines8) + [
        _check("상품 정산액 = 1~8 합 = 상품별 소계 합", out["product_subtotal"], sub),
        _check("6 종류별 합 = 1쪽 6", sum(x["amount"] for x in out["rg_kinds"]), lines8[6]),
        _check("이번 정산 금액 = 상품 정산액 + 9 반영 + 10", out["settle_amount"], s),
        _check("확정 전 금액 = 1~8 확정 전 합 + 9 확정 전", out["pending_total"], pt),
        _check("어디로 갔나요 합 = 이번 정산 금액", sum(x["amount"] for x in out["flow"]), out["settle_amount"]),
        _check("11 날짜별 합 = 이번 정산 금액", sum(x["amount"] for x in out["deposits"]), out["settle_amount"])]
    cc = st.cash
    cc["검산(실제 = 정산금액 − 공제 − 판매 조정)"] = round(cc["그 줄 정산금액 합"] - cc["그 줄에서 빠진 공제(판매 조정 제외)"]
                                               - cc["판매 조정·음수 공제(환불 회수 · 날짜만 옮김)"] - cc["이 달 판매 기간 지급 줄 실제 지급액 합(계정 전체)"])
    return c + st.chk + [{"검사": "참고 — 이 달 판매 기간 쿠팡 지급 줄 실제 지급액과 이 정산서의 차이 구성", **{k: round(v) for k, v in cc.items()}}]


# ── 판단 문장 ──
FIXED = [
    "달 나누는 기준(쿠팡이 붙인 달): 1~4 = 매출인식일 달(정산집계 '상품별 월별') · 6 = 물류비 리포트 매출인식일 달(= 이 달 판매 기간 지급 줄의 창고비 칸, 원 단위 일치) · "
    "5 = 광고 날짜 달(광고정산 청구가능액 × 1.1) · 7 = 밀크런 픽업 달(밀크런 파일) · 8 = 쿠팡 정산 주기 달(재고 손실 보상 리포트 파일 = 이 달 지급 줄 보상 칸) — "
    "8 은 정산집계의 '발생일' 달과 다를 수 있음(전체 기간 합은 같음)",
    "4 쿠팡 부담 할인 = 쿠팡 정산금액 − (판매 금액 − 판매자 할인쿠폰 − 판매수수료) — 기존 정산서 'D 쿠팡 지원 할인'과 같은 식",
    "광고·밀크런 상품 나누기 = 기존 코드와 같은 규칙(광고: 날짜×캠페인 청구액을 그날 광고 보고서 옵션 광고비 비율로 · 밀크런: 입고 건 적치 수량 비율) — 관리 밖 상품 몫은 정산서에 안 넣음",
    "날짜별 표(11) = 이 달 판매 지급 줄의 관리 몫 정산금액(줄 정산금액 × 판매 방식별 관리 비율) − 이 달 비용을 쿠팡이 실제로 뺀 지급 줄(광고·밀크런·창고비·보상의 실제 공제 줄)의 관리 몫 · "
    "같은 날 쿠팡 지급에는 다른 달 판매·비용도 섞여 있어 통장 입금액과 1:1 로 같지 않음(차이 구성 = checks 마지막 '참고' 줄)",
    "판매 조정·음수 공제(이미 정산된 판매의 환불을 쿠팡이 다른 지급에서 먼저 빼고 나중에 돌려주는 돈)는 날짜만 옮기는 돈이라 정산 금액·날짜별 표에 넣지 않음(환불 자체는 1 판매 금액에 이미 들어 있음)",
]


def _judge_status(st: MonthState, out: dict) -> str:
    if out["status"] == "확정":
        return (f"기간 = {st.m} 판매분 · 자료 기준일 {st.basis} · 상태 '확정' — 이 달 판매 기간의 상품별 정산 파일이 모두 있음"
                "(지급 '예정' 줄은 금액 확정·지급일만 남음)")
    weeks = sorted({f"{row[3][5:]}~{row[4][5:]}({r['채널']})" for _key, row, r in st.lines() if st.pend_line(row, r)})
    return (f"기간 = {st.m} 판매분 · 자료 기준일 {st.basis} · 상태 '정산 예정 포함'(D-242 A안) — 상품별 정산 파일이 아직 없는 판매 기간 "
            f"{', '.join(weeks)} 은 쿠팡 정산 줄 금액(쿠팡 계산 · 확정 전)을 넣고 상품 판매 비율로 나눔 · 확정 전 금액 {out['pending_total']:,}원(바뀔 수 있음) · "
            "방법·원천 = pending_detail")


def _judge_tables(st: MonthState) -> list:
    j = []
    if st.ext_used:
        j.append(f"광고·밀크런·정산 예정(옵션 단위 자료)은 관리 VID 로 판정 — 정산 파일에 판매가 없어 등록상품 목록(mpids)에는 없는 관리 상품 "
                 f"{sorted(st.ext_used)}({', '.join(st.names.get(p, p) for p in sorted(st.ext_used))})의 금액이 그 상품 줄로 들어감")
    for x in st.added:
        j.append(f"관리 상품 추가(판정표 {st.judge.added_path}): {x['등록상품ID']} {st.names.get(str(x['등록상품ID']), '')} — {x['근거']}")
    for x in getattr(st, "name_used", []):
        if len(x["등록상품ID"]) > 1 or "확인 필요" in x["판정"]:
            j.append(f"상품 이름 {x['판정']}(Claude 판정): '{x['표시 이름']}' = {', '.join(x['등록상품ID'])} — {x['근거']} (판정표 {st.judge.names_path})")
    return j


def _judge_flow(st: MonthState) -> list:
    j = []
    if st.pend_cost:
        j.append("6·7·8 상품 자료 전 금액(창고비·밀크런·재고 보상)은 이 달 로켓그로스 상품 판매(확정+예정) 비율로 나눔 — 이 세 비용은 로켓그로스 재고에만 생겨 "
                 "판매자배송(윙) 판매는 나누는 기준에서 뺌(Claude 판단 · 설계서 '이 달 상품 판매 비율'을 로켓그로스로 좁힘)")
    if st.fast["계정 전체"]:
        j.append(f"빠른정산 상환: 이 달 판매 지급 줄({', '.join(sorted(set(st.fast['지급일'])))})에서 쿠팡이 상환으로 빼는 {st.fast['계정 전체']:,.0f}원(계정 전체) = "
                 f"이미 먼저 받은 돈(D-312 ①) → 날짜 줄에서 빼고 '{FAST}' 줄·'빠른정산으로 먼저 받음'으로 따로 표시(관리 몫 {st.fast['관리 몫']:,.0f})")
    else:
        j.append("빠른정산 상환: 이 달 판매 지급 줄에 없음(0) → '어디로 갔나요' 빠른정산 줄 공란(D-343)")
    own = {k: v for k, v in st.own.items() if round(v)}
    if own:
        j.append("위탁자 본인 차감(D-312 ② · 관리 몫 0 · 이 정산서 금액·날짜별 표에 안 넣음): "
                 + " · ".join(f"{k.split('— ')[-1]} {v:,.0f}원" for k, v in sorted(own.items())))
    return j


def _judge_share(st: MonthState) -> list:
    j = [st.ad_note] if st.ad_note else []
    r = st.reg
    if r["구함"]:
        j.append(f"9 적용 비중 = 판매 비중 {pct(st.sales_share)}(이 달 관리 판매 ÷ 계정 판매 · 확정+예정) 과 등록 비중 {r['관리 상품 수']}/{r['등록 상품 수']}"
                 f"={pct(st.reg_share)}({r['기준']} · 관리 = 관리 상품 목록 또는 옵션 하나라도 관리 판정) 중 작은 쪽 {pct(st.share)} (D-237 · D-241 ⑨)"
                 " · 계정 정액 3종(판매자서비스이용료·세이버 구독료·비즈니스 인사이트) = 등록 비중(D-271)")
    return j


def judgments(st: MonthState, out: dict) -> list:
    return list(st.judge.notes) + list(st.j) + _judge_tables(st) + [_judge_status(st, out)] + FIXED + _judge_flow(st) + _judge_share(st)


def evidence(st: MonthState, merged: dict, names: list) -> dict:
    ev = {"판매 비중": {"관리 판매": sum(v for p, v in st.allsales.items() if st.is_m(p)),
                    "계정 판매": sum(st.allsales.values()), "비중": st.sales_share,
                    "판매 상품 수": st.sold_n, "그중 관리": st.sold_m},
          "등록 비중": st.reg, "적용 비중": st.share, "광고": st.ad, "창고·배송비": st.cfs, "밀크런": st.milk,
          "재고 보상": st.comp, "판매자서비스이용료": st.svc, "우대수수료 환급": st.fav,
          "배송비(관리 몫)": [round(st.ship_m[0]), round(st.ship_m[1])],
          "비용 위치 못 찾음(입금 예정으로)": {k: round(v) for k, v in st.unlocated.items()},
          "6·7·8 상품 자료 전 금액(계정 전체 → 관리 몫)": {k: [round(v), round(st.pend_cost_m.get(k, 0.0))] for k, v in st.pend_cost.items()},
          "빠른정산 상환": {k: (round(v) if isinstance(v, float) else v) for k, v in st.fast.items()},
          "위탁자 본인 차감(관리 몫 0 · D-312 ②)": {k: round(v) for k, v in st.own.items() if round(v)},
          "관리 상품 추가 판정": st.added,
          "상품 등록상품ID": {n: merged[n] for n in names}}
    if st.missing:
        ev["상품명 판정 후보"] = st.missing
    return ev


# ── 조립 ──
def _head(st: MonthState) -> dict:
    info = st.d["info"]
    return {"account": st.aid, "company": info["사업자"], "ceo": info["대표자"],
            "period_start": f"{st.m}-01", "period_end": f"{month_end(st.m)}", "basis_date": st.basis}


def _active(st: MonthState) -> list:
    return sorted(p for p in set(st.cols) | set(st.pend) if any(abs(st.cols[p][k]) > 1e-9 for k in range(1, 9)))


def assemble(st: MonthState) -> dict:
    """계산 끝난 상태 → 정산서 자료 dict(샘플 data_*.json 과 같은 키)."""
    merged = name_groups(st, _active(st))
    t = product_table(st, merged)
    lines8, pend8 = t["lines8"], t["pend8"]
    subtotal = sum(lines8[k] for k in range(1, 9))
    c_items, applied = common_out(st)
    st.coupang_cat = coupang_by_cat(st)
    sep_int = [(n, round(a)) for n, a in st.sep]
    settle = subtotal + sum(applied) + sum(a for _, a in sep_int)
    deposits(st, lines8, applied)
    rows = dep_rows(st, settle - sum(a for _, a in sep_int), sep_int)
    fl = flow(st, rows)
    pending_total = sum(pend8.values()) + sum(x["applied_amount"] for x in c_items if x.get("pending"))
    out = {**_head(st), "status": "정산 예정 포함" if pending_total or st.pend_info else "확정",
           "lines": [{"no": i, "name": LINE_NAMES[i - 1], "amount": lines8[i], "pending": pend8[i]} for i in range(1, 9)],
           "product_subtotal": subtotal, "products": [_product_row(t, n) for n in t["names"]], "rg_kinds": rg_kinds(st, lines8[6]),
           "common": {"items": c_items, "basis_text": st.basis_text,
                      "total_coupang": sum(x["coupang_amount"] for x in c_items), "total_applied": sum(applied)},
           "separate": [{"name": n, "amount": a} for n, a in sep_int],
           "settle_amount": settle, "pending_total": pending_total, "pending_detail": st.pend_info, "flow": fl, "deposits": rows}
    out["checks"] = checks(st, out, lines8)
    out["judgments"] = judgments(st, out)
    out["_근거"] = evidence(st, merged, t["names"])
    return out
