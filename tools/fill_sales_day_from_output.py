"""지난 날짜 칸 판매량을 output 의 저장 자료(판매분석 일별 기록)로 채운다 — 로그인·쿠팡 조회 없음(T-155 · 소유자 2026-11-22
"별도 스크립트에서 OUTPUT파일을 읽어서 처리해줘").

- 채우는 칸 = 그 날짜 칸의 **판매량 빈 칸만**(값 있는 칸은 그대로). 값 = 앱 ①과 같은 규칙(`pipeline_process._fill_product_metrics`):
  블록 VID 중 그날 기록에 있는 첫 VID 의 '판매수량'(= 판매분석 `m.sales` 그대로 · D-031) · 그날 기록이 있는데 블록 VID 가 없으면 0
  (판매분석은 판매·노출 있던 VID 만 줌) · 그 계정의 그날 기록이 없으면 빈 칸 그대로(로그인 실패 등 — 지어내지 않음).
- 노출·방문자 = 저장 자료에 없음(판매분석 일별 기록엔 판매수량·금액·주문만) → 건드리지 않음.
- 기본 = 미리보기(쓰기 없음). `--apply` = 마스터를 `output/백업/` 에 복사한 뒤 저장(D-376 임시 파일 바꿔 끼우기).
  앱·무인 실행이 파이프라인 잠금을 쥐고 있으면 멈춤(exit 3). 결과 구글시트는 다음 실행이 마스터를 그대로 반영.
- `--check 날짜` = 이미 채워진 날짜 칸과 같은 규칙으로 다시 계산해 비교(이 스크립트 계산이 앱과 같은지 확인 · 쓰기 없음).

    python tools/fill_sales_day_from_output.py --output output --check 2026-11-20
    python tools/fill_sales_day_from_output.py --output output --date 2026-11-19            # 미리보기
    python tools/fill_sales_day_from_output.py --output output --date 2026-11-19 --apply
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")   # type: ignore[union-attr]
except AttributeError:
    pass

from coupang_analytics import config, sales_history  # noqa: E402
from coupang_analytics.pipeline_paths import _master_path, column_label  # noqa: E402
from coupang_analytics.registry_lock import RegistryLockError, registry_lock  # noqa: E402
from coupang_analytics.workbook import OutputWorkbook  # noqa: E402


def blocks(wb) -> list[tuple[str, str, str, list[str]]]:
    """[(사업자, 상품, 계정ID, 블록 VID)] — 판매량 행이 있는 블록 전부(판매중지 블록 포함)."""
    out = []
    for biz, prod, metric in wb._metric_row:
        if metric == config.M_SALES:
            aid = wb.product_account_id(biz, prod) or wb.account_id_of(biz) or ""
            out.append((biz, prod, aid, [str(v) for v in wb.product_vids(biz, prod)]))
    return out


def expected(rec: dict | None, vids: list[str]):
    """그날 기록 → 블록 판매량(앱 ①과 같은 규칙) · 기록 없음 = None."""
    if rec is None:
        return None
    opts = rec.get("옵션") or {}
    return next((int(opts[v].get("판매수량") or 0) for v in vids if v in opts), 0)


def cell(wb, biz: str, prod: str, label: str):
    col = wb._date_col.get(biz, {}).get(label)
    return None if col is None else wb.wb[biz].cell(wb._metric_row[(biz, prod, config.M_SALES)], col)


def plan(out: Path, wb, day: str) -> list[dict]:
    label, recs = column_label(day), {}
    rows = []
    for biz, prod, aid, vids in blocks(wb):
        if aid not in recs:
            recs[aid] = sales_history.load_account(out, aid) if aid else {}
        c = cell(wb, biz, prod, label)
        rows.append({"사업자": biz, "상품": prod, "계정": aid, "칸": c, "지금": None if c is None else c.value,
                     "계산": expected(recs[aid].get(day), vids)})
    return rows


def do_check(out: Path, wb, day: str) -> int:
    rows = [r for r in plan(out, wb, day) if r["칸"] is not None and r["지금"] not in (None, "") and r["계산"] is not None]
    bad = [r for r in rows if r["지금"] != r["계산"]]
    print(f"[확인] {column_label(day)} 칸 — 값 있는 판매량 칸 {len(rows)}개 중 다시 계산과 다름 {len(bad)}개")
    for r in bad[:20]:
        print(f"  다름: {r['사업자']} / {r['상품'][:30]} ({r['계정']}) 칸 {r['지금']} · 계산 {r['계산']}")
    return 0 if not bad else 1


def do_fill(out: Path, master: Path, wb, day: str, apply: bool) -> int:
    rows = plan(out, wb, day)
    if any(r["칸"] is None for r in rows):
        print(f"❌ 마스터에 {column_label(day)} 날짜 칸이 없는 시트가 있음 — 날짜 칸을 만들지 않습니다(앱 실행이 만든 칸만 채움)")
        return 1
    todo = [r for r in rows if r["지금"] in (None, "") and r["계산"] is not None]
    keep = sum(1 for r in rows if r["지금"] not in (None, ""))
    none = sorted({r["계정"] or r["사업자"] for r in rows if r["지금"] in (None, "") and r["계산"] is None})
    print(f"[{column_label(day)} 판매량] 블록 {len(rows)} · 채울 칸 {len(todo)}(판매 있음 {sum(1 for r in todo if r['계산'])}) · "
          f"이미 값 있음 {keep} · 그날 기록 없어 빈 칸 그대로 {len(rows) - len(todo) - keep}(계정 {len(none)}: {', '.join(none)})")
    print("  노출·방문자 = 저장 자료에 없음 → 그대로(빈 칸)")
    if not apply:
        print("  (미리보기 — 쓰지 않음. 저장하려면 --apply)")
        return 0
    for r in todo:
        r["칸"].value = r["계산"]
    bak = out / "백업" / f"쿠팡데이타분석_통계_{day}판매량채우기전_{datetime.now():%y%m%d_%H%M%S}.xlsx"
    bak.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(master, bak)
    wb.save(master)
    print(f"  ✅ 저장 {master} · 저장 전 백업 {bak}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--output", default="output")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--date", help="채울 날짜(YYYY-MM-DD · 판매일 = 날짜 칸)")
    g.add_argument("--check", help="이미 채워진 날짜와 다시 계산 비교(YYYY-MM-DD)")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.output)
    master = _master_path(out)
    if not master.is_file():
        print(f"❌ 마스터 없음: {master}")
        return 1
    try:
        with registry_lock(out / "_잠금" / "파이프라인.lock", wait_sec=0):
            wb = OutputWorkbook.load(master)
            return do_check(out, wb, a.check) if a.check else do_fill(out, master, wb, a.date, a.apply)
    except RegistryLockError:
        print("⏸ 앱·무인 실행이 도는 중(파이프라인 잠금) — 끝난 뒤 다시 실행하세요")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
