"""설정 탭 '샵마인 로그인 입력'(D-389) — 샵마인 로그인 자격을 한 번 입력하면 매일 비번 동기화가 저절로 돈다.

- 입력 = 업체ID·사용자ID·비밀번호(비밀번호 칸은 화면에 안 보임) → 즉시 credstore(DPAPI·이 PC 사용자 전용) 저장
  (`shopmine_sync.make_login`→`store_login` — CLI `tools/shopmine_sync.py setup` 과 같은 함수).
- 저장 직후 연결 확인 1회(배경) = 로그인 + 계정 목록·필드 확인(discover 자동) · 관리대장은 안 건드림.
  샵마인이 거부하면 거부 표시 → 매일 다시 로그인하지 않음(잠금 방지) · 다시 입력하면 풀림.
- 비밀번호 값은 로그·라벨·파일 어디에도 안 남긴다(라벨은 '저장됨/연결됨/거부'만).
"""
from __future__ import annotations

from PySide6 import QtWidgets

from coupang_analytics import shopmine_sync

LBL_NONE = "(샵마인 로그인 미입력 — 비번 동기화 안 함)"
LBL_SAVED = "(샵마인 로그인: 저장됨 — 매일 자동 동기화)"
LBL_REJECTED = "(샵마인 로그인: 샵마인이 거부함 — 다시 입력하세요)"


def ask_login(parent) -> tuple[str, str, str] | None:
    """업체ID·사용자ID·비밀번호 입력 창 → (업체ID, 사용자ID, 비밀번호) · 취소/빈 값이면 None."""
    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle("샵마인 로그인 입력")
    form = QtWidgets.QFormLayout(dlg)
    note = QtWidgets.QLabel("샵마인 프로그램에 로그인할 때 쓰는 정보를 한 번 넣으세요.\n"
                            "이 PC 에만 암호화해 저장하고, 비밀번호는 화면·로그에 보이지 않습니다.")
    note.setWordWrap(True)
    form.addRow(note)
    company, user, pw = QtWidgets.QLineEdit(), QtWidgets.QLineEdit(), QtWidgets.QLineEdit()
    pw.setEchoMode(QtWidgets.QLineEdit.Password)
    form.addRow("업체 ID", company)
    form.addRow("사용자 ID", user)
    form.addRow("비밀번호", pw)
    box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
    box.accepted.connect(dlg.accept)
    box.rejected.connect(dlg.reject)
    form.addRow(box)
    dlg.fields = (company, user, pw)          # 시험용 손잡이(값은 창 안에만)
    if dlg.exec() != QtWidgets.QDialog.Accepted:
        return None
    vals = company.text().strip(), user.text().strip(), pw.text()
    return vals if vals[0] and vals[2].strip() else None


def saved_label(store) -> str:
    """저장 상태 라벨(값 없음) — 미입력 / 저장됨 / 거부됨."""
    creds = shopmine_sync.load_login(store)
    if creds is None:
        return LBL_NONE
    return LBL_REJECTED if creds.get(shopmine_sync.REJECTED_FLAG) else LBL_SAVED


class ShopmineLoginMixin:
    """App 에 섞는 설정 탭 동작 — self.creds_store·self.log·self.run_bg·self.shopmine_lbl 을 쓴다."""

    def load_shopmine_login(self):
        got = ask_login(self)
        if got is None:
            return
        try:
            shopmine_sync.store_login(shopmine_sync.make_login(*got), self.creds_store)
        except Exception as exc:                     # noqa: BLE001  저장 실패 = 사유 표시 후 중단
            self.log(f"[샵마인] 로그인 정보 저장 실패({exc.__class__.__name__}): {exc}")
            QtWidgets.QMessageBox.warning(self, "샵마인 로그인 저장 실패", str(exc))
            return
        del got
        self.shopmine_lbl.setText("(샵마인 로그인: 저장됨 — 연결 확인 중…)")
        self.log("[샵마인] 로그인 정보 저장됨(이 PC 암호화) — 연결 확인 중…")
        self.run_bg(lambda: shopmine_sync.check_login(self.creds_store, self.log), on_done=self._shopmine_checked)

    def _shopmine_checked(self, result):
        ok, msg = result
        self.shopmine_lbl.setText(f"(샵마인 로그인: {msg[:60]})" if ok else saved_label(self.creds_store))
        self.log(f"[샵마인] 연결 확인 {'OK' if ok else '실패'} — {msg}"
                 + (" · 관리대장 비번 동기화는 매일 관리대장을 읽을 때 자동(첫날은 대조 리포트만)" if ok else ""))

    def _show_saved_shopmine(self):
        try:
            self.shopmine_lbl.setText(saved_label(self.creds_store))
        except Exception as exc:                     # noqa: BLE001  앱 시작을 막지 않게 — 사유는 라벨·로그에 남김
            self.shopmine_lbl.setText(f"(샵마인 로그인: 저장값 확인 실패 — {exc.__class__.__name__})")
            self.log(f"[샵마인] 저장된 로그인 정보 확인 실패({exc.__class__.__name__}): {exc}")
