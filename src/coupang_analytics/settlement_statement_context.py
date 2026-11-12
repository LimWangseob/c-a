"""위탁정산서 실행 준비 — 입력 폴더·인자 → 한 번 읽는 공통 자료(ctx). T-25 이관(옛 `statement_managed.py` 59~136줄의 모듈 전역 계산
+ `run_contract_window.py` 계약 기간 보강 · 행동 불변). 고정 경로 없음 — 모든 경로는 `StatementArgs` 로 받는다.

입력 폴더(`inputs`) 고정 이름(손 입력·AI 판정표 · 없으면 ❌ 시작 전 중단):
  사업자_대응표.csv · 체험단_보충.json · 쿠팡_별도보상.json · 관리시작달_차이표.xlsx(계약일 AI 판정 D-185) ·
  svc_digital_judge.json(가전 AI 판정 D-161) · ledger.json(관리대장 스냅샷·비밀번호 없음) ·
  관리상품_되찾기_판정.json(이력 없이 지운 로켓그로스 상품 — 위탁자 본인 상품 AI 판정 · settlement_statement_scope ⑤)
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import openpyxl

from coupang_analytics import sales_history, sales_summary
from coupang_analytics import settlement_experience as XP
from coupang_analytics import settlement_files as SF
from coupang_analytics import settlement_ledger as SL
from coupang_analytics import settlement_statement_scope as SCOPE
from coupang_analytics import settlement_statement_source as SRC

MAP_CSV = "사업자_대응표.csv"
REQUIRED = (MAP_CSV, "체험단_보충.json", "쿠팡_별도보상.json", "관리시작달_차이표.xlsx", "svc_digital_judge.json", "ledger.json",
            SCOPE.JUDGE)
DIGITAL_RATES = {5.8, 6.4, 7.8}


@dataclass(frozen=True)
class StatementArgs:
    out: Path               # 출력 폴더
    managed_output: Path    # 관리 상품 기준 output 폴더(쿠팡데이타분석_통계*.xlsx·판매분석_*·_raw 상품조회)
    settle_dir: Path        # output/정산 폴더
    stats: Path             # 정산집계_*.xlsx
    basis: str              # 장부 기준일 YYYY-MM-DD(D-137 ⑤)
    inputs: Path            # 입력 폴더(위 고정 이름)
    issued: str             # 발행일 YYYY-MM-DD(정산서 '발행'·요약 파일 이름)
    settle_only: Path | None = None   # 원장 '정산전용상품' 시트 사본 json(없으면 구글 실시간 읽기)
    supp: Path | None = None          # 보충 조회 폴더(옛 기준일 조회 방식 · 보통 없음)
    snap: Path | None = None          # 같은 시각대 조회 스냅샷 폴더(보통 없음)
    account_history: Path | None = None   # 원장 '계정이력' 시트 사본 json(없으면 구글 실시간 · 계약 없는 계정의 관리 시작)


def missing_inputs(inputs: Path) -> list[str]:
    return [n for n in REQUIRED if not (inputs / n).is_file()]


def _settle_only_rows(rows: list) -> dict:
    out: dict = defaultdict(dict)
    for r in rows[1:]:
        r = list(r) + [""] * 5
        if r[0] and r[2]:
            out[str(r[0]).strip()][str(r[2]).strip()] = str(r[4]).strip()
    return out


def settle_only_sheet(snapshot: Path | None) -> tuple[dict, str]:
    """원장 '정산전용상품' 시트 → {계정ID: {등록상품ID: 구분}}. 못 읽으면 ({}, 사유) — 그 계정들은 '판정 대기'."""
    if snapshot is not None:
        return _settle_only_rows(json.loads(snapshot.read_text(encoding="utf-8"))), ""
    try:
        from coupang_analytics import appconfig, gsheet_api
        rows = gsheet_api.GSheetClient(appconfig.get("registry/url", "")).read_values("정산전용상품")
    except Exception as exc:  # noqa: BLE001 — 시트 없음·권한 = 그 계정들은 '판정 대기'(사유를 정산서 범위 칸에 적음)
        return {}, f"정산전용상품 시트 못 읽음: {exc.__class__.__name__}"
    return _settle_only_rows(rows), ""


def contracts(table: Path) -> dict:
    """{계정ID: 계약일 YYYY-MM-DD 또는 None(맞는 계약 못 찾음)} — 차이 표 6행 머리글 · A=계정ID · F=계약일('-' = 없음)."""
    rows = list(openpyxl.load_workbook(table, read_only=True, data_only=True).active.iter_rows(values_only=True))
    head = rows[5]
    if head[0] != "계정ID" or not str(head[5]).startswith("계약일"):
        raise ValueError(f"계약 대조 표 머리글이 다름: {head[:6]}")
    return {str(r[0]): (None if r[5] in (None, "-") else str(r[5])[:10]) for r in rows[6:] if r[0]}


def unjudged(p: Path, svc_judge: dict) -> set:
    """윙 주문상세의 서비스이용율 칸 → 가전 요율인데 판정표에 없는 등록상품ID."""
    wb = openpyxl.load_workbook(p, read_only=True)
    h, out = None, set()
    for r in wb.worksheets[0].iter_rows(values_only=True):
        if h is None:
            h = {str(c): i for i, c in enumerate(r) if c} if r and "상품 ID" in r and "서비스이용율(%,VAT별도)" in r else None
            continue
        pid = r[h["상품 ID"]]
        try:
            rate = round(float(r[h["서비스이용율(%,VAT별도)"]] or 0), 1)
        except ValueError:
            continue
        if pid and rate in DIGITAL_RATES and str(pid) not in svc_judge:
            out.add(str(pid))
    wb.close()
    return out


def _settle_files(base: Path, svc_judge: dict) -> tuple[dict, dict]:
    """(계정ID → 정산 파일 목록, 계정ID → 판정표에 없는 가전 요율 등록상품)."""
    files: dict = defaultdict(list)
    unj: dict = defaultdict(set)
    for p in sorted((base / "파일").glob("*.xlsx")):
        try:
            f = SF.load_settle_file(p)
        except Exception:  # noqa: BLE001 — 읽는 방법 없는 리포트는 옵션↔상품 대응에 필요 없음
            continue
        files[SRC.aid_of(f.account)].append(f)
        if f.channel == SF.CH_WING:
            unj[SRC.aid_of(f.account)] |= unjudged(p, svc_judge)
    return files, unj


def _accounts(a: StatementArgs, c: SimpleNamespace) -> None:
    """정산집계·장부·미정산 — 계정 전체 숫자."""
    c.st = SRC.read_stats(a.stats)
    c.tot, c.per = SRC.confirmed(c.st["data"])
    c.accts = sorted({r[0] for _, src in SRC.DETAIL for r in c.st["data"][src][1]})
    led_accounts = json.loads((a.inputs / "ledger.json").read_text(encoding="utf-8"))["accounts"]
    c.names = SRC.build_map(c.accts, led_accounts, c.st["stale"], a.inputs / MAP_CSV, a.out / MAP_CSV)
    c.snaps = SL.load_snapshots(a.snap)
    c.led = SL.Ledger(a.settle_dir, a.supp, c.snaps, date.fromisoformat(a.basis))
    c.un, c.aps = SRC.unsettled(a.settle_dir, a.supp, c.accts, c.per, c.led, c.snaps)
    c.rgf = SRC.rg_file_targets(a.settle_dir)


def _managed(a: StatementArgs, c: SimpleNamespace) -> None:
    """관리 상품 기준 — 대장(결과 엑셀 + 날짜별 사본) VID·같은 상품명(D-107)·되찾은 로켓그로스 상품·체험단·원장 정산전용상품."""
    c.ledger = SCOPE.ledger_vids(a.managed_output)
    c.daily, c.periods = sales_history.load_daily(a.managed_output), sales_history.load_periods(a.managed_output)
    c.listings = sales_summary.managed_listings((c.daily, c.periods), c.ledger)
    c.contracts = contracts(a.inputs / "관리시작달_차이표.xlsx")
    c.rg = SCOPE.recover_all(c.ledger, c.listings, (c.daily, c.periods), SCOPE.inventory(a.managed_output), c.contracts,
                             SCOPE.account_history(a.account_history), SCOPE.load_judge(a.inputs / SCOPE.JUDGE))
    c.xrows = XP.load(a.out, None, a.inputs / "체험단_보충.json")
    c.settle_only, c.settle_only_err = settle_only_sheet(a.settle_only)


def load(a: StatementArgs) -> SimpleNamespace:
    """공통 자료를 한 번 읽음(옛 모듈 전역과 같은 순서·같은 값)."""
    c = SimpleNamespace(args=a, base=a.settle_dir, basis=a.basis, issued=a.issued, out=a.out)
    a.out.mkdir(parents=True, exist_ok=True)
    c.extras = SRC.extras(a.inputs / "쿠팡_별도보상.json")
    _accounts(a, c)
    _managed(a, c)
    c.svc_judge = json.loads((a.inputs / "svc_digital_judge.json").read_text(encoding="utf-8"))
    c.files, c.unjudged = _settle_files(a.settle_dir, c.svc_judge)
    return c
