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
                          daily=stores[0], periods=stores[1], ranked={}, src_vids={})
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
                          src_vids=src_vids, files={}, contracts={"a1": "2026-05-14"}, daily=stores[0], periods=stores[1])
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


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    test_managed_alloc()
    test_settlement_ledger()
    test_additional_pay()
    test_migration_inputs()
    test_managed_scope()
    test_scope_priority()
    test_scope_judge()
    print("✅ 위탁정산서 계산 규칙 시험 3종 + 이관 입구 + 관리 상품 범위 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
