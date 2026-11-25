"""output 내보내기 — 운용 PC output 을 개발 PC 로 옮길 때 '바뀐 파일만' 작게 묶는다(D-243 ① · STATE T-48).

만드는 것(받는 곳 기본 = output 옆 `내보내기` 폴더):
- `output_변경분_yymmdd_HHMM.zip` : 지난 내보내기 뒤 바뀐 파일만. 크기·수정 시각이 같으면 안 바뀜, 다르면 내용 해시
  (SHA-256)로 다시 보고 내용이 같으면 뺀다. 지난 기록에 있던 파일이 다른 자리에서 같은 해시로 나오면 '옮김'
  (보관 이동 · 내용은 다시 안 보냄). 보낸 기록 = `output\\_내보내기기록.json`(zip 을 다 만들고 대조까지 통과한 뒤에만 고침).
- `output_확인용_yymmdd_HHMM.zip` : 확인용 작은 묶음 — 앱 실행 로그(run_log 최근 3개)·정산 로그(최근 실행 3회의
  실행·오류·처리기록 + `_현재상태.txt`·`_완료.json`·`_앱정상종료.json`)·`쿠팡데이타분석_통계.xlsx`·
  `쿠팡데이타분석_실행단계.json`. 보낸 기록과 무관(매번 새로).
- zip 안 = `output/...`(예전 전체 압축과 같은 모양) + 맨 끝 `_내보내기목록.json`(파일마다 크기·해시·수정 시각, 옮김,
  사라짐, 뺀 파일) → 개발 PC `tools/output_merge.py` 가 이걸로 대조한다.

지키는 규칙:
- 한글 이름 = UTF-8 표시(0x800) — Python zipfile 로 쓰고 다시 열어 표시·해시 대조(D-201 방식 · tar 안 씀).
- 정산 증빙(`정산\\증빙`) 포함(D-149) — 빼는 폴더 = 정산서 배치가 다시 만드는 `정산서\\_읽은결과` 하나(잠금 파일·임시 파일·이 도구 기록도 뺌).
- 평문 비밀번호 든 파일은 넣지 않는다(CLAUDE.md '비밀번호 평문 = 출력물 금지' · 관리대장 로컬 백업 없음 규칙).
  판정 = 엑셀 칸 글자 전체가 비밀번호 머리글('비밀번호'·'비번'·'패스워드'·'password'·'pw' + 숫자)인 칸이 있음,
  또는 json·csv 에 비밀번호 키/열이 있음. 실측(output (37)): `백업\\원장_*.xlsx`(registry_gsheet.backup_local
  '비밀번호 포함')·`백업\\관리대장_*.xlsx`·`[셀독] 관리 대장.xlsx` 가 걸림. 상품명 '비밀번호 공구통' 같은 칸은 안 걸림.
- 앱·정산이 도는 중이면 만들지 않고 멈춤(종료 코드 3) — 판정 근거는 `busy_reasons()` 설명.

    python tools/output_export.py --output D:\\coupang-analytics\\output              # 변경분 + 확인용
    python tools/output_export.py --output ... --only check                             # 확인용만
    python tools/output_export.py --output ... --archive                                # 보관 이동 먼저(output_archive)
    python tools/output_export.py --output ... --baseline-record 기준기록.json           # 처음 한 번(기준본 기록)
    python tools/output_export.py make-record --output <기준본 output> --to 기준기록.json  # 개발 PC: 기준본 기록 만들기

이 파일은 저장소 패키지 없이 혼자 돈다(운용 PC 는 exe 배포라 `coupang_analytics` 패키지가 없음) — 잠금 판정은
`registry_lock.py` 와 같은 OS 잠금 방식을 여기서 직접 쓴다(오프라인 시험이 실제 registry_lock 과 맞는지 대조).
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

FORMAT = 1
RECORD_NAME = "_내보내기기록.json"          # output 안 · 보낸 기록
MERGE_RECORD_NAME = "_합치기기록.json"       # 개발 PC 기준본 안 · 합친 기록(output_merge)
MANIFEST_NAME = "_내보내기목록.json"         # zip 맨 끝
ARC_PREFIX = "output/"
SKIP_PREFIX = "정산서/_읽은결과/"            # 정산서 배치가 원본에서 다시 만드는 저장분(D-419 ① · 원본이 아님)
CHUNK = 1 << 20
EXIT_BUSY, EXIT_NO_RECORD = 3, 2
sys.path.insert(0, str(Path(__file__).resolve().parent))   # output_archive(같은 폴더)

# ── 실행 중 판정 ─────────────────────────────────────────────
# 잠금 파일(output 기준 상대경로) — 쥔 프로세스가 있으면 OS 잠금이 걸려 있다(파일만 남은 건 무해 · registry_lock.py).
LOCKS = (
    ("앱 실행(판매수집·키워드·순위 — ui/app_qt.py _pipe_lock_path)", "_잠금/파이프라인.lock"),
    ("정산 자동 다운로드(watch·합치기 — tools/settlement_download.py)", "정산/_잠금/_watch.lock"),
    ("셀독전환자 로그인 확인·정산 받기(transfer_login.RUN_LOCK)", "정산_셀독전환/_잠금/_실행.lock"),
    ("원장 쓰기(registry_lock.DEFAULT_LOCK_PATH)", "_원장.lock"),
)
ACCOUNT_LOCK_GLOB = "정산/_잠금/*.lock"         # 계정별 정산 로그인 잠금(settlement_download.py _session·셀독전환자)
STATUS_FILE = "정산/로그/_현재상태.txt"         # 정산 heartbeat(settlement_runlog.RunLog.heartbeat)
LIVE_STATUSES = ("작동중", "대기중")            # settlement_status_panel_qt.read_settlement_status live_expected
STALE_SEC = 12 * 60                              # 같은 화면의 '멈춤 의심' 기준 — 이보다 오래된 작동중 = 죽은 기록

if sys.platform == "win32":
    import msvcrt

    def _try_lock(fd: int) -> bool:
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        return True
else:
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        fcntl.flock(fd, fcntl.LOCK_UN)
        return True


def lock_held(path: Path) -> bool:
    """잠금 파일을 다른 프로세스가 쥐고 있나 — 잠깐 잡아 보고 바로 놓음(transfer_login.busy_reason 과 같은 방식).
    파일이 없으면 아무도 안 쥔 것(쥐는 쪽이 만든다) — 이 도구는 잠금 파일을 새로 만들지 않는다."""
    if not path.exists():
        return False
    fd = os.open(path, os.O_RDWR)
    try:
        return not _try_lock(fd)
    finally:
        os.close(fd)


def _status_busy(out: Path, now: datetime) -> str:
    """정산 상태 파일이 '작동중/대기중'이고 최근(STALE_SEC 안)에 갱신됐으면 그 이유. 갱신 = 상태 파일 '갱신:' 줄과
    최신 `실행_*.log` 수정 시각 중 늦은 것(read_settlement_status 와 같은 기준)."""
    p = out / STATUS_FILE
    if not p.exists():
        return ""
    st = dict(ln.split(":", 1) for ln in p.read_text(encoding="utf-8").splitlines() if ":" in ln)
    status = st.get("상태", "").strip()
    if status not in LIVE_STATUSES:
        return ""
    stamps = []
    if st.get("갱신", "").strip():
        stamps.append(datetime.strptime(st["갱신"].strip(), "%Y-%m-%d %H:%M:%S"))
    logs = list(p.parent.glob("실행_*.log"))
    if logs:
        stamps.append(datetime.fromtimestamp(max(x.stat().st_mtime for x in logs)))
    if stamps and (now - max(stamps)).total_seconds() <= STALE_SEC:
        return f"정산 상태 파일 = '{status}'(마지막 활동 {max(stamps):%m-%d %H:%M:%S}) — {p}"
    return ""


def busy_reasons(out: Path, now: datetime | None = None) -> list[str]:
    """앱·정산이 도는 중이면 그 이유들(없으면 []). 근거:
    - `_잠금/파이프라인.lock` = 앱 전체실행·무인(--auto)·반자동 순위·키워드가 실행 내내 쥠(ui/app_qt.py run_bg pipelinelock)
    - `정산/_잠금/_watch.lock` = 정산 watch(①대기 포함)·합치기가 쥠(tools/settlement_download.py cmd_watch·cmd_merge)
    - `정산/_잠금/{계정}.lock` = 정산 계정 로그인 중(수동 run·download·셀독전환자 받기)
    - `정산_셀독전환/_잠금/_실행.lock` = 셀독전환자 1·2단계 · `_원장.lock` = 원장 쓰기
    - `정산/로그/_현재상태.txt` 작동중/대기중 + 12분 안 갱신(잠금이 없는 예외 상황 대비 이중 확인)"""
    now = now or datetime.now()
    out = Path(out)
    why = [f"{label} — {out / rel}" for label, rel in LOCKS if lock_held(out / rel)]
    why += [f"정산 계정 로그인 중 — {p}" for p in sorted(out.glob(ACCOUNT_LOCK_GLOB))
            if p.name != "_watch.lock" and lock_held(p)]
    st = _status_busy(out, now)
    return why + ([st] if st else [])


# ── 평문 비밀번호 판정 ───────────────────────────────────────
_PW_CELL = re.compile(r"\s*(비밀번호|비번|패스워드|password|passwd|pw)\s*\d?\s*(\([^)]*\))?\s*", re.I)
_PW_JSON = re.compile(r'"(?:비밀번호|비번|패스워드|password|passwd|pw)\d?"\s*:\s*"[^"]+"', re.I)
_T_TEXT = re.compile(r"<t(?:\s[^>]*)?>([^<]{1,40})</t>")
_SHEET_HEAD = 512 * 1024      # 시트 XML 앞부분(머리글 줄)만 — 인라인 글자(openpyxl 원장 백업 방식)


def _xlsx_has_pw(path: Path) -> bool:
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        chunks = [z.read("xl/sharedStrings.xml")] if "xl/sharedStrings.xml" in names else []
        for n in names:
            if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"):
                with z.open(n) as f:
                    chunks.append(f.read(_SHEET_HEAD))
    return any(_PW_CELL.fullmatch(html.unescape(t)) for c in chunks
               for t in _T_TEXT.findall(c.decode("utf-8", "replace")))


def _csv_has_pw(path: Path) -> bool:
    with path.open(encoding="utf-8-sig", errors="replace") as f:
        head = f.readline()
    return any(_PW_CELL.fullmatch(c.strip().strip('"')) for c in head.split(","))


def has_plain_password(path: Path) -> bool:
    """이 파일에 평문 비밀번호가 들어 있을 수 있나(엑셀 비밀번호 머리글 칸 · json 비밀번호 키 · csv 비밀번호 열)."""
    suf = path.suffix.lower()
    if suf in (".xlsx", ".xlsm"):
        return zipfile.is_zipfile(path) and _xlsx_has_pw(path)
    if suf in (".json", ".jsonl"):
        return bool(_PW_JSON.search(path.read_text(encoding="utf-8", errors="replace")))
    if suf == ".csv":
        return _csv_has_pw(path)
    return False


# ── 파일 목록·해시 ───────────────────────────────────────────
def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(CHUNK), b""):
            h.update(b)
    return h.hexdigest()


def skip_file(rel: str) -> bool:
    """내보내기에서 늘 빼는 것 — 잠금 파일(.lock · 열면 OS 잠금 충돌)·쓰는 중 임시 파일·이 도구들 기록."""
    name = rel.rsplit("/", 1)[-1]
    return (name.endswith((".lock", ".tmp", ".part")) or name in (RECORD_NAME, MERGE_RECORD_NAME)
            or name.startswith(RECORD_NAME))


def walk_files(out: Path, skip_dirs: tuple[Path, ...] = ()) -> dict[str, os.stat_result]:
    """output 아래 파일 {상대경로(/): stat}. skip_dirs(받는 곳이 output 안일 때) 아래는 뺌."""
    found: dict[str, os.stat_result] = {}
    skips = {d.resolve() for d in skip_dirs}
    for dirpath, dirnames, filenames in os.walk(out):
        here = Path(dirpath)
        dirnames[:] = [d for d in dirnames if (here / d).resolve() not in skips]
        for fn in filenames:
            p = here / fn
            rel = p.relative_to(out).as_posix()
            if not skip_file(rel) and not rel.startswith(SKIP_PREFIX):
                found[rel] = p.stat()
    return found


def load_record(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("형식") != FORMAT or not isinstance(data.get("파일"), dict):
        raise SystemExit(f"[오류] 보낸 기록 형식이 다름: {path}")
    return data


def save_json_atomic(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    os.replace(tmp, path)


def make_record(out: Path, name: str) -> dict:
    """기준본 기록 — 파일마다 [크기, 수정시각=None, 해시, 표시] (수정 시각은 PC 마다 달라 비움 → 해시로 대조)."""
    files = {rel: [st.st_size, None, sha256_of(out / rel), ""] for rel, st in sorted(walk_files(out).items())}
    return {"형식": FORMAT, "기준": name, "마지막": {"ID": f"기준:{name}", "시각": f"{datetime.now():%Y-%m-%d %H:%M:%S}"},
            "파일": files}


def since_record(out: Path, since: datetime) -> dict:
    """기준 기록이 없을 때 — 기준 시각 전에 고친 파일은 기준본에 있다고 보고 [크기, 수정시각, 해시=None] 로 기록."""
    cut = since.timestamp()
    files = {rel: [st.st_size, st.st_mtime_ns, None, ""] for rel, st in walk_files(out).items() if st.st_mtime < cut}
    return {"형식": FORMAT, "기준": f"시각 {since:%Y-%m-%d %H:%M}", "마지막": {"ID": f"기준:시각 {since:%Y-%m-%d %H:%M}"},
            "파일": files}


class Plan:
    """한 번 내보내기 판정 결과."""

    def __init__(self):
        self.send: list[str] = []                 # 보낼 파일(바뀜·새로)
        self.moved: list[tuple[str, str, str]] = []   # (전, 후, 해시)
        self.gone: list[str] = []                 # 기록에 있었는데 사라짐(옮김 아님)
        self.secret: list[str] = []               # 평문 비밀번호라 뺌
        self.unreadable: list[tuple[str, str]] = []   # 못 읽음(다음에 다시)
        self.files: dict[str, list] = {}          # 새 기록


def _classify(out: Path, rel: str, st, rec: list | None, plan: Plan, hashes: dict) -> None:
    if rec and rec[0] == st.st_size and rec[1] == st.st_mtime_ns:
        plan.files[rel] = rec
        return
    try:
        sha = sha256_of(out / rel) if (rec and rec[2] and rec[0] == st.st_size) or rec is None else None
    except OSError as exc:
        plan.unreadable.append((rel, f"{exc.__class__.__name__}: {exc}"))
        return
    if rec and sha and sha == rec[2]:
        plan.files[rel] = [st.st_size, st.st_mtime_ns, sha, rec[3]]
        return
    hashes[rel] = sha
    plan.send.append(rel)


def _find_moves(plan: Plan, old: dict, seen: set, hashes: dict) -> None:
    missing: dict[str, list[str]] = {}
    for rel, rec in old.items():
        if rel not in seen and rec[2]:
            missing.setdefault(rec[2], []).append(rel)
    keep = []
    for rel in plan.send:
        sha = hashes.get(rel)
        if rel not in old and sha and missing.get(sha):
            src = missing[sha].pop(0)
            plan.moved.append((src, rel, sha))
            plan.files[rel] = [old[src][0], None, sha, old[src][3]]
        else:
            keep.append(rel)
    plan.send = keep
    moved_src = {m[0] for m in plan.moved}
    plan.gone = sorted(r for r in old if r not in seen and r not in moved_src)


def _drop_secrets(out: Path, plan: Plan) -> None:
    keep = []
    for rel in plan.send:
        if has_plain_password(out / rel):
            st = (out / rel).stat()
            plan.secret.append(rel)
            plan.files[rel] = [st.st_size, st.st_mtime_ns, sha256_of(out / rel), "비밀번호"]
        else:
            keep.append(rel)
    plan.send = keep


def plan_changes(out: Path, record: dict, skip_dirs: tuple[Path, ...] = ()) -> Plan:
    """지난 기록과 비교해 보낼 파일·옮김·사라짐·뺀 파일을 정한다(아직 아무것도 안 씀)."""
    plan, old = Plan(), record["파일"]
    hashes: dict[str, str | None] = {}
    found = walk_files(out, skip_dirs)
    for rel, st in sorted(found.items()):
        _classify(out, rel, st, old.get(rel), plan, hashes)
    _find_moves(plan, old, set(found), hashes)
    _drop_secrets(out, plan)
    return plan


# ── zip 쓰기·대조 ────────────────────────────────────────────
_STORED = (".zip", ".gz", ".png", ".jpg", ".jpeg", ".webp")


def _zinfo(arc: str, st) -> zipfile.ZipInfo:
    t = time.localtime(max(st.st_mtime, 315532800))   # zip 시각 하한 1980-01-01
    zi = zipfile.ZipInfo(arc, date_time=t[:6])
    zi.compress_type = zipfile.ZIP_STORED if arc.lower().endswith(_STORED) else zipfile.ZIP_DEFLATED
    zi.external_attr = 0o644 << 16
    zi.file_size = st.st_size          # 크기를 미리 알려 2GB 미만은 보통 머리(ZIP64 머리 없음 — 탐색기 호환)
    return zi


def write_zip(dest: Path, out: Path, rels: list[str], manifest: dict) -> dict[str, list]:
    """rels 를 `output/<상대경로>` 로 담고 맨 끝에 목록을 담는다. 담으면서 잰 [크기, 수정시각ns, 해시] 를 돌려준다
    (목록·기록은 실제로 담은 바이트 기준). dest 는 `.part` 경로 — 대조 뒤 호출부가 이름을 바꾼다."""
    got: dict[str, list] = {}
    with zipfile.ZipFile(dest, "w", allowZip64=True) as zf:
        for rel in rels:
            src = out / rel
            st = src.stat()
            h, n = hashlib.sha256(), 0
            with src.open("rb") as fin, zf.open(_zinfo(ARC_PREFIX + rel, st), "w") as fo:
                for b in iter(lambda: fin.read(CHUNK), b""):
                    h.update(b)
                    n += len(b)
                    fo.write(b)
            got[rel] = [n, st.st_mtime_ns, h.hexdigest()]
        manifest["파일"] = [{"경로": r, "크기": v[0], "수정시각ns": v[1], "sha256": v[2]} for r, v in got.items()]
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=1), zipfile.ZIP_DEFLATED)
    return got


def verify_zip(path: Path) -> list[str]:
    """만든 zip 을 다시 열어 대조 — 목록과 항목 수·이름 같음 · 비ASCII 이름 전부 UTF-8 표시 · 내용 해시·CRC 같음.
    문제 목록을 돌려준다(빈 목록 = 통과)."""
    bad: list[str] = []
    with zipfile.ZipFile(path) as zf:
        man = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
        want = {ARC_PREFIX + f["경로"]: f for f in man["파일"]}
        infos = [i for i in zf.infolist() if i.filename != MANIFEST_NAME]
        if {i.filename for i in infos} != set(want):
            bad.append(f"항목 이름이 목록과 다름(zip {len(infos)} · 목록 {len(want)})")
        for i in infos:
            if not i.filename.isascii() and not i.flag_bits & 0x800:
                bad.append(f"UTF-8 표시 없음: {i.filename}")
            h = hashlib.sha256()
            with zf.open(i) as f:          # 끝까지 읽으면 zipfile 이 CRC 도 대조(다르면 BadZipFile)
                for b in iter(lambda: f.read(CHUNK), b""):
                    h.update(b)
            w = want.get(i.filename)
            if w and (h.hexdigest() != w["sha256"] or i.file_size != w["크기"]):
                bad.append(f"내용 다름: {i.filename}")
    return bad


def zip_name(dest_dir: Path, kind: str, now: datetime) -> Path:
    base = f"output_{kind}_{now:%y%m%d_%H%M}"
    p, n = dest_dir / f"{base}.zip", 2
    while p.exists() or p.with_name(p.name + ".part").exists():
        p, n = dest_dir / f"{base}_{n}.zip", n + 1
    return p


def _finish_zip(part: Path, final: Path, out: Path, log) -> bool:
    """대조 + 다시 실행 중 확인 → 통과면 이름 바꿈. 실패면 이 도구가 만든 .part 만 지우고 False."""
    bad = verify_zip(part)
    busy = busy_reasons(out)
    if bad or busy:
        part.unlink()
        for m in bad[:20]:
            log(f"  ❌ 대조 실패: {m}")
        for m in busy:
            log(f"  ⛔ 만드는 사이 실행이 시작됨: {m}")
        return False
    os.replace(part, final)
    return True


# ── 변경분·확인용 ────────────────────────────────────────────
def _manifest(kind: str, out: Path, now: datetime, prev: str) -> dict:
    return {"형식": FORMAT, "종류": kind, "ID": f"{now:%y%m%d_%H%M%S}", "이전ID": prev,
            "만든시각": f"{now:%Y-%m-%d %H:%M:%S}", "output": str(out.resolve())}


def export_changes(out: Path, dest_dir: Path, record: dict, now: datetime, log) -> Path | None:
    plan = plan_changes(out, record, (dest_dir,))
    man = _manifest("변경분", out, now, record["마지막"]["ID"])
    man.update({"옮김": [{"전": a, "후": b, "sha256": s} for a, b, s in plan.moved], "사라짐": plan.gone,
                "뺌_비밀번호": plan.secret, "못읽음": [r for r, _ in plan.unreadable]})
    final = zip_name(dest_dir, "변경분", now)
    part = final.with_name(final.name + ".part")
    got = write_zip(part, out, plan.send, man)
    if not _finish_zip(part, final, out, log):
        return None
    files = dict(plan.files)
    files.update({rel: [v[0], v[1], v[2], ""] for rel, v in got.items()})
    save_json_atomic(out / RECORD_NAME, {"형식": FORMAT, "기준": record.get("기준", ""), "파일": files,
                                          "마지막": {"ID": man["ID"], "시각": man["만든시각"], "zip": final.name}})
    size = sum(v[0] for v in got.values())
    log(f"  ✔ 변경분: 파일 {len(got)}개({size / 1e6:.1f}MB) → 압축 {final.stat().st_size / 1e6:.1f}MB · "
        f"옮김 {len(plan.moved)} · 사라짐 {len(plan.gone)}")
    for rel in plan.secret:
        log(f"  · 평문 비밀번호가 있어 뺌: {rel}")
    for rel, why in plan.unreadable:
        log(f"  ⚠ 못 읽어서 이번엔 못 보냄(다음 내보내기 때 다시): {rel} — {why}")
    return final


def check_bundle_files(out: Path) -> list[str]:
    """확인용 묶음에 넣을 파일(있는 것만) — 앱 실행 로그 최근 3 · 정산 최근 3회 로그 · 상태 · 결과 엑셀 · 실행 단계."""
    rels = [p.name for p in sorted(out.glob("run_log_*.log"))[-3:]]
    logdir = out / "정산" / "로그"
    for p in sorted(logdir.glob("실행_*.log"))[-3:]:
        rid = p.stem.removeprefix("실행_")
        rels += [f"정산/로그/{n}" for n in (p.name, f"오류_{rid}.log", f"처리기록_{rid}.csv") if (logdir / n).exists()]
    rels += [f"정산/로그/{n}" for n in ("_현재상태.txt", "_완료.json", "_앱정상종료.json") if (logdir / n).exists()]
    rels += [n for n in ("쿠팡데이타분석_통계.xlsx", "쿠팡데이타분석_실행단계.json") if (out / n).exists()]
    return rels


def export_check(out: Path, dest_dir: Path, now: datetime, log) -> Path | None:
    rels = check_bundle_files(out)
    secret = [r for r in rels if has_plain_password(out / r)]
    rels = [r for r in rels if r not in secret]
    man = _manifest("확인용", out, now, "")
    man["뺌_비밀번호"] = secret
    final = zip_name(dest_dir, "확인용", now)
    part = final.with_name(final.name + ".part")
    got = write_zip(part, out, rels, man)
    if not _finish_zip(part, final, out, log):
        return None
    log(f"  ✔ 확인용: 파일 {len(got)}개 → 압축 {final.stat().st_size / 1e6:.1f}MB")
    return final


# ── 명령 ────────────────────────────────────────────────────
def _load_or_start_record(out: Path, args, log) -> dict | None:
    rec_path = out / RECORD_NAME
    if rec_path.exists():
        return load_record(rec_path)
    if args.baseline_record:
        log(f"  처음 내보내기 — 기준본 기록 사용: {args.baseline_record}")
        return load_record(Path(args.baseline_record))
    if args.since:
        log(f"  처음 내보내기 — 기준 시각 {args.since} 뒤에 고친 파일을 보냄")
        return since_record(out, datetime.strptime(args.since, "%Y-%m-%d %H:%M"))
    log("❌ 보낸 기록이 없습니다(처음). 아래 둘 중 하나로 다시 실행하세요:\n"
        "   ① --baseline-record <개발 PC 가 기준본으로 만든 기록 파일>  (정확 · 권장)\n"
        "   ② --since \"YYYY-MM-DD HH:MM\"  (기준본 zip 을 만든 시각 — 그 뒤에 고친 파일만)")
    return None


def cmd_export(args, log=print) -> int:
    out = Path(args.output).resolve()
    if not out.is_dir():
        log(f"❌ output 폴더가 없음: {out}")
        return 1
    busy = busy_reasons(out)
    if busy:
        log("⛔ 앱·정산이 도는 중이라 만들지 않고 멈춥니다(끝난 뒤 다시 실행):")
        for m in busy:
            log(f"   - {m}")
        return EXIT_BUSY
    if args.archive:
        import output_archive   # 같은 tools 폴더(운용 PC = 이 파일 옆)
        rc = output_archive.run(out, before=output_archive.this_month(), dry_run=False, log=log)
        if rc:
            return rc
    dest_dir = Path(args.dest).resolve() if args.dest else out.parent / "내보내기"
    dest_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    made: list[Path | None] = []
    if args.only in ("", "changes"):
        record = _load_or_start_record(out, args, log)
        if record is None:
            return EXIT_NO_RECORD
        made.append(export_changes(out, dest_dir, record, now, log))
    if args.only in ("", "check"):
        made.append(export_check(out, dest_dir, now, log))
    if any(m is None for m in made):
        return EXIT_BUSY
    log("완료 — 아래 파일을 개발 PC 로 옮기세요:")
    for z in made:
        log(f"   {z}")
    return 0


def cmd_make_record(args, log=print) -> int:
    out = Path(args.output).resolve()
    rec = make_record(out, args.name or out.parent.name)
    save_json_atomic(Path(args.to), rec)
    log(f"✔ 기준본 기록: 파일 {len(rec['파일'])}개 → {Path(args.to).resolve()}")
    return 0


def main(argv=None) -> int:
    rc = getattr(sys.stdout, "reconfigure", None)
    if rc:
        rc(encoding="utf-8")
    ap = argparse.ArgumentParser(description="output 변경분·확인용 내보내기(D-243)")
    ap.add_argument("command", nargs="?", default="export", choices=("export", "make-record"))
    ap.add_argument("--output", default="output", help="output 폴더")
    ap.add_argument("--dest", default="", help="zip 받는 곳(기본 = output 옆 내보내기)")
    ap.add_argument("--only", default="", choices=("", "changes", "check"))
    ap.add_argument("--archive", action="store_true", help="내보내기 전에 지난 달까지의 백업·로그를 보관\\YYYY-MM 로 이동")
    ap.add_argument("--baseline-record", default="", help="처음 한 번: 개발 PC 가 만든 기준본 기록")
    ap.add_argument("--since", default="", help='처음 한 번: 기준본 zip 만든 시각 "YYYY-MM-DD HH:MM"')
    ap.add_argument("--to", default="", help="make-record: 기록 파일 저장 경로")
    ap.add_argument("--name", default="", help="make-record: 기준 이름(기본 = 기준본 폴더 위 폴더 이름)")
    args = ap.parse_args(argv)
    if args.command == "make-record":
        if not args.to:
            ap.error("make-record 는 --to 필요")
        return cmd_make_record(args)
    return cmd_export(args)


if __name__ == "__main__":
    raise SystemExit(main())
