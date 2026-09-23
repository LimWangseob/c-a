"""출력 결과 구글시트의 `계정목록` 시트 생성·동기화 (Sheets API).

스키마(기존 openpyxl `계정 목록`과 동일 8열, designs/GSHEET_UNIFIED.md 확정):
    A 대표자 | B 사업자 | C 상품명(클릭 이동·노출명·통계시트 하이퍼링크) | D 계정ID |
    E 체험단 시작일 | F 체험단 종료일 | G 모니터링 종료일 | H 상태

- **자동 열 = A·B·C·D·H** (프로그램이 씀). **직원 입력 열 = E·F·G**(온라인 편집) → 프로그램이 **절대 안 씀**.
- 대표자(A)는 2026-09-17 추가. 기존 7열 시트는 sync 시 **A에 빈 열 1개 삽입**으로 자동 마이그레이션(모든 값·메모·서식이 오른쪽으로 밀려 새 위치와 정확히 일치).
- 신규 상품은 **계정별 그룹 맨 마지막**에 `insertDimension`으로 빈 행을 끼워 넣는다(기존 마케팅 행은
  통째로 아래로 밀리며 D~F 값·서식 그대로 보존 = 동시편집 안전). 관리대장에서 사라진 상품은 행을 지우지
  않고 **상태만 '⛔ 판매중지'**로(데이터 보존, 옵션 B). 다시 나타나면 상태 원복.
- 행 매칭은 **안정 키**(계정ID+vid 앵커, 노출명이 바뀌어도 불변)로 한다. 키는 A열 셀 **메모(note)**에 저장.

fallback 금지: 인증·권한·쿼터 오류는 `gsheet_api.GSheetError`로 올라간다(호출부가 한국어로 표시).
"""
from __future__ import annotations

from dataclasses import dataclass

# 열 인덱스(0-based)
COL_REP = 0                                    # 대표자(2026-09-17 추가)
COL_BUSINESS, COL_PRODUCT, COL_ACCOUNT = 1, 2, 3
COL_MKT_START, COL_MKT_END, COL_MKT_MON = 4, 5, 6
COL_STATUS = 7
N_COLS = 8
HEADER_ROW0 = 1        # 헤더가 있는 0-based 행(=시트 2행). 0행=제목.
DATA_START0 = 2        # 데이터 시작 0-based 행(=시트 3행)
DISCONTINUED = "⛔ 판매중지"
INDEX_SHEET_NAME = "계정목록"   # 결과 구글시트의 계정목록 시트명(openpyxl '계정 목록'과 구분 — 공백 없음)
# 헤더행(제목) = **전체 열 동일 색**(사용자 지정)으로, 데이터 행(은은한 밴드색)보다 진하게 해 명확히 구분.
# 굵은 글씨(_header_request).
_HEAD_FILL = {"red": 0.718, "green": 0.788, "blue": 0.910}  # B7C9E8 헤더 전체(진한 청회색)
# 사업자별 바탕색 밴딩(시각 구분) — **행 전체(A~G) 동일 색**, 사업자마다 다른 색으로 순환.
# 사업자 등장 순서 band(0,1,2,…)를 팔레트 길이로 나눈 나머지에 매핑 → 인접 사업자는 항상 다른 색.
# 중간 채도의 파스텔(검은 글씨 읽힘·너무 진하지 않게, 사용자 지정) + **인접이 웜↔쿨 교대**로 대비를
# 키움(짝=웜, 홀=쿨). 8개 초과 시 색이 다시 순환(웜/쿨 교대라 순환 경계도 대비 유지).
_BAND_FILLS = ({"red": 0.984, "green": 0.867, "blue": 0.753},   # 살구(웜)   FBDDC0
               {"red": 0.776, "green": 0.855, "blue": 0.953},   # 파랑(쿨)   C6DAF3
               {"red": 0.961, "green": 0.906, "blue": 0.659},   # 노랑(웜)   F5E7A8
               {"red": 0.749, "green": 0.890, "blue": 0.871},   # 청록(쿨)   BFE3DE
               {"red": 0.965, "green": 0.812, "blue": 0.871},   # 분홍(웜)   F6CFDE
               {"red": 0.804, "green": 0.910, "blue": 0.784},   # 초록(쿨)   CDE8C8
               {"red": 0.953, "green": 0.788, "blue": 0.761},   # 로즈(웜)   F3C9C2
               {"red": 0.851, "green": 0.812, "blue": 0.937})   # 라벤더(쿨) D9CFEF


def _band_fill(band: int) -> dict:
    return _BAND_FILLS[(band or 0) % len(_BAND_FILLS)]


@dataclass
class IndexRow:
    """계정목록 한 행의 **자동 열** 데이터(프로그램 산출). 마케팅 3열은 여기 없다(직원 소유)."""
    business: str            # B
    product: str             # C 표시명(노출명)
    account_id: str          # D
    status: str              # H 예: 예정/체험단중/모니터링/종료/미수집/⛔ 판매중지
    key: str                 # 안정 매칭 키(계정ID+vid 앵커). 노출명이 바뀌어도 불변
    link_gid: int | None = None   # C 하이퍼링크 대상 통계시트 gid
    link_row: int | None = None   # C 하이퍼링크 대상 행(상품 블록 헤더)
    band: int = 0            # 사업자 등장 순서 인덱스 → 바탕색 밴딩(사업자별 시각 구분)
    representative: str = ""  # A 대표자(관리대장 대표자명)


@dataclass
class ExistingRow:
    grid_row: int            # 0-based 현재 격자 행
    account_id: str
    key: str                 # A열 메모에서 읽은 안정 키(없으면 합성)


@dataclass
class SyncPlan:
    updates: list[tuple[int, IndexRow]]      # (최종 0-based 행, 데이터) — 기존 매칭행 자동열 갱신
    inserts: list[tuple[int, IndexRow]]      # (최종 0-based 행, 데이터) — 신규(빈 행 삽입 후 기록)
    discontinue: list[tuple[int, str]]       # (최종 0-based 행, 계정ID) — 상태만 ⛔ + 사업자 밴드색만
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
                discontinue.append((grid, e.account_id))  # 관리대장에서 사라짐 → 상태 ⛔ + 밴드색만
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
    """A·B·C·D(+B열=사업자 셀에 키 메모)와 H(상태)만 쓰는 updateCells 요청(마케팅 E~G는 건드리지 않음)."""
    bg = {"backgroundColor": _band_fill(row.band)}   # 사업자별 밴드색(A·B·C·D·H만 — E~G 마케팅색 불변)
    abcd = {
        "updateCells": {
            "start": {"sheetId": sheet_id, "rowIndex": grid_row, "columnIndex": COL_REP},
            "rows": [{"values": [
                {**_s(row.representative), "userEnteredFormat": bg},              # A 대표자
                {**_s(row.business), "note": row.key, "userEnteredFormat": bg},   # B 사업자 + 안정 키 메모
                {**_product_cell(row), "userEnteredFormat": bg},                  # C 상품명(링크)
                {**_s(row.account_id), "userEnteredFormat": bg},                  # D 계정ID
            ]}],
            "fields": "userEnteredValue,note,userEnteredFormat.backgroundColor",
        }
    }
    h = {
        "updateCells": {
            "start": {"sheetId": sheet_id, "rowIndex": grid_row, "columnIndex": COL_STATUS},
            "rows": [{"values": [{**_s(row.status), "userEnteredFormat": bg}]}],
            "fields": "userEnteredValue,userEnteredFormat.backgroundColor",
        }
    }
    return [abcd, h]


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


def _mkt_fill_request(sheet_id: int, grid_row: int, band: int) -> dict:
    """행의 D~F(마케팅 입력열)를 그 사업자 밴드색으로 칠한다 → **행 전체 동일 바탕색**.
    배경만 설정(값·다른 서식 불변)이라 직원 입력 D~F 값은 보존된다(repeatCell = updateCells 아님)."""
    return {
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": grid_row, "endRowIndex": grid_row + 1,
                      "startColumnIndex": COL_MKT_START, "endColumnIndex": COL_MKT_MON + 1},
            "cell": {"userEnteredFormat": {"backgroundColor": _band_fill(band),
                                           "horizontalAlignment": "CENTER"}},
            "fields": "userEnteredFormat.backgroundColor,userEnteredFormat.horizontalAlignment",
        }
    }


def _row_band_fill_request(sheet_id: int, grid_row: int, band: int) -> dict:
    """행 **전체(A~G)** 를 사업자 밴드색으로 칠한다(배경만 = 값 보존). 판매중지 행도 사업자별 동일색
    유지용 — 값은 안 건드리므로 ⛔ 상태·마케팅 D~F 값 모두 보존된다."""
    return {
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": grid_row, "endRowIndex": grid_row + 1,
                      "startColumnIndex": 0, "endColumnIndex": N_COLS},
            "cell": {"userEnteredFormat": {"backgroundColor": _band_fill(band)}},
            "fields": "userEnteredFormat.backgroundColor",
        }
    }


def _header_request(sheet_id: int) -> dict:
    """헤더행(2행)을 현재 `_HEADS` 라벨·서식으로 (재)기록. 전체생성·증분 모두에서 호출해 라벨 변경
    (예 '마케팅 시작일'→'체험단 시작일')이 **기존 시트에도** 반영되게 한다(증분은 헤더를 안 건드렸던 문제 보완)."""
    head_vals = []
    for h in _HEADS:                                  # 제목줄 전체 동일 색(_HEAD_FILL) — 열마다 안 다르게
        head_vals.append({**_s(h), "userEnteredFormat": {
            "textFormat": {"bold": True}, "horizontalAlignment": "CENTER", "backgroundColor": _HEAD_FILL}})
    return {"updateCells": {
        "start": {"sheetId": sheet_id, "rowIndex": HEADER_ROW0, "columnIndex": 0},
        "rows": [{"values": head_vals}], "fields": "userEnteredValue,userEnteredFormat"}}


def _rep_cell_request(sheet_id: int, grid_row: int, rep: str, band: int) -> dict:
    """판매중지 행의 **A(대표자) 셀**만 값+밴드색으로 갱신(다른 값·직원 마케팅 미접촉).
    살아있는 계정의 판매중지 상품 행이 대표자 공란이던 문제 보정(2026-09-17)."""
    return {"updateCells": {
        "start": {"sheetId": sheet_id, "rowIndex": grid_row, "columnIndex": COL_REP},
        "rows": [{"values": [{**_s(rep), "userEnteredFormat": {"backgroundColor": _band_fill(band)}}]}],
        "fields": "userEnteredValue,userEnteredFormat.backgroundColor"}}


def _build_requests_for_plan(sheet_id: int, plan: SyncPlan,
                             band_by_acct: dict[str, int] | None = None,
                             rep_by_acct: dict[str, str] | None = None) -> list[dict]:
    """증분 동기화 요청 묶음. 삽입은 최종 위치 오름차순으로(선삽입이 후위치 인덱스를 맞춰줌).

    band_by_acct: 계정ID→밴드(desired 로스터에서). 판매중지 행을 그 계정 밴드색으로 칠하는 데 쓴다.
    rep_by_acct: 계정ID→대표자(desired 로스터에서). 판매중지 행의 대표자 컬럼(A)을 채운다(공란 방지).
    (계정이 로스터에서 완전히 사라졌으면 없음 → 색·대표자는 그대로 두고 상태만 갱신)."""
    band_by_acct = band_by_acct or {}
    rep_by_acct = rep_by_acct or {}
    reqs: list[dict] = [_header_request(sheet_id)]   # 헤더 라벨 항상 최신화(행 1=헤더, 삽입 대상 밖이라 안전)
    for grid_row, _row in sorted(plan.inserts, key=lambda t: t[0]):
        reqs.append(_insert_blank_row_request(sheet_id, grid_row))
    for grid_row, row in plan.inserts:
        reqs += _auto_cells_request(sheet_id, grid_row, row)
        reqs.append(_mkt_fill_request(sheet_id, grid_row, row.band))
    for grid_row, row in plan.updates:
        reqs += _auto_cells_request(sheet_id, grid_row, row)
        reqs.append(_mkt_fill_request(sheet_id, grid_row, row.band))   # 기존 행 D~F도 밴드색으로(행 전체 동일)
    for grid_row, acct in plan.discontinue:
        reqs.append(_status_only_request(sheet_id, grid_row, DISCONTINUED))
        if acct in band_by_acct:                     # 판매중지 행도 계정 밴드색(행 전체 동일) — 값 보존
            reqs.append(_row_band_fill_request(sheet_id, grid_row, band_by_acct[acct]))
            if rep_by_acct.get(acct):                 # 대표자 공란 방지(그 계정 대표자 채움)
                reqs.append(_rep_cell_request(sheet_id, grid_row, rep_by_acct[acct], band_by_acct[acct]))
    return reqs


_HEADS = ["대표자", "사업자", "상품명(클릭 이동)", "계정ID", "체험단 시작일", "체험단 종료일", "모니터링 종료일", "상태"]
_MKT_LABELS = (_HEADS[COL_MKT_START], _HEADS[COL_MKT_END], _HEADS[COL_MKT_MON])   # 체험단 3열 헤더 라벨
_COL_WIDTHS = {COL_REP: 110, COL_BUSINESS: 150, COL_PRODUCT: 300, COL_ACCOUNT: 110,
               COL_MKT_START: 95, COL_MKT_END: 95, COL_MKT_MON: 100, COL_STATUS: 90}


def _full_build_requests(sheet_id: int, desired: list[IndexRow]) -> list[dict]:
    """빈 계정목록 최초 생성 — 제목·헤더·전체 행·서식(틀고정·마케팅색·열너비)."""
    reqs: list[dict] = []
    # 제목(A1:G1 병합)
    reqs.append({"mergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                                          "startColumnIndex": 0, "endColumnIndex": N_COLS},
                                "mergeType": "MERGE_ALL"}})   # 제목 A1:G1 한 칸으로(‘MERGE_ROW’는 무효값)
    n_prod = sum(1 for d in desired if d.status != DISCONTINUED)
    reqs.append({"updateCells": {
        "start": {"sheetId": sheet_id, "rowIndex": 0, "columnIndex": 0},
        "rows": [{"values": [{**_s(f"계정목록 · 상품 {n_prod}개"),
                              "userEnteredFormat": {"textFormat": {"bold": True, "fontSize": 14},
                                                    "horizontalAlignment": "CENTER"}}]}],
        "fields": "userEnteredValue,userEnteredFormat"}})
    reqs.append(_header_request(sheet_id))    # 헤더(2행) 라벨·서식
    # 데이터 행
    for i, row in enumerate(desired):
        grid = DATA_START0 + i
        reqs += _auto_cells_request(sheet_id, grid, row)
        reqs.append(_mkt_fill_request(sheet_id, grid, row.band))
    # 틀고정(제목·헤더 2행 + A~C 3열) + 열너비
    # 틀고정: 제목·헤더 2행만. ⚠ 열 고정은 넣지 않는다 — 제목이 A1:G1 병합이라 열 고정(예 3열)이 그 병합을
    # '일부만' 자르면 구글 시트가 400 거부(엑셀과 달리 병합 셀을 가로지르는 틀고정 불가). 계정목록은 7열뿐이라
    # 가로 스크롤이 거의 없어 열 고정 실익도 작다.
    reqs.append({"updateSheetProperties": {
        "properties": {"sheetId": sheet_id,
                       "gridProperties": {"frozenRowCount": 2, "frozenColumnCount": 0}},
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
    if len(values) <= HEADER_ROW0:
        return {}
    # 열 위치를 **헤더(2행) 라벨로 탐지** — 대표자 컬럼 추가로 밀린 신규 레이아웃과 옛 레이아웃 모두 안전.
    hdr = [str(h).strip() for h in values[HEADER_ROW0]]

    def _col(label):
        return hdr.index(label) if label in hdr else None

    c_start, c_end, c_mon = _col(_MKT_LABELS[0]), _col(_MKT_LABELS[1]), _col(_MKT_LABELS[2])
    c_biz, c_acct = _col("사업자"), _col("계정ID")
    c_prod = next((i for i, h in enumerate(hdr) if h.startswith("상품명")), None)
    if c_start is None:                     # 마케팅 열이 없으면(레이아웃 이상) 빈 dict
        return {}

    def _cell(row, c):
        return row[c] if (c is not None and len(row) > c) else ""

    out: dict[str, tuple[str, str, str]] = {}
    for gi in range(DATA_START0, len(values)):
        row = values[gi]
        start, end, mon = _cell(row, c_start), _cell(row, c_end), _cell(row, c_mon)
        if not (start or end or mon):
            continue
        note = (notes[gi][c_biz] if (c_biz is not None and gi < len(notes)
                                     and len(notes[gi]) > c_biz) else None)
        key = note or _synth_key(_cell(row, c_acct), _cell(row, c_prod))
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
    band_by_acct: dict[str, int] = {}                # **계정ID** 등장 순서 → 밴드 인덱스(계정ID별 바탕색, 2026-09-17)
    for biz, prod, hdr, has_sheet in wb.product_roster():
        acct = wb.account_id_of(biz)
        registered = wb.registered_name(biz, prod) or prod
        key = marketing_key(acct, registered)
        linkable = bool(has_sheet and prod and hdr)
        gid = stats_gids.get(biz) if linkable else None
        band = band_by_acct.setdefault(acct or biz, len(band_by_acct))   # 계정ID 기준(없으면 사업자 폴백)
        rows.append(IndexRow(business=biz, product=prod, account_id=acct,
                             status=wb.status_of(biz, prod, has_sheet), key=key,
                             link_gid=gid, link_row=(hdr if (linkable and gid is not None) else None),
                             band=band, representative=wb.representative_of(biz)))
    return rows


def _ensure_rep_column(client, sheet: str, sheet_id: int) -> None:
    """기존 7열(대표자 없음) 계정목록을 8열로 **자동 마이그레이션** — A에 빈 열 1개 삽입(2026-09-17).

    insertDimension(COLUMNS 0) 은 모든 값·메모·서식·직원 마케팅을 오른쪽으로 밀어 새 위치와 정확히
    일치시킨다(안정 키 메모도 옛 A '사업자'→새 B '사업자'로 이동 = COL_BUSINESS 와 일치). 이미 대표자
    열이면 no-op. 헤더/데이터가 없으면(신규 시트) 생략 → full build 가 새 레이아웃으로 만든다."""
    values, _ = client.read_grid(sheet)
    if len(values) <= HEADER_ROW0:
        return
    hdr = [str(h).strip() for h in (values[HEADER_ROW0] or [])]
    if hdr and len(hdr) > COL_REP and hdr[COL_REP] == _HEADS[COL_REP]:
        return                                        # 이미 대표자 열 있음
    client.batch_update([{"insertDimension": {
        "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
        "inheritFromBefore": False}}])


def delete_accounts(client, removed, *, sheet: str = INDEX_SHEET_NAME, on_log=None) -> int:
    """관리대장에서 **줄이 사라진 계정**을 결과 구글시트에서 완전 삭제 — 계정목록 행 + 그 사업자 통계 시트.

    removed = [(사업자, 계정ID), …]. ⚠ 되돌릴 수 없음. '판매중지'로 남은 계정은 여기 오지 않는다(호출부가 구분).
    계정목록 행은 **계정ID 열(헤더로 탐지)** 로 매칭해 아래→위로 deleteDimension(인덱스 안정). 삭제 요청 수 반환.
    """
    log = on_log or (lambda m: None)
    if not removed:
        return 0
    ids = {str(a).strip() for _b, a in removed if str(a).strip()}
    n = 0
    titles = client.sheet_titles()
    # 1) 계정목록 행 삭제(계정ID 열 헤더 탐지)
    if ids and sheet in titles:
        sid = client.sheet_id(sheet)
        values, _ = client.read_grid(sheet)
        if sid is not None and len(values) > HEADER_ROW0:
            hdr = [str(h).strip() for h in values[HEADER_ROW0]]
            c_acct = hdr.index("계정ID") if "계정ID" in hdr else None
            if c_acct is not None:
                del_rows = []
                for gi in range(DATA_START0, len(values)):
                    row = values[gi]
                    acct = str(row[c_acct]).strip() if len(row) > c_acct and row[c_acct] else ""
                    if acct in ids:
                        del_rows.append(gi)
                reqs = [{"deleteDimension": {"range": {"sheetId": sid, "dimension": "ROWS",
                        "startIndex": gi, "endIndex": gi + 1}}} for gi in sorted(del_rows, reverse=True)]
                if reqs:
                    client.batch_update(reqs)      # 아래→위라 한 배치 내 인덱스 안정
                    n += len(reqs)
                    log(f"  [구글시트] 계정목록 행 {len(reqs)}개 삭제(삭제된 계정)")
    # 2) 통계 시트 삭제(그 사업자 시트)
    for biz, _a in removed:
        sid = client.sheet_id(biz)
        if sid is not None:
            client.batch_update([{"deleteSheet": {"sheetId": sid}}])
            n += 1
            log(f"  [구글시트] 통계 시트 '{biz}' 삭제")
    return n


_GRID_ROW_BUFFER = 50   # 삽입 여유행(매 실행 재확장 방지 — 신규 상품/계정 몇 개는 그리드 확장 없이 소화)


def _grid_grow_requests(client, sheet: str, sheet_id: int, n_data_rows: int) -> list[dict]:
    """삽입/기록이 그리드 끝을 넘어 400 나지 않게, 부족하면 **미리 행을 늘린다**(appendDimension).

    insertDimension(inheritFromBefore=False)은 startIndex < 현재 rowCount 라야 한다 — 데이터가 그리드를
    꽉 채우면 신규 삽입이 그리드 끝(==rowCount)을 넘어 400(라이브 2026-09-23 실측). 삽입 전 rowCount 를
    `헤더2 + 데이터행수 + 여유(_GRID_ROW_BUFFER)` 이상으로 맞춘다. rowCount 를 못 읽으면(폴백) 확장 생략."""
    need = DATA_START0 + n_data_rows + _GRID_ROW_BUFFER
    cur = client.grid_row_count(sheet)
    if cur is not None and cur < need:
        return [{"appendDimension": {"sheetId": sheet_id, "dimension": "ROWS", "length": need - cur}}]
    return []


def sync_index(client, desired: list[IndexRow], *, sheet: str = INDEX_SHEET_NAME) -> SyncPlan:
    """결과 구글시트의 `계정목록`을 원하는 로스터에 맞춰 생성/동기화하고 계획을 반환.

    비어 있으면 전체 생성, 아니면 증분(자동열만 갱신·신규 삽입·판매중지 표기). 마케팅 D~F는 안 건드린다.
    삽입이 그리드 끝을 넘지 않게 **미리 그리드를 확장**한다(부족할 때만 — insertDimension 400 방지).
    """
    sheet_id = client.ensure_sheet(sheet)
    _ensure_rep_column(client, sheet, sheet_id)   # 옛 7열 시트면 A에 대표자 빈 열 삽입(멱등) → 아래 읽기는 새 레이아웃
    existing = _read_existing(client, sheet)
    if not existing:
        grow = _grid_grow_requests(client, sheet, sheet_id, len(desired))
        client.batch_update(grow + _full_build_requests(sheet_id, desired))
        # 최초 생성도 계획 형태로 반환(삽입=전체)
        return SyncPlan(updates=[], inserts=[(DATA_START0 + i, d) for i, d in enumerate(desired)],
                        discontinue=[], total_rows=len(desired))
    plan = plan_sync(existing, desired)
    band_by_acct = {r.account_id: r.band for r in desired}   # 판매중지 행도 계정 밴드색으로 칠하기 위함
    rep_by_acct = {r.account_id: r.representative for r in desired if r.representative}  # 판매중지 행 대표자 채움
    grow = _grid_grow_requests(client, sheet, sheet_id, plan.total_rows)
    client.batch_update(grow + _build_requests_for_plan(sheet_id, plan, band_by_acct, rep_by_acct))
    return plan
