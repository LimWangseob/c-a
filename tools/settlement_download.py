"""쿠팡 정산 파일 배치 다운로드(별도 프로그램) — 위탁계정마다 'N일 요청 → N+1일 받기' + 집계.

**사무실에서 실행**(로그인=앱과 같은 반자동: 보이는 창·비번 자동입력·2차인증은 사람·비번 오류는 재시도 없이 건너뜀).

  python tools/settlement_download.py probe    [--accounts ID]        # 읽기만 확인(최근 30일 일정·목록, 요청 안 함)
  python tools/settlement_download.py request  [--from 2026-01-01] [--to 2026-01-31] [--cap 5] [--dry-run] [--accounts ID,ID]
  python tools/settlement_download.py download [--accounts ID,ID]       # 다음날: 완료분 받기
  python tools/settlement_download.py run      [--from …] [--to …] [--accounts …]   # 요청+받기 한 세션(전체 확대용)
  python tools/settlement_download.py watch                             # 운용 PC 상시: 앱 ①판매수집 완료 후 재개·17:40 멈춤
  python tools/settlement_download.py stats                             # 받은 파일 집계 엑셀

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
from coupang_analytics import settlement_jobs as SJ  # noqa: E402
from coupang_analytics import settlement_runlog as RL  # noqa: E402
from coupang_analytics import settlement_wing_api as API  # noqa: E402

BASE = Path("output") / "정산"
JOBS = BASE / "_요청기록.json"
FILES = BASE / "파일"
COSTS = FILES / "비용"                                   # 로켓그로스 비용 리포트(집계 파일 목록과 분리)
AMOUNTS = BASE / "쿠팡지급내역"                           # 정산현황 금액(계정별 JSON) — 집계 대조용
GAP_SEC = (45, 75)                                      # 요청 사이 = 앱 반자동 순위 간격과 같게(소유자 2026-10-06)
LOOKUP_GAP_SEC = (3, 8)                                 # 조회·받기 사이(화면에서 넘겨 보는 정도)
LOG: RL.RunLog = None  # type: ignore[assignment]   # main() 에서 실행 시작 시 생성
CHANNELS: tuple = ()                                    # --channel 로 제한(비우면 윙·로켓그로스 둘 다)


def log(m: str) -> None:
    if LOG is None:
        print(m, flush=True)
    else:
        LOG.line(m)


class SessionSkip(Exception):
    """이 계정은 이번 실행에서 건너뜀(사용 중·비번 없음·로그인 미완료) — 오류 아님."""


class BlockDetected(Exception):
    """쿠팡 차단 화면(Access Denied 등) 감지 — 그 계정 즉시 중단."""


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


def name_of(a) -> str:
    return SA.display_name(a)


def _migrate_names(accts) -> None:
    """요청 기록(_요청기록.json)·받은 파일·쿠팡 지급 내역 파일의 예전 계정명 → 지금 계정명(멱등)."""
    jobs = SJ.load_jobs(JOBS)
    m = SA.renames([j.account for j in jobs], accts)
    mt = SA.renames([SF.parse_file_name(p.name)["account"] for d in (FILES, COSTS) for p in d.glob("*.xlsx")]
                    + [j.file.split("/")[-1].split("_")[0] for j in jobs if j.file], accts, tok=lambda x: SF._token(x, "계정명"))
    for j in jobs:
        j.account = m.get(j.account, j.account)
        if j.file:
            head, _, rest = j.file.rpartition("/")
            acct, _, tail = rest.partition("_")
            j.file = (head + "/" if head else "") + mt.get(acct, acct) + "_" + tail
    if m or mt:
        SJ.save_jobs(JOBS, jobs)
    for d in (FILES, COSTS):
        for p in list(d.glob("*.xlsx")):
            acct, _, tail = p.name.partition("_")
            if acct in mt:
                os.replace(p, p.with_name(mt[acct] + "_" + tail))
    for p in list(AMOUNTS.glob("*.json")):
        acct, _, ch = p.stem.rpartition("_")
        if acct in mt:
            os.replace(p, p.with_name(f"{mt[acct]}_{ch}.json"))
    if m or mt:
        log(f"  [계정명 맞춤] 요청 기록 {len(m)}개·파일 계정명 {len(mt)}개를 지금 계정 파일 이름으로 바꿈")


def _profile_in_use(profile: str) -> bool:
    """그 프로필로 떠 있는 Chrome 이 있으면 True(①판매수집 등이 사용 중) — 종료하지 않고 확인만."""
    ps = ("(Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -and "
          "$_.CommandLine.ToLower().Contains($env:SM_PROFILE.ToLower()) } | Measure-Object).Count")
    env = dict(os.environ, SM_PROFILE=str(Path(profile).resolve()))
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=20,
                       env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.stdout.strip() not in ("", "0")


def _profile_busy(profile: str, wait_sec: int = 60) -> bool:
    """사용 중이면 5초마다 다시 확인(최대 wait_sec). 실측 2026-10-06: 직전 실행의 Chrome 이 닫히는 데 약 1분 걸려
    바로 다음 실행이 '사용 중'으로 잘못 건너뜀 → 잠깐 기다려 본 뒤에도 떠 있을 때만 사용 중으로 본다."""
    end = time.monotonic() + wait_sec
    while _profile_in_use(profile):
        if time.monotonic() >= end:
            return True
        log("  (이 계정 Chrome 이 아직 떠 있음 — 닫히길 5초 기다림)")
        time.sleep(5)
    return False


def _login(b, a, pw, hidden: bool) -> None:
    """로그인 + 판정 코드 기록. 차단은 '차단', 비번 오류·미완료는 SessionSkip(재시도 안 함)."""
    from coupang_analytics.pipeline_sales import LoginBlocked, LoginCredentialError, _ensure_login
    name = name_of(a)
    try:
        ok = _ensure_login(b, a, pw, log, login=True, semi=not hidden)
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
def session(a, hidden: bool):
    """그 계정 로그인 세션(잠금·사용중 확인·로그인 판정 기록)."""
    from coupang_analytics.browser import WingBrowser
    from coupang_analytics.pipeline_sales import account_profile
    from coupang_analytics.registry_lock import RegistryLockError, registry_lock
    prof = account_profile(a.account_id)
    if _profile_busy(prof):
        raise SessionSkip("이 계정 Chrome 이 60초 넘게 실행 중(①판매수집 등)")
    pw = a.password                                       # 정산 계정 파일 값(메모리에서만 씀·앱 암호 저장소 미변경)
    if not pw:
        raise SessionSkip("계정 파일에 비밀번호 없음")
    try:
        with registry_lock(BASE / "_잠금" / f"{a.account_id}.lock", wait_sec=5, on_log=log):
            with WingBrowser(profile_dir=prof, offscreen=hidden) as b:
                _login(b, a, pw, hidden)
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


def api(b, who: str, method: str, path: str, body: dict | None = None):
    """WING 주소 호출. 차단 의심(403·429·HTML)이면 '차단' 기록 후 BlockDetected."""
    try:
        return API.call(b.page, method, path, body)
    except API.ApiBlocked as exc:
        LOG.record(who, "차단감지", RL.BLOCK, str(exc))
        raise BlockDetected(str(exc)) from exc


# ── 정산 일정 조회 ────────────────────────────────────────────────
_SOURCES = (("윙", API.WING_URL, API.WING_EVENTS, API.wing_events_body, API.wing_events),
            ("로켓그로스", API.RG_URL, API.RG_EVENTS, API.rg_events_body, API.rg_events))


def read_events(b, name: str, start: date, end: date) -> list:
    """지급일 기준 달 단위로 윙·로켓그로스 정산 일정 조회. 조회 구간마다 처리기록을 남긴다(날짜별 정상/비정상 분석)."""
    found: list = []
    for ch, url, path, body, parse in _SOURCES:
        if CHANNELS and ch not in CHANNELS:
            continue
        goto(b, url, name)
        for k, (ws, we) in enumerate(API.month_windows(start, end)):
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
            found += evs
    return found


def _save_amounts(name: str, ch: str, resp: dict) -> None:
    """쿠팡 정산현황 금액을 계정·채널별 JSON 에 (정산일·기간·비율) 키로 덮어 모아 둔다(원자적 저장)."""
    path = AMOUNTS / f"{SF._token(name, '계정명')}_{ch}.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    merged = {(r["정산일"], r["기간 시작"], r["기간 끝"], r["지급비율"]): r for r in old}
    merged.update({(r["정산일"], r["기간 시작"], r["기간 끝"], r["지급비율"]): r for r in API.amount_rows(resp, ch)})
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(sorted(merged.values(), key=lambda r: (r["정산일"], r["기간 시작"])), ensure_ascii=False,
                              indent=1), encoding="utf-8")
    os.replace(tmp, path)


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
    events = read_events(b, name, args.start, args.end)
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
            except Exception as exc:                       # 그 파일만 실패 기록 후 다음 파일(무음 아님)
                LOG.error(name, "받기", exc, **_job_fields(j))
            SJ.save_jobs(JOBS, jobs)


def cmd_run(a, b, args, jobs: list) -> None:
    """한 세션에서 요청 → (생성 약 1분) → 받기. 요청이 길면 그 사이 앞선 파일은 이미 완료돼 있음."""
    cmd_request(a, b, args, jobs)
    if not args.dry_run:
        time.sleep(90)
        cmd_download(a, b, args, jobs)


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


def cmd_stats() -> None:
    from coupang_analytics import settlement_stats as ST
    files = [SF.load_settle_file(p) for p in sorted(FILES.glob("*.xlsx"))]
    amounts = []
    for p in sorted(AMOUNTS.glob("*.json")):
        acct, ch = p.stem.rsplit("_", 1)
        amounts += [{"계정": acct, "채널": ch, **r} for r in json.loads(p.read_text(encoding="utf-8"))]
    costs = []
    for p in sorted(COSTS.glob("*.xlsx")):
        m = SF.parse_file_name(p.name)
        for sheet, v in SF.rg_cost_totals(SF.read_sheets(p), m["period_end"]).items():
            costs.append((m["account"], m["settle_date"], m["period_start"], m["period_end"], m["report"], sheet, v))
    res = ST.aggregate(files)
    out = ST.write_stats(BASE / f"정산집계_{datetime.now():%y%m%d_%H%M%S}.xlsx", res, files=files, amounts=amounts,
                         costs=costs)
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
        log(f"== {name} {args.command} ==")
        try:
            with session(a, args.hidden) as b:
                run(a, b, args, jobs)
            bad = 0
        except SessionSkip as exc:
            LOG.record(name, "계정", RL.SKIP, str(exc))
        except BlockDetected as exc:
            bad += 1
            LOG.error(name, "계정", exc, RL.BLOCK)
        except Exception as exc:                           # 그 계정만 중단(무음 아님·전체 추적은 오류 로그)
            bad += 1
            LOG.error(name, "계정", exc)
        if bad >= 2:
            LOG.record("(전체)", "중단", RL.BLOCK, "연속 2계정 실패/차단 — 전체 중단(화면 변경·차단 의심, probe 로 확인)")
            return 1
    return 0


WATCH_STATE = BASE / "_자동실행.json"
WATCH_POLL_SEC = 300


def cmd_watch(args) -> int:
    """운용 PC 상시 실행: 앱 ①판매수집 완료 → 정산 재개(숨김 창) → 다음날 17:40 멈춤 → 반복(settlement_watch).
    같은 PC에 watch 가 둘 뜨지 않게 잠금. 대기 중엔 5분마다 확인하고, 판단이 바뀔 때만 기록한다."""
    from coupang_analytics import settlement_watch as W
    from coupang_analytics.pipeline_paths import _run_stage_path
    from coupang_analytics.registry_lock import RegistryLockError, registry_lock
    global LOG
    try:
        with registry_lock(BASE / "_잠금" / "_watch.lock", wait_sec=0, on_log=log):
            last = ""
            while True:
                marker, why = W.read_marker(_run_stage_path("output"))
                action, reason, cycle = W.decide(datetime.now(), marker, W.load_last_cycle(WATCH_STATE))
                if reason != last:
                    log(f"[자동] {reason}" + (f" ({why})" if why and action == "wait" else ""))
                    last = reason
                if action == "wait":
                    # 대기 중엔 로그는 판단이 바뀔 때만 남기지만, 상태 파일은 매 폴링마다 덮어써
                    # '갱신' 시각이 계속 바뀌게 한다 → 운용 PC에서 창 없이도 '살아있음'을 확인할 수 있다.
                    LOG.heartbeat("대기중", reason + (f" ({why})" if why else ""))
                    time.sleep(WATCH_POLL_SEC)
                    continue
                LOG = RL.RunLog(BASE)
                args.until_at, args.end, args.hidden = cycle + timedelta(days=1), date.today(), True
                log(f"실행 {LOG.run_id} · 자동 · {reason} · 기간 {args.start}~{args.end} · 멈춤 {args.until_at:%m-%d %H:%M}")
                LOG.heartbeat("작동중", f"{reason} · 멈춤 {args.until_at:%m-%d %H:%M}")
                try:
                    _run_accounts(load_accounts(set()), cmd_run, args)
                    if not past_until(args):             # 멈춤 전에 한 바퀴 다 돌았음(연속 차단 중단 포함) = 이번 주기 완료
                        W.save_last_cycle(WATCH_STATE, cycle)
                    cmd_stats()
                except Exception as exc:                 # 그 바퀴만 실패 기록 후 5분 뒤 다시 판단(watch 는 계속)
                    LOG.error("(전체)", "자동실행", exc)
                    LOG.heartbeat("오류", f"자동실행 예외 — {exc.__class__.__name__}: {exc}")
                    time.sleep(WATCH_POLL_SEC)
                LOG.summary()
    except RegistryLockError:
        log("[자동] 정산 자동 실행이 이미 떠 있음 — 이 실행은 종료")
        return 0


def main() -> int:
    global LOG
    ap = argparse.ArgumentParser(description="쿠팡 정산 파일 배치 다운로드")
    ap.add_argument("command", choices=("probe", "request", "download", "run", "watch", "stats"))
    ap.add_argument("--accounts", default="", help="계정ID 쉼표 구분(비우면 관리대장 전체)")
    ap.add_argument("--from", dest="start", type=date.fromisoformat, default=date(2026, 1, 1))
    ap.add_argument("--to", dest="end", type=date.fromisoformat, default=date.today())
    ap.add_argument("--cap", type=int, default=500, help="계정당 한 번 실행 요청 상한")
    ap.add_argument("--dry-run", action="store_true", help="요청 대상만 보여 주고 누르지 않음")
    ap.add_argument("--hidden", action="store_true", help="창 숨김(2차인증 필요하면 실패)")
    ap.add_argument("--channel", choices=("윙", "로켓그로스"), default="", help="한 채널만")
    ap.add_argument("--until", default="", help="HH:MM 이후엔 새 요청·새 계정 시작 안 함(앱 18:00 무인 실행 전 멈춤)")
    args = ap.parse_args()
    global CHANNELS
    CHANNELS = (args.channel,) if args.channel else ()
    apppaths.set_workdir()
    LOG = RL.RunLog(BASE)
    log(f"실행 {LOG.run_id} · 명령 {args.command} · 기간 {args.start}~{args.end} · 데이터 폴더 {Path.cwd()}")
    LOG.heartbeat("작동중", f"명령 {args.command} · 기간 {args.start}~{args.end}")   # 수동 실행도 창 없이 모니터링
    if args.command == "stats":
        cmd_stats()
        LOG.heartbeat("완료", "명령 stats")
        return 0
    if args.command == "watch":
        return cmd_watch(args)
    accts = load_accounts({x.strip() for x in args.accounts.split(",") if x.strip()})
    if args.command == "probe":
        accts = accts[:1]
    run = {"probe": cmd_probe, "request": cmd_request, "download": cmd_download, "run": cmd_run}[args.command]
    rc = _run_accounts(accts, run, args)
    LOG.summary()
    log(f"기록: {LOG.csv} · 오류 추적: {LOG.errors if LOG.errors.exists() else '없음'}")
    LOG.heartbeat("완료", f"명령 {args.command} · 종료코드 {rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
