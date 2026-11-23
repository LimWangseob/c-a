r"""배포 업데이트(deploy/update.ps1 · 업데이트.bat) 오프라인 검증 — 가짜 프로세스·임시 설치 폴더에서만 돈다.

기대값 출처 = 소유자 11-23 원문 '배포 파일을 운용 PC에 배포할때 정산 다운로드가 실행되고 있어서, 작업관리자로 들어가서
정산 다운로드 실행파일을 강제 종료하고 배포파일을 업데이트하고 있어. 이 문제를 해결해줘.' + CLAUDE.md '⛔output/·data/·config.json 삭제 금지':
  ① 실행 중(정산 프로그램 + 무인 앱 + 그 자식) → 멈추고 복사 · 무엇을 멈췄는지 표시 · 다시 띄우기 필요 표시
  ② output\ · data\ · config.json · proxies.txt 그대로(새 폴더에 있어도 안 덮음) · 설치 폴더에만 있는 파일 안 지움
  ③ 실행 중 아님 → 바로 복사(다시 띄울 것 없음)
  ④ 멈추기 실패(곧바로 다시 뜸 · 파일을 다른 프로그램이 쥠) → 복사 안 함 + 이유 표시(종료코드 2)
  ⑤ 새 폴더에 exe 없음(Defender) · 새 폴더 = 설치 폴더 → 아무것도 안 함
  ⑥ 배포 묶음: build.bat 이 두 파일을 zip 에 넣음 · ps1 = UTF-8 BOM(Windows PowerShell 한글) · bat = chcp 65001 · CRLF
가짜 프로세스 = 시스템 cmd.exe 를 임시 설치 폴더에 앱·정산 이름으로 복사해 ping 을 자식으로 띄움(실제 앱·계정·네트워크 없음).

    python tools/verify_deploy_update_offline.py
"""
from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except AttributeError:
    pass

ROOT = Path(__file__).resolve().parents[1]
PS1 = ROOT / "deploy" / "update.ps1"
BAT = ROOT / "deploy" / "업데이트.bat"
APP, SETTLE = "쿠팡애널리틱스.exe", "정산다운로드.exe"
CMD = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "cmd.exe"
NO_WIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FAILS: list[str] = []


def ok(cond: bool, msg: str) -> None:
    print(f"  {'✔' if cond else '✘'} {msg}")
    if not cond:
        FAILS.append(msg)


def make_fixture(base: Path) -> tuple[Path, Path]:
    """새 폴더(src)·설치 폴더(dst). 설치 폴더 exe = cmd.exe 사본(가짜 프로세스용) · 새 폴더 exe = 새 내용 글자."""
    src, dst = base / "new" / "coupang-analytics", base / "inst" / "coupang-analytics"
    files_src = {APP: "NEW-APP", SETTLE: "NEW-SETTLE", "_internal/a.txt": "new-a", "_internal/sub/b.txt": "new-b",
                 "install.ps1": "# new", "output/x.txt": "SHOULD-NOT-COPY", "data/y.txt": "SHOULD-NOT-COPY",
                 "config.json": '{"new": 1}', "proxies.txt": "new-proxy"}
    files_dst = {"_internal/a.txt": "old-a", "output/쿠팡데이타분석_통계.xlsx": "OLD-MASTER", "data/prof.txt": "OLD-PROFILE",
                 "config.json": '{"old": 1}', "proxies.txt": "old-proxy", "only_in_target.txt": "keep"}
    for root, files in ((src, files_src), (dst, files_dst)):
        for rel, text in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
    shutil.copy2(CMD, dst / APP)
    shutil.copy2(CMD, dst / SETTLE)
    return src, dst


def spawn_fake(exe: Path, tail: str = "") -> subprocess.Popen:
    """가짜 앱·정산 = cmd 사본이 ping(자식 = Chrome 역할)을 띄워 오래 기다림. tail = 명령줄 끝 표식(--auto 등)."""
    line = f'"{exe}" /c ping -n 300 127.0.0.1 >nul' + (f" & rem {tail}" if tail else "")
    return subprocess.Popen(line, creationflags=NO_WIN, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def children(pid: int) -> list[int]:
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          f"(Get-CimInstance Win32_Process -Filter 'ParentProcessId={pid}').ProcessId"],
                         capture_output=True, text=True, creationflags=NO_WIN).stdout
    return [int(x) for x in out.split() if x.strip().isdigit()]


def alive(pid: int) -> bool:
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(h)
    return code.value == 259                                          # STILL_ACTIVE


def kill_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, creationflags=NO_WIN)


def run_update(src: Path, dst: Path, *extra: str) -> tuple[int, str]:
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PS1),
                        "-Source", str(src), "-Target", str(dst), "-Yes", "-NoInstall", "-NoRestart",
                        "-StopWaitSec", "10", *extra],
                       capture_output=True, creationflags=NO_WIN, timeout=180)
    out = (r.stdout + r.stderr).decode("utf-8", "replace")
    if os.environ.get("VERIFY_SHOW"):
        print(out)
    return r.returncode, out


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else "(없음)"


def check_preserved(src: Path, dst: Path) -> None:
    ok(read(dst / "output" / "쿠팡데이타분석_통계.xlsx") == "OLD-MASTER", "② output\\ 마스터 그대로")
    ok(read(dst / "data" / "prof.txt") == "OLD-PROFILE", "② data\\ 프로필 그대로")
    ok(read(dst / "config.json") == '{"old": 1}', "② config.json 그대로(새 폴더 것으로 안 덮음)")
    ok(read(dst / "proxies.txt") == "old-proxy", "② proxies.txt 그대로")
    ok(not (dst / "output" / "x.txt").exists() and not (dst / "data" / "y.txt").exists(),
       "② 새 폴더의 output\\·data\\ 내용은 복사 안 함")
    ok(read(dst / "only_in_target.txt") == "keep", "② 설치 폴더에만 있는 파일 안 지움")


def case_running(base: Path) -> None:
    print("① 정산 프로그램 + 무인 앱 실행 중 → 멈추고 복사")
    src, dst = make_fixture(base / "c1")
    settle, app = spawn_fake(dst / SETTLE), spawn_fake(dst / APP, "--auto")
    time.sleep(1.5)
    kids = children(settle.pid) + children(app.pid)
    try:
        code, out = run_update(src, dst)
        ok(code == 0, f"종료코드 0 (실제 {code})")
        ok("[멈춤] 정산 프로그램 정산다운로드.exe" in out and "[멈춤] 앱(무인 실행) 쿠팡애널리틱스.exe" in out,
           "멈춘 것 표시(정산 프로그램·무인 앱)")
        ok(out.index("[멈춤] 정산 프로그램") < out.index("[멈춤] 앱(무인 실행)"), "정산 먼저 멈춤 → 앱")
        ok(settle.poll() is not None and app.poll() is not None, "가짜 정산·앱 프로세스 끝남")
        ok(bool(kids) and not any(alive(k) for k in kids), f"자식(Chrome 역할 ping {len(kids)}개)까지 트리째 끝남")
        ok(read(dst / APP) == "NEW-APP" and read(dst / SETTLE) == "NEW-SETTLE", "exe 새 버전으로 바뀜")
        ok(read(dst / "_internal" / "a.txt") == "new-a" and read(dst / "_internal" / "sub" / "b.txt") == "new-b",
           "_internal 덮어쓰기·새 하위 폴더 생성")
        ok("크기·exe 내용 대조 일치" in out, "복사 뒤 대조 표시")
        ok("[다시 띄우기] 필요(정산 프로그램을 멈춤 · 무인 실행 앱을 멈춤)" in out, "④ 다시 띄우기 필요 표시(정산·무인 앱)")
        check_preserved(src, dst)
    finally:
        for p in (settle, app):
            kill_tree(p.pid)


def case_idle(base: Path) -> None:
    print("③ 실행 중 아님 → 바로 복사")
    src, dst = make_fixture(base / "c3")
    code, out = run_update(src, dst)
    ok(code == 0, f"종료코드 0 (실제 {code})")
    ok("실행 중인 프로그램 없음" in out and "[멈춤]" not in out, "멈춘 것 없음 표시")
    ok(read(dst / APP) == "NEW-APP", "exe 새 버전으로 바뀜")
    ok("다시 띄울 것 없음" in out and "[다시 띄우기]" not in out, "다시 띄우기 안 함")
    check_preserved(src, dst)


RESPAWN = """
import subprocess, sys, time
exe, end = sys.argv[1], time.time() + 90
p = None
while time.time() < end:
    if p is None or p.poll() is not None:
        p = subprocess.Popen(f'"{exe}" /c ping -n 300 127.0.0.1 >nul', creationflags=0x08000000)
    time.sleep(0.1)
"""


def unchanged(dst: Path) -> bool:
    return (dst / APP).read_bytes() == CMD.read_bytes() and read(dst / "_internal" / "a.txt") == "old-a"


def case_respawn(base: Path) -> None:
    print("④ 멈춰도 곧바로 다시 뜸 → 복사 안 함 + 이유")
    src, dst = make_fixture(base / "c4")
    keeper = subprocess.Popen([sys.executable, "-c", RESPAWN, str(dst / SETTLE)], creationflags=NO_WIN)
    time.sleep(2.0)
    try:
        code, out = run_update(src, dst)
        ok(code == 2, f"종료코드 2 (실제 {code})")
        ok("[실패] 아직 실행 중" in out and "멈추지 못한 프로그램이 있어 복사하지 않았습니다" in out, "이유 표시")
        ok(unchanged(dst), "설치 폴더 그대로(exe·_internal 안 바뀜)")
    finally:
        kill_tree(keeper.pid)


def case_locked(base: Path) -> None:
    print("④ 덮어쓸 파일을 다른 프로그램이 쥠 → 복사 안 함 + 이유")
    src, dst = make_fixture(base / "c5")
    k32 = ctypes.windll.kernel32
    k32.CreateFileW.restype = ctypes.c_void_p
    h = k32.CreateFileW(str(dst / "_internal" / "a.txt"), 0x80000000, 0, None, 3, 0, None)   # 읽기 · 공유 없음
    try:
        ok(h not in (None, ctypes.c_void_p(-1).value), "시험 준비: 파일 배타 열기")
        code, out = run_update(src, dst)
        ok(code == 2, f"종료코드 2 (실제 {code})")
        ok("쥐고 있는 파일 1개" in out and "_internal\\a.txt" in out, "어느 파일인지 표시")
    finally:
        k32.CloseHandle(ctypes.c_void_p(h))
    ok(unchanged(dst), "설치 폴더 그대로(하나도 복사 안 함)")


def case_refuse(base: Path) -> None:
    print("⑤ 새 폴더에 exe 없음 · 새 폴더 = 설치 폴더 → 아무것도 안 함")
    src, dst = make_fixture(base / "c6")
    (src / SETTLE).unlink()
    code, out = run_update(src, dst)
    ok(code == 2 and "Defender" in out and "정산다운로드.exe" in out, f"exe 없음 → 종료코드 2·Defender 안내 (실제 {code})")
    ok(unchanged(dst), "설치 폴더 그대로")
    code, out = run_update(dst, dst)
    ok(code == 2 and "새 폴더와 설치 폴더가 같습니다" in out, f"같은 폴더 → 종료코드 2 (실제 {code})")


def case_package() -> None:
    print("⑥ 배포 묶음(build.bat·인코딩)")
    build = (ROOT / "build.bat").read_text(encoding="utf-8")
    ok('deploy\\update.ps1" "dist\\coupang-analytics\\"' in build, "build.bat: update.ps1 → 코드 폴더")
    ok('deploy\\업데이트.bat" "dist\\"' in build and 'deploy\\업데이트.bat" "dist\\coupang-analytics\\"' in build,
       "build.bat: 업데이트.bat → zip 루트·코드 폴더")
    ok("'dist\\업데이트.bat' -DestinationPath" in build, "build.bat: zip 에 업데이트.bat 포함")
    raw_ps1, raw_bat = PS1.read_bytes(), BAT.read_bytes()
    ok(raw_ps1.startswith(b"\xef\xbb\xbf"), "update.ps1 = UTF-8 BOM(Windows PowerShell 5.1 한글)")
    ok(b"chcp 65001" in raw_bat and not raw_bat.startswith(b"\xef\xbb\xbf"), "업데이트.bat = chcp 65001 · BOM 없음")
    ok(b"\n" not in raw_ps1.replace(b"\r\n", b"") and b"\n" not in raw_bat.replace(b"\r\n", b""), "두 파일 CRLF")


def main() -> int:
    if sys.platform != "win32":
        print("Windows 전용 시험 — 건너뜀")
        return 0
    case_package()
    with tempfile.TemporaryDirectory(prefix="deploy_update_") as tmp:
        base = Path(tmp)
        case_running(base)
        case_idle(base)
        case_respawn(base)
        case_locked(base)
        case_refuse(base)
    if FAILS:
        print(f"❌ 배포 업데이트 검증 실패 {len(FAILS)}건")
        return 1
    print("✅ 배포 업데이트 검증 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
