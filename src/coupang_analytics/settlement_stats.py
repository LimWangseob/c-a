"""정산 파일 병합 → 계정·상품·월별 정산 집계 + 계약자 정산금액. SSOT=designs/SETTLEMENT_MODULE.md.

소유자 요구(2026-10-06): 윙 + 로켓그로스 정산 파일을 **병합해 상품별 최종 정산금액**을 내고,
**계약자 정산금액 = 계약금액 − 쿠팡이 정산한 금액**. 계약금액은 나중에 입력(없으면 그 칸은 비움 — 0 으로 꾸미지 않음).

집계 규칙:
- 주문 단위 집계는 **주정산 파일만**(윙 최종액 파일은 같은 주문이 다시 들어 있어 이중 집계 → 제외, 함정 1).
- 같은 파일(계정·채널·리포트·기간)이 두 번 있어도 한 번만. 같은 줄(주문·옵션·유형·날짜·금액)이 겹치면 한 번만(경고).
- 월 = 매출인식일 기준(윙=구매확정일, 로켓그로스=매출인식일). 날짜 없는 금액 줄(윙 배송비 등)은 그 파일 정산 기간
  끝의 달로 넣고 **건수를 경고로 남긴다**.
- 상품 = 계정 + 등록상품ID(윙 '상품 ID'·로켓그로스 '등록상품 ID'). 배송비 줄은 '배송비' 묶음.
- ⚠ 로켓그로스 부가 비용(밀크런·광고비·입출고/보관 등)은 상품별 집계엔 아직 반영 전 → 열 이름에 '부가비용 차감 전'.
  실제 지급액·차감 내역은 '쿠팡 지급 내역'(정산현황 금액 그대로) · 비용 리포트 합은 '로켓그로스 비용' 시트.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import payout as P
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
    """같은 파일(계정·채널·유형·리포트·기간)은 한 번만."""
    seen, keep = set(), []
    for f in files:
        key = (f.account, f.channel, f.kind, f.report, f.period_start, f.period_end)
        if key in seen:
            warns.append(f"같은 정산 파일이 두 번 있음 — 한 번만 집계: {key}")
            continue
        seen.add(key)
        keep.append(f)
    return keep


def _order_rows(files: list[SettleFile], warns: list):
    """집계할 (파일, 줄). 윙 최종액 파일은 같은 주문이 주정산 파일에 다시 들어 있어(이중 집계·함정 1)
    **주정산 파일이 없는 정산예정일의 줄만** 쓴다(주정산 파일을 아직 못 받은 주를 빠뜨리지 않게)."""
    files = _order_files(files, warns)
    covered = {(f.account, f.settle_date) for f in files if f.channel == CH_WING and f.kind != "최종액"}
    filled = 0
    for f in files:
        final = f.channel == CH_WING and f.kind == "최종액"
        for r in f.rows:
            if final and (r.account, r.due) in covered:
                continue
            filled += final
            yield f, r
    if filled:
        warns.append(f"윙 최종액 파일에서 주정산 파일이 없는 주의 줄 {filled}건을 집계에 넣음")


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
    for f, r in _order_rows(files, res.warnings):
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


def payout_lines(files: list[SettleFile], warns: list | None = None) -> list[tuple]:
    """파일별 계산 지급액(예상) — 쿠팡 화면 금액과 대조용. (파일, 구분, 금액) 목록. 실측 규칙은 payout.payout_amount.
    윙 주정산=70% · 윙 최종액=30%(정산예정일별 주 합계로 계산) + 주정산 파일이 없는 주의 70%(월별 파일에서 계산,
    과거 달은 월별 파일만 받으므로) · 로켓그로스=같은 파일이 70%·30% 두 지급에 쓰임."""
    warns = warns if warns is not None else []
    covered = {(f.account, f.settle_date) for f in files if f.channel == CH_WING and f.kind != "최종액"}
    out = []
    for f in files:
        amounts = [r.settle for r in f.rows]
        if f.channel == CH_WING and f.kind == "최종액":
            out += _final_lines(f, covered, warns)
        elif f.channel == CH_WING:
            out.append((f, "주정산 70%", P.payout_amount(P.PAYOUT_MP_WEEKLY_1ST, [sum(amounts)])))
        else:
            out.append((f, "주정산 70%", P.payout_amount(P.PAYOUT_RG_WEEKLY_1ST, amounts)))
            out.append((f, "2차 30%", P.payout_amount(P.PAYOUT_RG_WEEKLY_FINAL, amounts)))
    return out


def _final_lines(f: SettleFile, covered: set, warns: list) -> list[tuple]:
    weeks: dict = {}
    for r in f.rows:
        weeks[r.due] = weeks.get(r.due, 0) + r.settle
    if None in weeks:
        warns.append(f"{f.account} 윙 최종액 {f.period_start}~{f.period_end}: 정산예정일 없는 금액 줄 — "
                     "30% 계산이 화면과 다를 수 있음")
    lines = [(f, f"주정산 70%(정산예정 {due}·월별 파일에서 계산)", P.payout_amount(P.PAYOUT_MP_WEEKLY_1ST, [amt]))
             for due, amt in sorted(weeks.items(), key=lambda kv: str(kv[0]))
             if due is not None and (f.account, due) not in covered]
    lines.append((f, "최종액 30%", P.payout_amount(P.PAYOUT_MP_WEEKLY_FINAL, list(weeks.values()))))
    return lines


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


def write_stats(path, res: StatsResult, contracts: dict | None = None, files: list | None = None,
                amounts: list | None = None, costs: list | None = None) -> Path:
    """집계 엑셀: '상품별 월별'·'계정별 월별'·'계약자 정산'·'지급액 검산'(files 주면)·'쿠팡 지급 내역'(amounts)·
    '로켓그로스 비용'(costs)·'경고' 시트. contracts={계정: 계약금액}(없는 계정은 빈칸).
    amounts = [{'계정','채널','정산일','기간 시작','기간 끝','지급비율','최종지급액', 쿠팡 금액 칸…}],
    costs = [(계정, 정산일, 기간 시작, 기간 끝, 리포트, 시트, 최종비용)]."""
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
    if files is not None:
        _payout_sheet(wb, files, res.warnings)
    if amounts:
        _table_sheet(wb, "쿠팡 지급 내역", amounts, _AMOUNT_FIRST)
    if costs:
        cs2 = wb.create_sheet("로켓그로스 비용")
        cs2.append(["계정", "정산일", "기간 시작", "기간 끝", "리포트", "시트", "최종비용(VAT 포함)"])
        for row in costs:
            cs2.append(list(row))
    wn = wb.create_sheet("경고")
    wn.append(["경고"])
    for w in res.warnings:
        wn.append([w])
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    wb.save(p)
    return p


def _payout_sheet(wb, files: list, warns: list) -> None:
    ws = wb.create_sheet("지급액 검산")
    ws.append(["계정", "채널", "유형", "정산일", "기간 시작", "기간 끝", "정산 합계", "구분", "계산 지급액(예상·화면과 대조)"])
    for f, label, amount in payout_lines(files, warns):
        ws.append([f.account, f.channel, f.kind, f.settle_date.isoformat() if f.settle_date else "",
                   f.period_start.isoformat(), f.period_end.isoformat(), f.settle_total, label, amount])


_AMOUNT_FIRST = ["계정", "채널", "정산일", "기간 시작", "기간 끝", "지급비율", "최종지급액"]


def _table_sheet(wb, title: str, rows: list, first: list) -> None:
    """dict 줄 → 시트. 앞 열 고정 + 나머지 칸(쿠팡 응답 이름 그대로)은 처음 나온 순서로 — 칸을 버리지 않음."""
    cols = list(first)
    for r in rows:
        cols += [k for k in r if k not in cols]
    ws = wb.create_sheet(title)
    ws.append(cols)
    for r in rows:
        ws.append([r.get(c, "") for c in cols])
