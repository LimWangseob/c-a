"""파이프라인 공용 경로/단계 헬퍼 (leaf 모듈 — pipeline·pipeline_ranks·pipeline_gsheet 공유).

순환 import 방지용: 이 모듈은 config·workbook 등 leaf 만 import 하고 pipeline 을 import 하지 않는다.
pipeline.py 가 이 심볼들을 다시 import 해 `pipeline.X` 공개 API(UI·도구·핀)를 그대로 유지한다.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config
from .workbook import OutputWorkbook

_PROFILE = "data/chrome-pipeline"   # 검색 순위용(비로그인)
_PROFILES_DIR = "data/profiles"     # 계정별 로그인 프로필
# 진행 중(미완료) 통합 엑셀 + 진행 상태(같은 날 크래시 복구용). 완료되면 상태파일 삭제.
_PARTIAL_XLSX = f"{config.OUTPUT_FILE_PREFIX}_진행중.xlsx"
_PROGRESS_JSON = f"{config.OUTPUT_FILE_PREFIX}_진행중.json"
# 통계 마스터(지속형) — 매일 실행이 이어써서 날짜 컬럼을 누적하고 키워드를 동결한다.
_MASTER_XLSX = f"{config.OUTPUT_FILE_PREFIX}_통계.xlsx"
# 전체실행/무인의 **진행 단계** 마커(재부팅 복구용) — ②③은 진행중 파일을 안 만드므로 별도로 단계를 남긴다.
_RUN_STAGE_JSON = f"{config.OUTPUT_FILE_PREFIX}_실행단계.json"


def _partial_path(out_dir: str | Path) -> Path:
    return Path(out_dir) / _PARTIAL_XLSX


def _progress_path(out_dir: str | Path) -> Path:
    return Path(out_dir) / _PROGRESS_JSON


def _master_path(out_dir: str | Path) -> Path:
    return Path(out_dir) / _MASTER_XLSX


def _snapshot_path(out_dir: str | Path, now: datetime) -> Path:
    """그날 완료본 스냅샷(감사·백업용). 마스터가 손상돼도 날짜별 본이 남는다."""
    return Path(out_dir) / f"{config.OUTPUT_FILE_PREFIX}_통계_{now.strftime('%y%m%d')}.xlsx"


def run_day_column(day: date) -> date:
    """실행한 날의 날짜 칸 = 그 전날(판매 기준일 D · D-368): 11-20 00:10 실행 = 11.19 칸(판매 11-19 · 순위·재고 = 실행 때 측정).
    오늘 실행·무인·지난 칸 순위 보충·순위 묶음 갱신이 같은 규칙을 쓰게 하는 한 곳."""
    return day - timedelta(days=1)


def column_label(date_label: str) -> str:
    """날짜 칸 이름 = 년도 없는 '월.일'(예 '2026-10-09' → '10.09'). ①(run_full)·③(track_ranks_stage)이 같은 칸을 쓰게
    하는 단일 규칙 — ③이 ISO 를 그대로 칸 이름으로 써 ①과 다른 칸이 생기던 문제(simulate 20). 날짜가 아니면 그대로."""
    try:
        return datetime.strptime(str(date_label), "%Y-%m-%d").strftime("%m.%d")
    except ValueError:
        return str(date_label)


def master_exists(out_dir: str | Path = "output") -> bool:
    """이어쓸 통계 마스터가 있는지(UI가 '기존 통계에 추가' 옵션 노출 여부 판단)."""
    return _master_path(out_dir).exists()


def _run_stage_path(out_dir: str | Path) -> Path:
    return Path(out_dir) / _RUN_STAGE_JSON


_RUN_DAYS_KEEP = 14   # 날짜별 단계 기록(days) 보관 일수 — 보충 범위(pipeline_stages._CATCHUP_DAYS)보다 넉넉히


def _read_stage_file(out_dir) -> dict:
    p = _run_stage_path(out_dir)
    try:
        m = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        return {}
    return m if isinstance(m, dict) else {}


def run_days(marker: dict | None) -> dict:
    """{실행 날짜(ISO): 마지막 단계} — 단계 기록의 'days'. 'days' 없는 옛 파일 = 맨 위 date·stage 한 날(T-47 이어받기)."""
    if not marker:
        return {}
    days = marker.get("days")
    if isinstance(days, dict):
        return {str(k): str(v) for k, v in days.items()}
    day, stage = marker.get("date"), marker.get("stage")
    return {str(day): str(stage)} if day and stage else {}


def _write_stage_file(m: dict, days: dict, out_dir) -> None:
    m["days"] = dict(sorted(days.items())[-_RUN_DAYS_KEEP:])
    try:
        _run_stage_path(out_dir).write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def write_run_stage(stage: str, out_dir: str | Path = "output", day: str | None = None,
                    record_day: bool = True) -> None:
    """전체실행/무인의 진행 단계를 오늘 날짜로 기록(재부팅 복구용).

    stage: 'sales'=①판매수집 완료(다음=②) · 'ranks'=②키워드 완료(다음=③) · 'done'=전부 완료.
    ②③은 마스터에 직접 쓰고 진행중 파일을 안 남기므로, 이 마커로 어디까지 했는지 남긴다.
    맨 위 date·stage·at = 지금 시각 기준(재부팅 복구·정산이 읽음 · 그대로) · days[day] = 실행 날짜별 마지막 단계
    (day = 실행 시작일 · 자정 넘어 끝나도 그 실행 날짜 · 최근 며칠 못 끝낸 ③ 보충용 T-47).
    record_day=False = 맨 위만 갱신·days 는 그대로(날짜 지정 실행 — 그날 정기 ③ 미완료가 다음 날 보충에 남게 T-54).
    """
    now = datetime.now()
    days = run_days(_read_stage_file(out_dir))
    if record_day:
        days[day or now.strftime("%Y-%m-%d")] = stage
    _write_stage_file({"date": now.strftime("%Y-%m-%d"), "stage": stage, "at": now.isoformat(timespec="seconds")},
                      days, out_dir)


def mark_run_day(day: str, stage: str, out_dir: str | Path = "output") -> None:
    """지난 실행 날짜 하나의 단계만 바꿈(맨 위 date·stage·at 은 그대로) — 보충으로 그날 ③ 빈 칸을 다 채우면 'done'."""
    m = _read_stage_file(out_dir)
    days = run_days(m)
    days[day] = stage
    _write_stage_file(m, days, out_dir)


def read_run_stage(out_dir: str | Path = "output") -> dict | None:
    """오늘의 진행 단계 마커(dict) 반환 — 없거나 어제 이전이면 None(오늘 것만 유효)."""
    p = _run_stage_path(out_dir)
    if not p.exists():
        return None
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(m, dict) or m.get("date") != datetime.now().strftime("%Y-%m-%d"):
        return None
    return m


def read_last_run_stage(out_dir: str | Path = "output") -> dict | None:
    """마지막 실행의 단계 기록(dict) — 날짜와 상관없이(read_run_stage 는 오늘 것만). 없거나 깨졌으면 None.
    다음 날 실행이 '어제 ③ 을 못 끝냈는지' 판단하는 데 쓴다(T-20 재발 방지 (가) · pipeline_stages)."""
    p = _run_stage_path(out_dir)
    try:
        m = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except (OSError, ValueError):
        return None
    return m if isinstance(m, dict) else None

def _load_latest_wb(out: Path):
    """최신 결과 워크북 로드 — 마스터 우선, 없으면 진행중. (wb, path) 또는 (None, None)."""
    for p in (_master_path(out), _partial_path(out)):
        if p.exists():
            return OutputWorkbook.load(p), p
    return None, None
