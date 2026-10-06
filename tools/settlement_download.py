"""쿠팡 정산 파일 배치 다운로드(별도 프로그램) — 위탁계정마다 'N일 요청 → N+1일 받기' + 집계.

**사무실에서 실행**(로그인=앱과 같은 반자동: 보이는 창·비번 자동입력·2차인증은 사람·비번 오류는 재시도 없이 건너뜀).

  python tools/settlement_download.py probe    [--accounts ID]        # 첫 실행: 화면 구조만 확인(요청 안 함)
  python tools/settlement_download.py request  [--from 2026-01-01] [--to 2026-01-31] [--cap 5] [--dry-run] [--accounts ID,ID]
  python tools/settlement_download.py download [--accounts ID,ID]       # 다음날: 완료분 받기
  python tools/settlement_download.py stats                             # 받은 파일 집계 엑셀

규칙(차단 위험 완화·소유자 2026-10-06): 정산현황 '정산확정' 줄만 · 윙은 월별(최종액) 파일이 나온 달이면 주정산 생략 ·
로켓그로스는 같은 매출 주 1회 · 계정당 하루 요청 상한(--cap) · 요청 사이 30~90초 · **화면 이동마다 차단 검사 → 감지 시
그 계정 즉시 중단** · 연속 2계정 실패/차단이면 전체 중단. 같은 PC 동시 실행: 그 계정 프로필 Chrome 이 떠 있으면 건너뜀·
reap_orphan_chrome 미호출. 기록: output/정산/로그/(실행·처리기록·오류) — settlement_runlog. 데이터 폴더는 앱과 같게
(로그인된 계정 프로필 재사용) `COUPANG_DATA_ROOT` 로 지정 가능.
"""
from __future__ import annotations

import argparse
import os
import random
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics import apppaths  # noqa: E402
from coupang_analytics import settlement_files as SF  # noqa: E402
from coupang_analytics import settlement_jobs as SJ  # noqa: E402
from coupang_analytics import settlement_runlog as RL  # noqa: E402
from coupang_analytics import settlement_wing_ui as UI  # noqa: E402

BASE = Path("output") / "정산"
JOBS = BASE / "_요청기록.json"
FILES = BASE / "파일"
GAP_SEC = (30, 90)
LOG: RL.RunLog = None  # type: ignore[assignment]   # main() 에서 실행 시작 시 생성


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
    from coupang_analytics import appconfig
    from coupang_analytics.credstore import CredStore
    from coupang_analytics.input_list import parse_input_rows, read_ledger_rows
    url = appconfig.get("gsheet/input_url", "")
    if not url:
        raise SystemExit("관리대장 링크(gsheet/input_url)가 설정에 없음 — 앱 설정 탭에서 저장 후 다시 실행")
    _t, rows, strike = read_ledger_rows(url, store=CredStore())
    accts = [a for a in parse_input_rows(rows, strike).accounts if not only or a.account_id in only]
    if only and len(accts) != len(only):
        raise SystemExit(f"관리대장에 없는 계정: {sorted(only - {a.account_id for a in accts})}")
    return accts


def name_of(a) -> str:
    return f"{a.business_name or a.representative or '계정'}-{a.account_id}"


def _profile_in_use(profile: str) -> bool:
    """그 프로필로 떠 있는 Chrome 이 있으면 True(①판매수집 등이 사용 중) — 종료하지 않고 확인만."""
    ps = ("(Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -and "
          "$_.CommandLine.ToLower().Contains($env:SM_PROFILE.ToLower()) } | Measure-Object).Count")
    env = dict(os.environ, SM_PROFILE=str(Path(profile).resolve()))
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=20,
                       env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.stdout.strip() not in ("", "0")


def _accept_dialog(d) -> None:
    log(f"  [화면 알림] {d.message[:80]} → 확인")
    d.accept()


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
    from coupang_analytics.credstore import CredStore
    from coupang_analytics.pipeline_sales import account_profile
    from coupang_analytics.registry_lock import RegistryLockError, registry_lock
    prof = account_profile(a.account_id)
    if _profile_in_use(prof):
        raise SessionSkip("이 계정 Chrome 이 이미 실행 중(①판매수집 등)")
    pw = CredStore().get_password(a.account_id)
    if not pw:
        raise SessionSkip("저장된 비밀번호 없음 — 앱에서 관리대장을 한 번 불러오세요")
    try:
        with registry_lock(BASE / "_잠금" / f"{a.account_id}.lock", wait_sec=5, on_log=log):
            with WingBrowser(profile_dir=prof, offscreen=hidden) as b:
                _login(b, a, pw, hidden)
                b.page.on("dialog", _accept_dialog)
                yield b
    except RegistryLockError as exc:
        raise SessionSkip("다른 정산 다운로드가 이 계정을 쓰는 중") from exc


def goto(b, url: str, who: str) -> None:
    """화면 이동 + 차단 검사(Access Denied 등). 감지하면 '차단' 기록 후 BlockDetected."""
    b.page.goto(url, wait_until="domcontentloaded", timeout=40000)
    if b._page_blocked():
        LOG.record(who, "차단감지", RL.BLOCK, f"차단 화면 — {b.page.url[:120]}")
        raise BlockDetected(f"차단 화면 감지: {b.page.url[:120]}")


# ── 화면 → 정산 일정 ──────────────────────────────────────────────
_SOURCES = (("윙", UI.WING_URL, UI.WING_HEADERS, UI.parse_wing_rows),
            ("로켓그로스", UI.RG_URL, UI.RG_HEADERS, UI.parse_rg_rows))


def read_events(b, name: str, start: date, end: date) -> dict:
    """정산일 기준 달 단위로 윙·로켓그로스 정산현황 조회 → {(채널, 유형, 기간): (채널, 조회구간, 일정, 줄)}.
    조회 구간마다·정산 일정마다 처리기록을 남긴다(날짜별 정상/비정상 분석)."""
    found: dict = {}
    for ch, url, heads, parse in _SOURCES:
        for ws, we in UI.month_windows(start, end):
            goto(b, url, name)
            UI.set_period(b.page, ws, we)
            _ti, rows = UI.read_table(b.page, heads)
            evs = parse(rows, name)
            LOG.record(name, "조회", RL.OK, f"표 {len(rows)}줄·정산확정 {len(evs)}건", channel=ch,
                       period=f"{ws}~{we}")
            for ev, ri in evs:
                found.setdefault((ch, ev.kind, ev.period_start, ev.period_end), (ch, (ws, we), ev, ri))
    return found


def _click_request(b, j, found: dict) -> None:
    ch, (ws, we), _ev, _ri = found[(j.channel, j.kind, date.fromisoformat(j.period_start),
                                    date.fromisoformat(j.period_end))]
    goto(b, UI.WING_URL if ch == "윙" else UI.RG_URL, j.account)
    UI.set_period(b.page, ws, we)
    ti, rows = UI.read_table(b.page, UI.WING_HEADERS if ch == "윙" else UI.RG_HEADERS)
    parse = UI.parse_wing_rows if ch == "윙" else UI.parse_rg_rows
    hits = [ri for ev, ri in parse(rows, j.account)
            if (ev.kind, ev.period_start.isoformat(), ev.period_end.isoformat()) == (j.kind, j.period_start,
                                                                                    j.period_end)]
    if not hits:
        raise UI.UiChangedError(f"다시 조회하니 그 정산 줄이 없음: {j.kind} {j.period_start}~{j.period_end}")
    if ch == "윙":
        UI.click_in_row(b.page, ti, hits[0], UI.BTN_WING_REQUEST)
    else:
        UI.click_in_row(b.page, ti, hits[0], UI.BTN_RG_DOWNLOAD)
        UI.choose_menu_item(b.page, j.report)


def _job_fields(j) -> dict:
    return {"channel": j.channel, "kind": f"{j.kind}·{j.report}", "settle_date": j.settle_date,
            "period": f"{j.period_start}~{j.period_end}"}


# ── 명령 ──────────────────────────────────────────────────────────
def cmd_request(a, b, args, jobs: list) -> None:
    name = name_of(a)
    found = read_events(b, name, args.start, args.end)
    events = [v[2] for v in found.values()]
    picked = [j for j in SJ.plan_requests(events, jobs, today=date.today(), now=datetime.now(),
                                          per_account_cap=args.cap) if j.account == name]
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
        try:
            _click_request(b, j, found)
        except UI.UiChangedError as exc:
            LOG.error(name, "요청", exc)
            raise
        SJ.mark_requested(j, datetime.now())
        SJ.save_jobs(JOBS, jobs)
        LOG.record(name, "요청", RL.OK, "다운로드 요청함", **_job_fields(j))


def _arm_download(page, dl_dir: Path) -> None:
    client = page.context.new_cdp_session(page)
    client.send("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(dl_dir.resolve())})


def _fetch_one(b, ti: int, j, row, name: str) -> None:
    from coupang_analytics.collector import _fresh_download_dir, _wait_new_xlsx
    dl = _fresh_download_dir(BASE / "_받는중", log)
    _arm_download(b.page, dl)
    UI.click_in_row(b.page, ti, row.handle, UI.BTN_GET)
    raw = _wait_new_xlsx(dl, 120, log, [], b.page)
    fname = SF.settle_file_name(name, date.fromisoformat(j.settle_date), j.channel, j.kind, j.report,
                                date.fromisoformat(j.period_start), date.fromisoformat(j.period_end))
    SF.scrub_pii(raw, FILES / fname)                       # 구매자명 지운 사본만 보관
    f = SF.load_settle_file(FILES / fname)                 # 내용 확인(로켓그로스 기간 대조 포함)
    raw.unlink()
    j.status, j.file = SJ.ST_DONE, fname
    LOG.record(name, "받기", RL.OK, f"{fname} · 줄 {len(f.rows)} · 정산합 {f.settle_total:,} · 검산경고 "
               f"{len(f.warnings)}", **_job_fields(j))


def cmd_download(a, b, args, jobs: list) -> None:
    name = name_of(a)
    mine = [j for j in jobs if j.account == name]
    for ch, url, heads in (("윙", UI.WING_URL, UI.WING_LIST_HEADERS), ("로켓그로스", UI.RG_URL, UI.RG_LIST_HEADERS)):
        want = [j for j in mine if j.channel == ch and j.status == SJ.ST_REQUESTED]
        if not want:
            continue
        goto(b, url, name)
        UI.click_button(b.page, UI.BTN_LIST)
        ti, rows = UI.read_table(b.page, heads)
        pairs, notes = SJ.match_downloads(UI.parse_list_rows(rows, ch), want)
        for n in notes:
            LOG.record(name, "받기", RL.WAIT, n, channel=ch)
        for j, row in pairs:
            try:
                _fetch_one(b, ti, j, row, name)
            except Exception as exc:                       # 그 파일만 실패 기록 후 다음 파일(무음 아님)
                LOG.error(name, "받기", exc)
            SJ.save_jobs(JOBS, jobs)


def cmd_probe(a, b, args, jobs: list) -> None:
    """화면 구조만 확인 — 표 머리글·기간 입력칸·버튼 글자. 요청·다운로드는 누르지 않음(목록 창 열기만)."""
    name = name_of(a)
    for ch, url, heads, lheads in (("윙", UI.WING_URL, UI.WING_HEADERS, UI.WING_LIST_HEADERS),
                                   ("로켓그로스", UI.RG_URL, UI.RG_HEADERS, UI.RG_LIST_HEADERS)):
        goto(b, url, name)
        b.page.wait_for_load_state("networkidle", timeout=30000)
        log(f"[{ch}] 표 머리글: {b.page.evaluate(UI._HEADS_JS)}")
        log(f"[{ch}] 기간 입력칸: {[f['v'] for f in b.page.evaluate(UI._DATE_INPUTS_JS)]}")
        for t in (UI.BTN_SEARCH, UI.BTN_LIST, UI.BTN_WING_REQUEST if ch == "윙" else UI.BTN_RG_DOWNLOAD):
            log(f"[{ch}] 버튼 '{t}': {b.page.get_by_text(t, exact=True).count()}개")
        try:
            UI.read_table(b.page, heads)
            UI.click_button(b.page, UI.BTN_LIST)
            UI.read_table(b.page, lheads)
            LOG.record(name, "probe", RL.OK, "정산 표·다운로드 목록 표 찾음", channel=ch)
        except UI.UiChangedError as exc:
            LOG.error(name, "probe", exc)


def cmd_stats() -> None:
    from coupang_analytics import settlement_stats as ST
    files = [SF.load_settle_file(p) for p in sorted(FILES.glob("*.xlsx"))]
    res = ST.aggregate(files)
    out = ST.write_stats(BASE / f"정산집계_{datetime.now():%y%m%d_%H%M%S}.xlsx", res, files=files)
    log(f"집계 {len(files)}개 파일 → {out} (경고 {len(res.warnings)}건)")


def _run_accounts(accts, run, args) -> int:
    jobs = SJ.load_jobs(JOBS)
    bad = 0
    for a in accts:
        name = name_of(a)
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


def main() -> int:
    global LOG
    ap = argparse.ArgumentParser(description="쿠팡 정산 파일 배치 다운로드")
    ap.add_argument("command", choices=("probe", "request", "download", "stats"))
    ap.add_argument("--accounts", default="", help="계정ID 쉼표 구분(비우면 관리대장 전체)")
    ap.add_argument("--from", dest="start", type=date.fromisoformat, default=date(2026, 1, 1))
    ap.add_argument("--to", dest="end", type=date.fromisoformat, default=date.today())
    ap.add_argument("--cap", type=int, default=5, help="계정당 하루 요청 상한")
    ap.add_argument("--dry-run", action="store_true", help="요청 대상만 보여 주고 누르지 않음")
    ap.add_argument("--hidden", action="store_true", help="창 숨김(2차인증 필요하면 실패)")
    args = ap.parse_args()
    apppaths.set_workdir()
    LOG = RL.RunLog(BASE)
    log(f"실행 {LOG.run_id} · 명령 {args.command} · 기간 {args.start}~{args.end} · 데이터 폴더 {Path.cwd()}")
    if args.command == "stats":
        cmd_stats()
        return 0
    accts = load_accounts({x.strip() for x in args.accounts.split(",") if x.strip()})
    if args.command == "probe":
        accts = accts[:1]
    run = {"probe": cmd_probe, "request": cmd_request, "download": cmd_download}[args.command]
    rc = _run_accounts(accts, run, args)
    LOG.summary()
    log(f"기록: {LOG.csv} · 오류 추적: {LOG.errors if LOG.errors.exists() else '없음'}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
