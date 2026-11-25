"""정산서 배치 실행기(D-399 · D-204 1·3·4·5단계 · 모두싸인 2단계 보류) — 정산 받기 '완료' 뒤 사람 손 없이 정산서를 만든다.

띄우는 곳 = 정산 프로그램(`tools/settlement_download.py` · 배포 = `정산다운로드.exe`). watch 가 `_완료.json` 을 쓴 직후,
그리고 재시작(--resume)이 '이미 끝남'에 걸렸을 때 이번 회차 배치 기록이 없으면 `statements --cycle <회차>` 를 따로 띄운다.
24:00 까지 못 끝난 날(`_완료.json` 없음) = 안 돎(소유자 11-24).

순서(각 단계 = 자식 프로세스 `statements --stage …` · 메모리 격리 · 한 단계가 실패해도 다음 단계는 돎):
  ① 입력 확인(위탁 = 입력 폴더 고정 이름 8종 · 셀독 = `입력_셀독` 폴더) — 없으면 그 종류만 '중단'
  ② 최신 `정산집계_*.xlsx`(없거나 옛 형식 = `stats` 자식 1번)
  ③ 위탁정산서(`statement_jobs_consignor.run_job`) ④ 셀독 정산서(`statement_jobs_seldoc.run_job`)
  ⑤ 지난 배치 위탁정산서와 차이 비교(`tools/check_settlement_statements.py`) ⑥ 보고 파일
일 함수 약속(레인 B·D) = `run_job(opts: dict, on_log) -> {"ok": [...], "skipped": [{"id", "reason"}], "files": [...],
"abort": str | None}` · 모듈이 없으면 그 단계 = '중단 — 모듈 없음'(조용히 넘기지 않음).

실패 계정(`_완료_실패계정.json` · watch 가 `_완료.json` 직전에 씀) = 건너뛰고 '확인 필요 — 사유'(소유자 '성공 계정만').
'확인 필요' 한 목록(실패 계정·건너뛴 계정·계약·단계 중단 · 칸 = 날짜·종류·ID·계정·계약·상품명·금액·사유) = 운용자가 로그 없이
보게 세 곳(소유자 11-24 "확인필요 탬에 넣어줘"): ① 위탁자정산서 구글시트 '확인 필요' 탭(위탁 일 함수가 결과에 쓴 시트 `sheet` ·
매 배치 덮어쓰기 · 위탁자정산서 그리기 함수는 안 고침) ② 상태 파일 내용 줄 '확인 필요 N건' + 위 몇 건 ③ 보고 파일 표.
회차 기준 하루 1번(`_배치기록.json`) · 잠금 `_잠금/_배치.lock`(registry_lock · OS 잠금) · 상태 `_현재상태.txt`(정산 받기
상태와 같은 '라벨: 값' 꼴) · 보고 `보고/배치보고_YYMMDD_HHMMSS.md` · 상세 로그 `로그/배치_YYMMDD_HHMMSS.log`.
"""
from __future__ import annotations

import importlib
import json
import os
import runpy
import subprocess
import sys
import tempfile
import traceback
from contextlib import redirect_stdout
from datetime import date, datetime
from pathlib import Path

from . import settlement_read_store as READS
from . import settlement_store as STORE
from . import settlement_watch as W
from .registry_lock import RegistryLockError, registry_lock

ROOT_DIR = STORE.BASE.parent / "정산서"                 # output/정산서(상대경로 = set_workdir 기준)
RECORD = ROOT_DIR / "_배치기록.json"
LOCK = ROOT_DIR / "_잠금" / "_배치.lock"
STATUS = ROOT_DIR / "_현재상태.txt"
REPORTS = ROOT_DIR / "보고"
LOGS = ROOT_DIR / "로그"
INPUTS = ROOT_DIR / "입력"
SELDOC_INPUTS = ROOT_DIR / "입력_셀독"
STATS_GLOB = "정산집계_*.xlsx"
STAGE_TIMEOUT_SEC = 3 * 3600          # 단계 하나 상한(개발 PC 실측 위탁 약 21분 · 셀독 읽기 약 7분 · 집계 약 16분)
DIFF_TOOL = "check_settlement_statements.py"
DIFF = "diff"
STATS = "stats"
# (단계, 이름, 일 함수 모듈) — 레인 B·D 약속 경로
JOBS = (("consignor", "위탁정산서", "coupang_analytics.statement_jobs_consignor"),
        ("seldoc", "셀독 정산서", "coupang_analytics.statement_jobs_seldoc"))
OK, CHECK, STOP, SKIP = "정상", "확인 필요", "중단", "건너뜀"
# 상태(_현재상태.txt '상태:' · 정산 탭 배지 settlement_status_panel_qt._BADGE)
ST_RUN, ST_DONE, ST_CHECK, ST_STOP = "정산서 작동중", "정산서 완료", "정산서 완료·확인 필요", "정산서 중단"
VERDICT = {OK: ("정상 완료", ST_DONE), CHECK: ("일부 실패 --> 확인 필요", ST_CHECK), STOP: ("오류 발생 --> 중단", ST_STOP)}
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CHECK_TAB = "확인 필요"
CHECK_HEAD = ["날짜", "종류", "ID", "계정", "계약", "상품명", "금액", "사유"]
CHECK_TOP = 5                         # 상태 파일에 보여 줄 확인 필요 줄 수


# ── 기록 파일 ─────────────────────────────────────────────
def _write_json(path: Path, data) -> None:
    """원자적 쓰기(임시 파일 → 바꿔 끼우기 · 읽는 쪽이 반쪽 파일을 보지 않게)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1, default=str)
    os.replace(tmp, path)


def _read_json(path: Path) -> tuple[dict | None, str]:
    """(내용, 사유) — 없음 = (None, '') · 깨짐 = (None, 사유)."""
    if not path.exists():
        return None, ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"{path} 읽기 실패: {exc.__class__.__name__}: {exc}"
    return (data, "") if isinstance(data, dict) else (None, f"{path} 꼴이 다름(사전 아님)")


def read_record(path: Path = RECORD) -> tuple[dict | None, str]:
    return _read_json(path)


def ran_for(cycle: str, path: Path = RECORD) -> tuple[bool, str]:
    """이번 회차 배치 기록이 있나 → (있음, 기록 읽기 사유). 깨진 기록 = (False, 사유) — 배치가 떠서 그 사유로 중단 보고."""
    rec, why = read_record(path)
    return bool(rec and rec.get("cycle") == cycle), why


def write_failures(path: Path, key: str, fails: dict) -> None:
    """watch 가 `_완료.json` 직전에 — 이번 회차 실패로 끝난 계정 {계정명: 사유}(정산서 배치가 건너뜀 · D-399)."""
    _write_json(path, {"key": key, "accounts": {str(k): str(v) for k, v in fails.items()}})


def failed_accounts(done: dict, fails_file: Path, cycle: str) -> tuple[dict, dict, str]:
    """(건너뛸 계정 {계정명: 사유}, 계정 아닌 실패 {이름: 사유}, 중단 사유). 계정명 = '대표자-사업자-계정ID'(SA.display_name ·
    끝이 '-계정ID') · '(전체)' 같은 이름은 계정이 아니라 보고에만. 완료 기록에 실패 수가 있는데 이름 기록이 없거나 다른 회차면
    '성공 계정만' 을 지킬 수 없어 중단 사유."""
    data, why = _read_json(fails_file)
    if why:
        return {}, {}, why
    if not data or data.get("key") != cycle:
        if int(done.get("failed") or 0):
            return {}, {}, (f"정산 받기 실패 {done.get('failed')}계정의 이름 기록({fails_file})이 이번 회차({cycle}) 것이 아님 — "
                            "성공 계정만 만들 수 없어 중단")
        return {}, {}, ""
    accts = data.get("accounts") or {}
    skip = {n: r for n, r in accts.items() if "-" in n}
    return skip, {n: r for n, r in accts.items() if n not in skip}, ""


# ── 로그·상태 ─────────────────────────────────────────────
class BatchLog:
    """상세 로그(줄마다 시각) + 상태 파일(덮어쓰기 · 정산 받기 heartbeat 와 같은 '라벨: 값' 꼴)."""

    def __init__(self, run_id: str, echo=print):
        self.run_id, self.echo = run_id, echo
        self.path = LOGS / f"배치_{run_id}.log"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def line(self, msg: str) -> None:
        append_log(self.path, msg)
        self.echo(msg)

    def status(self, state: str, detail: str, extra: tuple[str, ...] = ()) -> None:
        STATUS.parent.mkdir(parents=True, exist_ok=True)
        lines = ["정산서 배치 — 현재 상태", f"갱신: {datetime.now():%Y-%m-%d %H:%M:%S}", f"상태: {state}",
                 f"내용: {str(detail)[:300]}", f"실행ID: {self.run_id}", f"상세 로그: {self.path.name}", *extra]
        tmp = STATUS.with_name(STATUS.name + ".tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(tmp, STATUS)


def append_log(path: Path, msg: str) -> None:
    with Path(path).open("a", encoding="utf-8") as fh:
        fh.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


# ── 자식 프로세스 ──────────────────────────────────────────
def _child_cmd(stage: str, opts_p: Path, res_p: Path, run_id: str) -> tuple[list[str], str]:
    from . import app_process as AP
    if stage == STATS:                    # 바퀴 끝 집계와 같은 자식(같은 실행ID 로그 · 상태 파일 안 건드림 T-113)
        return AP.settle_stats_cmd(run_id, res_p)
    return AP._settle_program_cmd(["statements", "--stage", stage, "--opts", str(opts_p.resolve()),
                                   "--result", str(res_p.resolve())])


def run_child(stage: str, opts_p: Path, res_p: Path, run_id: str) -> int:
    """단계 하나를 자식 프로세스로(창 없음 · 끝나면 OS 가 메모리 회수) → 종료코드. 시간 초과 = TimeoutExpired(호출부가 '중단')."""
    cmd, cwd = _child_cmd(stage, opts_p, res_p, run_id)
    return subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          timeout=STAGE_TIMEOUT_SEC, creationflags=_NO_WINDOW).returncode


RUNNER = run_child                        # 시험 = 같은 프로세스에서 stage_main 을 부르는 가짜로 바꿈


def _result(abort: str | None = None, **kw) -> dict:
    return {"ok": list(kw.get("ok", [])), "skipped": list(kw.get("skipped", [])), "files": list(kw.get("files", [])),
            "abort": abort, **({"note": kw["note"]} if kw.get("note") else {})}


def _shape_problem(data) -> str:
    """약속 꼴(ok·skipped·files 목록 · skipped 줄 = id·reason · abort = 글자|None) 검사 → 사유('' = 맞음)."""
    if not isinstance(data, dict):
        return f"결과가 사전이 아님({type(data).__name__})"
    bad = [k for k in ("ok", "skipped", "files") if not isinstance(data.get(k), list)]
    if bad or "abort" not in data or not (data["abort"] is None or isinstance(data["abort"], str)):
        return f"결과 꼴이 약속과 다름(칸 {bad or ['abort']})"
    if any(not isinstance(s, dict) or not {"id", "reason"} <= set(s) for s in data["skipped"]):
        return "결과 skipped 줄에 id·reason 이 없음"
    return ""


def _in_child(stage: str, opts: dict, run_dir: Path, blog: BatchLog) -> dict:
    """opts 파일 → 자식 → 결과 파일 읽기·꼴 검사. 실패(종료코드·시간 초과·결과 없음·꼴 다름) = abort 사유가 든 결과."""
    opts_p, res_p = run_dir / f"_{stage}_입력.json", run_dir / f"_{stage}_결과.json"
    _write_json(opts_p, opts)
    res_p.unlink(missing_ok=True)
    try:
        rc = RUNNER(stage, opts_p, res_p, blog.run_id)
    except subprocess.TimeoutExpired:
        return _result(f"시간 초과({STAGE_TIMEOUT_SEC // 60}분) — 자식 프로세스 끝냄")
    data, why = _read_json(res_p)
    if data is None:
        return _result(f"자식 종료코드 {rc} · {why or '결과 파일 없음'} (상세 = {blog.path})")
    problem = "" if stage == STATS else _shape_problem(data)
    return _result(f"{problem} — {res_p}") if problem else data


def stage_main(stage: str, opts_path: Path, result_path: Path) -> int:
    """자식 쪽(`statements --stage …`) — 일 함수(또는 차이 비교)를 돌려 결과 JSON. 예외 = 로그에 전체 추적 + abort 결과 · 종료코드 1
    (창 없는 exe 에서 처리 안 된 예외 창이 떠 부모가 시간 초과까지 기다리지 않게)."""
    opts = json.loads(Path(opts_path).read_text(encoding="utf-8"))
    log_path = Path(opts["log"])

    def on_log(m: str) -> None:
        append_log(log_path, f"  [{stage}] {m}")
    try:
        res = _diff(opts) if stage == DIFF else _job(opts, on_log)
    except Exception as exc:              # MemoryError 포함 — 숨기지 않고 기록 · 부모가 '중단'으로 받음
        append_log(log_path, f"  [{stage}] ❌ 예외\n" + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
        _write_json(Path(result_path), _result(f"{exc.__class__.__name__}: {exc}"))
        return 1
    _write_json(Path(result_path), res)
    return 0


def _job(opts: dict, on_log) -> dict:
    module = opts["module"]
    try:
        mod = importlib.import_module(module)
    except ModuleNotFoundError as exc:
        if exc.name != module:            # 모듈 안의 다른 import 실패 = 진짜 오류(위로)
            raise
        return _result(f"모듈 없음 — {module}")
    out = opts.get("managed_output")                  # 파일별 읽은 결과 저장(D-419 ①) — 배치에서만 켬
    READS.use(Path(out) / "정산서" / READS.DIR if out else None)
    try:
        return mod.run_job(opts, on_log)
    finally:
        if READS.note():
            on_log(READS.note())
        READS.use(None)


# ── 차이 비교 ─────────────────────────────────────────────
def tools_dir() -> Path:
    """검산 도구 폴더 — 배포 = 묶음 폴더(sys._MEIPASS)/tools · 개발 = 저장소 tools."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "tools"


def _diff(opts: dict) -> dict:
    """지난 배치 위탁정산서 폴더와 비교 — 검산 도구를 이 프로세스에서 돌려 출력 전부를 파일로, 요약 줄은 note."""
    tool, out = tools_dir() / DIFF_TOOL, Path(opts["out_txt"])
    if not tool.is_file():
        return _result(f"검산 도구 없음 — {tool}")
    keep = sys.argv
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with out.open("w", encoding="utf-8") as fh, redirect_stdout(fh):
            sys.argv = [str(tool), opts["new"], opts["old"]]
            runpy.run_path(str(tool), run_name="__main__")
    finally:
        sys.argv = keep
    heads = ("독립 검산", "'추정' 문구", "합계 전→후", "계정 수")
    note = " · ".join(ln.strip() for ln in out.read_text(encoding="utf-8").splitlines() if ln.startswith(heads))
    return _result(files=[str(out)], note=note)


# ── 단계 ──────────────────────────────────────────────────
def check_inputs() -> dict[str, str]:
    """{단계: 중단 사유('' = 있음)} — 위탁 = 입력 폴더 고정 이름(settlement_statement_context.REQUIRED) · 셀독 = 폴더에 파일."""
    from . import settlement_statement_context as SC
    miss = SC.missing_inputs(INPUTS)
    has_seldoc = SELDOC_INPUTS.is_dir() and any(p.is_file() for p in SELDOC_INPUTS.iterdir())
    return {"consignor": f"입력 없음 — {INPUTS.resolve()}: {', '.join(miss)}" if miss else "",
            "seldoc": "" if has_seldoc else f"입력 없음 — {SELDOC_INPUTS.resolve()} 에 파일 없음"}


def stats_problem(path: Path) -> str:
    """정산집계가 정산서가 읽는 형식인가('' = 맞음) — '옵션별 등록상품' 시트·머리 줄(D-244 · 옛 집계 구분)."""
    import openpyxl
    from . import settlement_stats as SS
    wb = openpyxl.load_workbook(path, read_only=True)
    try:
        if SS.COST_OPTIONS not in wb.sheetnames:
            return f"'{SS.COST_OPTIONS}' 시트 없음(옛 집계)"
        head = next(wb[SS.COST_OPTIONS].iter_rows(max_row=1, values_only=True), ())
        return "" if tuple(head[:4]) == SS.COST_OPTIONS_HEAD else f"'{SS.COST_OPTIONS}' 머리 줄 다름 {head[:4]}"
    finally:
        wb.close()


def pick_stats(run_dir: Path, blog: BatchLog) -> tuple[Path | None, dict]:
    """최신 정산집계(이름 = 만든 시각순) · 없거나 옛 형식 = stats 자식 1번 → (경로|None, 단계 결과)."""
    files = sorted(STORE.BASE.glob(STATS_GLOB))
    why = stats_problem(files[-1]) if files else "정산집계 파일 없음"
    if not why:
        blog.line(f"[집계] 최신 정산집계 = {files[-1]}")
        return files[-1], {**_result(files=[str(files[-1])]), "state": OK}
    blog.line(f"[집계] {why} — 정산집계 새로 만들기(stats 자식 1번)")
    res = _in_child(STATS, {}, run_dir, blog)
    out = res.get("out")
    if not out:
        res = _result(f"정산집계 만들기 실패 — {res.get('abort') or res.get('오류') or '결과에 파일 없음'}")
        return None, {**res, "state": STOP}
    return Path(out), {**_result(files=[out], note=f"{why} → 새로 만듦"), "state": OK}


def _state(res: dict) -> str:
    return STOP if res.get("abort") else CHECK if res.get("skipped") else OK


def _run_job(name: str, label: str, module: str, opts: dict, block: str, run_dir: Path, blog: BatchLog) -> dict:
    if block:
        blog.line(f"[{label}] ❌ 중단 — {block}")
        return {**_result(block), "state": STOP}
    blog.line(f"[{label}] 시작(자식 프로세스 · 결과 폴더 {opts['out']})")
    res = _in_child(name, {**opts, "module": module}, run_dir, blog)
    res["state"] = _state(res)
    blog.line(f"[{label}] {res['state']} — 만든 {len(res['ok'])} · 건너뜀 {len(res['skipped'])} · 파일 {len(res['files'])}"
              + (f" · 중단 사유 {res['abort']}" if res["abort"] else ""))
    return res


def _job_opts(cycle: str, run_dir: Path, blog: BatchLog, stats: Path | None, skip: dict) -> dict:
    """일 함수 공통 입력(약속 · 레인 B·D) — 경로는 절대경로. 기준일·발행일 = 배치 실행일."""
    today = date.today().isoformat()
    return {"cycle": cycle, "run_id": blog.run_id, "log": str(blog.path.resolve()), "settle_dir": str(STORE.BASE.resolve()),
            "managed_output": str(STORE.BASE.parent.resolve()), "stats": str(stats.resolve()) if stats else None,
            "inputs": str(INPUTS.resolve()), "seldoc_inputs": str(SELDOC_INPUTS.resolve()), "basis": today, "issued": today,
            "skip_accounts": skip, "sheet": True}


def _diff_stage(prev: dict | None, cons: dict, run_dir: Path, blog: BatchLog) -> dict:
    new = Path(cons.get("out") or "")
    old = Path(((prev or {}).get("stages") or {}).get("consignor", {}).get("out") or "")
    if cons["state"] == STOP or not list(new.glob("정산서_*.xlsx")):
        return {**_result(note="새 위탁정산서 파일 없음 — 비교 안 함"), "state": SKIP}
    if not str(old) or str(old) == "." or not old.is_dir():
        return {**_result(note="비교할 지난 배치 결과 없음(첫 배치)"), "state": SKIP}
    res = _in_child(DIFF, {"log": str(blog.path.resolve()), "new": str(new), "old": str(old),
                           "out_txt": str((REPORTS / f"차이비교_{blog.run_id}.txt").resolve())}, run_dir, blog)
    res["state"] = STOP if res["abort"] else OK
    blog.line(f"[차이 비교] {res['state']} — {res['abort'] or res.get('note', '')}")
    return res


# ── 확인 필요 목록 ────────────────────────────────────────
def _labels() -> dict:
    return {STATS: "정산집계", **{n: lb for n, lb, _m in JOBS}, DIFF: "지난 배치와 차이 비교", "inputs": "입력 확인"}


def check_items(day: str, stages: dict, skip: dict, others: dict) -> list[list]:
    """확인 필요 한 목록(CHECK_HEAD 칸) — 정산 받기 실패 계정 → 단계 중단 → 단계가 건너뛴 줄(일 함수 skipped 의 id·reason +
    있으면 account·contract·product·amount 그대로 · 없는 칸 = 빈 칸). 입력 없어 못 돈 단계 = 종류 '입력'."""
    rows = [[day, "정산 받기", "", n, "", "", "", f"정산 받기 실패 — {r}"] for n, r in {**skip, **others}.items()]
    for key, res in stages.items():
        kind = res.get("kind") or _labels()[key]
        if res.get("abort"):
            rows.append([day, kind, "", "", "", "", "", f"중단 — {res['abort']}"])
        rows += [[day, kind, str(x["id"]), *(str(x.get(k, "")) for k in ("account", "contract", "product", "amount")),
                  str(x["reason"])] for x in res.get("skipped", [])]
    return rows


def _sheet_client(sheet: str, log):
    from .gsheet_api import GSheetClient
    return GSheetClient(sheet, on_log=log)


SHEET_CLIENT = _sheet_client              # 시험 = 가짜 클라이언트(실 시트 쓰기 금지)


def write_check_tab(sheet: str, rows: list[list], log) -> str:
    """위탁자정산서 구글시트에 '확인 필요' 탭 덮어쓰기(없으면 만듦 → 값 지움 → 머리 줄 + 목록 · 0건 = '없음' 한 줄) → 결과 문구.
    위탁자정산서 그리기(write_statement)가 탭을 전부 다시 만들므로 그 뒤에 쓴다. 실패 = GSheetError 그대로(호출부가 기록)."""
    client = SHEET_CLIENT(sheet, log)
    gid = client.ensure_sheet(CHECK_TAB)
    client.batch_update([{"updateCells": {"range": {"sheetId": gid}, "fields": "userEnteredValue"}}])
    client.write_values(CHECK_TAB, [CHECK_HEAD, *(rows or [["", "", "", "", "", "", "", "확인 필요 없음"]])], raw=True)
    return f"'{CHECK_TAB}' 탭 {len(rows)}건 씀(gid {gid})"


def _check_sheet(stages: dict, rows: list[list], blog: BatchLog) -> dict:
    """확인 필요 탭 쓰기 단계 — 시트 = 위탁 일 함수 결과의 `sheet`(그 달 위탁자정산서 파일). 없음·실패 = 사유(보고·상태에 남음)."""
    from .gsheet_api import GSheetError
    sheet = (stages.get("consignor") or {}).get("sheet") or ""
    if not sheet:
        return {**_result(note="위탁자정산서 구글시트 주소 없음(위탁 일 함수가 시트를 안 씀) — 확인 필요 탭 안 씀"), "state": SKIP}
    try:
        note = write_check_tab(sheet, rows, blog.line)
    except GSheetError as exc:
        blog.line(f"[확인 필요 탭] ❌ {exc}")
        return {**_result(note=f"확인 필요 탭 쓰기 실패 — {exc}"), "state": CHECK}
    blog.line(f"[확인 필요 탭] {note}")
    return {**_result(note=note), "state": OK}


# ── 보고 ──────────────────────────────────────────────────
def _verdict(stages: dict, items: list) -> str:
    states = {s["state"] for s in stages.values()}
    return STOP if STOP in states else CHECK if (CHECK in states or items) else OK


def _stage_lines(label: str, res: dict) -> list[str]:
    out = [f"### {label} — {res['state']}"]
    if res.get("abort"):
        out.append(f"- 중단 — {res['abort']}")
    if res.get("note"):
        out.append(f"- {res['note']}")
    if res.get("ok"):
        out.append(f"- 만든 {len(res['ok'])}: " + ", ".join(map(str, res["ok"])))
    out += [f"- 확인 필요 — {s['id']} — {s['reason']}" for s in res.get("skipped", [])]
    out += [f"- 파일: {f}" for f in res.get("files", [])]
    return out + [""]


def _md_cell(v) -> str:
    return str(v).replace("|", "/").replace("\n", " ")


def write_report(blog: BatchLog, cycle: str, done: dict, verdict: str, stages: dict, skip: dict, others: dict,
                 run_dir: Path, items: list[list]) -> Path:
    labels = {**_labels(), "check_tab": f"구글시트 '{CHECK_TAB}' 탭"}
    lines = [f"# 정산서 배치 보고 — {blog.run_id}", "",
             f"- 회차: {cycle} · 정산 받기 완료 {done.get('at', '')} · 판정: **{VERDICT[verdict][0]}**",
             f"- 결과 폴더: {run_dir.resolve()}", f"- 상세 로그: {blog.path.resolve()}", "",
             f"## 확인 필요 {len(items)}건", "", "| " + " | ".join(CHECK_HEAD) + " |", "|" + "---|" * len(CHECK_HEAD)]
    lines += ["| " + " | ".join(_md_cell(v) for v in r) + " |" for r in items] or ["| " + " | ".join(["-"] * 7 + ["없음"]) + " |"]
    lines += ["", "## 정산 받기 실패 계정(정산서 안 만듦)"]
    lines += [f"- 확인 필요 — {n} — {r}" for n, r in {**skip, **others}.items()] or ["- 없음"]
    lines += ["", "## 단계"]
    for key, res in stages.items():
        lines += _stage_lines(labels[key], res)
    path = REPORTS / f"배치보고_{blog.run_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ── 실행 ──────────────────────────────────────────────────
def _done_problem(done: dict | None, cycle: str) -> str:
    if not done or done.get("result") != W.RESULT["done"]:
        return "정산 받기 '완료' 기록 없음(24:00 까지 못 끝난 날 = 안 돎)"
    if done.get("key") != cycle:
        return f"완료 기록 회차({done.get('key')})가 이 실행 회차({cycle})와 다름 — 안 돎"
    return ""


def _stages(cycle: str, done: dict, prev: dict | None, fails_file: Path, run_dir: Path, blog: BatchLog):
    skip, others, fwhy = failed_accounts(done, fails_file, cycle)
    for n, r in {**skip, **others}.items():
        blog.line(f"[실패 계정] 확인 필요 — {n} — {r} (정산서 안 만듦)")
    need = check_inputs()
    stages: dict = {"inputs": {**_result(note=" · ".join(f"{lb}: {need[n] or '있음'}" for n, lb, _m in JOBS)),
                               "state": CHECK if any(need.values()) else OK}}
    stats, stages[STATS] = pick_stats(run_dir, blog)
    opts = _job_opts(cycle, run_dir, blog, stats, skip)
    for name, label, module in JOBS:
        block = fwhy or need[name] or ("" if stats or name != "consignor" else "정산집계 없음")
        job = {**opts, "out": str((run_dir / name).resolve()), "consignor": stages.get("consignor")}
        stages[name] = {**_run_job(name, label, module, job, block, run_dir, blog), "out": job["out"],
                        **({"kind": "입력"} if not fwhy and need[name] else {})}
    stages[DIFF] = _diff_stage(prev, stages["consignor"], run_dir, blog)
    return stages, skip, others


def _run_locked(cycle: str, done_file: Path, fails_file: Path, redo: bool, blog: BatchLog) -> int:
    done = W.read_done(done_file)
    why = _done_problem(done, cycle)
    prev, rwhy = read_record()
    if why or rwhy:
        blog.line(f"❌ 정산서 배치 안 돎 — {why or rwhy}")
        blog.status(ST_STOP, why or f"{rwhy} — 파일 확인 뒤 다시(지우면 다음 회차부터 새로 씀)")
        return 2
    if prev and prev.get("cycle") == cycle and not redo:
        blog.line(f"이번 회차({cycle}) 정산서 배치는 이미 돎({prev.get('result')} · {prev.get('report')}) — 안 돎(하루 1번)")
        return 0
    run_dir = ROOT_DIR / f"배치_{blog.run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    blog.status(ST_RUN, f"회차 {cycle} 정산서 만드는 중")
    blog.line(f"정산서 배치 시작 — 회차 {cycle} · 결과 폴더 {run_dir.resolve()}")
    stages, skip, others = _stages(cycle, done, prev, fails_file, run_dir, blog)
    items = check_items(date.today().isoformat(), stages, skip, others)
    stages["check_tab"] = _check_sheet(stages, items, blog)
    if stages["check_tab"]["state"] == CHECK:   # 탭을 못 쓴 것도 운용자가 볼 목록에(상태·보고)
        items.append([date.today().isoformat(), f"'{CHECK_TAB}' 탭", "", "", "", "", "", stages["check_tab"]["note"]])
    verdict = _verdict(stages, items)
    report = write_report(blog, cycle, done, verdict, stages, skip, others, run_dir, items)
    _write_json(RECORD, {"cycle": cycle, "run_id": blog.run_id, "at": datetime.now().isoformat(timespec="seconds"),
                         "result": VERDICT[verdict][0], "out": str(run_dir.resolve()), "report": str(report.resolve()),
                         "실패계정": {**skip, **others}, "확인필요": items, "stages": stages})
    blog.line(f"정산서 배치 끝 — {VERDICT[verdict][0]} · 확인 필요 {len(items)}건 · 보고 {report.resolve()}")
    top = tuple(f"확인 필요: {r[1]} · {r[2] or r[3] or r[4] or '-'} · {r[7]}"[:200] for r in items[:CHECK_TOP])
    more = (f"확인 필요: … 외 {len(items) - CHECK_TOP}건(보고 파일)",) if len(items) > CHECK_TOP else ()
    blog.status(VERDICT[verdict][1], f"회차 {cycle} · {VERDICT[verdict][0]} · 확인 필요 {len(items)}건 · 보고 {report.name}",
                extra=top + more)
    return 0 if verdict != STOP else 1


def run_batch(cycle: str, done_file: Path, fails_file: Path, *, redo: bool = False, echo=print) -> int:
    """정산서 배치 한 번(같은 PC 에 둘 뜨지 않게 잠금 · 둘째 = 상태 안 건드리고 바로 끝)."""
    blog = BatchLog(datetime.now().strftime("%y%m%d_%H%M%S"), echo=echo)
    try:
        with registry_lock(LOCK, wait_sec=0, on_log=blog.line):
            return _run_locked(cycle, Path(done_file), Path(fails_file), redo, blog)
    except RegistryLockError:
        blog.line(f"정산서 배치가 이미 도는 중({LOCK}) — 이 실행은 종료")
        return 0


def main_cli(args, done_file: Path, fails_file: Path) -> int:
    """`statements` 명령 — `--stage` = 자식 단계 · 그 밖 = `--cycle` 배치(`--redo` = 하루 1번 기록 무시 · 사람이 다시 돌릴 때)."""
    if args.stage:
        return stage_main(args.stage, Path(args.opts), Path(args.result))
    if not args.cycle:
        print("statements 는 --cycle <회차 키(_완료.json key)> 가 필요합니다")
        return 2
    return run_batch(args.cycle, done_file, fails_file, redo=args.redo)
