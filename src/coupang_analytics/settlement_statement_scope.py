"""위탁정산서 관리 상품 범위 — D-427(소유자 2026-11-26 원문 "우선 위탁 계정 쿠팡 정산은 셀독관리대장에 계정이 있고 관리대장에 있는 상품이
판매(과거 상품 변경 이력 포함)되고 있으면 정산 파일을 내려 받아서 정산 파일 생성, 반대로 관리대장에 계정이 없으면 계약 종료인것임, 계약서상
만료가 되어 있어도 관리대장에 계정이 있으면 계약 연장으로 봄").

- 정산서를 만드는 계정 = 지금 관리대장 계정 = 지금 결과 엑셀(`MASTER`) 사업자 시트에 블록이 있는 계정. 날짜별 사본에만 있는 계정 = 대장에서
  빠짐 = 계약 종료(`ledger_scope` 의 지금 계정 집합 · 호출부 `settlement_statement_account.scope`).
- 관리 상품(지금 대장 계정만) = ① 관리대장 VID(지금 + 날짜별 사본 `쿠팡데이타분석_통계_yymmdd.xlsx`·보관본 — 예전에 대장에 있다가 지운 상품도
  넣고 기간을 자르지 않음 · D-223 ②) + 출처판정 '옛 대장' · 원장 '정산전용상품' 시트 ② 출처판정 '이력원장'(원장 '상품이력') ·
  같은 상품명의 다른 VID(D-107 · `sales_summary.managed_listings` — 호출부). 계약서 품목·쿠팡 등록 로켓그로스 되찾기는 출처가 아님(D-427).
- 출처를 못 정한 상품('확인 필요')은 금액에 넣지 않음(정산서 '관리 상품 확인 필요' 시트) — 추정·대신 진행 없음.
"""
from __future__ import annotations

import gzip
import json
import re
from collections import defaultdict
from pathlib import Path

from coupang_analytics import sales_summary, workbook_sales
from coupang_analytics import settlement_read_store as STORE
from coupang_analytics.workbook import OutputWorkbook

MASTER = "쿠팡데이타분석_통계.xlsx"
SNAP = re.compile(r"쿠팡데이타분석_통계_(\d{6}|보관_\d{6}_\d{6})\.xlsx")     # 날짜별 사본(pipeline_paths._snapshot_path) · 보관본
SOURCE = "관리상품_출처판정.json"     # 옛 대장·이력원장 → 등록상품 AI 판정(D-230 · D-427)
KEEP, OWN = ("관리",), ("본인상품", "제외")


# ── ① 관리대장(지금 + 날짜별 사본) ──
def ledger_files(output: Path) -> list[Path]:
    snaps = sorted(p for p in output.glob("쿠팡데이타분석_통계_*.xlsx") if SNAP.fullmatch(p.name))
    return [p for p in [output / MASTER] if p.is_file()] + snaps


def merge_ledgers(blocks: list) -> dict:
    """[{계정ID: VID 집합}] → 합집합(VID 는 글자 · 옛 결과 엑셀은 옵션 여러 개를 'a|b' 한 칸에 적어 나눔)."""
    out: dict = defaultdict(set)
    for b in blocks:
        for aid, vids in b.items():
            out[aid] |= {one.strip() for v in vids for one in str(v).split("|") if one.strip()}
    return dict(out)


def _ledger_blocks(p: Path) -> dict:
    return workbook_sales.managed_vids(OutputWorkbook.load(p))


def _read_ledger(p: Path) -> dict:
    return STORE.read("결과엑셀", p, _ledger_blocks, ("settlement_statement_scope",))


def _master(output: Path) -> Path:
    """지금 결과 엑셀 — 없으면 FileNotFoundError(대장 계정을 모르면 전 계정이 계약 종료로 보이므로 시작 전 중단 · D-427)."""
    p = output / MASTER
    if not p.is_file():
        raise FileNotFoundError(f"관리대장 결과 엑셀 없음: {p}")
    return p


def current_accounts(output: Path) -> set:
    """지금 관리대장 계정 = 지금 결과 엑셀 블록이 있는 계정(D-427 · 판매중지 블록 포함 D-094)."""
    return set(_read_ledger(_master(output)))


def ledger_scope(output: Path) -> tuple[set, dict]:
    """(지금 관리대장 계정, {계정ID: 대장 VID}) — VID = 결과 엑셀(지금) + 날짜별 사본 블록(판매중지 블록 포함 · D-094) · 결과 엑셀은 한 번만 읽음."""
    files = [_master(output)] + [p for p in ledger_files(output) if p.name != MASTER]
    blocks = [_read_ledger(p) for p in files]
    return set(blocks[0]), merge_ledgers(blocks)


def ledger_vids(output: Path) -> dict:
    """{계정ID: 대장 VID} — `ledger_scope` 의 VID."""
    return ledger_scope(output)[1]


# ── 쿠팡 등록 상품 자료(상품조회 · 판매분석) ──
def _raw_page(p: Path) -> dict:
    return json.loads(gzip.decompress(p.read_bytes()).decode("utf-8"))["data"]


def inventory(output: Path) -> dict:
    """{계정ID: {등록상품ID: {"created": YYYY-MM-DD, "name": 상품명, "types": {VID: RFM|NORMAL}}}} — 상품조회 원문(`_raw`).
    `_raw` 는 쪽마다 덮어쓰기라 쪽 수가 줄면 옛 뒤쪽 파일이 남음(T-142 rladygks0221 72쪽인데 192쪽까지) → 1쪽이 말한 전체 쪽까지만."""
    out: dict = defaultdict(dict)
    pages: dict = defaultdict(dict)
    for p in sorted((output / "_raw").glob("*_vendor_inventory_p*.json.gz")):
        aid, n = p.name.removesuffix(".json.gz").rsplit("_vendor_inventory_p", 1)
        pages[aid][int(n)] = p
    for aid, files in pages.items():
        total = int(_raw_page(files[1])["pagination"]["totalPages"])
        for x in (x for n, p in files.items() if n <= total for x in _raw_page(p)["productList"]):
            out[aid][str(x["vendorInventoryId"])] = {
                "created": str(x["createdOn"])[:10], "name": x.get("productName") or "",
                "types": {str(i["vendorItemId"]): i.get("registrationType") for i in x.get("vendorInventoryItems") or []}}
    return dict(out)


def sales_groups(recs: dict) -> dict:
    """판매분석 기간 저장(계정 하나) → {등록상품ID: {"vids", "rg", "name"}} — 등록상품ID 빈 옵션은 뺌."""
    out: dict = {}
    for rec in recs.values():
        for v, o in (rec.get("옵션") or {}).items():
            g = str(o.get("등록상품ID") or "")
            if g:
                e = out.setdefault(g, {"vids": set(), "rg": False, "name": sales_summary._listing(o)})
                e["vids"].add(str(v))
                e["rg"] |= o.get("구분") == "로켓그로스"
    return out


def vid_names(stores, aid: str) -> dict:
    """{VID: 판매 기록 상품명} — 일별·기간 저장 전부(D-107 같은 이름 판정용)."""
    return {str(v): sales_summary._listing(o) for store in stores for rec in (store.get(aid) or {}).values()
            for v, o in (rec.get("옵션") or {}).items()}


COST_ONLY = "비용만 있는 등록상품(판매 줄 없음 · 상품조회·판매분석에 없음) — 출처 판정 전 · 금액 밖(D-244)"


def option_products(files: list) -> dict:
    """{옵션ID: 등록상품ID} — 정산 파일 주문 줄(옵션ID·등록상품ID 있는 줄) 짝. 값 = 판매 줄이 있는 등록상품(같은 달 취소로 합이 0 이어도) ·
    정산서(settlement_statement_account opt2pid)와 출처 판정 준비(prepare)가 같은 기준(T-53)."""
    return {str(r.option_id): str(r.product_id) for f in files for r in f.rows if r.option_id and r.product_id}


def sold_products(files: list) -> dict:
    """{등록상품ID: (상품명, 옵션ID 집합, 로켓그로스 여부)} — 정산 파일 주문 줄에 나온 등록상품(option_products 와 같은 줄 ·
    출처 판정 준비가 상품조회·판매분석에 없는 판매 상품도 판정 대상에 올림 · 소유자 2026-11-16 T-55 D-256)."""
    out: dict = {}
    for f in files:
        for r in f.rows:
            if r.option_id and r.product_id:
                name, opts, rg = out.get(str(r.product_id), ("", set(), False))
                opts.add(str(r.option_id))
                out[str(r.product_id)] = (name or str(r.product_name or ""), opts, rg or f.channel == "로켓그로스")
    return out


def cost_only(costs: dict, inv: dict, groups: dict, sold) -> dict:
    """{등록상품ID: (상품명, 옵션ID 집합)} — 비용 리포트 짝(costs = {옵션ID: (등록상품ID, 상품명)}) 중 상품조회(inv)·판매분석(groups)에
    없고 판매 줄도 없는(sold = 정산 파일 주문 줄의 등록상품 · option_products 값) 등록상품(판매 없이 비용만 · D-244 ④⑤ · T-53)."""
    out: dict = {}
    for opt, (pid, name) in sorted(costs.items()):
        if pid not in inv and pid not in groups and pid not in sold:
            out.setdefault(pid, (name, set()))[1].add(opt)
    return out


def cost_only_checks(costs: dict, inv: dict, groups: dict, seen: set) -> list:
    """[(등록상품ID, 상품명, 사유)] — 비용만 있는 등록상품 중 아직 어느 경로(관리·판매 줄·출처판정)도 다루지 않은 것(D-244 ⑤)."""
    return [(pid, name, COST_ONLY) for pid, (name, _o) in sorted(cost_only(costs, inv, groups, seen).items())]


# ── 정산 대상 상품 출처 순위(D-230 · D-427) ──
# ① 관리대장(지금·사본 = ledger_vids · 옛 PC 대장 = 출처판정 '옛 대장') ② 이력원장(원장 '정산전용상품' 시트 → '상품이력' = 출처판정 '이력원장').
# 옛 대장·이력원장 → 등록상품 = AI 판정표(코드에 계정·상품 조건 없음 · D-229). 아래 순위는 위 순위가 정한 상품을 바꾸지 않음.
OLD, HIST = "옛 대장", "이력원장"
SETTLE = "원장 정산전용상품"
SOURCES = (OLD, HIST)                 # 출처판정 json 이 쓸 수 있는 출처(계약서 = 출처 아님 · D-427)
ORDER = (OLD, SETTLE, HIST)
CHECK = "확인 필요"
VERDICTS = KEEP + OWN + (CHECK,)


def load_sources(path: Path) -> dict:
    """입력 폴더 출처판정 → {계정ID: {등록상품ID: {"출처", "판정", "상품명", "근거"}}} — 모르는 출처·판정 = ValueError."""
    data = json.loads(path.read_text(encoding="utf-8"))["계정"]
    for aid, prods in data.items():
        for pid, e in prods.items():
            if e.get("출처") not in SOURCES or e.get("판정") not in VERDICTS:
                raise ValueError(f"{SOURCE} {aid} {pid}: 출처 {e.get('출처')!r} · 판정 {e.get('판정')!r} — 허용 = {SOURCES} · {VERDICTS}")
    return data


def ranked(settle_marks: dict, sources: dict) -> dict:
    """계정 하나 → {등록상품ID: (출처, 판정, 근거, 상품명)} — ORDER 순서로 먼저 정한 출처가 그 상품을 정함."""
    by: dict = {OLD: {}, HIST: {}}
    for pid, e in sources.items():
        by[e["출처"]][str(pid)] = (e["판정"], e.get("근거") or "", e.get("상품명") or "")
    by[SETTLE] = {str(p): ((k, "", "") if k in KEEP + OWN else (CHECK, "원장 정산전용상품 구분 빈 칸", ""))
                  for p, k in settle_marks.items()}
    out: dict = {}
    for src in ORDER:
        for pid, (verdict, why, name) in by[src].items():
            out.setdefault(pid, (src, verdict, why, name))
    return out


def source_checks(rk: dict) -> list:
    """[(등록상품ID, 상품명, 사유)] — 출처에서 '확인 필요'로 남은 상품(금액 밖 · 정산서 '관리 상품 확인 필요' 시트)."""
    return [(pid, name, f"{src}: {why}".rstrip(": ")) for pid, (src, verdict, why, name) in sorted(rk.items()) if verdict == CHECK]


def source_vids(rk: dict, inv: dict, groups: dict) -> set:
    """출처 '관리' 등록상품 → 그 상품의 VID 전부(상품조회 옵션 + 판매분석 옵션 · 판매자배송 포함) — 정산 파일 상품 ID 와
    상품조회 등록상품ID 가 달라도 VID 로 잡는다."""
    out: set = set()
    for pid, (_s, verdict, *_x) in rk.items():
        if verdict in KEEP:
            out |= set((inv.get(pid) or {}).get("types") or {}) | set((groups.get(pid) or {}).get("vids") or ())
    return out


def source_counts(rk: dict) -> list:
    """['옛 대장 1개', …] — 출처별 '관리' 상품 수(0개 출처는 뺌 · ORDER 순서)."""
    n = {src: sum(1 for s, v, *_ in rk.values() if s == src and v in KEEP) for src in ORDER}
    return [f"{src} {k}개" for src, k in n.items() if k]

