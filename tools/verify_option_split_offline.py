"""옵션 1개 → 여러 개로 나뉠 때 이력 승계·T-162 보완 오프라인 검증(실계정·실 구글시트 없음 · 임시 폴더만 씀).

스펙(소유자 원칙 · 기대 입출력):
- S1 이력은 **같은 VID 블록**으로만 이어진다. 옵션이 나뉘면 기존 VID 블록 = 그 VID 옵션 이름('노출명 (옵션)')이고,
  새 VID 옵션은 빈 블록으로 새로 시작한다(첫 옵션이 새 VID 여도 · 실측 11-18 (DW) LED 스탠드 블랙 725 이력 → 화이트 726 블록).
- S2 다른 정체성 규칙은 그대로: 옛 한 블록에 VID 가 여럿이던 블록은 대표(첫 옵션)로 이어짐(지금 동작 고정) ·
  VID 교체 = 옛 블록 삭제·새로 시작.
- S3 매칭 안 된 대장 상품 = 실행 결과 종합에 '확인 필요'(지금은 ⚠ 줄만 · 종합 '오류 0' · 정상 완료로 보임).
- S4 결과 시트 → 마스터 빈 칸 채움은 블록 VID(블록 3번째 줄 'VID' 칸)까지 같을 때만.
- S5 직원 키워드 반영 0개인 날도 로그 한 줄(읽었는데 바뀐 것 없음 ↔ 안 돎 구별).
- S6 기록 바로잡기 도구: 근거(판매분석 일별 VID 판매수량 · 분리 전 백업 VID) 있는 칸만 옮김 · 근거 없는 칸 = 확인 필요 ·
  미리보기 = 쓰기 0 · --apply = 백업 뒤 저장 · 파이프라인 잠금 중 = 멈춤(exit 3) · 바뀐 칸 = 그 두 블록 지표 칸만.

    python tools/verify_option_split_offline.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8")   # type: ignore[union-attr]
except AttributeError:
    pass

from coupang_analytics import config  # noqa: E402
from coupang_analytics.input_list import Account, Option, Product  # noqa: E402
from coupang_analytics.workbook import OutputWorkbook  # noqa: E402

BIZ = "옵션분리상회"
NAME = "무선 충전 스탠드 접이식"
A, B = "v725", "v726"           # A = 원래 하나뿐이던 옵션(블랙) · B = 나중에 따로 잡힌 옵션(화이트)
HIST = {"2026-11-15": (2, 34), "2026-11-16": (4, 37)}   # 날짜 → (판매량, 노출량) = A 의 이력
FAILS: list[str] = []


def check(ok: bool, msg: str) -> None:
    print(f"  {'✅' if ok else '❌'} {msg}")
    if not ok:
        FAILS.append(msg)


def _metric(wb, prod: str, metric: str, day: str):
    cols = wb._date_col[BIZ]
    col = cols.get(day) or cols.get(day[5:7] + "." + day[8:10])   # 메모리 = ISO 키 · 저장·다시 읽기 뒤 = 'MM.DD'
    return None if col is None else wb.wb[BIZ].cell(wb._metric_row[(BIZ, prod, metric)], col).value


def _single_block_master(vids: list[str], reg: str = "스탠드 T2088") -> OutputWorkbook:
    """분리 전 마스터 — 단일옵션 블록 하나(VID = vids)에 A 이력."""
    wb = OutputWorkbook.empty()
    wb.ensure_product_block(BIZ, NAME, config.KIND_CONTRACT, ["무선충전스탠드"], registered=reg)
    wb.set_product_vids(BIZ, NAME, vids)
    wb.set_product_account_id(BIZ, NAME, "acct1")
    for day, (sales, views) in HIST.items():
        wb.ensure_date(BIZ, day)
        wb.set_product_metric(BIZ, NAME, config.M_SALES, day, sales)
        wb.set_product_metric(BIZ, NAME, config.M_VIEWS, day, views)
    return wb


def _split_run(wb, opts: list[Option], base: str = "LED 스탠드 T2088", day: str = "2026-11-17") -> list[str]:
    from coupang_analytics.pipeline_process import _process_account
    logs: list[str] = []
    prod = Product(name=base, options=opts, exposed_name=NAME, kind=config.KIND_CONTRACT)
    acc = Account("acct1", "대표", BIZ, products=[prod], ledger_products={base})
    _process_account(acc, wb, {}, {}, day, logs.append, Path(tempfile.mkdtemp()) / "t.xlsx")
    return logs


def t1_split_new_vid_first() -> None:
    print("[S1] 옵션 1→2 · 첫 옵션 = 새 VID(화이트 B) · 기존 블록 VID = A(블랙) → A 이력은 A 블록에")
    wb = _single_block_master([A])
    logs = _split_run(wb, [Option("화이트", [B]), Option("블랙", [A])])
    white, black = f"{NAME} (화이트)", f"{NAME} (블랙)"
    check({white, black} <= set(wb.products_of(BIZ)), f"두 옵션 블록 생김: {wb.products_of(BIZ)}")
    check(wb.product_vids(BIZ, black) == [A] and wb.product_vids(BIZ, white) == [B],
          f"VID = 블랙 {wb.product_vids(BIZ, black)} · 화이트 {wb.product_vids(BIZ, white)}")
    got_black = [(_metric(wb, black, config.M_SALES, d), _metric(wb, black, config.M_VIEWS, d)) for d in HIST]
    got_white = [(_metric(wb, white, config.M_SALES, d), _metric(wb, white, config.M_VIEWS, d)) for d in HIST]
    check(got_black == list(HIST.values()), f"A(블랙) 블록에 A 이력 그대로: {got_black}")
    check(got_white == [(None, None)] * len(HIST), f"B(화이트) 블록 = 분리 전 날짜 빈 칸(새로 시작): {got_white}")
    check(not any("[정체성] 기존 블록" in x and "(화이트)" in x for x in logs),
          "A 블록을 첫 옵션(화이트) 이름으로 바꾸는 '이름 정규화' 로그 없음")
    check(wb.product_keywords(BIZ, white) == ["무선충전스탠드"], f"키워드(순위) = 대표(첫 옵션) 블록: {wb.product_keywords(BIZ, white)}")


def t2_split_old_vid_first() -> None:
    print("[S1] 옵션 1→2 · 첫 옵션 = 기존 VID(블랙 A) → A 이력은 A 블록(대표)에 · 새 옵션 = 빈 블록")
    wb = _single_block_master([A])
    _split_run(wb, [Option("블랙", [A]), Option("화이트", [B])])
    white, black = f"{NAME} (화이트)", f"{NAME} (블랙)"
    got = [_metric(wb, black, config.M_SALES, d) for d in HIST]
    check(got == [s for s, _ in HIST.values()] and wb.product_vids(BIZ, black) == [A], f"A 블록 이력 유지: {got}")
    check([_metric(wb, white, config.M_SALES, d) for d in HIST] == [None] * len(HIST), "새 옵션 블록 = 빈 칸")


def t3_legacy_multi_vid_block() -> None:
    print("[S2] 옛 블록 하나에 VID 둘(A·B) → 옵션별 블록 · 옛 이력 = 대표(첫 옵션) 블록(지금 동작 고정)")
    wb = _single_block_master([A, B])
    _split_run(wb, [Option("화이트", [B]), Option("블랙", [A])])
    white, black = f"{NAME} (화이트)", f"{NAME} (블랙)"
    got = [_metric(wb, white, config.M_SALES, d) for d in HIST]
    check(got == [s for s, _ in HIST.values()], f"옛 여러 VID 블록 이력 = 대표 블록: {got}")
    check(wb.product_vids(BIZ, white) == [B] and wb.product_vids(BIZ, black) == [A], "VID = 옵션별 하나")


def t4_vid_replaced_starts_new() -> None:
    print("[S2] 단일옵션 VID 교체(A → 새 C · 교집합 없음) = 옛 블록 삭제·새로 시작(D-009·소유자 09-20)")
    wb = _single_block_master([A], reg="LED 스탠드 T2088")
    logs = _split_run(wb, [Option("", ["v999"])])
    new = wb.resolve_block_name(BIZ, ["v999"])
    check(bool(new) and wb.resolve_block_name(BIZ, [A]) is None, f"새 VID 블록 {new} · 옛 VID 블록 없음")
    check(bool(new) and [_metric(wb, new, config.M_SALES, d) for d in HIST] == [None] * len(HIST),
          "옛 이력 삭제(새로 시작)")
    check(any("vid 변경" in x for x in logs), "정체성 변경 로그")


def t5_unmatched_needs_check() -> None:
    print("[S3] 매칭 안 된 대장 상품(VID 없음) = 실행 결과 종합 '확인 필요'·목록 · 없으면 판정 그대로")
    from coupang_analytics import run_result as RR
    from coupang_analytics.pipeline_process import _process_account
    for missing, want in ((True, f"{RR.UNMATCHED} --> 확인 필요"), (False, "정상 완료")):
        lines: list[str] = []
        prods = [Product(name="쿠팡 등록 상품", options=[Option("", ["v1"])], exposed_name="쿠팡 등록 상품")]
        if missing:
            prods.append(Product(name="접이식 정리함 JK0026", options=[Option("", [])]))
        acc = Account("acct1", "대표", BIZ, products=prods, ledger_products={p.name for p in prods})
        with RR.RunSummary(lines.append, [BIZ], should_stop=lambda: False, rank={}) as log:
            log.enter(RR.SALES)
            _process_account(acc, OutputWorkbook.empty(), {}, {}, "2026-11-22", log, Path(tempfile.mkdtemp()) / "t.xlsx")
            RR.LAST_SALES.update(ok=1, total=1, accounts=[BIZ], pw=[], missed={})
        judge = next((x for x in lines if x.startswith("판정: ")), "")
        check(judge == f"판정: {want}", f"{'미매칭 있음' if missing else '미매칭 없음'} 판정 = {judge!r}")
        listed = [x for x in lines if x.startswith(RR.UNMATCHED)]
        check(bool(listed) == missing and (not missing or "접이식 정리함 JK0026" in listed[0]),
              f"종합 목록 줄: {listed}")
        check((f"{RR.UNMATCHED} 1 ·" in lines[-1]) == missing, f"한 줄 요약: {lines[-1]}")


def t6_fill_checks_vid() -> None:
    print("[S4] 결과 시트 → 마스터 빈 칸 채움 = 블록 VID 줄(A 'VID' · C 값)까지 같을 때만 · 시트 숫자 VID 도 같게 봄")
    from coupang_analytics import gsheet_fill
    for sheet_vid, n_want, why in (("95322412626", 1, "VID 같음(글자)"), (95322412626, 1, "VID 같음(시트 숫자)"),
                                   ("96193704227", 0, "VID 다름 → 블록 건너뜀")):
        wb = OutputWorkbook.empty()
        wb.ensure_product_block(BIZ, "같은이름 상품", config.KIND_CONTRACT, ["kw"], registered="같은이름 상품")
        wb.set_product_vids(BIZ, "같은이름 상품", ["95322412626"])
        for d in ("2026-11-15", "2026-11-16"):
            wb.ensure_date(BIZ, d)
        wb.apply_style()
        ws = wb.wb[BIZ]
        grid = [[ws.cell(r, c).value for c in range(1, ws.max_column + 1)] for r in range(1, ws.max_row + 1)]
        vrow = next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value == "VID")
        cols = wb._date_col[BIZ]
        srow, scol = wb._metric_row[(BIZ, "같은이름 상품", config.M_SALES)], cols.get("2026-11-15") or cols["11.15"]
        grid[vrow - 1][2] = sheet_vid
        grid[srow - 1][scol - 1] = 7                    # 시트에만 있는 값(마스터 빈 칸)
        logs: list[str] = []
        got = gsheet_fill.fill_blank_cells(wb, {BIZ: grid}, on_log=logs.append)
        check(got == {BIZ: n_want} and (ws.cell(srow, scol).value == 7) == bool(n_want), f"{why}: {got} {logs}")
        if not n_want:
            check(any("VID 다름" in x for x in logs), f"건너뜀 로그에 'VID 다름': {logs}")


def t7_staff_keywords_zero_logged() -> None:
    print("[S5] 직원 키워드 반영 0개 상품인 날도 로그 한 줄 · 1개 이상 = 옛 문구 그대로")
    import coupang_analytics.gsheet_api as GA
    import coupang_analytics.gsheet_stats as GS
    from coupang_analytics import pipeline_gsheet as PG
    orig = (GA.load_sa_info, GA.GSheetClient, GS.merge_staff_keywords)
    try:
        GA.load_sa_info = lambda *a, **k: {"x": 1}
        GA.GSheetClient = lambda *a, **k: object()
        for n, want in ((0, "바뀐 키워드 없음(반영 0개 상품)"), (2, "직원 입력 키워드 반영 2개 상품")):
            GS.merge_staff_keywords = lambda client, wb, on_log=None, _n=n: _n
            logs: list[str] = []
            PG.pull_gsheet_keywords(OutputWorkbook.empty(), "https://example.invalid/sheet", logs.append)
            check(len(logs) == 1 and want in logs[0], f"반영 {n}개: {logs}")
    finally:
        GA.load_sa_info, GA.GSheetClient, GS.merge_staff_keywords = orig


# ── S6 기록 바로잡기 도구 ─────────────────────────────────────────────────────────
WHITE, BLACK = f"{NAME} (화이트)", f"{NAME} (블랙)"
OTHER, OTHER_NEW = "정상 상품 (기본)", "정상 상품 (대용량)"


def _days() -> list[str]:
    """오늘 기준 지난 6일(판매일) — d[0..3] = 분리 전 · d[4..5] = 분리 뒤(블랙 제 이력). 도구의 년도 추정과 맞게 오늘 기준."""
    from datetime import date, timedelta
    t = date.today()
    return [(t - timedelta(days=k)).isoformat() for k in (7, 6, 5, 4, 2, 1)]


def _bug_master(out: Path, with_backup: bool, contradict: bool = False) -> None:
    """옛 코드가 만든 모양: 화이트(B) 블록에 분리 전 A 이력 · 블랙(A) = 분리 뒤만 · 정상 쌍(제 이력 그대로 + 새 옵션) 하나 더."""
    from coupang_analytics import date_basis
    from coupang_analytics.pipeline_paths import _master_path
    d = _days()
    pre = {d[0]: (2, 30), d[1]: (0, 20), d[2]: (1, 11), d[3]: (3, 40)}   # A 이력(판매량·노출량)
    hist = {d[0]: {A: 2, B: 1}, d[1]: {A: 0, B: 0}, d[3]: {A: 3, B: 3},
            d[4]: {A: 1, B: 5}, d[5]: {A: 2, B: 4}}                        # d[2] = 그날 기록 없음
    if contradict:
        hist[d[3]] = {A: 9, B: 3}                                          # B 판매량 3 ≠ A 판매 9 → 쌍 전체 확인 필요
    wb = OutputWorkbook.empty()
    for nm, vids in ((WHITE, [B]), (BLACK, [A]), (OTHER, ["o1"]), (OTHER_NEW, ["o2"])):
        wb.ensure_product_block(BIZ, nm, config.KIND_CONTRACT, ["kw"] if nm in (WHITE, OTHER) else [],
                                registered="스탠드 T2088" if nm in (WHITE, BLACK) else "정상 상품")
        wb.set_product_vids(BIZ, nm, vids)
        wb.set_product_account_id(BIZ, nm, "acct1")
    for day in d:
        wb.ensure_date(BIZ, day)
    for day, (s, v) in pre.items():
        wb.set_product_metric(BIZ, WHITE, config.M_SALES, day, s)
        wb.set_product_metric(BIZ, WHITE, config.M_VIEWS, day, v)
        wb.set_product_metric(BIZ, OTHER, config.M_SALES, day, s)        # 정상 상품 = 제 VID o1 판매와 같음
    for day, (s, v) in ((d[4], (1, 50)), (d[5], (2, 60))):
        wb.set_product_metric(BIZ, BLACK, config.M_SALES, day, s)
        wb.set_product_metric(BIZ, BLACK, config.M_VIEWS, day, v)
        wb.set_product_metric(BIZ, WHITE, config.M_SALES, day, hist[day][B])
        wb.set_product_metric(BIZ, OTHER_NEW, config.M_SALES, day, 0)
        wb.set_product_metric(BIZ, OTHER, config.M_SALES, day, 1)
    date_basis.mark(wb, "시험")
    out.mkdir(parents=True, exist_ok=True)
    wb.save(_master_path(out))
    for day, opts in hist.items():
        opts = {**opts, "o1": pre.get(day, (1, 0))[0] if day in pre else 1}
        p = out / "판매분석_일별" / "acct1" / f"{day[:7]}.json"
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        data[day] = {"옵션": {v: {"판매수량": q} for v, q in opts.items()}}
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if with_backup:                                                        # 분리 실행 시작 때 백업 = A 한 블록(분리 전)
        bk = OutputWorkbook.empty()
        bk.ensure_product_block(BIZ, NAME, config.KIND_CONTRACT, ["kw"], registered="스탠드 T2088")
        bk.set_product_vids(BIZ, NAME, [A])
        for day, (s, v) in pre.items():
            bk.ensure_date(BIZ, day)
            bk.set_product_metric(BIZ, NAME, config.M_SALES, day, s)
            bk.set_product_metric(BIZ, NAME, config.M_VIEWS, day, v)
        date_basis.mark(bk, "시험")
        (out / "백업").mkdir(exist_ok=True)
        bk.save(out / "백업" / f"통계마스터_{d[4][2:4]}{d[4][5:7]}{d[4][8:10]}_180000.xlsx")


def _grid(path: Path) -> dict:
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    out = {(ws.title, r, c): v for ws in wb.worksheets for r, row in enumerate(ws.iter_rows(values_only=True), 1)
           for c, v in enumerate(row, 1) if v not in (None, "")}
    wb.close()
    return out


def _tool(out: Path, *args: str) -> tuple[int, str]:
    import contextlib
    import io
    import fix_option_split_history as FX
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = FX.main(["--output", str(out), *args])
    return rc, buf.getvalue()


def _preview(out: Path, plan: Path) -> list[dict]:
    rc, _ = _tool(out, "--plan-out", str(plan))
    check(rc == 0, f"미리보기 rc={rc}")
    return json.loads(plan.read_text(encoding="utf-8"))


def _changed_outside(before: dict, after: dict, master: Path) -> tuple[set, list]:
    """전후 전체 비교 → (바뀐 칸, 화이트·블랙 지표행 밖에서 바뀐 칸)."""
    changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
    wb = OutputWorkbook.load(master)
    rows = {r: p for (b, p, m), r in wb._metric_row.items() if b == BIZ}
    return changed, [k for k in changed if k[0] != BIZ or rows.get(k[1]) not in (WHITE, BLACK)]


def t8_fix_tool_preview() -> None:
    print("[S6] 바로잡기 도구 찾기 — 판매분석 근거 + 분리 전 백업 근거 = 옮김 · 미리보기 = 마스터 안 씀 · 정상 쌍 안 찾음")
    from coupang_analytics.pipeline_paths import _master_path
    d = _days()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "o"
        _bug_master(out, with_backup=True)
        mtime = _master_path(out).stat().st_mtime_ns
        plans = _preview(out, Path(tmp) / "판정표.json")
        check(_master_path(out).stat().st_mtime_ns == mtime, "미리보기 = 마스터 안 씀")
        check([(p["옮길_블록"], p["받을_블록"]) for p in plans] == [(WHITE, BLACK)],
              f"찾은 쌍 = 화이트 → 블랙 하나(정상 쌍 없음): {[(p['옮길_블록'], p['받을_블록']) for p in plans]}")
        dec = {x["판매일"]: (x["판정"], x["결정"]) for x in plans[0]["칸"]} if plans else {}
        check(dec == {d[0]: ("판매분석", "옮김"), d[1]: ("못 가림", "옮김"), d[2]: ("못 가림", "옮김"),
                      d[3]: ("못 가림", "옮김")}, f"판매분석 근거 1칸 + 백업 근거 3칸(같은 판매·기록 없음) = 옮김: {dec}")


def t9_fix_tool_apply() -> None:
    print("[S6] 바로잡기 도구 적용 — 대상 지정 없음·잠금 중 = 멈춤 · 판정표 칸만 · 바뀐 칸 = 두 블록 지표 칸만 · 백업 · 두 번 안 옮김")
    from coupang_analytics.pipeline_paths import _master_path
    from coupang_analytics.registry_lock import registry_lock
    d = _days()
    with tempfile.TemporaryDirectory() as tmp:
        out, plan = Path(tmp) / "o", Path(tmp) / "판정표.json"
        _bug_master(out, with_backup=True)
        master = _master_path(out)
        before, mtime = _grid(master), master.stat().st_mtime_ns
        _preview(out, plan)
        rc, _ = _tool(out, "--apply")
        check(rc == 2 and master.stat().st_mtime_ns == mtime, "--apply 대상 지정 없음 = 멈춤(exit 2)·저장 0")
        with registry_lock(out / "_잠금" / "파이프라인.lock", wait_sec=0):
            rc, _ = _tool(out, "--apply", "--plan", str(plan))
        check(rc == 3 and master.stat().st_mtime_ns == mtime, "파이프라인 잠금 중 = 멈춤(exit 3)·저장 0")
        rc, _ = _tool(out, "--apply", "--plan", str(plan))
        changed, bad = _changed_outside(before, _grid(master), master)
        check(rc == 0 and len(changed) == 16 and not bad, f"바뀐 칸 = 화이트·블랙 지표 칸만 {len(changed)}칸 · 그 밖 {bad[:3]}")
        wb = OutputWorkbook.load(master)
        got = [(_metric(wb, BLACK, config.M_SALES, x), _metric(wb, WHITE, config.M_SALES, x)) for x in d]
        check(got == [(2, None), (0, None), (1, None), (3, None), (1, 5), (2, 4)],
              f"블랙 = A 이력 전부 · 화이트 = 분리 전 빈 칸·분리 뒤 그대로: {got}")
        check(len(list((out / "백업").glob("쿠팡데이타분석_통계_옵션분리이력바로잡기전_*.xlsx"))) == 1, "저장 전 백업 1개")
        rc, txt = _tool(out)
        check(rc == 0 and "찾은 쌍 0" in txt, f"다시 찾기 = 0쌍(두 번 옮기지 않음): {txt.splitlines()[:1]}")


def t10_fix_tool_no_evidence() -> None:
    print("[S6] 바로잡기 도구 근거 부족 — 백업 없음 = 못 가린 칸 확인 필요 · 판매분석과 안 맞는 날 있는 쌍 = 전체 확인 필요·저장 0")
    from coupang_analytics.pipeline_paths import _master_path
    d = _days()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "o2"
        _bug_master(out, with_backup=False)
        plans = _preview(out, Path(tmp) / "판정표.json")
        dec = {x["판매일"]: x["결정"] for x in plans[0]["칸"]} if plans else {}
        check(dec == {d[0]: "옮김", d[1]: "확인 필요", d[2]: "확인 필요", d[3]: "확인 필요"},
              f"백업 없음 = 판매분석으로 못 가린 칸 확인 필요(안 옮김): {dec}")
        out3 = Path(tmp) / "o3"
        _bug_master(out3, with_backup=True, contradict=True)
        g3, mtime = _grid(_master_path(out3)), _master_path(out3).stat().st_mtime_ns
        rc, txt = _tool(out3, "--apply", "--biz", BIZ)
        check(rc == 0 and "[확인 필요]" in txt and _grid(_master_path(out3)) == g3
              and _master_path(out3).stat().st_mtime_ns == mtime,
              f"안 맞는 날 있는 쌍 = 쌍 전체 확인 필요·옮기지 않음·저장 안 함: {txt.splitlines()[:2]}")


def main() -> int:
    print("옵션 분리 이력 승계·T-162 보완 오프라인 검증")
    for t in (t1_split_new_vid_first, t2_split_old_vid_first, t3_legacy_multi_vid_block, t4_vid_replaced_starts_new,
              t5_unmatched_needs_check, t6_fill_checks_vid, t7_staff_keywords_zero_logged,
              t8_fix_tool_preview, t9_fix_tool_apply, t10_fix_tool_no_evidence):
        t()
    if FAILS:
        print(f"❌ 실패 {len(FAILS)}건")
        return 1
    print("✅ 옵션 분리 검증 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
