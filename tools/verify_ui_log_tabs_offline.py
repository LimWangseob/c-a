"""앱 진행 로그창 = 탭별 표시(T-19) 오프라인 검증 — 화면 없이(Qt offscreen) 실제 App 을 띄워 본다.

기대값 출처 = 소유자(2026-11-12): "탭을 바꾸면 그 탭의 로그만 보이게" + 같은 날 답
  ① 앱이 켜질 때 나오는 줄(어느 탭의 작업도 아닌 줄) = 모든 탭에 공통
  ② 로그창 '복사' = 지금 탭 줄만(전체 기록은 로그 파일에 그대로)
판정은 '그 탭을 열었을 때 화면 로그창에 보이는 글'로 한다(사람이 보는 결과 기준).

+ 정산 탭의 정산서 배치 상태(T-171 · 소유자 2026-11-24 "운용자가 알수 있는 방법이 있어야 함" · D-399 ④ 상태 카드):
  배치가 쓰는 `output/정산서/_현재상태.txt`(실제 쓰는 코드 `statement_batch.BatchLog.status`)의 상태·확인 필요 N건·건별 줄이 정산 탭에 보임 ·
  파일 없음 = '정산서 배치 기록 없음'(숨기지 않음) · 정산 받기 상태(`output/정산/로그`)와 서로 안 섞임.

    python tools/verify_ui_log_tabs_offline.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ui"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from PySide6 import QtWidgets  # noqa: E402

import app_qt  # noqa: E402
import settlement_status_panel_qt as SSP  # noqa: E402
import transfer_panel_qt  # noqa: E402
from coupang_analytics import statement_batch as SB  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="t19_log_")
app_qt.app_output_dir = lambda: Path(_TMP)          # 로그 파일 미러를 임시 폴더로(실제 output 에 안 씀)
SSP.app_output_dir = lambda: Path(_TMP)             # 정산·정산서 상태 파일도 임시 폴더에서 읽음
SB.STATUS, SB.LOGS = Path(_TMP) / "정산서" / "_현재상태.txt", Path(_TMP) / "정산서" / "로그"
app_qt.App._load_saved_secrets = lambda self: None  # 키·비번 저장소 안 읽음
app_qt.App._probe_gsheet_links = lambda self, *a, **k: None   # 구글시트 연결 확인(네트워크) 안 함
app_qt.App._auto_load_input = lambda self: self.log("시작줄-입력읽기")   # 시작 때 줄(어느 탭 작업도 아님)
app_qt.power.keep_awake = lambda on: None
QA = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def ok(msg):
    print(f"  ✔ {msg}")


def _pump(cond=lambda: True, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QA.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    QA.processEvents()
    return cond()


def _idx(w, name: str) -> int:
    names = [w.tabs.tabText(i) for i in range(w.tabs.count())]
    return names.index(name)


def _seen(w, i: int) -> str:
    """탭 i 를 열었을 때 화면 로그창에 보이는 글."""
    w.tabs.setCurrentIndex(i)
    _pump()
    return w.log_console.toPlainText()


def _app():
    w = app_qt.App(auto=False)
    w._log_activated = True
    return w


def s1_current_tab(w):
    kw, rank = _idx(w, "키워드 추천"), _idx(w, "순위 조회")
    w.tabs.setCurrentIndex(kw)
    w.log("S1-키워드줄")
    w.tabs.setCurrentIndex(rank)
    w.log("S1-순위줄")
    _pump()
    a, b = _seen(w, kw), _seen(w, rank)
    assert "S1-키워드줄" in a and "S1-순위줄" not in a, f"키워드 탭에 다른 탭 줄이 보임: {a!r}"
    assert "S1-순위줄" in b and "S1-키워드줄" not in b, f"순위 탭에 다른 탭 줄이 보임: {b!r}"
    ok("탭에서 남긴 줄 = 그 탭에만 보임(다른 탭엔 안 보임)")


def s2_bg_task_stays_on_start_tab(w):
    img, sales = _idx(w, "상세 이미지"), _idx(w, "판매 분석")
    w.tabs.setCurrentIndex(img)
    go, done = threading.Event(), []

    def task():
        go.wait(5)                                   # 시작 뒤 사람이 다른 탭으로 옮긴 다음에 줄을 남김
        w.log("S2-작업줄")
        t = threading.Thread(target=lambda: w.log("S2-하위스레드줄"))
        t.start()
        t.join()
        return 7

    def task_err():
        go.wait(5)
        raise ValueError("S2-오류")

    w.run_bg(task, on_done=lambda r: (w.log(f"S2-끝줄 {r}"), done.append(1)))
    w.run_bg(task_err, on_done=None)
    w.tabs.setCurrentIndex(sales)                    # 작업 도중 탭 이동
    go.set()
    assert _pump(lambda: done and w._bg_active == 0), "작업이 끝나지 않음"
    a, b = _seen(w, img), _seen(w, sales)
    for line in ("S2-작업줄", "S2-하위스레드줄", "S2-끝줄 7", "S2-오류"):
        assert line in a, f"시작한 탭(상세 이미지)에 '{line}' 없음: {a!r}"
        assert line not in b, f"옮겨 간 탭(판매 분석)에 '{line}' 이 보임: {b!r}"
    ok("버튼 작업의 줄(작업·하위 스레드·끝·오류) = 시작한 탭에만 — 도중에 탭을 옮겨도 섞이지 않음")


def s3_startup_lines_all_tabs(w):
    for i in range(w.tabs.count()):
        assert "시작줄-입력읽기" in _seen(w, i), f"시작 줄이 '{w.tabs.tabText(i)}' 탭에 없음"
    w.tabs.setCurrentIndex(_idx(w, "순위 조회"))
    w.log_all("시작줄-정리")                          # main() 의 시작 전 줄(남은 Chrome 정리 등)
    _pump()
    for i in range(w.tabs.count()):
        assert "시작줄-정리" in _seen(w, i), f"시작 줄(정리)이 '{w.tabs.tabText(i)}' 탭에 없음"
    ok(f"앱 시작 줄 = 모든 탭 {w.tabs.count()}개에 공통으로 보임")


def s4_auto_run_on_full_tab(w):
    full, st = _idx(w, "전체 실행"), _idx(w, "설정")
    w.tabs.setCurrentIndex(st)
    w.input_list = None
    quits = []
    w._auto_quit = lambda: quits.append(1)
    w.start_auto()
    _pump()
    assert quits, "입력 없음에서 무인 실행이 끝나지 않음"
    assert w.tabs.currentIndex() == full, f"무인 실행 화면이 '전체 실행' 탭이 아님: {w.tabs.tabText(w.tabs.currentIndex())}"
    a, b = _seen(w, full), _seen(w, st)
    assert "[무인 자동 실행] 시작" in a and "입력을 불러오지 못해" in a, f"전체 실행 탭에 무인 줄 없음: {a!r}"
    assert "[무인 자동 실행] 시작" not in b, f"설정 탭에 무인 줄이 보임: {b!r}"
    ok("무인 실행 = 화면을 '전체 실행' 탭으로 옮기고 그 탭에 줄을 남김")


def s5_transfer_poll_lines(w):
    tr, rank = _idx(w, "셀독전환 정산"), _idx(w, "순위 조회")
    w.tabs.setCurrentIndex(rank)                     # 사람은 다른 탭을 보는 중
    orig = transfer_panel_qt._tail
    transfer_panel_qt._tail = lambda folder, pattern, since, cur: (cur, ["S5-진행줄"])
    w._tr_refresh = lambda: None
    w._ts_refresh = lambda: None
    w._tr_proc = w._ts_proc = None
    try:
        w._tr_poll()
        w._ts_poll()
    finally:
        transfer_panel_qt._tail = orig
    _pump()
    a, b = _seen(w, tr), _seen(w, rank)
    for line in ("[셀독전환] S5-진행줄", "[셀독전환 정산] S5-진행줄", "로그인 확인 끝", "정산 자료 받기 끝"):
        assert line in a, f"셀독전환 탭에 '{line}' 없음: {a!r}"
        assert line not in b, f"보던 탭(순위 조회)에 '{line}' 이 보임"
    ok("셀독전환 진행 줄(5초마다 읽음) = 다른 탭을 보는 중에도 셀독전환 탭에만")


def s6_copy_clear_current_tab(w):
    kw, rank = _idx(w, "키워드 추천"), _idx(w, "순위 조회")
    w.tabs.setCurrentIndex(kw)
    _pump()
    w.copy_log()
    clip = QA.clipboard().text()
    assert "S1-키워드줄" in clip, f"복사에 지금 탭 줄이 없음: {clip!r}"
    assert "S1-순위줄" not in clip and "S2-작업줄" not in clip, f"복사에 다른 탭 줄이 들어감: {clip!r}"
    w.tabs.setCurrentIndex(kw)
    _pump()
    w._clear_log()
    assert "S1-키워드줄" not in _seen(w, kw), "지우기 뒤에도 지금 탭 줄이 남음"
    assert "S1-순위줄" in _seen(w, rank), "지우기가 다른 탭 줄까지 지움"
    ok("복사·지우기 = 지금 탭 줄만(다른 탭 줄은 그대로)")


def s7_file_mirror_all(w):
    text = w._log_path.read_text(encoding="utf-8")
    for line in ("시작줄-입력읽기", "S1-키워드줄", "S1-순위줄", "S2-작업줄", "S2-하위스레드줄", "S5-진행줄",
                 "[무인 자동 실행] 시작"):
        assert line in text, f"로그 파일에 '{line}' 없음"
    ok("로그 파일 = 모든 탭 줄이 한 파일에 그대로(지우기와 무관)")


def s8_close_mid_run_records(w):
    """앱 창을 닫으면 어느 단계에서 사람이 닫았는지 + [실행 결과 종합] '사람 중지 --> 중단'(T-47 · output (37) 11-13·14
    로그가 순위 한 줄 중간에서 그냥 끝남 · D-173). 실행이 없을 때도 닫힘 한 줄 · 무인이 스스로 끝낼 땐 '사람이' 안 씀."""
    from coupang_analytics import run_result as RR
    w._semi_stop = threading.Event()
    rs = RR.RunSummary(w.log, ["가-1"], should_stop=w._semi_stop.is_set, rank={})
    rs.__enter__()
    rs.enter(RR.SALES)
    rs.enter(RR.RANKS)
    start = len(w._log_path.read_text(encoding="utf-8"))
    w.close()
    _pump()
    text = w._log_path.read_text(encoding="utf-8")[start:]
    assert "[앱 종료] 사람이 앱 창을 닫음 — ③ 순위 도중" in text, text[-800:]
    assert "판정: 사람 중지 --> 중단" in text and "③ 순위: 사람이 창을 닫아 멈춤" in text, text[-800:]
    assert "③ 순위 결과 없음" not in text, "닫혀서 멈춘 ③ 을 '결과 없음' 오류로 세지 않음"
    assert w._semi_stop.is_set(), "닫을 때 ③ 중지 신호"
    rs.__exit__(None, None, None)            # 작업 스레드가 뒤늦게 끝나도 종합 두 번 안 찍음
    _pump()
    text = w._log_path.read_text(encoding="utf-8")[start:]
    assert text.count(RR.TITLE) == 1, text.count(RR.TITLE)
    assert not RR.ACTIVE, "끝난 실행은 목록에서 빠짐"
    start = len(text) + start
    w.show(); w.close(); _pump()
    text = w._log_path.read_text(encoding="utf-8")[start:]
    assert "[앱 종료] 사람이 앱 창을 닫음 — 도는 실행 없음" in text and RR.TITLE not in text, text
    w.show(); w._quitting = True; w.close(); _pump()
    assert "사람이" not in w._log_path.read_text(encoding="utf-8")[start + len(text):], "무인이 스스로 끝냄 = 사람 닫음 아님"
    ok("창 닫기 = 닫은 단계 + 종합 '사람 중지 --> 중단'(한 번만) · 실행 없을 때 한 줄 · 무인 스스로 끝남은 안 씀")


def _settle_screen(w) -> str:
    """정산 탭을 열었을 때 '정산서 배치' 칸에 실제로 보이는 글(안 숨겨진 것만)."""
    w.tabs.setCurrentIndex(_idx(w, "정산"))
    w._refresh_settlement_status()                    # 5초 타이머가 부르는 것과 같은 함수
    _pump()
    box = w.statement_box
    assert not box.isHidden(), "정산서 배치 칸이 숨겨짐"
    return chr(10).join(x.text() for x in box.findChildren(QtWidgets.QLabel) if not x.isHidden() and x.text())


def s9_statement_batch_status(w):
    seen = _settle_screen(w)
    assert "정산서 배치 기록 없음" in seen, seen                                       # 파일 없음 = 그렇게 보임(숨기지 않음)
    blog = SB.BatchLog("261125_101112", echo=lambda m: None)
    blog.status(SB.ST_RUN, "회차 2026-11-25 정산서 만드는 중")
    seen = _settle_screen(w)
    assert "● 정산서 만드는 중" in seen and "회차 2026-11-25" in seen and "기록 없음" not in seen, seen
    lines = tuple(f"확인 필요: 위탁정산서 · acc{i} · 사유{i}" for i in range(5)) + ("확인 필요: … 외 12건(보고 파일)",)
    blog.status(SB.ST_CHECK, "회차 2026-11-25 · 일부 실패 --> 확인 필요 · 확인 필요 17건 · 보고 배치보고_261125_101112.md", extra=lines)
    seen = _settle_screen(w)
    for want in ("정산서 만듦 — 건너뛴 계정 확인 필요", "확인 필요 17건", "배치보고_261125_101112.md", *(x.partition(": ")[2] for x in lines),
                 "마지막 갱신", "배치_261125_101112.log"):
        assert want in seen, (want, seen)
    blog.status(SB.ST_DONE, "회차 2026-11-25 · 정상 완료 · 확인 필요 0건 · 보고 배치보고_261125_101112.md")
    seen = _settle_screen(w)
    assert "● 정산서 모두 만듦" in seen and "확인 필요 0건" in seen and "acc1" not in seen, seen      # 앞 배치 건별 줄 안 남음
    blog.status(SB.ST_STOP, "정산 받기 '완료' 기록 없음(24:00 까지 못 끝난 날 = 안 돎)")
    seen = _settle_screen(w)
    assert "● 정산서 중단" in seen and "24:00 까지 못 끝난 날" in seen, seen
    log = Path(_TMP) / "정산" / "로그"                                                # 정산 받기 상태와 서로 안 섞임
    log.mkdir(parents=True, exist_ok=True)
    (log / "_현재상태.txt").write_text(chr(10).join(["정산 자동 다운로드 — 현재 상태", "갱신: 2026-11-25 10:00:00", "상태: 완료", "내용: 받기끝줄", ""]),
                                   encoding="utf-8")
    seen = _settle_screen(w)
    assert "● 모두 받음" in w.settle_badge.text() and w.settle_detail_lbl.text() == "받기끝줄", w.settle_badge.text()
    assert "정산서 중단" in seen and "받기끝줄" not in seen, seen
    SB.STATUS.write_text("깨진 파일", encoding="utf-8")                              # 꼴이 다름 = 못 읽었다고 보임
    seen = _settle_screen(w)
    assert "정산서 배치 상태 파일을 읽을 수 없음" in seen and "기록 없음" not in seen, seen
    SB.STATUS.write_bytes(bytes([0xFF, 0xFE, 0xFF]))
    assert "읽을 수 없음" in _settle_screen(w)
    SB.STATUS.unlink()
    assert "정산서 배치 기록 없음" in _settle_screen(w)
    ok("정산 탭 = 정산서 배치 상태(배지 4종·확인 필요 N건·건별 줄·보고 파일·갱신) · 기록 없음·깨진 파일도 글로 보임 · 정산 받기 상태와 안 섞임")


def main():
    w = _app()
    s1_current_tab(w)
    s2_bg_task_stays_on_start_tab(w)
    s3_startup_lines_all_tabs(w)
    s4_auto_run_on_full_tab(w)
    s5_transfer_poll_lines(w)
    s6_copy_clear_current_tab(w)
    s7_file_mirror_all(w)
    s9_statement_batch_status(w)
    s8_close_mid_run_records(w)
    print("앱 진행 로그창 탭별 표시(T-19)·정산 탭 정산서 배치 상태(T-171) 오프라인 검증 통과")


if __name__ == "__main__":
    main()
