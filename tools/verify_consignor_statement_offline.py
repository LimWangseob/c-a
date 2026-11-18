"""위탁자 정산서 3차 형식(구글시트) 시험 — 오프라인 · 결정적 · 구글 API·네트워크·로그인 없음(T-38 · 계획 S1).

기대값 = 계획서 3절 S1 검산 규칙·결정 문장에서 손으로 정함(코드에서 뽑지 않음):
  ① 숫자 쪽: 누적 반올림 칸 합 = 목표 · 상품표 열 합 = 1쪽 1~8(확정 전 포함) · 금액 전혀 없는 상품 뺌 · 판매 금액 큰 순 ·
     6 종류별 합 = 1쪽 6(끝전 줄) · 검산 1원 이상 차이만 실패 · 판정표 파일 없음 = judgments 사유(조용히 넘기지 않음).
  ② 그리기 쪽(합성 자료 2개 · 정산 예정 포함/확정): 검산 통과 · 칸 범위·병합 겹침 없음 · 쪽 높이 = 쪽 수 × A4 · 쪽 경계 = 행 경계 ·
     결정 문구(D-241 ⑦ 문의 없음 · D-242 머리 · D-251 회색 줄 · D-259 1쪽 · D-260 '판매 기간 … · 발행' 굵게 · '검토용' 없음) ·
     넘치면 다음 쪽(D-241 ④ · '(계속)' 머리 · 줄 빠짐·중복 없음) · 나눌 수 없는 큰 묶음 = 중단 · 검산 실패 = 쓰기 0회 ·
     여러 판매 달 = 쓰기 거부(D-241 ⑥).
  ③ 입구(tools/settlement_consignor.py): 계정ID 고르기(없는 ID = 중단) · 검산 합치기 · --sheet 는 --month 와 함께만.

    python tools/verify_consignor_statement_offline.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coupang_analytics import settlement_consignor_gsheet as GS  # noqa: E402
from coupang_analytics import settlement_consignor_month as CM  # noqa: E402
from coupang_analytics.settlement_consignor_gsheet_layout import MARGIN, PAGE_H, StatementLayoutError  # noqa: E402
from coupang_analytics.settlement_consignor_month_calc import cum_round  # noqa: E402
from coupang_analytics.settlement_consignor_month_cost import KINDS, PEND_KIND  # noqa: E402
from coupang_analytics.settlement_consignor_month_out import LINE_NAMES, product_table, rg_kinds  # noqa: E402

ISSUED = "2026-11-18"


def _tool():
    spec = importlib.util.spec_from_file_location("settlement_consignor_tool", ROOT / "tools" / "settlement_consignor.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeClient:
    """요청을 모으기만 하는 시트 클라이언트(GSheetClient 모양: meta · batch_update)."""

    def __init__(self, old_ids=(0, 1000, 1001)):
        self.calls: list[list[dict]] = []
        self._old = list(old_ids)

    def meta(self, refresh: bool = False) -> dict:
        return {"sheets": [{"properties": {"sheetId": s, "title": f"old{s}"}} for s in self._old]}

    def batch_update(self, requests: list[dict]) -> dict:
        self.calls.append(json.loads(json.dumps(requests)))
        return {}


# ── 합성 자료(손으로 맞춘 금액 · 실제 계정·사람 아님) ──────────────────
def _product(name: str, cols: list[int], pend: list[int] | None = None) -> dict:
    p: dict = {"name": name, **{f"c{k}": cols[k - 1] for k in range(1, 9)}, "subtotal": sum(cols)}
    if pend and any(pend):
        p["pending"] = {**{f"c{k}": pend[k - 1] for k in range(1, 9)}, "subtotal": sum(pend)}
    return p


def synthetic(pending: bool = True, month: str = "2026-09") -> dict:
    """1~8 = 상품 2개 열 합 · 상품 정산액 748,000 · 9 반영 −33,000 · 10 +1,500 → 이번 정산 금액 716,500 ·
    정산 예정 포함이면 확정 전 168,400(1 +200,000 · 3 −21,600 · 6 −10,000)."""
    a = [600_000, -10_000, -64_800, 3_000, -30_000, -50_000, -7_000, 3_000]
    b = [400_000, 0, -43_200, 2_000, -20_000, -30_000, -5_000, 0]
    pa = [200_000, 0, -21_600, 0, 0, -10_000, 0, 0] if pending else [0] * 8
    lines = [{"no": k, "name": LINE_NAMES[k - 1], "amount": a[k - 1] + b[k - 1], "pending": pa[k - 1]} for k in range(1, 9)]
    kinds = [{"name": "입출고비 (창고에 넣고 꺼냄)", "amount": -50_000}, {"name": "고객 배송비", "amount": -20_000 - (0 if pending else 10_000)}]
    if pending:
        kinds.append({"name": PEND_KIND, "amount": -10_000, "pending": True})
    flow = ([{"name": "쿠팡 입금 완료", "desc": "이미 들어온 돈", "amount": 548_100},
             {"name": "쿠팡 입금 예정", "desc": "쿠팡 미확정 포함", "amount": 168_400}] if pending
            else [{"name": "쿠팡 입금 완료", "desc": "이미 들어온 돈", "amount": 716_500}])
    deps = [{"date": f"{month}-10", "desc": "1주 판매 정산", "amount": 300_000}, {"date": f"{month}-17", "desc": "2주 판매 정산", "amount": 248_100},
            {"date": f"{month}-24", "desc": "3주 판매 정산" + (" (예정)" if pending else ""), "amount": 168_400}]
    return {"account": "synth01", "company": "합성상회", "ceo": "합성 위탁자", "period_start": f"{month}-01", "period_end": f"{month}-30",
            "basis_date": "2026-11-15", "status": "정산 예정 포함" if pending else "확정", "lines": lines, "product_subtotal": 748_000,
            "products": [_product("합성 상품 가", a, pa), _product("합성 상품 나", b)], "rg_kinds": kinds,
            "common": {"items": [{"name": "판매자서비스이용료", "coupang_amount": 55_000, "applied_amount": -33_000}],
                       "basis_text": "판매 비중 60.0% · 등록 비중 2/5=40.0% 중 작은 쪽 40.0%", "total_coupang": 55_000, "total_applied": -33_000},
            "separate": [{"name": "우대수수료 환급", "amount": 1_500}], "settle_amount": 716_500,
            "pending_total": 168_400 if pending else 0, "pending_detail": [{"방법": "합성"}] if pending else [],
            "flow": flow, "deposits": deps, "checks": [], "judgments": []}


# ── ① 숫자 쪽 ─────────────────────────────────────────────────
def test_cum_round() -> None:
    assert cum_round([0.4, 0.4, 0.4], 1) == [0, 1, 0]
    assert sum(cum_round([1.25, 2.25, -0.75, 3.5], 6)) == 6
    assert cum_round([], 0) == []


def test_product_table() -> None:
    cols: dict = defaultdict(lambda: [0.0] * 9)
    pend: dict = defaultdict(lambda: [0.0] * 9)
    cols["p1"][1:] = [100.4, -1.2, -10.6, 0.3, 0, -5.5, 0, 0]
    cols["p2"][1:] = [300.4, 0, -30.4, 0.3, -2.5, 0, 0, 0]
    cols["p3"][1:] = [100.4, 0, -10.4, 0.3, 0, 0, 0, 0]
    pend["p3"][1:] = [50.4, 0, -5.4, 0, 0, 0, 0, 0]
    st = SimpleNamespace(cols=cols, pend=pend)
    t = product_table(st, {"가": ["p1"], "나": ["p2"], "다": ["p3"], "빈": ["p0"]})
    assert t["names"] == ["나", "가", "다"], t["names"]             # 판매 금액 큰 순 · 같으면 이름 순 · 금액 없는 '빈' 뺌
    for k in range(1, 9):
        exp = round(sum(cols[p][k] for p in ("p1", "p2", "p3")))
        assert t["lines8"][k] == exp == sum(t["int"][n][k] for n in t["names"]), (k, t["lines8"][k], exp)
        assert t["pend8"][k] == sum(t["pint"][n][k] for n in t["names"])
    assert t["lines8"][1] == 501 and t["pend8"][1] == 50 and t["lines8"]["E"] == 501 - 1 - 51 + 1


def test_rg_kinds() -> None:
    kinds: dict = defaultdict(float, {KINDS[0][0]: 0.6, KINDS[1][0]: 0.6})
    got = rg_kinds(SimpleNamespace(kinds=kinds), -1)
    assert [x["amount"] for x in got] == [-1, -1, 1] and got[-1]["name"] == "끝전", got
    kinds[PEND_KIND] = 3.0
    got = rg_kinds(SimpleNamespace(kinds=kinds), -5)
    assert got[-1] == {"name": PEND_KIND, "amount": -3, "pending": True}, got


def test_failed_checks() -> None:
    cash = "검산(실제 = 정산금액 − 공제 − 판매 조정)"
    d = {"checks": [{"검사": "a", "차이": 0}, {"검사": "b", "차이": 0.6}, {"검사": "c", "차이": -1}, {"검사": "참고", cash: 2}]}
    assert [c["검사"] for c in CM.failed_checks(d)] == ["c", "참고"]


def test_load_judge() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        j = CM.load_judge(inputs=Path(tmp))
        assert j.added == {} and j.names == {} and len(j.notes) == 2, j.notes
        (Path(tmp) / CM.NAMES_FILE).write_text(json.dumps({"_설명": "x", "aid1": [{"표시 이름": "가"}]}, ensure_ascii=False), encoding="utf-8")
        j = CM.load_judge(inputs=Path(tmp))
        assert j.names == {"aid1": [{"표시 이름": "가"}]} and len(j.notes) == 1


# ── ② 그리기 쪽 ───────────────────────────────────────────────
def _grid(reqs: list[dict]) -> tuple[int, int]:
    gp = reqs[0]["updateSheetProperties"]["properties"]["gridProperties"]
    return gp["rowCount"], gp["columnCount"]


def _overlap(a: dict, b: dict) -> bool:
    return (a["startRowIndex"] < b["endRowIndex"] and b["startRowIndex"] < a["endRowIndex"]
            and a["startColumnIndex"] < b["endColumnIndex"] and b["startColumnIndex"] < a["endColumnIndex"])


def _range_errors(t, nr: int, nc: int) -> tuple[list[str], list]:
    errs, merges = [], []
    for i, r in enumerate(t.requests):
        kind = next(iter(r))
        if kind not in ("mergeCells", "updateBorders"):
            continue
        rg = r[kind]["range"]
        if rg["sheetId"] != t.gid:
            errs.append(f"{t.title} 요청 {i} 다른 탭 {rg['sheetId']}")
        if not (0 <= rg["startRowIndex"] < rg["endRowIndex"] <= nr and 0 <= rg["startColumnIndex"] < rg["endColumnIndex"] <= nc):
            errs.append(f"{t.title} 요청 {i} {kind} 범위 밖 {rg}")
        if kind == "mergeCells":
            merges.append((i, rg))
    return errs, merges


def _size_errors(t, nr: int, nc: int) -> list[str]:
    errs = []
    for r in t.requests:
        if "updateDimensionProperties" in r:
            rg = r["updateDimensionProperties"]["range"]
            if not (0 <= rg["startIndex"] < rg["endIndex"] <= (nr if rg["dimension"] == "ROWS" else nc)):
                errs.append(f"{t.title} 크기 요청 범위 밖 {rg}")
        if "updateCells" in r:
            rows = r["updateCells"]["rows"]
            if len(rows) != nr or any(len(x["values"]) != nc for x in rows):
                errs.append(f"{t.title} updateCells 크기 ≠ 시트 {nr}×{nc}")
    return errs


def structure_errors(plan) -> list[str]:
    """칸 범위 ⊂ 시트 크기 · updateCells 행·열 수 = 시트 크기 · 병합 겹침 없음 · 요청이 모두 자기 탭."""
    errs: list[str] = []
    for t in plan.tabs:
        nr, nc = _grid(t.requests)
        e, merges = _range_errors(t, nr, nc)
        errs += e + _size_errors(t, nr, nc)
        for k, (i, a) in enumerate(merges):
            errs += [f"{t.title} 병합 겹침 요청 {i} · {j}" for j, b in merges[k + 1:] if _overlap(a, b)]
    return errs


def _row_heights(reqs: list[dict]) -> list[int]:
    return [r["updateDimensionProperties"]["properties"]["pixelSize"] for r in reqs
            if "updateDimensionProperties" in r and r["updateDimensionProperties"]["range"]["dimension"] == "ROWS"]


def page_errors(plan) -> list[str]:
    """위탁자 탭: 높이 = 쪽 수 × (PAGE_H + 위아래 여백) · 쪽 경계 = 행 경계 · 쪽마다 첫·끝 행 = 여백."""
    sheet, errs = PAGE_H + 2 * MARGIN, []
    for t in (t for t in plan.tabs if t.kind == "consignor"):
        hs = _row_heights(t.requests)
        if sum(hs) != t.pages * sheet:
            errs.append(f"{t.title} 높이 {sum(hs)} ≠ {t.pages}쪽 × {sheet}")
        bounds = [0]
        for h in hs:
            bounds.append(bounds[-1] + h)
        idx = {b: i for i, b in enumerate(bounds)}
        for p in range(t.pages):
            top, bottom = idx.get(p * sheet), idx.get((p + 1) * sheet)
            if top is None or bottom is None:
                errs.append(f"{t.title} {p + 1}쪽 경계가 행 경계 아님")
            elif hs[top] != MARGIN or hs[bottom - 1] != MARGIN:
                errs.append(f"{t.title} {p + 1}쪽 위아래 여백 ≠ {MARGIN}")
    return errs


def texts(reqs: list[dict]) -> list[tuple[str, list]]:
    out = []
    for r in reqs:
        for row in r.get("updateCells", {}).get("rows", []):
            for v in row["values"]:
                uv = v.get("userEnteredValue", {})
                s = uv.get("stringValue") or uv.get("formulaValue")
                if s:
                    out.append((s, v.get("textFormatRuns", [])))
    return out


def _bold_at(text: str, runs: list, prefix: str) -> bool:
    i, fmt = text.find(prefix), None
    for r in runs:
        if r.get("startIndex", 0) <= i:
            fmt = r["format"]
    return bool(fmt and fmt.get("bold"))


def _consignor_text_errors(t, tx: list, joined: str) -> list[str]:
    errs = []
    pend = t.data.get("status") == "정산 예정 포함"
    if pend and "쿠팡 미확정 금액 포함" not in joined:
        errs.append(f"{t.title}: 1쪽 '쿠팡 미확정 금액 포함' 없음(D-259)")
    if any(p.get("pending") for p in t.data["products"]) and "└ 정산 예정(쿠팡 미확정)" not in joined:
        errs.append(f"{t.title}: 2쪽 '└ 정산 예정(쿠팡 미확정)' 없음(D-251)")
    if pend and f"자료 기준일 {t.data['basis_date']} · 정산 예정 포함" not in joined:
        errs.append(f"{t.title}: 머리 '자료 기준일 · 정산 예정 포함' 없음(D-242)")
    bolds = [_bold_at(s, runs, "판매 기간") for s, runs in tx if "판매 기간" in s and "발행" in s]
    if not bolds or not all(bolds):
        errs.append(f"{t.title}: '판매 기간 … · 발행 …' 줄 굵지 않음 {bolds}(D-260)")
    return errs


def decision_text_errors(plan) -> list[str]:
    errs = []
    for t in plan.tabs:
        tx = texts(t.requests)
        joined = "\n".join(s for s, _ in tx)
        errs += [f"{t.title}: '{bad}' 글자 있음" for bad in ("검토용", "문의", "확정 전 금액", "아직 반영 안 된") if bad in joined]
        if t.kind == "consignor":
            errs += _consignor_text_errors(t, tx, joined)
    return errs


def test_render() -> None:
    ds = [synthetic(True), {**synthetic(False), "account": "synth02", "ceo": "합성 위탁자 둘"}]
    for d in ds:
        assert GS.check(d) == [], (d["account"], GS.check(d))
    plan = GS.build_statement(ds, ISSUED)
    assert [t.kind for t in plan.tabs] == ["summary", "consignor", "consignor"] and [t.gid for t in plan.tabs] == [1000, 1001, 1002]
    assert plan.tabs[0].member_gids == [1001, 1002] and plan.tabs[1].title == "9월 합성 위탁자 (synth01)"
    errs = structure_errors(plan) + page_errors(plan) + decision_text_errors(plan)
    assert not errs, errs
    fake = FakeClient()
    GS.write_statement(fake, ds, ISSUED)
    setup = fake.calls[0]
    assert [next(iter(r)) for r in setup] == ["addSheet"] + ["deleteSheet"] * 3 + ["addSheet"] * 3 + ["deleteSheet"]
    assert len(fake.calls) == 1 + len(plan.tabs)


def test_overflow() -> None:
    """상품 40·입금 25줄을 0원으로 늘림(합계 불변) → 3쪽 이상 · 쪽 높이 지킴 · '(계속)' 머리 · 줄 빠짐·중복 없음 · 합계 줄 1번."""
    d = synthetic(True)
    d["products"] += [_product(f"합성 넘침 {i:02d} 이름이 조금 긴 상품 (옵션 포함)", [0] * 8) for i in range(40)]
    d["deposits"] += [{"date": "2026-09-30", "desc": f"합성 입금 {i}", "amount": 0} for i in range(25)]
    plan = GS.build_statement([d], ISSUED)
    t = plan.tabs[1]
    assert t.pages >= 3, t.pages
    assert not (page_errors(plan) + structure_errors(plan))
    cells = [s for s, _ in texts(t.requests)]
    assert "정산 상세 (계속)" in cells
    assert all(sum(s.startswith(f"합성 넘침 {i:02d} ") for s in cells) == 1 for i in range(40))
    assert all(cells.count(f"합성 입금 {i}") == 1 for i in range(25))
    assert cells.count("합계 (= 1쪽)") == 1 and cells.count("상품") >= 2


def test_unsplittable() -> None:
    d = synthetic(True)
    d["flow"] += [{"name": f"합성 {i}", "desc": "0원", "amount": 0} for i in range(45)]
    try:
        GS.build_statement([d], ISSUED)
    except StatementLayoutError:
        return
    raise AssertionError("한 쪽보다 큰 묶음인데 중단 안 됨(무한 반복 위험)")


def test_check_reject() -> None:
    d = synthetic(True)
    d["settle_amount"] += 1
    assert len(GS.check(d)) >= 3, GS.check(d)            # 정산 금액 · 어디로 갔나요 · 입금 내역
    fake = FakeClient()
    try:
        GS.write_statement(fake, [d], ISSUED)
        raise AssertionError("검산 실패인데 쓰기 예외 없음")
    except GS.StatementCheckError:
        pass
    assert fake.calls == []


def test_multi_month() -> None:
    fake = FakeClient()
    try:
        GS.write_statement(fake, [synthetic(True), synthetic(False, "2026-10")], ISSUED)
        raise AssertionError("여러 판매 달인데 쓰기 거부 안 됨(D-241 ⑥)")
    except GS.StatementCheckError:
        pass
    assert fake.calls == []


# ── ③ 입구 ────────────────────────────────────────────────────
def test_tool() -> None:
    T = _tool()
    accts = ["홍길동-합성상회-aaa1", "김합성-다른상회-bbb2"]
    assert T.pick_accounts(accts, []) == accts and T.pick_accounts(accts, ["bbb2"]) == ["김합성-다른상회-bbb2"]
    try:
        T.pick_accounts(accts, ["ccc3"])
        raise AssertionError("없는 계정ID 인데 중단 안 됨")
    except ValueError:
        pass
    d = synthetic(True)
    assert T.statement_failures(d) == []
    d["checks"] = [{"검사": "합성 검사", "차이": 2}]
    d["settle_amount"] += 1
    got = T.statement_failures(d)
    assert got[0] == "합성 검사 차이 2" and len(got) >= 4, got
    base = ["--out", "o", "--managed-output", "m", "--settle-dir", "s", "--stats", "x.xlsx", "--basis", "2026-11-15"]
    assert T._args(base + ["--month", "2026-09", "--sheet", "id"]).month == "2026-09"
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            T._args(base + ["--sheet", "id"])
        raise AssertionError("--sheet 가 --month 없이 통과")
    except SystemExit:
        pass


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    for f in (test_cum_round, test_product_table, test_rg_kinds, test_failed_checks, test_load_judge, test_render, test_overflow,
              test_unsplittable, test_check_reject, test_multi_month, test_tool):
        f()
    print("✅ 위탁자 정산서 3차 형식 시험(숫자 반올림·상품표 열 합·종류별 끝전·검산 기준 · 그리기 구조·쪽 높이·결정 문구·넘침·검산/여러 달 거부 · 입구) 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
