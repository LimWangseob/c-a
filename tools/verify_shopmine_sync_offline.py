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
        report = Path(out["report"])
        assert report.exists()
        text = report.read_text(encoding="utf-8-sig")
        for v in SM_VALUES:
            assert v not in text, f"리포트에 비번 값 '{v}' 가 노출됨"
        assert "shopA" in text and sm.ST_DIFF in text and sm.ST_SM_ONLY in text
    ok("end-to-end — 요약 숫자 · 갱신 4셀 · 리포트에 비번 값 0 · 상태 기록")


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
    test_apply_updates()
    test_run_daily_sync_end_to_end()
    test_no_pw_col_skips()
    print("통과 — 실 API·실 자격 없이 결정적. 비번 평문 비노출 확인.")


if __name__ == "__main__":
    main()
