"""정산서가 읽는 원본 파일의 '읽은 값' — 한 파일에서만 나오는 값(판정표·계약·산식 없음).
결과 엑셀(관리 VID) = `settlement_statement_scope.ledger_vids` · 물류비 리포트 = `settlement_statement_cfs.read_costs` · 저장·재사용 = `settlement_read_store`(D-419 ①)."""
from __future__ import annotations

from pathlib import Path

import openpyxl

from coupang_analytics import settlement_files as SF
from coupang_analytics import settlement_read_store as STORE

_BASE = ("settlement_read_files", "settlement_files")


# ── 정산 파일 ──
def settle_file(p: Path) -> SF.SettleFile:
    """정산 파일 1개(이름 규칙 → 계정·기간 · 읽는 방법 없는 리포트 = 예외 그대로)."""
    return STORE.read("정산파일", p, SF.load_settle_file, _BASE)


def _wing_rates(p: Path) -> list:
    """윙 주문상세 → [(등록상품ID, 서비스이용율(소수 1자리))] 서로 다른 짝."""
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
        if pid:
            out.add((str(pid), rate))
    wb.close()
    return sorted(out)


def wing_rates(p: Path) -> list:
    return STORE.read("윙요율", p, _wing_rates, _BASE)


# ── 광고·밀크런 ──
def xlsx_rows(p: Path) -> list:
    wb = openpyxl.load_workbook(p, read_only=True)
    try:
        rows = list(wb.active.iter_rows(values_only=True))
    finally:
        wb.close()                                # 안 닫으면 원본 파일이 잠긴 채 남음(3.12 실측)
    if not rows:
        return []
    h = [str(x or "").strip() for x in rows[0]]
    return [dict(zip(h, r)) for r in rows[1:] if r and any(x is not None for x in r)]


def _ad_rows(p: Path) -> list:
    return [(r.get("날짜"), r.get("캠페인 ID"), r.get("광고집행 옵션ID"), r.get("광고비"))
            for r in xlsx_rows(p) if r.get("날짜") and r.get("캠페인 ID")]


def ad_rows(p: Path) -> list:
    """매출성장광고 보고서 → [(날짜, 캠페인 ID, 광고집행 옵션ID, 광고비)] 칸 값 그대로(쓰는 4칸만)."""
    return STORE.read("광고", p, _ad_rows, _BASE)


def _milk_rows(p: Path) -> list:
    return [(str(r.get("밀크런번호")), r.get("총 합계금액"), r.get("취소수수료")) for r in xlsx_rows(p) if r.get("밀크런번호")]


def milk_rows(p: Path) -> list:
    """밀크런 엑셀 → [(밀크런번호, 총 합계금액, 취소수수료)] 칸 값 그대로(금액 = 글자일 수 있음)."""
    return STORE.read("밀크런", p, _milk_rows, _BASE)


# ── 로켓그로스 비용 리포트 ──
def _comp_lines(p: Path) -> list:
    m = SF.parse_file_name(p.name)
    return SF.rg_cost_lines(SF.read_sheets(p), m["account"], m["period_end"])


def comp_lines(p: Path) -> list:
    """재고 손실 보상 리포트 → [CostLine](계정 = 파일 이름의 계정)."""
    return STORE.read("재고보상", p, _comp_lines, _BASE)
