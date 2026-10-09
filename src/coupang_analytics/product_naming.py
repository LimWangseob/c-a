"""결과 블록 이름 현행화 — ③순위 검색결과의 **실제 노출상품명**으로(D-013 보완·소유자 2026-10-09).

①판매수집은 판매분석(당일·최근 30일)으로 노출명을 확인하지만, 그 기간 조회·판매가 없는 상품은 거기 안 나온다.
③순위 검색에서 그 상품(같은 VID)이 잡히면 검색결과의 노출명이 **지금 쿠팡에 보이는 이름**이므로 그날 바로 블록
이름을 바꾼다(같은 VID → set_display_name 으로 이력 승계). 소유자: "노출명이 매칭 안 되면 오류·반드시 현행화".

검색결과 노출명 = "{제목}, {옵션1}, {옵션2}" → 첫 콤마 앞이 제목(collector._option_label 과 같은 관례).
같은 등록상품명의 옵션 블록들('제목 (옵션라벨)')도 함께 바꾼다(라벨 유지). pipeline_ranks 가 상품 하나의 키워드
기록을 다 끝낸 뒤 호출(도중에 이름을 바꾸면 남은 키워드 기록 키가 어긋남).
"""
from __future__ import annotations


def serp_title(name: str) -> str:
    """검색결과 노출명에서 제목(첫 콤마 앞)만, 공백 정규화."""
    return " ".join(str(name or "").split(",")[0].split())


def _label_of(block: str) -> str:
    return block.rsplit(" (", 1)[1][:-1] if " (" in block and block.endswith(")") else ""


def rename_to_exposed(wb, biz: str, pname: str, serp_name: str, log) -> str:
    """대표 블록 pname 과 같은 상품(같은 등록상품명)의 옵션 블록들을 검색 노출명 제목으로 바꾼다. 반환=대표 블록의 새 이름.
    다른 상품 블록이 이미 그 이름이면 바꾸지 않고 경고(병합 방지)."""
    title = serp_title(serp_name)
    if not title:
        return pname
    reg = wb.registered_name(biz, pname)
    blocks = wb.blocks_with_registered_name(biz, reg) if reg else []
    if pname not in blocks:
        blocks = [pname]
    multi = len(blocks) > 1
    new_rep = pname
    for blk in blocks:
        label = _label_of(blk) if multi else ""
        want = f"{title} ({label})" if label else title
        if want == blk:
            continue
        if wb.has_product(biz, want):
            log(f"  [상품명] ⚠ 검색 노출명 '{want}' 은 이미 다른 상품 블록 이름 — 현행화 못 함(확인 필요)")
            continue
        if wb.set_display_name(biz, blk, want):
            log(f"  [상품명] 현행화(검색 노출명) '{blk}' → '{want}'(같은 VID·이력 승계)")
            if blk == pname:
                new_rep = want
    return new_rep
