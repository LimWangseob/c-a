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
from coupang_analytics.browser import WingBrowser  # noqa: E402
from coupang_analytics.credstore import CredStore  # noqa: E402
from coupang_analytics.input_list import parse_input_list, parse_password_file  # noqa: E402
from coupang_analytics.kw_ai import recommend_title  # noqa: E402
from coupang_analytics.kw_recommend import recommend, recommend_from_title  # noqa: E402
from coupang_analytics.kw_shopping import NaverShopCredentials  # noqa: E402
from coupang_analytics.kw_volume import NaverAdApi, NaverCredentials, parse_credentials_file  # noqa: E402
from coupang_analytics.pipeline import master_exists, resumable_progress, run_full  # noqa: E402
from coupang_analytics.rank import make_matcher, organic_rank, warmup  # noqa: E402
from coupang_analytics.session_keepalive import KeepAlive  # noqa: E402

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

_CFG_ROWS = [
    ("키워드 추천 설정", None, None),
    ("검색량 하한", "KW_MIN_VOLUME", int),
    ("검색량 상한(추천 탭 전용)", "KW_MAX_VOLUME", int),
    ("후보 수집 수", "KW_CANDIDATE_LIMIT", int),
    ("추천 개수(top_n)", "KW_TOP_N", int),
    ("추적 키워드 수", "KW_TRACK_N", int),
    ("AI 앵커 수", "KW_AI_ANCHOR_N", int),
    ("AI 모델", "KW_AI_MODEL", str),
    ("순위 설정", None, None),
    ("순위 스캔 상한", "RANK_SCAN_MAX", int),
]
_LOG_COLORS = {"ok": "#4ade80", "err": "#f87171", "warn": "#fbbf24", "head": "#60a5fa", "": "#e2e8f0"}


class App(QtWidgets.QMainWindow):
    log_signal = QtCore.Signal(str)
    finish_signal = QtCore.Signal(object, object, object, object)   # (btn, on_done, result, err)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("쿠팡 애널리틱스")
        self.input_list = None
        self.naver_creds = None
        self.naver_shop = None
        self.ai_key = ""
        self._busy = False
        self.creds_store = CredStore()
        self.product_business: dict[str, str] = {}
        self.cfg_edits: dict[str, tuple] = {}
        self.keepalive = KeepAlive(
            account_ids_fn=lambda: [a.account_id for a in self.input_list.accounts] if self.input_list else [],
            on_log=self.log, pause_check=lambda: self._busy)

        # 실시간 모니터링용 로그 파일 미러(GUI 콘솔과 동일 내용을 파일로도 기록)
        _log_dir = Path(__file__).resolve().parents[1] / "output"
        _log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = _log_dir / f"run_log_{datetime.now():%y%m%d_%H%M%S}.log"

        self.log_signal.connect(self._append_log)
        self.finish_signal.connect(self._on_finish)

        self._build_ui()
        self._load_saved_secrets()
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
        self.pw_lbl = QtWidgets.QLabel("(입력 엑셀에 '비밀번호' 컬럼 있으면 자동 저장 · 별도 파일만 이 버튼)")
        self.naver_lbl = QtWidgets.QLabel("(네이버 API 키 미선택)")
        self.openai_lbl = QtWidgets.QLabel("(OpenAI 키 미설정 — 키워드 추출 불가)")
        self.shop_lbl = QtWidgets.QLabel("(선택) 네이버쇼핑 키 미설정 — 경쟁강도 미반영")
        rows = [
            ("입력 엑셀 열기", self.load_input, self.input_lbl),
            ("(선택) 비번 파일", self.load_passwords, self.pw_lbl),
            ("네이버 API 키 열기", self.load_naver, self.naver_lbl),
            ("OpenAI(ChatGPT) API 키 입력", self.load_openai, self.openai_lbl),
            ("(선택) 네이버쇼핑 키 입력", self.load_naver_shop, self.shop_lbl),
        ]
        for i, (text, cmd, lbl) in enumerate(rows):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(cmd)
            b.setMinimumWidth(210)
            grid.addWidget(b, i, 0)
            grid.addWidget(lbl, i, 1)
        grid.setColumnStretch(1, 1)
        v.addWidget(fk)

        cur_form, cur_n = None, 0
        for label, attr, cast in _CFG_ROWS:
            if attr is None:                       # 섹션 카드 시작
                card = self._card(label)
                cur_form = QtWidgets.QGridLayout(card)
                cur_form.setColumnStretch(1, 1)    # 입력칸 열 늘어남
                cur_form.setColumnStretch(3, 1)
                cur_form.setColumnMinimumWidth(0, 140)
                cur_form.setColumnMinimumWidth(2, 140)
                cur_n = 0
                v.addWidget(card)
                continue
            row, col = cur_n // 2, (cur_n % 2) * 2   # 1줄에 2개씩(라벨+입력칸)
            cur_form.addWidget(QtWidgets.QLabel(label), row, col)
            e = QtWidgets.QLineEdit(str(getattr(config, attr)))
            e.setMaximumWidth(200)
            cur_form.addWidget(e, row, col + 1)
            self.cfg_edits[attr] = (e, cast)
            cur_n += 1
        apply_btn = QtWidgets.QPushButton("설정 적용")
        apply_btn.setObjectName("accent")          # '전체 실행'과 동일한 파란 악센트
        apply_btn.clicked.connect(self.apply_settings)
        v.addWidget(apply_btn, alignment=QtCore.Qt.AlignRight)
        v.addStretch(1)
        return scroll

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
        v.addWidget(QtWidgets.QLabel("광고 제외 오가닉 순위를 조회합니다(상한 200위). 로그인 불필요."))
        v.addStretch(1)
        return w

    def _collect_tab(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(12, 10, 12, 10)
        run = self._card("전체 실행 (계정마다 로그인→판매분석→키워드→PC·모바일 순위 → 통합 엑셀)")
        rv = QtWidgets.QVBoxLayout(run)
        top = QtWidgets.QHBoxLayout()
        self.pipeline_btn = QtWidgets.QPushButton("전체 실행")
        self.pipeline_btn.setObjectName("accent")
        self.pipeline_btn.clicked.connect(self.do_run_full)
        top.addWidget(self.pipeline_btn)
        self.keepalive_btn = QtWidgets.QPushButton("세션 유지 켜기")
        self.keepalive_btn.clicked.connect(self.toggle_keepalive)
        top.addWidget(self.keepalive_btn)
        ka = QtWidgets.QLabel("(켜두면 세션을 주기적으로 살려둬 재로그인·2차인증이 줄어듭니다. 로그인 아님)")
        ka.setObjectName("muted")
        top.addWidget(ka)
        top.addStretch(1)
        rv.addLayout(top)
        desc = QtWidgets.QLabel(
            "계정마다 [로그인→판매분석→키워드→PC·모바일 순위]를 완결하고 통합 엑셀에 누적 저장합니다. "
            "로그인은 창 없이 자동, 2차인증 필요할 때만 창이 뜹니다(로그로 예고). 진행상황은 아래 로그에서 확인.")
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        rv.addWidget(desc)
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
        with open(self._log_path, "a", encoding="utf-8") as fh:  # 파일 미러(실시간 tail용)
            fh.write(f"[{ts}] {msg}\n")

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
        if err is not None:
            self.log(f"[오류] {err.__class__.__name__}: {err}")
        elif on_done is not None:
            on_done(result)

    # ── 파일·키 로드 ──────────────────────────────────────────
    def load_input(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "입력 분석용 엑셀", "", "Excel (*.xlsx)")
        if not path:
            return
        il = parse_input_list(path)
        self.input_list = il
        self.product_business.clear()
        products = []
        for a in il.accounts:
            for p in a.products:
                products.append(p.name)
                self.product_business[p.name] = a.business_name
        self.kw_product.clear()
        self.kw_product.addItems(products)
        self.input_lbl.setText(f"{Path(path).name}  (계정 {len(il.accounts)}, 상품 {len(products)})")
        self.log(f"[입력] {len(il.accounts)}계정 · 상품 {len(products)}개 로드 · 오류 {len(il.errors)}건")
        for e in il.errors[:5]:
            self.log(f"   - 입력오류: {e}")
        self._store_passwords_from(path, quiet=True)

    def _store_passwords_from(self, path, quiet=False) -> int:
        try:
            pw_map = parse_password_file(path)
        except Exception as exc:
            if not quiet:
                QtWidgets.QMessageBox.warning(self, "비밀번호 파일 오류", str(exc))
            return 0
        saved = 0
        for aid, pw in pw_map.items():
            try:
                self.creds_store.set_password(aid, pw)
                saved += 1
            except Exception as exc:
                self.log(f"[비번] {aid} 저장 실패: {exc.__class__.__name__}")
        if saved:
            self.pw_lbl.setText(f"{Path(path).name}  (계정 {saved}개 비번 암호화 저장)")
            self.log(f"[비번] {saved}개 계정 비밀번호 저장됨 (이 PC 전용 암호화, 공유·git 안 됨). 순차 로그인 시 자동입력.")
        elif not quiet:
            self.log("[비번] 비밀번호를 찾지 못했습니다 (계정아이디/비밀번호 컬럼 확인).")
        return saved

    def load_passwords(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "계정 비밀번호 엑셀 (계정아이디+비밀번호 컬럼)", "", "Excel (*.xlsx);;All (*.*)")
        if path:
            self._store_passwords_from(path, quiet=False)

    def _account_pw(self, account_id):
        try:
            return self.creds_store.get_password(account_id) or None
        except Exception:
            return None

    def load_naver(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "네이버 검색광고 API 키 파일", "", "Text (*.txt);;All (*.*)")
        if not path:
            return
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

    def load_naver_shop(self):
        cid, ok1 = QtWidgets.QInputDialog.getText(self, "네이버쇼핑 Client ID", "개발자센터 Client ID")
        if not (ok1 and cid):
            return
        sec, ok2 = QtWidgets.QInputDialog.getText(
            self, "네이버쇼핑 Client Secret", "개발자센터 Client Secret", QtWidgets.QLineEdit.Password)
        if not (ok2 and sec):
            return
        self.naver_shop = NaverShopCredentials(cid.strip(), sec.strip())
        self.shop_lbl.setText("(네이버쇼핑 키: 입력됨 — 경쟁강도 반영)")
        try:
            self.creds_store.set_password("__naver_shop__", json.dumps(
                {"client_id": self.naver_shop.client_id, "client_secret": self.naver_shop.client_secret}))
            self.log("[네이버쇼핑] 키 입력·저장됨 (경쟁강도 선정 반영)")
        except Exception as exc:
            self.log(f"[네이버쇼핑] 입력됨(저장 실패: {exc.__class__.__name__})")

    def _load_saved_secrets(self):
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
            sj = self.creds_store.get_password("__naver_shop__")
        except Exception:
            sj = None
        if sj:
            d = json.loads(sj)
            self.naver_shop = NaverShopCredentials(d["client_id"], d["client_secret"])
            self.shop_lbl.setText("(네이버쇼핑 키: 저장됨 — 경쟁강도 반영)")
            self.log("[네이버쇼핑] 저장된 키 자동 로드됨")
        try:
            ak = self.creds_store.get_password("__openai__")
        except Exception:
            ak = None
        if ak:
            self.ai_key = ak
            self.openai_lbl.setText("(OpenAI 키: 저장됨 — 자동 로드)")
            self.log("[OpenAI] 저장된 키 자동 로드됨")

    # ── 설정 ──────────────────────────────────────────────────
    def apply_settings(self):
        for attr, (edit, cast) in self.cfg_edits.items():
            raw = edit.text().strip()
            try:
                setattr(config, attr, cast(raw))
            except ValueError:
                QtWidgets.QMessageBox.warning(self, "설정 오류", f"'{attr}' 값이 올바르지 않습니다: {raw}")
                return
        self.log("[설정] 적용됨 — " + ", ".join(f"{a}={getattr(config, a)}" for a in self.cfg_edits))
        QtWidgets.QMessageBox.information(self, "설정", "설정이 적용되었습니다.")

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
            f"[순위] 결과: {('오가닉 ' + str(r) + '위') if r else '200위 내 미노출'}"), btn=self.rank_btn)

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

    def do_run_full(self):
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
        n = sum(len(a.products) for a in self.input_list.accounts)
        resume = carry = False
        meta = resumable_progress()
        if meta:                        # ① 같은 날 크래시 복구
            mode = "통계 이어쓰기" if meta.get("carry") else "새 통계"
            box = QtWidgets.QMessageBox(self)
            box.setWindowTitle("이어서 할까요?")
            box.setText(f"이전에 끝나지 않은 작업이 있습니다({mode}).\n기간 {meta['date_from']}~{meta['date_to']}, "
                        f"완료 {len(meta['done'])}개 계정.\n\n[예] 이어서 / [아니오] 처음부터 다시 / [취소] 중단")
            box.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel)
            ans = box.exec()
            if ans == QtWidgets.QMessageBox.Cancel:
                return
            resume = ans == QtWidgets.QMessageBox.Yes
            if resume:
                df, dt = meta["date_from"], meta["date_to"]
        elif master_exists():           # ② 통계 마스터 있음 — 오늘 이어쓸지/새로 시작할지
            box = QtWidgets.QMessageBox(self)
            box.setWindowTitle("오늘 통계 이어쓰기")
            box.setText(f"기존 통계(쿠팡데이타분석_통계.xlsx)가 있습니다.\n오늘({dt}) 데이터를 이어서 쌓을까요?\n"
                        "키워드는 그대로 유지되고 오늘 날짜만 추가됩니다.\n\n"
                        "[예] 기존 통계에 추가 / [아니오] 새 통계 시작(기존은 보관) / [취소] 중단")
            box.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel)
            ans = box.exec()
            if ans == QtWidgets.QMessageBox.Cancel:
                return
            carry = ans == QtWidgets.QMessageBox.Yes
        else:                           # ③ 첫 실행(새 통계)
            if QtWidgets.QMessageBox.question(
                    self, "새 통계 시작", f"상품 {n}개, 기간 {df}~{dt}.\n첫 통계를 시작합니다(키워드 선정). "
                    "이후 매일 실행하면 키워드를 유지하며 누적됩니다.\n진행할까요?") != QtWidgets.QMessageBox.Yes:
                return
        grow = carry and self.cb_grow.isChecked()   # 발굴 추가는 통계 이어쓰기 때만 의미
        input_list, naver_creds, key = self.input_list, self.naver_creds, self.ai_key
        mode_txt = "이어서 " if resume else ("통계이어쓰기 " if carry else "새통계 ")
        self.log(f"[전체실행] {mode_txt}시작 — 상품 {n}개, 기간 {df}~{dt}"
                 f"{' · 새 키워드 발굴 추가' if grow else ''}")

        def task():
            self._busy = True
            try:
                naver = NaverAdApi(naver_creds)
                return run_full(input_list, naver, ai_key=key, date_from=df, date_to=dt,
                                get_password=self._account_pw, resume=resume, carry_forward=carry,
                                grow_keywords=grow, on_log=self.log)
            finally:
                self._busy = False
        self.run_bg(task, on_done=self._pipeline_done, btn=self.pipeline_btn)

    def _pipeline_done(self, path):
        self.log("=" * 50)
        self.log("[전체실행] ✅ 완료 — 통합 엑셀 생성됨")
        self.log(f"[전체실행] 파일: {path}")
        self.log("=" * 50)

    def toggle_keepalive(self):
        if self.keepalive.is_running():
            self.keepalive.stop()
            self.keepalive_btn.setText("세션 유지 켜기")
            return
        if self.input_list is None:
            QtWidgets.QMessageBox.warning(self, "입력 필요", "먼저 설정 탭에서 입력 엑셀을 여세요(대상 계정 목록).")
            return
        self.keepalive.start()
        self.keepalive_btn.setText("세션 유지 끄기")


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(_QSS)
    win = App()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
