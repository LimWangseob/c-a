"""통합 앱 공용 위젯 — 시안 '디자인 컨셉' 보드의 ④기간 알약 · ⑤큰 숫자+비교 배지 · ⑥둥근 알약 막대 그래프.

SSOT = designs/UI_SCREENS.md §3(컨셉 표)·§5(공통 컴포넌트: PeriodPill·KpiTile·PillBar). 색은 ui/theme_qt.py 토큰,
모양(둥근 모서리·선택 보라)은 theme_qt QSS 의 objectName/속성 선택자(pill·pillDim·badge[tone]·card·kpiValue)로 준다.
막대 그래프만 QSS 로 못 그려 paintEvent 로 직접 그린다(그림자 없음·테두리 위주 원칙).
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ui import theme_qt as T


class PeriodPills(QtWidgets.QWidget):
    """알약 버튼 묶음(하나만 선택) — 선택 = 보라 채움, 비선택 = 회색 테두리. dim 키는 '준비 중'(회색 점선·비활성)."""

    changed = QtCore.Signal(str)

    def __init__(self, options: dict[str, str], *, current: str | None = None,
                 dim: tuple[str, ...] = (), parent=None):
        super().__init__(parent)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._group = QtWidgets.QButtonGroup(self)
        self._group.setExclusive(True)
        self._keys: dict[QtWidgets.QAbstractButton, str] = {}
        for key, label in options.items():
            btn = QtWidgets.QPushButton(label)
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            if key in dim:
                btn.setObjectName("pillDim")
                btn.setEnabled(False)
                btn.setToolTip("준비 중 — 아직 없는 기능")
            else:
                btn.setObjectName("pill")
                btn.setCheckable(True)
                self._group.addButton(btn)
                self._keys[btn] = key
            lay.addWidget(btn)
        first = next(iter(self._keys.values()), None)
        self.set_current(current or first)
        self._group.buttonClicked.connect(lambda b: self.changed.emit(self._keys[b]))

    def current(self) -> str | None:
        btn = self._group.checkedButton()
        return self._keys.get(btn) if btn else None

    def set_current(self, key: str | None) -> None:
        for btn, k in self._keys.items():
            btn.setChecked(k == key)


def delta_text(pct: int | None) -> tuple[str, str]:
    """증감% → (배지 글자, tone). None = ('', '') 배지 숨김."""
    if pct is None:
        return "", ""
    if pct > 0:
        return f"▲ {pct}%", "up"
    if pct < 0:
        return f"▼ {abs(pct)}%", "down"
    return "– 0%", "flat"


class DeltaBadge(QtWidgets.QLabel):
    """비교 배지 — ▲ 초록 / ▼ 빨강 / – 회색(theme_qt QSS: QLabel#badge[tone=…])."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("badge")
        self.set_delta(None)

    def set_delta(self, pct: int | None) -> None:
        text, tone = delta_text(pct)
        self.setText(text)
        self.setProperty("tone", tone)
        self.setVisible(bool(text))
        self.style().unpolish(self)
        self.style().polish(self)


class KpiTile(QtWidgets.QFrame):
    """큰 숫자 + 바로 아래 비교 배지 + 회색 설명(시안 ⑤)."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(4)
        self.title = QtWidgets.QLabel(title)
        self.title.setObjectName("muted")
        self.value = QtWidgets.QLabel("—")
        self.value.setObjectName("kpiValue")
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(6)
        self.badge = DeltaBadge()
        self.note = QtWidgets.QLabel("")
        self.note.setObjectName("muted")
        self.note.setWordWrap(True)                     # 좁은 칸에서도 잘리지 않게 줄바꿈
        row.addWidget(self.badge, 0, QtCore.Qt.AlignTop)
        row.addWidget(self.note, 1)
        lay.addWidget(self.title)
        lay.addWidget(self.value)
        lay.addLayout(row)

    def set_data(self, value: str, pct: int | None, note: str) -> None:
        self.value.setText(value)
        self.badge.set_delta(pct)
        self.note.setText(note)


def fmt_num(v) -> str:
    """정수면 천단위 쉼표, 소수면 한 자리 — None = '—'."""
    if v is None:
        return "—"
    return f"{int(v):,}" if float(v).is_integer() else f"{v:,.1f}"


def bar_ratios(values: list) -> list[float]:
    """막대 높이 비율(0~1). None = 0(빈 트랙만). 최댓값 기준·전부 없거나 0이면 전부 0."""
    nums = [v for v in values if v is not None]
    top = max(nums) if nums else 0
    if top <= 0:
        return [0.0] * len(values)
    return [max(0.0, (v or 0) / top) for v in values]


def label_step(n: int, max_labels: int = 10) -> int:
    """막대가 많을 때 아래 날짜 글자를 몇 칸마다 쓸지(겹침 방지)."""
    return max(1, -(-n // max_labels))


class PillBarChart(QtWidgets.QWidget):
    """둥근 알약 막대(시안 ⑥) — 연한 트랙 위 둥근 막대, 선택 막대만 진한 보라+말풍선, 나머지 연보라.

    점: (라벨, 값|None, 보조). 값 None = 빈 트랙(미실행=공란). 막대를 누르면 그 막대가 선택된다(기본=마지막 값 있는 막대).
    """

    selected = QtCore.Signal(int)
    _LABEL_H = 34          # 아래 날짜+보조 글자 영역
    _TIP_H = 24            # 위 말풍선 영역

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(190)
        self._pts: list[tuple[str, float | None, str]] = []
        self._unit = ""
        self._sel = -1

    def set_points(self, pts: list[tuple[str, float | None, str]], unit: str = "") -> None:
        self._pts = list(pts)
        self._unit = unit
        filled = [i for i, (_l, v, _s) in enumerate(self._pts) if v is not None]
        self._sel = filled[-1] if filled else -1
        self.update()

    def selected_index(self) -> int:
        return self._sel

    def _slots(self) -> list[QtCore.QRectF]:
        n = len(self._pts)
        if not n:
            return []
        gap = 8 if n <= 14 else 4
        w = (self.width() - gap * (n - 1)) / n
        h = self.height() - self._LABEL_H - self._TIP_H
        return [QtCore.QRectF(i * (w + gap), self._TIP_H, w, h) for i in range(n)]

    def mousePressEvent(self, ev):  # noqa: N802 (Qt 이름)
        for i, r in enumerate(self._slots()):
            if r.left() <= ev.position().x() <= r.right() and self._pts[i][1] is not None:
                self._sel = i
                self.selected.emit(i)
                self.update()
                return
        super().mousePressEvent(ev)

    def paintEvent(self, _ev):  # noqa: N802 (Qt 이름)
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtCore.Qt.NoPen)
        slots = self._slots()
        ratios = bar_ratios([v for _l, v, _s in self._pts])
        for i, r in enumerate(slots):
            self._paint_bar(p, r, ratios[i], i == self._sel)
        self._paint_labels(p, slots)
        if 0 <= self._sel < len(slots):
            self._paint_tip(p, slots[self._sel])
        p.end()

    @staticmethod
    def _paint_bar(p: QtGui.QPainter, r: QtCore.QRectF, ratio: float, on: bool) -> None:
        rad = min(12.0, r.width() / 2)
        p.setBrush(QtGui.QColor(T.TRACK))
        p.drawRoundedRect(r, rad, rad)
        if ratio > 0:
            bh = max(r.width(), r.height() * ratio)            # 아주 작은 값도 둥근 알약 모양 유지
            bar = QtCore.QRectF(r.left(), r.bottom() - bh, r.width(), bh)
            p.setBrush(QtGui.QColor(T.PURPLE if on else T.PURPLE_LIGHT))
            p.drawRoundedRect(bar, rad, rad)

    def _paint_labels(self, p: QtGui.QPainter, slots: list[QtCore.QRectF]) -> None:
        step = label_step(len(slots))
        f = p.font()
        f.setPointSizeF(8.5)
        p.setFont(f)
        last = len(slots) - 1
        for i, r in enumerate(slots):
            if i % step and i != self._sel and i != last:
                continue
            label, _v, sub = self._pts[i]
            box = QtCore.QRectF(r.left() - 12, r.bottom() + 3, r.width() + 24, 15)
            p.setPen(QtGui.QColor(T.PURPLE if i == self._sel else T.MUTED))
            p.drawText(box, QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop, label)
            if sub and step == 1:
                p.setPen(QtGui.QColor(T.MUTED))
                p.drawText(box.translated(0, 15), QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop, sub)
        p.setPen(QtCore.Qt.NoPen)

    def _paint_tip(self, p: QtGui.QPainter, r: QtCore.QRectF) -> None:
        _label, v, _sub = self._pts[self._sel]
        text = f"{fmt_num(v)}{self._unit}"
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(text) + 14
        tip = QtCore.QRectF(r.center().x() - w / 2, 0, w, 20)
        tip.moveLeft(max(0.0, min(tip.left(), self.width() - w)))
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(T.TEXT))
        p.drawRoundedRect(tip, 6, 6)
        p.setPen(QtGui.QColor("#ffffff"))
        p.drawText(tip, QtCore.Qt.AlignCenter, text)
