"""상품 상세페이지 이미지 추출 — 사용자의 **실제 Chrome 세션에 CDP로 붙어**, 현재 열려 있는
상품 상세 탭의 DOM만 읽어 대표/갤러리 이미지와 상세설명 이미지를 저장한다(SSOT: DESIGN §5.3).

## 왜 CDP attach 인가(A안, 사용자 확정 2026-09-15)
- 앱이 **새 프로필로 코팡에 접근하면** 사무실 IP Akamai 가 콜드 세션을 Access Denied 로 막는다(실증).
- 유일하게 확실히 안 막히는 경로 = **사용자가 평소 쓰는 warm·로그인된 Chrome 세션**.
- 그래서 앱은 브라우저를 띄우지 않는다. 사용자가 디버그포트(`--remote-debugging-port`)로 띄운 자기 Chrome 에
  `extract_via_cdp()` 로 **붙어**, 현재 상품 탭의 DOM만 읽고 그 세션 쿠키로 이미지만 내려받는다(추가 네비 0·차단 0).
- 순수 로직(`extract_from_page`)은 Playwright Page 만 받으므로 어떤 경로로 얻은 탭이든 동일하게 동작한다.

## 무엇을 골라내나(실측 2026-09-15, 광동 써큐알파 상세페이지 537 img 중)
- **상세설명 이미지**: `.product-detail-content`(→ `.vendor-item` → `.subType-IMAGE`) 컨테이너 안의 img.
  URL = `thumbnail.coupangcdn.com/thumbnails/remote/q89/image/vendor_inventory/{hash}.jpg`(naturalWidth≈780=원본폭).
- **대표/갤러리 이미지**: `div.product-image` 컨테이너 안의 img(48x48 썸네일+492x492 메인이 같은 원본 → dedup).
- ⚠ 추천상품·리뷰 사진도 **같은 vendor_inventory URL**을 쓴다 → URL이 아니라 **DOM 컨테이너로 스코핑**해야
  이 상품 것만 정확히 걸러진다(URL 필터만으론 구분 불가).
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# ── 실측 기반 컨테이너 셀렉터(쿠팡 PC 상세페이지) ──
GALLERY_SEL = "div.product-image"
DETAIL_SEL = ".product-detail-content, .vendor-item"

# 상세 영역 펼치기 버튼 텍스트(접혀 있으면 지연로딩 이미지가 안 붙음)
_EXPAND_JS = r"""
() => {
  const clicked = [];
  for (const b of document.querySelectorAll('button, a, div[role=button]')) {
    const t = (b.textContent || '').replace(/\s+/g, '');
    if (/상품상세.*더보기|상품정보더보기|상세정보펼쳐보기/.test(t) && b.offsetParent) {
      try { b.click(); clicked.push(t.slice(0, 20)); } catch (e) {}
    }
  }
  return clicked;
}
"""

# 컨테이너 스코핑해서 이미지 URL 수집(DOM 순서 유지). data-src(지연로딩) 폴백 포함.
_COLLECT_JS = r"""
(sels) => {
  const grab = (sel) => {
    const out = [];
    for (const root of document.querySelectorAll(sel)) {
      for (const img of root.querySelectorAll('img')) {
        const src = img.currentSrc || img.src || img.getAttribute('data-src') || '';
        if (!src || src.startsWith('data:')) continue;
        out.push({ src, nw: img.naturalWidth || 0, nh: img.naturalHeight || 0 });
      }
    }
    return out;
  };
  return { gallery: grab(sels.gallery), detail: grab(sels.detail) };
}
"""

_CDN_PATH_RE = re.compile(r"/image/(vendor_inventory/[^?\s]+?\.(?:jpg|jpeg|png|webp|gif))", re.I)
_SIZE_RE = re.compile(r"(/thumbnails/remote/)([^/]+)(/image/)")


def _canonical(url: str) -> str:
    """dedup 키 = CDN 상 원본 상대경로(vendor_inventory/…). 크기·호스트 달라도 같은 이미지면 동일."""
    m = _CDN_PATH_RE.search(url)
    return m.group(1).lower() if m else url.lower()


def _ext_of(url: str) -> str:
    m = re.search(r"\.(jpg|jpeg|png|webp|gif)(?:$|[?&])", url, re.I)
    return "." + (m.group(1).lower() if m else "jpg")


def _upscale(url: str, size: str = "1000x1000ex") -> str:
    """갤러리 썸네일 URL의 크기 토큰(48x48ex/492x492ex)을 크게 바꿔 고해상도 요청."""
    return _SIZE_RE.sub(rf"\g<1>{size}\g<3>", url)


@dataclass
class ExtractResult:
    product_id: str = ""
    title: str = ""
    out_dir: str = ""
    gallery: list[str] = field(default_factory=list)  # 저장된 파일 경로
    detail: list[str] = field(default_factory=list)
    expanded: list[str] = field(default_factory=list)  # 클릭한 더보기 버튼
    skipped: int = 0                                    # 실패(다운로드 오류) 수


def _product_id(url: str) -> str:
    m = re.search(r"/vp/products/(\d+)", url)
    return m.group(1) if m else "unknown"


def _prepare_page(page: Any, log: Callable[[str], None] | None = None) -> list[str]:
    """현재 열린 상세페이지에서 상세 영역 펼치기 + 끝까지 스크롤(지연로딩 이미지 유발). 네비게이션 없음."""
    expanded: list[str] = []
    try:
        clicked = page.evaluate(_EXPAND_JS)
        if clicked:
            expanded = clicked
            if log:
                log(f"    상세 더보기 펼침: {clicked}")
            time.sleep(1.5)
    except Exception as exc:
        if log:
            log(f"    [경고] 더보기 펼치기 실패({exc.__class__.__name__})")
    # 끝까지 스크롤(지연로딩) — 높이 안정될 때까지
    try:
        last_h = 0
        for i in range(50):
            page.mouse.wheel(0, 1600)
            time.sleep(0.5)
            h = page.evaluate("() => document.body.scrollHeight")
            if h == last_h and i > 6:
                break
            last_h = h
        page.evaluate("() => window.scrollTo(0, 0)")
        time.sleep(1.0)
    except Exception as exc:
        if log:
            log(f"    [경고] 스크롤 실패({exc.__class__.__name__})")
    return expanded


def collect_image_urls(page: Any) -> dict[str, list[dict]]:
    """현재 페이지 DOM에서 갤러리·상세 이미지 URL 수집(컨테이너 스코핑, DOM 순서 유지)."""
    return page.evaluate(_COLLECT_JS, {"gallery": GALLERY_SEL, "detail": DETAIL_SEL})


def _dedup(items: list[dict], upscale: bool) -> list[str]:
    """canonical 경로로 dedup. 같은 이미지면 자연크기 큰 것 우선. 갤러리는 URL 고해상도화."""
    best: dict[str, tuple[int, str]] = {}
    order: list[str] = []
    for it in items:
        src = it.get("src") or ""
        if not src:
            continue
        key = _canonical(src)
        area = int(it.get("nw", 0)) * int(it.get("nh", 0))
        if key not in best:
            order.append(key)
            best[key] = (area, src)
        elif area > best[key][0]:
            best[key] = (area, best[key][1] if False else src)
    urls = []
    for key in order:
        _, src = best[key]
        urls.append(_upscale(src) if upscale else src)
    return urls


def _download(request: Any, urls: list[str], out_dir: Path, prefix: str,
              referer: str, log: Callable[[str], None] | None = None) -> tuple[list[str], int]:
    """현재 세션(쿠키 공유 APIRequestContext)으로 이미지 다운로드. 실패는 건너뛰되 개수 보고(fallback 금지)."""
    saved: list[str] = []
    skipped = 0
    width = max(2, len(str(len(urls))))
    for idx, url in enumerate(urls, 1):
        name = f"{prefix}_{idx:0{width}d}{_ext_of(url)}"
        dest = out_dir / name
        try:
            resp = request.get(url, headers={"referer": referer}, timeout=30000)
            if not resp.ok:
                skipped += 1
                if log:
                    log(f"    [실패] {name} HTTP {resp.status}")
                continue
            body = resp.body()
            if not body:
                skipped += 1
                if log:
                    log(f"    [실패] {name} 빈 응답")
                continue
            dest.write_bytes(body)
            saved.append(str(dest))
        except Exception as exc:
            skipped += 1
            if log:
                log(f"    [실패] {name} {exc.__class__.__name__}: {exc}")
    return saved, skipped


def extract_from_page(page: Any, out_root: str | Path,
                      gallery: bool = True, detail: bool = True,
                      log: Callable[[str], None] | None = None) -> ExtractResult:
    """**이미 열려 있는** 쿠팡 상세페이지(Playwright Page)에서 이미지를 추출·저장(추가 네비게이션 없음).

    호출 전제: 사람이 (자기 Chrome이든 앱 창이든) 상품 상세페이지를 열어 둔 상태 — 이 `page` 가 그 탭.
    이미지는 그 `page` 의 세션 쿠키를 공유하는 request 컨텍스트로 내려받는다.
    반환: 저장 경로·개수 등 ExtractResult. 이미지가 하나도 없으면 정상(빈 결과) — 오류 아님.
    """
    url = page.url
    if "/vp/products/" not in url:
        raise ValueError(f"상품 상세페이지가 아닙니다(현재 URL: {url}). 상품을 먼저 여세요.")
    pid = _product_id(url)
    title = ""
    try:
        title = page.title()
    except Exception:
        pass

    res = ExtractResult(product_id=pid, title=title)
    res.expanded = _prepare_page(page, log)

    collected = collect_image_urls(page)
    request = page.context.request     # 그 탭의 세션 쿠키를 공유하는 APIRequestContext
    out_dir = Path(out_root) / pid
    out_dir.mkdir(parents=True, exist_ok=True)
    res.out_dir = str(out_dir)

    if detail:
        det_urls = _dedup(collected.get("detail", []), upscale=False)  # 상세=q89 원본폭, 그대로
        if log:
            log(f"  상세 이미지 {len(det_urls)}개 다운로드...")
        res.detail, sk = _download(request, det_urls, out_dir, "detail", url, log)
        res.skipped += sk
    if gallery:
        gal_urls = _dedup(collected.get("gallery", []), upscale=True)  # 갤러리=고해상도화
        if log:
            log(f"  대표/갤러리 이미지 {len(gal_urls)}개 다운로드...")
        res.gallery, sk = _download(request, gal_urls, out_dir, "gallery", url, log)
        res.skipped += sk

    # 메타 기록(추적성)
    meta = {
        "product_id": pid, "title": title, "url": url,
        "gallery": [Path(p).name for p in res.gallery],
        "detail": [Path(p).name for p in res.detail],
        "skipped": res.skipped, "expanded": res.expanded,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if log:
        log(f"  → 저장: {out_dir}  (대표 {len(res.gallery)} · 상세 {len(res.detail)} · 실패 {res.skipped})")
    return res


# ── CDP attach 경로(권장): 사용자가 디버그포트로 띄운 자기 Chrome에 붙어 현재 상품 탭에서 추출 ──
def _pick_product_page(pages: list) -> Any:
    """열린 탭 중 쿠팡 상품 상세(/vp/products/)를 고른다 — 보이는(활성) 탭 우선, 없으면 마지막 것."""
    prods = [p for p in pages if "/vp/products/" in ((p.url or "") if not p.is_closed() else "")]
    if not prods:
        return None
    for p in prods:                        # 사용자가 지금 보고 있는(포커스된) 탭 우선
        try:
            if p.evaluate("() => document.visibilityState") == "visible":
                return p
        except Exception:
            continue
    return prods[-1]


def extract_via_cdp(cdp_url: str, out_root: str | Path,
                    gallery: bool = True, detail: bool = True,
                    log: Callable[[str], None] | None = None,
                    connect_tries: int = 3) -> ExtractResult:
    """디버그포트로 실행된 Chrome(cdp_url 예: http://127.0.0.1:9222)에 **붙어** 현재 상품 탭에서 추출.

    앱은 브라우저를 띄우지 않는다. 사용자의 warm·로그인된 실제 Chrome 세션을 그대로 쓰므로 차단이 없다.
    연결만 하고 읽을 뿐, 사용자 Chrome 은 종료하지 않는다(pw.stop() = CDP 연결만 해제).
    """
    from playwright.sync_api import sync_playwright  # 지연 import(모듈 로드는 가볍게)

    pw = sync_playwright().start()
    try:
        browser = None
        last_err: Exception | None = None
        for i in range(max(1, connect_tries)):
            try:
                browser = pw.chromium.connect_over_cdp(cdp_url)
                break
            except Exception as exc:                # Chrome 준비 전/포트 미개방 등 재시도
                last_err = exc
                time.sleep(1.0)
        if browser is None:
            raise RuntimeError(
                f"Chrome 디버그 포트({cdp_url})에 연결하지 못했습니다 — '쿠팡용 크롬 실행'으로 크롬을 먼저 "
                f"띄웠는지 확인하세요. ({last_err.__class__.__name__ if last_err else ''})")
        pages = []
        for ctx in browser.contexts:
            pages.extend(ctx.pages)
        page = _pick_product_page(pages)
        if page is None:
            raise ValueError("쿠팡 상품 상세페이지(/vp/products/…)가 열린 탭이 없습니다. 크롬에서 상품을 먼저 여세요.")
        if log:
            log(f"  연결됨 — 대상 탭: {page.url[:80]}")
        return extract_from_page(page, out_root, gallery=gallery, detail=detail, log=log)
    finally:
        pw.stop()   # CDP 연결만 해제(사용자 Chrome 은 그대로 실행 유지)
