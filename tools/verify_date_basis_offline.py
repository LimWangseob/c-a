"""결과 통계 시트 날짜 칸 = 판매일(D-368·D-369) 오프라인 검증 — 로그인·쿠팡·구글 호출 없음(결정적).

기대(설계 = DECISIONS D-368·D-369 · 분석 `output\\_설계_261119_날짜칸D-1\\분석_1단계.md` 3-5 a~g):
  B1 날짜 입구: 칸 = 판매일 = 지정일(column_dates(L) = (L, L, L)) · 실행일의 칸 = 실행일−1(01:30 실행이어도 전날)
  B2 옛 기준 마스터(칸 = 판매일+1) → 새 판 첫 실행 때 한 번 하루 당김: 백업 먼저 · 사업자 시트 라벨 −1·값 그대로 ·
     `_수집스탬프` 2·3열 −1 · `_순위묶음` 시작일(B1·D1)·배정일 −1 · 숨긴 표시 `_날짜기준` · 판매분석_일별 대조가 +0 으로 뒤집힘
  B3 같은 실행일 = 같은 순위 묶음 · 지난 쉬는 칸(회색) 그대로(날짜 +1 로 맞춰 같음)
  B4 두 번 당김 방지: 표시 있으면 그대로 · 표시가 없어져도(구글시트 복원 흉내) 데이터로 '이미 새 기준' → 표시만
  B5 판정 못 함(판매분석 기록 없음) = 실행 중단(DateBasisError) · 마스터 그대로
  B6 옛 판 진행 파일 = 지우지 않고 보관 이름으로 · 이번 실행 중단(다시 실행하면 새 기준)
  B7 당긴 뒤 새 규칙 실행: 새 칸(어제) = 스탬프 '수집됨' 아님 · 칸 겹침 없음
  B8 날짜 칸 없는 마스터 = 표시만 · 마스터 없음 = 할 일 없음 · 계정목록 그로스재고 갱신일 = 실제 잰 날(최신 칸+1)

    python tools/verify_date_basis_offline.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
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
from coupang_analytics import date_basis as DB  # noqa: E402
from coupang_analytics import rank_schedule as RS  # noqa: E402
from coupang_analytics.pipeline import column_dates  # noqa: E402
from coupang_analytics.pipeline_paths import _master_path, _partial_path, _progress_path, run_day_column  # noqa: E402
from coupang_analytics.workbook import OutputWorkbook  # noqa: E402
from coupang_analytics.workbook_common import _RANKGRP_SHEET, _STAMP_SHEET  # noqa: E402

RUN_DAYS = [date(2026, 11, 1) + timedelta(days=i) for i in range(15)]   # 옛 판이 돈 날(11-01~11-15)
SHOPS = (("가게A", "acc1", "상품1", "111", "키워드1"), ("가게B", "acc2", "상품2", "222", "키워드2"))


def ok(msg):
    print(f"  ✔ {msg}")


def _qty(day: date, salt: int) -> int:
    return (day.day * 7 + salt) % 11 + 1          # 이웃한 날끼리 늘 다름(우연한 +0 일치 없음)


def _md(d: date) -> str:
    return d.strftime("%m.%d")


def _write_history(out: Path, aid: str, vid: str, salt: int, days) -> None:
    by_month: dict[str, dict] = {}
    for d in days:
        q = _qty(d, salt)
        by_month.setdefault(d.strftime("%Y-%m"), {})[d.isoformat()] = {
            "수집": "x", "합계": {"판매금액": q * 1000, "판매수량": q, "주문": q},
            "옵션": {vid: {"상품": "p", "옵션": "o", "구분": "로켓그로스", "판매금액": q * 1000, "판매수량": q, "주문": q}}}
    for m, rec in by_month.items():
        p = out / "판매분석_일별" / aid / f"{m}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")


def _old_master(out: Path, history: bool = True) -> None:
    """옛 기준 마스터 — 실행일 R 칸 = R−1 판매 · 순위는 격일로 일부만 · 스탬프 · 순위 묶음(3묶음 11-05 · 격일 11-12)."""
    wb = OutputWorkbook.empty()
    for salt, (biz, aid, prod, vid, kw) in enumerate(SHOPS):
        wb.ensure_account(biz)
        wb.set_account_id(biz, aid)
        wb.ensure_product_block(biz, prod, "로켓그로스", [kw])
        wb.set_product_vids(biz, prod, [vid])
        for i, r in enumerate(RUN_DAYS):
            wb.set_product_metric(biz, prod, config.M_SALES, _md(r), _qty(r - timedelta(days=1), salt))
            if (i + salt) % 2 == 0:
                wb.set_keyword_rank(biz, prod, kw, _md(r), 10 + i)
            wb.mark_sales_collected(aid, _md(r))
        if history:
            _write_history(out, aid, vid, salt, [r - timedelta(days=1) for r in RUN_DAYS])
    RS._write(wb, RS.RankPlan(start=date(2026, 11, 5), groups={"acc1": 0, "acc2": 1},
                              names={"acc1": "가게A", "acc2": "가게B"},
                              assigned={"acc1": "2026-11-05", "acc2": "2026-11-05"},
                              start2=date(2026, 11, 12), groups2={"acc1": 0, "acc2": 1},
                              assigned2={"acc1": "2026-11-12", "acc2": "2026-11-12"}))
    wb.save(_master_path(out))


def _cells(wb) -> dict:
    """{(사업자, 행, 날짜): 값} — 날짜 칸 값 전부(머리행·1행 제외)."""
    out = {}
    for biz in wb.account_sheets():
        ws, heads = wb.wb[biz], set(wb._date_rows.get(biz, []))
        for lbl, c in wb._date_col.get(biz, {}).items():
            d = DB._parse_date(lbl)
            for r in range(2, ws.max_row + 1):
                v = ws.cell(r, c).value
                if r not in heads and v not in (None, ""):
                    out[(biz, r, d)] = v
    return out


def _rest(wb) -> set:
    """{(사업자, 행, 날짜)} — 순위 쉬는 칸(회색 대상)."""
    out = set()
    for biz, _aid, prod, _vid, kw in SHOPS:
        ws = wb.wb[biz]
        row = wb._kw_row[(biz, prod, kw)]
        col2d = {c: DB._parse_date(lbl) for lbl, c in wb._date_col[biz].items()}
        out |= {(biz, r, col2d[c]) for r, c in RS.rest_cells(wb, ws, biz, prod, [row])}
    return out


def _hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def b1_entry():
    print("[B1] 날짜 입구 — 칸 = 판매일 = 지정일 · 실행일의 칸 = 실행일−1")
    assert column_dates("2026-11-19") == ("2026-11-19", "2026-11-19", "2026-11-19"), column_dates("2026-11-19")
    assert column_dates("2026-03-01") == ("2026-03-01", "2026-03-01", "2026-03-01")
    assert run_day_column(date(2026, 11, 20)) == date(2026, 11, 19)      # 11-20 01:30 실행 = 11.19 칸
    assert run_day_column(date(2026, 3, 1)) == date(2026, 2, 28)          # 달 경계
    ok("column_dates(L) = (L, L, L) · 11-20 실행 → 11.19 칸 · 03-01 → 02.28")


def b2_shift(tmp: Path):
    print("[B2] 옛 기준 마스터 → 첫 실행 때 하루 당김(백업 먼저·라벨·스탬프·묶음 시작일 −1·값 그대로)")
    out = tmp / "b2"
    out.mkdir()
    _old_master(out)
    before = OutputWorkbook.load(_master_path(out))
    st, plus1, zero = DB.judge(before, out)
    assert st == "old" and plus1 >= DB.MIN_VOTES and zero == 0, (st, plus1, zero)
    cells0, rest0 = _cells(before), _rest(before)
    msgs: list[str] = []
    res = DB.ensure_sales_date_basis(out, msgs.append)
    assert "당김" in res, res
    baks = list((out / "백업").glob("통계마스터_날짜당기기전_*.xlsx"))
    assert len(baks) == 1 and _cells(OutputWorkbook.load(baks[0])) == cells0, "백업 = 당기기 전 그대로"
    wb = OutputWorkbook.load(_master_path(out))
    for biz, *_ in SHOPS:
        labels = sorted(wb._date_col[biz], key=DB._parse_date)
        assert labels[0] == "10.31" and labels[-1] == "11.14" and len(labels) == 15, labels
    cells1 = _cells(wb)
    assert cells1 == {(b, r, d - timedelta(days=1)): v for (b, r, d), v in cells0.items()}, "값 그대로·날짜만 −1"
    ws = wb.wb[_STAMP_SHEET]
    for r in range(2, ws.max_row + 1):
        assert ws.cell(r, 2).value == "11.14", ws.cell(r, 2).value
        hist = ws.cell(r, 3).value.split(",")
        assert "11.15" not in hist and "10.31" in hist and len(hist) == 15, hist
    g = wb.wb[_RANKGRP_SHEET]
    assert (g.cell(1, 2).value, g.cell(1, 4).value) == ("2026-11-04", "2026-11-11"), (g.cell(1, 2).value, g.cell(1, 4).value)
    assert {g.cell(r, 4).value for r in range(3, g.max_row + 1)} == {"2026-11-04"}
    assert {g.cell(r, 6).value for r in range(3, g.max_row + 1)} == {"2026-11-11"}
    st2, plus1b, zero2 = DB.judge(wb, out)
    assert st2 == "marked" and DB.has_mark(wb)
    assert DB.votes(wb, out) == (0, plus1), DB.votes(wb, out)          # 대조가 +0 으로 뒤집힘
    assert any("당김" in m for m in msgs)
    ok(f"백업 1개 · 라벨 10.31~11.14 · 값 {len(cells1)}칸 그대로 · 스탬프 −1 · 묶음 시작 11-04/11-11 · 대조 +1 {plus1} → +0 {plus1}")
    return out, rest0


def b3_rank_same(out: Path, rest0: set):
    print("[B3] 같은 실행일 = 같은 묶음 · 지난 쉬는 칸 그대로")
    wb = OutputWorkbook.load(_master_path(out))
    rest1 = _rest(wb)
    assert rest0 and rest1 == {(b, r, d - timedelta(days=1)) for (b, r, d) in rest0}, (len(rest0), len(rest1))
    plan = RS.load_plan(wb)
    for run in (date(2026, 11, 16), date(2026, 11, 17)):
        old_turn = RS.RankPlan(start=date(2026, 11, 5), start2=date(2026, 11, 12)).turn(run)   # 옛 칸 = 실행일
        assert plan.turn(run_day_column(run)) == old_turn, (run, plan.turn(run_day_column(run)), old_turn)
    ok(f"쉬는 칸 {len(rest1)}개 날짜 −1 로 그대로 · 11-16·11-17 실행 묶음 차례 옛 판과 같음")


def b4_idempotent(out: Path, tmp: Path):
    print("[B4] 두 번 당김 방지 — 표시 있으면 그대로 · 표시 없어도 데이터로 '이미 새 기준'")
    h = _hash(_master_path(out))
    assert "이미" in DB.ensure_sales_date_basis(out, None)
    assert _hash(_master_path(out)) == h, "두 번째 실행 = 마스터 그대로"
    out2 = tmp / "b4"
    shutil.copytree(out, out2)
    wb = OutputWorkbook.load(_master_path(out2))
    del wb.wb[DB.MARK_SHEET]                       # 구글시트에서 되살린 마스터 흉내(숨긴 시트 없음)
    wb.save(_master_path(out2))
    cells = _cells(OutputWorkbook.load(_master_path(out2)))
    res = DB.ensure_sales_date_basis(out2, None)
    assert "표시" in res, res
    wb2 = OutputWorkbook.load(_master_path(out2))
    assert DB.has_mark(wb2) and _cells(wb2) == cells, "다시 당기지 않음"
    assert not list((out2 / "백업").glob("*날짜당기기전*xlsx"))[1:], "새 백업 안 만듦"
    ok("두 번째 = 그대로 · 표시 지운 사본 = 데이터 +0 우세 → 표시만(당김 없음)")


def b5_unknown(tmp: Path):
    print("[B5] 판정 못 함(판매분석 기록 없음) = 실행 중단 · 마스터 그대로")
    out = tmp / "b5"
    out.mkdir()
    _old_master(out, history=False)
    h = _hash(_master_path(out))
    try:
        DB.ensure_sales_date_basis(out, None)
    except DB.DateBasisError as e:
        assert "판정" in str(e), e
    else:
        raise AssertionError("증거 없으면 중단해야 함")
    assert _hash(_master_path(out)) == h and not (out / "백업").exists()
    ok("DateBasisError · 마스터·백업 없음")


def b6_progress(tmp: Path):
    print("[B6] 옛 판 진행 파일 = 보관 이름으로(지우지 않음) · 이번 실행 중단")
    out = tmp / "b6"
    out.mkdir()
    _old_master(out)
    _progress_path(out).write_text(json.dumps({"date_label": "2026-11-15", "done": []}), encoding="utf-8")
    shutil.copy2(_master_path(out), _partial_path(out))
    try:
        DB.ensure_sales_date_basis(out, None)
    except DB.DateBasisError as e:
        assert "진행" in str(e), e
    else:
        raise AssertionError("옛 진행 파일이 있으면 이번 실행 중단")
    assert not _progress_path(out).exists() and not _partial_path(out).exists()
    kept = sorted(p.name for p in out.glob("*날짜당기기전*"))
    assert len(kept) == 2, kept
    assert DB.has_mark(OutputWorkbook.load(_master_path(out))), "마스터는 당김 끝"
    ok(f"보관 {kept} · 마스터 당김 끝 · 실행 중단")


def b7_next_run(out: Path):
    print("[B7] 당긴 뒤 새 규칙 실행(11-16 실행 = 11.15 칸) — 수집됨 아님 · 겹침 없음")
    wb = OutputWorkbook.load(_master_path(out))
    label = _md(run_day_column(date(2026, 11, 16)))
    assert label == "11.15" and not wb.has_sales("acc1", label) and not wb.has_sales("acc2", label)
    n = len(wb._date_col["가게A"])
    wb.ensure_date("가게A", label)
    assert len(wb._date_col["가게A"]) == n + 1 and "11.15" in wb._date_col["가게A"]
    old = OutputWorkbook.load(next((out / "백업").glob("통계마스터_날짜당기기전_*.xlsx")))
    assert old.has_sales("acc1", "11.15"), "당기기 전이었다면 '수집됨'으로 건너뜀(R1)"
    ok("새 칸 11.15 = 수집 대상 · 칸 1개 추가 · (당기기 전 = 수집됨으로 건너뛰던 위험 확인)")


def b8_misc(tmp: Path):
    print("[B8] 날짜 칸 없는 마스터 = 표시만 · 마스터 없음 = 할 일 없음 · 그로스재고 갱신일 = 최신 칸+1")
    out = tmp / "b8"
    out.mkdir()
    assert "없음" in DB.ensure_sales_date_basis(out, None)
    wb = OutputWorkbook.empty()
    wb.ensure_account("가게C")
    wb.save(_master_path(out))
    assert "표시" in DB.ensure_sales_date_basis(out, None)
    assert DB.has_mark(OutputWorkbook.load(_master_path(out)))
    wb = OutputWorkbook.empty()
    wb.ensure_account("가게D")
    wb.ensure_product_block("가게D", "상품", "로켓그로스", ["kw"])
    wb.set_product_metric("가게D", "상품", config.M_SALES, "11.30", 1)
    assert wb.growth_asof() == "12.01", wb.growth_asof()               # 11.30 칸 재고 = 12-01 새벽 측정
    DB.mark(wb, "새 통계")
    assert DB.has_mark(wb) and DB.judge(wb, out)[0] == "marked"
    ok("표시만 · 마스터 없음 · 그로스재고 '12.01'(칸 11.30 다음 날) · mark() 멱등 표시")


def main():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        b1_entry()
        out, rest0 = b2_shift(tmp)
        b3_rank_same(out, rest0)
        b4_idempotent(out, tmp)
        b5_unknown(tmp)
        b6_progress(tmp)
        b7_next_run(out)
        b8_misc(tmp)
    print("날짜 칸 = 판매일(D-368·D-369) 오프라인 검증 통과")


if __name__ == "__main__":
    main()
