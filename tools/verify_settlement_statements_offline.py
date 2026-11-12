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
    ctx = SimpleNamespace(managed={"m1": [5, 6]}, listings={"m1": {"노출명"}}, settle_only={"a1": {"111": "관리", "222": ""}},
                          settle_only_err="", window={"m1": {"vids": ["7"], "pids": ["P9"]}})
    assert AC.scope(ctx, "m1") == ("결과 시트 관리 상품 + 계약 기간 보강", {"5", "6", "7"}, {"노출명"}, {"P9": "관리"})
    assert AC.scope(ctx, "a1")[0] == "판정 대기(원장 정산전용상품 구분 빈 칸 1줄)"
    assert AC.scope(ctx, "zz")[0] == "관리 상품 자료 없음"
    assert (AC.month_add("2026-01", -1), AC.month_add("2026-12", 1), AC.month_add("9999-99", -1)) == ("2025-12", "2027-01", "9999-99")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    test_managed_alloc()
    test_settlement_ledger()
    test_additional_pay()
    test_migration_inputs()
    print("✅ 위탁정산서 계산 규칙 시험 3종 + 이관 입구 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
