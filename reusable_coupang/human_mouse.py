"""사람처럼 마우스 이동·스크롤·호버를 **실제 브라우저 입력**으로 재현(위조 아님, 실제 Input 이벤트).

[reusable_coupang] rank_search 가 검색·결과 훑기 때 호출한다. Playwright(sync) Page 하나로 동작.

- 이동 = 베지어 곡선 경로 + 미세 지터 + 가끔 오버슈트→보정, 가속/감속(ease). 직선·등속(로봇)과 확연히 다름.
- 스크롤 = 여러 번 나눠 굴리기 + 읽는 듯 멈춤 + 가끔 살짝 되올림(재확인). 한 번에 쭉(로봇)과 다름.
- 호버 = 검색창/상품 타일로 커서를 옮겨 잠깐 머무름. **클릭은 절대 안 함**(상품 페이지 이탈 방지 = 조회 무영향).
- 전부 best-effort: 실패(좌표 못 구함·CDP 예외)해도 조용히 no-op(검색 자체엔 영향 없음).
- on/off = `config.RANK_HUMAN_INTERACT`(기본 True). 타이핑(human_typing)과 같은 '실제 입력 재현' 계열 — 지문위조 아님.
"""
from __future__ import annotations

import random
import time

from . import config

_last_xy: dict = {}   # 마지막 커서 위치(경로 시작점) — 페이지별로 대략 추적


def _enabled() -> bool:
    return bool(getattr(config, "RANK_HUMAN_INTERACT", True))


def _viewport(page):
    try:
        w, h = page.evaluate("[window.innerWidth, window.innerHeight]")
        return int(w or 1280), int(h or 800)
    except Exception:
        return 1280, 800


def _rect(page, selector: str, index: int = 0):
    """selector 의 index 번째 요소 화면좌표 사각형 (x,y,w,h). 보이지 않거나 없으면 None."""
    try:
        r = page.evaluate(
            """([sel, i]) => {
                const els = [...document.querySelectorAll(sel)].filter(e => e.offsetParent !== null);
                const e = els[i]; if (!e) return null;
                const b = e.getBoundingClientRect();
                if (b.width < 2 || b.height < 2) return null;
                return [b.x, b.y, b.width, b.height];
            }""",
            [selector, index],
        )
        return tuple(r) if r else None
    except Exception:
        return None


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _bezier(x0, y0, x1, y1, steps):
    """(x0,y0)→(x1,y1) 2차 베지어 경로 점들. 제어점을 직선에서 수직으로 벗어나게 둬 자연스런 호(arc)."""
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = x1 - x0, y1 - y0
    dist = max(1.0, (dx * dx + dy * dy) ** 0.5)
    # 직선에 수직인 방향으로 제어점을 살짝 밀어 곡선을 만든다(거리에 비례, 좌우 무작위).
    off = random.uniform(0.05, 0.22) * dist * random.choice((-1, 1))
    nx, ny = -dy / dist, dx / dist
    cx, cy = mx + nx * off, my + ny * off
    pts = []
    for i in range(1, steps + 1):
        t = i / steps
        # ease-in-out(사람은 처음·끝이 느림) 적용
        te = 3 * t * t - 2 * t * t * t
        u = 1 - te
        bx = u * u * x0 + 2 * u * te * cx + te * te * x1
        by = u * u * y0 + 2 * u * te * cy + te * te * y1
        # 미세 손떨림
        bx += random.uniform(-1.2, 1.2)
        by += random.uniform(-1.2, 1.2)
        pts.append((bx, by))
    return pts


def human_move(page, x, y) -> None:
    """현재 커서 위치에서 (x,y) 로 사람처럼 곡선 이동(가끔 오버슈트→보정). best-effort."""
    if not _enabled():
        return
    try:
        vw, vh = _viewport(page)
        x = _clamp(float(x), 2, vw - 2)
        y = _clamp(float(y), 2, vh - 2)
        x0, y0 = _last_xy.get("x", vw * 0.5), _last_xy.get("y", vh * 0.35)
        dist = ((x - x0) ** 2 + (y - y0) ** 2) ** 0.5
        steps = int(_clamp(dist / 11.0, 6, 44))
        # 가끔(25%) 목표를 살짝 지나쳤다가 되돌아오는 오버슈트
        overshoot = random.random() < 0.25 and dist > 60
        tx, ty = (x + random.uniform(-18, 18), y + random.uniform(-14, 14)) if overshoot else (x, y)
        for px, py in _bezier(x0, y0, tx, ty, steps):
            page.mouse.move(px, py)
            time.sleep(random.uniform(0.004, 0.016))
        if overshoot:
            for px, py in _bezier(tx, ty, x, y, random.randint(4, 8)):
                page.mouse.move(px, py)
                time.sleep(random.uniform(0.006, 0.018))
        _last_xy["x"], _last_xy["y"] = x, y
    except Exception:
        pass


def _move_into(page, rect) -> None:
    x, y, w, h = rect
    # 요소 내부의 무작위 지점(가장자리 회피)으로 이동
    px = x + w * random.uniform(0.25, 0.75)
    py = y + h * random.uniform(0.3, 0.7)
    human_move(page, px, py)


def human_scroll(page, *, bursts: int | None = None) -> None:
    """읽는 것처럼 여러 번 나눠 아래로 스크롤(멈춤 포함), 가끔 살짝 되올림. best-effort."""
    if not _enabled():
        return
    try:
        n = bursts if bursts is not None else random.randint(2, 4)
        for i in range(n):
            page.mouse.wheel(0, random.uniform(90, 280))       # 아래로 한 번 굴림
            time.sleep(random.uniform(0.35, 1.15))             # 읽는 멈춤
            if random.random() < 0.18:                         # 가끔 살짝 되올림(재확인)
                page.mouse.wheel(0, -random.uniform(40, 110))
                time.sleep(random.uniform(0.3, 0.8))
    except Exception:
        pass


def approach_search(page) -> None:
    """타이핑 직전, 커서를 검색창 쪽으로 사람처럼 옮기고 잠깐 머무름(클릭 안 함 — 포커스는 타이핑이 처리)."""
    if not _enabled():
        return
    try:
        rect = _rect(page, "input[name='q'], input.headerSearchKeyword, #headerSearchKeyword")
        if rect:
            _move_into(page, rect)
            time.sleep(random.uniform(0.15, 0.5))
    except Exception:
        pass


def browse_serp(page) -> None:
    """검색결과 로드 후, 사람처럼 결과를 훑어봄: 읽는 멈춤 → 상품 1~2개 호버 → 아래로 스크롤(→가끔 되올림).
    **클릭 없음**(상품 페이지 이탈 방지 = 순위 파싱에 영향 0). best-effort·시간 상한 대략 2~7초."""
    if not _enabled():
        return
    try:
        time.sleep(random.uniform(0.6, 1.6))                   # 결과 훑기 전 읽는 멈춤
        for _ in range(random.randint(1, 2)):                  # 상품 타일 몇 개에 커서 호버
            idx = random.randint(0, 4)
            rect = _rect(page, _PRODUCT_SEL, idx)
            if rect:
                _move_into(page, rect)
                time.sleep(random.uniform(0.3, 0.9))
        human_scroll(page)
    except Exception:
        pass


_PRODUCT_SEL = "li[class*='ProductUnit_productUnit']"
