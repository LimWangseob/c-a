"""노출·방문자 아침 보충(D-374 · 소유자 2026-11-20 'B. 아침에 한 번 더') — 매일 08:00 계정마다 다시 로그인해 **어제(D-1) 하루의
노출(`totalPageViews`)·방문자(`totalUniqueVisitor`)만** 다시 받아 마스터·그날 스냅샷·결과 구글시트의 어제 칸에서 그 두 줄만 덮어쓴다.

왜: 판매는 거의 실시간인데 노출·방문자는 쿠팡이 하루 한 번(화면 '어제 오후 11:59 업데이트') 넣어 00:10 무인 ① 때는 0 일 수 있다
(실측 `output\\_분석_261120_판매실시간\\확인결과.md`). 판매·순위·재고·판매가·판매상태 칸은 건드리지 않는다(D-362 '다시 받기 없음'의
예외는 이 두 줄뿐).

언제·누가: 앱 1분 타이머(ui/app_qt `_morning_tick` · 06:00 계약자 현황과 같은 방식). 무인 앱(00:10 `--auto`)은 ①②③ 뒤 이 단계가
그날 남아 있으면 08:00 까지 기다렸다가 끝내고 종료한다. 시각 = 이 파일 `MORNING_AT` 한 곳.

겹침 막기(한 번에 한 브라우저):
- 파이프라인 잠금(`output/_잠금/파이프라인.lock` · 기다리지 않음) — ①②③·날짜 지정·순위 탭·다른 창 실행이 돌면 시작 안 함(끝나면 다음
  타이머에서) · 쥐고 있는 동안 셀독전환 로그인도 새로 시작 안 함(transfer_login.BUSY_LOCKS).
- 정산과는 계정마다: 정산과 같은 계정 잠금(`output/정산/_잠금/{계정ID}.lock`)을 쥔 뒤 그 계정 Chrome 이 꺼질 때까지 기다리고 연다.
  정산이 그 계정을 쓰는 중이면 그 바퀴 맨 뒤로 미루고, 그래도 쓰는 중이면 `BUSY_WAIT_SEC` 까지 기다림(넘으면 그 번 실패).
  정산은 잠금을 못 얻으면 그 계정을 오류로 세지 않고 다음 바퀴에 다시 한다(정산 쪽 기존 동작 · 코드 변경 없음).

실패: 계정마다 최대 3번(처음 + 다시 2번 · D-373 과 같은 수 · 바퀴 사이 `RETRY_GAP_SEC`) · 비밀번호 거부·2차 인증·계정 정지 = 다시 안 함
(24시간 규칙 D-123 · D-373 과 같음) · 끝내 실패한 계정 = 그 칸 00:10 값 그대로 + '노출·방문자 아침 보충 실패' 줄(대신 채우지 않음).
아침 값도 노출·방문 0 인데 그날 판매가 있는 계정 = ⚠ 줄(측정용 · 값은 그대로 씀).
대상: 이번 회차 ① 이 어제 칸을 받은 계정(`_수집스탬프`)만 · 날짜 지정으로 채운 다른 칸은 대상 아님.
"""
from __future__ import annotations

import json
import random
import time
from contextlib import contextmanager
from datetime import date, datetime, time as dtime
from pathlib import Path

from . import config

TAG = "[노출·방문자 아침 보충]"
MORNING_AT = dtime(8, 0)    # 시작 시각(소유자 11-20 B안 · 시각 = 통제 세션 제안 08:00 · 바꾸려면 여기만)
LAST_START = dtime(23, 0)   # 이 시각 뒤엔 그날 새로 시작 안 함(정산 회차 끝 24:00 · 다음 00:10 무인 전에 끝내기)
MAX_TRIES = 3               # 계정마다 시도 수(처음 + 다시 2번 · D-373 과 같은 수)
RETRY_GAP_SEC = 600         # 실패 계정 다시 시도 전 쉼(바퀴 사이 10분)
BUSY_WAIT_SEC = 1800        # 정산이 그 계정을 쓰는 중일 때 기다리는 최대 시간(넘으면 그 번 실패)
STATE_DIR = "노출방문_아침보충"   # output/ 아래 — 날짜별 기록(무엇을 몇 번 시도·어느 칸 바꿨는지) + 그날 실행 표시
RUN_MARK = "_실행기록.json"
FAIL = "노출·방문자 아침 보충 실패"


class LoginFailed(Exception):
    """로그인 못 함. retry=False = 다시 시도 안 함(비밀번호 거부·2차 인증·계정 정지)."""

    def __init__(self, msg: str, retry: bool = True):
        super().__init__(msg)
        self.retry = retry


class AccountBusy(Exception):
    """정산 등 다른 실행이 그 계정 잠금·Chrome 을 쓰는 중."""


def target_day(now: datetime) -> date:
    """보충할 칸 = 실행일 − 1(어제 · D-368·D-372 날짜 칸 규칙 한 곳 `run_day_column`)."""
    from .pipeline_paths import run_day_column
    return run_day_column(now.date())


def _mark_path(out_dir) -> Path:
    return Path(out_dir) / STATE_DIR / RUN_MARK


def last_day(out_dir="output") -> str:
    p = _mark_path(out_dir)
    try:
        return str(json.loads(p.read_text(encoding="utf-8")).get("날짜") or "") if p.is_file() else ""
    except (OSError, ValueError, AttributeError):
        return "!"


def owed_today(now: datetime, out_dir="output") -> bool:
    """오늘 아직 안 했고 시작할 수 있는 시간이 남았나(무인 앱이 ①②③ 뒤 종료를 미룰지)."""
    return now.time() < LAST_START and last_day(out_dir) != now.date().isoformat()


def daily_due(now: datetime, out_dir="output") -> bool:
    """08:00 ~ 23:00 이고 오늘 실행 기록이 없으면 True(08:00 에 앱이 꺼져 있었으면 켠 뒤 그날 한 번)."""
    return MORNING_AT <= now.time() and owed_today(now, out_dir)


def wait_reason(now: datetime, out_dir="output") -> str:
    """미룰 이유 · 아니면 ''. ① 이 도는 중 · 이번 회차(00:10~) ① 완료 기록 없음(보충할 어제 칸이 아직 없음) — 계약자 현황과 같은 판정."""
    from .pipeline_paths import _progress_path
    from .settlement_watch import cycle_window, sales_in_progress
    busy, _ = sales_in_progress(_progress_path(out_dir), now=now)
    if busy:
        return "① 판매수집이 아직 도는 중 — 끝나면 1분 안에 시작"
    if not sales_done(now, out_dir):
        return f"이번 회차({cycle_window(now)[0]:%m-%d %H:%M}~) ① 판매수집 완료 기록 없음 — ① 이 끝나면 1분 안에 시작"
    return ""


def sales_done(now: datetime, out_dir="output") -> bool:
    """이번 회차(00:10~) ① 판매수집이 끝났나(`_실행단계.json` · 정산·계약자 현황과 같은 판정)."""
    from .pipeline_paths import _run_stage_path
    from .settlement_watch import cycle_window, read_marker, sales_done_in_cycle
    return sales_done_in_cycle(read_marker(_run_stage_path(out_dir))[0], cycle_window(now)[0])


def targets(wb, accounts, label: str) -> list:
    """보충 대상 = 이번 ① 이 그 칸(label)을 받은 계정(스탬프) 중 결과 시트에 그 칸이 있는 계정 · 대장 순서."""
    out, seen = [], set()
    for a in accounts:
        if a.account_id in seen:   # 대장에 같은 계정이 여러 줄이어도 한 번
            continue
        seen.add(a.account_id)
        if wb.has_sales(a.account_id, label) and _sheets(wb, a.account_id, label):
            out.append(a)
    return out


def _sheets(wb, account_id: str, label: str) -> list[str]:
    return [b for b in wb.account_sheets()
            if account_id in wb.account_ids_of(b) and wb._date_col.get(b, {}).get(label) is not None]


def _cell(wb, biz: str, product: str, metric: str, col: int):
    row = wb._metric_row.get((biz, product, metric))
    return (None, None) if row is None else (row, wb.wb[biz].cell(row, col).value)


def apply(wb, account_id: str, label: str, metrics: dict) -> list[dict]:
    """그 계정 상품 블록의 label 칸 노출·방문자 두 줄만 아침 값으로. 블록 VID 중 아침 응답에 있는 첫 VID 값(D-031 — 합치지 않음 ·
    00:10 `_fill_product_metrics` 와 같은 규칙) · 응답에 없는 블록 = 그대로(0 으로 덮지 않음). 반환 = 바뀐 칸 목록(근거 기록용)."""
    changed = []
    for biz in _sheets(wb, account_id, label):
        col = wb._date_col[biz][label]
        for prod in wb.products_of(biz):
            if wb.product_account_id(biz, prod) not in ("", account_id):
                continue
            vids = wb.product_vids(biz, prod)
            vid = next((v for v in vids if v in metrics), None)
            if vid is None:
                continue
            m = metrics[vid]
            for metric, new in ((config.M_VIEWS, m.views), (config.M_VISITORS, m.visitors)):
                row, old = _cell(wb, biz, prod, metric, col)
                if row is None or old == new:
                    continue
                wb.wb[biz].cell(row, col, new)
                changed.append({"사업자": biz, "상품": prod, "VID": vid, "줄": metric, "전": old, "후": new})
    return changed


@contextmanager
def account_guard(account_id: str, *, lock_dir, in_use, wait_sec: float, clock=time.monotonic, sleep=time.sleep):
    """정산과 같은 계정 잠금을 쥔 채(기다림 wait_sec) 그 계정 Chrome 이 꺼질 때까지 기다림 → 그 안에서만 브라우저를 연다.
    못 얻으면 AccountBusy(아무것도 안 함). 잠금을 쥔 동안 정산은 그 계정을 건너뛰었다가 다음 바퀴에 다시 한다."""
    from .pipeline_sales import account_profile
    from .registry_lock import RegistryLockError, registry_lock
    try:
        with registry_lock(Path(lock_dir) / f"{account_id}.lock", wait_sec=wait_sec):
            end = clock() + wait_sec
            while in_use(account_profile(account_id)):
                if clock() >= end:
                    raise AccountBusy(f"그 계정 Chrome 이 {wait_sec / 60:.0f}분 넘게 켜져 있음(정산 등)")
                sleep(5)
            yield
    except RegistryLockError as exc:
        raise AccountBusy(f"정산이 이 계정을 쓰는 중({wait_sec / 60:.0f}분 기다림)") from exc


def profile_in_use(profile: str) -> bool:
    """그 프로필로 떠 있는 Chrome 이 있나(정산 tools/settlement_download `_profile_in_use` 와 같은 확인 · 끄지 않음)."""
    import os
    import subprocess
    ps = ("(Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -and "
          "$_.CommandLine.ToLower().Contains($env:SM_PROFILE.ToLower()) } | Measure-Object).Count")
    env = dict(os.environ, SM_PROFILE=str(Path(profile).resolve()))
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=20,
                       env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.stdout.strip() not in ("", "0")


def fetch_live(a, day_iso: str, get_password, log) -> tuple[dict, bool]:
    """계정 하나: 보이는 창 로그인(① 과 같은 `_login_with_candidates` · 세션 있으면 재사용) → 판매분석 그 하루 조회만.
    반환 (지표 {VID: OptionMetric}, 새로 로그인했나). 상품조회·재고·원문 보관·판매 기록은 하지 않음."""
    from . import collector
    from .browser import WING_URL, WingBrowser
    from .pipeline_sales import (AccountSuspended, LoginBlocked, LoginCredentialError, _login_with_candidates,
                                 _pw_list, account_profile)
    pws = _pw_list(get_password(a.account_id) if get_password else None)
    with WingBrowser(profile_dir=account_profile(a.account_id), offscreen=False) as b:
        b.goto(WING_URL)
        b.page.wait_for_timeout(1500)
        fresh = not b.authenticated()
        try:
            ok = _login_with_candidates(b, a, pws, log, login=True, semi=True)
        except LoginCredentialError as exc:
            raise LoginFailed("비밀번호 거부(24시간 다시 안 넣음 · D-123)", retry=False) from exc
        except LoginBlocked as exc:
            raise LoginFailed("로그인 차단(Akamai)") from exc
        if not ok:
            code = b.classify_login()[0]
            raise LoginFailed(f"로그인 미완료({code})", retry=code != "otp")
        if b.is_suspended():
            raise LoginFailed("계정 정지(승인 반려)", retry=False) from AccountSuspended(a.account_id)
        return collector.fetch_sales_details(b.page, day_iso, day_iso, log), fresh


class _Run:
    """한 번 실행의 상태(계정별 시도·결과·바뀐 칸)."""

    def __init__(self, accounts, label: str):
        self.left = list(accounts)
        self.tries: dict[str, int] = {}
        self.result: dict[str, dict] = {}
        self.changed: list[dict] = []
        self.label = label
        self.fresh = False

    def fail(self, a, why: str, retry: bool, log) -> None:
        n = self.tries[a.account_id] = self.tries.get(a.account_id, 0) + 1
        final = (not retry) or n >= MAX_TRIES
        self.result[a.account_id] = {"사업자": a.label, "결과": "실패" if final else "다시", "시도": n, "사유": why}
        if final:
            self.left.remove(a)
            log(f"  {TAG} ❌ {FAIL} — {a.label}({a.account_id}) · {n}번 시도 · {why} · {self.label} 칸 노출·방문자 = 00:10 값 그대로")
        else:
            log(f"  {TAG} ↻ {a.label}({a.account_id}) {n}/{MAX_TRIES}번째 실패 · {why} — 다음 바퀴에 다시")


def _one(st: _Run, a, wb, day_iso: str, ctx: dict, log) -> None:
    """계정 하나 처리(잠금 → 로그인 → 하루 조회 → 두 줄 덮어쓰기). 예외는 st.fail 로."""
    if st.fresh:   # 새 로그인 뒤엔 사람 간격(① 과 같은 로그인 몰아치기 방지)
        ctx["sleep"](random.uniform(config.LOGIN_PACE_MIN_SEC, config.LOGIN_PACE_MAX_SEC))
    with account_guard(a.account_id, lock_dir=ctx["lock_dir"], in_use=ctx["in_use"], wait_sec=ctx["busy_wait"],
                       sleep=ctx["sleep"]):
        metrics, st.fresh = ctx["fetch"](a, day_iso, ctx["get_password"], log)
    ch = apply(wb, a.account_id, st.label, metrics)
    st.changed += ch
    st.left.remove(a)
    views = sum(m.views for m in metrics.values())
    visits = sum(m.visitors for m in metrics.values())
    sales = sum(m.sales for m in metrics.values())
    st.result[a.account_id] = {"사업자": a.label, "결과": "성공", "시도": st.tries.get(a.account_id, 0) + 1,
                               "노출": views, "방문": visits, "판매": sales, "바뀐 칸": len(ch)}
    log(f"  {TAG} ✅ {a.label}({a.account_id}) — 계정 전체 노출 {views}·방문 {visits}·판매 {sales} · 바뀐 칸 {len(ch)}")
    if sales > 0 and views == 0 and visits == 0:
        log(f"  {TAG} ⚠ {a.label}({a.account_id}) 아침 값도 노출·방문 0 인데 판매 {sales} — 쿠팡 집계가 더 늦는 날로 보임(측정용 · 값 그대로)")


def _pass(st: _Run, wb, day_iso: str, ctx: dict, log) -> None:
    """한 바퀴 — 정산이 쓰는 계정은 맨 뒤로 한 번 미룸(그 뒤엔 기다림)."""
    queue, deferred = list(st.left), set()
    while queue:
        a = queue.pop(0)
        busy_wait = 0 if a.account_id not in deferred else ctx["busy_wait_full"]
        try:
            _one(st, a, wb, day_iso, dict(ctx, busy_wait=busy_wait), log)
        except AccountBusy as exc:
            if a.account_id not in deferred:   # 처음 = 기다리지 않고 맨 뒤로 · 두 번째 = BUSY_WAIT_SEC 까지 기다림
                deferred.add(a.account_id)
                queue.append(a)
                log(f"  {TAG} ⏸ {a.label}({a.account_id}) {exc} — 이 바퀴 맨 뒤로")
                continue
            st.fail(a, str(exc), True, log)
        except LoginFailed as exc:
            st.fail(a, str(exc), exc.retry, log)
        except Exception as exc:   # 조회 오류 등 — 그 계정만 실패로 세고 다음 계정(00:10 값 그대로)
            st.fail(a, f"{exc.__class__.__name__}: {str(exc).splitlines()[0][:150] if str(exc) else ''}", True, log)


def _finish(st: _Run, wb, out: Path, now: datetime, gsheet_url, log, push) -> None:
    from .pipeline_paths import _master_path, _snapshot_path
    if st.changed:
        wb.save(_master_path(out))
        wb.save(_snapshot_path(out, now))
        log(f"  {TAG} 마스터·그날 스냅샷 저장 — {st.label} 칸 노출·방문자 {len(st.changed)}칸 바뀜")
        push(wb, gsheet_url, log)
    else:
        log(f"  {TAG} 바뀐 칸 없음 — 마스터·구글시트 그대로")


def _record(out: Path, now: datetime, day_iso: str, st: _Run, note: str) -> None:
    d = out / STATE_DIR
    d.mkdir(parents=True, exist_ok=True)
    rec = {"날짜": now.date().isoformat(), "시각": datetime.now().isoformat(timespec="seconds"), "보충한 날": day_iso,
           "칸": st.label, "메모": note, "계정": st.result, "바뀐 칸": st.changed}
    (d / f"{now.date().isoformat()}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    _mark_path(out).write_text(json.dumps({k: rec[k] for k in ("날짜", "시각", "보충한 날", "메모")}, ensure_ascii=False),
                               encoding="utf-8")


def run_daily(accounts, *, now: datetime, get_password=None, out_dir="output", on_log=print, gsheet_url=None,
              pipe_lock, fetch=fetch_live, in_use=profile_in_use, sleep=time.sleep, push=None,
              lock_dir=None) -> dict | None:
    """그날 한 번. 파이프라인 잠금을 못 얻으면 None(기록 안 남김 → 다음 타이머에 다시). 시작했으면 성공·실패와 상관없이 그날 기록."""
    from .pipeline_paths import _master_path, column_label
    from .registry_lock import RegistryLockError, registry_lock
    from .settlement_store import BASE
    out, log = Path(out_dir), on_log
    try:
        with registry_lock(pipe_lock, wait_sec=0):
            return _run_locked(accounts, now, out, log, gsheet_url, get_password, fetch, in_use, sleep,
                               push, Path(lock_dir) if lock_dir else BASE / "_잠금", _master_path, column_label)
    except RegistryLockError:
        return None


def _run_locked(accounts, now, out, log, gsheet_url, get_password, fetch, in_use, sleep, push, lock_dir,
                master_path, column_label) -> dict:
    from .pipeline_gsheet import push_gsheet
    from .workbook import OutputWorkbook
    day_iso = target_day(now).isoformat()
    st = _Run([], column_label(day_iso))
    note = ""
    try:
        log(f"== {TAG} 시작 — {st.label} 칸(어제 {day_iso}) 노출·방문자만 다시 받음 · 판매·순위 칸 그대로 ==")
        master = master_path(out)
        if not master.exists():
            note = "마스터 없음"
            log(f"  {TAG} ❌ 마스터 없음({master.name}) — 오늘 보충 안 함")
            return st.result
        wb = OutputWorkbook.load(master)
        st.left = targets(wb, accounts, st.label)
        log(f"  {TAG} 대상 {len(st.left)}계정(이번 ① 이 {st.label} 칸을 받은 계정)")
        ctx = {"fetch": fetch, "get_password": get_password, "in_use": in_use, "sleep": sleep, "lock_dir": lock_dir,
               "busy_wait_full": BUSY_WAIT_SEC}
        for n in range(1, MAX_TRIES + 1):
            if not st.left:
                break
            if n > 1:
                log(f"  {TAG} {RETRY_GAP_SEC // 60}분 뒤 {n}번째 바퀴 — 남은 {len(st.left)}계정")
                sleep(RETRY_GAP_SEC)
            _pass(st, wb, day_iso, ctx, log)
        _finish(st, wb, out, now, gsheet_url, log, push or push_gsheet)
        bad = [r for r in st.result.values() if r["결과"] == "실패"]
        note = f"성공 {len(st.result) - len(bad)} · 실패 {len(bad)} · 바뀐 칸 {len(st.changed)}"
        log(f"== {TAG} 끝 — {note} ==")
        return st.result
    finally:
        _record(out, now, day_iso, st, note or "중간에 끝남(오류 — 위 로그)")


__all__ = ["MORNING_AT", "MAX_TRIES", "FAIL", "apply", "daily_due", "owed_today", "run_daily", "sales_done", "targets",
           "wait_reason"]
