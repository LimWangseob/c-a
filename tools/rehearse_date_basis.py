"""날짜 칸 하루 당기기 리허설(D-369 ⑥) — 운용 PC output 사본으로 개발 PC 에서 미리 돌려 봄. 로그인·쿠팡·구글 호출 없음.

원본 폴더는 **읽기만**: 마스터·판매분석_일별·진행 파일·단계 기록만 새 임시 폴더로 복사한 뒤 그 복사본에서
`date_basis.ensure_sales_date_basis` 를 돌리고 분석서(3-5) a~g 를 확인해 결과를 출력한다(실패 = exit 1).

    python tools/rehearse_date_basis.py "D:\\coupang-analytics\\output\\_분석_261119_output40\\원본\\output"
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics import date_basis as DB  # noqa: E402
from coupang_analytics import rank_schedule as RS  # noqa: E402
from coupang_analytics.pipeline_paths import _MASTER_XLSX, _PROGRESS_JSON, _PARTIAL_XLSX, _RUN_STAGE_JSON  # noqa: E402
from coupang_analytics.pipeline_paths import run_day_column  # noqa: E402
from coupang_analytics.workbook import OutputWorkbook  # noqa: E402
from coupang_analytics.workbook_common import _RANKGRP_SHEET, _STAMP_SHEET  # noqa: E402

FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(f"  {'✔' if cond else '✘'} {msg}")
    if not cond:
        FAILS.append(msg)


def copy_source(src: Path, dst: Path) -> None:
    for name in (_MASTER_XLSX, _PROGRESS_JSON, _PARTIAL_XLSX, _RUN_STAGE_JSON):
        if (src / name).exists():
            shutil.copy2(src / name, dst / name)
    shutil.copytree(src / "판매분석_일별", dst / "판매분석_일별")


def rest_set(wb) -> set:
    out = set()
    for biz in wb.account_sheets():
        col2d = {c: DB._parse_date(lbl) for lbl, c in (wb._date_col.get(biz) or {}).items()}
        for prod in wb.products_of(biz):
            rows = [r for (b, p, _k), r in wb._kw_row.items() if b == biz and p == prod]
            out |= {(biz, r, col2d[c]) for r, c in RS.rest_cells(wb, wb.wb[biz], biz, prod, rows)}
    return out


def stamps(wb) -> list:
    if _STAMP_SHEET not in wb.wb.sheetnames:
        return []
    ws = wb.wb[_STAMP_SHEET]
    return [(ws.cell(r, 2).value, ws.cell(r, 3).value) for r in range(2, ws.max_row + 1)]


def plan_dates(wb) -> tuple:
    if _RANKGRP_SHEET not in wb.wb.sheetnames:
        return (None, None)
    ws = wb.wb[_RANKGRP_SHEET]
    return ws.cell(1, 2).value, ws.cell(1, 4).value


def main(src: Path) -> int:
    with tempfile.TemporaryDirectory() as t:
        out = Path(t)
        copy_source(src, out)
        master = out / _MASTER_XLSX
        before = OutputWorkbook.load(master)
        state, plus1, zero = DB.judge(before, out)
        print(f"[판정] {state} · 칸=판매일+1 {plus1} · +0 {zero}")
        cells0, rest0, st0, pd0 = DB._date_values(before), rest_set(before), stamps(before), plan_dates(before)
        latest0 = max((DB._parse_date(x) for b in before.account_sheets() for x in before._date_col.get(b) or {}),
                      default=None)
        msgs: list[str] = []
        try:
            DB.ensure_sales_date_basis(out, msgs.append)
        except DB.DateBasisError as e:
            print(f"[중단] {e}")
        for m in msgs:
            print(f"  로그: {m}")
        after = OutputWorkbook.load(master)
        cells1 = DB._date_values(after)
        check(cells1 == {(b, r, d - timedelta(days=1)): v for (b, r, d), v in cells0.items()},
              f"(a) 날짜 칸 값 {len(cells1)}개 그대로 · 날짜만 −1")
        st1 = stamps(after)
        def _m(v):   # 빈 칸(아직 수집 기록 없는 계정) = 그대로 · 날짜 = 하루 당김
            return v if v in (None, "") else DB._minus1(v)
        same = all(a2 == _m(a1) and (h2 or "") == ",".join(_m(x) for x in (h1 or "").split(",") if x)
                   for (a1, h1), (a2, h2) in zip(st0, st1))
        check(same and len(st0) == len(st1),
              f"(b) 스탬프 {sum(1 for a, _ in st1 if a)}/{len(st1)}계정 −1 (예 {st0[:1]} → {st1[:1]})")
        check(rest_set(after) == {(b, r, d - timedelta(days=1)) for (b, r, d) in rest0},
              f"(c) 순위 쉬는 칸 {len(rest0)}개 그대로 · 묶음 시작일 {pd0} → {plan_dates(after)}")
        p2, z2 = DB.votes(after, out)
        check(DB.has_mark(after) and z2 >= DB.MIN_VOTES and z2 >= DB.DOMINANCE * p2,
              f"(d) 대조 뒤집힘 +1 {plus1}·+0 {zero} → +1 {p2}·+0 {z2} · 표시 있음")
        mt = master.stat().st_mtime_ns
        check("이미" in DB.ensure_sales_date_basis(out, None) and master.stat().st_mtime_ns == mt, "(e) 두 번째 = 그대로")
        wb = OutputWorkbook.load(master)
        del wb.wb[DB.MARK_SHEET]
        wb.save(master)
        res = DB.ensure_sales_date_basis(out, None)
        check("표시" in res and DB._date_values(OutputWorkbook.load(master)) == cells1,
              f"(f) 표시 지운 사본(구글시트 복원 흉내) = 다시 안 당김 · {res}")
        if latest0:
            lbl = run_day_column(latest0 + timedelta(days=1)).strftime("%m.%d")   # 옛 최신 실행 다음 날 = 새 규칙 칸
            wb = OutputWorkbook.load(master)
            aids = [a for b in wb.account_sheets() for a in wb.account_ids_of(b)]
            check(not any(wb.has_sales(a, lbl) for a in aids)
                  and not any(lbl in (wb._date_col.get(b) or {}) for b in wb.account_sheets())
                  and any(before.has_sales(a, lbl) for a in aids),
                  f"(g) 다음 실행 칸 {lbl} = 새 칸·수집 대상({len(aids)}계정) · 당기기 전이면 '수집됨'으로 건너뛰었을 칸")
        print(f"[결과] {'통과' if not FAILS else '실패 ' + str(len(FAILS)) + '건'} · 원본 폴더 수정 없음({src})")
    return 1 if FAILS else 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or not (Path(sys.argv[1]) / _MASTER_XLSX).exists():
        print(__doc__)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1])))
