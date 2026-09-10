"""로그(run_log)를 읽어 노출순위를 엑셀 워크북에 반영하는 복구 도구.

전체실행/③단계 로그의 `[키워드] {상품} → [...]`(상품 컨텍스트)와 `[순위] '{kw}': {값}` 라인을 파싱해,
**기존 워크북의 순위 셀만 갱신**한다. 로그인·네트워크 없음(로그+엑셀만).
- **50위 밖 → 50위로 고정**(config.RANK_SCAN_MAX). 스캔 안 순위(예: 36)는 그 값 그대로.
- 로그에 있는(=실제 측정된) 키워드만 갱신 — 로그에 없는 순위는 손대지 않음.
- 기존 소스코드 재사용: OutputWorkbook.load/save/set_keyword_rank/account_sheets/latest_date.

사용:
    python tools/reflect_log_to_excel.py <run_log.log> [워크북.xlsx]
    (워크북 생략 시 output/쿠팡데이타분석_통계.xlsx = 마스터)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from coupang_analytics import config  # noqa: E402
from coupang_analytics.workbook import OutputWorkbook  # noqa: E402

_MASTER = "output/쿠팡데이타분석_통계.xlsx"
_RE_ACCT = re.compile(r"==\s*\[\d+/\d+\]\s*(.+?)\s*\(계정ID:")   # 계정(시트=사업자명)
_RE_KW = re.compile(r"\[키워드\]\s*(.+?)\s*→\s*\[")             # 상품 컨텍스트 확립
_RE_RANK = re.compile(r"\[순위\]\s*'(.+?)':\s*(.+?)\s*$")        # 키워드→순위


def parse_log(path: str) -> list[tuple[str, str, str, int]]:
    """→ [(사업자명, 상품명, 키워드, 순위)]. 50위 밖 → RANK_SCAN_MAX 로 고정."""
    entries: list[tuple[str, str, str, int]] = []
    biz: str | None = None
    product: str | None = None
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        m = _RE_ACCT.search(line)
        if m:
            biz, product = m.group(1).strip(), None
            continue
        m = _RE_KW.search(line)
        if m:
            product = m.group(1).strip()
            continue
        m = _RE_RANK.search(line)
        if m and biz and product:
            kw, val = m.group(1).strip(), m.group(2).strip()
            if "밖" in val:                     # "50위 밖" → 상한값 고정
                rank = config.RANK_SCAN_MAX
            else:
                digits = re.sub(r"[^0-9]", "", val)
                if not digits:
                    continue
                rank = min(int(digits), config.RANK_SCAN_MAX)   # 안전: 상한 초과값도 상한으로
            entries.append((biz, product, kw, rank))
    return entries


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    log_path = args[0]
    wb_path = args[1] if len(args) > 1 else _MASTER
    if not Path(log_path).exists():
        print(f"[중단] 로그 파일 없음: {log_path}")
        return
    if not Path(wb_path).exists():
        print(f"[중단] 워크북 없음: {wb_path}")
        return

    entries = parse_log(log_path)
    fixed50 = sum(1 for e in entries if e[3] == config.RANK_SCAN_MAX)
    print(f"[반영] 로그 파싱 — 순위 항목 {len(entries)}개 "
          f"(50위밖→{config.RANK_SCAN_MAX} {fixed50}개 · 스캔내 {len(entries) - fixed50}개)")

    wb = OutputWorkbook.load(wb_path)
    sheets = set(wb.account_sheets())
    date_cache: dict[str, str | None] = {}
    applied = no_row = 0
    no_sheet: set[str] = set()
    for biz, product, kw, rank in entries:
        if biz not in sheets:
            no_sheet.add(biz)
            continue
        if biz not in date_cache:
            date_cache[biz] = wb.latest_date(biz)
        date = date_cache[biz]
        if not date:
            continue
        if wb.set_keyword_rank(biz, product, kw, date, rank):
            applied += 1
        else:
            no_row += 1
    wb.save(wb_path)
    print(f"[반영] 완료 — 순위 갱신 {applied}개 · 행 없음(스킵) {no_row}개")
    if no_sheet:
        print(f"[반영] ⚠ 워크북에 없는 시트(스킵): {sorted(no_sheet)}")
    print(f"[반영] 저장: {wb_path}")


if __name__ == "__main__":
    main()
