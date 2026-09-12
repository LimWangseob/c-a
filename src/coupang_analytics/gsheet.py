"""공개(링크 공유) 구글 시트를 xlsx 로 내려받아 입력 대장으로 사용 — 인증 불필요(export 엔드포인트).

- 시트가 **'링크가 있는 모든 사용자 · 보기 가능'** 이어야 한다(비공개면 로그인 리다이렉트로 실패).
- ⚠ 대장에 비밀번호 컬럼이 있으면 내려받은 파일에 **평문**으로 담긴다 → 호출부는 파싱 직후 그 임시 파일을
  **삭제**해 평문이 디스크에 남지 않게 한다(비번은 파싱 시 DPAPI 로 암호화 저장됨).
"""
from __future__ import annotations

import re
from pathlib import Path

import requests

_ID_RE = re.compile(r"/spreadsheets/d/([A-Za-z0-9_-]+)")
_EXPORT = "https://docs.google.com/spreadsheets/d/{sid}/export?format=xlsx"


def sheet_id_from_url(url: str) -> str:
    """구글 시트 URL(또는 순수 ID)에서 스프레드시트 ID 추출."""
    s = (url or "").strip()
    m = _ID_RE.search(s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{20,}", s):   # 순수 ID 직접 입력도 허용
        return s
    raise ValueError("구글 시트 URL/ID 를 인식하지 못했습니다.")


def download_xlsx(url: str, dest: str | Path, timeout: float = 30) -> Path:
    """공개 구글 시트를 xlsx 로 내려받아 dest 에 저장하고 경로 반환. 실패 시 ValueError(사유 명시)."""
    sid = sheet_id_from_url(url)
    r = requests.get(_EXPORT.format(sid=sid), timeout=timeout)
    if r.status_code != 200 or r.content[:2] != b"PK":
        raise ValueError(
            "구글 시트를 내려받지 못했습니다 — 시트를 '링크가 있는 모든 사용자 · 보기 가능'으로 "
            f"공유했는지 확인하세요. (status={r.status_code})")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return dest
