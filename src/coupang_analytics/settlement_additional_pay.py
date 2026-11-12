"""윙 추가지급(정산 > 추가지급) — 정산서 반영(D-116 ③①).

추가지급(쿠팡확인요청 승인·회수 지원 등)은 매출내역·지급내역에 안 나오고 이 메뉴에만 나온다(KB §1-1·§1-7).
수집 = settlement_verify_collect `additional`({YYYYMM: {reports, page, pageSize, totalPages}}, 쪽 크기 100·1쪽만).
칸 이름 = 윙 화면 코드 AdditionalPaymentReportRow(2026-10-26 벅스 실측, KB §1-7 칸 순서와 같음). 실제 줄은 아직 0건
(전 계정·운용 PC 10-26) → 줄이 있으면 금액과 함께 '확인 필요(첫 실제 자료로 칸 확정)'를 붙인다.
"""
from __future__ import annotations

import json
from pathlib import Path

FIELDS = (("업체코드", "vendorId"), ("지급일", "payDate"), ("세금계산서", "taxInvoiceIssueType"), ("노출상품ID", "productId"),
          ("등록상품명", "productName"), ("옵션ID", "vendorItemId"), ("옵션명", "vendorItemName"), ("주문번호", "orderId"),
          ("판매가", "salePrice"), ("판매수량", "saleQuantity"), ("신청금액", "requestAmount"), ("지급구분", "requestStatusType"),
          ("지급금액", "finalRewardAmount"), ("지급항목", "rewardType"), ("비고", "note"))
PAID = "PAID"                          # 화면: PAID = '지급', 그 밖 = '반려'


def _num(v) -> int:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def months_of(base: Path, acct: str, snap: dict | None) -> dict | None:
    """{YYYYMM: 응답} — 검증자료 + 스냅샷(같은 달은 스냅샷). 둘 다 없으면 None(자료 없음)."""
    p = base / "검증자료" / f"{acct}.json"
    d = (json.loads(p.read_text(encoding="utf-8")).get("additional") if p.exists() else None)
    s = (snap or {}).get("additional")
    if d is None and s is None:
        return None
    return {**(d or {}), **(s or {})}


def summarize(months: dict | None) -> dict:
    """→ {상태: 없음|있음|자료 없음, 지급금액(PAID 합), 줄[{한글 칸: 값}], 메모}. 금액은 쿠팡 칸 그대로 더하기만."""
    if months is None:
        return {"상태": "자료 없음", "지급금액": 0, "줄": [], "메모": "추가지급 조회 자료 없음 — 확인 필요"}
    rows, notes = [], []
    for ym, r in sorted(months.items()):
        if r is None:
            notes.append(f"{ym} 조회 실패")
            continue
        rows += [{k: x.get(c) for k, c in FIELDS} for x in r.get("reports") or []]
        if (r.get("totalPages") or 0) > 1:
            notes.append(f"{ym} {r['totalPages']}쪽 중 1쪽만 수집")
    if not rows and not notes:
        return {"상태": "없음", "지급금액": 0, "줄": [], "메모": "추가지급 없음"}
    paid = sum(_num(x["지급금액"]) for x in rows if x["지급구분"] == PAID)
    memo = " · ".join([f"{len(rows)}줄(지급 {sum(x['지급구분'] == PAID for x in rows)})", *notes])
    return {"상태": "있음" if rows else "자료 없음", "지급금액": paid, "줄": rows, "메모": memo}
