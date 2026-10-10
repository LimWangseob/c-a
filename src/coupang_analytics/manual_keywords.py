"""키워드 추천 탭 [선택 키워드 저장] → **결과파일의 그 상품 블록에 키워드 추가** + 결과 구글시트 반영(F2·D-033).

예전엔 `keyword_store`(data/keywords.json)에 쓰기만 하고 아무도 읽지 않아 저장해도 결과에 반영되지 않았다.
- 탭의 상품명 = **관리대장 상품명**, 결과 블록 이름 = 쿠팡 노출상품명 → ①이 남긴 매칭 고정(`_매칭고정.json`, 대장 줄→VID)으로
  블록을 찾는다(`resolve_block_name`). 매칭 기록이 없으면(아직 ①에서 매칭 안 됨) 저장하지 않고 이유를 알린다.
- 기존 키워드는 그대로 두고 **추가만**(상한 `KW_MAX_TRACK`). 이미 있는 키워드는 건너뜀(띄어쓰기 다르면 별개).
- 결과 구글시트가 키워드의 기준(① 시작 때 시트 값으로 동기화)이라 **저장 직후 시트에도 반영**한다 — 안 하면 다음 ①이 지움.
"""
from __future__ import annotations

from pathlib import Path

from . import config
from .match_anchor import anchor_path, key_of, load_anchors
from .pipeline_gsheet import push_gsheet
from .pipeline_paths import _load_latest_wb


class ManualKeywordError(Exception):
    """저장할 수 없음(매칭 기록·결과파일·블록 없음) — 호출부(UI)가 그대로 안내한다."""


def _target_block(wb, business: str, vids) -> str | None:
    """VID 로 찾은 블록 — 다중옵션이면 키워드 칸이 있는 **대표 블록**(같은 등록상품명)을 고른다."""
    block = wb.resolve_block_name(business, vids)
    if block is None or wb.has_keyword_section(business, block):
        return block
    reg = wb.registered_name(business, block)
    for p in wb.products_of(business):
        if reg and wb.registered_name(business, p) == reg and wb.has_keyword_section(business, p):
            return p
    return block


def apply_manual_keywords(account_id: str, business: str, ledger_name: str, keywords: list[str], *,
                          out_dir: str = "output", gsheet_output_url: str | None = None, on_log=None) -> list[str]:
    """대장 상품(계정ID·사업자·대장명)의 결과 블록에 키워드를 추가하고 저장·결과시트 반영. 반환 = 실제 추가한 키워드."""
    log = on_log or (lambda m: None)
    out = Path(out_dir)
    rec = load_anchors(account_id, anchor_path(out)).get(key_of(ledger_name))
    if not rec:
        raise ManualKeywordError(f"'{ledger_name}' 은 아직 ①판매수집에서 쿠팡 상품과 매칭되지 않아 결과파일 블록이 없습니다 "
                                 "— ① 판매수집 후 다시 저장하세요")
    wb, path = _load_latest_wb(out)
    if wb is None:
        raise ManualKeywordError("결과파일이 없습니다 — ① 판매수집을 먼저 실행하세요")
    block = _target_block(wb, business, rec.get("vids") or [])
    if block is None:
        raise ManualKeywordError(f"결과파일 '{business}' 시트에서 '{ledger_name}'(VID {rec.get('vids')}) 블록을 찾지 못했습니다")
    wb.ensure_keyword_section(business, block)
    room = max(0, config.KW_MAX_TRACK - len(wb.product_keywords(business, block)))
    want = [k.strip() for k in keywords if k and k.strip()]
    added = wb.add_product_keywords(business, block, want[:room] if room < len(want) else want)
    if len(want) > room:
        log(f"  [키워드 저장] 상한 {config.KW_MAX_TRACK}개 초과분 제외: {want[room:]}")
    if added:
        wb.pad_keyword_rows(business, block)
        wb.apply_style()
        wb.save(path)
        push_gsheet(wb, gsheet_output_url, log)
    log(f"== [키워드 저장] [{business}] {block} ← 추가 {added}" + ("" if added else " (모두 이미 있음 — 변경 없음)") + " ==")
    return added


__all__ = ["ManualKeywordError", "apply_manual_keywords"]
