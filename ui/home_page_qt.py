"""통합 앱 홈 — 시안 홈 보드(Main)의 '변동 추이' 카드 승격(화면 머리+기간 알약·큰 숫자+비교 배지·알약 막대).

데이터 = 결과 통계 마스터(output/쿠팡데이타분석_통계.xlsx) **조회 전용**(ui/home_trend.py). 파일이 없거나 못 읽으면
카드에 이유를 그대로 보여준다(조용히 비우지 않음). 매출·수익 탭은 아직 없는 기능 = 회색 '준비 중'.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6 import QtCore, QtWidgets

from coupang_analytics import config
from ui import home_trend as H
from ui.widgets_qt import KpiTile, PeriodPills, PillBarChart, fmt_num

_WEEK = "월화수목금토일"
_TABS = {t: t for t in H.METRICS} | {"money": "매출·수익 (준비 중)"}
_CAPTION = {H.RANK: f"막대 = 그날 검색 1페이지({H.PAGE1}위) 안에 든 키워드 수 · 아래 = 평균 순위(정확 순위만)"}
_GUIDE = ("지금 작동하는 영역(왼쪽 메뉴): 05 문의·리뷰 · 11 사업·계약(계약·업무일지) · 12 채권자·상환.\n"
          "나머지 메뉴는 아직 기존 운영 앱에서 동작합니다(순차 이관). 저장소: 로컬 파일 output/통합앱_data/.")


def _kday(d: date) -> str:
    return f"{d.month}월 {d.day}일({_WEEK[d.weekday()]})"


class HomePage(QtWidgets.QWidget):
    def __init__(self, master: Path, parent=None):
        super().__init__(parent)
        self._master = master
        self._daily: dict = {}
        self._points: list[H.DayPoint] = []
        self._build()
        QtCore.QTimer.singleShot(0, self.refresh)        # 창부터 띄우고 엑셀은 그 다음에 읽음

    # ── 화면 ──
    def _build(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(12)
        root.addLayout(self._head())
        root.addWidget(self._trend_card())
        guide = QtWidgets.QLabel(_GUIDE)
        guide.setObjectName("muted")
        root.addWidget(guide)
        root.addStretch(1)

    def _head(self) -> QtWidgets.QHBoxLayout:
        row = QtWidgets.QHBoxLayout()
        left = QtWidgets.QVBoxLayout()
        left.setSpacing(0)
        crumb = QtWidgets.QLabel("홈")
        crumb.setObjectName("crumb")
        title = QtWidgets.QLabel(f"오늘 현황 · {_kday(date.today())}")
        title.setObjectName("pageTitle")
        left.addWidget(crumb)
        left.addWidget(title)
        row.addLayout(left)
        row.addStretch(1)
        right = QtWidgets.QVBoxLayout()
        top = QtWidgets.QHBoxLayout()
        self.last_lbl = QtWidgets.QLabel("")
        self.last_lbl.setObjectName("muted")
        btn = QtWidgets.QPushButton("새로고침")
        btn.setToolTip("결과 엑셀(통계 마스터)을 다시 읽습니다(수집 아님).")
        btn.clicked.connect(self.refresh)
        top.addStretch(1)
        top.addWidget(self.last_lbl)
        top.addWidget(btn)
        self.period = PeriodPills(H.PERIODS, current="7d")
        self.period.changed.connect(lambda _k: self._render())
        right.addLayout(top)
        right.addWidget(self.period, 0, QtCore.Qt.AlignRight)
        row.addLayout(right)
        return row

    def _trend_card(self) -> QtWidgets.QFrame:
        card = QtWidgets.QFrame()
        card.setObjectName("card")
        lay = QtWidgets.QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        head = QtWidgets.QHBoxLayout()
        t = QtWidgets.QLabel("변동 추이")
        t.setObjectName("cardTitle")
        self.tabs = PeriodPills(_TABS, current=H.RANK, dim=("money",))
        self.tabs.changed.connect(lambda _k: self._render())
        head.addWidget(t)
        head.addStretch(1)
        head.addWidget(self.tabs)
        lay.addLayout(head)
        self.caption = QtWidgets.QLabel("")
        self.caption.setObjectName("muted")
        self.caption.setWordWrap(True)
        lay.addWidget(self.caption)
        body = QtWidgets.QHBoxLayout()
        self.kpi = KpiTile()
        self.kpi.setFixedWidth(230)
        self.chart = PillBarChart()
        self.chart.selected.connect(self._show_kpi)
        body.addWidget(self.kpi, 0, QtCore.Qt.AlignTop)
        body.addWidget(self.chart, 1)
        lay.addLayout(body)
        return card

    # ── 데이터 ──
    def refresh(self) -> None:
        if not self._master.exists():
            self._daily = {}
            self._render(f"결과 엑셀(통계 마스터)이 아직 없습니다 — {self._master.name}. "
                         "기존 앱에서 ①판매수집 또는 전체 실행으로 먼저 수집하세요.")
            return
        try:
            self._daily = H.load_master(self._master)
        except Exception as exc:                       # 비치명 — 이유를 카드에 그대로 표시
            self._daily = {}
            self._render(f"결과 엑셀을 읽지 못했습니다: {exc.__class__.__name__}: {exc}")
            return
        self._render()

    def _render(self, problem: str = "") -> None:
        tab = self.tabs.current() or H.RANK
        end = H.last_day(self._daily)
        if problem or end is None:
            self._points = []
            self.chart.set_points([], "")
            self.kpi.set_data("—", None, "")
            self.last_lbl.setText("")
            self.caption.setText(problem or "결과 엑셀에 날짜별 값이 아직 없습니다.")
            return
        start, end = H.period_range(self.period.current() or "7d", end)
        self._points = H.series(self._daily, tab, start, end)
        self.chart.set_points([(p.label, p.value, p.sub) for p in self._points], H.UNITS[tab])
        self.last_lbl.setText(f"결과 파일 마지막 데이터 {_kday(end)}")
        self.caption.setText(f"{start:%m.%d}~{end:%m.%d} · " + _CAPTION.get(
            tab, f"전 계정·전 상품 {config.M_VIEWS if tab == '검색량' else tab} 날짜별 합계") + " · 빈 막대 = 미실행(공란)")
        self._show_kpi(self.chart.selected_index())

    def _show_kpi(self, idx: int) -> None:
        if not (0 <= idx < len(self._points)):
            self.kpi.set_data("—", None, "값 있는 날 없음")
            return
        tab = self.tabs.current() or H.RANK
        p = self._points[idx]
        cur, prev, pct = H.week_compare(self._daily, tab, p.day)
        self.kpi.title.setText(f"{'1페이지 안 키워드' if tab == H.RANK else tab} · {_kday(p.day)}")
        note = "지난주 같은 요일 대비" if pct is not None else "지난주 같은 요일 값 없음"
        if p.sub:
            note = f"{p.sub} · {note}"
        self.kpi.set_data(f"{fmt_num(cur)}{H.UNITS[tab]}", pct, note)
