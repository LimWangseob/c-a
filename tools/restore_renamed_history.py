"""사업자명 변경으로 지워진 계정 이력 복구(D-080) — 옛 결과 파일의 옛 시트 이력을 지금 결과 파일의 새 시트로 합친다.

예전 일원화(merge_account)는 새 이름 시트에 같은 상품이 있으면 건너뛰고 옛 시트를 지워, 옛 날짜 이력·동결 키워드가
사라졌다(실측: 10-16 최문석→셀와니·안재현→피에스이·원더폴리→원더풀리, 10-12 봄날의햇살, 10-02 백성민, 09-22 이종훈).
이 도구는 지금 결과 파일을 고치지 않고 **새 파일로** 저장한다(원본 보존). 합치기 규칙 = `merge_history_from`
(같은 상품=이름 같거나 VID 겹침 → 새 시트 빈 칸만 채움·옛 키워드 추가 / 지금 없는 옛 상품은 되살리지 않음).

실행:
  python tools/restore_renamed_history.py --master <지금 통계.xlsx> --out <저장할 새 파일> \
      --pair "<옛 결과 파일>|<옛 시트>|<새 시트>" [--pair ...]   (옛 시트 이름 속 줄바꿈 = ⏎)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics.workbook import OutputWorkbook  # noqa: E402


def _filled(wb: OutputWorkbook, biz: str) -> int:
    """그 시트에서 값이 들어 있는 날짜 칸 수(지표·순위 행 전체) — 복구 전후 비교용."""
    ws, cols = wb.wb[biz], list(wb._date_col.get(biz, {}).values())
    return sum(1 for r in range(1, ws.max_row + 1) for c in cols if ws.cell(r, c).value not in (None, ""))


def restore(master: Path, out: Path, pairs: list[tuple[Path, str, str]], log=print) -> dict:
    wb = OutputWorkbook.load(master)
    result = {}
    for src_path, old, new in pairs:
        if new not in wb.account_sheets():
            raise ValueError(f"지금 결과 파일에 새 시트 '{new}' 가 없음")
        old_wb = OutputWorkbook.load(src_path)
        if old not in old_wb.account_sheets():
            raise ValueError(f"{src_path.name} 에 옛 시트 '{old}' 가 없음")
        before = (len(wb._date_col.get(new, {})), _filled(wb, new))
        n = wb.merge_history_from(old_wb, old, new, only_existing=True)
        after = (len(wb._date_col.get(new, {})), _filled(wb, new))
        skipped = [p for p in old_wb.products_of(old) if wb._merge_target(old_wb, old, p, new) is None]
        log(f"[복구] {src_path.name} '{old}' → '{new}': 상품 {n}개 합침 · 날짜 {before[0]}→{after[0]}칸 · "
            f"값 {before[1]}→{after[1]}칸 · 지금 없는 옛 상품 {len(skipped)}개 건너뜀 {skipped}")
        result[(old, new)] = {"merged": n, "before": before, "after": after, "skipped": skipped}
    wb.apply_style()
    wb.save(out)
    log(f"[복구] 저장 → {out}")
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--master", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--pair", action="append", required=True, help="옛결과파일|옛시트|새시트")
    a = ap.parse_args()
    if a.out.resolve() == a.master.resolve():
        raise SystemExit("--out 은 --master 와 다른 파일이어야 합니다(원본 보존)")
    pairs = []
    for raw in a.pair:
        src, old, new = raw.split("|")
        pairs.append((Path(src), old.replace("\\n", "\n").replace("⏎", "\n"), new))   # 시트 이름 속 줄바꿈 표기
    restore(a.master, a.out, pairs)


if __name__ == "__main__":
    main()
