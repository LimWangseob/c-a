"""위탁자 정산서 3차 형식(구글시트) — 숫자 만들기: 계정 1개 × 판매 달 1개 → 정산서 자료 dict + 자동 검산. T-38 계획 S2
(샘플 `output\\_샘플_261115_위탁자정산서\\_scripts\\s01_extract.py`·`s03_compute.py` 를 옮김 · 계산식·순서 그대로 · 샘플 뒤 확정 규칙 반영).

- 기존 위탁정산서 계산(`settlement_statement_deduct.Account`)을 같은 프로세스에서 돌려 중간값을 꺼냄(기존 코드 수정 없음 · pkl 없음).
- 판정표 2개(AI·소유자 근거 · D-229 — 계정·상품 조건은 코드에 쓰지 않음): 관리 상품 추가(`관리상품_추가_판정.json`) ·
  상품 이름 묶기(`상품이름_판정.json`). 기본 위치 = 정산서 입력 폴더(`StatementArgs.inputs`). 파일·계정이 없으면 judgments 에 적고 묶지 않음.
- 계산 단계: 1~4 판매(확정 + 정산 예정 D-242 A안) → 5 광고 → 6 창고·배송비 → 7 밀크런 → 8 재고 보상 → 6·7·8 상품 자료 전 금액 나누기 →
  9 계정 공통 → 비중(D-237·D-241·D-271) → 10 별도 입금(D-236) → 상품표·날짜별 입금·어디로 갔나요·검산·판단.
- 공개: `load_judge` · `account_source` · `sale_months` · `build_month` · `failed_checks`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from coupang_analytics import settlement_ledger as SL
from coupang_analytics import settlement_statement_account as AC
from coupang_analytics import settlement_statement_source as SRC
from coupang_analytics.settlement_consignor_month_calc import MonthState, ads, pending_sales, sales, settle_by_channel
from coupang_analytics.settlement_consignor_month_cost import (
    alloc_pending_costs, compensation, expect_values, logistics, milkrun, other_common, separate, shares)
from coupang_analytics.settlement_consignor_month_out import assemble
from coupang_analytics.settlement_statement_deduct import Account

NAMES_FILE = "상품이름_판정.json"
ADDED_FILE = "관리상품_추가_판정.json"
STATS_COST = "로켓그로스 비용 상품별"
DIFF_KEYS = ("차이", "검산(실제 = 정산금액 − 공제 − 판매 조정)")


@dataclass
class ConsignorJudge:
    """판정표 2개 — added = {계정ID: [{등록상품ID, 이름, 근거}]} · names = {계정ID: [{표시 이름, 등록상품ID[], 판정, 근거}]} ·
    notes = 판정표 파일을 못 읽은 사유(정산서 judgments 첫 줄로)."""
    added: dict = field(default_factory=dict)
    names: dict = field(default_factory=dict)
    added_path: str = ""
    names_path: str = ""
    notes: list = field(default_factory=list)


def _table(p: Path | None, what: str, notes: list) -> dict:
    if p is None or not p.is_file():
        notes.append(f"{what} 판정표 파일 없음({p or '경로 없음'}) — 그 판정 없이 계산")
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    return {k: v for k, v in d.items() if not k.startswith("_")}


def load_judge(inputs: Path | None = None, added: Path | None = None, names: Path | None = None) -> ConsignorJudge:
    """판정표 경로 = 인자 → 없으면 입력 폴더(inputs)의 고정 이름. 파일이 없으면 빈 표 + notes(조용히 넘기지 않음)."""
    added = added or (inputs / ADDED_FILE if inputs else None)
    names = names or (inputs / NAMES_FILE if inputs else None)
    notes: list = []
    a = _table(added, "관리 상품 추가", notes)
    n = _table(names, "상품이름(상품명 묶기)", notes)
    return ConsignorJudge(added=a, names=n, added_path=str(added or ""), names_path=str(names or ""), notes=notes)


def _file_rows(files: list) -> list:
    out = []
    for fi, f in enumerate(files):
        for r in f.rows:
            out.append((fi, f.channel, f.kind, str(f.period_start), str(f.period_end), str(r.order_id), str(r.product_id or ""),
                        str(r.option_id or ""), r.product_name, r.qty, r.sales, r.coupon, r.fee, r.settle,
                        str(r.recognized) if r.recognized else "", r.kind, r.gross))
    return out


def _all_vids(a: Account, pa: list, inv: dict) -> set:
    """관리 판정을 미리 구해 둘 VID — 정산 파일·판매분석·광고 보고서·입고·상품조회에 나온 옵션 전부(샘플 s01 과 같은 범위)."""
    allv = set(a.opt2pid) | set(a.vid_name) | {str(int(float(x[2]))) for x in pa if x[2] not in (None, "")}
    allv |= {str(k.get("vendorItemId")) for s in (a.v.get("inbound") or []) for k in s.get("skus") or []}
    for p in inv.values():
        allv |= set(p["types"])
    return allv


def _rows_of(ctx, sheet: str, acct: str) -> list:
    h, rows = ctx.st["data"][sheet]
    return [dict(zip(h, row)) for row in rows if row[0] == acct]


def account_source(ctx, acct: str) -> dict:
    """계정 하나 — 기존 위탁정산서 계산(Account.run)을 돌려 한 달 정산서에 필요한 중간값(샘플 s01 extract 와 같은 내용 + 지급 줄 공제 항목)."""
    a = Account(ctx, acct)
    a.run()
    lines, _dup = AC.payout_lines(ctx.led, a.aid, a.L)
    if len(lines) != len(a.line_info):
        raise ValueError(f"{acct} 지급 줄 수가 기존 계산과 다름: {len(lines)} vs {len(a.line_info)}")
    pa, bill, have = AC.ad_files(ctx.base, acct)
    inv = ctx.inv.get(a.aid) or {}
    return {
        "acct": acct, "aid": a.aid, "info": ctx.names.get(acct), "cdate": a.cdate, "base": str(ctx.base), "basis": ctx.basis,
        "mpids": set(a.mpids), "is_mv": {v: a.is_mv(v) for v in _all_vids(a, pa, inv)}, "opt2pid": dict(a.opt2pid),
        "files_meta": [(i, f.channel, f.kind, str(f.period_start), str(f.period_end)) for i, f in enumerate(a.files)],
        "file_rows": _file_rows(a.files),
        "lines": [(list(row), dict(r), li[5]) for (row, r), li in zip(lines, a.line_info)],
        "line_info": [(st, ch, ym, pay, rel, dict(parts), list(row)) for st, ch, ym, pay, rel, parts, row in a.line_info],
        "prows": _rows_of(ctx, "상품별 월별", acct), "rg_cost_rows": _rows_of(ctx, STATS_COST, acct),
        "ads": (pa, bill, sorted(have)), "v": a.v, "add": a.add, "periods": ctx.periods.get(a.aid) or {}, "inventory": inv,
        "u": [tuple(x) for x in a.u], "extras": ctx.extras.get(a.aid, []), "L_gen": dict(a.L["gen"]),
        "pur": dict(a.pur), "wconf": {k: tuple(v) for k, v in a.wconf.items()}, "own_judge": ctx.own_judge.get(a.aid, {}),
    }


def sale_months(src: dict) -> list[str]:
    """계정의 판매 달(YYYY-MM) — 정산집계 '상품별 월별' 판매·정산 금액이 있는 달 + 정산 예정(쿠팡 정산 줄) 판매가 있는 달 ·
    2025 판매 달 = 정산 밖(D-328 · settlement_ledger.sold_2025)."""
    ms = {str(p["월(매출인식)"])[:7] for p in src["prows"]
          if (p["윙 판매액"] or 0) or (p["로켓그로스 매출금액"] or 0) or (p["쿠팡 정산금액 합계(부가비용 차감 전)"] or 0)}
    ms |= {x[1] for x in src["u"] if len(str(x[1])) == 7 and (x[2] or x[3])}
    return sorted(m for m in ms if not SL.sold_2025(m))


def _resolve(ctx, account) -> dict:
    if isinstance(account, dict):
        return account
    hit = [a for a in ctx.accts if a == account or SRC.aid_of(a) == account]
    if len(hit) != 1:
        raise ValueError(f"계정을 정산집계에서 하나로 못 찾음: {account} → {hit}")
    return account_source(ctx, hit[0])


def build_month(ctx, account, month: str, judge: ConsignorJudge) -> dict:
    """계정 1개 × 판매 달 1개 → 정산서 자료 dict(키 = 샘플 data_*.json 과 같음).
    account = 계정 이름('이름-사업자-계정ID')·계정ID 또는 `account_source()` 결과(여러 달을 부를 때 한 번만 계산) · ctx = 정산서 공통 자료
    (`settlement_statement_context.load` · account 가 source 면 None 가능)."""
    st = MonthState(_resolve(ctx, account), month, judge)
    sales(st)
    settle_by_channel(st)
    pending_sales(st)
    ads(st)
    logistics(st)
    milkrun(st)
    compensation(st)
    alloc_pending_costs(st)
    other_common(st)
    expect_values(st)
    shares(st)
    separate(st)
    return assemble(st)


def failed_checks(data: dict) -> list[dict]:
    """자동 검산 중 차이가 1원 이상인 항목 — 비면 통과(시트 쓰기 전 입구에서 확인)."""
    out = []
    for c in data["checks"]:
        dv = next((c[k] for k in DIFF_KEYS if k in c), 0)
        if isinstance(dv, (int, float)) and abs(dv) >= 1:
            out.append(c)
    return out
