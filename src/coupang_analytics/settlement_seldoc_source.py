"""셀독 정산서 입력 읽기 — 위탁정산서 결과 파일 · 계약서 분석 DB · 셀독 입력 폴더(사업자 대응표 + 계약·상품군 판정표). T-25 4단계.

- D-225 ① 쿠팡 판매·정산 숫자 = 위탁정산서 결과 파일에서만(따로 받거나 계산하지 않음) ② 계약 내용 = 계약서 분석 DB 값 그대로 ③ 없으면 없는 대로.
- 대상 계약 = DB '계약유형(소)' 규칙(TARGET_TYPES 대상 · EXCLUDE_WORDS 제외 · 그 밖 = 규칙 밖 → 중단) + 계약자↔계정 판정표(D-229 · AI 판정 · 근거 원문).
  후보 = 계약자 명칭·대표가 계정 사업자·대표자와 이름 글자로 같은 계약(같은 사람인지는 판정표가 정함).
- 판정표 없음·판정 없는 대상 계약·DB 에 없는 계약 = SeldocInputError(시작 전 중단 · fallback 없음).
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

from coupang_analytics.settlement_scope_judge import _norm
from coupang_analytics.settlement_statement_context import MAP_CSV
from coupang_analytics.settlement_statement_sheets import SHIP_LABEL

JUDGE = "셀독_계약상품군_판정.json"
TARGET_TYPES = ("셀독 상품공급 OEM", "보냉백 OEM 생산공급")        # 준비 문서 3절 규칙 — 대상
EXCLUDE_WORDS = ("제로리스크", "제로셀", "투자", "위임")             # 같은 규칙 — 제외
G_LABEL, EXTRA_PREFIX, HOLD_LABEL = "G 최종 지급액", "쿠팡 별도 보상 — ", "입금 보류"
BOOK_LABELS = (G_LABEL, EXTRA_PREFIX, "입금 ", "월별 판매", "상품별 판매", "계산 근거", "판매 기간", "쿠팡 계정")


class SeldocInputError(Exception):
    """입력이 모자라거나 맞지 않음 — 셀독 정산서를 만들지 않는다(시작 전 중단)."""


def _int(v) -> int:
    return round(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


# ── 규칙 ──
def contract_kind(kind: str) -> str:
    """'대상' | '제외' | '규칙 밖'."""
    k = str(kind or "").strip()
    if k in TARGET_TYPES:
        return "대상"
    return "제외" if any(w in k for w in EXCLUDE_WORDS) else "규칙 밖"


def goal_total(amount: int, profit: int | None) -> int:
    """목표 정산 총액 = 계약금액 + 목표수익금(빈 칸 = 0 · D-221 ①·D-225 ③)."""
    return amount + (profit or 0)


def reach(result: int, amount: int, profit: int | None) -> float:
    """목표 도달율 = 정산 기준 실적 ÷ (계약금액 + 목표수익금) (D-221 ①)."""
    total = goal_total(amount, profit)
    return result / total if total else 0.0


# ── 계약서 분석 DB ──
@dataclass
class Contract:
    doc_id: str
    kind: str
    signed: str
    end: str
    amount: int
    profit: int | None
    rate: float | None
    title: str
    party: str
    rep: str
    company: str
    items: list = field(default_factory=list)       # [(품목명(원문), 단가|None, 수량|None)]


def _num_or_none(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _rows(ws) -> tuple[dict, list]:
    it = ws.iter_rows(values_only=True)
    return {str(c): k for k, c in enumerate(next(it)) if c is not None}, list(it)


def load_contracts(db: Path) -> dict:
    """DB '계약 통합'·'품목' → {문서ID: Contract} (읽기만 · 문서ID 는 글자 전체가 같아야 같은 계약)."""
    wb = openpyxl.load_workbook(db, read_only=True, data_only=True)
    h, rows = _rows(wb["계약 통합"])
    ih, irows = _rows(wb["품목"])
    wb.close()
    out: dict = {}
    for r in rows:
        def g(k: str):
            return r[h[k]] if k in h else None
        doc = str(g("문서ID(누르면 원문 PDF)") or "")
        if doc:
            out[doc] = Contract(doc, str(g("계약유형(소)") or ""), str(g("계약일(서명일)") or "")[:10], str(g("계약종료일") or "")[:10],
                                _int(g("계약금액(원금)")), _num_or_none(g("수익금")), _num_or_none(g("수익률(%)")),
                                str(g("문서제목(원문)") or ""), str(g("계약자 명칭") or ""), str(g("계약자 대표") or ""), str(g("회사측 명칭") or ""))
    for r in irows:
        c = out.get(str(r[ih["문서ID"]] or ""))
        if c is not None:
            c.items.append((str(r[ih["품목명(원문)"]] or ""), _num_or_none(r[ih["단가"]]), _num_or_none(r[ih["수량"]])))
    return out


# ── 셀독 입력 폴더 ──
def load_people(inputs: Path) -> dict:
    """사업자_대응표.csv → {계정ID: (사업자, 대표자)}."""
    p = inputs / MAP_CSV
    if not p.is_file():
        raise SeldocInputError(f"시작 전 중단 — {p} 없음")
    with open(p, encoding="utf-8-sig", newline="") as f:
        return {r["계정ID"].strip(): (r["사업자"].strip(), r["대표자"].strip()) for r in csv.DictReader(f) if r.get("계정ID")}


def load_judge(inputs: Path) -> dict:
    p = inputs / JUDGE
    if not p.is_file():
        raise SeldocInputError(f"시작 전 중단 — 판정표 {p} 없음")
    j = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(j.get("계약"), dict):
        raise SeldocInputError(f"시작 전 중단 — 판정표 {p} 에 '계약' 없음")
    return j


@dataclass
class Job:
    aid: str
    contract: Contract
    split: bool              # 계정의 대상 계약이 여럿 = 상품군 정산서(D-155)
    people: tuple            # (사업자, 대표자)


def candidates(contracts: dict, people: tuple) -> list:
    keys = {_norm(x) for x in people if _norm(x)}
    return [c for c in contracts.values() if keys & ({_norm(c.party), _norm(c.rep)} - {""})]


def _from_candidates(aid: str, people: tuple, contracts: dict, judged: dict) -> list:
    """이름이 같은 후보 중 규칙 '대상' + 판정표 '이 계정·대상' · 규칙 밖 유형·판정 없는 대상 계약 = 중단."""
    picked = []
    for c in candidates(contracts, people):
        kind = contract_kind(c.kind)
        if kind == "규칙 밖":
            raise SeldocInputError(f"시작 전 중단 — {aid} 후보 계약 {c.doc_id} 유형 '{c.kind}' = 대상 규칙 밖")
        if kind != "대상":
            continue
        j = judged.get(c.doc_id)
        if j is None:
            raise SeldocInputError(f"시작 전 중단 — {aid} 대상 계약 {c.doc_id}({c.signed} {c.kind}) 판정 없음")
        if j.get("계정ID") == aid and j.get("판정") == "대상":
            picked.append(c)
    return picked


def _from_judge(aid: str, contracts: dict, judged: dict) -> list:
    """판정표가 이 계정 대상으로 둔 계약 — DB 에 없음·대상 유형 아님 = 중단."""
    out = []
    for doc, j in judged.items():
        if j.get("계정ID") != aid or j.get("판정") != "대상":
            continue
        if doc not in contracts:
            raise SeldocInputError(f"시작 전 중단 — {aid} 판정표 계약 {doc} 계약 못 찾음(DB 에 없음)")
        if contract_kind(contracts[doc].kind) != "대상":
            raise SeldocInputError(f"시작 전 중단 — {aid} 판정표 계약 {doc} 유형 '{contracts[doc].kind}' = 대상 유형 아님")
        out.append(contracts[doc])
    return out


def _account_jobs(aid: str, people: tuple, contracts: dict, judged: dict) -> list:
    picked = _from_candidates(aid, people, contracts, judged)
    picked += [c for c in _from_judge(aid, contracts, judged) if c not in picked]
    if not picked:
        raise SeldocInputError(f"시작 전 중단 — {aid} 대상 계약 없음")
    picked.sort(key=lambda c: (c.signed, c.doc_id))
    return [Job(aid, c, len(picked) > 1, people) for c in picked]


def plan(people: dict, contracts: dict, judge: dict, aids: list) -> list:
    """계정마다 대상 계약 → [Job] (계정 순서 · 계약일 순)."""
    jobs = []
    for aid in aids:
        if aid not in people:
            raise SeldocInputError(f"시작 전 중단 — {aid} 가 사업자 대응표에 없음")
        jobs += _account_jobs(aid, people[aid], contracts, judge["계약"])
    return jobs


# ── 위탁정산서 결과 파일 ──
@dataclass
class Perf:
    label: str               # 사업자 (대표 …)
    aid: str
    period: str              # 판매 기간(첫 줄)
    done: int                # 입금 완료
    due: int                 # 입금 예정(보류 뺀 값)
    hold: int                # 보류
    total: int               # G 최종 지급액
    extras: list             # [(보상 내용, 원)] — 쿠팡 별도 보상
    months: list             # [(판매 월, 판매금액, 상태)]
    products: list           # [(상품명, 수량, 판매금액)] — 정산 끝난 판매 · 같은 상품명 합침 · 배송비 줄 뺌

    @property
    def result(self) -> int:
        """정산 기준 실적 = 입금 완료 + 입금 예정 + 보류 + 보상(D-152 ⑥ · D-224)."""
        return self.done + self.due + self.hold + sum(x for _, x in self.extras)

    @property
    def sales(self) -> int:
        return sum(m[1] for m in self.months)

    @property
    def qty(self) -> int:
        return sum(p[1] for p in self.products)


def _table(ws) -> list:
    """표 시트(머리 4행) → 5행부터 '합계' 앞까지."""
    out = []
    for r in ws.iter_rows(min_row=5, values_only=True):
        if r[0] in (None, "합계"):
            break
        out.append(r)
    return out


def _head(ws) -> tuple[dict, list, tuple]:
    info, extras, g = {}, [], None
    for r in ws.iter_rows(min_col=2, max_col=5, values_only=True):
        k = str(r[0] or "")
        if k in ("사업자", "쿠팡 계정", "판매 기간") and k not in info:
            info[k] = str(r[1] or "")
        elif k == G_LABEL and isinstance(r[1], (int, float)):
            g = (_int(r[1]), _int(r[2]), _int(r[3]))
        elif k.startswith(EXTRA_PREFIX):
            extras.append((k[len(EXTRA_PREFIX):], _int(r[1])))
    if g is None or len(info) < 3:
        raise SeldocInputError(f"위탁정산서 모양이 다름 — '{G_LABEL}' 줄 또는 사업자·쿠팡 계정·판매 기간 칸 없음")
    return info, extras, g


def _products(ws) -> list:
    acc: dict = {}
    for name, q, amt, *_ in _table(ws):
        if name != SHIP_LABEL:
            e = acc.setdefault(str(name), [0, 0])
            e[0] += _int(q)
            e[1] += _int(amt)
    return sorted(((n, q, a) for n, (q, a) in acc.items()), key=lambda x: -x[2])


def read_statement(path: Path) -> Perf:
    """위탁정산서 결과 파일 → Perf. G 줄의 칸 합 ≠ G 이면 SeldocInputError."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        info, extras, (done, due_hold, total) = _head(wb["정산서"])
        hold = next((_int(r[3]) for r in wb["계산 근거"].iter_rows(min_row=5, values_only=True) if r[0] == HOLD_LABEL), None)
        months = [(str(r[0]), _int(r[1]), str(r[3] or "").split("(")[0]) for r in _table(wb["월별 판매"])]
        products = _products(wb["상품별 판매"])
    finally:
        wb.close()
    if done + due_hold != total:
        raise SeldocInputError(f"{path.name}: G 입금 완료 {done:,} + 입금 예정 {due_hold:,} ≠ G {total:,}")
    if hold is None:
        raise SeldocInputError(f"{path.name}: '계산 근거' 시트에 '{HOLD_LABEL}' 줄 없음")
    return Perf(info["사업자"], info["쿠팡 계정"], info["판매 기간"].split("\n")[0].strip(), done, due_hold - hold, hold, total,
                extras, months, products)
