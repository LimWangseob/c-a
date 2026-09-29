"""핀 테스트 — L1 데이터 백본 '공개 API 계약' 고정.

배경: 커머스 앱을 L0(플랫폼)·L1(데이터 백본)·L2(도메인)·L3(조립)로 계층화(docs/ARCHITECTURE.md).
L2 도메인/L3 조립이 부르는 **L1 진입점(공개 API)** 을 계약으로 고정한다. 도메인 세션이 병렬로 편집하다
L1 시그니처를 무심코 바꾸면(파라미터 추가·삭제·이름변경·필수화, 함수 삭제) 이 핀이 즉시 빨개진다.

계약 범위·근거는 실측(호출처 grep)으로 확정 — 도메인/조립이 실제 부르는 것만. SSOT=docs/L1_CONTRACT.md.
registry 계열은 아직 live(pipeline·ui) 미연동이나 L1 백본으로 설계 확정·2단계(앱 연계) 대비 미리 고정.

비교 방식(견고성): 시그니처 **전체 문자열**(타입힌트·한글 기본값 표기)은 취약해서 쓰지 않고,
각 파라미터의 (종류, 이름, 기본값 유무)만 비교한다 = 계약 파괴는 잡되 타입힌트 정리엔 안 깨짐.
    P=위치/키워드 겸용 · K=키워드 전용 · A=*args · W=**kwargs · O=위치 전용 · 뒤 0/1=기본값 없음/있음

실행: python tools/pin_l1_contract.py (순수·결정적·로그인/실API 없음).
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics import (  # noqa: E402
    collector, gsheet_index, gsheet_stats, input_list, pipeline_gsheet,
    pipeline_sales, rank, registry, registry_gsheet, registry_model)
from coupang_analytics.workbook import OutputWorkbook  # noqa: E402

_KIND = {
    inspect.Parameter.POSITIONAL_OR_KEYWORD: "P",
    inspect.Parameter.KEYWORD_ONLY: "K",
    inspect.Parameter.VAR_POSITIONAL: "A",
    inspect.Parameter.VAR_KEYWORD: "W",
    inspect.Parameter.POSITIONAL_ONLY: "O",
}


def _struct(obj, name: str) -> str:
    """obj.name 의 파라미터 구조 문자열(종류:이름:기본값유무 공백연결)."""
    sig = inspect.signature(getattr(obj, name))
    parts = []
    for p in sig.parameters.values():
        has_default = "1" if p.default is not inspect.Parameter.empty else "0"
        parts.append(f"{_KIND[p.kind]}:{p.name}:{has_default}")
    return " ".join(parts)


# ── 골든 계약: 실측(호출처)으로 확정한 L1 공개 진입점의 파라미터 구조 ─────────────
# 모듈 함수형 진입점
FUNC_CONTRACTS: dict = {
    collector: [
        ("discover", "P:page:0 P:date_from:0 P:date_to:0 P:log:1"),
        ("fetch_sales_roster", "P:page:0 P:date_from:0 P:date_to:0 P:log:1"),
        ("fetch_vendor_inventory", "P:page:0 P:log:1"),
        ("fetch_inventory", "P:page:0 P:log:1"),
        ("fetch_product_ids", "P:page:0 P:vendor_inventory_ids:0 P:log:1"),
        ("products_from_vendor_inventory", "P:listings:0 P:log:1"),
        ("sale_status_by_vid", "P:listings:0 P:log:1"),
        ("save_discovered", "P:account_id:0 P:products:0"),
        ("reset_raw", ""),
        ("raw_dumps", ""),
        ("kind_of", "P:registration_types:0"),
        ("sale_status_of", "P:product_status:0"),
        ("vid_meta_of", "P:listings:0"),
    ],
    input_list: [
        ("parse_input_list", "P:path:0"),
        ("parse_input_rows", "P:rows:0 P:strike_grid:1"),
        ("parse_password_file", "P:path:0"),
        ("parse_password_rows", "P:rows:0"),
        ("read_ledger_rows", "P:url_or_id:0 K:store:1 K:sa_path:1"),
        ("write_ledger_inventory", "P:client:0 P:wb:0 P:on_log:1 K:sheet:1"),
        ("validate_input_list", "P:il:0"),
        ("build_idf", "P:names:0"),
    ],
    gsheet_index: [
        ("roster_from_workbook", "P:wb:0 P:stats_gids:0"),
        ("sync_index", "P:client:0 P:desired:0 K:sheet:1 K:on_log:1"),
        ("delete_accounts", "P:client:0 P:removed:0 K:sheet:1 K:on_log:1"),
        ("delete_renamed_accounts", "P:client:0 P:renamed:0 K:sheet:1 K:on_log:1"),
        ("read_marketing", "P:client:0 K:sheet:1"),
        ("apply_marketing", "P:accounts:0 P:marketing_map:0"),
        ("plan_sync", "P:existing:0 P:desired:0"),
        ("marketing_key", "P:account_id:0 P:product:0"),
    ],
    gsheet_stats: [
        ("merge_staff_keywords", "P:client:0 P:wb:0 K:on_log:1"),
        ("push_statistics", "P:client:0 P:wb:0 K:on_log:1"),
        ("read_staff_keywords", "P:client:0 P:wb:0"),
        ("worksheet_to_requests", "P:ws:0 P:sheet_id:0 P:index_gid:1"),
    ],
    pipeline_gsheet: [
        # ⚠ 옛 이름 _push_gsheet·_pull_gsheet_keywords 를 공개 이름으로 정리(2026-09-28).
        ("push_gsheet", "P:wb:0 P:output_url:0 P:log:0 P:removed_accounts:1 P:renamed_accounts:1"),
        ("pull_gsheet_keywords", "P:wb:0 P:output_url:0 P:log:0"),
        ("backup_sources", "P:out_dir:1 K:input_url:1 K:output_url:1 K:on_log:1"),
        ("restore_master_from_gsheet", "P:out_dir:0 P:url:0 P:on_log:1"),
        ("push_ledger_inventory", "P:input_url:0 P:log:0 P:out_dir:1"),
    ],
    registry: [
        ("sync", "P:reg:0 P:snap:0 K:now:0"),
        # 2단계(§10-1): 원장→앱 입력 변환·직전 비번(registry_input, registry 재수출)
        ("previous_password", "P:reg:0 P:account_id:0"),
        ("to_input_list", "P:reg:0 P:as_of:1 K:on_log:1"),
        ("password_map", "P:reg:0"),
    ],
    registry_gsheet: [
        ("run_sync", "P:client:0 P:read_ledger:0 K:now:1 K:log:1 K:dry_run:1 K:backup_dir:1 K:lock_path:1"),
        ("run_backfill", "P:client:0 P:snapshots:0 K:log:1 K:dry_run:1 K:backup_dir:1 K:lock_path:1"),
        ("load_registry", "P:client:0"),
        ("save_registry", "P:client:0 P:reg:0 P:res:0 P:now:0"),
        # 2단계(§10-1): 쿠팡확인 줄 단위 쓰기(이력 미기록·두 열만 RAW)
        ("write_coupang_check", "P:client:0 P:checks:0 K:dry_run:1 K:on_log:1 K:lock_path:1"),
    ],
    registry_model: [
        ("parse_ledger", "P:rows:0 P:strike_grid:1 P:sheet:1"),
    ],
    # 2-3(§10-1): 한 계정 반자동 1회 로그인 공개 진입점(UI [이전 비번 1회]용·pipeline 재수출)
    pipeline_sales: [
        ("try_login_once", "P:account_id:0 P:password:0 K:on_log:1"),
    ],
    # rank = L1 조회 프리미티브(2026-09-28 재분류·R4 확정). collector 와 동급 순위 조회 수단.
    # 도메인(kw_recommend·kw_metrics)+조립(pipeline_sales/process/ranks)이 공유 → "도메인→L1" 합법.
    rank: [
        ("warmup", "P:browser:0"),
        ("make_matcher", "P:product_ids:1 P:vendor_item_ids:1 P:name_substr:1"),
        ("human_type_query", "P:page:0 P:text:0"),
        ("organic_ranks", "P:browser:0 P:keyword:0 P:matchers:0 P:max_rank:1 P:mobile:1 P:log:1 P:matched_out:1"),
        ("organic_ranks_batch", "P:browser:0 P:keywords:0 P:matchers:0 P:max_rank:1 P:mobile:1 P:log:1"),
        ("organic_rank", "P:browser:0 P:keyword:0 P:matches:0 P:max_rank:1"),
        ("extract_items", "P:page:0"),
        ("parse_serp_rank", "P:page:0 P:matchers:0 P:max_rank:1"),
    ],
}

# OutputWorkbook 핵심 기록/조회 메서드(파라미터 구조까지 고정)
WB_CONTRACTS = [
    ("load", "P:path:0"),
    ("empty", ""),
    ("save", "P:self:0 P:path:0"),
    ("apply_style", "P:self:0"),
    ("ensure_product_block",
     "P:self:0 P:biz:0 P:product:0 P:kind:0 P:keywords:0 K:rank_rows:1 K:registered:1"),
    ("set_product_metric", "P:self:0 P:biz:0 P:product:0 P:metric:0 P:date_iso:0 P:value:0"),
    ("set_keyword_rank",
     "P:self:0 P:biz:0 P:product:0 P:keyword:0 P:date_iso:0 P:rank:0 P:scanned:1"),
    ("add_product_keywords", "P:self:0 P:biz:0 P:product:0 P:keywords:0"),
    ("reconcile_account",
     "P:self:0 P:biz:0 P:seen_products:0 P:ledger_products:1 P:delete_missing:1 P:account_id:1"),
    ("delete_account", "P:self:0 P:biz:0"),
    ("delete_product_block", "P:self:0 P:biz:0 P:product:0"),
    ("apply_sale_status", "P:self:0 P:biz:0 P:status_by_vid:0"),
]

# OutputWorkbook 실사용 메서드 전체(이름 존재만 — 계약 표면이 사라지면 잡음).
# 근거=조립계층(pipeline_process·pipeline·pipeline_ranks) + 입력/시트 계층 실측 호출.
WB_PRESENT = sorted(set([
    # 생성/직렬화
    "load", "empty", "save", "apply_style",
    # 기록
    "set_product_metric", "ensure_product_block", "add_product_keywords", "set_keyword_search",
    "set_title_cache", "set_keyword_rank", "set_product_kind", "set_product_extra",
    "set_product_pid", "set_product_vids", "set_display_name", "set_product_account_id",
    "set_discontinued", "set_marketing", "ensure_account", "reconcile_account",
    "delete_product_block", "set_account_id", "set_representative", "apply_sale_status",
    "mark_sales_collected", "merge_account", "sync_discontinued_from_ledger", "delete_account",
    "reset_date_column", "clear_sales_stamps", "pad_keyword_rows",
    # 조회
    "keyword_search", "title_cache", "is_rank_filled", "product_keywords", "has_product",
    "resolve_block_name", "blocks_with_registered_name", "product_vids", "products_of",
    "has_marketing", "product_due", "account_sheets", "account_ids_of", "account_id_of",
    "latest_date", "rank_suppressed", "sibling_vids", "data_quality_summary", "inventory_by_biz",
    "product_roster", "product_account_id", "status_of", "representative_of", "account_due",
]))

# 데이터클래스/예외 계약(도메인이 import 하는 타입 — 사라지면 import 깨짐).
TYPE_CONTRACTS = [
    (collector, ["VendorInventoryOption", "VendorInventoryListing",
                 "SalesFetchError", "InventoryFetchError", "VendorInventoryFetchError"]),
    (input_list, ["Account", "Product", "Option", "InputList", "InputValidationError"]),
    (registry, ["Registry"]),
    (registry_model, ["COUPANG_CHECK_VALUES"]),   # 2-2 쿠팡확인 값 6종(오타 방지 상수)
    (rank, ["SearchItem", "RankBlocked"]),
]


def _check(cond: bool, msg: str) -> None:
    print(f"    {'[통과]' if cond else '[실패]'} {msg}")
    if not cond:
        raise AssertionError(msg)


def pin_func_contracts() -> None:
    print("[핀 L1-1] 함수형 진입점 파라미터 구조 — collector·input_list·gsheet_*·pipeline_gsheet·registry")
    for mod, items in FUNC_CONTRACTS.items():
        modname = mod.__name__.split(".")[-1]
        for name, golden in items:
            _check(hasattr(mod, name), f"{modname}.{name} 존재")
            got = _struct(mod, name)
            _check(got == golden, f"{modname}.{name} 파라미터 구조 = {golden!r}"
                   + ("" if got == golden else f"  (현재: {got!r})"))


def pin_workbook_contracts() -> None:
    print("[핀 L1-2] OutputWorkbook 핵심 기록/조회 메서드 파라미터 구조")
    for name, golden in WB_CONTRACTS:
        _check(hasattr(OutputWorkbook, name), f"OutputWorkbook.{name} 존재")
        got = _struct(OutputWorkbook, name)
        _check(got == golden, f"OutputWorkbook.{name} 파라미터 구조 = {golden!r}"
               + ("" if got == golden else f"  (현재: {got!r})"))


def pin_workbook_present() -> None:
    print(f"[핀 L1-3] OutputWorkbook 실사용 메서드 전체 존재({len(WB_PRESENT)}개)")
    missing = [n for n in WB_PRESENT if not callable(getattr(OutputWorkbook, n, None))]
    _check(not missing, "실사용 메서드 전부 존재"
           + ("" if not missing else f"  (누락: {missing})"))


def pin_types() -> None:
    print("[핀 L1-4] 도메인이 import 하는 데이터클래스/예외 타입 존재")
    for mod, names in TYPE_CONTRACTS:
        modname = mod.__name__.split(".")[-1]
        for name in names:
            _check(hasattr(mod, name), f"{modname}.{name} 존재")


def main() -> int:
    print("=" * 64)
    print("  핀 테스트 — L1 데이터 백본 공개 API 계약")
    print("=" * 64)
    pin_func_contracts()
    pin_workbook_contracts()
    pin_workbook_present()
    pin_types()
    print("=" * 64)
    print("  [완료] L1 계약 핀 모두 통과")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
