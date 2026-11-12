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
            "carry": True, "date_label": DL}   # 같은 날짜 칸의 진행분(다른 칸이면 이어받지 않음 — P8·D-032)
    p = plan_run_mode(newall=False, redo=False, meta=meta, master=True, date_from=DF, date_to=DT, date_label=DL)
    _check(p.resume and p.carry, "resume·carry True")
    _check(p.date_from == "2026-09-19" and p.date_to == "2026-09-20", "기간=meta로 덮음")
    _check("이어서 하기" in p.mode_desc and "2개" in p.mode_desc, "완료 2개 건너뜀 안내")
    _check(p.date_label == DL, "날짜라벨=진행분 칸 그대로")
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
    # D-032: '당일'·무인 실행도 같은 규칙 — 오늘 시작했어도 **다른 날짜 칸**의 진행분은 이어받지 않음(10-10 실측:
    # 01:05 시작 '10.09' 진행분을 18:00 무인 실행이 이어받아 10.10 칸이 안 생기고 수집도 안 됨)
    p3 = plan_run_mode(False, False, meta, True, "2026-10-10", "2026-10-10", "2026-10-11")
    _check(not p3.resume and p3.carry and p3.date_label == "2026-10-11", "당일 실행 ≠ 진행분 칸 → 오늘 칸 새로(이어받지 않음)")
    p4 = plan_run_mode(False, False, meta, True, DF, DT, "2026-10-10")
    _check(p4.resume and p4.date_label == "2026-10-10", "같은 칸 진행분이면 이어서")


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
    _st.read_last_run_stage = lambda: None   # 개발 PC output 의 실제 단계 기록을 읽지 않게(결정적 · P12 만 바꿔 넣음)
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


# ── [실행 결과 종합](D-168 앱 쪽 · D-172 '원인 --> 결과') + 순위 빈 칸 1회 재시도(소유자 11-08) ─────────────
from coupang_analytics import run_result as _rr  # noqa: E402

MASTER = Path("output") / "쿠팡데이타분석_통계.xlsx"


def _fake_result_stages(*, unfilled=(0,), searched=(5,), sales_fail=False, kw_fail=False, kw_raise=None, stop_at=None,
                        retry_empty=False):
    """가짜 단계 — ①은 LAST_SALES, ③은 LAST_RANK 를 실제처럼 채우고 로그를 남긴다(실 로그인·시트 없음).
    unfilled·searched = ③ 회차마다 값(실제 ③처럼 부를 때마다 LAST_RANK 를 새로 채움) · retry_empty = 재시도 ③이 요약 없이 끝남."""
    calls, marks, stop, seq, sseq = [], [], {"v": False}, list(unfilled), list(searched)

    def fake_run_full(_il, **kw):
        calls.append("①")
        log = kw["on_log"]
        log("  [자동입력] 실패(Timeout) — 창에서 직접 입력하세요")       # ① 도중 기록('❌' 아님) = 오류 아님
        if sales_fail:
            log("  [가-1] ❌ [상품명] 노출명 확인 실패: '상품' VID ['v1']")
        _rr.LAST_SALES.update(accounts=["가-1", "나-2", "다-3"], pw=["나-2"] if sales_fail else [],
                              missed={"다-3": "2단계 인증 필요"} if sales_fail else {},
                              ok=1 if sales_fail else 3, total=3,
                              files=[("통계 마스터", MASTER), ("그날 스냅샷", Path("output") / "snap_261108.xlsx")])
        stop["v"] = stop["v"] or stop_at == "①"
        return "snap"

    def fake_kw(*_a, **k):
        calls.append("②")
        if kw_fail:
            k["on_log"]("  [자동완성] 실패 — Timeout (이 소스만 건너뜀, 다른 소스로 계속)")
        if kw_raise:
            raise kw_raise

    def fake_track(**k):
        calls.append("③")
        n = seq.pop(0) if seq else 0
        s = sseq.pop(0) if len(sseq) > 1 else sseq[0]
        if n:
            k["on_log"]("  ❌ [순위] 가-1 · 상품 「kw」 — 검색결과가 두 바퀴 연속 안 나옴 → 공란, 확인 필요")
        _st.LAST_RANK.clear()
        if retry_empty and calls.count("③") > 1:   # 재시도 ③이 워크북을 못 읽고 끝남(요약 없음)
            return None
        _st.LAST_RANK.update(searched=s, blocked=1, conn=0, unfilled=n, novid=0, stopped=False)
        stop["v"] = stop["v"] or stop_at == "③"
        return MASTER
    _st.run_full, _st.select_keywords_stage, _st.track_ranks_stage = fake_run_full, fake_kw, fake_track
    _st.push_ledger_inventory = lambda *a: calls.append("재고")
    _st.push_company_stock = lambda *a: calls.append("회사재고")
    _st.write_run_stage = lambda s: marks.append(s)
    _st.read_last_run_stage = lambda: None   # 개발 PC output 의 실제 단계 기록을 읽지 않게(결정적 · P12 만 바꿔 넣음)
    return calls, marks, (lambda: stop["v"])


def _block(logs: list) -> list:
    i = max(i for i, m in enumerate(logs) if m == "===== [실행 결과 종합] =====")
    return logs[i:]


def pin_run_result():
    print("[핀 P11] 실행 결과 종합 — 판정 '원인 --> 결과' · 빈 칸은 모든 처리 끝난 뒤 ③ 1회 재시도 · 예외·중지에도 블록")
    logs: list = []
    calls, marks, stop = _fake_result_stages(unfilled=(2, 0), searched=(3, 2), sales_fail=True, kw_fail=True)
    run_stages(
        None, StagePlan(), ai_key="k", naver=None, date_from=DF, date_to=DT, date_label=DL, get_password=lambda a: None,
        carry=True, should_stop=stop, on_log=logs.append, gsheet_output_url="https://docs.google.com/spreadsheets/d/OUT")
    _check(calls == ["①", "②", "③", "재고", "회사재고", "③"], f"빈 칸 남음 → 재고 역기록까지 끝난 뒤 ③ 1회 재시도 {calls}")
    _check(marks == ["sales", "ranks", "done"], f"단계 기록 'done' = 재시도 뒤 {marks}")
    _check(any("[단계] ③ 순위 빈 칸 2개 — 모든 처리 끝난 뒤 1회 재시도" in m for m in logs), "재시도 안내 줄")
    b = _block(logs)
    j = " | ".join(b)
    _check(b[1] == "판정: 일부 실패 --> 확인 필요", f"판정 {b[1]}")
    _check("전체 작업 계정: 3개 — 가-1, 나-2, 다-3" in b, "계정 수·이름")
    _check("① 판매수집: 수집 성공 1/3계정" in b, "① 수집 성공 수")
    _check(any(x.startswith("비밀번호 오류로 수집 안 된 계정: 1개 — 나-2 (") and "24시간" in x for x in b), "비밀번호 오류 계정")
    _check("사람 조치 필요: 1개" in b and "  - 다-3: 2단계 인증 필요" in b, "사람 조치(2단계 인증)")
    _check("③ 순위: 측정 5건(첫 회 3 + 재시도 2) · 빈 칸 0 · VID 없음 0 · 차단감지 2회 · 모든 처리 끝난 뒤 빈 칸 1회 재시도함" in b,
           "③ 요약 = 첫 회 + 재시도 합산(측정·차단) · 빈 칸은 재시도 결과(11-08 시뮬 재현: 재시도분만 남던 결함)")
    err = j.split("오류 현황")[1].split("이번 실행에서 저장한 파일")[0]
    _check("노출명 확인 실패" in err and "자동완성] 실패" in err, "오류 현황 = ① '❌' 줄 + ② '실패' 줄")
    _check("두 바퀴 연속" not in err and "[자동입력] 실패" not in err, "재시도로 풀린 ③ 첫 회 ❌·① 도중 '실패'는 오류 아님")
    _check(f"  - 통계 마스터: {MASTER.resolve()}" in b and "  - 결과 구글시트: https://docs.google.com/spreadsheets/d/OUT" in b,
           "저장 파일 = 드라이브부터 전체 경로 + 결과 구글시트 링크(③ 같은 마스터는 한 번만)")
    _check(sum("통계 마스터" in x for x in b) == 1, "같은 파일 중복 없음")
    _check(b[-1].startswith("==> 일부 실패 --> 확인 필요 · 계정 3 · 비밀번호 오류 1 · 사람 조치 1 · 로그인 못 함 0 · 순위 빈 칸 0 · 오류 2"),
           f"한 줄 요약 {b[-1]}")
    for unfilled, judge, n3 in (((3, 3), "순위 빈 칸 --> 확인 필요", 2), ((0,), "정상 완료", 1)):
        logs = []
        calls, marks, stop = _fake_result_stages(unfilled=unfilled)
        run_stages(
            None, StagePlan(), ai_key="k", naver=None, date_from=DF, date_to=DT, date_label=DL,
            get_password=lambda a: None, carry=True, should_stop=stop, on_log=logs.append)
        _check(_block(logs)[1] == f"판정: {judge}" and calls.count("③") == n3, f"{judge} · ③ {n3}번(재시도는 1회만)")
    logs = []
    calls, marks, stop = _fake_result_stages(unfilled=(2,), stop_at="③")
    run_stages(None, StagePlan(), ai_key="k", naver=None, date_from=DF, date_to=DT, date_label=DL,
               get_password=lambda a: None, carry=True, should_stop=stop, on_log=logs.append)
    _check(calls.count("③") == 1 and _block(logs)[1] == "판정: 사람 중지 --> 중단", "중지 → 재시도 없음·'사람 중지 --> 중단'")
    logs = []
    calls, marks, stop = _fake_result_stages(kw_raise=RuntimeError("boom"))
    try:
        run_stages(None, StagePlan(), ai_key="k", naver=None, date_from=DF, date_to=DT, date_label=DL,
                   get_password=lambda a: None, carry=True, should_stop=stop, on_log=logs.append)
        raised = False
    except RuntimeError:
        raised = True
    b = _block(logs)
    _check(raised and b[1] == "판정: 오류 발생 --> 중단" and "오류 내용: RuntimeError: boom" in b,
           "예외 → 블록 찍고 예외는 그대로 올림·'오류 발생 --> 중단'")
    _check("③ 순위: 이번 실행에서 안 돎" in b, "안 돈 단계 표시")
    logs = []
    calls, marks, stop = _fake_result_stages(unfilled=(2,), searched=(3,), retry_empty=True)
    run_stages(None, StagePlan(), ai_key="k", naver=None, date_from=DF, date_to=DT, date_label=DL,
               get_password=lambda a: None, carry=True, should_stop=stop, on_log=logs.append)
    b = _block(logs)
    _check(b[1] == "판정: 순위 빈 칸 --> 확인 필요" and any("측정 3건(첫 회 3 + 재시도 0) · 빈 칸 2" in x for x in b),
           f"재시도 ③이 요약 없이 끝나도 첫 회 빈 칸 유지(정상 완료로 오판 안 함) {b[1]}")
    logs = []
    calls, marks, stop = _fake_result_stages()
    run_stages(None, StagePlan(keywords=False, ranks=False), ai_key="k", naver=None, date_from=DF, date_to=DT,
               date_label=DL, get_password=lambda a: None, carry=True, should_stop=stop, on_log=logs.append)
    _check(_block(logs)[1] == "판정: 정상 완료" and calls == ["①"], "① 단독 실행도 블록")


def pin_yesterday_rank_catchup():
    print("[핀 P12] 직전 실행이 어제 ③ 을 못 끝냄(단계 기록 어제 'sales'·'ranks') → 오늘 ③ 뒤 어제 칸 ③ 1회 (T-20 재발 방지 (가))")
    from datetime import date, timedelta
    y = (date.today() - timedelta(days=1)).isoformat()
    orig = _st.read_last_run_stage

    def run(marker, plan=None, designated=False):
        calls, marks, stop = _fake_result_stages()
        labels: list = []
        track = _st.track_ranks_stage

        def rec(**k):
            labels.append(k.get("date_label"))
            return track(**k)
        _st.track_ranks_stage = rec
        _st.read_last_run_stage = lambda: marker
        logs: list = []
        run_stages(None, plan or StagePlan(), ai_key="k", naver=None, date_from=DF, date_to=DT, date_label=DL,
                   get_password=lambda a: None, carry=True, designated=designated, should_stop=stop,
                   on_log=logs.append)
        return calls, marks, labels, logs
    try:
        for stage in ("sales", "ranks"):
            calls, marks, labels, logs = run({"date": y, "stage": stage})
            _check(calls == ["①", "②", "③", "재고", "회사재고", "③"] and labels[-1] == y,
                   f"어제 '{stage}' → 오늘 ③·재고 뒤 어제 칸({y}) ③ 1회 {calls} {labels}")
            _check(any("지난 실행" in m and "③" in m and y[5:].replace("-", ".") in m for m in logs), "지난 실행 칸 채우기 안내 줄(칸 이름 포함)")
            _check(marks[-1] == "done", f"단계 기록 끝 = done {marks}")
        for marker, why in (({"date": y, "stage": "done"}, "어제 done"), (None, "기록 없음"),
                            ({"date": date.today().isoformat(), "stage": "sales"}, "오늘 기록(재부팅 복구 몫)")):
            calls, _, labels, _ = run(marker)
            _check(calls.count("③") == 1, f"{why} → 어제 칸 채우기 없음 {calls}")
        calls, _, _, _ = run({"date": y, "stage": "sales"}, designated=True)
        _check(calls.count("③") == 1, f"날짜 지정 실행 → 어제 칸 채우기 없음 {calls}")
        calls, _, _, _ = run({"date": y, "stage": "sales"}, plan=StagePlan(keywords=False, ranks=False))
        _check("③" not in calls, f"① 단독 → ③ 없음 {calls}")
    finally:
        _st.read_last_run_stage = orig

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
    pin_run_result()
    pin_yesterday_rank_catchup()
    print("=" * 60)
    print("  [완료] 실행모드 핀 모두 통과")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
