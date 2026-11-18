"""다시받을목록 자동 재받기(D-339 · T-82 · T-90) 오프라인 검증 — 로그인·쿠팡 호출 없음(결정적).

기대값 출처 = 소유자 선택 D-339(11-18) "자동으로 다시 받기 (추천)" 적용 문구(코드에서 뽑지 않음):
① 다시받을목록.csv 의 빈 파일·광고 subtotals 필요분을 다음 실행에서 자동으로 다시 받음 ② 받은 기록에 올라 다시 안 받던 빈 파일도
대상(실측 ski1121·freewin7777 라이브정산_202602.json = {"요약": [], "상세": []} · 받은 기록 11-11) ③ 한 회차 개수 상한·차단 간격 =
평소 받기 흐름 그대로(이 단계는 표시만 · 접속 없음) ④ 다시 받아도 같은 결과면 반복하지 않고 '확인 필요' ⑤ `_광고_다시받기.json` 을
앱이 만듦(T-122 인계 2절 — 지금은 앱이 안 만듦). 2025 달 광고 = 정산 대상 아님(D-328) → 자동 대상 아님.

    python tools/verify_settlement_refetch_offline.py
"""
from __future__ import annotations

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

from coupang_analytics import settlement_ads as AD  # noqa: E402
from coupang_analytics import settlement_docs as DOC  # noqa: E402
from coupang_analytics import settlement_fetch_check as FC  # noqa: E402
from coupang_analytics import settlement_jobs as SJ  # noqa: E402
from coupang_analytics import settlement_refetch as RF  # noqa: E402

D = date.fromisoformat
ACCT = "가-나-acct1"
EMPTY: dict = {"요약": [], "상세": []}


def ok(msg: str) -> None:
    print(f"  OK {msg}")


def wjson(p: Path, data) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def rjson(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def age(p: Path, day: str) -> None:
    t = datetime.fromisoformat(f"{day}T12:00:00").timestamp()
    os.utime(p, (t, t))


def live_base(td: str) -> tuple[Path, Path, Path]:
    """라이브정산 2월 빈 json(받은 기록 11-11) + 3/30 공제 347 — D-302 실측 모양."""
    base = Path(td)
    folder = base / "검증자료" / "월자료" / ACCT
    f = wjson(folder / "라이브정산_202602.json", EMPTY)
    age(f, "2026-11-11")
    led = wjson(folder / DOC.LEDGER, {"라이브정산": {"202602": "2026-11-11T04:18:46", "202601": "2026-11-11T04:10:00"}})
    wjson(base / "쿠팡지급내역" / f"{ACCT}_로켓그로스.json", [{"정산일": "2026-03-30", FC.LIVE_FIELD: 347}])
    return base, f, led


def live_rows(base: Path) -> list[dict]:
    return FC.live_checks(base / "검증자료" / "월자료", base / "쿠팡지급내역")


def r1_live_empty():
    print("[R1] 라이브정산 빈 파일(받은 기록 있음) → 받은 기록에서 그 달만 뺌 · 대기 중 다시 안 건드림 · 같은 결과 = 확인 필요")
    with tempfile.TemporaryDirectory() as td:
        base, f, led = live_base(td)
        rows = live_rows(base)
        assert [(r["판정"], r["다시 받기"]) for r in rows] == [(FC.SUSPECT, FC.YES)], rows
        s = RF.plan(base, rows, D("2026-11-18"))
        assert s["표시"] == 1, s
        assert list(rjson(led)["라이브정산"]) == ["202601"], "그 달만 받은 기록에서 빠짐(다음 실행 collect_docs 가 다시 받음)"
        assert rows[0]["다시 받기"] == FC.YES, "표시한 줄은 다시받을목록에 그대로(대기)"
        assert DOC.left_months(led.parent, D("2026-11-18"), False) >= 1

        s = RF.plan(base, live_rows(base), D("2026-11-19"))                # 아직 안 받음(파일 그대로) = 대기
        assert (s["표시"], s["대기"]) == (0, 1), s

        f.write_text(json.dumps(EMPTY, ensure_ascii=False), encoding="utf-8")    # 다시 받았는데 또 빈 파일
        wjson(led, {"라이브정산": {"202601": "2026-11-11T04:10:00", "202602": "2026-11-19T05:00:00"}})
        rows = live_rows(base)
        s = RF.plan(base, rows, D("2026-11-20"))
        assert (s["표시"], s["같은 결과"]) == (0, 1), s
        assert "202602" in rjson(led)["라이브정산"], "같은 결과 = 다시 빼지 않음(반복 안 함)"
        assert (rows[0]["판정"], rows[0]["다시 받기"]) == (FC.CHECK, FC.NO) and "같은 결과" in rows[0]["설명"], rows[0]
        alls, again = FC.write(base / "자료출처", rows, D("2026-11-20"))
        assert len(again.read_text(encoding="utf-8-sig").strip().splitlines()) == 1, "다시받을목록 = 머리줄만"
        assert "확인 필요" in alls.read_text(encoding="utf-8-sig")
        s = RF.plan(base, live_rows(base), D("2026-11-21"))                # 다음 날에도 같은 판정 유지
        assert s["같은 결과"] == 1 and "202602" in rjson(led)["라이브정산"], s
    ok("ski1121 모양 빈 2월 = 받은 기록 202602 만 빠짐 · 파일 그대로면 대기 · 다시 받아 또 빈 = 확인 필요·다시받을목록 빠짐·반복 없음")


def r1b_live_new_content():
    print("[R1b] 다시 받았는데 내용이 달라졌으나 아직 의심 = 한 번 더(새 내용마다 1번 · 무한 반복 아님)")
    with tempfile.TemporaryDirectory() as td:
        base, f, led = live_base(td)
        RF.plan(base, live_rows(base), D("2026-11-18"))
        wjson(f, {"요약": [], "상세": [], "비고": "다른 빈 응답"})
        wjson(led, {"라이브정산": {"202601": "x", "202602": "2026-11-19T05:00:00"}})
        s = RF.plan(base, live_rows(base), D("2026-11-20"))
        assert s["표시"] == 1 and "202602" not in rjson(led)["라이브정산"], s
    ok("내용 지문이 새로우면 한 번 더 표시 · 전에 본 지문이면 R1 처럼 멈춤")


def ad_file(folder: Path, ym: str, data: dict) -> Path:
    p = wjson(folder / f"{ACCT}_광고정산_{ym}.json", data)
    age(p, "2026-11-10")
    return p


def r2_ads():
    print("[R2] 광고 subtotals 없음 → 앱이 _광고_다시받기.json 작성(2026 달만 · 2025 = D-328 제외) · 같은 결과면 목록에서 뺌")
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        ad = base / "검증자료" / "광고"
        for ym in ("202512", "202602"):
            ad_file(ad, ym, {"summary": {}, "items": []})
        wjson(ad / AD.REFETCH, {"다른계정": ["202603"]})
        rows = FC.ad_checks(ad)
        s = RF.plan(base, rows, D("2026-11-18"))
        assert rjson(ad / AD.REFETCH) == {"다른계정": ["202603"], ACCT: ["202602"]}, rjson(ad / AD.REFETCH)
        assert s["표시"] == 1 and s["대상 아님"] == 1, s
        old = [r for r in rows if r["기간"] == "202512"][0]
        assert old["다시 받기"] == FC.NO and "D-328" in old["설명"], old
        assert AD.refetch_months(ad, ACCT) == {"202602"}

        def call(method, path, body):                                    # 광고센터가 subtotals 없이 같은 응답(가짜)
            if "DailySettlement" in body["query"]:
                return {"data": {"getDailySettlement": {"summary": {}, "items": []}}}
            return {"data": {"getCampaignList": []}}
        wjson(ad / f"{ACCT}_광고.json", {"캠페인 없음": ["202512", "202602"]})
        for ym in ("202512", "202602"):
            (ad / f"{ACCT}_밀크런_{ym}.xlsx").write_bytes(b"m")
        got = AD.collect(call, lambda url: b"m", ad, ACCT, D("2026-02-01"), D("2026-03-10"))
        assert got["다시 받음"] == ["202602"], got
        s = RF.plan(base, FC.ad_checks(ad), D("2026-11-19"))
        assert s["같은 결과"] == 1 and ACCT not in rjson(ad / AD.REFETCH), (s, rjson(ad / AD.REFETCH))
        n = AD.collect(call, lambda url: b"m", ad, ACCT, D("2026-02-01"), D("2026-03-10"))
        assert n["다시 받음"] == [], "같은 결과 뒤엔 다시 안 받음"
    ok("다른 계정 줄 보존 + 202602 추가 · 202512 = 대상 아님(D-328) · 다시 받아도 subtotals 없음 = 확인 필요·다시받기 목록에서 빠짐·반복 없음")


def cost_row(p: Path) -> dict:
    return FC._row(FC.SUSPECT, "비용 리포트", ACCT, "2026-11-06", "2026-10-05~2026-10-11", "보관비", 0, 6660, FC.YES, p,
                   "리포트 자료 줄 0(머리줄만)인데 공제 6,660원")


def job(status=SJ.ST_DONE, attempts=1, report="보관비") -> SJ.Job:
    return SJ.Job(ACCT.replace("-", " ", 1), "로켓그로스", "주정산", report, "2026-10-05", "2026-10-11", "2026-11-06",
                  status=status, attempts=attempts, file="비용/x.xlsx")


def r3_cost_report():
    print("[R3] 비용 리포트 머리줄만 → 요청 기록 그 줄 = 요청예정·시도 0(다음 정기 단계가 요청 상한 안에서 요청·받기) · 다른 줄 그대로")
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        p = base / "파일" / "비용" / "x.xlsx"
        p.parent.mkdir(parents=True)
        p.write_bytes(b"header-only")
        age(p, "2026-11-07")
        other = job(report="입출고비")
        SJ.save_jobs(base / "_요청기록.json", [job(), other])
        s = RF.plan(base, [cost_row(p)], D("2026-11-18"))
        js = SJ.load_jobs(base / "_요청기록.json")
        assert s["표시"] == 1 and (js[0].status, js[0].attempts) == (SJ.ST_PLANNED, 0), (s, js[0])
        assert (js[1].status, js[1].attempts) == (SJ.ST_DONE, 1), "목록에 없는 줄은 그대로"

        js[0].status = SJ.ST_REQUESTED                                   # 다음 실행이 요청함(아직 못 받음)
        SJ.save_jobs(base / "_요청기록.json", js)
        s = RF.plan(base, [cost_row(p)], D("2026-11-19"))
        assert s["대기"] == 1 and SJ.load_jobs(base / "_요청기록.json")[0].status == SJ.ST_REQUESTED, "대기 중 = 되돌리지 않음"

        p.write_bytes(b"header-only")                                    # 받았는데 같은 내용
        rows = [cost_row(p)]
        s = RF.plan(base, rows, D("2026-11-20"))
        assert s["같은 결과"] == 1 and rows[0]["다시 받기"] == FC.NO, (s, rows)

        q = base / "파일" / "비용" / "y.xlsx"                             # 요청 기록에 없는 줄 = 확인 필요(조용히 넘기지 않음)
        q.write_bytes(b"z")
        lost = cost_row(q) | {"항목": "없는리포트"}
        s = RF.plan(base, [lost], D("2026-11-20"))
        assert s["길 없음"] == 1 and lost["판정"] == FC.CHECK and "요청 기록" in lost["설명"], (s, lost)
    ok("그 줄만 요청예정·시도 0 · 요청됨(대기) = 그대로 · 같은 내용 = 확인 필요 · 요청 기록에 없는 줄 = 확인 필요")


def r4_milk_review():
    print("[R4] 밀크런 읽기 실패 → 파일을 보관_다시받기/ 로 옮김(삭제 없음 · 다음 광고 단계가 그 달을 다시 받음) · 리뷰 이벤트 = 검증자료 매일 받음")
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        ad = base / "검증자료" / "광고"
        m = ad / f"{ACCT}_밀크런_202609.xlsx"
        m.parent.mkdir(parents=True)
        m.write_bytes(b"broken")
        rows = [FC._row(FC.SUSPECT, "밀크런", ACCT, "", "202609", "머리글", "", "", FC.YES, m, "칸 없음"),
                FC._row(FC.SUSPECT, "리뷰 이벤트", ACCT, "", "누계", "리뷰 캠페인", 4440, 0, FC.YES, base / "v.json", "x")]
        s = RF.plan(base, rows, D("2026-11-18"))
        assert s["표시"] == 1 and s["매일 받음"] == 1, s
        assert not m.exists() and (ad / RF.MILK_KEEP / m.name).read_bytes() == b"broken", "옮김(내용 그대로)"
        assert AD._left(ad, ACCT, [("202609", None, None)], set()) == 1, "그 달이 다시 받을 달로 셈"
        s = RF.plan(base, rows[:1], D("2026-11-19"))
        assert s["대기"] == 1, s
        m.write_bytes(b"broken")                                         # 다시 받았는데 같은 내용
        s = RF.plan(base, rows[:1], D("2026-11-20"))
        assert s["같은 결과"] == 1 and m.exists(), (s, "같은 결과 = 다시 옮기지 않음")
        assert len(list((ad / RF.MILK_KEEP).iterdir())) == 1
    ok("밀크런 = 보관_다시받기\\ 로 옮김 · 남은 달 1 · 대기 · 같은 내용 = 확인 필요(그대로 둠) · 리뷰 = 매일 다시 받음(할 일 없음)")


def r5_source_checks_flow():
    print("[R5] 정산 실행 끝 source_checks — 받기 의심 → 자동 재받기 표시 → 다시받을목록 쓰기 · 처리기록 한 줄")
    import settlement_download as TD
    recs: list = []
    log = SimpleNamespace(record=lambda *a, **k: recs.append(a), error=lambda *a, **k: recs.append(("ERR",) + a))
    with tempfile.TemporaryDirectory() as td:
        base, f, led = live_base(td)
        saved = (TD.BASE, TD.FILES, TD.LOG)
        try:
            TD.BASE, TD.FILES, TD.LOG = base, base / "파일", log
            TD.source_checks(web=False)
        finally:
            TD.BASE, TD.FILES, TD.LOG = saved
        assert list(rjson(led)["라이브정산"]) == ["202601"], rjson(led)
        assert not [r for r in recs if r[0] == "ERR"], recs
        line = [r for r in recs if r[1] == "자동 다시 받기"]
        assert line and "표시 1" in line[0][3], recs
    ok("실행 끝 1번에 받은 기록 202602 빠짐 · 처리기록 '자동 다시 받기 표시 1'")


def r6_cost_overwrite_keeps_old():
    print("[R6] 비용 리포트 다시 받기 = 같은 이름 덮어씀 → 덮어쓰기 전 값 수집일별 보관(D-335)")
    import settlement_download as TD
    from coupang_analytics import settlement_files as SF
    with tempfile.TemporaryDirectory() as td:
        costs = Path(td) / "비용"
        costs.mkdir()
        old = costs / "f.xlsx"
        old.write_bytes(b"old")
        age(old, "2026-11-07")
        raw = Path(td) / "raw.xlsx"
        raw.write_bytes(b"new")
        saved = (TD.COSTS, TD.LOG, SF.read_sheets, SF.assert_no_pii, SF.rg_cost_totals)
        log = SimpleNamespace(record=lambda *a, **k: None, saved=lambda *a, **k: None)
        try:
            TD.COSTS, TD.LOG = costs, log
            SF.read_sheets, SF.assert_no_pii, SF.rg_cost_totals = (lambda p: {}), (lambda s: None), (lambda s, e: {})
            TD._keep_cost(raw, job(report="보관비"), "A", "f.xlsx")
        finally:
            TD.COSTS, TD.LOG, SF.read_sheets, SF.assert_no_pii, SF.rg_cost_totals = saved
        assert old.read_bytes() == b"new"
        assert [p.name for p in (costs / "수집일별보관" / "f.xlsx").iterdir()] == ["2026-11-07.xlsx.gz"]
    ok("새 파일 = 같은 이름 · 11-07 값 = 비용\\수집일별보관\\f.xlsx\\2026-11-07.xlsx.gz")


def main() -> int:
    r1_live_empty()
    r1b_live_new_content()
    r2_ads()
    r3_cost_report()
    r4_milk_review()
    r5_source_checks_flow()
    r6_cost_overwrite_keeps_old()
    print("다시받을목록 자동 재받기 — 전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
