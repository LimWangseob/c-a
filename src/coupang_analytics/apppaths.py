"""실행 기준 폴더 · 작업 디렉터리 · 설정 파일 경로 (.exe 배포 대응).

**개발(노트북)·운용(PC) 폴더 구조를 동일**하게 둔다(소유자 2026-09-21). 한 폴더 안에 코드와 상태가 함께 있고,
상대경로(`output/`·`data/`·`config.json`)로 쓴다:

    <앱 폴더>/
      (코드: src·ui  또는  배포 exe·_internal)   ← **업데이트·재설치로 갈아끼워도 되는** 부분
      output/        ← 통계 마스터·로그·진행·스냅샷        ┐
      data/          ← 크롬 프로필(순위 warm 유지=차단 방지) ├ **삭제 금지(보존)** — 업데이트해도 그대로 둔다
      config.json    ← 설정(비밀 아님)                      ┘

경로는 상대경로라 실행 방식(개발=`python ui/app_qt.py`, 배포=exe 더블클릭)과 무관하게 이 폴더에서 해석되며,
`set_workdir()`가 시작 시 CWD 를 이 폴더로 고정한다. 배포/설치는 **폴더명도 동일**하게 쓰고, 업데이트 시 코드만
교체하고 output·data·config.json 은 지우지 않는다(설치 스크립트가 보존). 환경변수 `COUPANG_DATA_ROOT` 로
상태 폴더를 딴 곳으로 지정할 수도 있다(선택). 번들 리소스(QSS 등)는 base_dir 을 쓴다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

CONFIG_NAME = "config.json"   # 설정 파일 이름(앱 폴더에 위치·보존)


def base_dir() -> Path:
    """앱 폴더 — frozen(.exe)=exe 가 있는 폴더, 개발=repo 루트. 상태(output·data·config)도 여기 기준."""
    if getattr(sys, "frozen", False):          # PyInstaller 로 묶인 실행파일
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]  # src/coupang_analytics/apppaths.py → repo 루트


def data_root() -> Path:
    """상태(output·data·config)를 두는 폴더 = 앱 폴더(base_dir). 환경변수 `COUPANG_DATA_ROOT` 로 재지정 가능."""
    env = os.environ.get("COUPANG_DATA_ROOT", "").strip()
    return Path(env) if env else base_dir()


def config_path() -> Path:
    """설정 파일(config.json) 경로 = 앱 폴더/config.json (보존)."""
    return data_root() / CONFIG_NAME


def output_dir() -> Path:
    """산출물 폴더(마스터·진행·스냅샷·로그) = 앱 폴더/output. 없으면 만든다(보존 폴더)."""
    d = data_root() / "output"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def data_dir() -> Path:
    """크롬 프로필 등 = 앱 폴더/data. 없으면 만든다(보존 폴더)."""
    d = data_root() / "data"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def set_workdir() -> Path:
    """상대경로(output·data·capture)가 **앱 폴더** 에서 해석되도록 CWD 고정. 앱 폴더 반환.

    엔트리(main)에서 **가장 먼저** 호출(reap_orphan_chrome·로그가 상대경로를 쓰기 때문). 보존 폴더도 확보."""
    root = data_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
        (root / "output").mkdir(parents=True, exist_ok=True)
        (root / "data").mkdir(parents=True, exist_ok=True)
        os.chdir(root)
        return root
    except OSError:
        b = base_dir()
        try:
            os.chdir(b)
        except OSError:
            pass
        return b
