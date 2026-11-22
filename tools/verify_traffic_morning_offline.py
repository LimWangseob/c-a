"""노출·방문자 아침 보충 오프라인 검증(D-374) — 로그인·쿠팡·구글 호출 없음(계정 조회·구글 반영은 가짜).

기대값은 결정 문구(D-374 · 통제 세션 지시서)에서 뽑았다(코드에서 뽑지 않음):
- 08:00 에 어제(실행일 − 1) 칸의 노출·방문자 두 줄만 아침 값으로 덮어씀 · 판매·순위·재고·다른 날짜 칸은 그대로 (M1)
- 정산이 그 계정 잠금·Chrome 을 쓰는 중이면 그동안 들어가지 않음(맨 뒤로 미룸 → 끝난 뒤) · 파이프라인 잠금 중이면 시작 안 함 (M2)
- 계정마다 최대 3번 · 끝내 실패 = 00:10 값 그대로 + '노출·방문자 아침 보충 실패' 줄 · 비밀번호 거부 = 다시 안 함 (M3)
- 하루 한 번(그날 기록 · 08:00 전·23:00 뒤 안 함 · 무인 앱은 그날 남았으면 종료 미룸) (M4)
- 날짜 지정 실행과 섞이지 않음(대상 = 이번 ① 이 어제 칸을 받은 계정 · 다른 칸 안 건드림 · ① 미완료 회차 = 대기) (M5)
- 아침 값도 노출·방문 0 인데 판매가 있는 계정 = ⚠ 줄(값은 그대로 씀) (M6)
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
    """가짜 계정 조회 — 계정마다 정한 값/예외를 차례로. calls = 부른 순서."""

    def __init__(self, plan: dict):
        self.plan, self.calls = plan, []

    def __call__(self, a, day_iso, get_password, log):
        self.calls.append((a.account_id, day_iso))
        todo = self.plan[a.account_id]
        r = todo.pop(0) if isinstance(todo, list) else todo
        if isinstance(r, Exception):
            raise r
        return r, False


def run(out: Path, fake, *, log=None, in_use=lambda p: False, sleep=lambda s: None, pushed=None, now=NOW):
    lines = []
    res = TM.run_daily(accounts(), now=now, out_dir=out, on_log=(log or lines.append), gsheet_url="URL",
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


def main() -> int:
    for t in (m1_only_two_rows, m2_no_overlap, m3_three_tries, m4_once_a_day, m5_not_mixed, m6_zero_warn, m8_missed_after_23, m9_stop_new_2350):
        t()
    print(f"\n결과: {'통과' if not FAILS else f'실패 {len(FAILS)}건'}")
    for f in FAILS:
        print("  ✘", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
