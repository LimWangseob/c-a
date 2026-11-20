"""단계 조립(①판매수집 → ②키워드 선정 → ③반자동 순위 → 재고 역기록) — 단일 구현(정리 B6, 2026-10-10).

예전엔 UI(app_qt)의 전체실행(`_full_pipeline_task`)·무인(`start_auto`)·재부팅 복구(`start_resume`)가 같은 조립을
각자 따로 들고 있어 한 곳만 고치면 나머지가 갈라졌다(재개·쿨다운·단계 기록 규칙 불일치). 여기 한 곳에서 조립하고
UI 는 무엇을 할지(StagePlan)만 정한다. 게이트: `tools/pin_run_plan.py` P9~P10(가짜 단계로 호출 순서·단계 기록) · ① 미완료 즉시 재시도=simulate 8.

단계 기록(`write_run_stage`) = **실제로 끝난 단계**: ① 끝 → 'sales'(재부팅 복구는 ②부터·정산은 이 기록을 보고
받기 시작 D-021) · ② 끝 → 'ranks'(복구는 ③만) · ③을 중지 없이 끝냄 → 'done'(복구 안 함). ① 단독 실행은 기록 안 함.

실행 끝 = [실행 결과 종합](D-168 앱 쪽 · D-172 '원인 --> 결과', `run_result.RunSummary` — 예외·중지에도 찍음).
③ 빈 칸이 남으면 **재고 역기록까지 모든 처리가 끝난 뒤 ③을 1회 더**(소유자 2026-11-08) — 남으면 '순위 빈 칸 --> 확인 필요'.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .pipeline import run_full, select_keywords_stage
from .pipeline_gsheet import push_company_stock, push_ledger_inventory
from .pipeline_paths import column_label, mark_run_day, read_last_run_stage, run_day_column, run_days, write_run_stage
from .pipeline_ranks import LAST_RANK, track_ranks_stage
from . import traffic_morning
from .run_result import KEYWORDS, MORNING, RANKS, SALES, STOCK, RunSummary


@dataclass
class StagePlan:
    """무엇을 할지 — UI 가 정하고 run_stages 가 실행한다."""
    sales: bool = True          # ① 판매수집
    keywords: bool = True       # ② 키워드 선정
    ranks: bool = True          # ③ 반자동 순위 + 재고 역기록
    resume: bool = False        # ① 오늘 진행분 이어서(완료 계정 건너뜀)


def plan_resume_stages(marker: dict | None, prog: dict | None) -> StagePlan | None:
    """재부팅 복구(--resume) 계획 — 오늘 단계 기록(marker)·①진행 파일(prog)로 남은 단계만. 할 것 없으면 None.

    진행 파일 있음 = ① 중단 → ①부터 이어서 + ②③ · 기록 'sales' = ②③ · 'ranks' = ③만 · 'done'/없음 = 없음."""
    stage = marker.get("stage") if marker else None
    if not prog and stage in (None, "done"):
        return None
    do_sales = bool(prog)
    return StagePlan(sales=do_sales, keywords=do_sales or stage == "sales", ranks=True, resume=True)


def _retry_blank_ranks(ranks: dict, log, should_stop, result):
    """③ 빈 칸이 남았으면 모든 처리 끝난 뒤 빈 칸만 1회 더(소유자 11-08 D-173 · 채운 칸은 ③이 건너뜀 · 중지면 안 함).

    ③은 부를 때마다 LAST_RANK 를 새로 채운다 → 재시도분만 남아 첫 회 측정·차단이 사라지던 결함(11-08 시뮬 재현)
    → 측정·차단·연결 장애 = 첫 회 + 재시도 합산(첫 회 측정 수 따로 보관) · 빈 칸·VID 없음 = 재시도 결과."""
    left = int(LAST_RANK.get("unfilled") or 0)
    if not left or should_stop():
        return result
    first = dict(LAST_RANK)
    log.enter(RANKS, again=True)
    log(f"[단계] ③ 순위 빈 칸 {left}개 — 모든 처리 끝난 뒤 1회 재시도")
    result = track_ranks_stage(**ranks) or result
    for k in ("unfilled", "novid", "stopped"):   # 재시도가 요약 없이 끝남(워크북 못 읽음 등) → 첫 회 빈 칸 유지
        LAST_RANK.setdefault(k, first.get(k))
    for k in ("searched", "blocked", "conn"):
        LAST_RANK[k] = int(first.get(k) or 0) + int(LAST_RANK.get(k) or 0)
    LAST_RANK["first_searched"] = int(first.get("searched") or 0)
    return result


_CATCHUP_DAYS = 3   # 보충 범위 = 오늘 앞 3일(소유자 2026-11-16 T-52 답 '3일' · 처음 = Claude 제안 7일 T-47 · D-248·D-253)


def _missed_rank_days(marker: dict | None, today: date) -> list[str]:
    """③ 을 못 끝낸 지난 날들(ISO · 최근부터) — 날짜별 단계 기록(run_days)이 'sales'(① 끝)·'ranks'(② 끝)이고
    오늘 앞 _CATCHUP_DAYS 일 안. 'done'·기록 없음·오늘 기록(재부팅 복구 몫)은 빼고, 보충이 빈 칸을 남긴 날은
    'done' 이 안 찍혀 다음 실행이 다시 본다. ① 이 그날 돌아 날짜 칸이 있는 경우만 대상."""
    lo, hi = (today - timedelta(days=_CATCHUP_DAYS)).isoformat(), today.isoformat()
    return sorted((d for d, st in run_days(marker).items() if st in ("sales", "ranks") and lo <= d < hi), reverse=True)


def _catch_up_missed_ranks(missed: list[str], ranks: dict, log, should_stop, result):
    """오늘 ③·재고 역기록이 끝난 뒤 못 끝낸 지난 날 칸마다 ③ 을 1회(T-20 재발 방지 (가) 소유자 2026-11-12 · 여러 날 T-47).

    11-11 실측: ② 오류로 ③ 이 안 돌았고, 다음 날 재부팅 복구는 오늘 시작분만 이어받아(D-032) 그 칸이 빈 채로 남음.
    output (37): 이틀 연속 ③ 이 07:00 에 끊겨 앞날(11.13)이 보충 대상에서 빠짐 → 보충 범위(_CATCHUP_DAYS) 안 못 끝낸 날 전부.
    채운 칸은 ③ 이 건너뛰므로 빈 칸만 검색된다. 빈 칸 0 이면 그날 'done'. 종합의 ③ 측정 값은 오늘 실행 값을 유지하고
    보충 칸별 결과는 LAST_RANK['catchup'](빈 칸은 종합 판정·한 줄 요약에 더함)."""
    today_rank, done = dict(LAST_RANK), []
    for day in missed:
        if should_stop():
            break
        col = run_day_column(date.fromisoformat(day)).isoformat()   # 기록 열쇠 = 실행일 · 칸 = 그 전날(D-368)
        label = column_label(col)
        log.enter(RANKS)
        log(f"[단계] ③ 지난 실행({label}) 순위 칸 채우기 — {column_label(day)} 실행이 ③ 까지 못 끝냄(빈 칸만 검색)")
        result = track_ranks_stage(**{**ranks, "date_label": col}) or result
        left = int(LAST_RANK.get("unfilled") or 0)
        log(f"  [③ {label} 칸] 측정 {int(LAST_RANK.get('searched') or 0)}건 · 남은 빈 칸 {left}개")
        if "unfilled" in LAST_RANK and not left and not should_stop():
            mark_run_day(day, "done")
        done.append({"label": label, "searched": int(LAST_RANK.get("searched") or 0), "unfilled": left})
    LAST_RANK.clear()
    LAST_RANK.update(today_rank)
    if done:
        LAST_RANK["catchup"] = done
    return result


def run_stages(input_list, plan: StagePlan, *, ai_key, naver, date_from: str, date_to: str, date_label: str,
               get_password, carry: bool, redo_today: bool = False, designated: bool = False,
               grow: bool = False, rank_date_label: str | None = None, should_stop=lambda: False,
               gsheet_input_url: str = "", gsheet_output_url: str = "", registry_url: str = "",
               stock_url: str = "", on_log=print):
    """plan 대로 ①→②→③→재고 역기록. 단계 사이에서 중지 요청이면 남은 단계 생략. 반환 = ③ 결과(없으면 ① 결과).

    rank_date_label: ③이 기록할 날짜 칸(None = 최신 칸). 전체실행은 ①과 같은 칸을 넘긴다(날짜 지정·재개 라벨 일치)."""
    LAST_RANK.clear()                       # 이번 실행의 ③ 요약만 남게(③ 안 돌면 UI 가 지난 요약을 읽지 않음)
    accounts = [a.label for a in getattr(input_list, "accounts", None) or []]
    run_day = date.today()                  # 이 실행의 날짜 — 자정 넘어 끝나도 단계 기록·통합판매현황 '전일' 기준(T-47)
    missed = [] if (designated or not plan.ranks) else _missed_rank_days(read_last_run_stage(), run_day)
    with RunSummary(on_log, accounts, should_stop=should_stop, rank=LAST_RANK, sheet_url=gsheet_output_url) as log:
        result = None
        if plan.sales:                      # ① 반자동 판매수집(미완료 계정 즉시 재시도는 run_full 안에서·D-029)
            log.enter(SALES)
            result = run_full(input_list, ai_key=ai_key, date_from=date_from, date_to=date_to,
                              get_password=get_password, resume=plan.resume, carry_forward=carry,
                              redo_today=redo_today, date_label=date_label, on_log=log,
                              gsheet_output_url=gsheet_output_url, registry_url=registry_url,
                              stock_url=stock_url, designated=designated)
            if not (plan.keywords or plan.ranks):   # ① 단독 실행 → 판매데이터만 채우고 끝(단계 기록 안 함)
                return result
            write_run_stage("sales", day=run_day.isoformat(), record_day=not designated)
        if plan.keywords and not should_stop():  # ② 키워드 선정 — 노출측정 없이 AI 선정(동결분 유지·로그인 불필요)
            log.enter(KEYWORDS)
            log("[단계] ② 키워드 선정 — 노출측정 없이 AI 선정(동결분 유지)")
            select_keywords_stage(naver, ai_key, grow=grow, on_log=log, gsheet_output_url=gsheet_output_url,
                                  stock_url=stock_url)
            write_run_stage("ranks", day=run_day.isoformat(), record_day=not designated)
        if plan.ranks and not should_stop():     # ③ 반자동 순위 — 보이는 창 자동 타이핑(차단 시 쿨다운-재개)
            ranks = dict(should_stop=should_stop, on_log=log, gsheet_output_url=gsheet_output_url,
                         stock_url=stock_url, date_label=rank_date_label, run_date=run_day)
            log.enter(RANKS)
            log("[단계] ③ 반자동 순위 — 보이는 창 자동 타이핑(중지: '반자동 중지')")
            result = track_ranks_stage(**ranks)
            log.saved("통계 마스터(③ 순위 반영)", result)
            # 입력 관리대장 '그로스 재고'(AD)·회사보유재고 역기록(SA 편집권한 필요·없으면 로그 후 비치명)
            log.enter(STOCK)
            push_ledger_inventory(gsheet_input_url, log)
            push_company_stock(stock_url, gsheet_input_url, log)
            result = _retry_blank_ranks(ranks, log, should_stop, result)
            result = _catch_up_missed_ranks(missed, ranks, log, should_stop, result)
            if not should_stop():
                left = int(LAST_RANK.get("unfilled") or 0)   # 오늘 칸 빈 칸(재시도 뒤 · 쉬는 칸 제외 D-257)
                write_run_stage("done", day=run_day.isoformat(), record_day=not designated and not left)
                if left and not designated:   # 그날 못 잰 칸 = 다음 실행이 보충(D-253 3일 · 맨 위는 'done' D-257)
                    mark_run_day(run_day.isoformat(), "ranks")
        _note_morning_missed(input_list, log, designated)
        return result


def _note_morning_missed(input_list, log, designated: bool) -> None:
    """①②③ 이 23:00 뒤 끝나 그날 노출·방문자 아침 보충을 못 하게 됨 → 이 실행 종합 오류 현황에 ❌ 한 줄(D-374 보완 · 날짜 지정 제외)."""
    if not designated and traffic_morning.missed_today(datetime.now()):
        log.enter(MORNING)
        traffic_morning.note_missed(getattr(input_list, "accounts", None) or [], log=log)


__all__ = ["StagePlan", "plan_resume_stages", "run_stages"]
