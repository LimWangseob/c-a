"""위탁정산서 계산 규칙 시험(오프라인) — T-25 이관 전 git 밖 시험 3종(test_managed_alloc·test_settlement_ledger·test_additional_pay)을
본문 그대로 옮김. 기대값 = 각 결정(D-116·D-161·D-185·D-186)의 설계 예시·실측 값(코드에서 뽑지 않음).

    python tools/verify_settlement_statements_offline.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coupang_analytics import settlement_additional_pay as AP  # noqa: E402
from coupang_analytics import settlement_ledger as SL  # noqa: E402
from coupang_analytics import settlement_managed_alloc as MA  # noqa: E402


# ── test_managed_alloc.py — managed_alloc 시험 — D-116 ② 배분 기준에서 도출(실측 값은 벅스 2026-10-26). ──
MV = {"95425233537", "95501572184", "95501565002"}           # 관리 옵션(벅스 J0058·보냉백)


def ismv(v):
    return v in MV


def test_managed_alloc() -> None:
    # 배송비: 같은 주문 상품 → 그 상품 · 상품 없음 → 반품 상품(실측 16102026647963 = J0058) · 반품 자료 없음 = 확인 필요
    order_pids = {"1": {"P1"}, "2": {"P2"}, "3": {"P1", "P2"}}
    ret = {"16102026647963": [{"items": [{"vendorItemId": 95425233537}]}], "9": []}
    s = MA.ship_split([("1", 3000, 2910), ("2", 3000, 2910), ("3", 3000, 2910), ("16102026647963", 6000, 5820),
                       ("8", 7000, 6790), ("9", 6000, 5820)], order_pids, {"P1"}, ret, ismv)
    assert s["관리"] == [3000 + 1500 + 6000, 2910 + 1455 + 5820] and s["확인 필요"] == [13000, 12610], s
    assert s["근거"] == {"같은 주문 상품": 3, "반품 조회 상품": 1, "반품 자료 없음": 1, "반품 기록 없음": 1}
    # 판매자서비스이용료(D-161) — 소유자 확정 예시: 구매확정 달 기준·끝난 달만·일반/가전 따로·구분 모름 = 일반
    c = MA.svc_charges({"2026-08": (1000000, 0, 0), "2026-09": (999999, 0, 0), "2026-10": (900000, 4000000, 0),
                        "2026-11": (5000000, 0, 0), "2026-07": (0, 5000000, 0), "2026-06": (900000, 0, 200000)}, "2026-10")
    assert c == {"2026-06": 55000, "2026-07": 55000, "2026-08": 55000}, c
    assert MA.svc_charges({"2026-01": (0, 2670900, 0)}, "2026-02") == {}   # 실측 hk66597582 가전 267만 = 공제 없음
    # 부과 순서로 채움 · 판매 없는 달에 부과돼도 그 구매확정 달 판매로 나눔 · 안 빠진 잔액 = 예정금 차감
    sales = {"2026-08": (400000, 2000000), "2026-09": (1100000, 1100000)}
    c = {"2026-08": 55000, "2026-09": 55000}
    r = MA.svc_settle(c, 55000, sales)
    assert (round(r["공제 관리"]), r["잔액 전체"], round(r["잔액 관리"]), r["규칙 밖"]) == (11000, 55000, 55000, 0), r
    r = MA.svc_settle(c, 165000, sales)                                 # 부과보다 더 빠짐 = 규칙 밖(호출부가 줄 비율로 나눔)
    assert (round(r["공제 관리"]), r["잔액 전체"], r["규칙 밖"]) == (66000, 0, 55000), r
    # 상품 자료 없는 공제(D-162): 공제를 받은 줄의 판매 기간 관리 정산금 비율 · 관리 시작 전 줄 제외
    ln = [("윙", "2026-05", {"물류": 100}), ("윙", "2026-06", {"물류": 30}), ("로켓그로스", "2026-07", {"물류": 70, "광고": 10})]
    rt = {("윙", "2026-06"): .5, ("로켓그로스", "2026-07"): .2}
    assert abs(MA.line_share(ln, "물류", "2026-06", lambda ch, ym: rt[ch, ym]) - .29) < 1e-9
    assert MA.line_share(ln, "없음", "2026-06", lambda ch, ym: rt[ch, ym]) == 0
    # 광고(D-119): 날짜×캠페인 청구가능 × 그날 보고서 옵션 광고비 비율 — 벅스 7월 실측(정산내역·보고서 일별 옵션 광고비)
    bill = {20260712: 30000, 20260713: 30000, 20260714: 50000, 20260715: 50000, 20260716: 46128, 20260717: 51321,
            20260718: 50327, 20260719: 51390, 20260720: 19022}
    pa = {20260712: (4809, 15026, 10317), 20260713: (1810, 19346, 8924), 20260714: (4149, 38439, 7942),
          20260715: (5342, 33005, 11662), 20260716: (1161, 33342, 11629), 20260717: (1439, 31422, 18466),
          20260718: (3386, 42410, 4540), 20260719: (3471, 47158, 767), 20260720: (893, 17811, 320)}
    opts = (95501565002, 95501572184, 95501576583)
    rows = [(d, 105108858.0, float(o), c) for d, cs in pa.items() for o, c in zip(opts, cs)]
    bills = {(d, "105108858"): b for d, b in bill.items()}
    m, t, note = MA.ad_share(rows, {**bills, (20260721, "1"): 100}, ismv) or (0, 0, "")   # 관리 = 565002·572184
    assert t == 378188 + 100 and round(m) == 378188 - 74402 and "20260721" in note, (m, t, note)   # 576583 몫 74,402(날짜별)
    assert MA.ad_share(rows, {}, ismv) is None                          # 청구 자료 없음 = 호출부가 확인 필요로
    # 캠페인 없는 조정(광고 프로모션 할인 등, campaignId 없음) = 그 달 캠페인 청구 관리 비율로 나눔(2026-11-02 output(29) 실측)
    r2 = [(20260601, 1.0, 95501572184.0, 100), (20260602, 2.0, 1.0, 100)]
    m, t, _ = MA.ad_share(r2, {(20260601, "1"): 100, (20260602, "2"): 100, (20260630, ""): -20}, ismv)
    assert (round(m, 6), t) == (90, 180), (m, t)
    m, t, note = MA.ad_share(r2, {(20260701, ""): -5}, ismv)            # 그 달 캠페인 청구 없음 = 메모(관리 몫 0)
    assert (m, t) == (0, -5) and "20260701" in note, (m, t, note)
    # 보고서를 아직 못 받은 달(파일 없음) = 관리 몫 0 이 아니라 비율 계산에서 뺌(2026-11-02 output(29): 6~7월 보고서 미수집)
    m, t, note = MA.ad_share(r2, {(20260601, "1"): 100, (20260602, "2"): 100, (20260705, "1"): 999, (20260731, ""): -9},
                             ismv, have={"202606"})
    assert (round(m, 6), t) == (100, 200) and "202607" in note, (m, t, note)
    assert MA.ad_share(r2, {(20260705, "1"): 999}, ismv, have={"202606"})[1] == 0       # 전부 미수집 = 호출부가 확인 필요로
    # 관리 몫(D-146): 상품별 자료 금액 그대로 · 자료 없는 공제 = 금액 없이(비율로 나누지 않고 '확인 필요'로 돌려줌) · 자료가 공제보다 많으면 공제액까지만
    assert MA.scoped(2139539, 3048006, 3040613) == (2139539, 7393)      # 벅스 물류비 — 자료 없는 7,393 은 관리 몫에 넣지 않음
    assert MA.scoped(0, 1000, 0) == (0, 1000)                           # 자료 없음 = 관리 몫 없음·전부 확인 필요
    assert MA.scoped(70, 50, 100) == (35, 0)                            # 리포트 100 중 공제된 50 까지만
    assert MA.scoped(70, 0, 100) == (0, 0)
    assert MA.scoped(-20, -120, -100) == (-20, -20)                     # 보상(빼는 돈이 음수)도 같은 규칙
    # 관리 시작 뒤 공제(D-154) = 판매 기간 시작 달 기준 — 시작 전 판매분은 시작 뒤에 지급돼도 뺌(벅스 2026-06 시작 · 5월 판매 6월 지급)
    lines = [("2026-05", {"물류": 100}), ("2026-06", {"물류": 30, "광고": 5}), ("2026-07", {"물류": 20})]
    assert MA.due_since(lines, "물류", "2026-06") == 50
    assert MA.due_since(lines, "광고", "2026-07") == 0
    # 밀크런: 밀크런번호(11322007)마다 적치 수량 비율 · 취소 입고 제외 · 입고 없는 밀크런 메모
    ib = [{"milkrunSeq": "11322007", "skus": [{"vendorItemId": 95501572184, "stowedQty": 124},
                                             {"vendorItemId": 1, "stowedQty": 0, "requestedQty": 124}]},
          {"milkrunSeq": "11322007", "cancelled": True, "skus": [{"vendorItemId": 1, "stowedQty": 999}]}]
    m, t, note = MA.milk_share([("11322007", 31350), ("777", 1000)], ib, ismv) or (0, 0, "")
    assert (m, t) == (31350 / 2, 32350) and "777" in note
    assert MA.milk_share([], ib, ismv) is None
    # 환급: 주문 → 상품 / 추가지급: 옵션 → 관리
    assert MA.order_share([("1", 100), ("3", 10), ("x", 5)], order_pids, {"P1"})[:2] == (105, 115)
    assert MA.vid_share([(95425233537, 3000), (5, 1000)], ismv)[:2] == (3000, 4000)
    # 관리 시작 달(D-185 · 소유자 2026-11-09): 자동·계약 중 이른 달 · 계약 전 판매 뺌 · 다르거나 계약 없음 = 확인 필요
    st, note = MA.contract_start("2026-02", "2026-08-05", True)         # 휴라엘: 자동이 빠름 → 계약 전 판매가 빠져 계약 달부터
    assert st == "2026-08" and "계약 전 판매 제외" in note and "확인 필요" in note, (st, note)
    st, note = MA.contract_start("2026-07", "2026-05-18", True)         # 케이씨메뉴팩처: 계약이 이름 → 계약 달
    assert st == "2026-05" and "확인 필요" in note and "계약 전 판매" not in note, (st, note)
    assert MA.contract_start("2026-04", "2026-04-09", True) == ("2026-04", "")      # 같은 달 = 표시 없음
    st, note = MA.contract_start("2026-04", None, True)                 # 맞는 계약 없음 → 자동 그대로 + 확인 필요
    assert st == "2026-04" and "계약 못 찾음" in note and "확인 필요" in note, (st, note)
    st, note = MA.contract_start("2026-04", None, False)                # 대조 표에 없는 계정 = 자동 + 확인 필요(조용히 넘어가지 않음)
    assert st == "2026-04" and "표에 없음" in note, (st, note)
    assert MA.contract_start("", "2026-10-13", True) == ("", "")        # 관리 상품 활동 없음 = 시작 달 없음
    assert MA.pre_contract("2026-07", "2026-08-05") and not MA.pre_contract("2026-08", "2026-08-05")
    assert not MA.pre_contract("2025-11", None)
    # 판매 0인 달(계약 달 ~ 관리 첫 판매 전) — 상품 자료 없는 공제는 첫 판매 달부터의 나눌 금액·평균으로만(그 달 관리 비율 0 = 몫 0)
    # 첫 판매 뒤: 공제 200 · 상품 자료 150(관리 60) · 비율 0.5 → 60 + 50 × 0.5 = 85 — 판매 0인 달 공제가 얼마든 같은 값
    assert MA.gap_free(60, 60, 150, 200, 0.5) == (85, 50)
    assert MA.gap_free(70, 60, 150, 200, 0.5) == (95, 50)          # 판매 0인 달 상품별 관리 금액 10 = 그대로 더함
    assert MA.gap_free(60, 60, 300, 200, 0.5) == (40, 0)           # 자료 > 공제 = 공제액까지만(scoped 그대로)
    print("test_managed_alloc OK")


# ── test_settlement_ledger.py — settlement_ledger 시험 — 기준일 스냅샷 로켓그로스 달 경계 겹침(12-01 줄 2벌·2026-10-26 실측) · 70:30 검산 · D-085 유지. ──
def rg(pay, s, e, ratio, payable, fin):
    return {"정산일": pay, "기간 시작": s, "기간 끝": e, "지급비율": ratio, "최종지급액": fin, "totalPayableAmount": payable}


def test_settlement_ledger() -> None:
    # 실측 니코에이블 모양: 10월·11월·12월 조회 이어 붙임 — 11월 조회 끝 경계에 12-01 줄이 한 벌 더
    oct_ = [rg("2026-10-01", "2026-08-03", "2026-08-09", 30, 246501, 229156)]
    nov = [rg("2026-11-06", "2026-10-05", "2026-10-11", 70, 646163, 71958),
           rg("2026-12-01", "2026-10-05", "2026-10-11", 30, 276920, 186587),
           rg("2026-11-20", "2026-10-19", "2026-10-25", 70, 155656, 53554),
           rg("2026-12-01", "2026-10-19", "2026-10-25", 30, 66692, 66692)]
    dec = [rg("2026-12-01", "2026-10-05", "2026-10-11", 30, 276920, 186587),
           rg("2026-12-01", "2026-10-19", "2026-10-25", 30, 90131, 90131)]        # 두 조회 사이 금액 바뀜(ljung0622)
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        (base / "쿠팡지급내역").mkdir()
        snaps = {"x1": {"로켓그로스": oct_ + nov + dec, "윙": [], "수집 끝": "2026-10-19T13:15:28"}}
        L = SL.Ledger(base, None, snaps, date(2026, 10, 19)).account("가-x1", {}, [], {}, {})
        assert round(L["buckets"]["최종 예정"]) == 71958 + 186587 + 53554 + 90131, L["buckets"]      # 12-01 줄 1벌만
        assert not L["e1_bad"], L["e1_bad"]
        # 70:30 검산 — 끝난 주 30% 줄이 2벌(2배)이면 E1 다름 · 진행 중 주(10-19~25)는 검산 안 함
        r30 = rg("2026-11-27", "2026-10-05", "2026-10-11", 30, 276920, 186587)        # 1일 아님 = 겹침 거르기 밖
        dup = SL.Ledger(base, None, {"x1": {"로켓그로스": [nov[0], r30, r30], "윙": []}}, date(2026, 10, 19))
        L = dup.account("가-x1", {}, [], {}, {})
        assert [x[1] for x in L["e1_bad"]] == ["2026-10-05~2026-10-11 30% 줄 ↔ 70% 줄×3/7"], L["e1_bad"]
        ok7 = SL.Ledger(base, None, {"x1": {"로켓그로스": nov[:2], "윙": []}}, date(2026, 10, 19)).account("가-x1", {}, [], {}, {})
        assert not ok7["e1_bad"], ok7["e1_bad"]                                              # 276,920 vs 276,927(차 7원) = 일치
    out = SL.rg_window_overlap(oct_ + nov + dec)
    assert len(out) == 5, len(out)
    assert sorted(r["최종지급액"] for r in out if r["정산일"] == "2026-12-01") == [90131, 186587], out   # 뒤(12월 조회) 1벌
    one = [rg("2026-12-01", "2026-10-05", "2026-10-11", 30, 1, 1)] * 3                # 홀수 벌 = 한 조회 안 여러 줄 → 그대로
    assert len(SL.rg_window_overlap(oct_ + one)) == 4
    first = [rg("2026-10-01", "2026-08-03", "2026-08-09", 30, 1, 1)] * 2              # 첫 달 1일 = 앞 조회 없음 → 그대로
    assert len(SL.rg_window_overlap(first)) == 2

    print("settlement_ledger 시험 통과")


def wg(pay, s, e, ratio, paid, ded, pending=0, target=None):
    return {"정산일": pay, "기간 시작": s, "기간 끝": e, "지급비율": ratio, "paidAmount": paid, "pendingAmount": pending,
            "totalDeductionAmount": ded, "targetAmount": paid / (ratio / 100) if target is None else target,
            "최종지급액": paid + pending - ded, "지급상태": "DONE"}


def test_d329_sale_2025_excluded() -> None:
    """D-328·D-329: 판매 기간(윙 구매확정일 · 로켓그로스 매출인식일)이 전부 2025년인 정산 줄 = 판매·공제·최종 통째 제외(정산일이 2026 이어도) ·
    2026 판매 줄 = 원문 공제 그대로. 줄 모양 = 실측(1단계 s4_①_줄.csv · hk66597582 윙 70% · oopean 보류 해제 2026-02-13 · RG 12월 말 주)."""
    w25 = wg("2026-01-06", "2025-12-08", "2025-12-14", 70, 2_099_065, 10_000)                       # 2026 지급 · 2025 판매
    w25old = wg("2025-12-22", "2025-12-01", "2025-12-07", 70, 500_000, 0)                          # 2025 지급 · 2025 판매
    rel25 = wg("2026-02-13", "2025-11-09", "2025-11-09", 100, 0, 0, pending=68_926, target=0)      # 보류 해제(2025 판매)
    w26 = wg("2026-01-13", "2026-01-05", "2026-01-11", 70, 700_000, 50_000)                        # 2026 판매 = 공제 그대로
    w25h = {**wg("2026-01-19", "2025-12-22", "2025-12-28", 70, 41_314, 0), "지급상태": "PENDING"}    # 보류(oopean 실측 모양)
    w26h = {**wg("2026-01-23", "2026-01-12", "2026-01-18", 70, 46_750, 0), "지급상태": "PENDING"}
    holds = [{"revenueRecognitionDateFrom": s, "revenueRecognitionDateTo": e, "paymentDate": p, "paymentStatus": "P",
              "finalPaymentAmount": f, "pendingReason": "시험"}
             for s, e, p, f in (("2025-12-22", "2025-12-28", "2026-01-19", 41_314), ("2026-01-12", "2026-01-18", "2026-01-23", 46_750))]
    rg25 = {**rg("2026-01-09", "2025-12-22", "2025-12-28", 70, 1_000_000, 600_000), "totalAdditionalDeductionAmount": 400_000}
    rg25old = {**rg("2025-12-12", "2025-11-03", "2025-11-09", 70, 300_000, 300_000)}
    rg26 = {**rg("2026-01-16", "2026-01-01", "2026-01-04", 70, 800_000, 700_000), "totalAdditionalDeductionAmount": 100_000}
    per = {("가-x1", "202512"): {"w_settle": 3_000_000}, ("가-x1", "202601"): {"w_settle": 1_000_000}}
    rgf = {("2025-11-03", "2025-11-09"): 300_000 / 0.7}                     # 2025 주 정산 파일(지금 keep 이 이 주 줄을 넣음)
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        (base / "쿠팡지급내역").mkdir()
        snaps = {"x1": {"윙": [w25, w25old, rel25, w26, w25h, w26h], "로켓그로스": [rg25, rg25old, rg26],
                        "pending": {"pendingReports": holds}}}
        L = SL.Ledger(base, None, snaps, date(2026, 3, 1)).account("가-x1", per, [], rgf, {})
    got = sorted((r[1], r[2], r[3]) for r in L["rows"])
    assert got == [("로켓그로스", "2026-01-16", "2026-01-01"), ("윙", "2026-01-13", "2026-01-05"),
                   ("윙", "2026-01-23", "2026-01-12")], got
    b = L["buckets"]
    assert round(b["최종 지급 완료"]) == 650_000 + 700_000 and round(b["공제"]) == 50_000 + 100_000, b    # 2026 줄 공제 원문 그대로
    assert not any(m < "2026" for _ch, m in L["gen"]) and round(b["줄 생성 전"]) == 1_000_000 - 746_750, L["gen"]   # 2025 달 없음
    assert not [x for x in L["e1"] if x[1] < "2026"], L["e1"]                                            # 2025 주·달 검산 없음
    assert L["e3"] == (46_750, 46_750) and L["ok"], (L["e3"], L["e1_bad"], L["e2_bad"])                 # 2025 판매 보류 = E3 밖
    print("test_d329_sale_2025_excluded OK")


def test_d328_product_rows_2025_excluded() -> None:
    """D-328(판매 시점 2025 = 정산일이 2026 이어도 위탁정산서 금액에 넣지 않음 · 판매 시점 = 윙 구매확정일 · RG 매출인식일 달):
    장부 줄(T-117)만이 아니라 정산집계 '상품별 월별'·윙 미정산 달·정산 파일 판매 줄·배송비 줄의 2025 판매 달도 계정 합계·관리 몫에서 뺀다.
    실측 근거: 11-15 정산집계(정산집계_재생성_R193) '상품별 월별' 2025-11·12 판매 1,159,473,158 · 정산 852,971,283 가 남아 있었음."""
    from types import SimpleNamespace

    from coupang_analytics import settlement_files as SF
    from coupang_analytics import settlement_statement_account as SA
    from coupang_analytics import settlement_statement_source as SRC
    h = ["계정", "월(매출인식)", "등록상품ID", "상품명", "윙 판매액", "로켓그로스 매출금액", "판매수수료(VAT포함)", "판매자할인쿠폰",
         "쿠팡 정산금액 합계(부가비용 차감 전)", "로켓그로스 물류비(VAT포함)", "재고 손실 보상", "물류비·보상 반영 후(광고비 등 계정 차감 전)",
         "윙 정산금액", "로켓그로스 정산대상액", "윙 수량", "로켓그로스 수량"]
    acct = "가-사업자-x1"
    rows = [[acct, "2025-12", "P1", "상품", 100_000, 0, 10_000, 0, 90_000, 0, 0, 90_000, 90_000, 0, 1, 0],
            [acct, "2026-01", "P1", "상품", 50_000, 0, 5_000, 0, 45_000, 0, 0, 45_000, 45_000, 0, 1, 0]]
    tot, per = SRC.confirmed({"상품별 월별": (h, rows)})
    assert (tot[acct]["sales"], tot[acct]["settle"]) == (50_000, 45_000), tot[acct]          # 계정 합계 = 2026 판매만
    assert (acct, "202512") not in per and per[(acct, "202601")]["w_settle"] == 45_000, dict(per)
    pur = {m: {"purchaseReports": [{"revenueAmount": s, "apAmount": ap}]} for m, s, ap in (("202512", 100_000, 90_000),
                                                                                             ("202601", 60_000, 54_000))}
    un = SRC._wing_unsettled(acct, pur, per, {}, "시험", "2026-02-10")
    assert [x[1] for x in un] == ["2026-01"] and un[0][3] == 54_000 - 45_000, un           # 2025 달 = 미정산(정산 예정) 밖
    ctx = SimpleNamespace(st={"data": {"상품별 월별": (h, rows)}}, unjudged={"x1": set()}, svc_judge={}, base=Path(tempfile.gettempdir()))
    a = SA.AccountBase(ctx, acct)
    a.mpids, a.opt2pid, a.cdate, a.files = {"P1"}, {}, None, []
    a._products()
    assert (a.tm["sales"], a.tm["settle"]) == (50_000, 45_000), a.tm                        # 관리 몫 = 2026 판매만
    assert not [k for k in a.mset if k[1] < "2026"] and not [k for k in a.msales if k[1] < "2026"], (dict(a.mset), dict(a.msales))
    assert a.prod[("P1", True)][2:4] == [50_000, 45_000], a.prod
    assert a.raw_s["2025-12"] == 100_000, a.raw_s            # 관리 시작 달 자동 판정(D-185) = 판매 이력이라 2025 도 그대로 봄

    def srow(order, pid, day, sales, settle):
        return SF.SettleRow("윙", acct, day, day, order, pid, "o1" if pid else "", "상품", "", 1 if pid else 0, sales, 0, 0, settle, day, "판매")
    f = SF.SettleFile("윙", acct, date(2025, 12, 1), date(2026, 1, 31), kind="주정산",
                      rows=[srow("A", "P1", date(2025, 12, 5), 100_000, 90_000), srow("A", "", date(2025, 12, 5), 3_000, 2_910),
                            srow("B", "P1", date(2026, 1, 5), 50_000, 45_000), srow("B", "", date(2026, 1, 5), 3_000, 2_910)])
    a.files = [f]
    a._ships()
    assert [round(x) for x in a.ship["관리"]] == [3_000, 2_910] and not round(a.ship["제외"][0]), a.ship   # 2025 배송비 = 관리·제외 모두 밖
    a._gross_and_ship()
    assert (a.gross, a.refund) == (50_000, 0), (a.gross, a.refund)                          # 판매액 = 2026 판매 줄만
    print("test_d328_product_rows_2025_excluded OK")


def test_d391_unknown_ship_same_month_wing_ratio() -> None:
    """D-391 ④(소유자 11-23 "로그인 비번 오류로 안됨, 다른 계정에서 도출된 산출식을 적용할것.") — 같은 주문 상품·반품 조회로도 상품을 못 찾은
    윙 배송비 줄 = 그 줄 달(구매확정 달)의 '같은 달 윙 상품 정산금 관리 비율'(ⓒ)로 나눔. 산식 근거 = 다른 계정 반품 조회 169줄을 정답으로 한
    백테스트 오차 합 최소(ⓒ 61,554 < 계정 관리 비율 ⓐ 174,442 < 확인 필요 ⓑ 208,872 · `output\\_검증_261117_정산끝난달\\결과_1_배송비.md` 3·6절 ·
    D-269 근거). 그 달 윙 상품 정산금이 없으면 관리 몫 0(백테스트와 같음). 기대값 = 손 계산(코드에서 뽑지 않음)."""
    from types import SimpleNamespace

    from coupang_analytics import settlement_files as SF
    from coupang_analytics import settlement_statement_account as SA
    h = ["계정", "월(매출인식)", "등록상품ID", "상품명", "윙 판매액", "로켓그로스 매출금액", "판매수수료(VAT포함)", "판매자할인쿠폰",
         "쿠팡 정산금액 합계(부가비용 차감 전)", "로켓그로스 물류비(VAT포함)", "재고 손실 보상", "물류비·보상 반영 후(광고비 등 계정 차감 전)",
         "윙 정산금액", "로켓그로스 정산대상액", "윙 수량", "로켓그로스 수량"]
    acct = "가-사업자-x2"
    rows = [[acct, "2026-02", "P1", "관리", 33_000, 0, 3_000, 0, 30_000, 0, 0, 30_000, 30_000, 0, 1, 0],
            [acct, "2026-02", "P2", "비관리", 77_000, 0, 7_000, 0, 70_000, 0, 0, 70_000, 70_000, 0, 1, 0],
            [acct, "2026-03", "P1", "관리", 0, 110_000, 10_000, 0, 100_000, 0, 0, 100_000, 0, 100_000, 0, 1],   # 로켓그로스만 = 윙 비율엔 안 듦
            [acct, "2026-03", "P2", "비관리", 55_000, 0, 5_000, 0, 50_000, 0, 0, 50_000, 50_000, 0, 1, 0]]
    ctx = SimpleNamespace(st={"data": {"상품별 월별": (h, rows)}}, unjudged={"x2": set()}, svc_judge={}, base=Path(tempfile.mkdtemp()))
    a = SA.AccountBase(ctx, acct)
    a.mpids, a.opt2pid, a.cdate = {"P1"}, {}, None

    def srow(order, pid, day, sales, settle):
        return SF.SettleRow("윙", acct, day, day, order, pid, "o1" if pid else "", "상품", "", 1 if pid else 0, sales, 0, 0, settle, day, "판매")
    a.files = [SF.SettleFile("윙", acct, date(2026, 2, 1), date(2026, 4, 30), kind="주정산",
                             rows=[srow("X", "", date(2026, 2, 10), 6_000, 5_802),       # 상품 줄·반품 자료 없음(검증자료 파일 없음)
                                   srow("Y", "", date(2026, 3, 10), 6_000, 5_802),
                                   srow("Z", "", date(2026, 4, 10), 6_000, 5_802)])]    # 그 달 윙 상품 정산 없음
    a._ships()
    assert a.ship["확인 필요"] == [18_000, 17_406] and a.ship["근거"]["반품 자료 없음"] == 3, a.ship
    a._products()
    a._gross_and_ship()
    # ⓒ 2026-02 = 30,000 / (30,000+70,000) = 0.3 · 2026-03 = 0 / 50,000 = 0 · 2026-04 = 윙 상품 정산 없음 → 0
    # (현행 ⓐ 계정 비율 = 130,000 / 250,000 = 0.52 → 17,406 × 0.52 = 9,051 — 이 값이면 실패)
    assert [round(x, 1) for x in a.ship_u] == [1_800.0, 1_740.6], a.ship_u
    assert round(a.tm["settle"], 1) == 130_000 + 1_740.6 and round(a.tx["settle"], 1) == 120_000 + 17_406 - 1_740.6, (a.tm, a.tx)
    assert round(a.tm["sales"]) == 33_000 + 110_000 + 1_800 and round(a.tx["sales"]) == 77_000 + 55_000 + 18_000 - 1_800, (a.tm, a.tx)
    print("test_d391_unknown_ship_same_month_wing_ratio OK")


# ── test_additional_pay.py — additional_pay 시험 — D-116 ③①: 없으면 '없음', 있으면 지급금액 + '확인 필요(첫 실제 자료로 칸 확정)'. ──
EMPTY = {"reports": [], "page": 1, "pageSize": 100, "totalPages": 0}      # 실측 응답(전 계정 0건)


def row(status, amount, kind="VENDOR_ITEM", order=1):
    return {"vendorId": "A01", "payDate": "2026-10-31", "orderId": order, "vendorItemId": 9, "requestStatusType": status,
            "finalRewardAmount": amount, "requestAmount": amount, "rewardType": kind}


def test_additional_pay() -> None:
    s = AP.summarize({"202609": EMPTY, "202610": EMPTY})
    assert (s["상태"], s["지급금액"], s["메모"]) == ("없음", 0, "추가지급 없음"), s
    s = AP.summarize({"202610": {**EMPTY, "reports": [row("PAID", 3000), row("REJECTED", 5000, order=2),
                                                      row("PAID", 1500, "DELIVERY_FEE", 3)], "totalPages": 1}})
    assert s["상태"] == "있음" and s["지급금액"] == 4500 and len(s["줄"]) == 3, s
    assert s["줄"][0]["주문번호"] == 1 and s["줄"][2]["지급항목"] == "DELIVERY_FEE"
    s = AP.summarize({"202610": {**EMPTY, "reports": [row("PAID", 10)], "totalPages": 2}, "202609": None})
    assert "202610 2쪽 중 1쪽만 수집" in s["메모"] and "202609 조회 실패" in s["메모"], s
    s = AP.summarize({"202609": None})
    assert s["상태"] == "자료 없음" and "조회 실패" in s["메모"], s
    assert AP.summarize(None)["상태"] == "자료 없음"
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        (base / "검증자료").mkdir()
        (base / "검증자료" / "x-a1.json").write_text(json.dumps({"additional": {"202609": EMPTY}}), encoding="utf-8")
        m = AP.months_of(base, "x-a1", {"additional": {"202610": {**EMPTY, "reports": [row("PAID", 7)]}}})
        assert m is not None and set(m) == {"202609", "202610"} and AP.summarize(m)["지급금액"] == 7
        assert AP.months_of(base, "x-none", None) is None
    print("test_additional_pay OK")


# ── T-25 이관으로 생긴 입구(설계: docs/plans/T25-step1-statements-migration-2026-11-12.md 3절) ──
def test_migration_inputs() -> None:
    from types import SimpleNamespace

    from coupang_analytics import settlement_statement_account as AC
    from coupang_analytics import settlement_statement_context as CTX
    with tempfile.TemporaryDirectory() as d:
        inp = Path(d)
        assert CTX.missing_inputs(inp) == list(CTX.REQUIRED)                 # 손 입력 6종 없으면 전부 이름으로 알림
        for n in CTX.REQUIRED:
            (inp / n).write_text("", encoding="utf-8")
        assert CTX.missing_inputs(inp) == []                                 # 계약 기간 보강(선택)은 없어도 됨
        snap = inp / "정산전용상품.json"                                      # 원장 '정산전용상품' 사본 = A 계정ID · C 등록상품ID · E 구분
        snap.write_text(json.dumps([["계정ID", "", "등록상품ID", "", "구분"], ["a1", "x", " 111 ", "", "관리"], ["a1", "", "222"],
                                    ["", "", "333", "", "관리"]]), encoding="utf-8")
        rows, err = CTX.settle_only_sheet(snap)
        assert (dict(rows), err) == ({"a1": {"111": "관리", "222": ""}}, ""), rows
    from coupang_analytics import settlement_statement_scope as SCOPE
    so = {"a1": {"111": "관리", "222": ""}}
    ctx = SimpleNamespace(ledger={"m1": {"5", "6"}}, listings={"m1": {"노출명"}}, rg={}, settle_only=so, settle_only_err="",
                          ranked={"a1": SCOPE.ranked(so["a1"], {})}, src_vids={})
    assert AC.scope(ctx, "m1") == ("관리대장 상품", {"5", "6"}, {"노출명"}, {})
    assert AC.scope(ctx, "a1")[0] == "판정 대기(원장 정산전용상품 구분 빈 칸 1줄)"
    assert AC.scope(ctx, "zz")[0] == "관리 상품 자료 없음"
    assert (AC.month_add("2026-01", -1), AC.month_add("2026-12", 1), AC.month_add("9999-99", -1)) == ("2025-12", "2027-01", "9999-99")


# ── 관리 상품 범위(소유자 2026-11-12 승인 규칙 ①~⑤ · 원문 "규칙안 5가지 승인, 기준일·달 단위도 제안대로 진행해") ──
# ① 대장 상품(지금 + 예전에 있다가 지운 상품 · 기간 자르지 않음 D-223 ②) ② 같은 상품명 다른 VID(D-107 · 같은 계정만)
# ③ 이력 없이 지워진 상품만 쿠팡 등록 로켓그로스 상품에서 되찾음(같은 상품의 판매자배송 VID 포함 · D-222)
# ④ 등록 '계약 달 이후'(달 단위) · 계약 없고 대장에만 있으면 원장 계정이력 첫 관리 시작 ⑤ 위탁자 본인 상품 제외 · 판정 못 함/자료 없음 = 확인 필요
def _inv(created: str, **types) -> dict:
    return {"created": created, "name": f"상품{created}", "types": {k[1:]: t for k, t in types.items()}}


def test_managed_scope() -> None:
    from types import SimpleNamespace

    from coupang_analytics import settlement_statement_account as AC
    from coupang_analytics import settlement_statement_scope as SCOPE
    # ① 대장 = 지금 결과 엑셀 + 날짜별 사본(지운 상품) — 파일 고르기 · 합치기
    with tempfile.TemporaryDirectory() as d:
        for n in ("쿠팡데이타분석_통계.xlsx", "쿠팡데이타분석_통계_261001.xlsx", "쿠팡데이타분석_통계_보관_261002_101010.xlsx",
                  "쿠팡데이타분석_진행중.xlsx", "~$쿠팡데이타분석_통계_261001.xlsx", "쿠팡데이타분석_통계_261001.json"):
            (Path(d) / n).write_text("", encoding="utf-8")
        assert [p.name for p in SCOPE.ledger_files(Path(d))] == [
            "쿠팡데이타분석_통계.xlsx", "쿠팡데이타분석_통계_261001.xlsx", "쿠팡데이타분석_통계_보관_261002_101010.xlsx"]
    ledger = SCOPE.merge_ledgers([{"a1": {11}, "e1": {"901"}, "f1": {"911"}, "c1": {"951"}, "d1": {"961"}},
                                  {"a1": {"21"}, "gone": {"31"}}])
    assert ledger["a1"] == {"11", "21"} and ledger["gone"] == {"31"}, ledger           # 지운 상품·계정째 빠진 계정도 대장 상품
    assert SCOPE.merge_ledgers([{"x": {"1|2 ", 3}}]) == {"x": {"1", "2", "3"}}          # 옛 결과 엑셀 'a|b' 한 칸 = 옵션 2개
    # ④ 원장 계정이력 → 첫 관리 시작(비밀번호 줄은 안 봄 · 계정아이디 변경은 이어짐 · 기록 시작일 최초등록 = 그 전부터 관리)
    head = ["번호", "실행번호", "일시", "효력일", "계정아이디", "사업자명", "변동유형", "항목", "이전값", "변경값"]
    rows = [head, ["1", "", "", "2026-09-20", "d1", "", "최초등록", "", "", ""],
            ["2", "", "", "2026-10-02", "c0", "", "신규계정", "", "", ""],
            ["3", "", "", "2026-10-05", "c1", "", "확인완료", "계정아이디", "c0", "c1"],
            ["4", "", "", "2026-09-25", "c1", "", "수정", "비밀번호", "x", "y"]]
    starts = SCOPE.first_starts(rows)
    assert starts == {"d1": ("2026-09-20", True), "c0": ("2026-10-02", False), "c1": ("2026-10-02", False)}, starts
    stores = ({"a1": {"2026-06-01": {"옵션": {"11": {"상품": "보냉백 A", "구분": "로켓그로스"},
                                               "13": {"상품": "보냉백  A", "구분": "윙"}}}},
               "b1": {"2026-06-01": {"옵션": {"91": {"상품": "보냉백 A", "구분": "윙"}}}}},
              {"a1": {"M:2026-06": {"옵션": {"101": {"상품": "재등록", "구분": "로켓그로스", "등록상품ID": "16280000000"},
                                             "111": {"상품": "옛", "구분": "로켓그로스", "등록상품ID": "16050000000"},
                                             "121": {"상품": "모름", "구분": "로켓그로스", "등록상품ID": "16150000000"},
                                             "131": {"상품": "윙만", "구분": "윙", "등록상품ID": "16290000000"}}}}})
    inv = {"a1": {"16000000001": _inv("2026-01-01", v11="RFM", v12="NORMAL"),          # 대장 상품(계약 전 등록이어도 대장 우선)
                  "16250000000": _inv("2026-07-01", v41="RFM", v42="NORMAL"),          # ③ 이력 없이 지운 RG — 판매자배송 VID 포함
                  "16251000000": _inv("2026-07-01", v51="NORMAL"),                     # 판매자배송 전용·대장과 무관 = 후보 아님
                  "16100000000": _inv("2026-04-30", v61="RFM"),                        # 계약 달 전 등록 = 제외
                  "16200000000": _inv("2026-05-13", v71="RFM", v72="NORMAL"),          # 진공포장기: 05-13 등록·계약 05-14 = 같은 달 = 포함
                  "16260000000": _inv("2026-08-01", v81="RFM"),                        # 위탁자 본인 상품 = 제외
                  "16270000000": _inv("2026-08-01", v91="RFM")},                       # 판정 없음 = 확인 필요
           "c1": {"16300000001": _inv("2026-09-15", v52="RFM"), "16400000001": _inv("2026-10-05", v53="RFM")},
           "d1": {"16255000002": _inv("2026-08-10", v62="RFM")},
           "f1": {"16255000003": _inv("2026-08-10", v63="RFM")}}
    judge = {"a1": {"16250000000": {"판정": "관리"}, "16200000000": {"판정": "관리"}, "16100000000": {"판정": "관리"},
                    "16260000000": {"판정": "본인상품", "근거": "위탁자 브랜드"}, "16280000000": {"판정": "관리"}},
             "c1": {"16400000001": {"판정": "관리"}, "16300000001": {"판정": "관리"}}}
    from coupang_analytics import sales_summary
    listings = sales_summary.managed_listings(stores, ledger)
    contracts = {"a1": "2026-05-14", "c1": None}
    rg = SCOPE.recover_all(ledger, listings, stores, inv, contracts, (starts, ""), judge, {})
    a1 = rg["a1"]
    assert a1["vids"] == {"41", "42", "71", "72", "101"}, a1["vids"]
    assert {p for p, _n, _w in a1["got"]} == {"16250000000", "16200000000", "16280000000"}, a1["got"]
    excl = {p: w for p, _n, w in a1["excl"]}
    assert set(excl) == {"16100000000", "16260000000", "16050000000"}, excl            # 계약 달 전(상품조회·ID 순서) · 본인 상품
    assert "계약 달 전 등록" in excl["16100000000"] and "위탁자 본인" in excl["16260000000"], excl
    check = {p: w for p, _n, w in a1["check"]}
    assert set(check) == {"16270000000", "16150000000"}, check                          # 판정 없음 · 등록일 모름(ID 사이)
    assert rg["c1"]["vids"] == {"53"} and {p for p, *_ in rg["c1"]["excl"]} == {"16300000001"}, rg["c1"]   # 대장 관리 시작 2026-10 기준
    assert [p for p, *_ in rg["d1"]["check"]] == ["16255000002"] and not rg["d1"]["vids"], rg["d1"]      # 기록 시작일 최초등록 = 확인 필요
    assert [w for *_x, w in rg["f1"]["check"]] == ["기준일 없음(계약 없음 · 원장 계정이력에 관리 시작 없음)"], rg["f1"]
    assert [w for *_x, w in rg["e1"]["check"]] == ["상품조회 자료 없음 — 이력 없이 지운 로켓그로스 상품을 되찾지 못함"], rg["e1"]
    ctx = SimpleNamespace(ledger=ledger, listings=listings, rg=rg, settle_only={}, settle_only_err="", files={}, contracts=contracts,
                          daily=stores[0], periods=stores[1], ranked={}, src_vids={}, cost_opts={}, inv=inv)
    sc, vids, names, marks = AC.scope(ctx, "a1")
    assert sc == "관리대장 상품 + 되찾은 로켓그로스 상품 3개(확인 필요 2개)" and vids == {"11", "21", "41", "42", "71", "72", "101"}, (sc, vids)
    assert names == {"보냉백 A"} and marks == {}, names
    acc = AC.AccountBase(ctx, "벅스-a1")
    acc._scope()
    assert acc.is_mv("13") and not acc.is_mv("51") and not acc.is_mv("91") and acc.scope_check == a1["check"]   # ② 같은 이름 윙 VID
    sc, vids, _n, _m = AC.scope(ctx, "gone")                                                # D-210: 계정째 대장에서 빠진 계정도 대장 상품
    assert (sc, vids) == ("관리대장 상품(확인 필요 1개)", {"31"}), (sc, vids)                 # 상품조회 없음 = 되찾기 확인 필요


# ── 정산 대상 상품 출처 순위(D-230 · D-231 · 소유자 2026-11-13) ──
# ① 관리대장(지금 + 사본 + 옛 PC 대장) ② 이력원장('상품이력' + '정산전용상품' 시트 · 모든 계정) ③ 계약서 품목(판매 방식 안 가림)
# ④ 쿠팡 등록 로켓그로스(되찾기 D-227) — 상품 단위로 위 순위에 없을 때만 아래 순위 · 아래 순위가 위를 빼지 않음.
# 옛 대장·이력원장·계약서 → 등록상품 = AI 판정표(관리상품_출처판정.json · 코드에 계정·상품 조건 없음 D-229).
def test_scope_priority() -> None:
    from types import SimpleNamespace

    from coupang_analytics import sales_summary
    from coupang_analytics import settlement_statement_account as AC
    from coupang_analytics import settlement_statement_context as CTX
    from coupang_analytics import settlement_statement_scope as SCOPE
    assert SCOPE.SOURCE in CTX.REQUIRED                                       # 출처판정 파일 없으면 시작 전 중단
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / SCOPE.SOURCE
        p.write_text(json.dumps({"계정": {"a1": {"1": {"출처": "카톡", "판정": "관리"}}}}, ensure_ascii=False), encoding="utf-8")
        try:
            SCOPE.load_sources(p)
            raise AssertionError("모르는 출처를 받아들임")
        except ValueError:
            pass
        p.write_text(json.dumps({"계정": {"a1": {"1": {"출처": "계약서", "판정": "아마도"}}}}, ensure_ascii=False), encoding="utf-8")
        try:
            SCOPE.load_sources(p)
            raise AssertionError("모르는 판정을 받아들임")
        except ValueError:
            pass
    ledger = {"a1": {"11"}}
    stores: tuple = ({"a1": {"2026-06-01": {"옵션": {"11": {"상품": "대장상품", "구분": "로켓그로스"}}}}}, {"a1": {}})
    inv = {"a1": {"16000000001": _inv("2026-06-01", v11="RFM"),                 # 대장 상품 — 정산전용상품 '본인상품'이어도 관리(①>②)
                  "16210000000": _inv("2026-03-01", v21="RFM"),                 # 옛 대장 — 계약 달 전 등록이어도 관리(①>④)
                  "16220000000": _inv("2026-07-01", v31="NORMAL"),              # 계약 품목 · 판매자배송 전용 = 관리(D-231 ③)
                  "16230000000": _inv("2026-07-01", v41="RFM"),                 # 이력원장 = 관리
                  "16240000000": _inv("2026-07-01", v51="RFM"),                 # 정산전용상품 '본인상품' — 4순위 판정 '관리'로 안 돌아옴
                  "16250000000": _inv("2026-07-01", v61="RFM"),                 # 출처판정 '확인 필요' = 금액 밖 · 표시
                  "16260000000": _inv("2026-07-01", v71="RFM"),                 # 정산전용상품 구분 빈 칸 = 확인 필요
                  "16270000000": _inv("2026-07-01", v81="RFM")}}                # 출처 없음 → 4순위 되찾기(지금 규칙)
    settle_only = {"a1": {"16000000001": "본인상품", "16240000000": "본인상품", "16260000000": "", "16230000000": "본인상품"},
                   "x1": {"18000000001": "관리"}}
    sources = {"a1": {"16210000000": {"출처": "옛 대장", "판정": "관리", "상품명": "물총", "근거": "옛 대장 10행"},
                      "16220000000": {"출처": "계약서", "판정": "관리", "상품명": "가방", "근거": "공급계약 품목"},
                      "16230000000": {"출처": "이력원장", "판정": "관리", "상품명": "샌들", "근거": "상품이력 관리중단 줄"},
                      "16250000000": {"출처": "계약서", "판정": "확인 필요", "상품명": "모름", "근거": "계약자 ↔ 계정 애매"}},
               "x1": {"17000000001": {"출처": "계약서", "판정": "관리", "상품명": "청소기", "근거": "계약 품목"}},
               "y1": {"19000000001": {"출처": "이력원장", "판정": "관리", "상품명": "칫솔", "근거": "상품이력"}}}
    ranked = {a: SCOPE.ranked(settle_only.get(a) or {}, sources.get(a) or {}) for a in set(settle_only) | set(sources)}
    assert ranked["a1"]["16230000000"][:2] == ("원장 정산전용상품", "본인상품"), ranked["a1"]   # 같은 2순위면 시트가 먼저
    assert ranked["a1"]["16210000000"][:2] == ("옛 대장", "관리") and ranked["a1"]["16260000000"][1] == "확인 필요", ranked["a1"]
    judge = {"a1": {"16240000000": {"판정": "관리"}, "16270000000": {"판정": "관리"}, "16210000000": {"판정": "제외"},
                    "16250000000": {"판정": "관리"}}}                                     # 출처 '확인 필요' = 정해지지 않음 → 4순위로 넘어감
    listings = sales_summary.managed_listings(stores, ledger)
    rg = SCOPE.recover_all(ledger, listings, stores, inv, {"a1": "2026-05-14"}, ({}, ""), judge, ranked)
    assert {p for p, *_ in rg["a1"]["got"]} == {"16270000000", "16250000000"}, rg["a1"]   # 1~3순위로 정한 상품만 4순위 후보 아님
    assert not rg["a1"]["excl"] and [p for p, *_ in rg["a1"]["check"]] == ["16260000000"], rg["a1"]   # 시트 빈 칸 → 4순위 판정 없음
    src_vids = {a: SCOPE.source_vids(rk, inv.get(a) or {}, SCOPE.sales_groups(stores[1].get(a) or {})) for a, rk in ranked.items()}
    assert src_vids["a1"] == {"21", "31"}, src_vids                                   # 1~3순위 '관리' 등록상품 → 그 상품의 VID 전부
    ctx = SimpleNamespace(ledger=ledger, listings=listings, rg=rg, settle_only=settle_only, settle_only_err="", ranked=ranked,
                          src_vids=src_vids, files={}, contracts={"a1": "2026-05-14"}, daily=stores[0], periods=stores[1], cost_opts={}, inv=inv)
    sc, vids, _names, marks = AC.scope(ctx, "a1")
    assert sc == "관리대장 상품 + 옛 대장 1개 + 계약서 1개 + 되찾은 로켓그로스 상품 2개(확인 필요 1개)", sc   # 0개 출처는 안 적음
    assert vids == {"11", "81", "61", "21", "31"}, vids
    keep = {p for p, k in marks.items() if k == "관리"}
    assert keep == {"16210000000", "16220000000"}, marks                             # 정산전용 '본인상품'이 이력원장보다 먼저
    acc = AC.AccountBase(ctx, "벅스-a1")
    acc._scope()
    acc.opt2pid = {"11": "16000000001", "21": "90000000021", "31": "90000000031", "41": "16230000000", "51": "16240000000",
                   "61": "16250000000", "71": "16260000000", "81": "16270000000"}   # 정산 파일 상품 ID ≠ 상품조회 등록상품ID 여도 VID 로 잡힘
    assert [acc.is_mv(v) for v in ("11", "21", "31", "41", "51", "61", "71", "81")] == \
        [True, True, True, False, False, True, False, True]                          # ①은 ②가 못 뺌 · ③ 판매자배송 포함
    assert [p for p, *_ in acc.scope_check] == ["16260000000"], acc.scope_check     # 4순위에서도 못 정한 것만 · 두 번 안 셈
    sc, _v, _n, marks = AC.scope(ctx, "x1")                                           # 대장 밖 계정 = 2·3순위
    assert sc == "원장 정산전용상품 + 계약서 1개" and marks == {"18000000001": "관리", "17000000001": "관리"}, (sc, marks)
    sc, _v, _n, marks = AC.scope(ctx, "y1")
    assert sc == "이력원장 1개" and marks == {"19000000001": "관리"}, (sc, marks)
    print("test_scope_priority OK")


# 출처 AI 판정(소유자 2026-11-13 "상품 판정은 AI가 최종 확정하고 그 이후부터는 프로그램이 처리") — 프로그램 = 후보·자료 모으기 + 답 검사만.
def test_scope_judge() -> None:
    import openpyxl

    from coupang_analytics import settlement_scope_judge as J
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "옛대장.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "(신)계정정보"
        ws.append(["7:3 셀독정보"])
        ws.append(["대표자명", "연락처", "사업자명", "계정명", "비밀번호", "상품명", "계약여부"])
        ws.append(["홍길동", "010-0000-0000", "가나상회", "ga1", "pw-secret!", "물총 TTGW02", "정상계약"])
        ws.append(["", "", "", "", "", "이어진 줄", ""])
        ws2 = wb.create_sheet("셀독관리")
        ws2.append(["대표자명", "계정명", "아이디", "상품", "계약일"])          # '계정명' = 상호 · '아이디' = 계정ID → 값으로 고름
        ws2.append(["홍길동", "가나상회", "ga1", "보냉백 YG0209", "2026-05-14"])
        wb.save(p)
        rows = J.old_ledger_rows([p], {"ga1"})
    got = rows["ga1"]
    assert [(r["시트"], r["행"], r["상품"]) for r in got] == [("(신)계정정보", 3, "물총 TTGW02"), ("셀독관리", 2, "보냉백 YG0209")], got
    blob = json.dumps(rows, ensure_ascii=False)
    assert "pw-secret" not in blob and "010-0000" not in blob, blob                      # 비밀번호·연락처 칸은 안 읽음
    hist = J.history_rows([["번호", "효력일", "계정아이디", "사업자명", "상품명", "변동유형", "비고"],
                           ["7", "2026-10-01", "ga1", "가나상회", "칫솔살균기 DP77", "관리중단", "x"], ["8", "", "", "", "", "", ""]])
    assert hist == {"ga1": [{"번호": "7", "효력일": "2026-10-01", "상품명": "칫솔살균기 DP77", "변동유형": "관리중단"}]}, hist
    pk = J.packet("ga1", ("가나상회", "홍길동"), [{"등록상품ID": "161", "상품명": "UZI 충전식 물총", "등록일": "", "판매방식": ["RFM"]},
                                                  {"등록상품ID": "162", "상품명": "칫솔 살균기", "등록일": "", "판매방식": ["NORMAL"]}],
                  got, hist["ga1"], [])
    good = {"계정ID": "ga1", "판정": [
        {"등록상품ID": "161", "상품명": "UZI 충전식 물총", "출처": "옛 대장", "판정": "관리", "근거": "옛대장 3행 모델 TTGW02", "원문": "물총 TTGW02"},
        {"등록상품ID": "162", "상품명": "칫솔 살균기", "출처": "이력원장", "판정": "확인 필요", "근거": "모델 없음", "원문": "칫솔살균기 DP77"}]}
    ok, errs = J.check_answer(pk, good)
    assert not errs and set(ok) == {"161", "162"} and ok["161"]["출처"] == "옛 대장", (ok, errs)
    bad = {"계정ID": "ga1", "판정": [
        {"등록상품ID": "999", "출처": "옛 대장", "판정": "관리", "근거": "x", "원문": "물총 TTGW02"},          # 판정대상 밖
        {"등록상품ID": "161", "출처": "카톡", "판정": "관리", "근거": "x", "원문": "물총 TTGW02"},             # 출처 모름
        {"등록상품ID": "162", "출처": "이력원장", "판정": "관리", "근거": "x", "원문": "칫솔살균기 DP99"}]}      # 원문 지어냄
    ok, errs = J.check_answer(pk, bad)
    assert not ok and len(errs) == 3 and "원문이 근거자료에 없음" in errs[2], errs
    assert J._norm("(주)가나 상회") == J._norm("㈜가나상회") == "가나상회"
    print("test_scope_judge OK")


# ── 판매 없이 비용만 있는 관리 상품(D-244 · 소유자 2026-11-15) — 근거 T-42 보고: dalbong1849 16258713629 보관비(옵션 = 대장 VID)·
# ljung0622 TTGW02 반출비(옵션 = 되찾은 VID)가 관리 상품ID 를 주문 줄 짝에서만 만들어 '관리 밖'으로 빠짐.
def test_cost_only_scope() -> None:
    from types import SimpleNamespace

    import openpyxl

    from coupang_analytics import settlement_files as SF
    from coupang_analytics import settlement_scope_judge as J
    from coupang_analytics import settlement_statement_account as AC
    from coupang_analytics import settlement_statement_source as SRC
    from coupang_analytics import settlement_stats as SS
    acct = "서달원-(DW)커머스-d1"
    lines = [SF.CostLine(acct, "2026-09", "16258713629", "95609464754", "아기수영장 HW016", "보관비", 5408, 540),
             SF.CostLine(acct, "2026-10", "", "95609464754", "", SF.COMPENSATION, 100),           # 보상 = 옵션만 → 같은 짝으로 상품
             SF.CostLine(acct, "2026-05", "16157622592", "95273555059", "전동물총 TTGW02", "반출비", 166800, 16680),
             SF.CostLine(acct, "2026-09", "16377117417", "95700000001", "빔프로젝터거치대 LN167", "보관비", 2200, 220),
             SF.CostLine(acct, "2026-09", "16400000000", "95700000002", "판정표 관리 상품", "보관비", 100, 10),
             SF.CostLine(acct, "2026-09", "16500000000", "95700000003", "상품조회에 있는 상품", "보관비", 100, 10),
             SF.CostLine(acct, "2026-09", SF.MULTI_PRODUCT, "", "", "반출 배송 서비스비", 1000, 100),
             # 옵션ID 없이 등록상품ID 만 있는 비용 줄(R191 시뮬레이션 B8 — seankim137 16377117417 반출 배송 서비스비 2,420원이 짝 없이 빠짐)
             SF.CostLine(acct, "2026-09", "16600000000", "", "반출비만 상품", "반출 배송 서비스비", 2200, 220),
             SF.CostLine(acct, "2026-10", "", "95700000009", "", SF.COMPENSATION, 300),            # 상품 못 찾은 보상(tellace83 13,474원 꼴)
             # 비용 줄도 있고 정산 파일 주문 줄(판매)도 있는 상품 — 상품조회·판매분석에는 없음(T-53 · R192 시뮬레이션 B8 ④-2 ski1121·Difpick 꼴)
             SF.CostLine(acct, "2026-09", "16700000000", "95700000010", "판매도 있는 상품", "보관비", 100, 10)]
    res = SS.aggregate([], lines)
    with tempfile.TemporaryDirectory() as d:
        p = SS.write_stats(Path(d) / "정산집계_new.xlsx", res)
        wb = openpyxl.load_workbook(p, read_only=True)
        assert SRC.COST_OPTIONS in wb.sheetnames, wb.sheetnames                        # ① 새 시트
        opts = SRC.cost_options(wb)
        wb.close()
        assert opts == {"d1": {"95609464754": ("16258713629", "아기수영장 HW016"), "95273555059": ("16157622592", "전동물총 TTGW02"),
                               "95700000001": ("16377117417", "빔프로젝터거치대 LN167"), "95700000002": ("16400000000", "판정표 관리 상품"),
                               "95700000003": ("16500000000", "상품조회에 있는 상품"),
                               SRC.no_option_key("16600000000"): ("16600000000", "반출비만 상품"),
                               "95700000009": ("옵션 95700000009", ""),
                               "95700000010": ("16700000000", "판매도 있는 상품")}}, opts   # 묶음 줄(여러 상품) 짝 없음
        empty = SS.write_stats(Path(d) / "정산집계_0.xlsx", SS.aggregate([], []))     # 비용 없어도 머리 줄만 있는 시트
        wb = openpyxl.load_workbook(empty, read_only=True)
        assert SRC.COST_OPTIONS in wb.sheetnames and SRC.cost_options(wb) == {}, wb.sheetnames
        wb.close()
        old = Path(d) / "정산집계_old.xlsx"                                             # ② 옛 집계(시트 없음) = 시작 전 중단
        wb = openpyxl.Workbook()
        wb.active.title = "상품별 월별"
        wb.save(old)
        try:
            SRC.read_stats(old)
            raise AssertionError("옛 정산집계를 받아들임")
        except FileNotFoundError as exc:                                               # 두 도구가 '❌ 시작 전 중단'으로 받는 종류
            assert isinstance(exc, SRC.StatsTooOld) and "정산집계를 다시 만드세요" in str(exc), exc
    # ③ 관리 VID 옵션의 등록상품 = 관리(판매 줄 짝 opt2pid 는 그대로)
    ledger = {"d1": {"95609464754", "95322412626"}}
    rg = {"d1": {"vids": {"95273555059"}, "got": [("16157622592", "전동물총", "되찾기")], "excl": [], "check": []}}
    files = {"d1": [SimpleNamespace(channel="로켓그로스", rows=[SimpleNamespace(option_id="95322412626", product_id="16142251017", product_name="관리 상품"),
                                          SimpleNamespace(option_id="95111", product_id="8758835645", product_name="판매만 상품"),
                                          # 판매 + 같은 달 취소(합 0 · 정산집계 '상품별 월별' 주문 칸은 0) — 그래도 주문 줄이 있는 상품(T-53)
                                          SimpleNamespace(option_id="95700000010", product_id="16700000000", product_name="비용+판매 상품"),
                                          SimpleNamespace(option_id="95700000010", product_id="16700000000", product_name="")])]}
    rk = {"16400000000": ("옛 대장", "관리", "옛 대장 3행", "판정표 관리 상품")}
    inv = {"d1": {"16142251017": _inv("2026-04-08", v95322412626="RFM"), "16500000000": _inv("2026-08-01", v95700000003="RFM")}}
    ctx = SimpleNamespace(ledger=ledger, listings={}, rg=rg, settle_only={}, settle_only_err="", files=files, contracts={},
                          daily={}, periods={}, ranked={"d1": rk}, src_vids={}, cost_opts=opts, inv=inv)
    acc = AC.AccountBase(ctx, acct)
    acc._scope()
    assert acc.opt2pid == {"95322412626": "16142251017", "95111": "8758835645", "95700000010": "16700000000"}, acc.opt2pid
    assert acc.mpids == {"16142251017", "16258713629", "16157622592", "16400000000"}, acc.mpids
    # ⑤ 판정 전(출처판정·되찾기에 없음 · 상품조회·판매분석에 없음) = '관리 상품 확인 필요'(금액 밖) — 16500000000 은 상품조회 경로
    chk = {p: (n, w) for p, n, w in acc.scope_check}
    assert set(chk) == {"16377117417", "16600000000", "옵션 95700000009"} and chk["16377117417"][0] == "빔프로젝터거치대 LN167", acc.scope_check
    assert chk["16600000000"][0] == "반출비만 상품", chk                          # 옵션ID 없는 비용 줄도 조용히 빠지지 않음
    assert "비용만" in chk["16377117417"][1] and "금액 밖" in chk["16377117417"][1], chk
    # ④ 출처 AI 판정 대상 = 상품조회 + 판매분석 + 비용만 있는 등록상품(관리 VID 옵션 상품은 뺌 · 정산 파일 주문 줄에 나온 상품은 뺌 =
    #    정산서 seen 의 opt2pid 값과 같은 기준 · T-53) — 16700000000 = 비용 줄 + 주문 줄 → '비용만' 아님
    assert "16700000000" not in chk, chk
    vids = ledger["d1"] | rg["d1"]["vids"]
    from coupang_analytics import settlement_statement_scope as SCOPE
    sold = SCOPE.sold_products(files["d1"])                                     # prepare 가 쓰는 판매 줄 상품 = 정산서 seen 의 판매 줄 몫
    assert set(sold) == set(acc.opt2pid.values()) == {"16142251017", "8758835645", "16700000000"}, sold
    tg = J.targets("d1", inv, {}, lambda v: v in vids, {}, opts["d1"], sold)
    got = {t["등록상품ID"]: t for t in tg}
    # 판매 줄은 있는데 상품조회·판매분석에 없는 상품도 판정 대상(관리 VID 옵션 상품 16142251017 은 뺌 · 소유자 2026-11-16 D-256)
    assert set(got) == {"16377117417", "16400000000", "16500000000", "16600000000", "옵션 95700000009", "8758835645", "16700000000"}, got
    assert got["16700000000"] == {"등록상품ID": "16700000000", "상품명": "비용+판매 상품", "노출명": [], "등록일": "",
                                  "판매방식": ["RFM"]}, got["16700000000"]
    assert got["16600000000"]["노출명"] == [] and got["16600000000"]["상품명"] == "반출비만 상품", got["16600000000"]
    assert got["16377117417"] == {"등록상품ID": "16377117417", "상품명": "빔프로젝터거치대 LN167", "노출명": [], "등록일": "",
                                  "판매방식": ["RFM"]}, got["16377117417"]
    print("test_cost_only_scope OK")


# ── 지급 줄 공제 분류 — 기대값 = 결정 원문 실측 값(D-312 · D-304 · D-305 · 코드에서 뽑지 않음) ──
def _wing(paid, why, pending=0, ratio=70, day="2026-08-24"):
    return {"채널": "윙", "정산일": day, "기간 시작": "2026-08-01", "기간 끝": "2026-08-07", "지급비율": ratio, "targetAmount": paid,
            "paidAmount": paid, "pendingAmount": pending, "차감 사유": [{"사유": k, "금액": v} for k, v in why],
            "totalDeductionAmount": sum(v for _, v in why), "최종지급액": paid + pending - sum(v for _, v in why)}


def test_d312_fast_used() -> None:
    """D-312 ①: 윙 '빠른정산 사용액' = 이미 당겨 받은 돈(±0) = 빠른정산 계좌인출액과 같은 항목(FAST) — 공제 항목으로 따로 두지 않음.
    실측 seankim137 2026-08-24 줄: 사용액 491,416 + 인출 254,512 + 광고 424,164 = 지급가능 1,170,092 · 최종 0."""
    from coupang_analytics import settlement_statement_account as SA
    r = _wing(1170092, [("빠른정산 사용액", 491416), ("빠른정산 계좌인출액", 254512), ("상품광고비", 424164)])
    pay, rel, parts = SA.deductions(r)
    assert "빠른정산 사용액" not in parts, parts
    assert parts == {"빠른정산 계좌인출액": 491416 + 254512, "광고비": 424164}, parts
    assert round(pay + rel - sum(parts.values())) == 0
    print("test_d312_fast_used OK")


OWN_LOAN, OWN_MCA, OWN_CARD = "위탁자 본인 차감 — 성장 대출", "위탁자 본인 차감 — MCA 상환", "위탁자 본인 차감 — 체크카드 대금"


def _rg_line(**kw):
    base = dict.fromkeys(("totalAdSalesDeductionAmount", "totalMilkRunDeductionAmount", "totalArFactoringDeductionAmount",
                          "totalMerchantCashAdvanceDeductionAmount", "totalDebitCardDeductionAmount", "totalSalesAdjustment",
                          "totalFinalCfsFeeDeductionAmount", "totalCfsInventoryCompensationAmount"), 0)
    return {"채널": "로켓그로스", **base, **kw}


def test_d312_own_deduction() -> None:
    """D-312 ②: 26 성장 대출(윙 사유) · 80 MCA 상환 · 81 체크카드(RG 칸) = 정산금액에서 차감(쿠팡 실지급과 같음) · '위탁자 본인 차감'
    줄(D-305 따로 줄 · 기타 공제에 섞지 않음) · 관리 몫 0. 실측 tellace83 26 798,784 · 80 8,121,756 · seankim137 81 82,870."""
    from collections import Counter
    from types import SimpleNamespace
    from coupang_analytics import settlement_statement_account as SA
    from coupang_analytics.settlement_statement_deduct import Account
    pay, rel, parts = SA.deductions(_wing(798784, [("쿠팡 판매자 성장 대출", 798784)]))
    assert parts == {OWN_LOAN: 798784}, parts
    add = 8121756 + 82870 + 5000                                     # 추가공제 = MCA + 체크카드 + 그 밖 5,000
    pay, rel, parts = SA.deductions(_rg_line(totalPayableAmount=10_000_000, totalMerchantCashAdvanceDeductionAmount=8121756,
                                             totalDebitCardDeductionAmount=82870, totalAdditionalDeductionAmount=add))
    assert (parts[OWN_MCA], parts[OWN_CARD], parts["기타 공제"]) == (8121756, 82870, 5000), parts
    assert round(pay - sum(parts.values())) == 10_000_000 - add      # 계정 지급액 = 쿠팡 실지급 그대로
    # 관리 몫: 위탁자 본인 차감 = 0 · 다른 공제는 그대로(기타 공제 관리 비율 0.5 → 2,500)
    a = Account.__new__(Account)
    a.D = Counter({OWN_LOAN: 798784, OWN_MCA: 8121756, OWN_CARD: 82870, "기타 공제": 5000})
    a.share, a.rates = {"기타 공제": (0.5, "시험", "쿠팡 자료")}, {"기타 공제": ("", 0.5)}
    a.sv, a.start, a.active, a.line_info = {"잔액 관리": 0}, "2025-01", False, []
    a.L, a.mset, a.S, a.settle_m = {"gen": {}}, {}, 0.0, 100_000.0
    a.ctx = SimpleNamespace()
    a._rest_and_status()
    assert all(a.share[k][0] == 0 and a.share[k][2] == "위탁자 본인 차감" for k in (OWN_LOAN, OWN_MCA, OWN_CARD)), a.share
    assert {k: round(x) for k, x in a.Dm.items() if round(x)} == {"기타 공제": 2500}, a.Dm
    assert round(a.pay_m) == 97_500, a.pay_m
    print("test_d312_own_deduction OK")


def test_t125_forecast_keeps_own_cols() -> None:
    """T-125 A2(80·81 · D-305 · D-312 ②): 정산 예정 기록에 MCA·체크카드 칸이 남아야 예정 줄도 '위탁자 본인 차감'(관리 몫 0)·D-305 감지.
    칸 이름 = 쿠팡 원문(output38 `정산현황_원문\\…tellace83\\2026-11-16.json.gz` 51줄 · 예정 MCA 263,040 · 추가공제 1,006,565 ·
    seankim137 2026-09-14 70% 줄 체크카드 6,500 · `debitCardOffsetYearMonthBreakdown` {'2026-08': 6500}). 옛 기록(칸 없음) = 지금 처리 그대로."""
    from datetime import date
    from coupang_analytics import settlement_forecast as FC
    from coupang_analytics import settlement_statement_account as SA
    own = ("totalMerchantCashAdvanceDeductionAmount", "totalDebitCardDeductionAmount", "debitCardOffsetYearMonthBreakdown")
    add = 1_006_565 + 6_500
    raw = {**_rg_line(totalPayableAmount=3_000_000, totalAdditionalDeductionAmount=add, totalMerchantCashAdvanceDeductionAmount=263_040,
                      totalDebitCardDeductionAmount=6_500),
           "debitCardOffsetYearMonthBreakdown": {"2026-11": 6_500},
           "정산일": "2026-11-24", "기간 시작": "2026-11-10", "기간 끝": "2026-11-16", "지급비율": 70, "최종지급액": 3_000_000 - add, "지급상태": "예정"}
    raw.pop("채널")
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / FC.FORECAST_FILE
        FC.record(f, "x-y-tellace83", "로켓그로스", [raw], date(2026, 11, 16))
        got = FC.load(f)
    assert len(got) == 1 and all(k in got[0] for k in own), sorted(got[0])
    r = {**got[0], "채널": "로켓그로스"}
    _pay, _rel, parts = SA.deductions(r, False)
    assert (parts[OWN_MCA], parts[OWN_CARD], parts["기타 공제"]) == (263_040, 6_500, add - 263_040 - 6_500), parts
    assert dict(SA.watched(r)) == {"MCA 상환": 263_040, "체크카드 대금": 6_500}, SA.watched(r)
    assert r["debitCardOffsetYearMonthBreakdown"] == {"2026-11": 6_500}             # 새 정산서 체크카드 = 달 칸(cost.py OWN_BR)
    old = {k: v for k, v in r.items() if k not in own}                              # 옛 기록 = 칸 없음 → 기타 공제(지금 처리 그대로)
    _pay, _rel, parts = SA.deductions(old, False)
    assert (parts[OWN_MCA], parts[OWN_CARD], parts["기타 공제"]) == (0, 0, add), parts
    print("test_t125_forecast_keeps_own_cols OK")


class _Led:
    """장부 가짜(지급 줄만) — 윙·로켓그로스 원본 줄 → Ledger.account 의 rows 모양."""

    def __init__(self, wing, rg=()):
        self.w, self.r = list(wing), list(rg)

    def wing_rows(self, aid):
        return self.w

    def rg_rows(self, aid):
        return self.r

    def account(self, acct, per, un, rgf, aps):
        rows = [[acct, ch, *SL._key(r), r.get("상태", "지급 완료"), 0, 0, r["최종지급액"]]
                for ch, rs in (("윙", self.w), ("로켓그로스", self.r)) for r in rs]
        return {"rows": rows, "buckets": {"줄 생성 전": 0}, "e1_bad": [], "e2_bad": [], "e3": (0, 0)}


def _acct(wing, rg=(), judge=None):
    from types import SimpleNamespace
    from coupang_analytics.settlement_statement_deduct import Account
    ctx = SimpleNamespace(led=_Led(wing, rg), per={}, un={"가-x1": []}, rgf={}, aps={"가-x1": {}}, tot={"가-x1": {"settle": 0}},
                          own_judge=judge or {})
    a = Account(ctx, "가-x1")
    a._payouts()
    return a


def test_d304_wing_negative_round() -> None:
    """D-304: 윙 회차 최종액(paid − 공제)이 음수면 그 음수만큼 '3PM_매출채권'에 되돌려 넣고(공제 −), 뒤 회차 3PM 회수 줄 = 같은 항목
    공제 → 짝이면 합 0 · 정산금액 = Σmax(회차 최종액, 0) = 쿠팡 실지급(이중 차감 없음). 실측 guarisen2024 이중 차감 52,343."""
    from coupang_analytics import settlement_statement_account as SA
    neg = _wing(1_001_000, [("상품광고비", 1_053_343)], day="2026-08-24")
    back = {**_wing(500_000, [("3PM_매출채권", 52_343)], day="2026-08-31"), "기간 시작": "2026-08-08", "기간 끝": "2026-08-14"}
    pay, rel, parts = SA.deductions(neg)
    assert (round(parts["3PM_매출채권"]), round(parts["광고비"])) == (-52_343, 1_053_343), parts
    assert round(pay + rel - sum(parts.values())) == 0
    assert round(SA.deductions(back)[2]["3PM_매출채권"]) == 52_343
    a = _acct([neg, back])
    assert a.bad == 0, a.bad
    assert round(a.D["3PM_매출채권"]) == 0 and round(a.D["광고비"]) == 1_053_343, a.D
    assert sorted(round(x[8]) for x in a.rows_out) == [0, 447_657], a.rows_out          # 음수 회차 = 0 지급
    assert round(a.fin["지급 완료"]) == 447_657 == round(a.paid_total), a.fin              # = 쿠팡 실지급(0 + 447,657)
    print("test_d304_wing_negative_round OK")


def test_d319_scheduled_negative_kept() -> None:
    """D-319: D-304 되돌림은 '지급 완료' 회차만 — 예정(지급 전) 윙 음수 회차는 음수 그대로(뒤 회차 3PM 회수 공제가 아직 자료에 없어
    0 으로 두면 예정 합이 부풂 · 실측 oopean 예정 +1,813,986)."""
    from coupang_analytics import settlement_statement_account as SA
    neg = {**_wing(1_001_000, [("상품광고비", 1_053_343)]), "상태": "예정"}
    pay, rel, parts = SA.deductions(neg, done=False)
    assert round(parts["3PM_매출채권"]) == 0 and round(pay + rel - sum(parts.values())) == -52_343, parts
    a = _acct([neg])
    assert a.bad == 0, a.bad
    assert round(a.D["3PM_매출채권"]) == 0 and [round(x[8]) for x in a.rows_out] == [-52_343], a.rows_out
    assert round(a.fin["예정"]) == -52_343, a.fin
    print("test_d319_scheduled_negative_kept OK")


def _wing_one_day(pay_day, day, fin, pending=0):
    return {"정산일": pay_day, "기간 시작": day, "기간 끝": day, "지급비율": 100, "최종지급액": fin, "지급상태": "DONE", "차감 사유": [],
            "targetAmount": 0, "paidAmount": 0, "pendingAmount": pending, "totalDeductionAmount": 0}


def test_d308_additional_round() -> None:
    """D-308 ①(T-105): 윙 추가지급 줄(정산대상·paid·pending 0 · 기간 = 정산일 하루) = 보류 해제(pending > 0)와 따로 분류 · 검산 =
    같은 날 추가지급 메뉴 PAID finalRewardAmount(짝 없으면 E2 다름). 실측 roum0502 2026-10-22 16,897 · freewin7777 11-13 117,960."""
    add = _wing_one_day("2026-10-22", "2026-10-22", 16_897)
    rel = _wing_one_day("2026-10-20", "2026-08-16", 277_218, pending=277_218)
    assert SL.additional(add) and not SL.release(add), "추가지급 줄 = 보류 해제 아님"
    assert SL.release(rel) and not SL.additional(rel), "보류 해제 줄 = 추가지급 아님"
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        (base / "쿠팡지급내역").mkdir()
        snaps = {"x1": {"윙": [add, rel], "로켓그로스": []}}
        led = SL.Ledger(base, None, snaps, date(2026, 11, 15))
        L = led.account("가-x1", {}, [], {}, {})
        assert [x[1:3] for x in L["e2_bad"]] == [("2026-10-22", "2026-10-22")], L["e2_bad"]        # 추가지급 메뉴 짝 없음
        (base / "검증자료").mkdir()
        rep = {"reports": [{**row("PAID", 16_897), "payDate": "2026-10-22"}, {**row("REJECTED", 500), "payDate": "2026-10-22"}],
               "totalPages": 1}
        (base / "검증자료" / "가-x1.json").write_text(json.dumps({"additional": {"202610": rep}}), encoding="utf-8")
        L = led.account("가-x1", {}, [], {}, {})
        assert not L["e2_bad"], L["e2_bad"]
        lab = {x[2]: x[6] for x in L["rows"]}
        assert lab == {"2026-10-22": "지급 완료 · 추가지급", "2026-10-20": "지급 완료 · 보류 해제 지급"}, lab
        assert round(L["buckets"]["최종 지급 완료"]) == 16_897 + 277_218 and not round(L["buckets"]["지급대상 지급 완료"]), L["buckets"]
    a = _acct([add, rel])
    assert a.bad == 0, a.bad                                    # 추가지급 줄 검산은 장부 E2(메뉴 짝)에서
    assert round(a.paid_total) == 16_897 + 277_218 and round(a.D["보류됐다 풀린 돈"]) == -277_218, (a.paid_total, a.D)
    print("test_d308_additional_round OK")


def test_d305_watch_warning() -> None:
    """D-305: 감지 목록(윙 사유 채권추심·빠른정산 사용액·쿠팡 판매자 성장 대출 + 로켓그로스 MCA·체크카드 칸) 중 처리 판정표(파일)에 없는
    계정×항목 = '확인 필요' 불일치 사유 · 판정표에 있는 항목은 경고 없음."""
    wing = _wing(1_000_000, [("채권추심", 10_000), ("쿠팡 판매자 성장 대출", 798_784), ("상품광고비", 1_000)])
    rg = {**_rg_line(totalPayableAmount=10_000_000, totalMerchantCashAdvanceDeductionAmount=8_121_756,
                     totalAdditionalDeductionAmount=8_121_756),
          "정산일": "2026-08-26", "기간 시작": "2026-08-01", "기간 끝": "2026-08-07", "지급비율": 70, "최종지급액": 1_878_244}
    a = _acct([wing], [rg], judge={"x1": {"채권추심": "시험 근거"}})
    a.ucheck, a.start_note = [], ""
    assert a.bad == 0, a.bad
    assert a._why() == ["확인 필요 — 처리 판정표에 없는 MCA 상환 8,121,756원(D-305)",
                        "확인 필요 — 처리 판정표에 없는 쿠팡 판매자 성장 대출 798,784원(D-305)"], a._why()
    print("test_d305_watch_warning OK")


# ── 관리 몫 입금 나누기(D-294 · 2026-11-17) — 근거 = 샘플검증2 1절 aehee5505(관리 100%): ② 1,270,470 · 있는 줄 1,153,573 · gen 6,609 →
# 지금 방식은 배율 1.09506 으로 끝난 줄에 퍼뜨려 10-07 지급 RG 70% 107,947 → 118,209(+10,262). D-294 = 끝난 줄 = 그 줄 실제 관리 몫 ·
# 지급 줄·gen 이 없는 잔액 110,288 = '입금 예정(지급일 미정)' 한 줄.
def test_status_split_pending_rest() -> None:
    from collections import Counter

    from coupang_analytics.settlement_statement_deduct import status_split
    r1 = ("x", "로켓그로스", "2026-10-07", "2026-09-01", "2026-09-06", 70, "지급 완료")
    r2 = ("x", "로켓그로스", "2026-11-10", "2026-09-07", "2026-10-31", 70, "지급 완료")
    r3 = ("x", "윙", "2026-10-20", "2026-09-21", "2026-09-27", 70, "보류")          # 관리 일부 달(관리 6,890 / 계정 10,274)
    line_info = [("지급 완료", "로켓그로스", "2026-09", 107_947.0, 0.0, Counter({"광고비": 9_570.0}), r1),
                 ("지급 완료", "로켓그로스", "2026-09", 1_045_626.0, 0.0, Counter(), r2),
                 ("보류", "윙", "2026-09", 10_274.0, 0.0, Counter(), r3)]
    gen = {("로켓그로스", "2026-11"): 6_609.0}
    mset = {("로켓그로스", "2026-09"): (1_153_573.0, 1_153_573.0), ("로켓그로스", "2026-11"): (6_609.0, 6_609.0),
            ("윙", "2026-09"): (6_890.0, 10_274.0)}
    settle_m = 1_270_470.0 + 6_890.0
    st, ded, lines = status_split(line_info, gen, mset, settle_m, {"광고비": ("2026-09", 1.0)}, 1.0)
    got = {(row[2], s): round(sm) for row, s, sm, _dm in lines if row}
    assert got == {("2026-10-07", "지급 완료"): 107_947, ("2026-11-10", "지급 완료"): 1_045_626, ("2026-10-20", "보류"): 6_890}, got
    assert sorted((s, round(sm)) for row, s, sm, _dm in lines if row is None) == [("예정", 6_609), ("예정", 110_288)], lines
    assert round(st["지급 완료"]) == 1_153_573 and round(st["보류"]) == 6_890 and round(st["예정"]) == 116_897, st
    assert round(sum(st.values())) == round(settle_m), st                                  # 합 = ② 그대로
    assert ded["지급 완료"] == Counter({"광고비": 9_570.0}) and not ded["예정"], ded      # 공제 몫은 그대로
    # 잔액 0 이면 지급일 미정 잔액 줄 없음
    _st, _d, lines0 = status_split(line_info[:2], {}, mset, 1_153_573.0, {}, 1.0)
    assert all(row is not None for row, *_ in lines0) and round(_st["지급 완료"]) == 1_153_573, lines0
    print("test_status_split_pending_rest OK")


def test_d342_deduction_window_2026() -> None:
    """D-342: 공제 관리 몫(광고·밀크런 등)을 나눌 자료 창 시작 = max(관리 시작 달, 2026-01) · 밀크런 '시작 전달부터'(D-154)는 그 전달이
    2025 면 적용 안 함(안 (나)) · 관리 시작 표시(D-185)는 그대로. 실측 ljung0622(관리 시작 2025-10 · 2025 판매 줄 통째 빠짐 D-329):
    2025-10~12 관리 광고·밀크런이 '판매 0인 달'(D-186) 금액으로 2026 줄 공제 위에 통째 더해지면 안 됨 · 관리 밀크런 = 2026-01 이후 밀크런의 관리 몫."""
    from collections import Counter
    from types import SimpleNamespace

    from coupang_analytics import settlement_statement_deduct as DED
    from coupang_analytics.settlement_statement_account import AD, LOGI, MILK
    a = DED.Account.__new__(DED.Account)
    a.ctx, a.acct = SimpleNamespace(base=Path(tempfile.gettempdir())), "가-x1"
    a.vids, a.vid_name, a.mnames, a.marks, a.opt2pid = {"111"}, {}, set(), {}, {}
    a.start, a.fs, a.active, a.S = "2025-10", "2026-01", ["2026-01"], 0.5
    a.mset = {("로켓그로스", "2026-01"): (500.0, 1000.0)}
    parts = Counter({AD: 2_200.0, MILK: 600.0, LOGI: 1_000.0})                 # 2026 판매 줄 공제(2025 줄 = D-329 로 이미 빠짐)
    a.line_info = [("지급 완료", "로켓그로스", "2026-01", 10_000.0, 0.0, parts, ("x", "로켓그로스", "2026-02-10", "2026-01-01"))]
    a.deduct_lines = [(x[1], x[2], x[5]) for x in a.line_info]
    a.D, a.share, a.rates = Counter(parts), {}, {}
    a.by_m = {"2026-01": Counter({"logi": 1_000.0, "m_logi": 400.0})}        # 상품별 물류비 = 2026 만(D-328)
    a.v = {"inbound": [{"milkrunSeq": s, "skus": [{"vendorItemId": 111, "stowedQty": q1}, {"vendorItemId": 222, "stowedQty": q2}]}
                       for s, q1, q2 in (("M11", 1, 0), ("M12", 1, 0), ("M01", 1, 1))]}
    days = {"20251015": (1_000.0, 1.0), "20251115": (1_000.0, 1.0), "20251215": (1_000.0, 1.0), "20260115": (2_000.0, 0.5)}
    pa = [(d, 1, 111, c * r) for d, (c, r) in days.items()] + [(d, 1, 222, c * (1 - r)) for d, (c, r) in days.items()]
    bill = {(int(d), "1"): c for d, (c, _r) in days.items()}
    milk = {"202511": [("M11", 400.0)], "202512": [("M12", 500.0)], "202601": [("M01", 600.0)]}
    saved = DED.ad_files, DED.milk_rows
    DED.ad_files = lambda base, acct: (pa, bill, {d[:6] for d in days})
    DED.milk_rows = lambda base, acct, since="": [x for m, xs in sorted(milk.items()) if m >= since for x in xs]
    try:
        a._logi_comp()
        a._ads()
        a._milk()
    finally:
        DED.ad_files, DED.milk_rows = saved
    got = {k: round(a.share[k][0] * a.D[k]) for k in (AD, MILK, LOGI)}
    # 광고 = 2026-01 청구 2,000 × 관리 0.5 × 1.1 (2025-10~12 관리 3,300 안 더함) · 밀크런 = M01 600 × 0.5(2025-11·12 밀크런 = 2025 줄에서 공제 · 안 (나))
    assert got == {AD: 1_100, MILK: 300, LOGI: 400}, got
    assert a.rates[AD][0] == a.rates[MILK][0] == "2026-01", a.rates                 # 입금 나누기도 2026-01 판매 줄부터
    assert "관리 시작 2025-10" in a.share[AD][1], a.share[AD]                        # D-185 표시 그대로
    print("test_d342_deduction_window_2026 OK")


def test_d279_svc_estimate_row_and_d304_note() -> None:
    """D-279 ②: 쿠팡 예정 줄에 아직 안 붙은 이용료(규칙 잔액 · 우리 계산값) = 따로 '경고값' 줄 · 쿠팡 줄 몫 줄엔 경고 없음 · 합계 그대로.
    D-304: 3PM_매출채권 줄 설명 = 원문 값 + '이월'."""
    from collections import Counter

    import openpyxl

    from coupang_analytics import settlement_statement_book as BK
    from coupang_analytics import settlement_statement_sheets as SH
    from coupang_analytics.settlement_statement_account import PM3, SVC
    a = {"Dm": {SVC: 110_000.0 + 55_000.0, PM3: 20_000.0}, "sv": {"잔액 관리": 55_000.0},
         "st_settle": {"지급 완료": 1_000_000.0, "예정": 0.0, "보류": 0.0},
         "st_ded": {"지급 완료": Counter({SVC: 55_000.0, PM3: 20_000.0}), "예정": Counter({SVC: 55_000.0 + 55_000.0}), "보류": Counter()}}
    ded = [(SVC, 165_000), (PM3, 20_000)]
    tbl = SH._status_table(a, 1_000_000, ded)
    rows = {label: (c, total) for label, c, total in tbl}
    assert rows[SVC] == ({"지급 완료": -55_000, "보류": 0, "예정": -55_000}, -110_000), rows[SVC]      # 쿠팡 줄 몫(완료 + 예정 줄)
    assert rows[SH.SVC_EST] == ({"지급 완료": 0, "보류": 0, "예정": -55_000}, -55_000), rows          # 규칙 잔액 = 예정만
    assert sum(t for _l, _c, t in tbl[1:]) == -185_000, tbl                                             # 공제 합 그대로
    assert "D-279 ②" in SH.SVC_EST and "경고값" in SH.SVC_EST
    assert "이월" in SH.NOTES[PM3] and "D-304" in SH.NOTES[PM3] and "경고값" not in SH.NOTES[SVC]
    ws = openpyxl.Workbook().active
    v = {"tbl": tbl, "cost": 185_000, "fast": 0, "보류": 0, "지급 완료": 925_000, "예정": -110_000, "pay": 815_000, "settle": 1_000_000}
    share = {SVC: (110_000 / 165_000, "", "쿠팡 자료 비율"), PM3: (1.0, "", "쿠팡 자료")}
    BK._blocks_fg(ws, 1, {"D": {SVC: 165_000.0, PM3: 20_000.0}, "share": share}, v, [], "")
    notes = {ws.cell(r, 2).value: str(ws.cell(r, 6).value) for r in range(1, ws.max_row + 1)}
    assert "D-279 ②" in notes[SH.SVC_EST] and "경고값" in notes[SH.SVC_EST], notes
    assert "경고값" not in notes[SVC] and "이월" in notes[PM3], notes
    print("test_d279_svc_estimate_row_and_d304_note OK")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    test_d342_deduction_window_2026()
    test_d279_svc_estimate_row_and_d304_note()
    test_d312_fast_used()
    test_d312_own_deduction()
    test_t125_forecast_keeps_own_cols()
    test_d304_wing_negative_round()
    test_d319_scheduled_negative_kept()
    test_d308_additional_round()
    test_d305_watch_warning()
    test_cost_only_scope()
    test_managed_alloc()
    test_settlement_ledger()
    test_d329_sale_2025_excluded()
    test_d328_product_rows_2025_excluded()
    test_d391_unknown_ship_same_month_wing_ratio()
    test_additional_pay()
    test_migration_inputs()
    test_managed_scope()
    test_scope_priority()
    test_scope_judge()
    test_status_split_pending_rest()
    print("✅ 위탁정산서 계산 규칙 시험 3종 + 이관 입구 + 관리 상품 범위 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
