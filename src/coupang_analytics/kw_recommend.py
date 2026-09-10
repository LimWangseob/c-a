"""키워드 추천/선정 — AI 용도·핵심(core) + AI 조합생성 + 핵심/연관 판정 + 핵심 밀착 선정.

방법론(메모리 keyword-methodology-ai-anchor):
1. analyze_product → 용도·핵심(core)·앵커.
2. 후보 조립(_assemble_candidates):
   - 앵커 네이버 연관확장(≥KW_MIN_VOLUME=500) — 넓은 맥락.
   - (배치) AI 조합생성(core×속성) → 각 검색량 네이버 측정 → **KW_TRACK_MIN_VOLUME(30) 이상** 추가.
     네이버 연관에 없고 검색량 500 미만이라 과거 놓치던 롱테일(캠핑화로테이블 등)을 살린다.
3. judge_keywords → 핵심/연관/탈락(형제상품군·거대일반어·타사 브랜드 복합어 탈락).
4. Keyword Score(관련성·구매의도·검색량)로 상위 압축 → 압축분만 쿠팡 실노출 측정 → 노출점수·등급 →
   AI 최종선정(select_keywords)이 점수·노출·클릭·경쟁도·관련도를 종합해 N개 우선순위 확정.
(진단은 순위 조회 흐름에서 옵션별로 기록. 선정단계에서 잰 순위는 워크북에 재사용.)

AI 없이는 도출 불가(폴백 폐지) — 키 미설정·호출 실패 시 KeywordAIError 로 상위에서 중단.
'키워드 추천' 탭(_ai_candidates→_rank_candidates, 쿠팡 1P 경쟁 점수)은 조합생성 없이 500밴드 유지.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field

from . import config
from .browser import WingBrowser
from .kw_ai import analyze_product, generate_keywords, judge_keywords, select_keywords
from .kw_metrics import page1_competition
from .kw_suggest import SuggestError, collect_suggestions
from .kw_volume import KeywordVolume, NaverAdApi
from .rank import RankBlocked, warmup


@dataclass
class KeywordRec:
    keyword: str
    volume: int          # 월 검색량(총, 네이버)
    clicks: float        # 월 클릭수(총, 아이템스카우트 지표)
    comp_idx: str        # 경쟁정도 높음/중간/낮음 (아이템스카우트)
    ad_depth: int        # 광고 노출 개수(네이버, 아이템스카우트 '광고')
    rocket_ratio: float  # 쿠팡 1P 로켓비율
    ad_count: int        # 쿠팡 1P 광고수
    score: float
    note: str = ""       # 수집 이슈(차단/결과없음) 표기


@dataclass
class TrackKeyword:
    """추적 대상으로 확정된 키워드 + 선정 근거 지표(Keyword Score 페이즈 B)."""
    keyword: str
    volume: int                    # 월 검색량(총)
    mobile_share: float            # 모바일 비중(%)
    relevance: str = ""            # 핵심(바로 이 상품)/연관(관련되나 정확히 그 상품은 아님)
    clicks: float = 0.0            # 월 평균 클릭수(총) — 구매의도 신호
    comp_idx: str = ""             # 네이버 경쟁정도 높음/중간/낮음
    score: float = 0.0             # Keyword Score(100점, 실제 만점 95 — 추세 데이터 없음)
    grade: str = ""                # A/B/C/D
    exposure_best: int | None = None       # 쿠팡 오가닉 최상위 순위(옵션 통틀어), 미노출 None
    ranks_pc: dict = field(default_factory=dict)      # {옵션라벨: PC순위 or None} — 선정단계 측정 재사용
    ranks_mobile: dict = field(default_factory=dict)  # {옵션라벨: 모바일순위 or None}
    role: str = ""                 # REP(대표)/SALES(수요)/GROWTH(성장)/DEFENSE(방어) — AI 최종선정 역할


def _score(volume: int, rocket_ratio: float, ad_count: int) -> float:
    """검색량↑ 좋음, 로켓비율↑·광고수↑ 나쁨."""
    return (config.KW_W_VOLUME * math.log10(volume + 1)
            - config.KW_W_ROCKET * rocket_ratio
            - config.KW_W_AD * (ad_count / 10.0))


def _mobile_share(v: KeywordVolume) -> float:
    return round(v.mobile / v.total * 100, 1) if v.total else 0.0


def _norm(s: str) -> str:
    return s.replace(" ", "").casefold()


# ── Keyword Score(100점) — 후보 지표 종합 (페이즈 B) ────────────────
# 관련성35(핵심/연관) + 구매의도25(클릭·롱테일) + 검색량20 + 쿠팡노출15 + 추세5(데이터 없어 0).
# 압축(부분점수=노출 제외)으로 상위 후보만 쿠팡 실노출을 측정한 뒤, 노출점수를 더해 전체점수·등급을 낸다.
def _score_relevance(tier: str, match: float = 1.0) -> float:
    """관련성 점수 = 티어(핵심/연관) 기본점 × AI 적합도(match) 미세조정.

    티어가 굵은 축(핵심 35 / 연관 19.25)이고, match(0~1)로 티어 내 순서를 다듬는다
    (match=0이면 0.7배, 1이면 1.0배). 구매의도(intent)는 별도로 네이버 실클릭에서 측정한다.
    """
    if tier == "핵심":
        base = config.KW_SCORE_W_RELEVANCE
    elif tier == "연관":
        base = config.KW_SCORE_W_RELEVANCE * 0.55
    else:
        return 0.0
    return base * (0.7 + 0.3 * max(0.0, min(match, 1.0)))


def _score_volume(volume: int) -> float:
    return min(math.log10(volume + 1) / math.log10(config.KW_MAX_VOLUME), 1.0) * config.KW_SCORE_W_VOLUME


def _score_intent(clicks: float, keyword: str) -> float:
    """구매의도 = 월클릭수(로그, 비중 72%) + 롱테일성(키워드 길이, 비중 28%)."""
    click_part = min(math.log10(clicks + 1) / 3.0, 1.0) * (config.KW_SCORE_W_INTENT * 0.72)  # log10(1000)=3
    chars = len(keyword.replace(" ", ""))
    long_part = min(chars / 8.0, 1.0) * (config.KW_SCORE_W_INTENT * 0.28)
    return click_part + long_part


def _score_exposure(best_rank: int | None) -> float:
    """쿠팡 오가닉 최상위 순위 → 노출점수. 미노출(None)=0."""
    if best_rank is None:
        return 0.0
    w = config.KW_SCORE_W_EXPOSURE
    if best_rank <= 3:
        return w
    if best_rank <= 10:
        return w * 0.8
    if best_rank <= config.RANK_GOOD_THRESHOLD:   # ≤20
        return w * 0.53
    if best_rank <= config.RANK_SCAN_MAX:         # ≤50
        return w * 0.27
    return 0.0


def _partial_score(kv: KeywordVolume, tier: str, match: float = 1.0) -> float:
    """노출 측정 전 점수(압축용) — 관련성(티어×match)+구매의도+검색량+추세(0)."""
    return (_score_relevance(tier, match) + _score_intent(kv.total_clicks, kv.keyword)
            + _score_volume(kv.total))


def _keyword_score(kv: KeywordVolume, tier: str, match: float, best_rank: int | None) -> float:
    return _partial_score(kv, tier, match) + _score_exposure(best_rank)


def _grade(score: float) -> str:
    if score >= config.KW_GRADE_A:
        return "A"
    if score >= config.KW_GRADE_B:
        return "B"
    if score >= config.KW_GRADE_C:
        return "C"
    return "D"


def comp_from_idx(comp_idx: str) -> float | None:
    """네이버 경쟁정도(높음/중간/낮음) → 공략우선순위용 공급밀도 근사(작을수록 진입 유리)."""
    return {"높음": 3.0, "중간": 2.0, "낮음": 1.0}.get((comp_idx or "").strip())


def _timed(_logf, label, fn, *args, **kwargs):
    """호출 소요시간을 [시간] 로그로 남긴다(어느 AI/네이버 단계가 병목인지 실측용).

    첫 인자명을 _logf 로 둔 이유: 감싸는 함수가 log= 키워드를 받을 때(예: collect_suggestions) 이름 충돌 방지.
    """
    t = time.time()
    r = fn(*args, **kwargs)
    if _logf:
        _logf(f"  [시간] {label} {time.time() - t:.1f}s")
    return r


def _assemble_candidates(title: str, naver: NaverAdApi, ai_key: str | None, generate: bool,
                         browser=None, log=None
                         ) -> tuple[str, str, list[str], list[str], list[str],
                                    list[KeywordVolume], dict[str, str], dict[str, float]]:
    """후보 조립(여러 방안) → 핵심/연관 판정.

    반환: (core, use, identities, attributes, 앵커, 통과 KeywordVolume, {키워드:연관도}, {키워드:match}).

    후보 소스(generate=True 배치 추적):
      ① 앵커 네이버 연관확장(≥KW_MIN_VOLUME=500) — 넓은 맥락.
      ② **쿠팡 자동완성**(browser 있을 때): core·identities를 시드로 쿠팡 실수요 검색어 → 네이버로 검색량 측정(≥30).
      ③ AI 조합 생성(정체성×속성) → 검색량 측정(≥30) — 네이버 연관에 없는 롱테일.
      ④ **네이버 2단계 확장**: 1차 후보 중 검색량 상위 KW_EXPAND2_N개를 재시드로 다시 연관조회(≥30).
    핵심(core)은 후보에 있으면 하한과 무관하게 추적 대상. AI 실패 시 KeywordAIError 전파.
    자동완성 소스 실패는 로그로 남기고 그 소스만 건너뛴다(다른 소스로 계속).
    """
    use, core, identities, attributes, anchors = _timed(log, "AI 제목분석", analyze_product,
                                                        title, api_key=ai_key)
    pool: dict[str, KeywordVolume] = {}
    for c in _timed(log, "네이버 앵커연관", naver.related_keywords_multi, anchors):   # ① 넓은 연관(≥500)
        if c.total >= config.KW_MIN_VOLUME:
            pool.setdefault(c.keyword, c)
    if generate:
        if browser is not None:                                     # ② 쿠팡 자동완성(실수요)
            seeds = list(dict.fromkeys(s for s in ([core] + identities) if s))   # 순서보존 중복제거
            try:
                suggests = _timed(log, "쿠팡 자동완성", collect_suggestions, browser, seeds, log=log)
            except SuggestError as exc:
                suggests = []
                if log:
                    log(f"  [자동완성] 실패 — {exc} (이 소스만 건너뜀, 다른 소스로 계속)")
            sug_norm = {_norm(s) for s in suggests}
            if suggests:
                for c in _timed(log, "네이버 자동완성연관", naver.related_keywords_multi, suggests):
                    if _norm(c.keyword) in sug_norm and c.total >= config.KW_TRACK_MIN_VOLUME:
                        pool.setdefault(c.keyword, c)
        gen = _timed(log, "AI 조합생성", generate_keywords, title, use, identities, attributes,
                     api_key=ai_key)  # ③
        gen_norm = {_norm(g) for g in gen}
        for c in _timed(log, "네이버 조합연관", naver.related_keywords_multi, gen):   # 생성어 실검색량 측정
            if _norm(c.keyword) in gen_norm and c.total >= config.KW_TRACK_MIN_VOLUME:
                pool.setdefault(c.keyword, c)
        top = sorted(pool.values(), key=lambda c: c.total, reverse=True)[:config.KW_EXPAND2_N]
        exp_seeds = [c.keyword for c in top]                       # ④ 네이버 2단계 확장(상위 재시드)
        if exp_seeds:
            for c in _timed(log, "네이버 2단계연관", naver.related_keywords_multi, exp_seeds):
                if c.total >= config.KW_TRACK_MIN_VOLUME:
                    pool.setdefault(c.keyword, c)
    judged = _timed(log, "AI 핵심연관판정", judge_keywords, title, [c.keyword for c in pool.values()],
                    api_key=ai_key, use=use, core=core, identities=identities)  # {키워드:(티어,match)}
    tiers = {k: t for k, (t, _m) in judged.items()}
    matches = {k: m for k, (_t, m) in judged.items()}
    if core and core in pool and core not in tiers:                # 핵심은 무조건 추적 대상
        tiers[core] = "핵심"
        matches.setdefault(core, 1.0)
    relevant = [pool[name] for name in pool if name in tiers]
    return core, use, identities, attributes, anchors, relevant, tiers, matches


def _ai_candidates(title: str, naver: NaverAdApi,
                   ai_key: str | None) -> tuple[str, str, list[str], list[str], list[KeywordVolume], dict[str, str]]:
    """'키워드 추천' 탭용 — 앵커 연관확장만(조합 생성·자동완성 없음, 500 밴드 유지)."""
    return _assemble_candidates(title, naver, ai_key, generate=False)


def select_keywords_light(title: str, naver: NaverAdApi, ai_key: str | None,
                          n: int | None = None, browser=None, log=None,
                          measure_ranks=None, exclude: set[str] | None = None) -> list[TrackKeyword]:
    """배치 추적용 키워드 선정(페이즈 B — 점수 압축 + 쿠팡 실노출 승격 + AI 종합선정).

    1) 후보 수집(앵커연관 + 쿠팡 자동완성 + AI 조합생성 + 네이버 2단계확장) → 핵심/연관 판정.
    2) **부분점수(관련성·구매의도·검색량)로 상위 KW_SCORE_POOL_N개 압축**(핵심 core는 항상 포함).
    3) 압축분만 `measure_ranks`로 **쿠팡 실노출(오가닉 순위) 측정** → 노출점수 반영 → 전체 100점·등급.
       (측정한 옵션별 순위는 TrackKeyword에 실어 호출부가 워크북 순위에 **재사용** — 재조회 없음.)
    4) **AI 최종선정**(select_keywords): 점수·등급·노출·클릭·경쟁도·관련도를 종합해 n개 우선순위 확정.

    measure_ranks(keywords: list) -> {키워드: (ranks_pc, ranks_mobile)} 각 {옵션라벨: 순위 or None}.
    여러 키워드를 **한 번에**(병렬 fetch) 측정한다. None이면 노출점수 없이 부분점수만으로 선정(예: 라이브 검증).
    exclude 는 통계 유지 중 **발굴 추가**용으로, 이미 추적 중인 키워드를 후보에서 빼 **새 키워드만** n개 뽑는다
    (기존은 호출부가 동결). AI 없으면 KeywordAIError.
    """
    core, use, identities, _attributes, _anchors, relevant, tiers, matches = _assemble_candidates(
        title, naver, ai_key, generate=True, browser=browser, log=log)
    if exclude:   # 통계 유지 중 발굴 추가 — 이미 추적 중인 키워드는 후보에서 제외(새 것만 뽑음)
        relevant = [c for c in relevant if c.keyword not in exclude]
        tiers = {k: v for k, v in tiers.items() if k not in exclude}
        matches = {k: v for k, v in matches.items() if k not in exclude}
    if not relevant:
        return []
    # (2) 부분점수로 압축 — 요청량·IP차단 제어 위해 상위 소수만 쿠팡 노출 측정
    ranked = sorted(relevant, key=lambda c: _partial_score(c, tiers.get(c.keyword, ""),
                                                           matches.get(c.keyword, 1.0)), reverse=True)
    pool = ranked[:config.KW_SCORE_POOL_N]
    core_tracked = bool(exclude) and core in exclude   # 발굴 추가에서 core가 이미 추적중이면 강제포함 불필요
    if core and not core_tracked and core in {c.keyword for c in relevant} \
            and core not in {c.keyword for c in pool}:
        pool = pool[:config.KW_SCORE_POOL_N - 1] + [next(c for c in relevant if c.keyword == core)]
    if log:
        log(f"  [점수] 후보 {len(relevant)}개 → 압축 {len(pool)}개 노출측정: {[c.keyword for c in pool]}")
    # (3) 압축분 쿠팡 실노출 **일괄 측정**(measure_ranks가 여러 키워드를 병렬 fetch로 한 번에) → 노출점수·등급
    batch: dict[str, tuple[dict, dict]] = {}
    if measure_ranks is not None:
        batch = measure_ranks([c.keyword for c in pool])   # {키워드: (ranks_pc, ranks_mobile)}
    meta: dict[str, tuple[float, str, int | None, dict, dict]] = {}
    for c in pool:
        ranks_pc, ranks_mobile = batch.get(c.keyword, ({}, {}))
        best = min([v for v in (*ranks_pc.values(), *ranks_mobile.values()) if v], default=None)
        if measure_ranks is not None and log:
            log(f"  [노출측정] '{c.keyword}' 쿠팡 오가닉 노출순위: {rank_label(best)}")
        s = _keyword_score(c, tiers.get(c.keyword, ""), matches.get(c.keyword, 1.0), best)
        meta[c.keyword] = (round(s, 1), _grade(s), best, ranks_pc, ranks_mobile)
    # (4) AI 최종선정 — 점수·등급·노출까지 종합해 우선순위 확정
    items = [{"keyword": c.keyword, "volume": c.total, "mobile": _mobile_share(c),
              "clicks": round(c.total_clicks, 1), "comp": c.comp_idx,
              "relevance": tiers.get(c.keyword, ""), "score": meta[c.keyword][0],
              "grade": meta[c.keyword][1],
              "exposure": meta[c.keyword][2] if meta[c.keyword][2] else "미노출"} for c in pool]
    picked = _timed(log, "AI 최종선정", select_keywords, title, items, use=use, core=core,
                    identities=identities, n=n, api_key=ai_key)   # [(키워드, 역할)]
    kv = {c.keyword: c for c in pool}
    out: list[TrackKeyword] = []
    for kw, role in picked:
        c = kv[kw]
        s, g, best, rpc, rmo = meta[kw]
        out.append(TrackKeyword(kw, c.total, _mobile_share(c), relevance=tiers.get(kw, ""),
                                clicks=round(c.total_clicks, 1), comp_idx=c.comp_idx,
                                score=s, grade=g, exposure_best=best, role=role,
                                ranks_pc=rpc, ranks_mobile=rmo))
    return out


def recommend(seed_keyword: str, naver: NaverAdApi, browser: WingBrowser,
              top_n: int | None = None) -> list[KeywordRec]:
    """단일 시드 키워드로 추천(점수 내림차순) — '키워드 추천' 탭의 직접 시드 입력용."""
    top_n = config.KW_TOP_N if top_n is None else top_n
    return _rank_candidates(naver.related_keywords(seed_keyword), browser, top_n)


def recommend_from_title(title: str, naver: NaverAdApi, browser: WingBrowser,
                         ai_key: str | None, top_n: int | None = None) -> list[KeywordRec]:
    """상품 제목 → AI 앵커+판정 후보 → 쿠팡 1P 경쟁 점수화 → 상위 추천('키워드 추천' 탭).

    AI 없으면 KeywordAIError(토큰 폴백 폐지).
    """
    top_n = config.KW_TOP_N if top_n is None else top_n
    relevant = _ai_candidates(title, naver, ai_key)[5]   # (core,use,identities,attributes,anchors,relevant,tiers,matches)
    return _rank_candidates(relevant, browser, top_n)


def _rank_candidates(candidates: list[KeywordVolume], browser: WingBrowser, top_n: int) -> list[KeywordRec]:
    """후보(KeywordVolume) → 검색량 밴드 필터 → 쿠팡 1P 경쟁 수집 → 점수화 → 상위 top_n.

    '키워드 추천' 탭 전용이므로 황금키워드 정책(하한+상한 밴드)을 그대로 적용한다.
    """
    banded = [c for c in candidates if config.KW_MIN_VOLUME <= c.total <= config.KW_MAX_VOLUME]
    picked = sorted(banded, key=lambda c: c.total, reverse=True)[:config.KW_CANDIDATE_LIMIT]

    warmup(browser)
    recs: list[KeywordRec] = []
    for c in picked:
        note = ""
        rocket_ratio, ad_count = 0.0, 0
        try:
            comp = page1_competition(browser, c.keyword)
            if comp.found:
                rocket_ratio, ad_count = comp.rocket_ratio, comp.ad_count
            else:
                note = "결과없음"
        except RankBlocked:
            note = "차단됨"
        recs.append(KeywordRec(
            keyword=c.keyword, volume=c.total, clicks=c.total_clicks, comp_idx=c.comp_idx,
            ad_depth=c.pl_avg_depth, rocket_ratio=rocket_ratio, ad_count=ad_count,
            score=_score(c.total, rocket_ratio, ad_count), note=note,
        ))
        time.sleep(random.uniform(config.KW_QUERY_DELAY_MIN, config.KW_QUERY_DELAY_MAX))

    recs.sort(key=lambda r: r.score, reverse=True)
    return recs[:top_n]


# ── 처방(진단) 헬퍼 — 순위 결과를 판매전략으로 연결 ──────────────────
def rank_label(rank: int | None) -> str:
    """순위 표시 — 스캔 상한 안이면 그 순위, 밖(None)이면 'N위 밖'.

    None 은 '미노출(존재하지 않음)'이 아니라 **스캔 상한(RANK_SCAN_MAX) 밖 = 뒤쪽 순위**를 뜻한다.
    진짜 미노출(오가닉 구조상 안 걸림)은 제목미포함일 때이며 diagnose_exposure 가 따로 판정한다.
    """
    return str(rank) if rank else f"{config.RANK_SCAN_MAX}위 밖"


def keyword_in_title(keyword: str, title: str) -> bool:
    """이 키워드가 현재 노출제목에 담겨 있는가(띄어쓰기 무시, 구성단어 모두 포함도 인정)."""
    t = (title or "").replace(" ", "")
    k = keyword.replace(" ", "")
    if k in t:
        return True
    toks = [w for w in keyword.split() if w]
    return bool(toks) and all(w in t for w in toks)


def diagnose_exposure(has_title: bool, rank_pc: int | None, rank_mobile: int | None) -> str:
    """제목포함여부 × 현재순위 → 처방. (노출불가/마케팅필요/양호)

    - 제목에 없고 스캔밖     → 노출불가(제목미포함): 오가닉 구조상 안 걸림 → 상품명에 키워드 추가해야 노출
    - 제목에 없는데 노출됨    → 상세/태그로 노출(제목추가 권장)
    - 제목에 있고 스캔밖      → 마케팅필요(N위 밖): 걸리긴 하나 뒤쪽 순위 → 광고·리뷰로 끌어올림
    - 제목에 있고 상위        → 양호
    """
    best = min([r for r in (rank_pc, rank_mobile) if r is not None], default=None)
    if not has_title:
        return "노출불가(제목미포함)" if best is None else "노출됨(제목미포함·제목추가권장)"
    if best is None:
        return f"마케팅필요({config.RANK_SCAN_MAX}위 밖)"
    if best <= config.RANK_GOOD_THRESHOLD:
        return "양호"
    return "마케팅필요(하위)"


def attack_priority(volume: int, comp: float | None) -> int:
    """공략 우선순위 점수 = 검색량 ÷ 경쟁강도(수요/공급밀도). 클수록 먼저 공략.

    경쟁강도(=상품수÷검색량) 미상이면 검색량만으로 근사한다.
    """
    if comp and comp > 0:
        return round(volume / comp)
    return volume
