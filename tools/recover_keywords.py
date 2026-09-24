"""키워드 복구 — 백업 마스터의 상품별 키워드를 현재 마스터의 **키워드 없는 블록**에 병합.

배경(2026-09-25): 레이아웃 v4에서 키워드를 C→A열로 옮기던 중, 마이그레이션 없는 빌드가 실행돼
옛 마스터의 C열 키워드가 저장 시 소실됐다(순위·판매·재고·vid는 보존). 유실 직전 백업
(`output/백업/…` 또는 일자 스냅 `쿠팡데이타분석_통계_YYMMDD.xlsx`)에는 키워드가 온전하다.

이 도구는:
  - 백업(SRC)에서 (사업자, 상품)→키워드를 읽고(현재 코드의 C 폴백으로 옛 v3도 읽힘),
  - 현재 마스터(DST)에서 **키워드가 하나도 없는 상품 블록에만** 그 키워드를 채운다
    (이미 키워드가 있는 블록은 건드리지 않음 — 이번 실행에 새로 선정된 것 보존),
  - v4 서식(apply_style)으로 OUT 에 저장한다(DST 원본은 미변경).

매칭 키 = (사업자 시트명, 순수 상품명 `_key`). 이름 불일치(노출명 드리프트)는 미매칭으로 보고.

사용:
  python tools/recover_keywords.py --src 백업.xlsx --dst 현재마스터.xlsx --out 복구.xlsx [--dry-run]
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

from coupang_analytics import config  # noqa: E402
from coupang_analytics.workbook import (  # noqa: E402
    _COL_KW, _COL_METRIC, _COL_SEARCH, _LABEL_KEYWORD, _LABEL_SEARCH,
    _SPECIAL_SHEETS, OutputWorkbook, _key, _norm, _unmerge_all)

_SUBHEAD_G = {"비고", "⛔ 판매중지", "🔴 체험단중"}   # 키워드 소헤더행의 G(비고 슬롯) 후보


def repair_keyword_subheaders(wb: OutputWorkbook) -> int:
    """손상된 마스터에서 사라진 키워드 소헤더 마커('키워드'@A열)를 복원(2026-09-25 유실 사고 대응).

    버그 빌드가 저장한 마스터는 키워드 소헤더의 A='키워드'가 사라져 `_find_kw_head`가 키워드 구역을 못
    찾고(→ v4 서식이 키워드행을 지표행으로 오인해 뭉갬), add_product_keywords 후 저장 시 다시 유실된다.
    소헤더행 = 블록 안 첫 M_RANK(노출순위) 행 **직전** 행(F='검색량' 또는 G∈{비고/판매중지/체험단}로 검증).
    그 행의 A가 '키워드'가 아니면 복원한다. 복원 수 반환(0=멀쩡). 이후 호출부가 _reindex."""
    fixed = 0
    idx_norm = "계정목록".replace(" ", "")
    for ws in wb.wb.worksheets:
        if ws.title in _SPECIAL_SHEETS or ws.title.replace(" ", "") == idx_norm:
            continue
        _unmerge_all(ws)                       # 쓰기 전 병합 해제(apply_style 가 재병합)
        headers = [r for r in range(1, ws.max_row + 1) if _norm(ws.cell(r, _COL_METRIC).value) == "날짜"]
        for hi, hr in enumerate(headers):
            end = (headers[hi + 1] - 1) if hi + 1 < len(headers) else ws.max_row
            first_kw = next((r for r in range(hr, end + 1)
                             if _norm(ws.cell(r, _COL_METRIC).value) == config.M_RANK), None)
            if not first_kw or first_kw <= hr:
                continue
            sh = first_kw - 1                  # 소헤더 후보(첫 키워드행 직전)
            is_sub = (_norm(ws.cell(sh, _COL_SEARCH).value) == _LABEL_SEARCH
                      or _norm(ws.cell(sh, _COL_METRIC).value) in _SUBHEAD_G)
            if is_sub and _norm(ws.cell(sh, _COL_KW).value) != _LABEL_KEYWORD:
                ws.cell(sh, _COL_KW, _LABEL_KEYWORD)
                if not _norm(ws.cell(sh, _COL_SEARCH).value):
                    ws.cell(sh, _COL_SEARCH, _LABEL_SEARCH)
                fixed += 1
    if fixed:
        wb._reindex()
    return fixed


def _keyword_map(path: str) -> dict[tuple[str, str], list[str]]:
    """백업 워크북 → {(사업자, 순수상품명): [키워드…]} (키워드 있는 상품만)."""
    wb = OutputWorkbook.load(path)
    out: dict[tuple[str, str], list[str]] = {}
    for biz in wb.account_sheets():
        for product in wb.products_of(biz):
            kws = wb.product_keywords(biz, product)
            if kws:
                out[(biz, _key(product))] = list(kws)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="키워드가 온전한 백업 마스터")
    ap.add_argument("--dst", required=True, help="키워드가 유실된 현재 마스터")
    ap.add_argument("--out", help="복구본 저장 경로(생략 시 dry-run 강제)")
    ap.add_argument("--dry-run", action="store_true", help="변경 미저장, 복구 범위만 보고")
    args = ap.parse_args()
    dry = args.dry_run or not args.out

    src_kw = _keyword_map(args.src)
    dst = OutputWorkbook.load(args.dst)
    n_repair = repair_keyword_subheaders(dst)   # 손상된 키워드 소헤더('키워드'@A) 복원(병합 전제)
    print(f"  키워드 소헤더 복원: {n_repair}개 블록")
    dst_products = {(biz, _key(p)) for biz in dst.account_sheets() for p in dst.products_of(biz)}

    restore: list[tuple[str, str, list[str]]] = []   # (biz, product, kws) 복구 대상
    already: list[tuple[str, str]] = []              # 이미 키워드 있음(스킵)
    unmatched: list[tuple[str, str]] = []            # 백업엔 있으나 현재 마스터에 상품 없음
    for (biz, product), kws in src_kw.items():
        if (biz, product) not in dst_products:
            unmatched.append((biz, product)); continue
        if dst.product_keywords(biz, product):
            already.append((biz, product)); continue
        restore.append((biz, product, kws))

    n_kw = sum(len(k) for _, _, k in restore)
    print("=" * 64)
    print("  키워드 복구 — 백업 → 현재 마스터(키워드 없는 블록만)")
    print("=" * 64)
    print(f"  백업 키워드 상품:        {len(src_kw)}개")
    print(f"  복구 대상(현재 비어있음): 상품 {len(restore)}개 · 키워드 {n_kw}개")
    print(f"  스킵(이미 키워드 있음):   상품 {len(already)}개")
    print(f"  미매칭(현재 마스터에 상품 없음): {len(unmatched)}개")
    for biz, product in unmatched[:15]:
        print(f"     · 미매칭: {biz} / {product}")
    print("  [복구 예시]")
    for biz, product, kws in restore[:8]:
        print(f"     {biz} / {product[:26]} ← {kws}")

    if dry:
        print("\n  [DRY-RUN] 저장 안 함. --out 지정 시 복구본 생성.")
        return 0

    for biz, product, kws in restore:
        dst.add_product_keywords(biz, product, kws)
    dst.apply_style()
    dst.save(args.out)
    # 검증(재로드)
    chk = OutputWorkbook.load(args.out)
    restored_ok = sum(1 for biz, product, _ in restore if chk.product_keywords(biz, product))
    print(f"\n  ✅ 저장: {args.out}")
    print(f"  검증(재로드): 복구 대상 {len(restore)}개 중 키워드 채워짐 {restored_ok}개")
    return 0 if restored_ok == len(restore) else 1


if __name__ == "__main__":
    raise SystemExit(main())
