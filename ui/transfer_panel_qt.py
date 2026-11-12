"""셀독전환 정산 탭(Qt 믹스인) — 미정산 셀독전환자 ①②계정 정산 1단계 = 로그인 확인(소유자 2026-10-22·D-111).

app_qt.App 이 상속한다. 실행은 정산 프로그램의 `transfer-login` 명령(app_process.start_transfer_login · 창 없음)이고,
이 탭은 결과 파일(output/정산_셀독전환/로그인확인_최신.json)과 로그 파일을 3초마다 읽어 보여 준다(배포 exe 는 콘솔이
없어 화면 출력을 못 받음). 로그인 코드·규칙은 앱 ①과 같음(transfer_login 문서).
2단계 = 정산 자료 받기(`transfer-settle` · D-187): 18:00 무인 앱이 매일 함께 띄우고(체크로 끔), [지금 받기]로도 띄움 —
앱 실행·정산 자동 수집이 끝난 뒤 받고 17:40 에 멈춤. 결과 = output/정산_셀독전환/셀독전환_정산내역_누적.xlsx.
"""
from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from PySide6 import QtCore, QtWidgets

from coupang_analytics import app_process, appconfig
from coupang_analytics import transfer_accounts as TA
from coupang_analytics import transfer_login as TL
from coupang_analytics import transfer_settle as TS

POLL_MS = 3000


def _tail(folder: Path, pattern: str, since: float, cur: tuple[Path, int] | None) -> tuple[tuple[Path, int] | None, list]:
    """이번 실행의 로그 파일(시작 뒤 생긴 가장 새 것)에서 새 줄만 → (읽은 위치, 새 줄)."""
    if cur is None:
        logs = [p for p in folder.glob(pattern) if p.stat().st_mtime >= since - 2]
        if not logs:
            return None, []
        cur = (max(logs, key=lambda p: p.stat().st_mtime), 0)
    path, pos = cur
    with path.open("r", encoding="utf-8") as f:
        f.seek(pos)
        text = f.read()
        cur = (path, f.tell())
    return cur, [ln for ln in text.splitlines() if ln.strip()]


class TransferPanelMixin:
    # App 이 제공하는 것(정적검사용 선언)
    log: Callable[[str], None]
    _card: Callable[[str], Any]
    _save_shared: Callable[[str, str], None]
    _open_folder: Callable[[str], None]

    def _transfer_tab(self):
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        inner = QtWidgets.QWidget()
        scroll.setWidget(inner)
        v = QtWidgets.QVBoxLayout(inner)
        v.setContentsMargins(14, 12, 14, 12)
        sub = QtWidgets.QLabel("미정산 셀독전환자(①셀독진행·②계정수령_상품미등록) 계정의 쿠팡 정산 내역을 받기 위한 탭입니다. "
                               "1단계 = 로그인 확인(다운로드 없음) · 2단계 = 정산 자료 받기(매일 18시 뒤). 비밀번호 칸이 빈 계정은 "
                               "관리대장 비밀번호를 씁니다. 앱 실행·정산 자동 다운로드가 도는 중에는 시작하지 않고, 17:40 이 지나면 "
                               "새 계정을 시작하지 않습니다.")
        sub.setObjectName("muted")
        sub.setWordWrap(True)
        v.addWidget(sub)
        v.addWidget(self._transfer_card())
        v.addWidget(self._settle_card())
        v.addStretch(1)
        self._transfer_page = scroll   # 이 탭 화면 — 5초마다 읽는 진행 줄의 주인 탭(T-19)
        return scroll

    def _transfer_card(self):
        card = self._card("셀독전환자 로그인 확인 (계정마다 로그인만 해 보고 창을 닫음 · 계정 사이 45~75초)")
        g = QtWidgets.QGridLayout(card)
        g.setColumnStretch(1, 1)
        self.tr_file_edit = QtWidgets.QLineEdit(appconfig.get(TA.CONFIG_KEY, "") or TA.DEFAULT_PATH)
        self.tr_file_edit.editingFinished.connect(lambda: self._save_shared(TA.CONFIG_KEY, self.tr_file_edit.text().strip()))
        pick = QtWidgets.QPushButton("찾기")
        pick.clicked.connect(self._tr_pick_file)
        g.addWidget(QtWidgets.QLabel("전환자 파일"), 0, 0)
        g.addWidget(self.tr_file_edit, 0, 1)
        g.addWidget(pick, 0, 2)
        btns = QtWidgets.QHBoxLayout()
        self.tr_start_btn = QtWidgets.QPushButton("로그인 확인 시작")
        self.tr_start_btn.clicked.connect(lambda: self._tr_start(retry=False))
        self.tr_retry_btn = QtWidgets.QPushButton("성공 안 된 계정만 다시")
        self.tr_retry_btn.clicked.connect(lambda: self._tr_start(retry=True))
        self.tr_stop_btn = QtWidgets.QPushButton("중지")
        self.tr_stop_btn.setEnabled(False)
        self.tr_stop_btn.clicked.connect(self._tr_stop)
        folder = QtWidgets.QPushButton("결과 폴더 열기")
        folder.clicked.connect(lambda: self._open_folder(str(TL.OUT_DIR.resolve())))
        for b in (self.tr_start_btn, self.tr_retry_btn, self.tr_stop_btn, folder):
            btns.addWidget(b)
        btns.addStretch(1)
        g.addLayout(btns, 1, 0, 1, 3)
        self.tr_state_lbl = QtWidgets.QLabel()
        self.tr_state_lbl.setWordWrap(True)
        g.addWidget(self.tr_state_lbl, 2, 0, 1, 3)
        self._tr_proc: subprocess.Popen | None = None
        self._tr_log: tuple[Path, int] | None = None
        self._tr_since = 0.0
        self._tr_timer = QtCore.QTimer(self)
        self._tr_timer.setInterval(POLL_MS)
        self._tr_timer.timeout.connect(self._tr_poll)
        self._tr_refresh()
        return card

    def _tr_pick_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "셀독전환자 파일", str(Path(self.tr_file_edit.text()).parent),
                                                        "엑셀 (*.xlsx)")
        if path:
            self.tr_file_edit.setText(path)
            self._save_shared(TA.CONFIG_KEY, path)
            self._tr_refresh()

    def _tr_refresh(self) -> None:
        """파일 계정 수 + 마지막 결과(성공·연락 필요·차단·건너뜀·미확인)."""
        try:
            accts, _w = TA.read_transfer_file(self.tr_file_edit.text().strip())
        except TA.TransferFileError as exc:
            self.tr_state_lbl.setText(f"⛔ 파일 오류 — {exc}")
            return
        c = TL.counts(accts, TL.load_state())
        run = " · ⏳ 실행 중" if self._tr_running() else ""
        self.tr_state_lbl.setText(f"①② {len(accts)}계정 — 성공 {c[TL.OK]} · 실패(연락 필요) {c[TL.FAIL]} · 차단 {c[TL.BLOCK]} · "
                                  f"건너뜀 {c[TL.SKIP]} · 미확인 {c['미확인']}{run}  (결과 엑셀 = 결과 폴더의 로그인확인_*.xlsx)")

    def _tr_running(self) -> bool:
        return self._tr_proc is not None and self._tr_proc.poll() is None

    def _tr_start(self, retry: bool) -> None:
        if self._tr_running():
            self.log("[셀독전환] 이미 로그인 확인이 도는 중입니다")
            return
        self._save_shared(TA.CONFIG_KEY, self.tr_file_edit.text().strip())
        what = "성공 안 된 계정만" if retry else "파일의 ①② 전 계정"
        ok = QtWidgets.QMessageBox.question(
            self, "셀독전환자 로그인 확인",
            f"{what} 쿠팡 로그인을 차례로 확인합니다(계정당 1~2분 + 사이 45~75초).\n"
            "비밀번호가 틀리면 그 계정은 다시 넣지 않고 '연락 필요'로 남깁니다.\n17:40 이 지나면 새 계정을 시작하지 않습니다. 시작할까요?")
        if ok != QtWidgets.QMessageBox.Yes:
            return
        self._tr_since = time.time()
        self._tr_log = None
        self._tr_proc = app_process.start_transfer_login(self.log, retry, self.tr_file_edit.text().strip())
        if self._tr_proc is None:
            return
        self.log(f"[셀독전환] 로그인 확인 시작({what}) — 진행 줄은 여기 로그에 이어서 표시")
        for b, on in ((self.tr_start_btn, False), (self.tr_retry_btn, False), (self.tr_stop_btn, True)):
            b.setEnabled(on)
        self._tr_timer.start()
        self._tr_refresh()

    def _tr_stop(self) -> None:
        proc = self._tr_proc
        if proc is None or proc.poll() is not None:
            return
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True,
                       creationflags=0x08000000)   # 그 실행과 띄운 Chrome 까지(CREATE_NO_WINDOW)
        self.log("[셀독전환] 로그인 확인 중지 — 끝난 계정 결과는 남음('성공 안 된 계정만 다시'로 이어서)")

    def _tr_poll(self) -> None:
        self._tr_tail_log()
        self._tr_refresh()
        if not self._tr_running():
            self._tr_timer.stop()
            for b, on in ((self.tr_start_btn, True), (self.tr_retry_btn, True), (self.tr_stop_btn, False)):
                b.setEnabled(on)
            self.log("[셀독전환] 로그인 확인 끝 — 결과 폴더의 로그인확인_*.xlsx('연락 필요' 시트) 확인",
                     page=self._transfer_page)

    def _tr_tail_log(self) -> None:
        """이번 실행의 로그 파일에서 새 줄만 앱 로그로."""
        self._tr_log, lines = _tail(TL.OUT_DIR / "로그", "로그인확인_*.log", self._tr_since, self._tr_log)
        for line in lines:
            self.log(f"[셀독전환] {line}", page=self._transfer_page)   # 다른 탭을 보는 중에도 이 탭에(T-19)

    # ── 2단계: 정산 자료 받기(D-187) ─────────────────────────────
    def _settle_card(self):
        card = self._card("셀독전환자 정산 자료 받기 (2단계 · 2026-01-01 부터 · 계정당 한 번에 30건 · 받은 것은 다시 안 받음)")
        g = QtWidgets.QGridLayout(card)
        g.setColumnStretch(1, 1)
        self.ts_daily_chk = QtWidgets.QCheckBox("매일 18시 뒤 자동으로 받기 — 18:00 무인 실행이 함께 띄움 · 앱 실행·정산 자동 수집이 "
                                                "끝난 뒤 받음 · 로그인 '실패' 계정은 넣지 않음")
        self.ts_daily_chk.setChecked(TS.daily_on())
        self.ts_daily_chk.toggled.connect(lambda on: self._save_shared(TS.DAILY_KEY, "1" if on else "0"))
        g.addWidget(self.ts_daily_chk, 0, 0, 1, 3)
        btns = QtWidgets.QHBoxLayout()
        self.ts_start_btn = QtWidgets.QPushButton("지금 받기")
        self.ts_start_btn.clicked.connect(self._ts_start)
        self.ts_stop_btn = QtWidgets.QPushButton("중지")
        self.ts_stop_btn.setEnabled(False)
        self.ts_stop_btn.clicked.connect(self._ts_stop)
        book = QtWidgets.QPushButton("누적 파일 폴더 열기")
        book.clicked.connect(lambda: self._open_folder(str(TS.OUT_DIR.resolve())))
        for b in (self.ts_start_btn, self.ts_stop_btn, book):
            btns.addWidget(b)
        btns.addStretch(1)
        g.addLayout(btns, 1, 0, 1, 3)
        self.ts_state_lbl = QtWidgets.QLabel()
        self.ts_state_lbl.setWordWrap(True)
        g.addWidget(self.ts_state_lbl, 2, 0, 1, 3)
        self._ts_proc: subprocess.Popen | None = None
        self._ts_log: tuple[Path, int] | None = None
        self._ts_since = 0.0
        self._ts_timer = QtCore.QTimer(self)
        self._ts_timer.setInterval(POLL_MS)
        self._ts_timer.timeout.connect(self._ts_poll)
        self._ts_refresh()
        return card

    def _ts_running(self) -> bool:
        return self._ts_proc is not None and self._ts_proc.poll() is None

    def _ts_refresh(self) -> None:
        """대상 계정 수(로그인 '실패' 제외) · 누적 파일 마지막 갱신."""
        try:
            accts, _w = TA.read_transfer_file(self.tr_file_edit.text().strip())
        except TA.TransferFileError as exc:
            self.ts_state_lbl.setText(f"⛔ 파일 오류 — {exc}")
            return
        n = len(TS.pick_targets(accts, TL.load_state()))
        book = TS.CUMULATIVE
        when = f"{datetime.fromtimestamp(book.stat().st_mtime):%m-%d %H:%M}" if book.exists() else "아직 없음"
        run = " · ⏳ 실행 중(앱·정산 자동 수집이 끝날 때까지 기다릴 수 있음)" if self._ts_running() else ""
        self.ts_state_lbl.setText(f"대상 {n}계정 / {len(accts)}계정(로그인 '실패' 제외) · 누적 파일 {book.name} — {when}{run}")

    def _ts_start(self) -> None:
        if self._ts_running() or self._tr_running():
            self.log("[셀독전환] 이미 셀독전환 실행(로그인 확인·정산 자료 받기)이 도는 중입니다")
            return
        self._save_shared(TA.CONFIG_KEY, self.tr_file_edit.text().strip())
        ok = QtWidgets.QMessageBox.question(
            self, "셀독전환자 정산 자료 받기",
            "로그인 '실패'가 아닌 계정마다 로그인해 2026-01-01 부터 정산 자료를 받습니다(계정당 한 번에 30건 · 요청 사이 45~75초).\n"
            "앱 실행·정산 자동 수집이 돌거나 17:40~20:40 이면 끝날 때까지 기다렸다 시작하고, 17:40 에 멈춥니다. 시작할까요?")
        if ok != QtWidgets.QMessageBox.Yes:
            return
        self._ts_since, self._ts_log = time.time(), None
        self._ts_proc = app_process.start_transfer_settle(self.log, os.getpid())
        if self._ts_proc is None:
            return
        self.ts_start_btn.setEnabled(False)
        self.ts_stop_btn.setEnabled(True)
        self._ts_timer.start()
        self._ts_refresh()

    def _ts_stop(self) -> None:
        proc = self._ts_proc
        if proc is None or proc.poll() is not None:
            return
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True,
                       creationflags=0x08000000)   # 그 실행과 띄운 Chrome 까지(CREATE_NO_WINDOW)
        self.log("[셀독전환] 정산 자료 받기 중지 — 받은 파일·요청 기록은 남음(다음 실행에서 이어서)")

    def _ts_poll(self) -> None:
        self._ts_log, lines = _tail(TS.STORE_DIR / "로그", "실행_*.log", self._ts_since, self._ts_log)
        for line in lines:
            self.log(f"[셀독전환 정산] {line}", page=self._transfer_page)
        self._ts_refresh()
        if not self._ts_running():
            self._ts_timer.stop()
            self.ts_start_btn.setEnabled(True)
            self.ts_stop_btn.setEnabled(False)
            self.log(f"[셀독전환] 정산 자료 받기 끝 — 누적 파일 {TS.CUMULATIVE.resolve()}", page=self._transfer_page)
