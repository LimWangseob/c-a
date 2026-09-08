"""확정 키워드 저장소 — (사업자, 상품) → 키워드 목록.

키워드 추천 화면에서 사람이 확정한 3~5개를 저장한다. 이후 워크북 생성 시
시트8 노출순위 행으로 반영되고 rank.py 가 추적한다. 비밀정보 아님(로컬 JSON).
"""
from __future__ import annotations

import json
from pathlib import Path

DEFAULT_PATH = Path("data") / "keywords.json"


def _key(business: str, product: str) -> str:
    return f"{business}||{product}"


def load_all(path: str | Path = DEFAULT_PATH) -> dict[str, list[str]]:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def get(business: str, product: str, path: str | Path = DEFAULT_PATH) -> list[str]:
    return load_all(path).get(_key(business, product), [])


def save(business: str, product: str, keywords: list[str], path: str | Path = DEFAULT_PATH) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = load_all(path)
    data[_key(business, product)] = list(dict.fromkeys(keywords))  # 중복 제거·순서 유지
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
