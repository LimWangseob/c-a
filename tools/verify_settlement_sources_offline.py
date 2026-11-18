"""받기 의심 감지(T-82)·자료 출처 대조(T-78 S1~S3) 오프라인 검증 — 기대값 = 설계서·D-302 실측 사례(코드에서 뽑지 않음).

로그인·브라우저·네트워크 호출 없음(공개 웹은 가짜 fetch). 실패 시 AssertionError → exit 1.

    python tools/verify_settlement_sources_offline.py
"""
from __future__ import annotations

import json
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

import openpyxl  # noqa: E402

from coupang_analytics import settlement_ads as AD  # noqa: E402
from coupang_analytics import settlement_fetch_check as FC  # noqa: E402
from coupang_analytics import settlement_files as SF  # noqa: E402
from coupang_analytics import settlement_sources as SRC  # noqa: E402
from coupang_analytics.settlement_wing_api import SiteChangedError  # noqa: E402

D = date.fromisoformat
ACCT = "가-나-acct1"


def ok(msg: str) -> None:
    print(f"  OK {msg}")


def xlsx(path: Path, sheets: dict) -> Path:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def wjson(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


REVIEW_HDR = ["정산유형", "정산주기(종료일)", "발생일", "매출인식일", "거래유형", "이벤트 ID", "제품명", "노출상품 ID", "주문ID",
              "주문일", "리뷰 ID", "리뷰생성일", "리뷰유형", "세금계산서 발행월", "리뷰 이벤트 수수료", None, None, None]
REVIEW_SUB = [None] * 14 + ["발생금액(A)", "할인금액(B)", "무료 프로모션 금액(C)", "할인적용금액(A-B-C)"]


def summary_sheet(end: str, total: int, tax: int) -> list:
    return [[None], [None], ["정산주기(종료일)", "합계", "세액", "최종비용"], [end, total, tax, total + tax]]


def cost_file(base: Path, settle: str, report: str, start: str, end: str, sheets: dict) -> Path:
    name = SF.settle_file_name(ACCT, D(settle), "로켓그로스", "주정산", report, D(start), D(end))
    return xlsx(base / "파일" / "비용" / name, sheets)


def t1_cost_reports():
    print("[T1] 비용 리포트 ↔ 같은 정산 줄 공제 칸 — 리뷰 리포트 0줄 + 공제 6,660 = 대조 안 함(D-324 ④ · 검산은 T9 계정 누계)")
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        review = cost_file(base, "2026-11-06", "리뷰 이벤트 비용", "2026-10-05", "2026-10-11",
                           {"리뷰 이벤트": [[None] * 18 for _ in range(5)] + [REVIEW_HDR, REVIEW_SUB]})
        cost_file(base, "2026-11-06", "보관비", "2026-10-05", "2026-10-11", {"보관비": summary_sheet("2026-10-11", 6304, 630)})
        cost_file(base, "2026-11-06", "입출고/배송비", "2026-10-05", "2026-10-11",
                  {"입출고비": summary_sheet("2026-10-11", 50000, 5000), "배송비": summary_sheet("2026-10-11", 80000, 8000)})
        cost_file(base, "2026-11-13", "보관비", "2026-10-12", "2026-10-18", {"보관비": summary_sheet("2026-10-18", 100, 10)})
        cost_file(base, "2026-11-13", "리뷰 이벤트 비용", "2026-10-12", "2026-10-18",
                  {"리뷰 이벤트": [[None] * 18 for _ in range(5)] + [REVIEW_HDR, REVIEW_SUB]})
        wjson(base / "쿠팡지급내역" / f"{ACCT}_로켓그로스.json", [
            {"정산일": "2026-11-06", "기간 시작": "2026-10-05", "기간 끝": "2026-10-11", "지급비율": 70,
             "totalPostPurchaseDeductionAmount": 6660.0, "totalStorageFeeDeductionAmount": 6934,
             "totalWarehousingFeeDeductionAmount": 55000, "totalFulfillmentFeeDeductionAmount": 88000}])
        rows = FC.cost_checks(base / "파일" / "비용", base / "쿠팡지급내역")
        by = {(r["정산일"], r["항목"]): r for r in rows}
        assert len(rows) == 1, rows
        assert ("2026-11-06", "리뷰-이벤트-비용") not in by, by     # D-324 ④: 쿠팡이 빈 리포트를 줌(윙 화면 재받기 11-18) — 받기 의심 아님
        assert review.exists()
        r = by[("2026-11-13", "리뷰-이벤트-비용")]
        assert (r["판정"], r["다시 받기"]) == (FC.CHECK, FC.NO) and "지급 내역 줄 없음" in r["설명"], r
        assert ("2026-11-13", "보관비") not in by            # 정산 줄 없는 주 물류비 = 미납 CFS 주 리포트(D-065) · 대조 안 함
        assert ("2026-11-06", "입출고-배송비") not in by and ("2026-11-06", "보관비") not in by   # 두 칸 합 = 리포트 합
        bad = cost_file(base, "2026-11-06", "반출비", "2026-10-05", "2026-10-11", {"x": [["a"], ["b"]]})
        r = [x for x in FC.cost_checks(base / "파일" / "비용", base / "쿠팡지급내역") if x["항목"] == "반출비"][0]
        assert (r["판정"], r["받은 값"], r["다시 받기"], r["근거 파일"]) == (FC.SUSPECT, "읽기 실패", FC.YES, str(bad)), r
        memo = base / "memo.json"
        first = FC.cost_checks(base / "파일" / "비용", base / "쿠팡지급내역", memo)
        orig = SF.read_sheets
        SF.read_sheets = lambda p: (_ for _ in ()).throw(AssertionError(f"기억된 파일을 다시 읽음 {p}"))
        try:
            assert FC.cost_checks(base / "파일" / "비용", base / "쿠팡지급내역", memo) == first
        finally:
            SF.read_sheets = orig
        assert len(json.loads(memo.read_text(encoding="utf-8"))) == 6
    ok("리뷰 0줄 ↔ 공제 6,660 = 줄 없음(D-324 ④) · 입출고/배송 2칸 합 일치 = 줄 없음 · 지급 줄 없음 = 확인 필요(미납 CFS 주 물류비 제외) · 못 읽는 파일 = 받기 의심 · 시트 합 기억(두 번째는 엑셀 안 읽음)")


def t2_live():
    print("[T2] 라이브정산 요약 ↔ 공제 줄 — 빈 json 달의 짝 없는 공제 = 받기 의심(D-302 freewin7777 2026-02 · 347)")
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        md = base / "검증자료" / "월자료" / ACCT
        wjson(md / "라이브정산_202602.json", {"요약": [], "상세": []})
        wjson(md / "라이브정산_202603.json", {"요약": [{"totalAmount": 290, "calculationDate": "20260425", "month": "202603"}],
                                              "상세": []})
        wjson(md / "라이브정산_202604.json", {"요약": [{"totalAmount": 264, "calculationDate": "20260525"}], "상세": []})
        wjson(base / "쿠팡지급내역" / f"{ACCT}_로켓그로스.json", [
            {"정산일": "2026-01-10", "totalCoupangLiveDeductionAmount": 999},            # 받는 시작 달 앞 = 범위 밖
            {"정산일": "2026-03-30", "totalCoupangLiveDeductionAmount": 347},
            {"정산일": "2026-04-27", "totalCoupangLiveDeductionAmount": 290}])
        wjson(base / "쿠팡지급내역" / f"{ACCT}_윙.json", [{"정산일": "2026-06-01", "차감 사유": [{"사유": "라이브 커머스", "금액": 500}]}])
        rows = FC.live_checks(base / "검증자료" / "월자료", base / "쿠팡지급내역")
        assert [(r["판정"], r["정산일"], r["기간"], r["대조 값"], r["다시 받기"]) for r in rows] == [
            (FC.SUSPECT, "2026-03-30", "202602", 347, FC.YES), (FC.CHECK, "2026-06-01", "202604", 500, FC.NO)], rows
        assert rows[0]["근거 파일"].endswith("라이브정산_202602.json") and "비었는데" in rows[0]["설명"]
    ok("빈 2월 json + 3/30 공제 347 = 받기 의심 · 290 = 4월 계산일 뒤 짝 · 264 달 짝 없는 윙 500 = 확인 필요(다시 받기 아님) · 범위 밖 무시")


def t3_ads_milk():
    print("[T3] 광고정산 subtotals 없음 = T-90 필요분만 · 밀크런 총 합계금액 = 발생+조정+추가금+세액 검산")
    with tempfile.TemporaryDirectory() as td:
        ad = Path(td) / "광고"
        wjson(ad / f"{ACCT}_광고정산_202601.json", {"summary": {}, "items": []})
        wjson(ad / f"{ACCT}_광고정산_202602.json", {"summary": {}, "items": [], "subtotals": None})
        rows = FC.ad_checks(ad)
        assert [(r["기간"], r["다시 받기"]) for r in rows] == [("202601", FC.T90)], rows
        head = ["정산번호", "밀크런번호", "발생금액", "세액", "총 합계금액", "취소수수료", "조정액", "추가금", "통행료"]
        xlsx(ad / f"{ACCT}_밀크런_202609.xlsx", {"s": [head,
             ["1", "M1", "28500", "3550", "39050", "0", "0", "7000", "0"],      # 추가금 포함(output38 실측 모양)
             ["1", "M2", "15000", "1280", "14080", "0", "-2200", "0", "0"],     # 조정액 포함
             ["1", "M3", "1000", "100", "1100", "0", "0", "0", "500"],          # 통행료 처음 봄
             ["1", "M4", "1000", "100", "9999", "0", "0", "0", "0"]]})          # 합 다름
        xlsx(ad / f"{ACCT}_밀크런_202610.xlsx", {"s": [head[:5], ["1", "M5", "1", "1", "2"]]})
        rows = FC.milk_checks(ad)
        got = sorted((r["기간"], r["항목"], r["판정"]) for r in rows)
        assert got == [("202609", "M3 통행료", FC.CHECK), ("202609", "M4 총 합계금액", FC.CHECK),
                       ("202610", "머리글", FC.SUSPECT)], got
    ok("subtotals 키 없음만 후보(null 은 받은 것) · 추가금·조정액 포함 합 일치 · 통행료·합 다름 = 확인 필요 · 칸 빠진 엑셀 = 받기 의심")


def t4_write():
    print("[T4] 받기의심.csv 전체 · 다시받을목록.csv = 다시 받기 예·T-90 만")
    with tempfile.TemporaryDirectory() as td:
        rows = [FC._row(FC.SUSPECT, "비용 리포트", "a", "2026-11-06", "p", "x", 0, 1, FC.YES, "f", "w"),
                FC._row(FC.CHECK, "밀크런", "a", "", "202609", "y", 1, 2, FC.NO, "f", "w"),
                FC._row(FC.SUSPECT, "광고정산", "a", "", "202601", "z", "", "", FC.T90, "f", "w")]
        alls, again = FC.write(Path(td), rows, D("2026-11-18"))
        n = [len(p.read_text(encoding="utf-8-sig").strip().splitlines()) for p in (alls, again)]
        assert n == [4, 3], n
        assert FC.summary(rows) == "받기 의심 광고정산 1 · 받기 의심 비용 리포트 1 · 확인 필요 밀크런 1", FC.summary(rows)
    ok("두 파일 줄 수 · 처리기록 한 줄 요약")


def t4b_scan_budget():
    print("[T4b] scan = 비용 리포트·밀크런 엑셀 새 파일 상한(실행당) · 기억된 파일은 다시 안 읽음 · 남은 수 보고")
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        for i, (s, e) in enumerate((("2026-10-05", "2026-10-11"), ("2026-10-12", "2026-10-18"), ("2026-10-19", "2026-10-25"))):
            cost_file(base, f"2026-11-{6 + i:02d}", "리뷰 이벤트 비용", s, e,
                      {"리뷰 이벤트": [[None] * 18 for _ in range(5)] + [REVIEW_HDR, REVIEW_SUB]})
        wjson(base / "쿠팡지급내역" / f"{ACCT}_로켓그로스.json",
              [{"정산일": "2026-11-06", "기간 시작": "2026-10-05", "기간 끝": "2026-10-11", "totalPostPurchaseDeductionAmount": 2220}])
        wjson(base / "검증자료" / f"{ACCT}.json", {"review_campaigns": {"count": 1, "hasMore": False, "campaigns": [camp(1)]}})
        head = ["밀크런번호", "발생금액", "세액", "총 합계금액", "조정액", "추가금", "통행료"]
        xlsx(base / "검증자료" / "광고" / f"{ACCT}_밀크런_202609.xlsx", {"s": [head, ["M1", "1", "1", "x", "0", "0", "0"]]})
        rows, later = FC.scan(base, max_new=2)
        assert later == 2 and [(r["정산일"], r["판정"]) for r in rows] == [("2026-11-07", FC.CHECK)], (later, rows)   # 11-06 = D-324 ④
        rows, later = FC.scan(base, max_new=2)
        assert later == 0 and [r["정산일"] for r in rows] == ["2026-11-07", "2026-11-08", ""], (later, rows)  # 남은 2개 · 리뷰 누계 1×2,220 = 공제
        milk = [r for r in rows if r["종류"] == "밀크런"][0]
        assert (milk["판정"], milk["받은 값"], milk["다시 받기"]) == (FC.SUSPECT, "읽기 실패", FC.YES), milk
        assert FC.scan(base, max_new=0) == (rows, 0)                              # 다 기억 → 새로 안 읽어도 같은 결과
    ok("상한 2 → 남음 2 · 다음 실행에 마저 · 숫자 아닌 밀크런 금액 = 받기 의심(0 으로 안 바꿈) · 기억만으로 같은 결과")


def camp(used: int, incentive: int = 2000, fee: int = 200, status: str = "ACTIVE") -> dict:
    """리뷰 이벤트 캠페인(검증자료 review_campaigns 실측 칸 · 91white fe9e2d01 모양) — 1건 = 2,000 + 200×1.1 = 2,220(D-302 ⑤)."""
    return {"campaignId": f"c{used}{status}", "status": status, "incentivePerReview": incentive, "serviceFeePerReview": fee,
            "sellerContribution": {"targetReviews": 25, "consumedReviews": used}}


def t9_review_cumulative():
    print("[T9] 리뷰 이벤트 계정 누계 = 사용 리뷰 × 2,220(D-324 ② · 근거 신규22_리뷰공제_이월검산.md 2절 표)")
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        amounts, ver = base / "쿠팡지급내역", base / "검증자료"
        # 91white 모양: 캠페인 3 + 2(취소된 캠페인도 사용분은 공제) · RG 6,660 + 윙 4,440 = 11,100 = 5 × 2,220 → 줄 없음
        wjson(ver / "가-나-a91.json", {"review_campaigns": {"count": 2, "hasMore": False,
                                                         "campaigns": [camp(3), camp(2, status="CANCELLED")]}})
        wjson(amounts / "가-나-a91_로켓그로스.json", [{"정산일": "2026-11-06", "totalPostPurchaseDeductionAmount": 6660.0}])
        wjson(amounts / "가-나-a91_윙.json", [{"정산일": "2026-11-13", "차감 사유": [{"사유": "리뷰 이벤트", "금액": 4440},
                                                                                {"사유": "상품/브랜드광고비", "금액": 2316}]}])
        # tellace83 모양: 1건 2,220 = 2,220 → 줄 없음
        wjson(ver / "가-나-at.json", {"review_campaigns": {"count": 1, "hasMore": False, "campaigns": [camp(1)]}})
        wjson(amounts / "가-나-at_로켓그로스.json", [{"정산일": "2026-11-10", "totalPostPurchaseDeductionAmount": 2220}])
        # sg0141n 모양: 사용 9(4·3·1·1) = 19,980 · 지급 끝난 공제 2,220 → 남은 8건 = 회차 미확정(확인 필요 · 다시 받기 아님)
        wjson(ver / "가-나-asg.json", {"review_campaigns": {"count": 4, "hasMore": False,
                                                         "campaigns": [camp(4), camp(3), camp(1), camp(1)]}})
        wjson(amounts / "가-나-asg_로켓그로스.json", [{"정산일": "2026-11-03", "totalPostPurchaseDeductionAmount": 2220}])
        # robincohs 모양: 0 = 0 → 줄 없음
        wjson(ver / "가-나-arc.json", {"review_campaigns": {"count": 0, "hasMore": False, "campaigns": []}})
        wjson(amounts / "가-나-arc_로켓그로스.json", [{"정산일": "2026-11-03", "totalPostPurchaseDeductionAmount": 0}])
        # 사용 리뷰보다 공제가 많음 = 캠페인 자료 빠짐 의심(받기 의심 · 다시 받기)
        wjson(ver / "가-나-aover.json", {"review_campaigns": {"count": 1, "hasMore": False, "campaigns": [camp(0)]}})
        wjson(amounts / "가-나-aover_로켓그로스.json", [{"정산일": "2026-11-03", "totalPostPurchaseDeductionAmount": 2220}])
        # 공제는 있는데 검증자료(캠페인) 없음 = 받기 의심
        wjson(amounts / "가-나-anone_윙.json", [{"정산일": "2026-11-13", "차감 사유": [{"사유": "리뷰 이벤트", "금액": 2220}]}])
        wjson(ver / "결제확정_지연분포.json", {"기준 달": "202610"})                 # 계정 파일 아닌 검증자료 = 무시
        rows = FC.review_checks(ver, amounts)
        got = [(r["계정"], r["판정"], r["받은 값"], r["대조 값"], r["다시 받기"]) for r in rows]
        assert got == [("가-나-anone", FC.SUSPECT, 2220, 0, FC.YES), ("가-나-aover", FC.SUSPECT, 2220, 0, FC.YES),
                       ("가-나-asg", FC.CHECK, 2220, 19980, FC.NO)], got
        sg = rows[2]
        assert sg["종류"] == "리뷰 이벤트" and "8건" in sg["설명"] and "회차 미확정" in sg["설명"], sg
        assert "캠페인 자료 없음" in rows[0]["설명"] and rows[1]["근거 파일"].endswith("가-나-aover.json"), rows
        assert FC.review_per(camp(1, incentive=3000, fee=300)) == 3330                 # 1건 금액 = 캠페인 칸(사사오입 300×1.1)
        wjson(ver / "가-나-at.json", {"review_campaigns": {"count": 101, "hasMore": True, "campaigns": [camp(0)]}})
        more = [r for r in FC.review_checks(ver, amounts) if r["계정"] == "가-나-at"]
        assert len(more) == 1 and more[0]["판정"] == FC.SUSPECT and "100개 넘음" in more[0]["설명"], more
    ok("5×2,220 = 6,660+4,440(윙 포함) · 1 = 2,220 · 0 = 0 줄 없음 · 사용 9 ↔ 2,220 = 8건 회차 미확정(확인 필요) · 공제 > 사용·캠페인 자료 없음·다 못 받음 = 받기 의심")


def t5_ads_progress_refetch():
    print("[T5] 광고 끝나지 않은 달 일별 매일 덮어쓰기(S2) · _광고_다시받기.json 달만 subtotals 다시 받기(옛 파일 보관)")
    assert AD.progress_months(D("2025-11-01"), D("2026-11-18")) == [("202611", D("2026-11-01"), D("2026-11-17"))]
    assert AD.progress_months(D("2025-11-01"), D("2026-11-02")) == [("202610", D("2026-10-01"), D("2026-10-31")),
                                                                    ("202611", D("2026-11-01"), D("2026-11-01"))]
    assert AD.progress_months(D("2026-11-01"), D("2026-11-01")) == []
    with tempfile.TemporaryDirectory() as td:
        folder, calls = Path(td), []
        for ym in ("202609", "202610"):
            wjson(folder / f"{ACCT}_광고정산_{ym}.json", {"summary": {}, "items": []})        # 옛 질의
            (folder / f"{ACCT}_밀크런_{ym}.xlsx").write_bytes(b"m")
        wjson(folder / f"{ACCT}_광고.json", {"캠페인 없음": ["202609", "202610"]})
        wjson(folder / AD.REFETCH, {ACCT: ["202609"]})

        def call(method, path, body):
            calls.append(body["variables"])
            if "DailySettlement" in body["query"]:
                return {"data": {"getDailySettlement": {"summary": {}, "items": [], "subtotals": {"rocketGrowth": []}}}}
            return {"data": {"getCampaignList": []}}
        s = AD.collect(call, lambda url: b"m", folder, ACCT, D("2026-09-01"), D("2026-11-18"))
        assert s["다시 받음"] == ["202609"] and s["진행 달"] == ["202611"] and not s["실패"], s
        assert "subtotals" in json.loads((folder / f"{ACCT}_광고정산_202609.json").read_text(encoding="utf-8"))
        assert "subtotals" not in json.loads((folder / f"{ACCT}_광고정산_202610.json").read_text(encoding="utf-8"))  # 목록 밖
        assert (folder / AD.OLD_KEEP / f"{ACCT}_광고정산_202609.json").exists()
        prog = json.loads((folder / f"{ACCT}_{AD.PROGRESS}_202611.json").read_text(encoding="utf-8"))
        assert prog["기간"] == ["2026-11-01", "2026-11-17"] and "subtotals" in prog
        assert {"startDate": 20261101, "endDate": 20261117, "settlementDomain": "SELLER"} in calls, calls
        assert not list(folder.glob(f"{ACCT}_광고정산_2026*.tmp"))
        n = len(calls)
        s2 = AD.collect(call, lambda url: b"m", folder, ACCT, D("2026-09-01"), D("2026-11-18"))
        assert s2["다시 받음"] == [] and s2["진행 달"] == ["202611"] and len(calls) == n + 1, (s2, calls[n:])  # 진행 달만 다시
    ok("진행 달 = 1일~어제(말일 넘으면 지난달 끝까지) · 다시 받기 목록 달만·옛 파일 보관 · 두 번째 실행 = 진행 달 1번만 부름")


def rg_fee_grid(rows: list) -> dict:
    head = ["정산유형", "정산주기(종료일)", "매출인식일", "주문ID", "카테고리ID", "카테고리명", "옵션ID", "등록상품 ID", "등록상품명",
            "옵션명", "판매가(A)", "판매수량(B)", "판매액(A*B)", "판매수수료율(%,VAT별도)", "할인적용 판매수수료율(%,VAT별도)"]
    return {"s": [[None], head] + rows}


def t6_originals():
    print("[T6] S1 원문 대조 — 기준 만든 뒤 새 카테고리ID·새 수수료율·새 서비스이용율만 변경이력(처음 본 날 = 원문 날짜)")
    with tempfile.TemporaryDirectory() as td:
        base, files = Path(td), Path(td) / "파일"

        def rg(settle, start, end, rows):
            xlsx(files / SF.settle_file_name(ACCT, D(settle), "로켓그로스", "주정산", "판매수수료", D(start), D(end)), rg_fee_grid(rows))
        rg("2026-10-20", "2026-10-05", "2026-10-11", [["주정산", "2026-10-11", "2026-10-06", "1", "5401", "보호대", "9", "8", "p", "o",
                                                      1, 1, 1, 7.8, 0]])
        wing = [["주문번호", "옵션 ID", "서비스이용율(%,VAT별도)", "구매확정일"], ["1", "94507205566", "10.8", "2026-10-20"],
                ["1", "0", "0", ""]]
        xlsx(files / SF.settle_file_name(ACCT, D("2026-11-13"), "윙", "주정산", "주문상세", D("2026-10-19"), D("2026-10-25")), {"s": wing})
        xlsx(files / "무관한파일.xlsx", {"s": [["a"]]})
        r = SRC.compare_originals(base, files, D("2026-11-18"))
        assert (r["읽음"], r["남음"], r["이력"], r["기준"]) == (2, 0, 0, "2026-11-18"), r
        rg("2026-10-27", "2026-10-12", "2026-10-18", [
            ["주정산", "2026-10-18", "2026-10-13", "2", "5401", "보호대", "9", "8", "p", "o", 1, 1, 1, 7.8, 0],     # 같음
            ["주정산", "2026-10-18", "2026-10-14", "3", "5401", "보호대", "9", "8", "p", "o", 1, 1, 1, 6.5, 0],     # 새 비율
            ["주정산", "2026-10-18", "2026-10-15", "4", "7777", "새카테고리", "9", "8", "p", "o", 1, 1, 1, 10.0, 0]])
        r = SRC.compare_originals(base, files, D("2026-11-19"))
        assert (r["읽음"], r["이력"]) == (1, 4), r       # 5401 수수료율 새 값 + 7777 처음(이름·율·할인율 3항목)
        hist = (base / "자료출처" / "변경이력.csv").read_text(encoding="utf-8-sig").splitlines()
        assert hist[0].split(",")[:3] == ["기록일", "출처ID", "항목"] and len(hist) == 5, hist
        assert any("5401 판매수수료율,7.8,6.5,2026-10-14" in h for h in hist), hist
        assert any("7777 카테고리명,,새카테고리,2026-10-15" in h for h in hist), hist
        assert SRC.compare_originals(base, files, D("2026-11-20"))["읽음"] == 0          # 읽은 파일 다시 안 읽음
        bad = files / SF.settle_file_name(ACCT, D("2026-11-03"), "로켓그로스", "주정산", "판매수수료", D("2026-10-19"), D("2026-10-25"))
        xlsx(bad, {"s": [["정산유형", "옵션ID"]]})
        for day in ("2026-11-21", "2026-11-22"):                                          # 다음 실행에도 다시 오류(읽은 표시 안 함)
            r = SRC.compare_originals(base, files, D(day))
            assert r["읽음"] == 0 and len(r["오류"]) == 1 and bad.name in r["오류"][0] and "머리글" in r["오류"][0], r
    ok("기준 실행 = 이력 0 · 새 비율 1 + 새 카테고리 3항목 = 4줄 · 처음 본 날 = 매출인식일 · 같은 파일 다시 안 읽음 · 칸 바뀜 = 오류 목록(매 실행)")


def t7_public_web():
    print("[T7] S3 공개 웹 — 일반 연결(가짜 fetch) · 날짜·지문 비교 · 매주 주기 · 못 읽으면 오류")
    page = "<html><script>x=1</script><body><h1>판매수수료</h1><p>{}</p><p>" + "설명 " * 80 + "</p></body></html>"
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        assert SRC.due_public(base, D("2026-11-18")) == ["MD-FEE-TABLE", "MD-RG-ZEROCOST", "MD-RG-MAIN"]
        assert SRC.check_public(base, "MD-FEE-TABLE", D("2026-11-17"), lambda url: page.format("기준일 2019.11.25")) == []
        snap = json.loads((base / "자료출처" / "MD-FEE-TABLE" / "2026-11-17.json").read_text(encoding="utf-8"))
        assert snap["날짜"] == ["2019.11.25"] and "x=1" not in snap["글자"], snap
        assert SRC.check_public(base, "MD-FEE-TABLE", D("2026-11-18"), lambda url: page.format("기준일 2019.11.25")) == []
        h = SRC.check_public(base, "MD-FEE-TABLE", D("2026-11-19"), lambda url: page.format("기준일 2026년 12월 1일"))
        assert len(h) == 1 and "2019.11.25" in h[0]["이전 값"] and "2026년12월1일" in h[0]["새 값"], h
        SRC.check_public(base, "MD-RG-MAIN", D("2026-11-10"), lambda url: page.format("2026-11-01"))
        assert "MD-RG-MAIN" not in SRC.due_public(base, D("2026-11-16")) and "MD-RG-MAIN" in SRC.due_public(base, D("2026-11-17"))
        assert "MD-FEE-TABLE" not in SRC.due_public(base, D("2026-11-19"))                  # 오늘 이미 읽음
        for bad in ("<html><body>loading</body></html>", page.format("날짜 없음")):
            try:
                SRC.check_public(base, "MD-RG-ZEROCOST", D("2026-11-19"), lambda url, b=bad: b)
                raise AssertionError("못 읽은 페이지가 조용히 넘어감")
            except SiteChangedError:
                pass
    ok("스크립트 글자 뺌 · 같은 글자 = 이력 0 · 날짜 바뀜 = 이력 1(이전·새 날짜) · 매주 = 7일 뒤 · 빈·날짜 없는 페이지 = 오류")


def t8_registry():
    print("[T8] 등록표 — '안 받음' 58행이 모두 출처(방법) 또는 받지 않는 사유를 가짐 · 구현 단계 = S1~S3")
    covered = {n for s in SRC.SOURCES.values() for n in s["순번"]} | set(SRC.NOT_SOURCED)
    assert covered == set(range(1, SRC.ROWS + 1)), sorted(set(range(1, SRC.ROWS + 1)) ^ covered)
    assert not set(SRC.NOT_SOURCED) & {n for s in SRC.SOURCES.values() for n in s["순번"]}
    for sid, s in SRC.SOURCES.items():
        assert {"순번", "방법", "주기", "단계", "설명"} <= set(s), sid
        assert (s["방법"] == "M-D") == ("주소" in s), sid
    assert {sid for sid, s in SRC.SOURCES.items() if SRC.implemented(s["단계"])} == {
        "ME-RG-CATEGORY", "ME-WING-RATE", "MD-FEE-TABLE", "MD-RG-ZEROCOST", "MD-RG-MAIN", "ME-AD-DAILY"}
    ok("58행 빈틈·겹침 없음 · M-D 만 주소 · 구현 6출처(S1·S2·S3)")


def main():
    t1_cost_reports()
    t2_live()
    t3_ads_milk()
    t4_write()
    t4b_scan_budget()
    t5_ads_progress_refetch()
    t6_originals()
    t7_public_web()
    t8_registry()
    t9_review_cumulative()
    print("받기 의심·자료 출처 대조 오프라인 검증 통과")


if __name__ == "__main__":
    main()
