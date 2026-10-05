"""계약 원장 오프라인 검증 — 설계(DOMAIN_D8_SETTLEMENT_PHASE23 §4.1·IO 11-3) 기대 동작을 가짜 시트로 확인.

로그인·실 API 없음(결정적). 버전 이력·as_of 복원·유효/만료/해지·만료예정·가림·검증·무결성·잠금.

    python tools/verify_contract_offline.py
"""
from __future__ import annotations

import re
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics import contract_store as C  # noqa: E402

LOCK = str(Path(tempfile.mkdtemp(prefix="ctlock_")) / "_계약.lock")


def ok(msg):
    print(f"  ✔ {msg}")


def _expect(exc, fn, what):
    try:
        fn()
    except exc:
        return
    raise AssertionError(f"{what} — {exc.__name__} 안 남")


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
        for r in self.grids.get(sheet, []):
            r = list(r)
            while r and r[-1] in ("", None):
                r.pop()
            out.append(r)
        while out and not out[-1]:
            out.pop()
        return out

    def write_values(self, sheet, rows, start="A1", raw=False):
        self.writes.append((sheet, start, raw))
        g = self.grids.setdefault(sheet, [])
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


KEY = ("example01", "셀독관리")


def fields(start="2026-01-01", end="2026-12-31", **over):
    f = {"사업자명": "(주)예시", "대표자명": "홍길동", "계약일자": "2025-12-20",
         "계약기간시작": start, "계약기간끝": end, "수익배분": "6:4", "수익기준": "정산대상액",
         "수익계산식": "정산액*0.4", "계약금": "300만", "정산계좌": "농협 123-456-789012",
         "수탁자": "비밀수탁(주)", "수탁자대표자": "김수탁", "수탁자사업자번호": "111-22-33333"}
    f.update(over)
    return f


def rows(cli):
    g = cli.grids[C.SHEET]
    hx = {h: i for i, h in enumerate(g[0])}
    return [{h: (r[i] if i < len(r) else "") for h, i in hx.items()} for r in g[1:]]


# ── 시나리오 ──────────────────────────────────────────────────────
def t1_init():
    print("[C1] 최초 계약 — 시트/헤더·#1·as_of 내용·상태 유효")
    cli = FakeClient()
    v = C.record(cli, account_id=KEY[0], business=KEY[1], fields=fields(), eff="2026-01-01", lock_path=LOCK)
    assert v.no == 1 and v.kind == C.KIND_INIT
    assert cli.grids[C.SHEET][0] == list(C.HEADER)
    led = C.load(cli)
    snap = C.as_of(led, KEY, "2026-03-01")
    assert snap and snap["수익배분"] == "6:4" and snap["상태"] == C.ST_VALID
    assert C.as_of(led, KEY, "2025-12-31") is None                 # 효력 전
    ok("최초 #1·as_of 내용·유효·효력 전 None")
    return cli


def t2_amend(cli):
    print("[C2] 개정 — 효력일 기준 그 시점 유효 버전")
    C.record(cli, account_id=KEY[0], business=KEY[1], fields=fields(**{"수익배분": "7:3"}),
             eff="2026-06-01", lock_path=LOCK)
    led = C.load(cli)
    assert C.as_of(led, KEY, "2026-05-31")["수익배분"] == "6:4"      # 개정 전
    assert C.as_of(led, KEY, "2026-07-01")["수익배분"] == "7:3"      # 개정 후
    assert [v.kind for v in led.versions if v.key == KEY].count(C.KIND_AMEND) == 1
    C.check_integrity(led)
    ok("개정 전/후 내용·개정 버전 1·번호 연속")
    return cli


def t3_terminate(cli):
    print("[C3] 해지 — 상태 해지(내용은 마지막 버전 유지)")
    C.record(cli, account_id=KEY[0], business=KEY[1], eff="2026-08-01", terminate=True, lock_path=LOCK)
    led = C.load(cli)
    assert C.status(led, KEY, "2026-07-31") == C.ST_VALID
    assert C.status(led, KEY, "2026-09-01") == C.ST_TERMINATED
    assert C.as_of(led, KEY, "2026-09-01")["수익배분"] == "7:3"      # 내용은 유지, 상태만 해지
    ok("해지 전 유효·해지 후 해지·내용 유지")


def t4_expired_and_expiring():
    print("[C4] 만료(기간 끝 지남)·만료 예정(30일 전·경계)")
    cli = FakeClient()
    C.record(cli, account_id="acc2", business="위탁", fields=fields(end="2026-12-31"),
             eff="2026-01-01", lock_path=LOCK)
    led = C.load(cli)
    k = ("acc2", "위탁")
    assert C.status(led, k, "2027-01-05") == C.ST_EXPIRED
    assert C.expiring_soon(led, k, today=date(2026, 12, 10)) is True        # 끝까지 21일
    assert C.expiring_soon(led, k, today=date(2026, 12, 1)) is True         # 30일(경계)
    assert C.expiring_soon(led, k, today=date(2026, 11, 30)) is False       # 31일(아직)
    assert C.expiring_soon(led, k, today=date(2027, 1, 5)) is False         # 이미 만료
    ok("만료·만료예정 21일/30일 경계·31일 전 제외·만료 후 제외")


def t5_masking():
    print("[C5] 가림 — 대표/정산담당만 민감 칸 원문, 그 외 ●●●●")
    cli = FakeClient()
    C.record(cli, account_id="acc3", business="위탁", fields=fields(), eff="2026-01-01", lock_path=LOCK)
    snap = C.as_of(C.load(cli), ("acc3", "위탁"), "2026-06-01")
    raw = C.view(snap, role="대표")
    masked = C.view(snap, role="창고")
    assert raw["정산계좌"] == "농협 123-456-789012" and raw["수탁자사업자번호"] == "111-22-33333"
    assert masked["정산계좌"] == C.MASK and masked["수탁자"] == C.MASK and masked["수탁자사업자번호"] == C.MASK
    assert masked["수익배분"] == "6:4"                                       # 비민감은 그대로
    assert C.view(snap, role="정산담당")["정산계좌"] == "농협 123-456-789012"
    ok("대표/정산담당 원문·그 외 민감 4칸 가림·비민감 유지")


def t6_validation():
    print("[C6] 검증 — 필수 칸·기간 끝>시작·효력일 형식·해지 키 필요·실패 시 쓰기 0")
    cli = FakeClient()
    n = len(cli.writes)
    _expect(C.ContractError, lambda: C.record(cli, account_id="", business="b", fields=fields(),
            eff="2026-01-01", lock_path=LOCK), "위탁계정 없음")
    _expect(C.ContractError, lambda: C.record(cli, account_id="a", business="", fields=fields(),
            eff="2026-01-01", lock_path=LOCK), "사업 없음")
    _expect(C.ContractError, lambda: C.record(cli, account_id="a", business="b",
            fields=fields(**{"수익계산식": ""}), eff="2026-01-01", lock_path=LOCK), "필수 칸 빈값")
    _expect(C.ContractError, lambda: C.record(cli, account_id="a", business="b",
            fields=fields(start="2026-12-31", end="2026-01-01"), eff="2026-01-01", lock_path=LOCK), "기간 역전")
    _expect(C.ContractError, lambda: C.record(cli, account_id="a", business="b", fields=fields(),
            eff="26.01.01", lock_path=LOCK), "효력일 형식")
    _expect(C.ContractError, lambda: C.record(cli, account_id="", business="b", eff="2026-01-01",
            terminate=True, lock_path=LOCK), "해지 키 없음")
    assert cli.grids == {} and len(cli.writes) == n
    ok("6경우 ContractError·시트 미생성·쓰기 0")


def t7_integrity_blocks():
    print("[C7] 번호 누락 = 무결성 오류·다음 record 쓰기 0")
    cli = FakeClient()
    C.record(cli, account_id="a", business="b", fields=fields(), eff="2026-01-01", lock_path=LOCK)
    C.record(cli, account_id="a", business="b", fields=fields(**{"수익배분": "5:5"}),
             eff="2026-02-01", lock_path=LOCK)
    del cli.grids[C.SHEET][2]                                        # 최신이 위 → 바닥(#1) 삭제 = {2}
    n = len(cli.writes)
    _expect(C.ContractError, lambda: C.record(cli, account_id="a", business="b", fields=fields(),
            eff="2026-03-01", lock_path=LOCK), "번호 불연속")
    assert len(cli.writes) == n
    ok("번호 불연속 검출·쓰기 0")


def t8_dry_run_reload():
    print("[C8] 미리보기=쓰기 0·재로드 일치")
    cli = FakeClient()
    v = C.record(cli, account_id="a", business="b", fields=fields(), eff="2026-01-01",
                 dry_run=True, lock_path=LOCK)
    assert v.no == 1 and cli.grids == {} and cli.writes == []
    C.record(cli, account_id="a", business="b", fields=fields(), eff="2026-01-01", lock_path=LOCK)
    led = C.load(cli)
    assert led.keys() == [("a", "b")] and led.next_no() == 2
    ok("미리보기 무변경·실제 1줄·재로드·keys/next_no")


def t9_lock():
    print("[C9] 쓰기 잠금 — 겹치면 중단(쓰기 0)·미리보기 통과")
    from coupang_analytics import registry_lock as RL
    lock = str(Path(tempfile.mkdtemp(prefix="ctlock9_")) / "_계약.lock")
    cli = FakeClient()
    C.record(cli, account_id="a", business="b", fields=fields(), eff="2026-01-01", lock_path=lock)
    orig = RL.LOCK_WAIT_SEC
    RL.LOCK_WAIT_SEC = 0.3
    try:
        with RL.registry_lock(lock):
            n = len(cli.writes)
            _expect(RL.RegistryLockError, lambda: C.record(cli, account_id="a", business="b",
                    fields=fields(**{"수익배분": "5:5"}), eff="2026-02-01", lock_path=lock), "잠금 중 record")
            assert len(cli.writes) == n
            C.record(cli, account_id="a", business="b", fields=fields(), eff="2026-02-01",
                     dry_run=True, lock_path=lock)
    finally:
        RL.LOCK_WAIT_SEC = orig
    ok("잠금 중 쓰기 0·미리보기 통과")


def main():
    cli = t1_init()
    t2_amend(cli)
    t3_terminate(cli)
    t4_expired_and_expiring()
    t5_masking()
    t6_validation()
    t7_integrity_blocks()
    t8_dry_run_reload()
    t9_lock()
    print("계약 원장 오프라인 검증 통과")


if __name__ == "__main__":
    main()
