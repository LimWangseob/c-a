"""셀독등록원장 오프라인 검증 — 설계서(designs/LEDGER_REGISTRY.md) 기대 동작을 가짜 대장·가짜 구글시트로 확인.

로그인·실 API 없음(결정적). 실패 시 AssertionError → exit 1. run_checks 게이트 편입.

    python tools/verify_registry_offline.py
"""
from __future__ import annotations

import copy
import re
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

from coupang_analytics import registry as R  # noqa: E402
from coupang_analytics import registry_gsheet as RG  # noqa: E402
from coupang_analytics import registry_model as M  # noqa: E402

# ── 가짜 관리대장 ─────────────────────────────────────────────────
# 실제 셀독리스트처럼 1행=예시, 2행=헤더. '완료일자'가 뒤(체험단)에 한 번 더 있다(앞쪽=그로스를 써야 함).
HDR = ["구분", "대표자명", "사업자명", "계정아이디", "비밀번호", "계약금", "체험단 주체", "상품명",
       "그로스 재고 (자동갱신 09.20)", "요청수량", "작업수량", "박스", "파레트", "완료일자", "출고일자",
       "1차체험단", "완료일자"]
W = len(HDR)
C_ACCT, C_PROD = 3, 7


def P(name, growth=("", "", "", "", "", ""), stock="", struck=False):
    return {"name": name, "growth": growth, "stock": stock, "struck": struck}


def A(aid, rep, biz, pw, dep="", exp="", products=(), struck=False):
    return {"aid": aid, "rep": rep, "biz": biz, "pw": pw, "dep": dep, "exp": exp,
            "products": list(products), "struck": struck}


def ledger(accounts):
    rows = [["예시"] + [""] * (W - 1), list(HDR)]
    strike = [[False] * W, [False] * W]
    for a in accounts:
        items = a["products"] or [None]
        for i, p in enumerate(items):
            row, srow = [""] * W, [False] * W
            if i == 0:
                row[1:7] = [a["rep"], a["biz"], a["aid"], a["pw"], a["dep"], a["exp"]]
                srow[C_ACCT] = a["struck"]
            if p:
                row[7], row[8] = p["name"], p["stock"]
                row[9:15] = list(p["growth"])
                row[16] = "체험단완료"          # 뒤쪽 '완료일자'(체험단) — 그로스 완료일자로 잡히면 안 됨
                srow[C_PROD] = p["struck"]
            rows.append(row)
            strike.append(srow)
    return rows, strike


def snap_of(accounts):
    rows, strike = ledger(accounts)
    return M.parse_ledger(rows, strike, "셀독리스트")


def day(d, h=18):
    return datetime(2026, 10, d, h, 0, 0)


def base():
    return [
        A("example01", "홍길동", "(주)예시상사", "pass!123", "300만", "셀독", [
            P("예시 비타민C 120정", ("100", "80", "3", "", "26.09.10", "26.09.12"), "418"),
            P("예시 오메가3 60캡슐", ("", "", "", "", "", ""), "5"),
            P("--"),                                        # 상품명 아님 → 제외
        ]),
        A("sample22", "김예시", "예시마켓", "0012", "-", "판매자", [
            P("예시 캠핑테이블", struck=True)]),             # 상품 취소선
        A("demo333", "이샘플", "샘플스토어", "demo#77", "200만", "셀독", [
            P("예시 마스카라")], struck=True),                # 계정 취소선
        A("nopd", "박없음", "무상품상사", "np!1"),              # 상품 없는 계정
    ]


def kinds(events, sheet=None):
    return [(e.sheet, e.kind, e.account_id, e.product, e.item) for e in events
            if sheet is None or e.sheet == sheet]


def status(reg, aid, prod):
    return reg.row_status(aid, prod)


def ok(msg):
    print(f"  ✔ {msg}")


# ── 엔진 시나리오 ─────────────────────────────────────────────────
def t1_initial():
    print("[R1] 최초등록 — 모든 계정·상품 행 생성, 취소선=관리중단")
    reg = R.Registry()
    snap = snap_of(base())
    assert any("상품명 아님" in w for w in snap.warnings), snap.warnings
    res = R.sync(reg, snap, now=day(1))
    keys = set(reg.rows)
    assert keys == {("example01", "예시 비타민C 120정"), ("example01", "예시 오메가3 60캡슐"),
                    ("sample22", "예시 캠핑테이블"), ("demo333", "예시 마스카라"), ("nopd", "")}, keys
    acct = [e for e in res.events if e.sheet == M.SHEET_ACCT]
    assert [e.kind for e in acct].count(M.K_INIT) == 4
    assert (M.SHEET_ACCT, M.K_STOP, "demo333", "", "관리상태") in kinds(res.events)
    assert (M.SHEET_PROD, M.K_STOP, "sample22", "예시 캠핑테이블", "관리상태") in kinds(res.events)
    assert status(reg, "example01", "예시 비타민C 120정") == (M.ST_ACTIVE, "")
    assert status(reg, "sample22", "예시 캠핑테이블") == (M.ST_STOPPED, "2026-10-01")
    assert status(reg, "demo333", "예시 마스카라") == (M.ST_STOPPED, "2026-10-01")
    assert status(reg, "nopd", "") == (M.ST_ACTIVE, "")
    row = reg.rows[("example01", "예시 비타민C 120정")]
    assert row.growth["그로스 완료일자"] == "2026-09-10", row.growth     # 뒤쪽 체험단 완료일자 아님·날짜 표기 통일(R15)
    assert row.acct["비밀번호"] == "pass!123" and row.stock == "418"
    assert reg.rows[("sample22", "예시 캠핑테이블")].acct["비밀번호"] == "0012"   # 앞자리 0 보존
    assert row.registered == "2026-10-01"
    nos = [e.no for e in reg.history if e.sheet == M.SHEET_ACCT]
    assert nos == list(range(1, len(nos) + 1)), nos
    ok("행 5개·최초등록 4계정·취소선 관리중단·그로스 열 앞쪽 매칭·비밀번호 원문")
    return reg


def t2_no_noise(reg):
    print("[R2] 표기 차이(공백·90.0) = 변경 아님")
    acc = base()
    acc[0]["products"][0] = P("  예시  비타민C 120정 ", ("100.0", "80", "3", "", "26.09.10", "26.09.12"), "418")
    res = R.sync(reg, snap_of(acc), now=day(2))
    assert res.events == [], kinds(res.events)
    ok("이력 0건")


def t3_edits(reg):
    print("[R3] 계정 수정(비밀번호 원문)·그로스 수정·재고=이력 없음")
    acc = base()
    acc[0]["pw"] = "new#456"
    acc[0]["dep"] = "500만"
    acc[0]["products"][0] = P("예시 비타민C 120정", ("100", "90", "3", "", "26.09.10", "26.09.12"), "400")
    res = R.sync(reg, snap_of(acc), now=day(3))
    ks = kinds(res.events)
    pw = [e for e in res.events if e.item == "비밀번호"][0]
    assert (pw.old, pw.new, pw.sheet) == ("pass!123", "new#456", M.SHEET_ACCT), pw
    assert (M.SHEET_ACCT, M.K_EDIT, "example01", "", "계약금") in ks
    g = [e for e in res.events if e.sheet == M.SHEET_GROWTH]
    assert [(e.item, e.old, e.new) for e in g] == [("그로스 작업수량", "80", "90")], g
    assert not any("재고" in e.item for e in res.events)
    assert reg.rows[("example01", "예시 비타민C 120정")].stock == "400"
    assert reg.rows[("example01", "예시 오메가3 60캡슐")].acct["비밀번호"] == "new#456"   # 계정 모든 줄 갱신
    assert "셀독리스트 X" not in pw.source and pw.source.startswith("셀독리스트 E"), pw.source
    ok("비번 원문 이력·계약금·작업수량 1건·재고 무기록·계정 전 줄 갱신")
    return acc


def t4_new(reg, acc):
    print("[R4] 신규계정·신규상품")
    acc = copy.deepcopy(acc)
    acc[0]["products"].append(P("예시 유산균 30포", ("87", "87", "1", "", "", "26.08.26")))
    acc.append(A("newacct1", "최신규", "신규상회", "nw!1", "100만", "셀독", [P("신규 텀블러")]))
    res = R.sync(reg, snap_of(acc), now=day(4))
    ks = kinds(res.events)
    assert (M.SHEET_ACCT, M.K_NEW_ACCT, "newacct1", "", "") in ks, ks
    assert (M.SHEET_PROD, M.K_NEW_PROD, "newacct1", "신규 텀블러", "") in ks
    assert (M.SHEET_PROD, M.K_NEW_PROD, "example01", "예시 유산균 30포", "") in ks
    assert reg.rows[("example01", "예시 유산균 30포")].registered == "2026-10-04"
    ok("신규계정 1·신규상품 2")
    return acc


def t5_product_delete(reg, acc):
    print("[R5] 상품 줄 삭제 = 그 줄만 관리중단")
    acc = copy.deepcopy(acc)
    acc[0]["products"] = [p for p in acc[0]["products"] if p["name"] != "예시 유산균 30포"]
    res = R.sync(reg, snap_of(acc), now=day(5))
    assert kinds(res.events) == [(M.SHEET_PROD, M.K_STOP, "example01", "예시 유산균 30포", "관리상태")], \
        kinds(res.events)
    assert status(reg, "example01", "예시 유산균 30포") == (M.ST_STOPPED, "2026-10-05")
    assert status(reg, "example01", "예시 비타민C 120정") == (M.ST_ACTIVE, "")
    assert res.events[0].source == "대장에서 상품 삭제"
    ok("관리중단 1줄·나머지 관리중")
    return acc


def t6_account_stop(reg, acc):
    print("[R6] 계정 취소선=전 줄 관리중단 · 계정 줄 삭제=관리중단(줄 보존)")
    acc = copy.deepcopy(acc)
    acc[0]["struck"] = True
    acc = [a for a in acc if a["aid"] != "sample22"]
    res = R.sync(reg, snap_of(acc), now=day(6))
    ks = kinds(res.events)
    assert (M.SHEET_ACCT, M.K_STOP, "example01", "", "관리상태") in ks
    assert (M.SHEET_ACCT, M.K_STOP, "sample22", "", "관리상태") in ks
    assert len(res.events) == 2, ks
    for p in ("예시 비타민C 120정", "예시 오메가3 60캡슐"):
        assert status(reg, "example01", p) == (M.ST_STOPPED, "2026-10-06")
    assert status(reg, "example01", "예시 유산균 30포") == (M.ST_STOPPED, "2026-10-05")   # 더 이른 중단일 유지
    assert ("sample22", "예시 캠핑테이블") in reg.rows                                    # 줄 보존
    assert [e for e in res.events if e.account_id == "sample22"][0].source == "대장에서 계정 삭제"
    ok("계정 2개 관리중단·줄 보존·상품 개별 중단일 유지")
    return acc


def t7_resume(reg, acc):
    print("[R7] 재개 — 계정 취소선 해제")
    acc = copy.deepcopy(acc)
    acc[0]["struck"] = False
    res = R.sync(reg, snap_of(acc), now=day(7))
    assert kinds(res.events) == [(M.SHEET_ACCT, M.K_RESUME, "example01", "", "관리상태")], kinds(res.events)
    assert status(reg, "example01", "예시 비타민C 120정") == (M.ST_ACTIVE, "")
    assert status(reg, "example01", "예시 유산균 30포") == (M.ST_STOPPED, "2026-10-05")   # 상품 자체 중단은 유지
    ok("계정 재개·삭제됐던 상품은 관리중단 유지")
    return acc


def t8_product_rename(reg, acc):
    print("[R8] 상품명 변경 의심 = 보류 → 승인/반려")
    acc = copy.deepcopy(acc)
    for p in acc[0]["products"]:
        if p["name"] == "예시 오메가3 60캡슐":
            p["name"] = "예시 오메가3 60캡슐 2개"
    res = R.sync(reg, snap_of(acc), now=day(8))
    assert kinds(res.events) == [(M.SHEET_PROD, M.K_RENAME_PROD, "example01", "예시 오메가3 60캡슐 2개", "상품명")], \
        kinds(res.events)
    pend = res.events[0]
    assert pend.confirm == M.C_PENDING and (pend.old, pend.new) == ("예시 오메가3 60캡슐", "예시 오메가3 60캡슐 2개")
    assert ("example01", "예시 오메가3 60캡슐") in reg.rows and status(reg, "example01", "예시 오메가3 60캡슐")[0] == M.ST_ACTIVE
    assert ("example01", "예시 오메가3 60캡슐 2개") not in reg.rows
    again = R.sync(reg, snap_of(acc), now=day(8, 19))
    assert again.events == [], kinds(again.events)                      # 같은 보류 반복 기록 없음
    pend.confirm = M.C_APPROVE                                          # 담당자 승인(확인상태 칸)
    res = R.sync(reg, snap_of(acc), now=day(9))
    assert kinds(res.events) == [(M.SHEET_PROD, M.K_CONFIRMED, "example01", "예시 오메가3 60캡슐 2개", "상품명")], \
        kinds(res.events)
    assert res.events[0].note.startswith(f"#{pend.no}")
    assert ("example01", "예시 오메가3 60캡슐 2개") in reg.rows and ("example01", "예시 오메가3 60캡슐") not in reg.rows
    assert reg.rows[("example01", "예시 오메가3 60캡슐 2개")].registered == "2026-10-01"   # 이력 이어짐
    ok("보류·중복기록 없음·승인=이름 이어붙임")
    # 반려: 다른 상품 이름 변경
    for p in acc[0]["products"]:
        if p["name"] == "예시 비타민C 120정":
            p["name"] = "예시 비타민C 120정 대용량"
    res = R.sync(reg, snap_of(acc), now=day(10))
    pend2 = res.events[0]
    assert pend2.kind == M.K_RENAME_PROD
    pend2.confirm = M.C_REJECT
    res = R.sync(reg, snap_of(acc), now=day(11))
    ks = kinds(res.events)
    assert ks[0] == (M.SHEET_PROD, M.K_REJECTED, "example01", "예시 비타민C 120정 대용량", "상품명"), ks
    assert (M.SHEET_PROD, M.K_NEW_PROD, "example01", "예시 비타민C 120정 대용량", "") in ks
    assert (M.SHEET_PROD, M.K_STOP, "example01", "예시 비타민C 120정", "관리상태") in ks
    again = R.sync(reg, snap_of(acc), now=day(12))
    assert again.events == [], kinds(again.events)                      # 반려된 쌍은 다시 보류 안 함
    ok("반려=옛 상품 관리중단+새 상품 신규·재보류 없음")
    return acc


def t9_account_rename(reg, acc):
    print("[R9] 계정아이디 변경 의심 = 보류 → 승인")
    acc = copy.deepcopy(acc)
    for a in acc:
        if a["aid"] == "newacct1":
            a["aid"] = "newacct2"
    res = R.sync(reg, snap_of(acc), now=day(13))
    assert kinds(res.events) == [(M.SHEET_ACCT, M.K_RENAME_ACCT, "newacct2", "", "계정아이디")], kinds(res.events)
    assert ("newacct1", "신규 텀블러") in reg.rows and status(reg, "newacct1", "신규 텀블러")[0] == M.ST_ACTIVE
    res.events[0].confirm = M.C_APPROVE
    res = R.sync(reg, snap_of(acc), now=day(14))
    assert kinds(res.events) == [(M.SHEET_ACCT, M.K_CONFIRMED, "newacct2", "", "계정아이디")], kinds(res.events)
    assert ("newacct2", "신규 텀블러") in reg.rows and ("newacct1", "신규 텀블러") not in reg.rows
    assert status(reg, "newacct2", "신규 텀블러") == (M.ST_ACTIVE, "")
    ok("보류·승인=계정 줄 이동·상태 유지")
    return acc


def t10_guard():
    print("[R10] 대장 계정 급감 = 반영 중단(원장 불변)")
    accs = [A(f"g{i}", f"대표{i}", f"상사{i}", "pw", products=[P(f"상품{i}")]) for i in range(6)]
    reg = R.Registry()
    R.sync(reg, snap_of(accs), now=day(1))
    before = len(reg.history)
    try:
        R.sync(reg, snap_of(accs[:1]), now=day(2))
    except R.RegistryGuardError as exc:
        assert "급감" in str(exc), exc
    else:
        raise AssertionError("급감인데 중단 안 됨")
    assert len(reg.history) == before
    ok("RegistryGuardError·이력 불변")


def t11_as_of_and_integrity(reg):
    print("[R11] as_of 과거 복원·무결성")
    d2 = R.as_of(reg, "2026-10-02")
    assert d2[("example01", "예시 비타민C 120정")]["비밀번호"] == "pass!123"
    assert d2[("example01", "예시 비타민C 120정")]["계약금"] == "300만"
    assert d2[("example01", "예시 비타민C 120정")]["그로스 작업수량"] == "80"
    assert ("example01", "예시 유산균 30포") not in d2                           # 10/4 신규 이전
    assert ("newacct1", "신규 텀블러") not in d2
    d6 = R.as_of(reg, "2026-10-06")
    assert d6[("example01", "예시 비타민C 120정")]["관리상태"] == M.ST_STOPPED
    assert d6[("example01", "예시 오메가3 60캡슐")]["상품명"] == "예시 오메가3 60캡슐"   # 이름변경(10/9) 이전
    assert R.as_of(reg, "2026-09-30") == {}
    R.check_integrity(reg)
    bad = copy.deepcopy(reg)
    bad.rows[("example01", "예시 오메가3 60캡슐 2개")].acct["계약금"] = "999만"      # 이력과 안 맞는 손수정
    try:
        R.check_integrity(bad)
    except R.RegistryIntegrityError:
        pass
    else:
        raise AssertionError("이력과 안 맞는 원장 값을 못 잡음")
    gap = copy.deepcopy(reg)
    gap.history = [h for h in gap.history if not (h.sheet == M.SHEET_ACCT and h.no == 2)]
    try:
        R.check_integrity(gap)
    except R.RegistryIntegrityError as exc:
        assert "번호" in str(exc)
    else:
        raise AssertionError("이력 번호 누락을 못 잡음")
    ok("10/2·10/6 복원·9/30=빈 원장·손수정/번호누락 검출")


def t12_managed_between(reg):
    print("[R12] managed_between — 기간 중 한 번이라도 관리한 계정(현재 중단 포함)")
    got = R.managed_between(reg, "2026-10-01", "2026-10-03")
    assert "sample22" in got and "demo333" in got and "example01" in got, got
    got = R.managed_between(reg, "2026-10-07", "2026-10-31")
    assert "sample22" not in got and "example01" in got and "newacct2" in got, got
    assert "demo333" in R.managed_between(reg, "2026-10-01", "2026-10-01")          # 중단일 당일은 관리
    assert "demo333" not in R.managed_between(reg, "2026-10-02", "2026-10-31")
    ok("중단 계정 기간 포함·이후 제외·계정아이디 변경 이어짐")


# ── 구글시트 입출력(가짜 클라이언트) ─────────────────────────────
class FakeClient:
    def __init__(self):
        self.grids: dict[str, list[list[str]]] = {}
        self.writes: list = []
        self.batches: list = []

    def sheet_titles(self):
        return list(self.grids)

    def sheet_id(self, title):
        return (list(self.grids).index(title) + 1) if title in self.grids else None

    def ensure_sheets(self, titles):
        for t in titles:
            self.grids.setdefault(t, [])
        return {t: self.sheet_id(t) for t in titles}

    def read_values(self, sheet, cell_range=None):
        out = []
        for r in self.grids[sheet]:
            r = list(r)
            while r and r[-1] in ("", None):
                r.pop()
            out.append(r)
        while out and not out[-1]:
            out.pop()
        return out

    def write_values(self, sheet, rows, start="A1", raw=False):
        self.writes.append((sheet, start, raw))
        g = self.grids[sheet]
        r0 = int(re.sub(r"\D", "", start)) - 1
        while len(g) < r0 + len(rows):
            g.append([])
        for i, row in enumerate(rows):
            g[r0 + i] = [("" if v is None else str(v)) for v in row]

    def batch_update(self, requests):
        self.batches.append(requests)
        titles = list(self.grids)
        for q in requests:
            ins = q.get("insertDimension")
            if ins and ins["range"]["dimension"] == "ROWS":
                g = self.grids[titles[ins["range"]["sheetId"] - 1]]
                s, e = ins["range"]["startIndex"], ins["range"]["endIndex"]
                for _ in range(e - s):
                    g.insert(s, [])
        return {}


def reader(accounts):
    rows, strike = ledger(accounts)
    return lambda: ("셀독리스트", rows, strike)


def t13_io_roundtrip():
    print("[R13] 구글시트 입출력 — 시트 5개·RAW 쓰기·최신이 위·번호 연속·재로드 일치")
    cli = FakeClient()
    with tempfile.TemporaryDirectory() as tmp:
        res = RG.run_sync(cli, reader(base()), now=day(1), backup_dir=tmp)
        assert set(cli.grids) >= {M.SHEET_MAIN, M.SHEET_ACCT, M.SHEET_PROD, M.SHEET_GROWTH, M.SHEET_SYNC}
        assert cli.grids[M.SHEET_MAIN][0] == list(M.MAIN_HEADER)
        assert "쿠팡확인" in M.MAIN_HEADER and "쿠팡확인일" in M.MAIN_HEADER
        assert all(raw for (s, _, raw) in cli.writes), cli.writes                  # 비번 '0012' 보존용 RAW
        main = cli.grids[M.SHEET_MAIN]
        ix = {h: i for i, h in enumerate(main[0])}
        pws = {r[ix["계정아이디"]]: r[ix["비밀번호"]] for r in main[1:]}
        assert pws["sample22"] == "0012"
        assert main[1][ix["관리상태"]] == M.ST_ACTIVE                              # 관리중 먼저 정렬
        acc = copy.deepcopy(base())
        acc[0]["pw"] = "new#456"
        RG.run_sync(cli, reader(acc), now=day(2), backup_dir=tmp)
        ah = cli.grids[M.SHEET_ACCT]
        hx = {h: i for i, h in enumerate(ah[0])}
        nos = [int(r[hx["번호"]]) for r in ah[1:]]
        assert nos == sorted(nos, reverse=True) and nos[-1] == 1, nos               # 최신이 위·1부터
        assert ah[1][hx["항목"]] == "비밀번호" and ah[1][hx["이전값"]] == "pass!123"
        assert len(cli.grids[M.SHEET_SYNC]) == 3                                   # 헤더+실행 2건
        reg = RG.load_registry(cli)
        assert set(reg.rows) == set(res.registry.rows)
        R.check_integrity(reg)
        assert len(list(Path(tmp).glob("원장_*.xlsx"))) >= 1                       # 실행마다 로컬 백업
        # 승인 흐름: 사람이 시트의 확인상태 칸을 바꾼다
        acc[0]["products"][1]["name"] = "예시 오메가3 60캡슐 2개"
        RG.run_sync(cli, reader(acc), now=day(3), backup_dir=tmp)
        ph = cli.grids[M.SHEET_PROD]
        px = {h: i for i, h in enumerate(ph[0])}
        assert ph[1][px["확인상태"]] == M.C_PENDING
        ph[1][px["확인상태"]] = M.C_APPROVE
        RG.run_sync(cli, reader(acc), now=day(4), backup_dir=tmp)
        reg = RG.load_registry(cli)
        assert ("example01", "예시 오메가3 60캡슐 2개") in reg.rows
        # 이력 줄 삭제(누가 지움) → 무결성 중단·쓰기 없음
        del cli.grids[M.SHEET_ACCT][2]
        n_writes = len(cli.writes)
        try:
            RG.run_sync(cli, reader(acc), now=day(5), backup_dir=tmp)
        except R.RegistryIntegrityError:
            pass
        else:
            raise AssertionError("이력 줄 삭제를 못 잡음")
        assert len(cli.writes) == n_writes
    ok("시트5·RAW·정렬·번호·재로드·백업·시트 승인·무결성 중단")


def t14_ledger_read_fail_and_dry_run():
    print("[R14] 대장 읽기 실패=전체 중단 · 미리보기=쓰기 없음")
    cli = FakeClient()

    def boom():
        raise RuntimeError("403 권한 없음")
    try:
        RG.run_sync(cli, boom, now=day(1), backup_dir=None)
    except RuntimeError:
        pass
    else:
        raise AssertionError("대장 읽기 실패인데 진행됨")
    assert cli.writes == [] and cli.batches == [] and cli.grids == {}
    res = RG.run_sync(cli, reader(base()), now=day(1), backup_dir=None, dry_run=True)
    assert res.events and cli.writes == [] and cli.grids == {}
    ok("읽기 실패=아무것도 안 씀·미리보기=변경 목록만")


def t15_format_equivalence():
    print("[R15] 읽는 경로별 표시형식 차이 = 변경 아님(실측 2026-09-28: 엑셀 백업 vs 구글시트 표시값)")
    from datetime import datetime as _dt
    xlsx_like = [A("fmt01", "정형식", "형식상사", "pw", 31508400, "셀독", [
        P("형식 상품", ("500", "840", "10", "", _dt(2026, 8, 4), _dt(2026, 8, 18)))])]
    sheet_like = [A("fmt01", "정형식", "형식상사", "pw", "31,508,400", "셀독", [
        P("형식 상품", ("500", "840", "10", "", "26.8.4", "26.08.18"))])]
    reg = R.Registry()
    R.sync(reg, snap_of(xlsx_like), now=day(1))
    res = R.sync(reg, snap_of(sheet_like), now=day(2))
    assert res.events == [], kinds(res.events)
    row = reg.rows[("fmt01", "형식 상품")]
    assert row.acct["계약금"] == "31508400" and row.growth["그로스 출고일자"] == "2026-08-18", (row.acct, row.growth)
    for raw, want in (("2026-08-18", "2026-08-18"), ("2026/8/18", "2026-08-18"), ("26.08.18.", "2026-08-18"),
                      ("불가", "불가"), ("전량", "전량"), ("1,000개", "1,000개"), ("-", "-"), ("26.13.40", "26.13.40")):
        assert M.canon(raw) == want, (raw, M.canon(raw), want)
    assert M.canon_pw("1,234") == "1,234"                                        # 비밀번호는 원문 유지
    ok("쉼표 숫자·날짜 표기 통일·글자값/잘못된 날짜/비밀번호 원문 유지")


def t16_backfill():
    print("[R16] 소급 구축 — 과거 사본 날짜순 재생·사본별 동기화기록·원장 차 있으면 거부")
    day1 = base()
    day2 = copy.deepcopy(day1)
    day2[0]["pw"] = "new#456"
    day3 = [a for a in copy.deepcopy(day2) if a["aid"] != "nopd"]
    snaps = [(day(3), "관리대장_261003.xlsx", reader(day3)),        # 순서 섞어 넣어도 날짜순 재생
             (day(1), "관리대장_261001.xlsx", reader(day1)),
             (day(2), "관리대장_261002.xlsx", reader(day2))]
    cli = FakeClient()
    res = RG.run_backfill(cli, snaps, dry_run=True)
    assert cli.grids == {} and len(res) == 3                                         # 미리보기=쓰기 없음
    with tempfile.TemporaryDirectory() as tmp:
        res = RG.run_backfill(cli, snaps, backup_dir=tmp)
        reg = RG.load_registry(cli)
        R.check_integrity(reg)
        pw = [h for h in reg.history if h.item == "비밀번호"][0]
        assert pw.eff == "2026-10-02" and pw.old == "pass!123", pw
        stop = [h for h in reg.history if h.account_id == "nopd" and h.kind == M.K_STOP][0]
        assert stop.eff == "2026-10-03" and stop.source == "대장에서 계정 삭제"
        sync_rows = cli.grids[M.SHEET_SYNC]
        assert len(sync_rows) == 4, sync_rows                                        # 헤더 + 사본 3개
        assert "관리대장_261003.xlsx" in sync_rows[1][-1] and "관리대장_261001.xlsx" in sync_rows[3][-1]
        assert len(list(Path(tmp).glob("원장_*.xlsx"))) == 1                         # 소급 결과 로컬 백업
        n = len(cli.writes)
        try:
            RG.run_backfill(cli, snaps, backup_dir=tmp)
        except R.RegistryIntegrityError as exc:
            assert "이미" in str(exc)
        else:
            raise AssertionError("원장이 차 있는데 소급을 또 함")
        assert len(cli.writes) == n
    ok("날짜순·효력일=사본날짜·사본별 기록·백업·재실행 거부")


def main():
    t16_backfill()
    t15_format_equivalence()
    reg = t1_initial()
    t2_no_noise(reg)
    acc = t3_edits(reg)
    acc = t4_new(reg, acc)
    acc = t5_product_delete(reg, acc)
    acc = t6_account_stop(reg, acc)
    acc = t7_resume(reg, acc)
    acc = t8_product_rename(reg, acc)
    t9_account_rename(reg, acc)
    t10_guard()
    t11_as_of_and_integrity(reg)
    t12_managed_between(reg)
    t13_io_roundtrip()
    t14_ledger_read_fail_and_dry_run()
    print("셀독등록원장 오프라인 검증 통과")


if __name__ == "__main__":
    main()
