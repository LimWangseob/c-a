# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 스펙 — 쿠팡 애널리틱스 GUI(.exe · 콘솔 없음 · onedir).

빌드: `build.bat` 더블클릭  (또는  python -m PyInstaller --noconfirm coupang_analytics.spec)
결과: dist\\쿠팡애널리틱스\\쿠팡애널리틱스.exe  — 이 '쿠팡애널리틱스' 폴더 전체를 다른 PC로 복사해 쓴다.

메모:
- 기본 UI = PySide6(app_qt.py). tkinter 폴백(app.py)은 제외해 용량을 줄인다.
- playwright 는 실제 Chrome 에 CDP 로 '연결'만 하지만(브라우저 다운로드 불필요) node 드라이버가
  필요하므로 collect_all 로 전부 포함한다. ⚠ 실행 PC 에는 **Google Chrome 설치가 필수**(정책=실제 Chrome).
- 산출물/프로필은 exe 폴더 기준(apppaths.set_workdir). exe 폴더는 쓰기 가능한 곳에 두어야 한다
  (예: 바탕화면·문서. Program Files 같은 보호 폴더 금지).
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []
for _pkg in ("playwright",):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h
hiddenimports += collect_submodules("coupang_analytics")

a = Analysis(
    ["ui/app_qt.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    # 기본 UI=PySide6 → tkinter 폴백 제외. 나머지는 이 앱이 안 쓰는데 환경에 깔려 딸려오던 거대
    # 패키지들(torch 370MB·scipy·pandas·botocore 등) — 제외해 배포 용량을 크게 줄인다.
    excludes=[
        "tkinter", "torch", "torchvision", "torchaudio", "scipy", "pandas",
        "matplotlib", "botocore", "boto3", "IPython", "notebook", "sympy",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="쿠팡애널리틱스",
    console=False,                 # 더블클릭 실행 — 콘솔 창 없음
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="쿠팡애널리틱스")
