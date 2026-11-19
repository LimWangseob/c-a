"""셀독 계약자별 상품 현황 — 자료 모으기·상품 묶기·셀독/개인 판정·10개 규칙(D-357·D-358 · T-132).

설계 = `output/_설계_261119_셀독고객별시트/설계안.md`(2·3·4·5절) · 양식 = 같은 폴더 시안(서식은 contractor_sheet_xlsx).
① 판매수집이 끝난 뒤 **로그인 없이 저장 자료만** 읽는다(매일 06:00 contractor_stage.run_daily · D-361).

읽는 자료(계정마다 · 그 실행 날짜 이후 저장분만 — 로그인 실패한 계정의 옛 값을 조용히 쓰지 않음):
- 상품 목록·판매상태·판매가 = `상품정보_일별/{계정}/{날짜}.json.gz`(product_info · 판매상태 = N3 productStatus 칸)
- 그로스 재고·판매가·즉시할인·productId = `재고현황_일별/{계정}/{날짜}.json.gz`(재고현황 응답 원문)
- 최근 7일 판매수량 = `판매분석_일별`(sales_history · 기록 없는 날 = 0)
- productId(링크) = `_상품ID_전체.json`(N1 누적 · ① 이 계정마다 덧붙임) + 재고현황 원문
- 셀독 VID = `_매칭결과.json`(① 매칭 결과 · 대장 줄 → VID) ∪ `_매칭고정.json`(매칭 고정 VID · D-009) — 설계안 3절 1번

셀독/개인 판정 3단(설계안 3절 · 전역 AI 매칭 규칙): ① VID 고정(대장) → ② 같은 계정·같은 상품명(D-107) → ③ AI 판정
(contractor_sheet_judge · 후보만 · 판정표 파일에 덧붙임). 판정 근거·애매한 건은 엑셀이 아니라 판정표 파일에만 남는다.
하드코딩 금지(D-229): 계정·상품 조건을 코드에 넣지 않는다.
"""
from __future__ import annotations

import gzip
import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from . import daily_snapshot, sales_history

KEY_URL = "contractor/url"                  # 설정 탭 '셀독 계약자별 상품 현황 링크'(appconfig · D-358 ⑩)
DIRNAME = "계약자별상품현황"                  # output 아래 폴더(D-358 ⑤)
FILE_PREFIX = "셀독_계약자별상품현황"         # 파일 = {접두}_yymmdd.xlsx(매일 새 파일)
PID_STORE = "_상품ID_전체.json"              # N1 VID→productId 누적 {계정: {VID: productId}}
MIN_TOTAL = 10                              # 쿠팡 계정 상품이 이 수 이상이면 7일 판매 0건 개인 상품을 뺌(D-357 ②)
DAYS = 7                                    # 판매 기간(D-358 ①)
SELLING = frozenset({"ON_SALE", "PARTIAL_ON_SALE"})

ST_ON, ST_OFF, ST_UNKNOWN = "판매중", "판매중지", "상태 미수집"
GROWTH, SELLER, BOTH = "로켓그로스", "판매자배송", "그로스+판매자배송"
BASIS_VID, BASIS_NAME = "VID 고정(대장)", "같은 상품명(D-107)"


@dataclass
class Item:
    """VID(옵션) 하나."""
    vid: str
    name: str
    opt: str
    method: str
    price: int | None
    real: int | None
    growth: int | None
    status: str
    pid: str = ""


@dataclass
class Prod:
    """시트 1줄 = 같은 계정·같은 등록상품명(옵션 합산)."""
    acc: str
    name: str
    vids: list[str]
    sel: bool
    basis: str
    pid: str
    vid: str
    method: str
    status: str
    price: int | None
    real: int | None
    growth: int | None
    d7: list[int | None]                    # 옛 날짜 → 최근(엑셀에서 뒤집어 최근이 왼쪽) · None = 그날 판매 기록 없음(공란)
    s7: int                                 # 기록 있는 날만 합(D-361 ③)


@dataclass
class Biz:
    """관리대장 사업자 하나(시트 1개 · D-357 ①)."""
    name: str
    reps: list[str]
    accs: list[str]
    rows: list[Prod] = field(default_factory=list)
    total: int = 0
    dropped: int = 0
    marks: list[str] = field(default_factory=list)   # '(로그인 실패)' 같은 짧은 표시(D-358 ⑦)

    @property
    def title(self) -> str:
        return " ".join([self.name, *dict.fromkeys(self.marks)])


@dataclass
class Report:
    days: list[date]
    bizs: list[Biz]
    ai_calls: int = 0


def norm(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def week_days(date_to: str) -> list[date]:
    """판매 7일(옛 → 최근) — 마지막 날 = ① 조회 끝 날(18시 실행 = 전날 · 판매 자료 익일 반영)."""
    last = date.fromisoformat(date_to)
    return [last - timedelta(days=i) for i in range(DAYS - 1, -1, -1)]


# ── 저장 자료 읽기 ───────────────────────────────────────────────
def _latest_file(out_dir, dirname: str, acc: str, since: str) -> Path | None:
    files = [p for p in daily_snapshot.complete_files(out_dir, dirname, acc) if p.name[:10] >= since]
    return files[-1] if files else None


def _read_gz(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def load_product_rows(out_dir, acc: str, since: str) -> list[dict] | None:
    """그 실행 날짜 이후 상품정보 완료본의 옵션 줄. 없음 = None(그날 자료 없음 — 로그인 실패 등)."""
    p = _latest_file(out_dir, daily_snapshot.PRODUCT_INFO_DIRNAME, acc, since)
    return None if p is None else list(_read_gz(p).get("상품") or [])


def load_inventory(out_dir, acc: str, since: str) -> tuple[list[dict] | None, int]:
    """재고현황 원문 → (viProperties, 깨진 쪽 수). 파일 없음 = (None, 0)(판매자배송만 쓰는 계정은 정상)."""
    p = _latest_file(out_dir, daily_snapshot.INVENTORY_DIRNAME, acc, since)
    if p is None:
        return None, 0
    props: list[dict] = []
    bad = 0
    for body in _read_gz(p).get("응답") or []:
        try:
            props += json.loads(body).get("viProperties") or []
        except (TypeError, ValueError, AttributeError):
            bad += 1
    return props, bad


def load_week(out_dir, acc: str, days: list[date]) -> tuple[dict[str, list[int | None]], list[int | None]]:
    """({VID: [7일 판매수량(옛 → 최근)]}, 기록에 없는 VID 의 7일). 그날 기록에 없는 VID = 0(판매분석은 판매·노출 있던 VID 만 줌) ·
    그 계정의 그날 판매 기록이 아예 없으면(정산 받기 늦음·실패) 그 날 = None(공란 · D-361 ③)."""
    rec = sales_history.load_account(out_dir, acc)
    base: list[int | None] = [0 if d.isoformat() in rec else None for d in days]
    out: dict[str, list[int | None]] = {}
    for i, d in enumerate(days):
        for vid, o in ((rec.get(d.isoformat()) or {}).get("옵션") or {}).items():
            out.setdefault(str(vid), list(base))[i] = int(o.get("판매수량") or 0)
    return out, base


def load_pid_store(out_dir) -> dict[str, dict[str, str]]:
    p = Path(out_dir) / PID_STORE
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def merge_pid_store(out_dir, acc: str, pids: dict[str, str]) -> int:
    """N1 — 그 계정 {VID: productId} 를 누적 파일에 덧붙임(있는 값은 새 값으로 · 지우지 않음). 새로 생긴 VID 수 반환."""
    data = load_pid_store(out_dir)
    have = data.setdefault(acc, {})
    new = {str(v): str(p) for v, p in pids.items() if v and p}
    added = sum(1 for v in new if v not in have)
    if not new or all(have.get(v) == p for v, p in new.items()):
        return 0
    have.update(new)
    path = Path(out_dir) / PID_STORE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)
    return added


# ── 상품 만들기 ───────────────────────────────────────────────
def _amount(pricing: dict, key: str) -> int:
    return int((pricing.get(key) or {}).get("amount") or 0)


def _growth_item(v: dict) -> Item | None:
    ld, pr = v.get("listingDetails") or {}, v.get("pricing") or {}
    vid = str(v.get("vendorItemId") or "")
    if not vid:
        return None
    sale, disc = _amount(pr, "salesPrice"), _amount(pr, "allMemberInstantDiscount")
    return Item(vid, ld.get("vendorInventoryName") or "", ld.get("vendorInventoryItemName") or "", GROWTH,
                sale or None, (sale - disc) if sale else None, (v.get("inventoryDetails") or {}).get("orderableQuantity"),
                ST_OFF if ld.get("isSaleSuspended") else ST_ON, str(ld.get("productId") or ""))


def _status_of(row: dict) -> str:
    st = row.get("productStatus")
    if st is None:
        return ST_UNKNOWN                   # 판매상태 칸 없는 옛 보관본(N3 전) — 지어내지 않음
    return ST_ON if st in SELLING else ST_OFF


def build_items(rows: list[dict], props: list[dict], pids: dict[str, str]) -> dict[str, Item]:
    """{VID: Item} — 그로스 = 재고현황(판매가·즉시할인·재고·productId) · 나머지 = 상품정보(판매가 = 실구매가)."""
    items: dict[str, Item] = {}
    for v in props:
        it = _growth_item(v)
        if it is not None:
            items[it.vid] = it
    for r in rows:
        vid = str(r.get("vendorItemId") or "")
        if not vid:
            continue
        status = _status_of(r)
        if vid in items:
            if status == ST_OFF:            # 상품조회가 판매중지면 판매중지(재고 화면은 판매중이어도)
                items[vid].status = ST_OFF
            continue
        price = r.get("salePrice")
        items[vid] = Item(vid, r.get("productName") or "", r.get("itemName") or "",
                          SELLER if r.get("registrationType") == "NORMAL" else GROWTH, price, price, None, status)
    for it in items.values():
        it.pid = it.pid or pids.get(it.vid, "")
    return items


def rule_basis(items: dict[str, Item], seldoc_vids: set[str]) -> dict[str, str]:
    """판정 1·2단 — {셀독 VID: 근거}. ① 대장 VID ② 그 VID 와 같은 계정·같은 상품명(공백 정리 뒤 완전 일치 · D-107)."""
    basis = {v: BASIS_VID for v in items if v in seldoc_vids}
    names = {norm(items[v].name) for v in basis}
    for v, it in items.items():
        if v not in basis and norm(it.name) in names:
            basis[v] = BASIS_NAME
    return basis


def _min(vals) -> int | None:
    got = [v for v in vals if v]
    return min(got) if got else None


def _group_status(its: list[Item]) -> str:
    states = {it.status for it in its}
    return ST_ON if ST_ON in states else (ST_UNKNOWN if ST_UNKNOWN in states else ST_OFF)


def _group_growth(its: list[Item]) -> int | None:
    growth = [it.growth for it in its if it.method == GROWTH and it.growth is not None]
    return sum(growth) if growth else None


def _group(acc: str, opts: list[tuple[Item, list[int | None]]], basis: dict[str, str]) -> Prod:
    """옵션 합산 — 판매가·실구매가 = 최저 · 그로스 재고 = 그로스 옵션 합 · 링크 = productId 있는 옵션(판매 많은 순)."""
    opts.sort(key=lambda o: (-sum(q or 0 for q in o[1]), o[0].opt or ""))
    its = [o[0] for o in opts]
    lead = next((it for it in its if it.pid), its[0])
    methods = {it.method for it in its}
    d7 = [None if opts[0][1][i] is None else sum(o[1][i] or 0 for o in opts) for i in range(DAYS)]   # 빈 날 = 계정 단위
    bases = list(dict.fromkeys(basis[it.vid] for it in its if it.vid in basis))
    return Prod(acc, its[0].name, [it.vid for it in its], bool(bases), " · ".join(bases), lead.pid, lead.vid,
                BOTH if len(methods) > 1 else its[0].method, _group_status(its), _min(it.price for it in its),
                _min(it.real for it in its), _group_growth(its), d7, sum(q or 0 for q in d7))


def account_prods(acc: str, items: dict[str, Item], week: dict[str, list[int | None]], basis: dict[str, str],
                  empty: list[int | None] | None = None) -> list[Prod]:
    """등록상품 1줄씩(같은 상품명 옵션 합산). 판매중지 옵션은 대장 VID 만 넣음(셀독은 판매중지도 표시 · D-358 ② · 같은 상품명
    옵션은 판매중만 = 승인된 시안 규칙 — 판매중지된 판매자배송 사본이 판매방식·그로스 재고에 섞이지 않게)."""
    groups: dict[str, list[tuple[Item, list[int | None]]]] = {}
    for vid, it in items.items():
        if basis.get(vid) != BASIS_VID and it.status == ST_OFF:
            continue
        groups.setdefault(norm(it.name), []).append((it, week.get(vid, empty or [0] * DAYS)))
    return [_group(acc, opts, basis) for opts in groups.values()]


def shown(p: Prod, n_acc: int) -> bool:
    """10개 규칙(D-357 ②) — 계정 상품 수(n_acc)가 MIN_TOTAL 이상이면 7일 판매 0건 개인 상품을 뺌."""
    return p.sel or p.s7 > 0 or n_acc < MIN_TOTAL


def link_targets(listings: list[tuple[str, str, str, list[str]]], known: set[str], seldoc_vids: set[str]) -> list[str]:
    """N2 — 링크(productId)를 따로 받아야 할 등록상품ID. listings = [(등록상품ID, 상품명, 판매상태, [VID])].

    시트에 나올 등록상품(대장 VID 가 든 것 · 판매중인 것) 중 productId 를 모르는 것만. 그 계정 상품이 MIN_TOTAL 미만이면
    판매 0건 개인 상품도 나오므로 전부, 이상이면 대장 VID 가 든 것만 — 판매가 있던 개인 상품은 판매분석이 productId 를 준다.
    계정 전체 조회(하루 약 58분 · pipeline_sales)는 하지 않는다."""
    rows = [(vinv, norm(n), bool(seldoc_vids & set(vids)), vids) for vinv, n, st, vids in listings
            if seldoc_vids & set(vids) or st in SELLING]
    n_acc = len({n for _, n, _, _ in rows})
    out = [vinv for vinv, _, sel, vids in rows if vinv and not (known & set(vids)) and (sel or n_acc < MIN_TOTAL)]
    return list(dict.fromkeys(out))


__all__ = ["KEY_URL", "DIRNAME", "FILE_PREFIX", "MIN_TOTAL", "Item", "Prod", "Biz", "Report", "account_prods",
           "build_items", "link_targets", "load_inventory", "load_pid_store", "load_product_rows", "load_week",
           "merge_pid_store", "norm", "rule_basis", "shown", "week_days"]
