"""output 합치기(개발 PC) — 기준본 폴더 위에 운용 PC 변경분 zip 을 겹쳐 풀고, 받은 파일을 해시로 대조한다(D-243 ①).

기준본 기본 = `D:\\coupang-analytics\\output\\_분석_261115_output37\\output\\`(output (37)) · 다른 곳은 `--base`.
순서(zip 마다): ① 이름 풀기 — UTF-8 표시(0x800)면 그대로, 없으면 cp437 로 읽힌 바이트를 UTF-8 → cp949 순으로 해석
(Windows 탐색기·tar 로 만든 옛 zip) · 둘 다 안 되면 ❌ 멈춤 ② 경로 탈출 막기 — 절대경로·드라이브·`..`·기준본 밖으로
나가는 이름은 ❌ 멈춤(아무것도 안 씀) ③ 순서 확인 — zip 목록의 '이전ID' 가 기준본에 마지막으로 합친 ID 와 같아야 함
(빠진 변경분이 있으면 멈춤 · `--force` 로만 넘김) ④ '옮김'(운용 PC 보관 이동) = 기준본 안에서 이름만 옮김 ⑤ 파일을
`.part` 로 풀며 해시 → 목록과 같을 때만 제자리로 바꿈 · 수정 시각 = 목록 값 ⑥ 다 푼 뒤 디스크에서 다시 읽어 해시 대조
⑦ 기준본 `_합치기기록.json` 에 덧붙임. '사라짐' 파일은 지우지 않고 알리기만 한다(⛔ 삭제 없음).
목록이 없는 zip(예전 전체 압축)도 겹쳐 풀 수 있다(대조 = zip CRC 만 · 순서 확인 없음).

    python tools/output_merge.py output_변경분_261116_0930.zip                 # 기준본에 합침
    python tools/output_merge.py a.zip b.zip --dry-run                         # 무엇을 할지만
    python tools/output_merge.py check output_확인용_261116_0930.zip           # 풀지 않고 대조만
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
import output_export as OE  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = Path(r"D:\coupang-analytics\output\_분석_261115_output37\output")


class MergeError(Exception):
    """합치기를 시작하지 않음(아무것도 안 씀)."""


def decode_name(info: zipfile.ZipInfo) -> str:
    """zip 항목 이름 → 바른 글자. UTF-8 표시가 없으면 zipfile 이 cp437 로 읽은 것이라 원래 바이트로 되돌려 해석."""
    if info.flag_bits & 0x800 or info.filename.isascii():
        return info.filename
    raw = info.filename.encode("cp437")
    for enc in ("utf-8", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise MergeError(f"이름을 UTF-8·cp949 어느 쪽으로도 못 읽음: {raw!r}")


def safe_rel(name: str) -> str:
    """zip 이름 → 기준본 기준 상대경로(/). 위험한 이름이면 MergeError."""
    n = name.replace("\\", "/")
    parts = PurePosixPath(n).parts
    if not n or n.startswith("/") or ":" in n or any(p in ("..", "") for p in parts):
        raise MergeError(f"위험한 경로라 멈춤: {name!r}")
    return n


def _target(base: Path, rel: str) -> Path:
    t = (base / rel).resolve()
    if not t.is_relative_to(base.resolve()):
        raise MergeError(f"기준본 밖으로 나가는 경로라 멈춤: {rel!r}")
    return t


def read_zip(path: Path) -> tuple[dict | None, list[tuple[zipfile.ZipInfo, str]]]:
    """(목록 또는 None, [(항목, 기준본 기준 상대경로)]) — 디렉터리 항목 뺌 · `output/` 앞머리 뗌(모두 붙어 있을 때)."""
    with zipfile.ZipFile(path) as zf:
        infos = [(i, decode_name(i)) for i in zf.infolist() if not i.is_dir()]
        man = None
        if any(n == OE.MANIFEST_NAME for _, n in infos):
            man = json.loads(zf.read(OE.MANIFEST_NAME).decode("utf-8"))
    infos = [(i, safe_rel(n)) for i, n in infos if n != OE.MANIFEST_NAME]
    if infos and all(n.startswith(OE.ARC_PREFIX) for _, n in infos):
        infos = [(i, n[len(OE.ARC_PREFIX):]) for i, n in infos]
    return man, infos


def _last_id(base: Path) -> str:
    p = base / OE.MERGE_RECORD_NAME
    if not p.exists():
        return ""
    hist = json.loads(p.read_text(encoding="utf-8")).get("합침", [])
    return hist[-1]["ID"] if hist else ""


def check_order(base: Path, man: dict, force: bool) -> str:
    """순서 확인 — 문제가 있으면 그 문구(force 면 경고만)."""
    if man.get("종류") != "변경분":
        raise MergeError(f"'{man.get('종류')}' 묶음은 합치지 않음 — 그냥 풀어서 보세요(대조만 = check 명령)")
    last, prev = _last_id(base), man.get("이전ID", "")
    ok = (prev == last) if last else prev.startswith("기준:")
    if ok:
        return ""
    msg = (f"순서가 맞지 않음 — 이 zip 의 이전ID '{prev}' · 기준본에 마지막으로 합친 ID '{last or '(없음 — 기준본 그대로)'}'"
           " → 빠진 변경분 zip 이 있는지 확인")
    if not force:
        raise MergeError(msg + " (그래도 합치려면 --force)")
    return msg


def _check_manifest(man: dict, infos) -> dict[str, dict]:
    want = {f["경로"]: f for f in man.get("파일", [])}
    have = {n for _, n in infos}
    if have != set(want):
        raise MergeError(f"zip 항목과 목록이 다름(빠짐 {len(set(want) - have)} · 남음 {len(have - set(want))})")
    return want


def _extract_one(zf: zipfile.ZipFile, info: zipfile.ZipInfo, dst: Path, want: dict | None) -> str:
    """.part 로 풀며 해시 → 목록과 같으면 제자리로. 반환 = 해시. 다르면 MergeError(.part 는 지움 — 이 도구가 만든 임시)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    part = dst.with_name(dst.name + ".part")
    h = hashlib.sha256()
    with zf.open(info) as fin, part.open("wb") as fo:      # 끝까지 읽으면 zipfile 이 CRC 대조
        for b in iter(lambda: fin.read(OE.CHUNK), b""):
            h.update(b)
            fo.write(b)
    sha = h.hexdigest()
    if want and sha != want["sha256"]:
        part.unlink()
        raise MergeError(f"받은 내용 해시가 목록과 다름: {dst}")
    os.replace(part, dst)
    if want and want.get("수정시각ns"):
        os.utime(dst, ns=(want["수정시각ns"], want["수정시각ns"]))
    else:
        ts = datetime(*info.date_time).timestamp()
        os.utime(dst, (ts, ts))
    return sha


def _apply_moves(base: Path, man: dict, dry: bool, log) -> int:
    n = 0
    for m in man.get("옮김", []):
        src, dst = _target(base, safe_rel(m["전"])), _target(base, safe_rel(m["후"]))
        if dst.exists():
            log(f"  · 옮김 건너뜀(이미 있음): {m['후']}")
        elif not src.exists():
            log(f"  ⚠ 옮길 원본이 기준본에 없음: {m['전']} → {m['후']}")
        else:
            if not dry:
                dst.parent.mkdir(parents=True, exist_ok=True)
                os.rename(src, dst)
            n += 1
    return n


def _verify_disk(base: Path, written: dict[str, str]) -> list[str]:
    return [rel for rel, sha in written.items() if OE.sha256_of(_target(base, rel)) != sha]


def _record(base: Path, zpath: Path, man: dict | None, n_files: int, n_moves: int, warn: str) -> None:
    p = base / OE.MERGE_RECORD_NAME
    data: dict = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"형식": OE.FORMAT, "합침": []}
    data["합침"].append({"ID": (man or {}).get("ID", f"목록없음:{zpath.name}"), "zip": zpath.name,
                        "시각": f"{datetime.now():%Y-%m-%d %H:%M:%S}", "파일": n_files, "옮김": n_moves,
                        "경고": warn})
    OE.save_json_atomic(p, data)


def merge_zip(zpath: Path, base: Path, *, dry: bool = False, force: bool = False, log=print) -> int:
    """zip 하나를 기준본에 합침. 반환 = 0(통과) · 1(대조 실패)."""
    man, infos = read_zip(zpath)
    for _, rel in infos:
        _target(base, rel)                                   # 하나라도 위험하면 아무것도 안 씀
    warn = check_order(base, man, force) if man else "목록 없음 — zip CRC 대조만"
    want = _check_manifest(man, infos) if man else {}
    if warn:
        log(f"  ⚠ {warn}")
    log(f"  {zpath.name}: 파일 {len(infos)}개 · 옮김 {len((man or {}).get('옮김', []))} · "
        f"사라짐 {len((man or {}).get('사라짐', []))}(지우지 않음)")
    if dry:
        return 0
    n_moves = _apply_moves(base, man or {}, dry, log)
    written: dict[str, str] = {}
    with zipfile.ZipFile(zpath) as zf:
        for info, rel in infos:
            written[rel] = _extract_one(zf, info, _target(base, rel), want.get(rel))
    bad = _verify_disk(base, written)
    for rel in bad:
        log(f"  ❌ 디스크 대조 실패: {rel}")
    if bad:
        return 1
    _record(base, zpath, man, len(written), n_moves, warn)
    log(f"  ✔ 합침: 파일 {len(written)}개 해시 대조 통과 · 옮김 {n_moves} → {base}")
    return 0


def check_zip(zpath: Path, log=print) -> int:
    """풀지 않고 대조만(output_export.verify_zip 과 같은 기준 + 이름 해석·경로 안전)."""
    man, infos = read_zip(zpath)
    if man is None:
        log(f"❌ 목록({OE.MANIFEST_NAME})이 없는 zip: {zpath}")
        return 1
    _check_manifest(man, infos)
    bad = OE.verify_zip(zpath)
    for m in bad:
        log(f"  ❌ {m}")
    log(f"  {'❌' if bad else '✔'} {zpath.name}: {man.get('종류')} · 파일 {len(infos)}개")
    return 1 if bad else 0


def main(argv=None) -> int:
    rc = getattr(sys.stdout, "reconfigure", None)
    if rc:
        rc(encoding="utf-8")
    ap = argparse.ArgumentParser(description="운용 PC output 변경분 zip → 개발 PC 기준본 합치기(D-243)")
    ap.add_argument("zips", nargs="+", help="zip 들(앞에 'check' 를 쓰면 대조만)")
    ap.add_argument("--base", default=str(DEFAULT_BASE))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="순서(이전ID)가 안 맞아도 합침")
    a = ap.parse_args(argv)
    zips = [Path(z) for z in a.zips]
    try:
        if zips[0].name == "check":
            return max(check_zip(z) for z in zips[1:])
        base = Path(a.base).resolve()
        if not base.is_dir():
            raise MergeError(f"기준본 폴더가 없음: {base}")
        for z in sorted(zips, key=lambda p: p.name):        # 이름 = 만든 시각 순
            if merge_zip(z, base, dry=a.dry_run, force=a.force):
                return 1
    except MergeError as exc:
        print(f"❌ {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
