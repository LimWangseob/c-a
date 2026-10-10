"""쿠팡 애널리틱스 데스크톱 UI — PySide6(Qt) + Windows 11 Fluent 스타일(QSS).

화면 계층만 Qt로 재작성. 수집/로그인/키워드/순위 등 **백엔드 로직은 기존 모듈 그대로 호출**한다.
(Tkinter 버전 `ui/app.py`는 폴백으로 보존.)
- 실제 Win11 룩: 둥근 모서리·플랫 카드·흰 카드/슬레이트 캔버스·**틸 악센트 통일**·슬레이트 콘솔 로그.
- 브라우저/수집 작업은 백그라운드 스레드에서 실행하고, 로그·완료는 시그널로 GUI 스레드에 전달.
"""
from __future__ import annotations

import html
import json
import os
import sys
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))   # ui/ 형제 모듈(registry_ui 등)

from coupang_analytics import appconfig, config, keyword_store  # noqa: E402
from coupang_analytics.apppaths import output_dir as app_output_dir, set_workdir  # noqa: E402
from coupang_analytics.app_process import (mark_app_finished, prepare_auto_start,  # noqa: E402
                                           start_settlement_watch)
from coupang_analytics.browser import WingBrowser, find_chrome, reap_orphan_chrome  # noqa: E402
from coupang_analytics.credstore import CredStore  # noqa: E402
from coupang_analytics import detail_images  # noqa: E402
from coupang_analytics import holiday_source  # noqa: E402
from coupang_analytics import gsheet_api, gsheet_index  # noqa: E402
from coupang_analytics.input_list import (parse_input_list, parse_input_rows,  # noqa: E402
                                           parse_password_candidates,
                                           read_ledger_rows, read_xlsx_rows)
from coupang_analytics.kw_ai import recommend_title  # noqa: E402
from coupang_analytics.kw_recommend import recommend, recommend_from_title  # noqa: E402
from coupang_analytics.kw_volume import NaverAdApi, NaverCredentials, parse_credentials_file  # noqa: E402
from coupang_analytics.pipeline import (column_dates, _interruptible_sleep, backup_sources,  # noqa: E402
                                        master_exists, plan_run_mode, push_company_stock,
                                        push_ledger_inventory,
                                        read_run_stage, resumable_progress, restore_master_from_gsheet,
                                        run_full, run_log_labels, run_title,
                                        select_keywords_stage,
                                        track_ranks_stage, write_run_stage)
from coupang_analytics.rank import make_matcher, organic_rank, warmup  # noqa: E402
import registry_ui  # noqa: E402
from proxy_panel_qt import ProxyPanelMixin  # noqa: E402
from registry_panel_qt import RegistryPanelMixin  # noqa: E402
from settlement_status_panel_qt import SettlementStatusMixin  # noqa: E402
from stock_panel_qt import KEY_STOCK_URL, StockPanelMixin  # noqa: E402

_PROFILE = "data/chrome-ui"
_IMG_PROFILE = "data/chrome-images"   # 상세이미지 전용 Chrome 프로필(사용자가 여기 코팡 로그인 → warm 영속)
_IMG_CDP_PORT = 9222                  # 그 Chrome 을 디버그포트로 띄워 앱이 CDP 로 붙는다(A안)

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

/* 체크박스 — 빈 네모(흰 바탕·회색 테두리), 선택 시 파란 채움 + 흰색 체크마크 */
QCheckBox { background: transparent; padding: 4px; spacing: 8px; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px;
    border: 2px solid #9aa7b6; background: #ffffff; }
QCheckBox::indicator:hover { border: 2px solid #2563eb; }
QCheckBox::indicator:checked { border: 2px solid #2563eb; background: #2563eb; image: url(__CHECK_ICON__); }
QCheckBox:checked { color: #1f2937; font-weight: 600; }

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


# 설정 탭 '구글 시트 연동' 카드의 링크 4개 — 종류 → (설정 키, 화면 이름). 링크 입력은 **설정 탭에서만**
# (2026-10-03 소유자: 흩어진 설정 일원화 — 9/29 에 정산 탭으로 옮겼던 재고현황·원장 링크칸을 다시 설정으로).
_GS_LINKS = {
    "input": ("gsheet/input_url", "관리대장(입력)"),
    "output": ("gsheet/output_url", "결과(출력)"),
    "stock": (KEY_STOCK_URL, "재고현황(회사 재고)"),
    "registry": (registry_ui.KEY_URL, "셀독등록원장"),
}


class App(RegistryPanelMixin, StockPanelMixin, ProxyPanelMixin, SettlementStatusMixin, QtWidgets.QMainWindow):
    log_signal = QtCore.Signal(str)
    finish_signal = QtCore.Signal(object, object, object, object)   # (btn, on_done, result, err)
    gs_status_signal = QtCore.Signal(str, object, str)   # (_GS_LINKS 종류, 연결됨 True/False/None=미확인, 설명)

    def __init__(self, auto: bool = False):
        super().__init__()
        self.auto = auto            # 무인 자동 실행(--auto) 모드 — 팝업 없이 로그로, **완주 후에만 종료**(강제종료 없음)
        self.setWindowTitle("쿠팡 애널리틱스")
        self.input_list = None
        self.naver_creds = None
        self.ai_key = ""
        self.creds_store = CredStore()
        self.product_business: dict[str, str] = {}

        # 실시간 모니터링용 로그 파일 미러(GUI 콘솔과 동일 내용을 파일로도 기록).
        # **보존 폴더(프로젝트 루트)/output** 에 남긴다 — 실행 폴더가 바뀌어도 마스터·로그가 한 곳에 모이게.
        self._log_path = app_output_dir() / f"run_log_{datetime.now():%y%m%d_%H%M%S}.log"

        self.log_signal.connect(self._append_log)
        self.finish_signal.connect(self._on_finish)
        self.gs_status_signal.connect(self._set_gs_status)

        self._build_ui()
        self._load_saved_secrets()
        self._auto_load_input()     # 마지막 사용 입력 엑셀 자동 로드(무인 실행·재시작 후 즉시 실행 가능)
        if not auto:
            self._probe_gsheet_links()  # 구글시트 링크 4개 연결 상태를 뒤에서 확인해 라벨로(무인 실행은 생략)
        scr = self.screen().availableGeometry()
        # 최대 크기 = 화면(작업영역)으로 제한 — 창이 화면보다 커지지 않게.
        self.setMaximumSize(scr.width(), scr.height())
        # 자유롭게 좌우·상하로 줄일 수 있게 최소 크기는 작게(내용은 스크롤/줄바꿈으로 수용).
        self.setMinimumSize(min(720, scr.width()), min(480, scr.height()))
        # 시작 크기 = 화면 안에서 적당히(화면이 작으면 화면에 맞춤).
        self.resize(min(1100, scr.width()), min(900, scr.height()))

    # ── 레이아웃 ──────────────────────────────────────────────
    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._header())
        self.tabs = QtWidgets.QTabWidget()
        # 탭 ↔ 진행 로그를 위아래 나눔막대(splitter)로 — 고정 높이(예전 360px)는 설정·정산 탭 하단을 잘랐다.
        # 로그가 숨으면 탭이 전체 높이를 쓰고, 로그가 보이면 처음 한 번 탭 ~400px·로그 나머지(사용자가 끌어 조절).
        self._splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.addWidget(self.tabs)
        root.addWidget(self._splitter, 1)
        self.tabs.addTab(self._settings_tab(), "설정")
        self.tabs.addTab(self._sales_tab(), "판매 분석")   # 결과 엑셀에서 판매지표 조회(수집 아님)
        self.tabs.addTab(self._kw_tab(), "키워드 추천")
        self.tabs.addTab(self._rank_tab(), "순위 조회")
        self.tabs.addTab(self._images_tab(), "상세 이미지")
        self.tabs.addTab(self._collect_tab(), "전체 실행")
        self.tabs.addTab(self._settlement_tab(), "정산")   # 회사재고 + 셀독등록원장 실행(링크는 설정 탭)
        self.log_panel = self._log_panel()
        self._splitter.addWidget(self.log_panel)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)   # 창을 키우면 로그가 늘어남
        self._log_sized = False                 # 로그 첫 표시 때 한 번만 나눔 크기 지정
        # 진행 로그창 = **실행 버튼을 누른 뒤부터** 표시(소유자 2026-09-29). 처음(설정 화면)엔 숨김.
        # 설정 탭에서 유휴면 숨기되, 설정 탭의 실행(원장 반영·연결확인 등)이 도는 동안은 예외로 보인다.
        self._log_activated = False        # 첫 실행이 일어났는가(그 전엔 항상 숨김)
        self._bg_active = 0                # 현재 도는 백그라운드 작업 수(설정 탭 유휴 판정용)
        self._settings_hold = False        # 설정 탭에서 시작한 작업의 결과 로그를 탭을 떠날 때까지 유지
        self.log_panel.setVisible(False)
        self.tabs.currentChanged.connect(self._on_tab_changed)

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

        note = QtWidgets.QLabel(
            "ℹ️ 설정은 입력·선택·연결확인 즉시 <b>자동 저장</b>됩니다. 맨 아래 <b>‘설정값 저장’</b> 버튼으로 "
            "한 번에 확정 저장할 수도 있습니다. 창 모서리를 끌어 크기를 바꿀 수 있고, 내용이 길면 자동 스크롤됩니다.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#1B5E20; background:#E8F5E9; border:1px solid #A5D6A7;"
                           "border-radius:6px; padding:8px 10px;")
        v.addWidget(note)

        fk = self._card("파일 · API 키")
        grid = QtWidgets.QGridLayout(fk)
        self.input_lbl = QtWidgets.QLabel("(입력 분석용 엑셀 미선택)")
        self.naver_lbl = QtWidgets.QLabel("(네이버 API 키 미선택)")
        self.openai_lbl = QtWidgets.QLabel("(OpenAI 키 미설정 — 키워드 추출 불가)")
        self.holiday_lbl = QtWidgets.QLabel("(공휴일 API 키 미설정 — 정산 지급일 계산용)")
        rows = [
            ("입력 엑셀 열기", self.load_input, self.input_lbl),
            ("네이버 API 키 열기", self.load_naver, self.naver_lbl),
            ("OpenAI(ChatGPT) API 키 입력", self.load_openai, self.openai_lbl),
            ("공휴일 API 키 입력", self.load_holiday_key, self.holiday_lbl),
        ]
        for i, (text, cmd, lbl) in enumerate(rows):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(cmd)
            b.setMinimumWidth(210)
            grid.addWidget(b, i, 0)
            grid.addWidget(lbl, i, 1)
        self.holiday_chk_btn = QtWidgets.QPushButton("연결 확인")
        self.holiday_chk_btn.setToolTip("data.go.kr 특일정보로 올해 공휴일을 조회해 키가 동작하는지 확인")
        self.holiday_chk_btn.clicked.connect(self.check_holiday_key)
        grid.addWidget(self.holiday_chk_btn, len(rows) - 1, 2)
        grid.setColumnStretch(1, 1)
        v.addWidget(fk)
        v.addWidget(self._gsheet_card())   # 구글 시트 연동(서비스계정 · 관리대장 · 결과 · 재고현황 · 원장 링크)
        v.addWidget(self._rank_delay_card())   # 순위 검색 간격(운영값) — 저장만, 파이프라인 배선은 통합(config)
        v.addWidget(self._proxy_card())        # 노출순위 프록시·이미지 끄기(config.json 토글)
        v.addWidget(self._img_dir_card())      # 상세 이미지 저장 폴더
        save_row = QtWidgets.QHBoxLayout()
        save_row.addStretch(1)
        self.save_settings_btn = QtWidgets.QPushButton("💾 설정값 저장")
        self.save_settings_btn.setMinimumWidth(180)
        self.save_settings_btn.setToolTip("구글시트 링크 4개·입력소스·순위 간격·프록시를 config.json(+레지스트리)에 한 번에 확정 저장")
        self.save_settings_btn.clicked.connect(self._save_all_settings)
        save_row.addWidget(self.save_settings_btn)
        v.addLayout(save_row)
        v.addStretch(1)
        self._settings_page = scroll         # 정산 탭 [설정에서 변경] 이동 대상
        return scroll

    def _save_all_settings(self):
        """설정 탭의 값(구글시트 링크 4개·입력소스·순위 간격·프록시)을 config.json(+레지스트리)에 일괄 확정 저장.

        각 항목은 평소 입력·선택 즉시 자동 저장되지만, 이 버튼은 현재 화면값을 **한 번에** 확정 저장한다
        (링크를 입력하고 Enter/포커스이동을 안 했어도 확실히 저장). 자동저장과 동일한 `_cfg_save_shared` 경로."""
        for kind, (key, _who) in _GS_LINKS.items():
            _cfg_save_shared(key, self._gs_edits[kind].text().strip())
            self._refresh_link_state(kind)
        src = ("gsheet" if self.src_gsheet_radio.isChecked()
               else "file" if self.src_file_radio.isChecked()
               else registry_ui.SOURCE_REGISTRY)
        _cfg_save_shared("input/source", src)
        _cfg_save_shared(_KEY_RANK_MIN, str(self.rank_delay_min.value()))
        _cfg_save_shared(_KEY_RANK_MAX, str(self.rank_delay_max.value()))
        for key, val in self._proxy_values().items():
            _cfg_save_shared(key, val)
        QtWidgets.QMessageBox.information(
            self, "저장 완료",
            "✅ 설정값을 저장했습니다.\n(참고: 각 항목은 입력·선택 즉시 자동 저장되며, 이 버튼은 전체를 한 번에 확정 저장합니다.)")

    def _rank_delay_card(self):
        """③ 순위 검색 간격(초) — 운영자가 화면에서 조정. QSettings/config.json `rank/nav_delay_min|max`
        에 저장하고, 실제 적용(파이프라인이 이 값을 읽기)은 config.py 배선(통합 소관). 비어 있으면 config 기본값."""
        st = QtCore.QSettings("coupang-analytics", "ui")
        card = self._card("순위 검색 간격 (③ 순위 조회)")
        row = QtWidgets.QHBoxLayout(card)
        self.rank_delay_min = QtWidgets.QSpinBox()
        self.rank_delay_max = QtWidgets.QSpinBox()
        defaults = (config.RANK_NAV_DELAY_MIN_SEC, config.RANK_NAV_DELAY_MAX_SEC)
        for sb, key, dv in ((self.rank_delay_min, _KEY_RANK_MIN, defaults[0]),
                            (self.rank_delay_max, _KEY_RANK_MAX, defaults[1])):
            sb.setRange(10, 600)
            sb.setSuffix(" 초")
            sb.setValue(st.value(key, dv, type=int))
        self.rank_delay_min.valueChanged.connect(lambda _v: self._on_rank_delay_changed("min"))
        self.rank_delay_max.valueChanged.connect(lambda _v: self._on_rank_delay_changed("max"))
        row.addWidget(QtWidgets.QLabel("검색 사이 대기"))
        row.addWidget(self.rank_delay_min)
        row.addWidget(QtWidgets.QLabel("~"))
        row.addWidget(self.rank_delay_max)
        hint = QtWidgets.QLabel(f"기본 {defaults[0]}~{defaults[1]}초. 너무 낮추면 쿠팡 차단 — "
                                "차단 없이 며칠 지난 뒤 조금씩만 낮추세요.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        row.addWidget(hint, 1)
        return card

    def _on_rank_delay_changed(self, which: str):
        """최소 ≤ 최대 유지(방금 바꾼 쪽을 기준으로 다른 쪽을 맞춤) 후 둘 다 저장."""
        lo, hi = self.rank_delay_min.value(), self.rank_delay_max.value()
        if lo > hi:
            (self.rank_delay_max if which == "min" else self.rank_delay_min).setValue(lo if which == "min" else hi)
            return                              # 맞춘 쪽의 valueChanged 가 다시 들어와 저장
        _cfg_save_shared(_KEY_RANK_MIN, str(lo))
        _cfg_save_shared(_KEY_RANK_MAX, str(hi))

    def _img_dir_card(self):
        """상세 이미지 저장 폴더(QSettings `dir/detail_images`) — 변경은 여기서만, 상세 이미지 탭은 표시·열기만."""
        card = self._card("상세 이미지 저장 폴더")
        row = QtWidgets.QHBoxLayout(card)
        self.img_dir_set_lbl = QtWidgets.QLabel(self._img_out_root())
        self.img_dir_set_lbl.setWordWrap(True)
        self.img_dir_set_lbl.setMinimumWidth(0)
        row.addWidget(self.img_dir_set_lbl, 1)
        chg = QtWidgets.QPushButton("폴더 변경")
        chg.clicked.connect(self._img_change_dir)
        row.addWidget(chg)
        return card

    def _goto_link_setting(self, kind: str):
        """다른 탭의 [설정에서 변경] → 설정 탭으로 이동해 그 링크칸에 커서."""
        self.tabs.setCurrentWidget(self._settings_page)
        edit = self._gs_edits[kind]
        self._settings_page.ensureWidgetVisible(edit)
        edit.setFocus()

    def _settlement_tab(self):
        """정산 탭 — 회사보유재고(재고현황→관리대장) + 셀독등록원장(원장 미리보기/반영·비밀번호 불일치).

        설정 탭에 있던 두 카드를 정산 성격으로 묶어 별도 탭으로(2026-09-29 소유자). 카드 자체는 mixin 이 만든다."""
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        inner = QtWidgets.QWidget()
        scroll.setWidget(inner)
        v = QtWidgets.QVBoxLayout(inner)
        v.setContentsMargins(14, 12, 14, 12)
        sub = QtWidgets.QLabel("회사 재고(판매자배송) 반영과 셀독등록원장 관리를 여기서 합니다. "
                               "링크 등록·변경은 '설정' 탭에서 합니다. 정산 금액·지급일 계산 기능은 준비 중입니다.")
        sub.setObjectName("muted")
        sub.setWordWrap(True)
        v.addWidget(sub)
        v.addWidget(self._settlement_status_card())  # 창 없는 정산 자동 다운로드의 '지금 상태'를 색으로 한눈에
        v.addWidget(self._stock_card())     # 회사 재고(판매자배송) — 재고현황 → 관리대장 '회사보유재고'
        v.addWidget(self._registry_card())  # 셀독등록원장(원장 링크·미리보기/반영·비밀번호 불일치)
        v.addStretch(1)
        return scroll

    # ── 판매 분석 탭(조회 전용) ──────────────────────────────
    _SALES_COLS = ("사업자", "상품", "최신 수집일", "판매량", "방문자", "노출량", "재고", "최고 순위")

    def _sales_tab(self):
        """판매 분석 — **수집된 결과 엑셀(통계 마스터)에서** 사업자·상품·최신 일자 판매지표를 표로 조회.

        실행·수집이 아니라 **조회 전용**(소유자 2026-09-29: 데이터 출처=엑셀 파일). '새로고침'으로 최신 결과
        엑셀을 읽어 표를 채우고, '결과 엑셀/폴더 열기'로 원본을 직접 연다."""
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(12, 10, 12, 10)
        card = self._card("판매 분석 — 결과 엑셀(통계 마스터)에서 최신 판매지표 조회")
        cv = QtWidgets.QVBoxLayout(card)
        bar = QtWidgets.QHBoxLayout()
        self.sales_refresh_btn = QtWidgets.QPushButton("새로고침")
        self.sales_refresh_btn.setToolTip("결과 엑셀(통계 마스터)을 다시 읽어 아래 표를 갱신합니다(수집 아님).")
        self.sales_refresh_btn.clicked.connect(self._load_sales_analysis)
        self.sales_open_btn = QtWidgets.QPushButton("결과 엑셀 열기")
        self.sales_open_btn.clicked.connect(self._open_master_excel)
        self.sales_folder_btn = QtWidgets.QPushButton("결과 폴더 열기")
        self.sales_folder_btn.clicked.connect(self._open_output_folder)
        for b in (self.sales_refresh_btn, self.sales_open_btn, self.sales_folder_btn):
            bar.addWidget(b)
        bar.addStretch(1)
        cv.addLayout(bar)
        self.sales_summary_lbl = QtWidgets.QLabel("‘새로고침’을 눌러 결과 엑셀에서 판매지표를 불러오세요.")
        self.sales_summary_lbl.setObjectName("muted")
        cv.addWidget(self.sales_summary_lbl)
        self.sales_table = QtWidgets.QTableWidget(0, len(self._SALES_COLS))
        self.sales_table.setHorizontalHeaderLabels(list(self._SALES_COLS))
        self.sales_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.sales_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.sales_table.horizontalHeader().setStretchLastSection(True)
        self.sales_table.verticalHeader().setVisible(False)
        cv.addWidget(self.sales_table, 1)
        v.addWidget(card, 1)
        return w

    def _master_xlsx_path(self) -> Path:
        """결과 통계 마스터 엑셀 경로(output/쿠팡데이타분석_통계.xlsx)."""
        return app_output_dir() / f"{config.OUTPUT_FILE_PREFIX}_통계.xlsx"

    @staticmethod
    def _metric_at_latest(wb, biz: str, prod: str, metric: str):
        """워크북에서 그 상품의 **최신 일자** 지표 값(없으면 ''). product_inventory 와 같은 방식(읽기 전용)."""
        row = wb._metric_row.get((biz, prod, metric))
        d = wb.latest_date(biz)
        col = wb._date_col.get(biz, {}).get(d) if d else None
        if row is None or col is None:
            return ""
        val = wb.wb[biz].cell(row, col).value
        return "" if val is None else val

    @staticmethod
    def _best_rank_at_latest(wb, biz: str, prod: str) -> str:
        """최신 일자 기준 그 상품 키워드들 중 **가장 좋은 순위**('12위 · 키워드'). 정확 순위 없으면 ''
        ('N위밖'·공란·차단은 제외 — 계정목록 체험단효과와 같은 판정 wb._rank_num)."""
        d = wb.latest_date(biz)
        col = wb._date_col.get(biz, {}).get(d) if d else None
        if col is None:
            return ""
        best = None
        for kw in wb.product_keywords(biz, prod):
            row = wb._kw_row.get((biz, prod, kw))
            n = wb._rank_num(wb.wb[biz].cell(row, col).value) if row else None
            if n is not None and (best is None or n < best[0]):
                best = (n, kw)
        return f"{best[0]}위 · {best[1]}" if best else ""

    def _load_sales_analysis(self):
        """결과 엑셀(통계 마스터)을 읽어 판매 분석 표를 채운다(조회 전용·비치명)."""
        from coupang_analytics.workbook import OutputWorkbook
        master = self._master_xlsx_path()
        if not master.exists():
            self.sales_table.setRowCount(0)
            self.sales_summary_lbl.setText(
                "결과 엑셀(통계 마스터)이 아직 없습니다 — ①판매수집 또는 전체 실행으로 데이터를 먼저 수집하세요.")
            return
        try:
            wb = OutputWorkbook.load(master)
        except Exception as exc:
            self.sales_summary_lbl.setText(f"결과 엑셀을 읽지 못했습니다: {exc.__class__.__name__}: {exc}")
            return
        rows = []
        for biz in wb.account_sheets():
            d = wb.latest_date(biz) or ""
            for prod in wb.products_of(biz):
                rows.append((
                    biz, prod, d,
                    self._metric_at_latest(wb, biz, prod, config.M_SALES),
                    self._metric_at_latest(wb, biz, prod, config.M_VISITORS),
                    self._metric_at_latest(wb, biz, prod, config.M_VIEWS),
                    self._metric_at_latest(wb, biz, prod, config.M_INVENTORY),
                    self._best_rank_at_latest(wb, biz, prod)))
        self.sales_table.setRowCount(len(rows))
        for r, vals in enumerate(rows):
            for c, val in enumerate(vals):
                it = QtWidgets.QTableWidgetItem("" if val == "" else str(val))
                if 3 <= c <= 6:                  # 지표(판매량~재고)는 우측 정렬
                    it.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                self.sales_table.setItem(r, c, it)
        self.sales_table.resizeColumnsToContents()
        self.sales_summary_lbl.setText(
            f"사업자 {len(wb.account_sheets())} · 상품 {len(rows)} · 결과: {master.name} "
            "(판매량·방문자·노출량·최고 순위=최신 일자 값)")

    def _open_master_excel(self):
        master = self._master_xlsx_path()
        if master.exists():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(master)))
        else:
            QtWidgets.QMessageBox.information(self, "결과 없음", "통계 마스터 엑셀이 아직 없습니다(먼저 수집).")

    def _open_output_folder(self):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(app_output_dir())))

    def _gsheet_card(self):
        """구글 시트 연동 카드 — 서비스계정 키 + 구글시트 링크 4개(관리대장·결과·재고현황·원장) 등록.

        입력은 PC 엑셀('입력 엑셀 열기')과 **병존**한다. 여기서 링크를 등록하면 서비스계정으로 직접 읽는다.
        결과 시트는 프로그램이 계정목록/통계를 쓴다(서비스계정을 '편집자'로 공유 필요). 설정 상세=docs/GSHEET_SETUP.md.
        """
        st = QtCore.QSettings("coupang-analytics", "ui")
        card = self._card("구글 시트 연동 (관리대장 · 결과 · 재고현황 · 원장 — 링크는 모두 여기서 등록)")
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
        self.gs_input_edit.editingFinished.connect(lambda: self._on_gs_link_edited("input"))
        in_btns = QtWidgets.QHBoxLayout()
        in_chk = QtWidgets.QPushButton("연결 확인")
        in_chk.clicked.connect(lambda: self._check_gsheet("input"))
        in_load = QtWidgets.QPushButton("관리대장에서 불러오기")
        in_load.clicked.connect(self.load_input_from_gsheet)
        in_btns.addWidget(in_chk)
        in_btns.addWidget(in_load)
        g.addWidget(QtWidgets.QLabel("관리대장(입력) 링크"), 1, 0)
        g.addLayout(self._gs_link_box("input", self.gs_input_edit), 1, 1)
        g.addLayout(in_btns, 1, 2)

        # 2.5) 기본 입력 소스 — 시작(무인 자동로드)이 어느 쪽을 쓸지. 구글시트=기본, PC 엑셀=선택.
        cur_src = st.value("input/source", "", type=str)
        if cur_src not in ("gsheet", "file", registry_ui.SOURCE_REGISTRY):
            cur_src = "gsheet"                        # 미설정 = 구글시트 기본(사용자 지정)
            _cfg_save_shared("input/source", cur_src)
        self.src_gsheet_radio = QtWidgets.QRadioButton("구글시트 관리대장(기본)")
        self.src_file_radio = QtWidgets.QRadioButton("PC 엑셀(선택)")
        self.src_registry_radio = QtWidgets.QRadioButton("원장(관리중만)")
        self.src_gsheet_radio.setChecked(cur_src == "gsheet")
        self.src_file_radio.setChecked(cur_src == "file")
        self.src_registry_radio.setChecked(cur_src == registry_ui.SOURCE_REGISTRY)
        src_box = QtWidgets.QHBoxLayout()
        for rb in (self.src_gsheet_radio, self.src_file_radio, self.src_registry_radio):
            rb.toggled.connect(self._on_input_source_changed)
            src_box.addWidget(rb)
        src_box.addStretch(1)
        g.addWidget(QtWidgets.QLabel("기본 입력 소스"), 2, 0)
        g.addLayout(src_box, 2, 1, 1, 2)

        # 3) 결과(출력) 링크
        self.gs_output_edit = QtWidgets.QLineEdit(st.value("gsheet/output_url", "", type=str))
        self.gs_output_edit.setPlaceholderText("결과 구글시트 링크 또는 ID (계정목록·통계를 여기에 씀 — 서비스계정 '편집자' 공유)")
        self.gs_output_edit.editingFinished.connect(lambda: self._on_gs_link_edited("output"))
        out_chk = QtWidgets.QPushButton("연결 확인")
        out_chk.clicked.connect(lambda: self._check_gsheet("output"))
        g.addWidget(QtWidgets.QLabel("결과(출력) 링크"), 3, 0)
        g.addLayout(self._gs_link_box("output", self.gs_output_edit), 3, 1)
        g.addWidget(out_chk, 3, 2)

        # 4) 재고현황(회사 재고)·셀독등록원장 링크 — 실행 버튼은 '정산' 탭(여기선 등록·연결확인만)
        self.stock_url_edit = QtWidgets.QLineEdit(st.value(KEY_STOCK_URL, "", type=str))
        self.stock_url_edit.setPlaceholderText("재고현황 구글시트 링크 또는 ID — 비우면 회사 재고 반영 안 함(서비스계정 공유)")
        self.reg_url_edit = QtWidgets.QLineEdit(st.value(registry_ui.KEY_URL, "", type=str))
        self.reg_url_edit.setPlaceholderText("원장 구글시트 링크 또는 ID — 비우면 원장 미사용(서비스계정 '편집자' 공유)")
        self._gs_edits = {"input": self.gs_input_edit, "output": self.gs_output_edit,
                          "stock": self.stock_url_edit, "registry": self.reg_url_edit}
        for row, kind in ((4, "stock"), (5, "registry")):
            edit = self._gs_edits[kind]
            edit.editingFinished.connect(lambda k=kind: self._on_gs_link_edited(k))
            chk = QtWidgets.QPushButton("연결 확인")
            chk.clicked.connect(lambda _c=False, k=kind: self._check_gsheet(k))
            g.addWidget(QtWidgets.QLabel(f"{_GS_LINKS[kind][1]} 링크"), row, 0)
            g.addLayout(self._gs_link_box(kind, edit), row, 1)
            g.addWidget(chk, row, 2)
        return card

    # ── 구글시트 링크 연결 상태 라벨(_GS_LINKS 4종) ─────────────────────
    def _gs_link_box(self, kind: str, edit):
        """링크 입력칸 + 그 아래 연결 상태 줄(서비스계정 라벨처럼 한눈에)."""
        box = QtWidgets.QVBoxLayout()
        box.setSpacing(2)
        lbl = QtWidgets.QLabel()
        lbl.setWordWrap(True)
        self.gs_status_lbl = getattr(self, "gs_status_lbl", {})
        self.gs_status_lbl[kind] = lbl
        box.addWidget(edit)
        box.addWidget(lbl)
        self._set_gs_status(kind, None, "링크 없음" if not edit.text().strip() else "확인 전")
        return box

    def _set_gs_status(self, kind: str, ok, detail: str):
        lbl = self.gs_status_lbl.get(kind)
        if lbl is None:
            return
        if ok is True:
            lbl.setText(f"✅ 연결됨 — {detail}")
            lbl.setStyleSheet("color: #047857;")
        elif ok is False:
            lbl.setText(f"⚠ 연결 안 됨 — {detail}")
            lbl.setStyleSheet("color: #b91c1c; font-weight: 700;")
        else:
            lbl.setText(f"({detail})")
            lbl.setStyleSheet("color: #64748b;")

    def _on_gs_link_edited(self, kind: str):
        _cfg_save_shared(_GS_LINKS[kind][0], self._gs_edits[kind].text().strip())
        self._refresh_link_state(kind)
        self._probe_gsheet_links((kind,))

    def _refresh_link_state(self, kind: str):
        """링크가 바뀌면 그 링크를 쓰는 정산 탭 상태줄도 맞춘다(회사재고·원장)."""
        if kind == "stock":
            self._refresh_stock_state()
        elif kind == "registry":
            self._refresh_registry_state()

    def _probe_gsheet_links(self, kinds=tuple(_GS_LINKS)):
        """등록된 링크를 뒤에서 열어 보고 상태 줄 갱신(진행 로그창은 건드리지 않음 — 첫 실행 전 숨김 유지)."""
        urls = {k: self._gs_edits[k].text().strip() for k in kinds}
        todo = [(k, urls[k]) for k in kinds if urls[k]]
        for k in kinds:
            self._set_gs_status(k, None, "확인 중…" if urls[k] else "링크 없음")

        def work():
            for k, url in todo:
                try:
                    title, sheets = gsheet_api.check_access(url, store=self.creds_store)
                    self.gs_status_signal.emit(k, True, f"'{title}' (시트 {len(sheets)}개)")
                except Exception as exc:          # 원인을 그대로 보여 준다(권한·링크·키 미등록 등)
                    self.gs_status_signal.emit(k, False, f"{exc.__class__.__name__}: {exc}")
        if todo:
            threading.Thread(target=work, daemon=True).start()

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

    # ── 상세 이미지 탭(반자동: 사람이 창에서 상품을 열고 '이미지 추출') ──
    def _images_tab(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(12, 10, 12, 10)

        card = self._card("상품 상세페이지 이미지 추출 (내 Chrome 세션에 붙어 추출 · 필요할 때 1건씩)")
        cv = QtWidgets.QVBoxLayout(card)

        img_desc = QtWidgets.QLabel(
            "① '쿠팡용 크롬 실행' → 뜬 <b>내 Chrome</b>에서 (처음이면 쿠팡 로그인 후) <b>상품 상세페이지를 여세요</b>.<br>"
            "② 상품이 화면에 뜬 상태에서 '이미지 추출' → 그 탭에서 대표+상세설명 이미지를 저장합니다.<br>"
            "③ 다음 상품을 그 크롬에서 열고 또 '이미지 추출' — 필요할 때마다 반복.<br>"
            "앱은 브라우저를 새로 띄우지 않고 내 로그인·warm 세션에 붙어 읽기만 하므로 차단(Access Denied)이 없습니다.")
        img_desc.setWordWrap(True)   # 줄바꿈 자동 — 안 하면 한 줄로 붙어 창 최소폭이 과도하게 커짐
        cv.addWidget(img_desc)

        btns = QtWidgets.QHBoxLayout()
        self.img_launch_btn = QtWidgets.QPushButton("쿠팡용 크롬 실행")
        self.img_launch_btn.setToolTip(
            f"디버그 포트({_IMG_CDP_PORT})로 전용 Chrome 을 띄웁니다(프로필 영속 — 한 번 로그인하면 유지).\n"
            "그 창에서 상품을 여신 뒤 '이미지 추출'을 누르세요.")
        self.img_launch_btn.clicked.connect(self.do_img_launch_chrome)
        btns.addWidget(self.img_launch_btn)

        self.img_extract_btn = QtWidgets.QPushButton("이미지 추출")
        self.img_extract_btn.setObjectName("accent")
        self.img_extract_btn.setToolTip("그 Chrome 에 지금 열려 있는 상품 상세페이지에서 대표+상세 이미지를 저장합니다.")
        self.img_extract_btn.clicked.connect(self.do_img_extract)
        btns.addWidget(self.img_extract_btn)
        btns.addStretch(1)
        cv.addLayout(btns)

        fold = QtWidgets.QHBoxLayout()
        fold.addWidget(QtWidgets.QLabel("저장 폴더:"))
        self.img_dir_lbl = QtWidgets.QLabel(self._img_out_root())
        self.img_dir_lbl.setStyleSheet("color:#556; ")
        self.img_dir_lbl.setWordWrap(True)          # 긴 경로가 창 폭을 강제하지 않게
        self.img_dir_lbl.setMinimumWidth(0)
        fold.addWidget(self.img_dir_lbl, 1)
        opn = QtWidgets.QPushButton("폴더 열기")
        opn.clicked.connect(lambda: self._open_folder(self._img_out_root()))
        fold.addWidget(opn)
        cv.addLayout(fold)
        where = QtWidgets.QLabel("저장 폴더 변경은 '설정' 탭에서 합니다.")
        where.setObjectName("muted")
        cv.addWidget(where)

        v.addWidget(card)
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
        # ① 판매수집 = 반자동만(보이는 신뢰 창 로그인). 무인 offscreen 방식은 차단에 취약해 폐지(사용자 요청).
        self.sales_semi_btn = QtWidgets.QPushButton("① 판매수집")
        self.sales_semi_btn.setToolTip(
            "보이는 Chrome 창을 띄우고 로그인(ID/비번 자동입력, 2차인증은 사람)한 뒤\n"
            "그 신뢰 창에서 판매수집합니다(반자동). 무인 오프스크린 자동로그인 차단을 피합니다.")
        self.sales_semi_btn.clicked.connect(lambda: self.do_run_full(keywords_off=True, sales_semi=True))
        top.addWidget(self.sales_semi_btn)
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
        self.pipeline_btn = QtWidgets.QPushButton("전체 실행(①반자동→②→③반자동)")
        self.pipeline_btn.setObjectName("accent")
        self.pipeline_btn.setToolTip("①판매수집(반자동 로그인) → ②키워드 선정(노출측정 없음) → ③순위(반자동 자동타이핑).\n"
                                     "오프스크린 공개검색을 안 써 차단을 피합니다. ③ 중 '반자동 중지'로 멈출 수 있습니다.")
        self.pipeline_btn.clicked.connect(lambda: self.do_run_full(keywords_off=False, sales_semi=True))
        top.addWidget(self.pipeline_btn)
        top.addStretch(1)
        rv.addLayout(top)
        desc = QtWidgets.QLabel(
            "계정마다 [로그인→판매분석→키워드→PC·모바일 순위]를 완결하고 통합 엑셀에 누적 저장합니다. "
            "로그인은 창 없이 자동, 2차인증 필요할 때만 창이 뜹니다(로그로 예고). 진행상황은 아래 로그에서 확인.")
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        rv.addWidget(desc)
        # 실행 모드 — 화면에서 3택(하나만 선택). 실행 시 예/아니오만 확인.
        moderow = QtWidgets.QHBoxLayout()
        moderow.addWidget(QtWidgets.QLabel("실행 모드:"))
        # 라디오버튼 = 하나만 선택(배타 그룹).
        self.cb_resume = QtWidgets.QRadioButton("이어서 하기")
        self.cb_resume.setChecked(True)
        self.cb_resume.setToolTip("오전에 하다 만 작업을 이어서 완료합니다(이미 끝낸 계정·상품은 건너뜀).\n"
                                  "어제까지 통계는 그대로 유지, 오늘 컬럼만 마저 채웁니다. [기본]")
        self.cb_redo = QtWidgets.QRadioButton("오늘 것만 다시 수집")
        self.cb_redo.setToolTip("오늘 수집한 것을 지우고 오늘 것만 처음부터 다시 수집합니다(완료분 포함 전부).\n"
                                "어제까지 통계·키워드는 그대로 유지됩니다.")
        self.cb_newall = QtWidgets.QRadioButton("통계 전체 초기화(백업 후)")
        self.cb_newall.setToolTip("⚠ 지금까지 전체 통계를 백업파일로 보관하고 완전히 빈 통계로 새로 시작합니다.\n"
                                  "누적 시계열이 끊깁니다 — 첫 수집이나 키워드 전면 재선정 때만 사용하세요.")
        self._mode_group = QtWidgets.QButtonGroup(self)   # 하나만 선택(상호배타)
        self._mode_group.setExclusive(True)
        for cb in (self.cb_resume, self.cb_redo, self.cb_newall):
            self._mode_group.addButton(cb)
            moderow.addWidget(cb)
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
        self.cb_today = QtWidgets.QRadioButton("당일(=어제, 최신 확정일)")
        self.cb_today.setToolTip("쿠팡 판매분석은 당일 데이터를 익일 이후 생성합니다.\n"
                                 "따라서 '당일'은 데이터가 확정된 어제(D-1) 날짜로 수집합니다.")
        self.cb_today.setChecked(True)
        self.cb_range = QtWidgets.QRadioButton("날짜 지정")
        self.cb_range.setToolTip("지정한 날짜 칸을 채웁니다(빈 칸만 — 이미 수집된 계정·순위는 건너뜀).\n"
                                 "판매 = 그 날짜의 전날 데이터 · 노출순위 = 지금 측정한 값.\n"
                                 "예: 10.10 에 10.09 지정 → 10.09 칸에 10/08 판매 + 지금 순위.")
        self._period_group = QtWidgets.QButtonGroup(self)   # 하나만 선택(상호배타)
        self._period_group.setExclusive(True)
        self._period_group.addButton(self.cb_today)
        self._period_group.addButton(self.cb_range)
        self.cb_today.toggled.connect(self._toggle_range)
        pbar.addWidget(self.cb_today)
        pbar.addWidget(self.cb_range)
        yday = (date.today() - timedelta(days=1)).isoformat()   # 기본값=어제 칸(중단된 어제 작업 채우기)
        self.to_edit = QtWidgets.QLineEdit(yday)          # 채울 날짜 칸(YYYY-MM-DD)
        self.to_edit.setMaximumWidth(120)
        pbar.addWidget(self.to_edit)
        hint = QtWidgets.QLabel("(그 날짜 칸에: 판매=전날 · 노출순위=지금 측정 · 빈 칸만)")
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

    def _save_shared(self, key: str, value: str) -> None:
        _cfg_save_shared(key, value)

    def log(self, msg: str):
        self.log_signal.emit(msg)   # 어느 스레드에서 불려도 GUI 스레드로 전달

    def _append_log(self, msg: str):
        color = _LOG_COLORS.get(self._log_tag(msg), "#e2e8f0")
        ts = config.log_ts()   # 표준 포맷 'YYYY-MM-DD HH:MM:SS.mmm'(config.format_log 과 동일 규칙)
        stamp = html.escape(f"[{ts}] ")
        safe = html.escape(msg).replace(" ", "&nbsp;")
        # 사용자가 위로 스크롤해 과거 로그를 보는 중이면 새 줄이 와도 맨 아래로 끌어내리지 않는다
        # (맨 아래에 있을 때만 따라 내려감 = 자동 팔로우). 이래야 로그 스크롤이 실제로 작동한다.
        sb = self.log_console.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4
        self.log_console.append(
            f'<span style="color:#64748b">{stamp}</span>'
            f'<span style="color:{color}">{safe}</span>')
        if at_bottom:
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
        """화면(최근 N줄)이 아니라 **실행 로그 파일 전체**를 복사한다.

        콘솔 위젯은 메모리 보호로 최근 config.UI_LOG_MAX_LINES 줄만 유지하지만, 전체 이력은 run_log
        파일에 남는다(회전 시 직전 세대 .log.1 포함). 이 둘을 이어 붙여 **모든 로그**를 클립보드에 넣는다.
        파일을 못 읽으면 화면 텍스트로 폴백."""
        parts = []
        for p in (self._log_path.with_suffix(".log.1"), self._log_path):   # 회전된 직전분 + 현재
            try:
                if p.exists():
                    parts.append(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        text = "".join(parts).strip() or self.log_console.toPlainText()
        QtWidgets.QApplication.clipboard().setText(text)
        self.log(f"[로그] 전체 복사됨 — {len(text.splitlines())}줄 (클립보드)")

    # ── 백그라운드 실행(스레드 → 시그널로 완료 전달) ───────────
    def _guard_busy(self) -> bool:
        """브라우저를 여는 실행이 이미 도는 중이면 True(호출부가 즉시 return) — 동시 실행 방지.

        같은 프로필로 WingBrowser 두 개가 열리면 프로필 잠금 충돌(ECONNRESET/포트 미개방)·중지 버튼
        오작동이 난다(CLAUDE.md: rank_browser와 로그인 브라우저 동시 개방 금지). Qt 클릭은 GUI 스레드
        단일 처리라 이 검사↔run_bg(_run_active 설정) 사이에 다른 클릭이 끼어들지 않는다(경쟁 없음)."""
        if getattr(self, "_run_active", False):
            self.log("[안내] 이미 실행 중입니다 — 지금 작업이 끝난 뒤 다시 눌러 주세요.")
            return True
        return False

    def _update_log_visibility(self):
        """진행 로그창 표시 규칙 — 첫 실행 전엔 숨김. 이후엔 표시하되, **설정 탭에서 유휴 상태면 숨김**
        (설정 탭의 실행이 도는 동안은 예외로 표시해 원장 반영·연결확인 결과를 볼 수 있게)."""
        panel = getattr(self, "log_panel", None)
        if panel is None:
            return
        on_settings = self.tabs.currentIndex() == 0
        visible = self._log_activated and (self._bg_active > 0 or not on_settings or self._settings_hold)
        panel.setVisible(visible)
        if visible and not self._log_sized:     # 첫 표시: 탭 ~400px, 나머지 로그
            self._log_sized = True
            total = max(self._splitter.height(), 600)
            self._splitter.setSizes([min(400, total // 2), total - min(400, total // 2)])

    def _on_tab_changed(self, *_):
        self._settings_hold = False             # 설정 탭을 떠나면 '결과 보이기' 유지 해제
        self._update_log_visibility()

    @staticmethod
    def _pipe_lock_path() -> str:
        """교차 프로세스 파이프라인 실행 잠금 — 열어둔 GUI 와 18:00 무인(--auto)이 **동시에** 파이프라인을
        돌려 마스터·계정이 충돌하는 것을 막는다. 유휴 GUI 는 잠금을 쥐지 않으므로 무인은 항상 실행된다."""
        d = app_output_dir() / "_잠금"
        d.mkdir(parents=True, exist_ok=True)
        return str(d / "파이프라인.lock")

    def run_bg(self, task, on_done=None, btn=None, exclusive=False, pipelinelock=False):
        lock_cm = None
        if pipelinelock:   # 계정 로그인·마스터 쓰기 실행 = 이 PC 전체에서 한 번에 하나(다른 창/무인과도 배타)
            from coupang_analytics.registry_lock import RegistryLockError, registry_lock
            lock_cm = registry_lock(self._pipe_lock_path(), wait_sec=0, on_log=self.log)
            try:
                lock_cm.__enter__()
            except RegistryLockError:
                self.log("[안내] 다른 창이나 무인 실행에서 파이프라인이 진행 중입니다 — 동시 실행을 막습니다. "
                         "끝난 뒤 다시 실행하세요.")
                if btn:
                    btn.setEnabled(True)
                if on_done is not None:        # 흐름 마무리 — 무인(--auto)은 이 경로로 정상 종료된다
                    self.finish_signal.emit(btn, on_done, None, None)
                return
        if exclusive:   # 브라우저/파이프라인 실행 = 한 번에 하나(배타). btn 은 그 실행의 소유 표식.
            self._run_active = True
            self._active_btn = btn
        self._bg_active += 1              # 진행 로그창 표시(실행 버튼 클릭 후부터)
        self._log_activated = True
        if self.tabs.currentIndex() == 0:  # 설정 탭 작업은 끝난 뒤에도 결과 로그를 보이게(탭 이동 시 해제)
            self._settings_hold = True
        self._update_log_visibility()
        if btn:
            btn.setEnabled(False)

        def worker():
            result, err = None, None
            try:
                result = task()
            except Exception as exc:
                err = exc
            finally:
                if lock_cm is not None:      # 실행 끝(성공·실패 무관)에 잠금 해제 — 프로세스 죽어도 OS 가 해제
                    try:
                        lock_cm.__exit__(None, None, None)
                    except Exception:
                        pass
            self.finish_signal.emit(btn, on_done, result, err)
        threading.Thread(target=worker, daemon=True).start()

    def _on_finish(self, btn, on_done, result, err):
        if btn:
            btn.setEnabled(True)
        self._bg_active = max(0, self._bg_active - 1)   # 진행 로그창 표시 갱신(설정 탭 유휴면 숨김)
        # 배타 실행(그 btn 이 소유)만 종료 처리 — 다른 빠른 작업이 파이프라인 도중 끝나도 중지 버튼을
        # 끄지 않는다(예전엔 무조건 껐음 → 파이프라인을 멈출 수 없던 버그).
        if btn is not None and btn is getattr(self, "_active_btn", None):
            self._run_active = False
            self._active_btn = None
            if getattr(self, "track_stop_btn", None) is not None:   # 이 배타 실행이 소유한 중지 버튼만 끔
                self.track_stop_btn.setEnabled(False)
        if err is not None:
            self.log(f"[오류] {err.__class__.__name__}: {err}")
        elif on_done is not None:
            on_done(result)
        self._update_log_visibility()   # 실행 종료 후 표시 갱신(설정 탭 유휴면 숨김)

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
        _cfg_save_shared("file/input", str(path))   # 무인 자동로드용(config.json + 레지스트리)

    def _set_input_list(self, il, label: str) -> None:
        """파싱된 InputList 를 UI 상태(상품목록·라벨·로그)에 반영. 파일/구글시트 공용."""
        self.input_list = il
        self._pw_cands = {}                 # 대장 비번 후보(로더가 채움·D-012) — 입력 바뀌면 초기화
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
        try:
            self._apply_pw_candidates(parse_password_candidates(read_xlsx_rows(path)))
        except Exception as exc:              # 비번 읽기 실패는 비치명(저장된 값으로 로그인·사유 명시)
            self.log(f"[비번] PC 엑셀 비밀번호 읽기 실패({exc.__class__.__name__}) — 저장된 비밀번호 사용")
        return True

    def _apply_pw_candidates(self, cands: dict) -> None:
        """관리대장 비번 후보 반영(매 로드 = 매 실행 대장과 비교·D-012). 첫 후보는 DPAPI 저장(빈 칸 계정은 기존 저장값 유지),
        한 계정 여러 줄의 값이 다르면 경고(행 번호·값 순서)하고 로그인 때 차례로 시도."""
        self._pw_cands = cands
        self._store_passwords_map({aid: c[0].password for aid, c in cands.items()}, quiet=True)
        for aid, cs in cands.items():
            if len(cs) > 1:
                order = " · ".join(f"값{k + 1}=행 {','.join(map(str, c.rows))}" for k, c in enumerate(cs))
                self.log(f"[비번] ⚠ {aid}: 관리대장 줄마다 비밀번호가 다름({order}) — 로그인 시 값1부터 차례로 시도"
                         "(최대 2개). 대장에서 이 계정 비밀번호를 한 값으로 맞춰 주세요")
            trimmed = sorted(r for c in cs for r in c.trimmed)
            if trimmed:   # D-018: 앞뒤 공백은 떼고 제출(대장 원문은 그대로라 정리 요청)
                self.log(f"[비번] ⚠ {aid}: 관리대장 행 {','.join(map(str, trimmed))} 비밀번호 앞뒤에 공백이 있어 "
                         "떼고 입력합니다. 대장에서 공백을 지워 주세요")

    def _on_input_source_changed(self, checked=True) -> None:
        """기본 입력 소스 라디오 변경 → input/source 영속(다음 시작 자동로드가 이 값을 따른다)."""
        if not checked:                 # 라디오 전환 시 꺼지는 쪽 신호는 무시(켜진 쪽만 1회 처리)
            return
        if self.src_registry_radio.isChecked():
            src, name = registry_ui.SOURCE_REGISTRY, "원장(관리중만)"
        elif self.src_gsheet_radio.isChecked():
            src, name = "gsheet", "구글시트 관리대장"
        else:
            src, name = "file", "PC 엑셀"
        _cfg_save_shared("input/source", src)
        self.log(f"[입력] 기본 입력 소스 = {name}"
                 + ("" if src == "gsheet" else " — 구글시트는 여전히 '관리대장에서 불러오기'로 수동 사용 가능"))

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

    def _apply_input_gsheet(self, url: str, persist: bool = True) -> bool:
        """관리대장 구글시트 → InputList 적용 + 비번 DPAPI 저장(수동/무인 공용). 실패는 예외로 올림.

        persist=False = 원장 로드 실패로 대신 읽는 경우 — 사용자가 고른 입력소스(원장)를 바꾸지 않는다."""
        title, rows, strike_grid = read_ledger_rows(url, store=self.creds_store)
        il = parse_input_rows(rows, strike_grid)
        self._set_input_list(il, f"[구글시트] {title}")
        self._apply_pw_candidates(parse_password_candidates(rows))
        if not persist:
            return True
        _cfg_save_shared("gsheet/input_url", url)
        _cfg_save_shared("input/source", "gsheet")   # 무인 자동로드가 구글시트를 우선하도록 표시
        if getattr(self, "src_gsheet_radio", None) is not None:
            self.src_gsheet_radio.setChecked(True)   # 기본 입력 소스 라디오도 구글시트로 동기화
        return True

    def _auto_load_input(self) -> bool:
        """입력 자동 로드(무인 실행·재시작 후): 소스=원장이면 원장에서(실패 시 로그 후 구글 관리대장),
        gsheet면 등록 링크에서, 아니면 마지막 PC 엑셀에서."""
        st = QtCore.QSettings("coupang-analytics", "ui")
        url = st.value("gsheet/input_url", "", type=str)
        src = st.value("input/source", "", type=str)
        if src == registry_ui.SOURCE_REGISTRY:
            reg_url = st.value(registry_ui.KEY_URL, "", type=str).strip()
            try:
                if not reg_url:
                    raise ValueError("원장 링크 미등록")
                return self._apply_input_registry(reg_url)
            except Exception as exc:
                self.log(f"== [입력] 원장 로드 실패 → 관리대장으로 전환: {exc.__class__.__name__}: {exc} ==")
        if src in ("gsheet", registry_ui.SOURCE_REGISTRY) and url:
            try:
                return self._apply_input_gsheet(url, persist=(src == "gsheet"))
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
        cs = getattr(self, "_pw_cands", {}).get(account_id) or []
        if len(cs) > 1:                       # 대장 줄마다 다른 값 → 후보 목록(파이프라인이 차례로 시도·D-012)
            return [c.password for c in cs]
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

    def load_holiday_key(self):
        """공휴일 API 키(data.go.kr 특일정보 서비스키) 입력 → DPAPI 저장(정산 지급일 계산용)."""
        key, ok = QtWidgets.QInputDialog.getText(
            self, "공휴일 API 키", "data.go.kr '한국천문연구원 특일정보' 서비스키(일반 인증키)를 입력하세요",
            QtWidgets.QLineEdit.Password)
        if not (ok and key.strip()):
            return
        try:
            self.creds_store.set_password(holiday_source.CRED_KEY, key.strip())
        except Exception as exc:
            self.log(f"[공휴일] 키 저장 실패({exc.__class__.__name__}): {exc}")
            return
        self.holiday_lbl.setText("(공휴일 API 키: 입력됨 — 저장됨)")
        self.log("[공휴일] API 키 입력·저장됨 — [연결 확인]으로 동작을 확인하세요")

    def check_holiday_key(self):
        """저장된 공휴일 키로 올해 공휴일 조회(네트워크) — 실패는 로그·라벨에 이유를 남긴다."""
        year = date.today().year
        self.log(f"[공휴일] {year}년 공휴일 조회로 키 확인 중…")

        def done(n):
            self.holiday_lbl.setText(f"(공휴일 API 키: 연결됨 — {year}년 공휴일 {n}일)")
            self.log(f"[공휴일] 연결 확인 OK — {year}년 공휴일 {n}일")
        self.run_bg(lambda: len(holiday_source.fetch_from_store(self.creds_store)(year)),
                    on_done=done, btn=self.holiday_chk_btn)

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
        key, who = _GS_LINKS[kind]
        url = self._gs_edits[kind].text().strip()
        if not url:
            QtWidgets.QMessageBox.information(self, "링크 필요", f"{who} 구글시트 링크를 먼저 입력하세요.")
            return
        # 편집 중 값도 즉시 저장(editingFinished 미발생 상태 대비)
        _cfg_save_shared(key, url)
        self._refresh_link_state(kind)
        try:
            title, sheets = gsheet_api.check_access(url, store=self.creds_store)
        except gsheet_api.GSheetError as exc:
            self._set_gs_status(kind, False, str(exc))
            QtWidgets.QMessageBox.warning(self, "연결 실패", str(exc))
            self.log(f"[구글] {who} 연결 실패: {exc}")
            return
        self._set_gs_status(kind, True, f"'{title}' (시트 {len(sheets)}개)")
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
        try:
            hk = self.creds_store.get_password(holiday_source.CRED_KEY)
        except Exception:
            hk = None
        if hk:
            self.holiday_lbl.setText("(공휴일 API 키: 저장됨 — 자동 로드)")

    # ── 키워드 추천 ───────────────────────────────────────────
    def do_recommend(self):
        if self._guard_busy():
            return
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
        self.run_bg(task, on_done=self._fill_kw, btn=self.kw_run_btn, exclusive=True)

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
        if self._guard_busy():
            return
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
            btn=self.rank_btn, exclusive=True)

    # ── 전체 실행 ─────────────────────────────────────────────
    def _toggle_range(self):
        self.to_edit.setEnabled(self.cb_range.isChecked())

    def _run_dates(self):
        """(판매조회_from, 판매조회_to, 컬럼라벨_실행날짜) 반환.

        쿠팡 판매분석은 당일 데이터를 익일 이후 생성 → **판매조회는 전일(D-1)**. 하지만 결과파일의
        **컬럼 제목은 실제 작업한 날(오늘=실행날짜)**로 적는다(순위는 오늘 측정이므로 라벨과 일치, 판매는
        전일 데이터가 그 컬럼에 함께 들어감). 새벽까지 이어져 날짜가 바뀌어도 이 값은 시작 시점에 한 번
        정해져 실행날짜 기준으로 고정된다. **날짜 지정**(소유자 2026-10-10)도 같은 규칙: 칸=지정일, 판매=그 전날,
        순위=지금 측정(그 칸에 기록)·빈 칸만 채움."""
        label = date.today().isoformat() if self.cb_today.isChecked() else self.to_edit.text().strip()
        return column_dates(label)   # (판매=전날, 판매=전날, 칸=label) — 형식 오류는 ValueError

    def _require_run_inputs(self) -> bool:
        """전체실행/판매수집 전 필수 입력·키 확인 — 없으면 경고 후 False."""
        if self.input_list is None:
            QtWidgets.QMessageBox.warning(self, "입력 필요", "설정 탭에서 입력 엑셀을 먼저 여세요.")
            return False
        if self.naver_creds is None:
            QtWidgets.QMessageBox.warning(self, "키 필요", "설정 탭에서 네이버 API 키를 먼저 여세요.")
            return False
        if not self.ai_key:
            QtWidgets.QMessageBox.warning(self, "키 필요", "키워드 추출에 OpenAI(ChatGPT) API 키가 필요합니다.")
            return False
        return True

    def do_run_full(self, keywords_off: bool = False, sales_semi: bool = False):
        if self._guard_busy():
            return
        if not self._require_run_inputs():
            return
        try:
            df, dt, dlabel = self._run_dates()
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "날짜 형식", "날짜는 YYYY-MM-DD 로 입력하세요(예: 2026-10-09).")
            return
        skip_ranks = False   # 날짜 지정도 순위 포함(지금 측정값을 그 칸에·소유자 2026-10-10)
        n = sum(len(a.products) for a in self.input_list.accounts)
        title = run_title(keywords_off, sales_semi)
        # 실행 모드 3택 → 여기선 예/아니오만 확인.
        #  · ① 이어서 하기: 오늘 진행분 있으면 이어서(완료 계정 건너뜀), 아니면 마스터에 오늘 컬럼 추가.
        #  · ② 오늘 처음(다시): carry_forward + redo_today → 오늘 컬럼·완료스탬프 초기화 후 전 계정 재수집(어제까지 유지).
        #  · ③ 전체 새로 시작: carry_forward=False → 기존 마스터 백업 후 빈 통계로 새로.
        newall = self.cb_newall.isChecked()
        redo = self.cb_redo.isChecked()
        # fix ③: 마스터가 없지만 결과 구글시트가 있으면(다른 PC·재설치) 통째로 복원 → '첫 실행' 오판으로
        # 과거 통계(날짜 컬럼)를 유실하지 않는다. '통계 전체 초기화(newall)'는 의도적 초기화라 복원하지 않는다.
        gs_out = QtCore.QSettings("coupang-analytics", "ui").value("gsheet/output_url", "", type=str).strip()
        if not newall and not master_exists() and gs_out:
            self.log("[통계] 마스터가 없어 결과 구글시트에서 복원을 시도합니다…")
            restore_master_from_gsheet("output", gs_out, self.log)
        meta = resumable_progress() if not (newall or redo) else None   # 이어서만 오늘 진행분 재개
        plan = plan_run_mode(newall, redo, meta, master_exists(), df, dt, dlabel,   # 실행모드 결정(백엔드 공통)
                             designated=not self.cb_today.isChecked())
        resume, carry, redo_today = plan.resume, plan.carry, plan.redo_today
        df, dt, mode_desc = plan.date_from, plan.date_to, plan.mode_desc
        dlabel = plan.date_label   # 재개 시 시작일 기준 날짜라벨 복원(백엔드 공통·app.py와 동일 동작)
        grow = carry and not redo_today and self.cb_grow.isChecked()   # 발굴 추가는 이어쓰기 때만
        # 단일 확인 팝업 — 실행 여부(예/아니오)만.
        confirm = (f"{mode_desc}\n대상: 상품 {n}개"
                   f"{' · 새 키워드 발굴 추가' if grow else ''}\n\n실행할까요?")
        if QtWidgets.QMessageBox.question(self, f"{title} 확인", confirm) != QtWidgets.QMessageBox.Yes:
            self.log(f"[{title}] 취소됨")
            return
        input_list, naver_creds, key = self.input_list, self.naver_creds, self.ai_key
        mode_txt, stage_txt = run_log_labels(keywords_off, resume, redo_today, carry, skip_ranks)
        self.log(f"[{'판매수집' if keywords_off else '전체실행'}] {mode_txt}시작 — 상품 {n}개, 기간 {df}~{dt}"
                 f"{' · 새 키워드 발굴 추가' if grow else ''}{stage_txt}")
        btn = self.sales_semi_btn if keywords_off else self.pipeline_btn
        self.log("[① 반자동] 보이는 창에서 로그인(2차인증은 직접) 후 판매수집합니다 — 창이 뜨면 두세요")
        # 전체실행은 오프스크린을 전혀 안 쓴다: ①반자동 판매수집 → ②키워드선정(노출측정 없음) → ③반자동 순위.
        stop = None
        if not keywords_off:
            self._semi_stop = threading.Event()
            self.track_stop_btn.setEnabled(True)
            stop = self._semi_stop

        gs_in = QtCore.QSettings("coupang-analytics", "ui").value("gsheet/input_url", "", type=str).strip()
        designated = not self.cb_today.isChecked()   # 날짜 지정(D-016) — 이력 없는 옛 칸은 판매값으로 수집 판정(D-019)

        self.run_bg(lambda: self._full_pipeline_task(
            input_list, naver_creds, key, df, dt, dlabel, resume, carry, redo_today,
            grow, keywords_off, gs_in, gs_out, stop, designated),
            on_done=self._pipeline_done, btn=btn, exclusive=True, pipelinelock=True)

    def _full_pipeline_task(self, input_list, naver_creds, key, df, dt, dlabel, resume, carry,
                            redo_today, grow, keywords_off, gs_in, gs_out, stop, designated=False):
        """전체실행/판매수집 백그라운드 작업 — ①반자동 판매수집 → ②키워드선정 → ③반자동 순위(offscreen 전무).

        재부팅 복구용 단계마커(write_run_stage)와 그로스 재고 역기록(push_ledger_inventory)까지 포함.
        인자는 do_run_full 시점의 스냅샷(실행 중 self.* 변경에 영향받지 않음 — 행동 불변)."""
        backup_sources(input_url=gs_in, output_url=gs_out, on_log=self.log)   # 작업 전 원본 백업(항상)
        input_list, reg_url = self._registry_presync(input_list, gs_in)   # 원장 자동 반영(비치명·2-1)
        naver = NaverAdApi(naver_creds)
        stock_url = self._stock_url()           # 회사보유재고 재고현황 링크(계정목록 표기 + 대장 역기록 공용)
        # ① 반자동 판매수집 — 순위·키워드·노출측정 전무(offscreen 미사용)
        snap = run_full(input_list, ai_key=key, date_from=df, date_to=dt,
                        get_password=self._account_pw, resume=resume, carry_forward=carry,
                        redo_today=redo_today, sales_semi=True, date_label=dlabel, on_log=self.log,
                        gsheet_output_url=gs_out, registry_url=reg_url, stock_url=stock_url,
                        designated=designated)
        if keywords_off:                        # ① 단독 실행 → 판매데이터만 채우고 종료
            return snap
        write_run_stage("sales")                # ① 완료 표시(재부팅 복구: 여기부턴 ②③만)
        if stop is not None and stop.is_set():
            return snap
        # ② 키워드 선정 — 공개검색(노출측정) 없이 AI 선정만(로그인 불필요·동결분 유지)
        self.log("[전체실행] ② 키워드 선정 — 노출측정 없이 AI 선정(동결분 유지)")
        select_keywords_stage(naver, key, grow=grow, on_log=self.log, gsheet_output_url=gs_out,
                              stock_url=stock_url)
        write_run_stage("ranks")                # ② 완료 표시(재부팅 복구: 여기부턴 ③만)
        if stop is not None and stop.is_set():
            return snap
        # ③ 반자동 순위 — 보이는 창에서 자동 타이핑·검색(차단 회피)
        self.log("[전체실행] ③ 반자동 순위 — 보이는 창 자동 타이핑(중지: '반자동 중지')")
        result = track_ranks_stage(should_stop=(stop.is_set if stop is not None else (lambda: False)),
                                   on_log=self.log, gsheet_output_url=gs_out, stock_url=stock_url,
                                   date_label=dlabel)   # ①과 같은 날짜 칸에(날짜 지정·재개 라벨 일치)
        # 입력 관리대장의 '그로스 재고'(AD) 컬럼을 수집 재고로 역기록(SA 편집권한 필요·없으면 로그 후 비치명)
        push_ledger_inventory(gs_in, self.log)   # gs_in = 위에서 정의(백업·역기록 공용)
        push_company_stock(self._stock_url(), gs_in, self.log)   # 회사보유재고(판매자배송) 역기록(비치명)
        if not (stop is not None and stop.is_set()):
            write_run_stage("done")             # 전부 완료 표시(재부팅 복구 안 함)
        return result

    # ── 무인 자동 실행(--auto, 18:00 시작 → **모든 처리 완주 후 종료**·강제종료 없음) ───────
    def start_auto(self):
        """무인 자동 실행 — 팝업 없이 **①반자동 판매수집 → ②키워드선정 → ③반자동 순위**, **모든 처리 완주 후에만 종료**(강제종료 없음).

        무인이어도 **처리 방식은 전부 반자동**(전체실행과 동일 조합·offscreen 전무): ①은 보이는 신뢰 창에서
        자동입력 로그인(Akamai 통과율↑), ②는 로그인 없이 쿠팡 자동완성+네이버+AI 선정, ③은 autosubmit 순위.
        사람 개입 0 전제: 입력·키 자동 로드, 확인 팝업 없음, 로그인 차단·2차인증 계정은 건너뜀(멈추지 않음),
        차단 시 쿨다운/자동재개. 절전은 실행 동안 방지. (2차인증은 사무실=신뢰 IP면 없이 통과.)
        """
        self.log("== [무인 자동 실행] 시작 ==")
        _prevent_sleep(True)
        if self.input_list is None:
            # 입력 자동 로드(_auto_load_input)가 구글시트·PC엑셀 모두 실패 → 바로 종료. 위에 이미 사유 로그가 있다
            # (예: 구글시트 403/404). 구글시트 사용자인데 "입력 엑셀이 없어"만 보여 혼동되던 것을 명확히 한다.
            self.log("[무인] 입력을 불러오지 못해 실행 불가(구글시트·PC엑셀 모두 실패) — "
                     "위 로그의 '입력 … 로드 실패' 사유를 확인하세요(구글시트 링크·서비스계정 편집 공유 또는 PC 엑셀). 종료")
            return self._auto_quit()
        if self.naver_creds is None or not self.ai_key:
            self.log("[무인] 네이버/OpenAI 키 미설정 — 설정 후 재시도. 종료")
            return self._auto_quit()
        # ⚠ 06:00 강제 종료 폐지(소유자 2026-09-23): **어떤 경우에도 강제 종료 금지 — 모든 처리(①②③+재고
        # 역기록)가 끝난 뒤에만 _auto_done 으로 종료**한다. 순위·로그인 단계는 자체 서킷브레이커(쿨다운 MAX·
        # 연속차단)로 스스로 끝나므로 무한 대기하지 않는다. (예전 _schedule_auto_stop 은 06:00에 순위를 중간에
        # 끊고 60초 뒤 강제 종료했다 — 미처리분 발생·소유자 불가 판정.) 절전만 실행 동안 방지.
        df, dt, dlabel = self._run_dates()         # 판매조회=어제(D-1) · 컬럼라벨=실행날짜(오늘)
        meta = resumable_progress()
        resume = bool(meta)
        gs_out = QtCore.QSettings("coupang-analytics", "ui").value("gsheet/output_url", "", type=str).strip()
        # fix ③: 마스터가 없지만 결과 구글시트가 있으면 복원(무인이라 팝업 없이 자동) → 첫 실행 오판·과거 통계 유실 방지.
        if not resume and not master_exists() and gs_out:
            self.log("[무인] 마스터가 없어 결과 구글시트에서 복원을 시도합니다…")
            restore_master_from_gsheet("output", gs_out, self.log)
        carry = bool(meta.get("carry", False)) if meta else master_exists()
        if resume:
            df, dt = meta["date_from"], meta["date_to"]
            dlabel = meta.get("date_label") or dlabel
        self._semi_stop = threading.Event()
        n = sum(len(a.products) for a in self.input_list.accounts)
        self.log(f"[무인] ①반자동 판매수집 → ②키워드선정 → ③반자동 순위 · 상품 {n}개 · 기간 {df}~{dt} · "
                 f"{'이어서' if resume else ('이어쓰기' if carry else '새 통계')}")
        il, naver_creds, key, stop = self.input_list, self.naver_creds, self.ai_key, self._semi_stop
        gs_in = QtCore.QSettings("coupang-analytics", "ui").value("gsheet/input_url", "", type=str).strip()

        def task():
            try:
                backup_sources(input_url=gs_in, output_url=gs_out, on_log=self.log)   # 작업 전 원본 백업(항상)
                run_il, reg_url = self._registry_presync(il, gs_in)   # 원장 자동 반영(비치명·2-1)
                naver = NaverAdApi(naver_creds)
                stock_url = self._stock_url()      # 회사보유재고 재고현황 링크(계정목록 표기 + 대장 역기록 공용)
                # ① 반자동 판매수집(무인이어도 **처리 방식은 반자동** — 보이는 신뢰 창·실제 타이핑으로 Akamai 통과율↑).
                #    2차인증은 사무실(신뢰 IP)이면 없이 통과; 낯선 환경서 뜨면 사람이 없어 그 계정만 건너뜀(멈춤 없음).
                #    판매만(키워드·순위·노출측정 없음) → 이어서 ②③. 전체실행과 동일 조합(offscreen 전무).
                run_full(run_il, ai_key=key, date_from=df, date_to=dt,
                         get_password=self._account_pw, resume=resume, carry_forward=carry,
                         sales_semi=True, date_label=dlabel, on_log=self.log, gsheet_output_url=gs_out,
                         registry_url=reg_url, stock_url=stock_url)
                # 야간 1회 쿨다운-재개: 차단 등으로 미완료 계정이 남았으면(진행중 파일 잔존) 30분 쉬고
                # **남은 계정만 1회 더** 시도(제출 총량 억제 = 위탁계정 잠금 방지, 무한 재시도 금지). 역시 반자동.
                if (not stop.is_set() and config.LOGIN_NIGHT_RESUME and resumable_progress()):
                    mins = config.LOGIN_NIGHT_RESUME_COOLDOWN_SEC // 60
                    self.log(f"[무인] 차단 등 미완료 계정 남음 → {mins}분 쿨다운 후 1회 재개(남은 계정만)")
                    _interruptible_sleep(config.LOGIN_NIGHT_RESUME_COOLDOWN_SEC, stop.is_set,
                                         self.log, resume_label=" — 로그인 재개")
                    if not stop.is_set():
                        self.log("[무인] 쿨다운 종료 — 미완료 계정 로그인 재개(1회)")
                        run_full(run_il, ai_key=key, date_from=df, date_to=dt,
                                 get_password=self._account_pw, resume=True, carry_forward=carry,
                                 sales_semi=True, date_label=dlabel, on_log=self.log, gsheet_output_url=gs_out,
                                 registry_url=reg_url, stock_url=stock_url)
                if not stop.is_set():
                    write_run_stage("sales")       # ① 완료 표시(재부팅 복구용·정산이 이 기록을 보고 받기 시작 D-021)
                # ② 키워드 선정(노출측정 없음·로그인 불필요·부족분 4개까지 보충)
                if not stop.is_set():
                    select_keywords_stage(naver, key, grow=False, on_log=self.log, gsheet_output_url=gs_out,
                                          stock_url=stock_url)
                    write_run_stage("ranks")       # ② 완료 표시(재부팅 복구: 여기부턴 ③만)
                # ③ 반자동 순위(autosubmit, 차단 시 쿨다운-재개)
                if not stop.is_set():
                    track_ranks_stage(should_stop=stop.is_set, on_log=self.log,
                                      gsheet_output_url=gs_out, stock_url=stock_url)
                # 입력 관리대장의 '그로스 재고'(AD) 컬럼을 수집 재고로 역기록(SA 편집권한 필요·없으면 비치명)
                if not stop.is_set():
                    push_ledger_inventory(gs_in, self.log)   # gs_in = 위에서 정의(백업·역기록 공용)
                    push_company_stock(self._stock_url(), gs_in, self.log)   # 회사보유재고 역기록(비치명)
                    write_run_stage("done")        # 전부 완료 표시
                # (결과는 구글 시트 통합으로 결과시트에 직접 반영 — rclone 업로드 제거)
            except Exception as exc:                # 무인: 어떤 오류도 앱을 매달아두지 않게 로그 후 종료로
                self.log(f"[무인] 실행 중 오류: {exc.__class__.__name__}: {exc}")
            return None
        self.run_bg(task, on_done=self._auto_done, btn=None, pipelinelock=True)

    def _auto_done(self, _result=None):
        self.log("== [무인 자동 실행] 완료 — 종료 ==")
        self._auto_quit()

    def _auto_quit(self):
        mark_app_finished()   # D-020: 무인이 스스로 끝남 → 정산은 계속(17:55 까지). 사람이 끄면 이 표시 없음 → 함께 종료
        _prevent_sleep(False)
        QtWidgets.QApplication.quit()

    # ── 재부팅 복구(--resume): 재부팅으로 끊긴 '오늘 작업'만 이어서(없으면 조용히 종료) ──
    def start_resume(self):
        """재부팅 후 자동 실행 — 오늘 중단된 전체실행/무인 작업이 있으면 **판매수집은 건너뛰고 순위부터**
        이어서 완료한다(없으면 아무것도 안 하고 종료). 작업 스케줄러 '로그온 시' 트리거가 부른다.

        판단: `read_run_stage()`(단계 마커)와 `resumable_progress()`(①판매 진행중 파일)로 어디까지 했는지 본다.
          - 진행중 파일 있음 = ① 판매수집 중단 → ①부터 이어서(완료계정 건너뜀) + ②③.
          - 마커 'sales'  = ①만 끝남 → ②③.
          - 마커 'ranks'  = ②까지 끝남 → ③만.
          - 마커 'done'/없음 & 진행중 없음 = 이어서 할 것 없음 → 종료.
        재부팅 후 Windows 자동 로그인이 켜져 있어야 이 창(세션)이 떠서 동작한다(반자동은 잠긴 세션도 가능).
        """
        marker = read_run_stage()
        prog = resumable_progress()
        stage = marker.get("stage") if marker else None
        if not prog and (stage is None or stage == "done"):
            self.log("[재부팅 복구] 오늘 이어서 할 중단 작업이 없습니다 — 종료")
            return self._auto_quit()
        if self.input_list is None:
            self.log("[재부팅 복구] 입력 엑셀/관리대장이 없어 이어서 불가 — 종료")
            return self._auto_quit()
        if self.naver_creds is None or not self.ai_key:
            self.log("[재부팅 복구] 네이버/OpenAI 키 미설정 — 종료")
            return self._auto_quit()

        _prevent_sleep(True)   # 06:00 강제 종료 폐지(소유자 2026-09-23) — 이어서 하는 작업도 완주 후에만 종료
        self._semi_stop = threading.Event()
        stop = self._semi_stop
        df, dt, dlabel = self._run_dates()
        if prog:                                   # ①판매 진행중 = 원래 작업 실행날짜 라벨 유지(새벽 재부팅에도 시작일 기준)
            dlabel = prog.get("date_label") or dlabel
        carry = master_exists()
        il, naver_creds, key = self.input_list, self.naver_creds, self.ai_key
        gs_out = QtCore.QSettings("coupang-analytics", "ui").value("gsheet/output_url", "", type=str).strip()
        gs_in = QtCore.QSettings("coupang-analytics", "ui").value("gsheet/input_url", "", type=str).strip()

        do_sales = bool(prog)                      # 판매수집 진행중이면 ①부터 이어서(완료계정 건너뜀)
        do_keywords = do_sales or stage == "sales"  # ①했거나 마커가 'sales'면 ②부터, 'ranks'면 ③만
        self.log(f"== [재부팅 복구] 오늘 중단분 이어서 — 단계마커={stage!r}, 판매진행중={bool(prog)} → "
                 f"{'①판매+' if do_sales else ''}{'②키워드+' if do_keywords else ''}③순위 ==")

        def task():
            try:
                backup_sources(input_url=gs_in, output_url=gs_out, on_log=self.log)   # 작업 전 원본 백업(항상)
                run_il, reg_url = self._registry_presync(il, gs_in)   # 원장 자동 반영(비치명·2-1)
                naver = NaverAdApi(naver_creds)
                stock_url = self._stock_url()      # 회사보유재고 재고현황 링크(계정목록 표기 + 대장 역기록 공용)
                if do_sales:                       # ① 판매수집 이어서(반자동·완료계정 건너뜀)
                    run_full(run_il, ai_key=key, date_from=df, date_to=dt,
                             get_password=self._account_pw, resume=True, carry_forward=carry,
                             sales_semi=True, date_label=dlabel, on_log=self.log, gsheet_output_url=gs_out,
                             registry_url=reg_url, stock_url=stock_url)
                    if not stop.is_set():
                        write_run_stage("sales")
                if not stop.is_set() and do_keywords:   # ② 키워드 선정(동결분 유지·부족분만)
                    select_keywords_stage(naver, key, grow=False, on_log=self.log, gsheet_output_url=gs_out,
                                          stock_url=stock_url)
                    if not stop.is_set():
                        write_run_stage("ranks")
                if not stop.is_set():              # ③ 반자동 순위(이미 채워진 순위는 건너뜀)
                    track_ranks_stage(should_stop=stop.is_set, on_log=self.log,
                                      gsheet_output_url=gs_out, stock_url=stock_url)
                if not stop.is_set():              # 마무리: 그로스 재고 역기록 + 완료 표시
                    push_ledger_inventory(gs_in, self.log)
                    push_company_stock(self._stock_url(), gs_in, self.log)   # 회사보유재고 역기록(비치명)
                    write_run_stage("done")
            except Exception as exc:               # 복구도 무인이라 어떤 오류도 매달지 않고 로그 후 종료
                self.log(f"[재부팅 복구] 실행 중 오류: {exc.__class__.__name__}: {exc}")
            return None
        self.run_bg(task, on_done=self._auto_done, btn=None, pipelinelock=True)

    def do_select_keywords(self):
        """② 키워드 선정 — 로그인 불필요. 최신 결과 워크북 상품에 키워드만 채운다(순위 없음)."""
        if self._guard_busy():
            return
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
        gs_out = QtCore.QSettings("coupang-analytics", "ui").value("gsheet/output_url", "", type=str).strip()
        self.log("[키워드 선정] 시작 — 순위 조회 없이 키워드만 선정(로그인 불필요)")

        stock_url = self._stock_url()
        def task():
            backup_sources(output_url=gs_out, on_log=self.log)   # 작업 전 원본 백업(항상)
            return select_keywords_stage(NaverAdApi(naver_creds), key, grow=grow, on_log=self.log,
                                         gsheet_output_url=gs_out, stock_url=stock_url)
        self.run_bg(task, on_done=self._pipeline_done, btn=self.kw_btn, exclusive=True, pipelinelock=True)

    def do_track_ranks(self, semi: bool = True):
        """③ 노출순위 조회(반자동) — 로그인 불필요. 앱이 창을 띄우고 키워드를 안내, 사용자가 직접
        검색하면 그 화면을 읽어 기록한다(자동 검색을 안 해 차단이 안 생김). 자동 방식은 차단 위험으로 폐지.
        """
        if self._guard_busy():
            return
        if not (master_exists() or resumable_progress()):
            QtWidgets.QMessageBox.warning(self, "먼저 ①②",
                                          "결과 파일이 없습니다. ① 판매수집·② 키워드 선정을 먼저 실행하세요.")
            return
        try:   # '날짜 지정'이면 그 칸에(빈 칸만), '오늘'이면 기존대로 가장 최근 칸
            rank_label = None if self.cb_today.isChecked() else column_dates(self.to_edit.text().strip())[2]
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "날짜 형식", "날짜는 YYYY-MM-DD 로 입력하세요(예: 2026-10-09).")
            return
        self._semi_stop = threading.Event()
        self.track_stop_btn.setEnabled(True)
        self.log("[반자동 순위] 시작 — 뜬 창에서 로그에 안내되는 키워드를 직접 검색하세요(중지: '반자동 중지')"
                 + (f" · 기록 칸 {rank_label}(지정)" if rank_label else ""))
        should_stop = self._semi_stop.is_set
        gs_out = QtCore.QSettings("coupang-analytics", "ui").value("gsheet/output_url", "", type=str).strip()

        stock_url = self._stock_url()
        def task_semi():
            backup_sources(output_url=gs_out, on_log=self.log)   # 작업 전 원본 백업(항상)
            return track_ranks_stage(should_stop=should_stop, on_log=self.log,
                                     gsheet_output_url=gs_out, stock_url=stock_url, date_label=rank_label)
        self.run_bg(task_semi, on_done=self._pipeline_done, btn=self.track_semi_btn, exclusive=True, pipelinelock=True)

    def _stop_semi(self):
        """반자동 순위 중지 요청 — 현재 키워드까지만 처리하고 멈춤(진행분은 저장됨)."""
        ev = getattr(self, "_semi_stop", None)
        if ev is not None:
            ev.set()
            self.log("[반자동 순위] 중지 요청 — 현재 키워드 처리 후 멈춥니다")
        self.track_stop_btn.setEnabled(False)

    # ── 상세 이미지(반자동) ────────────────────────────────────
    def _img_out_root(self) -> str:
        """상세이미지 저장 루트(QSettings 영속). 기본 = <기준폴더>/output/상세이미지."""
        st = QtCore.QSettings("coupang-analytics", "ui")
        default = str(app_output_dir() / "상세이미지")
        return st.value("dir/detail_images", default, type=str) or default

    def _img_change_dir(self):
        start = self._img_out_root()
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "상세이미지 저장 폴더 선택", start)
        if d:
            QtCore.QSettings("coupang-analytics", "ui").setValue("dir/detail_images", d)
            for lbl in (self.img_dir_lbl, self.img_dir_set_lbl):   # 상세 이미지 탭 표시 + 설정 탭
                lbl.setText(d)

    def _open_folder(self, path: str):
        """폴더를 탐색기로 연다(없으면 생성). 파일 다운로드가 아니라 로컬 폴더 열기라 안전."""
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            os.startfile(path)   # Windows 전용(앱이 Windows 데스크톱 GUI)
        except Exception as exc:
            self.log(f"[상세이미지] 폴더 열기 실패({exc.__class__.__name__}: {exc})")

    @staticmethod
    def _port_open(port: int) -> bool:
        """localhost 포트가 열려 있는지(=디버그 Chrome 이 이미 떠 있는지) 빠르게 확인."""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(("127.0.0.1", port)) == 0

    def do_img_launch_chrome(self):
        """상세이미지용 Chrome 을 디버그포트로 실행(전용 프로필·영속). 이미 떠 있으면 안내만."""
        if self._port_open(_IMG_CDP_PORT):
            self.log(f"[상세이미지] 쿠팡용 크롬이 이미 실행 중입니다(포트 {_IMG_CDP_PORT}). "
                     "그 창에서 상품을 열고 '이미지 추출'을 누르세요.")
            return
        from coupang_analytics.browser import _kill_profile_chrome
        import subprocess
        profile = str(Path(_IMG_PROFILE).resolve())   # 보존 폴더(프로젝트 루트)/data/chrome-images (CWD=루트)
        try:
            Path(profile).mkdir(parents=True, exist_ok=True)
            killed = _kill_profile_chrome(profile)   # 그 프로필 잔여 Chrome 정리(포트 미개방 방지)
            if killed:
                self.log(f"[상세이미지] 이 프로필의 잔여 Chrome {killed}개 정리")
            args = [
                find_chrome(),
                f"--remote-debugging-port={_IMG_CDP_PORT}",
                f"--user-data-dir={profile}",
                "--no-first-run", "--no-default-browser-check",
                "--disable-session-crashed-bubble", "--hide-crash-restore-bubble",
                "--disable-features=InfiniteSessionRestore",
                "about:blank",
            ]
            subprocess.Popen(args)
            self.log(f"[상세이미지] 쿠팡용 크롬을 띄웠습니다(포트 {_IMG_CDP_PORT}). "
                     "처음이면 쿠팡 로그인 후, 상품 상세페이지를 열고 '이미지 추출'을 누르세요.")
        except Exception as exc:
            self.log(f"[상세이미지][오류] 크롬 실행 실패: {exc.__class__.__name__}: {exc}")

    def do_img_extract(self):
        """디버그포트로 떠 있는 내 Chrome 에 붙어(CDP) 현재 상품 탭에서 이미지 추출(1회, 백그라운드)."""
        if not self._port_open(_IMG_CDP_PORT):
            QtWidgets.QMessageBox.information(
                self, "먼저 쿠팡용 크롬 실행",
                "'쿠팡용 크롬 실행'으로 크롬을 띄우고, 그 창에서 상품 상세페이지를 연 뒤 추출하세요.")
            return
        out_root = self._img_out_root()
        cdp_url = f"http://127.0.0.1:{_IMG_CDP_PORT}"
        self.log("[상세이미지] 내 Chrome 세션에 붙어 현재 상품 탭에서 추출 중...")

        def task():
            return detail_images.extract_via_cdp(cdp_url, out_root, log=self.log)
        self.run_bg(task, on_done=self._img_extract_done, btn=self.img_extract_btn)

    def _img_extract_done(self, res):
        """[GUI 스레드] 추출 결과 로그 + 저장폴더 열기."""
        if res is None:
            return
        if res.gallery or res.detail:
            self.log(f"[상세이미지] ✅ '{res.title[:40]}' — 대표 {len(res.gallery)} · "
                     f"상세 {len(res.detail)}장 저장(실패 {res.skipped}) → {res.out_dir}")
            self._open_folder(res.out_dir)
        else:
            self.log("[상세이미지] 추출된 이미지가 없습니다 — 상품 상세페이지가 열려 있는지 확인하세요.")

    def _pipeline_done(self, path):
        self.log("=" * 50)
        if path:
            self.log("[전체실행] ✅ 완료 — 통합 엑셀 생성됨")
            self.log(f"[전체실행] 파일: {path}")
        else:
            self.log("[전체실행] ⏹ 종료(중지 요청 또는 결과 없음) — 진행분은 저장됨")
        self.log("=" * 50)



def _check_icon_path() -> str:
    """흰색 체크마크 PNG를 임시폴더에 1회 생성하고 경로(슬래시)를 반환 — 체크박스 선택 시 표시 이미지.

    QSS는 data URI를 못 받으므로 런타임 생성 파일을 참조한다. 생성 실패 시 ""(파란 채움만·체크 없음).
    QApplication 생성 후(QPixmap 사용 가능) 호출할 것.
    """
    try:
        path = Path(QtCore.QDir.tempPath()) / "coupang_check.png"
        s = 18
        pm = QtGui.QPixmap(s, s)
        pm.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        pen = QtGui.QPen(QtGui.QColor("#ffffff"))
        pen.setWidthF(2.2)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        pen.setJoinStyle(QtCore.Qt.RoundJoin)
        p.setPen(pen)
        p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(4, 9.5), QtCore.QPointF(7.5, 13), QtCore.QPointF(14, 5)]))
        p.end()
        pm.save(str(path), "PNG")
        return str(path).replace("\\", "/")
    except Exception:
        return ""


# ── 설정 이식(배포 패키지 무설정용) — 이 PC 설정을 내보내고, 새 PC에서 가져와 자동 적용 ──────
# 담는 값: QSettings(구글시트 링크·입력소스) + credstore 키 4개(네이버·OpenAI·구글SA·공휴일).
# ⚠ 내보낸 파일은 **평문**(API/SA 키 포함) → 배포 zip 안에서만·설치 시 즉시 이 PC용 암호화(DPAPI) 후 삭제.
# 계정 비밀번호는 담지 않는다(관리대장 '비밀번호' 컬럼에서 매 실행 자동 로드).
_KEY_RANK_MIN, _KEY_RANK_MAX = "rank/nav_delay_min", "rank/nav_delay_max"   # 순위 검색 간격(초·정수)
_EXPORT_QKEYS = ("gsheet/input_url", "gsheet/output_url", "input/source", "registry/url", "stock/url",
                 _KEY_RANK_MIN, _KEY_RANK_MAX)
_EXPORT_CREDS = ("__naver__", "__openai__", "__gsheet_sa__", holiday_source.CRED_KEY)
# config.json(보존 폴더)에 두는 **공유 설정** 키 — 무인/양쪽 UI 공통(구글시트 링크·입력소스·마지막 입력파일).
# dir/*(마지막 폴더)는 per-PC UI 편의라 레지스트리에만 둔다.
_CONFIG_SHARED_KEYS = ("gsheet/input_url", "gsheet/output_url", "input/source", "file/input", "registry/url",
                       "stock/url", _KEY_RANK_MIN, _KEY_RANK_MAX)


def _cfg_save_shared(key: str, value: str) -> None:
    """공유 설정을 **config.json + 레지스트리** 양쪽에 저장(파일이 권위·레지스트리는 호환 병행)."""
    try:
        appconfig.set(key, value)
    except Exception:
        pass
    st = QtCore.QSettings("coupang-analytics", "ui")
    st.setValue(key, value)
    st.sync()   # 즉시 디스크 flush — config.json 이 지워져도(재빌드 등) QSettings 가 최신값 보존(2026-10-05)


def _sync_config_and_registry() -> None:
    """시작 시 1회: **config.json(보존 폴더)** 을 설정 권위로 삼아 레지스트리와 맞춘다.

    - config.json 이 있으면 그 값을 레지스트리에 반영(파일 편집·다른 PC 이식이 그대로 먹히게).
    - 없으면 레지스트리의 공유 키로 config.json 을 만든다(기존 사용자 자동 이관 + 루트 표식 생성).
    UI(설정 카드)·무인 자동로드가 읽는 QSettings 를 config.json 과 일치시켜, 읽기 코드는 그대로 둔다."""
    st = QtCore.QSettings("coupang-analytics", "ui")
    cfg = appconfig.load()
    if cfg:
        for k, v in cfg.items():
            if isinstance(v, str) and v:
                st.setValue(k, v)
        st.sync()
    else:
        seed = {}
        for k in _CONFIG_SHARED_KEYS:
            v = st.value(k, "", type=str)
            if v:
                seed[k] = v
        appconfig.update(seed) if seed else appconfig.ensure_exists()


def _export_settings(path: str) -> None:
    """이 PC의 설정(구글시트 링크·입력소스 + API/SA 키)을 평문 JSON 으로 내보낸다(배포 패키지 동봉용).

    설치 스크립트(install.ps1)가 이 파일의 qsettings 로 새 PC **프로젝트 루트에 config.json** 을 만들고
    (비밀 아님), 키는 credstore 로 암호화 이식한다."""
    from coupang_analytics.credstore import CredStore
    st = QtCore.QSettings("coupang-analytics", "ui")
    cs = CredStore()
    data = {"qsettings": {}, "credstore": {}}
    for k in _EXPORT_QKEYS:
        v = appconfig.get(k, "") or st.value(k, "", type=str)   # config.json 우선(없으면 레지스트리)
        if v:
            data["qsettings"][k] = v
    for k in _EXPORT_CREDS:
        v = cs.get_password(k)
        if v:
            data["credstore"][k] = v
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    # config.json(비밀 아님)은 설치 스크립트(install.ps1)가 이 파일의 qsettings 로 **루트에** 만든다
    # (onedir 안에 config.json 을 두면 가짜 루트 표식이 되므로 여기선 만들지 않는다).
    print(f"[설정 내보내기] {path} - 링크/소스 {len(data['qsettings'])}개, 키 {len(data['credstore'])}개(평문·배포 zip 전용)")


def _import_settings(path: str) -> None:
    """새 PC에서 내보낸 설정을 가져와 **이 PC 전용 암호화(DPAPI)** 로 저장하고 평문 파일을 삭제한다(무설정 설치)."""
    from coupang_analytics.credstore import CredStore
    p = Path(path)
    if not p.exists():
        print(f"[설정 가져오기] 설정 파일 없음(건너뜀): {path}")
        return
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"[설정 가져오기] [주의] 설정 파일을 읽지 못함(건너뜀): {exc}")
        return
    st = QtCore.QSettings("coupang-analytics", "ui")
    qs = data.get("qsettings") or {}
    # 운용 PC 재배포(업데이트) 때 **이미 저장된 값(config.json)은 보존** — 패키지의 옛 링크로 덮어쓰지 않는다.
    # (소유자 2026-10-07: 재배포마다 구글시트 URL 이 과거 값으로 초기화돼 매번 재설정하던 문제 근본 수정.)
    imported = [k for k, v in qs.items() if not appconfig.get(k, "")]
    for k in imported:
        st.setValue(k, qs[k])
    st.sync()
    appconfig.update({k: qs[k] for k in imported if isinstance(qs[k], str)})   # config.json(보존 폴더)에도 이식
    kept = [k for k in qs if k not in imported]
    cs = CredStore()
    n = 0
    for k, v in (data.get("credstore") or {}).items():
        try:
            cs.set_password(k, v); n += 1
        except Exception as exc:
            print(f"[설정 가져오기] [주의] 키 저장 실패({k}): {exc}")
    try:
        p.unlink()               # 평문 설정 파일 즉시 삭제(이 PC엔 암호화본만 남김)
        deleted = "평문 파일 삭제함"
    except OSError:
        deleted = "[주의] 평문 파일 삭제 실패-수동 삭제 필요"
    print(f"[설정 가져오기] 완료 - 링크/소스 이식 {len(imported)}개·기존 보존 {len(kept)}개, "
          f"키 {n}개 이 PC용 암호화 저장, {deleted}")


def main():
    argv = sys.argv
    if "--export-settings" in argv:      # 배포 패키지 만들 때(이 PC): 설정 평문 내보내기
        _export_settings(argv[argv.index("--export-settings") + 1]); return
    if "--import-settings" in argv:      # 새 PC 설치 시: 설정 가져와 암호화 저장 + 평문 삭제
        _import_settings(argv[argv.index("--import-settings") + 1]); return
    _root = set_workdir()           # 상태(output·data)를 **보존 폴더(프로젝트 루트)** 에 고정 — 실행 폴더 무관
    _sync_config_and_registry()     # config.json(보존 폴더) ↔ 레지스트리 동기화(설정 파일을 권위로·창 생성 전)
    print(f"[경로] 데이터 폴더(마스터·크롬 프로필·설정·로그) = {_root}")
    auto = "--auto" in sys.argv     # 무인 자동 실행(작업 스케줄러가 18:00에 이 인자로 실행)
    resume = "--resume" in sys.argv  # 재부팅 복구(작업 스케줄러 '로그온 시' 트리거) — 중단분만 이어서, 없으면 종료
    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(_QSS.replace("__CHECK_ICON__", _check_icon_path()))
    try:                            # Chrome 필수(실제 Chrome+CDP 정책) — 없으면 크래시 대신 안내 후 종료
        find_chrome()
    except FileNotFoundError:
        if auto or resume:
            print("[무인] Google Chrome 미설치 — 실행 불가")   # 무인: 대화상자 대신 로그
        else:
            QtWidgets.QMessageBox.critical(
                None, "Google Chrome 필요",
                "이 프로그램은 실제 Google Chrome 으로 동작합니다.\n\n"
                "이 PC 에 Chrome 이 설치돼 있지 않습니다. https://www.google.com/chrome 에서 "
                "Chrome 을 설치한 뒤 다시 실행하세요.")
        sys.exit(1)
    pre_logs: list[str] = []
    if auto:                        # D-010: 18:00 무인 = 이전 앱·정산 프로그램 종료 + 옛 정산 예약작업 제거(그 Chrome 은 아래 reap)
        prepare_auto_start(pre_logs.append)
    reaped = reap_orphan_chrome()   # 이전 실행이 강제종료·크래시로 남긴 좀비 Chrome 정리(누적 원천 차단)
    if reaped:
        pre_logs.append(f"[시작] 잔여(좀비) Chrome {reaped}개 정리함")
    if auto or resume:              # D-021: 18:00(·재부팅 복구) 앱과 함께 정산 기동 — 정산은 ① 완료까지 대기
        start_settlement_watch(pre_logs.append)
    win = App(auto=(auto or resume))
    win.show()
    for m in pre_logs:
        win.log(m)
    if resume:                      # 재부팅 복구 — 오늘 중단분만 이어서(없으면 스스로 종료)
        QtCore.QTimer.singleShot(1500, win.start_resume)
    elif auto:                      # 이벤트 루프 뜬 직후 무인 실행 자동 시작
        QtCore.QTimer.singleShot(1500, win.start_auto)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
