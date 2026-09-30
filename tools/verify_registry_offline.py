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

# 원장 잠금 격리 — 테스트가 실제 output/_원장.lock 을 건드리지 않게(임시 폴더).
LOCK = str(Path(tempfile.mkdtemp(prefix="reglock_")) / "_원장.lock")

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
        c0 = 0
        for ch in re.sub(r"\d", "", start):
            c0 = c0 * 26 + ord(ch) - 64
        c0 -= 1
        while len(g) < r0 + len(rows):
            g.append([])
        for i, row in enumerate(rows):
            vals = [("" if v is None else str(v)) for v in row]
            if c0 == 0:
                g[r0 + i] = vals
            else:                                       # 열 범위 쓰기 = 그 칸들만 덮어씀(나머지 열 보존)
                cur = list(g[r0 + i]) + [""] * max(0, c0 + len(vals) - len(g[r0 + i]))
                cur[c0:c0 + len(vals)] = vals
                g[r0 + i] = cur

    def read_grid(self, sheet, *, notes=False):
        vals = self.read_values(sheet)
        return vals, [[None] * len(r) for r in vals]

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
        res = RG.run_sync(cli, reader(base()), now=day(1), backup_dir=tmp, lock_path=LOCK)
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
        RG.run_sync(cli, reader(acc), now=day(2), backup_dir=tmp, lock_path=LOCK)
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
        RG.run_sync(cli, reader(acc), now=day(3), backup_dir=tmp, lock_path=LOCK)
        ph = cli.grids[M.SHEET_PROD]
        px = {h: i for i, h in enumerate(ph[0])}
        assert ph[1][px["확인상태"]] == M.C_PENDING
        ph[1][px["확인상태"]] = M.C_APPROVE
        RG.run_sync(cli, reader(acc), now=day(4), backup_dir=tmp, lock_path=LOCK)
        reg = RG.load_registry(cli)
        assert ("example01", "예시 오메가3 60캡슐 2개") in reg.rows
        # 이력 줄 삭제(누가 지움) → 무결성 중단·쓰기 없음
        del cli.grids[M.SHEET_ACCT][2]
        n_writes = len(cli.writes)
        try:
            RG.run_sync(cli, reader(acc), now=day(5), backup_dir=tmp, lock_path=LOCK)
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
        RG.run_sync(cli, boom, now=day(1), backup_dir=None, lock_path=LOCK)
    except RuntimeError:
        pass
    else:
        raise AssertionError("대장 읽기 실패인데 진행됨")
    assert cli.writes == [] and cli.batches == [] and cli.grids == {}
    res = RG.run_sync(cli, reader(base()), now=day(1), backup_dir=None, dry_run=True, lock_path=LOCK)
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
    res = RG.run_backfill(cli, snaps, dry_run=True, lock_path=LOCK)
    assert cli.grids == {} and len(res) == 3                                         # 미리보기=쓰기 없음
    with tempfile.TemporaryDirectory() as tmp:
        res = RG.run_backfill(cli, snaps, backup_dir=tmp, lock_path=LOCK)
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
            RG.run_backfill(cli, snaps, backup_dir=tmp, lock_path=LOCK)
        except R.RegistryIntegrityError as exc:
            assert "이미" in str(exc)
        else:
            raise AssertionError("원장이 차 있는데 소급을 또 함")
        assert len(cli.writes) == n
    ok("날짜순·효력일=사본날짜·사본별 기록·백업·재실행 거부")


def _expect(exc, fn, what):
    try:
        fn()
    except exc:
        return
    raise AssertionError(f"{what} — {exc.__name__} 안 남")


def t17_write_coupang_check():
    print("[R17] 쿠팡확인 쓰기 — 두 열만·줄키 우선·이력 불변·헤더 이름 탐지·검증")
    cli = FakeClient()
    with tempfile.TemporaryDirectory() as tmp:
        RG.run_sync(cli, reader(base()), now=day(1), backup_dir=tmp, lock_path=LOCK)
    before = copy.deepcopy(cli.grids)
    ix = {h: i for i, h in enumerate(cli.grids[M.SHEET_MAIN][0])}
    other = [c for h, c in ix.items() if h not in ("쿠팡확인", "쿠팡확인일")]
    checks = {"example01": ("확인됨", "2026-10-02"),
              ("example01", " 예시  오메가3 60캡슐 "): ("미등록", "2026-10-02"),     # 줄키(공백 정규화)가 우선
              "demo333": ("비밀번호불일치", "2026-10-02"),
              "ghost": ("로그인실패", "2026-10-02")}                                  # 원장에 없음 → 경고
    logs: list = []
    n_writes = len(cli.writes)
    assert RG.write_coupang_check(cli, checks, dry_run=True, on_log=logs.append, lock_path=LOCK) == 3
    assert cli.grids == before and len(cli.writes) == n_writes                       # 미리보기 = 무변경
    assert any("ghost" in m for m in logs), logs
    assert RG.write_coupang_check(cli, checks, lock_path=LOCK) == 3
    main = cli.grids[M.SHEET_MAIN]
    got = {(r[ix["계정아이디"]], r[ix["상품명"]]): (r[ix["쿠팡확인"]], r[ix["쿠팡확인일"]]) for r in main[1:]}
    assert got[("example01", "예시 비타민C 120정")] == ("확인됨", "2026-10-02")
    assert got[("example01", "예시 오메가3 60캡슐")] == ("미등록", "2026-10-02")
    assert got[("demo333", "예시 마스카라")] == ("비밀번호불일치", "2026-10-02")
    assert got[("sample22", "예시 캠핑테이블")] == ("", "")                         # 대상 아님 = 그대로
    old_main = {(r[ix["계정아이디"]], r[ix["상품명"]]): r for r in before[M.SHEET_MAIN][1:]}
    for r in main[1:]:
        o = old_main[(r[ix["계정아이디"]], r[ix["상품명"]])]
        assert [r[c] for c in other] == [o[c] if c < len(o) else "" for c in other], r   # 다른 열 불변
    assert all(cli.grids[s] == before[s] for s in (*M.HISTORY_SHEETS, M.SHEET_SYNC))   # 이력·동기화기록 불변
    assert cli.writes[-1] == (M.SHEET_MAIN, "S2", True), cli.writes[-1]              # 두 열 범위·RAW
    reg = RG.load_registry(cli)
    R.check_integrity(reg)
    assert reg.rows[("example01", "예시 오메가3 60캡슐")].coupang == "미등록"
    assert RG.write_coupang_check(cli, {"example01": ("확인됨", "2026-10-02")}, lock_path=LOCK) == 1   # 이미 확인됨인 줄은 변경 아님
    # 헤더 이름으로 탐지: 열 순서가 바뀌어도 쿠팡확인 칸을 찾는다
    moved = FakeClient()
    moved.grids[M.SHEET_MAIN] = [["메모", *main[0]], *[["x", *r] for r in main[1:]]]
    assert RG.write_coupang_check(moved, {"sample22": ("판매중지", "2026-10-03")}, lock_path=LOCK) == 1
    mx = {h: i for i, h in enumerate(moved.grids[M.SHEET_MAIN][0])}
    row = next(r for r in moved.grids[M.SHEET_MAIN][1:] if r[mx["계정아이디"]] == "sample22")
    assert (row[mx["쿠팡확인"]], row[mx["쿠팡확인일"]], row[0]) == ("판매중지", "2026-10-03", "x")
    # 검증: 값 6종·날짜 형식·원장 없음
    _expect(ValueError, lambda: RG.write_coupang_check(cli, {"example01": ("정상", "2026-10-02")}, lock_path=LOCK), "미지 값")
    _expect(ValueError, lambda: RG.write_coupang_check(cli, {"example01": ("확인됨", "26.10.02")}, lock_path=LOCK), "날짜 형식")
    _expect(R.RegistryIntegrityError, lambda: RG.write_coupang_check(FakeClient(), {}, lock_path=LOCK), "원장 없음")
    ok("미리보기 무변경·줄키 우선·다른 열/이력 불변·S2 RAW·재로드·열 이동 탐지·검증 예외")


def t18_previous_password():
    print("[R18] 직전 비밀번호 — 변경 없음=None·직전값·계정아이디 변경 추적")
    reg = R.Registry()
    acc = base()
    R.sync(reg, snap_of(acc), now=day(1))
    assert R.previous_password(reg, "example01") is None
    assert R.previous_password(reg, "없는계정") is None
    acc[0]["pw"] = "second#2"
    R.sync(reg, snap_of(acc), now=day(2))
    assert R.previous_password(reg, "example01") == "pass!123"
    acc[0]["pw"] = "third#3"
    R.sync(reg, snap_of(acc), now=day(3))
    assert R.previous_password(reg, "example01") == "second#2"
    acc[0]["pw"] = "second#2"                                     # 이전 값으로 되돌림 → 현재와 같은 값은 건너뜀
    R.sync(reg, snap_of(acc), now=day(4))
    assert R.previous_password(reg, "example01") == "third#3"
    acc[1]["pw"] = ""                                             # 비움 → 같은 값 복원: 이전값 '' 건너뛰고
    R.sync(reg, snap_of(acc), now=day(5))                         # 현재와 같은 '0012' 도 건너뜀 → None
    acc[1]["pw"] = "0012"
    acc[3]["pw"] = "np!2"
    R.sync(reg, snap_of(acc), now=day(5, 19))
    assert R.previous_password(reg, "sample22") is None
    for a in acc:
        if a["aid"] == "nopd":
            a["aid"] = "nopd2"
    res = R.sync(reg, snap_of(acc), now=day(6))
    assert (M.SHEET_ACCT, M.K_RENAME_ACCT, "nopd2", "", "계정아이디") in kinds(res.events), kinds(res.events)
    res.events[[e.kind for e in res.events].index(M.K_RENAME_ACCT)].confirm = M.C_APPROVE
    R.sync(reg, snap_of(acc), now=day(7))
    assert ("nopd2", "") in reg.rows
    assert R.previous_password(reg, "nopd2") == "np!1"                   # 옛 아이디(nopd) 이력까지 이어 봄
    ok("None·직전값·되돌림 건너뜀·계정아이디 변경 추적")


def t19_to_input_list():
    print("[R19] 원장 → 입력 — 관리중만·ledger 전체 줄·비번맵·as_of")
    reg = R.Registry()
    acc = base()
    acc[0]["products"].append(P("예시 유산균 30포"))
    R.sync(reg, snap_of(acc), now=day(1))
    acc[0]["products"][1]["struck"] = True                        # 오메가3 관리중단(10/2)
    R.sync(reg, snap_of(acc), now=day(2))
    il = R.to_input_list(reg)
    by = {a.account_id: a for a in il.accounts}
    assert set(by) == {"example01", "sample22", "nopd"}, set(by)  # demo333(계정 취소선) 제외
    ex = by["example01"]
    assert [p.name for p in ex.products] == ["예시 비타민C 120정", "예시 유산균 30포"]
    assert ex.ledger_products == {"예시 비타민C 120정", "예시 오메가3 60캡슐", "예시 유산균 30포"}
    assert (ex.representative, ex.business_name) == ("홍길동", "(주)예시상사")
    assert by["sample22"].products == [] and by["sample22"].ledger_products == {"예시 캠핑테이블"}
    assert by["nopd"].products == []
    assert il.ledger_account_ids == {"example01", "sample22", "demo333", "nopd"}   # 관리중단 계정도 줄 존재
    assert all(p.options and p.options[0].label == "" for p in ex.products)
    assert ex.products[0].inbound_summary == "출고일 : 2026-09-12\n요청수량 : 100 · 작업수량 : 80 · 박스 : 3"
    past = {a.account_id: a for a in R.to_input_list(reg, "2026-10-01").accounts}
    assert "예시 오메가3 60캡슐" in [p.name for p in past["example01"].products]   # 10/1엔 관리중
    pw = R.password_map(reg)
    assert pw == {"example01": "pass!123", "sample22": "0012", "nopd": "np!1"}, pw
    ok("관리중 계정·상품만·ledger_products/ids 전체·요약·as_of 과거·비번맵(중단 계정 제외)")


def t20_write_lock():
    print("[R20] 원장 쓰기 잠금 — 겹치면 대기 후 중단(쓰기 0)·미리보기 통과·예외 시 해제·프로세스 강제종료 시 OS 자동 해제")
    import subprocess
    from coupang_analytics import registry_lock as RL
    lock = str(Path(tempfile.mkdtemp(prefix="reglock20_")) / "_원장.lock")
    cli = FakeClient()
    RG.run_sync(cli, reader(base()), now=day(1), backup_dir=None, lock_path=lock)
    orig_wait = RL.LOCK_WAIT_SEC
    RL.LOCK_WAIT_SEC = 0.3
    try:
        with RL.registry_lock(lock):                               # 다른 원장 쓰기가 진행 중인 상황
            n, nb = len(cli.writes), len(cli.batches)
            logs: list = []
            _expect(R.RegistryLockError, lambda: RG.run_sync(cli, reader(base()), now=day(2), backup_dir=None,
                                                             lock_path=lock, log=logs.append), "run_sync 잠금")
            _expect(R.RegistryLockError, lambda: RG.write_coupang_check(
                cli, {"example01": ("확인됨", "2026-10-02")}, lock_path=lock), "쿠팡확인 잠금")
            _expect(R.RegistryLockError, lambda: RG.run_backfill(FakeClient(), [], lock_path=lock), "소급 잠금")
            assert len(cli.writes) == n and len(cli.batches) == nb, cli.writes[n:]   # 막히면 쓰기 0
            assert any("대기" in m for m in logs), logs
            assert RG.write_coupang_check(cli, {"example01": ("확인됨", "2026-10-02")}, dry_run=True,
                                          lock_path=lock) == 2                    # 미리보기는 잠금 무관
            RG.run_sync(cli, reader(base()), now=day(2), backup_dir=None, dry_run=True, lock_path=lock)
        try:                                                        # 블록 안 예외 → 해제
            with RL.registry_lock(lock):
                raise KeyError("boom")
        except KeyError:
            pass
        assert RG.write_coupang_check(cli, {"example01": ("확인됨", "2026-10-02")}, lock_path=lock) == 2
        # 다른 프로세스가 잠금을 쥔 채 강제 종료 → OS 가 풀어 즉시 획득(오래된 잠금 추측 로직 없음)
        code = ("import sys,time; sys.path.insert(0, sys.argv[1]);"
                "from coupang_analytics.registry_lock import registry_lock\n"
                "with registry_lock(sys.argv[2]):\n print('LOCKED', flush=True); time.sleep(60)")
        child = subprocess.Popen([sys.executable, "-c", code, str(ROOT / "src"), lock],
                                 stdout=subprocess.PIPE, text=True)
        try:
            assert child.stdout.readline().strip() == "LOCKED"
            _expect(R.RegistryLockError, lambda: RL.registry_lock(lock).__enter__(), "자식이 쥔 잠금")
        finally:
            child.kill()
            child.wait(10)
        with RL.registry_lock(lock, wait_sec=5):
            pass
    finally:
        RL.LOCK_WAIT_SEC = orig_wait
    ok("run_sync·쿠팡확인·소급 잠금 중단+쓰기 0·대기 로그·미리보기 통과·예외 해제·강제종료 후 즉시 획득")


def t21_company_stock():
    print("[R21] 회사보유재고 — 링크 탭·'창고 , 수량개' 표기·'-'=0·음수 경고·동일상품명(공백/대소문자 무시)·그 열만·미매칭 보존")
    from coupang_analytics import company_stock as CS
    assert [CS.parse_qty(v) for v in ("  5,670 ", "-", "- 1", " ", "abc", 12)] == [5670, 0, -1, None, None, 12]
    stock_cli = FakeClient()
    stock_cli.grids["Sheet1"] = [["재고현황 26.08.20 기준"], ["창고", "구분", "바코드", "상품명", " 현재고", "셀독"],
                                 ["김포1", "공산품", "1", "햄스트링기구 R010", "  2,360 ", "셀독"],
                                 ["검단", "공산품", "2", "햄스트링기구  R010", "  24 "],        # 다른 창고 → 이어 씀
                                 ["김포1", "공산품", "9", "햄스트링기구 R010", "  40 "],        # 같은 창고 → 그 창고 합산
                                 ["검단", "건기식", "3", "파미젠 NMN 정 60정", "  -  "],       # '-' = 0
                                 ["김포2", "공산품", "", "코스프레 w205", "- 3 "],             # 음수 → 경고
                                 ["김포2", "공산품", "", "재고미상", "확인중"],               # 숫자 아님 → 제외
                                 ["", "공산품", "", "창고미상", "5"]]                        # 창고 없음 → 제외
    stock_cli.grids["건기식_260929"] = [[], [], ["", "", "창고", "상품명", "현재고"],
                                        ["", "", "검단", "웰빙곳간 알부민 120정", "1203"]]
    assert CS.resolve_tab(stock_cli, "https://x/edit?gid=1#gid=1") == "Sheet1"
    assert CS.resolve_tab(stock_cli, "https://x/edit?gid=2") == "건기식_260929"
    assert CS.resolve_tab(stock_cli, "https://x/edit") == "Sheet1"                  # gid 없음 = 첫 탭
    _expect(ValueError, lambda: CS.resolve_tab(stock_cli, "https://x/edit#gid=99"), "없는 gid")
    stock, warns = CS.read_stock(stock_cli.grids["Sheet1"])
    assert stock[CS.name_key("햄스트링기구 R010")] == ("햄스트링기구 R010", {"김포1": 2400, "검단": 24}), stock
    assert CS.stock_text(stock[CS.name_key("햄스트링기구 R010")][1]) == "김포1 , 2,400개 / 검단 , 24개"
    assert CS.stock_text(stock[CS.name_key("파미젠 NMN 정 60정")][1]) == "검단 , 0개"
    assert CS.stock_text(stock[CS.name_key("코스프레 w205")][1]) == "김포2 , -3개" and any("음수" in w for w in warns)
    assert CS.name_key("재고미상") not in stock and CS.name_key("창고미상") not in stock
    assert sum("확인 필요 — 제외" in w for w in warns) == 2, warns
    assert CS.stock_text({"김포2": 150}) == "김포2 , 150개"                                  # 소유자 예시 표기
    gun = CS.read_stock(stock_cli.grids["건기식_260929"])[0]
    assert CS.stock_text(gun[CS.name_key("웰빙곳간 알부민 120정")][1]) == "검단 , 1,203개"
    # 관리대장: 회사보유재고 열(상품명 오른쪽)·다른 열은 절대 불변
    hdr = ["구분", "대표자명", "사업자명", "계정아이디", "비밀번호", "상품명", "회사보유재고", "그로스 재고 (자동갱신 09.29)"]
    led = FakeClient()
    led.grids["셀독리스트"] = [["예시"], hdr,
                               ["", "홍길동", "(주)예시", "ex01", "pw!1", "햄스트링기구R010", "", "11"],   # 공백 무시
                               ["", "", "", "", "", "파미젠 nmn 정 60정\n(노출명 전체)", "5", "12"],       # 대소문자·첫 줄
                               ["", "", "", "", "", "없는상품", "7", "13"],                              # 미매칭 → 7 유지
                               ["", "", "", "", "", "--", "9", ""],                                     # 상품명 아님
                               ["", "김예시", "예시마켓", "sm22", "0012", "햄스트링기구 R010", "", "14"]]  # 다른 계정 같은 값
    before = copy.deepcopy(led.grids["셀독리스트"])
    res = CS.run_company_stock("https://x/edit?gid=1", "L", dry_run=True, stock_client=stock_cli, ledger_client=led)
    assert (res.matched, res.changed, res.stock_sheet) == (3, 3, "Sheet1") and not led.writes     # 미리보기 = 쓰기 0
    assert res.unmatched == [("(주)예시", "없는상품")], res.unmatched
    res = CS.run_company_stock("https://x/edit?gid=1", "L", stock_client=stock_cli, ledger_client=led)
    assert led.writes == [("셀독리스트", "G3", False)], led.writes                                # 그 열 데이터 구간 1회
    g = led.grids["셀독리스트"]
    ham = "김포1 , 2,400개 / 검단 , 24개"
    assert [r[6] for r in g[2:]] == [ham, "검단 , 0개", "7", "9", ham], [r[6] for r in g[2:]]
    for new, old in zip(g, before):
        assert new[:6] + new[7:] == old[:6] + old[7:], (new, old)                                # 다른 열 불변
    assert CS.run_company_stock("https://x/edit?gid=1", "L", stock_client=stock_cli,
                                ledger_client=led).changed == 0 and len(led.writes) == 1          # 같은 값 = 쓰기 없음
    bad = FakeClient()
    bad.grids["셀독리스트"] = [hdr[:6]]
    _expect(ValueError, lambda: CS.write_company_stock(bad, stock), "회사보유재고 열 없음")
    ok("탭 선택·창고별 표기(같은 창고 합산)·'-'=0·음수/비숫자 경고·공백/대소문자/첫 줄 매칭·계정 공통값·미매칭 보존·그 열만·미리보기 0")


def t22_name_rules():
    print("[R22] 이름 규칙 — 띄어쓰기·대소문자만 변경=자동 이름변경 · 색상 분리=옛 줄 중단+색상 신규 · 진짜 변경=보류 유지")
    g = ("100", "80", "3", "", "", "")
    reg = R.Registry()
    base_acc = [A("fe1", "대표", "비엔케이", "pw", products=[P("와이어 빨래줄 R20", g), P("신형타프 R008"),
                                                             P("보냉백 BG001")])]
    R.sync(reg, snap_of(base_acc), now=day(1))
    acc = [A("fe1", "대표", "비엔케이", "pw", products=[P("와이어빨래줄 r20", ("100", "90", "3", "", "", "")),
                                                        P("신형타프 R008 (블랙)"), P("신형타프 R008 (베이지)"),
                                                        P("보냉백 BG002")])]
    res = R.sync(reg, snap_of(acc), now=day(2))
    ks = kinds(res.events)
    # 1) 띄어쓰기·대소문자만 → 즉시 이름 변경(확인완료·자동반영), 보류 없음·이력 이어짐·같은 실행 그로스 수정도 새 이름에
    auto = [e for e in res.events if e.kind == M.K_CONFIRMED]
    assert [(e.old, e.new, e.confirm) for e in auto] == [("와이어 빨래줄 R20", "와이어빨래줄 r20", M.C_AUTO)], auto
    assert ("fe1", "와이어빨래줄 r20") in reg.rows and ("fe1", "와이어 빨래줄 R20") not in reg.rows
    assert reg.rows[("fe1", "와이어빨래줄 r20")].registered == "2026-10-01"                       # 이력 이어짐
    assert (M.SHEET_GROWTH, M.K_EDIT, "fe1", "와이어빨래줄 r20", "그로스 작업수량") in ks
    assert status(reg, "fe1", "와이어빨래줄 r20") == (M.ST_ACTIVE, "")
    # 2) 색상 분리 → 옛 줄 관리중단 + 색상 줄 신규(이름변경 보류 아님)
    assert (M.SHEET_PROD, M.K_STOP, "fe1", "신형타프 R008", "관리상태") in ks
    assert (M.SHEET_PROD, M.K_NEW_PROD, "fe1", "신형타프 R008 (블랙)", "") in ks
    assert (M.SHEET_PROD, M.K_NEW_PROD, "fe1", "신형타프 R008 (베이지)", "") in ks
    # 3) 진짜 이름 변경(코드 변경)은 여전히 확인필요 보류
    held = [e for e in res.events if e.kind == M.K_RENAME_PROD]
    assert [(e.old, e.new, e.confirm) for e in held] == [("보냉백 BG001", "보냉백 BG002", M.C_PENDING)], held
    assert not any(e.kind == M.K_RENAME_PROD and "신형타프" in e.new for e in res.events)
    il = R.to_input_list(reg)
    assert sorted(p.name for p in il.accounts[0].products) == [
        "보냉백 BG001", "신형타프 R008 (베이지)", "신형타프 R008 (블랙)", "와이어빨래줄 r20"]      # 대장과 일치(보류 1건 제외)
    R.check_integrity(reg)
    old = R.as_of(reg, "2026-10-01")
    assert ("fe1", "와이어 빨래줄 R20") in old and ("fe1", "와이어빨래줄 r20") not in old          # 과거 복원 = 옛 이름
    assert old[("fe1", "와이어 빨래줄 R20")]["그로스 작업수량"] == "80"
    assert R.sync(reg, snap_of(acc), now=day(3)).events == []                                     # 재실행 잡음 없음
    # 1:1 이 아니면(같은 키 새 이름 2개) 자동 판단 안 함 → 일반 규칙
    reg2 = R.Registry()
    R.sync(reg2, snap_of([A("x1", "대", "상사", "pw", products=[P("캠핑 의자")])]), now=day(1))
    r2 = R.sync(reg2, snap_of([A("x1", "대", "상사", "pw", products=[P("캠핑의자"), P("캠핑의 자")])]), now=day(2))
    assert not any(e.kind == M.K_CONFIRMED for e in r2.events), kinds(r2.events)
    ok("자동 이름변경(자동반영·이력/그로스 이어짐·과거 복원)·색상 분리=중단+신규·진짜 변경 보류·1:1 아닐 때 제외")


def t23_company_stock_skip_logged():
    print("[R23] 회사재고 미설정·SA 미등록 = 조용히 넘기지 않고 '생략' 안내 로그(오류 아님·쓰기 없음)")
    from coupang_analytics import company_stock as CS
    from coupang_analytics import gsheet_api
    from coupang_analytics import pipeline_gsheet as PG
    calls: list = []
    orig_run, orig_sa, orig_apply = CS.run_company_stock, gsheet_api.load_sa_info, CS.apply_to_workbook
    CS.run_company_stock = lambda *a, **k: calls.append("run")
    CS.apply_to_workbook = lambda *a, **k: calls.append("apply") or 0
    try:
        for stock, inp, want in (("", "L", "재고현황 링크(stock/url) 미설정"), ("S", "", "관리대장 링크(gsheet/input_url) 미설정"),
                                 (None, None, "재고현황 링크(stock/url)·관리대장 링크(gsheet/input_url) 미설정")):
            logs: list = []
            PG.push_company_stock(stock, inp, logs.append)
            assert len(logs) == 1 and want in logs[0] and "생략" in logs[0], logs
        logs = []
        PG.inject_company_stock(object(), "", logs.append)
        assert len(logs) == 1 and "stock/url" in logs[0] and "생략" in logs[0], logs
        gsheet_api.load_sa_info = lambda *a, **k: None                      # SA 키 미등록
        logs = []
        PG.push_company_stock("S", "L", logs.append)
        PG.inject_company_stock(object(), "S", logs.append)
        assert len(logs) == 2 and all("서비스계정 키 미등록" in m and "생략" in m for m in logs), logs
        assert calls == [], calls                                               # 생략 경로 = 반영·주입 호출 없음
        assert not any("실패" in m or "⚠" in m for m in logs)                  # 오류가 아니라 안내
    finally:
        CS.run_company_stock, gsheet_api.load_sa_info, CS.apply_to_workbook = orig_run, orig_sa, orig_apply
    ok("링크 미설정 3경우·계정목록 주입 미설정·SA 미등록 각 1줄 안내·반영 호출 없음·오류 표기 아님")


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
    t17_write_coupang_check()
    t18_previous_password()
    t19_to_input_list()
    t20_write_lock()
    t21_company_stock()
    t22_name_rules()
    t23_company_stock_skip_logged()
    print("셀독등록원장 오프라인 검증 통과")


if __name__ == "__main__":
    main()
