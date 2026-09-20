"""출력 결과 구글시트의 **사업자별 통계 시트** 쓰기 — openpyxl 마스터 워크북을 그대로 미러링.

설계(designs/GSHEET_UNIFIED.md §4 Phase 3b, 사용자 확정 'openpyxl 시트 미러링'):
- 이미 완성돼 매 실행 생성되는 openpyxl 마스터(`workbook.OutputWorkbook`, 상품블록·일자 가로누적·키워드
  노위·재고·마케팅 배경색·테두리·틀고정·"👈 계정 목록" 복귀링크·상태)의 **각 사업자 시트를 Sheets API
  batchUpdate 로 1:1 번역**해 push 한다. 시계열 이어쓰기·마케팅 규칙·모든 서식은 openpyxl 렌더러에서
  이미 계산돼 있으므로 여기선 **값+서식을 그대로 옮기기만** 한다(규칙 재구현·이중 렌더러 없음).
- 통계 시트는 **프로그램 전용**(직원 편집 없음)이라 매 실행 **전체 교체**가 안전하다(계정목록과 달리
  증분 보존 불필요). `계정목록`(직원 마케팅 D~F 보존)은 `gsheet_index.sync_index` 가 따로 담당한다.

fallback 금지: 인증·권한·쿼터 오류는 `gsheet_api.GSheetError` 로 올라간다(호출부가 한국어로 표시).
"""
from __future__ import annotations

from typing import Any

from openpyxl.worksheet.worksheet import Worksheet

from . import config
from .gsheet_index import INDEX_SHEET_NAME
from .workbook import (_COL_METRIC, _COL_NAME, _LABEL_DATE, _LABEL_KEYWORD,
                       _SPECIAL_SHEETS, _key)

# openpyxl 선(Side) 스타일 → Sheets 테두리 스타일
_BORDER_STYLE = {
    "thin": "SOLID", "hair": "SOLID", "medium": "SOLID_MEDIUM", "thick": "SOLID_THICK",
    "double": "DOUBLE", "dotted": "DOTTED", "dashed": "DASHED",
}
# openpyxl 가로 정렬 → Sheets horizontalAlignment
_HALIGN = {"left": "LEFT", "center": "CENTER", "right": "RIGHT"}
_VALIGN = {"top": "TOP", "center": "MIDDLE", "bottom": "BOTTOM"}


def _rgb_to_color(rgb: Any) -> dict | None:
    """openpyxl 색(ARGB hex 문자열 'FFRRGGBB' 또는 'RRGGBB') → Sheets Color(0~1). 못 읽으면 None.

    테마색·인덱스색(문자열 아님)·흰색 alpha 0 등은 None 으로 흘려 기본색을 쓰게 둔다(조용한 실패 아님 —
    실제로 지정 안 된 색이므로 서식에서 뺀다)."""
    if not isinstance(rgb, str):
        return None
    h = rgb.strip()
    if len(h) == 8:          # ARGB → RGB(알파 버림)
        h = h[2:]
    if len(h) != 6:
        return None
    try:
        r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return None
    return {"red": r, "green": g, "blue": b}


def _text_format(cell) -> dict:
    """openpyxl Font → Sheets textFormat(설정된 속성만)."""
    f = cell.font
    tf: dict[str, Any] = {}
    if f is not None:
        if f.name:
            tf["fontFamily"] = f.name
        if f.size:
            tf["fontSize"] = int(f.size)
        if f.bold:
            tf["bold"] = True
        if f.italic:
            tf["italic"] = True
        if f.underline and f.underline != "none":
            tf["underline"] = True
        col = _rgb_to_color(getattr(f.color, "rgb", None)) if f.color is not None else None
        if col:
            tf["foregroundColor"] = col
    return tf


def _borders(cell) -> dict:
    """openpyxl Border → Sheets borders(설정된 변만)."""
    out: dict[str, Any] = {}
    b = cell.border
    if b is None:
        return out
    for side_name, gkey in (("left", "left"), ("right", "right"), ("top", "top"), ("bottom", "bottom")):
        side = getattr(b, side_name, None)
        if side is not None and side.style:
            gb: dict[str, Any] = {"style": _BORDER_STYLE.get(side.style, "SOLID")}
            col = _rgb_to_color(getattr(side.color, "rgb", None)) if side.color is not None else None
            gb["color"] = col or {"red": 0.5, "green": 0.5, "blue": 0.5}
            out[gkey] = gb
    return out


def _cell_format(cell) -> dict:
    """openpyxl 셀 서식 → Sheets userEnteredFormat(배경·정렬·줄바꿈·테두리·숫자서식·글꼴)."""
    fmt: dict[str, Any] = {}
    # 배경(solid fill 만)
    fill = cell.fill
    if fill is not None and getattr(fill, "patternType", None) == "solid":
        bg = _rgb_to_color(getattr(fill.fgColor, "rgb", None))
        if bg:
            fmt["backgroundColor"] = bg
    # 정렬 + 줄바꿈
    al = cell.alignment
    if al is not None:
        if al.horizontal in _HALIGN:
            fmt["horizontalAlignment"] = _HALIGN[al.horizontal]
        if al.vertical in _VALIGN:
            fmt["verticalAlignment"] = _VALIGN[al.vertical]
        fmt["wrapStrategy"] = "WRAP" if al.wrap_text else "OVERFLOW_CELL"
    # 테두리
    br = _borders(cell)
    if br:
        fmt["borders"] = br
    # 숫자 서식
    nf = cell.number_format
    if nf and nf != "General":
        fmt["numberFormat"] = {"type": "NUMBER", "pattern": nf}
    # 글꼴
    tf = _text_format(cell)
    if tf:
        fmt["textFormat"] = tf
    return fmt


def _cell_value(cell, index_gid: int | None) -> dict | None:
    """openpyxl 셀 값 → Sheets userEnteredValue. 값 없으면 None.

    내부 하이퍼링크(예 '👈 계정 목록' 복귀 링크)는 구글 네이티브 `=HYPERLINK("#gid=..&range=A1", 텍스트)`
    수식으로 옮긴다(계정목록 gid 필요). 그 외 문자열/숫자는 그대로."""
    link = getattr(cell, "hyperlink", None)
    if link is not None and getattr(link, "location", None) and index_gid is not None:
        text = str(cell.value if cell.value is not None else "").replace('"', '""')
        return {"formulaValue": f'=HYPERLINK("#gid={index_gid}&range=A1","{text}")'}
    v = cell.value
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, (int, float)):
        return {"numberValue": v}
    s = str(v)
    if s.startswith("="):
        return {"formulaValue": s}
    return {"stringValue": s}


def _freeze(ws: Worksheet) -> tuple[int, int]:
    """openpyxl freeze_panes('H2' 등) → (frozenRowCount, frozenColumnCount). 없으면 (0,0)."""
    fp = ws.freeze_panes
    if not fp:
        return 0, 0
    from openpyxl.utils.cell import coordinate_to_tuple
    try:
        row, col = coordinate_to_tuple(fp)      # 'H2' → (2, 8)
    except Exception:
        return 0, 0
    return max(row - 1, 0), max(col - 1, 0)     # 그 셀 위/왼쪽까지 고정


def worksheet_to_requests(ws: Worksheet, sheet_id: int, index_gid: int | None = None) -> list[dict]:
    """openpyxl 사업자 시트 하나 → Sheets batchUpdate 요청 묶음(전체 교체). 순수 함수(테스트 가능).

    순서: 병합해제(전체) → 그리드 크기/틀고정 → 값+서식(updateCells) → 병합 재적용 → 열너비/행높이.
    """
    maxr = ws.max_row
    maxc = ws.max_column
    if maxr < 1 or maxc < 1:
        return []
    reqs: list[dict] = []
    # 1) 기존 병합 전부 해제(시트 전체) — 이전 실행의 병합 잔재 제거(멱등)
    reqs.append({"unmergeCells": {"range": {"sheetId": sheet_id}}})
    # 2) 그리드 크기(데이터에 맞춤·초과분 제거) + 틀고정
    fr, fc = _freeze(ws)
    reqs.append({"updateSheetProperties": {
        "properties": {"sheetId": sheet_id, "gridProperties": {
            "rowCount": max(maxr, 1), "columnCount": max(maxc, 1),
            "frozenRowCount": fr, "frozenColumnCount": fc}},
        "fields": ("gridProperties.rowCount,gridProperties.columnCount,"
                   "gridProperties.frozenRowCount,gridProperties.frozenColumnCount")}})
    # 3) 값 + 서식(전 범위 한 요청)
    rows_data: list[dict] = []
    for r in range(1, maxr + 1):
        values: list[dict] = []
        for c in range(1, maxc + 1):
            cell = ws.cell(r, c)
            cd: dict[str, Any] = {}
            uev = _cell_value(cell, index_gid)
            if uev is not None:
                cd["userEnteredValue"] = uev
            fmt = _cell_format(cell)
            if fmt:
                cd["userEnteredFormat"] = fmt
            values.append(cd)
        rows_data.append({"values": values})
    reqs.append({"updateCells": {
        "start": {"sheetId": sheet_id, "rowIndex": 0, "columnIndex": 0},
        "rows": rows_data,
        "fields": "userEnteredValue,userEnteredFormat"}})
    # 4) 병합 재적용
    for mr in ws.merged_cells.ranges:
        if mr.max_row > mr.min_row or mr.max_col > mr.min_col:
            reqs.append({"mergeCells": {
                "range": {"sheetId": sheet_id,
                          "startRowIndex": mr.min_row - 1, "endRowIndex": mr.max_row,
                          "startColumnIndex": mr.min_col - 1, "endColumnIndex": mr.max_col},
                "mergeType": "MERGE_ALL"}})
    # 5) 열 너비(엑셀 문자폭 → 대략 픽셀: width*7+5) + 1행 높이
    for letter, dim in ws.column_dimensions.items():
        if not dim.width:
            continue
        from openpyxl.utils import column_index_from_string
        try:
            ci = column_index_from_string(letter) - 1
        except Exception:
            continue
        if ci >= maxc:
            continue
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": ci, "endIndex": ci + 1},
            "properties": {"pixelSize": int(dim.width * 7 + 5)}, "fields": "pixelSize"}})
    h1 = ws.row_dimensions[1].height if 1 in ws.row_dimensions else None
    if h1:
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": int(h1 * 1.33)}, "fields": "pixelSize"}})
    return reqs


def push_statistics(client, wb, *, on_log=None) -> dict[str, int]:
    """openpyxl 마스터 워크북의 **사업자별 통계 시트**를 결과 구글시트로 전체 미러링. {사업자: gid} 반환.

    - 특수시트(_상품ID·계정 목록·_계정정보·_마케팅·_중단)는 제외(계정목록은 sync_index 담당).
    - 각 사업자 시트는 ensure_sheet 후 값+서식 전체 교체. "👈 계정 목록" 복귀링크는 구글 계정목록 gid 로 재연결.
    - 시트당 batchUpdate 1회로 묶어 쿼터(429)를 아낀다.
    """
    log = on_log or (lambda m: None)
    biz_sheets = [b for b in wb.account_sheets() if b not in _SPECIAL_SHEETS]
    # 계정목록(복귀 링크 대상) + 사업자 시트를 한 번에 생성(대량 최초 생성의 429 회피)
    gid_map = client.ensure_sheets([INDEX_SHEET_NAME] + biz_sheets)
    index_gid = gid_map[INDEX_SHEET_NAME]
    gids: dict[str, int] = {}
    for biz in biz_sheets:
        ws = wb.wb[biz]
        sheet_id = gid_map[biz]
        reqs = worksheet_to_requests(ws, sheet_id, index_gid=index_gid)
        if reqs:
            client.batch_update(reqs)
        gids[biz] = sheet_id
        log(f"  [구글시트] 통계 시트 '{biz}' 반영({ws.max_row}행×{ws.max_column}열)")
    return gids


def read_staff_keywords(client, wb) -> dict[tuple[str, str], list[str]]:
    """결과 통계 시트에서 **상품별 키워드 목록**을 읽는다 → {(사업자, 상품): [키워드…]}.

    통계 시트는 push_statistics 가 쓴 레이아웃(상품 헤더행 G='날짜'·C=노출명 / 키워드 소헤더 C='키워드' /
    그 아래 키워드 행 C=키워드명)을 그대로 되읽는다. 프로그램이 쓴 AI 키워드 + **직원이 그 영역에 직접 타이핑한
    키워드**를 모두 포함(위치 기반 파싱이라 직원 행에 G='노출 순위'가 없어도 잡힌다). 시트가 없으면 건너뜀.
    """
    ci, gi = _COL_NAME - 1, _COL_METRIC - 1     # read_grid 값 격자는 0-based
    titles = set(client.sheet_titles())
    out: dict[tuple[str, str], list[str]] = {}
    for biz in wb.account_sheets():
        if biz in _SPECIAL_SHEETS or biz not in titles:
            continue
        values, _notes = client.read_grid(biz)
        cur: str | None = None
        in_kw = False
        for row in values:
            c = row[ci].strip() if len(row) > ci and row[ci] else ""
            g = row[gi].strip() if len(row) > gi and row[gi] else ""
            if g == _LABEL_DATE and c:                 # 상품 헤더행 → 새 상품(노출명 꼬리 제거)
                cur, in_kw = _key(c), False
            elif c == _LABEL_KEYWORD:                   # 키워드 소헤더 → 이 아래가 키워드 영역
                in_kw = True
            elif in_kw and cur and c and c != _LABEL_KEYWORD:
                if g == config.M_RANK_OFF:              # 추적 중단 키워드 = 담당자 활성 목록 아님(재활성 루프 방지)
                    continue
                out.setdefault((biz, cur), [])
                if c not in out[(biz, cur)]:
                    out[(biz, cur)].append(c)
    return out


def merge_staff_keywords(client, wb, *, on_log=None) -> int:
    """결과 통계 시트의 상품별 키워드를 워크북에 **동기화**(담당자 편집 반영). 반영 상품 수 반환.

    담당자가 구글시트 키워드 영역을 직접 편집한 것을 그대로 따른다:
    - **추가**: 시트에 있는데 워크북에 없는 키워드 → 활성 추가(상품당 활성 상한 `KW_MAX_TRACK`).
    - **재활성**: 지웠다가 다시 넣은 중단 키워드 → 재활성(과거 이력 유지).
    - **중단**: 워크북엔 활성인데 담당자가 시트에서 지운 키워드 → **추적 중단**(행·과거값 보존, 검색만 제외).
    ⚠ 안전장치: 그 상품 시트에서 활성 키워드가 **하나도 안 읽히면**(파싱 실패·빈 영역) 그 상품은 건드리지
    않는다(오판으로 전부 중단하는 사고 방지). 실행 시작 시 호출 → 반영분이 워크북에 들어가 종료 시 미러링돼도 유지.
    """
    log = on_log or (lambda m: None)
    staff = read_staff_keywords(client, wb)     # {(biz,product): [활성 키워드…]} (중단 행은 이미 제외됨)
    n = 0
    for (biz, product), kws in staff.items():
        want = list(dict.fromkeys(kws))          # 담당자가 남긴 = 최종 활성 목록
        if not wb.has_product(biz, product) or not want:
            continue                             # 상품 없음·빈 목록(파싱 실패 방지) → 스킵
        before = wb.active_keywords(biz, product)
        changed = False
        # 1) 재활성 — 담당자가 다시 넣은 중단 키워드(이력 유지)
        for kw in want:
            if kw in wb.product_keywords(biz, product) and wb.is_keyword_inactive(biz, product, kw):
                changed |= wb.set_keyword_active(biz, product, kw, True)
        # 2) 추가 — 시트에 있는데 워크북에 아예 없는 키워드(활성 상한 내)
        room = config.KW_MAX_TRACK - len(wb.active_keywords(biz, product))
        add = [kw for kw in want if kw not in wb.product_keywords(biz, product)]
        capped = add[:max(0, room)]
        if capped:
            wb.add_product_keywords(biz, product, capped)
            changed = True
        if len(add) > len(capped):
            log(f"  [구글시트] '{biz}/{product}' 상한({config.KW_MAX_TRACK}) 초과분 제외: {add[len(capped):]}")
        # 3) 중단 — 워크북엔 활성인데 담당자가 시트에서 지운 키워드(이력 보존·검색 제외)
        for kw in before:
            if kw not in want:
                changed |= wb.set_keyword_active(biz, product, kw, False)
        if changed:
            n += 1
            log(f"  [구글시트] '{biz}/{product}' 담당자 키워드 편집 반영 → 활성 {wb.active_keywords(biz, product)}")
    return n
