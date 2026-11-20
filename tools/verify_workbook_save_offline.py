"""마스터 엑셀 저장 = 끊겨도 옛 마스터가 남음(D-376) 오프라인 검증 — 로그인·구글 호출 없음.

기대값(통제 세션 지시서 · 실측 재현 `output\\_배포검증\\R245b_261120\\추가검증\\A_자동종료\\` B1·B2: 저장 중 taskkill 로
7,866,280B 마스터가 2.1MB·4.1MB 로 잘림 → BadZipFile):
- W1 저장 = 같은 폴더 임시 파일에 다 쓴 뒤 바꿔 끼움 · 끝나면 임시 파일 없음 · 마스터·스냅샷(같은 save) 모두
- W2 저장 도중 오류(쓰다 만 상태에서 예외) = 옛 마스터 그대로(열림·값 같음) · 임시 파일 지움 · 예외는 그대로 올림
- W3 강제 종료로 남은 임시 파일 = 다음 저장이 덮어씀(남지 않음) · 마스터 찾기·스냅샷 찾기·output 내보내기에 안 걸림
- W4 마스터가 다른 프로그램(엑셀)에 열려 있음 = 지금처럼 PermissionError(errno 13 · 파일 = 마스터 경로) · 임시 파일 지움 · 마스터 그대로
- W5 좀비 Chrome 정리 = data 폴더 '아래'만(data2·data_old 같은 앞부분만 같은 폴더 안 잡음) · 다른 앱 종료 수 = taskkill 성공만
실행: python tools/verify_workbook_save_offline.py
"""
from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

import openpyxl  # noqa: E402

from coupang_analytics import config  # noqa: E402
from coupang_analytics.workbook import OutputWorkbook  # noqa: E402

FAILS: list[str] = []


def check(ok: bool, msg: str) -> None:
    print(f"  {'✔' if ok else '✘'} {msg}")
    if not ok:
        FAILS.append(msg)


def wb_with(value: int) -> OutputWorkbook:
    wb = OutputWorkbook.empty()
    wb.ensure_account("가게A")
    wb.ensure_product_block("가게A", "상품A", "로켓그로스", ["kw"])
    wb.set_product_metric("가게A", "상품A", config.M_SALES, "11.20", value)
    return wb


def sales(path: Path):
    wb = OutputWorkbook.load(path)
    return wb.wb["가게A"].cell(wb._metric_row[("가게A", "상품A", config.M_SALES)], wb._date_col["가게A"]["11.20"]).value


def leftovers(d: Path) -> list[str]:
    return sorted(p.name for p in d.iterdir() if p.name.endswith(".tmp"))


def w1_atomic_ok():
    print("[W1] 정상 저장 = 임시 파일 → 바꿔 끼움 · 임시 파일 안 남음 · 스냅샷도 같은 방식")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        master, snap = out / "쿠팡데이타분석_통계.xlsx", out / "쿠팡데이타분석_통계_261120.xlsx"
        wb = wb_with(5)
        wb.save(master)
        wb.save(snap)
        check(zipfile.is_zipfile(master) and sales(master) == 5 and sales(snap) == 5, "마스터·스냅샷 열림 · 값 5")
        check(leftovers(out) == [], f"임시 파일 없음 {leftovers(out)}")
        seen = []
        orig = openpyxl.Workbook.save

        def spy(self, filename):
            seen.append(Path(filename))
            return orig(self, filename)
        openpyxl.Workbook.save = spy
        try:
            wb_with(6).save(master)
        finally:
            openpyxl.Workbook.save = orig
        check(seen and seen[0] != master and seen[0].parent == master.parent and seen[0].name.endswith(".tmp"),
              f"openpyxl 이 쓰는 곳 = 같은 폴더 임시 파일(마스터 아님) {seen}")
        check(sales(master) == 6, "바꿔 끼운 뒤 새 값 6")


def w2_crash_mid_save():
    print("[W2] 저장 도중 오류 = 옛 마스터 그대로 · 임시 파일 지움 · 예외 그대로")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        master = out / "쿠팡데이타분석_통계.xlsx"
        wb_with(5).save(master)
        size0 = master.stat().st_size
        orig = openpyxl.Workbook.save

        def half(self, filename):   # 쓰다 만 상태(앞부분만 써짐)에서 끊김 흉내
            with open(filename, "wb") as fh:
                fh.write(b"PK\x03\x04" + b"\x00" * 1000)
            raise MemoryError("저장 도중 끊김(시험)")
        openpyxl.Workbook.save = half
        raised = None
        try:
            wb_with(9).save(master)
        except MemoryError as exc:
            raised = exc
        finally:
            openpyxl.Workbook.save = orig
        check(raised is not None, "예외는 그대로 올림(조용히 삼키지 않음)")
        check(zipfile.is_zipfile(master) and master.stat().st_size == size0 and sales(master) == 5,
              f"옛 마스터 그대로(열림 · 크기 {master.stat().st_size} = {size0} · 값 5)")
        check(leftovers(out) == [], f"임시 파일 지움 {leftovers(out)}")


def w3_stale_tmp():
    print("[W3] 강제 종료로 남은 임시 파일 = 다음 저장이 덮어씀 · 마스터·스냅샷 찾기·내보내기에 안 걸림")
    from coupang_analytics import workbook
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        master = out / "쿠팡데이타분석_통계.xlsx"
        wb_with(5).save(master)
        tmp = workbook.save_tmp_path(master)
        tmp.write_bytes(b"PK\x03\x04 garbage")      # taskkill 로 끊긴 저장이 남긴 것
        snap_tmp = workbook.save_tmp_path(out / "쿠팡데이타분석_통계_261120.xlsx")
        snap_tmp.write_bytes(b"x")
        import re
        from coupang_analytics.settlement_statement_scope import SNAP
        check(not list(out.glob("쿠팡데이타분석_통계_*.xlsx")) and not SNAP.fullmatch(snap_tmp.name),
              f"스냅샷 찾기(쿠팡데이타분석_통계_*.xlsx · SNAP)에 안 걸림 {snap_tmp.name}")
        import output_export as OE
        check(OE.skip_file(tmp.name) and OE.skip_file(snap_tmp.name), "output 내보내기 = 임시 파일 건너뜀(skip_file)")
        check(re.fullmatch(r".+\.xlsx", tmp.name) is None, f"이름이 .xlsx 로 안 끝남(마스터·엑셀 목록 안 걸림) {tmp.name}")
        wb_with(7).save(master)
        check(sales(master) == 7 and not tmp.exists(), "다음 저장 = 남은 임시 파일 덮어써 바꿔 끼움(남지 않음)")


def w4_locked_master():
    print("[W4] 마스터가 엑셀에 열려 있음 = PermissionError(errno 13 · 마스터 경로) · 임시 파일 지움 · 마스터 그대로")
    if sys.platform != "win32":
        check(True, "Windows 아님 — 건너뜀")
        return
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        master = out / "쿠팡데이타분석_통계.xlsx"
        wb_with(5).save(master)
        from coupang_analytics import workbook
        workbook.REPLACE_WAIT_SEC = 1.0                                      # 시험: 다시 시도 시간 짧게
        h = k32.CreateFileW(str(master), 0x80000000, 0, None, 3, 0x80, None)   # 읽기 · 공유 0(엑셀이 연 것처럼 잠금)
        err = None
        try:
            wb_with(8).save(master)
        except PermissionError as exc:
            err = exc
        finally:
            k32.CloseHandle(h)
        check(err is not None and err.errno == 13 and Path(err.filename) == master,
              f"PermissionError errno 13 · 파일 = 마스터 {err!r}")
        check(leftovers(out) == [], f"임시 파일 지움 {leftovers(out)}")
        check(sales(master) == 5, "마스터 그대로(값 5)")
        import threading
        workbook.REPLACE_WAIT_SEC = 10.0
        fh = open(master, "rb")                                             # 다른 창이 마스터를 읽는 중(파이썬 열기 = 지우기 공유 없음)
        threading.Timer(1.5, fh.close).start()                              # 1.5초 뒤 읽기 끝
        wb_with(9).save(master)
        check(sales(master) == 9 and leftovers(out) == [], "다른 창이 잠깐 읽는 중 = 끝나길 기다렸다 바꿔 끼움(바로 쓰기 때처럼 저장 성공)")


def w5_reap_and_kill_count():
    print("[W5] 좀비 Chrome 정리 = data 폴더 아래만 · 다른 앱 종료 수 = taskkill 성공만")
    import subprocess
    from coupang_analytics import app_process, browser
    got = {}
    orig = subprocess.run

    def fake_run(cmd, **k):
        got["env"] = k.get("env", {})
        return subprocess.CompletedProcess(cmd, 0, "", "")
    browser.subprocess.run = fake_run
    try:
        browser.reap_orphan_chrome("data")
    finally:
        browser.subprocess.run = orig
    base = got["env"].get("SM_DATA", "")
    check(base.endswith("\\") and base.lower() == str(Path("data").resolve()).lower() + "\\",
          f"찾는 글자 = data 경로 + 구분자(data2·data_old 안 잡음) {base!r}")
    check("LASTEXITCODE" in app_process._KILL_PS and "-eq 0" in app_process._KILL_PS,
          "종료 수 = taskkill 종료코드 0 일 때만 셈")


def main() -> int:
    for t in (w1_atomic_ok, w2_crash_mid_save, w3_stale_tmp, w4_locked_master, w5_reap_and_kill_count):
        try:
            t()
        except Exception as exc:
            FAILS.append(f"{t.__name__}: {exc.__class__.__name__}: {exc}")
            print(f"  ✘ {t.__name__} 예외 {exc.__class__.__name__}: {exc}")
    print(f"\n결과: {'통과' if not FAILS else f'실패 {len(FAILS)}건'}")
    for f in FAILS:
        print("  ✘", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
