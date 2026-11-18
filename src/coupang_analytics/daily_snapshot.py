"""수집 원본 날짜별 보관 — output/{종류}/{계정ID}/{YYYY-MM-DD}.json.gz (소유자 승인 2026-11-06).

쿠폰 목록(wing_coupons)·재고현황(pricing·개당 비용)은 **수집 시점의 현재값**이라 지나면 다시 못 받는다. 그래서 계정·
수집일별로 쌓는다. output/_raw 는 매 실행 덮어쓰고, 판매분석_일별은 그날을 교체하지만 여기는 **덮어쓰지 않는다**.

파일 이름 규칙(같은 날 다시 저장해도 앞 파일은 그대로):
- 그날 첫 완료본 = {날짜}.json.gz · 그날 두 번째부터 = {날짜}_{시분초}.json.gz
- 중간에 멈춘 부분본 = {날짜}_부분.json.gz · 그다음 = {날짜}_부분_{시분초}.json.gz (완료본 판정에서 제외)

압축은 output/_raw 와 같은 gzip. 임시 파일에 쓰고 바꿔 끼움(반쯤 쓴 파일 없음). 날짜 = 실행 시작일이 아니라 저장 시각의 날짜
(자정을 넘긴 실행도 그 시점 값이므로).
"""
from __future__ import annotations

import gzip
import json
import os
from datetime import datetime
from pathlib import Path

COUPON_DIRNAME = "쿠폰목록_일별"
INVENTORY_DIRNAME = "재고현황_일별"
PRODUCT_INFO_DIRNAME = "상품정보_일별"   # 상품조회 칸 뽑아 보관(product_info · T-100)
_SUFFIX = ".json.gz"
_PARTIAL = "_부분"


def _now() -> datetime:
    return datetime.now()


def _day_dir(out_dir, dirname: str, account_id: str) -> Path:
    return Path(out_dir) / dirname / account_id


def has_day(out_dir, dirname: str, account_id: str) -> bool:
    """오늘 완료본이 있나(부분본은 아님)."""
    return (_day_dir(out_dir, dirname, account_id) / f"{_now():%Y-%m-%d}{_SUFFIX}").exists()


def complete_files(out_dir, dirname: str, account_id: str) -> list[Path]:
    """그 계정 완료본 파일(부분본 제외) — 이름순 = 날짜순(같은 날 시각 붙은 파일이 뒤)."""
    d = _day_dir(out_dir, dirname, account_id)
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob(f"*{_SUFFIX}") if _PARTIAL not in p.name)


def _free_path(d: Path, now: datetime, partial: bool) -> Path:
    """아직 없는 파일 이름 — 이미 있으면 시분초를, 같은 초에 또 있으면 일련번호를 붙임(덮어쓰기 없음)."""
    stem = f"{now:%Y-%m-%d}{_PARTIAL if partial else ''}"
    path = d / f"{stem}{_SUFFIX}"
    n = 1
    while path.exists():
        path = d / f"{stem}_{now:%H%M%S}{f'_{n}' if n > 1 else ''}{_SUFFIX}"
        n += 1
    return path


KEEP_DIRNAME = "수집일별보관"   # 덮어쓰는 파일의 전날 값(D-335) — 같은 폴더 아래 · 밑줄 없는 이름(계정 '{tok}_*' glob 에 안 걸림)


def _same_as_latest(d: Path, old: bytes) -> bool:
    latest = max(d.glob("*.gz"), default=None) if d.is_dir() else None   # 이름 = 날짜(같은 날 시각 붙은 것이 뒤)
    return latest is not None and gzip.decompress(latest.read_bytes()) == old


def keep_before_overwrite(path, today=None, new: bytes | None = None) -> Path | None:
    """덮어쓰기 **직전**에 부름 — 옛 파일이 오늘 전 수집분이면 그 값을 `{폴더}/수집일별보관/{파일 이름}/{옛 수집일}{확장자}.gz` 로 남김
    (소유자 D-335 · 11-18). 수집일 = 옛 파일 수정 날짜. 같은 날 다시 쓰기는 안 남김(그날 마지막 값은 다음날 첫 덮어쓰기 때 남음) ·
    새로 쓸 내용(new)이나 앞 보관본과 같으면 안 남김 · 보관본은 덮어쓰지 않음(같은 이름 있으면 시각 붙임) · 읽는 쪽 파일 이름 그대로.
    반환 = 남긴 경로(없으면 None). 저장 실패 = OSError 그대로(호출부가 덮어쓰기 전에 멈춤 — 옛 값 안 잃음)."""
    p = Path(path)
    if not p.is_file():
        return None
    st = p.stat()
    when = datetime.fromtimestamp(st.st_mtime)
    if when.date() == (today or _now().date()):
        return None
    old = p.read_bytes()
    raw = gzip.decompress(old) if p.suffix == ".gz" else old
    d = p.parent / KEEP_DIRNAME / p.name
    if (new is not None and new == old) or _same_as_latest(d, raw):
        return None
    ext = "".join(p.suffixes[-2:]) if p.suffix == ".gz" else p.suffix + ".gz"
    d.mkdir(parents=True, exist_ok=True)
    dst = d / f"{when:%Y-%m-%d}{ext}"
    n = 1
    while dst.exists():
        dst = d / f"{when:%Y-%m-%d}_{when:%H%M%S}{f'_{n}' if n > 1 else ''}{ext}"
        n += 1
    tmp = dst.with_name(dst.name + ".tmp")
    tmp.write_bytes(old if p.suffix == ".gz" else gzip.compress(old))
    os.replace(tmp, dst)
    return dst


def save(out_dir, dirname: str, account_id: str, payload: dict, partial: bool = False) -> Path:
    """머리 칸(수집·계정·날짜)을 붙여 저장하고 경로를 돌려줌. 저장 실패는 OSError(호출부가 비치명 처리)."""
    now = _now()
    d = _day_dir(out_dir, dirname, account_id)
    d.mkdir(parents=True, exist_ok=True)
    path = _free_path(d, now, partial)
    rec = {"수집": now.isoformat(timespec="seconds"), "계정": account_id, "날짜": f"{now:%Y-%m-%d}", **payload}
    tmp = path.with_name(path.name + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(rec, fh, ensure_ascii=False)
    os.replace(tmp, path)
    return path
