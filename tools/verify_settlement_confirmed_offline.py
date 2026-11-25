r"""쿠팡 확정 장부(D-419 ② · T-188) 오프라인 검증 — 합성 자료만(네트워크·실자료·실제 output 폴더 없음).

기대값 출처 = D-419: 계정ID × 판매 달 · 건별(지급 줄 전 칸·판매 줄·비용 줄·광고 청구 원문)·월별(계정·채널 합계·확정 여부·사유) ·
닫는 조건 = 정산일 지남 + 보류 0 + 예정 줄 0 + 이월 물류비 0 + 정산 파일 합 = 지급 줄 + 서로 다른 날 받은 값 2번 같음 ·
닫힌 뒤 다르면 다시 열고 옛 값 보관 + '확인 필요' · 닫힌 달 = 장부 값 · 안 닫힌 달 = 원본 · 두 길의 값 같음 · 정산서 금액은 저장 안 함 ·
구매자 이름 없음 · 2025 판매 달 없음(D-328).

    python tools/verify_settlement_confirmed_offline.py
"""
from __future__ import annotations

import copy
import gzip
import json
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

from coupang_analytics import settlement_confirmed as C  # noqa: E402
from coupang_analytics import settlement_confirmed_read as CR  # noqa: E402
from coupang_analytics import settlement_files as SF  # noqa: E402
from coupang_analytics import settlement_ledger as SL  # noqa: E402
from coupang_analytics import settlement_read_store as READS  # noqa: E402
from coupang_analytics import settlement_statement_account as AC  # noqa: E402
from coupang_analytics import settlement_statement_cfs as CFS  # noqa: E402
from coupang_analytics import settlement_statement_context as CTX  # noqa: E402
from coupang_analytics import settlement_statement_source as SRC  # noqa: E402
from coupang_analytics import statement_batch as SB  # noqa: E402

ACCT, AID = "홍길동-길동상사-acc1", "acc1"
D1, D2, D3 = "2026-11-18", "2026-11-19", "2026-11-20"
WEEK = ("2026-08-03", "2026-08-09")
RG_FILE = "20260901_로켓그로스_주정산_판매수수료_20260803-20260809.xlsx"
WING_FILE = "20260825_윙_주정산_주문상세_20260801-20260807.xlsx"
COST_FILE = "20260901_로켓그로스_주정산_보관비_20260803-20260809.xlsx"
COMP_FILE = "20260901_로켓그로스_주정산_재고-손실-보상_20260803-20260809.xlsx"


def wjson(p: Path, data) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def xlsx(p: Path, rows: list, title: str = "Sheet1") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    wb.active.title = title
    for r in rows:
        wb.active.append(r)
    wb.save(p)
    wb.close()
    return p


def rg_pay(ratio, payable, final, pay_day, week=WEEK, **kw) -> dict:
    return {"정산일": pay_day, "기간 시작": week[0], "기간 끝": week[1], "지급비율": ratio, "최종지급액": final, "totalPayableAmount": payable,
            "totalAdditionalDeductionAmount": 0, "totalFinalCfsFeeDeductionAmount": payable - final, C.CARRY: 0,
            "totalCfsInventoryCompensationAmount": 0, "totalSalesAdjustment": 0, **kw}


def wing_pay(ratio, paid, pay_day, start="2026-08-01", end="2026-08-07", **kw) -> dict:
    ded = kw.pop("ded", 0)
    return {"정산일": pay_day, "기간 시작": start, "기간 끝": end, "지급비율": ratio, "최종지급액": paid - ded, "지급상태": "DONE", "실지급": True,
            "차감 사유": [{"사유": "광고비", "금액": ded}, {"사유": "서버이용료", "금액": 0}], "targetAmount": 2700, "paidAmount": paid,
            "pendingAmount": 0, "totalDeductionAmount": ded, **kw}


RG_ROWS = [rg_pay(70, 623, 600, "2026-09-01"), rg_pay(30, 267, 200, "2026-10-01")]
WING_ROWS = [wing_pay(70, 1890, "2026-08-25", ded=100), wing_pay(30, 810, "2026-10-01", end="2026-08-31")]
RG_HEAD = ["정산유형", *SF._RG_COLS.values()]
WING_HEAD = [*SF._WING_COLS.values(), "서비스이용율(%,VAT별도)"]


def rg_line(settle=890, gross=1000, fee=100) -> dict:
    return {"정산유형": "WEEKLY", "주문ID": "9", "등록상품 ID": "501", "등록상품명": "컵", "옵션ID": "77", "옵션명": "흰색", "판매가(A)": gross,
            "판매수량(B)": 1, "판매액(A*B)": gross, "매출금액(A*B-C)": gross, "판매자할인쿠폰(D+E)": 0, "판매수수료": fee,
            "판매수수료 VAT": gross - fee - settle, "정산대상액": settle, "매출인식일": "2026-08-04", "거래유형": "판매", "정산주기(종료일)": "2026-08-09"}


def wing_line(pid, rate) -> dict:
    return {"주문번호": pid, "상품 ID": pid, "상품명": "컵", "옵션 ID": "77", "옵션명": "흰색", "판매가": 1000, "판매수량": 1, "환불수량": 0, "판매액": 1000,
            "판매자 할인쿠폰(A+B)": 0, "판매수수료": 100, "마이샵수수료할인": 0, "정산금액": 900, "구매확정일": "2026-08-03",
            "구매확정(출고)유형": "확정", "정산예정일": "2026-08-25", "서비스이용율(%,VAT별도)": rate}


def rg_xlsx(p: Path, extra_col: bool = False, **kw) -> Path:
    """로켓그로스 정산 파일 — extra_col = 쿠팡이 엑셀 가운데에 새 칸을 끼운 형식(실측 '개별포장 상품 사이즈')."""
    head, line = list(RG_HEAD), rg_line(**kw)
    if extra_col:
        head.insert(3, "개별포장 상품 사이즈")
        line["개별포장 상품 사이즈"] = "XS"
    return xlsx(p, [[], head, [line[h] for h in head]], "주문내역, 판매수수료")


def cost_xlsx(p: Path, amounts=(100, 48), extra: bool = False) -> Path:
    x = ["크기"] if extra else []
    return xlsx(p, [["보관비"], [""], ["정산주기(종료일)", "합계", "세액", "최종비용"], ["2026-08-09", sum(amounts), 16, sum(amounts) + 16], [],
                    ["정산유형", "정산주기(종료일)", "매출인식일", *x, "등록상품 ID", "등록상품명", "비용"], ["", "", "", *x, "", "", "최종비용"],
                    *(["WEEKLY", "2026-08-09", f"2026-08-0{4 + i}", *x, f"1613193080{i}", "컵", a] for i, a in enumerate(amounts))], "보관비")


def make(base: Path, *, days=(D1,), rg=None, wing=None, acct=ACCT, coming=None) -> Path:
    """계정 하나 · 2026-08 판매 — 닫는 조건을 모두 만족하는 자료(관찰 날만 부족)."""
    wjson(base / "쿠팡지급내역" / f"{acct}_로켓그로스.json", RG_ROWS if rg is None else rg)
    wjson(base / "쿠팡지급내역" / f"{acct}_윙.json", WING_ROWS if wing is None else wing)
    rg_xlsx(base / "파일" / f"{acct}_{RG_FILE}")
    xlsx(base / "파일" / f"{acct}_{WING_FILE}", [WING_HEAD, *([wing_line(p, r)[h] for h in WING_HEAD] for p, r in (("501", 10.8), ("502", 7.8), ("503", 5.8)))])
    cost_xlsx(base / "파일" / "비용" / f"{acct}_{COST_FILE}")
    xlsx(base / "파일" / "비용" / f"{acct}_{COMP_FILE}", [["정산주기(종료일)", "옵션ID", "등록상품명", "발생일", "보상 금액"],
                                                   ["2026-08-09", "77", "컵", "2026-08-06", 2500]], "재고 손실 보상")
    wjson(base / "검증자료" / "광고" / f"{acct}_광고정산_202608.json",
          {"summary": {"rocketGrowth": {"totalFinalAmount": 110}, "nonRod": None}, "items": [{"date": 20260801, "campaignId": 11, "billableAmount": 100}]})
    got(base, acct, *days)
    if coming is not None:
        p = base / "정산예정기록" / "2026-11.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("".join(json.dumps({"수집일": d, "계정": acct, "채널": ch, "묶음": "1", **r}, ensure_ascii=False) + "\n" for d, ch, r in coming), encoding="utf-8")
    return base


def got(base: Path, acct: str, *days) -> None:
    """정산현황을 실제로 받은 날 기록(정산현황_원문)."""
    for d in days:
        p = base / C.RG_RAW_DIRNAME / acct / f"{d}.json.gz"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(gzip.compress(b"{}"))


def run(base: Path, root: Path, day: str) -> tuple[dict, dict]:
    """장부 갱신 한 번 → (2026-08 장부 기록, 일 함수 결과). 로그는 버림."""
    res = C.run_job({"settle_dir": str(base), "out": str(root), "basis": day}, lambda m: None)
    return C.load_index(root)["계정"].get(AID, {}).get("2026-08", {}), res


def closed(td: str) -> tuple[Path, Path, dict]:
    base, root = make(Path(td) / "정산"), Path(td) / "정산확정"
    run(base, root, D1)
    got(base, ACCT, D2)
    e, _res = run(base, root, D2)
    assert e["상태"] == CR.CLOSED, e
    return base, root, e


# ── 닫기 ──
def t1_two_different_collect_days() -> None:
    with tempfile.TemporaryDirectory() as td:
        base, root = make(Path(td) / "정산"), Path(td) / "정산확정"
        e, res = run(base, root, D1)
        assert e["상태"] == C.WATCH and e["첫수집일"] == D1 and not e["확정일"] and res["skipped"] == [] and res["abort"] is None, (e, res)
        assert CR.use(root) == 0, "관찰 = 아직 장부 값을 안 씀"
        for day in (D1, D2, D3):                                                       # 배치는 또 돌았지만 새로 받은 날이 없음 → 안 닫음
            assert run(base, root, day)[0]["상태"] == C.WATCH, day
        got(base, ACCT, D2 + "_부분")                                                    # 중간에 멈춘 부분본 = 받은 날 아님
        assert run(base, root, D3)[0]["상태"] == C.WATCH
        got(base, ACCT, D2)
        e, res = run(base, root, D3)                                                   # 다른 날 다시 받아 같은 값 → 닫힘(확정일 = 수집일)
        assert e["상태"] == CR.CLOSED and e["확정일"] == D2 and e["사유"] == [] and "2026-08 닫힘 1/1" in res["ok"], (e, res)
        assert CR.use(root) == 1
        CR.use(None)
    print("t1 다른 수집일 2번 같은 값 → 닫힘(같은 날·부분본·안 받은 날 = 관찰 아님) OK")


def t2_why_not_closed() -> None:
    cases = {
        "정산일 안 지난 줄 1": {"rg": [RG_ROWS[0], rg_pay(30, 267, 200, D1)]},
        "보류 줄 1": {"wing": [WING_ROWS[0], {**WING_ROWS[1], "지급상태": "PENDING"}]},
        "이월 물류비 8,194": {"rg": [RG_ROWS[0], {**RG_ROWS[1], C.CARRY: 8194.0}]},
        "로켓그로스 2026-08-03~2026-08-09 파일 890 · 지급 줄 623": {"rg": RG_ROWS[:1]},
        "윙 파일 2,700 · 지급 줄 1,890": {"wing": WING_ROWS[:1]},
        "예정 줄 1": {"coming": [(D1, "로켓그로스", rg_pay(30, 0, 0, "2026-11-25"))]},
        "수집 기록 없음": {"days": ()},
    }
    for want, kw in cases.items():
        with tempfile.TemporaryDirectory() as td:
            base, root = make(Path(td) / "정산", **kw), Path(td) / "정산확정"
            e, res = run(base, root, D1)
            assert e["상태"] == C.OPEN and any(want in w for w in e["사유"]) and len(e["사유"]) == 1, (want, e)
            assert not CR.case_path(root, AID, "2026-08").exists() and res["skipped"] == [], "못 닫는 달 = 사유만(확인 필요 아님)"
            if kw.get("days") != ():
                got(base, ACCT, D2)
            assert run(base, root, D2)[0]["상태"] == (C.WATCH if want.startswith("정산일") else C.OPEN), want
    with tempfile.TemporaryDirectory() as td:                                          # 지난 예정 기록 = 수집일 전에 지급된 줄 → 예정 아님
        base = make(Path(td) / "정산", coming=[("2026-09-30", "로켓그로스", RG_ROWS[1])])
        assert run(base, Path(td) / "c", D1)[0]["상태"] == C.WATCH
    with tempfile.TemporaryDirectory() as td:                                          # 끝나지 않은 판매 달 · 2025 판매 달
        nov = ("2026-11-02", "2026-11-08")
        base = make(Path(td) / "정산", rg=[*RG_ROWS, rg_pay(100, 0, 0, "2026-11-10", nov), rg_pay(100, 5, 5, "2026-01-05", ("2025-12-01", "2025-12-07"))])
        run(base, Path(td) / "c", D1)
        book = C.load_index(Path(td) / "c")["계정"][AID]
        assert sorted(book) == ["2026-08", "2026-11"] and book["2026-11"]["사유"] == ["판매 달이 안 끝남"], book
    print("t2 못 닫는 사유 7가지 · 지난 예정 기록 · 안 끝난 달 · 2025 판매 달 제외 OK")


def t3_body_is_coupang_original() -> None:
    with tempfile.TemporaryDirectory() as td:
        base, root, e = closed(td)
        b = CR.decode(CR.case_path(root, AID, "2026-08").read_bytes())
        assert b["계정ID"] == AID and b["판매달"] == "2026-08" and b[CR.PAY] == {"윙": WING_ROWS, "로켓그로스": RG_ROWS}, b[CR.PAY]
        assert set(b[CR.SALE]) == {RG_FILE, WING_FILE} and set(b[CR.COST]) == {COST_FILE, COMP_FILE}
        assert b[CR.SALE][RG_FILE]["칸"] == SF.read_sheets(base / "파일" / f"{ACCT}_{RG_FILE}"), "판매 줄 = 원문 칸 그대로"
        assert b[CR.COST][COST_FILE]["칸"]["보관비"][-1][-1] == 48
        assert b[CR.AD]["광고정산_202608.json"]["칸"]["summary"]["rocketGrowth"]["totalFinalAmount"] == 110
        assert e["파일"][CR.SALE][RG_FILE] == b[CR.SALE][RG_FILE]["원본지문"]
        cell = {"a": [date(2026, 8, 3), 1, 1.5, None, "1"]}                              # 날짜 칸도 형 그대로
        assert CR.decode(CR.encode(cell)) == cell and CR.encode(cell) == CR.encode(copy.deepcopy(cell))
    with tempfile.TemporaryDirectory() as td:                                          # 구매자명 칸이 있는 파일 = 장부에 안 넣음
        base, root = make(Path(td) / "정산"), Path(td) / "c"
        head = [*WING_HEAD, "구매자명"]
        xlsx(base / "파일" / f"{ACCT}_{WING_FILE}", [head, *([{**wing_line(p, 10.8), "구매자명": "가짜이름"}[h] for h in head] for p in ("501", "502", "503"))])
        e, _res = run(base, root, D1)
        assert e["상태"] == C.OPEN and "구매자명" in e["사유"][0] and not CR.case_path(root, AID, "2026-08").exists(), e
        assert not any("가짜이름".encode() in p.read_bytes() for p in root.rglob("*") if p.is_file())
    print("t3 건별 = 쿠팡 원문 값 그대로 · 구매자명 칸 = 못 닫음 OK")


# ── 닫힌 뒤 ──
def t4_reopen_on_change() -> None:
    changed = [RG_ROWS[0], {**RG_ROWS[1], "최종지급액": 8394, "totalFinalCfsFeeDeductionAmount": -8127}]
    with tempfile.TemporaryDirectory() as td:
        base, root, _e = closed(td)
        old = CR.case_path(root, AID, "2026-08").read_bytes()
        wjson(base / "쿠팡지급내역" / f"{ACCT}_로켓그로스.json", changed)
        got(base, ACCT, D3)
        e, res = run(base, root, D3)
        assert e["상태"] == C.WATCH and e["첫수집일"] == D3 and not e["확정일"], e
        h = e["이력"][-1]
        assert h["종류"] == C.REOPENED and h["확정일"] == D2 and (root / h["보관"]).read_bytes() == old, h
        assert len(res["skipped"]) == 1 and {"id", "account", "amount", "reason"} <= set(res["skipped"][0]), res["skipped"]
        line = res["skipped"][0]
        assert line["id"] == AID and line["account"] == ACCT and line["amount"] == 8194, line
        assert "2026-08 확정했던 쿠팡 값이 바뀜" in line["reason"] and "최종지급액 200→8,394" in line["reason"] and "2026-10-01" in line["reason"], line
        assert CR.use(root) == 0, "다시 열린 달 = 원본"
        assert len(run(base, root, D3)[1]["skipped"]) == 1, "다시 닫힐 때까지 매 배치 '확인 필요'"
        got(base, ACCT, "2026-11-21")
        e, res = run(base, root, "2026-11-21")                                         # 바뀐 값이 다른 날 또 같음 → 다시 닫힘 · 이력·옛 값은 남음
        assert e["상태"] == CR.CLOSED and e["확정일"] == "2026-11-21" and res["skipped"] == [] and (root / h["보관"]).is_file(), e
        wjson(base / "쿠팡지급내역" / f"{ACCT}_로켓그로스.json", RG_ROWS)                        # 같은 달이 두 번째로 바뀌어도 앞 보관본을 덮지 않음
        e, _res = run(base, root, "2026-11-22")
        assert [x["종류"] for x in e["이력"]] == [C.REOPENED] * 2 and len({x["보관"] for x in e["이력"]}) == 2 and (root / h["보관"]).read_bytes() == old
    print("t4 닫힌 뒤 값이 바뀜 → 다시 열림 + 옛 값 보관 + 확인 필요(다시 닫힐 때까지) OK")


def t5_reopen_kinds_and_not() -> None:
    def rows(p, data):
        return lambda b: wjson(b / "쿠팡지급내역" / f"{ACCT}_{p}.json", data)

    reopen = {
        "줄 사라짐": rows("윙", WING_ROWS[:1]),
        "새 줄": rows("윙", [*WING_ROWS, wing_pay(100, 0, "2026-11-12", end="2026-08-31", pendingAmount=50, 최종지급액=50)]),
        "판매 줄 파일 값 바뀜": lambda b: rg_xlsx(b / "파일" / f"{ACCT}_{RG_FILE}", settle=880),
        "비용 줄 파일 값 바뀜": lambda b: cost_xlsx(b / "파일" / "비용" / f"{ACCT}_{COST_FILE}", (100, 49)),
        "비용 줄 파일 사라짐": lambda b: (b / "파일" / "비용" / f"{ACCT}_{COST_FILE}").unlink(),
        "비용 줄 새 파일": lambda b: cost_xlsx(b / "파일" / "비용" / f"{ACCT}_{COST_FILE.replace('보관비', '반출비')}"),
        "광고 청구 파일 값 바뀜": lambda b: wjson(b / "검증자료" / "광고" / f"{ACCT}_광고정산_202608.json", {"summary": {}, "items": []}),
        "예정 줄 1": lambda b: make(b, days=(D2,), coming=[(D2, "윙", wing_pay(30, 5, "2026-12-01"))]),
    }
    for want, change in reopen.items():
        with tempfile.TemporaryDirectory() as td:
            base, root, _e = closed(td)
            change(base)
            got(base, ACCT, D3)
            e, res = run(base, root, D3)
            assert e["상태"] != CR.CLOSED and any(want in w for w in e["이력"][-1]["바뀐 것"]) and len(res["skipped"]) == 1, (want, e)
            assert (root / e["이력"][-1]["보관"]).is_file(), want
    wide = [{**r, "새칸": [{"a": 1}]} for r in RG_ROWS]
    same = {
        "차감 사유 순서": (rows("윙", [{**r, "차감 사유": r["차감 사유"][::-1]} for r in WING_ROWS]), 0),
        "정수·실수": (rows("윙", [{**r, "paidAmount": float(r["paidAmount"])} for r in WING_ROWS]), 0),
        "줄에 새 칸": (rows("로켓그로스", wide), 1),
        "엑셀에 새 칸": (lambda b: rg_xlsx(b / "파일" / f"{ACCT}_{RG_FILE}", extra_col=True), 1),
        "비용 엑셀에 새 칸": (lambda b: cost_xlsx(b / "파일" / "비용" / f"{ACCT}_{COST_FILE}", extra=True), 1),
        "광고 새 칸": (lambda b: wjson(b / "검증자료" / "광고" / f"{ACCT}_광고정산_202608.json",
                                  {"summary": {"rocketGrowth": {"totalFinalAmount": 110.0, "vat": 10}, "nonRod": None}, "subtotals": [],
                                   "items": [{"date": 20260801, "campaignId": 11, "billableAmount": 100}]}), 1),
    }
    for name, (change, widened) in same.items():
        with tempfile.TemporaryDirectory() as td:
            base, root, e0 = closed(td)
            change(base)
            got(base, ACCT, D3)
            e, res = run(base, root, D3)
            assert e["상태"] == CR.CLOSED and e["확정일"] == D2 and e["수집일"] == D3 and res["skipped"] == [], (name, e)
            assert [h["종류"] for h in e["이력"]] == [C.WIDENED] * widened and all((root / h["보관"]).is_file() for h in e["이력"]), (name, e["이력"])
            assert two_ways(base, root), name                                          # 새 칸을 나중에 읽어도 원본과 같게 장부도 새 원문
            assert e["본문"] != e0["본문"], name
    with tempfile.TemporaryDirectory() as td:                                          # 관찰 중 다시 받은 엑셀에 칸만 더해짐 = 같은 값 → 닫힘
        base, root = make(Path(td) / "정산"), Path(td) / "c"
        run(base, root, D1)
        rg_xlsx(base / "파일" / f"{ACCT}_{RG_FILE}", extra_col=True)
        got(base, ACCT, D2)
        e, _res = run(base, root, D2)
        assert e["상태"] == CR.CLOSED and e["이력"] == [] and two_ways(base, root), e
    with tempfile.TemporaryDirectory() as td:                                          # 관찰 중 값이 바뀜 = 관찰을 새로 시작(확인 필요 아님)
        base, root = make(Path(td) / "정산"), Path(td) / "c"
        run(base, root, D1)
        wjson(base / "쿠팡지급내역" / f"{ACCT}_로켓그로스.json", [RG_ROWS[0], {**RG_ROWS[1], "최종지급액": 199, "totalFinalCfsFeeDeductionAmount": 68}])
        got(base, ACCT, D2)
        e, res = run(base, root, D2)
        assert (e["상태"], e["첫수집일"], e["이력"], res["skipped"]) == (C.WATCH, D2, [], []), e
    print(f"t5 다시 여는 것 {len(reopen)}가지 · 안 여는 것(순서·수 모양·새 칸·계정 배치) {len(same)}가지 OK")


def t6_rename_gone_broken() -> None:
    with tempfile.TemporaryDirectory() as td:                                          # 계정 이름이 바뀌어도(파일 이름 앞) 같은 달
        base, root, _e = closed(td)
        new = "홍길동[임꺽정]-길동상사-acc1"
        for p in [*base.rglob(f"{ACCT}_*"), base / C.RG_RAW_DIRNAME / ACCT]:
            p.rename(p.with_name(p.name.replace(ACCT, new)))
        e, res = run(base, root, D3)
        assert e["상태"] == CR.CLOSED and e["계정명"] == new and res["skipped"] == [] and two_ways(base, root, new), e
    with tempfile.TemporaryDirectory() as td:                                          # 원본이 통째로 사라짐 = 다시 열림(조용히 장부만 쓰지 않음)
        base, root, _e = closed(td)
        for p in base.rglob(f"{ACCT}_*"):
            p.unlink()
        e, res = run(base, root, D3)
        assert e["상태"] == C.OPEN and len(res["skipped"]) == 1 and (root / e["이력"][-1]["보관"]).is_file(), e
    with tempfile.TemporaryDirectory() as td:                                          # 장부 본문이 깨짐 = 다시 열림 · 읽는 쪽은 깨진 본문을 안 씀
        base, root, _e = closed(td)
        p = CR.case_path(root, AID, "2026-08")
        p.write_bytes(p.read_bytes()[:-5])
        CR.use(root)
        try:
            CR.pay_rows(AID, "윙", [])
            raise AssertionError("깨진 장부 본문을 그대로 씀")
        except CR.ConfirmedBroken:
            pass
        CR.use(None)
        e, res = run(base, root, D3)
        assert e["상태"] == C.WATCH and "깨짐" in res["skipped"][0]["reason"], (e, res)
    with tempfile.TemporaryDirectory() as td:                                          # 원본 파일을 못 읽음 = 그 달만 다시 열림(다른 계정은 그대로)
        base, root, _e = closed(td)
        make(base, acct="가짜-둘째상사-acc2", days=(D2, D3))
        (base / "파일" / f"{ACCT}_{RG_FILE}").write_bytes(b"PK broken")
        e, res = run(base, root, D3)
        assert e["상태"] == C.OPEN and "원본 대조 못 함" in res["skipped"][0]["reason"] and len(res["skipped"]) == 1, (e, res)
        assert C.load_index(root)["계정"]["acc2"]["2026-08"]["상태"] == C.WATCH
    with tempfile.TemporaryDirectory() as td:                                          # 장부 기록이 깨짐 = 새로 덮지 않고 실패(호출부 = 원본으로 진행)
        base, root, _e = closed(td)
        (root / CR.INDEX).write_text("{", encoding="utf-8")
        try:
            run(base, root, D3)
            raise AssertionError("깨진 장부 기록을 덮음")
        except ValueError:
            assert (root / CR.INDEX).read_text(encoding="utf-8") == "{"
    print("t6 계정 이름 바뀜 · 원본 사라짐 · 장부 깨짐 · 원본 못 읽음(계정 격리) · 장부 기록 깨짐 OK")


# ── 정산서가 쓰는 값 ──
def read_all(base: Path, acct: str = ACCT) -> dict:
    """정산서가 원본에서 읽는 값 전부(지급 줄 장부·정산 파일·요율·비용·광고 청구)."""
    led = SL.Ledger(base, None, {}, date(2026, 11, 22))
    files, unj = CTX._settle_files(base, {})
    return {"윙": led.wing_rows(AID), "로켓": led.rg_rows(AID), "순서": {k: list(v) for k, v in led.past.items()},
            "파일": [vars(f) | {"rows": [vars(r) for r in f.rows]} for f in files[AID]], "요율": {k: sorted(v) for k, v in unj.items()},
            "rgf": {k: dict(v) for k, v in SRC.rg_file_targets(base).items()}, "비용": CFS.read_costs(base, acct),
            "광고": AC.ad_files(base, acct)[1], "청구": AC.ad_bills(base, acct)}


def two_ways(base: Path, root: Path, acct: str = ACCT) -> bool:
    raw = read_all(base, acct)
    assert CR.use(root) == 1
    try:
        return repr(read_all(base, acct)) == repr(raw)
    finally:
        CR.use(None)


def t7_statement_reads_ledger() -> None:
    sep = ("2026-09-07", "2026-09-13")
    with tempfile.TemporaryDirectory() as td:
        base, root = make(Path(td) / "정산", rg=[*RG_ROWS, rg_pay(70, 70, 60, "2026-10-01", sep)]), Path(td) / "정산확정"
        run(base, root, D1)
        got(base, ACCT, D2)
        run(base, root, D2)
        book = C.load_index(root)["계정"][AID]
        assert (book["2026-08"]["상태"], book["2026-09"]["상태"]) == (CR.CLOSED, C.OPEN), book
        raw = read_all(base)
        assert two_ways(base, root), "장부를 쓰는 길 = 원본을 읽는 길"
        READS.use(Path(td) / "읽은결과")                                                  # 읽은 결과 저장과 함께 켜도 같음(배치 = 둘 다 켜짐)
        for _ in range(2):
            assert two_ways(base, root)
        READS.use(None)
        # 정말 장부에서 읽는지 — 켠 뒤 원본을 망가뜨려도 닫힌 달 값은 그대로, 안 닫힌 달은 원본을 따름
        CR.use(root)
        wjson(base / "쿠팡지급내역" / f"{ACCT}_로켓그로스.json", [{**RG_ROWS[0], "최종지급액": -1}, rg_pay(70, 70, 1, "2026-10-01", sep)])
        (base / "파일" / f"{ACCT}_{RG_FILE}").write_bytes(b"x")
        (base / "파일" / "비용" / f"{ACCT}_{COST_FILE}").write_bytes(b"x")
        wjson(base / "검증자료" / "광고" / f"{ACCT}_광고정산_202608.json", {})
        now = read_all(base)
        CR.use(None)
        assert now["로켓"] == [*RG_ROWS, {**raw["로켓"][-1], "최종지급액": 1, "totalFinalCfsFeeDeductionAmount": 69}], now["로켓"]
        for k in ("윙", "파일", "요율", "rgf", "비용", "광고", "청구"):
            assert now[k] == raw[k], k
        assert raw["요율"] == {AID: ["502", "503"]} and raw["rgf"] == {AID: {WEEK: 890}} and raw["청구"]["로켓그로스"] == {"2026-08": 110.0}, raw
        assert CR.sheets(base / "파일" / f"{ACCT}_{RG_FILE}") is None and CR.source_sha(base / "x_y.xlsx") is None, "끄면 늘 원본"
        assert CR.use(Path(td) / "없는 폴더") == 0
    print("t7 닫힌 달 = 장부 값 · 안 닫힌 달 = 원본 · 두 길 값 같음 · 끄면 옛 동작 OK")


# ── 월별 ──
def t8_month_book() -> None:
    with tempfile.TemporaryDirectory() as td:
        base, root, _e = closed(td)
        p = root / CR.MONTHS / "2026-08.xlsx"
        wb = openpyxl.load_workbook(p)
        rows = [list(r) for r in wb.active.iter_rows(values_only=True)]
        wb.close()
        w, g = (dict(zip(rows[0], r)) for r in rows[1:])
        assert (w["채널"], w["판매액"], w["판매수수료"], w["정산대상(정산 파일)"], w["정산대상(지급 줄)"], w["공제: 윙 광고비"], w["공제 합계"],
                w["최종지급액"], w["검산 차이"]) == ("윙", 3000, 300, 2700, 2700, 100, 100, 2600, 0), w
        assert (g["채널"], g["판매액"], g["판매수수료"], g["정산대상(지급 줄)"], g["공제: 로켓그로스 물류비"], g["최종지급액"], g["검산 차이"]) == (
            "로켓그로스", 1000, 110, 890, 90, 800, 0), g
        assert (g["확정 여부"], g["확정일"], g["못 닫는 사유"]) == (CR.CLOSED, D2, None) and len(rows) == 3, g
        before = p.read_bytes()
        run(base, root, D2)
        assert p.read_bytes() == before, "바뀐 것 없으면 다시 쓰지 않음"
    with tempfile.TemporaryDirectory() as td:
        base, root = make(Path(td) / "정산", rg=RG_ROWS[:1]), Path(td) / "c"
        run(base, root, D1)
        wb = openpyxl.load_workbook(root / CR.MONTHS / "2026-08.xlsx")
        rows = [list(r) for r in wb.active.iter_rows(values_only=True)]
        wb.close()
        r = dict(zip(rows[0], rows[1]))
        assert r["확정 여부"] == C.OPEN and "정산 파일 합 ≠ 지급 줄" in r["못 닫는 사유"], r
    with tempfile.TemporaryDirectory() as td:                                          # 정산서 금액(관리 몫)은 어디에도 없음(D-419 ③)
        _base, root, _e = closed(td)
        text = gzip.decompress(CR.case_path(root, AID, "2026-08").read_bytes()).decode() + (root / CR.INDEX).read_text(encoding="utf-8")
        assert "관리 몫" not in text and "정산서" not in text
    print("t8 월별 엑셀(판매·수수료·공제 항목·최종·확정 여부·사유 · 검산 0 · 안 바뀌면 안 씀) OK")


# ── 배치 ──
def t9_batch_stage() -> None:
    blog = types.SimpleNamespace(line=lambda m: None, run_id="r", path=Path("x.log"))
    keep, seen = (SB.CONFIRMED_DIR, SB._in_child), []
    with tempfile.TemporaryDirectory() as td:
        base, root, _e = closed(td)
        out = Path(td) / "output"
        SB.CONFIRMED_DIR = root
        try:
            SB._in_child = lambda name, opts, run_dir, b: seen.append((name, opts)) or SB._job(opts, lambda m: None)
            opts = {"settle_dir": str(base), "basis": D3, "managed_output": str(out)}
            res = SB._ledger_stage(opts, Path(td), blog)
            assert res["state"] == SB.OK and opts["confirmed"] == str(root.resolve()) and seen[0][0] == "confirmed" and "confirmed" not in seen[0][1], (res, opts)
            wjson(base / "쿠팡지급내역" / f"{ACCT}_로켓그로스.json", [{**RG_ROWS[0], "최종지급액": 1}, RG_ROWS[1]])
            opts = {k: v for k, v in opts.items() if k != "confirmed"}
            res = SB._ledger_stage(opts, Path(td), blog)                                # 값이 바뀐 달 = 확인 필요 목록 한 줄(탭·상태 카드·보고 공통)
            assert res["state"] == SB.CHECK and opts["confirmed"], res
            items = SB.check_items(D3, {"confirmed": res}, {}, {})
            assert len(items) == 1 and items[0][:4] == [D3, "쿠팡 확정 장부", AID, ACCT] and items[0][6] == "-599" and "2026-08" in items[0][7], items
            (root / CR.INDEX).write_text("{", encoding="utf-8")                          # 장부 단계 실패 = 장부 없이 다음 단계 · 확인 필요 · '중단' 판정 아님
            SB._in_child = lambda name, opts, run_dir, b: SB._result("JSONDecodeError: 깨짐")
            opts = {k: v for k, v in opts.items() if k != "confirmed"}
            res = SB._ledger_stage(opts, Path(td), blog)
            items = SB.check_items(D3, {"confirmed": res}, {}, {})
            assert res["state"] == SB.CHECK and "confirmed" not in opts and items[0][7].startswith("중단 — "), (res, items)
            assert SB._verdict({"confirmed": res}, items) == SB.CHECK
        finally:
            SB.CONFIRMED_DIR, SB._in_child = keep
    with tempfile.TemporaryDirectory() as td:                                          # 일 함수 = opts['confirmed'] 가 있을 때만 켜지고 끝나면 꺼짐
        base, root, _e = closed(td)
        p, seen2 = base / "파일" / f"{ACCT}_{RG_FILE}", []
        mod = types.ModuleType("_t188_fake_job2")
        mod.run_job = lambda opts, on_log: seen2.append(CR.source_sha(p)) or SB._result()  # type: ignore[attr-defined]
        sys.modules[mod.__name__] = mod
        try:
            for conf in ({"confirmed": str(root)}, {}):
                SB._job({"module": mod.__name__, "managed_output": None, **conf}, lambda m: None)
        finally:
            del sys.modules[mod.__name__]
        assert seen2[0] and seen2[1] is None and CR.source_sha(p) is None, seen2
    assert SB.CONFIRMED_DIR == Path("output") / "정산확정", SB.CONFIRMED_DIR
    print("t9 배치 단계(성공 = 장부 켬 · 바뀜 = 확인 필요 · 실패 = 원본으로 진행 + 확인 필요) OK")


def main() -> int:
    for t in (t1_two_different_collect_days, t2_why_not_closed, t3_body_is_coupang_original, t4_reopen_on_change, t5_reopen_kinds_and_not,
              t6_rename_gone_broken, t7_statement_reads_ledger, t8_month_book, t9_batch_stage):
        t()
    print("쿠팡 확정 장부 오프라인 검증 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
