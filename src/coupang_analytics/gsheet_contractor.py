"""셀독 계약자별 상품 현황 → 구글시트(설계안 11절 안1 · D-358 ⑩) — 매일 같은 시트를 통째 덮어쓰기.

- 주소 = 설정 탭 '셀독 계약자별 상품 현황 링크'(appconfig `contractor/url`) · 권한 = 지금 서비스계정(spreadsheets 범위만) · 새 권한 없음.
- 엑셀과 **같은 워크북**을 시트마다 `gsheet_stats.worksheet_to_requests` 로 옮긴다 → 값·서식·칸 폭(엑셀 폭 × 7 + 5 픽셀)이 같다.
- 반쯤 쓰다 끊겨 어제·오늘이 섞이지 않게: 새 탭(임시 이름)에 전부 쓴 뒤 **한 번의 batchUpdate** 로 옛 탭을 지우고 새 탭 이름을
  바꿔 끼운다(정산서 임시 탭 방식 · 끊기면 옛 탭이 그대로 남고 다음 실행이 남은 임시 탭까지 지움). 대장에서 사라진 사업자 탭도 지워짐.
- 시트 안 링크(요약 ↔ 사업자 탭) = `gsheet.sheet_link`(파일 전체 주소 · 모바일에서도 열림).
- 실패 = `GSheetError`(403 권한·404 주소·네트워크) 그대로 올림 → 호출부가 ❌ 로그·실행 계속(조용한 폴백 없음).
"""
from __future__ import annotations

import re
from datetime import datetime

from .gsheet import sheet_link
from .gsheet_stats import _rgb_to_color, worksheet_to_requests

_LOC = re.compile(r"^#?'?(.*?)'?!")
TMP_PREFIX = "~새탭"
# 구글시트가 지원해 그대로 옮길 수 있는 조건부 서식(소유자 11-19 '구글시트에서 일부 기능 미지원' — 데이터 막대 등은 없음).
SUPPORTED_CF = frozenset({"colorScale", "cellIs"})
_CFVO = {"min": "MIN", "max": "MAX", "num": "NUMBER", "percent": "PERCENT", "percentile": "PERCENTILE"}
_CELLIS = {"equal": "NUMBER_EQ", "greaterThan": "NUMBER_GREATER", "lessThan": "NUMBER_LESS"}


def _target(location: str) -> str:
    m = _LOC.match(location or "")
    return m.group(1).replace("''", "'") if m else ""


def _patch_links(ws, reqs: list[dict], gids: dict[str, int], doc_id: str) -> None:
    """시트 안 링크(#'탭'!A1) 칸 → =HYPERLINK(파일 주소?gid=…). worksheet_to_requests 는 탭 하나(계정목록)만 알아서 여기서 바꿈."""
    cells = next(r["updateCells"]["rows"] for r in reqs if "updateCells" in r)
    for row in ws.iter_rows():
        for c in row:
            link = c.hyperlink
            loc = getattr(link, "location", None) or (getattr(link, "target", "") or "")
            if not link or str(loc).startswith("http"):
                continue
            title = _target(str(loc))
            if title not in gids:
                raise ValueError(f"시트 안 링크 대상 탭 없음: {c.coordinate} → '{title}'")
            text = str(c.value if c.value is not None else "").replace('"', '""')
            cells[c.row - 1]["values"][c.column - 1]["userEnteredValue"] = {
                "formulaValue": f'=HYPERLINK("{sheet_link(doc_id, gids[title])}","{text}")'}


def _row_heights(ws, gid: int) -> list[dict]:
    """2행부터 줄 높이(제목·머리글 2줄·데이터 줄 간격 · 포인트 × 1.33 픽셀) — worksheet_to_requests 는 1행 높이만 옮김."""
    return [{"updateDimensionProperties": {
        "range": {"sheetId": gid, "dimension": "ROWS", "startIndex": r - 1, "endIndex": r},
        "properties": {"pixelSize": int(dim.height * 1.33)}, "fields": "pixelSize"}}
        for r, dim in ws.row_dimensions.items() if r > 1 and dim.height]


def _point(cfvo, color) -> dict:
    p = {"type": _CFVO[cfvo.type], "color": _rgb_to_color(getattr(color, "rgb", None))}
    if cfvo.val is not None:
        v = float(cfvo.val)
        p["value"] = str(int(v)) if v.is_integer() else str(v)
    return p


def _rule_body(rule) -> dict:
    """openpyxl 조건부 규칙 → 구글 규칙 본문. 지원 안 되는 종류 = 예외(조용히 빼지 않음 · 엑셀·구글 모양이 갈라지지 않게)."""
    if rule.type not in SUPPORTED_CF:
        raise ValueError(f"구글시트로 못 옮기는 조건부 서식: {rule.type}")
    if rule.type == "colorScale":
        cs = rule.colorScale
        if len(cs.cfvo) != 2:
            raise ValueError(f"색 농도는 2색만 옮김(받은 {len(cs.cfvo)}색)")
        return {"gradientRule": {"minpoint": _point(cs.cfvo[0], cs.color[0]),
                                 "maxpoint": _point(cs.cfvo[1], cs.color[1])}}
    if rule.operator not in _CELLIS:
        raise ValueError(f"구글시트로 못 옮기는 비교: {rule.operator}")
    f = rule.dxf.font
    tf = {"bold": bool(f.bold)}
    if f.color is not None and _rgb_to_color(f.color.rgb):
        tf["foregroundColor"] = _rgb_to_color(f.color.rgb)
    return {"booleanRule": {"condition": {"type": _CELLIS[rule.operator],
                                          "values": [{"userEnteredValue": str(v)} for v in rule.formula]},
                            "format": {"textFormat": tf}}}


def cond_format_requests(ws, gid: int) -> list[dict]:
    """엑셀 조건부 서식(색 농도·값 비교) → addConditionalFormatRule — 엑셀과 같은 규칙을 구글에도 그대로."""
    out = []
    for cf in ws.conditional_formatting:
        ranges = [{"sheetId": gid, "startRowIndex": r.min_row - 1, "endRowIndex": r.max_row,
                   "startColumnIndex": r.min_col - 1, "endColumnIndex": r.max_col} for r in cf.sqref.ranges]
        for rule in cf.rules:
            out.append({"addConditionalFormatRule": {"index": 0, "rule": {"ranges": ranges, **_rule_body(rule)}}})
    return out


def plan_gids(old_ids: list[int], titles: list[str]) -> dict[str, int]:
    """새 탭 gid — 지금 있는 탭과 겹치지 않게 큰 수부터(바꿔 끼운 뒤에도 같은 gid → 링크 그대로)."""
    start = max(old_ids + [0]) + 1
    return {t: start + i for i, t in enumerate(titles)}


def push_report(client, wb, log=print, now: datetime | None = None) -> dict[str, int]:
    """워크북(요약 + 사업자 시트)을 등록된 구글시트로 통째 교체. {탭: gid} 반환. 실패 = GSheetError 그대로."""
    titles = list(wb.sheetnames)
    meta = client.meta(refresh=True)
    old = [s["properties"]["sheetId"] for s in meta.get("sheets") or []]
    gids = plan_gids(old, titles)
    tag = f"{TMP_PREFIX}{(now or datetime.now()):%H%M%S}_"
    client.batch_update([{"addSheet": {"properties": {"sheetId": gids[t], "title": f"{tag}{i}"}}}
                         for i, t in enumerate(titles)])
    for t in titles:
        ws = wb[t]
        reqs = worksheet_to_requests(ws, gids[t], doc_id=client.spreadsheet_id)
        _patch_links(ws, reqs, gids, client.spreadsheet_id)
        client.batch_update(reqs + _row_heights(ws, gids[t]) + cond_format_requests(ws, gids[t]))
    swap = [{"deleteSheet": {"sheetId": sid}} for sid in old]
    swap += [{"updateSheetProperties": {"properties": {"sheetId": gids[t], "title": t, "index": i,
                                                       "tabColor": _tab_color(wb[t])},
                                        "fields": "title,index,tabColor"}} for i, t in enumerate(titles)]
    client.batch_update(swap)
    log(f"  [계약자별 현황 구글시트] ✔ 탭 {len(titles)}개 교체(옛 탭 {len(old)}개 지움)")
    return gids


def _tab_color(ws) -> dict:
    rgb = getattr(ws.sheet_properties.tabColor, "rgb", None) or "FF9C7FD6"
    h = rgb[-6:]
    return {"red": int(h[0:2], 16) / 255, "green": int(h[2:4], 16) / 255, "blue": int(h[4:6], 16) / 255}


__all__ = ["SUPPORTED_CF", "TMP_PREFIX", "cond_format_requests", "plan_gids", "push_report"]
