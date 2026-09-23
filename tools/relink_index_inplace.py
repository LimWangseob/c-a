"""계정목록 C열 링크 **제자리 수리** — 라이브 통계 시트에서 블록 헤더행을 찾아 링크만 재작성.

배경(2026-09-23 실측): 결과 구글시트 `계정목록`의 상품 링크가 전부 **자기참조**(`#gid=계정목록&range=A1`)로
깨져 있음. 반면 표시명(노출 상품명)·계정·상태·직원영역(E~G)은 정상. 증분 sync 는 등록명 키 불일치로 실패
(그리드 400)하므로, 여기서는 **이름·데이터를 건드리지 않고 C열 링크만** 올바른 사업자 통계 시트로 고친다.

동작(마스터 불필요·키 매칭 불필요·라이브 시트만·READ 우선):
  1) 계정목록을 FORMULA 로 읽어 각 행의 (사업자[B], 표시명[C]) 확보
  2) 각 사업자 통계 시트를 읽어 **블록 헤더행**(G열=='날짜'인 행)의 {정규화 상품명: 시트행} 맵 작성
  3) 계정목록 각 데이터행의 표시명을 그 사업자 맵에서 찾아 링크 `#gid={사업자gid}&range=A{블록행}` 생성
  4) **기본=드라이런**(매칭/미매칭 집계 + 표본 출력, 쓰기 없음). `--write` 주면 **C열만** batch 로 재작성.

⚠ C열(상품 셀)만 씀 — 대표자/사업자/계정ID/상태/직원 마케팅(E~G)·통계 시트 미접촉.
사용: python tools/relink_index_inplace.py          # 드라이런(표본 보고)
      python tools/relink_index_inplace.py --write   # 실제 적용
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from coupang_analytics import appconfig, gsheet_api, gsheet_index  # noqa: E402
from coupang_analytics.workbook import (  # noqa: E402
    _COL_METRIC, _COL_NAME, _LABEL_DATE, _key, _norm)

INDEX = gsheet_index.INDEX_SHEET_NAME
COL_BIZ, COL_PROD = gsheet_index.COL_BUSINESS, gsheet_index.COL_PRODUCT
DATA0 = gsheet_index.DATA_START0


def _output_url() -> str:
    v = appconfig.get("gsheet/output_url", "")
    if v:
        return v
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\coupang-analytics\ui\gsheet") as k:
            val, _ = winreg.QueryValueEx(k, "output_url")
        return str(val).strip() if val else ""
    except (ImportError, OSError):
        return ""


def _hyperlink_display(cell: str) -> str:
    """C셀 문자열에서 표시명 추출 — HYPERLINK 수식이면 2번째 인자, 아니면 원문."""
    s = str(cell or "")
    m = re.search(r'=HYPERLINK\("[^"]*"\s*,\s*"(.*)"\)\s*$', s)
    if m:
        return m.group(1).replace('""', '"')
    return s


def _block_header_rows(client, biz: str) -> dict[str, int]:
    """사업자 통계 시트의 {정규화 상품명: 1-based 블록 헤더행}. G열=='날짜'인 행이 블록 헤더(첫 등장만)."""
    vals = client.read_values(biz)
    out: dict[str, int] = {}
    for i, row in enumerate(vals):
        metric = _norm(row[_COL_METRIC - 1]) if len(row) >= _COL_METRIC else ""
        if metric != _LABEL_DATE:
            continue
        name = _key(row[_COL_NAME - 1]) if len(row) >= _COL_NAME else ""
        if name:
            out.setdefault(name, i + 1)   # 1-based 시트 행
    return out


def main() -> int:
    write = "--write" in sys.argv
    url = _output_url()
    if not url:
        print("[중단] 결과 구글시트 URL 없음(설정 gsheet/output_url 또는 레지스트리).")
        return 1
    if not gsheet_api.load_sa_info():
        print("[중단] 서비스계정(SA) 키 없음(설정 탭에서 등록).")
        return 1

    client = gsheet_api.GSheetClient(url)
    index_gid = client.sheet_id(INDEX)
    gid_by_title = {s["properties"]["title"]: s["properties"]["sheetId"]
                    for s in client.meta().get("sheets", [])}
    print(f"[재링크·제자리] 계정목록 gid={index_gid} · 시트 {len(gid_by_title)}개 · "
          f"{'실제 적용(--write)' if write else '드라이런(표본만)'}")

    # 1) 계정목록 FORMULA
    svc = client._sheets()
    resp = svc.values().get(spreadsheetId=client.spreadsheet_id, range=f"'{INDEX}'",
                            valueRenderOption="FORMULA").execute()
    rows = resp.get("values", [])

    # 2) 사업자별 블록 헤더행 맵(캐시)
    hdr_cache: dict[str, dict[str, int]] = {}
    updates: list[dict] = []
    fixed = skipped_nolink = unmatched = already_ok = 0
    samples: list[str] = []
    unmatched_samples: list[str] = []

    for gi in range(DATA0, len(rows)):
        row = rows[gi]
        biz = (row[COL_BIZ] if len(row) > COL_BIZ else "").strip()
        cell = row[COL_PROD] if len(row) > COL_PROD else ""
        disp = _hyperlink_display(cell)
        if not disp.strip():
            skipped_nolink += 1
            continue
        biz_gid = gid_by_title.get(biz)
        if biz_gid is None:
            unmatched += 1
            if len(unmatched_samples) < 5:
                unmatched_samples.append(f"[사업자시트없음] {biz} · {disp[:30]}")
            continue
        if biz not in hdr_cache:
            hdr_cache[biz] = _block_header_rows(client, biz)
        hrow = hdr_cache[biz].get(_key(disp))
        if hrow is None:
            unmatched += 1
            if len(unmatched_samples) < 5:
                unmatched_samples.append(f"[블록못찾음] {biz} · {disp[:30]}")
            continue
        # 이미 올바른 링크면(자기참조 아님·같은 gid·같은 행) 건너뜀
        want = f"#gid={biz_gid}&range=A{hrow}"
        if f'"{want}"' in str(cell):
            already_ok += 1
            continue
        name_esc = disp.replace('"', '""')
        formula = f'=HYPERLINK("{want}","{name_esc}")'
        updates.append({
            "updateCells": {
                "start": {"sheetId": index_gid, "rowIndex": gi, "columnIndex": COL_PROD},
                "rows": [{"values": [{"userEnteredValue": {"formulaValue": formula}}]}],
                "fields": "userEnteredValue",
            }})
        fixed += 1
        if len(samples) < 5:
            samples.append(f"{biz} · {disp[:26]} → gid={biz_gid} A{hrow}")

    print(f"\n[집계] 수리대상 {fixed} · 이미정상 {already_ok} · 미매칭 {unmatched} · 링크없음행 {skipped_nolink}")
    print("[표본·수리]")
    for s in samples:
        print("   ", s)
    if unmatched_samples:
        print("[표본·미매칭(링크 안 건드림)]")
        for s in unmatched_samples:
            print("   ", s)

    if not write:
        print("\n※ 드라이런입니다. 실제 적용하려면 --write 로 다시 실행하세요(C열만 재작성).")
        return 0
    if not updates:
        print("\n수리할 링크 없음(전부 정상). 변경 없음.")
        return 0
    client.batch_update(updates)
    print(f"\n✅ 계정목록 C열 링크 {fixed}개 재작성 완료(이름·데이터·직원영역 미접촉).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
