"""샵마인 비번 ↔ 관리대장 동기화 오프라인 검증 — 실 서버·실 자격 없이 결정적(D-195).

덮는 범위: ①DPAPI 왕복(store_login/load_login·평문 비노출) ②응답 필드 탐색(인증키·레코드 리스트·필드명·비번 추출)
③관리대장 비번 열 탐지·열 문자 ④대조 분류(같음/다름/샵마인에만/대장에만/빈 비번) ⑤갱신 계획(빈 값 제외·여러 줄 통일)
⑥되쓰기(구글시트 셀·credstore 갱신·값2 비움) ⑦end-to-end(리포트에 비번 값 없음·요약 숫자). 비번 평문은 어디에도 안 남는다.

    python tools/verify_shopmine_sync_offline.py
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


def main():
    print("[verify_shopmine_sync_offline] 샵마인↔관리대장 동기화 오프라인 검증")
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
    print("통과 — 실 API·실 자격 없이 결정적. 비번 평문 비노출 확인.")


if __name__ == "__main__":
    main()
