"""단계 조립(①판매수집 → ②키워드 선정 → ③반자동 순위 → 재고 역기록) — 단일 구현(정리 B6, 2026-10-10).

예전엔 UI(app_qt)의 전체실행(`_full_pipeline_task`)·무인(`start_auto`)·재부팅 복구(`start_resume`)가 같은 조립을
각자 따로 들고 있어 한 곳만 고치면 나머지가 갈라졌다(재개·쿨다운·단계 기록 규칙 불일치). 여기 한 곳에서 조립하고
UI 는 무엇을 할지(StagePlan)만 정한다. 게이트: `tools/pin_run_plan.py` P9~P11(가짜 단계로 호출 순서·단계 기록).

단계 기록(`write_run_stage`) = **실제로 끝난 단계**: ① 끝 → 'sales'(재부팅 복구는 ②부터·정산은 이 기록을 보고
받기 시작 D-021) · ② 끝 → 'ranks'(복구는 ③만) · ③을 중지 없이 끝냄 → 'done'(복구 안 함). ① 단독 실행은 기록 안 함.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import config
from .pipeline import resumable_progress, run_full, select_keywords_stage
from .pipeline_gsheet import push_company_stock, push_ledger_inventory
from .pipeline_paths import write_run_stage
from .pipeline_ranks import _interruptible_sleep, track_ranks_stage


@dataclass
class StagePlan:
    """무엇을 할지 — UI 가 정하고 run_stages 가 실행한다."""
    sales: bool = True          # ① 판매수집
    keywords: bool = True       # ② 키워드 선정
    ranks: bool = True          # ③ 반자동 순위 + 재고 역기록
    resume: bool = False        # ① 오늘 진행분 이어서(완료 계정 건너뜀)
    night_resume: bool = False  # ① 뒤 미완료 계정이 남으면 쿨다운 후 1회 더(무인 — 제출 총량 억제)


def plan_resume_stages(marker: dict | None, prog: dict | None) -> StagePlan | None:
    """재부팅 복구(--resume) 계획 — 오늘 단계 기록(marker)·①진행 파일(prog)로 남은 단계만. 할 것 없으면 None.

    진행 파일 있음 = ① 중단 → ①부터 이어서 + ②③ · 기록 'sales' = ②③ · 'ranks' = ③만 · 'done'/없음 = 없음."""
    stage = marker.get("stage") if marker else None
    if not prog and stage in (None, "done"):
        return None
    do_sales = bool(prog)
    return StagePlan(sales=do_sales, keywords=do_sales or stage == "sales", ranks=True, resume=True)


def _night_resume(run_sales, should_stop, log) -> None:
    """무인 1회 쿨다운-재개 — 차단 등으로 미완료 계정이 남았으면(진행 파일 잔존) 쉬고 **남은 계정만 1회 더**
    (무한 재시도 금지 = 위탁계정 잠금 방지)."""
    if should_stop() or not config.LOGIN_NIGHT_RESUME or not resumable_progress():
        return
    mins = config.LOGIN_NIGHT_RESUME_COOLDOWN_SEC // 60
    log(f"[무인] 차단 등 미완료 계정 남음 → {mins}분 쿨다운 후 1회 재개(남은 계정만)")
    _interruptible_sleep(config.LOGIN_NIGHT_RESUME_COOLDOWN_SEC, should_stop, log, resume_label=" — 로그인 재개")
    if not should_stop():
        log("[무인] 쿨다운 종료 — 미완료 계정 로그인 재개(1회)")
        run_sales(resume=True, redo_today=False)


def run_stages(input_list, plan: StagePlan, *, ai_key, naver, date_from: str, date_to: str, date_label: str,
               get_password, carry: bool, redo_today: bool = False, designated: bool = False,
               grow: bool = False, rank_date_label: str | None = None, should_stop=lambda: False,
               gsheet_input_url: str = "", gsheet_output_url: str = "", registry_url: str = "",
               stock_url: str = "", on_log=print):
    """plan 대로 ①→②→③→재고 역기록. 단계 사이에서 중지 요청이면 남은 단계 생략. 반환 = ③ 결과(없으면 ① 결과).

    rank_date_label: ③이 기록할 날짜 칸(None = 최신 칸). 전체실행은 ①과 같은 칸을 넘긴다(날짜 지정·재개 라벨 일치)."""
    log = on_log
    result = None

    def run_sales(resume: bool, redo_today: bool):
        return run_full(input_list, ai_key=ai_key, date_from=date_from, date_to=date_to,
                        get_password=get_password, resume=resume, carry_forward=carry,
                        redo_today=redo_today, sales_semi=True, date_label=date_label, on_log=log,
                        gsheet_output_url=gsheet_output_url, registry_url=registry_url,
                        stock_url=stock_url, designated=designated)

    if plan.sales:                          # ① 반자동 판매수집 — 순위·키워드·노출측정 전무
        result = run_sales(plan.resume, redo_today)
        if plan.night_resume:
            _night_resume(run_sales, should_stop, log)
        if not (plan.keywords or plan.ranks):   # ① 단독 실행 → 판매데이터만 채우고 끝(단계 기록 안 함)
            return result
        write_run_stage("sales")
    if plan.keywords and not should_stop():  # ② 키워드 선정 — 노출측정 없이 AI 선정(동결분 유지·로그인 불필요)
        log("[단계] ② 키워드 선정 — 노출측정 없이 AI 선정(동결분 유지)")
        select_keywords_stage(naver, ai_key, grow=grow, on_log=log, gsheet_output_url=gsheet_output_url,
                              stock_url=stock_url)
        write_run_stage("ranks")
    if plan.ranks and not should_stop():     # ③ 반자동 순위 — 보이는 창 자동 타이핑(차단 시 쿨다운-재개)
        log("[단계] ③ 반자동 순위 — 보이는 창 자동 타이핑(중지: '반자동 중지')")
        result = track_ranks_stage(should_stop=should_stop, on_log=log, gsheet_output_url=gsheet_output_url,
                                   stock_url=stock_url, date_label=rank_date_label)
        # 입력 관리대장 '그로스 재고'(AD)·회사보유재고 역기록(SA 편집권한 필요·없으면 로그 후 비치명)
        push_ledger_inventory(gsheet_input_url, log)
        push_company_stock(stock_url, gsheet_input_url, log)
        if not should_stop():
            write_run_stage("done")
    return result


__all__ = ["StagePlan", "plan_resume_stages", "run_stages"]
