"""회사보유재고(판매자배송) — 정산 탭 '회사 재고' 카드(Qt 믹스인). app_qt.App 이 상속한다.
재고현황 링크 입력칸은 **설정 탭**(구글 시트 연동 카드)에 있다(2026-10-03 소유자: 설정 일원화) — 여기선 상태만.

재고현황 구글시트(stock/url) → 관리대장(gsheet/input_url) '회사보유재고' 열 역기록. 로직은 company_stock 호출만
(요약·미매칭 로그도 백엔드가 남긴다). 야간 무인 실행 끝의 자동 반영은 app_qt 가 pipeline.push_company_stock 으로.
쓰기 안전규약: [미리보기](dry_run) → 사람이 [관리대장에 반영] 확인 → 실행.
"""
from __future__ import annotations

from typing import Any, Callable

from PySide6 import QtCore, QtWidgets

from coupang_analytics import company_stock

KEY_STOCK_URL = "stock/url"   # 재고현황 구글시트 링크(관리대장·결과·원장과 별도)


class StockPanelMixin:
    # App 이 제공하는 것(정적검사용 선언)
    gs_input_edit: Any
    stock_url_edit: Any            # 설정 탭 '구글 시트 연동' 카드의 재고현황 링크칸
    log: Callable[[str], None]
    run_bg: Callable[..., None]
    _card: Callable[[str], Any]
    _save_shared: Callable[[str, str], None]
    _goto_link_setting: Callable[[str], None]

    @staticmethod
    def _stock_url() -> str:
        """야간/실행 끝 자동 반영용 — 저장된 재고현황 링크(작업 스레드에서도 안전)."""
        return QtCore.QSettings("coupang-analytics", "ui").value(KEY_STOCK_URL, "", type=str).strip()

    def _stock_card(self):
        card = self._card("회사 재고 (판매자배송 — 재고현황 → 관리대장 '회사보유재고' 열)")
        g = QtWidgets.QGridLayout(card)
        g.setColumnStretch(1, 1)
        self.stock_state_lbl = QtWidgets.QLabel()          # 링크 설정 상태(미설정=경고)
        self.stock_state_lbl.setWordWrap(True)
        go = QtWidgets.QPushButton("설정에서 변경")
        go.clicked.connect(lambda: self._goto_link_setting("stock"))
        btns = QtWidgets.QHBoxLayout()
        self.stock_preview_btn = QtWidgets.QPushButton("미리보기")
        self.stock_preview_btn.clicked.connect(lambda: self.do_company_stock(dry_run=True))
        self.stock_apply_btn = QtWidgets.QPushButton("관리대장에 반영")
        self.stock_apply_btn.clicked.connect(lambda: self.do_company_stock(dry_run=False))
        btns.addWidget(self.stock_preview_btn)
        btns.addWidget(self.stock_apply_btn)
        btns.addWidget(go)
        g.addWidget(QtWidgets.QLabel("재고현황 링크"), 0, 0)
        g.addWidget(self.stock_state_lbl, 0, 1)
        g.addLayout(btns, 0, 2)
        note = QtWidgets.QLabel("매일 밤 무인 실행 끝에 자동 반영(그로스 재고 역기록 다음). "
                                "재고현황·관리대장 링크는 '설정' 탭의 '구글 시트 연동'에서 등록합니다.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        g.addWidget(note, 1, 0, 1, 3)
        self._refresh_stock_state()
        return card

    def _refresh_stock_state(self):
        """재고현황 링크 상태를 한눈에 — 비었으면 경고(야간 회사재고 반영이 조용히 빠지는 것 방지)."""
        url = self.stock_url_edit.text().strip()
        if url:
            text, style = "✅ 재고현황 링크 설정됨 — 무인 실행 끝에 회사 재고 반영", "color: #047857;"
        else:
            text, style = ("⚠ 재고현황 링크 미설정 — 회사 재고가 관리대장에 반영되지 않습니다",
                           "color: #b91c1c; font-weight: 700;")
        lbl = getattr(self, "stock_state_lbl", None)   # 정산 탭이 아직 안 만들어졌으면 건너뜀
        if lbl is not None:
            lbl.setText(text)
            lbl.setStyleSheet(style)

    def do_company_stock(self, dry_run: bool):
        stock_url, in_url = self.stock_url_edit.text().strip(), self.gs_input_edit.text().strip()
        if not (stock_url and in_url):
            QtWidgets.QMessageBox.information(self, "링크 필요",
                                              "재고현황 링크와 관리대장(입력) 링크를 '설정' 탭에서 먼저 등록하세요.")
            return
        self._save_shared(KEY_STOCK_URL, stock_url)
        self._refresh_stock_state()
        if not dry_run and QtWidgets.QMessageBox.question(
                self, "관리대장 반영 확인",
                "재고현황의 회사 재고를 관리대장 '회사보유재고' 열에 씁니다.\n"
                "먼저 [미리보기]로 바뀔 내용을 확인하셨나요?\n\n반영할까요?") != QtWidgets.QMessageBox.Yes:
            self.log("[회사재고] 반영 취소됨")
            return
        self.log(f"[회사재고] {'미리보기(저장 안 함)' if dry_run else '관리대장 반영'} 시작")
        self.run_bg(lambda: company_stock.run_company_stock(stock_url, in_url, dry_run=dry_run, on_log=self.log),
                    on_done=lambda _r: None, btn=self.stock_preview_btn if dry_run else self.stock_apply_btn)
