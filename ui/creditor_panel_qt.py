"""통합 앱 — 채권자 패널(D8·12-x). creditor_store 연결. 등록·채권/상환 기록(정정=반대기록)·잔액·역할별 가림.

⚠ 기록 전용(배분 계산은 법률 확정 후·R1 보류). 이름·연락처=대표/정산담당, 상환계좌=대표만 원문.
"""
from __future__ import annotations

from datetime import date

from PySide6 import QtWidgets

from coupang_analytics import creditor_store as CR

from . import panel_kit as K

ROLES = ("창고", "정산담당", "대표")
_COLS = ["번호", "이름", "연락처", "상환계좌", "잔액"]


class CreditorPanel(QtWidgets.QWidget):
    def __init__(self, client):
        super().__init__()
        self.client = client
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        reg, rlay = K.group("채권자 등록")
        self.name = QtWidgets.QLineEdit()
        self.contact = QtWidgets.QLineEdit()
        self.account = QtWidgets.QLineEdit()
        rlay.addWidget(K.form([("이름 *", self.name), ("연락처 *", self.contact), ("상환계좌 *", self.account)]))
        radd = K.accent_button("채권자 등록")
        radd.clicked.connect(self._add_creditor)
        self._right(rlay, radd)
        root.addWidget(reg)

        mv, mlay = K.group("채권 확정 / 상환 기록 (정정은 금액에 음수 = 반대 기록)")
        self.cid = K.combo([])
        self.kind = K.combo(CR.MOVEMENT_TYPES)
        self.amount = QtWidgets.QLineEdit()
        self.mdate = QtWidgets.QLineEdit(date.today().isoformat())
        self.note = QtWidgets.QLineEdit()
        mlay.addWidget(K.form([("채권자번호", self.cid), ("유형", self.kind), ("금액(원) *", self.amount),
                               ("일자 *", self.mdate), ("비고", self.note)]))
        madd = K.accent_button("기록")
        madd.clicked.connect(self._add_movement)
        self._right(mlay, madd)
        root.addWidget(mv)

        box2, lay2 = K.group("채권자 잔액 (채권확정 − 상환 누적)")
        head = QtWidgets.QHBoxLayout()
        head.addWidget(QtWidgets.QLabel("열람 역할:"))
        self.role = K.combo(ROLES)
        self.role.currentIndexChanged.connect(self.refresh)
        head.addWidget(self.role)
        head.addStretch(1)
        lay2.addLayout(head)
        self.tbl = K.make_table(_COLS)
        lay2.addWidget(self.tbl)
        root.addWidget(box2, 1)

    @staticmethod
    def _right(lay, btn) -> None:
        hb = QtWidgets.QHBoxLayout()
        hb.addStretch(1)
        hb.addWidget(btn)
        lay.addLayout(hb)

    def _add_creditor(self) -> None:
        try:
            CR.record_creditor(self.client, name=self.name.text().strip(), contact=self.contact.text().strip(),
                               account=self.account.text().strip())
        except Exception as exc:
            K.error(self, exc)
            return
        for e in (self.name, self.contact, self.account):
            e.clear()
        self.refresh()

    def _add_movement(self) -> None:
        if not self.cid.currentText():
            K.error(self, ValueError("먼저 채권자를 등록하세요"))
            return
        try:
            CR.record_movement(self.client, creditor_id=self.cid.currentText(), kind=self.kind.currentText(),
                               amount=self.amount.text().strip(), date=self.mdate.text().strip(),
                               note=self.note.text().strip())
        except Exception as exc:
            K.error(self, exc)
            return
        self.amount.clear()
        self.note.clear()
        self.refresh()

    def refresh(self) -> None:
        creditors = CR.load_creditors(self.client)
        moves = CR.load_movements(self.client)
        cur = self.cid.currentText()
        self.cid.blockSignals(True)
        self.cid.clear()
        self.cid.addItems([c.no for c in creditors])
        if cur:
            self.cid.setCurrentText(cur)
        self.cid.blockSignals(False)
        role = self.role.currentText()
        rows = []
        for c in creditors:
            m = CR.mask_master(c, role=role)
            rows.append([m["번호"], m["이름"], m["연락처"], m["상환계좌"], f"{CR.balance(moves, c.no):,}"])
        K.set_rows(self.tbl, rows)
