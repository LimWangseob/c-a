"""정산 파일 병합 → 계정·상품·월별 정산 집계 + 계약자 정산금액. SSOT=designs/SETTLEMENT_MODULE.md.

소유자 요구(2026-10-06): 윙 + 로켓그로스 정산 파일을 **병합해 상품별 최종 정산금액**을 내고,
**계약자 정산금액 = 계약금액 − 쿠팡이 정산한 금액**. 계약금액은 나중에 입력(없으면 그 칸은 비움 — 0 으로 꾸미지 않음).

집계 규칙:
- 주문 단위 집계는 **주정산 파일만**(윙 최종액 파일은 같은 주문이 다시 들어 있어 이중 집계 → 제외, 함정 1).
- 같은 파일(계정·채널·리포트·기간)이 두 번 있어도 한 번만. 같은 줄(주문·옵션·유형·날짜·금액)이 겹치면 한 번만(경고).
- 월 = 매출인식일 기준(윙=구매확정일, 로켓그로스=매출인식일). 날짜 없는 금액 줄(윙 배송비 등)은 그 파일 정산 기간
  끝의 달로 넣고 **건수를 경고로 남긴다**.
- 상품 = 계정 + 등록상품ID(윙 '상품 ID'·로켓그로스 '등록상품 ID'). 배송비 줄은 '배송비' 묶음.
- ⚠ 로켓그로스 부가 비용(밀크런·광고비·입출고/보관 등)은 아직 반영 전 → 열 이름에 '부가비용 차감 전'으로 명시.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .settlement_files import CH_WING, SettleFile

SHIPPING_KEY = "배송비"


@dataclass
class ProductMonth:
    account: str
    month: str
    product_id: str
    product_name: str = ""
    wing_qty: int = 0
    wing_sales: int = 0
    wing_settle: int = 0
    rg_qty: int = 0
    rg_sales: int = 0
    rg_settle: int = 0
    coupon: int = 0
    fee: int = 0

    @property
    def settle_total(self) -> int:
        return self.wing_settle + self.rg_settle


@dataclass
class StatsResult:
    products: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def account_months(self) -> dict:
        out: dict = {}
        for p in self.products:
            a = out.setdefault((p.account, p.month), {"wing": 0, "rg": 0})
            a["wing"] += p.wing_settle
            a["rg"] += p.rg_settle
        return out

    def account_totals(self) -> dict:
        out: dict = {}
        for p in self.products:
            out[p.account] = out.get(p.account, 0) + p.settle_total
        return out


def _order_files(files: list[SettleFile], warns: list) -> list[SettleFile]:
    seen, keep = set(), []
    for f in files:
        if f.channel == CH_WING and f.kind == "최종액":
            continue                                  # 같은 주문이 주정산 파일에 있음(이중 집계 방지)
        key = (f.account, f.channel, f.report, f.period_start, f.period_end)
        if key in seen:
            warns.append(f"같은 정산 파일이 두 번 있음 — 한 번만 집계: {key}")
            continue
        seen.add(key)
        keep.append(f)
    return keep


def _add(p: ProductMonth, r) -> None:
    if r.channel == CH_WING:
        p.wing_qty += r.qty
        p.wing_sales += r.sales
        p.wing_settle += r.settle
    else:
        p.rg_qty += r.qty
        p.rg_sales += r.sales
        p.rg_settle += r.settle
    p.coupon += r.coupon
    p.fee += r.fee
    if not p.product_name and r.product_name:
        p.product_name = r.product_name


def aggregate(files: list[SettleFile]) -> StatsResult:
    """정산 파일들 → 계정·월·상품별 집계(정렬: 계정 → 월 → 상품)."""
    res = StatsResult()
    table: dict = {}
    seen_rows: set = set()
    undated = dup = 0
    for f in _order_files(files, res.warnings):
        for r in f.rows:
            rk = (r.channel, r.account, r.order_id, r.option_id, r.kind, r.recognized, r.settle, r.qty)
            if rk in seen_rows:
                dup += 1
                continue
            seen_rows.add(rk)
            day = r.recognized or f.period_end
            undated += r.recognized is None
            pid = r.product_id or (SHIPPING_KEY if r.option_id.startswith("<") else r.option_id)
            key = (r.account, f"{day:%Y-%m}", pid)
            _add(table.setdefault(key, ProductMonth(r.account, f"{day:%Y-%m}", pid)), r)
    if undated:
        res.warnings.append(f"날짜 없는 금액 줄 {undated}건 — 각 파일 정산 기간 끝의 달로 집계")
    if dup:
        res.warnings.append(f"여러 파일에 겹친 같은 줄 {dup}건 — 한 번만 집계")
    res.products = [table[k] for k in sorted(table)]
    return res


def contractor_amount(contract_amount: int | None, coupang_settled: int) -> int:
    """계약자 정산금액 = 계약금액 − 쿠팡 정산금액(소유자 정의). 계약금액이 없으면 ValueError(0 으로 가정하지 않음)."""
    if contract_amount is None:
        raise ValueError("계약금액이 입력되지 않아 계약자 정산금액을 계산할 수 없음")
    if isinstance(contract_amount, bool) or not isinstance(contract_amount, int):
        raise TypeError(f"계약금액은 원 단위 정수: {contract_amount!r}")
    return contract_amount - coupang_settled


_P_HEAD = ["계정", "월(매출인식)", "등록상품ID", "상품명", "윙 수량", "윙 판매액", "윙 정산금액", "로켓그로스 수량",
           "로켓그로스 매출금액", "로켓그로스 정산대상액", "판매자할인쿠폰", "판매수수료(VAT포함)",
           "쿠팡 정산금액 합계(부가비용 차감 전)"]
_A_HEAD = ["계정", "쿠팡 정산금액 합계(부가비용 차감 전)", "계약금액", "계약자 정산금액(계약금액−쿠팡 정산금액)"]


def write_stats(path, res: StatsResult, contracts: dict | None = None) -> Path:
    """집계 엑셀: '상품별 월별'·'계정별 월별'·'계약자 정산'·'경고' 시트. contracts={계정: 계약금액}(없는 계정은 빈칸)."""
    import openpyxl
    contracts = contracts or {}
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "상품별 월별"
    ws.append(_P_HEAD)
    for p in res.products:
        ws.append([p.account, p.month, p.product_id, p.product_name, p.wing_qty, p.wing_sales, p.wing_settle,
                   p.rg_qty, p.rg_sales, p.rg_settle, p.coupon, p.fee, p.settle_total])
    am = wb.create_sheet("계정별 월별")
    am.append(["계정", "월(매출인식)", "윙 정산금액", "로켓그로스 정산대상액", "합계(부가비용 차감 전)"])
    for (acct, month), v in sorted(res.account_months().items()):
        am.append([acct, month, v["wing"], v["rg"], v["wing"] + v["rg"]])
    cs = wb.create_sheet("계약자 정산")
    cs.append(_A_HEAD)
    for acct, settled in sorted(res.account_totals().items()):
        c = contracts.get(acct)
        cs.append([acct, settled, c if c is not None else "", contractor_amount(c, settled) if c is not None else ""])
    wn = wb.create_sheet("경고")
    wn.append(["경고"])
    for w in res.warnings:
        wn.append([w])
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    wb.save(p)
    return p
