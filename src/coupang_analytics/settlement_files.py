"""쿠팡 정산 파일 읽기·검산·개인정보 제거·파일 이름 규칙. SSOT=designs/SETTLEMENT_MODULE.md(정산 파일 배치).

실측(2026-10-06 소유자 샘플·화면 원 단위 대조):
- **윙 정산현황 주문 상세**(`MSF_PAYMENT_REVENUE_DETAIL-*.xlsx`): 시트 'Order Detail Report'·1행 머리글·25칸. 주문마다
  3줄(상품 정보 1줄 + 옵션ID만 다르고 수량·금액이 0인 줄 2개 → 집계 제외). `구매자명` = 개인정보(저장 시 제거).
  정산금액 = 판매액 − 판매자할인쿠폰(A+B) − 판매수수료 + 마이샵수수료할인 (57/57줄). 파일 안에 계정·정산 주 없음.
- **로켓그로스 판매수수료 리포트**(`{vendorId}-CATEGORY_TR-*.xlsx`): 시트 '주문내역, 판매수수료'·2행 머리글·28칸.
  정산대상액 = 판매액(A*B) − 판매자할인쿠폰 − 판매수수료 − 판매수수료 VAT (118/118줄·2025-11~12 파일 4,700여 줄 —
  쿠팡지원할인(C)은 쿠팡 부담이라 정산대상액에서 빼지 않음·매출금액(A*B−C) 기준이면 C 있는 줄만 어긋남, 실측 2026-10-06). `정산주기(종료일)` 있음·계정명 없음.
→ 계정·기간은 **요청 기록(파일 이름)** 이 붙인다. 숫자·ID 변환 실패 = SettlementParseError(조용히 0 금지),
  검산 위반 줄 = 경고(쿠팡 형식 변경 감지용·중단 아님). 이름을 붙일 수 없는 금액 줄은 버리지 않고 경고와 함께 남긴다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .settlement_parse import SettlementParseError, parse_date, parse_id, parse_int

CH_WING = "윙"
CH_RG = "로켓그로스"
PII_COLUMNS = ("구매자명",)

_WING_COLS = {"order_id": "주문번호", "product_id": "상품 ID", "product_name": "상품명", "option_id": "옵션 ID",
              "option_name": "옵션명", "unit_price": "판매가", "qty": "판매수량", "refund_qty": "환불수량",
              "sales": "판매액", "coupon": "판매자 할인쿠폰(A+B)", "fee": "판매수수료", "myshop": "마이샵수수료할인",
              "settle": "정산금액", "recognized": "구매확정일", "kind": "구매확정(출고)유형",
              "due": "정산예정일"}
_RG_COLS = {"order_id": "주문ID", "product_id": "등록상품 ID", "product_name": "등록상품명", "option_id": "옵션ID",
            "option_name": "옵션명", "unit_price": "판매가(A)", "qty": "판매수량(B)", "gross": "판매액(A*B)",
            "sales": "매출금액(A*B-C)", "coupon": "판매자할인쿠폰(D+E)", "fee": "판매수수료", "fee_vat": "판매수수료 VAT",
            "settle": "정산대상액", "recognized": "매출인식일", "kind": "거래유형", "cycle_end": "정산주기(종료일)"}
_SHIP_MARK = re.compile(r"<[^<>]{1,20}배송료>")   # 실측: 주문마다 <기본배송료>·<추가배송료> 줄(대개 0원)
_MONEY = ("unit_price", "qty", "refund_qty", "gross", "sales", "coupon", "fee", "fee_vat", "myshop", "settle")


@dataclass
class SettleRow:
    """정산 파일 1줄(윙·로켓그로스 공통). 금액은 원 단위 정수. fee = 수수료(로켓그로스는 VAT 포함 합)."""
    channel: str
    account: str
    period_start: date
    period_end: date
    order_id: str
    product_id: str
    option_id: str
    product_name: str
    option_name: str
    qty: int
    sales: int
    coupon: int
    fee: int
    settle: int
    recognized: date | None
    kind: str
    due: date | None = None          # 윙 정산예정일(주정산 묶음 — 최종액 30% 계산에 씀)·로켓그로스는 없음
    gross: int = 0                   # 로켓그로스 판매액(A×B, 쿠팡지원할인 전) — 로켓그로스 부가세 대조용·윙은 0


@dataclass
class SettleFile:
    channel: str
    account: str
    period_start: date
    period_end: date
    rows: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    dropped_zero: int = 0
    kind: str = ""                   # 파일 이름의 유형(주정산·최종액 등) — load_settle_file 이 채움
    report: str = ""
    settle_date: date | None = None

    @property
    def settle_total(self) -> int:
        return sum(r.settle for r in self.rows)


# ── 공통 ──────────────────────────────────────────────────────────
def _norm(h) -> str:
    return "".join(str(h or "").split())


def _header(rows: list, must: tuple, where: str) -> tuple[int, dict]:
    """머리글 행(상단 5행 안) 찾기 → (행 번호, {머리글: 열}). 필수 머리글 누락 = SettlementParseError."""
    for i, row in enumerate(rows[:5]):
        cells = [_norm(c) for c in row]
        if all(_norm(m) in cells for m in must[:2]):
            missing = [m for m in must if _norm(m) not in cells]
            if missing:
                raise SettlementParseError(f"{where} 필수 머리글 누락 {len(missing)}개: {', '.join(missing)}")
            return i, {m: cells.index(_norm(m)) for m in must}
    raise SettlementParseError(f"{where} 머리글({must[0]}·{must[1]})을 상단 5행에서 찾지 못함")


def _values(raw: list, cols: dict, idx: dict, r: int, where: str) -> dict:
    oid = cols.get("option_id")
    ship = bool(oid and idx[oid] < len(raw) and _SHIP_MARK.fullmatch(str(raw[idx[oid]] or "").strip()))
    return {f: _cell(f, raw[idx[h]] if idx[h] < len(raw) else None, ship, f"{where} {r}행 '{h}'")
            for f, h in cols.items()}


def _cell(f: str, v, ship: bool, where: str):
    blank = not str(v or "").strip()
    if f in _MONEY:
        return 0 if ship and blank else parse_int(v, where)   # 배송비 줄의 빈 금액칸 = 0(실측 2025-11~2026-01 파일)
    if f == "option_id" and _SHIP_MARK.fullmatch(str(v or "").strip()):
        return str(v).strip()                       # 윙 배송비 줄 표시값(<기본배송료>·<추가배송료>) — ID 아님
    if f in ("option_id", "product_id", "order_id"):
        return "" if blank else parse_id(v, where)
    if f in ("recognized", "cycle_end", "due"):
        return None if blank else parse_date(v, where)
    return str(v or "").strip()


# ── 윙 정산현황 주문 상세 ─────────────────────────────────────────
def parse_wing_detail(rows: list, *, account: str, period_start: date, period_end: date) -> SettleFile:
    """윙 주문 상세 격자 → SettleFile. 0원 보조줄(상품명 없음·수량·금액 0) 제외, 구매자명은 읽지 않음."""
    out = SettleFile(CH_WING, account, period_start, period_end)
    hrow, idx = _header(rows, tuple(_WING_COLS.values()), "윙 정산 파일")
    for r, raw in enumerate(rows[hrow + 1:], start=hrow + 2):
        if not any(str(c or "").strip() for c in raw):
            continue
        v = _values(list(raw), _WING_COLS, idx, r, "윙 정산 파일")
        if not v["product_name"] and not any(v[k] for k in ("qty", "sales", "fee", "settle")):
            out.dropped_zero += 1
            continue
        _check_wing(v, r, out)
        out.rows.append(SettleRow(CH_WING, account, period_start, period_end, v["order_id"], v["product_id"],
                                  v["option_id"], v["product_name"], v["option_name"], v["qty"] - v["refund_qty"],
                                  v["sales"], v["coupon"], v["fee"], v["settle"], v["recognized"], v["kind"],
                                  v["due"]))
    return out


def _check_wing(v: dict, r: int, out: SettleFile) -> None:
    if v["settle"] != v["sales"] - v["coupon"] - v["fee"] + v["myshop"]:
        out.warnings.append(f"윙 {r}행 정산금액 {v['settle']} ≠ 판매액−쿠폰−수수료+마이샵할인")
    ship = bool(_SHIP_MARK.fullmatch(v["option_id"]))
    if v["sales"] != v["unit_price"] * v["qty"] and not ship:   # 배송비 줄은 판매가·수량 0 에 금액만(실측 6,000)
        out.warnings.append(f"윙 {r}행 판매액 {v['sales']} ≠ 판매가×판매수량")
    if not v["product_name"] and not ship:
        out.warnings.append(f"윙 {r}행 상품명 없는 금액 줄(옵션 {v['option_id']}) — 집계에 포함")
    d = v["recognized"]
    if d and not (out.period_start <= d <= out.period_end):
        out.warnings.append(f"윙 {r}행 구매확정일 {d} 가 요청 기간 {out.period_start}~{out.period_end} 밖")


# ── 로켓그로스 판매수수료 리포트 ──────────────────────────────────
def parse_rg_fee(rows: list, *, account: str, period_start: date, period_end: date) -> SettleFile:
    """로켓그로스 판매수수료 리포트 격자 → SettleFile. 파일의 정산주기(종료일)가 요청 기간 끝과 다르면 오류(엉뚱한 파일)."""
    out = SettleFile(CH_RG, account, period_start, period_end)
    hrow, idx = _header(rows, ("정산유형", "옵션ID", *[h for h in _RG_COLS.values() if h != "옵션ID"]),
                        "로켓그로스 정산 파일")
    for r, raw in enumerate(rows[hrow + 1:], start=hrow + 2):
        if not any(str(c or "").strip() for c in raw):
            continue
        v = _values(list(raw), _RG_COLS, idx, r, "로켓그로스 정산 파일")
        if v["cycle_end"] != period_end:
            raise SettlementParseError(f"로켓그로스 {r}행 정산주기(종료일) {v['cycle_end']} ≠ 요청 기간 끝 {period_end} "
                                       "— 다른 기간 파일로 보임(이름 붙이기 중단)")
        if v["settle"] != v["gross"] - v["coupon"] - v["fee"] - v["fee_vat"]:
            out.warnings.append(f"로켓그로스 {r}행 정산대상액 {v['settle']} ≠ 판매액−쿠폰−수수료−VAT")
        out.rows.append(SettleRow(CH_RG, account, period_start, period_end, v["order_id"], v["product_id"],
                                  v["option_id"], v["product_name"], v["option_name"], v["qty"], v["sales"],
                                  v["coupon"], v["fee"] + v["fee_vat"], v["settle"], v["recognized"], v["kind"],
                                  gross=v["gross"]))
    return out


# ── xlsx 입출력 ───────────────────────────────────────────────────
def read_grid(path) -> list:
    import openpyxl
    wb = openpyxl.load_workbook(Path(path), read_only=True, data_only=True)
    try:
        return [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    finally:
        wb.close()


def scrub_pii(src, dst, columns=PII_COLUMNS) -> int:
    """정산 파일에서 개인정보 열(구매자명 등)을 **지운 사본**을 dst 에 저장. 지운 열 수 반환(없으면 0).
    머리글을 상단 5행에서 못 찾으면 SettlementParseError(엉뚱한 파일을 그대로 저장하지 않음)."""
    import openpyxl
    wb = openpyxl.load_workbook(Path(src))
    ws = wb.worksheets[0]
    targets = {_norm(c) for c in columns}
    for hr in range(1, 6):
        cells = [_norm(c.value) for c in ws[hr]]
        if sum(1 for c in cells if c) >= 5:
            cols = [i + 1 for i, c in enumerate(cells) if c in targets]
            for c in reversed(cols):
                ws.delete_cols(c)
            Path(dst).parent.mkdir(parents=True, exist_ok=True)
            wb.save(Path(dst))
            return len(cols)
    raise SettlementParseError(f"{Path(src).name}: 머리글을 찾지 못해 개인정보 제거 불가 — 저장 중단")


# ── 로켓그로스 비용 리포트(보관비·입출고/배송비 등) ────────────────
def read_sheets(path) -> dict:
    """모든 시트 → {시트명: 격자}. 비용 리포트는 시트가 여럿(입출고비·배송비 등)."""
    import openpyxl
    wb = openpyxl.load_workbook(Path(path), read_only=True, data_only=True)
    try:
        return {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets}
    finally:
        wb.close()


def assert_no_pii(sheets: dict, columns=PII_COLUMNS) -> None:
    """상단 10행 어디에도 개인정보 머리글이 없어야 함 — 있으면 저장 중단(비용 리포트는 지우는 규칙이 없음)."""
    targets = {_norm(c) for c in columns}
    for name, rows in sheets.items():
        for row in rows[:10]:
            hit = targets & {_norm(c) for c in row}
            if hit:
                raise SettlementParseError(f"비용 리포트 '{name}' 시트에 개인정보 칸 {sorted(hit)} — 저장 중단")


_QTY_NOTICE = _norm("반출비 청구 제외 수량(B)")


def rg_cost_totals(sheets: dict, period_end: date) -> dict:
    """비용 리포트 → {시트명: 최종비용(VAT 포함)}. 실측 모양 2가지(2026-10-06):
    ① 4행 요약 [정산주기(종료일), 합계, 세액, 최종비용] — 보관비·입출고비·배송비·바코드·반품회수·재입고
    ② 건별 목록(머리글에 '보상 금액') — 재고 손실 보상: 그 열 합.
    ③ 금액 없는 수량 안내 시트(머리글 '반출비 청구 제외 수량(B)') — 반출비 리포트의 '자동반출(고객반품) - 쿠팡귀책'
       (실측 2026-10-08 운용 PC 16개: 반출비 시트 최종비용이 쿠팡 차감액과 16/16 일치, 이 시트는 금액 칸 없음) → 제외.
    그 밖의 모양은 오류. 정산주기(종료일)가 요청 기간 끝과 다르면 오류(엉뚱한 주 파일)."""
    out = {}
    for name, rows in sheets.items():
        if any(_QTY_NOTICE in {_norm(c) for c in r} for r in rows[:20]):
            continue
        head = next((i for i, r in enumerate(rows[:5]) if "보상금액" in {_norm(c) for c in r}), None)
        out[name] = (_summary_cost(name, rows, period_end) if head is None
                     else _listed_cost(name, rows, head, period_end))
    return out


def _listed_cost(name: str, rows: list, head: int, period_end: date) -> int:
    cells = [_norm(c) for c in rows[head]]
    ci, ce = cells.index("보상금액"), cells.index("정산주기(종료일)")
    data = [r for r in rows[head + 1:] if ci < len(r) and str(r[ci] or "").strip()]
    if any(parse_date(r[ce], f"{name} 정산주기") != period_end for r in data):
        raise SettlementParseError(f"비용 리포트 '{name}': 정산주기(종료일)가 {period_end} 아닌 줄 있음")
    return sum(parse_int(r[ci], f"{name} 보상 금액") for r in data)


def _summary_cost(name: str, rows: list, period_end: date) -> int:
    if len(rows) < 4 or _norm(rows[2][0] if rows[2] else "") != "정산주기(종료일)":
        raise SettlementParseError(f"비용 리포트 '{name}' 시트 모양이 다름(3행 '정산주기(종료일)' 요약 머리글 없음)")
    end = parse_date(rows[3][0], f"{name} 요약 정산주기")
    if end != period_end:
        raise SettlementParseError(f"비용 리포트 '{name}' 정산주기(종료일) {end} ≠ 요청 기간 끝 {period_end}")
    return parse_int(rows[3][3], f"{name} 최종비용")


# ── 로켓그로스 비용 리포트 → 상품별 ────────────────────────────────
_COST_AMOUNT = ("최종비용(A-B-C)", "최종비용", "할인적용가(A-B)")   # 하위 머리글, 앞에 있는 것 우선(실측 8종)
_COST_PRODUCT = ("등록상품 ID", "대표 등록상품 ID")                 # 반출 배송 서비스비=박스 단위라 '대표' 상품
_COST_NAME = ("등록상품명", "대표 등록상품명")
COMPENSATION = "재고 손실 보상"
MULTI_PRODUCT = "(여러 상품)"          # 반출 배송 박스에 서로 다른 상품이 함께 — 나누는 기준이 없어 묶음으로 둠
NO_PRODUCT = "(상품 미표기)"           # 대표 등록상품 ID 가 '-'


def _cost_pid(v, where: str) -> str:
    """상품 ID 칸 → ID. 반출 배송 서비스비는 박스 단위라 'a,b'·'-' 가 있음(실측 95줄 중 10줄):
    같은 ID 반복=그 상품, 서로 다른 ID=MULTI_PRODUCT, '-'=NO_PRODUCT(추측 배분 안 함·집계 경고로 남김)."""
    parts = [x.strip() for x in str(v or "").split(",") if x.strip()]
    if not parts or parts == ["-"]:
        return NO_PRODUCT
    ids = {parse_id(x, where) for x in parts}
    return ids.pop() if len(ids) == 1 else MULTI_PRODUCT


@dataclass
class CostLine:
    """비용 리포트의 상품·월 묶음 1줄. ex_vat=VAT 별도(상세 줄 합·정확), vat=시트 세액을 금액 비율로 나눈 몫
    (끝수는 큰 몫부터 1원씩 → 상품별 합 = 시트 세액). 재고 손실 보상은 받는 돈(+)이라 kind 로 구분·vat 0."""
    account: str
    month: str
    product_id: str                  # 재고 손실 보상은 파일에 없음 → '' (집계에서 옵션ID 로 찾음)
    option_id: str
    product_name: str
    kind: str                        # 시트 이름(입출고비·배송비·보관비…·재고 손실 보상)
    ex_vat: int
    vat: int = 0


def _split(total: int, parts: list) -> list[int]:
    """total 을 parts 비율로 나눈 정수(합=total). 끝수는 소수 부분이 큰 순서로 1원씩. parts 합이 0 이면 전부 0."""
    base = sum(parts)
    if not total:
        return [0] * len(parts)
    if not base:
        raise SettlementParseError(f"나눌 금액 합이 0 인데 나눌 값 {total} 이 있음 — 배분 불가")
    raw = [total * x / base for x in parts]
    out = [int(r // 1) for r in raw]
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - out[i], reverse=True)[:total - sum(out)]:
        out[i] += 1
    return out


def _col(cells: list, names: tuple, where: str) -> int:
    for n in names:
        if _norm(n) in cells:
            return cells.index(_norm(n))
    raise SettlementParseError(f"{where}: 머리글 {names} 없음")


def _summary_lines(name: str, rows: list, account: str, period_end: date) -> list[CostLine]:
    """요약형 시트(4행 요약 + 7·8행 2줄 머리글 + 상세 줄) → 상품·월 묶음. 상세 합 ≠ 요약 합계면 오류."""
    hi = next((i for i, r in enumerate(rows[:15]) if r and _norm(r[0]) == "정산유형"), None)
    if hi is None:
        raise SettlementParseError(f"비용 리포트 '{name}': 상세 머리글(정산유형) 없음")
    top, sub = [_norm(c) for c in rows[hi]], [_norm(c) for c in rows[hi + 1]]
    ai, pi = _col(sub, _COST_AMOUNT, name), _col(top, _COST_PRODUCT, name)
    ni, mi, ci = _col(top, _COST_NAME, name), _col(top, ("매출인식일",), name), _col(top, ("정산주기(종료일)",), name)
    oi = top.index("옵션ID") if "옵션ID" in top else None
    groups: dict = {}
    for r in rows[hi + 2:]:
        if ai >= len(r) or not str(r[ai] or "").strip():
            continue
        if parse_date(r[ci], f"{name} 정산주기") != period_end:
            raise SettlementParseError(f"비용 리포트 '{name}': 정산주기(종료일)가 {period_end} 아닌 줄")
        key = (_cost_pid(r[pi], f"{name} 상품ID"), f"{parse_date(r[mi], f'{name} 매출인식일'):%Y-%m}")
        g = groups.setdefault(key, {"amt": 0, "name": str(r[ni] or "").strip(),
                                    "opt": parse_id(r[oi], f"{name} 옵션ID") if oi is not None else ""})
        g["amt"] += parse_int(r[ai], f"{name} 금액")
    total, tax = parse_int(rows[3][1], f"{name} 합계"), parse_int(rows[3][2], f"{name} 세액")
    if sum(g["amt"] for g in groups.values()) != total:
        raise SettlementParseError(f"비용 리포트 '{name}': 상세 합 {sum(g['amt'] for g in groups.values())} ≠ 요약 합계 {total}")
    keys = sorted(groups)
    vats = _split(tax, [groups[k]["amt"] for k in keys])
    return [CostLine(account, m, pid, groups[(pid, m)]["opt"], groups[(pid, m)]["name"], name, groups[(pid, m)]["amt"], v)
            for (pid, m), v in zip(keys, vats)]


def _compensation_lines(name: str, rows: list, account: str, period_end: date) -> list[CostLine]:
    """재고 손실 보상(건별 목록) → 옵션·월 묶음(등록상품ID 없음). 월=발생일."""
    hi = next(i for i, r in enumerate(rows[:5]) if "보상금액" in {_norm(c) for c in r})
    top = [_norm(c) for c in rows[hi]]
    ai, oi, ni, di = (top.index("보상금액"), _col(top, ("옵션ID",), name), _col(top, ("등록상품명",), name),
                      _col(top, ("발생일",), name))
    _listed_cost(name, rows, hi, period_end)                     # 정산주기 대조(다른 주 줄 있으면 오류)
    groups: dict = {}
    for r in rows[hi + 1:]:
        if ai < len(r) and str(r[ai] or "").strip():
            key = (parse_id(r[oi], f"{name} 옵션ID"), f"{parse_date(r[di], f'{name} 발생일'):%Y-%m}")
            g = groups.setdefault(key, {"amt": 0, "name": str(r[ni] or "").strip()})
            g["amt"] += parse_int(r[ai], f"{name} 보상 금액")
    return [CostLine(account, m, "", opt, g["name"], COMPENSATION, g["amt"]) for (opt, m), g in sorted(groups.items())]


def rg_cost_lines(sheets: dict, account: str, period_end: date) -> list[CostLine]:
    """비용 리포트 전체 시트 → 상품·월별 줄(수량 안내 시트 제외). 시트별 합은 rg_cost_totals 와 같다."""
    out: list[CostLine] = []
    for name, rows in sheets.items():
        if any(_QTY_NOTICE in {_norm(c) for c in r} for r in rows[:20]):
            continue
        listed = any("보상금액" in {_norm(c) for c in r} for r in rows[:5])
        out += (_compensation_lines if listed else _summary_lines)(name, rows, account, period_end)
    return out


# ── 파일 이름 규칙 ────────────────────────────────────────────────
_BAD = re.compile(r'[\\/:*?"<>|_\s]+')
_NAME = re.compile(r"^(?P<account>.+)_(?P<settle>\d{8})_(?P<channel>[^_]+)_(?P<kind>[^_]+)_(?P<report>[^_]+)_"
                   r"(?P<ps>\d{8})-(?P<pe>\d{8})\.xlsx$")


def _token(s: str, what: str) -> str:
    t = _BAD.sub("-", str(s).strip()).strip("-")
    if not t:
        raise ValueError(f"파일 이름의 {what} 이(가) 비었음")
    return t


def settle_file_name(account: str, settle_date: date, channel: str, kind: str, report: str,
                     period_start: date, period_end: date) -> str:
    """`{계정명}_{정산일}_{채널}_{유형}_{리포트}_{기간시작}-{기간끝}.xlsx` (소유자 요구: 계정명·정산연월일 포함).
    계정명·유형 등의 '_'·공백·금지문자는 '-' 로 바꿔 다시 읽을 수 있게 한다."""
    return (f"{_token(account, '계정명')}_{settle_date:%Y%m%d}_{_token(channel, '채널')}_{_token(kind, '유형')}_"
            f"{_token(report, '리포트')}_{period_start:%Y%m%d}-{period_end:%Y%m%d}.xlsx")


def parse_file_name(name: str) -> dict:
    """settle_file_name 의 역. 규칙에 안 맞으면 ValueError."""
    m = _NAME.match(Path(name).name)
    if not m:
        raise ValueError(f"정산 파일 이름 규칙에 맞지 않음: {name}")
    d = m.groupdict()

    def to_d(s: str) -> date:
        return date(int(s[:4]), int(s[4:6]), int(s[6:]))
    return {"account": d["account"], "settle_date": to_d(d["settle"]), "channel": d["channel"], "kind": d["kind"],
            "report": d["report"], "period_start": to_d(d["ps"]), "period_end": to_d(d["pe"])}


def load_settle_file(path) -> SettleFile:
    """이름 규칙대로 저장된 파일 → 이름에서 계정·기간을 얻어 채널별로 파싱."""
    meta = parse_file_name(Path(path).name)
    rows = read_grid(path)
    kw = {"account": meta["account"], "period_start": meta["period_start"], "period_end": meta["period_end"]}
    if meta["channel"] == CH_WING:
        out = parse_wing_detail(rows, **kw)
    elif meta["channel"] == CH_RG and meta["report"] == "판매수수료":
        out = parse_rg_fee(rows, **kw)
    else:
        raise SettlementParseError(f"{Path(path).name}: 아직 읽는 방법이 없는 정산 파일({meta['channel']}·{meta['report']})")
    out.kind, out.report, out.settle_date = meta["kind"], meta["report"], meta["settle_date"]
    return out
