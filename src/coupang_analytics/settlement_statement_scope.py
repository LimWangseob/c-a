"""위탁정산서 관리 상품 범위 — 소유자 2026-11-12 승인 규칙 ①~⑤(원문 "규칙안 5가지 승인, 기준일·달 단위도 제안대로 진행해").

① 관리 상품 = 관리대장 상품: 지금 결과 엑셀 사업자 시트 블록 + 날짜별 사본(`쿠팡데이타분석_통계_yymmdd.xlsx` · 보관본) 블록 —
  예전에 대장에 있다가 지운 상품도 넣고 관리 기간을 자르지 않음(D-223 ②). 계정째 대장에서 빠진 계정도 같음(D-210).
② 같은 상품명의 다른 VID(판매자배송·다른 수량 옵션·재등록) = `sales_summary.managed_listings`(D-107 · 같은 계정만) — 호출부.
③ 대장에서 이력 없이 지워진 상품만 그 계정의 쿠팡 등록 **로켓그로스** 상품에서 되찾음(D-222 · D-159 ②): 상품조회(`_raw`) 상품 중
  RFM 옵션이 있는 상품 → 그 상품의 모든 VID(판매자배송 겸용분 포함) · 상품조회에 없는 판매분석 등록상품 중 '로켓그로스' 옵션이 있는 것.
  판매자배송으로만 등록된 상품은 되찾지 않음.
④ 등록 조건 = 등록 달 ≥ 기준 달(달 단위): 기준 = 계약일(`관리시작달_차이표` F칸) · 계약을 못 찾고 대장에만 있는 계정 = 원장
  '계정이력'의 첫 관리 시작. 상품조회에 없는 상품의 등록 달 = 등록상품ID 순서(D-159 근거: ID 시간순 역전 0건) — 앞뒤로 못 가르면 확인 필요.
⑤ 위탁자 본인 상품 제외(D-107 · D-159 ③) = 입력 폴더 AI 판정표 `JUDGE`(되찾을 후보마다 '관리'·'본인상품'·'제외' + 근거).
⑤를 판정 못 했거나 자료가 없으면 '확인 필요'(금액에 넣지 않음 · 정산서 '관리 상품 확인 필요' 시트) — 추정·대신 진행 없음.
"""
from __future__ import annotations

import gzip
import json
import re
from collections import defaultdict
from pathlib import Path

from coupang_analytics import sales_summary, workbook_sales
from coupang_analytics.registry_model import ITEM_ACCT_ID, K_CONFIRMED, K_INIT, K_NEW_ACCT, K_RESUME, SHEET_ACCT
from coupang_analytics.workbook import OutputWorkbook

MASTER = "쿠팡데이타분석_통계.xlsx"
SNAP = re.compile(r"쿠팡데이타분석_통계_(\d{6}|보관_\d{6}_\d{6})\.xlsx")     # 날짜별 사본(pipeline_paths._snapshot_path) · 보관본
JUDGE = "관리상품_되찾기_판정.json"
KEEP, OWN = ("관리",), ("본인상품", "제외")
NO_INV = "상품조회 자료 없음 — 이력 없이 지운 로켓그로스 상품을 되찾지 못함"
NO_BASE = "기준일 없음(계약 없음 · 원장 계정이력에 관리 시작 없음)"


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


def ledger_vids(output: Path) -> dict:
    """{계정ID: 대장 VID} — 결과 엑셀(지금) + 날짜별 사본 블록(판매중지 블록 포함 · D-094)."""
    return merge_ledgers([workbook_sales.managed_vids(OutputWorkbook.load(p)) for p in ledger_files(output)])


# ── ③ 쿠팡 등록 상품 자료 ──
def inventory(output: Path) -> dict:
    """{계정ID: {등록상품ID: {"created": YYYY-MM-DD, "name": 상품명, "types": {VID: RFM|NORMAL}}}} — 상품조회 원문(`_raw`)."""
    out: dict = defaultdict(dict)
    for p in sorted((output / "_raw").glob("*_vendor_inventory_p*.json.gz")):
        aid = p.name.split("_vendor_inventory_p")[0]
        for x in json.loads(gzip.decompress(p.read_bytes()).decode("utf-8"))["data"]["productList"]:
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


# ── ④ 기준 달 ──
def first_starts(rows: list) -> dict:
    """원장 '계정이력' 줄(머리줄 + 줄) → {계정ID: (첫 관리 시작일, 원장 기록 시작일의 최초등록인가)}. 비밀번호 줄은 읽지 않음."""
    if not rows:
        return {}
    h = {str(c): k for k, c in enumerate(rows[0])}
    body = sorted((list(r) + [""] * len(h) for r in rows[1:]), key=lambda r: (str(r[h["효력일"]])[:10], str(r[h["번호"]]).zfill(9)))
    begin = min((str(r[h["효력일"]])[:10] for r in body if r[h["변동유형"]] == K_INIT), default="")
    out: dict = {}
    for r in body:
        aid, kind, eff = str(r[h["계정아이디"]]).strip(), r[h["변동유형"]], str(r[h["효력일"]])[:10]
        if kind == K_CONFIRMED and r[h["항목"]] == ITEM_ACCT_ID and str(r[h["이전값"]]).strip() in out:
            out.setdefault(str(r[h["변경값"]]).strip(), out[str(r[h["이전값"]]).strip()])
        elif kind in (K_INIT, K_NEW_ACCT, K_RESUME) and aid:
            out.setdefault(aid, (eff, kind == K_INIT and eff == begin))
    return out


def account_history(snapshot: Path | None) -> tuple[dict, str]:
    """원장 '계정이력' → (first_starts, 못 읽은 사유). 사본 json 을 주면 그것, 없으면 구글 실시간."""
    if snapshot is not None:
        return first_starts(json.loads(snapshot.read_text(encoding="utf-8"))), ""
    try:
        from coupang_analytics import appconfig, gsheet_api
        rows = gsheet_api.GSheetClient(appconfig.get("registry/url", "")).read_values(SHEET_ACCT)
    except Exception as exc:  # noqa: BLE001 — 못 읽으면 계약 없는 계정의 되찾기 후보가 전부 '확인 필요'(사유를 정산서에 적음)
        return {}, f"원장 계정이력 못 읽음: {exc.__class__.__name__}"
    return first_starts(rows), ""


def baseline(aid: str, contracts: dict, starts: tuple) -> tuple:
    """(기준 달 YYYY-MM | None, 근거 이름, 기준일, 기준 전 등록 = 확인 필요인가(원장 기록 시작 전부터 관리), 없을 때 사유)."""
    if contracts.get(aid):
        return contracts[aid][:7], "계약", contracts[aid], False, ""
    got, err = starts
    if aid in got:
        d, at_begin = got[aid]
        return d[:7], "원장 첫 관리 시작", d, at_begin, ""
    return None, "", "", False, NO_BASE + (f" · {err}" if err else "")


def _bounds(bm: str, inv_all: dict) -> tuple:
    """(bm 달 앞 등록 상품 ID 최댓값, bm 달 이후 등록 상품 ID 최솟값) — 상품조회 전 계정."""
    ids = [(int(p), e["created"][:7]) for prods in inv_all.values() for p, e in prods.items() if p.isdigit()]
    return max((i for i, m in ids if m < bm), default=None), min((i for i, m in ids if m >= bm), default=None)


def id_side(pid: str, bm: str, inv_all: dict) -> str | None:
    """상품조회에 없는 등록상품의 등록 달 ≥ bm 여부를 ID 순서로 — 'after'·'before'·None(못 가름 · 앞뒤가 엇갈림)."""
    lo, hi = _bounds(bm, inv_all)
    if not pid.isdigit() or (lo is not None and hi is not None and lo >= hi):
        return None
    if hi is not None and int(pid) >= hi:
        return "after"
    if lo is not None and int(pid) <= lo:
        return "before"
    return None


# ── ③④⑤ 되찾기 ──
def candidates(inv: dict, groups: dict, is_mv) -> list:
    """[(등록상품ID, 상품명, VID 집합, 등록일 | None)] — 대장 상품(VID·같은 이름)이 아닌 로켓그로스 등록 상품."""
    out = []
    for pid, e in inv.items():
        if "RFM" in e["types"].values() and not any(is_mv(v) for v in e["types"]):
            out.append((pid, e["name"], set(e["types"]), e["created"]))
    for g, e in groups.items():
        if g not in inv and e["rg"] and not any(is_mv(v) for v in e["vids"]):
            out.append((g, e["name"], set(e["vids"]), None))
    return out


def _side(pid: str, created: str | None, bm: str, inv_all: dict) -> tuple:
    if created:
        return ("after" if created[:7] >= bm else "before"), f"등록 {created}"
    return id_side(pid, bm, inv_all), "등록일 = 등록상품ID 순서(상품조회에 없음)"


def classify(cand: tuple, base: tuple, judge: dict, inv_all: dict) -> tuple:
    """후보 하나 → ('관리' | '제외' | '확인 필요', 사유)."""
    pid, _name, _vids, created = cand
    bm, src, bdate, unsure_before, why = base
    if bm is None:
        return "확인 필요", why
    side, how = _side(pid, created, bm, inv_all)
    if side is None:
        return "확인 필요", f"등록일 모름 — 상품조회에 없고 등록상품ID 순서로도 {src} 달({bdate}) 앞뒤를 못 가름"
    if side == "before":
        if unsure_before:
            return "확인 필요", f"관리 시작일 모름 — 원장 기록 시작({bdate}) 전부터 관리 · {how}"
        return "제외", f"{src} 달 전 등록({src} {bdate} · {how})"
    j = judge.get(pid) or {}
    if j.get("판정") in KEEP:
        return "관리", f"{src} 달 이후 등록({how}) · {j.get('근거') or ''}".rstrip(" ·")
    if j.get("판정") in OWN:
        return "제외", f"위탁자 본인 상품 등({j['판정']}) — {j.get('근거') or ''}".rstrip(" —")
    if j:
        return "확인 필요", f"위탁자 본인 상품인지 못 정함 — {j.get('근거') or j.get('판정')}"
    return "확인 필요", "위탁자 본인 상품인지 판정 없음"


def recover(aid: str, is_mv, stores, inv_all: dict, base: tuple, judge: dict) -> dict:
    """계정 하나 → {"vids": 되찾은 VID, "got"·"excl"·"check": [(등록상품ID, 상품명, 사유)]}."""
    r: dict = {"vids": set(), "got": [], "excl": [], "check": []}
    if aid not in inv_all:
        r["check"].append(("", "", NO_INV))
        return r
    groups = sales_groups(stores[1].get(aid) or {})
    for cand in sorted(candidates(inv_all[aid], groups, is_mv)):
        verdict, why = classify(cand, base, judge.get(aid) or {}, inv_all)
        r[{"관리": "got", "제외": "excl", "확인 필요": "check"}[verdict]].append((cand[0], cand[1], why))
        if verdict == "관리":
            r["vids"] |= cand[2]
    return r


def recover_all(ledger: dict, listings: dict, stores, inv_all: dict, contracts: dict, starts: tuple, judge: dict) -> dict:
    """대장 계정마다 recover — {계정ID: 결과}. stores = (일별, 기간) 판매분석 저장."""
    out = {}
    for aid, vids in ledger.items():
        names, vname = listings.get(aid) or set(), vid_names(stores, aid)

        def is_mv(v: str, vids=vids, names=names, vname=vname) -> bool:
            return v in vids or vname.get(v) in names
        out[aid] = recover(aid, is_mv, stores, inv_all, baseline(aid, contracts, starts), judge)
    return out


def load_judge(path: Path) -> dict:
    """입력 폴더 AI 판정표 → {계정ID: {등록상품ID: {"판정", "근거", ...}}}."""
    return json.loads(path.read_text(encoding="utf-8"))["계정"]
