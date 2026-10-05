"""문의/CS 원장 오프라인 검증 — 설계(DOMAIN_D10_CS §3·§9·IO 05-1) 기대 동작을 가짜 시트로 확인.

로그인·실 API 없음(결정적). 접수→진행→보류→재개→완료 상태 replay·번호/참조 무결성·개인정보 가림·열람 로그·
통계 집계·검증·미리보기·잠금.

    python tools/verify_cs_offline.py
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

from coupang_analytics import cs_gsheet as G  # noqa: E402
from coupang_analytics import cs_model as M  # noqa: E402
from coupang_analytics import cs_store as S  # noqa: E402

LOCK = str(Path(tempfile.mkdtemp(prefix="cslock_")) / "_문의.lock")


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


def dt(d, h=10):
    return datetime(2026, 10, d, h, 0, 0)


def open_q(cli, **kw):
    base = dict(marketplace="쿠팡", account_id="example01", type=M.TYPE_PRODUCT,
                content="재고 있나요?", lock_path=LOCK)
    base.update(kw)
    return G.open_inquiry(cli, **base)


# ── 시나리오 ──────────────────────────────────────────────────────
def t1_open():
    print("[CS1] 접수 — 시트 3개·Q-0001·상태 접수·연속 ID")
    cli = FakeClient()
    q = open_q(cli, asker_name="김고객", contact="010-5555-6666", now=dt(1))
    assert q.id == "Q-0001"
    assert set(cli.grids) >= set(M.ALL_SHEETS)
    assert cli.grids[M.SHEET_INQUIRY][0] == list(M.HEADER_INQUIRY)
    clog = G.load_log(cli)
    assert S.status_of(clog, "Q-0001") == M.ST_RECEIVED
    q2 = open_q(cli, now=dt(1))
    assert q2.id == "Q-0002"
    ok("시트 3개·Q-0001/Q-0002·접수 상태")
    return cli


def t2_status_replay():
    print("[CS2] 상태 replay — 진행→보류→재개→(응대)→완료→재개방")
    cli = FakeClient()
    open_q(cli, now=dt(1))
    G.add_event(cli, inquiry_id="Q-0001", kind=M.EV_PROGRESS, author="CS담당", now=dt(2), lock_path=LOCK)
    assert S.status_of(G.load_log(cli), "Q-0001") == M.ST_PROGRESS
    G.add_event(cli, inquiry_id="Q-0001", kind=M.EV_HOLD, author="CS담당", note="고객 회신 대기", now=dt(3), lock_path=LOCK)
    assert S.status_of(G.load_log(cli), "Q-0001") == M.ST_HOLD
    G.add_event(cli, inquiry_id="Q-0001", kind=M.EV_RESUME, author="CS담당", now=dt(4), lock_path=LOCK)
    assert S.status_of(G.load_log(cli), "Q-0001") == M.ST_PROGRESS
    G.add_event(cli, inquiry_id="Q-0001", kind=M.EV_REPLY, author="CS담당", note="답변 전송함", now=dt(5), lock_path=LOCK)
    assert S.status_of(G.load_log(cli), "Q-0001") == M.ST_PROGRESS            # 응대는 상태 불변
    G.add_event(cli, inquiry_id="Q-0001", kind=M.EV_DONE, author="CS담당", now=dt(6), lock_path=LOCK)
    assert S.status_of(G.load_log(cli), "Q-0001") == M.ST_DONE
    G.add_event(cli, inquiry_id="Q-0001", kind=M.EV_REOPEN, author="CS담당", note="재문의", now=dt(7), lock_path=LOCK)
    assert S.status_of(G.load_log(cli), "Q-0001") == M.ST_PROGRESS
    S.check_integrity(G.load_log(cli))
    ok("진행/보류/재개/응대(불변)/완료/재개방 상태·무결성")


def t3_open_inquiries():
    print("[CS3] 미완료 조망 — 완료 제외·계정 필터")
    cli = FakeClient()
    open_q(cli, account_id="acc1", now=dt(1))                                 # Q-0001 접수
    open_q(cli, account_id="acc2", now=dt(1))                                 # Q-0002 접수
    G.add_event(cli, inquiry_id="Q-0001", kind=M.EV_DONE, author="x", now=dt(2), lock_path=LOCK)
    clog = G.load_log(cli)
    assert [q.id for q in S.open_inquiries(clog)] == ["Q-0002"]
    assert S.open_inquiries(clog, account_id="acc1") == []
    assert [q.id for q in S.open_inquiries(clog, account_id="acc2")] == ["Q-0002"]
    ok("완료 제외·계정별 필터")


def t4_masking():
    print("[CS4] 가림 — CS담당/대표 원문·그 외 고객이름·연락처 ●●●●·문의ID 공개")
    q = M.Inquiry("Q-0007", "2026-10-01 10:00:00", "쿠팡", "acc1", "", M.TYPE_PRODUCT,
                  "김고객", "010-5555-6666", "문의내용")
    raw = M.mask_inquiry(q, role="CS담당")
    masked = M.mask_inquiry(q, role="창고")
    assert raw["고객이름"] == "김고객" and raw["연락처"] == "010-5555-6666"
    assert masked["고객이름"] == M.MASK and masked["연락처"] == M.MASK
    assert masked["문의ID"] == "Q-0007" and masked["문의내용"] == "문의내용"      # 비민감 공개
    assert M.mask_inquiry(q, role="대표")["연락처"] == "010-5555-6666"
    empty = M.mask_inquiry(M.Inquiry("Q-1", "", "쿠팡", "a", "", M.TYPE_ETC, "", "", "c"), role="창고")
    assert empty["고객이름"] == "" and empty["연락처"] == ""                      # 빈값은 가림 안 함
    ok("CS담당/대표 원문·그 외 2칸 가림·비민감 공개·빈값 그대로")


def t5_validation():
    print("[CS5] 검증 — 접수 필수·유형·이벤트 kind·보류 사유·명부 없음·실패 쓰기 0")
    cli = FakeClient()
    n = len(cli.writes)
    _expect(M.CSError, lambda: open_q(cli, marketplace="", now=dt(1)), "판매처 없음")
    _expect(M.CSError, lambda: open_q(cli, content="", now=dt(1)), "내용 없음")
    _expect(M.CSError, lambda: open_q(cli, type="환불", now=dt(1)), "유형 허용값")
    _expect(M.CSError, lambda: G.add_event(cli, inquiry_id="Q-0001", kind="종료", author="x",
            now=dt(2), lock_path=LOCK), "이벤트 kind")
    assert cli.grids == {} and len(cli.writes) == n
    open_q(cli, now=dt(1))                                                    # Q-0001 생성
    _expect(M.CSError, lambda: G.add_event(cli, inquiry_id="Q-0001", kind=M.EV_HOLD, author="x",
            now=dt(2), lock_path=LOCK), "보류 사유 없음")
    _expect(M.CSError, lambda: G.add_event(cli, inquiry_id="Q-9999", kind=M.EV_PROGRESS, author="x",
            now=dt(2), lock_path=LOCK), "명부에 없음")
    ok("접수 3·이벤트 kind·보류 사유·명부 없음 검출·실패 쓰기 0")


def t6_integrity():
    print("[CS6] 번호 누락·고아 문의ID = 무결성 오류·다음 쓰기 0")
    cli = FakeClient()
    open_q(cli, now=dt(1))
    G.add_event(cli, inquiry_id="Q-0001", kind=M.EV_PROGRESS, author="x", now=dt(2), lock_path=LOCK)
    G.add_event(cli, inquiry_id="Q-0001", kind=M.EV_REPLY, author="x", note="답", now=dt(3), lock_path=LOCK)
    del cli.grids[M.SHEET_EVENT][2]                                           # 최신이 위 → 바닥(#1) 삭제 = 번호 갭
    n = len(cli.writes)
    _expect(M.CSError, lambda: G.add_event(cli, inquiry_id="Q-0001", kind=M.EV_DONE, author="x",
            now=dt(4), lock_path=LOCK), "번호 불연속")
    assert len(cli.writes) == n
    # 고아 이벤트(명부에 없는 문의ID)
    cli2 = FakeClient()
    open_q(cli2, now=dt(1))
    G.add_event(cli2, inquiry_id="Q-0001", kind=M.EV_PROGRESS, author="x", now=dt(2), lock_path=LOCK)
    cli2.grids[M.SHEET_EVENT][1][1] = "Q-0099"                                 # 문의ID를 명부에 없는 값으로 손상
    _expect(M.CSError, lambda: S.check_integrity(G.load_log(cli2)), "고아 문의ID")
    ok("번호 불연속·고아 문의ID 검출·쓰기 0")


def t7_stats():
    print("[CS7] 통계 — 접수/완료/보류·평균 처리일·보류율·계정별")
    cli = FakeClient()
    open_q(cli, account_id="acc1", now=dt(1))                                 # Q-0001
    G.add_event(cli, inquiry_id="Q-0001", kind=M.EV_DONE, author="x", now=dt(4), lock_path=LOCK)   # 3일
    open_q(cli, account_id="acc2", now=dt(2))                                 # Q-0002 보류
    G.add_event(cli, inquiry_id="Q-0002", kind=M.EV_HOLD, author="x", note="대기", now=dt(3), lock_path=LOCK)
    open_q(cli, account_id="acc1", now=dt(10))                                # Q-0003 범위 밖
    st = S.stats(G.load_log(cli), "2026-10-01", "2026-10-05")
    assert st["접수"] == 2 and st["완료"] == 1 and st["보류"] == 1, st
    assert st["평균처리일"] == 3.0 and st["보류율"] == 0.5, st
    assert st["계정별"] == {"acc1": 1, "acc2": 1}, st["계정별"]
    ok("접수2·완료1·보류1·평균 3.0일·보류율 0.5·계정별")


def t8_access_log():
    print("[CS8] 열람 로그 — append·원문 값 없음(항목명만)")
    cli = t1_open()
    logs: list = []
    G.record_access(cli, actor="대표", inquiry_id="Q-0001", items="고객이름·연락처",
                    now=dt(2, 14), on_log=logs.append, lock_path=LOCK)
    acc = cli.grids[M.SHEET_ACCESS]
    assert acc[1][2] == "대표" and acc[1][3] == "Q-0001" and acc[1][4] == "고객이름·연락처"
    assert not any("010-" in m or "김고객" in m for m in logs)
    ok("열람기록 append·로그에 원문 없음")


def t9_dry_run():
    print("[CS9] 미리보기=쓰기 0·재로드 일치·로그에 고객 원문 없음")
    cli = FakeClient()
    logs: list = []
    q = open_q(cli, asker_name="김고객", contact="010-5555-6666", now=dt(1),
               dry_run=True, on_log=logs.append)
    assert q.id == "Q-0001" and cli.grids == {} and cli.writes == []
    assert not any("010-" in m or "김고객" in m for m in logs)
    open_q(cli, now=dt(1))
    assert len(G.load_log(cli).inquiries) == 1
    ok("미리보기 무변경·실제 1건·로그에 원문 없음")


def t10_lock():
    print("[CS10] 쓰기 잠금 — 겹치면 중단(쓰기 0)")
    from coupang_analytics import registry_lock as RL
    lock = str(Path(tempfile.mkdtemp(prefix="cslock10_")) / "_문의.lock")
    cli = FakeClient()
    open_q(cli, now=dt(1), lock_path=lock)
    orig = RL.LOCK_WAIT_SEC
    RL.LOCK_WAIT_SEC = 0.3
    try:
        with RL.registry_lock(lock):
            n = len(cli.writes)
            _expect(RL.RegistryLockError, lambda: G.add_event(cli, inquiry_id="Q-0001",
                    kind=M.EV_PROGRESS, author="x", now=dt(2), lock_path=lock), "잠금 중 이벤트")
            assert len(cli.writes) == n
    finally:
        RL.LOCK_WAIT_SEC = orig
    ok("잠금 중 쓰기 0")


def main():
    t1_open()
    t2_status_replay()
    t3_open_inquiries()
    t4_masking()
    t5_validation()
    t6_integrity()
    t7_stats()
    t8_access_log()
    t9_dry_run()
    t10_lock()
    print("문의/CS 원장 오프라인 검증 통과")


if __name__ == "__main__":
    main()
