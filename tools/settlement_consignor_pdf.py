"""위탁자별 정산서 PDF 묶기(D-260) — 명령줄 입구. 본체 = `src/coupang_analytics/settlement_consignor_pdf.py`(이 파일은 인자만).

    python tools/settlement_consignor_pdf.py --data <…/위탁자정산서> --sheets <위탁자정산서_시트.json> --issued YYYY-MM-DD --out <PDF 폴더>
        [--accounts 계정ID,계정ID] [--months YYYY-MM,YYYY-MM]

- 자료 = `settlement_consignor.py`·배치가 만든 `<계정ID>_<YYYYMM>.json` · 시트 = {"YYYY-MM": 주소}(달마다 파일 1개 D-241 ⑥).
- 위탁자 1명 = PDF 1개(판매 달 순서) · 여러 달이면 첫 장 월별 요약(마지막 달 시트에 임시 탭을 잠깐 그렸다 지움 = 시트 쓰기).
- 발송은 하지 않음(D-399). 하나라도 못 만들면 끝 코드 1(만든 것은 그대로).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coupang_analytics import settlement_consignor_pdf as PDF  # noqa: E402


def _list(text: str) -> list[str]:
    return [x.strip() for x in text.split(",") if x.strip()]


def _session():
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account

    from coupang_analytics.gsheet_api import SCOPES, load_sa_info
    info = load_sa_info()
    if not info:
        raise PDF.ConsignorPdfError("서비스계정 키가 등록되지 않았습니다(설정 탭에서 1회 등록 필요)")
    return AuthorizedSession(service_account.Credentials.from_service_account_info(info, scopes=SCOPES))


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(description="위탁자별 정산서 PDF 묶기(D-260)")
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--sheets", required=True, type=Path)
    ap.add_argument("--issued", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--accounts", default="", help="쉼표로 나눈 계정ID(비면 자료의 전 계정)")
    ap.add_argument("--months", default="", help="쉼표로 나눈 판매 달 YYYY-MM(비면 자료의 모든 달)")
    a = ap.parse_args(argv)
    date.fromisoformat(a.issued)
    sheets = {k: v for k, v in json.loads(a.sheets.read_text(encoding="utf-8")).items() if not k.startswith("_") and v}
    from coupang_analytics.gsheet_api import GSheetClient
    try:
        made, failed = PDF.run(a.data, sheets, a.issued, a.out, session=_session(), client_for=GSheetClient,
                               accounts=_list(a.accounts), months=_list(a.months))
    except PDF.ConsignorPdfError as exc:
        print(f"❌ 시작 전 중단 — {exc}")
        return 1
    print(f"PDF {len(made)}개 → {a.out} · 못 만듦 {len(failed)}명")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
