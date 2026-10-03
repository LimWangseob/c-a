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


_SCHEME_WORDS = {"https", "http", "ftp"}   # 중복 붙여넣기 시 `/d/` 뒤에 잘못 잡히는 URL 스킴


def sheet_id_from_url(url: str) -> str:
    """구글 시트 URL(또는 순수 ID)에서 스프레드시트 ID 추출.

    ⚠ 중복 붙여넣기 방어(2026-10-03): 링크 칸에 URL이 두 번 겹쳐 들어가면(예 `…/d/https://…/d/<ID>/edit`)
    옛 코드는 첫 `/d/` 뒤의 **'https'** 를 ID로 잡아 API 404("ID/URL 확인: https")를 냈다(실측: 재고현황·원장).
    → `finditer` 로 모든 `/d/<id>` 후보를 뽑되 **뒤에 `://` 가 오는(=중첩 URL 스킴) 후보와 스킴 단어는 제외**,
    남은 유효 후보의 **마지막(=실제 ID)** 을 쓴다. 길이로 거르지 않으므로 짧은 테스트 ID도 지킨다. 유효 후보가
    전혀 없으면(중복/깨진 링크) **명확한 사유로 예외**(조용히 넘기지 않음·사용자 안내).
    """
    s = (url or "").strip()
    cands = [m.group(1) for m in _ID_RE.finditer(s)
             if s[m.end():m.end() + 3] != "://" and m.group(1).lower() not in _SCHEME_WORDS]
    if cands:
        return cands[-1]                             # 중복 붙여넣기면 마지막(실제) ID
    if re.fullmatch(r"[A-Za-z0-9_-]{20,}", s):       # 순수 ID 직접 입력도 허용
        return s
    if _ID_RE.search(s):                             # /d/ 는 있으나 유효 ID 없음 = 중복/깨진 링크
        raise ValueError(
            "구글 시트 링크가 올바르지 않습니다 - URL이 중복 입력된 것 같습니다. "
            "링크 칸을 비우고 주소(또는 ID)를 한 번만 넣어 주세요.")
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
