"""셀독등록원장 2단계 — UI 공용 도우미(Qt 없음 · app_qt/app 양쪽이 호출).

원장 로직은 전부 registry/registry_gsheet(D8) 것을 **호출만** 한다. 여기엔 화면이 쓰는 얇은 묶음만 둔다.
SSOT=designs/LEDGER_REGISTRY.md §10-1 (2-1 원장 자동 반영 · 2-3 이전 비밀번호 · 2-4 입력소스 원장).
"""
from __future__ import annotations

from coupang_analytics import gsheet_api, registry, registry_gsheet
from coupang_analytics.input_list import read_ledger_rows

SOURCE_REGISTRY = "registry"          # QSettings input/source 값(원장)
KEY_URL = "registry/url"              # 원장 구글시트 링크(입력 관리대장·결과 시트와 별도)
CHECK_PW_MISMATCH = "비밀번호불일치"   # registry_model.COUPANG_CHECK_VALUES 중 2-3 대상


def load(registry_url: str, store, log=None):
    """원장 구글시트 → Registry(읽기 전용)."""
    return registry_gsheet.load_registry(gsheet_api.GSheetClient(registry_url, store=store, on_log=log))


def sync(registry_url: str, input_url: str, store, log, *, dry_run: bool = False):
    """대장 → 원장 동기화 1회(dry_run=True 면 미리보기·쓰기 없음). 실패는 예외로 올린다(호출부가 판단)."""
    client = gsheet_api.GSheetClient(registry_url, store=store, on_log=log)
    return registry_gsheet.run_sync(client, lambda: read_ledger_rows(input_url, store=store),
                                    log=log, dry_run=dry_run)


def presync(registry_url: str, input_url: str, store, log) -> bool:
    """실행 시작(백업 직후) 원장 자동 반영 — **비치명**: 실패는 로그로 남기고 실행은 계속한다.

    원장 링크가 없으면 원장 미사용(조용히 건너뜀·기존 동작 그대로). 대장 링크가 없으면 반영할 원본이
    없으므로 로그로 알리고 건너뛴다. 반환=반영 성공 여부."""
    if not registry_url:
        return False
    if not input_url:
        log("[원장] 관리대장(입력) 링크가 없어 원장 자동 반영을 건너뜁니다")
        return False
    log("[원장] 실행 전 원장 자동 반영(관리대장 → 원장)…")
    try:
        sync(registry_url, input_url, store, log)
        return True
    except Exception as exc:
        log(f"[원장] 자동 반영 실패({exc.__class__.__name__}): {exc} — 원장 없이 실행을 계속합니다")
        return False


def load_input(registry_url: str, store, log):
    """입력소스=원장: 관리중 계정·상품 InputList + 관리중 계정 비밀번호 맵. 실패는 예외로 올린다."""
    reg = load(registry_url, store, log)
    return registry.to_input_list(reg, on_log=log), registry.password_map(reg)


def password_mismatch_accounts(reg) -> list[tuple[str, str, str]]:
    """쿠팡확인='비밀번호불일치'인 계정 → [(계정아이디, 사업자명, 확인일)] (계정당 1줄, 원장 순서)."""
    out: dict[str, tuple[str, str, str]] = {}
    for (aid, _), row in reg.rows.items():
        if row.coupang == CHECK_PW_MISMATCH and aid not in out:
            out[aid] = (aid, row.acct.get("사업자명", ""), row.coupang_date)
    return list(out.values())
