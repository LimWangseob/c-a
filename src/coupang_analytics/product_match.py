"""입력 대장 상품 ↔ 쿠팡 발견(등록) 상품 매칭 → **추적 범위를 대장 상품으로 한정**.

정책(확정): 추적 대상 = 입력 대장에 있는 상품(위탁 관리분)만. 판매분석에 잡힌 그 외 등록상품은
관리 대상이 아니라 제외한다. 대장 상품명은 보통 `내부코드명 (괄호=실제 노출제목)` 형태다.
- 괄호에 전체 노출제목이 있으면 발견 제목과 **정확 매칭**(가장 신뢰).
- 없으면 **브랜드(계정 공통어) 제외 + 띄어쓰기 제거 부분일치**(한글 띄어쓰기 변형 흡수).
- 한 발견상품은 한 대장상품에만 배정(유일 배정)해 1:다 오매칭을 막는다.

매칭되면 발견 상품의 **노출제목·vid·구분(계약/개인)** 을 부여(시트 표시=노출제목).
매칭 안 되면(휴면 등) 대장명으로 추적한다 — 판매지표·재고는 공란, 키워드·순위는 대장명 기준.
"""
from __future__ import annotations

import re
from collections import Counter

from . import config
from .input_list import Option, Product

_STOP = {"프리미엄", "정품", "1위", "추천", "신형", "max", "plus", "premium", "ml", "mg",
         "세트", "대형", "소형", "중형"}
_CODE_TAIL = re.compile(r"[A-Za-z]{1,5}-?\d{2,}[A-Za-z0-9]*$")   # 토큰 끝 관리코드 제거(손세정기YG0187)


def _norm(s) -> str:
    return re.sub(r"[\s/+,]+", "", str(s)).lower()


def _paren(name: str) -> str:
    m = re.search(r"[（(]([^)）]+)[)）]", str(name).replace("\n", " "))
    return m.group(1).strip() if m else ""


def _tokens(name: str) -> list[str]:
    s = re.sub(r"[（(][^)）]*[)）]", " ", str(name).replace("\n", " "))
    out = []
    for t in re.split(r"[\s/+,]+", s):
        t = _CODE_TAIL.sub("", t.strip()).lower()
        if len(t) >= 2 and t not in _STOP and not t.isdigit():
            out.append(t)
    return out


def _title(p: Product) -> str:
    return p.title or p.name


def _assign(ledger: list[Product], discovered: list[Product]) -> dict[int, Product]:
    """{대장 index: 발견 Product}. 유일 배정(점수 높은 쌍부터, 대장·발견 각각 1회)."""
    if not discovered:
        return {}
    # 브랜드 = 발견 제목의 60%+(또는 3건+)에 등장하는 토큰(계정 브랜드: YULIFE·디프·HB153 등)
    dc: Counter = Counter()
    for d in discovered:
        dc.update(set(_tokens(_title(d))))
    thr = max(3, int(len(discovered) * 0.6))
    brand = {t for t, c in dc.items() if c >= thr}
    ndisc = [_norm(_title(d)) for d in discovered]
    dtoks = [[t for t in _tokens(_title(d)) if t not in brand and len(t) >= 2] for d in discovered]

    pairs: list[tuple[int, int, int]] = []      # (점수, 대장i, 발견i)
    for li, lp in enumerate(ledger):
        par = _norm(_paren(lp.name))
        ltoks = [t for t in _tokens(lp.name) if t not in brand]
        nlp = _norm(lp.name)
        for di, _d in enumerate(discovered):
            nd = ndisc[di]
            if par and (par == nd or par in nd or nd in par):
                sc = 1000                                   # 괄호 전체제목 = 정확 매칭
            else:
                sc = sum(len(t) for t in ltoks if t in nd)  # 대장 토큰이 발견제목(공백제거)에 부분일치
                sc += sum(len(t) for t in dtoks[di] if t in nlp and t not in ltoks)  # 역방향(복합어 흡수)
            if sc > 0:
                pairs.append((sc, li, di))
    pairs.sort(reverse=True)
    used_l: set[int] = set()
    used_d: set[int] = set()
    res: dict[int, Product] = {}
    for sc, li, di in pairs:
        if li in used_l or di in used_d or sc < 2:
            continue
        res[li] = discovered[di]
        used_l.add(li)
        used_d.add(di)
    return res


def scope_to_ledger(ledger: list[Product], discovered: list[Product]) -> tuple[list[Product], int]:
    """대장 상품만 추적 대상으로. 반환: (추적 Product 목록, 매칭된 개수).

    매칭 상품 = 발견 노출제목/vid/구분 부여(시트 표시=노출제목). 미매칭 = 대장명으로 추적(지표·재고 공란).
    """
    res = _assign(ledger, discovered)
    out: list[Product] = []
    for li, lp in enumerate(ledger):
        d = res.get(li)
        if d is not None:
            out.append(Product(
                name=_title(d), title=_title(d), kind=d.kind,
                options=[Option(o.label, list(o.vendor_item_ids), list(o.product_ids)) for o in d.options]))
        else:
            out.append(Product(name=lp.name, title=lp.name, kind=config.KIND_PERSONAL, options=[Option("")]))
    return out, len(res)
