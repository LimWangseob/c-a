"""결과 통계 시트 날짜 칸 기준 = 판매일(D-368·D-369) — 옛 기준(칸 = 판매일+1) 마스터를 새 판 첫 실행 때 한 번 하루 당김.

판정(두 번 당김 방지 · 추측 금지):
  ① 숨긴 표시 시트 `_날짜기준` B1 = '판매일' → 이미 새 기준(할 일 없음)
  ② 표시 없음 → 판매분석_일별(판매일 키)의 VID 판매수량과 칸 판매량을 대조 — 칸 = 판매일+1 일치가 우세 = 옛 기준(당김) ·
     +0 우세 = 이미 새 기준(구글시트에서 되살린 마스터 등 · 표시만) · 날짜 칸 없음 = 표시만 · 그 밖 = 실행 중단
당김 = 백업 먼저(`output\\백업\\통계마스터_날짜당기기전_*.xlsx`) → 사업자 시트 날짜 머리글 −1(값 그대로) · `_수집스탬프`
2·3열 −1 · `_순위묶음` 시작일·배정일 −1(같은 실행일 = 같은 묶음) → 값·대조 검증 → 표시 → 저장. 옛 판 진행 파일은
지우지 않고 보관 이름으로 바꾸고 이번 실행을 멈춤(그 진행분은 옛 칸 기준이라 이어받으면 칸이 틀림).
통합판매현황·판매분석_일별·계약자 현황·재고 기준일 = 원래 판매일 기준이라 손대지 않음(D-369 정정).
"""
from __future__ import annotations

import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

import openpyxl

from . import config, rank_schedule, sales_history
from .pipeline_paths import _master_path, _partial_path, _progress_path
from .workbook import OutputWorkbook
from .workbook_common import _DATEBASIS_SHEET, _RANKGRP_SHEET, _STAMP_SHEET, _norm, _parse_date

MARK_SHEET = _DATEBASIS_SHEET
BASIS = "판매일"
MIN_VOTES = 20      # 판정에 필요한 최소 일치 건수(판매>0 칸) — 운용 사본 output40 = 510건 중 443건
DOMINANCE = 3       # 한쪽 일치가 다른 쪽의 몇 배 이상이어야 판정(output40 = 443 : 50)
_TAG = "날짜당기기전"


class DateBasisError(RuntimeError):
    """날짜 칸 기준을 판정·당기지 못함 → 그 실행 안 함(D-369 '실패하면 그날 실행 안 함')."""


def has_mark(wb: OutputWorkbook) -> bool:
    return MARK_SHEET in wb.wb.sheetnames and _norm(wb.wb[MARK_SHEET].cell(1, 2).value) == BASIS


def mark(wb: OutputWorkbook, note: str) -> None:
    """숨긴 표시 `_날짜기준`(A1 '날짜 칸 기준' · B1 '판매일' · A2 '기록' · B2 사유) — 이미 있으면 그대로."""
    if has_mark(wb):
        return
    ws = wb.wb[MARK_SHEET] if MARK_SHEET in wb.wb.sheetnames else wb.wb.create_sheet(MARK_SHEET)
    ws.sheet_state = "hidden"
    ws.cell(1, 1, "날짜 칸 기준")
    ws.cell(1, 2, BASIS)
    ws.cell(2, 1, "기록")
    ws.cell(2, 2, f"{datetime.now():%Y-%m-%d %H:%M:%S} · {note}")


def _file_has_mark(path: Path) -> bool:
    xwb = openpyxl.load_workbook(path, read_only=True)
    try:
        if MARK_SHEET not in xwb.sheetnames:
            return False
        row = next(xwb[MARK_SHEET].iter_rows(min_row=1, max_row=1, max_col=2, values_only=True), ())
        return len(row) > 1 and _norm(row[1]) == BASIS
    finally:
        xwb.close()


def _sold_by_vid(wb: OutputWorkbook, biz: str, out_dir, cache: dict) -> dict[str, dict[str, float]]:
    """{VID: {판매일 ISO: 판매수량}} — 그 사업자 계정들의 판매분석_일별(읽기만)."""
    qty: dict[str, dict[str, float]] = {}
    for aid in wb.account_ids_of(biz):
        if aid not in cache:
            cache[aid] = sales_history.load_account(out_dir, aid)
        for day, rec in cache[aid].items():
            for vid, o in (rec.get("옵션") or {}).items():
                q = o.get("판매수량")
                if isinstance(q, (int, float)) and not isinstance(q, bool):
                    qty.setdefault(str(vid), {})[day] = qty.get(str(vid), {}).get(day, 0) + q
    return qty


def _product_votes(ws, row: int, cols: dict, vids: list, qty: dict) -> tuple[int, int]:
    plus1 = zero = 0
    for day in {d for v in vids for d in qty.get(v, {})}:
        q = sum(qty.get(v, {}).get(day, 0) for v in vids)
        if q <= 0:
            continue
        d = date.fromisoformat(day)
        for off in (0, 1):
            c = cols.get((d + timedelta(days=off)).strftime("%m.%d"))
            v = ws.cell(row, c).value if c else None
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v == q:
                plus1, zero = (plus1 + 1, zero) if off else (plus1, zero + 1)
    return plus1, zero


def votes(wb: OutputWorkbook, out_dir) -> tuple[int, int]:
    """(칸 = 판매일+1 일치 수, 칸 = 판매일 일치 수) — 판매 > 0 인 날·VID 있는 블록의 판매량 칸만."""
    plus1 = zero = 0
    cache: dict = {}
    for biz in wb.account_sheets():
        cols = wb._date_col.get(biz) or {}
        if not cols:
            continue
        qty = _sold_by_vid(wb, biz, out_dir, cache)
        for prod in wb.products_of(biz):
            row, vids = wb._metric_row.get((biz, prod, config.M_SALES)), wb.product_vids(biz, prod)
            if row is not None and vids:
                p, z = _product_votes(wb.wb[biz], row, cols, vids, qty)
                plus1, zero = plus1 + p, zero + z
    return plus1, zero


def judge(wb: OutputWorkbook, out_dir) -> tuple[str, int, int]:
    """('marked'|'empty'|'old'|'new'|'unknown', +1 일치, +0 일치)."""
    if has_mark(wb):
        return "marked", 0, 0
    if not any(wb._date_col.get(b) for b in wb.account_sheets()):
        return "empty", 0, 0
    plus1, zero = votes(wb, out_dir)
    if plus1 >= MIN_VOTES and plus1 >= DOMINANCE * zero:
        return "old", plus1, zero
    if zero >= MIN_VOTES and zero >= DOMINANCE * plus1:
        return "new", plus1, zero
    return "unknown", plus1, zero


def _minus1(label) -> str:
    d = _parse_date(label)
    return (d - timedelta(days=1)).strftime("%m.%d") if d else _norm(label)   # 범위 라벨('from~to') = 판매 기간 그대로


def _iso_minus1(value) -> str | None:
    d = _parse_date(value)
    return (d - timedelta(days=1)).isoformat() if d else value


def _shift_sheet(wb: OutputWorkbook, biz: str) -> None:
    cols = wb._date_col.get(biz) or {}
    parsed = {lbl: _parse_date(lbl) for lbl in cols}
    bad = sorted(lbl for lbl, d in parsed.items() if d is None)
    if bad:
        raise DateBasisError(f"❌ 날짜 칸 당기기 못 함 — {biz} 시트에 날짜가 아닌 칸 이름 {bad} (확인 필요)")
    date2cols: dict[date, list[int]] = {}
    for lbl, d in parsed.items():
        date2cols.setdefault(d - timedelta(days=1), []).append(cols[lbl])
    days = sorted(date2cols)
    target = [days[-1] - timedelta(days=i) for i in range((days[-1] - days[0]).days + 1)]   # 최신 왼쪽·연속
    wb._rebuild_date_grid(biz, date2cols, target, set(cols.values()))


def _shift_stamps(wb: OutputWorkbook) -> int:
    if _STAMP_SHEET not in wb.wb.sheetnames:
        return 0
    ws, n = wb.wb[_STAMP_SHEET], 0
    for r in range(2, ws.max_row + 1):
        if _norm(ws.cell(r, 2).value):
            ws.cell(r, 2).value = _minus1(ws.cell(r, 2).value)
            n += 1
        hist = [h for h in _norm(ws.cell(r, 3).value).split(",") if h]
        if hist:
            ws.cell(r, 3).value = ",".join(_minus1(h) for h in hist)
    return n


def _shift_rank_plan(wb: OutputWorkbook) -> None:
    if _RANKGRP_SHEET not in wb.wb.sheetnames:
        return
    ws = wb.wb[_RANKGRP_SHEET]
    for r, c in [(1, 2), (1, 4)] + [(r, c) for r in range(3, ws.max_row + 1) for c in (4, 6)]:
        if ws.cell(r, c).value not in (None, ""):
            ws.cell(r, c).value = _iso_minus1(ws.cell(r, c).value)
    if hasattr(wb, rank_schedule._CACHE):
        delattr(wb, rank_schedule._CACHE)


def _date_values(wb: OutputWorkbook) -> dict:
    """{(사업자, 행, 날짜): 값} — 날짜 칸 값 전부(1행·머리행 제외) · 당기기 검증용."""
    out = {}
    for biz in wb.account_sheets():
        ws, heads = wb.wb[biz], set(wb._date_rows.get(biz, []))
        for lbl, c in (wb._date_col.get(biz) or {}).items():
            d = _parse_date(lbl)
            for r in range(2, ws.max_row + 1):
                v = ws.cell(r, c).value
                if r not in heads and v not in (None, ""):
                    out[(biz, r, d)] = v
    return out


def shift_back(wb: OutputWorkbook, out_dir) -> int:
    """날짜 칸·스탬프·순위 묶음 날짜를 하루 당김(메모리) → 값 그대로·대조가 +0 우세로 바뀌었는지 검증. 반환 = 바뀐 스탬프 수."""
    before = _date_values(wb)
    plus1, _zero = votes(wb, out_dir)
    for biz in wb.account_sheets():
        if wb._date_col.get(biz):
            _shift_sheet(wb, biz)
    stamps = _shift_stamps(wb)
    _shift_rank_plan(wb)
    if _date_values(wb) != {(b, r, d - timedelta(days=1)): v for (b, r, d), v in before.items()}:
        raise DateBasisError("❌ 날짜 칸 당기기 검증 실패 — 당긴 뒤 값이 전과 다름(마스터는 그대로 · 확인 필요)")
    p2, z2 = votes(wb, out_dir)
    if (p2, z2) != (0, plus1) and not (z2 >= MIN_VOTES and z2 >= DOMINANCE * p2):
        raise DateBasisError(f"❌ 날짜 칸 당기기 검증 실패 — 판매분석 대조 +1 {p2}·+0 {z2}(마스터는 그대로 · 확인 필요)")
    return stamps


def _park_progress(out: Path, ts: str) -> list[str]:
    moved = []
    for p in (_progress_path(out), _partial_path(out)):
        if p.exists():
            dst = p.with_name(f"{p.stem}_{_TAG}_{ts}{p.suffix}")
            p.rename(dst)
            moved.append(dst.name)
    return moved


def ensure_sales_date_basis(out_dir="output", log=None) -> str:
    """실행 시작 때(① run_full · ③ track_ranks_stage) 부름 — 결과 한 줄. 판정 못 함·검증 실패·옛 진행 파일 = DateBasisError."""
    log = log or (lambda m: None)
    out = Path(out_dir)
    master = _master_path(out)
    if not master.exists():
        return "마스터 없음 — 새 통계는 판매일 기준으로 시작"
    if _file_has_mark(master):
        return "이미 판매일 기준"
    wb = OutputWorkbook.load(master)
    state, plus1, zero = judge(wb, out)
    if state in ("empty", "new"):
        mark(wb, f"표시만(당김 없음) — {'날짜 칸 없음' if state == 'empty' else f'판매분석 대조 +0 {zero}·+1 {plus1}'}")
        wb.save(master)
        msg = f"[날짜 칸] 이미 판매일 기준 — 표시만 남김(당김 없음 · 대조 +0 {zero}·+1 {plus1})"
        log(msg)
        return msg
    if state == "unknown":
        raise DateBasisError(f"❌ 날짜 칸 기준을 판정 못 함 — 판매분석 대조 칸=판매일+1 {plus1}건·+0 {zero}건"
                             f"(기준 {MIN_VOTES}건·{DOMINANCE}배) → 실행 안 함(마스터 그대로 · 확인 필요)")
    ts = datetime.now().strftime("%y%m%d_%H%M%S")
    backup = out / "백업" / f"통계마스터_{_TAG}_{ts}.xlsx"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(master, backup)
    stamps = shift_back(wb, out)
    mark(wb, f"하루 당김(옛 기준 칸 = 판매일+1 · 대조 +1 {plus1}·+0 {zero}) · 백업 {backup.name}")
    wb.save(master)
    msg = (f"[날짜 칸] 지난 날짜 칸을 하루 당김(칸 = 판매일 D-368) — 사업자 시트 "
           f"{sum(1 for b in wb.account_sheets() if wb._date_col.get(b))}개 · 스탬프 {stamps}계정 · 대조 +1 {plus1}→+0 · "
           f"백업 {backup.name}")
    log(msg)
    moved = _park_progress(out, ts)
    if moved:
        raise DateBasisError(f"❌ 옛 판 진행 파일 {moved} 은 옛 날짜 칸 기준이라 보관만 했습니다 — 이번 실행은 멈춤, "
                             f"다시 실행하면 판매일 기준으로 시작(날짜 당기기는 끝남)")
    return msg


__all__ = ["BASIS", "DOMINANCE", "DateBasisError", "MARK_SHEET", "MIN_VOTES", "ensure_sales_date_basis", "has_mark",
           "judge", "mark", "shift_back", "votes"]
