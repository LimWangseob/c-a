"""일회성(소급) 도구 — 통계 마스터의 **일자 컬럼을 시트별 첫날~마지막날 연속·날짜순으로 정규화**.

배경: 지금까지 날짜 컬럼은 '실행한 날'만 생겼다. 실행이 없거나 중단된 날(예: 09.11)은 컬럼 자체가
안 생겨 시계열이 일자별로 끊겼다. 이 도구는 기존 마스터에 **빠진 달력일을 빈 컬럼으로 삽입**하고 정렬한다.
값(순위·판매·방문자·노출·재고)은 (행,날짜)로 스냅샷해 그대로 이식하므로 유실·이동이 없다(멱등).

- 시트별 min~max **내부 공백만** 채운다(신규 계정을 첫 추적일 이전으로 소급하지 않음).
- **맨 뒤(마지막 날 이후)로는 채우지 않는다** — 아직 안 한 날은 다음 실행이 자동 생성한다(진행 중 ③ 재개와 충돌 방지).
- 실행 전 **마스터를 백업**(…_통계_보관_날짜정렬전_yymmdd_HHMMSS.xlsx)한 뒤 원본을 정규화·재서식·저장한다.

사용: python tools/normalize_dates.py            # 기본 output/ 마스터
      python tools/normalize_dates.py <경로.xlsx>  # 특정 파일
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from coupang_analytics import config           # noqa: E402
from coupang_analytics.workbook import OutputWorkbook  # noqa: E402


def main() -> int:
    if len(sys.argv) > 1:
        master = Path(sys.argv[1])
    else:
        master = Path("output") / f"{config.OUTPUT_FILE_PREFIX}_통계.xlsx"
    if not master.exists():
        print(f"[중단] 마스터가 없습니다: {master}")
        return 1

    now = datetime.now()
    bak = master.with_name(f"{config.OUTPUT_FILE_PREFIX}_통계_보관_날짜정렬전_{now.strftime('%y%m%d_%H%M%S')}.xlsx")
    shutil.copy2(master, bak)
    print(f"[백업] {bak.name}")

    wb = OutputWorkbook.load(master)
    added = wb.normalize_date_columns(log=lambda m: print(config.format_log(m)))   # 표준 로그 포맷
    wb.apply_style()   # apply_style 자체도 normalize 를 부르지만(멱등) 서식 재적용 목적으로 호출
    wb.save(master)

    total = sum(len(v) for v in added.values())
    touched = {b: v for b, v in added.items() if v}
    print("\n=== 날짜 정규화 완료 ===")
    print(f"빈 컬럼 삽입: 총 {total}칸 · 변경 시트 {len(touched)}개")
    for biz, labs in sorted(touched.items()):
        print(f"  [{biz}] +{labs}")
    if not touched:
        print("  (이미 모든 시트가 일자별 연속·정렬 — 변경 없음)")
    print(f"저장: {master.name} (백업: {bak.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
