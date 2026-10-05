"""통합 앱 패널 공용 UI 헬퍼(카드·표·폼·버튼·오류 표시). H_ui 레인. 기존 app_qt 스타일(QSS)과 어울리게.

도메인 패널(cs·contract·worklog·creditor)이 공유하는 작은 조립 함수만 둔다(선제 추상화 아님·실제 중복 제거).
오류는 조용히 삼키지 않고 QMessageBox 로 보여준다([[no-silent-fallback-principle]]).
"""
from __future__ import annotations

from PySide6 import QtWidgets


def group(title: str) -> tuple[QtWidgets.QGroupBox, QtWidgets.QVBoxLayout]:
    box = QtWidgets.QGroupBox(title)
    lay = QtWidgets.QVBoxLayout(box)
    lay.setContentsMargins(12, 16, 12, 12)
    lay.setSpacing(8)
    return box, lay


def accent_button(text: str) -> QtWidgets.QPushButton:
    btn = QtWidgets.QPushButton(text)
    btn.setObjectName("accent")
    return btn


def make_table(headers: list[str]) -> QtWidgets.QTableWidget:
    tbl = QtWidgets.QTableWidget(0, len(headers))
    tbl.setHorizontalHeaderLabels(headers)
    tbl.verticalHeader().setVisible(False)
    tbl.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
    tbl.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    tbl.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
    tbl.horizontalHeader().setStretchLastSection(True)
    tbl.setWordWrap(False)
    return tbl


def set_rows(tbl: QtWidgets.QTableWidget, rows: list[list[str]], *, red_rows: set[int] | None = None) -> None:
    from PySide6 import QtGui
    red_rows = red_rows or set()
    tbl.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            item = QtWidgets.QTableWidgetItem("" if val is None else str(val))
            if r in red_rows:
                item.setForeground(QtGui.QColor("#b91c1c"))
            tbl.setItem(r, c, item)
    tbl.resizeColumnsToContents()


def form(rows: list[tuple[str, QtWidgets.QWidget]]) -> QtWidgets.QWidget:
    """(라벨, 위젯) 목록 → 폼 위젯."""
    w = QtWidgets.QWidget()
    fl = QtWidgets.QFormLayout(w)
    fl.setSpacing(8)
    for label, widget in rows:
        fl.addRow(label, widget)
    return w


def combo(items) -> QtWidgets.QComboBox:
    c = QtWidgets.QComboBox()
    c.addItems(list(items))
    return c


def error(parent, exc: Exception) -> None:
    QtWidgets.QMessageBox.warning(parent, "입력 확인", str(exc))


def info(parent, msg: str) -> None:
    QtWidgets.QMessageBox.information(parent, "완료", msg)
