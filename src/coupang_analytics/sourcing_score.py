"""소싱 후보 점수 공식 — 순수 함수(의존 0·결정적).

소싱은 "신규로 팔 만한 틈새"를 찾는 일이라, 점수는 세 신호를 합친다.
- 수요↑: 네이버 월검색량(volume)이 많을수록 가점.
- 경쟁↓: 쿠팡 1페이지 로켓비율(rocket_ratio)·광고수(ad_count)가 높을수록 감점
  (로켓비율↑=판매자배송 진입 어려움, 광고수↑=경쟁 과열 — DOMAIN_D2_SOURCING §7).
- 마진↑: 사람이 입력한 기대마진(est_margin·비율 0~1 가정)이 높을수록 가점. 없으면(None) 기여 0.

가중치는 모듈 상수. 공식은 단조(monotone)·결정적이라 오프라인 테스트로 랭킹을 고정할 수 있다.
"""
from __future__ import annotations

# 수요: 월검색량을 이 값으로 나눠 스케일(검색량 1,000 ≈ 1점).
_VOLUME_SCALE = 1000.0

# 경쟁 감점 가중(클수록 경쟁에 민감).
_ROCKET_WEIGHT = 40.0   # rocket_ratio(0~1) 1점당 감점
_AD_WEIGHT = 2.0        # 광고 1개당 감점

# 마진 가점 가중(est_margin 비율 1.0 == 이 점수).
_MARGIN_WEIGHT = 30.0


def sourcing_score(
    volume: int,
    rocket_ratio: float,
    ad_count: int,
    est_margin: float | None,
) -> float:
    """소싱 종합 점수(높을수록 유망). 수요 - 경쟁 + 마진.

    - volume: 네이버 월검색량(수요).
    - rocket_ratio: 쿠팡 1P 오가닉 중 로켓 비율(0~1·경쟁).
    - ad_count: 쿠팡 1P 광고 수(경쟁).
    - est_margin: 사람 입력 기대마진 비율(없으면 None=마진 기여 0).
    """
    demand = volume / _VOLUME_SCALE
    competition = rocket_ratio * _ROCKET_WEIGHT + ad_count * _AD_WEIGHT
    margin_bonus = (est_margin or 0.0) * _MARGIN_WEIGHT
    return round(demand - competition + margin_bonus, 4)
