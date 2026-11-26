"""노출·방문자 아침 보충(D-374 · 소유자 2026-11-20 'B. 아침에 한 번 더') — 매일 08:00 계정마다 다시 로그인해 **어제(D-1) 하루(+ 7일 안 아직 0 인 칸)의
노출(`totalPageViews`)·방문자(`totalUniqueVisitor`)만** 다시 받아 마스터·그날 스냅샷·결과 구글시트의 그 칸에서 그 두 줄만 덮어쓴다.

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
대상: ① 이 그 칸을 받은 계정(`_수집스탬프`) 중 그 칸 노출·방문이 아직 모두 0(00:10 값 그대로)인 계정 · 날짜 지정으로 채운 칸도
스탬프가 있으면 같은 규칙(값이 이미 있으면 안 건드림).

'아직 없음'과 '진짜 0'(소유자 2026-11-26 "11.25 노출량·방문자 … 원인 파악해서 수정"): 11-26 08:07~08:42 32계정 응답이 모두
판매는 있는데 노출·방문 0(운용 PC 사본 `노출방문_아침보충\\2026-11-26.json` · 쿠팡이 그날 트래픽 집계를 아직 안 넣음)이라 0 이 확정돼
11.25 칸이 계속 0 이었다. 그래서
- 쿠팡이 그 날 집계를 마쳤다는 근거 = 그 날 칸에 노출·방문이 0 이 아닌 계정이 하나라도 있음(이번 응답 또는 마스터).
- 근거가 없으면 그 날 0 을 확정하지 않음 → 같은 날 `RETRY_LATER_SEC` 뒤 다시(23:00 전까지 · 무인 앱은 그때까지 켜 둠) · 다음 날
  회차도 어제 칸과 함께 `LOOKBACK_DAYS` 안의 아직 0 인 칸을 같은 세션에서 다시 받음(이미 0 으로 들어간 지난 칸도 메움).
- 판매 있는데 노출·방문 0 인 계정이 `PROBE` 개 이어지고 노출 있는 계정이 없으면 그 날은 이번 회차 멈춤(남은 계정 로그인 안 함).
- 근거가 있는 날 받은 계정은 '확정'(`_확정.json` · 0 이어도 진짜 0 — 다시 안 받음) · 단 판매 있는데 0 인 계정은 확정 안 함(다음 회차 다시).
"""
from __future__ import annotations

import json
import random
import time
from contextlib import contextmanager
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

from . import config

TAG = "[노출·방문자 아침 보충]"
MORNING_AT = dtime(8, 0)    # 시작 시각(소유자 11-20 B안 · 시각 = 통제 세션 제안 08:00 · 바꾸려면 여기만)
LAST_START = dtime(23, 0)   # 이 시각 뒤엔 그날 새로 시작 안 함(정산 회차 끝 24:00 · 다음 00:10 무인 전에 끝내기)
STOP_NEW = dtime(23, 50)    # 도는 중이어도 이 시각 뒤엔 새 계정 시작 안 함 → 받은 데까지 저장(00:10 무인이 앱을 끝내기 전 · D-374 보완)
MAX_TRIES = 3               # 계정마다 시도 수(처음 + 다시 2번 · D-373 과 같은 수)
RETRY_GAP_SEC = 600         # 실패 계정 다시 시도 전 쉼(바퀴 사이 10분)
BUSY_WAIT_SEC = 1800        # 정산이 그 계정을 쓰는 중일 때 기다리는 최대 시간(넘으면 그 번 실패)
STATE_DIR = "노출방문_아침보충"   # output/ 아래 — 날짜별 기록(무엇을 몇 번 시도·어느 칸 바꿨는지) + 그날 실행 표시
RUN_MARK = "_실행기록.json"
CONFIRM = "_확정.json"      # {보충한 날 ISO: [계정ID]} — 쿠팡 집계가 끝난 날 받은 계정(0 이어도 진짜 0 · 다시 안 받음)
FAIL = "노출·방문자 아침 보충 실패"
MISSED = "노출·방문자 아침 보충 못 함"
NOT_YET = "쿠팡 노출·방문 집계 전"
LOOKBACK_DAYS = 7           # 아직 0 인 칸을 다시 받는 범위(어제 포함 7일 · 그 앞 칸은 안 받음)
RETRY_LATER_SEC = 7200      # 집계 전이면 같은 날 이만큼 뒤 다시(LAST_START 전까지)
PROBE = 3                   # 판매 있는데 노출·방문 0 인 계정이 이만큼 이어지고 노출 있는 계정이 없으면 그 날은 이번 회차 멈춤


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


def _mark(out_dir) -> dict:
    """그날 실행 표시(`_실행기록.json`) · 없으면 {} · 깨졌으면 {'날짜': '!'}(오늘 기록 아님 → 다시 함)."""
    p = _mark_path(out_dir)
    try:
        m = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except (OSError, ValueError):
        return {"날짜": "!"}
    return m if isinstance(m, dict) else {"날짜": "!"}


def last_day(out_dir="output") -> str:
    return str(_mark(out_dir).get("날짜") or "")


def again_at(now: datetime, out_dir="output") -> datetime | None:
    """오늘 기록에 적힌 '같은 날 다시' 시각(쿠팡 집계 전 → RETRY_LATER_SEC 뒤) · 없으면 None."""
    m = _mark(out_dir)
    if m.get("날짜") != now.date().isoformat() or not m.get("다시"):
        return None
    try:
        return datetime.fromisoformat(str(m["다시"]))
    except ValueError:
        return None


def owed_today(now: datetime, out_dir="output") -> bool:
    """오늘 아직 안 했거나 같은 날 다시가 남았고 시작할 수 있는 시간이 남았나(무인 앱이 ①②③ 뒤 종료를 미룰지)."""
    return now.time() < LAST_START and (last_day(out_dir) != now.date().isoformat() or again_at(now, out_dir) is not None)


def daily_due(now: datetime, out_dir="output") -> bool:
    """08:00 ~ 23:00 이고 오늘 실행 기록이 없거나 적힌 '다시' 시각이 지났으면 True(08:00 에 앱이 꺼져 있었으면 켠 뒤 그날 한 번)."""
    at = again_at(now, out_dir)
    return MORNING_AT <= now.time() and owed_today(now, out_dir) and (at is None or now >= at)


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


def pipe_busy(pipe_lock) -> bool:
    """다른 실행(①②③·날짜 지정·다른 창)이 파이프라인 잠금을 쥐고 있나 — 잠깐 쥐어 보고 바로 놓음(관리대장 다시 읽기 전에 확인)."""
    from .registry_lock import RegistryLockError, registry_lock
    try:
        with registry_lock(pipe_lock, wait_sec=0):
            return False
    except RegistryLockError:
        return True


def missed_today(now: datetime, out_dir="output") -> bool:
    """그날 보충 대상이 있었는데(이번 회차 ① 완료) 23:00 을 넘겨 아직 기록이 없음 = '못 함' 줄을 남길 때."""
    return (now >= datetime.combine(now.date(), LAST_START) and last_day(out_dir) != now.date().isoformat()
            and sales_done(now, out_dir))


def give_up(accounts, *, now: datetime, out_dir="output", log, why: str, pipe_lock=None) -> bool:
    """그날 보충을 못 함 — ❌ 한 줄(사유·대상 계정 수 · 어제 칸 = 00:10 값 그대로) + 그날 기록(한 번만 · 값은 대신 채우지 않음).
    pipe_lock 을 주면 다른 실행이 쥐고 있을 때 여기서 남기지 않음(False · 그 실행이 끝에 자기 종합에 남김)."""
    from .registry_lock import RegistryLockError, registry_lock
    if pipe_lock is None:
        return _give_up(accounts, now, Path(out_dir), log, why)
    try:
        with registry_lock(pipe_lock, wait_sec=0):
            return _give_up(accounts, now, Path(out_dir), log, why)
    except RegistryLockError:
        return False


def _give_up(accounts, now: datetime, out: Path, log, why: str) -> bool:
    from .pipeline_paths import _master_path, column_label
    from .workbook import OutputWorkbook
    if last_day(out) == now.date().isoformat():
        return False
    day_iso = target_day(now).isoformat()
    st = _Run([], column_label(day_iso))
    master = _master_path(out)
    n = len(targets(OutputWorkbook.load(master), accounts, st.label)) if master.exists() else 0
    note = f"{MISSED} — {why} · 대상 {n}계정"
    log(f"  {TAG} ❌ {note} · {st.label} 칸 노출·방문자 = 00:10 값 그대로")
    _record(out, now, day_iso, st, note)
    return True


def note_missed(accounts, *, out_dir="output", log, why: str = "①②③ 이 23:00 뒤에 끝남") -> bool:
    """①②③ 끝(run_stages · 파이프라인 잠금 안) — 23:00 이 지나 그날 보충을 못 하게 됐으면 그 실행 종합 오류 현황에 ❌ 한 줄."""
    now = datetime.now()
    return missed_today(now, out_dir) and give_up(accounts, now=now, out_dir=out_dir, log=log, why=why)


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


def _traffic_cells(wb, label: str, account_id: str | None = None):
    """label 칸의 노출·방문 칸 값들(account_id 를 주면 그 계정 상품 블록만 · 다계정 사업자 = 그 계정 소속·미태깅)."""
    for biz in wb.account_sheets():
        col = wb._date_col.get(biz, {}).get(label)
        if col is None or (account_id is not None and account_id not in wb.account_ids_of(biz)):
            continue
        for prod in wb.products_of(biz):
            if account_id is not None and wb.product_account_id(biz, prod) not in ("", account_id):
                continue
            for metric in (config.M_VIEWS, config.M_VISITORS):
                yield _cell(wb, biz, prod, metric, col)[1]


def _has_traffic(wb, label: str, account_id: str | None = None) -> bool:
    """그 칸에 노출·방문이 0 이 아닌 칸이 있나(계정 → 이미 실제 값 · 전체 → 쿠팡이 그 날 집계를 마친 근거)."""
    return any(v not in (None, "", 0) for v in _traffic_cells(wb, label, account_id))


def window(now: datetime) -> dict[str, str]:
    """다시 받을 수 있는 날 {ISO: 칸} — 어제(target_day)부터 LOOKBACK_DAYS 일 · 어제 먼저."""
    from .pipeline_paths import column_label
    y = target_day(now)
    return {(y - timedelta(days=i)).isoformat(): column_label((y - timedelta(days=i)).isoformat())
            for i in range(LOOKBACK_DAYS)}


def _load_confirmed(out: Path, log) -> dict[str, set]:
    p = out / STATE_DIR / CONFIRM
    try:
        return {d: set(v) for d, v in json.loads(p.read_text(encoding="utf-8")).items()} if p.is_file() else {}
    except (OSError, ValueError, AttributeError, TypeError) as exc:
        log(f"  {TAG} ⚠ 확정 기록({p.name})을 못 읽음 — 창 안의 0 칸을 모두 다시 받음 · {exc.__class__.__name__}")
        return {}


def _save_confirmed(out: Path, confirmed: dict[str, set], days) -> None:
    """창(days) 안의 날만 남김(지난 날 기록은 더 쓰지 않음)."""
    d = out / STATE_DIR
    d.mkdir(parents=True, exist_ok=True)
    keep = {k: sorted(v) for k, v in sorted(confirmed.items()) if k in days and v}
    (d / CONFIRM).write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")


def plan(wb, accounts, now: datetime, confirmed: dict[str, set]) -> "_Run":
    """이번에 받을 계정·날 — 창 안의 날 중 ① 이 그 칸을 받았고(스탬프) 그 칸 노출·방문이 아직 모두 0 이며 확정 안 된 계정 · 대장 순서."""
    days = window(now)
    st = _Run([], days[target_day(now).isoformat()], days)
    for a in targets_any(wb, accounts, days.values()):
        need = [d for d, lbl in days.items() if a.account_id not in confirmed.get(d, set())
                and wb.has_sales(a.account_id, lbl) and _sheets(wb, a.account_id, lbl)
                and not _has_traffic(wb, lbl, a.account_id)]
        if need:
            st.left.append(a)
            st.need[a.account_id] = need
    st.traffic = {d for d, lbl in days.items() if _has_traffic(wb, lbl)}
    return st


def targets_any(wb, accounts, labels) -> list:
    """대장에 같은 계정이 여러 줄이어도 한 번 · labels 중 하나라도 결과 시트에 그 칸이 있는 계정 · 대장 순서."""
    out, seen, labels = [], set(), list(labels)
    for a in accounts:
        if a.account_id not in seen and any(_sheets(wb, a.account_id, lbl) for lbl in labels):
            out.append(a)
        seen.add(a.account_id)
    return out


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
                changed.append({"칸": label, "사업자": biz, "상품": prod, "VID": vid, "줄": metric, "전": old, "후": new})
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


def fetch_live(a, days: list[str], get_password, log) -> tuple[dict, bool]:
    """계정 하나: 보이는 창 로그인(① 과 같은 `_login_with_candidates` · 세션 있으면 재사용) → 같은 세션에서 판매분석 그 날들 하루씩 조회만.
    반환 ({날 ISO: {VID: OptionMetric}}, 새로 로그인했나). 상품조회·재고·원문 보관·판매 기록은 하지 않음 · 조회 사이 쉼 = ① 기간 조회와 같음."""
    from . import collector
    from .browser import WING_URL, WingBrowser
    from .pipeline_sales import (_PERIOD_GAP_SEC, AccountSuspended, LoginBlocked, LoginCredentialError,
                                 _login_with_candidates, _pw_list, account_profile)
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
        got = {}
        for i, d in enumerate(days):
            if i:
                time.sleep(random.uniform(*_PERIOD_GAP_SEC))
            got[d] = collector.fetch_sales_details(b.page, d, d, log)
        return got, fresh


class _PastStop(Exception):
    """23:50(STOP_NEW) 지남 — 새 계정 시작 안 함."""


class _Run:
    """한 번 실행의 상태(계정별 시도·결과·바뀐 칸 · 날마다 받은 계정·쿠팡 집계 근거)."""

    def __init__(self, accounts, label: str, days: dict[str, str] | None = None):
        self.left = list(accounts)
        self.tries: dict[str, int] = {}
        self.result: dict[str, dict] = {}
        self.changed: list[dict] = []
        self.label = label                 # 어제 칸(기록·못 함 줄 기준)
        self.days = days or {}             # {날 ISO: 칸} 창
        self.need: dict[str, list[str]] = {}       # {계정ID: 받을 날}
        self.got: dict[str, set] = {}              # {날: 받은 계정ID}
        self.traffic: set[str] = set()             # 노출·방문 0 아닌 칸·응답이 있는 날(쿠팡 집계 끝)
        self.zero_sold: dict[str, list] = {}       # {날: [(계정, 판매)]} 판매 있는데 노출·방문 0
        self.held: dict[str, list] = {}            # {날: [계정]} 집계 전으로 보여 이번에 안 받음
        self.fresh = False
        self.cut = False   # 23:50 넘어 새 계정 시작 멈춤

    def labels(self, account_id: str) -> str:
        return ", ".join(self.days[d] for d in self.need.get(account_id, ())) or self.label

    def stalled(self, day: str) -> bool:
        """그 날 = 노출 있는 계정 없이 판매 있는데 노출·방문 0 인 계정이 PROBE 개 → 이번 회차엔 더 안 받음."""
        return day not in self.traffic and len(self.zero_sold.get(day, ())) >= PROBE

    def fail(self, a, why: str, retry: bool, log) -> None:
        n = self.tries[a.account_id] = self.tries.get(a.account_id, 0) + 1
        final = (not retry) or n >= MAX_TRIES
        self.result[a.account_id] = {"사업자": a.label, "결과": "실패" if final else "다시", "시도": n, "사유": why}
        if final:
            self.left.remove(a)
            log(f"  {TAG} ❌ {FAIL} — {a.label}({a.account_id}) · {n}번 시도 · {why} · {self.labels(a.account_id)} 칸 "
                "노출·방문자 = 00:10 값 그대로")
        else:
            log(f"  {TAG} ↻ {a.label}({a.account_id}) {n}/{MAX_TRIES}번째 실패 · {why} — 다음 바퀴에 다시")

    def hold(self, a, days, log) -> None:
        self.left.remove(a)
        for d in days:
            self.held.setdefault(d, []).append(a)
        self.result[a.account_id] = {"사업자": a.label, "결과": "집계 전", "시도": self.tries.get(a.account_id, 0),
                                     "사유": f"{NOT_YET}으로 보임 — 이번 회차 로그인 안 함"}
        log(f"  {TAG} ⏳ {a.label}({a.account_id}) {self.labels(a.account_id)} 칸 = {NOT_YET}으로 보여 이번엔 로그인 안 함")


def _one(st: _Run, a, wb, ctx: dict, log) -> None:
    """계정 하나 처리(잠금 → 로그인 → 받을 날 하루씩 조회 → 두 줄 덮어쓰기). 예외는 st.fail 로."""
    days = st.need.get(a.account_id, [])
    if all(st.stalled(d) for d in days):
        return st.hold(a, days, log)
    days = [d for d in days if not st.stalled(d)]
    if st.fresh:   # 새 로그인 뒤엔 사람 간격(① 과 같은 로그인 몰아치기 방지)
        ctx["sleep"](random.uniform(config.LOGIN_PACE_MIN_SEC, config.LOGIN_PACE_MAX_SEC))
    left = (ctx["deadline"] - ctx["clock"]()).total_seconds()
    if left <= 0:
        raise _PastStop()
    with account_guard(a.account_id, lock_dir=ctx["lock_dir"], in_use=ctx["in_use"], wait_sec=min(ctx["busy_wait"], left),
                       sleep=ctx["sleep"]):
        got, st.fresh = ctx["fetch"](a, days, ctx["get_password"], log)
    per_day = [(d, got[d]) for d in days]   # 빠진 날 = KeyError → 그 계정 실패(대신 채우지 않음)
    st.left.remove(a)
    sums = [_take(st, a, wb, d, metrics, log) for d, metrics in per_day]
    st.result[a.account_id] = {"사업자": a.label, "결과": "성공", "시도": st.tries.get(a.account_id, 0) + 1,
                               "칸": [st.days[d] for d in days], **{k: sum(s[k] for s in sums) for k in sums[0]}}


def _take(st: _Run, a, wb, day: str, metrics: dict, log) -> dict:
    """한 날 응답 → 칸 덮어쓰기 + 쿠팡 집계 근거(노출 있음 / 판매 있는데 0) 쌓기."""
    label = st.days[day]
    ch = apply(wb, a.account_id, label, metrics)
    st.changed += ch
    st.got.setdefault(day, set()).add(a.account_id)
    views = sum(m.views for m in metrics.values())
    visits = sum(m.visitors for m in metrics.values())
    sales = sum(m.sales for m in metrics.values())
    if views or visits:
        st.traffic.add(day)
    elif sales > 0:
        st.zero_sold.setdefault(day, []).append((a, sales))
    log(f"  {TAG} ✅ {a.label}({a.account_id}) {label} 칸 — 계정 전체 노출 {views}·방문 {visits}·판매 {sales} · 바뀐 칸 {len(ch)}")
    return {"노출": views, "방문": visits, "판매": sales, "바뀐 칸": len(ch)}


def _settle(st: _Run, out: Path, confirmed: dict[str, set], log) -> bool:
    """날마다 판정 — 집계 끝난 날 = 받은 계정 확정(판매 있는데 0 인 계정 빼고 · ⚠ 측정 줄) · 집계 전 = 확정 안 함(⏳ 줄).
    반환 = 어제 칸이 집계 전이라 같은 날 다시 받을 게 남았나(지난 칸만 집계 전이면 False — 다음 날 회차가 창 안에서 다시 ·
    끝내 안 들어오는 날 때문에 날마다 되풀이·무인 앱이 하루 종일 켜져 있지 않게)."""
    pending, yday = False, next(iter(st.days), "")
    for day, label in st.days.items():
        zero = st.zero_sold.get(day, [])
        if day in st.traffic:
            confirmed.setdefault(day, set()).update(st.got.get(day, set()) - {a.account_id for a, _s in zero})
            for a, sales in zero:
                log(f"  {TAG} ⚠ {a.label}({a.account_id}) {label} 아침 값도 노출·방문 0 인데 판매 {sales} — 쿠팡 집계가 더 늦는 "
                    "계정으로 보임(측정용 · 값 그대로 · 확정 안 함 → 다음 회차 다시)")
        elif st.got.get(day) or st.held.get(day):
            pending = pending or day == yday
            log(f"  {TAG} ⏳ {label} 칸 = {NOT_YET}(받은 {len(st.got.get(day, ()))}계정 모두 노출·방문 0 · 그중 판매 있음 "
                f"{len(zero)} · 이번에 안 받은 {len(st.held.get(day, ()))}계정) — 0 으로 확정 안 함 · "
                + ("다시 받음" if day == yday else f"다음 날 {MORNING_AT:%H:%M} 회차가 다시 받음({LOOKBACK_DAYS}일 안)"))
    _save_confirmed(out, confirmed, st.days)
    return pending


def _pass(st: _Run, wb, ctx: dict, log) -> None:
    """한 바퀴 — 정산이 쓰는 계정은 맨 뒤로 한 번 미룸(그 뒤엔 기다림)."""
    queue, deferred = list(st.left), set()
    while queue:
        a = queue.pop(0)
        busy_wait = 0 if a.account_id not in deferred else ctx["busy_wait_full"]
        try:
            if ctx["clock"]() >= ctx["deadline"]:
                raise _PastStop()
            _one(st, a, wb, dict(ctx, busy_wait=busy_wait), log)
        except _PastStop:
            st.cut = True
            return
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


def _passes(st: _Run, wb, ctx: dict, log) -> None:
    """최대 3바퀴 — 다시 시도 쉼이 23:50 을 넘기거나 23:50 이 지나면 멈추고 남은 계정을 ❌ 한 줄로(받은 데까지는 _finish 가 저장)."""
    for n in range(1, MAX_TRIES + 1):
        if not st.left or st.cut:
            break
        if n > 1:
            if ctx["clock"]() + timedelta(seconds=RETRY_GAP_SEC) >= ctx["deadline"]:
                st.cut = True
                break
            log(f"  {TAG} {RETRY_GAP_SEC // 60}분 뒤 {n}번째 바퀴 — 남은 {len(st.left)}계정")
            ctx["sleep"](RETRY_GAP_SEC)
        _pass(st, wb, ctx, log)
    if st.cut and st.left:
        names = ", ".join(f"{a.label}({a.account_id})" for a in st.left)
        for a in st.left:
            st.result[a.account_id] = {"사업자": a.label, "결과": "못 함", "시도": st.tries.get(a.account_id, 0),
                                       "사유": f"{STOP_NEW:%H:%M} 넘음"}
        log(f"  {TAG} ❌ {MISSED}({STOP_NEW:%H:%M} 넘음) — 남은 {len(st.left)}계정: {names} · {st.label} 칸 노출·방문자 = "
            "00:10 값 그대로(받은 계정까지는 저장)")


def _finish(st: _Run, wb, out: Path, now: datetime, gsheet_url, log, push) -> None:
    from .pipeline_paths import _master_path, _snapshot_path
    if st.changed:
        wb.save(_master_path(out))
        wb.save(_snapshot_path(out, now))
        cols = ", ".join(sorted({c["칸"] for c in st.changed}))
        log(f"  {TAG} 마스터·그날 스냅샷 저장 — {cols} 칸 노출·방문자 {len(st.changed)}칸 바뀜")
        push(wb, gsheet_url, log)
    else:
        log(f"  {TAG} 바뀐 칸 없음 — 마스터·구글시트 그대로")


def _record(out: Path, now: datetime, day_iso: str, st: _Run, note: str, again: datetime | None = None) -> None:
    """그날 기록(같은 날 다시 = 앞 기록을 두고 시각 붙은 파일 더) + 실행 표시(again = 같은 날 다시 할 시각 · 없으면 그날 끝)."""
    d = out / STATE_DIR
    d.mkdir(parents=True, exist_ok=True)
    rec = {"날짜": now.date().isoformat(), "시각": datetime.now().isoformat(timespec="seconds"), "보충한 날": day_iso,
           "칸": st.label, "받은 날": sorted(st.got), "메모": note, "계정": st.result, "바뀐 칸": st.changed,
           **({"다시": again.isoformat(timespec="seconds")} if again else {})}
    path = d / f"{now.date().isoformat()}.json"
    if path.exists():
        path = d / f"{now.date().isoformat()}_{now:%H%M%S}.json"
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    _mark_path(out).write_text(json.dumps({k: rec[k] for k in ("날짜", "시각", "보충한 날", "메모", "다시") if k in rec},
                                          ensure_ascii=False), encoding="utf-8")


def _again(pending: bool, clock, log) -> datetime | None:
    """집계 전 칸이 남았으면 같은 날 RETRY_LATER_SEC 뒤(LAST_START 전일 때만 · 아니면 다음 날 회차가 창 안에서 다시)."""
    if not pending:
        return None
    at = clock() + timedelta(seconds=RETRY_LATER_SEC)
    if at.date() == clock().date() and at.time() < LAST_START:
        log(f"  {TAG} ⏳ {at:%H:%M} 에 다시 받음(같은 날 · 무인 앱은 그때까지 켜 둠)")
        return at
    log(f"  {TAG} ⏳ 오늘은 {LAST_START:%H:%M} 전에 다시 할 시간이 없음 — 다음 날 {MORNING_AT:%H:%M} 회차가 "
        f"어제 칸과 함께 다시 받음({LOOKBACK_DAYS}일 안)")
    return None


def run_daily(accounts, *, now: datetime, get_password=None, out_dir="output", on_log=print, gsheet_url=None,
              pipe_lock, fetch=fetch_live, in_use=profile_in_use, sleep=time.sleep, push=None,
              lock_dir=None, clock=None) -> dict | None:
    """그날 한 번. 파이프라인 잠금을 못 얻으면 None(기록 안 남김 → 다음 타이머에 다시). 시작했으면 성공·실패와 상관없이 그날 기록."""
    from .pipeline_paths import _master_path, column_label
    from .registry_lock import RegistryLockError, registry_lock
    from .settlement_store import BASE
    out, log = Path(out_dir), on_log
    try:
        with registry_lock(pipe_lock, wait_sec=0):
            return _run_locked(accounts, now, out, log, gsheet_url, get_password, fetch, in_use, sleep,
                               push, Path(lock_dir) if lock_dir else BASE / "_잠금", _master_path, column_label,
                               clock or datetime.now)
    except RegistryLockError:
        return None


def _run_locked(accounts, now, out, log, gsheet_url, get_password, fetch, in_use, sleep, push, lock_dir,
                master_path, column_label, clock) -> dict:
    from .pipeline_gsheet import push_gsheet
    from .workbook import OutputWorkbook
    day_iso = target_day(now).isoformat()
    st = _Run([], column_label(day_iso))
    note, again = "", None
    try:
        log(f"== {TAG} 시작 — {st.label} 칸(어제 {day_iso})과 {LOOKBACK_DAYS}일 안 아직 0 인 칸의 노출·방문자만 다시 받음 · "
            "판매·순위 칸 그대로 ==")
        master = master_path(out)
        if not master.exists():
            note = "마스터 없음"
            log(f"  {TAG} ❌ 마스터 없음({master.name}) — 오늘 보충 안 함")
            return st.result
        wb = OutputWorkbook.load(master)
        confirmed = _load_confirmed(out, log)
        st = plan(wb, accounts, now, confirmed)
        _log_plan(st, log)
        ctx = {"fetch": fetch, "get_password": get_password, "in_use": in_use, "sleep": sleep, "lock_dir": lock_dir,
               "busy_wait_full": BUSY_WAIT_SEC, "clock": clock, "deadline": datetime.combine(now.date(), STOP_NEW)}
        _passes(st, wb, ctx, log)
        again = _again(_settle(st, out, confirmed, log), clock, log)
        _finish(st, wb, out, now, gsheet_url, log, push or push_gsheet)
        note = _note(st, again)
        log(f"== {TAG} 끝 — {note} ==")
        return st.result
    finally:
        _record(out, now, day_iso, st, note or "중간에 끝남(오류 — 위 로그)", again)


def _log_plan(st: _Run, log) -> None:
    by_day = {lbl: sum(d in need for need in st.need.values()) for d, lbl in st.days.items()}
    days = " · ".join(f"{lbl} {n}" for lbl, n in by_day.items() if n) or "없음"
    log(f"  {TAG} 대상 {len(st.left)}계정(① 이 그 칸을 받았고 노출·방문이 아직 모두 0 · 확정 안 됨) — 칸별 계정 수: {days}")


def _note(st: _Run, again: datetime | None) -> str:
    n = {k: sum(r["결과"] == k for r in st.result.values()) for k in ("성공", "실패", "못 함", "집계 전")}
    return (f"성공 {n['성공']} · 실패 {n['실패']}" + (f" · 못 함({STOP_NEW:%H:%M} 넘음) {n['못 함']}" if n["못 함"] else "")
            + (f" · {NOT_YET} 미룸 {n['집계 전']}" if n["집계 전"] else "") + f" · 바뀐 칸 {len(st.changed)}"
            + (f" · {again:%H:%M} 다시" if again else ""))


__all__ = ["MORNING_AT", "MAX_TRIES", "FAIL", "MISSED", "NOT_YET", "LOOKBACK_DAYS", "RETRY_LATER_SEC", "PROBE", "STOP_NEW",
           "again_at", "apply", "daily_due", "give_up", "missed_today", "note_missed", "owed_today", "pipe_busy", "plan",
           "run_daily", "sales_done", "targets", "wait_reason", "window"]
