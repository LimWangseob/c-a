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
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config
from .browser import WING_URL, WingBrowser
from .input_list import Account, InputList, InputValidationError, validate_input_list
from . import wing_session
from . import session_state
from .kw_ai import KeywordAIError, recommend_title
from .kw_recommend import (attack_priority, comp_from_idx, diagnose_exposure,
                           keyword_in_title, rank_label, select_keywords_light)
from .kw_volume import NaverAdApi
from .rank import make_matcher, warmup   # 순위 함수 대부분은 pipeline_ranks 로 이동(warmup·make_matcher만 core 사용)
from .session_store import SessionStore
from .workbook import OutputWorkbook

# 경로/단계 헬퍼·상수는 leaf 모듈 pipeline_paths 로 분리(순환 import 방지). 여기서 다시 import 해
# `pipeline.X` 공개 API(UI·도구·핀)를 그대로 유지한다.
from .pipeline_paths import (  # noqa: E402
    _PROFILE, _PROFILES_DIR, _load_latest_wb, _master_path, _partial_path,
    _progress_path, _snapshot_path)
# 재수출(UI·스케줄러·도구가 pipeline.X 로 쓰는 공개 API) — pipeline 내부 미사용이라 noqa.
from .pipeline_paths import master_exists, read_run_stage, write_run_stage  # noqa: E402,F401
# 구글시트 연동·백업·복원은 pipeline_gsheet 로 분리(대형 파일 정비). pipeline.X 로 다시 노출.
from .pipeline_gsheet import (  # noqa: E402,F401
    _pull_gsheet_keywords, _push_gsheet, backup_sources,
    push_ledger_inventory, restore_master_from_gsheet)
# ③ 순위(측정·서킷브레이커·자동/반자동 검색·스테이지)는 pipeline_ranks 로 분리. pipeline.X 로 다시 노출
# (핀/시뮬 monkeypatch 대상은 pipeline_ranks). core(_fill_product_metrics·_finalize_run)가 _best/
# _measure_safe/_reset_rank_state/_backfill_ranks/_RANK_HALT 를 호출하므로 재수출 필요.
from .pipeline_ranks import (  # noqa: E402,F401
    RankHalt, _RANK_CB, _RANK_HALT, _RANK_TELEMETRY_ID, _all_pages, _backfill_ranks, _best,
    _count_unfilled_ranks, _interruptible_sleep, _live_url, _looks_blocked, _measure,
    _measure_nav_serial, _measure_product_auto, _measure_safe, _measure_unfilled_once,
    _prefill_search, _rank_cooldown, _rank_matcher, _reset_rank_state, _search_q,
    _semi_browser_prep, _semi_on_miss, _semi_prep_product, _semi_record, _semi_search_one,
    _semi_start_log, _semi_summary_log, _semi_track_product, _submit_search, _track_ranks_semi,
    _wait_results_loaded, _wait_user_search, track_ranks_stage)


def _fill_frozen_search_volumes(wb, biz: str, product: str, keywords: list[str],
                                naver: NaverAdApi | None, log) -> int:
    """동결 키워드 중 **검색량이 비어 있는 것만** 네이버 검색광고 API로 채운다(AI 불필요, fix ②).

    키워드가 있으면 생성(선정)은 생략(동결)하되, 직원이 결과 시트에 직접 넣어 **검색량 칸이 공란**인
    키워드는 네이버 월검색량으로 채운다(소유자 규칙 2026-09-20). 못 찾은 키워드는 공란 유지(날조 금지).
    """
    if naver is None or not keywords:
        return 0

    def _blank(v) -> bool:
        return v is None or (isinstance(v, str) and not v.strip())

    empties = [kw for kw in keywords if _blank(wb.keyword_search(biz, product, kw))]
    if not empties:
        return 0
    try:
        vols = naver.related_keywords_multi(empties)
    except Exception as exc:   # 네이버 400/429 등이 동결 상품 처리를 막지 않게 격리(공란 유지)
        log(f"  [검색량] {product} 동결 키워드 검색량 조회 실패(공란 유지) — "
            f"{exc.__class__.__name__}: {str(exc)[:80]}")
        return 0
    norm = lambda s: str(s).replace(" ", "").lower()   # 네이버는 힌트 공백 제거·대소문자 무시로 조회
    by = {norm(v.keyword): v.total for v in vols}
    n = 0
    for kw in empties:
        vol = by.get(norm(kw))
        if vol is not None and wb.set_keyword_search(biz, product, kw, vol):
            n += 1
    if n:
        log(f"  [검색량] {product} 동결 키워드 {n}개 검색량 채움(네이버)")
    return n


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


def account_profile(account_id: str) -> str:
    """계정별 로그인 프로필 경로 (한 번 로그인하면 재사용)."""
    return f"{_PROFILES_DIR}/{account_id}"


def _product_matcher(product):
    """상품 단위 매처(옵션 통합) — 새 서식은 상품별 노출순위라 옵션의 vid/pid를 모두 합쳐 하나로 매칭."""
    vids, pids = set(), set()
    for opt in product.options:
        vids |= set(opt.vendor_item_ids)
        pids |= set(opt.product_ids)
    return make_matcher(product_ids=pids, vendor_item_ids=vids,
                        name_substr=None if (vids or pids) else product.name)


class NeedLogin(Exception):
    """세션이 없어 로그인이 필요한 계정(세션우선 1차 패스에서 뒤로 미룸)."""


class LoginBlocked(Exception):
    """Akamai 로그인 차단(Access Denied) — 서킷브레이커 카운트 대상."""


class LoginCredentialError(Exception):
    """비밀번호 오류·계정잠금·휴면 등 **확정 자격 실패**(#input-error). 재시도·재제출 금지
    (재제출이 5회 오류 계정잠금을 유발 — 위탁계정). 호출부는 이 계정을 '처리됨'으로 표시해
    같은 실행·야간 재개가 다시 제출하지 않게 한다. 사용자 지시(2026-09-15): 비번 1회 오류면 재시도 안 함."""


def _dump_raw(account_id: str, log, out_dir: str = "output") -> None:
    """수집한 3개 데이터 API 응답 **원문(가공 없음)** 을 계정별 gzip 사이드카로 저장 — 다양한 오프라인 분석용.

    파싱/요약이 아니라 **쿠팡이 준 응답 바디 그대로**(F12 네트워크와 동일)를 남긴다. 재수집·재빌드 없이
    중복 판별·필드 탐색 등에 쓴다. 저장 위치=output/_raw/{계정}_{api}_p{n}.json.gz, run_log 엔 위치만(원문이
    커서 run_log 오염 방지). 설정(config.SAVE_RAW_RESPONSES) 끄면 no-op·버퍼 비면 no-op. 저장 실패는
    비치명(로그만·수집은 계속). api = vendor_inventory | inventory | sales(각 페이지 p1·p2…)."""
    if not config.SAVE_RAW_RESPONSES:
        return
    import gzip
    from .collector import raw_dumps
    dumps = raw_dumps()
    if not dumps:
        return
    try:
        d = Path(out_dir) / "_raw"
        d.mkdir(parents=True, exist_ok=True)
        n = 0
        for api, bodies in dumps.items():
            for i, body in enumerate(bodies, 1):
                with gzip.open(d / f"{account_id}_{api}_p{i}.json.gz", "wt", encoding="utf-8") as fh:
                    fh.write(body)
                n += 1
        if n:
            log(f"  [원본저장] {account_id}: 응답 원문 {n}개 → output/_raw/{account_id}_*.json.gz (가공 없음·분석용)")
    except Exception as exc:   # 저장 실패해도 수집은 계속(비치명)
        log(f"  [원본저장] ⚠ {account_id} 응답 원문 저장 실패(비치명) — {exc.__class__.__name__}: {str(exc)[:80]}")


def _login_and_discover(a: Account, date_from, date_to, get_password, log, login: bool = True,
                        semi: bool = False):
    """계정 하나: (필요시) 로그인 → **같은 신선한 세션**에서 즉시 판매분석 발견 + 지표.

    반환: (report_account[활동 상품만] | None, {옵션ID: OptionMetric}, {옵션ID: 재고수량},
    {옵션ID: 판매상태}, {업번들 vid 집합}, {상품조회 전체 vid 집합}). 4번째 판매상태맵 = 상품조회 productStatus
    문자열(판매자배송 포함 전 상품) 또는 폴백 RFM isSaleSuspended(bool). 5번째 = 업번들 vid(잔재 자동삭제용). 6번째 =
    이번 상품조회에 존재하는 전체 vid(죽은 중복 블록 정리 기준). 로그인 미완료면 (None,{},{},{},set(),set()) → 다음 계정으로.
    login=False(세션우선 1차): 세션 없으면 자동제출하지 않고 **NeedLogin** 을 던져 뒤로 미룬다
    (반복 자동로그인 = IP 차단 유발이라, 세션 살아있는 계정을 먼저 다 수집). Akamai 차단 시 LoginBlocked.
    semi=True(**반자동 판매수집**): 창을 **처음부터 보이게**(offscreen=False) 띄우고 **무인 아님**(사람이
    2차인증/직접로그인 처리)으로 로그인 → 그 신뢰 창에서 수집. ③ 반자동과 같은 '보이는 신뢰 세션' 방식.
    """
    from . import collector
    from .collector import save_discovered   # 지연 import
    pw = get_password(a.account_id) if get_password else None
    # 기본은 **창 숨김**(offscreen). 반자동(semi)이면 처음부터 보이게 띄운다(사람이 2차인증 처리).
    with WingBrowser(profile_dir=account_profile(a.account_id), offscreen=not semi) as b:
        if not _ensure_login(b, a, pw, log, login=login, semi=semi):
            return None, {}, {}, {}, set(), set(), {}, {}   # 이 계정 건너뜀(무인 비번없음·otp·로그인 미완료)
        collector.reset_raw()                # 계정별 응답 원문 버퍼 초기화(파일 분리)
        found = _discover_products(b, a, date_from, date_to, log)
        _dump_raw(a.account_id, log)         # 3 API 응답 원문 저장(가공 없음·분석용). found None(데이터없음)이어도 남김
        if found is None:                    # 판매분석·상품조회 모두 데이터 없음 → 건너뜀
            return None, {}, {}, {}, set(), set(), {}, {}
        (products, tracked, metrics, inventory, sale_status, upbundle_vids, live_all_vids,
         vid_meta, pid_by_vid) = found
        _persist_session(a, b, log)                                 # 세션 3요소+쿠키 영속(부가)
        session_state.observe_collection_done(a.account_id)         # 관측: 이 계정 수집 완료 시각
    save_discovered(a.account_id, products)   # (요약 로그는 위 with 블록에서 계정 단위로 남김)
    report = Account(a.account_id, a.representative, a.business_name, tracked)
    report.ledger_products = set(a.ledger_products)   # ⑥: 줄 존재 전체(활성+판매중지/취소선) 전파 — 완전삭제 판정용
    return (report, metrics, inventory, sale_status, upbundle_vids, live_all_vids, vid_meta, pid_by_vid)


def _ensure_login(b, a: Account, pw, log, *, login: bool = True, semi: bool = False) -> bool:
    """로그인 국면 — 세션 판정·(필요시)자동입력·대기·분류·반자동 1회 재시도.

    반환: **True**=로그인됨(호출부가 발견 진행) / **False**=이 계정 건너뜀(호출부가 (None,{},{},{}) 반환:
    무인 비번없음·2차인증(otp)·로그인 미완료). **예외**: NeedLogin(세션우선 1차 미제출)·LoginBlocked(Akamai)·
    LoginCredentialError(비번오류/계정잠금·재시도 금지). 제어흐름은 분해 전과 완전히 동일하다."""
    if semi:
        b.show()
    b.goto(WING_URL)
    b.page.wait_for_timeout(1500)
    if b.authenticated():
        log(f"  [{a.label}] 세션 재사용 → 이미 로그인됨" + (" (보이는 창)" if semi else " (창 안 뜸)"))
        session_state.observe_session_ok(a.account_id, final_url=b.page.url)   # 관측(제어흐름 불변)
        return True
    if not login:                  # 세션우선 1차 패스 — 자동제출 안 하고 로그인 대기열로 미룸
        session_state.observe_reauth_required(a.account_id, final_url=b.page.url)
        raise NeedLogin()
    unattended = config.LOGIN_UNATTENDED and not semi   # 반자동이면 사람 대기(무인 아님)
    return _fresh_login(b, a, pw, log, unattended)


def _fresh_login(b, a: Account, pw, log, unattended: bool) -> bool:
    """신선 로그인(세션 없음) — 자동입력·대기·반자동 1회 재시도·실패분류·성공 안착.

    반환 True/False, 예외 LoginBlocked/LoginCredentialError 는 _ensure_login 규약과 동일."""
    shown = {"v": False}

    def _need_user():   # 2차인증·봇챌린지 등 사람이 꼭 필요할 때
        if unattended:  # 무인: 창 안 띄움 — 사람 필요분은 건너뛰고 나중에 반자동/수동으로
            return
        if not shown["v"]:
            shown["v"] = True
            log(f"  [{a.label}] ⚠ 로그인 창을 잠시 띄웁니다(2차인증/직접로그인 필요). 놀라지 마세요")
            b.show()

    if pw and b.autofill_login(a.account_id, pw, on_log=log):
        log(f"  [{a.label}] ID/비번 자동입력·제출 — 창 숨긴 채 로그인 확인 중"
            + (" (무인: 사람 필요 시 건너뜀)" if unattended else " (2차인증 필요할 때만 창 표시)"))
    elif unattended:
        # 무인 + 비번없음/자동입력실패 → 사람 개입 불가 → 건너뜀(창 안 띄움)
        log(f"  [{a.label}] 무인 로그인 불가(비번 없음/자동입력 실패) — 건너뜀(나중에 반자동/수동)")
        session_state.observe_reauth_required(a.account_id, final_url=b.page.url)
        return False
    else:
        _need_user()   # 비번 없음/자동입력 실패 → 직접 로그인해야 하니 창 표시
        log(f"  [{a.label}] 직접 로그인이 필요해 창을 띄웠습니다")
    _wait_to = config.LOGIN_UNATTENDED_WAIT_SEC if unattended else 300
    _grace = config.LOGIN_BLOCK_GRACE_SEC if unattended else 60.0
    # skip_on_otp=True: 2차 인증(인증번호) 화면이 뜨면 **대기하지 않고 이 계정 건너뜀**(다음 계정 진행).
    ok = b.wait_for_login(timeout=_wait_to, on_log=log, tag=a.account_id,
                          on_need_user=_need_user, blocked_grace=_grace, skip_on_otp=True)
    # 비밀번호 오류·계정잠금·휴면(#input-error=classify_login 'error') = **확정 자격 실패**.
    # 사용자 지시(2026-09-15): 비번 1회 오류면 **재시도·재제출 금지**(재제출이 5회 오류 계정잠금 유발).
    cred_fail = (not ok) and b.classify_login()[0] == "error"
    otp_seen = (not ok) and b.classify_login()[0] == "otp"   # 2차인증 → 재시도 없이 건너뜀
    if not ok and not cred_fail and not otp_seen and unattended and pw and config.LOGIN_SEMI_ON_BLOCK:
        ok, cred_fail = _semi_retry_login(b, a, pw, log, _grace)
    if not ok:
        return _resolve_login_failure(b, a, log, cred_fail)   # False 반환 또는 LoginBlocked/CredentialError raise
    session_state.observe_auth_success(a.account_id, final_url=b.page.url)
    b.goto(WING_URL)                     # 신선 로그인 후 wing 안착(인증 리다이렉트 완료 대기)
    b.page.wait_for_timeout(1500)        # 페이지 안정 — discover fetch 가 진행중 네비에 중단(Failed to fetch)되는 것 방지
    b.hide()   # 로그인 끝나면 다시 숨김
    return True


def _semi_retry_login(b, a: Account, pw, log, grace) -> tuple[bool, bool]:
    """반자동(무인) **1회** 재시도 — 무인 오프스크린 자동입력이 소프트 차단/폼 정체로 실패했을 때만.

    (비번오류는 호출부 cred_fail 로 이미 배제.) 창을 띄우고 앱이 자동입력·클릭으로 딱 1번 더 시도한다.
    ⚠ 제출이 1회 추가되므로 **계정당·실행당 정확히 1회**. Akamai IP 차단은 이걸로도 대부분 못 뚫음.
    반환: (ok, cred_fail) — cred_fail 은 재시도가 비번오류를 드러냈을 때도 재큐 금지용."""
    log(f"  [{a.label}] 로그인 차단/미완료 → 반자동 1회 재시도(창 표시, 앱이 자동입력·클릭)")
    b.show()
    b.goto(WING_URL)                      # 신선 로그인 폼으로 리다이렉트 유도
    b.page.wait_for_timeout(1200)
    ok = False
    if b.authenticated():                 # 그새 로그인 완료됐을 수도
        ok = True
    elif b.autofill_login(a.account_id, pw, on_log=log):
        ok = b.wait_for_login(timeout=config.LOGIN_SEMI_WAIT_SEC, on_log=log,
                              tag=a.account_id, on_need_user=lambda: None,
                              blocked_grace=grace, skip_on_otp=True)
    log(f"  [{a.label}] 반자동 재시도 {'성공' if ok else '실패 — 이 계정 건너뜀'}")
    b.hide()
    cred_fail = (not ok) and b.classify_login()[0] == "error"   # 재시도가 비번오류를 드러냈을 때도 재큐 금지
    return ok, cred_fail


def _resolve_login_failure(b, a: Account, log, cred_fail: bool) -> bool:
    """로그인 미완료(not ok) 뒤처리 — 실패 유형 관측 후 제어흐름 분기(분해 전과 동일).

    반환 False(otp·일반 미완료=이 계정 건너뜀). raise LoginBlocked(Akamai)·LoginCredentialError(비번오류)."""
    code, detail = b.classify_login()
    ftype = session_state.failure_type_of(code, detail)   # 세분 실패분류(탐지코드는 불변)
    session_state.observe_auth_failure(a.account_id, ftype, final_url=b.page.url)
    if code == "blocked":   # Akamai 차단 → 서킷브레이커가 세도록 신호
        log(f"  [{a.label}] Akamai 로그인 차단 — 이 계정 건너뜀")
        raise LoginBlocked()
    if cred_fail:           # 비번오류/계정잠금/휴면 → 재시도 금지(계정잠금 방지), 이번 주기 완료처리
        log(f"  [{a.label}] 로그인 거부(비밀번호 오류/계정 상태: {detail[:60]}) — "
            "재시도 안 함(계정잠금 방지), 이 계정 건너뜀")
        raise LoginCredentialError(a.account_id)
    if code == "otp":       # 2차 인증(인증번호) 화면 → 대기 없이 건너뜀(다음 계정 진행, 다음 실행에서 재시도)
        log(f"  [{a.label}] ⚠ 2차 인증(인증번호) 필요 — 대기하지 않고 이 계정 건너뜀"
            " (다음 계정 진행 · 미완료로 남겨 다음 실행에서 재시도)")
        return False
    log(f"  [{a.label}] 로그인 미완료 — 이 계정 건너뜀")
    return False


def _discover_products(b, a: Account, date_from, date_to, log):
    """발견 국면 — 상품조회/수정(vid 출처)·판매분석(지표)·재고현황·대장 스코핑/보강.

    반환: (products, tracked, metrics, inventory, sale_status, upbundle_vids). 판매분석·상품조회 **모두
    데이터 없음**이면 None(호출부가 (None,{},{},{},set()) 로 이 계정 건너뜀). upbundle_vids = 이번 상품조회의
    업번들(자동번들) 옵션 vid 집합(마스터 잔재 블록 자동삭제용, 소유자 2026-09-24). 제어흐름은 분해 전과 동일하다."""
    from .collector import (fetch_vendor_inventory, products_from_vendor_inventory,
                            VendorInventoryFetchError, sale_status_by_vid, vid_meta_of)
    from .product_match import scope_to_ledger
    # ── vid·옵션·상품 = 상품조회/수정(전 상품·전 옵션 나열, 당일 판매 0 상품도 포함). 폴백=판매분석 발견 ──
    # (vi-detail-search 는 당일 판매활동 상품만 잡혀 판매 0 상품 vid 누락 → 상품조회/수정으로 vid 출처 교체)
    vendor_products = None
    vendor_status: dict[str, str] = {}   # {vid: 판매상태} — 상품조회 productStatus(전 상품·판매자배송 포함)
    listings: list = []                  # 진단(vid 대조)용 — 실패 시 빈 목록
    try:
        listings = fetch_vendor_inventory(b.page, log)
        vendor_products = products_from_vendor_inventory(listings, log)
        vendor_status = sale_status_by_vid(listings, log)   # 판매상태 출처(화면과 일치·판매자배송까지 커버)
    except VendorInventoryFetchError as exc:
        log(f"  [{a.label}] ⚠ 상품조회/수정(vid 출처) 실패 → 판매분석 발견으로 폴백 — {str(exc)[:120]}")
    # ── 지표(노출/판매/방문자) = 판매분석(vi-detail-search). 상품은 위 vendor_products 로 대체 ──
    got = _run_discover(b, a, date_from, date_to, vendor_products is not None, log)
    if got is None:        # 판매분석·상품조회 모두 데이터 없음 → 이 계정 건너뜀(관측은 _run_discover 가 남김)
        return None
    products, metrics = got
    if vendor_products is not None:
        products = vendor_products   # vid 출처 = 상품조회/수정(전 상품·전 옵션). 지표는 metrics(vi-detail)로 조인
    inventory, inv_names, rfm_status, inv_pids = _discover_inventory(b, a, products, log)
    # 판매상태 출처(§2.3 대장↔쿠팡 불일치 경고) = **상품조회 productStatus(전 상품·판매자배송 포함)** 우선,
    # 없으면(상품조회 실패) RFM isSaleSuspended(로켓그로스만) 폴백. 라이브 실측(2026-09-20 nicoable/sg0141n)에서
    # productStatus 가 ON_SALE/PARTIAL_ON_SALE/SUSPENDED 로 정상 변동·**화면 판매/승인상태와 일치** 확인.
    # (wellbing1107 은 '신규 등록 불가' 제한 계정이라 전부 SUSPENDED 였을 뿐 — 필드 자체는 정상.)
    sale_status = vendor_status if vendor_status else rfm_status
    # 이번 상품조회의 **업번들(자동번들) 옵션 vid 집합** — 마스터에 남은 옛 업번들 잔재 블록을 vid 기준으로
    # 자동삭제하는 데 쓴다(소유자 2026-09-24, _purge_upbundle_blocks). 상품조회 실패(listings=[])면 빈 집합.
    upbundle_vids = {o.vendor_item_id for lst in listings for o in lst.options
                     if getattr(o, "is_upbundle", False) and o.vendor_item_id}
    # 이번 상품조회에 **실제로 존재하는 전체 vid**(NORMAL·RFM·업번들 모두 = 코팡 현재 보유분). 죽은 중복 블록
    # 정리(_sweep_dead_duplicates)의 기준 — 이 집합에 없는 vid = 코팡서 사라짐. 상품조회 실패면 빈 집합(정리 skip).
    live_all_vids = {o.vendor_item_id for lst in listings for o in lst.options if o.vendor_item_id}
    vid_meta = vid_meta_of(listings)   # {vid: (판매가, 판매시작일)} — 헤더 표시(상품판매가·입고일 근사)
    pid_by_vid = _pid_by_vid(inv_pids, metrics)
    # 추적 범위 = 입력 대장 상품(위탁 관리분)만. 당일 발견을 매칭해 노출제목·vid·구분 부여(지표는 당일 것).
    tracked, n_match = scope_to_ledger(a.products, products)
    tracked, n_match = _augment_vids(b, a, tracked, n_match, inv_names, date_to, log)
    _log_discover_summary(a, products, metrics, inventory, sale_status, tracked, n_match, log)
    return (products, tracked, metrics, inventory, sale_status, upbundle_vids, live_all_vids,
            vid_meta, pid_by_vid)


def _discover_inventory(b, a: Account, products, log):
    """로켓그로스/둘다 상품이 있으면 재고현황(RFM) 직접조회 — (inventory, inv_names, rfm_status, inv_pids).
    판매자배송 전용 계정은 재고 없어 생략. 실패해도 수집 전체는 진행(부가지표·사유 명시)."""
    from .collector import fetch_inventory, InventoryFetchError
    inventory: dict[str, int] = {}
    inv_names: dict[str, str] = {}
    rfm_status: dict[str, bool] = {}   # {vid: isSaleSuspended} — RFM 재고 API(로켓그로스만)
    inv_pids: dict[str, str] = {}      # {vid: productId} — 재고 API 노출상품ID(판매 0 상품 커버, 항목2)
    if any(p.kind in config.KINDS_WITH_INVENTORY for p in products):
        try:
            inventory, inv_names, rfm_status, inv_pids = fetch_inventory(b.page, log)   # 재고 수량 + roster + 판매상태 + productId
            log(f"  [{a.label}] 재고현황 {len(inventory)}개 옵션 조회")
        except InventoryFetchError as exc:   # 부가지표 — 실패해도 수집 전체는 진행(사유 명시)
            log(f"  [{a.label}] ⚠ 재고현황 조회 실패(계속) — {str(exc)[:120]}")
    return inventory, inv_names, rfm_status, inv_pids


def _pid_by_vid(inv_pids: dict, metrics: dict) -> dict[str, str]:
    """{vid: 노출상품ID(productId)} — 상품명 하이퍼링크(항목2). 재고 API(판매 0 상품 커버) ∪ 판매분석(활동 상품).
    상품조회(vendor-inventory)엔 공개 productId 가 없어 이 두 소스로만 확보(실측 2026-09-26)."""
    pid_by_vid: dict[str, str] = dict(inv_pids)
    for oid, om in metrics.items():
        pid = getattr(om, "product_id", "")
        if pid and oid not in pid_by_vid:
            pid_by_vid[oid] = pid
    return pid_by_vid


def _log_discover_summary(a: Account, products, metrics, inventory, sale_status, tracked, n_match, log) -> None:
    """계정 요약(진행경과·오류추적): 소스별 개수 + 대장 매칭/미매칭(vid 없는 상품은 등록명으로 추적)."""
    unmatched = [tp.name for tp in tracked if not any(o.vendor_item_ids for o in tp.options)]
    vid_count = sum(len(o.vendor_item_ids) for tp in tracked for o in tp.options)
    log(f"  [계정 {a.account_id}/{a.label}] 소스: 상품조회 {len(products)}상품 · 판매분석 {len(metrics)}옵션"
        f" · 재고 {len(inventory)}vid · 판매상태 {len(sale_status)}vid")
    log(f"  [계정 {a.account_id}/{a.label}] 대장 {len(a.products)} → 추적 {len(tracked)}"
        f"(매칭 {n_match}·vid {vid_count}) · 미매칭(vid없음) {len(unmatched)}"
        + (f": {[_short(n, 22) for n in unmatched[:10]]}{'…' if len(unmatched) > 10 else ''}" if unmatched else ""))


def _run_discover(b, a: Account, date_from, date_to, has_vendor: bool, log):
    """판매분석(vi-detail-search) 지표 수집 — PWTimeout(데이터없음)·Failed to fetch(1회 재시도) 처리.

    반환: (products, metrics). 당일 데이터 없어도 상품조회 상품이 있으면 ([], {}) 로 계속. 판매분석·상품조회
    **모두 없음**(has_vendor=False + PWTimeout)이면 collection_empty 관측 후 None(호출부가 이 계정 건너뜀)."""
    from .collector import discover
    from playwright.sync_api import TimeoutError as PWTimeout   # 판매데이터 없음 판별용

    def _empty_or_skip():   # '엑셀 다운로드'/데이터 미표시 = 당일 판매 상품 없음
        if not has_vendor:
            log(f"  [{a.label}] 판매분석·상품조회 모두 데이터 없음 — 건너뜀")
            session_state.observe_collection_empty(a.account_id)
            return None
        log(f"  [{a.label}] 판매분석 당일 데이터 없음 — 상품조회/수정 상품만 추적(vid 확보, 지표 0)")
        return [], {}

    try:
        return discover(b.page, date_from, date_to, log)   # 같은 세션에서 즉시 수집(지표)
    except PWTimeout:
        return _empty_or_skip()
    except Exception as exc:   # 신선 로그인 직후 페이지 미안착 → fetch 중단(Failed to fetch). wing 재안착 후 1회 재시도
        if "Failed to fetch" not in str(exc):
            raise
        log(f"  [{a.label}] discover fetch 중단(Failed to fetch) — wing 재안착 후 1회 재시도")
        b.goto(WING_URL)
        b.page.wait_for_timeout(2500)
        try:
            return discover(b.page, date_from, date_to, log)
        except PWTimeout:
            return _empty_or_skip()


def _augment_vids(b, a: Account, tracked, n_match: int, inv_names: dict, date_to, log):
    """대장에 있는데 당일 판매·방문 0이라 미매칭(vid 없음)인 상품 → 그로스 재고 vid + 최근 N일 판매분석
    vid 로 **정체(vid)만** 보강(지표는 당일 것만 기록 — 넓은기간 합계 미반영, 사용자 정책 2026-09-13).

    반환: (tracked, n_match). 미매칭이 없으면 그대로 반환(no-op)."""
    from .collector import fetch_sales_roster, SalesFetchError
    from .product_match import augment_unmatched
    if not any(not any(o.vendor_item_ids for o in tp.options) for tp in tracked):
        return tracked, n_match
    extra = _roster_from_names(inv_names, config.KIND_CONTRACT)   # 그로스 재고 roster(판매 무관 vid)
    try:
        d0 = (date.fromisoformat(date_to) - timedelta(days=config.SALES_VID_WINDOW_DAYS)).isoformat()
        extra += fetch_sales_roster(b.page, d0, date_to, log)     # 최근 N일 vid+이름(지표 미반영)
    except SalesFetchError as exc:   # 보강 실패는 비치명적 — 재고 roster 만으로 진행
        log(f"  [{a.label}] ⚠ vid 보강 {config.SALES_VID_WINDOW_DAYS}일 조회 실패(계속) — {str(exc)[:100]}")
    tracked, added = augment_unmatched(a.products, tracked, extra)
    n_match += added
    if added:
        log(f"  [{a.label}] 당일 미매칭 {added}개 vid 보강(그로스 재고/최근 {config.SALES_VID_WINDOW_DAYS}일 · 지표는 당일 유지)")
    return tracked, n_match


def _persist_session(a: Account, b, log) -> None:
    """로그인 성공 세션(3요소+쿠키[_abck 포함])을 영속 — 재사용·생존검증·데이터 HTTP 호출용.

    수집이 이미 끝난 뒤의 **부가 작업**이라, 실패해도 수집 결과엔 영향이 없다(사유를 명시 로그).
    ⚠️ is_alive/extract_vendor_id 의 엔드포인트는 사무실 라이브에서 최종 검증 대상.
    """
    try:
        alive = wing_session.is_alive(b.page)
        vid = wing_session.extract_vendor_id(b.page)
        SessionStore().save(a.account_id, wing_session.capture(b.context, vid))
        log(f"  [세션] 저장됨 (생존검증={alive}, vendorId={'추출' if vid else '미확인'})")
    except Exception as exc:
        log(f"  [세션] 영속 스킵 — {exc.__class__.__name__}: {str(exc)[:60]}")


def _roster_from_names(names_by_vid: dict, kind: str) -> list:
    """{옵션ID(vid): 등록상품명} → 매칭 후보 Product 목록(상품명으로 그룹, 옵션=vid).

    그로스 재고에서 얻은 **판매 무관 vid·상품명**을 scope_to_ledger/augment_unmatched 후보로 만든다
    (당일 판매 0인 그로스 상품의 vid 보강용). 지표는 없다 — 정체(vid) 보강 전용."""
    from .input_list import Option, Product
    by_name: dict[str, list[str]] = {}
    for vid, nm in (names_by_vid or {}).items():
        nm = (nm or "").strip()
        if nm and vid:
            by_name.setdefault(nm, []).append(str(vid))
    return [Product(name=nm, title=nm, kind=kind,
                    options=[Option("", [v]) for v in vids]) for nm, vids in by_name.items()]


def _vtag(vids) -> str:
    """로그용 **vid 태그**(오류·진행 추적 키). 여러 개면 '/'로 잇고, 없으면 '없음'.

    모든 상품/옵션 단위 로그 앞에 붙여 `grep vid=<값>` 으로 한 상품의 전 과정(수집→지표→키워드→순위→
    오류)을 추적할 수 있게 한다. vid 없는(미매칭) 상품은 vid=없음 → 등록상품명으로 추적한다."""
    vs = [str(v) for v in (vids or []) if v]
    return "vid=" + ("/".join(vs) if vs else "없음")


def _short(name: str, n: int = 30) -> str:
    """로그용 상품명 축약(길면 …). 내부 개행 제거."""
    s = " ".join(str(name or "").split())
    return s if len(s) <= n else s[:n] + "…"


def _ilog(log, tag: str, vids, name: str = "", msg: str = "", *, kind: str = "") -> None:
    """상품/옵션 단위 로그 **공통 포맷**(진행상황·디버깅용) — vid 를 **항상** 포함한다.

    형식: `  [{tag}] vid=.. [{상품명}][ [{kind}]][ {msg}]`. `grep "vid=<값>"` 한 번으로 그 상품의
    전 과정(발견→지표→재고→키워드→순위→오류)을 이어서 볼 수 있게 태그·vid 를 앞에 고정한다.
    name/kind/msg 는 있을 때만 붙는다. log 가 None 이면 무시(호출부 가드 불필요)."""
    if log is None:
        return
    parts = [f"[{tag}]", _vtag(vids)]
    if name:
        parts.append(_short(name))
    if kind:
        parts.append(f"[{kind}]")
    if msg:
        parts.append(msg)
    log("  " + " ".join(parts))


def _block_sale_status(sale_status, vids) -> str:
    """이 블록(옵션 vid 목록)의 **쿠팡 판매상태 문자열**을 판정 — 실행일 '판매상태' 지표행 기록용.

    sale_status = {vid: 판매상태 문자열('판매중'/'부분판매중'/'판매중지'/'임시저장'/'승인반려'/'검토중')} 또는
    {vid: isSaleSuspended bool}(RFM 폴백) 둘 다 지원. 블록 vid 중 상태맵에 있는 것만 보고: **모두 같으면
    그 상태·섞이면 부분판매중·하나도 없으면 ''(미상 → 기록 생략, 옛 값 보존)**. workbook.apply_sale_status
    의 블록 판정과 같은 규칙(단일 SSOT 아님 — 여기는 실행일 이력 기록, 거기는 최신 상태 저장)."""
    if not sale_status:
        return ""

    def _one(st) -> str:
        if isinstance(st, bool):
            return "판매중지" if st else "판매중"
        return str(st or "").strip()

    known = [s for s in (_one(sale_status[v]) for v in vids if v in sale_status) if s]
    if not known:
        return ""
    uniq = set(known)
    return next(iter(uniq)) if len(uniq) == 1 else "부분판매중"


def _fill_product_metrics(wb, biz, pname, vids, kind, metrics, inv_by_vid, date_iso,
                          log=None, sale_status=None) -> None:
    """**옵션(블록) 단위** 판매지표·재고·판매상태 기록 + **vid 기준 데이터 로그**(진행 추적).

    vids = 이 블록에 속한 옵션ID 목록(단일옵션·판매자배송=상품 전 옵션, 다중옵션=그 옵션 하나). 지표는
    vi-detail-search(metrics: vid→OptionMetric)에서, 재고는 RFM 재고 API(inv_by_vid: vid→수량)에서 vid 로
    조인해 이 블록 vid 들만 합산한다. 재고행은 kind 가 로켓그로스/둘다일 때만.
    **재고 규칙(소유자 2026-09-24 개정)**: 재고현황 API에 vid 있으면 수량(0=입고됐지만 품절) · **없으면
    판매중지 여부와 무관하게 '미입고'**(실입고 안 됨). 값 출처=재고현황 API만(상품조회 stockQuantity 금지).
    **판매상태(소유자 2026-09-24)**: 쿠팡 productStatus(sale_status)를 실행일 '판매상태' 지표행에 항상 기록
    (재고칸이 아니라 별도 지표행 — 쿠팡 상태 그대로 존중, 판매중지도 재고칸엔 미입고/값)."""
    views = sales = visitors = 0
    for oid in vids:
        m = metrics.get(oid)
        if m:
            views += m.views
            sales += m.sales
            visitors += m.visitors
    wb.set_product_metric(biz, pname, config.M_SALES, date_iso, sales)
    wb.set_product_metric(biz, pname, config.M_VISITORS, date_iso, visitors)
    wb.set_product_metric(biz, pname, config.M_VIEWS, date_iso, views)
    inv_txt = ""
    if kind in config.KINDS_WITH_INVENTORY:   # 재고현황 = 로켓그로스 + 둘다(로켓그로스 파트 있음)
        matched = [oid for oid in vids if inv_by_vid and oid in inv_by_vid]
        if matched:
            qty = sum(inv_by_vid[oid] for oid in matched)
            wb.set_product_metric(biz, pname, config.M_INVENTORY, date_iso, qty)   # 0=입고됐지만 품절
            inv_txt = f"·재고 {qty}"
        else:
            # 재고현황에 없음 = 로켓그로스 등록됐으나 물류센터 **미입고**(판매중지 여부 무관 · 재고 0=품절과 구분)
            wb.set_product_metric(biz, pname, config.M_INVENTORY, date_iso, config.INV_NOT_INBOUND)
            inv_txt = "·재고 미입고"
    status = _block_sale_status(sale_status, vids)   # 실행일 판매상태(쿠팡 존중·미상은 생략)
    if status:
        wb.set_product_metric(biz, pname, config.M_SALE_STATUS, date_iso, status)
    no_metric = [v for v in vids if v not in metrics]   # 당일 지표가 없는 vid(판매 0·미노출 등)
    _ilog(log, "지표", vids, pname,
          f"노출 {views}·판매 {sales}·방문 {visitors}{inv_txt}"
          + (f"·상태 {status}" if status else "")
          + (f" ⚠지표없는vid {no_metric}" if no_metric else ""), kind=kind)


def _log_diagnose(product, track_info, ai_key, log, wb=None, biz=None, roles=None, pname=None) -> None:
    """진단(제목포함×순위)·공략우선순위·역할·권고제목을 **로그로** 남긴다(새 서식엔 미기록, 셀러 참고용).

    track_info: [(키워드, 검색량, 경쟁정도, 순위)]. 새 서식은 검색량·순위만 기록하고, 이 분석은 로그로 제공.
    roles: {키워드: 역할}(REP/SALES/GROWTH/DEFENSE) — 새 상품 AI 선정 시에만. 동결 상품은 None.
    권고제목(⑤): 키워드 서명이 캐시와 같으면 AI 재호출 없이 재사용(동결 상품 매일 재생성 방지).
    """
    if not track_info:
        return
    title = product.display_title
    pname = pname or product.name
    roles = roles or {}
    for kw, vol, comp, rank in track_info:
        diag = diagnose_exposure(keyword_in_title(kw, title), rank, None)
        role = f" · 역할 {roles[kw]}" if kw in roles else ""
        log(f"  [진단] '{kw}': {diag} · 공략우선순위 {attack_priority(vol, comp_from_idx(comp))}"
            f" · 순위 {rank_label(rank)}{role}")
    kws_by_vol = [kw for kw, _v, _c, _r in sorted(track_info, key=lambda x: x[1], reverse=True)]
    sig = "|".join(sorted(kw for kw, *_ in track_info))   # 키워드 집합 서명(순서 무관)
    rec = ""
    if wb is not None and biz is not None:                 # ⑤ 캐시 재사용(키워드 동일 → 같은 제목)
        csig, ctitle = wb.title_cache(biz, pname)
        if csig == sig and ctitle:
            rec = ctitle
    if not rec:
        try:
            rec = recommend_title(title, kws_by_vol, api_key=ai_key)
        except KeywordAIError as exc:
            log(f"  [제목] 권고제목 생성 실패 — {exc.__class__.__name__}: {str(exc)[:60]}")
            rec = ""
        if rec and wb is not None and biz is not None:
            wb.set_title_cache(biz, pname, sig, rec)
    cov = round(sum(1 for kw, *_ in track_info if keyword_in_title(kw, title)) / len(track_info) * 100)
    log(f"  [제목] 현재: {title}")
    log(f"  [제목] 커버리지 {cov}% → 권고: {rec or '(생성실패)'}")


def _block_name(base: str, label: str) -> str:
    """블록 이름 = 등록상품명 + 옵션라벨(있을 때). 단일옵션·판매자배송(label='')은 등록상품명 그대로.

    다중옵션 상품을 옵션(vid)별 블록으로 분리할 때 각 블록의 이름을 만든다(소유자 확정: 쿠팡 등록상품명 +
    옵션라벨). 등록상품명은 안정 키(노출 SERP명 아님)라 cross-day 시계열이 안 끊긴다."""
    label = (label or "").strip()
    return f"{base} ({label})" if label else base


@dataclass
class _ProcCtx:
    """_process_account 한 계정 처리의 공유 인자(상품·옵션 루프가 이 컨텍스트로 동작)."""
    wb: OutputWorkbook
    naver: NaverAdApi
    ai_key: str | None
    browser: object
    metrics: object
    inv_by_vid: object
    date_iso: str
    grow: bool
    skip_ranks: bool
    keywords_off: bool
    log: object
    save_path: object
    sale_status: object = None   # {vid: 판매상태(문자열) 또는 isSaleSuspended(bool)} — 미입고/판매중지 구분용
    vid_meta: object = None       # {vid: (판매가, 판매시작일)} — 헤더 표시(상품판매가·로켓그로스 입고일 근사)
    pid_by_vid: object = None     # {vid: 노출상품ID(productId)} — 상품명 하이퍼링크(항목2·판매분석∪재고)


def _frozen_keywords(pctx: _ProcCtx, biz: str, pname: str, base: str, kind: str, title: str,
                     opt_vids, existing, measure, cap: dict):
    """기존 상품의 키워드 동결 경로 — 시트 키워드 그대로(grow=True면 상한 내 발굴 추가), 미기입 순위만 측정.

    반환: (keywords, ranks{키워드:순위}, track_info). 동결분은 검색량/경쟁 미측정(track_info 값 0/'').
    """
    wb, log = pctx.wb, pctx.log
    naver, ai_key, browser, grow, date_iso = pctx.naver, pctx.ai_key, pctx.browser, pctx.grow, pctx.date_iso
    keywords = list(existing)
    wb.ensure_product_block(biz, pname, kind, keywords, registered=base)   # no-op
    if grow and len(existing) < config.KW_MAX_TRACK and browser is not None:
        want = min(config.KW_ADD_PER_DAY, config.KW_MAX_TRACK - len(existing))
        found = select_keywords_light(title, naver, ai_key, browser=browser, log=log,
                                      n=want, measure_ranks=measure, exclude=set(existing))
        add = [t for t in found if t.keyword not in existing][:want]
        if add:
            wb.add_product_keywords(biz, pname, [t.keyword for t in add])
            for t in add:
                wb.set_keyword_search(biz, pname, t.keyword, t.volume)
            keywords += [t.keyword for t in add]
            _ilog(log, "키워드", opt_vids, title, f"→ 동결 {existing} + 발굴 {[t.keyword for t in add]}")
        else:
            _ilog(log, "키워드", opt_vids, title, f"→ (동결) {keywords}")
    else:
        _ilog(log, "키워드", opt_vids, title, f"→ (동결) {keywords}")
    _fill_frozen_search_volumes(wb, biz, pname, keywords, naver, log)  # 검색량 공란만 네이버로(fix ②)
    todo = [kw for kw in keywords if not wb.is_rank_filled(biz, pname, kw, date_iso)]
    measured = measure(todo, _cap=cap) if (browser is not None and todo) else {}
    ranks = {kw: _best(measured.get(kw)) for kw in todo if kw in measured}  # 측정 실패는 공란
    track_info = [(kw, 0, "", ranks.get(kw)) for kw in keywords]   # 동결분은 검색량/경쟁 미측정
    return keywords, ranks, track_info


def _resolve_keywords(pctx: _ProcCtx, biz: str, pname: str, base: str, kind: str, title: str,
                      opt_vids, measure, measure_cb, cap: dict):
    """대표 옵션의 키워드 확정 — 기존=동결(grow면 상한 내 발굴 추가), 새 상품=AI 선정.

    반환: (keywords, ranks{키워드:순위}, track_info[(kw,vol,comp,rank)], roles{키워드:역할}).
    선정 실패(AI 깨진 JSON·네이버 400 등)는 이 상품만 건너뛰고 빈 결과 반환(판매지표는 호출부가 계속 기록).
    """
    wb, log = pctx.wb, pctx.log
    naver, ai_key, browser, grow, date_iso = pctx.naver, pctx.ai_key, pctx.browser, pctx.grow, pctx.date_iso
    try:   # 한 상품의 키워드 선정 실패가 계정 전체를 막지 않게 격리
        existing = wb.product_keywords(biz, pname)
        if existing:                                   # 기존 상품 → 동결(역할 재판정 안 함)
            kws, ranks, track_info = _frozen_keywords(pctx, biz, pname, base, kind, title,
                                                      opt_vids, existing, measure, cap)
            return kws, ranks, track_info, {}
        # 새 상품 → AI 선정(skip_ranks면 순위 없이 부분점수)
        tracks = select_keywords_light(title, naver, ai_key, browser=browser, log=log,
                                       measure_ranks=measure_cb)
        keywords = [t.keyword for t in tracks]
        wb.ensure_product_block(biz, pname, kind, keywords, registered=base)
        for t in tracks:
            wb.set_keyword_search(biz, pname, t.keyword, t.volume)
        ranks = {t.keyword: t.exposure_best for t in tracks}          # 선정단계 순위 재사용
        track_info = [(t.keyword, t.volume, t.comp_idx, t.exposure_best) for t in tracks]
        roles = {t.keyword: t.role for t in tracks if t.role}         # ④ 역할(REP/SALES/GROWTH/DEFENSE)
        _ilog(log, "키워드", opt_vids, title,
              f"→ {[f'{t.keyword}({t.role})' if t.role else t.keyword for t in tracks]}")
        return keywords, ranks, track_info, roles
    except Exception as exc:   # 이 상품만 건너뜀(판매지표·재고는 호출부가 계속 기록). 계정은 완주.
        _ilog(log, "오류", opt_vids, title,
              f"키워드 처리 실패(건너뜀, 판매지표는 기록) — {exc.__class__.__name__}: {str(exc)[:80]}")
        wb.ensure_product_block(biz, pname, kind, wb.product_keywords(biz, pname), registered=base)
        return [], {}, [], {}


def _apply_vid_meta(wb, biz: str, pname: str, kind: str, opt_vids, vid_meta, date_iso,
                    inbound_summary: str = "") -> None:
    """이 옵션(블록)의 판매가·로켓그로스 판매일·최근입고를 기록(소유자 2026-09-24).

    **판매가**=이 블록 옵션(첫 vid) salePrice → **'판매가' 지표행(재고현황 아래)에 일자별** 기록(마케팅 일환
    변동 추적). **로켓그로스 판매일**(판매시작일 근사)+**최근입고 요약**(관리대장)=로켓그로스/둘다만 → 헤더에
    묶어 표시(판매자배송은 로켓그로스 개념 없어 생략). vid_meta 비어도 최근입고(대장)는 반영."""
    price = None
    started = ""
    if vid_meta:
        for v in opt_vids:
            if v in vid_meta:
                price, started = vid_meta[v]
                break
    if isinstance(price, (int, float)) and price > 0:
        wb.set_product_metric(biz, pname, config.M_SALE_PRICE, date_iso, price)   # 판매가 지표행(일자별)
    wb.set_product_kind(biz, pname, kind)   # 판매방식(메타 col11) — 레이아웃 v4 헤더 '판매방식' 줄 표시용
    is_rg = kind in config.KINDS_WITH_INVENTORY
    inbound = started if is_rg else None
    summ = inbound_summary if (is_rg and inbound_summary) else None
    if inbound or summ:
        wb.set_product_extra(biz, pname, inbound_date=inbound, inbound_summary=summ)   # 헤더 로켓그로스 묶음


def _apply_pid(wb, biz: str, pname: str, opt_vids, pid_by_vid) -> None:
    """이 블록의 옵션 vid 중 하나로 노출상품ID(productId)를 찾아 저장(항목2 상품명 하이퍼링크).

    productId 는 상품(노출페이지) 단위라 같은 상품의 옵션 vid 는 같은 값을 공유 → 첫 매칭 vid 로 충분.
    소스=판매분석∪재고(상품조회엔 공개 productId 없음). 없으면 no-op(검색 링크 폴백 유지)."""
    if not pid_by_vid:
        return
    pid = next((pid_by_vid[v] for v in opt_vids if v in pid_by_vid), "")
    if pid:
        wb.set_product_pid(biz, pname, pid)


def _process_option(pctx: _ProcCtx, biz: str, product, base: str, kind: str, title: str,
                    i: int, opt, multi: bool) -> None:
    """상품의 옵션(vid) 한 개를 기록. 대표(i==0)=키워드/순위/지표, 2차 옵션=판매정보(지표·재고)만.

    keywords_off(①판매수집)면 대표도 지표·재고·vid만(키워드는 ②, 순위는 ③). 상품마다 저장(중단 복구).
    """
    wb, log = pctx.wb, pctx.log
    is_rep = (i == 0)
    pname = _block_name(base, opt.label if multi else "")
    opt_vids = list(opt.vendor_item_ids)
    if pctx.keywords_off or not is_rep:
        # ① 판매수집 단계, 또는 다중옵션 2차 블록 → 지표·재고·vid만(키워드/순위 없음, rank_rows=is_rep)
        wb.ensure_product_block(biz, pname, kind, wb.product_keywords(biz, pname),
                                rank_rows=is_rep, registered=base)
        wb.set_product_vids(biz, pname, opt_vids)
        _apply_pid(wb, biz, pname, opt_vids, pctx.pid_by_vid)   # 노출상품ID(항목2 하이퍼링크·판매분석∪재고)
        _apply_vid_meta(wb, biz, pname, kind, opt_vids, pctx.vid_meta, pctx.date_iso, product.inbound_summary)   # 판매가 지표행·판매일/최근입고 헤더
        _fill_product_metrics(wb, biz, pname, opt_vids, kind, pctx.metrics, pctx.inv_by_vid,
                              pctx.date_iso, log=log, sale_status=pctx.sale_status)
        wb.save(pctx.save_path)
        return
    # ── 대표 옵션(단일옵션 포함): 키워드 동결/선정 → 순위 → 지표 → 진단 ──
    naver, ai_key, browser, grow = pctx.naver, pctx.ai_key, pctx.browser, pctx.grow
    skip_ranks, date_iso = pctx.skip_ranks, pctx.date_iso
    pmatcher = {"제품": _product_matcher(product)}   # 순위 매칭 = 리스팅 전 옵션 vid(아이템위너 놓침 방지)

    def measure(kws, _m=pmatcher, _cap=None):
        return _measure_safe(browser, kws, _m, log, matched_out=_cap)   # 순위 실패해도 판매데이터 완주

    measure_cb = measure if (browser is not None and not skip_ranks) else None
    cap: dict = {}   # 매칭된 검색결과 항목(노출명) 회수용
    keywords, ranks, track_info, roles = _resolve_keywords(
        pctx, biz, pname, base, kind, title, opt_vids, measure, measure_cb, cap)

    if not skip_ranks:                             # 순위 기록(PC). 날짜지정 수집(skip_ranks)은 순위 제외
        # 차단된 실행이면 미측정(None)을 '50위'로 위장 기록하지 않고 **공란**으로 남긴다 →
        # is_rank_filled=False 유지 → 다음(쉰 IP) 실행이 그 순위만 재측정.
        blocked = _RANK_HALT["stop"]
        for kw in keywords:                        # 이미 채워진 건 건너뜀
            if kw not in ranks or wb.is_rank_filled(biz, pname, kw, date_iso):
                continue
            if ranks.get(kw) is None and blocked:  # 차단으로 못 잰 값 → 공란(재측정 대상)
                continue
            wb.set_keyword_rank(biz, pname, kw, date_iso, ranks.get(kw))
            _ilog(log, "순위", opt_vids, "", f"'{kw}': {rank_label(ranks.get(kw))}")
        # ⚠ set_display_name(노출명 교체) 중단 — 블록 이름을 등록상품명+옵션라벨로 고정(옵션 정체성 안정).
        mi = cap.get("제품")                        # 노출명은 로그로만(블록명은 등록상품명 유지)
        if mi is not None and getattr(mi, "name", ""):
            _ilog(log, "노출명", opt_vids, "", f"검색결과 노출명 = {_short(mi.name, 40)} (블록명은 등록상품명 고정)")
            wb.set_product_pid(biz, pname, getattr(mi, "product_id", ""))   # 항목3: 상품명 하이퍼링크용 productId
    wb.set_product_vids(biz, pname, opt_vids)          # 대표 옵션 vid 저장(③은 sibling_vids 합집합으로 매칭)
    _apply_pid(wb, biz, pname, opt_vids, pctx.pid_by_vid)   # 노출상품ID(항목2·판매분석∪재고·순위매칭 pid보다 완전)
    _apply_vid_meta(wb, biz, pname, kind, opt_vids, pctx.vid_meta, pctx.date_iso, product.inbound_summary)   # 판매가 지표행·판매일/최근입고 헤더
    _fill_product_metrics(wb, biz, pname, opt_vids, kind, pctx.metrics, pctx.inv_by_vid, date_iso,
                          log=log, sale_status=pctx.sale_status)
    _log_diagnose(product, track_info, ai_key, log, wb=wb, biz=biz, roles=roles, pname=pname)
    wb.save(pctx.save_path)


def _migrate_product_blocks(wb, biz: str, base: str, rep_name: str, vids_all, opts, multi: bool,
                            log) -> None:
    """정체성/마이그레이션(소유자 2026-09-20: vid=상품당 1개).

    ① **같은 vid** = 같은 상품 → 기존 블록 승계 + 이름을 등록상품명으로 정규화(set_display_name 은
       중단됐으니 이 한 번만). ② **등록상품명은 같은데 vid 가 다른**(교집합 없는) 옛 블록 = 정체성 바뀜
       → **이전 데이터 삭제하고 새로 시작**(잘못된 이력 승계 방지). vid 없는 복원 잔재 블록도 대체 삭제한다
       (단 이번에 이어쓸 블록·미매칭 상품은 보존).
    """
    vidset = set(vids_all)
    old = wb.resolve_block_name(biz, vids_all)   # 새 vid 와 교집합 있는 기존 블록(같은 vid)
    if old and old != rep_name and not wb.has_product(biz, rep_name):
        if wb.set_display_name(biz, old, rep_name):
            log(f"  [정체성] 기존 블록 '{old}' → '{rep_name}'(같은 vid·과거 이력 승계·이름 정규화)")
    new_names = {_block_name(base, o.label if multi else "") for o in opts}   # 이번에 쓸(이어쓸) 블록
    for stale in wb.blocks_with_registered_name(biz, base):
        stored = set(wb.product_vids(biz, stale))
        # ① vid 가 바뀐 옛 블록(교집합 없음) = 정체성 변경 → 삭제·새로 시작(단일옵션 동일이름도 삭제 후 재생성).
        changed_vid = bool(vidset and stored and not (vidset & stored))
        # ② 구글시트 복원 잔재: 옛 블록에 vid 가 **없는데** 이번에 vid 있는 옵션 블록을 새로 만든다 = pre-vid 잔재
        #    → 삭제. 단 **이번에 이어쓸 블록(new_names)** 과 **미매칭 상품(vidset 비었음)** 은 보존.
        legacy_novid = bool(vidset and not stored and stale not in new_names)
        if changed_vid or legacy_novid:
            if wb.delete_product_block(biz, stale):
                why = (f"vid 변경(이전 {sorted(stored)} → {vids_all})" if changed_vid
                       else f"vid 없는 옛 블록 잔재(복원분) → 옵션 블록 {vids_all} 로 대체")
                log(f"  [정체성] '{stale}' {why} → 이전 데이터 삭제·새로 시작")


def _purge_upbundle_blocks(wb, biz: str, upbundle_vids, log) -> None:
    """이번 상품조회의 **업번들(자동번들) vid** 집합으로 마스터의 옛 업번들 잔재 블록을 삭제(소유자 2026-09-24).

    업번들 옵션은 수집 단계에서 이미 추적 제외되지만(products_from_vendor_inventory), 리스팅 전체가 업번들이면
    그 상품이 추적에서 통째 빠져 마스터 블록이 **고아**로 남아 reconcile 이 '판매중지'로 표기하는 clutter 가
    생긴다. 그 잔재를 매 수집마다 정리한다. **vid 기준**(이름패턴 '(N개)' 아님 — 색상/사이즈 변형 오삭제 방지):
    블록의 vid 가 **전부** 업번들 vid 면 삭제. vid 없는 블록·일반 옵션 블록(실vid)은 보존. 상품조회 실패로
    upbundle_vids 가 비면 no-op(잘못된 삭제 방지)."""
    if not upbundle_vids or biz not in wb.wb.sheetnames:
        return
    for p in list(wb.products_of(biz)):
        vids = wb.product_vids(biz, p)
        if vids and all(v in upbundle_vids for v in vids):
            if wb.delete_product_block(biz, p):
                log(f"  [정체성] '{p}' 업번들(자동번들) 잔재 블록 삭제(vid {vids} 전부 업번들·원상품 재고공유)")


def _sweep_dead_duplicates(wb, biz: str, live_vids, log) -> None:
    """**죽은 중복 블록**만 정리 — 안전 규칙(소유자 2026-09-24). 두 조건을 **모두** 만족할 때만 삭제:

    (a) **같은 상품군(블록명 접두=옵션라벨 앞부분)에 live 형제 존재**(vid 가 이번 상품조회에 있는 블록) AND
    (b) 그 블록 vid 가 **전부 이번 상품조회(live_vids)에 없음**(코팡서 사라진 죽은 등록).

    → 재등록으로 죽은 옛 vid 유령(R601_/__/…)만 제거하고, **판매중지 단독 상품·색상/사이즈 변형·코팡에
    남아있는 vid(판매자배송 twin 포함)·신규는 전부 보존**(reconcile 이 판매중지 표기). 상품조회 실패로 live_vids
    비면 no-op(오삭제 방지). **그룹 키=마스터 블록명 접두**(등록상품명/발견명 드리프트에 무관 — vid 앵커로 live 판정).
    같은 상품군에 live 형제가 없으면(그룹 전체가 코팡서 소멸=판매중지 단독) 통째 보존."""
    if not live_vids:
        return
    groups: dict = {}   # 블록명 접두 → [블록명…] (색상/사이즈/재등록 형제가 한 군)
    for p in wb.products_of(biz):
        prefix = p.rsplit(" (", 1)[0] if " (" in p else p
        groups.setdefault(prefix, []).append(p)
    for prefix, blocks in groups.items():
        if len(blocks) < 2:
            continue   # 형제 없는 단독 블록(판매중지 단독 포함) → 보존
        has_live = any(any(v in live_vids for v in wb.product_vids(biz, b)) for b in blocks)
        if not has_live:
            continue   # 그룹 전체가 코팡서 소멸 → 판매중지 단독군 → 통째 보존
        for b in blocks:
            vids = wb.product_vids(biz, b)
            # 🔒 정책(소유자 2026-09-24): **판매자배송(NORMAL) twin 은 삭제하지 않고 보존**한다.
            # 같은 상품을 로켓그로스+판매자배송 둘 다 등록하면 vid 가 2개(RFM/NORMAL) 생기고, 추적은 RFM 만
            # 하지만 NORMAL twin 도 **코팡 상품조회에 살아있는 vid** 라 아래 'vid 전부 소멸' 조건에 안 걸린다
            # → 판매중지 표기로 남겨 보존(데이터 유실 방지). 완전 제거는 registrationType 배선이 필요한 별도 후속.
            if vids and all(v not in live_vids for v in vids):   # 코팡서 완전 소멸한 vid만(=죽은 재등록)
                if wb.delete_product_block(biz, b):
                    log(f"  [정체성] '{b}' 죽은 중복 블록 삭제(vid {vids} 상품조회에 없음·live 형제 존재)")


def _process_account(report_acc, wb, naver, ai_key, browser, metrics, inv_by_vid,
                     date_iso, grow, log, save_path, skip_ranks: bool = False,
                     keywords_off: bool = False, sale_status=None, upbundle_vids=None,
                     live_vids=None, vid_meta=None, pid_by_vid=None) -> None:
    """계정(시트) 하나: 상품마다 **옵션 블록**을 만들고 [대표=키워드/순위/지표, 2차=지표만] 기록·저장.

    다중옵션 상품은 옵션(vid)별 블록으로 분리한다 — **대표(첫 옵션)** 만 키워드 동결/선정·순위(리스팅 단위)를
    담고, 나머지 옵션 블록은 판매정보(지표·재고)만(순위행 없음). 단일옵션은 대표 하나(기존과 동일).
    - 기존 상품(대표 블록에 키워드 있음): **키워드 동결**, 순위만 조회(grow=True면 상한 내 발굴 추가).
    - 새 상품: AI 선정 + 선정단계 순위 재사용. 순위 매칭은 리스팅 전 옵션 vid(놓침 방지).
    - skip_ranks=True(날짜 지정 수집): 쿠팡 순위 조회를 제외(browser=None). 판매지표·재고만.
    - keywords_off=True(① 판매수집 단계): 모든 옵션 블록에 지표·재고·vid만(키워드는 ②, 순위는 ③).
    - upbundle_vids: 이번 상품조회의 업번들 vid 집합 → 마스터 잔재 업번들 블록 자동삭제(reconcile 전).
    - live_vids: 이번 상품조회 전체 vid 집합 → **죽은 중복 블록** 정리(같은 등록상품명 live 형제 있고 vid 소멸한
      것만·판매중지 단독/변형/신규 보존, reconcile 전). 상품조회 실패면 빈 집합(정리 skip).
    상품마다 save_path 저장 → 도중 끊겨도 이어감.
    """
    from .input_list import Option
    biz = report_acc.label   # 시트명 = 사업자명, 없으면 대표자명·계정ID(빈 시트명 KeyError 방지)
    wb.ensure_account(biz)
    _purge_upbundle_blocks(wb, biz, upbundle_vids, log)   # 옛 업번들 잔재 정리(reconcile 판매중지 표기 전)
    seen_products: list[str] = []          # 이번 대장에 존재한 옵션 블록명 — 대조로 판매중지 감지
    for product in report_acc.products:
        title = product.display_title
        kind = product.kind or config.KIND_PERSONAL
        opts = list(product.options) or [Option("")]
        multi = len(opts) > 1                           # 옵션 라벨은 **다중옵션에만** 붙인다(단일옵션=등록상품명 그대로)
        base = product.name                            # 등록상품명(vendor-inventory) = 블록 기준명
        vids_all = [oid for o in opts for oid in o.vendor_item_ids]
        rep_name = _block_name(base, opts[0].label if multi else "")
        _migrate_product_blocks(wb, biz, base, rep_name, vids_all, opts, multi, log)
        # 수집 주기·마케팅은 상품(대표) 단위. 오늘 대상 아니면 이 상품의 모든 옵션 블록을 오늘치 생략.
        if product.mkt_start or product.mkt_end or product.mkt_mon:   # 대장에 마케팅 값 있을 때만 반영
            wb.set_marketing(biz, rep_name, product.mkt_start, product.mkt_end, product.mkt_mon)
        if wb.has_marketing():
            _due, _why = wb.product_due(biz, rep_name, date_iso)
            if not _due:
                log(f"  [{title}] {_why} — 오늘 수집 생략(상품 주기)")
                for o in opts:
                    seen_products.append(_block_name(base, o.label if multi else ""))   # 있음(오늘 스킵돼도 '있음')
                continue
        # ── 옵션 블록 루프: 대표(i==0)만 키워드/순위, 나머지는 판매정보만 ──
        pctx = _ProcCtx(wb=wb, naver=naver, ai_key=ai_key, browser=browser, metrics=metrics,
                        inv_by_vid=inv_by_vid, date_iso=date_iso, grow=grow, skip_ranks=skip_ranks,
                        keywords_off=keywords_off, log=log, save_path=save_path, sale_status=sale_status,
                        vid_meta=vid_meta, pid_by_vid=pid_by_vid)
        for i, opt in enumerate(opts):
            bname = _block_name(base, opt.label if multi else "")
            seen_products.append(bname)
            _process_option(pctx, biz, product, base, kind, title, i, opt, multi)
            wb.set_product_account_id(biz, bname, report_acc.account_id)   # 항목5: 상품별 계정ID 태깅(다계정ID 사업자)
    # 죽은 중복 블록 정리(안전 규칙): live 형제 있고 vid 가 상품조회서 소멸한 잔재만 삭제(reconcile 판매중지 표기 전)
    _sweep_dead_duplicates(wb, biz, live_vids, log)
    # 대장 대조(항목⑥, 소유자 2026-09-25): **줄이 완전히 사라진 상품 = 이력 포함 완전삭제**(백업 안전망),
    # 대장에 **판매중지/취소선으로 남은(줄 존재)** 상품 = 판매중지 표기 유지. ledger_products=줄 존재 전체.
    newly, deleted = wb.reconcile_account(biz, seen_products, report_acc.ledger_products,
                                          delete_missing=True, account_id=report_acc.account_id)   # 항목5: 계정ID 스코핑
    if deleted:
        log(f"  [SYNC] [{biz}] 관리대장에서 줄이 사라진 상품 {len(deleted)}개 → 완전삭제(이력 포함·백업 보존): "
            f"{deleted[:3]}{'…' if len(deleted) > 3 else ''}")
    if newly:
        log(f"  [{biz}] 대장에 판매중지로 남은 상품 {len(newly)}개 → 판매중지 표기(유지): "
            f"{newly[:3]}{'…' if len(newly) > 3 else ''}")
    wb.save(save_path)


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

    if not skip_ranks and not keywords_off:   # 노출순위 미처리분 자동 재시도(쿨다운·진전없으면 중단).
        # ⚠ keywords_off(①판매수집 전용)는 순위를 절대 다루지 않으므로 백필도 하지 않는다(과거 resume가
        #    skip_ranks=False를 물려받으면 ①이 헛도는 offscreen 백필을 시도하던 잠재버그 방지).
        _backfill_ranks(wb, partial, log, was_blocked=_RANK_HALT["stop"])

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

