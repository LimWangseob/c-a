"""쿠팡 자동완성(검색어 추천) 수집 — 키워드 선정 후보 소스.

검색창에 글자를 칠 때 쿠팡이 내려주는 자동완성 엔드포인트를 rank_browser 세션에서
**직접 호출**한다(타이핑 없이 fetch). 브라우저 세션 안에서 호출하므로 Akamai 쿠키(`_abck`)가
자동으로 실려 안정적이다. 반드시 쿠팡 오리진(www.coupang.com) 페이지가 로드된 상태여야
same-origin fetch가 된다(호출 전 rank.warmup 등으로 홈을 먼저 연다).

엔드포인트(2026-09-07 실측 확정):
    GET https://www.coupang.com/n-api/web-adapter/search?keyword={q}&_={ms}
    → [{"keyword":"화로 테이블","travelKeyword":false,"requestId":"..."}, ...]  최대 10개
반환 순서 = 쿠팡 검색 인기/수요순 → 후보 우선순위 신호로 그대로 보존한다.
자동완성은 prefix 기반이라, 시드를 여러 각도(붙임/띄움/짧은 접두)로 넣어 후보를 넓힌다.
"""
from __future__ import annotations

import json


class SuggestError(Exception):
    """자동완성 요청 실패(비200·JSON 파싱 실패 등). 폴백 없이 호출부로 전파."""


# 브라우저 세션(쿠팡 오리진)에서 실행하는 fetch. 결과를 {status, body}로 반환.
_FETCH_JS = """
async (kw) => {
  const url = `https://www.coupang.com/n-api/web-adapter/search`
            + `?keyword=${encodeURIComponent(kw)}&_=${Date.now()}`;
  const r = await fetch(url, {headers: {accept: 'application/json'}, credentials: 'include'});
  return {status: r.status, body: await r.text()};
}
"""


def fetch_suggestions(browser, prefix: str) -> list[str]:
    """`prefix`에 대한 쿠팡 자동완성 후보(쿠팡 인기순, 최대 10개).

    browser = WingBrowser(쿠팡 오리진 로드 상태). 실패 시 SuggestError.
    """
    prefix = (prefix or "").strip()
    if not prefix:
        return []
    res = browser.page.evaluate(_FETCH_JS, prefix)
    status, body = res.get("status"), res.get("body", "")
    if status != 200:
        raise SuggestError(f"자동완성 요청 실패(status={status}, prefix='{prefix}')")
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SuggestError(f"자동완성 응답 JSON 파싱 실패(prefix='{prefix}'): {exc}") from exc
    out = []
    for d in data:
        kw = (d.get("keyword") or "").strip()
        if kw:
            out.append(kw)
    return out


def collect_suggestions(browser, seeds, log=None) -> list[str]:
    """여러 시드로 자동완성을 모아 **순서 보존 중복제거**(먼저 나온 것=더 상위 신호).

    seeds = 핵심어들(붙임/띄움 변형 포함 가능). 반환 = 후보 리스트(인기순 근사).
    """
    seen: dict[str, None] = {}
    for seed in seeds:
        got = fetch_suggestions(browser, seed)
        for kw in got:
            if kw not in seen:
                seen[kw] = None
        if log:
            log(f"  [자동완성] '{seed}' → {got}")            # 이 시드가 준 후보 나열
    if log:
        log(f"  [자동완성] 누적 후보 {len(seen)}개: {list(seen.keys())}")   # 전체 후보 나열
    return list(seen.keys())
