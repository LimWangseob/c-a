#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""샵마인 계정 비번 ↔ 관리대장(구글시트) 동기화 CLI (D-195).

앱(ui/app_qt.py)이 하루 1회 자동으로 도는 것과 **같은 코어**(coupang_analytics.shopmine_sync)를 쓴다. 이 CLI 는
①로그인 자격 저장(setup) ②응답 필드명·건수 확인(discover) ③수동 1회 동기화(sync) ④네트워크 없는 검증(selftest).

보안: 비번은 getpass 로 받아 화면·로그에 안 보이고, credstore(DPAPI·이 PC 전용)에만 저장한다. discover 는 값 없이
필드명·건수만 출력한다. 본인 계정·본인 데이터. 샵마인 약관상 비공식 접근 제한 가능성 유의(저빈도 호출).

사용 예:
  py -3.12 tools/shopmine_sync.py setup
  py -3.12 tools/shopmine_sync.py discover
  py -3.12 tools/shopmine_sync.py sync                 # 설정 탭 관리대장 링크 사용(gsheet/input_url)
  py -3.12 tools/shopmine_sync.py sync --url <관리대장 URL/ID>
  py -3.12 tools/shopmine_sync.py selftest
"""
from __future__ import annotations

import argparse
import getpass
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from coupang_analytics import appconfig, shopmine_sync as sm   # noqa: E402
from coupang_analytics.credstore import CredStore               # noqa: E402


def cmd_setup(a) -> None:
    print("샵마인 로그인 정보를 저장합니다(비밀번호는 화면·로그에 안 보입니다).")
    print("※ 본인 계정·본인 데이터에만 사용하세요. 샵마인 약관상 비공식 접근이 제한될 수 있습니다.\n")
    company = a.company_id or input("업체 ID(CompanyId): ").strip()
    user = a.user_id if a.user_id is not None else input("사용자 ID(UserId, 대표계정이면 비우고 Enter): ").strip()
    pw = getpass.getpass("비밀번호(UserPassword, 화면에 안 보임): ")
    if not pw:
        sys.exit("비밀번호가 비었습니다. 중단.")
    creds = {
        "CompanyId": company, "UserId": user, "UserPassword": pw,
        "OsVersion": a.os_version, "ShopmineVersion": a.shopmine_version,
        "IdKey": a.id_key, "PwKey": a.pw_key,
        "StartPage": a.start_page, "PageSize": a.page_size, "PwHash": a.pw_hash,
    }
    sm.store_login(creds, CredStore())
    del pw, creds
    print("\n저장 완료(DPAPI·이 PC 현재 사용자 전용). 커밋·공유 금지.")
    print("다음: discover 로 필드명·건수 확인 → sync.")


def cmd_discover(a) -> None:
    creds = sm.load_login(CredStore())
    if creds is None:
        sys.exit("로그인 정보 없음 — 먼저 setup.")
    _, authkey, login_resp = sm.do_login(creds, print)
    print("\n--- 로그인 응답 최상위 키(값 숨김) ---")
    print(", ".join(sorted(login_resp.keys())) if isinstance(login_resp, dict) else "(리스트 응답)")
    recs, first = sm.fetch_accounts(creds, authkey, int(creds.get("PageSize", sm.PAGE_SIZE_DEFAULT)),
                                    int(creds.get("StartPage", sm.START_PAGE_DEFAULT)), max_pages=1, log=print)
    print("\n--- market_account 응답 최상위 키 ---")
    print(", ".join(sorted(first.keys())) if isinstance(first, dict) else "(리스트 응답)")
    print(f"--- 계정 레코드 {len(recs)}건(첫 페이지), 첫 레코드 필드명 ---")
    for k in sm.masked_keys(recs):
        print(f"  - {k}")
    print(f"\n계정ID·비번 필드(정적분석 추정 {sm.ID_KEY_DEFAULT}/{sm.PW_KEY_DEFAULT})를 확인하세요. 다르면 "
          "setup --id-key/--pw-key 로 다시 저장. 값은 출력하지 않았습니다.")


def cmd_sync(a) -> None:
    url = (a.url or appconfig.get("gsheet/input_url")).strip()
    if not url:
        sys.exit("관리대장 링크가 없습니다 — --url 로 주거나 앱 설정 탭에 등록(gsheet/input_url)하세요.")
    from coupang_analytics.input_list import read_ledger_rows
    store = CredStore()
    sheet, rows, _ = read_ledger_rows(url, store=store)
    print(f"관리대장 '{sheet}' {len(rows)}행 읽음. 샵마인 서버에서 현재 비번 받아 대조·갱신…")
    out = sm.run_daily_sync(url, sheet, rows, store=store, log=print)
    print(f"완료: {out}")


def cmd_selftest(a) -> None:
    import subprocess
    r = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1]
                                            / "tools" / "verify_shopmine_sync_offline.py")])
    sys.exit(r.returncode)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="샵마인 계정 비번 ↔ 관리대장 동기화 CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("setup", help="샵마인 로그인 자격 DPAPI 저장(getpass)")
    sp.add_argument("--company-id")
    sp.add_argument("--user-id")
    sp.add_argument("--os-version", default="Windows")
    sp.add_argument("--shopmine-version", default="", help="거부되면 샵마인 앱 정보의 실제 버전 지정")
    sp.add_argument("--id-key", default=sm.ID_KEY_DEFAULT)
    sp.add_argument("--pw-key", default=sm.PW_KEY_DEFAULT)
    sp.add_argument("--start-page", type=int, default=sm.START_PAGE_DEFAULT)
    sp.add_argument("--page-size", type=int, default=sm.PAGE_SIZE_DEFAULT)
    sp.add_argument("--pw-hash", default="",
                    help="비번 전송 변환(앱이 해시해 보낼 때): md5·sha1·sha256·sha512(또는 …-upper). 기본 빈값=평문")

    sub.add_parser("discover", help="응답 필드명·건수만 확인(값 숨김)")

    sp = sub.add_parser("sync", help="관리대장 대조·갱신 1회")
    sp.add_argument("--url", default="", help="관리대장 URL/ID(생략 시 설정 탭 gsheet/input_url)")

    sub.add_parser("selftest", help="네트워크 없이 오프라인 검증 실행")
    return p


def main() -> None:
    a = build_parser().parse_args()
    {"setup": cmd_setup, "discover": cmd_discover, "sync": cmd_sync, "selftest": cmd_selftest}[a.cmd](a)


if __name__ == "__main__":
    main()
