"""정산 다운로드 실행 판단(순수 로직·오프라인 검증) — 18:00 앱과 함께 떠서 ①판매수집 완료를 기다렸다가 받고,
다 받으면 끝난다(늦어도 다음 날 17:55).

**D-021(소유자 2026-10-10, D-010 의 '①뒤 기동'을 대체)**: 회차 = 18:00 ~ 다음 날 17:55(`cycle_window`).
18:00 무인 앱이 시작하면서 정산도 띄운다 → 정산은 **이번 회차의 ①판매수집 완료 기록**(`sales_done_in_cycle`)이
생길 때까지 대기 → 받기 → 다 받으면 종료·17:55 가 되면 종료 → 18:00 둘 다 다시 기동. 앱을 사람이 끄면(배포 등)
정산도 함께 종료(app_process.watch_parent·D-020).

소유자 결정(D-010·2026-10-09, 2026-10-07 '24시간 감시'를 대체):
- 18:00 앱이 시작되면 기존 정산 프로그램을 끝내고, **①판매수집이 끝나면 앱이 정산을 띄운다**(예약작업 없음).
- 정산은 ②키워드·③순위와 겹쳐도 계속 돈다(로그인을 쓰는 건 ①뿐·③은 비로그인 별도 프로필).
- 받을 게 있으면(소급) 연속으로 바퀴를 돌고, **모든 정산 파일을 받으면 기록하고 정상 종료**한다.
- 연속 실패·차단으로 중단되면 기록하고 종료 → 다음 ①판매수집 완료 후 이어서. 파일 생성 대기·서버 일시 오류만
  남았으면 몇 바퀴 더 보고(MAX_IDLE_PASSES) 그래도 남으면 '미완료'로 종료(무한 재로그인 방지).
- 같은 ①완료 기준으로 이미 '완료'면 다시 돌지 않는다(`_완료.json`·재부팅 복구·수동 재시작 중복 방지).

신호: `_진행중.json` 수정 시각(`sales_in_progress`)=①이 '지금' 도는지(그동안 정지) · `_실행단계.json`(`read_marker`)=
①이 '언제' 끝났는지(완료 기록의 기준 키).
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, time as dtime, timedelta
from pathlib import Path

SALES_DONE = ("sales", "ranks", "done")
SALES_STALE_MIN = 20   # _진행중.json 이 이보다 최근에 갱신됐으면 ①판매수집이 '지금 돌고 있다'고 본다
MAX_IDLE_PASSES = 3    # 새로 받은 게 없는데 생성 대기·일시 오류만 남은 바퀴를 이만큼까지(그 뒤 '미완료' 종료)
RESULT = {"done": "완료", "stop": "중단", "giveup": "미완료"}
CYCLE_START = dtime(18, 0)              # 회차 시작 = 앱·정산 동시 기동(18:00 무인)
CYCLE_END_GAP = timedelta(minutes=5)    # 다음 회차 5분 전(17:55)에 정산 종료


def cycle_window(now: datetime) -> tuple[datetime, datetime]:
    """now 가 속한 회차 (시작=가장 최근 18:00, 끝=그다음 날 17:55)."""
    start = datetime.combine(now.date(), CYCLE_START)
    if now < start:
        start -= timedelta(days=1)
    return start, start + timedelta(days=1) - CYCLE_END_GAP


def sales_done_in_cycle(marker: dict | None, cycle_start: datetime) -> bool:
    """이번 회차(cycle_start 이후)에 ①판매수집이 끝났나 — 앱 단계 기록(stage·at)으로 판정."""
    return bool(marker) and marker.get("stage") in SALES_DONE and marker["at"] >= cycle_start


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


def sales_key(marker: dict | None, now: datetime) -> str:
    """완료 기록 기준 키 = ①판매수집 완료 시각(앱이 띄운 경우). ① 기록이 없으면(수동 시작) 오늘 날짜."""
    if marker and marker.get("stage") in SALES_DONE:
        return marker["at"].isoformat(timespec="seconds")
    return f"수동:{now.date().isoformat()}"


def already_done(done: dict | None, key: str) -> bool:
    return bool(done) and done.get("key") == key and done.get("result") == RESULT["done"]


def read_done(path) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None                     # 손상 = 기록 없음(한 바퀴 더 돌 뿐 — 안전한 쪽)


def write_done(path, key: str, action: str, reason: str, now: datetime | None = None) -> None:
    """완료/중단/미완료 기록(원자적 쓰기)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {"key": key, "result": RESULT[action], "reason": reason,
           "at": (now or datetime.now()).isoformat(timespec="seconds")}
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def plan_after_pass(stopped: bool, work: int, pending: int, waits: int, idle_passes: int) -> tuple[str, str]:
    """한 바퀴 뒤 다음 행동(순수). stopped=연속 실패/차단 중단 · work=이번에 새로 요청/받은 수 ·
    pending=요청예정/요청됨(파일 생성 대기) 작업 수 · waits=일시 오류·브라우저 닫힘으로 '대기'된 계정 수 ·
    idle_passes=새로 한 일 없이 끝난 연속 바퀴 수.
      → 'again'(곧 다음 바퀴) · 'later'(5분 뒤 다음 바퀴) · 'done'(다 받음·종료) · 'stop'(중단·종료) · 'giveup'(미완료·종료)"""
    if stopped:   # D-031: 종료하지 않고 이번 바퀴만 멈춤 → 잠시 뒤 같은 사무실 IP 로 다음 바퀴(프록시 안 씀·🔒 로그인 정책)
        return "later", "연속 실패/차단 — 이번 바퀴만 멈춤, 잠시 뒤 다음 바퀴에 다시 시도"
    if work > 0:
        return "again", f"{work}건 처리 — 곧 다음 바퀴(아직 받을 것 확인)"
    if pending or waits:
        left = f"파일 생성 대기 {pending}건·일시 오류 대기 {waits}계정"
        if idle_passes >= MAX_IDLE_PASSES:
            return "giveup", f"{left} 남음({idle_passes}바퀴 진전 없음) — 다음 ①판매수집 완료 후 이어서"
        return "later", f"{left} — 잠시 뒤 다시 확인"
    return "done", "✅ 모든 정산 파일 다운로드 완료 — 정상 종료"


def sales_in_progress(progress_path, *, now: datetime | None = None,
                      stale_min: int = SALES_STALE_MIN) -> tuple[bool, str]:
    """①판매수집이 지금 돌고 있는지 — 앱이 ①판매수집 동안 계정마다 갱신하는 `_진행중.json` 의 수정 시각으로 판정.
    (존재 + 최근 stale_min 분 내 갱신)=진행 중 → 정산 일시정지. ①끝나면 파일이 지워지거나(완료) 갱신이
    멈춰(미완료 남김) 곧 '진행 중 아님'이 된다. 계정별 `_profile_busy` 건너뜀이 추가 안전장치다."""
    p = Path(progress_path)
    if not p.exists():
        return False, ""
    now = now or datetime.now()
    age_min = (now - datetime.fromtimestamp(p.stat().st_mtime)).total_seconds() / 60
    if age_min <= stale_min:
        return True, f"①판매수집 진행 중(진행 파일 {max(0, int(age_min))}분 전 갱신) — 정산 일시정지"
    return False, ""
