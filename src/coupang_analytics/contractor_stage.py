"""셀독 계약자별 상품 현황 — 매일 06:00 앱이 한 번(D-361 ① · ① 판매수집 직후 실행 대체) · 로그인·브라우저 없음(설계안 4절 · T-132).

run_daily = 앱 타이머(ui/app_qt `_contractor_tick`)가 부름 — 06:00 이 지났고 그날 실행 기록이 없을 때 한 번(06:00 에 앱이 꺼져
있었으면 켠 뒤 한 번) · 최근 7일 = 실행일 전날까지(D-361 ②) · 상품·판매가·그로스 재고 = 회차(settlement_watch
`cycle_window` — 그날 06:00 이 든 회차 = 그날 01:30 ① · D-362)부터의 보관본. 06:00 에 ① 이 아직 돌면 끝날 때까지 미룸
(`wait_reason` · 기준일 섞임 방지 · 통제 세션 11-19).

run_stage = 관리대장 계정 → 사업자 묶음 → 계정마다 저장 자료(contractor_sheet) → 판정 3단(규칙 → AI · 판정표 덧붙임) →
10개 규칙 → `output/계약자별상품현황/셀독_계약자별상품현황_yymmdd.xlsx`(매일 새 파일 · 같은 날 다시 = 그날 파일 교체) →
구글시트(설정 `contractor/url` · 없으면 ⚠ 생략 · 실패 = ❌ 로그 후 계속).

- 로그인 실패·자료 없는 계정 = 옛 값을 쓰지 않고 요약 사업자 이름 옆에 '(로그인 실패)'·'(오늘 자료 없음)'(D-358 ⑦).
- 실패는 ❌ 줄로 남기고 앱·①②③을 멈추지 않는다 · 만들지 못한 날도 실행 기록을 남겨 같은 날 되풀이하지 않는다.
- 계정의 어느 날 판매 기록이 아예 없으면 그 날 칸만 공란(contractor_sheet.load_week · D-361 ③).
- 날짜 지정 실행은 만들지 않음(7일 기간이 그 날짜 기준이 되어 그날 파일을 다른 기간으로 바꿔 쓰게 됨).
"""
from __future__ import annotations

import json
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

from . import contractor_sheet as CS
from . import contractor_sheet_judge as CJ

TAG = "[계약자별 현황]"
DAILY_AT = dtime(6, 0)                      # 매일 실행 시각(D-361 ①)
RUN_MARK = "_실행기록.json"                  # output/계약자별상품현황/ 아래 — 그날 실행했는지(같은 날 두 번 안 돎)


def _ledger_names(acct) -> list[str]:
    return list(dict.fromkeys(" ".join(str(p.ledger_text or p.name).split()) for p in acct.products if p.name))


def _login_reasons(out_dir, days: list[date], log) -> dict[str, str]:
    from . import login_today
    try:
        return {k: v for d in days for k, v in login_today.reasons_today(out_dir=out_dir, today=d).items()}
    except (OSError, ValueError) as exc:
        log(f"  {TAG} ⚠ 그날 로그인 기록 읽기 실패 — 자료 없는 계정은 '(오늘 자료 없음)'으로 표시 · {exc.__class__.__name__}")
        return {}


def _account(acct, out_dir, since: str, days, seldoc: set[str], pids: dict, log):
    """한 계정 → (모든 상품 줄, 자료 없음 여부). 판정은 1·2단(규칙)까지."""
    rows = CS.load_product_rows(out_dir, acct.account_id, since)
    if rows is None:
        return [], True
    props, bad = CS.load_inventory(out_dir, acct.account_id, since)
    if bad:
        log(f"  {TAG} ⚠ {acct.account_id}: 재고현황 원문 {bad}쪽 읽기 실패 — 그 쪽 그로스 재고·즉시할인 없음")
    if props is None and any(r.get("registrationType") not in (None, "NORMAL") for r in rows):
        log(f"  {TAG} ⚠ {acct.account_id}: 오늘 재고현황 보관본 없음 — 그로스 재고·즉시할인 '－'")
    if rows and all("productStatus" not in r for r in rows):
        log(f"  {TAG} ⚠ {acct.account_id}: 상품정보에 판매상태 칸 없음(옛 보관본) — 판매상태 '{CS.ST_UNKNOWN}'")
    items = CS.build_items(rows, props or [], pids)
    week, empty = CS.load_week(out_dir, acct.account_id, days)
    return CS.account_prods(acct.account_id, items, week, CS.rule_basis(items, seldoc), empty), False


def _mark(acct, n_accs: int, reasons: dict[str, str]) -> str:
    what = "로그인 실패" if acct.account_id in reasons else "오늘 자료 없음"
    return f"({what})" if n_accs == 1 else f"({acct.account_id} {what})"


def build_report(accounts, out_dir, *, run_day: date, date_to: str, ask=None, log=print,
                 now: str | None = None, data_day: date | None = None) -> CS.Report:
    """관리대장 계정(input_list.accounts) → 보고서. ask = AI(system, user) → dict(None = AI 판정 생략 · ⚠ 로그).
    data_day = 상품·재고 보관본을 이 날짜 이후 것만 씀(None = run_day · 그보다 옛 값은 '자료 없음')."""
    from .match_anchor import load_match_results, match_result_path
    out = Path(out_dir)
    ctx = _Ctx(out, run_day, CS.week_days(date_to), load_match_results(match_result_path(out)), CS.load_pid_store(out),
               CJ.load(out / CJ.JUDGE_FILE), ask, log, now)
    ctx.data_day = data_day or run_day
    groups: dict[str, list] = {}
    for a in accounts:
        groups.setdefault(a.label, []).append(a)
    rep = CS.Report(ctx.days, [_biz(name, accs, ctx) for name, accs in groups.items()])
    rep.ai_calls = ctx.ai_calls
    CJ.save(out / CJ.JUDGE_FILE, ctx.judged)
    return rep


class _Ctx:
    """build_report 한 번의 공통 자료(매칭 결과·상품ID 누적·판정표) — 사업자마다 넘김."""

    def __init__(self, out: Path, run_day: date, days, match: dict, pids: dict, judged: dict, ask, log, now):
        self.out, self.run_day, self.days, self.match, self.pids = out, run_day, days, match, pids
        self.judged, self.ask, self.log, self.now = judged, ask, log, now
        self.data_day = run_day
        self.reasons: dict[str, str] | None = None
        self.ai_calls = 0

    def seldoc(self, acc: str) -> set[str]:
        from .match_anchor import anchor_path, load_anchors
        got = {v for vids in (self.match.get(acc) or {}).values() for v in vids}               # ① 매칭 결과
        return got | {v for r in load_anchors(acc, anchor_path(self.out)).values() for v in r["vids"]}   # 매칭 고정

    def login_reasons(self) -> dict[str, str]:
        if self.reasons is None:
            self.reasons = _login_reasons(self.out, sorted({self.data_day, self.run_day}), self.log)
        return self.reasons


def _biz(name: str, accs: list, ctx: _Ctx) -> CS.Biz:
    """사업자 하나 — 계정마다 상품 줄 · 10개 규칙 · ③ AI 판정 · 자료 없는 계정 표시."""
    b = CS.Biz(name, list(dict.fromkeys(a.representative or "-" for a in accs)), [a.account_id for a in accs])
    for a in accs:
        prods, missing = _account(a, ctx.out, ctx.data_day.isoformat(), ctx.days, ctx.seldoc(a.account_id),
                                  ctx.pids.get(a.account_id) or {}, ctx.log)
        if missing:
            b.marks.append(_mark(a, len(accs), ctx.login_reasons()))
            continue
        show = [p for p in prods if CS.shown(p, len(prods))]
        ctx.ai_calls += CJ.judge_account(a.account_id, show, _ledger_names(a), ctx.judged, ctx.ask, ctx.log, ctx.now)
        b.total += len(prods)
        b.dropped += len(prods) - len(show)
        b.rows += show
    b.rows.sort(key=lambda r: (not r.sel, -r.s7, r.name or ""))
    return b


def report_path(out_dir, run_day: date) -> Path:
    return Path(out_dir) / CS.DIRNAME / f"{CS.FILE_PREFIX}_{run_day:%y%m%d}.xlsx"


def push_gsheet(wb, url: str, log, client_factory=None) -> bool:
    """구글시트 반영 — 주소 없음 = ⚠ 생략 · 실패(403·404·네트워크·주소 형식) = ❌ 로그 후 False(실행 계속)."""
    if not url:
        log(f"  {TAG} ⚠ 구글시트 반영 생략 — 셀독 계약자별 상품 현황 링크 미설정(설정 탭 '구글 시트 연동')")
        return False
    from .gsheet_api import GSheetClient, GSheetError
    from .gsheet_contractor import push_report
    try:
        client = (client_factory or GSheetClient)(url)
        push_report(client, wb, log)
        return True
    except (GSheetError, ValueError) as exc:
        log(f"  {TAG} ❌ 구글시트 반영 실패 — {exc} · PC 파일은 저장됨 · 구글시트는 전날 내용 그대로")
        return False


def run_stage(input_list, *, date_to: str, run_day: date | None = None, ai_key: str | None = None,
              designated: bool = False, out_dir="output", on_log=print, gsheet_url: str | None = None,
              client_factory=None, ask=None, data_day: date | None = None) -> Path | None:
    """만들기 한 번(run_daily 가 부름) — 실패는 ❌ 줄로 남기고 None. 만든 파일 경로 반환."""
    log = on_log
    accounts = list(getattr(input_list, "accounts", None) or [])
    if designated:
        log(f"  {TAG} 날짜 지정 실행 — 만들지 않음(매일 실행 때만)")
        return None
    if not accounts:
        log(f"  {TAG} 관리대장 계정 없음 — 만들지 않음")
        return None
    day = run_day or date.today()
    try:
        if ask is None and ai_key:
            from .product_match_ai import openai_ask
            ask = openai_ask(ai_key)
        rep = build_report(accounts, out_dir, run_day=day, date_to=date_to, ask=ask, log=log,
                           now=datetime.now().isoformat(timespec="seconds"), data_day=data_day)
        if sum(len(b.marks) for b in rep.bizs) >= len(accounts):
            # 소유자 11-20: 새 판 설치 첫날 낮(지난 회차 자료뿐) — 전 사업자 '(오늘 자료 없음)' 빈 표가 구글시트를 덮어씀
            log(f"  {TAG} ❌ 모든 계정 자료 없음({len(accounts)}계정 · 이번 회차 자료 없음) — PC 파일·구글시트 만들지 않음"
                "(구글시트는 전날 내용 그대로)")
            return None
        from .contractor_sheet_xlsx import build_workbook
        wb = build_workbook(rep)
        path = report_path(out_dir, day)
        path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(path)
    except Exception as exc:                 # 이 표 실패가 ②③을 막지 않게 — 원인을 ❌ 줄로 남김
        log(f"  {TAG} ❌ 만들기 실패 — {exc.__class__.__name__}: {str(exc)[:200]}")
        return None
    n_sel = sum(r.sel for b in rep.bizs for r in b.rows)
    n_mark = sum(1 for b in rep.bizs if b.marks)
    log(f"  {TAG} 사업자 {len(rep.bizs)} · 셀독 {n_sel} · 개인 {sum(len(b.rows) for b in rep.bizs) - n_sel} · "
        f"기간 {rep.days[0]:%m.%d}~{rep.days[-1]:%m.%d} · 자료 없음 표시 {n_mark} · AI 호출 {rep.ai_calls} → {path}")
    saved = getattr(log, "saved", None)
    if callable(saved):
        saved("셀독 계약자별 상품 현황", path)
    if gsheet_url is None:
        from . import appconfig
        gsheet_url = appconfig.get(CS.KEY_URL)
    push_gsheet(wb, gsheet_url, log, client_factory)
    return path


def _mark_path(out_dir) -> Path:
    return Path(out_dir) / CS.DIRNAME / RUN_MARK


def _last_day(out_dir) -> str:
    """실행 기록의 날짜 — 없음 = ''. 손상 = '!'(다시 한 번 돌고 새로 씀 · run_daily 가 ⚠ 로그)."""
    p = _mark_path(out_dir)
    if not p.is_file():
        return ""
    try:
        return str(json.loads(p.read_text(encoding="utf-8")).get("날짜") or "")
    except (OSError, ValueError, AttributeError):
        return "!"


def daily_due(now: datetime, out_dir="output") -> bool:
    """06:00 이 지났고 오늘 실행 기록이 없으면 True(06:00 에 앱이 꺼져 있었으면 켠 뒤 그날 한 번)."""
    return now.time() >= DAILY_AT and _last_day(out_dir) != now.date().isoformat()


def wait_reason(now: datetime, out_dir="output") -> str:
    """만들기를 미룰 이유 · 아니면 ''. ① 판매수집이 지금 도는 중(반쯤 받은 날 자료로 만들지 않게 · 정산과 같은 `_진행중.json`
    수정 시각 — ① 이 멈춰 갱신이 끊기면 곧 '') · 이번 회차(01:30~) ① 완료 기록이 없음(정산과 같은 `_실행단계.json` 판정 —
    설치 첫날 낮·01:30 실패·밤새 꺼짐이면 지난 회차 자료뿐이라 전 사업자 '자료 없음' 빈 표가 됨 · 소유자 11-20)."""
    from .pipeline_paths import _progress_path, _run_stage_path
    from .settlement_watch import cycle_window, read_marker, sales_done_in_cycle, sales_in_progress
    busy, _ = sales_in_progress(_progress_path(out_dir), now=now)
    if busy:
        return "① 판매수집이 아직 도는 중 — 끝나면 1분 안에 만듦(그날 자료가 다 모인 뒤)"
    start = cycle_window(now)[0]
    if not sales_done_in_cycle(read_marker(_run_stage_path(out_dir))[0], start):
        return (f"이번 회차({start:%m-%d %H:%M}~) ① 판매수집 완료 기록 없음 — ① 이 끝나면 1분 안에 만듦"
                "(지난 회차 자료로 만들지 않음 · 구글시트는 전날 내용 그대로)")
    return ""


def run_daily(input_list, *, now: datetime, ai_key: str | None = None, out_dir="output", on_log=print,
              gsheet_url: str | None = None, client_factory=None, ask=None) -> Path | None:
    """매일 06:00 실행(D-361) — 최근 7일 = 실행일 전날까지 · 보관본 = 그날 06:00 이 든 회차(그날 01:30 ①)부터(06:00 을 놓쳐 낮에 앱이
    켜진 직후 만들어도 그날 ① 이 아니라 전날 회차 ① 자료 · 그 뒤 것이 있으면 더 새것) · 성공·실패 모두 그날 기록."""
    from .settlement_watch import cycle_window
    if _last_day(out_dir) == "!":
        on_log(f"  {TAG} ⚠ 실행 기록 파일 손상 — 이번 실행 뒤 새로 씀 · {_mark_path(out_dir)}")
    day = now.date()
    on_log(f"  {TAG} 매일 {DAILY_AT:%H:%M} 실행 — {day:%m-%d}")
    path = run_stage(input_list, date_to=(day - timedelta(days=1)).isoformat(), run_day=day, ai_key=ai_key,
                     out_dir=out_dir, on_log=on_log, gsheet_url=gsheet_url, client_factory=client_factory, ask=ask,
                     data_day=cycle_window(datetime.combine(day, DAILY_AT))[0].date())
    mark = _mark_path(out_dir)
    mark.parent.mkdir(parents=True, exist_ok=True)
    mark.write_text(json.dumps({"날짜": day.isoformat(), "시각": datetime.now().isoformat(timespec="seconds"),
                                "파일": str(path) if path else ""}, ensure_ascii=False), encoding="utf-8")
    return path


__all__ = ["DAILY_AT", "build_report", "daily_due", "push_gsheet", "report_path", "run_daily", "run_stage"]
