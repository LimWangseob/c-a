"""정산 다운로드 자동 대기·재개 판단(순수 로직·오프라인 검증) — 운용 PC에서 기존 앱과 번갈아 돌기.

소유자 결정(2026-10-07): 정산은 **24시간 감시**하되 **①판매수집이 돌고 있을 때만 일시정지**하고, 끝나면 재개한다.
- **소급(초기)**: 2026-01 ~ 오늘치 밀린 정산을 다 받아야 하므로, 받을 게 있는 동안은 **연속**으로 바퀴를 돈다.
- **정상(소급 후)**: 받을 게 없어지면 **다음 ①판매수집 완료마다 1회**만 돈다(매번 전 계정 재로그인하지 않음 = 계정 보호).
- ⛔ 로그인을 쓰는 건 ①판매수집뿐이라 ②키워드·③순위(로그인 없음·별도 프로필)와는 겹쳐도 된다.

신호 둘:
- `_진행중.json` 수정 시각(`sales_in_progress`) = ①판매수집이 '지금' 도는지(일시정지 판단).
- `_실행단계.json`(`read_marker`: stage sales=①완료·at=시각) = ①판매수집이 '언제' 끝났는지(정상 1회 트리거).
실제 '소급 연속 vs 하루 1회'는 호출부가 한 바퀴 처리 건수로 정한다(받은 게 있으면 바로 다음 바퀴).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

SALES_DONE = ("sales", "ranks", "done")
SALES_STALE_MIN = 20   # _진행중.json 이 이보다 최근에 갱신됐으면 ①판매수집이 '지금 돌고 있다'고 본다


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


def plan_watch(busy: bool, busy_why: str, sales_at: datetime | None,
               last_sales_at: datetime | None) -> tuple[str, str]:
    """다음 행동(순수). busy=①판매수집 진행 중 · sales_at=현재 ①완료 기록 시각 ·
    last_sales_at=마지막으로 정산을 '받을 것 없음'까지 돌린 ①완료 시각(=소급 끝난 뒤 '하루 1회' 기준, 소급 중엔 None).
      → 'wait' : ①판매수집 중(busy)이거나, 소급 끝났고 새 ①완료가 아직 없음.
      → 'run'  : 지금 한 바퀴(소급 중=항상·정상 중=새 ①완료 있을 때)."""
    if busy:
        return "wait", busy_why
    if last_sales_at is not None and (sales_at is None or sales_at <= last_sales_at):
        return "wait", "받을 정산 없음 — 다음 ①판매수집 완료까지 대기"
    return "run", ("소급 수집(밀린 정산 받는 중)" if last_sales_at is None
                   else "새 ①판매수집 완료 — 정산 수집")


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
