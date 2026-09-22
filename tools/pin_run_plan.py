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

from coupang_analytics.pipeline import plan_run_mode, run_log_labels, run_title  # noqa: E402

DF, DT = "2026-09-21", "2026-09-22"


def _check(cond: bool, msg: str) -> None:
    print(f"    {'[통과]' if cond else '[실패]'} {msg}")
    if not cond:
        raise AssertionError(msg)


def pin_newall():
    print("[핀 P1] 통계 전체 초기화(newall) — 이어쓰기/재개 아님")
    p = plan_run_mode(newall=True, redo=False, meta={"date_from": "x", "date_to": "y", "done": [1]},
                      master=True, date_from=DF, date_to=DT)
    _check(not p.resume and not p.carry and not p.redo_today, "resume/carry/redo 모두 False")
    _check("전체 초기화" in p.mode_desc, "초기화 안내 문구")
    _check(p.date_from == DF and p.date_to == DT, "기간=기본(meta 무시)")


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
    meta = {"date_from": "2026-09-19", "date_to": "2026-09-20", "done": ["a", "b"], "carry": True}
    p = plan_run_mode(newall=False, redo=False, meta=meta, master=True, date_from=DF, date_to=DT)
    _check(p.resume and p.carry, "resume·carry True")
    _check(p.date_from == "2026-09-19" and p.date_to == "2026-09-20", "기간=meta로 덮음")
    _check("이어서 하기" in p.mode_desc and "2개" in p.mode_desc, "완료 2개 건너뜀 안내")


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
    _check(run_title(True, True) == "① 판매수집(반자동)", "①판매수집 반자동 제목")
    _check(run_title(True, False) == "① 판매수집", "①판매수집 제목")
    _check(run_title(False, True) == "전체 실행(① 반자동 로그인)", "전체실행 반자동 제목")
    _check(run_title(False, False) == "전체 실행", "전체실행 제목")
    m, s = run_log_labels(keywords_off=False, resume=True, redo_today=False, carry=True, skip_ranks=False)
    _check(m == "이어서 " and s == "", "resume=이어서·전체실행 단계표기 없음")
    m, s = run_log_labels(keywords_off=False, resume=False, redo_today=True, carry=True, skip_ranks=False)
    _check(m == "오늘다시 ", "redo_today=오늘다시")
    m, s = run_log_labels(keywords_off=False, resume=False, redo_today=False, carry=True, skip_ranks=False)
    _check(m == "통계이어쓰기 ", "carry=통계이어쓰기")
    m, s = run_log_labels(keywords_off=False, resume=False, redo_today=False, carry=False, skip_ranks=False)
    _check(m == "새통계 ", "아무것도 없음=새통계")
    m, s = run_log_labels(keywords_off=True, resume=False, redo_today=False, carry=False, skip_ranks=True)
    _check(s == " · ①판매수집(키워드·순위 없음)", "keywords_off=①판매수집 단계표기")
    m, s = run_log_labels(keywords_off=False, resume=False, redo_today=False, carry=True, skip_ranks=True)
    _check(s == " · 순위 제외(판매데이터만)", "skip_ranks(재개 아님)=순위 제외 표기")


def main() -> int:
    print("=" * 60)
    print("  핀 테스트 — plan_run_mode 실행모드 결정")
    print("=" * 60)
    pin_newall()
    pin_redo_with_master()
    pin_redo_no_master()
    pin_resume()
    pin_carry_master_only()
    pin_first_run()
    pin_labels()
    print("=" * 60)
    print("  [완료] 실행모드 핀 모두 통과")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
