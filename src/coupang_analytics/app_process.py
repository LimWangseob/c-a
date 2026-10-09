"""앱·정산 프로그램 프로세스 제어 — D-010(소유자 2026-10-09).

- 18:00 무인(--auto) 앱이 시작되면 **기존 앱 창과 정산 프로그램을 끝낸다**(한 PC 에 앱 하나·정산 하나).
- **①판매수집이 끝나면 앱이 정산 프로그램을 띄운다**(예약작업 '쿠팡애널리틱스_정산다운로드'는 없앰).
- 정산은 다 받으면 스스로 끝난다(tools/settlement_download.py watch·settlement_watch.plan_after_pass).

프로세스 찾기 = PowerShell CIM(Win32_Process) — 배포(exe 이름)·개발(python 명령줄) 둘 다. 자기 자신 PID 는 제외.
모든 보조 명령은 콘솔창 없이(CREATE_NO_WINDOW — 함정 #8 깜빡임 방지).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_NO_CONSOLE = 0x08000000      # CREATE_NO_WINDOW
_BREAKAWAY = 0x01000000       # CREATE_BREAKAWAY_FROM_JOB
_NEW_GROUP = 0x00000200       # CREATE_NEW_PROCESS_GROUP(앱 쪽 Ctrl 신호와 분리)
SETTLE_EXE = "정산다운로드.exe"
APP_EXE = "쿠팡애널리틱스.exe"


def settlement_watch_cmd() -> tuple[list[str], str]:
    """정산 자동 수집(watch)을 띄울 명령 + 작업 폴더. 배포=정산다운로드.exe(형제)·개발=python tools/..."""
    if getattr(sys, "frozen", False):
        folder = Path(sys.executable).parent
        return [str(folder / SETTLE_EXE), "watch"], str(folder)
    root = Path(__file__).resolve().parents[2]
    return [sys.executable, str(root / "tools" / "settlement_download.py"), "watch"], str(root)


def start_settlement_watch(log) -> subprocess.Popen | None:
    """정산 프로그램을 창 없이 띄운다(이미 돌면 정산 쪽 잠금이 둘째를 바로 끝냄). 실패는 로그 후 None."""
    cmd, cwd = settlement_watch_cmd()
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
    log("[정산] ①판매수집 완료 → 정산 자동 수집 시작(다 받으면 스스로 종료·상태=정산 탭)" + note)
    return proc


def _ps(script: str, env_extra: dict[str, str]) -> str:
    env = dict(os.environ)
    env.update(env_extra)
    r = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True,
                       timeout=30, env=env, creationflags=_NO_CONSOLE)
    return r.stdout or ""


# 배포 exe 이름이 같거나, **python 프로세스**인데 명령줄에 스크립트 표식이 있는 것(개발)만 — 편집기 등 같은 파일을
# 연 다른 프로그램은 제외. 자기 PID 제외. 종료한 것마다 'K' 한 줄 출력.
_KILL_PS = ("Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne [int]$env:SM_SELF -and "
            "($_.Name -eq $env:SM_NAME -or ($_.Name -like 'python*' -and $_.CommandLine -and "
            "$_.CommandLine.Contains($env:SM_MARK))) } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; 'K' }")


def _kill(name: str, mark: str, log, what: str) -> int:
    try:
        n = _ps(_KILL_PS, {"SM_SELF": str(os.getpid()), "SM_NAME": name, "SM_MARK": mark}).count("K")
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"[시작] ⚠ {what} 종료 확인 실패({exc.__class__.__name__}) — 계속")
        return 0
    if n:
        log(f"[시작] 실행 중이던 {what} {n}개 종료")
    return n


def stop_settlement(log) -> int:
    """정산 프로그램(배포 exe·개발 python) 종료 — 그 Chrome 은 이어서 reap_orphan_chrome 이 정리."""
    return _kill(SETTLE_EXE, "settlement_download.py", log, "정산 프로그램")


def stop_other_apps(log) -> int:
    """다른 앱 창(배포 exe·개발 app_qt.py) 종료 — 18:00 무인 실행만 남긴다(자기 자신 제외)."""
    return _kill(APP_EXE, "app_qt.py", log, "이전 앱")


# 옛 예약작업(정산 watch: 로그온+매일 08:00) 제거 — 실행 인자 'watch' 로 찾음(한글 작업명 인코딩 문제 회피).
_UNREG_PS = ("Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { "
             "((($_.Actions | ForEach-Object { [string]$_.Arguments }) -join ' ') -match '(^|\\s)watch(\\s|$)') } | "
             "ForEach-Object { try { Unregister-ScheduledTask -TaskName $_.TaskName -TaskPath $_.TaskPath "
             "-Confirm:$false -ErrorAction Stop; 'K' } catch { 'E' } }")


def remove_legacy_settlement_task(log) -> int:
    """정산 예약작업(로그온·08:00)을 없앤다 — 이제 앱이 ① 뒤에만 띄움(D-010). 실패(권한)는 로그로 알림."""
    try:
        out = _ps(_UNREG_PS, {})
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"[시작] ⚠ 옛 정산 예약작업 확인 실패({exc.__class__.__name__})")
        return 0
    if "E" in out:
        log("[시작] ⚠ 옛 정산 예약작업(로그온·08:00) 삭제 실패(권한) — 작업 스케줄러에서 "
            "'쿠팡애널리틱스_정산다운로드'를 직접 삭제하세요")
    n = out.count("K")
    if n:
        log(f"[시작] 옛 정산 예약작업 {n}개 삭제(이제 ①판매수집 뒤 앱이 정산을 띄움)")
    return n


def prepare_auto_start(log) -> None:
    """18:00 무인 시작 정리 — 이전 앱·정산 프로그램 종료 + 옛 정산 예약작업 제거(D-010)."""
    stop_other_apps(log)
    stop_settlement(log)
    remove_legacy_settlement_task(log)
