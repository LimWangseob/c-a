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
_SUFFIX = ".json.gz"
_PARTIAL = "_부분"


def _now() -> datetime:
    return datetime.now()


def _day_dir(out_dir, dirname: str, account_id: str) -> Path:
    return Path(out_dir) / dirname / account_id


def has_day(out_dir, dirname: str, account_id: str) -> bool:
    """오늘 완료본이 있나(부분본은 아님)."""
    return (_day_dir(out_dir, dirname, account_id) / f"{_now():%Y-%m-%d}{_SUFFIX}").exists()


def _free_path(d: Path, now: datetime, partial: bool) -> Path:
    """아직 없는 파일 이름 — 이미 있으면 시분초를, 같은 초에 또 있으면 일련번호를 붙임(덮어쓰기 없음)."""
    stem = f"{now:%Y-%m-%d}{_PARTIAL if partial else ''}"
    path = d / f"{stem}{_SUFFIX}"
    n = 1
    while path.exists():
        path = d / f"{stem}_{now:%H%M%S}{f'_{n}' if n > 1 else ''}{_SUFFIX}"
        n += 1
    return path


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
