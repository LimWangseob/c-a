"""정산 표본 시험 도구(S1 · D-353) 보조 — 읽은 파일 지문 · 읽기 코드 지문 · 네트워크 막기. 정산 코드 본체는 고치지 않음.

- 읽은 파일 = 파이썬 감사 훅 'open'(builtins.open·io.open·os.open 전부 · openpyxl·gzip 포함)으로 읽기 모드 파일을 모음 ·
  목록을 본 폴더('os.scandir'·'os.listdir' · glob·iterdir 포함) + 읽은 파일의 부모 폴더 = 이름 목록 지문(새 파일이 생겨도 무효).
- 파일 지문 = (경로, 크기, 수정 시각 ns) · 폴더 지문 = 정렬한 이름 목록의 sha1. 하나라도 다르면 저장 자료 무효 → 다시 읽기.
- 읽기 코드 지문 = 읽는 동안 실제로 돈 src 파일(sys.monitoring PY_START)의 내용 sha1 — 다른 src 가 그 파일을 바꿨으면 같은 저장 자료를 못 씀.
- 네트워크 = 감사 훅에서 socket.connect·getaddrinfo 를 막음(구글시트·API 호출은 ❌ 오류로 끝남 · 조용한 대체 없음).
"""
from __future__ import annotations

import hashlib
import importlib
import marshal
import os
import pickle
import sys
import types
from pathlib import Path

_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT
_CODE_EXT = (".py", ".pyc", ".pyd", ".dll", ".so")
_NET_EVENTS = ("socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "urllib.Request")


class NetworkBlocked(RuntimeError):
    pass


class _State:
    installed = False
    net_blocked = False
    rec: "Reads | None" = None


def _is_write(mode, flags) -> bool:
    if isinstance(mode, str):
        return any(ch in mode for ch in "wax+")
    return isinstance(flags, int) and bool(flags & _WRITE_FLAGS)


def _hook(event: str, args: tuple) -> None:
    if _State.net_blocked and event in _NET_EVENTS:
        raise NetworkBlocked(f"네트워크 금지(표본 시험 도구) — {event} {args[:2]!r}")
    rec = _State.rec
    if rec is None:
        return
    if event == "open":
        rec.on_open(args)
    elif event in ("os.scandir", "os.listdir"):
        rec.on_list(args[0] if args else ".")


def install(block_network: bool = True) -> None:
    """감사 훅 1회 등록(되돌릴 수 없음 · 프로세스 끝까지) — 기록은 Reads 가 켜진 동안만."""
    _State.net_blocked = _State.net_blocked or block_network
    if not _State.installed:
        sys.addaudithook(_hook)
        _State.installed = True


def _norm(p) -> str | None:
    if isinstance(p, int):
        return None
    try:
        return str(Path(os.fsdecode(p)).resolve())
    except (TypeError, ValueError, OSError):
        return None


class Reads:
    """with Reads(제외 폴더들) as r: … → r.files(읽기만 한 파일) · r.dirs(목록 본 폴더 + 읽은 파일 부모)."""

    def __init__(self, exclude: tuple = ()):
        self.exclude = tuple(str(Path(x).resolve()) for x in exclude)
        self.read: set = set()
        self.written: set = set()
        self.listed: set = set()

    def _skip(self, p: str) -> bool:
        return p.endswith(_CODE_EXT) or any(p == x or p.startswith(x + os.sep) for x in self.exclude)

    def on_open(self, args: tuple) -> None:
        p = _norm(args[0])
        if p is None or self._skip(p):
            return
        (self.written if _is_write(args[1] if len(args) > 1 else None, args[2] if len(args) > 2 else None) else self.read).add(p)

    def on_list(self, path) -> None:
        p = _norm(path)
        if p is not None and not self._skip(p):
            self.listed.add(p)

    def __enter__(self) -> "Reads":
        install()
        _State.rec = self
        return self

    def __exit__(self, *exc) -> None:
        _State.rec = None

    def files(self) -> list[str]:
        return sorted(p for p in self.read - self.written if os.path.isfile(p))

    def dirs(self) -> list[str]:
        parents = {str(Path(p).parent) for p in self.files()}
        return sorted(d for d in (self.listed | parents) if os.path.isdir(d) and not self._skip(d))


def _dir_sig(d: str) -> str:
    return hashlib.sha1("\n".join(sorted(os.listdir(d))).encode("utf-8")).hexdigest()


def fingerprint(files: list[str], dirs: list[str]) -> dict:
    """{"files": {경로: [크기, 수정 ns]}, "dirs": {경로: 이름 목록 sha1}} — 없는 경로는 None(그대로 기록 · 비교에서 다름)."""
    fs = {}
    for p in files:
        st = os.stat(p) if os.path.exists(p) else None
        fs[p] = [st.st_size, st.st_mtime_ns] if st else None
    return {"files": fs, "dirs": {d: (_dir_sig(d) if os.path.isdir(d) else None) for d in dirs}}


def changed(fp: dict) -> list[str]:
    """저장 때 지문과 지금이 다른 경로 목록(비면 그대로) — 파일 크기·수정 시각 · 폴더 이름 목록."""
    now = fingerprint(list(fp["files"]), list(fp["dirs"]))
    out = [f"파일 {p}" for p, v in fp["files"].items() if now["files"][p] != v]
    return out + [f"폴더 {d}" for d, v in fp["dirs"].items() if now["dirs"][d] != v]


class CodeRun:
    """with CodeRun(src) as c: … → c.files = 그 동안 함수가 처음 실행된 src 아래 .py (상대 경로). sys.monitoring(3.12+) · 코드마다 1번만 잡고 끔."""

    TOOL = 4    # sys.monitoring 도구 번호(0~5 · 디버거 0·커버리지 1·프로파일러 2·최적화 5 피함)

    def __init__(self, src: Path):
        self.src = str(Path(src).resolve())
        self.files: set = set()

    def _start(self, code, _offset):
        mon = sys.monitoring
        f = code.co_filename
        if f.startswith(self.src + os.sep):
            self.files.add(Path(f).resolve().relative_to(self.src).as_posix())
        return mon.DISABLE

    def __enter__(self) -> "CodeRun":
        mon = sys.monitoring
        mon.use_tool_id(self.TOOL, "settlement_sample")
        mon.register_callback(self.TOOL, mon.events.PY_START, self._start)
        mon.set_events(self.TOOL, mon.events.PY_START)
        mon.restart_events()        # 앞에서 DISABLE 된 코드도 다시 잡음(한 프로세스에서 여러 번 쓸 때)
        return self

    def __exit__(self, *exc) -> None:
        mon = sys.monitoring
        mon.set_events(self.TOOL, 0)
        mon.register_callback(self.TOOL, mon.events.PY_START, None)
        mon.free_tool_id(self.TOOL)


def _local_fn(module: str, qualname: str, code: bytes, defaults, closure, kwdefaults):
    """저장한 이름 없는 함수 되살리기 — 그 모듈 전역 + 저장한 코드(같은 파이썬 판 · 읽기 코드 지문이 같을 때만 불러옴)."""
    g = importlib.import_module(module).__dict__
    cells = tuple(types.CellType(v) for v in closure) if closure is not None else None
    f = types.FunctionType(marshal.loads(code), g, qualname.rsplit(".", 1)[-1], defaults, cells)
    f.__qualname__, f.__kwdefaults__ = qualname, kwdefaults
    return f


class Pickler(pickle.Pickler):
    """기본 pickle + 모듈에서 이름으로 못 찾는 함수(lambda·함수 안 함수 · 예 `defaultdict(lambda: [0, 0])`)를 코드째 저장.
    정산 코드 본체를 바꾸지 않고 ctx 를 저장하려고 씀. 코드 = marshal(파이썬 판마다 다름 → 저장 자료에 판을 함께 적음)."""

    def reducer_override(self, obj):
        if not isinstance(obj, types.FunctionType) or "<locals>" not in obj.__qualname__ and "<lambda>" not in obj.__qualname__:
            return NotImplemented
        closure = tuple(c.cell_contents for c in obj.__closure__) if obj.__closure__ else None
        return _local_fn, (obj.__module__, obj.__qualname__, marshal.dumps(obj.__code__), obj.__defaults__, closure, obj.__kwdefaults__)


def dump(obj, f) -> None:
    Pickler(f, protocol=pickle.HIGHEST_PROTOCOL).dump(obj)


def code_sig(src: Path, rel_files: list[str]) -> dict:
    """{상대 경로: 내용 sha1 또는 None(그 src 에 없음)} — 읽기 코드가 같은지 src 사이 비교용."""
    out = {}
    for rel in sorted(rel_files):
        p = Path(src) / rel
        out[rel] = hashlib.sha1(p.read_bytes()).hexdigest() if p.is_file() else None
    return out
