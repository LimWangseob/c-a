"""통합 앱 — 계약 패널(D8·11-3). contract_store 연결. 등록(최초/개정)·해지·as_of 목록·역할별 민감 가림."""
from __future__ import annotations

from datetime import date

from PySide6 import QtWidgets

from coupang_analytics import contract_store as C

from . import panel_kit as K

ROLES = ("창고", "정산담당", "대표")           # 기본=창고(가림 확인). 대표/정산담당=정산계좌·수탁자 원문
_COLS = ["위탁계정", "사업", "상태", "계약기간", "수익배분", "계약금", "정산계좌"]


class ContractPanel(QtWidgets.QWidget):
    def __init__(self, client):
        super().__init__()
        self.client = client
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        box, lay = K.group("계약 등록 / 개정 (같은 위탁계정·사업이면 개정으로 쌓임)")
        self.f = {k: QtWidgets.QLineEdit() for k in
                  ("위탁계정", "사업", "사업자명", "대표자명", "수익배분", "수익기준", "수익계산식", "계약금", "정산계좌")}
        self.signdate = QtWidgets.QLineEdit(date.today().isoformat())
        self.start = QtWidgets.QLineEdit(date.today().isoformat())
        self.end = QtWidgets.QLineEdit(date(date.today().year + 1, date.today().month, date.today().day).isoformat())
        rows = [(f"{k} *" if k in ("위탁계정", "사업", "사업자명", "대표자명", "수익배분", "수익기준", "수익계산식")
                 else k, w) for k, w in self.f.items()]
        rows[4:4] = [("계약일자 * (YYYY-MM-DD)", self.signdate),
                     ("계약기간시작 *", self.start), ("계약기간끝 *", self.end)]
        lay.addWidget(K.form(rows))
        add = K.accent_button("등록 / 개정")
        add.clicked.connect(self._add)
        hb = QtWidgets.QHBoxLayout()
        hb.addStretch(1)
        hb.addWidget(add)
        lay.addLayout(hb)
        root.addWidget(box)

        box2, lay2 = K.group("계약 목록 (오늘 기준 유효 계약 · 만료 30일 이내 = 빨강)")
        head = QtWidgets.QHBoxLayout()
        head.addWidget(QtWidgets.QLabel("열람 역할:"))
        self.role = K.combo(ROLES)
        self.role.currentIndexChanged.connect(self.refresh)
        head.addWidget(self.role)
        head.addStretch(1)
        term = QtWidgets.QPushButton("선택 계약 해지")
        term.clicked.connect(self._terminate)
        head.addWidget(term)
        lay2.addLayout(head)
        self.tbl = K.make_table(_COLS)
        lay2.addWidget(self.tbl)
        root.addWidget(box2, 1)

    def _add(self) -> None:
        fields = {k: w.text().strip() for k, w in self.f.items()}
        fields["계약일자"] = self.signdate.text().strip()
        fields["계약기간시작"] = self.start.text().strip()
        fields["계약기간끝"] = self.end.text().strip()
        try:
            C.record(self.client, account_id=fields["위탁계정"], business=fields["사업"], fields=fields,
                     eff=date.today().isoformat())
        except Exception as exc:
            K.error(self, exc)
            return
        self.refresh()

    def _terminate(self) -> None:
        r = self.tbl.currentRow()
        if r < 0:
            K.error(self, ValueError("해지할 계약을 목록에서 고르세요"))
            return
        aid, biz = self.tbl.item(r, 0).text(), self.tbl.item(r, 1).text()
        try:
            C.record(self.client, account_id=aid, business=biz, eff=date.today().isoformat(), terminate=True)
        except Exception as exc:
            K.error(self, exc)
            return
        self.refresh()

    def refresh(self) -> None:
        led = C.load(self.client)
        at = date.today().isoformat()
        role = self.role.currentText()
        rows, red = [], set()
        for i, key in enumerate(led.keys()):
            snap = C.as_of(led, key, at)
            if snap is None:
                continue
            v = C.view(snap, role=role)
            rows.append([v["위탁계정"], v["사업"], v.get("상태", ""),
                         f"{v.get('계약기간시작', '')}~{v.get('계약기간끝', '')}",
                         v.get("수익배분", ""), v.get("계약금", ""), v.get("정산계좌", "")])
            if C.expiring_soon(led, key, today=date.today()):
                red.add(len(rows) - 1)
        K.set_rows(self.tbl, rows, red_rows=red)
