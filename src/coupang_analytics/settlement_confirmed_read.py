"""쿠팡 확정 장부(`output/정산확정`) 읽기 — 닫힌 달 = 장부 값, 안 닫힌 달 = 원본(D-419 ② · T-188). 장부 만들기 = `settlement_confirmed`.

- 켜는 곳 = 정산서 배치 일 함수(`use(폴더)`) 뿐. 안 켜면(기본 · 시험·손 도구·받기) 아래 함수는 늘 '장부 없음' = 원본(옛 동작).
- 배치가 바로 앞 단계에서 장부를 원본과 대조해 다르면 그 달을 다시 열고(원본 사용), 그 단계가 실패하면 장부를 켜지 않는다 →
  켜진 장부의 닫힌 달 값 = 원본 값.
- 장부에 든 것 = 쿠팡 원문 값(지급 줄 전 칸 · 엑셀 칸 값 · 광고 청구 json)뿐. 읽는 코드(파서)는 원본과 같은 것을 쓴다.
- 파일 열쇠 = (계정ID, 파일 이름의 계정명 뒤) — 계정 이름이 바뀌어도 같은 파일.
다른 정산 모듈을 import 하지 않음(`settlement_files`·`settlement_read_store` 가 이 모듈을 씀).
"""
from __future__ import annotations

import gzip
import hashlib
import json
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

DIRNAME = "정산확정"                    # output/정산확정
INDEX = "_장부.json"                    # 계정×달 상태·관찰·이력·파일 지문(건별 본문과 따로)
CASES, MONTHS, OLD = "건별", "월별", "보관"
CLOSED = "닫힘"
PAY, SALE, COST, AD = "지급 줄", "판매 줄", "비용 줄", "광고 청구"      # 본문 칸
_root: Path | None = None
_closed: dict = {}                      # (계정ID, 'YYYY-MM') → 본문 지문
_files: dict = {}                       # (계정ID, 파일 이름 뒤) → ('YYYY-MM', 본문 칸, 원본 sha256)


class ConfirmedBroken(ValueError):
    """장부 파일이 깨짐·지문이 다름 — 조용히 원본으로 바꾸지 않고 그 단계에서 드러냄(장부 갱신 단계가 먼저 걸러 다시 엶)."""


def file_key(path) -> tuple[str, str]:
    """원본 파일 이름 → (계정ID, 계정명 뒤 이름). 이름 = `{계정명}_…`(계정명 끝 = '-계정ID')."""
    acct, _, tail = Path(path).name.partition("_")
    return acct.rsplit("-", 1)[-1], tail


# ── 칸 값 ↔ json ──
def _dump(o):
    if isinstance(o, datetime):
        return {"$t": o.isoformat()}
    if isinstance(o, date):
        return {"$d": o.isoformat()}
    raise TypeError(f"장부에 넣을 수 없는 칸 값 {type(o).__name__}")


def _load(d: dict):
    if len(d) == 1:
        if "$t" in d:
            return datetime.fromisoformat(d["$t"])
        if "$d" in d:
            return date.fromisoformat(d["$d"])
    return d


def encode(body: dict) -> bytes:
    """본문 → gzip json(같은 값 = 같은 바이트)."""
    return gzip.compress(json.dumps(body, ensure_ascii=False, default=_dump, separators=(",", ":")).encode("utf-8"), 6, mtime=0)


def decode(data: bytes) -> dict:
    return json.loads(gzip.decompress(data).decode("utf-8"), object_hook=_load)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def case_path(root: Path, aid: str, ym: str) -> Path:
    return Path(root) / CASES / aid / f"{ym}.json.gz"


# ── 켜기 ──
def use(root: Path | None) -> int:
    """장부 폴더를 정하고 켬(None = 끔) → 닫힌 달 수. 장부 없음(첫 배치 전) = 0."""
    global _root
    _root = None
    _closed.clear()
    _files.clear()
    _body.cache_clear()
    if root is None or not (Path(root) / INDEX).is_file():
        return 0
    idx = json.loads((Path(root) / INDEX).read_text(encoding="utf-8"))
    for aid, months in idx["계정"].items():
        for ym, e in months.items():
            if e["상태"] == CLOSED:
                _closed[aid, ym] = e["본문"]
                for kind, tails in e["파일"].items():
                    _files.update({(aid, t): (ym, kind, sha) for t, sha in tails.items()})
    _root = Path(root)
    return len(_closed)


@lru_cache(maxsize=8)                   # 정산 파일은 계정·정산일 순으로 읽음 — 달 몇 개가 번갈아 나옴
def _body(root: str, aid: str, ym: str, want: str) -> dict:
    p = case_path(Path(root), aid, ym)
    data = p.read_bytes()
    if digest(data) != want:
        raise ConfirmedBroken(f"확정 장부 본문이 장부 기록과 다름 — {p}")
    return decode(data)


def _entry(path) -> tuple[dict, str] | None:
    """닫힌 달의 파일이면 (본문 안의 그 파일 기록, 원본 sha) · 아니면 None(원본을 읽음)."""
    hit = _files.get(file_key(path)) if _root is not None else None
    if hit is None:
        return None
    (aid, tail), (ym, kind, sha) = file_key(path), hit
    return _body(str(_root), aid, ym, _closed[aid, ym])[kind][tail], sha


# ── 읽는 쪽이 부르는 것 ──
def sheets(path) -> dict | None:
    """닫힌 달의 정산 파일·비용 리포트 → {시트: 격자}(장부 값) · 아니면 None."""
    got = _entry(path)
    return None if got is None else got[0]["칸"]


def ad_json(path) -> dict | None:
    """닫힌 달의 광고정산 json → 내용(장부 값) · 아니면 None."""
    got = _entry(path)
    return None if got is None else got[0]["칸"]


def source_sha(path) -> str | None:
    """닫힌 달 파일의 원본 sha256(장부 기록 — 읽은 결과 저장의 열쇠) · 아니면 None."""
    hit = _files.get(file_key(path)) if _root is not None else None
    return None if hit is None else hit[2]


def pay_rows(aid: str, ch: str, rows: list) -> list:
    """지급 줄(원본 파일 순서 = 정산일·기간 시작) → 닫힌 판매 달의 줄만 장부 줄로 바꾼 목록."""
    months = [ym for a, ym in _closed if a == aid] if _root is not None else []
    if not months:
        return rows
    out = [r for r in rows if str(r["기간 시작"])[:7] not in months]
    for ym in sorted(months):
        out += _body(str(_root), aid, ym, _closed[aid, ym])[PAY].get(ch, [])
    return sorted(out, key=lambda r: (str(r["정산일"]), str(r["기간 시작"])))
