"""노출·방문자 아침 보충 — 앱 연결 오프라인 검증(D-374 · 화면 없이 Qt offscreen 으로 실제 App 을 띄움 · 로그인·구글 호출 없음).

기대값(D-374 ②③): 앱 1분 타이머가 08:00 뒤 그날 한 번 부름 · 이 창의 다른 실행(①②③ 등)이 돌면 기다림(⏸ 줄 그날 한 번) ·
시작 직전 관리대장 다시 읽음(D-366) · 도는 동안 이 창 버튼 실행 막음 · 파이프라인 잠금 경로를 넘김 ·
무인 앱 = 이번 회차 ① 이 끝났고 그날 보충이 남았으면 ①②③ 뒤 종료하지 않고 기다렸다가 보충 뒤 종료 · ① 미완료·이미 함 = 바로 종료.
핵심 규칙(어제 칸 두 줄만·잠금·3번·하루 한 번)은 tools/verify_traffic_morning_offline.py.
실행: python tools/verify_ui_morning_offline.py
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

FAILS: list[str] = []
LOADS: list = []
CLOCK = None


def check(ok: bool, msg: str) -> None:
    print(f"  {'✔' if ok else '✘'} {msg}")
    if not ok:
        FAILS.append(msg)


def m7_app_tick():
    global LOADS, CLOCK
    print("[M7] 앱 1분 타이머 · 다른 실행 도는 중 = 기다림 · 무인 앱 = ①②③ 뒤 08:00 보충 끝낸 뒤 종료")
    import os
    from types import SimpleNamespace
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(ROOT / "ui"))
    from PySide6 import QtWidgets
    import app_qt
    tmp = Path(tempfile.mkdtemp(prefix="d374_ui_"))
    app_qt.app_output_dir = lambda: tmp
    app_qt.App._load_saved_secrets = lambda self: None
    app_qt.App._probe_gsheet_links = lambda self, *a, **k: None
    app_qt.App._merge_output_marketing = lambda self, il: None
    app_qt.power.keep_awake = lambda on: None
    il = SimpleNamespace(accounts=[SimpleNamespace(account_id="acc1", business_name="가게A", products=[])],
                         errors=[], struck=[])
    loads = LOADS = []
    app_qt.App._auto_load_input = lambda self: (loads.append(1), setattr(self, "input_list", il), True)[2]
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = app_qt.App(auto=True)
    w._contractor_timer.stop()
    quits, calls = [], []
    w._auto_quit = lambda: quits.append(1)
    w.run_bg = lambda task, *a, **k: task()

    class Clock(datetime):
        cur = datetime(2026, 11, 21, 3, 0)

        @classmethod
        def now(cls, tz=None):
            return cls.cur
    app_qt.datetime = CLOCK = Clock
    state = {"owed": True, "done": True, "due": False, "why": ""}
    TM_ = app_qt.traffic_morning
    TM_.owed_today = lambda now, out_dir="output": state["owed"]
    TM_.sales_done = lambda now, out_dir="output": state["done"]
    TM_.daily_due = lambda now, out_dir="output": state["due"]
    TM_.wait_reason = lambda now, out_dir="output": state["why"]
    TM_.missed_today = lambda now, out_dir="output": False   # 23:00 못 함 줄은 M9

    def fake_run(accounts, **k):
        calls.append((list(a.account_id for a in accounts), k["pipe_lock"], w._run_active))
        state["owed"] = False
        return {}
    TM_.run_daily = fake_run

    w._auto_done()
    check(not quits and w._morning_hold, "03:00 ①②③ 끝 · 보충 남음 = 종료 안 하고 기다림")
    w._stages_running = True
    state["due"] = True
    Clock.cur = datetime(2026, 11, 21, 8, 0, 30)
    w._morning_tick()
    w._morning_tick()
    check(not calls, "이 창에서 ①②③ 등 실행 도는 중 = 시작 안 함")
    w._stages_running = False
    w._morning_tick()
    check(len(calls) == 1 and calls[0][0] == ["acc1"] and calls[0][1].endswith("파이프라인.lock"),
          f"끝나면 시작 · 파이프라인 잠금 경로 넘김 {calls}")
    check(calls[0][2] is True and w._run_active is False, "도는 동안 이 창 버튼 실행 막음 · 끝나면 풂")
    check(loads[-1:] == [1] and len(loads) >= 2, "시작 직전 관리대장 다시 읽음(D-366)")
    w._morning_tick()
    check(quits == [1] and not w._morning_hold, "보충 끝 → 무인 앱 종료")

    quits.clear()
    w2 = app_qt.App(auto=True)
    w2._contractor_timer.stop()
    w2._auto_quit = lambda: quits.append(2)
    state.update(owed=True, done=False)
    w2._auto_done()
    check(quits == [2], "이번 회차 ① 완료 기록 없음(① 실패 등) = 기다리지 않고 종료")
    state.update(owed=False, done=True)
    quits.clear()
    w2._auto_done()
    check(quits == [2], "오늘 보충 이미 함·23:00 지남 = 바로 종료")
    log = w._log_path.read_text(encoding="utf-8")
    check(log.count("⏸ 이 창에서 다른 실행이 도는 중") == 1, "⏸ 줄 = 같은 이유 그날 한 번")



def m8_no_reread_while_locked():
    print("[M8] 다른 창·무인 실행이 파이프라인 잠금을 쥔 동안 = 관리대장 다시 읽지 않음 · ⏸ 하루 한 번 · 풀리면 시작")
    import app_qt
    from coupang_analytics.registry_lock import registry_lock
    TM_ = app_qt.traffic_morning
    w = app_qt.App(auto=False)
    w._contractor_timer.stop()
    w.run_bg = lambda task, *a, **k: task()
    loads0 = len(LOADS)
    TM_.daily_due = lambda now, out_dir="output": True
    TM_.wait_reason = lambda now, out_dir="output": ""
    TM_.missed_today = lambda now, out_dir="output": False
    runs = []
    TM_.run_daily = lambda accounts, **k: runs.append(1) or {}
    lock = w._pipe_lock_path()
    with registry_lock(lock, wait_sec=0):          # 무인 앱 ③ 이 잠금을 쥠(다른 핸들 = 다른 실행)
        for m in range(30):
            CLOCK.cur = datetime(2026, 11, 21, 9, m, 30)
            w._morning_tick()
    check(len(LOADS) == loads0 and not runs, f"잠금 동안 30분 = 관리대장 다시 읽기 {len(LOADS) - loads0}번 · run_daily {len(runs)}번")
    log = w._log_path.read_text(encoding="utf-8")
    check(log.count("⏸ 다른 창·무인 실행이 파이프라인을 쓰는 중") == 1, "⏸ 줄 = 그날 한 번")
    CLOCK.cur = datetime(2026, 11, 21, 11, 31)
    w._morning_tick()
    check(len(LOADS) == loads0 + 1 and runs == [1], "잠금 풀림 = 대장 1번 읽고 시작")


def m9_missed_line_before_quit():
    print("[M9] 무인 앱이 기다리다 23:00 을 넘김 = ❌ '아침 보충 못 함' 줄을 남긴 뒤 종료")
    import app_qt
    TM_ = app_qt.traffic_morning
    w = app_qt.App(auto=True)
    w._contractor_timer.stop()
    quits, order = [], []
    w._auto_quit = lambda: (order.append("종료"), quits.append(1))
    w._morning_hold = True
    TM_.owed_today = lambda now, out_dir="output": False
    TM_.daily_due = lambda now, out_dir="output": False
    TM_.missed_today = lambda now, out_dir="output": True
    seen = {}

    def give_up(accounts, **k):
        order.append("못 함")
        seen.update(k, n=len(accounts))
        k["log"]("  [노출·방문자 아침 보충] ❌ 노출·방문자 아침 보충 못 함 — 시험")
        return True
    TM_.give_up = give_up
    CLOCK.cur = datetime(2026, 11, 21, 23, 0, 30)
    w._morning_tick()
    check(order == ["못 함", "종료"], f"못 함 줄 → 종료 순서 {order}")
    check(seen.get("pipe_lock", "").endswith("파이프라인.lock") and seen.get("n") == 1 and seen.get("why"),
          f"사유·계정·잠금 경로 넘김 {seen}")



def main() -> int:
    m7_app_tick()
    m8_no_reread_while_locked()
    m9_missed_line_before_quit()
    print(f"\n결과: {'통과' if not FAILS else f'실패 {len(FAILS)}건'}")
    for f in FAILS:
        print("  ✘", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
