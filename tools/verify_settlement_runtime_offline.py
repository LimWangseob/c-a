"""정산 다운로드·검증 런타임 오프라인 검증 — 주소 응답 해석·실행 기록·감시 판단·계정 파일·상태 화면·차단/일시 오류
구분·검증 자료 수집·검증 시트·지급일 대조·계좌 입금·정산캘린더. verify_settlement_offline.py(계산·파싱 골든)에서 분리.

로그인·쿠팡 주소·공휴일 API 호출 없음(결정적·가짜 응답). 실패 시 AssertionError → exit 1. run_checks 게이트.

    python tools/verify_settlement_runtime_offline.py
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

D = date.fromisoformat


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
           "totalContainerUnloadingFeeDeductionAmount": 5000}
    assert API.cost_reports(det) == ("보관비", "입출고/배송비", "재고 손실 보상")
    r70 = {**rresp["settlementStatusReports"][0], "settlementRatio": 70, "settlementStatusReportDetail": det}
    ev70 = API.rg_events({"settlementStatusReports": [r70]}, "계정A")[0]
    assert ev70.reports == ("보관비", "입출고/배송비", "재고 손실 보상") and SJ.reports_for(ev70)[0] == "판매수수료"
    assert API.unmapped_costs({"settlementStatusReports": [r70]}) == [
        "V1-2026-07-27-2026-07-31: totalContainerUnloadingFeeDeductionAmount=5000"]
    cj = SJ.Job("a", "로켓그로스", "주정산", "입출고/배송비", "x", "y", "z", ref="k")
    assert API.rg_request_body(cj, 1)["sellerReportType"] == "WAREHOUSING_SHIPPING"
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
    assert W.plan_after_pass(True, 5, 3, 1, 0)[0] == "later"                       # 연속 실패/차단 = 이번 바퀴만 멈춤(D-031)
    assert W.plan_after_pass(False, 4, 9, 0, 0)[0] == "again"                       # 받는 중(소급) = 곧 다음 바퀴
    assert W.plan_after_pass(False, 0, 2, 0, 1)[0] == "later"                       # 파일 생성 대기 = 잠시 뒤
    assert W.plan_after_pass(False, 0, 0, 1, 1)[0] == "later"                       # 서버 일시 오류 계정 = 잠시 뒤
    a, r = W.plan_after_pass(False, 0, 2, 0, W.MAX_IDLE_PASSES)
    assert a == "giveup" and "남음" in r                                           # 진전 없이 반복 = 미완료 종료
    a, r = W.plan_after_pass(False, 0, 0, 0, 1)
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
    assert len(d["조회 실패"]) == 1 and "매출내역 202609" in d["조회 실패"][0]
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
                          "2026-10-05")}   # 테스트 주입(쿠팡 실지급일과 맞춘 영업일 기준)
    cases = [  # (지급비율, 기간 시작, 기간 끝, 실제 지급일) — nicoable·bux1004 등 운용 PC 정산현황 실값
        (70, "2026-07-27", "2026-07-31", "2026-08-31"), (30, "2026-07-27", "2026-07-31", "2026-09-07"),   # 소유자 화면 확인
        (30, "2026-08-01", "2026-08-02", "2026-09-07"), (30, "2026-08-03", "2026-08-09", "2026-10-01"),
        (70, "2026-08-31", "2026-08-31", "2026-10-07"),
        (100, "2026-01-26", "2026-01-31", "2026-03-05"), (100, "2026-05-25", "2026-05-31", "2026-06-29"),
        (30, "2026-06-01", "2026-06-07", "2026-08-03"), (70, "2026-04-13", "2026-04-19", "2026-05-19"),
        (70, "2026-06-15", "2026-06-21", "2026-07-20")]
    for ratio, ps, pe, want in cases:
        got = P.rg_payout_date(ratio, D(ps), D(pe), hol)
        assert got == D(want), (ratio, ps, pe, got, want)
    expect(ValueError, lambda: P.rg_payout_date(50, D("2026-08-03"), D("2026-08-09"), hol), "모르는 지급비율")
    old = P.payout_date(P.PAYOUT_RG_WEEKLY_FINAL, revenue_month="2026-07", holidays=hol)
    assert old != D("2026-09-07")                                                      # 옛 규칙(익익월)은 월걸침 주를 못 맞춤
    ok("70%·100%=+20(5/1·7/17 비영업일 반영)·30% 월걸침=+25(07-27~31·08-01~02→09-07)·30% 일반=익익월·모르는 비율=오류")


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
            assert got == {D("2026-08-17"), D("2026-10-05")}                                 # 캐시 우선(키 없어도)
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


def p27_cycle():
    print("[P27] 정산 회차(D-021) — 18:00 앱과 함께 기동·①완료까지 대기·다 받으면 종료·다음 날 17:55 종료")
    import json as _json
    import os
    from datetime import datetime as RealDT, timedelta
    from types import SimpleNamespace
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import settlement_download as TD
    from coupang_analytics import settlement_runlog as RLG
    from coupang_analytics import settlement_watch as W
    D = RealDT
    assert W.cycle_window(D(2026, 10, 10, 18, 0, 5)) == (D(2026, 10, 10, 18), D(2026, 10, 11, 17, 55))
    assert W.cycle_window(D(2026, 10, 11, 3, 0)) == (D(2026, 10, 10, 18), D(2026, 10, 11, 17, 55)), "새벽=전날 18시 회차"
    assert W.cycle_window(D(2026, 10, 11, 18, 0))[0] == D(2026, 10, 11, 18), "18:00 = 새 회차"
    start = D(2026, 10, 10, 18)
    assert W.sales_done_in_cycle({"stage": "sales", "at": D(2026, 10, 10, 19)}, start)
    assert W.sales_done_in_cycle({"stage": "done", "at": D(2026, 10, 11, 2)}, start)
    assert not W.sales_done_in_cycle({"stage": "sales", "at": D(2026, 10, 9, 19)}, start), "지난 회차 ① = 대기"
    assert not W.sales_done_in_cycle(None, start)

    def run(marker_at, sales_after=None):
        """가짜 시계로 cmd_watch 한 회차 실행 → (반환값, 한 바퀴 호출 수, 마지막 상태, until_at, 종료 시각)."""
        clock = {"now": D(2026, 10, 10, 18, 0, 5)}
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
        olds = (TD.datetime, TD.time.sleep, TD._one_pass, TD._pending_jobs, TD._wait_accounts, TD.LOG)
        args = SimpleNamespace(parent=0, until="", until_at=None, hidden=False)
        try:
            TD.datetime, TD.time.sleep = FakeDT, fake_sleep
            TD._one_pass = lambda a: (passes.append(clock["now"]), (False, 3 if len(passes) == 1 else 0))[1]   # 첫 바퀴 3건·다음 0건
            TD._pending_jobs, TD._wait_accounts = (lambda: 0), (lambda lg: 0)
            TD.LOG = RLG.RunLog(TD.BASE, now=clock["now"], echo=lambda m: None)
            TD.LOG.heartbeat = lambda st, msg: hb.append((st, msg))
            rc = TD.cmd_watch(args)
        finally:
            TD.datetime, TD.time.sleep, TD._one_pass, TD._pending_jobs, TD._wait_accounts, TD.LOG = olds
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
            assert end <= D(2026, 10, 11, 17, 55) + timedelta(seconds=1) and until_at == D(2026, 10, 11, 17, 55)
            rc, passes, last, _, _ = run(D(2026, 10, 9, 19))                # 지난 회차 ① 기록만 = 받지 않음
            assert passes == [] and last[0] == "종료", (passes, last)
            rc, passes, last, _, _ = run(None, sales_after=D(2026, 10, 10, 19, 30))   # 19:30 ① 완료 → 받기
            assert passes and passes[0] >= D(2026, 10, 10, 19, 30), passes
            assert rc == 0 and len(passes) == 2 and last == ("완료", W.plan_after_pass(False, 0, 0, 0, 1)[1]), \
                (rc, passes, last)                                              # 3건 받음 → 다음 바퀴 0건 = 다 받음 → 종료
        finally:
            os.chdir(old_cwd)
    ok("회차=18:00~다음 날 17:55·①완료 전/지난 회차 기록=대기만 하다 17:55 종료·① 완료 후 받기·다 받으면 바로 종료")


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
    a, r = W.plan_after_pass(False, 0, 0, 0, 1, failed=fails)
    assert a == "done" and "실패 2계정" in r and "로그인 1" in r and "계정 1" in r and "확인 필요" in r, r
    a0, r0 = W.plan_after_pass(False, 0, 0, 0, 1)
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
        olds = (TD.datetime, TD.time.sleep, TD._one_pass, TD._pending_jobs, TD._wait_accounts, TD.LOG)
        args = SimpleNamespace(parent=0, until="", until_at=None, hidden=False, since=since)
        try:
            TD.datetime, TD.time.sleep = FakeDT, fake_sleep
            TD._one_pass = lambda a: (passes.append(clock["now"]), (False, 0))[1]
            TD._pending_jobs, TD._wait_accounts = (lambda: 0), (lambda lg: 0)
            TD.LOG = RLG.RunLog(TD.BASE, now=clock["now"], echo=lambda m: None)
            TD.LOG.heartbeat = lambda st, msg: None
            TD.cmd_watch(args)
        finally:
            TD.datetime, TD.time.sleep, TD._one_pass, TD._pending_jobs, TD._wait_accounts, TD.LOG = olds
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
        olds = (TD.datetime, TD.time.sleep, TD._one_pass, TD._pending_jobs, TD._wait_accounts, TD.LOG)
        args = SimpleNamespace(parent=0, until="", until_at=None, hidden=False, since="")
        try:
            TD.datetime, TD.time.sleep = FakeDT, fake_sleep
            TD._one_pass = lambda a: (passes.append(clock["now"]), (False, 0))[1]
            TD._pending_jobs, TD._wait_accounts = (lambda: 0), (lambda lg: 0)
            TD.LOG = RLG.RunLog(TD.BASE, now=clock["now"], echo=lambda m: None)
            TD.LOG.heartbeat = lambda st, msg: None
            TD.cmd_watch(args)
        finally:
            TD.datetime, TD.time.sleep, TD._one_pass, TD._pending_jobs, TD._wait_accounts, TD.LOG = olds
            stage.unlink(missing_ok=True)
        return passes

    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            (Path(tmp) / "output").mkdir()
            # 실측: 10-20 18:48 ① 완료 기준 '완료'(21:31) → ③ 끝(04:29)에 단계 기록이 done 으로 바뀜 → 08:00 옛 예약작업
            assert run(D(2026, 10, 21, 8, 0, 2), D(2026, 10, 21, 4, 29), "2026-10-20T18:48:17") == [], \
                "같은 회차 '완료'인데 단계 기록 시각이 바뀌었다고 다시 받음"
            # 지난 회차의 '완료'는 이번 회차를 막지 않음(다음 날 18:00 이후 ① 완료 → 받음)
            assert run(D(2026, 10, 21, 19, 0), D(2026, 10, 21, 18, 50), "2026-10-20T18:48:17"), "새 회차인데 안 받음"
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
    ok("오늘 뒤 줄만 예정 기록·같은 날 마지막 값·정산일 지나면 칸별 대조(며칠 전 예정)·실제 없음·요약·집계 시트"
       "·로켓그로스 정산대상 칸 저장(판매액+환불−수수료−할인)")


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
    ok("관리대장 값 우선·다르면 대장→파일 순서(최대 2)·대장에 없는 계정은 파일 값·값 노출 없음")


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
    print("[P37] 정산 계정 = 원장(셀독원장 관리중·관리중단 90일 이내 − 오입력 + 정산전용계정) · 동기화 오래되면 중단(D-103)")
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
    assert set(got) == {"keep1", "rec1", "own1"}, got                     # old1(중단 112일)·gone1(중단 173일) 제외
    assert got["keep1"] == ("대표-가게1", "pw1b") and got["own1"] == ("임-디프", "pwO"), got   # 원장 최신 비번·정산전용 값
    assert info["중복(셀독원장 우선)"] == ["keep1"] and info["정산전용"] == 1, info
    for last, why in (("2026-10-20 08:00:00", "오래됨"), ("", "기록 없음")):
        try:
            SA.accounts_from_registry(reg, settle, last, now)
        except SA.AccountSourceError:
            pass
        else:
            raise AssertionError(f"동기화 {why}인데 통과")
    ok("관리중·중단 90일 이내 포함·오래된 중단 제외·정산전용 관리중 포함·중복=원장 우선·최신 비번·동기화 오래됨/없음=중단")


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
    store: dict = {"reports": [], "campaigns": {"202606": [], "202607": [{"id": "105108858", "name": "07-12 보냉백 3종"},
                                                                         {"id": "1", "name": "b"}]}}

    def call(method, path, body):
        calls.append(body["query"].split("(")[0].split()[-1] if "query" in body else "?")
        q = body["query"]
        if "getDailySettlement" in q:                 # 실측(벅스 7월): 날짜×캠페인 청구가능 — 7/12 소진 30,150 → 일예산 초과 차감 30,000
            v = body["variables"]
            assert v["settlementDomain"] == "SELLER", v
            items = [{"date": 20260712, "campaignId": "105108858", "campaignName": "07-12 보냉백 3종", "deliveredAdcost": 30150,
                      "deliveredAdcostAfterCap": 30000, "billableAmount": 30000}] if v["startDate"] == 20260701 else []
            return {"data": {"getDailySettlement": {"summary": {"total": {"billableAmount": 30000 if items else 0}},
                                                    "items": items}}}
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
        assert got == [AD.MILK_EXCEL.format(y=2026, m=m) for m in (6, 7)], got                       # 밀크런 내역은 바로
        settle = json.loads((folder / "벅스-bux1004_광고정산_202607.json").read_text(encoding="utf-8"))
        assert settle["items"][0]["billableAmount"] == 30000 and settle["items"][0]["date"] == 20260712, settle
        assert json.loads((folder / "벅스-bux1004_광고정산_202606.json").read_text(encoding="utf-8"))["items"] == []
        assert (folder / "벅스-bux1004_밀크런_202606.xlsx").exists()
        assert s1["요청"] == ["202607"] and s1["캠페인 없음"] == ["202606"], s1
        st = json.loads((folder / "벅스-bux1004_광고.json").read_text(encoding="utf-8"))
        assert st["캠페인 없음"] == ["202606"]
        store["reports"] = [{**rep, "status": "inprogress"}]
        got.clear()
        calls.clear()
        s2 = AD.collect(call, get_bytes, folder, "벅스-bux1004", D("2026-06-10"), D("2026-08-05"))
        assert s2["기다림"] == ["202607"] and got == [] and "requestReport" not in str(calls), (s2, calls)   # 6월 다시 안 물음
        assert "DailySettlement" not in str(calls), calls                                          # 받은 정산내역 다시 안 받음
        store["reports"] = [rep]
        s3 = AD.collect(call, get_bytes, folder, "벅스-bux1004", D("2026-06-10"), D("2026-08-06"))
        assert s3["받음"] == ["202607"] and got == [AD.PA_EXCEL.format(id="14900611")], (s3, got)
        assert (folder / "벅스-bux1004_매출성장광고_202607.xlsx").exists()
        got.clear()
        calls.clear()
        s4 = AD.collect(call, get_bytes, folder, "벅스-bux1004", D("2026-06-10"), D("2026-08-07"))
        assert calls == [] and got == [] and not s4["받을 것"], (calls, got, s4)                     # 다 받았으면 광고센터 안 엶
    ok("끝난 달+3일·광고비·밀크런 내역 엑셀 바로·캠페인 전부로 보고서 요청·진행 중=기다림·완료=받기·캠페인 없는 달 기록·다 받으면 호출 없음")


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
    print("정산 런타임 오프라인 검증 통과")


if __name__ == "__main__":
    main()
