"""정산 계산 모듈 오프라인 검증 — designs/coupang_golden_cases.json 100% + 규칙 핀. SSOT=designs/SETTLEMENT_MODULE.md §6.

로그인·공휴일 API·정산 API 호출 없음(결정적). 공휴일은 골든 `_meta.holidays_used` 주입.
실패 시 AssertionError → exit 1. run_checks 게이트 편입 대상.

    python tools/verify_settlement_offline.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics import holiday_kr as HK  # noqa: E402
from coupang_analytics import payout as P  # noqa: E402
from coupang_analytics import settlement_amount as SA  # noqa: E402
from coupang_analytics import settlement_parse as SP  # noqa: E402

GOLDEN = json.loads((ROOT / "designs" / "coupang_golden_cases.json").read_text(encoding="utf-8"))
HOL = {date.fromisoformat(d) for d in GOLDEN["_meta"]["holidays_used"]}
D = date.fromisoformat


def ok(msg):
    print(f"  ✔ {msg}")


def expect(exc, fn, what):
    try:
        fn()
    except exc:
        return
    raise AssertionError(f"{what} — {exc.__name__} 안 남")


# ── 골든 ──────────────────────────────────────────────────────────
def g1_payout_dates():
    print("[G1] 지급일 골든 12케이스")
    cases = GOLDEN["payout_date"]
    for c in cases:
        week = c.get("confirm_week") or c.get("sales_week")
        got = P.payout_date(c["policy"], week_end=D(week[1]) if week else None,
                            revenue_month=c.get("revenue_month"), holidays=HOL)
        assert got == D(c["expected"]), (c, got)
    assert len(cases) == 12, len(cases)
    ok(f"{len(cases)}/{len(cases)} 일치(마감일+15/20영업일·월 경계 분할=같은 주 일요일·MP FINAL 익익월 1일 무보정)")


def g2_amounts():
    print("[G2] 금액 골든 2케이스")
    by = {c["policy"]: c for c in GOLDEN["amount_formula"]}
    m = by["MP_REVENUE_REPORT"]
    r = SA.mp_revenue(sales=m["A_sales"], seller_coupon=m["B_seller_coupon"], fee=m["C_fee"],
                      myshop_fee=m["D_myshop_fee"], deduction=m["F_deduction"])
    assert (r.settlement_target, r.final_payout) == (m["expected_E"], m["expected_final"]), r
    h = by["RG_HOME_PROFIT"]
    p = SA.rg_home_profit(sales=h["sales"], seller_coupon=h["seller_coupon"], fee=h["fee"],
                          fulfillment=h["fulfillment"], ads=h["ads"], review_event=h["review_event"],
                          inventory_compensation=h["inventory_compensation"])
    assert (p.cost, p.profit, p.margin_pct) == (h["expected_cost"], h["expected_profit"], h["expected_margin_pct"]), p
    assert len(by) == 2
    ok("윙 E·최종 / RG 비용·이익·마진% 일치")


def g3_invariants():
    print("[G3] 판매분석 불변식 골든 4행(음수 행 통과)")
    rows = GOLDEN["insights_row_invariants"]
    for c in rows:
        row = SimpleNamespace(**{k: c[k] for k in ("sales", "orders", "units", "views", "total_sales",
                                                   "total_units", "cancel_amount", "cancel_units")},
                              cvr_pct=Decimal(str(c["cvr_pct"])))
        assert SP.check_invariants(row) == [], (c, SP.check_invariants(row))
    assert len(rows) == 4 and len(GOLDEN["invariant_rules"]) == 3
    bad = SimpleNamespace(sales=100, total_sales=90, cancel_amount=0, units=2, total_units=2, cancel_units=0,
                          orders=1, views=3, cvr_pct=Decimal("33.00"))
    assert len(SP.check_invariants(bad)) == 2                          # 매출식 + 전환율(33.33) 위반
    ok("골든 4행 위반 0(판매자배송 -35000 포함)·3식 적용·위반 행은 잡음")


# ── 규칙 핀 ───────────────────────────────────────────────────────
def p1_holidays():
    print("[P1] 영업일·대체공휴일·공휴일 소스 실패")
    assert HK.add_business_days(D("2026-08-09"), 1, HOL) == D("2026-08-10")
    assert HK.next_business_day(D("2026-09-26"), HOL) == D("2026-09-28")        # 추석 토 → 월
    assert HK.next_business_day(D("2026-09-28"), HOL) == D("2026-09-28")        # 영업일 자신
    expect(ValueError, lambda: HK.add_business_days(D("2026-08-09"), 0, HOL), "0영업일")
    subs = HK.substitute_holidays({D("2026-08-15"): HK.KIND_NATIONAL,           # 광복절 토 → 8/17
                                   D("2026-09-24"): HK.KIND_LUNAR, D("2026-09-25"): HK.KIND_LUNAR,
                                   D("2026-09-26"): HK.KIND_LUNAR})             # 추석 목~토 → 대체 없음
    assert subs == {D("2026-08-17")}, subs
    s25 = HK.substitute_holidays({D("2025-05-05"): (HK.KIND_NATIONAL, HK.KIND_NATIONAL),   # 어린이날+부처님오신날
                                  D("2025-10-03"): HK.KIND_NATIONAL, D("2025-10-05"): HK.KIND_LUNAR,
                                  D("2025-10-06"): HK.KIND_LUNAR, D("2025-10-07"): HK.KIND_LUNAR})
    assert s25 == {D("2025-05-06"), D("2025-10-08")}, s25                     # 겹침→5/6·추석 일요일→10/8
    assert HK.substitute_holidays({D("2027-02-06"): HK.KIND_LUNAR, D("2027-02-07"): HK.KIND_LUNAR,
                                   D("2027-02-08"): HK.KIND_LUNAR}) == {D("2027-02-09")}   # 설 토·일 → 일요일분 1일
    with tempfile.TemporaryDirectory() as tmp:
        expect(HK.HolidaySourceError, lambda: HK.holidays(2026, cache_dir=tmp), "소스·캐시 없음")
        expect(HK.HolidaySourceError, lambda: HK.holidays(2026, cache_dir=tmp, fetch=lambda y: []), "빈 결과")
        expect(HK.HolidaySourceError, lambda: HK.holidays(2026, cache_dir=tmp, fetch=lambda y: 1 / 0), "조회 예외")
        expect(HK.HolidaySourceError, lambda: HK.holidays(2026, cache_dir=tmp, fetch=lambda y: ["2025-01-01"]),
               "다른 해")
        calls = []
        got = HK.holidays(2026, cache_dir=tmp, fetch=lambda y: calls.append(y) or ["2026-08-17", "2026-09-24"])
        again = HK.holidays(2026, cache_dir=tmp, fetch=lambda y: calls.append(y) or [], extra=["2026-06-03"])
        assert got == {D("2026-08-17"), D("2026-09-24")} and calls == [2026]           # 두 번째는 캐시
        assert again == got | {D("2026-06-03")}                                           # 임시공휴일 수동 추가
    ok("영업일 가산·다음 영업일·대체공휴일(광복절 토·추석 토 무대체·겹침·추석 일요일·설 토일)·실패=예외·캐시·수동 추가")


def p2_payout_rules():
    print("[P2] 지급 규칙 — 골든 밖 정책·인자 검증·행 단위 반올림")
    assert P.week_sunday(D("2026-08-31")) == D("2026-09-06") and P.week_sunday(D("2026-09-06")) == D("2026-09-06")
    assert P.payout_date(P.PAYOUT_MP_MONTHLY, revenue_month="2026-08", holidays=HOL) == \
        HK.add_business_days(D("2026-08-31"), 15, HOL)
    assert P.payout_date(P.PAYOUT_RG_MONTHLY, revenue_month="2026-08", holidays=HOL) == \
        HK.add_business_days(D("2026-08-31"), 20, HOL)
    assert P.payout_date(P.PAYOUT_RG_WEEKLY_FINAL, revenue_month="2025-01", holidays=HOL) == D("2025-03-03")  # 토→월
    assert P.payout_date(P.PAYOUT_RG_WEEKLY_FINAL, revenue_month="2024-11",
                         holidays={D("2025-01-01")}) == D("2025-01-02")          # 익익월 1일 공휴일 → 다음 영업일
    expect(ValueError, lambda: P.payout_date("PAYOUT_X", week_end=D("2026-08-09"), holidays=HOL), "미지 정책")
    expect(ValueError, lambda: P.payout_date(P.PAYOUT_MP_WEEKLY_1ST, holidays=HOL), "week_end 누락")
    expect(ValueError, lambda: P.payout_date(P.PAYOUT_MP_MONTHLY, holidays=HOL), "revenue_month 누락")
    expect(ValueError, lambda: P.payout_date(P.PAYOUT_MP_MONTHLY, revenue_month="2026/08", holidays=HOL), "월 형식")
    assert P.payout_amount(P.PAYOUT_MP_WEEKLY_1ST, [15, 25]) == 11 + 18        # 10.5→11·17.5→18(사사오입·행 단위)
    assert P.payout_amount(P.PAYOUT_MP_WEEKLY_FINAL, [15, 25]) == 5 + 8        # 4.5→5·7.5→8
    expect(TypeError, lambda: P.payout_amount(P.PAYOUT_MP_WEEKLY_1ST, [1.5]), "정수 아닌 금액")
    e = P.estimate(P.PAYOUT_RG_WEEKLY_1ST, week_end=D("2026-08-30"), holidays=HOL, row_amounts=[100])
    assert (e.date, e.amount, e.is_estimate) == (D("2026-09-29"), 70, True)
    ok("월정산·RG 최종액(첫 영업일)·인자 검증·70/30 행 단위 사사오입·예측 표기")


def p3_amount_rules():
    print("[P3] 금액 규칙 — RG 실지급·매출 0 마진·정수 강제")
    assert SA.rg_payout(settlement_target=1000, milkrun=100, ads=200, cfs=50) == 650
    z = SA.rg_home_profit(sales=0, seller_coupon=0, fee=0, fulfillment=0, ads=10, review_event=0)
    assert (z.profit, z.margin_pct) == (-10, None)                              # 매출 0 = 마진 정의 불가(0% 아님)
    c = SA.rg_home_profit(sales=1000, seller_coupon=0, fee=0, fulfillment=0, ads=0, review_event=0,
                          inventory_compensation=50)
    assert (c.cost, c.profit, c.margin_pct) == (-50, 1050, 105.0)              # 재고손실보상 = 이익 가산
    h = SA.rg_home_profit(sales=400, seller_coupon=0, fee=0, fulfillment=0, ads=351, review_event=0)
    assert h.margin_pct == 12.3, h                                              # 12.25 → 사사오입 12.3(은행가 12.2 아님)
    expect(TypeError, lambda: SA.mp_revenue(sales="1000", seller_coupon=0, fee=0), "문자열 금액")
    expect(TypeError, lambda: SA.rg_payout(settlement_target=1.0, milkrun=0, ads=0, cfs=0), "소수 금액")
    ok("RG 실지급·매출 0 → 마진 None·재고손실보상 가산·정수 아닌 금액 거부")


HDR = list(SP.REQUIRED_HEADERS)


def _raw(**over):
    base = {"옵션 ID": "94632081597", "옵션명": "1개", "상품명": "예시", "등록상품ID": "1234567890",
            "카테고리": "건강", "판매방식": "로켓그로스", "매출(원)": "285,900", "주문": "12", "판매량": "13",
            "방문자": "105", "조회": "159", "장바구니": "20", "구매전환율": "7.55%",
            "아이템위너 비율(%)": "1.10000000000000008881", "총 매출(원)": "285900", "총 판매수": "13",
            "총 취소 금액(원)": "0", "총 취소된 상품수": "0", "즉시 취소된 상품수": "0"}
    base.update(over)
    return [base[h] for h in HDR]


def p4_parse():
    print("[P4] 판매분석 파싱 — 헤더 이름·전 셀 문자열·ID 문자열·실패=오류·메타 강제·불변식 경고")
    meta = {"period_start": "2026-09-01", "period_end": 46293, "account_id": "ex01"}      # 시리얼 46293=2026-09-28
    shuffled = list(reversed(HDR))
    rows = [shuffled, list(reversed(_raw())),
            list(reversed(_raw(**{"옵션 ID": "95907346795", "판매방식": "판매자배송", "매출(원)": "-35000",
                                  "주문": "-1", "판매량": "-1", "조회": "13", "구매전환율": "-7.69%",
                                  "총 매출(원)": "0", "총 판매수": "0", "총 취소 금액(원)": "-35000",
                                  "총 취소된 상품수": "-1"}))),
            [""] * len(HDR),
            list(reversed(_raw(**{"옵션 ID": "95222903297", "매출(원)": "100"})))]              # 매출식 위반
    logs: list = []
    f = SP.parse_insights_rows(rows, **meta, on_log=logs.append)
    assert f.meta == SP.InsightsMeta(D("2026-09-01"), D("2026-09-28"), "ex01")
    assert [r.option_id for r in f.rows] == ["94632081597", "95907346795", "95222903297"]    # 빈 행 건너뜀·열 순서 무관
    r0 = f.rows[0]
    assert (r0.sales, r0.cvr_pct, r0.item_winner_pct, r0.product_id) == (285900, Decimal("7.55"), Decimal("1.10"),
                                                                         "1234567890")
    assert f.rows[1].sales == -35000                                               # 음수 정상·필터링 없음
    assert len(f.warnings) == 1 and "95222903297" in f.warnings[0] and any("불변식" in m for m in logs)
    expect(SP.SettlementParseError, lambda: SP.parse_insights_rows(rows, period_start="2026-09-01", period_end="",
                                                                   account_id="ex01"), "메타 없음")
    expect(SP.SettlementParseError, lambda: SP.parse_insights_rows(rows, period_start="2026-09-30",
                                                                   period_end="2026-09-01", account_id="a"), "기간 역전")
    expect(SP.SettlementParseError, lambda: SP.parse_insights_rows([HDR[:-1], _raw()[:-1]], **meta), "헤더 누락")
    for bad in ({"매출(원)": "12a"}, {"주문": ""}, {"판매량": "1.5"}, {"구매전환율": "없음"}, {"옵션 ID": "9.46E+10"}):
        expect(SP.SettlementParseError, lambda b=bad: SP.parse_insights_rows([HDR, _raw(**b)], **meta), f"값 {bad}")
    try:
        SP.parse_insights_rows([HDR[1:], _raw()[1:]], **meta)
    except SP.SettlementParseError as exc:
        assert "옵션 ID" in str(exc)                                                # 누락 목록 명시
    assert SP.parse_date("2026.9.1") == D("2026-09-01") and SP.parse_date(45658) == D("2025-01-01")
    ok("열 순서 무관·빈 행·음수 행·ID/비율 문자열·메타 강제(시리얼 날짜)·헤더/값 실패 오류·불변식 위반=경고")


class _Resp:
    """requests.Response 대역(녹화 응답)."""
    def __init__(self, payload=None, *, status=200, text=None):
        self.status_code = status
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload, ensure_ascii=False)

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def _kasi(items, total=None, code="00"):
    body_items = "" if items == [] else {"item": items[0] if len(items) == 1 else items}
    return {"response": {"header": {"resultCode": code, "resultMsg": "NORMAL SERVICE."},
                         "body": {"items": body_items, "numOfRows": 100, "pageNo": 1,
                                  "totalCount": len(items) if total is None else total}}}


def p5_holiday_source():
    print("[P5] 공휴일 API(특일정보) — 녹화 응답 파싱·오류 코드·holiday_kr 연결(실 API 미호출)")
    from coupang_analytics import holiday_source as HS
    y2026 = [{"dateKind": "01", "dateName": "광복절", "isHoliday": "Y", "locdate": 20260815, "seq": 1},
             {"dateKind": "01", "dateName": "대체공휴일", "isHoliday": "Y", "locdate": 20260817, "seq": 1},
             {"dateKind": "01", "dateName": "추석", "isHoliday": "Y", "locdate": 20260924, "seq": 1},
             {"dateKind": "01", "dateName": "추석", "isHoliday": "Y", "locdate": 20260925, "seq": 1},
             {"dateKind": "01", "dateName": "추석", "isHoliday": "Y", "locdate": 20260926, "seq": 1},
             {"dateKind": "01", "dateName": "제헌절", "isHoliday": "N", "locdate": 20260717, "seq": 1}]
    sent = []

    def get(resp):
        def http_get(url, params=None, timeout=None):
            sent.append((url, dict(params)))
            return resp
        return http_get
    days = HS.make_fetch("KEY", http_get=get(_Resp(_kasi(y2026))))(2026)
    assert days == {D("2026-08-15"), D("2026-08-17"), D("2026-09-24"), D("2026-09-25"), D("2026-09-26")}, days
    url, params = sent[-1]
    assert url == HS.ENDPOINT and params["solYear"] == "2026" and params["_type"] == "json" and params["ServiceKey"] == "KEY"
    assert HS.make_fetch("K", http_get=get(_Resp(_kasi(y2026[:1]))))(2026) == {D("2026-08-15")}   # 1건 = dict 응답
    assert HS.parse_rest_days(_kasi([]), 2026) == set()                                          # 0건 = items ""
    xml = ("<OpenAPI_ServiceResponse><cmmMsgHeader><returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR"
           "</returnAuthMsg><returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>")
    bad = [("인증오류 XML", _Resp(None, text=xml)), ("HTTP 500", _Resp(None, status=500, text="err")),
           ("서비스 오류코드", _Resp(_kasi(y2026, code="22"))), ("건수 불일치", _Resp(_kasi(y2026, total=120))),
           ("JSON 아님", _Resp(None, text="oops")),
           ("다른 해", _Resp(_kasi([{"isHoliday": "Y", "locdate": 20250101}])))]
    for what, resp in bad:
        expect(HS.HolidayApiError, lambda r=resp: HS.make_fetch("K", http_get=get(r))(2026), what)
    for resp in (_Resp(None, text=xml), _Resp(None, status=500, text="err"), _Resp(None, text="oops")):
        try:
            HS.make_fetch("SECRET-9f3a", http_get=get(resp))(2026)
        except HS.HolidayApiError as exc:
            assert "SECRET-9f3a" not in str(exc), exc                            # 오류 문구에 키 노출 금지
    try:
        HS.make_fetch("K", http_get=get(_Resp(None, text=xml)))(2026)
    except HS.HolidayApiError as exc:
        msg = str(exc)                                                           # 원인 문구·코드를 풀어서 보여줌
        assert "인증" in msg and "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in msg and "코드 30" in msg, msg
    expect(HS.HolidayApiError, lambda: HS.make_fetch("  "), "키 없음")
    expect(HS.HolidayApiError, lambda: HS.fetch_from_store(SimpleNamespace(get_password=lambda k: None)), "저장 키 없음")
    with tempfile.TemporaryDirectory() as tmp:                                     # holiday_kr 연결: 실패=HolidaySourceError
        expect(HK.HolidaySourceError,
               lambda: HK.holidays(2026, cache_dir=tmp, fetch=HS.make_fetch("K", http_get=get(_Resp(None, text=xml)))),
               "API 오류 → 지급일 계산 중단")
        hol = HK.holidays(2026, cache_dir=tmp, fetch=HS.make_fetch("K", http_get=get(_Resp(_kasi(y2026)))))
        assert P.payout_date(P.PAYOUT_MP_WEEKLY_1ST, week_end=D("2026-08-09"), holidays=hol) == D("2026-08-31")
    ok("대체·연휴 포함·isHoliday=N 제외·1건 dict·0건·인증 XML/HTTP/코드/건수/형식/다른 해 오류·키 없음·홀리데이 연결")


def main():
    g1_payout_dates()
    g2_amounts()
    g3_invariants()
    p1_holidays()
    p2_payout_rules()
    p3_amount_rules()
    p4_parse()
    p5_holiday_source()
    print("정산 계산 모듈 오프라인 검증 통과(골든 payout 12·amount 2·불변식 4행/3식 100%)")


if __name__ == "__main__":
    main()
