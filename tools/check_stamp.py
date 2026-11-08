"""회귀 게이트 통과 기록 — 같은 내용을 두 번 검사하지 않게 한다(D-180).

내용 키 = 작업 폴더(또는 커밋)의 git 트리 해시. 임시 인덱스에서 만들어 실제 스테이징은 건드리지 않는다.
키에서 빼는 경로(EXCLUDE)는 검사 입력이 아닌 것만 둔다:
  - docs/memory : 훅이 커밋·푸시 때 자동으로 미러링하는 메모리 사본
  - .claude     : 로컬 Claude 설정·작업 폴더(git 추적 대상 아님)
기록 파일 = `git rev-parse --git-path checks-pass.json`(작업 폴더마다 따로·git 추적 안 함).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

EXCLUDE = ("docs/memory", ".claude")
_ZERO = "0" * 40
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# git 이 훅에 넘기는 저장소 지정 변수(`git rev-parse --local-env-vars`). 그대로 물려받으면 root 가 아닌
# 훅의 저장소·인덱스를 고친다(2026-11-08 pre-commit 안에서 실 인덱스 덮어씀·core.bare=true 사고).
_REPO_ENV = ("GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CONFIG", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
             "GIT_OBJECT_DIRECTORY", "GIT_DIR", "GIT_WORK_TREE", "GIT_IMPLICIT_WORK_TREE", "GIT_GRAFT_FILE",
             "GIT_INDEX_FILE", "GIT_NO_REPLACE_OBJECTS", "GIT_REPLACE_REF_BASE", "GIT_PREFIX", "GIT_SHALLOW_FILE",
             "GIT_COMMON_DIR")


def clean_env() -> dict:
    """root 폴더에서 저장소를 스스로 찾게 저장소 지정 변수를 뺀 환경."""
    return {k: v for k, v in os.environ.items() if k not in _REPO_ENV}


def _git(root: Path, args: list[str], env: dict | None = None) -> str:
    out = subprocess.run(["git", *args], cwd=str(root), env=env or clean_env(), capture_output=True, text=True,
                         encoding="utf-8", errors="replace", check=True, creationflags=_NO_WINDOW)
    return out.stdout.strip()


def _git_path(root: Path, name: str) -> Path:
    p = Path(_git(root, ["rev-parse", "--git-path", name]))
    return p if p.is_absolute() else root / p


def _key(root: Path, fill: list[str]) -> str:
    """임시 인덱스에 fill 명령으로 내용을 담고 EXCLUDE 를 뺀 트리 해시."""
    with tempfile.TemporaryDirectory() as d:
        idx = Path(d) / "index"
        real = _git_path(root, "index")
        if real.exists():
            shutil.copyfile(real, idx)          # 파일 상태 캐시 재사용(빠름)
        env = {**clean_env(), "GIT_INDEX_FILE": str(idx)}
        _git(root, fill, env)
        _git(root, ["rm", "-r", "--cached", "-q", "--ignore-unmatch", "--", *EXCLUDE], env)
        return _git(root, ["write-tree"], env)


def worktree_key(root: Path) -> str | None:
    """지금 작업 폴더 내용(무시 파일 제외·새 파일 포함)의 키. git 이 아니면 None."""
    try:
        return _key(root, ["add", "-A", "--", ".", *[f":(exclude){p}" for p in EXCLUDE]])
    except (subprocess.CalledProcessError, OSError):
        return None


def commit_key(root: Path, rev: str) -> str | None:
    """커밋 rev 내용의 키(worktree_key 와 같은 방식이라 비교 가능)."""
    try:
        return _key(root, ["read-tree", rev])
    except (subprocess.CalledProcessError, OSError):
        return None


def pushed_revs(lines: list[str]) -> list[str]:
    """pre-push 표준입력 '<로컬ref> <로컬sha> <원격ref> <원격sha>' 에서 올라갈 커밋들(삭제 푸시 제외)."""
    revs = []
    for line in lines:
        parts = line.split()
        if len(parts) == 4 and parts[1] != _ZERO:
            revs.append(parts[1])
    return revs


def _load(root: Path) -> dict:
    try:
        return json.loads(_git_path(root, "checks-pass.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, subprocess.CalledProcessError):
        return {}


def passed(root: Path, key: str | None, quick: bool) -> bool:
    """key 가 이미 통과했나. 전체 통과는 빠른 검사도 대신한다."""
    if not key:
        return False
    d = _load(root)
    return key == d.get("full") or (quick and key == d.get("quick"))


def record(root: Path, key: str | None, quick: bool) -> None:
    if not key:
        return
    d = _load(root)
    d["quick"] = key
    if not quick:
        d["full"] = key
    try:
        _git_path(root, "checks-pass.json").write_text(json.dumps(d), encoding="utf-8")
    except (OSError, subprocess.CalledProcessError):
        pass
