"""업무일지 원장 오프라인 검증 — 설계(DOMAIN_D8_SETTLEMENT_PHASE23 §4.2·IO 11-4) 기대 동작을 가짜 시트로 확인.

로그인·실 API 없음(결정적). 실패 시 AssertionError/예외 → exit 1. run_checks 게이트 편입.

    python tools/verify_worklog_offline.py
"""
from __future__ import annotations

import re
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics import worklog_store as W  # noqa: E402

# 원장 잠금 격리 — 실제 output/ 를 건드리지 않게 임시 폴더.
LOCK = str(Path(tempfile.mkdtemp(prefix="wllock_")) / "_업무일지.lock")


def ok(msg):
    print(f"  ✔ {msg}")


def _expect(exc, fn, what):
    try:
        fn()
    except exc:
        return
    raise AssertionError(f"{what} — {exc.__name__} 안 남")


class FakeClient:
    """GSheetClient 흉내 — read/write/ensure/batch(insertDimension ROWS). write 는 A2 삽입을 반영."""

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


def rows(cli):
    g = cli.grids[W.SHEET]
    hx = {h: i for i, h in enumerate(g[0])}
    return [{h: (r[i] if i < len(r) else "") for h, i in hx.items()} for r in g[1:]]


# ── 시나리오 ──────────────────────────────────────────────────────
def t1_append_empty():
    print("[W1] 빈 시트에 첫 줄 — 시트 생성·헤더·번호 1·일자/작성자 자동·상품 빈값=계정 전체")
    cli = FakeClient()
    e = W.append(cli, account_id="example01", content="상세페이지 교체 요청", status=W.WL_ACTIVE,
                 author="담당자A", now=day(10), lock_path=LOCK)
    assert e.no == 1 and e.date == "2026-10-10" and e.author == "담당자A"
    assert e.product == "" and e.account_id == "example01"
    assert cli.grids[W.SHEET][0] == list(W.HEADER)
    r = rows(cli)
    assert len(r) == 1 and r[0]["번호"] == "1" and r[0]["상태"] == W.WL_ACTIVE
    assert r[0]["위탁계정"] == "example01" and r[0]["내용"] == "상세페이지 교체 요청"
    ok("시트/헤더 생성·#1·자동 일자·작성자·상품 공란 보존")
    return cli


def t2_append_order(cli):
    print("[W2] 여러 줄 — 번호 연속·최신이 위")
    W.append(cli, account_id="example01", content="가격 조정", status=W.WL_DONE,
             author="담당자B", product="예시 비타민C", now=day(11), lock_path=LOCK)
    W.append(cli, account_id="sample22", content="재고 보충 협의", status=W.WL_HOLD,
             author="담당자A", now=day(12), lock_path=LOCK)
    r = rows(cli)
    assert [x["번호"] for x in r] == ["3", "2", "1"], r          # 최신이 위
    assert r[0]["위탁계정"] == "sample22" and r[0]["상태"] == W.WL_HOLD
    assert r[1]["상품"] == "예시 비타민C"
    W.check_integrity(W.load(cli))
    ok("번호 1..3 연속·최신 위·상품/상태 보존")


def t3_validation():
    print("[W3] 검증 — 위탁계정/내용 필수·상태 허용값·실패 시 쓰기 0")
    cli = FakeClient()
    n = len(cli.writes)
    _expect(W.WorklogError, lambda: W.append(cli, account_id="", content="x", status=W.WL_ACTIVE,
                                             author="A", lock_path=LOCK), "위탁계정 없음")
    _expect(W.WorklogError, lambda: W.append(cli, account_id="a", content="", status=W.WL_ACTIVE,
                                             author="A", lock_path=LOCK), "내용 없음")
    _expect(W.WorklogError, lambda: W.append(cli, account_id="a", content="x", status="진행중",
                                             author="A", lock_path=LOCK), "상태 허용값 아님")
    assert cli.grids == {} and len(cli.writes) == n
    ok("3경우 WorklogError·시트 미생성·쓰기 0")


def t4_overdue():
    print("[W4] 7일 넘은 진행 = 지연 표시(렌더 계산·완료/보류·비ISO 제외)")
    today = date(2026, 10, 20)

    def mk(st, d):
        return W.WorklogEntry(1, d, "A", "acc", "", "c", "", st)
    assert W.is_overdue(mk(W.WL_ACTIVE, "2026-10-12"), today=today) is True        # 8일 전
    assert W.is_overdue(mk(W.WL_ACTIVE, "2026-10-13"), today=today) is False       # 7일 전(경계)
    assert W.is_overdue(mk(W.WL_DONE, "2026-09-01"), today=today) is False         # 완료는 제외
    assert W.is_overdue(mk(W.WL_HOLD, "2026-09-01"), today=today) is False         # 보류도 제외
    assert W.is_overdue(mk(W.WL_ACTIVE, ""), today=today) is False                 # 일자 없음
    assert W.is_overdue(mk(W.WL_ACTIVE, "26.10.12"), today=today) is False         # 비ISO = 계산 안 함
    wl = W.Worklog([mk(W.WL_ACTIVE, "2026-10-01"), mk(W.WL_DONE, "2026-10-01"), mk(W.WL_ACTIVE, "2026-10-19")])
    assert [e.date for e in W.overdue(wl, today=today)] == ["2026-10-01"]
    ok("8일전 지연·7일 경계·완료/보류/빈값/비ISO 제외·overdue 목록")


def t5_integrity_blocks_write():
    print("[W5] 번호 누락/중복 = 무결성 오류·다음 append 쓰기 0")
    cli = t1_append_empty()
    W.append(cli, account_id="acc", content="c2", status=W.WL_ACTIVE, author="A", now=day(11), lock_path=LOCK)
    del cli.grids[W.SHEET][2]                                    # 최신이 위 → 바닥(#1) 삭제 = 번호 {2}, 1..n 깨짐
    n = len(cli.writes)
    _expect(W.WorklogError, lambda: W.append(cli, account_id="acc", content="c3", status=W.WL_ACTIVE,
                                             author="A", now=day(12), lock_path=LOCK), "번호 불연속")
    assert len(cli.writes) == n
    ok("번호 불연속 검출·쓰기 0")


def t6_dry_run_and_reload():
    print("[W6] 미리보기=쓰기 0·재로드 일치")
    cli = FakeClient()
    e = W.append(cli, account_id="acc", content="미리보기", status=W.WL_ACTIVE, author="A",
                 now=day(10), dry_run=True, lock_path=LOCK)
    assert e.no == 1 and cli.grids == {} and cli.writes == []
    W.append(cli, account_id="acc", content="실제", status=W.WL_ACTIVE, author="A", now=day(10), lock_path=LOCK)
    wl = W.load(cli)
    assert len(wl.entries) == 1 and wl.entries[0].content == "실제" and wl.next_no() == 2
    ok("미리보기 무변경·실제 1줄·재로드·next_no")


def t7_lock():
    print("[W7] 쓰기 잠금 — 겹치면 중단(쓰기 0)·미리보기 통과")
    from coupang_analytics import registry_lock as RL
    lock = str(Path(tempfile.mkdtemp(prefix="wllock7_")) / "_업무일지.lock")
    cli = FakeClient()
    W.append(cli, account_id="acc", content="c1", status=W.WL_ACTIVE, author="A", now=day(10), lock_path=lock)
    orig = RL.LOCK_WAIT_SEC
    RL.LOCK_WAIT_SEC = 0.3
    try:
        with RL.registry_lock(lock):
            n = len(cli.writes)
            _expect(RL.RegistryLockError, lambda: W.append(cli, account_id="acc", content="c2",
                    status=W.WL_ACTIVE, author="A", now=day(11), lock_path=lock), "잠금 중 append")
            assert len(cli.writes) == n
            W.append(cli, account_id="acc", content="미리보기", status=W.WL_ACTIVE, author="A",
                     now=day(11), dry_run=True, lock_path=lock)                # 미리보기는 잠금 무관
    finally:
        RL.LOCK_WAIT_SEC = orig
    ok("잠금 중 쓰기 0·미리보기 통과")


def main():
    t1_append_empty()
    cli = t1_append_empty()
    t2_append_order(cli)
    t3_validation()
    t4_overdue()
    t5_integrity_blocks_write()
    t6_dry_run_and_reload()
    t7_lock()
    print("업무일지 원장 오프라인 검증 통과")


if __name__ == "__main__":
    main()
