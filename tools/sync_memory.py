"""세션 메모리를 repo 안으로 미러링 — 커밋마다 자동 백업(세션·PC 바뀌어도 손실 방지).

배경(2026-09-25, 소유자): 확정사항은 코드+설계서(git)·결정기록(git)·**메모리** 3채널로 넘긴다. 앞의 둘은 git 이라
안전하지만 메모리는 `%USERPROFILE%\\.claude\\projects\\<slug>\\memory` 로 **repo 밖**이라 PC 교체·`.claude`
소실 시 유실된다. 이 도구가 **매 커밋 pre-commit 훅에서** 외부 메모리 폴더를 repo `docs/memory/` 로 미러링하고
스테이징해 git 에 함께 저장한다 → 새 세션/새 PC 는 클론만으로 메모리 스냅샷을 확보한다(SSOT 는 여전히 외부
`.claude` 실사용본, `docs/memory/` 는 그 백업 스냅샷).

경로 우선순위: env `COUPANG_MEMORY_DIR` > 기본(`%USERPROFILE%\\.claude\\projects\\<slug>\\memory`).
<slug> = repo 절대경로에서 `:`·`\\`·`/` → `-`(하네스 규칙, 예 `D:\\coupang-analytics` → `D--coupang-analytics`).
외부 메모리 폴더가 없으면(다른 PC·메모리 미사용) **조용히 no-op**(커밋을 막지 않는다·exit 0).

사용:
  python tools/sync_memory.py            # 미러링만(변경 파일 보고)
  python tools/sync_memory.py --stage    # 미러링 + `git add docs/memory`(pre-commit 훅용)
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "docs" / "memory"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass


def _memory_src() -> Path | None:
    env = os.environ.get("COUPANG_MEMORY_DIR")
    if env:
        p = Path(env)
        return p if p.is_dir() else None
    profile = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    if not profile:
        return None
    slug = str(ROOT).replace(":", "-").replace("\\", "-").replace("/", "-")
    p = Path(profile) / ".claude" / "projects" / slug / "memory"
    return p if p.is_dir() else None


_README = (
    "# docs/memory — 세션 메모리 스냅샷(자동 생성·수정 금지)\n\n"
    "이 폴더는 `tools/sync_memory.py` 가 **커밋마다** 외부 실사용 메모리\n"
    "(`%USERPROFILE%\\.claude\\projects\\<slug>\\memory`)를 미러링한 **백업 스냅샷**입니다.\n"
    "직접 수정하지 마세요 — 실사용 메모리를 고치면 다음 커밋에 자동 반영됩니다.\n"
    "목적: PC 교체·`.claude` 소실에도 확정사항(메모리)을 git 으로 보존(손실 방지).\n"
)


def mirror() -> tuple[int, int, int]:
    """외부 메모리 → docs/memory 미러(추가·갱신·삭제). 반환=(추가/갱신, 삭제, 전체 소스 파일 수)."""
    src = _memory_src()
    if src is None:
        return (-1, 0, 0)                                  # 소스 없음 = no-op 신호
    DEST.mkdir(parents=True, exist_ok=True)
    src_files = {p.name: p for p in src.glob("*.md")}
    changed = 0
    for name, p in src_files.items():
        data = p.read_bytes()
        target = DEST / name
        if not target.exists() or target.read_bytes() != data:
            target.write_bytes(data)
            changed += 1
    # 소스에서 사라진 파일은 스냅샷에서도 제거(README 는 유지)
    removed = 0
    for t in DEST.glob("*.md"):
        if t.name not in src_files:
            t.unlink()
            removed += 1
    (DEST / "README.md").write_text(_README, encoding="utf-8")
    return (changed, removed, len(src_files))


def main() -> int:
    stage = "--stage" in sys.argv
    changed, removed, total = mirror()
    if changed < 0:
        print("  [메모리 동기화] 외부 메모리 폴더 없음 → 건너뜀(no-op)")
        return 0
    print(f"  [메모리 동기화] docs/memory 미러 — 갱신 {changed} · 삭제 {removed} · 전체 {total}개")
    if stage:
        try:
            subprocess.run(["git", "add", "--", str(DEST)], cwd=str(ROOT), check=True)
            print("  [메모리 동기화] git add docs/memory 완료(이번 커밋에 포함)")
        except Exception as exc:
            print(f"  [메모리 동기화] ⚠ git add 실패(커밋은 계속): {exc.__class__.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
