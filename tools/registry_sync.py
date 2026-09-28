"""셀독등록원장 동기화 도구 — 관리대장(구글시트) → 셀독등록원장(구글시트) 1회 반영. SSOT=designs/LEDGER_REGISTRY.md.

로그인·수집 없음(구글시트만). 첫 실행이면 원장 시트 5개를 만들고 현재 대장 전체를 '최초등록'으로 넣는다.
이후 실행은 바뀐 것만 원장에 반영하고 계정이력·상품이력·그로스이력에 한 줄씩 추가한다(원장 줄은 지우지 않음).

사용:
  python tools/registry_sync.py --dry-run                   # 미리보기(원장에 쓰지 않음·변경 목록만)
  python tools/registry_sync.py                             # 실제 반영
  python tools/registry_sync.py --registry <원장 URL> --ledger <관리대장 URL> [--save-url]

URL 기본값 = 설정(config.json/레지스트리)의 registry/url(원장)·gsheet/input_url(관리대장).
--save-url 이면 지정한 원장 URL 을 설정(registry/url)에 저장한다.
⚠ 원장 파일은 서비스계정에 **편집자**로 공유돼 있어야 한다. 원장에는 비밀번호 원문이 저장된다(소유자 결정
2026-09-28) — 공유 범위를 소유자·담당자·서비스계정으로 한정할 것.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics import appconfig, gsheet_api, registry_gsheet  # noqa: E402
from coupang_analytics.credstore import CredStore  # noqa: E402
from coupang_analytics.input_list import read_ledger_rows  # noqa: E402
from coupang_analytics.registry import RegistryGuardError, RegistryIntegrityError  # noqa: E402


def _shared_setting(key: str) -> str:
    """config.json 우선·레지스트리(app_qt QSettings) 폴백 — tools/relink_index.py 와 같은 방식."""
    v = appconfig.get(key, "")
    if v:
        return v
    group, name = key.split("/", 1)
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Software\coupang-analytics\ui\{group}") as k:
            val, _ = winreg.QueryValueEx(k, name)
        return str(val).strip() if val else ""
    except (ImportError, OSError):
        return ""


def main() -> int:
    ap = argparse.ArgumentParser(description="관리대장 → 셀독등록원장 동기화")
    ap.add_argument("--registry", help="셀독등록원장 구글시트 URL(기본=설정 registry/url)")
    ap.add_argument("--ledger", help="셀독관리대장 구글시트 URL(기본=설정 gsheet/input_url)")
    ap.add_argument("--dry-run", action="store_true", help="미리보기(원장에 쓰지 않음)")
    ap.add_argument("--save-url", action="store_true", help="--registry URL 을 설정에 저장")
    args = ap.parse_args()

    registry_url = args.registry or _shared_setting("registry/url")
    ledger_url = args.ledger or _shared_setting("gsheet/input_url")
    if not registry_url:
        print("[중단] 셀독등록원장 URL 이 없습니다 — --registry 로 주거나 설정 registry/url 에 저장하세요.")
        return 1
    if not ledger_url:
        print("[중단] 관리대장 URL 이 없습니다 — --ledger 로 주거나 설정 탭에서 관리대장 링크를 등록하세요.")
        return 1
    if args.save_url and args.registry:
        appconfig.set("registry/url", args.registry)
        print("[설정] registry/url 저장")

    store = CredStore()
    try:
        client = gsheet_api.GSheetClient(registry_url, store=store, on_log=print)
        registry_gsheet.run_sync(client, lambda: read_ledger_rows(ledger_url, store=store),
                                 log=print, dry_run=args.dry_run)
    except (RegistryGuardError, RegistryIntegrityError) as exc:
        print(f"[중단] {exc}")
        return 2
    except (gsheet_api.GSheetError, ValueError) as exc:
        print(f"[중단] 구글시트/대장 오류 — 원장은 변경되지 않았습니다: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
