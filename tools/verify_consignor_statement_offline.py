"""위탁자 정산서 3차 형식(구글시트) 시험 — 오프라인 · 결정적 · 구글 API·네트워크·로그인 없음(T-38 · 계획 S1).

기대값 = 계획서 3절 S1 검산 규칙·결정 문장에서 손으로 정함(코드에서 뽑지 않음):
  ① 숫자 쪽: 누적 반올림 칸 합 = 목표 · 상품표 열 합 = 1쪽 1~8(확정 전 포함) · 금액 전혀 없는 상품 뺌 · 판매 금액 큰 순 ·
     6 종류별 합 = 1쪽 6(누적 반올림 · 끝전 줄 없음) · 검산 1원 이상 차이만 실패 · 판정표 파일 없음 = judgments 사유(조용히 넘기지 않음).
  ①-2 고정 형식(D-343 · 승인 샘플 `output\\_샘플_261118_고정형식정산서\\` 11-19 "샘플 승인."): 6 종류별 9줄 · 9 계정 공통 9줄 · 10 별도 입금 3줄(우대수수료 2 + 추가지급 1 · 소유자 11-19 "줄 추가 (추천)") ·
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
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coupang_analytics import settlement_consignor_gsheet as GS  # noqa: E402
from coupang_analytics import settlement_consignor_gsheet_pages as GS_PAGES  # noqa: E402
from coupang_analytics import settlement_consignor_month as CM  # noqa: E402
from coupang_analytics.settlement_consignor_gsheet_layout import MARGIN, PAGE_H, StatementLayoutError  # noqa: E402
from coupang_analytics.settlement_consignor_month_calc import cum_round  # noqa: E402
from coupang_analytics import settlement_statement_account as AC  # noqa: E402
from coupang_analytics import settlement_fee_rules as FR  # noqa: E402
from coupang_analytics.settlement_consignor_month_calc import AD_NOCAMP, ads  # noqa: E402
from coupang_analytics.settlement_consignor_month_cost import BI_CAT, KINDS, PEND_KIND, _rg_notes, expect_values  # noqa: E402
from coupang_analytics.settlement_consignor_month_dep import _cost_locs, dep_rows, flow  # noqa: E402
from coupang_analytics.settlement_consignor_month_milk import milk_months  # noqa: E402
from coupang_analytics.settlement_consignor_month_sep import separate  # noqa: E402
from coupang_analytics.settlement_consignor_month_wingad import ad_months  # noqa: E402
from coupang_analytics.settlement_consignor_month_out import LINE_NAMES, _product_row, common_out, coupang_by_cat, product_table, rg_kinds  # noqa: E402

ISSUED = "2026-11-18"
# 고정 줄(기대 = 승인 샘플 `_render_fixed_sample.py` KIND_ROWS·COMMON_ROWS·SEP_ROWS·FLOW_ROWS 의 정산서 이름 · 코드에서 뽑지 않음)
FIX_KINDS = ["입출고비 (창고에 넣고 꺼냄)", "고객 배송비", "보관비 (오래 둘수록 비쌈)", "바코드 붙이기", "반품 회수비", "반품 재입고비",
             "창고에서 빼내는 비용 (반출)", "반출 배송비", "종류별 내역 전 (정산 예정·쿠팡 미확정)"]
FIX_COMMON = ["판매자서비스이용료", "로켓그로스 세이버 구독료", "비즈니스 인사이트 이용료", "쿠팡 라이브 수수료", "리뷰 이벤트 (체험단)",
              "3PM 매출채권", "채권추심", "상품 표시 없는 창고·운송·보상 비용", "그 밖의 쿠팡 공제"]
FIX_SEP = ["우대수수료 환급 (관리 상품 몫)", "우대수수료 환급 (상품 확인 전 · 계정 전체)",
           "추가지급 (관리 상품 몫)"]         # 셋째 줄 = 소유자 11-19 "줄 추가 (추천)"(T-125 A1 · 통제 전달)
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
            "separate": [{"name": FIX_SEP[0], "amount": 1_500}, {"name": FIX_SEP[1], "amount": 0}, {"name": FIX_SEP[2], "amount": 0}],
            "settle_amount": 716_500,
            "pending_total": 168_400 if pending else 0, "pending_detail": [{"방법": "합성"}] if pending else [],
            "flow": fl, "deposits": deps, "checks": [], "judgments": [], "remarks": [], "_근거": {"적용 비중": 0.4}}


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
    st = SimpleNamespace(cols=cols, pend=pend, pend_wing=Counter({"p3": 20.4}))
    t = product_table(st, {"가": ["p1"], "나": ["p2"], "다": ["p3"], "빈": ["p0"]})
    assert t["names"] == ["나", "가", "다"], t["names"]             # 판매 금액 큰 순 · 같으면 이름 순 · 금액 없는 '빈' 뺌
    for k in range(1, 9):
        exp = round(sum(cols[p][k] for p in ("p1", "p2", "p3")))
        assert t["lines8"][k] == exp == sum(t["int"][n][k] for n in t["names"]), (k, t["lines8"][k], exp)
        assert t["pend8"][k] == sum(t["pint"][n][k] for n in t["names"])
    assert _product_row(t, "다")["pending"]["wing_c1"] == 20 and "pending" not in _product_row(t, "가")   # D-405 윙 예정 판매만 따로
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
                         pend_line=lambda row, r: False, ad={"deducted": 0, "base": 0}, milk={"deducted": 0},
                         cfs={"line_fees": 0, "adjust": 0, "pending": 0, "noline": 0}, comp={"paid": 0})
    key = ("2026-11-10", "2026-10-01", "2026-10-07", "로켓그로스", "")
    _rg_notes(st, key, list(key), {"totalPostPurchaseDeductionAmount": 8_880.0})
    assert not [j for j in st.j if "PostPurchase" in j], st.j
    items, _ = common_out(st)
    review = next(x for x in items if x["name"] == "리뷰 이벤트 (체험단)")
    assert (review["coupang_amount"], review["applied_amount"]) == (8_880, -4_440), review
    cat = st.common_items[0][2]
    assert st.loc[cat] == [(key, 8_880.0)] and coupang_by_cat(st)[cat] == 8_880


def test_ad_nocamp_d317() -> None:
    """신규-01 · D-317 ②: 캠페인 없는 광고 조정·지원금 = 그 달 옵션별 배분 합 비율(관리 6,000 ÷ 전체 10,000 = 60%)로 나눔 ·
    줄 위치 = 9 '그 밖의 쿠팡 공제'(D-347 ① · 금액 영향 없음) · D-241 비중(0.5)을 쓰지 않음."""
    cols: dict = defaultdict(lambda: [0.0] * 9)
    pa = [(20261005, 111, 7001, 600.0), (20261005, 111, 7002, 400.0)]
    bill = {(20261005, "111"): 10_000.0, (20261031, ""): -2_000.0}
    st = SimpleNamespace(m="2026-10", mk="202610", d={"ads": (pa, bill, {"202610"}), "ad_bills": {"윙": {}, "로켓그로스": {}}}, cols=cols, common=[], loc=defaultdict(list), j=[], chk=[],
                         share=0.5, reg_share=0.4, lines=lambda: iter([]), ad_note="",
                         managed_vid=lambda v: ({"7001": ("P1", True), "7002": ("P2", False)}[str(v)]))
    ads(st)
    assert st.ad_alloc_share == 0.6 and [c for _n, _a, c in st.common] == [AD_NOCAMP], st.common
    assert round(cols["P1"][5]) == -6_600, cols["P1"]                  # 캠페인 광고비 관리 몫 6,000 × 1.1
    items, applied = common_out(st)
    etc = next(x for x in items if x["name"] == "그 밖의 쿠팡 공제")
    assert (etc["coupang_amount"], etc["applied_amount"]) == (-2_200, 1_320), etc     # −2,200 × 60% (D-241 0.5 였으면 1,100)


def _ad_month(m: str, bills: dict, wing: list, rg: list | None = None, charged: float = 0.0, rg_bills: dict | None = None,
              plan: tuple = ()) -> SimpleNamespace:
    """T-186 시험 자료 — 윙 줄 = (지급일, 판매 기간 시작, 차감 사유) · rg = 로켓그로스 줄 (지급일, 시작, 끝, 비율, 광고 공제 · 달 표시 = 판매 달) ·
    charged = 그 달 광고 청구(부가세 전) · bills·rg_bills = 달별 윙·로켓그로스 청구금액."""
    lines = []
    for day, start, why in wing:
        row = ["", "", day, start, start, "70", "예정" if day in plan else "지급 완료"]
        lines.append(((day, start, start, "윙", "70"), row, {"채널": "윙", "차감 사유": [{"사유": k, "금액": v} for k, v in why]}))
    for day, start, end, pct_, amt in rg or []:
        row = ["", "", day, start, end, pct_, "지급 완료"]
        lines.append(((day, start, end, "로켓그로스", pct_), row, {"채널": "로켓그로스", "adSalesOffsetYearMonthBreakdown": json.dumps({start[:7]: amt} if amt else {})}))
    st = SimpleNamespace(m=m, mk=m.replace("-", ""), d={"ads": ([], {(int(m.replace("-", "") + "15"), ""): charged}, set()),
                                                        "ad_bills": {"윙": bills, "로켓그로스": rg_bills if rg_bills is not None else dict.fromkeys(bills, 0)}},
                         cols=defaultdict(lambda: [0.0] * 9), common=[], loc=defaultdict(list), j=[], chk=[], lines=lambda: iter(lines), ad_note="",
                         managed_vid=lambda v: ("", False), milk={"deducted": 0}, cfs={"line_fees": 0, "adjust": 0, "pending": 0, "noline": 0}, comp={"paid": 0})
    ads(st)
    return st


def _ad_dates(st: SimpleNamespace, cost: float) -> tuple[dict, float]:
    """관리 몫 100% 로 날짜별 표 광고 위치 — ({지급일: 뺀 금액}, 지급일 미정 금액)."""
    st.common_items, dep = [], Counter()
    st.coupang_cat = coupang_by_cat(st)
    _cost_locs(st, dep, {}, {5: -cost, 6: 0, 7: 0, 8: 0}, [])
    got: Counter = Counter()
    for k, v in dep.items():
        got[k[0]] += -v
    return {k: round(v) for k, v in got.items() if round(v)}, round(st.unlocated["ad"])


def test_t186_wing_ad_deducted() -> None:
    """T-186: 쿠팡이 윙 지급 줄에서 이미 뺀 광고비(달 표시 없음)는 '아직 안 뺀 금액'이 아님 — 광고 달 = 줄의 판매 달(그 달 윙 청구액까지) ·
    기대값 = 쿠팡 원문 금액(광고센터 nonRod 청구 127,478 = 98,095 + 223,665 − 202,522 + 8,240 · 4월 66,000)."""
    ad = "상품/브랜드광고비"
    wing = [("2026-05-26", "2026-04-27", [(ad, 66_000)]), ("2026-05-26", "2026-05-01", [(ad, 98_095)]), ("2026-06-01", "2026-05-04", [(ad, 223_665)]),
            ("2026-06-09", "2026-05-11", [(ad, -202_522)]), ("2026-06-16", "2026-05-18", []),
            ("2026-07-01", "2026-05-01", [(ad, 8_240), ("판매자서비스이용료", 55_000)])]
    bills = {"2026-04": 66_000, "2026-05": 127_478}
    for m, charged, want in (("2026-04", 60_000.0, {"2026-05-26": 66_000}),
                             ("2026-05", 115_889.0, {"2026-05-26": 98_095, "2026-06-01": 223_665, "2026-06-09": -202_522, "2026-07-01": 8_240})):
        st = _ad_month(m, bills, wing, charged=charged)
        assert {k[0]: a for k, a in st.loc["ad"]} == want and st.ad["deducted"] == sum(want.values()), (m, st.loc["ad"])
        assert abs(st.chk[0]["차이"]) < 1 and not [j for j in st.j if "윙 지급 줄" in j], (st.chk, st.j)
        assert _ad_dates(st, sum(want.values())) == (want, 0), m          # 날짜별 표 = 쿠팡이 실제로 뺀 날 · '지급일 미정' 0
    # 로켓그로스 + 윙 = 둘 다
    st = _ad_month("2026-05", bills, wing, rg=[("2026-06-12", "2026-05-04", "2026-05-10", "70", 500), ("2026-05-12", "2026-04-06", "2026-04-12", "70", 70)],
                   charged=(127_478 + 500) / 1.1, rg_bills={"2026-04": 70, "2026-05": 500})
    assert st.ad["deducted"] == 127_978 and abs(st.chk[0]["차이"]) < 1, st.chk


def test_t186_wing_ad_carry() -> None:
    """T-186 · D-289 ②: 그 달 줄에서 모자란 몫은 뒤 달 줄에서 빠짐(지급 순서 누적) — 뒤 달 줄의 그 달 청구를 넘는 금액 = 앞 달 모자란 몫 ·
    같은 금액 먼저(앞 달 미납이 남아도 다음 달들이 자기 청구액 그대로 빠진 실측) · 못 가른 금액 = '확인 필요'(위치에 안 넣음)."""
    def line(day, start, a):
        return start[:7], (day, start, start, "윙", "70"), a
    # 6월 청구 137,530 한 푼도 못 뺌 → 7월 줄 79,273 + 8월 줄 58,257
    got, unk = ad_months({"2026-06": 137_530, "2026-07": 141_730, "2026-08": 90_254},
                              [line("2026-08-10", "2026-07-06", 100_000), line("2026-09-01", "2026-07-01", 121_003),
                               line("2026-09-20", "2026-08-03", 148_511)])
    tot = {m: sum(a for _k, a in v) for m, v in got.items()}
    assert tot == {"2026-06": 137_530, "2026-07": 141_730, "2026-08": 90_254} and not unk, (tot, unk)
    assert [(k[0], a) for k, a in got["2026-06"]] == [("2026-08-10", 79_273), ("2026-09-20", 58_257)], got["2026-06"]
    # 4월 1,108 은 끝내 안 빠짐 · 7월 333 은 8월 줄에서 빠짐(같은 금액) → 4월 위치 0 · 8월 = 청구 그대로
    got, unk = ad_months({"2026-04": 1_108, "2026-07": 333, "2026-08": 1_577}, [line("2026-09-10", "2026-08-10", 1_910)])
    assert {m: sum(a for _k, a in v) for m, v in got.items() if v} == {"2026-07": 333, "2026-08": 1_577} and not unk, (got, unk)
    # 음수 청구(지원금) · 청구 0 인 달의 환급 · 앞 달 미납 없는 넘침 · 청구 자료 없는 달 = 확인 필요(달 모름)
    got, unk = ad_months({"2026-01": -356, "2026-02": 0, "2026-03": 0},
                              [line("2026-02-10", "2026-01-12", -356), line("2026-03-10", "2026-02-12", -80_321), line("2026-04-10", "2026-03-12", 1_802),
                               line("2026-06-10", "2026-05-12", 56_030)])
    assert got["2026-01"] == [(("2026-02-10", "2026-01-12", "2026-01-12", "윙", "70"), -356)], got
    assert [(m, a) for _k, m, a in unk] == [("2026-02", -80_321), ("2026-03", 1_802), ("2026-05", 56_030)] and not any(got[m] for m in ("2026-02", "2026-03", "2026-05")), (got, unk)
    # 같은 것을 한 달 계산에서: 청구 자료 없는 달 = 지금처럼 '확인 필요' 문장만(위치·뺀 금액 0) · 이월 = 설명 한 줄
    st = _ad_month("2026-05", {}, [("2026-06-10", "2026-05-12", [("상품/브랜드광고비", 56_030)])])
    assert st.ad["deducted"] == 0 and not st.loc["ad"] and [j for j in st.j if j.startswith("확인 필요") and "56030" in j.replace(",", "")], st.j
    st = _ad_month("2026-03", {"2026-03": 12_354, "2026-04": 219_996}, [("2026-05-20", "2026-04-13", [("상품/브랜드광고비", 232_350)])], charged=12_354 / 1.1)
    assert st.ad["deducted"] == 12_354 and st.loc["ad"][0][0][0] == "2026-05-20" and [j for j in st.j if "이월" in j and "12,354" in j], (st.loc, st.j)


def test_t186_ad_bills_file() -> None:
    """T-186: 광고 청구액 = 광고정산 json summary(nonRod 윙 · rocketGrowth 로켓그로스) totalFinalAmount(부가세 포함) · null = 0 · 칸 없음 = 모름(달 안 넣음) ·
    2025 판매 달 = 안 씀(정산서 지급 줄에 2025 판매 줄이 없음 D-328 → 남겨 두면 안 빠진 청구로 보여 2026 이월을 가져감) · 진행 중 달 파일 안 읽음 · 괄호 계정."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "검증자료" / "광고"
        d.mkdir(parents=True)
        for name, data in (("가짜[나다]-x1_광고정산_202512", {"summary": {"nonRod": {"totalFinalAmount": 8_309}, "rocketGrowth": {"totalFinalAmount": 24_651}}}),
                           ("가짜[나다]-x1_광고정산_202604", {"summary": {"nonRod": None, "rocketGrowth": None}, "items": []}),
                           ("가짜[나다]-x1_광고정산_202605", {"summary": {"nonRod": {"billableAmount": 115_889, "totalFinalAmount": 127_478},
                                                                  "rocketGrowth": {"totalFinalAmount": 500}}, "items": []}),
                           ("가짜[나다]-x1_광고정산_202606", {"summary": {}, "items": []}),
                           ("가짜[나다]-x1_광고정산진행_202607", {"summary": {"nonRod": {"totalFinalAmount": 9}}}),
                           ("가짜나-x1_광고정산_202605", {"summary": {"nonRod": {"totalFinalAmount": 5}}})):
            (d / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
        assert AC.ad_bills(Path(tmp), "가짜[나다]-x1") == {"윙": {"2026-04": 0, "2026-05": 127_478}, "로켓그로스": {"2026-04": 0, "2026-05": 500}}


def test_t186_2025_bill_not_owed() -> None:
    """T-186 ②: 정산서 지급 줄에 2025 판매 줄이 없음(D-328) → 2025 청구가 '안 빠진 청구'로 남아 2026 이월을 가져가면 안 됨.
    기대값 = 쿠팡 원문 금액: 9월 줄 866,759 = 9월 청구 854,588 + 7월 남은 8,398 + 8월 남은 3,773(2025-12 청구 8,309 은 2025 줄에서 빠짐)."""
    bill = {"202512": 8_309, "202607": 1_652_221, "202608": 570_706, "202609": 854_588}
    ad = "상품/브랜드광고비"
    wing = [("2026-08-20", "2026-07-06", [(ad, 1_643_823)]), ("2026-09-20", "2026-08-10", [(ad, 566_933)]), ("2026-10-20", "2026-09-07", [(ad, 866_759)])]
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "검증자료" / "광고"
        d.mkdir(parents=True)
        for ym, n in bill.items():
            (d / f"가짜-x1_광고정산_{ym}.json").write_text(json.dumps({"summary": {"nonRod": {"totalFinalAmount": n}, "rocketGrowth": None}}), encoding="utf-8")
        bills = AC.ad_bills(Path(tmp), "가짜-x1")["윙"]
    for m in ("2026-07", "2026-08", "2026-09"):
        want = bill[m.replace("-", "")]
        st = _ad_month(m, bills, wing, charged=want / 1.1)
        assert st.ad["deducted"] == want and _ad_dates(st, want)[1] == 0 and not [j for j in st.j if j.startswith("확인 필요: 윙")], (m, st.loc, st.j)


RG_0930 = [("2026-10-15", "2026-09-07", "2026-09-13", "70", 1_505_014), ("2026-11-03", "2026-09-28", "2026-09-30", "70", 94_419),
           ("2026-11-03", "2026-10-01", "2026-10-04", "70", 272_357), ("2026-11-06", "2026-10-05", "2026-10-11", "70", 1_100_159)]


def test_t186_partly_deducted() -> None:
    """T-186 ②: 일부만 빠진 달 — 안 빠진 몫 = '지급일 미정', 뺀 몫 = 실제 뺀 날. 기대값 = 쿠팡 원문 금액(로켓그로스 청구 9월 1,646,910·10월 1,533,752 ·
    9/30 광고 47,477 은 같은 지급일 10/1~4 줄에서 빠짐 D-308 ② → 10월 안 빠진 몫 = 1,533,752 − (1,372,516 − 47,477) = 208,713)."""
    rb = {"2026-09": 1_646_910, "2026-10": 1_533_752}
    z = dict.fromkeys(rb, 0)
    st = _ad_month("2026-09", z, [], RG_0930, charged=1_646_910 / 1.1, rg_bills=rb)
    assert _ad_dates(st, 1_646_910) == ({"2026-10-15": 1_505_014, "2026-11-03": 141_896}, 0) and abs(st.chk[0]["차이"]) < 1, (st.loc, st.chk)
    st = _ad_month("2026-10", z, [], RG_0930, charged=1_533_752 / 1.1, rg_bills=rb)
    assert _ad_dates(st, 1_533_752) == ({"2026-11-03": 224_880, "2026-11-06": 1_100_159}, 208_713), st.loc
    assert [j for j in st.j if "208,713" in j and "아직 안 뺌" in j], st.j            # 뒤 달 광고 줄 없음 = 아직 안 뺀 것
    # 한 푼도 안 빠진 달 = 전부 미정 · 관리 몫 일부(40%)면 미정도 같은 비율
    st = _ad_month("2026-10", {"2026-10": 0}, [], [], charged=113_050 / 1.1, rg_bills={"2026-10": 113_050})
    assert _ad_dates(st, 113_050 * 0.4) == ({}, 45_220), st.loc
    # 윙 예정 줄에 이미 공제가 잡힌 금액 = 그 예정 줄 날짜(미정으로 또 빼지 않음)
    ad = "상품/브랜드광고비"
    st = _ad_month("2026-10", {"2026-10": 1_291_803}, [("2026-11-13", "2026-10-19", [(ad, 1_006_429)]), ("2026-12-01", "2026-10-01", [(ad, 285_374)])],
                   charged=1_291_803 / 1.1)
    assert _ad_dates(st, 1_291_803) == ({"2026-11-13": 1_006_429, "2026-12-01": 285_374}, 0), st.loc
    # 부호가 섞인 달(지원금 음수 줄) + 마지막 8,240 이 아직 안 빠짐
    st = _ad_month("2026-05", {"2026-05": 127_478}, [("2026-05-26", "2026-05-01", [(ad, 98_095)]), ("2026-06-01", "2026-05-04", [(ad, 223_665)]),
                                                     ("2026-06-09", "2026-05-11", [(ad, -202_522)])], charged=115_889)
    assert _ad_dates(st, 127_478) == ({"2026-05-26": 98_095, "2026-06-01": 223_665, "2026-06-09": -202_522}, 8_240), st.loc
    # 끝전 ±2원 = 다 빠진 것(D-281) · 청구 자료 없는 달(로켓그로스 달 표시만) = 미정 안 지어냄
    st = _ad_month("2026-04", {"2026-04": 51_302}, [("2026-05-20", "2026-04-13", [(ad, 51_300)])], charged=51_302 / 1.1)
    assert _ad_dates(st, 51_302) == ({"2026-05-20": 51_302}, 0), st.loc
    st = _ad_month("2026-07", {}, [], [("2026-08-20", "2026-07-06", "2026-07-12", "70", 66_324)], charged=70_000 / 1.1)
    assert _ad_dates(st, 70_000) == ({"2026-08-20": 70_000}, 0) and st.ad["deducted"] == 66_324, st.loc


def test_t186_rg_month_border() -> None:
    """T-186 ②: 로켓그로스 달 경계 이동 = 누적으로 다 빠진 달은 미정 0 (원문: 6월 +154,216 / 7월 −154,216 · 3월 +182,646 → 4월 −2,023,119 → 5월 +1,840,473)."""
    rg = [("2026-07-20", "2026-06-15", "2026-06-21", "70", 520_374), ("2026-08-03", "2026-06-29", "2026-06-30", "70", 200_000),
          ("2026-09-01", "2026-06-29", "2026-06-30", "30", 0), ("2026-08-03", "2026-07-01", "2026-07-05", "70", 300_000),
          ("2026-08-24", "2026-07-20", "2026-07-26", "70", 1_010_469)]
    rb = {"2026-06": 566_158, "2026-07": 1_464_685}
    z = dict.fromkeys(rb, 0)
    st = _ad_month("2026-06", z, [], rg, charged=566_158 / 1.1, rg_bills=rb)
    assert _ad_dates(st, 566_158) == ({"2026-07-20": 520_374, "2026-08-03": 45_784}, 0) and abs(st.chk[0]["차이"]) < 1, st.loc
    st = _ad_month("2026-07", z, [], rg, charged=1_464_685 / 1.1, rg_bills=rb)
    assert _ad_dates(st, 1_464_685) == ({"2026-08-03": 454_216, "2026-08-24": 1_010_469}, 0) and abs(st.chk[0]["차이"]) < 1, st.loc
    got, unk = ad_months({"2026-03": 4_914_137, "2026-04": 5_461_081, "2026-05": 3_007_045},
                         [("2026-03", ("2026-05-04", "2026-03-30", "2026-03-31", "로켓그로스", "70"), 5_096_783),
                          ("2026-04", ("2026-05-25", "2026-04-20", "2026-04-26", "로켓그로스", "70"), 3_437_962),
                          ("2026-05", ("2026-06-15", "2026-05-11", "2026-05-17", "로켓그로스", "70"), 4_847_518)], rg=True)
    assert {m: sum(a for _k, a in v) for m, v in got.items()} == {"2026-03": 4_914_137, "2026-04": 5_461_081, "2026-05": 3_007_045} and not unk, got
    assert sorted(k[0] for k, _a in got["2026-04"]) == ["2026-05-04", "2026-05-25", "2026-06-15"], got["2026-04"]
    # 짝 없는 넘침·음수 = 쿠팡 달 표시대로 그 달에 둠(지어내지 않음) · 지급일이 다르면 다음 달 첫 줄을 안 가져옴
    k1, k2 = ("2026-02-20", "2026-01-12", "2026-01-18", "로켓그로스", "70"), ("2026-03-20", "2026-02-01", "2026-02-08", "로켓그로스", "70")
    got, unk = ad_months({"2026-01": 1_000, "2026-02": 500}, [("2026-01", k1, 1_300), ("2026-02", k2, 500)], rg=True)
    assert {m: v for m, v in got.items() if v} == {"2026-01": [(k1, 1_000), (k1, 300)], "2026-02": [(k2, 500)]} and not unk, got
    got, unk = ad_months({"2026-01": 0}, [("2026-01", k1, -961)], rg=True)
    assert got["2026-01"] == [(k1, -961)] and not unk, got
    got, _unk = ad_months({"2026-01": 1_000, "2026-02": 500}, [("2026-01", ("2026-03-13", "2026-01-26", "2026-01-31", "로켓그로스", "70"), 700), ("2026-02", k2, 500)], rg=True)
    assert sum(a for _k, a in got["2026-01"]) == 700 and got["2026-02"] == [(k2, 500)], got
    # 두 곳에서 채움 = 앞 달 넘침 100 먼저 + 같은 지급일 다음 달 첫 줄 200 만(두 번 안 채움) · 채운 달은 뒤 달 넘침을 또 안 가져감
    k3, k4 = ("2026-03-27", "2026-02-23", "2026-02-28", "로켓그로스", "70"), ("2026-03-27", "2026-03-01", "2026-03-08", "로켓그로스", "70")
    k5 = ("2026-04-20", "2026-03-16", "2026-03-22", "로켓그로스", "70")
    ls = [("2026-01", k1, 1_100), ("2026-02", k3, 700), ("2026-03", k4, 500), ("2026-03", k5, 900)]
    got, unk = ad_months({"2026-01": 1_000, "2026-02": 1_000, "2026-03": 900}, ls, rg=True)
    assert got["2026-02"] == [(k3, 700), (k1, 100), (k4, 200)] and sum(a for _k, a in got["2026-03"]) == 1_200 and not unk, got
    got, _unk = ad_months({"2026-01": 1_000, "2026-02": 1_000}, ls, rg=True)                 # 3월 청구 자료 없음 = 3월 줄을 안 가져옴
    assert got["2026-02"] == [(k3, 700), (k1, 100)] and got["2026-03"] == [(k4, 500), (k5, 900)], got
    # 뒤 달 광고 줄이 있는데도 남은 몫 = 미정 + '확인 필요'(미납일 수 있음 D-309 · 숫자 안 지어냄)
    st = _ad_month("2026-06", {"2026-06": 0, "2026-07": 0}, [], [("2026-08-24", "2026-07-20", "2026-07-26", "70", 29_990)], charged=73_000 / 1.1,
                   rg_bills={"2026-06": 73_000, "2026-07": 29_990})
    assert _ad_dates(st, 73_000) == ({}, 73_000) and [j for j in st.j if j.startswith("확인 필요: 2026-06 로켓그로스") and "73,000" in j], st.j


def _mk(day: str, start: str, pct_: str, amt: float) -> tuple:
    return (day, start, start, "로켓그로스", pct_), amt


def test_t179_milk_months() -> None:
    """T-179 ⑩: 쿠팡은 한 달 밀크런을 여러 지급일에 나눠 뺌 → 나눠 뺀 합이 파일 합과 원 단위로 같으면 찾은 것 · 1원이라도 다르면 못 찾음(느슨하게 안 맞춤).
    기대값 = 쿠팡 원문 금액(nicoable 5·6·8·10월 · 91white 4·5월 · ski1121 2·3월 · woolins 10월)."""
    nic = {"2026-05": 60_500, "2026-06": 144_760, "2026-07": 59_180, "2026-08": 69_850, "2026-09": 13_200, "2026-10": 25_300}
    lines = [_mk("2026-06-23", "2026-05-18", "70", 52_908), _mk("2026-06-29", "2026-05-25", "70", 7_592), _mk("2026-07-03", "2026-06-01", "70", 144_760),
             _mk("2026-08-10", "2026-07-06", "70", 59_180), _mk("2026-10-07", "2026-09-01", "70", 53_566), _mk("2026-10-15", "2026-09-07", "70", 16_284),
             _mk("2026-11-03", "2026-10-01", "70", 13_200), _mk("2026-11-06", "2026-10-05", "70", 9_983), _mk("2027-01-04", "2026-11-30", "30", 15_317)]
    got = {m: [(k[0], a) for k, a in xs] for m, xs in milk_months(nic, lines).items()}
    assert got == {"2026-05": [("2026-06-23", 52_908), ("2026-06-29", 7_592)], "2026-06": [("2026-07-03", 144_760)], "2026-07": [("2026-08-10", 59_180)],
                   "2026-08": [("2026-10-07", 53_566), ("2026-10-15", 16_284)], "2026-09": [("2026-11-03", 13_200)],
                   "2026-10": [("2026-11-06", 9_983), ("2027-01-04", 15_317)]}, got
    # 1원 다름 = 못 찾음 · 덜 빠짐(woolins 194,000 중 13,834) = 못 찾음 · 달이 끝나기 전 지급 줄 = 그 달 것 아님
    assert milk_months({"2026-08": 69_851}, lines) == {} and milk_months({"2026-10": 194_000}, [_mk("2026-11-13", "2026-10-12", "70", 9_684),
                                                                                               _mk("2026-12-01", "2026-10-12", "30", 4_150)]) == {}
    assert milk_months({"2026-08": 69_850}, [_mk("2026-08-20", "2026-07-06", "70", 53_566), _mk("2026-10-15", "2026-09-07", "70", 16_284)]) == {}
    # 한 지급 줄에 두 달 몫이 섞임(91white 06-09 21,806 = 4월 14,634 + 5월 7,172) → 두 달 합 47,190 이 줄 합과 같고 지급 순서대로 앞 달부터
    w = [_mk("2026-05-19", "2026-04-13", "70", 7_075), _mk("2026-06-01", "2026-04-13", "30", 3_675), _mk("2026-06-02", "2026-05-01", "70", 9_596),
         _mk("2026-06-09", "2026-05-04", "70", 21_806), _mk("2026-06-10", "2026-05-01", "30", 925), _mk("2026-07-01", "2026-05-04", "30", 4_113),
         _mk("2026-07-03", "2026-06-01", "70", 14_080)]
    got = {m: [(k[0], a) for k, a in xs] for m, xs in milk_months({"2026-04": 34_980, "2026-05": 12_210, "2026-06": 14_080}, w).items()}
    assert got["2026-04"] == [("2026-05-19", 7_075), ("2026-06-01", 3_675), ("2026-06-02", 9_596), ("2026-06-09", 14_634)], got
    assert got["2026-05"] == [("2026-06-09", 7_172), ("2026-06-10", 925), ("2026-07-01", 4_113)] and got["2026-06"] == [("2026-07-03", 14_080)], got
    # 사이에 다른 달을 한 번에 뺀 지급일이 끼어도 남은 줄끼리 이어서 봄(ski1121 2월 208,445 + 358,825 · 3월 = 04-03 689,591)
    got = milk_months({"2026-02": 567_270, "2026-03": 689_591}, [_mk("2026-03-05", "2026-01-26", "70", 208_445), _mk("2026-04-03", "2026-03-01", "70", 689_591),
                                                                 _mk("2026-04-06", "2026-02-23", "30", 358_825)])
    assert [a for _k, a in got["2026-02"]] == [208_445, 358_825] and [a for _k, a in got["2026-03"]] == [689_591], got
    # 파일 → 달 합(글자 금액 · 취소수수료) · 2025 달 = 정산 밖 · 괄호 계정 · 없음 = {}
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "검증자료" / "광고"
        d.mkdir(parents=True)
        for ym in ("202512", "202605"):
            (d / f"가짜[나다]-x1_밀크런_{ym}.xlsx").write_bytes(b"")
        real, AC.milk_file = AC.milk_file, lambda p: [("1", 52_908.0), ("2", 7_592.0)]
        try:
            assert AC.milk_totals(Path(tmp), "가짜[나다]-x1") == {"2026-05": 60_500.0} and AC.milk_totals(Path(tmp), "x") == {}
        finally:
            AC.milk_file = real


def test_t179_ad_wait() -> None:
    """T-179 ⑩: 광고 청구 = 뺀 것 + '지급일 미정'(쿠팡이 아직 안 뺀 몫) 이면 검산 통과 · 뒤 달 지급이 끝났는데 안 뺀 몫(theirumlab 4월 6,986)은 그대로 실패 ·
    끝전 ±2원 = 통과(D-281) · 청구 자료 없는 달 = 실패."""
    rb = {"2026-09": 1_646_910, "2026-10": 1_533_752}
    z = dict.fromkeys(rb, 0)
    st = _ad_month("2026-10", z, [], RG_0930, charged=1_533_752 / 1.1, rg_bills=rb)
    assert st.chk[0]["차이"] == 0 and st.chk[0]["값"][1:] == [1_325_039, 208_713], st.chk
    st = _ad_month("2026-04", {"2026-04": 0}, [], [("2026-05-12", "2026-04-06", "2026-04-12", "70", 65_870), ("2026-06-12", "2026-05-04", "2026-05-10", "70", 0)],
                   charged=72_856 / 1.1, rg_bills={"2026-04": 72_856})
    assert round(st.chk[0]["차이"]) == 6_986 and [j for j in st.j if j.startswith("확인 필요") and "6,986" in j], (st.chk, st.j)     # 5월 줄 지급 완료 = 안 빼고 지급함
    # 윙 10월 22,000 이 남고 11월 줄은 아직 예정(11월 청구 자료 없음) = 지급일 미정 · 11월 청구를 알면 = 확인 필요
    ad, wing = "상품/브랜드광고비", [("2026-11-20", "2026-10-26", [("상품/브랜드광고비", 460_182)]), ("2026-11-27", "2026-11-02", [("상품/브랜드광고비", 96_936)])]
    for bills, want in (({"2026-10": 482_182}, 0), ({"2026-10": 482_182, "2026-11": 96_936}, 22_000)):
        lines = _ad_month("2026-10", bills, wing, charged=482_182 / 1.1, plan=("2026-11-27",))
        assert round(lines.chk[0]["차이"]) == want, (bills, lines.chk, lines.j)
    assert round(_ad_month("2026-10", {"2026-10": 482_182}, wing, charged=482_182 / 1.1).chk[0]["차이"]) == 22_000     # 11월 줄이 지급 완료 = 안 빼고 지급함
    st = _ad_month("2026-04", {"2026-04": 51_302}, [("2026-05-20", "2026-04-13", [(ad, 51_300)])], charged=51_301.7 / 1.1)
    assert st.chk[0]["차이"] == 0 and st.chk[0]["끝전(±2원 · D-281)"] == 1.7, st.chk
    st = _ad_month("2026-07", {}, [], [("2026-08-20", "2026-07-06", "2026-07-12", "70", 66_324)])
    assert st.chk[0]["차이"] == -66_324, st.chk


def test_t179_cfs_no_line_period() -> None:
    """T-179 ⑩: 지급 줄이 없는 정산주기의 물류비 = 뒤 줄 상세(cfsDeductionDetails)가 갚은 금액과 원 단위로 같으면 통과 · 다르면 실패 그대로.
    기대값 = WBpeak 2026-02 원문(리포트 147,647 = 줄 칸 139,271 + 02-01 하루 주기 8,376)."""
    from coupang_analytics.settlement_consignor_month_cost import logistics

    def run(paid: int, own_start: str = "2026-02-02") -> SimpleNamespace:
        own = {"채널": "로켓그로스", "totalStorageFeeDeductionAmount": 139_271}
        late = {"채널": "로켓그로스", "cfsDeductionDetails": json.dumps([{"settlementPeriodStartDate": "2026-01-31T15:00:00Z", "settlementPeriodEndDate": "2026-01-31T15:00:00Z",
                                                                    "lastSettlementUnpaidCfsDeductionAmount": paid}])}
        lines = [(("2026-03-12", own_start, "2026-02-08", "로켓그로스", 70), ["", "", "2026-03-12", own_start, "2026-02-08", 70, "지급 완료"], own),
                 (("2026-04-06", "2026-03-02", "2026-03-08", "로켓그로스", 70), ["", "", "2026-04-06", "2026-03-02", "2026-03-08", 70, "지급 완료"], late)]
        st = SimpleNamespace(m="2026-02", d={"rg_cost_rows": [{"월(매출인식)": "2026-02", "등록상품ID": "P1", "물류비 합계(VAT포함)": 147_647}]}, managed=lambda p: False,
                             common=[], loc=defaultdict(list), chk=[], j=[], lines=lambda: iter(lines), pend_line=lambda row, r: False)
        logistics(st)
        return st
    st = run(8_376)
    assert st.chk[0]["차이"] == 0 and st.cfs["noline"] == 8_376 and st.loc["cfs"][-1][0][0] == "2026-04-06", (st.chk, st.loc)
    assert run(8_000).chk[0]["차이"] == 376
    assert run(8_376, "2026-02-01").chk[0]["차이"] == 8_376           # 그 주기 줄이 있으면 줄 칸으로 봐야 함(갚은 금액을 더하지 않음)


def test_t179_cash_reference() -> None:
    """T-179 ⑩: 참고 대조(실제 지급액 = 줄 공식) — 보류 해제액·줄 생성 전 금액·지급 끝난 윙 음수 회차·추가지급 줄을 원문 값으로 넣으면 0 · 그 밖의 차이는 그대로.
    기대값 = 쿠팡 원문(Difpick 5월 해제 9,724,088 · bux1004 11월 생성 전 13,834 · guarisen2024 7월 음수 −52,343 · freewin7777 추가지급 117,960)."""
    from coupang_analytics.settlement_consignor_month_dep import _cash_reference
    from coupang_analytics.settlement_consignor_month_out import cash_gap

    def run(rows: list, gen: dict) -> int:
        lines, info = [], []
        for day, start, status, pay, rel, parts, final, extra in rows:
            row = ["", "윙", day, start, start, 100 if extra else 70, status]
            r = {"채널": "윙", "최종지급액": final, "정산일": day, "기간 시작": start, "기간 끝": start, "지급비율": 100 if extra else 70,
                 "targetAmount": 0 if extra else pay, "paidAmount": 0 if extra else pay, "pendingAmount": rel}
            lines.append(((day, start, start, "윙", 70), row, r))
            info.append((status.split(" ·")[0], "윙", start[:7], pay, rel, Counter(parts), row))
        st = SimpleNamespace(m="2026-05", d={"line_info": info, "L_gen": gen}, lines=lambda: iter(lines), loc={}, pay_ch=Counter({"윙": sum(x[3] for x in rows) + sum(gen.values())}))
        _cash_reference(st)
        return cash_gap(st.cash)
    sale = ("2026-06-30", "2026-05-04", "지급 완료", 100_000, 0, {AC.AD: 30_000}, 70_000, False)
    assert run([sale, ("2026-07-20", "2026-05-11", "지급 완료 · 보류 해제", 0, 9_724_088, {}, 9_724_088, False)], {}) == 0
    assert run([sale], {("윙", "2026-05"): 13_834}) == 0
    assert run([sale, ("2026-07-01", "2026-05-18", "지급 완료", 0, 0, {AC.AD: 52_343, AC.PM3: -52_343}, -52_343, False)], {}) == 0
    assert run([sale, ("2026-05-13", "2026-05-13", "지급 완료 · 추가지급", 0, 0, {}, 117_960, True)], {}) == 0
    assert run([(*sale[:6], 69_990, False)], {}) == 10                       # 설명 안 되는 10원 = 그대로 실패
    assert run([("2026-07-01", "2026-05-18", "예정", 0, 0, {AC.AD: 52_343}, -52_343, False)], {}) == 0      # 예정 음수 = 줄 공식 그대로(D-319)


def test_t179_pending_rg_missing_70() -> None:
    """T-179 ⑩: 정산 예정 로켓그로스 — 70% 줄을 못 받은 판매 주는 30% 줄의 할인·수수료(기간 전체 값 · 두 줄이 같음)로. 정산 금액은 그대로.
    기대값 = bux1004 2026-10 원문(판매 600,930 · 쿠폰 81,630 + 97,700 · 수수료 22,779 + 27,326 · 정산 371,495 → 차 0)."""
    from coupang_analytics.settlement_consignor_month_calc import _pend_rg

    def row(start, end, pct_, coupon, fee):
        return None, ["", "", "x", start, end], {"채널": "로켓그로스", "지급비율": pct_, "totalSellerDiscount": coupon, "totalTakeRateAmountWithVat": fee}
    pl = [row("2026-10-19", "2026-10-25", 30, 81_630, 22_779), row("2026-10-26", "2026-10-31", 70, 97_700, 27_326), row("2026-10-26", "2026-10-31", 30, 97_700, 27_326)]
    st = SimpleNamespace(chk=[])
    cf, est, _how = _pend_rg(st, pl, 600_930, 371_495, SimpleNamespace(opts={"v": (600_930, 371_495)}))
    assert st.chk[0]["차이"] == 0 and cf("v") == (179_330, 50_105) and not est, (st.chk, cf("v"))


def _line(ch: str, s: str, e: str, bi: dict | None = None) -> tuple:
    row = ["", "", "2026-12-01", s, e, "70"]
    return (row[2], s, e, ch, row[5]), row, {"채널": ch, **({BI_CAT[2:]: json.dumps(bi)} if bi else {})}


def _expect_st(m: str, basis: str, common: list, lines: list, pend: bool = True) -> SimpleNamespace:
    """pend = 그 달 정산 예정분(pend_info · 정산서 상태 '정산 예정 포함'과 같은 근거) 있음."""
    return SimpleNamespace(m=m, basis=basis, common=common, j=[], share=0.5, reg_share=0.4, lines=lambda: iter(lines),
                           pend_info=[{"항목": "1~4 로켓그로스 정산 예정"}] if pend else [])


def test_expect_values() -> None:
    """T-121: 입력 없음 = 숫자 없이 비고 · 74 = BI 쓰는 계정의 '정산 예정분 남은 달'만(통제 11-19 · 지급 끝난 달 = 없음 · 조각 0 이어도 근거·판단 문장) ·
    9 BI 줄 note = 그 줄 금액 있을 때만(금액 없는 줄 안 만듦 D-081) · 줄 없는 기간 = 근거만 · 금액 변화 0."""
    lines = [_line("로켓그로스", "2026-10-01", "2026-10-26", bi={"2026-10": 20_228}), _line("윙", "2026-10-01", "2026-10-31"),
             _line("윙", "2026-09-28", "2026-09-30")]
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
    # 74 ① 지급 끝난 달(정산 예정분 없음) · 조각 있음 = 비고·판단 문장·근거 없음
    bi_lines = [_line("로켓그로스", "2026-09-01", "2026-11-14", bi={"2026-01": 108_900})]
    st = _expect_st("2026-01", "2026-11-15", [("비즈니스 인사이트 이용료", 108_900.0, BI_CAT)], bi_lines, pend=False)
    expect_values(st)
    assert st.bi_note == "" and st.j == [] and "74 비즈니스 인사이트 남은 청구" not in st.expect, (st.bi_note, st.j, st.expect)
    assert all(x.get("note") is None for x in common_out(st)[0])
    # 74 ② 정산 예정분 남은 달 · 조각 0(쿠팡이 아직 안 뺌) · BI 쓰는 계정(다른 달 조각) = 근거·판단 문장 있음 · 9 BI 줄 금액 0 → 줄 비고 없음
    st = _expect_st("2026-10", "2026-11-15", [], bi_lines)
    expect_values(st)
    e74 = st.expect["74 비즈니스 인사이트 남은 청구"]
    assert e74["쿠팡이 뺀 조각"] == 0 and e74["예상값"] is None and FR.NO_INPUT in e74["비고"], e74
    assert any("0원" in j and FR.NO_INPUT in j for j in st.j), st.j
    assert all(x.get("note") is None for x in common_out(st)[0])
    # 74 BI 안 쓰는 계정(어느 줄에도 조각 없음) · 정산 예정분 있음 = 74 없음
    st = _expect_st("2026-10", "2026-11-15", [], [_line("로켓그로스", "2026-09-01", "2026-11-14")])
    expect_values(st)
    assert "74 비즈니스 인사이트 남은 청구" not in st.expect and st.j == [], st.expect


def test_flow_fixed() -> None:
    """D-343: 어디로 갔나요 = 늘 4줄(값 없으면 0)."""
    st = SimpleNamespace(basis="2026-11-15")
    rows = [{"date": "2026-10-10", "desc": "쿠팡 입금 완료", "amount": 1_000, "_status": "지급 완료"}]
    got = flow(st, rows)
    assert [x["name"] for x in got] == FIX_FLOW and [x["amount"] for x in got] == [1_000, 0, 0, 0], got


def _add(day: str, vid: str, amt: int, status: str = "PAID") -> dict:
    return {"지급일": day, "옵션ID": vid, "지급금액": amt, "지급구분": status}


def _sep_st(m: str, rows: list, managed: set, cdate: str = "2026-01-01", basis: str = "2026-11-15") -> SimpleNamespace:
    return SimpleNamespace(m=m, mk=m.replace("-", ""), basis=basis, j=[], order_pids={}, is_m=lambda p: False, is_mv={v: True for v in managed},
                           d={"v": {"favorable": {}}, "add": {"줄": rows}, "extras": [], "cdate": cdate})


def test_t125_additional_pay() -> None:
    """T-125 A1(D-236 별도 입금 = 정산 금액에 넣음 · D-308 ① 추가지급 = finalRewardAmount · 보류 해제와 따로): 10 셋째 줄 '추가지급 (관리 상품 몫)' =
    이 달 지급일 PAID 줄의 관리 옵션 금액(옛 엑셀과 같은 옵션 → 관리 VID · 계약 전 0) · '이번 계산에 안 넣음' 문장 없음 · 날짜별 표 = 지급일 줄
    '쿠팡 추가지급' · 기준일 뒤·지급일 없음 = '(지급일 미정)'(D-294 ②) · 지급일 없는 줄 = 확인 필요 문장.
    실자료 모양 = output38 검증자료 roum0502 202610 PAID 16,897(옵션 95878257194 · 10-22) · freewin7777 202611 PAID 117,960(11-13)."""
    rows = [_add("2026-10-22", "95878257194", 16_897), _add("2026-10-30", "111", 5_000), _add("2026-10-25", "95878257194", 7_000, "REJECT"),
            _add("2026-11-13", "96036856804", 117_960)]
    st = _sep_st("2026-10", rows, managed={"95878257194"})
    separate(st)
    assert [n for n, _ in st.sep] == FIX_SEP and st.sep[2][1] == 16_897, st.sep    # 관리 밖 5,000 · 반려 7,000 · 11월 지급 = 안 넣음
    assert not [j for j in st.j if "이번 계산에 안 넣음" in j], st.j
    rows_d = dep_rows(SimpleNamespace(dep_raw={}, unlocated={}, fast={"지급일": []}, fav_rows=[], add_rows=st.add_rows), 0,
                      [(n, round(a)) for n, a in st.sep])
    assert [(r["date"], r["amount"], r["_status"]) for r in rows_d] == [("2026-10-22", 16_897, "지급 완료")], rows_d
    assert [x["amount"] for x in flow(SimpleNamespace(basis="2026-11-15"), rows_d)] == [16_897, 0, 0, 0]
    pre = _sep_st("2026-10", [_add("2026-10-22", "95878257194", 16_897)], managed={"95878257194"}, cdate="2026-11-01")
    separate(pre)
    assert pre.sep[2][1] == 0, pre.sep                                                 # 계약 전 지급 = 0
    later = _sep_st("2026-11", [_add("2026-11-13", "96036856804", 117_960), _add("", "96036856804", 300)], managed={"96036856804"}, basis="2026-11-10")
    separate(later)
    assert later.sep[2][1] == 117_960 and later.add_rows == [(None, 117_960)], (later.sep, later.add_rows)
    assert any("지급일 없는 1줄 300원" in j for j in later.j), later.j
    rows_d = dep_rows(SimpleNamespace(dep_raw={}, unlocated={}, fast={"지급일": []}, fav_rows=[], add_rows=later.add_rows), 0,
                      [(n, round(a)) for n, a in later.sep])
    assert [(r["date"], r["amount"], r["_status"]) for r in rows_d] == [("(지급일 미정)", 117_960, "예정")], rows_d
    assert [x["amount"] for x in flow(SimpleNamespace(basis="2026-11-10"), rows_d)] == [0, 0, 117_960, 0]


def _ship_st(m: str, prows: list, file_rows: list) -> SimpleNamespace:
    cols: dict = defaultdict(lambda: [0.0] * 9)
    return SimpleNamespace(m=m, opt2pid={}, j=[], chk=[], ship_stats=0, cols=cols, allsales=defaultdict(float),
                           managed=lambda p: p == "P1", vid_pid=lambda v: "", d={"file_rows": file_rows, "v": {}, "prows": prows})


def test_d391_unknown_ship_same_month_wing_ratio() -> None:
    """D-391 ④(소유자 11-23 "로그인 비번 오류로 안됨, 다른 계정에서 도출된 산출식을 적용할것.") — 같은 주문 상품·반품 조회로도 상품을 못 찾은
    윙 배송비 줄 = 그 달 윙 상품 정산금 비율로 상품에 나눔 → 관리 몫 = '같은 달 윙 상품 정산금 관리 비율'(ⓒ · 다른 계정 반품 조회 169줄 백테스트 오차
    합 최소 `output\\_검증_261117_정산끝난달\\결과_1_배송비.md` 3·6절 · D-269). 그 달 윙 상품 정산이 없으면 금액에 넣지 않고 '확인 필요' 문장.
    기대값 = 손 계산(배송비 6,000 · 수수료 198 · 정산 5,802 = gbseller808 실측 줄 모양 · 관리 비율 30,000/100,000 = 0.3)."""
    from coupang_analytics.settlement_consignor_month_calc import ships

    def prow(ym: str, pid: str, wing_settle: int) -> dict:
        return {"월(매출인식)": ym, "등록상품ID": pid, "윙 정산금액": wing_settle, "쿠팡 정산금액 합계(부가비용 차감 전)": wing_settle}

    def frow(oid: str, day: str) -> tuple:     # (파일, 판매 방식, 종류, 기간 시작, 기간 끝, 주문, 상품, 옵션, 상품명, 수량, 판매, 쿠폰, 수수료, 정산, 구매확정, 구분, 총액)
        return (0, "윙", "주정산", day, day, oid, "", "", "", 0, 6_000, 0, 198, 5_802, day, "판매", 6_000)
    prows = [prow("2026-02", "P1", 30_000), prow("2026-02", "P2", 70_000), prow("2026-02", "배송비", 5_802)]
    st = _ship_st("2026-02", prows, [frow("X", "2026-02-10")])
    ships(st)
    assert [round(x, 1) for x in st.ship_m] == [1_800.0, 1_740.6] and st.ship_all == [6_000, 5_802], (st.ship_m, st.ship_all)
    assert [round(x, 1) for x in st.cols["P1"][1:5]] == [1_800.0, 0.0, -59.4, 0.0] and "P2" not in st.cols, dict(st.cols)
    assert round(st.allsales["P1"], 1) == 1_800.0 and round(st.allsales["P2"], 1) == 4_200.0, st.allsales
    assert any("D-391" in j for j in st.j) and not [j for j in st.j if "금액에 넣지 않음" in j], st.j
    none = _ship_st("2026-04", [prow("2026-04", "P1", 0)], [frow("Z", "2026-04-10")])   # 그 달 윙 상품 정산 없음
    ships(none)
    assert none.ship_m == [0, 0] and any("확인 필요" in j and "금액에 넣지 않음" in j for j in none.j), (none.ship_m, none.j)


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
    for t in (t for t in plan.tabs if t.kind != "evidence"):     # '{n}월 근거' = 내부용 · PDF 안 냄(D-401 ②) → 위탁자 문구 규칙 밖
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
    assert [t.kind for t in plan.tabs] == ["summary", "consignor", "consignor", "evidence"] and [t.gid for t in plan.tabs] == [1000, 1001, 1002, 1003]
    assert plan.tabs[0].member_gids == [1001, 1002] and plan.tabs[1].title == "9월 합성 위탁자 (synth01)"
    errs = structure_errors(plan) + page_errors(plan) + decision_text_errors(plan)
    assert not errs, errs
    fake = FakeClient()
    GS.write_statement(fake, ds, ISSUED)
    setup = fake.calls[0]
    assert [next(iter(r)) for r in setup] == ["addSheet"] + ["deleteSheet"] * 3 + ["addSheet"] * 4 + ["deleteSheet"]
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
    b["separate"] = [{"name": FIX_SEP[0], "amount": 0}, {"name": FIX_SEP[1], "amount": 1_000}, {"name": FIX_SEP[2], "amount": 500}]
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


class SheetClient(FakeClient):
    """탭 추가·삭제를 실제 시트처럼 흉내(순서 = 구글 addSheet index 자리에 끼움 · index 없으면 맨 끝) — 남는 탭·순서를 봄."""

    def __init__(self, tabs: list[tuple[int, str]], spreadsheet_id: str = "합성시트"):
        super().__init__(())
        self.tabs, self.spreadsheet_id, self.deleted = list(tabs), spreadsheet_id, []

    def meta(self, refresh: bool = False) -> dict:
        return {"sheets": [{"properties": {"sheetId": i, "title": t}} for i, t in self.tabs]}

    def _add(self, p: dict) -> None:
        assert p["sheetId"] not in [i for i, _ in self.tabs], f"탭 번호 겹침 {p}"
        assert p["title"] not in [t for _, t in self.tabs], f"탭 이름 겹침 {p}"
        self.tabs.insert(p.get("index", len(self.tabs)), (p["sheetId"], p["title"]))

    def batch_update(self, requests: list[dict]) -> dict:
        super().batch_update(requests)
        for r in requests:
            if "addSheet" in r:
                self._add(r["addSheet"]["properties"])
            if "deleteSheet" in r:
                sid = r["deleteSheet"]["sheetId"]
                assert sid in [i for i, _ in self.tabs], f"없는 탭 삭제 {sid}"
                assert len(self.tabs) > 1, "마지막 탭 삭제(구글 거부)"
                self.deleted.append(sid)
                self.tabs = [x for x in self.tabs if x[0] != sid]
        return {}


def test_d242_change_log_tab_kept() -> None:
    """D-242 ③ 탭 = 요약 · 위탁자별 · 맨 끝 '변경 기록' — 매일 다시 그려도 '변경 기록' 탭은 지우지 않고 맨 끝 그대로(T-147 ①)."""
    names = ["9월 요약", "9월 합성 위탁자 (synth01)", "9월 근거"]
    for old in ([(1000, names[0]), (1001, names[1]), (1002, names[2]), (77, "변경 기록")],       # 맨 끝
                [(77, "변경 기록"), (1000, names[0]), (5, "옛 탭")],                           # 사람이 앞으로 옮김
                [(77, "변경 기록")]):                                                           # 그 탭만
        c = SheetClient(old)
        GS.write_statement(c, [synthetic(True)], ISSUED)
        assert [t for _, t in c.tabs] == [*names, "변경 기록"], c.tabs
        assert c.tabs[-1][0] == 77 and 77 not in c.deleted, (c.tabs, c.deleted)
    c = SheetClient([(0, "시트1")])                                                           # 없으면 만들지 않음(칸 내용 결정 없음)
    GS.write_statement(c, [synthetic(True)], ISSUED)
    assert [t for _, t in c.tabs] == names, c.tabs
    c = SheetClient([(1001, "변경 기록"), (0, "시트1")])                                        # 번호가 새 탭과 겹침 = 쓰기 전 중단
    try:
        GS.write_statement(c, [synthetic(True)], ISSUED)
        raise AssertionError("'변경 기록' 탭 번호 겹침인데 중단 안 됨")
    except GS.StatementCheckError as exc:
        assert "변경 기록" in str(exc), exc
    assert c.calls == []
    print("test_d242_change_log_tab_kept OK")


def test_d261_e1_pending_not_negative() -> None:
    """D-261 ① E1(CURRENT_RULES 12절): 2쪽 상품 줄(이름 묶은 뒤)의 정산 예정 판매 ≥ 0 — 음수면 검산 실패(사유에 상품·금액) · 0 = 통과 ·
    확정 달(정산 예정 없음)의 확정 판매 음수는 대상 아님 · 다른 열(쿠폰·수수료 음수)은 대상 아님. 관리 비율 0~100% 밖 = D-262 ③(계산 쪽)."""
    assert GS.check(synthetic(True)) == [] and GS.check(synthetic(False)) == []
    d = synthetic(True)
    b = d["products"][1]
    a = d["products"][0]["pending"]
    a["c1"] += 270_499                                                                         # 합계는 맞춘 채 한 상품만 음수(sg0141n 11월 −270,499)
    a["subtotal"] += 270_499
    b["pending"] = {**{f"c{k}": 0 for k in range(1, 9)}, "c1": -270_499, "subtotal": -270_499}
    errs = GS.check(d)
    assert len(errs) == 1 and "합성 상품 나" in errs[0] and "-270,499" in errs[0] and "E1" in errs[0], errs
    fake = FakeClient()
    try:
        GS.write_statement(fake, [d], ISSUED)
        raise AssertionError("E1 검산 실패인데 쓰기 예외 없음")
    except GS.StatementCheckError:
        pass
    assert fake.calls == []
    a["c1"] -= 270_499
    a["subtotal"] -= 270_499
    b["pending"].update(c1=0, subtotal=0)
    assert GS.check(d) == []
    # D-405(소유자 11-25 (가)): 로켓그로스 음수 = 쿠팡 순액 그대로 통과 · 윙 음수 = 막음(합이 양수여도)
    b["pending"].update(c1=-78_000, c2=78_000, wing_c1=0)
    a["c1"] += 78_000
    a["c2"] -= 78_000
    assert GS.check(d) == [], GS.check(d)
    b["pending"].update(c1=200, c2=-200, wing_c1=-1)
    a["c1"] -= 78_200
    a["c2"] += 78_200
    errs = GS.check(d)
    assert len(errs) == 1 and "E1" in errs[0] and "합성 상품 나" in errs[0] and "윙" in errs[0], errs
    print("test_d261_e1_pending_not_negative OK")


# ── D-260 위탁자별 PDF ─────────────────────────────────────────
def _pdf_bytes(text: str, pages: int = 1) -> bytes:
    """글자 있는 합성 PDF(한글 = 유니코드 대응표 있는 Type0 글꼴) — pypdf extract_text 로 되읽힘."""
    from pypdf import PdfWriter
    from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject
    w = PdfWriter()
    codes = {ch: i + 1 for i, ch in enumerate(sorted(set(text)))}
    cmap = DecodedStreamObject()
    rows = "\n".join(f"<{i:04X}> <{ord(ch):04X}>" for ch, i in codes.items())
    cmap.set_data(("/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CMapName /X def /CMapType 2 def\n"
                   "1 begincodespacerange <0000> <FFFF> endcodespacerange\n"
                   f"{len(codes)} beginbfchar\n{rows}\nendbfchar\nendcmap end end").encode())
    desc = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/CIDFontType2"),
                             NameObject("/BaseFont"): NameObject("/X")})
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type0"),
                             NameObject("/BaseFont"): NameObject("/X"), NameObject("/Encoding"): NameObject("/Identity-H"),
                             NameObject("/DescendantFonts"): ArrayObject([desc]), NameObject("/ToUnicode"): w._add_object(cmap)})
    for _ in range(pages):
        pg = w.add_blank_page(width=595, height=842)
        st = DecodedStreamObject()
        hexs = "".join(f"{codes[ch]:04X}" for ch in text)
        st.set_data(f"BT /F1 9 Tf 10 800 Td <{hexs}> Tj ET".encode())
        pg[NameObject("/Contents")] = w._add_object(st)
        pg[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


class PdfSession:
    """구글 내보내기 흉내 — 주소의 (파일, gid) → 그 탭 PDF. 내보낸 순서를 남김."""

    def __init__(self, pdfs: dict):
        self.pdfs, self.asked = pdfs, []

    def get(self, url: str, timeout: int = 0):
        sid = url.split("/d/")[1].split("/")[0]
        gid = int(url.split("gid=")[1].split("&")[0])
        self.asked.append((sid, gid))
        body = self.pdfs.get((sid, gid))
        return SimpleNamespace(status_code=200 if body else 404, headers={"content-type": "application/pdf"}, content=body or b"none")


def _month_pdf(d: dict, extra: str = "") -> bytes:
    return _pdf_bytes(f"쿠팡 판매 정산서 {d['account']} 판매 기간 {d['period_start']} ~ {d['period_end']} "
                      f"이번 정산 금액 {d['settle_amount']:,}원 {extra}", 2)


def _pdf_case():
    """9월·10월 = 달마다 파일 1개(D-241 ⑥) · 파일마다 요약·위탁자·근거 탭 + 다른 위탁자 탭."""
    a, b = synthetic(False, "2026-09"), synthetic(True, "2026-10")
    c9 = SheetClient([(1000, "9월 요약"), (1001, "9월 남의 정산서 (other1)"), (1002, "9월 합성 위탁자 (synth01)"), (1003, "9월 근거")], "S09")
    c10 = SheetClient([(1000, "10월 요약"), (1001, "10월 합성 위탁자 (synth01)"), (1002, "10월 근거"), (77, "변경 기록")], "S10")
    return a, b, c9, c10


def test_d260_month_summary_page() -> None:
    """D-260 ② 여러 달 위탁자 PDF 첫 장 = 그 위탁자 한 명의 월별 요약: 달마다 판매 금액·쿠팡이 뺀 돈·계정 공통·별도 입금·이번 정산 금액·
    쿠팡 미확정 금액·입금 완료·입금 예정 + 합계 · '판매 기간 … · 발행 …' 굵게 · 다른 위탁자·'검토용'·내부 글자 없음."""
    from coupang_analytics import settlement_consignor_pdf as PDF
    from coupang_analytics.settlement_consignor_gsheet_layout import requests_for
    a, b, _c9, _c10 = _pdf_case()
    page = PDF.month_summary_sheet([b, a], ISSUED)                        # 넘긴 순서와 상관없이 판매 달 순서
    tx = texts(requests_for(page, 1))
    flat = [s for s, _ in tx]
    joined = chr(10).join(flat)
    for head in ("판매 금액", "쿠팡이", "계정 공통", "별도 입금", "이번 정산", "쿠팡 미확정", "입금 완료", "입금 예정"):
        assert any(s.startswith(head) for s in flat), head
    assert joined.index("9월" + chr(10)) < joined.index("10월" + chr(10)) < joined.rindex(chr(10) + "합계" + chr(10)), joined
    nums = [s for s in _numbers(requests_for(page, 1))]
    # 손 계산(synthetic 문서): 달마다 판매 1,000,000 · 뺀 돈 748,000−33,000−1,000,000 = −285,000 · 9 −33,000 · 10 +1,500 · 정산 716,500
    sep, okt = [1_000_000, -285_000, -33_000, 1_500, 716_500, 0, 716_500, 0], [1_000_000, -285_000, -33_000, 1_500, 716_500, 168_400, 548_100, 168_400]
    tot = [2_000_000, -570_000, -66_000, 3_000, 1_433_000, 168_400, 1_264_600, 168_400]
    assert nums == sep + okt + tot, nums
    who = [(s, r) for s, r in tx if "판매 기간 2026-09-01 ~ 2026-10-30" in s]
    assert who and _bold_at(*who[0], "판매 기간"), who
    assert "1,433,000원" in joined and "168,400원" in joined and "2개월" in joined, joined
    for bad in ("검토용", "아직 반영 안 된", "확인 필요", "내부용", "보기 →", "위탁자별"):
        assert bad not in joined, bad
    chk = {**a, "status": "확인 필요"}                                      # D-402 요약 머리 = '확정 전'
    j2 = chr(10).join(s for s, _ in texts(requests_for(PDF.month_summary_sheet([chk, {**chk, "period_start": "2026-10-01"}], ISSUED), 1)))
    assert "확정 전" in j2 and "확인 필요" not in j2, j2
    for bad_ds in ([a], [a, a], [a, {**b, "account": "other1"}]):          # 한 달 · 같은 달 둘 · 다른 위탁자 = 중단
        try:
            PDF.month_summary_sheet(bad_ds, ISSUED)
            raise AssertionError("월별 요약 대상 아닌데 그려짐")
        except PDF.ConsignorPdfError:
            pass
    print("test_d260_month_summary_page OK")


def _numbers(reqs: list[dict]) -> list:
    return [c["userEnteredValue"]["numberValue"] for r in reqs for row in r.get("updateCells", {}).get("rows", [])
            for c in row.get("values", []) if "numberValue" in (c.get("userEnteredValue") or {})]


def test_d260_consignor_pdf() -> None:
    """D-260 ① 위탁자 1명 = PDF 1개(판매 달 순서로 이어 붙임) · 여러 달 = 첫 장 월별 요약 · 모음 '{n}월 요약'·'{n}월 근거'(D-401 ②) 안 넣음 ·
    달 파일 둘(D-241 ⑥)에서 모음 · 월별 요약 탭은 잠깐 그렸다 지움(시트 탭 그대로) · 실패 = 파일 안 만듦."""
    from pypdf import PdfReader

    from coupang_analytics import settlement_consignor_pdf as PDF
    a, b, c9, c10 = _pdf_case()
    G = PDF.SUMMARY_GID
    good = {("S09", 1002): _month_pdf(a), ("S10", 1001): _month_pdf(b), ("S10", G): _pdf_bytes("쿠팡 판매 정산서 — 월별 요약 1,433,000원")}
    clients = {"2026-09": c9, "2026-10": c10}
    with tempfile.TemporaryDirectory() as td:
        before = [list(c9.tabs), list(c10.tabs)]
        ses = PdfSession(good)
        out = PDF.consignor_pdf(ses, clients, [b, a], ISSUED, Path(td))
        assert out.name == "위탁자정산서_합성 위탁자_synth01_9~10월.pdf" and out.parent == Path(td), out
        assert sorted(ses.asked) == [("S09", 1002), ("S10", 1001), ("S10", G)], ses.asked   # 요약·근거·남의 탭은 내보내지 않음
        pages = [p.extract_text() for p in PdfReader(str(out)).pages]
        assert len(pages) == 5 and "월별 요약" in pages[0] and "2026-09-01" in pages[1] and "2026-10-01" in pages[3], pages
        assert [c9.tabs, c10.tabs] == before, (c9.tabs, c10.tabs)                      # 월별 요약 탭 지워짐 · 다른 탭 그대로
        one = PDF.consignor_pdf(PdfSession(good), {"2026-09": c9}, [a], ISSUED, Path(td))     # 한 달 = 요약 첫 장 없음
        assert one.name == "위탁자정산서_합성 위탁자_synth01_9월.pdf" and len(PdfReader(str(one)).pages) == 2, one
        assert c9.tabs == before[0]
    e1 = {**b, "products": [{**b["products"][0], "pending": {**b["products"][0]["pending"], "c1": -1}}, b["products"][1]]}
    cases = {
        "탭 없음": (good, {"2026-09": c9, "2026-10": SheetClient([(1000, "10월 요약")], "S10")}, [a, b]),
        "그 달 시트 없음": (good, {"2026-09": c9}, [a, b]),
        "내보내기 실패": ({k: v for k, v in good.items() if k != ("S10", 1001)}, clients, [a, b]),
        "시트 금액 ≠ 자료": ({**good, ("S09", 1002): _month_pdf({**a, "settle_amount": 1})}, clients, [a, b]),
        "다른 달 탭": ({**good, ("S09", 1002): _month_pdf(b)}, clients, [a, b]),
        "요약 탭 금액 다름": ({**good, ("S10", G): _pdf_bytes("월별 요약 1원")}, clients, [a, b]),
        "검토용 글자": ({**good, ("S09", 1002): _month_pdf(a, "검토용")}, clients, [a, b]),
        "내부 글자": ({**good, ("S09", 1002): _month_pdf(a, "확인 필요")}, clients, [a, b]),
        "검산 실패": (good, clients, [a, e1]),
    }
    for name, (pdfs, cl, ds) in cases.items():
        with tempfile.TemporaryDirectory() as td:
            try:
                PDF.consignor_pdf(PdfSession(pdfs), cl, ds, ISSUED, Path(td))
                raise AssertionError(f"{name}: 중단 안 됨")
            except PDF.ConsignorPdfError as exc:
                assert "synth01" in str(exc), (name, exc)
            assert list(Path(td).iterdir()) == [], name
            assert [c9.tabs, c10.tabs] == before, (name, c10.tabs)                     # 실패해도 월별 요약 탭 안 남음
    stale = SheetClient([*before[1], (G, PDF.summary_title(a))], "S10")                # 앞 실행이 끊겨 남은 월별 요약 탭 = 다시 그림
    with tempfile.TemporaryDirectory() as td:
        PDF.consignor_pdf(PdfSession(good), {"2026-09": c9, "2026-10": stale}, [a, b], ISSUED, Path(td))
        assert stale.tabs == before[1], stale.tabs
    print("test_d260_consignor_pdf OK")


def test_d260_pdf_run() -> None:
    """위탁자별 PDF 묶기 입구: 자료 json 폴더 + 달별 시트 주소 → 위탁자마다 PDF 1개 · 위탁자 하나가 막히면 그 위탁자만 사유(나머지 계속)."""
    from coupang_analytics import settlement_consignor_pdf as PDF
    a, b, c9, c10 = _pdf_case()
    x = {**synthetic(False, "2026-09"), "account": "other2", "ceo": "합성 위탁자 둘"}
    with tempfile.TemporaryDirectory() as td:
        data, out = Path(td) / "위탁자정산서", Path(td) / "PDF"
        data.mkdir()
        for d in (a, b, x):
            (data / f"{d['account']}_{d['period_start'][:7].replace('-', '')}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        (data / "_요약.json").write_text("[]", encoding="utf-8")
        good = {("S09", 1002): _month_pdf(a), ("S10", 1001): _month_pdf(b), ("S10", PDF.SUMMARY_GID): _pdf_bytes("월별 요약 1,433,000원")}
        made, failed = PDF.run(data, {"2026-09": "u9", "2026-10": "u10"}, ISSUED, out, session=PdfSession(good),
                               client_for=lambda u: {"u9": c9, "u10": c10}[u], log=lambda m: None)
        assert [p.name for p in made] == ["위탁자정산서_합성 위탁자_synth01_9~10월.pdf"], made
        assert len(failed) == 1 and failed[0][0] == "other2" and "탭 없음" in failed[0][1], failed
        try:
            PDF.run(data, {}, ISSUED, out, accounts=["none9"], session=PdfSession(good), client_for=lambda u: c9, log=lambda m: None)
            raise AssertionError("없는 계정ID 인데 중단 안 됨")
        except PDF.ConsignorPdfError:
            pass
    print("test_d260_pdf_run OK")


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


# ── ④ 배치 실행 경로 run_job(D-399 계획 설계 3·5·6 · 레인 B) — 계산 경계만 가짜 · 반복·격리·시트 고르기·보고 꼴을 봄 ──
def _vs():
    spec = importlib.util.spec_from_file_location("verify_statements_tool", ROOT / "tools" / "verify_settlement_statements_offline.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class BrokenClient(FakeClient):
    def batch_update(self, requests: list[dict]) -> dict:
        raise RuntimeError("합성 시트 오류")


def _job_output(base: Path, V) -> None:
    V.touch_inputs(base / "정산서" / "입력")
    (base / "정산").mkdir()
    for n in ("정산집계_261123_010101.xlsx", "정산집계_261124_010101.xlsx"):
        (base / "정산" / n).write_text("", encoding="utf-8")


def _job_fakes(V, out: Path, accts: list[str]):
    """b2 = 옛 위탁정산서 예외 · c3 = 새 형식 계정 예외 · e5 = 2026-10 검산 실패 · 나머지 = 2026-09·10 둘 다 통과."""
    def source(ctx, acct):
        if acct.endswith("-c3"):
            raise ValueError("합성 계정 오류 c3")
        return {"aid": acct.rsplit("-", 1)[-1]}

    def build(ctx, src, m, judge):
        d = synthetic(True, m)
        d["account"] = src["aid"]
        if src["aid"] == "e5" and m == "2026-10":
            d["settle_amount"] += 1
        return d

    layer = V.fake_statement_layer(out, accts, bad={"b2"})
    return layer, V._Patch((CM, "account_source", source), (CM, "sale_months", lambda src: ["2026-09", "2026-10"]),
                           (CM, "build_month", build))


def test_run_job_abort() -> None:
    from coupang_analytics import settlement_statement_context as CTX
    from coupang_analytics import statement_jobs_consignor as J
    with tempfile.TemporaryDirectory() as d:
        logs: list[str] = []
        got = J.run_job({"output": d}, logs.append)
        assert set(got) == {"ok", "skipped", "files", "abort", "sheet", "sheets"} and got["sheet"] is None, got
        assert (got["ok"], got["skipped"], got["files"]) == ([], [], []), got
        assert all(n in got["abort"] for n in CTX.REQUIRED) and "정산집계" in got["abort"] and "정산 폴더" in got["abort"], got
        assert logs and "시작 전 중단" in logs[0], logs
        assert not (Path(d) / "정산서" / "위탁정산서_" ).exists() and not any(Path(d).rglob("*.xlsx")), "중단인데 파일 생김"


def test_run_job_isolation_and_sheets() -> None:
    from coupang_analytics import statement_jobs_consignor as J
    V = _vs()
    accts = ["가-상회-a1", "나-상회-b2", "다-상회-c3", "라-상회-d4", "마-상회-e5"]
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        _job_output(base, V)
        out = base / "결과"
        (base / "정산서" / "입력" / J.SHEETS_FILE).write_text(json.dumps({"_설명": "합성", "2026-09": "S09"}), encoding="utf-8")
        fakes: dict = {}

        def client_for(s):
            fakes[s] = FakeClient()
            return fakes[s]

        layer, cm = _job_fakes(V, out, accts)
        buf = io.StringIO()
        with layer, cm, contextlib.redirect_stdout(buf):
            got = J.run_job({"output": str(base), "out": str(out), "basis": "2026-11-24", "issued": "2026-11-24", "sheet": True,
                             "skip_accounts": {"라-상회-d4": "로그인 막힘"}, "cycle": "x", "run_id": "y"}, print, client_for=client_for)
        log = buf.getvalue()
        assert got["abort"] is None and got["ok"] == ["a1"], got                      # 성공 계정만
        assert all(set(x) == {"id", "account", "contract", "month", "product", "amount", "reason"} for x in got["skipped"]), got["skipped"]
        assert got["sheet"] == "S09" and got["sheets"] == {"2026-09": "S09"}, got                 # 레인 A 가 '확인 필요' 탭을 쓸 시트
        why = {x["id"]: x for x in got["skipped"]}
        assert len(got["skipped"]) == 5 and set(why) == {"d4", "b2", "c3", "e5", "시트 2026-10"}, got["skipped"]
        assert why["d4"]["reason"] == f"{J.SKIP_REASON} — 로그인 막힘" and why["d4"]["account"] == "라-상회-d4", why["d4"]
        assert "위탁정산서 못 만듦" in why["b2"]["reason"] and "합성 계정 오류 c3" in why["c3"]["reason"], why
        assert why["e5"]["reason"].startswith("검산 실패") and why["e5"]["month"] == "2026-10", why["e5"]
        assert why["e5"]["amount"] == 716_501 and why["e5"]["account"] == "마-상회-e5", why["e5"]   # 그 달 시트에 못 넣은 정산 금액
        assert J.NO_SHEET in why["시트 2026-10"]["reason"] and why["시트 2026-10"]["amount"] == 716_500, why["시트 2026-10"]
        assert "정산집계_261124_010101.xlsx" in log, "최신 정산집계 자동 선택 안 됨"
        assert log.count("❌ 정산서 못 만듦 b2") == 1, log                          # print 를 on_log 로 줘도 되돌아 들어오지 않음
        names = {Path(f).name for f in got["files"]}
        assert {"a1_202609.json", "e5_202610.json", "b2_202609.json", "_요약.json", "전체_합성.xlsx"} <= names, names
        assert not any(n.startswith(("c3", "d4")) for n in names) and all(Path(f).is_file() for f in got["files"]), names
        assert set(fakes) == {"S09"}                                                 # 시트 있는 달만 · 없는 달 = 확인 필요
        titles = [r["addSheet"]["properties"]["title"] for r in fakes["S09"].calls[0] if "addSheet" in r]
        assert [t for t in titles if "(" in t] == ["9월 합성 위탁자 (a1)", "9월 합성 위탁자 (e5)"], titles   # b2·c3·d4 = 안 씀
        layer, cm = _job_fakes(V, out, accts)
        with layer, cm, contextlib.redirect_stdout(io.StringIO()):
            off = J.run_job({"output": str(base), "out": str(out), "issued": "2026-11-24", "skip": ["d4"]}, print,
                            client_for=client_for)
            bad = J.run_job({"output": str(base), "out": str(out), "issued": "2026-11-24", "write_sheet": True,
                             "sheets": {"2026-09": "X", "2026-10": "Y"}}, print, client_for=lambda s: BrokenClient())
        assert off["ok"] == ["a1"] and not any(x["id"].startswith("시트") for x in off["skipped"]) and off["sheet"] is None, off  # 시트 쓰기 끔
        assert {x["id"]: x["reason"][:10] for x in bad["skipped"] if x["id"].startswith("시트")} == \
            {"시트 2026-09": "시트 쓰기 실패 —", "시트 2026-10": "시트 쓰기 실패 —"}, bad["skipped"]


def test_d262_excluded_pending_listed() -> None:
    """D-262 ③ · D-399 ④ — 못 나눠 뺀 정산 예정분 = 정산서는 발행(계정 성공 · 검산 실패 아님) + '확인 필요' 목록에 금액·사유 한 줄."""
    from coupang_analytics import statement_jobs_consignor as J
    d = synthetic(True, "2026-10")
    d["pending_excluded"] = [{"판매 방식": "윙", "판매": 1300, "정산": 1077, "사유": "나눌 판매 없음"}]
    r = {"account": "a1", "month": "2026-10", "data": d, "failures": J.statement_failures(d)}
    assert r["failures"] == [], r["failures"]
    ok, out, sheet_ok = J._merge({"made_ids": ["a1"], "none": [], "failed": []}, [r], [], {}, {"a1": "가-상회-a1"})
    assert ok == ["a1"] and sheet_ok == {"a1"}, (ok, sheet_ok)
    assert [(x["id"], x["account"], x["month"], x["amount"]) for x in out] == [("a1", "가-상회-a1", "2026-10", 1077)], out
    assert "그 금액만 빼고" in out[0]["reason"] and "1,300" in out[0]["reason"] and "나눌 판매 없음" in out[0]["reason"], out
    print("test_d262_excluded_pending_listed OK")


def test_inputs_pack() -> None:
    spec = importlib.util.spec_from_file_location("statement_inputs_pack", ROOT / "tools" / "statement_inputs_pack.py")
    assert spec and spec.loader
    P = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(P)
    import zipfile
    from datetime import datetime
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        inp, sel, dest = base / "입력", base / "입력_셀독", base / "보내기"
        (inp / "_대안").mkdir(parents=True)
        (inp / "보관").mkdir()
        (sel / "판정").mkdir(parents=True)
        for p, t in ((inp / "ledger.json", '{"accounts": []}'), (inp / "사업자_대응표.csv", "계정ID,사업자\n"),
                     (inp / "_준비_보고.md", "x"), (inp / "_대안" / "a.json", "{}"), (inp / "보관" / "old.json", "{}"),
                     (sel / "판정" / "상품군.json", "{}")):
            p.write_text(t, encoding="utf-8")
        before = sorted((p, p.read_bytes()) for p in base.rglob("*") if p.is_file())
        now = datetime(2026, 11, 24, 21, 0, 0)
        z1 = P.pack(inp, sel, dest, now=now, log=lambda s: None)
        z2 = P.pack(inp, sel, dest, now=now, log=lambda s: None)
        assert z1.name == "정산서입력_261124.zip" and z2.name == "정산서입력_261124_210000.zip" and z1.is_file(), (z1, z2)
        with zipfile.ZipFile(z1) as z:
            got = sorted(i.filename for i in z.infolist())
            assert all(i.flag_bits & 0x800 for i in z.infolist()), "이름 UTF-8 표시 없음"
        assert got == ["입력/ledger.json", "입력/사업자_대응표.csv", "입력_셀독/판정/상품군.json"], got
        after = sorted((p, p.read_bytes()) for p in base.rglob("*") if p.is_file() and p.parent != dest)
        assert after == before, "묶음 도구가 원본을 바꾸거나 지움"
        (inp / "ledger.json").write_text('{"accounts": [{"id": "a", "비밀번호": "x"}]}', encoding="utf-8")
        try:
            P.pack(inp, sel, dest, now=now, log=lambda s: None)
            raise AssertionError("비밀번호 칸이 있는데 묶음")
        except ValueError as exc:
            assert "비밀번호" in str(exc)
        assert len(list(dest.iterdir())) == 2, "중단인데 zip 생김"
        (inp / "ledger.json").write_text('{"accounts": []}', encoding="utf-8")
        assert P.seldoc_missing(sel) == ["사업자_대응표.csv", "셀독_계약상품군_판정.json", "셀독_계약유형_판정.json", P.SELDOC_DB]
        try:
            P.pack(inp, sel, dest, now=now, log=lambda s: None, strict=True)             # 배포 빌드 = 셀독 입력 빠지면 묶지 않음
            raise AssertionError("셀독 입력이 빠졌는데 묶음(strict)")
        except ValueError as exc:
            assert "셀독 입력 빠짐" in str(exc)
        assert len(list(dest.iterdir())) == 2
        for n in ("사업자_대응표.csv", "셀독_계약상품군_판정.json", "셀독_계약유형_판정.json", "계약서_정밀분석_DB_v6.xlsx", "계약서_정밀분석_DB_v5.xlsx"):
            (sel / n).write_text("{}" if n.endswith(".json") else "계정ID\n", encoding="utf-8")
        try:
            P.pack(inp, sel, dest, now=now, log=lambda s: None)
            raise AssertionError("계약 DB 가 둘인데 묶음")
        except ValueError as exc:
            assert "1개만" in str(exc)
        (sel / "계약서_정밀분석_DB_v5.xlsx").unlink()
        assert P.seldoc_missing(sel) == []


def test_d401_remarks_and_evidence() -> None:
    """D-401(소유자 11-24 "(가)+(나) 둘 다"): ① 위탁자 탭 1쪽 고정 '비고' 상자 = 위탁자용 문장(remarks)만 · 문장 없어도 상자 있음(D-343 공란) ·
    내부 판단(judgments)·'확인 필요'·근거는 위탁자 탭에 없음 ② 달마다 '{n}월 근거' 탭 = judgments·_근거·pending_detail·9 원문 항목·비고 전부 ·
    PDF 대상(pdf_gids) = 위탁자 탭만. ③ remarks 문장 종류: 정산 예정 금액(쿠팡 미확정) · 74 남은 청구 예상값(숫자 있을 때만) — 그 밖 = 내부."""
    from coupang_analytics import settlement_consignor_month_out as OUT
    NL = chr(10)
    inner = ["확인 필요 — 보류 해제 규칙 미확정(해제 2건 · 합 1,950,408원 · 지급 완료 2건 1,950,408원)", "합성 Claude 판단 문장 가나다"]
    a = {**synthetic(True), "judgments": inner, "remarks": ["합성 위탁자용 비고 문장"], "_근거": {"합성근거키": {"값": 1}}}
    a["common"]["items"][2].update(note="합성 BI 비고 내부")
    b = {**synthetic(False), "account": "synth02", "ceo": "합성 위탁자 둘", "judgments": ["합성 둘 판단"]}
    plan = GS.build_statement([a, b], ISSUED)
    ev = [t for t in plan.tabs if t.kind == "evidence"]
    assert [t.title for t in ev] == ["9월 근거"] and plan.pdf_gids() == [1001, 1002], ([t.title for t in plan.tabs], plan.pdf_gids())
    assert not (structure_errors(plan) + page_errors(plan) + decision_text_errors(plan))
    ta, tb = plan.tabs[1], plan.tabs[2]
    ja, jb = (NL.join(s for s, _ in texts(t.requests)) for t in (ta, tb))
    assert "비고" in [s for s, _ in texts(ta.requests)] and "비고" in [s for s, _ in texts(tb.requests)]       # 문장 없어도 상자(공란)
    assert "· 합성 위탁자용 비고 문장" in ja and ta.pages == tb.pages == 2, (ta.pages, tb.pages)
    for bad in inner + ["합성 둘 판단", "확인 필요", "합성근거키", "합성 BI 비고 내부"]:
        assert bad not in ja and bad not in jb, bad
    je = NL.join(s for s, _ in texts(ev[0].requests))
    for want in inner + ["합성 둘 판단", "합성근거키", "합성 BI 비고 내부", "합성 위탁자용 비고 문장", '"방법": "합성"', "내부용"]:
        assert want in je, want
    # 문장 종류(숫자 모듈): 정산 예정 · 74 예상값 숫자 = 위탁자용 / 예상값 없음(입력 없음) = 넣지 않음
    st = SimpleNamespace(m="2026-09", expect={OUT.BI_EXPECT: {"예상값": 33_000}})
    r = OUT.remarks(st, {"pending_total": 168_400})
    assert len(r) == 2 and "168,400원" in r[0] and "33,000원" in r[1] and not any("확인 필요" in x for x in r), r
    assert OUT.remarks(SimpleNamespace(m="2026-09", expect={OUT.BI_EXPECT: {"예상값": None}}), {"pending_total": 0}) == []
    print("test_d401_remarks_and_evidence OK")


def test_d402_check_status_header() -> None:
    """D-402(소유자 11-24 "'확정 전'으로 통일"): 상태 '확인 필요' 달 = 위탁자 탭 1쪽·2쪽 머리 둘 다 '확정 전'(내부 '확인 필요' 글자 없음) ·
    내부 '{n}월 근거' 탭은 '상태 확인 필요' 그대로 · 정산 예정 포함·확정 달은 지금 글자 그대로."""
    NL = chr(10)
    a = {**synthetic(False), "status": "확인 필요", "judgments": ["확인 필요 — 보류 해제 규칙 미확정(해제 1건)"]}
    plan = GS.build_statement([a], ISSUED)
    assert not (structure_errors(plan) + page_errors(plan) + decision_text_errors(plan))
    ta = plan.tabs[1]
    ja = NL.join(s for s, _ in texts(ta.requests))
    assert "확인 필요" not in ja, ja
    assert ja.count("확정 전") >= 2, ja                                      # 1쪽 머리 + 2쪽 머리
    je = NL.join(s for s, _ in texts([t for t in plan.tabs if t.kind == "evidence"][0].requests))
    assert "상태 확인 필요" in je, je
    for st, want in (("정산 예정 포함", "정산 예정 포함"), ("확정", "확정")):
        assert GS_PAGES.shown_status({"status": st}) == want
    assert GS_PAGES.shown_status({"status": "확인 필요"}) == "확정 전"
    print("test_d402_check_status_header OK")


def test_t175_old_forecast_record() -> None:
    """T-175 ③: 달 표시 칸 저장 전 예정 기록 줄(output44 예정 RG 29,709줄 전부) = 추가 공제 나머지를 9 에 못 넣음 → 0 으로 숨기지 않고
    '확인 필요' 문장(금액 포함) · 새 기록·쿠팡 원문 줄 = 문장 없음. 금액 = output44 gyi0101 2026-03-05 줄(추가공제 2,587,570 − 광고 271,619 − 빠른정산 2,207,051)."""
    from types import SimpleNamespace

    from coupang_analytics import settlement_consignor_month_cost as C
    old = {"채널": "로켓그로스", "수집일": "2026-11-23", "totalPayableAmount": 3_110_470, "totalAdditionalDeductionAmount": 2_587_570.0,
           "totalAdSalesDeductionAmount": 271_619.0, "totalArFactoringDeductionAmount": 2_207_051.0, "totalSalesAdjustment": 0}
    st = SimpleNamespace(j=[])
    C._old_record(st, ("2026-12-01", "2026-11-10", "2026-11-16", "로켓그로스", 70), old)
    assert len(st.j) == 1 and "108,900원" in st.j[0] and "확인 필요" in st.j[0], st.j
    new = {**old, "totalPostPurchaseDeductionAmount": 0, "totalSubscriptionFeeDeductionAmount": 108_900.0}
    st2 = SimpleNamespace(j=[])
    C._old_record(st2, ("k",), new)
    C._old_record(st2, ("k",), {k: v for k, v in old.items() if k != "수집일"})
    assert st2.j == [], st2.j
    print("test_t175_old_forecast_record OK")


def test_new23_cross_week_flag() -> None:
    """신규-23: 쿠팡 주 판매 기간은 달 끝에서 잘림(output44 지급 줄 3,469·예정 줄 522 중 달 걸친 70% 주 0) → 새 정산서는 주 시작 달 그대로 ·
    걸친 주가 나오면 '확인 필요' 문장(금액 그대로) · 한 달 주 = 문장 없음."""
    from coupang_analytics.settlement_consignor_month_calc import cross_weeks
    us = [("로켓그로스", "2026-09", 100, 70, "쿠팡 계산", "n", [("2026-09-28", "2026-10-04", 100, 70), ("2026-09-21", "2026-09-27", 1, 1)]),
          ("윙", "2026-09", 5, 4, "k", "n")]
    got = cross_weeks(us, "2026-09")
    assert len(got) == 1 and "2026-09-28~2026-10-04" in got[0] and "확인 필요" in got[0], got
    assert cross_weeks([("로켓그로스", "2026-09", 1, 1, "k", "n", [("2026-09-01", "2026-09-06", 1, 1)])], "2026-09") == []
    print("test_new23_cross_week_flag OK")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    for f in (test_run_job_abort, test_run_job_isolation_and_sheets, test_d262_excluded_pending_listed, test_inputs_pack):
        f()
    for f in (test_cum_round, test_product_table, test_rg_kinds, test_common_fixed, test_post_purchase, test_ad_nocamp_d317, test_t186_wing_ad_deducted, test_t186_wing_ad_carry, test_t186_ad_bills_file, test_t186_2025_bill_not_owed, test_t186_partly_deducted, test_t186_rg_month_border, test_t179_milk_months, test_t179_ad_wait, test_t179_cfs_no_line_period, test_t179_cash_reference, test_t179_pending_rg_missing_70,
              test_t175_old_forecast_record, test_new23_cross_week_flag, test_d401_remarks_and_evidence, test_d402_check_status_header, test_expect_values, test_flow_fixed, test_t125_additional_pay, test_d391_unknown_ship_same_month_wing_ratio, test_failed_checks, test_load_judge,
              test_sale_months_2025_excluded, test_render, test_fixed_render, test_product_pages, test_overflow, test_unsplittable, test_check_reject,
              test_multi_month, test_d242_change_log_tab_kept, test_d261_e1_pending_not_negative, test_d260_month_summary_page, test_d260_consignor_pdf,
              test_d260_pdf_run, test_tool):
        f()
    print("✅ 위탁자 정산서 3차 형식 시험(숫자 반올림·상품표 열 합·종류별 9줄·검산 기준 · 그리기 구조·쪽 높이·결정 문구·넘침·검산/여러 달 거부 · 입구 · D-343 고정 형식(고정 줄·공란·쪽 규칙)·D-324 리뷰 이벤트) 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
