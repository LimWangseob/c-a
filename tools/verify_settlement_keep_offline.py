"""정산 자료 전날 값 보관(D-335 · T-123) 오프라인 검증 — 로그인·쿠팡 호출 없음(결정적).

기대값 출처 = 소유자 원문(D-335 · 11-18) "이미 받은 자료에 다음날 업데이트해서 전날 자료가 없어지는 것은 방지 해야 함." ·
조사표 `output\\_점검_261118_정산항목체크\\정산자료_수집진행률_1118.md` 5절 '덮어씀' 9곳(코드에서 뽑지 않음).
규칙: 덮어쓰기 전 값이 수집일(옛 파일 수정 날짜)별로 남음 · 같은 내용이면 중복 보관 생략 · 보관본은 덮어쓰지 않음 ·
읽는 쪽(최신 파일 이름 · glob) 그대로 · 보관 위치 = 같은 폴더 `수집일별보관\\{파일 이름}\\{YYYY-MM-DD}{확장자}.gz`.

    python tools/verify_settlement_keep_offline.py
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics import daily_snapshot as DS  # noqa: E402
from coupang_analytics import sales_history as SH  # noqa: E402
from coupang_analytics import settlement_ads as AD  # noqa: E402
from coupang_analytics import settlement_docs as DOC  # noqa: E402
from coupang_analytics import settlement_fetch_check as FC  # noqa: E402
from coupang_analytics import settlement_jobs as SJ  # noqa: E402
from coupang_analytics import settlement_sources as SRC  # noqa: E402
from coupang_analytics import settlement_store as STORE  # noqa: E402

D = date.fromisoformat
KEEP = "수집일별보관"


def ok(msg: str) -> None:
    print(f"  OK {msg}")


def age(p: Path, day: str) -> None:
    """옛 파일 수정 시각을 그 날 정오로(= 그날 받은 자료)."""
    t = datetime.fromisoformat(f"{day}T12:00:00").timestamp()
    os.utime(p, (t, t))


def kept(p: Path) -> dict[str, bytes]:
    """보관본 {파일 이름: 풀어낸 내용}."""
    d = p.parent / KEEP / p.name
    return {x.name: gzip.decompress(x.read_bytes()) for x in sorted(d.glob("*.gz"))} if d.is_dir() else {}


def k1_helper():
    print("[K1] 보관 함수 — 첫 저장 없음 · 다음날 덮어쓰기 전 옛 값 = 옛 수집일 이름 · 같은 날 재기록 생략 · 같은 내용 생략 · 보관본 안 덮음")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "A.json"
        assert DS.keep_before_overwrite(p, D("2026-11-17")) is None, "파일 없음 = 보관 없음"
        p.write_bytes(b'{"v": 1}')
        age(p, "2026-11-17")
        assert DS.keep_before_overwrite(p, D("2026-11-17")) is None and kept(p) == {}, "같은 날 다시 쓰기 = 보관 없음(그날 마지막 값은 다음날 남김)"
        got = DS.keep_before_overwrite(p, D("2026-11-18"))
        assert got == p.parent / KEEP / "A.json" / "2026-11-17.json.gz", got
        assert kept(p) == {"2026-11-17.json.gz": b'{"v": 1}'}, kept(p)
        p.write_bytes(b'{"v": 1}')                                   # 다음날 같은 내용으로 다시 씀
        age(p, "2026-11-18")
        assert DS.keep_before_overwrite(p, D("2026-11-19")) is None and len(kept(p)) == 1, "앞 보관본과 같은 내용 = 생략"
        p.write_bytes(b'{"v": 2}')
        age(p, "2026-11-19")
        assert DS.keep_before_overwrite(p, D("2026-11-20"), new=b'{"v": 2}') is None, "새로 쓸 내용과 같음 = 생략"
        DS.keep_before_overwrite(p, D("2026-11-20"))
        assert kept(p) == {"2026-11-17.json.gz": b'{"v": 1}', "2026-11-19.json.gz": b'{"v": 2}'}, kept(p)
        p.write_bytes(b'{"v": 3}')
        age(p, "2026-11-19")                                         # 같은 수집일 이름이 이미 있음(시계·복사본) — 보관본 안 덮음
        DS.keep_before_overwrite(p, D("2026-11-21"))
        names = sorted(kept(p))
        assert names[:2] == ["2026-11-17.json.gz", "2026-11-19.json.gz"] and len(names) == 3 and names[2].startswith("2026-11-19_"), names
        assert kept(p)["2026-11-19.json.gz"] == b'{"v": 2}', "앞 보관본 그대로"
        assert sorted(x.name for x in Path(td).glob("*.json")) == ["A.json"], "읽는 쪽 glob('*.json') = 최신 파일만"
        assert not list(Path(td).rglob("*.tmp")), "임시 파일 안 남음"
        g = Path(td) / "B.json.gz"                                    # 이미 압축된 파일 = 다시 압축 안 함
        g.write_bytes(gzip.compress(b"x"))
        age(g, "2026-11-17")
        assert DS.keep_before_overwrite(g, D("2026-11-18")).name == "2026-11-17.json.gz"
    ok("첫 저장·같은 날·같은 내용 = 보관 없음 · 다음날 = 옛 수집일 이름 · 같은 이름 있으면 시각 붙임 · glob 영향 없음")


def k2_verify_json():
    print("[K2] 1번 검증자료 계정 json — 다음날 수집이 우대수수료 '이체 대기' 기록을 지워도 전날 값 남음(실측 23계정)")
    import settlement_download as TD
    from coupang_analytics import settlement_verify_collect as VC
    old = {"수집일": "2026-11-15", "favorable": {"202610": [{"status": "TRANSFER_WAIT", "transferDate": "-"}]}}
    new = {"수집일": "2026-11-18", "favorable": {"202610": [{"status": "TRANSFER_COMPLETE", "transferDate": "2026-11-17"}]},
           "조회 실패": []}
    saved = (TD.VERIFY, TD.LOG, TD.name_of, TD._wing_files, VC.collect)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "A.json"
        p.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
        age(p, "2026-11-15")
        log = SimpleNamespace(record=lambda *a, **k: None, saved=lambda *a, **k: None)
        try:
            TD.VERIFY, TD.LOG, TD.name_of, TD._wing_files = Path(td), log, (lambda a: "A"), (lambda n: [])
            VC.collect = lambda *a, **k: json.loads(json.dumps(new))
            TD.collect_verify(None, None, SimpleNamespace(start=D("2026-01-01")))
        finally:
            TD.VERIFY, TD.LOG, TD.name_of, TD._wing_files, VC.collect = saved
        assert json.loads(p.read_text(encoding="utf-8"))["favorable"]["202610"][0]["status"] == "TRANSFER_COMPLETE", "최신 파일 = 새 값"
        k = kept(p)
        assert list(k) == ["2026-11-15.json.gz"], k
        assert json.loads(k["2026-11-15.json.gz"])["favorable"]["202610"][0]["status"] == "TRANSFER_WAIT", "전날 '이체 대기' 기록 남음"
    ok("최신 파일 이름 그대로 새 값 · 11-15 값 = 수집일별보관\\A.json\\2026-11-15.json.gz")


def k3_docs_returns_and_state():
    print("[K3] 2·7·9번 월자료 — RG반품내역_최신.xlsx 다음날 덮어쓰기 · _실패_ 근거 · _받은기록.json 전날 값 남음")
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td) / "월자료" / "A"
        run = DOC._Run(folder, lambda m: None, (), lambda: datetime(2026, 11, 17, 19, 0))
        run.save(f"{DOC.RETURNS}_최신.xlsx", b"PK-day17", DOC.RETURNS)
        p, lp = folder / f"{DOC.RETURNS}_최신.xlsx", folder / DOC.LEDGER
        age(p, "2026-11-17")
        age(lp, "2026-11-17")
        run2 = DOC._Run(folder, lambda m: None, (), lambda: datetime(2026, 11, 18, 19, 0))
        run2.save(f"{DOC.RETURNS}_최신.xlsx", b"PK-day18", DOC.RETURNS)
        assert p.read_bytes() == b"PK-day18" and kept(p) == {"2026-11-17.xlsx.gz": b"PK-day17"}, kept(p)
        assert str(json.loads(kept(lp)["2026-11-17.json.gz"])[DOC.RETURNS]).startswith("2026-11-17"), kept(lp)

        class Fail(Exception):
            detail = {"쪽": 1}
        fp = folder / "_실패_주문별매출_202601.json"
        run2.attempt("주문별매출 202601", lambda: (_ for _ in ()).throw(Fail("a")))
        age(fp, "2026-11-17")
        Fail.detail = {"쪽": 2}
        DOC._Run(folder, lambda m: None, (), lambda: datetime(2026, 11, 18, 19, 0)).attempt(
            "주문별매출 202601", lambda: (_ for _ in ()).throw(Fail("b")))
        assert json.loads(fp.read_text(encoding="utf-8")) == {"쪽": 2}, "최신 실패 근거"
        assert json.loads(kept(fp)["2026-11-17.json.gz"]) == {"쪽": 1}, "앞 실패 근거 남음"
        assert DOC.left_months(folder, D("2026-11-18"), True) >= 0, "받은 기록 읽기 그대로"
    ok("반품 최신본·실패 근거·받은 기록 = 최신 이름 그대로 · 전날 값 수집일별보관")


def k4_amounts():
    print("[K4] 3번 쿠팡지급내역 — 같은 정산일 줄을 쿠팡이 고쳐 다시 받아도 옛 줄 남음")
    saved = STORE.AMOUNTS
    with tempfile.TemporaryDirectory() as td:
        try:
            STORE.AMOUNTS = Path(td)
            row = {"정산일": "2026-11-13", "기간 시작": "2026-10-27", "금액": 100}
            STORE.save_amounts("A", "윙", [row])
            p = Path(td) / "A_윙.json"
            age(p, "2026-11-13")
            STORE.save_amounts("A", "윙", [{**row, "금액": 90}])
            assert json.loads(p.read_text(encoding="utf-8"))[0]["금액"] == 90, "최신 = 고친 값"
            assert json.loads(kept(p)["2026-11-13.json.gz"])[0]["금액"] == 100, "고치기 전 값 남음"
            for day in ("2026-11-14", "2026-11-15", "2026-11-16"):              # 같은 내용 계속 = 보관 안 늘어남
                age(p, day)
                STORE.save_amounts("A", "윙", [{**row, "금액": 90}])
            assert sorted(kept(p)) == ["2026-11-13.json.gz", "2026-11-14.json.gz"], kept(p)
        finally:
            STORE.AMOUNTS = saved
    ok("정산일 묶음 교체 전 값 = 수집일별보관 · 같은 내용 생략")


def k5_ads_progress():
    print("[K5] 4·9번 광고 진행 달 일별·광고 상태 — 매일 덮어써도 전날 일별 값 남음")
    acct = "가-나-acct1"
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        for ym in ("202609", "202610"):
            (folder / f"{acct}_광고정산_{ym}.json").write_text("{}", encoding="utf-8")
            (folder / f"{acct}_밀크런_{ym}.xlsx").write_bytes(b"m")
        (folder / f"{acct}_광고.json").write_text(json.dumps({"캠페인 없음": ["202609", "202610"]}), encoding="utf-8")
        amount = [7]

        def call(method, path, body):
            if "DailySettlement" in body["query"]:
                return {"data": {"getDailySettlement": {"summary": {"v": amount[0]}, "items": [], "subtotals": {}}}}
            return {"data": {"getCampaignList": []}}
        AD.collect(call, lambda url: b"m", folder, acct, D("2026-09-01"), D("2026-11-17"))
        p = folder / f"{acct}_{AD.PROGRESS}_202611.json"
        age(p, "2026-11-17")
        amount[0] = 8
        AD.collect(call, lambda url: b"m", folder, acct, D("2026-09-01"), D("2026-11-18"))
        assert json.loads(p.read_text(encoding="utf-8"))["summary"]["v"] == 8
        prev = json.loads(kept(p)["2026-11-17.json.gz"])
        assert prev["summary"]["v"] == 7 and prev["기간"] == ["2026-11-01", "2026-11-16"], prev
        assert not [x for x in folder.glob(f"{acct}_*") if x.is_dir()], "광고 계정 파일 glob 에 보관 폴더 안 걸림"
    ok("진행 달 일별 = 최신 이름 그대로 · 11-17 받은 값(1일~16일) 남음")


def k6_period():
    print("[K6] 6번 판매분석_기간 — 진행 중 달 누계 교체 전 값 남음")
    with tempfile.TemporaryDirectory() as td:
        m = {"v1": SimpleNamespace(product_name="상품", option_name="옵션", registration_type="RFM", gmv=1000, sales=1,
                                   orders=1, inventory_id="1")}
        SH.record_period(td, "acc1", "M:2026-11", "2026-11-01", "2026-11-16", m)
        p = Path(td) / SH.PERIOD_DIRNAME / "acc1.json"
        age(p, "2026-11-17")
        m["v1"].gmv = 3000
        SH.record_period(td, "acc1", "M:2026-11", "2026-11-01", "2026-11-17", m)
        assert SH.load_periods(td)["acc1"]["M:2026-11"]["합계"]["판매금액"] == 3000, "읽는 쪽 = 최신"
        assert json.loads(kept(p)["2026-11-17.json.gz"])["M:2026-11"]["합계"]["판매금액"] == 1000
    ok("기간 합계 교체 전 값 = 수집일별보관 · load_period 그대로")


def k7_fetch_check_jobs_sources():
    print("[K7] 8·9번 받기의심.csv·다시받을목록.csv · _요청기록.json · 원문관측.json — 전날 값 남음")
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        row = {c: "" for c in FC.COLUMNS}
        FC.write(base, [{**row, "다시 받기": FC.YES}], D("2026-11-17"))
        sus = base / "받기의심.csv"
        age(sus, "2026-11-17")
        age(base / "다시받을목록.csv", "2026-11-17")
        FC.write(base, [], D("2026-11-18"))
        assert "2026-11-17" in kept(sus)["2026-11-17.csv.gz"].decode("utf-8-sig"), kept(sus)
        assert "2026-11-17.csv.gz" in kept(base / "다시받을목록.csv")

        jp = base / "_요청기록.json"
        SJ.save_jobs(jp, [])
        age(jp, "2026-11-17")
        SJ.save_jobs(jp, [SJ.Job(**_job_args())])
        assert json.loads(kept(jp)["2026-11-17.json.gz"]) == [], kept(jp)
        assert len(SJ.load_jobs(jp)) == 1, "읽는 쪽 그대로"

        sp = SRC.folder(base) / "원문관측.json"
        (base / "파일").mkdir()
        SRC.compare_originals(base, base / "파일", D("2026-11-17"))
        age(sp, "2026-11-17")
        state = json.loads(sp.read_text(encoding="utf-8"))
        SRC.compare_originals(base, base / "파일", D("2026-11-18"))
        assert json.loads(kept(sp)["2026-11-17.json.gz"]) == state, kept(sp)
    ok("목록·요청기록·원문관측 = 최신 이름 그대로 · 전날 값 수집일별보관")


def _job_args() -> dict:
    import dataclasses
    fields = {f.name: f for f in dataclasses.fields(SJ.Job)}
    out = {}
    for n, f in fields.items():
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
            out[n] = "x"
    return out


def main() -> int:
    k1_helper()
    k2_verify_json()
    k3_docs_returns_and_state()
    k4_amounts()
    k5_ads_progress()
    k6_period()
    k7_fetch_check_jobs_sources()
    print("정산 자료 전날 값 보관 — 전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
