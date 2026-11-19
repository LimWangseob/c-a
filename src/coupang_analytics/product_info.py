"""상품 정보 날짜별 보관 — 상품조회/수정(vendor-inventory/search) 응답에서 정산이 쓸 칸만 옵션(vid)별로 뽑아 쌓는다(T-100·D-296 ③·D-316·D-318 ④).

저장 = output/상품정보_일별/{계정ID}/{YYYY-MM-DD}.json.gz (daily_snapshot 규칙 그대로 · 덮어쓰지 않음 · 같은 날 재수집은 시각 붙은 파일).
원천 = 분석 수집이 이미 받은 상품조회 응답 원문(collector 원문 버퍼) — **추가 조회 없음**.

보관 칸(응답 원문 이름 그대로 · 2026-11-18 저장 응답 281쪽 12,601상품 실측):
- 리스팅: vendorInventoryId · productName · categoryId(말단 · D-316 ④) · displayCategoryCode · categoryName ·
  deliveryChargeType · deliveryCharge(기본배송비) · freeShipOverAmount · returnCharge(반품배송비 편도 · D-318 ④)
- 판매상태: productStatus(ON_SALE·PARTIAL_ON_SALE·SUSPENDED… · 셀독 계약자별 상품 현황 N3 · D-358)
- 옵션: vendorItemId(=vid · 정산 옵션ID) · vendorInventoryItemId · itemName · registrationType · salePrice
- deliveryChargeOnReturn(초도반품비) = 찾는 칸이지만 **이 응답에 없음**(실측 0/12,601) → 응답에 생기면 그대로 담고, 없으면 '응답에_없는_칸'에 적는다.
- '상품 정보 수량' = 이 응답·재고현황 응답 어디에도 해당 칸 없음 → 칸 이름을 지어내지 않고 담지 않는다(보고서).

응답 쪽마다 깨졌는지(비200 본문·JSON 아님·success=false·쪽 수 모자람)를 보고, 하나라도 있으면 부분본(_부분)으로 둔다(lookup 이 안 씀).
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from . import daily_snapshot

DIRNAME = daily_snapshot.PRODUCT_INFO_DIRNAME
LISTING_KEYS = ("vendorInventoryId", "productName", "productStatus", "categoryId", "displayCategoryCode", "categoryName",
                "deliveryChargeType", "deliveryCharge", "freeShipOverAmount", "returnCharge", "deliveryChargeOnReturn")
OPTION_KEYS = ("vendorItemId", "vendorInventoryItemId", "itemName", "registrationType", "salePrice")


def _page(body) -> dict | None:
    """응답 원문 한 쪽 → data(정상) 또는 None(깨진 쪽)."""
    try:
        doc = json.loads(body)
    except (TypeError, json.JSONDecodeError):
        return None
    data = doc.get("data") if isinstance(doc, dict) and doc.get("success") is not False else None
    return data if isinstance(data, dict) and isinstance(data.get("productList"), list) else None


def _rows_of(listing: dict) -> list[dict]:
    base = {k: listing[k] for k in LISTING_KEYS if k in listing}
    out = []
    for it in listing.get("vendorInventoryItems") or []:
        if it.get("vendorItemId") in (None, ""):
            continue                                   # vid 없는 옵션(승인 전 등)은 정산 줄과 이을 수 없음
        row = dict(base)
        row.update({k: it[k] for k in OPTION_KEYS if k in it})
        row["vendorItemId"] = str(it["vendorItemId"])
        out.append(row)
    return out


def extract(bodies) -> dict:
    """상품조회 응답 원문 쪽 목록 → {'상품': [옵션별 줄], '응답에_없는_칸': [...], '쪽': n, '완전': bool}.

    완전 = 깨진 쪽 0 · 받은 쪽 수 ≥ 응답 totalPages. 응답에_없는_칸 = 리스팅이 하나라도 있는데 어느 리스팅에도 없는 보관 칸."""
    rows: list[dict] = []
    seen: set[str] = set()
    n_listing = 0
    bad = 0
    total_pages = 0
    for body in bodies or []:
        data = _page(body)
        if data is None:
            bad += 1
            continue
        total_pages = max(total_pages, int((data.get("pagination") or {}).get("totalPages") or 1))
        for listing in data["productList"]:
            n_listing += 1
            seen.update(k for k in LISTING_KEYS if k in listing)
            rows.extend(_rows_of(listing))
    good = len(bodies or []) - bad
    missing = [k for k in LISTING_KEYS if k not in seen] if n_listing else []
    return {"상품": rows, "응답에_없는_칸": missing, "쪽": good, "완전": bad == 0 and good >= total_pages}


def archive(out_dir, account_id: str, bodies, log) -> Path | None:
    """그 계정 상품조회 응답 원문을 날짜별 파일로 보관. 응답 없음 = no-op. 저장 실패 = 로그(비치명 · 수집은 계속)."""
    if not bodies:
        return None
    got = extract(bodies)
    try:
        path = daily_snapshot.save(out_dir, DIRNAME, account_id, got, partial=not got["완전"])
    except OSError as exc:
        log(f"  [상품정보 보관] ⚠ {account_id} 저장 실패(비치명) — {exc.__class__.__name__}: {str(exc)[:80]}")
        return None
    note = "" if got["완전"] else " · ⚠ 깨진 쪽 있음 → 부분본(조회에 안 씀)"
    log(f"  [상품정보 보관] {account_id}: 옵션 {len(got['상품'])}줄(쪽 {got['쪽']}){note} → {path}")
    return path


def lookup(out_dir, account_id: str, on: str | None = None) -> dict[str, dict]:
    """정산 쪽 조회 — {옵션ID(vid): 보관 줄 + '날짜'}. on(YYYY-MM-DD) 이하 완료본만 오래된 것부터 겹쳐 **그 옵션이 마지막으로 보인 날** 값.

    지워진 상품도 마지막으로 보인 날 값이 남는다. 보관 파일 없음 = {}(호출부가 '자료 없음'으로 처리).
    categoryId = row.get('categoryId') · 초도반품비 = row.get('deliveryChargeOnReturn')(지금 응답엔 없음)."""
    out: dict[str, dict] = {}
    for p in daily_snapshot.complete_files(out_dir, DIRNAME, account_id):
        day = p.name[:10]
        if on and day > on:
            continue
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            rec = json.load(fh)
        for row in rec.get("상품") or []:
            out[row["vendorItemId"]] = {**row, "날짜": rec.get("날짜", day)}
    return out
