"""장부 DB 이관 ①·②·⑥ — 판매분석 일별 → sale_daily · 주문별매출 → order_line('주문별매출') · 라이브정산 상세 → product_cost
· 상품조회·판매분석 원문·RG 재고(최신·날짜별)·주문 줄 → option_attr(옵션 짝 · 금액 없음 · 대조표 7절 빠짐 #56~58).

- 판매분석 일별 = 옵션×결제일(판매 0 인 옵션 줄 = 뺀 줄 이유 '판매 0 옵션'). 사본은 옛 한 파일 `{계정ID}.json`,
  지금 코드는 `{계정ID}/{YYYY-MM}.json`(D-243) — 둘 다 읽는다.
- 주문별매출 = 윙 구매확정일 기준 달 파일 · 상품+배송비가 한 줄(apAmount = productGmv + deliveryGmv − sfcAmount − trAmountIncVat).
- 월자료의 다른 파일은 대조표 판정대로 '생략' 또는 '확인 필요'(J4 전 미반영)로 이름만 남긴다.
"""
from __future__ import annotations

import gzip
import json
import re
import sqlite3
from pathlib import Path

from .ledger_src import Registry, account_id, d10, nid, won

RAW = re.compile(r"^(?P<acc>.+?)_(?P<kind>vendor_inventory|sales|inventory)_p\d+\.json\.gz$")
MONTH_FILES = {"주문별매출": "반영", "라이브정산": "반영", "매입세금계산서": "확인 필요", "윙부가세상세": "생략",
               "RG부가세상세": "생략", "위수탁세금계산서": "생략", "RG재고변동": "생략", "RG반품내역": "생략"}
_OL = ("INSERT INTO order_line(account_id, sale_type, order_no, item_key, txn_type, seq, option_id, product_id, inventory_id, "
       "recognized, paid_date, cycle_end, qty, gross, sales, coupon, fee, settle, src, file_id, sheet, src_row) "
       "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")


class Attr:
    """옵션 짝 모으기 → option_attr(처음·마지막 본 날)."""

    def __init__(self):
        self.seen: dict[tuple, list[str]] = {}

    def add(self, acc, vid, st, inv, pid, item, sku, src, day) -> None:
        if not vid:
            return
        k = (acc, nid(vid), st or "", nid(inv), nid(pid), nid(item), nid(sku), src)
        v = self.seen.setdefault(k, [day, day])
        v[0], v[1] = min(v[0], day), max(v[1], day)

    def flush(self, con: sqlite3.Connection) -> None:
        con.executemany("INSERT INTO option_attr VALUES (?,?,?,?,?,?,?,?,?,?)",
                        [k + tuple(v) for k, v in sorted(self.seen.items())])


class SalesLoader:
    def __init__(self, con: sqlite3.Connection, reg: Registry):
        self.con, self.reg, self.attr = con, reg, Attr()

    # ── 판매분석 일별 ──
    def daily(self, base: Path) -> None:
        files = sorted(base.glob("*.json")) + sorted(base.glob("*/*.json"))
        for p in files:
            acc = p.stem if p.parent == base else p.parent.name
            fid = self.reg.add(p, "판매분석 일별", acc)
            if fid is None:
                continue
            d = json.loads(p.read_text(encoding="utf-8"))
            rows, read = [], 0
            for day, rec in sorted(d.items()):
                if len(day) != 10:
                    continue
                for vid, o in sorted((rec.get("옵션") or {}).items()):
                    read += 1
                    qty, amt, orders = won(o.get("판매수량")), won(o.get("판매금액")), won(o.get("주문"))
                    self.attr.add(acc, vid, o.get("구분"), o.get("등록상품ID"), "", "", "", "판매분석 일별", day)
                    if not (qty or amt or orders):
                        self.reg.skip(fid, "판매 0 옵션")
                        continue
                    rows.append((acc, o.get("구분") or "", nid(vid), day, qty, amt, orders, nid(o.get("등록상품ID")),
                                 str(rec.get("수집") or ""), fid, f"{day}.{vid}"))
            self.con.executemany("INSERT INTO sale_daily VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
            self.reg.done(fid, read, len(rows))
        self.con.commit()

    # ── 월자료 ──
    def monthly(self, base: Path) -> None:
        if not base.is_dir():
            return
        for d in sorted(x for x in base.iterdir() if x.is_dir()):
            acc = account_id(d.name)
            for p in sorted(d.iterdir()):
                kind = re.split(r"_\d{6}|_최신", p.stem)[0]
                status = MONTH_FILES.get(kind, "생략")
                if status != "반영":
                    note = "확인 필요(J4) — 판정 전 미반영" if status == "확인 필요" else "대조표 7-5절 생략"
                    self.reg.add(p, f"월자료 {kind}", acc, status=status, note=note)
                    continue
                fid = self.reg.add(p, f"월자료 {kind}", acc)
                if fid is not None:
                    (self._orders if kind == "주문별매출" else self._live)(p, fid, acc)
        self.con.commit()

    def _orders(self, p: Path, fid: int, acc: str) -> None:
        lines = json.loads(p.read_text(encoding="utf-8")).get("줄") or []
        seen: dict[tuple, int] = {}
        rows = []
        for i, r in enumerate(lines):
            vid = nid(r.get("vendorItemId"))
            item = vid or f"배송비:{nid(r.get('shippingFeeId'))}"
            tt, conf = str(r.get("transactionType") or ""), d10(r.get("confirmDate"))
            key = (nid(r.get("orderId")), item, tt, conf)
            seen[key] = seen.get(key, 0) + 1
            pg, dg = won(r.get("productGmv")), won(r.get("deliveryGmv"))
            rows.append((acc, "윙", key[0], item, tt, seen[key], vid, "", "", conf, d10(r.get("paidDate")), "", 0, pg,
                         pg + dg, won(r.get("sfcAmount")), won(r.get("trAmountIncVat")), won(r.get("apAmount")),
                         "주문별매출", fid, "", i))
        self.con.executemany(_OL, rows)
        self.reg.done(fid, len(lines), len(rows))

    def _live(self, p: Path, fid: int, acc: str) -> None:
        j = json.loads(p.read_text(encoding="utf-8"))
        det = j.get("상세") or []
        for i, r in enumerate(det):
            self.con.execute(
                "INSERT INTO product_cost(account_id, kind, nat_key, option_id, inventory_id, order_no, txn_type, occur_date, "
                "cycle_end, settle_type, amount, sign, file_stage, settle_date, file_id, sheet, src_row) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (acc, "라이브 수수료", f"{nid(r.get('orderId'))}|{nid(r.get('vendorItemId'))}|{r.get('orderOrCancel')}",
                 nid(r.get("vendorItemId")), "", nid(r.get("orderId")), str(r.get("orderOrCancel") or ""),
                 d10(r.get("calculationDate")), "", "", -won(r.get("totalAmount")), -1, "라이브정산",
                 d10(r.get("calculationDate")), fid, "상세", i))
        n_sum = len(j.get("요약") or [])
        if n_sum:
            self.reg.skip(fid, "요약[] — 확인 필요(J4)", n_sum)
        self.reg.done(fid, len(det) + n_sum, len(det))

    # ── 옵션 짝 원천(_raw · 재고현황_일별) ──
    def raw(self, base: Path) -> None:
        for p in sorted(base.glob("*.json.gz")):
            m = RAW.match(p.name)
            if not m:
                continue
            acc, kind = m["acc"], m["kind"]
            fid = self.reg.add(p, f"원문 {kind}", acc)
            if fid is None:
                continue
            day = "최신"
            n = self._raw_file(json.load(gzip.open(p, "rt", encoding="utf-8")), acc, kind, day)
            self.reg.done(fid, n, n)

    def _raw_file(self, j: dict, acc: str, kind: str, day: str) -> int:
        n = 0
        if kind == "vendor_inventory":
            for pr in (j.get("data") or {}).get("productList") or []:
                for it in pr.get("vendorInventoryItems") or []:
                    self.attr.add(acc, it.get("vendorItemId"), it.get("registrationType") or pr.get("registrationType"),
                                  pr.get("vendorInventoryId"), "", "", it.get("skuId"), "상품조회", day)
                    n += 1
        elif kind == "sales":
            for x in j.get("vendorItems") or []:
                vd = x.get("vendorItemDetails") or {}
                self.attr.add(acc, vd.get("vendorItemId"), vd.get("registrationType"), vd.get("inventoryId"),
                              vd.get("productId"), vd.get("itemId"), "", "판매분석 원문", day)
                n += 1
        else:
            n = self._inventory(j.get("viProperties") or [], acc, "RG 재고(최신)", day)
        return n

    def _inventory(self, props: list, acc: str, src: str, day: str) -> int:
        for x in props:
            ld = x.get("listingDetails") or {}
            self.attr.add(acc, x.get("vendorItemId"), "RFM", ld.get("vendorInventoryId"),
                          ld.get("productId") or x.get("productId"), ld.get("itemId") or x.get("itemId"), "", src, day)
        return len(props)

    def snapshots(self, base: Path) -> None:
        if not base.is_dir():
            return
        for d in sorted(x for x in base.iterdir() if x.is_dir()):
            for p in sorted(d.glob("*.json.gz")):
                fid = self.reg.add(p, "RG 재고현황 날짜별", d.name)
                if fid is None:
                    continue
                j = json.load(gzip.open(p, "rt", encoding="utf-8"))
                n = 0
                for s in j.get("응답") or []:
                    resp = json.loads(s) if isinstance(s, str) else s
                    n += self._inventory(resp.get("viProperties") or [], d.name, "RG 재고 날짜별", str(j.get("날짜") or p.name[:10]))
                self.reg.done(fid, n, n)

    def from_lines(self) -> None:
        q = ("SELECT account_id, option_id, sale_type, product_id, inventory_id, MIN(recognized), MAX(recognized), src "
             "FROM order_line WHERE option_id != '' GROUP BY account_id, option_id, sale_type, product_id, inventory_id, src")
        for acc, vid, st, pid, inv, lo, hi, src in self.con.execute(q).fetchall():
            self.attr.add(acc, vid, st, inv, pid, "", "", f"주문 줄({src})", lo or "")
            self.attr.add(acc, vid, st, inv, pid, "", "", f"주문 줄({src})", hi or "")


def load(con: sqlite3.Connection, reg: Registry, output: Path) -> None:
    s = SalesLoader(con, reg)
    output = Path(output)
    s.daily(output / "판매분석_일별")
    s.monthly(output / "정산" / "검증자료" / "월자료")
    s.raw(output / "_raw")
    s.snapshots(output / "재고현황_일별")
    for sub, kind, note in (("판매분석_기간", "판매분석 기간", "확인 필요(J4) — 판정 전 미반영"),
                            ("쿠폰목록_일별", "쿠폰목록 날짜별", "대조표 7-7절 생략(불필요)")):
        for p in sorted((output / sub).rglob("*")) if (output / sub).is_dir() else []:
            if p.is_file():
                acc = p.parent.name if p.parent.name != sub else p.stem
                reg.add(p, kind, acc, status="확인 필요" if "확인" in note else "생략", note=note)
    s.from_lines()
    s.attr.flush(con)
    reg.flush()
