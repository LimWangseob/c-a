"""장부 DB 이관 ② — 정산 파일(윙 주문상세 · 로켓그로스 판매수수료) → order_line(주문 줄 한 번만) + order_pay(지급 기록).

- 파일 이름 = `{계정}_{정산일}_{채널}_{유형}_{리포트}_{기간시작}-{기간끝}.xlsx`(settlement_files 규칙 · 계정·기간은 이름에서).
- 주문 줄 KEY = 계정ID+판매방식+주문번호+(옵션ID/배송비 표시)+거래유형+인식일+seq(KEY 분석 3절 · 샘플검증 5절 2).
  윙은 거래유형 칸이 없어 금액 부호로 '판매'/'환불'을 만든다. seq = 한 파일 안 같은 KEY 의 n번째 줄.
- 같은 줄이 지급 단계(주정산 70% · 최종액 30% · 보류 해제 100%)마다 다른 파일에 다시 나오면 주문 줄은 하나, 지급 기록만 추가.
  같은 KEY 인데 금액이 다르면 줄을 새로 만들지 않고 검사 기록(check_result 'L1 같은 KEY 금액 다름')으로 남긴다(J3 판정 대상).
- 윙 0원 보조줄(상품명 없음·수량·금액 0) = 장부에 안 넣고 뺀 줄 이유 '0원 보조줄'로 센다.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from . import settlement_files as SF
from .ledger_src import Registry, account_id, blank, cell, d10, find_header, header_index, nid, won

NAME = re.compile(r"^(?P<acc>.+)_(?P<sd>\d{8})_(?P<ch>윙|로켓그로스)_(?P<kind>[^_]+)_(?P<rep>주문상세|판매수수료)_"
                  r"(?P<ps>\d{8})-(?P<pe>\d{8})\.xlsx$")
_SHIP = re.compile(r"<[^<>]{1,20}배송료>")
_AMT = ("qty", "gross", "sales", "coupon", "fee", "settle")


def ymd(s: str) -> str:
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def _wing_row(r: list, ix: dict, where: str) -> dict | None:
    item = nid(cell(r, ix, "옵션ID"))
    qty, rqty = won(cell(r, ix, "판매수량"), where), won(cell(r, ix, "환불수량"), where)
    sales, settle = won(cell(r, ix, "판매액"), where), won(cell(r, ix, "정산금액"), where)
    fee = won(cell(r, ix, "판매수수료"), where) - won(cell(r, ix, "마이샵수수료할인"), where)
    coupon = won(cell(r, ix, "판매자할인쿠폰(A+B)"), where)
    named = bool(str(cell(r, ix, "상품명") or "").strip())
    if not named and not any((qty, rqty, sales, fee, settle, coupon)):
        return None
    refund = sales < 0 or (sales == 0 and settle < 0) or (rqty > 0 and qty == 0)
    return {"order_no": nid(cell(r, ix, "주문번호")), "item_key": item, "txn_type": "환불" if refund else "판매",
            "option_id": "" if _SHIP.fullmatch(item) else item, "product_id": nid(cell(r, ix, "상품ID")),
            "inventory_id": "", "recognized": d10(cell(r, ix, "구매확정일")), "paid_date": d10(cell(r, ix, "결제완료일")),
            "cycle_end": "", "qty": qty - rqty, "gross": sales, "sales": sales, "coupon": coupon, "fee": fee,
            "settle": settle}


def _rg_row(r: list, ix: dict, where: str) -> dict:
    vid = nid(cell(r, ix, "옵션ID"))
    return {"order_no": nid(cell(r, ix, "주문ID")), "item_key": vid, "txn_type": str(cell(r, ix, "거래유형") or "").strip(),
            "option_id": vid, "product_id": "", "inventory_id": nid(cell(r, ix, "등록상품ID")),
            "recognized": d10(cell(r, ix, "매출인식일")), "paid_date": d10(cell(r, ix, "발생일(결제완료일)")),
            "cycle_end": d10(cell(r, ix, "정산주기(종료일)")), "qty": won(cell(r, ix, "판매수량(B)"), where),
            "gross": won(cell(r, ix, "판매액(A*B)"), where), "sales": won(cell(r, ix, "매출금액(A*B-C)"), where),
            "coupon": won(cell(r, ix, "판매자할인쿠폰(D+E)"), where),
            "fee": won(cell(r, ix, "판매수수료"), where) + won(cell(r, ix, "판매수수료VAT"), where),
            "settle": won(cell(r, ix, "정산대상액"), where)}


class SettleLoader:
    """파일을 차례로 읽어 주문 줄은 한 번만 만들고 지급 기록을 붙인다."""

    def __init__(self, con: sqlite3.Connection, reg: Registry):
        self.con, self.reg = con, reg
        self.lines: dict[tuple, tuple[int, tuple]] = {}
        self.next_id = 1

    def run(self, base: Path) -> None:
        for p in sorted(Path(base).glob("*.xlsx")):
            m = NAME.match(p.name)
            if not m:
                self.reg.add(p, "정산 파일(이름 규칙 밖)", None, status="생략", note="이름 규칙 밖 — 읽지 않음")
                continue
            acc = account_id(m["acc"])
            fid = self.reg.add(p, f"{m['ch']} {m['rep']}", acc)
            if fid is None:
                continue
            try:
                self._file(p, fid, acc, m)
            except Exception as exc:          # 파일 하나 실패 = 그 파일 '오류'로 남기고 다음 파일(V2 가 보고)
                self.reg.fail(fid, f"{type(exc).__name__}: {exc}")
        self.reg.flush()

    def _file(self, p: Path, fid: int, acc: str, m: re.Match) -> None:
        ch = m["ch"]
        grid = SF.read_grid(p)
        hr = find_header(grid, ("주문번호", "옵션ID") if ch == "윙" else ("주문ID", "옵션ID", "정산대상액"), 6)
        if hr < 0:
            raise ValueError("머리글을 찾지 못함")
        ix = header_index(grid[hr])
        pay = (m["kind"], ymd(m["sd"]), ymd(m["ps"]), ymd(m["pe"]))
        seen: dict[tuple, int] = {}
        read = loaded = 0
        new_lines, pays = [], []
        for n, r in enumerate(grid[hr + 1:], start=hr + 2):
            if blank(r):
                continue
            read += 1
            where = f"{p.name} {n}행"
            v = _wing_row(r, ix, where) if ch == "윙" else _rg_row(r, ix, where)
            if v is None:
                self.reg.skip(fid, "0원 보조줄")
                continue
            key = (acc, ch, v["order_no"], v["item_key"], v["txn_type"], v["recognized"])
            seen[key] = seen.get(key, 0) + 1
            ident = key + (seen[key],)
            amt = tuple(v[k] for k in _AMT)
            got = self.lines.get(ident)
            if got is None:
                lid = self.next_id
                self.next_id += 1
                self.lines[ident] = (lid, amt)
                new_lines.append((lid, acc, ch, v["order_no"], v["item_key"], v["txn_type"], seen[key], v["option_id"],
                                  v["product_id"], v["inventory_id"], v["recognized"], v["paid_date"], v["cycle_end"],
                                  *amt, "주문상세" if ch == "윙" else "판매수수료", fid, "", n))
            else:
                lid = got[0]
                if got[1] != amt:
                    self._conflict(acc, ident, got[1], amt, where)
            pays.append((lid, fid, n, *pay))
            loaded += 1
        self.con.executemany(f"INSERT INTO order_line VALUES ({','.join('?' * 23)})", new_lines)
        self.con.executemany("INSERT INTO order_pay VALUES (?,?,?,?,?,?,?)", pays)
        self.reg.done(fid, read, loaded)
        self.con.commit()

    def _conflict(self, acc: str, ident: tuple, old: tuple, new: tuple, where: str) -> None:
        subj = "|".join(str(x) for x in ident[1:]) + f"@{where}"
        self.con.execute("INSERT OR REPLACE INTO check_result VALUES (?,?,?,?,?,?,?,?)",
                         ("L1 같은 KEY 금액 다름", acc, subj, old[-1], new[-1], new[-1] - old[-1], "확인 필요", ""))


def load(con: sqlite3.Connection, reg: Registry, settle_dir: Path) -> None:
    SettleLoader(con, reg).run(Path(settle_dir) / "파일")
