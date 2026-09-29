"""셀독등록원장 2단계 — 설정 탭 '원장' 카드와 실행 시작 원장 반영(Qt 믹스인).

app_qt.App 이 상속한다. App 쪽에서 쓰는 것: _card·log·run_bg·creds_store·_save_shared·_store_passwords_map·
_set_input_list·gs_input_edit. 원장 로직은 registry_ui(→ registry/registry_gsheet) 호출만.
쓰기 안전규약(DOMAIN_DESIGN §5.4): [원장 미리보기](dry_run) → 사람이 [원장 반영] 확인 → 실행.
SSOT=designs/LEDGER_REGISTRY.md §4-1·§10-1.
"""
from __future__ import annotations

from typing import Any, Callable

from PySide6 import QtCore, QtWidgets

import registry_ui


class RegistryPanelMixin:
    # App 이 제공하는 것(정적검사용 선언)
    creds_store: Any
    gs_input_edit: Any
    log: Callable[[str], None]
    run_bg: Callable[..., None]
    _card: Callable[[str], Any]
    _save_shared: Callable[[str, str], None]
    _set_input_list: Callable[[Any, str], None]
    _store_passwords_map: Callable[..., int]
    _guard_busy: Callable[[], bool]
    # ── 설정 카드 ────────────────────────────────────────────
    def _registry_card(self):
        st = QtCore.QSettings("coupang-analytics", "ui")
        card = self._card("셀독등록원장 (지우지 않고 쌓는 원장 — 관리대장과 별도 구글시트)")
        g = QtWidgets.QGridLayout(card)
        g.setColumnStretch(1, 1)

        self.reg_url_edit = QtWidgets.QLineEdit(st.value(registry_ui.KEY_URL, "", type=str))
        self.reg_url_edit.setPlaceholderText("원장 구글시트 링크 또는 ID — 비우면 원장 미사용(서비스계정 '편집자' 공유)")
        self.reg_url_edit.editingFinished.connect(
            lambda: self._save_shared(registry_ui.KEY_URL, self.reg_url_edit.text().strip()))
        btns = QtWidgets.QHBoxLayout()
        self.reg_preview_btn = QtWidgets.QPushButton("원장 미리보기")
        self.reg_preview_btn.clicked.connect(lambda: self.do_registry_sync(dry_run=True))
        self.reg_apply_btn = QtWidgets.QPushButton("원장 반영")
        self.reg_apply_btn.clicked.connect(lambda: self.do_registry_sync(dry_run=False))
        btns.addWidget(self.reg_preview_btn)
        btns.addWidget(self.reg_apply_btn)
        g.addWidget(QtWidgets.QLabel("원장 링크"), 0, 0)
        g.addWidget(self.reg_url_edit, 0, 1)
        g.addLayout(btns, 0, 2)

        # 2-3 비밀번호 불일치(A안): 목록 → 사람이 고른 계정만 이전 비밀번호로 1회
        self.reg_pw_list = QtWidgets.QListWidget()
        self.reg_pw_list.setMaximumHeight(110)
        pw_btns = QtWidgets.QVBoxLayout()
        self.reg_pw_refresh_btn = QtWidgets.QPushButton("불일치 목록 보기")
        self.reg_pw_refresh_btn.clicked.connect(self.do_registry_pw_mismatch)
        self.reg_pw_retry_btn = QtWidgets.QPushButton("이전 비밀번호로 1회 시도")
        self.reg_pw_retry_btn.setEnabled(False)          # 목록에서 계정을 골라야 켜짐
        self.reg_pw_retry_btn.setToolTip("고른 계정만 원장 이력의 직전 비밀번호로 1회 로그인(자동 재시도 없음)")
        self.reg_pw_retry_btn.clicked.connect(self.do_registry_pw_retry)
        self.reg_pw_list.itemSelectionChanged.connect(
            lambda: self.reg_pw_retry_btn.setEnabled(bool(self.reg_pw_list.selectedItems())))
        pw_btns.addWidget(self.reg_pw_refresh_btn)
        pw_btns.addWidget(self.reg_pw_retry_btn)
        pw_btns.addStretch(1)
        g.addWidget(QtWidgets.QLabel("비밀번호 불일치"), 1, 0, QtCore.Qt.AlignTop)
        g.addWidget(self.reg_pw_list, 1, 1)
        g.addLayout(pw_btns, 1, 2)
        return card

    def _registry_urls(self) -> tuple[str, str]:
        return self.reg_url_edit.text().strip(), self.gs_input_edit.text().strip()

    # ── 2-1 수동: 미리보기 / 반영 ────────────────────────────
    def do_registry_sync(self, dry_run: bool):
        reg_url, in_url = self._registry_urls()
        if not (reg_url and in_url):
            QtWidgets.QMessageBox.information(self, "링크 필요", "원장 링크와 관리대장(입력) 링크를 먼저 등록하세요.")
            return
        self._save_shared(registry_ui.KEY_URL, reg_url)
        if not dry_run and QtWidgets.QMessageBox.question(
                self, "원장 반영 확인",
                "관리대장 내용을 원장에 반영합니다(이력 추가·원장 쓰기).\n"
                "먼저 [원장 미리보기]로 바뀔 내용을 확인하셨나요?\n\n반영할까요?") != QtWidgets.QMessageBox.Yes:
            self.log("[원장] 반영 취소됨")
            return
        self.log(f"[원장] {'미리보기(쓰기 없음)' if dry_run else '반영'} 시작 — 관리대장 → 원장")
        btn = self.reg_preview_btn if dry_run else self.reg_apply_btn
        self.run_bg(lambda: registry_ui.sync(reg_url, in_url, self.creds_store, self.log, dry_run=dry_run),
                    on_done=lambda _r: self.log(f"[원장] {'미리보기' if dry_run else '반영'} 완료"), btn=btn)

    # ── 2-3: 비밀번호 불일치 목록 ───────────────────────────
    def do_registry_pw_mismatch(self):
        reg_url, _ = self._registry_urls()
        if not reg_url:
            QtWidgets.QMessageBox.information(self, "링크 필요", "원장 링크를 먼저 등록하세요.")
            return
        self.run_bg(lambda: registry_ui.password_mismatch_accounts(
            registry_ui.load(reg_url, self.creds_store, self.log)),
            on_done=self._show_pw_mismatch, btn=self.reg_pw_refresh_btn)

    def _show_pw_mismatch(self, rows):
        self.reg_pw_list.clear()
        for aid, biz, day in rows:
            item = QtWidgets.QListWidgetItem(f"{biz or '(사업자명 없음)'} · {aid} · 확인일 {day or '-'}")
            item.setData(QtCore.Qt.UserRole, aid)
            self.reg_pw_list.addItem(item)
        self.log(f"[원장] 비밀번호 불일치 {len(rows)}개 계정"
                 + (" — 쿠팡 비밀번호 변경 여부 확인 필요" if rows else ""))

    def do_registry_pw_retry(self):
        """2-3(A안): 고른 계정의 직전 비밀번호를 원장 이력에서 찾아 → 사람 확인 → 1회 로그인."""
        items = self.reg_pw_list.selectedItems()
        reg_url, _ = self._registry_urls()
        if not items or not reg_url or self._guard_busy():
            return
        aid = items[0].data(QtCore.Qt.UserRole)
        self.run_bg(lambda: registry_ui.previous_password(reg_url, self.creds_store, aid, self.log),
                    on_done=lambda pw: self._confirm_pw_retry(reg_url, aid, pw), btn=self.reg_pw_retry_btn)

    def _confirm_pw_retry(self, reg_url: str, aid: str, pw):
        if not pw:
            self.log(f"[원장] {aid} 이전 비밀번호 없음(계정이력에 비밀번호 변경 기록 없음) — 시도하지 않습니다")
            QtWidgets.QMessageBox.information(self, "이전 비밀번호 없음",
                                              f"{aid} 계정은 원장 이력에 이전 비밀번호가 없습니다.")
            return
        if self._guard_busy() or QtWidgets.QMessageBox.question(
                self, "이전 비밀번호로 1회 시도",
                f"{aid} 계정을 원장 이력의 **직전 비밀번호**로 1회만 로그인합니다.\n"
                "보이는 창이 뜨며, 2차인증이 나오면 직접 처리하세요. 실패해도 다시 시도하지 않습니다.\n\n진행할까요?"
        ) != QtWidgets.QMessageBox.Yes:
            self.log(f"[원장] {aid} 이전 비밀번호 시도 취소됨")
            return
        self.log(f"[원장] {aid} 이전 비밀번호로 1회 로그인 시도")
        self.run_bg(lambda: registry_ui.try_previous_password(reg_url, self.creds_store, aid, pw, self.log),
                    on_done=lambda ok: self.do_registry_pw_mismatch() if ok else None,
                    btn=self.reg_pw_retry_btn, exclusive=True)   # 브라우저 = 다른 실행과 동시 금지

    # ── 2-4: 입력소스 = 원장 ────────────────────────────────
    def _apply_input_registry(self, url: str) -> bool:
        """원장 → 관리중 계정·상품 입력 + 비밀번호 DPAPI 저장(GUI 스레드용). 실패는 예외로 올림."""
        il, pw = registry_ui.load_input(url, self.creds_store, self.log)
        self._set_input_list(il, "[원장] 관리중")
        self._store_passwords_map(pw, quiet=True)
        return True

    # ── 2-1 자동: 실행 시작(백업 직후) — 백그라운드 스레드에서 호출 ──
    def _registry_presync(self, il, gs_in: str):
        """원장 링크가 있으면 원장 자동 반영 1회(비치명). 입력소스=원장이고 반영에 성공하면 방금 반영된 원장으로
        입력을 다시 구성해 돌려준다(화면 위젯은 건드리지 않음 — 작업 스레드). 반환=(입력, 원장 링크 or None)."""
        st = QtCore.QSettings("coupang-analytics", "ui")
        reg_url = st.value(registry_ui.KEY_URL, "", type=str).strip()
        if not registry_ui.presync(reg_url, gs_in, self.creds_store, self.log):
            return il, (reg_url or None)
        if st.value("input/source", "", type=str) == registry_ui.SOURCE_REGISTRY:
            try:
                il, pw = registry_ui.load_input(reg_url, self.creds_store, self.log)
                self._store_passwords_map(pw, quiet=True)
            except Exception as exc:
                self.log(f"[원장] 반영 후 입력 다시 읽기 실패({exc.__class__.__name__}): {exc} — 시작 때 읽은 입력으로 진행")
        return il, reg_url
