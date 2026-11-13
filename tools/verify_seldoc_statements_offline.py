"""셀독 정산서 시험(오프라인·결정적·실 API 없음) — T-25 4단계. 기대값 = 결정 문장에서 도출(코드에서 뽑지 않음).

- D-221 ① 목표 도달율 = 정산 기준 실적 ÷ (계약금액 + 목표수익금) · ② 시트 1장 · 내부용 글자(출처·확인 필요·D번호) 없음
  · 근거 예시 "도달율 52.1% = 13,063,096 ÷ 25,085,280"
- D-225 ① 쿠팡 숫자 = 위탁정산서 결과만 ② 계약 내용 = 계약서 분석 DB 값 그대로 ③ 값이 없으면 없는 대로('없음')
  → 수익금 빈 칸 = 목표수익금 '없음' · 분모 = 계약금액
- D-218 판매실적과 정산 자료는 따로 나란히(더하거나 한쪽으로 대신하지 않음)
- D-152 ⑥·D-224 정산 요약 = 입금 완료 · 입금 예정 · 보류 · 보상 → 정산 기준 실적 = 넷의 합 · A4 세로 1쪽
- 대상 계약(준비 문서 3절): '셀독 상품공급 OEM'·'보냉백 OEM 생산공급' = 대상 · 제로리스크·제로셀·투자·위임 = 제외
- D-155 서달원 = 계약별 상품군 · D-229 개별 판정 = 판정표 파일 · 판정표 없거나 계약 못 찾으면 시작 전 중단(fallback 금지)

    python tools/verify_seldoc_statements_offline.py
"""
from __future__ import annotations

import csv
import inspect
import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

DOC_A = "aaaaaaaa-0000-0000-0000-000000000001"     # 보냉백 OEM(가나상사 · 한 계약)
DOC_B1 = "bbbbbbbb-0000-0000-0000-000000000001"    # 셀독 OEM 수영장(다라커머스)
DOC_B2 = "bbbbbbbb-0000-0000-0000-000000000002"    # 셀독 OEM 매트(다라커머스)
DOC_B3 = "bbbbbbbb-0000-0000-0000-000000000003"    # 셀독 OEM 가방(다라커머스 · 판매 상품 없음)
DOC_Z = "cccccccc-0000-0000-0000-000000000001"     # 제로리스크(제외)
DOC_INV = "cccccccc-0000-0000-0000-000000000002"   # 투자계약(제외)
DOC_POA = "cccccccc-0000-0000-0000-000000000003"   # 위임장(제외)
DOC_ZS = "cccccccc-0000-0000-0000-000000000004"    # 제로셀(제외)
HEAD = ["관계그룹ID", "그룹 대표 이름", "문서ID(누르면 원문 PDF)", "파일명", "문서제목(원문)", "문서종류", "계약유형(대)", "계약유형(소)",
        "계약일(서명일)", "계약종료일", "회사측 명칭", "계약자 명칭", "계약자 대표", "계약금액(원금)", "수익금", "수익률(%)", "품목"]
INTERNAL = ("D-", "확인 필요", "출처", "판정", "Claude", "추정", "R1")


# ── 합성 입력(작게) ──
def _contract(doc, kind, signed, end, party, rep, amount, profit=None, rate=None, title="“셀독” 상품공급 OEM 계약서", company="㈜회사"):
    return {"문서ID(누르면 원문 PDF)": doc, "계약유형(소)": kind, "계약일(서명일)": signed, "계약종료일": end, "회사측 명칭": company,
            "계약자 명칭": party, "계약자 대표": rep, "계약금액(원금)": amount, "수익금": profit, "수익률(%)": rate, "문서제목(원문)": title}


CONTRACTS = [
    _contract(DOC_A, "보냉백 OEM 생산공급", "2026-05-14", None, "가나상사", "김가나", 10_000_000, title="상품 공급 OEM 계약서"),
    _contract(DOC_Z, "OEM 제품공급 제로리스크", "2025-02-25", None, "가나상사", "김가나", 50_000_000, 5_000_000, 10),
    _contract(DOC_POA, "토탈셀러 미정산 채권 회수 협의체 위임장", "2026-04-07", None, "가나상사", "김가나", None),
    _contract(DOC_B1, "셀독 상품공급 OEM", "2026-03-27", "2026-09-23", "이다라", None, 20_000_000),
    _contract(DOC_B2, "셀독 상품공급 OEM", "2026-06-09", "2026-12-10", "이다라", None, 16_000_000, 2_000_000, 12.5),
    _contract(DOC_B3, "셀독 상품공급 OEM", "2026-05-21", "2026-11-20", "다라커머스", "이다라", 13_000_000),
    _contract(DOC_INV, "투자계약(확정지급)", "2025-11-28", None, "이다라", None, 10_400_000, 1_664_000, 16),
    _contract(DOC_ZS, "제로셀 상품공급 OEM(3자)", "2026-01-09", "2026-07-07", "스마트", "이다라", 10_000_000, 1_500_000, 15),
]
ITEMS = [(DOC_A, "보냉백 YG1", 6000, 1000), (DOC_A, "보냉백 BG1", 4000, 1000), (DOC_B1, "수영장 HW1", 20000, 1000),
         (DOC_B2, "매트 MN1", 8000, 2000), (DOC_B3, "가방 C1", 6500, 2000)]


def make_db(p: Path, contracts=CONTRACTS, items=ITEMS) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "계약 통합"
    ws.append(HEAD)
    for c in contracts:
        ws.append([c.get(h) for h in HEAD])
    wi = wb.create_sheet("품목")
    wi.append(["문서ID", "파일명", "품목명(원문)", "품목 종류", "모델", "단가", "수량", "금액", "품목별 지급액", "근거"])
    for doc, name, price, qty in items:
        wi.append([doc, "f", name, name.split()[0], name.split()[-1], price, qty, price * qty, None, "1쪽"])
    wi.append([DOC_A + "~2", "다른 문서", "목욕의자", "목욕의자", None, None, 10, 100, None, "1쪽"])     # 문서ID 앞부분만 같은 줄 = 다른 계약
    wb.save(p)
    return p


def make_statement(p: Path, biz: str, aid: str, done: int, due_hold: int, hold: int, extras=(), months=(), prods=()) -> Path:
    """위탁정산서 결과 파일 모양(settlement_statement_book 의 칸 이름) — 정산서·월별 판매·상품별 판매·계산 근거."""
    from coupang_analytics.settlement_statement_sheets import SHIP_LABEL
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "정산서"
    ws["B1"] = f"{biz}님 쿠팡 판매 정산내역서"
    for r, (k, v) in enumerate([("사업자", biz), ("쿠팡 계정", aid), ("판매 기간", "2026-06 ~ 2026-11-03\n관리 시작 2026-05 — 확인 필요"),
                                ("기준일", "2026-11-03  (발행 2026-11-12)")], 2):
        ws.cell(r, 2, k)
        ws.cell(r, 3, v)
    ws["B7"], ws["E7"] = "A 판매금액", "G 최종 지급액"
    ws["E8"] = done + due_hold
    ws["B41"], ws["C41"], ws["D41"], ws["E41"] = "G 최종 지급액", done, due_hold, done + due_hold
    r = 54
    for label, amt in extras:
        ws.cell(r, 2, f"쿠팡 별도 보상 — {label}")
        ws.cell(r, 3, amt)
        r += 1
    m = wb.create_sheet("월별 판매")
    m.append(["월별 판매"])
    m.append(["관리 상품만"])
    m.append([])
    m.append(["판매 월", "판매금액", "쿠팡 정산금액", "상태"])
    for ym, s, st in months:
        m.append([ym, s, round(s * .8), st])
    m.append(["합계", sum(x[1] for x in months), None])
    s = wb.create_sheet("상품별 판매")
    s.append(["상품별 판매"])
    s.append(["정산 끝난 판매만"])
    s.append([])
    s.append(["상품명", "수량", "판매금액", "쿠팡 정산금액"])
    for name, q, amt in list(prods) + [(SHIP_LABEL, 0, 18000)]:
        s.append([name, q, amt, round(amt * .8)])
    s.append(["합계", sum(x[1] for x in prods), sum(x[2] for x in prods) + 18000, None])
    b = wb.create_sheet("계산 근거")
    b.append(["계산 근거"])
    b.append(["관리 상품 = …"])
    b.append([])
    b.append(["항목", "계정 전체", "관리 상품 비율", "관리 상품 몫", "나누는 기준"])
    b.append(["입금 지급 완료", 1, 1, done, ""])
    b.append(["입금 예정", 1, 1, due_hold - hold, ""])
    b.append(["입금 보류", 1, 1, hold, ""])
    wb.save(p)
    return p


def make_inputs(d: Path, judge: dict | None) -> Path:
    from coupang_analytics import settlement_seldoc_source as SS
    inp = d / "입력_셀독"
    inp.mkdir()
    with open(inp / "사업자_대응표.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["정산 계정명", "대표자", "사업자", "계정ID", "출처"])
        w.writerow(["김가나-가나상사-ga1", "김가나", "가나상사", "ga1", "관리대장"])
        w.writerow(["이다라-다라커머스-da1", "이다라", "다라커머스", "da1", "관리대장"])
    if judge is not None:
        (inp / SS.JUDGE).write_text(json.dumps(judge, ensure_ascii=False), encoding="utf-8")
    return inp


JUDGE = {"계약": {DOC_A: {"계정ID": "ga1", "판정": "대상", "근거": "계약자 명칭 '가나상사' = 계정 사업자"},
                  DOC_B1: {"계정ID": "da1", "판정": "대상", "근거": "계약자 '이다라' = 계정 대표자"},
                  DOC_B2: {"계정ID": "da1", "판정": "대상", "근거": "계약자 '이다라' = 계정 대표자"},
                  DOC_B3: {"계정ID": "da1", "판정": "대상", "근거": "계약자 명칭 '다라커머스' = 계정 사업자"}},
         "상품": {"da1": {"P1": {"상품명": "수영장 HW1", "문서ID": DOC_B1, "근거": "계약 품목 '수영장 HW1' 과 같은 상품"},
                          "P2": {"상품명": "매트 MN1", "문서ID": DOC_B2, "근거": "계약 품목 '매트 MN1' 과 같은 상품"},
                          "P3": {"상품명": "가습기 N1", "문서ID": DOC_B2, "근거": "계약 외 상품 — 나머지 상품 계약"}}}}


def _raises(fn, *a, word: str = "") -> str:
    from coupang_analytics.settlement_seldoc_source import SeldocInputError
    try:
        fn(*a)
    except SeldocInputError as exc:
        assert word in str(exc), (word, str(exc))
        return str(exc)
    raise AssertionError(f"SeldocInputError 안 남: {fn.__name__}")


# ── 1. 규칙(결정 문장) ──
def test_rules() -> None:
    from coupang_analytics import settlement_seldoc_source as SS
    assert SS.contract_kind("셀독 상품공급 OEM") == SS.contract_kind("보냉백 OEM 생산공급") == "대상"
    for t in ("OEM 제품공급 제로리스크", "제로리스크 OEM(재고보증 전량사입)", "제로셀 상품공급 OEM(3자)", "투자계약(확정지급)",
              "토탈셀러 미정산 채권 회수 협의체 위임장", "계약자 협의체 위임·동의(토탈셀러 미정산 채권 회수)"):
        assert SS.contract_kind(t) == "제외", t
    assert SS.contract_kind("물품 공급(납품) 계약") == "규칙 밖"                   # 규칙에 없는 유형 = 혼자 넣거나 빼지 않음
    assert abs(SS.reach(13_063_096, 20_904_400, 4_180_880) - 0.5207) < 1e-4       # D-221 근거 예시 52.1%
    assert SS.reach(13_063_096, 20_904_400, None) == 13_063_096 / 20_904_400      # 수익금 빈 칸 = 분모 계약금액만
    assert SS.goal_total(20_904_400, None) == 20_904_400 and SS.goal_total(14_000_000, 4_200_000) == 18_200_000
    print("test_rules OK")


# ── 2. 위탁정산서 결과 읽기(D-225 ① · D-152 ⑥ · D-218) ──
def test_read_statement() -> None:
    from coupang_analytics import settlement_seldoc_source as SS
    with tempfile.TemporaryDirectory() as d:
        p = make_statement(Path(d) / "s.xlsx", "가나상사 (대표 김가나)", "ga1", 3_000_000, 1_500_000, 500_000,
                           extras=[("쿠팡 화재 보상금", 2_000_000)],
                           months=[("2026-06", 4_000_000, "끝남"), ("2026-10", 1_000_000, "정산 중(일부 비율 배분)")],
                           prods=[("보냉백 YG1", 300, 2_000_000), ("보냉백 BG1", 100, 1_000_000), ("보냉백 YG1", 10, 100_000)])
        pf = SS.read_statement(p)
        assert (pf.aid, pf.label, pf.done, pf.due, pf.hold, pf.total) == ("ga1", "가나상사 (대표 김가나)", 3_000_000, 1_000_000, 500_000, 4_500_000)
        assert pf.extras == [("쿠팡 화재 보상금", 2_000_000)]
        assert pf.result == 3_000_000 + 1_000_000 + 500_000 + 2_000_000                 # 입금 완료 + 예정 + 보류 + 보상
        assert pf.sales == 5_000_000 and pf.qty == 410                                 # 판매 = 월별 판매 합계 · 수량 = 상품별(정산 끝난 판매)
        assert pf.products == [("보냉백 YG1", 310, 2_100_000), ("보냉백 BG1", 100, 1_000_000)]   # 같은 상품명 합침 · 배송비 줄 뺌
        assert [m[2] for m in pf.months] == ["끝남", "정산 중"]
        assert pf.period.startswith("2026-06 ~ 2026-11-03") and "확인 필요" not in pf.period
        wb = openpyxl.load_workbook(p)
        wb["정산서"]["E41"] = 4_500_001                                               # 칸 합 ≠ G = 읽지 않음
        wb.save(p)
        _raises(SS.read_statement, p, word="G")
    print("test_read_statement OK")


# ── 3. 대상 계약 고르기(규칙 + 판정표) ──
def test_plan() -> None:
    from coupang_analytics import settlement_seldoc_source as SS
    with tempfile.TemporaryDirectory() as d:
        db = SS.load_contracts(make_db(Path(d) / "db.xlsx"))
        assert db[DOC_A].items == [("보냉백 YG1", 6000, 1000), ("보냉백 BG1", 4000, 1000)]        # '~2' 문서는 다른 계약
        assert (db[DOC_A].profit, db[DOC_A].rate, db[DOC_B2].profit) == (None, None, 2_000_000)
        inp = make_inputs(Path(d), JUDGE)
        people = SS.load_people(inp)
        jobs = SS.plan(people, db, SS.load_judge(inp), ["ga1", "da1"])
        assert [(j.aid, j.contract.doc_id, j.split) for j in jobs] == [
            ("ga1", DOC_A, False), ("da1", DOC_B1, True), ("da1", DOC_B3, True), ("da1", DOC_B2, True)]   # 계약일 순 · 제외 유형 4건 빠짐
        bad = json.loads(json.dumps(JUDGE))
        del bad["계약"][DOC_B3]
        _raises(SS.plan, people, db, bad, ["da1"], word=DOC_B3)                         # 대상 계약인데 판정 없음 = 중단
        bad = json.loads(json.dumps(JUDGE))
        bad["계약"]["dddddddd-0000-0000-0000-000000000009"] = {"계정ID": "da1", "판정": "대상", "근거": "x"}
        _raises(SS.plan, people, db, bad, ["da1"], word="계약 못 찾음")                 # 판정표 계약이 DB 에 없음 = 중단
        bad = json.loads(json.dumps(JUDGE))
        bad["계약"][DOC_Z] = {"계정ID": "ga1", "판정": "대상", "근거": "x"}
        _raises(SS.plan, people, db, bad, ["ga1"], word="대상 유형 아님")
        odd = CONTRACTS + [_contract("eeeeeeee-0000-0000-0000-000000000001", "물품 공급(납품) 계약", "2026-01-01", None, "가나상사", "", 1)]
        db2 = SS.load_contracts(make_db(Path(d) / "db2.xlsx", odd))
        _raises(SS.plan, people, db2, JUDGE, ["ga1"], word="규칙 밖")
        _raises(SS.plan, people, db, JUDGE, ["zz9"], word="대응표")
        _raises(SS.load_judge, Path(d) / "없는폴더", word="시작 전 중단")
    print("test_plan OK")


# ── 4. 상품군 나누기(D-155 · 판정표대로) ──
def test_groups() -> None:
    from coupang_analytics import settlement_seldoc_groups as G
    docs = [DOC_B1, DOC_B2, DOC_B3]
    got = G.assign({"P1", "P2", "P3"}, JUDGE["상품"]["da1"], docs)
    assert got == {DOC_B1: {"P1"}, DOC_B2: {"P2", "P3"}, DOC_B3: set()}, got           # 판매 상품 없는 계약 = 빈 범위(실적 0)
    _raises(G.assign, {"P1", "P4"}, JUDGE["상품"]["da1"], docs, word="P4")              # 판정 없는 관리 상품 = 중단
    _raises(G.assign, {"P1"}, {"P1": {"문서ID": DOC_A, "근거": "x"}}, docs, word="P1")   # 이 계정 계약이 아닌 문서ID = 중단
    seen: set = set()
    f = G.group_filter(lambda v: v != "v9", {"v1": "P1", "v2": "P2", "v9": "P1"}, {"P1"}, seen)
    assert (f("v1"), f("v2"), f("v9"), f("v7")) == (True, False, False, False)
    assert seen == {"v7"}
    # 판정할 관리 상품 = 정산 원본 관리 등록상품 + 관리 VID 의 등록상품(정산 중 달에만 팔린 상품도 빠지지 않게)
    assert G.managed_pids({"P1"}, {"v1": "P1", "v5": "P5", "v6": "P6"}, lambda v: v != "v6", ["v8"]) == {"P1", "P5"}                                                              # 관리 VID 인데 등록상품을 모름 = 기록(뒤에서 중단)
    print("test_groups OK")


# ── 5. 양식 1장(D-221 · D-224 · D-218 · D-225 ③) ──
def _cells(ws) -> dict:
    return {c.coordinate: c.value for row in ws.iter_rows() for c in row if c.value is not None}


def _find(cells: dict, text: str, min_row: int = 1) -> str:
    """text 가 든 첫 칸(min_row 행부터) — 카드 제목과 계약 내용 줄이 같은 글자일 때 구분."""
    return next(k for k, v in cells.items() if v == text and int("".join(ch for ch in k if ch.isdigit())) >= min_row)


def _right_of(ws, coord: str, col: str):
    return ws[f"{col}{ws[coord].row}"].value


def _assert_page(wb):
    """1장 · A4 세로 1쪽 · 20열 × 4.6 · 내부용 글자 없음(D-221 ② · D-224)."""
    assert wb.sheetnames == ["셀독 정산서"]
    ws = wb.active
    ps = ws.page_setup
    assert (ps.orientation, str(ps.paperSize), ps.fitToWidth, ps.fitToHeight, ws.sheet_properties.pageSetUpPr.fitToPage) == (
        "portrait", "9", 1, 1, True)
    assert ws.print_area == f"'셀독 정산서'!$A$1:$T${ws.max_row}"
    assert [ws.column_dimensions[chr(65 + i)].width for i in range(20)] == [4.6] * 20 and "A1:T1" in ws.merged_cells
    assert not [v for v in _cells(ws).values() if isinstance(v, str) and any(w in v for w in INTERNAL)], "내부용 글자"
    rs = list(ws.merged_cells.ranges)                                   # 병합이 겹치면 엑셀이 '읽을 수 없는 내용' 복구 창을 띄움
    overlap = [(str(a), str(b)) for i, a in enumerate(rs) for b in rs[i + 1:]
               if not (a.max_row < b.min_row or b.max_row < a.min_row or a.max_col < b.min_col or b.max_col < a.min_col)]
    assert not overlap, overlap
    return ws


def test_sheet() -> None:
    from coupang_analytics import settlement_seldoc_sheet as SH
    from coupang_analytics import settlement_seldoc_source as SS
    with tempfile.TemporaryDirectory() as d:
        db = SS.load_contracts(make_db(Path(d) / "db.xlsx"))
        pf = SS.read_statement(make_statement(Path(d) / "s.xlsx", "가나상사 (대표 김가나)", "ga1", 3_000_000, 1_500_000, 500_000,
                                              extras=[("쿠팡 화재 보상금", 2_000_000)],
                                              months=[("2026-06", 4_000_000, "끝남"), ("2026-10", 1_000_000, "정산 중(일부 비율 배분)")],
                                              prods=[("보냉백 YG1", 300, 2_000_000), ("보냉백 BG1", 100, 1_000_000)]))
        out = SH.write(Path(d) / "o.xlsx", db[DOC_A], pf, "2026-11-03", "2026-11-12")
        ws = _assert_page(openpyxl.load_workbook(out))
        c = _cells(ws)
        result = 3_000_000 + 1_000_000 + 500_000 + 2_000_000
        assert (ws["A5"].value, ws["F5"].value, ws["P5"].value) == (10_000_000, result, 10_000_000 - result)
        assert abs(ws["K5"].value - result / 10_000_000) < 1e-12                          # 분모 = 계약금액(수익금 빈 칸)
        assert "없음" in str(_right_of(ws, _find(c, "목표수익률 · 목표수익금"), "F"))
        assert _right_of(ws, _find(c, "목표 정산 총액", 12), "F") == 10_000_000
        # 판매 요약(왼쪽)과 정산 요약(오른쪽) 따로 — 판매금액은 실적에 더하지 않음
        assert ws["A" + str(ws[_find(c, "쿠팡 판매 요약")].row)].value == "쿠팡 판매 요약"
        assert _find(c, "쿠팡 정산 요약").startswith("L")
        note = ws[next(k for k, v in c.items() if isinstance(v, str) and v.startswith("정산 대상 상품 · 판매 기간"))]                                            # 판매 요약 밑 안내 = 줄바꿈 두 줄이 다 보이는 높이
        assert note.alignment.wrap_text and (ws.row_dimensions[note.row].height or 15) >= 24, ws.row_dimensions[note.row].height
        assert _right_of(ws, _find(c, "판매금액"), "E") == 5_000_000
        assert _right_of(ws, _find(c, "판매수량"), "E") == 400
        settle = {k: _right_of(ws, _find(c, k, 12), "Q") for k in ("입금 완료", "입금 예정", "보류", "정산 기준 실적")}
        assert settle == {"입금 완료": 3_000_000, "입금 예정": 1_000_000, "보류": 500_000, "정산 기준 실적": result}, settle
        assert _right_of(ws, _find(c, "보상 (쿠팡 화재 보상금)"), "Q") == 2_000_000
        bar = [ws.cell(9, k).fill.fgColor.rgb for k in range(1, 21)]
        assert bar.count(bar[0]) == round(result / 10_000_000 * 20) and bar[0] != bar[-1]   # 도달율 막대 = 20칸 중 비율만큼
    print("test_sheet OK")


def test_sheet_goal() -> None:
    """목표수익금이 있는 계약 = 분모 계약금액 + 수익금 · 실적 0 · 막대 0칸."""
    from coupang_analytics import settlement_seldoc_sheet as SH
    from coupang_analytics import settlement_seldoc_source as SS
    with tempfile.TemporaryDirectory() as d:
        db = SS.load_contracts(make_db(Path(d) / "db.xlsx"))
        empty = SS.Perf(label="x", aid="da1", period="", done=0, due=0, hold=0, total=0, extras=[], months=[], products=[])
        ws2 = openpyxl.load_workbook(SH.write(Path(d) / "o2.xlsx", db[DOC_B2], empty, "2026-11-03", "2026-11-12")).active
        assert (ws2["A5"].value, ws2["F5"].value, ws2["K5"].value, ws2["P5"].value) == (18_000_000, 0, 0, 18_000_000)
        c2 = _cells(ws2)
        assert _right_of(ws2, _find(c2, "목표수익률 · 목표수익금"), "F") == "12.5%  ·  2,000,000원"
        assert len({ws2.cell(9, k).fill.fgColor.rgb for k in range(1, 21)}) == 1
    print("test_sheet_goal OK")


# ── 6. 입구(명령줄) — 계약 1건 = 1파일 · 판정표 없음/계약 못 찾음/상품군 정산서 없음 = 시작 전 중단 ──
def _run(argv) -> tuple[int, str]:
    import settlement_seldoc as T
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = T.main(argv)
    return code, buf.getvalue()


def test_cli() -> None:
    from coupang_analytics import settlement_seldoc_groups as G
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        db = make_db(base / "db.xlsx")
        st, gs, out = base / "위탁", base / "상품군", base / "out"
        st.mkdir()
        gs.mkdir()
        make_statement(st / "정산서_가나상사_김가나_ga1_관리상품.xlsx", "가나상사 (대표 김가나)", "ga1", 3_000_000, 1_000_000, 0,
                       months=[("2026-06", 4_000_000, "끝남")], prods=[("보냉백 YG1", 300, 4_000_000)])
        make_statement(st / "정산서_다라커머스_이다라_da1_관리상품.xlsx", "다라커머스 (대표 이다라)", "da1", 9, 9, 0)
        for doc, done in ((DOC_B1, 1_000_000), (DOC_B2, 2_000_000)):
            make_statement(G.group_path(gs, "da1", doc), "다라커머스 (대표 이다라)", "da1", done, 0, 0)
        argv = ["make", "--statements", str(st), "--group-statements", str(gs), "--db", str(db), "--out", str(out),
                "--basis", "2026-11-03", "--issued", "2026-11-12", "--accounts", "ga1,da1"]
        code, log = _run(argv + ["--seldoc-inputs", str(make_inputs(base, None))])
        assert code == 1 and "시작 전 중단" in log, log                                   # 판정표 없음
        (base / "입력_셀독" / "사업자_대응표.csv").unlink()
        (base / "입력_셀독").rmdir()
        inp = make_inputs(base, JUDGE)
        code, log = _run(argv + ["--seldoc-inputs", str(inp)])
        assert code == 1 and "시작 전 중단" in log and DOC_B3[:8] in log, log            # 판매 없는 계약도 상품군 정산서가 있어야 함
        make_statement(G.group_path(gs, "da1", DOC_B3), "다라커머스 (대표 이다라)", "da1", 0, 0, 0)
        assert not out.exists()                                                          # 중단 = 파일 안 만듦
        code, log = _run(argv + ["--seldoc-inputs", str(inp)])
        assert code == 0, log
        files = sorted(out.glob("셀독정산서_*_20261103기준_*.xlsx"))
        assert len(files) == 4, files                                                    # 계약 1건 = 1파일
        got = {}
        for f in files:
            ws = openpyxl.load_workbook(f).active
            got[ws["F13"].value] = ws["F5"].value
        assert got == {"2026-05-14": 4_000_000, "2026-03-27": 1_000_000, "2026-06-09": 2_000_000, "2026-05-21": 0}, got
        bad = json.loads(json.dumps(JUDGE))
        bad["계약"]["dddddddd-0000-0000-0000-000000000009"] = {"계정ID": "ga1", "판정": "대상", "근거": "x"}
        (inp / "셀독_계약상품군_판정.json").write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        code, log = _run(argv + ["--seldoc-inputs", str(inp)])
        assert code == 1 and "계약 못 찾음" in log, log
    print("test_cli OK")


# ── 7. 읽는 칸 이름 = 위탁정산서 코드가 쓰는 이름(이름이 바뀌면 여기서 먼저 깨짐) ──
def test_labels_match_book() -> None:
    from coupang_analytics import settlement_seldoc_source as SS
    from coupang_analytics import settlement_statement_book as BK
    src = inspect.getsource(BK)
    for label in SS.BOOK_LABELS:
        assert f'"{label}' in src, label
    print("test_labels_match_book OK")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    test_rules()
    test_read_statement()
    test_plan()
    test_groups()
    test_sheet()
    test_sheet_goal()
    test_cli()
    test_labels_match_book()
    print("✅ 셀독 정산서 시험 8종 통과(규칙·읽기·대상 계약·상품군·양식 1장·목표수익금·입구·칸 이름)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
