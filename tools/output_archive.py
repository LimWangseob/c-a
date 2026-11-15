"""output 보관 이동 — 지난 달까지의 백업·로그를 `output\\보관\\YYYY-MM\\<원래 자리>` 로 **옮기기만** 한다(D-243 ②).

⛔ 지우지 않는다(output 삭제 금지) · 앱 기동 경로에 넣지 않는다(사람이 bat 로 또는 내보내기 `--archive` 로만).
앱·정산이 도는 중이면 아무것도 안 옮기고 멈춤(output_export.busy_reasons 와 같은 판정 · 종료 코드 3).

옮기는 대상(이름의 날짜 yymmdd **와** 마지막 수정 날짜가 둘 다 이번 달 1일 전인 것 · 각 묶음의 가장 최근 1개는 남김).
수정 날짜도 보는 이유: 늘 켜 둔 앱은 지난 달에 만든 run_log 에 줄마다 열고-쓰고-닫기로 이어 쓴다(ui/app_qt.py:1016) —
이름만 보고 옮기면 다음 줄이 원래 자리에 새 파일을 만들어 로그가 둘로 갈린다.
- `백업\\*_yymmdd_HHMMSS.xlsx`(통계마스터·결과시트·원장·관리대장 백업)
  근거: 쓰는 곳만 있고 읽는 코드 없음 — pipeline_gsheet.backup_sources(통계마스터_·결과시트_)·
  registry_gsheet.backup_local(원장_) 이 쓰기만 함 · 저장소 전체 '백업' 검색에서 이 폴더를 읽는 glob/open 없음(2026-11-15).
- `run_log_yymmdd_HHMMSS.*`(앱 실행 로그 · 회전본 .log.1 · 옛 .zip)
  근거: ui/app_qt.py:199 가 새 이름으로 쓰기만 함 · 'run_log' 를 읽는 코드 없음.
- `정산\\로그\\실행_yymmdd_HHMMSS.log`
  근거: 읽는 곳 = ui/settlement_status_panel_qt._newest_log(가장 최근 1개만) → 최근 1개는 남기므로 화면 그대로.
  (`정산_셀독전환\\로그` 는 다른 폴더라 대상 아님 · 처리기록·오류 로그·처리기록_누적.csv 는 대상 아님)

이미 같은 자리에 파일이 있으면 옮기지 않고 그대로 둠(덮어쓰기 없음). 열려 있어 못 옮긴 파일은 그대로 두고 알림.
옮긴 기록 = `output\\보관\\_이동기록.jsonl`(한 줄 = 전·후·크기·시각).

    python tools/output_archive.py --output D:\\coupang-analytics\\output            # 옮김
    python tools/output_archive.py --output ... --dry-run                             # 옮길 목록만
    python tools/output_archive.py --output ... --before 2026-10                     # 2026-10-01 전까지만
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import output_export as OE  # noqa: E402

ARCHIVE_DIR = "보관"
MOVE_LOG = "_이동기록.jsonl"
_STAMP = re.compile(r"_(\d{6})_\d{6}")

# (묶음 이름, 폴더(output 기준), 이름 규칙) — 묶음마다 가장 최근 1개는 남김
GROUPS = (
    ("백업", "백업", re.compile(r"(.+)_\d{6}_\d{6}\.xlsx")),
    ("앱 실행 로그", "", re.compile(r"(run_log)_\d{6}_\d{6}\..+")),
    ("정산 실행 로그", "정산/로그", re.compile(r"(실행)_\d{6}_\d{6}\.log")),
)


def this_month() -> date:
    return date.today().replace(day=1)


def _stamp_date(name: str) -> date | None:
    m = _STAMP.search(name)
    return datetime.strptime(m.group(1), "%y%m%d").date() if m else None


def plan_moves(out: Path, before: date) -> list[tuple[Path, Path]]:
    """(전, 후) 목록 — 이름 날짜가 before 전인 파일 · 같은 앞이름(예 통계마스터·원장) 묶음의 가장 최근 1개는 뺌."""
    moves: list[tuple[Path, Path]] = []
    for _label, folder, rule in GROUPS:
        d = out / folder if folder else out
        if not d.is_dir():
            continue
        kinds: dict[str, list[tuple[date, Path]]] = {}
        for p in d.iterdir():
            m = rule.fullmatch(p.name)
            when = _stamp_date(p.name) if m and p.is_file() else None
            if m and when:
                kinds.setdefault(m.group(1), []).append((when, p))
        for items in kinds.values():
            items.sort(key=lambda x: (x[0], x[1].name))
            for when, p in items[:-1]:
                if when < before and date.fromtimestamp(p.stat().st_mtime) < before:
                    rel = p.relative_to(out)
                    moves.append((p, out / ARCHIVE_DIR / f"{when:%Y-%m}" / rel))
    return sorted(moves)


def _move_one(src: Path, dst: Path) -> str:
    if dst.exists():
        return "같은 자리에 이미 파일이 있어 그대로 둠"
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(src, dst)          # 같은 드라이브 = 이름만 바뀜(내용·수정 시각 그대로) · 대상이 있으면 실패(덮어쓰기 없음)
    except PermissionError as exc:
        return f"사용 중이라 못 옮김({exc.__class__.__name__})"
    return ""


def run(out: Path, *, before: date, dry_run: bool, log=print) -> int:
    out = Path(out).resolve()
    busy = OE.busy_reasons(out)
    if busy:
        log("⛔ 앱·정산이 도는 중이라 보관 이동을 하지 않고 멈춥니다:")
        for m in busy:
            log(f"   - {m}")
        return OE.EXIT_BUSY
    moves = plan_moves(out, before)
    total = sum(s.stat().st_size for s, _ in moves)
    log(f"  보관 이동 대상: {len(moves)}개({total / 1e6:.1f}MB) · 기준 = 이름 날짜 {before:%Y-%m-%d} 전")
    if dry_run:
        for s, d in moves:
            log(f"   {s.relative_to(out)} → {d.relative_to(out)}")
        return 0
    done, kept = 0, []
    log_path = out / ARCHIVE_DIR / MOVE_LOG
    for s, d in moves:
        why = _move_one(s, d)
        if why:
            kept.append((s, why))
            continue
        done += 1
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"시각": f"{datetime.now():%Y-%m-%d %H:%M:%S}", "전": s.relative_to(out).as_posix(),
                                "후": d.relative_to(out).as_posix(), "크기": d.stat().st_size},
                               ensure_ascii=False) + "\n")
    log(f"  ✔ 보관 이동 {done}개 · 그대로 둔 것 {len(kept)}개 → {out / ARCHIVE_DIR}")
    for s, why in kept:
        log(f"   ⚠ {s.relative_to(out)}: {why}")
    return 0


def main(argv=None) -> int:
    rc = getattr(sys.stdout, "reconfigure", None)
    if rc:
        rc(encoding="utf-8")
    ap = argparse.ArgumentParser(description="output 백업·로그 보관 이동(D-243 ② · 삭제 없음)")
    ap.add_argument("--output", default="output")
    ap.add_argument("--before", default="", help="YYYY-MM — 그 달 1일 전까지 옮김(기본 = 이번 달)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    before = datetime.strptime(a.before, "%Y-%m").date() if a.before else this_month()
    return run(Path(a.output), before=before, dry_run=a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
