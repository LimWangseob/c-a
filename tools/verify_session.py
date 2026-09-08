"""세션 영속/회수 로직 실증(로그인 불필요 부분). 실제 DPAPI 왕복 + vendorId 정규식 fixture.

라이브(브라우저) 필요한 is_alive/extract_vendor_id 는 사무실 세션에서 검증. 여기선 순수 로직만.
실행: python tools/verify_session.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics.session_store import SessionStore  # noqa: E402
from coupang_analytics.wing_session import _VENDOR_RE  # noqa: E402


def _check(cond, msg):
    print(f"    {'[통과]' if cond else '[실패]'} {msg}")
    if not cond:
        raise AssertionError(msg)


def main():
    print("=" * 60)
    print("  세션 영속/회수 로직 실증 (DPAPI 왕복 + vendorId 정규식)")
    print("=" * 60)

    print("[1] SessionStore DPAPI 왕복 (실제 Windows DPAPI, 계정별 파일)")
    d = Path(tempfile.mkdtemp())
    store = SessionStore(base_dir=d)
    blob = {"vendor_id": "A00012345",
            "tokens": {"WebSessionId": "sess-XYZ", "PCID": "pcid-123", "OAuthTokenRequestState": "st-9"},
            "cookies": [{"name": "_abck", "value": "abck-sensor", "domain": ".coupang.com", "path": "/"}]}
    store.save("acct_1", blob)
    got = SessionStore(base_dir=d).load("acct_1")   # 새 인스턴스 재로드
    _check(got is not None, "저장→재로드 성공")
    _check(got["vendor_id"] == "A00012345", "vendor_id 왕복 일치")
    _check(got["tokens"] == blob["tokens"], "세션 3요소 왕복 일치")
    _check(got["cookies"] == blob["cookies"], "쿠키(_abck 등) 왕복 일치")
    raw = (d / "acct_1.json").read_text(encoding="utf-8")
    _check("sess-XYZ" not in raw and "abck-sensor" not in raw, "파일에 평문 토큰/쿠키 없음(DPAPI 암호화 확인)")
    _check(SessionStore(base_dir=d).load("없는계정") is None, "미존재 계정 로드→None")
    store.delete("acct_1")
    _check(not (d / "acct_1.json").exists(), "삭제 동작")

    print("[2] vendorId 정규식(ShopMine 실측 패턴) fixture 파싱")
    html = "<script>var config={ vendorId: 'A00098765', name:'x' };</script>"
    m = _VENDOR_RE.search(html)
    _check(m and m.group(1) == "A00098765", "vendorId 추출 정상")
    _check(_VENDOR_RE.search("<div>no vendor here</div>") is None, "미존재 시 None")

    print("=" * 60)
    print("  [완료] 세션 로직 실증 통과 (is_alive/extract_vendor_id 라이브는 사무실)")
    print("=" * 60)


if __name__ == "__main__":
    main()
