r"""정산서 '파일별 읽은 결과' 저장(D-419 ①·③ · T-188) 오프라인 검증 — 합성 파일만(네트워크·실자료 없음).

기대값 출처 = D-419: 원본 내용 지문 + 읽기 코드 판이 같을 때만 저장분 · 새로 받았거나 바뀐 파일만 읽음 · 정산서 금액(판정표가 들어간 값)은
저장하지 않음 · 저장분은 지워도 다시 만들어짐 · 값은 저장 없이 읽은 것과 같음(금액 변화 0).

    python tools/verify_settlement_read_store_offline.py
"""
from __future__ import annotations

import sys
import tempfile
import types
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools")]
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except AttributeError:
    pass

import openpyxl  # noqa: E402

from coupang_analytics import settlement_files as SF  # noqa: E402
from coupang_analytics import settlement_read_files as RF  # noqa: E402
from coupang_analytics import settlement_read_store as S  # noqa: E402
from coupang_analytics import settlement_statement_account as AC  # noqa: E402
from coupang_analytics import settlement_statement_cfs as CFS  # noqa: E402
from coupang_analytics import settlement_statement_context as CTX  # noqa: E402
from coupang_analytics import settlement_statement_scope as SCOPE  # noqa: E402
from coupang_analytics import settlement_statement_source as SRC  # noqa: E402
from coupang_analytics import statement_batch as SB  # noqa: E402

ACCT = "홍길동-길동상사-acc1"
ROOTS = ("settlement_files",)


def xlsx(p: Path, rows: list, title: str = "Sheet1") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    wb.active.title = title
    for r in rows:
        wb.active.append(r)
    wb.save(p)
    return p


def stored(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file()) if root.exists() else []


def t1_key_rules() -> None:
    with tempfile.TemporaryDirectory() as td:
        d, calls = Path(td), []
        f = d / "a.txt"
        f.write_text("하나", encoding="utf-8")

        def fn(p):
            calls.append(Path(p).name)
            return (Path(p).name, Path(p).read_text(encoding="utf-8"))

        assert S.read("k", f, fn, ROOTS) == ("a.txt", "하나") and S.note() == "" and not stored(d / "c"), "안 켜면 저장 없음"
        S.use(d / "c")
        for _ in range(3):
            assert S.read("k", f, fn, ROOTS) == ("a.txt", "하나")
        assert len(calls) == 2 and S.note() == "읽은 결과 저장 — 재사용 2개 · 새로 읽음 1개", (calls, S.note())
        f.write_text("둘", encoding="utf-8")                                            # 내용 바뀜 → 다시 읽음
        assert S.read("k", f, fn, ROOTS) == ("a.txt", "둘") and len(calls) == 3
        g = d / "b.txt"
        g.write_text("둘", encoding="utf-8")                                            # 내용 같아도 이름 다름(이름에서 계정·기간을 얻음)
        assert S.read("k", g, fn, ROOTS)[0] == "b.txt" and len(calls) == 4
        (d / "x").mkdir()
        h = d / "x" / "a.txt"
        h.write_text("둘", encoding="utf-8")                                            # 폴더만 다름 = 같은 파일
        assert S.read("k", h, fn, ROOTS) == ("a.txt", "둘") and len(calls) == 4
        assert S.read("k2", h, fn, ROOTS)[1] == "둘" and len(calls) == 5, "종류가 다르면 따로"
        for p in stored(d / "c"):                                                      # 저장분이 잘림·바뀜 → 다시 읽고 건수 표시
            p.write_bytes(p.read_bytes()[:-3] + b"zzz")
        S.use(d / "c")
        assert S.read("k", f, fn, ROOTS) == ("a.txt", "둘") and len(calls) == 6 and "깨진 저장분 1" in S.note(), S.note()
        assert S.read("k", f, fn, ROOTS)[1] == "둘" and len(calls) == 6, "깨진 것은 새로 쓴 뒤 다시 재사용"
    S.use(None)


def t2_errors_and_moving_file() -> None:
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        f = d / "a.txt"
        f.write_text("1", encoding="utf-8")
        S.use(d / "c")

        def boom(p):
            raise SF.SettlementParseError("못 읽음")

        for _ in range(2):
            try:
                S.read("k", f, boom, ROOTS)
                raise AssertionError("예외가 그대로 나와야 함")
            except SF.SettlementParseError:
                pass
        assert not stored(d / "c"), "읽기 오류는 저장하지 않음"

        def moving(p):
            v = p.read_text(encoding="utf-8")
            p.write_text("읽는 중 바뀜", encoding="utf-8")
            return v

        assert S.read("k", f, moving, ROOTS) == "1" and not stored(d / "c"), "읽는 사이 바뀐 파일은 저장하지 않음"
        blocked = d / "c2"
        blocked.write_text("폴더 자리에 파일", encoding="utf-8")                           # 저장 실패(폴더 못 만듦) = 값은 그대로·건수 안내
        S.use(blocked)
        assert S.read("k", f, lambda p: 7, ROOTS) == 7 and "저장 못 함 1" in S.note(), S.note()
    S.use(None)


def t3_code_version() -> None:
    c = S.module_closure(("settlement_read_files", "settlement_files"))
    assert {"settlement_files", "settlement_parse", "settlement_read_files", "settlement_read_store"} <= set(c), c
    led = S.module_closure(("settlement_statement_scope",))
    assert {"workbook", "workbook_sales", "workbook_meta", "workbook_index", "workbook_common"} <= set(led), led
    with tempfile.TemporaryDirectory() as td:                                          # 이어서 import 하는 모듈까지(함수 안 import 포함)
        d = Path(td)
        (d / "a.py").write_text("from . import b\ndef f():\n    from .c import x\n", encoding="utf-8")
        (d / "b.py").write_text("import coupang_analytics.e\nfrom coupang_analytics import d as D\nfrom coupang_analytics.g import h\n", encoding="utf-8")
        for n in "cdegz":
            (d / f"{n}.py").write_text("", encoding="utf-8")
        assert S.module_closure(("a",), d) == ["a", "b", "c", "d", "e", "g"]
    with tempfile.TemporaryDirectory() as td:
        d, calls = Path(td), []
        f = d / "a.txt"
        f.write_text("1", encoding="utf-8")
        S.use(d / "c")
        real = S.code_version
        try:
            S.code_version = lambda roots: "a" * 64
            S.read("k", f, lambda p: calls.append(1) or 1, ROOTS)
            S.read("k", f, lambda p: calls.append(1) or 1, ROOTS)
            S.code_version = lambda roots: "b" * 64                                     # 읽기 코드가 바뀜 → 다시 읽어 덮어씀
            assert S.read("k", f, lambda p: calls.append(1) or 2, ROOTS) == 2 and len(calls) == 2
            assert len(stored(d / "c")) == 1
        finally:
            S.code_version = real
        exe = d / "app.exe"                                                            # 배포 exe = exe 내용이 코드 판
        keep = sys.executable
        got = []
        sys.frozen = True  # type: ignore[attr-defined]
        try:
            for body in (b"v1", b"v2"):
                exe.write_bytes(body)
                sys.executable = str(exe)
                S.code_version.cache_clear()
                got.append(S.code_version(ROOTS))
        finally:
            del sys.frozen  # type: ignore[attr-defined]
            sys.executable = keep
            S.code_version.cache_clear()
        assert got[0] != got[1], got
    S.use(None)


WING = list(SF._WING_COLS.values()) + ["서비스이용율(%,VAT별도)"]


def wing_row(pid, rate, sales=1000, fee=100):
    v = {"주문번호": "1", "상품 ID": pid, "상품명": "컵", "옵션 ID": "77", "옵션명": "흰색", "판매가": sales, "판매수량": 1, "환불수량": 0,
         "판매액": sales, "판매자 할인쿠폰(A+B)": 0, "판매수수료": fee, "마이샵수수료할인": 0, "정산금액": sales - fee,
         "구매확정일": "2026-08-03", "구매확정(출고)유형": "확정", "정산예정일": "2026-08-25", "서비스이용율(%,VAT별도)": rate}
    return [v[h] for h in WING]


RG = ["정산유형", *SF._RG_COLS.values()]


def rg_row(settle=890):
    v = {"정산유형": "WEEKLY", "주문ID": "9", "등록상품 ID": "501", "등록상품명": "컵", "옵션ID": "77", "옵션명": "흰색", "판매가(A)": 1000,
         "판매수량(B)": 1, "판매액(A*B)": 1000, "매출금액(A*B-C)": 1000, "판매자할인쿠폰(D+E)": 0, "판매수수료": 100, "판매수수료 VAT": 10,
         "정산대상액": settle, "매출인식일": "2026-08-04", "거래유형": "판매", "정산주기(종료일)": "2026-08-09"}
    return [v[h] for h in RG]


def settle_dir(d: Path) -> Path:
    b = d / "정산"
    xlsx(b / "파일" / f"{ACCT}_20260825_윙_주정산_주문상세_20260801-20260807.xlsx", [WING, wing_row("501", 10.8), wing_row("502", 7.8), wing_row("503", 5.8)])
    xlsx(b / "파일" / f"{ACCT}_20260901_로켓그로스_주정산_판매수수료_20260803-20260809.xlsx", [[], RG, rg_row()])
    ad = b / "검증자료" / "광고"
    xlsx(ad / f"{ACCT}_매출성장광고_202608.xlsx", [["날짜", "캠페인 ID", "광고유형", "광고집행 옵션ID", "광고비"], [20260801, 11, "x", "77", 12.5],
                                          [20260801, None, "x", "77", 9], [20260802, 11, "x", None, "모름"], [None] * 5, [20260803, "12", "x", 88, 3]])
    xlsx(ad / f"{ACCT}_밀크런_202608.xlsx", [["밀크런번호", "총 합계금액", "취소수수료"], [900, "14,960", None], [901, "-2,400", "100"], [None, "5", None]])
    xlsx(b / "파일" / "비용" / f"{ACCT}_20260901_로켓그로스_주정산_보관비_20260803-20260809.xlsx",
         [["보관비"], [""], ["정산주기(종료일)", "합계", "세액", "최종비용"], ["2026-08-09", 148, 16, 164], [],
          ["정산유형", "정산주기(종료일)", "매출인식일", "등록상품 ID", "비용"], ["", "", "", "", "최종비용"],
          ["WEEKLY", "2026-08-09", "2026-08-04", "16131930801", 100], ["WEEKLY", "2026-08-09", "2026-08-05", "16131928633", 48]], "보관비")
    xlsx(b / "파일" / "비용" / f"{ACCT}_20260901_로켓그로스_주정산_재고-손실-보상_20260803-20260809.xlsx",
         [["정산주기(종료일)", "옵션ID", "등록상품명", "발생일", "보상 금액"], ["2026-08-09", "77", "컵", "2026-08-06", 2500]], "재고 손실 보상")
    return b


def read_all(b: Path, judge: dict) -> dict:
    files, unj = CTX._settle_files(b, judge)
    return {"파일": {k: [vars(x) | {"rows": [vars(r) for r in x.rows]} for x in v] for k, v in files.items()}, "요율": dict(unj),
            "rg": {k: dict(v) for k, v in SRC.rg_file_targets(b).items()}, "광고": AC.ad_files(b, ACCT),
            "밀크런": AC.milk_rows(b, ACCT), "비용": CFS.read_costs(b, ACCT)}


def t4_same_values() -> None:
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        b = settle_dir(d)
        off = read_all(b, {})
        assert off["요율"] == {"acc1": {"502", "503"}} and off["rg"] == {"acc1": {("2026-08-03", "2026-08-09"): 890}}, (off["요율"], off["rg"])
        assert off["광고"][0] == [(20260801, 11, "77", 12.5), (20260802, 11, None, 0.0), (20260803, "12", 88, 3.0)], off["광고"]
        assert off["밀크런"] == [("900", 14960.0), ("901", -2300.0)], off["밀크런"]
        logi, comp, starts = off["비용"]
        assert [x[:2] for x in logi["2026-08-09"]] == [("2026-08-04", "16131930801"), ("2026-08-05", "16131928633")]
        assert round(sum(x[2] for x in logi["2026-08-09"]), 6) == 164 and starts == {"2026-08-09": "2026-08-03"}
        assert comp == {"2026-08-09": [("77", "2026-08", 2500.0)]}, comp
        S.use(d / "c")
        assert read_all(b, {}) == off
        made = len(stored(d / "c"))
        S.use(d / "c")
        assert read_all(b, {}) == off, "저장분으로 읽은 값 = 원본에서 읽은 값"
        assert "새로 읽음 0개" in S.note() and len(stored(d / "c")) == made and made == 7, (S.note(), made)
        assert isinstance(off["파일"]["acc1"][0]["rows"][0]["recognized"], date)
        got = read_all(b, {"502": {"가전": True}})                                       # 판정표만 바뀜 → 저장분 그대로 쓰되 새 판정표로 거름(판정은 저장 안 함)
        assert got["요율"] == {"acc1": {"503"}} and "새로 읽음 0개" in S.note(), got["요율"]
        p = b / "파일" / f"{ACCT}_20260901_로켓그로스_주정산_판매수수료_20260803-20260809.xlsx"
        xlsx(p, [[], RG, rg_row(), rg_row()])                                           # 다시 받아 내용이 바뀐 파일만 다시 읽음
        S.use(d / "c")
        assert SRC.rg_file_targets(b)["acc1"] == {("2026-08-03", "2026-08-09"): 1780} and "새로 읽음 1개" in S.note(), S.note()
        one = RF.settle_file(p)
        one.rows.clear()                                                               # 받은 값을 고쳐도 저장분은 그대로
        assert len(RF.settle_file(p).rows) == 2
    S.use(None)


def t5_ledger() -> None:
    real, calls = SCOPE._ledger_blocks, []
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        for name, body in ((SCOPE.MASTER, "m"), ("쿠팡데이타분석_통계_261101.xlsx", "s")):
            (d / name).write_bytes(body.encode())
        SCOPE._ledger_blocks = lambda p: calls.append(p.name) or {"acc1": {"11|12"} if p.name == SCOPE.MASTER else {"13"}}
        try:
            S.use(d / "c")
            assert SCOPE.ledger_vids(d) == SCOPE.ledger_vids(d) == {"acc1": {"11", "12", "13"}} and len(calls) == 2, calls
            (d / SCOPE.MASTER).write_bytes(b"m2")                                        # 지금 결과 엑셀만 바뀜 = 그것만 다시
            SCOPE.ledger_vids(d)
            assert calls[2:] == [SCOPE.MASTER], calls
        finally:
            SCOPE._ledger_blocks = real
            S.use(None)


def t6_batch_turns_on_and_off() -> None:
    seen: list = []
    mod = types.ModuleType("_t188_fake_job")

    def run_job(opts, on_log):
        f = Path(opts["managed_output"]) / "a.txt"
        seen.append([S.read("k", f, lambda p: p.read_text(), ROOTS) for _ in range(2)])
        return {"ok": [], "skipped": [], "files": [], "abort": None}

    mod.run_job = run_job  # type: ignore[attr-defined]
    sys.modules[mod.__name__] = mod
    try:
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "a.txt").write_text("v")
            logs: list = []
            SB._job({"module": mod.__name__, "managed_output": td}, logs.append)
            assert seen == [["v", "v"]] and logs == ["읽은 결과 저장 — 재사용 1개 · 새로 읽음 1개"], (seen, logs)
            assert len(stored(Path(td) / "정산서" / "_읽은결과")) == 1 and S.note() == "", "끝나면 꺼짐"
            SB._job({"module": mod.__name__, "managed_output": td}, logs.append)           # 다음 작업(다른 자식)도 재사용
            assert logs[-1] == "읽은 결과 저장 — 재사용 2개 · 새로 읽음 0개", logs
    finally:
        del sys.modules[mod.__name__]


def t7_export_skips_store() -> None:
    import output_export as OE
    with tempfile.TemporaryDirectory() as td:
        for rel in ("정산서/_읽은결과/정산파일/abc", "정산서/입력/a.json", "정산/b.json"):
            p = Path(td) / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x")
        assert sorted(OE.walk_files(Path(td))) == ["정산/b.json", "정산서/입력/a.json"]


def main() -> None:
    for t in (t1_key_rules, t2_errors_and_moving_file, t3_code_version, t4_same_values, t5_ledger, t6_batch_turns_on_and_off, t7_export_skips_store):
        try:
            t()
        finally:
            S.use(None)
        print(f"{t.__name__} OK")
    print("정산서 파일별 읽은 결과 저장 오프라인 검증 통과")


if __name__ == "__main__":
    main()
