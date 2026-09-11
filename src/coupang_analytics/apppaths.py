"""실행 기준 폴더 · 작업 디렉터리 고정 (.exe 배포 대응).

이 앱은 `output/`·`data/`(크롬 프로필)·`capture/` 를 **상대경로**로 쓴다. 개발 실행(`python ui/app_qt.py`)은
repo 루트에서 도니 문제없지만, PyInstaller 로 묶은 **.exe 를 더블클릭**하면 작업 디렉터리(CWD)가 exe 폴더가
아닐 수 있어 산출물이 엉뚱한 곳에 생기거나 쓰기에 실패한다. 그래서 시작 시 CWD 를 기준 폴더로 고정한다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def base_dir() -> Path:
    """실행 기준 폴더 — frozen(.exe)=exe 가 있는 폴더, 개발=repo 루트."""
    if getattr(sys, "frozen", False):          # PyInstaller 로 묶인 실행파일
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]  # src/coupang_analytics/apppaths.py → repo 루트


def set_workdir() -> Path:
    """상대경로(output·data·capture)가 기준 폴더에서 해석되도록 CWD 를 고정. 기준 폴더 반환.

    엔트리(main)에서 **가장 먼저** 호출한다(reap_orphan_chrome·로그 경로가 상대경로를 쓰기 때문).
    """
    b = base_dir()
    try:
        os.chdir(b)
    except OSError:
        pass
    return b
