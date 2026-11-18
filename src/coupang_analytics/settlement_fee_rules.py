"""정산 지급 전 예상 규칙값 — 쿠팡 줄이 아직 없을 때만 쓰는 계정 정액·신상품 무료 규칙(T-116 · D-325 · D-326). 순수 함수.

이미 지급된(쿠팡 줄이 있는) 금액은 늘 쿠팡 원문 값(D-279) — 여기 값은 예상·경고값만. 판매자서비스이용료 규칙
(`settlement_managed_alloc.svc_charges`·`svc_settle`)과 같은 모양: 규칙으로 못 정하는 값은 None 을 돌려 호출부가 금액 없이
'확인 필요'로 둔다(D-146). 특정 계정·상품·금액 조건 없음(D-229).

- 비즈니스 인사이트(74 · D-325): 청구 = 월정액(VAT 제외) × 12 ÷ 365 × 유료 이용일수(유료 시작일~그 달 말일) 사사오입 → × 1.1 사사오입 ·
  달 첫날 시작·월말 갱신 = 월정액 그대로(× 1.1) · 회차 공제는 지급액 한도까지 나뉘어 빠짐 → 회차 예상 = 청구액 − 이미 뺀 조각.
- 로켓그로스 신상품 무료(43·44·45·76·76-2 · D-326 · D-318 ① 구체화): 첫 진열일(첫 입고완료일 + 1)부터 45일(첫 진열 2026-04-01~08-31) ·
  입출고·배송 k ≤ 43 = 0원 · k = 44 = 쿠팡 줄 값(없으면 경계 미확정) · k ≥ 45 = 유료 · 보관 31~45일 무료 = k ≤ 44 ·
  대상 옵션 = 데이터로 못 가름 → 쿠팡 줄 값 / 그 옵션 첫 정산 줄(계정 시작 무료 창 밖)이 0원이면 대상.
"""
from __future__ import annotations

import calendar
from datetime import date

# ── 비즈니스 인사이트 월정액 표(VAT 제외) — 한곳 · 화면 확인값만 · (플랜, 유효 시작, 유효 끝, 출처) ──
# 12-01 신규 요금제('프로' 이상 · 두 계정 화면 공지 11-18) 뒤 값은 모름 → 화면 확인 뒤 줄 추가(그 전엔 None = 확인 필요).
# 옛 공제에 보이는 99,000·50,000 은 플랜 이름을 화면에서 못 봐 표에 없음(D-325 근거 = 금액만).
BI_MONTHLY = (
    ("프리미엄", date(2025, 11, 1), date(2026, 11, 30), 375_000,
     "윙 화면 tellace83 구독 내역 2025-12-01~2026-11-09 · BI_RG 2025-11 345,205(28일) — "
     "output\\_통제_261118_재개준비\\윙화면_tellace83\\74_비즈니스인사이트_구독내역.md"),
    ("스탠다드", date(2026, 10, 1), date(2026, 11, 30), 89_000,
     "윙 화면 nicoable 구독 관리(2026-11 청구 89,000) · BI_RG 2026-10 70,225/77,248(24일) — "
     "output\\_통제_261118_재개준비\\윙화면_nicoable\\74_비즈니스인사이트.md"),
)


def bi_monthly(plan: str, day: date) -> int | None:
    """그 날 플랜의 월정액(VAT 제외) — 표에 없는 플랜·기간 = None(호출부 '확인 필요')."""
    return next((won for p, a, b, won, _src in BI_MONTHLY if p == plan and a <= day <= b), None)


def _half_up(num: int, den: int) -> int:
    """num / den 사사오입(0.5 올림 · 양수) — 정수 계산(실수 오차·은행가 반올림 없음)."""
    return (2 * num + den) // (2 * den)


def bi_paid_days(start: date) -> int:
    """유료 이용일수 = 유료 시작일부터 그 달 말일까지(양 끝 포함)."""
    return calendar.monthrange(start.year, start.month)[1] - start.day + 1


def bi_supply(monthly: int, start: date) -> int:
    """공급가(VAT 제외) — 달 첫날 시작 = 월정액 · 달 중간(첫 달·플랜 변경·무료 체험 종료 다음 날) = 월정액 × 12 ÷ 365 × 일수 사사오입."""
    if start.day == 1:
        return monthly
    return _half_up(monthly * 12 * bi_paid_days(start), 365)


def bi_charge(monthly: int, start: date) -> int:
    """청구액(VAT 포함) = 공급가 × 1.1 사사오입(세금계산서 합계·RG 공제 칸 원 단위 · D-325)."""
    return _half_up(bi_supply(monthly, start) * 11, 10)


def bi_left(charge: int, taken: list) -> dict:
    """회차 예상 — 청구액 − 이미 회차에서 뺀 조각(원문 값) · 청구보다 더 빠진 금액 = 규칙 밖(조용히 0 으로 안 바꿈)."""
    got = sum(taken)
    return {"남은 청구": max(charge - got, 0), "규칙 밖": max(got - charge, 0)}


# ── 로켓그로스 신상품 무료 창(D-326) ──
NEWFREE_FROM, NEWFREE_TO = date(2026, 4, 1), date(2026, 8, 31)    # 첫 진열이 이 안인 옵션만(4~8월 시작분 모두 45일)
NEWFREE_LAST_FREE = 43                                            # 입출고·배송 k ≤ 43 = 0원
NEWFREE_EDGE = 44                                                 # k = 44 = 쿠팡 줄 값(시각 경계 · 데이터로 못 가름)
NEWFREE_STORAGE_LAST = 44                                         # 보관 31~45일 무료 = k ≤ 44
NEWFREE_KINDS = ("입출고", "배송", "보관31_45")
NF_FREE, NF_EDGE, NF_PAID, NF_OUT = "신상품 무료", "경계 미확정(44일째)", "유료(45일째 뒤)", "대상 아님(첫 진열 4~8월 밖)"
NF_NOT, NF_UNKNOWN, NF_COUPANG = "대상 아님(첫 정산 줄 유료)", "대상 미확정(첫 정산 줄 없음)", "쿠팡 줄 값"


def newfree_display(first_inbound_done: date) -> date:
    """첫 진열일 = 첫 입고완료일 + 1(바코드 자료 8옵션 모두 하루 차이 · D-326)."""
    return date.fromordinal(first_inbound_done.toordinal() + 1)


def newfree_state(display: date, occur: date, kind: str) -> str:
    """k = 발생일 − 첫 진열일(진열 당일 = 0 = 1일째) → 무료·경계·유료·대상 아님. 진열 전 발생·모르는 항목 = 오류(자료 오류를 숨기지 않음)."""
    if kind not in NEWFREE_KINDS:
        raise ValueError(f"신상품 무료 항목 아님: {kind!r}")
    k = (occur - display).days
    if k < 0:
        raise ValueError(f"발생일 {occur} 이 첫 진열일 {display} 보다 앞")
    if not NEWFREE_FROM <= display <= NEWFREE_TO:
        return NF_OUT
    if kind == "보관31_45":
        return NF_FREE if k <= NEWFREE_STORAGE_LAST else NF_PAID
    if k <= NEWFREE_LAST_FREE:
        return NF_FREE
    return NF_EDGE if k == NEWFREE_EDGE else NF_PAID


def newfree_expect(kind: str, display: date, occur: date, paid: int, first_line: int | None,
                   coupang: int | None = None) -> tuple[int | None, str]:
    """한 줄 예상 금액 → (금액 또는 None, 근거). coupang = 쿠팡 줄 값(있으면 그대로) · paid = 유료일 때 규칙 금액 ·
    first_line = 그 옵션 첫 정산 줄 금액(계정 시작 무료 창 밖 · 없으면 None). None 금액 = 호출부 '확인 필요'."""
    if coupang is not None:
        return coupang, NF_COUPANG
    state = newfree_state(display, occur, kind)
    if state in (NF_OUT, NF_PAID):
        return paid, state
    if first_line is None:
        return None, NF_UNKNOWN
    if first_line != 0:
        return paid, NF_NOT
    return (0, NF_FREE) if state == NF_FREE else (None, NF_EDGE)
