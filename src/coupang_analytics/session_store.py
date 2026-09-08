"""계정별 세션 영속 저장소 — 세션 3요소(WebSessionId·PCID·OAuthTokenRequestState) + 쿠키.

ShopMine 의 계정별 세션 JSON(MarketAccountConfig)에 대응. **계정별 독립 파일**(격리·이식)로 두되,
쿠키는 민감정보이므로 **DPAPI 로 암호화**해 이 PC·이 사용자만 복호화 가능하게 저장한다(credstore 방식 재사용).
복원(RESTORE)만으로 재로그인·2차인증을 건너뛰는 게 목적. 저장/로드 실패는 예외로 올린다(무음 금지).
"""
from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path

from .credstore import _dpapi_decrypt, _dpapi_encrypt

_DEFAULT_DIR = Path("data") / "sessions"


def _safe_key(account_key: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_.@+-]", "_", account_key.strip())
    if not s:
        raise ValueError("빈 account_key 로는 세션을 저장할 수 없습니다")
    return s


class SessionStore:
    """계정별 세션 blob 을 DPAPI 암호화된 JSON 파일로 영속·복원."""

    def __init__(self, base_dir: str | Path | None = None):
        self.dir = Path(base_dir) if base_dir else _DEFAULT_DIR

    def _path(self, account_key: str) -> Path:
        return self.dir / f"{_safe_key(account_key)}.json"

    def save(self, account_key: str, blob: dict) -> None:
        """세션 blob 저장(DPAPI 암호화). blob 예: {vendor_id, tokens{}, cookies[]}."""
        self.dir.mkdir(parents=True, exist_ok=True)
        payload = dict(blob)
        payload["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        plain = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        enc = base64.b64encode(_dpapi_encrypt(plain)).decode("ascii")
        self._path(account_key).write_text(enc, encoding="utf-8")

    def load(self, account_key: str) -> dict | None:
        """세션 blob 복원(없으면 None). 복호화·파싱 실패는 예외로 올린다."""
        p = self._path(account_key)
        if not p.exists():
            return None
        raw = p.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        plain = _dpapi_decrypt(base64.b64decode(raw)).decode("utf-8")
        return json.loads(plain)

    def delete(self, account_key: str) -> None:
        p = self._path(account_key)
        if p.exists():
            p.unlink()
