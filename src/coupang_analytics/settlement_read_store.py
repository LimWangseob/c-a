"""정산서 '파일별 읽은 결과' 저장(D-419 ① · T-188) — 원본 파일 내용과 읽기 코드가 그대로면 지난번 읽은 결과를 다시 씀.

- 켜는 곳 = 정산서 배치 일 함수(`use(폴더)`) 뿐. 안 켜면(기본 · 시험·손 도구) 늘 원본을 읽음 = 옛 동작.
- 열쇠 = 종류 + 파일 이름(이름에서 계정·기간을 얻는 읽기가 있음) + 파일 내용 sha256. 저장분 머리 = 읽기 코드 판·내용 검사값.
  하나라도 다르면 원본을 다시 읽어 덮어씀. 저장분이 깨짐 = 다시 읽음(건수를 안내 줄에 표시).
- 읽기 코드 판 = 배포 exe 는 exe 파일 내용(배포할 때마다 한 번 다시 읽음) · 개발은 읽기 모듈 + 그 모듈이 import 하는 이 패키지 모듈 전부의
  소스 내용 · 둘 다 Python·openpyxl 판 포함.
- 저장하는 것 = 원본에서 읽은 값뿐(판정표·계약·산식이 들어간 값·정산서 금액은 저장하지 않음 · D-419 ③). 읽기 오류는 저장하지 않음.
- 원본 파일은 건드리지 않음 · 저장 폴더를 지워도 다음 실행이 다시 만듦.
"""
from __future__ import annotations

import ast
import hashlib
import os
import pickle
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path

import openpyxl

PKG = "coupang_analytics"
DIR = "_읽은결과"                 # output/정산서/_읽은결과
MAGIC = b"READ1\n"
_root: Path | None = None
_count: Counter = Counter()


def use(folder: Path | None) -> None:
    """저장 폴더를 정하고 켬(None = 끔) · 건수는 0부터."""
    global _root
    _root = Path(folder) if folder is not None else None
    _count.clear()


def note() -> str:
    """안내 줄 — 재사용·새로 읽음 파일 수(꺼져 있으면 '')."""
    if _root is None:
        return ""
    extra = "".join(f" · {k} {_count[k]}" for k in ("깨진 저장분", "저장 못 함") if _count[k])
    return f"읽은 결과 저장 — 재사용 {_count['재사용']}개 · 새로 읽음 {_count['새로 읽음']}개{extra}"


# ── 읽기 코드 판 ─────────────────────────────────────────────
def _imports(src: str, known: set) -> set:
    """소스 하나가 import 하는 이 패키지 모듈 이름(함수 안 import 포함)."""
    out: set = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.ImportFrom):
            base = (n.module or "").removeprefix(PKG).lstrip(".").split(".")[0]
            if n.level or (n.module or "").split(".")[0] == PKG:
                out |= {base} if base else {a.name for a in n.names}
        elif isinstance(n, ast.Import):
            out |= {a.name.split(".")[1] for a in n.names if a.name.startswith(PKG + ".")}
    return out & known


def module_closure(roots: tuple, folder: Path | None = None) -> list[str]:
    """읽기 모듈(roots) + 그 모듈들이 이어서 import 하는 이 패키지 모듈(이름 순)."""
    folder = folder or Path(__file__).parent
    known = {p.stem for p in folder.glob("*.py")}
    todo, seen = list(roots), set()
    while todo:
        m = todo.pop()
        if m not in seen:
            seen.add(m)
            todo += _imports((folder / f"{m}.py").read_text(encoding="utf-8"), known)
    return sorted(seen)


@lru_cache(maxsize=None)
def code_version(roots: tuple) -> str:
    h = hashlib.sha256(f"{sys.version}|openpyxl {openpyxl.__version__}".encode())
    if getattr(sys, "frozen", False):
        h.update(Path(sys.executable).read_bytes())
        return h.hexdigest()
    folder = Path(__file__).parent
    for m in module_closure((Path(__file__).stem, *roots)):
        h.update(m.encode() + b"\0" + (folder / f"{m}.py").read_bytes())
    return h.hexdigest()


# ── 저장·재사용 ──────────────────────────────────────────────
def _sha(p: Path) -> str:
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _stored(f: Path, ver: str) -> tuple | None:
    """(값,) — 저장분이 없거나 코드 판이 다르면 None · 깨졌으면 건수만 세고 None(원본을 다시 읽음)."""
    if not f.is_file():
        return None
    b = f.read_bytes()
    head = len(MAGIC) + 64
    if not b.startswith(MAGIC) or hashlib.sha256(b[head + 64:]).hexdigest() != b[head:head + 64].decode("ascii", "replace"):
        _count["깨진 저장분"] += 1
        return None
    return (pickle.loads(b[head + 64:]),) if b[len(MAGIC):head].decode("ascii") == ver else None


def _write(f: Path, ver: str, value) -> None:
    body = pickle.dumps(value, pickle.HIGHEST_PROTOCOL)
    tmp = f.with_name(f"{f.name}.{os.getpid()}.tmp")
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(MAGIC + ver.encode() + hashlib.sha256(body).hexdigest().encode() + body)
        os.replace(tmp, f)
    except OSError:                      # 디스크 부족·다른 프로그램이 쥠 = 이번만 저장 못 함(값은 원본에서 읽은 것 · 건수 안내)
        _count["저장 못 함"] += 1
        tmp.unlink(missing_ok=True)


def read(kind: str, path: Path, fn, roots: tuple):
    """fn(path) 값 — 내용·코드가 그대로면 저장분. roots = 읽기 코드가 든 모듈 이름들(`module_closure` 시작점)."""
    if _root is None:
        return fn(path)
    path, ver = Path(path), code_version(roots)
    sha = _sha(path)
    f = _root / kind / hashlib.sha256(f"{kind}|{path.name}|{sha}".encode()).hexdigest()[:40]
    got = _stored(f, ver)
    if got is not None:
        _count["재사용"] += 1
        return got[0]
    value = fn(path)
    _count["새로 읽음"] += 1
    if _sha(path) == sha:                # 읽는 사이 원본이 바뀌었으면 저장하지 않음
        _write(f, ver, value)
    return value
