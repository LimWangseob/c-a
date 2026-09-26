"""파이프라인 공용 경로/단계 헬퍼 (leaf 모듈 — pipeline·pipeline_ranks·pipeline_gsheet 공유).

순환 import 방지용: 이 모듈은 config·workbook 등 leaf 만 import 하고 pipeline 을 import 하지 않는다.
pipeline.py 가 이 심볼들을 다시 import 해 `pipeline.X` 공개 API(UI·도구·핀)를 그대로 유지한다.
"""
from __future__ import annotations

import json
from datetime import datetime
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


def master_exists(out_dir: str | Path = "output") -> bool:
    """이어쓸 통계 마스터가 있는지(UI가 '기존 통계에 추가' 옵션 노출 여부 판단)."""
    return _master_path(out_dir).exists()


def _run_stage_path(out_dir: str | Path) -> Path:
    return Path(out_dir) / _RUN_STAGE_JSON


def write_run_stage(stage: str, out_dir: str | Path = "output") -> None:
    """전체실행/무인의 진행 단계를 오늘 날짜로 기록(재부팅 복구용).

    stage: 'sales'=①판매수집 완료(다음=②) · 'ranks'=②키워드 완료(다음=③) · 'done'=전부 완료.
    ②③은 마스터에 직접 쓰고 진행중 파일을 안 남기므로, 이 마커로 어디까지 했는지 남긴다.
    """
    try:
        _run_stage_path(out_dir).write_text(
            json.dumps({"date": datetime.now().strftime("%Y-%m-%d"), "stage": stage,
                        "at": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False),
            encoding="utf-8")
    except OSError:
        pass


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


def _load_latest_wb(out: Path):
    """최신 결과 워크북 로드 — 마스터 우선, 없으면 진행중. (wb, path) 또는 (None, None)."""
    for p in (_master_path(out), _partial_path(out)):
        if p.exists():
            return OutputWorkbook.load(p), p
    return None, None
