"""EPIPE 크래시 재현 — 로그인 창이 죽은 뒤 다음 계정 브라우저로 전환하는 상황.

2026-09-08 라이브(전체실행)에서 [2/35] 웰빙피크 로그인 창이 (Akamai 차단 후) 닫히고
[3/35] 콰이어트랩으로 넘어가는 순간 Playwright 드라이버가 `EPIPE: broken pipe`
(PipeTransport.send at DispatcherConnection.sendEvent)로 죽어 앱 전체가 종료됐다.

이 스크립트는 **위탁계정 로그인/Akamai 없이** 그 상황만 재현한다:
  브라우저 A 열기 → (사람이 창 X 누른 것과 동일하게) Chrome 프로세스 트리 강제 종료
  → is_connected=False → __exit__(pw.stop+kill_tree) → 브라우저 B 열기.

EPIPE 가 재현되면 근본 = "창(Chrome)이 외부에서 죽은 뒤 정리/전환 중 드라이버 파이프 broken".
재현이 안 되면 다른 요인(로그인 이벤트 폭주 등)이므로 추측 없이 다음 단서로 넘어간다.

사용: python -u tools/repro_epipe.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics.browser import WingBrowser  # noqa: E402

_P1 = str(ROOT / "data" / "profiles" / "_repro_epipe_1")
_P2 = str(ROOT / "data" / "profiles" / "_repro_epipe_2")


def main() -> None:
    print("=" * 60)
    print("  EPIPE 재현: 브라우저 창 죽음 → 정리 → 다음 브라우저 전환")
    print("=" * 60)

    print("[1] 브라우저 A 열기 (로그인 브라우저 역할) + show + 페이지 이벤트 유발")
    b = WingBrowser(profile_dir=_P1, offscreen=True)
    b.__enter__()
    b.show()                     # 실제 로그인처럼 창 표시(setWindowBounds CDP)
    try:
        b.goto("https://wing.coupang.com")   # 로그인 폼으로 리다이렉트 = CDP 이벤트 활발
    except Exception as exc:
        print(f"    goto 예외(무해) {exc.__class__.__name__}")
    print(f"    A is_connected = {b._browser.is_connected()}  (열림 정상)")

    print("[2] graceful 종료 — 사람이 창 X (Chrome 정상 종료 → CDP disconnect 이벤트 발생)")
    try:
        cdp = b.context.new_cdp_session(b.page)
        cdp.send("Browser.close")            # 창 X 와 동일: graceful shutdown + disconnect 이벤트
    except Exception as exc:                  # close 응답 대기 중 연결끊김 = 예상됨
        print(f"    Browser.close 예외(예상) {exc.__class__.__name__}")
    time.sleep(2.0)
    try:
        conn = b._browser.is_connected()
    except Exception as exc:                    # is_connected 조회 자체가 터질 수도
        conn = f"조회예외 {exc.__class__.__name__}"
    print(f"    A is_connected = {conn}  (False/예외 = 창 죽음 감지 지점)")

    print("[3] __exit__ 호출 (pw.stop + kill_tree) — 실제 파이프라인의 with 블록 종료와 동일")
    b.__exit__(None, None, None)
    print("    A 정리 완료 (여기까지 EPIPE 없으면 정리단계는 안전)")

    print("[4] 브라우저 B 열기 — 다음 계정으로 넘어가는 순간 재현")
    with WingBrowser(profile_dir=_P2, offscreen=True) as b2:
        b2.goto("about:blank")
        print(f"    B is_connected = {b2._browser.is_connected()}  (열림 정상)")
    print("    B 정리 완료")

    print("=" * 60)
    print("  [결과] EPIPE 없이 전 구간 통과 — 이 경로는 원인 아님")
    print("=" * 60)


if __name__ == "__main__":
    main()
