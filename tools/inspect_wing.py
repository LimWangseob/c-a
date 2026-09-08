"""쿠팡 윙 페이지 구조 점검 (실제 Chrome + CDP 연결, 라이브 1회).

Playwright가 브라우저를 '띄우는' 대신, **회원님의 진짜 Chrome**을 원격 디버깅 포트로
구동하고 CDP로 연결한다. 자동화 위장·지문 조작을 하지 않으므로 webdriver 흔적이 없어
쿠팡 로그인이 정상 작동한다. 회원님이 그 창에서 직접 로그인 → 판매분석 이동 →
상품별 리포트 다운로드까지 진행하고 창을 닫으면 캡처가 마무리된다.

캡처물(HTML/URL/스크린샷/세션/네트워크)은 로컬 전용(git 제외).

사용:
  python tools/inspect_wing.py [--account <계정아이디>]
"""
from __future__ import annotations

import argparse
import ctypes
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from playwright.sync_api import sync_playwright  # noqa: E402

from coupang_analytics.input_list import parse_input_list  # noqa: E402

DEFAULT_INPUT = r"D:\토탈셀러\셀독\토탈셀러_셀독 관리 대장 (3).xlsx"
WING_URL = "https://wing.coupang.com/"
SALES_ANALYSIS_URL = "https://wing.coupang.com/tenants/business-insight/sales-analysis"
DEBUG_PORT = 9222
SNAPSHOT_EVERY = 4.0
MAX_MINUTES = 20
CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    str(Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe"),
]


def find_chrome() -> str:
    for p in CHROME_CANDIDATES:
        if Path(p).exists():
            return p
    raise FileNotFoundError("설치된 Google Chrome 을 찾지 못했습니다.")


def center_window(w: int, h: int) -> tuple[int, int]:
    """화면 정중앙 좌상단 좌표 계산 (Windows)."""
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    return max(0, (sw - w) // 2), max(0, (sh - h) // 2)


def show_account(input_path: str, account_id: str | None) -> None:
    il = parse_input_list(input_path)
    if not il.accounts:
        print("[경고] 입력 파일에서 계정을 찾지 못했습니다.")
        return
    acct = il.accounts[0]
    if account_id:
        acct = next((a for a in il.accounts if a.account_id == account_id), acct)
    print("=" * 56)
    print("  이 계정으로 로그인하세요:")
    print(f"   대표자명 : {acct.representative}")
    print(f"   사업자명 : {acct.business_name}")
    print(f"   계정아이디: {acct.account_id}")
    print("=" * 56)


def wait_port(port: int, timeout: float = 20.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.3)
    raise TimeoutError(f"Chrome 디버깅 포트({port})가 열리지 않았습니다.")


def attach_listeners(page, net_f, out: Path) -> None:
    def on_response(resp):
        try:
            net_f.write(f"{resp.status}\t{resp.request.method}\t{resp.request.resource_type}\t{resp.url}\n")
            net_f.flush()
        except Exception as exc:
            net_f.write(f"[listener 오류] {exc.__class__.__name__}\n")
    page.on("response", on_response)

    def on_download(dl):
        net_f.write(f"DOWNLOAD\t{dl.suggested_filename}\t{dl.url}\n")
        net_f.flush()
        dl_dir = out / "downloads"
        dl_dir.mkdir(parents=True, exist_ok=True)
        try:
            dl.save_as(str(dl_dir / dl.suggested_filename))
            print(f"   [다운로드 저장] {dl.suggested_filename}")
        except Exception as exc:
            net_f.write(f"[download 저장 실패] {exc.__class__.__name__}\n")
    page.on("download", on_download)


def dump(page, context, out: Path, n: int) -> str:
    """현재 상태 캡처. URL만 필수, 나머지는 전환 중 실패해도 건너뛴다."""
    url = page.url
    (out / f"url_{n:03d}.txt").write_text(url, encoding="utf-8")
    steps = (
        ("html", lambda: (out / f"page_{n:03d}.html").write_text(page.content(), encoding="utf-8")),
        ("shot", lambda: page.screenshot(path=str(out / f"shot_{n:03d}.png"), full_page=False)),
        ("session", lambda: context.storage_state(path=str(out / "session.json"))),
    )
    for label, act in steps:
        try:
            act()
        except Exception as exc:  # 페이지 전환 중 일시 실패 — 다음 틱에 재시도
            print(f"   [스킵:{label}] {exc.__class__.__name__}")
    return url


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=DEFAULT_INPUT)
    ap.add_argument("--account", default=None)
    ap.add_argument("--out", default=str(ROOT / "capture"))
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    profile = ROOT / "data" / "chrome-profile"
    profile.mkdir(parents=True, exist_ok=True)

    show_account(args.input, args.account)
    print("\n진짜 Chrome 창이 열립니다. 이 창에서 직접 로그인 →")
    print("비즈니스 인사이트 > 판매분석 → 기간 설정 → '상품별 판매 리포트' 다운로드까지 해보세요.")
    print("끝나면 Chrome 창을 닫으면 캡처가 마무리됩니다.\n")

    chrome = find_chrome()
    win_w, win_h = 1200, 900
    cx, cy = center_window(win_w, win_h)
    subprocess.Popen([
        chrome,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={profile}",
        f"--window-position={cx},{cy}",
        f"--window-size={win_w},{win_h}",
        "--no-first-run", "--no-default-browser-check",
        WING_URL,
    ])
    wait_port(DEBUG_PORT)

    net_f = (out / "network.log").open("w", encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{DEBUG_PORT}")
        context = browser.contexts[0]
        context.on("page", lambda pg: attach_listeners(pg, net_f, out))
        page = context.pages[0] if context.pages else context.new_page()
        attach_listeners(page, net_f, out)

        alive = {"v": True}
        browser.on("disconnected", lambda *_: alive.__setitem__("v", False))
        print(">>> 방금 새로 열린 '북마크 없는 빈 Chrome' 창에 로그인하세요! (평소 크롬 아님) <<<\n")
        n = 0
        prev_logged = False
        deadline = time.time() + MAX_MINUTES * 60
        while alive["v"] and time.time() < deadline:
            try:
                if not browser.is_connected():
                    print("[종료] Chrome 연결이 끊어졌습니다.")
                    break
                pages = [pg for pg in context.pages if not pg.is_closed()]
                # 어느 탭이든 로그인된 페이지를 우선 추적
                logged_page = next((pg for pg in pages if "wing.coupang.com" in pg.url and "xauth" not in pg.url), None)
                page = logged_page or (pages[-1] if pages else page)
                logged = logged_page is not None
                if logged and not prev_logged:
                    print("   [로그인 성공] → 판매분석으로 자동 이동합니다. 기간 설정 후 '상품별 리포트' 다운로드 하세요.")
                    try:
                        page.goto(SALES_ANALYSIS_URL, wait_until="domcontentloaded", timeout=30000)
                    except Exception as e:
                        print(f"   [이동 대기] {e.__class__.__name__}")
                    prev_logged = True
                url = dump(page, context, out, n)
                print(f"[캡처] {n:03d} [{'로그인됨' if logged else '로그인 대기'}]  {url[:78]}")
                n += 1
            except Exception as exc:  # 일시 실패는 건너뛰고 계속
                print(f"[스킵] {exc.__class__.__name__}")
            time.sleep(SNAPSHOT_EVERY)
    net_f.close()
    print(f"\n완료. 캡처 위치: {out}  (로그인 성공: {prev_logged})")


if __name__ == "__main__":
    main()
