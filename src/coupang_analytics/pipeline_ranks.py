"""③ 순위(노출조회) — 반자동 검색(자동 타이핑+Enter·화면만 읽음)·egress 회전·track_ranks_stage.

pipeline.py 에서 분리(대형 파일 정비, 행동 불변). 순위 함수 내부 호출·모듈 전역(_ROT 등)은 이 모듈에서
resolve 되므로, 테스트 monkeypatch(핀·시뮬)는 이 모듈(pipeline_ranks)의 심볼을 교체해야 한다(pipeline 아님).
pipeline.py 가 이 심볼들을 다시 import 해 `pipeline.X` 공개 API(UI·도구)를 그대로 유지한다(재수출).
"""
from __future__ import annotations

import hashlib
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import config
from . import human_mouse
from . import proxy_blocklist
from . import proxy_pool
from .browser import WingBrowser
from .kw_recommend import rank_label
from .product_naming import rename_to_exposed
from .rank import human_type_query, make_matcher
from .pipeline_gsheet import push_gsheet, inject_company_stock   # track_ranks_stage 종료 시 결과 반영·회사재고 주입(한 방향·순환 없음)
from .pipeline_paths import _PROFILE, _load_latest_wb, column_label
from .workbook_sales import refresh_sales_sheet


# ── egress 재회전 드라이버 (2026-10-02 · D-030 2026-10-10) ────────────────
# drive_rank 가 ①프록시 선택 ②브라우저 열기 ③egress IP 에코+차단이력 선제 skip(첫 바퀴) ④run_once 실행
# ⑤차단(blocked=True)이면 그 egress 를 차단목록에 기록하고 **새 egress 로 다음 키워드부터**(막힌 키워드는 다음 바퀴·
# 2026-10-13, 횟수 제한 없이 풀을 돌려 씀). 30분 쿨다운·당일 중단은 폐지(D-030). RANK_PROXY_ROTATE_ON_BLOCK=False 거나 프록시 OFF 면
# 1회 open(차단되면 다음 키워드 계속).
# **IP 하나 = 기기 하나(2026-10-13)**: 프록시 주소(sessid)마다 순위 프로필을 따로 두고(_rank_profile), 이번 실행에서 막힌
# (주소, IP)는 그 주소의 IP 가 바뀔 때까지 다시 쓰지 않는다 — 주소가 전부 막힌 IP 면 새 IP 를 기다림(_next_round).
_ROT = {"active": False, "can": (lambda: False)}
_RANK_PROFILE_ROOT = "data/chrome-rank"
_FRESH_IP_WAIT_SEC = 300


def _rank_profile(px) -> str:
    """순위 브라우저 프로필 — 프록시 주소(sessid)마다 따로(쿠키·식별 정보가 IP 하나에만 묶이게). 프록시 없으면 기존 프로필.
    10-13 실측: 한 프로필로 IP 수십 개를 옮겨 다니자 새 IP 도 첫 검색에서 막힘·같은 IP 를 다른 프로필로는 통과.
    폴더 이름 = sessid(없으면 주소 해시) — 자격증명은 경로에 안 넣음."""
    if not px:
        return _PROFILE
    m = re.search(r"sessid[._]([A-Za-z0-9]+)", px)
    return f"{_RANK_PROFILE_ROOT}/{m.group(1) if m else hashlib.sha1(px.encode()).hexdigest()[:10]}"


_EGRESS_MARK = "_rank_egress.txt"          # 프로필 폴더 안 — 그 프로필이 마지막으로 쓴 egress IP
_CLEAR_ORIGINS = ("https://www.coupang.com", "https://coupang.com")


def _identity_follows_ip(browser, profile: str, egress: str, log) -> None:
    """흔적(쿠키·저장소)은 **같은 IP 동안만** 유지(D-058): 프로필이 지난번과 다른 IP 로 나가면 쿠팡 접속 전에 비운다.
    같은 IP = 누적(신용), IP 바뀜 = 비움(흔적이 IP 를 따라다니면 'IP 를 바꿔 가며 숨는 봇' 신호·10-13 실측 77/87 즉시 차단).
    IP 확인은 ipify(쿠팡 아님)라 이 시점엔 아직 쿠팡에 안 들어감. 비우기 실패 = ⚠ 로그 후 진행(기록 안 남겨 다음에 다시)."""
    mark = Path(profile) / _EGRESS_MARK
    try:
        last = mark.read_text(encoding="utf-8").strip()
    except OSError:
        last = ""
    if last == egress:
        return
    try:
        browser.context.clear_cookies()
        cdp = browser.context.new_cdp_session(browser.page)
        for origin in _CLEAR_ORIGINS:
            cdp.send("Storage.clearDataForOrigin", {"origin": origin, "storageTypes": "all"})
        cdp.detach()
    except Exception as exc:
        log(f"  [프록시] ⚠ 흔적 비우기 실패({exc.__class__.__name__}: {str(exc)[:80]}) — 그대로 진행·다음에 다시 시도")
        return
    mark.parent.mkdir(parents=True, exist_ok=True)
    mark.write_text(egress, encoding="utf-8")
    log(f"  [프록시] 🧹 이 프로필의 IP 가 바뀜({last or '처음'} → {egress}) — 쿠팡 흔적(쿠키·저장소) 비우고 시작")


def rotation_can_rotate() -> bool:
    """지금 차단되면 쿨다운 대신 새 egress 로 회전할 수 있는가(drive_rank 가동 중 + 다음 egress 존재)."""
    try:
        return bool(_ROT["active"] and _ROT["can"]())
    except Exception:
        return False


def _echo_egress(browser, proxy_url, log) -> str | None:
    """브라우저(프록시 경유) 자신이 보는 공인 egress IP. 프록시 없거나 선제검사 OFF면 None."""
    if not proxy_url or not getattr(config, "RANK_PROXY_PRECHECK_EGRESS", True):
        return None
    ip = proxy_blocklist.resolve_egress_ip(browser, log)
    log(f"  [프록시] egress 확인 — {ip or '확인 실패'}")
    return ip


def _rank_single_open(offscreen: bool, run_once, log) -> None:
    """회전 OFF/프록시 OFF 경로 — 기존처럼 1회 open(선제skip·회전 없음·동작 불변·핀 경로)."""
    px, ok = proxy_pool.rank_proxy_or_skip(log)
    if not ok:
        return
    with WingBrowser(profile_dir=_rank_profile(px), offscreen=offscreen, proxy=px,
                     block_images=getattr(config, "RANK_BLOCK_IMAGES", False)) as browser:
        run_once(browser, None)


def _run_on_egress(offscreen: bool, px, run_once, log, skip_blocked: bool = True, force: bool = False,
                   skip_pairs=frozenset()):
    """한 egress 로 브라우저를 열어 실행. 반환 (egress_ip, outcome, blocked).

    outcome="skip" = egress 가 차단이력이라 선제 skip(실행 안 함·skip_blocked=True 일 때만) · "ran" = run_once 실행 ·
    "conn" = **IP 확인(에코) 경로가 모두 실패 = 프록시 연결 장애**(2026-10-13 — 쿠팡 검색 없이 넘김·차단 기록 안 함).
    force=True 면 에코 실패여도 실행(에코 서비스 쪽 장애일 수 있어 연속 실패 뒤엔 실제 검색 화면으로 판정).
    skip_pairs = 이번 실행에 막힌 (주소, IP) — 그 주소가 아직 같은 IP 면 검색 없이 "skip"(10-13: 53/55 즉시 차단).
    """
    with WingBrowser(profile_dir=_rank_profile(px), offscreen=offscreen, proxy=px,
                     block_images=getattr(config, "RANK_BLOCK_IMAGES", False)) as browser:
        egress = _echo_egress(browser, px, log)
        if (px and egress is None and not force
                and getattr(config, "RANK_PROXY_PRECHECK_EGRESS", True)):
            log("  [프록시] ⚠ 연결 장애 — IP 확인 실패(쿠팡 차단 아님) → 이 IP 로 검색 안 하고 다음 IP")
            return None, "conn", False
        if px and egress and (px, egress) in skip_pairs:
            log(f"  [프록시] egress {egress} = 이번 실행에 막힌 IP(이 주소의 IP 가 아직 안 바뀜) → 검색 없이 다음 주소")
            return egress, "skip", False
        if skip_blocked and px and egress and proxy_blocklist.is_blocked(egress):
            e = proxy_blocklist.entry(egress) or {}
            log(f"  [프록시] ⚠ egress {egress} = 차단이력({e.get('last', '?')}, "
                f"{e.get('count', '?')}회) → skip, 새 IP 요청")
            return egress, "skip", False
        if px:
            log(f"  [프록시] ✅ egress {egress or '(미확인)'} — 순위 진행")
            if egress:
                _identity_follows_ip(browser, _rank_profile(px), egress, log)
        return egress, "ran", bool(run_once(browser, egress))


def drive_rank(offscreen: bool, run_once, log, should_stop=None, halt_reason=None) -> None:
    """순위 브라우저 수명 + egress 회전/차단목록. run_once(browser, egress_ip) -> blocked(bool).

    blocked=True(=IP 차단으로 중단)면 egress 를 기록하고 **새 egress 로 이어서** 한다(run_once 는 채운 키워드·이번 바퀴에
    미룬 키워드를 건너뜀 — 막힌 키워드는 다음 바퀴에 다시·2026-10-13). **회전 횟수 제한 없이 프록시 풀을 돌려 쓴다**(D-030 — 30분 쿨다운·당일 중단 폐지): 한 바퀴를 다
    쓰면 처음부터 다시 돈다. 단 이번 실행에 막힌 (주소, IP)는 그 주소의 IP 가 바뀔 때까지 건너뛰고, 주소가 전부 그렇다면
    새 IP 를 기다린다(2026-10-13 _next_round). 프로필은 주소마다 따로(_rank_profile). 끝 = 남은 키워드 없음·중지 요청·프록시 설정 오류.
    프록시 OFF/회전 플래그 OFF면 기존처럼 1회 open 만 한다.
    **연결 장애는 차단과 구분(2026-10-13)**: IP 확인 실패(outcome "conn")·halt_reason()=="conn"(검색 중 크롬 연결
    오류 화면)이면 차단 목록에 기록하지 않는다. 연결 장애가 _CONN_STREAK_WAIT 번 이어지면 _CONN_WAIT_SEC 쉬고 다음 IP 는
    IP 확인 실패여도 실제 검색 화면으로 판정한다(에코 서비스 쪽 장애로 영영 못 도는 것 방지).
    """
    should_stop = should_stop or (lambda: False)
    halt_reason = halt_reason or (lambda: "block")
    log = log or (lambda m: None)
    if not getattr(config, "RANK_PROXY_ROTATE_ON_BLOCK", True) or not getattr(config, "PROXY_ENABLED", False):
        _rank_single_open(offscreen, run_once, log)
        return

    prog = {"tried": set(), "round": 1, "rotations": 0, "conn": 0, "pairs": set(), "ran": False}
    _ROT["active"], _ROT["can"] = True, (lambda: True)   # 프록시 풀을 돌려 쓰므로 항상 회전 가능
    try:
        while not should_stop():
            px, ok, status = proxy_pool.pick_rank_proxy(prog["tried"], log)
            if not ok:
                if status != "exhausted":
                    return   # 설정 오류 — pick_rank_proxy 가 이미 로그·순위 스킵(직접연결 안 함)
                _next_round(prog, log, should_stop)
                continue
            egress, outcome, blocked = _run_on_egress(offscreen, px, run_once, log,
                                                      skip_blocked=prog["round"] == 1,
                                                      force=prog["conn"] >= _CONN_STREAK_WAIT,
                                                      skip_pairs=prog["pairs"])
            prog["tried"].add(px)
            if outcome == "skip":
                continue   # 차단 이력 IP — 첫 바퀴에선 다른 IP 먼저
            if outcome == "conn" or (blocked and halt_reason() == "conn"):
                _conn_trouble(prog, log, should_stop)
                continue
            prog["conn"], prog["ran"] = 0, True
            if not blocked or px is None:
                return
            if egress and halt_reason() == "block":
                prog["pairs"].add((px, egress))
                proxy_blocklist.record(egress, "Akamai 검색차단")
                log(f"  [프록시] ⛔ 차단 감지 — egress {egress} 차단목록 등록")
            prog["rotations"] += 1
            log(f"  [프록시] 🔄 새 IP로 전환({prog['rotations']}번째) — 다음 키워드부터(막힌 키워드는 다음 바퀴)")
    finally:
        _ROT["active"], _ROT["can"] = False, (lambda: False)


def _next_round(prog: dict, log, should_stop) -> None:
    """프록시 주소를 한 바퀴 다 씀 → 다음 바퀴. 이번 바퀴에 검색한 주소가 하나도 없으면(전부 막힌 IP·연결 장애)
    업체가 IP 를 바꿔 줄 때까지 _FRESH_IP_WAIT_SEC 기다린다 — 막힌 IP 로 헛 검색하지 않음(비용·신분 보호·2026-10-13)."""
    if prog["round"] > 1 and not prog["ran"]:
        log(f"  [프록시] ⏳ 주소 {len(prog['tried'])}개가 모두 이번 실행에 막힌 IP — 업체가 새 IP 를 줄 때까지 "
            f"{_FRESH_IP_WAIT_SEC // 60}분 대기(막힌 IP 로 검색 안 함)")
        _interruptible_sleep(_FRESH_IP_WAIT_SEC, should_stop)
    prog["tried"], prog["round"], prog["ran"] = set(), prog["round"] + 1, False
    log(f"  [프록시] 풀 한 바퀴 다 씀 → {prog['round']}바퀴째(이번 실행에 막힌 IP 는 건너뜀)")


_CONN_STREAK_WAIT = 3     # 연결 장애가 이만큼 이어지면 쉬었다가(프록시 업체 쪽 장애) 다음 IP 는 실제 화면으로 판정
_CONN_WAIT_SEC = 300


def _conn_trouble(prog: dict, log, should_stop) -> None:
    """프록시 연결 장애 1건 — 차단 목록엔 안 남김. 연속 _CONN_STREAK_WAIT 번이면 _CONN_WAIT_SEC 쉼(중지 즉시 반응)."""
    prog["conn"] += 1
    if prog["conn"] < _CONN_STREAK_WAIT:
        log(f"  [프록시] 🔌 연결 장애 {prog['conn']}회 연속 — 차단 아님(차단 목록에 안 남김) → 다음 IP")
        return
    log(f"  [프록시] 🔌 연결 장애 {prog['conn']}회 연속 — 프록시 업체 쪽 장애 추정 → {_CONN_WAIT_SEC // 60}분 쉬고 "
        "다음 IP 는 실제 검색 화면으로 판정")
    _interruptible_sleep(_CONN_WAIT_SEC, should_stop)


def _rank_matcher(vids):
    """③ 순위 매칭 매처 — **VID 정확 매칭만**(D-030: 쿠팡 상품은 VID 가 반드시 있다 → VID 없음은 오류로 처리하고
    상품명 부분일치로 찾지 않는다·호출부 _semi_prep_product)."""
    return {"제품": make_matcher(vendor_item_ids={str(v) for v in vids if v})}


def _log_quality_summary(wb, log) -> None:
    """③ 순위까지 끝난 뒤 데이터 품질 자가점검을 run_log 에 남긴다(2026-09-28, [[verify-by-data-not-status]]).

    '✅ 완료'가 가리는 불완전(판매중인데 순위 공란=차단/미측정·pid 미확보·미매칭)을 매 실행 즉시 가시화한다.
    순위가 최종 반영된 ③ 종료 시점에만 호출(①만 끝난 시점엔 순위가 당연히 공란이라 오탐). 읽기만·비치명."""
    try:
        q = wb.data_quality_summary()
    except Exception as exc:
        log(f"  [데이터점검] ⚠ 요약 생성 실패(비치명) — {exc.__class__.__name__}: {str(exc)[:80]}")
        return
    anomalies = q["active_blank_rank"] + q["search_link"] + q["miss_vid"]
    head = "⚠ 확인 필요" if anomalies else "이상 없음"
    log(f"== [데이터점검] {head} — 상품 {q['products']} · 판매중인데 순위 공란 {q['active_blank_rank']} · "
        f"상품링크 검색폴백(pid 미확보) {q['search_link']} · 미매칭(vid없음) {q['miss_vid']} ==")
    if anomalies:
        log("==   ↳ '완료'여도 위 수치가 크면 불완전(차단·미수집·미매칭) — 데이터로 확인 후 재실행/재배포 판단 ==")


def _rank_date(wb, biz: str, date_label: str | None) -> str | None:
    """순위를 기록할 날짜 칸 — 지정일(date_label·날짜 지정 실행·소유자 2026-10-10)이면 그 칸(없으면 추가),
    아니면 그 시트의 가장 최근 날짜 칸(기존 동작)."""
    if date_label:
        label = column_label(date_label)   # ①과 같은 '월.일' 칸(ISO 를 그대로 쓰면 다른 칸이 생겼음)
        wb.ensure_date(biz, label)
        return label
    return wb.latest_date(biz)


def track_ranks_stage(out_dir: str = "output", on_log=None,
                      should_stop=None, gsheet_output_url: str | None = None,
                      stock_url: str | None = None, date_label: str | None = None) -> Path | None:
    """③ 노출순위 조회 전용(**반자동**) — 최신 워크북 로드, 상품(고유ID)+키워드로 순위 측정·기록. 로그인 불필요.

    ①(상품ID)·②(키워드)가 이미 워크북에 있어야 한다. 상품마다 저장된 vendorItemId 로 검색결과에서 내
    상품을 찾아 오가닉 순위를 기록한다(가장 최근 일자 컬럼, date_label 을 주면 **그 날짜 칸**·이미 채워진 칸은 건너뜀).
    앱이 보이는 창에서 키워드를 타이핑+Enter 하고 그 화면만 읽는다(offscreen 자동 순위는 폐기·D-022 B5 삭제).
    매칭 시 블록 이름을 검색결과의 **노출명**으로 현행화한다. should_stop() 이 참이면 중도 중단.
    """
    log = on_log or (lambda m: None)
    LAST_RANK.clear()
    config.apply_rank_nav_delay_override(log)   # 설정 탭 순위 간격(config.json)으로 덮어씀 — 없으면 기본 유지
    config.apply_proxy_override(log)            # 노출순위 프록시 설정(config.json proxy/*) 런타임 적용 — 미설정=기본 ON
    config.apply_rank_images_override(log)      # 노출순위 이미지 로드 여부(config.json rank/block_images) — 미설정=기본(이미지 유지)
    out = Path(out_dir)
    wb, path = _load_latest_wb(out)
    if wb is None:
        log("== 순위 조회: 결과 워크북이 없습니다 — 먼저 ①②를 실행하세요 ==")
        return None
    inject_company_stock(wb, stock_url, log)   # 회사보유재고 → 워크북(계정목록 5열) · apply_style 전
    refresh_sales_sheet(wb, out, log)          # 첫 시트 통합판매현황(① 뒤 쌓인 판매 기록 반영)

    def _on_pass():   # 진전 있는 바퀴 끝마다 결과 반영 — 밤새 빈 칸을 다시 돌아도 시트가 따라옴(2026-10-13)
        wb.apply_style()
        wb.save(path)
        push_gsheet(wb, gsheet_output_url, log)

    result = _track_ranks_semi(wb, path, log, should_stop or (lambda: False), date_label, on_pass=_on_pass)
    push_gsheet(wb, gsheet_output_url, log)   # ③ 반자동 순위 채운 뒤 결과 구글시트에도 반영
    _log_quality_summary(wb, log)   # 데이터 품질 자가점검(완료가 가리는 불완전 가시화·③ 최종 시점)
    return result

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


def _block_marker(pg) -> str:
    """현재 페이지가 쿠팡 차단/권한없음 안내 페이지면 **맞은 판정 단어**, 아니면 ''(사람이 그 창에서 봤을 화면)."""
    try:
        txt = pg.inner_text("body")[:400]
    except Exception:
        try:
            txt = pg.title() or ""
        except Exception:
            return ""
    return next((m for m in _BLOCK_PAGE_MARKERS if m in txt), "")


def _looks_blocked(pg) -> bool:
    return bool(_block_marker(pg))


# 차단 판정 증거(2026-10-13): 판정 단어만으론 원인 확정이 안 됐다(10-12 밤 '밀키트' 569회 — 통제 실험이 따로 필요했음).
_EVIDENCE_DIR = Path("output") / "_순위차단"
_EVIDENCE_KEEP = 20


def _save_block_evidence(pg, kw: str, marker: str) -> dict:
    """차단 판정 순간의 화면 증거(판정 단어·주소·제목·본문 앞부분 txt + 캡처 png)를 최근 _EVIDENCE_KEEP 건만 남긴다.
    반환 {marker, file} — 저장 실패는 {marker, error}(호출부가 로그에 그대로 남김·검색 흐름은 계속)."""
    info = {"marker": marker}
    try:
        _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        stem = f"{datetime.now():%m%d_%H%M%S_%f}_{re.sub(r'[^0-9A-Za-z가-힣]', '_', kw)[:20]}"
        body = pg.inner_text("body")[:1500]
        (_EVIDENCE_DIR / f"{stem}.txt").write_text(
            f"키워드: {kw}\n판정 단어: {marker}\n주소: {_live_url(pg)}\n제목: {pg.title()}\n\n{body}", encoding="utf-8")
        pg.screenshot(path=str(_EVIDENCE_DIR / f"{stem}.png"))
        info["file"] = stem
        for old in sorted(_EVIDENCE_DIR.glob("*.txt"))[:-_EVIDENCE_KEEP]:
            old.unlink()
            old.with_suffix(".png").unlink(missing_ok=True)
    except Exception as exc:
        info["error"] = f"{exc.__class__.__name__}: {str(exc)[:80]}"
    return info


def _connection_down(browser) -> bool:
    """창이 크롬 연결 오류 페이지(chrome-error://)면 True — 프록시 경로 장애(쿠팡 차단 아님·2026-10-13 구분)."""
    try:
        return any(_live_url(pg).startswith("chrome-error://") for pg in _all_pages(browser))
    except Exception:
        return False   # 창 상태를 못 읽음 = 판정 불가 → 일반 미로딩으로 처리(연결 장애로 단정 안 함)


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


def _submit_search(browser, kw: str) -> None:
    """자동제출 — 프리필된 검색창에서 Enter(사이트 자체 JS로 검색=사람 조작에 가장 가까움). 실패 시 버튼/폼 폴백.

    ⚠ 이중 검색요청 방지(2026-10-02): 예전엔 Enter 직후 **무조건** _SUBMIT_JS(버튼클릭/폼submit)를 또 실행해,
    Enter 가 이미 네비를 시작한 경우 같은 쿼리가 두 번 제출될 수 있었다(검색결과 페이지엔 같은 검색창·버튼이
    있어 재제출됨). 이제 Enter 후 URL q 가 kw 로 바뀌는지 RANK_SUBMIT_CONFIRM_SEC 동안 확인해, **네비가
    시작됐으면 폴백을 생략**한다. Enter 가 폼을 못 넘긴 레이아웃일 때만(확인 실패) 버튼/폼 제출로 폴백한다.
    (자동 경로 rank._load_results 의 _await_query_navigated 와 같은 '네비 확인' 패턴.)
    성공 여부(결과 로드)는 이 함수가 아니라 이후 _wait_results_loaded 로 판정한다.
    """
    try:
        browser.page.keyboard.press("Enter")
    except Exception:
        pass
    want = kw.replace(" ", "")
    deadline = time.time() + max(0.0, getattr(config, "RANK_SUBMIT_CONFIRM_SEC", 2.0))
    while True:
        try:
            if _search_q(_live_url(browser.page)) == want:
                return   # Enter 로 검색 네비 시작 확인 → 버튼/폼 폴백 생략(이중 요청 방지)
        except Exception:
            pass
        if time.time() >= deadline:
            break
        time.sleep(0.1)
    # Enter 로 안 넘어가는 레이아웃(네비 미확인) — 그때만 검색버튼/폼 제출 폴백(진짜 폴백)
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
            marker = _block_marker(pg)
            if marker:                # 확정 차단 페이지 → 증거 남기고 데드라인(40s) 안 기다리고 즉시 반환(빠른 반응)
                return None, _save_block_evidence(pg, kw, marker)
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
    halted: bool = False        # 차단 → 이 IP 로는 그만(drive_rank 가 새 IP 로 다시 엶)
    miss_streak: int = 0        # 자동제출 연속 실패 수(성공 시 0으로 리셋)
    novid_products: int = 0     # VID 가 없어 측정 못 한 상품 수(오류·종료 요약)
    measured_any: bool = False  # 첫 검색 전엔 대기 없음·마지막 검색 뒤에도 대기 없음(간격은 '검색 사이'에만)
    # ── 종료 요약용 **누적** 카운터(실행 전체 합계) ──
    searched: int = 0           # 실제 측정(순위 기록)된 검색 건수
    blocked_total: int = 0      # 차단 판정 총 횟수(차단 페이지 또는 연속 미로딩)
    rotations: int = 0          # 차단으로 새 IP 로 바꾼 횟수
    conn_fail: int = 0          # 프록시 연결 장애(chrome-error 페이지) 횟수 — 차단과 구분(2026-10-13)
    # ── 바퀴(pass) 단위 완주(2026-10-13): 막힌 키워드는 이번 바퀴에서 뒤로 미루고 다음 바퀴에 다시 ──
    deferred: set = field(default_factory=set)   # 이번 바퀴에 미룬 (사업자, 상품, 키워드)
    novid: set = field(default_factory=set)      # VID 없어 ❌ 기록한 (사업자, 상품) — 바퀴마다 중복 기록 방지
    pass_no: int = 1
    pass_mark: int = 0          # 이번 바퀴 시작 때의 searched(진전 판정)
    pass_trouble: bool = False  # 이번 바퀴에 차단/연결 장애가 있었나(없는데 진전도 없으면 측정 불가로 마침)
    halt_reason: str = ""       # 'block' | 'conn' | 'miss' — drive_rank 가 차단 IP 기록 여부 판단(conn 은 기록 안 함)
    unfilled: list = field(default_factory=list)   # 끝날 때 남은 빈 칸 (사업자, 상품, 키워드)


# 끝난 ③ 순위의 요약(UI 완료 문구·도구가 읽음 — 빈 칸이 남으면 '완료' 대신 ⚠·2026-10-13). run_stages 가 시작 때 비움.
LAST_RANK: dict = {}


def _track_ranks_semi(wb, path, log, should_stop, date_label: str | None = None, on_pass=None) -> Path:
    """반자동 순위조회 — 보이는 창에서 앱이 키워드를 사람처럼 타이핑+Enter, 검색결과 화면만 읽어 순위 산출·기록.

    offscreen 네비게이션·직접 fetch 없음(차단 회피·DESIGN §5.2). 상품마다 저장 → 중단해도 이어서.
    **바퀴 단위 완주(2026-10-13)**: 막힌 키워드는 이번 바퀴에서 뒤로 미루고 다음 키워드로 간다(한 키워드에 갇히지
    않음). 한 바퀴가 끝나면 남은 빈 칸만 다시 돈다 — 빈 칸이 0 이 되거나 중지 요청까지. 차단·연결 장애 없이 한 바퀴
    진전이 없으면(검색결과가 안 나오는 키워드) ❌ 로 남기고 마친다. on_pass() = 진전 있는 바퀴 끝마다 결과 반영.
    """
    st = _SemiState()
    LAST_RANK.clear()
    _semi_start_log(log)

    def _run_semi(browser, egress) -> bool:
        st.halted, st.halt_reason, st.miss_streak = False, "", 0   # 새 egress → 이어서(누적 카운터·미룬 키워드 유지)
        _semi_browser_prep(browser)
        while not should_stop():
            _semi_one_pass(st, browser, wb, path, date_label, should_stop, log)
            if should_stop() or st.halted:
                break
            if not _semi_next_pass(st, wb, date_label, on_pass, log):
                break
        return st.halted and not should_stop()   # 차단 중단 → drive_rank 가 새 egress 로 이어서

    drive_rank(offscreen=False, run_once=_run_semi, log=log, should_stop=should_stop,
               halt_reason=lambda: st.halt_reason)
    wb.apply_style()
    wb.save(path)
    st.unfilled = _unfilled(wb, date_label)
    if st.novid_products:
        log(f"  ❌ [순위] VID 없는 상품 {st.novid_products}개 — 매칭 실패(①판매수집에서 VID 를 못 찾음) 확인 필요·순위 공란")
    log("== 반자동 노출순위 종료 — 진행분 저장됨" + (f" · ⚠ 빈 칸 {len(st.unfilled)}개 남음 ==" if st.unfilled else " ==="))
    LAST_RANK.update(searched=st.searched, blocked=st.blocked_total, conn=st.conn_fail,
                     unfilled=len(st.unfilled), novid=st.novid_products, stopped=bool(should_stop()))
    _semi_summary_log(st, log)
    return path


def _semi_one_pass(st: _SemiState, browser, wb, path, date_label, should_stop, log) -> None:
    """한 바퀴 — 모든 사업자·상품의 빈 칸(이번 바퀴에 미룬 것 제외)을 차례로 검색."""
    for biz in wb.account_sheets():
        if should_stop() or st.halted:
            return
        date = _rank_date(wb, biz, date_label)
        if not date:
            continue
        for pname in wb.products_of(biz):
            if should_stop() or st.halted:
                return
            _semi_track_product(st, browser, wb, biz, pname, date, path, should_stop, log)


def _semi_next_pass(st: _SemiState, wb, date_label, on_pass, log) -> bool:
    """바퀴 끝 — 남은 빈 칸이 있으면 다음 바퀴 준비(True). 빈 칸 0 또는 '진전·차단·연결 장애 모두 없음'이면 False."""
    left = _unfilled(wb, date_label)
    progressed = st.searched > st.pass_mark
    if progressed and on_pass:
        on_pass()                          # 진전 있는 바퀴마다 결과 반영(밤새 돌아도 시트가 따라옴)
    if not left:
        return False
    if not progressed and not st.pass_trouble:
        for biz, pname, kw in left:        # 차단도 연결 장애도 아닌데 화면이 계속 안 나옴 = 측정 불가 → 무한 반복 대신 마침
            log(f"  ❌ [순위] {biz} · {pname} 「{kw}」 — 검색결과가 두 바퀴 연속 안 나옴(차단·연결 장애 아님) → 공란, 확인 필요")
        return False
    st.pass_no += 1
    st.pass_mark, st.pass_trouble = st.searched, False
    st.deferred.clear()
    log(f"== [순위] {st.pass_no}바퀴째 — 남은 빈 칸 {len(left)}개 다시(막혔던 키워드) ==")
    return True


def _rank_todo(wb, biz, pname, date):
    """순위를 채울 대상이면 (vids, 빈 키워드 목록), 아니면 None.
    생략: 수집주기 밖·판매중지(rank_suppressed)·키워드 없음(2차 옵션)·다 채움. vids = sibling_vids(전 옵션·아이템위너)."""
    if wb.has_marketing() and not wb.product_due(biz, pname, date)[0]:
        return None                        # 상품 수집 주기(마케팅 상품만 매일) — 오늘 대상 아니면 순위도 생략
    if wb.rank_suppressed(biz, pname):     # 판매중지·임시저장·승인반려·대장취소선 → 순위 제외(소유자 2026-09-22)
        return None
    keywords = wb.product_keywords(biz, pname)
    if not keywords:                       # 2차 옵션 블록(키워드 없음)은 순위 대상 아님
        return None
    todo = [kw for kw in keywords if not wb.is_rank_filled(biz, pname, kw, date)]
    if not todo:
        return None
    return wb.sibling_vids(biz, pname), todo


def _unfilled(wb, date_label) -> list:
    """아직 빈 순위 칸 (사업자, 상품, 키워드) — VID 없는 상품(❌ 따로 집계)은 뺀다."""
    out = []
    for biz in wb.account_sheets():
        date = _rank_date(wb, biz, date_label)
        if not date:
            continue
        for pname in wb.products_of(biz):
            t = _rank_todo(wb, biz, pname, date)
            if t and t[0]:
                out += [(biz, pname, kw) for kw in t[1]]
    return out


def _semi_summary_log(st: _SemiState, log) -> None:
    """순위 단계 종료 요약 — 측정·차단·연결 장애·IP 전환·빈 칸·VID 없음 누적 + 검색간격. 차단이 있으면 간격 상향 검토를 안내."""
    log(f"== [순위요약] 측정 {st.searched}건 · 빈 칸 {len(st.unfilled)} · 차단감지 {st.blocked_total}회 · "
        f"연결 장애 {st.conn_fail}회 · IP 전환 {st.rotations}회 · {st.pass_no}바퀴 · VID 없음 {st.novid_products} · "
        f"검색간격 {config.RANK_NAV_DELAY_MIN_SEC}~{config.RANK_NAV_DELAY_MAX_SEC}s ==")
    if st.blocked_total:
        log("== [순위요약] ⚠ 차단 발생 — 검색간격(설정 탭 '순위 간격' · config RANK_NAV_DELAY) 상향 검토 · "
            f"증거 화면 = {_EVIDENCE_DIR} ==")
    else:
        log("== [순위요약] 차단 0 — 현재 검색간격 유지 ==")


def _semi_start_log(log) -> None:
    log("== 반자동(자동검색) 노출순위 시작 — 앱이 키워드 자동입력+Enter까지 수행(손 안 대도 됨). "
        f"키워드 간 {config.RANK_NAV_DELAY_MIN_SEC}~{config.RANK_NAV_DELAY_MAX_SEC}s 간격, "
        "막힌 키워드는 뒤로 미루고 다음 키워드 계속(프록시면 새 IP), 한 바퀴 끝나면 빈 칸만 다시 — 다 채울 때까지 ==")


def _semi_browser_prep(browser) -> None:
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


def _semi_prep_product(st: _SemiState, wb, biz, pname, date, log):
    """반자동 순위 추적 전 가드/준비 — 대상 아니면 None, 대상이면 (matcher, todo).

    생략: _rank_todo 생략분·**이번 바퀴에 미룬 키워드**·**VID 없음(❌오류·D-030 — 바퀴마다 중복 기록 안 함)**."""
    t = _rank_todo(wb, biz, pname, date)
    if t is None:
        return None
    vids, todo = t
    todo = [kw for kw in todo if (biz, pname, kw) not in st.deferred]
    if not todo:
        return None
    if not vids:   # 쿠팡 상품은 VID 가 반드시 있다 → 없음 = ①매칭 실패 오류(상품명으로 찾지 않음·D-030)
        if (biz, pname) not in st.novid:
            st.novid.add((biz, pname))
            st.novid_products += 1
            log(f"  ❌ [순위] {biz} · {pname} — VID 없음(매칭 실패 오류) → 순위 검색 안 함")
        return None
    return _rank_matcher(vids), todo


def _semi_track_product(st: _SemiState, browser, wb, biz, pname, date, path, should_stop, log) -> None:
    """한 상품의 미기입 키워드를 순회하며 반자동 검색·순위 기록(상태기계는 st 로 공유).
    못 잡은 키워드는 이번 바퀴에서 뒤로 미룬다(st.deferred) — 다음 키워드로 가고 다음 바퀴에 다시."""
    prep = _semi_prep_product(st, wb, biz, pname, date, log)
    if prep is None:
        return
    matcher, todo = prep
    seen_name = ""                         # 검색결과 노출명(이 상품 키워드를 다 돈 뒤 블록 이름 현행화·D-013)
    for idx, kw in enumerate(todo, 1):
        if should_stop() or st.halted:
            break
        if st.measured_any:
            # 검색 **사이** 사람속도 간격(버스트 없이 차단 회피). 검색 앞에 두어 마지막 검색 뒤엔
            # 대기 안 함(자투리 제거). 중단형이라 대기 중 '반자동 중지'도 즉시 반응.
            d = random.uniform(config.RANK_NAV_DELAY_MIN_SEC, config.RANK_NAV_DELAY_MAX_SEC)
            _interruptible_sleep(d, should_stop)
            if should_stop() or st.halted:
                break
        browser.to_front()   # 키워드마다 창을 앞으로(다른 창에 가려 못 찾는 것 방지)
        log(f"  🔎 [{biz}] {pname}  ({idx}/{len(todo)}){f' · {st.pass_no}바퀴째' if st.pass_no > 1 else ''}")
        pg, blocked, aborted = _semi_search_one(st, browser, kw, should_stop, log)
        if aborted:          # 검색 직전 pause 중 중지/halt → 키워드 루프 종료
            break
        if pg is None:
            st.deferred.add((biz, pname, kw))
            _semi_on_miss(st, kw, blocked, _connection_down(browser), log)
            continue
        st.miss_streak = 0   # 성공 → 연속 실패 리셋
        st.searched += 1     # 종료 요약용 누적(리셋 안 함)
        seen_name = _semi_record(wb, pg, matcher, biz, pname, kw, date, path, idx, len(todo), log) or seen_name
    if seen_name:
        rename_to_exposed(wb, biz, pname, seen_name, log)
        wb.save(path)


def _semi_search_one(st: _SemiState, browser, kw, should_stop, log):
    """키워드 1건 검색 — 자동제출(사람처럼 타이핑 → 짧은 멈춤 → Enter → 결과 대기).

    반환: (pg, blocked, aborted). blocked = 차단 증거 dict(판정 단어·증거 파일) 또는 False.
    aborted=True 면 pause 중 중지/halt(호출부가 키워드 루프 종료)."""
    filled = _prefill_search(browser, kw)   # 사람처럼 한 글자씩 타이핑(붙여넣기 아님)
    # 타이핑이 이미 사람 리듬(글자별 미세 랜덤)을 재현 → 다 치고 **짧게 멈춘 뒤** 검색(사람 패턴).
    pause = random.uniform(0.5, 1.4)
    log(f"     ⌨ 「{kw}」 한 글자씩 자동 타이핑{'' if filled else '(검색창 못찾음→URL 폴백)'}"
        f" → {pause:.1f}s 뒤 자동검색(Enter)")
    _interruptible_sleep(pause, should_stop)   # 다 치고 잠깐 멈춤(중지 반응 유지)
    if should_stop() or st.halted:
        return None, False, True
    _submit_search(browser, kw)          # 사람 대신 앱이 Enter(제출) — 네비 확인 후에만 폼 폴백(이중요청 방지)
    st.measured_any = True               # 실제 검색 발생 → 다음 키워드는 '검색 사이' 간격 적용
    pg, blocked = _wait_results_loaded(browser, kw, should_stop, config.RANK_SEMI_AUTO_WAIT_SEC)
    return pg, blocked, False


def _semi_on_miss(st: _SemiState, kw, blocked, conn: bool, log) -> None:
    """검색 결과 미감지(pg=None) 처리 — 키워드는 호출부가 이미 뒤로 미룸. 원인을 셋으로 나눠 기록한다(2026-10-13):
    연결 장애(크롬 연결 오류 화면=프록시 경로·쿠팡 차단 아님) · 차단(판정 단어+증거 화면) · 미로딩(연속 N회면 IP 의심).
    연결 장애·차단은 즉시, 미로딩은 연속 N회면 프록시 새 IP 로 전환(없으면 다음 키워드 계속). 쿨다운·당일 중단 없음(D-030)."""
    st.miss_streak += 1
    reason = "miss"
    if conn:
        st.conn_fail += 1
        st.pass_trouble, reason = True, "conn"
        st.miss_streak = config.RANK_SEMI_AUTO_MAX_MISS
        log(f"  [반자동] 「{kw}」 연결 장애(크롬 연결 오류 화면 — 프록시 경로 끊김·쿠팡 차단 아님) → 뒤로 미룸")
    elif blocked:   # 확정 차단 페이지(사용권한 없음)=IP 막힘 → 3회 안 기다리고 즉시 판정
        st.blocked_total += 1     # 종료 요약용 누적
        st.pass_trouble, reason = True, "block"
        st.miss_streak = config.RANK_SEMI_AUTO_MAX_MISS
        ev = blocked if isinstance(blocked, dict) else {}
        log(f"  [반자동] 「{kw}」 쿠팡 접근차단 감지(판정 단어 '{ev.get('marker', '?')}' · 증거 "
            f"{ev.get('file') or ev.get('error', '없음')}) → 뒤로 미루고 다음 키워드")
    else:
        log(f"  [반자동] 「{kw}」 결과 미로딩 → 뒤로 미룸(다음 바퀴 다시). "
            f"연속 {st.miss_streak}/{config.RANK_SEMI_AUTO_MAX_MISS}")
    if st.miss_streak < config.RANK_SEMI_AUTO_MAX_MISS:
        return
    st.miss_streak = 0
    if rotation_can_rotate():
        st.rotations += 1
        st.halted, st.halt_reason = True, reason   # drive_rank 가 (차단이면) egress 기록 후 새 IP 로 다음 키워드부터
        log("  ⟳ 프록시 새 IP 로 전환 — 다음 키워드부터(막힌 키워드는 다음 바퀴에 다시)")
        return
    log("  ⚠ 바꿀 프록시 IP 없음 → 쉬지 않고 다음 키워드 계속(막힌 키워드는 다음 바퀴에 다시)")


def _semi_record(wb, pg, matcher, biz, pname, kw, date, path, idx, total, log) -> str:
    """검색결과 페이지에서 순위를 파싱해 워크북에 기록·저장(상품마다 저장 → 중단해도 이어서).
    반환 = 잡힌 상품의 검색결과 노출명(없으면 "") — 호출부가 상품 루프 끝에 블록 이름 현행화."""
    from .rank import parse_serp_rank
    human_mouse.browse_serp(pg)   # 결과를 사람처럼 훑어봄(호버·스크롤, 클릭 없음)
    try:
        # 반자동은 로드된 페이지 1장만 읽는다 → 상한 없이 오가닉 전부를 센다(실제 등수 기록). 못 찾으면
        # scanned=이 페이지에서 센 개수 → '{scanned}위밖'(예 44개까지 있으면 '44위밖', 다음 페이지 넘겨야 함).
        res, scanned = parse_serp_rank(pg, matcher, max_rank=config.RANK_SCAN_MAX_SEMI)
    except Exception as exc:
        log(f"  [반자동] 「{kw}」 파싱 실패(공란) — {exc.__class__.__name__}: {str(exc)[:80]}")
        return ""
    rank, mi = res.get("제품", (None, None))
    wb.set_keyword_rank(biz, pname, kw, date, rank, scanned=scanned)
    log(f"  ✅ 「{kw}」 순위 = {rank_label(rank) if rank else f'{scanned}위밖'}  — 기록 완료({idx}/{total})")
    name = ""
    if mi is not None and getattr(mi, "name", ""):   # 검색결과 노출명 → 상품 루프 끝에 블록 이름 현행화(D-013)
        log(f"  [노출명] 검색결과 노출명 = {mi.name}")
        wb.set_product_pid(biz, pname, getattr(mi, "product_id", ""))   # 항목3: 상품명 하이퍼링크용 productId
        name = mi.name
    wb.save(path)
    # (키워드 사이 간격은 _semi_track_product 상단에서 '검색 앞'에 적용 — 마지막 검색 뒤 자투리 대기 제거)
    return name
