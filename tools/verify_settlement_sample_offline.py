"""정산 표본 전후 계산 시험 도구(S1 · D-353 · `tools/settlement_sample.py`) 시험 — 오프라인 · 결정적 · 네트워크·로그인 없음.

기대값 = 작업 지시(11-19 통제 세션 S1 · 소유자 승인 "그 조건으로 진행하고 S1도 T-125 끝나면 시작해줘.")에서 손으로 정함:
  ① 저장 자료로 계산한 결과 = 저장 없이 원래 파일에서 바로 계산한 결과(같은 json) · 두 번째 계산은 원래 파일을 다시 읽지 않음.
  ② 원래 파일이 바뀌면(내용·크기 / 수정 시각만 / 같은 폴더에 새 파일 · 없던 선택 파일이 생김) 자동으로 다시 읽음 → 새 값.
  ③ diff = 금액 칸이 바뀐 곳을 전·후·차이로 잡음 · 안 바뀌면 금액 칸 변화 0 · 한쪽 오류도 보임.
  ④ 고르는 src 의 읽기 코드(읽는 동안 돈 파일)가 다르면 같은 저장 자료를 안 쓰고 다시 읽음.
  ⑤ 네트워크 막음(감사 훅) · 계정 3개 이상 = 중단 · worktree 면 저장 위치 = 본 저장소 output\\_표본캐시.
  ⑥ 실제 묶음(real_kit) = 지금 src 의 정산 함수 이름·인자가 도구가 부르는 그대로 있음(이름 바뀌면 여기서 실패).
합성 자료 = 계정 2개 · json(폴더 glob) + xlsx(openpyxl) + 선택 파일 + 출력 폴더 쓰기(지문에서 빠져야 함).

    python tools/verify_settlement_sample_offline.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import socket
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import settlement_sample as S  # noqa: E402
import settlement_sample_track as TR  # noqa: E402

LOADER = '''
import json
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
import openpyxl
CALLS = []
SCALE = 1

def load(args, out):
    CALLS.append(1)
    d = Path(args["data"])
    rows = {}
    for p in sorted(d.glob("*.json")):
        rows[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    wb = openpyxl.load_workbook(d / "fee.xlsx", read_only=True)
    fee = {str(r[0]): float(r[1]) for r in wb.active.iter_rows(min_row=2, values_only=True)}
    wb.close()
    opt = d / "opt.json"
    bonus = json.loads(opt.read_text(encoding="utf-8")) if opt.is_file() else {}
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "map.csv").write_text("x", encoding="utf-8")
    base = 3
    acc = defaultdict(lambda: [0, 0])                 # 정산 코드처럼 이름 없는 기본값 함수(기본 pickle 로는 저장 못 함)
    acc["x"][0] += 1
    return SimpleNamespace(accts=sorted(rows), rows=rows, fee=fee, bonus=bonus, acc=acc, add=lambda v: v + base)
'''


def _compute(ctx, accts, kind):
    out = {kind: {}, "오류": {}}
    for aid in accts:
        r = ctx.rows[aid]
        if kind == "old":
            sales = sum(x["amt"] for m in r.values() for x in m)
            out["old"][aid] = {"요약": {"관리 판매금액": sales, "정산 100% 일치(계정)": "일치", "계정ID": aid}, "1쪽": {"pay": sales - ctx.fee[aid]},
                               "자료": {"set": {3, 1, 2}}}
            continue
        ctx.fee[aid] = ctx.fee[aid] + 1000       # 계산이 ctx 를 바꿔도 다음 계산(kind)에 번지지 않아야 함
        for m, xs in sorted(r.items()):
            out["new"][f"{aid} {m}"] = {"settle_amount": sum(x["amt"] for x in xs) + ctx.bonus.get(aid, 0),
                                        "lines": [{"name": x["name"], "amount": x["amt"]} for x in xs], "note": "같음"}
    return out


def _env(tmp: Path):
    """합성 src(읽기 코드 1파일) · 자료 폴더 · 저장 폴더 → (kit, store, data, src)."""
    src, data, root = tmp / "src", tmp / "data", tmp / "cache"
    src.mkdir()
    data.mkdir()
    (src / "synth_loader.py").write_text(LOADER, encoding="utf-8")
    (data / "a1.json").write_text(json.dumps({"2026-10": [{"name": "1 판매", "amt": 1000}], "2026-11": [{"name": "1 판매", "amt": 500}]}), encoding="utf-8")
    (data / "b2.json").write_text(json.dumps({"2026-11": [{"name": "1 판매", "amt": 70}]}), encoding="utf-8")
    import openpyxl
    wb = openpyxl.Workbook()
    wb.active.append(["계정", "수수료"])
    wb.active.append(["a1", 100])
    wb.active.append(["b2", 7])
    wb.save(data / "fee.xlsx")
    store = S.Store(root, "합성")
    S.new_meta(store, {"data": str(data)}, ["a1", "b2"])
    return _kit(src), store, data, src


def _kit(src: Path) -> S.Kit:
    spec = importlib.util.spec_from_file_location(f"synth_loader_{time.monotonic_ns()}", src / "synth_loader.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod              # 실제 정산 모듈처럼 이름으로 찾을 수 있게(되살릴 때 그 모듈 전역을 씀)
    spec.loader.exec_module(mod)
    kit = S.Kit(src=src, load=mod.load, compute=_compute)
    kit.mod = mod   # type: ignore[attr-defined]
    return kit


def _run(kit, store, direct=False):
    logs: list = []
    res = S.run(kit, store, ["old", "new"], direct=direct, log=logs.append)
    return S.plain(res), logs


def _touch_later(p: Path) -> None:
    st = p.stat()
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))


def test_cached_equals_direct() -> None:
    with tempfile.TemporaryDirectory() as t:
        kit, store, _data, _src = _env(Path(t))
        direct, _ = _run(kit, store, direct=True)
        first, logs1 = _run(kit, store)
        second, logs2 = _run(kit, store)
        assert direct == first == second, (direct, first)
        assert len(kit.mod.CALLS) == 3, kit.mod.CALLS          # 바로 2(kind 마다 · pickle 안 거침) + 첫 저장 1 · 두 번째는 읽지 않음
        assert any(x.startswith("다시 읽음 — 저장 자료 없음") for x in logs1), logs1
        assert any(x.startswith("저장 자료 사용") for x in logs2), logs2
        assert first["new"]["a1 2026-10"]["settle_amount"] == 1000 and first["old"]["a1"]["1쪽"]["pay"] == 1400
        assert first["old"]["a1"]["자료"]["set"] == [1, 2, 3]   # set = 정렬 목록(결정적)
        c = store.load_ctx(store.meta()["entries"][0])
        assert c.acc["new"] == [0, 0] and c.acc["x"] == [1, 0] and c.add(4) == 7    # lambda·닫힌 값 되살림
        rev = S.plain(S.run(kit, store, ["new", "old"], log=lambda _x: None))
        assert rev["old"] == first["old"] and rev["new"] == first["new"]     # 계산마다 새로 푼 ctx(새 계산이 바꾼 값이 옛 계산에 안 번짐)
        e = store.meta()["entries"][0]
        files = set(e["fp"]["files"])
        assert {str((Path(t) / "data" / n).resolve()) for n in ("a1.json", "b2.json", "fee.xlsx")} <= files, files
        assert not [p for p in files if "map.csv" in p or p.endswith(".py")], files      # 출력 폴더·코드 = 지문 밖
        assert str((Path(t) / "data").resolve()) in e["fp"]["dirs"]
        assert list(e["code"]) == ["synth_loader.py"], e["code"]


def test_source_change_rereads() -> None:
    with tempfile.TemporaryDirectory() as t:
        kit, store, data, _src = _env(Path(t))
        _run(kit, store)
        (data / "a1.json").write_text(json.dumps({"2026-10": [{"name": "1 판매", "amt": 1234}]}), encoding="utf-8")
        res, logs = _run(kit, store)
        assert len(kit.mod.CALLS) == 2 and any("원래 자료 바뀜" in x and "a1.json" in x for x in logs), logs
        assert res["new"]["a1 2026-10"]["settle_amount"] == 1234 and "a1 2026-11" not in res["new"]
        _touch_later(data / "b2.json")                                   # 수정 시각만
        _run(kit, store)
        assert len(kit.mod.CALLS) == 3
        (data / "opt.json").write_text(json.dumps({"b2": 5}), encoding="utf-8")   # 없던 선택 파일이 생김(폴더 이름 목록)
        res, logs = _run(kit, store)
        assert len(kit.mod.CALLS) == 4 and any("폴더" in x for x in logs), logs
        assert res["new"]["b2 2026-11"]["settle_amount"] == 75
        _run(kit, store)
        assert len(kit.mod.CALLS) == 4                                   # 바뀐 것 없음 = 다시 안 읽음
        assert len(store.meta()["entries"]) == 1 and len(list(store.dir.glob("ctx_*.pkl"))) == 1   # 옛 pkl 지움


def test_code_change_rereads() -> None:
    with tempfile.TemporaryDirectory() as t:
        kit, store, _data, src = _env(Path(t))
        _run(kit, store)
        (src / "synth_loader.py").write_text(LOADER.replace("SCALE = 1", "SCALE = 2"), encoding="utf-8")
        kit2 = _kit(src)
        _res, logs = _run(kit2, store)
        assert len(kit2.mod.CALLS) == 1 and any("읽기 코드 다름" in x and "synth_loader.py" in x for x in logs), logs
        assert len(store.meta()["entries"]) == 2                          # src 마다 저장 자료(읽기 코드 지문)
        (src / "synth_loader.py").write_text(LOADER, encoding="utf-8")
        _res, logs = _run(_kit(src), store)
        assert any(x.startswith("저장 자료 사용 ctx_1.pkl") for x in logs), logs   # 원래 코드로 돌아오면 첫 저장 자료


def test_diff_catches_money() -> None:
    with tempfile.TemporaryDirectory() as t:
        kit, store, data, _src = _env(Path(t))
        before, _ = _run(kit, store)
        text, n = S.diff(before, before)
        assert n == 0 and "전부 같음 2건" in text and "전부 같음 3건" in text, text
        (data / "b2.json").write_text(json.dumps({"2026-11": [{"name": "1 판매", "amt": 90}]}), encoding="utf-8")
        after, _ = _run(kit, store)
        text, n = S.diff(before, after)
        assert "| 정산 금액 | 70 | 90 | 20 |" in text and "| 1~8 1. 1 판매 | 70 | 90 | 20 |" in text, text
        assert "| 요약 관리 판매금액 | 70 | 90 | 20 |" in text and "| 1쪽 pay | 63 | 83 | 20 |" in text, text
        assert n == 4, (n, text)
        broken = json.loads(json.dumps(after))
        broken["new"]["b2 2026-11"] = {"오류": "ValueError('x')"}
        broken["오류"] = {"new b2 2026-11": "ValueError('x')"}
        text, _n = S.diff(before, broken)
        assert "| 오류 | — | ValueError('x') |" in text and "❌ 후 오류 new b2 2026-11" in text, text
        buf = io.StringIO()
        a, b = Path(t) / "전.json", Path(t) / "후.json"
        S.write_json(before, a)
        S.write_json(after, b)
        with contextlib.redirect_stdout(buf):
            assert S.main(["diff", str(a), str(b), "--save", str(Path(t) / "전후.txt")]) == 0
        assert "금액 칸 바뀐 수 4" in buf.getvalue() and (Path(t) / "전후.txt").is_file()


def test_guards() -> None:
    TR.install(block_network=True)
    try:
        socket.getaddrinfo("example.com", 443)
        raise AssertionError("네트워크가 막히지 않음")
    except TR.NetworkBlocked:
        pass
    for bad in ("a,b,c", " , "):
        try:
            S._accounts(bad)
            raise AssertionError(bad)
        except SystemExit:
            pass
    assert S._accounts("x, y,x") == ["x", "y"]
    with tempfile.TemporaryDirectory() as t:
        wt = Path(t) / "repo" / ".claude" / "worktrees" / "w1"
        wt.mkdir(parents=True)
        (wt / ".git").write_text(f"gitdir: {Path(t) / 'repo' / '.git' / 'worktrees' / 'w1'}\n", encoding="utf-8")
        assert S.main_checkout(wt) == Path(t) / "repo"
        assert S.main_checkout(Path(t)) == Path(t)
    for bad in ("", "a/b", "..\\x"):
        try:
            S.Store(Path("."), bad)
            raise AssertionError(bad)
        except SystemExit:
            pass


def test_real_kit_wiring() -> None:
    import inspect
    kit = S.real_kit(ROOT / "src")
    from coupang_analytics import settlement_consignor_month as CM
    from coupang_analytics import settlement_statement_book as BK
    from coupang_analytics import settlement_statement_context as CTX
    from coupang_analytics import settlement_statement_deduct as DED
    from coupang_analytics import settlement_statement_sheets as SH
    from coupang_analytics import settlement_statement_source as SRC
    from coupang_analytics import gsheet_api
    assert kit.src == (ROOT / "src").resolve()
    for f in (CM.account_source, CM.build_month, CM.sale_months, CM.load_judge, DED.account, SH.shown, BK.summary_row, SRC.aid_of, CTX.load):
        assert callable(f)
    assert list(inspect.signature(CM.build_month).parameters) == ["ctx", "account", "month", "judge"]
    assert len(BK.SUM_HDR) == 16 and BK.SUM_HDR[2] == "계정ID"
    names = {f.name for f in __import__("dataclasses").fields(CTX.StatementArgs)}
    assert names == set(S.ARG_PATHS) | set(S.ARG_TEXT) | {"out", "only"}, names
    try:
        gsheet_api.GSheetClient("x")
        raise AssertionError("구글시트 막히지 않음")
    except TR.NetworkBlocked:
        pass


TESTS = [test_cached_equals_direct, test_source_change_rereads, test_code_change_rereads, test_diff_catches_money, test_guards,
         test_real_kit_wiring]


def main() -> int:
    getattr(sys.stdout, "reconfigure", lambda **k: None)(encoding="utf-8")
    bad = 0
    for t in TESTS:
        try:
            t()
            print(f"✅ {t.__name__}")
        except Exception as e:  # noqa: BLE001 — 시험 결과 표시용(실패는 끝 코드 1)
            bad += 1
            print(f"❌ {t.__name__}: {e!r}")
    print(f"{len(TESTS) - bad}/{len(TESTS)} 통과")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
