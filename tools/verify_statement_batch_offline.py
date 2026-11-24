"""정산서 배치 실행기 오프라인 검증(D-399 · 레인 A) — watch 완료 뒤 띄우기·재시작 보완·하루 1번·실패 계정 건너뜀·모듈 없음·잠금.

기대(소유자 11-24 · 계획 docs/plans/statement-batch-D399-plan-2026-11-24.md 설계 1~5):
  완료 = 띄움 · 24:00 미완료 = 안 띄움 · 같은 회차 두 번째 = 안 돎 · 완료 직후 죽음 → 재시작이 띄움 · 실패 계정 = 건너뛰고 '확인 필요'
  · 일 함수 모듈 없음 = 그 단계 '중단 — 모듈 없음'(다음 단계는 돎) · 잠금 = 두 번째 실행 막힘.
로그인·쿠팡·구글·실 일 함수 호출 없음 — 레인 B·D 일 함수는 가짜 모듈(sys.modules 주입)로, 자식 프로세스는 같은 프로세스에서
stage_main 을 부르는 가짜로 바꾼다(실 자식 프로세스 = 명령 줄 1건만 실제로 띄워 확인). 실패 = AssertionError → exit 1.

    python tools/verify_statement_batch_offline.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import types
from contextlib import contextmanager
from datetime import datetime as RealDT, timedelta
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

import openpyxl  # noqa: E402

import settlement_download as TD  # noqa: E402
from coupang_analytics import app_process as AP  # noqa: E402
from coupang_analytics import settlement_statement_context as SC  # noqa: E402
from coupang_analytics import settlement_stats as SS  # noqa: E402
from coupang_analytics import settlement_watch as W  # noqa: E402
from coupang_analytics import statement_batch as SB  # noqa: E402
from coupang_analytics import settlement_runlog as RLG  # noqa: E402
from coupang_analytics.registry_lock import registry_lock  # noqa: E402

CONS, SELDOC = SB.JOBS[0][2], SB.JOBS[1][2]
CALLS: dict = {}
SHEET = "가짜-위탁자정산서-시트"
SHEETS: dict = {}                       # 가짜 시트 {주소: {탭: 값}} — 실 구글 시트 쓰기 금지


class FakeSheet:
    """gsheet_api.GSheetClient 모양(ensure_sheet·batch_update·write_values) — 쓴 값만 기억."""

    def __init__(self, url, log):
        self.tabs = SHEETS.setdefault(url, {})

    def ensure_sheet(self, title):
        self.tabs.setdefault(title, [["옛 값"] * 3] * 9)
        return 77

    def batch_update(self, reqs):
        assert reqs == [{"updateCells": {"range": {"sheetId": 77}, "fields": "userEnteredValue"}}], reqs
        self.tabs[SB.CHECK_TAB] = []

    def write_values(self, sheet, rows, start="A1", raw=False):
        assert start == "A1" and raw and self.tabs[sheet] == [], (start, raw)   # 지운 뒤 씀(옛 줄 안 남음)
        self.tabs[sheet] = rows


class DeniedSheet(FakeSheet):
    def ensure_sheet(self, title):
        from coupang_analytics.gsheet_api import GSheetError
        raise GSheetError("권한 없음(가짜)")


def ok(msg):
    print(f"  ✔ {msg}")


def _patched(obj_attrs: list, fn):
    """[(객체, 이름, 값)] 을 잠시 바꿔 fn() 실행 후 되돌림(verify_settlement_runtime_offline 과 같은 방식)."""
    olds = [(o, n, getattr(o, n)) for o, n, _v in obj_attrs]
    try:
        for o, n, v in obj_attrs:
            setattr(o, n, v)
        return fn()
    finally:
        for o, n, v in olds:
            setattr(o, n, v)


@contextmanager
def _workdir():
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            Path("output").mkdir()
            yield Path(tmp)
        finally:
            os.chdir(cwd)


def _stats_file(name: str, current: bool = True) -> Path:
    p = TD.BASE / name
    p.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    wb.active.title = "정산"
    if current:
        wb.create_sheet(SS.COST_OPTIONS).append(list(SS.COST_OPTIONS_HEAD))
    wb.save(p)
    return p


def _inputs() -> None:
    SB.INPUTS.mkdir(parents=True, exist_ok=True)
    for n in SC.REQUIRED:
        (SB.INPUTS / n).write_bytes(b"x")
    SB.SELDOC_INPUTS.mkdir(parents=True, exist_ok=True)
    (SB.SELDOC_INPUTS / "계약DB_사본.xlsx").write_bytes(b"x")


def _done(key: str, fails: dict | None = None, write_fails: bool = True) -> None:
    fails = fails or {}
    if write_fails:
        SB.write_failures(TD.DONE_FAILS_FILE, key, fails)
    W.write_done(TD.DONE_FILE, key, "done", "✅ 다 받음", failed=len(fails))


def _fake_job(kind: str):
    def run_job(opts, on_log):
        CALLS.setdefault(kind, []).append(opts)
        on_log(f"가짜 {kind} 일 함수 시작")
        if kind == "boom":
            raise RuntimeError("가짜 일 함수 예외")
        if kind == "bad":
            return {"ok": ["a"]}
        out = Path(opts["out"])
        out.mkdir(parents=True, exist_ok=True)
        f = out / ("정산서_가짜.xlsx" if kind == "consignor" else "셀독정산서_가짜.xlsx")
        f.write_bytes(b"x")
        skipped = [{"id": "acc9", "reason": f"{kind} 판정 없음", "account": "김위탁-위탁상사-acc9", "contract": "계약-7",
                    "product": "보냉백", "amount": 12000}]
        return {"ok": ["acc1"], "skipped": skipped, "files": [f], "abort": None,
                **({"sheet": SHEET} if kind == "consignor" else {})}
    mod = types.ModuleType(kind)
    mod.run_job = run_job
    return mod


def _inproc(stage, opts_p, res_p, run_id):
    """가짜 자식 — stats = 정산집계 새로 만듦(결과 JSON 'out') · 그 밖 = 같은 프로세스에서 stage_main(실제 자식 쪽 코드)."""
    CALLS.setdefault("stage", []).append(stage)
    if stage == SB.STATS:
        res_p.write_text(json.dumps({"out": str(_stats_file(f"정산집계_{run_id}.xlsx").resolve())}), encoding="utf-8")
        return 0
    return SB.stage_main(stage, opts_p, res_p)


def _batch(cycle: str, jobs: dict | None = None, **kw) -> int:
    """가짜 B·D 모듈 주입 + 가짜 자식으로 run_batch 한 번(echo 끔)."""
    jobs = jobs if jobs is not None else {CONS: _fake_job("consignor"), SELDOC: _fake_job("seldoc")}
    keep = {k: sys.modules.get(k) for k in jobs}
    sys.modules.update(jobs)
    try:
        return _patched([(SB, "RUNNER", _inproc), (SB, "SHEET_CLIENT", kw.pop("client", FakeSheet))], lambda: SB.run_batch(cycle, TD.DONE_FILE, TD.DONE_FAILS_FILE,
                                                                       echo=lambda m: None, **kw))
    finally:
        for k, v in keep.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _status() -> str:
    return next((ln.split(":", 1)[1].strip() for ln in SB.STATUS.read_text(encoding="utf-8").splitlines()
                 if ln.startswith("상태:")), "")


def b1_full_run_and_failed_accounts():
    print("[B1] 가짜 B·D 로 배치 끝까지 — 정산집계 없음 = stats 자식 1번 · 실패 계정 = 건너뛰고 '확인 필요' · 보고·기록·상태")
    CALLS.clear()
    SHEETS.clear()
    with _workdir():
        _inputs()
        key = "2026-11-21T01:30:00"
        _done(key, {"홍길동-길동상사-acc2": "로그인", RLG.ALL: "받기 의심"})
        assert _batch(key) == 0
        assert CALLS["stage"] == [SB.STATS, "consignor", "seldoc"], CALLS["stage"]     # 첫 배치 = 차이 비교 안 함
        c, s = CALLS["consignor"][0], CALLS["seldoc"][0]
        assert c["skip_accounts"] == {"홍길동-길동상사-acc2": "로그인"}, c["skip_accounts"]   # '(전체)' = 계정 아님 → 보고만
        assert c["cycle"] == key and Path(c["stats"]).name.startswith("정산집계_") and c["sheet"] is True, c
        assert s["consignor"]["files"] and s["consignor"]["state"] == SB.CHECK, s["consignor"]   # 셀독 = 위탁 결과를 받음
        rec = json.loads(SB.RECORD.read_text(encoding="utf-8"))
        assert rec["cycle"] == key and rec["result"] == "일부 실패 --> 확인 필요", rec
        assert rec["stages"][SB.DIFF]["state"] == SB.SKIP and "첫 배치" in rec["stages"][SB.DIFF]["note"], rec["stages"]
        rep = Path(rec["report"]).read_text(encoding="utf-8")
        for want in ("확인 필요 — 홍길동-길동상사-acc2 — 로그인", f"확인 필요 — {RLG.ALL} — 받기 의심",
                     "확인 필요 — acc9 — consignor 판정 없음", "확인 필요 — acc9 — seldoc 판정 없음", "만든 1: acc1"):
            assert want in rep, (want, rep)
        assert Path(rec["report"]).parent.resolve() == SB.REPORTS.resolve() and Path(rec["report"]).name.startswith("배치보고_")
        assert _status() == SB.ST_CHECK, _status()
        # 확인 필요 한 목록 = 구글시트 '확인 필요' 탭(덮어쓰기) · 상태 내용 줄 'N건' + 위 몇 건 · 보고 표 · 기록
        day = RealDT.now().date().isoformat()
        want = [[day, "정산 받기", "", "홍길동-길동상사-acc2", "", "", "", "정산 받기 실패 — 로그인"],
                [day, "정산 받기", "", RLG.ALL, "", "", "", "정산 받기 실패 — 받기 의심"],
                [day, "위탁정산서", "acc9", "김위탁-위탁상사-acc9", "계약-7", "보냉백", "12000", "consignor 판정 없음"],
                [day, "셀독 정산서", "acc9", "김위탁-위탁상사-acc9", "계약-7", "보냉백", "12000", "seldoc 판정 없음"]]
        assert SHEETS[SHEET][SB.CHECK_TAB] == [SB.CHECK_HEAD, *want], SHEETS
        assert rec["확인필요"] == want and rec["stages"]["check_tab"]["state"] == SB.OK, rec["stages"]["check_tab"]
        stat = SB.STATUS.read_text(encoding="utf-8")
        assert "확인 필요 4건" in stat and "확인 필요: 위탁정산서 · acc9 · consignor 판정 없음" in stat, stat
        assert "## 확인 필요 4건" in rep and "| 위탁정산서 | acc9 | 김위탁-위탁상사-acc9 | 계약-7 | 보냉백 | 12000 |" in rep, rep
        logs = list(SB.LOGS.glob("배치_*.log"))
        assert len(logs) == 1 and "가짜 consignor 일 함수 시작" in logs[0].read_text(encoding="utf-8")
    ok("끝까지 돎 · 실패 계정·건너뛴 계약 = 보고 '확인 필요 — 사유' · 기록·상태(완료·확인 필요)·상세 로그")


def b2_same_cycle_once_and_diff():
    print("[B2] 같은 회차 두 번째 = 안 돎(하루 1번) · 다음 회차 = 지난 배치와 차이 비교(검산 도구 출력 파일·요약) · 옛 집계 = stats 1번")
    CALLS.clear()
    with _workdir() as tmp:
        _inputs()
        _stats_file("정산집계_261120_010000.xlsx")
        k1 = "2026-11-21T01:30:00"
        _done(k1)
        assert _batch(k1) == 0 and CALLS["stage"] == ["consignor", "seldoc"], CALLS["stage"]   # 최신 집계 형식 맞음 = stats 안 함
        first = json.loads(SB.RECORD.read_text(encoding="utf-8"))
        assert first["result"] == "일부 실패 --> 확인 필요", first
        CALLS.clear()
        assert _batch(k1) == 0 and not CALLS, CALLS                                    # 같은 회차 = 일 함수 안 부름
        assert json.loads(SB.RECORD.read_text(encoding="utf-8"))["run_id"] == first["run_id"]
        # 다음 회차 — 최신 집계가 옛 형식 → stats 1번 · 차이 비교 = 지난 배치 위탁 폴더와
        tool = tmp / "도구" / SB.DIFF_TOOL
        tool.parent.mkdir()
        tool.write_text("import sys\nsys.stdout.reconfigure(encoding='utf-8')\nprint('독립 검산 1/1')\n"
                        "print('비교', sys.argv[1], sys.argv[2])\nprint('계정 수', 1, 1, '일치', 1)\n", encoding="utf-8")
        _stats_file("정산집계_261121_090000.xlsx", current=False)
        k2 = "2026-11-22T01:30:00"
        _done(k2)
        CALLS.clear()
        assert _patched([(SB, "tools_dir", lambda: tool.parent)], lambda: _batch(k2)) == 0
        assert CALLS["stage"] == [SB.STATS, "consignor", "seldoc", SB.DIFF], CALLS["stage"]
        rec = json.loads(SB.RECORD.read_text(encoding="utf-8"))
        d = rec["stages"][SB.DIFF]
        assert d["state"] == SB.OK and "독립 검산 1/1" in d["note"] and "계정 수 1 1 일치 1" in d["note"], d
        txt = Path(d["files"][0]).read_text(encoding="utf-8")
        assert f"비교 {rec['stages']['consignor']['out']} {first['stages']['consignor']['out']}" in txt, txt
        # 검산 도구가 없는 묶음(배포 spec 에 안 넣음) = 그 단계 '중단 — 검산 도구 없음'(조용히 넘기지 않음)
        k3 = "2026-11-23T01:30:00"
        _done(k3)
        assert _patched([(SB, "tools_dir", lambda: tmp / "없음")], lambda: _batch(k3)) == 1
        d = json.loads(SB.RECORD.read_text(encoding="utf-8"))["stages"][SB.DIFF]
        assert d["state"] == SB.STOP and "검산 도구 없음" in d["abort"], d
        assert _status() == SB.ST_STOP
    ok("같은 회차 = 안 돎 · 다음 회차 = 차이 비교(새·지난 폴더 · 출력 파일 · 요약 줄) · 옛 집계 = stats 1번 · 도구 없음 = 중단")


def b3_missing_module_and_bad_jobs():
    print("[B3] 일 함수 모듈 없음 = '중단 — 모듈 없음'(다음 단계는 돎) · 일 함수 예외·약속과 다른 꼴 = 그 단계만 중단")
    CALLS.clear()
    with _workdir():
        _inputs()
        _stats_file("정산집계_261120_010000.xlsx")
        key = "2026-11-21T01:30:00"
        _done(key)
        gone = "coupang_analytics._없는_정산서_모듈_시험"
        jobs = ((SB.JOBS[0][0], SB.JOBS[0][1], gone), SB.JOBS[1])
        assert _patched([(SB, "JOBS", jobs)], lambda: _batch(key)) == 1
        rec = json.loads(SB.RECORD.read_text(encoding="utf-8"))
        assert rec["stages"]["consignor"]["state"] == SB.STOP and rec["stages"]["consignor"]["abort"] == f"모듈 없음 — {gone}", rec
        assert rec["stages"]["seldoc"]["state"] == SB.CHECK and CALLS["seldoc"], rec["stages"]["seldoc"]   # 다음 단계는 돎
        assert rec["result"] == "오류 발생 --> 중단" and _status() == SB.ST_STOP
        assert f"중단 — 모듈 없음 — {gone}" in Path(rec["report"]).read_text(encoding="utf-8")
        _done("2026-11-22T01:30:00")
        assert _batch("2026-11-22T01:30:00", {CONS: _fake_job("boom"), SELDOC: _fake_job("bad")}) == 1
        st = json.loads(SB.RECORD.read_text(encoding="utf-8"))["stages"]
        assert st["consignor"]["abort"] == "RuntimeError: 가짜 일 함수 예외", st["consignor"]
        assert "결과 꼴이 약속과 다름" in st["seldoc"]["abort"], st["seldoc"]
        log = "".join(p.read_text(encoding="utf-8") for p in SB.LOGS.glob("배치_*.log"))
        assert "Traceback" in log and "가짜 일 함수 예외" in log                         # 전체 추적 = 상세 로그
    ok("모듈 없음·예외·꼴 다름 = 그 단계만 '중단'(사유·추적 기록) · 다른 단계는 끝까지")


def b4_not_done_failed_names_inputs():
    print("[B4] '완료' 기록 없음 = 안 돎 · 실패 수는 있는데 이름 기록 없음 = '성공 계정만' 못 지켜 중단 · 입력 없음 = 그 종류만 중단")
    CALLS.clear()
    with _workdir():
        _inputs()
        _stats_file("정산집계_261120_010000.xlsx")
        assert _batch("2026-11-21T01:30:00") == 2 and not CALLS and not SB.RECORD.exists()   # 24:00 미완료 날
        assert _status() == SB.ST_STOP
        key = "2026-11-21T01:30:00"
        _done(key, {"홍길동-길동상사-acc2": "로그인"}, write_fails=False)
        assert _batch(key) == 1 and not CALLS.get("consignor") and not CALLS.get("seldoc"), CALLS
        st = json.loads(SB.RECORD.read_text(encoding="utf-8"))["stages"]
        assert "이름 기록" in st["consignor"]["abort"] and "이름 기록" in st["seldoc"]["abort"], st
        for p in SB.SELDOC_INPUTS.iterdir():
            p.unlink()
        (SB.INPUTS / SC.REQUIRED[0]).unlink()
        k2 = "2026-11-22T01:30:00"
        _done(k2)
        CALLS.clear()
        assert _batch(k2) == 1 and not CALLS.get("consignor") and not CALLS.get("seldoc"), CALLS
        st = json.loads(SB.RECORD.read_text(encoding="utf-8"))["stages"]
        assert SC.REQUIRED[0] in st["consignor"]["abort"] and "입력 없음" in st["seldoc"]["abort"], st
        assert st["inputs"]["state"] == SB.CHECK, st["inputs"]
    ok("미완료 날 = 안 돎(기록 없음) · 실패 이름 없음 = 중단 · 입력 없는 종류 = 그 종류만 중단")


def b5_lock():
    print("[B5] 잠금 — 배치가 도는 중이면 두 번째 실행 = 아무것도 안 하고 종료(상태 파일 안 건드림)")
    CALLS.clear()
    assert SB.LOCK.as_posix() == "output/정산서/_잠금/_배치.lock", SB.LOCK                 # 계획 설계 4 경로
    with _workdir():
        _inputs()
        _stats_file("정산집계_261120_010000.xlsx")
        key = "2026-11-21T01:30:00"
        _done(key)
        with registry_lock(SB.LOCK, wait_sec=0):
            assert _batch(key) == 0
        assert not CALLS and not SB.RECORD.exists() and not SB.STATUS.exists(), CALLS
        assert _batch(key) == 0 and CALLS["consignor"]                                # 잠금 풀린 뒤 = 돎
    ok("잠금 중 = 막힘 · 풀린 뒤 = 돎")


def b7_check_tab_edges():
    print("[B7] 확인 필요 탭 — 다음 배치 = 덮어쓰기(0건 = '없음' 한 줄) · 시트 주소 없음 = 안 씀(보고) · 쓰기 실패 = 확인 필요 목록에")
    CALLS.clear()
    SHEETS.clear()
    with _workdir():
        _inputs()
        _stats_file("정산집계_261120_010000.xlsx")

        def clean(kind):
            def run_job(opts, on_log):
                return {"ok": ["acc1"], "skipped": [], "files": [], "abort": None, **({"sheet": SHEET} if kind else {})}
            return types.SimpleNamespace(run_job=run_job)
        SHEETS[SHEET] = {SB.CHECK_TAB: [["옛 확인 필요 줄"] * 8] * 30}
        _done("2026-11-21T01:30:00")
        assert _batch("2026-11-21T01:30:00", {CONS: clean("sheet"), SELDOC: clean("")}) == 0
        assert SHEETS[SHEET][SB.CHECK_TAB] == [SB.CHECK_HEAD, ["", "", "", "", "", "", "", "확인 필요 없음"]], SHEETS
        rec = json.loads(SB.RECORD.read_text(encoding="utf-8"))
        assert rec["result"] == "정상 완료" and _status() == SB.ST_DONE and "확인 필요 0건" in SB.STATUS.read_text(encoding="utf-8")
        _done("2026-11-22T01:30:00")
        assert _batch("2026-11-22T01:30:00", {CONS: clean(""), SELDOC: clean("")}) == 0
        ct = json.loads(SB.RECORD.read_text(encoding="utf-8"))["stages"]["check_tab"]
        assert ct["state"] == SB.SKIP and "시트 주소 없음" in ct["note"], ct
        _done("2026-11-23T01:30:00")
        assert _batch("2026-11-23T01:30:00", {CONS: clean("sheet"), SELDOC: clean("")}, client=DeniedSheet) == 0
        rec = json.loads(SB.RECORD.read_text(encoding="utf-8"))
        assert rec["stages"]["check_tab"]["state"] == SB.CHECK and rec["result"] == "일부 실패 --> 확인 필요", rec["stages"]
        assert rec["확인필요"][-1][1] == f"'{SB.CHECK_TAB}' 탭" and "권한 없음(가짜)" in rec["확인필요"][-1][7], rec["확인필요"]
        assert _status() == SB.ST_CHECK and "권한 없음(가짜)" in Path(rec["report"]).read_text(encoding="utf-8")
    ok("덮어쓰기(옛 줄 안 남음 · 0건 = '없음') · 주소 없음 = 안 씀 · 쓰기 실패 = 확인 필요(상태·보고)")


def b6_real_child_process():
    print("[B6] 실제 자식 프로세스 1건 — 정산 프로그램 명령(statements --stage)·결과 JSON·없는 모듈 = '모듈 없음'")
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        opts_p, res_p, log_p = t / "입력.json", t / "결과.json", t / "배치.log"
        gone = "coupang_analytics._없는_정산서_모듈_시험"
        opts_p.write_text(json.dumps({"log": str(log_p), "module": gone}, ensure_ascii=False), encoding="utf-8")
        cmd, cwd = SB._child_cmd("consignor", opts_p, res_p, "261121_013000")
        assert cmd[1:2] == [str(ROOT / "tools" / "settlement_download.py")] and cmd[2:4] == ["statements", "--stage"], cmd
        env = {**os.environ, "COUPANG_DATA_ROOT": str(t / "데이터")}
        r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, timeout=300,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        assert r.returncode == 0, (r.returncode, r.stderr.decode("utf-8", "replace")[-2000:])
        res = json.loads(res_p.read_text(encoding="utf-8"))
        assert res == {"ok": [], "skipped": [], "files": [], "abort": f"모듈 없음 — {gone}"}, res
        assert not (t / "데이터" / "output" / "정산" / "로그").exists()              # 정산 받기 로그·상태 안 만듦
    ok("자식 명령 줄·데이터 폴더·결과 JSON 실제로 맞음 · 정산 받기 로그 안 건드림")


class Crash(BaseException):
    """가상 강제 종료(작업관리자·재부팅) — except Exception 에 안 잡힘."""


def _watch(start, pending, *, fails=None, crash_after_done=False):
    """가짜 시계로 cmd_watch 한 번(P74 방식) → (띄운 명령들, 예외). 바퀴 = 한 일 1 · pending(n) = 생성 대기 수."""
    clock = {"now": start}
    spawned: list = []
    n = {"pass": 0}

    class FakeDT(RealDT):
        @classmethod
        def now(cls, tz=None):
            return clock["now"]

    def fake_sleep(sec):
        clock["now"] += timedelta(seconds=max(sec, 1))

    def one(args):
        n["pass"] += 1
        TD.LOG = RLG.RunLog(TD.BASE, now=clock["now"], echo=lambda m: None)
        TD.LOG.heartbeat = lambda *a, **k: None
        TD.TRIES.begin_pass(f"p{n['pass']}")
        TD.REST_PLAN.clear()
        clock["now"] += timedelta(minutes=3)
        return False, 0

    real_done = W.write_done

    def done_then_crash(*a, **k):
        real_done(*a, **k)
        raise Crash("완료 기록 직후 강제 종료")

    def spawn(cmd, cwd):
        spawned.append(cmd)
        return SimpleNamespace(pid=4321), None, ""
    args = SimpleNamespace(parent=0, ledger_synced=True, until="", until_at=None, hidden=False, manual=False, start=None)
    log0 = RLG.RunLog(TD.BASE, now=clock["now"], echo=lambda m: None)
    log0.heartbeat = lambda *a, **k: None
    patches = [(TD, "datetime", FakeDT), (TD.time, "sleep", fake_sleep), (TD, "_one_pass", one), (TD, "_rest_pass", one),
               (TD, "_pending_jobs", lambda: pending(n["pass"])), (TD, "_watch_wait_reason", lambda *a, **k: ("", None)),
               (TD, "_between_passes", lambda: None), (TD, "_cycle_sources", lambda a: None),
               (TD, "_evidence_sweep", lambda a, act: None), (TD, "_watch_failures", lambda: dict(fails or {})),
               (TD, "LOG", log0), (TD, "TRIES", None), (AP, "_spawn_detached", spawn)]
    if crash_after_done:
        patches.append((W, "write_done", done_then_crash))
    try:
        _patched(patches, lambda: TD.cmd_watch(args))
    except Crash as exc:
        return spawned, exc
    return spawned, None


def w1_watch_spawn():
    print("[W1] watch 완료 → 실패 계정 이름 기록(완료 기록보다 먼저) → statements --cycle <회차> 띄움 · 24:00 미완료 = 안 띄움")
    with _workdir():
        t0 = RealDT(2026, 11, 21, 2, 0)
        spawned, err = _watch(t0, lambda k: 0, fails={"홍길동-길동상사-acc2": "로그인"})
        done = W.read_done(TD.DONE_FILE)
        assert err is None and done and done["result"] == "완료", (err, done)
        assert len(spawned) == 1 and spawned[0][-3:] == ["statements", "--cycle", done["key"]], spawned
        assert spawned[0][1] == str(ROOT / "tools" / "settlement_download.py"), spawned       # 개발 = python tools/…
        f = json.loads(TD.DONE_FAILS_FILE.read_text(encoding="utf-8"))
        assert f == {"key": done["key"], "accounts": {"홍길동-길동상사-acc2": "로그인"}}, f
    with _workdir():
        spawned, err = _watch(RealDT(2026, 11, 21, 22, 0), lambda k: 1)               # 생성 대기가 24:00 까지 남음
        assert err is None and not spawned and not TD.DONE_FILE.exists(), spawned
    ok("완료 = 띄움(개발 = python tools/settlement_download.py statements --cycle) · 실패 이름 먼저 · 미완료 = 안 띄움")


def w2_crash_then_resume():
    print("[W2] 완료 기록 직후 죽음 → 재시작(--resume) '이미 끝남' 에서 정산서 기록 없으면 띄움 · 기록 있으면 안 띄움")
    with _workdir():
        t0 = RealDT(2026, 11, 21, 2, 0)
        spawned, err = _watch(t0, lambda k: 0, crash_after_done=True)
        assert isinstance(err, Crash) and not spawned and W.read_done(TD.DONE_FILE), (err, spawned)
        key = W.read_done(TD.DONE_FILE)["key"]
        spawned, err = _watch(t0 + timedelta(minutes=10), lambda k: 0)                 # 재시작 = 이미 끝남 분기
        assert err is None and len(spawned) == 1 and spawned[0][-3:] == ["statements", "--cycle", key], spawned
        SB._write_json(SB.RECORD, {"cycle": key, "result": "정상 완료"})               # 배치가 돌고 기록을 남김
        spawned, err = _watch(t0 + timedelta(minutes=20), lambda k: 0)
        assert err is None and not spawned, spawned                                    # 같은 회차 = 다시 안 띄움
        SB.RECORD.write_text("{깨짐", encoding="utf-8")                                  # 깨진 기록 = 띄워서 배치가 사유 보고
        spawned, err = _watch(t0 + timedelta(minutes=30), lambda k: 0)
        assert len(spawned) == 1, spawned
    ok("완료 직후 죽어도 재시작이 띄움 · 같은 회차 기록 있으면 안 띄움 · 깨진 기록 = 띄워 보고")


def main():
    b1_full_run_and_failed_accounts()
    b2_same_cycle_once_and_diff()
    b3_missing_module_and_bad_jobs()
    b4_not_done_failed_names_inputs()
    b5_lock()
    b6_real_child_process()
    b7_check_tab_edges()
    w1_watch_spawn()
    w2_crash_then_resume()
    print("정산서 배치 실행기 오프라인 검증 통과")


if __name__ == "__main__":
    main()
