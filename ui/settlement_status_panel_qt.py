"""정산 자동 다운로드 상태 — 정산 탭 '상태' 카드(Qt 믹스인). app_qt.App 이 상속한다.

창 없는(console=False) '정산다운로드.exe watch' 가 output/정산/로그/_현재상태.txt 에 매 5분 덮어쓰는
상태(settlement_runlog.RunLog.heartbeat)와 최신 실행 로그를 **읽기만** 해서, 운용 PC 사람이 색으로
한눈에(작동중/대기중/완료/오류·살아있나) 확인한다. 야간 파이프라인·정산 다운로드 로직은 건드리지 않는다.

순수 읽기 로직 `read_settlement_status(로그폴더)` 는 Qt 없이 오프라인 검증한다(게이트 핀).
"""
from __future__ import annotations

import csv
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from coupang_analytics.apppaths import output_dir as app_output_dir

# PySide6 는 Qt 가 실제로 필요한 메서드(_settlement_status_card) 안에서 지연 import 한다 →
# 순수 읽기 로직 read_settlement_status 는 Qt 없는 환경(오프라인 게이트)에서도 그대로 import·검증된다.

STALE_SEC = 12 * 60   # 마지막 활동이 이보다 오래 전이면 '멈춤 의심'(watch 폴링 5분 + 여유)
_LABELS = {"상태": "상태", "갱신": "갱신", "내용": "내용", "실행ID": "실행ID", "상세 로그": "상세로그"}
# 상태 → (배지 문구, 배경색, 글자색)
_BADGE = {
    "작동중": ("● 작동 중", "#047857", "#ffffff"),
    "대기중": ("● 대기 중 (앱 판매수집 끝나면 시작)", "#2563eb", "#ffffff"),
    "완료": ("● 이번 분량 완료", "#334155", "#ffffff"),
    "오류": ("● 오류 — 아래 로그 확인", "#b91c1c", "#ffffff"),
    "시작함": ("● 시작함 — 곧 상태 갱신", "#2563eb", "#ffffff"),
    "중지됨": ("● 중지됨 (사용자가 멈춤)", "#64748b", "#ffffff"),
}
_UNKNOWN_BADGE = ("정산 자동 다운로드가 아직 실행된 적 없음", "#94a3b8", "#ffffff")
_RESULT_ORDER = ("정상", "건너뜀", "대기", "실패", "차단")


def _dt(s: str | None) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S") if s else None
    except (ValueError, TypeError):
        return None


def _parse_status_file(path: Path) -> dict:
    """_현재상태.txt(라벨: 값 줄들) → dict. 파일 없으면 {}."""
    if not path.exists():
        return {}
    out: dict = {}
    for ln in path.read_text(encoding="utf-8").splitlines():
        key, sep, val = ln.partition(":")
        if sep and key.strip() in _LABELS:
            out[_LABELS[key.strip()]] = val.strip()
    return out


def _newest_log(log_dir: Path) -> Path | None:
    logs = list(log_dir.glob("실행_*.log"))
    return max(logs, key=lambda p: p.stat().st_mtime) if logs else None


def _tail(path: Path, n: int) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except OSError:
        return []


def _today_counts(log_dir: Path, today: str) -> dict:
    """처리기록_누적.csv 에서 오늘 날짜(YYYY-MM-DD) 결과별 건수."""
    p = log_dir / "처리기록_누적.csv"
    if not p.exists():
        return {}
    counts: dict = {}
    with p.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if (row.get("시각") or "").startswith(today):
                r = row.get("결과") or "?"
                counts[r] = counts.get(r, 0) + 1
    return counts


def read_settlement_status(log_dir, *, now: datetime | None = None) -> dict:
    """정산 로그 폴더를 읽어 화면이 그릴 상태 dict 를 만든다(읽기 전용·부작용 없음).

    '마지막 활동' = 상태 파일 갱신 시각과 최신 실행 로그 수정 시각 중 더 최근 것(작동 중엔 상태 파일은
    가만있고 로그가 줄마다 갱신되므로 둘 다 본다). 작동중/대기중인데 그게 STALE_SEC 보다 오래됐으면
    '멈춤 의심'(야간 ~10h 멈춤 같은 상황을 사람이 알아채게)."""
    now = now or datetime.now()
    log_dir = Path(log_dir)
    st = _parse_status_file(log_dir / "_현재상태.txt")
    newest = _newest_log(log_dir) if log_dir.exists() else None
    stamps = [d for d in (_dt(st.get("갱신")),) if d]
    if newest:
        stamps.append(datetime.fromtimestamp(newest.stat().st_mtime))
    last_active = max(stamps) if stamps else None
    age = (now - last_active).total_seconds() if last_active else None
    status = st.get("상태", "")
    live_expected = status in ("작동중", "대기중")
    return {
        "exists": bool(st) or newest is not None,
        "상태": status,
        "내용": st.get("내용", ""),
        "실행ID": st.get("실행ID", ""),
        "last_active": last_active,
        "age_sec": age,
        "stale": bool(live_expected and age is not None and age > STALE_SEC),
        "live_expected": live_expected,
        "log_name": newest.name if newest else "",
        "tail": _tail(newest, 25) if newest else [],
        "today_counts": _today_counts(log_dir, now.strftime("%Y-%m-%d")),
    }


def _age_text(age_sec: float | None) -> str:
    if age_sec is None:
        return ""
    m = int(age_sec // 60)
    if m < 1:
        return "방금 전"
    if m < 60:
        return f"{m}분 전"
    return f"{m // 60}시간 {m % 60}분 전"


def _counts_text(counts: dict) -> str:
    if not counts:
        return "오늘 받은 기록 없음"
    ordered = [f"{k} {counts[k]}" for k in _RESULT_ORDER if k in counts]
    ordered += [f"{k} {v}" for k, v in counts.items() if k not in _RESULT_ORDER]
    return "오늘: " + " · ".join(ordered)


class SettlementStatusMixin:
    # App 이 제공하는 것(정적검사용 선언)
    _card: Callable[[str], Any]
    _open_folder: Callable[[str], None]
    log: Callable[[str], None]
    _settle_proc: Any = None

    @staticmethod
    def _settlement_log_dir() -> Path:
        return app_output_dir() / "정산" / "로그"

    def _settlement_status_card(self):
        from PySide6 import QtCore, QtWidgets   # Qt 는 여기서만 필요 — 지연 import(오프라인 게이트는 Qt 없이 리더만 씀)
        card = self._card("정산 자동 다운로드 — 지금 상태")
        v = QtWidgets.QVBoxLayout(card)
        v.setSpacing(8)
        self.settle_badge = QtWidgets.QLabel()
        self.settle_badge.setAlignment(QtCore.Qt.AlignCenter)
        self.settle_badge.setMinimumHeight(52)
        f = self.settle_badge.font()
        f.setPointSize(f.pointSize() + 5)
        f.setBold(True)
        self.settle_badge.setFont(f)
        v.addWidget(self.settle_badge)

        ctrl = QtWidgets.QHBoxLayout()
        self.settle_start_btn = QtWidgets.QPushButton("정산 시작")
        self.settle_start_btn.clicked.connect(self._settle_start)
        self.settle_stop_btn = QtWidgets.QPushButton("정산 중지")
        self.settle_stop_btn.clicked.connect(self._settle_stop)
        ctrl.addWidget(self.settle_start_btn)
        ctrl.addWidget(self.settle_stop_btn)
        ctrl.addStretch(1)
        hint = QtWidgets.QLabel("24시간 감시 — 판매수집 중엔 자동으로 멈췄다 끝나면 재개")
        hint.setObjectName("muted")
        ctrl.addWidget(hint)
        v.addLayout(ctrl)

        self.settle_active_lbl = QtWidgets.QLabel()
        self.settle_active_lbl.setWordWrap(True)
        self.settle_detail_lbl = QtWidgets.QLabel()
        self.settle_detail_lbl.setObjectName("muted")
        self.settle_detail_lbl.setWordWrap(True)
        self.settle_counts_lbl = QtWidgets.QLabel()
        self.settle_counts_lbl.setObjectName("muted")
        for w in (self.settle_active_lbl, self.settle_detail_lbl, self.settle_counts_lbl):
            v.addWidget(w)

        self.settle_log_view = QtWidgets.QPlainTextEdit()
        self.settle_log_view.setReadOnly(True)
        self.settle_log_view.setMinimumHeight(180)
        self.settle_log_view.setStyleSheet("font-family: Consolas, 'D2Coding', monospace; font-size: 12px;")
        v.addWidget(self.settle_log_view, 1)

        btns = QtWidgets.QHBoxLayout()
        refresh = QtWidgets.QPushButton("새로고침")
        refresh.clicked.connect(self._refresh_settlement_status)
        folder = QtWidgets.QPushButton("로그 폴더 열기")
        folder.clicked.connect(lambda: self._open_folder(str(self._settlement_log_dir())))
        btns.addWidget(refresh)
        btns.addWidget(folder)
        btns.addStretch(1)
        self.settle_updated_lbl = QtWidgets.QLabel()
        self.settle_updated_lbl.setObjectName("muted")
        btns.addWidget(self.settle_updated_lbl)
        v.addLayout(btns)

        self._settle_timer = QtCore.QTimer(card)
        self._settle_timer.setInterval(5000)   # 5초마다 자동 새로고침(파일만 읽음·가벼움)
        self._settle_timer.timeout.connect(self._refresh_settlement_status)
        self._settle_timer.start()
        self._refresh_settlement_status()
        return card

    def _refresh_settlement_status(self):
        if getattr(self, "settle_badge", None) is None:
            return
        info = read_settlement_status(self._settlement_log_dir())
        if not info["exists"]:
            self._set_settle_badge(*_UNKNOWN_BADGE)
            self.settle_active_lbl.setText("설치·등록 후 정산 자동 다운로드가 한 번이라도 돌면 여기에 상태가 보입니다.")
            self.settle_active_lbl.setStyleSheet("")
            self.settle_detail_lbl.setText("")
            self.settle_counts_lbl.setText("")
            self.settle_log_view.setPlainText("(아직 로그 없음)")
            self.settle_updated_lbl.setText("")
            return
        if not info["상태"]:   # 로그는 있으나 상태 파일 없음(새 버전 첫 실행 전·옛 기록만)
            self._set_settle_badge("상태 표시 준비 전 (옛 로그만 있음)", "#94a3b8", "#ffffff")
            self.settle_active_lbl.setText("최신 로그는 있지만 '지금 상태' 표시는 새 버전으로 한 번 실행된 뒤부터 보입니다.")
            self.settle_active_lbl.setStyleSheet("")
            self.settle_detail_lbl.setText("")
            self.settle_counts_lbl.setText(_counts_text(info["today_counts"]))
            self.settle_log_view.setPlainText("\n".join(info["tail"]) or "(로그 비어 있음)")
            self._scroll_log_bottom()
            self.settle_updated_lbl.setText(f"최신 로그 {info['log_name']}" if info["log_name"] else "")
            return
        self._set_settle_badge(*_BADGE.get(info["상태"], (f"● {info['상태']}", "#64748b", "#ffffff")))
        if info["stale"]:
            self.settle_active_lbl.setText(f"⚠ {_age_text(info['age_sec'])}부터 변화가 없습니다 — 멈췄을 수 있습니다. "
                                           "확인이 필요하면 담당자에게 알려 주세요.")
            self.settle_active_lbl.setStyleSheet("color:#b91c1c; font-weight:700;")
        else:
            self.settle_active_lbl.setText(f"마지막 활동: {_age_text(info['age_sec']) or '기록 없음'}")
            self.settle_active_lbl.setStyleSheet("color:#047857;" if info["live_expected"] else "")
        self.settle_detail_lbl.setText(info["내용"])
        self.settle_counts_lbl.setText(_counts_text(info["today_counts"]))
        self.settle_log_view.setPlainText("\n".join(info["tail"]) or "(로그 비어 있음)")
        self._scroll_log_bottom()
        stamp = info["last_active"]
        self.settle_updated_lbl.setText(
            (f"최신 로그 {info['log_name']} · " if info["log_name"] else "")
            + (f"갱신 {stamp:%m-%d %H:%M:%S}" if stamp else ""))

    def _set_settle_badge(self, text: str, bg: str, fg: str) -> None:
        self.settle_badge.setText(text)
        self.settle_badge.setStyleSheet(f"background:{bg}; color:{fg}; border-radius:8px; padding:8px;")

    def _scroll_log_bottom(self) -> None:
        sb = self.settle_log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── 정산 감시 시작/중지(별도 프로세스 제어) ──────────────────────────
    @staticmethod
    def _settle_watch_cmd() -> tuple[list[str], str]:
        """24시간 감시(watch)를 띄울 명령 + 작업 폴더. frozen=정산다운로드.exe(형제)·개발=python tools/..."""
        if getattr(sys, "frozen", False):
            folder = Path(sys.executable).parent
            return [str(folder / "정산다운로드.exe"), "watch"], str(folder)
        root = Path(__file__).resolve().parents[1]
        return [sys.executable, str(root / "tools" / "settlement_download.py"), "watch"], str(root)

    def _settle_start(self) -> None:
        cmd, cwd = self._settle_watch_cmd()
        if getattr(sys, "frozen", False) and not Path(cmd[0]).exists():
            self._settle_write_status("오류", f"정산다운로드.exe 를 찾을 수 없습니다: {cmd[0]}")
            self._refresh_settlement_status()
            return
        try:
            # CREATE_NO_WINDOW(0x08000000): 콘솔창 깜빡임 없이 백그라운드 실행(함정 #8). 이미 돌면 watch 잠금으로 1개만.
            self._settle_proc = subprocess.Popen(
                cmd, cwd=cwd, creationflags=0x08000000,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._settle_write_status("시작함", "정산 감시를 시작했습니다 — 곧 상태가 갱신됩니다(이미 돌고 있으면 그대로).")
        except OSError as exc:
            self.log(f"[정산] 시작 실패: {exc}")
            self._settle_write_status("오류", f"정산 시작 실패: {exc}")
        self._refresh_settlement_status()

    def _settle_stop(self) -> None:
        killed = self._kill_settlement()
        self._settle_write_status(
            "중지됨", "사용자가 정산 감시를 멈췄습니다." if killed else "중지 요청 — 실행 중인 정산이 없었습니다.")
        self._refresh_settlement_status()

    def _kill_settlement(self) -> bool:
        """정산 감시 프로세스를 종료. frozen=이름으로, 개발=우리가 띄운 PID 로. 하나라도 죽였으면 True."""
        killed = False
        if getattr(sys, "frozen", False):
            r = subprocess.run(["taskkill", "/F", "/T", "/IM", "정산다운로드.exe"],
                               creationflags=0x08000000, capture_output=True)
            killed = r.returncode == 0
        proc = getattr(self, "_settle_proc", None)
        if proc is not None and proc.poll() is None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           creationflags=0x08000000, capture_output=True)
            killed = True
        self._settle_proc = None
        return killed

    def _settle_write_status(self, status: str, detail: str) -> None:
        """시작/중지/오류처럼 프로세스가 스스로 못 남기는 상태를 앱이 _현재상태.txt 에 직접 적는다(배지 즉시 반영)."""
        d = self._settlement_log_dir()
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / "_현재상태.txt").write_text(
                "정산 자동 다운로드 — 현재 상태\n"
                f"갱신: {datetime.now():%Y-%m-%d %H:%M:%S}\n상태: {status}\n내용: {detail}\n"
                "실행ID: -\n상세 로그: -\n", encoding="utf-8")
        except OSError as exc:
            self.log(f"[정산] 상태 기록 실패: {exc}")


if __name__ == "__main__":   # 단독 스모크(offscreen 가능) — 실제 output/정산/로그 를 읽어 1회 그린다
    import sys

    from PySide6 import QtWidgets
    app = QtWidgets.QApplication(sys.argv)
    info = read_settlement_status(app_output_dir() / "정산" / "로그")
    print("상태:", info["상태"] or "(없음)", "· 멈춤의심:", info["stale"], "· 마지막:", info["last_active"])
    print(_counts_text(info["today_counts"]))
