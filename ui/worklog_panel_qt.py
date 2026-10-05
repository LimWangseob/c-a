"""통합 앱 — 업무일지 패널(D8·11-4). worklog_store 연결. 작성(append)·목록(최신순·진행 7일 경과 빨강)."""
from __future__ import annotations

from datetime import date

from PySide6 import QtWidgets

from coupang_analytics import worklog_store as W

from . import panel_kit as K


class WorklogPanel(QtWidgets.QWidget):
    def __init__(self, client, author: str = "담당자"):
        super().__init__()
        self.client = client
        self.author = author
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        box, lay = K.group("업무일지 작성")
        self.acc = QtWidgets.QLineEdit()
        self.prod = QtWidgets.QLineEdit()
        self.prod.setPlaceholderText("비우면 계정 전체")
        self.content = QtWidgets.QLineEdit()
        self.follow = QtWidgets.QLineEdit()
        self.status = K.combo(W.STATUS_CHOICES)
        lay.addWidget(K.form([("위탁계정 *", self.acc), ("상품", self.prod), ("내용 *", self.content),
                              ("후속조치", self.follow), ("상태 *", self.status)]))
        add = K.accent_button("추가")
        add.clicked.connect(self._add)
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        row.addWidget(add)
        lay.addLayout(row)
        root.addWidget(box)

        box2, lay2 = K.group("업무일지 목록 (최신순 · 진행 7일 경과 = 빨강)")
        self.tbl = K.make_table(list(W.HEADER))
        lay2.addWidget(self.tbl)
        root.addWidget(box2, 1)

    def _add(self) -> None:
        try:
            W.append(self.client, account_id=self.acc.text().strip(), content=self.content.text().strip(),
                     status=self.status.currentText(), author=self.author, product=self.prod.text().strip(),
                     followup=self.follow.text().strip())
        except Exception as exc:                       # 검증 실패 등 — 조용히 넘기지 않고 사용자에게 표시
            K.error(self, exc)
            return
        for e in (self.acc, self.prod, self.content, self.follow):
            e.clear()
        self.refresh()

    def refresh(self) -> None:
        wl = W.load(self.client)
        rows, red = [], set()
        for i, e in enumerate(wl.entries):
            rows.append([str(e.no), e.date, e.author, e.account_id, e.product, e.content, e.followup, e.status])
            if W.is_overdue(e, today=date.today()):
                red.add(i)
        K.set_rows(self.tbl, rows, red_rows=red)
