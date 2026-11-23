"""정산 다운로드·검증 런타임 오프라인 검증 — 주소 응답 해석·실행 기록·감시 판단·계정 파일·상태 화면·차단/일시 오류
구분·검증 자료 수집·검증 시트·지급일 대조·계좌 입금·정산캘린더. verify_settlement_offline.py(계산·파싱 골든)에서 분리.

로그인·쿠팡 주소·공휴일 API 호출 없음(결정적·가짜 응답). 실패 시 AssertionError → exit 1. run_checks 게이트.

    python tools/verify_settlement_runtime_offline.py
"""
from __future__ import annotations

import sys
import tempfile
from contextlib import contextmanager
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

D = date.fromisoformat
# 광고센터 일별 광고비 정산내역 화면이 실제로 보낸 질의(2026-11-17 · 공백 한 칸으로 줄임 · 근거 = 통제 세션 메모
# T82_getDailySettlement_화면질의_2026-11-17.md) — settlement_ads._DAILY 칸 이름은 여기 있는 것만 쓴다(짐작 금지).
AD_SCREEN_QUERY = (
    "mutation ($startDate: Int!, $endDate: Int!, $settlementDomain: SettlementDomain!, $reportType: SettlementReportType) { "
    "getDailySettlement( startDate: $startDate endDate: $endDate settlementDomain: $settlementDomain reportType: $reportType ) "
    "{ ...DailySettlement __typename } } fragment DailySettlement on DailySettlement { summary { total { vendorName "
    "deliveredAdcost deliveredAdcostAfterCap promotionAdjustment billableAdjustment billableAmount totalFinalAmount __typename } "
    "nonRod { domain deliveredAdcost deliveredAdcostAfterCap billableAmount promotionAdjustment billableAdjustment "
    "deliveredAdcostAdj deliveredAdcostAfterAdj vat totalFinalAmount __typename } rod { domain deliveredAdcost "
    "deliveredAdcostAfterCap billableAmount promotionAdjustment billableAdjustment deliveredAdcostAdj deliveredAdcostAfterAdj "
    "vat totalFinalAmount __typename } rocketGrowth { domain deliveredAdcost deliveredAdcostAfterCap billableAmount "
    "promotionAdjustment billableAdjustment deliveredAdcostAdj deliveredAdcostAfterAdj vat totalFinalAmount __typename } "
    "__typename } items { date type settlementDomain campaignId campaignName adType goalType deliveredAdcost "
    "deliveredAdcostAdj deliveredAdcostAfterAdj budgetAmount budgetType priorSpend deliveredAdcostAfterCap billableAmount "
    "promotionAdjustment billableAdjustment cumulativeMonthlyDeliveredAdcost monthlyCap priorMonthRollover createdBy "
    "ownership __typename } subtotals { nonRod { date domain deliveredAdcost deliveredAdcostAfterCap deliveredAdcostAdj "
    "deliveredAdcostAfterAdj billableAmount promotionAdjustment billableAdjustment vat totalFinalAmount taxCode __typename } "
    "rod { date domain deliveredAdcost deliveredAdcostAfterCap deliveredAdcostAdj deliveredAdcostAfterAdj billableAmount "
    "promotionAdjustment billableAdjustment vat totalFinalAmount taxCode __typename } rocketGrowth { date domain "
    "deliveredAdcost deliveredAdcostAfterCap deliveredAdcostAdj deliveredAdcostAfterAdj billableAmount promotionAdjustment "
    "billableAdjustment vat totalFinalAmount taxCode __typename } __typename } dailyInvoiceAgencyCampaignAdjustments { "
    "adjustmentType adjustmentAmount invoiceAgencyId campaignId __typename } __typename }")


def ok(msg):
    print(f"  ✔ {msg}")


def expect(exc, fn, what):
    try:
        fn()
    except exc:
        return
    raise AssertionError(f"{what} — {exc.__name__} 안 남")


def p10_wing_api_parse():
    print("[P10] 정산 주소 응답 → 정산 일정·요청 본문·다운로드 목록(실측 응답 모양·값은 가상·라이브 미호출)")
    from datetime import datetime
    from coupang_analytics import settlement_jobs as SJ
    from coupang_analytics import settlement_wing_api as API
    wresp = {"paymentReports": [
        {"payDate": "2026-01-02", "transactionCycleCode": "R", "recognitionFrom": "2025-11-03",
         "recognitionTo": "2025-11-30", "paymentStatus": "DONE", "ratio": 30},
        {"payDate": "2026-01-23", "transactionCycleCode": "W", "recognitionFrom": "2026-01-01",
         "recognitionTo": "2026-01-04", "paymentStatus": "DONE", "ratio": 70}], "totalAmount": 0}
    ev = API.wing_events(wresp, "계정A")
    assert [(e.kind, e.settle_date, e.period_start, e.period_end) for e in ev] == [
        ("최종액", D("2026-01-02"), D("2025-11-03"), D("2025-11-30")),
        ("주정산", D("2026-01-23"), D("2026-01-01"), D("2026-01-04"))], ev
    expect(API.SiteChangedError, lambda: API.wing_events(
        {"paymentReports": [{**wresp["paymentReports"][0], "transactionCycleCode": "X"}]}, "a"), "모르는 주기 코드")
    # D-075(실측 2026-10-16 노바네스트 화면): 'M' = 월정산 — 같은 '엑셀 다운로드 요청'(revenue-detail)·구매확정일 그 달 전체.
    mresp = {"paymentReports": [wresp["paymentReports"][1], {**wresp["paymentReports"][0], "transactionCycleCode": "M",
                                                            "payDate": "2026-09-21", "recognitionFrom": "2026-08-01",
                                                            "recognitionTo": "2026-08-31"}]}
    assert [(e.kind, e.period_start, e.period_end) for e in API.wing_events(mresp, "a")] == [
        ("주정산", D("2026-01-01"), D("2026-01-04")), ("월정산", D("2026-08-01"), D("2026-08-31"))], "M = 월정산 일정"
    assert API.unsupported_cycles(mresp) == [], "월정산은 더 이상 '확인 필요' 아님"
    expect(API.SiteChangedError, lambda: API.wing_events({"reports": []}, "a"), "응답 칸 없음")
    rresp = {"settlementStatusReports": [
        {"settlementDate": "2026-09-06T15:00:00.000Z", "settlementPeriodStartDate": "2026-07-26T15:00:00.000Z",
         "settlementPeriodEndDate": "2026-07-30T15:00:00.000Z", "settlementRatio": 30, "settlementCycle": "WEEKLY",
         "settlementGroupKey": "V1-2026-07-27-2026-07-31", "finalSettlementAmount": 1}]}
    rev = API.rg_events(rresp, "계정A")
    assert [(e.kind, e.settle_date, e.period_start, e.period_end, e.ref) for e in rev] == [
        ("최종액", D("2026-09-07"), D("2026-07-27"), D("2026-07-31"), "V1-2026-07-27-2026-07-31")], rev   # UTC→한국 날짜
    expect(API.SiteChangedError, lambda: API.rg_events({"settlementStatusReports": [
        {**rresp["settlementStatusReports"][0], "settlementCycle": "DAILY"}]}, "a"), "모르는 RG 주기")
    assert API.rg_events_body(D("2026-01-01"), D("2026-01-31")) == {
        "startDate": "2025-12-31T15:00:00.000Z", "endDate": "2026-01-31T15:00:00.000Z", "searchDateType": "PAYMENT"}
    assert API.wing_events_body(D("2026-01-01"), D("2026-01-31"))["fromDate"] == "2026-01-01"
    jobs: list = []
    picked = SJ.plan_requests(ev + rev, jobs, today=D("2026-10-06"), now=datetime(2026, 10, 6, 15), per_account_cap=9)
    rj = next(j for j in picked if j.channel == "로켓그로스")
    assert rj.ref == "V1-2026-07-27-2026-07-31"                                     # 일정의 키가 요청까지 전달
    assert API.rg_request_body(rj, 1791000000000) == {"sellerReportType": "CATEGORY_TR", "requestTime": "1791000000000",
                                                      "settlementGroupKeys": [rj.ref], "locale": "ko"}
    wj = next(j for j in picked if j.channel == "윙" and j.kind == "주정산")
    assert API.wing_request_body(wj) == {"excelType": "MSF_PAYMENT_REVENUE_DETAIL",
                                         "recognitionDateRange": {"start": "2026-01-01", "end": "2026-01-04"},
                                         "searchDateType": "CONFIRM_DATE",
                                         "searchDateRange": {"start": "2026-01-01", "end": "2026-01-04"}}
    expect(API.SiteChangedError, lambda: API.rg_request_body(SJ.Job("a", "로켓그로스", "주정산", "판매수수료", "x", "y", "z"),
                                                              1), "묶음 키 없음")
    expect(API.SiteChangedError, lambda: API.rg_request_body(SJ.Job("a", "로켓그로스", "주정산", "새 비용", "x", "y", "z",
                                                                     ref="k"), 1), "코드 미확인 리포트")
    assert API.wing_request_id({"success": True, "reason": "OK", "data": 134}) == "134"
    expect(API.SiteChangedError, lambda: API.wing_request_id({"success": False, "reason": "LIMIT", "data": None}), "거절")
    assert API.rg_request_id({"requestId": "abc", "duplicateRequest": False, "remainingTime": 0}) == "abc"
    expect(API.RequestThrottled, lambda: API.rg_request_id({"requestId": "", "duplicateRequest": True,
                                                            "remainingTime": 30}), "대기시간 응답")
    # 비용 리포트: 그 주 금액 있는 종류만(입출고+배송 → 1종으로 합침)·0원 제외·미확인 비용은 알림
    det = {"totalStorageFeeDeductionAmount": 201287, "totalFulfillmentFeeDeductionAmount": 843508,
           "totalWarehousingFeeDeductionAmount": 867526, "totalBarcodeLabelingFeeDeductionAmount": 0,
           "totalCfsInventoryCompensationAmount": 119770, "totalAdSalesDeductionAmount": 1003081,
           "totalContainerUnloadingFeeDeductionAmount": 5000, "totalPostPurchaseDeductionAmount": 2220,
           "totalBusinessInsightsDeductionAmount": 99000, "totalSubscriptionFeeDeductionAmount": 99000}
    # 리뷰 이벤트(PPIR) 금액 → 리뷰 이벤트 비용 리포트(D-171·N2) · BI·구독료는 리포트 없음(지급 내역 JSON 칸으로만)
    assert API.cost_reports(det) == ("리뷰 이벤트 비용", "보관비", "입출고/배송비", "재고 손실 보상")
    r70 = {**rresp["settlementStatusReports"][0], "settlementRatio": 70, "settlementStatusReportDetail": det}
    ev70 = API.rg_events({"settlementStatusReports": [r70]}, "계정A")[0]
    assert ev70.reports == ("리뷰 이벤트 비용", "보관비", "입출고/배송비", "재고 손실 보상") and SJ.reports_for(ev70)[0] == "판매수수료"
    assert API.unmapped_costs({"settlementStatusReports": [r70]}) == [
        "V1-2026-07-27-2026-07-31: totalContainerUnloadingFeeDeductionAmount=5000"]
    cj = SJ.Job("a", "로켓그로스", "주정산", "입출고/배송비", "x", "y", "z", ref="k")
    assert API.rg_request_body(cj, 1)["sellerReportType"] == "WAREHOUSING_SHIPPING"
    pj = SJ.Job("a", "로켓그로스", "주정산", "리뷰 이벤트 비용", "x", "y", "z", ref="k")
    assert API.rg_request_body(pj, 1)["sellerReportType"] == "PPIR"
    am_bi = API.amount_rows({"settlementStatusReports": [r70]}, "로켓그로스")[0]
    assert am_bi["totalBusinessInsightsDeductionAmount"] == 99000 and am_bi["totalPostPurchaseDeductionAmount"] == 2220,         "리포트 없는 공제 칸도 지급 내역에 저장(N2)"
    am = API.amount_rows({"paymentReports": [{**wresp["paymentReports"][1], "finalPaidAmount": 19664,
                                              "bankAccountInfo": {"bank": "가림"}, "isAdditionalPayment": False,
                                              "detail": {"paidAmount": 19664, "isActualPayment": True,
                                                         "payableSummarySeqList": [1, 2],
                                                         "deductionDetail": [{"serviceFeeAmount": 55000, "serviceType": "CLR_3SF",
                                                                              "serviceTypeNameKR": "판매자서비스이용료",
                                                                              "serviceTypeNameEN": "SELLER SERVICE FEE"}]}}]}, "윙")
    assert am == [{"정산일": "2026-01-23", "기간 시작": "2026-01-01", "기간 끝": "2026-01-04", "지급비율": 70,
                   "최종지급액": 19664, "지급상태": "DONE", "실지급": True,
                   "차감 사유": [{"사유": "판매자서비스이용료", "금액": 55000}], "paidAmount": 19664}], am   # 계좌·내부번호 제외
    r70x = {**r70, "settlementStatusReportDetail": {**det, "pastDeductedCfsFeeDetails": [{"paymentRatio": 30, "pastDeductedCfsFeeAmount": 24959.0}],
                                                    "adSalesOffsetYearMonthBreakdown": {"2026-08": 59266.0}, "salesAdjustmentDetails": []}}
    ar = API.amount_rows({"settlementStatusReports": [r70x]}, "로켓그로스")[0]
    assert ar["정산일"] == "2026-09-07" and ar["totalStorageFeeDeductionAmount"] == 201287
    assert ar["pastDeductedCfsFeeDetails"] == [{"paymentRatio": 30, "pastDeductedCfsFeeAmount": 24959.0}]   # 상계 상세 보존
    assert ar["adSalesOffsetYearMonthBreakdown"] == {"2026-08": 59266.0} and "salesAdjustmentDetails" not in ar   # 빈 목록은 생략
    wl = API.wing_list_rows([
        {"id": 1, "excelType": "MSF_PAYMENT_REVENUE_DETAIL", "status": "FINISHED", "startedAt": "2026-10-06 14:49:59",
         "downloadUrl": "https://x/dl?id=1", "jsonItems": '[{"key":"구매확정일", "value":"2026-09-01 - 2026-09-06", "view":true}]'},
        {"id": 2, "excelType": "MSF_VAT_DETAIL", "status": "FINISHED", "startedAt": "2025-02-19 05:07:42",
         "downloadUrl": "https://x/dl?id=2", "jsonItems": '[{"key":"구매확정일", "value":"2025-01-01 - 2025-01-31"}]'}])
    assert [(r.requested_at, r.status, r.period_start, r.period_end, r.handle) for r in wl] == [
        (datetime(2026, 10, 6, 14, 49, 59), "FINISHED", D("2026-09-01"), D("2026-09-06"), "https://x/dl?id=1")]
    rl = API.rg_list_rows([{"requestId": "abc", "requestTime": "1791000000000", "downloadStatus": "COMPLETED",
                            "sellerReportType": "CATEGORY_TR", "recognitionDateFrom": None}])
    assert (rl[0].report, rl[0].status, rl[0].req_id, rl[0].handle) == ("판매수수료", "COMPLETED", "abc", "1791000000000")
    assert API.rg_list_body(datetime(2026, 10, 6, 0, 0), datetime(2026, 10, 6, 0, 0, 1)) == {
        "requestTimeFrom": str(int(datetime(2026, 10, 6).timestamp() * 1000)),
        "requestTimeTo": str(int(datetime(2026, 10, 6).timestamp() * 1000) + 1000)}
    assert API.month_windows(D("2026-01-15"), D("2026-03-02")) == [
        (D("2026-01-15"), D("2026-01-31")), (D("2026-02-01"), D("2026-02-28")), (D("2026-03-01"), D("2026-03-02"))]

    class FakePage:
        def __init__(self, status, text):
            self.r = {"status": status, "ctype": "x", "text": text}

        def evaluate(self, js, arg=None):
            return self.r
    assert API.call(FakePage(200, '{"a":1}'), "GET", "/p") == {"a": 1}
    expect(API.ApiBlocked, lambda: API.call(FakePage(403, "x"), "GET", "/p"), "403=차단")
    expect(API.ApiBlocked, lambda: API.call(FakePage(200, "<html>Access Denied"), "GET", "/p"), "HTML=차단")
    for st in (500, 502, 503, 504):                     # D-010: 500 도 서버 일시 오류(실측 10/09 지급내역 500 HTML·빈 본문)                                                      # 실측 2026-10-08: 504 HTML = 서버 일시 오류
        expect(API.ServerBusy, lambda st=st: API.call(FakePage(st, "<html><title>%d Gateway Time-out</title>" % st), "GET", "/p"),
               f"{st}=일시 오류(차단 아님)")
        assert not issubclass(API.ServerBusy, API.ApiBlocked)
    expect(API.SiteChangedError, lambda: API.call(FakePage(400, "{}"), "GET", "/p"), "400=중단")
    ok("윙/RG 일정(UTC→한국 날짜·묶음키)·요청 본문·요청번호·목록(부가세 메뉴 무시)·달 구간·403/HTML=차단·500/502~504=일시오류·M=건너뜀")


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
            lg.error("B-2", "조회", exc, channel="윙", settle_date="2026-01-13")
        lg2 = RLG.RunLog(tmp, now=datetime(2026, 10, 7, 21, 0, 0), echo=out.append)
        lg2.record("A-1", "받기", RLG.WAIT, "아직 WAIT", channel="윙")
        rows = list(_csv.DictReader(open(lg.csv, encoding="utf-8-sig")))
        assert [r["결과"] for r in rows] == ["정상", "정상", "차단", "실패"] and rows[1]["정산일"] == "2026-01-12"
        assert (rows[3]["채널"], rows[3]["정산일"]) == ("윙", "2026-01-13")                    # 실패 줄에도 정산일
        total = list(_csv.DictReader(open(lg.total, encoding="utf-8-sig")))
        assert len(total) == 5 and {r["실행ID"] for r in total} == {"261006_210000", "261007_210000"}   # 누적
        tb = lg.errors.read_text(encoding="utf-8")
        assert "Traceback" in tb and "ValueError: 표 머리글 없음" in tb and "B-2 · 조회" in tb
        assert "⛔ [차단감지] B-2" in lg.text.read_text(encoding="utf-8")
        summ = lg.summary()
        assert "[요약] A-1: 정상 2" in summ and "[요약] B-2: 실패 1 · 차단 1" in summ, summ
        assert "[비정상] 조회 실패: 1건" in summ and "[비정상] 차단감지 차단: 1건" in summ
        # heartbeat: 창 없는 자동 실행 모니터링 — 고정 경로(_현재상태.txt)에 **덮어쓰기**(append 아님)·개인정보 없음.
        lg.heartbeat("대기중", "앱 ①판매수집 완료 기다림")
        st = lg.status
        assert st.name == "_현재상태.txt" and st.parent == lg.dir                    # 로그 폴더 안 고정 파일
        txt1 = st.read_text(encoding="utf-8")
        assert "상태: 대기중" in txt1 and "앱 ①판매수집 완료 기다림" in txt1
        assert f"실행ID: {lg.run_id}" in txt1 and f"상세 로그: {lg.text.name}" in txt1
        lg.heartbeat("작동중", "요청 누르는 중", extra=("추가줄",))
        txt2 = st.read_text(encoding="utf-8")
        assert "상태: 작동중" in txt2 and "추가줄" in txt2
        assert "대기중" not in txt2 and txt2.count("상태:") == 1                      # 누적 아님 — 최신 1건만
        assert not st.with_name(st.name + ".tmp").exists()                           # 임시파일은 남기지 않음(os.replace)
        lg2.heartbeat("완료", "명령 run")                                             # 다른 RunLog 도 같은 고정 파일을 공유
        assert lg2.status == st and "상태: 완료" in st.read_text(encoding="utf-8")
    ok("실행·누적 CSV(엑셀용)·정산일 칸·차단/로그인 기록·오류 전체 추적·계정별/단계별 요약·상태 파일 덮어쓰기 모니터링")


def p12_watch_decide():
    print("[P12] 정산 실행 판단(D-010) — 다 받으면 종료·중단/진전없음 종료·같은 ①완료 재실행 안 함·① 중 정지")
    import os as _os
    from datetime import datetime
    from coupang_analytics import settlement_watch as W
    T = datetime
    # 한 바퀴 뒤 판단: 중단 > 새로 한 일 있음(곧 다음 바퀴) > 대기 남음(잠시 뒤·진전 없으면 미완료 종료) > 완료
    assert W.plan_after_pass(True, 5, 3, 1)[0] == "later"                          # 연속 실패/차단 = 이번 바퀴만 멈춤(D-031)
    assert W.plan_after_pass(False, 4, 9, 0)[0] == "again"                          # 받는 중(소급) = 곧 다음 바퀴
    assert W.plan_after_pass(False, 0, 2, 0)[0] == "later"                          # 파일 생성 대기 = 잠시 뒤(24:00 까지 · D-373 ②)
    assert W.plan_after_pass(False, 0, 0, 1)[0] == "later"                          # 다시 시도할 오류 항목 = 다음 바퀴(D-373)
    assert not hasattr(W, "MAX_IDLE_PASSES") and "giveup" not in W.RESULT        # 진전 없음 '미완료' 종료 없음(D-373 ②)
    a, r = W.plan_after_pass(False, 0, 0, 0)
    assert a == "done" and "모든 정산 파일 다운로드 완료" in r                        # 다 받음 = 기록 후 정상 종료
    # 완료 기록 키 = ①완료 시각(앱이 띄움) / 없으면 오늘(수동) — 같은 키 '완료'면 다시 안 돎
    mk = {"stage": "sales", "at": T(2026, 10, 9, 19, 54, 35)}
    assert W.sales_key(mk, T(2026, 10, 9, 20, 0)) == "2026-10-09T19:54:35"
    assert W.sales_key(None, T(2026, 10, 9, 20, 0)) == "수동:2026-10-09"
    with tempfile.TemporaryDirectory() as tmp:
        dp = Path(tmp) / "_완료.json"
        assert W.read_done(dp) is None
        W.write_done(dp, "k1", "stop", "중단 사유")
        assert not W.already_done(W.read_done(dp), "k1")                            # 중단 = 다시 돌아야
        W.write_done(dp, "k1", "done", "완료")
        assert W.already_done(W.read_done(dp), "k1") and not W.already_done(W.read_done(dp), "k2")   # 새 ①완료 = 다시
        dp.write_text("{깨짐", encoding="utf-8")
        assert W.read_done(dp) is None                                              # 손상 = 기록 없음(한 바퀴 더)
    # sales_in_progress: _진행중.json 수정 시각(신선=진행 중)
    with tempfile.TemporaryDirectory() as tmp:
        prog = Path(tmp) / "진행중.json"
        assert W.sales_in_progress(prog)[0] is False                                # 파일 없음
        prog.write_text("{}", encoding="utf-8")
        _os.utime(prog, (T(2026, 10, 7, 12, 0, 0).timestamp(),) * 2)
        assert W.sales_in_progress(prog, now=T(2026, 10, 7, 12, 10))[0] is True      # 10분 전 = 진행 중
        assert W.sales_in_progress(prog, now=T(2026, 10, 7, 12, 40))[0] is False     # 40분 전 = 아님(①끝남)
        # read_marker 왕복
        mp = Path(tmp) / "단계.json"
        assert W.read_marker(mp)[0] is None and "없음" in W.read_marker(mp)[1]
        mp.write_text('{"date": "2026-10-07", "stage": "sales", "at": "2026-10-07T19:30:00"}', encoding="utf-8")
        assert W.read_marker(mp)[0] == {"stage": "sales", "at": T(2026, 10, 7, 19, 30)}
        mp.write_text("{깨짐", encoding="utf-8")
        assert W.read_marker(mp)[0] is None and "읽기 실패" in W.read_marker(mp)[1]
    ok("다 받으면 완료 종료·중단/진전없음 종료·같은 ①완료 재실행 안 함·① 진행 중 정지·단계 기록 왕복")


def p13_accounts_file():
    print("[P13] 정산 계정 파일 — 탭/공백 섞임·뒤 공백·3열=비번 줄은 이름 없음(비번 비노출)·중복/칸 없음=오류·계정명 맞춤")
    from coupang_analytics import settlement_accounts as SA
    from coupang_analytics import settlement_files as SF
    text = ("acc1\tpw1!!\t홍길동-주식회사 가나\n"           # 이름에 공백
            "acc2 \tsecret#9\tsecret#9\n"                  # 3열 = 비번(실제 파일에 있는 모양)
            "acc3  pw3\t\n"                                 # 이름 없음·공백 구분
            "plan_it \tpw4* \t 김다라_플랜\n"               # 뒤 공백·밑줄 ID
            "\n\t\n")
    accts, warns = SA.parse_accounts_text(text)
    assert [(a.account_id, a.label, a.password) for a in accts] == [
        ("acc1", "홍길동-주식회사 가나", "pw1!!"), ("acc2", "acc2", "secret#9"), ("acc3", "acc3", "pw3"),
        ("plan_it", "김다라_플랜", "pw4*")]
    assert len(warns) == 2 and "비밀번호와 같아" in warns[0] and not any("secret" in w for w in warns)   # 비번 비노출
    assert "secret" not in repr(accts) and "pw1" not in repr(accts)                                       # repr 에도 없음
    expect(SA.AccountsFileError, lambda: SA.parse_accounts_text("acc1 a 이름\nacc1 b 이름"), "중복 계정ID")
    expect(SA.AccountsFileError, lambda: SA.parse_accounts_text("acc1\n"), "비번 칸 없음")
    expect(SA.AccountsFileError, lambda: SA.parse_accounts_text("\n\n"), "빈 파일")
    with tempfile.TemporaryDirectory() as tmp:
        expect(SA.AccountsFileError, lambda: SA.read_accounts_file(Path(tmp) / "없음.txt"), "파일 없음")
        (Path(tmp) / "a.txt").write_bytes("acc1\tpw\t이름".encode("cp949"))
        expect(SA.AccountsFileError, lambda: SA.read_accounts_file(Path(tmp) / "a.txt"), "UTF-8 아님")
        (Path(tmp) / "b.txt").write_text("﻿acc1\tpw\t이름", encoding="utf-8")
        assert SA.read_accounts_file(Path(tmp) / "b.txt")[0][0].account_id == "acc1"                  # BOM 허용
    assert SA.display_name(accts[0]) == "홍길동-주식회사 가나-acc1"
    olds = ["(주)가나-acc1", "홍길동-주식회사 가나-acc1", "옛이름-plan_it", "남의-xacc3", "모름-zzz"]
    assert SA.renames(olds, accts) == {"(주)가나-acc1": "홍길동-주식회사 가나-acc1", "옛이름-plan_it": "김다라_플랜-plan_it"}
    tok = lambda x: SF._token(x, "계정명")
    assert SA.renames(["(주)가나-acc1", "옛이름-plan-it"], accts, tok=tok) == {
        "(주)가나-acc1": "홍길동-주식회사-가나-acc1", "옛이름-plan-it": "김다라-플랜-plan-it"}
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import settlement_download as TD
    from coupang_analytics import settlement_jobs as SJ
    here = [SJ.Job("홍길동-주식회사 가나-acc1", "윙", "주정산", "주문상세", "2026-01-05", "2026-01-11", "2026-01-30",
                   status=SJ.ST_DONE, file="홍길동-주식회사-가나-acc1_20260130_윙_주정산_주문상세_20260105-20260111.xlsx")]
    came = [SJ.Job("(주)가나-acc1", "윙", "주정산", "주문상세", "2026-01-05", "2026-01-11", "2026-01-30",
                   file="(주)가나-acc1_20260130_윙_주정산_주문상세_20260105-20260111.xlsx"),
            SJ.Job("(주)가나-acc1", "윙", "최종액", "주문상세", "2026-01-01", "2026-01-31", "2026-03-02",
                   file="비용/(주)가나-acc1_20260302_윙_최종액_주문상세_20260101-20260131.xlsx")]
    TD._rename_jobs(came, accts)
    assert came[1].file == "비용/홍길동-주식회사-가나-acc1_20260302_윙_최종액_주문상세_20260101-20260131.xlsx"
    assert SJ.merge_jobs(here, came) == (1, 1) and here[0].status == SJ.ST_DONE     # 옛 이름이어도 같은 작업은 한 번
    ok("공백/탭 혼합·3열=비번→이름 없음(경고·repr 비노출)·중복/칸 없음/빈 파일/UTF-8 아님=오류·BOM·계정ID 끝 기준 이름 맞춤"
       "·다른 PC 기록 합치기(옛 이름 맞춘 뒤 중복 없음)")


def p14_status_reader():
    print("[P14] 상태 화면 리더 — heartbeat(_현재상태.txt)↔UI 리더 계약·멈춤 의심 판정·오늘 집계")
    import os as _os
    import re as _re
    from datetime import datetime as _dtm
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ui"))
    import settlement_status_panel_qt as UI               # PySide6 는 이 프로젝트 필수 의존(앱 UI)
    from coupang_analytics import settlement_runlog as RLG
    fixed = _dtm(2026, 10, 7, 12, 55, 0)
    with tempfile.TemporaryDirectory() as tmp:
        lg = RLG.RunLog(tmp, now=fixed)                             # RunLog.dir = <tmp>/로그
        lg.heartbeat("작동중", "①판매수집 완료 — 재개 · 멈춤 10-07 17:40")
        lg.record("A-1", "요청", RLG.OK, "다운로드 요청함", channel="윙", settle_date="2026-01-12")
        lg.record("B-2", "요청", RLG.BLOCK, "차단 화면", channel="윙", settle_date="2026-01-12")
        # heartbeat 의 '갱신'은 실제 now(생존신호) → 시간 판정만 고정(형식·라벨은 heartbeat 실제 출력 그대로 검증).
        lg.status.write_text(_re.sub(r"갱신: .*", f"갱신: {fixed:%Y-%m-%d %H:%M:%S}",
                                     lg.status.read_text(encoding="utf-8")), encoding="utf-8")
        _os.utime(lg.text, (fixed.timestamp(),) * 2)               # 로그 mtime 도 고정
        info = UI.read_settlement_status(lg.dir, now=_dtm(2026, 10, 7, 12, 57, 0))
        assert info["exists"] and info["상태"] == "작동중" and not info["stale"], info   # 2분 전 = 정상
        assert info["내용"].startswith("①판매수집 완료") and info["log_name"] == lg.text.name
        cnt = UI.read_settlement_status(lg.dir, now=_dtm.now())["today_counts"]    # 누적 CSV 는 실제 '시각'(오늘)
        assert cnt.get(RLG.OK) == 1 and cnt.get(RLG.BLOCK) == 1, cnt              # 오늘 쓴 2줄 집계
        late = UI.read_settlement_status(lg.dir, now=_dtm(2026, 10, 7, 13, 20, 0))
        assert late["stale"] is True, late                                       # 25분 무변화 = 멈춤 의심
        empty = Path(tmp) / "빈폴더"
        assert UI.read_settlement_status(empty)["exists"] is False               # 로그 없음 = 아직 실행 안 됨
        assert UI._counts_text({}) == "오늘 받은 기록 없음" and "분 전" in UI._age_text(180)
    ok("heartbeat 덮어쓰기 파싱·작동중/대기중 멈춤 의심(STALE_SEC)·오늘 결과 집계·로그 없음/빈값 표기")


def p15_browser_closed_transient():
    print("[P15] 브라우저 닫힘(reap)=일시적 — '차단'·연속 실패로 안 셈·다음 바퀴 재시도")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    import settlement_download as SD
    # 브라우저/탭 닫힘 오류는 True(일시적), 그 외 오류는 False(진짜 실패)
    assert SD._is_browser_closed(Exception("Target page, context or browser has been closed"))
    assert SD._is_browser_closed(type("TargetClosedError", (Exception,), {})("x"))
    assert SD._is_browser_closed(Exception("Connection closed while reading from the driver"))
    assert not SD._is_browser_closed(Exception("Access Denied"))
    assert not SD._is_browser_closed(ValueError("표 머리글 없음"))
    ok("TargetClosedError·'has been closed'·'Connection closed'=일시적(True)·그 외(차단/파싱 오류)=False")


def p16_cost_by_product():
    print("[P16] 로켓그로스 비용 상품별 — 상세 줄→상품·월(VAT 별도 정확·세액 비율 배분 합 일치)·보상=옵션→상품·박스 여러 상품=묶음")
    from coupang_analytics import settlement_files as SF
    from coupang_analytics import settlement_stats as ST
    end = D("2025-12-21")
    head = [[], ["쿠팡풀필먼트서비스(CFS) 배송비 정산 내역"], ["정산주기(종료일)", "배송비 합계", "세액", "최종비용"],
            ["2025-12-21", 1000.0, 101.0, 1101.0], [], [],
            ["정산유형", "정산주기(종료일)", "매출인식일", "등록상품 ID", "옵션ID", "등록상품명", "판매수량",
             "쿠팡풀필먼트서비스(CFS) 배송비 (VAT 별도)", None, None, None, None],
            [None, None, None, None, None, None, None, "발생비용(A)", "할인가(B)", "할인적용가(A-B)", "추가비용", "최종비용"]]
    ship = head + [["주정산", "2025-12-21", "2025-12-15", "77", "701", "보냉백", 1, 900, 0, 900, 0, 700.0],
                   ["주정산", "2025-12-21", "2025-12-16", "77", "701", "보냉백", 1, 900, 0, 900, 0, -100.0],   # 음수 조정 줄
                   ["주정산", "2025-12-21", "2026-01-02", "88", "801", "압축팩", 1, 400, 0, 400, 0, 400.0]]
    lines = SF.rg_cost_lines({"배송비": ship}, "A", end)
    got = [(c.product_id, c.month, c.ex_vat, c.vat) for c in lines]
    assert got == [("77", "2025-12", 600, 61), ("88", "2026-01", 400, 40)], got   # '최종비용' 칸·월=매출인식일·세액 합 101
    bad = [r[:] for r in ship]
    bad[8][11] = 701.0                                                              # 상세 합 ≠ 요약 합계
    expect(SF.SettlementParseError, lambda: SF.rg_cost_lines({"배송비": bad}, "A", end), "상세 합 불일치")
    ret = [[], ["반출 배송"], ["정산주기(종료일)", "합계", "세액", "최종비용"], ["2025-12-21", 3000.0, 300.0, 3300.0], [], [],
           ["정산유형", "정산주기(종료일)", "매출인식일", "대표 등록상품 ID", "대표 등록상품명", "비용 청구 수량", "X", None],
           [None, None, None, None, None, None, "발생비용(A)", "최종비용(A-B-C)"]]
    ret += [["주정산", "2025-12-21", "2025-12-15", "77,77", "보냉백,보냉백", 1, 0, 1000.0],      # 같은 상품 반복 = 그 상품
            ["주정산", "2025-12-21", "2025-12-15", "77,88", "보냉백,압축팩", 1, 0, 1000.0],      # 서로 다른 상품 = 묶음
            ["주정산", "2025-12-21", "2025-12-15", "-", "-", 1, 0, 1000.0]]                    # 미표기
    rl = SF.rg_cost_lines({"반출 배송 서비스비 리포트": ret}, "A", end)
    assert sorted(c.product_id for c in rl) == sorted(["77", SF.MULTI_PRODUCT, SF.NO_PRODUCT])
    assert sum(c.vat for c in rl) == 300
    comp = [[None] * 3, ["발생일", "정산주기(종료일)", "주문ID", "옵션ID", "등록상품명", "보상 금액"],
            [None] * 6, ["2025-12-02", "2025-12-21", "1", "701", "보냉백", 4775.0],
            ["2025-12-09", "2025-12-21", "2", "999", "모르는상품", 1000.0]]
    cl = SF.rg_cost_lines({"재고 손실 보상": comp}, "A", end)
    assert [(c.kind, c.option_id, c.ex_vat, c.vat) for c in cl] == [
        (SF.COMPENSATION, "701", 4775, 0), (SF.COMPENSATION, "999", 1000, 0)]
    assert SF._split(101, [900, -100, 400]) == [76, -9, 34] and sum(SF._split(7, [1, 1, 1])) == 7
    expect(SF.SettlementParseError, lambda: SF._split(5, [1, -1]), "합 0 인데 나눌 값")
    res = ST.aggregate([], lines + rl + cl)
    by = {p.product_id: p for p in res.products if p.month == "2025-12"}
    assert by["77"].rg_cost == 661 + 1100 and by["77"].rg_comp == 4775            # 배송 + 반출배송(같은 상품 반복)
    assert by["77"].settle_after_costs == 0 - 1761 + 4775 and by["77"].costs["배송비"] == 661
    assert "옵션 999" in by and any("옵션ID 로 상품을 못 찾아" in w for w in res.warnings)
    assert any(SF.MULTI_PRODUCT in w for w in res.warnings) and any(SF.NO_PRODUCT in w for w in res.warnings)
    import openpyxl
    with tempfile.TemporaryDirectory() as tmp:
        wb = openpyxl.load_workbook(ST.write_stats(Path(tmp) / "c.xlsx", res))
        ws = wb["로켓그로스 비용 상품별"]
        hdr = [c.value for c in ws[1]]
        assert hdr[:5] == ["계정", "월(매출인식)", "등록상품ID", "상품명", "배송비"] and hdr[-2:] == ["물류비 합계(VAT포함)", "재고 손실 보상"]
        am = [c.value for c in wb["계정별 월별"][2]]
        assert am[5:] == [sum(p.rg_cost for p in by.values()), 5775, -sum(p.rg_cost for p in by.values()) + 5775]
    ok("상세→상품·월(음수 줄 포함)·세액 배분 합 일치·상세 합 불일치=오류·박스 같은 상품/여러 상품/미표기·보상 옵션→상품·"
       "못 찾음=옵션 줄+경고·상품/계정 시트 물류비·보상·반영 후")


def p17_server_busy():
    print("[P17] 서버 일시 오류(502·503·504) — 재시도 후 성공·끝내 실패=대기(차단·연속실패 아님)·전체 중단 안 함")
    import contextlib
    from datetime import datetime
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import settlement_download as TD
    from coupang_analytics import settlement_runlog as RLG
    from coupang_analytics import settlement_wing_api as API

    class SeqPage:                                                      # 응답 차례대로
        def __init__(self, seq):
            self.seq = list(seq)

        def evaluate(self, js, arg=None):
            st, text = self.seq.pop(0)
            return {"status": st, "ctype": "x", "text": text}

    class B:
        def __init__(self, seq):
            self.page = SeqPage(seq)
    old_retry, old_log = TD.SERVER_BUSY_RETRY, TD.LOG
    with tempfile.TemporaryDirectory() as tmp:
        TD.LOG = RLG.RunLog(tmp, now=datetime(2026, 10, 8, 12), echo=lambda m: None)
        TD.SERVER_BUSY_RETRY = (0, 2)
        try:
            assert TD.api(B([(504, "<html>"), (502, "<html>"), (200, '{"ok":1}')]), "A", "POST", "/p", {}) == {"ok": 1}
            expect(API.ServerBusy, lambda: TD.api(B([(504, "<html>")] * 3), "A", "POST", "/p", {}), "3번 다 504")
            expect(TD.BlockDetected, lambda: TD.api(B([(403, "x")]), "A", "POST", "/p", {}), "403=차단")
            assert [r["결과"] for r in TD.LOG.rows] == [RLG.BLOCK]                 # 504 는 차단 기록 없음

            @contextlib.contextmanager
            def fake_session(a, hidden, until=None):
                yield None

            def busy_run(a, b, args, jobs):
                raise API.ServerBusy("/tenants/x → 504 서버 일시 오류")

            class Acc:
                def __init__(self, i):
                    self.account_id, self.label = i, i

            class Args:
                until, until_at, hidden, command = "", None, True, "run"
            old_session, old_name = TD.session, TD.name_of
            TD.session, TD.name_of = fake_session, (lambda a: a.account_id)
            try:
                TD.LOG = RLG.RunLog(tmp, now=datetime(2026, 10, 8, 13), echo=lambda m: None)
                rc = TD._run_accounts([Acc("a1"), Acc("a2"), Acc("a3")], busy_run, Args)
            finally:
                TD.session, TD.name_of = old_session, old_name
            assert rc == 0, rc                                                      # 연속 2계정이어도 전체 중단 안 함
            res = [(r["계정"], r["결과"]) for r in TD.LOG.rows if r["단계"] == "계정"]
            assert res == [("a1", RLG.WAIT), ("a2", RLG.WAIT), ("a3", RLG.WAIT)], res
            assert not any(r["결과"] == RLG.BLOCK for r in TD.LOG.rows)
        finally:
            TD.SERVER_BUSY_RETRY, TD.LOG = old_retry, old_log
    ok("504→502→성공=값 반환·3번 실패=ServerBusy·403=차단 기록·계정 단위 일시 오류=대기·연속 3계정도 전체 중단 안 함")


def p18_verify_collect():
    print("[P18] 검증 자료 수집 — 월 끝=어제·화면 먼저 열기·월렛 여러 쪽·계좌 칸 제거·한 달 일시 오류여도 계속")
    from datetime import date
    from coupang_analytics import settlement_verify_collect as VC
    from coupang_analytics import settlement_wing_api as API
    ms = VC.months(D("2026-01-01"), D("2026-10-08"))
    assert len(ms) == 10 and ms[0] == ("202601", D("2026-01-01"), D("2026-01-31")) and ms[-1] == ("202610", D("2026-10-01"), D("2026-10-07"))
    assert VC.months(D("2026-10-01"), D("2026-10-01")) == []                          # 어제 이전 달 없음
    log: list = []

    def open_page(url):
        log.append(("화면", url))

    def call(method, path, body):
        log.append((method, path, body))
        if path == VC.WALLET_HIST:
            return {"walletHistories": [{"amount": 10 + body["pageNumber"], "bankAccountOwner": "예금주"}], "totalPage": 2}
        if path == VC.WALLET_BAL:
            return {"content": {"balanceAmount": 21, "bankAccountNumber": "123"}}
        if path == VC.PURCHASE and body["fromDate"] == "2026-09-01":
            raise API.ServerBusy("504")
        if path == VC.PENDING:                     # 보류목록 = 긴 기간 한 번 + 여러 쪽(실측 2026-10-19 원더폴리 2025-12 보류 10건)
            return {"pendingReports": [{"finalPaymentAmount": body["page"], "bankAccount": "가림"}], "totalPageCount": 2}
        return {"ok": path, "body": body}
    d = VC.collect(call, open_page, D("2026-08-01"), D("2026-10-08"))
    assert d["wallet"] == [{"amount": 10}, {"amount": 11}] and d["wallet_balance"] == 21    # 2쪽·예금주 제거
    assert "예금주" not in str(d) and "123" not in str(d)
    assert d["purchase"]["202609"] is None and d["purchase"]["202608"]["body"]["toDate"] == "2026-08-31"
    assert d["purchase"]["202610"]["body"]["toDate"] == "2026-10-07"                         # 오늘 이후 날짜 안 넣음
    old = [x for x in d["조회 실패"] if not x.startswith(("빠른정산", "리뷰 이벤트"))]   # 새 항목(P50)은 이 가짜 응답 모양으론 실패가 맞음
    assert len(old) == 1 and "매출내역 202609" in old[0], d["조회 실패"]
    assert d["wing_vat"]["body"] == {"from": 202608, "to": 202610}
    assert d["rg_vat"]["ok"].endswith("?fromYearMonth=2026-08&toYearMonth=2026-10")
    pend = [x for x in log if x[:2] == ("POST", VC.PENDING)]
    assert len(pend) == 2, pend                                                              # 달마다 아님 — 기간 한 번·2쪽
    assert d["pending"]["전체"]["pendingReports"] == [{"finalPaymentAmount": 1}, {"finalPaymentAmount": 2}]
    assert d["pending"]["전체"]["totalRecordCount"] == 2 and d["pending"]["전체"]["from"] == "2025-01-01"
    assert d["pending"]["전체"]["to"] == "2026-10-07"                                          # 어제까지·2026 전 보류 포함
    i = log.index(("화면", VC.SALES_URL))
    assert log[i + 1][:2] == ("POST", VC.PURCHASE)                                         # 매출내역 화면 연 뒤 조회
    assert log.index(("화면", VC.PENDING_URL)) < next(k for k, x in enumerate(log) if x[:2] == ("POST", VC.PENDING))
    ok("월 끝=어제·빈 달 없음·화면 먼저·월렛 2쪽·예금주/계좌 제거·504 달=조회 실패 기록 후 계속·부가세 요청 모양")


def p19_verify_sheet():
    print("[P19] 정산 검증 — RG계산식·RG입금(보상 제외)·월렛장부·윙판매/지급·부가세·보류/추가지급·판정 규칙")
    from coupang_analytics import settlement_verify as SV
    rg = [{"정산일": "2026-08-03", "기간 시작": "2026-06-29", "기간 끝": "2026-06-30", "지급비율": 70, "최종지급액": 412909,
           "totalPayableAmount": 359852, "totalCfsInventoryCompensationAmount": 53057},
          {"정산일": "2026-08-03", "기간 시작": "2026-06-08", "기간 끝": "2026-06-14", "지급비율": 30, "최종지급액": 158356,
           "totalPayableAmount": 152130, "totalSalesAdjustment": 6226},
          {"정산일": "2026-10-07", "기간 시작": "2026-08-31", "기간 끝": "2026-08-31", "지급비율": 70, "최종지급액": 69394,
           "totalPayableAmount": 112832, "totalAdditionalDeductionAmount": 112832, "totalCfsInventoryCompensationAmount": 69394},
          {"정산일": "2026-10-15", "기간 시작": "2026-08-31", "기간 끝": "2026-08-31", "지급비율": 30, "최종지급액": 7111,
           "totalPayableAmount": 48354, "totalAdditionalDeductionAmount": 16284, "totalFinalCfsFeeDeductionAmount": 24959}]
    f = SV.rg_formula("A", rg)
    assert f[0]["우리(계산)"] == 4 and f[0]["판정"] == SV.OK and len(f) == 1                  # 4줄 모두 H−I−J+K+조정
    bad = SV.rg_formula("A", [{**rg[0], "최종지급액": 1}])
    assert bad[1]["판정"] == SV.DIFF and bad[1]["차이"] == 412908
    v = {"수집일": "2026-10-08", "기간": ["2026-01-01", "2026-10-07"], "조회 실패": [], "wallet_balance": 300000,
         "wallet": [{"walletEventType": "DEPOSIT", "paymentDate": "20260803000729", "amount": 359852 + 158356},
                    {"walletEventType": "WITHDRAWAL", "paymentDate": "20260805", "amount": 518208 - 300000}],
         "purchase": {"202605": {"purchaseReports": [{"revenueAmount": 8602500, "sellerDiscountCoupon": 0, "feeAmount": 968234,
                                                      "apAmount": 7634266, "deductionAmount": 55000, "finalPaidAmount": 7579266}]},
                      "202609": {"purchaseReports": [{"revenueAmount": 2065700, "sellerDiscountCoupon": 1116300, "feeAmount": 94452,
                                                      "apAmount": 854948, "deductionAmount": 87556, "finalPaidAmount": 767392}]},
                      "202610": None},
         "wing_vat": {"paymentMethodReports": [{"yearMonth": "202605", "total": 8602500}]},
         "rg_vat": {"vatResponseAggregatedDtos": [{"yearMonth": "2026-07", "creditCardPaymentAmountAgg": 7106626,
                                                   "cashPaymentAmountAgg": 2231507, "otherPaymentAmountAgg": 10701127,
                                                   "sellerFundedCouponAggAmount": 10134700}]},
         "pending": {"202605": {"totalRecordCount": 0}}, "additional": {"202605": {"reports": [{"x": 1}]}}}
    w = {x["기준"]: x for x in SV.rg_wallet("A", rg, v)}
    assert w["지급일 2026-08-03"]["판정"] == SV.OK and "보상 53,057 제외" in w["지급일 2026-08-03"]["비고"]
    assert w["지급일 2026-10-07"]["판정"] == SV.OK and w["지급일 2026-10-07"]["쿠팡"] == 0      # 보상만 있는 날: 0 = 입금 없음
    assert w["지급일 2026-10-15"]["판정"] == SV.PENDING                                      # 수집일 이후 = 미정산
    assert w["~2026-10-08"]["판정"] == SV.OK                                                 # 입금 − 인출 = 잔액
    comp = [x for x in SV.rg_wallet("A", rg, v) if x["대조"] == "재고손실보상"]
    assert comp[0]["우리(계산)"] == 53057 + 69394 and comp[0]["판정"] == SV.CONFIRMED          # 공식: 대표계좌 별도 입금
    assert "대표 정산 계좌" in comp[0]["비고"]
    ours = {"202605": {"매출": 8602500, "쿠폰": 0, "수수료": 968234, "정산대상": 7634266}}
    ws = SV.wing_sales("A", ours, v)
    assert [x["판정"] for x in ws if x["기준"] == "202605"] == [SV.OK] * 4
    assert all(x["판정"] == SV.PENDING for x in ws if x["기준"] == "202609")                  # 최근 달·우리 0 = 미정산
    assert any(x["기준"] == "202610" and x["판정"] == SV.NODATA for x in ws)                   # 조회 실패 달
    wp = SV.wing_pay("A", [{"정산일": "2026-07-01", "기간 시작": "2026-05-01", "최종지급액": 7579266, "paidAmount": 7634266,
                            "totalDeductionAmount": 55000, "지급상태": "DONE"},
                           {"정산일": "2026-06-01", "기간 시작": "2026-05-04", "최종지급액": 0, "지급상태": "HOLD"}], v)
    assert [x["판정"] for x in wp if x["기준"] == "202605"] == [SV.OK] * 3
    assert any(x["항목"] == "지급상태" and x["판정"] == SV.CHECK and x["비고"] == "HOLD" for x in wp)
    vt = SV.vat("A", ours, {"202607": {"판매액": 20039260, "쿠폰": 10134700}}, v)
    assert [x["판정"] for x in vt] == [SV.OK, SV.OK, SV.OK], vt
    h = {x["대조"]: x["판정"] for x in SV.holds("A", v)}
    assert h == {"보류": SV.OK, "추가지급": SV.CHECK}
    assert SV.build("A", {}, {}, [], [], None)[1]["판정"] == SV.NODATA                       # 검증 자료 없음
    import openpyxl
    from coupang_analytics import settlement_stats as ST
    rows = SV.build("A", ours, {}, [], rg, v)
    with tempfile.TemporaryDirectory() as tmp:
        res = ST.aggregate([])
        wb = openpyxl.load_workbook(ST.write_stats(Path(tmp) / "v.xlsx", res, verify=rows))
        assert [c.value for c in wb["검증"][1]] == SV.HEAD and wb["검증"].max_row == 1 + len(rows)
        assert any("검증 '확인 필요'" in w for w in res.warnings)                        # 보상·추가지급 = 확인 필요
    ok("RG계산식 4줄·틀리면 다름·입금=최종−보상·수집일 이후=미정산·월렛장부·보상=확인 필요·윙판매/지급(최근 달 미정산)·"
       "지급상태 HOLD=확인 필요·부가세 윙/RG·보류0/추가지급1·자료 없음")


def p20_rg_payout_dates():
    print("[P20] 로켓그로스 지급일 — 70%·100%=주마감+20영업일 · 30% 월걸침 주=+25 · 30% 일반=익익월 첫 영업일(실측 629/629)")
    from coupang_analytics import payout as P
    hol = {D(x) for x in ("2026-01-01", "2026-02-16", "2026-02-17", "2026-02-18", "2026-03-02", "2026-05-01", "2026-05-05",
                          "2026-05-25", "2026-06-03", "2026-07-17", "2026-08-17", "2026-09-24", "2026-09-25",
                          "2026-10-05", "2026-10-09")}   # 테스트 주입(쿠팡 실지급일과 맞춘 영업일 기준)
    cases = [  # (지급비율, 기간 시작, 기간 끝, 실제 지급일) — nicoable·bux1004 등 운용 PC 정산현황 실값
        (70, "2026-07-27", "2026-07-31", "2026-08-31"), (30, "2026-07-27", "2026-07-31", "2026-09-07"),   # 소유자 화면 확인
        (30, "2026-08-01", "2026-08-02", "2026-09-07"), (30, "2026-08-03", "2026-08-09", "2026-10-01"),
        (70, "2026-08-31", "2026-08-31", "2026-10-07"),
        (100, "2026-01-26", "2026-01-31", "2026-03-05"), (100, "2026-05-25", "2026-05-31", "2026-06-29"),
        (30, "2026-06-01", "2026-06-07", "2026-08-03"), (70, "2026-04-13", "2026-04-19", "2026-05-19"),
        (70, "2026-06-15", "2026-06-21", "2026-07-20"),
        # 월정산(MONTHLY) 100% = 그 달 1일~말일 줄 → 월 마감일 + 20영업일(도움말·D-075 novanest1284 '월정' 09-30·T-97)
        (100, "2026-08-01", "2026-08-31", "2026-09-30"), (100, "2026-09-01", "2026-09-30", "2026-10-30"),
        (100, "2026-06-01", "2026-06-30", "2026-07-29"),
        (100, "2026-09-28", "2026-09-30", "2026-11-03")]   # 주정산 월말 조각 100% 는 그대로 주 일요일 기준
    for ratio, ps, pe, want in cases:
        got = P.rg_payout_date(ratio, D(ps), D(pe), hol)
        assert got == D(want), (ratio, ps, pe, got, want)
    expect(ValueError, lambda: P.rg_payout_date(50, D("2026-08-03"), D("2026-08-09"), hol), "모르는 지급비율")
    old = P.payout_date(P.PAYOUT_RG_WEEKLY_FINAL, revenue_month="2026-07", holidays=hol)
    assert old != D("2026-09-07")                                                      # 옛 규칙(익익월)은 월걸침 주를 못 맞춤
    ok("70%·100%=+20(5/1·7/17 비영업일 반영)·월정산 100%(1일~말일)=월말+20·30% 월걸침=+25(07-27~31·08-01~02→09-07)·30% 일반=익익월·모르는 비율=오류")


def p21_bank_inflows():
    print("[P21] 계좌 입금 — 윙 지급·월렛 입금/인출·재고 손실 보상(대표계좌)·물류비 환급(익월 21일)·지급월별 합계")
    from coupang_analytics import settlement_verify as SV
    wing = [{"정산일": "2026-07-01", "최종지급액": 2235280, "지급상태": "DONE"},
            {"정산일": "2026-10-20", "최종지급액": 999, "지급상태": "SCHEDULED"}]                      # 미래 = 제외
    rg = [{"정산일": "2026-08-03", "기간 시작": "2026-06-29", "최종지급액": 412909, "totalCfsInventoryCompensationAmount": 53057},
          {"정산일": "2026-07-27", "기간 시작": "2026-06-22", "최종지급액": 0, "totalCfsFeeAdjustment": 10125}]
    v = {"수집일": "2026-10-08", "wallet": [
        {"walletEventType": "DEPOSIT", "paymentDate": "20260803000729", "amount": 359852},
        {"walletEventType": "WITHDRAWAL", "paymentDate": "20260805121648", "amount": 359852}]}
    rows = {r["지급월"]: r for r in SV.inflows("A", wing, rg, v, today=D("2026-10-08"))}
    assert rows["2026-07"]["윙 지급"] == 2235280 and rows["2026-07"]["물류비 환급"] == 10125         # 6월분 환급 = 7월 21일
    assert "07-21" in rows["2026-07"]["비고"]
    a = rows["2026-08"]
    assert (a["RG 월렛 입금"], a["RG 월렛 인출"], a["재고 손실 보상"]) == (359852, 359852, 53057)
    assert a["쿠팡 지급 합계"] == 359852 + 53057 and a["대표계좌 입금 합계"] == 359852 + 53057
    assert "2026-10" not in rows                                                         # 지급 전 회차 제외
    # 자동 인출(AUTO_WITHDRAWAL)도 대표계좌로 나간 돈 — 실측 output(23) 2026-10-16: 효성 자동 인출 113건 101,654,006원이
    # 인출 0 으로 집계돼 대표계좌 입금·월렛장부가 틀림(자동 인출 포함 시 22계정 입금−인출=잔액 원 단위 일치).
    va = {"수집일": "2026-10-08", "wallet": [
        {"walletEventType": "DEPOSIT", "paymentDate": "20260803000729", "amount": 359852},
        {"walletEventType": "AUTO_WITHDRAWAL", "paymentDate": "20260804103634", "amount": 359852}], "wallet_balance": 0.0}
    auto = {r["지급월"]: r for r in SV.inflows("A", wing, rg, va, today=D("2026-10-08"))}["2026-08"]
    assert auto["RG 월렛 인출"] == 359852 and auto["대표계좌 입금 합계"] == 359852 + 53057, auto
    led = [r for r in SV.rg_wallet("A", rg, va) if r["대조"] == "월렛장부"][0]
    assert (led["우리(계산)"], led["판정"]) == (0, "일치"), led
    none = SV.inflows("A", wing, rg, None, today=D("2026-10-08"))
    assert all(r["RG 월렛 입금"] is None for r in none) and "월렛 자료 없음" in none[0]["비고"]
    import openpyxl
    from coupang_analytics import settlement_stats as ST
    with tempfile.TemporaryDirectory() as tmp:
        wb = openpyxl.load_workbook(ST.write_stats(Path(tmp) / "i.xlsx", ST.aggregate([]),
                                                   inflows=SV.inflows("A", wing, rg, v, today=D("2026-10-08"))))
        assert [c.value for c in wb["계좌 입금"][1]] == SV.INFLOW_HEAD and wb["계좌 입금"].max_row == 3
    ok("윙=지급일 지난 회차·월렛 입금/인출·보상=정산일 대표계좌·환급=매출인식 익월 21일·합계 2종·지급 전 제외·월렛 없음 표시")


def p22_paydates_verify():
    print("[P22] 지급일 대조 — RG 전부·윙 70%·윙 30%/100%는 대상 아님·공휴일 없으면 자료 없음")
    from coupang_analytics import settlement_verify as SV
    hol = {D(x) for x in ("2026-08-17", "2026-09-24", "2026-09-25", "2026-10-05")}
    rg = [{"정산일": "2026-08-31", "기간 시작": "2026-07-27", "기간 끝": "2026-07-31", "지급비율": 70, "최종지급액": 1},
          {"정산일": "2026-09-07", "기간 시작": "2026-07-27", "기간 끝": "2026-07-31", "지급비율": 30, "최종지급액": 1},
          {"정산일": "2026-09-08", "기간 시작": "2026-08-01", "기간 끝": "2026-08-02", "지급비율": 30, "최종지급액": 1}]   # 하루 틀림
    wing = [{"정산일": "2026-09-18", "기간 시작": "2026-08-24", "기간 끝": "2026-08-30", "지급비율": 70, "최종지급액": 1},
            {"정산일": "2026-10-01", "기간 시작": "2026-08-01", "기간 끝": "2026-08-31", "지급비율": 30, "최종지급액": 1},
            {"정산일": "2026-07-20", "기간 시작": "2026-05-17", "기간 끝": "2026-05-17", "지급비율": 100, "최종지급액": 1}]
    rows = SV.paydates("A", wing, rg, hol)
    summ = {r["항목"]: r for r in rows if r["기준"] == "요약"}
    assert summ["로켓그로스"]["우리(계산)"] == 2 and summ["로켓그로스"]["쿠팡"] == 3 and summ["로켓그로스"]["판정"] == SV.DIFF
    assert summ["윙 70%"]["판정"] == SV.OK and summ["윙 70%"]["쿠팡"] == 1
    bad = [r for r in rows if r["판정"] == SV.DIFF and r["기준"] != "요약"]
    assert len(bad) == 1 and "2026-08-01" in bad[0]["항목"] and bad[0]["비고"] == "계산 2026-09-07"
    assert not any("30%" in r["항목"] and r["대조"] == "지급일" and "윙" in r["항목"] for r in rows)     # 윙 30%·100% 대상 아님
    none = SV.paydates("A", wing, rg, None)
    assert len(none) == 1 and none[0]["판정"] == SV.NODATA and "공휴일" in none[0]["비고"]
    import os
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import settlement_download as TD
    from datetime import datetime
    from coupang_analytics import settlement_runlog as RLG
    old_cwd, old_log = os.getcwd(), TD.LOG
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            TD.LOG = RLG.RunLog(tmp, now=datetime(2026, 10, 8), echo=lambda m: None)
            (Path(tmp) / "output").mkdir()
            (Path(tmp) / "output" / "_holidays_2026.json").write_text('["2026-08-17", "2026-10-05"]', encoding="utf-8")
            got = TD.load_holidays([{"정산일": "2026-08-31"}])
            assert got == {D("2026-08-17"), D("2026-10-05"), D("2026-05-01"), D("2026-07-17")}                                 # 캐시 우선(키 없어도)  # 쿠팡 비영업일 05-01·07-17 항상(D-179)
            assert TD.load_holidays([{"정산일": "2025-12-01"}]) is None                       # 캐시·키 없는 해 = None
            assert any("지급일 대조 건너뜀" in r for r in TD.LOG.text.read_text(encoding="utf-8").splitlines())
        finally:
            os.chdir(old_cwd)
            TD.LOG = old_log
    ok("RG 3줄 중 2 일치·틀린 줄 하나만 상세·윙 70% 일치·윙 30%/100% 제외·공휴일 없음=자료 없음 1줄")


def p23_calendar():
    print("[P23] 정산캘린더 — 윙 지급일은 캘린더로 대조(30% 포함·공휴일 불필요)·수집은 폼 본문·캘린더 없으면 규칙")
    from coupang_analytics import settlement_verify as SV
    from coupang_analytics import settlement_verify_collect as VC
    cal = [{"title": "9월 최종액 정산", "start": "2026-11-02 00:00:00", "transactionCycleCode": "R",
            "recognitionFrom": "2026-09-01", "recognitionTo": "2026-09-30"},
           {"title": "[주정산]\n08/31 ~ 09/06", "start": "2026-09-29 00:00:00", "transactionCycleCode": "W",
            "recognitionFrom": "2026-08-31", "recognitionTo": "2026-09-06"},
           {"title": "신정", "start": "2025-01-01 00:00:00", "transactionCycleCode": "UK", "recognitionFrom": None,
            "recognitionTo": None}]
    wing = [{"정산일": "2026-09-29", "기간 시작": "2026-08-31", "기간 끝": "2026-08-31", "지급비율": 70, "최종지급액": 1},
            {"정산일": "2026-09-29", "기간 시작": "2026-09-01", "기간 끝": "2026-09-06", "지급비율": 70, "최종지급액": 1},
            {"정산일": "2026-11-01", "기간 시작": "2026-09-01", "기간 끝": "2026-09-30", "지급비율": 30, "최종지급액": 1},   # 하루 틀림
            {"정산일": "2026-07-20", "기간 시작": "2026-05-17", "기간 끝": "2026-05-17", "지급비율": 100, "최종지급액": 1}]
    rows = SV.paydates("A", wing, [], None, calendar=cal)
    summ = {r["항목"]: r for r in rows if r["기준"] == "요약"}
    assert summ["윙(캘린더)"]["우리(계산)"] == 2 and summ["윙(캘린더)"]["쿠팡"] == 3 and summ["윙(캘린더)"]["판정"] == SV.DIFF
    bad = [r for r in rows if r["기준"] != "요약" and r["판정"] == SV.DIFF]
    assert len(bad) == 1 and bad[0]["비고"] == "캘린더 2026-11-02"                          # 휴일 보정된 최종액 날짜
    assert not any("RG" in r["항목"] or r["항목"] == "공휴일" for r in rows)                  # RG 줄 없으면 공휴일 불요
    miss = SV.paydates("A", [{**wing[0], "기간 시작": "2026-01-05", "기간 끝": "2026-01-11"}], [], None, calendar=cal)
    assert any(r["판정"] == SV.NODATA and "캘린더에 없음" in r["비고"] for r in miss)
    log: list = []

    def call(method, path, body):
        log.append((method, path, body))
        return cal if path == VC.CALENDAR else {}
    d = VC.collect(call, lambda url: log.append(("화면", url)), D("2026-01-01"), D("2026-10-08"))
    assert d["calendar"] == cal
    i = log.index(("화면", VC.CALENDAR_URL))
    assert log[i + 1] == ("POST", VC.CALENDAR, "startDate=2025-12-25&endDate=2026-12-17")    # 폼 본문·시작 7일 전~오늘+70일
    ok("윙 캘린더 대조(분할 주·최종액·틀린 날 1)·100% 제외·RG 없으면 공휴일 불요·캘린더에 없는 회차=자료 없음·수집 폼 본문")



def p24_local_store():
    print("[P24] 정산 로컬 기록 — 다른 PC 폴더 합치기·예전 계정명 맞춤·금액 기록 키 병합(이 PC 값 우선)")
    import json
    import os
    from datetime import datetime
    from types import SimpleNamespace
    sys.path.insert(0, str(ROOT / "tools"))
    import settlement_download as TD
    from coupang_analytics import settlement_accounts as SA
    from coupang_analytics import settlement_files as SF
    from coupang_analytics import settlement_jobs as SJ
    from coupang_analytics import settlement_runlog as RLG
    accts, _ = SA.parse_accounts_text("acc1\tpw1\t홍길동-주식회사 가나\n")
    new, old = "홍길동-주식회사 가나-acc1", "(주)가나-acc1"
    tnew, told = SF._token(new, "계정명"), SF._token(old, "계정명")

    def fname(acct, settle, kind="주정산", report="주문상세", ch="윙", ps="2026-01-05", pe="2026-01-11"):
        return SF.settle_file_name(acct, D(settle), ch, kind, report, D(ps), D(pe))

    def amt(settle, paid):
        return {"정산일": settle, "기간 시작": "2026-01-05", "기간 끝": "2026-01-11", "지급비율": 70, "최종지급액": paid}

    def wjson(path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    def rjson(path):
        return json.loads(path.read_text(encoding="utf-8"))

    old_cwd, old_log, old_load = os.getcwd(), TD.LOG, TD.load_accounts
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            TD.LOG = RLG.RunLog(Path(tmp) / "기록", now=datetime(2026, 10, 8), echo=lambda m: None)
            TD.load_accounts = lambda only: accts
            # (a) _migrate_names: 이 PC 에 남은 예전 이름 파일·요청 기록·금액 기록 → 지금 이름(금액은 키 병합·지금 이름 값 우선)
            f_old, f_new = fname(old, "2026-01-30"), fname(new, "2026-01-30")
            TD.FILES.mkdir(parents=True)
            (TD.FILES / f_old).write_bytes(b"old")
            SJ.save_jobs(TD.JOBS, [SJ.Job(old, "윙", "주정산", "주문상세", "2026-01-05", "2026-01-11", "2026-01-30",
                                          status=SJ.ST_DONE, file=f_old)])
            wjson(TD.AMOUNTS / f"{told}_윙.json", [amt("2026-01-30", 999), amt("2026-02-06", 7)])
            wjson(TD.AMOUNTS / f"{tnew}_윙.json", [amt("2026-01-30", 100)])
            TD._migrate_names(accts)
            assert sorted(p.name for p in TD.FILES.glob("*.xlsx")) == [f_new]
            j = SJ.load_jobs(TD.JOBS)
            assert [(x.account, x.file) for x in j] == [(new, f_new)]
            assert sorted(p.name for p in TD.AMOUNTS.glob("*.json")) == [f"{tnew}_윙.json"]
            assert [(r["정산일"], r["최종지급액"]) for r in rjson(TD.AMOUNTS / f"{tnew}_윙.json")] == [
                ("2026-01-30", 100), ("2026-02-06", 7)]                                   # 키 병합·지금 이름 값 우선·정렬
            TD._migrate_names(accts)                                                       # 멱등
            assert sorted(p.name for p in TD.FILES.glob("*.xlsx")) == [f_new] and len(SJ.load_jobs(TD.JOBS)) == 1
            # (a2) 월자료·광고·정산현황 원문도 계정ID 기준 지금 이름으로 이어 씀(T-46 ⑥ · output (37) hide4u 폴더 둘) —
            #      없는 쪽은 옮김 · 같은 이름은 지금 이름 쪽 유지 + 받은 기록·캠페인 없음은 합침 · 옛 쪽 겹친 파일 = 보관(삭제 없음)
            mo, mn = TD.VERIFY / "월자료" / told, TD.VERIFY / "월자료" / tnew
            mo.mkdir(parents=True)
            mn.mkdir(parents=True)
            (mo / "주문별매출_202605.json").write_bytes(b"o5")
            (mo / "라이브정산_202609.json").write_bytes(b"old")
            (mn / "라이브정산_202609.json").write_bytes(b"new")
            wjson(mo / "_받은기록.json", {"주문별매출": {"202605": "a"}, "라이브정산": {"202609": "a"}, "RG반품내역": "2026-11-01"})
            wjson(mn / "_받은기록.json", {"라이브정산": {"202609": "b"}, "주문별매출": {"202606": "b"}})
            ad = TD.VERIFY / "광고"
            ad.mkdir(parents=True)
            (ad / f"{told}_밀크런_202609.xlsx").write_bytes(b"m9")
            (ad / f"{told}_광고정산_202610.json").write_bytes(b"old")
            (ad / f"{tnew}_광고정산_202610.json").write_bytes(b"new")
            wjson(ad / f"{told}_광고.json", {"캠페인 없음": ["202601"]})
            wjson(ad / f"{tnew}_광고.json", {"캠페인 없음": ["202602"]})
            rg = TD.BASE / "정산현황_원문" / told
            rg.mkdir(parents=True)
            (rg / "2026-11-10.json.gz").write_bytes(b"gz")
            js = SJ.load_jobs(TD.JOBS)
            js.append(SJ.Job(old, "윙", SJ.DOC_KIND, "부가세상세", "2026-05-01", "2026-05-31", "2026-06-15", status=SJ.ST_DONE,
                             file=f"월자료/{told}/부가세상세_202605.xlsx"))
            SJ.save_jobs(TD.JOBS, js)
            TD._migrate_names(accts)
            keep = TD.BASE / "보관" / "계정명바뀜" / told
            assert not mo.exists() and sorted(p.name for p in mn.iterdir()) == [
                "_받은기록.json", "라이브정산_202609.json", "주문별매출_202605.json"], list(mn.iterdir())  # 옛 코드 = 폴더 둘
            assert (mn / "라이브정산_202609.json").read_bytes() == b"new" and (keep / "월자료" / "라이브정산_202609.json").read_bytes() == b"old"
            assert rjson(mn / "_받은기록.json") == {"주문별매출": {"202605": "a", "202606": "b"}, "라이브정산": {"202609": "b"},
                                                  "RG반품내역": "2026-11-01"}, rjson(mn / "_받은기록.json")
            assert (keep / "월자료" / "_받은기록.json").exists(), "합친 옛 받은 기록도 보관(삭제 없음)"
            assert sorted(p.name for p in ad.iterdir()) == [f"{tnew}_광고.json", f"{tnew}_광고정산_202610.json",
                                                            f"{tnew}_밀크런_202609.xlsx"], list(ad.iterdir())
            assert (ad / f"{tnew}_광고정산_202610.json").read_bytes() == b"new"
            assert (keep / "광고" / f"{told}_광고정산_202610.json").read_bytes() == b"old"
            assert rjson(ad / f"{tnew}_광고.json") == {"캠페인 없음": ["202601", "202602"]}
            assert not rg.exists() and (TD.BASE / "정산현황_원문" / tnew / "2026-11-10.json.gz").read_bytes() == b"gz"
            assert [j_.file for j_ in SJ.load_jobs(TD.JOBS) if j_.kind == SJ.DOC_KIND] == [f"월자료/{tnew}/부가세상세_202605.xlsx"]
            TD._migrate_names(accts)                                                       # 멱등
            assert sorted(p.name for p in ad.iterdir()) == [f"{tnew}_광고.json", f"{tnew}_광고정산_202610.json",
                                                            f"{tnew}_밀크런_202609.xlsx"] and not mo.exists()
            js = [j_ for j_ in SJ.load_jobs(TD.JOBS) if j_.kind != SJ.DOC_KIND]
            SJ.save_jobs(TD.JOBS, js)                                                      # 아래 (b) 시험 기대값 그대로
            # (b) cmd_merge: 옮겨 온 폴더(예전 이름) 합치기 — 같은 작업 1회·같은 이름 파일은 원본에 남김·비용 폴더·금액 병합
            src = Path(tmp) / "옮겨온"
            f2_old, c_old = fname(old, "2026-02-06", ps="2026-01-12", pe="2026-01-18"), fname(old, "2026-01-30", "주정산", "보관비", "로켓그로스")
            SJ.save_jobs(src / "_요청기록.json", [
                SJ.Job(old, "윙", "주정산", "주문상세", "2026-01-05", "2026-01-11", "2026-01-30", file=f_old),
                SJ.Job(old, "윙", "주정산", "주문상세", "2026-01-12", "2026-01-18", "2026-02-06", status=SJ.ST_DONE,
                       file=f2_old)])
            (src / "파일" / "비용").mkdir(parents=True)
            (src / "파일" / f_old).write_bytes(b"other")
            (src / "파일" / f2_old).write_bytes(b"f2")
            (src / "파일" / "비용" / c_old).write_bytes(b"c")
            wjson(src / "쿠팡지급내역" / f"{told}_윙.json", [amt("2026-01-30", 555), amt("2026-02-13", 3)])
            assert TD.cmd_merge(SimpleNamespace(src=str(src))) == 0
            j = SJ.load_jobs(TD.JOBS)
            assert [(x.account, x.settle_date, x.status, x.file) for x in j] == [
                (new, "2026-01-30", SJ.ST_DONE, f_new), (new, "2026-02-06", SJ.ST_DONE, fname(new, "2026-02-06", ps="2026-01-12", pe="2026-01-18"))], j
            assert (TD.FILES / f_new).read_bytes() == b"old" and (src / "파일" / f_old).exists()   # 같은 이름 = 그대로 둠
            assert (TD.FILES / fname(new, "2026-02-06", ps="2026-01-12", pe="2026-01-18")).read_bytes() == b"f2" and not (src / "파일" / f2_old).exists()
            assert [p.name for p in TD.COSTS.glob("*.xlsx")] == [fname(new, "2026-01-30", "주정산", "보관비", "로켓그로스")]
            # 옮겨 온 금액 기록(예전 이름)도 지금 이름 하나로 합침·같은 키는 이 PC 값 우선(2026-10-08 결함 수정 —
            # 예전엔 파일·요청 기록만 새 이름이 되고 금액 기록은 예전 이름으로 남아 집계에서 계정이 둘로 갈렸음)
            assert sorted(p.name for p in TD.AMOUNTS.glob("*.json")) == [f"{tnew}_윙.json"]
            assert [(r["정산일"], r["최종지급액"]) for r in rjson(TD.AMOUNTS / f"{tnew}_윙.json")] == [
                ("2026-01-30", 100), ("2026-02-06", 7), ("2026-02-13", 3)]
            rec = [r for r in TD.LOG.rows if r["단계"] == "합치기"]
            assert len(rec) == 1 and rec[0]["결과"] == RLG.OK and "1건 추가·1건 이미 있음" in rec[0]["사유"] \
                and "파일 2개 옮김·1개 같은 이름" in rec[0]["사유"], rec
            # (c) _save_amounts: 정산현황 응답 → 계정·채널 JSON 에 키로 덮어 모음
            resp = {"paymentReports": [{"payDate": "2026-02-13", "recognitionFrom": "2026-01-05",
                                        "recognitionTo": "2026-01-11", "ratio": 70, "finalPaidAmount": 4, "detail": {}}]}
            TD._save_amounts(new, "윙", resp)
            got = rjson(TD.AMOUNTS / f"{tnew}_윙.json")
            assert [(r["정산일"], r["최종지급액"]) for r in got] == [("2026-01-30", 100), ("2026-02-06", 7), ("2026-02-13", 4)]
            # (c2) 같은 지급일·기간·비율 줄이 여러 개(보류 해제 100% — 실측 2026-10-19 디프 5/12 23줄·5/4 42줄, 줄 번호 없음)
            #      = 전부 보관 · 같은 지급일을 다시 조회하면 그날 줄 묶음을 통째로 바꿈(늘어나지 않음)
            rel = lambda amt: {"payDate": "2026-05-12", "recognitionFrom": "2026-04-29", "recognitionTo": "2026-04-29",  # noqa: E731
                               "ratio": 100, "finalPaidAmount": amt, "detail": {}}
            TD._save_amounts(new, "윙", {"paymentReports": [rel(219232), rel(63428)]})
            TD._save_amounts(new, "윙", {"paymentReports": [rel(219232), rel(63428)]})
            got = [r["최종지급액"] for r in rjson(TD.AMOUNTS / f"{tnew}_윙.json") if r["정산일"] == "2026-05-12"]
            assert sorted(got) == [63428, 219232], got
            TD._save_amounts(new, "윙", {"paymentReports": [rel(5)]})
            assert [r["최종지급액"] for r in rjson(TD.AMOUNTS / f"{tnew}_윙.json") if r["정산일"] == "2026-05-12"] == [5]
            assert len(rjson(TD.AMOUNTS / f"{tnew}_윙.json")) == 4                            # 다른 지급일 줄은 그대로
            # (c3) 다른 PC 기록 합치기 — 같은 지급일은 이 PC 줄 묶음 우선·없는 지급일은 옮겨 온 줄 묶음 전부
            o = Path(tmp) / "옮김.json"
            wjson(o, [{**amt("2026-05-12", 1)}, {**amt("2026-05-12", 2)}, {**amt("2026-06-16", 3)}, {**amt("2026-06-16", 4)}])
            TD.STORE.merge_amount_file(o, TD.AMOUNTS / f"{tnew}_윙.json")
            m = rjson(TD.AMOUNTS / f"{tnew}_윙.json")
            assert [r["최종지급액"] for r in m if r["정산일"] == "2026-05-12"] == [5]
            assert sorted(r["최종지급액"] for r in m if r["정산일"] == "2026-06-16") == [3, 4]
            # (d) 이 PC 에 예전 이름 금액 기록만 남은 경우(받은 파일·요청 기록엔 예전 이름 없음)도 다음 실행 때 맞춰짐
            wjson(TD.AMOUNTS / f"{told}_로켓그로스.json", [amt("2026-03-03", 11)])
            TD._migrate_names(accts)
            assert sorted(p.name for p in TD.AMOUNTS.glob("*.json")) == [f"{tnew}_로켓그로스.json", f"{tnew}_윙.json"]
            assert [r["최종지급액"] for r in rjson(TD.AMOUNTS / f"{tnew}_로켓그로스.json")] == [11]
            wjson(TD.AMOUNTS / "남의이름-zzz_윙.json", [amt("2026-03-03", 1)])               # 계정 파일에 없는 계정 = 그대로
            TD._migrate_names(accts)
            assert (TD.AMOUNTS / "남의이름-zzz_윙.json").exists()
            assert not list(TD.AMOUNTS.glob("*.tmp"))
            # (e) 검증 자료(스냅샷) — 예전 이름 파일도 지금 이름으로. 둘 다 있으면 수집일 최근 것 하나(같으면 지금 이름)
            #     2026-10-13 실측: 계정 파일 이름 칸이 바뀐 뒤 예전 이름 검증 자료가 남아 '계좌 입금'에 계정이 두 번 들어감
            wjson(TD.VERIFY / f"{told}.json", {"수집일": "2026-10-12", "wallet": ["옛"]})
            wjson(TD.VERIFY / f"{tnew}.json", {"수집일": "2026-10-12", "wallet": ["새"]})
            TD._migrate_names(accts)
            assert sorted(p.name for p in TD.VERIFY.glob("*.json")) == [f"{tnew}.json"]
            assert rjson(TD.VERIFY / f"{tnew}.json")["wallet"] == ["새"]                        # 수집일 같음 = 지금 이름
            wjson(TD.VERIFY / f"{told}.json", {"수집일": "2026-10-13", "wallet": ["더 최근"]})
            TD._migrate_names(accts)
            assert sorted(p.name for p in TD.VERIFY.glob("*.json")) == [f"{tnew}.json"]
            assert rjson(TD.VERIFY / f"{tnew}.json")["wallet"] == ["더 최근"]                    # 수집일 최근 = 그것
            (TD.VERIFY / f"{tnew}.json").unlink()
            wjson(TD.VERIFY / f"{told}.json", {"수집일": "2026-10-11", "wallet": ["옛만"]})
            wjson(TD.VERIFY / "남의이름-zzz.json", {"수집일": "2026-10-11"})                    # 계정 파일에 없는 계정 = 그대로
            TD._migrate_names(accts)
            assert sorted(p.name for p in TD.VERIFY.glob("*.json")) == sorted([f"{tnew}.json", "남의이름-zzz.json"])
            assert rjson(TD.VERIFY / f"{tnew}.json")["wallet"] == ["옛만"]
        finally:
            os.chdir(old_cwd)
            TD.LOG, TD.load_accounts = old_log, old_load
    ok("예전 이름 파일·요청·금액 → 지금 이름(멱등)·합치기(같은 작업 1회·같은 이름 파일 원본 보존·비용 폴더·금액 키 병합)"
       "·정산현황 금액 덮어 모음")

def p25_app_launch():
    print("[P25] 앱이 정산 띄우기(D-010) — 명령·창 없음·작업 묶음 분리(불가 시 분리 없이+경고)·실패 로그")
    import subprocess as _sp
    from coupang_analytics import app_process as AP
    cmd, cwd = AP.settlement_watch_cmd(1)
    assert cmd[-3] == "watch" and cmd[-4].endswith("settlement_download.py") and Path(cwd).is_dir(), (cmd, cwd)
    calls, logs = [], []
    real = _sp.Popen

    class _P:
        pid = 1

    def fake(cmd, cwd=None, creationflags=0, **k):
        calls.append(creationflags)
        if creationflags & AP._BREAKAWAY and len(calls) == 1 and fake.deny:
            raise PermissionError("job breakaway denied")
        return _P()
    try:
        _sp.Popen = fake
        fake.deny = False
        assert AP.start_settlement_watch(logs.append) is not None
        assert calls[-1] & AP._BREAKAWAY and calls[-1] & AP._NO_CONSOLE and "⚠" not in logs[-1]
        calls.clear()
        fake.deny = True
        assert AP.start_settlement_watch(logs.append) is not None
        assert len(calls) == 2 and not calls[-1] & AP._BREAKAWAY and "분리 불가" in logs[-1]
        _sp.Popen = lambda *a, **k: (_ for _ in ()).throw(OSError("없음"))
        assert AP.start_settlement_watch(logs.append) is None and "시작 실패" in logs[-1]
    finally:
        _sp.Popen = real
    ok("watch 명령·창 없이·작업 묶음 분리 우선·분리 불가 시 경고 후 그대로·시작 실패 로그")


def p26_parent_watch():
    print("[P26] 앱 종료 감시(D-020) — 사람이 앱을 닫거나 강제 종료하면 정산도 종료·무인 정상 완료면 계속")
    import subprocess as _sp
    import tempfile
    import threading
    from coupang_analytics import app_process as AP
    cmd, _ = AP.settlement_watch_cmd(4321)
    assert cmd[-3:] == ["watch", "--parent", "4321"], cmd          # 앱이 자기 PID 를 넘김
    done_file = Path(tempfile.mkdtemp()) / "_앱정상종료.json"

    def _run(finished_normally: bool) -> bool:
        app = _sp.Popen([sys.executable, "-c", "import time; time.sleep(60)"])   # '앱' 역할 실제 프로세스
        gone = threading.Event()
        AP.watch_parent(app.pid, gone.set, done_file=done_file, poll_sec=0.2)
        assert not gone.wait(0.6), "앱이 살아 있는 동안은 정산 계속"
        if finished_normally:
            AP.mark_app_finished(done_file=done_file, pid=app.pid)   # 18:00 무인 ①②③ 완주 → _auto_done
        app.kill()                                                     # 창 닫기·작업 관리자 강제 종료
        app.wait()
        return gone.wait(3)
    assert _run(finished_normally=False), "사람이 앱을 닫음/강제 종료 → 정산 종료 신호"
    assert not _run(finished_normally=True), "무인 정상 완료 뒤 앱 종료 → 정산 계속(다음 18:00 까지)"
    AP.mark_app_finished(done_file=done_file, pid=999999)              # 다른(이전) 앱의 완료 표시는 무효
    assert not AP.app_finished_normally(4321, done_file=done_file)
    gone = threading.Event()
    AP.watch_parent(999999, gone.set, done_file=Path(tempfile.mkdtemp()) / "x.json", poll_sec=0.2)
    assert gone.wait(3), "시작 때 이미 앱이 없으면(완료 표시 없음) 바로 종료 신호"
    ok("앱 PID 전달·앱 살아있으면 계속·사람 종료=정산 종료·무인 정상 완료=계속·다른 앱 완료 표시 무효·앱 이미 없음=종료")


def p27b_schedule_one_place():
    print("[P27b] 시각 한 곳(D-362·D-372) — 예약 작업 시각 = 회차 시작 · 실행 제한 = 회차 길이 · 셀독전환 멈춤 = 회차 20분 전")
    import re
    from datetime import datetime as RealDT, timedelta
    from coupang_analytics import settlement_watch as W
    from coupang_analytics import transfer_login as TL
    start = f"{W.CYCLE_START:%H:%M}"
    assert start == "00:10" and W.CYCLE_END_GAP == timedelta(minutes=10), (start, W.CYCLE_END_GAP)   # D-372 00:10 시작
    assert W.cycle_hhmm() == ("00:10", "24:00"), W.cycle_hhmm()                                      # 정산 끝 = 24시
    for name, pat in (("install.ps1", r"-Daily -At \(\[datetime\]'(\d\d:\d\d)'\)"),
                      ("install_schedule_py.ps1", r"-Daily -At (\d\d:\d\d)")):
        text = (ROOT / "deploy" / name).read_text(encoding="utf-8-sig")
        got = re.findall(pat, text)
        assert got == [start], f"{name} 예약 시각 {got} ≠ 회차 시작 {start}"
        lim = re.findall(r"-ExecutionTimeLimit \(New-TimeSpan -Hours (\d+) -Minutes (\d+)\)", text)
        assert lim and all(timedelta(hours=int(h), minutes=int(m)) == timedelta(days=1) - W.CYCLE_END_GAP
                           for h, m in lim), f"{name} 실행 제한 {lim} ≠ 회차 길이"
        assert "18:00" not in text, f"{name} 에 옛 18:00 글이 남음"
    end = RealDT.combine(RealDT(2026, 1, 1), W.CYCLE_START) - timedelta(minutes=20)
    assert TL.UNTIL_DEFAULT == f"{end:%H:%M}" == "23:50", TL.UNTIL_DEFAULT
    ok(f"예약 {start} · 실행 제한 23시간50분 = 회차 끝 24:00 · 셀독전환 멈춤 {TL.UNTIL_DEFAULT}(설치 스크립트 2개 대조)")


def p27_cycle():
    print("[P27] 정산 회차(D-021·D-372) — 00:10 앱과 함께 기동·①완료까지 대기·다 받으면 종료·그날 24:00 종료")
    import json as _json
    import os
    from datetime import datetime as RealDT, timedelta
    from types import SimpleNamespace
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import settlement_download as TD
    from coupang_analytics import settlement_runlog as RLG
    from coupang_analytics import settlement_watch as W
    D = RealDT
    assert W.cycle_window(D(2026, 10, 10, 0, 10, 5)) == (D(2026, 10, 10, 0, 10), D(2026, 10, 11, 0, 0))
    assert W.cycle_window(D(2026, 10, 10, 18, 0)) == (D(2026, 10, 10, 0, 10), D(2026, 10, 11, 0, 0)), "저녁=그날 00:10 회차"
    assert W.cycle_window(D(2026, 10, 10, 23, 59)) == (D(2026, 10, 10, 0, 10), D(2026, 10, 11, 0, 0)), "23:59=그날 회차"
    s25, e25 = W.cycle_window(D(2026, 10, 11, 0, 5))
    assert s25 == D(2026, 10, 10, 0, 10) and D(2026, 10, 11, 0, 5) >= e25, "24:00~00:10 = 지난 회차 끝남(다음 회차와 안 겹침)"
    assert W.cycle_window(D(2026, 10, 11, 0, 10))[0] == D(2026, 10, 11, 0, 10), "00:10 = 새 회차"
    start = D(2026, 10, 10, 0, 10)
    assert W.sales_done_in_cycle({"stage": "sales", "at": D(2026, 10, 10, 3)}, start)
    assert W.sales_done_in_cycle({"stage": "done", "at": D(2026, 10, 10, 11)}, start)
    assert not W.sales_done_in_cycle({"stage": "sales", "at": D(2026, 10, 9, 3)}, start), "지난 회차 ① = 대기"
    assert not W.sales_done_in_cycle(None, start)

    def run(marker_at, sales_after=None):
        """가짜 시계로 cmd_watch 한 회차 실행 → (반환값, 한 바퀴 호출 수, 마지막 상태, until_at, 종료 시각)."""
        clock = {"now": D(2026, 10, 10, 0, 10, 5)}
        passes, hb = [], []
        stage = Path("output") / "쿠팡데이타분석_실행단계.json"

        def write_marker(at):
            stage.write_text(_json.dumps({"date": f"{at:%Y-%m-%d}", "stage": "sales", "at": at.isoformat()}),
                             encoding="utf-8")
        if marker_at:
            write_marker(marker_at)

        class FakeDT(RealDT):
            @classmethod
            def now(cls, tz=None):
                return clock["now"]

        def fake_sleep(sec):
            clock["now"] += timedelta(seconds=max(sec, 1))
            if sales_after and clock["now"] >= sales_after and not stage.exists():
                write_marker(clock["now"])                          # 앱의 ①판매수집이 끝남
        olds = (TD.datetime, TD.time.sleep, TD._one_pass, TD._rest_pass, TD._pending_jobs, TD._retry_count, TD.LOG)
        args = SimpleNamespace(parent=0, ledger_synced=True, until="", until_at=None, hidden=False)   # 대장 반영(D-366 ②) = P69
        try:
            TD.datetime, TD.time.sleep = FakeDT, fake_sleep
            TD._one_pass = lambda a: (passes.append(clock["now"]), (False, 3 if len(passes) == 1 else 0))[1]   # 첫 바퀴 3건·다음 0건
            TD._rest_pass = TD._one_pass                                     # 다음 바퀴 = 남은 일 바퀴(D-382)
            TD._pending_jobs, TD._retry_count = (lambda: 0), (lambda: 0)
            TD.LOG = RLG.RunLog(TD.BASE, now=clock["now"], echo=lambda m: None)
            TD.LOG.heartbeat = lambda st, msg: hb.append((st, msg))
            rc = TD.cmd_watch(args)
        finally:
            TD.datetime, TD.time.sleep, TD._one_pass, TD._rest_pass, TD._pending_jobs, TD._retry_count, TD.LOG = olds
        if stage.exists():
            stage.unlink()
        return rc, passes, hb[-1], args.until_at, clock["now"]

    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            (Path(tmp) / "output").mkdir()
            rc, passes, last, until_at, end = run(None)                     # ① 이 끝나지 않는 회차
            assert passes == [] and last[0] == "종료" and "회차 종료" in last[1], (passes, last)
            assert end <= D(2026, 10, 11, 0, 0) + timedelta(seconds=1) and until_at == D(2026, 10, 11, 0, 0)
            rc, passes, last, _, _ = run(D(2026, 10, 9, 3))                 # 지난 회차 ① 기록만 = 받지 않음
            assert passes == [] and last[0] == "종료", (passes, last)
            rc, passes, last, _, _ = run(None, sales_after=D(2026, 10, 10, 3, 0))     # 03:00 ① 완료 → 받기
            assert passes and passes[0] >= D(2026, 10, 10, 3, 0), passes
            assert rc == 0 and len(passes) == 2 and last == ("완료", W.plan_after_pass(False, 0, 0, 0)[1]), \
                (rc, passes, last)                                              # 3건 받음 → 다음 바퀴 0건 = 다 받음 → 종료
        finally:
            os.chdir(old_cwd)
    ok("회차=00:10~그날 24:00·①완료 전/지난 회차 기록=대기만 하다 24:00 종료·① 완료 후 받기·다 받으면 바로 종료")


def p28_wait_app_profile():
    print("[P28] 앱이 그 계정 Chrome 을 쓰는 중이면 건너뛰지 않고 끝날 때까지 대기 → 이어서 진행(D-031)")
    import settlement_download as SD
    from datetime import datetime, timedelta
    seq = iter([True, True, True, False])
    orig = (SD._profile_in_use, SD.time.sleep)
    try:
        SD._profile_in_use = lambda prof: next(seq)
        SD.time.sleep = lambda s: None
        assert SD._profile_busy("p", until=datetime.now() + timedelta(hours=1)) is False, "앱이 끝나면 진행"
        SD._profile_in_use = lambda prof: True
        assert SD._profile_busy("p", until=datetime.now() - timedelta(seconds=1)) is True, "회차 끝까지 사용 중이면 그때 건너뜀"
    finally:
        SD._profile_in_use, SD.time.sleep = orig
    print("  ✓ 사용 중이면 대기·앱이 끝나면 진행·회차 끝이면 건너뜀")


def p29_monthly_failed_comment():
    print("[P29] 로켓그로스 월정산 줄 건너뜀·완료 표시에 실패 계정 수·계정 파일 # 주석 줄 (2026-10-12)")
    from datetime import datetime
    from coupang_analytics import settlement_accounts as SA
    from coupang_analytics import settlement_runlog as RLG
    from coupang_analytics import settlement_wing_api as API
    from coupang_analytics import settlement_watch as W
    # ① 실측(10-12 01:38 정산 오류 로그): 노바네스트 로켓그로스 'MONTHLY'(A01371646-2026-07-01-2026-07-31) →
    #    SiteChangedError 로 계정 전체 실패(정상 18·대기 4·실패 1). 윙 'M' 처럼 그 줄만 건너뛰고 '확인 필요'.
    week = {"settlementDate": "2026-09-06T15:00:00.000Z", "settlementPeriodStartDate": "2026-07-26T15:00:00.000Z",
            "settlementPeriodEndDate": "2026-07-30T15:00:00.000Z", "settlementRatio": 70, "settlementCycle": "WEEKLY",
            "settlementGroupKey": "V1-2026-07-27-2026-07-31"}
    month = {**week, "settlementCycle": "MONTHLY", "settlementGroupKey": "A01371646-2026-07-01-2026-07-31"}
    resp = {"settlementStatusReports": [week, month]}
    ev = API.rg_events(resp, "노바네스트")    # D-075: MONTHLY = 월정산(같은 request-download·리포트 9종 — 실측 10-16)
    assert [(e.kind, e.ref) for e in ev] == [("주정산", "V1-2026-07-27-2026-07-31"),
                                            ("월정산", "A01371646-2026-07-01-2026-07-31")], ev
    assert API.unsupported_cycles(resp) == [], "월정산은 더 이상 '확인 필요' 아님"
    expect(API.SiteChangedError, lambda: API.rg_events({"settlementStatusReports": [
        {**week, "settlementCycle": "DAILY"}]}, "a"), "모르는 RG 주기는 여전히 중단")
    ok("로켓그로스 MONTHLY = 월정산 일정(D-075)·모르는 다른 주기는 중단")
    # ② 실측(10-12 05:56): 로그인 실패 10·계정 실패 1 인데 '✅ 모든 정산 파일 다운로드 완료'·상태 '완료 · 이미 모두 받음'.
    with tempfile.TemporaryDirectory() as tmp:
        lg = RLG.RunLog(tmp, now=datetime(2026, 10, 12, 1, 38, 0), echo=lambda m: None)
        lg.record("A-1", "로그인", RLG.FAIL, "비밀번호 오류")
        lg.record("A-1", "계정", RLG.SKIP, "로그인 실패 — 건너뜀")
        lg.record("B-2", "계정", RLG.OK, "정상")
        lg.record("B-2", "계정", RLG.FAIL, "SiteChangedError")
        lg.record("C-3", "차단감지", RLG.BLOCK, "차단")
        lg.record("C-3", "요청", RLG.OK, "다음 바퀴 정상")       # 실패 뒤 정상 = 해소(세지 않음)
        fails = lg.unresolved_failures()
        assert fails == {"A-1": "로그인", "B-2": "계정"}, f"해소 안 된 실패 계정: {fails}"
    a, r = W.plan_after_pass(False, 0, 0, 0, failed=fails)
    assert a == "done" and "실패 2계정" in r and "로그인 1" in r and "계정 1" in r and "확인 필요" in r, r
    a0, r0 = W.plan_after_pass(False, 0, 0, 0)
    assert a0 == "done" and "실패" not in r0, r0
    ok("완료 문구 = '실패 N계정(로그인·계정) 확인 필요'·실패 뒤 정상 해소는 제외·실패 없으면 그대로")
    # ③ 계정 파일 '#' 주석 줄(사용 안 함 계정을 막아 두기) = 건너뜀 — 예전엔 '#id' 로 로그인 시도
    accts, _w = SA.parse_accounts_text("acc1 pw1 홍길동-가나\n# bandu11 pw2 연다인-반두\n  #plan_it pw3\nacc2 pw4\n")
    assert [a.account_id for a in accts] == ["acc1", "acc2"], f"# 주석 줄을 계정으로 읽음: {[a.account_id for a in accts]}"
    ok("계정 파일 # 주석 줄 건너뜀")


def p30_manual_full_run():
    print("[P30] 사람이 누른 전체실행도 정산 함께 기동 — 그 실행의 ①완료(--since 이후)까지 대기 후 받기(2026-10-13)")
    import json as _json
    import os
    from datetime import datetime as RealDT, timedelta
    from types import SimpleNamespace
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import settlement_download as TD
    from coupang_analytics import app_process as AP
    from coupang_analytics import settlement_runlog as RLG
    from coupang_analytics import settlement_watch as W
    D = RealDT
    cmd, _ = AP.settlement_watch_cmd(4321, since=D(2026, 10, 13, 14, 0))
    assert cmd[-5:] == ["watch", "--parent", "4321", "--since", "2026-10-13T14:00:00"], cmd
    assert AP.settlement_watch_cmd(4321)[0][-3:] == ["watch", "--parent", "4321"], "무인(18:00)은 그대로"

    def run(since):
        """14:00 수동 전체실행 — 같은 회차 새벽 02:00 ① 기록 + 그 기준 '완료' 기록이 이미 있음. 15:00 에 새 ① 완료."""
        clock = {"now": D(2026, 10, 13, 14, 0, 5)}
        passes = []
        stage = Path("output") / "쿠팡데이타분석_실행단계.json"

        def write_marker(at):
            stage.write_text(_json.dumps({"date": f"{at:%Y-%m-%d}", "stage": "sales", "at": at.isoformat()}),
                             encoding="utf-8")
        write_marker(D(2026, 10, 13, 2, 0))
        W.write_done(TD.DONE_FILE, D(2026, 10, 13, 2, 0).isoformat(timespec="seconds"), "done", "다 받음")

        class FakeDT(RealDT):
            @classmethod
            def now(cls, tz=None):
                return clock["now"]

        def fake_sleep(sec):
            clock["now"] += timedelta(seconds=max(sec, 1))
            if clock["now"] >= D(2026, 10, 13, 15, 0) and not passes and "새①" not in clock:
                clock["새①"] = True
                write_marker(clock["now"])                          # 이번 전체실행의 ①판매수집이 끝남
        olds = (TD.datetime, TD.time.sleep, TD._one_pass, TD._pending_jobs, TD._retry_count, TD.LOG)
        args = SimpleNamespace(parent=0, ledger_synced=True, until="", until_at=None, hidden=False, since=since)   # 대장 반영(D-366 ②) = P69
        try:
            TD.datetime, TD.time.sleep = FakeDT, fake_sleep
            TD._one_pass = lambda a: (passes.append(clock["now"]), (False, 0))[1]
            TD._pending_jobs, TD._retry_count = (lambda: 0), (lambda: 0)
            TD.LOG = RLG.RunLog(TD.BASE, now=clock["now"], echo=lambda m: None)
            TD.LOG.heartbeat = lambda st, msg: None
            TD.cmd_watch(args)
        finally:
            TD.datetime, TD.time.sleep, TD._one_pass, TD._pending_jobs, TD._retry_count, TD.LOG = olds
            stage.unlink(missing_ok=True)
        return passes

    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            (Path(tmp) / "output").mkdir()
            assert run("") == [], "--since 없음 = 새벽 ① 기준 '이미 끝남'으로 바로 종료(지금 무인 동작)"
            passes = run("2026-10-13T14:00:00")
            assert passes and passes[0] >= D(2026, 10, 13, 15, 0), f"이번 실행 ① 완료(15:00) 뒤에 받기: {passes}"
        finally:
            os.chdir(old_cwd)
    ok("수동 전체실행 = 실행 시각 이후 ① 완료까지 대기 후 받기·무인 명령 불변")


def p31_keep_originals():
    print("[P31] --originals = 받은 쿠팡 원본을 받은 그대로 증빙 폴더에 복사(D-062) · 지정 안 하면 지금 동작 그대로")
    import os
    from types import SimpleNamespace
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import settlement_download as TD
    from coupang_analytics import settlement_jobs as SJ
    from coupang_analytics import settlement_runlog as RLG
    data = b"PK\x03\x04-coupang-original-with-buyer-name"

    def fake_scrub(src, dst, columns=None):
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        Path(dst).write_bytes(b"PK-scrubbed")
    olds = (TD._get_bytes, TD.SF.scrub_pii, TD.SF.load_settle_file, TD.SF.read_sheets, TD.SF.assert_no_pii,
            TD.SF.rg_cost_totals, TD.LOG, TD.ORIGINALS, TD.api)
    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            TD._get_bytes = lambda b, url: data
            TD.SF.scrub_pii, TD.SF.load_settle_file = fake_scrub, lambda p: SimpleNamespace(rows=[], settle_total=0,
                                                                                             warnings=[])
            TD.SF.read_sheets, TD.SF.assert_no_pii, TD.SF.rg_cost_totals = (lambda p: {}), (lambda s: None), \
                (lambda s, d: {})
            TD.LOG = RLG.RunLog(TD.BASE, echo=lambda m: None)

            def fetch(report="주문상세"):
                ch = "윙" if report == "주문상세" else "로켓그로스"
                j = SJ.Job("홍길동-가나-acc1", ch, "주정산", report, "2026-01-05", "2026-01-11", "2026-01-30")
                if ch == "로켓그로스":
                    TD.api = lambda b, who, m, p, body=None: {"url": "u"}
                TD._fetch_one(None, j, SimpleNamespace(handle="u"), "홍길동-가나-acc1")
                return j
            TD.ORIGINALS = None
            j = fetch()
            assert j.status == SJ.ST_DONE and (TD.FILES / j.file).read_bytes() == b"PK-scrubbed"
            assert not (Path(tmp) / "원본").exists(), "지정 안 하면 원본 폴더 안 만듦(지금 동작)"
            TD.ORIGINALS = Path(tmp) / "원본"
            j = fetch()
            assert (TD.ORIGINALS / j.file).read_bytes() == data, "원본 = 받은 바이트 그대로(구매자명 포함)"
            assert (TD.FILES / j.file).read_bytes() == b"PK-scrubbed", "집계용 사본은 그대로 구매자명 지운 것"
            assert not (TD.BASE / "_받는중" / j.file).exists()
            jc = fetch("보관비")
            name = jc.file.split("/", 1)[1]
            assert (TD.ORIGINALS / name).read_bytes() == data and (TD.COSTS / name).read_bytes() == data
        finally:
            (TD._get_bytes, TD.SF.scrub_pii, TD.SF.load_settle_file, TD.SF.read_sheets, TD.SF.assert_no_pii,
             TD.SF.rg_cost_totals, TD.LOG, TD.ORIGINALS, TD.api) = olds
            os.chdir(old_cwd)
    ok("윙·판매수수료·비용 리포트 원본 바이트 그대로 복사 · 집계 사본(구매자명 제거)·비용 폴더 불변 · 미지정=폴더 없음")


def p36_same_cycle_done():
    print("[P36] 같은 회차에 이미 '완료'면 ① 단계 기록 시각이 바뀌어도(sales→done) 다시 안 받음 — 실측 10-21 08:00 "
          "옛 예약작업이 35계정 재로그인(D-091) · 옛 예약작업 제거 명령")
    import json as _json
    import os
    from datetime import datetime as RealDT, timedelta
    from types import SimpleNamespace
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import settlement_download as TD
    from coupang_analytics import app_process as AP
    from coupang_analytics import settlement_runlog as RLG
    from coupang_analytics import settlement_watch as W
    D = RealDT
    assert "Unregister-ScheduledTask" in AP._LEGACY_WATCH_PS and "watch" in AP._LEGACY_WATCH_PS
    logs: list = []
    old_ps = AP._ps
    try:
        AP._ps = lambda script, env: "R\n"
        assert AP.remove_legacy_settlement_task(logs.append) == 1 and "삭제" in logs[-1], logs
        AP._ps = lambda script, env: ""
        assert AP.remove_legacy_settlement_task(logs.append) == 0
        # D-189: 관리자로 만든 작업은 일반 권한으로 못 지움 → 실패 사유를 그대로 남김('권한' 단정 금지) ·
        # 사람이 켠 실행(elevate)만 관리자 확인 창(UAC)으로 지우고 남은 수를 다시 셈 · 무인은 창을 띄우지 않음
        deny = "F:액세스가 거부되었습니다.\n"
        AP._ps = lambda script, env, timeout=30: deny
        logs.clear()
        assert AP.remove_legacy_settlement_task(logs.append) == 0 and "액세스가 거부" in logs[-1] and "관리자" in logs[-1], logs
        calls: list = []

        def fake(outs):
            def _f(script, env, timeout=30):
                calls.append(("RunAs" in script, timeout))
                return outs.pop(0)
            return _f
        AP._ps = fake([deny, "X0\n", "N0\n"])
        logs.clear()
        assert AP.remove_legacy_settlement_task(logs.append, elevate=True) == 1, logs
        assert calls[1][0] and calls[1][1] >= 120 and not calls[2][0], calls    # 둘째 = 관리자 실행(대기 넉넉히) · 셋째 = 남은 수 확인
        assert any("UAC" in m for m in logs) and "1개 삭제" in logs[-1], logs
        AP._ps = fake([deny, "C:작업을 취소했습니다.\n", "N1\n"])
        logs.clear()
        assert AP.remove_legacy_settlement_task(logs.append, elevate=True) == 0 and "1개 남음" in logs[-1] \
            and "취소" in logs[-1], logs
        app_src = (Path(__file__).resolve().parent.parent / "ui" / "app_qt.py").read_text(encoding="utf-8")
        assert "remove_legacy_settlement_task(pre_logs.append, elevate=True)" in app_src, "사람이 켠 실행에서 제거 안 함"
    finally:
        AP._ps = old_ps

    def run(now, marker_at, done_key):
        clock = {"now": now}
        passes: list = []
        stage = Path("output") / "쿠팡데이타분석_실행단계.json"
        stage.write_text(_json.dumps({"date": f"{marker_at:%Y-%m-%d}", "stage": "done", "at": marker_at.isoformat()}),
                         encoding="utf-8")
        W.write_done(TD.DONE_FILE, done_key, "done", "다 받음")

        class FakeDT(RealDT):
            @classmethod
            def now(cls, tz=None):
                return clock["now"]

        def fake_sleep(sec):
            clock["now"] += timedelta(seconds=max(sec, 1))
        olds = (TD.datetime, TD.time.sleep, TD._one_pass, TD._pending_jobs, TD._retry_count, TD.LOG)
        args = SimpleNamespace(parent=0, ledger_synced=True, until="", until_at=None, hidden=False, since="")   # 대장 반영(D-366 ②) = P69
        try:
            TD.datetime, TD.time.sleep = FakeDT, fake_sleep
            TD._one_pass = lambda a: (passes.append(clock["now"]), (False, 0))[1]
            TD._pending_jobs, TD._retry_count = (lambda: 0), (lambda: 0)
            TD.LOG = RLG.RunLog(TD.BASE, now=clock["now"], echo=lambda m: None)
            TD.LOG.heartbeat = lambda st, msg: None
            TD.cmd_watch(args)
        finally:
            TD.datetime, TD.time.sleep, TD._one_pass, TD._pending_jobs, TD._retry_count, TD.LOG = olds
            stage.unlink(missing_ok=True)
        return passes

    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            (Path(tmp) / "output").mkdir()
            # 실측(10-21 · 18:00 회차 때): ① 완료 기준 '완료' → ③ 끝에 단계 기록이 done 으로 바뀜 → 옛 예약작업이 다시 띄움.
            # 00:10 회차(D-372)로 옮김: 03:00 ① 완료 '완료' → 10:29 ③ 끝(done) → 14:00 다시 떠도 같은 회차 = 안 받음
            assert run(D(2026, 10, 21, 14, 0, 2), D(2026, 10, 21, 10, 29), "2026-10-21T03:00:17") == [], \
                "같은 회차 '완료'인데 단계 기록 시각이 바뀌었다고 다시 받음"
            # 지난 회차의 '완료'는 이번 회차를 막지 않음(다음 날 00:10 이후 ① 완료 → 받음)
            assert run(D(2026, 10, 22, 4, 0), D(2026, 10, 22, 3, 50), "2026-10-21T03:00:17"), "새 회차인데 안 받음"
        finally:
            os.chdir(old_cwd)
    ok("같은 회차 완료 = 단계 기록 시각과 무관하게 종료 · 새 회차는 받음 · 옛 예약작업 제거")


def p35_amounts_from():
    print("[P35] 지급 내역 = 2025-11 부터 기록(2026 첫 30% 줄의 70% 몫·2025 보류 대조) · 받을 파일 계획은 시작일부터만")
    from datetime import date
    from types import SimpleNamespace
    sys.path.insert(0, str(ROOT / "tools"))
    import settlement_download as TD
    seen, saved = [], []
    olds = (TD.goto, TD.api, TD._save_amounts, TD._read_forecast, TD.LOG, TD.time.sleep, TD.CHANNELS, TD._SOURCES)

    def body(ws, we):
        return {"fromDate": ws.isoformat()}

    def parse(resp, name):
        return [SimpleNamespace(settle_date=date.fromisoformat(resp["w"][:8] + "20"), reports=())]

    def api(b, name, m, path, bd):
        seen.append(bd["fromDate"])
        return {"w": bd["fromDate"]}
    try:
        TD.goto, TD._read_forecast, TD.time.sleep = (lambda *a: None), (lambda *a: None), (lambda s: None)
        TD.LOG, TD.CHANNELS = SimpleNamespace(record=lambda *a, **k: None), ()
        TD._SOURCES = (("윙", "url", "path", body, parse),)
        TD._save_amounts = lambda name, ch, resp: saved.append(resp["w"])
        TD.api = api
        evs = TD.read_events(None, "A", date(2026, 1, 1), date(2026, 2, 28), amounts_from=TD.AMOUNTS_FROM)
        plain = TD.read_events(None, "A", date(2026, 1, 1), date(2026, 2, 28))
    finally:
        (TD.goto, TD.api, TD._save_amounts, TD._read_forecast, TD.LOG, TD.time.sleep, TD.CHANNELS, TD._SOURCES) = olds
    assert TD.AMOUNTS_FROM == date(2025, 11, 1)
    assert saved[:4] == ["2025-11-01", "2025-12-01", "2026-01-01", "2026-02-01"], saved      # 2025-11·12 지급 내역 기록
    assert [str(e.settle_date) for e in evs] == ["2026-01-20", "2026-02-20"], evs              # 계획엔 시작일부터만
    assert [str(e.settle_date) for e in plain] == ["2026-01-20", "2026-02-20"] and saved[4:] == ["2026-01-01", "2026-02-01"]
    ok("지급 내역 2025-11 부터 기록·받을 파일 계획(정산 일정)은 시작일부터만 — 2025 일정이 '요청예정'으로 남지 않음·인자 없으면 그대로")


def p34_forecast_accuracy():
    print("[P34] 정산 예정 기록(D-078) — 오늘 뒤 줄은 예정 기록에만·같은 날 다시 보면 마지막 값·정산일 지나면 실제와 칸별 대조")
    from datetime import date
    from coupang_analytics import settlement_forecast as FC
    from coupang_analytics import settlement_stats as ST
    rows = [{"정산일": "2026-10-15", "기간 시작": "2026-09-07", "기간 끝": "2026-09-13", "지급비율": 70, "최종지급액": 75036},
            {"정산일": "2026-10-22", "기간 시작": "2026-09-14", "기간 끝": "2026-09-20", "지급비율": 70, "최종지급액": 1000,
             "totalPayableAmount": 5000, "totalAdSalesDeductionAmount": 4000}]
    past, fut = FC.split_future(rows, date(2026, 10, 16))
    assert [r["정산일"] for r in past] == ["2026-10-15"] and [r["정산일"] for r in fut] == ["2026-10-22"]
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "예정.jsonl"
        # 시계가 같은 값을 돌려줘도(Windows 시계 정밀도 — 10-21 게이트 간헐 실패 실측) 묶음 번호는 계속 커져야 함
        real_ns, FC.time.time_ns = FC.time.time_ns, (lambda: 1_792_590_650_777_422_500)
        try:
            FC.record(f, "A", "로켓그로스", fut, date(2026, 10, 16))
            FC.record(f, "A", "로켓그로스", [{**fut[0], "최종지급액": 1200}], date(2026, 10, 16))   # 같은 날 다시 → 마지막
            FC.record(f, "A", "로켓그로스", [{**fut[0], "최종지급액": 1300}], date(2026, 10, 20))
        finally:
            FC.time.time_ns = real_ns
        fc = FC.load(f)
        assert sorted((r["수집일"], r["최종지급액"]) for r in fc) == [("2026-10-16", 1200), ("2026-10-20", 1300)], fc
        assert FC.accuracy(fc, [], date(2026, 10, 21)) == []                                    # 정산일 전 = 비교 안 함
        actual = [{"계정": "A", "채널": "로켓그로스", **fut[0], "지급비율": 70.0, "최종지급액": 1300}]
        acc = FC.accuracy(fc, actual, date(2026, 10, 22))
        assert [(r["수집일"], r["미리 본 일수"], r["판정"]) for r in acc] == [("2026-10-16", 6, "다름"), ("2026-10-20", 2, "일치")], acc
        assert "최종지급액 +100" in acc[0]["차이(실제−예정)"] and acc[0]["예정 광고비(RG)"] == 4000
        assert FC.accuracy(fc, [], date(2026, 10, 22))[0]["판정"] == "실제 없음"
        summ = FC.summary(acc)
        assert [(s["미리 본 일수"], s["비교 줄"], s["최종지급액 일치"]) for s in summ] == [("0~3일", 1, 1), ("4~7일", 1, 0)], summ
        import openpyxl
        out = ST.write_stats(Path(tmp) / "s.xlsx", ST.aggregate([]), forecast=acc)
        names = openpyxl.load_workbook(out).sheetnames
        assert "예정 정확도" in names and "예정 정확도 요약" in names, names
        # 로켓그로스 정산대상 100% = 판매액 + 환불 − 수수료(VAT 포함) − 판매자할인(쿠팡 칸 그대로 — 실측 737/737, D-080)
        rg = {"정산일": "2026-10-20", "기간 시작": "2026-08-17", "기간 끝": "2026-08-23", "지급비율": 70, "최종지급액": 15421,
              "totalPayableAmount": 15421, "totalSalesAmount": 25000, "totalRefundedAmount": 0,
              "totalTakeRateAmountWithVat": 2970, "totalSellerDiscount": 0}
        f2 = Path(tmp) / "예정2.jsonl"
        FC.record(f2, "B", "로켓그로스", [rg], date(2026, 10, 18))
        kept = FC.load(f2)[0]
        assert FC.rg_target(kept) == 22030 and FC.rg_sales(kept) == 25000, kept           # 정산 파일 정산대상 22,030
        assert FC.rg_target({k: v for k, v in kept.items() if k != "totalSellerDiscount"}) is None   # 칸 없으면 계산 안 함
        # 같은 정산 줄 키가 여러 개(보류 해제 100%) = 한 번 조회의 줄 묶음 전부 · 같은 날 다시 조회하면 마지막 조회 묶음만
        f3 = Path(tmp) / "예정3.jsonl"
        rel = {"정산일": "2026-11-02", "기간 시작": "2026-09-21", "기간 끝": "2026-09-21", "지급비율": 100}
        FC.record(f3, "C", "윙", [{**rel, "최종지급액": 7}, {**rel, "최종지급액": 9}], date(2026, 10, 18))
        assert sorted(r["최종지급액"] for r in FC.load(f3)) == [7, 9]
        FC.record(f3, "C", "윙", [{**rel, "최종지급액": 11}], date(2026, 10, 18))
        assert [r["최종지급액"] for r in FC.load(f3)] == [11]
        # D-243 ③ 달별 파일 — 수집일 달 파일(정산예정기록/YYYY-MM.jsonl)에만 씀 · 지난 달 파일은 다시 안 씀 ·
        #   옛 한 파일은 첫 기록 때 달 파일로 나눈 뒤 보관/YYYY-MM/ 로 이동(삭제 없음) · 달 폴더가 없으면 옛 파일 그대로 읽음(분석 사본)
        import json as _json
        base = Path(tmp) / "정산"
        f4 = base / "정산예정기록.jsonl"
        legacy = [{"수집일": "2026-09-30", "계정": "D", "채널": "윙", "묶음": "1", **rel, "최종지급액": 1},
                  {"수집일": "2026-10-02", "계정": "D", "채널": "윙", "묶음": "2", **rel, "최종지급액": 2},
                  {"수집일": "2026-10-03", "계정": "D", "채널": "윙", **rel, "최종지급액": 3}]          # 묶음 없는 옛 줄
        base.mkdir()
        f4.write_text("".join(_json.dumps(r, ensure_ascii=False) + "\n" for r in legacy), encoding="utf-8")
        want = sorted((r["수집일"], r["최종지급액"]) for r in legacy)
        assert sorted((r["수집일"], r["최종지급액"]) for r in FC.load(f4)) == want                  # 달 폴더 없음 = 옛 파일
        FC.record(f4, "D", "윙", [{**rel, "최종지급액": 4}], date(2026, 11, 5))
        months = base / "정산예정기록"
        assert sorted(p.name for p in months.iterdir()) == ["2026-09.jsonl", "2026-10.jsonl", "2026-11.jsonl"], list(months.iterdir())
        assert not f4.exists() and (base / "보관" / "2026-11" / "정산예정기록.jsonl").is_file(), "옛 파일 = 보관으로 이동(삭제 없음)"
        assert sorted((r["수집일"], r["최종지급액"]) for r in FC.load(f4)) == sorted(want + [("2026-11-05", 4)])
        oct_bytes = (months / "2026-10.jsonl").read_bytes()
        FC.record(f4, "D", "윙", [{**rel, "최종지급액": 5}], date(2026, 11, 6))
        assert (months / "2026-10.jsonl").read_bytes() == oct_bytes, "지난 달 파일은 다시 안 씀"
        assert len((months / "2026-11.jsonl").read_text(encoding="utf-8").splitlines()) == 2
        f4.write_text(_json.dumps(legacy[0], ensure_ascii=False) + "\n", encoding="utf-8")          # 옛 파일이 다시 생김(합치기 등)
        FC.record(f4, "D", "윙", [{**rel, "최종지급액": 6}], date(2026, 11, 7))
        assert len((months / "2026-09.jsonl").read_text(encoding="utf-8").splitlines()) == 1, "같은 줄은 한 번만(중복 없음)"
        assert not f4.exists() and len(list((base / "보관" / "2026-11").glob("정산예정기록*.jsonl"))) == 2
    ok("오늘 뒤 줄만 예정 기록·같은 날 마지막 값·정산일 지나면 칸별 대조(며칠 전 예정)·실제 없음·요약·집계 시트"
       "·로켓그로스 정산대상 칸 저장(판매액+환불−수수료−할인)·달별 파일(옛 파일 변환·보관 이동 D-243 ③)")


def p33_login_password_source():
    print("[P33] 정산 로그인 비밀번호 = 앱과 같은 관리대장 값 먼저(소유자 2026-10-16) · 대장에 없는 계정만 정산 계정 파일 · 값이 다르면 둘 다(최대 2·D-012)")
    from coupang_analytics import settlement_accounts as SA

    class Store:
        def __init__(self, d):
            self.d = d

        def get_password(self, aid):
            return self.d.get(aid)
    st = Store({"same": "pw-a", "diff": "pw-new", "only": "pw-l"})
    acc = lambda aid, pw: SA.SettleAccount(aid, f"대표-사업자-{aid}", pw)   # noqa: E731
    assert SA.login_passwords(acc("same", "pw-a"), st) == (["pw-a"], "관리대장")
    pws, note = SA.login_passwords(acc("diff", "pw-old"), st)
    assert pws == ["pw-new", "pw-old"] and "다름" in note, (pws, note)                       # 대장 값 먼저
    assert SA.login_passwords(acc("only", ""), st) == (["pw-l"], "관리대장")                    # 계정 파일 비번 빈 칸
    pws, note = SA.login_passwords(acc("nofile", "pw-f"), st)
    assert pws == ["pw-f"] and "관리대장에 없음" in note, note                                   # 대장에 없는 계정(디프 등)
    assert SA.login_passwords(acc("none", ""), st) == ([], "비밀번호 없음")
    assert "pw" not in note                                                                   # 값은 설명에 안 씀
    # D-123: 원장 비밀번호는 대장 원문(앞뒤 공백 포함) — 앱 ①처럼 공백 떼고 비교·입력(실측 dalbong1849 정산만 거부)
    assert SA.login_passwords(acc("diff", " pw-new  "), st) == (["pw-new"], "관리대장"), "공백만 다르면 같은 값 1개"
    assert SA.login_passwords(acc("nofile", " pw-f "), st)[0] == ["pw-f"], "원장 값 앞뒤 공백 뗌"
    assert "원장" in SA.login_passwords(acc("diff", "pw-old"), st)[1], "설명 = 원장(옛 '계정 파일' 문구 아님)"
    # D-190: 대장 줄마다 값이 다른 계정의 값2 도 정산 후보(실측 wavetech — 앱은 값2 로 성공·정산은 값1 만 알아 거부 반복)
    #   순서 = 대장 값1 → 원장 값 → 대장 값2 · 최대 2(D-012) → 원장이 값1 과 같거나 비면 값2 가 둘째(옛 동작은 그대로)
    st2 = Store({"wt": "pw-1", SA.alt_key("wt"): "pw-2", "db": "pw-1", SA.alt_key("db"): "pw-2"})
    pws, note = SA.login_passwords(acc("wt", "pw-1"), st2)
    assert pws == ["pw-1", "pw-2"] and "값2" in note and "pw" not in note, (pws, note)
    assert SA.login_passwords(acc("wt", ""), st2)[0] == ["pw-1", "pw-2"], "원장 빈 칸"
    pws, note = SA.login_passwords(acc("db", "pw-l"), st2)
    assert pws == ["pw-1", "pw-l"] and "원장" in note, (pws, note)            # 원장이 다르면 지금처럼 원장이 둘째(dalbong1849)
    assert SA.login_passwords(acc("db", "pw-2"), st2)[0] == ["pw-1", "pw-2"], "원장 = 값2 → 같은 값 1개"

    class WStore(Store):
        def set_password(self, aid, pw):
            self.d[aid] = pw
    from types import SimpleNamespace as Cand
    ws = WStore({SA.alt_key("one"): "old-2"})
    SA.save_ledger_alternates(ws, {"two": [Cand(password="a"), Cand(password=" b ")], "one": [Cand(password="a")],
                                   "single": [Cand(password="c")]})
    assert ws.d[SA.alt_key("two")] == "b" and ws.d[SA.alt_key("one")] == "" and SA.alt_key("single") not in ws.d, ws.d
    from coupang_analytics.credstore import CredStore                 # 실제 이 PC 암호 저장소(DPAPI)·한글 키 왕복
    with tempfile.TemporaryDirectory() as tmp:
        cs = CredStore(Path(tmp) / "creds.json")
        cs.set_password("wt", "pw-1")
        SA.save_ledger_alternates(cs, {"wt": [Cand(password="pw-1"), Cand(password="pw-2")]})
        assert SA.login_passwords(acc("wt", "pw-1"), CredStore(Path(tmp) / "creds.json"))[0] == ["pw-1", "pw-2"]
    ok("관리대장 값 우선·다르면 대장→원장 순서(최대 2)·대장에 없는 계정은 원장 값·앞뒤 공백 뗌·값 노출 없음"
       " · 대장 값2 = 원장이 값1 과 같거나 빌 때 둘째(D-190)")


def p32_evidence_rules():
    print("[P32] 증빙 원본 전체 받기(D-067) — 사업자 폴더·월 구간·정산 줄 없는 주·판매분석 누락 검사·환급 이름·완료 표시")
    import json
    from coupang_analytics import settlement_evidence as EV
    assert EV.business_of("한상현-니코에이블-nicoable") == "니코에이블"
    assert EV.business_of("김현창-주식회사-로움-kimhc") == "주식회사-로움"          # 사업자 이름 안의 '-' 보존
    assert EV.business_of("aehee5505") == "aehee5505"                               # 이름 없는 계정 = 계정ID
    assert EV.account_folder(Path("X"), "서달원-(DW)커머스-dalbong1849") == Path("X") / "증빙_(DW)커머스_쿠팡원본"
    assert EV.month_windows(date(2026, 4, 15), date(2026, 6, 3)) == [
        ("202604", date(2026, 4, 15), date(2026, 4, 30)), ("202605", date(2026, 5, 1), date(2026, 5, 31)),
        ("202606", date(2026, 6, 1), date(2026, 6, 3))]
    det = lambda s, e: {"cfsDeductionDetails": [{"settlementPeriodStartDate": s, "settlementPeriodEndDate": e,  # noqa: E731
                                                 "lastSettlementUnpaidCfsDeductionAmount": 13200.0}]}
    reports = [{"settlementGroupKey": "A01684473-2026-05-25-2026-05-31",            # 실측 니코에이블: 5/11~17 주 = 정산 줄 없음
                "settlementStatusReportDetail": det("2026-05-10T15:00:00Z", "2026-05-16T15:00:00Z")},
               {"settlementGroupKey": "A01684473-2026-08-03-2026-08-09",            # 미납 CFS 가 정산 줄 있는 주 → 대상 아님
                "settlementStatusReportDetail": det("2026-07-12T15:00:00Z", "2026-07-18T15:00:00Z")},
               {"settlementGroupKey": "A01684473-2026-07-13-2026-07-19", "settlementStatusReportDetail": {}}]
    assert EV.missing_cost_weeks(reports) == ["A01684473-2026-05-11-2026-05-17"], EV.missing_cost_weeks(reports)
    head = ["날짜", "판매량", "매출(원)"]
    daily = [head, ["2026-05-01", 1, 100], ["2026-05-02", 2, 300], ["", 3, 400]]
    assert EV.check_daily(daily, date(2026, 5, 1), date(2026, 5, 2))[:2] == (True, "2일 전부")
    assert not EV.check_daily(daily[:2] + daily[3:], date(2026, 5, 1), date(2026, 5, 2))[0]   # 하루 빠짐
    assert EV.check_items([["상품", "판매량", "매출(원)"], ["a", 3, 400]], 3, 400)[0]
    assert not EV.check_items([["상품", "판매량", "매출(원)"], ["a", 2, 400]], 3, 400)[0]
    items = json.dumps([{"key": "지급일", "value": "2026-09-01 ~ 2026-09-30"}], ensure_ascii=False)
    assert EV.refund_file_name(items, "2026-10-15 12:11:05") == "쿠팡_우대수수료환급_2026-09-01-2026-09-30.xlsx"
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "증빙_x_쿠팡원본"
        (f / EV.MENU).mkdir(parents=True)
        (f / EV.MENU / "쿠팡_a.pdf").write_bytes(b"%PDF")
        (f / EV.MENU / "~$잠금.xlsx").write_bytes(b"x")
        (f / EV.MENU / "_실패화면.png").write_bytes(b"x")
        assert not EV.write_results(f, {"a": {"결과": EV.OK}, "b": {"결과": EV.FAIL}}) and not (f / EV.DONE).exists()
        assert EV.write_results(f, {"a": {"결과": EV.OK}, "b": {"결과": EV.NONE}}) and (f / EV.DONE).exists()
        assert EV.previous_steps(f) == {"a": {"결과": EV.OK}, "b": {"결과": EV.NONE}}          # 이어받기: 정상/없음 단계만
        EV.write_results(f, {"a": {"결과": EV.OK}, "b": {"결과": EV.FAIL}})
        assert list(EV.previous_steps(f)) == ["a"] and EV.previous_steps(Path(tmp) / "없음") == {}
        rows = (f / EV.LISTING).read_text(encoding="utf-8-sig").splitlines()
        assert len(rows) == 2 and "쿠팡_a.pdf" in rows[1]                               # 잠금·작업 파일 제외
    ok("사업자 폴더('-' 보존)·월 구간·정산 줄 없는 주(니코에이블 5/11~17)·누락 검사·환급 이름·완료 표시·목록 제외 규칙")


def p37_accounts_from_registry():
    print("[P37] 정산 계정 = 원장(셀독원장 한 번이라도 관리한 계정 − 오입력 + 정산전용계정) · 기간 제한 없음(D-211) · 동기화 오래되면 중단(D-103)")
    from datetime import datetime as D
    from coupang_analytics import registry as R, registry_model as M, registry_settle as RS
    from coupang_analytics import settlement_accounts as SA

    def snap(accts):
        hdr = ["구분", "대표자명", "사업자명", "계정아이디", "비밀번호", "상품명"]
        rows = [["예시"], hdr] + [["", rep, biz, aid, pw, "상품"] for aid, rep, biz, pw in accts]
        return M.parse_ledger(rows, None, "셀독리스트")
    reg = R.Registry()
    R.sync(reg, snap([("keep1", "대표", "가게1", "pw1"), ("old1", "대표", "옛가게", "pw2"), ("rec1", "대표", "최근가게", "pw3")]),
           now=D(2026, 6, 1, 18))
    R.sync(reg, snap([("keep1", "대표", "가게1", "pw1"), ("rec1", "대표", "최근가게", "pw3")]), now=D(2026, 7, 1, 18))   # old1 중단
    R.sync(reg, snap([("keep1", "대표", "가게1", "pw1b")]), now=D(2026, 10, 11, 18))                                   # rec1 중단·비번 변경
    settle, _w = RS.parse_settle([list(RS.SETTLE_HEADER),
                                  ["관리중", "2026-10-21", "", "우리사업자", "임", "디프", "own1", "pwO", ""],
                                  ["관리중단", "2026-01-01", "2026-05-01", "위탁", "김", "끝난곳", "gone1", "pwG", ""],
                                  ["관리중", "", "", "위탁", "박", "중복", "keep1", "pwX", ""]])
    now = D(2026, 10, 21, 19)
    accts, info = SA.accounts_from_registry(reg, settle, "2026-10-21 18:00:30", now)
    got = {a.account_id: (a.label, a.password) for a in accts}
    assert set(got) == {"keep1", "rec1", "old1", "own1", "gone1"}, got    # 중단 112일(old1)·173일(gone1)도 포함(D-211 기간 제한 없음)
    assert got["keep1"] == ("대표-가게1", "pw1b") and got["own1"] == ("임-디프", "pwO"), got   # 원장 최신 비번·정산전용 값
    assert info["중복(셀독원장 우선)"] == ["keep1"] and info["정산전용"] == 2, info
    for last, why in (("2026-10-20 08:00:00", "오래됨"), ("", "기록 없음")):
        try:
            SA.accounts_from_registry(reg, settle, last, now)
        except SA.AccountSourceError:
            pass
        else:
            raise AssertionError(f"동기화 {why}인데 통과")
    ok("관리중·관리중단(기간 무관) 포함·정산전용 관리중·관리중단 포함·중복=원장 우선·최신 비번·동기화 오래됨/없음=중단")


def p38_wing_extra_settlement():
    print("[P38] 윙 정산주기 'B' = 추가정산 — 받기 방법 미확인 → 그 줄만 건너뛰고 '확인 필요' · 다른 주기는 계속 받음")
    from datetime import date as D
    from coupang_analytics import settlement_wing_api as API
    # 실측(운용 PC 10-22~10-25 매 실행): roum0502 일정 '[추가정산] 10/20 ~ 10/20' · 지급일 10-22 · 코드 'B'
    #   → SiteChangedError 로 계정 전체 실패(그 계정 다른 주정산까지 못 받음).
    week = {"payDate": "2026-10-20", "transactionCycleCode": "W", "recognitionFrom": "2026-09-21",
            "recognitionTo": "2026-09-27", "paymentStatus": "DONE", "ratio": 70}
    extra = {"payDate": "2026-10-22", "transactionCycleCode": "B", "recognitionFrom": "2026-10-20",
             "recognitionTo": "2026-10-20", "title": "[추가정산]\n10/20 ~ 10/20"}
    resp = {"paymentReports": [week, extra]}
    ev = API.wing_events(resp, "로움")
    assert [(e.kind, e.settle_date, e.period_start) for e in ev] == [("주정산", D(2026, 10, 20), D(2026, 9, 21))], ev
    notes = API.unsupported_cycles(resp)
    assert len(notes) == 1 and "추가정산" in notes[0] and "'B'" in notes[0] and "2026-10-20" in notes[0], notes
    expect(API.SiteChangedError, lambda: API.wing_events(
        {"paymentReports": [week, {**extra, "transactionCycleCode": "X"}]}, "a"), "다른 모르는 코드는 여전히 중단")
    ok("추가정산(B) 줄만 건너뜀·'확인 필요' 기록 문구·주정산은 그대로·다른 모르는 코드는 중단")


def p39_favorable_refund():
    print("[P39] 우대수수료 환급 주문별(D-116 ③②) — 매일 검증 자료에 결제/취소일 달마다·쪽 끝까지·필요한 칸만")
    from coupang_analytics import settlement_verify_collect as VC
    from coupang_analytics import settlement_wing_api as API
    # 실측(벅스 2026-10-26): 화면 조회 = GET …/favorablefee/refund/list/data?page&pageSize&from&to&dateType · 한 달 넘으면 400 ·
    # pageSize=500 → 9월 67건 한 번 · 줄 칸 = orderId·transactionDate(Str)·expected/realTransferDate(Str)·refundAmount·
    # companyScale·transferStatus·taxBillIssueTarget + 매 줄 localeProperty(큰 번역표 — 저장 안 함).
    row = {"orderId": 7102282429642, "transactionDate": 1788188400000, "transactionDateStr": "2026-09-01",
           "expectedTransferDate": 1789570800000, "expectedTransferDateStr": "2026-09-17", "realTransferDate": None,
           "realTransferDateStr": None, "refundAmount": -226, "refundAmountStr": "-226", "companyScale": "THREE",
           "companyScaleStr": "중소3", "transferStatus": "TRANSFER_WAIT", "transferStatusStr": "지급 대기",
           "taxBillIssueTarget": True, "taxBillIssueTargetStr": "Y", "localeProperty": {"big": "x" * 50}}
    gets: list = []

    def call(method, path, body):
        if path.startswith(VC.FAVORABLE):
            q = dict(x.split("=", 1) for x in path.split("?", 1)[1].split("&"))
            gets.append((method, q))
            if q["from"] == "2026-08-01":
                raise API.ServerBusy("504")
            if q["from"] == "2026-09-01":
                return {"dtos": [{**row, "orderId": int(q["page"])}], "totalCount": 2, "totalPage": 2, "page": int(q["page"])}
            return {"dtos": [], "totalCount": 0, "totalPage": 0, "page": 1}
        return {}
    d = VC.collect(call, lambda url: None, D("2026-08-01"), D("2026-10-08"))
    fav = d["favorable"]
    assert set(fav) == {"202608", "202609", "202610"} and fav["202608"] is None, fav
    assert any("우대수수료 환급 202608" in x for x in d["조회 실패"]), d["조회 실패"]
    assert fav["202610"] == {"totalCount": 0, "rows": []}
    assert fav["202609"]["totalCount"] == 2 and [r["orderId"] for r in fav["202609"]["rows"]] == [1, 2]   # 2쪽 끝까지
    assert fav["202609"]["rows"][0] == {"orderId": 1, "transactionDateStr": "2026-09-01", "expectedTransferDateStr": "2026-09-17",
                                        "realTransferDateStr": None, "refundAmount": -226, "companyScale": "THREE",
                                        "transferStatus": "TRANSFER_WAIT", "taxBillIssueTarget": True}
    q10 = [q for m, q in gets if q["from"] == "2026-10-01"][0]
    assert q10["to"] == "2026-10-07" and q10["dateType"] == "TRANSACTION" and q10["pageSize"] == "500"   # 한 달·어제까지
    assert all(m == "GET" for m, _ in gets) and len(gets) == 4, gets              # 8월 실패 1·9월 2쪽·10월 1
    ok("결제/취소일 달마다 GET·pageSize 500·어제까지·2쪽 끝까지·localeProperty/Str 칸 버림·504 달=조회 실패 기록 후 계속")


def p40_orphan_ship_returns():
    print("[P40] 상품 없는 윙 배송비 줄(D-116 ③③) → 그 주문의 반품 정보(주문조회 반품)만 조회·개인정보 없는 칸만 누적 저장")
    from coupang_analytics import settlement_files as SF
    from coupang_analytics import settlement_verify_collect as VC
    from coupang_analytics import settlement_wing_api as API

    def r(order, pid, opt, sales):
        return SF.SettleRow("윙", "벅스-bux1004", D("2026-08-01"), D("2026-08-31"), order, pid, opt, "", "", 0, sales, 0, 0,
                            sales, D("2026-08-06"), "")
    f1 = SF.SettleFile("윙", "벅스-bux1004", D("2026-08-01"), D("2026-08-31"),
                       rows=[r("16102026647963", "", "<기본배송료>", 6000),      # 실측: 상품 줄 없음 = 반품 왕복배송비
                             r("200", "", "<기본배송료>", 3000), r("300", "", "<기본배송료>", 0), r("400", "", "<기본배송료>", 3000)])
    f2 = SF.SettleFile("윙", "벅스-bux1004", D("2026-07-01"), D("2026-07-31"),
                       rows=[r("200", "8976534411", "95425233537", 37900)])           # 다른 파일에 상품 줄 = 정상 배송비
    assert VC.orphan_ship_orders([f1, f2]) == ["16102026647963", "400"]            # 금액 0 줄 제외
    old = {"16102026647963": [{"cancelId": 1}], "400": None}
    assert VC.returns_to_ask(["16102026647963", "400", "500"], old) == ["400", "500"]   # 조회 실패(None)·새 주문만
    # 실측 응답(벅스 2026-10-26, 개인정보 칸은 가짜 값): GET /tenants/sfl-portal/return/delivery/{주문번호} — 다른 화면에서도 됨 ·
    # 없는 주문 = 200 빈 본문
    rec = {"cancelId": 1832692324, "orderId": 16102026647963, "amount": 37900, "memberName": "홍길동", "receiverName": "홍길동",
           "receiverPhoneNumber": "010", "returnAddress": "주소", "receiptDate": "2026-08-04T07:22:12.000+00:00",
           "returnDate": "2026-08-06T04:15:40.000+00:00", "returnStatus": "REFUND_COMPLETED", "requestSolution": "RETURN_REFUND",
           "reasonCode": "REORDER", "reasonCodeName": "상품을 추가하여 재주문", "reasonUserText": "고객이 쓴 글", "faultType": "CUSTOMER",
           "returnDeliveryPriceBurden": "고객", "deliveryChargeType": "FREE", "returnDeliveryPrice": 3000,
           "estimatedRefundPrice": 31900, "cancelCountSum": 1, "productShipmentType": "THIRD_PARTY",
           "omsSimpleOrderItemDtos": [{"vendorItemName": "무선 진공 압축 포장기, J0058", "vendorItemId": 95425233537,
                                       "vendorId": "A01263988", "unitPrice": 37900, "price": 37900, "quantity": 1,
                                       "paymentId": 16100315998115, "csCancelQuantity": 0, "cancelQuantity": 1}]}
    gets: list = []

    def call(method, path, body):
        gets.append((method, path))
        oid = path.rsplit("/", 1)[-1]
        if path.startswith(VC.RETURN_DELIVERY) and oid == "16102026647963":
            return [rec]
        if oid == "400":
            raise API.SiteChangedError(f"{path} 응답이 JSON 아님: ''")
        if oid == "500":
            raise API.ServerBusy("504")
        return {}
    d = VC.collect(call, lambda url: None, D("2026-08-01"), D("2026-08-03"), orders=["16102026647963", "400", "500"])
    got = d["returns"]
    assert [p for m, p in gets if VC.RETURN_DELIVERY in p] == [f"{VC.RETURN_DELIVERY}/{o}" for o in ("16102026647963", "400", "500")]
    assert got["400"] == [] and got["500"] is None and any("반품 조회 500" in x for x in d["조회 실패"]), got
    x = got["16102026647963"][0]
    assert x["items"] == [{"vendorItemId": 95425233537, "vendorItemName": "무선 진공 압축 포장기, J0058", "unitPrice": 37900,
                           "price": 37900, "quantity": 1, "cancelQuantity": 1}], x
    assert x["returnDate"].startswith("2026-08-06") and x["returnDeliveryPriceBurden"] == "고객" and x["returnDeliveryPrice"] == 3000
    assert "홍길동" not in str(got) and "010" not in str(got) and "주소" not in str(got) and "고객이 쓴 글" not in str(got)
    assert "returns" not in VC.collect(lambda *a: {}, lambda url: None, D("2026-08-01"), D("2026-08-03"))   # 주문 없으면 안 부름
    ok("상품 없는 배송비 주문만(금액 0·다른 파일 상품 줄 제외)·새/실패 주문만 조회·개인정보·고객 글 안 남김·빈 본문=반품 없음·504=조회 실패")


def p41_ad_reports():
    print("[P41] 광고비 원천 월별(D-116 ③④) — 끝난 달(+3일)만 · 윙 로켓그로스 광고비 내역 엑셀 + 매출 성장 광고 보고서(요청→다음에 받기)")
    import json
    import re
    import tempfile
    from pathlib import Path
    from coupang_analytics import settlement_ads as AD
    assert [m[0] for m in AD.due_months(D("2026-06-15"), D("2026-08-03"))] == ["202606"]       # 7월은 8/4 부터
    assert [m[0] for m in AD.due_months(D("2026-06-15"), D("2026-08-04"))] == ["202606", "202607"]
    assert AD.due_months(D("2026-06-15"), D("2026-08-04"))[0][1:] == (D("2026-06-01"), D("2026-06-30"))   # 달 전체
    # 실측(벅스 2026-10-26): reportList 줄 = id·startDate·endDate(YYYYMMDD 정수)·dateGroup 'daily'·granularity 'keyword'·
    # campaignCount·status(inprogress|completed|error)
    rep = {"id": "14900611", "startDate": 20260701, "endDate": 20260731, "dateGroup": "daily", "granularity": "keyword",
           "campaignCount": 2, "status": "completed"}
    assert AD.pick_report([rep, {**rep, "id": "9", "campaignCount": 1}], "202607", 2)["id"] == "14900611"
    assert AD.pick_report([{**rep, "id": "15000000", "status": "error"}, rep], "202607", 2)["id"] == "14900611"  # 실패 건 무시
    assert AD.pick_report([{**rep, "granularity": "campaign"}], "202607", 2) is None
    calls: list = []
    daily: list = []                                  # getDailySettlement (startDate, endDate)
    store: dict = {"reports": [], "campaigns": {"202606": [], "202607": [{"id": "105108858", "name": "07-12 보냉백 3종"},
                                                                         {"id": "1", "name": "b"}]}}

    def call(method, path, body):
        calls.append(body["query"].split("(")[0].split()[-1] if "query" in body else "?")
        q = body["query"]
        if "getDailySettlement" in q:                 # 실측(벅스 7월): 날짜×캠페인 청구가능 — 7/12 소진 30,150 → 일예산 초과 차감 30,000
            v = body["variables"]
            daily.append((v["startDate"], v["endDate"]))
            assert v["settlementDomain"] == "SELLER", v
            items = [{"date": 20260712, "campaignId": "105108858", "campaignName": "07-12 보냉백 3종", "deliveredAdcost": 30150,
                      "deliveredAdcostAfterCap": 30000, "billableAmount": 30000}] if v["startDate"] == 20260701 else []
            d = {"summary": {"total": {"billableAmount": 30000 if items else 0}}, "items": items}
            if "subtotals" in q:                      # 실측(광고센터 화면 2026-11-17): 날짜×배송유형 부가세·청구금액 — 고른 칸만 옴
                d["subtotals"] = {"rocketGrowth": [{"date": 20260712, "domain": "ROCKETGROWTH", "billableAmount": 30000, "vat": 3000,
                                                    "totalFinalAmount": 33000, "taxCode": "B0"}] if items else None,
                                  "nonRod": None, "rod": None}
            return {"data": {"getDailySettlement": d}}
        if "getCampaignList" in q:
            return {"data": {"getCampaignList": store["campaigns"][str(body["variables"]["startDate"])[:6]]}}
        if "reportList" in q:
            return {"data": {"reportList": {"reports": store["reports"]}}}
        if "requestReport" in q:
            store["asked"] = body["variables"]
            return {"data": {"requestReport": {"id": "1"}}}
        raise AssertionError(q)
    got: list = []

    def get_bytes(url):
        got.append(url)
        return b"PK-" + url.encode()
    with tempfile.TemporaryDirectory() as d:
        folder = Path(d)
        s1 = AD.collect(call, get_bytes, folder, "벅스-bux1004", D("2026-06-10"), D("2026-08-04"))
        v = store["asked"]
        assert v == {"startDate": 20260701, "endDate": 20260731, "campaignIds": ["105108858", "1"], "reportType": "pa",
                     "dateGroup": "daily", "granularity": "keyword", "excludeIfNoClickCount": False}, v
        assert got == [AD.MILK_EXCEL.format(y=2026, m=m) for m in (7, 6)], got                       # 밀크런 내역은 바로(최근 달부터)
        settle = json.loads((folder / "벅스-bux1004_광고정산_202607.json").read_text(encoding="utf-8"))
        assert settle["items"][0]["billableAmount"] == 30000 and settle["items"][0]["date"] == 20260712, settle
        assert json.loads((folder / "벅스-bux1004_광고정산_202606.json").read_text(encoding="utf-8"))["items"] == []
        # T-82: 일별 배송유형·부가세·청구금액(+VAT) = 같은 요청 subtotals 를 그대로 저장 · 칸 이름은 화면 질의에 있는 것만(짐작 금지)
        assert settle["subtotals"]["rocketGrowth"] == [{"date": 20260712, "domain": "ROCKETGROWTH", "billableAmount": 30000,
                                                        "vat": 3000, "totalFinalAmount": 33000, "taxCode": "B0"}], settle
        assert settle["summary"]["total"]["billableAmount"] == 30000, settle                     # 기존 월 합 그대로
        screen = set(re.findall(r"[A-Za-z_]+", AD_SCREEN_QUERY))
        assert set(re.findall(r"[A-Za-z_]+", AD._DAILY)) <= screen, set(re.findall(r"[A-Za-z_]+", AD._DAILY)) - screen
        for dom in ("rocketGrowth", "nonRod", "rod"):
            assert re.search(dom + r" \{ date domain [^}]*billableAmount [^}]*vat totalFinalAmount taxCode", AD._DAILY), dom
        assert (folder / "벅스-bux1004_밀크런_202606.xlsx").exists()
        assert s1["요청"] == ["202607"] and s1["캠페인 없음"] == ["202606"], s1
        st = json.loads((folder / "벅스-bux1004_광고.json").read_text(encoding="utf-8"))
        assert st["캠페인 없음"] == ["202606"]
        store["reports"] = [{**rep, "status": "inprogress"}]
        got.clear()
        calls.clear()
        daily.clear()
        s2 = AD.collect(call, get_bytes, folder, "벅스-bux1004", D("2026-06-10"), D("2026-08-05"))
        assert s2["기다림"] == ["202607"] and got == [] and "requestReport" not in str(calls), (s2, calls)   # 6월 다시 안 물음
        assert daily == [(20260801, 20260804)], daily          # 받은 정산내역 다시 안 받음 · 끝나지 않은 8월만 1일~어제(T-78 S2)
        store["reports"] = [rep]
        s3 = AD.collect(call, get_bytes, folder, "벅스-bux1004", D("2026-06-10"), D("2026-08-06"))
        assert s3["받음"] == ["202607"] and got == [AD.PA_EXCEL.format(id="14900611")], (s3, got)
        assert (folder / "벅스-bux1004_매출성장광고_202607.xlsx").exists()
        got.clear()
        calls.clear()
        daily.clear()
        s4 = AD.collect(call, get_bytes, folder, "벅스-bux1004", D("2026-06-10"), D("2026-08-07"))
        assert calls == ["DailySettlement"] and got == [] and not s4["받을 것"], (calls, got, s4)    # 끝난 달은 다 받음 →
        assert daily == [(20260801, 20260806)] and s4["진행 달"] == ["202608"], (daily, s4)        # 진행 달 일별만(T-78 S2 · D-291 ⑥)
        assert not (folder / "벅스-bux1004_광고정산_202608.json").exists()                          # 끝난 달 이름과 섞지 않음
    ok("끝난 달+3일·광고비·밀크런 내역 엑셀 바로·캠페인 전부로 보고서 요청·진행 중=기다림·완료=받기·캠페인 없는 달 기록·다 받으면 진행 달 일별만")


def p42_inbound():
    print("[P42] 로켓그로스 입고 내역(D-116 ③⑤) — 밀크런번호·상품별 요청/적치 수량 · 쪽 끝까지 · 필요한 칸만")
    from coupang_analytics import settlement_verify_collect as VC
    # 실측(벅스 2026-10-26): GET /tenants/rfm-inbound/data/inbound/search?pagingSize&pageIndex(0부터) → content[34]·pagination
    # {currentPage,totalPages,totalElements} · milkrunSeq = 밀크런 엑셀 '밀크런번호'(11322007 = 10/14) · 실제 입고 = stowedQty
    # (receivedQty 0) · shipmentId 는 19자리(JS 숫자 범위 밖 → 파이썬 json 그대로 정수).
    ship = {"shipmentId": 1113306920199917568, "milkrunSeq": "11322007", "shipmentType": "MILKRUN_PALLET",
            "createdAt": 1791000000000, "fcCode": "INC4", "updatedBy": "bux1004", "truckShipmentInfo": {"driver": "x"},
            "milkrunShipmentInfo": {"pickupDateYYYYMMDD": "20261014", "milkrunSeq": "11322007", "weight": 150},
            "latestShipmentStatus": {"statusId": "STOWED", "shipmentCancelled": False, "internalLifecycleStatus": "DONE",
                                     "updatedBy": "System"},
            "skuDetails": [{"receivedQty": 0, "stowedQty": 124, "plannedSku": {"vendorItemId": 95501572184, "requestedQty": 124,
                                                                             "cachedSkuName": "보냉백", "barcode": "88"}}]}
    seen: list = []

    def call(method, path, body):
        if path.startswith(VC.INBOUND):
            q = dict(x.split("=", 1) for x in path.split("?", 1)[1].split("&"))
            seen.append(q["pageIndex"])
            return {"content": [{**ship, "shipmentId": int(q["pageIndex"])}], "pagination": {"currentPage": int(q["pageIndex"]),
                                                                                            "totalPages": 2, "totalElements": 2}}
        return {}
    d = VC.collect(call, lambda url: None, D("2026-08-01"), D("2026-08-03"))
    ib = d["inbound"]
    assert seen == ["0", "1"] and [x["shipmentId"] for x in ib] == [0, 1], (seen, ib)
    assert ib[0] == {"shipmentId": 0, "milkrunSeq": "11322007", "shipmentType": "MILKRUN_PALLET", "createdAt": 1791000000000,
                     "fcCode": "INC4", "pickupDate": "20261014", "statusId": "STOWED", "cancelled": False,
                     "skus": [{"vendorItemId": 95501572184, "skuName": "보냉백", "requestedQty": 124, "receivedQty": 0,
                               "stowedQty": 124}]}, ib[0]
    ok("밀크런번호·픽업일·상태·상품(옵션ID·요청/입고/적치 수량)만 · 0쪽부터 끝까지")


def p43_collect_throttle_isolation():
    print("[P43] 운용 PC 설치 전 보완(D-120) — 광고비 하루 받는 달 수 상한·요청 사이 쉼 / 검증 새 항목 예상 못 한 오류 = 그 항목만 조회 실패")
    import tempfile
    from pathlib import Path
    from coupang_analytics import settlement_ads as AD
    from coupang_analytics import settlement_verify_collect as VC
    # ① 9개월 밀린 계정: 첫날 최근 2개월만·원격 요청마다 gap(쉼) 먼저
    log: list = []

    def call(method, path, body):
        log.append("call")
        q = body["query"]
        if "getDailySettlement" in q:
            return {"data": {"getDailySettlement": {"summary": {}, "items": []}}}
        if "getCampaignList" in q:
            return {"data": {"getCampaignList": []}}
        raise AssertionError(q)

    def get_bytes(url):
        log.append("get")
        return b"PK"
    with tempfile.TemporaryDirectory() as d:
        s = AD.collect(call, get_bytes, Path(d), "a-x", D("2026-01-01"), D("2026-10-26"), gap=lambda: log.append("gap"))
        assert s["캠페인 없음"] == ["202609", "202608"] and s["남은 달"] == 7, s                        # 9개월 중 최근 2개월
        assert log and all(log[i] == "gap" for i in range(0, len(log), 2)) and log.count("gap") == len(log) // 2, log
        log.clear()
        s = AD.collect(call, get_bytes, Path(d), "a-x", D("2026-01-01"), D("2026-10-27"), gap=lambda: log.append("gap"))
        assert s["캠페인 없음"] == ["202607", "202606"] and s["남은 달"] == 5, s                        # 다음 날 그다음 2개월
    # ② 새 항목(환급·입고·반품)에서 예상 못 한 오류(시간 초과·응답 모양) = 그 항목만 '조회 실패' · 차단(fatal)은 그대로 올라감
    from coupang_analytics import settlement_wing_api as API

    class Blocked(Exception):
        pass

    def call2(method, path, body):
        if path.startswith(VC.FAVORABLE):
            raise TimeoutError("시간 초과")
        if path.startswith(VC.INBOUND):
            return {"content": None, "pagination": "모양 다름"}      # AttributeError 유발
        if path.startswith(VC.RETURN_DELIVERY):
            raise KeyError("x")
        return {}
    dd = VC.collect(call2, lambda url: None, D("2026-09-01"), D("2026-10-03"), orders=["1"], fatal=(Blocked,))
    assert dd["favorable"] == {"202609": None, "202610": None} and dd["inbound"] is None and dd["returns"] == {"1": None}, dd
    assert sum(("우대수수료 환급" in x) + ("입고 내역" in x) + ("반품 조회" in x) for x in dd["조회 실패"]) == 4, dd["조회 실패"]
    assert dd["additional"] == {"202609": {}, "202610": {}}                                           # 다른 항목은 계속 조회

    def call3(method, path, body):
        if path.startswith(VC.FAVORABLE):
            raise Blocked("차단")
        return {}
    expect(Blocked, lambda: VC.collect(call3, lambda url: None, D("2026-09-01"), D("2026-10-03"), fatal=(Blocked,)),
           "차단은 삼키지 않음")
    expect(API.ApiBlocked, lambda: VC.collect(lambda m, p, b: (_ for _ in ()).throw(API.ApiBlocked("x"))
                                              if p.startswith(VC.FAVORABLE) else {}, lambda url: None,
                                              D("2026-09-01"), D("2026-10-03")), "기본 fatal = ApiBlocked")
    ok("광고 9개월 → 하루 최근 2개월·요청마다 쉼 / 환급·입고·반품 예상 밖 오류 = 그 항목만 조회 실패·차단은 중단")


def p44_adcenter_navigation():
    print("[P44] 광고센터 새 창 이동 중 evaluate(운용 PC 10-27 43계정 실패) — 최종 주소까지 기다리고 '실행 맥락 사라짐'은 쉬고 다시(상한)")
    from playwright.sync_api import Error as PwError
    from coupang_analytics import settlement_evidence_web as EW
    gone = "Page.evaluate: Execution context was destroyed, most likely because of a navigation"

    class Loc:
        def __init__(self, n=0):
            self.n, self.first = n, self

        def click(self):
            pass

        def count(self):
            return self.n

    class Page:                                      # 윙 '광고센터' → relay/wing/home → marketing/dashboard 로 한 번 더 이동
        def __init__(self, fails):
            self.fails, self.url, self.evals = fails, "https://advertising.coupang.com/relay/wing/home", []

        def wait_for_load_state(self, state="load", timeout=None):
            pass

        def wait_for_url(self, pred, timeout=None):
            assert not pred("https://advertising.coupang.com/relay/wing/home")
            self.url = "https://advertising.coupang.com/marketing/dashboard/sales"
            assert pred(self.url)

        def evaluate(self, js, arg=None):
            self.evals.append(js)
            if self.fails:
                self.fails -= 1
                raise PwError(gone)
            return None                              # 닫을 안내 창 없음

        def get_by_text(self, text, exact=False):
            return Loc(0)

    class Pop:
        def __init__(self, q):
            self.value = q

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class B:
        def __init__(self, q):
            self.page = type("P", (), {"locator": lambda s, *a, **k: Loc()})()
            self.context = type("C", (), {"expect_page": lambda s, timeout=None: Pop(q)})()

    T = type("T", (), {"goto": staticmethod(lambda b, url, label: None), "log": staticmethod(lambda m: None)})
    sleep = EW.time.sleep
    EW.time.sleep = lambda s: None
    try:
        q = Page(fails=2)
        assert EW.open_adcenter(T, B(q), "벅스") is q
        assert q.evals == [EW._CLOSE_POPUP] * 3 and "marketing/dashboard" in q.url, (q.evals, q.url)  # 2번 사라짐 → 3번째 정상
        q = Page(fails=99)
        expect(PwError, lambda: EW.open_adcenter(T, B(q), "벅스"), "계속 사라지면 상한 뒤 오류")
        assert len(q.evals) == EW.NAV_RETRIES, len(q.evals)
        q = Page(fails=0)

        def other(js, arg=None):
            q.evals.append(js)
            raise PwError("Page.evaluate: TypeError: x is not a function")
        q.evaluate = other
        expect(PwError, lambda: EW.open_adcenter(T, B(q), "벅스"), "다른 오류는 다시 안 함")
        assert len(q.evals) == 1, q.evals
    finally:
        EW.time.sleep = sleep
    ok("relay → 최종 주소 기다림 · 이동 중 사라짐 = 쉬고 다시(상한 NAV_RETRIES) · 다른 오류는 바로 올림 · 동의·이동 버튼 안 누름(닫기 JS만)")


def p45_ad_report_csv():
    print("[P45] 큰 매출 성장 광고 보고서 = 쿠팡이 엑셀 대신 탭 구분 글자(text/csv)로 줌(운용 PC 11-03 꿈꾸는아재·디프픽 202604) — 엑셀로 바꿔 저장")
    import io
    import openpyxl
    import settlement_download as TD
    from coupang_analytics import settlement_ads as AD
    from coupang_analytics import settlement_wing_api as API
    head = ["날짜", "캠페인 ID", "캠페인명", "광고집행 옵션ID", "키워드", "노출수", "광고비"]
    tsv = "\n".join("\t".join(f'"{x}"' for x in r) for r in [
        head, ["20260401", "105108858", "04-01 보냉백", "95501572184", "보냉백, 3중", "1,204", "12345"],
        ["20260402", "105108858", "2026", "95501572184", "", "7", "-20.5"]]).encode("utf-8")
    rows = list(openpyxl.load_workbook(io.BytesIO(AD.report_xlsx(tsv))).active.iter_rows(values_only=True))
    assert list(rows[0]) == head and len(rows) == 3, rows
    assert rows[1] == (20260401, 105108858, "04-01 보냉백", 95501572184, "보냉백, 3중", 1204, 12345), rows[1]
    assert rows[2][-1] == -20.5 and rows[2][4] is None, rows[2]                    # 금액 = 숫자(정산서가 숫자 칸만 읽음)
    assert AD.report_xlsx(b"PK-xlsx") == b"PK-xlsx"
    for bad in (b'"a"\t"b"\n"1"\t"2"', "오류 안내".encode("utf-8"), b"\xff\xfe\x00"):      # 다른 모양 = 조용히 저장 안 함
        try:
            AD.report_xlsx(bad)
            raise AssertionError(bad)
        except API.SiteChangedError:
            pass

    class R:
        status = 200
        headers = {"content-type": "text/csv; charset=utf-8"}

        def body(self):
            return tsv

    class B:
        class context:
            class request:
                @staticmethod
                def get(url, timeout):
                    return R()
    assert TD._get_bytes(B, "u", text_ok=True) == tsv
    try:
        TD._get_bytes(B, "u")                                                      # 밀크런·정산 원본은 그대로 엑셀만
        raise AssertionError("글자 응답을 받음")
    except API.SiteChangedError:
        pass
    # D-191: 받기 실패(실측 '500 text/html' = hide4u 윙 부가세 상세 8달 · 3회차 연속 · D-193) = 원인 판정 근거를 남김 —
    #   오류 화면 제목·본문 글자 · 받은 주소(호스트·경로만, 물음표 뒤 값 없음) · 목록 줄 상태·생성 시각
    page = ("<!DOCTYPE html>\n<html lang=\"ko\"><head><meta charset=\"utf-8\"><title>WING - 오류</title>"
            "<style>.x{color:red}</style><script>var t='secret';</script></head><body><div class=\"err\">"
            "요청하신 파일을 찾을 수 없습니다.&nbsp;잠시 후 다시 시도해 주세요.</div></body></html>").encode("utf-8")

    class R500:
        status = 500
        headers = {"content-type": "text/html;charset=UTF-8"}

        def body(self):
            return page

    class B500:
        class context:
            class request:
                @staticmethod
                def get(url, timeout):
                    return R500()
    try:
        TD._get_bytes(B500, "https://wing.coupang.com/tenants/x/download/123?token=SECRET&e=1")
        raise AssertionError("500 을 받음")
    except API.SiteChangedError as exc:
        m = str(exc)
        assert "500" in m and "WING - 오류" in m and "요청하신 파일을 찾을 수 없습니다. 잠시 후" in m, m
        assert "wing.coupang.com/tenants/x/download/123" in m and "SECRET" not in m and "secret" not in m, m
    from datetime import datetime
    from coupang_analytics import settlement_jobs as SJ
    row5 = SJ.DownloadRow("윙", datetime(2026, 11, 9, 8, 6), "FINISHED", "윙부가세상세", handle="https://h/p?token=SECRET")
    j5 = SJ.Job("A", "윙", SJ.DOC_KIND, "윙부가세상세", "2026-07-01", "2026-07-31", "2026-07-31")
    old_get = TD._get_bytes
    try:
        TD._get_bytes = lambda b, url, text_ok=False: (_ for _ in ()).throw(API.SiteChangedError("파일 받기 실패: 500"))
        TD._fetch_one(None, j5, row5, "A")
        raise AssertionError("실패를 넘김")
    except API.SiteChangedError as exc:
        assert "목록 줄 상태 FINISHED" in str(exc) and "11-09 08:06" in str(exc) and "SECRET" not in str(exc), exc
    finally:
        TD._get_bytes = old_get
    rep = {"id": "7", "startDate": 20260401, "endDate": 20260430, "dateGroup": "daily", "granularity": "keyword",
           "campaignCount": 1, "status": "completed"}

    def call(method, path, body):
        q = body["query"]
        if "getDailySettlement" in q:
            return {"data": {"getDailySettlement": {"summary": {}, "items": []}}}
        if "getCampaignList" in q:
            return {"data": {"getCampaignList": [{"id": "105108858", "name": "c"}]}}
        return {"data": {"reportList": {"reports": [rep]}}}
    with tempfile.TemporaryDirectory() as d:
        folder = Path(d)
        s = AD.collect(call, lambda url: b"PK-milk", folder, "꿈꾸는아재-t", date(2026, 4, 1), date(2026, 5, 4),
                       get_report=lambda url: tsv)
        assert s["받음"] == ["202604"], s
        saved = folder / "꿈꾸는아재-t_매출성장광고_202604.xlsx"
        assert saved.read_bytes()[:2] == b"PK" and (folder / "꿈꾸는아재-t_밀크런_202604.xlsx").read_bytes() == b"PK-milk"
        assert sorted(f.name for f in s["파일"]) == sorted(["꿈꾸는아재-t_밀크런_202604.xlsx", "꿈꾸는아재-t_광고정산_202604.json",
                                                         saved.name, "꿈꾸는아재-t_광고정산진행_202605.json"]), s["파일"]
        # D-168 받은 파일 = 이번에 쓴 3개 + 끝나지 않은 5월 일별(T-78 S2)
    ok("글자 보고서 → 엑셀(금액 숫자·따옴표·콤마) · 다른 모양 = 저장 안 하고 오류 · 밀크런·정산 원본은 엑셀만 · 받은 달 다시 안 받음")


def p54_result_summary():
    print("[P54] [실행 결과 종합](D-168) — 판정·전체 계정·비밀번호 오류·사람 조치·오류 현황·받은 파일 전부·남은 소급")
    from datetime import datetime
    from coupang_analytics import settlement_runlog as RLG
    with tempfile.TemporaryDirectory() as tmp:
        lg = RLG.RunLog(tmp, now=datetime(2026, 11, 8, 18, 0, 0), echo=lambda m: None)
        lg.accounts = ["A-1", "B-2", "C-3", "D-4", "E-5"]
        f1 = Path(tmp) / "파일" / "A-1_윙_주정산.xlsx"
        lg.record("A-1", "로그인", RLG.OK, "success: 로그인 완료")
        lg.saved("A-1", f1, "정산 파일")
        lg.record("A-1", "받기", RLG.OK, "A-1_윙_주정산.xlsx", channel="윙", settle_date="2026-11-10")
        lg.remaining("A-1", "판매분석", 120, "일")
        lg.remaining("A-1", "월자료", 6, "달")
        lg.record("B-2", "로그인", RLG.FAIL, "비밀번호 오류·잠금 의심 — 재시도 안 함 (b2)")
        lg.record("B-2", "계정", RLG.SKIP, "비밀번호 오류(재시도 안 함)")
        lg.record("C-3", "로그인", RLG.FAIL, "otp: 2차 인증(인증번호) 입력칸 — 열린 창에 휴대폰 인증번호를 직접 입력하세요")
        lg.record("D-4", "받기", RLG.FAIL, "파일 받기 실패", channel="윙", settle_date="2026-11-10")
        lg.record("D-4", "받기", RLG.OK, "다시 받음", channel="윙", settle_date="2026-11-10")      # 같은 일 = 풀림
        lg.record("E-5", "조회", RLG.WAIT, "확인 필요 — 받기 방법 미확인 정산주기 1", channel="윙")
        lg.remaining("E-5", "판매분석", 30, "일")
        b = RLG.result_block(lg, pending=3)
        j = " | ".join(b)
        assert b[0] == "===== [실행 결과 종합] =====" and b[1] == "판정: 일부 실패 --> 확인 필요", b[:2]
        assert "전체 작업 계정: 5개 — A-1, B-2, C-3, D-4, E-5" in b
        assert any(x.startswith("비밀번호 오류로 수집 안 된 계정: 1개 — B-2 (") and "24시간" in x for x in b), j
        assert "사람 조치 필요: 1개" in b and any(x.startswith("  - C-3: otp: 2차 인증") for x in b), j
        assert "오류 현황(실패·차단, 뒤에 풀린 것 제외): 2건" in b and "  - 로그인 실패 2건: B-2, C-3" in b, j   # D-4 = 뒤에 풀림
        assert "D-4" not in j.split("오류 현황")[1].split("대기·확인 필요")[0]
        assert "남은 소급: 판매분석 150일(2계정) · 월자료 6달(1계정) · 쿠팡 파일 생성·요청 대기 3건" in b, j
        assert "이번 실행에서 받은 파일: 1개" in b and f"  - A-1: {f1.resolve()} (정산 파일)" in b, j   # 드라이브부터 전체 경로
        assert b[-1].startswith("==> 일부 실패 --> 확인 필요 · 계정 5 · 비밀번호 오류 1 · 사람 조치 1 · 오류 2 · 받은 파일 1"), b[-1]
        lg.summary(pending=3)                                                        # 실행 로그 끝에 그대로 남음
        txt = lg.text.read_text(encoding="utf-8")
        assert "[실행 결과 종합]" in txt and "==> 일부 실패 --> 확인 필요" in txt.splitlines()[-1]
        # 정상 완료 · 남은 소급 0 = '없음' · 소급 기록 자체가 없으면 '확인 못 함'
        ok_lg = RLG.RunLog(tmp, now=datetime(2026, 11, 8, 19), echo=lambda m: None)
        ok_lg.record("A-1", "로그인", RLG.OK, "success")
        assert RLG.result_block(ok_lg)[1] == "판정: 정상 완료" and "남은 소급: 확인 못 함(소급 단계를 돌지 않음)" in RLG.result_block(ok_lg)
        ok_lg.remaining("A-1", "판매분석", 0, "일")
        assert "남은 소급: 없음" in RLG.result_block(ok_lg) and "전체 작업 계정: 1개 — A-1" in RLG.result_block(ok_lg)
        # 연속 실패 중단 = '중단' → 다음 바퀴가 다시 돌면 (전체) 중단은 풀리지만 계정 단위 차단은 남음(소급 정상 줄이 가리지 않음)
        p1 = RLG.RunLog(tmp, now=datetime(2026, 11, 8, 20), echo=lambda m: None)
        p1.accounts = ["A-1", "C-3"]
        p1.record("C-3", "로그인", RLG.FAIL, "otp: 2단계 인증")
        p1.record("A-1", "계정", RLG.BLOCK, "BlockDetected: 차단 화면")
        p1.record("(전체)", "중단", RLG.BLOCK, "연속 2계정 실패/차단 — 전체 중단")
        p1.remaining("A-1", "판매분석", 40, "일")
        assert RLG.result_block(p1)[1] == "판정: 연속 실패 --> 중단"                          # 원인 --> 결과(소유자 11-08)
        p2 = RLG.RunLog(tmp, now=datetime(2026, 11, 8, 21), echo=lambda m: None)
        p2.accounts = ["A-1", "C-3"]
        p2.record("C-3", "로그인", RLG.OK, "success")                                # 사람이 인증 → 뒤 바퀴 성공 = 사람 조치에서 빠짐
        p2.record("A-1", "로그인", RLG.OK, "success")
        p2.record("A-1", "소급", RLG.OK, "판매분석 40일")
        p2.saved("A-1", Path(tmp) / "판매분석_일별" / "a1.json", "판매분석 일별 40일 추가")
        p2.remaining("A-1", "판매분석", 0, "일")
        cyc = RLG.Totals()
        cyc.add(p1)
        cyc.add(p2)
        c = RLG.result_block(cyc, note="회차 종료 시각", title="실행 결과 종합 — 이번 회차 2바퀴")
        assert c[0] == "===== [실행 결과 종합 — 이번 회차 2바퀴] =====" and c[1] == "판정: 일부 실패 --> 확인 필요 — 회차 종료 시각", c[:2]
        assert "사람 조치 필요: 0개" in c and "  - 계정 차단 1건: A-1" in c and "전체 작업 계정: 2개 — A-1, C-3" in c, c
        assert "남은 소급: 없음" in c and "이번 실행에서 받은 파일: 1개" in c                    # 남은 수 = 마지막 바퀴 값
        assert RLG.result_block(cyc, stopped=True)[1] == "판정: 진전 없음 --> 중단"               # watch 진전 없음 종료(giveup)
        # 회차 끝(watch) — 마지막 실행 로그 끝에 회차 합계 블록 · 상태 카드에 한 줄 요약
        import settlement_download as TD
        last = RLG.RunLog(tmp, now=datetime(2026, 11, 9, 17, 55), echo=lambda m: None)
        _patched([(TD, "CYCLE", cyc), (TD, "LOG", last), (TD, "_pending_jobs", lambda: 2)],
                 lambda: TD._cycle_close("종료", "회차 종료 시각"))
        tail = last.text.read_text(encoding="utf-8")
        assert "[실행 결과 종합 — 이번 회차 2바퀴]" in tail and "쿠팡 파일 생성·요청 대기 2건" in tail, tail
        card = last.status.read_text(encoding="utf-8")
        assert "상태: 종료" in card and "결과 종합: 일부 실패 --> 확인 필요 · 계정 2" in card, card
    ok("판정(정상 완료·일부 실패 --> 확인 필요·연속 실패/진전 없음 --> 중단) · 계정 이름 전부 · 비밀번호 오류/사람 조치 분리(마지막 로그인 기준) · "
       "같은 일 재성공은 풀림·계정 단위 실패는 남음 · 받은 파일 전체 경로 · 남은 소급 합계·계정 수·대기 건 · 회차 합계")


def _fake_log(record=lambda *a, **k: None):
    """정산 실행 기록(RunLog) 가짜 — record 만 확인하고 받은 파일·남은 소급(D-168)은 버림."""
    from types import SimpleNamespace
    return SimpleNamespace(record=record, saved=lambda *a, **k: None, remaining=lambda *a, **k: None)


def _patched(obj_attrs: list, fn):
    """[(객체, 이름, 값)] 을 잠시 바꿔 fn() 실행 후 되돌림."""
    olds = [(o, n, getattr(o, n)) for o, n, _v in obj_attrs]
    try:
        for o, n, v in obj_attrs:
            setattr(o, n, v)
        return fn()
    finally:
        for o, n, v in olds:
            setattr(o, n, v)


def p46_verify_keep_previous():
    print("[P46] 검증 자료 조회 실패한 항목·달 = 지난 값 유지·받은 날 기록(D-161 — 매일 통째로 다시 써서 hide4u 1~4월 소실)")
    import json
    from types import SimpleNamespace
    sys.path.insert(0, str(ROOT / "tools"))
    import settlement_download as TD
    from coupang_analytics import settlement_verify_collect as VC
    old = {"수집일": "2026-11-04", "기간": ["2026-01-01", "2026-11-03"], "조회 실패": [],
           "purchase": {"202601": {"purchaseReports": [{"revenueAmount": 100}]}, "202602": {"v": 2}},
           "wallet": [{"amount": 1}], "wallet_balance": 5, "rg_vat": {"a": 1, "b": 2},
           "pending": {"전체": {"totalRecordCount": 3}}, "returns": {"9": []}}
    new = {"수집일": "2026-11-05", "기간": ["2026-01-01", "2026-11-04"], "조회 실패": ["매출내역 202601: ServerBusy: x"],
           "purchase": {"202601": None, "202602": {"v": 3}, "202603": None},
           "wallet": None, "wallet_balance": 6, "rg_vat": {"a": 9}, "pending": {"전체": None}}
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "A.json"
        p.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
        _patched([(TD, "VERIFY", Path(tmp)), (TD, "LOG", _fake_log(record=lambda *a, **k: None)),
                  (TD, "name_of", lambda a: "A"), (TD, "_wing_files", lambda n: []),
                  (VC, "collect", lambda *a, **k: json.loads(json.dumps(new)))],
                 lambda: TD.collect_verify(None, None, SimpleNamespace(start=D("2026-01-01"))))
        got = json.loads(p.read_text(encoding="utf-8"))
    assert got["purchase"]["202601"] == old["purchase"]["202601"], "조회 실패한 달은 지난 값 그대로(재현: None 으로 덮어씀)"
    assert got["purchase"]["202602"] == {"v": 3} and got["purchase"]["202603"] is None, "새로 받은 달 = 새 값 · 지난 값 없는 달 = 그대로 실패"
    assert got["wallet"] == [{"amount": 1}] and got["wallet_balance"] == 6 and got["pending"]["전체"] == {"totalRecordCount": 3}
    assert got["rg_vat"] == {"a": 9}, "받은 응답은 지난 응답과 섞지 않음"
    assert got["지난 값"] == {"purchase/202601": "2026-11-04", "wallet": "2026-11-04", "pending/전체": "2026-11-04"}, got["지난 값"]
    assert got["조회 실패"] == new["조회 실패"] and got["수집일"] == "2026-11-05" and got["returns"] == {"9": []}
    again = VC.keep_previous({**new, "수집일": "2026-11-06", "purchase": {"202601": None, "202602": None}}, got)
    assert again["지난 값"]["purchase/202601"] == "2026-11-04" and again["지난 값"]["purchase/202602"] == "2026-11-05", again["지난 값"]
    fixed = VC.keep_previous({**new, "purchase": {"202601": {"v": 1}}, "wallet": [], "pending": {"전체": {}}}, got)
    assert fixed["지난 값"] == {} and fixed["purchase"]["202601"] == {"v": 1} and fixed["wallet"] == [], "다시 받으면 지난 값 표시 없음"
    assert VC.keep_previous(new, {})["지난 값"] == {}
    ok("실패한 달·항목 = 지난 값 유지(받은 날 이어서 기록) · 받은 값은 새 값 · 응답 안 섞음 · 다시 받으면 표시 지움")


def p47_settle_sales_coupons():
    print("[P47] 정산 실행에 판매분석 소급(2026-01-01부터·정산 계정 전부)·윙 쿠폰 수집 — 표시·① 판매수집은 4/1 그대로(D-161 ①②)")
    import json
    import os
    from datetime import timedelta
    from types import SimpleNamespace
    sys.path.insert(0, str(ROOT / "tools"))
    import settlement_download as TD
    from coupang_analytics import collector, wing_coupons
    from coupang_analytics import pipeline_sales as PS
    from coupang_analytics import sales_history as SH
    from coupang_analytics import sales_summary as SS
    assert SS.FIRST_DAY == D("2026-04-01") and SS.COLLECT_FROM == D("2026-01-01"), "표시 시작 4/1 · 수집 시작 1/1"
    assert SS.plan_backfill({}, D("2026-01-02"), first=SS.COLLECT_FROM) == ["2026-01-02", "2026-01-01"]
    assert SS.plan_backfill({}, D("2026-01-02")) == [], "기본(① 판매수집) = 4/1 전은 안 함"
    y = date.today() - timedelta(days=1)
    have = {(SS.FIRST_DAY + timedelta(days=i)).isoformat(): {"수집": "2000-01-01T00:00:00", "합계": {}, "옵션": {}}
            for i in range((y - SS.FIRST_DAY).days + 1)}                    # ① 이 4/1~어제 다 받은 관리대장 계정
    fetched, coupons, recs = [], [], []

    def fetch(page, f, t, log=None):
        fetched.append((f, t))
        return {}
    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            d = Path("output") / "판매분석_일별"
            d.mkdir(parents=True)
            (d / "acc1.json").write_text(json.dumps(have), encoding="utf-8")
            patches = [(collector, "fetch_sales_details", fetch), (PS.time, "sleep", lambda s: None),
                       (wing_coupons, "record_day", lambda page, aid, out, log, gap=(0, 0): coupons.append((aid, out))),
                       (TD, "goto", lambda b, url, who: None), (TD, "name_of", lambda a: "홍길동-가나-acc1"),
                       (TD, "LOG", _fake_log(record=lambda *a, **k: recs.append(a)))]
            _patched(patches, lambda: PS._record_sales_backfill(object(), "acc1", "output", lambda m: None))
            assert fetched == [], "① 판매수집 소급은 4/1 기준 그대로(1~3월 안 부름)"
            _patched(patches, lambda: TD.collect_sales(SimpleNamespace(account_id="acc1"), SimpleNamespace(page=object()),
                                                       SimpleNamespace(start=D("2026-01-01"))))
            first = SS.FIRST_DAY.isoformat()                 # 하루짜리 기간(어제가 월요일 = 이번 주 · 1일 = 이번 달)과 구분 — 소급 = 4/1 전 날
            days = [f for f, t in fetched if f == t and f < first]
            periods = [(f, t) for f, t in fetched if not (f == t and f < first)]
            # D-167: 1/1 이 아직 없는 계정 = 한시 150일 → 1~3월 90일 한 번에(최근부터)
            assert days[0] == "2026-03-31" and len(days) == 90 and days[-1] == "2026-01-01", (len(days), days[:3])
            assert ("2026-01-01", "2026-01-31") in periods and ("2026-03-01", "2026-03-31") in periods, periods
            assert coupons == [("acc1", "output")], coupons
            assert any(r[1] == "판매분석·쿠폰" for r in recs), recs
            assert "2026-01-31" in SH.load_account("output", "acc1"), "1~3월 일별 저장(계정 × 달 파일 D-243 ③ 경로 변경만)"
        finally:
            os.chdir(old_cwd)
    ok("정산 실행 = 1/1부터 빠진 날(1/1 받기 전 150일 D-167·최근부터)·1~3월 월 합계·쿠폰(계정ID) · ① 판매수집은 4/1 그대로")


def p48_ads_from_december():
    print("[P48] 광고·밀크런 = 2025-11분부터(D-166 — D-161 ④ 2025-12 에서 앞당김) · 하루 계정당 2개월 상한 그대로(D-120)")
    from types import SimpleNamespace
    sys.path.insert(0, str(ROOT / "tools"))
    import settlement_download as TD
    from coupang_analytics import settlement_ads as AD
    seen = []

    def fake(call, get_bytes, folder, acct, start, today, **k):
        seen.append(start)
        return {"받을 것": [], "요청": [], "기다림": [], "받음": [], "캠페인 없음": [], "남은 달": 0}
    _patched([(AD, "collect", fake), (TD, "name_of", lambda a: "A"), (TD, "LOG", _fake_log(record=lambda *a, **k: None))],
             lambda: TD.collect_ads(None, None, SimpleNamespace(start=D("2026-01-01"))))
    assert AD.FROM == D("2025-11-01") and seen == [D("2025-11-01")], seen
    assert AD.due_months(AD.FROM, D("2026-01-05"))[0][0] == "202511" and AD.MAX_MONTHS == 2
    ok("광고센터·밀크런 받는 시작 = 2025-11(D-166) · 상한 2개월 유지")


def p49_rg_missing_costs():
    print("[P49] 로켓그로스 빠진 비용 리포트를 매일 정산 계획에 — 정산 줄 없는 주 물류비·조회에 없는 지급 줄(0원 줄) · 원인 확인용 응답 원문 하루 1번(D-164)")
    import gzip
    import json
    import os
    sys.path.insert(0, str(ROOT / "tools"))
    import settlement_download as TD
    from coupang_analytics import settlement_jobs as SJ
    from coupang_analytics import settlement_store as STORE
    from coupang_analytics import settlement_wing_api as API
    cfs = [{"settlementPeriodStartDate": "2026-01-25T15:00:00Z", "settlementPeriodEndDate": "2026-01-31T15:00:00Z",
            "lastSettlementUnpaidCfsDeductionAmount": 13200.0}]
    w1 = {"settlementDate": "2026-03-04T15:00:00.000Z", "settlementPeriodStartDate": "2026-02-01T15:00:00.000Z",
          "settlementPeriodEndDate": "2026-02-07T15:00:00.000Z", "settlementRatio": 70, "settlementCycle": "WEEKLY",
          "settlementGroupKey": "A0001-2026-02-02-2026-02-08", "finalSettlementAmount": 1000,
          "settlementStatusReportDetail": {"totalStorageFeeDeductionAmount": 100, "cfsDeductionDetails": cfs}}
    zero = {"정산일": "2026-03-12", "기간 시작": "2026-02-09", "기간 끝": "2026-02-15", "지급비율": 70, "최종지급액": 0,
            "totalVreturnShippingFeeDeductionAmount": 5500}                # 지급 내역엔 있는데 정산현황 조회 일정에 없는 줄(*2)
    plain0 = {**zero, "정산일": "2026-03-19", "기간 시작": "2026-02-16", "기간 끝": "2026-02-22",
              "totalVreturnShippingFeeDeductionAmount": 0}                 # 비용도 없는 0원 줄 = 받을 것 없음
    # 순수 규칙
    miss = API.missing_week_events([w1], "A", D("2025-11-01"))
    assert [(e.kind, e.ref, str(e.settle_date), e.reports) for e in miss] == [
        (SJ.MISSING_KIND, "A0001-2026-01-26-2026-02-01", "2026-03-05", API.CFS_KINDS)], miss
    assert API.missing_week_events([w1], "A", D("2026-02-01")) == [], "조회 시작 전 주는 정산 줄을 못 봤을 수 있어 만들지 않음"
    have = API.rg_events({"settlementStatusReports": [w1]}, "A")
    extra = API.unlisted_row_events([zero, plain0, API.amount_rows({"settlementStatusReports": [w1]}, "로켓그로스")[0]],
                                    have, [w1], "A")
    assert [(e.kind, e.ref, str(e.settle_date), e.reports) for e in extra] == [
        ("주정산", "A0001-2026-02-09-2026-02-15", "2026-03-12", ("반출 배송 서비스비",))], extra
    assert API.unlisted_row_events([zero], [], [w1, {**w1, "settlementGroupKey": "B9-2026-02-02-2026-02-08"}], "A") == [], \
        "업체코드가 하나로 정해지지 않으면 요청 키를 만들지 않음(추측 금지)"
    jobs: list = []
    SJ.plan_requests(have + miss + extra, jobs, today=D("2026-04-01"), now=TD.datetime(2026, 4, 1, 9), per_account_cap=50)
    by = {(j.kind, j.report) for j in jobs}
    assert {(SJ.MISSING_KIND, k) for k in API.CFS_KINDS} <= by and (SJ.MISSING_KIND, "판매수수료") not in by, by
    assert ("주정산", "반출 배송 서비스비") in by and ("주정산", "판매수수료") in by and ("주정산", "보관비") in by, by
    j = next(j for j in jobs if j.kind == SJ.MISSING_KIND)
    assert API.rg_request_body(j, 1)["settlementGroupKeys"] == ["A0001-2026-01-26-2026-02-01"]
    # 정산 일정 조회에 붙임 + 응답 원문 하루 1번
    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            STORE.AMOUNTS.mkdir(parents=True)
            (STORE.AMOUNTS / "A_로켓그로스.json").write_text(json.dumps([zero], ensure_ascii=False), encoding="utf-8")

            def api(b, name, m, path, body):
                return {"settlementStatusReports": [w1] if body["endDate"].startswith("2026-03-31") else []}
            ahead = [(D("2026-04-01"), D("2026-04-30"), {"settlementStatusReports": []})]
            run = lambda: TD.read_events(None, "A", D("2026-01-01"), D("2026-03-31"), amounts_from=D("2026-01-01"))  # noqa: E731
            patches = [(TD, "goto", lambda *a: None), (TD, "api", api), (TD, "_read_forecast", lambda *a: ahead),
                       (TD.time, "sleep", lambda s: None), (TD, "LOG", _fake_log(record=lambda *a, **k: None)),
                       (TD, "CHANNELS", ()), (TD, "_SOURCES", TD._SOURCES[1:])]
            evs = _patched(patches, run)
            assert sorted((e.kind, e.ref) for e in evs) == sorted([
                ("주정산", "A0001-2026-02-02-2026-02-08"), (SJ.MISSING_KIND, "A0001-2026-01-26-2026-02-01"),
                ("주정산", "A0001-2026-02-09-2026-02-15")]), evs
            raw_dir = STORE.BASE / TD.RG_RAW_DIRNAME / "A"
            files = sorted(raw_dir.glob("*.json.gz"))
            assert len(files) == 1, files
            rec = json.loads(gzip.open(files[0], "rt", encoding="utf-8").read())
            assert [x["기간"] for x in rec["조회"]] == [["2026-01-01", "2026-01-31"], ["2026-02-01", "2026-02-28"],
                                                     ["2026-03-01", "2026-03-31"]] and len(rec["예정"]) == 1, rec.keys()
            _patched(patches, run)
            assert len(sorted(raw_dir.glob("*.json.gz"))) == 1, "같은 날 다시 조회해도 원문은 하루 1번"
        finally:
            os.chdir(old_cwd)
    ok("정산 줄 없는 주 = 물류비 5종만(판매수수료 없음)·조회에 없는 지급 줄 = 그 주 일정·업체코드 모르면 안 만듦 · 원문 하루 1번")


def p50_verify_new_items():
    print("[P50] 검증 원자료 새 항목(D-169 N9·D-171 N12·N13) — 빠른정산 이용 여부·프로모션 추가 수수료·리뷰 이벤트 캠페인 · 실패 = 그 항목만")
    from coupang_analytics import settlement_verify_collect as VC
    # 실측(gyi0101 2026-11-08 라이브·조회만): available-services → {result, displayMessage, content:{availableServices:[…]}} ·
    # promotion-fee → {participated:false, eventStartedAt, eventEndedAt, exitedAt, extraFeeRatio:7} · campaigns?startDate&endDate
    # (한국 0시 = 전날 15시 UTC ISO)&pageSize(100 허용) → {vendorId, count, hasMore, campaigns[], statusCounts{…}} · 다른 화면에서 불러도 200.
    seen: list = []
    promo = {"participated": False, "eventStartedAt": None, "eventEndedAt": None, "exitedAt": None, "extraFeeRatio": 7}
    sc = {"ACTIVE": 0, "COMPLETED": 1}

    def call(method, path, body, more=False):
        if path == VC.FAST_SETTLEMENT:
            return {"result": "SUCCESS", "displayMessage": "", "content": {"availableServices": ["FAST_SETTLEMENT", "FACTORING"]}}
        if path == VC.PROMOTION_FEE:
            return dict(promo)
        if path.startswith(VC.REVIEW_CAMPAIGNS):
            seen.append(path)
            return {"vendorId": "A00434040", "count": 1, "hasMore": more, "campaigns": [{"campaignId": 7}], "statusCounts": sc}
        return {}
    d = VC.collect(call, lambda url: None, D("2026-01-01"), D("2026-11-08"))
    assert d["fast_settlement"] == ["FAST_SETTLEMENT", "FACTORING"], d["fast_settlement"]
    assert d["promotion_fee"] == promo, d["promotion_fee"]
    assert d["review_campaigns"] == {"count": 1, "hasMore": False, "campaigns": [{"campaignId": 7}], "statusCounts": sc},         "업체코드 칸은 저장 안 함(파일 이름이 계정)"
    assert seen == [f"{VC.REVIEW_CAMPAIGNS}?startDate=2025-12-31T15:00:00.000Z&endDate=2026-11-07T14:59:59.999Z&pageSize=100"], seen
    assert not d["조회 실패"], d["조회 실패"]
    # 더 있음(hasMore) = 다 못 받음 → 받은 것은 저장하되 '조회 실패'에 남김(오류 정의 — 에러 없음 ≠ 다 받음)
    d2 = VC.collect(lambda m, p, b: call(m, p, b, more=True), lambda url: None, D("2026-01-01"), D("2026-11-08"))
    assert d2["review_campaigns"]["hasMore"] is True and any("리뷰 이벤트 캠페인" in x and "더 있음" in x for x in d2["조회 실패"]), d2
    # 예상 못 한 오류(응답 모양) = 그 항목만 실패 · 다음 날 지난 값 유지(D-161)
    d3 = VC.collect(lambda m, p, b: {"content": None} if p == VC.FAST_SETTLEMENT else call(m, p, b), lambda url: None,
                    D("2026-01-01"), D("2026-11-08"))
    assert d3["fast_settlement"] is None and any("빠른정산" in x for x in d3["조회 실패"]), d3["조회 실패"]
    assert VC.keep_previous(d3, d)["fast_settlement"] == ["FAST_SETTLEMENT", "FACTORING"]
    ok("빠른정산 이용 서비스 목록·프로모션 수수료 응답 그대로·리뷰 캠페인(1/1~어제·100개)·더 있음/모양 오류 = 그 항목만 실패")


def p51_regular_then_backfill():
    print("[P51] 정산 실행 = 정기(전 계정) → 소급(전 계정 다시) 두 단계(D-170) · 판매분석 소급 = 회차 기준 150일 → 1/1 받으면 60일(D-167)")
    from types import SimpleNamespace
    sys.path.insert(0, str(ROOT / "tools"))
    import settlement_download as TD
    from coupang_analytics import sales_summary as SS
    # ① 상한: 1/1 이 없으면 150(한시) · 1/1 까지 받았으면 60(자동 복귀 — 사람이 되돌릴 필요 없음)
    assert SS.SETTLE_BACKFILL_LIMIT == 150 and SS.BACKFILL_PER_DAY == 60
    assert SS.settle_limit({}, SS.COLLECT_FROM) == 150
    assert SS.settle_limit({"2026-01-01": {"수집": "x"}}, SS.COLLECT_FROM) == 60
    # ② 회차 기준(18:00~17:55): 이번 회차 시작 뒤 받은 날만 상한에서 뺀다 — 자정을 넘어도 한 회차는 한 번만 셈
    have = {f"2026-10-{i:02d}": {"수집": "2026-11-08T19:00:00"} for i in range(1, 21)}          # 회차 시작 뒤(전날 밤) 20일
    have.update({f"2026-09-{i:02d}": {"수집": "2026-11-09T01:00:00"} for i in range(1, 11)})    # 자정 넘어 10일
    have.update({f"2026-08-{i:02d}": {"수집": "2026-11-08T10:00:00"} for i in range(1, 6)})     # 회차 전(그날 오전 ①) 5일
    plan = SS.plan_backfill(have, D("2026-11-08"), today=D("2026-11-09"), first=SS.COLLECT_FROM, limit=150,
                            since="2026-11-08T18:00:00")
    assert len(plan) == 150 - 30 and plan[0] == "2026-11-08", (len(plan), plan[:2])
    assert len(SS.plan_backfill(have, D("2026-11-08"), today=D("2026-11-09"), first=SS.COLLECT_FROM, limit=150)) == 140,         "since 없으면 지금처럼 '오늘 날짜' 기준(① 판매수집 그대로)"
    # ③ 정기 단계엔 판매분석 소급이 없고, 소급 단계가 받는다 · 소급에서 한 일은 '소급' 줄로 남아 다음 바퀴 판단에 셈
    calls: list = []
    recs: list = []
    fake_log = SimpleNamespace(record=lambda *a, **k: recs.append(a), rows=[], line=lambda m: None)   # line = [메모리] 줄(D-346)
    patches = [(TD, "cmd_request", lambda *a: calls.append("요청")), (TD, "cmd_download", lambda *a: calls.append("받기")),
               (TD, "collect_verify", lambda *a: calls.append("검증")), (TD, "collect_ads", lambda *a: calls.append("광고")),
               (TD, "collect_sales", lambda *a: (calls.append("판매"), 37)[1]),
               (TD, "collect_docs", lambda *a: (calls.append("월자료"), 2)[1]), (TD.time, "sleep", lambda s: None),
               (TD, "request_docs", lambda *a: (calls.append("월자료 요청"), 3)[1]),
               (TD, "name_of", lambda a: "A"), (TD, "LOG", fake_log)]
    args = SimpleNamespace(dry_run=False, until="", start=D("2026-01-01"))
    _patched(patches, lambda: TD.cmd_run(None, None, args, []))
    assert calls == ["요청", "받기", "검증", "광고"], calls
    calls.clear()
    _patched(patches, lambda: TD.cmd_backfill(None, None, args, []))
    assert calls == ["판매", "월자료", "월자료 요청"] and recs and recs[-1][1] == "소급"         and "판매분석 37일 · 월자료 2개 · 월자료 요청 3건" in recs[-1][3], (calls, recs)
    fake_log.rows = [{"단계": "소급", "결과": TD.RL.OK}, {"단계": "받기", "결과": TD.RL.OK}, {"단계": "검증", "결과": TD.RL.OK}]
    assert TD._sweep_work_count(fake_log) == 2, "요청·받기·소급만 '한 일'"
    recs.clear()
    _patched([(TD, "collect_sales", lambda *a: 0), (TD, "collect_docs", lambda *a: 0), (TD, "name_of", lambda a: "A"),
              (TD, "request_docs", lambda *a: 0),
              (TD, "LOG", fake_log)],
             lambda: TD.cmd_backfill(None, None, args, []))
    assert not recs, "받은 게 없으면 '소급' 줄 없음(다 받았거나 이번 회차 상한 다 씀 → 완료로 끝남)"
    # ④ 한 바퀴 = 전 계정 정기 → 전 계정 소급 · 정기가 중단(연속 실패)이면 소급 안 함
    order: list = []

    class FakeLog:
        run_id, rows, files, left, accounts = "t", [], [], {}, []

        def __init__(self, base):
            pass

        def heartbeat(self, *a):
            pass

        def summary(self, **k):
            pass

        def line(self, m):
            pass
    for rc_regular, want in ((0, ["cmd_run", "cmd_backfill"]), (1, ["cmd_run"])):
        order.clear()
        pat = [(TD.RL, "RunLog", FakeLog), (TD, "load_accounts", lambda only: ["a", "b"]), (TD, "_stats_in_child", lambda: None),
               (TD, "name_of", lambda a: a), (TD, "_pending_jobs", lambda: 0), (TD, "CYCLE", TD.RL.Totals()),
               (TD, "_backlog_left", lambda accts, a: None),
               (TD, "_run_accounts", lambda accts, run, a: (order.append(run.__name__), rc_regular if run is TD.cmd_run else 0)[1])]
        stopped, _work = _patched(pat, lambda: TD._one_pass(SimpleNamespace(start=D("2026-01-01"), until="", dry_run=False)))
        assert order == want and stopped == bool(rc_regular), (order, stopped)
    ok("정기 = 요청·받기·검증·광고 · 소급 = 판매분석(회차 기준 150일→60) · 전 계정 정기 끝난 뒤 소급 · 소급 한 일도 '다음 바퀴' 판단에 셈")


def p52_settlement_docs():
    print("[P52] 정산 월자료(D-171 N3~N7·N10) — 세금계산서 2종·라이브·주문별 매출(size 10)·RG 재고변동·RG 반품 하루 1번 · 회차당 종류별 3달")
    import calendar
    import gzip
    import io
    import json
    import tempfile
    from datetime import datetime
    from pathlib import Path
    import openpyxl
    from coupang_analytics import settlement_docs as DOC
    from coupang_analytics import settlement_wing_api as API
    # ① 받을 달: 2026-01 부터 · 말일+지연일이 지난 달 · 최근부터
    assert [m[0] for m in DOC.due_months("매입세금계산서", D("2026-11-08"))] == [f"2026{m:02d}" for m in range(9, 0, -1)]
    assert DOC.due_months("라이브정산", D("2026-03-08"))[0][0] == "202601", "라이브 계산일 = 다음 달 25일 → 35일 뒤"
    assert DOC.due_months("라이브정산", D("2026-03-07")) == []

    # ② 매입 세금계산서 HTML(실측 12칸) → 줄·공급가액 합 · 머리글 바뀌면 화면 변경 · '발행 내역이 없습니다' = 0줄
    def table(head, rows):
        def tr(cells, t):
            return "<tr>" + "".join(f"<{t}> {c} </{t}>" for c in cells) + "</tr>"
        return ("<html><table class='x'><tr><td>달력</td></tr></table><table class='table table-bordered'><thead>" + tr(head, "th")
                + "</thead><tbody>" + "".join(tr(r, "td") for r in rows) + "</tbody></table></html>")
    r1 = ["쿠팡 주식회사", "1208800767", "유라이프", "000", "판매수수료 판매자서비스이용료", "1", "473,746", "47,375", "521,121",
          "2026-01-31", "전송완료", "보기"]
    r2 = r1[:5] + ["2", "-182,748", "-18,274", "-201,022"] + r1[9:]
    seen: list = []

    def hc(m, p, b):
        seen.append((m, p, b))
        return table(DOC.TAX_HEAD, [r1, r2])
    d = DOC.fetch_purchase_tax(hc, D("2026-01-01"), D("2026-01-31"))
    assert seen == [("POST", DOC.TAX, "from=2026-01-01&to=2026-01-31&year=2026&month=01")], seen
    assert d["공급가액 합"] == 473746 - 182748 and d["세액 합"] == 47375 - 18274 and d["줄"][0]["발행내용"] == r1[4], d
    expect(API.SiteChangedError, lambda: DOC.parse_invoice_table(table(DOC.TAX_HEAD[:-1], [r1[:-1]]), DOC.TAX_HEAD), "머리글 변경")
    assert DOC.parse_invoice_table(table(DOC.CONSIGN_HEAD, [["발행 내역이 없습니다."]]), DOC.CONSIGN_HEAD) == []
    # 위수탁: 쪽 넘김 — 같은 줄이 다시 오거나 빈 쪽이면 멈춤
    c1 = ["11", "유라이프", "000", "x", "A1", "1,000", "100", "1,100", "2026-01-31", "보기"]
    pages = {1: [c1], 2: [c1[:4] + ["A2"] + c1[5:]], 3: [c1]}
    cs = DOC.fetch_consign_tax(lambda m, p, b: table(DOC.CONSIGN_HEAD, pages[int(p.split("page=")[1].split("&")[0])]),
                               D("2026-01-01"), D("2026-01-31"))
    assert cs["공급가액 합"] == 2000 and len(cs["줄"]) == 2, cs

    # ③ 라이브: 요약·상세(쪽 끝까지)·크리에이터 칸 제외 · 상세 합 ≠ 요약 합 = 다 못 받음
    summ = {"successful": True, "rData": [{"netGmv": 97300, "amount": 4865, "platformFeeVat": 487}]}

    def raw(i):
        return {"successful": True, "rData": {"page": {"pageTotal": 2, "pageIndex": i}, "data": [
            {"orderId": i, "netGmv": 48650, "amount": 2432 + (i == 2), "creatorName": "누구", "creatorNameToken": "t", "creatorId": 9}]}}

    def lc(m, p, b):
        return summ if "/summary/" in p else raw(int(p.rsplit("=", 1)[1]))
    lv = DOC.fetch_live(lc, "202601")
    assert len(lv["상세"]) == 2 and "creatorName" not in str(lv) and lv["요약"] == summ["rData"], lv
    expect(API.SiteChangedError, lambda: DOC.fetch_live(lambda m, p, b: summ if "/summary/" in p else
                                                        {"successful": True, "rData": {"page": {"pageTotal": 1}, "data": []}}, "202601"),
           "라이브 합 불일치")

    # ④ 주문별 매출: 쪽 수 16 → 1~16쪽 151줄 + 17쪽 빈 쪽 · size 10 · cursorToken 이어받기 · 고객 이름 제외
    bodies: list = []

    def oc(m, p, b, total=151, pages_=16):
        if p.endswith("-page-total"):
            assert b["size"] == 10
            return pages_
        bodies.append(b)
        lo = (b["page"] - 1) * 10
        got = [{"orderId": i, "transactionType": "ORDER", "customerName": "고객", "productGmv": 100, "apAmount": 90,
                "deliveryGmv": 0, "trAmountIncVat": 10} for i in range(lo, min(lo + 10, total))]
        return {"orderDetails": got, "rawRecordSize": len(got), "cursorToken": f"c{b['page']}"}
    od = DOC.fetch_order_detail(oc, D("2026-01-01"), D("2026-01-31"))
    assert od["줄 수"] == 151 and od["쪽 수"] == 16 and od["합계"]["apAmount"] == 151 * 90 and "customerName" not in str(od["줄"][0])
    assert [b["page"] for b in bodies] == list(range(1, 18)) and all(b["size"] == 10 for b in bodies)
    assert bodies[0]["cursorToken"] == "" and bodies[1]["cursorToken"] == "c1" and bodies[0]["searchDateType"] == "CONFIRM_DATE"
    expect(API.SiteChangedError, lambda: DOC.fetch_order_detail(lambda m, p, b: oc(m, p, b, total=130), D("2026-01-01"),
                                                                D("2026-01-31")), "줄 수가 쪽 수와 안 맞음")
    # ④-b 마지막 쪽 cursorToken '' = 다음 쪽 없음(실측 11-09 bf0621 2026-09: 쪽 수 1 · 1쪽 3줄 cursor '' · 2쪽을 ''로 부르면
    #      서버가 처음부터 다시 시작해 1쪽 3줄을 또 줌 → 옛 코드 '같은 줄 두 번' SiteChangedError — 11-08 1쪽 달 10/10 실패)
    def real(total, last_cursor_empty=True, merged=frozenset(), raw_size=True):
        """total = 원본 건수(쪽 수·rawRecordSize 기준) · merged = 앞 줄에 합쳐져 줄로 안 오는 원본 번호(추가배송료 — ④-c)."""
        sent: list = []

        def c(m, p, b):
            if p.endswith("-page-total"):
                return -(-total // 10)
            sent.append(b)
            pg = b["page"] if b["cursorToken"] else 1          # 커서 없으면 서버는 처음부터(실측)
            lo = (pg - 1) * 10
            raw = range(lo, min(lo + 10, total))
            r = {"orderDetails": [{"orderId": i, "transactionType": "ORDER", "apAmount": 1} for i in raw if i not in merged],
                 "cursorToken": "" if lo + 10 >= total and last_cursor_empty else f"c{pg}"}
            if raw_size:
                r["rawRecordSize"] = len(raw)
            return r
        return c, sent
    for total, want_calls in ((3, 1), (10, 1), (27, 3)):
        c, sent = real(total)
        od = DOC.fetch_order_detail(c, D("2026-09-01"), D("2026-09-30"))
        assert od["줄 수"] == total and [b["page"] for b in sent] == list(range(1, want_calls + 1)), (total, od["줄 수"], sent)
    c, sent = real(27, last_cursor_empty=False)                 # 마지막 쪽에도 커서가 오면 빈 쪽까지(옛 방식 그대로)
    assert DOC.fetch_order_detail(c, D("2026-09-01"), D("2026-09-30"))["줄 수"] == 27 and len(sent) == 4, sent
    # ④-c 상품+추가배송료 = 서버가 한 줄로 합쳐 줌(금액 합산) · 쪽 수·rawRecordSize 는 합치기 전 건수(실측 11-09 oopean 2026-08: 쪽 수 49 ·
    #      5·29·31쪽 rawRecordSize 10 인데 9줄 · 원본 481·줄 478 · 정산금액 = 엑셀 상품+추가배송료와 같음) → 옛 확인(줄 수 > 480) 실패
    c, sent = real(481, merged={45, 285, 305})
    od = DOC.fetch_order_detail(c, D("2026-08-01"), D("2026-08-31"))
    assert od["쪽 수"] == 49 and od["줄 수"] == 478 and od["원본 건수"] == 481 and len(sent) == 49, (od["줄 수"], len(sent))
    expect(API.SiteChangedError, lambda: DOC.fetch_order_detail(real(27, raw_size=False)[0], D("2026-09-01"), D("2026-09-30")),
           "rawRecordSize 없음")
    # ④-d 오래된 달(1~4월) = 1쪽부터 커서 '' · 쪽 수는 여러 쪽(T-51 · output43 실패 근거 45개 전부 1쪽 '커서 빈칸' · 서버 쪽 수 2~82 ·
    #      1~4월 받은 달 중 여러 쪽 달 0 = 1쪽·0쪽 달만 받음 · 5~10월은 여러 쪽 달 14~21개 받음) → 커서 없으면 쪽 번호로 쪽 수까지
    def by_page(total, restart=False):
        sent: list = []

        def c(m, p, b):
            if p.endswith("-page-total"):
                return -(-total // 10)
            sent.append(b)
            pg = 1 if restart else b["page"]                     # restart = 커서 '' 면 쪽 번호를 무시하고 처음부터(bf0621 모양)
            lo = (pg - 1) * 10
            got = [{"orderId": i, "transactionType": "ORDER", "apAmount": 1} for i in range(lo, min(lo + 10, total))]
            return {"orderDetails": got, "rawRecordSize": len(got), "cursorToken": "", "requestPage": pg, "requestSize": 10}
        return c, sent
    c, sent = by_page(58)
    od = DOC.fetch_order_detail(c, D("2026-01-01"), D("2026-01-31"))
    assert od["줄 수"] == 58 and od["쪽 수"] == 6 and [b["page"] for b in sent] == [1, 2, 3, 4, 5, 6], (od["줄 수"], sent)
    assert all(b["cursorToken"] == "" for b in sent), sent
    c, sent = by_page(580, restart=True)                         # 쪽 번호가 안 먹으면 2쪽에서 바로 멈춤(58쪽 헛호출 안 함)
    expect(API.SiteChangedError, lambda: DOC.fetch_order_detail(c, D("2026-01-01"), D("2026-01-31")), "쪽 번호 무시 = 처음부터")
    assert len(sent) == 2, len(sent)
    # ④-e 같은 주문·유형·옵션·배송비 번호라도 구매확정일이 다르면 다른 줄(T-51 · output43 Difpick 2026-05 4쪽·11쪽 CANCEL
    #      13100182213074 확정 05-04 정산 −19,660 · 05-08 −19,659 — 수수료도 −2,650/−2,651 로 다름 = 서버 반복 아님)
    def two_cancel(m, p, b):
        if p.endswith("-page-total"):
            return 1
        x = {"orderId": 13, "transactionType": "CANCEL", "vendorItemId": 9, "shippingFeeId": 5, "apAmount": -19660, "confirmDate": "2026-05-04"}
        return {"orderDetails": [x, {**x, "apAmount": -19659, "confirmDate": "2026-05-08"}], "rawRecordSize": 2, "cursorToken": ""}
    od = DOC.fetch_order_detail(two_cancel, D("2026-05-01"), D("2026-05-31"))
    assert od["줄 수"] == 2 and od["합계"]["apAmount"] == -39319, od

    # ⑤ RG 재고변동·반품 엑셀 판정
    def wb_bytes(sheets):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        for name, rows in sheets:
            ws = wb.create_sheet(name)
            for r in rows:
                ws.append(r)
        b = io.BytesIO()
        wb.save(b)
        return b.getvalue()
    per = ["", "내역 발생 일자 : 2026.01.01 ~ 2026.01.31"]
    recon = wb_bytes([("1. 재고이관 상세", [per, [], ["등록상품 ID", "옵션 ID", "SKU ID", "등록상품명，옵션명"], ["설명"],
                                          ["15991608281", "94595392275", "69078539", "건조대"]]),
                      ("2. 입고관련", [per, ["등록상품 ID", "옵션 ID", "SKU ID", "입고요청 ID"]])])
    assert DOC.check_recon(recon, D("2026-01-01"), D("2026-01-31")) == 1
    expect(API.SiteChangedError, lambda: DOC.check_recon(recon, D("2026-02-01"), D("2026-02-28")), "다른 달")
    expect(API.SiteChangedError, lambda: DOC.check_recon(b"<html>", D("2026-01-01"), D("2026-01-31")), "엑셀 아님")
    rets = wb_bytes([("Excel Data", [["", "안내"], [], ["", *DOC.RETURNS_HEAD], ["", "* 설명"],
                                     ["", "2026-05-17", "배송중단", "0", "41", "95", "식기건조대", "-", "Q1", "판매불가", "검수진행중"]])])
    assert DOC.check_returns(rets) == 1
    assert DOC.returns_url("A00434040", D("2026-11-08")).endswith("/A00434040/1735657200000/1794063599999")

    # ⑥ 업체코드 = RG 원문 settlementGroupKey 앞부분(하나일 때만 · 다른 근거는 P55)
    with tempfile.TemporaryDirectory() as tmp:
        sd = Path(tmp)
        assert DOC.rg_vendor(sd / "없음", [], sd / "재고없음") == ""
        with gzip.open(sd / "2026-11-08.json.gz", "wt", encoding="utf-8") as fh:
            json.dump({"조회": [{"응답": {"settlementStatusReports": [{"settlementGroupKey": "A00434040-2026-10-27-2026-11-02"}]}}],
                       "예정": []}, fh)
        assert DOC.rg_vendor(sd, [], sd / "재고없음") == "A00434040"

    # ⑦ collect: 회차당 종류별 3달 · 받은 달 다시 안 받음 · 한 종류 실패 = 그 종류만 · 업체코드 없으면 RG 안 함 · 반품 하루 1번
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "월자료" / "A"
        clock = {"now": datetime(2026, 11, 8, 20, 0, 0)}
        got_urls: list = []

        def gb(url):
            got_urls.append(url)
            if "reconciliation" in url:
                y, m = url.rsplit("/", 2)[1:]
                last = calendar.monthrange(int(y), int(m))[1]
                p_ = ["", f"내역 발생 일자 : {y}.{int(m):02d}.01 ~ {y}.{int(m):02d}.{last}"]
                return wb_bytes([("1. 재고이관 상세", [p_, ["등록상품 ID", "옵션 ID", "SKU ID"]]),
                                 ("2. 입고관련", [p_, ["등록상품 ID", "옵션 ID", "SKU ID"]])])
            return rets

        def api_(m, p, b):
            if "/live/" in p:
                return lc(m, p, b) if "202609" not in p else {"successful": False}
            return oc(m, p, b)

        def hc2(m, p, b):
            return table(DOC.TAX_HEAD, [r1]) if p == DOC.TAX else table(DOC.CONSIGN_HEAD, [["발행 내역이 없습니다."]])

        skip: set = set()                                         # 회차 동안 같은 집합(호출부 DOC_FAILED · D-245)

        def run(vendor=""):
            return DOC.collect(api_, hc2, gb, folder, D("2026-11-08"), vendor=vendor, since="2026-11-08T18:00:00",
                               now=lambda: clock["now"], skip=skip)
        s1 = run()
        names = sorted(x.split("(")[0] for x in s1["받음"])
        assert names == sorted([f"{k}_{ym}.json" for k in ("매입세금계산서", "위수탁세금계산서", "주문별매출") for ym in
                                ("202609", "202608", "202607")] + [f"라이브정산_{ym}.json" for ym in ("202608", "202607", "202606")]), names
        assert len(s1["실패"]) == 1 and s1["실패"][0].startswith("라이브정산 202609") and skip == {"라이브정산 202609"}, s1["실패"]
        assert s1["남은 달"] == 3 * 6 + 6, s1["남은 달"]          # 세 종류 6달씩 + 라이브 6달(실패 달 넘어 옛 3달 받음 · D-245)
        assert sorted(f.name for f in s1["파일"]) == names and all(f.exists() for f in s1["파일"])   # D-168 받은 파일 경로
        assert not got_urls, "업체코드 없으면 RG 재고변동·반품 안 부름"
        assert json.loads((folder / "매입세금계산서_202609.json").read_text(encoding="utf-8"))["공급가액 합"] == 473746
        s2 = run(vendor="A00434040")                              # 같은 회차 다시 = 예산 다 씀 · RG 만 새로
        assert sorted(x.split("(")[0] for x in s2["받음"]) == sorted(
            [f"RG재고변동_{ym}.xlsx" for ym in ("202609", "202608", "202607")] + ["RG반품내역_최신.xlsx"]), s2["받음"]
        assert run(vendor="A00434040")["받음"] == [], "반품내역은 하루 1번"
        clock["now"] = datetime(2026, 11, 9, 18, 30, 0)          # 다음 회차 = 다음 3달
        s4 = DOC.collect(api_, hc2, gb, folder, D("2026-11-09"), vendor="A00434040", since="2026-11-09T18:00:00",
                         now=lambda: clock["now"])
        assert "매입세금계산서_202606.json" in " ".join(s4["받음"]) and "RG반품내역_최신.xlsx" in " ".join(s4["받음"]), s4

        def blocked(m, p, b):
            raise API.ApiBlocked("x")
        expect(API.ApiBlocked, lambda: DOC.collect(blocked, hc2, gb, Path(tmp) / "B", D("2026-11-08")), "차단은 그대로")
    ok("세금계산서 HTML 12칸·10칸(합계)·라이브 상세=요약·주문별 size 10 쪽 수 대조·RG 엑셀 판정·업체코드 · 회차당 3달·실패 격리·반품 하루 1번")


def p56_one_failure_not_blocking():
    print("[P56] 한 곳 실패가 나머지를 막지 않음(D-245 · output (37) 보고 B ③④) — 월자료 실패 달은 그 회차에 다시 안 부르고 옛 달로 ·"
          " 광고센터 500 이어도 밀크런 받음 · 주문별 매출 실패 근거 파일(T-2 재현용)")
    from coupang_analytics import settlement_ads as AD
    from coupang_analytics import settlement_docs as DOC
    import json
    from datetime import datetime

    from coupang_analytics import settlement_wing_api as API
    D = date.fromisoformat

    def no(*_a):
        return None
    with tempfile.TemporaryDirectory() as tmp:
        calls: list = []

        def fetch(kind, ym, f, t):
            calls.append(ym)
            if ym in ("202609", "202608"):
                raise API.SiteChangedError(f"{ym} 맞지 않음")
            return b"{}", "json", "0줄"

        def run(since: str, skip: set, day: str):
            r = DOC._Run(Path(tmp), no, (API.ApiBlocked,), lambda: datetime.fromisoformat(day), skip)
            r.kind("주문별매출", D(day[:10]), since, fetch, no)
            return r
        skip1: set = set()
        r1 = run("2026-11-15T18:00:00", skip1, "2026-11-15T19:00:00")
        assert calls == ["202609", "202608", "202607", "202606", "202605"], calls        # 옛 코드 = 202609 실패에서 멈춤
        assert skip1 == {"주문별매출 202609", "주문별매출 202608"} and r1.out["남은 달"] == 6, (skip1, r1.out)
        calls.clear()
        run("2026-11-15T18:00:00", skip1, "2026-11-15T21:00:00")                          # 같은 회차 다음 바퀴 = 예산 다 씀
        assert calls == [], calls
        calls.clear()
        run("2026-11-16T18:00:00", set(), "2026-11-16T19:00:00")                          # 다음 회차 = 실패 달 1번 더 · 옛 달 3개
        assert calls[:2] == ["202610", "202609"] or calls[:1] == ["202609"], calls
        assert {"202604", "202603"} <= set(calls), calls

        # 주문별 매출 실패 근거 = 쪽별 커서·중복 줄(고객 이름 칸 없음)
        def one_page(m, path, body):
            if path.endswith("-page-total"):
                return 2
            return {"orderDetails": [{"orderId": i, "transactionType": "ORDER", "vendorItemId": 1, "shippingFeeId": None,
                                      "customerName": "홍길동"} for i in range(10)], "rawRecordSize": 10, "cursorToken": ""}
        r = DOC._Run(Path(tmp) / "o", no, (API.ApiBlocked,), datetime.now)
        assert r.attempt("주문별매출 202604", lambda: DOC.fetch_order_detail(one_page, D("2026-04-01"), D("2026-04-30"))) is None
        ev = json.loads((Path(tmp) / "o" / "_실패_주문별매출_202604.json").read_text(encoding="utf-8"))
        page_ev = {"줄": 10, "원본": 10, "커서 빈칸": True, "요청쪽": None, "칸": ["cursorToken", "orderDetails", "rawRecordSize"]}
        assert ev["쪽 수(서버)"] == 2 and ev["쪽별"] == [{"쪽": 1, **page_ev}, {"쪽": 2, **page_ev}], ev   # 2쪽 = 같은 줄 → 멈춤(T-51)
        assert "홍길동" not in json.dumps(ev, ensure_ascii=False), ev

        def dup(m, path, body):
            if path.endswith("-page-total"):
                return 1
            x = {"orderId": 7, "transactionType": "ORDER", "vendorItemId": 1, "shippingFeeId": None, "productGmv": 100}
            return {"orderDetails": [x, {**x, "productGmv": 200}], "rawRecordSize": 2, "cursorToken": ""}
        assert r.attempt("주문별매출 202605", lambda: DOC.fetch_order_detail(dup, D("2026-05-01"), D("2026-05-31"))) is None
        ev = json.loads((Path(tmp) / "o" / "_실패_주문별매출_202605.json").read_text(encoding="utf-8"))
        assert [[(x["쪽"], x["productGmv"]) for x in g] for g in ev["같은 키 줄"]] == [[(1, 100), (1, 200)]], ev

    # 광고센터 500 → 밀크런은 따로 2달씩 · 남은 달 = 다 못 받은 달 · 실패 사유 남김
    with tempfile.TemporaryDirectory() as tmp:
        def ad500(m, path, body):
            raise API.SiteChangedError("ServerBusy: /marketing-reporting/v2/graphql → 500")
        s1 = AD.collect(ad500, lambda url: b"PK-milk", Path(tmp), "h-hellojin", D("2026-06-01"), D("2026-10-20"))
        milks = sorted(p_.name for p_ in Path(tmp).glob("*_밀크런_*.xlsx"))
        assert milks == ["h-hellojin_밀크런_202608.xlsx", "h-hellojin_밀크런_202609.xlsx"], milks
        assert len(s1["실패"]) == 1 and s1["실패"][0].startswith("광고센터 202609") and s1["남은 달"] == 4, s1
        s2 = AD.collect(ad500, lambda url: b"PK-milk", Path(tmp), "h-hellojin", D("2026-06-01"), D("2026-10-21"))
        assert len(list(Path(tmp).glob("*_밀크런_*.xlsx"))) == 4 and s2["남은 달"] == 4, s2      # 옛 코드 = 밀크런도 202609 에서 멈춤

        def blocked(m, path, body):
            raise API.ApiBlocked("차단")
        expect(API.ApiBlocked, lambda: AD.collect(blocked, lambda url: b"PK", Path(tmp) / "b", "x", D("2026-06-01"), D("2026-10-20"),
                                                  fatal=(API.ApiBlocked,)), "차단은 그대로")
    ok("월자료 실패 달 건너뛰고 옛 달 · 같은 회차 재시도 없음 · 광고센터 500 이어도 밀크런 · 주문별 매출 실패 근거 파일")


def p55_rg_vendor_fallback():
    print("[P55] 로켓그로스 업체코드(D-214 ⓐ) — 정산현황 원문에 줄이 없어도 정산 요청 기록(ref)·재고현황 원문(vendorId)으로 정함"
          " → 월자료 RG 3종(재고변동·반품·부가세 상세) 받음 · 근거 없으면 윙 전용 그대로")
    import gzip
    import json
    import tempfile
    from types import SimpleNamespace
    sys.path.insert(0, str(ROOT / "tools"))
    import settlement_download as TD
    from coupang_analytics import settlement_docs as DOC
    from coupang_analytics import settlement_docs_request as DR
    from coupang_analytics import settlement_jobs as SJ
    name = "유병욱-(주)고로켓컴퍼니-gorocket23"
    a = SimpleNamespace(account_id="gorocket23")
    args = SimpleNamespace(until="", dry_run=False, cycle_since="2026-11-12T18:00:00")

    def job(acct, ch, ref):
        return SJ.Job(acct, ch, "최종액", "판매수수료", "2025-11-03", "2025-11-09", "2026-01-02", ref=ref)

    def gz(p: Path, rec) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(p, "wt", encoding="utf-8") as fh:
            json.dump(rec, fh)

    def run(tmp: Path, jobs: list) -> tuple:
        """소급 단계(cmd_backfill) 그대로 → 월자료 받기(DOC.collect)에 넘긴 업체코드 · 부가세 상세 요청(DR.plan)의 RG 여부."""
        seen: dict = {}
        log = SimpleNamespace(record=lambda *x, **k: None, saved=lambda *x, **k: None, remaining=lambda *x, **k: None,
                              line=lambda m: None)   # line = [메모리] 줄(D-346)
        pat = [(TD, "BASE", tmp / "정산"), (TD, "JOBS", tmp / "정산" / "_요청기록.json"), (TD, "INVENTORY", tmp / "재고현황_일별"),
               (TD, "LOG", log), (TD, "name_of", lambda _a: name), (TD, "goto", lambda *x: None),
               (TD, "collect_sales", lambda *x: 0),
               (DOC, "collect", lambda *x, **k: (seen.__setitem__("vendor", k.get("vendor")), {"파일": [], "받음": [], "실패": [], "남은 달": 0})[1]),
               (DR, "plan", lambda _jobs, _acct, _t, _n, _s, rg: (seen.__setitem__("rg", rg), [])[1])]
        _patched(pat, lambda: TD.cmd_backfill(a, None, args, jobs))
        return seen.get("vendor"), seen.get("rg")
    raw_empty = {"조회": [{"기간": ["2026-11-01", "2026-11-12"], "응답": {"settlementStatusReports": []}}],
                 "예정": [{"기간": ["2026-11-13", "2026-11-30"], "응답": {"settlementStatusReports": []}}]}
    rg_jobs = [job(name, "로켓그로스", "A01152633-2025-11-03-2025-11-09"), job(name, "윙", ""),
               job("다른-계정-x1", "로켓그로스", "A09999999-2025-11-03-2025-11-09")]
    # ① gorocket23 재현(운용 PC output(36)): 2026-07부터 로켓그로스 정산 0건 → 원문 줄 0 · 정산 요청 기록엔 업체코드가 남아 있음
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        gz(tmp / "정산" / TD.RG_RAW_DIRNAME / name / "2026-11-12.json.gz", raw_empty)
        assert run(tmp, list(rg_jobs)) == ("A01152633", True), run(tmp, list(rg_jobs))
        # 이름 표기만 다른 옛 기록(공백·'_'·'/' — 운용 PC '권미혜_세제곱-sejegop')도 같은 계정(폴더 이름과 같은 규칙)
        assert run(tmp, [job("유병욱_(주)고로켓컴퍼니-gorocket23", "로켓그로스", "A01152633-2025-11-03-2025-11-09")]) == ("A01152633", True)
        # ② 요청 기록에도 없으면 재고현황 원문(① 저장)의 로켓그로스 줄 vendorId(guarisen2024 형) · 비어 있는 줄은 무시
        inv = {"응답": [json.dumps({"viProperties": [{"creturnConfigViewDto": None},
                                                    {"creturnConfigViewDto": {"vendorId": "A01298295"}}]})]}
        gz(tmp / "재고현황_일별" / "gorocket23" / "2026-11-11.json.gz", inv)
        assert run(tmp, [job(name, "윙", "")]) == ("A01298295", True)
        # ③ 근거가 여럿이면 앞 근거(원문 → 요청 기록 → 재고) · 한 근거 안에 업체코드가 둘이면 '' (추측 금지)
        assert run(tmp, list(rg_jobs))[0] == "A01152633", "요청 기록이 재고보다 앞"
        two = [job(name, "로켓그로스", "A01152633-2025-11-03-2025-11-09"), job(name, "로켓그로스", "A01000001-2025-11-10-2025-11-16")]
        assert run(tmp, two) == ("", False)
        gz(tmp / "정산" / TD.RG_RAW_DIRNAME / name / "2026-11-13.json.gz",
           {"조회": [{"응답": {"settlementStatusReports": [{"settlementGroupKey": "A01152633-2026-11-03-2026-11-09"}]}}], "예정": []})
        assert run(tmp, two) == ("A01152633", True), "원문에 줄이 있으면 지금처럼 원문"
    # ④ 근거 0 = 윙 전용(지금과 같음)
    with tempfile.TemporaryDirectory() as tmp:
        assert run(Path(tmp), [job(name, "윙", "")]) == ("", False)
    ok("원문 줄 0 + 요청 기록 업체코드 → RG 받음(gorocket23) · 재고현황 vendorId(guarisen2024) · 둘 이상 = '' · 근거 0 = 윙 전용")


def p53_vat_detail_requests():
    print("[P53] 요청형 월자료 = 부가세 신고 상세 윙·RG(D-171 N8) — 회차 계정당 4건(D-170)·화면 본문 그대로·메뉴로 짝·칸·기간 판정·화면 월 합계 대조")
    import io
    import json
    from datetime import datetime
    from pathlib import Path
    import openpyxl
    from coupang_analytics import settlement_docs_request as DR
    from coupang_analytics import settlement_jobs as SJ
    from coupang_analytics import settlement_wing_api as API
    # ① 계획: 2026-01 부터 말일+15일 지난 달 · 최근 달부터 · 회차 4건 · RG 는 업체코드 있는 계정만 · 정기 요청 상한엔 안 섞임
    jobs: list = []
    now = datetime(2026, 11, 8, 19, 0)
    pk = DR.plan(jobs, "A", D("2026-11-08"), now, "2026-11-08T18:00:00", rg=True)
    assert len(jobs) == 18 and {j.kind for j in jobs} == {SJ.DOC_KIND}, len(jobs)        # 2026-01~09 × 2종(10월 = 11-15 부터)
    assert [(j.report, j.period_start, j.period_end) for j in pk] == [
        ("윙부가세상세", "2026-09-01", "2026-09-30"), ("RG부가세상세", "2026-09-01", "2026-09-30"),
        ("윙부가세상세", "2026-08-01", "2026-08-31"), ("RG부가세상세", "2026-08-01", "2026-08-31")], pk
    assert SJ.plan_requests([], jobs, today=D("2026-11-08"), now=now, per_account_cap=50) == [], "정기 단계는 월자료를 고르지 않음"
    for j in pk:
        SJ.mark_requested(j, now, "r")
    assert DR.plan(jobs, "A", D("2026-11-08"), now, "2026-11-08T18:00:00", rg=True) == [], "같은 회차 예산 다 씀"
    nxt = DR.plan(jobs, "A", D("2026-11-09"), datetime(2026, 11, 9, 19), "2026-11-09T18:00:00", rg=True)
    assert [(j.report, j.period_start[:7]) for j in nxt] == [("윙부가세상세", "2026-07"), ("RG부가세상세", "2026-07"),
                                                             ("윙부가세상세", "2026-06"), ("RG부가세상세", "2026-06")], nxt
    assert {j.report for j in DR.plan([], "W", D("2026-11-08"), now, "", rg=False)} == {"윙부가세상세"}
    # ② 요청 본문 = 화면 JS 그대로(실측 11-08) · RG 기간 = 실제 목록 완료본(2026-01)과 같은 UTC 시각
    j1 = SJ.Job("A", "로켓그로스", SJ.DOC_KIND, "RG부가세상세", "2026-01-01", "2026-01-31", "2026-01-31")
    assert DR.rg_body(j1, 5) == {"sellerReportType": "VAT", "requestTime": "5", "recognitionDateFrom": "2025-12-31T15:00:00.000Z",
                                 "recognitionDateTo": "2026-01-31T14:59:59.999Z", "locale": "ko"}
    jw = SJ.Job("A", "윙", SJ.DOC_KIND, "윙부가세상세", "2026-01-01", "2026-01-31", "2026-01-31")
    assert DR.wing_body(jw) == {"excelType": "MSF_PAYMENT_METHOD_DETAIL", "searchDateType": "CONFIRM_DATE",
                                "recognitionDateRange": {"start": "2026-01-01", "end": "2026-01-31"},
                                "searchDateRange": {"start": "2026-01-01", "end": "2026-01-31"}}
    # ③ 요청: 윙·RG 주소 · 요청번호 기록 · '잠시 후' = 이번 회차 멈춤 · 거절 = 기록하고 멈춤(정산 전체 안 막음)
    sent, recs = [], []

    def post(m, path, body):
        sent.append(path)
        if path == API.WING_REQUEST:
            return {"success": True, "data": 77}
        return {"requestId": "rq", "duplicateRequest": False, "remainingTime": 0}
    a = SJ.Job("A", "윙", SJ.DOC_KIND, "윙부가세상세", "2026-02-01", "2026-02-28", "2026-02-28")
    b = SJ.Job("A", "로켓그로스", SJ.DOC_KIND, "RG부가세상세", "2026-02-01", "2026-02-28", "2026-02-28")
    n = DR.request([a, b], post, save=lambda: None, record=lambda j, r, m: recs.append((j.report, r)), now=lambda: now)
    assert n == 2 and sent == [API.WING_REQUEST, API.RG_REQUEST] and (a.req_id, b.req_id) == ("77", "rq"), (sent, recs)
    assert a.status == b.status == SJ.ST_REQUESTED and recs == [("윙부가세상세", "정상"), ("RG부가세상세", "정상")], recs
    recs.clear()
    c = SJ.Job("A", "로켓그로스", SJ.DOC_KIND, "RG부가세상세", "2026-03-01", "2026-03-31", "2026-03-31")
    n = DR.request([c, a], lambda m, p, bd: {"requestId": "", "duplicateRequest": True, "remainingTime": 3}, save=lambda: None,
                   record=lambda j, r, m: recs.append(r))
    assert n == 0 and recs == ["대기"] and c.status == SJ.ST_PLANNED, recs
    recs.clear()
    n = DR.request([jw], lambda m, p, bd: {"success": False, "data": None, "reason": "x"}, save=lambda: None,
                   record=lambda j, r, m: recs.append(r))
    assert n == 0 and recs == ["실패"], recs
    # ④ 목록: 윙 부가세 상세 줄 = 메뉴 '윙부가세상세' · 같은 달 월정산 주문상세와 섞이지 않게 메뉴로 짝
    cond = '[{"key":"구매확정일", "value":"2026-01-01 - 2026-01-31", "view":true}]'
    wl = API.wing_list_rows([
        {"excelType": "MSF_PAYMENT_METHOD_DETAIL", "status": "FINISHED", "startedAt": "2026-09-17 17:39:05", "downloadUrl": "u1",
         "jsonItems": cond},
        {"excelType": "MSF_PAYMENT_REVENUE_DETAIL", "status": "FINISHED", "startedAt": "2026-09-17 17:40:00", "downloadUrl": "u2",
         "jsonItems": cond}])
    assert [(r.report, r.period_start, r.handle) for r in wl] == [("윙부가세상세", D("2026-01-01"), "u1"),
                                                                 ("주문상세", D("2026-01-01"), "u2")], wl
    jw.status, jw.requested_at = SJ.ST_REQUESTED, "2026-09-17T17:38:00"
    pairs, _ = SJ.match_downloads(wl, [jw])
    assert [r.handle for _j, r in pairs] == ["u1"], pairs

    # ⑤ 받은 파일 판정 — 칸 구성 = 실파일(gyi0101 2026-01) · 합계 = 판매 + 환불(파일 부호) = 화면 월 합계(실측 값)
    def xlsx(sheet, grid):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = sheet
        for r in grid:
            ws.append(list(r))
        bio = io.BytesIO()
        wb.save(bio)
        return bio.getvalue()
    wing = xlsx("Excel Data (1)", [DR.WING_HEAD,
                                   ["8100161496144", "94332319057", "2026-01-01", "상품비", "TAX", 3436936, 372700, 88264, 0, 0, 0],
                                   ["9100160864257", "94332319057", "2026-01-31", "배송비", "TAX", 21000, 0, 0, 21000, 7000, 0]])
    got = DR.check(DR.WING_VAT, wing, D("2026-01-01"), D("2026-01-31"))
    assert got["판매"] == {"카드": 3457936, "현금": 372700, "기타": 88264}, got
    assert got["합계"] == {"카드": 3478936, "현금": 379700, "기타": 88264}, got
    # 2026-05 이후 달 파일 = 둘째 칸 머리글 '옵션 ID'(빈칸 아님 — output (34) 11-09~10 실측 158건) · 칸 순서 같음 → 같이 읽음(D-188)
    head05 = (DR.WING_HEAD[0], "옵션 ID") + DR.WING_HEAD[2:]
    wing05 = xlsx("Excel Data (1)", [head05, ["13103037814653", "95907631792", "2026-05-26", "상품비", "TAX", 12700, 0, 0, 0, 0, 0]])
    got = DR.check(DR.WING_VAT, wing05, D("2026-05-01"), D("2026-05-31"))
    assert got["줄"] == 1 and got["합계"] == {"카드": 12700, "현금": 0, "기타": 0}, got
    got = DR.check(DR.WING_VAT, xlsx("Excel Data (1)", [head05]), D("2026-06-01"), D("2026-06-30"))
    assert got["줄"] == 0 and got["합계"] == {"카드": 0, "현금": 0, "기타": 0}, got     # 판매 없는 달 = 머리글만
    expect(API.SiteChangedError, lambda: DR.check(DR.WING_VAT, xlsx("Excel Data (1)", [(DR.WING_HEAD[0], "상품 ID") + DR.WING_HEAD[2:]]),
                                                  D("2026-05-01"), D("2026-05-31")), "둘째 칸이 다른 이름")
    rg = xlsx("부가세 신고자료", [[None] * 11, DR.RG_HEAD,
                               ["1", "9", "2026-01-01", "2026-01", "TAX", 22255835, 6323656, 833309, "-", "-", "-"],
                               ["2", "9", "2026-01-31", "2026-01", "TAX", "-", "-", "-", -3843221, -773859, -147454],
                               [None] * 11])
    got = DR.check(DR.RG_VAT, rg, D("2026-01-01"), D("2026-01-31"))
    assert got["줄"] == 2 and got["합계"] == {"카드": 18412614, "현금": 5549797, "기타": 685855}, got
    expect(API.SiteChangedError, lambda: DR.check(DR.RG_VAT, rg, D("2026-02-01"), D("2026-02-28")), "다른 달 파일")
    expect(API.SiteChangedError, lambda: DR.check(DR.WING_VAT, rg, D("2026-01-01"), D("2026-01-31")), "머리글 다름(RG 파일을 윙으로)")
    expect(API.SiteChangedError, lambda: DR.check(DR.WING_VAT, b"<html>", D("2026-01-01"), D("2026-01-31")), "엑셀 아님")
    with tempfile.TemporaryDirectory() as tmp:
        folder, vp = Path(tmp) / "월자료" / "A", Path(tmp) / "A.json"
        ref = {"wing_vat": {"paymentMethodReports": [{"yearMonth": "202601", "card": 3478936, "cash": 379700, "etc": 88264,
                                                      "total": 3946900}]},
               "rg_vat": {"vatResponseAggregatedDtos": [{"yearMonth": "2026-01", "creditCardPaymentAmountAgg": 18412614.0,
                                                         "cashPaymentAmountAgg": 5549797.0, "otherPaymentAmountAgg": 1742829.0,
                                                         "sellerFundedCouponAggAmount": 1056974.0}]}}
        vp.write_text(json.dumps(ref), encoding="utf-8")
        jw.status = j1.status = SJ.ST_REQUESTED
        ok1, m1 = DR.keep(wing, jw, folder, vp)
        ok2, m2 = DR.keep(rg, j1, folder, vp)
        assert ok1 and ok2 and "일치" in m1 and "일치" in m2 and jw.status == j1.status == SJ.ST_DONE, (m1, m2)
        assert (folder / "윙부가세상세_202601.xlsx").read_bytes() == wing and j1.file == "월자료/A/RG부가세상세_202601.xlsx"
        vp.write_text(json.dumps({"wing_vat": {"paymentMethodReports": [{"yearMonth": "202601", "card": 1, "cash": 379700,
                                                                          "etc": 88264}]}}), encoding="utf-8")
        ok3, m3 = DR.keep(wing, jw, folder, vp)
        assert not ok3 and "다름" in m3 and "확인 필요" in m3, m3
        ok4, m4 = DR.keep(rg, j1, folder, vp)
        assert ok4 and "대조 못 함" in m4, m4
        # ⑥ 앱 받기 단계: 월자료 작업 = 판정·저장(정산 파일 처리 안 탐) · 합계 다르면 '실패' 줄
        sys.path.insert(0, str(ROOT / "tools"))
        import settlement_download as TD
        logs: list = []
        jw.status = SJ.ST_REQUESTED
        row = SJ.DownloadRow("윙", datetime(2026, 9, 17, 17, 39), "FINISHED", "윙부가세상세", handle="u1")
        _patched([(TD, "VERIFY", Path(tmp)), (TD, "_get_bytes", lambda b_, url, text_ok=False: wing),
                  (TD, "LOG", _fake_log(record=lambda *a, **k: logs.append(a)))],
                 lambda: TD._fetch_one(None, jw, row, "A"))
        assert logs and logs[-1][1] == "받기" and logs[-1][2] == TD.RL.FAIL and jw.status == SJ.ST_DONE, logs
    ok("부가세 상세 = 최근 달부터 회차 4건·정기와 분리 · 화면 본문 그대로 · 메뉴로 짝 · 칸·기간 판정 · 판매+환불 = 화면 월 합계(RG 기타−쿠폰)")


def p57_backlog_all_accounts():
    print("[P57] [실행 결과 종합] 남은 소급 = 바퀴 끝에 전 계정 저장 자료로 다시 셈(T-46 ⑤ · output (37) 보고 B ⑤) —"
          " 로그인 못 한 계정·중단된 바퀴도 판매분석·월자료·광고 남은 양이 잡힘")
    import json
    import os
    from datetime import timedelta
    from types import SimpleNamespace
    sys.path.insert(0, str(ROOT / "tools"))
    import settlement_download as TD
    from coupang_analytics import settlement_ads as AD
    from coupang_analytics import settlement_docs as DOC
    today = date.today()
    sales_all = (today - timedelta(days=1) - D("2026-01-01")).days + 1                # 1/1~어제 전부 빔
    wing_kinds = [k for k in DOC.KINDS if k not in DOC.RG_KINDS]
    docs_all = sum(len(DOC.due_months(k, today)) for k in wing_kinds)
    ads_all = len(AD.due_months(AD.FROM, today))

    class FakeLog:
        run_id, accounts = "t", []

        def __init__(self, base):
            self.rows, self.files, self.left = [], [], {}

        def heartbeat(self, *a, **k):
            pass

        def summary(self, **k):
            pass

        def line(self, m):
            pass

        def record(self, *a, **k):
            pass

        def saved(self, *a, **k):
            pass

        def remaining(self, account, kind, n, unit):
            self.left[(account, kind)] = (int(n), unit)
    accts = [SimpleNamespace(account_id="a1", nm="A-a1"), SimpleNamespace(account_id="b2", nm="B-b2")]

    def run_accounts(accts_, run, args):           # A 만 소급 단계를 돌고 '판매분석 0' 을 남김 · B = 로그인 실패(남은 값 없음)
        if run is TD.cmd_backfill:
            TD.LOG.remaining("A-a1", "판매분석", 0, "일")
        return 0
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "output" / "판매분석_일별").mkdir(parents=True)
        os.chdir(t)
        try:
            # A = 판매분석 1/1~어제 다 받음 · 월자료 주문별매출 1달 받음 · 광고 1달 받음(밀크런+광고정산+매출성장광고)
            days = {(D("2026-01-01") + timedelta(days=i)).isoformat(): {"수집": "x"} for i in range(sales_all)}
            (t / "output" / "판매분석_일별" / "a1.json").write_text(json.dumps(days), encoding="utf-8")
            ym = DOC.due_months("주문별매출", today)[0][0]
            (t / "v" / "월자료" / "A-a1").mkdir(parents=True)
            (t / "v" / "월자료" / "A-a1" / DOC.LEDGER).write_text(json.dumps({"주문별매출": {ym: "x"}}), encoding="utf-8")
            am = AD.due_months(AD.FROM, today)[-1][0]
            (t / "v" / "광고").mkdir(parents=True)
            for f in (f"A-a1_밀크런_{am}.xlsx", f"A-a1_광고정산_{am}.json", f"A-a1_매출성장광고_{am}.xlsx"):
                (t / "v" / "광고" / f).write_bytes(b"x")
            cycle = TD.RL.Totals()
            pat = [(TD.RL, "RunLog", FakeLog), (TD, "load_accounts", lambda only: accts), (TD, "_stats_in_child", lambda: None),
                   (TD, "name_of", lambda a: a.nm), (TD, "_pending_jobs", lambda: 0), (TD, "CYCLE", cycle),
                   (TD, "VERIFY", t / "v"), (TD, "BASE", t / "b"), (TD, "INVENTORY", t / "inv"), (TD, "JOBS", t / "b" / "_요청기록.json"),
                   (TD, "_run_accounts", run_accounts)]
            _patched(pat, lambda: TD._one_pass(SimpleNamespace(start=D("2026-01-01"), until="", dry_run=False)))
        finally:
            os.chdir(cwd)
    left = cycle.left
    assert left.get(("B-b2", "판매분석")) == (sales_all, "일"), left                     # 옛 코드 = B 줄 없음(남은 소급 적게 셈)
    assert left.get(("B-b2", "월자료")) == (docs_all, "달"), left
    assert left.get(("B-b2", "광고")) == (ads_all, "달"), left
    assert left.get(("A-a1", "판매분석")) == (0, "일") and left.get(("A-a1", "월자료")) == (docs_all - 1, "달"), left
    assert left.get(("A-a1", "광고")) == (ads_all - 1, "달"), left
    block = "\n".join(TD.RL.result_block(cycle))
    assert f"판매분석 {sales_all}일(1계정)" in block, block
    ok("바퀴 끝 전 계정 다시 셈 — 로그인 못 한 계정 판매분석·월자료·광고 전부 · 받은 계정은 저장 자료 기준")


def p58_stats_keep_latest():
    print("[P58] 정산집계 = 최신 3개만 output/정산 · 나머지는 보관/YYYY-MM/(파일 이름 날짜) 로 이동 · 삭제 없음(D-243 ② · T-46)")
    from coupang_analytics import settlement_store as STORE
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        names = ["정산집계_260930_180001.xlsx", "정산집계_261001_180001.xlsx", "정산집계_261101_180001.xlsx",
                 "정산집계_261114_180001.xlsx", "정산집계_261115_010229.xlsx"]
        for i, n in enumerate(names):
            (base / n).write_bytes(bytes([i]))
        (base / "정산집계_수동.xlsx").write_bytes(b"m")                                     # 이름 규칙 밖 = 손대지 않음
        moved = STORE.rotate_stats(base)
        assert sorted(p.name for p in base.glob("정산집계_*.xlsx")) == ["정산집계_261101_180001.xlsx", "정산집계_261114_180001.xlsx",
                                                                      "정산집계_261115_010229.xlsx", "정산집계_수동.xlsx"]
        assert (base / "보관" / "2026-09" / names[0]).read_bytes() == b"\x00" and (base / "보관" / "2026-10" / names[1]).exists()
        assert moved == 2 and STORE.rotate_stats(base) == 0, moved                          # 멱등
    ok("정산집계 최신 3개 · 옛 것 보관/YYYY-MM 이동 · 이름 규칙 밖 그대로 · 멱등")


def p59_suspended_pending():
    print("[P59] 정지 계정(_계정정지.json · D-199)의 요청됨·요청예정 = 회차 완료 판단 수에서 뺌 · 받기는 계속(D-215) ·"
          " [실행 결과 종합] '정지 계정 대기 N건 — 확인 필요' 따로 표시(T-46 ⑦ · output (37) hide4u 9건 · 소유자 A안)")
    import json
    import os
    from types import SimpleNamespace
    sys.path.insert(0, str(ROOT / "tools"))
    import settlement_download as TD
    from coupang_analytics import settlement_jobs as SJ
    from coupang_analytics import settlement_runlog as RLG
    from coupang_analytics import settlement_watch as W
    hide = "장성원-온라이프-(계정사용불가)-hide4u"
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            Path("output").mkdir()
            Path("output/_계정정지.json").write_text(json.dumps({"hide4u": {"업체코드": "", "struck_at": "2026-11-11T18:23:40"}}),
                                                    encoding="utf-8")
            jobs = Path(tmp) / "_요청기록.json"
            js = [SJ.Job(hide, "윙", "주정산", f"r{i}", "2026-01-05", "2026-01-11", "2026-01-30", status=SJ.ST_REQUESTED)
                  for i in range(9)]
            js += [SJ.Job("가-dehide4u", "윙", "주정산", "x", "2026-01-05", "2026-01-11", "2026-01-30", status=SJ.ST_PLANNED),
                   SJ.Job(hide, "윙", "주정산", "done", "2026-01-05", "2026-01-11", "2026-01-30", status=SJ.ST_DONE)]
            SJ.save_jobs(jobs, js)
            pending, susp = _patched([(TD, "JOBS", jobs)], lambda: (TD._pending_jobs(), TD._suspended_pending()))
            assert pending == 1, pending                                   # 옛 코드 = 10 → 'later' 반복(회차 '완료' 못 함)
            assert susp == {hide: 9}, susp                                 # '-dehide4u' 는 다른 계정(끝이 '-hide4u' 아님)
            lg = SimpleNamespace(rows=[], unresolved_failures=lambda: {})
            fails = _patched([(TD, "JOBS", jobs), (TD, "LOG", lg)], TD._watch_failures)
            assert fails == {hide: "정지 계정 받기 대기"}, fails
            act, why = W.plan_after_pass(False, 0, 0, 0, failed=fails)
            assert act == "done" and "확인 필요" in why and W.done_status(len(fails)) == "완료·실패 확인", (act, why)
        finally:
            os.chdir(cwd)
    with tempfile.TemporaryDirectory() as tmp:
        lg = RLG.RunLog(Path(tmp), echo=lambda m: None)
        lg.remaining(hide, "판매분석", 0, "일")
        b = RLG.result_block(lg, suspended={hide: 9})
        assert b[1] == "판정: 일부 실패 --> 확인 필요", b[1]
        assert f"정지 계정 대기 9건 — 확인 필요(완료 판단에서 뺌 · 받기는 계속 D-215)" in b, b
        assert f"  - {hide}: 9건" in b and "정지 계정 대기 9" in b[-1], b
        assert "정지 계정 대기" not in "\n".join(RLG.result_block(lg)), "정지 계정 없으면 줄 없음(지금 그대로)"
    ok("정지 계정 대기 = 완료 판단에서 뺌 · 따로 '확인 필요' 표시 · 완료·실패 확인 · 다른 계정 이름 끝 혼동 없음")


def _t113_fake_log(rows: list, beats: list):
    class FakeLog:
        run_id, files, left, accounts = "t", [], {}, []
        csv = Path("처리기록_t.csv")

        def __init__(self, *a, **k):
            self.rows = rows

        def record(self, acct, step, result, reason="", **k):
            rows.append({"계정": acct, "단계": step, "결과": result, "사유": reason})

        def error(self, acct, step, exc, *a, **k):
            rows.append({"계정": acct, "단계": step, "결과": "실패", "사유": repr(exc)})

        def heartbeat(self, status, detail="", **k):
            beats.append((status, detail))

        def line(self, m):
            beats.append(("줄", m))

        def summary(self, **k):
            pass
    return FakeLog


def p60_memory_floor_finally():
    print("[P60] T-113 (다) 바퀴 끝 finally 의 MemoryError(11-18 06:53 _backlog_left) — 밖으로 새지 않고(처리 안 된 예외 창 없음)"
          " 처리기록 '실패'·_현재상태 '메모리 부족' 기록 · 처리 안 된 MemoryError = 기록 후 종료코드 3")
    from types import SimpleNamespace
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import settlement_download as TD
    rows, beats = [], []

    def boom(*a):
        raise MemoryError()
    pat = [(TD.RL, "RunLog", _t113_fake_log(rows, beats)), (TD, "load_accounts", lambda only: ["a"]),
           (TD, "_stats_in_child", lambda: None), (TD, "name_of", lambda a: a), (TD, "_pending_jobs", lambda: 0),
           (TD, "_suspended_pending", lambda: {}), (TD, "CYCLE", TD.RL.Totals()), (TD, "_run_both", lambda accts, a: 0),
           (TD, "_backlog_left", boom), (TD, "_RESERVE", [bytearray(1)])]
    stopped, _work = _patched(pat, lambda: TD._one_pass(SimpleNamespace(start=D("2026-01-01"), until="", dry_run=False)))
    assert stopped is False, stopped                                      # 옛 코드 = MemoryError 가 _one_pass 밖으로 샘(재현 확인)
    fail = [r for r in rows if r["단계"] == "남은 소급 계산"]
    assert fail and fail[0]["결과"] == TD.RL.FAIL and "메모리 부족" in fail[0]["사유"] and "커밋" in fail[0]["사유"], rows
    assert any("메모리 부족" in d for s, d in beats if s == "작동중"), beats
    rows.clear(), beats.clear()
    log = _t113_fake_log(rows, beats)()
    rc = _patched([(TD, "LOG", log), (TD, "_RESERVE", [bytearray(1)])], lambda: TD._memory_floor_exit(MemoryError()))
    assert rc == 3 and beats[-1][0] == "종료" and "메모리 부족" in beats[-1][1], beats
    assert any(r["단계"] == "정산 종료" and r["결과"] == TD.RL.FAIL for r in rows), rows
    ok("finally MemoryError = 처리기록 '실패'(커밋 MB 포함)·상태 '메모리 부족' · 바퀴는 실패로 끝나고 감시는 계속 · 처리 안 된 것 = 기록 후 3")


def p61_self_exit_when_taskkill_fails():
    print("[P61] T-113 (다) 앱 종료 감시의 자기 종료 — taskkill 이 안 먹어도(11-18 07:00:02 메모리 바닥) 사유 기록 후 프로세스 직접 종료")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import settlement_download as TD
    from coupang_analytics import app_process as AP

    class Exited(BaseException):
        pass

    def fake_exit(code):
        raise Exited(code)
    for heartbeat_fails in (False, True):
        rows, beats = [], []
        log = _t113_fake_log(rows, beats)()
        if heartbeat_fails:
            def hb(*a, **k):
                raise MemoryError()
            log.heartbeat = hb
        pat = [(TD, "LOG", log), (AP, "watch_parent", lambda pid, fn: fn()),
               (AP, "kill_self_tree", lambda: "taskkill 종료코드 128"), (TD.os, "_exit", fake_exit)]
        try:
            _patched(pat, lambda: TD._watch_app(4321))
            raise AssertionError("자기 종료 안 함")                     # 옛 코드 = kill_self_tree 가 돌아오면 그대로 살아 있음
        except Exited as e:
            assert e.args == (1,), e.args
        if not heartbeat_fails:
            assert "자기 종료 명령 실패(taskkill 종료코드 128)" in beats[-1][1], beats
    real = AP.subprocess.run

    def no_proc(*a, **k):
        raise OSError("가짜 — 새 프로세스 못 만듦")
    AP.subprocess.run = no_proc
    try:
        assert AP.kill_self_tree() == "taskkill 실행 실패 OSError"
    finally:
        AP.subprocess.run = real
    ok("taskkill 실패·기록 실패 둘 다 os._exit(1) · 상태에 '자기 종료 명령 실패(사유)' · kill_self_tree 는 실패 사유 반환")


def p62_stats_separate_process():
    print("[P62] T-113 (나) 바퀴 끝 정산 집계 = 별도 짧은 프로세스(stats --run-id --result) — 같은 실행 로그에 이어 씀·"
          "상태 파일 안 덮음·집계 파일 기록 · 자식 실패 = 종료코드·오류 로그로 바퀴 '실패'")
    import os
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import settlement_download as TD
    cwd, env_old = os.getcwd(), {k: os.environ.get(k) for k in ("COUPANG_DATA_ROOT", "LOCALAPPDATA")}
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        for sub in ("파일/비용", "쿠팡지급내역", "검증자료"):
            (t / "output" / "정산" / sub).mkdir(parents=True)
        os.environ["COUPANG_DATA_ROOT"], os.environ["LOCALAPPDATA"] = str(t), str(t)   # 자식도 같은 데이터 폴더 · 키 없음(API 안 부름)
        os.chdir(t)
        try:
            log = TD.RL.RunLog(TD.BASE)
            log.heartbeat("작동중", "부모 상태")
            _patched([(TD, "LOG", log)], TD._stats_in_child)
            outs = [f for a, f, n in log.files if n == "정산 집계"]
            assert len(outs) == 1 and Path(outs[0]).exists() and Path(outs[0]).parent == (t / "output" / "정산").resolve(), log.files
            text = log.text.read_text(encoding="utf-8")
            assert "명령 stats" in text and "집계 정산 파일 0개" in text and "집계 뒤 · 정산 프로세스 커밋" in text \
                and "정산 집계 = 별도 프로세스(최고 커밋" in text and text.count("[메모리]") >= 3, text   # ⚠ 여부 = 이 PC 상태
            assert "집계 시작 · 집계 프로세스 커밋" in text and "집계 끝 · 집계 프로세스 커밋" in text, \
                "자식도 같은 실행 로그에 [메모리] 줄(D-346 ④)"
            assert "부모 상태" in log.status.read_text(encoding="utf-8"), "자식이 _현재상태.txt 를 덮지 않음"
            assert not list(log.dir.glob("_집계결과_*.json")), "결과 JSON 은 읽고 지움"
            assert not list(log.dir.glob("처리기록_*.csv")) or log.csv.exists(), "새 실행ID 기록 파일 안 만듦"
            (t / "output" / "정산" / "파일" / "깨짐.xlsx").write_bytes(b"not a zip")
            try:
                _patched([(TD, "LOG", log)], TD._stats_in_child)
                raise AssertionError("자식 실패를 숨김")
            except RuntimeError as exc:
                assert "종료코드 1" in str(exc) and log.errors.name in str(exc), exc
            assert "정산 집계" in log.errors.read_text(encoding="utf-8"), "자식 추적은 같은 실행ID 오류 로그"
        finally:
            os.chdir(cwd)
            for k, v in env_old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    ok("자식 프로세스 집계 → 같은 실행 로그·집계 파일 기록·상태 파일 그대로 · 깨진 파일 = 자식 종료코드 1 + 같은 오류 로그 → 바퀴 실패")


def p63_own_chrome_sweep():
    print("[P63] T-113 (라) 바퀴 사이 Chrome 정리 = 정산 프로세스 자손만(앱·소유자·부모 없는 앱 몫 안 건드림) · 수·메모리 기록")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import settlement_download as TD
    from coupang_analytics import settlement_memory as MEM
    MB = 1 << 20
    text = "\n".join("\t".join(map(str, r)) for r in (
        (200, 100, 300 * MB, 1, 1, 1), (201, 200, 50 * MB, 1, 0, 1), (202, 201, 10 * MB, 1, 0, 1),   # 정산(100)이 띄운 Chrome 트리
        (300, 50, 200 * MB, 1, 1, 1), (301, 300, 40 * MB, 1, 0, 1),                                  # 앱(50) Chrome
        (400, 60, 500 * MB, 0, 1, 1),                                                                 # 소유자 Chrome
        (500, 999, 100 * MB, 1, 1, 0), (501, 500, 20 * MB, 1, 0, 1)))                                 # 부모 없는 우리 Chrome(앱 몫 잔여)
    rows = MEM.parse_census(text + "\n")
    assert MEM.own_tree(rows, 100) == [200, 201, 202], MEM.own_tree(rows, 100)
    assert MEM.summarize(rows, [200, 201, 202]) == {"전체": 8, "전체MB": 1220, "우리": 7, "부모없는우리": 1, "정산자손": 3}
    expect(ValueError, lambda: MEM.parse_census("1\t2\t3\n"), "형식 다른 줄 = 오류(조용히 빼지 않음)")
    killed, calls = [], [0]

    def census(_d):
        calls[0] += 1
        return rows if calls[0] == 1 else [r for r in rows if r["pid"] not in (200, 201, 202)]
    real = MEM.subprocess.run
    MEM.subprocess.run = lambda cmd, **k: killed.append(cmd)
    try:
        n = _patched([(MEM, "_census", census)], lambda: MEM.sweep_own_chrome(root_pid=100))
    finally:
        MEM.subprocess.run = real
    assert killed == [["taskkill", "/F", "/T", "/PID", "200"]], killed           # 맨 위 하나만 트리째 · 300·400·500 안 건드림
    assert n["종료"] == 3 and n["남은자손"] == 0 and n["부모없는우리"] == 1, n
    beats = []
    log = _t113_fake_log([], beats)()
    _patched([(TD, "LOG", log), (MEM, "sweep_own_chrome", lambda: n)], TD._between_passes)
    line = beats[-1][1]
    assert "남은 Chrome 3개 종료(남음 0)" in line and "PC Chrome 8개" in line and "부모 없는 우리 Chrome 1개" in line \
        and "정산 프로세스 커밋" in line, line

    def fail():
        raise OSError("가짜 조회 실패")
    _patched([(TD, "LOG", log), (MEM, "sweep_own_chrome", fail)], TD._between_passes)
    assert "⚠ Chrome 확인 실패(OSError" in beats[-1][1], beats[-1]
    ok("자손 3개만 taskkill /T(맨 위 1번) · 앱·소유자·부모 없는 앱 몫 그대로 · 전체 수·MB·남은 수·커밋 기록 · 조회 실패 사유 기록")


def _fake_mem(samples: list):
    """가짜 측정 Tracker — samples 를 차례로 돌려줌(마지막 값 반복) · 시각 고정 01:02:03."""
    from datetime import datetime
    from coupang_analytics import memory_log as ML
    seq = list(samples)
    return ML.Tracker("정산 프로세스", measure_fn=lambda: seq.pop(0) if len(seq) > 1 else seq[0],
                      clock=lambda: datetime(2026, 11, 19, 1, 2, 3))


def p64_memory_log_line():
    print("[P64] D-346 ④ [메모리] 줄 — 프로세스 커밋·PC 사용 가능/전체·Chrome 수·MB · 기준선(PC < 15% · 프로세스 > 1GB) ⚠메모리 · "
          "측정 못 함도 그 칸에 사유 · 종합 한 줄(최고 시각·단계·⚠ 횟수) · 별도 프로세스 합침")
    from coupang_analytics import memory_log as ML
    S = ML.Sample
    t = _fake_mem([S((500, 600), (8000, 16000), (10, 900, 0))])
    ln = t.line("바퀴 시작")
    assert ln == ("  [메모리] 바퀴 시작 · 정산 프로세스 커밋 500MB(최고 600MB) · PC 사용 가능 8000/16000MB(50%) · "
                  "Chrome 10개 900MB"), ln
    t = _fake_mem([S((300, 300), "", ""), S((1100, 1300), (2000, 16000), (207, 9000, 3)),
                   S("측정 못 함(OSError: 가짜)", (9000, 16000), "측정 못 함(OSError: 스냅샷)")])
    lines: list = []
    with t.around("검증 수집 A", lines.append):
        pass
    ln = lines[0]
    assert ln.startswith("  [메모리] ⚠메모리(PC 사용 가능 12% < 15% · 정산 프로세스 1100MB > 1024MB) 검증 수집 A 뒤 · ") \
        and "커밋 1100MB(최고 1300MB) · 전 300MB → +800MB" in ln and "Chrome 207개 9000MB(메모리 못 읽은 3개)" in ln, ln
    ln = t.line("계정 끝")
    assert "정산 프로세스 커밋 측정 못 함(OSError: 가짜)" in ln and "Chrome 측정 못 함(OSError: 스냅샷)" in ln \
        and "⚠메모리" not in ln, ln
    for x in (lines[0], ln):
        assert "❌" not in x and "실패" not in x, f"오류 판정 단어 없음(앱 종합 오류 수에 안 섞임) {x}"
    assert t.summary() == ("[메모리] 최고 커밋 1300MB(01:02:03 검증 수집 A 뒤) · PC 사용 가능 최저 12%(01:02:03 검증 수집 A 뒤) · "
                           "⚠메모리 1회(기준 PC 사용 가능 < 15% 또는 프로세스 > 1024MB) · 측정 2회(못 잰 칸 2개)"), t.summary()
    child = _fake_mem([S((1229, 1345), (1500, 16000), (5, 100, 0))])
    child.line("집계 끝")
    t.merge(child.state(), "집계 프로세스")
    s = t.summary()
    assert "최고 커밋 1345MB(01:02:03 집계 프로세스 집계 끝)" in s and "최저 9%(01:02:03 집계 프로세스 집계 끝)" in s \
        and "⚠메모리 2회" in s and "측정 3회" in s, s
    assert ML.Tracker("x", measure_fn=lambda: None).summary() == "[메모리] 이번 실행 측정 0회 — 기록 없음(확인 필요)"

    def boom():
        raise OSError("kernel32 없음")
    assert ML._try(boom).startswith("측정 못 함(OSError"), "측정 실패는 사유 문자열(실행 계속 · 폴백 값 없음)"
    real = ML.measure()                                    # 실제 PC(Windows) 한 번 — 새 프로세스 없이 숫자 셋
    assert isinstance(real.proc, tuple) and isinstance(real.pc, tuple) and isinstance(real.chrome, tuple), real
    ok("줄 형식·⚠ 두 기준·증가분·측정 못 함 사유·종합(최고·최저 시각·단계·⚠ 횟수)·자식 합침 · 실제 측정 숫자 셋")


def p65_settlement_memory_lines():
    print("[P65] D-346 ④ 정산 단계 경계 [메모리] — 바퀴 시작·집계 전·집계 뒤(자식 최고 합침)·계정마다·검증·광고·판매분석 전후 · "
          "회차 [실행 결과 종합]에 메모리 한 줄")
    from types import SimpleNamespace
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import settlement_download as TD
    from coupang_analytics import memory_log as ML
    S = ML.Sample
    rows, beats = [], []
    mem = _fake_mem([S((40, 50), (8000, 16000), (3, 300, 0))])
    pat = [(TD.RL, "RunLog", _t113_fake_log(rows, beats)), (TD, "load_accounts", lambda only: ["a"]), (TD, "MEMLOG", mem),
           (TD, "_stats_in_child", lambda: None), (TD, "name_of", lambda a: a), (TD, "_pending_jobs", lambda: 0),
           (TD, "_suspended_pending", lambda: {}), (TD, "CYCLE", TD.RL.Totals()), (TD, "_run_both", lambda accts, a: 0),
           (TD, "_backlog_left", lambda accts, a: None)]
    _patched(pat, lambda: TD._one_pass(SimpleNamespace(start=D("2026-01-01"), until="", dry_run=False)))
    text = [m for s, m in beats if s == "줄"]
    assert any("[메모리] 바퀴 시작 · 정산 프로세스 커밋 40MB" in m for m in text) and any("[메모리] 집계 전 ·" in m for m in text), text
    calls, beats[:] = [], []
    log = _t113_fake_log(rows, beats)()
    pats = [(TD, "cmd_request", lambda *a: None), (TD, "cmd_download", lambda *a: None), (TD.time, "sleep", lambda s: None),
            (TD, "collect_verify", lambda *a: calls.append("검증")), (TD, "collect_ads", lambda *a: calls.append("광고")),
            (TD, "collect_sales", lambda *a: 0), (TD, "collect_docs", lambda *a: 0), (TD, "request_docs", lambda *a: 0),
            (TD, "name_of", lambda a: "A"), (TD, "LOG", log), (TD, "MEMLOG", mem)]
    args = SimpleNamespace(dry_run=False, until="", start=D("2026-01-01"), command="watch", hidden=True)
    _patched(pats, lambda: (TD.cmd_run(None, None, args, []), TD.cmd_backfill(None, None, args, [])))
    text = [m for s, m in beats if s == "줄"]
    for stage in ("검증 수집 A 뒤", "광고(보고서 TSV→xlsx) A 뒤", "판매분석·쿠폰 A 뒤"):
        assert any(f"[메모리] {stage} · 정산 프로세스 커밋 40MB(최고 50MB) · 전 " in m for m in text), (stage, text)
    beats[:] = []

    @contextmanager
    def fake_session(*a, **k):
        yield None

    def cmd_backfill(a, b, args, jobs):          # 가짜 단계 — 이름 cmd_backfill → 줄 단계 '소급'
        pass
    _patched([(TD, "LOG", log), (TD, "MEMLOG", mem), (TD, "session", fake_session), (TD, "name_of", lambda a: a),
              (TD, "past_until", lambda a: False), (TD.SJ, "load_jobs", lambda p: [])],
             lambda: TD._run_accounts(["가", "나"], cmd_backfill, args))
    text = [m for s, m in beats if s == "줄"]
    assert any("[메모리] 소급 가 끝 ·" in m for m in text) and any("[메모리] 소급 나 끝 ·" in m for m in text), text
    beats[:] = []
    cyc = TD.RL.Totals()
    cyc.passes = 1
    _patched([(TD, "LOG", log), (TD, "MEMLOG", mem), (TD, "CYCLE", cyc), (TD, "_pending_jobs", lambda: 0),
              (TD, "_suspended_pending", lambda: {}),
              (TD.RL, "result_block", lambda *a, **k: ["===== [실행 결과 종합] =====", "판정: 완료", "==> 완료"])],
             lambda: TD._cycle_close("완료", "끝"))
    text = [m for s, m in beats if s == "줄"]
    assert text[-2].startswith("[메모리] 최고 커밋 50MB(01:02:03 바퀴 시작)") and text[-1] == "==> 완료", text
    ok("바퀴 시작·집계 전 · 검증·광고·판매분석 뒤(전 값·증가분) · 계정마다 · 회차 종합 끝 '==>' 바로 위에 메모리 한 줄")


def p66_openblas_one_thread():
    print("[P66] T-113 D-346 OpenBLAS 1스레드 — 정산 프로그램을 읽은 자식 프로세스가 openpyxl·numpy 를 불러도 커밋 < 100MB "
          "(옛 = 22스레드 노트북 9→703MB) · 앱 진입점도 numpy 를 부를 import 보다 먼저")
    import os
    import subprocess
    code = ("import importlib.util, sys\n"
            f"spec = importlib.util.spec_from_file_location('sd', {str(ROOT / 'tools' / 'settlement_download.py')!r})\n"
            "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
            "import openpyxl, numpy, os\n"
            "from coupang_analytics import settlement_memory as M\n"
            "print(os.environ.get('OPENBLAS_NUM_THREADS'), M.commit_mb()[0])\n")
    env = {k: v for k, v in os.environ.items() if k != "OPENBLAS_NUM_THREADS"}
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 0, r.stderr[-500:]
    val, mb = r.stdout.split()[-2:]
    assert val == "1" and int(mb) < 100, f"OPENBLAS_NUM_THREADS={val} · 커밋 {mb}MB"
    src = (ROOT / "ui" / "app_qt.py").read_text(encoding="utf-8")
    at = src.index('os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")')
    assert at < src.index("from coupang_analytics"), "앱: numpy 를 부를 수 있는 우리 모듈 import 보다 먼저"
    ok(f"정산 프로그램 자식 = OPENBLAS_NUM_THREADS 1 · openpyxl+numpy 뒤 커밋 {mb}MB(< 100MB) · 앱 진입점 순서 맞음")


def p67_manual_start():
    print("[P67] 정산 탭 '정산 시작'(--manual · D-354) — 이번 회차 '완료' 기록·①완료 대기 없이 바로 받음 · ①이 도는 중이면 대기 · "
          "무인(18:00)·전체실행은 그대로")
    import json as _json
    import os
    from datetime import datetime as RealDT, timedelta
    from types import SimpleNamespace
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import settlement_download as TD
    from coupang_analytics import app_process as AP
    from coupang_analytics import settlement_runlog as RLG
    from coupang_analytics import settlement_watch as W
    D = RealDT
    assert AP.settlement_watch_cmd(4321, manual=True)[0][-4:] == ["watch", "--parent", "4321", "--manual"]
    assert "--manual" not in AP.settlement_watch_cmd(4321)[0], "무인(18:00)은 그대로"
    assert "--manual" not in AP.settlement_watch_cmd(4321, since=D(2026, 11, 19, 9))[0], "전체실행은 그대로"
    panel = (ROOT / "ui" / "settlement_status_panel_qt.py").read_text(encoding="utf-8")
    assert "start_settlement_watch(self.log, manual=True)" in panel, "정산 탭 버튼 = 수동 모드"

    def run(manual, marker_at, busy=False):
        clock = {"now": D(2026, 11, 19, 11, 22, 29)}
        passes = []
        stage = Path("output") / "쿠팡데이타분석_실행단계.json"
        if marker_at:
            stage.write_text(_json.dumps({"date": f"{marker_at:%Y-%m-%d}", "stage": "sales", "at": marker_at.isoformat()}),
                             encoding="utf-8")
        W.write_done(TD.DONE_FILE, marker_at.isoformat(timespec="seconds") if marker_at else "x", "done",
                     "받을 수 있는 정산 파일 다운로드 완료", failed=7)

        class FakeDT(RealDT):
            @classmethod
            def now(cls, tz=None):
                return clock["now"]

        def fake_sleep(sec):
            clock["now"] += timedelta(seconds=max(sec, 1))
        olds = (TD.datetime, TD.time.sleep, TD._one_pass, TD._rest_pass, TD._pending_jobs, TD._retry_count, TD.LOG,
                W.sales_in_progress)
        args = SimpleNamespace(parent=0, ledger_synced=True, until="", until_at=None, hidden=False, manual=manual)   # 대장 반영(D-366 ②) = P69
        try:
            TD.datetime, TD.time.sleep = FakeDT, fake_sleep
            TD._one_pass = lambda a: (passes.append(clock["now"]), (False, 3 if len(passes) == 1 else 0))[1]
            TD._rest_pass = TD._one_pass                                     # 다음 바퀴 = 남은 일 바퀴(D-382)
            TD._pending_jobs, TD._retry_count = (lambda: 0), (lambda: 0)
            TD.LOG = RLG.RunLog(TD.BASE, now=clock["now"], echo=lambda m: None)
            TD.LOG.heartbeat = lambda st, msg: None
            W.sales_in_progress = lambda *a, **k: ((True, "①판매수집 진행 중") if busy and not passes and
                                                   clock["now"] < D(2026, 11, 19, 12) else (False, ""))
            rc = TD.cmd_watch(args)
        finally:
            (TD.datetime, TD.time.sleep, TD._one_pass, TD._rest_pass, TD._pending_jobs, TD._retry_count, TD.LOG,
             W.sales_in_progress) = olds
        if stage.exists():
            stage.unlink()
        return rc, passes

    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            (Path(tmp) / "output").mkdir()
            done_at = D(2026, 11, 19, 7, 48, 19)                              # 11-19 운용 PC 실측: 이번 회차 ① 07:48 · 정산 '완료'
            assert run(False, done_at)[1] == [], "옛 동작(무인) = 이미 끝남 → 받지 않고 종료(D-091 그대로)"
            rc, passes = run(True, done_at)
            assert rc == 0 and passes and passes[0] == D(2026, 11, 19, 11, 22, 29), ("수동 = 완료 기록 있어도 바로 받음", passes)
            assert run(True, None)[1], "수동 = 이번 회차 ① 기록이 없어도 받음(①완료 대기 없음)"
            rc, passes = run(True, done_at, busy=True)
            assert passes and passes[0] >= D(2026, 11, 19, 12), ("①이 도는 중 = 끝날 때까지 대기 뒤 받음", passes)
        finally:
            os.chdir(old_cwd)
    ok("버튼 = --manual · 완료 기록·① 미완료여도 바로 받음 · ① 진행 중이면 대기 · 무인·전체실행 = 그대로(D-021·D-091)")


def p68_evidence_auto():
    print("[P68] 자동 증빙(D-363·D-365) — 정산 '완료' 뒤 남은 시간만 · 회차 끝 40분 전부터 새 계정·새 단계 안 함 · 완료 계정도 "
          "매달 새 달분 · 같은 단계 2회차 연속 실패 = 확인 필요 · 정산 기록·원본 폴더 되돌림 · 검증·광고 포함(cmd_run)")
    import contextlib
    import inspect
    import json as _json
    import os
    from datetime import datetime as RealDT, timedelta
    from types import SimpleNamespace
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import settlement_download as TD
    from coupang_analytics import settlement_evidence as EV
    from coupang_analytics import settlement_runlog as RLG
    from coupang_analytics import settlement_watch as W
    DT = RealDT
    start = D("2026-01-01")
    # ③ 멈춤 = 회차 끝 − 40분(회차 상수가 아니라 끝 시각에서 계산 — D-372 24:00 → 23:20)
    assert EV.STOP_BEFORE == timedelta(minutes=40) and EV.CHECK_AFTER == 2
    assert EV.stop_at(W.cycle_window(DT(2026, 11, 21, 0, 10))[1]) == DT(2026, 11, 21, 23, 20)
    # ② 자동 증빙 '정산 원본' = cmd_run 그대로(검증 수집·광고 포함 · 빼지 않음) · 배치·run·소급·셀독전환에는 증빙 없음
    assert "cmd_run(a, b, args, jobs)" in inspect.getsource(TD.cmd_evidence)
    for fn in (TD._run_both, TD.cmd_backfill, TD.cmd_run, TD._transfer_settle, TD.main):
        assert "_evidence_sweep" not in inspect.getsource(fn), fn.__name__

    def mark(folder, name, at):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(_json.dumps({"시각": f"{at:%Y-%m-%d %H:%M}"}), encoding="utf-8")

    def step(res, stop=False):
        return {"결과": res, "내용": "", "파일": 0, **({"멈춤": True} if stop else {})}
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "증빙_x_쿠팡원본"
        now = DT(2026, 12, 2, 3, 0)
        # ④ 완료 표시 없음 = 대상(이어받기) · 이번 달 완료 = 대상 아님 · 지난달 이전 완료 = 매달 1일 지나면 다시(완료한 달 1일부터)
        assert EV.renewal(f, now, start) == (True, start, False)
        mark(f, EV.DONE, DT(2026, 12, 1, 5)), mark(f, EV.RESULT, DT(2026, 12, 1, 5))
        assert EV.renewal(f, now, start)[0] is False, "이번 달 완료인데 다시 받음"
        mark(f, EV.DONE, DT(2026, 11, 19, 20)), mark(f, EV.RESULT, DT(2026, 11, 19, 20))
        assert EV.renewal(f, now, start) == (True, D("2026-11-01"), True), "새 달 첫 시도 = 지난 단계 결과 무시·완료한 달 1일부터"
        mark(f, EV.RESULT, DT(2026, 12, 1, 23))
        assert EV.renewal(f, now, start) == (True, D("2026-11-01"), False), "이번 달 시도가 있으면 이어받기"
        # ⑤ 회차마다 1번만 셈 · 멈춤(시도 안 함)은 안 셈 · 2회차 = 확인 필요 · 정상이면 0
        F, G = EV.FAIL, EV.OK
        assert EV.fail_streak(f, {"광고": step(F), "월렛": step(G)}, "c1") == []
        assert EV.fail_streak(f, {"광고": step(F)}, "c1") == [], "같은 회차 두 번 = 1회차"
        assert EV.fail_streak(f, {"광고": step(F, stop=True)}, "c2") == [], "멈춤(시도 안 함)을 실패로 셈"
        assert EV.fail_streak(f, {"광고": step(F)}, "c3") == ["광고"], "2회차 연속 실패인데 확인 필요 아님"
        assert EV.fail_streak(f, {"광고": step(G)}, "c4") == [], "정상인데 확인 필요 남음"
        assert not any(r["파일"].startswith("_") for r in EV.listing_rows(f)), "기록 파일이 증빙 목록에 섞임"

        class Acc:
            def __init__(self, i):
                self.account_id = i
        olds = (TD.LOG, TD.name_of, TD.JOBS, TD.ORIGINALS, TD.EVIDENCE_DIR, TD.EVIDENCE_JOBS, TD.datetime, TD.log,
                TD.cmd_evidence, TD.session, TD._one_pass, TD._rest_pass, TD._between_passes, TD._pending_jobs, TD._retry_count,
                TD._watch_failures, TD._cycle_close, TD.time.sleep)
        old_cwd = os.getcwd()
        os.chdir(tmp)
        try:
            TD.name_of = lambda a: f"대표-사업{a.account_id}-{a.account_id}"
            TD.LOG = RLG.RunLog(tmp, now=DT(2026, 11, 20, 1), echo=lambda m: None)
            # cmd_evidence: 멈춤 시각 뒤 = 단계 0개 시작 · 단계마다 '멈춤' 표시 · 단계 결과 반환
            args = SimpleNamespace(out=tmp, redo=False, start=start, end=D("2026-11-20"), until="00:40", until_at=DT(2000, 1, 1))
            steps = TD.cmd_evidence(Acc("e0"), None, args, [])
            TD.ORIGINALS = olds[3]
            assert steps and all(v.get("멈춤") and v["결과"] == EV.FAIL for v in steps.values()), steps
            # _evidence_auto: 증빙 기록·원본 폴더·기간은 그 계정 동안만 · 예외여도 되돌림 · [메모리] 줄 · 2회차 실패 = 확인 필요 줄
            clock = {"now": DT(2026, 11, 20, 10)}

            class FakeDT(RealDT):
                @classmethod
                def now(cls, tz=None):
                    return clock["now"]
            lines: list = []
            seen: list = []
            boom = {"on": False}
            ev_dir = Path(tmp) / "output" / "정산" / "증빙"
            TD.EVIDENCE_DIR, TD.EVIDENCE_JOBS = ev_dir, ev_dir / "_요청기록.json"
            TD.datetime, TD.log = FakeDT, lines.append

            def fake_ev(a, b, args, jobs):
                seen.append({"acc": a.account_id, "jobs": TD.JOBS, "out": args.out, "start": args.start, "redo": args.redo,
                             "until_at": args.until_at, "now": clock["now"], "done": TD.DONE_FILE.exists()})
                TD.ORIGINALS = Path("다른곳")                       # cmd_evidence 처럼 바꿈
                clock["now"] += fake_ev.took
                if boom["on"]:
                    raise RuntimeError("화면 바뀜")
                return {"광고센터 월별 광고비": step(EV.FAIL)}
            fake_ev.took = timedelta(minutes=5)
            TD.cmd_evidence = fake_ev
            jobs0, orig0 = TD.JOBS, TD.ORIGINALS
            a_args = SimpleNamespace(out="", start=start, redo=False, cycle_since="c1", until_at=None)
            TD._evidence_auto(Acc("a1"), None, a_args, ["정산기록"])
            assert seen[-1]["jobs"] == TD.EVIDENCE_JOBS and seen[-1]["out"] == str(ev_dir), seen
            assert (TD.JOBS, TD.ORIGINALS, a_args.out, a_args.redo) == (jobs0, orig0, "", False), "전역·인자 안 되돌림"
            assert any("증빙 대표-사업a1-a1" in m and "[메모리]" in m for m in lines), lines
            a_args.cycle_since = "c2"
            TD._evidence_auto(Acc("a1"), None, a_args, [])
            chk = [r for r in TD.LOG.rows if r["계정"].endswith("a1") and "확인 필요" in r["사유"]]
            assert chk and chk[-1]["단계"] == "증빙 광고센터 월별 광고비" and chk[-1]["결과"] == RLG.FAIL, TD.LOG.rows[-3:]
            boom["on"] = True
            expect(RuntimeError, lambda: TD._evidence_auto(Acc("a1"), None, a_args, []), "증빙 예외")
            assert (TD.JOBS, TD.ORIGINALS, a_args.out) == (jobs0, orig0, ""), "예외 때 전역 안 되돌림"
            boom["on"] = False
            mark(EV.account_folder(ev_dir, "대표-사업a2-a2"), EV.DONE, DT(2026, 11, 3, 4))
            n = len(seen)
            TD._evidence_auto(Acc("a2"), None, a_args, [])
            assert len(seen) == n, "이번 달 완료 계정인데 증빙 받음"

            # ① B2: cmd_watch — 정산 '완료' 기록 뒤에만 증빙 · 회차 끝 40분 전부터 새 계정 안 함 · 증빙 실패가 정산 완료를 안 바꿈
            @contextlib.contextmanager
            def fake_session(a, hidden, until=None):
                yield None
            TD.session = fake_session
            TD._between_passes = lambda: None
            TD._pending_jobs, TD._retry_count, TD._watch_failures = (lambda: 0), (lambda: 0), (lambda: {})
            TD.time.sleep = lambda sec: None

            def watch(now0, took, work=(0,)):
                cs, ce = W.cycle_window(now0)
                clock["now"] = now0
                order: list = []
                stage = Path("output") / "쿠팡데이타분석_실행단계.json"
                stage.write_text(_json.dumps({"date": f"{cs:%Y-%m-%d}", "stage": "done", "at": (cs + timedelta(minutes=1)).isoformat()}),
                                 encoding="utf-8")
                TD.DONE_FILE.unlink(missing_ok=True)
                works = list(work)

                def one_pass(a):
                    order.append("정산")
                    TD.PASS_ACCOUNTS[:] = [Acc("w1"), Acc("w2"), Acc("w3")]
                    return False, works.pop(0) if works else 0
                TD._one_pass = TD._rest_pass = one_pass                       # 다음 바퀴 = 남은 일 바퀴(D-382)
                TD._cycle_close = lambda st, reason, stopped=False: order.append(("종합", st))
                fake_ev.took = took
                n0 = len(seen)
                wargs = SimpleNamespace(parent=0, ledger_synced=True, until="", until_at=None, hidden=False, since="", manual=False, start=start,   # 대장 반영(D-366 ②) = P69
                                        redo=False, out="", command="watch")
                rc = TD.cmd_watch(wargs)
                return rc, order, seen[n0:], ce
            mark(EV.account_folder(ev_dir, "대표-사업w3-w3"), EV.DONE, DT(2026, 11, 20, 9))   # 이번 달 완료 = 로그인도 안 함
            _, ce0 = W.cycle_window(DT(2026, 11, 20, 12))
            rc, order, got, ce = watch(ce0 - timedelta(hours=3), timedelta(minutes=5), work=(4, 0))
            assert rc == 0 and order[:2] == ["정산", "정산"] and order[-1][0] == "종합", order
            assert [g["acc"] for g in got] == ["w1", "w2"], ("완료 계정 빼고 남은 계정만", got)
            assert all(g["done"] and g["until_at"] == ce - timedelta(minutes=40) for g in got), ("정산 완료 기록 뒤·40분 전 멈춤", got)
            assert TD.PASS_ACCOUNTS and order.index(("종합", "완료")) == len(order) - 1, "증빙 실패가 정산 완료 판정을 바꿈"
            rc, order, got, ce = watch(ce0 - timedelta(hours=3), timedelta(hours=2, minutes=50))
            assert [g["acc"] for g in got] == ["w1"], ("40분 전 지나면 새 계정 시작 안 함", got)
            rc, order, got, ce = watch(ce0 - timedelta(minutes=30), timedelta(minutes=5))
            assert got == [] and order[-1][0] == "종합", ("40분 안쪽에서 정산이 끝나면 증빙 0", got)
        finally:
            (TD.LOG, TD.name_of, TD.JOBS, TD.ORIGINALS, TD.EVIDENCE_DIR, TD.EVIDENCE_JOBS, TD.datetime, TD.log,
             TD.cmd_evidence, TD.session, TD._one_pass, TD._rest_pass, TD._between_passes, TD._pending_jobs, TD._retry_count,
             TD._watch_failures, TD._cycle_close, TD.time.sleep) = olds
            TD.PASS_ACCOUNTS.clear()
            os.chdir(old_cwd)
    ok("40분 전 멈춤(끝 시각 기준) · 새 달 다시(완료한 달 1일부터) · 2회차 연속 실패 = 확인 필요 · 전역 되돌림(예외 포함) · "
       "정산 '완료' 기록 뒤에만 증빙 · 완료 계정 로그인 안 함 · 검증·광고 포함")


def p69_ledger_presync():
    print("[P69] 정산 회차 첫 바퀴 전 관리대장→원장 반영 1회 + 대장 비밀번호 저장(D-366 ②) — 같은 rows 로 둘 다 · 원장 잠금 = "
          "앱과 같은 run_sync · 못 읽으면 그 바퀴 중단·다음 바퀴 재시도 · 둘째 바퀴부터 안 함 · 사람이 누르는 명령은 그대로")
    import inspect
    import os
    from datetime import datetime as RealDT, timedelta
    from types import SimpleNamespace
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import settlement_download as TD
    from coupang_analytics import appconfig, credstore, gsheet_api
    from coupang_analytics import input_list as IL
    from coupang_analytics import registry_gsheet as RG
    from coupang_analytics import settlement_accounts as SA
    from coupang_analytics import settlement_runlog as RLG
    assert issubclass(TD.LedgerSyncError, Exception)

    class Store:
        def __init__(self):
            self.d = {}

        def get_password(self, k):
            return self.d.get(k)

        def set_password(self, k, v):
            self.d[k] = v
    rows = [["사업자명", "계정아이디", "상품명", "비밀번호"],
            ["가", "acc1", "상품1", "pw-one "], ["나", "acc2", "상품2", "pw-a"], ["나", "acc2", "상품3", "pw-a"],
            ["나", "acc2", "상품4", "pw-b"]]
    ledger = ("셀독리스트", rows, [[False] * 4 for _ in rows])
    cfg = {"gsheet/input_url": "IN-URL", "registry/url": "REG-URL", "settlement/account_source": ""}
    st = {"store": Store(), "reads": 0, "syncs": [], "read_exc": None, "sync_exc": None}
    lines: list = []

    def fake_read(url, *, store=None, sa_path=None):
        assert url == "IN-URL" and store is st["store"], (url, store)
        st["reads"] += 1
        if st["read_exc"]:
            raise st["read_exc"]
        return ledger

    class Client:
        def __init__(self, url, store=None, on_log=None, **k):
            self.url, self.store = url, store

    def fake_sync(client, read_ledger, **kw):
        if st["sync_exc"]:
            raise st["sync_exc"]
        st["syncs"].append((client.url, client.store, read_ledger(), kw))
    olds = (appconfig.get, IL.read_ledger_rows, gsheet_api.GSheetClient, RG.run_sync, credstore.CredStore, TD.log)
    old_cwd = os.getcwd()
    tmpdir = tempfile.TemporaryDirectory()
    try:
        appconfig.get = lambda k, d="": cfg.get(k, d)
        IL.read_ledger_rows, gsheet_api.GSheetClient, RG.run_sync = fake_read, Client, fake_sync
        credstore.CredStore = lambda *a, **k: st["store"]
        TD.log = lines.append
        os.chdir(tmpdir.name)
        TD._ledger_presync()
        assert st["reads"] == 1, ("관리대장 읽기 = 1번(원장 반영·비밀번호 같은 rows)", st["reads"])
        (url, store, got, kw), = st["syncs"]
        assert url == "REG-URL" and store is st["store"] and got is ledger, "원장 반영 = 방금 읽은 같은 대장 값"
        assert "lock_path" not in kw and "dry_run" not in kw, ("앱과 같은 원장 잠금(기본 경로)·실제 반영", kw)
        assert kw.get("judge") is not None, "상품명 변경 자동 판단 = 앱 원장 반영과 같게(D-070)"
        s = st["store"].d
        assert s["acc1"] == "pw-one" and s["acc2"] == "pw-b", ("값1 = 앱 _apply_pw_candidates 와 같은 값(적은 줄 먼저 D-012)", s)
        assert s[SA.alt_key("acc2")] == "pw-a", "줄마다 다른 값2 도 저장(D-190 save_ledger_alternates)"
        text = "\n".join(map(str, lines))
        assert "pw-" not in text, ("평문 비밀번호 로그 금지", text)
        # 못 읽음 = LedgerSyncError(이유) · 원장 안 건드림 · 비밀번호 안 바뀜
        st.update(store=Store(), syncs=[], read_exc=OSError("네트워크 끊김"))
        try:
            TD._ledger_presync()
            raise AssertionError("대장 못 읽으면 실패로 올려야 함(조용히 넘어가기 금지)")
        except TD.LedgerSyncError as exc:
            assert "관리대장" in str(exc) and "네트워크 끊김" in str(exc), str(exc)
        assert st["syncs"] == [] and st["store"].d == {}, "못 읽으면 원장·비밀번호 손대지 않음"
        st["read_exc"], st["sync_exc"] = None, RuntimeError("원장 잠금 120초 초과")
        expect(TD.LedgerSyncError, TD._ledger_presync, "원장 반영 실패 = 그 바퀴 중단")
        st["sync_exc"] = None
        cfg["gsheet/input_url"] = ""
        expect(TD.LedgerSyncError, TD._ledger_presync, "관리대장 링크 없음")
        cfg["gsheet/input_url"], cfg["registry/url"] = "IN-URL", ""
        expect(TD.LedgerSyncError, TD._ledger_presync, "원장 링크 없음(정산 계정 출처 = 원장)")
        cfg["settlement/account_source"], st["syncs"], st["store"] = "file", [], Store()
        TD._ledger_presync()
        assert st["syncs"] == [] and st["store"].d.get("acc1") == "pw-one", "옛 계정 파일 출처 = 비밀번호만 저장(원장 반영 없음)"
    finally:
        appconfig.get, IL.read_ledger_rows, gsheet_api.GSheetClient, RG.run_sync, credstore.CredStore, TD.log = olds
        os.chdir(old_cwd)
        tmpdir.cleanup()
    # watch 회차: 첫 바퀴 계정 읽기 전 1회 · 실패 = 그 바퀴 안 돌고 5분 뒤 다시 · 성공 뒤 바퀴들은 다시 안 함
    calls, passes, beats = [], [], []
    clock = {"now": RealDT(2026, 11, 20, 2, 0)}

    class FakeDT(RealDT):
        @classmethod
        def now(cls, tz=None):
            return clock["now"]

    def presync():
        calls.append(clock["now"])
        if len(calls) == 1:
            raise TD.LedgerSyncError("관리대장 읽기 실패 — OSError: 네트워크 끊김")

    def one_pass(a):
        assert calls and len(calls) == 2, "바퀴(계정 읽기)는 반영 성공 뒤에만"
        passes.append(clock["now"])
        return False, (3 if len(passes) == 1 else 0)
    olds = (TD.datetime, TD.time.sleep, TD._one_pass, TD._rest_pass, TD._pending_jobs, TD._retry_count, TD.LOG, TD._ledger_presync,
            TD._evidence_sweep, TD._between_passes, TD._watch_failures)
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            (Path(tmp) / "output").mkdir()
            TD.datetime = FakeDT
            TD.time.sleep = lambda sec: clock.__setitem__("now", clock["now"] + timedelta(seconds=max(sec, 1)))
            TD._one_pass, TD._rest_pass, TD._ledger_presync = one_pass, one_pass, presync
            TD._pending_jobs, TD._retry_count, TD._watch_failures = (lambda: 0), (lambda: 0), (lambda: {})
            TD._evidence_sweep, TD._between_passes = (lambda a, act: None), (lambda: None)
            TD.LOG = RLG.RunLog(TD.BASE, now=clock["now"], echo=lambda m: None)
            TD.LOG.heartbeat = lambda status, msg="", **k: beats.append((status, msg))
            rc = TD.cmd_watch(SimpleNamespace(parent=0, until="", until_at=None, hidden=False, manual=True))
        finally:
            (TD.datetime, TD.time.sleep, TD._one_pass, TD._rest_pass, TD._pending_jobs, TD._retry_count, TD.LOG, TD._ledger_presync,
             TD._evidence_sweep, TD._between_passes, TD._watch_failures) = olds
            os.chdir(old_cwd)
    assert rc == 0 and len(calls) == 2 and len(passes) == 2, ("반영 = 실패 1 + 성공 1 · 그 뒤 바퀴 2번", calls, passes)
    assert calls[1] - calls[0] >= timedelta(seconds=TD.WATCH_POLL_SEC), ("다음 바퀴 = 5분 뒤 재시도", calls)
    bad = [m for s, m in beats if "❌" in m and "관리대장" in m]
    assert bad and "다음 바퀴" in bad[0], ("상태 카드에 실패 이유·재시도 안내", beats)
    # 사람이 누르는 명령(run·evidence·request·download·probe 등)은 그대로 — 반영은 watch 회차에서만
    assert "_ledger_presync" not in inspect.getsource(TD.main) and "_ledger_presync" not in inspect.getsource(TD._one_pass)
    ok("같은 rows 로 원장 반영(앱 run_sync·기본 잠금·자동 판단)+비밀번호 값1·값2 저장 · 평문 로그 0 · 못 읽음/반영 실패 = "
       "그 바퀴 중단·상태 카드 이유·5분 뒤 재시도 · 둘째 바퀴부터 안 함 · 사람 명령 그대로")


def p70_error_retry_three():
    print("[P70] 정산 오류 = 계정·항목별 최대 3번(처음 + 다시 2번) · 그 뒤 더 시도 안 함 · 오류 로그(사유·시각·계정·데이터·항목·n번째) ·"
          " 비밀번호 거부 = 지금 그대로 · 2차 인증 = 다시 시도 안 함 · 파일 생성 대기 = 안 셈 · 다 끝나면 조기 종료 · 회차마다 0부터(D-373)")
    import contextlib
    import csv
    import json as _json
    import os
    from datetime import datetime as RealDT, timedelta
    from types import SimpleNamespace
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import settlement_download as TD
    from coupang_analytics import pipeline_sales as PS
    from coupang_analytics import settlement_jobs as SJ
    from coupang_analytics import settlement_retry as TR
    from coupang_analytics import settlement_runlog as RLG
    from coupang_analytics import settlement_watch as W
    from coupang_analytics import settlement_wing_api as API
    CYC, CYC2 = "2026-11-21T00:10:00", "2026-11-22T00:10:00"

    def rows(folder):
        with (Path(folder) / TR.LOG_NAME).open(encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    class Acc:
        def __init__(self, i):
            self.account_id, self.label = i, i

    class Args:
        until, until_at, hidden, command = "", None, True, "run"

    # ① 시도표 단위 — 일시 오류 2번 뒤 성공 · 3번 실패 = 더 시도 안 함 · 같은 바퀴 두 번째 실패 안 셈 · 재시작 이어 셈 · 다음 회차 0부터
    with tempfile.TemporaryDirectory() as tmp:
        lines: list = []
        t = TR.Tries(tmp, CYC, line=lines.append)
        for p in ("p1", "p2"):
            t.begin_pass(p)
            assert t.why_not("A", "받기", "정산일 2026-11-20") == ""
            assert t.fail("A", "받기", "ServerBusy: 504", "정산일 2026-11-20")["결과"] == TR.RETRY
            assert t.fail("A", "받기", "ServerBusy: 504", "정산일 2026-11-20") is None, "같은 바퀴 두 번째 실패 = 안 셈(①)"
            assert t.retry_now() == 1 and "이번 바퀴에 이미 실패" in t.why_not("A", "받기", "정산일 2026-11-20")
        t.begin_pass("p3")
        assert t.why_not("A", "받기", "정산일 2026-11-20") == "" and t.retry_now() == 0, "새 바퀴 = 다시 시도 가능 · 이번 바퀴 실패 0"
        t.ok("A", "받기", "정산일 2026-11-20")                                      # 3번째에 성공
        assert t.items == {} and t.given_up() == {}
        for p in ("q1", "q2", "q3"):
            t.begin_pass(p)
            e = t.fail("B", "계정 처리(정기)", "SiteChangedError: 표 머리글 없음", "정기")
        assert e["시도"] == 3 and e["결과"] == TR.GIVE_UP and t.retry_now() == 0, e
        t.begin_pass("q4")
        assert "3번 실패" in t.why_not("B", "계정 처리(정기)", "정기") and t.fail("B", "계정 처리(정기)", "x", "정기") is None
        assert t.given_up() == {"B": "계정 처리(정기)"}
        got = rows(tmp)
        assert [(r["계정"], r["시도"], r["결과"]) for r in got] == [
            ("A", "1/3", TR.RETRY), ("A", "2/3", TR.RETRY),
            ("B", "1/3", TR.RETRY), ("B", "2/3", TR.RETRY), ("B", "3/3", TR.GIVE_UP)], got
        last = got[-1]                                                                  # 로그 한 건 = 사유·시각·계정·데이터·항목·n번째
        assert (last["시도 항목"], last["데이터"], last["회차"], last["실행ID"]) == ("계정 처리(정기)", "정기", CYC, "q3"), last
        assert last["오류사유"] == "SiteChangedError: 표 머리글 없음" and RealDT.strptime(last["시각"], "%Y-%m-%d %H:%M:%S"), last
        assert any("[오류 3/3] B · 계정 처리(정기) · 정기 → 더 시도 안 함" in m for m in lines), lines   # 실행 로그 한 줄
        assert any("[오류 1/3] A · 받기" in m and "다음 바퀴에 다시 시도" in m for m in lines), lines
        assert "오류로 더 시도 안 한 항목" in t.summary_lines()[0] and "B · 계정 처리(정기)" in t.summary_lines()[1]
        t2 = TR.Tries(tmp, CYC, line=lines.append)                                      # 같은 회차 재시작(재부팅 복구) = 이어 셈
        assert "3번 실패" in t2.why_not("B", "계정 처리(정기)", "정기")
        t3 = TR.Tries(tmp, CYC2, line=lines.append)                                     # ④ 다음 회차 = 0부터
        assert t3.items == {} and t3.why_not("B", "계정 처리(정기)", "정기") == ""
        t3.begin_pass("r1")
        assert t3.fail("B", "계정 처리(정기)", "x", "정기")["시도"] == 1
        assert _json.loads((Path(tmp) / TR.STATE_NAME).read_text(encoding="utf-8"))["회차"] == CYC2
        # 예외 2종 — 비밀번호 거부 = 막지 않음(지금 방식)·로그 한 번 · 2차 인증 = 처음부터 다시 시도 안 함
        assert t3.fail("P", "로그인", "비밀번호 오류", kind=TR.PASSWORD)["결과"] == TR.NO_RETRY
        assert t3.why_not("P", "로그인") == "" and t3.retry_now() == 1, "비밀번호 거부 = 다시 시도 수에 안 셈·막지도 않음"
        t3.begin_pass("r2")
        assert t3.fail("P", "로그인", "비밀번호 오류", kind=TR.PASSWORD) is None, "같은 회차 비밀번호 거부 로그 = 한 번"
        assert t3.fail("H", "로그인", "otp: 2차 인증", kind=TR.HUMAN)["결과"] == TR.NO_RETRY
        assert "사람 조치" in t3.why_not("H", "로그인") and t3.retry_now() == 0 and t3.given_up() == {"P": "로그인", "H": "로그인"}
    ok("2번 실패 뒤 성공 = 기록 지움 · 3번째 실패 = 더 시도 안 함 · 바퀴당 1번 · 로그 9칸 · 재시작 이어 셈 · 다음 회차 0부터 · 비번·2차 인증 예외")

    # ② 로그인 실패 종류 — 비밀번호 거부 / 2차 인증 / Akamai·차단 / 그 밖
    class FB:
        def __init__(self, code):
            self.code = code

        def classify_login(self):
            return self.code, f"{self.code} 화면"

    def kind_of(ret=None, exc=None, code="form"):
        def cand(*_a, **_k):
            if exc is not None:
                raise exc
            return ret
        try:
            _patched([(PS, "_login_with_candidates", cand), (TD, "name_of", lambda a: a.account_id)],
                     lambda: TD._login(FB(code), Acc("x"), ["p"], True))
        except TD.SessionSkip as e:
            return e.kind
        return "로그인됨"
    with tempfile.TemporaryDirectory() as tmp:
        lg = RLG.RunLog(tmp, now=RealDT(2026, 11, 21, 1), echo=lambda m: None)
        got = _patched([(TD, "LOG", lg), (TD, "TRIES", None)], lambda: [
            kind_of(exc=PS.LoginCredentialError("x")), kind_of(exc=PS.LoginBlocked()), kind_of(False, code="otp"),
            kind_of(False, code="akamai"), kind_of(False, code="blocked"), kind_of(False, code="form"), kind_of(True, code="success")])
    assert got == [TR.PASSWORD, TR.BLOCK, TR.HUMAN, TR.BLOCK, TR.BLOCK, TR.ERROR, "로그인됨"], got
    ok("로그인 실패 종류 = 비밀번호 거부·접속 차단(LoginBlocked·akamai·blocked)·2차 인증(사람 조치)·그 밖 오류")

    # ③ 계정 단위 — 서버 오류 3바퀴 뒤 건너뜀 · 2번 뒤 성공 · 2차 인증 1번만 · 비밀번호 거부 = 매 바퀴 지금 그대로
    with tempfile.TemporaryDirectory() as tmp:
        visits: dict = {}
        ran: dict = {}

        @contextlib.contextmanager
        def fake_session(a, hidden, until=None):
            visits[a.account_id] = visits.get(a.account_id, 0) + 1
            if a.account_id == "otp":
                raise TD.SessionSkip("로그인 미완료(otp: 2차 인증 화면)", TR.HUMAN)
            if a.account_id == "pw":
                raise TD.SessionSkip("비밀번호 오류(재시도 안 함)", TR.PASSWORD)
            yield None

        def cmd_run(a, b, args, jobs):                                   # 이름 = 정기 단계(항목 '계정 처리(정기)')
            ran[a.account_id] = ran.get(a.account_id, 0) + 1
            if a.account_id == "srv" or (a.account_id == "flaky" and ran["flaky"] <= 2):
                raise API.ServerBusy("/tenants/x → 504 서버 일시 오류")
        tries = TR.Tries(Path(tmp) / "로그", CYC, line=lambda m: None)
        after: list = []

        def passes():
            for p in range(4):
                TD.LOG = RLG.RunLog(tmp, now=RealDT(2026, 11, 21, 1, p), echo=lambda m: None)
                tries.begin_pass(f"p{p}")
                assert TD._run_accounts([Acc(i) for i in ("srv", "flaky", "otp", "pw", "good")], cmd_run, Args) == 0
                after.append((TD._retry_count(), [r for r in TD.LOG.rows if r["결과"] == RLG.SKIP]))
        _patched([(TD, "session", fake_session), (TD, "name_of", lambda a: a.account_id), (TD, "TRIES", tries),
                  (TD, "LOG", None), (TD, "JOBS", Path(tmp) / "_요청기록.json")], passes)
        assert ran == {"srv": 3, "flaky": 4, "good": 4}, ran                         # srv 4번째 바퀴 안 감 · flaky 3번째 성공
        assert visits == {"srv": 3, "flaky": 4, "otp": 1, "pw": 4, "good": 4}, visits  # 2차 인증 1번만 · 비번 = 지금 그대로
        assert [n for n, _ in after] == [2, 2, 0, 0], after                           # 이번 바퀴 실패·다시 시도 남은 항목 수
        skips = [(r["계정"], r["사유"]) for r in after[3][1]]
        assert any(a == "srv" and "3번 실패" in s for a, s in skips), skips
        assert any(a == "otp" and "사람 조치" in s for a, s in skips), skips
        log_rows = [(r["계정"], r["시도 항목"], r["시도"], r["결과"]) for r in rows(Path(tmp) / "로그")]
        assert log_rows == [
            ("srv", "계정 처리(정기)", "1/3", TR.RETRY), ("flaky", "계정 처리(정기)", "1/3", TR.RETRY),
            ("otp", "로그인", "1/3", TR.NO_RETRY), ("pw", "로그인", "1/3", TR.NO_RETRY),
            ("srv", "계정 처리(정기)", "2/3", TR.RETRY), ("flaky", "계정 처리(정기)", "2/3", TR.RETRY),
            ("srv", "계정 처리(정기)", "3/3", TR.GIVE_UP)], log_rows
        fails = _patched([(TD, "TRIES", tries), (TD, "LOG", SimpleNamespace(unresolved_failures=lambda: {})),
                          (TD, "JOBS", Path(tmp) / "_요청기록.json")], TD._watch_failures)
        assert set(fails) == {"srv", "otp", "pw"}, fails                                    # 회차 누적 '확인 필요'(마지막 바퀴는 건너뜀 줄만)
    ok("계정 서버 오류 = 3바퀴 뒤 건너뜀 · 2번 실패 뒤 성공 · 2차 인증 1번만 · 비밀번호 거부 매 바퀴 그대로 · 확인 필요 = 회차 누적")

    # ④ 정산 파일(받기) — 파싱 오류 3번 뒤 안 받음·생성 대기 수에서 뺌 · 쿠팡 파일 생성 대기 = 안 셈
    with tempfile.TemporaryDirectory() as tmp:
        jobs_p = Path(tmp) / "_요청기록.json"
        bad = SJ.Job("A-1", "윙", "주정산", "정산", "2026-11-10", "2026-11-16", "2026-11-20", status=SJ.ST_REQUESTED, ref="r1")
        wait = SJ.Job("A-1", "윙", "주정산", "정산", "2026-11-03", "2026-11-09", "2026-11-13", status=SJ.ST_REQUESTED, ref="r2")
        js = [bad, wait]
        SJ.save_jobs(jobs_p, js)
        fetched: list = []

        def fetch(b, j, row, name):
            fetched.append(j.ref)
            raise API.SiteChangedError("표 머리글 없음(파싱 오류)")

        def match(rows_, want):                                                         # r2 = 쿠팡이 아직 파일을 안 만듦
            return [(j, None) for j in want if j.ref == "r1"], [f"{j.ref} 아직 생성 중" for j in want if j.ref == "r2"]
        tries = TR.Tries(Path(tmp) / "로그", CYC, line=lambda m: None)

        def passes():
            out = []
            for p in range(4):
                TD.LOG = RLG.RunLog(tmp, now=RealDT(2026, 11, 21, 2, p), echo=lambda m: None)
                tries.begin_pass(f"p{p}")
                TD.cmd_download(Acc("A-1"), None, Args, js)
                out.append((TD._retry_count(), TD._pending_jobs()))
            return out
        out = _patched([(TD, "TRIES", tries), (TD, "name_of", lambda a: a.account_id), (TD, "JOBS", jobs_p),
                        (TD, "_list_rows", lambda b, ch, want, name: []), (TD, "_fetch_one", fetch),
                        (SJ, "match_downloads", match), (TD, "LOG", None)], passes)
        assert fetched == ["r1", "r1", "r1"], fetched                                   # 4번째 바퀴 = 안 받음
        assert out == [(1, 2), (1, 2), (0, 1), (0, 1)], out                            # 소진된 r1 = 생성 대기 수에서 뺌 · r2 = 그대로
        items = {(e["항목"], e["데이터"]): e["시도"] for e in tries.items.values()}
        assert items == {("받기 윙 주정산·정산", "정산일 2026-11-20 · 기간 2026-11-10~2026-11-16"): 3}, items   # r2(생성 대기) = 안 셈
    ok("받기 파싱 오류 3번 뒤 안 받음·대기 수에서 뺌 · 파일 생성 대기 = 횟수 안 셈")

    # ⑤ 회차(cmd_watch) — 3번 소진되면 24:00 전 조기 종료 · 생성 대기만 남으면 그 계정만 20분마다 24:00 까지(소유자 '20분으로 해줘')
    def watch(one_pass, pending, wait_pass=lambda n: (False, 0)):
        """pending = 바퀴 뒤 생성 대기 수(숫자 또는 지금까지 바퀴 수 → 수). 장면마다 시도표 새로(같은 회차 파일 이어 셈 방지)."""
        (Path(TD.BASE) / "로그" / TR.STATE_NAME).unlink(missing_ok=True)
        clock = {"now": RealDT(2026, 11, 21, 3, 0)}
        passes: list = []
        beats: list = []
        sweeps: list = []

        class FakeDT(RealDT):
            @classmethod
            def now(cls, tz=None):
                return clock["now"]

        def fake_sleep(sec):
            clock["now"] += timedelta(seconds=max(sec, 1))

        def op(kind, fn):
            def run(args):
                passes.append((kind, clock["now"]))
                TD.LOG = RLG.RunLog(TD.BASE, now=clock["now"], echo=lambda m: None)
                TD.LOG.heartbeat = lambda st, msg="", **k: beats.append((st, msg))
                TD.TRIES.begin_pass(f"p{len(passes)}")
                return fn(len(passes))
            return run
        args = SimpleNamespace(parent=0, ledger_synced=True, until="", until_at=None, hidden=False, manual=True)
        log0 = RLG.RunLog(TD.BASE, now=clock["now"], echo=lambda m: None)
        log0.heartbeat = lambda st, msg="", **k: beats.append((st, msg))
        rc = _patched([(TD, "datetime", FakeDT), (TD.time, "sleep", fake_sleep), (TD, "_one_pass", op("전체", one_pass)),
                       (TD, "_rest_pass", op("남은 일", wait_pass)),
                       (TD, "_pending_jobs", lambda: pending(len(passes)) if callable(pending) else pending),
                       (TD, "_between_passes", lambda: None), (TD, "_evidence_sweep", lambda a, act: sweeps.append(act)),
                       (TD, "LOG", log0), (TD, "TRIES", None)],
                      lambda: TD.cmd_watch(args))
        return rc, passes, beats[-1], clock["now"], sweeps
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            Path("output").mkdir()

            def server_down(n=0):                                       # 매 바퀴 같은 계정 서버 오류
                why = TD.TRIES.why_not("srv", "계정 처리(정기)", "정기")
                if not why:
                    TD.TRIES.fail("srv", "계정 처리(정기)", "ServerBusy: 504", "정기")
                return False, 0
            rc, passes, last, end, sweeps = watch(server_down, 0, wait_pass=server_down)
            assert rc == 0 and [k for k, _ in passes] == ["전체", "남은 일", "남은 일"] and last[0] == "완료·실패 확인",                 (rc, passes, last)                                          # 오류 다시 시도 = 남은 일 바퀴(D-382 — 옛 = 전체 3번)
            assert end < RealDT(2026, 11, 21, 4, 0) and "확인 필요" in last[1], (end, last)   # 24:00 전 조기 종료
            assert [b - a for (_, a), (_, b) in zip(passes, passes[1:])] == [timedelta(seconds=TD.WATCH_POLL_SEC)] * 2, passes
            rc, passes, last, end, sweeps = watch(lambda n: (False, 0), 1)   # 쿠팡 파일 생성 대기만 계속
            kinds = [k for k, _ in passes]
            assert kinds[0] == "전체" and set(kinds[1:]) == {"남은 일"} and len(kinds) > 4, kinds   # 그 뒤 = 남은 일(대기 계정만)
            gaps = {b - a for (_, a), (_, b) in zip(passes, passes[1:])}
            assert gaps == {timedelta(minutes=20)} and TD.WATCH_PENDING_SEC == 1200, gaps                  # 20분마다
            assert last[0] == "종료" and "회차 종료" in last[1] and RealDT(2026, 11, 22, 0, 0) <= end, (last, end)   # 24:00 끝
            assert passes[-1][1] < RealDT(2026, 11, 22, 0, 0) and sweeps == ["done"], (passes[-1], sweeps)     # 빈 시간 증빙 1번
            rc, passes, last, end, sweeps = watch(lambda n: (False, 0), lambda n: 1 if n < 3 else 0)   # 대기 바퀴 2번째에 다 받음
            assert [k for k, _ in passes] == ["전체", "남은 일", "남은 일"] and last[0] == "완료", (passes, last)
            assert end < RealDT(2026, 11, 21, 4, 0) and sweeps == ["done", "done"], (end, sweeps)      # 일찍 끝남 · 끝 증빙 = 남은 것만
            rc, passes, last, end, sweeps = watch(lambda n: (False, 0), 1,
                                                  wait_pass=lambda n: (TD.TRIES.fail("A", "받기", "504") and (False, 0)) or (False, 0))
            assert {b - a for (_, a), (_, b) in zip(passes[1:], passes[2:4])} == {timedelta(seconds=TD.WATCH_POLL_SEC)}, passes[:4]
            assert (Path(TD.BASE) / "로그" / TR.STATE_NAME).exists()
        finally:
            os.chdir(cwd)
    ok("3번 소진 = 24:00 전 '완료·실패 확인' 종료 · 생성 대기만 = 대기 계정만 20분마다 24:00 까지(빈 시간 증빙 1번) · "
       "대기 끝나면 일찍 종료 · 대기 중 오류 다시 시도 = 5분 그대로")

    # ⑦ 대기 바퀴 대상 = 받으러 갈 파일이 있는 계정만(다 받은 계정·비밀번호 거부·3번 소진 = 로그인 0) · 그 계정은 받기만
    with tempfile.TemporaryDirectory() as tmp:
        jobs_p = Path(tmp) / "_요청기록.json"
        SJ.save_jobs(jobs_p, [
            SJ.Job("A", "윙", "주정산", "정산", "2026-11-10", "2026-11-16", "2026-11-20", status=SJ.ST_REQUESTED),
            SJ.Job("B", "윙", "주정산", "정산", "2026-11-10", "2026-11-16", "2026-11-20", status=SJ.ST_DONE),
            SJ.Job("P", "윙", "주정산", "정산", "2026-11-10", "2026-11-16", "2026-11-20", status=SJ.ST_REQUESTED),
            SJ.Job("G", "윙", "주정산", "정산", "2026-11-10", "2026-11-16", "2026-11-20", status=SJ.ST_REQUESTED)])
        tries = TR.Tries(Path(tmp) / "로그", CYC, line=lambda m: None)
        tries.begin_pass("p0")
        tries.fail("P", "로그인", "비밀번호 오류", kind=TR.PASSWORD)
        for p in ("p1", "p2", "p3"):
            tries.begin_pass(p)
            tries.fail("G", "받기 윙 주정산·정산", "표 머리글 없음", "정산일 2026-11-20 · 기간 2026-11-10~2026-11-16")
        visits: list = []
        did: list = []

        @contextlib.contextmanager
        def fake_session(a, hidden, until=None):
            visits.append(a.account_id)
            yield None
        everyone = [Acc(i) for i in ("A", "B", "P", "G")]
        done = {"정기": {"A", "B", "P", "G"}, "소급": {"A", "B", "P", "G"}}          # 회차 첫 전체 바퀴에서 정기·소급 끝남

        def wait_once():
            TD._plan_rest({}, False, RLG.RunLog(tmp, now=RealDT(2026, 11, 21, 4), echo=lambda m: None))
            return TD._rest_pass(Args), TD._pending_jobs()
        res = _patched([(TD, "TRIES", tries), (TD, "JOBS", jobs_p), (TD, "BASE", Path(tmp)), (TD, "name_of", lambda a: a.account_id),
                        (TD, "session", fake_session), (TD, "PASS_ACCOUNTS", everyone), (TD, "PHASE_DONE", done),
                        (TD, "REST_PLAN", {}), (TD, "CYCLE", RLG.Totals()),
                        (TD, "cmd_download", lambda a, b, args, jobs: did.append(("받기", a.account_id))),
                        (TD, "cmd_request", lambda a, b, args, jobs: did.append(("요청", a.account_id)))], wait_once)
        assert visits == ["A"] and did == [("받기", "A")], (visits, did)       # B 다 받음·P 비밀번호 거부·G 3번 소진 = 로그인 0
        assert res == ((False, 0), 1), res                                     # 받으러 갈 것 = A 1건
    ok("대기 바퀴 = 받으러 갈 파일 계정만 로그인(다 받음·비밀번호 거부·3번 소진 = 0) · 받기만(검증·광고·소급 안 함)")

    # ⑧ 끝 상태 = 끝나는 방식과 상관없이 같음(배포 검증 sim S2·S2b·S2c 11-20) — 마지막이 대기 바퀴여도 비밀번호 거부 계정이 '실패'에 남음
    with tempfile.TemporaryDirectory() as tmp:
        tries = TR.Tries(Path(tmp) / "로그", CYC, line=lambda m: None)
        tries.begin_pass("p1")
        tries.fail("B", "로그인", "비밀번호 오류(재시도 안 함)", kind=TR.PASSWORD)
        full = RLG.RunLog(tmp, now=RealDT(2026, 11, 21, 1), echo=lambda m: None)    # 마지막 = 전체 바퀴(B 로그인 실패 줄 있음)
        full.record("B", "로그인", RLG.FAIL, "비밀번호 오류·잠금 의심 — 재시도 안 함")
        wait = RLG.RunLog(tmp, now=RealDT(2026, 11, 21, 5), echo=lambda m: None)    # 마지막 = 대기 바퀴(B 안 들어감)
        wait.record("C", "받기", RLG.OK, "정산 파일")

        def fails(lg):
            return _patched([(TD, "TRIES", tries), (TD, "LOG", lg), (TD, "JOBS", Path(tmp) / "_요청기록.json")], TD._watch_failures)
        f_full, f_wait = fails(full), fails(wait)
        assert f_full == f_wait == {"B": "로그인"}, (f_full, f_wait)
        a_full, a_wait = W.plan_after_pass(False, 0, 0, 0, failed=f_full), W.plan_after_pass(False, 0, 0, 0, failed=f_wait)
        assert a_full == a_wait and "실패 1계정(로그인 1)" in a_wait[1] and W.done_status(len(f_wait)) == "완료·실패 확인", a_wait
        tries.begin_pass("p2")
        tries.ok("B", "로그인")                                                      # 대장 비밀번호 고쳐 로그인 성공 = 빠짐
        assert fails(wait) == {}, "로그인 성공한 계정은 실패에서 빠짐"
    ok("끝 상태·문구 = 마지막이 대기 바퀴여도 비밀번호 거부 계정 '실패(로그인)' 그대로 · 로그인 성공하면 빠짐")

    # ⑥ 월자료 실패 달 — 다시 시도 남으면 다음 바퀴에 다시(D-245 '그 회차 다시 안 부름' 부분 대체) · 3번째 실패 뒤 건너뜀
    with tempfile.TemporaryDirectory() as tmp:
        tries = TR.Tries(Path(tmp), CYC, line=lambda m: None)
        skip: set = set()
        for p in range(3):
            tries.begin_pass(f"p{p}")
            skip.add("주문별매출 202609")
            _patched([(TD, "TRIES", tries)], lambda: TD._docs_retry(
                "A", {"주문별매출 202609"}, ["주문별매출 202609: SiteChangedError: 쪽 수 다름"], skip))
            assert ("주문별매출 202609" in skip) == (p == 2), (p, skip)
        e = next(iter(tries.items.values()))
        assert (e["항목"], e["데이터"], e["시도"], e["사유"]) == ("월자료 주문별매출", "202609", 3, "SiteChangedError: 쪽 수 다름"), e
        skip2: set = {"라이브정산 202610"}
        _patched([(TD, "TRIES", None)], lambda: TD._docs_retry("A", {"라이브정산 202610"}, [], skip2))
        assert skip2 == {"라이브정산 202610"}, "watch 밖(사람 명령) = 지금 그대로(그 실행에서 다시 안 부름)"
    ok("월자료 실패 달 = 3번까지 다음 바퀴에 다시 · 그 뒤 건너뜀 · 사람 명령은 그대로")


def p71_wait_rest_open_to_transfer():
    print("[P71] 대기 바퀴 사이 20분 쉼 = 셀독전환이 계정 시작 가능(쉼 표시) · 바퀴 도는 중·5분 다시 시도 쉼 = 지금처럼 기다림 · "
          "남은 표시 = 새 watch 가 시작 때 지움 · 끝나면 없음 · 이중 watch 막기(잠금) 그대로(D-375 B1)")
    import os
    from datetime import datetime as RealDT, timedelta
    from types import SimpleNamespace
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import settlement_download as TD
    from coupang_analytics import settlement_retry as TR
    from coupang_analytics import settlement_runlog as RLG
    from coupang_analytics import settlement_watch as W
    from coupang_analytics import transfer_login as TL
    from coupang_analytics.registry_lock import RegistryLockError, registry_lock
    clock = {"now": RealDT(2026, 11, 21, 3, 0)}
    seen: list = []                               # (언제, 표시 있음, 전환 busy_reason)

    class FakeDT(RealDT):
        @classmethod
        def now(cls, tz=None):
            return clock["now"]

    def look(kind):
        seen.append((kind, TL.WATCH_REST.exists(), TL.busy_reason(now=lambda: clock["now"] + timedelta(seconds=1))))

    def fake_sleep(sec):
        look(f"쉼 {int(sec)}")
        clock["now"] += timedelta(seconds=max(sec, 1))

    def op(kind, fn):
        def run(args):
            look(kind)
            TD.LOG = RLG.RunLog(TD.BASE, now=clock["now"], echo=lambda m: None)
            TD.LOG.heartbeat = lambda st, msg="", **k: None
            TD.TRIES.begin_pass(f"p{len(seen)}")
            return fn()
        return run
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            Path("output").mkdir()
            W.mark_rest(RealDT(2026, 11, 21, 3, 15), TL.WATCH_REST, now=RealDT(2026, 11, 21, 2, 55))   # 죽은 watch 가 남긴 표시
            fails = {"n": 0}

            def wait_pass():                     # 대기 바퀴 3번째 = 서버 오류 1번(다시 시도 5분 쉼)
                fails["n"] += 1
                if fails["n"] == 3:
                    TD.TRIES.fail("A", "받기", "504")
                return False, 0
            log0 = RLG.RunLog(TD.BASE, now=clock["now"], echo=lambda m: None)
            log0.heartbeat = lambda st, msg="", **k: None
            args = SimpleNamespace(parent=0, ledger_synced=True, until="", until_at=None, hidden=False, manual=True)
            rc = _patched([(TD, "datetime", FakeDT), (TD.time, "sleep", fake_sleep),
                           (TD, "_one_pass", op("전체", lambda: (False, 0))), (TD, "_rest_pass", op("대기", wait_pass)),
                           (TD, "_pending_jobs", lambda: 1), (TD, "_between_passes", lambda: None),
                           (TD, "_evidence_sweep", lambda a, act: None), (TD, "LOG", log0), (TD, "TRIES", None)],
                          lambda: TD.cmd_watch(args))
            assert rc == 0 and clock["now"] >= RealDT(2026, 11, 22, 0, 0), (rc, clock)
            busy = "정산 자동 다운로드"
            first = seen[0]
            assert first[0] == "전체" and not first[1] and busy in first[2], f"시작 = 남은 표시 지움 · 바퀴 중 = 기다림: {first}"
            passes = [s for s in seen if s[0] in ("전체", "대기")]
            assert all(not m and busy in why for _, m, why in passes), f"바퀴 도는 중 = 표시 없음·기다림: {passes}"
            rests20 = [s for s in seen if s[0] == f"쉼 {TD.WATCH_PENDING_SEC}"]
            assert len(rests20) > 10 and all(m and why == "" for _, m, why in rests20), f"20분 쉼 = 계정 시작 가능: {rests20[:3]}"
            rests5 = [s for s in seen if s[0] == f"쉼 {TD.WATCH_POLL_SEC}"]
            assert rests5 and all(not m and busy in why for _, m, why in rests5), f"5분 다시 시도 쉼 = 기다림: {rests5}"
            assert not TL.WATCH_REST.exists() and TL.busy_reason() == "", "끝나면 표시 없음·잠금 풀림"
            with registry_lock(TL.BUSY_LOCKS[1], wait_sec=0):     # 이중 실행 막기 = 그대로(쉬는 중에도 잠금은 쥠)
                try:
                    with registry_lock(TL.BUSY_LOCKS[1], wait_sec=0):
                        raise AssertionError("잠금이 두 번 잡힘")
                except RegistryLockError:
                    pass
            assert Path(TD.BASE / "_잠금" / "_watch.lock") == TL.BUSY_LOCKS[1] and TL.WATCH_REST.parent == TD.BASE / "_잠금"
            (Path(TD.BASE) / "로그" / TR.STATE_NAME).unlink(missing_ok=True)
        finally:
            os.chdir(cwd)
    ok("시작 = 남은 표시 지움 · 전체·대기 바퀴 도는 중 = 표시 없음(전환 기다림) · 20분 쉼 = 표시(전환 계정 시작) · 5분 다시 시도 쉼 = "
       "기다림 · 끝나면 표시 없음 · 같은 잠금 경로")


def p72_rest_pass_left_work_only():
    print("[P72] 남은 일 바퀴(D-382 · 소유자 11-23 '1~6 전부 수용') — 회차 첫 바퀴 뒤 = 오류 남은 계정의 오류 단계만 · 못 끝낸 정기·소급"
          " = 전부 · 생성 대기 = 받기 · 정기 = 회차 첫 바퀴 1번 · 새 요청 0 = 90초 안 기다림 · 3번 규칙·끝 문구 그대로")
    import contextlib
    from datetime import datetime as RealDT, timedelta
    from types import SimpleNamespace
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import settlement_download as TD
    from coupang_analytics import settlement_jobs as SJ
    from coupang_analytics import settlement_retry as TR
    from coupang_analytics import settlement_runlog as RLG
    from coupang_analytics import settlement_wing_api as API
    CYC = "2026-11-22T00:10:00"
    RealLog = RLG.RunLog

    class Acc:
        def __init__(self, i):
            self.account_id, self.label = i, i

    def world(tmp, ids, **beh):
        """가짜 쿠팡(계정·단계별 동작) + 실제 _one_pass/_rest_pass/_run_accounts/cmd_run/cmd_backfill/_plan_rest."""
        B = {k: set() for k in ("busy", "pw", "otp", "block", "srv", "boom", "ads_fail", "docs_fail", "dl_fail")}
        B.update({"asked": {}, "days": {}, "left": {}}, **beh)
        calls: list = []
        sleeps: list = []
        clock = {"t": RealDT(2026, 11, 22, 1, 0)}
        tries = TR.Tries(Path(tmp) / "로그", CYC, line=lambda m: None)

        def runlog(base, **k):                     # 바퀴마다 다른 실행ID(같은 초 = 같은 바퀴로 세지 않게)
            clock["t"] += timedelta(minutes=7)
            return RealLog(base, now=clock["t"], echo=lambda m: None)

        @contextlib.contextmanager
        def session(a, hidden, until=None):
            n = a.account_id
            calls.append((n, "로그인"))
            if n in B["busy"]:
                raise TD.SessionSkip("이 계정 Chrome 이 계속 실행 중")
            for key, kind in (("pw", TR.PASSWORD), ("otp", TR.HUMAN), ("block", TR.BLOCK)):
                if n in B[key]:
                    raise TD.SessionSkip(f"로그인 실패({key})", kind)
            TD._try_ok(n, "로그인")
            yield None

        def step(name, fn=None):
            def run(a, *rest):
                calls.append((a.account_id, name))
                return fn(a.account_id) if fn else None
            return run

        def request(n):
            if n in B["srv"]:
                raise API.ServerBusy("/tenants/x → 504 서버 일시 오류")
            if n in B["boom"]:
                raise RuntimeError("표 머리글 없음")
            return B["asked"].get(n, 0)

        def download(n):
            if n in B["dl_fail"]:
                TD._try_fail(n, "받기 윙 주정산·정산", "SiteChangedError: 파싱", "정산일 2026-11-21")

        def ads(n):
            if n in B["ads_fail"]:
                TD._try_fail(n, "광고비", "ServerBusy 500", "광고비·밀크런 원천")
            else:
                TD._try_ok(n, "광고비", "광고비·밀크런 원천")

        def sales(n):
            TD.LOG.remaining(n, "판매분석", B["left"].get(n, 0), "일")
            return B["days"].get(n, 0)

        def docs(n):
            if n in B["docs_fail"]:
                TD.TRIES.fail(n, "월자료 주문별매출", "SiteChangedError: 맞지 않음", "202609")
            TD.LOG.remaining(n, "월자료", 0, "달")
            return 0
        args = SimpleNamespace(start=D("2026-01-01"), end=D("2026-11-22"), until="", until_at=None, hidden=True, dry_run=False,
                               cap=99, command="watch", cycle_since=CYC)
        accts = [Acc(i) for i in ids]
        pat = [(TD, "session", session), (TD, "name_of", lambda a: a.account_id), (TD, "TRIES", tries), (TD, "LOG", None),
               (TD, "BASE", Path(tmp)), (TD, "JOBS", Path(tmp) / "_요청기록.json"), (TD, "PASS_ACCOUNTS", []),
               (TD, "PHASE_DONE", {"정기": set(), "소급": set()}), (TD, "REST_PLAN", {}), (TD, "CYCLE", RLG.Totals()),
               (TD.RL, "RunLog", runlog), (TD, "load_accounts", lambda only: list(accts)), (TD, "_mem", lambda *a, **k: None),
               (TD, "MEMLOG", SimpleNamespace(around=lambda *a, **k: contextlib.nullcontext())),
               (TD, "_stats_in_child", lambda: calls.append(("(전체)", "집계"))), (TD, "_backlog_left", lambda accts, args: None),
               (TD.time, "sleep", sleeps.append),
               (TD, "cmd_request", step("조회", request)), (TD, "cmd_download", step("받기", download)),
               (TD, "collect_verify", step("검증")), (TD, "collect_ads", step("광고", ads)),
               (TD, "collect_sales", step("판매분석", sales)), (TD, "collect_docs", step("월자료", docs)),
               (TD, "request_docs", step("월자료요청", lambda n: 0))]
        return B, calls, sleeps, args, pat

    last: dict = {}

    def run(pat, kinds):
        """kinds 순서대로 바퀴 → [(그 바퀴 부른 것, 그 뒤 다시 시도 수, 그 뒤 계획)] · 마지막 바퀴 기록 = last['log']."""
        def go():
            out = []
            for k in kinds:
                n0 = len(calls)
                (TD._one_pass if k == "전체" else TD._rest_pass)(args)
                out.append((calls[n0:], TD._retry_count(), {n: set(s) for n, s in TD.REST_PLAN.items()}))
            last["log"] = TD.LOG
            return out
        return _patched(pat, go)

    def after(pat, fn):                              # 마지막 바퀴 기록으로 fn(끝 문구·다시 계획)
        return _patched(pat + [(TD, "LOG", last["log"])], fn)
    FULL_A = [("A", "로그인"), ("A", "조회"), ("A", "받기"), ("A", "검증"), ("A", "광고")]
    BACK_A = [("A", "로그인"), ("A", "판매분석"), ("A", "월자료"), ("A", "월자료요청")]

    # 1·9 월자료 실패 → 다음 바퀴 = A 의 월자료만(조회·90초·광고·판매분석 0번 · B·C 로그인 0) · 성공하면 남은 일 없음
    with tempfile.TemporaryDirectory() as tmp:
        B, calls, sleeps, args, pat = world(tmp, ["A", "B", "C"], docs_fail={"A"})
        (full, r1, p1), = run(pat, ["전체"])
        assert ("B", "조회") in full and ("C", "판매분석") in full and 90 not in sleeps, (full, sleeps)   # E: 새 요청 0 = 안 기다림
        assert r1 == 1 and p1 == {"A": {"월자료"}}, (r1, p1)
        B["docs_fail"].clear()
        (rest, r2, p2), = run(pat, ["남은 일"])
        assert rest == [("A", "로그인"), ("A", "월자료")] and r2 == 0 and p2 == {}, (rest, r2, p2)
    ok("월자료 실패 → 다음 바퀴 = 그 계정 월자료만(다른 계정 로그인 0 · 정산 일정 조회·90초·광고·판매분석 0) · 성공 = 남은 일 없음")

    # 2 광고비 실패 → 광고만 · 3 받기 파싱 오류 → 받기만 · 3번째 실패 뒤 그 회차 안 들어감
    with tempfile.TemporaryDirectory() as tmp:
        B, calls, sleeps, args, pat = world(tmp, ["A", "B"], ads_fail={"A"}, dl_fail={"B"})
        got = run(pat, ["전체", "남은 일", "남은 일", "남은 일"])
        assert got[1][0] == [("A", "로그인"), ("A", "광고"), ("B", "로그인"), ("B", "받기")], got[1][0]
        assert got[2][0] == got[1][0] and got[3][0] == [] and [g[1] for g in got] == [2, 2, 0, 0], got   # 처음 + 다시 2번
        assert {e["시도"] for e in TD.TR.Tries(Path(tmp) / "로그", CYC).items.values()} == {3}
    ok("광고비 실패 = 광고만 · 받기 실패 = 받기만 · 처음 + 다시 2번 뒤 그 회차 로그인 0(D-373 그대로)")

    # 4 정기 서버 오류 → 정기만(그 바퀴 소급은 끝남) · 정기 3번 = 바퀴 종류 상관없이 · 5 로그인 차단 → 정기+소급 전부
    with tempfile.TemporaryDirectory() as tmp:
        B, calls, sleeps, args, pat = world(tmp, ["A", "K", "C"], srv={"A"}, block={"K"})
        got = run(pat, ["전체", "남은 일"])
        assert got[0][2] == {"A": {"정기"}, "K": {"정기", "소급"}}, got[0][2]
        rest = got[1][0]
        assert rest[:2] == [("A", "로그인"), ("A", "조회")] and ("A", "판매분석") not in rest, rest
        assert rest[2:] == [("K", "로그인")] and ("C", "로그인") not in rest, rest
        B["srv"].clear()
        B["block"].clear()
        got = run(pat, ["남은 일"])
        assert got[0][0] == FULL_A + [("K", "로그인"), ("K", "조회"), ("K", "받기"), ("K", "검증"), ("K", "광고"),
                                      ("K", "판매분석"), ("K", "월자료"), ("K", "월자료요청")] and got[0][2] == {}, got
    with tempfile.TemporaryDirectory() as tmp:
        B, calls, sleeps, args, pat = world(tmp, ["A"], srv={"A"})
        got = run(pat, ["전체", "남은 일", "남은 일", "남은 일"])
        assert [len([c for c in g[0] if c[1] == "조회"]) for g in got] == [1, 1, 1, 0] and got[3][2] == {}, got
        e = TD.TR.Tries(Path(tmp) / "로그", CYC).items
        assert [(v["항목"], v["시도"], v["결과"]) for v in e.values()] == [("계정 처리(정기)", 3, TR.GIVE_UP)], e
    ok("정기 서버 오류 = 정기만(소급 끝남) · 정기 3번 = 전체·남은 일 바퀴 합쳐 3번 · 로그인 차단 = 정기+소급 전부")

    # 6 '사용 중'으로 정기 못 끝낸 계정(시도표 밖) + 다른 계정 오류 → 그 계정 = 정기+소급 전부 · 오류 계정 = 오류 단계만
    # 7 비밀번호 거부·2차 인증·3번 소진 = 남은 일 바퀴 로그인 0 · 끝 문구 '실패'에 그대로
    with tempfile.TemporaryDirectory() as tmp:
        B, calls, sleeps, args, pat = world(tmp, ["A", "U", "P", "H"], docs_fail={"A"}, busy={"U"}, pw={"P"}, otp={"H"})
        got = run(pat, ["전체"])
        assert got[0][2] == {"A": {"월자료"}, "U": {"정기", "소급"}}, got[0][2]
        B["busy"].clear()
        got = run(pat, ["남은 일"])
        assert got[0][0] == [("A", "로그인"), ("A", "월자료"), ("U", "로그인"), ("U", "조회"), ("U", "받기"), ("U", "검증"),
                             ("U", "광고"), ("U", "판매분석"), ("U", "월자료"), ("U", "월자료요청")], got[0][0]
        fails = after(pat, TD._watch_failures)
        assert {"P", "H"} <= set(fails), fails
    ok("사용 중으로 못 끝낸 계정 = 정기+소급 전부 · 오류 계정 = 그 단계만 · 비밀번호 거부·2차 인증 = 로그인 0·끝 문구에 남음")

    # 8 생성 대기 + 오류 = 한 바퀴에 같이(대기 계정 = 받기만 · 요청예정 = 요청 뒤 90초는 새 요청 있을 때만) · 12 'again' 뒤 = 정기 없음
    with tempfile.TemporaryDirectory() as tmp:
        B, calls, sleeps, args, pat = world(tmp, ["A", "W", "Q", "S"], docs_fail={"A"}, asked={"Q": 1},
                                            days={"S": 60}, left={"S": 30})
        got = run(pat, ["전체"])
        SJ.save_jobs(Path(tmp) / "_요청기록.json", [
            SJ.Job("W", "윙", "주정산", "정산", "2026-11-10", "2026-11-16", "2026-11-21", status=SJ.ST_REQUESTED, ref="r1"),
            SJ.Job("Q", "윙", "주정산", "정산", "2026-11-10", "2026-11-16", "2026-11-21", status=SJ.ST_PLANNED)])
        assert sleeps.count(90) == 1, sleeps                                  # 전체 바퀴 = 새 요청 있던 Q 만 90초(E)
        after(pat, lambda: TD._plan_rest({}, False, TD.LOG))                   # 받을 파일이 생긴 뒤 다시 계획(같은 규칙)
        plan = after(pat, lambda: dict(TD.REST_PLAN))
        assert plan == {"A": {"월자료"}, "W": {"받기"}, "Q": {"받기"}, "S": {"소급"}}, plan   # S = 소급이 일했고 밀린 소급 남음(D)
        B["days"], sleeps[:] = {}, []
        got = run(pat, ["남은 일"])
        assert got[0][0] == [("A", "로그인"), ("A", "월자료"), ("W", "로그인"), ("W", "받기"), ("Q", "로그인"), ("Q", "조회"),
                             ("Q", "받기"), ("S", "로그인"), ("S", "판매분석"), ("S", "월자료"), ("S", "월자료요청")], got[0][0]
        assert sleeps.count(90) == 1 and not [c for c in got[0][0] if c[1] in ("검증", "광고")], (sleeps, got)   # 정기 = 첫 바퀴 1번
        B["asked"] = {}
        after(pat, lambda: TD._plan_rest({}, False, TD.LOG))
        sleeps[:] = []
        got = run(pat, ["남은 일"])
        assert ("Q", "조회") in got[0][0] and 90 not in sleeps, (got, sleeps)   # 새 요청 0 = 안 기다림
    ok("생성 대기·요청예정·오류·밀린 소급 = 한 바퀴에 그 단계만 · 정기 다시 안 함 · 90초 = 새 요청 있을 때만")

    # 10 남은 일 바퀴가 연속 실패로 중단 = 못 간 계정 계획 그대로 다음 바퀴에
    with tempfile.TemporaryDirectory() as tmp:
        B, calls, sleeps, args, pat = world(tmp, ["X", "G", "Y", "Z"], docs_fail={"Z"}, boom={"X", "Y"})   # 전체 = G 가 사이(중단 아님)
        got = run(pat, ["전체", "남은 일"])
        assert got[0][2] == {"X": {"정기"}, "Y": {"정기"}, "Z": {"월자료"}}, got[0][2]
        assert [c for c in got[1][0] if c[1] == "로그인"] == [("X", "로그인"), ("Y", "로그인")], got[1][0]   # 연속 2계정 = 중단
        assert got[1][2] == {"X": {"정기"}, "Y": {"정기"}, "Z": {"월자료"}}, got[1][2]                     # Z = 그대로
    ok("남은 일 바퀴 중단 = 못 간 계정 계획 유지(다음 바퀴에)")


def main():
    p10_wing_api_parse()
    p11_runlog()
    p12_watch_decide()
    p13_accounts_file()
    p14_status_reader()
    p15_browser_closed_transient()
    p16_cost_by_product()
    p17_server_busy()
    p18_verify_collect()
    p19_verify_sheet()
    p20_rg_payout_dates()
    p21_bank_inflows()
    p22_paydates_verify()
    p23_calendar()
    p24_local_store()
    p25_app_launch()
    p26_parent_watch()
    p27_cycle()
    p27b_schedule_one_place()
    p28_wait_app_profile()
    p29_monthly_failed_comment()
    p30_manual_full_run()
    p31_keep_originals()
    p32_evidence_rules()
    p33_login_password_source()
    p34_forecast_accuracy()
    p35_amounts_from()
    p36_same_cycle_done()
    p37_accounts_from_registry()
    p38_wing_extra_settlement()
    p39_favorable_refund()
    p40_orphan_ship_returns()
    p41_ad_reports()
    p42_inbound()
    p43_collect_throttle_isolation()
    p44_adcenter_navigation()
    p45_ad_report_csv()
    p46_verify_keep_previous()
    p47_settle_sales_coupons()
    p48_ads_from_december()
    p49_rg_missing_costs()
    p50_verify_new_items()
    p51_regular_then_backfill()
    p52_settlement_docs()
    p53_vat_detail_requests()
    p54_result_summary()
    p55_rg_vendor_fallback()
    p56_one_failure_not_blocking()
    p57_backlog_all_accounts()
    p58_stats_keep_latest()
    p59_suspended_pending()
    p60_memory_floor_finally()
    p61_self_exit_when_taskkill_fails()
    p62_stats_separate_process()
    p63_own_chrome_sweep()
    p64_memory_log_line()
    p65_settlement_memory_lines()
    p66_openblas_one_thread()
    p67_manual_start()
    p68_evidence_auto()
    p69_ledger_presync()
    p70_error_retry_three()
    p71_wait_rest_open_to_transfer()
    p72_rest_pass_left_work_only()
    print("정산 런타임 오프라인 검증 통과")


if __name__ == "__main__":
    main()
