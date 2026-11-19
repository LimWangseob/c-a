"""셀독 계약자별 상품 현황 단계 — ① 판매수집 끝·② 전, 로그인 없음(D-358 ⑥ · 설계안 4절 · T-132).

run_stage = 관리대장 계정 → 사업자 묶음 → 계정마다 저장 자료(contractor_sheet) → 판정 3단(규칙 → AI · 판정표 덧붙임) →
10개 규칙 → `output/계약자별상품현황/셀독_계약자별상품현황_yymmdd.xlsx`(매일 새 파일 · 같은 날 다시 = 그날 파일 교체) →
구글시트(설정 `contractor/url` · 없으면 ⚠ 생략 · 실패 = ❌ 로그 후 계속).

- 로그인 실패·자료 없는 계정 = 옛 값을 쓰지 않고 요약 사업자 이름 옆에 '(로그인 실패)'·'(오늘 자료 없음)'(D-358 ⑦).
- 이 단계의 실패는 ①②③을 멈추지 않는다 — ❌ 줄(실행 결과 종합의 오류 현황에 잡힘)로 남기고 다음 단계로.
- 날짜 지정 실행은 만들지 않음(7일 기간이 그 날짜 기준이 되어 그날 파일을 다른 기간으로 바꿔 쓰게 됨).
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from . import contractor_sheet as CS
from . import contractor_sheet_judge as CJ

TAG = "[계약자별 현황]"


def _ledger_names(acct) -> list[str]:
    return list(dict.fromkeys(" ".join(str(p.ledger_text or p.name).split()) for p in acct.products if p.name))


def _login_reasons(out_dir, run_day: date, log) -> dict[str, str]:
    from . import login_today
    try:
        return login_today.reasons_today(out_dir=out_dir, today=run_day)
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
    week = CS.load_week(out_dir, acct.account_id, days)
    return CS.account_prods(acct.account_id, items, week, CS.rule_basis(items, seldoc)), False


def _mark(acct, n_accs: int, reasons: dict[str, str]) -> str:
    what = "로그인 실패" if acct.account_id in reasons else "오늘 자료 없음"
    return f"({what})" if n_accs == 1 else f"({acct.account_id} {what})"


def build_report(accounts, out_dir, *, run_day: date, date_to: str, ask=None, log=print,
                 now: str | None = None) -> CS.Report:
    """관리대장 계정(input_list.accounts) → 보고서. ask = AI(system, user) → dict(None = AI 판정 생략 · ⚠ 로그)."""
    from .match_anchor import load_match_results, match_result_path
    out = Path(out_dir)
    ctx = _Ctx(out, run_day, CS.week_days(date_to), load_match_results(match_result_path(out)), CS.load_pid_store(out),
               CJ.load(out / CJ.JUDGE_FILE), ask, log, now)
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
        self.reasons: dict[str, str] | None = None
        self.ai_calls = 0

    def seldoc(self, acc: str) -> set[str]:
        from .match_anchor import anchor_path, load_anchors
        got = {v for vids in (self.match.get(acc) or {}).values() for v in vids}               # ① 매칭 결과
        return got | {v for r in load_anchors(acc, anchor_path(self.out)).values() for v in r["vids"]}   # 매칭 고정

    def login_reasons(self) -> dict[str, str]:
        if self.reasons is None:
            self.reasons = _login_reasons(self.out, self.run_day, self.log)
        return self.reasons


def _biz(name: str, accs: list, ctx: _Ctx) -> CS.Biz:
    """사업자 하나 — 계정마다 상품 줄 · 10개 규칙 · ③ AI 판정 · 자료 없는 계정 표시."""
    b = CS.Biz(name, list(dict.fromkeys(a.representative or "-" for a in accs)), [a.account_id for a in accs])
    for a in accs:
        prods, missing = _account(a, ctx.out, ctx.run_day.isoformat(), ctx.days, ctx.seldoc(a.account_id),
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
              client_factory=None, ask=None) -> Path | None:
    """① 끝 단계(pipeline_stages) — 실패는 ❌ 줄로 남기고 None(①②③ 계속). 만든 파일 경로 반환."""
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
                           now=datetime.now().isoformat(timespec="seconds"))
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


__all__ = ["build_report", "push_gsheet", "report_path", "run_stage"]
