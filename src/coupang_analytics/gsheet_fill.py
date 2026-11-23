"""결과 구글시트 → 마스터 **빈 칸 채우기**(실행 시작 때 · T-159 · 소유자 11-23 '운용 마스터는 매일 처음 시작시 현행화').

결과 통계 시트는 마스터의 미러(push_statistics 가 같은 행·열에 값+서식 전체 교체)라 행 번호가 같다. 다른 PC(개발 PC)가
결과 시트에 직접 채운 지난 날짜 값(예: 11.19 판매량)이 운용 마스터에는 비어 있으면, 다음 미러링이 그 값을 빈 칸으로 덮는다
→ 실행 시작 때 **마스터 칸이 비었고 시트 칸에 값이 있을 때만** 시트 값을 마스터에 옮긴다.

대응 규칙:
- 사업자 = 시트 이름이 같은 것만(없으면 건너뜀 — 첫 실행 계정 등).
- 행 = 마스터 행 번호 그대로. 블록(상품) 머리줄의 지표 칸 '날짜'·상품명(C · VID 꼬리 뗀 키)이 시트 같은 행과 같고,
  블록 안 지표행의 지표 칸 글자가 모두 같을 때만 그 블록을 씀(다르면 블록 건너뜀 + 로그). 순위행은 키워드(A, 옛 C)까지
  같을 때만 그 행을 씀(직원이 시트에서 키워드를 바꾼 행 = 그 행만 건너뜀).
- 열 = **블록 머리줄의 날짜 글자**로 찾음(D-368·D-369 날짜 칸 하루 당김·새 날짜 칸 추가로 위치가 다를 수 있음).
- 마스터 값이 있는 칸은 절대 안 바꿈 · 이번 회차가 쓸 날짜 칸(skip_labels)은 대상에서 뺌 · 마스터에 없는 날짜 칸은 만들지 않음.
읽기·인증 오류는 호출부(pipeline_gsheet.pull_gsheet_blank_cells)가 ⚠ 로그 후 진행한다.
"""
from __future__ import annotations

from typing import Any

from . import config
from .workbook_common import (_ALL_METRICS, _COL_KW, _COL_METRIC, _COL_NAME, _FIRST_DATE, _LABEL_DATE,
                              _key, _norm)

_ROW_LABELS = frozenset(_ALL_METRICS) | {config.M_RANK}   # 채우는 행 = 날짜 칸 지표행(판매량·방문자·…·판매상태) + 순위행


def read_stat_grids(client, wb) -> tuple[dict[str, list[list[Any]]], list[str]]:
    """결과 시트에서 마스터 사업자 시트와 이름이 같은 시트만 **저장 타입 그대로**(UNFORMATTED) 묶어 읽음.
    반환 = ({사업자: 값 격자}, 시트에 없는 사업자 목록)."""
    titles = set(client.sheet_titles())
    bizs = wb.account_sheets()
    names = [b for b in bizs if b in titles]
    grids = client.read_values_batch(names, unformatted=True) if names else {}
    return grids, [b for b in bizs if b not in titles]


def _at(grid: list[list[Any]], r: int, c: int) -> Any:
    """격자 값(1-based 행·열). 없으면 None."""
    if r - 1 >= len(grid):
        return None
    row = grid[r - 1]
    return row[c - 1] if c - 1 < len(row) else None


def _blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _blocks(ws) -> list[tuple[int, int]]:
    """마스터 시트의 상품 블록 (머리줄, 마지막 줄) 목록 — 지표 칸(G)='날짜' 줄이 블록 시작."""
    heads = [r for r in range(1, ws.max_row + 1) if _norm(ws.cell(r, _COL_METRIC).value) == _LABEL_DATE]
    return [(h, (heads[i + 1] - 1) if i + 1 < len(heads) else ws.max_row) for i, h in enumerate(heads)]


def _date_cols(values) -> dict[str, int]:
    """머리줄 값들(H~) → {날짜 글자: 열(1-based)}. 같은 글자가 두 번이면 앞 칸(재색인 setdefault 와 같음)."""
    out: dict[str, int] = {}
    for c, v in values:
        d = _norm(v)
        if d:
            out.setdefault(d, c)
    return out


def _row_kw(get, r: int) -> str:
    """순위행 키워드(v4 = A · 옛 C 폴백 — workbook._reindex_sheet 와 같은 규칙)."""
    return _key(get(r, _COL_KW)) or _key(get(r, _COL_NAME))


def _block_rows(ws, grid, head: int, last: int) -> tuple[list[int], str]:
    """블록이 시트와 같은지 확인 → (쓸 행 목록, 건너뛴 사유 ''=같음). 순위행 키워드가 다르면 그 행만 뺌."""
    m_get = lambda r, c: ws.cell(r, c).value   # noqa: E731
    s_get = lambda r, c: _at(grid, r, c)       # noqa: E731
    if _norm(s_get(head, _COL_METRIC)) != _LABEL_DATE or _key(s_get(head, _COL_NAME)) != _key(m_get(head, _COL_NAME)):
        return [], "상품명 다름"
    rows: list[int] = []
    for r in range(head + 1, last + 1):
        label = _norm(m_get(r, _COL_METRIC))
        if label not in _ROW_LABELS:
            continue
        if _norm(s_get(r, _COL_METRIC)) != label:
            return [], f"{r}행 지표 다름"
        if label == config.M_RANK and (not _row_kw(m_get, r) or _row_kw(m_get, r) != _row_kw(s_get, r)):
            continue                              # 빈 순위행·키워드 다른 행 = 그 행만 안 씀
        rows.append(r)
    return rows, ""


def _fill_block(ws, grid, head: int, rows: list[int], skip: set[str]) -> int:
    """한 블록: 마스터·시트 머리줄의 같은 날짜 글자 칸끼리 — 마스터 빈 칸 + 시트 값 있음 → 시트 값을 씀."""
    m_cols = _date_cols((c, ws.cell(head, c).value) for c in range(_FIRST_DATE, ws.max_column + 1))
    hrow = grid[head - 1] if head - 1 < len(grid) else []
    s_cols = _date_cols((c, hrow[c - 1]) for c in range(_FIRST_DATE, len(hrow) + 1))
    pairs = [(mc, s_cols[d]) for d, mc in m_cols.items() if d in s_cols and d not in skip]
    n = 0
    for r in rows:
        for mc, sc in pairs:
            cell = ws.cell(r, mc)
            sv = _at(grid, r, sc)
            if _blank(cell.value) and not _blank(sv):
                cell.value = sv
                n += 1
    return n


def fill_blank_cells(wb, grids: dict[str, list[list[Any]]], *, skip_labels=(), on_log=None) -> dict[str, int]:
    """시트 격자로 마스터 빈 칸을 채움(위 대응 규칙) → {사업자: 채운 칸 수}. 블록 건너뜀은 사업자별 한 줄 로그."""
    log = on_log or (lambda m: None)
    skip = {_norm(x) for x in skip_labels if _norm(x)}
    out: dict[str, int] = {}
    for biz, grid in grids.items():
        if biz not in wb.wb.sheetnames:
            continue
        ws = wb.wb[biz]
        n, skipped = 0, []
        for head, last in _blocks(ws):
            rows, why = _block_rows(ws, grid, head, last)
            if why:
                skipped.append(f"{_key(ws.cell(head, _COL_NAME).value)[:20]}({why})")
                continue
            n += _fill_block(ws, grid, head, rows, skip)
        out[biz] = n
        if skipped:
            log(f"  [구글시트] ⚠ '{biz}' 시트와 행이 달라 건너뛴 블록 {len(skipped)}개: {', '.join(skipped[:3])}"
                + (" …" if len(skipped) > 3 else ""))
    return out
