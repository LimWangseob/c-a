"""위탁자 정산서 3차 형식(구글시트) 시험 — 오프라인 · 결정적 · 구글 API·네트워크·로그인 없음(T-38 · 계획 S1).

기대값 = 계획서 3절 S1 검산 규칙·결정 문장에서 손으로 정함(코드에서 뽑지 않음):
  ① 숫자 쪽: 누적 반올림 칸 합 = 목표 · 상품표 열 합 = 1쪽 1~8(확정 전 포함) · 금액 전혀 없는 상품 뺌 · 판매 금액 큰 순 ·
     6 종류별 합 = 1쪽 6(누적 반올림 · 끝전 줄 없음) · 검산 1원 이상 차이만 실패 · 판정표 파일 없음 = judgments 사유(조용히 넘기지 않음).
  ①-2 고정 형식(D-343 · 승인 샘플 `output\\_샘플_261118_고정형식정산서\\` 11-19 "샘플 승인."): 6 종류별 9줄 · 9 계정 공통 9줄 · 10 별도 입금 2줄 ·
     어디로 갔나요 4줄 = 계정·달과 상관없이 같은 이름·순서 · 값 0 = 공란 · '이번 기간 없음'·'끝전' 없음 · 상품 줄 = 2쪽에 다 들어가면 2쪽, 아니면
     전부 3쪽부터(2쪽엔 '상품 n개 — 상품별 줄은 3쪽부터' + 합계) · 한 쪽 최대 이름 한 줄 상품 35개 / 회색 줄 함께 19개 ·
     로켓그로스 리뷰 이벤트(PostPurchase) = 9 '리뷰 이벤트' 줄에 원문 값(D-324 ①④).
  ①-3 예상값(T-121 · 인계 44줄): 입력(BI 플랜·유료 시작일 · 세이버 끝날 · 할인표 · 접수채널)이 없으면 숫자 0개 · 금액 있는 9 '비즈니스 인사이트'
     줄에만 비고 '입력 없음 → 예상값 미확정' · 쿠팡 줄 없는 기간(그 채널 전체 마지막 지급 줄 끝 다음 날 ~ min(달 끝, 기준일 전날) ∩ 그 달) = 근거에만 ·
     금액·다른 줄 변화 0.
  ② 그리기 쪽(합성 자료 2개 · 정산 예정 포함/확정): 검산 통과 · 칸 범위·병합 겹침 없음 · 쪽 높이 = 쪽 수 × A4 · 쪽 경계 = 행 경계 ·
     결정 문구(D-241 ⑦ 문의 없음 · D-242 머리 · D-251 회색 줄 · D-259 1쪽 · D-260 '판매 기간 … · 발행' 굵게 · '검토용' 없음) ·
     넘치면 다음 쪽(D-241 ④ · '(계속)' 머리 · 줄 빠짐·중복 없음) · 나눌 수 없는 큰 묶음 = 중단 · 검산 실패 = 쓰기 0회 ·
     여러 판매 달 = 쓰기 거부(D-241 ⑥).
  ③ 입구(tools/settlement_consignor.py): 계정ID 고르기(없는 ID = 중단) · 검산 합치기 · --sheet 는 --month 와 함께만.

    python tools/verify_consignor_statement_offline.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coupang_analytics import settlement_consignor_gsheet as GS  # noqa: E402
from coupang_analytics import settlement_consignor_month as CM  # noqa: E402
from coupang_analytics.settlement_consignor_gsheet_layout import MARGIN, PAGE_H, StatementLayoutError  # noqa: E402
from coupang_analytics.settlement_consignor_month_calc import cum_round  # noqa: E402
from coupang_analytics import settlement_statement_account as AC  # noqa: E402
from coupang_analytics import settlement_fee_rules as FR  # noqa: E402
from coupang_analytics.settlement_consignor_month_cost import BI_CAT, KINDS, PEND_KIND, _rg_notes, expect_values  # noqa: E402
from coupang_analytics.settlement_consignor_month_dep import flow  # noqa: E402
from coupang_analytics.settlement_consignor_month_out import LINE_NAMES, common_out, coupang_by_cat, product_table, rg_kinds  # noqa: E402

ISSUED = "2026-11-18"
# 고정 줄(기대 = 승인 샘플 `_render_fixed_sample.py` KIND_ROWS·COMMON_ROWS·SEP_ROWS·FLOW_ROWS 의 정산서 이름 · 코드에서 뽑지 않음)
FIX_KINDS = ["입출고비 (창고에 넣고 꺼냄)", "고객 배송비", "보관비 (오래 둘수록 비쌈)", "바코드 붙이기", "반품 회수비", "반품 재입고비",
             "창고에서 빼내는 비용 (반출)", "반출 배송비", "종류별 내역 전 (정산 예정·쿠팡 미확정)"]
FIX_COMMON = ["판매자서비스이용료", "로켓그로스 세이버 구독료", "비즈니스 인사이트 이용료", "쿠팡 라이브 수수료", "리뷰 이벤트 (체험단)",
              "3PM 매출채권", "채권추심", "상품 표시 없는 창고·운송·보상 비용", "그 밖의 쿠팡 공제"]
FIX_SEP = ["우대수수료 환급 (관리 상품 몫)", "우대수수료 환급 (상품 확인 전 · 계정 전체)"]
FIX_FLOW = ["쿠팡 입금 완료", "빠른정산으로 먼저 받음", "쿠팡 입금 예정", "쿠팡페이 환급"]


def _tool():
    spec = importlib.util.spec_from_file_location("settlement_consignor_tool", ROOT / "tools" / "settlement_consignor.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeClient:
    """요청을 모으기만 하는 시트 클라이언트(GSheetClient 모양: meta · batch_update)."""

    def __init__(self, old_ids=(0, 1000, 1001)):
        self.calls: list[list[dict]] = []
        self._old = list(old_ids)

    def meta(self, refresh: bool = False) -> dict:
        return {"sheets": [{"properties": {"sheetId": s, "title": f"old{s}"}} for s in self._old]}

    def batch_update(self, requests: list[dict]) -> dict:
        self.calls.append(json.loads(json.dumps(requests)))
        return {}


# ── 합성 자료(손으로 맞춘 금액 · 실제 계정·사람 아님) ──────────────────
def _product(name: str, cols: list[int], pend: list[int] | None = None) -> dict:
    p: dict = {"name": name, **{f"c{k}": cols[k - 1] for k in range(1, 9)}, "subtotal": sum(cols)}
    if pend and any(pend):
        p["pending"] = {**{f"c{k}": pend[k - 1] for k in range(1, 9)}, "subtotal": sum(pend)}
    return p


def synthetic(pending: bool = True, month: str = "2026-09") -> dict:
    """1~8 = 상품 2개 열 합 · 상품 정산액 748,000 · 9 반영 −33,000 · 10 +1,500 → 이번 정산 금액 716,500 ·
    정산 예정 포함이면 확정 전 168,400(1 +200,000 · 3 −21,600 · 6 −10,000)."""
    a = [600_000, -10_000, -64_800, 3_000, -30_000, -50_000, -7_000, 3_000]
    b = [400_000, 0, -43_200, 2_000, -20_000, -30_000, -5_000, 0]
    pa = [200_000, 0, -21_600, 0, 0, -10_000, 0, 0] if pending else [0] * 8
    lines = [{"no": k, "name": LINE_NAMES[k - 1], "amount": a[k - 1] + b[k - 1], "pending": pa[k - 1]} for k in range(1, 9)]
    kinds = [{"name": n, "amount": 0} for n in FIX_KINDS]
    kinds[0]["amount"], kinds[1]["amount"] = -50_000, -20_000 - (0 if pending else 10_000)
    kinds[-1].update(amount=-10_000 if pending else 0, pending=True)
    common = [{"key": f"k{i}", "name": n, "coupang_amount": 0, "applied_amount": 0} for i, n in enumerate(FIX_COMMON)]
    common[0].update(coupang_amount=55_000, applied_amount=-33_000)
    fl = [{"name": n, "desc": "합성", "amount": 0} for n in FIX_FLOW]
    fl[0]["amount"], fl[2]["amount"] = (548_100, 168_400) if pending else (716_500, 0)
    deps = [{"date": f"{month}-10", "desc": "1주 판매 정산", "amount": 300_000}, {"date": f"{month}-17", "desc": "2주 판매 정산", "amount": 248_100},
            {"date": f"{month}-24", "desc": "3주 판매 정산" + (" (예정)" if pending else ""), "amount": 168_400}]
    return {"account": "synth01", "company": "합성상회", "ceo": "합성 위탁자", "period_start": f"{month}-01", "period_end": f"{month}-30",
            "basis_date": "2026-11-15", "status": "정산 예정 포함" if pending else "확정", "lines": lines, "product_subtotal": 748_000,
            "products": [_product("합성 상품 가", a, pa), _product("합성 상품 나", b)], "rg_kinds": kinds,
            "common": {"items": common,
                       "basis_text": "판매 비중 60.0% · 등록 비중 2/5=40.0% 중 작은 쪽 40.0%", "total_coupang": 55_000, "total_applied": -33_000},
            "separate": [{"name": FIX_SEP[0], "amount": 1_500}, {"name": FIX_SEP[1], "amount": 0}], "settle_amount": 716_500,
            "pending_total": 168_400 if pending else 0, "pending_detail": [{"방법": "합성"}] if pending else [],
            "flow": fl, "deposits": deps, "checks": [], "judgments": []}


# ── ① 숫자 쪽 ─────────────────────────────────────────────────
def test_cum_round() -> None:
    assert cum_round([0.4, 0.4, 0.4], 1) == [0, 1, 0]
    assert sum(cum_round([1.25, 2.25, -0.75, 3.5], 6)) == 6
    assert cum_round([], 0) == []


def test_product_table() -> None:
    cols: dict = defaultdict(lambda: [0.0] * 9)
    pend: dict = defaultdict(lambda: [0.0] * 9)
    cols["p1"][1:] = [100.4, -1.2, -10.6, 0.3, 0, -5.5, 0, 0]
    cols["p2"][1:] = [300.4, 0, -30.4, 0.3, -2.5, 0, 0, 0]
    cols["p3"][1:] = [100.4, 0, -10.4, 0.3, 0, 0, 0, 0]
    pend["p3"][1:] = [50.4, 0, -5.4, 0, 0, 0, 0, 0]
    st = SimpleNamespace(cols=cols, pend=pend)
    t = product_table(st, {"가": ["p1"], "나": ["p2"], "다": ["p3"], "빈": ["p0"]})
    assert t["names"] == ["나", "가", "다"], t["names"]             # 판매 금액 큰 순 · 같으면 이름 순 · 금액 없는 '빈' 뺌
    for k in range(1, 9):
        exp = round(sum(cols[p][k] for p in ("p1", "p2", "p3")))
        assert t["lines8"][k] == exp == sum(t["int"][n][k] for n in t["names"]), (k, t["lines8"][k], exp)
        assert t["pend8"][k] == sum(t["pint"][n][k] for n in t["names"])
    assert t["lines8"][1] == 501 and t["pend8"][1] == 50 and t["lines8"]["E"] == 501 - 1 - 51 + 1


def test_rg_kinds() -> None:
    """D-343: 늘 9줄(이름·순서 고정 · 값 없으면 0) · 끝전 줄 없음 — 원 단위는 누적 반올림으로 종류 줄 안(합 = 1쪽 6)."""
    kinds: dict = defaultdict(float, {KINDS[0][0]: 0.6, KINDS[1][0]: 0.6})
    got = rg_kinds(SimpleNamespace(kinds=kinds, j=[]), -1)
    assert [x["name"] for x in got] == FIX_KINDS, got
    assert sum(x["amount"] for x in got) == -1 and [x["amount"] for x in got[2:]] == [0] * 7, got
    assert got[-1]["pending"] and not any(x.get("pending") for x in got[:-1])
    kinds[PEND_KIND] = 3.0
    got = rg_kinds(SimpleNamespace(kinds=kinds, j=[]), -4)
    assert len(got) == 9 and got[-1] == {"name": PEND_KIND, "amount": -3, "pending": True}, got
    assert rg_kinds(SimpleNamespace(kinds=defaultdict(float), j=[]), 0) == [{"name": n, "amount": 0, **({"pending": True} if n == PEND_KIND else {})} for n in FIX_KINDS]


def test_common_fixed() -> None:
    """D-343: 9 계정 공통 = 고정 9줄(이름·순서) · 없는 항목 0 · 항목마다 비중(D-271 정액 3종 = 등록 비중) 반올림 뒤 줄로 합침 · 금액 0 항목 뺌."""
    st = SimpleNamespace(share=0.5, reg_share=0.4, common=[
        ("윙 지급 차감 — 판매자서비스이용료", 11_000.0, "w:" + AC.SVC),                       # 정액 → 등록 비중 0.4
        ("로켓그로스 세이버 구독료", 9_900.0, "o:subscriptionFeeOffsetYearMonthBreakdown"),
        ("윙 지급 차감 — 리뷰 이벤트", 2_220.0, "w:리뷰 이벤트"),
        ("윙 지급 차감 — 채권추심", 1_000.0, "w:채권추심"),
        ("창고·배송비 중 쿠팡이 상품을 표시하지 않은 금액 (x)", 300.0, "cfs"),
        ("재고 보상 중 쿠팡이 상품을 표시하지 않은 금액", -100.0, "comp"),
        ("윙 지급 차감 — 기타 공제", 50.0, "w:기타 공제"),
        ("광고비 중 쿠팡이 상품을 표시하지 않은 금액", 100.0, "ad"),
        ("반올림 0", 0.2, "w:기타 공제")])
    items, applied = common_out(st)
    assert [x["name"] for x in items] == FIX_COMMON, items
    got = {x["name"]: (x["coupang_amount"], x["applied_amount"]) for x in items}
    assert got == {"판매자서비스이용료": (11_000, -4_400), "로켓그로스 세이버 구독료": (9_900, -3_960), "비즈니스 인사이트 이용료": (0, 0),
                   "쿠팡 라이브 수수료": (0, 0), "리뷰 이벤트 (체험단)": (2_220, -1_110), "3PM 매출채권": (0, 0), "채권추심": (1_000, -500),
                   "상품 표시 없는 창고·운송·보상 비용": (200, -100), "그 밖의 쿠팡 공제": (150, -75)}, got
    assert sum(applied) == sum(x["applied_amount"] for x in items) == -10_145 and len(applied) == len(st.common_items) == 8


def test_post_purchase() -> None:
    """D-324 ①④: 로켓그로스 리뷰 이벤트 공제(totalPostPurchaseDeductionAmount) = 원문 값 → 9 '리뷰 이벤트' 줄 · 날짜별 표 위치 · 판단 문장만 쓰던 것 없앰."""
    st = SimpleNamespace(own=defaultdict(float), common=[], loc=defaultdict(list), j=[], share=0.5, reg_share=0.4,
                         pend_line=lambda row, r: False, ad={"deducted": 0}, milk={"deducted": 0},
                         cfs={"line_fees": 0, "adjust": 0, "pending": 0}, comp={"paid": 0})
    key = ("2026-11-10", "2026-10-01", "2026-10-07", "로켓그로스", "")
    _rg_notes(st, key, list(key), {"totalPostPurchaseDeductionAmount": 8_880.0})
    assert not [j for j in st.j if "PostPurchase" in j], st.j
    items, _ = common_out(st)
    review = next(x for x in items if x["name"] == "리뷰 이벤트 (체험단)")
    assert (review["coupang_amount"], review["applied_amount"]) == (8_880, -4_440), review
    cat = st.common_items[0][2]
    assert st.loc[cat] == [(key, 8_880.0)] and coupang_by_cat(st)[cat] == 8_880


def _line(ch: str, s: str, e: str) -> tuple:
    row = ["", "", "2026-12-01", s, e, "70"]
    return (row[2], s, e, ch, row[5]), row, {"채널": ch}


def _expect_st(m: str, basis: str, common: list, lines: list) -> SimpleNamespace:
    return SimpleNamespace(m=m, basis=basis, common=common, j=[], share=0.5, reg_share=0.4, lines=lambda: iter(lines))


def test_expect_values() -> None:
    """T-121: 입력 없음 = 숫자 없이 비고 · 9 BI 줄(금액 있음)에만 비고 · 줄 없는 기간 = 근거만 · 금액 변화 0."""
    lines = [_line("로켓그로스", "2026-10-01", "2026-10-26"), _line("윙", "2026-10-01", "2026-10-31"), _line("윙", "2026-09-28", "2026-09-30")]
    st = _expect_st("2026-10", "2026-11-15", [("비즈니스 인사이트 이용료", 20_228.0, BI_CAT), ("윙 지급 차감 — 판매자서비스이용료", 55_000.0, "w:" + AC.SVC)], lines)
    expect_values(st)
    assert FR.NO_INPUT in st.bi_note and "SV-BI-SUB" in st.bi_note, st.bi_note
    assert any("20,228" in j and FR.NO_INPUT in j for j in st.j), st.j
    assert set(st.expect) == {"74 비즈니스 인사이트 남은 청구", "45·76 보관비(세이버 체험 · 시작 창 B=A)", "신규-03 입출고비·배송비 할인가"}, st.expect
    assert all(v["예상값"] is None and FR.NO_INPUT in v["비고"] for v in st.expect.values()), st.expect
    assert st.expect["45·76 보관비(세이버 체험 · 시작 창 B=A)"]["기간"] == "2026-10-27~2026-10-31"     # 윙 = 달 끝까지 줄 있음 → 4 없음
    items, applied = common_out(st)
    notes = {x["name"]: x.get("note") for x in items}
    assert notes.pop("비즈니스 인사이트 이용료") == st.bi_note and not any(notes.values()), notes
    bi = next(x for x in items if x["key"] == "bi")
    assert (bi["coupang_amount"], bi["applied_amount"]) == (20_228, -8_091) and sum(applied) == -8_091 - 22_000, (bi, applied)
    # 이번 달(기준일 11-15) · BI 조각 없음 · 윙 줄 11-09 까지 → 4 = R1 + '판매자 접수면 편도일 수 있음' · 로켓그로스 줄 없음(채널 안 씀) → 45·76 없음
    st = _expect_st("2026-11", "2026-11-15", [], [_line("윙", "2026-11-03", "2026-11-09")])
    expect_values(st)
    assert st.bi_note == "" and st.j == [] and list(st.expect) == ["4 반품배송비(구매확정 전 · 고객 귀책)"], st.expect
    e4 = st.expect["4 반품배송비(구매확정 전 · 고객 귀책)"]
    assert e4["기간"] == "2026-11-10~2026-11-14" and "판매자 접수면 편도일 수 있음" in e4["비고"] and FR.NO_INPUT in e4["비고"], e4
    assert all(x.get("note") is None for x in common_out(st)[0])
    # 이번 달 첫 주 · 그 달 줄 0개지만 채널은 씀(앞 달 줄) → 달 1일부터 · 기준일이 달 1일 = 줄 없는 기간 없음
    st = _expect_st("2026-11", "2026-11-05", [], [_line("로켓그로스", "2026-10-27", "2026-10-31")])
    expect_values(st)
    assert st.expect["신규-03 입출고비·배송비 할인가"]["기간"] == "2026-11-01~2026-11-04", st.expect
    st = _expect_st("2026-11", "2026-11-01", [], [_line("로켓그로스", "2026-10-27", "2026-10-31")])
    expect_values(st)
    assert st.expect == {}, st.expect
    # 지난 달 구멍(그 주 판매 없음 · 뒤 줄 있음) = 줄 없는 기간 아님 — 기간 = 채널 전체 마지막 줄 끝 뒤(구매확정 전·이번 주 D-279 ③)
    st = _expect_st("2026-08", "2026-11-15", [], [_line("윙", "2026-08-03", "2026-08-09"), _line("윙", "2026-11-02", "2026-11-08")])
    expect_values(st)
    assert st.expect == {}, st.expect


def test_flow_fixed() -> None:
    """D-343: 어디로 갔나요 = 늘 4줄(값 없으면 0)."""
    st = SimpleNamespace(basis="2026-11-15")
    rows = [{"date": "2026-10-10", "desc": "쿠팡 입금 완료", "amount": 1_000, "_status": "지급 완료"}]
    got = flow(st, rows)
    assert [x["name"] for x in got] == FIX_FLOW and [x["amount"] for x in got] == [1_000, 0, 0, 0], got


def test_failed_checks() -> None:
    cash = "검산(실제 = 정산금액 − 공제 − 판매 조정)"
    d = {"checks": [{"검사": "a", "차이": 0}, {"검사": "b", "차이": 0.6}, {"검사": "c", "차이": -1}, {"검사": "참고", cash: 2}]}
    assert [c["검사"] for c in CM.failed_checks(d)] == ["c", "참고"]


def test_load_judge() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        j = CM.load_judge(inputs=Path(tmp))
        assert j.added == {} and j.names == {} and len(j.notes) == 2, j.notes
        (Path(tmp) / CM.NAMES_FILE).write_text(json.dumps({"_설명": "x", "aid1": [{"표시 이름": "가"}]}, ensure_ascii=False), encoding="utf-8")
        j = CM.load_judge(inputs=Path(tmp))
        assert j.names == {"aid1": [{"표시 이름": "가"}]} and len(j.notes) == 1


def test_sale_months_2025_excluded() -> None:
    """D-328·D-329: 판매 달(매출인식·구매확정)이 2025 = 정산 밖 → 판매 달 목록에도 없음(상품별 월별·정산 예정 둘 다)."""
    def prow(ym: str, wing: int) -> dict:
        return {"월(매출인식)": ym, "윙 판매액": wing, "로켓그로스 매출금액": 0, "쿠팡 정산금액 합계(부가비용 차감 전)": 0}
    src = {"prows": [prow("2025-12", 5_000), prow("2026-01", 3_000), prow("2026-02", 0)],
           "u": [("로켓그로스", "2025-11", 1_000, 900, "예정", ""), ("윙", "2026-03", 2_000, 1_800, "예정", ""),
                 ("윙", "-", 0, 0, "자료 없음", "")]}
    assert CM.sale_months(src) == ["2026-01", "2026-03"], CM.sale_months(src)


# ── ② 그리기 쪽 ───────────────────────────────────────────────
def _grid(reqs: list[dict]) -> tuple[int, int]:
    gp = reqs[0]["updateSheetProperties"]["properties"]["gridProperties"]
    return gp["rowCount"], gp["columnCount"]


def _overlap(a: dict, b: dict) -> bool:
    return (a["startRowIndex"] < b["endRowIndex"] and b["startRowIndex"] < a["endRowIndex"]
            and a["startColumnIndex"] < b["endColumnIndex"] and b["startColumnIndex"] < a["endColumnIndex"])


def _range_errors(t, nr: int, nc: int) -> tuple[list[str], list]:
    errs, merges = [], []
    for i, r in enumerate(t.requests):
        kind = next(iter(r))
        if kind not in ("mergeCells", "updateBorders"):
            continue
        rg = r[kind]["range"]
        if rg["sheetId"] != t.gid:
            errs.append(f"{t.title} 요청 {i} 다른 탭 {rg['sheetId']}")
        if not (0 <= rg["startRowIndex"] < rg["endRowIndex"] <= nr and 0 <= rg["startColumnIndex"] < rg["endColumnIndex"] <= nc):
            errs.append(f"{t.title} 요청 {i} {kind} 범위 밖 {rg}")
        if kind == "mergeCells":
            merges.append((i, rg))
    return errs, merges


def _size_errors(t, nr: int, nc: int) -> list[str]:
    errs = []
    for r in t.requests:
        if "updateDimensionProperties" in r:
            rg = r["updateDimensionProperties"]["range"]
            if not (0 <= rg["startIndex"] < rg["endIndex"] <= (nr if rg["dimension"] == "ROWS" else nc)):
                errs.append(f"{t.title} 크기 요청 범위 밖 {rg}")
        if "updateCells" in r:
            rows = r["updateCells"]["rows"]
            if len(rows) != nr or any(len(x["values"]) != nc for x in rows):
                errs.append(f"{t.title} updateCells 크기 ≠ 시트 {nr}×{nc}")
    return errs


def structure_errors(plan) -> list[str]:
    """칸 범위 ⊂ 시트 크기 · updateCells 행·열 수 = 시트 크기 · 병합 겹침 없음 · 요청이 모두 자기 탭."""
    errs: list[str] = []
    for t in plan.tabs:
        nr, nc = _grid(t.requests)
        e, merges = _range_errors(t, nr, nc)
        errs += e + _size_errors(t, nr, nc)
        for k, (i, a) in enumerate(merges):
            errs += [f"{t.title} 병합 겹침 요청 {i} · {j}" for j, b in merges[k + 1:] if _overlap(a, b)]
    return errs


def _row_heights(reqs: list[dict]) -> list[int]:
    return [r["updateDimensionProperties"]["properties"]["pixelSize"] for r in reqs
            if "updateDimensionProperties" in r and r["updateDimensionProperties"]["range"]["dimension"] == "ROWS"]


def page_errors(plan) -> list[str]:
    """위탁자 탭: 높이 = 쪽 수 × (PAGE_H + 위아래 여백) · 쪽 경계 = 행 경계 · 쪽마다 첫·끝 행 = 여백."""
    sheet, errs = PAGE_H + 2 * MARGIN, []
    for t in (t for t in plan.tabs if t.kind == "consignor"):
        hs = _row_heights(t.requests)
        if sum(hs) != t.pages * sheet:
            errs.append(f"{t.title} 높이 {sum(hs)} ≠ {t.pages}쪽 × {sheet}")
        bounds = [0]
        for h in hs:
            bounds.append(bounds[-1] + h)
        idx = {b: i for i, b in enumerate(bounds)}
        for p in range(t.pages):
            top, bottom = idx.get(p * sheet), idx.get((p + 1) * sheet)
            if top is None or bottom is None:
                errs.append(f"{t.title} {p + 1}쪽 경계가 행 경계 아님")
            elif hs[top] != MARGIN or hs[bottom - 1] != MARGIN:
                errs.append(f"{t.title} {p + 1}쪽 위아래 여백 ≠ {MARGIN}")
    return errs


def texts(reqs: list[dict]) -> list[tuple[str, list]]:
    out = []
    for r in reqs:
        for row in r.get("updateCells", {}).get("rows", []):
            for v in row["values"]:
                uv = v.get("userEnteredValue", {})
                s = uv.get("stringValue") or uv.get("formulaValue")
                if s:
                    out.append((s, v.get("textFormatRuns", [])))
    return out


def _bold_at(text: str, runs: list, prefix: str) -> bool:
    i, fmt = text.find(prefix), None
    for r in runs:
        if r.get("startIndex", 0) <= i:
            fmt = r["format"]
    return bool(fmt and fmt.get("bold"))


def _consignor_text_errors(t, tx: list, joined: str) -> list[str]:
    errs = []
    pend = t.data.get("status") == "정산 예정 포함"
    if pend and "쿠팡 미확정 금액 포함" not in joined:
        errs.append(f"{t.title}: 1쪽 '쿠팡 미확정 금액 포함' 없음(D-259)")
    if any(p.get("pending") for p in t.data["products"]) and "└ 정산 예정(쿠팡 미확정)" not in joined:
        errs.append(f"{t.title}: 2쪽 '└ 정산 예정(쿠팡 미확정)' 없음(D-251)")
    if pend and f"자료 기준일 {t.data['basis_date']} · 정산 예정 포함" not in joined:
        errs.append(f"{t.title}: 머리 '자료 기준일 · 정산 예정 포함' 없음(D-242)")
    bolds = [_bold_at(s, runs, "판매 기간") for s, runs in tx if "판매 기간" in s and "발행" in s]
    if not bolds or not all(bolds):
        errs.append(f"{t.title}: '판매 기간 … · 발행 …' 줄 굵지 않음 {bolds}(D-260)")
    return errs


def decision_text_errors(plan) -> list[str]:
    errs = []
    for t in plan.tabs:
        tx = texts(t.requests)
        joined = "\n".join(s for s, _ in tx)
        errs += [f"{t.title}: '{bad}' 글자 있음" for bad in ("검토용", "문의", "확정 전 금액", "아직 반영 안 된") if bad in joined]
        if t.kind == "consignor":
            errs += _consignor_text_errors(t, tx, joined)
    return errs


def test_render() -> None:
    ds = [synthetic(True), {**synthetic(False), "account": "synth02", "ceo": "합성 위탁자 둘"}]
    for d in ds:
        assert GS.check(d) == [], (d["account"], GS.check(d))
    plan = GS.build_statement(ds, ISSUED)
    assert [t.kind for t in plan.tabs] == ["summary", "consignor", "consignor"] and [t.gid for t in plan.tabs] == [1000, 1001, 1002]
    assert plan.tabs[0].member_gids == [1001, 1002] and plan.tabs[1].title == "9월 합성 위탁자 (synth01)"
    errs = structure_errors(plan) + page_errors(plan) + decision_text_errors(plan)
    assert not errs, errs
    fake = FakeClient()
    GS.write_statement(fake, ds, ISSUED)
    setup = fake.calls[0]
    assert [next(iter(r)) for r in setup] == ["addSheet"] + ["deleteSheet"] * 3 + ["addSheet"] * 3 + ["deleteSheet"]
    assert len(fake.calls) == 1 + len(plan.tabs)


def test_overflow() -> None:
    """상품 40·입금 25줄을 0원으로 늘림(합계 불변) → 3쪽 이상 · 쪽 높이 지킴 · '(계속)' 머리 · 줄 빠짐·중복 없음 · 합계 줄 1번."""
    d = synthetic(True)
    d["products"] += [_product(f"합성 넘침 {i:02d} 이름이 조금 긴 상품 (옵션 포함)", [0] * 8) for i in range(40)]
    d["deposits"] += [{"date": "2026-09-30", "desc": f"합성 입금 {i}", "amount": 0} for i in range(25)]
    plan = GS.build_statement([d], ISSUED)
    t = plan.tabs[1]
    assert t.pages >= 3, t.pages
    assert not (page_errors(plan) + structure_errors(plan))
    cells = [s for s, _ in texts(t.requests)]
    assert "정산 상세 (계속)" in cells
    assert all(sum(s.startswith(f"합성 넘침 {i:02d} ") for s in cells) == 1 for i in range(40))
    assert all(cells.count(f"합성 입금 {i}") == 1 for i in range(25))
    assert cells.count("합계 (= 1쪽)") == 2 and cells.count("상품") >= 2     # 상품 3쪽부터 → 2쪽 합계 + 상품 쪽 합계(승인 샘플)


def _relines(d: dict, prods: list[dict]) -> dict:
    """상품 줄을 바꾸고 1~8·6 종류별·정산 금액·어디로 갔나요·입금 내역을 그 합에 맞춤(검산 통과 유지)."""
    d = json.loads(json.dumps(d))
    d["products"] = prods
    for x in d["lines"]:
        x["amount"] = sum(p[f"c{x['no']}"] for p in prods)
        x["pending"] = sum((p.get("pending") or {}).get(f"c{x['no']}", 0) for p in prods)
    L6, P6 = d["lines"][5]["amount"], d["lines"][5]["pending"]
    for k in d["rg_kinds"]:
        k["amount"] = P6 if k.get("pending") else 0
    d["rg_kinds"][0]["amount"] = L6 - P6
    d["product_subtotal"] = sum(p["subtotal"] for p in prods)
    d["settle_amount"] = d["product_subtotal"] + d["common"]["total_applied"] + sum(x["amount"] for x in d["separate"])
    d["pending_total"] = sum(x["pending"] for x in d["lines"])
    d["status"], d["pending_detail"] = ("정산 예정 포함", [{"방법": "합성"}]) if d["pending_total"] else ("확정", [])
    for f in d["flow"]:
        f["amount"] = 0
    d["flow"][0]["amount"] = d["settle_amount"]
    d["deposits"] = [{"date": "2026-09-10", "desc": "합성 입금", "amount": d["settle_amount"]}]
    return d


def _labels(t) -> list[str]:
    """정산서에서 계정·달마다 같아야 하는 글자(숫자·상품명·날짜·회사 뺌)."""
    fixed = set(FIX_KINDS + FIX_COMMON + FIX_SEP + FIX_FLOW)
    return [s for s, _ in texts(t.requests) if s in fixed]


def test_fixed_render() -> None:
    """D-343: 확정·정산 예정 두 계정 = 고정 줄 이름·순서 같음 · 고정 줄 모두 있음 · 값 0 = 공란(숫자 0 칸 없음) · '이번 기간 없음'·'끝전' 없음 · 바닥 문구."""
    a = synthetic(True)
    b = {**synthetic(False), "account": "synth02", "ceo": "합성 위탁자 둘"}
    b["separate"] = [{"name": FIX_SEP[0], "amount": 0}, {"name": FIX_SEP[1], "amount": 1_500}]
    plan = GS.build_statement([a, b], ISSUED)
    ta, tb = plan.tabs[1], plan.tabs[2]
    assert _labels(ta) == _labels(tb) and sorted(set(_labels(ta))) == sorted(set(FIX_KINDS + FIX_COMMON + FIX_SEP + FIX_FLOW)), _labels(ta)
    for t in (ta, tb):
        joined = "\n".join(s for s, _ in texts(t.requests))
        assert "이번 기간 없음" not in joined and "끝전" not in joined, t.title
        assert "금액이 없는 항목은 비워 두었습니다" in joined and "쿠팡 미확정 금액 포함" in joined and "별도 입금 포함" in joined, t.title
        zeros = [v for r in t.requests for row in r.get("updateCells", {}).get("rows", []) for v in row["values"]
                 if v.get("userEnteredValue", {}).get("numberValue") == 0]
        assert not zeros, (t.title, len(zeros))
    bad = {**a, "rg_kinds": a["rg_kinds"][:2] + [{"name": "끝전", "amount": a["lines"][5]["amount"] - sum(k["amount"] for k in a["rg_kinds"][:2])}]}
    try:                                                    # 옛 가변 자료(줄이 생기고 빠짐) = 그리지 않고 중단
        GS.build_statement([bad], ISSUED)
        raise AssertionError("고정 형식 아닌 자료인데 그려짐(D-343)")
    except StatementLayoutError:
        pass


def _prods(n: int, pend: bool) -> list[dict]:
    return [_product(f"합성 상품 {i:02d}", [1_000, 0, -100, 0, 0, 0, 0, 0], [1_000, 0, -100, 0, 0, 0, 0, 0] if pend else None) for i in range(n)]


def test_product_pages() -> None:
    """상품 줄 쪽 규칙(승인 샘플): 2쪽에 다 들어가면 2쪽(모두 2쪽) · 아니면 전부 3쪽부터 + 2쪽 안내 · 상품 쪽 한 장 = 이름 한 줄 35개 / 회색 함께 19개."""
    base = synthetic(False)
    for n, pend, pages in ((2, False, 2), (9, True, 3), (35, False, 3), (36, False, 4), (19, True, 3), (20, True, 4)):
        d = _relines(base, _prods(n, pend))
        assert GS.check(d) == [], GS.check(d)
        plan = GS.build_statement([d], ISSUED)
        t = plan.tabs[1]
        cells = [s for s, _ in texts(t.requests)]
        assert t.pages == pages, (n, pend, t.pages)
        assert not (page_errors(plan) + structure_errors(plan)), (n, pend)
        moved = any(f"상품 {n}개 — 상품별 줄은 3쪽부터" in s for s in cells)
        assert moved == (pages > 2), (n, pend, moved)
        assert all(cells.count(f"합성 상품 {i:02d}") == 1 for i in range(n)), (n, pend)
        assert cells.count("합계 (= 1쪽)") == (2 if moved else 1) and cells.count("└ 정산 예정(쿠팡 미확정)") == (2 if moved else 1) + (n if pend else 0)


def test_unsplittable() -> None:
    """한 줄이 한 쪽보다 큼(나눌 수 없음) = 중단(무한 반복 없음)."""
    d = synthetic(True)
    d["products"][1]["name"] = "합성 아주 긴 상품 이름 " * 300
    try:
        GS.build_statement([d], ISSUED)
    except StatementLayoutError:
        return
    raise AssertionError("한 쪽보다 큰 줄인데 중단 안 됨(무한 반복 위험)")


def test_check_reject() -> None:
    d = synthetic(True)
    d["settle_amount"] += 1
    assert len(GS.check(d)) >= 3, GS.check(d)            # 정산 금액 · 어디로 갔나요 · 입금 내역
    fake = FakeClient()
    try:
        GS.write_statement(fake, [d], ISSUED)
        raise AssertionError("검산 실패인데 쓰기 예외 없음")
    except GS.StatementCheckError:
        pass
    assert fake.calls == []


def test_multi_month() -> None:
    fake = FakeClient()
    try:
        GS.write_statement(fake, [synthetic(True), synthetic(False, "2026-10")], ISSUED)
        raise AssertionError("여러 판매 달인데 쓰기 거부 안 됨(D-241 ⑥)")
    except GS.StatementCheckError:
        pass
    assert fake.calls == []


# ── ③ 입구 ────────────────────────────────────────────────────
def test_tool() -> None:
    T = _tool()
    accts = ["홍길동-합성상회-aaa1", "김합성-다른상회-bbb2"]
    assert T.pick_accounts(accts, []) == accts and T.pick_accounts(accts, ["bbb2"]) == ["김합성-다른상회-bbb2"]
    try:
        T.pick_accounts(accts, ["ccc3"])
        raise AssertionError("없는 계정ID 인데 중단 안 됨")
    except ValueError:
        pass
    d = synthetic(True)
    assert T.statement_failures(d) == []
    d["checks"] = [{"검사": "합성 검사", "차이": 2}]
    d["settle_amount"] += 1
    got = T.statement_failures(d)
    assert got[0] == "합성 검사 차이 2" and len(got) >= 4, got
    base = ["--out", "o", "--managed-output", "m", "--settle-dir", "s", "--stats", "x.xlsx", "--basis", "2026-11-15"]
    assert T._args(base + ["--month", "2026-09", "--sheet", "id"]).month == "2026-09"
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            T._args(base + ["--sheet", "id"])
        raise AssertionError("--sheet 가 --month 없이 통과")
    except SystemExit:
        pass
    err = io.StringIO()
    try:                                                    # 2025 판매 달 = 정산 밖(D-328) — 손으로 줘도 만들지 않음
        with contextlib.redirect_stderr(err):
            T._args(base + ["--month", "2025-12"])
        raise AssertionError("--month 2025-12 가 통과(D-328)")
    except SystemExit:
        assert "D-328" in err.getvalue(), err.getvalue()
    assert T._args(base + ["--month", "2026-01"]).month == "2026-01"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    for f in (test_cum_round, test_product_table, test_rg_kinds, test_common_fixed, test_post_purchase, test_expect_values, test_flow_fixed, test_failed_checks, test_load_judge,
              test_sale_months_2025_excluded, test_render, test_fixed_render, test_product_pages, test_overflow, test_unsplittable, test_check_reject,
              test_multi_month, test_tool):
        f()
    print("✅ 위탁자 정산서 3차 형식 시험(숫자 반올림·상품표 열 합·종류별 9줄·검산 기준 · 그리기 구조·쪽 높이·결정 문구·넘침·검산/여러 달 거부 · 입구 · D-343 고정 형식(고정 줄·공란·쪽 규칙)·D-324 리뷰 이벤트) 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
