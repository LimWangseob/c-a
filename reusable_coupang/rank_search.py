"""자동 노출순위 검색 모듈 — 쿠팡 검색에서 **광고 제외 오가닉 순위**를 산출한다(로그인 불필요).

[reusable_coupang] `from reusable_coupang.rank_search import organic_ranks, make_matcher` 로 가져다 쓴다.

━━━ 원리 ━━━
쿠팡 검색은 headless/자동화 브라우저를 차단(Access Denied)하므로 **실제 Chrome**(auto_login.WingBrowser)으로 조회한다.
그리고 **검색어를 URL 로 직접 넣지 않고(붙여넣기·즉시이동은 봇 신호), 보이는 검색창에 사람처럼 한 글자씩
타이핑 + Enter** 해서 결과를 띄운다(실측: 신뢰 키입력만 통과). 결과 DOM 에서:
  - 상품 항목: li[class*='ProductUnit_productUnit']
  - 광고 마커: 항목 내부의 <span>광고</span> → **제외**
  - 상품 식별: /vp/products/{productId}?...&vendorItemId=... (href 에서 파싱)
광고를 뺀 오가닉 순번을 세며, 상한(config.RANK_SCAN_MAX) 안에 대상이 없으면 None(=상한 밖/미노출).

━━━ 두 가지 사용법 ━━━
1) **자동 검색**(`organic_ranks`/`organic_rank`): 이 모듈이 직접 검색창에 타이핑·Enter 하고 결과를 읽는다.
   → 무인 배치에 적합. 단, 우리가 네비게이션을 하므로 대량이면 Akamai 부하↑ (간격·소량 권장).
2) **반자동 파싱**(`parse_serp_rank`): 사람(또는 다른 로직)이 **이미 띄워 놓은** 검색결과 페이지의 DOM 만 읽는다.
   → 우리가 네비/타이핑을 안 해 봇 신호가 가장 적음. 대량·차단 회피에 유리.

━━━ 의존 ━━━
- playwright(sync) + 실제 Chrome (auto_login.WingBrowser).  human_typing / human_mouse (같은 패키지).
- ⚠ 쿠팡 검색결과 DOM 클래스명(ProductUnit_productUnit 등)은 사이트 개편 시 바뀔 수 있다 → 셀렉터 상수 갱신 필요.

━━━ 최소 사용 예 ━━━
    from reusable_coupang.auto_login import WingBrowser
    from reusable_coupang.rank_search import warmup, organic_ranks, make_matcher
    with WingBrowser(profile_dir="data/rank", offscreen=True) as b:
        warmup(b)                                  # 홈 1회 방문(신뢰 쿠키 유지)
        matchers = {"내상품": make_matcher(vendor_item_ids={"12345678"})}
        ranks = organic_ranks(b, "빌베리", matchers)   # {"내상품": 3 or None}
"""
from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote, unquote

from playwright.sync_api import TimeoutError as PWTimeout

from . import config, human_mouse, human_typing
from .auto_login import WingBrowser

HOME_URL = "https://www.coupang.com/"
SEARCH_URL = "https://www.coupang.com/np/search?q={q}&page={page}"
_BLOCK_HINTS = ("죄송", "Denied", "Access", "제한된", "사용권한")   # '사용권한이 없습니다/제한된' 접근차단 페이지
# Akamai 봇 챌린지 페이지 마커(실측: 센서 스크립트/behavioral 컨테이너).
_CHALLENGE_MARKERS = ("sec-if-cpt-container", "behavioral-content", "_sec/cp_challenge")

# 검색결과 DOM 셀렉터(⚠ 사이트 개편 시 갱신 필요).
_ITEM_SEL = "li[class*='ProductUnit_productUnit']"
_NAME_SEL = "[class*='ProductUnit_productName']"
_AD_XPATH = "xpath=.//span[normalize-space(text())='광고']"

# 검색창 셀렉터(PC/변형 포함).
_SEARCH_BOX_SEL = "input[name='q'], input.headerSearchKeyword, #headerSearchKeyword"
_FOCUS_CLEAR_JS = r"""() => {
  const inputs = Array.from(document.querySelectorAll(
      "input[name='q'], input.headerSearchKeyword, #headerSearchKeyword"));
  const vis = inputs.find(i => i.offsetParent !== null) || inputs[0];
  if (!vis) return false;
  vis.focus();
  try { vis.select(); } catch (e) {}
  return true;
}"""
_READ_Q_JS = r"""() => {
  const i = Array.from(document.querySelectorAll(
      "input[name='q'], input.headerSearchKeyword, #headerSearchKeyword")).find(x => x.offsetParent !== null)
      || document.querySelector("input[name='q']");
  return i ? i.value : null;
}"""

# Akamai 봇 신뢰 쿠키 — 유지해야 '재방문 신뢰 브라우저'로 인식돼 챌린지(차단)가 줄어든다.
_AKAMAI_TRUST_COOKIES = ("_abck", "bm_sz", "ak_bmsc", "bm_sv", "bm_mi")


class RankBlocked(Exception):
    """쿠팡이 검색을 차단(봇탐지)했을 때. 미노출(None)과 구분해 호출자가 로그·공란 처리."""


@dataclass
class SearchItem:
    """검색결과 한 항목. is_ad=광고 여부, product_id/vendor_item_id=상품·옵션 식별자, name=노출 상품명."""
    is_ad: bool
    product_id: str
    vendor_item_id: str
    name: str
    is_rocket: bool = False


# ── 검색어 타이핑(붙여넣기 금지) ──────────────────────────────────────────────
def _typed_ok(page, text: str) -> bool:
    """검색창의 현재 값이 text 와 같은가(조합 성공 검증). 공백 무시."""
    try:
        v = page.evaluate(_READ_Q_JS)
    except Exception:
        return False
    return v is not None and str(v).replace(" ", "") == text.replace(" ", "")


def _focus_clear(page) -> bool:
    try:
        if not page.evaluate(_FOCUS_CLEAR_JS):
            return False
        page.keyboard.press("Control+a")        # 기존 입력 전체선택
        page.keyboard.press("Delete")           # 지우고 새로 타이핑
        return True
    except Exception:
        return False


def human_type_query(page, text: str) -> bool:
    """보이는 쿠팡 검색창에 text 를 **사람처럼 한 글자씩 실제 키보드로** 입력한다(붙여넣기 아님).

    한글은 CDP IME 자모 조합(config.TYPE_JAMO_IME), 영문/숫자는 글자 단위 키입력. 글자마다 미세 랜덤 간격.
    입력 후 **값을 검증**해 조합이 어긋나면 음절 단위 키입력으로 폴백(그래도 어긋나면 False → 호출부가 URL 폴백).
    """
    if not _focus_clear(page):
        return False
    human_typing.type_focused(page, text, jamo=config.TYPE_JAMO_IME)
    if _typed_ok(page, text):
        return True
    if config.TYPE_JAMO_IME:                    # 자모 조합 어긋남 → 음절 단위 신뢰 키입력으로 폴백
        if _focus_clear(page):
            human_typing.type_focused(page, text, jamo=False)
            if _typed_ok(page, text):
                return True
    return False


def _url_q(url: str) -> str:
    """URL 의 q 파라미터(디코드·공백제거). 없으면 ''."""
    m = re.search(r"[?&]q=([^&]+)", url or "")
    return unquote(m.group(1)).replace(" ", "") if m else ""


def _await_query_navigated(browser, keyword: str, timeout_ms: int = 8000) -> bool:
    """타이핑+Enter 후 현재 페이지 URL 의 q 가 keyword 로 바뀔 때까지 대기(네비 완료 확인). 같아지면 True."""
    want = keyword.replace(" ", "")
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        try:
            if _url_q(browser.page.evaluate("() => location.href")) == want:
                return True
        except Exception:
            pass
        time.sleep(0.15)
    return False


# ── 결과 파싱 ────────────────────────────────────────────────────────────────
def _parse_ids(href: str) -> tuple[str, str]:
    pid = re.search(r"/vp/products/(\d+)", href)
    vid = re.search(r"vendorItemId=(\d+)", href)
    return (pid.group(1) if pid else "", vid.group(1) if vid else "")


def extract_items(page) -> list[SearchItem]:
    """현재 검색결과 페이지 DOM 에서 상품 항목 리스트 추출(광고 포함 — is_ad 로 구분)."""
    result: list[SearchItem] = []
    for el in page.query_selector_all(_ITEM_SEL):
        a = el.query_selector("a[href*='/vp/products/']")
        if a is None:
            continue
        pid, vid = _parse_ids(a.get_attribute("href") or "")
        name_el = el.query_selector(_NAME_SEL)
        name = name_el.inner_text().strip() if name_el else ""
        is_rocket = el.query_selector("[class*='rocketArea'], img[alt*='로켓'], img[src*='rocket']") is not None
        result.append(SearchItem(el.query_selector(_AD_XPATH) is not None, pid, vid, name, is_rocket))
    return result


def make_matcher(product_ids: set[str] | None = None,
                 vendor_item_ids: set[str] | None = None,
                 name_substr: str | None = None) -> Callable[[SearchItem], bool]:
    """'내 상품인지' 판정 함수 생성. productId / vendorItemId(권장·불변) / 상품명 부분일치 중 하나라도 맞으면 True.

    ⚠ productId 는 가변(재등록 시 바뀜)이라 **vendorItemId 앵커 권장**. vid 없을 때만 상품명 부분일치 폴백.
    """
    pids = product_ids or set()
    vids = vendor_item_ids or set()
    needle = (name_substr or "").strip()

    def matches(it: SearchItem) -> bool:
        if it.product_id and it.product_id in pids:
            return True
        if it.vendor_item_id and it.vendor_item_id in vids:
            return True
        if needle and needle in it.name:
            return True
        return False
    return matches


# ── 검색 준비·로드 ───────────────────────────────────────────────────────────
def warmup(browser: WingBrowser) -> None:
    """검색 전 준비 — **개인화 쿠키만 비우고 Akamai 신뢰 쿠키(_abck 등)는 유지**한 뒤 홈 1회 방문.

    매 실행 전체 쿠키를 지우면 '매번 새 방문자'가 돼 Akamai 가 세션을 재검증→봇 의심→차단을 유발한다(실측).
    개인화(최근검색 등)만 지우고 신뢰 쿠키는 남겨, 비로그인 기준은 유지하면서 '재방문 신뢰 브라우저'로
    인식돼 차단 확률을 낮춘다.
    """
    try:
        keep = [c for c in browser.context.cookies() if c.get("name") in _AKAMAI_TRUST_COOKIES]
        browser.context.clear_cookies()          # 개인화 포함 전부 비우고
        if keep:
            browser.context.add_cookies(keep)    # Akamai 신뢰 쿠키만 되살림(차단 회피)
    except Exception as exc:
        print(f"[rank_search] 쿠키 정리 건너뜀({exc.__class__.__name__})")
    browser.goto(HOME_URL)
    time.sleep(random.uniform(config.RANK_PAGE_DELAY_MIN, config.RANK_PAGE_DELAY_MAX))


def _load_results(browser: WingBrowser, keyword: str, page_no: int = 1,
                  timeout: float = 6000, log=None) -> bool:
    """검색 결과를 로드. 상품이 뜨면 True, 결과 없음이면 False, 차단이면 RankBlocked.

    **1페이지 = 검색창에 사람처럼 한 글자씩 타이핑 + Enter**(직접 URL 이동/붙여넣기 아님 = 쿠팡 키입력 체크 통과).
    2페이지 이상(스캔 상한이 1페이지=60개를 넘을 때만·드묾)은 URL 이동 폴백. 검색창을 못 찾으면 URL 이동 폴백.
    상품은 정상 시 ~0.1초에 뜨므로 셀렉터 타임아웃은 짧게(6초) — 차단 페이지일 때 빨리 실패. 차단 마커면 RankBlocked.
    """
    t0 = time.time()
    if page_no <= 1:                              # 사람처럼 검색창 타이핑 + Enter
        human_mouse.approach_search(browser.page)   # 타이핑 직전 커서를 검색창으로(사람처럼)
        if human_type_query(browser.page, keyword):
            try:
                browser.page.keyboard.press("Enter")
                _await_query_navigated(browser, keyword)   # 네비 완료(URL q 일치) 대기
            except Exception:
                browser.goto(SEARCH_URL.format(q=quote(keyword), page=1))
        else:                                     # 검색창 못 찾음 → URL 이동 폴백(최후)
            browser.goto(SEARCH_URL.format(q=quote(keyword), page=1))
    else:
        browser.goto(SEARCH_URL.format(q=quote(keyword), page=page_no))
    t_goto = time.time() - t0
    try:
        browser.page.wait_for_selector(_ITEM_SEL, timeout=timeout)
        t_sel = time.time() - t0 - t_goto
        if log and (t_goto > 5.0 or t_sel > 5.0):   # 평상시엔 조용, 환경적 지연(느림)만 경고
            log(f"    [느림] 페이지 로딩 goto {t_goto:.1f}s + 셀렉터 {t_sel:.1f}s (쿠팡 응답 지연)")
        human_mouse.browse_serp(browser.page)        # 결과를 사람처럼 훑어봄(호버·스크롤, 클릭 없음)
        return True
    except PWTimeout:
        try:
            html = browser.page.content()
        except Exception:
            html = browser.page.title() or ""
        if any(h in html for h in _BLOCK_HINTS) or any(h in html for h in _CHALLENGE_MARKERS):
            blocked_url = SEARCH_URL.format(q=quote(keyword), page=page_no)
            raise RankBlocked(f"검색 차단됨(Akamai 챌린지): {blocked_url}")
        return False  # 정상 페이지지만 상품 없음(빈 결과)


# ── 지문 정합(모바일 에뮬레이션 시에만) ───────────────────────────────────────
def _chrome_major(page) -> str:
    """실제 실행 중인 Chrome 의 메이저 버전(예 '153'). 지문 **정합**(하드코딩 불일치 제거)용."""
    try:
        m = re.search(r"Chrome/(\d+)", page.evaluate("navigator.userAgent") or "")
        if m:
            return m.group(1)
    except Exception:
        pass
    return "153"   # 폴백


def _set_mobile(page, on: bool) -> None:
    """CDP로 모바일 기기 에뮬레이션 On/Off. **UA/클라이언트힌트 정합**:
    - Off(PC) = UA 를 **안 건드림** → 네이티브(실제 Chrome) UA·userAgentData 그대로 = 완전 정합.
    - On(모바일) = UA 를 **실제 크롬 버전에 맞춰** 생성 + `userAgentMetadata`(클라이언트힌트)도 함께 설정
      → UA 문자열 ↔ sec-ch-ua 불일치 제거. (지문 '위조'가 아니라 실제 값에 맞추는 '정합' — 가짜 버전 금지.)
    """
    cdp = page.context.new_cdp_session(page)
    try:
        if on:
            major = _chrome_major(page)
            ua = (f"Mozilla/5.0 (Linux; Android 14; SM-S928N) AppleWebKit/537.36 "
                  f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Mobile Safari/537.36")
            meta = {"brands": [{"brand": "Chromium", "version": major},
                               {"brand": "Google Chrome", "version": major},
                               {"brand": "Not?A_Brand", "version": "99"}],
                    "fullVersion": f"{major}.0.0.0", "platform": "Android", "platformVersion": "14",
                    "architecture": "", "model": "SM-S928N", "mobile": True}
            cdp.send("Emulation.setDeviceMetricsOverride",
                     {"width": 412, "height": 915, "deviceScaleFactor": 3, "mobile": True})
            cdp.send("Emulation.setUserAgentOverride",
                     {"userAgent": ua, "platform": "Linux armv8l", "userAgentMetadata": meta})
            cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})
        else:
            cdp.send("Emulation.clearDeviceMetricsOverride")
            cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": False})
            # PC 는 UA 오버라이드 안 함 = 네이티브(실제) UA·클라이언트힌트 유지(정합).
    finally:
        cdp.detach()


# ── 순위 산출(자동 검색) ──────────────────────────────────────────────────────
def organic_ranks(browser: WingBrowser, keyword: str, matchers: dict[str, Callable[[SearchItem], bool]],
                  max_rank: int | None = None, mobile: bool = False, log=None,
                  matched_out: dict[str, SearchItem] | None = None) -> dict[str, int | None]:
    """키워드 1회 검색으로 여러 대상(옵션)의 오가닉 순위를 한 번에 산출.

    matchers: {라벨: matcher}. 반환 {라벨: 순위 or None(상한 밖/미노출)}. 차단 시 RankBlocked.
    mobile=True 면 모바일 기기 에뮬레이션으로 조회(모바일 노출순위). 조회 후 에뮬레이션 해제.
    matched_out 를 주면 매칭된 라벨의 실제 검색결과 항목(SearchItem — 정확 노출명 포함)을 채워
    호출부가 노출명 갱신 등에 쓸 수 있다(제어흐름 불변).
    """
    max_rank = config.RANK_SCAN_MAX if max_rank is None else max_rank
    result: dict[str, int | None] = {label: None for label in matchers}
    remaining = dict(matchers)
    rank = 0
    page_no = 1
    if mobile:
        _set_mobile(browser.page, True)
    try:
        while rank < max_rank and remaining:
            if not _load_results(browser, keyword, page_no, log=log):
                break
            items = extract_items(browser.page)
            if not items:
                break
            for it in items:
                if it.is_ad:
                    continue
                rank += 1
                for label in [lbl for lbl, m in remaining.items() if m(it)]:
                    result[label] = rank
                    if matched_out is not None:
                        matched_out[label] = it
                    del remaining[label]
                if rank >= max_rank or not remaining:
                    break
            page_no += 1
            if remaining:
                time.sleep(random.uniform(config.RANK_PAGE_DELAY_MIN, config.RANK_PAGE_DELAY_MAX))
    finally:
        if mobile:
            _set_mobile(browser.page, False)
    return result


def organic_rank(browser: WingBrowser, keyword: str, matches: Callable[[SearchItem], bool],
                 max_rank: int | None = None) -> int | None:
    """단일 대상의 광고 제외 오가닉 순위. 상한 안에 없으면 None(상한 밖/미노출). 차단 시 RankBlocked."""
    max_rank = config.RANK_SCAN_MAX if max_rank is None else max_rank
    rank = 0
    page_no = 1
    while rank < max_rank:
        if not _load_results(browser, keyword, page_no):
            return None
        items = extract_items(browser.page)
        if not items:
            return None
        for it in items:
            if it.is_ad:
                continue
            rank += 1
            if matches(it):
                return rank
            if rank >= max_rank:
                return None
        page_no += 1
        time.sleep(random.uniform(config.RANK_PAGE_DELAY_MIN, config.RANK_PAGE_DELAY_MAX))
    return None


def parse_serp_rank(page, matchers: dict[str, Callable[[SearchItem], bool]],
                    max_rank: int | None = None) -> dict[str, tuple[int | None, SearchItem | None]]:
    """**네비게이션 없이** 현재 열린 검색결과 페이지에서 광고 제외 오가닉 순위를 산출(반자동 전용).

    사람(또는 다른 로직)이 직접 검색해 이미 떠 있는 SERP 의 DOM(extract_items)만 읽는다 — goto/warmup 안 함(봇 신호 0).
    반환 {라벨: (순위 or None, 매칭 SearchItem or None)}. 매칭 항목의 name = 정확 노출명.
    """
    max_rank = config.RANK_SCAN_MAX if max_rank is None else max_rank
    result: dict[str, tuple[int | None, SearchItem | None]] = {label: (None, None) for label in matchers}
    remaining = dict(matchers)
    rank = 0
    for it in extract_items(page):
        if it.is_ad:
            continue
        rank += 1
        for label in [lbl for lbl, m in remaining.items() if m(it)]:
            result[label] = (rank, it)
            del remaining[label]
        if rank >= max_rank or not remaining:
            break
    return result
