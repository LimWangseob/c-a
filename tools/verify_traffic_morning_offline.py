"""노출·방문자 아침 보충 오프라인 검증(D-374) — 로그인·쿠팡·구글 호출 없음(계정 조회·구글 반영은 가짜).

기대값은 결정 문구(D-374 · 통제 세션 지시서)에서 뽑았다(코드에서 뽑지 않음):
- 08:00 에 어제(실행일 − 1) 칸의 노출·방문자 두 줄만 아침 값으로 덮어씀 · 판매·순위·재고·다른 날짜 칸은 그대로 (M1)
- 정산이 그 계정 잠금·Chrome 을 쓰는 중이면 그동안 들어가지 않음(맨 뒤로 미룸 → 끝난 뒤) · 파이프라인 잠금 중이면 시작 안 함 (M2)
- 계정마다 최대 3번 · 끝내 실패 = 00:10 값 그대로 + '노출·방문자 아침 보충 실패' 줄 · 비밀번호 거부 = 다시 안 함 (M3)
- 하루 한 번(그날 기록 · 08:00 전·23:00 뒤 안 함 · 무인 앱은 그날 남았으면 종료 미룸) (M4)
- 날짜 지정 실행과 섞이지 않음(대상 = 이번 ① 이 어제 칸을 받은 계정 · 다른 칸 안 건드림 · ① 미완료 회차 = 대기) (M5)
- 아침 값도 노출·방문 0 인데 판매가 있는 계정 = ⚠ 줄(값은 그대로 씀) (M6)
- 쿠팡 집계 전(판매 있는데 응답 노출·방문 전부 0 · 소유자 2026-11-26 '11.25 … 원인 파악해서 수정') = 0 으로 확정 안 함 · 같은 날 뒤 시각에
  다시 · 무인 앱은 그때까지 켜 둠 (M10) · 이미 0 으로 들어간 지난 칸(7일 안)도 다음 회차가 메움 (M11) · 집계 끝난 날의 0 = 진짜 0 확정 ·
  판매 있는데 0 = 확정 안 함 (M12) · 집계 전으로 보이면 남은 계정 로그인 안 함 (M13) · 실제 조회 = 창 한 번에 날마다 하루 조회 (M14)
- 앱 타이머·무인 앱 종료 미룸 = tools/verify_ui_morning_offline.py (화면 라이브러리 PySide6 필요라 따로)
실행: python tools/verify_traffic_morning_offline.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics import config  # noqa: E402
from coupang_analytics import traffic_morning as TM  # noqa: E402
from coupang_analytics.input_list import Account  # noqa: E402
from coupang_analytics.pipeline_paths import _master_path, _snapshot_path  # noqa: E402
from coupang_analytics.registry_lock import registry_lock  # noqa: E402
from coupang_analytics.report import OptionMetric  # noqa: E402
from coupang_analytics.workbook import OutputWorkbook  # noqa: E402

FAILS: list[str] = []
NOW = datetime(2026, 11, 21, 8, 0, 30)      # 11-21 08:00 → 보충 칸 = 11.20
LABEL, OLD = "11.20", "11.19"
SHOPS = [("가게A", "acc1", "상품A", "111"), ("가게B", "acc2", "상품B", "222")]


def check(ok: bool, msg: str) -> None:
    print(f"  {'✔' if ok else '✘'} {msg}")
    if not ok:
        FAILS.append(msg)


def om(vid: str, views: int, visitors: int, sales: int = 0) -> OptionMetric:
    return OptionMetric(option_id=vid, product_name="p", option_name="o", item_id="i", views=views, sales=sales,
                        visitors=visitors)


def master(out: Path, stamped=(LABEL,)) -> None:
    """00:10 결과 — 11.20 칸 판매 5·노출 0·방문 0·순위 7위 · 11.19 칸(날짜 지정으로 채운 옛 칸) 노출 30."""
    wb = OutputWorkbook.empty()
    for biz, aid, prod, vid in SHOPS:
        wb.ensure_account(biz)
        wb.set_account_id(biz, aid)
        wb.ensure_product_block(biz, prod, "로켓그로스", ["kw"])
        wb.set_product_vids(biz, prod, [vid])
        for lbl, views in ((OLD, 30), (LABEL, 0)):
            wb.set_product_metric(biz, prod, config.M_SALES, lbl, 5)
            wb.set_product_metric(biz, prod, config.M_VIEWS, lbl, views)
            wb.set_product_metric(biz, prod, config.M_VISITORS, lbl, views // 2)
            wb.set_product_metric(biz, prod, config.M_INVENTORY, lbl, 9)
            wb.set_keyword_rank(biz, prod, "kw", lbl, 7)
        for lbl in stamped:
            wb.mark_sales_collected(aid, lbl)
    wb.save(_master_path(out))


def accounts():
    return [Account(aid, "대표", biz) for biz, aid, _p, _v in SHOPS]


def val(out: Path, biz: str, prod: str, metric: str, lbl: str):
    wb = OutputWorkbook.load(_master_path(out))
    row = wb._metric_row[(biz, prod, metric)]
    return wb.wb[biz].cell(row, wb._date_col[biz][lbl]).value


def rank(out: Path, biz: str, prod: str, lbl: str):
    wb = OutputWorkbook.load(_master_path(out))
    return wb.wb[biz].cell(wb._kw_row[(biz, prod, "kw")], wb._date_col[biz][lbl]).value


class Fake:
    """가짜 계정 조회 — 계정마다 정한 값/예외를 차례로(한 번 부를 때 하나). calls = (계정, 날) 부른 순서.
    값 = {VID: OptionMetric}(받은 날 모두 같은 값) 또는 {'YYYY-MM-DD': {VID: …}}(날마다 다른 값)."""

    def __init__(self, plan: dict):
        self.plan, self.calls, self.opens = plan, [], []

    def __call__(self, a, days, get_password, log):
        one = isinstance(days, str)            # 옛 방식(하루 문자열)으로 불려도 같은 기록
        want = [days] if one else list(days)
        self.opens.append(a.account_id)        # 계정 창 연 횟수(로그인 1번 = 1)
        self.calls += [(a.account_id, d) for d in want]
        todo = self.plan[a.account_id]
        r = todo.pop(0) if isinstance(todo, list) else todo
        if isinstance(r, Exception):
            raise r
        by_day = {d: (r.get(d, {}) if any(str(k)[:2] == "20" for k in r) else r) for d in want}
        return (by_day[want[0]] if one else by_day), False


def run(out: Path, fake, *, log=None, in_use=lambda p: False, sleep=lambda s: None, pushed=None, now=NOW, accs=None):
    lines = []
    res = TM.run_daily(accs or accounts(), now=now, out_dir=out, on_log=(log or lines.append), gsheet_url="URL",
                       pipe_lock=out / "_잠금" / "파이프라인.lock", fetch=fake, in_use=in_use, sleep=sleep,
                       push=lambda wb, url, lg: (pushed if pushed is not None else []).append(url),
                       lock_dir=out / "정산" / "_잠금", clock=lambda: now)   # 23:50 마감도 시험 시각 기준(실제 시계 X)
    return res, lines


def m1_only_two_rows():
    print("[M1] 어제 칸 노출·방문자 두 줄만 덮어씀 · 판매·순위·재고·옛 칸 그대로 · 응답에 없는 블록 그대로")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        master(out)
        pushed = []
        fake = Fake({"acc1": {"111": om("111", 120, 60, 99)}, "acc2": {"999": om("999", 1, 1)}})
        res, lines = run(out, fake, pushed=pushed)
        check(val(out, "가게A", "상품A", config.M_VIEWS, LABEL) == 120, "acc1 11.20 노출 0 → 120")
        check(val(out, "가게A", "상품A", config.M_VISITORS, LABEL) == 60, "acc1 11.20 방문 0 → 60")
        check(val(out, "가게A", "상품A", config.M_SALES, LABEL) == 5, "판매 칸 그대로(5 · 아침 응답 판매 99 안 씀)")
        check(rank(out, "가게A", "상품A", LABEL) == "7위", "순위 칸 그대로(7위)")
        check(val(out, "가게A", "상품A", config.M_INVENTORY, LABEL) == 9, "재고 칸 그대로(9)")
        check(val(out, "가게A", "상품A", config.M_VIEWS, OLD) == 30, "옛 칸(11.19) 노출 그대로(30)")
        check(val(out, "가게B", "상품B", config.M_VIEWS, LABEL) == 0, "acc2: 응답에 블록 VID 없음 → 그대로(0 · 덮지 않음)")
        check([c[1] for c in fake.calls] == ["2026-11-20", "2026-11-20"], f"조회 = 어제 하루만 {fake.calls}")
        check(_snapshot_path(out, NOW).exists(), "그날 스냅샷도 저장")
        check(pushed == ["URL"], "결과 구글시트 반영 1번")
        rec = json.loads((out / TM.STATE_DIR / "2026-11-21.json").read_text(encoding="utf-8"))
        check(len(rec["바뀐 칸"]) == 2 and {c["줄"] for c in rec["바뀐 칸"]} == {config.M_VIEWS, config.M_VISITORS},
              f"근거 기록 = 바뀐 칸 2개(노출·방문 · 전/후) {rec['바뀐 칸']}")
        check(res["acc1"]["결과"] == "성공" and res["acc2"]["결과"] == "성공", "두 계정 성공")


def m2_no_overlap():
    print("[M2] 정산이 계정을 쓰는 중 = 그동안 안 들어감(맨 뒤로 → 끝난 뒤) · 파이프라인 잠금 중 = 시작 안 함")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        master(out)
        held = threading.Event()
        release = threading.Event()
        lock_dir = out / "정산" / "_잠금"

        def settle():   # 정산이 acc1 잠금을 쥐고 있음
            with registry_lock(lock_dir / "acc1.lock", wait_sec=0):
                held.set()
                release.wait(10)
        t = threading.Thread(target=settle)
        t.start()
        held.wait(5)
        order = []
        fake = Fake({"acc1": {"111": om("111", 120, 60)}, "acc2": {"222": om("222", 80, 40)}})

        def fetch(a, day, gp, log):
            order.append(a.account_id)
            if a.account_id == "acc2":
                release.set()          # acc2 를 받는 동안 정산이 acc1 을 끝냄
                t.join(5)
            return fake(a, day, gp, log)
        res, lines = run(out, fetch)
        check(order == ["acc2", "acc1"], f"acc1 = 정산 잠금 동안 안 들어감 → 맨 뒤로 미룬 뒤 받음 {order}")
        check(any("이 바퀴 맨 뒤로" in x for x in lines), "로그 '이 바퀴 맨 뒤로'")
        check(res["acc1"]["결과"] == "성공" and res["acc1"]["시도"] == 1, "미룸은 실패로 안 셈(시도 1)")

    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        master(out)
        chrome = {"n": 0}

        def in_use(profile):   # acc1 Chrome(정산) 이 3번 확인할 동안 켜져 있다가 꺼짐
            if profile.endswith("acc1"):
                chrome["n"] += 1
                return chrome["n"] <= 3
            return False
        order = []
        fake = Fake({"acc1": {"111": om("111", 1, 1)}, "acc2": {"222": om("222", 1, 1)}})
        run(out, lambda a, dd, gp, lg: (order.append((a.account_id, chrome["n"])), fake(a, dd, gp, lg))[1],
            in_use=in_use)
        check(order[-1][0] == "acc1" and order[-1][1] >= 4, f"acc1 Chrome 꺼진 뒤에만 열림 {order}")

    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        master(out)
        fake = Fake({"acc1": {}, "acc2": {}})
        with registry_lock(out / "_잠금" / "파이프라인.lock", wait_sec=0):   # ①②③·날짜 지정·다른 창 실행 중
            res, _ = run(out, fake)
        check(res is None and not fake.calls, "파이프라인 잠금 중 = 조회 0 · None")
        check(TM.last_day(out) == "", "그날 기록 안 남김(끝나면 다음 타이머에 다시)")


def m3_three_tries():
    print("[M3] 3번 실패 = 00:10 값 그대로 + 실패 로그 · 비밀번호 거부 = 1번만")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        master(out)
        sleeps = []
        fake = Fake({"acc1": [TM.LoginFailed("로그인 차단(Akamai)")] * 3,
                     "acc2": [TM.LoginFailed("비밀번호 거부(24시간 다시 안 넣음 · D-123)", retry=False)]})
        pushed = []
        res, lines = run(out, fake, sleep=sleeps.append, pushed=pushed)
        check([c[0] for c in fake.calls].count("acc1") == 3, f"acc1 3번 시도 {fake.calls}")
        check([c[0] for c in fake.calls].count("acc2") == 1, "acc2 비밀번호 거부 = 다시 안 함(1번)")
        check(sleeps.count(TM.RETRY_GAP_SEC) == 2, f"바퀴 사이 쉼 2번 {sleeps}")
        check(val(out, "가게A", "상품A", config.M_VIEWS, LABEL) == 0, "acc1 칸 = 00:10 값 그대로(0 · 대신 채우지 않음)")
        fl = [x for x in lines if TM.FAIL in x]
        check(len(fl) == 2 and any("acc1" in x and "3번 시도" in x for x in fl), f"실패 로그 2줄 {fl}")
        check(res["acc1"] == {"사업자": "가게A", "결과": "실패", "시도": 3, "사유": "로그인 차단(Akamai)"},
              f"기록 {res['acc1']}")
        check(not pushed, "바뀐 칸 0 = 구글시트 반영 안 함")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        master(out)
        fake = Fake({"acc1": [RuntimeError("vi-detail-search 500"), {"111": om("111", 50, 20)}],
                     "acc2": {"222": om("222", 5, 2)}})
        res, _ = run(out, fake)
        check(res["acc1"]["결과"] == "성공" and res["acc1"]["시도"] == 2 and
              val(out, "가게A", "상품A", config.M_VIEWS, LABEL) == 50, "조회 오류 1번 → 2번째 바퀴 성공")


def m4_once_a_day():
    print("[M4] 하루 한 번 · 08:00 전/23:00 뒤 안 함 · 무인 앱 종료 미룸 판단")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        check(not TM.daily_due(datetime(2026, 11, 21, 7, 59), out), "07:59 = 아직")
        check(TM.daily_due(NOW, out), "08:00 = 할 때")
        check(not TM.daily_due(datetime(2026, 11, 21, 23, 1), out), "23:01 = 그날 새로 시작 안 함")
        check(TM.owed_today(datetime(2026, 11, 21, 3, 0), out), "03:00 ①②③ 끝 = 무인 앱 08:00 까지 남음")
        master(out)
        fake = Fake({"acc1": {"111": om("111", 1, 1)}, "acc2": {"222": om("222", 1, 1)}})
        run(out, fake)
        check(not TM.daily_due(datetime(2026, 11, 21, 9, 0), out) and not TM.owed_today(NOW, out),
              "실행 뒤 같은 날 다시 안 함")
        check(TM.daily_due(datetime(2026, 11, 22, 8, 0), out), "다음 날 08:00 = 다시")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        (out / "x").mkdir()
        res, lines = run(out, Fake({}))
        check(res == {} and TM.last_day(out) == "2026-11-21", "마스터 없음 = ❌ 줄 + 그날 기록(1분마다 되풀이 안 함)")
    check(TM.MORNING_AT.strftime("%H:%M") == "08:00" and TM.MAX_TRIES == 3, "시각 08:00 · 3번(한 곳 상수)")


def m5_not_mixed():
    print("[M5] 날짜 지정과 안 섞임 · 대상 = 이번 ① 이 어제 칸을 받은 계정 · ① 미완료 회차 = 대기")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        master(out, stamped=(OLD,))          # 날짜 지정으로 11.19 만 받은 상태(11.20 칸 ① 없음)
        fake = Fake({"acc1": {"111": om("111", 9, 9)}, "acc2": {"222": om("222", 9, 9)}})
        res, lines = run(out, fake)
        check(not fake.calls and res == {}, "어제 칸 ① 스탬프 없음 = 대상 0(로그인 0)")
        check(val(out, "가게A", "상품A", config.M_VIEWS, OLD) == 30, "날짜 지정 칸 그대로")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        check("완료 기록 없음" in TM.wait_reason(NOW, out), "이번 회차 ① 완료 기록 없음 = 대기")
        from coupang_analytics.pipeline_paths import _run_stage_path
        _run_stage_path(out).write_text(json.dumps({"date": "2026-11-21", "stage": "done",
                                                    "at": "2026-11-21T03:00:00"}), encoding="utf-8")
        check(TM.wait_reason(NOW, out) == "", "이번 회차 ①②③ 끝 = 시작")
        _run_stage_path(out).write_text(json.dumps({"date": "2026-11-20", "stage": "done",
                                                    "at": "2026-11-20T03:00:00"}), encoding="utf-8")
        check("완료 기록 없음" in TM.wait_reason(NOW, out), "어제 회차 기록뿐 = 대기")
        check(TM.target_day(datetime(2026, 11, 21, 8, 0)).isoformat() == "2026-11-20", "보충 칸 = 실행일 − 1")


def m6_zero_warn():
    print("[M6] 아침 값도 노출·방문 0 인데 판매 있음 = ⚠ 줄(값 그대로)")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        master(out)
        fake = Fake({"acc1": {"111": om("111", 0, 0, 3)}, "acc2": {"222": om("222", 4, 2, 0)}})
        _, lines = run(out, fake)
        w = [x for x in lines if "⚠" in x]
        check(len(w) == 1 and "acc1" in w[0] and "판매 3" in w[0], f"⚠ 1줄(acc1) {w}")


def _stage_done(out: Path, at: str = "2026-11-21T03:00:00") -> None:
    from coupang_analytics.pipeline_paths import _run_stage_path
    _run_stage_path(out).write_text(json.dumps({"date": at[:10], "stage": "done", "at": at}), encoding="utf-8")


def m8_missed_after_23():
    print("[M8] 23:00 넘겨 그날 보충을 못 함 = ❌ '아침 보충 못 함' 한 줄(사유·계정 수 · 값 그대로) · 그날 종합 오류 현황에도 · 한 번만")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        master(out)
        late = datetime(2026, 11, 21, 23, 5)
        check(not TM.missed_today(late, out), "이번 회차 ① 완료 기록 없음 = 못 함 대상 아님(보충 대상 없던 날)")
        _stage_done(out)
        check(not TM.missed_today(datetime(2026, 11, 21, 22, 59), out), "22:59 = 아직 시작 가능")
        check(TM.missed_today(late, out), "23:05 · ① 완료 · 그날 기록 없음 = 못 함")
        lines = []
        ok = TM.give_up(accounts(), now=late, out_dir=out, log=lines.append, why="③ 순위가 23:00 뒤에 끝남")
        bad = [x for x in lines if "❌ 노출·방문자 아침 보충 못 함" in x]
        check(ok and len(bad) == 1 and "③ 순위가 23:00 뒤에 끝남" in bad[0] and "2계정" in bad[0]
              and "11.20" in bad[0] and "00:10 값 그대로" in bad[0], f"❌ 줄 1개(사유·2계정·칸·값 그대로) {bad}")
        check(val(out, "가게A", "상품A", config.M_VIEWS, LABEL) == 0, "값 대신 채우지 않음(0 그대로)")
        check(TM.last_day(out) == "2026-11-21" and not TM.missed_today(late, out), "그날 기록 → 두 번 안 남김")
        lines2 = []
        with registry_lock(out / "_잠금" / "파이프라인.lock", wait_sec=0):
            out2 = out / "b"
            (out2).mkdir()
            ok2 = TM.give_up(accounts(), now=late, out_dir=out2, log=lines2.append, why="x",
                             pipe_lock=out / "_잠금" / "파이프라인.lock")
        check(ok2 is False and not lines2, "다른 실행이 파이프라인을 쥠 = 여기서 안 남김(그 실행의 종합이 남김)")

    import os
    from coupang_analytics import pipeline_stages as PSt
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "output"
        out.mkdir()
        master(out)
        _stage_done(out)
        here = os.getcwd()
        saved = {k: getattr(PSt, k) for k in ("run_full", "select_keywords_stage", "track_ranks_stage",
                                               "push_ledger_inventory", "push_company_stock", "write_run_stage")}
        orig_dt = TM.datetime

        class Late(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 11, 21, 23, 5)
        try:
            os.chdir(d)
            PSt.run_full = lambda *a, **k: None
            PSt.select_keywords_stage = lambda *a, **k: None
            PSt.track_ranks_stage = lambda **k: None
            PSt.push_ledger_inventory = PSt.push_company_stock = lambda *a, **k: None
            PSt.write_run_stage = lambda *a, **k: None
            TM.datetime = PSt.datetime = Late
            lines = []
            il = type("IL", (), {"accounts": accounts()})()
            PSt.run_stages(il, PSt.StagePlan(), ai_key="k", naver=None, date_from="2026-11-20", date_to="2026-11-20",
                           date_label="2026-11-20", get_password=None, carry=True, on_log=lines.append)
        finally:
            os.chdir(here)
            TM.datetime = PSt.datetime = orig_dt
            for k, v in saved.items():
                setattr(PSt, k, v)
        blk = lines[lines.index(next(x for x in lines if "[실행 결과 종합]" in x)):]
        check(any("노출·방문자 아침 보충 1건" in x for x in blk) and any("아침 보충 못 함" in x for x in blk),
              f"①②③ 가 23:00 뒤 끝남 = 그 실행 종합 오류 현황에 들어감 {[x for x in blk if '오류' in x or '아침' in x]}")


def m9_stop_new_2350():
    print("[M9] 23:50 뒤 새 계정 시작 안 함 · 받은 계정까지 저장·구글 반영 · 남은 계정 ❌ 줄 · 자정 넘김 없음")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        master(out)
        cur = [datetime(2026, 11, 21, 23, 45)]
        fake = Fake({"acc1": {"111": om("111", 70, 30)}, "acc2": {"222": om("222", 80, 40)}})

        def fetch(a, day, gp, log):
            cur[0] += timedelta(minutes=6)       # 계정 하나 6분
            return fake(a, day, gp, log)
        pushed, lines = [], []
        TM.run_daily(accounts(), now=cur[0], out_dir=out, on_log=lines.append, gsheet_url="URL",
                     pipe_lock=out / "_잠금" / "파이프라인.lock", fetch=fetch, in_use=lambda p: False,
                     sleep=lambda s: cur.__setitem__(0, cur[0] + timedelta(seconds=s)),
                     push=lambda wb, url, lg: pushed.append(url), lock_dir=out / "정산" / "_잠금", clock=lambda: cur[0])
        check([c[0] for c in fake.calls] == ["acc1"], f"23:51 = acc2 새로 시작 안 함 {fake.calls}")
        check(val(out, "가게A", "상품A", config.M_VIEWS, LABEL) == 70 and pushed == ["URL"],
              "받은 계정(acc1)까지 마스터 저장·구글 반영")
        check(val(out, "가게B", "상품B", config.M_VIEWS, LABEL) == 0, "남은 계정 = 00:10 값 그대로")
        cut = [x for x in lines if "❌ 노출·방문자 아침 보충 못 함(23:50 넘음)" in x]
        check(len(cut) == 1 and "남은 1계정" in cut[0] and "acc2" in cut[0], f"❌ 남은 계정 줄 {cut}")
        check(TM.STOP_NEW.strftime("%H:%M") == "23:50", "23:50 = 한 곳 상수")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        master(out)
        cur = [datetime(2026, 11, 21, 23, 41)]   # 1바퀴 뒤 10분 쉼 = 23:51 → 다음 바퀴 안 감
        fake = Fake({"acc1": [TM.LoginFailed("로그인 차단(Akamai)")] * 3, "acc2": {"222": om("222", 5, 5)}})
        lines = []
        TM.run_daily(accounts(), now=cur[0], out_dir=out, on_log=lines.append, gsheet_url="URL",
                     pipe_lock=out / "_잠금" / "파이프라인.lock", fetch=fake, in_use=lambda p: False,
                     sleep=lambda s: cur.__setitem__(0, cur[0] + timedelta(seconds=s)),
                     push=lambda *a: None, lock_dir=out / "정산" / "_잠금", clock=lambda: cur[0])
        check([c[0] for c in fake.calls].count("acc1") == 1, f"다시 시도 쉼(10분)이 23:50 을 넘기면 다음 바퀴 안 감 {fake.calls}")
        cut = [x for x in lines if "❌" in x and "23:50 넘음" in x]
        check(len(cut) == 1 and "acc1" in cut[0], f"남은 계정 = 다시 시도 남은 acc1 {cut}")


def raw_metrics(vid: str, pv: int, uv: int, sold: int) -> dict:
    """판매분석 하루 응답 1옵션 → 지표(실제 파싱 함수 · 칸 모양 = 운용 PC 사본 `_raw/sg0141n_sales_p1`(11-26 00:10 · 11-25 하루):
    판매·주문은 있는데 totalPageViews·totalUniqueVisitor = 0.0 · 변화율 −100 · 장바구니 0)."""
    from coupang_analytics import collector
    body = {"vendorItemDetails": {"vendorItemId": vid, "productName": "p", "itemName": "o", "itemId": "i",
                                  "registrationType": "RFM"},
            "businessInsightsMetricsResponse": {"totalPageViews": float(pv), "pageViewsVariance": -100.0 if not pv else 5.0,
                                                "totalUniqueVisitor": float(uv), "uniqueVisitorVariance": -100.0 if not uv else 5.0,
                                                "totalUnitsSold": float(sold), "totalOrders": float(sold),
                                                "totalGmv": 19900.0 * sold, "totalAddToCart": 0.0, "totalCogs": None}}
    return collector._parse_vendor_items([body])


def master_multi(out: Path, shops, cols) -> None:
    """여러 날 칸 — cols = [(칸, 노출)] · 모든 칸 ① 스탬프(그 칸을 ① 이 받음) · 판매 5 · 방문 = 노출 // 2."""
    wb = OutputWorkbook.empty()
    for biz, aid, prod, vid in shops:
        wb.ensure_account(biz)
        wb.set_account_id(biz, aid)
        wb.ensure_product_block(biz, prod, "로켓그로스", ["kw"])
        wb.set_product_vids(biz, prod, [vid])
        for lbl, views in cols:
            wb.set_product_metric(biz, prod, config.M_SALES, lbl, 5)
            wb.set_product_metric(biz, prod, config.M_VIEWS, lbl, views)
            wb.set_product_metric(biz, prod, config.M_VISITORS, lbl, views // 2)
            wb.mark_sales_collected(aid, lbl)
    wb.save(_master_path(out))


def m10_not_yet_same_day():
    print("[M10] 쿠팡 집계 전(판매는 있는데 응답 노출·방문 전부 0 · 11-26 08:07 실측 모양) = 0 으로 확정 안 함 · 같은 날 뒤 시각에 다시")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        master(out)
        zero = Fake({"acc1": raw_metrics("111", 0, 0, 14), "acc2": raw_metrics("222", 0, 0, 3)})
        _, lines = run(out, zero)
        check(val(out, "가게A", "상품A", config.M_VIEWS, LABEL) == 0, "집계 전 응답 = 칸 그대로(0)")
        check(any(getattr(TM, "NOT_YET", "쿠팡 노출·방문 집계 전") in x for x in lines),
              f"로그 '쿠팡 노출·방문 집계 전' 줄 {[x for x in lines if '집계' in x]}")
        later = NOW + timedelta(minutes=30)
        check(TM.owed_today(later, out), "같은 날 다시 남음 = 무인 앱 종료 미룸")
        check(not TM.daily_due(later, out), "바로 되풀이 안 함(30분 뒤 = 아직)")
        t2 = NOW + timedelta(seconds=getattr(TM, "RETRY_LATER_SEC", 7200))
        check(TM.daily_due(t2, out), f"정한 뒤 시각({t2:%H:%M}) = 다시 할 때")
        real = Fake({"acc1": raw_metrics("111", 120, 60, 14), "acc2": raw_metrics("222", 80, 40, 3)})
        run(out, real, now=t2)
        check(val(out, "가게A", "상품A", config.M_VIEWS, LABEL) == 120
              and val(out, "가게B", "상품B", config.M_VISITORS, LABEL) == 40, "뒤 시각에 실제 값으로 채움(120·40)")
        t3 = t2 + timedelta(minutes=1)
        check(not TM.owed_today(t3, out) and not TM.daily_due(t3, out), "다 받은 뒤 = 그날 끝(무인 앱 종료 가능)")


def m11_past_zero_next_day():
    print("[M11] 이미 0 으로 들어간 지난 칸(11.25 처럼 · 그날 기록 '바뀐 칸 0'으로 끝남) = 다음 날 회차가 어제 칸과 함께 메움")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        master_multi(out, SHOPS, [("11.10", 0), ("11.20", 0), ("11.21", 0)])
        (out / TM.STATE_DIR).mkdir(parents=True)
        (out / TM.STATE_DIR / TM.RUN_MARK).write_text(json.dumps(   # 고치기 전 판이 11-21 에 남긴 기록
            {"날짜": "2026-11-21", "보충한 날": "2026-11-20", "메모": "성공 2 · 실패 0 · 바뀐 칸 0"}), encoding="utf-8")
        now = datetime(2026, 11, 22, 8, 0, 30)
        fake = Fake({"acc1": {"2026-11-21": raw_metrics("111", 70, 30, 1), "2026-11-20": raw_metrics("111", 120, 60, 5)},
                     "acc2": {"2026-11-21": raw_metrics("222", 7, 3, 0), "2026-11-20": raw_metrics("222", 80, 40, 5)}})
        run(out, fake, now=now)
        days = sorted({c[1] for c in fake.calls})
        check(days == ["2026-11-20", "2026-11-21"], f"어제(11-21)·지난 0 칸(11-20) 둘 다 조회 · 7일 넘은 11-10 은 안 함 {days}")
        check(val(out, "가게A", "상품A", config.M_VIEWS, "11.20") == 120
              and val(out, "가게B", "상품B", config.M_VISITORS, "11.20") == 40, "지난 칸 11.20 실제 값으로 메움")
        check(val(out, "가게A", "상품A", config.M_VIEWS, "11.21") == 70, "어제 칸 11.21 도 채움")
        check(fake.opens == ["acc1", "acc2"], f"계정마다 창 한 번(같은 세션에서 두 날) {fake.opens}")
    with tempfile.TemporaryDirectory() as d:   # 어제 칸은 집계 끝 · 지난 칸만 아직 집계 전 = 같은 날 되풀이 안 함(다음 날 회차가 다시)
        out = Path(d)
        master_multi(out, SHOPS, [("11.20", 0), ("11.21", 0)])
        now = datetime(2026, 11, 22, 8, 0, 30)
        run(out, Fake({"acc1": {"2026-11-21": raw_metrics("111", 70, 30, 1), "2026-11-20": raw_metrics("111", 0, 0, 5)},
                       "acc2": {"2026-11-21": raw_metrics("222", 7, 3, 0), "2026-11-20": raw_metrics("222", 0, 0, 5)}}), now=now)
        check(not TM.owed_today(now + timedelta(minutes=1), out), "지난 칸만 집계 전 = 같은 날 다시 안 함(무인 앱 종료)")
        nxt = Fake({"acc1": {}, "acc2": {}})
        run(out, nxt, now=now + timedelta(days=1))
        check(("acc1", "2026-11-20") in nxt.calls, f"다음 날 회차가 지난 칸 11-20 다시 조회 {nxt.calls}")


def m12_true_zero_confirmed():
    print("[M12] 집계 끝난 날(다른 계정 노출 있음) = 활동 없는 계정 0 은 진짜 0 으로 확정(다시 안 받음) · 판매 있는데 0 = 확정 안 함(다음 날 다시)")
    nxt = datetime(2026, 11, 22, 8, 0, 30)
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        master(out)
        run(out, Fake({"acc1": raw_metrics("111", 50, 20, 2), "acc2": {}}))
        check(not TM.owed_today(NOW + timedelta(minutes=1), out), "집계 끝난 날 = 같은 날 다시 안 함")
        again = Fake({"acc1": {}, "acc2": {}})
        run(out, again, now=nxt)
        check(not again.calls, f"진짜 0 으로 확정된 칸(acc2 11.20) = 다음 날 다시 안 받음 {again.calls}")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        master(out)
        run(out, Fake({"acc1": raw_metrics("111", 50, 20, 2), "acc2": raw_metrics("222", 0, 0, 3)}))
        again = Fake({"acc1": {}, "acc2": raw_metrics("222", 9, 5, 3)})
        run(out, again, now=nxt)
        check(again.calls == [("acc2", "2026-11-20")] and val(out, "가게B", "상품B", config.M_VIEWS, LABEL) == 9,
              f"판매 3 인데 노출 0 = 확정 안 함 → 다음 날 다시 받아 메움 {again.calls}")


def m13_probe_stop():
    print("[M13] 집계 전으로 보이면(판매 있는데 노출·방문 0 계정이 3개 이어짐 · 노출 있는 계정 없음) 남은 계정은 이번에 로그인 안 함")
    shops = SHOPS + [("가게C", "acc3", "상품C", "333"), ("가게D", "acc4", "상품D", "444")]
    accs = [Account(aid, "대표", biz) for biz, aid, _p, _v in shops]
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        master_multi(out, shops, [(LABEL, 0)])
        fake = Fake({aid: raw_metrics(vid, 0, 0, 4) for _b, aid, _p, vid in shops})
        res, lines = run(out, fake, accs=accs)
        check(fake.opens == ["acc1", "acc2", "acc3"], f"3계정만 열고 멈춤(acc4 로그인 안 함) {fake.opens}")
        check(TM.owed_today(NOW + timedelta(minutes=30), out), "남은 계정 = 같은 날 뒤 시각에 다시")
        check(res is not None and res.get("acc4", {}).get("결과") != "실패", f"acc4 = 실패로 세지 않음 {res and res.get('acc4')}")


def m14_live_fetch_days():
    print("[M14] 실제 조회 함수 = 창 한 번(로그인 한 번)에 받을 날마다 판매분석 하루 조회(시작일 = 끝일) · 날 사이 쉼")
    from types import SimpleNamespace
    from coupang_analytics import browser, collector, pipeline_sales
    asked, sleeps, opened = [], [], []

    class FakeBrowser:
        def __init__(self, profile_dir, offscreen):
            opened.append(offscreen)
            self.page = SimpleNamespace(wait_for_timeout=lambda ms: None)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def goto(self, url):
            pass

        def authenticated(self):
            return True

        def is_suspended(self):
            return False
    saved = (browser.WingBrowser, pipeline_sales._login_with_candidates, collector.fetch_sales_details, TM.time)
    try:
        browser.WingBrowser = FakeBrowser
        pipeline_sales._login_with_candidates = lambda b, a, pws, log, login, semi: True
        collector.fetch_sales_details = lambda page, f, t, log=None: (asked.append((f, t)), {"1": om("1", 1, 1)})[1]
        TM.time = SimpleNamespace(sleep=sleeps.append, monotonic=saved[3].monotonic)
        got, fresh = TM.fetch_live(Account("acc1", "대표", "가게A"), ["2026-11-21", "2026-11-20"], None, lambda m: None)
    finally:
        browser.WingBrowser, pipeline_sales._login_with_candidates, collector.fetch_sales_details, TM.time = saved
    check(asked == [("2026-11-21", "2026-11-21"), ("2026-11-20", "2026-11-20")], f"날마다 하루 조회 {asked}")
    check(sorted(got) == ["2026-11-20", "2026-11-21"] and opened == [False] and fresh is False,
          f"창 한 번(보이는 창) · 날별 결과 {sorted(got)} {opened}")
    check(len(sleeps) == 1, f"날 사이 쉼 1번 {sleeps}")


def main() -> int:
    for t in (m1_only_two_rows, m2_no_overlap, m3_three_tries, m4_once_a_day, m5_not_mixed, m6_zero_warn, m8_missed_after_23,
              m9_stop_new_2350, m10_not_yet_same_day, m11_past_zero_next_day, m12_true_zero_confirmed, m13_probe_stop, m14_live_fetch_days):
        t()
    print(f"\n결과: {'통과' if not FAILS else f'실패 {len(FAILS)}건'}")
    for f in FAILS:
        print("  ✘", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
