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
import shutil
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config
from . import human_mouse
from .browser import WING_URL, WingBrowser
from .input_list import Account, InputList, InputValidationError, validate_input_list
from . import wing_session
from . import session_state
from .kw_ai import KeywordAIError, recommend_title
from .kw_recommend import (attack_priority, comp_from_idx, diagnose_exposure,
                           keyword_in_title, rank_label, select_keywords_light)
from .kw_volume import NaverAdApi
from .rank import RankBlocked, human_type_query, make_matcher, organic_ranks, organic_ranks_batch, warmup
from .session_store import SessionStore
from .workbook import OutputWorkbook

_PROFILE = "data/chrome-pipeline"   # 검색 순위용(비로그인)
_PROFILES_DIR = "data/profiles"     # 계정별 로그인 프로필
# 진행 중(미완료) 통합 엑셀 + 진행 상태(같은 날 크래시 복구용). 완료되면 상태파일 삭제.
_PARTIAL_XLSX = f"{config.OUTPUT_FILE_PREFIX}_진행중.xlsx"
_PROGRESS_JSON = f"{config.OUTPUT_FILE_PREFIX}_진행중.json"
# 통계 마스터(지속형) — 매일 실행이 이어써서 날짜 컬럼을 누적하고 키워드를 동결한다.
_MASTER_XLSX = f"{config.OUTPUT_FILE_PREFIX}_통계.xlsx"
# 전체실행/무인의 **진행 단계** 마커(재부팅 복구용) — ②③은 진행중 파일을 안 만드므로 별도로 단계를 남긴다.
_RUN_STAGE_JSON = f"{config.OUTPUT_FILE_PREFIX}_실행단계.json"


def _partial_path(out_dir: str | Path) -> Path:
    return Path(out_dir) / _PARTIAL_XLSX


def _progress_path(out_dir: str | Path) -> Path:
    return Path(out_dir) / _PROGRESS_JSON


def _master_path(out_dir: str | Path) -> Path:
    return Path(out_dir) / _MASTER_XLSX


def _snapshot_path(out_dir: str | Path, now: datetime) -> Path:
    """그날 완료본 스냅샷(감사·백업용). 마스터가 손상돼도 날짜별 본이 남는다."""
    return Path(out_dir) / f"{config.OUTPUT_FILE_PREFIX}_통계_{now.strftime('%y%m%d')}.xlsx"


def master_exists(out_dir: str | Path = "output") -> bool:
    """이어쓸 통계 마스터가 있는지(UI가 '기존 통계에 추가' 옵션 노출 여부 판단)."""
    return _master_path(out_dir).exists()


def restore_master_from_gsheet(out_dir: str | Path, url: str | None, on_log=None) -> bool:
    """통계 마스터(_통계.xlsx)가 없을 때 **결과 구글시트(전체 미러)에서 통째로 내려받아 복원**.

    다른 PC·재설치로 마스터가 없으면 '첫 실행'으로 오판해 과거 날짜 컬럼(시계열)을 유실한다 → 결과
    구글시트가 있으면 export(xlsx)로 마스터를 복원해 이어쓴다(소유자 2026-09-20, fix ③).
    ⚠ 구글시트는 **가시 시트(계정목록·사업자별 통계)만** 미러라 숨김 메타(_상품ID/_마케팅 등)는 없다
    → 복원본은 과거 '값(시계열)'을 살리고, 숨김 메타는 다음 ①판매수집이 재구성(vid 재발견·대장 매칭).
    성공=True(이어쓰기), 실패=사유 로그 후 False(정상 첫 실행 — fallback 금지 원칙에 따라 조용히 넘기지 않음).
    """
    log = on_log or (lambda m: None)
    master = _master_path(out_dir)
    if master.exists() or not url:
        return False
    try:
        from . import gsheet
        gsheet.download_xlsx(url, master)
        OutputWorkbook.load(master)          # 유효한 워크북인지 확인(빈/손상 파일이면 예외 → 첫 실행)
    except Exception as exc:
        if master.exists():
            try:
                master.unlink()              # 손상 파일 잔재 제거(다음 저장이 깨끗한 첫 실행으로)
            except OSError:
                pass
        log("== ⚠ 마스터가 없어 결과 구글시트에서 복원을 시도했으나 실패 — 새 통계로 시작합니다 "
            f"({exc.__class__.__name__}: {str(exc)[:120]}) ==")
        return False
    _strip_gsheet_index_tab(master, log)   # 복원본에 섞여온 인덱스 탭 '계정목록'(공백 없음) 제거(오염 방지)
    log(f"== 마스터 파일이 없어 결과 구글시트에서 복원했습니다 → {master.name} "
        "(과거 통계 이어쓰기 · 숨김 메타는 다음 판매수집이 재구성) ==")
    return True


def _strip_gsheet_index_tab(master: Path, log) -> None:
    """복원 마스터에서 **결과 구글시트의 인덱스 탭 '계정목록'(공백 없음)** 을 제거한다.

    결과 구글시트를 통째로 내려받으면 인덱스 탭 `계정목록`(gsheet_index.INDEX_SHEET_NAME, 공백 없음)까지 딸려온다.
    마스터 자체 인덱스는 `계정 목록`(공백 있음)이라, 이 탭을 두면 account_sheets 가 통계로 오인 → 미러링 중복 +
    계정목록 동기화 충돌(400). 복원 직후 지운다(마스터 인덱스는 다음 저장이 다시 만든다). 방어=account_sheets 도
    공백 무시로 제외하지만, 파일에 남겨두지 않는 게 깔끔하다."""
    import openpyxl
    from .gsheet_index import INDEX_SHEET_NAME   # '계정목록'(공백 없음)
    try:
        wb = openpyxl.load_workbook(master)
        if INDEX_SHEET_NAME in wb.sheetnames and len(wb.sheetnames) > 1:
            del wb[INDEX_SHEET_NAME]
            wb.save(master)
            log(f"  [복원] 구글시트 인덱스 탭 '{INDEX_SHEET_NAME}' 제거(마스터 자체 인덱스와 중복 방지)")
        wb.close()
    except Exception as exc:   # 실패해도 복원 자체는 유효(account_sheets 방어가 있음) — 조용히 넘기지 않고 로그
        log(f"  [복원] ⚠ 인덱스 탭 정리 건너뜀 — {exc.__class__.__name__}: {str(exc)[:80]}")


def backup_sources(out_dir: str | Path = "output", *, input_url: str | None = None,
                   output_url: str | None = None, on_log=None) -> list[Path]:
    """작업 시작 전 원본 백업 — **로컬 통계 마스터 + 결과 구글시트 + 관리대장 구글시트**를 타임스탬프
    로컬 xlsx 로 `output/백업/` 에 저장한다(소유자 2026-09-20: 항상 작업 전 별도 백업 후 진행).

    실패는 **로그로 명시**하되 작업을 막지 않는다(백업 실패 ≠ 작업 중단, 하지만 조용히 넘기지 않음).
    구글시트 백업은 export(xlsx)라 SA 없이도 공개공유면 됨. 반환=저장된 백업 파일 목록.
    """
    log = on_log or (lambda m: None)
    out = Path(out_dir)
    bdir = out / "백업"
    ts = datetime.now().strftime("%y%m%d_%H%M%S")
    saved: list[Path] = []
    try:
        bdir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log(f"== [백업] ⚠ 백업 폴더 생성 실패 — 백업 없이 진행: {exc} ==")
        return saved
    # 1) 로컬 통계 마스터(있으면)
    master = _master_path(out)
    if master.exists():
        dest = bdir / f"통계마스터_{ts}.xlsx"
        try:
            shutil.copy(master, dest)
            saved.append(dest)
            log(f"== [백업] 통계 마스터 → 백업/{dest.name} ==")
        except OSError as exc:
            log(f"== [백업] ⚠ 통계 마스터 백업 실패(진행): {exc} ==")
    # 2) 결과·관리대장 구글시트(있으면)
    for label, url in (("결과시트", output_url), ("관리대장", input_url)):
        if not url:
            continue
        dest = bdir / f"{label}_{ts}.xlsx"
        try:
            from . import gsheet
            gsheet.download_xlsx(url, dest)
            saved.append(dest)
            log(f"== [백업] {label} 구글시트 → 백업/{dest.name} ==")
        except Exception as exc:   # 공개공유 아님·네트워크 등 → 명시 후 진행(작업은 계속)
            log(f"== [백업] ⚠ {label} 구글시트 백업 실패(진행): {exc.__class__.__name__}: {str(exc)[:120]} ==")
    if saved:
        log(f"== [백업] 작업 전 원본 {len(saved)}개 백업 완료(output/백업/) ==")
    return saved


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


def _run_stage_path(out_dir: str | Path) -> Path:
    return Path(out_dir) / _RUN_STAGE_JSON


def write_run_stage(stage: str, out_dir: str | Path = "output") -> None:
    """전체실행/무인의 진행 단계를 오늘 날짜로 기록(재부팅 복구용).

    stage: 'sales'=①판매수집 완료(다음=②) · 'ranks'=②키워드 완료(다음=③) · 'done'=전부 완료.
    ②③은 마스터에 직접 쓰고 진행중 파일을 안 남기므로, 이 마커로 어디까지 했는지 남긴다.
    """
    try:
        _run_stage_path(out_dir).write_text(
            json.dumps({"date": datetime.now().strftime("%Y-%m-%d"), "stage": stage,
                        "at": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False),
            encoding="utf-8")
    except OSError:
        pass


def read_run_stage(out_dir: str | Path = "output") -> dict | None:
    """오늘의 진행 단계 마커(dict) 반환 — 없거나 어제 이전이면 None(오늘 것만 유효)."""
    p = _run_stage_path(out_dir)
    if not p.exists():
        return None
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(m, dict) or m.get("date") != datetime.now().strftime("%Y-%m-%d"):
        return None
    return m


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


def _best(pair) -> int | None:
    """(ranks_pc, ranks_mobile) → 최상위 순위(없으면 None). 새 서식은 상품 단일 매처라 값 1개."""
    if not pair:
        return None
    pc, mo = pair
    vals = [v for v in (*pc.values(), *mo.values()) if v]
    return min(vals) if vals else None


# 순위 차단(Akamai 챌린지) 감지 시 이번 실행의 순위 조회를 전면 중단(더 두드리지 않음). 실행마다 리셋.
_RANK_HALT = {"stop": False}
# 서킷브레이커 — 이번 실행에 쓴 cooldown 횟수(상한 초과 시 당일 중지). 실행마다 리셋.
_RANK_CB = {"cooldowns": 0}
_RANK_TELEMETRY_ID = "__rank__"   # 순위 응답 관측용 합성 계정ID(session_events 에 rank_* 이벤트)


def _reset_rank_state() -> None:
    """실행 시작 시 순위 차단 상태 초기화 — halt 플래그 해제 + 서킷브레이커 cooldown 카운터 리셋."""
    _RANK_HALT["stop"] = False
    _RANK_CB["cooldowns"] = 0


def _rank_cooldown(browser, log, reason: str) -> bool:
    """이상징후 → 신규검색 중지 → 충분한 cooldown → (홈 1회 = 소량 정상요청). 재개 가능하면 True.

    cooldown 반복이 상한(RANK_COOLDOWN_MAX) 초과면 당일 중지(False). 우회 재요청은 하지 않는다 —
    호출부가 True면 같은 검색을 1회 재측정(=probe)해 정상 여부를 확인한다.
    """
    _RANK_CB["cooldowns"] += 1
    if _RANK_CB["cooldowns"] > config.RANK_COOLDOWN_MAX:
        _RANK_HALT["stop"] = True
        log(f"  [노출측정] ⛔ 이상징후 반복({reason}) — cooldown {config.RANK_COOLDOWN_MAX}회 초과, "
            "당일 중지. 쉰 시간/IP에 다시 실행하면 남은 것부터 이어서")
        return False
    cd = config.RANK_COOLDOWN_SEC
    log(f"  [노출측정] ⚠ 이상징후 감지({reason}) → 신규검색 즉시 중지, {cd // 60}분 cooldown 후 "
        f"probe(재측정)로 상태확인 (cooldown {_RANK_CB['cooldowns']}/{config.RANK_COOLDOWN_MAX})")
    time.sleep(cd)
    try:
        warmup(browser)          # 홈 1회(신뢰쿠키 갱신) = 소량 정상요청
    except Exception:
        pass
    return True


class RankHalt(Exception):
    """순위 조회 중 차단 감지 → 즉시 중단 신호. `.partial` = 중단 전까지 측정된 {키워드:(pc,mo)}."""
    def __init__(self, partial=None):
        super().__init__("순위 차단 감지 — 중단")
        self.partial = partial or {}


def _measure_nav_serial(browser, keywords, matchers, log, matched_out=None):
    """기본(안전) 순위 측정 — **사람처럼 검색창을 하나씩** 직렬 네비게이션 + 랜덤 간격(RANK_NAV_DELAY).

    **서킷브레이커**: 이상징후(응답시간 급증 RANK_SLOW_ABS_SEC↑ · 403/429/Akamai 챌린지 RankBlocked)를
    감지하면 신규검색을 즉시 중지하고 충분한 cooldown(RANK_COOLDOWN_SEC) 후 같은 검색을 1회 재측정(probe)한다.
    정상이면 재개, 또 이상이면 cooldown 반복(상한 RANK_COOLDOWN_MAX)→초과 시 당일 중지(_RANK_HALT)+RankHalt.
    우회 재요청은 하지 않는다. 각 응답은 관측층에 기록(rank_ok/rank_empty/rank_challenge).
    matched_out 를 주면 매칭된 검색결과 항목(정확 노출명 포함)을 채워 호출부가 노출명 갱신에 쓴다.
    """
    pc: dict = {}
    for i, kw in enumerate(keywords):
        if _RANK_HALT["stop"]:
            break
        if i > 0:   # 검색 사이 사람 간격(버스트 제거 = 차단 회피)
            d = random.uniform(config.RANK_NAV_DELAY_MIN_SEC, config.RANK_NAV_DELAY_MAX_SEC)
            log(f"  [노출측정] 다음 검색까지 {d:.0f}s 대기(사람 속도)")
            time.sleep(d)
        while True:   # 이상징후 → cooldown 후 같은 kw 재측정(probe). 반복 상한 초과면 당일 중지.
            try:
                t0 = time.monotonic()
                r = organic_ranks(browser, kw, matchers, log=log, matched_out=matched_out)
                dt = time.monotonic() - t0
                if dt >= config.RANK_SLOW_ABS_SEC:      # 응답시간 급증 = 이상징후(조기감지)
                    if not _rank_cooldown(browser, log, f"응답 {dt:.0f}s 급증"):
                        raise RankHalt({k: (pc[k], {}) for k in pc})
                    continue                            # cooldown 후 같은 kw 재측정(probe)
                pc[kw] = r
                session_state.record_event(
                    _RANK_TELEMETRY_ID, "rank_ok" if any(v is not None for v in r.values()) else "rank_empty")
                break
            except RankBlocked:                         # 403/429/Akamai 챌린지 = 이상징후
                session_state.record_event(_RANK_TELEMETRY_ID, "rank_challenge")
                if not _rank_cooldown(browser, log, "차단(403/Challenge)"):
                    raise RankHalt({k: (pc[k], {}) for k in pc})
                continue                                # cooldown 후 같은 kw 재측정(probe)
    return {kw: (pc.get(kw, {}), {}) for kw in keywords}


def _measure(browser, keywords, matchers, log, matched_out=None):
    """키워드들의 순위 측정 → {키워드: (ranks_pc, ranks_mobile)}.

    기본 = 직렬 네비게이션(RANK_NAV_SERIAL, 안전). False면 (구) 병렬 fetch 경로(빠르나 봇틱).
    이번 실행에 이미 차단 감지(_RANK_HALT)면 즉시 빈 결과(더 두드리지 않음).
    모바일은 RANK_INCLUDE_MOBILE=True 일 때만(기본 제외).
    matched_out(선택)엔 매칭된 검색결과 항목이 담겨 노출명 갱신에 쓰인다(직렬 경로에서만).
    """
    if not keywords or _RANK_HALT["stop"]:
        return {}
    if config.RANK_NAV_SERIAL:
        return _measure_nav_serial(browser, keywords, matchers, log, matched_out)
    try:   # (구) 병렬 fetch 경로 — 옵션
        pc = organic_ranks_batch(browser, keywords, matchers, log=log)
        mo = (organic_ranks_batch(browser, keywords, matchers, mobile=True, log=log)
              if config.RANK_INCLUDE_MOBILE else {})
    except RankBlocked:
        log("  [노출측정] 병렬 fetch 실패(차단/빈응답) → 순차 방식으로 폴백")
        pc, mo = {}, {}
        for kw in keywords:
            try:
                pc[kw] = organic_ranks(browser, kw, matchers, log=log)
                if config.RANK_INCLUDE_MOBILE:
                    mo[kw] = organic_ranks(browser, kw, matchers, mobile=True, log=log)
            except RankBlocked:
                log("  [노출측정] 쿠팡 검색 차단(과다 실행 시 Akamai) — 남은 순위 공란, 잠시 후/내일 재시도")
                break
    return {kw: (pc.get(kw, {}), mo.get(kw, {})) for kw in keywords}


def _measure_safe(browser, keywords, matchers, log, matched_out=None):
    """순위 측정 예외 안전 래퍼(run_full 경로) — 어떤 예외가 나도 공란 처리하고 계속(순위는 부가지표).

    차단(RankHalt)이면 부분결과를 돌려주고, 이후 _measure 는 _RANK_HALT 로 자동 no-op → 그 실행의
    나머지 순위는 안 두드린다(자동 중단). track_ranks_stage(③)는 RankHalt 를 직접 잡아 중단·저장한다.
    """
    if not keywords:
        return {}
    try:
        return _measure(browser, keywords, matchers, log, matched_out)
    except RankHalt as h:
        return h.partial
    except Exception as exc:
        log(f"  [순위] 측정 실패(공란 처리) — {exc.__class__.__name__}: {str(exc)[:80]}")
        return {}


def _rank_matcher(vids, pname: str = ""):
    """③ 순위 매칭 매처 — vid 있으면 vid로 **정확 매칭**, 없으면 **상품명(부분일치) 폴백**(DESIGN §2.1).

    ⚠ 판매 0인 날은 vi-detail-search 가 그 상품을 안 줘서 vid 가 없을 수 있다(수집 자체는 정상 — 지표 0).
    그런 상품도 건너뛰지 않고 상품명으로 순위를 추적한다(run_full 자체 경로 `_product_matcher` 와 동일 방침).
    ③ 순위조회는 product 객체 없이 워크북의 (vid, 상품명)만 안다."""
    vset = set(str(v) for v in vids if v)
    return {"제품": make_matcher(vendor_item_ids=vset,
                                 name_substr=None if vset else (pname or "").strip())}


def _load_latest_wb(out: Path):
    """최신 결과 워크북 로드 — 마스터 우선, 없으면 진행중. (wb, path) 또는 (None, None)."""
    for p in (_master_path(out), _partial_path(out)):
        if p.exists():
            return OutputWorkbook.load(p), p
    return None, None


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
            return None, {}, {}, {}, set(), set(), {}   # 이 계정 건너뜀(무인 비번없음·otp·로그인 미완료)
        collector.reset_raw()                # 계정별 응답 원문 버퍼 초기화(파일 분리)
        found = _discover_products(b, a, date_from, date_to, log)
        _dump_raw(a.account_id, log)         # 3 API 응답 원문 저장(가공 없음·분석용). found None(데이터없음)이어도 남김
        if found is None:                    # 판매분석·상품조회 모두 데이터 없음 → 건너뜀
            return None, {}, {}, {}, set(), set(), {}
        products, tracked, metrics, inventory, sale_status, upbundle_vids, live_all_vids, vid_meta = found
        _persist_session(a, b, log)                                 # 세션 3요소+쿠키 영속(부가)
        session_state.observe_collection_done(a.account_id)         # 관측: 이 계정 수집 완료 시각
    save_discovered(a.account_id, products)   # (요약 로그는 위 with 블록에서 계정 단위로 남김)
    report = Account(a.account_id, a.representative, a.business_name, tracked)
    report.ledger_products = set(a.ledger_products)   # ⑥: 줄 존재 전체(활성+판매중지/취소선) 전파 — 완전삭제 판정용
    return (report, metrics, inventory, sale_status, upbundle_vids, live_all_vids, vid_meta)


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
    from .collector import (fetch_inventory, InventoryFetchError,
                            fetch_vendor_inventory, products_from_vendor_inventory,
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
    # 로켓그로스 파트가 있는 상품(로켓그로스·둘다)이 있으면 같은 세션에서 재고현황도 직접조회
    # (판매자배송 전용 계정은 재고 없음 → 생략)
    inventory: dict[str, int] = {}
    inv_names: dict[str, str] = {}
    rfm_status: dict[str, bool] = {}   # {vid: isSaleSuspended} — RFM 재고 API(로켓그로스만)
    if any(p.kind in config.KINDS_WITH_INVENTORY for p in products):
        try:
            inventory, inv_names, rfm_status = fetch_inventory(b.page, log)   # 재고 수량 + vid→상품명 roster + 판매상태
            log(f"  [{a.label}] 재고현황 {len(inventory)}개 옵션 조회")
        except InventoryFetchError as exc:   # 부가지표 — 실패해도 수집 전체는 진행(사유 명시)
            log(f"  [{a.label}] ⚠ 재고현황 조회 실패(계속) — {str(exc)[:120]}")
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
    # 추적 범위 = 입력 대장 상품(위탁 관리분)만. 당일 발견을 매칭해 노출제목·vid·구분 부여(지표는 당일 것).
    tracked, n_match = scope_to_ledger(a.products, products)
    tracked, n_match = _augment_vids(b, a, tracked, n_match, inv_names, date_to, log)
    # ── 계정 요약(진행경과·오류추적): 소스별 개수 + 대장 매칭/미매칭(vid 없는 상품은 등록명으로 추적) ──
    unmatched = [tp.name for tp in tracked if not any(o.vendor_item_ids for o in tp.options)]
    vid_count = sum(len(o.vendor_item_ids) for tp in tracked for o in tp.options)
    log(f"  [계정 {a.account_id}/{a.label}] 소스: 상품조회 {len(products)}상품 · 판매분석 {len(metrics)}옵션"
        f" · 재고 {len(inventory)}vid · 판매상태 {len(sale_status)}vid")
    log(f"  [계정 {a.account_id}/{a.label}] 대장 {len(a.products)} → 추적 {len(tracked)}"
        f"(매칭 {n_match}·vid {vid_count}) · 미매칭(vid없음) {len(unmatched)}"
        + (f": {[_short(n, 22) for n in unmatched[:10]]}{'…' if len(unmatched) > 10 else ''}" if unmatched else ""))
    return products, tracked, metrics, inventory, sale_status, upbundle_vids, live_all_vids, vid_meta


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
    wb.set_product_vids(biz, pname, opt_vids)          # 대표 옵션 vid 저장(③은 sibling_vids 합집합으로 매칭)
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
                     live_vids=None, vid_meta=None) -> None:
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
                        vid_meta=vid_meta)
        for i, opt in enumerate(opts):
            bname = _block_name(base, opt.label if multi else "")
            seen_products.append(bname)
            _process_option(pctx, biz, product, base, kind, title, i, opt, multi)
            wb.set_product_account_id(biz, bname, report_acc.account_id)   # 항목5: 상품별 계정ID 태깅(다계정ID 사업자)
    # 죽은 중복 블록 정리(안전 규칙): live 형제 있고 vid 가 상품조회서 소멸한 잔재만 삭제(reconcile 판매중지 표기 전)
    _sweep_dead_duplicates(wb, biz, live_vids, log)
    # 대장 대조(항목⑥, 소유자 2026-09-25): **줄이 완전히 사라진 상품 = 이력 포함 완전삭제**(백업 안전망),
    # 대장에 **판매중지/취소선으로 남은(줄 존재)** 상품 = 판매중지 표기 유지. ledger_products=줄 존재 전체.
    newly, deleted = wb.reconcile_account(biz, seen_products, report_acc.ledger_products, delete_missing=True)
    if deleted:
        log(f"  [SYNC] [{biz}] 관리대장에서 줄이 사라진 상품 {len(deleted)}개 → 완전삭제(이력 포함·백업 보존): "
            f"{deleted[:3]}{'…' if len(deleted) > 3 else ''}")
    if newly:
        log(f"  [{biz}] 대장에 판매중지로 남은 상품 {len(newly)}개 → 판매중지 표기(유지): "
            f"{newly[:3]}{'…' if len(newly) > 3 else ''}")
    wb.save(save_path)


def _pull_gsheet_keywords(wb, output_url: str | None, log) -> None:
    """실행 시작 시 결과 통계 시트의 **직원 입력 키워드**를 워크북으로 역머지(그 상품은 AI 선정 대신 동결).

    output_url 없거나 SA 미등록이면 조용히 생략(정상 — 구글 통합 미사용). 실패는 로그로 명시하되 실행을
    막지 않는다(읽기 실패 시 AI 선정으로 진행). 첫 실행엔 통계 시트가 아직 없어 no-op(정상)."""
    if not output_url:
        return
    try:
        from . import gsheet_api, gsheet_stats
        if not gsheet_api.load_sa_info():
            return
        client = gsheet_api.GSheetClient(output_url, on_log=log)
        n = gsheet_stats.merge_staff_keywords(client, wb, on_log=log)
        if n:
            log(f"== [구글시트] 직원 입력 키워드 반영 {n}개 상품 → 해당 상품 AI 선정 생략(동결) ==")
    except Exception as exc:
        log(f"== [구글시트] 직원 키워드 읽기 실패: {exc.__class__.__name__}: {exc} (AI 선정으로 진행) ==")


def push_ledger_inventory(input_url: str | None, log, out_dir: str = "output") -> None:
    """관리대장(**입력** 구글시트)의 '그로스 재고' 컬럼을 최신 마스터 재고로 역기록(전체실행·무인 종료 시).

    최신 마스터 워크북을 직접 로드해 재고를 뽑는다(단계들이 이미 저장 완료한 뒤 호출). 입력 URL 없거나 SA
    미등록이면 조용히 생략(정상). SA에 관리대장 편집권한 없으면 403 → **로그로 명시**하고 비치명(수집·결과시트는
    이미 저장됨). 직원 입력 다른 컬럼은 미접촉(그로스재고 셀만 갱신·미매칭·개인상품은 기존값 보존).
    """
    if not input_url:
        return
    try:
        from . import gsheet_api, input_list
        wb, _ = _load_latest_wb(Path(out_dir))
        if wb is None:
            return
        if not gsheet_api.load_sa_info():
            return
        client = gsheet_api.GSheetClient(input_url, on_log=log)
        n = input_list.write_ledger_inventory(client, wb, on_log=log)
        if n:
            log(f"== [관리대장] 그로스 재고 역기록 완료 — {n}개 상품(입력 대장 AD컬럼) ==")
    except Exception as exc:
        log(f"== [관리대장] 그로스 재고 역기록 실패(비치명 — SA 편집권한 확인): "
            f"{exc.__class__.__name__}: {str(exc)[:120]} ==")


def _push_gsheet(wb, output_url: str | None, log, removed_accounts=None, renamed_accounts=None) -> None:
    """완성된 openpyxl 마스터를 결과 구글시트로 반영 — 통계 시트 미러링 + 계정목록 증분 동기화.

    output_url 없거나 서비스계정 미등록이면 조용히 생략(정상 — 구글 통합 미사용). 반영 실패는 **로그로 명시**
    (조용한 무시 아님)하되 파이프라인을 죽이지 않는다: xlsx 마스터·스냅샷은 이미 저장됐다(오프라인 백업).
    removed_accounts=[(사업자, 계정ID)…]: 관리대장에서 **줄이 사라진** 계정 → 결과 구글시트에서도 완전 삭제
    (계정목록 행 + 통계 시트). '판매중지'로 남은 건 여기 없음(유지+경고).
    renamed_accounts=[(옛사업자명, 계정ID)…]: 시트명 변경으로 **일원화**된 계정의 옛 이름 잔재 → 계정목록 옛
    이름 행·옛 통계 시트를 **이름 기준**으로 제거(계정ID는 새 이름과 공유하므로 이름 매칭). 새 이름은 미러링/동기화.
    """
    # ⚠ 조용한 스킵 금지 — 반영 안 된 이유를 **항상 로그로** 남긴다(정상종료인데 반영 안 됨을 추적 가능하게).
    if not output_url:
        log("== [구글시트] ⚠ 반영 생략 — **결과(출력) 시트 URL 미설정**. "
            "설정 탭 '구글 시트 연동'에 결과 시트 링크를 넣어야 반영됩니다(이 PC 설정, xlsx는 저장됨) ==")
        return
    _phase = "초기화"
    try:
        from . import gsheet_api, gsheet_index, gsheet_stats
        if not gsheet_api.load_sa_info():
            log("== [구글시트] ⚠ 반영 생략 — **서비스계정(SA) 키 미등록**(설정 탭에서 SA 키 입력 필요·이 PC 설정, xlsx는 저장됨) ==")
            return
        log(f"== [구글시트] 결과 반영 시작 — 출력시트 …{str(output_url)[-24:]} ==")
        _phase = "클라이언트 연결"
        client = gsheet_api.GSheetClient(output_url, on_log=log)
        if removed_accounts:   # 삭제된 계정 먼저 제거(행+시트) → 이후 미러링/동기화는 남은 것만 대상
            _phase = "삭제계정 정리"
            d = gsheet_index.delete_accounts(client, removed_accounts, on_log=log)
            if d:
                log(f"== [구글시트] 삭제된 계정 정리 — {len(removed_accounts)}개(계정목록 행·통계 시트 제거) ==")
        if renamed_accounts:   # 일원화된 옛 이름 잔재 제거(이름 기준) → 새 이름은 아래 미러링/동기화
            _phase = "일원화 옛이름 정리"
            r = gsheet_index.delete_renamed_accounts(client, renamed_accounts, on_log=log)
            if r:
                log(f"== [구글시트] 일원화 옛 이름 정리 — {len(renamed_accounts)}개"
                    f"({', '.join(nm for nm, _a in renamed_accounts)} 계정목록 행·옛 통계 시트 제거) ==")
        _phase = "통계 시트 미러링"
        log("== [구글시트] 통계 시트 미러링 중… ==")
        gids = gsheet_stats.push_statistics(client, wb, on_log=log)          # 사업자별 통계 시트 전체 미러링
        _phase = "계정목록 동기화"
        log(f"== [구글시트] 통계 {len(gids)}시트 미러링 완료 → 계정목록 동기화 중… ==")
        roster = gsheet_index.roster_from_workbook(wb, gids)                 # 계정목록 로스터(등록명 기반 안정키)
        plan = gsheet_index.sync_index(client, roster)                      # 계정목록 증분(마케팅 D~F 보존)
        log(f"== [구글시트] ✅ 결과 반영 완료 — 통계 {len(gids)}시트 · 계정목록 "
            f"갱신 {len(plan.updates)}·신규 {len(plan.inserts)}·판매중지 {len(plan.discontinue)} ==")
    except Exception as exc:
        # ⚠ 조용한 실패 금지 — 계정목록/통계가 최신이 아닐 수 있음을 **눈에 띄게** 경고(과거 이 실패를
        # 한 줄로 삼켜 계정목록이 옛 상태로 방치됨, 라이브 2026-09-23). 실행은 계속(xlsx 는 보존).
        log("== [구글시트] ❌❌ 결과 반영 실패 — **계정목록/통계가 최신이 아닐 수 있습니다(확인 필요)** ==")
        log(f"==   단계='{_phase}' · {exc.__class__.__name__}: {str(exc)[:200]} ==")
        log("==   xlsx 마스터·스냅샷은 정상 저장됨. SA 편집권한·시트 공유·URL 확인 후 재실행하면 반영됩니다 ==")


def _count_unfilled_ranks(wb) -> int:
    """오늘(각 사업자 최신일자) 기준 **아직 못 채운 순위 셀 수**(vid 없으면 상품명으로 매칭하므로 포함)."""
    n = 0
    for biz in wb.account_sheets():
        date = wb.latest_date(biz)
        if not date:
            continue
        for pname in wb.products_of(biz):
            for kw in wb.product_keywords(biz, pname):
                if not wb.is_rank_filled(biz, pname, kw, date):
                    n += 1
    return n


def _measure_unfilled_once(wb, path, log) -> int:
    """공란 순위를 한 번 훑어 측정(브라우저 1개, vid 있는 상품의 공란 키워드만). 채운 수 반환.

    ③ track_ranks_stage 자동 루프와 같은 방식(상품마다 저장·차단 감지 시 중단). 보완 라운드 1회에 해당.
    """
    filled = 0
    halted = False
    with WingBrowser(profile_dir=_PROFILE, offscreen=True) as browser:
        warmup(browser)
        for biz in wb.account_sheets():
            if halted:
                break
            date = wb.latest_date(biz)
            if not date:
                continue
            for pname in wb.products_of(biz):
                vids = wb.sibling_vids(biz, pname)   # 리스팅 전 옵션 vid 합집합(아이템위너 놓침 방지)
                keywords = wb.product_keywords(biz, pname)
                if not keywords:                        # 2차 옵션 블록(키워드 없음)·vid 없는 상품 건너뜀
                    continue
                todo = [kw for kw in keywords if not wb.is_rank_filled(biz, pname, kw, date)]
                if not todo:
                    continue
                cap: dict = {}
                try:
                    measured = _measure(browser, todo, _rank_matcher(vids, pname), log, matched_out=cap)
                except RankHalt as h:               # 차단 감지 → 부분결과만 기록하고 전면 중단
                    measured, halted = h.partial, True
                except Exception as exc:
                    log(f"  [순위보완] 측정 실패(공란) — {exc.__class__.__name__}: {str(exc)[:80]}")
                    measured = {}
                for kw in todo:
                    if kw not in measured:
                        continue
                    r = _best(measured.get(kw))
                    wb.set_keyword_rank(biz, pname, kw, date, r)
                    log(f"  [순위보완] {biz} · {pname} '{kw}': {rank_label(r)}")
                    filled += 1
                mi = cap.get("제품")                    # 노출명은 로그로만(블록명=등록상품명 고정, set_display_name 중단)
                if mi is not None and getattr(mi, "name", ""):
                    log(f"  [노출명] 검색결과 노출명 = {mi.name} (블록명은 등록상품명 고정)")
                wb.save(path)                        # 상품마다 저장(중단돼도 보존)
                if halted:
                    break
    return filled


def _backfill_ranks(wb, path, log, *, was_blocked: bool) -> None:
    """전체실행 후 남은 공란 순위를 **쿨다운을 두고 자동 재시도**(진전 없으면 중단 — IP 하드플래그 판단).

    ⚠️ 안티차단 원칙: 차단 뒤 즉시 두드리면 IP만 탄다 → 라운드 사이에 긴 쿨다운(RANK_BACKFILL_COOLDOWN_SEC)
    으로 IP flag가 완화될 시간을 준 뒤에만 재시도. 한 라운드가 0개 진전이면 즉시 중단(다음 실행/쉰 IP로).
    """
    if not config.RANK_BACKFILL:
        return
    remaining = _count_unfilled_ranks(wb)
    if remaining == 0:
        return
    log(f"  [순위보완] 미처리 순위 {remaining}개 — 자동 재시도(최대 {config.RANK_BACKFILL_ROUNDS}회, "
        f"라운드 간 {config.RANK_BACKFILL_COOLDOWN_SEC // 60}분 쿨다운·진전 없으면 중단)")
    for rnd in range(1, config.RANK_BACKFILL_ROUNDS + 1):
        if rnd > 1 or was_blocked:                  # 차단 뒤엔 즉시 재시도 무의미 → 쿨다운(IP 완화 시간)
            log(f"  [순위보완] IP 쿨다운 {config.RANK_BACKFILL_COOLDOWN_SEC // 60}분 대기 후 재시도"
                f"(라운드 {rnd}/{config.RANK_BACKFILL_ROUNDS})…")
            time.sleep(config.RANK_BACKFILL_COOLDOWN_SEC)
        _reset_rank_state()                         # 새 라운드 = 이전 차단 플래그·서킷브레이커 초기화
        try:
            filled = _measure_unfilled_once(wb, path, log)
        except Exception as exc:                    # 보완은 부가 — 어떤 예외도 전체 저장을 막지 않음
            log(f"  [순위보완] 라운드 {rnd} 중단({exc.__class__.__name__}: {str(exc)[:80]}) — 남은 순위는 다음 실행")
            return
        remaining = _count_unfilled_ranks(wb)
        log(f"  [순위보완] 라운드 {rnd}: {filled}개 채움 · 남은 {remaining}개")
        if remaining == 0:
            log("  [순위보완] 모든 순위 처리 완료")
            return
        if filled == 0:                             # 진전 0 = IP 여전히 차단 추정 → 더 두드리지 않음
            log("  [순위보완] 진전 없음(IP 여전히 차단 추정) — 중단. 남은 순위는 다음 실행/쉰 IP에서 이어서")
            return
    log("  [순위보완] 재시도 상한 도달 — 남은 순위는 다음 실행에서 이어서")


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
    struck = list(input_list.struck)
    summary = {"new": new_ids, "gone": gone_ids, "renamed": renamed, "struck": struck}
    if not (new_ids or gone_ids or renamed or struck):
        log("== [SYNC] 관리대장↔결과 일치(신규·삭제·이름변경·취소선 없음) ==")
        return summary
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
    return summary


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
            upbundle_vids=None, live_vids=None, vid_meta=None) -> None:
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
                             upbundle_vids=upbundle_vids, live_vids=live_vids, vid_meta=vid_meta)
        else:
            with WingBrowser(profile_dir=_PROFILE, offscreen=True) as rank_browser:
                warmup(rank_browser)
                _process_account(report_acc, wb, ctx.naver, ctx.ai_key, rank_browser, metrics,
                                 inv_by_vid, ctx.col_label, ctx.grow, log, ctx.partial,
                                 sale_status=inv_status, upbundle_vids=upbundle_vids, live_vids=live_vids,
                                 vid_meta=vid_meta)
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
            report_acc, metrics, inv_by_vid, inv_status, upbundle_vids, live_vids, vid_meta = _login_and_discover(
                a, ctx.date_from, ctx.date_to, get_password, log, login=False)
            _finish(ctx, a, report_acc, metrics, inv_by_vid, inv_status, upbundle_vids, live_vids, vid_meta)
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
            report_acc, metrics, inv_by_vid, inv_status, upbundle_vids, live_vids, vid_meta = _login_and_discover(
                a, ctx.date_from, ctx.date_to, get_password, log, login=True, semi=sales_semi)
            blocks = 0                            # 로그인 성공 → 연속 차단 카운터 리셋
            _finish(ctx, a, report_acc, metrics, inv_by_vid, inv_status, upbundle_vids, live_vids, vid_meta)
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


def track_ranks_stage(out_dir: str = "output", on_log=None, semi: bool = False,
                      should_stop=None, gsheet_output_url: str | None = None) -> Path | None:
    """③ 노출순위 조회 전용 — 최신 워크북 로드, 상품(고유ID)+키워드로 순위 측정·기록. 로그인 불필요.

    ①(상품ID)·②(키워드)가 이미 워크북에 있어야 한다. 상품마다 저장된 vendorItemId 로 검색결과에서 내
    상품을 찾아 오가닉 순위를 기록한다(가장 최근 일자 컬럼). 예외 안전 — 차단·browser 죽음도 공란 처리.
    매칭 시 계약상품명을 검색결과의 **정확한 노출명**으로 갱신한다.
    semi=True 면 **반자동** — 앱이 창을 띄우고 키워드를 안내, 사람이 직접 검색하면 그 화면만 읽어 순위 산출
    (자동 네비게이션 없음 → 차단 회피). should_stop() 이 참이면 중도 중단.
    """
    log = on_log or (lambda m: None)
    out = Path(out_dir)
    wb, path = _load_latest_wb(out)
    if wb is None:
        log("== 순위 조회: 결과 워크북이 없습니다 — 먼저 ①②를 실행하세요 ==")
        return None
    if semi:
        result = _track_ranks_semi(wb, path, log, should_stop or (lambda: False))
        _push_gsheet(wb, gsheet_output_url, log)   # ③ 반자동 순위 채운 뒤 결과 구글시트에도 반영
        return result
    log(f"== 노출순위 조회 시작 — {path.name} ==")
    _reset_rank_state()          # 이번 실행 차단 플래그·서킷브레이커(cooldown) 초기화
    if config.RANK_NAV_SERIAL:
        log(f"  [모드] 사람속도 직렬 네비게이션(검색 간격 {config.RANK_NAV_DELAY_MIN_SEC}"
            f"~{config.RANK_NAV_DELAY_MAX_SEC}s) — 버스트 없이 차단 회피. 차단 감지 시 즉시 중단(이어서 재개)")
    halted = False
    noname_products = 0   # vid·상품명 모두 없어(이례) 측정 못 한 상품 수(집계 → 종료 시 안내)
    with WingBrowser(profile_dir=_PROFILE, offscreen=True) as browser:
        warmup(browser)
        for biz in wb.account_sheets():
            if halted:
                break
            date = wb.latest_date(biz)
            if not date:
                continue
            for pname in wb.products_of(biz):
                halted, noname = _measure_product_auto(browser, wb, path, biz, pname, date, log)
                if noname:
                    noname_products += 1
                if halted:
                    break
    wb.apply_style()   # 저장본 서식 항상 표준으로 고정
    wb.save(path)
    if noname_products:
        log(f"  [안내] vid·상품명이 모두 없는 상품 {noname_products}개는 매칭 근거가 없어 순위 공란입니다(이례).")
    if halted:
        log("== ⛔ 노출순위 중단(쿠팡 검색 차단 감지) — 진행분 저장됨. "
            "쉰 IP/시간에 다시 실행하면 남은 것부터 이어서 조회합니다 ==")
    else:
        log("== 노출순위 조회 완료 ==")
    _push_gsheet(wb, gsheet_output_url, log)   # ③ 자동 순위 채운 뒤 결과 구글시트에도 반영(차단 중단이어도 진행분 반영)
    return path


def _measure_product_auto(browser, wb, path, biz: str, pname: str, date, log) -> tuple[bool, bool]:
    """③ 자동(offscreen) 순위 — 한 상품 측정·기록·저장. 반환 (halted, noname).

    keywords/vid 없거나 todo 비면 (False, ·)로 건너뜀. RankHalt=차단 감지(부분결과 기록·halted=True),
    그 외 예외=공란(다음 재시도). 상품마다 저장 → 중단돼도 진행분 보존. (⚠ 현 정책은 반자동만 사용 —
    이 자동 경로는 사문화에 가깝지만 track_ranks_stage(semi=False) 로 여전히 호출 가능·핀 O/O2 로 커버.)"""
    if wb.rank_suppressed(biz, pname):   # 판매중지·임시저장·승인반려·대장취소선 → 순위 제외(소유자 2026-09-22)
        return False, False
    vids = wb.sibling_vids(biz, pname)   # 리스팅 전 옵션 vid 합집합(아이템위너 놓침 방지)
    keywords = wb.product_keywords(biz, pname)
    if not keywords:                     # 2차 옵션 블록(키워드 없음)은 순위 대상 아님
        return False, False
    if not vids and not (pname or "").strip():   # 매칭 근거(vid·상품명) 전무 → 측정 불가(이례)
        return False, True
    # 이미 채워진 키워드는 건너뜀 = **중단 지점부터 이어서**(당일 재작업 시 남은 것만)
    todo = [kw for kw in keywords if not wb.is_rank_filled(biz, pname, kw, date)]
    if not todo:
        return False, False
    if not vids:   # 판매 0 등으로 vid 없음 → 상품명(부분일치)으로 매칭(건너뛰지 않음)
        log(f"  [순위] {biz} · {pname} — vid 없음(판매 0 등) → 상품명으로 매칭")
    cap: dict = {}
    halted = False
    try:
        measured = _measure(browser, todo, _rank_matcher(vids, pname), log, matched_out=cap)
    except RankHalt as h:              # 차단 감지 → 부분결과만 기록하고 전면 중단
        measured = h.partial
        halted = True
    except Exception as exc:           # 그 외 예외 → 공란(다음에 재시도)
        log(f"  [순위] 측정 실패(공란) — {exc.__class__.__name__}: {str(exc)[:80]}")
        measured = {}
    for kw in todo:
        if kw not in measured:            # 측정 안 됨(중단·실패) → 공란 유지(다음에 이어서)
            continue
        r = _best(measured.get(kw))       # 정상 측정: 미노출이면 '-', 노출이면 'N위'
        wb.set_keyword_rank(biz, pname, kw, date, r)
        log(f"  [{biz}] {pname} '{kw}': {rank_label(r)}")
    mi = cap.get("제품")                   # 노출명은 로그로만(블록명=등록상품명 고정, set_display_name 중단)
    if mi is not None and getattr(mi, "name", ""):
        log(f"  [노출명] 검색결과 노출명 = {mi.name} (블록명은 등록상품명 고정)")
    wb.save(path)   # **상품마다 저장** → 중단돼도 여기까지 보존(재실행 시 이어서)
    return halted, False


def _search_q(url: str) -> str | None:
    """검색결과 URL 이면 q(디코드·공백제거) 반환, 아니면 None."""
    from urllib.parse import unquote
    if "/np/search" not in url or "q=" not in url:
        return None
    for part in url.split("?", 1)[-1].split("&"):
        if part.startswith("q="):
            return unquote(part[2:]).replace("+", " ").replace(" ", "")
    return None


# 쿠팡 차단/권한없음 페이지 마커(실측: "요청하신 페이지의 사용권한이 없습니다 … 제한된 페이지").
_BLOCK_PAGE_MARKERS = ("사용권한", "제한된", "Access Denied", "Denied", "죄송")


def _looks_blocked(pg) -> bool:
    """현재 페이지가 쿠팡 차단/권한없음 안내 페이지로 보이는가(사람이 그 창에서 봤을 화면)."""
    try:
        txt = pg.inner_text("body")[:400]
    except Exception:
        try:
            txt = pg.title() or ""
        except Exception:
            return False
    return any(m in txt for m in _BLOCK_PAGE_MARKERS)


def _live_url(pg) -> str:
    """페이지의 **현재 렌더러 실제 URL**(location.href 직접 읽기).

    실측(2026-09-11): connect_over_cdp 장기 연결에서 사용자가 창에서 직접 검색하면 Playwright 가 그
    네비게이션 이벤트를 놓쳐 캐시된 `pg.url` 이 이전(홈) URL 로 **고착**되는 일이 있다(별도 연결로는 최신
    q 가 보이는데 앱은 "입력 대기 중"만 반복). 캐시 대신 렌더러에서 location.href 를 직접 읽어 이를 회피.
    """
    try:
        u = pg.evaluate("() => location.href")
        if u:
            return u
    except Exception:
        pass
    try:
        return pg.url or ""
    except Exception:
        return ""


# 반자동 자동입력 — 뜬 창의 검색창에 키워드를 **사람처럼 한 글자씩 실제 키보드로** 친다(붙여넣기 아님).
# ⚠️ 쿠팡은 붙여넣기/즉시 채움(비신뢰 input)을 감지해 차단하므로 반드시 타이핑(rank.human_type_query 재사용).
def _prefill_search(browser, kw: str) -> bool:
    """뜬 창의 보이는 검색창에 kw 를 **사람처럼 한 글자씩 실제 키보드로 타이핑**(붙여넣기 아님, 제출은 안 함).

    ⚠️ 쿠팡은 붙여넣기/즉시 채움(비신뢰 input)을 감지해 차단하고 실제 키입력만 통과시킨다(실측) → 반드시 타이핑.
    browser.page(앞 창) 우선, 실패 시 다른 탭. 성공 True(실패 시 호출부가 복사 폴백 안내)."""
    pages = _all_pages(browser)
    try:
        if browser.page in pages:
            pages = [browser.page] + [p for p in pages if p is not browser.page]
    except Exception:
        pass
    for pg in pages:
        try:
            human_mouse.approach_search(pg)   # 타이핑 직전 커서를 검색창으로(사람처럼)
            if human_type_query(pg, kw):
                return True
        except Exception:
            continue
    return False


# 자동제출 폴백 — Enter 가 폼을 안 넘길 때 검색버튼 클릭 또는 폼 submit.
_SUBMIT_JS = r"""() => {
  const input = document.querySelector("input[name='q'], input.headerSearchKeyword");
  if (!input) return false;
  const btn = document.querySelector(
      "form [type='submit'], button[type='submit'], [class*='searchButton'], [class*='search-btn']");
  if (btn) { btn.click(); return true; }
  if (input.form) { input.form.submit(); return true; }
  return false;
}"""


def _submit_search(browser) -> None:
    """자동제출 — 프리필된 검색창에서 Enter(사이트 자체 JS로 검색=사람 조작에 가장 가까움). 실패 시 버튼/폼 폴백.

    성공 여부는 이 함수가 아니라 이후 결과 페이지 로드(_wait_results_loaded)로 판정한다.
    """
    try:
        browser.page.keyboard.press("Enter")
    except Exception:
        pass
    # Enter 로 안 넘어가는 레이아웃 대비 — 검색버튼/폼 제출도 시도(무해, 이미 넘어갔으면 no-op에 가까움)
    try:
        browser.page.evaluate(_SUBMIT_JS)
    except Exception:
        pass


def _wait_results_loaded(browser, kw: str, should_stop, timeout: float):
    """자동제출 후 kw 검색결과가 **완전히 로드**될 때까지 대기(사람 안내 없음). (pg, blocked) 반환.

    URL q==kw + document.readyState=='complete' + 상품 존재를 모두 만족해야 결과로 인정(로딩 중/전환 중 오독 방지
    = '결과를 기다림'). 상품 0인데 차단 페이지 마커면 blocked=True. 타임아웃/중지면 (None, blocked).
    """
    from .rank import extract_items
    want = kw.replace(" ", "")
    deadline = time.time() + timeout
    blocked = False
    while time.time() < deadline:
        if should_stop():
            return None, blocked
        for pg in _all_pages(browser):
            if _search_q(_live_url(pg)) != want:
                continue
            try:
                if pg.evaluate("() => document.readyState") != "complete":
                    continue     # 아직 로딩 중 → 기다림
            except Exception:
                continue
            try:
                items = extract_items(pg)
            except Exception:
                items = []
            if items:
                return pg, False
            if _looks_blocked(pg):
                return None, True     # 확정 차단 페이지 → 데드라인(40s) 안 기다리고 즉시 반환(빠른 반응)
        time.sleep(1.0)
    return None, blocked


def _interruptible_sleep(total_sec: float, should_stop, log=None, resume_label: str = "") -> None:
    """긴 쿨다운 대기 — should_stop 을 주기적으로 확인해 **즉시 중지 가능**, 5분마다 남은시간 하트비트 로그.

    자리 비운 사용자가 '멈춘 줄 알고 4시간 방치'하지 않도록, 대기 중임을 로그로 계속 알린다.
    """
    end = time.time() + total_sec
    next_beat = 0.0
    while time.time() < end:
        if should_stop():
            return
        if log and time.time() >= next_beat:
            mins = max(0, int((end - time.time()) // 60) + 1)
            log(f"    ⏳ 쿨다운 대기 중… 약 {mins}분 후 자동 재개{resume_label}")
            next_beat = time.time() + 300     # 5분마다 하트비트
        time.sleep(min(5.0, max(0.5, end - time.time())))


def _all_pages(browser):
    """연결된 브라우저의 **모든 컨텍스트×모든 탭**(방어적). 단일 컨텍스트라도 전부 순회. 실패 시 browser.page."""
    ctxs = []
    try:
        b = browser.context.browser
        ctxs = list(b.contexts) if b else [browser.context]
    except Exception:
        ctxs = [browser.context] if browser.context else []
    pages = []
    for ctx in ctxs:
        try:
            pages.extend(ctx.pages)
        except Exception:
            continue
    return pages or [browser.page]


def _wait_user_search(browser, kw: str, log, should_stop, timeout: float = 300.0):
    """사용자가 뜬 창에서 kw 를 직접 검색할 때까지 대기(폴링). 감지되면 **그 페이지**를, 타임아웃/중지면 None.

    **여러 탭 전부**를 스캔한다(프로필 복원 탭·사용자가 연 새 탭이 browser.page 와 달라도 인식).
    URL 이 /np/search 이고 q(디코드·공백무시)가 kw 와 같고 상품이 떠 있는 첫 탭을 그 검색으로 인정한다
    (이전/다른 키워드 잔여결과를 잘못 기록하지 않도록 q 일치 요구). 자동 네비게이션은 하지 않는다.

    안내를 **상황별로 정확히** 준다(과거엔 q 가 실제로 맞아도 무조건 "안내 키워드로 검색하세요"라고 떠서
    올바로 검색한 사용자가 '인식 못 함'으로 오해했다 — 실측 재현):
    - q 일치인데 상품 목록이 비면: **차단(권한없음) 페이지**인지, 단순 **로딩 대기**인지 구분해 알린다.
    - q 불일치 검색결과만 있으면: 안내 키워드로 검색하라고 알린다.
    - 검색결과가 아예 없으면: 검색창에 입력하라고 알린다.
    """
    from .rank import extract_items
    want = kw.replace(" ", "")
    deadline = time.time() + timeout
    last = 0.0
    while time.time() < deadline:
        if should_stop():
            return None
        pages = _all_pages(browser)   # 모든 컨텍스트×탭 순회(사용자가 연 새 탭·창도 포함)
        other_qs: list[str] = []      # 안내와 다른 키워드로 열린 검색결과
        matched_empty = False         # 안내 키워드로 검색은 됐으나 상품이 안 잡힘(차단/로딩)
        matched_blocked = False       # 그 중 차단/권한없음 페이지로 보임
        err_reason = ""               # extract 예외 원인(있으면 로그에 노출 — 조용히 삼키지 않음)
        for pg in pages:
            q = _search_q(_live_url(pg))   # 캐시 pg.url 대신 렌더러 실제 location.href(이벤트 놓침 방지)
            if q is None:
                continue
            if q != want:
                other_qs.append(q)
                continue
            try:
                items = extract_items(pg)
            except Exception as exc:
                err_reason = f"{exc.__class__.__name__}: {str(exc)[:60]}"
                items = []
            if items:
                return pg
            matched_empty = True
            if _looks_blocked(pg):
                matched_blocked = True
        if time.time() - last > 15:
            if matched_blocked:
                log(f"    …「{kw}」 검색은 인식됐으나 **쿠팡 차단(사용권한 없음) 페이지**가 떴습니다 — "
                    "그 창을 새로고침(F5)하거나 잠시 후 다시 검색하세요(자동 우회 없음)")
            elif matched_empty:
                extra = f" [{err_reason}]" if err_reason else ""
                log(f"    …「{kw}」 검색은 인식됐으나 상품 목록이 아직 안 보입니다 — "
                    f"페이지가 다 뜰 때까지 잠시 기다리거나 새로고침 해주세요{extra}")
            elif other_qs:
                opened = ", ".join(f"'{q}'" for q in other_qs)
                _prefill_search(browser, kw)   # 창엔 옛 검색이 떠 있음 → 검색창을 kw로 재채움(사람은 Enter만)
                log(f"    ⌨ 창엔 '{other_qs[0]}' 결과가 떠 있습니다 → 검색창에 「{kw}」를 다시 채웠으니"
                    f" **그 창에서 Enter** 하세요(안 채워졌으면 직접 입력: {kw})")
            else:
                log(f"    … **뜬 Chrome 창**(빨간 띠)에서 「{kw}」로 검색(Enter)하세요"
                    f" (자동입력 안 됐으면 직접 입력: {kw} · 다른 브라우저 아님 · 중지는 '반자동 중지')")
            last = time.time()
        time.sleep(1.0)
    return None


# 반자동 창 식별용 — 우리가 연 창에만 하단 빨간 띠(모든 페이지·검색결과에 계속 표시). 다른 Chrome 창엔 없어
# 여러 창 중 이 창을 한눈에 찾게 한다. Akamai 탐지와 무관(우리 창 UI 표식일 뿐, 지문위조·행동위장 아님).
_SEMI_BANNER_JS = r"""(() => {
  const ID='__semi_marker__';
  function add(){
    if(document.getElementById(ID))return;
    const d=document.createElement('div');
    d.id=ID;
    d.textContent='★ 반자동 순위조회 창 — 이 창에서 검색하세요 ★';
    d.style.cssText='position:fixed;left:0;right:0;bottom:0;z-index:2147483647;'
      +'background:#ff3b30;color:#fff;font:bold 18px sans-serif;text-align:center;'
      +'padding:10px;box-shadow:0 -2px 10px rgba(0,0,0,.4);pointer-events:none';
    (document.body||document.documentElement).appendChild(d);
  }
  add();
  try{new MutationObserver(add).observe(document.documentElement,{childList:true,subtree:true});}catch(e){}
  setInterval(add,1000);
})();"""


@dataclass
class _SemiState:
    """반자동 순위 상태기계의 가변 카운터(헬퍼가 공유·변경). 제어흐름은 분해 전과 동일."""
    autosubmit: bool
    halted: bool = False        # 자동제출 서킷브레이커(연속 차단/미감지) → 당일 전면 중단
    miss_streak: int = 0        # 자동제출 연속 실패 수(성공 시 0으로 리셋)
    cooldowns: int = 0          # 차단 감지 쿨다운 진입 횟수(진전 있으면 0으로 리셋) — 무한 재시도 방지
    noname_products: int = 0    # vid·상품명 모두 없어(이례) 측정 못 한 상품 수(집계 → 종료 시 안내)
    measured_any: bool = False  # 첫 검색 전엔 대기 없음·마지막 검색 뒤에도 대기 없음(간격은 '검색 사이'에만)
    # ── 종료 요약용 **누적** 카운터(진전 리셋 대상 아님 — 실행 전체 합계, B-1 간격 되돌림 판단) ──
    searched: int = 0           # 실제 측정(순위 기록)된 검색 건수
    cooldown_total: int = 0     # 차단 감지로 쿨다운에 진입한 총 횟수(간격이 짧아 IP를 태우는지 신호)
    blocked_total: int = 0      # 확정 차단 페이지(사용권한 없음) 감지 총 횟수


def _track_ranks_semi(wb, path, log, should_stop) -> Path:
    """반자동 순위조회 — 앱이 창을 띄우고 키워드를 안내, 사람이 직접 검색한 화면만 읽어 순위 산출·기록.

    우리가 검색(네비게이션)을 하지 않으므로 Akamai 봇차단이 안 생긴다. 상품마다 저장 → 중단해도 이어서.
    """
    st = _SemiState(autosubmit=config.RANK_SEMI_AUTOSUBMIT)
    _semi_start_log(st.autosubmit, log)
    with WingBrowser(profile_dir=_PROFILE, offscreen=False) as browser:
        _semi_browser_prep(browser, st.autosubmit, log)
        for biz in wb.account_sheets():
            if should_stop() or st.halted:
                break
            date = wb.latest_date(biz)
            if not date:
                continue
            for pname in wb.products_of(biz):
                if should_stop() or st.halted:
                    break
                _semi_track_product(st, browser, wb, biz, pname, date, path, should_stop, log)
    wb.apply_style()
    wb.save(path)
    if st.noname_products:
        log(f"  [안내] vid·상품명이 모두 없는 상품 {st.noname_products}개는 매칭 근거가 없어 순위 공란입니다(이례).")
    if st.halted:
        log("== ⛔ 반자동(자동검색) 중단(차단 추정) — 진행분 저장됨. 쉰 시간/IP에 다시 실행하면 이어서 조회 ==")
    else:
        log("== 반자동 노출순위 종료 — 진행분 저장됨(중단 시 다음 실행이 남은 것부터 이어서) ==")
    _semi_summary_log(st, log)
    return path


def _semi_summary_log(st: _SemiState, log) -> None:
    """순위 단계 종료 요약 — 측정·쿨다운·차단 누적 + 검색간격. 차단/쿨다운이 있으면 간격 되돌림을 권고(B-1).

    소유자가 검색간격을 45~75 → 35~55 로 낮춘 뒤 **차단이 늘면 되돌려야** 하는데, 그 판단을 로그 grep 없이
    바로 할 수 있게 한다. 차단/쿨다운이 0이면 현재 간격 유지 판단."""
    if st.autosubmit:   # 자동제출(현재 기본)에서만 차단/쿨다운 카운터가 의미 있음
        log(f"== [순위요약] 측정 {st.searched}건 · 쿨다운 {st.cooldown_total}회 · 차단감지 {st.blocked_total}회 "
            f"· 검색간격 {config.RANK_NAV_DELAY_MIN_SEC}~{config.RANK_NAV_DELAY_MAX_SEC}s ==")
        if st.cooldown_total or st.blocked_total:
            log("== [순위요약] ⚠ 차단/쿨다운 발생 — config.py 의 RANK_NAV_DELAY 를 45~75 로 되돌리는 것을 권고합니다"
                "(간격이 짧아 IP를 태우는 신호). 다음 실행에서도 계속 뜨면 상향 필요 ==")
        else:
            log("== [순위요약] 차단/쿨다운 0 — 현재 검색간격 유지 판단(무차단) ==")


def _semi_start_log(autosubmit: bool, log) -> None:
    if autosubmit:
        log("== 반자동(자동검색) 노출순위 시작 — 앱이 키워드 자동입력+Enter까지 수행(손 안 대도 됨). "
            f"키워드 간 {config.RANK_NAV_DELAY_MIN_SEC}~{config.RANK_NAV_DELAY_MAX_SEC}s 간격, "
            f"연속 {config.RANK_SEMI_AUTO_MAX_MISS}회 차단 시 계정 보호로 당일 중단 ==")
    else:
        log("== 반자동 노출순위 시작 — 뜬 Chrome 창의 쿠팡 검색창에 '안내되는 키워드'를 직접 입력·검색하세요 ==")


def _semi_browser_prep(browser, autosubmit: bool, log) -> None:
    """반자동 창 준비 — 빨간 띠(창 식별) 주입 + 쿠팡 홈(검색창) 이동 + 창 표시."""
    try:
        browser.page.add_init_script(_SEMI_BANNER_JS)   # 이후 모든 네비/검색결과에 빨간 띠(창 식별)
    except Exception:
        pass
    browser.show()
    try:
        browser.goto("https://www.coupang.com/")   # 검색창 제공
    except Exception:
        pass
    try:
        browser.page.evaluate(_SEMI_BANNER_JS)          # 현재(홈) 페이지에도 즉시 표시
    except Exception:
        pass
    browser.show()   # goto 후 다시 중앙·맨앞으로
    if not autosubmit:
        log("  [반자동] ⬆ 창 여러 개 중 **하단에 빨간 띠('반자동 순위조회 창')**가 있는 창에서 검색하세요")


def _semi_track_product(st: _SemiState, browser, wb, biz, pname, date, path, should_stop, log) -> None:
    """한 상품의 미기입 키워드를 순회하며 반자동 검색·순위 기록(상태기계는 st 로 공유)."""
    if wb.has_marketing() and not wb.product_due(biz, pname, date)[0]:
        return                             # 상품 수집 주기(마케팅 상품만 매일) — 오늘 대상 아니면 순위도 생략
    if wb.rank_suppressed(biz, pname):     # 판매중지·임시저장·승인반려·대장취소선 → 순위 제외(소유자 2026-09-22)
        return
    vids = wb.sibling_vids(biz, pname)     # 리스팅 전 옵션 vid 합집합(아이템위너 놓침 방지)
    keywords = wb.product_keywords(biz, pname)
    if not keywords:                       # 2차 옵션 블록(키워드 없음)은 순위 대상 아님
        return
    if not vids and not (pname or "").strip():   # 매칭 근거(vid·상품명) 전무 → 측정 불가(이례)
        st.noname_products += 1
        return
    todo = [kw for kw in keywords if not wb.is_rank_filled(biz, pname, kw, date)]
    if not todo:
        return
    if not vids:   # 판매 0 등으로 vid 없음 → 상품명(부분일치)으로 매칭(건너뛰지 않음)
        log(f"  [순위] {biz} · {pname} — vid 없음(판매 0 등) → 상품명으로 매칭")
    matcher = _rank_matcher(vids, pname)
    for idx, kw in enumerate(todo, 1):
        if should_stop() or st.halted:
            break
        if st.measured_any and st.autosubmit:
            # 검색 **사이** 사람속도 간격(버스트 없이 차단 회피). 검색 앞에 두어 마지막 검색 뒤엔
            # 대기 안 함(자투리 제거). 중단형이라 대기 중 '반자동 중지'도 즉시 반응.
            d = random.uniform(config.RANK_NAV_DELAY_MIN_SEC, config.RANK_NAV_DELAY_MAX_SEC)
            _interruptible_sleep(d, should_stop)
            if should_stop() or st.halted:
                break
        browser.to_front()   # 키워드마다 창을 앞으로(다른 창에 가려 못 찾는 것 방지)
        log(f"  🔎 [{biz}] {pname}  ({idx}/{len(todo)})")
        pg, blocked, aborted = _semi_search_one(st, browser, kw, should_stop, log)
        if aborted:          # 검색 직전 pause 중 중지/halt → 키워드 루프 종료
            break
        if pg is None:
            _semi_on_miss(st, kw, blocked, should_stop, log)
            continue
        st.miss_streak = 0   # 성공 → 연속 실패 리셋
        st.cooldowns = 0     # 진전 발생 → 쿨다운 카운터도 리셋(IP 살아있음)
        st.searched += 1     # 종료 요약용 누적(리셋 안 함)
        _semi_record(wb, pg, matcher, biz, pname, kw, date, path, idx, len(todo), log)


def _semi_search_one(st: _SemiState, browser, kw, should_stop, log):
    """키워드 1건 검색 — 자동제출(타이핑+Enter+결과대기) 또는 반자동(자동입력+사람 Enter 대기).

    반환: (pg, blocked, aborted). aborted=True 면 pause 중 중지/halt(호출부가 키워드 루프 종료)."""
    filled = _prefill_search(browser, kw)   # 사람처럼 한 글자씩 타이핑(붙여넣기 아님)
    if st.autosubmit:
        # 타이핑이 이미 사람 리듬(글자별 미세 랜덤)을 재현 → 다 치고 **짧게 멈춘 뒤** 검색(사람 패턴).
        pause = random.uniform(0.5, 1.4)
        log(f"     ⌨ 「{kw}」 한 글자씩 자동 타이핑{'' if filled else '(검색창 못찾음→URL 폴백)'}"
            f" → {pause:.1f}s 뒤 자동검색(Enter)")
        _interruptible_sleep(pause, should_stop)   # 다 치고 잠깐 멈춤(중지 반응 유지)
        if should_stop() or st.halted:
            return None, False, True
        _submit_search(browser)              # 사람 대신 앱이 Enter(제출)
        st.measured_any = True               # 실제 검색 발생 → 다음 키워드는 '검색 사이' 간격 적용
        pg, blocked = _wait_results_loaded(browser, kw, should_stop, config.RANK_SEMI_AUTO_WAIT_SEC)
        return pg, blocked, False
    if filled:
        log(f"     ✅ 검색창에 「{kw}」 자동입력됨 → **빨간 띠 창에서 Enter만** 누르세요"
            f" (안 채워졌으면 직접 입력: {kw})")
    else:
        log(f"     그 창 검색창을 비우고, 아래 '검색어'만 더블클릭해 복사→붙여넣고 Enter:")
        log(f"     검색어 ▶  {kw}")
    return _wait_user_search(browser, kw, log, should_stop), False, False


def _semi_on_miss(st: _SemiState, kw, blocked: bool, should_stop, log) -> None:
    """검색 결과 미감지(pg=None) 처리 — 자동제출은 서킷브레이커(쿨다운 재개/당일 중단), 반자동은 공란."""
    if not st.autosubmit:
        log(f"  [반자동] 「{kw}」 미감지/시간초과 — 공란으로 두고 다음에 이어서 조회합니다")
        return
    st.miss_streak += 1
    if blocked:   # 확정 차단 페이지(사용권한 없음)=IP 막힘 → 3회 안 기다리고 즉시 판정
        st.blocked_total += 1     # 종료 요약용 누적
        st.miss_streak = config.RANK_SEMI_AUTO_MAX_MISS
        log(f"  [반자동] 「{kw}」 쿠팡 접근차단(사용권한 없음) 감지 — **이 IP가 막혔습니다**. "
            "휴대폰 핫스팟 등 **새 IP**에서 재실행하면 남은 것부터 이어서 조회됩니다")
    else:
        log(f"  [반자동] 「{kw}」 결과 미로딩(차단 추정) — 공란. "
            f"연속 {st.miss_streak}/{config.RANK_SEMI_AUTO_MAX_MISS}")
    if st.miss_streak < config.RANK_SEMI_AUTO_MAX_MISS:
        return
    # 하드 스톱 대신 **긴 쿨다운 후 자동 재개**(무인 장시간). 쿨다운 후에도 진전 0이
    # 반복되면(cooldowns 초과) 그때 당일 중단(IP 회복 불가 판단 — 무한 재시도 금지).
    st.cooldowns += 1
    st.cooldown_total += 1        # 종료 요약용 누적(진전 시 cooldowns 만 리셋·이건 유지)
    if st.cooldowns > config.RANK_SEMI_COOLDOWN_MAX:
        st.halted = True
        log(f"  ⛔ 쿨다운 {config.RANK_SEMI_COOLDOWN_MAX}회 후에도 계속 차단 = IP 회복 불가"
            " → 당일 중단. 쉰 시간/다른 IP에서 다시 실행하면 남은 것부터 이어서")
        return
    mins = config.RANK_SEMI_COOLDOWN_SEC // 60
    resume_at = (datetime.now() + timedelta(seconds=config.RANK_SEMI_COOLDOWN_SEC)).strftime("%H:%M")
    log(f"  ⏸ 차단 감지 — 하드중단 대신 {mins}분 쿨다운 후 자동 재개(약 {resume_at}). "
        f"쿨다운 {st.cooldowns}/{config.RANK_SEMI_COOLDOWN_MAX} (재개 후 1개라도 측정되면 리셋)")
    _interruptible_sleep(config.RANK_SEMI_COOLDOWN_SEC, should_stop, log, f"(약 {resume_at})")
    st.miss_streak = 0    # 쿨다운 끝 → 다음 키워드부터 재개


def _semi_record(wb, pg, matcher, biz, pname, kw, date, path, idx, total, log) -> None:
    """검색결과 페이지에서 순위를 파싱해 워크북에 기록·저장(상품마다 저장 → 중단해도 이어서)."""
    from .rank import parse_serp_rank
    human_mouse.browse_serp(pg)   # 결과를 사람처럼 훑어봄(호버·스크롤, 클릭 없음)
    try:
        # 반자동은 로드된 페이지 1장만 읽는다 → 상한 없이 오가닉 전부를 센다(실제 등수 기록). 못 찾으면
        # scanned=이 페이지에서 센 개수 → '{scanned}위밖'(예 44개까지 있으면 '44위밖', 다음 페이지 넘겨야 함).
        res, scanned = parse_serp_rank(pg, matcher, max_rank=config.RANK_SCAN_MAX_SEMI)
    except Exception as exc:
        log(f"  [반자동] 「{kw}」 파싱 실패(공란) — {exc.__class__.__name__}: {str(exc)[:80]}")
        return
    rank, mi = res.get("제품", (None, None))
    wb.set_keyword_rank(biz, pname, kw, date, rank, scanned=scanned)
    log(f"  ✅ 「{kw}」 순위 = {rank_label(rank) if rank else f'{scanned}위밖'}  — 기록 완료({idx}/{total})")
    if mi is not None and getattr(mi, "name", ""):   # 노출명은 로그로만(블록명=등록상품명 고정)
        log(f"  [노출명] 검색결과 노출명 = {mi.name} (블록명은 등록상품명 고정)")
    wb.save(path)
    # (키워드 사이 간격은 _semi_track_product 상단에서 '검색 앞'에 적용 — 마지막 검색 뒤 자투리 대기 제거)
