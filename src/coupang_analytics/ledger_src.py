"""장부 DB 이관 공통 — 원천 파일 등록(경로·크기·SHA-256·줄 수·뺀 줄 이유) · 값 정규화 · 제외 계정.

- 원천 파일은 열기만 한다(수정 0). 등록 순서 = 정렬된 경로 순 → 같은 자료면 같은 file_id(V1).
- 값 정규화: 빈 칸·'-' = 0 / '' · 그 밖에 숫자로 못 읽는 값 = 오류(조용히 0 금지).
- 제외 계정(예: 실행 인자 `--exclude Difpick`)은 코드에 적지 않고 인자로만 받는다(D-229).
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from collections import Counter
from datetime import date, datetime
from pathlib import Path

_ID_FLOAT = re.compile(r"-?\d+\.0")
_YMD8 = re.compile(r"\d{8}(\.0)?")


class LedgerValueError(ValueError):
    """원천 값을 읽지 못함 — 어느 파일·어느 위치인지 함께 알린다."""


def account_id(name: str) -> str:
    """계정 표기(이름-상호-계정ID / 계정ID-계정ID) → 계정ID = 마지막 '-' 뒤(KEY 분석 3절)."""
    return str(name).strip().rsplit("-", 1)[-1]


def nm(h) -> str:
    """머리글 비교용 — 공백 전부 제거."""
    return "".join(str(h or "").split())


def nid(v) -> str:
    s = "" if v is None else str(v).strip()
    return s[:-2] if _ID_FLOAT.fullmatch(s) else s


def d10(v) -> str:
    """날짜 → 'YYYY-MM-DD' · 빈 값 = ''."""
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return f"{v:%Y-%m-%d}"
    s = str(v).strip()
    if not s:
        return ""
    if _YMD8.fullmatch(s):
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s[:10].replace(".", "-")


def won(v, where: str = "") -> int:
    """금액 → 원 단위 정수(반올림) · 빈 칸·'-' = 0 · 못 읽으면 LedgerValueError."""
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return int(round(v))
    s = str(v).strip().replace(",", "")
    if s in ("", "-"):
        return 0
    try:
        return int(round(float(s)))
    except ValueError as exc:
        raise LedgerValueError(f"금액을 읽지 못함 {v!r} — {where}") from exc


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


class Registry:
    """src_file·src_skip 기록. 한 파일 = add() → (줄 넣기) → done()."""

    def __init__(self, con: sqlite3.Connection, root: Path, exclude: frozenset[str], only: frozenset[str] = frozenset()):
        self.con, self.root, self.exclude, self.only = con, Path(root), exclude, only
        self.skips: Counter = Counter()

    def wanted(self, acc: str | None) -> bool:
        """시험용 --only: 고른 계정 밖 파일은 등록도 안 함(계정 없는 파일은 그대로)."""
        return not (self.only and acc and acc not in self.only)

    def rel(self, path: Path) -> str:
        try:
            return str(Path(path).relative_to(self.root)).replace("\\", "/")
        except ValueError:
            return str(path).replace("\\", "/")

    def add(self, path: Path, kind: str, acc: str | None, status: str = "반영", note: str = "") -> int | None:
        """파일 등록 → file_id. 제외 계정이면 '제외'로만 남기고 None(읽지 않음) · --only 밖이면 등록 없이 None."""
        if not self.wanted(acc):
            return None
        if acc and acc in self.exclude:
            status, note = "제외", "제외 계정(실행 인자)"
        p = Path(path)
        cur = self.con.execute(
            "INSERT INTO src_file(path, kind, account_id, size, sha256, status, note) VALUES (?,?,?,?,?,?,?)",
            (self.rel(p), kind, acc, p.stat().st_size, sha256(p), status, note))
        if status in ("제외", "생략", "확인 필요") or cur.lastrowid is None:
            return None
        return int(cur.lastrowid)

    def skip(self, file_id: int, reason: str, n: int = 1) -> None:
        self.skips[(file_id, reason)] += n

    def done(self, file_id: int, read: int, loaded: int) -> None:
        skipped = sum(n for (fid, _), n in self.skips.items() if fid == file_id)
        self.con.execute("UPDATE src_file SET rows_read=?, rows_loaded=?, rows_skipped=? WHERE file_id=?",
                         (read, loaded, skipped, file_id))

    def fail(self, file_id: int, msg: str) -> None:
        self.con.execute("UPDATE src_file SET status='오류', note=? WHERE file_id=?", (msg[:500], file_id))

    def flush(self) -> None:
        self.con.executemany("INSERT OR REPLACE INTO src_skip VALUES (?,?,?)",
                             [(fid, r, n) for (fid, r), n in sorted(self.skips.items())])
        self.con.commit()


def header_index(row: list) -> dict[str, int]:
    """머리글 한 줄 → {공백 뺀 이름: 열 번호}(같은 이름이면 앞 칸)."""
    out: dict[str, int] = {}
    for i, h in enumerate(row):
        k = nm(h)
        if k and k not in out:
            out[k] = i
    return out


def find_header(grid: list, must: tuple[str, ...], within: int = 12) -> int:
    """must 머리글이 모두 있는 첫 줄 번호(0부터) · 없으면 -1."""
    for i, r in enumerate(grid[:within]):
        names = {nm(c) for c in r}
        if all(m in names for m in must):
            return i
    return -1


def cell(row: list, ix: dict, name: str):
    j = ix.get(name)
    return row[j] if j is not None and j < len(row) else None


def blank(row) -> bool:
    return not any(str(c if c is not None else "").strip() for c in row)
