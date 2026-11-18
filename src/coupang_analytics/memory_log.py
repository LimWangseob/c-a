"""실행 로그 `[메모리]` 줄(D-346 ④ · T-113) — 야간 무인 실행의 메모리를 로그만 보고 알 수 있게.

소유자 2026-11-18: "보고보다 로그에 남겨줘. 야간에 실행되는대 내가알수가 없어."

- 한 줄 = 이 프로세스 커밋 MB(지금·최고) · PC 사용 가능/전체 MB(%) · Chrome 수·작업집합 합 MB. 큰 할당 단계는 전 값과 증가분.
- 기준선(`PC_AVAIL_WARN_PCT` · `PROC_WARN_MB`)을 넘으면 같은 줄에 `⚠메모리(사유)`.
- 측정은 새 프로세스 없이 kernel32 만(PowerShell 조회는 계정마다엔 무거움) — 메모리 바닥에서도 가벼움.
- 측정 실패도 그 칸에 사유를 적는다(폴백·생략 없음). 오류 판정 단어('❌'·'실패')는 쓰지 않음 — 실행 판정에 안 섞이게.
- 실행 끝 [실행 결과 종합]에 `summary()` 한 줄 = 그날 최고 커밋(시각·단계) · PC 사용 가능 최저(시각·단계) · ⚠ 횟수.
- 별도 프로세스(정산 집계 자식)의 기록은 `state()` → JSON → 부모 `merge()` 로 합친다.
판정·형식은 순수(`Tracker(measure_fn=가짜)`) — 시험은 가짜 측정값으로.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as _W
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

from .settlement_memory import _PMC, commit_mb

PC_AVAIL_WARN_PCT = 15     # PC 사용 가능 메모리가 전체의 15% 미만이면 ⚠ (D-346 기준선)
PROC_WARN_MB = 1024        # 이 프로세스 커밋이 1GB 를 넘으면 ⚠ (D-346 기준선)
_ERRORS = (OSError, ValueError, MemoryError)   # 측정 실패 = 그 칸에 사유(실행은 계속)


class _MSEX(ctypes.Structure):
    _fields_ = [("dwLength", _W.DWORD), ("dwMemoryLoad", _W.DWORD), ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


class _PE32(ctypes.Structure):
    _fields_ = [("dwSize", _W.DWORD), ("cntUsage", _W.DWORD), ("th32ProcessID", _W.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", _W.DWORD), ("cntThreads", _W.DWORD),
                ("th32ParentProcessID", _W.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", _W.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


def pc_memory_mb() -> tuple[int, int]:
    """PC 실제 메모리 (사용 가능, 전체) MB — GlobalMemoryStatusEx(작업 관리자 '사용 가능')."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    m = _MSEX()
    m.dwLength = ctypes.sizeof(m)
    if not k32.GlobalMemoryStatusEx(ctypes.byref(m)):
        raise OSError(ctypes.get_last_error(), "GlobalMemoryStatusEx")
    return m.ullAvailPhys >> 20, m.ullTotalPhys >> 20


def chrome_usage() -> tuple[int, int, int]:
    """PC 의 chrome.exe (수, 작업집합 합 MB, 메모리를 못 읽은 수) — 프로세스 목록 스냅샷 + 프로세스마다 메모리 조회."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = _W.HANDLE
    k32.OpenProcess.restype = _W.HANDLE
    k32.CloseHandle.argtypes = [_W.HANDLE]
    k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = [_W.HANDLE, ctypes.POINTER(_PE32)]
    k32.K32GetProcessMemoryInfo.argtypes = [_W.HANDLE, ctypes.POINTER(_PMC), _W.DWORD]
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)            # TH32CS_SNAPPROCESS
    if not snap or snap == _W.HANDLE(-1).value:
        raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot")
    n = ws = unread = 0
    try:
        e = _PE32()
        e.dwSize = ctypes.sizeof(e)
        ok = k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            if e.szExeFile.lower() == "chrome.exe":
                n += 1
                h = k32.OpenProcess(0x1000, False, e.th32ProcessID)     # PROCESS_QUERY_LIMITED_INFORMATION
                c = _PMC()
                c.cb = ctypes.sizeof(c)
                if h and k32.K32GetProcessMemoryInfo(h, ctypes.byref(c), c.cb):
                    ws += c.WorkingSetSize
                else:
                    unread += 1                                  # 그 사이 끝난 프로세스 등 — 수는 세고 MB 는 '못 읽음'으로 표시
                if h:
                    k32.CloseHandle(h)
            ok = k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)
    return n, ws >> 20, unread


@dataclass
class Sample:
    """한 번 잰 값 — 칸마다 값 또는 '측정 못 함' 사유 문자열."""
    proc: tuple[int, int] | str          # (지금, 최고) MB
    pc: tuple[int, int] | str            # (사용 가능, 전체) MB
    chrome: tuple[int, int, int] | str   # (수, 작업집합 MB, 못 읽은 수)


def _try(fn):
    try:
        return fn()
    except _ERRORS as exc:
        return f"측정 못 함({exc.__class__.__name__}: {str(exc)[:80]})"


def measure() -> Sample:
    return Sample(_try(commit_mb), _try(pc_memory_mb), _try(chrome_usage))


def _pct(pc: tuple[int, int]) -> float:
    return pc[0] * 100 / pc[1] if pc[1] else 0.0


def _proc_text(role: str, s: Sample, before: Sample | None) -> str:
    if not isinstance(s.proc, tuple):
        return f"{role} 커밋 {s.proc}"
    out = f"{role} 커밋 {s.proc[0]}MB(최고 {s.proc[1]}MB)"
    if before is not None and isinstance(before.proc, tuple):
        out += f" · 전 {before.proc[0]}MB → {s.proc[0] - before.proc[0]:+d}MB"
    return out


def _pc_text(s: Sample) -> str:
    return f"PC 사용 가능 {s.pc[0]}/{s.pc[1]}MB({_pct(s.pc):.0f}%)" if isinstance(s.pc, tuple) else f"PC 메모리 {s.pc}"


def _chrome_text(s: Sample) -> str:
    if not isinstance(s.chrome, tuple):
        return f"Chrome {s.chrome}"
    return f"Chrome {s.chrome[0]}개 {s.chrome[1]}MB" + (f"(메모리 못 읽은 {s.chrome[2]}개)" if s.chrome[2] else "")


class Tracker:
    """한 프로세스의 `[메모리]` 줄과 그날 최고 — role = 줄에 쓸 프로세스 이름('정산 프로세스'·'앱 프로세스')."""

    def __init__(self, role: str, *, measure_fn=measure, clock=datetime.now,
                 proc_warn_mb: int = PROC_WARN_MB, pc_warn_pct: int = PC_AVAIL_WARN_PCT):
        self.role, self._measure, self._clock = role, measure_fn, clock
        self.proc_warn_mb, self.pc_warn_pct = proc_warn_mb, pc_warn_pct
        self.reset()

    def reset(self) -> None:
        self.n = self.warns = self.fails = 0
        self.top: tuple | None = None      # (커밋 최고 MB, 시각, 단계) — OS 최고값이 처음 보인 측정
        self.low: tuple | None = None      # (PC 사용 가능 최저 %, 시각, 단계)

    def _warn_why(self, s: Sample) -> list[str]:
        why = []
        if isinstance(s.pc, tuple) and s.pc[1] and _pct(s.pc) < self.pc_warn_pct:
            why.append(f"PC 사용 가능 {_pct(s.pc):.0f}% < {self.pc_warn_pct}%")
        if isinstance(s.proc, tuple) and s.proc[0] > self.proc_warn_mb:
            why.append(f"{self.role} {s.proc[0]}MB > {self.proc_warn_mb}MB")
        return why

    def _note(self, s: Sample, stage: str, why: list) -> None:
        t = self._clock().strftime("%H:%M:%S")
        self.n += 1
        self.warns += bool(why)
        self.fails += sum(isinstance(v, str) for v in (s.proc, s.pc, s.chrome))
        if isinstance(s.proc, tuple) and (self.top is None or s.proc[1] > self.top[0]):
            self.top = (s.proc[1], t, stage)
        if isinstance(s.pc, tuple) and s.pc[1] and (self.low is None or _pct(s.pc) < self.low[0]):
            self.low = (_pct(s.pc), t, stage)

    def line(self, stage: str, *, before: Sample | None = None, note: str = "") -> str:
        """지금 재서 한 줄. before = 단계 전 값(증가분 표시) · note = 덧붙일 말."""
        s = self._measure()
        why = self._warn_why(s)
        self._note(s, stage, why)
        head = f"[메모리] ⚠메모리({' · '.join(why)}) " if why else "[메모리] "
        return (f"  {head}{stage} · {_proc_text(self.role, s, before)} · {_pc_text(s)} · {_chrome_text(s)}"
                + (f" · {note}" if note else ""))

    def mark(self) -> Sample:
        """단계 전 값(줄 없음 · 종합 횟수에 안 셈)."""
        return self._measure()

    @contextmanager
    def around(self, stage: str, log):
        """큰 할당 후보 단계 — 끝나면(예외여도) 전 값·증가분이 든 한 줄."""
        before = self.mark()
        try:
            yield
        finally:
            log(self.line(f"{stage} 뒤", before=before))

    def state(self) -> dict:
        return {"n": self.n, "warns": self.warns, "fails": self.fails, "top": self.top, "low": self.low}

    def merge(self, st: dict, label: str) -> None:
        """별도 프로세스 기록을 합침 — 최고·최저는 그 프로세스 이름(label)을 단계 앞에 붙임."""
        self.n += int(st.get("n") or 0)
        self.warns += int(st.get("warns") or 0)
        self.fails += int(st.get("fails") or 0)
        top, low = st.get("top"), st.get("low")
        if top and (self.top is None or top[0] > self.top[0]):
            self.top = (top[0], top[1], f"{label} {top[2]}")
        if low and (self.low is None or low[0] < self.low[0]):
            self.low = (low[0], low[1], f"{label} {low[2]}")

    def summary(self) -> str:
        """[실행 결과 종합] 한 줄 — 그날 최고 커밋(시각·단계) · PC 사용 가능 최저 · ⚠ 횟수 · 못 잰 칸 수."""
        if not self.n:
            return "[메모리] 이번 실행 측정 0회 — 기록 없음(확인 필요)"
        top = f"최고 커밋 {self.top[0]}MB({self.top[1]} {self.top[2]})" if self.top else "커밋 측정 못 함"
        low = f"PC 사용 가능 최저 {self.low[0]:.0f}%({self.low[1]} {self.low[2]})" if self.low else "PC 메모리 측정 못 함"
        return (f"[메모리] {top} · {low} · ⚠메모리 {self.warns}회(기준 PC 사용 가능 < {self.pc_warn_pct}% 또는 "
                f"프로세스 > {self.proc_warn_mb}MB) · 측정 {self.n}회" + (f"(못 잰 칸 {self.fails}개)" if self.fails else ""))


APP = Tracker("앱 프로세스")      # 앱 ①②③ 실행 — RunSummary 가 실행 시작 때 reset


__all__ = ["APP", "PC_AVAIL_WARN_PCT", "PROC_WARN_MB", "Sample", "Tracker", "chrome_usage", "measure", "pc_memory_mb"]
