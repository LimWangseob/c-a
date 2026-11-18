"""정산 프로세스 메모리·Chrome 기록과 바퀴 사이 자기 Chrome 정리(T-113 · 운용 PC 정산 MemoryError 11-16·11-18).

- `commit_mb()` = 이 프로세스의 커밋(지금·최고, MB) — 새 프로세스 없이 kernel32 로 읽음(메모리 바닥에서도 가벼움).
- `sweep_own_chrome()` = 바퀴 사이(정산이 연 브라우저가 없을 때) **이 프로세스 자손 chrome.exe 만** 종료하고,
  PC 의 Chrome 전체 수·작업집합 합·우리 자동화(data 폴더 프로필) 수·부모 없는 우리 Chrome 수를 센다.
  앱·소유자 Chrome 은 자손이 아니므로 건드리지 않는다(앱 몫 잔여는 앱 시작 `reap_orphan_chrome` 이 정리 · 여기선 수만 기록).
- 판정은 순수 함수(`parse_census`·`own_tree`·`summarize`) — 시험은 가짜 프로세스 표로(실 프로세스 종료 없음).
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as _W
import os
import subprocess
from pathlib import Path

_NO_CONSOLE = 0x08000000      # CREATE_NO_WINDOW

# chrome.exe 한 줄 = PID · 부모PID · 작업집합(바이트) · 우리 data 폴더 프로필(1/0) · 주 프로세스(--type= 없음 1/0) · 부모 살아 있음(1/0)
_CENSUS_PS = (
    "$all = Get-CimInstance Win32_Process; $ids = @{}; foreach ($p in $all) { $ids[[int]$p.ProcessId] = 1 }; "
    "foreach ($p in $all) { if ($p.Name -ne 'chrome.exe') { continue }; $c = [string]$p.CommandLine; "
    "($p.ProcessId, $p.ParentProcessId, $p.WorkingSetSize, [int]($c.ToLower().Contains($env:SM_DATA)), "
    "[int](-not $c.Contains('--type=')), [int]($ids.ContainsKey([int]$p.ParentProcessId))) -join [char]9 }")


class _PMC(ctypes.Structure):
    _fields_ = [("cb", _W.DWORD), ("PageFaultCount", _W.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t)]


def commit_mb() -> tuple[int, int]:
    """이 프로세스 커밋(private) (지금, 최고) MB — 작업 관리자 '커밋 크기'와 같은 값."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetCurrentProcess.restype = _W.HANDLE
    k32.K32GetProcessMemoryInfo.argtypes = [_W.HANDLE, ctypes.POINTER(_PMC), _W.DWORD]
    c = _PMC()
    c.cb = ctypes.sizeof(c)
    if not k32.K32GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb):
        raise OSError(ctypes.get_last_error(), "K32GetProcessMemoryInfo 실패")
    return c.PagefileUsage >> 20, c.PeakPagefileUsage >> 20


def parse_census(text: str) -> list[dict]:
    """`_CENSUS_PS` 출력 → chrome.exe 표. 칸 수가 다른 줄은 버리지 않고 오류(조용히 빼면 수가 틀림)."""
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.strip().split("\t")
        if len(parts) != 6:
            raise ValueError(f"Chrome 조회 줄 형식이 다름: {line[:80]!r}")
        pid, ppid, ws, ours, main, alive = (int(x or 0) for x in parts)
        rows.append({"pid": pid, "ppid": ppid, "ws": ws, "ours": bool(ours), "main": bool(main), "parent_alive": bool(alive)})
    return rows


def own_tree(rows: list[dict], root_pid: int) -> list[int]:
    """root_pid(정산 프로세스)의 자손 chrome.exe PID 전부 — 정산이 띄운 Chrome 주 프로세스와 그 렌더러 등."""
    kids: dict[int, list[int]] = {}
    for r in rows:
        kids.setdefault(r["ppid"], []).append(r["pid"])
    out, todo = [], list(kids.get(root_pid, []))
    while todo:
        pid = todo.pop()
        if pid in out or pid == root_pid:
            continue
        out.append(pid)
        todo += kids.get(pid, [])
    return sorted(out)


def summarize(rows: list[dict], own: list[int]) -> dict:
    """기록할 수 — Chrome 전체·작업집합 합(MB)·우리 자동화(data 폴더)·부모 없는 우리 Chrome(주 프로세스)·정산 자손."""
    return {"전체": len(rows), "전체MB": sum(r["ws"] for r in rows) >> 20,
            "우리": sum(1 for r in rows if r["ours"]),
            "부모없는우리": sum(1 for r in rows if r["ours"] and r["main"] and not r["parent_alive"]),
            "정산자손": len(own)}


def _census(data_dir: str) -> list[dict]:
    env = dict(os.environ, SM_DATA=str(Path(data_dir).resolve()).lower())
    r = subprocess.run(["powershell", "-NoProfile", "-Command", _CENSUS_PS], capture_output=True, text=True,
                       timeout=60, env=env, creationflags=_NO_CONSOLE)
    if r.returncode != 0:
        raise OSError(f"Chrome 조회 종료코드 {r.returncode}: {(r.stderr or '').strip()[:120]}")
    return parse_census(r.stdout or "")


def sweep_own_chrome(data_dir: str = "data", root_pid: int | None = None) -> dict:
    """바퀴 사이: 이 프로세스 자손 Chrome 을 트리째 종료(taskkill /T — 위에서부터) 후 수를 반환.
    반환 = summarize(정리 전) + '종료' = 종료 명령을 보낸 자손 수 + '남은자손' = 정리 뒤 다시 센 자손 수."""
    root = os.getpid() if root_pid is None else root_pid
    rows = _census(data_dir)
    own = own_tree(rows, root)
    info = summarize(rows, own)
    for r in rows:
        if r["pid"] in own and r["ppid"] == root:       # 맨 위(정산이 직접 띄운 Chrome)만 — /T 로 그 아래까지
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(r["pid"])], capture_output=True, timeout=30,
                           creationflags=_NO_CONSOLE)
    info["종료"] = len(own)
    info["남은자손"] = len(own_tree(_census(data_dir), root)) if own else 0
    return info
