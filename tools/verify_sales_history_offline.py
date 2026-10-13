"""판매분석 금액 날짜별 누적(sales_history) 오프라인 검증 — 로그인·쿠팡 호출 없음(결정적).

목표(소유자 2026-10-13): 매일 ① 판매수집의 판매분석(vi-detail-search) 상품(옵션)별 **판매금액(totalGmv)** 을
날짜별로 쌓아, 정산 전 최근 판매를 금액으로 알 수 있게 한다(사업자별 정산내역의 로켓그로스 미정산 추정 보강).

    python tools/verify_sales_history_offline.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics import collector as C  # noqa: E402
from coupang_analytics import sales_history as SH  # noqa: E402
from coupang_analytics.report import OptionMetric  # noqa: E402


def ok(msg):
    print(f"  ✔ {msg}")


def _item(vid, gmv, units, orders, reg="RFM", name="캠핑테이블 XR010", opt="블랙"):
    return {"vendorItemDetails": {"vendorItemId": vid, "productName": name, "itemName": opt, "itemId": 77,
                                  "registrationType": reg, "productId": 900},
            "businessInsightsMetricsResponse": {"totalPageViews": 40.0, "totalUnitsSold": float(units),
                                                "totalUniqueVisitor": 20.0, "totalGmv": float(gmv),
                                                "totalOrders": float(orders)}}


def s1_parse_gmv():
    print("[S1] 판매분석 응답 → 옵션별 판매금액·주문수(API 값 그대로)")
    m = C._parse_vendor_items([_item(111, 125000, 5, 3), _item(222, 0, 0, 0, reg="NORMAL")])
    assert m["111"].gmv == 125000 and m["111"].orders == 3 and m["111"].sales == 5
    assert m["222"].gmv == 0 and m["222"].orders == 0
    assert OptionMetric("1", "p", "o", "i", 0, 0, 0).gmv is None      # 엑셀 폴백 등 금액 모름 = None(0 아님)
    ok("totalGmv→gmv·totalOrders→orders · 금액 없는 출처는 None")


def s2_record_daily():
    print("[S2] 하루 단위만 날짜별 기록·같은 날 덮어씀·다른 날 추가·판매 0인 날도 기록")
    m = C._parse_vendor_items([_item(111, 125000, 5, 3), _item(222, 30000, 1, 1, reg="NORMAL", name="보냉백")])
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "output"
        assert SH.record(out, "acc1", "2026-10-12", "2026-10-12", m).startswith("기록 — 옵션 2개·판매금액 155,000원")
        d = json.loads((out / SH.DIRNAME / "acc1.json").read_text(encoding="utf-8"))
        day = d["2026-10-12"]
        assert day["옵션"]["111"] == {"상품": "캠핑테이블 XR010", "옵션": "블랙", "구분": "로켓그로스", "판매금액": 125000,
                                     "판매수량": 5, "주문": 3}, day
        assert day["옵션"]["222"]["구분"] == "윙" and day["합계"] == {"판매금액": 155000, "판매수량": 6, "주문": 4}
        assert day["수집"]                                                      # 수집 시각 남김
        m2 = C._parse_vendor_items([_item(111, 50000, 2, 2)])
        SH.record(out, "acc1", "2026-10-12", "2026-10-12", m2)                  # 같은 날 재실행 = 그날만 교체
        SH.record(out, "acc1", "2026-10-13", "2026-10-13", {})                  # 판매 0인 날 = 빈 기록(없음과 구분)
        d = json.loads((out / SH.DIRNAME / "acc1.json").read_text(encoding="utf-8"))
        assert sorted(d) == ["2026-10-12", "2026-10-13"]
        assert list(d["2026-10-12"]["옵션"]) == ["111"] and d["2026-10-12"]["합계"]["판매금액"] == 50000
        assert d["2026-10-13"]["옵션"] == {} and d["2026-10-13"]["합계"]["판매금액"] == 0
        assert not list((out / SH.DIRNAME).glob("*.tmp"))                       # 반쯤 쓴 파일 없음
    ok("하루=기록·같은 날 교체·다른 날 추가·0 판매 날 기록·합계·임시파일 없음")


def s3_skip():
    print("[S3] 넓은 기간(보강 조회)·금액 모르는 출처(엑셀 폴백) = 기록 안 함")
    m = C._parse_vendor_items([_item(111, 125000, 5, 3)])
    fallback = {"111": OptionMetric("111", "p", "o", "i", 1, 5, 1, registration_type="RFM")}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "output"
        r1 = SH.record(out, "acc1", "2026-09-12", "2026-10-12", m)
        r2 = SH.record(out, "acc1", "2026-10-12", "2026-10-12", fallback)
        assert r1.startswith("건너뜀") and "하루" in r1, r1
        assert r2.startswith("건너뜀") and "금액" in r2, r2
        assert not (out / SH.DIRNAME / "acc1.json").exists()
    ok("기간 조회·엑셀 폴백은 기록 안 함(사유 반환)")


def main():
    old = os.getcwd()
    try:
        s1_parse_gmv()
        s2_record_daily()
        s3_skip()
    finally:
        os.chdir(old)
    print("판매분석 금액 날짜별 누적 오프라인 검증 통과")


if __name__ == "__main__":
    main()
