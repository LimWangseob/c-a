"""계정목록 **전체 재작성** — 현재 마스터로 데이터행을 새로 쓴다(제목·헤더·서식·직원 E~G 미접촉).

배경(2026-09-23 실측): 결과 구글시트 `계정목록`이 **옛 노출명 + 자기참조 링크**로 낡음. 증분 sync 는
등록명 키 불일치로 그리드 400 실패해 방치됨. 링크만 수리는 이름도 낡아 54/123 만 매칭. 그래서
**현재 마스터로 데이터행을 통째로 재작성**한다(현재 노출명 + 정상 링크 + 현재 계정/상태).

동작(제목·헤더·틀고정·열너비는 이미 정상 → 미접촉, 직원 마케팅 E~G 값 미접촉·색만):
  1) 마스터 로드 → roster_from_workbook(사업자 통계 시트 gid·블록 헤더행 포함)
  2) 각 로스터행을 A·B·C(링크)·D·H + B열 안정키 note + 밴드색으로 재작성(_auto_cells_request+_mkt_fill_request)
  3) 로스터보다 많은 **옛 데이터행은 삭제**(deleteDimension) → 낡은 상품 잔재 제거
  4) 제목의 '상품 N개' 카운트만 갱신
  기본=드라이런(집계·표본), --write 로 실제 적용.

⚠ E~G(체험단·모니터링=직원 입력) **값 미접촉**(색만). ⚠ 로스터가 그리드보다 크면 중단(수동 확인 필요).
사용: python tools/rebuild_index.py <마스터.xlsx>            # 드라이런
      python tools/rebuild_index.py <마스터.xlsx> --write     # 적용
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from coupang_analytics import appconfig, gsheet_api, gsheet_index  # noqa: E402
from coupang_analytics.workbook import OutputWorkbook  # noqa: E402

INDEX = gsheet_index.INDEX_SHEET_NAME
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


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--write"]
    write = "--write" in sys.argv
    if not args:
        print("[중단] 마스터 경로를 인자로 주세요(현재 운용 마스터). "
              "예: python tools/rebuild_index.py <통계.xlsx> [--write]")
        return 1
    master = Path(args[0])
    if not master.exists():
        print(f"[중단] 마스터 없음: {master}")
        return 1
    url = _output_url()
    if not url or not gsheet_api.load_sa_info():
        print("[중단] 결과 구글시트 URL 또는 SA 키 없음.")
        return 1

    wb = OutputWorkbook.load(master)
    client = gsheet_api.GSheetClient(url)
    sheet_id = client.sheet_id(INDEX)
    if sheet_id is None:
        print(f"[중단] '{INDEX}' 시트 없음.")
        return 1
    gid_by_title = {s["properties"]["title"]: s["properties"]["sheetId"]
                    for s in client.meta().get("sheets", [])}
    gids = {b: gid_by_title[b] for b in wb.account_sheets() if b in gid_by_title}
    roster = gsheet_index.roster_from_workbook(wb, gids)

    # 현재 데이터행 수(값 있는 마지막 행 기준) + 그리드 확인
    vals = client.read_values(INDEX)
    old_rows = len(vals)                          # 값 있는 마지막 행(1-based 개수)
    meta = client._sheets().get(spreadsheetId=client.spreadsheet_id,
                                fields="sheets.properties(sheetId,gridProperties.rowCount)").execute()
    grid_rows = next((s["properties"].get("gridProperties", {}).get("rowCount")
                      for s in meta.get("sheets", []) if s["properties"]["sheetId"] == sheet_id), None)
    need_rows = DATA0 + len(roster)
    linked = sum(1 for r in roster if r.link_gid is not None)
    missing = [b for b in wb.account_sheets() if b not in gids]
    print(f"[전체재작성] 마스터={master.name} · 로스터 {len(roster)}행(링크 {linked}) · "
          f"현재 데이터 {old_rows}행 · 그리드 {grid_rows}행 · {'적용(--write)' if write else '드라이런'}")
    if missing:
        print(f"  [주의] 통계시트 없는 사업자 {len(missing)}개는 링크 없이 텍스트: {missing[:8]}")
    if grid_rows is not None and need_rows > grid_rows:
        print(f"[중단] 로스터가 그리드보다 큼(need {need_rows} > grid {grid_rows}). 수동 확인 필요(행 추가).")
        return 1

    # 표본
    print("[표본·재작성 링크]")
    shown = 0
    for r in roster:
        if r.link_gid is not None and shown < 5:
            print(f"    {r.business} · {r.product[:26]} → gid={r.link_gid} A{r.link_row} · 상태={r.status}")
            shown += 1

    trailing = max(0, old_rows - need_rows)
    print(f"[삭제 예정] 로스터 뒤 옛 데이터행 {trailing}개(그리드 {DATA0+len(roster)+1}~{old_rows}행)")

    if not write:
        print("\n※ 드라이런. 적용하려면 --write 추가. (E~G 직원값 미접촉·제목/헤더/서식 유지)")
        return 0

    # 실제 적용 — 데이터행 재작성 + 제목 카운트 + 옛 잔재행 삭제
    reqs: list[dict] = []
    n_prod = sum(1 for d in roster if d.status != gsheet_index.DISCONTINUED)
    reqs.append({"updateCells": {
        "start": {"sheetId": sheet_id, "rowIndex": 0, "columnIndex": 0},
        "rows": [{"values": [{"userEnteredValue": {"stringValue": f"계정목록 · 상품 {n_prod}개"}}]}],
        "fields": "userEnteredValue"}})
    for i, row in enumerate(roster):
        grid_row = DATA0 + i
        reqs += gsheet_index._auto_cells_request(sheet_id, grid_row, row)   # 밴드색은 내부에서 row.band 사용
        reqs.append(gsheet_index._mkt_fill_request(sheet_id, grid_row, row.band))
    # 옛 잔재 데이터행 삭제(로스터 뒤) — 단일 구간
    if trailing > 0:
        reqs.append({"deleteDimension": {"range": {
            "sheetId": sheet_id, "dimension": "ROWS",
            "startIndex": need_rows, "endIndex": old_rows}}})
    client.batch_update(reqs)
    print(f"\n✅ 계정목록 전체 재작성 완료 — {len(roster)}행(링크 {linked}) · 옛 행 {trailing}개 삭제 · "
          "제목/헤더/서식·직원 E~G 유지")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
