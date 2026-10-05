"""통합 앱 — 문의/CS 패널(D10·05-x). cs_gsheet/cs_store 연결. 접수·이벤트(상태/응대)·목록(상태 replay)·가림·통계.

업무일지(D8)와 별개 — 외부 고객 문의만. 응대 전송(쓰기)은 범위밖(§2.2)·여기선 접수·상태·이력만.
"""
from __future__ import annotations

from datetime import date, timedelta

from PySide6 import QtWidgets

from coupang_analytics import cs_gsheet as G
from coupang_analytics import cs_model as M
from coupang_analytics import cs_store as S

from . import panel_kit as K

ROLES = ("창고", "CS담당", "대표")
_COLS = ["문의ID", "상태", "판매처", "위탁계정", "유형", "고객이름", "연락처", "문의내용"]


class CSPanel(QtWidgets.QWidget):
    def __init__(self, client, author: str = "CS담당"):
        super().__init__()
        self.client = client
        self.author = author
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        rec, rlay = K.group("문의 접수")
        self.mkt = QtWidgets.QLineEdit("쿠팡")
        self.acc = QtWidgets.QLineEdit()
        self.prod = QtWidgets.QLineEdit()
        self.prod.setPlaceholderText("비우면 계정 전체")
        self.type = K.combo(M.INQUIRY_TYPES)
        self.name = QtWidgets.QLineEdit()
        self.contact = QtWidgets.QLineEdit()
        self.content = QtWidgets.QLineEdit()
        rlay.addWidget(K.form([("판매처 *", self.mkt), ("위탁계정 *", self.acc), ("상품", self.prod),
                               ("문의유형 *", self.type), ("고객이름", self.name), ("연락처", self.contact),
                               ("문의내용 *", self.content)]))
        radd = K.accent_button("접수")
        radd.clicked.connect(self._receive)
        self._right(rlay, radd)
        root.addWidget(rec)

        ev, elay = K.group("상태 변경 / 응대 기록 (문의 선택 → 이벤트 추가)")
        self.qid = K.combo([])
        self.kind = K.combo(M.EVENT_KINDS)
        self.note = QtWidgets.QLineEdit()
        self.note.setPlaceholderText("응대내용 / 보류 사유")
        elay.addWidget(K.form([("문의ID", self.qid), ("변동유형", self.kind), ("응대내용", self.note)]))
        eadd = K.accent_button("이벤트 기록")
        eadd.clicked.connect(self._event)
        self._right(elay, eadd)
        root.addWidget(ev)

        box2, lay2 = K.group("문의 목록 (상태 = 이벤트 이력에서 계산)")
        head = QtWidgets.QHBoxLayout()
        head.addWidget(QtWidgets.QLabel("열람 역할:"))
        self.role = K.combo(ROLES)
        self.role.currentIndexChanged.connect(self.refresh)
        head.addWidget(self.role)
        head.addStretch(1)
        stat = QtWidgets.QPushButton("통계(최근 30일)")
        stat.clicked.connect(self._stats)
        head.addWidget(stat)
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

    def _receive(self) -> None:
        try:
            G.open_inquiry(self.client, marketplace=self.mkt.text().strip(), account_id=self.acc.text().strip(),
                           type=self.type.currentText(), content=self.content.text().strip(),
                           product=self.prod.text().strip(), asker_name=self.name.text().strip(),
                           contact=self.contact.text().strip())
        except Exception as exc:
            K.error(self, exc)
            return
        for e in (self.acc, self.prod, self.name, self.contact, self.content):
            e.clear()
        self.refresh()

    def _event(self) -> None:
        if not self.qid.currentText():
            K.error(self, ValueError("먼저 문의를 접수하세요"))
            return
        try:
            G.add_event(self.client, inquiry_id=self.qid.currentText(), kind=self.kind.currentText(),
                        author=self.author, note=self.note.text().strip())
        except Exception as exc:
            K.error(self, exc)
            return
        self.note.clear()
        self.refresh()

    def _stats(self) -> None:
        log = G.load_log(self.client)
        end = date.today()
        st = S.stats(log, (end - timedelta(days=30)).isoformat(), end.isoformat())
        K.info(self, f"최근 30일 — 접수 {st['접수']} · 완료 {st['완료']} · 보류 {st['보류']}\n"
                     f"평균 처리일 {st['평균처리일']} · 보류율 {st['보류율']:.0%}\n계정별 {st['계정별']}")

    def refresh(self) -> None:
        log = G.load_log(self.client)
        cur = self.qid.currentText()
        self.qid.blockSignals(True)
        self.qid.clear()
        self.qid.addItems([q.id for q in log.inquiries])
        if cur:
            self.qid.setCurrentText(cur)
        self.qid.blockSignals(False)
        role = self.role.currentText()
        rows = []
        for q in log.inquiries:
            v = M.mask_inquiry(q, role=role)
            rows.append([q.id, S.status_of(log, q.id), v["판매처"], v["위탁계정"], v["문의유형"],
                         v["고객이름"], v["연락처"], v["문의내용"]])
        K.set_rows(self.tbl, rows)
