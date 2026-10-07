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
# playwright(node 드라이버) + 구글 API 클라이언트(디스커버리 문서·google_auth 등)를 통째로 포함한다.
# ⚠ googleapiclient 는 static_discovery=True 로 쓰므로 번들된 discovery_cache/documents(sheets.v4.json)가
#   반드시 포함돼야 런타임 네트워크 없이 동작한다 → collect_all 로 datas 확보.
for _pkg in ("playwright", "googleapiclient", "google_auth_httplib2"):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h
# google.oauth2 / google.auth 는 네임스페이스 패키지 → 서브모듈을 명시 수집(hidden import 누락 방지).
hiddenimports += collect_submodules("google.auth")
hiddenimports += collect_submodules("google.oauth2")
hiddenimports += collect_submodules("coupang_analytics")

_EXCLUDES = [
    "tkinter", "torch", "torchvision", "torchaudio", "scipy", "pandas",
    "matplotlib", "botocore", "boto3", "IPython", "notebook", "sympy",
]

# app_qt.py 는 ui/ 의 형제 모듈을 맨이름으로 import(registry_ui·registry_panel_qt·stock_panel_qt).
# → pathex 에 'ui' 를 넣어 PyInstaller 가 이 모듈들을 찾게 하고, hiddenimports 로도 명시(누락=런타임
#   ModuleNotFoundError). H_ui 가 정산/회사재고 UI 를 추가한 뒤 spec 미갱신으로 빠졌던 것(2026-09-29).
_ui_hidden = hiddenimports + ["registry_ui", "registry_panel_qt", "stock_panel_qt",
                              "settlement_status_panel_qt"]

# 메인 GUI 앱(콘솔 없음).
a = Analysis(
    ["ui/app_qt.py"],
    pathex=["src", "ui"],
    binaries=binaries,
    datas=datas,
    hiddenimports=_ui_hidden,
    # 기본 UI=PySide6 → tkinter 폴백 제외. 나머지는 이 앱이 안 쓰는데 환경에 깔려 딸려오던 거대
    # 패키지들(torch 370MB·scipy·pandas·botocore 등) — 제외해 배포 용량을 크게 줄인다.
    excludes=_EXCLUDES,
    noarchive=False,
)
# 라이브 진단(읽기전용·콘솔): 사무실 PC 에서 로그인→상품조회/수정(vid)+판매분석(지표)만 조회·출력하고
# 마스터/구글시트는 건드리지 않는다. vid 출처 변경·판매상태(productStatus) 실동작 검증용(앱 실행 전 안전 점검).
a_diag = Analysis(
    ["tools/verify_login_discover_live.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=_EXCLUDES,
    noarchive=False,
)
# 정산 파일 배치 다운로드(읽기·콘솔 없음): 운용 PC 에서 watch 무인 실행(정산다운로드.exe watch).
# 로그인 세션 same-origin fetch 로 WING 정산 파일을 받는다(정책=실제 Chrome). 앱(①판매수집)과 같은 계정 프로필
# 동시 사용은 계정 잠금으로 방지. 정산 입력=data\정산_계정목록.txt(비번 평문·zip 미동봉·운용 PC 에 소유자가 직접).
a_settle = Analysis(
    ["tools/settlement_download.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=_EXCLUDES,
    noarchive=False,
)
# 공유 의존성(playwright·google·PySide6 등) 중복 제거 — 진단·정산 exe 는 앱 폴더의 사본을 참조한다.
MERGE((a, "쿠팡애널리틱스", "쿠팡애널리틱스"), (a_diag, "쿠팡진단", "쿠팡진단"), (a_settle, "정산다운로드", "정산다운로드"))

pyz = PYZ(a.pure)
pyz_diag = PYZ(a_diag.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="쿠팡애널리틱스",
    console=False,                 # 더블클릭 실행 — 콘솔 창 없음
    disable_windowed_traceback=False,
)
exe_diag = EXE(
    pyz_diag,
    a_diag.scripts,
    [],
    exclude_binaries=True,
    name="쿠팡진단",
    console=True,                  # 진단 로그를 콘솔에 출력(읽기전용 점검용)
    disable_windowed_traceback=False,
)
pyz_settle = PYZ(a_settle.pure)
exe_settle = EXE(
    pyz_settle,
    a_settle.scripts,
    [],
    exclude_binaries=True,
    name="정산다운로드",
    console=False,                 # 무인 실행 — 콘솔창 없음(로그는 output\정산\로그\ 파일로). 깜빡임 함정 #8 회피.
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas,
               exe_diag, a_diag.binaries, a_diag.datas,
               exe_settle, a_settle.binaries, a_settle.datas,
               name="coupang-analytics")   # onedir 폴더명 = 개발(노트북 repo)과 동일(소유자 2026-09-21). exe 이름은 '쿠팡애널리틱스.exe' 유지.
