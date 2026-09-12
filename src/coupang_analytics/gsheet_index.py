"""출력 결과 구글시트의 `계정목록` 시트 생성·동기화 (Sheets API).

스키마(기존 openpyxl `계정 목록`과 동일 7열, designs/GSHEET_UNIFIED.md 확정):
    A 사업자 | B 상품명(클릭 이동·노출명·통계시트 하이퍼링크) | C 계정ID |
    D 마케팅 시작일 | E 마케팅 종료일 | F 모니터링 종료일 | G 상태

- **자동 열 = A·B·C·G** (프로그램이 씀). **직원 입력 열 = D·E·F**(온라인 편집) → 프로그램이 **절대 안 씀**.
- 신규 상품은 **계정별 그룹 맨 마지막**에 `insertDimension`으로 빈 행을 끼워 넣는다(기존 마케팅 행은
  통째로 아래로 밀리며 D~F 값·서식 그대로 보존 = 동시편집 안전). 관리대장에서 사라진 상품은 행을 지우지
  않고 **상태만 '⛔ 판매중지'**로(데이터 보존, 옵션 B). 다시 나타나면 상태 원복.
- 행 매칭은 **안정 키**(계정ID+vid 앵커, 노출명이 바뀌어도 불변)로 한다. 키는 A열 셀 **메모(note)**에 저장.

fallback 금지: 인증·권한·쿼터 오류는 `gsheet_api.GSheetError`로 올라간다(호출부가 한국어로 표시).
"""
from __future__ import annotations

from dataclasses import dataclass

# 열 인덱스(0-based)
COL_BUSINESS, COL_PRODUCT, COL_ACCOUNT = 0, 1, 2
COL_MKT_START, COL_MKT_END, COL_MKT_MON = 3, 4, 5
COL_STATUS = 6
N_COLS = 7
HEADER_ROW0 = 1        # 헤더가 있는 0-based 행(=시트 2행). 0행=제목.
DATA_START0 = 2        # 데이터 시작 0-based 행(=시트 3행)
DISCONTINUED = "⛔ 판매중지"
INDEX_SHEET_NAME = "계정목록"   # 결과 구글시트의 계정목록 시트명(openpyxl '계정 목록'과 구분 — 공백 없음)
_MKT_FILL = {"red": 1.0, "green": 0.949, "blue": 0.8}     # FFF2CC 마케팅 입력열 안내색
_HEAD_FILL = {"red": 0.851, "green": 0.882, "blue": 0.949}  # D9E9FA 헤더


@dataclass
class IndexRow:
    """계정목록 한 행의 **자동 열** 데이터(프로그램 산출). 마케팅 3열은 여기 없다(직원 소유)."""
    business: str            # A
    product: str             # B 표시명(노출명)
    account_id: str          # C
    status: str              # G 예: 예정/마케팅중/모니터링/종료/미수집/⛔ 판매중지
    key: str                 # 안정 매칭 키(계정ID+vid 앵커). 노출명이 바뀌어도 불변
    link_gid: int | None = None   # B 하이퍼링크 대상 통계시트 gid
    link_row: int | None = None   # B 하이퍼링크 대상 행(상품 블록 헤더)


@dataclass
class ExistingRow:
    grid_row: int            # 0-based 현재 격자 행
    account_id: str
    key: str                 # A열 메모에서 읽은 안정 키(없으면 합성)


@dataclass
class SyncPlan:
    updates: list[tuple[int, IndexRow]]      # (최종 0-based 행, 데이터) — 기존 매칭행 자동열 갱신
    inserts: list[tuple[int, IndexRow]]      # (최종 0-based 행, 데이터) — 신규(빈 행 삽입 후 기록)
    discontinue: list[int]                   # 최종 0-based 행 — 상태만 ⛔ 판매중지
    total_rows: int                          # 최종 데이터 행 수(검증용)


def _synth_key(account_id: str, product: str) -> str:
    return f"{account_id}␟{product}"    # 메모 키가 없을 때의 폴백(계정ID+상품명)


def plan_sync(existing: list[ExistingRow], desired: list[IndexRow]) -> SyncPlan:
    """기존 행 배치와 원하는 로스터를 비교해 **갱신/삽입/판매중지** 계획을 세운다(순수 함수·테스트 가능).

    규칙: 기존 계정 순서·행 순서 보존 → 각 계정 그룹 끝에 신규 상품 삽입 → 새 계정은 맨 아래. 기존 순서는
    절대 재배치하지 않으므로 삽입만으로 마케팅 행이 안전하게 밀린다.
    """
    existing_by_key = {e.key: e for e in existing}
    desired_by_key = {d.key: d for d in desired}

    # 계정 출력 순서 = 기존 시트의 계정 등장 순서 + (기존에 없던) 신규 계정을 desired 순서로 뒤에.
    existing_acct_order: list[str] = []
    existing_by_acct: dict[str, list[ExistingRow]] = {}
    for e in existing:
        if e.account_id not in existing_by_acct:
            existing_by_acct[e.account_id] = []
            existing_acct_order.append(e.account_id)
        existing_by_acct[e.account_id].append(e)

    desired_by_acct: dict[str, list[IndexRow]] = {}
    desired_acct_order: list[str] = []
    for d in desired:
        if d.account_id not in desired_by_acct:
            desired_by_acct[d.account_id] = []
            desired_acct_order.append(d.account_id)
        desired_by_acct[d.account_id].append(d)

    acct_order = existing_acct_order + [a for a in desired_acct_order if a not in existing_by_acct]

    # 최종 슬롯 순서를 구성: ('keep', ExistingRow) | ('new', IndexRow)
    slots: list[tuple[str, object]] = []
    for acct in acct_order:
        for e in existing_by_acct.get(acct, []):          # 기존 행(순서 보존)
            slots.append(("keep", e))
        for d in desired_by_acct.get(acct, []):           # 이 계정의 신규 상품 → 그룹 끝에
            if d.key not in existing_by_key:
                slots.append(("new", d))

    updates: list[tuple[int, IndexRow]] = []
    inserts: list[tuple[int, IndexRow]] = []
    discontinue: list[int] = []
    for pos, (kind, obj) in enumerate(slots):
        grid = DATA_START0 + pos
        if kind == "keep":
            e: ExistingRow = obj  # type: ignore[assignment]
            d = desired_by_key.get(e.key)
            if d is not None:
                updates.append((grid, d))                 # 자동열 갱신(노출명/상태 변동 반영)
            else:
                discontinue.append(grid)                  # 관리대장에서 사라짐 → 상태만 ⛔
        else:
            inserts.append((grid, obj))                   # type: ignore[arg-type]
    return SyncPlan(updates=updates, inserts=inserts, discontinue=discontinue, total_rows=len(slots))


# ── Sheets API 요청 빌더 ────────────────────────────────────────────
def _s(v: str) -> dict:
    return {"userEnteredValue": {"stringValue": v}}


def _product_cell(row: IndexRow) -> dict:
    """B 상품명 셀 — 통계시트 링크가 있으면 HYPERLINK 수식, 없으면 텍스트."""
    if row.link_gid is not None and row.link_row is not None:
        loc = f"#gid={row.link_gid}&range=A{row.link_row}"
        name = row.product.replace('"', '""')
        return {"userEnteredValue": {"formulaValue": f'=HYPERLINK("{loc}","{name}")'}}
    return _s(row.product)


def _auto_cells_request(sheet_id: int, grid_row: int, row: IndexRow) -> list[dict]:
    """A·B·C(+A열 키 메모)와 G(상태)만 쓰는 updateCells 요청(마케팅 D~F는 건드리지 않음)."""
    abc = {
        "updateCells": {
            "start": {"sheetId": sheet_id, "rowIndex": grid_row, "columnIndex": COL_BUSINESS},
            "rows": [{"values": [
                {**_s(row.business), "note": row.key},   # 안정 키를 A열 메모에 보존
                _product_cell(row),
                _s(row.account_id),
            ]}],
            "fields": "userEnteredValue,note",
        }
    }
    g = {
        "updateCells": {
            "start": {"sheetId": sheet_id, "rowIndex": grid_row, "columnIndex": COL_STATUS},
            "rows": [{"values": [_s(row.status)]}],
            "fields": "userEnteredValue",
        }
    }
    return [abc, g]


def _status_only_request(sheet_id: int, grid_row: int, status: str) -> dict:
    return {
        "updateCells": {
            "start": {"sheetId": sheet_id, "rowIndex": grid_row, "columnIndex": COL_STATUS},
            "rows": [{"values": [_s(status)]}],
            "fields": "userEnteredValue",
        }
    }


def _insert_blank_row_request(sheet_id: int, grid_row: int) -> dict:
    return {
        "insertDimension": {
            "range": {"sheetId": sheet_id, "dimension": "ROWS",
                      "startIndex": grid_row, "endIndex": grid_row + 1},
            "inheritFromBefore": False,
        }
    }


def _mkt_fill_request(sheet_id: int, grid_row: int) -> dict:
    """신규 행의 마케팅 D~F에 안내색만 칠한다(값은 비움 — 직원이 입력)."""
    return {
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": grid_row, "endRowIndex": grid_row + 1,
                      "startColumnIndex": COL_MKT_START, "endColumnIndex": COL_MKT_MON + 1},
            "cell": {"userEnteredFormat": {"backgroundColor": _MKT_FILL,
                                           "horizontalAlignment": "CENTER"}},
            "fields": "userEnteredFormat.backgroundColor,userEnteredFormat.horizontalAlignment",
        }
    }


def _build_requests_for_plan(sheet_id: int, plan: SyncPlan) -> list[dict]:
    """증분 동기화 요청 묶음. 삽입은 최종 위치 오름차순으로(선삽입이 후위치 인덱스를 맞춰줌)."""
    reqs: list[dict] = []
    for grid_row, _row in sorted(plan.inserts, key=lambda t: t[0]):
        reqs.append(_insert_blank_row_request(sheet_id, grid_row))
    for grid_row, row in plan.inserts:
        reqs += _auto_cells_request(sheet_id, grid_row, row)
        reqs.append(_mkt_fill_request(sheet_id, grid_row))
    for grid_row, row in plan.updates:
        reqs += _auto_cells_request(sheet_id, grid_row, row)
    for grid_row in plan.discontinue:
        reqs.append(_status_only_request(sheet_id, grid_row, DISCONTINUED))
    return reqs


_HEADS = ["사업자", "상품명(클릭 이동)", "계정ID", "마케팅 시작일", "마케팅 종료일", "모니터링 종료일", "상태"]
_COL_WIDTHS = {COL_BUSINESS: 150, COL_PRODUCT: 300, COL_ACCOUNT: 110,
               COL_MKT_START: 95, COL_MKT_END: 95, COL_MKT_MON: 100, COL_STATUS: 90}


def _full_build_requests(sheet_id: int, desired: list[IndexRow]) -> list[dict]:
    """빈 계정목록 최초 생성 — 제목·헤더·전체 행·서식(틀고정·마케팅색·열너비)."""
    reqs: list[dict] = []
    # 제목(A1:G1 병합)
    reqs.append({"mergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                                          "startColumnIndex": 0, "endColumnIndex": N_COLS},
                                "mergeType": "MERGE_ROW"}})
    n_prod = sum(1 for d in desired if d.status != DISCONTINUED)
    reqs.append({"updateCells": {
        "start": {"sheetId": sheet_id, "rowIndex": 0, "columnIndex": 0},
        "rows": [{"values": [{**_s(f"계정목록 · 상품 {n_prod}개"),
                              "userEnteredFormat": {"textFormat": {"bold": True, "fontSize": 14},
                                                    "horizontalAlignment": "CENTER"}}]}],
        "fields": "userEnteredValue,userEnteredFormat"}})
    # 헤더(2행)
    head_vals = []
    for c, h in enumerate(_HEADS):
        fill = _MKT_FILL if COL_MKT_START <= c <= COL_MKT_MON else _HEAD_FILL
        head_vals.append({**_s(h), "userEnteredFormat": {
            "textFormat": {"bold": True}, "horizontalAlignment": "CENTER", "backgroundColor": fill}})
    reqs.append({"updateCells": {
        "start": {"sheetId": sheet_id, "rowIndex": HEADER_ROW0, "columnIndex": 0},
        "rows": [{"values": head_vals}], "fields": "userEnteredValue,userEnteredFormat"}})
    # 데이터 행
    for i, row in enumerate(desired):
        grid = DATA_START0 + i
        reqs += _auto_cells_request(sheet_id, grid, row)
        reqs.append(_mkt_fill_request(sheet_id, grid))
    # 틀고정(제목·헤더 2행 + A~C 3열) + 열너비
    reqs.append({"updateSheetProperties": {
        "properties": {"sheetId": sheet_id,
                       "gridProperties": {"frozenRowCount": 2, "frozenColumnCount": 3}},
        "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"}})
    for c, w in _COL_WIDTHS.items():
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": c, "endIndex": c + 1},
            "properties": {"pixelSize": w}, "fields": "pixelSize"}})
    return reqs


def _read_existing(client, sheet: str) -> list[ExistingRow]:
    """계정목록의 기존 데이터 행을 (계정ID, 안정키) 로 읽는다. 키는 A열 메모, 없으면 합성."""
    values, notes = client.read_grid(sheet, notes=True)
    out: list[ExistingRow] = []
    for gi in range(DATA_START0, len(values)):
        row = values[gi]
        biz = row[COL_BUSINESS] if len(row) > COL_BUSINESS else ""
        prod = row[COL_PRODUCT] if len(row) > COL_PRODUCT else ""
        acct = row[COL_ACCOUNT] if len(row) > COL_ACCOUNT else ""
        if not (biz or prod or acct):
            continue                                     # 완전 빈 행은 건너뜀
        note = notes[gi][COL_BUSINESS] if (gi < len(notes) and len(notes[gi]) > COL_BUSINESS) else None
        out.append(ExistingRow(grid_row=gi, account_id=acct, key=note or _synth_key(acct, prod)))
    return out


def marketing_key(account_id: str, product: str) -> str:
    """마케팅 병합용 안정 키 = 계정ID + 등록 상품명(노출명이 바뀌어도 불변).

    Phase 3a 가 A열 메모에 저장하는 키와 동일 규약이라, 메모가 있으면 그것으로, 없으면 이 합성 키로 매칭된다.
    """
    return _synth_key(account_id, product)


def read_marketing(client, *, sheet: str = INDEX_SHEET_NAME) -> dict[str, tuple[str, str, str]]:
    """출력 `계정목록`의 **직원 입력 마케팅(D~F)** 을 {안정키: (시작, 종료, 모니터링종료)} 로 읽는다.

    값이 하나도 없는 행은 건너뛴다. 시트가 아직 없으면 빈 dict(첫 실행 대비 — fallback 아님, 정상 상태).
    """
    if sheet not in client.sheet_titles():
        return {}
    values, notes = client.read_grid(sheet, notes=True)

    def _cell(row, c):
        return row[c] if len(row) > c else ""

    out: dict[str, tuple[str, str, str]] = {}
    for gi in range(DATA_START0, len(values)):
        row = values[gi]
        start = _cell(row, COL_MKT_START)
        end = _cell(row, COL_MKT_END)
        mon = _cell(row, COL_MKT_MON)
        if not (start or end or mon):
            continue
        note = notes[gi][COL_BUSINESS] if (gi < len(notes) and len(notes[gi]) > COL_BUSINESS) else None
        key = note or _synth_key(_cell(row, COL_ACCOUNT), _cell(row, COL_PRODUCT))
        out[key] = (start, end, mon)
    return out


def apply_marketing(accounts, marketing_map: dict[str, tuple[str, str, str]]) -> int:
    """마케팅 맵을 InputList 계정/상품에 병합(직원 입력이 대장/기존값보다 우선). 반영 상품 수 반환.

    accounts 는 `input_list.Account` 시퀀스(덕타이핑 — a.account_id, a.products[*].name/mkt_*). 매칭된 상품만 갱신.
    """
    n = 0
    for a in accounts:
        for p in a.products:
            mk = marketing_map.get(marketing_key(a.account_id, p.name))
            if mk:
                p.mkt_start, p.mkt_end, p.mkt_mon = mk
                n += 1
    return n


def roster_from_workbook(wb, stats_gids: dict[str, int]) -> list[IndexRow]:
    """openpyxl `OutputWorkbook` → 계정목록 IndexRow 로스터(자동열만). 파이프라인이 sync_index 에 투입.

    - 순서·집합 = `wb.product_roster()`(openpyxl `계정 목록`과 동일).
    - **안정 키 = marketing_key(계정ID + 등록상품명)**(노출명이 바뀌어도 불변, 3c 마케팅 머지와 매칭 — §7).
      등록명이 없으면(옛 마스터) 노출명으로 폴백.
    - B 하이퍼링크 = 그 사업자 통계 시트 gid(`stats_gids`) + 블록 헤더행(있을 때만).
    """
    rows: list[IndexRow] = []
    for biz, prod, hdr, has_sheet in wb.product_roster():
        acct = wb.account_id_of(biz)
        registered = wb.registered_name(biz, prod) or prod
        key = marketing_key(acct, registered)
        linkable = bool(has_sheet and prod and hdr)
        gid = stats_gids.get(biz) if linkable else None
        rows.append(IndexRow(business=biz, product=prod, account_id=acct,
                             status=wb.status_of(biz, prod, has_sheet), key=key,
                             link_gid=gid, link_row=(hdr if (linkable and gid is not None) else None)))
    return rows


def sync_index(client, desired: list[IndexRow], *, sheet: str = INDEX_SHEET_NAME) -> SyncPlan:
    """결과 구글시트의 `계정목록`을 원하는 로스터에 맞춰 생성/동기화하고 계획을 반환.

    비어 있으면 전체 생성, 아니면 증분(자동열만 갱신·신규 삽입·판매중지 표기). 마케팅 D~F는 안 건드린다.
    """
    sheet_id = client.ensure_sheet(sheet)
    existing = _read_existing(client, sheet)
    if not existing:
        client.batch_update(_full_build_requests(sheet_id, desired))
        # 최초 생성도 계획 형태로 반환(삽입=전체)
        return SyncPlan(updates=[], inserts=[(DATA_START0 + i, d) for i, d in enumerate(desired)],
                        discontinue=[], total_rows=len(desired))
    plan = plan_sync(existing, desired)
    client.batch_update(_build_requests_for_plan(sheet_id, plan))
    return plan
