"""정산 다운로드 자동 대기·재개 판단(순수 로직·오프라인 검증) — 운용 PC에서 기존 앱과 번갈아 돌기.

소유자 결정(2026-10-06): 정산은 **기존 앱 무인 실행의 ①판매수집이 끝난 직후 재개**하고, **다음날 17:40에 멈춘다**
(18:00 무인 실행 전 — 진행 중 요청 마무리·받기·Chrome 닫기 여유). 로그인을 쓰는 건 ①판매수집뿐이라 ②키워드·
③순위(로그인 없음·별도 프로필)와는 겹쳐도 된다.

판단 기준 = 앱이 남기는 단계 기록(`output/…_실행단계.json`: stage sales=①완료·ranks=②완료·done=전부, at=기록 시각).
- 주기 시작 P = 가장 최근의 17:40.
- P 이후에 ①완료(sales/ranks/done) 기록이 있으면 → 실행(다음 17:40까지).
- 기록이 없으면 대기. 단 P + FALLBACK(8시간 20분 = 새벽 2시)이 지나도 없으면 앱이 그날 안 돈 것으로 보고 실행
  (같은 계정 Chrome 이 떠 있으면 그 계정은 건너뛰는 안전장치가 그대로 있음) — 이유를 기록에 남긴다.
- 이번 주기를 이미 끝까지 마쳤으면 다음 주기까지 대기(하루 1바퀴 — 매번 26계정 다시 로그인하지 않음).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

STOP_HM = "17:40"
FALLBACK = timedelta(hours=8, minutes=20)
SALES_DONE = ("sales", "ranks", "done")


def cycle_start(now: datetime, stop_hm: str = STOP_HM) -> datetime:
    """가장 최근의 멈춤 시각(오늘 17:40 이 지났으면 오늘, 아니면 어제)."""
    hh, mm = (int(x) for x in stop_hm.split(":"))
    today = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return today if now >= today else today - timedelta(days=1)


def read_marker(path) -> tuple[dict | None, str]:
    """앱 단계 기록 → ({'stage','at'(datetime)}, 사유). 없거나 깨졌으면 (None, 사유) — 사유는 호출부가 기록."""
    p = Path(path)
    if not p.exists():
        return None, f"앱 단계 기록 없음({p.name})"
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
        return {"stage": str(m["stage"]), "at": datetime.fromisoformat(m["at"])}, ""
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return None, f"앱 단계 기록 읽기 실패: {exc.__class__.__name__}: {exc}"


def decide(now: datetime, marker: dict | None, last_cycle: datetime | None, stop_hm: str = STOP_HM
           ) -> tuple[str, str, datetime]:
    """→ ('run'|'wait', 사유, 이번 주기 시작 P). 실행이면 멈출 시각 = P + 1일."""
    p = cycle_start(now, stop_hm)
    if last_cycle is not None and last_cycle >= p:
        return "wait", f"이번 주기({p:%m-%d %H:%M}~) 정산 완료 — 다음 ①판매수집 완료까지 대기", p
    if marker and marker["stage"] in SALES_DONE and marker["at"] >= p:
        return "run", f"앱 ①판매수집 완료 기록({marker['at']:%m-%d %H:%M}·{marker['stage']}) 확인 — 재개", p
    if now >= p + FALLBACK:
        return "run", (f"{p + FALLBACK:%m-%d %H:%M} 까지 앱 ①판매수집 완료 기록 없음 — 앱이 안 돈 것으로 보고 재개"
                       "(계정 Chrome 사용 중이면 그 계정 건너뜀)"), p
    return "wait", f"앱 ①판매수집 완료 기다림(주기 {p:%m-%d %H:%M}~·늦어도 {p + FALLBACK:%m-%d %H:%M} 재개)", p


def load_last_cycle(path) -> datetime | None:
    p = Path(path)
    if not p.exists():
        return None
    return datetime.fromisoformat(json.loads(p.read_text(encoding="utf-8"))["last_cycle"])


def save_last_cycle(path, cycle: datetime) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps({"last_cycle": cycle.isoformat(timespec="seconds")}), encoding="utf-8")
    tmp.replace(p)
