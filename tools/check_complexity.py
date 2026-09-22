"""품질 게이트 — 썩음이 **건강한 파일로 번지는 것**을 막는다(회귀 차단, 제자리 분해 유도).

규칙(2026-09-22 기준, 근거=designs/CODE_HEALTH_PLAN.md §1):
- 이미 썩은 4파일(pipeline·workbook·app_qt·app)은 **허용**(정비 대상, 지금은 C 허용).
- 그 외 파일이 유지보수지수(MI)가 **C로 떨어지면 차단**(exit 1) — 건강(A/B) 유지가 규칙.
- 4파일 밖에서 **새 D+ 괴물함수**(CC≥D=21)가 생기면 **경고**(차단 아님, 눈에 띄게).

radon 미설치면 조언만 하고 통과(신규 PC에서 게이트가 막지 않도록).

    python tools/check_complexity.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

# 이미 썩어서 정비 대상인 파일(여기만 MI C 허용). 정비로 B↑ 되면 이 목록에서 빼면 자동으로 회귀 방지됨.
KNOWN_BAD = {"pipeline.py", "workbook.py", "app_qt.py", "app.py"}
SCAN_DIRS = ["src/coupang_analytics", "ui"]
CC_WARN_RANK = "D"   # D 이상(CC≥21)이면 괴물함수 경고
_RANK_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5}


def _py_files() -> list[Path]:
    out: list[Path] = []
    for d in SCAN_DIRS:
        out.extend(sorted((ROOT / d).glob("*.py")))
    return out


def main() -> int:
    try:
        from radon.complexity import cc_rank, cc_visit
        from radon.metrics import mi_rank, mi_visit
    except ImportError:
        print("[품질게이트] radon 미설치 → 조언만(통과). 설치: python -m pip install radon")
        return 0

    print("=" * 64)
    print("  품질 게이트 — MI 회귀 차단 + 괴물함수 경고")
    print("=" * 64)
    mi_violations: list[str] = []   # 4파일 밖인데 MI C (차단)
    cc_warnings: list[str] = []     # 4파일 밖인데 CC D+ (경고)
    for path in _py_files():
        name = path.name
        src = path.read_text(encoding="utf-8")
        try:
            mi_score = mi_visit(src, multi=True)
        except Exception as exc:      # 문법 오류 등 — 파싱 실패는 다른 게이트가 잡음
            print(f"  [건너뜀] {name}: 분석 실패({exc.__class__.__name__})")
            continue
        rank = mi_rank(mi_score)
        if name not in KNOWN_BAD and rank == "C":
            mi_violations.append(f"{name} (MI={mi_score:.1f}, 등급 C)")
        if name in KNOWN_BAD:
            continue                  # 괴물함수 경고는 정비 대상 4파일은 건너뜀(이미 알려짐)
        for block in cc_visit(src):
            grank = cc_rank(block.complexity)
            if _RANK_ORDER.get(grank, 0) >= _RANK_ORDER[CC_WARN_RANK]:
                cc_warnings.append(f"{name}:{block.lineno} {block.name} (CC={block.complexity}, {grank})")

    if cc_warnings:
        print(f"\n  ⚠ 건강 파일에 D+ 괴물함수 {len(cc_warnings)}개(경고 — 작게 분해 권장):")
        for w in cc_warnings:
            print(f"    · {w}")
    if mi_violations:
        print(f"\n  ❌ 건강하던 파일이 C로 떨어짐 {len(mi_violations)}개(차단):")
        for v in mi_violations:
            print(f"    · {v}")
        print("\n  → 새 코드로 파일이 썩었습니다. 함수 추출/분리로 되돌리거나, 정비 대상이면")
        print("    tools/check_complexity.py 의 KNOWN_BAD 에 근거와 함께 추가하세요.")
        print("=" * 64)
        return 1
    print(f"\n  ✅ 건강 파일 전부 A/B 유지 (괴물함수 경고 {len(cc_warnings)}개)")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
