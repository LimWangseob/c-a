"""회귀 게이트 자체 검증 — 동시 실행·통과 기록 건너뛰기(D-180). 임시 git 저장소에서만 돈다.

기대값 출처 = 소유자 승인(2026-11-08 "1·2·4 적용"):
  ① 같은 내용을 두 번 검사하지 않음 — 내용이 한 글자라도 다르면 반드시 다시 검사(우회 아님)
  ② 검사를 동시에 실행 — 결과·실패 판정은 예전과 같음(하나라도 실패면 exit 1·전체 결과 표시)

    python tools/verify_run_checks_offline.py
"""
from __future__ import annotations

import io
import subprocess
import sys
import tempfile
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


def main():
    s1_key()
    s2_commit_same_key()
    s3_record()
    s4_push_refs()
    s5_parallel()
    s6_skip()
    s7_hook_env()
    print("회귀 게이트 자체(동시 실행·통과 기록) 오프라인 검증 통과")


if __name__ == "__main__":
    main()
