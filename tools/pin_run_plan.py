"""핀 테스트 — pipeline.plan_run_mode 실행모드 결정(순수 로직) 고정.

배경: app_qt/app.do_run_full 의 실행모드 if/elif 사슬(newall/redo/resume/carry)은 예전에 회귀가 잦았고
UI에 중복돼 있었다 → 백엔드 plan_run_mode 로 공통화. 이 파일이 6개 분기를 골든값으로 고정한다.
분해 전/후로 초록이면 실행모드 결정이 불변임을 보증. 실행: python tools/pin_run_plan.py (순수·결정적).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics.pipeline import column_dates, plan_run_mode, run_log_labels, run_title  # noqa: E402

DF, DT = "2026-09-21", "2026-09-22"
DL = "09.22"   # 기본 날짜라벨(오늘)


def _check(cond: bool, msg: str) -> None:
    print(f"    {'[통과]' if cond else '[실패]'} {msg}")
    if not cond:
        raise AssertionError(msg)


def pin_newall():
    print("[핀 P1] 통계 전체 초기화(newall) — 이어쓰기/재개 아님")
    p = plan_run_mode(newall=True, redo=False, meta={"date_from": "x", "date_to": "y", "done": [1]},
                      master=True, date_from=DF, date_to=DT, date_label=DL)
    _check(not p.resume and not p.carry and not p.redo_today, "resume/carry/redo 모두 False")
    _check("전체 초기화" in p.mode_desc, "초기화 안내 문구")
    _check(p.date_from == DF and p.date_to == DT, "기간=기본(meta 무시)")
    _check(p.date_label == DL, "날짜라벨=기본(재개 아님 → 복원 안 함)")


def pin_redo_with_master():
    print("[핀 P2] 오늘 것만 다시(redo)+마스터 있음 — 이어쓰기+오늘 재수집")
    p = plan_run_mode(newall=False, redo=True, meta=None, master=True, date_from=DF, date_to=DT)
    _check(p.carry and p.redo_today and not p.resume, "carry·redo_today True·resume False")
    _check("오늘 것만 다시" in p.mode_desc, "오늘 재수집 안내")


def pin_redo_no_master():
    print("[핀 P3] 오늘 것만 다시(redo)+마스터 없음 — 새 통계 시작")
    p = plan_run_mode(newall=False, redo=True, meta=None, master=False, date_from=DF, date_to=DT)
    _check(not p.carry and not p.redo_today and not p.resume, "전부 False(새 통계)")
    _check("새 통계 시작" in p.mode_desc, "새 통계 안내")


def pin_resume():
    print("[핀 P4] 진행분(meta) 있음 — 이어서(완료 건너뜀), 기간=meta로 덮음")
    meta = {"date_from": "2026-09-19", "date_to": "2026-09-20", "done": ["a", "b"],
            "carry": True, "date_label": "09.19"}
    p = plan_run_mode(newall=False, redo=False, meta=meta, master=True, date_from=DF, date_to=DT, date_label=DL)
    _check(p.resume and p.carry, "resume·carry True")
    _check(p.date_from == "2026-09-19" and p.date_to == "2026-09-20", "기간=meta로 덮음")
    _check("이어서 하기" in p.mode_desc and "2개" in p.mode_desc, "완료 2개 건너뜀 안내")
    _check(p.date_label == "09.19", "날짜라벨=meta로 복원(재개 시 시작일 기준·app_qt/app 공통)")
    # 재개인데 meta 에 date_label 없으면 기본 라벨로 폴백(옛 진행중 파일 호환)
    p2 = plan_run_mode(newall=False, redo=False, meta={k: v for k, v in meta.items() if k != "date_label"},
                       master=True, date_from=DF, date_to=DT, date_label=DL)
    _check(p2.date_label == DL, "meta 에 date_label 없으면 기본 라벨 폴백")


def pin_carry_master_only():
    print("[핀 P5] 마스터만 있음(진행분 없음) — 오늘 컬럼 추가(이어쓰기)")
    p = plan_run_mode(newall=False, redo=False, meta=None, master=True, date_from=DF, date_to=DT)
    _check(p.carry and not p.resume and not p.redo_today, "carry만 True")
    _check(f"오늘({DT})" in p.mode_desc and "컬럼 추가" in p.mode_desc, "오늘 컬럼 추가 안내")


def pin_first_run():
    print("[핀 P6] 아무것도 없음(첫 실행) — 새 통계 시작")
    p = plan_run_mode(newall=False, redo=False, meta=None, master=False, date_from=DF, date_to=DT)
    _check(not p.carry and not p.resume and not p.redo_today, "전부 False")
    _check("새 통계 시작" in p.mode_desc and DF in p.mode_desc, "새 통계·기간 안내")


def pin_labels():
    print("[핀 P7] run_title / run_log_labels — 제목·모드/단계 표기(UI 공통)")
    _check(run_title(True) == "① 판매수집(반자동)", "①판매수집 반자동 제목")
    _check(run_title(False) == "전체 실행(① 반자동 로그인)", "전체실행 반자동 제목")
    m, s = run_log_labels(keywords_off=False, resume=True, redo_today=False, carry=True)
    _check(m == "이어서 " and s == "", "resume=이어서·전체실행 단계표기 없음")
    m, s = run_log_labels(keywords_off=False, resume=False, redo_today=True, carry=True)
    _check(m == "오늘다시 ", "redo_today=오늘다시")
    m, s = run_log_labels(keywords_off=False, resume=False, redo_today=False, carry=True)
    _check(m == "통계이어쓰기 ", "carry=통계이어쓰기")
    m, s = run_log_labels(keywords_off=False, resume=False, redo_today=False, carry=False)
    _check(m == "새통계 ", "아무것도 없음=새통계")
    m, s = run_log_labels(keywords_off=True, resume=False, redo_today=False, carry=False)
    _check(s == " · ①판매수집(키워드·순위 없음)", "keywords_off=①판매수집 단계표기")
    m, s = run_log_labels(keywords_off=False, resume=False, redo_today=False, carry=True)
    _check(s == "", "전체실행=단계표기 없음")


def pin_designated_date():
    print("[핀 P8] 날짜 지정(2026-10-10) — 칸=지정일·판매=전날·오늘 다른 날짜 진행분은 안 이어받음·빈 칸만")
    _check(column_dates("2026-10-09") == ("2026-10-08", "2026-10-08", "2026-10-09"), "10.09 칸 = 10/08 판매")
    _check(column_dates("2026-10-01") == ("2026-09-30", "2026-09-30", "2026-10-01"), "월 경계(10/01 칸=9/30 판매)")
    meta = {"date_from": "2026-10-09", "date_to": "2026-10-09", "done": ["a"], "carry": True, "date_label": "2026-10-10"}
    p = plan_run_mode(False, False, meta, True, "2026-10-08", "2026-10-08", "2026-10-09", designated=True)
    _check(not p.resume and p.carry and p.date_label == "2026-10-09", "오늘(10.10) 진행분 대신 지정 칸(10.09) 채우기")
    _check(p.date_from == "2026-10-08" and "빈 칸만" in p.mode_desc, "판매=지정일 전날·안내 문구")
    p2 = plan_run_mode(False, False, dict(meta, date_label="2026-10-09"), True, "2026-10-08", "2026-10-08",
                       "2026-10-09", designated=True)
    _check(p2.resume and p2.date_label == "2026-10-09", "같은 지정 날짜 진행분이면 이어서")
    p3 = plan_run_mode(False, False, meta, True, DF, DT, DL)
    _check(p3.resume and p3.date_label == "2026-10-10", "날짜 지정 아니면 기존대로 진행분 이어서(라벨=진행분)")


# ── 단계 조립(정리 B6 — 전체실행·무인 --auto·재부팅 복구 --resume 공통 run_stages) ─────────────
import coupang_analytics.pipeline_stages as _st  # noqa: E402
from coupang_analytics.pipeline_stages import StagePlan, plan_resume_stages, run_stages  # noqa: E402


def _fake_stages(stop_at: str | None = None):
    """가짜 단계 — 호출 순서·단계 기록만 모은다(실 로그인·API·시트 없음). stop_at=그 단계 실행 중 중지 요청."""
    calls, marks, stop = [], [], {"v": False}

    def hit(name):
        calls.append(name)
        if stop_at == name:
            stop["v"] = True

    def fake_run_full(_il, **kw):
        hit("①재개" if kw["resume"] else "①")
        return "snap"
    _st.run_full = fake_run_full
    _st.select_keywords_stage = lambda *a, **k: hit("②")
    _st.track_ranks_stage = lambda **k: (hit("③"), calls.append(f"③칸={k['date_label']}"))[0] or "ranks"
    _st.push_ledger_inventory = lambda *a: hit("재고")
    _st.push_company_stock = lambda *a: hit("회사재고")
    _st.write_run_stage = lambda s: marks.append(s)
    return calls, marks, (lambda: stop["v"])


def _run(plan, stop_fn, **kw):
    return run_stages(None, plan, ai_key="k", naver=None, date_from=DF, date_to=DT, date_label=DL,
                      get_password=lambda a: None, carry=True, should_stop=stop_fn, on_log=lambda m: None, **kw)


def pin_resume_plan():
    print("[핀 P9] 재부팅 복구 계획 — 진행 파일·단계 기록으로 남은 단계만(할 것 없으면 None)")
    _check(plan_resume_stages(None, None) is None, "기록·진행 파일 없음 → 할 것 없음")
    _check(plan_resume_stages({"stage": "done"}, None) is None, "'done' → 할 것 없음")
    p = plan_resume_stages(None, {"done": []})
    _check(p.sales and p.keywords and p.ranks and p.resume, "① 진행 중 → ①이어서+②③")
    p = plan_resume_stages({"stage": "done"}, {"done": []})
    _check(p.sales and p.keywords, "진행 파일이 있으면 'done' 이어도 ①부터")
    p = plan_resume_stages({"stage": "sales"}, None)
    _check(not p.sales and p.keywords and p.ranks, "'sales' → ②③")
    p = plan_resume_stages({"stage": "ranks"}, None)
    _check(not p.sales and not p.keywords and p.ranks, "'ranks' → ③만")


def pin_stage_assembly():
    print("[핀 P10] 단계 조립 — 순서 ①→②→③→재고 역기록·단계 기록=끝난 단계·① 단독은 기록 없음")
    calls, marks, stop = _fake_stages()
    _check(_run(StagePlan(), stop, rank_date_label=DL) == "ranks", "반환=③ 결과")
    _check(calls == ["①", "②", "③", f"③칸={DL}", "재고", "회사재고"], f"전체 순서 {calls}")
    _check(marks == ["sales", "ranks", "done"], f"단계 기록 {marks}")
    calls, marks, stop = _fake_stages()
    _check(_run(StagePlan(keywords=False, ranks=False), stop) == "snap", "① 단독 반환=① 결과")
    _check(calls == ["①"] and marks == [], "① 단독 = 판매만·단계 기록 없음")
    calls, marks, stop = _fake_stages()
    _run(StagePlan(sales=False, keywords=False, resume=True), stop)
    _check(calls == ["③", "③칸=None", "재고", "회사재고"] and marks == ["done"], "복구 'ranks' = ③(최신 칸)+역기록만")
    calls, marks, stop = _fake_stages(stop_at="①")
    _run(StagePlan(), stop)
    _check(calls == ["①"] and marks == ["sales"], "① 중 중지 → ① 끝 기록만·②③·역기록 생략")
    calls, marks, stop = _fake_stages(stop_at="③")
    _run(StagePlan(), stop)
    _check(calls[-2:] == ["재고", "회사재고"] and marks == ["sales", "ranks"], "③ 중 중지 → 역기록은 함·'done' 없음")


def main() -> int:
    print("=" * 60)
    print("  핀 테스트 — plan_run_mode 실행모드 결정 + 단계 조립(run_stages)")
    print("=" * 60)
    pin_newall()
    pin_redo_with_master()
    pin_redo_no_master()
    pin_resume()
    pin_carry_master_only()
    pin_first_run()
    pin_labels()
    pin_designated_date()
    pin_resume_plan()
    pin_stage_assembly()
    print("=" * 60)
    print("  [완료] 실행모드 핀 모두 통과")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
