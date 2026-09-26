"""③ 순위(노출조회) — 측정 헬퍼·서킷브레이커·자동/반자동 검색·track_ranks_stage.

pipeline.py 에서 분리(대형 파일 정비, 행동 불변). 순위 함수 내부 호출·모듈 전역(_RANK_HALT 등)은 이 모듈에서
resolve 되므로, 테스트 monkeypatch(핀·시뮬)는 이 모듈(pipeline_ranks)의 심볼을 교체해야 한다(pipeline 아님).
pipeline.py 가 이 심볼들을 다시 import 해 `pipeline.X` 공개 API(UI·도구)를 그대로 유지한다(재수출).
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from . import config
from . import human_mouse
from . import session_state
from .browser import WingBrowser
from .kw_recommend import rank_label
from .rank import (RankBlocked, human_type_query, make_matcher, organic_ranks,
                   organic_ranks_batch, warmup)
from .pipeline_gsheet import _push_gsheet   # track_ranks_stage 종료 시 결과 반영(한 방향·순환 없음)
from .pipeline_paths import _PROFILE, _load_latest_wb


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
                    wb.set_product_pid(biz, pname, getattr(mi, "product_id", ""))   # 항목3: 상품명 하이퍼링크용
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
        wb.set_product_pid(biz, pname, getattr(mi, "product_id", ""))   # 항목3: 상품명 하이퍼링크용 productId
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


def _semi_prep_product(st: _SemiState, wb, biz, pname, date, log):
    """반자동 순위 추적 전 가드/준비 — 대상 아니면 None, 대상이면 (matcher, todo).

    생략: 수집주기 밖·판매중지(rank_suppressed)·키워드 없음(2차 옵션)·미기입 todo 없음.
    matcher = sibling_vids(전 옵션 vid 합집합·아이템위너 놓침 방지), vid 없으면 상품명(부분일치)."""
    if wb.has_marketing() and not wb.product_due(biz, pname, date)[0]:
        return None                        # 상품 수집 주기(마케팅 상품만 매일) — 오늘 대상 아니면 순위도 생략
    if wb.rank_suppressed(biz, pname):     # 판매중지·임시저장·승인반려·대장취소선 → 순위 제외(소유자 2026-09-22)
        return None
    vids = wb.sibling_vids(biz, pname)     # 리스팅 전 옵션 vid 합집합(아이템위너 놓침 방지)
    keywords = wb.product_keywords(biz, pname)
    if not keywords:                       # 2차 옵션 블록(키워드 없음)은 순위 대상 아님
        return None
    if not vids and not (pname or "").strip():   # 매칭 근거(vid·상품명) 전무 → 측정 불가(이례)
        st.noname_products += 1
        return None
    todo = [kw for kw in keywords if not wb.is_rank_filled(biz, pname, kw, date)]
    if not todo:
        return None
    if not vids:   # 판매 0 등으로 vid 없음 → 상품명(부분일치)으로 매칭(건너뛰지 않음)
        log(f"  [순위] {biz} · {pname} — vid 없음(판매 0 등) → 상품명으로 매칭")
    return _rank_matcher(vids, pname), todo


def _semi_track_product(st: _SemiState, browser, wb, biz, pname, date, path, should_stop, log) -> None:
    """한 상품의 미기입 키워드를 순회하며 반자동 검색·순위 기록(상태기계는 st 로 공유)."""
    prep = _semi_prep_product(st, wb, biz, pname, date, log)
    if prep is None:
        return
    matcher, todo = prep
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
        wb.set_product_pid(biz, pname, getattr(mi, "product_id", ""))   # 항목3: 상품명 하이퍼링크용 productId
    wb.save(path)
    # (키워드 사이 간격은 _semi_track_product 상단에서 '검색 앞'에 적용 — 마지막 검색 뒤 자투리 대기 제거)
