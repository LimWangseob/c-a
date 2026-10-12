"""대장 줄 ↔ 쿠팡 VID **매칭 고정(앵커)** 저장소 — D-009(소유자 2026-10-09).

한 번 확정된 매칭(괄호 정확일치·AI 확신 high/medium)은 `output/_매칭고정.json` 에 계정별로 남기고, 다음 실행은
**그 VID 로 바로 매칭**한다(AI 재호출 없음 → 날마다 같은 결과·AI 실패일에도 블록 유지). 그 VID 가 쿠팡 상품조회에서
사라졌을 때만 다시 매칭한다. 대장 상품명을 바꾸면 키가 달라져 새로 매칭된다(= 담당자 수정 반영).

형식: {계정ID: {대장명(공백정규화): {vids, title, kind, options:[[label,[vid..],[pid..]]], how, conf, at}}}.
쓰기는 temp+os.replace 원자적 저장(중단 시 파일 손상 방지·proxy_blocklist 와 같은 방식).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

ANCHOR_FILE = "_매칭고정.json"
MATCH_RESULT_FILE = "_매칭결과.json"   # ① 매칭 결과 전부(대장 줄 → VID) — 그로스 재고 역기록용(2026-10-12)


def anchor_path(out_dir: str | Path | None = None) -> Path:
    """앵커 파일 경로 — 기본 = 데이터 폴더의 output(통계 마스터와 같은 곳·재배포에도 보존)."""
    if out_dir is None:
        from . import apppaths
        out_dir = Path(apppaths.data_root()) / "output"
    return Path(out_dir) / ANCHOR_FILE


def key_of(name: str) -> str:
    """대장명 키 — 공백·줄바꿈만 정규화(글자는 그대로: 담당자가 이름을 바꾸면 새 매칭)."""
    return " ".join(str(name).split())


def _load_all(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AnchorFileError(f"매칭 고정 파일 읽기 실패({path.name}): {exc}") from exc
    return data if isinstance(data, dict) else {}


class AnchorFileError(Exception):
    """앵커 파일 손상 — 호출부가 로그로 알리고 이번 실행은 고정 없이(AI 매칭) 진행한다."""


def load_anchors(account_id: str, path: Path | None = None) -> dict[str, dict]:
    """그 계정의 앵커 {대장명키: 기록}. 파일 없으면 빈 dict."""
    rec = _load_all(path or anchor_path()).get(account_id) or {}
    return {k: v for k, v in rec.items() if isinstance(v, dict) and v.get("vids")}


def save_anchors(account_id: str, anchors: dict[str, dict], path: Path | None = None) -> None:
    """그 계정 앵커를 통째 교체 저장(다른 계정은 보존). 원자적 쓰기."""
    _save_account(account_id, anchors, path or anchor_path())


def match_result_path(out_dir: str | Path | None = None) -> Path:
    """① 매칭 결과(전부) 파일 경로 — 매칭 고정 파일과 같은 폴더."""
    return anchor_path(out_dir).with_name(MATCH_RESULT_FILE)


def save_match_result(account_id: str, mapping: dict[str, list[str]], path: Path | None = None) -> None:
    """① 매칭 결과 **전부**(고정 여부 무관 — AI 낮은 확신·규칙 대체 포함) {대장명키: [VID…]} 를 계정별로 교체 저장.
    관리대장 그로스 재고 역기록이 대장 줄 → VID 블록을 찾는 데 쓴다(이름 유사도 대신 AI 매칭 결과·2026-10-12)."""
    _save_account(account_id, mapping, path or match_result_path())


def load_match_results(path: Path | None = None) -> dict[str, dict[str, list[str]]]:
    """{계정ID: {대장명키: [VID…]}} — 파일 없으면 빈 dict. 손상이면 AnchorFileError(호출부가 로그)."""
    return {a: {k: list(v) for k, v in m.items() if isinstance(v, list) and v}
            for a, m in _load_all(path or match_result_path()).items() if isinstance(m, dict)}


def _save_account(account_id: str, value: dict, p: Path) -> None:
    try:
        data = _load_all(p)
    except AnchorFileError:
        data = {}                                   # 손상 파일은 이번 저장으로 재생성(호출부가 이미 로그)
    data[account_id] = value
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
