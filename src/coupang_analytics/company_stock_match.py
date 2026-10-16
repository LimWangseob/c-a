"""회사보유재고 매칭 — 관리대장 상품명 ↔ 재고현황 상품명(D-072·소유자 2026-10-16 "재고현황 수정").

옛 규칙(동일 상품명·띄어쓰기/대소문자 무시)만으로는 대장 상품명 칸의 괄호 설명('보냉백 BG001(벅스 3중 …)')·색상 줄
('신형타프 R008 (블랙)')·모델번호 표기 차이('R20'↔'R020')·대장 오타('HS0300'↔쿠팡·재고 'HS0030') 때문에 40줄 중 21줄이
재고현황에 있는데도 미매칭(실측 2026-10-16). 판단 순서(앞 단계에서 정해지면 끝):
  1) 상품명 전체 일치(옛 규칙)
  2) 대장 이름의 괄호 앞·괄호 안 각각 = 재고현황 상품명, 또는 재고현황 '괄호 앞' 이름 — 재고현황에 색상별 줄이 있으면
     대장 괄호 안 색상과 같은 줄만, 없으면 그 상품 줄 전부(색상별로 나눠 표기)
  3) 모델번호(영문+숫자, 숫자 앞 0 무시 — R20=R020) — 대장 이름에서, 없으면 ① 매칭된 쿠팡 상품명에서 — 재고현황에서
     그 번호를 가진 상품이 하나뿐일 때만(인덕션 A003·변신큐브 A003 처럼 둘 이상이면 판단 안 함)
  4) AI(OpenAI) — 이름이 비슷한 후보 중 **같은 모델·같은 용량**만 고름(번호 한 글자만 달라도 다른 상품: JK8602≠JK8601)
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
_CODE = re.compile(r"[A-Za-z]+-?\d+[A-Za-z]*")
_SYSTEM = (
    "너는 쿠팡 위탁판매 회사의 창고 재고 담당자다. 관리대장 상품 하나와 회사 창고 재고 목록의 후보들을 보고, "
    "**같은 상품(같은 모델번호·같은 용량/수량)** 인 후보 번호를 고른다. 모델번호가 한 글자라도 다르면 다른 상품 "
    "(예: JK8602 와 JK8601 은 다름), 브랜드가 다르면 다른 상품. 영문/한글 브랜드 표기 차이(PHARMIZEN=파미젠)는 같음. "
    "확실하지 않으면 null. id = 각 줄 앞 L 뒤의 번호. JSON 으로만: "
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
        return [name_key(ledger_name)], "상품명 일치"
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


def from_cache(cache: dict, stock: dict, ledger_name: str, title: str = "") -> tuple[list, str] | None:
    """저장된 AI 결과 — 고른 재고현황 이름이 아직 있으면 그 키들 · '없음' 결과는 그날만 유효 · 해당 없음이면 None."""
    rec = cache.get(_cache_key(ledger_name, title))
    if not rec:
        return None
    if rec.get("stock"):
        keys = [name_key(s) for s in rec["stock"]]
        return (keys, f"AI — {rec.get('why', '')}") if all(k in stock for k in keys) else None
    return ([], "") if rec.get("date") == date.today().isoformat() else None


def ask_ai(ask, items: list, stock: dict, idx: list, cache: dict, log) -> dict:
    """items = [(id, 대장명, 쿠팡 상품명)] → {id: ([키], 근거)} · 결과를 cache 에 기록. AI 장애면 로그 후 빈 결과(기존값 유지)."""
    if not items or ask is None:
        return {}
    lines, shortlists = [], {}
    for i, name, title in items:
        q = name_key(_split(name)[0] + title)
        top = sorted(idx, key=lambda c: -SequenceMatcher(None, q, c.key).ratio())[:6]
        shortlists[i] = top
        lines.append(f"L{i}. 관리대장: {name}" + (f" · 쿠팡 상품명: {title}" if title else "") + " · 후보: "
                     + " | ".join(f"{n}) {c.shown}" for n, c in enumerate(top, 1)))
    try:
        res = ask(_SYSTEM, "\n".join(lines))
        got = {int(x["id"]): x for x in (res or {}).get("items") or []}
    except Exception as exc:   # AI 장애 = 이번엔 그 상품 기존값 유지(로그로 명시·다음 실행에서 다시)
        log(f"  [회사재고] ⚠ AI 매칭 실패({exc.__class__.__name__}) — 규칙으로 못 찾은 상품은 기존값 유지")
        return {}
    out, today = {}, date.today().isoformat()
    for i, name, title in items:
        x = got.get(i) or {}
        pick, why = x.get("pick"), str(x.get("reason") or "")[:80]
        top = shortlists[i]
        if isinstance(pick, int) and 1 <= pick <= len(top):
            c = top[pick - 1]
            out[i] = ([c.key], f"AI — {why}")
            cache[_cache_key(name, title)] = {"stock": [c.shown], "why": why, "date": today}
        else:
            cache[_cache_key(name, title)] = {"stock": [], "why": why, "date": today}
    return out
