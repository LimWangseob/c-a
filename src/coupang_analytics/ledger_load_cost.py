"""장부 DB 이관 ③ — 로켓그로스 비용 리포트(`정산/파일/비용/*.xlsx`) → product_cost(옵션 단위) · account_entry(계정 단위).

- 시트 모양(자료목록 B-2): 3·4행 요약(정산주기 끝·합계·세액·최종비용 = VAT 포함) · 7·8행 2줄 머리글 · 9행부터 자료
  (재고 손실 보상 2·3행 · 리뷰 이벤트 6·7행). 상세 줄 금액 = VAT 별도.
- D-263: 옵션 칸이 있는 줄 = 상품 내역(product_cost) · 옵션 칸이 없는 '반출 배송 서비스비' = 계정 내역(고리 = 반출ID 칸).
  요약의 세액 = 계정 단위로 오는 값 → 계정 내역('지급 구성') · 요약 최종비용 = 대조용(상품 줄 합 + 세액 = 요약 · V 검사).
- 금액 칸 = 최종비용 → 할인적용가(A-B) → 할인적용금액(A-B-C) → 보상 금액 순(시트마다 있는 칸) · 재고 손실 보상 = 받는 돈(+).
- '자동반출(고객반품) - 쿠팡귀책' 시트 = 수량 안내·금액 없음 → 뺀 줄 이유로 셈(settlement_files 와 같음).
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from . import settlement_files as SF
from .ledger_src import Registry, account_id, blank, d10, nid, nm, won

NAME = re.compile(r"^(?P<acc>.+)_(?P<sd>\d{8})_로켓그로스_(?P<kind>[^_]+)_(?P<rep>[^_]+)_(?P<ps>\d{8})-(?P<pe>\d{8})\.xlsx$")
_SUB = ("발생비용(A)", "할인가(B)", "보상률", "검수등급", "발생금액(A)")
_AMOUNT_PREF = (("최종비용(A-B-C)", "최종비용"), ("할인적용가(A-B)",), ("할인적용금액(A-B-C)",), ("보상금액",))
_KEY_COLS = ("정산유형", "거래유형", "주문ID", "배송ID", "반출ID", "입고ID", "요청ID", "리뷰ID", "이벤트ID", "검수번호",
             "옵션ID", "SKUID", "진열일", "발생일", "발생일(배송완료일)", "발생일(입고완료일)")
_OCCUR = ("발생일", "발생일(배송완료일)", "발생일(입고완료일)")
_ACCOUNT_SHEETS = ("반출배송서비스비리포트",)
_INFO_SHEETS = ("자동반출",)


def ymd(s: str) -> str:
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def _summary(g: list) -> tuple[int, list] | None:
    for i, r in enumerate(g[:6]):
        c = [nm(x) for x in r]
        if c and c[0] == "정산주기(종료일)" and "최종비용" in c and i + 1 < len(g):
            return i, c
    return None


def _header(g: list) -> tuple[int, list[str], int] | None:
    """(머리글 줄, 칸 이름 '위/아래', 자료 시작 줄) · 못 찾으면 None."""
    for i, r in enumerate(g[:12]):
        c = [nm(x) for x in r]
        if c and c[0] == "정산주기(종료일)" and "최종비용" in c:
            continue
        if ({"옵션ID", "반출ID", "리뷰ID"} & set(c)) and ({"정산주기(종료일)", "발생일"} & set(c)):
            sub = [nm(x) for x in g[i + 1]] if i + 1 < len(g) else []
            is_sub = any(s in _SUB for s in sub)
            cols, last = [], ""
            for j in range(max(len(c), len(sub))):
                t = c[j] if j < len(c) else ""
                s = sub[j] if (is_sub and j < len(sub)) else ""
                last = t or last
                cols.append(f"{last}/{s}" if s else t)
            return i, cols, i + (2 if is_sub else 1)
    return None


def _amount_col(cols: list[str]) -> int:
    for names in _AMOUNT_PREF:
        for j, c in enumerate(cols):
            if c.rsplit("/", 1)[-1] in names:
                return j
    return -1


class CostLoader:
    def __init__(self, con: sqlite3.Connection, reg: Registry):
        self.con, self.reg = con, reg

    def run(self, base: Path) -> None:
        for p in sorted(Path(base).glob("*.xlsx")):
            m = NAME.match(p.name)
            if not m:
                self.reg.add(p, "비용 리포트(이름 규칙 밖)", None, status="생략", note="이름 규칙 밖 — 읽지 않음")
                continue
            acc = account_id(m["acc"])
            fid = self.reg.add(p, f"로켓그로스 비용 {m['rep']}", acc)
            if fid is None:
                continue
            try:
                self._file(p, fid, acc, m)
            except Exception as exc:
                self.reg.fail(fid, f"{type(exc).__name__}: {exc}")
        self.reg.flush()

    def _file(self, p: Path, fid: int, acc: str, m: re.Match) -> None:
        stage, sd = m["kind"], ymd(m["sd"])
        read = loaded = 0
        for sheet, g in SF.read_sheets(p).items():
            key = nm(sheet)
            if key.startswith(_INFO_SHEETS):
                n_info = max(len(g) - 1, 0)
                self.reg.skip(fid, f"금액 없는 안내 시트({sheet})", n_info)
                read += n_info
                continue
            self._summary_rows(g, fid, acc, sheet)
            h = _header(g)
            if h is None:
                self.reg.skip(fid, f"머리글 없음({sheet})", 1)
                read += 1
                continue
            r0, cols, start = h
            ix = {c: j for j, c in enumerate(cols) if c and c not in ()}
            aj = _amount_col(cols)
            if aj < 0:
                raise ValueError(f"{sheet} 금액 칸을 찾지 못함")
            for n, r in enumerate(g[start:], start=start + 1):
                if blank(r):
                    continue
                read += 1
                where = f"{p.name} {sheet} {n}행"
                loaded += self._row(r, ix, aj, acc, sheet, key, stage, sd, fid, n, where)
        self.reg.done(fid, read, loaded)
        self.con.commit()

    def _summary_rows(self, g: list, fid: int, acc: str, sheet: str) -> None:
        s = _summary(g)
        if s is None:
            return
        i, c = s
        v = g[i + 1]
        cyc = d10(v[0])
        val = {name: won(v[j] if j < len(v) else None, f"{sheet} 요약") for j, name in enumerate(c)
               if name and name != "정산주기(종료일)"}
        tax = next((val[k] for k in val if k == "세액"), 0)
        rk = f"cycle:{cyc}"
        self.con.execute("INSERT INTO account_entry(account_id, sale_type, round_key, item, role, amount, link_key, "
                         "occur_date, file_id, src_pos) VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (acc, "로켓그로스", rk, f"비용 세액 {sheet}", "지급 구성", -tax, "", cyc, fid, f"{sheet}!{i + 2}"))
        self.con.execute("INSERT INTO account_entry(account_id, sale_type, round_key, item, role, amount, link_key, "
                         "occur_date, file_id, src_pos) VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (acc, "로켓그로스", rk, f"비용 요약 최종비용 {sheet}", "대조용", -val.get("최종비용", 0), "", cyc,
                          fid, f"{sheet}!{i + 2}"))

    def _row(self, r: list, ix: dict, aj: int, acc: str, sheet: str, key: str, stage: str, sd: str,
             fid: int, n: int, where: str) -> int:
        def get(name: str):
            j = ix.get(name)
            return r[j] if j is not None and j < len(r) else None
        amt = won(r[aj] if aj < len(r) else None, where)
        cyc = d10(get("정산주기(종료일)"))
        occur = next((d10(get(c)) for c in _OCCUR if get(c) not in (None, "")), "")
        if key in _ACCOUNT_SHEETS:
            self.con.execute("INSERT INTO account_entry(account_id, sale_type, round_key, item, role, amount, link_key, "
                             "occur_date, file_id, src_pos) VALUES (?,?,?,?,?,?,?,?,?,?)",
                             (acc, "로켓그로스", f"cycle:{cyc}", sheet, "지급 구성", -amt, nid(get("반출ID")), occur, fid,
                              f"{sheet}!{n}"))
            return 1
        sign = 1 if "보상" in sheet else -1
        nat = "|".join(f"{c}={nid(get(c)) if 'ID' in c or c == '검수번호' else d10(get(c)) if '일' in c else get(c)}"
                       for c in _KEY_COLS if c in ix)
        self.con.execute(
            "INSERT INTO product_cost(account_id, kind, nat_key, option_id, inventory_id, order_no, txn_type, occur_date, "
            "cycle_end, settle_type, amount, sign, file_stage, settle_date, file_id, sheet, src_row) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (acc, sheet, nat, nid(get("옵션ID")), nid(get("등록상품ID")), nid(get("주문ID")),
             str(get("거래유형") or "").strip(), occur, cyc, str(get("정산유형") or "").strip(), sign * amt, sign,
             stage, sd, fid, sheet, n))
        return 1


def load(con: sqlite3.Connection, reg: Registry, settle_dir: Path) -> None:
    CostLoader(con, reg).run(Path(settle_dir) / "파일" / "비용")
