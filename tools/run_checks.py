"""회귀 게이트 — 오프라인 검증(아래 CHECKS 목록 전부)을 동시에(기본 3개) 실행하고 하나라도 실패하면 exit 1.

용도: 커밋/푸시 전(git 훅) 또는 수동으로 회귀를 잡는다. 모두 **로그인·실 API 없이** 결정적으로 돈다
(verify_offline [6]도 기본은 결정적 모킹 — 실 API는 VERIFY_REAL_API=1 옵트인).

    python tools/run_checks.py           # 전체 (pre-push)
    python tools/run_checks.py --quick   # 빠른 (pre-commit, CHECKS 의 quick=False 항목[verify_offline] 제외)
    python tools/run_checks.py -j 1      # 한 번에 하나씩(예전 방식). 기본은 동시 3개(D-180)
    python tools/run_checks.py --quick --skip-if-passed        # pre-commit: 같은 내용이 이미 통과했으면 건너뜀
    python tools/run_checks.py --skip-if-passed=push < refs    # pre-push: 올라갈 커밋 내용이 이미 전체 통과했으면 건너뜀

통과하면 그때 작업 폴더 내용의 키를 기록한다(check_stamp.py). 건너뛰기는 내용이 한 글자라도 다르면 일어나지 않는다.

개수는 적지 않는다(검증이 늘 때마다 문구가 어긋났음 — E7). 실행 끝 요약에 'N종'이 나온다.

각 스크립트는 실패 시 non-zero로 끝난다(assert/SystemExit). 여기선 하나가 죽어도 나머지를 계속
돌려 **전체 결과를 한 번에** 보여주고, 실패가 하나라도 있으면 최종 exit 1.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_stamp  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

# (표시명, 스크립트, quick 포함 여부) — quick=커밋 전 빠른 것만
CHECKS = [
    ("시뮬레이션(파이프라인 운영 조합 시나리오)", "tools/simulate_pipeline.py", True),
    ("핀(로그인·발견·반자동순위 실제코드)", "tools/pin_login_ranks.py", True),
    ("핀(apply_style 서식 출력)", "tools/pin_apply_style.py", True),
    ("핀(실행모드 결정 plan_run_mode)", "tools/pin_run_plan.py", True),
    ("핀(L1 데이터 백본 공개 API 계약)", "tools/pin_l1_contract.py", True),
    ("구글시트 오프라인 검증", "tools/verify_gsheet_offline.py", True),
    ("정밀 렌더 검증(시트·항목·값 end-to-end)", "tools/verify_render_precision.py", True),
    ("셀독계정상품이력관리원장(대장→원장·이력·복원)", "tools/verify_registry_offline.py", True),
    ("소싱 후보(발굴·검색량·경쟁·점수 랭킹)", "tools/verify_sourcing_offline.py", True),
    ("정산 계산(지급일·금액·파싱 골든)", "tools/verify_settlement_offline.py", True),
    ("정산 런타임(다운로드·감시·검증 시트·지급일 대조)", "tools/verify_settlement_runtime_offline.py", True),
    ("판매분석 금액 날짜별 누적", "tools/verify_sales_history_offline.py", True),
    ("통합 판매현황(첫 시트·월·주 조회)", "tools/verify_sales_summary_offline.py", True),
    ("쿠폰 목록·재고현황 날짜별 보관", "tools/verify_coupon_snapshot_offline.py", True),
    ("셀독전환자 로그인 확인(파일·비번 후보·멈춤·연락 필요 목록)", "tools/verify_transfer_offline.py", True),
    ("셀독전환자 정산 자료 받기(매일 18시 뒤·대상·기다림·원장 파일 재사용·누적 파일)", "tools/verify_transfer_settle_offline.py", True),
    ("샵마인 비번↔관리대장 동기화(DPAPI·필드탐색·대조·되쓰기·비번 비노출)", "tools/verify_shopmine_sync_offline.py", True),
    ("계정 정지 감지→대장 취소선(판정·열·상태파일·백업먼저·가역)", "tools/verify_account_suspend_offline.py", True),
    ("회귀 게이트 자체(동시 실행·통과 기록)", "tools/verify_run_checks_offline.py", True),
    ("오프라인 실증(워크북·매칭·키워드선정)", "tools/verify_offline.py", False),
]

DEFAULT_JOBS = 3   # 실측(2026-11-08, 22코어 PC): 3개 동시 = 16종 94~149초 · 하나씩 = 약 209초

# 자식 콘솔창 억제(무인/pythonw 실행 시 검은 창 깜빡임 방지, Windows 전용)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(name: str, script: str, root: Path | None = None) -> tuple[bool, float, str]:
    started = time.monotonic()
    proc = subprocess.run(
        [sys.executable, script],
        cwd=str(root or ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=_NO_WINDOW,
    )
    dur = time.monotonic() - started
    return proc.returncode == 0, dur, (proc.stdout or "") + (proc.stderr or "")


def _report(name: str, ok: bool, dur: float, out: str) -> None:
    print(f"▶ {name} …  {'✅ 통과' if ok else '❌ 실패'}  ({dur:.1f}s)", flush=True)
    if not ok:                           # 실패 시 원인 파악용으로 마지막 출력만 표시
        print("  ── 실패 출력(마지막 20줄) " + "─" * 30)
        for line in out.rstrip().splitlines()[-20:]:
            print("  │ " + line)
        print("  " + "─" * 52)


def run_all(checks: list, jobs: int, root: Path | None = None) -> list[tuple[str, bool, float, str]]:
    """checks 를 jobs 개씩 동시에 실행. 목록 앞(가장 오래 걸리는 시뮬레이션)부터 시작, 결과는 CHECKS 순서."""
    results: list = [None] * len(checks)
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        futs = {ex.submit(_run, name, script, root): i for i, (name, script, _) in enumerate(checks)}
        for f in as_completed(futs):
            i = futs[f]
            ok, dur, out = f.result()
            _report(checks[i][0], ok, dur, out)
            results[i] = (checks[i][0], ok, dur, out)
    return results


def _already_passed(root: Path, mode: str | None, quick: bool) -> bool:
    if mode == "push":                   # 올라갈 커밋마다 그 내용이 전체 통과한 적 있나
        revs = check_stamp.pushed_revs(sys.stdin.read().splitlines())
        return bool(revs) and all(check_stamp.passed(root, check_stamp.commit_key(root, r), False) for r in revs)
    if mode == "worktree":
        return check_stamp.passed(root, check_stamp.worktree_key(root), quick)
    return False


def _args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="회귀 게이트")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("-j", "--jobs", type=int, default=DEFAULT_JOBS)
    ap.add_argument("--skip-if-passed", nargs="?", const="worktree", choices=["worktree", "push"], default=None)
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    a = _args(argv)
    root = ROOT
    checks = [c for c in CHECKS if not a.quick or c[2]]
    label = "빠른 검증(--quick)" if a.quick else "전체 검증"
    if a.skip_if_passed and _already_passed(root, a.skip_if_passed, a.quick):
        print(f"  ⏭ {label} 건너뜀 — 같은 내용이 이미 통과함(통과 기록: check_stamp · D-180)")
        return 0
    key = check_stamp.worktree_key(root)
    print("=" * 64)
    print(f"  회귀 게이트 — {label} ({len(checks)}종 · 동시 {max(1, a.jobs)}개)")
    print("=" * 64)
    started = time.monotonic()
    results = run_all(checks, a.jobs, root)
    wall = time.monotonic() - started
    total = sum(d for _, _, d, _ in results)
    failed = [n for n, ok, _, _ in results if not ok]
    print("=" * 64)
    if failed:
        print(f"  ❌ 실패 {len(failed)}종: {', '.join(failed)}  (걸린 시간 {wall:.1f}s · 검사 합계 {total:.1f}s)")
        print("=" * 64)
        return 1
    print(f"  ✅ 전부 통과 ({len(results)}종, 걸린 시간 {wall:.1f}s · 검사 합계 {total:.1f}s)")
    print("=" * 64)
    if key and key == check_stamp.worktree_key(root):   # 검사 도중 내용이 바뀌었으면 기록 안 함
        check_stamp.record(root, key, a.quick)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
