"""앱·정산 프로그램 프로세스 제어 — D-010(소유자 2026-10-09).

- 18:00 무인(--auto) 앱이 시작되면 **기존 앱 창과 정산 프로그램을 끝낸다**(한 PC 에 앱 하나·정산 하나).
- **D-021**: 18:00(·재부팅 복구) 앱이 시작하면서 **정산도 함께 띄운다** → 정산은 ①판매수집 완료까지 대기 후 받고,
  다 받으면·다음 날 17:55 면 스스로 끝난다(settlement_watch.cycle_window). 예약작업은 없음(D-010 에서 폐지).
- **D-020(소유자 2026-10-10)**: 무인 ①②③ 완주 뒤 앱이 끝나도 정산은 계속(다음 18:00 까지). 그러나 **사람이 앱을
  닫거나 강제 종료(재배포 등)하면 정산도 종료** — 정산이 앱 PID 를 감시(`watch_parent`)하고, 무인 정상 완료는
  앱이 남긴 표시(`mark_app_finished`)로 구분한다(작업 관리자 강제 종료도 같은 경로로 잡힘).

프로세스 찾기 = PowerShell CIM(Win32_Process) — 배포(exe 이름)·개발(python 명령줄) 둘 다. 자기 자신 PID 는 제외.
모든 보조 명령은 콘솔창 없이(CREATE_NO_WINDOW — 함정 #8 깜빡임 방지).
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

_NO_CONSOLE = 0x08000000      # CREATE_NO_WINDOW
_BREAKAWAY = 0x01000000       # CREATE_BREAKAWAY_FROM_JOB
_NEW_GROUP = 0x00000200       # CREATE_NEW_PROCESS_GROUP(앱 쪽 Ctrl 신호와 분리)
SETTLE_EXE = "정산다운로드.exe"
APP_EXE = "쿠팡애널리틱스.exe"


def settlement_watch_cmd(parent_pid: int) -> tuple[list[str], str]:
    """정산 자동 수집(watch)을 띄울 명령 + 작업 폴더. 배포=정산다운로드.exe(형제)·개발=python tools/...
    `--parent`=앱 PID(D-020: 사람이 앱을 끄면 정산도 끝나게 감시)."""
    tail = ["watch", "--parent", str(parent_pid)]
    if getattr(sys, "frozen", False):
        folder = Path(sys.executable).parent
        return [str(folder / SETTLE_EXE), *tail], str(folder)
    root = Path(__file__).resolve().parents[2]
    return [sys.executable, str(root / "tools" / "settlement_download.py"), *tail], str(root)


def start_settlement_watch(log) -> subprocess.Popen | None:
    """정산 프로그램을 창 없이 띄운다(이미 돌면 정산 쪽 잠금이 둘째를 바로 끝냄). 실패는 로그 후 None."""
    cmd, cwd = settlement_watch_cmd(os.getpid())
    if getattr(sys, "frozen", False) and not Path(cmd[0]).exists():
        log(f"[정산] ⚠ {SETTLE_EXE} 를 찾을 수 없어 정산 자동 수집을 못 띄움: {cmd[0]}")
        return None
    # 앱(작업 스케줄러 작업)이 ③ 뒤 끝나도 정산은 계속 돌아야 한다 → 작업 묶음(job)에서 분리해 띄운다
    # (CREATE_BREAKAWAY_FROM_JOB). 그 묶음이 분리를 막으면 분리 없이 띄우고 알린다.
    proc, err = None, None
    for flags, note in ((_NO_CONSOLE | _BREAKAWAY | _NEW_GROUP, ""),
                        (_NO_CONSOLE | _NEW_GROUP, " — ⚠ 작업 묶음 분리 불가: 앱이 끝날 때 정산도 끝날 수 있음")):
        try:
            proc = subprocess.Popen(cmd, cwd=cwd, creationflags=flags, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            break
        except OSError as exc:
            err = exc
    if proc is None:
        log(f"[정산] ⚠ 정산 자동 수집 시작 실패: {err}")
        return None
    log("[정산] 정산 자동 수집 시작 — ①판매수집 완료를 기다렸다가 받음·다 받거나 17:55 면 종료·"
        "앱을 사람이 끄면 함께 종료(상태=정산 탭)" + note)
    return proc


# ── D-020: 앱 종료 감시 ─────────────────────────────────────────────
APP_DONE_FILE = Path("output") / "정산" / "로그" / "_앱정상종료.json"   # 무인 ①②③ 완주 표시(앱 PID)
_SYNCHRONIZE = 0x00100000
_WAIT_OBJECT_0 = 0


def mark_app_finished(done_file: Path = APP_DONE_FILE, pid: int | None = None) -> None:
    """무인 실행이 ①②③을 다 끝내고 **정상 종료**한다는 표시 — 정산은 이 앱이 끝나도 계속 돈다."""
    done_file.parent.mkdir(parents=True, exist_ok=True)
    done_file.write_text(json.dumps({"pid": pid or os.getpid(), "at": datetime.now().isoformat(timespec="seconds")},
                                    ensure_ascii=False), encoding="utf-8")


def app_finished_normally(pid: int, done_file: Path = APP_DONE_FILE) -> bool:
    """그 앱(PID)이 정상 완료 표시를 남겼나(다른·이전 앱의 표시는 무효)."""
    try:
        return int(json.loads(done_file.read_text(encoding="utf-8")).get("pid", 0)) == pid
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def watch_parent(parent_pid: int, on_gone, done_file: Path = APP_DONE_FILE, poll_sec: float = 3.0) -> threading.Thread:
    """앱(parent_pid)이 끝나면 — 정상 완료 표시가 없을 때만 — on_gone() 호출(사람이 닫음·강제 종료).
    시작 시 프로세스 핸들을 열어 두고 그 핸들로 기다린다(PID 재사용에 안전). 이미 없으면 바로 판정."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = k32.OpenProcess(_SYNCHRONIZE, False, int(parent_pid))

    def _loop() -> None:
        if handle:
            while k32.WaitForSingleObject(handle, int(poll_sec * 1000)) != _WAIT_OBJECT_0:
                pass
            k32.CloseHandle(handle)
        if not app_finished_normally(parent_pid, done_file):
            on_gone()
    t = threading.Thread(target=_loop, name="app-parent-watch", daemon=True)
    t.start()
    return t


def kill_self_tree() -> None:
    """정산 프로그램 자신과 그 자식(Chrome)을 함께 종료."""
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(os.getpid())], capture_output=True,
                   creationflags=_NO_CONSOLE)


def _ps(script: str, env_extra: dict[str, str]) -> str:
    env = dict(os.environ)
    env.update(env_extra)
    r = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True,
                       timeout=30, env=env, creationflags=_NO_CONSOLE)
    return r.stdout or ""


# 배포 exe 이름이 같거나, **python 프로세스**인데 명령줄에 스크립트 표식이 있는 것(개발)만 — 편집기 등 같은 파일을
# 연 다른 프로그램은 제외. 자기 PID 제외. 자식(그 프로그램이 띄운 Chrome)까지 트리째 종료. 종료한 것마다 'K' 한 줄.
_KILL_PS = ("Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne [int]$env:SM_SELF -and "
            "($_.Name -eq $env:SM_NAME -or ($_.Name -like 'python*' -and $_.CommandLine -and "
            "$_.CommandLine.Contains($env:SM_MARK))) } | "
            "ForEach-Object { taskkill /F /T /PID $_.ProcessId 2>&1 | Out-Null; 'K' }")


def _kill(name: str, mark: str, log, what: str, tag: str) -> int:
    try:
        n = _ps(_KILL_PS, {"SM_SELF": str(os.getpid()), "SM_NAME": name, "SM_MARK": mark}).count("K")
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"{tag} ⚠ {what} 종료 확인 실패({exc.__class__.__name__}) — 계속")
        return 0
    if n:
        log(f"{tag} 실행 중이던 {what} {n}개 종료")
    return n


def stop_settlement(log, tag: str = "[시작]") -> int:
    """정산 프로그램(배포 exe·개발 python)과 그 Chrome 종료 — 18:00 시작 정리·정산 탭 [정산 중지] 공용. 종료 수 반환."""
    return _kill(SETTLE_EXE, "settlement_download.py", log, "정산 프로그램", tag)


def stop_other_apps(log) -> int:
    """다른 앱 창(배포 exe·개발 app_qt.py) 종료 — 18:00 무인 실행만 남긴다(자기 자신 제외)."""
    return _kill(APP_EXE, "app_qt.py", log, "이전 앱", "[시작]")


def prepare_auto_start(log) -> None:
    """18:00 무인 시작 정리 — 이전 앱·정산 프로그램 종료(옛 정산 예약작업 제거는 install.ps1 이 설치 때 함)."""
    stop_other_apps(log)
    stop_settlement(log)
