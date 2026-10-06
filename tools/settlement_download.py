"""쿠팡 정산 파일 배치 다운로드(별도 프로그램) — 위탁계정마다 'N일 요청 → N+1일 받기' + 집계.

**사무실에서 실행**(로그인=앱과 같은 반자동: 보이는 창·비번 자동입력·2차인증은 사람·비번 오류는 재시도 없이 건너뜀).

  python tools/settlement_download.py probe   [--accounts ID]   # 첫 실행: 화면 구조만 확인(요청 안 함)
  python tools/settlement_download.py request [--from 2026-01-01] [--cap 5] [--dry-run] [--accounts ID,ID]
  python tools/settlement_download.py download [--accounts ID,ID]                    # 다음날: 완료분 받기
  python tools/settlement_download.py stats                                          # 받은 파일 집계 엑셀

규칙(차단 위험 완화·소유자 2026-10-06): 정산현황 '정산확정' 줄만 · 윙은 월별(최종액) 파일이 나온 달이면 주정산 생략 ·
로켓그로스는 같은 매출 주 1회 · 계정당 하루 요청 상한(--cap) · 요청 사이 30~90초 · 계정 오류면 그 계정 중단,
연속 2계정 실패면 전체 중단. 같은 PC 동시 실행: 그 계정 프로필 Chrome 이 이미 떠 있으면(①판매수집 중) **건너뜀**
(열면 기존 창을 닫아버림)·reap_orphan_chrome 미호출(순위 Chrome 보호). 저장: output/정산/파일/{계정}_{정산일}_….xlsx
(구매자명 칸 삭제본만), 요청 기록 output/정산/_요청기록.json.
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

from coupang_analytics import apppaths, config  # noqa: E402
from coupang_analytics import settlement_files as SF  # noqa: E402
from coupang_analytics import settlement_jobs as SJ  # noqa: E402
from coupang_analytics import settlement_wing_ui as UI  # noqa: E402

BASE = Path("output") / "정산"
JOBS = BASE / "_요청기록.json"
FILES = BASE / "파일"
GAP_SEC = (30, 90)


def log(m: str) -> None:
    print(config.format_log(m), flush=True)


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


class SessionSkip(Exception):
    """이 계정은 이번 실행에서 건너뜀(사용 중·비번 없음·로그인 실패) — 오류 아님."""


def _accept_dialog(d) -> None:
    log(f"  [화면 알림] {d.message[:80]} → 확인")
    d.accept()


@contextmanager
def session(a, hidden: bool):
    """그 계정 로그인 세션(잠금·사용중 확인·로그인 실패 시 SessionSkip)."""
    from coupang_analytics.browser import WingBrowser
    from coupang_analytics.credstore import CredStore
    from coupang_analytics.pipeline_sales import LoginBlocked, LoginCredentialError, _ensure_login, account_profile
    from coupang_analytics.registry_lock import RegistryLockError, registry_lock
    prof = account_profile(a.account_id)
    if _profile_in_use(prof):
        raise SessionSkip("이 계정 Chrome 이 이미 실행 중(①판매수집 등) — 건너뜀")
    pw = CredStore().get_password(a.account_id)
    if not pw:
        raise SessionSkip("저장된 비밀번호 없음 — 앱에서 관리대장을 한 번 불러오세요")
    try:
        with registry_lock(BASE / "_잠금" / f"{a.account_id}.lock", wait_sec=5, on_log=log):
            with WingBrowser(profile_dir=prof, offscreen=hidden) as b:
                try:
                    ok = _ensure_login(b, a, pw, log, login=True, semi=not hidden)
                except (LoginBlocked, LoginCredentialError) as exc:   # 비번 오류=재시도 금지 정책 그대로
                    raise SessionSkip(f"로그인 중단({exc.__class__.__name__}) — 재시도 안 함") from exc
                if not ok:
                    raise SessionSkip("로그인 미완료")
                b.page.on("dialog", _accept_dialog)
                yield b.page
    except RegistryLockError as exc:
        raise SessionSkip("다른 정산 다운로드가 이 계정을 쓰는 중") from exc


# ── 화면 → 정산 일정 ──────────────────────────────────────────────
def read_events(page, name: str, start: date, end: date) -> dict:
    """달 단위로 윙·로켓그로스 정산현황을 조회 → {작업 키 일부: (채널, 조회구간, 표 번호, 줄 번호, 일정)}."""
    found: dict = {}
    for url, heads, parse, ch in ((UI.WING_URL, UI.WING_HEADERS, UI.parse_wing_rows, "윙"),
                                  (UI.RG_URL, UI.RG_HEADERS, UI.parse_rg_rows, "로켓그로스")):
        for ws, we in UI.month_windows(start, end):
            page.goto(url, wait_until="domcontentloaded", timeout=40000)
            UI.set_period(page, ws, we)
            ti, rows = UI.read_table(page, heads)
            for ev, ri in parse(rows, name):
                found.setdefault((ch, ev.kind, ev.period_start, ev.period_end), (ch, (ws, we), ev, ri))
            log(f"  [{ch}] {ws}~{we}: 정산 줄 {len(rows)}개")
    return found


def _click_request(page, j, found: dict) -> None:
    ch, (ws, we), _ev, _ri = found[(j.channel, j.kind, date.fromisoformat(j.period_start),
                                    date.fromisoformat(j.period_end))]
    page.goto(UI.WING_URL if ch == "윙" else UI.RG_URL, wait_until="domcontentloaded", timeout=40000)
    UI.set_period(page, ws, we)
    ti, rows = UI.read_table(page, UI.WING_HEADERS if ch == "윙" else UI.RG_HEADERS)
    parse = UI.parse_wing_rows if ch == "윙" else UI.parse_rg_rows
    hits = [ri for ev, ri in parse(rows, j.account) if (ev.kind, ev.period_start.isoformat(),
                                                         ev.period_end.isoformat()) == (j.kind, j.period_start,
                                                                                         j.period_end)]
    if not hits:
        raise UI.UiChangedError(f"다시 조회하니 그 정산 줄이 없음: {j.kind} {j.period_start}~{j.period_end}")
    if ch == "윙":
        UI.click_in_row(page, ti, hits[0], UI.BTN_WING_REQUEST)
    else:
        UI.click_in_row(page, ti, hits[0], UI.BTN_RG_DOWNLOAD)
        UI.choose_menu_item(page, j.report)


# ── 명령 ──────────────────────────────────────────────────────────
def cmd_request(a, page, args, jobs: list) -> int:
    name = name_of(a)
    found = read_events(page, name, args.start, date.today())
    events = [v[2] for v in found.values()]
    picked = [j for j in SJ.plan_requests(events, jobs, today=date.today(), now=datetime.now(),
                                          per_account_cap=args.cap) if j.account == name]
    SJ.save_jobs(JOBS, jobs)
    log(f"  요청 대상 {len(picked)}건(상한 {args.cap})" + (" — 미리보기, 요청 안 함" if args.dry_run else ""))
    for k, j in enumerate(picked):
        log(f"   · {j.channel} {j.kind} {j.report} {j.period_start}~{j.period_end} (정산일 {j.settle_date})")
        if args.dry_run:
            continue
        if k:
            time.sleep(random.uniform(*GAP_SEC))
        _click_request(page, j, found)
        SJ.mark_requested(j, datetime.now())
        SJ.save_jobs(JOBS, jobs)
    return len(picked)


def _arm_download(page, dl_dir: Path) -> None:
    client = page.context.new_cdp_session(page)
    client.send("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(dl_dir.resolve())})


def cmd_download(a, page, args, jobs: list) -> int:
    from coupang_analytics.collector import _fresh_download_dir, _wait_new_xlsx
    name, got = name_of(a), 0
    mine = [j for j in jobs if j.account == name]
    for ch, url, heads in (("윙", UI.WING_URL, UI.WING_LIST_HEADERS), ("로켓그로스", UI.RG_URL, UI.RG_LIST_HEADERS)):
        want = [j for j in mine if j.channel == ch and j.status == SJ.ST_REQUESTED]
        if not want:
            continue
        page.goto(url, wait_until="domcontentloaded", timeout=40000)
        UI.click_button(page, UI.BTN_LIST)
        ti, rows = UI.read_table(page, heads)
        pairs, notes = SJ.match_downloads(UI.parse_list_rows(rows, ch), want)
        for n in notes:
            log(f"   · {n}")
        for j, row in pairs:
            dl = _fresh_download_dir(BASE / "_받는중", log)
            _arm_download(page, dl)
            UI.click_in_row(page, ti, row.handle, UI.BTN_GET)
            raw = _wait_new_xlsx(dl, 120, log, [], page)
            fname = SF.settle_file_name(name, date.fromisoformat(j.settle_date), j.channel, j.kind, j.report,
                                        date.fromisoformat(j.period_start), date.fromisoformat(j.period_end))
            SF.scrub_pii(raw, FILES / fname)                       # 구매자명 지운 사본만 보관
            SF.load_settle_file(FILES / fname)                     # 내용 확인(로켓그로스 기간 대조 포함)
            raw.unlink()
            j.status, j.file = SJ.ST_DONE, fname
            SJ.save_jobs(JOBS, jobs)
            got += 1
            log(f"   ✔ {fname}")
    return got


def cmd_probe(a, page, args, jobs: list) -> int:
    """화면 구조만 확인 — 표 머리글·기간 입력칸·버튼 글자. 요청·다운로드는 누르지 않음(목록 창 열기만)."""
    for ch, url, heads, lheads in (("윙", UI.WING_URL, UI.WING_HEADERS, UI.WING_LIST_HEADERS),
                                   ("로켓그로스", UI.RG_URL, UI.RG_HEADERS, UI.RG_LIST_HEADERS)):
        page.goto(url, wait_until="domcontentloaded", timeout=40000)
        page.wait_for_load_state("networkidle", timeout=30000)
        log(f"[{ch}] 표 머리글: {page.evaluate(UI._HEADS_JS)}")
        log(f"[{ch}] 기간 입력칸: {[f['v'] for f in page.evaluate(UI._DATE_INPUTS_JS)]}")
        for t in (UI.BTN_SEARCH, UI.BTN_LIST, UI.BTN_WING_REQUEST if ch == "윙" else UI.BTN_RG_DOWNLOAD):
            log(f"[{ch}] 버튼 '{t}': {page.get_by_text(t, exact=True).count()}개")
        try:
            UI.read_table(page, heads)
            log(f"[{ch}] 정산 표 찾음 ✔")
            UI.click_button(page, UI.BTN_LIST)
            UI.read_table(page, lheads)
            log(f"[{ch}] 다운로드 목록 표 찾음 ✔")
        except UI.UiChangedError as exc:
            log(f"[{ch}] ✖ {exc}")
    return 0


def cmd_stats() -> None:
    from coupang_analytics import settlement_stats as ST
    files = [SF.load_settle_file(p) for p in sorted(FILES.glob("*.xlsx"))]
    res = ST.aggregate(files)
    out = ST.write_stats(BASE / f"정산집계_{datetime.now():%y%m%d_%H%M%S}.xlsx", res, files=files)
    log(f"집계 {len(files)}개 파일 → {out} (경고 {len(res.warnings)}건)")


def main() -> int:
    ap = argparse.ArgumentParser(description="쿠팡 정산 파일 배치 다운로드")
    ap.add_argument("command", choices=("probe", "request", "download", "stats"))
    ap.add_argument("--accounts", default="", help="계정ID 쉼표 구분(비우면 관리대장 전체)")
    ap.add_argument("--from", dest="start", type=date.fromisoformat, default=date(2026, 1, 1))
    ap.add_argument("--cap", type=int, default=5, help="계정당 하루 요청 상한")
    ap.add_argument("--dry-run", action="store_true", help="요청 대상만 보여 주고 누르지 않음")
    ap.add_argument("--hidden", action="store_true", help="창 숨김(2차인증 필요하면 실패)")
    args = ap.parse_args()
    apppaths.set_workdir()
    if args.command == "stats":
        cmd_stats()
        return 0
    accts = load_accounts({x.strip() for x in args.accounts.split(",") if x.strip()})
    if args.command == "probe":
        accts = accts[:1]
    run = {"probe": cmd_probe, "request": cmd_request, "download": cmd_download}[args.command]
    jobs = SJ.load_jobs(JOBS)
    fails = 0
    for a in accts:
        log(f"== {name_of(a)} {args.command} ==")
        try:
            with session(a, args.hidden) as page:
                run(a, page, args, jobs)
            fails = 0
        except SessionSkip as exc:
            log(f"  건너뜀: {exc}")
        except Exception as exc:                                  # 그 계정만 중단(무음 아님)·연속 실패면 전체 중단
            fails += 1
            log(f"  ✖ {exc.__class__.__name__}: {str(exc)[:200]}")
            if fails >= 2:
                log("연속 2계정 실패 — 전체 중단(화면 변경·차단 의심, probe 로 확인)")
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
