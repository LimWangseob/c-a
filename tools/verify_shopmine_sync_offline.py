"""샵마인 비번 ↔ 관리대장 동기화 오프라인 검증 — 실 서버·실 자격 없이 결정적(D-195).

덮는 범위: ①DPAPI 왕복(store_login/load_login·평문 비노출) ②응답 필드 탐색(인증키·레코드 리스트·필드명·비번 추출)
③관리대장 비번 열 탐지·열 문자 ④대조 분류(같음/다름/샵마인에만/대장에만/빈 비번) ⑤갱신 계획(빈 값 제외·여러 줄 통일)
⑥되쓰기(구글시트 셀·credstore 갱신·값2 비움) ⑦end-to-end(리포트에 비번 값 없음·요약 숫자). 비번 평문은 어디에도 안 남는다.
T-160 안전장치: 자격 없음 하루 1번 로그 · 샵마인 값 = 24시간 안 쿠팡 거부값이면 대장 안 덮음 · 리포트 '샵마인=대장' 값1/값2 ·
되쓴 뒤 비밀번호 후보 다시 반영(on_applied) · 앱 훅 연결.
D-389(소유자 2026-11-23 '내가 별도 작업 없이 진행되도록 수정해줘'): 설정 탭 입력 = make_login(CLI 와 같은 함수·D-196 기본값) ·
discover 자동(필드 대소문자·0건·없음) · 샵마인 로그인 거부 = 표시 후 매일 재시도 안 함 · 첫날 = 대조 리포트만 · 다음 날 자동 반영 ·
⑤ 대장 값 = 지난 로그인 성공값이고 샵마인 값은 아니면 대장 안 덮음 · 설정 탭 화면(비번 칸 가림·값 미노출).

    python tools/verify_shopmine_sync_offline.py
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics import login_today as LT  # noqa: E402
from coupang_analytics import settlement_accounts as SA  # noqa: E402
from coupang_analytics import shopmine_sync as sm  # noqa: E402
from coupang_analytics.credstore import CredStore  # noqa: E402

# 결과·리포트·디스크 어디에도 나오면 안 되는 비번 값들
SECRET = "S3cret!login"
SM_VALUES = ["newA", "newD", "oldA", "oldB", "cpw", "d1", "d2", "fpw"]

HEADER = ["대표자명", "사업자명", "계정아이디", "비밀번호", "상품명"]
# 비번 열 = index 3 → "D". shopA 2줄 같은값 · shopD 2줄 다른값(통일 대상) · shopF 는 샵마인에 없음.
LEDGER_ROWS = [
    HEADER,                                        # row 1
    ["김", "A사", "shopA", "oldA", "상품1"],        # row 2
    ["", "", "shopA", "oldA", "상품2"],             # row 3
    ["이", "B사", "shopB", "oldB", "상품1"],        # row 4
    ["박", "C사", "shopC", "cpw", "상품1"],         # row 5
    ["최", "D사", "shopD", "d1", "상품1"],          # row 6
    ["", "", "shopD", "d2", "상품2"],               # row 7
    ["정", "F사", "shopF", "fpw", "상품1"],         # row 8
]
SHOPMINE = {
    "shopA": "newA",   # 다름 → 갱신(행 2,3)
    "shopB": "",       # 샵마인 비번 없음 → 건너뜀
    "shopC": "cpw",    # 같음
    "shopD": "newD",   # 다름(d1·d2 둘 다와) → 갱신·통일(행 6,7)
    "shopE": "eee",    # 샵마인에만 → 리포트만
}


def ok(msg):
    print(f"  ✔ {msg}")


class FakeClient:
    def __init__(self):
        self.writes = []
        self.backups = []                       # (source, new_title, 그 시점까지의 쓰기 수)

    def duplicate_sheet(self, source_title, new_title):
        self.backups.append((source_title, new_title, len(self.writes)))   # 쓰기 전이면 셋째=0
        return 999

    def write_values(self, sheet, rows, start, raw=False):
        self.writes.append((sheet, start, rows[0][0], raw))


def test_dpapi_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        store = CredStore(Path(d) / "creds.json")
        creds = {"CompanyId": "co1", "UserId": "", "UserPassword": SECRET,
                 "OsVersion": "Windows", "ShopmineVersion": "", "IdKey": "MarketId", "PwKey": "MarketPassword"}
        sm.store_login(creds, store)
        assert sm.load_login(store) == creds, "DPAPI 왕복 불일치"
        disk = (Path(d) / "creds.json").read_text(encoding="utf-8")
        assert SECRET not in disk, "creds.json 에 평문 비번이 남음(DPAPI 암호화 실패)"
        assert sm.load_login(CredStore(Path(d) / "empty.json")) is None, "미설정이면 None"
    ok("DPAPI 왕복 — 저장/복원 일치 · 디스크 평문 없음 · 미설정 None")


def test_field_discovery():
    assert sm.find_value_by_keyname({"x": {"AuthenticationKey": "K"}}, sm.AUTHKEY_NAMES) == "K"
    assert sm.find_value_by_keyname({"authKey": "K2"}, sm.AUTHKEY_NAMES) == "K2"
    assert sm.find_value_by_keyname({"nope": 1}, sm.AUTHKEY_NAMES) is None
    assert sm.first_record_list([{"MarketId": "a"}]) == [{"MarketId": "a"}]
    assert sm.first_record_list({"data": [{"MarketId": "a"}]}) == [{"MarketId": "a"}]
    assert sm.first_record_list({"n": 1}) == []
    assert sm.masked_keys([{"b": 1, "a": 2}]) == ["a", "b"]
    recs = [{"MarketId": "shopA", "MarketPassword": "p1"}, {"MarketId": " ", "MarketPassword": "x"}]
    assert sm.extract_passwords(recs, "MarketId", "MarketPassword") == {"shopA": "p1"}, "빈 계정ID 제외"
    ok("필드 탐색 — 인증키 중첩/별칭 · 레코드 리스트 · 필드명 · 비번 추출(빈 ID 제외)")


def test_col_letter():
    assert sm._col_letter(0) == "A"
    assert sm._col_letter(3) == "D"
    assert sm._col_letter(26) == "AA"
    assert sm._col_letter(27) == "AB"
    ok("열 인덱스 → A1 문자")


def test_ledger_map():
    cands, pw_col = sm.ledger_password_map(LEDGER_ROWS)
    assert pw_col == "D", f"비번 열 문자 D 기대, 받음 {pw_col}"
    assert sorted(cands) == ["shopA", "shopB", "shopC", "shopD", "shopF"]
    assert {c.password for c in cands["shopA"]} == {"oldA"}
    assert sorted(r for c in cands["shopA"] for r in c.rows) == [2, 3], "shopA = 행 2,3"
    assert len(cands["shopD"]) == 2, "shopD 는 값 2개(d1·d2)"
    assert sm.ledger_password_map([["대표자명", "상품명"]])[1] is None, "비번 열 없으면 None"
    ok("관리대장 비번 열·후보·행 번호")


def test_classify():
    cands, _ = sm.ledger_password_map(LEDGER_ROWS)
    st = dict(sm.classify(SHOPMINE, cands))
    assert st["shopA"] == sm.ST_DIFF
    assert st["shopB"] == sm.ST_SM_EMPTY
    assert st["shopC"] == sm.ST_MATCH
    assert st["shopD"] == sm.ST_DIFF
    assert st["shopE"] == sm.ST_SM_ONLY
    assert st["shopF"] == sm.ST_LED_ONLY
    ok("대조 분류 — 같음/다름/샵마인에만/대장에만/빈 비번")


def test_updates_plan():
    cands, _ = sm.ledger_password_map(LEDGER_ROWS)
    plan = dict((aid, (pw, rows)) for aid, pw, rows in sm.updates_to_apply(SHOPMINE, cands))
    assert set(plan) == {"shopA", "shopD"}, "빈 값·같음·대장없음은 갱신 안 함"
    assert plan["shopA"] == ("newA", [2, 3])
    assert plan["shopD"] == ("newD", [6, 7]), "여러 줄 다른 값도 샵마인 현재값으로 통일"
    ok("갱신 계획 — 빈 값/같음/샵마인전용 제외 · 여러 줄 통일")


def test_unify_all_rows_when_partial_match():
    # (DW)커머스처럼 한 계정이 여러 줄: 일부 줄만 샵마인 현재값, 나머지는 옛값 → '다름'으로 보고 모든 줄 통일(모두 변경)
    rows = [
        ["대표자명", "사업자명", "계정아이디", "비밀번호", "상품명"],
        ["", "DW", "dw1849", "cur!", "상품1"],      # row2 이미 현재값
        ["", "DW", "dw1849", "old!", "상품2"],      # row3 옛값
        ["", "DW", "dw1849", "old!", "상품3"],      # row4 옛값
        ["", "온", "same1", "ok!", "상품1"],        # row5·6 모든 줄 현재값 → 같음(안 바꿈)
        ["", "온", "same1", "ok!", "상품2"],
    ]
    cands, pw_col = sm.ledger_password_map(rows)
    shopmine = {"dw1849": "cur!", "same1": "ok!"}
    st = dict(sm.classify(shopmine, cands))
    assert st["dw1849"] == sm.ST_DIFF, "한 줄만 맞고 나머지 다르면 '다름'(통일 필요)"
    assert st["same1"] == sm.ST_MATCH, "모든 줄이 현재값이면 '같음'(안 바꿈)"
    plan = dict((aid, (pw, r)) for aid, pw, r in sm.updates_to_apply(shopmine, cands))
    assert set(plan) == {"dw1849"}, "모든 줄이 현재값인 계정은 갱신 안 함"
    assert plan["dw1849"] == ("cur!", [2, 3, 4]), "여러 줄 전부(이미 맞은 줄 포함) 현재값으로 통일"
    ok("여러 줄 통일 — 일부만 맞아도 모든 줄 현재값으로('모두 변경') · 전부 맞으면 안 바꿈")


def test_apply_updates():
    store = CredStore(Path(tempfile.mkdtemp()) / "creds.json")
    store.set_password(SA.alt_key("shopD"), "d2")        # 값2(D-190) 존재 → 통일 후 비워져야
    cands, pw_col = sm.ledger_password_map(LEDGER_ROWS)
    plan = sm.updates_to_apply(SHOPMINE, cands)
    cl = FakeClient()
    n = sm.apply_updates(cl, "Sheet1", pw_col, plan, store, lambda m: None)
    assert n == 4, f"쓴 셀 4개 기대, 받음 {n}"
    cells = {(c[1], c[2], c[3]) for c in cl.writes}
    assert ("D2", "newA", True) in cells and ("D3", "newA", True) in cells
    assert ("D6", "newD", True) in cells and ("D7", "newD", True) in cells
    assert all(c[3] is True for c in cl.writes), "비번은 RAW 로 써야 함('0012'·'=' 해석 방지)"
    assert store.get_password("shopA") == "newA" and store.get_password("shopD") == "newD", "credstore 갱신"
    assert store.get_password(SA.alt_key("shopD")) == "", "값2 비움(한 값 통일)"
    ok("되쓰기 — 구글시트 셀(RAW)·credstore 갱신·값2 비움")


def test_run_daily_sync_end_to_end():
    with tempfile.TemporaryDirectory() as d:
        store = CredStore(Path(d) / "creds.json")
        cl = FakeClient()
        out = sm.run_daily_sync(
            "URL", "Sheet1", LEDGER_ROWS, store=store, client=cl,
            fetch=lambda s, log: dict(SHOPMINE), log=lambda m: None,
            now=datetime(2026, 11, 10, 18, 0, 0), out_dir=str(Path(d) / "rep"))
        assert out == {"accounts": 6, "updated": 2, "cells": 4, "report": out["report"]}, out
        assert len(cl.writes) == 4
        assert len(cl.backups) == 1, "변경 전 관리대장 백업(탭 복제) 1회"
        src, name, writes_at_backup = cl.backups[0]
        assert src == "Sheet1" and name.startswith("백업_비번동기화_"), cl.backups
        assert writes_at_backup == 0, "백업은 어떤 되쓰기보다 먼저여야 함(복구 안전)"
        report = Path(out["report"])
        assert report.exists()
        text = report.read_text(encoding="utf-8-sig")
        for v in SM_VALUES:
            assert v not in text, f"리포트에 비번 값 '{v}' 가 노출됨"
        assert "shopA" in text and sm.ST_DIFF in text and sm.ST_SM_ONLY in text
    ok("end-to-end — 요약 숫자 · 갱신 4셀 · 리포트에 비번 값 0 · 상태 기록")


def test_login_rejected_message():
    # 서버가 응답은 주되 로그인 거부(IsSuccess=False·AuthenticationKey 빈 값) → 필드 문제 아닌 '거부'로 또렷이 알림
    real = sm.post_failover
    try:
        sm.post_failover = lambda path, body, log=None: (
            "srv", {"AuthenticationKey": "", "AuthorizationCode": "", "IsSuccess": False})
        try:
            sm.do_login({"CompanyId": "c", "UserId": "c", "UserPassword": "x"}, lambda m: None)
            assert False, "거부 시 ShopmineError 를 올려야 함"
        except sm.ShopmineError as exc:
            assert "거부" in str(exc) and "UserId" in str(exc), str(exc)
        # 성공(IsSuccess=True·인증키 있음) → 인증키 반환
        sm.post_failover = lambda path, body, log=None: (
            "srv", {"AuthenticationKey": "KEY123", "IsSuccess": True})
        srv, key, _ = sm.do_login({"CompanyId": "c"}, lambda m: None)
        assert key == "KEY123"
    finally:
        sm.post_failover = real
    ok("로그인 거부(IsSuccess=False) → 또렷한 안내 · 성공 → 인증키 반환")


def test_login_strips_fields():
    # 샵마인 앱이 입력칸을 .Trim() 하므로(REA IL 확정) 보내는 본문도 공백을 떼야 동일(평문 그대로·해시 없음)
    sent = {}
    real = sm.post_failover
    try:
        sm.post_failover = lambda path, body, log=None: (sent.update(body), ("srv", {"AuthenticationKey": "K", "IsSuccess": True}))[1]
        sm.do_login({"CompanyId": " co ", "UserId": " u\t", "UserPassword": "  pw!! "}, lambda m: None)
    finally:
        sm.post_failover = real
    assert sent["CompanyId"] == "co" and sent["UserId"] == "u" and sent["UserPassword"] == "pw!!", sent
    ok("로그인 본문 — 업체ID·사용자ID·비번 앞뒤 공백 제거(앱 Trim 과 동일·평문)")


def test_dry_run_no_write():
    # apply=False(미리보기) → 대조·리포트는 하되 관리대장·credstore 에 아무것도 안 쓴다(갱신 예정 건수는 그대로 보고)
    with tempfile.TemporaryDirectory() as d:
        store = CredStore(Path(d) / "creds.json")
        cl = FakeClient()
        out = sm.run_daily_sync(
            "URL", "Sheet1", LEDGER_ROWS, store=store, client=cl,
            fetch=lambda s, log: dict(SHOPMINE), log=lambda m: None,
            now=datetime(2026, 11, 10), out_dir=str(Path(d) / "rep"), apply=False)
        assert out == {"accounts": 6, "updated": 2, "cells": 0, "report": out["report"]}, out
        assert cl.writes == [], "dry-run 은 관리대장에 쓰지 않아야 함"
        assert cl.backups == [], "dry-run 은 백업 탭도 안 만든다(변경 안 하니까)"
        assert not store.get_password("shopA"), "dry-run 은 credstore 도 안 건드림"
        assert Path(out["report"]).exists(), "리포트는 생성(대조 결과 미리보기)"
    ok("dry-run — 대조·리포트만 · 관리대장/credstore 쓰기 0 · 백업 0 · 갱신 예정 건수 보고")


def test_no_pw_col_skips():
    out = sm.run_daily_sync("URL", "S", [["대표자명", "상품명"]], store=None,
                            client=FakeClient(), fetch=lambda s, log: {"x": "y"}, log=lambda m: None,
                            now=datetime(2026, 11, 10), out_dir=tempfile.mkdtemp())
    assert out == {"skipped": "no_pw_col"}, out
    ok("비번 열 없으면 대조 건너뜀(쓰기 없음)")


def test_daily_gate_nocred_logs_once():
    # ⑤ 자격 없음 = 조용히 건너뛰지 않고 그날 1번 로그(운용 PC 0회를 몰랐던 원인 — T-160 ①)
    with tempfile.TemporaryDirectory() as d:
        store = CredStore(Path(d) / "creds.json")
        assert sm.daily_gate(store, "2026-11-23", "", "") == sm.GATE_NOCRED_LOG, "자격 없음 첫 확인 = 로그"
        assert sm.daily_gate(store, "2026-11-23", "", "2026-11-23") == sm.GATE_NOCRED_QUIET, "그날 두 번째부터 조용히"
        assert sm.daily_gate(store, "2026-11-24", "", "2026-11-23") == sm.GATE_NOCRED_LOG, "다음 날 다시 1번"
        sm.store_login({"CompanyId": "co1", "UserPassword": SECRET}, store)
        assert sm.daily_gate(store, "2026-11-23", "", "2026-11-23") == sm.GATE_RUN, "자격 있으면 실행"
        assert sm.daily_gate(store, "2026-11-23", "2026-11-23", "") == sm.GATE_DONE, "오늘 이미 함 = 안 함"
    assert "설정 탭" in sm.NOCRED_MSG and "샵마인 로그인 입력" in sm.NOCRED_MSG and "setup" not in sm.NOCRED_MSG, sm.NOCRED_MSG
    ok("자격 없음 — 하루 1번 로그(그날 두 번째 조용히·다음 날 다시) · 자격 있으면 실행 · 오늘 이미 함 = 안 함")


def test_refused_value_not_written():
    # ⑥ 샵마인 값 = 24시간 안 쿠팡 거부값 → 대장(맞는 값 9줄)을 덮지 않고 ⚠ 로그(실측 위험: 샵마인에 옛 값이면 맞는 값 지움)
    rows = [HEADER, ["", "DW", "dw1", "oldA", "p1"], ["", "DW", "dw1", "newA", "p2"], ["", "DW", "dw1", "newA", "p3"],
            ["", "B", "b1", "oldB", "p1"]]
    shopmine = {"dw1": "oldA", "b1": "newB"}
    LT.record_failure("dw1", LT.PW_WRONG, "oldA")                       # 쿠팡이 방금 oldA 를 거부
    with tempfile.TemporaryDirectory() as d:
        store, cl, logs = CredStore(Path(d) / "creds.json"), FakeClient(), []
        out = sm.run_daily_sync("URL", "Sheet1", rows, store=store, client=cl, fetch=lambda s_, log: dict(shopmine),
                                log=logs.append, now=datetime(2026, 11, 23, 0, 10), out_dir=str(Path(d) / "rep"))
        assert out["updated"] == 1 and {c[1] for c in cl.writes} == {"D5"}, (out, cl.writes)
        assert not store.get_password("dw1"), "거부값으로 credstore 도 안 바꿈"
        assert any("dw1" in m and "덮지 않음" in m and "⚠" in m for m in logs), logs
        text = Path(out["report"]).read_text(encoding="utf-8-sig")
        assert f"dw1,{sm.ST_SM_REFUSED}" in text, text
        for v in ("oldA", "newA", "oldB", "newB"):
            assert v not in text and not any(v in m for m in logs), f"값 '{v}' 노출"
    LT._path(None).unlink(missing_ok=True)
    ok("샵마인 값 = 24시간 안 거부값 → 대장·credstore 안 덮음 · ⚠ 로그 · 리포트 상태 · 다른 계정은 그대로 갱신")


def test_report_which_ledger_value():
    # ③ 리포트(값 없이)에 샵마인 값 = 대장 값1/값2/다름
    rows = [HEADER, ["", "DW", "dw1", "oldA", "p1"], ["", "DW", "dw1", "newA", "p2"], ["", "DW", "dw1", "newA", "p3"],
            ["", "W", "w1", "x1", "p1"], ["", "Z", "z1", "zz", "p1"]]
    cands, _ = sm.ledger_password_map(rows)
    lab = sm.ledger_value_label({"dw1": "newA", "w1": "x1", "z1": "other", "e1": "e"}, cands)
    assert lab == {"dw1": "값2", "w1": "값1", "z1": "대장 값과 다름", "e1": "-"}, lab
    with tempfile.TemporaryDirectory() as d:
        out = sm.run_daily_sync("URL", "Sheet1", rows, store=CredStore(Path(d) / "c.json"), client=FakeClient(),
                                fetch=lambda s_, log: {"dw1": "newA", "w1": "x1"}, log=lambda m: None,
                                now=datetime(2026, 11, 23), out_dir=str(Path(d) / "rep"), apply=False, refused=lambda a, p: False)
        text = Path(out["report"]).read_text(encoding="utf-8-sig").splitlines()
        assert text[0] == "계정ID,상태,샵마인=대장" and f"dw1,{sm.ST_DIFF},값2" in text and f"w1,{sm.ST_MATCH},값1" in text, text
        assert not any(v in "\n".join(text) for v in ("oldA", "newA", "x1", "zz")), "리포트에 값 없음"
    ok("리포트 '샵마인=대장' — 값1/값2(시작 로그 번호)·대장 값과 다름·- · 값 없음")


def test_on_applied_reapplies_candidates():
    # ⑦ 동기화로 대장이 바뀌면 비밀번호 후보를 그 자리에서 다시 반영(전엔 다음 대장 읽기까지 옛 순서 — 1번째 옛 값)
    from coupang_analytics.input_list import parse_password_candidates
    rows = [HEADER, ["", "DW", "dw1", "oldA", "p1"], ["", "DW", "dw1", "newA", "p2"], ["", "DW", "dw1", "newA", "p3"]]
    assert [c.password for c in parse_password_candidates(rows)["dw1"]][0] == "oldA", "전: 1줄 옛 값이 1번째"
    got = []
    with tempfile.TemporaryDirectory() as d:
        sm.run_daily_sync("URL", "Sheet1", rows, store=CredStore(Path(d) / "c.json"), client=FakeClient(),
                          fetch=lambda s_, log: {"dw1": "newA"}, log=lambda m: None, now=datetime(2026, 11, 23),
                          out_dir=str(Path(d) / "rep"), refused=lambda a, p: False,
                          on_applied=lambda new_rows: got.append(parse_password_candidates(new_rows)))
        assert len(got) == 1 and [c.password for c in got[0]["dw1"]] == ["newA"], got
        assert [r[3] for r in rows[1:]] == ["oldA", "newA", "newA"], "원래 격자는 그대로(사본만 고침)"
        got.clear()
        sm.run_daily_sync("URL", "Sheet1", rows, store=CredStore(Path(d) / "c.json"), client=FakeClient(),
                          fetch=lambda s_, log: {"dw1": "newA"}, log=lambda m: None, now=datetime(2026, 11, 23),
                          out_dir=str(Path(d) / "rep"), apply=False, refused=lambda a, p: False,
                          on_applied=lambda new_rows: got.append(1))
        assert got == [], "미리보기(쓰기 없음)는 다시 반영 안 부름"
    src = (ROOT / "ui" / "app_qt.py").read_text(encoding="utf-8")
    body = src[src.index("def _maybe_shopmine_sync"):src.index("def _maybe_account_suspend")]
    assert "shopmine_sync.app_daily_hook(" in body, "앱 훅 = app_daily_hook(하루 1번 자격 안내·첫날 리포트만 D-389)"
    assert "on_applied=" in body and "_apply_pw_candidates(" in body, "앱 훅 = 되쓴 뒤 후보 다시 반영"
    assert "load_login(self.creds_store) is None" not in body, "옛 '조용히 건너뜀' 분기 없음"
    ok("되쓴 뒤 후보 다시 반영 — 한 값으로 통일된 후보 · 원 격자 불변 · 미리보기는 안 부름 · 앱 훅 연결")


def test_make_login_defaults():
    # D-196 실서버 성공 로그인 본문 = OsVersion "" · ShopmineVersion 26.8.24.866 · 필드 MarketId/MarketPassword
    c = sm.make_login(" co1 ", " user1 ", SECRET)
    assert c == {"CompanyId": "co1", "UserId": "user1", "UserPassword": SECRET, "OsVersion": "",
                 "ShopmineVersion": "26.8.24.866", "IdKey": "MarketId", "PwKey": "MarketPassword",
                 "StartPage": 1, "PageSize": 100}, c
    c2 = sm.make_login("co1", "", SECRET, ShopmineVersion="9.9", OsVersion=None)
    assert c2["ShopmineVersion"] == "9.9" and c2["OsVersion"] == "", "CLI 가 준 값만 바꿈(None=기본값)"
    cli = (ROOT / "tools" / "shopmine_sync.py").read_text(encoding="utf-8")
    assert "sm.make_login(" in cli and '"OsVersion": a.os_version' not in cli, "CLI setup = 앱과 같은 make_login"
    ok("로그인 블록 — 설정 탭·CLI 같은 make_login · D-196 성공값 기본 · CLI 지정값만 덮음")


def test_resolve_fields():
    assert sm.resolve_fields([{"marketid": "a", "MARKETPASSWORD": "p"}], "MarketId", "MarketPassword") == \
        ("marketid", "MARKETPASSWORD"), "대소문자만 다르면 실제 이름"
    for recs, want in (([], "0건"), ([{"Id": "a", "Pw": "zz-secret"}], "필드")):
        try:
            sm.resolve_fields(recs, "MarketId", "MarketPassword")
            assert False, "ShopmineError 기대"
        except sm.ShopmineError as exc:
            assert want in str(exc) and "zz-secret" not in str(exc), str(exc)
    ok("discover 자동 — 필드 대소문자 맞춤 · 0건/필드 없음 = 오류(필드명만·값 없음)")


def _fake_server(login_ok=True, recs=None):
    """post_failover 대역 — 로그인 응답 / 계정 목록 응답. 호출 기록 반환."""
    calls = []

    def fake(path, body, log=None):
        calls.append(path)
        if path == "api/login":
            return "srv", ({"AuthenticationKey": "K", "IsSuccess": True} if login_ok
                           else {"AuthenticationKey": "", "IsSuccess": False})
        return "srv", {"DataTable": list(recs or [])}
    return fake, calls


def test_login_rejected_marks_and_stops():
    real = sm.post_failover
    with tempfile.TemporaryDirectory() as d:
        store, logs = CredStore(Path(d) / "c.json"), []
        sm.store_login(sm.make_login("co1", "u1", SECRET), store)
        try:
            sm.post_failover, calls = _fake_server(login_ok=False)
            okk, msg = sm.check_login(store, logs.append)
            assert not okk and "거부" in msg and SECRET not in msg, msg
            assert sm.load_login(store)[sm.REJECTED_FLAG] is True, "거부 표시"
            assert sm.daily_gate(store, "2026-11-24", "", "") == sm.GATE_REJECTED_LOG, "거부 = 그날 1번 안내"
            assert sm.daily_gate(store, "2026-11-24", "", "2026-11-24") == sm.GATE_NOCRED_QUIET, "그날 두 번째 조용히"
            assert "설정 탭" in sm.REJECTED_MSG and sm.NOTICE_MSG[sm.GATE_REJECTED_LOG] == sm.REJECTED_MSG
            n_before = len(calls)
            st = {}
            gate = sm.app_daily_hook("URL", "S", LEDGER_ROWS, store=store, today="2026-11-24",
                                     get_state=lambda k: st.get(k, ""), set_state=st.__setitem__, log=logs.append)
            assert gate == sm.GATE_REJECTED_LOG and len(calls) == n_before, "거부된 자격으로 다시 로그인하지 않음(잠금 방지)"
            assert logs[-1] == sm.REJECTED_MSG, logs
            sm.store_login(sm.make_login("co1", "u1", "other"), store)          # 다시 입력 = 표시 풀림
            assert sm.daily_gate(store, "2026-11-24", "", "2026-11-24") == sm.GATE_RUN
            sm.post_failover, calls = _fake_server(recs=[{"marketid": "shopA", "marketpassword": "newA"},
                                                         {"marketid": "shopC", "marketpassword": "cpw"}])
            okk, msg = sm.check_login(store, logs.append)
            assert okk and "2건" in msg, msg
            assert sm.load_login(store)["IdKey"] == "marketid", "실제 필드명 저장(discover 자동)"
        finally:
            sm.post_failover = real
        for v in (SECRET, "other", "newA", "cpw"):
            assert not any(v in m for m in logs), f"로그에 값 '{v}' 노출"
    ok("샵마인 로그인 거부 — 표시·하루 1번 안내·재로그인 0 · 다시 입력하면 풀림 · 연결 확인 = 건수·필드명 저장 · 값 미노출")


def test_proven_guard():
    # ⑤ DW 모양: 대장 옛값 1줄 + 맞는 값 2줄 · 지난 로그인 성공 = newA. 샵마인이 옛값이면 덮지 않음, 성공값이면 통일.
    rows = [HEADER, ["", "DW", "dw1", "oldA", "p1"], ["", "DW", "dw1", "newA", "p2"], ["", "DW", "dw1", "newA", "p3"],
            ["", "B", "b1", "oldB", "p1"]]
    LT.record_success("dw1", "newA", now=datetime.now() - timedelta(hours=2))
    try:
        cands, _ = sm.ledger_password_map(rows)
        st = dict(sm.classify({"dw1": "oldA", "b1": "newB"}, cands, None, LT.proven_ok))
        assert st == {"dw1": sm.ST_LED_PROVEN, "b1": sm.ST_DIFF}, st
        assert dict(sm.classify({"dw1": "newA"}, cands, None, LT.proven_ok))["dw1"] == sm.ST_DIFF, "샵마인=성공값 → 통일"
        with tempfile.TemporaryDirectory() as d:
            cl, logs = FakeClient(), []
            out = sm.run_daily_sync("URL", "Sheet1", rows, store=CredStore(Path(d) / "c.json"), client=cl,
                                    fetch=lambda s_, log: {"dw1": "oldA", "b1": "newB"}, log=logs.append,
                                    now=datetime(2026, 11, 24), out_dir=str(Path(d) / "rep"))
            assert out["updated"] == 1 and {c[1] for c in cl.writes} == {"D5"}, (out, cl.writes)
            assert any("dw1" in m and "성공한 값" in m and "덮지 않음" in m for m in logs), logs
            assert f"dw1,{sm.ST_LED_PROVEN}" in Path(out["report"]).read_text(encoding="utf-8-sig")
            for v in ("oldA", "newA", "oldB", "newB"):
                assert not any(v in m for m in logs), f"로그에 값 '{v}' 노출"
        LT.record_failure("dw1", LT.PW_WRONG, "newA", now=datetime.now() - timedelta(hours=1))   # 그 뒤 쿠팡이 성공값을 거부 = 비번 바뀜
        assert not LT.proven_ok("dw1", "newA"), "성공 뒤 거부 = 더는 성공값 아님"
        assert dict(sm.classify({"dw1": "oldX"}, cands, None, LT.proven_ok))["dw1"] == sm.ST_DIFF, "→ 샵마인 값 반영"
        assert not LT.proven_ok("dw1", "") and not LT.proven_ok("zz", "newA")
    finally:
        LT._path(None).unlink(missing_ok=True)
    ok("⑤ 대장 성공값 보호 — 샵마인 옛값이면 대장 유지·⚠·리포트 · 샵마인=성공값이면 통일 · 성공값이 거부되면 해제")


def test_app_daily_hook_first_day_preview():
    with tempfile.TemporaryDirectory() as d:
        store, st, logs = CredStore(Path(d) / "c.json"), {}, []
        kw = dict(store=store, get_state=lambda k: st.get(k, ""), set_state=st.__setitem__, log=logs.append)
        assert sm.app_daily_hook("URL", "Sheet1", LEDGER_ROWS, today="2026-11-24", **kw) == sm.GATE_NOCRED_LOG
        assert logs == [sm.NOCRED_MSG] and st == {sm.K_NOTICE: "2026-11-24"}, (logs, st)
        sm.app_daily_hook("URL", "Sheet1", LEDGER_ROWS, today="2026-11-24", **kw)
        assert logs == [sm.NOCRED_MSG], "그날 두 번째 조용히"
        sm.store_login(sm.make_login("co1", "u1", SECRET), store)
        sync = dict(fetch=lambda s_, log: dict(SHOPMINE), out_dir=str(Path(d) / "rep"),
                    refused=lambda a, p: False, proven=lambda a, p: False)
        cl1, got = FakeClient(), []
        sm.app_daily_hook("URL", "Sheet1", LEDGER_ROWS, today="2026-11-24", client=cl1,
                          now=datetime(2026, 11, 24, 18), on_applied=got.append, **sync, **kw)
        assert cl1.writes == [] and cl1.backups == [] and got == [], "첫날 = 대조 리포트만(대장·백업 0)"
        assert st[sm.K_FIRST_REPORT] == "2026-11-24" and st[sm.K_LAST_SYNC] == "2026-11-24", st
        assert any("첫 동기화" in m and "리포트만" in m for m in logs) and any("미리보기" in m for m in logs), logs
        assert list((Path(d) / "rep").glob("대조_*.csv")), "첫날 리포트 생성"
        assert sm.app_daily_hook("URL", "Sheet1", LEDGER_ROWS, today="2026-11-24", client=cl1, **sync, **kw) \
            == sm.GATE_DONE
        cl2 = FakeClient()
        sm.app_daily_hook("URL", "Sheet1", LEDGER_ROWS, today="2026-11-25", client=cl2,
                          now=datetime(2026, 11, 25, 18), on_applied=got.append, **sync, **kw)
        assert len(cl2.writes) == 4 and len(cl2.backups) == 1 and len(got) == 1, "다음 날 = 자동 반영(백업 먼저)"
        assert st[sm.K_FIRST_REPORT] == "2026-11-24" and st[sm.K_LAST_SYNC] == "2026-11-25", st
        assert not any(v in m for m in logs for v in SM_VALUES + [SECRET]), "로그에 값 없음"
    assert sm.REPORT_DIR == "output/샵마인동기화"
    ok("앱 훅 — 자격 없음 하루 1번 · 첫날 대조 리포트만(쓰기·백업 0) · 같은 날 다시 안 함 · 다음 날 자동 반영")


def test_settings_tab_ui():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(ROOT / "ui"))
    from PySide6 import QtCore, QtWidgets
    import shopmine_login_qt as UI
    _qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    seen = {}

    def fill():
        dlg = next(w for w in QtWidgets.QApplication.topLevelWidgets()
                   if isinstance(w, QtWidgets.QDialog) and w.isVisible())
        company, user, pw = dlg.fields
        seen["echo"] = pw.echoMode()
        company.setText(" co1 ")
        user.setText("u1")
        pw.setText(SECRET)
        dlg.accept()
    QtCore.QTimer.singleShot(0, fill)
    assert UI.ask_login(None) == ("co1", "u1", SECRET)
    assert seen["echo"] == QtWidgets.QLineEdit.Password, "비밀번호 칸 = 화면에 안 보임"
    with tempfile.TemporaryDirectory() as d:
        store = CredStore(Path(d) / "c.json")
        assert UI.saved_label(store) == UI.LBL_NONE
        logs, lbl = [], QtWidgets.QLabel()
        fake = type("F", (UI.ShopmineLoginMixin,), {})()
        fake.creds_store, fake.log, fake.shopmine_lbl = store, logs.append, lbl
        fake.run_bg = lambda task, on_done=None, **k: on_done(task())
        real_ask, real_chk = UI.ask_login, sm.check_login
        try:
            UI.ask_login = lambda parent: ("co1", "u1", SECRET)
            sm.check_login = lambda s_, log: (True, "연결됨 — 샵마인 계정 59건(비밀번호 값은 안 보임)")
            fake.load_shopmine_login()
        finally:
            UI.ask_login, sm.check_login = real_ask, real_chk
        assert sm.load_login(store) == sm.make_login("co1", "u1", SECRET), "입력 즉시 DPAPI 저장(make_login)"
        assert SECRET not in (Path(d) / "c.json").read_text(encoding="utf-8"), "디스크 평문 없음"
        assert "59건" in lbl.text() and SECRET not in lbl.text(), lbl.text()
        assert not any(SECRET in m for m in logs), logs
        fake._show_saved_shopmine()
        assert lbl.text() == UI.LBL_SAVED
        sm.mark_rejected(store)
        assert UI.saved_label(store) == UI.LBL_REJECTED
    src = (ROOT / "ui" / "app_qt.py").read_text(encoding="utf-8")
    assert '("샵마인 로그인 입력", self.load_shopmine_login, self.shopmine_lbl)' in src, "설정 탭 '파일 · API 키' 줄"
    assert "ShopmineLoginMixin, QtWidgets.QMainWindow" in src and "self._show_saved_shopmine()" in src
    export = src[src.index("_EXPORT_CREDS = ("):].split("\n", 1)[0]
    assert "shopmine" not in export.lower(), "샵마인 자격은 배포 설정 내보내기(평문)에 안 담음"
    ok("설정 탭 — '샵마인 로그인 입력' 줄 · 비번 칸 가림 · 입력 즉시 DPAPI · 연결 확인 라벨 · 저장/거부 표시 · 배포 내보내기 제외")


def main():
    print("[verify_shopmine_sync_offline] 샵마인↔관리대장 동기화 오프라인 검증")
    LT.DEFAULT_DIR = tempfile.mkdtemp(prefix="sm_login_today_")   # 쿠팡 로그인 거부 기록 = 임시 폴더(운용 output 미접촉)
    LT._key = lambda: b"sm-test-key"                              # 실 credstore 지문 키 미접촉
    test_dpapi_roundtrip()
    test_field_discovery()
    test_col_letter()
    test_ledger_map()
    test_classify()
    test_updates_plan()
    test_unify_all_rows_when_partial_match()
    test_apply_updates()
    test_run_daily_sync_end_to_end()
    test_login_rejected_message()
    test_login_strips_fields()
    test_dry_run_no_write()
    test_no_pw_col_skips()
    test_daily_gate_nocred_logs_once()
    test_refused_value_not_written()
    test_report_which_ledger_value()
    test_on_applied_reapplies_candidates()
    test_make_login_defaults()
    test_resolve_fields()
    test_login_rejected_marks_and_stops()
    test_proven_guard()
    test_app_daily_hook_first_day_preview()
    test_settings_tab_ui()
    print("통과 — 실 API·실 자격 없이 결정적. 비번 평문 비노출 확인.")


if __name__ == "__main__":
    main()
