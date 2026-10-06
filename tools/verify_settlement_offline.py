"""정산 계산 모듈 오프라인 검증 — designs/coupang_golden_cases.json 100% + 규칙 핀. SSOT=designs/SETTLEMENT_MODULE.md §6.

로그인·공휴일 API·정산 API 호출 없음(결정적). 공휴일은 골든 `_meta.holidays_used` 주입.
실패 시 AssertionError → exit 1. run_checks 게이트 편입 대상.

    python tools/verify_settlement_offline.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date, timedelta
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
    # 실측 규칙(2026-10-06): 윙 70%=전체×70% · 로켓그로스 70%=줄별 70% 사사오입 합 · 30%=전체−70%
    assert P.payout_amount(P.PAYOUT_MP_WEEKLY_1ST, [15, 25]) == 28             # 40×0.7 (줄별이면 29)
    assert P.payout_amount(P.PAYOUT_MP_WEEKLY_FINAL, [15, 25]) == 40 - (11 + 18)  # 윙 최종액=주별 합계마다 70% 뺀 나머지
    assert P.payout_amount(P.PAYOUT_MP_WEEKLY_FINAL, [49721, 16364, 11191, 337770]) == 124513   # 실측 8월 최종액 화면값
    assert P.payout_amount(P.PAYOUT_RG_WEEKLY_1ST, [15, 25]) == 11 + 18        # 10.5→11·17.5→18(줄별)
    assert P.payout_amount(P.PAYOUT_RG_WEEKLY_FINAL, [15, 25]) == 40 - 29      # 나머지(줄별 30% 합 5+8=13 아님)
    assert P.payout_amount(P.PAYOUT_RG_MONTHLY, [15, 25]) == 40
    assert P.payout_amount(P.PAYOUT_MP_WEEKLY_1ST, [337770]) == 236439          # 실측 윙 8/24~30 주 화면값
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


def p6_diag_no_values():
    print("[P6] 정산 주소 실측 도구 — 구조만 기록·값(금액·이름·주문번호·질의값) 비저장")
    import importlib.util
    spec = importlib.util.spec_from_file_location("diag_se", ROOT / "tools" / "diag_settlement_endpoints.py")
    DG = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(DG)
    payload = {"data": [{"orderId": "31234567890", "productName": "비밀상품명", "settlementAmount": 3764453,
                         "detail": {"fee": 414947, "items": [{"vendorItemId": "94632081597"}]}}], "total": 7}
    e = DG.entry("POST", "https://wing.coupang.com/tenants/settlement/v2/search?vendorId=A00123&from=2026-09-01",
                 200, "fetch", "application/json;charset=UTF-8",
                 json.dumps({"vendorId": "A00123", "period": {"from": "2026-09-01"}}), payload)
    dumped = json.dumps(e, ensure_ascii=False)
    for secret in ("31234567890", "비밀상품명", "3764453", "414947", "94632081597", "A00123", "2026-09-01"):
        assert secret not in dumped, (secret, dumped)
    assert e["query"] == ["from", "vendorId"] and e["path"] == "/tenants/settlement/v2/search"
    assert e["response"]["data"]["item"]["detail"]["fee"] == "int" and e["response"]["data"]["__list__"] == 1
    assert e["request"] == {"vendorId": "str", "period": {"from": "str"}}
    assert DG.body_keys("a=1&b=secret") == {"__form__": ["a", "b"]} and DG.body_keys("rawtext") == {"__text_len__": 7}
    keyed = DG.shape({"94632081597": {"qty": 3}, "95222903297": {"qty": 1}, "2026-09-01": 5, "20260902": 6,
                      "status": "DONE"})
    assert keyed == {"<숫자키>": {"qty": "int"}, "<날짜키>": "int", "status": "str"}, keyed   # ID·날짜 키 비노출
    other = DG.entry("GET", "https://wing.coupang.com/tenants/common/menu", 200, "xhr", "text/html", None, None)
    lines = DG.summarize([other, e, e])
    assert len(lines) == 2 and lines[0].startswith("★") and "settlement" in lines[0]    # 정산 주소 먼저·중복 1줄
    ok("값 7종 비노출·질의 이름만·요청/응답 구조·폼/텍스트 본문·정산 주소 우선 요약·중복 제거")


# ── 정산 파일·요청 기록·집계 (실측 머리글 그대로의 가상 데이터 — 실파일은 개인정보라 저장소에 넣지 않음) ──
WING_HDR = ["주문번호", "과세유형", "상품 ID", "상품명", "옵션 ID", "옵션명", "판매가", "판매수량", "환불수량", "판매액",
            "판매자 할인쿠폰(A+B)", "판매자 할인쿠폰(A.즉시할인)", "판매자 할인쿠폰(B.다운로드)", "판매수수료",
            "서비스이용율(%,VAT별도)", "서비스이용료소급분", "마이샵수수료할인", "정산금액", "구매자명", "결제완료일",
            "배송완료일", "구매확정일", "취소완료일", "구매확정(출고)유형", "정산예정일"]
RG_HDR = ["정산유형", "정산주기(종료일)", "세금계산서 발행월", "발생일(결제완료일)", "매출인식일", "주문ID", "거래유형",
          "카테고리ID", "카테고리명", "과세유형", "등록상품 ID", "옵션ID", "SKU ID", "등록상품명", "옵션명", "판매가(A)",
          "판매수량(B)", "판매액(A*B)", "쿠팡지원할인(C)", "매출금액(A*B-C)", "즉시할인쿠폰(D)", "다운로드쿠폰(E)",
          "판매자할인쿠폰(D+E)", "정산대상액", "판매수수료율(%,VAT별도)", "할인적용 판매수수료율(%,VAT별도)", "판매수수료",
          "판매수수료 VAT"]


def _wing_row(order, pid, name, oid, price, qty, coupon, fee, settle, buyer="홍길동", conf="2026-08-27",
              due="2026-09-18", sales=None):
    v = dict.fromkeys(WING_HDR, "")
    v.update({"주문번호": order, "상품 ID": pid, "상품명": name, "옵션 ID": oid, "옵션명": name and "옵션",
              "판매가": float(price), "판매수량": float(qty), "환불수량": 0.0,
              "판매액": float(price * qty if sales is None else sales),
              "판매자 할인쿠폰(A+B)": float(coupon), "판매자 할인쿠폰(A.즉시할인)": float(coupon),
              "판매자 할인쿠폰(B.다운로드)": 0.0, "판매수수료": float(fee), "서비스이용율(%,VAT별도)": "10.8",
              "마이샵수수료할인": 0.0, "정산금액": float(settle), "구매자명": buyer if name else "",
              "구매확정일": conf if name else "", "정산예정일": due})
    return [v[h] for h in WING_HDR]


def _wing_grid():
    return [WING_HDR,
            _wing_row("1001", "77", "보냉백", "95467404277", 12700, 1, 0, 1372, 11328),
            _wing_row("1001", "", "", "<기본배송료>", 0, 0, 0, 0, 0),
            _wing_row("1001", "", "", "<추가배송료>", 0, 0, 0, 0, 0),
            _wing_row("1002", "88", "압축포장기", "95425233537", 37900, 1, 20000, 1933, 15967),
            _wing_row("1003", "", "", "<기본배송료>", 0, 0, 0, 0, 6000, sales=6000),     # 실측 모양: 판매가·수량 0·금액만
            _wing_row("1004", "77", "보냉백", "95467404277", 12700, 2, 0, 2744, 99999)]   # 검산 위반 = 경고


def _rg_row(order, kind, pid, oid, name, price, qty, settle_target, fee, vat, rec="2026-08-05", cycle="2026-08-09"):
    v = dict.fromkeys(RG_HDR, "")
    v.update({"정산유형": "주정산", "정산주기(종료일)": cycle, "세금계산서 발행월": "2026-08", "매출인식일": rec,
              "주문ID": order, "거래유형": kind, "등록상품 ID": pid, "옵션ID": oid, "SKU ID": "5" + oid[-4:],
              "등록상품명": name, "옵션명": name, "판매가(A)": float(price), "판매수량(B)": float(qty),
              "판매액(A*B)": float(price * qty), "쿠팡지원할인(C)": 0.0, "매출금액(A*B-C)": float(price * qty),
              "즉시할인쿠폰(D)": 0.0, "다운로드쿠폰(E)": 0.0, "판매자할인쿠폰(D+E)": 0.0, "정산대상액": float(settle_target),
              "판매수수료율(%,VAT별도)": 10.8, "할인적용 판매수수료율(%,VAT별도)": 10.8, "판매수수료": float(fee),
              "판매수수료 VAT": float(vat)})
    return [v[h] for h in RG_HDR]


def _rg_grid(cycle="2026-08-09"):
    return [[None] * len(RG_HDR), RG_HDR,
            _rg_row("2001", "주문 정산", "77", "95222903297", "보냉백", 9310, 1, 8205, 1005, 100, cycle=cycle),
            _rg_row("2002", "주문 정산취소", "77", "95222903297", "보냉백", 9310, -1, -8205, -1005, -100, cycle=cycle)]


def p7_settle_files():
    print("[P7] 정산 파일 읽기 — 실측 머리글·0원 배송비 줄 제외·검산 경고·기간 대조·구매자명 삭제·파일 이름 규칙")
    from coupang_analytics import settlement_files as SF
    w = SF.parse_wing_detail(_wing_grid(), account="계정A", period_start=D("2026-08-24"), period_end=D("2026-08-30"))
    assert (len(w.rows), w.dropped_zero) == (4, 2), (len(w.rows), w.dropped_zero)
    assert [r.option_id for r in w.rows][2] == "<기본배송료>" and w.rows[2].settle == 6000          # 금액 있는 배송비 줄
    assert len(w.warnings) == 1 and "정산금액" in w.warnings[0], w.warnings                          # 1004 검산 위반
    assert not any(hasattr(r, "buyer") for r in w.rows) and "홍길동" not in str([vars(r) for r in w.rows])
    assert w.rows[0].option_id == "95467404277" and w.rows[1].coupon == 20000
    g = SF.parse_rg_fee(_rg_grid(), account="계정A", period_start=D("2026-08-03"), period_end=D("2026-08-09"))
    assert (len(g.rows), g.settle_total, g.rows[0].fee, g.warnings) == (2, 0, 1105, []), g
    expect(SF.SettlementParseError, lambda: SF.parse_rg_fee(_rg_grid("2026-08-16"), account="계정A",
                                                             period_start=D("2026-08-03"), period_end=D("2026-08-09")),
           "다른 기간 파일")
    bad = _wing_grid()
    bad[1][WING_HDR.index("판매액")] = "12,7OO"
    expect(SF.SettlementParseError, lambda: SF.parse_wing_detail(bad, account="a", period_start=D("2026-08-24"),
                                                                  period_end=D("2026-08-30")), "숫자 변환 실패")
    expect(SF.SettlementParseError, lambda: SF.parse_wing_detail([WING_HDR[:-3]], account="a",
                                                                  period_start=D("2026-08-24"),
                                                                  period_end=D("2026-08-30")), "머리글 누락")
    n = SF.settle_file_name("셀독 계정_A", D("2026-09-18"), SF.CH_WING, "주정산", "주문상세", D("2026-08-24"), D("2026-08-30"))
    assert n == "셀독-계정-A_20260918_윙_주정산_주문상세_20260824-20260830.xlsx", n
    meta = SF.parse_file_name(n)
    assert (meta["account"], meta["settle_date"], meta["channel"], meta["period_end"]) == (
        "셀독-계정-A", D("2026-09-18"), "윙", D("2026-08-30"))
    expect(ValueError, lambda: SF.parse_file_name("MSF_PAYMENT_REVENUE_DETAIL-2026-10-06.xlsx"), "규칙 밖 이름")
    import openpyxl
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "raw.xlsx"
        wb = openpyxl.Workbook()
        for row in _wing_grid():
            wb.active.append(row)
        wb.save(src)
        dst = Path(tmp) / n
        assert SF.scrub_pii(src, dst) == 1
        assert "구매자명" not in SF.read_grid(dst)[0] and "홍길동" not in str(SF.read_grid(dst))
        f = SF.load_settle_file(dst)
        assert (f.account, f.kind, f.report, len(f.rows)) == ("셀독-계정-A", "주정산", "주문상세", 4)
        empty = Path(tmp) / "empty.xlsx"
        openpyxl.Workbook().save(empty)
        expect(SF.SettlementParseError, lambda: SF.scrub_pii(empty, Path(tmp) / "x.xlsx"), "머리글 없는 파일 저장")
    ok("윙 0원 배송비 2줄 제외·금액 배송비 유지·검산 경고·구매자명 미보관/삭제·로켓그로스 취소·기간 대조·이름 왕복")


def p8_settle_jobs():
    print("[P8] 요청 기록 — 같은 기간 한 번·비용 리포트는 금액 있는 것만·하루 상한·미래 제외·재요청·목록 대조")
    from datetime import datetime
    from coupang_analytics import settlement_jobs as SJ
    ev = [SJ.SettleEvent("A", "로켓그로스", "주정산", D("2026-09-07"), D("2026-08-03"), D("2026-08-09")),
          SJ.SettleEvent("A", "로켓그로스", "주정산", D("2026-10-01"), D("2026-08-03"), D("2026-08-09"), ("보관비",)),
          SJ.SettleEvent("A", "윙", "주정산", D("2026-09-18"), D("2026-08-24"), D("2026-08-30")),
          SJ.SettleEvent("A", "윙", "최종액", D("2026-10-01"), D("2026-08-03"), D("2026-08-30")),
          SJ.SettleEvent("A", "윙", "주정산", D("2026-10-30"), D("2026-10-05"), D("2026-10-11")),   # 미래
          SJ.SettleEvent("B", "윙", "주정산", D("2026-09-18"), D("2026-08-24"), D("2026-08-30"))]
    jobs: list = []
    now = datetime(2026, 10, 6, 19, 0)
    pick = SJ.plan_requests(ev, jobs, today=D("2026-10-06"), now=now, per_account_cap=3)
    keys = sorted((j.account, j.channel, j.kind, j.report) for j in jobs)
    assert keys == [("A", "로켓그로스", "주정산", "보관비"), ("A", "로켓그로스", "주정산", "판매수수료"),
                    ("A", "윙", "최종액", "주문상세"),
                    ("B", "윙", "주정산", "주문상세")], keys                       # 70/30 1번·미래 제외·A 윙 주정산=월별로 대체
    assert sum(j.account == "A" for j in pick) == 3 and sum(j.account == "B" for j in pick) == 1
    assert pick[0].settle_date == "2026-09-07"                                     # 오래된 것부터
    for j in pick:
        SJ.mark_requested(j, now)
    assert SJ.plan_requests(ev, jobs, today=D("2026-10-07"), now=datetime(2026, 10, 7, 19), per_account_cap=3) == []
    later = SJ.plan_requests(ev, jobs, today=D("2026-10-10"), now=datetime(2026, 10, 10, 19), per_account_cap=9)
    assert len(later) == 4                                                         # 3일 지나도 미완료 → 재요청 대상
    capped = SJ.plan_requests(ev, [], today=D("2026-10-06"), now=now, per_account_cap=2)
    assert sum(j.account == "A" for j in capped) == 2                               # 계정당 하루 상한
    # 월별 파일이 나오기 전엔 주정산을 계획 → 나온 뒤엔 아직 요청 안 한 주정산은 '생략(월별로 대체)'
    evc = [SJ.SettleEvent("C", "윙", "주정산", D("2026-09-18"), D("2026-08-24"), D("2026-08-30")),
           SJ.SettleEvent("C", "윙", "주정산", D("2026-09-29"), D("2026-08-31"), D("2026-08-31")),   # 월 경계 분할 행
           SJ.SettleEvent("C", "윙", "최종액", D("2026-10-01"), D("2026-08-03"), D("2026-08-30"))]
    jc: list = []
    early = SJ.plan_requests(evc, jc, today=D("2026-09-20"), now=datetime(2026, 9, 20, 19), per_account_cap=5)
    assert [(j.kind, j.period_start) for j in early] == [("주정산", "2026-08-24")]         # 최종액은 아직 미도래
    after = SJ.plan_requests(evc, jc, today=D("2026-10-06"), now=now, per_account_cap=5)
    assert jc[0].status == SJ.ST_SKIPPED and "월별" in jc[0].note
    assert sorted((j.kind, j.period_start) for j in after) == [("주정산", "2026-08-31"), ("최종액", "2026-08-03")]
    done = SJ.Job("C", "윙", "주정산", "주문상세", "2026-08-24", "2026-08-30", "2026-09-18", status=SJ.ST_DONE)
    SJ.plan_requests(evc, [done], today=D("2026-10-06"), now=now, per_account_cap=5)
    assert done.status == SJ.ST_DONE                                               # 이미 받은 건 그대로
    j0 = next(j for j in jobs if j.kind == "최종액")
    j0.attempts = SJ.MAX_ATTEMPTS
    SJ.plan_requests(ev, jobs, today=D("2026-10-10"), now=datetime(2026, 10, 10, 19), per_account_cap=9)
    assert j0.status == SJ.ST_FAILED                                               # 무한 재시도 금지
    assert SJ.parse_condition("구매확정일:2026-08-24 - 2026-08-30") == (D("2026-08-24"), D("2026-08-30"))
    expect(ValueError, lambda: SJ.parse_condition("구매확정일:"), "기간 없는 조건")
    wing_b = next(j for j in jobs if j.account == "B")
    rg_fee = next(j for j in jobs if j.report == "판매수수료")
    t_b, t_rg = datetime.fromisoformat(wing_b.requested_at), datetime.fromisoformat(rg_fee.requested_at)
    rows = [SJ.DownloadRow("윙", t_b, "WAIT", period_start=D("2026-08-24"), period_end=D("2026-08-30")),
            SJ.DownloadRow("윙", t_b + timedelta(minutes=1), "FINISHED", period_start=D("2026-08-24"),
                           period_end=D("2026-08-30")),
            SJ.DownloadRow("로켓그로스", t_rg + timedelta(seconds=4), "완료", report="판매수수료")]
    pairs, notes = SJ.match_downloads(rows, [wing_b, rg_fee])
    assert [(j.account, j.report, r.status) for j, r in pairs] == [("B", "주문상세", "FINISHED"),
                                                                   ("A", "판매수수료", "완료")], pairs
    rows.append(SJ.DownloadRow("로켓그로스", t_rg + timedelta(seconds=9), "완료", report="판매수수료"))
    pairs, notes = SJ.match_downloads(rows, [rg_fee])
    assert pairs == [] and "구분 불가" in notes[0]                                    # 애매하면 받지 않음
    pairs, notes = SJ.match_downloads([rows[0]], [wing_b])
    assert pairs == [] and "아직 WAIT" in notes[0]
    # 실제 운영 모양: 로켓그로스 판매수수료를 여러 주 40초 간격으로 요청 → 각자 자기 목록 줄과 짝(겹치지 않음)
    t0 = datetime(2026, 10, 6, 20, 0, 0)
    w1 = SJ.Job("A", "로켓그로스", "주정산", "판매수수료", "2026-08-03", "2026-08-09", "2026-10-01",
                status=SJ.ST_REQUESTED, requested_at=t0.isoformat())
    w2 = SJ.Job("A", "로켓그로스", "주정산", "판매수수료", "2026-08-10", "2026-08-16", "2026-10-01",
                status=SJ.ST_REQUESTED, requested_at=(t0 + timedelta(seconds=40)).isoformat())
    lst = [SJ.DownloadRow("로켓그로스", t0 + timedelta(seconds=2), "완료", report="판매수수료", handle=1),
           SJ.DownloadRow("로켓그로스", t0 + timedelta(seconds=43), "완료", report="판매수수료", handle=0)]
    pairs, notes = SJ.match_downloads(lst, [w1, w2])
    assert [(j.period_start, r.handle) for j, r in pairs] == [("2026-08-03", 1), ("2026-08-10", 0)], (pairs, notes)
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "기록.json"
        SJ.save_jobs(p, jobs)
        assert [j.key for j in SJ.load_jobs(p)] == [j.key for j in jobs] and not (Path(tmp) / "기록.json.tmp").exists()
    ok("70/30 한 번·보관비만 추가·미래 제외·상한·오래된 순·만료 재요청·3회 실패·월별 나온 달 주정산 생략·윙 기간/RG 시각 대조·애매=보류·기록 왕복")


def p9_settle_stats():
    print("[P9] 병합·집계 — 최종액 파일 제외·중복 파일/줄 1회·배송비 묶음·월=매출인식일·계약자 정산금액")
    from coupang_analytics import settlement_files as SF
    from coupang_analytics import settlement_stats as ST
    w = SF.parse_wing_detail(_wing_grid(), account="A", period_start=D("2026-08-24"), period_end=D("2026-08-30"))
    w.kind, w.settle_date = "주정산", D("2026-09-18")
    wfinal = SF.parse_wing_detail([*_wing_grid(), _wing_row("1009", "77", "보냉백", "95467404277", 12700, 1, 0, 1372,
                                                            11328, conf="2026-08-12", due="2026-08-31")],
                                  account="A", period_start=D("2026-08-03"), period_end=D("2026-08-30"))
    wfinal.kind = "최종액"
    g = SF.parse_rg_fee(_rg_grid(), account="A", period_start=D("2026-08-03"), period_end=D("2026-08-09"))
    g.kind, g.report = "주정산", "판매수수료"
    res = ST.aggregate([w, wfinal, g, g])
    by = {(p.month, p.product_id): p for p in res.products}
    assert by[("2026-08", "77")].wing_settle == 11328 + 99999 + 11328 and by[("2026-08", "77")].rg_settle == 0
    assert by[("2026-08", "77")].rg_qty == 0 and by[("2026-08", "77")].product_name == "보냉백"
    assert by[("2026-08", ST.SHIPPING_KEY)].wing_settle == 6000                      # 날짜 없는 배송비 = 기간 끝 달
    assert res.account_totals() == {"A": 11328 + 15967 + 6000 + 99999 + 11328}       # 최종액은 주정산 없는 주(1009)만
    assert any("주정산 파일이 없는 주의 줄 1건" in x for x in res.warnings), res.warnings
    assert any("두 번" in x for x in res.warnings) and any("날짜 없는" in x for x in res.warnings)
    assert not any("겹친 같은 줄" in x for x in res.warnings)                        # 주정산 있는 주는 최종액서 제외
    lines = {(f.kind, f.channel, label): amt for f, label, amt in ST.payout_lines([w, wfinal, g])}
    assert lines[("최종액", "윙", "주정산 70%(정산예정 2026-08-31·월별 파일에서 계산)")] == 7930   # 주정산 없는 주만
    assert not any("2026-09-18·월별" in k[2] for k in lines)                           # 주정산 있는 주는 중복 계산 안 함
    assert lines[("주정산", "윙", "주정산 70%")] == 93306                               # 133,294×0.7
    assert lines[("최종액", "윙", "최종액 30%")] == 144622 - (93306 + 7930)            # 주별(09-18·08-31) 70% 뺀 나머지
    assert lines[("주정산", "로켓그로스", "주정산 70%")] == 0 and ("주정산", "로켓그로스", "2차 30%") in lines
    assert ST.contractor_amount(10_000_000, 3_764_453) == 6_235_547
    expect(ValueError, lambda: ST.contractor_amount(None, 1), "계약금액 미입력")
    expect(TypeError, lambda: ST.contractor_amount(1.5, 1), "정수 아닌 계약금액")
    import openpyxl
    with tempfile.TemporaryDirectory() as tmp:
        out = ST.write_stats(Path(tmp) / "집계.xlsx", res, {"A": 200_000}, files=[w, wfinal, g])
        wb = openpyxl.load_workbook(out)
        assert wb.sheetnames == ["상품별 월별", "계정별 월별", "계약자 정산", "지급액 검산", "경고"]
        assert [c.value for c in wb["계약자 정산"][2]] == ["A", 144622, 200000, 55378]
        assert wb["지급액 검산"].max_row == 1 + 5                 # 윙 주정산·최종액 30%·월별서 계산한 08-31 주 70% + RG 2
        out2 = ST.write_stats(Path(tmp) / "집계2.xlsx", res)
        assert [c.value for c in openpyxl.load_workbook(out2)["계약자 정산"][2]][2:] == [None, None]   # 미입력=빈칸
    ok("최종액=주정산 없는 주만·중복 파일 1회·배송비 묶음·월 귀속·지급액 검산(윙 최종액 30% 주별)·계약자 정산금액·엑셀 5시트")


def p10_wing_ui_parse():
    print("[P10] 정산 화면 글자 → 정산 일정·다운로드 목록(스크린샷 모양 가상 화면·라이브 미호출)")
    from datetime import datetime
    from coupang_analytics import settlement_wing_ui as UI
    K = UI.ROW_KEY
    wing = [{"정산일": "2026-10-01", "정산유형": "최종액정산", "지급비율": "30%", "구매확정기간": "2026-08-03 ~ 2026-08-30",
             "정산상태": "정산확정", "최종지급액": "124,513", K: 0},
            {"정산일": "2026-09-18", "정산유형": "주정산", "지급비율": "70%", "구매확정기간": "2026-08-24 ~ 2026-08-30",
             "정산상태": "정산확정", "최종지급액": "236,439", K: 1},
            {"정산일": "2026-10-07", "정산유형": "주정산", "지급비율": "70%", "구매확정기간": "2026-09-07 ~ 2026-09-13",
             "정산상태": "정산예정", "최종지급액": "7,217", K: 3}]                      # 예정 = 아직 받지 않음
    ev = UI.parse_wing_rows(wing, "계정A")
    assert [(e.kind, e.settle_date, e.period_start, e.period_end, ri) for e, ri in ev] == [
        ("최종액", D("2026-10-01"), D("2026-08-03"), D("2026-08-30"), 0),
        ("주정산", D("2026-09-18"), D("2026-08-24"), D("2026-08-30"), 1)], ev
    rg = [{"정산일": "2026-09-07", "정산유형": "주별", "지급비율": "30", "매출인식일": "2026-07-27~2026-07-31", K: 0},
          {"정산일": "2026-10-01", "정산유형": "주별", "지급비율": "30", "매출인식일": "2026-08-03~2026-08-09", K: 2}]
    rev = UI.parse_rg_rows(rg, "계정A")
    assert [(e.channel, e.kind, e.period_start, ri) for e, ri in rev] == [
        ("로켓그로스", "주정산", D("2026-07-27"), 0), ("로켓그로스", "주정산", D("2026-08-03"), 2)]
    expect(UI.UiChangedError, lambda: UI.parse_wing_rows([{**wing[0], "정산유형": "특별정산"}], "a"), "모르는 유형")
    expect(UI.UiChangedError, lambda: UI.parse_rg_rows([{**rg[0], "매출인식일": "7월 4주"}], "a"), "기간 글자")
    assert UI.report_key("리포트 : 판매수수료 리포트") == "판매수수료" and UI.report_key("입출고/배송비 리포트") == "입출고/배송비"
    expect(UI.UiChangedError, lambda: UI.report_key("리포트 : 새 리포트"), "모르는 리포트")
    wl = UI.parse_list_rows([{"요청일시": "2026-10-06 11:43:41", "메뉴명": "[중개] 정산현황 주문 상세 내역",
                              "검색조건": "구매확정일:2026-08-24 - 2026-08-30", "상태": "WAIT", K: 0},
                             {"요청일시": "2025-02-19 05:07:42", "메뉴명": "[중개] 부가세 신고 내역 상세",
                              "검색조건": "구매확정일:2025-01-01 - 2025-01-31", "상태": "FINISHED", K: 2}], "윙")
    assert [(r.requested_at, r.status, r.period_start, r.period_end, r.handle) for r in wl] == [
        (datetime(2026, 10, 6, 11, 43, 41), "WAIT", D("2026-08-24"), D("2026-08-30"), 0)]   # 부가세 메뉴 무시
    rl = UI.parse_list_rows([{"요청일시": "2026-10-06 11:55:15", "상태": "진행중", "리포트": "리포트 : 판매수수료 리포트",
                              K: 4}], "로켓그로스")
    assert (rl[0].report, rl[0].status, rl[0].handle) == ("판매수수료", "진행중", 4)
    assert UI.month_windows(D("2026-01-15"), D("2026-03-02")) == [
        (D("2026-01-15"), D("2026-01-31")), (D("2026-02-01"), D("2026-02-28")), (D("2026-03-01"), D("2026-03-02"))]

    class FakePage:
        def __init__(self, tables):
            self.tables = tables

        def evaluate(self, js, arg=None):
            if arg is None:
                return [" ".join(t["ths"]) for t in self.tables]
            return [t for t in self.tables if all(m in t["ths"] for m in arg)]
    tbl = {"ti": 3, "ths": list(UI.WING_HEADERS) + ["주문상세내역"],
           "rows": [["2026-09-18", "주정산", "70%", "2026-08-24 ~ 2026-08-30", "정산확정", "236,439", "미리보기"],
                    ["총 최종지급액", "236,439"]]}                                         # 합계 줄 = 제외
    ti, rows = UI.read_table(FakePage([tbl]), UI.WING_HEADERS)
    assert ti == 3 and len(rows) == 1 and rows[0]["구매확정기간"].startswith("2026-08-24") and rows[0][K] == 0
    expect(UI.UiChangedError, lambda: UI.read_table(FakePage([]), UI.WING_HEADERS), "표 없음")
    expect(UI.UiChangedError, lambda: UI.read_table(FakePage([tbl, tbl]), UI.WING_HEADERS), "표 둘")
    ok("정산확정만·유형/기간 변환·화면 줄 번호 유지·리포트 이름·목록(부가세 메뉴 무시)·달 구간·표 0/2개=오류·합계 줄 제외")


def p11_runlog():
    print("[P11] 실행 기록 — 처리기록 CSV(실행·누적)·로그인/차단/실패 기록·오류 전체 추적·요약")
    import csv as _csv
    from datetime import datetime
    from coupang_analytics import settlement_runlog as RLG
    with tempfile.TemporaryDirectory() as tmp:
        out: list = []
        lg = RLG.RunLog(tmp, now=datetime(2026, 10, 6, 21, 0, 0), echo=out.append)
        lg.record("A-1", "로그인", RLG.OK, "success: 로그인 완료")
        lg.record("A-1", "요청", RLG.OK, "다운로드 요청함", channel="윙", kind="주정산·주문상세", settle_date="2026-01-12",
                  period="2025-12-29~2026-01-04")
        lg.record("B-2", "차단감지", RLG.BLOCK, "차단 화면 — https://wing.coupang.com/x")
        try:
            raise ValueError("표 머리글 없음")
        except ValueError as exc:
            lg.error("B-2", "조회", exc)
        lg2 = RLG.RunLog(tmp, now=datetime(2026, 10, 7, 21, 0, 0), echo=out.append)
        lg2.record("A-1", "받기", RLG.WAIT, "아직 WAIT", channel="윙")
        rows = list(_csv.DictReader(open(lg.csv, encoding="utf-8-sig")))
        assert [r["결과"] for r in rows] == ["정상", "정상", "차단", "실패"] and rows[1]["정산일"] == "2026-01-12"
        total = list(_csv.DictReader(open(lg.total, encoding="utf-8-sig")))
        assert len(total) == 5 and {r["실행ID"] for r in total} == {"261006_210000", "261007_210000"}   # 누적
        tb = lg.errors.read_text(encoding="utf-8")
        assert "Traceback" in tb and "ValueError: 표 머리글 없음" in tb and "B-2 · 조회" in tb
        assert "⛔ [차단감지] B-2" in lg.text.read_text(encoding="utf-8")
        summ = lg.summary()
        assert "[요약] A-1: 정상 2" in summ and "[요약] B-2: 실패 1 · 차단 1" in summ, summ
        assert "[비정상] 조회 실패: 1건" in summ and "[비정상] 차단감지 차단: 1건" in summ
    ok("실행·누적 CSV(엑셀용)·정산일 칸·차단/로그인 기록·오류 전체 추적·계정별/단계별 요약")


def main():
    g1_payout_dates()
    g2_amounts()
    g3_invariants()
    p1_holidays()
    p2_payout_rules()
    p3_amount_rules()
    p4_parse()
    p5_holiday_source()
    p6_diag_no_values()
    p7_settle_files()
    p8_settle_jobs()
    p9_settle_stats()
    p10_wing_ui_parse()
    p11_runlog()
    print("정산 계산 모듈 오프라인 검증 통과(골든 payout 12·amount 2·불변식 4행/3식 100%)")


if __name__ == "__main__":
    main()
