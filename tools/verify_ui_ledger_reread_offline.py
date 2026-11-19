"""켜 둔 앱의 관리대장 다시 읽기(D-366 ①) 오프라인 검증 — 화면 없이(Qt offscreen) 실제 App 을 띄워 본다.

기대값 출처 = 소유자(2026-11-19): "관리대장 변경분이 정확히 반영되어야 함" → D-366 ① 적용 원문
  ① 켜 둔 앱의 모든 버튼 실행 = 시작 전 확인(`_require_run_inputs`)에서 `_auto_load_input`(앱 시작 때 읽는 함수) 다시 부름
     · 확인 팝업 전(팝업의 '대상 상품 N개' = 새 대장) · 못 읽으면 실행 안 함(지난 대장·PC 엑셀로 대신 안 돌림 D-134)
  ② 06:00 계약자 현황 = 만들기 직전 같은 함수로 다시 읽음 · 못 읽으면 그날 한 번 알림 + 10분 뒤 다시(1분마다 구글 호출 안 함)
  ③ 한 실행은 시작 때 읽은 대장으로 끝까지(도중 변경 = 다음 실행)
구글 호출 없음 — 대장 읽기(`_auto_load_input`)는 페이크로 바꿔 '몇 번 불렸나·무엇을 넣었나'만 본다.

    python tools/verify_ui_ledger_reread_offline.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

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

_TMP = tempfile.mkdtemp(prefix="d366_reread_")
app_qt.app_output_dir = lambda: Path(_TMP)          # 로그 파일 미러를 임시 폴더로
app_qt.App._load_saved_secrets = lambda self: None  # 키·비번 저장소 안 읽음
app_qt.App._probe_gsheet_links = lambda self, *a, **k: None
app_qt.App._merge_output_marketing = lambda self, il: None   # 결과 구글시트 마케팅 읽기(네트워크) 안 함
app_qt.power.keep_awake = lambda on: None
QA = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def ok(msg):
    print(f"  ✔ {msg}")


def _il(tag: str, n: int):
    """관리대장 InputList 대역 — 계정 1개·상품 n개(상품 이름에 몇 번째 대장인지 표시)."""
    prods = [SimpleNamespace(name=f"{tag}-상품{i}") for i in range(n)]
    return SimpleNamespace(accounts=[SimpleNamespace(account_id="acc1", business_name="사업자", products=prods)],
                           errors=[], struck=[])


class Ledger:
    """구글 관리대장 대역 — 읽을 때마다 지금 대장(sheet)을 앱에 넣음 · fail=True 면 못 읽음(앱 함수처럼 False)."""

    def __init__(self):
        self.sheet, self.fail, self.calls = _il("시작", 3), False, 0

    def load(self, app):
        self.calls += 1
        if self.fail:
            app.log("[입력] ❌ 구글 관리대장을 읽지 못해 실행을 중단합니다(페이크)")
            return False
        app._set_input_list(self.sheet, "[구글시트] 페이크 대장")
        return True


LEDGER = Ledger()
app_qt.App._auto_load_input = lambda self: LEDGER.load(self)


class Clock(datetime):
    cur = datetime(2026, 11, 19, 6, 5)

    @classmethod
    def now(cls, tz=None):
        return cls.cur


class Boxes:
    """확인·경고 팝업 대역 — 무엇을 물었는지 기록 · 확인 팝업은 '아니오'(실제 실행은 안 함)."""

    def __init__(self):
        self.questions, self.warnings = [], []

    def question(self, _parent, title, text, *a, **k):
        self.questions.append(text)
        return QtWidgets.QMessageBox.No

    def warning(self, _parent, title, text, *a, **k):
        self.warnings.append(text)


def _app():
    w = app_qt.App(auto=False)
    w._contractor_timer.stop()            # 시험은 tick 을 직접 부른다(타이머가 끼어들지 않게)
    w.naver_creds, w.ai_key = object(), "sk-test"
    return w


def _patch_boxes():
    b = Boxes()
    QtWidgets.QMessageBox.question = b.question
    QtWidgets.QMessageBox.warning = b.warning
    return b


def s1_button_run_rereads_before_confirm(w):
    app_qt.master_exists = lambda: True               # 결과 파일 있음(복원·첫 실행 경로 안 탐)
    app_qt.resumable_progress = lambda: None
    app_qt.restore_master_from_gsheet = lambda *a, **k: (_ for _ in ()).throw(AssertionError("복원 호출됨"))
    LEDGER.sheet, LEDGER.fail = _il("새대장", 5), False   # 앱 켠 뒤 대장이 바뀜(상품 3 → 5)
    before, boxes = LEDGER.calls, _patch_boxes()
    for keywords_off in (True, False):                # 판매 수집 · 전체 실행(날짜 지정도 같은 버튼 흐름)
        w.do_run_full(keywords_off=keywords_off)
    assert LEDGER.calls == before + 2, f"버튼 실행마다 대장을 다시 읽어야 함: {LEDGER.calls - before}번"
    assert len(boxes.questions) == 2 and all("상품 5개" in q for q in boxes.questions), \
        f"확인 팝업 '대상 상품' = 새 대장 기준이어야 함: {boxes.questions!r}"
    assert w.input_list is LEDGER.sheet, "실행에 넘길 입력 = 새 대장"
    ok("버튼 실행(판매 수집·전체 실행) = 실행마다 대장 다시 읽음 · 확인 팝업 '상품 5개' = 새 대장")


def s2_button_run_read_fail_stops(w):
    old = w.input_list
    LEDGER.fail = True
    before, boxes = LEDGER.calls, _patch_boxes()
    ran = []
    w.run_bg = lambda *a, **k: ran.append(1)
    try:
        w.do_run_full(keywords_off=True)
    finally:
        del w.run_bg
    assert LEDGER.calls == before + 1, "못 읽은 경우도 실행 전에 읽기를 시도해야 함"
    assert not boxes.questions and not ran, "못 읽으면 확인 팝업·실행 없음(지난 대장으로 대신 안 돌림 · D-134)"
    assert boxes.warnings and "관리대장" in boxes.warnings[0], f"못 읽음 경고 없음: {boxes.warnings!r}"
    assert w.input_list is old
    LEDGER.fail = False
    ok("버튼 실행 때 대장을 못 읽으면 = 경고만 · 확인 팝업·실행 없음(지난 대장으로 대신 안 돌림)")


def _contractor_env(w):
    built = []
    app_qt.contractor_stage.daily_due = lambda now, out_dir="output": not built
    app_qt.contractor_stage.wait_reason = lambda now, out_dir="output": ""
    app_qt.contractor_stage.run_daily = lambda il, **k: built.append(il)
    w.run_bg = lambda task, *a, **k: task()          # 뒤 작업을 그 자리에서(시험용)
    app_qt.datetime = Clock
    return built


def _log_text(w) -> str:
    return w._log_path.read_text(encoding="utf-8")


def s3_contractor_rereads_and_retries(w):
    built = _contractor_env(w)
    Clock.cur = datetime(2026, 11, 19, 6, 0, 30)
    LEDGER.fail, before, log0 = True, LEDGER.calls, len(_log_text(w))
    w._contractor_tick()
    assert LEDGER.calls == before + 1 and not built, "06:00 = 만들기 직전 대장 다시 읽기 · 못 읽으면 안 만듦"
    for m in (1, 5, 9):                               # 1분마다 tick — 10분 전엔 구글 호출 없음
        Clock.cur = datetime(2026, 11, 19, 6, 0, 30) + timedelta(minutes=m)
        w._contractor_tick()
    assert LEDGER.calls == before + 1, f"못 읽은 뒤 10분 안엔 다시 안 읽음(1분마다 구글 호출 금지): {LEDGER.calls - before}번"
    Clock.cur = datetime(2026, 11, 19, 6, 10, 30)
    w._contractor_tick()
    assert LEDGER.calls == before + 2 and not built, "10분 뒤 다시 읽기"
    warns = _log_text(w)[log0:].count("[계약자별 현황] ⚠")
    assert warns == 1, f"못 읽음 알림 = 그날 한 번만: {warns}번"
    LEDGER.sheet, LEDGER.fail = _il("06시대장", 4), False
    Clock.cur = datetime(2026, 11, 19, 6, 20, 30)
    w._contractor_tick()
    assert LEDGER.calls == before + 3 and built == [LEDGER.sheet], "읽히면 새 대장으로 만듦"
    ok("06:00 계약자 현황 = 만들기 직전 대장 다시 읽음 · 못 읽으면 알림 1번 + 10분 뒤 다시 · 읽히면 새 대장으로")


def s4_contractor_fresh_each_day(w):
    built = _contractor_env(w)
    LEDGER.sheet, before = _il("다음날대장", 6), LEDGER.calls
    Clock.cur = datetime(2026, 11, 20, 6, 0, 10)
    w._contractor_tick()
    assert LEDGER.calls == before + 1 and built == [LEDGER.sheet], "다음 날도 만들기 직전 다시 읽음"
    ok("다음 날 06:00 도 만들기 직전 다시 읽음(켜 둔 동안 바뀐 대장 반영)")


def s5_no_reread_during_run(w):
    """③ 실행 도중(①~③ 도는 중) 06:00 이 와도 대장을 다시 읽지 않음 — 비밀번호 후보·입력이 실행 중에 바뀌지 않게."""
    built = _contractor_env(w)
    run_il = w.input_list
    seen = {}
    app_qt.backup_sources = lambda **k: None
    app_qt.App._registry_presync = lambda self, il, gs_in: (il, "")
    app_qt.NaverAdApi = lambda creds: None

    def fake_run_stages(il, plan, **k):
        seen["calls"] = LEDGER.calls
        LEDGER.sheet = _il("도중변경", 9)              # 실행 도중 사람이 대장을 고침
        Clock.cur = datetime(2026, 11, 21, 6, 0, 10)
        w._contractor_tick()                         # 실행 도중 06:00
        seen["after"] = LEDGER.calls
        return None
    app_qt.run_stages = fake_run_stages
    w._stages_task(run_il, app_qt.StagePlan(), object(), "sk", "", "")
    assert seen["after"] == seen["calls"], "실행 도중엔 대장을 다시 읽지 않음(시작 때 읽은 대장으로 끝까지)"
    assert built == [run_il], "실행 도중 06:00 계약자 현황 = 실행 시작 때 읽은 대장으로"
    assert w.input_list is run_il
    ok("실행 도중 06:00 = 다시 읽지 않음 · 실행 시작 때 읽은 대장으로 만듦")


def main():
    w = _app()
    assert LEDGER.calls == 1, "앱 시작 때 한 번 읽음"
    s1_button_run_rereads_before_confirm(w)
    s2_button_run_read_fail_stops(w)
    s3_contractor_rereads_and_retries(w)
    s4_contractor_fresh_each_day(w)
    s5_no_reread_during_run(w)
    print("켜 둔 앱 관리대장 다시 읽기(D-366 ①) 오프라인 검증 통과")


if __name__ == "__main__":
    main()
