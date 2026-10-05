"""채권자 원장 오프라인 검증 — 설계(DOMAIN_D8_SETTLEMENT_PHASE23 §4.3·SETTLEMENT_MODEL §3.3·IO 12-x) 기대 동작.

로그인·실 API 없음(결정적). 잔액 replay(확정−상환·정정=반대기록)·2단계 가림·열람/응대 로그·검증·무결성·
로그에 원문 없음·로컬 백업 없음·잠금.

    python tools/verify_creditor_offline.py
"""
from __future__ import annotations

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

from coupang_analytics import creditor_store as CR  # noqa: E402

LOCK = str(Path(tempfile.mkdtemp(prefix="crlock_")) / "_채권자.lock")


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


def day(d, h=10):
    return datetime(2026, 10, d, h, 0, 0)


# ── 시나리오 ──────────────────────────────────────────────────────
def t1_register():
    print("[CR1] 채권자 등록 — 시트 4개·번호 C-0001·연속 번호")
    cli = FakeClient()
    logs: list = []
    c1 = CR.record_creditor(cli, name="홍길동", contact="010-1111-2222",
                            account="농협 302-1111-2222-33", on_log=logs.append, lock_path=LOCK)
    assert c1.no == "C-0001"
    assert set(cli.grids) >= set(CR.ALL_SHEETS)
    assert cli.grids[CR.SHEET_MASTER][0] == list(CR.H_MASTER)
    c2 = CR.record_creditor(cli, name="김둘", contact="010-3333-4444",
                            account="국민 123-45-6789", lock_path=LOCK)
    assert c2.no == "C-0002"
    assert not any("홍길동" in m or "302-1111" in m for m in logs)      # 로그에 원문 없음
    ok("시트 4개·C-0001/C-0002·로그에 이름/계좌 원문 없음")
    return cli


def t2_masking():
    print("[CR2] 가림 — 대표=전부·정산담당=계좌만 가림·그 외=이름/연락처/계좌 가림·번호 공개")
    c = CR.Creditor("C-0007", "홍길동", "010-1111-2222", "농협 302-1111")
    rep = CR.mask_master(c, role="대표")
    fin = CR.mask_master(c, role="정산담당")
    other = CR.mask_master(c, role="창고")
    assert rep["이름"] == "홍길동" and rep["연락처"] == "010-1111-2222" and rep["상환계좌"] == "농협 302-1111"
    assert fin["이름"] == "홍길동" and fin["연락처"] == "010-1111-2222" and fin["상환계좌"] == CR.MASK
    assert other["이름"] == CR.MASK and other["연락처"] == CR.MASK and other["상환계좌"] == CR.MASK
    assert rep["번호"] == fin["번호"] == other["번호"] == "C-0007"      # 번호는 공개
    assert CR.mask_master({"번호": "C-1", "이름": "", "연락처": "x", "상환계좌": ""}, role="창고")["이름"] == ""  # 빈값은 가림 안 함
    ok("대표 원문·정산담당 계좌만 가림·그 외 3칸 가림·번호 공개·빈값 그대로")


def t3_balance():
    print("[CR3] 잔액 replay — 채권확정 − 상환 누적·정정=반대기록")
    cli = t1_register()
    CR.record_movement(cli, creditor_id="C-0001", kind=CR.MV_CLAIM, amount="1,000,000",
                       date="2026-10-01", lock_path=LOCK)
    CR.record_movement(cli, creditor_id="C-0001", kind=CR.MV_REPAY, amount=300000,
                       date="2026-10-05", lock_path=LOCK)
    mv = CR.load_movements(cli)
    assert CR.balance(mv, "C-0001") == 700000
    CR.record_movement(cli, creditor_id="C-0001", kind=CR.MV_REPAY, amount=-100000,     # 과다 상환 정정(반대기록)
                       date="2026-10-06", note="10/5 상환 오입력 정정", lock_path=LOCK)
    assert CR.balance(CR.load_movements(cli), "C-0001") == 800000
    ok("확정100만−상환30만=70만·반대기록 정정→80만")
    return cli


def t4_balance_as_of_and_all(cli):
    print("[CR4] 잔액 as_of·전체 잔액")
    CR.record_movement(cli, creditor_id="C-0002", kind=CR.MV_CLAIM, amount=500000,
                       date="2026-10-10", lock_path=LOCK)
    mv = CR.load_movements(cli)
    assert CR.balance(mv, "C-0001", as_of="2026-10-04") == 1000000       # 상환(10/5) 전
    assert CR.balance(mv, "C-0001", as_of="2026-10-05") == 700000
    allb = CR.balances(mv)
    assert allb == {"C-0001": 800000, "C-0002": 500000}, allb
    ok("as_of 상환 전/후·balances 전체")


def t5_validation():
    print("[CR5] 검증 — 채권자 필수·유형·금액·일자·명부 없음·실패 시 쓰기 0")
    cli = t1_register()
    n = len(cli.writes)
    _expect(CR.CreditorError, lambda: CR.record_creditor(cli, name="", contact="x", account="y",
            lock_path=LOCK), "이름 없음")
    _expect(CR.CreditorError, lambda: CR.record_movement(cli, creditor_id="C-0001", kind="증액",
            amount=100, date="2026-10-01", lock_path=LOCK), "유형 허용값")
    _expect(CR.CreditorError, lambda: CR.record_movement(cli, creditor_id="C-0001", kind=CR.MV_CLAIM,
            amount="만원", date="2026-10-01", lock_path=LOCK), "금액 비정수")
    _expect(CR.CreditorError, lambda: CR.record_movement(cli, creditor_id="C-0001", kind=CR.MV_CLAIM,
            amount=100, date="26.10.01", lock_path=LOCK), "일자 형식")
    _expect(CR.CreditorError, lambda: CR.record_movement(cli, creditor_id="C-9999", kind=CR.MV_CLAIM,
            amount=100, date="2026-10-01", lock_path=LOCK), "명부에 없음")
    assert len(cli.writes) == n                                          # 등록된 채권자(2명)만 있고 실패는 쓰기 0
    ok("5경우 CreditorError·실패 쓰기 0")


def t6_integrity():
    print("[CR6] 번호 누락 = 무결성 오류·다음 쓰기 0")
    cli = t3_balance()
    del cli.grids[CR.SHEET_LEDGER][3]                                    # 채권상환 3줄 중 바닥 삭제 → 번호 갭
    n = len(cli.writes)
    _expect(CR.CreditorError, lambda: CR.record_movement(cli, creditor_id="C-0001", kind=CR.MV_CLAIM,
            amount=1, date="2026-10-09", lock_path=LOCK), "번호 불연속")
    assert len(cli.writes) == n
    ok("채권상환 번호 불연속 검출·쓰기 0")


def t7_contact_access_log():
    print("[CR7] 응대·열람 로그 — append·열람기록엔 원문 값 없음(항목명만)")
    cli = t1_register()
    CR.record_contact(cli, creditor_id="C-0001", content="상환 일정 문의 회신", author="정산담당",
                      now=day(11), lock_path=LOCK)
    logs: list = []
    CR.record_access(cli, actor="대표", creditor_id="C-0001", items="이름·상환계좌",
                     now=day(11, 14), on_log=logs.append, lock_path=LOCK)
    con = cli.grids[CR.SHEET_CONTACT]
    acc = cli.grids[CR.SHEET_ACCESS]
    assert con[1][1] == "C-0001" and con[1][4] == "상환 일정 문의 회신"
    assert acc[1][2] == "대표" and acc[1][3] == "C-0001" and acc[1][4] == "이름·상환계좌"
    assert not any("농협" in m for m in logs)                            # 항목명만, 원문 없음
    _expect(CR.CreditorError, lambda: CR.record_contact(cli, creditor_id="C-0001", content="",
            author="x", lock_path=LOCK), "응대 내용 필수")
    ok("응대 append·열람기록 항목명만·내용 필수")


def t8_dry_run_and_no_backup():
    print("[CR8] 미리보기=쓰기 0·로컬 백업 함수 없음(원문 유출 방지·§4.3)")
    cli = FakeClient()
    c = CR.record_creditor(cli, name="홍", contact="010", account="농협 1", dry_run=True, lock_path=LOCK)
    assert c.no == "C-0001" and cli.grids == {} and cli.writes == []
    assert not hasattr(CR, "backup_local")                              # 채권자 원장은 로컬 백업을 만들지 않는다
    ok("미리보기 무변경·backup_local 부재")


def t9_lock():
    print("[CR9] 쓰기 잠금 — 겹치면 중단(쓰기 0)")
    from coupang_analytics import registry_lock as RL
    lock = str(Path(tempfile.mkdtemp(prefix="crlock9_")) / "_채권자.lock")
    cli = FakeClient()
    CR.record_creditor(cli, name="홍", contact="010", account="농협 1", lock_path=lock)
    orig = RL.LOCK_WAIT_SEC
    RL.LOCK_WAIT_SEC = 0.3
    try:
        with RL.registry_lock(lock):
            n = len(cli.writes)
            _expect(RL.RegistryLockError, lambda: CR.record_movement(cli, creditor_id="C-0001",
                    kind=CR.MV_CLAIM, amount=100, date="2026-10-01", lock_path=lock), "잠금 중 기록")
            assert len(cli.writes) == n
    finally:
        RL.LOCK_WAIT_SEC = orig
    ok("잠금 중 쓰기 0")


def main():
    t1_register()
    cli = t3_balance()
    t4_balance_as_of_and_all(cli)
    t2_masking()
    t5_validation()
    t6_integrity()
    t7_contact_access_log()
    t8_dry_run_and_no_backup()
    t9_lock()
    print("채권자 원장 오프라인 검증 통과")


if __name__ == "__main__":
    main()
