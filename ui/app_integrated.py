"""통합 앱(멀티플랫폼 커머스 관리) — 실행 셸. v3.3 사이드바(대분류 13) + 스택 페이지.

⚠ 기존 운영 앱(ui/app_qt.py)은 **건드리지 않는다**([[keep-existing-app-running-until-integrated]]). 이 셸은 별도 진입점으로,
현재까지 구현된 신규 도메인(05 문의/CS·11 계약·업무일지·12 채권자)을 **실제 작동 패널**로 보여주고, 나머지 대분류는
기존 앱에서 운영 중임을 안내한다. 저장은 **로컬 JSON**(LocalSheetClient·구글 자격증명 불필요) — 설치·실험용 즉시 실행.
나중에 통합이 진전되면 실제 GSheetClient 로 **인자만 교체**해 끼운다.

    python ui/app_integrated.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))              # 저장소 루트 — `python ui/app_integrated.py` 직접 실행 시 `import ui.*` 되게
sys.path.insert(0, str(_ROOT / "src"))      # coupang_analytics 패키지

from PySide6 import QtCore, QtWidgets  # noqa: E402

from coupang_analytics.apppaths import output_dir, set_workdir  # noqa: E402

from ui.contract_panel_qt import ContractPanel  # noqa: E402
from ui.creditor_panel_qt import CreditorPanel  # noqa: E402
from ui.cs_panel_qt import CSPanel  # noqa: E402
from ui.local_sheet_client import LocalSheetClient  # noqa: E402
from ui.worklog_panel_qt import WorklogPanel  # noqa: E402

APP_NAME = "커머스 판로 통합 관리"

# v3.3 대분류 13 (SSOT=designs/UI_SCREENS.md·DECISIONS 2026-10-05). 숫자 배지 없음·주문/배송 없음(샵마인).
MENU = ["01 상품", "02 가격", "03 재고", "04 정산", "05 문의·리뷰", "06 마케팅", "07 통계",
        "08 판매처", "09 셀독", "10 당근", "11 사업·계약", "12 채권자·상환", "13 설정"]

_QSS = """
* { font-family:'Segoe UI'; font-size:13px; color:#0f172a; }
QMainWindow, QWidget { background:#e3e9f1; }
QLabel, QRadioButton, QCheckBox { background:transparent; }
#header { background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #0f766e, stop:1 #14b8a6); }
#headerTitle { color:#ffffff; font-size:19px; font-weight:700; }
#headerSub { color:#d1f2ec; font-size:12px; }
QListWidget#nav { background:#0f766e; border:none; outline:none; padding:6px 0; }
QListWidget#nav::item { color:#d1f2ec; padding:11px 18px; border-radius:8px; margin:2px 8px; }
QListWidget#nav::item:hover { background:#115e59; }
QListWidget#nav::item:selected { background:#ffffff; color:#0f172a; font-weight:700; }
QGroupBox { background:#ffffff; border:1px solid #e5e9f0; border-radius:10px; margin-top:14px; padding:12px; }
QGroupBox::title { subcontrol-origin:margin; left:14px; padding:3px 12px; background:#ccfbf1;
    color:#0f766e; border-radius:7px; font-weight:700; }
QPushButton { background:#f1f5f9; border:1px solid #e2e8f0; border-radius:8px; padding:8px 14px; }
QPushButton:hover { background:#e7edf4; }
QPushButton#accent { background:#0d9488; border:1px solid #0d9488; color:#ffffff; font-weight:700; padding:9px 18px; }
QPushButton#accent:hover { background:#0f766e; }
QLineEdit, QComboBox { background:#ffffff; border:1px solid #cbd5e1; border-radius:8px; padding:6px 10px;
    selection-background-color:#0d9488; selection-color:#ffffff; }
QLineEdit:focus, QComboBox:focus { border:1px solid #0d9488; }
QComboBox QAbstractItemView { background:#ffffff; border:1px solid #e2e8f0;
    selection-background-color:#ccfbf1; selection-color:#0f172a; outline:none; }
QTableWidget { background:#ffffff; border:1px solid #e5e9f0; border-radius:10px; gridline-color:#eef2f7;
    selection-background-color:#ccfbf1; selection-color:#0f172a; outline:none; }
QHeaderView::section { background:#dbe3ee; color:#3f5069; border:none; border-right:1px solid #eef2f7;
    padding:8px 6px; font-weight:700; }
QTabBar::tab { background:transparent; color:#44546a; padding:9px 18px; margin:6px 3px 0 3px;
    border-top-left-radius:10px; border-top-right-radius:10px; }
QTabBar::tab:selected { background:#ffffff; color:#0f172a; font-weight:600; }
QTabWidget::pane { border:none; background:#e3e9f1; }
#card { background:#ffffff; border:1px solid #e5e9f0; border-radius:10px; }
"""


def _placeholder(title: str) -> QtWidgets.QWidget:
    w = QtWidgets.QWidget()
    lay = QtWidgets.QVBoxLayout(w)
    lay.addStretch(1)
    t = QtWidgets.QLabel(f"{title}")
    t.setStyleSheet("font-size:18px; font-weight:700; color:#0f766e;")
    msg = QtWidgets.QLabel("이 영역은 현재 기존 운영 앱(쿠팡 애널리틱스)에서 동작합니다.\n"
                           "통합 앱으로는 순차 이관 예정입니다 — 운영은 기존 앱에서 계속하세요.")
    msg.setStyleSheet("color:#64748b; font-size:14px;")
    for lbl in (t, msg):
        lbl.setAlignment(QtCore.Qt.AlignHCenter)
        lay.addWidget(lbl)
    lay.addStretch(2)
    return w


def _home() -> QtWidgets.QWidget:
    w = QtWidgets.QWidget()
    lay = QtWidgets.QVBoxLayout(w)
    lay.setContentsMargins(24, 24, 24, 24)
    title = QtWidgets.QLabel("커머스 판로 통합 관리 — 미리보기")
    title.setStyleSheet("font-size:20px; font-weight:800; color:#0f172a;")
    body = QtWidgets.QLabel(
        "지금 작동하는 영역(왼쪽 메뉴):\n"
        "  • 05 문의·리뷰 — 고객 문의 접수·상태·응대·통계\n"
        "  • 11 사업·계약 — 계약(버전 이력·만료)·업무일지\n"
        "  • 12 채권자·상환 — 채권 확정·상환·잔액(민감정보 가림)\n\n"
        "나머지 메뉴(상품·가격·재고·정산·마케팅·통계·판매처·셀독·당근·설정)는\n"
        "아직 기존 운영 앱에서 동작합니다. 통합은 순차 진행합니다.\n\n"
        "※ 저장소: 로컬 파일(구글 연동 없이 실험용). 데이터는 output/통합앱_data/ 아래에 쌓입니다.")
    body.setStyleSheet("color:#334155; font-size:14px;")
    lay.addWidget(title)
    lay.addSpacing(10)
    lay.addWidget(body)
    lay.addStretch(1)
    return w


class IntegratedApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1180, 760)
        self._data = output_dir() / "통합앱_data"
        self._pages: dict[str, QtWidgets.QWidget] = {}
        self._build()

    def _client(self, name: str) -> LocalSheetClient:
        return LocalSheetClient(self._data / f"{name}.json")

    def _page(self, label: str) -> QtWidgets.QWidget:
        if label == "05 문의·리뷰":
            return CSPanel(self._client("문의"))
        if label == "12 채권자·상환":
            return CreditorPanel(self._client("채권자"))
        if label == "11 사업·계약":
            tabs = QtWidgets.QTabWidget()
            tabs.addTab(ContractPanel(self._client("계약")), "계약")
            tabs.addTab(WorklogPanel(self._client("업무일지")), "업무일지")
            return tabs
        return _placeholder(label)

    def _build(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        outer = QtWidgets.QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._header())

        body = QtWidgets.QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.nav = QtWidgets.QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(190)
        self.nav.addItems(MENU)
        self.nav.currentRowChanged.connect(self._goto)
        body.addWidget(self.nav)

        self.stack = QtWidgets.QStackedWidget()
        self.stack.addWidget(_home())                       # index 0 = 홈
        for label in MENU:
            w = self._page(label)
            self._pages[label] = w
            self.stack.addWidget(w)
        wrap = QtWidgets.QWidget()
        wl = QtWidgets.QVBoxLayout(wrap)
        wl.setContentsMargins(16, 12, 16, 16)
        wl.addWidget(self.stack)
        body.addWidget(wrap, 1)
        outer.addLayout(body, 1)

    def _header(self) -> QtWidgets.QWidget:
        h = QtWidgets.QWidget()
        h.setObjectName("header")
        h.setFixedHeight(64)
        lay = QtWidgets.QHBoxLayout(h)
        lay.setContentsMargins(20, 0, 20, 0)
        title = QtWidgets.QLabel(APP_NAME)
        title.setObjectName("headerTitle")
        home_btn = QtWidgets.QPushButton("🏠 홈")
        home_btn.clicked.connect(lambda: (self.nav.clearSelection(), self.stack.setCurrentIndex(0)))
        lay.addWidget(title)
        lay.addStretch(1)
        sub = QtWidgets.QLabel("통합 미리보기 · 로컬 저장")
        sub.setObjectName("headerSub")
        lay.addWidget(sub)
        lay.addSpacing(12)
        lay.addWidget(home_btn)
        return h

    def _goto(self, row: int) -> None:
        if row >= 0:
            self.stack.setCurrentIndex(row + 1)             # +1: 0 은 홈


def main() -> int:
    set_workdir()
    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(_QSS)
    win = IntegratedApp()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
