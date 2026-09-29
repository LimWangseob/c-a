"""정산 금액 식 3종. SSOT=designs/SETTLEMENT_MODULE.md §4 (근거 COUPANG_SETTLEMENT_DOMAIN.md §3).

- `MP_REVENUE_REPORT`(윙 매출내역): 정산대상액 E = A − B − C − D, 최종지급예정액 = E − F.
- RG 실지급(로켓그로스): 판매수수료리포트 정산대상액 − 밀크런 − 광고비 − CFS(부가 리포트 조인 필수·누락=이익 과대).
- `RG_HOME_PROFIT`(로켓그로스 홈 이익·VAT 포함): 이익 = 매출 − (쿠폰+수수료+풀필먼트+광고+리뷰이벤트) + 재고손실보상,
  마진% = 이익/매출×100 소수 1자리(사사오입). **상품원가 미포함**(순이익은 원가·외부비용을 따로 뺌).

금액은 원 단위 정수만 받는다(쿠팡 파일값 그대로·앱이 수수료를 재계산하지 않음). 정수가 아니면 TypeError(조용한 변환 금지).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


def _won(name: str, v) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise TypeError(f"금액 '{name}' 은 원 단위 정수여야 함: {v!r}")
    return v


@dataclass(frozen=True)
class MpRevenue:
    settlement_target: int          # 정산대상액 E
    final_payout: int               # 최종지급예정액 = E − F


def mp_revenue(*, sales: int, seller_coupon: int, fee: int, myshop_fee: int = 0,
               deduction: int = 0) -> MpRevenue:
    """윙 매출내역: E = 매출 A − 판매자할인쿠폰 B(즉시+다운로드) − 판매수수료 C − 마이샵수수료 D, 최종 = E − 정산차감 F."""
    e = (_won("매출금액", sales) - _won("판매자할인쿠폰", seller_coupon) - _won("판매수수료", fee)
         - _won("마이샵수수료", myshop_fee))
    return MpRevenue(e, e - _won("정산차감", deduction))


def rg_payout(*, settlement_target: int, milkrun: int, ads: int, cfs: int) -> int:
    """로켓그로스 실지급 = 판매수수료리포트 정산대상액 − 밀크런 이용액 − 광고비 − CFS 요금.
    밀크런·광고비·CFS 는 별도 리포트 값(없으면 0 이 아니라 호출부가 조인 누락을 먼저 확인 — 함정 5)."""
    return (_won("정산대상액", settlement_target) - _won("밀크런", milkrun) - _won("광고비", ads)
            - _won("CFS", cfs))


@dataclass(frozen=True)
class RgProfit:
    cost: int                       # 비용 합계(쿠폰+수수료+풀필먼트+광고+리뷰이벤트 − 재고손실보상)
    profit: int                     # 이익 = 매출 − 비용
    margin_pct: float | None        # 이익/매출×100 소수 1자리. 매출 0 이면 정의 불가 → None(명시)


def rg_home_profit(*, sales: int, seller_coupon: int, fee: int, fulfillment: int, ads: int, review_event: int,
                   inventory_compensation: int = 0) -> RgProfit:
    """로켓그로스 홈 '이익'(VAT 포함). 매출이 0 이면 마진%는 정의되지 않아 None(0% 로 꾸미지 않음)."""
    cost = (_won("판매자할인쿠폰", seller_coupon) + _won("판매수수료", fee) + _won("풀필먼트서비스비", fulfillment)
            + _won("광고비", ads) + _won("리뷰이벤트", review_event)
            - _won("재고손실보상", inventory_compensation))
    s = _won("매출", sales)
    profit = s - cost
    margin = (float((Decimal(profit) * 100 / Decimal(s)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
              if s else None)
    return RgProfit(cost, profit, margin)
