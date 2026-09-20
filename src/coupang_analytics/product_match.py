"""입력 대장 상품 ↔ 쿠팡 발견(등록) 상품 매칭 → **추적 범위를 대장 상품으로 한정**.

정책(확정): 추적 대상 = 입력 대장에 있는 상품(위탁 관리분)만. 판매분석·상품조회에 잡힌 그 외 등록상품
(소유자 직접판매 등)은 관리 대상이 아니라 제외한다. 쿠팡 상품조회로는 위탁/직접이 구분 안 되므로 **대장이
유일 기준**인데, 대장명이 쿠팡 등록명과 100% 일치하지 않을 수 있다. 대장 상품명은 보통 `내부코드명
(괄호=실제 노출제목)` 형태다.
- **정밀 우선 매칭(2026-09-18)**: 괄호 노출제목 정확일치 = 최우선. 아니면 **대장 핵심어(IDF 최고 토큰)를
  발견제목이 포함** + **핵심어 IDF 재현율·2등 마진** 통과 시에만 매칭. 미달이면 **미매칭**으로 둔다 —
  흔한 단어 하나로 **비관리 상품에 잘못 붙는(오매칭)** 것보다 통계 공란이 안전(소유자 지시).
- 한 발견상품은 한 대장상품에만 배정(유일 배정)해 1:다 오매칭을 막는다.

매칭되면 발견 상품의 **노출제목·vid·구분(계약/개인)** 을 부여(시트 표시=노출제목).
매칭 안 되면(휴면·이름 상이 등) 대장명으로 추적한다 — 판매지표·재고는 공란, 키워드·순위는 대장명 기준.
한 번 vid 가 잡히면 이후 실행은 vid 앵커(`workbook.resolve_block_name`)로 안정 식별한다.
"""
from __future__ import annotations

import re
from collections import Counter

from . import config
from .input_list import Option, Product, _build_idf

_STOP = {"프리미엄", "정품", "1위", "추천", "신형", "max", "plus", "premium", "ml", "mg",
         "세트", "대형", "소형", "중형"}
_CODE_TAIL = re.compile(r"[A-Za-z]{1,5}-?\d{2,}[A-Za-z0-9]*$")   # 토큰 끝 관리코드 제거(손세정기YG0187)
# 규격·수량 토큰(숫자로 시작하는 단위) 제거 — 상품 정체성이 아니므로 핵심어/재현율에서 뺀다.
# 예: 120정·30포·600mg·4개월분·88%·25t. ⚠ '3d프린트'처럼 단위가 4자 이상이면 정체성으로 보고 유지.
_SPEC = re.compile(r"^\d+[가-힣a-zA-Z%]{0,3}$")

# 정밀 매칭 임계(2026-09-18, 정밀 우선) — 대장명이 쿠팡명과 100% 일치하지 않아도 **확신 있는 것만** 매칭하고
# 애매하면 미매칭(대장명 추적·통계 공란)으로 둔다. 엉뚱한(비관리) 상품에 붙이는 것보다 공란이 안전.
#   RECALL_MIN = 대장 상품 핵심어(IDF 가중)의 재현율 하한, MARGIN = 최고-차선 재현율 마진.
_RECALL_MIN = 0.55
_MARGIN = 0.15


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
        if len(t) >= 2 and t not in _STOP and not t.isdigit() and not _SPEC.match(t):
            out.append(t)
    return out


def _title(p: Product) -> str:
    return p.title or p.name


def _spec_tokens(name: str) -> set:
    """규격·수량 토큰 집합 — `_tokens` 가 정체성에서 **제외**하는 것(120정·30포·600mg·88%·순수숫자 등).

    핵심어(상품 정체성)가 동점이라 어느 변형인지 못 가릴 때만 **타이브레이커**로 쓴다(예: 대장 '…정 120정'
    ↔ 발견 '…정 120정' vs '…정'). 괄호(노출제목) 안은 무시하고 본문 토큰만. 소문자·strip 정규화."""
    s = re.sub(r"[（(][^)）]*[)）]", " ", str(name).replace("\n", " "))
    out = set()
    for t in re.split(r"[\s/+,]+", s):
        t = t.strip().lower()
        if t and (t.isdigit() or _SPEC.match(t)):
            out.add(t)
    return out


def _assign(ledger: list[Product], discovered: list[Product]) -> dict[int, Product]:
    """{대장 index: 발견 Product}. **정밀 우선 매칭**(2026-09-18) — 확신 있는 쌍만, 대장·발견 각 1회 유일 배정.

    쿠팡 상품조회로는 위탁/직접이 구분 안 되므로 대장이 유일 기준인데, 대장명이 쿠팡명과 100% 일치하지
    않을 수 있다. 흔한 단어 하나로 **비관리 상품에 잘못 붙는(오매칭)** 것을 막기 위해:
      ① 괄호 노출제목 정확일치 = 최우선(신뢰 최고),
      ② 아니면 **대장 상품의 핵심어(IDF 최고 토큰)를 발견제목이 반드시 포함**(핵심 게이트) +
         **핵심어 IDF 재현율 ≥ RECALL_MIN** + **최고-차선 마진 ≥ MARGIN**일 때만 매칭,
      ③ 미달 = 미매칭(호출부가 대장명으로 추적·통계 공란) — 엉뚱한 데이터보다 공란이 안전.
    """
    if not discovered:
        return {}
    # 브랜드 = 발견 제목의 60%+(또는 3건+)에 등장하는 토큰(계정 브랜드: YULIFE·디프·HB153 등) → 핵심어에서 제외
    dc: Counter = Counter()
    for d in discovered:
        dc.update(set(_tokens(_title(d))))
    thr = max(3, int(len(discovered) * 0.6))
    brand = {t for t, c in dc.items() if c >= thr}
    # IDF 가중 = 계정 코퍼스(발견 제목 + 대장명) 기반 → 규격·브랜드어(정·30포 등) 눌러 상품 핵심어 부각
    w = _build_idf([_title(d) for d in discovered] + [lp.name for lp in ledger])
    ndisc = [_norm(_title(d)) for d in discovered]   # 공백 제거 발견제목 — 정체성 매칭은 띄어쓰기 무관(부분일치)

    qualified: list[tuple[int, float, int, int]] = []   # (괄호정확?, 재현율, 대장i, 발견i)
    for li, lp in enumerate(ledger):
        par = _norm(_paren(lp.name))
        # ① 괄호 노출제목 정확일치(대장 형식 '코드 (노출제목)')
        if par:
            hit = next((di for di in range(len(discovered))
                        if par == ndisc[di] or par in ndisc[di] or ndisc[di] in par), None)
            if hit is not None:
                qualified.append((1, 1.0, li, hit))
                continue
        # ② 핵심어 게이트 + IDF 재현율 + 마진. 괄호가 있으면 그 노출제목 토큰으로, 없으면 대장명 토큰으로.
        core_text = _paren(lp.name) or lp.name
        ptoks = {t for t in _tokens(core_text) if t not in brand} or set(_tokens(core_text))
        if not ptoks:
            continue                                    # 순수 코드명 등 → 미매칭(공란)
        pden = sum(w(t) for t in ptoks) or 1.0
        top = max(ptoks, key=lambda t: (w(t), len(t)))   # 최고가중(희소=핵심) 토큰, IDF 동점이면 긴 토큰
        # 핵심 게이트=핵심어가 발견제목(공백 제거)에 부분일치 + IDF 재현율(대장 토큰이 발견제목에 부분일치).
        # 공백 제거 부분일치라 쿠팡 붙여쓰기 제목('루바브치커리뿌리추출물')도 대장 띄어쓰기와 매칭된다.
        scored = sorted(((sum(w(t) for t in ptoks if t in ndisc[di]) / pden, di)
                         for di in range(len(discovered)) if top in ndisc[di]), reverse=True)
        if not scored:
            continue                                    # 핵심어를 담은 발견상품 없음 → 미매칭
        best, best_di = scored[0]
        second = scored[1][0] if len(scored) > 1 else 0.0
        if best >= _RECALL_MIN and (best - second) >= _MARGIN:
            qualified.append((0, best, li, best_di))
        elif best >= _RECALL_MIN:
            # 애매(핵심어 재현율은 충분한데 **마진 미달** = 변형 상품 동점). 규격 타이브레이커로 확정 시도:
            # 최고재현율 동률권(best 근방) 후보 중 **대장 규격토큰과 겹치는 후보가 정확히 1개**면 그것으로 확정.
            # 규격은 정체성이 아니라 동점을 가르는 보조키로만 쓴다(핵심 정밀도 불변). 여전히 애매하면 미매칭.
            lspec = _spec_tokens(core_text)
            if lspec:
                tied = [di for rc, di in scored if (best - rc) < _MARGIN]        # 동률권(마진 이내) 후보들
                hit = [di for di in tied if lspec & _spec_tokens(_title(discovered[di]))]
                if len(hit) == 1:
                    qualified.append((0, best, li, hit[0]))                       # 규격으로 유일 확정
        # else: 재현율 미달/규격도 애매 → 미매칭(공란, 오매칭 방지)

    qualified.sort(reverse=True)                          # 괄호정확 우선, 그 다음 재현율 높은 순
    used_l: set[int] = set()
    used_d: set[int] = set()
    res: dict[int, Product] = {}
    for _paren_exact, _sc, li, di in qualified:
        if li in used_l or di in used_d:
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
                options=[Option(o.label, list(o.vendor_item_ids), list(o.product_ids)) for o in d.options],
                mkt_start=lp.mkt_start, mkt_end=lp.mkt_end, mkt_mon=lp.mkt_mon))   # 대장 마케팅 이월
        else:
            out.append(Product(name=lp.name, title=lp.name, kind=config.KIND_PERSONAL, options=[Option("")],
                               mkt_start=lp.mkt_start, mkt_end=lp.mkt_end, mkt_mon=lp.mkt_mon))
    return out, len(res)


def augment_unmatched(ledger: list[Product], tracked: list[Product],
                      extra: list[Product]) -> tuple[list[Product], int]:
    """이미 매칭된 상품은 **그대로 두고**, vid 없는(미매칭) 대장 상품만 extra 후보와 매칭해 vid·노출명·구분을 채운다.

    당일 발견으로 못 잡은 상품(당일 판매·방문 0)을 최근기간 판매분석·그로스 재고 roster(extra)로 보강할 때 쓴다.
    ⚠ 지표는 호출부가 당일 것만 기록하므로 여기선 **정체(vid/이름/구분)만** 채운다(넓은기간 지표 미반영).
    반환: (보강된 tracked, 새로 vid 채운 개수). tracked/ledger 는 1:1 이며 그 정렬을 유지한다."""
    idxs = [i for i, tp in enumerate(tracked)
            if not any(o.vendor_item_ids for o in tp.options)]   # vid 없는(미매칭) 대장 상품 위치
    if not idxs or not extra:
        return tracked, 0
    # 이미 당일 매칭에 쓰인 vid 는 후보에서 제외 — 유사 상품 2개에 같은 vid 를 중복 배정하지 않게(정체성 유일).
    used = {v for tp in tracked for o in tp.options for v in o.vendor_item_ids}
    extra = [d for d in extra if not (used & {v for o in d.options for v in o.vendor_item_ids})]
    if not extra:
        return tracked, 0
    sub = [ledger[i] for i in idxs]
    res = _assign(sub, extra)                                    # {sub_pos: 매칭된 extra Product}
    out = list(tracked)
    added = 0
    for pos, i in enumerate(idxs):
        d = res.get(pos)
        if d is None:
            continue
        lp = ledger[i]
        out[i] = Product(
            name=_title(d), title=_title(d), kind=d.kind,
            options=[Option(o.label, list(o.vendor_item_ids), list(o.product_ids)) for o in d.options],
            mkt_start=lp.mkt_start, mkt_end=lp.mkt_end, mkt_mon=lp.mkt_mon)   # 대장 마케팅 이월
        added += 1
    return out, added
