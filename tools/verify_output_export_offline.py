"""output 내보내기·합치기·보관 이동 오프라인 검증(D-243 ①② · STATE T-48) — 임시 폴더만 씀 · 실 output 안 건드림.

기대(설계 = D-243 원문·T-48 지시에서 도출):
 ① 변경분 = 기록에 없는 파일·내용이 바뀐 파일만 · 수정 시각만 바뀌고 내용 같으면 뺌 · 두 번째 내보내기 = 0개
 ② 실행 중이면 멈춤 — 실제 registry_lock 으로 쥔 잠금 4종·계정 잠금·정산 상태 파일(실제 RunLog.heartbeat) · 화면
    리더(read_settlement_status)와 같은 판정 · 잠금 파일이 없으면 새로 만들지 않음 · 만드는 사이 시작되면 zip 버림
 ③ 한글 이름 UTF-8 표시(0x800) · 정산\\증빙 포함(D-149) · 평문 비밀번호 파일 뺌(실제 원장 백업 함수 형식 포함)
 ④ 합치기 = 기준본 + 변경분 → 운용 쪽과 해시 같음 · 순서 어긋나면 멈춤 · cp949 이름 zip · 경로 탈출 막음
 ⑤ 보관 이동 = 지난 달까지만·이동만(파일 수·내용 그대로)·최근 1개·이번 달 수정 파일은 남김 · 옮김은 내용 다시 안 보냄

    python tools/verify_output_export_offline.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
rc = getattr(sys.stdout, "reconfigure", None)
if rc:
    rc(encoding="utf-8")

import openpyxl  # noqa: E402
import output_archive as OA  # noqa: E402
import output_export as OE  # noqa: E402
import output_merge as OM  # noqa: E402
from coupang_analytics import registry_gsheet as RG  # noqa: E402
from coupang_analytics.registry_lock import registry_lock  # noqa: E402
from coupang_analytics.settlement_runlog import RunLog  # noqa: E402
from ui.settlement_status_panel_qt import read_settlement_status  # noqa: E402

LOGS: list[str] = []


def ok(msg: str) -> None:
    print(f"  ✔ {msg}")


def _w(p: Path, text: str, mtime: datetime | None = None) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    if mtime:
        os.utime(p, (mtime.timestamp(), mtime.timestamp()))
    return p


def _xlsx(p: Path, rows: list[list]) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    for r in rows:
        wb.active.append(r)
    wb.save(p)
    return p


def make_output(root: Path) -> Path:
    out = root / "output"
    _w(out / "쿠팡데이타분석_실행단계.json", '{"date": "2026-11-14", "stage": "ranks"}')
    _xlsx(out / "쿠팡데이타분석_통계.xlsx", [["상품명", "노출순위"], ["비밀번호 공구통", 3]])   # 상품명 = 오탐 아님
    _w(out / "run_log_261113_180000.log", "앱 로그 1")
    _w(out / "run_log_261114_180000.log", "앱 로그 2")
    _w(out / "판매분석_일별" / "계정A.json", '{"매출": 1}')
    _w(out / "정산" / "증빙" / "증빙_사업자_쿠팡원본" / "주문.csv", "주문번호,구매자\n1,홍길동\n")
    _w(out / "정산" / "로그" / "실행_261114_180000.log", "정산 로그")
    _w(out / "정산" / "로그" / "처리기록_261114_180000.csv", "시각,결과\n")
    _w(out / "정산" / "_잠금" / "_watch.lock", "")
    _w(out / "_잠금" / "파이프라인.lock", "")
    _w(out / "그대로.txt", "안 바뀜")
    _w(out / "곧사라짐.txt", "지워질 파일")
    return out


def _names(z: Path) -> set[str]:
    with zipfile.ZipFile(z) as zf:
        return {i.filename for i in zf.infolist()}


def _manifest(z: Path) -> dict:
    with zipfile.ZipFile(z) as zf:
        return json.loads(zf.read(OE.MANIFEST_NAME).decode("utf-8"))


def _tree(d: Path) -> dict[str, str]:
    return {rel: OE.sha256_of(d / rel) for rel in OE.walk_files(d)}


def _log(m: str) -> None:
    LOGS.append(m)


# ── ③ 비밀번호 판정 ─────────────────────────────────────────
def test_password_detection():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        raws = {s: [["계정아이디", "비밀번호", "상품명"], ["acct1", "plain-secret", "상품"]] if s == RG.ALL_SHEETS[0]
                else [["번호"]] for s in RG.ALL_SHEETS}
        ledger_bak = RG.backup_local(raws, d / "백업", datetime(2026, 11, 14, 18, 0), _log)   # 실제 원장 백업 형식
        assert OE.has_plain_password(ledger_bak), "원장 백업(인라인 글자·문자 참조)을 못 잡음"
        assert OE.has_plain_password(_xlsx(d / "[셀독] 관리 대장.xlsx", [["대표"], ["대표자명", "계정아이디", "비밀번호 1"]]))
        assert not OE.has_plain_password(_xlsx(d / "광고.xlsx", [["상품명"], ["비밀번호 공구통"], ["비밀번호  약통 정리함"]]))
        assert OE.has_plain_password(_w(d / "a.json", '{"id": "x", "password": "abc"}'))
        assert not OE.has_plain_password(_w(d / "b.json", '{"msg": "비밀번호가 다릅니다"}'))
        assert OE.has_plain_password(_w(d / "c.csv", "계정아이디,비밀번호\nx,y\n"))
        assert not OE.has_plain_password(_w(d / "d.log", "비밀번호: (값 생략)"))
    ok("평문 비밀번호 판정 — 실제 원장 백업·관리대장 머리글·json 키·csv 열은 잡고 상품명·로그 문구는 안 잡음")


# ── ② 실행 중 판정 ─────────────────────────────────────────
def test_busy_locks_and_status():
    with tempfile.TemporaryDirectory() as d:
        out = make_output(Path(d))
        assert OE.busy_reasons(out) == [], "잠금 파일만 남은 건 실행 중 아님"
        for rel in ("_잠금/파이프라인.lock", "정산/_잠금/_watch.lock", "정산_셀독전환/_잠금/_실행.lock", "_원장.lock",
                    "정산/_잠금/acct1.lock"):
            with registry_lock(out / rel, wait_sec=0):
                why = OE.busy_reasons(out)
                assert len(why) == 1 and rel.split("/")[-1] in why[0], (rel, why)
                assert OE.cmd_export(_args(out), log=_log) == OE.EXIT_BUSY
            assert OE.busy_reasons(out) == [], rel
        assert not list((Path(d) / "내보내기").glob("*.zip")), "실행 중엔 zip 을 만들면 안 됨"
    ok("잠금 5종(앱·정산 watch·셀독전환자·원장·계정) 쥐면 멈춤(종료 코드 3·zip 없음) · 남은 잠금 파일은 무해")


def test_busy_does_not_create_locks():
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "output"
        out.mkdir()
        assert OE.busy_reasons(out) == []
        assert list(out.rglob("*")) == [], "판정이 잠금 파일·폴더를 만들면 안 됨"
    ok("실행 중 판정은 잠금 파일·폴더를 새로 만들지 않음")


def test_busy_status_file_matches_panel():
    with tempfile.TemporaryDirectory() as d:
        out = make_output(Path(d))
        log = RunLog(out / "정산", echo=lambda m: None)
        for status, busy in (("작동중", True), ("대기중", True), ("완료", False), ("종료", False)):
            log.heartbeat(status, "시험")
            panel = read_settlement_status(out / "정산" / "로그")
            assert bool(OE.busy_reasons(out)) is busy, status
            assert (panel["live_expected"] and not panel["stale"]) is busy, status   # 화면과 같은 판정
        log.heartbeat("작동중", "죽은 기록")
        old = datetime.now() - timedelta(minutes=30)
        st = out / "정산" / "로그" / "_현재상태.txt"
        st.write_text(st.read_text(encoding="utf-8").replace(st.read_text(encoding="utf-8").splitlines()[1],
                                                              f"갱신: {old:%Y-%m-%d %H:%M:%S}"), encoding="utf-8")
        for p in (out / "정산" / "로그").glob("실행_*.log"):
            os.utime(p, (old.timestamp(), old.timestamp()))
        assert OE.busy_reasons(out) == [] and read_settlement_status(out / "정산" / "로그")["stale"]
    ok("정산 상태 파일 작동중·대기중(12분 안) = 멈춤 · 완료·종료·30분 넘은 작동중 = 진행 — 정산 상태 화면 판정과 같음")


# ── ① 변경분 · ③ UTF-8·증빙·비밀번호 ───────────────────────
def _args(out: Path, **kw):
    class A:
        output, dest, only, archive, baseline_record, since = str(out), "", "", False, "", ""
    a = A()
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def _first_export(root: Path) -> tuple[Path, Path, Path]:
    """기준본(= 운용 쪽 사본) 기록을 만들고 운용 쪽을 바꾼 뒤 첫 변경분을 낸다 → (운용 output, 기준본, zip)."""
    out = make_output(root)
    base = root / "dev" / "output"
    shutil.copytree(out, base)
    OE.save_json_atomic(root / "기준기록.json", OE.make_record(base, "시험기준"))
    _w(out / "판매분석_일별" / "계정A.json", '{"매출": 2}')                     # 내용 바뀜
    t = datetime.now() + timedelta(seconds=5)
    os.utime(out / "그대로.txt", (t.timestamp(), t.timestamp()))                 # 시각만 바뀜(내용 같음)
    _w(out / "정산" / "증빙" / "증빙_사업자_쿠팡원본" / "새주문.csv", "주문번호,구매자\n2,김철수\n")
    _w(out / "재고현황_일별" / "재고_261115.json", '{"재고": 5}')
    (out / "곧사라짐.txt").unlink()
    RG.backup_local({s: [["계정아이디", "비밀번호"], ["a", "x"]] for s in RG.ALL_SHEETS}, out / "백업",
                    datetime(2026, 11, 15, 18, 0), _log)
    assert OE.cmd_export(_args(out, baseline_record=str(root / "기준기록.json")), log=_log) == 0
    zips = sorted((root / "내보내기").glob("output_변경분_*.zip"))
    assert len(zips) == 1, zips
    return out, base, zips[0]


def test_changes_export():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        out, _base, z = _first_export(root)
        names = _names(z) - {OE.MANIFEST_NAME}
        want = {"output/판매분석_일별/계정A.json", "output/정산/증빙/증빙_사업자_쿠팡원본/새주문.csv",
                "output/재고현황_일별/재고_261115.json"}
        assert names == want, names
        man = _manifest(z)
        assert man["종류"] == "변경분" and man["이전ID"] == "기준:시험기준"
        assert man["사라짐"] == ["곧사라짐.txt"] and len(man["뺌_비밀번호"]) == 1 and man["뺌_비밀번호"][0].startswith("백업/원장_")
        with zipfile.ZipFile(z) as zf:
            for i in zf.infolist():
                assert i.filename.isascii() or i.flag_bits & 0x800, i.filename
        assert OE.verify_zip(z) == []
        rec = OE.load_record(out / OE.RECORD_NAME)
        assert rec["마지막"]["ID"] == man["ID"] and "그대로.txt" in rec["파일"]
        assert not any(n.endswith(".lock") for n in rec["파일"])
        # 두 번째 = 바뀐 것 없음
        assert OE.cmd_export(_args(out, only="changes"), log=_log) == 0
        z2 = sorted((root / "내보내기").glob("output_변경분_*.zip"))[-1]
        assert _names(z2) == {OE.MANIFEST_NAME} and _manifest(z2)["이전ID"] == man["ID"]
    ok("변경분 = 바뀐·새 파일 3개만(시각만 바뀐 파일·잠금·비밀번호 원장 백업 뺌) · 사라짐 기록 · 증빙 포함 · "
       "한글 UTF-8 · 두 번째 = 0개")


def test_first_run_needs_baseline():
    with tempfile.TemporaryDirectory() as d:
        out = make_output(Path(d))
        assert OE.cmd_export(_args(out, only="changes"), log=_log) == OE.EXIT_NO_RECORD
        cut = datetime.now() + timedelta(minutes=1)
        later = cut + timedelta(minutes=1)
        _w(out / "판매분석_일별" / "계정A.json", '{"매출": 9}', mtime=later)
        assert OE.cmd_export(_args(out, only="changes", since=f"{cut:%Y-%m-%d %H:%M}"), log=_log) == 0
        z = sorted((Path(d) / "내보내기").glob("output_변경분_*.zip"))[-1]
        assert _names(z) == {OE.MANIFEST_NAME, "output/판매분석_일별/계정A.json"}, _names(z)
    ok("처음(기록 없음) = 멈춤(종료 코드 2) · --since 기준 시각 뒤 고친 파일만")


def test_busy_starts_midway():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        out = make_output(root)
        OE.save_json_atomic(root / "r.json", OE.make_record(out, "x"))
        _w(out / "새.txt", "새 파일")
        real, calls = OE.busy_reasons, []

        def fake(o, now=None):
            calls.append(1)
            return [] if len(calls) == 1 else ["시험: 만드는 사이 실행 시작"]
        OE.busy_reasons = fake
        try:
            assert OE.cmd_export(_args(out, only="changes", baseline_record=str(root / "r.json")), log=_log) == 3
        finally:
            OE.busy_reasons = real
        assert not list((root / "내보내기").glob("*.zip*")) and not (out / OE.RECORD_NAME).exists()
    ok("만드는 사이 실행이 시작되면 zip 버림·보낸 기록 안 고침")


def test_check_bundle():
    with tempfile.TemporaryDirectory() as d:
        out = make_output(Path(d))
        RunLog(out / "정산", echo=lambda m: None).heartbeat("완료", "끝")
        assert OE.cmd_export(_args(out, only="check"), log=_log) == 0
        z = sorted((Path(d) / "내보내기").glob("output_확인용_*.zip"))[-1]
        assert _names(z) == {OE.MANIFEST_NAME, "output/run_log_261113_180000.log", "output/run_log_261114_180000.log",
                             "output/정산/로그/실행_261114_180000.log", "output/정산/로그/처리기록_261114_180000.csv",
                             "output/정산/로그/_현재상태.txt", "output/쿠팡데이타분석_통계.xlsx",
                             "output/쿠팡데이타분석_실행단계.json"}, _names(z)
        assert OM.check_zip(z, log=_log) == 0
    ok("확인용 = 앱 실행 로그·정산 로그·상태·결과 엑셀·실행 단계 · 대조 통과")


# ── ④ 합치기 ───────────────────────────────────────────────
def test_merge_matches_source():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        out, base, z = _first_export(root)
        assert OM.merge_zip(z, base, log=_log) == 0
        src, dev = _tree(out), _tree(base)
        secret = {r for r in src if r.startswith("백업/원장_")}
        assert {r: h for r, h in src.items() if r not in secret} == {r: h for r, h in dev.items()
                                                                       if r != "곧사라짐.txt"}
        assert (base / "곧사라짐.txt").exists(), "사라짐은 지우지 않음"
        assert OM._last_id(base) == _manifest(z)["ID"]
        try:
            OM.merge_zip(z, base, log=_log)            # 같은 zip 두 번 = 순서 어긋남
            raise AssertionError("순서 확인이 안 막음")
        except OM.MergeError:
            pass
    ok("합치기 = 기준본+변경분이 운용 쪽과 해시 같음(비밀번호 파일 제외) · 사라짐은 안 지움 · 같은 zip 두 번 = 멈춤")


def _cp949_zip(path: Path, files: dict[str, bytes]) -> None:
    """UTF-8 표시 없이 cp949 이름으로 쓴 zip(Windows tar·옛 압축) — 같은 길이 ASCII 자리표로 쓰고 바이트만 바꿈."""
    marks = {}
    with zipfile.ZipFile(path, "w") as zf:
        for i, (name, data) in enumerate(files.items()):
            raw = name.encode("cp949")
            mark = f"{i:02d}".encode() + b"Q" * (len(raw) - 2)
            marks[mark] = raw
            zf.writestr(mark.decode(), data)
    blob = path.read_bytes()
    for mark, raw in marks.items():
        blob = blob.replace(mark, raw)
    path.write_bytes(blob)


def test_merge_cp949_and_traversal():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        base = root / "base"
        base.mkdir()
        z = root / "old.zip"
        _cp949_zip(z, {"output/정산/증빙/한글.txt": b"abc", "output/판매분석_일별/계정.json": b"{}"})
        with zipfile.ZipFile(z) as zf:
            assert not any(i.flag_bits & 0x800 for i in zf.infolist())
        assert OM.merge_zip(z, base, log=_log) == 0
        assert (base / "정산" / "증빙" / "한글.txt").read_bytes() == b"abc"
        assert (base / "판매분석_일별" / "계정.json").exists()
        for bad in ("../evil.txt", "C:/evil.txt", "a/../../evil.txt", "/abs.txt"):
            zb = root / "bad.zip"
            with zipfile.ZipFile(zb, "w") as zf:
                zf.writestr("ok.txt", b"1")
                zf.writestr(bad, b"x")
            try:
                OM.merge_zip(zb, base, log=_log)
                raise AssertionError(f"경로 탈출 안 막음: {bad}")
            except OM.MergeError:
                pass
            assert not (base / "ok.txt").exists() and not (root / "evil.txt").exists(), bad
    ok("cp949 이름(UTF-8 표시 없음) zip 합침 · 경로 탈출 4종 = 아무것도 안 쓰고 멈춤")


# ── ⑤ 보관 이동 ────────────────────────────────────────────
def test_archive_moves_only():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        out = make_output(root)
        old = datetime(2026, 9, 20, 18, 0)
        for rel in ("백업/통계마스터_260920_180000.xlsx", "백업/통계마스터_261020_180000.xlsx",
                    "백업/통계마스터_261114_180000.xlsx", "백업/원장_261001_180000.xlsx", "백업/원장_261002_180000.xlsx",
                    "run_log_260920_180000.log", "run_log_260921_180000.log.1", "정산/로그/실행_260920_180000.log",
                    "백업/통계마스터_복구교체전.xlsx"):
            _w(out / rel, rel, mtime=old)
        _w(out / "run_log_261031_180000.log", "지난달에 시작해 이번 달에도 쓰는 로그", mtime=datetime.now())
        OE.save_json_atomic(root / "r.json", OE.make_record(out, "x"))
        before_tree = _tree(out)
        assert OA.run(out, before=date(2026, 11, 1), dry_run=False, log=_log) == 0
        after = _tree(out)
        moved = {"백업/통계마스터_260920_180000.xlsx": "보관/2026-09/백업/통계마스터_260920_180000.xlsx",
                 "백업/통계마스터_261020_180000.xlsx": "보관/2026-10/백업/통계마스터_261020_180000.xlsx",
                 "백업/원장_261001_180000.xlsx": "보관/2026-10/백업/원장_261001_180000.xlsx",
                 "run_log_260920_180000.log": "보관/2026-09/run_log_260920_180000.log",
                 "run_log_260921_180000.log.1": "보관/2026-09/run_log_260921_180000.log.1",
                 "정산/로그/실행_260920_180000.log": "보관/2026-09/정산/로그/실행_260920_180000.log"}
        for a, b in moved.items():
            assert a not in after and after[b] == before_tree[a], (a, b)
        for keep in ("백업/통계마스터_261114_180000.xlsx", "백업/원장_261002_180000.xlsx", "run_log_261031_180000.log",
                     "정산/로그/실행_261114_180000.log", "백업/통계마스터_복구교체전.xlsx"):
            assert keep in after, keep
        assert len(after) == len(before_tree) + 1 and (out / "보관" / OA.MOVE_LOG).exists(), "삭제 없음(+이동기록 1)"
        # 이동 뒤 내보내기 = 옮김만(내용 다시 안 보냄)
        assert OE.cmd_export(_args(out, only="changes", baseline_record=str(root / "r.json")), log=_log) == 0
        z = sorted((root / "내보내기").glob("output_변경분_*.zip"))[-1]
        man = _manifest(z)
        assert {(m["전"], m["후"]) for m in man["옮김"]} == set(moved.items()), man["옮김"]
        assert _names(z) == {OM.OE.MANIFEST_NAME, "output/보관/_이동기록.jsonl"}, _names(z)
        held = _tree(out)
        with registry_lock(out / "_잠금" / "파이프라인.lock", wait_sec=0):
            assert OA.run(out, before=date(2026, 12, 1), dry_run=False, log=_log) == OE.EXIT_BUSY
        assert _tree(out) == held, "실행 중엔 아무것도 안 옮김"
    ok("보관 이동 = 지난 달까지·이동만(파일 수 그대로)·묶음마다 최근 1개·이번 달 수정·날짜 없는 이름은 남김 · "
       "이동 뒤 변경분 = '옮김'만 · 실행 중 = 안 옮김")


def main():
    print("output 내보내기·합치기·보관 이동 오프라인 검증(D-243)")
    test_password_detection()
    test_busy_locks_and_status()
    test_busy_does_not_create_locks()
    test_busy_status_file_matches_panel()
    test_changes_export()
    test_first_run_needs_baseline()
    test_busy_starts_midway()
    test_check_bundle()
    test_merge_matches_source()
    test_merge_cp949_and_traversal()
    test_archive_moves_only()
    print("✅ output 내보내기 검증 통과")


if __name__ == "__main__":
    main()
