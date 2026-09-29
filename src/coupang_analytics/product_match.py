"""입력 대장 상품 ↔ 쿠팡 발견(등록) 상품 매칭 → **추적 범위를 대장 상품으로 한정**.

정책(확정): 추적 대상 = 입력 대장에 있는 상품(위탁 관리분)만. 판매분석·상품조회에 잡힌 그 외 등록상품
(소유자 직접판매 등)은 관리 대상이 아니라 제외한다. 쿠팡 상품조회로는 위탁/직접이 구분 안 되므로 **대장이
유일 기준**인데, 대장명이 쿠팡 등록명과 100% 일치하지 않을 수 있다. 대장 상품명은 보통 `내부코드명
(괄호=실제 노출제목)` 형태다.
- **정밀 우선 매칭(2026-09-18)**: 괄호 노출제목 정확일치 = 최우선. 아니면 **대장 핵심어(IDF 최고 토큰)를
  발견제목이 포함** + **핵심어 IDF 재현율·2등 마진** 통과 시에만 매칭. 미달이면 **미매칭**으로 둔다 —
  흔한 단어 하나로 **비관리 상품에 잘못 붙는(오매칭)** 것보다 통계 공란이 안전(소유자 지시).
- **본문명 우선(2026-09-29·원인②)**: ② 핵심어는 대장 **본문**(코드·상품명)에 정체성 토큰이 있으면 본문에서
  뽑고 괄호(색상/옵션/메모: '블랙'·'대체요망')는 무시한다 — 담당자 본문명을 최대한 존중. 본문이 코드뿐이면
  괄호(노출제목)로 폴백. 괄호 정확일치는 ①에서 이미 처리.
- **동점 타이브레이커(2026-09-29)**: 한글접두가 중복(예 '차량용청소기 ST6645' vs 'Q808')이라 핵심어만으론
  마진 미달(애매)일 때, 동률권 후보를 **규격토큰(`_spec_tokens`·숫자시작)** 또는 **모델코드(`_code_tokens`·
  `_CODE_TAIL`이 떼는 ST6645·BG001 등)** 로 가른다 — 그 보조키를 담은 후보가 **정확히 1개**면 확정, 아니면
  미매칭. 코드가 동일한 **중복 리스팅**(같은 코드 2 vid)은 못 가르므로 미매칭 유지(오매칭 방지).
- 한 발견상품은 한 대장상품에만 배정(유일 배정)해 1:다 오매칭을 막는다.

매칭되면 발견 상품의 **노출제목·vid·구분(계약/개인)** 을 부여(시트 표시=노출제목).
매칭 안 되면(휴면·이름 상이 등) 대장명으로 추적한다 — 판매지표·재고는 공란, 키워드·순위는 대장명 기준.
한 번 vid 가 잡히면 이후 실행은 vid 앵커(`workbook.resolve_block_name`)로 안정 식별한다.
"""
from __future__ import annotations

import re
from collections import Counter

from . import config
from .input_list import Option, Product, build_idf

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


def _code_tokens(name: str) -> set:
    """관리 모델코드 토큰(ST6645·YG0204·BG001·CL01 등) — `_CODE_TAIL` 이 정체성에서 **떼는** 코드.

    한글접두가 중복이라 애매할 때(마진 미달)만 **타이브레이커**로 쓴다 — 발견제목에 그 코드가 실제로
    있고 담은 후보가 정확히 1개면 확정. 규격(_SPEC=숫자시작)이 못 잡는 **문자시작 코드**(ST6645·BG001)를
    가른다. 괄호(노출제목/메모) 안은 무시하고 본문 토큰만·소문자 정규화."""
    s = re.sub(r"[（(][^)）]*[)）]", " ", str(name).replace("\n", " "))
    out = set()
    for t in re.split(r"[\s/+,]+", s):
        m = _CODE_TAIL.search(t.strip())
        if m:
            out.add(m.group(0).lower())
    return out


def _tiebreak(core_text: str, scored: list, discovered: list[Product], ndisc: list[str],
              best: float) -> tuple[str, int, list[int]]:
    """애매(마진 미달) 동률권 해소 → ('match', di, []) | ('merge', -1, [di,...]) | ('none', -1, []).

    ⓐ **판매중지 제외**(소유자 2026-09-29): 같은 이름·코드 중복 리스팅은 담당자가 상품 오입력→수정 불가라 죽은 걸
       판매중지시킨 재등록이 흔함 → 동률권에서 판매중지 빼 **live 유일이면 확정**. 다 판매중지면 원본 유지.
    ⓑ 규격토큰(_SPEC=숫자시작)·모델코드(_CODE_TAIL: ST6645·BG001 등 문자시작)로 정확히 1개면 확정(보조키·정체성 아님).
    ⓒ 그래도 여럿이고 **모두 같은 이름**이면 = 같은 등록상품명의 별도 상품(다른 vid/가격) → 병합 신호(별도 블록).
    """
    tied = [di for rc, di in scored if (best - rc) < _MARGIN]                # 동률권(마진 이내) 후보들
    live = [di for di in tied if getattr(discovered[di], "sale_status", "") != "판매중지"]
    if len(live) == 1:
        return ("match", live[0], [])                                        # 판매중지 제외 후 live 유일 → 확정
    sub = live or tied                                                       # 다 live → 보조키 / 다 판매중지 → 원본
    lspec = _spec_tokens(core_text)
    thit = [di for di in sub if lspec & _spec_tokens(_title(discovered[di]))] if lspec else []
    if len(thit) != 1:
        lcode = _code_tokens(core_text)
        if lcode:
            chit = [di for di in sub if lcode & _code_tokens(_title(discovered[di]))]
            if len(chit) == 1:
                thit = chit
    if len(thit) == 1:
        return ("match", thit[0], [])                                       # 규격/코드로 유일 확정
    if len(live) > 1 and len({ndisc[di] for di in live}) == 1:
        return ("merge", -1, live)                                          # 같은 이름 별도 상품 → 별도 블록
    return ("none", -1, [])                                                  # 여전히 애매 → 미매칭(오매칭 방지)


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
    w = build_idf([_title(d) for d in discovered] + [lp.name for lp in ledger])
    ndisc = [_norm(_title(d)) for d in discovered]   # 공백 제거 발견제목 — 정체성 매칭은 띄어쓰기 무관(부분일치)

    qualified: list[tuple[int, float, int, int]] = []   # (괄호정확?, 재현율, 대장i, 발견i)
    merge_groups: dict[int, list[int]] = {}             # 대장i → 같은 이름 다중 live 발견i들(별도 상품·병합 대상)
    for li, lp in enumerate(ledger):
        par = _norm(_paren(lp.name))
        # ① 괄호 노출제목 정확일치(대장 형식 '코드 (노출제목)')
        if par:
            hit = next((di for di in range(len(discovered))
                        if par == ndisc[di] or par in ndisc[di] or ndisc[di] in par), None)
            if hit is not None:
                qualified.append((1, 1.0, li, hit))
                continue
        # ② 핵심어 게이트 + IDF 재현율 + 마진. 대장 **본문**(코드·상품명)에 정체성 토큰이 있으면 본문 우선으로
        # 매칭하고 괄호(색상/옵션/메모)는 무시 — 담당자 대장 본문명을 최대한 존중(원인②). 본문이 코드뿐이면
        # 괄호(노출제목)로 폴백. ⚠괄호 정확일치는 위 ①에서 이미 처리(여기 도달=①실패).
        base_toks = {t for t in _tokens(lp.name) if t not in brand} or set(_tokens(lp.name))
        if base_toks:
            core_text, ptoks = lp.name, base_toks       # 본문 우선(괄호=색상/옵션/메모 무시)
        else:
            core_text = _paren(lp.name) or lp.name       # 본문이 코드뿐 → 괄호(노출제목) 폴백
            ptoks = {t for t in _tokens(core_text) if t not in brand} or set(_tokens(core_text))
        if not ptoks:
            continue                                    # 순수 코드명·괄호도 없음 → 미매칭(공란)
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
            # 애매(마진 미달=변형/중복 동점) → 보조키 해소(판매중지 제외·규격·모델코드) 또는 같은 이름 병합(_tiebreak).
            kind, di, dis = _tiebreak(core_text, scored, discovered, ndisc, best)
            if kind == "match":
                qualified.append((0, best, li, di))
            elif kind == "merge":
                merge_groups[li] = dis
        # else: 재현율 미달/보조키도 애매 → 미매칭(공란, 오매칭 방지)

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
    # 같은 이름 별도 상품(다중 live) 병합 — 1:1 매칭에서 안 쓰인 것만. 여럿이면 옵션 여러 개인 한 Product 로
    # 병합해 호출부의 옵션 분리가 별도 블록을 만들게 한다(라벨=itemName). 하나만 남으면 그것으로 매칭.
    for li, dis in merge_groups.items():
        if li in used_l:
            continue
        avail = [di for di in dis if di not in used_d]
        if not avail:
            continue
        res[li] = discovered[avail[0]] if len(avail) == 1 else _merge_same_name(discovered, avail)
        used_l.add(li)
        used_d.update(avail)
    return res


def _merge_same_name(discovered: list[Product], dis: list[int]) -> Product:
    """같은 이름 별도 상품(다른 vid) 여러 개 → **옵션 여러 개인 한 Product** 로 병합(호출부 옵션 분리로 별도 블록).

    블록 구분 라벨 = 옵션 itemName(products_from_vendor_inventory 가 보존). 라벨이 비거나 겹치면 vid 꼬리로 유니크화.
    이름/구분/판매상태는 첫 상품 기준(같은 이름이라 동일)."""
    d0 = discovered[dis[0]]
    opts: list[Option] = []
    seen: set[str] = set()
    for di in dis:
        for o in discovered[di].options:
            lbl = (o.label or "").strip() or (o.vendor_item_ids[0][-4:] if o.vendor_item_ids else "")
            base_lbl, k = lbl, 2
            while lbl in seen:
                lbl = f"{base_lbl} #{k}"
                k += 1
            seen.add(lbl)
            opts.append(Option(label=lbl, vendor_item_ids=list(o.vendor_item_ids),
                               product_ids=list(o.product_ids)))
    return Product(name=_title(d0), title=_title(d0), kind=d0.kind, options=opts,
                   sale_status=d0.sale_status)


def _base_name(name: str) -> str:
    """색상/옵션 괄호를 뗀 base(마지막 ' (' 이후 제거) — 색상별 대장 줄을 한 상품군으로 묶는 그룹키."""
    return name.rsplit(" (", 1)[0].rstrip() if " (" in name else name


def _spec_in_label(spec: str, label: str) -> bool:
    """대장 괄호 색상(spec)이 쿠팡 옵션 라벨에 포함되는가(공백무시 부분일치). 예 '블랙'⊂'블랙 Free'."""
    s = _norm(spec)
    return bool(s) and s in _norm(label)


def _is_variant(d: Product) -> bool:
    """발견상품이 **색상형**(구분되는 라벨의 옵션 2개 이상) — 색상 배정/미배정 판정 대상."""
    labs = {(o.label or "").strip() for o in d.options if (o.label or "").strip()}
    return len(d.options) >= 2 and len(labs) >= 2


def _color_overrides(ledger: list[Product], discovered: list[Product],
                     res: dict[int, Product]) -> dict[int, object]:
    """색상별 대장 줄 → 그 색상 옵션만 배정(소유자 2026-09-29). 반환 {대장i: (발견상품, [Option]) | None(미매칭)}.

    - #1 대장 괄호 색상이 발견 옵션 라벨에 있으면 그 옵션만 배정(색상별 별도 블록).
    - #2 색상 줄이 2개 이상(명확한 색상 분리)인데 그 색상이 옵션에 없으면 미매칭(오매칭 방지).
    - #3 색상 지정 없는 줄·단일 괄호(메모일 수 있음)는 손대지 않음(기존 전체 매칭 유지).
    """
    from collections import defaultdict
    groups: dict[str, list[int]] = defaultdict(list)
    for li, lp in enumerate(ledger):
        groups[_norm(_base_name(lp.name))].append(li)
    overrides: dict[int, object] = {}
    for _base, lis in groups.items():
        color_lis = [li for li in lis if _norm(_paren(ledger[li].name))]
        if not color_lis:
            continue                                   # #3 색상 지정 없음
        d = next((res[li] for li in lis if res.get(li) is not None), None)
        if d is None:
            continue                                   # 그룹 전체 미매칭 → 색상 근거 없음(기존 유지)
        strict = len(color_lis) >= 2                    # 색상 줄 2개↑ = 명확한 색상 분리
        for li in color_lis:
            spec = _paren(ledger[li].name)
            opts = [o for o in d.options if _spec_in_label(spec, o.label)]
            if opts:
                overrides[li] = (d, opts)              # #1 색상별 옵션 배정
            elif strict and _is_variant(d):
                overrides[li] = None                   # #2 색상 없음(2줄↑·색상형) → 미매칭
            # else: 메모/단일 → 손대지 않음(#3)
    return overrides


def scope_to_ledger(ledger: list[Product], discovered: list[Product]) -> tuple[list[Product], int]:
    """대장 상품만 추적 대상으로. 반환: (추적 Product 목록, 매칭된 개수).

    매칭 상품 = 발견 노출제목/vid/구분 부여(시트 표시=노출제목). 미매칭 = 대장명으로 추적(지표·재고 공란).
    **색상별 대장 줄**(신형타프 (블랙)/(베이지))은 그 색상 옵션(vid)만 배정해 별도 블록·별도 계정목록 줄이
    되게 한다(소유자 2026-09-29·재고관리상 색상 분리). 색상 지정 없는 줄은 기존대로 전체 옵션.
    """
    res = _assign(ledger, discovered)
    over = _color_overrides(ledger, discovered, res)

    def _unmatched(lp: Product) -> Product:
        return Product(name=lp.name, title=lp.name, kind=config.KIND_PERSONAL, options=[Option("")],
                       mkt_start=lp.mkt_start, mkt_end=lp.mkt_end, mkt_mon=lp.mkt_mon,
                       inbound_summary=lp.inbound_summary, discontinued=lp.discontinued)

    def _tracked(lp: Product, d: Product, opts: list[Option], name: str) -> Product:
        return Product(name=name, title=name, kind=d.kind,
                       options=[Option(o.label, list(o.vendor_item_ids), list(o.product_ids)) for o in opts],
                       mkt_start=lp.mkt_start, mkt_end=lp.mkt_end, mkt_mon=lp.mkt_mon,
                       inbound_summary=lp.inbound_summary, discontinued=lp.discontinued)   # 대장 마케팅·입고·판매중지 이월

    out: list[Product] = []
    matched = 0
    for li, lp in enumerate(ledger):
        if li in over:
            ov = over[li]
            if ov is None:                             # #2 색상 미매칭
                out.append(_unmatched(lp))
            else:                                       # #1 색상별 배정 — 블록명에 색상 옵션 라벨 붙여 구분
                d, opts = ov                            # type: ignore[misc]
                nm = f"{_title(d)} ({opts[0].label})" if (opts and opts[0].label) else _title(d)
                out.append(_tracked(lp, d, opts, nm))
                matched += 1
            continue
        d = res.get(li)
        if d is not None:
            out.append(_tracked(lp, d, list(d.options), _title(d)))
            matched += 1
        else:
            out.append(_unmatched(lp))
    return out, matched


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
            mkt_start=lp.mkt_start, mkt_end=lp.mkt_end, mkt_mon=lp.mkt_mon,
                               inbound_summary=lp.inbound_summary)   # 대장 마케팅·입고요약 이월
        added += 1
    return out, added


def _tracked_from(lp: Product, d: Product) -> Product:
    """발견 상품 d 의 정체(노출명·vid·구분)를 부여하고 대장 lp 의 마케팅·입고요약·판매중지를 이월한 추적 Product."""
    return Product(
        name=_title(d), title=_title(d), kind=d.kind,
        options=[Option(o.label, list(o.vendor_item_ids), list(o.product_ids)) for o in d.options],
        mkt_start=lp.mkt_start, mkt_end=lp.mkt_end, mkt_mon=lp.mkt_mon,
        inbound_summary=lp.inbound_summary, discontinued=lp.discontinued)


def _vids_of(p: Product) -> set:
    return {v for o in p.options for v in o.vendor_item_ids}


def _ai_targets(tracked: list[Product], discovered: list[Product]) -> tuple[list[int], list[int], set]:
    """AI 폴백 대상 — (미매칭 대장 위치 idxs, 아직 안 쓰인 발견 di 후보, 쓰인 vid 집합)."""
    idxs = [i for i, tp in enumerate(tracked) if not _vids_of(tp)]
    used = {v for tp in tracked for v in _vids_of(tp)}
    cand = [di for di, d in enumerate(discovered) if not (used & _vids_of(d))]
    return idxs, cand, used


def _valid_pick(v, n: int) -> int:
    """0..n-1 범위의 정수면 그 값, 아니면 -1(잘못된 AI 응답 방어)."""
    try:
        i = int(v)
    except (TypeError, ValueError):
        return -1
    return i if 0 <= i < n else -1


def augment_ai(ledger: list[Product], tracked: list[Product], discovered: list[Product],
               matcher, log=None) -> tuple[list[Product], int]:
    """정밀·roster 매칭 후에도 **남은 미매칭** 대장 상품을 **AI 의미(문맥) 매칭**으로 보강(폴백·소유자 2026-09-29).

    토큰이 안 겹쳐도 의미가 같은 상품('목견인기'↔'거북목 교정기 견인기')을 잡는다. **미매칭에만** 적용하고
    정밀 매칭 결과는 안 건드린다. `matcher(대장명들, 후보제목들) -> {대장i: 후보i}` 주입식(오프라인 테스트는
    페이크·실 API 는 kw_ai). **확신 없으면 matcher 가 그 줄을 비운다 = 공란 유지(오매칭 방지)**. 이미 쓰인 vid
    후보 제외·한 후보는 한 대장에만(유일 배정). 반환: (보강된 tracked, AI로 채운 개수)."""
    log = log or (lambda m: None)
    idxs, cand, used = _ai_targets(tracked, discovered)
    if not idxs or not cand:
        return tracked, 0
    picks = matcher([ledger[i].name for i in idxs], [_title(discovered[di]) for di in cand]) or {}
    out = list(tracked)
    added = 0
    for u_local, c_local in picks.items():
        ui, ci = _valid_pick(u_local, len(idxs)), _valid_pick(c_local, len(cand))
        if ui < 0 or ci < 0:
            continue
        i, d = idxs[ui], discovered[cand[ci]]
        if _vids_of(d) & used:                                   # 이미 다른 대장에 배정 → 스킵(유일 배정)
            continue
        out[i] = _tracked_from(ledger[i], d)
        used |= _vids_of(d)
        added += 1
        log(f"  [AI매칭] '{ledger[i].name}' ↔ '{_title(d)}'(의미 매칭·미매칭 폴백)")
    return out, added
