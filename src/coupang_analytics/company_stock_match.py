"""회사보유재고 매칭 — 관리대장 상품명 ↔ 재고현황 상품명(D-072·소유자 2026-10-16 "재고현황 수정").

옛 규칙(동일 상품명·띄어쓰기/대소문자 무시)만으로는 대장 상품명 칸의 괄호 설명('보냉백 BG001(벅스 3중 …)')·색상 줄
('신형타프 R008 (블랙)')·모델번호 표기 차이('R20'↔'R020')·대장 오타('HS0300'↔쿠팡·재고 'HS0030') 때문에 40줄 중 21줄이
재고현황에 있는데도 미매칭(실측 2026-10-16).

⛔판정 = AI(D-157·소유자 2026-11-05 "상품명은 AI로 판정 — 직원이 명확하게 하지 않는 경우가 있음"). 그대로 확정하는 것은
1) 상품명 전체 일치뿐이고, 2)·3) 은 AI 에게 맨 앞 후보로 보일 뿐이다(실측 11-05: 모델번호 규칙이 '드라이기거치대 Y003' 에
'안전화 Y003' 재고를 붙임). AI 를 못 쓰면 규칙 값으로 넘어가지 않고 기존값 유지. 후보 추출 순서:
  1) 상품명 전체 일치(옛 규칙)
  2) 대장 이름의 괄호 앞·괄호 안 각각 = 재고현황 상품명, 또는 재고현황 '괄호 앞' 이름 — 재고현황에 색상별 줄이 있으면
     대장 괄호 안 색상과 같은 줄만, 없으면 그 상품 줄 전부(색상별로 나눠 표기)
  3) 모델번호(영문+숫자, 숫자 앞 0 무시 — R20=R020) — 대장 이름에서, 없으면 ① 매칭된 쿠팡 상품명에서 — 재고현황에서
     그 번호를 가진 상품이 하나뿐일 때만(인덕션 A003·변신큐브 A003 처럼 둘 이상이면 판단 안 함)
  4) AI(OpenAI) — 2)·3) 후보 + 이름이 비슷한 후보 중 **같은 상품**만 고름(번호 한 글자만 달라도 다른 상품: JK8602≠JK8601)
     · 결과는 `output/_회사재고매칭.json` 에 저장(계정목록 표기는 저장된 결과만 씀 — 실행마다 AI 반복 호출 없음)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

from .company_stock import name_key

CACHE_FILE = "_회사재고매칭.json"
EXACT = "상품명 일치"          # 규칙 중 이것만 AI 없이 확정(같은 글자 = 판단할 것이 없음·D-157)
_SHORTLIST = 10                # 줄당 AI 후보 수
_BATCH = 30                    # 한 번에 물을 줄 수(답 길이 상한 4,000 토큰 — 넘으면 JSON 이 잘려 전부 실패)
_CODE = re.compile(r"[A-Za-z]+-?\d+[A-Za-z]*")
_SYSTEM = (
    "너는 쿠팡 위탁판매 회사의 창고 재고 담당자다. 관리대장 상품 하나와 회사 창고 재고 목록의 후보들을 보고, "
    "**같은 상품(같은 모델번호·같은 용량/수량)** 인 후보 번호를 고른다. 관리대장 이름은 직원이 적은 것이라 줄임말·용도 이름·"
    "오타·메모가 섞일 수 있으니, 쿠팡 상품명이 있으면 그것까지 보고 실제 상품을 판단한다(예: 대장 '코골이 방지 기구' + 쿠팡 "
    "'코골이 방지 비강확장기 숨통박사' = 후보 '비강확장기 HR-01BK'). 모델번호가 한 글자라도 다르면 다른 상품 "
    "(예: JK8602 와 JK8601 은 다름), 모델번호가 같아도 상품 종류가 다르면 다른 상품(예: 드라이기거치대 Y003 ≠ 안전화 Y003), "
    "브랜드가 다르면 다른 상품. 영문/한글 브랜드 표기 차이(PHARMIZEN=파미젠)는 같음. '외 N줄' 후보 = 색상·사이즈 줄을 묶은 한 상품. "
    "양쪽 모두에 모델번호가 있을 때만 번호로 가르고, 한쪽에 모델번호가 없으면 상품 종류·용도가 같은지로 판단한다(예: 쿠팡 "
    "'의료용 경추 거북목 교정기 견인기' = 후보 '거북목교정기'). 확실하지 않으면 null. reason 은 한국어. "
    "id = 각 줄 앞 L 뒤의 번호. JSON 으로만: "
    '{"items":[{"id":번호,"pick":후보번호 또는 null,"reason":"한 줄 근거"}]}'
)


def _split(name: str) -> tuple[str, str]:
    """'보냉백 BG001(벅스 …)' → ('보냉백 BG001', '벅스 …') · 괄호 없으면 (이름, '')."""
    m = re.match(r"\s*([^(]*)\((.*?)\)?\s*$", name or "")
    return ((m.group(1).strip(), m.group(2).strip()) if m else (str(name or "").strip(), ""))


def codes(text: str) -> set:
    """모델번호 정규화 — 대문자·숫자 앞 0 제거(R020 → R20, HS0030 → HS30)."""
    out = set()
    for t in _CODE.findall(str(text or "")):
        m = re.match(r"([A-Za-z]+)-?(\d+)([A-Za-z]*)", t)
        if m:
            out.add(f"{m.group(1).upper()}{int(m.group(2))}{m.group(3).upper()}")
    return out


@dataclass
class _Item:
    key: str
    shown: str
    base: str     # name_key(괄호 앞)
    paren: str    # name_key(괄호 안)
    codes: set


def build_index(stock: dict) -> list:
    out = []
    for key, (shown, _wh) in stock.items():
        head, inside = _split(shown)
        out.append(_Item(key, shown, name_key(head), name_key(inside), codes(head)))
    return out


def _pick_color(cands: list, ledger_paren: str) -> list:
    hit = [c for c in cands if c.paren and c.paren in ledger_paren]
    return hit or cands


def match_rules(stock: dict, idx: list, ledger_name: str, coupang_title: str = "") -> tuple[list, str]:
    """규칙 1~3 → ([재고현황 키…], 근거) · 못 찾으면 ([], '')."""
    if name_key(ledger_name) in stock:
        return [name_key(ledger_name)], EXACT
    head, inside = _split(ledger_name)
    lp = name_key(inside)
    for part in (head, inside):
        k = name_key(part)
        if not k:
            continue
        if k in stock:
            return [k], "괄호 앞/안 이름 일치"
        cands = [c for c in idx if c.base == k]
        if cands:
            return [c.key for c in _pick_color(cands, lp)], "괄호 앞 이름 일치(색상별 줄)"
    for src, label in ((head + " " + inside, "대장"), (coupang_title, "쿠팡 상품명")):
        want = codes(src)
        cands = [c for c in idx if want & c.codes]
        if want and cands and len({c.base for c in cands}) == 1:
            return [c.key for c in _pick_color(cands, lp)], f"모델번호 일치({label} {'·'.join(sorted(want & cands[0].codes))})"
    return [], ""


def text_of(stock: dict, keys: list, stock_text) -> str:
    """한 줄이면 '창고 , 수량개' · 색상별 여러 줄이면 '(그레이) 검단 , 599개 / (핑크) 검단 , 299개'."""
    if len(keys) == 1:
        return stock_text(stock[keys[0]][1])
    parts = []
    for k in keys:
        shown, by_wh = stock[k]
        tag = _split(shown)[1] or shown
        parts.append(f"({tag}) {stock_text(by_wh)}")
    return " / ".join(parts)


# ── 4) AI ──────────────────────────────────────────────────────
def _cache_key(ledger_name: str, title: str) -> str:
    return f"{name_key(ledger_name)}|{name_key(title)}"


def load_cache(out_dir="output") -> dict:
    p = Path(out_dir) / CACHE_FILE
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def save_cache(cache: dict, out_dir="output") -> None:
    p = Path(out_dir) / CACHE_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def from_cache(cache: dict, stock: dict, ledger_name: str, title: str = "", rule: list = ()) -> tuple[list, str] | None:
    """저장된 AI 결과 — 고른 재고현황 이름이 아직 있고 규칙 후보(rule)가 판정 때와 같으면 그 키들 · '없음' 결과는 그날만 유효
    · 해당 없음이면 None. 규칙 후보가 달라짐 = 색상·사이즈 줄이 새로 생김 → 다시 판정(새 줄 재고 누락 방지)."""
    rec = cache.get(_cache_key(ledger_name, title))
    if not rec:
        return None
    if rec.get("stock"):
        keys = [name_key(s) for s in rec["stock"]]
        same = rec.get("rule") is None or rec["rule"] == sorted(rule)
        return (keys, f"AI — {rec.get('why', '')}") if same and all(k in stock for k in keys) else None
    return ([], "") if rec.get("date") == date.today().isoformat() else None


def judged_none(cache: dict, ledger_name: str, title: str = "") -> bool:
    """마지막 AI 판정이 '재고현황에 없음'이었나(날짜 무관) — 계정목록 표기용(D-156)."""
    rec = cache.get(_cache_key(ledger_name, title))
    return bool(rec) and not rec.get("stock")


def _shortlist(stock: dict, idx: list, name: str, title: str) -> tuple[list, list]:
    """AI 에게 보일 후보([[_Item…]…] — 색상·사이즈 줄은 한 후보), 규칙 키. 규칙 후보가 맨 앞 · 뒤는 글자가 비슷한 상품."""
    rule = match_rules(stock, idx, name, title)[0]
    head, inside = _split(name)
    groups: dict = {}
    for c in idx:
        if c.key not in rule:
            groups.setdefault(c.base or c.key, []).append(c)
    q = name_key(head + title)
    ranked = sorted(groups, key=lambda b: -SequenceMatcher(None, q, b).ratio())
    first = [[c for c in idx if c.key in rule]] if rule else []
    return first + [_pick_color(groups[b], name_key(inside)) for b in ranked[:_SHORTLIST - len(first)]], rule


def _label(group: list) -> str:
    return group[0].shown + (f" 외 {len(group) - 1}줄" if len(group) > 1 else "")


def _ask_batch(ask, batch: list, stock: dict, idx: list, cache: dict, log) -> dict:
    lines, shortlists = [], {}
    for i, name, title in batch:
        shortlists[i] = _shortlist(stock, idx, name, title)
        lines.append(f"L{i}. 관리대장: {name}" + (f" · 쿠팡 상품명: {title}" if title else "") + " · 후보: "
                     + " | ".join(f"{n}) {_label(g)}" for n, g in enumerate(shortlists[i][0], 1)))
    try:
        res = ask(_SYSTEM, "\n".join(lines))
        got = {int(x["id"]): x for x in (res or {}).get("items") or []}
    except Exception as exc:   # AI 장애 = 이번엔 그 상품 기존값 유지(로그로 명시·다음 실행에서 다시)
        log(f"  [회사재고] ⚠ AI 매칭 실패({exc.__class__.__name__}) — 이번에 못 물은 상품은 기존값 유지")
        return {}
    out, today = {}, date.today().isoformat()
    for i, name, title in batch:
        x = got.get(i)
        if x is None:
            continue
        pick, why = x.get("pick"), str(x.get("reason") or "")[:80]
        top, rule = shortlists[i]
        if isinstance(pick, int) and 1 <= pick <= len(top):
            out[i] = ([c.key for c in top[pick - 1]], f"AI — {why}")
            cache[_cache_key(name, title)] = {"stock": [c.shown for c in top[pick - 1]], "why": why, "date": today,
                                              "rule": sorted(rule)}
        else:
            cache[_cache_key(name, title)] = {"stock": [], "why": why, "date": today}
    return out


def ask_ai(ask, items: list, stock: dict, idx: list, cache: dict, log) -> dict:
    """items = [(id, 대장명, 쿠팡 상품명)] → {id: ([키], 근거)} · 결과를 cache 에 기록. AI 장애·답에서 빠진 줄 = 판단 없음(기록 안 함·호출부가 기존값 유지)."""
    if not items or ask is None:
        return {}
    out: dict = {}
    for s in range(0, len(items), _BATCH):
        out.update(_ask_batch(ask, items[s:s + _BATCH], stock, idx, cache, log))
    return out
