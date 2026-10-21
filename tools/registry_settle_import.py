"""정산 계정 파일 → 셀독계정상품이력관리원장 '정산전용계정' 시트 1회 옮기기(D-103).

셀독원장(관리대장에서 들어온 계정)에 없는 계정만 옮긴다 — 이미 시트에 있는 계정ID 는 건너뜀(여러 번 실행해도 안전).
우리 사업자(디프·디프픽, D-088)는 구분=우리사업자. 출력에는 계정ID 만(비밀번호 출력 없음). 옮긴 뒤 이력 반영(정산전용이력).

실행: python tools/registry_settle_import.py [--dry-run] [--file data/정산_계정목록.txt]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from coupang_analytics import appconfig, gsheet_api, registry_gsheet as RG, registry_settle as RS  # noqa: E402
from coupang_analytics import settlement_accounts as SA  # noqa: E402

OWN_IDS = {"ski1121", "Difpick"}   # 우리 사업자(D-088 — 통보 제외)


def main() -> int:
    ap = argparse.ArgumentParser(description="정산 계정 파일 → 원장 정산전용계정 시트")
    ap.add_argument("--file", default="", help="정산 계정 파일(기본 = 설정 settlement/accounts_file 또는 data/정산_계정목록.txt)")
    ap.add_argument("--dry-run", action="store_true", help="옮길 계정만 보여 주고 쓰지 않음")
    args = ap.parse_args()
    url = appconfig.get("registry/url", "")
    if not url:
        print("원장 링크(설정 registry/url)가 비어 있음")
        return 1
    path = args.file or appconfig.get(SA.CONFIG_KEY, "") or SA.DEFAULT_PATH
    accts, warns = SA.read_accounts_file(path)
    for w in warns:
        print(f"  [계정 파일] {w}")
    client = gsheet_api.GSheetClient(url)
    in_registry = set(RG.load_registry(client).account_ids())
    todo = [a.account_id for a in accts if a.account_id not in in_registry]
    print(f"정산 계정 파일 {len(accts)}개 · 셀독원장에 있음 {len(accts) - len(todo)}개 · 정산전용 대상 {len(todo)}개: {todo}")
    if args.dry_run:
        return 0
    added = RS.import_rows(client, accts, in_registry, OWN_IDS, datetime.now().strftime("%Y-%m-%d"))
    print(f"정산전용계정 시트에 추가 {len(added)}개: {added}")
    RS.sync_settle(client, log=print)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
