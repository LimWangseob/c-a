"""입력 파서 병합 + 시작 전 검증 회귀 테스트(실제 실행, 네트워크 없음).

- 같은 계정ID가 여러 행에 흩어져도 **한 계정으로 병합**(상품 누락 방지 — 과거 데이터 손실 버그).
- validate_input_list: 빈 사업자명·상품0개=경고, 시트명 충돌·계정0=치명적.
- (있으면) 실제 관리대장으로도 스모크 검증.

실행: python tools/verify_input.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics import config                                    # noqa: E402
from coupang_analytics.input_list import (parse_input_list,             # noqa: E402
                                          validate_input_list)

_PASS = _FAIL = 0


def _check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"    [통과] {msg}")
    else:
        _FAIL += 1
        print(f"    [실패] {msg}")


def _make_xlsx(rows: list[tuple]) -> str:
    """헤더 + rows 로 임시 입력엑셀 생성. 컬럼: 대표자명·사업자명·계정아이디·상품명."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([config.IN_COL_REPRESENTATIVE, config.IN_COL_BUSINESS,
               config.IN_COL_ACCOUNT_ID, config.IN_COL_PRODUCT])
    for r in rows:
        ws.append(list(r))
    p = Path(tempfile.mkdtemp()) / "in.xlsx"
    wb.save(p)
    return str(p)


def test_merge_duplicate_account_id():
    print("[1] 같은 계정ID 흩어진 행 → 한 계정 병합(상품 누락 방지)")
    path = _make_xlsx([
        ("대표A", "비즈A", "accA", "상품A1"),
        ("대표A", "비즈A", "accA", "상품A2"),      # 같은 계정ID 재등장 → 병합돼야
        ("대표B", "비즈B", "accB", "상품B1"),
        ("대표A", "비즈A", "accA", "상품A3"),      # 비연속 재등장도 병합
    ])
    il = parse_input_list(path)
    ids = [a.account_id for a in il.accounts]
    _check(ids.count("accA") == 1, f"accA 는 1개 계정으로 병합 (실제 {ids.count('accA')})")
    accA = next(a for a in il.accounts if a.account_id == "accA")
    names = {p.name for p in accA.products}
    _check(names == {"상품A1", "상품A2", "상품A3"}, f"accA 상품 3개 전부 보존 ({sorted(names)})")
    _check(len(il.accounts) == 2, f"고유 계정 2개 (실제 {len(il.accounts)})")


def test_validate_warn_and_fatal():
    print("[2] 검증 — 빈 사업자명/상품0개=경고, 정상=치명적 0")
    path = _make_xlsx([
        ("대표A", "비즈A", "accA", "상품A1"),
        ("대표B", "", "accB", "상품B1"),           # 사업자명 없음 → 경고(대표명 대체)
        ("대표C", "비즈C", "accC", None),           # 상품 0개 → 경고
    ])
    il = parse_input_list(path)
    fatals, warns = validate_input_list(il)
    _check(not fatals, f"치명적 0 (실제 {fatals})")
    _check(any("사업자명 없음" in w for w in warns), "빈 사업자명 경고")
    _check(any("상품 0개" in w for w in warns), "상품 0개 경고")


def test_validate_sheet_collision_fatal():
    print("[3] 검증 — 다른 계정이 같은 시트명 → 치명적(덮어씀 방지)")
    # 사업자명 비고 대표자명 같으면 label 충돌(다른 계정ID인데 같은 시트명)
    path = _make_xlsx([
        ("홍길동", "", "accX", "상품X"),
        ("홍길동", "", "accY", "상품Y"),           # label='홍길동' 충돌
    ])
    il = parse_input_list(path)
    fatals, _ = validate_input_list(il)
    _check(any("시트명 충돌" in f for f in fatals), f"시트명 충돌 치명적 감지 ({fatals})")


def test_real_ledger_smoke():
    print("[4] 실제 관리대장 스모크(있으면)")
    real = Path(r"D:\토탈셀러\셀독\토탈셀러_셀독 관리 대장 (3).xlsx")
    if not real.exists():
        print("    [건너뜀] 실제 파일 없음")
        return
    il = parse_input_list(str(real))
    ids = [a.account_id for a in il.accounts]
    _check(len(ids) == len(set(ids)), "실파일: 병합 후 중복 계정ID 없음")
    fatals, warns = validate_input_list(il)
    _check(not fatals, f"실파일: 치명적 0 (경고 {len(warns)}건)")
    total = sum(len(a.products) for a in il.accounts)
    _check(total == 79, f"실파일: 상품 79개 보존 (실제 {total})")


def main() -> int:
    print("=" * 60)
    print("  입력 파서 병합 + 시작 전 검증 회귀 테스트")
    print("=" * 60)
    test_merge_duplicate_account_id()
    test_validate_warn_and_fatal()
    test_validate_sheet_collision_fatal()
    test_real_ledger_smoke()
    print("=" * 60)
    print(f"  결과: 통과 {_PASS} / 실패 {_FAIL}")
    print("=" * 60)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
