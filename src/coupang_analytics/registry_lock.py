"""셀독등록원장 — 원장 쓰기 동시 실행 잠금. SSOT=designs/LEDGER_REGISTRY.md §10-1.

원장 쓰기(run_sync·run_backfill·write_coupang_check)는 셀독원장 시트 전체를 읽고→비교→덮어쓴다. 둘이 겹치면
나중 쓰기가 앞 쓰기를 덮는다(lost update: 쿠팡확인 소실·이력 번호 겹침). → **읽기부터 쓰기까지** 잠근다.

방식 = **OS 파일 잠금**(Windows msvcrt.locking / 그 외 fcntl.flock — 폴백이 아니라 플랫폼 분기). 프로세스가 죽으면
(크래시·재부팅·taskkill) OS 가 잠금을 자동으로 푼다 → '오래된 잠금 강제 해제' 같은 추측 로직이 없다.
잠금 파일은 남아 있어도 무해(파일 존재가 아니라 OS 잠금으로 판정).

한계: **같은 PC 안에서만** 보호(프로세스 1개 전제). 다른 PC 가 같은 원장 구글시트에 동시에 쓰는 것은 막지 못한다
(운용 원칙 = 운용PC 한 대·야간 순차). 재진입 금지: 잠금을 쥔 채 다른 원장 쓰기를 부르면 스스로 대기에 걸린다.
"""
from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

DEFAULT_LOCK_PATH = "output/_원장.lock"      # 상대경로 = 앱 set_workdir(data_root) 기준
LOCK_WAIT_SEC = 120.0                        # 다른 원장 쓰기가 끝나길 기다리는 최대 시간
_POLL_SEC = 0.5


class RegistryLockError(Exception):
    """다른 원장 쓰기가 진행 중이라 잠금을 얻지 못함(아무것도 쓰지 않음)."""


if sys.platform == "win32":
    import msvcrt

    def _try_lock(fd: int) -> bool:
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def registry_lock(path: str | Path = DEFAULT_LOCK_PATH, *, wait_sec: float | None = None, on_log=None):
    """원장 쓰기 잠금. wait_sec(None=모듈 상수 LOCK_WAIT_SEC) 안에 못 얻으면 RegistryLockError.
    with 블록을 벗어나면(예외 포함) 해제."""
    log = on_log or (lambda m: None)
    wait_sec = LOCK_WAIT_SEC if wait_sec is None else wait_sec
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        deadline = time.monotonic() + wait_sec
        waited = False
        while not _try_lock(fd):
            if time.monotonic() >= deadline:
                raise RegistryLockError(f"다른 원장 쓰기가 진행 중 — {wait_sec:.0f}초 기다려도 잠금({p})을 못 얻어 "
                                        "이번 원장 쓰기를 건너뜀(아무것도 안 씀)")
            if not waited:
                log(f"  [원장] 다른 원장 쓰기 진행 중 — 최대 {wait_sec:.0f}초 대기 ({p})")
                waited = True
            time.sleep(_POLL_SEC)
        try:
            yield
        finally:
            _unlock(fd)
    finally:
        os.close(fd)
