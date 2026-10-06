"""D2 소싱 오프라인 검증 — 설계(DOMAIN_D2_SOURCING §5·§6·§7) 기대 동작을 가짜 응답으로 확인.

로그인·실 API·네트워크 없음(결정적). 후보 수집(시드 변형+자동완성 중복제거)·네이버 검색량 매칭·
쿠팡 1P 경쟁 수집·소싱 점수 내림차순 랭킹·경계(빈 시드·차단/결과없음·검색량 미확인·마진 None)·
top_n 절단·analyze_keyword 단일·sourcing_score 순수 공식 단조성.

L1 조회 프리미티브(kw_suggest.collect_suggestions·kw_metrics.page1_competition)는 browser/네트워크를
건드리므로 **그 호출 지점(seam)을 가짜로 치환**(모킹된 쿠팡 응답), 네이버는 FakeNaver 주입한다.
반환 응답 객체는 실제 dataclass(KeywordVolume·KeywordCompetition)에 캔값을 채워 쓴다.

    python tools/verify_sourcing_offline.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics import kw_metrics as KM  # noqa: E402
from coupang_analytics import kw_volume as KV  # noqa: E402
from coupang_analytics import sourcing as SRC  # noqa: E402
from coupang_analytics.sourcing_score import sourcing_score  # noqa: E402

BROWSER = object()  # 센티넬 — L1 조회를 가짜로 치환하므로 역참조되지 않음


def ok(msg):
    print(f"  ✔ {msg}")


# ── 캔 데이터(모킹된 응답) ──────────────────────────────────────────
def _kv(keyword, pc, mobile, comp_idx):
    return KV.KeywordVolume(keyword=keyword, pc=pc, mobile=mobile, comp_idx=comp_idx,
                            pc_clicks=10.0, mobile_clicks=20.0, pl_avg_depth=3)


# 네이버 월검색량(정규화 키=공백제거). '미니화로'는 일부러 빠뜨림 → '검색량 미확인'.
_VOLUMES = {
    "캠핑테이블": _kv("캠핑테이블", 20000, 10000, "낮음"),   # total 30000
    "접이식테이블": _kv("접이식테이블", 7000, 5000, "높음"),  # total 12000
    "우드테이블": _kv("우드테이블", 3000, 5000, "중간"),      # total 8000
}

# 쿠팡 1P 경쟁(found=True). '미니화로'는 결과없음(found=False).
_COMP = {
    "캠핑테이블": KM.KeywordCompetition("캠핑테이블", organic_count=10, ad_count=1, rocket_count=1, found=True),
    "접이식테이블": KM.KeywordCompetition("접이식테이블", organic_count=10, ad_count=3, rocket_count=5, found=True),
    "우드테이블": KM.KeywordCompetition("우드테이블", organic_count=10, ad_count=0, rocket_count=0, found=True),
}


class FakeNaver:
    """related_keywords_multi만 구현 — 캔 테이블에 있는 후보만 돌려줌(없으면 제외)."""

    def related_keywords_multi(self, hints):
        out = []
        for h in hints:
            kv = _VOLUMES.get(h.replace(" ", ""))
            if kv:
                out.append(kv)
        return out


def _fake_collect(browser, seeds, log=None):
    """시드 변형 → 쿠팡 자동완성 후보(캔). 시드 중복·무검색량 후보 포함."""
    assert browser is BROWSER
    return ["접이식테이블", "우드테이블", "캠핑테이블", "미니화로"]


def _fake_page1(browser, keyword):
    assert browser is BROWSER
    return _COMP.get(keyword, KM.KeywordCompetition(keyword, 0, 0, 0, found=False))


def _install_stubs():
    SRC.kw_suggest.collect_suggestions = _fake_collect
    SRC.kw_metrics.page1_competition = _fake_page1


# ── 시나리오 ──────────────────────────────────────────────────────
def t1_discover_ranking():
    print("[SRC1] 발굴·랭킹 — 후보 수집·점수 내림차순·필드 매핑")
    res = SRC.discover_candidates("캠핑테이블", FakeNaver(), BROWSER)
    kws = [c.keyword for c in res]
    # 후보 = 시드변형(캠핑테이블) + 자동완성(접이식·우드·캠핑테이블 dup·미니화로) 중복제거 = 4개
    assert set(kws) == {"캠핑테이블", "접이식테이블", "우드테이블", "미니화로"}, kws
    # 점수: 캠핑테이블 30-(0.1*40+1*2)=24 · 우드 8-0=8 · 미니화로 0 · 접이식 12-(0.5*40+3*2)=-14
    assert kws == ["캠핑테이블", "우드테이블", "미니화로", "접이식테이블"], kws
    top = res[0]
    assert top.volume == 30000 and top.clicks == 30.0 and top.comp_idx == "낮음"
    assert top.organic_count == 10 and top.ad_count == 1 and abs(top.rocket_ratio - 0.1) < 1e-9
    assert top.score == 24.0 and top.est_margin is None and top.note == "", top
    # 점수는 내림차순 단조
    scores = [c.score for c in res]
    assert scores == sorted(scores, reverse=True), scores
    ok("후보 4개 수집·점수 내림차순·필드/매핑 정확")


def t2_blank_seed():
    print("[SRC2] 빈 시드 — 후보 없음·네이버 호출 0")
    class Boom:
        def related_keywords_multi(self, hints):
            raise AssertionError("빈 시드인데 네이버를 불렀다")
    assert SRC.discover_candidates("   ", Boom(), BROWSER) == []
    ok("빈 시드 → [] (네이버 미호출)")


def t3_notes_boundary():
    print("[SRC3] 경계 note — 결과없음·검색량 미확인(silent 0 금지)")
    res = SRC.discover_candidates("캠핑테이블", FakeNaver(), BROWSER)
    mini = next(c for c in res if c.keyword == "미니화로")
    assert mini.note == "결과없음 · 검색량 미확인", mini.note
    assert mini.volume == 0 and mini.organic_count == 0 and mini.score == 0.0
    # 검색량만 없는 경우(쿠팡은 정상) note='검색량 미확인'만
    class OnlyComp:
        def related_keywords_multi(self, hints):
            return []
    SRC.kw_metrics.page1_competition = lambda b, k: KM.KeywordCompetition(k, 5, 0, 0, found=True)
    one = SRC.analyze_keyword("우드테이블", OnlyComp(), BROWSER)
    assert one.note == "검색량 미확인" and one.organic_count == 5, one
    _install_stubs()  # 복구
    ok("결과없음·검색량 미확인 note 명시·값 공란 처리")


def t4_top_n():
    print("[SRC4] top_n — 랭킹 후 상위 n개만")
    res = SRC.discover_candidates("캠핑테이블", FakeNaver(), BROWSER, top_n=2)
    assert [c.keyword for c in res] == ["캠핑테이블", "우드테이블"], res
    ok("top_n=2 → 상위 2개")


def t5_analyze_single():
    print("[SRC5] analyze_keyword — 단일 키워드 수요·경쟁(마진 None)")
    c = SRC.analyze_keyword("캠핑테이블", FakeNaver(), BROWSER)
    assert c.keyword == "캠핑테이블" and c.volume == 30000 and c.est_margin is None
    assert c.score == 24.0 and c.note == "", c
    try:
        SRC.analyze_keyword("  ", FakeNaver(), BROWSER)
    except ValueError:
        pass
    else:
        raise AssertionError("빈 키워드인데 ValueError 안 남")
    ok("단일 조회·빈 키워드 ValueError")


def t6_score_pure():
    print("[SRC6] sourcing_score — 순수 공식 단조성·마진 None==0")
    assert sourcing_score(10000, 0.0, 0, None) == 10.0
    assert sourcing_score(20000, 0.0, 0, None) > sourcing_score(10000, 0.0, 0, None)  # 수요↑
    assert sourcing_score(10000, 0.5, 0, None) < sourcing_score(10000, 0.0, 0, None)  # 로켓↑=감점
    assert sourcing_score(10000, 0.0, 5, None) < sourcing_score(10000, 0.0, 0, None)  # 광고↑=감점
    assert sourcing_score(10000, 0.0, 0, 0.5) > sourcing_score(10000, 0.0, 0, None)   # 마진↑=가점
    assert sourcing_score(10000, 0.0, 0, None) == sourcing_score(10000, 0.0, 0, 0.0)  # None==0
    ok("수요↑·경쟁↓·마진↑ 단조·None==0")


def main():
    _install_stubs()
    t1_discover_ranking()
    t2_blank_seed()
    t3_notes_boundary()
    t4_top_n()
    t5_analyze_single()
    t6_score_pure()
    print("D2 소싱 오프라인 검증 통과")


if __name__ == "__main__":
    main()
