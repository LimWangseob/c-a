"""회사보유재고 — 재고현황 구글시트(창고별) → 관리대장 '회사보유재고' 열 역기록. SSOT=designs/LEDGER_REGISTRY.md.

재고는 두 가지: 로켓그로스 재고(쿠팡 재고현황 API → '그로스 재고' 열, input_list.write_ledger_inventory)와
**판매자배송용 회사 자체 재고**(이 모듈). 소유자 결정(2026-09-29):
- 읽을 탭 = 설정에 넣은 **링크의 gid 탭**(gid 없는 링크면 구글시트가 여는 첫 탭).
- 대장 표기 = **'창고 , 수량개'**(예 '김포2 , 150개'). 여러 창고면 ' / ' 로 이어 씀(파일 순서), 같은 창고가 여러
  줄이면 그 창고 안에서 합산. '-' = 0, 음수는 그대로 쓰고 경고.
- 매칭 = **동일 상품명**(띄어쓰기·대소문자 무시). 관리대장 상품명이 여러 줄이면 첫 줄(대장 규칙).
  → D-072(2026-10-16): 괄호 앞/안·색상별 줄·모델번호·AI 단계 추가(`company_stock_match`).
- 미매칭 줄은 기존값 보존(공란으로 덮지 않음). 같은 상품이 여러 계정에 있으면 모두 같은 값(회사 전체 재고).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from openpyxl.utils import get_column_letter

from . import config
from .input_list import (_REQUIRED, _cell, _find_header_row, _is_real_product_name, _norm, _one_line,
                         account_labels)

STOCK_COL = "회사보유재고"            # 관리대장 대상 열(헤더 이름으로 찾음)
_HEADER_SCAN = 15
_GID = re.compile(r"[#?&]gid=(\d+)")


@dataclass
class StockResult:
    matched: int = 0                               # 값을 쓴 대장 상품 줄 수
    changed: int = 0                               # 그중 값이 바뀐 줄 수
    unmatched: list = field(default_factory=list)  # (사업자명, 상품명) — 재고현황에 없음
    how: list = field(default_factory=list)        # (사업자명, 상품명, 근거) — 상품명 일치가 아닌 매칭(로그용)
    warnings: list = field(default_factory=list)
    stock_sheet: str = ""
    items: int = 0                                 # 재고현황 상품 수(창고 합산 후)


def name_key(name) -> str:
    """동일 상품명 판정 키 — 띄어쓰기·대소문자 무시(소유자 2026-09-29)."""
    return "".join(str(name or "").split()).lower()


def parse_qty(v) -> int | None:
    """'  5,670 ' → 5670 · '-' → 0 · '- 1' → -1 · 빈칸·글자 → None(합산 제외, 호출부가 경고)."""
    s = "".join(str(v if v is not None else "").split()).replace(",", "")
    if s == "-":
        return 0
    return int(s) if re.fullmatch(r"-?\d+", s) else None


def resolve_tab(client, url: str) -> str:
    """링크의 gid 탭 이름. gid 없는 링크면 첫 탭(구글시트가 그 링크로 여는 탭). 없는 gid 면 ValueError."""
    titles = client.sheet_titles()
    m = _GID.search(url or "")
    if not m:
        return titles[0]
    gid = int(m.group(1))
    for t in titles:
        if client.sheet_id(t) == gid:
            return t
    raise ValueError(f"재고현황 링크의 탭(gid={gid})이 파일에 없음 — 링크를 다시 복사해 주세요")


def _stock_columns(rows: list) -> tuple[int, int, int, int]:
    """(헤더 행, 창고 열, 상품명 열, 현재고 열) — 헤더 이름으로 찾음(탭마다 열 위치가 다름)."""
    for r, row in enumerate(rows[:_HEADER_SCAN]):
        cells = ["".join(str(c).split()) for c in row]
        if "상품명" in cells and "창고" in cells:
            qty = next((i for i, c in enumerate(cells) if "현재고" in c), None)
            if qty is not None:
                return r, cells.index("창고"), cells.index("상품명"), qty
    raise ValueError(f"재고현황 상단 {_HEADER_SCAN}행에서 '창고'·'상품명'·'현재고' 헤더를 찾지 못함")


def stock_text(by_wh: dict) -> str:
    """{창고: 수량} → '김포2 , 150개' / 여러 창고 '김포1 , 2,360개 / 검단 , 24개'(소유자 2026-09-29 표기)."""
    return " / ".join(f"{wh} , {q:,}개" for wh, q in by_wh.items())


def read_stock(rows: list) -> tuple[dict, list]:
    """재고현황 값 격자 → ({상품명키: (표시명, {창고: 수량})}, 경고). 숫자 아닌 수량 줄은 제외+경고."""
    hrow, i_wh, i_name, i_qty = _stock_columns(rows)
    stock: dict[str, tuple[str, dict]] = {}
    warnings: list[str] = []
    for r, row in enumerate(rows[hrow + 1:], start=hrow + 2):
        name = " ".join(str(_cell(row, i_name) or "").split())
        if not name:
            continue
        q = parse_qty(_cell(row, i_qty))
        wh = " ".join(str(_cell(row, i_wh) or "").split())
        if q is None or not wh:
            warnings.append(f"재고현황 {r}행 '{name}' 창고 '{wh}'·수량 '{_cell(row, i_qty)}' 확인 필요 — 제외")
            continue
        by_wh = stock.setdefault(name_key(name), (name, {}))[1]
        by_wh[wh] = by_wh.get(wh, 0) + q
    for shown, by_wh in stock.values():
        if any(q < 0 for q in by_wh.values()):
            warnings.append(f"재고현황 '{shown}' 음수 재고({stock_text(by_wh)}) — 그대로 기록, 재고현황 확인 필요")
    return stock, warnings


def _ledger_rows(values: list) -> tuple[int, int, list]:
    """관리대장 → (헤더 행, 회사보유재고 열, [(행 0-based, 사업자명, 상품명, 계정ID)]). 헤더·열 없으면 ValueError."""
    header, hrow = _find_header_row(values, lambda h: all(n in h for n in _REQUIRED))
    if hrow < 0:
        raise ValueError("관리대장 헤더(사업자명·계정아이디·상품명)를 찾지 못함")
    nz = ["".join(str(h).split()) for h in header]
    col = next((i for i, h in enumerate(nz) if h.startswith(STOCK_COL)), None)   # '회사보유재고 (10.20기준)'·(자동갱신 MM.DD) 도
    if col is None:
        raise ValueError(f"관리대장에 '{STOCK_COL}' 열이 없음")
    i_biz, i_acct, i_prod = (header.index(c) for c in
                             (config.IN_COL_BUSINESS, config.IN_COL_ACCOUNT_ID, config.IN_COL_PRODUCT))
    out, biz, cur = [], "", ""
    labels = account_labels(values)                    # 파싱과 같은 계정 라벨(사업자명 빈 계정=대표자명·로그 표기용)
    for r in range(hrow + 1, len(values)):
        row = values[r]
        acct = _norm(_cell(row, i_acct))
        if acct:
            biz = labels.get(acct) or _one_line(_cell(row, i_biz)) or acct
            cur = acct
        prod = _norm(_cell(row, i_prod)).split("\n")[0].strip()
        if prod and _is_real_product_name(prod):
            out.append((r, biz, prod, cur))
    return hrow, col, out


def apply_to_workbook(wb, stock: dict, cache: dict | None = None, title_of=None) -> int:
    """재고현황 값(`read_stock` 결과)을 워크북 상품에 매칭(D-072 규칙 1~3 + 저장된 AI 결과)해 회사보유재고로 주입.

    계정목록(엑셀·구글시트) 5열 표기용(계정목록 렌더 전에 호출). 매칭 이름 = 등록명(있으면·대장 원본명).
    미매칭·재고현황에 없는 상품은 주입 안 함(계정목록에서 공란). 값 = 관리대장 역기록과 동일한 표기. AI 는 부르지 않음
    (관리대장 역기록이 묻고 저장한 결과만 사용)."""
    from . import company_stock_match as M
    idx, n = M.build_index(stock), 0
    for biz in wb.account_sheets():
        aids = wb.account_ids_of(biz)
        for prod in wb.products_of(biz):
            name = wb.registered_name(biz, prod) or prod
            title = next((t for t in ((title_of or (lambda a, p: ""))(a, name) for a in aids) if t), "")
            keys, _how = M.match_rules(stock, idx, name, title)
            if not keys and cache is not None:
                keys = (M.from_cache(cache, stock, name, title) or ([], ""))[0]
            if keys:
                wb.set_company_stock(biz, prod, M.text_of(stock, keys, stock_text))
                n += 1
    return n


def _match_rows(prods: list, stock: dict, title_of, ask, cache: dict, log) -> dict:
    """{행: ([재고현황 키], 근거)} — 규칙 1~3 → 저장된 AI 결과 → AI(남은 것만 한 번에·D-072)."""
    from . import company_stock_match as M
    idx, found, todo = M.build_index(stock), {}, []
    for r, _biz, prod, aid in prods:
        title = (title_of or (lambda a, p: ""))(aid, prod)
        keys, how = M.match_rules(stock, idx, prod, title)
        if not keys:
            cached = M.from_cache(cache, stock, prod, title)
            if cached is None:
                todo.append((r, prod, title))
                continue
            keys, how = cached
        if keys:
            found[r] = (keys, how)
    found.update(M.ask_ai(ask, todo, stock, idx, cache, log))
    return found


def write_company_stock(client, stock: dict, *, dry_run: bool = False,
                        sheet: str = "셀독리스트", title_of=None, ask=None, cache: dict | None = None,
                        log=None) -> StockResult:
    """관리대장 '회사보유재고' 열에 재고현황 '창고 , 수량개'를 기록(매칭 줄만·미매칭은 기존값 보존).

    다른 열은 건드리지 않는다(이 열의 데이터 구간만 한 번에 씀). 값이 바뀌는 줄이 없거나 dry_run 이면 쓰지 않음.
    title_of(계정ID, 대장명) = ① 매칭된 쿠팡 상품명(모델번호 단계) · ask = AI 호출 · cache = AI 결과 저장소(D-072)."""
    from . import company_stock_match as M
    values, _ = client.read_grid(sheet)
    hrow, col, prods = _ledger_rows(values)
    res = StockResult()
    col_out = [[_cell(values[r], col) if _cell(values[r], col) is not None else ""]
               for r in range(hrow + 1, len(values))]
    found = _match_rows(prods, stock, title_of, ask, {} if cache is None else cache, log or (lambda m: None))
    for r, biz, prod, _aid in prods:
        if r not in found:
            res.unmatched.append((biz, prod))
            continue
        keys, how = found[r]
        if how != "상품명 일치":
            res.how.append((biz, prod, how))
        res.matched += 1
        text = M.text_of(stock, keys, stock_text)
        if str(col_out[r - hrow - 1][0]).strip() != text:
            res.changed += 1
            col_out[r - hrow - 1] = [text]
    if res.changed and not dry_run:
        client.write_values(sheet, col_out, start=f"{get_column_letter(col + 1)}{hrow + 2}")
    head = f"{STOCK_COL} (자동갱신 {datetime.now():%m.%d})"     # 그로스 재고 열처럼 갱신일 표기(소유자 2026-10-21)
    if not dry_run and str(_cell(values[hrow], col) or "").strip() != head:
        client.write_values(sheet, [[head]], start=f"{get_column_letter(col + 1)}{hrow + 1}")
    return res


def run_company_stock(stock_url: str, input_url: str, *, dry_run: bool = False, on_log=None,
                      stock_client=None, ledger_client=None, title_of=None, ask=None,
                      out_dir: str | None = None) -> StockResult:
    """재고현황(stock_url) → 관리대장(input_url) '회사보유재고' 역기록 1회. UI 버튼·야간 배치 공용 진입점.

    실패(링크·권한·헤더 없음)는 예외로 올린다(폴백 없음) — 호출부가 비치명 처리(로그). 클라이언트는 테스트 주입용."""
    log = on_log or (lambda m: None)
    if stock_client is None or ledger_client is None:
        from .gsheet_api import GSheetClient                 # 지연 import(구글 라이브러리)
        stock_client = stock_client or GSheetClient(stock_url, on_log=log)
        ledger_client = ledger_client or GSheetClient(input_url, on_log=log)
    tab = resolve_tab(stock_client, stock_url)
    stock, warnings = read_stock(stock_client.read_values(tab))
    from . import company_stock_match as M
    cache = M.load_cache(out_dir) if out_dir else {}
    res = write_company_stock(ledger_client, stock, dry_run=dry_run, title_of=title_of, ask=ask, cache=cache, log=log)
    if out_dir and not dry_run:
        M.save_cache(cache, out_dir)
    res.stock_sheet, res.items, res.warnings = tab, len(stock), warnings
    for w in warnings[:30]:
        log(f"  [회사재고] ⚠ {w}")
    for biz, prod, how in res.how:
        log(f"  [회사재고] 매칭 — {biz} / {prod[:40]} ← {how}")
    for biz, prod in res.unmatched:
        log(f"  [회사재고] 미매칭(기존값 유지) — {biz or '(사업자명 없음)'} / {prod}")
    log(f"== [회사재고] {'미리보기(저장 안 함) ' if dry_run else ''}재고현황 '{tab}' {len(stock)}품목 → "
        f"관리대장 '{STOCK_COL}' 매칭 {res.matched}줄·변경 {res.changed}줄·미매칭 {len(res.unmatched)}줄 ==")
    return res
