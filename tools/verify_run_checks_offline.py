"""회귀 게이트 자체 검증 — 동시 실행·통과 기록 건너뛰기(D-180). 임시 git 저장소에서만 돈다.

기대값 출처 = 소유자 승인(2026-11-08 "1·2·4 적용"):
  ① 같은 내용을 두 번 검사하지 않음 — 내용이 한 글자라도 다르면 반드시 다시 검사(우회 아님)
  ② 검사를 동시에 실행 — 결과·실패 판정은 예전과 같음(하나라도 실패면 exit 1·전체 결과 표시)
소유자 승인(2026-11-20 "A~C 모두 반영 (권장)" · D-377):
  A PC 전체에서 게이트 1개만 — 다른 게이트가 돌면 누가·언제부터인지 보이며 기다림 · 남은 잠금 파일·죽은 게이트는 막지 않음
  B 잠금을 얻은 뒤 건너뛰기 판정 — 앞 게이트가 통과 기록을 남기면 뒤 게이트(pre-push)는 건너뜀
  C 검사 프로세스는 낮은 우선순위(Windows BELOW_NORMAL)
시험의 게이트는 전부 임시 잠금 경로를 쓴다(실제 PC 잠금을 안 잡음 — 이 시험도 게이트 안에서 돈다).

    python tools/verify_run_checks_offline.py
"""
from __future__ import annotations

import csv
import io
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

import check_stamp as CS  # noqa: E402
import run_checks as RC  # noqa: E402


def ok(msg):
    print(f"  ✔ {msg}")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=str(root),
                          env=CS.clean_env(), capture_output=True, text=True, check=True).stdout.strip()


def _repo(tmp: str) -> Path:
    root = Path(tmp) / "repo"
    (root / "docs" / "memory").mkdir(parents=True)
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    (root / "docs" / "memory" / "m.md").write_text("m1\n", encoding="utf-8")
    (root / ".gitignore").write_text("/data/\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init")
    return root


def s1_key():
    print("[S1] 내용 키 — 같은 내용=같은 키 · 추적/새 파일 변경=다른 키 · 무시 파일·메모리 사본·.claude=그대로")
    with tempfile.TemporaryDirectory() as tmp:
        root = _repo(tmp)
        k0 = CS.worktree_key(root)
        assert k0 and k0 == CS.worktree_key(root), "같은 내용인데 키가 다름"
        (root / "data").mkdir()
        (root / "data" / "x.db").write_text("1", encoding="utf-8")
        (root / "docs" / "memory" / "m.md").write_text("m2\n", encoding="utf-8")
        (root / ".claude").mkdir()
        (root / ".claude" / "s.json").write_text("{}", encoding="utf-8")
        assert CS.worktree_key(root) == k0, "검사 입력 아닌 변경에 키가 바뀜"
        (root / "a.py").write_text("x = 2\n", encoding="utf-8")
        k1 = CS.worktree_key(root)
        assert k1 != k0, "추적 파일 수정을 못 잡음"
        (root / "b.py").write_text("y = 1\n", encoding="utf-8")
        assert CS.worktree_key(root) not in (k0, k1), "새 파일을 못 잡음"
        (root / "a.py").write_text("x = 1\n", encoding="utf-8")
        (root / "b.py").unlink()
        assert CS.worktree_key(root) == k0, "되돌렸는데 키가 다름"
    ok("키 판정 6가지")


def s2_commit_same_key():
    print("[S2] 커밋해도 내용이 같으면 같은 키 · 실제 스테이징은 안 건드림")
    with tempfile.TemporaryDirectory() as tmp:
        root = _repo(tmp)
        (root / "a.py").write_text("x = 3\n", encoding="utf-8")
        (root / "c.py").write_text("z = 1\n", encoding="utf-8")
        _git(root, "add", "a.py")
        before = _git(root, "status", "--porcelain")
        k = CS.worktree_key(root)
        assert _git(root, "status", "--porcelain") == before, "키 계산이 스테이징을 바꿈"
        assert CS.commit_key(root, "HEAD") != k, "커밋 전 HEAD 와 같으면 안 됨"
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", "c")
        assert CS.commit_key(root, "HEAD") == k, "커밋 뒤 같은 내용인데 키가 다름"
        assert CS.commit_key(root, "없는커밋") is None
    ok("커밋 전후 키 같음·스테이징 불변·없는 커밋=None")


def s3_record():
    print("[S3] 통과 기록 — 빠른 기록은 전체를 대신 못함 · 전체 기록은 빠른 것도 대신함 · 다른 키=미통과")
    with tempfile.TemporaryDirectory() as tmp:
        root = _repo(tmp)
        assert not CS.passed(root, "k1", True) and not CS.passed(root, None, True)
        CS.record(root, "k1", quick=True)
        assert CS.passed(root, "k1", True) and not CS.passed(root, "k1", False)
        CS.record(root, "k2", quick=False)
        assert CS.passed(root, "k2", True) and CS.passed(root, "k2", False)
        assert not CS.passed(root, "k3", True)
        assert "checks-pass.json" not in _git(root, "status", "--porcelain"), "기록 파일이 git 에 보임"
    ok("기록·대체 규칙·git 밖 저장")


def s4_push_refs():
    print("[S4] pre-push 입력 — 올라갈 커밋만 · 삭제 푸시 제외 · 빈 입력=건너뛰지 않음")
    z = "0" * 40
    lines = [f"refs/heads/a {'1' * 40} refs/heads/a {z}", f"(delete) {z} refs/heads/b {'2' * 40}", "", "잘못된 줄"]
    assert CS.pushed_revs(lines) == ["1" * 40]
    assert CS.pushed_revs([]) == []
    ok("ref 줄 해석")


def _scripts(tmp: str, spec: list[tuple[str, float, int]]) -> list:
    out = []
    for name, sec, rc in spec:
        p = Path(tmp) / f"{name}.py"
        p.write_text(f"import time, sys\nsys.stdout.reconfigure(encoding='utf-8')\ntime.sleep({sec})\nprint('{name} 출력')\nsys.exit({rc})\n", encoding="utf-8")
        out.append((name, str(p), True))
    return out


def _barrier_scripts(tmp: str, names: list[str], wait: float) -> list:
    """서로를 기다리는 검사 — 각자 시작 표시를 남기고 나머지 표시가 다 생겨야 통과(wait 초 안 생기면 exit 1).
    동시에 돌면 부하와 상관없이 통과 · 하나씩 돌면 앞의 것이 실패 → 걸린 시간 대신 '실제로 겹쳐 돎'을 판정(D-203)."""
    d = Path(tempfile.mkdtemp(dir=tmp))
    out = []
    for name in names:
        p = d / f"{name}.py"
        p.write_text(
            "import pathlib, sys, time\nsys.stdout.reconfigure(encoding='utf-8')\n"
            f"d = pathlib.Path(r'{d}')\n(d / '{name}.start').write_text('1')\n"
            f"end = time.monotonic() + {wait}\n"
            f"while not all((d / (n + '.start')).exists() for n in {names!r}):\n"
            f"    if time.monotonic() > end:\n        print('{name} 혼자 돎')\n        sys.exit(1)\n"
            "    time.sleep(0.02)\n"
            f"print('{name} 출력')\n", encoding="utf-8")
        out.append((name, str(p), True))
    return out


def _main(argv: list[str], stdin: str = "") -> tuple[int, str]:
    old_out, old_in = sys.stdout, sys.stdin
    sys.stdout, sys.stdin = io.StringIO(), io.StringIO(stdin)
    try:
        rc = RC.main(argv)
        return rc, sys.stdout.getvalue()
    finally:
        sys.stdout, sys.stdin = old_out, old_in


def s5_parallel():
    print("[S5] 동시 실행 — 서로 기다리는 3개가 동시 3개로 다 통과(실제로 겹쳐 돎) · 하나씩이면 실패 · 결과는 목록 순서 · 실패 하나면 exit 1·기록 안 함")
    with tempfile.TemporaryDirectory() as tmp:
        names = ["느림", "보통", "빠름"]
        res = RC.run_all(_barrier_scripts(tmp, names, 10.0), 3)
        assert all(r[1] for r in res), "동시에 안 돎: " + " / ".join(r[3].strip() for r in res)
        assert [r[0] for r in res] == names
        assert "느림 출력" in res[0][3]
        seq = RC.run_all(_barrier_scripts(tmp, names[:2], 1.5), 1)
        assert not seq[0][1] and "혼자 돎" in seq[0][3], "하나씩 돌았는데 동시 판정을 통과함"
        root = _repo(tmp)
        saved = RC.ROOT, RC.CHECKS
        RC.ROOT, RC.CHECKS = root, _scripts(tmp, [("통과", 0, 0), ("실패", 0, 3)])
        try:
            rc, out = _main([])
            assert rc == 1 and "실패 1종: 실패" in out and "실패 출력" in out, out
            assert not CS.passed(root, CS.worktree_key(root), True), "실패했는데 기록됨"
            rc, out = _main(["-j", "1"])
            assert rc == 1, "하나씩 실행도 같은 판정이어야 함"
        finally:
            RC.ROOT, RC.CHECKS = saved
    ok("동시 실행·순서·실패 판정·-j 1")


def s6_skip():
    print("[S6] 건너뛰기 — 같은 내용 통과 기록 있으면 안 돌림 · 내용 바뀌면 다시 돌림 · 푸시는 올라갈 커밋 내용으로")
    with tempfile.TemporaryDirectory() as tmp:
        root = _repo(tmp)
        flag = Path(tmp) / "fail_now"
        p = Path(tmp) / "gate.py"
        p.write_text(f"import sys, pathlib\nsys.exit(1 if pathlib.Path(r'{flag}').exists() else 0)\n", encoding="utf-8")
        saved = RC.ROOT, RC.CHECKS
        RC.ROOT, RC.CHECKS = root, [("게이트", str(p), True), ("전체만", str(p), False)]
        try:
            assert _main(["--quick", "--skip-if-passed"])[0] == 0          # 첫 실행 = 실제 검사·빠른 기록
            flag.touch()                                                   # 이제 돌리면 실패
            rc, out = _main(["--quick", "--skip-if-passed"])
            assert rc == 0 and "건너뜀" in out, out
            assert _main(["--quick"])[0] == 1, "옵션 없으면 늘 실제 검사"
            head = _git(root, "rev-parse", "HEAD")
            ref = f"refs/heads/master {head} refs/heads/master {'0' * 40}\n"
            rc, out = _main(["--skip-if-passed=push"], ref)
            assert rc == 1 and "건너뜀" not in out, "빠른 기록만으로 푸시를 건너뜀"
            flag.unlink()
            assert _main([])[0] == 0                                       # 전체 통과 기록
            flag.touch()
            assert _main(["--skip-if-passed=push"], ref)[0] == 0, "같은 내용 커밋인데 다시 돌림"
            assert _main(["--skip-if-passed=push"], "")[0] == 1, "올라갈 커밋 정보 없으면 검사해야 함"
            (root / "a.py").write_text("x = 9\n", encoding="utf-8")
            assert _main(["--quick", "--skip-if-passed"])[0] == 1, "내용 바뀌었는데 건너뜀"
            _git(root, "commit", "-qam", "바뀜")
            ref2 = f"refs/heads/master {_git(root, 'rev-parse', 'HEAD')} refs/heads/master {head}\n"
            assert _main(["--skip-if-passed=push"], ref2)[0] == 1, "다른 내용 커밋인데 푸시를 건너뜀"
        finally:
            RC.ROOT, RC.CHECKS = saved
    ok("건너뛰기 9가지")


def s7_hook_env():
    print("[S7] 훅 안 실행 — git 이 넘긴 GIT_DIR·GIT_INDEX_FILE 이 있어도 다른 저장소(훅의 저장소)를 안 건드림")
    import os
    with tempfile.TemporaryDirectory() as tmp:
        decoy = _repo(tmp + "/d")
        cfg, idx = decoy / ".git" / "config", decoy / ".git" / "index"
        before = (cfg.read_bytes(), idx.read_bytes())
        saved = {k: os.environ.get(k) for k in ("GIT_DIR", "GIT_INDEX_FILE")}
        os.environ["GIT_DIR"], os.environ["GIT_INDEX_FILE"] = str(decoy / ".git"), str(idx)
        try:
            s1_key()
            s2_commit_same_key()
            s6_skip()
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        assert (cfg.read_bytes(), idx.read_bytes()) == before, "훅 저장소의 설정·인덱스를 고침"
    ok("훅 환경에서도 훅 저장소 설정·인덱스 그대로")


# 다른 프로세스 게이트 시험의 최대 기다림 — 조건이 맞으면 바로 끝나므로 길어도 정상일 때 느려지지 않음.
# 검사 자식이 낮은 우선순위(D-377)라 PC 가 바쁘면(다른 세션 게이트·메모리 부족) 시작이 수십 초 늦음(실측 20초 넘김).
WAIT_SEC = 180


def _gate_child(repo: Path, check: Path, lock: Path) -> str:
    """다른 프로세스로 띄우는 가짜 게이트 — 임시 저장소·가짜 검사 1개·임시 잠금 경로."""
    return ("import sys, pathlib\n"
            f"sys.path.insert(0, r'{HERE}')\n"
            "import run_checks as RC\n"
            f"RC.ROOT = pathlib.Path(r'{repo}')\n"
            f"RC.CHECKS = [('가짜', r'{check}', True)]\n"
            f"RC.LOCK_PATH = pathlib.Path(r'{lock}')\n"
            "raise SystemExit(RC.main(sys.argv[1:]))\n")


def _hold_check(tmp: Path, release: Path) -> Path:
    """시작 표시(ran_<WHO>)를 남기고 release 파일이 생길 때까지(최대 WAIT_SEC) 붙잡는 가짜 검사."""
    p = tmp / "hold.py"
    p.write_text("import os, pathlib, time\n"
                 f"pathlib.Path(r'{tmp}', 'ran_' + os.environ['WHO']).write_text('1')\n"
                 f"end = time.monotonic() + {WAIT_SEC}\n"
                 f"while not pathlib.Path(r'{release}').exists() and time.monotonic() < end:\n    time.sleep(0.05)\n",
                 encoding="utf-8")
    return p


def _spawn(code: str, who: str, out: Path, argv: tuple[str, ...] = (), stdin: str | None = None) -> subprocess.Popen:
    env = {**CS.clean_env(), "WHO": who, "PYTHONUNBUFFERED": "1"}
    with out.open("wb") as f:                            # 자식이 핸들을 물려받음 — 부모 쪽은 바로 닫음(임시 폴더 정리)
        proc = subprocess.Popen([sys.executable, "-c", code, *argv], env=env, stdout=f,
                                stderr=subprocess.STDOUT, stdin=subprocess.PIPE if stdin is not None else None)
    if stdin is not None and proc.stdin is not None:
        proc.stdin.write(stdin.encode("utf-8"))
        proc.stdin.close()
    return proc


def _until(cond, sec: float) -> bool:
    end = time.monotonic() + sec
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return cond()


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def _finish(*procs: subprocess.Popen) -> None:
    for p in procs:
        try:
            p.wait(timeout=WAIT_SEC)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            raise AssertionError(f"게이트가 {WAIT_SEC}초 안에 안 끝남(잠금을 못 얻고 멈춤?)")


def s8_lock_wait_then_skip():
    print("[S8] PC 전체 게이트 1개(A) — 앞 게이트가 도는 동안 뒤 게이트(pre-push)는 누가·언제부터 쥐었는지 보이며 기다림 "
          "· 잠금 뒤 건너뛰기 판정(B) — 앞 게이트 통과 기록으로 뒤 게이트는 검사 없이 건너뜀")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:   # 실패 때 남은 자식이 진짜 실패를 가리지 않게
        t = Path(tmp)
        root = _repo(tmp)
        release, lock = t / "release", t / "gate.lock"
        code = _gate_child(root, _hold_check(t, release), lock)
        head = _git(root, "rev-parse", "HEAD")
        a = _spawn(code, "A", t / "a.out")
        b = None
        try:
            assert _until(lambda: (t / "ran_A").exists(), WAIT_SEC), "앞 게이트 검사가 시작 안 됨: " + _text(t / "a.out")
            b = _spawn(code, "B", t / "b.out", ("--skip-if-passed=push",),
                       f"refs/heads/master {head} refs/heads/master {'0' * 40}\n")
            assert _until(lambda: "기다립니다" in _text(t / "b.out"), WAIT_SEC), "뒤 게이트가 기다린다고 안 함: " + _text(t / "b.out")
            msg = _text(t / "b.out")
            assert f"PID {a.pid}" in msg and str(root) in msg and "시작" in msg, "누가·언제부터·어느 폴더인지 안 보임: " + msg
            assert not (t / "ran_B").exists(), "앞 게이트가 도는데 뒤 게이트 검사가 시작됨(동시에 2개)"
        finally:
            release.touch()
            _finish(*[p for p in (a, b) if p])
        assert a.returncode == 0, _text(t / "a.out")
        assert b.returncode == 0 and "건너뜀" in _text(t / "b.out"), "앞 게이트가 통과 기록을 남겼는데 다시 돎: " + _text(t / "b.out")
        assert not (t / "ran_B").exists(), "건너뛰어야 할 뒤 게이트가 검사를 돌림"
        with (t / "run_checks_times.csv").open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        assert [r["결과"] for r in rows] == ["통과", "건너뜀"], rows
        assert float(rows[1]["잠금대기초"]) > 0, "뒤 게이트가 기다린 초가 기록 안 됨(D-378 N): " + str(rows)
    ok("기다림 표시(PID·시작·작업 폴더)·동시 2개 없음·잠금 뒤 건너뜀·기다린 초 기록")


def s9_stale_lock():
    print("[S9] 남은 잠금 파일·죽은 게이트는 막지 않음 — 파일이 아니라 OS 잠금으로 판정(프로세스가 죽으면 OS 가 풂)")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:   # 실패 때 남은 자식이 진짜 실패를 가리지 않게
        t = Path(tmp)
        root = _repo(tmp)
        release, lock = t / "release", t / "gate.lock"
        lock.write_text("PID 99999 · 시작 2026-11-20 19:46:00 · 작업 폴더 X", encoding="utf-8")   # 죽은 게이트가 남긴 파일
        code = _gate_child(root, _hold_check(t, release), lock)
        release.touch()                                                  # 여기 검사는 붙잡지 않음(바로 끝남)
        b = _spawn(code, "B", t / "b.out")
        _finish(b)
        assert b.returncode == 0 and "기다립니다" not in _text(t / "b.out"), "남은 잠금 파일에 막힘: " + _text(t / "b.out")
        held = t / "held"
        dying = ("import sys, pathlib, time\n"                            # 잠금을 쥔 채 도중에 죽을 게이트(검사 자식 없음)
                 f"sys.path.insert(0, r'{HERE}')\n"
                 "import run_checks as RC\n"
                 f"RC.LOCK_PATH = pathlib.Path(r'{lock}')\n"
                 f"with RC._gate_lock(pathlib.Path(r'{root}')):\n"
                 f"    pathlib.Path(r'{held}').write_text('1')\n"
                 "    time.sleep(60)\n")
        a = _spawn(dying, "A", t / "a.out")
        try:
            assert _until(held.exists, WAIT_SEC), "잠금을 쥐지 못함: " + _text(t / "a.out")
        finally:
            a.kill()                                                       # 게이트가 도중에 죽음
            a.wait(timeout=10)
        c = _spawn(code, "C", t / "c.out")
        _finish(c)
        assert c.returncode == 0 and (t / "ran_C").exists(), "죽은 게이트의 잠금에 막힘: " + _text(t / "c.out")
    ok("남은 파일·죽은 게이트 모두 바로 잠금 얻음")


def s10_priority():
    print("[S10] 검사 프로세스 = 낮은 우선순위(Windows BELOW_NORMAL · 다른 OS 는 해당 없음)")
    if sys.platform != "win32":
        ok("Windows 아님 — 해당 없음")
        return
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "prio.py"
        p.write_text("import ctypes, sys\nk = ctypes.windll.kernel32\nk.GetCurrentProcess.restype = ctypes.c_void_p\n"
                     "k.GetPriorityClass.argtypes = [ctypes.c_void_p]\nc = k.GetPriorityClass(k.GetCurrentProcess())\n"
                     "print(hex(c))\nsys.exit(0 if c == 0x4000 else 1)\n", encoding="utf-8")
        res = RC.run_all([("우선순위", str(p), True)], 1)
        assert res[0][1], "검사 프로세스 우선순위가 BELOW_NORMAL(0x4000) 아님: " + res[0][3].strip()
    ok("검사 프로세스 우선순위 0x4000(BELOW_NORMAL)")


def _times_rows() -> list[dict]:
    p = RC.times_path()
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def s11_times_log():
    print("[S11] 시간 기록(D-378 N) — 게이트마다 한 줄: 종류·결과(통과/실패/건너뜀)·잠금 기다린 초·걸린 초·검사별 초 · 기록 못 쓰면 경고만(게이트 결과 그대로)")
    with tempfile.TemporaryDirectory() as tmp:
        root = _repo(tmp)
        flag = Path(tmp) / "fail_now"
        p = Path(tmp) / "gate.py"
        p.write_text(f"import sys, pathlib\nsys.exit(1 if pathlib.Path(r'{flag}').exists() else 0)\n", encoding="utf-8")
        saved = RC.ROOT, RC.CHECKS
        RC.ROOT, RC.CHECKS = root, [("검사가", str(p), True), ("검사나", str(p), True)]
        before = len(_times_rows())
        try:
            assert _main(["--quick", "--skip-if-passed"])[0] == 0
            assert _main(["--quick", "--skip-if-passed"])[0] == 0          # 같은 내용 → 건너뜀
            flag.touch()
            assert _main([])[0] == 1                                       # 전체 · 실패
            rows = _times_rows()[before:]
            assert [r["결과"] for r in rows] == ["통과", "건너뜀", "실패"], rows
            assert [r["종류"] for r in rows] == ["빠른", "빠른", "전체"], rows
            first = rows[0]
            assert first["작업폴더"] == str(root) and first["검사수"] == "2", first
            assert "검사가=" in first["검사별초"] and "검사나=" in first["검사별초"], first
            for r in rows:
                float(r["잠금대기초"]), float(r["걸린초"])
                assert r["시작"][:4].isdigit(), r
            assert rows[1]["검사별초"] == "" and rows[1]["검사수"] == "0", "건너뛰었는데 검사 기록이 있음"
            saved_lock = RC.LOCK_PATH
            bad = Path(tmp) / "막힘"
            bad.mkdir()
            (bad / "run_checks_times.csv").mkdir()                         # 기록 파일 자리에 폴더 → 쓰기 실패
            RC.LOCK_PATH = bad / "gate.lock"
            try:
                flag.unlink()
                rc, out = _main([])
                assert rc == 0 and "시간 기록 못 함" in out, out
            finally:
                RC.LOCK_PATH = saved_lock
        finally:
            RC.ROOT, RC.CHECKS = saved
    ok("통과·건너뜀·실패 3줄 · 종류·작업폴더·검사별 초 · 기록 실패 = 경고만")


def s12_untracked_warn():
    print("[S12] git 에 안 올린 파일(D-379) — 있으면 통과 때 경고(파일 이름) + 푸시 때 다시 검사 · .gitignore 로 빼면 경고 없음·커밋 뒤 푸시 건너뜀")
    with tempfile.TemporaryDirectory() as tmp:
        root = _repo(tmp)
        p = Path(tmp) / "gate.py"
        p.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
        saved = RC.ROOT, RC.CHECKS
        RC.ROOT, RC.CHECKS = root, [("게이트", str(p), True)]
        try:
            (root / "plans").mkdir()
            (root / "plans" / "계획.md").write_text("메모\n", encoding="utf-8")
            (root / "docs" / "memory" / "새메모.md").write_text("m2\n", encoding="utf-8")   # 키에서 빠지는 경로 = 경고 대상 아님
            rc, out = _main([])
            assert rc == 0 and "git 에 안 올린 파일 1개" in out and "plans/계획.md" in out, out
            assert "새메모.md" not in out, "키에서 빠지는 메모리 사본까지 경고함: " + out
            head = _git(root, "rev-parse", "HEAD")
            ref = f"refs/heads/master {head} refs/heads/master {'0' * 40}\n"
            rc, out = _main(["--skip-if-passed=push"], ref)
            assert rc == 0 and "건너뜀" not in out, "안 올린 파일이 있는데 커밋 내용 통과로 봄(지금 판정 그대로여야 함)"
            (root / ".gitignore").write_text("/data/\n/plans/\n", encoding="utf-8")
            _git(root, "commit", "-qam", "plans 무시")
            rc, out = _main([])
            assert rc == 0 and "git 에 안 올린 파일" not in out, out
            ref2 = f"refs/heads/master {_git(root, 'rev-parse', 'HEAD')} refs/heads/master {head}\n"
            rc, out = _main(["--skip-if-passed=push"], ref2)
            assert rc == 0 and "건너뜀" in out, "무시 목록에 넣었는데 푸시 때 다시 검사함: " + out
        finally:
            RC.ROOT, RC.CHECKS = saved
    ok("경고(이름·개수·메모리 사본 제외)·푸시 다시 검사 · 무시 목록 뒤 경고 없음·푸시 건너뜀")


def main():
    with tempfile.TemporaryDirectory() as lock_dir:      # 같은 프로세스 안 게이트(S5·S6·S7)도 실제 PC 잠금 대신 임시 잠금
        RC.LOCK_PATH = Path(lock_dir) / "gate.lock"
        _scenarios()


def _scenarios():
    s1_key()
    s2_commit_same_key()
    s3_record()
    s4_push_refs()
    s5_parallel()
    s6_skip()
    s7_hook_env()
    s8_lock_wait_then_skip()
    s9_stale_lock()
    s10_priority()
    s11_times_log()
    s12_untracked_warn()
    print("회귀 게이트 자체(동시 실행·통과 기록·PC 하나만·우선순위) 오프라인 검증 통과")


if __name__ == "__main__":
    main()
