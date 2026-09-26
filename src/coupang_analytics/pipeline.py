"""전체 실행 오케스트레이션(`run_full`) — **계정별로 처음부터 끝까지 완결 + 이어서 하기 지원**.

계정마다 [로그인(방금 연 세션) → 판매분석 발견·지표 → 키워드 → 순위]를 완결하고 다음 계정으로.
결과는 통합 워크북 1개에 누적하고, 진행 중엔 `쿠팡데이타분석_진행중.xlsx`(+`.json` 상태)에
저장하며, 전부 끝나면 날짜·시각이 붙은 최종본으로 이름을 바꾼다. 이어서 할 때는 완료 계정을
건너뛰고, 미완료 계정은 키워드 재사용 + 이미 조회한 순위 건너뛰기로 끊긴 지점부터 이어간다.
순위 조회는 부하가 크므로 순차로 지연을 두며, 차단되면 공란 처리하고 계속 진행한다.
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import config
from .browser import WingBrowser
from .input_list import Account, InputList, InputValidationError, validate_input_list
from .kw_ai import KeywordAIError
from .kw_recommend import select_keywords_light
from .kw_volume import NaverAdApi
from .rank import warmup   # 대부분 pipeline_ranks 로 이동(키워드-스테이지의 warmup 만 core 사용)
from .workbook import OutputWorkbook

# 경로/단계 헬퍼·상수는 leaf 모듈 pipeline_paths 로 분리(순환 import 방지). 여기서 다시 import 해
# `pipeline.X` 공개 API(UI·도구·핀)를 그대로 유지한다.
from .pipeline_paths import (  # noqa: E402
    _PROFILE, _load_latest_wb, _master_path, _partial_path,
    _progress_path, _snapshot_path)
# 재수출(UI·스케줄러·도구가 pipeline.X 로 쓰는 공개 API) — pipeline 내부 미사용이라 noqa.
from .pipeline_paths import master_exists, read_run_stage, write_run_stage  # noqa: E402,F401
# 구글시트 연동·백업·복원은 pipeline_gsheet 로 분리(대형 파일 정비). pipeline.X 로 다시 노출.
from .pipeline_gsheet import (  # noqa: E402,F401
    _pull_gsheet_keywords, _push_gsheet, backup_sources,
    push_ledger_inventory, restore_master_from_gsheet)
# ③ 순위(측정·서킷브레이커·자동/반자동 검색·스테이지)는 pipeline_ranks 로 분리. pipeline.X 로 다시 노출
# (핀/시뮬 monkeypatch 대상은 pipeline_ranks). core(_fill_product_metrics·_finalize_run)가 _best/
# _measure_safe/_reset_rank_state/_RANK_HALT 를 호출하므로 재수출 필요.
# ① 판매수집 엔진(로그인·발견·계정처리)은 pipeline_sales 로 분리. pipeline.X 로 다시 노출
# (run_full 이 _login_and_discover·_process_account 호출·NeedLogin류 catch·도구/핀이 여러 심볼 import).
from .pipeline_sales import (  # noqa: E402,F401
    LoginBlocked, LoginCredentialError, NeedLogin, _augment_vids, _discover_inventory,
    _discover_products, _dump_raw, _ensure_login, _fresh_login, _ilog, _log_discover_summary,
    _login_and_discover, _persist_session, _pid_by_vid, _resolve_login_failure,
    _roster_from_names, _run_discover, _semi_retry_login, _short, _vtag, account_profile)
# 상품/옵션 처리(_process_account 등)는 pipeline_process 로 분리. pipeline.X 로 다시 노출
# (run_full._finish 가 _process_account 호출·도구가 _ProcCtx/_resolve_keywords/_fill_product_metrics 등 import).
from .pipeline_process import (  # noqa: E402,F401
    _ProcCtx, _apply_pid, _apply_vid_meta, _block_name, _block_sale_status,
    _fill_frozen_search_volumes, _fill_product_metrics, _frozen_keywords, _log_diagnose,
    _migrate_product_blocks, _process_account, _process_option, _product_matcher,
    _purge_upbundle_blocks, _resolve_keywords, _sweep_dead_duplicates)
from .pipeline_ranks import (  # noqa: E402,F401
    RankHalt, _RANK_CB, _RANK_HALT, _RANK_TELEMETRY_ID, _all_pages, _best,
    _interruptible_sleep, _live_url, _looks_blocked, _measure,
    _measure_nav_serial, _measure_product_auto, _measure_safe,
    _prefill_search, _rank_cooldown, _rank_matcher, _reset_rank_state, _search_q,
    _semi_browser_prep, _semi_on_miss, _semi_prep_product, _semi_record, _semi_search_one,
    _semi_start_log, _semi_summary_log, _semi_track_product, _submit_search, _track_ranks_semi,
    _wait_results_loaded, _wait_user_search, track_ranks_stage)


def resumable_progress(out_dir: str | Path = "output") -> dict | None:
    """이어서 할 수 있는 진행 상태가 있으면 그 메타(dict)를, 없으면 None 반환.

    반환 예: {"date_from","date_to","started_at","done":[계정ID...]}. UI 팝업 문구에 사용.
    진행 엑셀과 상태파일이 **둘 다** 있어야 재개 가능으로 본다.
    """
    meta_path, xlsx_path = _progress_path(out_dir), _partial_path(out_dir)
    if not (meta_path.exists() and xlsx_path.exists()):
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(meta.get("done"), list):
        return None
    # 날짜 변경 시 처음부터 — 진행분이 **오늘 시작한 것**일 때만 재개 대상으로 인정한다.
    # (started_at 의 달력 날짜 != 오늘 → 어제 이전의 미완료 잔재이므로 이어쓰지 않고 새로 시작하게 None 반환.)
    started = str(meta.get("started_at", ""))[:10]   # 'YYYY-MM-DD'
    if started and started != datetime.now().strftime("%Y-%m-%d"):
        return None
    return meta


@dataclass
class RunPlan:
    """전체실행/판매수집 실행모드 결정 결과 — 플래그 + (재개면 덮은) 기간·날짜라벨 + 사용자 확인용 문구."""
    resume: bool
    carry: bool
    redo_today: bool
    date_from: str
    date_to: str
    mode_desc: str
    date_label: str


def plan_run_mode(newall: bool, redo: bool, meta: dict | None, master: bool,
                  date_from: str, date_to: str, date_label: str = "") -> RunPlan:
    """실행모드 결정(순수·오프라인 검증 가능) — app_qt/app.do_run_full 의 if/elif 사슬을 백엔드로 공통화.

    입력: newall(통계 전체 새로)·redo(오늘 것만 다시)·meta(resumable_progress 결과|None)·
    master(master_exists())·date_from/to(기본 기간)·date_label(기본 날짜라벨). 반환 RunPlan:
    resume/carry/redo_today 플래그 + (meta 있으면 그 기간으로 덮은) date_from/to + 확인 팝업용 mode_desc +
    (재개면 meta 의 date_label 로 복원한) date_label. ⚠ grow 는 UI마다 달라 여기서 안 다룬다.
    **date_label 복원은 양쪽 UI 공통**(예전엔 app.py 만 처리해 app_qt 재개 시 오늘 컬럼으로 어긋나는 버그)."""
    resume = carry = redo_today = False
    if newall:
        mode_desc = "통계 전체 초기화(백업 후) — ⚠ 기존 통계 마스터는 백업 후 빈 통계로 새로(누적 시계열 끊김)"
    elif redo:
        if master:
            carry = redo_today = True
            mode_desc = f"오늘 것만 다시 수집 — 오늘({date_to}) 초기화 후 전 계정 재수집(어제까지 유지·키워드 동결)"
        else:
            mode_desc = f"새 통계 시작(첫 실행 — 마스터 없음·구글시트 복원 불가), 기간 {date_from}~{date_to}"
    elif meta:
        resume = True
        carry = bool(meta.get("carry", False))
        date_from, date_to = meta["date_from"], meta["date_to"]
        date_label = meta.get("date_label") or date_label   # 재개 시 시작일 기준 라벨 고정(양쪽 UI 공통)
        mode_desc = f"이어서 하기 — 오늘 미완료분 이어서(완료 {len(meta['done'])}개 건너뜀), 기간 {date_from}~{date_to}"
    elif master:
        carry = True
        mode_desc = f"이어서 하기 — 오늘({date_to}) 컬럼 추가(키워드 동결)"
    else:
        mode_desc = f"새 통계 시작(첫 실행 — 마스터 없음·구글시트 복원 불가), 기간 {date_from}~{date_to}"
    return RunPlan(resume, carry, redo_today, date_from, date_to, mode_desc, date_label)


def run_title(keywords_off: bool, sales_semi: bool) -> str:
    """확인 팝업/로그 제목(순수) — app_qt/app.do_run_full 공통. ①판매수집 vs 전체실행 × 반자동 여부."""
    return (("① 판매수집(반자동)" if sales_semi else "① 판매수집") if keywords_off
            else ("전체 실행(① 반자동 로그인)" if sales_semi else "전체 실행"))


def run_log_labels(keywords_off: bool, resume: bool, redo_today: bool, carry: bool,
                   skip_ranks: bool) -> tuple[str, str]:
    """실행 로그용 (모드표기, 단계표기) 문자열(순수) — app_qt/app.do_run_full 공통(중복 제거).

    mode_txt=이어서/오늘다시/이어쓰기/새통계, stage_txt=①판매수집 단독 or 순위 제외 표기. 제어흐름은
    분해 전 두 UI 의 ternary 와 완전히 동일(행동 불변)."""
    mode_txt = ("오늘다시 " if redo_today else "이어서 ") if (resume or redo_today) else \
               ("통계이어쓰기 " if carry else "새통계 ")
    stage_txt = " · ①판매수집(키워드·순위 없음)" if keywords_off else \
        (" · 순위 제외(판매데이터만)" if skip_ranks and not resume else "")
    return mode_txt, stage_txt


def _save_progress(out_dir, date_from, date_to, started_at, done,
                   carry=False, grow=False, skip=False, date_label=None) -> None:
    _progress_path(out_dir).write_text(
        json.dumps({"date_from": date_from, "date_to": date_to, "started_at": started_at,
                    "done": list(done), "carry": carry, "grow": grow, "skip": skip,
                    "date_label": date_label},   # 컬럼 라벨=작업 실행날짜(판매조회 D-1과 분리) — 재개 시 동일 라벨 유지
                   ensure_ascii=False, indent=2),
        encoding="utf-8")


def _select_keywords_for_skipped(wb, save_path, accounts, naver, ai_key, log) -> None:
    """판매수집을 건너뛴(이미 오늘 수집됨) 계정의 상품 중 **키워드가 비어 있는 것만** 선정(로그인 없이).

    전체실행 재실행에서 판매는 스킵하되 ②키워드가 빠지지 않게 하는 보완 단계. 기존 키워드가 있는 상품은
    **동결**(건드리지 않음). select_keywords_stage(②)와 동일 로직(워크북 상품명 시드, 순위 조회 없음).
    로그인 브라우저는 이미 닫혔으므로 순위 브라우저 1개만 연다(중첩 금지 준수)."""
    biz_names = {a.label for a in accounts}
    targets = [(biz, pname) for biz in wb.account_sheets() if biz in biz_names
               for pname in wb.products_of(biz) if not wb.product_keywords(biz, pname)]
    if not targets:
        return
    log(f"== 판매수집 스킵 계정의 키워드 미보유 상품 {len(targets)}개 선정(로그인 없이) ==")
    with WingBrowser(profile_dir=_PROFILE, offscreen=True) as browser:
        warmup(browser)
        for biz, pname in targets:
            try:
                tracks = select_keywords_light(pname, naver, ai_key, browser=browser, log=log,
                                               measure_ranks=None)
                wb.add_product_keywords(biz, pname, [t.keyword for t in tracks])
                for t in tracks:
                    wb.set_keyword_search(biz, pname, t.keyword, t.volume)
                log(f"  [키워드] {biz} · {pname} → {[t.keyword for t in tracks]}")
            except Exception as exc:   # 한 상품 실패가 나머지·순위보완을 안 막게 격리
                log(f"  [키워드] {biz} · {pname} 선정 실패(건너뜀) — {exc.__class__.__name__}: {str(exc)[:80]}")
        wb.save(save_path)


def _column_label(date_from: str, date_to: str, date_label: str | None, log) -> str:
    """일자 컬럼 제목 = 작업 실행날짜(date_label)의 년도 없는 '월.일'. SSOT=designs/DESIGN.md §일자 컬럼.

    판매데이터는 전일(D-1=date_from~date_to)에서 오지만 컬럼 제목은 실제 작업한 날로 적는다(새벽 넘겨도
    시작일 기준). date_label 없으면 date_to 폴백, 기간지정이면 'from~to'. 라벨≠판매조회일이면 둘 다 안내.
    """
    label_src = date_label or date_to
    if date_from == date_to or date_label:
        try:
            col_label = datetime.strptime(label_src, "%Y-%m-%d").strftime("%m.%d")   # 년도 없는 '월.일'
        except ValueError:
            col_label = label_src
    else:
        col_label = f"{date_from}~{date_to}"
    if date_label and date_label != date_to:   # 라벨(실행일)과 판매조회일(전일)이 다르면 둘 다 안내
        log(f"== 컬럼(작업 실행날짜): {col_label} · 판매조회 {date_from}~{date_to}(전일) ==")
    else:
        log(f"== 수집 대상 구간(컬럼): {col_label} ==")
    return col_label


def preflight_sync_check(wb, input_list: InputList, log) -> dict:
    """작업 시작 전 **관리대장↔결과 대조**(비변경 진단, 항목②③ 소유자 2026-09-25).

    실제 정리(일원화 ⑤·삭제 ⑥·판매중지 ⑦)를 하기 **전에**, 관리대장과 결과 워크북의 불일치를 `[SYNC]` 로그로
    미리 보여준다(담당자가 무엇이 바뀔지 예고받음). 아무것도 바꾸지 않는다(읽기 전용). 반환=집계 dict(테스트용).

    검사: ①대장 O/결과 X(신규·미수집) ②결과 O/대장 X(삭제 예정 ⑥) ③사업자명 변경(계정ID 동일·시트명≠대장,
    일원화 예정 ⑤) ④취소선 제외(관리대장에서 뺀 항목). 불일치 판정 기준 = **관리대장**(소유자 결정)."""
    summary = _preflight_summary(wb, input_list)
    _log_preflight(log, summary)
    return summary


def _preflight_summary(wb, input_list: InputList) -> dict:
    """관리대장↔결과 불일치 집계(읽기 전용) — 신규/삭제예정/이름변경/취소선."""
    led_biz = {a.account_id: a.label for a in input_list.accounts if a.account_id}
    led_ids = input_list.ledger_account_ids or set(led_biz)
    res: dict[str, str] = {}                       # 결과 워크북의 계정ID → 사업자 시트명
    for biz in wb.account_sheets():
        for aid in (wb.account_ids_of(biz) or []):
            res.setdefault(aid, biz)
    new_ids = sorted(a for a in led_ids if a and a not in res)                  # 대장 O / 결과 X
    gone_ids = sorted(a for a in res if led_ids and a not in led_ids)           # 결과 O / 대장 X(삭제 예정)
    renamed = sorted((res[a], led_biz[a], a) for a in res                       # 사업자명 변경(일원화 예정)
                     if a in led_biz and res[a].strip() != (led_biz[a] or "").strip())
    return {"new": new_ids, "gone": gone_ids, "renamed": renamed, "struck": list(input_list.struck)}


def _log_preflight(log, summary: dict) -> None:
    """preflight 집계를 [SYNC] 로그로 출력(읽기 전용·아무것도 안 바꿈)."""
    new_ids, gone_ids = summary["new"], summary["gone"]
    renamed, struck = summary["renamed"], summary["struck"]
    if not (new_ids or gone_ids or renamed or struck):
        log("== [SYNC] 관리대장↔결과 일치(신규·삭제·이름변경·취소선 없음) ==")
        return
    log(f"== [SYNC] 관리대장↔결과 대조: 신규 {len(new_ids)}·삭제예정 {len(gone_ids)}·"
        f"이름변경 {len(renamed)}·취소선 {len(struck)} (실제 정리는 수집 후) ==")
    if new_ids:
        log(f"  [SYNC] 대장O·결과X(신규/미수집) {len(new_ids)}: {new_ids[:8]}{'…' if len(new_ids) > 8 else ''}")
    if gone_ids:
        log(f"  [SYNC] 결과O·대장X(삭제 예정, 관리대장 기준) {len(gone_ids)}: "
            f"{gone_ids[:8]}{'…' if len(gone_ids) > 8 else ''}")
    for old_biz, new_biz, aid in renamed[:8]:
        log(f"  [SYNC] 사업자명 변경(일원화 예정): '{old_biz}' → '{new_biz}' (계정ID {aid})")
    if struck:
        log(f"  [SYNC] 관리대장 취소선 제외 {len(struck)}: {struck[:5]}{'…' if len(struck) > 5 else ''}")


def _consolidate_renamed_accounts(wb, input_list: InputList, log) -> list[tuple[str, str]]:
    """시트명 변경으로 같은 계정ID가 둘로 쪼개진 경우 일원화(2026-09-25).

    관리대장은 담당자가 사업자명·대표자를 수시로 바꿔, 계정ID는 그대로인데 옛 시트명이 고아(전 상품 판매중지로
    오분류)가 된다(예: 이종훈→원더폴리). 대장의 (계정ID → 현재 사업자명) 을 기준으로, 같은 계정ID인데 다른
    이름을 가진 옛 시트를 현재 이름 시트로 **이력 보존하며 병합**한다. 삭제 판정보다 **먼저** 돌려, 옛 시트가
    '판매중지'로 오분류되기 전에 흡수한다. 반환 = 병합으로 사라진 **옛 이름** 목록 [(옛사업자명, 계정ID)…]
    (구글시트 계정목록 행·옛 통계 시트를 이름 기준으로 정리하는 데 쓴다 — 계정ID는 새 이름과 공유하므로 이름 매칭)."""
    target_of = {a.account_id: a.label for a in input_list.accounts if a.account_id and a.label}
    if not target_of:
        return []
    renamed: list[tuple[str, str]] = []
    for biz in list(wb.account_sheets()):
        # 항목5: 한 시트에 계정ID가 여럿일 수 있다(다계정ID). 대장에 있는 계정ID들의 현재 사업자명(target)을 모은다.
        sheet_aids = wb.account_ids_of(biz) or ([wb.account_id_of(biz)] if wb.account_id_of(biz) else [])
        ledger_aids = [a for a in sheet_aids if a in target_of]
        targets = {target_of[a] for a in ledger_aids}
        if not targets:
            continue                                       # 대장에 없는 계정(들) → 삭제 판정에 맡김
        if len(targets) > 1:                               # 다계정ID 사업자가 서로 다른 이름으로 발산 → 자동 병합 위험
            log(f"== [SYNC] [{biz}] 다계정ID가 서로 다른 사업자명으로 갈림({sorted(targets)}) — "
                "자동 일원화 보류(수동 확인 필요) ==")
            continue
        target = next(iter(targets))
        if target.strip() == (biz or "").strip():
            continue                                       # 이미 현재 이름
        moved = wb.merge_account(biz, target)
        if moved:
            for a in ledger_aids:                          # 옛 이름 잔재 = (옛사업자명, 각 계정ID) 전부(구글시트 정리)
                renamed.append((biz, a))
            log(f"== [{biz}] → [{target}] 일원화(계정ID {ledger_aids} 동일·시트명 변경) — 상품 {moved}개 이력 이관 ==")
    return renamed


def _reconcile_ledger_accounts(wb, input_list: InputList, uncollected, log
                               ) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """계정 단위 대조(2026-09-17 정책) — 관리대장 기준으로 결과 워크북의 계정을 정리한다.

    - 시트명 변경(계정ID 동일)으로 쪼개진 계정 = **일원화**(먼저, 옛 이름 흡수).
    - 대장에서 **줄이 완전히 사라진 계정 = 완전 삭제**(시트·이력·메타).
    - 대장에 **줄은 남았으나 비활성**(전 상품 판매중지 등) = 판매중지 표기(유지·경고 기능).
    - 로그인 실패(uncollected)는 '사라짐' 아님 → 제외(다음에 수집).
    삭제 판정 = 계정ID가 대장에 아예 없음.
    반환 = (완전 삭제한 [(사업자, 계정ID)…], 일원화로 사라진 옛 이름 [(옛사업자명, 계정ID)…]).
    """
    renamed = _consolidate_renamed_accounts(wb, input_list, log)  # 시트명 변경 계정 먼저 흡수(고아 오분류 방지)
    active_biz = {a.label for a in input_list.accounts}
    active_ids = input_list.ledger_account_ids            # 대장에 줄이 존재하는 계정ID(판매중지 포함)
    uncollected_biz = {a.label for a in uncollected}
    removed_accounts: list[tuple[str, str]] = []          # (사업자, 계정ID) — 결과에서 완전 삭제한 계정
    for biz in list(wb.account_sheets()):
        if biz in active_biz or biz in uncollected_biz:
            continue                                       # 활성(수집대상)·로그인 실패는 삭제/중지 대상 아님
        aid = wb.account_id_of(biz)
        if active_ids and aid and aid not in active_ids:   # 대장에 줄이 아예 없음 → 완전 삭제
            if wb.delete_account(biz):
                removed_accounts.append((biz, aid))
                log(f"== [{biz}] 관리대장에서 삭제됨(줄 사라짐) → 결과 완전 삭제(시트·이력·메타) ==")
        else:                                              # 대장에 남아있으나 비활성 → 판매중지(유지·경고, 삭제 안 함)
            gone, _del = wb.reconcile_account(biz, [])       # delete_missing=False(기본): 줄 존재=유지
            if gone:
                log(f"== [{biz}] 대장에 남았으나 비활성 → 상품 {len(gone)}개 판매중지 표기 ==")
    return removed_accounts, renamed


@dataclass
class _RunCtx:
    """run_full 한 번의 공유 실행 상태(계정별 기록·진행 저장에 필요한 것). 설정 후 불변으로 다룬다."""
    wb: OutputWorkbook
    out: Path
    partial: Path
    date_from: str
    date_to: str
    date_label: str | None
    started_at: str
    done: set                 # 완료 계정ID(가변 — 계정마다 add)
    carry: bool
    grow: bool
    skip_ranks: bool
    keywords_off: bool
    col_label: str
    total: int
    naver: NaverAdApi
    ai_key: str | None
    log: object


def _save_ctx_progress(ctx: _RunCtx) -> None:
    """실행 컨텍스트로 진행 상태 저장(_실행단계 진행파일). 9인자 호출 반복을 한 곳으로."""
    _save_progress(ctx.out, ctx.date_from, ctx.date_to, ctx.started_at, ctx.done,
                   ctx.carry, ctx.grow, ctx.skip_ranks, ctx.date_label)


def _finish(ctx: _RunCtx, a: Account, report_acc, metrics, inv_by_vid, inv_status=None,
            upbundle_vids=None, live_vids=None, vid_meta=None, pid_by_vid=None) -> None:
    """발견 결과를 워크북에 기록 + 진행 저장(1·2차 패스 공통). report_acc=None이면 무동작.

    upbundle_vids = 이번 상품조회의 업번들 vid 집합 → 마스터 잔재 업번들 블록 자동삭제.
    live_vids = 이번 상품조회 전체 vid 집합 → 죽은 중복 블록 정리 기준(_process_account)."""
    wb, log = ctx.wb, ctx.log
    if report_acc is None:      # 로그인 미완료/데이터 없음 → 다음 계정(전체 안 막힘)
        return
    wb.set_account_id(a.label, a.account_id)   # 목차 계정ID 표시용(비번은 저장 안 함)
    wb.set_representative(a.label, a.representative)   # 계정목록 대표자 컬럼(관리대장 대표자명)
    # 자동완성(키워드 후보)·순위 모두 비로그인 쿠팡 세션이 필요하다. 로그인 브라우저가 닫힌 뒤 별도로
    # 연다(중첩 금지 — sync playwright 충돌 방지). 활동 상품이 있을 때만 열고, 그 한 세션에서
    # 키워드 선정(자동완성)→순위까지 재사용한다(warmup 먼저 = 쿠팡 오리진 로드, same-origin fetch).
    if report_acc.products:
        if ctx.skip_ranks or ctx.keywords_off:
            # 순위 제외(날짜지정) 또는 판매수집 전용(①): 쿠팡 순위 브라우저 안 열고(차단 접촉 0)
            _process_account(report_acc, wb, ctx.naver, ctx.ai_key, None, metrics, inv_by_vid,
                             ctx.col_label, ctx.grow, log, ctx.partial, skip_ranks=ctx.skip_ranks,
                             keywords_off=ctx.keywords_off, sale_status=inv_status,
                             upbundle_vids=upbundle_vids, live_vids=live_vids, vid_meta=vid_meta,
                             pid_by_vid=pid_by_vid)
        else:
            with WingBrowser(profile_dir=_PROFILE, offscreen=True) as rank_browser:
                warmup(rank_browser)
                _process_account(report_acc, wb, ctx.naver, ctx.ai_key, rank_browser, metrics,
                                 inv_by_vid, ctx.col_label, ctx.grow, log, ctx.partial,
                                 sale_status=inv_status, upbundle_vids=upbundle_vids, live_vids=live_vids,
                                 vid_meta=vid_meta, pid_by_vid=pid_by_vid)
        # 판매상태 불일치 경고: 쿠팡 재고 판매상태맵을 마스터 전체 상품에 vid로 대조해 저장(멱등).
        # 대장에서 빠진(판매중지 표기) 상품도 쿠팡 재고에 살아있으면 vid로 잡혀 "판매중"으로 채워진다.
        # 상태맵은 ①판매수집 로그인 세션에서만 확보되므로(②③엔 없음) 여기서 1회 반영, 렌더는 apply_style이 담당.
        if inv_status:
            n_flag = wb.apply_sale_status(a.label, inv_status)
            if n_flag:
                log(f"  [{a.label}] 쿠팡 판매상태 {n_flag}개 상품 반영(대장=판매중지·쿠팡=판매중이면 경고 표시)")
    else:                                        # 대장 상품 0개 → Chrome 개방 생략, 시트도 생략
        log(f"  [{a.label}] 대장 상품 0개 — 시트·키워드·순위 생략")
    wb.mark_sales_collected(a.account_id, ctx.col_label)   # 오늘 판매수집 완료 스탬프(계정 단위·항목5, 같은 날 재실행 시 생략 근거)
    ctx.done.add(a.account_id)                    # 이 계정 완료 확정
    _save_ctx_progress(ctx)
    wb.save(ctx.partial)
    log(f"  [{a.label}] 완료 — 진행 {len(ctx.done)}/{ctx.total} (진행 저장: {ctx.partial.name})")


def _collect_session_first(ctx: _RunCtx, accounts, get_password
                           ) -> tuple[list[tuple[int, Account]], list[Account]]:
    """1차 패스 — 세션 살아있는 계정 먼저 수집(로그인 없음 → 차단 위험 0). 세션 만료는 로그인 대기열로.

    반복 자동로그인이 Akamai IP 차단을 유발하므로, 로그인 없는 계정을 먼저 다 확보한다.
    반환: (로그인 필요 [(순번, Account)], 오늘 판매수집 이미 완료라 생략한 계정[키워드 보완 대상]).
    """
    wb, log, done, total, col_label = ctx.wb, ctx.log, ctx.done, ctx.total, ctx.col_label
    login_needed: list[tuple[int, Account]] = []
    sales_skipped: list[Account] = []
    for i, a in enumerate(accounts, 1):
        if a.account_id in done:                  # 완료 계정 → 건너뜀
            log(f"== [{i}/{total}] {a.label} — 이미 완료, 건너뜀 ==")
            continue
        if wb.has_sales(a.account_id, col_label):  # 오늘 판매수집 이미 완료(계정 단위 스탬프·항목5) → 로그인·수집 생략(재실행)
            log(f"== [{i}/{total}] {a.label} — 오늘({col_label}) 판매수집 완료됨 → 로그인·수집 생략(재실행). "
                "키워드는 미보유분만 보완·순위는 미기입분만 조회 ==")
            done.add(a.account_id)
            _save_ctx_progress(ctx)
            sales_skipped.append(a)
            continue
        if ctx.carry and wb.has_marketing():      # 마케팅 설정됐을 때만 주기 게이팅(미설정=현행 매일 유지)
            due, why = wb.account_due(a.label, ctx.date_to, a.account_id)   # 항목5: 그 계정ID 상품만으로 판정
            if not due:
                log(f"== [{i}/{total}] {a.label} — {why} → 오늘 수집 안 함(로그인 생략) ==")
                done.add(a.account_id)            # 오늘은 의도적 스킵으로 '처리됨'(완주 판정·재개 일관)
                _save_ctx_progress(ctx)
                continue
        log(f"== [{i}/{total}] {a.label} (계정ID: {a.account_id}) ==")
        try:   # 한 계정의 어떤 오류(수집·워크북쓰기)도 전체를 막지 않게 계정 전체를 격리
            (report_acc, metrics, inv_by_vid, inv_status, upbundle_vids, live_vids,
             vid_meta, pid_by_vid) = _login_and_discover(
                a, ctx.date_from, ctx.date_to, get_password, log, login=False)
            _finish(ctx, a, report_acc, metrics, inv_by_vid, inv_status, upbundle_vids, live_vids,
                    vid_meta, pid_by_vid)
        except NeedLogin:                         # 세션 없음 → 뒤로 미룸(자동제출 안 함)
            login_needed.append((i, a))
            log(f"  [{a.label}] 세션 만료 → 로그인 대기열(세션 있는 계정 먼저 수집 후 처리)")
        except Exception as exc:
            first = (str(exc).splitlines() or [""])[0][:250]
            log(f"  [{a.label}] 처리 오류: {exc.__class__.__name__}: {first} — 건너뜀")
    return login_needed, sales_skipped


def _collect_with_login(ctx: _RunCtx, login_needed, get_password, sales_semi: bool) -> None:
    """2차 패스 — 로그인 필요 계정 처리. 서킷브레이커(연속 Akamai 차단 K회면 이후 로그인 생략)·
    로그인 사이 사람 간격(몰아치기=IP 플래그 방지)·비번오류는 재시도 금지(계정잠금 방지)."""
    log, done, total = ctx.log, ctx.done, ctx.total
    if login_needed:
        log(f"== 로그인 필요 계정 {len(login_needed)}개 처리(세션우선 수집 완료) ==")
    blocks = 0
    attempted = 0
    for i, a in login_needed:
        if blocks >= config.LOGIN_BLOCK_CIRCUIT:  # IP가 이미 플래그됨 → 더 두드리지 않음(더 태우기 방지)
            log(f"== [{i}/{total}] {a.label} — Akamai 차단 지속(연속 {blocks}회)으로 로그인 생략 "
                "→ 잠시 후/내일(쉰 IP) 이어서 수집 ==")
            continue
        if attempted > 0:   # 로그인 사이에 사람 간격(몰아치기=IP 플래그 방지). 첫 로그인엔 대기 없음
            pace = random.uniform(config.LOGIN_PACE_MIN_SEC, config.LOGIN_PACE_MAX_SEC)
            if pace > 0:
                log(f"  [페이싱] 다음 로그인까지 {pace:.0f}s 대기(로그인 몰아치기=차단 회피)")
                time.sleep(pace)
        attempted += 1
        log(f"== [{i}/{total}] {a.label} (계정ID: {a.account_id}) — 로그인 시도 ==")
        try:
            (report_acc, metrics, inv_by_vid, inv_status, upbundle_vids, live_vids,
             vid_meta, pid_by_vid) = _login_and_discover(
                a, ctx.date_from, ctx.date_to, get_password, log, login=True, semi=sales_semi)
            blocks = 0                            # 로그인 성공 → 연속 차단 카운터 리셋
            _finish(ctx, a, report_acc, metrics, inv_by_vid, inv_status, upbundle_vids, live_vids,
                    vid_meta, pid_by_vid)
        except LoginBlocked:                      # Akamai 차단 → 서킷브레이커 카운트
            blocks += 1
            log(f"  [{a.label}] 로그인 차단 누적 {blocks}/{config.LOGIN_BLOCK_CIRCUIT}")
        except LoginCredentialError:              # 비번오류/계정잠금 → 재시도 금지: '처리됨'으로 표시해
            done.add(a.account_id)                # 야간 재개·같은 날 재실행이 비번을 다시 제출하지 않게(계정잠금 방지).
            _save_ctx_progress(ctx)
            log(f"  [{a.label}] 비밀번호 오류/계정 상태로 건너뜀 — 자동 재시도 안 함(계정잠금 방지). "
                "관리대장에서 비번 수정 후 새 실행(다음 날/진행분 초기화)에서 재시도됨")
        except Exception as exc:
            first = (str(exc).splitlines() or [""])[0][:250]
            log(f"  [{a.label}] 처리 오류: {exc.__class__.__name__}: {first} — 건너뜀")


@dataclass
class _RunInit:
    """run_full 시작 시 결정되는 실행 상태(재개 복구 또는 새 실행)."""
    wb: OutputWorkbook
    date_from: str
    date_to: str
    started_at: str
    done: set
    carry: bool
    grow: bool
    skip_ranks: bool
    date_label: str | None


def _init_run_state(input_list: InputList, out: Path, partial: Path, prog: Path, master: Path,
                    now: datetime, resume: bool, carry_forward: bool, grow_keywords: bool,
                    skip_ranks: bool, redo_today: bool, date_from, date_to, date_label, log) -> _RunInit:
    """실행 시작 상태 결정 — 같은 날 크래시 복구(resume) 또는 새 실행(통계 이어쓰기/새 통계).

    resume=True고 오늘 진행분이 있으면 기간·완료계정·진행엑셀·모드(carry/grow/skip)를 복원한다.
    새 실행이면 날짜·done을 세우고, carry_forward+마스터 존재면 마스터를 이어쓰기(키워드 동결),
    아니면 빈 워크북(명시적 '새 통계'는 기존 마스터를 보관 후). 진행 기준선(partial)·진행파일을 저장한다.
    """
    meta = resumable_progress(out) if resume else None
    if meta:                                   # 같은 날 크래시 복구 — 기간·완료계정·진행엑셀·모드 복원
        date_from, date_to = meta["date_from"], meta["date_to"]
        started_at = meta["started_at"]
        done = set(meta["done"])
        carry = bool(meta.get("carry", False))
        grow = bool(meta.get("grow", False))
        skip_ranks = bool(meta.get("skip", False))   # 재개 시 순위제외 모드도 그대로 유지
        date_label = meta.get("date_label") or date_label   # 재개=원래 작업 실행날짜 라벨 유지(새벽 넘겨도 시작일 기준)
        wb = OutputWorkbook.load(partial)
        log(f"== 이어서 실행({'통계이어쓰기' if carry else '새통계'}) — 완료 {len(done)}개 건너뜀, "
            f"기간 {date_from}~{date_to} ==")
        return _RunInit(wb, date_from, date_to, started_at, done, carry, grow, skip_ranks, date_label)
    # 새 실행(오늘)
    date_to = date_to or now.strftime("%Y-%m-%d")
    date_from = date_from or date_to
    started_at = now.strftime("%Y-%m-%d %H:%M:%S")
    done: set = set()
    carry = carry_forward and master.exists()
    grow = grow_keywords and carry
    if carry_forward and not master.exists():
        log("== ⚠ 통계 마스터가 없어 '새 통계'로 시작합니다 — 결과 구글시트가 있으면 UI가 먼저 복원합니다 ==")
    if carry:
        wb = OutputWorkbook.load(master)   # 기존 통계 이어쓰기(키워드 동결 + 오늘 컬럼)
        log(f"== {'오늘 처음(다시) 하기' if redo_today else '통계 이어쓰기'} — 마스터 로드, "
            f"오늘 컬럼{' 초기화 후 재수집' if redo_today else ' 추가'}"
            f"{' · 새 키워드 발굴 추가' if grow else ' · 키워드 동결'} ==")
    else:
        if not carry_forward and master.exists():   # 명시적 '새 통계' → 기존 마스터 보관(백업)
            bak = out / f"{config.OUTPUT_FILE_PREFIX}_통계_보관_{now.strftime('%y%m%d_%H%M%S')}.xlsx"
            master.rename(bak)
            log(f"== 기존 통계 마스터를 보관함: {bak.name} ==")
        wb = OutputWorkbook.empty()
        log(f"== 새 통계 시작 — {len(input_list.accounts)}개 계정, 기간 {date_from}~{date_to} ==")
    for p in (partial, prog):
        if p.exists():
            p.unlink()
    wb.save(partial)                       # 크래시 복구 기준선(carry면 마스터 내용 포함)
    _save_progress(out, date_from, date_to, started_at, done, carry, grow, skip_ranks, date_label)
    return _RunInit(wb, date_from, date_to, started_at, done, carry, grow, skip_ranks, date_label)


def _validate_or_raise(input_list: InputList, log) -> None:
    """시작 전 입력 검증 — 경고는 알리고 진행, 치명적 이상은 시작 차단(작업 도중 크래시·데이터 손실 예방)."""
    fatals, warns = validate_input_list(input_list)
    for w in warns:
        log(f"  [입력검증] ⚠ {w}")
    if fatals:
        for f in fatals:
            log(f"  [입력검증] ✖ {f}")
        raise InputValidationError("입력 파일 검증 실패 — 위 항목을 고친 뒤 다시 시작하세요.")
    log(f"[입력검증] 통과 — 계정 {len(input_list.accounts)}개 · "
        f"상품 {sum(len(a.products) for a in input_list.accounts)}개"
        + (f" · 경고 {len(warns)}건(진행)" if warns else ""))


def _finalize_run(ctx: _RunCtx, master: Path, prog: Path, now: datetime, gsheet_output_url,
                  removed_accounts, uncollected, renamed_accounts=None) -> Path:
    """통계 마스터/스냅샷 저장 + 결과 구글시트 반영 + 진행파일 정리. 반환=스냅샷 경로.

    로그인 못한 계정이 남았으면 진행분을 유지(같은 날 재실행이 미완료분만 이어서 처리), 없으면 진행파일을
    지운다(날짜가 바뀌면 resumable_progress 가 '오늘 아님'으로 무시 → 자동으로 처음부터).
    """
    wb, log = ctx.wb, ctx.log
    snapshot = _snapshot_path(ctx.out, now)
    wb.apply_style()         # 가독성 서식(헤더 고정·상품 구분·정렬) — 최종본에만
    wb.save(master)          # 다음 날 이어쓸 마스터
    wb.save(snapshot)        # 그날 백업본(감사용)
    _push_gsheet(wb, gsheet_output_url, log, removed_accounts=removed_accounts,
                 renamed_accounts=renamed_accounts)   # 결과 반영 + 삭제 계정 + 일원화 옛 이름 정리
    if uncollected:
        _save_ctx_progress(ctx)
        wb.save(ctx.partial)     # 재개 기준선(완료분 반영)
        log(f"== 미완료 {len(uncollected)}개 남음 — 진행분 유지(같은 날 재실행 시 그 계정만 이어서) ==")
    else:
        for p in (ctx.partial, prog):
            if p.exists():
                p.unlink()
    log(f"== 완료: 마스터 {master.name} · 스냅샷 {snapshot.name} (성공 {len(ctx.done)}/{ctx.total} 계정) ==")
    return snapshot


def run_full(input_list: InputList, naver: NaverAdApi, out_dir: str = "output",
             ai_key: str | None = None, date_from: str | None = None, date_to: str | None = None,
             get_password=None, resume: bool = False, carry_forward: bool = False,
             grow_keywords: bool = False, skip_ranks: bool = False, redo_today: bool = False,
             sales_semi: bool = False, date_label: str | None = None,
             keywords_off: bool = False, on_log=None, gsheet_output_url: str | None = None) -> Path:
    """계정별 end-to-end 완결 + **같은 날 이어서 하기** + **통계 마스터 이어쓰기(cross-day)**.

    실행 모드(3택, UI 실행모드와 대응):
    - **① 이어서 하기**: `resume`(오늘 진행분 있으면 이어서·완료계정 건너뜀) 또는 `carry_forward`(마스터에
      오늘 컬럼 추가). 어제까지 유지.
    - **② 오늘 처음(다시) 하기**: `redo_today=True`(+carry_forward). 어제까지 유지하되 **오늘 컬럼·완료
      스탬프를 초기화**하고 전 계정을 오늘분 처음부터 재수집(완료계정도 다시). 키워드는 동결.
    - **③ 전체 새로 시작(fresh)**: `carry_forward=False`. 마스터가 있으면 보관(백업) 뒤 빈 워크북으로 새로.
    - **통계 이어쓰기(carry_forward=True)**: 마스터(`쿠팡데이타분석_통계.xlsx`)를 불러와 **기존 키워드를
      동결**하고 오늘 날짜 컬럼만 채운다(시계열 의미 유지). `grow_keywords=True`면 상한(KW_MAX_TRACK) 안에서
      상품당 하루 최대 KW_ADD_PER_DAY개 **새 키워드만 발굴 추가**(기존은 절대 제거 안 함).
    - **같은 날 크래시 복구(resume=True)**: `진행중.xlsx`(+`.json`)를 읽어 완료 계정은 건너뛰고 끊긴
      지점부터 이어간다. 진행 상태에 carry/grow 플래그가 있어 그 모드 그대로 재개된다.

    완료되면 마스터를 갱신하고 그날 스냅샷(`쿠팡데이타분석_통계_yymmdd.xlsx`)을 남긴 뒤 진행파일을 지운다.
    키워드는 AI로 도출하므로 `ai_key` 필수(없으면 KeywordAIError). 한 계정이 막혀도 그 계정만 건너뛴다.
    """
    log = on_log or (lambda m: None)
    _reset_rank_state()          # 이번 실행 순위 차단 플래그·서킷브레이커(cooldown) 초기화
    if not ai_key:
        raise KeywordAIError("OpenAI(ChatGPT) API 키가 없어 키워드 추출을 할 수 없습니다. "
                             "설정 탭에서 OpenAI API 키를 입력한 뒤 다시 실행하세요.")
    _validate_or_raise(input_list, log)
    now = datetime.now()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    partial, prog = _partial_path(out), _progress_path(out)

    master = _master_path(out)
    st = _init_run_state(input_list, out, partial, prog, master, now, resume, carry_forward,
                         grow_keywords, skip_ranks, redo_today, date_from, date_to, date_label, log)
    wb, date_from, date_to = st.wb, st.date_from, st.date_to
    started_at, done, date_label = st.started_at, st.done, st.date_label
    carry, grow, skip_ranks = st.carry, st.grow, st.skip_ranks

    # 목차 로스터 — 입력 전체 계정(계정ID·대표자명)을 등록해 **미수집 계정도 목차에 표시**(수집 현황 파악)
    for _a in input_list.accounts:
        wb.set_account_id(_a.label, _a.account_id)
        wb.set_representative(_a.label, _a.representative)   # 계정목록 대표자 컬럼 표시용(관리대장 대표자명)

    # 직원이 결과 통계 시트에 직접 넣은 키워드를 역머지(값 있으면 그 상품은 AI 선정 대신 동결). 미러링 전에 워크북에
    # 들어가야 종료 시 전체 교체돼도 보존된다. 새 상품(블록 없음)은 대상 아님(첫 수집 후 시트가 생겨야 입력 가능).
    if not keywords_off:                       # ①판매수집 전용은 키워드 단계가 없어 역머지 불필요
        _pull_gsheet_keywords(wb, gsheet_output_url, log)

    # 일자 컬럼 라벨 = **작업 실행날짜**(date_label). 순위(③)는 같은 실행날짜 컬럼(latest_date)에 기록돼
    # '오늘 순위 + 전일 판매'가 한 컬럼에 나란히 쌓인다.
    col_label = _column_label(date_from, date_to, date_label, log)
    if redo_today and carry:      # ② 오늘 처음(다시): 오늘 컬럼·완료스탬프 초기화 → 전 계정 오늘분 재수집
        c1 = wb.reset_date_column(col_label)
        c2 = wb.clear_sales_stamps()
        wb.save(partial)          # 초기화분을 진행파일에도 반영(크래시 복구 기준선)
        log(f"  [오늘 초기화] 오늘({col_label}) 컬럼 값 {c1}칸·완료스탬프 {c2}계정 해제 — 전 계정 재수집(어제까지 유지)")

    preflight_sync_check(wb, input_list, log)   # ②③ 시작 프리플라이트 — 대장↔결과 대조(비변경 진단·[SYNC] 로그)

    accounts = input_list.accounts
    total = len(accounts)
    # 계정별 기록·진행 저장에 쓰는 공유 상태를 한 곳에 모은다(_finish 가 이 컨텍스트로 동작).
    ctx = _RunCtx(wb=wb, out=out, partial=partial, date_from=date_from, date_to=date_to,
                  date_label=date_label, started_at=started_at, done=done, carry=carry, grow=grow,
                  skip_ranks=skip_ranks, keywords_off=keywords_off, col_label=col_label, total=total,
                  naver=naver, ai_key=ai_key, log=log)

    # 계정 수집 = 2패스(세션우선 → 로그인). Akamai IP 차단을 줄이려 로그인 없는 계정을 먼저 다 확보한다.
    login_needed, sales_skipped = _collect_session_first(ctx, accounts, get_password)
    _collect_with_login(ctx, login_needed, get_password, sales_semi)

    uncollected = [a for _, a in login_needed if a.account_id not in done]
    if uncollected:
        log(f"== ⚠ 로그인 못한 계정 {len(uncollected)}개(세션만료+Akamai차단): "
            f"{', '.join(a.label for a in uncollected)} — 쉰 IP(내일 등)에 재실행 시 수집됨 ==")

    removed_accounts, renamed_accounts = _reconcile_ledger_accounts(wb, input_list, uncollected, log)

    # 판매수집을 건너뛴(이미 오늘 수집됨) 계정도 키워드가 비어 있으면 선정(로그인 없이·워크북 기반).
    # 전체실행(①②③) 재실행에서 판매는 스킵하되 ②키워드가 빠지지 않게 한다(①판매수집 전용은 키워드 단계 없음).
    if sales_skipped and not keywords_off:
        _select_keywords_for_skipped(wb, partial, sales_skipped, naver, ai_key, log)

    # (offscreen 순위백필 _backfill_ranks 는 폐기·물리 삭제 — 2026-09-26. ③순위는 반자동만·§DESIGN §5.2)
    # 통계 마스터/스냅샷 저장 + 결과 구글시트 반영 + 진행파일 정리
    return _finalize_run(ctx, master, prog, now, gsheet_output_url, removed_accounts, uncollected,
                         renamed_accounts=renamed_accounts)


def select_keywords_stage(naver: NaverAdApi, ai_key: str | None, out_dir: str = "output",
                          grow: bool = False, on_log=None, gsheet_output_url: str | None = None) -> Path | None:
    """② 키워드 선정 전용 — 최신 워크북 로드, 상품별 키워드(**순위 조회 없음**) 선정·기록. 로그인 불필요.

    ①(판매수집)로 상품이 이미 워크북에 있어야 한다. 기존 키워드가 있으면 동결(grow=True면 상한 내 발굴
    추가), 없으면 새로 선정한다. 쿠팡 순위는 조회하지 않는다(measure_ranks=None) — 순위는 ③에서.
    자동완성(쿠팡, 비로그인)만 쓰므로 로그인 브라우저는 열지 않는다.
    """
    log = on_log or (lambda m: None)
    if not ai_key:
        raise KeywordAIError("OpenAI(ChatGPT) API 키가 없어 키워드 선정을 할 수 없습니다. "
                             "설정 탭에서 OpenAI API 키를 입력한 뒤 다시 실행하세요.")
    out = Path(out_dir)
    wb, path = _load_latest_wb(out)
    if wb is None:
        log("== 키워드 선정: 결과 워크북이 없습니다 — 먼저 ①(판매데이터 수집)을 실행하세요 ==")
        return None
    log(f"== 키워드 선정 시작(순위 조회 없음) — {path.name} ==")
    with WingBrowser(profile_dir=_PROFILE, offscreen=True) as browser:
        warmup(browser)
        for biz in wb.account_sheets():
            for pname in wb.products_of(biz):
                _select_product_keywords(wb, biz, pname, naver, ai_key, browser, grow, log)
            wb.save(path)
    # 키워드가 KW_TRACK_N(=4) 미만인 상품(선정 실패·옛 0행 블록 등)은 빈 순위행으로 4행 유지(사용자 요구 2026-09-15).
    padded = sum(wb.pad_keyword_rows(biz, p) for biz in wb.account_sheets() for p in wb.products_of(biz))
    if padded:
        log(f"  [키워드행] 4행 미만 상품에 빈 순위행 {padded}개 추가(키워드 없어도 4행 유지·공란)")
    wb.apply_style()   # 추가한 키워드 행까지 표준 서식 고정(시트간 서식 섞임 방지)
    wb.save(path)
    _push_gsheet(wb, gsheet_output_url, log)   # ② 개별 실행도 결과 구글시트에 반영(키워드 갱신)
    log("== 키워드 선정 완료 ==")
    return path


def _select_product_keywords(wb, biz: str, pname: str, naver, ai_key, browser, grow: bool, log) -> None:
    """② 한 상품 키워드 선정 — 동결(있으면 유지·검색량만 채움)/발굴(grow)/새 상품 AI 첫 선정.

    다중옵션 2차 블록(키워드 구역 없음)은 대상 아님. 한 상품 실패(AI·네이버 400 등)는 격리(로그만)."""
    if not wb.has_keyword_section(biz, pname):   # 다중옵션 2차 블록(판매정보만) → 키워드 선정 대상 아님
        return
    existing = wb.product_keywords(biz, pname)
    if existing:   # 시트에 채워진 키워드 = 그대로 사용. 검색량 공란만 네이버로(fix ②)
        _fill_frozen_search_volumes(wb, biz, pname, existing, naver, log)
    # **키워드가 있으면 시트 값 그대로 동결** — 일부(2개)만 있으면 일부만, AI 톱업 없음(소유자 2026-09-20).
    # 새 키워드는 grow(발굴 추가) 옵션일 때만 상한 내에서 추가. 키워드가 아예 없으면(새 상품) AI 첫 선정.
    if existing and not grow:
        log(f"  [{biz}] {pname} → 키워드 있음, 그대로 사용(동결) {existing}")
        return
    try:
        if existing:                           # grow: 기존 유지 + 상한 내 발굴 추가
            want = min(config.KW_ADD_PER_DAY, config.KW_MAX_TRACK - len(existing))
            if want <= 0:
                log(f"  [{biz}] {pname} → (동결·상한 {config.KW_MAX_TRACK}) {existing}")
                return
            tracks = select_keywords_light(pname, naver, ai_key, browser=browser, log=log,
                                           n=want, measure_ranks=None, exclude=set(existing))
            new = [t for t in tracks if t.keyword not in existing][:want]
            if new:
                wb.add_product_keywords(biz, pname, [t.keyword for t in new])
                for t in new:
                    wb.set_keyword_search(biz, pname, t.keyword, t.volume)
                log(f"  [{biz}] {pname} → 동결 {existing} + 발굴 {[t.keyword for t in new]}")
            else:
                log(f"  [{biz}] {pname} → (동결·추가 후보 없음) {existing}")
        else:                                  # 새 상품(키워드 0개) → AI 첫 선정(최대 KW_TRACK_N)
            tracks = select_keywords_light(pname, naver, ai_key, browser=browser,
                                           log=log, measure_ranks=None)
            wb.add_product_keywords(biz, pname, [t.keyword for t in tracks])
            for t in tracks:
                wb.set_keyword_search(biz, pname, t.keyword, t.volume)
            log(f"  [{biz}] {pname} → 키워드 {[t.keyword for t in tracks]}")
    except Exception as exc:   # 한 상품 실패(AI·네이버 400 등)가 나머지 상품·계정 선정을 안 막게 격리
        log(f"  [{biz}] {pname} 키워드 선정 실패(건너뜀) — {exc.__class__.__name__}: {str(exc)[:80]}")

