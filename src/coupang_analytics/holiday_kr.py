"""한국 공휴일·영업일 (POLICY `HOLIDAY_KR`). SSOT=designs/SETTLEMENT_MODULE.md §2.

- 공휴일 **하드코딩 금지**: 외부 소스(한국천문연구원 특일정보 API)를 연 단위로 조회해 로컬 캐시
  (`{cache_dir}/_holidays_{year}.json`) + 임시공휴일 수동 추가(`extra`). 조회 함수는 호출부가 주입(2단계 라이브 연동).
- **조회 실패 = HolidaySourceError**(0일 가정 금지 — xlsb '평일공휴일 수동입력 0' 결함 재현 금지).
- 영업일 = 토·일·공휴일(대체공휴일 포함) 제외. 계산 함수는 공휴일 집합을 인자로 받는 **순수 함수**(테스트는 골든
  `_meta.holidays_used` 주입 — 실 API 미호출).
- 대체공휴일 규칙(`substitute_holidays`): 국경일·어린이날·성탄절·부처님오신날 = 토·일 겹침 시 대체 /
  설·추석 = 일요일 또는 다른 공휴일 겹침만 대체(**토요일 겹침은 대체 없음**). 실측 앵커: 2026-08-15(토)→08-17,
  2026 추석 09-24~26(목~토)→대체 없음(09-28 영업일).
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

KIND_NATIONAL = "national"    # 국경일·어린이날·성탄절·부처님오신날 — 토·일 겹침 대체
KIND_LUNAR = "lunar"          # 설·추석 연휴 — 일요일·다른 공휴일 겹침만 대체
KIND_OTHER = "other"          # 대체 규칙 없음(신정·현충일·선거일·임시공휴일 등)


class HolidaySourceError(Exception):
    """공휴일 소스를 얻지 못함 — 지급일 계산 중단(0일 가정 금지)."""


# ── 영업일 (순수) ─────────────────────────────────────────────────
def is_business_day(d: date, holidays) -> bool:
    """토·일·공휴일이 아니면 영업일."""
    return d.weekday() < 5 and d not in holidays


def next_business_day(d: date, holidays) -> date:
    """d 포함, d 이후 첫 영업일."""
    while not is_business_day(d, holidays):
        d += timedelta(days=1)
    return d


def add_business_days(start: date, n: int, holidays) -> date:
    """start **다음날부터** 영업일을 n개 센 날(마감일+n영업일). n<1 은 ValueError."""
    if n < 1:
        raise ValueError(f"영업일 수는 1 이상이어야 함: {n}")
    d = start
    while n:
        d += timedelta(days=1)
        if is_business_day(d, holidays):
            n -= 1
    return d


# ── 대체공휴일 (순수) ─────────────────────────────────────────────
def _kinds(v) -> tuple:
    return tuple(v) if isinstance(v, (tuple, list, set)) else (v,)


def _lunar_blocks(entries: dict) -> list[list[date]]:
    """설·추석 연휴를 연속 날짜 묶음으로."""
    days = sorted(d for d, k in entries.items() if KIND_LUNAR in _kinds(k))
    blocks: list[list[date]] = []
    for d in days:
        if blocks and d - blocks[-1][-1] == timedelta(days=1):
            blocks[-1].append(d)
        else:
            blocks.append([d])
    return blocks


def _first_free_weekday(after: date, taken: set) -> date:
    d = after + timedelta(days=1)
    while d.weekday() >= 5 or d in taken:
        d += timedelta(days=1)
    return d


def substitute_holidays(entries: dict) -> set[date]:
    """{날짜: 종류 또는 (종류, …)} → 대체공휴일 날짜 집합(원 공휴일 제외). 대체일 = 겹친 휴일(연휴) 다음 첫
    비휴일 평일. 한 날짜에 공휴일이 둘 이상이면 종류를 튜플로(예 2025-05-05 어린이날+부처님오신날).

    - KIND_NATIONAL: 토·일 겹침 또는 다른 공휴일과 같은 날 → 대체 1일.
    - KIND_LUNAR: 연휴 중 하루라도 **일요일** 또는 다른 공휴일과 겹치면 연휴 끝 다음 비휴일 평일 1일
      (토요일만 겹치면 대체 없음)."""
    taken = set(entries)
    subs: set[date] = set()
    for d, v in sorted(entries.items()):
        ks = _kinds(v)
        if KIND_NATIONAL in ks and KIND_LUNAR not in ks and (d.weekday() >= 5 or len(ks) > 1):
            subs.add(_first_free_weekday(d, taken | subs))
    for block in _lunar_blocks(entries):
        if any(d.weekday() == 6 or len(_kinds(entries[d])) > 1 for d in block):
            subs.add(_first_free_weekday(block[-1], taken | subs))
    return subs


# ── 공휴일 집합(캐시·소스) ────────────────────────────────────────
def _cache_path(cache_dir, year: int) -> Path:
    return Path(cache_dir) / f"_holidays_{year}.json"


def holidays(year: int, *, fetch=None, cache_dir="output", extra=()) -> set[date]:
    """그 해 공휴일(대체공휴일 포함) 집합. 캐시가 있으면 캐시, 없으면 fetch(year) 로 조회해 캐시에 저장.

    fetch(year) → 공휴일 날짜들(대체공휴일 포함, 특일정보 API 결과). fetch 없고 캐시도 없거나, fetch 실패·빈 결과면
    HolidaySourceError(0일 가정 금지). extra = 임시공휴일 수동 추가(날짜 또는 'YYYY-MM-DD')."""
    p = _cache_path(cache_dir, year)
    if p.exists():
        days = {date.fromisoformat(s) for s in json.loads(p.read_text(encoding="utf-8"))}
    else:
        days = _fetch_and_cache(year, fetch, p)
    return days | {_as_date(d) for d in extra}


def _as_date(d) -> date:
    return d if isinstance(d, date) else date.fromisoformat(str(d))


def _fetch_and_cache(year: int, fetch, p: Path) -> set[date]:
    """소스 조회 → 검증(비어 있음·다른 해 섞임 = 오류) → 캐시 저장. 실패는 전부 HolidaySourceError."""
    if fetch is None:
        raise HolidaySourceError(f"{year}년 공휴일 캐시({p})가 없고 조회 소스도 없음 — 지급일 계산 불가")
    try:
        days = {_as_date(d) for d in fetch(year)}
    except Exception as exc:
        raise HolidaySourceError(f"{year}년 공휴일 조회 실패: {exc.__class__.__name__}: {exc}") from exc
    if not days:
        raise HolidaySourceError(f"{year}년 공휴일 조회 결과가 비어 있음 — 소스 확인 필요")
    if any(d.year != year for d in days):
        raise HolidaySourceError(f"{year}년 공휴일 조회 결과에 다른 해 날짜가 섞임")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(d.isoformat() for d in days)), encoding="utf-8")
    return days
