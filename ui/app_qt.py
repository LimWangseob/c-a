"""쿠팡 애널리틱스 데스크톱 UI — PySide6(Qt) + Windows 11 Fluent 스타일(QSS).

화면 계층만 Qt로 재작성. 수집/로그인/키워드/순위 등 **백엔드 로직은 기존 모듈 그대로 호출**한다.
(Tkinter 버전 `ui/app.py`는 폴백으로 보존.)
- 실제 Win11 룩: 둥근 모서리·플랫 카드·흰 카드/슬레이트 캔버스·**틸 악센트 통일**·슬레이트 콘솔 로그.
- 브라우저/수집 작업은 백그라운드 스레드에서 실행하고, 로그·완료는 시그널로 GUI 스레드에 전달.
"""
from __future__ import annotations

import html
import json
import sys
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6 import QtCore, QtWidgets

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from coupang_analytics import config, keyword_store  # noqa: E402
from coupang_analytics.apppaths import base_dir as app_base_dir, set_workdir  # noqa: E402
from coupang_analytics.browser import WingBrowser, find_chrome, reap_orphan_chrome  # noqa: E402
from coupang_analytics.credstore import CredStore  # noqa: E402
from coupang_analytics import gsheet_api, gsheet_index  # noqa: E402
from coupang_analytics.input_list import (parse_input_list, parse_input_rows,  # noqa: E402
                                           parse_password_file, parse_password_rows,
                                           read_ledger_rows)
from coupang_analytics.kw_ai import recommend_title  # noqa: E402
from coupang_analytics.kw_recommend import recommend, recommend_from_title  # noqa: E402
from coupang_analytics.kw_volume import NaverAdApi, NaverCredentials, parse_credentials_file  # noqa: E402
from coupang_analytics.pipeline import (_interruptible_sleep, master_exists,  # noqa: E402
                                        resumable_progress, run_full,
                                        select_keywords_stage, track_ranks_stage)
from coupang_analytics.rank import make_matcher, organic_rank, warmup  # noqa: E402

_PROFILE = "data/chrome-ui"

# ── Windows 11 Fluent 스타일시트 (둥근 모서리·플랫·악센트) ──────────────────
_QSS = """
* { font-family: 'Segoe UI'; font-size: 13px; color: #0f172a; }
QMainWindow, QWidget { background: #e3e9f1; }
QLabel, QRadioButton, QCheckBox { background: transparent; }

/* 헤더 배너 — 틸(teal) 그라데이션 */
#header { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0f766e, stop:1 #14b8a6); }
#headerTitle { color: #ffffff; font-size: 19px; font-weight: 700; }
#headerSub { color: #d1f2ec; font-size: 12px; }

/* 탭 = Win11 탐색기: 둥근 상단, 선택탭 흰색, 비선택 투명, 호버 연회색 */
QTabWidget::pane { border: none; background: #e3e9f1; top: -1px; }
QTabBar { background: #cdd8e6; qproperty-drawBase: 0; }
QTabBar::tab {
    background: transparent; color: #44546a; padding: 11px 24px; margin: 6px 3px 0 3px;
    border-top-left-radius: 10px; border-top-right-radius: 10px; min-width: 60px;
}
QTabBar::tab:hover { background: #bcc9db; }
QTabBar::tab:selected { background: #ffffff; color: #0f172a; font-weight: 600; }

/* 카드(구획) — 얇은 연한 테두리, 플랫 */
QGroupBox {
    background: #ffffff; border: 1px solid #e5e9f0; border-radius: 10px;
    margin-top: 14px; padding: 12px;
}
QGroupBox::title {
    subcontrol-origin: margin; left: 14px; padding: 3px 12px;
    background: #ccfbf1; color: #0f766e; border-radius: 7px; font-weight: 700; font-size: 13px;
}
QLabel#muted { color: #64748b; }

/* 버튼 — 플랫 둥근, 호버 연회색 */
QPushButton {
    background: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 8px;
    padding: 8px 14px; color: #0f172a;
}
QPushButton:hover { background: #e7edf4; }
QPushButton:pressed { background: #dbe3ec; }
QPushButton:disabled { color: #9aa7b6; background: #f3f5f8; }
/* 주요(악센트) 버튼 */
QPushButton#accent {
    background: #0d9488; border: 1px solid #0d9488; color: #ffffff; font-weight: 700; padding: 9px 18px;
}
QPushButton#accent:hover { background: #0f766e; }
QPushButton#accent:pressed { background: #115e59; }
QPushButton#accent:disabled { background: #9fd8d1; border-color: #9fd8d1; }

/* 입력창 — 둥근 테두리, 포커스 파랑 */
QLineEdit, QComboBox {
    background: #ffffff; border: 1px solid #cbd5e1; border-radius: 8px; padding: 6px 10px;
    selection-background-color: #0d9488; selection-color: #ffffff;
}
QLineEdit:focus, QComboBox:focus { border: 1px solid #0d9488; }
QLineEdit:disabled { background: #f3f5f8; color: #9aa7b6; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: #ffffff; border: 1px solid #e2e8f0; selection-background-color: #ccfbf1;
    selection-color: #0f172a; outline: none;
}

/* 목록(표) — Win11 리스트 */
QTableWidget {
    background: #ffffff; border: 1px solid #e5e9f0; border-radius: 10px; gridline-color: #eef2f7;
    selection-background-color: #ccfbf1; selection-color: #0f172a; outline: none;
}
QHeaderView::section {
    background: #dbe3ee; color: #3f5069; border: none; border-right: 1px solid #eef2f7;
    padding: 8px 6px; font-weight: 700;
}
QTableWidget::item { padding: 4px 6px; }

/* 라디오 — 선택 시 파란 원 + 굵은 파란 글씨로 뚜렷하게 */
QRadioButton { background: transparent; padding: 4px; spacing: 8px; }
QRadioButton::indicator { width: 16px; height: 16px; border-radius: 9px;
    border: 2px solid #64748b; background: #ffffff; }
QRadioButton::indicator:hover { border: 2px solid #0d9488; }
QRadioButton::indicator:checked { border: 5px solid #0d9488; background: #ffffff; }
QRadioButton:checked { color: #0d9488; font-weight: 700; }

/* 체크박스 — 네모, 선택 시 파란 채움 + 굵은 파란 글씨 */
QCheckBox { background: transparent; padding: 4px; spacing: 8px; }
QCheckBox::indicator { width: 17px; height: 17px; border-radius: 4px;
    border: 2px solid #64748b; background: #ffffff; }
QCheckBox::indicator:hover { border: 2px solid #0d9488; }
QCheckBox::indicator:checked { border: 2px solid #0d9488; background: #0d9488; }
QCheckBox:checked { color: #0d9488; font-weight: 700; }

/* 스크롤바 — Win11 얇은 스타일 */
QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: #cbd5e1; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #64748b; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:horizontal { background: #cbd5e1; border-radius: 5px; min-width: 30px; }

/* 로그 콘솔 — 밝은 슬레이트 */
#logConsole {
    background: #2b3a4a; color: #f1f5f9; border: none; border-radius: 10px;
    font-family: 'Consolas','D2Coding',monospace; font-size: 13px; padding: 8px;
}
#logTitle { font-weight: 700; color: #1e293b; }
"""

_LOG_COLORS = {"ok": "#4ade80", "err": "#f87171", "warn": "#fbbf24", "head": "#60a5fa", "": "#e2e8f0"}


def _prevent_sleep(on: bool) -> None:
    """무인 야간 실행 동안 Windows 절전/화면꺼짐 방지(SetThreadExecutionState). 실패해도 무해."""
    try:
        import ctypes
        ES_CONTINUOUS = 0x80000000
        ES_SYSTEM_REQUIRED = 0x00000001
        ES_DISPLAY_REQUIRED = 0x00000002
        flags = ES_CONTINUOUS | ((ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED) if on else 0)
        ctypes.windll.kernel32.SetThreadExecutionState(flags)
    except Exception:
        pass


class App(QtWidgets.QMainWindow):
    log_signal = QtCore.Signal(str)
    finish_signal = QtCore.Signal(object, object, object, object)   # (btn, on_done, result, err)

    def __init__(self, auto: bool = False):
        super().__init__()
        self.auto = auto            # 무인 자동 실행(--auto) 모드 — 팝업 없이 로그로, 06:00 자동 종료
        self.setWindowTitle("쿠팡 애널리틱스")
        self.input_list = None
        self.naver_creds = None
        self.ai_key = ""
        self.creds_store = CredStore()
        self.product_business: dict[str, str] = {}

        # 실시간 모니터링용 로그 파일 미러(GUI 콘솔과 동일 내용을 파일로도 기록).
        # 기준 폴더 기반(.exe 배포 시 _MEIPASS 임시폴더가 아닌 exe 폴더/output 에 남도록).
        _log_dir = app_base_dir() / "output"
        _log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = _log_dir / f"run_log_{datetime.now():%y%m%d_%H%M%S}.log"

        self.log_signal.connect(self._append_log)
        self.finish_signal.connect(self._on_finish)

        self._build_ui()
        self._load_saved_secrets()
        self._auto_load_input()     # 마지막 사용 입력 엑셀 자동 로드(무인 실행·재시작 후 즉시 실행 가능)
        scr = self.screen().availableGeometry()
        self.resize(min(1200, scr.width() - 80), min(1050, scr.height() - 80))

    # ── 레이아웃 ──────────────────────────────────────────────
    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._header())
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setMaximumHeight(360)   # 탭 영역은 컴팩트 → 아래 로그창이 화면 대부분 차지(2배↑)
        root.addWidget(self.tabs, 0)
        self.tabs.addTab(self._settings_tab(), "설정")
        self.tabs.addTab(self._kw_tab(), "키워드 추천")
        self.tabs.addTab(self._rank_tab(), "순위 조회")
        self.tabs.addTab(self._collect_tab(), "전체 실행")
        root.addWidget(self._log_panel(), 1)   # 로그가 남는 공간 전부

    def _header(self):
        head = QtWidgets.QFrame()
        head.setObjectName("header")
        lay = QtWidgets.QVBoxLayout(head)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(2)
        t = QtWidgets.QLabel("🛒  쿠팡 애널리틱스")
        t.setObjectName("headerTitle")
        s = QtWidgets.QLabel("계정별 상품 노출순위(PC·모바일)·판매지표 자동 수집 · AI 키워드 분석")
        s.setObjectName("headerSub")
        lay.addWidget(t)
        lay.addWidget(s)
        return head

    def _card(self, title):
        gb = QtWidgets.QGroupBox(title)
        return gb

    def _settings_tab(self):
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        inner = QtWidgets.QWidget()
        scroll.setWidget(inner)
        v = QtWidgets.QVBoxLayout(inner)
        v.setContentsMargins(14, 12, 14, 12)

        fk = self._card("파일 · API 키")
        grid = QtWidgets.QGridLayout(fk)
        self.input_lbl = QtWidgets.QLabel("(입력 분석용 엑셀 미선택)")
        self.naver_lbl = QtWidgets.QLabel("(네이버 API 키 미선택)")
        self.openai_lbl = QtWidgets.QLabel("(OpenAI 키 미설정 — 키워드 추출 불가)")
        rows = [
            ("입력 엑셀 열기", self.load_input, self.input_lbl),
            ("네이버 API 키 열기", self.load_naver, self.naver_lbl),
            ("OpenAI(ChatGPT) API 키 입력", self.load_openai, self.openai_lbl),
        ]
        for i, (text, cmd, lbl) in enumerate(rows):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(cmd)
            b.setMinimumWidth(210)
            grid.addWidget(b, i, 0)
            grid.addWidget(lbl, i, 1)
        grid.setColumnStretch(1, 1)
        v.addWidget(fk)
        v.addWidget(self._gsheet_card())   # 구글 시트 연동(입력 관리대장 · 출력 결과시트 · 서비스계정)
        # 키워드/순위 등 세부 설정값 입력란은 제거(사용자 미사용 · 영속 저장도 안 됨). 값은 config.py 에서 관리.
        v.addStretch(1)
        return scroll

    def _gsheet_card(self):
        """구글 시트 연동 카드 — 서비스계정 키 + 입력(관리대장)·출력(결과) 구글시트 링크 등록.

        입력은 PC 엑셀('입력 엑셀 열기')과 **병존**한다. 여기서 링크를 등록하면 서비스계정으로 직접 읽는다.
        결과 시트는 프로그램이 계정목록/통계를 쓴다(서비스계정을 '편집자'로 공유 필요). 설정 상세=docs/GSHEET_SETUP.md.
        """
        st = QtCore.QSettings("coupang-analytics", "ui")
        card = self._card("구글 시트 연동 (입력=관리대장 · 출력=결과시트)")
        g = QtWidgets.QGridLayout(card)
        g.setColumnStretch(1, 1)

        # 1) 서비스계정 키
        self.sa_lbl = QtWidgets.QLabel("(서비스계정 키 미등록 — 구글 시트 사용 불가)")
        sa_btn = QtWidgets.QPushButton("서비스계정 키(JSON) 등록")
        sa_btn.setMinimumWidth(210)
        sa_btn.clicked.connect(self.load_service_account)
        g.addWidget(sa_btn, 0, 0)
        g.addWidget(self.sa_lbl, 0, 1, 1, 2)

        # 2) 관리대장(입력) 링크
        self.gs_input_edit = QtWidgets.QLineEdit(st.value("gsheet/input_url", "", type=str))
        self.gs_input_edit.setPlaceholderText("「토탈셀러_셀독 관리 대장」 구글시트 링크 또는 ID — 비우면 PC 엑셀 사용")
        self.gs_input_edit.editingFinished.connect(
            lambda: st.setValue("gsheet/input_url", self.gs_input_edit.text().strip()))
        in_btns = QtWidgets.QHBoxLayout()
        in_chk = QtWidgets.QPushButton("연결 확인")
        in_chk.clicked.connect(lambda: self._check_gsheet("input"))
        in_load = QtWidgets.QPushButton("관리대장에서 불러오기")
        in_load.clicked.connect(self.load_input_from_gsheet)
        in_btns.addWidget(in_chk)
        in_btns.addWidget(in_load)
        g.addWidget(QtWidgets.QLabel("관리대장(입력) 링크"), 1, 0)
        g.addWidget(self.gs_input_edit, 1, 1)
        g.addLayout(in_btns, 1, 2)

        # 3) 결과(출력) 링크
        self.gs_output_edit = QtWidgets.QLineEdit(st.value("gsheet/output_url", "", type=str))
        self.gs_output_edit.setPlaceholderText("결과 구글시트 링크 또는 ID (계정목록·통계를 여기에 씀 — 서비스계정 '편집자' 공유)")
        self.gs_output_edit.editingFinished.connect(
            lambda: st.setValue("gsheet/output_url", self.gs_output_edit.text().strip()))
        out_chk = QtWidgets.QPushButton("연결 확인")
        out_chk.clicked.connect(lambda: self._check_gsheet("output"))
        g.addWidget(QtWidgets.QLabel("결과(출력) 링크"), 2, 0)
        g.addWidget(self.gs_output_edit, 2, 1)
        g.addWidget(out_chk, 2, 2)
        return card

    def _kw_tab(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(12, 10, 12, 10)
        bar = QtWidgets.QHBoxLayout()
        bar.addWidget(QtWidgets.QLabel("상품:"))
        self.kw_product = QtWidgets.QComboBox()
        self.kw_product.setMinimumWidth(360)
        bar.addWidget(self.kw_product)
        bar.addWidget(QtWidgets.QLabel("시드(선택·비우면 제목기반):"))
        self.seed_edit = QtWidgets.QLineEdit()
        self.seed_edit.setMaximumWidth(180)
        bar.addWidget(self.seed_edit)
        self.kw_run_btn = QtWidgets.QPushButton("추천 실행")
        self.kw_run_btn.setObjectName("accent")
        self.kw_run_btn.clicked.connect(self.do_recommend)
        bar.addWidget(self.kw_run_btn)
        bar.addStretch(1)
        v.addLayout(bar)

        cols = ["키워드", "검색량", "클릭수", "경쟁", "광고깊이", "로켓비율", "광고", "점수", "비고"]
        self.kw_table = QtWidgets.QTableWidget(0, len(cols))
        self.kw_table.setHorizontalHeaderLabels(cols)
        self.kw_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.kw_table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.kw_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.kw_table.verticalHeader().setVisible(False)
        self.kw_table.horizontalHeader().setStretchLastSection(True)
        self.kw_table.setColumnWidth(0, 220)
        v.addWidget(self.kw_table, 1)

        v.addWidget(QtWidgets.QLabel("상품 제목에서 다양한 키워드를 조사해 추천합니다. 3~5개 선택(Ctrl/Shift) 후 저장하세요."))
        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        self.title_btn = QtWidgets.QPushButton("상품명 추천(선택 키워드 기반)")
        self.title_btn.clicked.connect(self.do_recommend_title)
        btns.addWidget(self.title_btn)
        save_btn = QtWidgets.QPushButton("선택 키워드 저장(3~5개)")
        save_btn.clicked.connect(self.save_keywords)
        btns.addWidget(save_btn)
        v.addLayout(btns)
        return w

    def _rank_tab(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(12, 12, 12, 12)
        bar = QtWidgets.QHBoxLayout()
        bar.addWidget(QtWidgets.QLabel("키워드:"))
        self.rank_kw = QtWidgets.QLineEdit()
        self.rank_kw.setMaximumWidth(240)
        bar.addWidget(self.rank_kw)
        bar.addWidget(QtWidgets.QLabel("내 상품명 일부:"))
        self.rank_name = QtWidgets.QLineEdit()
        self.rank_name.setMaximumWidth(240)
        bar.addWidget(self.rank_name)
        self.rank_btn = QtWidgets.QPushButton("순위 조회")
        self.rank_btn.setObjectName("accent")
        self.rank_btn.clicked.connect(self.do_rank)
        bar.addWidget(self.rank_btn)
        bar.addStretch(1)
        v.addLayout(bar)
        v.addWidget(QtWidgets.QLabel(
            f"광고 제외 오가닉 순위를 조회합니다(상한 {config.RANK_SCAN_MAX}위, 밖이면 {config.RANK_SCAN_MAX}위). 로그인 불필요."))
        v.addStretch(1)
        return w

    def _collect_tab(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(12, 10, 12, 10)
        run = self._card("실행 — ①판매수집(로그인) → ②키워드 선정 → ③노출순위 조회 (②③은 로그인 불필요·순서무관)")
        rv = QtWidgets.QVBoxLayout(run)
        top = QtWidgets.QHBoxLayout()
        # 단계별 실행 — ① 로그인 판매수집(상품ID·지표·재고), ② 키워드 선정(순위 없음), ③ 노출순위 조회
        self.sales_btn = QtWidgets.QPushButton("① 판매수집")
        self.sales_btn.clicked.connect(lambda: self.do_run_full(keywords_off=True))
        top.addWidget(self.sales_btn)
        self.kw_btn = QtWidgets.QPushButton("② 키워드 선정")
        self.kw_btn.clicked.connect(self.do_select_keywords)
        top.addWidget(self.kw_btn)
        # ③ 순위(자동, 비로그인 검색)은 차단 위험이 커 현실성이 없어 제거(사용자 요청). 반자동만 유지.
        self.track_semi_btn = QtWidgets.QPushButton("③ 순위(반자동)")
        self.track_semi_btn.setToolTip(
            "창이 뜨면 로그에 안내되는 키워드를 그 창의 쿠팡 검색창에 직접 입력·검색하세요.\n"
            "앱이 결과 화면을 읽어 순위를 기록합니다(우리가 자동검색을 안 해 차단이 안 생깁니다).")
        self.track_semi_btn.clicked.connect(lambda: self.do_track_ranks(semi=True))
        top.addWidget(self.track_semi_btn)
        self.track_stop_btn = QtWidgets.QPushButton("반자동 중지")
        self.track_stop_btn.setEnabled(False)
        self.track_stop_btn.clicked.connect(self._stop_semi)
        top.addWidget(self.track_stop_btn)
        self.pipeline_btn = QtWidgets.QPushButton("전체 실행(①→②→③)")
        self.pipeline_btn.setObjectName("accent")
        self.pipeline_btn.clicked.connect(lambda: self.do_run_full(keywords_off=False))
        top.addWidget(self.pipeline_btn)
        top.addStretch(1)
        rv.addLayout(top)
        desc = QtWidgets.QLabel(
            "계정마다 [로그인→판매분석→키워드→PC·모바일 순위]를 완결하고 통합 엑셀에 누적 저장합니다. "
            "로그인은 창 없이 자동, 2차인증 필요할 때만 창이 뜹니다(로그로 예고). 진행상황은 아래 로그에서 확인.")
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        rv.addWidget(desc)
        # 실행 모드 — 팝업 3택 대신 화면에서 선택(이어쓰기=누적 / 처음부터=새 통계). 실행 시 예/아니오만 확인.
        moderow = QtWidgets.QHBoxLayout()
        moderow.addWidget(QtWidgets.QLabel("실행 모드:"))
        self.rb_append = QtWidgets.QRadioButton("이어쓰기(누적)")
        self.rb_append.setChecked(True)
        self.rb_append.setToolTip("기존 통계 마스터에 오늘 날짜 컬럼을 추가합니다(키워드 동결, 시계열 누적).\n"
                                  "같은 날 미완료분이 있으면 완료 계정을 건너뛰고 이어서 진행합니다.")
        self.rb_fresh = QtWidgets.QRadioButton("처음부터(새 통계)")
        self.rb_fresh.setToolTip("기존 통계 마스터를 백업한 뒤 빈 통계로 새로 시작합니다.\n"
                                 "⚠ 누적 시계열이 끊깁니다 — 첫 수집이나 키워드 전면 재선정 때만 사용하세요.")
        self._mode_group = QtWidgets.QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_group.addButton(self.rb_append)
        self._mode_group.addButton(self.rb_fresh)
        moderow.addWidget(self.rb_append)
        moderow.addWidget(self.rb_fresh)
        moderow.addStretch(1)
        rv.addLayout(moderow)
        optrow = QtWidgets.QHBoxLayout()
        self.cb_grow = QtWidgets.QCheckBox("새 키워드 발굴 추가 (통계 이어쓰기 시, 상한 7개·하루 2개)")
        self.cb_grow.setToolTip(
            "매일 실행은 첫날 정한 키워드를 그대로 유지합니다(통계 안정 — 시계열 비교가 가능).\n"
            "이 옵션을 켜면 기존 키워드는 그대로 두고, 상한(7개) 안에서 하루 최대 2개까지\n"
            "새 키워드를 발굴해 추가합니다(기존 키워드는 어떤 경우도 제거되지 않습니다).")
        optrow.addWidget(self.cb_grow)
        optrow.addStretch(1)
        rv.addLayout(optrow)
        v.addWidget(run)

        pbar = QtWidgets.QHBoxLayout()
        pbar.addWidget(QtWidgets.QLabel("수집 기간:"))
        self.cb_today = QtWidgets.QCheckBox("당일(=어제, 최신 확정일)")
        self.cb_today.setToolTip("쿠팡 판매분석은 당일 데이터를 익일 이후 생성합니다.\n"
                                 "따라서 '당일'은 데이터가 확정된 어제(D-1) 날짜로 수집합니다.")
        self.cb_today.setChecked(True)
        self.cb_range = QtWidgets.QCheckBox("기간")
        self._period_group = QtWidgets.QButtonGroup(self)   # 체크박스지만 하나만 선택(상호배타)
        self._period_group.setExclusive(True)
        self._period_group.addButton(self.cb_today)
        self._period_group.addButton(self.cb_range)
        self.cb_today.toggled.connect(self._toggle_range)
        pbar.addWidget(self.cb_today)
        pbar.addWidget(self.cb_range)
        yday = (date.today() - timedelta(days=1)).isoformat()   # 기본값도 확정일(어제)
        self.from_edit = QtWidgets.QLineEdit(yday)
        self.to_edit = QtWidgets.QLineEdit(yday)
        for e in (self.from_edit, self.to_edit):
            e.setMaximumWidth(120)
        pbar.addWidget(self.from_edit)
        pbar.addWidget(QtWidgets.QLabel("~"))
        pbar.addWidget(self.to_edit)
        hint = QtWidgets.QLabel("(기간: 판매분석=합계 · 노출순위=오늘)")
        hint.setObjectName("muted")
        pbar.addWidget(hint)
        pbar.addStretch(1)
        v.addLayout(pbar)
        v.addStretch(1)
        self._toggle_range()
        return w

    def _log_panel(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(10, 4, 10, 10)
        v.setSpacing(4)
        bar = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("진행 로그")
        title.setObjectName("logTitle")
        bar.addWidget(title)
        cp = QtWidgets.QPushButton("복사")
        cp.clicked.connect(self.copy_log)
        cl = QtWidgets.QPushButton("지우기")
        cl.clicked.connect(lambda: self.log_console.clear())
        bar.addWidget(cp)
        bar.addWidget(cl)
        bar.addStretch(1)
        v.addLayout(bar)
        self.log_console = QtWidgets.QTextEdit()
        self.log_console.setObjectName("logConsole")
        self.log_console.setReadOnly(True)
        # 24/365 상시가동 메모리 잠식 방지: 콘솔은 최근 N줄만 유지(오래된 줄 자동 폐기).
        # 전체 이력은 파일 미러(run_log_*.log)에 남으므로 화면 상한이 데이터 손실은 아니다.
        self.log_console.document().setMaximumBlockCount(config.UI_LOG_MAX_LINES)
        v.addWidget(self.log_console, 1)
        return w

    # ── 로그(스레드 안전) ─────────────────────────────────────
    @staticmethod
    def _log_tag(msg: str) -> str:
        if msg.startswith("==") or "====" in msg:
            return "head"
        if "오류" in msg or "실패" in msg or "차단" in msg or "[오류]" in msg:
            return "err"
        if "✅" in msg or "완료" in msg or "성공" in msg or "통과" in msg or "저장됨" in msg:
            return "ok"
        if "⚠" in msg or "경고" in msg or "미완료" in msg or "건너뜀" in msg or "데이터 없음" in msg:
            return "warn"
        return ""

    def log(self, msg: str):
        self.log_signal.emit(msg)   # 어느 스레드에서 불려도 GUI 스레드로 전달

    def _append_log(self, msg: str):
        color = _LOG_COLORS.get(self._log_tag(msg), "#e2e8f0")
        _now = datetime.now()   # [실행일자_시분초_1/60초] — 단계별 소요시간까지 보이게 프레임(00~59) 추가
        ts = f"{_now:%Y%m%d_%H%M%S}_{_now.microsecond * 60 // 1_000_000:02d}"
        stamp = html.escape(f"[{ts}] ")
        safe = html.escape(msg).replace(" ", "&nbsp;")
        self.log_console.append(
            f'<span style="color:#64748b">{stamp}</span>'
            f'<span style="color:{color}">{safe}</span>')
        sb = self.log_console.verticalScrollBar()
        sb.setValue(sb.maximum())
        self._rotate_log_if_big()   # 상시가동 시 로그 파일 무한 증가(디스크) 방지 — 상한 넘으면 .1 로 회전
        with open(self._log_path, "a", encoding="utf-8") as fh:  # 파일 미러(실시간 tail용)
            fh.write(f"[{ts}] {msg}\n")

    def _rotate_log_if_big(self) -> None:
        """로그 파일이 상한(config.UI_LOG_FILE_MAX_BYTES)을 넘으면 `.1` 로 회전(직전 1세대 보관).

        stat() 부담을 줄이려 수십 줄마다 한 번만 확인한다. 회전 실패는 로깅을 막지 않는다(무해).
        """
        self._log_writes = getattr(self, "_log_writes", 0) + 1
        if self._log_writes % 50:
            return
        try:
            if self._log_path.exists() and self._log_path.stat().st_size > config.UI_LOG_FILE_MAX_BYTES:
                self._log_path.replace(self._log_path.with_suffix(".log.1"))
        except OSError:
            pass

    def copy_log(self):
        QtWidgets.QApplication.clipboard().setText(self.log_console.toPlainText())
        self.log("[로그] 전체 복사됨 (클립보드)")

    # ── 백그라운드 실행(스레드 → 시그널로 완료 전달) ───────────
    def run_bg(self, task, on_done=None, btn=None):
        if btn:
            btn.setEnabled(False)

        def worker():
            result, err = None, None
            try:
                result = task()
            except Exception as exc:
                err = exc
            self.finish_signal.emit(btn, on_done, result, err)
        threading.Thread(target=worker, daemon=True).start()

    def _on_finish(self, btn, on_done, result, err):
        if btn:
            btn.setEnabled(True)
        if getattr(self, "track_stop_btn", None) is not None:   # 반자동 종료(성공/실패 공통) → 중지 버튼 끔
            self.track_stop_btn.setEnabled(False)
        if err is not None:
            self.log(f"[오류] {err.__class__.__name__}: {err}")
        elif on_done is not None:
            on_done(result)

    # ── 파일·키 로드 ──────────────────────────────────────────
    def _last_dir(self, key: str) -> str:
        """파일 대화상자 초기 폴더 = 직전에 그 용도로 연 폴더(QSettings 영속). 없으면 빈 문자열(기본 위치)."""
        return QtCore.QSettings("coupang-analytics", "ui").value(f"dir/{key}", "", type=str)

    def _remember_dir(self, key: str, path: str) -> None:
        """선택한 파일의 폴더를 그 용도의 '직전 폴더'로 저장 → 다음엔 그 폴더에서 열림."""
        QtCore.QSettings("coupang-analytics", "ui").setValue(f"dir/{key}", str(Path(path).parent))

    def load_input(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "입력 분석용 엑셀", self._last_dir("input"), "Excel (*.xlsx)")
        if not path:
            return
        self._remember_dir("input", path)
        self._apply_input(path, label=Path(path).name)
        QtCore.QSettings("coupang-analytics", "ui").setValue("file/input", str(path))   # 무인 자동로드용

    def _set_input_list(self, il, label: str) -> None:
        """파싱된 InputList 를 UI 상태(상품목록·라벨·로그)에 반영. 파일/구글시트 공용."""
        self.input_list = il
        self.product_business.clear()
        products = []
        for a in il.accounts:
            for p in a.products:
                products.append(p.name)
                self.product_business[p.name] = a.business_name
        self.kw_product.clear()
        self.kw_product.addItems(products)
        self.input_lbl.setText(f"{label}  (계정 {len(il.accounts)}, 상품 {len(products)})")
        self.log(f"[입력] {len(il.accounts)}계정 · 상품 {len(products)}개 로드 · 오류 {len(il.errors)}건")
        for e in il.errors[:5]:
            self.log(f"   - 입력오류: {e}")
        for s in il.struck[:8]:                     # 제외(상태=판매중지/삭제·취소선) 알림
            self.log(f"   · 제외: {s}")
        self._merge_output_marketing(il)            # 출력 계정목록의 직원 입력 마케팅 반영(권위 출처)

    def _merge_output_marketing(self, il) -> None:
        """출력 결과 구글시트 `계정목록`의 직원 입력 마케팅(D~F)을 입력 상품 모델에 병합.

        마케팅 권위 출처 = **출력 계정목록**(관리대장 아님). 출력 링크/서비스계정 미설정이면 조용히 건너뛴다
        (첫 실행엔 계정목록이 없을 수 있음 — 정상). 실패해도 입력 로드를 막지 않는다(로그만).
        """
        url = QtCore.QSettings("coupang-analytics", "ui").value("gsheet/output_url", "", type=str).strip()
        if not url:
            return
        try:
            if not gsheet_api.service_account_email(self.creds_store):
                return                              # 서비스계정 미등록 → 구글 기능 비활성(조용히)
            client = gsheet_api.GSheetClient(url, store=self.creds_store)
            merged = gsheet_index.apply_marketing(il.accounts, gsheet_index.read_marketing(client))
            if merged:
                self.log(f"[마케팅] 출력 계정목록에서 {merged}개 상품 마케팅 기간 반영(직원 입력 우선)")
        except gsheet_api.GSheetError as exc:
            self.log(f"[마케팅] 출력 계정목록 마케팅 읽기 건너뜀: {exc}")

    def _apply_input(self, path, label: str | None = None) -> bool:
        """PC 입력 엑셀 파싱·상품목록·비번 저장(수동/무인 공용). 영속은 호출부가 담당."""
        il = parse_input_list(path)
        self._set_input_list(il, label or Path(path).name)
        self._store_passwords_from(path, quiet=True)
        return True

    def load_input_from_gsheet(self):
        """설정 탭에 등록한 관리대장(구글시트) 링크를 서비스계정으로 읽어 입력으로 적용(수동 버튼).

        rows 를 한 번 읽어 상품 파싱 + 비번 추출 둘 다 처리(API 호출 최소화). 비번은 즉시 DPAPI 저장.
        """
        url = self.gs_input_edit.text().strip()
        if not url:
            QtWidgets.QMessageBox.information(self, "링크 필요", "관리대장(입력) 구글시트 링크를 먼저 등록하세요.")
            return
        self.log("[입력] 관리대장(구글시트) 읽는 중…")
        try:
            self._apply_input_gsheet(url)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "관리대장 읽기 실패", str(exc))
            self.log(f"[입력] 구글시트 읽기 실패({exc.__class__.__name__}): {exc}")

    def _apply_input_gsheet(self, url: str) -> bool:
        """관리대장 구글시트 → InputList 적용 + 비번 DPAPI 저장(수동/무인 공용). 실패는 예외로 올림."""
        title, rows = read_ledger_rows(url, store=self.creds_store)
        il = parse_input_rows(rows)
        self._set_input_list(il, f"[구글시트] {title}")
        self._store_passwords_map(parse_password_rows(rows), quiet=True)
        st = QtCore.QSettings("coupang-analytics", "ui")
        st.setValue("gsheet/input_url", url)
        st.setValue("input/source", "gsheet")       # 무인 자동로드가 구글시트를 우선하도록 표시
        return True

    def _auto_load_input(self) -> bool:
        """입력 자동 로드(무인 실행·재시작 후): 소스=gsheet면 등록 링크에서, 아니면 마지막 PC 엑셀에서."""
        st = QtCore.QSettings("coupang-analytics", "ui")
        url = st.value("gsheet/input_url", "", type=str)
        if st.value("input/source", "", type=str) == "gsheet" and url:
            try:
                return self._apply_input_gsheet(url)
            except Exception as exc:
                self.log(f"[입력] 구글시트 자동 로드 실패({exc.__class__.__name__}): {exc} — PC 엑셀로 폴백 시도")
        path = st.value("file/input", "", type=str)
        if not (path and Path(path).exists()):
            return False
        try:
            return self._apply_input(path)
        except Exception as exc:
            self.log(f"[입력] 자동 로드 실패({exc.__class__.__name__}): {exc}")
            return False

    def _store_passwords_from(self, path, quiet=False) -> int:
        try:
            pw_map = parse_password_file(path)
        except Exception as exc:
            if not quiet:
                QtWidgets.QMessageBox.warning(self, "비밀번호 파일 오류", str(exc))
            return 0
        return self._store_passwords_map(pw_map, quiet=quiet)

    def _store_passwords_map(self, pw_map: dict, quiet=False) -> int:
        """{계정아이디: 비밀번호} 를 DPAPI(이 PC 전용)로 저장. 관리대장(파일/구글시트) 공용.

        비번은 관리대장(입력)에서만 오며 결과 구글시트엔 저장하지 않는다(출력물 평문 금지).
        """
        saved = 0
        for aid, pw in pw_map.items():
            try:
                self.creds_store.set_password(aid, pw)
                saved += 1
            except Exception as exc:
                self.log(f"[비번] {aid} 저장 실패: {exc.__class__.__name__}")
        if saved:
            self.log(f"[비번] {saved}개 계정 비밀번호 저장됨 (이 PC 전용 암호화, 공유·git 안 됨). 순차 로그인 시 자동입력.")
        elif not quiet:
            self.log("[비번] 비밀번호를 찾지 못했습니다 (계정아이디/비밀번호 컬럼 확인).")
        return saved

    def _account_pw(self, account_id):
        try:
            return self.creds_store.get_password(account_id) or None
        except Exception:
            return None

    def load_naver(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "네이버 검색광고 API 키 파일", self._last_dir("naver"), "Text (*.txt);;All (*.*)")
        if not path:
            return
        self._remember_dir("naver", path)
        c = self.naver_creds = parse_credentials_file(path)
        self.naver_lbl.setText(f"{Path(path).name}  (고객 {c.customer_id})")
        try:
            self.creds_store.set_password("__naver__", json.dumps(
                {"customer_id": c.customer_id, "api_key": c.api_key, "secret_key": c.secret_key}))
            self.log("[네이버] API 키 로드·저장됨 (다음 실행부터 자동)")
        except Exception as exc:
            self.log(f"[네이버] 로드됨(저장 실패: {exc.__class__.__name__})")

    def load_openai(self):
        key, ok = QtWidgets.QInputDialog.getText(
            self, "OpenAI API 키", "sk-... 키를 입력하세요", QtWidgets.QLineEdit.Password)
        if not (ok and key):
            return
        self.ai_key = key.strip()
        self.openai_lbl.setText("(OpenAI 키: 입력됨 — 저장됨)")
        try:
            self.creds_store.set_password("__openai__", self.ai_key)
            self.log("[OpenAI] API 키 입력·저장됨 (다음 실행부터 자동)")
        except Exception as exc:
            self.log(f"[OpenAI] 입력됨(저장 실패: {exc.__class__.__name__})")

    def load_service_account(self):
        """서비스계정 JSON 키 파일을 선택 → 검증 후 DPAPI 저장(이 PC 전용). 이메일 표시.

        원본 JSON 은 앱이 별도로 남기지 않는다(credstore 암호화만). 대상 시트를 이 이메일에 공유해야 접근 가능.
        """
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "서비스계정 키 (JSON)", self._last_dir("sa"), "JSON (*.json);;All (*.*)")
        if not path:
            return
        self._remember_dir("sa", path)
        try:
            raw = Path(path).read_text(encoding="utf-8")
            email = gsheet_api.store_sa_json(raw, self.creds_store)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "서비스계정 키 오류", str(exc))
            self.log(f"[구글] 서비스계정 키 등록 실패: {exc}")
            return
        self.sa_lbl.setText(f"서비스계정: {email}  (이 주소에 시트를 공유하세요)")
        self.log(f"[구글] 서비스계정 키 등록·저장됨 — {email}")

    def _check_gsheet(self, kind: str):
        """등록한 구글시트 링크로 실제 접속해 제목·시트목록을 확인(권한/공유 상태 즉시 진단)."""
        edit = self.gs_input_edit if kind == "input" else self.gs_output_edit
        who = "관리대장(입력)" if kind == "input" else "결과(출력)"
        url = edit.text().strip()
        if not url:
            QtWidgets.QMessageBox.information(self, "링크 필요", f"{who} 구글시트 링크를 먼저 입력하세요.")
            return
        # 편집 중 값도 즉시 저장(editingFinished 미발생 상태 대비)
        QtCore.QSettings("coupang-analytics", "ui").setValue(f"gsheet/{kind}_url", url)
        try:
            title, sheets = gsheet_api.check_access(url, store=self.creds_store)
        except gsheet_api.GSheetError as exc:
            QtWidgets.QMessageBox.warning(self, "연결 실패", str(exc))
            self.log(f"[구글] {who} 연결 실패: {exc}")
            return
        preview = ", ".join(sheets[:8]) + (" …" if len(sheets) > 8 else "")
        QtWidgets.QMessageBox.information(
            self, "연결 성공", f"'{title}'\n시트 {len(sheets)}개: {preview}")
        self.log(f"[구글] {who} 연결 확인 OK — '{title}' (시트 {len(sheets)}개)")

    def _load_saved_secrets(self):
        try:
            email = gsheet_api.service_account_email(self.creds_store)
        except Exception as exc:
            email = None
            self.log(f"[구글] 저장된 서비스계정 키 확인 실패: {exc}")
        if email:
            self.sa_lbl.setText(f"서비스계정: {email}  (저장됨 — 자동 로드)")
            self.log(f"[구글] 저장된 서비스계정 키 자동 로드됨 — {email}")
        try:
            nj = self.creds_store.get_password("__naver__")
        except Exception:
            nj = None
        if nj:
            d = json.loads(nj)
            self.naver_creds = NaverCredentials(d["customer_id"], d["api_key"], d["secret_key"])
            self.naver_lbl.setText(f"저장된 네이버 키 (고객 {d['customer_id']})")
            self.log("[네이버] 저장된 키 자동 로드됨")
        try:
            ak = self.creds_store.get_password("__openai__")
        except Exception:
            ak = None
        if ak:
            self.ai_key = ak
            self.openai_lbl.setText("(OpenAI 키: 저장됨 — 자동 로드)")
            self.log("[OpenAI] 저장된 키 자동 로드됨")

    # ── 키워드 추천 ───────────────────────────────────────────
    def do_recommend(self):
        if self.naver_creds is None:
            QtWidgets.QMessageBox.warning(self, "키 필요", "네이버 API 키를 먼저 불러오세요.")
            return
        seed = self.seed_edit.text().strip()
        product = self.kw_product.currentText().strip()
        if not seed and not product:
            QtWidgets.QMessageBox.warning(self, "입력 필요", "상품을 선택하거나 시드 키워드를 입력하세요.")
            return
        if not seed and not self.ai_key:
            QtWidgets.QMessageBox.warning(self, "키 필요", "상품제목 기반 추천은 OpenAI(ChatGPT) API 키가 필요합니다.")
            return
        self.kw_table.setRowCount(0)
        self.log(f"[키워드] {'시드' if seed else '상품제목'} '{(seed or product)[:30]}' 기반 추천"
                 f"{'' if seed else ' (AI 앵커+판정)'} — 조사 → 쿠팡 경쟁(수십초)")
        key = self.ai_key

        def task():
            api = NaverAdApi(self.naver_creds)
            with WingBrowser(profile_dir=_PROFILE, offscreen=True) as wb:
                if seed:
                    return recommend(seed, api, wb)
                return recommend_from_title(product, api, wb, ai_key=key)
        self.run_bg(task, on_done=self._fill_kw, btn=self.kw_run_btn)

    def _fill_kw(self, recs):
        self.kw_table.setRowCount(len(recs))
        for row, r in enumerate(recs):
            vals = [r.keyword, r.volume, f"{r.clicks:.0f}", r.comp_idx, r.ad_depth,
                    f"{r.rocket_ratio:.2f}", r.ad_count, f"{r.score:.2f}", r.note]
            for col, val in enumerate(vals):
                item = QtWidgets.QTableWidgetItem(str(val))
                if col != 0:
                    item.setTextAlignment(QtCore.Qt.AlignCenter)
                self.kw_table.setItem(row, col, item)
        self.log(f"[키워드] 추천 {len(recs)}개 표시. 3~5개 선택 후 저장하세요.")

    def _selected_keywords(self):
        rows = sorted({idx.row() for idx in self.kw_table.selectedIndexes()})
        return [self.kw_table.item(r, 0).text() for r in rows if self.kw_table.item(r, 0)]

    def do_recommend_title(self):
        if not self.ai_key:
            QtWidgets.QMessageBox.warning(self, "키 필요", "상품명 추천은 OpenAI(ChatGPT) API 키가 필요합니다.")
            return
        product = self.kw_product.currentText().strip()
        if not product:
            QtWidgets.QMessageBox.warning(self, "입력 필요", "상품을 먼저 선택하세요.")
            return
        kws = self._selected_keywords()
        if not kws:   # 선택 없으면 상위 전체
            kws = [self.kw_table.item(r, 0).text() for r in range(self.kw_table.rowCount())]
        kws = kws[:8]
        if not kws:
            QtWidgets.QMessageBox.warning(self, "키워드 필요", "먼저 '추천 실행'으로 키워드를 조사하세요.")
            return
        brand = self.product_business.get(product, "")
        key = self.ai_key
        self.log(f"[상품명] '{product[:24]}' + 키워드 {kws} → 추천 생성 중…")
        self.run_bg(lambda: recommend_title(product, kws, brand=brand, api_key=key),
                    on_done=self._show_title, btn=self.title_btn)

    def _show_title(self, title):
        self.log(f"[상품명] 추천 → {title}")
        QtWidgets.QApplication.clipboard().setText(title)
        QtWidgets.QMessageBox.information(self, "상품명 추천", f"제안 상품명(클립보드 복사됨):\n\n{title}")

    def save_keywords(self):
        kws = self._selected_keywords()
        if not (3 <= len(kws) <= 5):
            QtWidgets.QMessageBox.warning(self, "선택 개수", "3~5개를 선택하세요.")
            return
        product = self.kw_product.currentText().strip()
        if not product:
            QtWidgets.QMessageBox.warning(self, "상품 필요", "상품을 먼저 선택하세요.")
            return
        business = self.product_business.get(product, "")
        keyword_store.save(business, product, kws)
        self.log(f"[저장] [{business}] {product} ← {kws}")
        QtWidgets.QMessageBox.information(self, "저장 완료", f"{len(kws)}개 키워드를 저장했습니다.")

    # ── 순위 조회 ─────────────────────────────────────────────
    def do_rank(self):
        kw = self.rank_kw.text().strip()
        name = self.rank_name.text().strip()
        if not kw or not name:
            QtWidgets.QMessageBox.warning(self, "입력 필요", "키워드와 상품명 일부를 입력하세요.")
            return
        self.log(f"[순위] '{kw}' 에서 '{name}' 오가닉 순위 조회 중…")

        def task():
            with WingBrowser(profile_dir=_PROFILE, offscreen=True) as wb:
                warmup(wb)
                return organic_rank(wb, kw, make_matcher(name_substr=name))
        self.run_bg(task, on_done=lambda r: self.log(
            f"[순위] 결과: {('오가닉 ' + str(r) + '위') if r else (str(config.RANK_SCAN_MAX) + '위 밖 → ' + str(config.RANK_SCAN_MAX) + '위')}"),
            btn=self.rank_btn)

    # ── 전체 실행 ─────────────────────────────────────────────
    def _toggle_range(self):
        on = self.cb_range.isChecked()
        self.from_edit.setEnabled(on)
        self.to_edit.setEnabled(on)

    def _run_dates(self):
        if self.cb_today.isChecked():
            # 쿠팡 판매분석은 당일 데이터를 익일 이후 생성 → '당일'은 데이터가 확정된 어제(D-1) 기준.
            d = (date.today() - timedelta(days=1)).isoformat()
            return d, d
        return self.from_edit.text().strip(), self.to_edit.text().strip()

    def do_run_full(self, keywords_off: bool = False):
        if self.input_list is None:
            QtWidgets.QMessageBox.warning(self, "입력 필요", "설정 탭에서 입력 엑셀을 먼저 여세요.")
            return
        if self.naver_creds is None:
            QtWidgets.QMessageBox.warning(self, "키 필요", "설정 탭에서 네이버 API 키를 먼저 여세요.")
            return
        if not self.ai_key:
            QtWidgets.QMessageBox.warning(self, "키 필요", "키워드 추출에 OpenAI(ChatGPT) API 키가 필요합니다.")
            return
        df, dt = self._run_dates()
        # 날짜를 직접 지정(어제 자동이 아님)하면 순위 조회 제외 = 그 날짜 판매데이터만 채움(차단 회피)
        skip_ranks = not self.cb_today.isChecked()
        n = sum(len(a.products) for a in self.input_list.accounts)
        title = "① 판매수집" if keywords_off else "전체 실행"
        # 실행 모드는 화면 라디오로 선택(팝업 3택 제거) → 여기선 예/아니오만 확인.
        #  · 처음부터(새 통계): carry_forward=False → 기존 마스터 백업 후 새로 시작.
        #  · 이어쓰기: 같은 날 미완료분이 있으면 이어서(완료 계정 건너뜀), 아니면 마스터에 오늘 컬럼 추가.
        #    (resumable_progress 는 '오늘 시작분'만 반환 → 날짜가 바뀌면 자동으로 새 오늘 컬럼.)
        fresh = self.rb_fresh.isChecked()
        resume = carry = False
        meta = None if fresh else resumable_progress()
        if fresh:
            mode_desc = "처음부터(새 통계) — ⚠ 기존 통계 마스터는 백업 후 새로 시작(누적 시계열 끊김)"
        elif meta:
            resume = True
            carry = bool(meta.get("carry", False))
            df, dt = meta["date_from"], meta["date_to"]
            mode_desc = f"이어쓰기 — 같은 날 미완료분 이어서(완료 {len(meta['done'])}개 건너뜀), 기간 {df}~{dt}"
        elif master_exists():
            carry = True
            mode_desc = f"이어쓰기 — 오늘({dt}) 컬럼 추가(키워드 동결)"
        else:
            mode_desc = f"새 통계 시작(첫 실행 — 마스터 없음), 기간 {df}~{dt}"
        grow = carry and self.cb_grow.isChecked()   # 발굴 추가는 통계 이어쓰기 때만 의미
        # 단일 확인 팝업 — 실행 여부(예/아니오)만.
        confirm = (f"{mode_desc}\n대상: 상품 {n}개"
                   f"{' · 새 키워드 발굴 추가' if grow else ''}\n\n실행할까요?")
        if QtWidgets.QMessageBox.question(self, f"{title} 확인", confirm) != QtWidgets.QMessageBox.Yes:
            self.log(f"[{title}] 취소됨")
            return
        input_list, naver_creds, key = self.input_list, self.naver_creds, self.ai_key
        mode_txt = "이어서 " if resume else ("통계이어쓰기 " if carry else "새통계 ")
        stage_txt = " · ①판매수집(키워드·순위 없음)" if keywords_off else \
            (" · 순위 제외(판매데이터만)" if skip_ranks and not resume else "")
        self.log(f"[{'판매수집' if keywords_off else '전체실행'}] {mode_txt}시작 — 상품 {n}개, 기간 {df}~{dt}"
                 f"{' · 새 키워드 발굴 추가' if grow else ''}{stage_txt}")
        btn = self.sales_btn if keywords_off else self.pipeline_btn

        def task():
            naver = NaverAdApi(naver_creds)
            return run_full(input_list, naver, ai_key=key, date_from=df, date_to=dt,
                            get_password=self._account_pw, resume=resume, carry_forward=carry,
                            grow_keywords=grow, skip_ranks=skip_ranks,
                            keywords_off=keywords_off, on_log=self.log)
        self.run_bg(task, on_done=self._pipeline_done, btn=btn)

    # ── 무인 자동 실행(--auto, 18:00 시작 → 06:00 자동 종료) ───────
    def start_auto(self):
        """무인 자동 실행 — 팝업 없이 ①판매수집+②키워드(자동순위 제외) → ③반자동 순위, 06:00 자동 종료.

        사람 개입 0: 입력·키 자동 로드, 확인 팝업 없음, 로그인 차단·2차인증 계정은 건너뜀(멈추지 않음),
        순위는 반자동 autosubmit(자동입력→자동검색→읽기, 차단 시 쿨다운/자동재개). 절전은 실행 동안 방지.
        """
        self.log("== [무인 자동 실행] 시작 ==")
        _prevent_sleep(True)
        if self.input_list is None:
            self.log("[무인] 입력 엑셀이 없어 실행 불가 — 앱을 한 번 수동 실행해 '입력 엑셀'을 연 뒤 다시 예약하세요. 종료")
            return self._auto_quit()
        if self.naver_creds is None or not self.ai_key:
            self.log("[무인] 네이버/OpenAI 키 미설정 — 설정 후 재시도. 종료")
            return self._auto_quit()
        self._schedule_auto_stop()                 # 06:00 자동 종료 예약
        df, dt = self._run_dates()                 # 당일=어제(D-1)
        meta = resumable_progress()
        resume = bool(meta)
        carry = bool(meta.get("carry", False)) if meta else master_exists()
        if resume:
            df, dt = meta["date_from"], meta["date_to"]
        self._semi_stop = threading.Event()
        n = sum(len(a.products) for a in self.input_list.accounts)
        self.log(f"[무인] ①판매수집+②키워드(자동순위 제외) → ③반자동 순위 · 상품 {n}개 · 기간 {df}~{dt} · "
                 f"{'이어서' if resume else ('이어쓰기' if carry else '새 통계')}")
        il, naver_creds, key, stop = self.input_list, self.naver_creds, self.ai_key, self._semi_stop

        def task():
            try:
                naver = NaverAdApi(naver_creds)
                run_full(il, naver, ai_key=key, date_from=df, date_to=dt,
                         get_password=self._account_pw, resume=resume, carry_forward=carry,
                         grow_keywords=False, skip_ranks=True, keywords_off=False, on_log=self.log)
                # 야간 1회 쿨다운-재개: 차단 등으로 미완료 계정이 남았으면(진행중 파일 잔존) 30분 쉬고
                # **남은 계정만 1회 더** 시도(제출 총량 억제 = 위탁계정 잠금 방지, 무한 재시도 금지).
                if (not stop.is_set() and config.LOGIN_NIGHT_RESUME and resumable_progress()):
                    mins = config.LOGIN_NIGHT_RESUME_COOLDOWN_SEC // 60
                    self.log(f"[무인] 차단 등 미완료 계정 남음 → {mins}분 쿨다운 후 1회 재개(남은 계정만)")
                    _interruptible_sleep(config.LOGIN_NIGHT_RESUME_COOLDOWN_SEC, stop.is_set,
                                         self.log, resume_label=" — 로그인 재개")
                    if not stop.is_set():
                        self.log("[무인] 쿨다운 종료 — 미완료 계정 로그인 재개(1회)")
                        run_full(il, naver, ai_key=key, date_from=df, date_to=dt,
                                 get_password=self._account_pw, resume=True, carry_forward=carry,
                                 grow_keywords=False, skip_ranks=True, keywords_off=False, on_log=self.log)
                if not stop.is_set():
                    track_ranks_stage(semi=True, should_stop=stop.is_set, on_log=self.log)
                # (결과는 구글 시트 통합으로 결과시트에 직접 반영 — rclone 업로드 제거)
            except Exception as exc:                # 무인: 어떤 오류도 앱을 매달아두지 않게 로그 후 종료로
                self.log(f"[무인] 실행 중 오류: {exc.__class__.__name__}: {exc}")
            return None
        self.run_bg(task, on_done=self._auto_done, btn=None)

    def _schedule_auto_stop(self):
        now = datetime.now()
        stop = now.replace(hour=6, minute=0, second=0, microsecond=0)
        if stop <= now:
            stop += timedelta(days=1)
        QtCore.QTimer.singleShot(int((stop - now).total_seconds() * 1000), self._auto_stop)
        self.log(f"[무인] {stop:%m-%d %H:%M} 자동 종료 예약")

    def _auto_stop(self):
        self.log("[무인] 06:00 도달 — 순위 조회 중지 요청 후 종료")
        ev = getattr(self, "_semi_stop", None)
        if ev is not None:
            ev.set()
        QtCore.QTimer.singleShot(60000, self._auto_quit)   # 정리 시간 준 뒤 강제 종료(백스톱)

    def _auto_done(self, _result=None):
        self.log("== [무인 자동 실행] 완료 — 종료 ==")
        self._auto_quit()

    def _auto_quit(self):
        _prevent_sleep(False)
        QtWidgets.QApplication.quit()

    def do_select_keywords(self):
        """② 키워드 선정 — 로그인 불필요. 최신 결과 워크북 상품에 키워드만 채운다(순위 없음)."""
        if self.input_list is None or self.naver_creds is None or not self.ai_key:
            QtWidgets.QMessageBox.warning(self, "키/입력 필요",
                                          "설정 탭에서 입력 엑셀·네이버 API·OpenAI 키를 먼저 준비하세요.")
            return
        if not (master_exists() or resumable_progress()):
            QtWidgets.QMessageBox.warning(self, "먼저 ① 판매수집",
                                          "결과 파일이 없습니다. ① 판매수집을 먼저 실행해 상품을 수집하세요.")
            return
        grow = self.cb_grow.isChecked()
        naver_creds, key = self.naver_creds, self.ai_key
        self.log("[키워드 선정] 시작 — 순위 조회 없이 키워드만 선정(로그인 불필요)")

        def task():
            return select_keywords_stage(NaverAdApi(naver_creds), key, grow=grow, on_log=self.log)
        self.run_bg(task, on_done=self._pipeline_done, btn=self.kw_btn)

    def do_track_ranks(self, semi: bool = True):
        """③ 노출순위 조회(반자동) — 로그인 불필요. 앱이 창을 띄우고 키워드를 안내, 사용자가 직접
        검색하면 그 화면을 읽어 기록한다(자동 검색을 안 해 차단이 안 생김). 자동 방식은 차단 위험으로 폐지.
        """
        if not (master_exists() or resumable_progress()):
            QtWidgets.QMessageBox.warning(self, "먼저 ①②",
                                          "결과 파일이 없습니다. ① 판매수집·② 키워드 선정을 먼저 실행하세요.")
            return
        self._semi_stop = threading.Event()
        self.track_stop_btn.setEnabled(True)
        self.log("[반자동 순위] 시작 — 뜬 창에서 로그에 안내되는 키워드를 직접 검색하세요(중지: '반자동 중지')")
        should_stop = self._semi_stop.is_set

        def task_semi():
            return track_ranks_stage(semi=True, should_stop=should_stop, on_log=self.log)
        self.run_bg(task_semi, on_done=self._pipeline_done, btn=self.track_semi_btn)

    def _stop_semi(self):
        """반자동 순위 중지 요청 — 현재 키워드까지만 처리하고 멈춤(진행분은 저장됨)."""
        ev = getattr(self, "_semi_stop", None)
        if ev is not None:
            ev.set()
            self.log("[반자동 순위] 중지 요청 — 현재 키워드 처리 후 멈춥니다")
        self.track_stop_btn.setEnabled(False)

    def _pipeline_done(self, path):
        self.log("=" * 50)
        self.log("[전체실행] ✅ 완료 — 통합 엑셀 생성됨")
        self.log(f"[전체실행] 파일: {path}")
        self.log("=" * 50)



def main():
    set_workdir()                   # .exe 더블클릭 대비 — 상대경로(output·data)가 exe 폴더에서 해석되게 CWD 고정
    auto = "--auto" in sys.argv     # 무인 자동 실행(작업 스케줄러가 18:00에 이 인자로 실행)
    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(_QSS)
    try:                            # Chrome 필수(실제 Chrome+CDP 정책) — 없으면 크래시 대신 안내 후 종료
        find_chrome()
    except FileNotFoundError:
        if auto:
            print("[무인] Google Chrome 미설치 — 실행 불가")   # 무인: 대화상자 대신 로그
        else:
            QtWidgets.QMessageBox.critical(
                None, "Google Chrome 필요",
                "이 프로그램은 실제 Google Chrome 으로 동작합니다.\n\n"
                "이 PC 에 Chrome 이 설치돼 있지 않습니다. https://www.google.com/chrome 에서 "
                "Chrome 을 설치한 뒤 다시 실행하세요.")
        sys.exit(1)
    reaped = reap_orphan_chrome()   # 이전 실행이 강제종료·크래시로 남긴 좀비 Chrome 정리(누적 원천 차단)
    if reaped:
        print(f"[시작] 잔여(좀비) Chrome {reaped}개 정리함")
    win = App(auto=auto)
    win.show()
    if auto:                        # 이벤트 루프 뜬 직후 무인 실행 자동 시작
        QtCore.QTimer.singleShot(1500, win.start_auto)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
