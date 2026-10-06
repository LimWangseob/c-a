"""D2 소싱(Sourcing) — 신규 판매 상품 후보 발굴·분석(1단계·읽기 전용·일회성 조회).

아직 안 파는 "팔 만한 후보"를 키워드 관점에서 모아 수요·경쟁·마진으로 점수화한다.
읽기 전용 도메인(쿠팡/네이버에 쓰기 없음). 산출물은 값 객체(SourcingCandidate) 리스트뿐이라
화면 표/엑셀로 내보내거나(모델 A·1단계) 나중에 원장(모델 B·2단계)에 쌓을 수 있다.

계층(ARCHITECTURE §2·불변): L2 도메인은 L0(browser)·L1 조회 프리미티브만 호출한다.
호출 대상(전부 U2로 L1 재분류 완료·L1_CONTRACT §7-d):
- kw_suggest.collect_suggestions — 쿠팡 자동완성(연관검색어) = 후보 발굴 소스.
- kw_volume.NaverAdApi.related_keywords_multi — 네이버 월검색량(수요)·클릭·경쟁지수.
- kw_metrics.page1_competition — 쿠팡 1페이지 경쟁 신호(오가닉수·광고수·로켓비율).
점수 공식은 sourcing_score(순수 함수).

⚠ AI 후보 생성(kw_ai)은 L2(D1) 비즈니스 로직이라 도메인끼리 직접 import 금지(ARCHITECTURE §2).
따라서 1단계 후보 발굴은 **쿠팡 자동완성 + 시드 변형만** 쓴다(AI 없음). 설계 §6 초안의
`ai_key` 파라미터는 계층 규칙 우선이라 **자리만 두되 미사용**(향후 L3 조립이 AI 후보를 넘겨줄 자리).

naver·browser 는 조립(L3)이 생성·주입한다(도메인은 세션을 직접 열지 않음·단일 브라우저 원칙).
폴백 금지([[no-silent-fallback-principle]]): 결과없음·검색량 미확인은 note로 명시, silent 0/None 금지.
예외(SuggestError·RankBlocked 등)는 호출부로 전파한다.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import kw_metrics, kw_suggest, kw_volume
from .sourcing_score import sourcing_score


@dataclass
class SourcingCandidate:
    keyword: str
    volume: int               # 네이버 월검색량(수요)
    clicks: float             # 네이버 월평균클릭 합(PC+모바일)
    comp_idx: str | None      # 네이버 경쟁지수(없으면 None)
    organic_count: int        # 쿠팡 1P 오가닉 수(kw_metrics)
    ad_count: int             # 쿠팡 1P 광고 수
    rocket_ratio: float       # 오가닉 중 로켓 비율(판매자배송 진입 난이도)
    est_margin: float | None  # 사람 입력 기대마진(1단계 조회엔 없음=None)
    score: float              # 소싱 종합 점수(수요·경쟁·마진)
    note: str                 # '결과없음'·'검색량 미확인' 등(정상=빈 문자열)


def _norm(text: str) -> str:
    """키워드 비교용 정규화 — 네이버는 공백을 제거해 조회하므로 매칭도 공백 제거."""
    return (text or "").replace(" ", "").strip()


def _seed_variants(seed: str) -> list[str]:
    """시드를 여러 각도(원형·공백제거)로 넓혀 자동완성 접두 다양화. 순서보존 중복제거."""
    s = (seed or "").strip()
    out: dict[str, None] = {}
    for v in (s, s.replace(" ", "")):
        v = v.strip()
        if v:
            out.setdefault(v, None)
    return list(out)


def _collect_candidates(seed: str, browser, log=None) -> list[str]:
    """후보 키워드 수집 = 시드 변형 + 쿠팡 자동완성(연관어). 순서보존 중복제거.

    시드 자신도 후보에 포함(자동완성이 시드를 안 돌려줄 수 있어 보장).
    """
    variants = _seed_variants(seed)
    if not variants:
        return []
    suggestions = kw_suggest.collect_suggestions(browser, variants, log=log)
    ordered: dict[str, None] = {}
    for kw in (*variants, *suggestions):
        kw = (kw or "").strip()
        if kw:
            ordered.setdefault(kw, None)
    return list(ordered)


def _volume_map(naver, candidates: list[str]) -> dict[str, kw_volume.KeywordVolume]:
    """후보 키워드들의 네이버 월검색량을 한 번에 조회해 정규화 키 → KeywordVolume."""
    if not candidates:
        return {}
    volumes = naver.related_keywords_multi(candidates)
    return {_norm(kv.keyword): kv for kv in volumes}


def _measure(keyword: str, kv: kw_volume.KeywordVolume | None, browser,
             est_margin: float | None) -> SourcingCandidate:
    """단일 키워드의 수요(네이버 kv)·경쟁(쿠팡 1P)을 모아 점수화한 후보 객체."""
    comp = kw_metrics.page1_competition(browser, keyword)
    notes: list[str] = []
    if not comp.found:
        notes.append("결과없음")                       # 쿠팡 1P 미로드 — silent 0 금지
    if kv is None:
        notes.append("검색량 미확인")                   # 네이버 연관어에 없음 — silent 0 금지
    volume = kv.total if kv else 0
    clicks = kv.total_clicks if kv else 0.0
    comp_idx = (kv.comp_idx or None) if kv else None
    score = sourcing_score(volume, comp.rocket_ratio, comp.ad_count, est_margin)
    return SourcingCandidate(
        keyword=keyword,
        volume=volume,
        clicks=clicks,
        comp_idx=comp_idx,
        organic_count=comp.organic_count,
        ad_count=comp.ad_count,
        rocket_ratio=comp.rocket_ratio,
        est_margin=est_margin,
        score=score,
        note=" · ".join(notes),
    )


def analyze_keyword(keyword: str, naver, browser) -> SourcingCandidate:
    """단일 키워드의 수요·경쟁 신호만(마진/AI 없이). 점수는 마진 None 기준."""
    kw = (keyword or "").strip()
    if not kw:
        raise ValueError("analyze_keyword: 키워드가 비었습니다")
    kv = _volume_map(naver, [kw]).get(_norm(kw))
    return _measure(kw, kv, browser, est_margin=None)


def discover_candidates(
    seed: str, naver, browser, ai_key: str | None = None,
    *, top_n: int | None = None, log=None,
) -> list[SourcingCandidate]:
    """시드 키워드 → 후보 수집(시드 변형·쿠팡 자동완성) → 네이버 검색량·쿠팡 1P 경쟁 수집 →
    소싱 점수 내림차순 랭킹.

    ai_key: 설계 §6 시그니처 호환용 자리(미사용). AI 후보 생성(kw_ai)은 L2(D1) 로직이라
    계층 규칙상 D2가 직접 못 부름 — 1단계는 자동완성+시드 변형만으로 후보를 모은다.
    top_n: 주면 상위 n개만 반환(랭킹 후 절단).
    """
    candidates = _collect_candidates(seed, browser, log=log)
    if not candidates:
        if log:
            log(f"[소싱] 시드 '{seed}' — 후보 없음")
        return []
    if log:
        log(f"[소싱] 후보 {len(candidates)}개 수집 — 검색량·경쟁 측정 시작")
    vol_map = _volume_map(naver, candidates)
    results = [
        _measure(kw, vol_map.get(_norm(kw)), browser, est_margin=None)
        for kw in candidates
    ]
    results.sort(key=lambda c: c.score, reverse=True)
    if top_n is not None:
        results = results[:top_n]
    if log:
        log(f"[소싱] 랭킹 완료 — {len(results)}개 반환")
    return results
