"""통합 판매현황(첫 시트 '통합판매현황') 오프라인 검증 — 로그인·쿠팡 호출 없음(결정적). SSOT=designs/SALES_SUMMARY.md.

목표(소유자 2026-10-15): 위탁계정 전체의 계정별·상품별 판매수량·판매금액(윙/로켓그로스 구분)을 전일·주간(월~일)·월별
세로 3구역으로 결과 파일 첫 시트에 매일 다시 그린다. 기존 시트는 한 칸씩 오른쪽.

    python tools/verify_sales_summary_offline.py
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

from coupang_analytics import config  # noqa: E402
from coupang_analytics import sales_history as SH  # noqa: E402
from coupang_analytics import sales_summary as SS  # noqa: E402
from coupang_analytics import workbook_sales as WS  # noqa: E402
from coupang_analytics.report import OptionMetric  # noqa: E402
from coupang_analytics.workbook import OutputWorkbook  # noqa: E402

Y = date(2026, 10, 14)   # 전일(수요일) — 이번 주 월요일 = 10-12


def ok(msg):
    print(f"  ✔ {msg}")


def _m(vid, name, reg, qty, gmv, opt="기본"):
    return OptionMetric(vid, name, opt, "i", 0, qty, 0, registration_type=reg, gmv=gmv, orders=qty)


def t1_plan():
    print("[T1] 기간 조회 계획 — 처음 = 1월~이번 달 + 최근 8주, 마감된 기간은 다시 안 함, 이번 달·주는 매일 다시")
    plan = SS.plan_periods({}, Y)
    keys = [k for k, _f, _t in plan]
    months = [k for k in keys if k.startswith("M:")]
    weeks = [k for k in keys if k.startswith("W:")]
    assert months == [f"M:2026-{m:02d}" for m in range(1, 11)], months
    assert weeks[0] == "W:2026-10-12" and weeks[-1] == "W:2026-08-24" and len(weeks) == 8, weeks
    rng = {k: (f, t) for k, f, t in plan}
    assert rng["M:2026-10"] == ("2026-10-01", "2026-10-14") and rng["M:2026-02"] == ("2026-02-01", "2026-02-28")
    assert rng["W:2026-10-12"] == ("2026-10-12", "2026-10-14") and rng["W:2026-10-05"] == ("2026-10-05", "2026-10-11")
    done = {k: {"조회기간": [f, t]} for k, f, t in plan}               # 전부 받음(이번 달·주는 10-14 까지)
    again = SS.plan_periods(done, date(2026, 10, 15))
    assert [k for k, _f, _t in again] == ["M:2026-10", "W:2026-10-12"], again   # 마감된 것은 다시 안 함
    assert SS.plan_periods(done, Y) == [], "같은 날 다시 돌면 조회 없음"
    ok("1~10월 10개 + 8주 · 2월 말일 · 이번 주 = 월~어제 · 다음 날엔 이번 달·주만 다시")


def t2_record_period():
    print("[T2] 기간 기록 저장 — 쿠팡 합계 그대로·옵션별·키별 교체·불러오기")
    with tempfile.TemporaryDirectory() as d:
        SH.record_period(d, "a1", "M:2026-10", "2026-10-01", "2026-10-14",
                         {"v1": _m("v1", "캠핑테이블", "RFM", 3, 30000)})
        SH.record_period(d, "a1", "M:2026-10", "2026-10-01", "2026-10-15",
                         {"v1": _m("v1", "캠핑테이블", "RFM", 4, 40000)})
        data = SH.load_periods(d)
        rec = data["a1"]["M:2026-10"]
        assert rec["조회기간"] == ["2026-10-01", "2026-10-15"] and rec["합계"]["판매금액"] == 40000, rec
        assert rec["옵션"]["v1"]["구분"] == "로켓그로스" and rec["옵션"]["v1"]["판매수량"] == 4
        assert not list(Path(d, SH.PERIOD_DIRNAME).glob("*.tmp")), "임시 파일 남지 않음"
        SH.record(d, "a1", "2026-10-14", "2026-10-14", {"v1": _m("v1", "캠핑테이블", "RFM", 1, 9000)})
        assert SH.load_daily(d)["a1"]["2026-10-14"]["합계"]["판매수량"] == 1
    ok("같은 키는 교체·조회기간 기록·구분 윙/로켓그로스·일별도 같은 방식으로 불러옴")


def _fixture(d):
    SH.record(d, "a1", "2026-10-14", "2026-10-14", {
        "v1": _m("v1", "캠핑테이블", "RFM", 2, 20000, "블랙"), "v2": _m("v2", "캠핑테이블", "RFM", 1, 10000, "화이트"),
        "v3": _m("v3", "허리보호대", "NORMAL", 1, 5000), "v4": _m("v4", "안팔린상품", "RFM", 0, 0)})
    SH.record_period(d, "a1", "W:2026-10-12", "2026-10-12", "2026-10-14", {"v1": _m("v1", "캠핑테이블", "RFM", 5, 50000)})
    SH.record_period(d, "a1", "M:2026-10", "2026-10-01", "2026-10-14", {
        "v1": _m("v1", "캠핑테이블", "RFM", 9, 90000), "v3": _m("v3", "허리보호대", "NORMAL", 2, 10000)})
    SH.record_period(d, "a1", "M:2026-09", "2026-09-01", "2026-09-30", {})          # 판매 0 인 달(미수집 아님)


def t3_build():
    print("[T3] 집계 — 계정→상품(옵션 합산)·윙/로켓그로스 줄 나눔·판매 0 상품 생략·미수집 ≠ 0·전체 합계")
    with tempfile.TemporaryDirectory() as d:
        _fixture(d)
        s = SS.build(SH.load_daily(d), SH.load_periods(d), {"a1": "에벤에셀 (a1)", "a2": "니코에이블 (a2)"}, Y)
    day = s.sections[0]
    assert [c.key for c in day.cols] == ["D:2026-10-14"]
    a1 = next(b for b in day.accounts if b.aid == "a1")
    rows = {(r.product, r.kind): r.values["D:2026-10-14"] for r in a1.rows}
    assert rows == {("캠핑테이블", "로켓그로스"): (3, 30000), ("허리보호대", "윙"): (1, 5000)}, rows
    assert a1.total["D:2026-10-14"] == (4, 35000)
    a2 = next(b for b in day.accounts if b.aid == "a2")
    assert a2.total["D:2026-10-14"] is None and a2.rows == [], "데이터 없는 계정 = 미수집(None)"
    assert day.total["D:2026-10-14"] == (4, 35000) and day.missing["D:2026-10-14"] == 1
    week, month = s.sections[1], s.sections[2]
    assert [c.key for c in week.cols][:2] == ["W:2026-10-12", "W:2026-10-05"] and len(week.cols) == 8
    assert [c.key for c in month.cols][:2] == ["M:2026-10", "M:2026-09"] and month.cols[-1].key == "M:2026-01"
    m1 = next(b for b in month.accounts if b.aid == "a1")
    assert m1.total["M:2026-09"] == (0, 0) and m1.total["M:2026-08"] is None, "판매 0 달 = 0 · 안 받은 달 = 미수집"
    assert week.total["W:2026-10-05"] == (0, 0) and week.missing["W:2026-10-05"] == 2
    ok("옵션 합산 3개·30,000원 · 윙 줄 따로 · a2 미수집 · 9월 0 ≠ 8월 미수집 · 최신 칸이 왼쪽")


def _wb_with_accounts(path):
    wb = OutputWorkbook.empty()
    for biz, aid in (("에벤에셀", "a1"), ("니코에이블", "a2")):
        wb.ensure_account(biz)
        wb.set_account_id(biz, aid)
        wb.ensure_product_block(biz, f"{biz} 상품", config.KIND_CONTRACT, ["kw"], registered=f"{biz} 상품")
        wb.ensure_date(biz, "2026-10-14")
    wb.apply_style()
    wb.save(path)
    return wb


def t4_sheet():
    print("[T4] 결과 파일 첫 시트 — 통합판매현황 맨 앞·계정 목록 두 번째·사업자 시트로 오인 안 됨·다시 그려도 1개")
    with tempfile.TemporaryDirectory() as d:
        _fixture(d)
        path = Path(d) / "m.xlsx"
        wb = _wb_with_accounts(path)
        before = wb.account_sheets()
        msg = WS.refresh_sales_sheet(wb, d, today=date(2026, 10, 15))
        wb.apply_style()
        WS.refresh_sales_sheet(wb, d, today=date(2026, 10, 15))           # 두 번 그려도 시트 1개
        wb.apply_style()
        wb.save(path)
        wb2 = OutputWorkbook.load(path)
        names = wb2.wb.sheetnames
        assert names[0] == WS.SALES_SHEET and names[1] == "계정 목록", names
        assert names.count(WS.SALES_SHEET) == 1
        assert wb2.account_sheets() == before, (wb2.account_sheets(), before)
        assert wb2.wb.active.title == WS.SALES_SHEET, "파일을 열면 통합판매현황"
        cells = [[c for c in r] for r in wb2.wb[WS.SALES_SHEET].iter_rows(values_only=True)]
        flat = [v for r in cells for v in r if v is not None]
        assert "1. 전일 10.14" in flat and "2. 주간 (월~일)" in flat and "3. 월별" in flat, flat[:20]
        tot = next(r for r in cells if r[0] == "전체 합계")
        assert tot[3] == 4 and tot[4] == 35000, tot
        assert any(r[0] == "니코에이블 (a2)" and r[3] == "미수집" for r in cells), "미수집 계정 표시"
        assert any(r[1] == "캠핑테이블" and r[2] == "로켓그로스" and r[4] == 30000 for r in cells)
        assert "기록" in msg or "갱신" in msg, msg
    ok("첫 시트·계정 목록 두 번째·활성 시트·사업자 시트 목록 불변·전체 합계 4개 35,000원·미수집 표시")


def t5_gsheet():
    print("[T5] 결과 구글시트 — 통합판매현황을 만들고 맨 앞(index 0)으로·사업자 미러링 대상 아님")
    from coupang_analytics import gsheet_stats as GS
    with tempfile.TemporaryDirectory() as d:
        _fixture(d)
        wb = _wb_with_accounts(Path(d) / "m.xlsx")
        WS.refresh_sales_sheet(wb, d, today=date(2026, 10, 15))
        wb.apply_style()

    class _Client:
        def __init__(self):
            self.reqs, self.made = [], []

        def ensure_sheets(self, titles):
            self.made += titles
            return {t: i + 10 for i, t in enumerate(titles)}

        def ensure_sheet(self, title):
            self.made.append(title)
            return 99

        def batch_update(self, reqs):
            self.reqs += reqs
    c = _Client()
    GS.push_statistics(c, wb)
    assert WS.SALES_SHEET not in c.made, "사업자 시트로 미러링 안 함"
    WS.push_sales_sheet(c, wb)
    moves = [r for r in c.reqs if "updateSheetProperties" in r
             and r["updateSheetProperties"]["properties"].get("index") == 0]
    assert moves and moves[-1]["updateSheetProperties"]["properties"]["sheetId"] == 99, moves
    assert any("updateCells" in r for r in c.reqs)
    ok("ensure_sheet → 값·서식 교체 → index 0 이동 · 사업자 미러링 목록엔 없음")


def t6_collect():
    print("[T6] ① 판매수집 기간 조회 — 계획한 기간만 조회·저장 · 조회 실패면 그 계정 나머지 중단(로그)")
    from coupang_analytics import collector
    from coupang_analytics import pipeline_sales as PS
    calls, logs = [], []

    def fake(page, f, t, log=None):
        calls.append((f, t))
        if len(calls) == 3:
            raise collector.SalesFetchError("status=500")
        return {"v1": _m("v1", "캠핑테이블", "RFM", 1, 1000)}
    orig = (collector.fetch_sales_details, PS.time.sleep)
    try:
        collector.fetch_sales_details, PS.time.sleep = fake, (lambda s: None)
        with tempfile.TemporaryDirectory() as d:
            PS._record_sales_periods("PAGE", "a1", d, logs.append, yesterday=Y)
            got = SH.load_periods(d).get("a1", {})
    finally:
        collector.fetch_sales_details, PS.time.sleep = orig
    assert len(calls) == 3 and len(got) == 2, (calls, got)
    assert any("중단" in m for m in logs), logs
    logs.clear()

    def broken(page, f, t, log=None):          # 핀 A 가 잡은 결함: 판매분석 오류가 아닌 브라우저 오류도 수집을 막으면 안 됨
        raise RuntimeError("Target page, context or browser has been closed")
    try:
        collector.fetch_sales_details = broken
        with tempfile.TemporaryDirectory() as d:
            PS._record_sales_periods("PAGE", "a1", d, logs.append, yesterday=Y)   # 예외가 밖으로 나오지 않음
    finally:
        collector.fetch_sales_details = orig[0]
    assert any("RuntimeError" in m for m in logs), logs
    ok("기간 2개 저장 · 3번째 실패에서 그 계정 중단 · 브라우저 오류도 ① 수집을 막지 않음(로그)")


def main() -> int:
    t1_plan()
    t2_record_period()
    t3_build()
    t4_sheet()
    t5_gsheet()
    t6_collect()
    print("통합 판매현황 오프라인 검증 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
