"""쿠팡 정산 파일 배치 다운로드(별도 프로그램) — 위탁계정마다 'N일 요청 → N+1일 받기' + 집계.

**사무실에서 실행**(로그인=앱과 같은 반자동: 보이는 창·비번 자동입력·2차인증은 사람·비번 오류는 재시도 없이 건너뜀).

  python tools/settlement_download.py probe    [--accounts ID]        # 읽기만 확인(최근 30일 일정·목록, 요청 안 함)
  python tools/settlement_download.py request  [--from 2026-01-01] [--to 2026-01-31] [--cap 5] [--dry-run] [--accounts ID,ID]
  python tools/settlement_download.py download [--accounts ID,ID]       # 다음날: 완료분 받기
  python tools/settlement_download.py run      [--from …] [--to …] [--accounts …]   # 요청+받기 한 세션(전체 확대용)
  python tools/settlement_download.py watch                             # 운용 PC 상시: 앱 ①판매수집 완료 후 재개·17:40 멈춤
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
import json
import os
import random
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics import apppaths  # noqa: E402
from coupang_analytics import settlement_accounts as SA  # noqa: E402
from coupang_analytics import settlement_files as SF  # noqa: E402
from coupang_analytics import settlement_forecast as FC  # noqa: E402
from coupang_analytics import settlement_jobs as SJ  # noqa: E402
from coupang_analytics import settlement_runlog as RL  # noqa: E402
from coupang_analytics import settlement_store as STORE  # noqa: E402
from coupang_analytics.settlement_store import AMOUNTS, BASE, COSTS, FILES, JOBS, VERIFY  # noqa: E402,F401
from coupang_analytics import settlement_wing_api as API  # noqa: E402

GAP_SEC = (45, 75)                                      # 요청 사이 = 앱 반자동 순위 간격과 같게(소유자 2026-10-06)
LOOKUP_GAP_SEC = (3, 8)
AMOUNTS_FROM = date(2025, 11, 1)                        # 지급 내역 기록 시작 — 2026 첫 30% 줄의 70% 몫(2025-11·12 판매)·2025 보류(D-083)                                 # 조회·받기 사이(화면에서 넘겨 보는 정도)
LOG: RL.RunLog = None  # type: ignore[assignment]   # main() 에서 실행 시작 시 생성
CHANNELS: tuple = ()                                    # --channel 로 제한(비우면 윙·로켓그로스 둘 다)
ORIGINALS: Path | None = None                           # --originals: 받은 쿠팡 원본 그대로 복사할 증빙 폴더(D-062)


def log(m: str) -> None:
    if LOG is None:
        print(m, flush=True)
    else:
        LOG.line(m)


class SessionSkip(Exception):
    """이 계정은 이번 실행에서 건너뜀(사용 중·비번 없음·로그인 미완료) — 오류 아님."""


class BlockDetected(Exception):
    """쿠팡 차단 화면(Access Denied 등) 감지 — 그 계정 즉시 중단."""


def _is_browser_closed(exc: BaseException) -> bool:
    """브라우저/탭이 닫혀 생긴 오류인지(차단이 아님). 18:00 앱 시작 시 reap_orphan_chrome 이 정산 Chrome 을
    같이 종료하면 playwright 가 TargetClosedError 를 던진다 — 이걸 '차단'·'연속 실패'로 세면 안 된다(일시적·재시도)."""
    name = exc.__class__.__name__
    msg = str(exc)
    return ("TargetClosed" in name
            or "Target page, context or browser has been closed" in msg
            or "has been closed" in msg
            or "Browser closed" in msg
            or "Connection closed" in msg)


# ── 계정·세션 ─────────────────────────────────────────────────────
def load_accounts(only: set) -> list:
    """정산 계정 파일(계정ID·비번·대표자-사업자) — 위치=config.json settlement/accounts_file(기본 data/정산_계정목록.txt).
    읽을 때마다 예전 이름으로 된 요청 기록·파일·금액 기록을 지금 이름으로 맞춘다(계정ID 기준)."""
    from coupang_analytics import appconfig
    path = appconfig.get(SA.CONFIG_KEY, "") or SA.DEFAULT_PATH
    try:
        accts, warns = SA.read_accounts_file(path)
    except SA.AccountsFileError as exc:
        raise SystemExit(f"정산 계정 파일 오류: {exc}") from exc
    for w in warns:
        log(f"  [계정 파일] {w}")
    log(f"  [계정 파일] {path} · 계정 {len(accts)}개")
    _migrate_names(accts)
    picked = [a for a in accts if not only or a.account_id in only]
    if only and len(picked) != len(only):
        raise SystemExit(f"계정 파일에 없는 계정: {sorted(only - {a.account_id for a in picked})}")
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
    pws, src = SA.login_passwords(a)                      # 관리대장(앱 저장) 값 먼저 · 대장에 없으면 계정 파일 값
    if not pws:
        raise SessionSkip("비밀번호 없음(관리대장·정산 계정 파일 모두)")
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
        for k, (ws, we) in enumerate(API.month_windows(min(start, amounts_from or start), end)):
            if k:
                time.sleep(random.uniform(*LOOKUP_GAP_SEC))
            resp = api(b, name, "POST", path, body(ws, we))
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
        _read_forecast(b, name, ch, path, body, end)
    return found


def _read_forecast(b, name: str, ch: str, path: str, body, end: date) -> None:
    """오늘 뒤 AHEAD_DAYS 까지 정산현황 조회 → 쿠팡이 미리 만든 정산 줄을 예정 기록에만(D-078). 받을 파일 계획엔 안 씀.
    쿠팡이 미래 날짜를 거부하는 등 실패해도 그 계정 정산은 계속(차단 신호만 그대로 올림)."""
    for ws, we in API.month_windows(end + timedelta(days=1), end + timedelta(days=FC.AHEAD_DAYS)):
        time.sleep(random.uniform(*LOOKUP_GAP_SEC))
        try:
            resp = api(b, name, "POST", path, body(ws, we))
        except (API.SiteChangedError, API.ServerBusy) as exc:
            LOG.record(name, "조회", RL.WAIT, f"정산 예정 조회 실패(진행) — {str(exc)[:120]}", channel=ch, period=f"{ws}~{we}")
            continue
        _save_amounts(name, ch, resp)
        LOG.record(name, "조회", RL.OK, "정산 예정(쿠팡 미리 계산) 조회", channel=ch, period=f"{ws}~{we}")


def _save_amounts(name: str, ch: str, resp: dict) -> None:
    """정산일 지난 줄 = 지급 내역 · 오늘 뒤 줄 = 예정 기록(수집일별·D-078)."""
    past, future = FC.split_future(API.amount_rows(resp, ch), date.today())
    STORE.save_amounts(name, ch, past)
    FC.record(STORE.FORECAST, SF._token(name, "계정명"), ch, future, date.today())


def past_until(args) -> bool:
    """멈춤 시각이 지났으면 True. watch=주기 끝 시각(until_at), 직접 실행=--until HH:MM(오늘 그 시각).
    앱 18:00 무인 실행과 같은 계정 프로필이 겹치지 않게."""
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


def _get_bytes(b, url: str) -> bytes:
    r = b.context.request.get(url, timeout=120000)
    body = r.body()
    if r.status != 200 or body[:2] != b"PK":                # xlsx = zip
        raise API.SiteChangedError(f"파일 받기 실패: {r.status} {r.headers.get('content-type')} {body[:60]!r}")
    return body


def _fetch_one(b, j, row, name: str) -> None:
    if j.channel == "윙":
        data = _get_bytes(b, row.handle)
    else:
        url = api(b, name, "POST", API.RG_GET, {"requestTime": row.handle, "locale": "ko"}).get("url")
        if not url:
            raise API.SiteChangedError("로켓그로스 받기 응답에 url 없음")
        data = _get_bytes(b, url)
    fname = SF.settle_file_name(name, date.fromisoformat(j.settle_date), j.channel, j.kind, j.report,
                                date.fromisoformat(j.period_start), date.fromisoformat(j.period_end))
    raw = BASE / "_받는중" / fname
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(data)
    if ORIGINALS is not None:                              # 증빙용 원본(구매자명 포함·받은 그대로) — 아래 처리와 별개
        ORIGINALS.mkdir(parents=True, exist_ok=True)
        (ORIGINALS / fname).write_bytes(data)
    if j.channel == "로켓그로스" and j.report != "판매수수료":
        _keep_cost(raw, j, name, fname)
        return
    SF.scrub_pii(raw, FILES / fname)                       # 구매자명 지운 사본만 보관
    raw.unlink()
    f = SF.load_settle_file(FILES / fname)                 # 내용 확인(로켓그로스 기간 대조 포함)
    j.status, j.file = SJ.ST_DONE, fname
    LOG.record(name, "받기", RL.OK, f"{fname} · 줄 {len(f.rows)} · 정산합 {f.settle_total:,} · 검산경고 "
               f"{len(f.warnings)}", **_job_fields(j))


def _keep_cost(raw: Path, j, name: str, fname: str) -> None:
    """비용 리포트: 개인정보 칸 없음 확인 → 시트별 최종비용 읽기(기간 대조) → 비용 폴더로 옮김."""
    sheets = SF.read_sheets(raw)
    SF.assert_no_pii(sheets)
    totals = SF.rg_cost_totals(sheets, date.fromisoformat(j.period_end))
    COSTS.mkdir(parents=True, exist_ok=True)
    os.replace(raw, COSTS / fname)
    j.status, j.file = SJ.ST_DONE, f"비용/{fname}"
    LOG.record(name, "받기", RL.OK, f"{fname} · " + " · ".join(f"{k} {v:,}" for k, v in totals.items()),
               **_job_fields(j))


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
    """한 세션에서 요청 → (생성 약 1분) → 받기. 요청이 길면 그 사이 앞선 파일은 이미 완료돼 있음."""
    cmd_request(a, b, args, jobs)
    if not args.dry_run:
        time.sleep(90)
        cmd_download(a, b, args, jobs)
        collect_verify(a, b, args)


def collect_verify(a, b, args) -> None:
    """검증 원자료(조회만)를 계정별로 하루 한 번 저장 — settlement_verify_collect. 오늘 이미 모았으면 건너뜀."""
    from coupang_analytics import settlement_verify_collect as VC
    name = name_of(a)
    path = VERIFY / f"{SF._token(name, '계정명')}.json"
    today = date.today()
    if path.exists() and json.loads(path.read_text(encoding="utf-8")).get("수집일") == today.isoformat():
        return
    data = VC.collect(lambda m, p, body: api(b, name, m, p, body), lambda url: goto(b, url, name), args.start, today,
                      note=lambda m: LOG.record(name, "검증", RL.WAIT, m),
                      gap=lambda: time.sleep(random.uniform(*LOOKUP_GAP_SEC)))
    path.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_json_atomic(path, data)
    LOG.record(name, "검증", RL.OK, f"검증 자료 저장 — 월렛 {len(data.get('wallet') or [])}건·조회 실패 {len(data['조회 실패'])}건")


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


def cmd_evidence(a, b, args, jobs: list) -> None:
    """계정 하나의 증빙 원본 전체(D-067): 정산 원본 → 정산 줄 없는 주 비용 → 판매분석 월별 → 지급 증빙 메뉴 → 목록·결과."""
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
            steps[label] = {"결과": EV.FAIL, "내용": f"멈춤 시각 {args.until} — 다음 실행에서", "파일": 0}
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


def cmd_stats() -> None:
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
    log(f"집계 정산 파일 {len(files)}개·비용 리포트 {len(costs)}시트·쿠팡 지급 내역 {len(amounts)}줄 → {out} "
        f"(경고 {len(res.warnings)}건)")


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
            if _is_browser_closed(exc):   # 브라우저 닫힘(예: 18:00 앱 시작 reap)=일시적 → '차단'·연속실패로 안 셈·다음 바퀴 재시도
                LOG.record(name, "계정", RL.WAIT,
                           f"브라우저가 닫힘(일시적·차단 아님) — 다음 바퀴에 재시도 ({exc.__class__.__name__})")
            else:                                          # 그 계정만 중단(무음 아님·전체 추적은 오류 로그)
                bad += 1
                LOG.error(name, "계정", exc)
        if bad >= 2:
            LOG.record("(전체)", "중단", RL.BLOCK, "연속 2계정 실패/차단 — 전체 중단(화면 변경·차단 의심, probe 로 확인)")
            return 1
    return 0


WATCH_POLL_SEC = 300             # ①판매수집 진행 중 정지·파일 생성 대기 확인 간격
WATCH_CATCHUP_REST_SEC = 60      # 소급(받을 게 남음) 중 한 바퀴와 다음 바퀴 사이 짧은 쉼
DONE_FILE = BASE / "로그" / "_완료.json"   # 같은 ①완료 기준 '완료' 기록(중복 실행 방지·D-010)


def _sweep_work_count(lg) -> int:
    """이번 한 바퀴에서 실제로 한 일(새 요청·받은 파일) 수."""
    return sum(1 for r in lg.rows if r["단계"] in ("요청", "받기") and r["결과"] == RL.OK)


def _wait_accounts(lg) -> int:
    """이번 바퀴에 '대기'(서버 일시 오류·브라우저 닫힘)로 넘긴 계정 수 — 아직 다 받았다고 볼 수 없음."""
    return len({r["계정"] for r in lg.rows if r["단계"] == "계정" and r["결과"] == RL.WAIT})


def _pending_jobs() -> int:
    """요청예정·요청됨(쿠팡 파일 생성 대기) 작업 수."""
    return sum(1 for j in SJ.load_jobs(JOBS) if j.status in (SJ.ST_PLANNED, SJ.ST_REQUESTED))


def _one_pass(args) -> tuple[bool, int]:
    """한 바퀴(전 계정) → (중단됐나, 새로 한 일 수). 예기치 못한 예외는 기록하고 '한 일 0'으로."""
    global LOG
    LOG = RL.RunLog(BASE)
    args.end = date.today()
    log(f"실행 {LOG.run_id} · 자동 · 정산 수집 · 기간 {args.start}~{args.end}")
    LOG.heartbeat("작동중", f"정산 수집 · 기간 {args.start}~{args.end}")
    try:
        rc = _run_accounts(load_accounts(set()), cmd_run, args)
        work = _sweep_work_count(LOG)
        cmd_stats()
    except Exception as exc:                 # 그 바퀴만 실패 기록(다음 판단은 진전 없음으로)
        LOG.error("(전체)", "자동실행", exc)
        return False, 0
    LOG.summary()
    return rc == 1, work


def _watch_app(parent_pid: int) -> None:
    """D-020: 앱을 사람이 닫거나 강제 종료하면(무인 정상 완료 표시 없음) 정산도 자기 Chrome 과 함께 종료."""
    from coupang_analytics import app_process as AP

    def _gone() -> None:
        reason = "앱이 종료돼(사람이 닫음·강제 종료) 정산도 종료 — 다음 실행에서 이어서 받음"
        log(f"[자동] {reason}")
        LOG.heartbeat("종료", reason)
        AP.kill_self_tree()
    AP.watch_parent(parent_pid, _gone)
    log(f"[자동] 앱(PID {parent_pid}) 종료 감시 — 사람이 앱을 끄면 함께 종료·무인 정상 완료 뒤엔 계속")


def _watch_wait_reason(W, prog, stage_path, cycle_start) -> tuple[str, dict | None]:
    """받기 전에 기다릴 이유('' = 지금 받아도 됨)와 앱 단계 기록. 이번 회차 ① 완료 전·①이 지금 도는 중이면 대기."""
    marker, _ = W.read_marker(stage_path)
    if not W.sales_done_in_cycle(marker, cycle_start):
        return f"①판매수집 완료 대기(이번 회차 {cycle_start:%m-%d %H:%M}~) — 완료되면 받기 시작", marker
    busy, why = W.sales_in_progress(prog)
    return (why if busy else ""), marker


def _sleep_until(sec: float, end: datetime) -> None:
    """sec 만큼 쉬되 회차 종료 시각(end)을 넘기지 않음."""
    time.sleep(max(0.0, min(sec, (end - datetime.now()).total_seconds())))


def cmd_watch(args) -> int:
    """18:00 앱과 함께 뜨는 정산 자동 수집(D-021). **이번 회차 ①판매수집 완료까지 기다렸다가** 받고, 다 받으면
    기록하고 종료·**다음 날 17:55** 가 되면 종료(남은 건 다음 회차). 중단(연속 실패/차단)·진전 없는 대기 초과도
    기록하고 종료. 같은 ①완료 기준으로 이미 '완료'면 바로 끝낸다. 앱을 사람이 끄면 함께 종료(--parent·D-020).
    같은 PC 에 둘 뜨지 않게 잠금."""
    from coupang_analytics import settlement_watch as W
    from coupang_analytics.pipeline_paths import _progress_path, _run_stage_path
    from coupang_analytics.registry_lock import RegistryLockError, registry_lock
    prog, stage_path = _progress_path("output"), _run_stage_path("output")
    try:
        with registry_lock(BASE / "_잠금" / "_watch.lock", wait_sec=0, on_log=log):
            cycle_start, cycle_end = W.cycle_window(datetime.now())
            if getattr(args, "since", ""):    # 사람이 누른 전체실행 — 그 실행 뒤에 끝난 ①만 기다림(2026-10-13)
                cycle_start = max(cycle_start, datetime.fromisoformat(args.since))
            args.until, args.until_at, args.hidden = f"{cycle_end:%H:%M}", cycle_end, True   # 17:55 뒤 새 요청·새 계정 안 함
            if args.parent:
                _watch_app(args.parent)
            idle, last_state = 0, ""
            while datetime.now() < cycle_end:
                why, marker = _watch_wait_reason(W, prog, stage_path, cycle_start)
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
                if W.already_done(done, key):
                    log(f"[자동] 이번 ①판매수집({key}) 기준 정산은 이미 끝남 — {done.get('reason', '')} — 종료")
                    LOG.heartbeat(W.done_status(int(done.get("failed") or 0)), f"이미 끝남 — {done.get('reason', '')}")
                    return 0
                stopped, work = _one_pass(args)
                idle = 0 if work else idle + 1
                fails = LOG.unresolved_failures()
                action, reason = W.plan_after_pass(stopped, work, _pending_jobs(), _wait_accounts(LOG), idle, failed=fails)
                log(f"[자동] {reason}")
                if action in ("again", "later"):
                    LOG.heartbeat("대기중", reason)
                    _sleep_until(WATCH_CATCHUP_REST_SEC if action == "again" else WATCH_POLL_SEC, cycle_end)
                    continue
                W.write_done(DONE_FILE, key, action, reason, failed=len(fails))
                LOG.heartbeat(W.done_status(len(fails)) if action == "done" else "종료", reason)
                return 0 if action == "done" else 1
            reason = f"회차 종료 시각({cycle_end:%m-%d %H:%M}) — 정산 종료(남은 건 18:00 다음 회차에서 이어서 받음)"
            log(f"[자동] {reason}")
            LOG.heartbeat("종료", reason)
            return 0
    except RegistryLockError:
        log("[자동] 정산 자동 실행이 이미 떠 있음 — 이 실행은 종료")
        return 0


def main() -> int:
    global LOG
    ap = argparse.ArgumentParser(description="쿠팡 정산 파일 배치 다운로드")
    ap.add_argument("command", choices=("probe", "request", "download", "run", "watch", "stats", "merge", "evidence"))
    ap.add_argument("--accounts", default="", help="계정ID 쉼표 구분(비우면 관리대장 전체)")
    ap.add_argument("--from", dest="start", type=date.fromisoformat, default=date(2026, 1, 1))
    ap.add_argument("--to", dest="end", type=date.fromisoformat, default=date.today())
    ap.add_argument("--cap", type=int, default=500, help="계정당 한 번 실행 요청 상한")
    ap.add_argument("--dry-run", action="store_true", help="요청 대상만 보여 주고 누르지 않음")
    ap.add_argument("--hidden", action="store_true", help="창 숨김(2차인증 필요하면 실패)")
    ap.add_argument("--channel", choices=("윙", "로켓그로스"), default="", help="한 채널만")
    ap.add_argument("--src", default="", help="merge: 합칠 정산 폴더(예: output\정산\정산 — 노트북에서 옮겨 온 것)")
    ap.add_argument("--until", default="", help="HH:MM 이후엔 새 요청·새 계정 시작 안 함(앱 18:00 무인 실행 전 멈춤)")
    ap.add_argument("--parent", type=int, default=0, help="watch: 앱 PID — 사람이 앱을 끄면 정산도 종료(D-020)")
    ap.add_argument("--originals", default="", help="받은 쿠팡 원본(구매자명 포함)을 그대로 복사해 둘 폴더(증빙용·D-062)")
    ap.add_argument("--since", default="", help="watch: 이 시각(ISO) 뒤에 끝난 ①판매수집만 기다림(앱 전체실행 버튼)")
    ap.add_argument("--out", default="", help="evidence: 증빙 상위 폴더(계정마다 증빙_{사업자}_쿠팡원본 — D-067)")
    ap.add_argument("--redo", action="store_true", help="evidence: 끝난 계정도 다시 받기")
    args = ap.parse_args()
    global CHANNELS, ORIGINALS, JOBS
    CHANNELS = (args.channel,) if args.channel else ()
    args.out = str(Path(args.out).resolve()) if args.out else ""     # set_workdir(작업 폴더 이동) 전에 고정
    ORIGINALS = Path(args.originals).resolve() if args.originals else None   # set_workdir(작업 폴더 이동) 전에 고정
    apppaths.set_workdir()
    LOG = RL.RunLog(BASE)
    log(f"실행 {LOG.run_id} · 명령 {args.command} · 기간 {args.start}~{args.end} · 데이터 폴더 {Path.cwd()}")
    if args.command != "watch":   # watch 는 잠금을 얻은 뒤 cmd_watch 가 상태를 쓴다 — 2중 실행(잠금 실패로 즉시
        LOG.heartbeat("작동중", f"명령 {args.command} · 기간 {args.start}~{args.end}")   # 종료)이 실제 실행 상태를 덮지 않게
    if args.command == "stats":
        cmd_stats()
        LOG.heartbeat("완료", "명령 stats")
        return 0
    if args.command == "watch":
        return cmd_watch(args)
    if args.command == "merge":
        return cmd_merge(args)
    accts = load_accounts({x.strip() for x in args.accounts.split(",") if x.strip()})
    if args.command == "probe":
        accts = accts[:1]
    if args.command == "evidence":
        if not args.out:
            log("evidence 는 --out <증빙 상위 폴더> 가 필요합니다")
            return 2
        JOBS = EVIDENCE_JOBS
        JOBS.parent.mkdir(parents=True, exist_ok=True)
        accts = _evidence_targets(accts, args)
    run = {"probe": cmd_probe, "request": cmd_request, "download": cmd_download, "run": cmd_run,
           "evidence": cmd_evidence}[args.command]
    rc = _run_accounts(accts, run, args)
    LOG.summary()
    log(f"기록: {LOG.csv} · 오류 추적: {LOG.errors if LOG.errors.exists() else '없음'}")
    LOG.heartbeat("완료", f"명령 {args.command} · 종료코드 {rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
