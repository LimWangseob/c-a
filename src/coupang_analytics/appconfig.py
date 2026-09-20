"""설정을 **프로젝트 루트의 config.json(보존 폴더)** 에 저장·관리 — 레지스트리(QSettings) 대체/병행.

- **비밀(API/SA 키)** 은 config.json 에 넣지 않는다 → 그대로 credstore(DPAPI, 이 PC 전용 암호화).
- config.json 에는 **비밀 아님** 만: 구글시트 입력/출력 링크·입력소스·마지막 입력파일 등. 키 형식은 QSettings 와
  같은 `'group/name'`(예 `gsheet/output_url`) 이라 레지스트리와 1:1 호환.
- **config.json 존재 = 프로젝트 루트 표식**([apppaths.data_root] 가 이 폴더를 상태 폴더로 삼음).
- 앱은 이 파일을 **읽고 쓴다**. 개발(노트북)·운용(PC)이 같은 파일 규칙으로 동작한다(소유자 2026-09-20).

호환: 읽기는 config.json 우선, 없으면 호출측이 레지스트리 폴백. 쓰기는 config.json + (호출측이) 레지스트리
병행 → 예전 방식과 섞여 있어도 안 깨진다(점진 이관).
"""
from __future__ import annotations

import json

from .apppaths import config_path


def load() -> dict:
    """config.json 을 dict 로 읽는다(없거나 손상 시 빈 dict)."""
    try:
        p = config_path()
        if p.is_file():
            d = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                return d
    except (OSError, ValueError):
        pass
    return {}


def save(cfg: dict) -> bool:
    """config.json 저장(utf-8·들여쓰기). 성공=True."""
    try:
        p = config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except OSError:
        return False


def get(key: str, default: str = "") -> str:
    """'group/name' 설정값(문자열). 없으면 default."""
    v = load().get(key, default)
    return v if isinstance(v, str) else default


def set(key: str, value: str) -> bool:  # noqa: A003  (설정 API 이름으로 set 이 자연스러움)
    """'group/name' 설정값 저장(다른 값은 보존)."""
    cfg = load()
    cfg[key] = value
    return save(cfg)


def update(items: dict) -> bool:
    """여러 설정을 한 번에 저장(기존 보존)."""
    cfg = load()
    cfg.update({k: v for k, v in items.items() if v is not None})
    return save(cfg)


def ensure_exists() -> bool:
    """config.json 이 없으면 빈 설정으로 만들어 **프로젝트 루트 표식** 을 남긴다. 있으면 그대로 True."""
    if config_path().is_file():
        return True
    return save(load())
