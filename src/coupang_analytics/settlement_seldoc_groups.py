"""셀독 정산서 — 계약이 여럿인 계정의 계약별 상품군 위탁정산서(D-152 ⑤ · D-155 ①). T-25 4단계.

D-155 ① 원문 규칙: 상품군 실지급 = 정산서와 같은 규칙으로 범위만 상품군으로 바꿔 직접 합산 · 관리 시작 달은 계정 전체 값으로 고정.
→ 위탁정산서 계산(`settlement_statement_deduct.Account`)을 그대로 쓰고, 관리 상품 판정(`is_mv`·`mpids`)만 판정표의 그 계약 상품으로
좁히며 관리 시작 달(start·fs)은 계정 전체 계산 값으로 고정한다. 결과는 위탁정산서와 같은 모양의 파일(`book`)로 써서
셀독 정산서가 위탁정산서 결과 파일만 읽게 한다(D-225 ①). 위탁정산서 계산 코드 자체는 바꾸지 않음.

상품 → 계약 = 판정표(`셀독_계약상품군_판정.json` '상품' · 등록상품ID 단위 · AI 판정 · 근거 원문 · D-229). 판정 없는 관리 상품·
등록상품을 못 찾는 관리 VID = SeldocInputError(그 계정만 못 만듦 · fallback 없음 · D-399 계정별 격리).
"""
from __future__ import annotations

from pathlib import Path

from coupang_analytics import settlement_statement_context as CTX
from coupang_analytics import settlement_statement_scope as SCOPE
from coupang_analytics import settlement_statement_source as SRC
from coupang_analytics.settlement_seldoc_source import ProductError, SeldocInputError
from coupang_analytics.settlement_statement_book import book
from coupang_analytics.settlement_statement_deduct import Account


def group_path(folder: Path, aid: str, doc_id: str) -> Path:
    """계약별 상품군 위탁정산서 파일 이름(셀독 정산서가 이 이름으로 찾음)."""
    return folder / f"정산서_{aid}_계약_{doc_id}.xlsx"


def assign(managed: set, judged: dict, docs: list) -> dict:
    """관리 등록상품ID → {문서ID: {등록상품ID}} (판정표대로 · 판정 없거나 이 계정 계약이 아닌 문서ID = 중단 · 문제 상품 전부를 한 번에 알림)."""
    out: dict = {d: set() for d in docs}
    bad = []
    for pid in sorted(managed):
        j = judged.get(pid) or {}
        doc = j.get("문서ID")
        if doc in out:
            out[doc].add(pid)
            continue
        if j.get("결정대기"):
            why = f"확인 필요 — 소유자 결정 대기({j['결정대기']})"
        elif j.get("판정") == "확인 필요" and j.get("사유"):
            why = f"확인 필요 — {j['사유']}"                      # 예: 관리대장에 없음(오류) — 소유자 11-24
        else:
            why = "판정 없음" if doc is None else f"문서ID {doc} = 이 계정 대상 계약 아님"
        amt = j.get("판매금액")
        bad.append((pid, why, j.get("상품명"), amt if isinstance(amt, (int, float)) and not isinstance(amt, bool) else None))
    if bad:
        raise ProductError("시작 전 중단 — " + " · ".join(f"관리 상품 {pid} 상품군 {why}" for pid, why, *_ in bad), bad)
    return out


def group_filter(base, vid2pid: dict, pids: set, unmapped: set):
    """관리 VID 판정 = 원래 판정(base) AND 그 VID 의 등록상품이 이 계약 상품군 · 등록상품을 모르는 관리 VID = unmapped 에 기록."""
    def f(v) -> bool:
        if not base(v):
            return False
        p = vid2pid.get(str(v))
        if p is None:
            unmapped.add(str(v))
            return False
        return p in pids
    return f


def vid_pids(opt2pid: dict, inv: dict, periods: dict) -> dict:
    """VID → 등록상품ID — 정산 원본 옵션 > 상품조회 > 판매분석(앞이 우선)."""
    out: dict = {}
    for pid, g in SCOPE.sales_groups(periods).items():
        out.update({v: pid for v in g["vids"]})
    for pid, x in inv.items():
        out.update({str(v): pid for v in x["types"]})
    out.update(opt2pid)
    return out


def managed_pids(mpids: set, vp: dict, is_mv, extra_vids=()) -> set:
    """판정해야 할 관리 등록상품 = 정산 원본에서 찾은 관리 등록상품 + 관리 VID 의 등록상품(정산 중 달 판매분석에만 있는 상품 포함)."""
    return set(mpids) | {vp[v] for v in set(vp) | set(extra_vids) if v in vp and is_mv(v)}


class GroupAccount(Account):
    """계정 하나의 계약 상품군 몫 — 위탁정산서 계산 그대로 · 관리 상품만 상품군으로 · 관리 시작 달 고정."""

    def __init__(self, ctx, acct: str, pids: set, base: Account, inv: dict):
        super().__init__(ctx, acct)
        self.g_pids, self.g_base, self.g_inv = pids, base, inv
        self.unmapped: set = set()
        self._gf = None

    def is_mv(self, v: str) -> bool:
        return self._gf(v) if self._gf is not None else Account.is_mv(self, v)

    def _scope(self) -> None:
        super()._scope()
        vp = vid_pids(self.opt2pid, self.g_inv, self.ctx.periods.get(self.aid) or {})
        self._gf = group_filter(lambda v: Account.is_mv(self, v), vp, self.g_pids, self.unmapped)
        self.mpids = {p for p in self.mpids if p in self.g_pids}

    def _start(self) -> None:
        super()._start()
        b = self.g_base
        self.start, self.fs, self.start_note, self.active = b.start, b.fs, b.start_note, b.active


def _base(ctx, acct: str) -> Account:
    b = Account(ctx, acct)
    b.result = b.run()
    return b


def _account(ctx, acct: str, docs: list, judged: dict, inv: dict, out_dir: Path, held=(), on_log=print) -> list:
    """계정 하나 — 계정 전체 계산(관리 시작 달) → 판정표대로 상품군 → 계약마다 상품군 위탁정산서.
    held = 아직 못 만드는 같은 계정 계약(상품 배정에만 씀 · 파일 안 만듦) · 모두 계산해 맞는지 본 뒤에만 파일을 씀."""
    base = _base(ctx, acct)
    vp = vid_pids(base.opt2pid, inv, ctx.periods.get(base.aid) or {})
    all_docs = list(docs) + [d for d in held if d not in docs]
    groups = assign(managed_pids(base.result["mpids"], vp, lambda v: Account.is_mv(base, v), base.vids), judged, all_docs)
    done = []
    for doc in docs:
        g = GroupAccount(ctx, acct, groups[doc], base, inv)
        a = g.run()
        if g.unmapped:
            raise SeldocInputError(f"시작 전 중단 — {base.aid} 등록상품을 못 찾는 관리 VID {sorted(g.unmapped)}")
        done.append((doc, a))
    made = []
    for doc, a in done:
        dest = group_path(out_dir, base.aid, doc)
        book(ctx, a, dest)
        made.append((base.aid, doc, dest, round(a["pay_m"])))
    total, whole = sum(x[3] for x in made), round(base.result["pay_m"])
    rest = f" · 못 만든 같은 계정 계약 {len(all_docs) - len(docs)}개" if len(all_docs) > len(docs) else ""
    on_log(f"{base.aid} 상품군 {len(made)}개 G 합 {total:,} · 계정 G {whole:,} · 차이 {total - whole:,}{rest}")
    return made


def _failed(exc: Exception) -> str:
    return str(exc).removeprefix("시작 전 중단 — ") if isinstance(exc, SeldocInputError) else f"{type(exc).__name__}: {exc}"


def run(args: CTX.StatementArgs, jobs: list, judge: dict, out_dir: Path, held: dict | None = None, on_log=print) -> tuple[list, dict]:
    """계약이 여럿인 계정(Job.split)마다 계약별 상품군 위탁정산서 → ([(계정ID, 문서ID, 경로, G)], {계정ID: {"reason", "products"}}).
    계정별 격리(D-399) — 한 계정이 막혀도 다른 계정은 만든다 · held = {계정ID: [미확정 같은 계정 문서ID]}(상품 배정에만)."""
    split = [j for j in jobs if j.split]
    aids = list(dict.fromkeys(j.aid for j in split))
    if not aids:
        return [], {}
    try:
        ctx = CTX.load(args)
        inv = SCOPE.inventory(args.managed_output)
    except (FileNotFoundError, SeldocInputError) as exc:
        return [], {aid: {"reason": f"상품군 정산서 입력을 못 읽음 — {exc}", "products": []} for aid in aids}
    accts = {SRC.aid_of(a): a for a in ctx.accts}
    out, failed = [], {}
    for aid in aids:
        try:
            if aid not in accts:
                raise SeldocInputError(f"{aid} 정산 자료 없음")
            out += _account(ctx, accts[aid], [j.contract.doc_id for j in split if j.aid == aid], _products(judge, aid),
                            inv.get(aid) or {}, out_dir, (held or {}).get(aid, ()), on_log)
        except Exception as exc:                                    # 계정 하나의 계산 오류 = 그 계정만 못 만듦(사유를 보고 · 삼키지 않음)
            failed[aid] = {"reason": _failed(exc), "products": getattr(exc, "items", [])}
            on_log(f"❌ {aid} 상품군 정산서 못 만듦 — {failed[aid]['reason']}")
    return out, failed


def _products(judge: dict, aid: str) -> dict:
    return (judge.get("상품") or {}).get(aid) or {}
