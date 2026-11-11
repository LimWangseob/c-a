"""계정 정지(승인 반려) 감지 → 관리대장 취소선 표기(가역) 오프라인 검증 — 실 로그인·네트워크 없음(소유자 2026-11-11).

덮는 범위: ①정지 판정(순수 judge_suspended·/unapproved·'승인 반려'·정상=False) ②is_suspended(가짜 page DOM)
③계정아이디 열·행 헬퍼 ④상태 파일 왕복 ⑤apply_strikes(되쓰기 전 백업 먼저·여러 행 취소선·applied 중복쓰기 방지
·정상화 원복으로 해제+제거·정상 계정 손 안 댐·dry-run 미기록·비번 열 없으면 skip).

    python tools/verify_account_suspend_offline.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics import account_suspend as susp  # noqa: E402
from coupang_analytics import browser  # noqa: E402
from coupang_analytics import input_list  # noqa: E402

HEADER = ["대표자명", "사업자명", "계정아이디", "비밀번호", "상품명"]
# 계정아이디 열 = index 2. hide4u 2줄(취소선 2행), normal1 1줄.
LEDGER = [
    HEADER,                                        # row 1
    ["김", "A사", "hide4u", "pwA", "상품1"],        # row 2
    ["", "", "hide4u", "pwA", "상품2"],             # row 3
    ["이", "B사", "normal1", "pwB", "상품1"],       # row 4
]


def ok(msg):
    print(f"  ✔ {msg}")


class FakePage:
    def __init__(self, unapproved=False, body=""):
        self._un, self._body = unapproved, body

    def query_selector(self, sel):
        return object() if (self._un and "unapproved" in sel) else None

    def inner_text(self, sel):
        return self._body


class _FakeSelf:
    def __init__(self, page):
        self.page = page


class FakeClient:
    def __init__(self):
        self.strikes = []     # (sheet, col0, rows, on)
        self.backups = []     # (source, new_title, 그 시점까지의 취소선 쓰기 수) — 백업이 먼저면 셋째=0

    def duplicate_sheet(self, source, new_title):
        self.backups.append((source, new_title, len(self.strikes)))
        return 999

    def set_strike(self, sheet, col0, rows, on):
        self.strikes.append((sheet, col0, tuple(rows), on))
        return len(rows)


def test_judge_suspended():
    assert browser.judge_suspended(True, "") is True
    assert browser.judge_suspended(False, "판매자 정보 입력하기 승인 반려") is True
    assert browser.judge_suspended(False, "정상 대시보드 주문 매출") is False
    assert browser.judge_suspended(False, "") is False
    ok("judge_suspended: /unapproved·'승인 반려'=정지 · 정상/빈화면=False")


def test_is_suspended_fakepage():
    assert browser.WingBrowser.is_suspended(_FakeSelf(FakePage(unapproved=True))) is True
    assert browser.WingBrowser.is_suspended(_FakeSelf(FakePage(body="승인 반려"))) is True
    assert browser.WingBrowser.is_suspended(_FakeSelf(FakePage(body="정상"))) is False
    ok("is_suspended: 가짜 page DOM(/unapproved 앵커·홈 문구)로 판정")


def test_id_column_rows():
    assert input_list.account_id_column(LEDGER) == 2
    rows = input_list.account_id_rows(LEDGER)
    assert rows == {"hide4u": [2, 3], "normal1": [4]}, rows
    assert input_list.account_id_column([["대표자명", "상품명"]]) is None
    ok("account_id_column=2 · account_id_rows: hide4u=[2,3]·normal1=[4]")


def test_state_file_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        susp.mark_suspended("hide4u", "A01781927", out_dir=d)
        assert susp.suspended_ids(d) == {"hide4u"}
        data = susp._load(d)["hide4u"]
        assert data["업체코드"] == "A01781927" and data["applied"] is False
        susp.clear_suspended("hide4u", out_dir=d)
        assert susp.suspended_ids(d) == set()
    ok("상태 파일 왕복: mark→suspended_ids·applied=False → clear→빔")


def test_apply_strikes_set_and_backup_first():
    with tempfile.TemporaryDirectory() as d:
        susp.mark_suspended("hide4u", "A01781927", out_dir=d)
        c = FakeClient()
        res = susp.apply_strikes(c, "셀독리스트", LEDGER, out_dir=d)
        # 백업이 모든 취소선 쓰기보다 먼저
        assert c.backups and c.backups[0][2] == 0, c.backups
        assert c.strikes == [("셀독리스트", 2, (2, 3), True)], c.strikes
        assert res["strike"] == {"hide4u": 2}
        # applied=True 기록 → 재호출 시 재쓰기 없음
        assert susp._load(d)["hide4u"]["applied"] is True
        c2 = FakeClient()
        susp.apply_strikes(c2, "셀독리스트", LEDGER, out_dir=d)
        assert c2.strikes == [] and c2.backups == []
    ok("apply_strikes: 백업 먼저 → 계정아이디 2행 취소선 ON · applied=True → 재호출 미쓰기")


def test_apply_strikes_unstrike_reverts():
    with tempfile.TemporaryDirectory() as d:
        susp.mark_suspended("hide4u", out_dir=d)
        susp.apply_strikes(FakeClient(), "셀독리스트", LEDGER, out_dir=d)   # 취소선 ON·applied
        c = FakeClient()
        res = susp.apply_strikes(c, "셀독리스트", LEDGER, out_dir=d, unstrike={"hide4u"})
        assert c.strikes == [("셀독리스트", 2, (2, 3), False)], c.strikes
        assert res["unstrike"] == {"hide4u": 2}
        assert susp.suspended_ids(d) == set()   # 정상화 → 상태 파일에서 제거
    ok("정상화 원복: unstrike → 취소선 OFF(2행) + 상태 파일 제거")


def test_dry_run_and_normal_untouched():
    with tempfile.TemporaryDirectory() as d:
        susp.mark_suspended("hide4u", out_dir=d)
        c = FakeClient()
        susp.apply_strikes(c, "셀독리스트", LEDGER, out_dir=d, dry_run=True)
        assert c.strikes == [] and c.backups == []
        assert susp._load(d)["hide4u"]["applied"] is False   # dry-run 은 applied 안 바꿈
        # normal1 은 상태 파일에 없으니 손대지 않음
        c2 = FakeClient()
        susp.apply_strikes(c2, "셀독리스트", LEDGER, out_dir=d)
        assert all("normal1" not in str(s) for s in c2.strikes)
    ok("dry-run 미기록(applied 불변) · 정상 계정(normal1) 손 안 댐")


def test_no_id_col_skips():
    with tempfile.TemporaryDirectory() as d:
        susp.mark_suspended("hide4u", out_dir=d)
        c = FakeClient()
        res = susp.apply_strikes(c, "셀독리스트", [["대표자명", "상품명"]], out_dir=d)
        assert res == {"skipped": "no_id_col"} and c.strikes == []
    ok("계정아이디 열 없으면 skip(되쓰기 없음)")


def main():
    print("계정 정지 감지 → 대장 취소선(가역) 오프라인 검증")
    test_judge_suspended()
    test_is_suspended_fakepage()
    test_id_column_rows()
    test_state_file_roundtrip()
    test_apply_strikes_set_and_backup_first()
    test_apply_strikes_unstrike_reverts()
    test_dry_run_and_normal_untouched()
    test_no_id_col_skips()
    print("✅ 계정 정지 검증 통과")


if __name__ == "__main__":
    main()
