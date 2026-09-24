"""키워드 복구 — 백업 마스터의 상품별 키워드를 현재 마스터에 병합.

배경(2026-09-25): 레이아웃 v4에서 키워드를 C→A열로 옮기던 중, 마이그레이션 없는 빌드가 실행돼
옛 마스터의 C열 키워드가 저장 시 소실됐다(순위·판매·재고·vid는 보존). 유실 직전 백업
(`output/백업/…` 또는 일자 스냅 `쿠팡데이타분석_통계_YYMMDD.xlsx`)에는 키워드가 온전하다.

이 도구는 백업(SRC)에서 (사업자, 상품)→키워드를 읽어(현재 코드의 C 폴백으로 옛 v3도 읽힘) DST 에 병합한다.
  - 기본: **키워드가 하나도 없는 블록에만** 백업 키워드를 채운다(이번 실행에 새로 선정된 것 보존).
  - --force-backup: **모든 매칭 상품을 백업(동결) 키워드로 교체**(현재값이 달라도 원래 동결본으로 복원).
손상된 키워드 소헤더('키워드'@A)는 저장 시 apply_style 이 자가복원한다(_migrate_keyword_col). DST 원본 미변경.

매칭 키 = (사업자 시트명, 순수 상품명 `_key`).

사용:
  python tools/recover_keywords.py --src 백업.xlsx --dst 현재마스터.xlsx --out 복구.xlsx [--force-backup] [--dry-run]
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

from coupang_analytics.workbook import OutputWorkbook, _key  # noqa: E402


def _keyword_map(path: str):
    """백업 워크북 → ({(사업자,상품): [키워드…]}, {(사업자,상품,키워드): 검색량}). 키워드+검색량(F) 함께 회수."""
    wb = OutputWorkbook.load(path)
    kw: dict[tuple[str, str], list[str]] = {}
    vol: dict[tuple[str, str, str], object] = {}
    for biz in wb.account_sheets():
        for product in wb.products_of(biz):
            kws = wb.product_keywords(biz, product)
            if not kws:
                continue
            key = (biz, _key(product))
            kw[key] = list(kws)
            for k in kws:
                v = wb.keyword_search(biz, product, k)      # F열 검색량(옛 v3도 C폴백 인덱스로 조회됨)
                if v not in (None, ""):
                    vol[(biz, _key(product), k)] = v
    return kw, vol


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="키워드가 온전한 백업 마스터")
    ap.add_argument("--dst", required=True, help="키워드가 유실된 현재 마스터")
    ap.add_argument("--out", help="복구본 저장 경로(생략 시 dry-run 강제)")
    ap.add_argument("--force-backup", action="store_true",
                    help="현재값이 달라도 백업(동결) 키워드로 교체(전 상품)")
    ap.add_argument("--dry-run", action="store_true", help="변경 미저장, 복구 범위만 보고")
    args = ap.parse_args()
    dry = args.dry_run or not args.out
    force = args.force_backup

    src_kw, src_vol = _keyword_map(args.src)
    dst = OutputWorkbook.load(args.dst)
    dst_products = {(biz, _key(p)) for biz in dst.account_sheets() for p in dst.products_of(biz)}

    fill: list[tuple[str, str, list[str]]] = []      # 빈 블록 채움
    replace: list[tuple[str, str, list[str], list[str]]] = []  # 교체(force, 현재≠백업)
    same: list[tuple[str, str]] = []                 # 이미 백업과 동일/유지
    unmatched: list[tuple[str, str]] = []
    for (biz, product), kws in src_kw.items():
        if (biz, product) not in dst_products:
            unmatched.append((biz, product)); continue
        have = dst.product_keywords(biz, product)
        if not have:
            fill.append((biz, product, kws))
        elif force and have != kws:
            replace.append((biz, product, have, kws))
        else:
            same.append((biz, product))

    print("=" * 64)
    print(f"  키워드 복구 — 백업 → 현재 마스터 {'(force: 전 상품 백업으로 교체)' if force else '(빈 블록만)'}")
    print("=" * 64)
    print(f"  백업 키워드 상품:              {len(src_kw)}개")
    print(f"  빈 블록 채움:                  상품 {len(fill)}개 · 키워드 {sum(len(k) for *_, k in fill)}개")
    if force:
        print(f"  교체(현재≠백업 → 백업으로):    상품 {len(replace)}개")
        for biz, product, old, new in replace[:12]:
            print(f"     {biz}/{product[:20]}: 현재{old} → 백업{new}")
    print(f"  유지(이미 동일):               상품 {len(same)}개")
    print(f"  미매칭(현재 마스터에 상품 없음): {len(unmatched)}개")
    for biz, product in unmatched[:15]:
        print(f"     · 미매칭: {biz} / {product}")

    if dry:
        print("\n  [DRY-RUN] 저장 안 함. --out 지정 시 복구본 생성.")
        return 0

    for biz, product, kws in fill:
        dst.add_product_keywords(biz, product, kws)
    for biz, product, old, new in replace:
        for kw in list(dst.product_keywords(biz, product)):  # 현재 키워드 전부 비움(순서·잔재 무관)
            dst.clear_keyword_row(biz, product, kw)
        dst.add_product_keywords(biz, product, new)          # 백업(동결) 키워드 전체 추가
    # 검색량(F열) 복원 — add_product_keywords 는 이름만 채우므로 백업 검색량을 별도로 되살린다(우측 빈칸 방지)
    n_vol = 0
    for (biz, product, kw), v in src_vol.items():
        if dst.set_keyword_search(biz, product, kw, v):
            n_vol += 1
    dst.apply_style()   # 소헤더 자가복원 + v4 서식
    dst.save(args.out)
    # 검증(재로드)
    chk = OutputWorkbook.load(args.out)
    fill_ok = sum(1 for biz, product, _ in fill if chk.product_keywords(biz, product))
    rep_ok = sum(1 for biz, product, _o, new in replace
                 if chk.product_keywords(biz, product) == new)
    print(f"\n  ✅ 저장: {args.out}")
    print(f"  검색량(F) 복원: {n_vol}개")
    print(f"  검증(재로드): 빈블록 채움 {fill_ok}/{len(fill)} · 교체 정확 {rep_ok}/{len(replace)}")
    ok = (fill_ok == len(fill)) and (rep_ok == len(replace))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
