"""PC별 비밀번호 저장소 (Windows DPAPI, 사용자 스코프 암호화).

비밀번호는 이 PC의 현재 사용자만 복호화 가능한 형태로 로컬에만 저장한다.
공유 파일·git·출력물 어디에도 평문/이식 가능한 형태로 남기지 않는다.
DPAPI 실패는 조용히 넘기지 않고 예외로 올린다(임의 대체·무시 금지).
"""
from __future__ import annotations

import base64
import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> _DATA_BLOB:
    buf = ctypes.create_string_buffer(data, len(data))
    return _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _blob_bytes(blob: _DATA_BLOB) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


def _dpapi_encrypt(plain: bytes) -> bytes:
    out = _DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(_blob(plain)), None, None, None, None, 0, ctypes.byref(out))
    if not ok:
        raise OSError("CryptProtectData 실패 (DPAPI 암호화 불가)")
    try:
        return _blob_bytes(out)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _dpapi_decrypt(cipher: bytes) -> bytes:
    out = _DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(_blob(cipher)), None, None, None, None, 0, ctypes.byref(out))
    if not ok:
        raise OSError("CryptUnprotectData 실패 (다른 사용자/PC이거나 데이터 손상)")
    try:
        return _blob_bytes(out)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


class CredStore:
    def __init__(self, path: str | Path | None = None):
        if path is None:
            base = os.environ.get("LOCALAPPDATA") or str(Path.home())
            path = Path(base) / "coupang-analytics" / "creds.json"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, str] = {}
        if self.path.exists():
            self._data = json.loads(self.path.read_text(encoding="utf-8"))

    def set_password(self, account_id: str, password: str) -> None:
        cipher = _dpapi_encrypt(password.encode("utf-8"))
        self._data[account_id] = base64.b64encode(cipher).decode("ascii")
        self._flush()

    def get_password(self, account_id: str) -> str | None:
        blob = self._data.get(account_id)
        if blob is None:
            return None
        return _dpapi_decrypt(base64.b64decode(blob)).decode("utf-8")

    def _flush(self) -> None:
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
