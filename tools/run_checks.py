"""회귀 게이트 — 오프라인 검증(아래 CHECKS 목록 전부)을 동시에(기본 3개) 실행하고 하나라도 실패하면 exit 1.

용도: 커밋/푸시 전(git 훅) 또는 수동으로 회귀를 잡는다. 모두 **로그인·실 API 없이** 결정적으로 돈다
(verify_offline [6]도 기본은 결정적 모킹 — 실 API는 VERIFY_REAL_API=1 옵트인).

    python tools/run_checks.py           # 전체 (pre-push)
    python tools/run_checks.py --quick   # 빠른 (pre-commit, CHECKS 의 quick=False 항목[verify_offline] 제외)
    python tools/run_checks.py -j 1      # 한 번에 하나씩(예전 방식). 기본은 동시 3개(D-180)
    python tools/run_checks.py --quick --skip-if-passed        # pre-commit: 같은 내용이 이미 통과했으면 건너뜀
    python tools/run_checks.py --skip-if-passed=push < refs    # pre-push: 올라갈 커밋 내용이 이미 전체 통과했으면 건너뜀

통과하면 그때 작업 폴더 내용의 키를 기록한다(check_stamp.py). 건너뛰기는 내용이 한 글자라도 다르면 일어나지 않는다.

PC 전체에서 게이트는 한 번에 1개만 돈다(D-377 · 노트북 과부하 — 게이트 1개 ≈ 2.3GB). 다른 게이트(다른 작업 폴더·
세션·git 훅 포함)가 돌고 있으면 누가(PID)·언제부터·어느 폴더인지 보여 주고 끝날 때까지 기다린다. 건너뛰기 판정은
잠금을 얻은 **뒤에** 한다 — 앞 게이트가 같은 내용으로 통과 기록을 남겼으면 뒤 게이트(pre-push 등)는 돌지 않는다.
잠금 = OS 파일 잠금(LOCK_PATH · registry_lock.py 와 같은 방식) — 게이트가 죽으면 OS 가 풀어 남은 파일은 막지 않는다.
검사 프로세스는 낮은 우선순위(Windows BELOW_NORMAL)로 띄워 다른 작업을 덜 밀어낸다.
게이트마다 한 줄 시간 기록 = 잠금 파일 옆 `run_checks_times.csv`(잠금 기다린 초·걸린 초·검사별 초 · D-378 N).

개수는 적지 않는다(검증이 늘 때마다 문구가 어긋났음 — E7). 실행 끝 요약에 'N종'이 나온다.

각 스크립트는 실패 시 non-zero로 끝난다(assert/SystemExit). 여기선 하나가 죽어도 나머지를 계속
돌려 **전체 결과를 한 번에** 보여주고, 실패가 하나라도 있으면 최종 exit 1.
"""
from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import time
from contextlib import contextmanager
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
    ("시뮬레이션(파이프라인 운영 조합 시나리오)", "tools/simulate_pipeline.py", False),   # D-352: 커밋 때 빼고 푸시(전체)에서만
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
    ("정산서 배치 실행기(완료 뒤 띄우기·재시작·하루 1번·실패 계정·모듈 없음·잠금 D-399)", "tools/verify_statement_batch_offline.py", True),
    ("위탁정산서 계산 규칙(배분·장부·추가지급·입력 폴더)", "tools/verify_settlement_statements_offline.py", True),
    ("위탁정산서 정산 예정분 나누기(D-262·D-266 실제값·B8·B+환산·확인 필요)", "tools/verify_settlement_pending_offline.py", True),
    ("정산 받기 의심·자료 출처 대조(T-82·T-78 S1~S3)", "tools/verify_settlement_sources_offline.py", True),
    ("정산 자료 전날 값 보관(덮어쓰기 9곳 · T-123 D-335)", "tools/verify_settlement_keep_offline.py", True),
    ("정산 다시받을목록 자동 재받기(T-122 D-339)", "tools/verify_settlement_refetch_offline.py", True),
    ("정산 윙 화면 보기·응답 기록 틀(T-122 D-340 · 첫 시험 전 칸 이름만)", "tools/verify_settlement_screen_view_offline.py", True),
    ("정산 지급 전 예상 규칙값(비즈니스 인사이트 일할·신상품 무료 창 T-116)", "tools/verify_settlement_fee_rules_offline.py", True),
    ("정산 표본 전후 계산 도구(저장 자료·지문 다시 읽기·금액 칸 비교 S1 D-353)", "tools/verify_settlement_sample_offline.py", True),
    ("셀독 정산서(대상 계약·상품군·양식 1장·도달율)", "tools/verify_seldoc_statements_offline.py", True),
    ("위탁자 정산서 3차 형식(숫자 검산·시트 그리기·쪽·결정 문구·입구)", "tools/verify_consignor_statement_offline.py", True),
    ("판매분석 금액 날짜별 누적", "tools/verify_sales_history_offline.py", True),
    ("통합 판매현황(첫 시트·월·주 조회)", "tools/verify_sales_summary_offline.py", True),
    ("쿠폰 목록·재고현황 날짜별 보관", "tools/verify_coupon_snapshot_offline.py", True),
    ("상품 정보 날짜별 보관(categoryId·반품배송비·조회 함수 T-100)", "tools/verify_product_info_offline.py", True),
    ("셀독 계약자별 상품 현황(10건 규칙·판정 3단·양식·칸 폭·구글 교체·06:00 실행·빈 날 공란 T-132 D-358·D-361)", "tools/verify_contractor_sheet_offline.py", True),
    ("셀독전환자 로그인 확인(파일·비번 후보·멈춤·연락 필요 목록)", "tools/verify_transfer_offline.py", True),
    ("셀독전환자 정산 자료 받기(매일 00:10 무인 뒤·대상·기다림·원장 파일 재사용·누적 파일)", "tools/verify_transfer_settle_offline.py", True),
    ("샵마인 비번↔관리대장 동기화(DPAPI·필드탐색·대조·되쓰기·비번 비노출)", "tools/verify_shopmine_sync_offline.py", True),
    ("계정 정지 감지→대장 취소선(판정·열·상태파일·백업먼저·가역)", "tools/verify_account_suspend_offline.py", True),
    ("회귀 게이트 자체(동시 실행·통과 기록·PC 전체 1개·낮은 우선순위 D-377)", "tools/verify_run_checks_offline.py", True),
    ("옵션 분리 이력 = 같은 VID 블록만·미매칭 확인 필요·빈 칸 채움 VID 대조·키워드 0 로그·이력 바로잡기 도구(T-162)",
     "tools/verify_option_split_offline.py", True),
    ("앱 진행 로그창 탭별 표시(탭·작업·시작 줄·복사)", "tools/verify_ui_log_tabs_offline.py", True),
    ("켜 둔 앱 관리대장 다시 읽기(버튼 실행·06:00 계약자·실행 도중 안 읽음 D-366)", "tools/verify_ui_ledger_reread_offline.py", True),
    ("날짜 칸 = 판매일·옛 칸 하루 당기기(백업·스탬프·순위 묶음·두 번 방지 D-368·D-369)", "tools/verify_date_basis_offline.py", True),
    ("output 내보내기·합치기·보관 이동(변경분·실행 중 멈춤·UTF-8·비밀번호 뺌 D-243)", "tools/verify_output_export_offline.py", True),
    ("노출·방문자 아침 보충(어제 칸 두 줄만·정산 계정 잠금·3번·하루 한 번·날짜 지정 안 섞임 D-374)", "tools/verify_traffic_morning_offline.py", True),
    ("마스터 엑셀 저장 = 임시 파일 → 바꿔 끼우기(끊겨도 옛 마스터 · 엑셀 열림 PermissionError · 좀비 Chrome 경로 D-376)", "tools/verify_workbook_save_offline.py", True),
    ("노출·방문자 아침 보충 앱 연결(1분 타이머·다른 실행 중 기다림·무인 앱 08:00 보충 뒤 종료 D-374)", "tools/verify_ui_morning_offline.py", True),
    ("배포 업데이트(실행 중 앱·정산 멈춤 → 복사 · output·data·config 보존 · 멈추기 실패 = 복사 안 함)", "tools/verify_deploy_update_offline.py", True),
    ("오프라인 실증(워크북·매칭·키워드선정)", "tools/verify_offline.py", False),
]

DEFAULT_JOBS = 3   # 실측(2026-11-08, 22코어 PC): 3개 동시 = 16종 94~149초 · 하나씩 = 약 209초

# 자식 콘솔창 억제(무인/pythonw 실행 시 검은 창 깜빡임 방지) + 낮은 우선순위(D-377) — Windows 전용(다른 OS 는 0)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_LOW_PRIORITY = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)

# PC 전체 게이트 잠금(D-377) — 작업 폴더·세션과 상관없는 한 곳(credstore 와 같은 LOCALAPPDATA 기준)
LOCK_PATH = Path(os.environ.get("LOCALAPPDATA") or str(Path.home())) / "coupang-analytics" / "run_checks.lock"
_LOCK_BYTE = 1 << 20     # Windows 잠금은 그 바이트를 남이 못 읽게 함 → 쥔 게이트 정보(앞부분)와 떨어진 곳을 잠근다
_LOCK_POLL_SEC = 1.0

if sys.platform == "win32":
    import msvcrt

    def _try_lock(fd: int) -> bool:
        os.lseek(fd, _LOCK_BYTE, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    def _unlock(fd: int) -> None:
        os.lseek(fd, _LOCK_BYTE, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


def _holder(path: Path) -> str:
    """잠금을 쥔 게이트가 적어 둔 'PID · 시작 · 작업 폴더'(쥔 직후 잠깐은 비어 있을 수 있음)."""
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as e:
        return f"정보 못 읽음({e})"


def _write_holder(fd: int, text: str) -> None:
    os.ftruncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, text.encode("utf-8"))


def times_path() -> Path:
    """게이트 시간 기록(D-378 N) — 잠금 파일과 같은 PC 공용 폴더 · 작업 폴더·세션이 달라도 한 파일."""
    return LOCK_PATH.with_name("run_checks_times.csv")


_TIMES_HEAD = ["시작", "작업폴더", "종류", "결과", "잠금대기초", "걸린초", "검사합계초", "검사수", "검사별초"]


def _log_times(root: Path, quick: bool, outcome: str, waited: float, wall: float, results: list) -> None:
    """게이트 한 번 = 한 줄. 못 쓰면 경고만 출력(게이트 결과는 그대로 · 조용히 넘기지 않음)."""
    p = times_path()
    row = [time.strftime("%Y-%m-%d %H:%M:%S"), str(root), "빠른" if quick else "전체", outcome,
           f"{waited:.1f}", f"{wall:.1f}", f"{sum(r[2] for r in results):.1f}", str(len(results)),
           ";".join(f"{r[0]}={r[2]:.1f}" for r in results)]
    try:
        new = not p.exists()
        with p.open("a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(_TIMES_HEAD)
            w.writerow(row)
    except OSError as e:
        print(f"  ⚠ 게이트 시간 기록 못 함({p}: {e}) — 검사 결과는 그대로", flush=True)


@contextmanager
def _gate_lock(root: Path):
    """PC 전체 게이트 잠금 — 다른 게이트가 쥐고 있으면 끝날 때까지 기다림(시간 제한 없음 · 죽으면 OS 가 풂).
    기다린 초를 넘겨 줌(시간 기록용 · D-378 N)."""
    path = LOCK_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        started, shown = time.monotonic(), None
        while not _try_lock(fd):
            who = _holder(path) or "정보 아직 없음"
            if who != shown:
                print(f"  ⏳ 다른 회귀 게이트가 돌고 있어 끝날 때까지 기다립니다 — {who} (PC 전체 1개 · D-377 · {path})",
                      flush=True)
                shown = who
            time.sleep(_LOCK_POLL_SEC)
        if shown is not None:
            print(f"  ▶ 앞 게이트가 끝나 시작합니다({time.monotonic() - started:.0f}초 기다림)", flush=True)
        waited = time.monotonic() - started
        _write_holder(fd, f"PID {os.getpid()} · 시작 {time.strftime('%Y-%m-%d %H:%M:%S')} · 작업 폴더 {root}")
        try:
            yield waited
        finally:
            _write_holder(fd, "")
            _unlock(fd)
    finally:
        os.close(fd)


def _run(name: str, script: str, root: Path | None = None) -> tuple[bool, float, str]:
    started = time.monotonic()
    proc = subprocess.run(
        [sys.executable, script],
        cwd=str(root or ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=_NO_WINDOW | _LOW_PRIORITY,
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
    with _gate_lock(root) as waited:     # 건너뛰기 판정도 잠금 안에서 — 앞 게이트의 통과 기록을 보고 판정(D-377)
        return _gate(a, root, waited)


def _gate(a: argparse.Namespace, root: Path, waited: float = 0.0) -> int:
    checks = [c for c in CHECKS if not a.quick or c[2]]
    label = "빠른 검증(--quick)" if a.quick else "전체 검증"
    if a.skip_if_passed and _already_passed(root, a.skip_if_passed, a.quick):
        print(f"  ⏭ {label} 건너뜀 — 같은 내용이 이미 통과함(통과 기록: check_stamp · D-180)")
        _log_times(root, a.quick, "건너뜀", waited, 0.0, [])
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
    _log_times(root, a.quick, "실패" if failed else "통과", waited, wall, results)
    print("=" * 64)
    if failed:
        print(f"  ❌ 실패 {len(failed)}종: {', '.join(failed)}  (걸린 시간 {wall:.1f}s · 검사 합계 {total:.1f}s)")
        print("=" * 64)
        return 1
    print(f"  ✅ 전부 통과 ({len(results)}종, 걸린 시간 {wall:.1f}s · 검사 합계 {total:.1f}s)")
    print("=" * 64)
    if key and key == check_stamp.worktree_key(root):   # 검사 도중 내용이 바뀌었으면 기록 안 함
        check_stamp.record(root, key, a.quick)
    _warn_untracked(root)
    return 0


def _warn_untracked(root: Path) -> None:
    """git 에 안 올린 파일이 있으면 이 통과 기록은 푸시 때 못 씀(커밋 내용과 키가 다름) → 이름을 보여 줌(D-379)."""
    try:
        files = check_stamp.untracked(root)
    except (subprocess.CalledProcessError, OSError) as e:
        print(f"  ⚠ git 에 안 올린 파일 확인 못 함({e})", flush=True)
        return
    if files:
        shown = ", ".join(files[:5]) + (f" 외 {len(files) - 5}개" if len(files) > 5 else "")
        print(f"  ⚠ git 에 안 올린 파일 {len(files)}개({shown}) — 푸시 때 이 통과 기록을 못 써 전체 검사를 다시 돕니다"
              " · 필요 없는 파일이면 .gitignore 에 넣거나 커밋하세요(D-379)", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
