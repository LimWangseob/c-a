"""셀독 정산서 시험(오프라인·결정적·실 API 없음) — T-25 4단계. 기대값 = 결정 문장에서 도출(코드에서 뽑지 않음).

- D-221 ① 목표 도달율 = 정산 기준 실적 ÷ (계약금액 + 목표수익금) · ② 시트 1장 · 내부용 글자(출처·확인 필요·D번호) 없음
  · 근거 예시 "도달율 52.1% = 13,063,096 ÷ 25,085,280"
- D-225 ① 쿠팡 숫자 = 위탁정산서 결과만 ② 계약 내용 = 계약서 분석 DB 값 그대로 ③ 값이 없으면 없는 대로('없음')
  → 수익금 빈 칸 = 목표수익금 '없음' · 분모 = 계약금액
- D-218 판매실적과 정산 자료는 따로 나란히(더하거나 한쪽으로 대신하지 않음)
- D-152 ⑥·D-224 정산 요약 = 입금 완료 · 입금 예정 · 보류 · 보상 → 정산 기준 실적 = 넷의 합 · A4 세로 1쪽
- 대상 계약(준비 문서 3절): '셀독 상품공급 OEM'·'보냉백 OEM 생산공급' = 대상 · 제로리스크·투자·위임 = 제외
- D-397 ①(D-206 ③) 제로셀 계약 = 대상(유형 이름에 '제로셀' · 계정별 최종 = 판정표 · 판정 없으면 중단 = 빠뜨리지 않음)
- D-155 서달원 = 계약별 상품군 · D-229 개별 판정 = 판정표 파일 · 판정표 없거나 계약 못 찾으면 시작 전 중단(fallback 금지)
- D-399 배치(레인 D): 판정 없는 계약 = 그 계약만 건너뛰고 보고 · 입력 자체 없음만 중단 · 같은 이름 = 덮지 않음 · 입력 기본 = output\정산서\입력_셀독

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
DOC_ZS = "cccccccc-0000-0000-0000-000000000004"    # 제로셀(대상 D-397 · 다라커머스 대표 이다라)
HEAD = ["관계그룹ID", "그룹 대표 이름", "문서ID(누르면 원문 PDF)", "파일명", "문서제목(원문)", "문서종류", "계약유형(대)", "계약유형(소)",
        "계약일(서명일)", "계약종료일", "회사측 명칭", "계약자 명칭", "계약자 대표", "계약금액(원금)", "수익금", "수익률(%)", "품목", "관리대상"]
INTERNAL = ("D-", "확인 필요", "출처", "판정", "Claude", "추정", "R1")


# ── 합성 입력(작게) ──
def _contract(doc, kind, signed, end, party, rep, amount, profit=None, rate=None, title="“셀독” 상품공급 OEM 계약서", company="㈜회사",
              managed=None):
    return {"관리대상": managed, "문서ID(누르면 원문 PDF)": doc, "계약유형(소)": kind, "계약일(서명일)": signed, "계약종료일": end, "회사측 명칭": company,
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


def make_db(p: Path, contracts=CONTRACTS, items=ITEMS, head=HEAD) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "계약 통합"
    ws.append(head)
    for c in contracts:
        ws.append([c.get(h) for h in head])
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
                  DOC_B3: {"계정ID": "da1", "판정": "대상", "근거": "계약자 명칭 '다라커머스' = 계정 사업자"},
                  DOC_ZS: {"계정ID": "da1", "판정": "대상", "근거": "계약자 대표 '이다라' = 계정 대표자 · 제로셀 상품공급(D-397)"}},
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
    for t in ("제로셀 상품공급 OEM", "제로셀 상품공급 OEM(3자)", "제로셀(분할지급·원금반환)", "제로셀 상품공급",
              "OEM 제품공급 제로셀", "제로셀(분할지급형 제로리스크)"):                  # D-397 제로셀 계약 = 대상(제외 낱말보다 먼저)
        assert SS.contract_kind(t) == "대상", t
    for t in ("OEM 제품공급 제로리스크", "제로리스크 OEM(재고보증 전량사입)", "투자계약(확정지급)",
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
            ("ga1", DOC_A, False), ("da1", DOC_ZS, True), ("da1", DOC_B1, True), ("da1", DOC_B3, True), ("da1", DOC_B2, True)]
        # 계약일 순 · 제로셀 포함(D-397) · 제외 유형 3건(제로리스크·위임·투자) 빠짐
        bad = json.loads(json.dumps(JUDGE))
        del bad["계약"][DOC_ZS]
        _raises(SS.plan, people, db, bad, ["da1"], word=DOC_ZS)                         # 제로셀 계약인데 판정 없음 = 중단(조용히 빼지 않음)
        other = json.loads(json.dumps(JUDGE))
        other["계약"][DOC_ZS] = {"계정ID": "zz1", "판정": "대상", "근거": "같은 이름 다른 사람"}
        assert DOC_ZS not in [j.contract.doc_id for j in SS.plan(people, db, other, ["da1"])]   # 판정표가 다른 계정으로 둠 = 이 계정에서 뺌
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


# ── 3-2. 신규셀독 관리대상 계약 = 유형 글자와 관계없이 대상(D-398 · 소유자 11-24 '53건 전부') ──
def test_managed() -> None:
    from coupang_analytics import settlement_seldoc_source as SS
    m1, m2 = "ffffffff-0000-0000-0000-000000000001", "ffffffff-0000-0000-0000-000000000002"
    rows = CONTRACTS + [_contract(m1, "물품 공급(납품) 계약", "2026-04-10", None, "가나상사", "김가나", 20_000_000, managed="관리대상"),
                        _contract(m2, "OEM 제품공급 제로리스크", "2025-11-27", None, "가나상사", "김가나", 50_000_000, managed="관리대상")]
    judge = json.loads(json.dumps(JUDGE))
    for doc in (m1, m2):
        judge["계약"][doc] = {"계정ID": "ga1", "판정": "대상", "근거": "x"}
    with tempfile.TemporaryDirectory() as d:
        db = SS.load_contracts(make_db(Path(d) / "db.xlsx", rows))
        assert db[m1].managed and db[m2].managed and not db[DOC_Z].managed
        assert SS.target_kind(db[m1]) == SS.target_kind(db[m2]) == "대상"                # 규칙 밖·제외 낱말이어도 관리대상 = 대상
        assert SS.target_kind(db[DOC_Z]) == "제외" and SS.target_kind(db[DOC_A]) == "대상"  # 관리대상 아님 = 글자 규칙 그대로
        inp = make_inputs(Path(d), judge)
        jobs = SS.plan(SS.load_people(inp), db, SS.load_judge(inp), ["ga1"])
        assert [j.contract.doc_id for j in jobs] == [m2, m1, DOC_A]                       # 관리대상 2건 + 보냉백 · 계약일 순 · 제로리스크 DOC_Z 빠짐
        bad = json.loads(json.dumps(judge))
        del bad["계약"][m1]
        _raises(SS.plan, SS.load_people(inp), db, bad, ["ga1"], word=m1)                # 관리대상인데 판정 없음 = 중단
        _raises(SS.load_contracts, make_db(Path(d) / "old.xlsx", head=HEAD[:-1]), word="관리대상")   # '관리대상' 칸 없는 옛 DB = 중단
    print("test_managed OK")


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
        for doc, done in ((DOC_B1, 1_000_000), (DOC_B2, 2_000_000), (DOC_ZS, 700_000)):
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
        assert len(files) == 5, files                                                    # 계약 1건 = 1파일(제로셀 포함 D-397)
        got = {}
        for f in files:
            ws = openpyxl.load_workbook(f).active
            got[ws["F13"].value] = ws["F5"].value
        assert got == {"2026-05-14": 4_000_000, "2026-01-09": 700_000, "2026-03-27": 1_000_000, "2026-06-09": 2_000_000,
                       "2026-05-21": 0}, got
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



# ── 8. 배치(D-399 레인 D) — run_job · 계약별 격리 · 입력 없음 abort · 기본 입력 위치 · 이름 겹침 ──
# 기대값 = 소유자 11-24 '실패 계정 있는 날 = 성공 계정만 생성' · 계획 레인 D '판정 없는 계약 = 건너뛰고 보고' ·
# '입력 자체가 없을 때만 중단' · '같은 이름 파일 = 덮어쓰기 금지·이름 규칙 유지' · 인터페이스 {"ok","skipped","files","abort"}.
def _batch_dir(base: Path, judge: dict | None = JUDGE, contracts=CONTRACTS) -> dict:
    """위탁정산서 결과·상품군 정산서·셀독 입력 폴더(기본 위치 = root 아래 output/정산서/입력_셀독) 합성 → run_job opts."""
    from coupang_analytics import settlement_seldoc_groups as G
    from coupang_analytics import statement_jobs_seldoc as JOB
    st, gs = base / "위탁", base / "상품군"
    st.mkdir()
    gs.mkdir()
    make_statement(st / "정산서_가나상사_김가나_ga1_관리상품.xlsx", "가나상사 (대표 김가나)", "ga1", 3_000_000, 1_000_000, 0,
                   months=[("2026-06", 4_000_000, "끝남")], prods=[("보냉백 YG1", 300, 4_000_000)])
    for doc, done in ((DOC_B1, 1_000_000), (DOC_B2, 2_000_000), (DOC_ZS, 700_000), (DOC_B3, 0)):
        make_statement(G.group_path(gs, "da1", doc), "다라커머스 (대표 이다라)", "da1", done, 0, 0)
    inp = JOB.default_inputs(base)
    inp.parent.mkdir(parents=True)
    make_inputs(inp.parent, judge)                                        # → base\output\정산서\입력_셀독
    make_db(inp / "계약서_정밀분석_DB_전수_v6.xlsx", contracts)
    return {"root": base, "statements": st, "group_statements": gs, "out": base / "out", "basis": "2026-11-03", "issued": "2026-11-12",
            "accounts": ["ga1", "da1"]}


def _dates(files) -> dict:
    return {openpyxl.load_workbook(f).active["F13"].value: openpyxl.load_workbook(f).active["F5"].value for f in files}


def _reasons(res: dict) -> dict:
    return {s["id"]: s["reason"] for s in res["skipped"]}


def test_batch_shape() -> None:
    """run_job 꼴 = {"ok","skipped","files","abort"} · 기본 입력 위치(--db·--seldoc-inputs 없이) · 손 실행과 같은 5장."""
    from coupang_analytics import statement_jobs_seldoc as JOB
    with tempfile.TemporaryDirectory() as d:
        opts = _batch_dir(Path(d))
        logs: list = []
        res = JOB.run_job(opts, logs.append)
        assert {"ok", "skipped", "files", "abort"} <= set(res) and res["abort"] is None, res
        assert all(isinstance(x, str) for x in res["ok"] + res["files"]) and res["skipped"] == [], res
        assert sorted(res["ok"]) == sorted(f"{a}:{x}" for a, x in (("ga1", DOC_A), ("da1", DOC_ZS), ("da1", DOC_B1), ("da1", DOC_B2), ("da1", DOC_B3)))
        assert len(res["files"]) == 5 and all(Path(f).is_file() and Path(f).parent == opts["out"] for f in res["files"])
        assert _dates(res["files"]) == {"2026-05-14": 4_000_000, "2026-01-09": 700_000, "2026-03-27": 1_000_000, "2026-06-09": 2_000_000,
                                        "2026-05-21": 0}
        assert any("셀독 정산서 5개" in x for x in logs), logs
        auto = JOB.run_job({**opts, "accounts": None, "out": Path(d) / "out2"}, logs.append)    # 계정 안 줌 = 판정표·이름 후보 계정 전부
        assert auto["abort"] is None and len(auto["files"]) == 5, auto
    print("test_batch_shape OK")


def test_batch_isolate() -> None:
    """판정 없는 계약 1건·규칙 밖 후보·결정 대기·위탁정산서 없음 → 그 계약만 skipped · 나머지 생성(strict 손 실행 = 아무것도 안 만듦)."""
    from coupang_analytics import statement_jobs_seldoc as JOB
    judge = json.loads(json.dumps(JUDGE))
    del judge["계약"][DOC_B3]                                                 # da1 계약 하나 판정 없음
    with tempfile.TemporaryDirectory() as d:
        opts = _batch_dir(Path(d), judge)
        strict = JOB.run_job({**opts, "strict": True}, lambda _m: None)
        assert strict["abort"] and "시작 전 중단" in strict["abort"] and DOC_B3 in strict["abort"] and strict["files"] == [], strict
        assert not opts["out"].exists()                                       # 중단 = 파일 안 만듦(손 실행 그대로)
        res = JOB.run_job(opts, lambda _m: None)
        assert res["abort"] is None, res
        why = _reasons(res)
        assert list(why) == [f"da1:{DOC_B3}"] and "판정 없음" in why[f"da1:{DOC_B3}"], why
        assert _dates(res["files"]) == {"2026-05-14": 4_000_000, "2026-01-09": 700_000, "2026-03-27": 1_000_000, "2026-06-09": 2_000_000}
    # 한 계약 계정에 미확정 후보(규칙 밖 유형)가 있음 = 계약 수를 모름 → 계정 전체 숫자를 그 계약에 몰지 않음(상품군 정산서만)
    odd = CONTRACTS + [_contract("eeeeeeee-0000-0000-0000-000000000001", "물품 공급(납품) 계약", "2026-01-01", None, "가나상사", "", 1)]
    with tempfile.TemporaryDirectory() as d:
        opts = _batch_dir(Path(d), JUDGE, odd)
        res = JOB.run_job(opts, lambda _m: None)
        why = _reasons(res)
        assert "소유자 결정 대기(규칙 밖 유형 확정)" in why["ga1:eeeeeeee-0000-0000-0000-000000000001"], why
        assert "상품군 정산서 없음" in why[f"ga1:{DOC_A}"], why                     # 위탁정산서(계정 전체)로 만들지 않음
        assert len(res["files"]) == 4 and all("가나" not in Path(f).name for f in res["files"]), res
    # 판정표 '확인 필요' + 결정대기 = '확인 필요 — 소유자 결정 대기(항목)' 로 건너뜀 · 결정대기 없는 '확인 필요' = 알림만(예전처럼 뺌)
    judge = json.loads(json.dumps(JUDGE))
    judge["계약"][DOC_ZS] = {"계정ID": "da1", "판정": "확인 필요", "판정_원래": "대상", "결정대기": "투자형 양식", "근거": "x"}
    judge["계약"][DOC_B3] = {"계정ID": "da1", "판정": "확인 필요", "근거": "계정 매칭 불확실"}
    with tempfile.TemporaryDirectory() as d:
        opts = _batch_dir(Path(d), judge)
        os_ = Path(opts["statements"]) / "정산서_가나상사_김가나_ga1_관리상품.xlsx"
        os_.unlink()                                                          # ga1 위탁정산서 없음(정산 받기 실패 계정) = ga1 만 건너뜀
        res = JOB.run_job(opts, lambda _m: None)
        why = _reasons(res)
        assert why[f"da1:{DOC_ZS}"].startswith("확인 필요 — 소유자 결정 대기(투자형 양식)"), why
        assert why[f"da1:{DOC_B3}"].startswith("확인 필요 — ") and "계정 매칭 불확실" in why[f"da1:{DOC_B3}"], why
        assert "위탁정산서 0개" in why[f"ga1:{DOC_A}"], why
        assert _dates(res["files"]) == {"2026-03-27": 1_000_000, "2026-06-09": 2_000_000}, res
        strict = JOB.run_job({**opts, "strict": True, "out": Path(d) / "o2"}, lambda _m: None)
        assert strict["abort"] and strict["files"] == [], strict              # 결정 대기·위탁정산서 없음 = 손 실행은 중단
    print("test_batch_isolate OK")


def test_batch_groups_isolate() -> None:
    """상품군 정산서를 이번에 만들 때 그 입력을 못 읽음 = 계약 여럿 계정만 skipped · 한 계약 계정은 생성 · 옛 상품군 파일을 쓰지 않음."""
    from coupang_analytics import settlement_seldoc_groups as G
    from coupang_analytics import statement_jobs_seldoc as JOB
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        opts = _batch_dir(base)
        miss = base / "없는입력"
        res = JOB.run_job({**opts, "groups": {"managed_output": miss, "settle_dir": miss, "stats": miss / "s.xlsx", "inputs": miss}},
                          lambda _m: None)
        assert res["abort"] is None, res
        why = _reasons(res)
        assert sorted(why) == sorted(f"da1:{x}" for x in (DOC_ZS, DOC_B1, DOC_B2, DOC_B3)), why
        assert all("상품군 정산서 못 만듦" in v for v in why.values()), why
        assert _dates(res["files"]) == {"2026-05-14": 4_000_000}, res        # group_statements 의 옛 파일은 안 씀
        bad = JOB.run_job({**opts, "groups": {"모름": 1}, "out": base / "o2"}, lambda _m: None)
        assert bad["abort"] and "상품군 인자" in bad["abort"], bad
    # 상품 배정 — 미확정(held) 같은 계정 계약에 배정된 상품 = 통과(파일은 안 만듦) · 결정 대기 상품 = 사유 그대로
    judged = {"P1": {"문서ID": DOC_B1}, "P2": {"문서ID": DOC_B2}, "P9": {"문서ID": None, "판정": "확인 필요", "결정대기": "나머지 상품 배정 규칙"}}
    assert G.assign({"P1", "P2"}, judged, [DOC_B1, DOC_B2]) == {DOC_B1: {"P1"}, DOC_B2: {"P2"}}
    msg = _raises(G.assign, {"P1", "P9", "P4"}, judged, [DOC_B1, DOC_B2], word="소유자 결정 대기(나머지 상품 배정 규칙)")
    assert "P4 상품군 판정 없음" in msg and "P9" in msg, msg                  # 문제 상품 전부를 한 번에
    print("test_batch_groups_isolate OK")


def test_batch_abort() -> None:
    """입력 자체가 없을 때만 abort — 판정표·대응표·계약 DB 사본 없음 · DB 사본 2개 · '관리대상' 칸 없음 · root 모름 · 날짜 틀림."""
    from coupang_analytics import statement_jobs_seldoc as JOB
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        opts = _batch_dir(base, None)                                         # 판정표 없음
        inp = JOB.default_inputs(base)
        res = JOB.run_job(opts, lambda _m: None)
        assert res["abort"] and "판정표" in res["abort"] and not res["files"] and not opts["out"].exists(), res
        (inp / "셀독_계약상품군_판정.json").write_text(json.dumps(JUDGE, ensure_ascii=False), encoding="utf-8")
        db = inp / "계약서_정밀분석_DB_전수_v6.xlsx"
        db.rename(base / "옮김.xlsx")
        cases = [("계약 DB 사본", {}), ("root", {"root": None}), ("계약 DB", {"db": base / "없음.xlsx"}), ("ValueError", {"basis": "2026-13-01", "db": base / "옮김.xlsx"})]
        for word, extra in cases:
            res = JOB.run_job({**opts, **extra}, lambda _m: None)
            assert res["abort"] and word in res["abort"] and res["abort"].startswith("시작 전 중단") and not res["files"], (word, res)
        make_db(inp / "계약서_정밀분석_DB_전수_v5.xlsx")
        make_db(inp / "계약서_정밀분석_DB_전수_v6.xlsx")
        res = JOB.run_job(opts, lambda _m: None)
        assert res["abort"] and "2개" in res["abort"], res                   # 사본이 여럿 = 어느 것인지 모름
        (inp / "계약서_정밀분석_DB_전수_v5.xlsx").unlink()
        old = base / "old.xlsx"
        make_db(old, head=HEAD[:-1])
        res = JOB.run_job({**opts, "db": old}, lambda _m: None)               # --db 덮어쓰기 · '관리대상' 칸 없는 옛 DB = abort
        assert res["abort"] and "관리대상" in res["abort"], res
        (inp / "사업자_대응표.csv").unlink()
        res = JOB.run_job(opts, lambda _m: None)
        assert res["abort"] and "사업자_대응표" in res["abort"], res
        assert not opts["out"].exists()
    print("test_batch_abort OK")


def test_batch_names() -> None:
    """같은 이름 = 덮어쓰기 금지·이름 규칙 유지 → 이번 실행에서 같은 이름이 되는 계약 = 모두 skipped · 이미 있는 파일 = skipped(내용 그대로)."""
    from coupang_analytics import settlement_seldoc_source as SS
    from coupang_analytics import statement_jobs_seldoc as JOB
    twin = "bbbbbbbb-0000-0000-0000-00000000000a"
    rows = CONTRACTS + [_contract(twin, "셀독 상품공급 OEM", "2026-03-27", None, "이다라", None, 5_000_000)]   # B1 과 같은 날·같은 첫 품목
    judge = json.loads(json.dumps(JUDGE))
    judge["계약"][twin] = {"계정ID": "da1", "판정": "대상", "근거": "x"}
    with tempfile.TemporaryDirectory() as d:
        opts = _batch_dir(Path(d), judge, rows)
        wb = openpyxl.load_workbook(JOB.find_db(JOB.default_inputs(Path(d))))
        wb["품목"].append([twin, "f", "수영장 HW1", "수영장", "HW1", 1, 1, 1, None, "1쪽"])
        wb.save(JOB.find_db(JOB.default_inputs(Path(d))))
        from coupang_analytics import settlement_seldoc_groups as G
        make_statement(G.group_path(opts["group_statements"], "da1", twin), "다라커머스 (대표 이다라)", "da1", 5, 0, 0)
        res = JOB.run_job(opts, lambda _m: None)
        why = _reasons(res)
        assert sorted(why) == sorted([f"da1:{DOC_B1}", f"da1:{twin}"]) and all("이름이 계약 2건" in v for v in why.values()), why
        assert len(res["files"]) == 4, res
        assert JOB.file_name(SS.Job("da1", SS.load_contracts(JOB.find_db(JOB.default_inputs(Path(d))))[DOC_B1], True, ("다라커머스", "이다라")),
                             "2026-11-03", "261112_000000") == "셀독정산서_이다라_260327_수영장_HW1_20261103기준_261112_000000.xlsx"
    with tempfile.TemporaryDirectory() as d:                                  # 이미 있는 파일(같은 초에 다시 실행 등)
        opts = _batch_dir(Path(d))
        stamp = "261112_101010"
        import coupang_analytics.statement_jobs_seldoc as M
        real = M.datetime

        class _Fixed(real):
            @classmethod
            def now(cls, tz=None):
                return real(2026, 11, 12, 10, 10, 10)
        M.datetime = _Fixed
        try:
            first = JOB.run_job(opts, lambda _m: None)
            target = Path(first["files"][0])
            before = target.read_bytes()
            again = JOB.run_job(opts, lambda _m: None)
        finally:
            M.datetime = real
        assert all(stamp in Path(f).name for f in first["files"]) and len(first["files"]) == 5, first
        assert again["files"] == [] and len(again["skipped"]) == 5, again
        assert all("같은 이름 파일 있음(덮지 않음)" in s["reason"] for s in again["skipped"]), again
        assert target.read_bytes() == before                                  # 덮어쓰지 않음
    print("test_batch_names OK")


def test_batch_inputs_install() -> None:
    """셀독 입력 1회 준비 = 복사만(원본 그대로) · 같은 내용 = 그대로 · 다른 내용·다른 DB 사본 = 거부(덮지 않음) · 명령줄 inputs."""
    from coupang_analytics import settlement_seldoc_source as SS
    from coupang_analytics import statement_jobs_seldoc as JOB
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        src = make_inputs(base, JUDGE)
        db = make_db(base / "계약서_정밀분석_DB_전수_v6.xlsx")
        dest = JOB.default_inputs(base / "운용")
        code, log = _run(["inputs", "--from", str(src), "--db", str(db), "--to", str(dest)])
        assert code == 0 and log.count("복사") == 3, log
        assert sorted(p.name for p in dest.iterdir()) == sorted([SS.JUDGE, "사업자_대응표.csv", db.name])
        assert (src / SS.JUDGE).is_file() and db.is_file()                    # 원본 그대로
        assert all(x.startswith("같음") for x in JOB.install_inputs(dest, src, db))
        (src / SS.JUDGE).write_text("{}", encoding="utf-8")
        _raises(JOB.install_inputs, dest, src, db, word="내용이 다름")
        assert json.loads((dest / SS.JUDGE).read_text(encoding="utf-8")) == JUDGE    # 덮지 않음
        v7 = make_db(base / "계약서_정밀분석_DB_전수_v7.xlsx")
        _raises(JOB.install_inputs, dest, src, v7, word="다른 계약 DB 사본")
        _raises(JOB.install_inputs, dest, src, make_db(base / "db.xlsx"), word="이름")
    with tempfile.TemporaryDirectory() as d:                                   # 유형 판정표(소유자 11-24 '제안대로 확정')가 있으면 함께 복사
        base = Path(d)                                                         # (빠지면 규칙 밖 유형의 대상 계약이 안 만들어짐 · T-179 재현)
        src = make_inputs(base, JUDGE)
        (src / SS.TYPES).write_text('{"유형": {"운영대행": {"판정": "대상", "근거": "x"}}}', encoding="utf-8")
        db = make_db(base / "계약서_정밀분석_DB_전수_v6.xlsx")
        dest = JOB.default_inputs(base / "운용")
        JOB.install_inputs(dest, src, db)
        assert SS.load_types(dest) == SS.load_types(src) != {}
        assert all(x.startswith("같음") for x in JOB.install_inputs(dest, src, db))
        (src / SS.TYPES).write_text('{"유형": {}}', encoding="utf-8")
        _raises(JOB.install_inputs, dest, src, db, word="내용이 다름")
    print("test_batch_inputs_install OK")


# ── 9. 소유자 11-24 결정 4건(통제 세션 전달 · 질문 카드 원문) ──
# ① 투자형 = '카드에 약정·지급완료 표시'(도달률 대신 약정·지급 완료·남은 지급) ② 규칙 밖 36유형 = '제안대로 확정'(유형 판정표 · 확인 필요 = 건너뜀)
# ③ "관리대장에도 없는 상품은 오류임. 확인필요 탬에 넣어줘." + "확인필요는 로그를 분석해야 만 인식됨" → skipped 에 상품명·금액·사유
# ④ rladygks0221 = '두 장 다' · 상계 관계는 비고
def test_decision_types() -> None:
    from coupang_analytics import settlement_seldoc_source as SS
    from coupang_analytics import statement_jobs_seldoc as JOB
    e1, e2, e3 = ("eeeeeeee-0000-0000-0000-00000000000" + x for x in "123")
    rows = CONTRACTS + [_contract(e1, "물품 공급(납품) 계약", "2026-01-01", None, "가나상사", "", 1),
                        _contract(e2, "유튜브 광고 영상 제작", "2026-01-02", None, "가나상사", "", 1),
                        _contract(e3, "운영대행", "2026-01-03", None, "가나상사", "", 1)]
    types = {"유형": {"물품 공급(납품) 계약": {"판정": "대상", "근거": "x"}, "유튜브 광고 영상 제작": {"판정": "제외", "근거": "x"},
                      "운영대행": {"판정": "확인 필요", "근거": "x"}}}
    judge = json.loads(json.dumps(JUDGE))
    judge["계약"][e1] = {"계정ID": "ga1", "판정": "대상", "근거": "x"}
    with tempfile.TemporaryDirectory() as d:
        opts = _batch_dir(Path(d), judge, rows)
        inp = JOB.default_inputs(Path(d))
        no = _reasons(JOB.run_job(opts, lambda _m: None))                      # 유형 판정표 없음 = 규칙 밖 3건 그대로 건너뜀(결정 대기)
        assert all(f"ga1:{x}" in no and "규칙 밖 유형 확정" in no[f"ga1:{x}"] for x in (e1, e2, e3)), no
        (inp / SS.TYPES).write_text(json.dumps(types, ensure_ascii=False), encoding="utf-8")
        assert SS.target_kind(SS.load_contracts(JOB.find_db(inp))[e1], SS.load_types(inp)) == "대상"
        res = JOB.run_job({**opts, "out": Path(d) / "o2"}, lambda _m: None)
        why = _reasons(res)
        assert f"ga1:{e2}" not in why, why                                                  # 제외 확정 = 뺌(대상 확정 e1 = 아래 상품군 단계까지 감)
        assert why[f"ga1:{e3}"].startswith("확인 필요 — ") and "유형 판정표 '확인 필요'" in why[f"ga1:{e3}"], why                          # 확인 필요 유형 = 그 계약만 건너뜀
        assert "상품군 정산서 없음" in why[f"ga1:{e1}"] and "상품군 정산서 없음" in why[f"ga1:{DOC_A}"], why   # ga1 계약 여럿 = 상품군만
        (inp / SS.TYPES).write_text(json.dumps({"유형": {"운영대행": {"판정": "몰라"}}}, ensure_ascii=False), encoding="utf-8")
        bad = JOB.run_job({**opts, "out": Path(d) / "o3"}, lambda _m: None)
        assert bad["abort"] and "유형 판정표" in bad["abort"], bad                           # 모양 틀림 = 중단
    print("test_decision_types OK")


def test_decision_invest_note() -> None:
    from coupang_analytics import statement_jobs_seldoc as JOB
    judge = json.loads(json.dumps(JUDGE))
    judge["계약"][DOC_A].update({"양식": "투자형", "지급완료": 8_000_000, "지급근거": "송금대조 확실 2건"})
    judge["계약"][DOC_B1]["비고"] = "2026-06-19 조기 종료된 계약의 정산종료금액 26,000,000원을 이 계약 계약금에서 상계함"
    with tempfile.TemporaryDirectory() as d:
        res = JOB.run_job(_batch_dir(Path(d), judge), lambda _m: None)
        assert res["abort"] is None and len(res["files"]) == 5, res
        sheets = {openpyxl.load_workbook(f).active["F13"].value: openpyxl.load_workbook(f).active for f in res["files"]}
        ws = sheets["2026-05-14"]                                                         # 투자형 = 카드 약정·지급 완료·지급율·남은 지급
        c = _cells(ws)
        assert (ws["A4"].value, ws["F4"].value, ws["K4"].value, ws["P4"].value) == ("약정 지급 총액", "지급 완료", "지급율", "남은 지급")
        assert (ws["A5"].value, ws["F5"].value, ws["P5"].value) == (10_000_000, 8_000_000, 2_000_000) and abs(ws["K5"].value - .8) < 1e-12
        assert ws["A8"].value == "지급율  80.0%" and "약정 지급 총액" in c.values() and "목표 정산 총액" not in c.values()
        assert _right_of(ws, _find(c, "정산 기준 실적", 12), "Q") == 4_000_000                 # 쿠팡 정산 요약은 그대로(따로 나란히)
        _assert_page(openpyxl.load_workbook(res["files"][0]))
        b1 = sheets["2026-03-27"]
        cb = _cells(b1)
        assert _right_of(b1, _find(cb, "비고"), "F") == judge["계약"][DOC_B1]["비고"] and b1["A4"].value == "목표 정산 총액"
        assert "비고" not in _cells(sheets["2026-06-09"]).values()                          # 비고 없는 계약 = 줄 없음
    judge["계약"][DOC_A].pop("지급완료")
    with tempfile.TemporaryDirectory() as d:
        why = _reasons(JOB.run_job(_batch_dir(Path(d), judge), lambda _m: None))
        assert "투자형인데 판정표 '지급완료' 금액 없음" in why[f"ga1:{DOC_A}"], why            # 지급 완료 모름 = 0 으로 그리지 않음
    print("test_decision_invest_note OK")


def test_decision_products_structured() -> None:
    from coupang_analytics import settlement_seldoc_groups as G
    from coupang_analytics import settlement_seldoc_source as SS
    from coupang_analytics import statement_jobs_seldoc as JOB
    judged = {"P1": {"문서ID": DOC_B1}, "P7": {"상품명": "기저귀가방 CL02", "문서ID": None, "판정": "확인 필요", "사유": "관리대장에 없음(오류)",
                                               "판매금액": 123_000}}
    try:
        G.assign({"P1", "P7", "P8"}, judged, [DOC_B1])
        raise AssertionError("ProductError 안 남")
    except SS.ProductError as exc:
        assert exc.items == [("P7", "확인 필요 — 관리대장에 없음(오류)", "기저귀가방 CL02", 123_000), ("P8", "판정 없음", None, None)], exc.items
    r = JOB._Result()
    r.skip("da1", "", "da1 관리 상품 P7 — 확인 필요 — 관리대장에 없음(오류)", product=("P7", "기저귀가방 CL02", 123_000))
    r.skip("da1", DOC_B1, "da1 계약 … 판정 없음")
    got = r.out()["skipped"]
    assert got[0]["id"] == "da1:상품:P7" and got[0]["kind"] == "확인 필요" and (got[0]["상품명"], got[0]["금액"]) == ("기저귀가방 CL02", 123_000)
    assert "관리대장에 없음(오류)" in got[0]["사유"] and got[0]["doc_id"] is None
    assert got[1]["id"] == f"da1:{DOC_B1}" and got[1]["doc_id"] == DOC_B1 and got[1]["product_id"] is None
    keys = {"id", "reason", "kind", "aid", "doc_id", "product_id", "상품명", "금액", "사유", "account", "contract", "product", "amount"}
    assert all(set(x) == keys for x in got), got
    # 레인 A 약속(D399_레인A 문서 '추가') — 확인 필요 탭 칸 account·contract·product·amount 가 빈 칸이 아님
    assert (got[0]["account"], got[0]["product"], got[0]["amount"]) == ("da1", "기저귀가방 CL02", 123_000), got[0]
    assert (got[1]["account"], got[1]["contract"]) == ("da1", DOC_B1), got[1]
    print("test_decision_products_structured OK")


def test_decision_invest_left_check() -> None:
    """통제 판단 11-24(D-221 ② 소유자 "계약자에게 송부해야 하는데 … 시각적으로 직관적이어야 함" · 시트에 내부용 글자 없음 + D-399
    "성공 계정만 생성"): 투자형 약정−지급 차이의 근거가 없음(판정표 '남은지급확인' = 사유) = 고객용 셀독 정산서를 만들지 않는다 ·
    그 계약만 skipped(kind 확인 필요 · 사유 한 줄) → 확인 필요 탭 · 다른 계약은 그대로 만듦 · 손 실행(strict) = 중단."""
    from coupang_analytics import settlement_seldoc_sheet as SH
    from coupang_analytics import statement_jobs_seldoc as JOB
    judge = json.loads(json.dumps(JUDGE))
    why = "회차 지급액이 약정보다 적은 사유 원문 없음"
    judge["계약"][DOC_A].update({"양식": "투자형", "지급완료": 9_802_000, "남은지급확인": why})
    with tempfile.TemporaryDirectory() as d:
        opts = _batch_dir(Path(d), judge)
        res = JOB.run_job(opts, lambda _m: None)
        assert res["abort"] is None and len(res["files"]) == 4 and f"ga1:{DOC_A}" not in res["ok"], res
        assert all(openpyxl.load_workbook(f).active["F13"].value != "2026-05-14" for f in res["files"]), res["files"]
        for f in res["files"]:                                                    # 만든 정산서 어디에도 내부용 글자 없음
            vals = [str(v) for v in _cells(openpyxl.load_workbook(f).active).values()]
            assert not any(w in v for v in vals for w in INTERNAL), (f, [v for v in vals if any(w in v for w in INTERNAL)])
        row = next(x for x in res["skipped"] if x["id"] == f"ga1:{DOC_A}")
        assert row["kind"] == "확인 필요" and why in row["사유"] and row["doc_id"] == DOC_A and len(res["skipped"]) == 1, res["skipped"]
        strict = JOB.run_job({**opts, "strict": True, "out": Path(d) / "o2"}, lambda _m: None)
        assert strict["abort"] and why in strict["abort"] and strict["files"] == [], strict
    assert "left_check" not in inspect.signature(SH.write).parameters                # 시트에 사유 글자를 쓰는 길 자체가 없음
    judge["계약"][DOC_A].pop("남은지급확인")
    with tempfile.TemporaryDirectory() as d:                                       # 사유 없음 = 남은 지급 금액 그대로(예전과 같음)
        res = JOB.run_job(_batch_dir(Path(d), judge), lambda _m: None)
        ws = next(openpyxl.load_workbook(f).active for f in res["files"] if openpyxl.load_workbook(f).active["F13"].value == "2026-05-14")
        assert ws["P5"].value == 198_000 and res["skipped"] == [], res
    print("test_decision_invest_left_check OK")


def _batch_opts(base: Path, opts: dict) -> dict:
    """배치 실행기(레인 A `statement_batch._job_opts`)가 셀독 단계에 넘기는 칸 그대로 — JSON 으로 건너가 경로 = 글자 · 위탁 단계 결과 = consignor."""
    from types import SimpleNamespace
    from coupang_analytics import statement_batch as SB
    blog = SimpleNamespace(run_id="251125_000000", path=base / "배치.log")
    o = SB._job_opts("2026-11-25", base / "배치_251125_000000", blog, base / "정산" / "정산집계_x.xlsx", {"이다라-다라커머스-da1": "받기 실패"})
    o.update({"managed_output": str(base / "output"), "settle_dir": str(base / "정산"), "inputs": str(base / "입력"),
              "seldoc_inputs": str(opts["root"] / "output" / "정산서" / "입력_셀독"), "basis": opts["basis"], "issued": opts["issued"],
              "out": str(base / "배치_251125_000000" / "seldoc"),
              "consignor": {"ok": ["ga1", "da1"], "skipped": [], "files": [], "abort": None, "state": "정상", "out": str(opts["statements"])}})
    return json.loads(json.dumps(o, ensure_ascii=False))


def test_batch_contract() -> None:
    """레인 A 약속(D399_레인A_run_job_입력약속) 그대로 넘겨도 셀독 정산서가 나온다(T-177) — statements = consignor.out · 상품군 = 배치 칸에서 만듦
    (경로 글자 → Path) · 정산 받기 실패 계정 = skipped · 위탁 단계 중단 = abort(옛 동작 = 배치 꼴이면 KeyError 'statements' 로 0장)."""
    from coupang_analytics import settlement_seldoc_groups as G
    from coupang_analytics import statement_jobs_seldoc as JOB
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        opts = _batch_dir(base)
        seen: dict = {}

        def fake_run(args, jobs, judge, out_dir, held, on_log):
            seen["args"] = args
            return [("da1", doc, G.group_path(Path(opts["group_statements"]), "da1", doc), 0) for doc in (DOC_B1, DOC_B2, DOC_ZS, DOC_B3)], {}, {}
        real, G.run = G.run, fake_run
        try:
            bo = _batch_opts(base, opts)
            res = JOB.run_job(bo, lambda _m: None)
            solo = JOB.run_job({k: v for k, v in bo.items() if k not in ("skip_accounts",)} | {"skip_accounts": {}, "out": str(base / "o2")}, lambda _m: None)
        finally:
            G.run = real
        assert res["abort"] is None, res
        a = seen["args"]
        assert all(isinstance(getattr(a, k), Path) for k in ("managed_output", "settle_dir", "stats", "inputs")), a
        assert str(a.stats).endswith("정산집계_x.xlsx") and a.account_history is None and a.settle_only is None, a   # 원장 = 구글 실시간(사본 안 씀)
        why = _reasons(res)
        assert "받기 실패" in why["da1"] and not any(x.startswith("da1") for x in res["ok"]), why
        assert len(res["files"]) == 1 and Path(res["files"][0]).parent == Path(bo["out"]), res      # ga1 한 장(위탁 결과 폴더에서)
        assert len(solo["files"]) == 5 and solo["abort"] is None, solo                                # 실패 계정 없으면 5장(상품군도 배치 칸에서)
        for bad in ({"abort": "정산집계 없음"}, {"state": "중단", "out": str(opts["statements"])}, {}):
            got = JOB.run_job({**bo, "consignor": bad, "out": str(base / "o3")}, lambda _m: None)
            assert got["abort"] and "위탁정산서 단계 중단" in got["abort"] and got["files"] == [], got
    print("test_batch_contract OK")


def test_groups_judge_marks() -> None:
    """통제 판단 11-24(D-400 ②·③): 판정 '제외' 상품 = 어느 계약에도 안 넣고 계정을 안 막음 · '판정표 갱신 필요' = 대장에 없는데 배정됨/
    '관리대장에 없음'인데 지금 대장에 있음(배정은 그대로)."""
    from coupang_analytics import settlement_seldoc_groups as G
    judged = {"P1": {"문서ID": DOC_B1}, "P2": {"문서ID": None, "판정": "제외", "사유": "맞는 계약 = 제외 유형"},
              "P3": {"문서ID": None, "판정": "확인 필요", "사유": "관리대장에 없음(오류)"}}
    assert G.assign({"P1", "P2"}, judged, [DOC_B1]) == {DOC_B1: {"P1"}}
    assert [x[0] for x in G.unassigned({"P1", "P2", "P3"}, judged, [DOC_B1])] == ["P3"]
    got = G.stale({"P1", "P2", "P3"}, judged, {"P3"})
    assert [(p, why.startswith("판정표 갱신 필요")) for p, why, *_ in got] == [("P1", True), ("P3", True)], got
    assert G.stale({"P1", "P3"}, judged, {"P1"}) == [], "어긋남 없음 = 줄 없음"
    # ③ '근거 없음' + 실제 계산 0 = 안 막음 · 대장에 없음(오류 D-400 ③)·판정 없음·소유자 결정 대기·금액 있음 = 예전처럼 막음
    judged.update({"P4": {"문서ID": None, "판정": "확인 필요", "사유": "관리대장에 있음 · 어느 계약 상품인지 근거 없음"},
                   "P5": {"문서ID": None, "판정": "확인 필요", "사유": "x", "결정대기": "y"}})
    sales: dict = {}
    real = G.GroupAccount, G._effect
    G.GroupAccount, G._effect = (lambda _c, _a, pids, _b, _i: pids), (lambda pids: any(sales.get(x) for x in pids))
    try:
        def free(*pids):
            return G.free_pids(None, "", None, {}, G.unassigned(set(pids), judged, [DOC_B1]), judged)
        assert free("P1", "P2", "P4") == {"P4"}
        assert free("P3") == free("P5") == free("P9") == free("P1") == set()
        assert free("P3", "P4") == set()                                          # 막는 상품이 하나라도 있으면 그 계정은 그대로 막힘
        sales["P4"] = 1
        assert free("P4") == set()
    finally:
        G.GroupAccount, G._effect = real
    print("test_groups_judge_marks OK")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    test_rules()
    test_read_statement()
    test_plan()
    test_managed()
    test_groups()
    test_sheet()
    test_sheet_goal()
    test_cli()
    test_labels_match_book()
    test_batch_shape()
    test_batch_isolate()
    test_batch_groups_isolate()
    test_batch_abort()
    test_batch_names()
    test_batch_inputs_install()
    test_decision_types()
    test_decision_invest_note()
    test_decision_products_structured()
    test_decision_invest_left_check()
    test_batch_contract()
    test_groups_judge_marks()
    print("✅ 셀독 정산서 시험 21종 통과(규칙·읽기·대상 계약·관리대상 계약·상품군·양식 1장·목표수익금·입구·칸 이름"
          "·배치 꼴·계약별 격리·상품군 격리·입력 없음 중단·이름 겹침·입력 준비·유형 판정·투자형 카드·비고·상품 단위 확인 필요"
          "·투자형 남은 지급 근거 없음 = 정산서 안 만듦·배치 꼴 그대로·판정 제외와 판정표 갱신 필요)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
