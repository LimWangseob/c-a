"""정산 파일 병합 → 계정·상품·월별 정산 집계 + 계약자 정산금액. SSOT=designs/SETTLEMENT_MODULE.md.

소유자 요구(2026-10-06): 윙 + 로켓그로스 정산 파일을 **병합해 상품별 최종 정산금액**을 내고,
**계약자 정산금액 = 계약금액 − 쿠팡이 정산한 금액**. 계약금액은 나중에 입력(없으면 그 칸은 비움 — 0 으로 꾸미지 않음).

집계 규칙:
- 주문 단위 집계는 **주정산 파일만**(윙 최종액 파일은 같은 주문이 다시 들어 있어 이중 집계 → 제외, 함정 1).
- 같은 파일(계정·채널·리포트·기간)이 두 번 있어도 한 번만. 같은 줄(주문·옵션·유형·날짜·금액)이 겹치면 한 번만(경고).
- 월 = 매출인식일 기준(윙=구매확정일, 로켓그로스=매출인식일). 날짜 없는 금액 줄(윙 배송비 등)은 그 파일 정산 기간
  끝의 달로 넣고 **건수를 경고로 남긴다**.
- 상품 = 계정 + 등록상품ID(윙 '상품 ID'·로켓그로스 '등록상품 ID'). 배송비 줄은 '배송비' 묶음.
- 로켓그로스 물류비(비용 리포트 8종: 입출고·배송·보관·바코드·반품회수/재입고·반출·반출배송)는 **상품·월별**로
  더한다(VAT 포함·월=매출인식일) · 재고 손실 보상은 받는 돈(+)·월=발생일·등록상품ID 가 없어 옵션ID 로 상품 찾음.
  광고비·밀크런·쿠팡라이브·이월 차감은 상품 상세가 없어 계정 단위('쿠팡 지급 내역' 시트)에만 있다.
- 실제 지급액·차감 내역은 '쿠팡 지급 내역'(정산현황 금액 그대로) · 비용 리포트 시트별 합은 '로켓그로스 비용' 시트.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import payout as P
from .settlement_files import CH_WING, COMPENSATION, MULTI_PRODUCT, NO_PRODUCT, SettleFile

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
    rg_cost: int = 0                 # 로켓그로스 물류비(VAT 포함·차감할 돈)
    rg_comp: int = 0                 # 재고 손실 보상(받을 돈)
    costs: dict = field(default_factory=dict)   # 비용 종류(시트 이름) → VAT 포함 금액

    @property
    def settle_total(self) -> int:
        return self.wing_settle + self.rg_settle

    @property
    def settle_after_costs(self) -> int:
        return self.settle_total - self.rg_cost + self.rg_comp


@dataclass
class StatsResult:
    products: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def account_months(self) -> dict:
        out: dict = {}
        for p in self.products:
            a = out.setdefault((p.account, p.month), {"wing": 0, "rg": 0, "cost": 0, "comp": 0})
            a["wing"] += p.wing_settle
            a["rg"] += p.rg_settle
            a["cost"] += p.rg_cost
            a["comp"] += p.rg_comp
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


def aggregate(files: list[SettleFile], cost_lines=()) -> StatsResult:
    """정산 파일들 + 로켓그로스 비용 리포트 줄(settlement_files.rg_cost_lines) → 계정·월·상품별 집계
    (정렬: 계정 → 월 → 상품)."""
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
    _add_costs(table, list(cost_lines), files, res.warnings)
    res.products = [table[k] for k in sorted(table)]
    return res


def _option_products(files: list[SettleFile], lines: list) -> dict:
    """(계정, 옵션ID) → 등록상품ID — 정산 파일·비용 리포트 줄에서(재고 손실 보상은 옵션ID 만 있음)."""
    out = {(r.account, r.option_id): r.product_id for f in files for r in f.rows if r.option_id and r.product_id}
    out.update({(c.account, c.option_id): c.product_id for c in lines if c.option_id and c.product_id
                and c.product_id not in (MULTI_PRODUCT, NO_PRODUCT)})
    return out


def _add_costs(table: dict, lines: list, files: list[SettleFile], warns: list) -> None:
    o2p = _option_products(files, lines)
    unmapped, bucket = 0, {}
    for c in lines:
        pid = c.product_id or o2p.get((c.account, c.option_id))
        if not pid:
            pid, unmapped = f"옵션 {c.option_id}", unmapped + 1
        amt = c.ex_vat + c.vat
        if pid in (MULTI_PRODUCT, NO_PRODUCT):
            bucket[pid] = bucket.get(pid, 0) + amt
        p = table.setdefault((c.account, c.month, pid), ProductMonth(c.account, c.month, pid))
        p.product_name = p.product_name or c.product_name
        if c.kind == COMPENSATION:
            p.rg_comp += amt
        else:
            p.rg_cost += amt
        p.costs[c.kind] = p.costs.get(c.kind, 0) + amt
    if unmapped:
        warns.append(f"재고 손실 보상 {unmapped}묶음 — 옵션ID 로 상품을 못 찾아 '옵션 ID' 줄로 따로 집계")
    for k, v in bucket.items():
        warns.append(f"반출 배송 서비스비 {v:,}원(VAT 포함) — 박스에 {k}: 상품별로 나누지 않고 '{k}' 줄로 집계")


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
           "쿠팡 정산금액 합계(부가비용 차감 전)", "로켓그로스 물류비(VAT포함)", "재고 손실 보상",
           "물류비·보상 반영 후(광고비 등 계정 차감 전)"]
_COST_ORDER = ["입출고비", "배송비", "보관비", "바코드 부가 서비스", "반품회수비", "반품재입고비", "반출비",
               "반출 배송 서비스비 리포트"]
_A_HEAD = ["계정", "쿠팡 정산금액 합계(부가비용 차감 전)", "계약금액", "계약자 정산금액(계약금액−쿠팡 정산금액)"]


def write_stats(path, res: StatsResult, contracts: dict | None = None, files: list | None = None,
                amounts: list | None = None, costs: list | None = None, verify: list | None = None) -> Path:
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
                   p.rg_qty, p.rg_sales, p.rg_settle, p.coupon, p.fee, p.settle_total, p.rg_cost, p.rg_comp,
                   p.settle_after_costs])
    am = wb.create_sheet("계정별 월별")
    am.append(["계정", "월(매출인식)", "윙 정산금액", "로켓그로스 정산대상액", "합계(부가비용 차감 전)",
               "로켓그로스 물류비(VAT포함)", "재고 손실 보상", "물류비·보상 반영 후(광고비 등 계정 차감 전)"])
    for (acct, month), v in sorted(res.account_months().items()):
        am.append([acct, month, v["wing"], v["rg"], v["wing"] + v["rg"], v["cost"], v["comp"],
                   v["wing"] + v["rg"] - v["cost"] + v["comp"]])
    _cost_product_sheet(wb, res.products)
    cs = wb.create_sheet("계약자 정산")
    cs.append(_A_HEAD)
    for acct, settled in sorted(res.account_totals().items()):
        c = contracts.get(acct)
        cs.append([acct, settled, c if c is not None else "", contractor_amount(c, settled) if c is not None else ""])
    if files is not None:
        _payout_sheet(wb, files, res.warnings)
    if verify:
        _verify_sheet(wb, verify, res.warnings)
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
    """dict 줄 → 시트. 앞 열 고정 + 나머지 칸(쿠팡 응답 이름 그대로)은 처음 나온 순서로 — 칸을 버리지 않음.
    목록·사전 값(차감 사유·상계 상세)은 글자(JSON)로 펼쳐 넣는다."""
    import json
    cols = list(first)
    for r in rows:
        cols += [k for k in r if k not in cols]
    ws = wb.create_sheet(title)
    ws.append(cols)
    for r in rows:
        ws.append([json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                   for v in (r.get(c, "") for c in cols)])


def _cost_product_sheet(wb, products: list) -> None:
    """'로켓그로스 비용 상품별' — 상품·월마다 비용 종류별(VAT 포함) + 합계 + 재고 손실 보상. 비용 없으면 시트 안 만듦."""
    rows = [p for p in products if p.costs]
    if not rows:
        return
    kinds = [k for k in _COST_ORDER if any(k in p.costs for p in rows)]
    kinds += sorted({k for p in rows for k in p.costs} - set(kinds) - {COMPENSATION})
    ws = wb.create_sheet("로켓그로스 비용 상품별")
    ws.append(["계정", "월(매출인식)", "등록상품ID", "상품명", *kinds, "물류비 합계(VAT포함)", "재고 손실 보상"])
    for p in rows:
        ws.append([p.account, p.month, p.product_id, p.product_name, *[p.costs.get(k, 0) for k in kinds],
                   p.rg_cost, p.rg_comp])


def _verify_sheet(wb, rows: list, warns: list) -> None:
    """'검증' — 쿠팡의 다른 장부와 계정별 대조(settlement_verify). 다름·확인 필요 건수는 경고에도."""
    from .settlement_verify import CHECK, DIFF, HEAD
    ws = wb.create_sheet("검증")
    ws.append(HEAD)
    for r in rows:
        ws.append([r[h] for h in HEAD])
    for verdict in (DIFF, CHECK):
        n = sum(1 for r in rows if r["판정"] == verdict)
        if n:
            warns.append(f"검증 '{verdict}' {n}건 — '검증' 시트에서 계정·대조별 확인")
