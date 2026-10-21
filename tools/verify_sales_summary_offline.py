"""통합 판매현황(첫 시트 '통합판매현황') 오프라인 검증 — 로그인·쿠팡 호출 없음(결정적). SSOT=designs/SALES_SUMMARY.md.

목표(소유자 2026-10-15·2026-10-21): 계정별·상품별 판매수량·판매금액(윙/로켓그로스 구분)을 결과 파일 첫 시트에 매일
다시 그린다. 위 = 대시보드(①요약·②월별·③주간 8주·④일별 31일 차트·⑤계정 순위·⑥상품 상위 20 열지도), 아래 = 일별 상세표
(최근 31일·최신이 왼쪽). 집계 기준 = 관리 상품(결과 사업자 시트 블록 VID). 일별 기록은 2026-04-01부터 계정당 하루 60일씩(D-097)
최근부터 거꾸로 소급. '지난달 같은 기간' = 이번 달 1~N일 vs 지난달 1~N일(일별).

    python tools/verify_sales_summary_offline.py
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics import config  # noqa: E402
from coupang_analytics import sales_dashboard as SD  # noqa: E402
from coupang_analytics import sales_history as SH  # noqa: E402
from coupang_analytics import sales_summary as SS  # noqa: E402
from coupang_analytics import workbook_sales as WS  # noqa: E402
from coupang_analytics import workbook_sales_dash as WD  # noqa: E402
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
    print("[T3] 상세표 — 일별 31칸·최신이 왼쪽·계정→상품(옵션 합산)·윙/로켓그로스 줄 나눔·판매 0 상품 생략·미수집 ≠ 0")
    with tempfile.TemporaryDirectory() as d:
        _fixture(d)
        s = SS.build(SH.load_daily(d), {"a1": "에벤에셀 (a1)", "a2": "니코에이블 (a2)"}, Y)
    assert len(s.sections) == 1, "주간·월별 구역은 상세표에서 제거(대시보드가 대신)"
    day = s.sections[0]
    keys = [c.key for c in day.cols]
    assert len(keys) == 31 and keys[0] == "D:2026-10-14" and keys[-1] == "D:2026-09-14", (keys[0], keys[-1])
    a1 = next(b for b in day.accounts if b.aid == "a1")
    rows = {(r.product, r.kind): r.values["D:2026-10-14"] for r in a1.rows}
    assert rows == {("캠핑테이블", "로켓그로스"): (3, 30000), ("허리보호대", "윙"): (1, 5000)}, rows
    assert a1.total["D:2026-10-14"] == (4, 35000) and a1.total["D:2026-10-13"] is None, "기록 없는 날 = 미수집"
    a2 = next(b for b in day.accounts if b.aid == "a2")
    assert a2.total["D:2026-10-14"] is None and a2.rows == [], "데이터 없는 계정 = 미수집(None)"
    assert day.total["D:2026-10-14"] == (4, 35000) and day.missing["D:2026-10-14"] == 1
    ok("31칸(10.14 → 09.14) · 옵션 합산 3개·30,000원 · 윙 줄 따로 · a2 미수집 · 기록 없는 날 미수집")


def _wb_with_accounts(path):
    wb = OutputWorkbook.empty()
    for biz, aid, vids in (("에벤에셀", "a1", ["v1", "v2", "v3", "v4"]), ("니코에이블", "a2", ["v9"])):
        wb.ensure_account(biz)
        wb.set_account_id(biz, aid)
        wb.ensure_product_block(biz, f"{biz} 상품", config.KIND_CONTRACT, ["kw"], registered=f"{biz} 상품")
        wb.set_product_vids(biz, f"{biz} 상품", vids)          # 관리 상품 = 블록 VID(집계 기준)
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
        from coupang_analytics import login_today as LT
        LT.record_failure("a2", LT.PW_WRONG, out_dir=d)                  # 오늘 a2 로그인 비밀번호 오류(D-068)
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
        assert any(str(v).startswith("① 요약") for v in flat) and any(str(v).startswith("상세 — 일별") for v in flat)
        assert not any(str(v).startswith(("2. 주간", "3. 월별")) for v in flat), "옛 주간·월별 구역 없음"
        i = next(i for i, r in enumerate(cells) if r[0] == "전체 합계")
        assert tuple(cells[i][2:4]) == ("수량", 4) and tuple(cells[i + 1][2:4]) == ("금액", 35000), cells[i:i + 2]   # 2줄
        assert any(r[0] == "니코에이블 (a2)" and r[3] == "미수집" for r in cells), "미수집 계정 표시"
        subs = {r[0]: r[1] for r in cells if r[1] and str(r[1]).startswith("소계")}
        assert subs == {"니코에이블 (a2)": "소계 — ⚠ 로그인 비밀번호 오류", "에벤에셀 (a1)": "소계"}, subs   # 소유자 2026-10-16
        j = next(i for i, r in enumerate(cells) if r[1] == "캠핑테이블")
        assert tuple(cells[j][2:4]) == ("로켓그로스·수량", 3) and tuple(cells[j + 1][2:4]) == ("로켓그로스·금액", 30000), \
            "상품 1건 = 수량 줄·금액 줄 · 구분 = 판매방식·수량/금액"
        assert not any(str(v).startswith("⑥") for v in flat), "⑥ 상품 열지도 없음"
        sws = wb2.wb[WS.SALES_SHEET]
        assert sws.freeze_panes == "A3", f"열 고정 없음(행 1~2만): {sws.freeze_panes}"
        hrow = next(r for r in cells if r[0] == "계정" and r[1] == "상품")
        assert len([v for v in hrow[3:] if v]) == 31 and hrow[3] == "10.14", "날짜 1칸·31일·최신 왼쪽"
        from openpyxl.utils import get_column_letter
        ws_w = {sws.column_dimensions[get_column_letter(c)].width for c in range(4, 4 + 31)}
        assert len(ws_w) == 1, f"날짜 칸 너비 모두 같음: {ws_w}"
        # 계정 블록(소유자 2026-10-21·D-102): 소계+상품 = 같은 색 계열 · 계정마다 번갈아 · 블록 바깥 굵은 테두리
        subs_r = [i + 1 for i, r in enumerate(cells) if r[1] and str(r[1]).startswith("소계")]
        fills = [sws.cell(rr, 4).fill.fgColor.rgb[-6:] for rr in subs_r]
        assert len(set(fills)) == 2, f"계정마다 다른 색(번갈아): {fills}"
        prod_r = j + 1                                                   # 에벤에셀 캠핑테이블 첫 줄(1-기준)
        a1_sub = next(rr for rr in subs_r if cells[rr - 1][0] == "에벤에셀 (a1)")
        pair = {"D9E2F3": "EEF3FB", "E2EFDA": "F3F9EF"}
        assert pair[sws.cell(a1_sub, 4).fill.fgColor.rgb[-6:]] == sws.cell(prod_r, 4).fill.fgColor.rgb[-6:], \
            "같은 계정의 소계·상품 = 같은 색 계열"
        last_c = 3 + 31
        assert sws.cell(a1_sub, 1).border.top.style == "medium" and sws.cell(a1_sub, 1).border.left.style == "medium"
        nxt = [rr for rr in subs_r if rr > a1_sub]
        end = nxt[0] - 1 if nxt else max(i + 1 for i, r in enumerate(cells) if r[2])   # 블록 끝 = 다음 소계 직전·마지막 줄
        assert sws.cell(end, last_c).border.bottom.style == "medium" and             sws.cell(end - 2, last_c).border.bottom.style != "medium", "블록 끝만 굵은 아래 테두리"
        assert sws.cell(a1_sub, last_c).border.right.style == "medium" and \
            sws.cell(a1_sub + 1, 5).border.top.style != "medium", "바깥만 굵게·안쪽은 가는 선"
        kpi = next(r for r in cells if str(r[0]).startswith("전일 "))
        assert (kpi[1], kpi[2]) == (35000, 4), f"대시보드 전일 = 상세 전체 합계: {kpi}"
        assert "기록" in msg or "갱신" in msg, msg
    ok("첫 시트·계정 목록 두 번째·사업자 시트 불변·전체 합계 2줄(4개/35,000원)·상품 2줄·미수집 사유·⑥ 없음·열 고정 없음·날짜 칸 같은 너비")


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

        def chart_ids(self, title):
            return [501, 502] if title == WS.SALES_SHEET else []

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
    bad = _merges_across_freeze(c.reqs)   # 라이브 2026-10-15 400 "You can't merge frozen and non-frozen columns"
    assert not bad, f"틀고정 경계를 가로지르는 병합(구글시트 400): {bad[:3]}"
    kinds = [next(iter(r)) for r in c.reqs]
    dels = [r["deleteEmbeddedObject"]["objectId"] for r in c.reqs if "deleteEmbeddedObject" in r]
    first_cells = kinds.index("updateCells", len(kinds) - kinds[::-1].index("deleteEmbeddedObject"))
    assert dels == [501, 502], "옛 차트를 지움"
    charts = [r["addChart"]["chart"] for r in c.reqs if "addChart" in r]
    assert len(charts) == 4 and kinds.index("addChart") > first_cells, "값을 쓴 뒤 차트 4개 다시 추가"
    assert [ch["spec"]["basicChart"]["chartType"] for ch in charts] == ["COLUMN", "LINE", "COLUMN", "BAR"]
    grid = [r["updateSheetProperties"]["properties"]["gridProperties"] for r in c.reqs if "updateSheetProperties" in r
            and r["updateSheetProperties"]["properties"].get("sheetId") == 99
            and "gridProperties" in r["updateSheetProperties"]["properties"]]
    assert grid and grid[-1]["frozenColumnCount"] == 0, f"열 고정 없음(고정 구역에 차트가 묻힘): {grid}"
    px = {r["updateDimensionProperties"]["range"]["startIndex"]: r["updateDimensionProperties"]["properties"]["pixelSize"]
          for r in c.reqs if "updateDimensionProperties" in r and r["updateDimensionProperties"]["range"].get("sheetId") == 99
          and "pixelSize" in r["updateDimensionProperties"]["properties"]
          and r["updateDimensionProperties"]["range"]["dimension"] == "COLUMNS"}
    W = sum(px[i] for i in range(10))                                      # 대시보드 폭 = A~J 실제 열 픽셀 합
    edges = []
    for ch in charts:
        pos = ch["position"]["overlayPosition"]
        left = sum(px[i] for i in range(pos["anchorCell"]["columnIndex"])) + pos.get("offsetXPixels", 0)
        edges.append((left, left + pos["widthPixels"]))
    (l2, r2), (l3, r3), (l4, r4), (l5, r5) = edges
    assert l2 == l4 == l5 == 0 and abs(r3 - W) <= 1 and abs(r4 - W) <= 1 and abs(r5 - W) <= 1, (W, edges)
    assert 0 < l3 - r2 < 40 and abs((r2 - l2) - (r3 - l3)) <= 1, f"②③ = W 를 반씩·사이 간격 일정: {edges}"
    assert all(ch["spec"]["hiddenDimensionStrategy"] == "SHOW_ALL" for ch in charts), "숨긴 열 자료도 그림"
    hid = [r["updateDimensionProperties"] for r in c.reqs if "updateDimensionProperties" in r
           and r["updateDimensionProperties"]["properties"].get("hiddenByUser")]
    cols = {ch["spec"]["basicChart"]["domains"][0]["domain"]["sourceRange"]["sources"][0]["startColumnIndex"]
            for ch in charts}
    assert hid and all(any(h["range"]["startIndex"] <= ci < h["range"]["endIndex"] for h in hid) for ci in cols), \
        "차트 자료 = 숨긴 열"
    assert kinds[-1] == "updateSheetProperties", "index 0 이동이 마지막"
    with tempfile.TemporaryDirectory() as d:                               # 계정 26개 — ⑤ 막대가 아래 표를 덮지 않음
        big = _many_accounts_wb(d)
    cb = _Client()
    WS.push_sales_sheet(cb, big)
    bws = big.wb[WS.SALES_SHEET]
    for ch in (r["addChart"]["chart"] for r in cb.reqs if "addChart" in r):
        pos = ch["position"]["overlayPosition"]
        row = pos["anchorCell"]["rowIndex"] + 1
        room = _free_rows_below(bws, row) * 20                             # 구글 실제 행 높이 20px(10-21 실측)
        assert pos.get("offsetYPixels", 0) + pos["heightPixels"] <= room, \
            f"차트가 아래 내용을 덮음(구글): {ch['spec']['title']} 높이 {pos['heightPixels']} > 빈 행 {room}px"
    ok("옛 차트 삭제 → 값·서식 → 숨긴 열·차트 4개 → index 0 · 열 고정 0 · ②③ W 반씩·④⑤ = W(열 픽셀 합) · 병합 400 없음")


def _free_rows_below(ws, row: int) -> int:
    """row 부터 A~J 에 내용이 처음 나오는 행 직전까지 행 수 — 차트가 이 안에 들어가야 아래 표를 덮지 않음."""
    r = row
    while r <= ws.max_row and not any(ws.cell(r, c).value not in (None, "") for c in range(1, 11)):
        r += 1
    return r - row


def _many_accounts_wb(d):
    """계정 26개(⑤ 막대가 길어지는 경우 — 10-21 구글 실측 겹침 재현): 계정마다 오늘 하루 판매 1건."""
    wb = OutputWorkbook.empty()
    for i in range(26):
        biz, aid = f"사업자{i:02d}", f"acc{i:02d}"
        wb.ensure_account(biz)
        wb.set_account_id(biz, aid)
        wb.ensure_product_block(biz, f"{biz} 상품", config.KIND_CONTRACT, ["kw"], registered=f"{biz} 상품")
        wb.set_product_vids(biz, f"{biz} 상품", [f"v{i}"])
        SH.record(d, aid, "2026-10-20", "2026-10-20", {f"v{i}": _m(f"v{i}", "상품", "RFM", 1, 1000 * (i + 1))})
    WS.refresh_sales_sheet(wb, d, today=date(2026, 10, 21))
    return wb


def _merges_across_freeze(reqs: list) -> list:
    """구글시트는 고정/비고정 행·열에 걸친 병합을 거부(400) — 같은 시트의 틀고정 값으로 병합 범위 검사."""
    frozen = {}
    for r in reqs:
        g = r.get("updateSheetProperties", {}).get("properties", {})
        if "gridProperties" in g:
            gp = g["gridProperties"]
            frozen[g["sheetId"]] = (gp.get("frozenRowCount", 0), gp.get("frozenColumnCount", 0))
    bad = []
    for r in reqs:
        m = r.get("mergeCells", {}).get("range")
        if not m:
            continue
        fr, fc = frozen.get(m["sheetId"], (0, 0))
        if m["startColumnIndex"] < fc < m["endColumnIndex"] or m["startRowIndex"] < fr < m["endRowIndex"]:
            bad.append(m)
    return bad


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


def t7_backfill_plan():
    print("[T7] 일별 소급 계획 — 2026-04-01까지 최근부터 거꾸로·있는 날 빼고·계정당 하루 최대 60일(오늘 받은 것 포함·D-097)")
    y = date(2026, 10, 20)
    have = {"2026-10-20": {"수집": "2026-10-21T18:05:00"}, "2026-10-18": {"수집": "2026-10-19T18:05:00"}}
    plan = SS.plan_backfill(have, y, today=date(2026, 10, 21))
    assert plan[:3] == ["2026-10-19", "2026-10-17", "2026-10-16"] and len(plan) == 59, plan[:5]   # 오늘 1건 = 59
    assert plan == sorted(plan, reverse=True) and "2026-10-18" not in plan
    assert SS.plan_backfill({}, date(2026, 4, 3)) == ["2026-04-03", "2026-04-02", "2026-04-01"], "4/1 전은 안 함"
    full = {f"x{i}": {"수집": "2026-10-21T19:00:00"} for i in range(60)}
    assert SS.plan_backfill(full, y, today=date(2026, 10, 21)) == [], "오늘 60일 받았으면 내일"
    days = (y - SS.BACKFILL_FROM).days + 1
    assert days == 203 and -(-days // SS.BACKFILL_PER_DAY) == 4, days
    ok("10.19부터 거꾸로 59일(오늘 1건) · 있는 날 건너뜀 · 4/1 끝 · 하루 60일 상한 · 4/1~10/20 = 203일 → 약 4일")


def t8_backfill_collect():
    print("[T8] ① 일별 소급 — 같은 세션 하루씩 조회·저장 · 조회 사이 쉼 · 실패면 그 계정 소급 중단(비치명·로그)")
    from coupang_analytics import collector
    from coupang_analytics import pipeline_sales as PS
    calls, sleeps, logs = [], [], []

    def fake(page, f, t, log=None):
        calls.append((f, t))
        if len(calls) == 4:
            raise collector.SalesFetchError("status=500")
        return {"v1": _m("v1", "캠핑테이블", "RFM", 1, 1000)} if f.endswith("7") else {}
    orig = (collector.fetch_sales_details, PS.time.sleep)
    try:
        collector.fetch_sales_details, PS.time.sleep = fake, sleeps.append
        with tempfile.TemporaryDirectory() as d:
            SH.record(d, "a1", "2026-10-19", "2026-10-19", {})
            PS._record_sales_backfill("PAGE", "a1", d, logs.append, yesterday=date(2026, 10, 20))
            got = SH.load_daily(d)["a1"]
    finally:
        collector.fetch_sales_details, PS.time.sleep = orig
    assert [f for f, _t in calls] == ["2026-10-20", "2026-10-18", "2026-10-17", "2026-10-16"], calls
    assert all(f == t for f, t in calls), "하루 단위 조회"
    assert sorted(got) == ["2026-10-17", "2026-10-18", "2026-10-19", "2026-10-20"], sorted(got)
    assert got["2026-10-18"]["합계"]["판매금액"] == 0 and got["2026-10-17"]["합계"]["판매금액"] == 1000, \
        "판매 0 인 날도 기록(미수집과 구분)"
    assert len(sleeps) == 3 and all(1.0 <= x <= 2.5 for x in sleeps), sleeps
    assert any("중단" in m for m in logs) and any("일별 소급 3/" in m for m in logs), logs
    ok("어제부터 거꾸로·있는 날(10.19) 건너뜀 · 판매 0 날 기록 · 1~2.5초 쉼 · 4번째 실패에서 중단(3일 저장)")


def t9_scope():
    print("[T9] 관리 상품 기준 — 결과 사업자 시트 블록 VID(판매중지 포함)만 · 결과 파일에 없는 계정 제외")
    with tempfile.TemporaryDirectory() as d:
        wb = _wb_with_accounts(Path(d) / "m.xlsx")
        wb.set_product_vids("에벤에셀", "에벤에셀 상품", ["v1"])
        wb.ensure_product_block("에벤에셀", "옛 상품", config.KIND_CONTRACT, ["kw"], registered="옛 상품")
        wb.set_product_vids("에벤에셀", "옛 상품", ["v3"])
        wb.set_discontinued("에벤에셀", "옛 상품", True)
        managed = WS.managed_vids(wb)
    assert managed["a1"] == {"v1", "v3"} and managed["a2"] == {"v9"}, managed
    store = {"a1": {"2026-10-14": {"옵션": {"v1": {"판매금액": 1}, "v2": {"판매금액": 9}, "v3": {"판매금액": 2}}}},
             "zz": {"2026-10-14": {"옵션": {"v9": {}}}}}
    got = SS.scope(store, managed)
    assert set(got) == {"a1"} and set(got["a1"]["2026-10-14"]["옵션"]) == {"v1", "v3"}, got
    assert set(SS.scope(store, None)) == {"a1", "zz"}, "None = 거르지 않음"
    ok("a1 = v1 + 판매중지 v3 · 관리 안 하는 v2 제외 · 결과 파일에 없는 계정 zz 제외")


def _dash_fixture(d):
    """a1 = 9월 하루 1,000원·10월 하루 1,500원(관리 v1) + 관리 안 하는 vx 999원 · a2 = 9/1~10/15 하루 2,000원
    (10/16~ 미수집) · a1 1월 기간 합계 50,000원."""
    day = date(2026, 9, 1)
    while day <= date(2026, 10, 20):
        amt = 1000 if day.month == 9 else 1500
        SH.record(d, "a1", day.isoformat(), day.isoformat(),
                  {"v1": _m("v1", "캠핑테이블", "RFM", 1, amt), "vx": _m("vx", "남의상품", "NORMAL", 1, 999)})
        if day <= date(2026, 10, 15):
            SH.record(d, "a2", day.isoformat(), day.isoformat(), {"v2": _m("v2", "기저귀백팩", "NORMAL", 2, 2000)})
        day += timedelta(days=1)
    SH.record_period(d, "a1", "M:2026-01", "2026-01-01", "2026-01-31", {"v1": _m("v1", "캠핑테이블", "RFM", 5, 50000)})


def t10_dashboard():
    print("[T10] 대시보드 값 — 전일·지난주(그 전주 대비)·이번 달 누계(지난달 같은 기간 대비)·월별·주간·일별·계정 순위")
    y = date(2026, 10, 20)   # 화요일
    assert SD.prev_month_same(y) == (date(2026, 9, 1), date(2026, 9, 20))
    assert SD.prev_month_same(date(2026, 3, 31)) == (date(2026, 2, 1), date(2026, 2, 28)), "지난달이 짧으면 말일"
    assert SD.last_full_week(y) == date(2026, 10, 12) and SD.last_full_week(date(2026, 10, 18)) == date(2026, 10, 12)
    labels = {"a1": "에벤에셀 (a1)", "a2": "니코에이블 (a2)"}
    with tempfile.TemporaryDirectory() as d:
        _dash_fixture(d)
        managed = {"a1": {"v1"}, "a2": {"v2"}}
        daily, per = SS.scope(SH.load_daily(d), managed), SS.scope(SH.load_periods(d), managed)
    b = SD.build(daily, per, labels, y)
    k_day, k_week, k_month = b.kpis
    assert (k_day.amount, k_day.missing, b.missing_today) == (1500, 1, 1), k_day
    assert k_week.span == "10.12~10.18" and k_week.amount == 10500 and k_week.missing == 1, k_week
    assert k_week.change == 0.0, "그 전주 10.05~10.11 도 a1 10,500 (a2 는 이번 주 미수집이라 비교에서 뺌)"
    assert k_month.amount == 30000 and abs(k_month.change - 0.5) < 1e-9, k_month       # 30,000 vs 9/1~20 20,000
    assert "09.01~09.20" in k_month.basis
    months = {p.label: p for p in b.months}
    assert list(months)[0] == "1월" and list(months)[-1] == "10월" and len(months) == 10
    assert months["1월"].amount == 50000 and months["1월"].missing == 1, "1월 = 쿠팡 기간 합계(일별 없음)"
    assert months["9월"].amount == 30 * 1000 + 30 * 2000 and months["9월"].missing == 0
    assert months["10월"].partial and months["10월"].amount == 30000 and months["10월"].missing == 1
    assert months["5월"].amount == 0 and months["5월"].missing == 2, "자료 없는 달 = 미수집"
    assert [p.label for p in b.weeks][-1] == "10.12" and len(b.weeks) == 8
    assert len(b.days) == 31 and b.days[-1].label == "10.20" and b.days[0].label == "09.20", "일별 = 오래된 → 최신"
    assert b.days[-1].amount == 1500, "관리 안 하는 vx 999원 빠짐"
    r1, r2 = b.accounts
    assert (r1.aid, r1.amount, r1.week, r1.prev_week, r1.change) == ("a1", 30000, 10500, 10500, 0.0), r1
    assert (r2.aid, r2.amount, r2.week, r2.prev_week, r2.change) == ("a2", None, None, 14000, None), "미수집 = 맨 아래"
    assert not hasattr(b, "products"), "⑥ 상품 열지도 자료 없음"
    ok("전일 1,500 · 지난주 10,500(0%) · 이번 달 30,000(+50%) · 1월 기간합계 · 10월 진행 중 · 순위 a1(지난주 10,500·0%)·a2 미수집")


def t11_charts_persist():
    print("[T11] 엑셀 — 차트 4개(②③④⑤)·같은 왼쪽 끝·같은 폭 W·다시 열어도 유지 · ⑤ 전 계정 5칸 표·미수집 줄 · 10월 막대")
    from openpyxl.utils import get_column_letter
    with tempfile.TemporaryDirectory() as d:
        _dash_fixture(d)
        day = date(2026, 10, 1)
        while day <= date(2026, 10, 20):                                   # a3 = 이번 달 매일 받았지만 판매 0
            SH.record(d, "a3", day.isoformat(), day.isoformat(), {})
            day += timedelta(days=1)
        path = Path(d) / "m.xlsx"
        wb = _wb_with_accounts(path)
        wb.set_product_vids("에벤에셀", "에벤에셀 상품", ["v1"])
        wb.set_product_vids("니코에이블", "니코에이블 상품", ["v2"])
        wb.ensure_account("벅스")
        wb.set_account_id("벅스", "a3")
        wb.ensure_product_block("벅스", "벅스 상품", config.KIND_CONTRACT, ["kw"], registered="벅스 상품")
        wb.set_product_vids("벅스", "벅스 상품", ["v7"])
        WS.refresh_sales_sheet(wb, d, today=date(2026, 10, 21))
        ws = wb.wb[WS.SALES_SHEET]
        assert len(ws._charts) == 4
        specs = WD.read_specs(ws)
        data_cols = {c for sp in specs for c in [sp["cat"][2]] + [s[2] for s in sp["series"]]}
        assert all(ws.column_dimensions[get_column_letter(c)].hidden for c in data_cols), "차트 자료 = 숨긴 열"
        assert min(data_cols) > 3 + 31, "상세표 오른쪽"
        w_pt = sum(ws.column_dimensions[get_column_letter(c)].width * WD.XL_PT_PER_CHAR for c in range(1, 11))
        col_pt = [ws.column_dimensions[get_column_letter(c)].width * WD.XL_PT_PER_CHAR for c in range(1, 11)]
        edges = []
        for ch in ws._charts:                                              # 실제 붙은 차트의 anchor 로 계산
            f = ch.anchor._from
            left = (sum(col_pt[:f.col]) * 12700 + f.colOff) / 12700
            edges.append((round(left, 1), round(left + ch.anchor.ext.width / 12700, 1)))
        assert [e[0] for e in edges] == [0, edges[1][0], 0, 0] and all(abs(e[1] - w_pt) < 1 for e in edges[1:]), \
            f"모든 도식 = 같은 왼쪽 끝·오른쪽 끝 W({w_pt}pt): {edges}"
        months = {ws.cell(r, specs[0]["cat"][2]).value: (ws.cell(r, specs[0]["cat"][2] + 1).value,
                                                         ws.cell(r, specs[0]["cat"][2] + 2).value)
                  for r in range(specs[0]["cat"][0] + 1, specs[0]["cat"][1] + 1)}
        assert months["10월"] == (0, 30000) and months["9월"][0] == 90000 and months["5월"] == (None, None), \
            f"10월 = 진행 중(연한 막대)·자료 없는 달 = 빈칸: {months}"
        dc = specs[2]["cat"][2]
        days = {ws.cell(r, dc).value: (ws.cell(r, dc + 1).value, ws.cell(r, dc + 2).value)
                for r in range(specs[2]["cat"][0] + 1, specs[2]["cat"][1] + 1)}
        assert days["10.15"] == (3500, 0) and days["10.20"] == (0, 1500), f"일부 계정 미수집 날 = 회색 계열: {days}"
        wb.save(path)
        wb2 = OutputWorkbook.load(path)
        assert len(wb2.wb[WS.SALES_SHEET]._charts) == 4, "다시 열면 설정으로 다시 붙임"
        wb2.save(path)
        wb3 = OutputWorkbook.load(path)
        assert len(wb3.wb[WS.SALES_SHEET]._charts) == 4, "열고 저장을 거듭해도 4개"
        cells = list(wb3.wb[WS.SALES_SHEET].iter_rows(values_only=True))
    assert WD._val(SD.Point("x", 0, 0, missing=3), 3) is None, "모든 계정 자료 없음 = 빈칸(0 막대 아님)"
    with tempfile.TemporaryDirectory() as d:                               # 계정 26개 — 엑셀도 차트 아래 끝 ≤ 다음 표
        big = _many_accounts_wb(d)
    bws = big.wb[WS.SALES_SHEET]
    for ch in bws._charts:
        row = ch.anchor._from.row + 1
        room_pt = _free_rows_below(bws, row) * 15                          # 엑셀 기본 행 15~16.5pt — 작은 쪽으로
        assert ch.anchor.ext.height / 12700 <= room_pt, \
            f"차트가 아래 내용을 덮음(엑셀): 높이 {ch.anchor.ext.height / 12700:.0f}pt > 빈 행 {room_pt}pt"
    head = next(r for r in cells if r[0] == "계정" and r[1] == "상품")
    assert head[3:5] == ("10.20", "10.19") and head[3 + 30] == "09.20", "상세 = 최신이 왼쪽 31일·날짜 1칸"
    tot = next(r for r in cells if r[0] == "전체 합계")
    kpi = next(r for r in cells if str(r[0]).startswith("전일 "))
    i = cells.index(tot)
    assert cells[i + 1][3] == kpi[1] == 1500, (cells[i + 1][3], kpi[1])
    rh = next(r for r in cells if r[0] == "순위")
    assert [v for v in rh[:10] if v] == ["순위", "계정", "이번 달 누계(원)", "지난주(원)", "전주 대비"], rh[:10]
    k = cells.index(rh)
    rows = [(r[0], r[1], r[2], r[5]) for r in cells[k + 1:k + 4]]
    assert rows == [(1, "에벤에셀 (a1)", 30000, 10500), ("-", "벅스 (a3)", 0, 0), ("-", "니코에이블 (a2)", "미수집", "미수집")], \
        f"⑤ = 전 계정(판매 순 → 판매 0 → 미수집·소유자 2026-10-21): {rows}"
    assert specs[3]["cat"][1] - specs[3]["cat"][0] == 3, "⑤ 막대 차트도 전 계정"
    flat = [v for r in cells for v in r if isinstance(v, str)]
    assert not any(v.startswith("판매 없음") for v in flat), "판매 0 계정은 표에 나오므로 따로 줄 없음"
    assert "미수집 1계정: 니코에이블(자료 없음)" in flat, "미수집 = 이름(사유)"
    # 소유자 2026-10-21: 미수집 계정이 생기면 계정명을 괄호로(① 미수집 칸·비교 기준·⑤·상세 미수집 줄)
    assert "1 / 3 계정 (니코에이블)" in flat, [v for v in flat if "/ 3 계정" in v]
    assert any(v.endswith("미수집 1계정(니코에이블) 제외") for v in flat), [v for v in flat if "제외" in v]
    miss_row = next(r for r in cells if r[0] == "미수집 계정 수")
    assert miss_row[1].startswith("벅스 ") and "니코에이블 5일" in miss_row[1], f"상세 미수집 줄 = 이름·일수: {miss_row}"
    assert WD.paren(()) == "" and WD.paren(("유라이프", "반달컴퍼니")) == "(유라이프, 반달컴퍼니)", "없으면 괄호 없음"
    assert not any(v.startswith("⑥") for v in flat) and not any(set(v) <= set("▁▂▃▄▅▆▇█·") for v in flat if v)
    ok("차트 4개 · 왼쪽 0·오른쪽 W 일치 · ②③ 반씩 · 10월 진행 중 30,000(a2 빠진 날 있어 제외) · 미수집 날 회색 · ⑤ 전 계정(판매 0·미수집 포함)·미수집 줄 · 다시 열어도 4개")


def main() -> int:
    t1_plan()
    t2_record_period()
    t3_build()
    t4_sheet()
    t5_gsheet()
    t6_collect()
    t7_backfill_plan()
    t8_backfill_collect()
    t9_scope()
    t10_dashboard()
    t11_charts_persist()
    print("통합 판매현황 오프라인 검증 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
