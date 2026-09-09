r"""상시 세션 keep-warm — 앱과 무관하게 로그인된 세션을 살려둔다(재로그인·차단 근본 축소).

차단 근본원인 = 세션이 방치로 죽어 매번 재로그인 → 로그인 POST가 Akamai에 걸림. 이 스크립트를
Windows 작업 스케줄러로 주기 실행하면(앱을 안 열어둬도) 세션이 계속 살아 재로그인 자체가 줄어든다.
안전 GET 만 하며 로그인 시도·지문위조 없음(만료 계정은 폼만 뜨고 건너뜀). 관측층에 결과가 기록된다.

**안전장치(단계적 배포 전제):**
- 대상 = 입력 대장(운영계정) ∩ `data/profiles/`(세션 보유). 대장에 없는 **고아/테스트 프로필은 제외**.
  대장 경로는 UI가 마지막으로 연 것(`data/last_input_path.txt`) 또는 `--input` 로 지정.
- TTL 측정 중 코호트(`data/ttl_cohort.json` 미프로브)는 **자동 제외**(데우면 측정 오염).
- `--limit N` : **소수 계정부터 단계적 활성화**(예: 처음엔 5개만 데우고 대조·확대). 기본은 전체.
- **single-instance lock**(`data/keepwarm.lock`): 이전 실행이 안 끝났으면 이번 실행은 그냥 종료(중복 요청 방지).
- 주기는 **임시 실험값**(config.SESSION_KEEPALIVE_MIN, 기본 25분). 실제 TTL 확인 전엔 확정값 아님.

사용:
    python tools/keepwarm.py --status              # 계정별 포함/제외 사유 + 합계(브라우저 안 엶)
    python tools/keepwarm.py --once [--limit N]    # 1회 패스(작업 스케줄러용)
    python tools/keepwarm.py --loop [분] [--limit N]  # 포그라운드 연속
옵션: --input <대장.xlsx>(대장 경로 override)

작업 스케줄러 등록 예(25분마다, 처음엔 5개만 — 단계적):
    schtasks /Create /TN coupang-keepwarm /SC MINUTE /MO 25 /F ^
      /TR "cmd /c cd /d D:\coupang-analytics && python tools\keepwarm.py --once --limit 5 >> output\keepwarm.log 2>&1"
    (해제: schtasks /Delete /TN coupang-keepwarm /F)
"""
from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

try:   # 작업 스케줄러가 로그로 리다이렉트하면 stdout 이 cp949 → 한글/기호 출력 시 크래시 방지
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from coupang_analytics import config, session_state  # noqa: E402
from coupang_analytics.input_list import last_input_path, parse_input_list  # noqa: E402
from coupang_analytics.session_keepalive import keepwarm_once  # noqa: E402

_PROFILES_DIR = Path("data/profiles")
_COHORT_PATH = Path("data/ttl_cohort.json")
_LOCK_PATH = Path("data/keepwarm.lock")


# ── 계정 인벤토리(대장 대조로 고아/테스트 제외) ────────────────────
def profile_accounts() -> list[str]:
    """로그인 프로필이 있는 계정. '_' 로 시작하는 내부·테스트 프로필(_repro_* 등)은 제외."""
    if not _PROFILES_DIR.exists():
        return []
    return sorted(d.name for d in _PROFILES_DIR.iterdir()
                  if d.is_dir() and not d.name.startswith("_"))


def ledger_accounts(input_path: str | None) -> tuple[set[str], str | None]:
    """입력 대장(운영계정) 계정ID 집합과 사용한 경로. 경로 없으면 (빈셋, None)."""
    path = input_path or last_input_path()
    if not path:
        return set(), None
    try:
        il = parse_input_list(path)
    except Exception as exc:
        print(f"[keepwarm] 대장 파싱 실패({exc.__class__.__name__}) — --input 확인 필요")
        return set(), path
    return {a.account_id for a in il.accounts}, path


def cohort_exclude() -> set[str]:
    """TTL 측정 중(미프로브) 코호트 계정 — keep-warm 제외(측정 오염 방지)."""
    if not _COHORT_PATH.exists():
        return set()
    try:
        plan = json.loads(_COHORT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {aid for aid, e in plan.items() if e.get("probed_at") is None}


def classify(input_path: str | None) -> dict:
    """명부 변경(신규·중지·해지)까지 반영해 분류. keep-warm 대상 = 대장∩프로필 − 코호트 − 죽은계정.

    - production        : 대장에 있고 프로필 보유(= keep-warm 후보)
    - orphan            : 프로필은 있으나 대장에 없음(관리 해지 → 자동 제외, 정리 후보)
    - needs_first_login : 대장에 있으나 프로필 없음(신규 등록 → 사무실 첫 로그인 필요)
    - blocked           : 중지/잠금/휴면/DISABLED 로 관측된 계정(keep-warm 두드리기 낭비 → 제외)
    - warm              : 실제 keep-warm 대상
    """
    profiles = profile_accounts()
    ledger, used_path = ledger_accounts(input_path)
    cohort = cohort_exclude()
    blocked_st = session_state.accounts_in_states(
        (session_state.STATE_ACCOUNT_BLOCKED, session_state.STATE_DISABLED))
    # 만료(로그인 필요) 세션은 GET 으로 못 살리므로 keep-warm 제외(무의미 auth 접촉 방지 = self-prune)
    reauth_st = session_state.accounts_in_states((session_state.STATE_REAUTH_REQUIRED,))
    production = [a for a in profiles if a in ledger] if ledger else []
    orphan = [a for a in profiles if a not in ledger] if ledger else list(profiles)
    needs_first_login = sorted(ledger - set(profiles)) if ledger else []
    blocked = [a for a in production if a in blocked_st]
    needs_login = [a for a in production if a in reauth_st and a not in blocked_st]
    warm = [a for a in production
            if a not in cohort and a not in blocked_st and a not in reauth_st]
    return {"profiles": profiles, "ledger_known": bool(ledger), "ledger_path": used_path,
            "production": production, "orphan": orphan, "needs_first_login": needs_first_login,
            "blocked": blocked, "needs_login": needs_login, "cohort": sorted(cohort), "warm": warm}


# ── 중복 실행 방지(single-instance lock) ──────────────────────────
@contextmanager
def _single_instance(max_age_sec: int = 1800):
    """이전 실행이 안 끝났으면(신선한 lock 존재) 이번 실행은 건너뜀. 오래된 lock 은 탈취."""
    _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _LOCK_PATH.exists():
        try:
            age = time.time() - _LOCK_PATH.stat().st_mtime
        except OSError:
            age = max_age_sec + 1
        if age < max_age_sec:
            print(f"[keepwarm] 이전 실행이 진행 중(lock {int(age)}s) — 이번 주기 건너뜀(중복 방지)")
            yield False
            return
        try:                       # 오래된 lock = 죽은 프로세스 잔재 → 탈취
            _LOCK_PATH.unlink()
        except OSError:
            pass
    try:
        fd = os.open(str(_LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:        # 경쟁 — 다른 인스턴스가 방금 잡음
        print("[keepwarm] 다른 인스턴스가 방금 시작 — 이번 주기 건너뜀")
        yield False
        return
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    try:
        yield True
    finally:
        try:
            _LOCK_PATH.unlink()
        except OSError:
            pass


# ── 실행 ──────────────────────────────────────────────────────────
def _once(input_path: str | None, limit: int | None, log=print) -> None:
    info = classify(input_path)
    if not info["ledger_known"]:
        log("[keepwarm] ⚠ 입력 대장 경로를 모름 — 운영계정 판별 불가. 앱에서 대장을 1회 열거나 "
            "--input <대장.xlsx> 로 지정하세요. (안전상 keep-warm 중단)")
        return
    targets = info["warm"]
    if limit is not None:
        targets = targets[:limit]
    if not targets:
        log(f"[keepwarm] 대상 0개(운영 {len(info['production'])}·코호트제외 {len(info['cohort'])}"
            f"·limit {limit}). 건너뜀")
        return
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c = keepwarm_once(targets, on_log=log)
    session_state.record_keepwarm_run(started, c)
    log(f"[keepwarm] {started} — 대상 {c['attempted']} / 유지 {c['alive']} "
        f"(만료 {c['expired']}·IdP미접촉 {c['app_only']}·챌린지 {c['challenge']}·오류 {c['error']}). "
        f"DB={config.SESSION_STATE_DB}")
    if c["challenge"]:
        log("[keepwarm] ⚠ 챌린지 발생 — 확대 전 원인 확인(IP/빈도). 단계 확대 보류 권장")


def _status(input_path: str | None) -> None:
    info = classify(input_path)
    cohort, blocked = set(info["cohort"]), set(info["blocked"])
    needs_login = set(info["needs_login"])
    print(f"대장: {info['ledger_path'] or '(모름 — 앱에서 1회 열거나 --input 지정)'}")
    print("\n[PRODUCTION] (대장에 있고 프로필 보유)")
    for a in info["production"]:
        tag = ("EXCLUDED_TTL" if a in cohort else
               "SKIP_BLOCKED" if a in blocked else
               "NEEDS_LOGIN" if a in needs_login else "WARM")
        print(f"  {a:<20} {tag}")
    if info["needs_first_login"]:
        print("\n[NEEDS_FIRST_LOGIN] (신규 등록 — 사무실서 첫 로그인해야 keep-warm 편입)")
        for a in info["needs_first_login"]:
            print(f"  {a:<20} 프로필 없음")
    if info["orphan"]:
        print("\n[ORPHAN] (프로필은 있으나 대장에 없음 = 관리 해지, 정리 후보)")
        for a in info["orphan"]:
            print(f"  {a:<20} EXCLUDED_ORPHAN")
    print("\n합계")
    print(f"  TOTAL_PROFILES     = {len(info['profiles'])}")
    print(f"  PRODUCTION         = {len(info['production'])}")
    print(f"  NEEDS_FIRST_LOGIN  = {len(info['needs_first_login'])}")
    print(f"  NEEDS_LOGIN(만료)  = {len(info['needs_login'])}")
    print(f"  TTL_COHORT         = {len(info['cohort'])}")
    print(f"  SKIP_BLOCKED(중지) = {len(info['blocked'])}")
    print(f"  ORPHAN             = {len(info['orphan'])}")
    print(f"  KEEPWARM(실대상)   = {len(info['warm'])}")


def _arg(args: list[str], name: str) -> str | None:
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else None


if __name__ == "__main__":
    args = sys.argv[1:]
    inp = _arg(args, "--input")
    lim = int(_arg(args, "--limit")) if _arg(args, "--limit") else None
    if args and args[0] == "--status":
        _status(inp)
    elif args and args[0] == "--disable":
        if len(args) < 2:
            print("사용: --disable <계정ID> [계정ID ...] (중지 계정 표시 → keep-warm·수집 제외)")
        else:
            for aid in args[1:]:
                session_state.set_state(aid, session_state.STATE_DISABLED)
                print(f"[중지표시] {aid} → DISABLED (keep-warm·수집에서 제외)")
    elif args and args[0] == "--enable":
        if len(args) < 2:
            print("사용: --enable <계정ID> [계정ID ...] (중지 해제 → 다음 접속 때 재평가)")
        else:
            for aid in args[1:]:
                session_state.set_state(aid, session_state.STATE_REAUTH_REQUIRED)
                print(f"[중지해제] {aid} → 재평가 대기(다음 로그인/터치 때 상태 갱신)")
    elif args and args[0] == "--once":
        with _single_instance() as got:
            if got:
                _once(inp, lim)
    elif args and args[0] == "--loop":
        interval = int(args[1]) * 60 if len(args) > 1 and args[1].isdigit() else config.SESSION_KEEPALIVE_MIN * 60
        print(f"[keepwarm] 연속 모드 — {interval // 60}분 간격 (Ctrl+C 종료)")
        try:
            while True:
                with _single_instance() as got:
                    if got:
                        _once(inp, lim)
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n[keepwarm] 종료")
    else:
        print(__doc__)
