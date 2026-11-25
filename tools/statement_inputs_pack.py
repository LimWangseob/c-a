"""정산서 입력 묶기(개발 PC → 운용 PC · D-399 계획 설계 6) — `output\\정산서\\입력\\` 손 입력 10종 + `output\\정산서\\입력_셀독\\` →
`정산서입력_YYMMDD.zip`(이름 UTF-8). 운용 PC 는 `업데이트.bat`(배포 zip 안의 묶음) 또는
`deploy\\정산서입력_반영.bat` 로 `output\\정산서\\` 에 더하기만 한다.

    python tools/statement_inputs_pack.py [--output <output 폴더>] [--seldoc <셀독 입력 폴더>] [--dest <zip 둘 폴더>]

- 원본은 읽기만(지우기·옮기기 없음) · 같은 이름 zip 이 이미 있으면 덮지 않고 `_HHMMSS` 를 붙인 새 이름.
- 넣는 것 = 두 폴더 안의 파일(하위 폴더 포함) · 빼는 것 = 이름이 `_`·`~$` 로 시작하는 파일·폴더, `보관` 폴더.
- 셀독 입력 3종 = 사업자_대응표.csv · 셀독_계약상품군_판정.json · 계약서_정밀분석_DB*.xlsx 1개 — 빠지면 알림(묶기는 함) · DB 가 여럿 = 중단.
- 비밀번호 칸이 든 파일(json 키 · csv 첫 줄 · xlsx 머리 3줄에 '비밀번호'·password 등)이 있으면 묶지 않고 중단(평문 비밀번호 사본 금지).
- zip 안 경로 = `입력/<파일>` · `입력_셀독/<파일>`(운용 PC `output\\정산서\\` 아래 같은 자리).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PW_NAMES = {"비밀번호", "비번", "password", "passwd", "pw", "pwd"}
SKIP_DIR = "보관"
SELDOC_FILES = ("사업자_대응표.csv", "셀독_계약상품군_판정.json")      # 셀독 입력 3종(레인 D 결정 · 통제 세션 11-24) + 계약 DB 1개
SELDOC_DB = "계약서_정밀분석_DB*.xlsx"


def _skip(rel: Path) -> bool:
    return any(p == SKIP_DIR or p.startswith("_") or p.startswith("~$") for p in rel.parts)


def files_of(folder: Path) -> list[Path]:
    """folder 아래 묶을 파일(이름 순) — 없는 폴더 = 빈 목록."""
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.rglob("*") if p.is_file() and not _skip(p.relative_to(folder)))


def _pw_key(v) -> bool:
    return isinstance(v, str) and v.strip().lower() in PW_NAMES


def _json_keys(o) -> bool:
    if isinstance(o, dict):
        return any(_pw_key(k) or _json_keys(v) for k, v in o.items())
    if isinstance(o, list):
        return any(_json_keys(v) for v in o)
    return False


def has_password(p: Path) -> bool:
    """비밀번호 칸이 보이면 True(묶지 않음)."""
    suf = p.suffix.lower()
    if suf == ".json":
        return _json_keys(json.loads(p.read_text(encoding="utf-8-sig")))
    if suf == ".csv":
        with p.open(encoding="utf-8-sig", newline="") as f:
            head = next(csv.reader(f), [])
        return any(_pw_key(c) for c in head)
    if suf in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        try:
            return any(_pw_key(c) for ws in wb.worksheets for r in ws.iter_rows(max_row=3, values_only=True) for c in r)
        finally:
            wb.close()
    return False


def seldoc_missing(seldoc: Path) -> list[str]:
    """셀독 입력 3종 중 없는 이름 · 계약 DB 가 여럿이면 ValueError(어느 것인지 모름 — 1개만 둘 것)."""
    dbs = sorted(seldoc.glob(SELDOC_DB)) if seldoc.is_dir() else []
    if len(dbs) > 1:
        raise ValueError(f"셀독 계약 DB 가 {len(dbs)}개 — 1개만 두세요: {[p.name for p in dbs]}")
    return [n for n in SELDOC_FILES if not (seldoc / n).is_file()] + ([] if dbs else [SELDOC_DB])


def zip_name(dest: Path, now: datetime) -> Path:
    p = dest / f"정산서입력_{now:%y%m%d}.zip"
    return p if not p.exists() else dest / f"정산서입력_{now:%y%m%d_%H%M%S}.zip"


def pack(inputs: Path, seldoc: Path, dest: Path, now: datetime | None = None, log=print, strict: bool = False) -> Path:
    """두 폴더 → zip 1개(원본 그대로 둠). 입력 폴더가 비었거나 비밀번호 칸이 있으면 ValueError · strict(배포 빌드) = 셀독 입력이 빠져도 ValueError."""
    now = now or datetime.now()
    plan = [(p, Path("입력") / p.relative_to(inputs)) for p in files_of(inputs)]
    plan += [(p, Path("입력_셀독") / p.relative_to(seldoc)) for p in files_of(seldoc)]
    if not any(arc.parts[0] == "입력" for _, arc in plan):
        raise ValueError(f"입력 폴더에 묶을 파일 없음: {inputs}")
    miss = seldoc_missing(seldoc)
    if miss and strict:
        raise ValueError(f"셀독 입력 빠짐: {', '.join(miss)} — {seldoc}")
    if miss:
        log(f"⚠ 셀독 입력 빠짐(셀독 정산서는 운용 PC 에서 '중단'으로 보고됨): {', '.join(miss)}")
    bad = [str(p) for p, _ in plan if has_password(p)]
    if bad:
        raise ValueError(f"비밀번호 칸이 든 파일 — 묶지 않음: {bad}")
    dest.mkdir(parents=True, exist_ok=True)
    out = zip_name(dest, now)
    with zipfile.ZipFile(out, "x", zipfile.ZIP_DEFLATED) as z:      # 'x' = 있는 파일 덮지 않음
        for p, arc in plan:
            z.write(p, arc.as_posix())
    log(f"✅ {out} — 파일 {len(plan)}개(입력 {sum(a.parts[0] == '입력' for _, a in plan)} · 셀독 "
        f"{sum(a.parts[0] == '입력_셀독' for _, a in plan)})")
    return out


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(description="정산서 입력 묶기(개발 PC → 운용 PC)")
    ap.add_argument("--output", type=Path, default=ROOT / "output")
    ap.add_argument("--seldoc", type=Path, help="셀독 정산서 입력 폴더(기본 <output>/정산서/입력_셀독)")
    ap.add_argument("--dest", type=Path, help="zip 둘 폴더(기본 <output>/정산서)")
    ap.add_argument("--strict", action="store_true", help="셀독 입력이 빠지면 묶지 않음(배포 빌드용)")
    a = ap.parse_args(argv)
    base = a.output / "정산서"
    try:
        pack(base / "입력", a.seldoc or base / "입력_셀독", a.dest or base, strict=a.strict)
    except ValueError as exc:
        print(f"❌ 묶지 않음 — {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
