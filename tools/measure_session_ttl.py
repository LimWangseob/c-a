"""세션 TTL 비간섭 측정(cohort) — SSO 세션이 방치 시 얼마나 사는지 실측(추측 제거).

**왜 cohort인가:** `authenticated()`를 몇 시간마다 반복 호출하면 그 접속 자체가 SSO Idle 을
갱신해 TTL 이 실제보다 길게 측정될 수 있다. 그래서 **각 계정을 목표 경과시간에 딱 1번만** 찌른다.
예) A=4h·B=8h·C=12h·D=24h·E=48h 로 등록하면
    4h VALID / 8h VALID / 12h VALID / 24h EXPIRED → Idle 경계가 12~24h 사이로 추정.
그다음 16h·20h 로 범위를 좁힌다.

**keep-warm 유효성도 같이 측정:** 프로브가 WING 접속 시 **xauth/sso 로 리다이렉트했는지**를 기록한다.
VALID인데 리다이렉트가 있으면 그 접속이 Keycloak 을 쳐서 Idle 을 갱신할 여지가 있다(=WING GET
keep-warm 유효 가능). 리다이렉트 없이 VALID면 WING 이 로컬 응답 → 단순 GET 은 Idle 갱신 못할 수 있음.

**로그인 0회·안전:** 만료된 계정은 로그인 폼이 떠도 **시도하지 않고** EXPIRED 로만 기록한다.
지문위조·자동제출 없음. 값(쿠키·토큰)은 저장하지 않는다.

절차(사무실, 2차인증 위치기반):
1) 코호트 계정들을 **각각 방금 로그인**시킨다(앱/직접). 로그인 직후:
   python tools/measure_session_ttl.py --enroll 계정A:4 계정B:8 계정C:12 계정D:24 계정E:48
   (Remember Me A/B 비교 시: 계정A:12:on 계정F:12:off 처럼 arm 태깅)
2) 이후 아무 때나(자동 스케줄러/수동) 도래분만 1회 프로브:
   python tools/measure_session_ttl.py --probe
3) 현황:
   python tools/measure_session_ttl.py --status
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from coupang_analytics import config, session_state  # noqa: E402

_PLAN_PATH = Path("data/ttl_cohort.json")
_FMT = "%Y-%m-%d %H:%M:%S"


# ── 순수 로직(브라우저 없이 테스트 가능) ──────────────────────────
def parse_spec(spec: str) -> dict:
    """'계정:시간[:arm]' → {account_id, target_hours, arm}. arm 기본 '-'."""
    parts = spec.split(":")
    if len(parts) < 2:
        raise ValueError(f"형식 오류(계정:시간[:arm]): {spec}")
    aid, hours = parts[0], float(parts[1])
    arm = parts[2] if len(parts) > 2 else "-"
    return {"account_id": aid, "target_hours": hours, "arm": arm}


def load_plan(path: Path = _PLAN_PATH) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_plan(plan: dict, path: Path = _PLAN_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")


def enroll(specs: list[str], plan: dict, now: datetime) -> dict:
    """코호트 등록 — baseline_at=now(방금 로그인 전제). 기존 항목은 덮어씀(재시작)."""
    for spec in specs:
        e = parse_spec(spec)
        plan[e["account_id"]] = {
            "baseline_at": now.strftime(_FMT),
            "target_hours": e["target_hours"],
            "arm": e["arm"],
            "probed_at": None,
            "result": None,
            "redirect": None,
        }
    return plan


def _elapsed_hours(entry: dict, now: datetime) -> float:
    base = datetime.strptime(entry["baseline_at"], _FMT)
    return (now - base).total_seconds() / 3600.0


def due_accounts(plan: dict, now: datetime) -> list[str]:
    """목표 경과시간 도래 + 아직 미프로브인 계정(딱 1회 원칙)."""
    return [aid for aid, e in plan.items()
            if e.get("probed_at") is None and _elapsed_hours(e, now) >= e["target_hours"]]


def status_rows(plan: dict, now: datetime) -> list[dict]:
    rows = []
    for aid, e in sorted(plan.items(), key=lambda kv: kv[1]["target_hours"]):
        el = _elapsed_hours(e, now)
        if e.get("probed_at"):
            phase = f"완료:{e['result']}" + (" (redirect)" if e.get("redirect") else "")
        elif e.get("touch_result") == "EXPIRED":
            phase = "⚠ 터치시 이미 EXPIRED — 재로그인 후 --touch 필요(측정 불가)"
        elif el >= e["target_hours"]:
            phase = "프로브 대기(도래)"
        else:
            base = "측정중" if e.get("touch_result") == "VALID" else "측정중(⚠ --touch 권장: baseline 부정확)"
            phase = f"{base} {el:.1f}/{e['target_hours']:.0f}h"
        rows.append({"account_id": aid, "arm": e["arm"], "target_h": e["target_hours"],
                     "elapsed_h": round(el, 1), "phase": phase})
    return rows


# ── 라이브 프로브(브라우저 1개, 로그인 0회) — 패키지의 touch_session 재사용 ──
def _probe_one(account_id: str) -> tuple[bool, bool, str]:
    """계정 프로필을 열어 WING 접속 후 (valid, redirected, final_url). 로그인 시도 없음."""
    from coupang_analytics.session_keepalive import touch_session
    return touch_session(account_id)


def touch_pending(plan: dict, now: datetime, log=print) -> dict:
    """미프로브 계정을 지금 1회 터치(안전 GET, 로그인 0회) → baseline=진짜 활동시점=now 로 재설정.

    Idle TTL 은 '마지막 활동 이후 경과'로 죽으므로, enroll(파일쓰기)만으론 baseline 이 부정확하다.
    이 명령으로 실제 세션을 한 번 건드려 t=0 을 확정한다. 터치 시 EXPIRED 면 그 계정은 이미 죽어
    측정 불가 → 재로그인 후 다시 --touch 해야 한다.
    """
    pending = [aid for aid, e in plan.items() if e.get("probed_at") is None]
    if not pending:
        log("터치할 대기 계정 없음(모두 프로브 완료).")
        return plan
    for aid in pending:
        entry = plan[aid]
        try:
            valid, redirected, final = _probe_one(aid)
        except Exception as exc:
            log(f"  [{aid}] 터치 실패({exc.__class__.__name__}: {str(exc)[:80]}) — 다시 --touch")
            continue
        entry["baseline_at"] = now.strftime(_FMT)   # 진짜 활동시점으로 재설정
        entry["touch_result"] = "VALID" if valid else "EXPIRED"
        entry["touch_redirect"] = redirected
        session_state.record_event(aid, "ttl_touch",
                                   failure_type=None if valid else session_state.FAIL_SESSION_EXPIRED,
                                   final_url=final, auth_redirect=redirected)
        if valid:
            log(f"  [{aid}] 터치 OK(VALID) — baseline=now, {entry['target_hours']:.0f}h 뒤 프로브")
        else:
            log(f"  [{aid}] ⚠ 터치시 EXPIRED — 재로그인 후 --touch 필요(현재 측정 불가)")
    save_plan(plan)
    return plan


def probe_due(plan: dict, now: datetime, log=print) -> dict:
    due = due_accounts(plan, now)
    if not due:
        log("도래한 프로브 없음(측정중이거나 이미 완료).")
        return plan
    for aid in due:
        entry = plan[aid]
        try:
            valid, redirected, final = _probe_one(aid)
        except Exception as exc:   # 프로브 실패는 사유만 남기고 다음(무음 아님)
            log(f"  [{aid}] 프로브 실패({exc.__class__.__name__}: {str(exc)[:80]}) — 다음 --probe 때 재시도")
            continue
        entry["probed_at"] = now.strftime(_FMT)
        entry["result"] = "VALID" if valid else "EXPIRED"
        entry["redirect"] = redirected
        elapsed_ms = int(_elapsed_hours(entry, now) * 3600 * 1000)
        session_state.record_event(
            aid, "ttl_probe",
            failure_type=None if valid else session_state.FAIL_SESSION_EXPIRED,
            final_url=final, auth_redirect=redirected, elapsed_ms=elapsed_ms)
        hint = " (redirect=Keycloak 접촉→keep-warm 유효 여지)" if (valid and redirected) else \
               (" (redirect 없음→단순 GET은 Idle 갱신 못할 수 있음)" if valid else "")
        log(f"  [{aid}] {entry['target_hours']:.0f}h 경과 → {entry['result']}{hint}")
    save_plan(plan)
    return plan


def _print_status(plan: dict, now: datetime) -> None:
    rows = status_rows(plan, now)
    if not rows:
        print("(등록된 코호트 없음 — --enroll 로 시작)")
        return
    print(f"{'계정':<18}{'arm':<6}{'목표h':>6}{'경과h':>8}  단계")
    print("-" * 70)
    for r in rows:
        print(f"{r['account_id']:<18}{r['arm']:<6}{r['target_h']:>6.0f}{r['elapsed_h']:>8.1f}  {r['phase']}")
    print(f"\nDB: {config.SESSION_STATE_DB} · 계획: {_PLAN_PATH}")


if __name__ == "__main__":
    args = sys.argv[1:]
    now = datetime.now()
    plan = load_plan()
    if args and args[0] == "--enroll":
        plan = enroll(args[1:], plan, now)
        save_plan(plan)
        print(f"[등록] {len(args[1:])}계정 코호트 시작. ⚠ baseline 정확도를 위해 지금 "
              "`--touch` 를 실행해 실제 활동시점으로 맞추세요.")
        _print_status(plan, now)
    elif args and args[0] == "--touch":
        touch_pending(plan, now)
        _print_status(plan, now)
    elif args and args[0] == "--probe":
        probe_due(plan, now)
        _print_status(plan, now)
    elif args and args[0] == "--status":
        _print_status(plan, now)
    elif args and args[0] == "--reset":
        if _PLAN_PATH.exists():
            _PLAN_PATH.unlink()
        print("[초기화] 코호트 계획 삭제됨(관측 이벤트 로그는 보존). --enroll 로 다시 시작.")
    else:
        print(__doc__)
