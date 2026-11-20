"""쿠팡 정산 파일 배치 다운로드(별도 프로그램) — 위탁계정마다 'N일 요청 → N+1일 받기' + 집계.

**사무실에서 실행**(로그인=앱과 같은 반자동: 보이는 창·비번 자동입력·2차인증은 사람·비번 오류는 재시도 없이 건너뜀).

  python tools/settlement_download.py probe    [--accounts ID]        # 읽기만 확인(최근 30일 일정·목록, 요청 안 함)
  python tools/settlement_download.py request  [--from 2026-01-01] [--to 2026-01-31] [--cap 5] [--dry-run] [--accounts ID,ID]
  python tools/settlement_download.py download [--accounts ID,ID]       # 다음날: 완료분 받기
  python tools/settlement_download.py run      [--from …] [--to …] [--accounts …]   # 요청+받기 한 세션(전체 확대용)
  python tools/settlement_download.py watch                             # 운용 PC 상시: 00:10 앱 ①판매수집 완료 후 받기·24:00 멈춤
  python tools/settlement_download.py stats                             # 받은 파일 집계 엑셀
  python tools/settlement_download.py merge --src output\정산\정산          # 다른 PC 정산 폴더 합치기(자동 실행 중지 후)
  (request·download·run 에 --originals <폴더> = 받은 쿠팡 원본을 그대로 증빙 폴더에 복사 — D-062)
  python tools/settlement_download.py evidence --out <증빙 상위 폴더> [--from 2026-01-01] [--accounts …] [--until 17:30] [--redo]
      # 계정마다 증빙 원본 전체(정산 원본·판매분석 월별·지급 증빙 메뉴 — D-067). 끝난 계정(_수집완료.json)은 건너뜀

규칙(차단 위험 완화·소유자 2026-10-06): 정산현황 '정산확정' 줄만 · 윙은 월별(최종액) 파일이 나온 달이면 주정산 생략 ·
로켓그로스는 같은 매출 주 1회·비용 리포트는 그 주 금액이 있는 종류만 · 계정당 실행 상한(--cap) · 요청 사이 45~75초
(앱 반자동 순위 간격) · 쿠팡이 대기시간 응답(remainingTime)하면 그 계정 요청 중단 · **화면 이동·호출마다 차단 검사 →
감지 시 그 계정 즉시 중단** · 연속 2계정 실패/차단이면 전체 중단. 호출 방식=화면 뒤 주소 직접(settlement_wing_api —
화면 기간 입력이 안 먹어 엉뚱한 줄 요청 위험 제거·요청 수는 화면과 같음). 요청 후 약 1분이면 완료(실측)라 같은 날
download 도 됨. 같은 PC 동시 실행: 그 계정 프로필 Chrome 이 떠 있으면 건너뜀·
reap_orphan_chrome 미호출. 기록: output/정산/로그/(실행·처리기록·오류) — settlement_runlog. 데이터 폴더는 앱과 같게
(로그인된 계정 프로필 재사용) `COUPANG_DATA_ROOT` 로 지정 가능.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

# numpy(OpenBLAS — openpyxl 이 부름)가 CPU 스레드 수만큼 버퍼를 잡아 프로세스마다 커밋 약 700MB(22스레드 실측 9→703MB ·
# 1스레드 9→28MB · T-113 D-346) — numpy 를 부를 수 있는 어떤 import 보다 먼저. 우리 코드는 numpy 계산을 안 씀.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics import apppaths  # noqa: E402
from coupang_analytics import daily_snapshot  # noqa: E402
from coupang_analytics import memory_log as ML  # noqa: E402
from coupang_analytics import settlement_accounts as SA  # noqa: E402
from coupang_analytics import settlement_files as SF  # noqa: E402
from coupang_analytics import settlement_forecast as FC  # noqa: E402
from coupang_analytics import settlement_jobs as SJ  # noqa: E402
from coupang_analytics import settlement_runlog as RL  # noqa: E402
from coupang_analytics import settlement_store as STORE  # noqa: E402
from coupang_analytics.settlement_store import AMOUNTS, BASE, COSTS, FILES, JOBS, VERIFY  # noqa: E402,F401
from coupang_analytics import settlement_wing_api as API  # noqa: E402

GAP_SEC = (45, 75)                                      # 요청 사이 = 앱 반자동 순위 간격과 같게(소유자 2026-10-06)
LOOKUP_GAP_SEC = (3, 8)                                 # 조회·받기 사이(화면에서 넘겨 보는 정도)
AMOUNTS_FROM = date(2025, 11, 1)                        # 지급 내역 기록 시작 — 2026 첫 30% 줄의 70% 몫(2025-11·12 판매)·2025 보류(D-083)
LOG: RL.RunLog = None  # type: ignore[assignment]   # main() 에서 실행 시작 시 생성
CHANNELS: tuple = ()                                    # --channel 로 제한(비우면 윙·로켓그로스 둘 다)
ORIGINALS: Path | None = None                           # --originals: 받은 쿠팡 원본 그대로 복사할 증빙 폴더(D-062)
REUSE_FROM: Path | None = None                          # transfer-settle 만: 원장 정산 파일 폴더 — 같은 파일이면 요청 안 하고 복사(D-187)


def log(m: str) -> None:
    if LOG is None:
        print(m, flush=True)
    else:
        LOG.line(m)


MEMLOG = ML.Tracker("정산 프로세스")   # D-346 ④ 단계 경계 [메모리] 줄 · 회차 종합 한 줄(watch 1프로세스 = 1회차)


def _mem(stage: str, note: str = "") -> None:
    log(MEMLOG.line(stage, note=note))


class SessionSkip(Exception):
    """이 계정은 이번 실행에서 건너뜀(사용 중·비번 없음·로그인 미완료) — 오류 아님."""


class BlockDetected(Exception):
    """쿠팡 차단 화면(Access Denied 등) 감지 — 그 계정 즉시 중단."""


def _is_browser_closed(exc: BaseException) -> bool:
    """브라우저/탭이 닫혀 생긴 오류인지(차단이 아님). 00:10 앱 시작 시 reap_orphan_chrome 이 정산 Chrome 을
    같이 종료하면 playwright 가 TargetClosedError 를 던진다 — 이걸 '차단'·'연속 실패'로 세면 안 된다(일시적·재시도)."""
    name = exc.__class__.__name__
    msg = str(exc)
    return ("TargetClosed" in name
            or "Target page, context or browser has been closed" in msg
            or "has been closed" in msg
            or "Browser closed" in msg
            or "Connection closed" in msg)


# ── 계정·세션 ─────────────────────────────────────────────────────
def _accounts_from_file() -> list:
    """옛 방식 — 정산 계정 파일(계정ID·비번·대표자-사업자). 설정 settlement/account_source=file 일 때만."""
    from coupang_analytics import appconfig
    path = appconfig.get(SA.CONFIG_KEY, "") or SA.DEFAULT_PATH
    try:
        accts, warns = SA.read_accounts_file(path)
    except SA.AccountsFileError as exc:
        raise SystemExit(f"정산 계정 파일 오류: {exc}") from exc
    for w in warns:
        log(f"  [계정 파일] {w}")
    log(f"  [계정 파일] {path} · 계정 {len(accts)}개")
    return accts


def _accounts_from_registry() -> list:
    """D-103 — 셀독계정상품이력관리원장(링크 = 설정 registry/url)에서 정산 계정을 만든다: 셀독원장(관리중·관리중단 — 기간 제한 없음 D-211
    · 오입력 제외) + 정산전용계정 시트(모든 줄). 원장이 오래됐거나 못 읽으면 중단(옛 계정 파일로 대신하지 않음)."""
    from coupang_analytics import appconfig, gsheet_api, registry_gsheet as RG, registry_settle as RS
    url = appconfig.get("registry/url", "")
    if not url:
        raise SystemExit("정산 계정 출처 = 원장인데 원장 링크(설정 탭 '원장')가 비어 있음 — 링크를 넣고 다시 실행")
    try:
        client = gsheet_api.GSheetClient(url, on_log=log)
        reg = RG.load_registry(client)
        titles = client.sheet_titles()
        settle, warns = (RS.parse_settle(client.read_values(RS.SHEET_SETTLE)) if RS.SHEET_SETTLE in titles else ({}, []))
        last = SA.last_sync_time(client.read_values("동기화기록"))
        accts, info = SA.accounts_from_registry(reg, settle, last, datetime.now())
    except (SA.AccountSourceError, RS.SettleSheetError) as exc:
        raise SystemExit(f"정산 계정(원장) 구성 실패: {exc}") from exc
    except Exception as exc:   # 링크·권한·시트 누락 등 — 이유를 그대로 남기고 중단
        raise SystemExit(f"정산 계정(원장) 읽기 실패 — 설정 탭 원장 링크·서비스계정 공유 확인: "
                         f"{exc.__class__.__name__}: {str(exc)[:150]}") from exc
    for w in warns:
        log(f"  [계정 출처] ⚠ {w}")
    log(f"  [계정 출처] 원장 · 동기화 {info['원장 동기화']} · 정산 대상 {len(accts)}계정(셀독원장 {info['셀독원장']} · "
        f"정산전용 {info['정산전용']}) · 오입력 제외 {info['오입력 제외']}"
        + (f" · 두 곳에 있어 셀독원장 값 사용 {info['중복(셀독원장 우선)']}" if info['중복(셀독원장 우선)'] else ""))
    return accts


class LedgerSyncError(Exception):
    """정산 회차 첫 바퀴 전 관리대장→원장 반영·비밀번호 저장 실패(D-366 ②) — 그 바퀴 중단·다음 바퀴 재시도."""


def _ledger_presync() -> None:
    """D-366 ② — 정산 회차 첫 바퀴가 계정을 읽기 직전, 정산이 스스로 관리대장을 1번 읽어 같은 값으로 ① 대장 비밀번호를
    이 PC 암호 저장소에 저장(앱 _apply_pw_candidates 와 같은 값1·값2 — D-012·D-190) ② 원장 반영(앱 원장 반영과 같은
    registry_gsheet.run_sync · 원장 잠금으로 앱과 차례 · 두 번 반영 = 같은 결과). 링크 = 앱과 같은 설정(gsheet/input_url·
    registry/url). 실패 = LedgerSyncError(이유) — 평문 비밀번호는 로그·파일에 안 씀."""
    from coupang_analytics import appconfig, credstore, gsheet_api, input_list as IL, registry_gsheet as RG
    input_url = appconfig.get("gsheet/input_url", "").strip()
    if not input_url:
        raise LedgerSyncError("관리대장 링크(설정 탭 '관리대장(입력)')가 비어 있음 — 대장 변경분을 반영할 수 없음")
    store = credstore.CredStore()
    try:
        ledger = IL.read_ledger_rows(input_url, store=store)
    except Exception as exc:   # 링크·권한·인터넷 — 이유를 그대로 남기고 그 바퀴 중단
        raise LedgerSyncError(f"관리대장 읽기 실패 — {exc.__class__.__name__}: {str(exc)[:150]}") from exc
    _save_ledger_passwords(store, IL.parse_password_candidates(ledger[1]))
    if (appconfig.get("settlement/account_source", "") or "registry").strip() == "file":
        log("  [원장] 정산 계정 출처 = 계정 파일 — 원장 반영 안 함(비밀번호만 저장)")
        return
    registry_url = appconfig.get("registry/url", "").strip()
    if not registry_url:
        raise LedgerSyncError("원장 링크(설정 탭 '원장')가 비어 있음 — 관리대장 → 원장 반영 불가")
    log("  [원장] 정산 회차 시작 전 원장 반영(관리대장 → 원장 · D-366)…")
    try:
        RG.run_sync(gsheet_api.GSheetClient(registry_url, store=store, on_log=log), lambda: ledger, log=log,
                    judge=_rename_judge(store))
    except Exception as exc:   # 잠금 대기 초과·계정 급감 보호·시트 오류 등 — 반영 안 된 원장으로 정산하지 않음
        raise LedgerSyncError(f"관리대장 → 원장 반영 실패 — {exc.__class__.__name__}: {str(exc)[:150]}") from exc


def _save_ledger_passwords(store, cands: dict) -> None:
    """앱 _apply_pw_candidates 와 같은 저장 — 계정마다 값1(credstore set_password) + 줄마다 다른 값2(save_ledger_alternates)."""
    try:
        for aid, cs in cands.items():
            store.set_password(aid, cs[0].password)
        SA.save_ledger_alternates(store, cands)
    except Exception as exc:   # 저장 실패 = 어제 비밀번호로 로그인할 수 있음(틀린 1회) → 그 바퀴 중단
        raise LedgerSyncError(f"관리대장 비밀번호 저장 실패 — {exc.__class__.__name__}") from exc
    log(f"  [비번] 관리대장 비밀번호 {len(cands)}계정 저장(이 PC 암호 저장소 · 회차 시작 전 · D-366)")


def _rename_judge(store):
    """원장 반영의 상품명 변경 자동 판단(D-070) — 앱 원장 반영(ui/registry_ui.rename_judge)과 같은 src 함수·같은 재료
    (글자 규칙 → 매칭 고정 기록 → AI). 정산 exe 엔 ui 모듈이 없어 여기서 같은 함수로 묶음."""
    from coupang_analytics import match_anchor, product_match_ai, registry_judge
    key = store.get_password("__openai__")
    if not key:
        log("  [원장] OpenAI 키 없음 — 상품명 변경은 글자 규칙·상품번호로만 자동 판단(나머지는 다음 실행에서 다시)")
    try:
        anchors = registry_judge.load_anchor_file(match_anchor.anchor_path())
    except (OSError, ValueError) as exc:
        log(f"  [원장] ⚠ 매칭 고정 기록 읽기 실패 — 상품번호 판단 생략 · {exc.__class__.__name__}")
        anchors = {}
    return registry_judge.make_judge(product_match_ai.openai_ask(key) if key else None, anchors, log)


def load_accounts(only: set) -> list:
    """정산 계정 목록 — 출처 = 설정 settlement/account_source: 'registry'(기본·D-103 원장) | 'file'(옛 정산 계정 파일).
    읽을 때마다 예전 이름으로 된 요청 기록·파일·금액 기록을 지금 이름으로 맞춘다(계정ID 기준)."""
    from coupang_analytics import appconfig
    source = (appconfig.get("settlement/account_source", "") or "registry").strip()
    if source not in ("registry", "file"):
        raise SystemExit(f"설정 settlement/account_source='{source}' — registry 또는 file 만")
    accts = _accounts_from_file() if source == "file" else _accounts_from_registry()
    _migrate_names(accts)
    picked = [a for a in accts if not only or a.account_id in only]
    if only and len(picked) != len(only):
        raise SystemExit(f"정산 계정에 없는 계정: {sorted(only - {a.account_id for a in picked})}")
    return picked


def cmd_merge(args) -> int:
    """다른 PC(노트북)에서 옮겨 온 정산 폴더(--src)를 이 PC 기록에 합침. 자동 실행(watch)이 돌면 거부(진행분 덮어쓰기 방지).
    요청 기록=같은 작업은 이 PC 우선·나머지 추가 / 받은 파일=같은 이름 있으면 그대로 둠 / 금액 기록=키로 합침.
    끝나면 계정 파일 기준 계정명 맞춤까지(load_accounts)."""
    from coupang_analytics.registry_lock import RegistryLockError, registry_lock
    src = Path(args.src)
    if not (src / "_요청기록.json").exists():
        raise SystemExit(f"합칠 폴더에 _요청기록.json 이 없음: {src}")
    try:
        with registry_lock(BASE / "_잠금" / "_watch.lock", wait_sec=0, on_log=log):
            accts = load_accounts(set())                    # 이 PC 기록부터 지금 계정명으로
            added, dup, moved, kept = STORE.merge_folder(src, accts)
            LOG.record("(전체)", "합치기", RL.OK, f"{src} → 요청 기록 {added}건 추가·{dup}건 이미 있음 · 파일 {moved}개 옮김·"
                       f"{kept}개 같은 이름 있어 그대로 둠(원본 폴더에 남음)")
            _migrate_names(accts)                           # 옮긴 파일·금액 기록의 예전 계정명 → 지금 계정명
    except RegistryLockError:
        raise SystemExit("정산 자동 실행이 도는 중 — 앱 정산 탭 [정산 중지] 후 다시 실행하세요(진행분 덮어쓰기 방지)") from None
    return 0


def name_of(a) -> str:
    return SA.display_name(a)


_rename_jobs = STORE.rename_jobs


def _migrate_names(accts) -> None:
    STORE.migrate_names(accts, log)


def _profile_in_use(profile: str) -> bool:
    """그 프로필로 떠 있는 Chrome 이 있으면 True(①판매수집 등이 사용 중) — 종료하지 않고 확인만."""
    ps = ("(Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -and "
          "$_.CommandLine.ToLower().Contains($env:SM_PROFILE.ToLower()) } | Measure-Object).Count")
    env = dict(os.environ, SM_PROFILE=str(Path(profile).resolve()))
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=20,
                       env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.stdout.strip() not in ("", "0")


def _profile_busy(profile: str, wait_sec: int = 60, until: datetime | None = None) -> bool:
    """사용 중이면 5초마다 다시 확인. until(자동 수집의 회차 끝)이 있으면 **그때까지 기다렸다가 앱이 그 계정을 끝내면
    이어서 진행**(D-031 — 건너뛰지 않음), 없으면(직접 실행) 최대 wait_sec. 실측 2026-10-06: 직전 실행의 Chrome 이
    닫히는 데 약 1분 걸려 바로 다음 실행이 '사용 중'으로 잘못 건너뛰던 것도 이 대기로 해소."""
    end_mono = time.monotonic() + wait_sec
    last = 0.0
    while _profile_in_use(profile):
        if (datetime.now() >= until) if until is not None else (time.monotonic() >= end_mono):
            return True
        if time.monotonic() - last >= 60:
            log("  (앱이 이 계정 Chrome 을 쓰는 중 — 끝날 때까지 기다렸다가 이어서 진행)")
            last = time.monotonic()
        time.sleep(5)
    return False


def _login(b, a, pws: list, hidden: bool) -> None:
    """로그인 + 판정 코드 기록. 차단은 '차단', 비번 오류·미완료는 SessionSkip(재시도 안 함). pws = 관리대장 값 먼저
    (SA.login_passwords) — 첫 값이 '비밀번호가 다릅니다'일 때만 다음 값 1회(앱 ①과 같은 _login_with_candidates·D-012)."""
    from coupang_analytics.pipeline_sales import LoginBlocked, LoginCredentialError, _login_with_candidates
    name = name_of(a)
    try:
        ok = _login_with_candidates(b, a, pws, log, login=True, semi=not hidden)
    except LoginBlocked as exc:
        LOG.record(name, "로그인", RL.BLOCK, f"로그인 차단 — {exc}")
        raise SessionSkip("로그인 차단(재시도 안 함)") from exc
    except LoginCredentialError as exc:
        LOG.record(name, "로그인", RL.FAIL, f"비밀번호 오류·잠금 의심 — 재시도 안 함 ({exc})")
        raise SessionSkip("비밀번호 오류(재시도 안 함)") from exc
    code, detail = b.classify_login()
    if not ok:
        LOG.record(name, "로그인", RL.BLOCK if code in ("blocked", "akamai") else RL.FAIL, f"{code}: {detail}")
        raise SessionSkip(f"로그인 미완료({code})")
    LOG.record(name, "로그인", RL.OK, f"{code}: {detail}")


@contextmanager
def session(a, hidden: bool, until: datetime | None = None):
    """그 계정 로그인 세션(잠금·사용중 확인[until 까지 대기]·로그인 판정 기록)."""
    from coupang_analytics.browser import WingBrowser
    from coupang_analytics.pipeline_sales import account_profile
    from coupang_analytics.registry_lock import RegistryLockError, registry_lock
    prof = account_profile(a.account_id)
    if _profile_busy(prof, until=until):
        raise SessionSkip("이 계정 Chrome 이 계속 실행 중(①판매수집 등) — 회차 끝/대기 시간 초과")
    pws, src = SA.login_passwords(a)                      # 관리대장(앱 저장) 값 먼저 · 대장에 없으면 원장 값(D-103·D-123)
    if not pws:
        raise SessionSkip("비밀번호 없음(관리대장·원장(또는 정산 계정 파일) 모두)")
    log(f"  [비번] {name_of(a)}: {src}")
    try:
        with registry_lock(BASE / "_잠금" / f"{a.account_id}.lock", wait_sec=5, on_log=log):
            with WingBrowser(profile_dir=prof, offscreen=hidden) as b:
                _login(b, a, pws, hidden)
                yield b
    except RegistryLockError as exc:
        raise SessionSkip("다른 정산 다운로드가 이 계정을 쓰는 중") from exc


def goto(b, url: str, who: str) -> None:
    """정산 화면 열기 + 차단 검사(Access Denied 등). 감지하면 '차단' 기록 후 BlockDetected. 이후 호출은 이 페이지 안에서."""
    b.page.goto(url, wait_until="domcontentloaded", timeout=40000)
    if b._page_blocked():
        LOG.record(who, "차단감지", RL.BLOCK, f"차단 화면 — {b.page.url[:120]}")
        raise BlockDetected(f"차단 화면 감지: {b.page.url[:120]}")
    b.page.wait_for_timeout(2500)                       # 화면 스크립트가 쿠키(XSRF) 준비할 시간


SERVER_BUSY_RETRY = (15, 2)                            # 쿠팡 서버 일시 오류: 15초 쉬고 최대 2번 더


def api(b, who: str, method: str, path: str, body: dict | None = None):
    """WING 주소 호출. 차단 의심(403·429·HTML)이면 '차단' 기록 후 BlockDetected. 서버 일시 오류(502·503·504)는
    잠시 쉬고 다시 시도, 그래도 안 되면 ServerBusy 를 올림(호출부가 '대기'로 기록·차단으로 세지 않음)."""
    wait, retries = SERVER_BUSY_RETRY
    for attempt in range(retries + 1):
        try:
            return API.call(b.page, method, path, body)
        except API.ApiBlocked as exc:
            LOG.record(who, "차단감지", RL.BLOCK, str(exc))
            raise BlockDetected(str(exc)) from exc
        except API.ServerBusy:
            if attempt == retries:
                raise
            log(f"  [서버 일시 오류] {path} — {wait}초 뒤 다시 시도({attempt + 1}/{retries})")
            time.sleep(wait)


# ── 정산 일정 조회 ────────────────────────────────────────────────
_SOURCES = (("윙", API.WING_URL, API.WING_EVENTS, API.wing_events_body, API.wing_events),
            ("로켓그로스", API.RG_URL, API.RG_EVENTS, API.rg_events_body, API.rg_events))


def read_events(b, name: str, start: date, end: date, amounts_from: date | None = None) -> list:
    """지급일 기준 달 단위로 윙·로켓그로스 정산 일정 조회. 조회 구간마다 처리기록을 남긴다(날짜별 정상/비정상 분석).
    amounts_from 이 start 보다 이르면 그때부터 지급 내역(금액)만 더 기록 — 돌려주는 정산 일정(받을 파일 계획)은 start 부터."""
    found: list = []
    for ch, url, path, body, parse in _SOURCES:
        if CHANNELS and ch not in CHANNELS:
            continue
        goto(b, url, name)
        raw: list = []
        for k, (ws, we) in enumerate(API.month_windows(min(start, amounts_from or start), end)):
            if k:
                time.sleep(random.uniform(*LOOKUP_GAP_SEC))
            resp = api(b, name, "POST", path, body(ws, we))
            raw.append((ws, we, resp))
            evs = [e for e in parse(resp, name) if ws <= e.settle_date <= we]   # 로켓그로스 끝 경계 하루 여유분 제외
            _save_amounts(name, ch, resp)
            costs = sum(len(e.reports) for e in evs)
            LOG.record(name, "조회", RL.OK, f"정산 일정 {len(evs)}건" + (f"·비용 리포트 {costs}건" if costs else ""),
                       channel=ch, period=f"{ws}~{we}")
            for n in API.unmapped_costs(resp):
                LOG.record(name, "조회", RL.WAIT, f"받을 리포트 미확인 비용 — {n}", channel=ch)
            for n in API.unsupported_cycles(resp):
                LOG.record(name, "조회", RL.WAIT, f"확인 필요 — 받기 방법 미확인 정산주기 {n} · 그 줄만 건너뜀", channel=ch)
            found += [e for e in evs if e.settle_date >= start]
        ahead = _read_forecast(b, name, ch, path, body, end) or []
        if ch == "로켓그로스":
            found += _rg_extra_events(name, raw, ahead, found, start, end, min(start, amounts_from or start))
    return found


RG_RAW_DIRNAME = STORE.RG_RAW_DIRNAME                   # output/정산/정산현황_원문/{계정}/{날짜}.json.gz (D-164 원인 확인용)
INVENTORY = Path("output") / daily_snapshot.INVENTORY_DIRNAME  # ① 재고현황 원문(계정ID별) — 로켓그로스 업체코드 셋째 근거(D-214 ⓐ)
RG_RAW_DAYS = 70                                        # 원문으로 남길 지난 조회 구간(최근 70일과 겹치는 달) — 예정 줄이 지난 줄이 되는 범위


def _rg_extra_events(name: str, raw: list, ahead: list, events: list, start: date, end: date, since: date) -> list:
    """로켓그로스 빠진 비용 리포트 일정(D-164): 정산 줄 없는 주 물류비 + 지급 내역엔 있는데 조회 일정엔 없는 줄(0원 줄·조사 *2).
    받을 파일 계획(jobs)에 들어가 같은 주·리포트는 한 번만 요청된다. 원인 확인용 응답 원문은 하루 1번 남김."""
    from coupang_analytics import daily_snapshot
    tok = SF._token(name, "계정명")
    reports = [r for _ws, _we, resp in raw for r in resp.get("settlementStatusReports") or []]
    if not daily_snapshot.has_day(BASE, RG_RAW_DIRNAME, tok):
        try:
            cut = end - timedelta(days=RG_RAW_DAYS)
            daily_snapshot.save(BASE, RG_RAW_DIRNAME, tok, {
                "조회": [{"기간": [ws.isoformat(), we.isoformat()], "응답": resp} for ws, we, resp in raw if we >= cut],
                "예정": [{"기간": [ws.isoformat(), we.isoformat()], "응답": resp} for ws, we, resp in ahead]})
        except OSError as exc:                            # 원인 확인용 — 저장 실패해도 정산은 계속(로그로 명시)
            LOG.record(name, "조회", RL.WAIT, f"정산현황 원문 저장 실패(진행) — {exc}", channel="로켓그로스")
    p = AMOUNTS / f"{tok}_로켓그로스.json"
    rows = [r for r in (json.loads(p.read_text(encoding="utf-8")) if p.exists() else []) if r["정산일"] <= end.isoformat()]
    miss = API.missing_week_events(reports, name, since)
    extra = [e for e in miss + API.unlisted_row_events(rows, events, reports, name) if e.settle_date >= start]
    if extra:
        n_miss = sum(e.kind == SJ.MISSING_KIND for e in extra)
        LOG.record(name, "조회", RL.OK, f"빠진 비용 리포트 일정 {len(extra)}건(정산 줄 없는 주 {n_miss}·조회에 없는 지급 줄 "
                   f"{len(extra) - n_miss}) — 받을 파일 계획에 넣음(이미 받은 주는 다시 요청 안 함)", channel="로켓그로스")
    return extra


def _read_forecast(b, name: str, ch: str, path: str, body, end: date) -> list:
    """오늘 뒤 AHEAD_DAYS 까지 정산현황 조회 → 쿠팡이 미리 만든 정산 줄을 예정 기록에만(D-078). 받을 파일 계획엔 안 씀.
    쿠팡이 미래 날짜를 거부하는 등 실패해도 그 계정 정산은 계속(차단 신호만 그대로 올림). 반환 = 받은 [(시작, 끝, 응답)]."""
    got: list = []
    for ws, we in API.month_windows(end + timedelta(days=1), end + timedelta(days=FC.AHEAD_DAYS)):
        time.sleep(random.uniform(*LOOKUP_GAP_SEC))
        try:
            resp = api(b, name, "POST", path, body(ws, we))
        except (API.SiteChangedError, API.ServerBusy) as exc:
            LOG.record(name, "조회", RL.WAIT, f"정산 예정 조회 실패(진행) — {str(exc)[:120]}", channel=ch, period=f"{ws}~{we}")
            continue
        _save_amounts(name, ch, resp)
        got.append((ws, we, resp))
        LOG.record(name, "조회", RL.OK, "정산 예정(쿠팡 미리 계산) 조회", channel=ch, period=f"{ws}~{we}")
    return got


def _save_amounts(name: str, ch: str, resp: dict) -> None:
    """정산일 지난 줄 = 지급 내역 · 오늘 뒤 줄 = 예정 기록(수집일별·D-078)."""
    past, future = FC.split_future(API.amount_rows(resp, ch), date.today())
    STORE.save_amounts(name, ch, past)
    FC.record(STORE.FORECAST, SF._token(name, "계정명"), ch, future, date.today())


def past_until(args) -> bool:
    """멈춤 시각이 지났으면 True. watch=주기 끝 시각(until_at), 직접 실행=--until HH:MM(오늘 그 시각).
    앱 00:10 무인 실행과 같은 계정 프로필이 겹치지 않게."""
    if getattr(args, "until_at", None):
        return datetime.now() >= args.until_at
    if not getattr(args, "until", ""):
        return False
    hh, mm = (int(x) for x in args.until.split(":"))
    return datetime.now() >= datetime.now().replace(hour=hh, minute=mm, second=0, microsecond=0)


def _job_fields(j) -> dict:
    return {"channel": j.channel, "kind": f"{j.kind}·{j.report}", "settle_date": j.settle_date,
            "period": f"{j.period_start}~{j.period_end}"}


# ── 명령 ──────────────────────────────────────────────────────────
def _request_one(b, j, name: str) -> str:
    if j.channel == "윙":
        return API.wing_request_id(api(b, name, "POST", API.WING_REQUEST, API.wing_request_body(j)))
    return API.rg_request_id(api(b, name, "POST", API.RG_REQUEST, API.rg_request_body(j, int(time.time() * 1000))))


def cmd_request(a, b, args, jobs: list) -> None:
    name = name_of(a)
    events = read_events(b, name, args.start, args.end, amounts_from=AMOUNTS_FROM)
    if REUSE_FROM is not None:                            # 셀독전환자(D-187) — 원장 정산 기록에 있는 파일은 요청 상한 전에 복사
        _reuse_main(a, name, events, jobs)
    picked = [j for j in SJ.plan_requests(events, jobs, today=date.today(), now=datetime.now(),
                                          per_account_cap=args.cap)
              if j.account == name and args.start.isoformat() <= j.settle_date <= args.end.isoformat()]   # 이번 기간만
    for j in jobs:
        if j.account == name and j.status == SJ.ST_SKIPPED:
            LOG.record(name, "요청", RL.SKIP, j.note, **_job_fields(j))
    SJ.save_jobs(JOBS, jobs)
    log(f"  요청 대상 {len(picked)}건(상한 {args.cap})" + (" — 미리보기, 요청 안 함" if args.dry_run else ""))
    for k, j in enumerate(picked):
        if args.dry_run:
            LOG.record(name, "요청", RL.SKIP, "미리보기(--dry-run)", **_job_fields(j))
            continue
        if k:
            time.sleep(random.uniform(*GAP_SEC))
        if past_until(args):
            LOG.record(name, "요청", RL.WAIT, f"멈춤 시각 {args.until} 지남 — 남은 요청은 다음 실행에서 이어감",
                       **_job_fields(j))
            break
        try:
            rid = _request_one(b, j, name)
        except API.RequestThrottled as exc:
            LOG.record(name, "요청", RL.WAIT, f"{exc} — 이 계정 요청은 다음 실행에서 이어감", **_job_fields(j))
            break
        except API.SiteChangedError as exc:
            LOG.error(name, "요청", exc, **_job_fields(j))
            raise
        SJ.mark_requested(j, datetime.now(), rid)
        SJ.save_jobs(JOBS, jobs)
        LOG.record(name, "요청", RL.OK, f"다운로드 요청함(요청번호 {rid})", **_job_fields(j))


def _reuse_main(a, name: str, events: list, jobs: list) -> None:
    """D-187 셀독전환자: 받을 파일이 원장 정산 기록(REUSE_FROM)에 이미 있으면 요청하지 않고 복사(같은 계정 두 번 요청 방지).
    같은 계정 판단 = transfer_settle.find_reusable(이름 끝 계정ID + 대표자명·사업자명)."""
    from coupang_analytics import transfer_settle as TS
    for j in SJ.plan_requests(events, jobs, today=date.today(), now=datetime.now(), per_account_cap=10 ** 9):
        if j.account != name or j.kind == SJ.DOC_KIND:
            continue
        fname = SF.settle_file_name(name, date.fromisoformat(j.settle_date), j.channel, j.kind, j.report,
                                    date.fromisoformat(j.period_start), date.fromisoformat(j.period_end))
        cost = j.channel == "로켓그로스" and j.report != "판매수수료"
        src = TS.find_reusable(REUSE_FROM / "비용" if cost else REUSE_FROM, a.account_id, a.names, fname)
        if src is None:
            continue
        dst = (COSTS if cost else FILES) / fname
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        j.status, j.file = SJ.ST_DONE, f"비용/{fname}" if cost else fname
        LOG.saved(name, dst, "원장 정산 기록에서 복사")
        LOG.record(name, "받기", RL.OK, f"원장 정산 기록에 같은 파일 — 요청 안 하고 복사({src.name})", **_job_fields(j))


def _get_bytes(b, url: str, text_ok: bool = False) -> bytes:
    r = b.context.request.get(url, timeout=120000)
    body = r.body()
    is_text = text_ok and "text/csv" in (r.headers.get("content-type") or "")   # 큰 광고 보고서(AD.report_xlsx 가 엑셀로 바꿈)
    if r.status != 200 or (body[:2] != b"PK" and not is_text):                # xlsx = zip
        u = urlsplit(url)
        raise API.SiteChangedError(f"파일 받기 실패: {r.status} {r.headers.get('content-type')} · 주소 {u.netloc}{u.path[:100]}"
                                   f" · {_fail_text(body)}")
    return body


def _fail_text(body: bytes) -> str:
    """받기 실패 응답 → 오류 화면 제목·본문 글자 앞 300자(스크립트·스타일 뺌) — 원인 판정 근거(D-191 · 옛 기록 = 앞 60바이트)."""
    t = body[:200000].decode("utf-8", "replace")
    title = re.search(r"<title[^>]*>(.*?)</title>", t, re.S | re.I)
    text = re.sub(r"<(script|style|title)[^>]*>.*?</\1>", " ", t, flags=re.S | re.I)
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text)).replace("\xa0", " ")).strip()
    return f"제목 '{(title.group(1).strip() if title else '')[:80]}' · 본문 '{text[:300]}'"


def _fetch_one(b, j, row, name: str) -> None:
    try:
        if j.channel == "윙":
            data = _get_bytes(b, row.handle)
        else:
            url = api(b, name, "POST", API.RG_GET, {"requestTime": row.handle, "locale": "ko"}).get("url")
            if not url:
                raise API.SiteChangedError("로켓그로스 받기 응답에 url 없음")
            data = _get_bytes(b, url)
    except API.SiteChangedError as exc:                    # D-191: 목록 줄(상태·생성 시각)도 함께 — 같은 줄 반복 실패 판정용
        raise API.SiteChangedError(f"목록 줄 상태 {row.status} · 생성 {row.requested_at:%m-%d %H:%M} · {exc}") from exc  # 처리기록 200자 안
    if j.kind == SJ.DOC_KIND:                              # 요청형 월자료(부가세 상세 — D-171 N8): 판정·저장·화면 월 합계 대조
        from coupang_analytics import settlement_docs_request as DR
        tok = SF._token(name, "계정명")
        ok, msg = DR.keep(data, j, VERIFY / "월자료" / tok, VERIFY / f"{tok}.json")
        LOG.saved(name, VERIFY / j.file, j.report)
        LOG.record(name, "받기", RL.OK if ok else RL.FAIL, msg, **_job_fields(j))
        return
    fname = SF.settle_file_name(name, date.fromisoformat(j.settle_date), j.channel, j.kind, j.report,
                                date.fromisoformat(j.period_start), date.fromisoformat(j.period_end))
    raw = BASE / "_받는중" / fname
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(data)
    if ORIGINALS is not None:                              # 증빙용 원본(구매자명 포함·받은 그대로) — 아래 처리와 별개
        ORIGINALS.mkdir(parents=True, exist_ok=True)
        (ORIGINALS / fname).write_bytes(data)
        LOG.saved(name, ORIGINALS / fname, "증빙용 원본")
    if j.channel == "로켓그로스" and j.report != "판매수수료":
        _keep_cost(raw, j, name, fname)
        return
    SF.scrub_pii(raw, FILES / fname)                       # 구매자명 지운 사본만 보관
    raw.unlink()
    f = SF.load_settle_file(FILES / fname)                 # 내용 확인(로켓그로스 기간 대조 포함)
    j.status, j.file = SJ.ST_DONE, fname
    LOG.saved(name, FILES / fname, "정산 파일")
    LOG.record(name, "받기", RL.OK, f"{fname} · 줄 {len(f.rows)} · 정산합 {f.settle_total:,} · 검산경고 "
               f"{len(f.warnings)}", **_job_fields(j))


def _keep_cost(raw: Path, j, name: str, fname: str) -> None:
    """비용 리포트: 개인정보 칸 없음 확인 → 시트별 최종비용 읽기(기간 대조) → 비용 폴더로 옮김."""
    sheets = SF.read_sheets(raw)
    SF.assert_no_pii(sheets)
    totals = SF.rg_cost_totals(sheets, date.fromisoformat(j.period_end))
    COSTS.mkdir(parents=True, exist_ok=True)
    daily_snapshot.keep_before_overwrite(COSTS / fname)   # 자동 다시 받기(D-339)로 같은 이름을 덮어쓸 때 옛 값(D-335)
    os.replace(raw, COSTS / fname)
    j.status, j.file = SJ.ST_DONE, f"비용/{fname}"
    LOG.saved(name, COSTS / fname, "비용 리포트")
    LOG.record(name, "받기", RL.OK, f"{fname} · " + " · ".join(f"{k} {v:,}" for k, v in totals.items()),
               **_job_fields(j))
    if j.report == "리뷰 이벤트 비용":                     # 리포트 합 ↔ 그 정산 줄 차감액(D-183) — 다르면 확인 필요(파일은 받음)
        p = AMOUNTS / f"{SF._token(name, '계정명')}_로켓그로스.json"
        gap = SF.review_gap(sum(totals.values()), json.loads(p.read_text(encoding="utf-8")) if p.exists() else [],
                            j.settle_date, j.period_start, j.period_end)
        if gap:
            LOG.record(name, "받기", RL.WAIT, gap, **_job_fields(j))


def _list_rows(b, ch: str, want: list, name: str) -> list:
    if ch == "윙":
        goto(b, API.WING_URL, name)
        return API.wing_list_rows(api(b, name, "GET", API.WING_LIST))
    goto(b, API.RG_URL, name)
    since = min(datetime.fromisoformat(j.requested_at) for j in want) - timedelta(minutes=5)
    return API.rg_list_rows(api(b, name, "POST", API.RG_LIST, API.rg_list_body(since, datetime.now())))


def cmd_download(a, b, args, jobs: list) -> None:
    name = name_of(a)
    mine = [j for j in jobs if j.account == name]
    for ch in ("윙", "로켓그로스"):
        want = [j for j in mine if j.channel == ch and j.status == SJ.ST_REQUESTED]
        if not want or (CHANNELS and ch not in CHANNELS):
            continue
        pairs, notes = SJ.match_downloads(_list_rows(b, ch, want, name), want)
        for n in notes:
            LOG.record(name, "받기", RL.WAIT, n, channel=ch)
        for k, (j, row) in enumerate(pairs):
            if k:
                time.sleep(random.uniform(*LOOKUP_GAP_SEC))
            try:
                _fetch_one(b, j, row, name)
            except BlockDetected:
                raise
            except API.ServerBusy as exc:                 # 서버 일시 오류 = 그 파일만 다음 바퀴에(차단·실패 아님)
                LOG.record(name, "받기", RL.WAIT, f"{exc} — 다음 바퀴에 다시", **_job_fields(j))
            except Exception as exc:                       # 그 파일만 실패 기록 후 다음 파일(무음 아님)
                LOG.error(name, "받기", exc, **_job_fields(j))
            SJ.save_jobs(JOBS, jobs)


def cmd_run(a, b, args, jobs: list) -> None:
    """정기 단계(D-170) — 한 세션에서 요청 → (생성 약 1분) → 받기 → 검증 원자료 → 광고(최근 달부터 2달·D-120).
    그날 정산에 필요한 것만. 판매분석 소급 등 밀린 몫은 전 계정 정기가 끝난 뒤 cmd_backfill."""
    cmd_request(a, b, args, jobs)
    if not args.dry_run:
        time.sleep(90)
        cmd_download(a, b, args, jobs)
        with MEMLOG.around(f"검증 수집 {name_of(a)}", log):        # 검증 json 최대 17MB 통째(D-346 큰 할당 후보 — 줄만)
            collect_verify(a, b, args)
        with MEMLOG.around(f"광고(보고서 TSV→xlsx) {name_of(a)}", log):   # 광고 보고서 변환(큰 할당 후보 — 줄만)
            collect_ads(a, b, args)


def cmd_backfill(a, b, args, jobs: list) -> None:
    """소급 단계(D-170) — 판매분석 1/1~(회차 기준 상한 150일→60일·D-167) + 월자료(D-171). 한 일이 있으면 '소급' 줄을 남겨
    다음 바퀴 판단(_sweep_work_count)에 셈 — 다 받았거나 이번 회차 상한을 다 쓰면 줄 없음 → '완료'로 끝남."""
    with MEMLOG.around(f"판매분석·쿠폰 {name_of(a)}", log):       # 판매분석 일별 통째 읽기(큰 할당 후보 — 줄만)
        days = collect_sales(a, b, args)
    docs = collect_docs(a, b, args, jobs)
    asked = request_docs(a, b, args, jobs)
    if days or docs:
        LOG.record(name_of(a), "소급", RL.OK, f"판매분석 {days}일 · 월자료 {docs}개" + (f" · 월자료 요청 {asked}건" if asked else ""))


def _rg_vendor(a, jobs: list) -> str:
    """로켓그로스 업체코드(없으면 '' = 윙 전용) — 정산현황 원문 → 정산 요청 기록 ref → ① 재고현황 원문 순(D-214 ⓐ ·
    settlement_docs.rg_vendor). 요청 기록은 계정 이름을 폴더와 같은 규칙(_token)으로 맞춰 고름(옛 표기 공백·'_'·'/')."""
    from coupang_analytics import settlement_docs as DOC
    tok = SF._token(name_of(a), "계정명")
    refs = [j.ref for j in jobs if j.channel == "로켓그로스" and j.ref and SF._token(j.account, "계정명") == tok]
    return DOC.rg_vendor(BASE / RG_RAW_DIRNAME / tok, refs, INVENTORY / a.account_id)


def request_docs(a, b, args, jobs: list) -> int:
    """요청형 월자료(부가세 상세 윙·RG — D-171 N8) · 회차 계정당 4건(D-170) · 요청 사이 = 정산 요청 간격.
    받기는 다음 바퀴 정기 단계의 cmd_download(같은 기록·같은 목록). 반환 = 요청 수('요청' 정상 줄 = 다음 바퀴 판단에 셈)."""
    from coupang_analytics import settlement_docs_request as DR
    name = name_of(a)
    since = getattr(args, "cycle_since", "") or f"{date.today()}T00:00:00"
    rg = bool(_rg_vendor(a, jobs))
    picked = DR.plan(jobs, name, date.today(), datetime.now(), since, rg)
    SJ.save_jobs(JOBS, jobs)
    if not picked or past_until(args):
        return 0
    goto(b, API.WING_URL, name)
    return DR.request(picked, lambda m, p, body: api(b, name, m, p, body), save=lambda: SJ.save_jobs(JOBS, jobs),
                      record=lambda j, res, msg: LOG.record(name, "요청", res, msg, **_job_fields(j)),
                      gap=lambda: time.sleep(random.uniform(*GAP_SEC)))


DOC_FAILED: dict = {}      # (회차 시작, 계정 폴더) → 이번 회차에 실패한 '종류 달' — 같은 회차 다음 바퀴엔 다시 안 부름(D-245)


def collect_docs(a, b, args, jobs: list) -> int:
    """월자료(D-171 — 세금계산서 2종·라이브·주문별 매출·RG 재고변동 + RG 반품내역 하루 1번) · 회차 계정당 종류별 3달(D-170).
    조회만. 종류 하나 실패 = 그 종류만 기록하고 계속(차단만 중단). 반환 = 받은 파일 수. 저장 = 검증자료/월자료/{계정}/."""
    from coupang_analytics import settlement_docs as DOC
    name = name_of(a)
    tok = SF._token(name, "계정명")

    def html(method: str, path: str, body):
        try:
            return DOC.call_html(b.page, method, path, body)
        except API.ApiBlocked as exc:
            LOG.record(name, "차단감지", RL.BLOCK, str(exc))
            raise BlockDetected(str(exc)) from exc
    goto(b, API.WING_URL, name)
    since = getattr(args, "cycle_since", "") or f"{date.today()}T00:00:00"
    s = DOC.collect(lambda m, p, body: api(b, name, m, p, body), html, lambda url: _get_bytes(b, url), VERIFY / "월자료" / tok,
                    date.today(), vendor=_rg_vendor(a, jobs), since=since, skip=DOC_FAILED.setdefault((since, tok), set()),
                    gap=lambda: time.sleep(random.uniform(*LOOKUP_GAP_SEC)), page_gap=lambda: time.sleep(random.uniform(1, 2.5)),
                    note=lambda m: LOG.record(name, "월자료", RL.WAIT, m), fatal=(BlockDetected,))
    for f in s["파일"]:
        LOG.saved(name, f, "월자료")
    LOG.remaining(name, "월자료", s["남은 달"], "달")
    if s["받음"] or s["남은 달"]:
        LOG.record(name, "월자료", RL.OK, f"받음 {len(s['받음'])}개 {' · '.join(s['받음'])}" + f" · 남은 달 {s['남은 달']}")
    return len(s["받음"])


def _run_both(accts, args) -> int:
    """전 계정 정기 → (중단·멈춤 시각·dry-run 아니면) 전 계정 소급. 반환 = 정기 단계 종료코드."""
    rc = _run_accounts(accts, cmd_run, args)
    if rc == 0 and not args.dry_run and not past_until(args):
        _run_accounts(accts, cmd_backfill, args)
    return rc


def collect_sales(a, b, args) -> int:
    """판매분석 월·주 합계·일별 소급(2026-01-01부터 — D-161 ③) + 윙 할인쿠폰(D-160) — 정산 계정 전부(정산전용 포함)·조회만.
    ① 판매수집과 같은 저장(output/판매분석_일별·_기간·쿠폰목록_일별)·같은 상한(계정당 하루 60일 — 오늘 ① 이 받은 날 포함)이라
    이미 받은 날·오늘 완료본은 다시 부르지 않는다. 표시(결과 시트)는 4/1부터 그대로(FIRST_DAY). 실패는 그 단계만 기록(비치명).
    일별 소급 상한 = 회차(args.cycle_since — 수동 실행은 오늘 0시) 기준 150일 → 1/1 까지 받으면 60일(D-167·D-170). 반환 = 받은 날 수."""
    from coupang_analytics import collector, wing_coupons
    from coupang_analytics import pipeline_sales as PS
    from coupang_analytics import sales_summary as SS
    name = name_of(a)

    def note(m: str) -> None:                             # 처리기록 + 실행 로그(record 가 로그 줄도 씀)
        LOG.record(name, "판매분석·쿠폰", RL.WAIT if "⚠" in m else RL.OK, m.strip())
    goto(b, API.WING_URL, name)                           # 윙 화면(같은 출처·XSRF) — 앞 단계가 다른 화면에서 끝났어도
    try:
        PS._record_sales_periods(b.page, a.account_id, "output", note, first=SS.COLLECT_FROM)
        since = getattr(args, "cycle_since", "") or f"{date.today()}T00:00:00"
        days = PS._record_sales_backfill(b.page, a.account_id, "output", note, first=SS.COLLECT_FROM, settle_since=since)
        _sales_left(name, a.account_id, days)
        wing_coupons.record_day(b.page, a.account_id, "output", note, gap=PS._PERIOD_GAP_SEC)
        return days
    finally:
        collector.reset_raw()                             # 응답 원문 버퍼(① 분석용)는 정산에선 안 씀 — 계정마다 비움


def _sales_left(name: str, account_id: str, days: int) -> None:
    """판매분석 받은 파일·남은 소급 일수(1/1~어제 중 빠진 날) → [실행 결과 종합](D-168). 그 계정 파일만 읽음."""
    from coupang_analytics import sales_history as SH
    from coupang_analytics import sales_summary as SS
    path = Path("output") / SH.DIRNAME / account_id      # 계정 × 달 파일 폴더(D-243 ③ 경로 변경만)
    try:
        have = SH.load_account("output", account_id)
    except (OSError, ValueError) as exc:                 # 남은 수 계산만 못 함 — 그 계정 나머지 소급은 계속(기록으로 명시)
        LOG.record(name, "판매분석·쿠폰", RL.WAIT, f"남은 소급 계산 실패 — 확인 필요 ({exc.__class__.__name__})")
        return
    if days:
        LOG.saved(name, path, f"판매분석 일별 {days}일 추가")
    LOG.remaining(name, "판매분석", len(SS.plan_backfill(have, date.today() - timedelta(days=1), first=SS.COLLECT_FROM,
                                                       limit=10 ** 6)), "일")


def _backlog_left(accts, args) -> None:
    """바퀴 끝 남은 소급을 **전 계정**의 저장 자료로 다시 셈 — 그 바퀴 소급 단계를 못 돈 계정(로그인 실패·중단된 바퀴·새 프로세스)도
    판매분석·월자료·광고 남은 양이 [실행 결과 종합]에 잡힘(T-46 ⑤ · output (37) 보고 B ⑤ — 적게 세어 '다 받았다' 오판 방지).
    받기 없음(파일만 읽음) · 판정 = 각 단계와 같은 함수(_sales_left · DOC/AD.left_months)."""
    from coupang_analytics import settlement_ads as AD
    from coupang_analytics import settlement_docs as DOC
    jobs = SJ.load_jobs(JOBS)
    today = date.today()
    for a in accts:
        name = name_of(a)
        tok = SF._token(name, "계정명")
        _sales_left(name, a.account_id, 0)
        try:
            LOG.remaining(name, "월자료", DOC.left_months(VERIFY / "월자료" / tok, today, bool(_rg_vendor(a, jobs))), "달")
            LOG.remaining(name, "광고", AD.left_months(VERIFY / "광고", tok, min(args.start, AD.FROM), today), "달")
        except (OSError, ValueError) as exc:   # 받은 기록 파일 깨짐 등 — 남은 수만 못 셈(기록으로 명시 · _sales_left 와 같음)
            LOG.record(name, "남은 소급", RL.WAIT, f"남은 소급 계산 실패 — 확인 필요 ({exc.__class__.__name__})")


def collect_verify(a, b, args) -> None:
    """검증 원자료(조회만)를 계정별로 하루 한 번 저장 — settlement_verify_collect. 오늘 이미 모았으면 건너뜀."""
    from coupang_analytics import settlement_verify_collect as VC
    name = name_of(a)
    path = VERIFY / f"{SF._token(name, '계정명')}.json"
    today = date.today()
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if old.get("수집일") == today.isoformat():
        return
    kept = old.get("returns") or {}                        # 반품 조회 결과는 누적(이미 찾은 주문은 다시 안 부름 — D-116)
    orders = VC.returns_to_ask(VC.orphan_ship_orders(_wing_files(name)), kept)
    data = VC.collect(lambda m, p, body: api(b, name, m, p, body), lambda url: goto(b, url, name), args.start, today,
                      note=lambda m: LOG.record(name, "검증", RL.WAIT, m),
                      gap=lambda: time.sleep(random.uniform(*LOOKUP_GAP_SEC)), orders=orders, fatal=(BlockDetected,))
    data = VC.keep_previous(data, old)                     # 조회 실패한 항목·달 = 지난 값 유지(D-161)
    data["returns"] = {**kept, **(data.get("returns") or {})}
    path.parent.mkdir(parents=True, exist_ok=True)
    daily_snapshot.keep_before_overwrite(path, today)      # 전날 값 수집일별 보관(D-335 · 우대수수료 '이체 대기' 등)
    STORE.write_json_atomic(path, data)
    LOG.saved(name, path, "검증 원자료")
    LOG.record(name, "검증", RL.OK, f"검증 자료 저장 — 월렛 {len(data.get('wallet') or [])}건·반품 조회 {len(orders)}주문·"
               f"조회 실패 {len(data['조회 실패'])}건" + (f"(지난 값 유지 {len(data['지난 값'])}건)" if data["지난 값"] else ""))


def collect_ads(a, b, args) -> None:
    """광고비 원천 월별(D-116 ③④) + 끝나지 않은 달 일별(매일 · T-78 S2) — 처음 부를 때 광고센터를 연다. 실패는 기록하고 정산은 계속(차단만 중단)."""
    from coupang_analytics import settlement_ads as AD
    from coupang_analytics import settlement_evidence_web as EW
    name, q = name_of(a), None

    def call(method: str, path: str, body):
        nonlocal q
        if q is None:
            q = EW.open_adcenter(sys.modules[__name__], b, name)
        return API.call(q, method, path, body)
    try:
        s = AD.collect(call, lambda url: _get_bytes(b, url), VERIFY / "광고", SF._token(name, "계정명"), min(args.start, AD.FROM),
                       date.today(),
                       gap=lambda: time.sleep(random.uniform(*LOOKUP_GAP_SEC)), get_report=lambda url: _get_bytes(b, url, text_ok=True),
                       fatal=(BlockDetected,))
        for f in s.get("파일", ()):
            LOG.saved(name, f, "광고")
        LOG.remaining(name, "광고", s["남은 달"], "달")
        for why in s.get("실패", ()):                              # 밀크런·광고센터 따로 실패(한쪽이 다른 쪽을 막지 않음 · D-245)
            LOG.record(name, "광고비", RL.FAIL, why)
        msg = [f"{k} {','.join(v)}" for k, v in s.items() if isinstance(v, list) and v and k not in ("받을 것", "파일", "실패")]
        if msg or s["남은 달"]:
            LOG.record(name, "광고비", RL.OK, " · ".join(msg + ([f"남은 달 {s['남은 달']}(다음 실행에)"] if s["남은 달"] else [])))
    except BlockDetected:
        raise
    except Exception as exc:                              # 광고비 원천은 정산 금액과 별개 — 그 단계만 실패 기록
        LOG.error(name, "광고비", exc)
    finally:
        if q is not None:
            q.close()


def source_checks(web: bool = True) -> None:
    """정산 자료를 다 받은 뒤 1번 — ① 받기 의심(T-82 · 파일끼리 대조 · 다시받을목록.csv · 다음 실행 자동 다시 받기 표시 D-339) ② 원문 대조(T-78 S1 M-E · 접속 없음)
    ③ 공개 웹(S3 M-D · 쿠키·프록시 없는 일반 연결 · 주기 된 페이지만). 단계마다 따로 실패 기록(정산 금액과 별개)."""
    from coupang_analytics import settlement_fetch_check as FCK
    from coupang_analytics import settlement_refetch as RF
    from coupang_analytics import settlement_sources as SRC
    today, out = date.today(), SRC.folder(BASE)
    try:
        rows, later = FCK.scan(BASE)
        n = RF.plan(BASE, rows, today)                    # 다시받을목록 → 다음 실행 평소 받기가 다시 받게 표시(D-339)
        LOG.record(RL.ALL, "자동 다시 받기", RL.WAIT if n["같은 결과"] or n["길 없음"] else RL.OK, RF.summary(n))
        _all, again = FCK.write(out, rows, today)
        LOG.record(RL.ALL, "받기 의심", RL.WAIT if any(r["다시 받기"] != FCK.NO for r in rows) else RL.OK,
                   f"{FCK.summary(rows)}" + (f" · 아직 안 읽은 엑셀 {later}개(다음 실행에)" if later else "") + f" → {again}")
    except Exception as exc:                              # 그 단계만 실패 기록(무음 아님)
        LOG.error(RL.ALL, "받기 의심", exc)
    try:
        r = SRC.compare_originals(BASE, FILES, today)
        LOG.record(RL.ALL, "자료 출처", RL.OK, f"원문 대조 읽음 {r['읽음']} · 남음 {r['남음']} · 변경 {r['이력']} · "
                   f"기준 {r['기준'] or '만드는 중'} → {out / '변경이력.csv'}")
        for why in r["오류"]:                              # 칸 바뀐 원문 = 그 파일만 실패(다음 실행에 다시)
            LOG.record(RL.ALL, "자료 출처", RL.FAIL, why[:200])
    except Exception as exc:
        LOG.error(RL.ALL, "자료 출처", exc)
    for sid in (SRC.due_public(BASE, today) if web else ()):
        try:
            hist = SRC.check_public(BASE, sid, today)
            LOG.record(RL.ALL, "자료 출처", RL.WAIT if hist else RL.OK, f"{sid} " + ("글자 바뀜 — 변경이력.csv" if hist else "같음"))
        except Exception as exc:
            LOG.error(RL.ALL, "자료 출처", exc)


def _wing_files(name: str) -> list:
    """이 계정의 윙 정산 파일(읽을 수 없는 파일은 건너뜀 — 받기 단계가 이미 오류로 기록)."""
    out = []
    for p in sorted(FILES.glob(f"{SF._token(name, '계정명')}_*_윙_*.xlsx")):
        try:
            out.append(SF.load_settle_file(p))
        except Exception:  # noqa: BLE001
            continue
    return out


def cmd_view(a, b, args, jobs: list) -> None:
    """화면 보기 + 화면 응답 기록 첫 시험(T-122 · D-340 · D-296) — `--source SV-…` 하나 · 소유자 로그인 한 계정 1회 · 자동 실행에 안 넣음.
    조회 전용 버튼만 · 페이지 안 스크립트 없음 · 칸 이름만 저장(값 없음) — settlement_screen_view."""
    from coupang_analytics import settlement_screen_view as SV
    name = name_of(a)
    spec = SV.SPECS.get(args.source)
    if spec is None:
        LOG.record(name, "화면 응답", RL.FAIL, f"모르는 출처 {args.source!r} — {', '.join(SV.SPECS)}")
        return
    try:
        rec = SV.capture(b.page, spec)
    except (SV.NeedLive, SV.NotViewOnly) as exc:
        LOG.record(name, "화면 응답", RL.WAIT, f"{args.source} 확인 필요 — {exc}")
        return
    p = SV.save(BASE, args.source, a.account_id, rec)
    LOG.saved(name, p, "화면 응답 칸 목록")
    LOG.record(name, "화면 응답", RL.OK, f"{args.source} 응답 {len(rec['응답'])}개 칸 목록 저장")


def cmd_probe(a, b, args, jobs: list) -> None:
    """읽기만 확인 — 최근 30일 정산 일정·다운로드 목록 모양. 요청·받기는 하지 않음."""
    name = name_of(a)
    end = date.today()
    for ch, url, path, body, parse in _SOURCES:
        try:
            goto(b, url, name)
            evs = parse(api(b, name, "POST", path, body(end - timedelta(days=30), end)), name)
            rows = _list_rows(b, ch, [SJ.Job(name, ch, "", "", "", "", "", requested_at=f"{end}T00:00:00")], name)
            LOG.record(name, "probe", RL.OK, f"정산 일정 {len(evs)}건 · 다운로드 목록 {len(rows)}줄", channel=ch)
        except API.SiteChangedError as exc:
            LOG.error(name, "probe", exc)


EVIDENCE_JOBS = BASE / "증빙" / "_요청기록.json"      # 증빙 전용 요청 기록 — 앱 기록에 '받음'인 파일도 원본을 다시 받게
EVIDENCE_DIR = EVIDENCE_JOBS.parent                   # 자동 증빙 상위 폴더 = 배치(정산증빙_전체받기.bat --out output\정산\증빙)와 같은 곳


def _evidence_step(name: str, label: str, fn) -> dict:
    """증빙 한 단계 — 차단은 그 계정 중단(올림), 그 밖의 실패는 기록하고 다음 단계(무음 아님)."""
    from coupang_analytics import settlement_evidence as EV
    try:
        res = fn()
    except BlockDetected:
        raise
    except Exception as exc:
        LOG.error(name, f"증빙 {label}", exc)
        res = {"결과": EV.FAIL, "내용": f"{exc.__class__.__name__}: {str(exc)[:200]}", "파일": 0}
    LOG.record(name, f"증빙 {label}", RL.OK if res["결과"] != EV.FAIL else RL.FAIL, f"{res['결과']} — {res['내용']}")
    return res


def cmd_evidence(a, b, args, jobs: list) -> dict:
    """계정 하나의 증빙 원본 전체(D-067): 정산 원본 → 정산 줄 없는 주 비용 → 판매분석 월별 → 지급 증빙 메뉴 → 목록·결과.
    반환 = 단계 결과(멈춤 시각으로 시작 안 한 단계 = '멈춤' 표시 — 자동 증빙 연속 실패 셈에서 뺌 D-365 ⑤)."""
    global ORIGINALS
    from coupang_analytics import settlement_evidence as EV
    from coupang_analytics import settlement_evidence_web as EW
    name, mod = name_of(a), sys.modules[__name__]
    folder = EV.account_folder(Path(args.out), name)
    ORIGINALS = folder / EV.ORIG
    steps: dict = {}
    prev = {} if args.redo else EV.previous_steps(folder)   # 지난 실행에서 정상/없음인 단계는 건너뜀(이어받기)

    def settle() -> dict:
        cmd_run(a, b, args, jobs)
        if any(j.account == name and j.status == SJ.ST_REQUESTED for j in jobs):   # 생성이 늦은 파일 — 2분 뒤 한 번 더
            time.sleep(120)
            cmd_download(a, b, args, jobs)
        left = sum(1 for j in jobs if j.account == name and j.status == SJ.ST_REQUESTED)
        n = len(list(ORIGINALS.glob("*.xlsx"))) if ORIGINALS.exists() else 0
        return {"결과": EV.FAIL if left else EV.OK, "내용": f"원본 {n}개" + (f" · 아직 생성 안 됨 {left}건(다시 실행)" if left else ""), "파일": n}
    menu, end = folder / EV.MENU, args.end
    plan = [("정산 원본", settle),
            ("정산 줄 없는 주 비용", lambda: EW.missing_week_costs(mod, b, name, args.start, end, folder / EV.ORIG)),
            ("우대수수료 환급 요청", lambda: EW.refund_request(mod, b, name, args.start, end)),
            ("판매분석 월별", lambda: EW.sales_originals(mod, b, args.start, end, folder / EV.SALES)),
            ("윙 지급 명세", lambda: EW.wing_statements(mod, b, name, args.start, end, menu)),
            ("로켓그로스 월렛", lambda: EW.wallet(mod, b, name, menu)),
            ("로켓그로스 광고비·밀크런", lambda: EW.rg_ad_milkrun(mod, b, name, args.start, end, menu)),
            ("광고센터 월별 광고비", lambda: EW.adcenter_monthly(mod, b, name, args.start, end, menu)),
            ("우대수수료 환급 받기", lambda: EW.refund_fetch(mod, b, name, steps.get("우대수수료 환급 요청", {}), menu))]
    for label, fn in plan:
        if past_until(args):
            steps[label] = {"결과": EV.FAIL, "내용": f"멈춤 시각 {args.until} — 다음 실행에서", "파일": 0, "멈춤": True}
            continue
        if label in prev and not (label == "우대수수료 환급 요청" and prev.get("우대수수료 환급 받기", {}).get("결과") == EV.FAIL):
            steps[label] = {**prev[label], "내용": "지난 실행 결과 그대로 — " + str(prev[label].get("내용", ""))}
            continue
        steps[label] = _evidence_step(name, label, fn)
    if steps["정산 원본"]["결과"] == EV.FAIL and not past_until(args):   # 윙 파일은 생성이 늦음(실측 5분+) — 메뉴 뒤 마저 받기
        def rest() -> dict:
            cmd_download(a, b, args, jobs)
            left = sum(1 for j in jobs if j.account == name and j.status == SJ.ST_REQUESTED)
            n = len(list(ORIGINALS.glob("*.xlsx"))) if ORIGINALS.exists() else 0
            return {"결과": EV.FAIL if left else EV.OK, "내용": f"원본 {n}개" + (f" · 아직 생성 안 됨 {left}건(다시 실행)" if left else ""), "파일": n}
        steps["정산 원본"] = _evidence_step(name, "정산 원본(마저 받기)", rest)
    done = EV.write_results(folder, steps)
    LOG.record(name, "증빙", RL.OK if done else RL.FAIL, f"{'완료' if done else '미완(다시 실행하면 이어서)'} · {folder}")
    return steps


def _evidence_auto(a, b, args, jobs: list) -> None:
    """자동 증빙 한 계정(D-363·D-365) — 정산 받기와 같은 방식의 로그인으로 cmd_evidence(배치와 같은 단계·같은 폴더·검증·광고 포함).
    증빙 요청 기록·원본 폴더·기간은 이 계정 동안만 바꾸고 되돌림(예외여도 — 다음 계정 정산 받기에 섞이지 않게) · jobs(정산 기록)는 안 씀."""
    global JOBS, ORIGINALS
    from coupang_analytics import settlement_evidence as EV
    name = name_of(a)
    folder = EV.account_folder(EVIDENCE_DIR, name)
    due, start, redo = EV.renewal(folder, datetime.now(), args.start)
    if not due:
        return
    keep = (JOBS, ORIGINALS, args.out, args.start, args.redo)
    EVIDENCE_JOBS.parent.mkdir(parents=True, exist_ok=True)
    JOBS, args.out, args.start, args.redo = EVIDENCE_JOBS, str(EVIDENCE_DIR), start, redo
    try:
        with MEMLOG.around(f"증빙 {name}", log):          # 검증·광고 포함이라 큰 할당 후보(D-346 · D-365 ②)
            steps = cmd_evidence(a, b, args, SJ.load_jobs(EVIDENCE_JOBS))
    finally:
        JOBS, ORIGINALS, args.out, args.start, args.redo = keep
    for label in EV.fail_streak(folder, steps, args.cycle_since):
        LOG.record(name, f"증빙 {label}", RL.FAIL,
                   f"확인 필요 — 같은 단계 {EV.CHECK_AFTER}회차 연속 실패(D-365) · 처리기록·오류 로그 확인 · 다음 회차에도 다시 시도")


def _evidence_targets(accts, args) -> list:
    """증빙 대상 = 아직 _수집완료.json 이 없는 계정(--redo 면 전부)."""
    from coupang_analytics import settlement_evidence as EV
    if args.redo:
        return accts
    left = [a for a in accts if not (EV.account_folder(Path(args.out), name_of(a)) / EV.DONE).exists()]
    log(f"증빙 대상 {len(left)}계정(완료 {len(accts) - len(left)}계정 건너뜀) → {args.out}")
    return left


def load_holidays(amounts: list):
    return STORE.load_holidays(amounts, log)


def cmd_stats() -> Path:
    from coupang_analytics import settlement_stats as ST
    files = [SF.load_settle_file(p) for p in sorted(FILES.glob("*.xlsx"))]
    amounts = []
    for p in sorted(AMOUNTS.glob("*.json")):
        acct, ch = p.stem.rsplit("_", 1)
        amounts += [{"계정": acct, "채널": ch, **r} for r in json.loads(p.read_text(encoding="utf-8"))]
    costs, lines = [], []
    for p in sorted(COSTS.glob("*.xlsx")):
        m = SF.parse_file_name(p.name)
        sheets = SF.read_sheets(p)
        for sheet, v in SF.rg_cost_totals(sheets, m["period_end"]).items():
            costs.append((m["account"], m["settle_date"], m["period_start"], m["period_end"], m["report"], sheet, v))
        lines += SF.rg_cost_lines(sheets, m["account"], m["period_end"])
    from coupang_analytics import settlement_verify as SV
    vdatas = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(VERIFY.glob("*.json"))}
    res = ST.aggregate(files, lines)
    verify = SV.build_all(files, amounts, vdatas, ST._order_rows, holidays=load_holidays(amounts))
    acc = FC.accuracy(FC.load(STORE.FORECAST), amounts, date.today())
    out = ST.write_stats(BASE / f"정산집계_{datetime.now():%y%m%d_%H%M%S}.xlsx", res, files=files, amounts=amounts,
                         costs=costs, verify=verify, inflows=SV.inflows_all(amounts, vdatas, today=date.today()),
                         forecast=acc)
    LOG.saved(RL.ALL, out, "정산 집계")
    moved = STORE.rotate_stats(BASE)                      # 최신 3개만 남기고 보관/YYYY-MM 으로 이동(D-243 ② · 삭제 없음)
    if moved:
        log(f"  [정산집계 정리] 옛 정산집계 {moved}개 → {BASE / '보관'}/YYYY-MM (최신 {STORE.STATS_KEEP}개만 남김)")
    log(f"집계 정산 파일 {len(files)}개·비용 리포트 {len(costs)}시트·쿠팡 지급 내역 {len(amounts)}줄 → {out} "
        f"(경고 {len(res.warnings)}건)")
    return out


STATS_CHILD_TIMEOUT_SEC = 3 * 3600    # 이 노트북 약 16분(보고 C 3-2) — 넘으면 자식을 끝내고 그 바퀴 '실패' 기록


def _stats_in_child() -> None:
    """바퀴 끝 정산 집계를 **별도 짧은 프로세스**(같은 프로그램 `stats --run-id … --result …`)로 돌린다(T-113 (나)).
    한 번에 약 1.37GB 를 쓰고 끝나도 약 0.9GB 를 python 이 OS 에 돌려주지 않아, 13시간 도는 watch 프로세스가 그 몫을
    들고 다음 바퀴를 돌았다(보고 C 3-2·3-3) — 자식이 끝나면 OS 가 전부 회수. 같은 실행ID 로그·오류 로그에 이어 쓰고,
    결과(집계 파일 경로·자식 최고 커밋)는 result JSON. 실패 = 예외(호출부가 그 바퀴 '실패'로 기록 · 숨기지 않음)."""
    from coupang_analytics import app_process as AP
    result = LOG.dir / f"_집계결과_{LOG.run_id}.json"
    result.unlink(missing_ok=True)
    cmd, cwd = AP.settle_stats_cmd(LOG.run_id, result)
    rc = subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        timeout=STATS_CHILD_TIMEOUT_SEC, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode
    data = json.loads(result.read_text(encoding="utf-8")) if result.exists() else {}
    result.unlink(missing_ok=True)
    MEMLOG.merge(data.get("메모리") or {}, "집계 프로세스")     # 자식의 [메모리] 최고·⚠ 를 회차 종합에(실패여도)
    if rc != 0 or not data.get("out"):
        raise RuntimeError(f"정산 집계(별도 프로세스) 실패 — 종료코드 {rc} · {data.get('오류') or '결과 파일 없음'} "
                           f"(추적 = {LOG.errors.name})")
    LOG.saved(RL.ALL, data["out"], "정산 집계")
    _mem("집계 뒤", note=f"정산 집계 = 별도 프로세스(최고 커밋 {data.get('최고커밋MB')}MB · 끝나면 OS 가 회수)")


def _commit_text() -> str:
    from coupang_analytics import settlement_memory as MEM
    try:
        now, peak = MEM.commit_mb()
    except OSError as exc:                   # 숫자만 못 읽음 — 사유를 그 자리에 적음
        return f"확인 실패({exc.__class__.__name__})"
    return f"{now}MB(최고 {peak}MB)"


def _cmd_stats_main(args) -> int:
    """`stats` 명령 — 사람이 부르면 그대로. `--result`(watch 바퀴 끝 자식 · T-113)면 부모 실행 기록에 이어 쓰고 상태 파일은
    건드리지 않으며(부모 몫), 실패(MemoryError 포함)는 오류 로그에 남기고 종료코드 1 — 창 없는 exe 에서 처리 안 된 예외 창이
    떠 부모가 시간 초과까지 기다리지 않게."""
    if not args.result:
        cmd_stats()
        LOG.heartbeat("완료", "명령 stats")
        return 0
    from coupang_analytics import settlement_memory as MEM
    res = Path(args.result)
    MEMLOG.role = "집계 프로세스"
    _mem("집계 시작")
    try:
        out = cmd_stats()
    except Exception as exc:                          # MemoryError 도 여기(Exception 하위) — 기록하고 부모가 '실패'로 받음
        _release_reserve()
        LOG.error(RL.ALL, "정산 집계", exc)
        _mem("집계 중단")
        res.write_text(json.dumps({"오류": f"{exc.__class__.__name__}: {exc}", "메모리": MEMLOG.state()}, ensure_ascii=False),
                       encoding="utf-8")
        return 1
    _mem("집계 끝")
    res.write_text(json.dumps({"out": str(Path(out).resolve()), "최고커밋MB": MEM.commit_mb()[1], "메모리": MEMLOG.state()},
                              ensure_ascii=False), encoding="utf-8")
    return 0


_PHASE = {"cmd_run": "정기", "cmd_backfill": "소급", "_evidence_auto": "증빙"}   # [메모리] 계정마다 줄의 단계 이름


def _run_accounts(accts, run, args) -> int:
    jobs = SJ.load_jobs(JOBS)
    bad = 0
    for a in accts:
        name = name_of(a)
        if past_until(args):
            LOG.record("(전체)", "중단", RL.WAIT, f"멈춤 시각 {args.until} 지남 — 남은 계정은 다음 실행에서 이어감")
            return 0
        LOG.heartbeat("작동중", f"실행 중: {name}")   # 상태 화면에 '어느 계정 실행 중' 표시(정산일은 로그 줄에)
        log(f"== {name} {args.command} ==")
        try:
            with session(a, args.hidden, getattr(args, "until_at", None)) as b:
                run(a, b, args, jobs)
            bad = 0
        except SessionSkip as exc:
            LOG.record(name, "계정", RL.SKIP, str(exc))
        except BlockDetected as exc:
            bad += 1
            LOG.error(name, "계정", exc, RL.BLOCK)
        except API.ServerBusy as exc:                     # 쿠팡 서버 일시 오류 = 차단 아님·연속 실패로 안 셈·다음 바퀴
            LOG.record(name, "계정", RL.WAIT, f"{exc} — 재시도해도 안 됨, 다음 바퀴에 다시")
        except Exception as exc:
            if _is_browser_closed(exc):   # 브라우저 닫힘(예: 00:10 앱 시작 reap)=일시적 → '차단'·연속실패로 안 셈·다음 바퀴 재시도
                LOG.record(name, "계정", RL.WAIT,
                           f"브라우저가 닫힘(일시적·차단 아님) — 다음 바퀴에 재시도 ({exc.__class__.__name__})")
            else:                                          # 그 계정만 중단(무음 아님·전체 추적은 오류 로그)
                bad += 1
                LOG.error(name, "계정", exc)
        _mem(f"{_PHASE.get(run.__name__, run.__name__)} {name} 끝")
        if bad >= 2:
            LOG.record("(전체)", "중단", RL.BLOCK, "연속 2계정 실패/차단 — 전체 중단(화면 변경·차단 의심, probe 로 확인)")
            return 1
    return 0


WATCH_POLL_SEC = 300             # ①판매수집 진행 중 정지·파일 생성 대기 확인 간격
WATCH_CATCHUP_REST_SEC = 60      # 소급(받을 게 남음) 중 한 바퀴와 다음 바퀴 사이 짧은 쉼
DONE_FILE = BASE / "로그" / "_완료.json"   # 같은 ①완료 기준 '완료' 기록(중복 실행 방지·D-010)
CYCLE = RL.Totals()                        # watch 한 회차의 바퀴 합계 — 회차 끝 [실행 결과 종합](D-168)
PASS_ACCOUNTS: list = []                   # 마지막 바퀴의 정산 계정 — 자동 증빙 대상 고르기(원장을 다시 읽지 않음 · D-365)


def _sweep_work_count(lg) -> int:
    """이번 한 바퀴에서 실제로 한 일(새 요청·받은 파일·소급) 수."""
    return sum(1 for r in lg.rows if r["단계"] in ("요청", "받기", "소급") and r["결과"] == RL.OK)


def _wait_accounts(lg) -> int:
    """이번 바퀴에 '대기'(서버 일시 오류·브라우저 닫힘)로 넘긴 계정 수 — 아직 다 받았다고 볼 수 없음."""
    return len({r["계정"] for r in lg.rows if r["단계"] == "계정" and r["결과"] == RL.WAIT})


def _open_jobs() -> tuple[list, set]:
    """(요청예정·요청됨 작업, 정지 계정ID — 앱 상태 파일 `output/_계정정지.json` D-199 · 읽기만)."""
    from coupang_analytics import account_suspend
    return [j for j in SJ.load_jobs(JOBS) if j.status in (SJ.ST_PLANNED, SJ.ST_REQUESTED)], account_suspend.suspended_ids()


def _is_suspended(account: str, ids: set) -> bool:
    return any(account.endswith("-" + i) for i in ids)          # 계정명 = '대표자-사업자-계정ID'(display_name)


def _pending_jobs() -> int:
    """요청예정·요청됨(쿠팡 파일 생성 대기) 작업 수 — 정지 계정 작업은 빼고 셈(받기는 D-215 대로 계속 · D-247 ·
    실측 output (37) hide4u 요청됨 9건이 받기 500 반복으로 회차 '완료'를 막음)."""
    jobs, ids = _open_jobs()
    return sum(1 for j in jobs if not _is_suspended(j.account, ids))


def _suspended_pending() -> dict[str, int]:
    """정지 계정의 요청예정·요청됨 작업 수 {계정: 건수} — [실행 결과 종합] '정지 계정 대기 — 확인 필요'(D-247)."""
    jobs, ids = _open_jobs()
    out: dict[str, int] = {}
    for j in jobs:
        if _is_suspended(j.account, ids):
            out[j.account] = out.get(j.account, 0) + 1
    return out


def _watch_failures() -> dict[str, str]:
    """완료 문구·상태의 '확인 필요' 계정 = 이번 바퀴 실패로 끝난 계정 + 정지 계정 받기 대기(D-247 — 완료·실패 확인)."""
    return {**LOG.unresolved_failures(), **{a: "정지 계정 받기 대기" for a in _suspended_pending()}}


def _one_pass(args) -> tuple[bool, int]:
    """한 바퀴(전 계정) → (중단됐나, 새로 한 일 수). 예기치 못한 예외는 기록하고 '한 일 0'으로."""
    global LOG
    LOG = RL.RunLog(BASE)
    args.end = date.today()
    log(f"실행 {LOG.run_id} · 자동 · 정산 수집 · 기간 {args.start}~{args.end}")
    LOG.heartbeat("작동중", f"정산 수집 · 기간 {args.start}~{args.end}")
    _mem("바퀴 시작")
    try:
        accts = load_accounts(set())
    except SystemExit as exc:                # 계정 구성 실패(원장 오래됨·링크 오류 등) = 이 회차 정산 중단 — 상태 카드에 이유
        reason = f"❌ {exc}"
        log(f"[자동] {reason}")
        LOG.heartbeat("종료", reason)
        raise
    LOG.accounts = [name_of(a) for a in accts]
    PASS_ACCOUNTS[:] = accts
    try:
        rc = _run_both(accts, args)
        work = _sweep_work_count(LOG)
        _mem("집계 전")
        _stats_in_child()                    # 바퀴 끝 집계 = 별도 짧은 프로세스(T-113 (나) — 1.37GB·남는 0.9GB 를 이 프로세스에 안 남김)
    except Exception as exc:                 # 그 바퀴만 실패 기록(다음 판단은 진전 없음으로)
        LOG.error("(전체)", "자동실행", exc)
        return False, 0
    finally:
        try:
            _backlog_left(accts, args)       # 남은 소급 = 전 계정 저장 자료로 다시 셈(T-46 ⑤)
        except MemoryError as exc:           # T-113 (다) 11-18 06:53 — finally 에서 새면 처리 안 된 예외 창·자기 종료 실패
            _note_memory_floor("남은 소급 계산", exc)
        CYCLE.add(LOG)                       # 회차 [실행 결과 종합] 재료(D-168)
    LOG.summary(pending=_pending_jobs(), suspended=_suspended_pending())
    return rc == 1, work


_RESERVE: list = [bytearray(16 << 20)]   # 메모리 바닥 때 풀어 기록할 여유(16MB · T-113) — 한 번만 씀


def _release_reserve() -> None:
    _RESERVE.clear()


def _note_memory_floor(step: str, exc: BaseException) -> None:
    """메모리 바닥(MemoryError)을 숨기지 않고 처리기록·_현재상태.txt 에 남긴다(T-113 (다) · fallback 아님 — 그 단계는 '실패')."""
    _release_reserve()
    reason = f"❌ 메모리 부족(MemoryError) — {step} 못 함 · 정산 프로세스 커밋 {_commit_text()} · PC 전체 메모리 바닥 의심(T-113)"
    LOG.record(RL.ALL, step, RL.FAIL, f"{exc.__class__.__name__}: {exc} — {reason}")
    LOG.heartbeat("작동중", reason)


def _memory_floor_exit(exc: BaseException) -> int:
    """처리 안 된 MemoryError — 창 없는 exe 의 '처리 안 된 예외' 창이 떠 프로세스가 남지 않게(11-18 07:00 이후 창 남음)
    처리기록·_현재상태.txt 에 남기고 종료코드 3. 기록조차 못 쓰면(바닥) 종료코드 3 과 멈춘 '갱신' 시각이 흔적."""
    if LOG is None:
        return 3
    try:
        _note_memory_floor("정산 종료", exc)
        LOG.heartbeat("종료", f"❌ 메모리 부족(MemoryError)으로 정산 종료 — 다음 회차에서 이어 받음 · 처리기록 {LOG.csv.name}")
    except (MemoryError, OSError):
        pass                                 # 더 쓸 곳이 없음 — 종료코드 3 으로 끝냄(창으로 멈춰 있지 않게)
    return 3


def _evidence_targets_auto(now: datetime, start: date) -> list:
    """자동 증빙 대상 = 이번 회차 정산 계정 중 증빙이 남았거나 새 달이 된 계정(로그인 전에 고름 — 끝난 계정은 로그인 안 함).
    결과 기록이 깨진 계정은 그 계정만 오류로 남기고 뺌(무음 아님)."""
    from coupang_analytics import settlement_evidence as EV
    out = []
    for a in PASS_ACCOUNTS:
        try:
            if EV.renewal(EV.account_folder(EVIDENCE_DIR, name_of(a)), now, start)[0]:
                out.append(a)
        except (OSError, ValueError, KeyError) as exc:
            LOG.error(name_of(a), "증빙 대상 확인", exc)
    return out


def _evidence_sweep(args, action: str) -> None:
    """D-363·D-365 ① — 회차 정산이 끝난(완료·미완료) 뒤 남은 시간에만 증빙. 회차 끝 40분 전부터 새 계정·새 단계 안 함(③ ·
    args.until_at 을 그동안만 앞당김) · 남은 것은 다음 회차. 증빙 결과는 정산 완료 판정·_완료.json 을 바꾸지 않음(종합에만 줄)."""
    global LOG
    from coupang_analytics import settlement_evidence as EV
    if action not in ("done", "giveup") or not PASS_ACCOUNTS:
        return
    stop = EV.stop_at(args.until_at)
    gap = int(EV.STOP_BEFORE.total_seconds() // 60)
    if datetime.now() >= stop:
        log(f"[자동] 증빙 — 회차 끝 {gap}분 전({stop:%m-%d %H:%M}) 지남 — 다음 회차에 이어서(D-365)")
        return
    targets = _evidence_targets_auto(datetime.now(), args.start)
    if not targets:
        log("[자동] 증빙 — 받을 계정 없음(모두 이번 달 완료)")
        return
    keep = (args.until, args.until_at)
    LOG = RL.RunLog(BASE)
    LOG.accounts = [name_of(a) for a in targets]
    args.until, args.until_at = f"{stop:%H:%M}", stop
    log(f"[자동] 정산 받기 끝 → 증빙 받기 {len(targets)}계정 · {stop:%m-%d %H:%M} 부터 새 계정·새 단계 안 함(회차 끝 {gap}분 전 · D-365)")
    LOG.heartbeat("작동중", f"정산 끝 · 증빙 받는 중 {len(targets)}계정 · {stop:%H:%M} 멈춤")
    try:
        _run_accounts(targets, _evidence_auto, args)
    finally:
        args.until, args.until_at = keep
        CYCLE.add(LOG)                        # 증빙 줄도 회차 [실행 결과 종합]에(확인 필요 포함 · D-365 ⑤)
    _between_passes()


def _cycle_close(status: str, reason: str, *, stopped: bool = False) -> None:
    """회차 끝 [실행 결과 종합](D-168) — 이번 회차 모든 바퀴를 합쳐 마지막 실행 로그 끝에 쓰고, 상태 카드에 한 줄 요약."""
    if not CYCLE.passes:
        LOG.heartbeat(status, reason)
        return
    lines = RL.result_block(CYCLE, pending=_pending_jobs(), suspended=_suspended_pending(), stopped=stopped, note=reason,
                            title=f"실행 결과 종합 — 이번 회차 {CYCLE.passes}바퀴")
    lines[-1:-1] = [MEMLOG.summary()]       # D-346 ④ 그날 최고 메모리(시각·단계)·⚠ 횟수 — '==>' 한 줄 요약 바로 위
    for ln in lines:
        LOG.line(ln)
    LOG.heartbeat(status, reason, extra=(f"결과 종합: {lines[-1].removeprefix('==> ')}",))


def _watch_app(parent_pid: int) -> None:
    """D-020: 앱을 사람이 닫거나 강제 종료하면(무인 정상 완료 표시 없음) 정산도 자기 Chrome 과 함께 종료."""
    from coupang_analytics import app_process as AP

    def _gone() -> None:
        reason = "앱이 종료돼(사람이 닫음·강제 종료) 정산도 종료 — 다음 실행에서 이어서 받음"
        try:
            log(f"[자동] {reason}")
            LOG.heartbeat("종료", reason)
            why = AP.kill_self_tree()        # 돌아오면 = taskkill 이 못 끝냄(메모리 바닥 등 · T-113 11-18 07:00:02)
            LOG.heartbeat("종료", f"{reason} · ⚠ 자기 종료 명령 실패({why}) — 프로세스 직접 종료 · 남은 Chrome 은 다음 앱 시작 때 정리")
        finally:
            os._exit(1)                      # 기록을 못 써도 프로세스는 반드시 끝냄(처리 안 된 예외 창으로 남지 않게)
    AP.watch_parent(parent_pid, _gone)
    log(f"[자동] 앱(PID {parent_pid}) 종료 감시 — 사람이 앱을 끄면 함께 종료·무인 정상 완료 뒤엔 계속")


def _between_passes() -> None:
    """바퀴 사이(T-113 (라)): 정산이 띄운 Chrome(이 프로세스 자손)만 정리 · PC Chrome 수·메모리·정산 커밋 기록.
    앱·소유자 Chrome 은 자손이 아니라 안 건드림(앱 몫 잔여 = 앱 시작 reap_orphan_chrome). 조회 실패는 사유를 기록."""
    from coupang_analytics import settlement_memory as MEM
    try:
        n = MEM.sweep_own_chrome()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        log(f"  [Chrome·메모리] ⚠ Chrome 확인 실패({exc.__class__.__name__}: {str(exc)[:120]}) · 정산 프로세스 커밋 {_commit_text()}")
        return
    log(f"  [Chrome·메모리] 정산이 띄운 남은 Chrome {n['종료']}개 종료(남음 {n['남은자손']}) · 정리 전 PC Chrome {n['전체']}개 "
        f"(작업집합 {n['전체MB']}MB · 우리 자동화 {n['우리']}개 · 부모 없는 우리 Chrome {n['부모없는우리']}개 = 앱 몫·안 건드림) · "
        f"정산 프로세스 커밋 {_commit_text()}")


def _watch_wait_reason(W, prog, stage_path, cycle_start, manual: bool = False) -> tuple[str, dict | None]:
    """받기 전에 기다릴 이유('' = 지금 받아도 됨)와 앱 단계 기록. 이번 회차 ① 완료 전·①이 지금 도는 중이면 대기.
    manual(정산 탭 '정산 시작' · D-354) = ① 완료 대기는 건너뜀 · ①이 지금 도는 중이면 그대로 대기."""
    marker, _ = W.read_marker(stage_path)
    if not manual and not W.sales_done_in_cycle(marker, cycle_start):
        return f"①판매수집 완료 대기(이번 회차 {cycle_start:%m-%d %H:%M}~) — 완료되면 받기 시작", marker
    busy, why = W.sales_in_progress(prog)
    return (why if busy else ""), marker


def _sleep_until(sec: float, end: datetime) -> None:
    """sec 만큼 쉬되 회차 종료 시각(end)을 넘기지 않음."""
    time.sleep(max(0.0, min(sec, (end - datetime.now()).total_seconds())))


def _ledger_ready(args) -> bool:
    """watch 회차의 관리대장 반영(D-366 ②) — 성공할 때까지 바퀴마다 1번, 성공 뒤엔 그 회차에서 다시 안 함.
    실패 = 이유를 로그·상태 카드에 남기고 False(그 바퀴 안 돎 · 다음 바퀴에서 다시)."""
    if getattr(args, "ledger_synced", False):
        return True
    try:
        _ledger_presync()
    except LedgerSyncError as exc:
        reason = f"❌ {exc} — 이번 바퀴 정산 안 함 · {WATCH_POLL_SEC // 60}분 뒤 다음 바퀴에서 다시"
        log(f"[자동] {reason}")
        LOG.heartbeat("대기중", reason)
        return False
    args.ledger_synced = True
    return True


def cmd_watch(args) -> int:
    """00:10 앱과 함께 뜨는 정산 자동 수집(D-021·D-372). **이번 회차 ①판매수집 완료까지 기다렸다가** 받고, 다 받으면
    기록하고 종료·**그날 24:00** 이 되면 종료(남은 건 다음 회차). 중단(연속 실패/차단)·진전 없는 대기 초과도
    기록하고 종료. 같은 ①완료 기준으로 이미 '완료'면 바로 끝낸다. 앱을 사람이 끄면 함께 종료(--parent·D-020).
    같은 PC 에 둘 뜨지 않게 잠금."""
    from coupang_analytics import settlement_watch as W
    from coupang_analytics.pipeline_paths import _progress_path, _run_stage_path
    from coupang_analytics.registry_lock import RegistryLockError, registry_lock
    prog, stage_path = _progress_path("output"), _run_stage_path("output")
    try:
        with registry_lock(BASE / "_잠금" / "_watch.lock", wait_sec=0, on_log=log):
            cycle_start, cycle_end = W.cycle_window(datetime.now())
            PASS_ACCOUNTS.clear()             # 자동 증빙 대상 = 이번 회차 바퀴의 계정만(D-365)
            args.cycle_since = cycle_start.isoformat(timespec="seconds")   # 소급 상한 = 회차(00:10~) 단위(D-170) · --since 와 무관
            if getattr(args, "since", ""):    # 사람이 누른 전체실행 — 그 실행 뒤에 끝난 ①만 기다림(2026-10-13)
                cycle_start = max(cycle_start, datetime.fromisoformat(args.since))
            args.until, args.until_at, args.hidden = f"{cycle_end:%H:%M}", cycle_end, True   # 24:00 뒤 새 요청·새 계정 안 함
            if args.parent:
                _watch_app(args.parent)
            manual = bool(getattr(args, "manual", False))
            if manual:
                log("[수동] 정산 탭 '정산 시작' — 이번 회차 '완료' 기록·①판매수집 완료 대기 없이 바로 받음"
                    "(①이 지금 도는 중이면 끝날 때까지 대기 · D-354)")
            idle, last_state = 0, ""
            while datetime.now() < cycle_end:
                why, marker = _watch_wait_reason(W, prog, stage_path, cycle_start, manual)
                if why:
                    if why != last_state:
                        log(f"[자동] {why}")
                        last_state = why
                    LOG.heartbeat("대기중", why)      # 매 폴링마다 '갱신' 시각 바뀜 = 살아있음 신호
                    _sleep_until(WATCH_POLL_SEC, cycle_end)
                    continue
                last_state = ""
                key = W.sales_key(marker, datetime.now())
                done = W.read_done(DONE_FILE)
                if not manual and W.already_done(done, key, cycle_start):   # 같은 회차 '완료'면 끝(D-091 · 수동 = D-354)
                    log(f"[자동] 이번 ①판매수집({key}) 기준 정산은 이미 끝남 — {done.get('reason', '')} — 종료")
                    LOG.heartbeat(W.done_status(int(done.get("failed") or 0)), f"이미 끝남 — {done.get('reason', '')}")
                    return 0
                if not _ledger_ready(args):   # D-366 ②: 첫 바퀴 계정 읽기 전 대장→원장·비밀번호 · 실패 = 이 바퀴 중단
                    _sleep_until(WATCH_POLL_SEC, cycle_end)
                    continue
                stopped, work = _one_pass(args)
                _between_passes()
                idle = 0 if work else idle + 1
                fails = _watch_failures()
                action, reason = W.plan_after_pass(stopped, work, _pending_jobs(), _wait_accounts(LOG), idle, failed=fails)
                log(f"[자동] {reason}")
                if action in ("again", "later"):
                    LOG.heartbeat("대기중", reason)
                    _sleep_until(WATCH_CATCHUP_REST_SEC if action == "again" else WATCH_POLL_SEC, cycle_end)
                    continue
                W.write_done(DONE_FILE, key, action, reason, failed=len(fails))
                _evidence_sweep(args, action)
                _cycle_close(W.done_status(len(fails)) if action == "done" else "종료", reason, stopped=action != "done")
                return 0 if action == "done" else 1
            reason = f"회차 종료 시각({cycle_end:%m-%d %H:%M}) — 정산 종료(남은 건 {W.CYCLE_START:%H:%M} 다음 회차에서 이어서 받음)"
            log(f"[자동] {reason}")
            _cycle_close("종료", reason)
            return 0
    except RegistryLockError:
        log("[자동] 정산 자동 실행이 이미 떠 있음 — 이 실행은 종료")
        return 0


def _use_transfer_store() -> None:
    """D-187 — 이 실행의 정산 기록 위치 = 셀독전환자 몫(output/정산_셀독전환/정산 · 원장 정산 기록과 섞지 않음 D-111 ⑥).
    증빙(evidence)의 JOBS 전환과 같은 방식 · 바꾸기 전 파일 폴더 = 재사용할 원장 정산 파일."""
    global BASE, JOBS, FILES, COSTS, AMOUNTS, VERIFY, AMOUNTS_FROM, REUSE_FROM
    from coupang_analytics import transfer_settle as TS
    REUSE_FROM = FILES
    STORE.use_base(TS.STORE_DIR)
    BASE, JOBS, FILES, COSTS, AMOUNTS, VERIFY = STORE.BASE, STORE.JOBS, STORE.FILES, STORE.COSTS, STORE.AMOUNTS, STORE.VERIFY
    AMOUNTS_FROM = TS.FROM


def _transfer_work(args):
    """D-187 셀독전환자 한 계정 = 1단계와 같은 로그인·판정 → 원장 정산과 같은 요청(계정당 30건)·90초·받기 → (결과, 사유).
    잠금·사용 중 확인은 원장 정산과 같은 계정 잠금(output/정산/_잠금/{계정ID}.lock)·같은 Chrome 프로필 확인."""
    from coupang_analytics import transfer_login as TL
    from coupang_analytics import transfer_settle as TS
    from coupang_analytics.pipeline_sales import account_profile
    from coupang_analytics.registry_lock import RegistryLockError, registry_lock
    locks = REUSE_FROM.parent / "_잠금"

    def work(a, pws: list, stop_at) -> tuple[str, str]:
        acct, args.until_at = TS.settle_account(a), stop_at
        name = name_of(acct)
        LOG.heartbeat("작동중", f"실행 중: {name}")
        if _profile_busy(account_profile(a.account_id), until=stop_at):
            return TL.SKIP, "이 계정 Chrome 이 계속 실행 중(앱·원장 정산) — 다음 실행에서 다시"
        try:
            with registry_lock(locks / f"{a.account_id}.lock", wait_sec=5, on_log=log),                     TL.logged_in(a, pws, args.hidden, log) as (status, reason, b):
                LOG.record(name, "로그인", {TL.OK: RL.OK, TL.BLOCK: RL.BLOCK}.get(status, RL.FAIL), reason)
                if status != TL.OK:
                    return status, reason
                jobs = SJ.load_jobs(JOBS)
                cmd_request(acct, b, args, jobs)
                time.sleep(90)
                cmd_download(acct, b, args, jobs)
                return TL.OK, "로그인 됨 · 정산 자료 받기 끝(받은 파일 = 처리기록)"
        except RegistryLockError:
            return TL.SKIP, "원장 정산이 이 계정을 쓰는 중 — 다음 실행에서 다시"
        except BlockDetected as exc:
            LOG.error(name, "계정", exc, RL.BLOCK)
            return TL.BLOCK, f"정산 화면 차단 — {str(exc)[:80]}"
        except API.ServerBusy as exc:
            LOG.record(name, "계정", RL.WAIT, str(exc))
            return TL.SKIP, "쿠팡 서버 일시 오류 — 다음 실행에서 다시"
        except Exception as exc:                          # 처리기록·오류 로그(전체 추적) 남기고 '건너뜀'(transfer_settle)
            LOG.error(name, "계정", exc)
            raise
    return work


def _transfer_settle(args) -> int:
    """D-187 셀독전환자 정산 자료 받기(매일 18시 뒤 · §15 2단계) — 기록 위치 전환 → 기다림·계정 반복 → 누적 파일."""
    global LOG
    from coupang_analytics import transfer_settle as TS
    _use_transfer_store()
    TS.apply_args(args)
    LOG = RL.RunLog(BASE)
    LOG.heartbeat("작동중", "셀독전환자 정산 자료 받기")
    if args.parent:
        _watch_app(args.parent)
    rc = TS.main_cli(args, _transfer_work(args), log)
    LOG.summary(pending=_pending_jobs(), suspended=_suspended_pending())
    LOG.heartbeat("완료" if rc == 0 else "종료", f"셀독전환자 정산 자료 받기 · 종료코드 {rc}")
    return rc


def main() -> int:
    global LOG
    ap = argparse.ArgumentParser(description="쿠팡 정산 파일 배치 다운로드")
    ap.add_argument("command", choices=("probe", "request", "download", "run", "watch", "stats", "merge", "evidence",
                                        "transfer-login", "transfer-settle", "sources", "view"))
    ap.add_argument("--accounts", default="", help="계정ID 쉼표 구분(비우면 관리대장 전체)")
    ap.add_argument("--from", dest="start", type=date.fromisoformat, default=date(2026, 1, 1))
    ap.add_argument("--to", dest="end", type=date.fromisoformat, default=date.today())
    ap.add_argument("--cap", type=int, default=500, help="계정당 한 번 실행 요청 상한")
    ap.add_argument("--dry-run", action="store_true", help="요청 대상만 보여 주고 누르지 않음")
    ap.add_argument("--hidden", action="store_true", help="창 숨김(2차인증 필요하면 실패)")
    ap.add_argument("--channel", choices=("윙", "로켓그로스"), default="", help="한 채널만")
    ap.add_argument("--src", default="", help="merge: 합칠 정산 폴더(예: output\정산\정산 — 노트북에서 옮겨 온 것)")
    ap.add_argument("--until", default="", help="HH:MM 이후엔 새 요청·새 계정 시작 안 함(앱 00:10 무인 실행 전 멈춤)")
    ap.add_argument("--parent", type=int, default=0, help="watch·transfer-settle: 앱 PID — 사람이 앱을 끄면 정산도 종료(D-020)")
    ap.add_argument("--originals", default="", help="받은 쿠팡 원본(구매자명 포함)을 그대로 복사해 둘 폴더(증빙용·D-062)")
    ap.add_argument("--since", default="", help="watch: 이 시각(ISO) 뒤에 끝난 ①판매수집만 기다림(앱 전체실행 버튼)")
    ap.add_argument("--manual", action="store_true", help="watch: 정산 탭 '정산 시작' — 이번 회차 완료 기록·①완료 대기 없이 바로 받음(D-354)")
    ap.add_argument("--out", default="", help="evidence: 증빙 상위 폴더(계정마다 증빙_{사업자}_쿠팡원본 — D-067)")
    ap.add_argument("--source", default="", help="view: 화면 출처 ID(settlement_screen_view.SPECS · 첫 시험 = 한 계정 1회)")
    ap.add_argument("--redo", action="store_true", help="evidence: 끝난 계정도 다시 받기")
    ap.add_argument("--file", default="", help="transfer-login: 셀독전환자 파일(비우면 설정 transfer/file)")
    ap.add_argument("--retry", action="store_true", help="transfer-login: 성공·인증번호·같은 틀린 비번 제외하고 다시")
    ap.add_argument("--start", default="", help="transfer-login: HH:MM 까지 기다렸다 시작(밤에 이어 하기)")
    ap.add_argument("--run-id", default="", help="stats: 이어 쓸 실행ID(watch 바퀴 끝 별도 프로세스 · T-113)")
    ap.add_argument("--result", default="", help="stats: 결과 JSON 경로(watch 바퀴 끝 별도 프로세스 · T-113)")
    args = ap.parse_args()
    global CHANNELS, ORIGINALS, JOBS
    CHANNELS = (args.channel,) if args.channel else ()
    args.out = str(Path(args.out).resolve()) if args.out else ""     # set_workdir(작업 폴더 이동) 전에 고정
    ORIGINALS = Path(args.originals).resolve() if args.originals else None   # set_workdir(작업 폴더 이동) 전에 고정
    apppaths.set_workdir()
    if args.command == "transfer-login":   # D-111 셀독전환자 로그인 확인 — 정산 기록·상태 화면과 섞지 않음(output/정산_셀독전환)
        from coupang_analytics import transfer_login
        args.until = args.until or transfer_login.UNTIL_DEFAULT
        return transfer_login.main_cli(args)
    if args.command == "transfer-settle":   # D-187 셀독전환자 정산 자료 받기 — output/정산_셀독전환/정산(원장 정산 기록과 따로)
        return _transfer_settle(args)
    LOG = RL.RunLog(BASE, now=datetime.strptime(args.run_id, "%y%m%d_%H%M%S") if args.run_id else None)
    log(f"실행 {LOG.run_id} · 명령 {args.command} · 기간 {args.start}~{args.end} · 데이터 폴더 {Path.cwd()}")
    if args.command != "watch" and not args.result:   # watch 는 잠금을 얻은 뒤 cmd_watch 가 상태를 쓴다 — 2중 실행(잠금
        LOG.heartbeat("작동중", f"명령 {args.command} · 기간 {args.start}~{args.end}")   # 실패로 즉시 종료)·바퀴 끝 집계 자식이 덮지 않게
    if args.command == "stats":
        return _cmd_stats_main(args)
    if args.command == "sources":         # 받기 의심·자료 출처 대조만(로그인·윙 접속 없음 · --hidden = 공개 웹도 안 읽음)
        source_checks(web=not args.hidden)
        LOG.heartbeat("완료", "명령 sources")
        return 0
    if args.command == "watch":
        return cmd_watch(args)
    if args.command == "merge":
        return cmd_merge(args)
    accts = load_accounts({x.strip() for x in args.accounts.split(",") if x.strip()})
    if args.command in ("probe", "view"):
        accts = accts[:1]
    if args.command == "evidence":
        if not args.out:
            log("evidence 는 --out <증빙 상위 폴더> 가 필요합니다")
            return 2
        JOBS = EVIDENCE_JOBS
        JOBS.parent.mkdir(parents=True, exist_ok=True)
        accts = _evidence_targets(accts, args)
    run = {"probe": cmd_probe, "view": cmd_view, "request": cmd_request, "download": cmd_download, "run": cmd_run,
           "evidence": cmd_evidence}[args.command]
    LOG.accounts = [name_of(a) for a in accts]
    rc = _run_both(accts, args) if run is cmd_run else _run_accounts(accts, run, args)
    if run is cmd_run and not args.dry_run:
        source_checks()
    LOG.summary(pending=_pending_jobs(), suspended=_suspended_pending())
    log(f"기록: {LOG.csv} · 오류 추적: {LOG.errors if LOG.errors.exists() else '없음'}")
    LOG.heartbeat("완료", f"명령 {args.command} · 종료코드 {rc}")
    return rc


if __name__ == "__main__":
    try:
        _rc = main()
    except MemoryError as _exc:              # T-113 (다) — 처리 안 된 예외 창 대신 기록 후 종료코드 3
        _rc = _memory_floor_exit(_exc)
    sys.exit(_rc)
