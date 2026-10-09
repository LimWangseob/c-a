"""관리대장 상품명 ↔ 쿠팡 등록상품 **AI 중심 매칭**(D-009·소유자 2026-10-09).

배경: 대장 상품명은 담당자 약칭(예 '크리스마스트리 R060 (골드)')이고 쿠팡 등록명은 다르게 적힌 경우가 많아
(같은 상품의 WING 등록명 '크리스마스 미니트리') 글자 규칙만으로는 놓친다. 대장 상품은 95% 이상 그 계정에
등록된 상품이므로, **의미까지 보는 AI 가 후보 중 가장 같은 상품을 고르게** 한다.

순서(대장 줄마다):
  ① **고정(앵커)** — 이전에 확정된 VID 가 지금도 쿠팡에 있으면 그대로(AI 호출 없음·날마다 같은 결과).
  ② **괄호/이름 정확일치** — 공백 무시 완전 일치면 확정(AI 불필요).
  ③ **AI 선택** — 줄마다 비슷한 후보를 추려(shortlist) 등록명·노출명·옵션·판매상태와 함께 보내고 하나를 고르게 한다.
     글자 규칙(product_match._assign) 결과는 **참고 후보**로만 준다.
  ④ AI 호출 실패 시에만 글자 규칙 결과로 대체(로그 명시·고정 안 함).
  → 마지막에 **색상 필터를 모든 경로에 공통 적용**(product_match.build_tracked).
고정 저장: 정확일치·AI 확신 high/medium 만(낮은 확신 low 는 매칭은 하되 다음 날 다시 판단).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .input_list import Option, Product
from .match_anchor import key_of
from .product_match import _assign, _base_name, _merge_same_name, _norm, _paren, _title

SHORTLIST_K = 12          # 줄당 AI 에 보낼 후보 수(대형 계정 2천여 상품 → 비슷한 것만)
SEND_ALL_MAX = 30         # 계정 후보가 이 이하면 추리지 않고 전부 보냄(작은 계정 = 맥락 최대)
ANCHOR_CONF = ("high", "medium")

MATCH_SYSTEM = (
    "너는 쿠팡 판매자 계정의 '관리대장 상품명'을 그 계정에 실제 등록된 '쿠팡 상품 후보' 중 하나와 연결한다.\n"
    "배경:\n"
    "- 관리대장 상품은 95% 이상 이 계정에 이미 등록된 상품이다. 그러니 **가장 같은 상품으로 보이는 후보를 고른다**. "
    "후보 중 같은 종류의 상품이 하나도 없을 때만 null.\n"
    "- 대장명 = 담당자가 쓴 약칭 + 모델코드 + (괄호). 괄호에는 ①쿠팡 등록명/노출명 ②색상·옵션(골드·블랙) "
    "③메모(대체요망·판매부진) 중 하나가 들어간다. 이름이 두 개 적혀 있으면(본문 + 괄호) 둘 다 근거로 쓴다.\n"
    "- 후보 = 등록명(판매자가 WING 에 입력한 이름) | 노출명(고객이 보는 제목, 있으면) | 옵션 | 판매상태.\n"
    "판단 규칙(중요한 순):\n"
    "1. 모델코드(영문+숫자 예 ST6645·R601·DYM046)가 후보 이름·옵션에 있으면 가장 강한 근거. 한두 글자 다른 코드"
    "(HS0300↔HS0030)는 같은 상품일 수 있다 — 상품 정체가 같으면 같은 상품으로 본다.\n"
    "2. 상품의 정체(무엇인가: 트리·풍선세트·청소기·마사지기·영양제 성분)가 같아야 한다. 띄어쓰기·오타(마시지기=마사지기)·"
    "약칭(목견인기=거북목 교정기 견인기)·브랜드 유무(디프·웰빙곳간)·꾸밈말(프리미엄·MAX)은 무시한다.\n"
    "3. 괄호 속 색상·옵션은 상품을 고르는 근거가 아니다(옵션 구분용). 단 같은 정체 후보가 여럿이면 그 색상 옵션이 있는 후보를 고른다.\n"
    "4. 같은 정체 후보가 여럿이면 수량·용량(120정·30포·4개)이 대장과 맞는 것 > 판매중 > 판매중지 순으로 고른다.\n"
    "5. '규칙 후보'는 글자 비교 프로그램의 추정일 뿐이다. 참고만 하고 틀렸으면 무시한다.\n"
    "6. 색상만 다른 대장 줄들(예 '타프 (블랙)'·'타프 (베이지)')은 같은 후보를 골라도 된다. 그 밖에는 한 후보를 두 줄에 쓰지 않는다.\n"
    "예시: '크리스마스트리 R060 (골드)' → 등록명 '크리스마스 미니트리'(옵션 골드 Free) = 같은 상품(트리). "
    "'크리스마스 풍선세트 (골드)' → '크리스마스풍선세트 (골드)' = 같은 상품(트리 아님). "
    "'코골이 방지 기구(' → '코골이 방지 비강확장기 숨통박사 자석 코골이 완화 기구 패치' = 같은 상품. "
    "'EMS고주파마시지기 DYM046' → '고주파마사지기 DYM046' = 같은 상품(오타).\n"
    "confidence: high=코드나 이름이 사실상 같음 · medium=정체가 같고 근거 충분 · low=가장 가깝지만 확신 부족.\n"
    '반드시 JSON 객체로만 답한다: {"matches":[{"line":줄번호,"pick":"C번호" 또는 null,'
    '"confidence":"high|medium|low","reason":"20자 이내"}]} — 받은 모든 줄에 답한다.'
)


@dataclass
class Pick:
    di: int                  # 후보(discovered) 위치(대표)
    how: str                 # anchor | anchor-snapshot | exact | ai | rule
    conf: str = ""           # AI 확신(high/medium/low) — anchor/exact 는 high
    reason: str = ""
    extra: list[int] = field(default_factory=list)   # 같은 이름 판매중 리스팅(동명 병합·별도 블록, 2026-09-29 유지)


@dataclass
class MatchOutcome:
    picks: dict[int, Pick] = field(default_factory=dict)      # 대장i → Pick
    candidates: list[Product] = field(default_factory=list)  # discovered (+앵커 스냅샷 복원분)
    anchors: dict[str, dict] = field(default_factory=dict)   # 저장할 앵커(대장명키 → 기록)
    notes: list[str] = field(default_factory=list)           # 로그 문장


# ── 후보 추리기(shortlist) ────────────────────────────────────────
def _bigrams(s: str) -> set[str]:
    t = _norm(s)
    return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) > 1 else ({t} if t else set())


def _codes(s: str) -> set[str]:
    return {m.lower() for m in re.findall(r"[A-Za-z]{1,5}-?\d{2,}[A-Za-z0-9]*", str(s))}


def _line_texts(lp: Product) -> list[str]:
    body = re.sub(r"[（(][^)）]*[)）]?", " ", lp.name).strip()
    return [t for t in (lp.name, body, _paren(lp.name)) if t]


def _cand_text(d: Product, expo: dict) -> str:
    names = [_title(d)] + sorted({expo[v] for o in d.options for v in o.vendor_item_ids if v in expo})
    return " ".join(names + [o.label for o in d.options if o.label])


def similarity(lp: Product, d: Product, expo: dict) -> float:
    """대장 줄 ↔ 후보 유사도(0~): 글자쌍(bigram) 대장 기준 포함률 최대값 + 모델코드 일치 가산."""
    ctext = _cand_text(d, expo)
    cb = _bigrams(ctext)
    best = 0.0
    for t in _line_texts(lp):
        lb = _bigrams(t)
        if lb:
            best = max(best, len(lb & cb) / len(lb))
    if _codes(lp.name) & _codes(ctext):
        best += 0.5
    return best


def shortlist(lp: Product, cands: list[int], discovered: list[Product], expo: dict, k: int = SHORTLIST_K) -> list[int]:
    return sorted(cands, key=lambda di: -similarity(lp, discovered[di], expo))[:k]


# ── AI 요청/응답 ─────────────────────────────────────────────────
def _status(d: Product) -> str:
    return d.sale_status or "상태미상"


def build_request(ledger: list[Product], lines: list[int], cand_ids: list[int], discovered: list[Product],
                  expo: dict, hints: dict[int, int]) -> str:
    """AI 사용자 메시지 — 대장 줄(번호 L)과 후보(번호 C, 계정 내 위치 di). 규칙 후보는 C번호로 참고 표기."""
    cno = {di: f"C{di}" for di in cand_ids}
    lines_txt = []
    for li in lines:
        hint = f"  [규칙 후보: {cno[hints[li]]}]" if hints.get(li) in cno else ""
        lines_txt.append(f"L{li}. {ledger[li].name}{hint}")
    cand_txt = []
    for di in cand_ids:
        d = discovered[di]
        ex = sorted({expo[v] for o in d.options for v in o.vendor_item_ids if v in expo} - {_title(d)})
        opts = ", ".join(o.label for o in d.options if o.label)[:120]
        cand_txt.append(f"{cno[di]}. 등록명: {_title(d)}" + (f" | 노출명: {ex[0]}" if ex else "")
                        + (f" | 옵션: {opts}" if opts else "") + f" | {_status(d)}")
    return ("[관리대장 줄]\n" + "\n".join(lines_txt) + "\n\n[쿠팡 상품 후보]\n" + "\n".join(cand_txt)
            + "\n\n각 대장 줄에 가장 같은 상품 후보를 골라라.")


def parse_response(obj: dict, lines: list[int], cand_ids: list[int]) -> dict[int, Pick]:
    """AI JSON → {대장i: Pick}. 범위 밖 번호·형식 오류는 버린다(잘못된 응답 방어)."""
    ok_l, ok_c = set(lines), set(cand_ids)
    out: dict[int, Pick] = {}
    for m in (obj.get("matches") or []):
        if not isinstance(m, dict):
            continue
        try:
            li = int(str(m.get("line", "")).lstrip("Ll"))
        except ValueError:
            continue
        pick = m.get("pick")
        if li not in ok_l or pick in (None, "", "null"):
            continue
        try:
            di = int(str(pick).lstrip("Cc"))
        except ValueError:
            continue
        conf = str(m.get("confidence") or "low").lower()
        if di in ok_c:
            out[li] = Pick(di, "ai", conf if conf in ("high", "medium", "low") else "low",
                           str(m.get("reason") or "")[:40])
    return out


# ── 메인 ─────────────────────────────────────────────────────────
def _vids(p: Product) -> set[str]:
    return {v for o in p.options for v in o.vendor_item_ids if v}


def _snapshot(rec: dict) -> Product:
    """앵커 기록 → 후보 Product(상품조회 실패일에 VID 유지용)."""
    opts = [Option(str(o[0]), list(o[1]), list(o[2]) if len(o) > 2 else []) for o in rec.get("options") or []]
    return Product(name=rec.get("title", ""), title=rec.get("title", ""), kind=rec.get("kind", ""),
                   options=opts or [Option("", list(rec.get("vids") or []))])


def _anchor_record(d: Product, pk: Pick, today: str) -> dict:
    return {"vids": sorted(_vids(d)), "title": _title(d), "kind": d.kind,
            "options": [[o.label, list(o.vendor_item_ids), list(o.product_ids)] for o in d.options],
            "how": pk.how, "conf": pk.conf or "high", "at": today}


def _apply_anchors(ledger, discovered, anchors, vendor_ok, out: MatchOutcome) -> set[int]:
    """① 고정 — 앵커 VID 를 담은 후보가 있으면 그것(같은 이름 여러 리스팅이면 병합). 상품조회 실패일엔 스냅샷 복원.
    반환: 고정으로 쓴 원래 후보 위치(di) 집합 — 정확일치·AI 후보에서 뺀다(유일 배정)."""
    used: set[int] = set()
    for li, lp in enumerate(ledger):
        rec = anchors.get(key_of(lp.name))
        if not rec:
            continue
        av = set(rec.get("vids") or [])
        dis = [di for di, d in enumerate(out.candidates) if _vids(d) & av]
        if dis:
            if not lp.discontinued and all(out.candidates[di].sale_status == "판매중지" for di in dis):
                out.notes.append(f"[매칭] '{lp.name}' 고정 상품이 판매중지 — 다시 판단(재등록 확인)")
                continue
            used.update(dis)
            out.picks[li] = Pick(dis[0], "anchor", "high", extra=dis[1:])
        elif not vendor_ok:
            out.candidates.append(_snapshot(rec))
            out.picks[li] = Pick(len(out.candidates) - 1, "anchor-snapshot", "high")
        else:
            out.notes.append(f"[매칭] '{lp.name}' 고정 VID {sorted(av)[:3]} 가 쿠팡에서 사라짐 — 다시 매칭")
    return used


def _apply_exact(ledger, out: MatchOutcome, used: set[int], n_disc: int) -> None:
    """② 정확일치 — 대장 괄호 또는 전체 이름이 후보 등록명과 공백 무시 완전 일치."""
    titles: dict[str, list[int]] = {}
    for di in range(n_disc):
        titles.setdefault(_norm(_title(out.candidates[di])), []).append(di)
    for li, lp in enumerate(ledger):
        if li in out.picks:
            continue
        for key in (_norm(_paren(lp.name)), _norm(lp.name)):
            hit = [di for di in titles.get(key, []) if di not in used] if key else []
            if len(hit) == 1:
                out.picks[li] = Pick(hit[0], "exact", "high")
                used.add(hit[0])
                break


def _resolve_conflicts(ledger, picks: dict[int, Pick], out: MatchOutcome) -> None:
    """한 후보를 여러 줄이 고르면 — 색상만 다른 같은 상품군 줄이면 허용, 아니면 우선순위 높은 줄만."""
    rank = {"anchor": 4, "anchor-snapshot": 4, "exact": 3, "ai": 2, "rule": 1}
    cr = {"high": 3, "medium": 2, "low": 1}
    by_di: dict[int, list[int]] = {}
    for li, pk in picks.items():
        by_di.setdefault(pk.di, []).append(li)
    for di, lis in by_di.items():
        groups = {_norm(_base_name(ledger[li].name)) for li in lis}
        if len(lis) < 2 or len(groups) == 1:
            continue
        lis.sort(key=lambda li: (rank.get(picks[li].how, 0), cr.get(picks[li].conf, 0)), reverse=True)
        keep = _norm(_base_name(ledger[lis[0]].name))
        for li in lis[1:]:
            if _norm(_base_name(ledger[li].name)) != keep:
                out.notes.append(f"[매칭] ⚠ '{ledger[li].name}' 가 고른 상품을 '{ledger[lis[0]].name}' 이 먼저 차지 — 이 줄 미매칭")
                del picks[li]


def match_ledger(ledger: list[Product], discovered: list[Product], *, anchors: dict[str, dict],
                 vendor_ok: bool, ask, expo: dict | None = None, today: str | None = None) -> MatchOutcome:
    """대장 ↔ 후보 매칭(①고정 ②정확일치 ③AI ④AI 실패 시 규칙). `ask(system, user) -> dict`(실 API=OpenAI,
    테스트=페이크·예외 시 규칙 대체). 반환 MatchOutcome(picks=대장i→Pick, candidates, 새 앵커, 로그 문장)."""
    expo = expo or {}
    today = today or date.today().isoformat()
    out = MatchOutcome(candidates=list(discovered))
    n_disc = len(discovered)
    used = _apply_anchors(ledger, discovered, anchors, vendor_ok, out)
    _apply_exact(ledger, out, used, n_disc)
    rest = [li for li in range(len(ledger)) if li not in out.picks]
    pool = [di for di in range(n_disc) if di not in used]
    if rest and pool:
        rule = _rule_hints(ledger, rest, discovered, pool)
        got = _ask_ai(ledger, rest, pool, discovered, expo, rule, ask, out)
        if got is None:                                   # ④ AI 실패 → 규칙 결과(로그 명시·고정 안 함)
            got = {li: Pick(di, "rule", "") for li, di in rule.items()}
        out.picks.update(got)
    _resolve_conflicts(ledger, out.picks, out)
    _add_siblings(ledger, out, n_disc)
    res = resolved(out)
    for li, pk in out.picks.items():
        if pk.how in ("anchor", "anchor-snapshot", "exact") or (pk.how == "ai" and pk.conf in ANCHOR_CONF):
            out.anchors[key_of(ledger[li].name)] = _anchor_record(res[li], pk, today)
    return out


def _add_siblings(ledger, out: MatchOutcome, n_disc: int) -> None:
    """고른 상품과 **등록명이 같은 판매중 리스팅**(재등록·중복 등록)을 함께 묶는다 — 별도 블록으로 계속 추적
    (2026-09-29 동명 병합 결정 유지·판매중지 리스팅은 제외). 다른 줄이 이미 쓴 리스팅은 건드리지 않는다."""
    taken = {x for pk in out.picks.values() for x in [pk.di, *pk.extra]}
    for li, pk in sorted(out.picks.items()):
        if pk.how == "anchor-snapshot":
            continue
        key = _norm(_title(out.candidates[pk.di]))
        sibs = [x for x in range(n_disc) if x not in taken and _norm(_title(out.candidates[x])) == key
                and out.candidates[x].sale_status != "판매중지"]
        if sibs:
            pk.extra.extend(sibs)
            taken.update(sibs)
            out.notes.append(f"[매칭] '{ledger[li].name}' 같은 이름 판매중 상품 {len(sibs)}개 함께 추적(별도 블록)")


def _rule_hints(ledger, rest: list[int], discovered, pool: list[int]) -> dict[int, int]:
    """글자 규칙(정밀 매칭 _assign) 결과 → {대장i: 후보 di}(AI 참고 후보·AI 실패 시 대체). 동명 병합 결과는
    VID 로 첫 리스팅에 대응(나머지는 _add_siblings 가 다시 묶음)."""
    sub = [ledger[li] for li in rest]
    cand = [discovered[di] for di in pool]
    res = _assign(sub, cand)
    out: dict[int, int] = {}
    for pos, d in res.items():
        dv = _vids(d)
        k = next((k for k, c in enumerate(cand) if _vids(c) and _vids(c) <= dv), None)
        if k is not None:
            out[rest[pos]] = pool[k]
    return out


def _ask_ai(ledger, rest, pool, discovered, expo, rule, ask, out: MatchOutcome) -> dict[int, Pick] | None:
    """③ AI 선택 — 줄마다 후보를 추려 한 번에 묻는다. 실패(예외)면 None(호출부가 규칙 대체)."""
    if len(pool) <= SEND_ALL_MAX:
        cand_ids = list(pool)
    else:
        ids: set[int] = set()
        for li in rest:
            ids.update(shortlist(ledger[li], pool, discovered, expo))
            if li in rule:
                ids.add(rule[li])
        cand_ids = sorted(ids)
    try:
        obj = ask(MATCH_SYSTEM, build_request(ledger, rest, cand_ids, discovered, expo, rule))
    except Exception as exc:                              # 키·네트워크·JSON 등 — 비치명(규칙 대체·로그 명시)
        out.notes.append(f"[매칭] ⚠ AI 매칭 실패 → 글자 규칙 결과로 대체(고정 안 함): {exc.__class__.__name__}: {str(exc)[:80]}")
        return None
    picks = parse_response(obj if isinstance(obj, dict) else {}, rest, cand_ids)
    for li, pk in picks.items():
        d = discovered[pk.di]
        flag = "⚠낮은확신·고정안함 " if pk.conf == "low" else ""
        out.notes.append(f"[AI매칭] {flag}'{ledger[li].name}' ↔ '{_title(d)}' ({pk.conf}·{pk.reason})")
    for li in rest:
        if li not in picks:
            out.notes.append(f"[AI매칭] '{ledger[li].name}' — 같은 상품 없음(후보 {len(cand_ids)}개 검토)")
    return picks


def resolved(out: MatchOutcome) -> dict[int, Product]:
    """MatchOutcome → product_match.build_tracked 입력 {대장i: 후보 Product}(동명 리스팅은 옵션 병합 = 별도 블록)."""
    return {li: (out.candidates[pk.di] if not pk.extra
                 else _merge_same_name(out.candidates, [pk.di, *pk.extra]))
            for li, pk in out.picks.items()}


def openai_ask(api_key: str, model: str | None = None):
    """실 API ask — kw_ai 의 OpenAI 호출(JSON 모드·temperature 0) 재사용. 실패는 KeywordAIError(호출부가 규칙 대체)."""
    from . import config
    from .kw_ai import _ask, _client, _json_object

    def ask(system: str, user: str) -> dict:
        n_lines = user.count("\nL") + 1
        text = _ask(_client(api_key), model or config.KW_AI_MODEL, system, user,
                    max_tokens=min(4000, 200 + 80 * n_lines))
        return _json_object(text)
    return ask
