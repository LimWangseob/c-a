"""출력 워크북 '셀독 상품 데이터' — **시트=사업자, 상품 블록(계약/개인) + 키워드 노출순위, 일자 가로 누적**.

서식(사용자 `셀독 판매 데이터_서식.xlsx` 분석 반영):
  열  A=상품구분(계약/개인) 또는 사업자명 · C=상품명 또는 키워드 · F=검색량 · G=지표라벨 · H~=일자
  상품 블록(세로):
    [계약 상품][상품명] … [날짜][일자→]
      G=판매량/방문자/노출량/재고현황      (계약=로켓그로스)   ← 개인은 전체판매량/전체노출량
    [사업자명][키워드] … [검색량][비고]
      C=키워드 F=검색량 G=노출 순위 [일자별 순위→]           (PC 단일, 모바일 제외)
행 키: 상품지표=(사업자,상품,지표) · 키워드순위=(사업자,상품,키워드). 일자 컬럼은 시트 공유.
값 없으면 공란. 재개(이어서)는 시트에서 상품·키워드·채움여부를 되읽어 지원.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date, datetime as _dt, timedelta as _td
from pathlib import Path

import openpyxl
from openpyxl.cell.cell import Cell
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.hyperlink import Hyperlink

from . import config


def _unmerge_all(ws) -> None:
    """시트의 모든 병합을 해제. 희소(미실체화) 병합셀은 정규 Cell 로 먼저 채워 unmerge KeyError 를 막는다.

    openpyxl `insert_rows`/재서식이 병합셀과 함께 쓰이면 데이터가 유실되므로, 행 삽입·서식 전에 호출한다.
    """
    for mr in list(ws.merged_cells.ranges):
        for rr in range(mr.min_row, mr.max_row + 1):
            for cc in range(mr.min_col, mr.max_col + 1):
                if (rr, cc) not in ws._cells:
                    ws._cells[(rr, cc)] = Cell(ws, row=rr, column=cc)
        ws.unmerge_cells(str(mr))


@dataclass
class _StyleCtx:
    """apply_style 팔레트(폰트·채움·테두리·정렬) 묶음 — 시트/블록 서식 헬퍼가 공유."""
    font: Font
    bold: Font
    title_font: Font
    f_prod: PatternFill
    f_prod2: PatternFill          # 상품군 교대 배경(같은 등록상품명=한 군, 인접 군을 두 색으로 구분)
    f_prod_lt: PatternFill        # 값칸·키워드 옅은 상품군색(상품군 전체 은은히 통일)
    f_prod2_lt: PatternFill
    f_label: PatternFill
    f_kwhead: PatternFill
    f_kind: PatternFill
    mkt_fill: PatternFill
    box: Border
    center: Alignment
    wrap: Alignment
    thick: Side
    thin: Side
    mid: Side          # 기본↔옵션(같은 상품군 내부) 구분선 — 격자(thin)보다 진하고 그룹 바깥(thick)보다 얇게


def _sty_cell(ws, r, c, sty: _StyleCtx, *, fill=None, fnt=None, align=None, num=False) -> None:
    """셀 서식 적용(폰트·정렬·테두리·선택 채움/숫자서식). 분해 전 apply_style 내부 `cell` 클로저와 동일."""
    x = ws.cell(r, c)
    x.font = fnt or sty.font
    x.alignment = align or sty.center
    x.border = sty.box
    if fill:
        x.fill = fill
    if num and isinstance(x.value, (int, float)):
        x.number_format = "#,##0"


def _sty_merge(ws, r1, c1, r2, c2) -> None:
    if r2 > r1 or c2 > c1:
        ws.merge_cells(start_row=r1, start_column=c1, end_row=r2, end_column=c2)


@dataclass
class _IdxStyle:
    """계정 목록(목차) 행 렌더 팔레트 — _build_index / _index_row 공유."""
    font: Font
    gray_font: Font
    link_font: Font
    red_bold: Font
    box: Border
    center: Alignment
    left: Alignment
    mkt_fill: PatternFill


def _rekey_block(mapping: dict, biz: str, old: str, new: str) -> dict:
    """블록 인덱스의 (biz, old[, …]) 키를 (biz, new[, …]) 로 이동한 새 dict — 상품명 리네임용.

    3튜플(_metric_row/_kw_row: (biz, product, metric/kw))·2튜플(_block_vids: (biz, product)) 모두 처리."""
    out = {}
    for k, v in mapping.items():
        out[(biz, new, *k[2:]) if (k[0] == biz and k[1] == old) else k] = v
    return out


def _sty_edge(ws, maxc, row, side, style) -> None:
    """상품 블록 경계(첫 행 상단/마지막 행 하단) 테두리 — 그룹 바깥=굵은선(thick)·변형 사이=얇은선(thin)."""
    for c in range(1, maxc + 1):
        b = ws.cell(row, c).border
        ws.cell(row, c).border = Border(
            left=b.left, right=b.right,
            top=style if side == "top" else b.top,
            bottom=style if side == "bottom" else b.bottom)

_COL_KIND = 1      # A: (레이아웃 v4) 헤더 라벨 칸 / 옛 구분 라벨(마이그레이션 회수용)
_COL_KW = 1        # A: 키워드명(레이아웃 v4 좌측확장 A~E, 병합 앵커=A). 상품 헤더 라벨과 행 종류로 구분(G값)
_COL_NAME = 3      # C: 상품명(헤더행 KEY) / 헤더 값 칸(pos0 C:F)
_COL_SEARCH = 6    # F: 검색량
_COL_METRIC = 7    # G: 지표 라벨
_FIRST_DATE = 8    # H~: 일자
_LABEL_DATE = "날짜"
_NOT_SELLING_STATUSES = ("판매중지", "임시저장", "승인반려", "검토중")   # ③ 순위 조회 제외 대상(판매중/부분판매중만)
_LABEL_KEYWORD = "키워드"
_LABEL_SEARCH = "검색량"
_LABEL_NOTE = "비고"
_ALL_METRICS = frozenset(config.CONTRACT_METRICS + config.PERSONAL_METRICS)
_META_SHEET = "_상품ID"   # 숨김 시트: (사업자,상품)→등록상품명·판매상태·제목캐시. ⚠vid(3열)는 폐지—vid 출처=헤더 이름칸(A)
_INDEX_SHEET = "계정 목록"  # 첫 시트: 전 계정(사업자) 목록 + 하이퍼링크 점프 + 요약(계정 100개도 탐색 쉽게)
_ACCT_SHEET = "_계정정보"  # 숨김 시트: (사업자)→계정ID 매핑. 목차에 계정ID 표시용(⚠ 비밀번호는 절대 저장 안 함)
_MKT_SHEET = "_마케팅"     # 숨김 시트: (사업자,상품)→마케팅 시작·종료·모니터링종료. 계정목록 입력을 보존(재생성돼도 유지)
_DISC_SHEET = "_중단"      # 숨김 시트: (사업자,상품) 판매중지/삭제(대장에서 사라짐) 표기. 데이터는 보존, 표시만 구분
_SPECIAL_SHEETS = (_META_SHEET, _INDEX_SHEET, _ACCT_SHEET, _MKT_SHEET, _DISC_SHEET)
_MKT_COLS = ("체험단 시작일", "체험단 종료일", "모니터링 종료일")   # 계정목록 편집 열(직원 입력 = 체험단 기간)
_MKT_COLS_LEGACY0 = "마케팅 시작일"   # 옛 라벨('마케팅 시작일') — 기존 마스터 계정목록에서 값 회수 시 인식용


def _norm(v) -> str:
    return str(v).strip() if v is not None else ""


def _key(v) -> str:
    """이름칸 셀 값 → **상품 키**(순수 상품명). 표시용으로 붙은 `⟨SEP⟩<vendorItemId>` 꼬리를 떼어낸다.

    상품 정체성(시계열 키)은 항상 구분자(`config.NAME_ID_SEP`) 앞부분이다. 구분자가 없으면(순수 이름·
    키워드 셀) `_norm` 과 동일하게 동작해 기존 키를 그대로 보존한다. 상품명 내부 개행은 손대지 않는다."""
    return _norm(v).split(config.NAME_ID_SEP, 1)[0]


def _vids_from_cell(v) -> list[str]:
    """이름칸 표시값의 **'VID : a / b' 꼬리**에서 vid 목록을 파싱한다(없으면 빈 리스트).

    vid 의 유일 출처(source of truth) = 헤더 C셀 표시값(소유자 확정 (A)). `_display_name` 이 렌더한
    `"{이름}{SEP}\nVID : a / b"` 를 역파싱한다 — 구분자 뒤 → 콜론 뒤 → '/' 분리. 구분자 없으면(순수
    이름·키워드 셀) vid 없음."""
    s = _norm(v)
    if config.NAME_ID_SEP not in s:
        return []
    tail = s.split(config.NAME_ID_SEP, 1)[1]
    # 꼬리는 여러 줄일 수 있다(VID / 상품판매가 / 로켓그로스 입고일). **'VID :' 줄만** 파싱해야 vid 오염 방지
    # (헤더에 다른 줄을 추가해도 vid 출처가 안 깨짐 — 소유자 2026-09-24 헤더 확장 대비 안전화).
    vid_line = ""
    for line in tail.splitlines():
        if "VID" in line.upper() and ":" in line:
            vid_line = line.split(":", 1)[1]
            break
    if not vid_line:                      # 옛 형식(줄 구분 없이 콜론 하나) 호환
        vid_line = tail.split(":", 1)[1] if ":" in tail else tail
    return [x.strip() for x in vid_line.split("/") if x.strip()]


def _nearest_year(month: int, day: int):
    """년도 없는 '월.일' → **오늘과 가장 가까운 연도**의 date(연말/연초 경계 보정).

    1월에 만난 '12.30'을 올해 12월로 오인하면 정규화가 first~last(1월~12월) 사이 ~363칸을 만들어
    폭발한다. 오늘 기준 작년/올해/내년 중 |날짜-오늘|이 최소인 해를 고른다(2/29 등 그 해에 없는 날은 건너뜀)."""
    today = _date.today()
    best = None
    for y in (today.year - 1, today.year, today.year + 1):
        try:
            cand = _date(y, month, day)
        except ValueError:   # 그 해에 없는 날(예: 평년 2/29)
            continue
        if best is None or abs((cand - today).days) < abs((best - today).days):
            best = cand
    return best


def _parse_date(s):
    """날짜 문자열 → date(못 읽으면 None). YYYY-MM-DD·YY.MM.DD·**MM.DD(년도 없음)**·YYYY/MM/DD·MM/DD 등 허용.

    ⚠ 일자 컬럼 라벨은 2026-09-16부터 **년도 없는 '월.일'(예 09.16)** 로 적는다(사용자 요청·당분간).
    '월.일'은 **오늘과 가장 가까운 연도**로 해석한다(`_nearest_year` — 연말/연초 경계 보정)."""
    s = _norm(s)
    if not s:
        return None
    if isinstance(s, (_dt, _date)):
        return s.date() if isinstance(s, _dt) else s
    no_year = ("%m/%d", "%m-%d", "%m.%d")   # 년도 없는 표기 → 오늘과 가장 가까운 해로 보정
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%y.%m.%d", "%Y/%m/%d", "%y/%m/%d", "%m.%d", "%m/%d", "%m-%d"):
        try:
            d = _dt.strptime(s, fmt).date()
        except ValueError:
            continue
        if fmt in no_year:
            ny = _nearest_year(d.month, d.day)
            return ny if ny is not None else d
        return d
    return None


class OutputWorkbook:
    """셀독 서식 워크북(시트=사업자). 상품 블록을 시트에 세로로 쌓고 일자 컬럼을 누적한다."""

    def __init__(self, wb: openpyxl.Workbook):
        self.wb = wb
        # 인덱스(재로드 시 시트에서 복원)
        self._date_col: dict[str, dict[str, int]] = {}          # {사업자: {일자: 컬럼}}
        self._date_rows: dict[str, list[int]] = {}              # {사업자: [날짜 헤더행...]}
        self._metric_row: dict[tuple[str, str, str], int] = {}  # {(사업자,상품,지표): 행}
        self._kw_row: dict[tuple[str, str, str], int] = {}      # {(사업자,상품,키워드): 행}
        self._vid_row: dict[tuple[str, str], int] = {}          # {(사업자,상품): _상품ID 시트 행(등록명·판매상태·제목캐시)}
        self._block_vids: dict[tuple[str, str], list[str]] = {}  # {(사업자,상품): vid 목록} — 헤더 이름칸 'VID :' 꼬리에서 복원(출처=(A))
        self._reindex()

    # ── 생성/로드/저장 ────────────────────────────────────────
    @classmethod
    def empty(cls) -> "OutputWorkbook":
        wb = openpyxl.Workbook()
        wb.remove(wb.active)   # 계정 시트는 ensure_account 로 추가(빈 기본시트 제거)
        return cls(wb)

    @classmethod
    def load(cls, path: str | Path) -> "OutputWorkbook":
        return cls(openpyxl.load_workbook(path))

    def save(self, path: str | Path) -> None:
        if not self.wb.worksheets:
            return   # 아직 계정 시트 없음(빈 워크북) — 저장 불가, 첫 계정 생성 후 저장됨
        self.wb.save(path)

    # ── 인덱스 복원 ───────────────────────────────────────────
    def _reindex(self) -> None:
        self._date_col.clear(); self._date_rows.clear()
        self._metric_row.clear(); self._kw_row.clear(); self._vid_row.clear()
        self._block_vids.clear()
        # vid 출처(A안, 레이아웃 v4)=숨김 메타시트 `_상품ID` col3. 헤더 이름칸 꼬리는 옛 마스터 폴백용.
        # 메타시트가 계정시트 뒤에 올 수 있어 **먼저 한 번** 스캔해 {(사업자,상품): [vid…]} 를 만든다.
        meta_vids: dict[tuple[str, str], list[str]] = {}
        if _META_SHEET in self.wb.sheetnames:
            mws = self.wb[_META_SHEET]
            for r in range(2, mws.max_row + 1):
                b = _norm(mws.cell(r, 1).value); p = _norm(mws.cell(r, 2).value)
                raw = _norm(mws.cell(r, 3).value)
                if b and p and raw:
                    vs = [x.strip() for x in raw.split("/") if x.strip()]
                    if vs:
                        meta_vids[(b, p)] = vs
        for ws in self.wb.worksheets:
            if ws.title in (_INDEX_SHEET, _ACCT_SHEET, _MKT_SHEET, _DISC_SHEET):  # 특수시트 = 데이터 아님
                continue
            if ws.title == _META_SHEET:                 # 상품ID 매핑 시트 → 행 인덱스만 복원
                for r in range(2, ws.max_row + 1):
                    b = _norm(ws.cell(r, 1).value); p = _norm(ws.cell(r, 2).value)
                    if b and p:
                        self._vid_row[(b, p)] = r
                continue
            biz = ws.title
            self._date_col[biz] = {}
            self._date_rows[biz] = []
            cur_prod = ""
            for r in range(1, ws.max_row + 1):
                # 이름칸엔 표시용 vid 꼬리가 붙을 수 있으므로 **키(순수 상품명)** 로 복원해 읽는다.
                # (키워드 셀엔 구분자가 없어 _key == _norm — 무해.)
                raw_name = ws.cell(r, _COL_NAME).value
                name = _key(raw_name)
                metric = _norm(ws.cell(r, _COL_METRIC).value)
                if metric == _LABEL_DATE:                       # 상품 헤더행 → 새 상품
                    cur_prod = name
                    self._date_rows[biz].append(r)
                    # vid 출처=메타 col3(우선). 없으면 옛 마스터 이름칸 'VID :' 꼬리서 폴백 복원(무손실 마이그레이션).
                    vids = meta_vids.get((biz, cur_prod)) or _vids_from_cell(raw_name)
                    if vids:
                        self._block_vids[(biz, cur_prod)] = vids
                    for c in range(_FIRST_DATE, ws.max_column + 1):
                        d = _norm(ws.cell(r, c).value)
                        if d:
                            self._date_col[biz].setdefault(d, c)
                elif metric in _ALL_METRICS:                    # 상품 지표행
                    if cur_prod:
                        self._metric_row[(biz, cur_prod, metric)] = r
                elif metric == config.M_RANK:                    # 키워드 순위행 — 키워드명=A열(v4 좌측확장 앵커)
                    # 옛 마스터(v3)는 키워드가 C열에 있으므로 A 없으면 **C 폴백**으로 읽어 동결 유지
                    # (물리 이전은 apply_style 의 _migrate_keyword_col 이 수행 — 여기선 인덱스만 올바르게).
                    kwn = _key(ws.cell(r, _COL_KW).value) or _key(ws.cell(r, _COL_NAME).value)
                    if cur_prod and kwn:
                        self._kw_row[(biz, cur_prod, kwn)] = r

    # ── 재개(이어서)용 조회 ──────────────────────────────────
    def has_product(self, biz: str, product: str) -> bool:
        return any(k[0] == biz and k[1] == product for k in self._metric_row)

    def product_keywords(self, biz: str, product: str) -> list[str]:
        """이 상품에 기록된 키워드 목록(있으면 AI 선정 건너뛰고 순위만 — 키워드 동결)."""
        out: list[str] = []
        for (b, p, kw) in self._kw_row:
            if b == biz and p == product and kw not in out:
                out.append(kw)
        return out

    def clear_keyword_row(self, biz: str, product: str, keyword: str) -> bool:
        """키워드 행을 **빈 순위행으로 비운다**(담당자가 구글시트에서 지운 키워드 반영).

        키워드명 칸(A·v4 좌측확장 앵커)과 그 행의 모든 일자값(H~)을 지워 빈 순위행(구조는 유지·검색 대상 아님)으로.
        소유자 확정(2026-09-20): **이력 보존 안 함** — 지운 키워드의 과거 순위값도 함께 삭제. 대상 행 없으면 no-op."""
        biz, product = _norm(biz), _key(product)
        row = self._kw_row.get((biz, product, str(keyword)))
        if row is None:
            return False
        ws = self.wb[biz]
        ws.cell(row=row, column=_COL_KW).value = None        # 키워드명(A) 삭제 → 빈 순위행
        ws.cell(row=row, column=_COL_SEARCH).value = None    # 검색량 삭제
        for c in range(_FIRST_DATE, ws.max_column + 1):      # 과거 일자별 순위값 삭제(이력 보존 안 함)
            ws.cell(row=row, column=c).value = None
        del self._kw_row[(biz, product, str(keyword))]
        return True

    def products_of(self, biz: str) -> list[str]:
        """그 사업자 시트의 상품명 목록(블록 등장 순서). ②③ 단계가 상품을 순회하는 데 쓴다."""
        out: list[str] = []
        for (b, p, _m) in self._metric_row:
            if b == biz and p not in out:
                out.append(p)
        return out

    def latest_date(self, biz: str) -> str | None:
        """그 사업자의 가장 최근 **날짜** 일자 컬럼 라벨(③ 순위 기록 날짜). 내림차순 정렬이라 물리적으론
        맨 왼쪽(H) 칸이지만, 물리 위치가 아니라 **날짜값 기준**으로 최신을 고른다(정렬 방향 무관)."""
        cols = self._date_col.get(biz, {})
        return max(cols, key=lambda d: (_parse_date(d) or _date.min)) if cols else None

    def account_sheets(self) -> list[str]:
        """계정(사업자) 시트명 목록 — 특수 시트(상품ID·목차·계정정보)는 제외.

        ⚠ 구글시트 복원(결과시트 통째 다운로드) 시 인덱스 탭 '계정목록'(공백 없음, gsheet_index)이 섞여
        올 수 있다. 마스터 자체 인덱스는 '계정 목록'(공백)이라, **공백 무시로 인덱스명과 같은 시트는 항상
        제외**한다(통계로 오인해 미러링·계정목록 동기화 충돌[400] 하는 것 방지)."""
        idx_norm = _INDEX_SHEET.replace(" ", "")   # '계정목록' — 공백 없는 형태(구글시트 미러 인덱스 포함)
        return [s for s in self.wb.sheetnames
                if s not in _SPECIAL_SHEETS and s.replace(" ", "") != idx_norm]

    def set_account_id(self, biz: str, account_id: str) -> None:
        """(사업자)→계정ID 를 숨김 시트에 저장(목차 표시용). ⚠ 비밀번호는 저장하지 않는다."""
        aid = _norm(account_id)
        if not aid:
            return
        if _ACCT_SHEET in self.wb.sheetnames:
            ws = self.wb[_ACCT_SHEET]
        else:
            ws = self.wb.create_sheet(_ACCT_SHEET)
            ws.sheet_state = "hidden"
            ws.cell(1, 1, "사업자"); ws.cell(1, 2, "계정ID")
        for r in range(2, ws.max_row + 1):
            if _norm(ws.cell(r, 1).value) == biz:
                ws.cell(r, 2, aid); return
        row = ws.max_row + 1
        ws.cell(row, 1, biz); ws.cell(row, 2, aid)

    def account_id_of(self, biz: str) -> str:
        """저장된 계정ID(없으면 '')."""
        if _ACCT_SHEET not in self.wb.sheetnames:
            return ""
        ws = self.wb[_ACCT_SHEET]
        for r in range(2, ws.max_row + 1):
            if _norm(ws.cell(r, 1).value) == biz:
                return _norm(ws.cell(r, 2).value)
        return ""

    def set_representative(self, biz: str, representative: str) -> None:
        """(사업자)→대표자명 을 숨김 계정정보 시트 **4열**에 저장(계정목록 대표자 컬럼 표시용).

        ⚠ 3열은 이미 '판매수집일'(mark_sales_collected)이 쓰므로 4열을 쓴다(충돌 방지).
        관리대장에 대표자명 항목이 있어 입력파싱(Account.representative)으로 넘어온다. 빈값이면 기존값 보존."""
        rep = _norm(representative)
        if not rep:
            return
        if _ACCT_SHEET in self.wb.sheetnames:
            ws = self.wb[_ACCT_SHEET]
        else:
            ws = self.wb.create_sheet(_ACCT_SHEET)
            ws.sheet_state = "hidden"
            ws.cell(1, 1, "사업자"); ws.cell(1, 2, "계정ID")
        if _norm(ws.cell(1, 4).value) != "대표자":
            ws.cell(1, 4, "대표자")
        for r in range(2, ws.max_row + 1):
            if _norm(ws.cell(r, 1).value) == biz:
                ws.cell(r, 4, rep); return
        row = ws.max_row + 1
        ws.cell(row, 1, biz); ws.cell(row, 4, rep)

    def representative_of(self, biz: str) -> str:
        """저장된 대표자명(없으면 '' — 옛 마스터엔 없을 수 있음). 계정정보 시트 4열(3열=판매수집일과 구분)."""
        if _ACCT_SHEET not in self.wb.sheetnames:
            return ""
        ws = self.wb[_ACCT_SHEET]
        for r in range(2, ws.max_row + 1):
            if _norm(ws.cell(r, 1).value) == biz:
                return _norm(ws.cell(r, 4).value)
        return ""

    def mark_sales_collected(self, biz: str, date_label: str) -> None:
        """이 계정의 '판매수집 완료(오늘=date_label 컬럼)' 스탬프를 숨김 계정정보 시트 3열에 기록.

        판매지표는 0/공란도 정상(판매데이터 없음)이라 값으로 '수집됨'을 판정할 수 없으므로, **명시적 스탬프**로
        기록한다. 같은 날 재실행이 이 스탬프를 보고 그 계정의 로그인·수집을 생략한다(진행파일이 지워져도 마스터에
        영속). date_label 은 워크북 일자 컬럼 라벨(yy.mm.dd 또는 from~to)과 동일 문자열."""
        label = _norm(date_label)
        if not label:
            return
        if _ACCT_SHEET in self.wb.sheetnames:
            ws = self.wb[_ACCT_SHEET]
        else:
            ws = self.wb.create_sheet(_ACCT_SHEET)
            ws.sheet_state = "hidden"
            ws.cell(1, 1, "사업자"); ws.cell(1, 2, "계정ID")
        if _norm(ws.cell(1, 3).value) != "판매수집일":
            ws.cell(1, 3, "판매수집일")
        for r in range(2, ws.max_row + 1):
            if _norm(ws.cell(r, 1).value) == biz:
                ws.cell(r, 3, label); return
        row = ws.max_row + 1
        ws.cell(row, 1, biz); ws.cell(row, 3, label)

    def sales_collected_on(self, biz: str) -> str:
        """그 계정에 마지막으로 기록된 판매수집일 라벨(없으면 '')."""
        if _ACCT_SHEET not in self.wb.sheetnames:
            return ""
        ws = self.wb[_ACCT_SHEET]
        if _norm(ws.cell(1, 3).value) != "판매수집일":
            return ""
        for r in range(2, ws.max_row + 1):
            if _norm(ws.cell(r, 1).value) == biz:
                return _norm(ws.cell(r, 3).value)
        return ""

    def has_sales(self, biz: str, date_label: str) -> bool:
        """그 계정의 판매수집이 date_label(오늘 컬럼) 기준으로 이미 완료됐는가(재실행 스킵 근거).

        다른 날 라벨이면 False(자동으로 그날 새로 수집) → 날짜가 바뀌면 스탬프가 달라 재수집된다."""
        return bool(_norm(date_label)) and self.sales_collected_on(biz) == _norm(date_label)

    def is_rank_filled(self, biz: str, product: str, keyword: str, date_iso: str) -> bool:
        row = self._kw_row.get((biz, product, keyword))
        col = self._date_col.get(biz, {}).get(date_iso)
        if row is None or col is None:
            return False
        # '-'(구 미측정/스캔밖 placeholder)는 미채움으로 봐 ③ 재실행이 다시 측정하게 한다
        # (새 규칙에선 스캔밖=50위로 기록하므로 '-'는 측정 안 된 잔재).
        return self.wb[biz].cell(row=row, column=col).value not in (None, "", "-")

    def clear_sales_stamps(self) -> int:
        """모든 계정의 '판매수집 완료' 스탬프(`_계정정보` 3열)를 해제 → '오늘 처음(다시)' 재수집 시
        오늘 이미 완료한 계정도 다시 수집(has_sales 가 False 가 됨). 해제한 계정 수 반환."""
        if _ACCT_SHEET not in self.wb.sheetnames:
            return 0
        ws = self.wb[_ACCT_SHEET]
        n = 0
        for r in range(2, ws.max_row + 1):
            if _norm(ws.cell(r, 3).value):
                ws.cell(r, 3).value = None
                n += 1
        return n

    def reset_date_column(self, date_label: str) -> int:
        """그 날짜 컬럼(`date_label`=일자 라벨 예 '26.09.14')의 **지표·순위 값만** 공란화 — 날짜 라벨·다른
        날짜·상품명/키워드는 불변. 컬럼이 아직 없으면 no-op(**새 컬럼 만들지 않음**). '오늘 처음(다시)'에서
        오늘 컬럼을 초기화해 전 계정·상품을 처음부터 다시 채우게 한다(어제까지 유지). ⚠ `date_label`은
        `ensure_date`가 쓰는 라벨과 동일 문자열이어야 매칭됨(ISO 아님)."""
        cleared = 0
        for rowmap in (self._metric_row, self._kw_row):
            for key, row in list(rowmap.items()):
                col = self._date_col.get(key[0], {}).get(date_label)
                if col is None:
                    continue
                cell = self.wb[key[0]].cell(row=row, column=col)
                if cell.value not in (None, ""):
                    cell.value = None
                    cleared += 1
        return cleared

    # ── 생성 ─────────────────────────────────────────────────
    def ensure_account(self, biz: str):
        if biz in self.wb.sheetnames:
            return self.wb[biz]
        ws = self.wb.create_sheet(title=biz[:31])   # 엑셀 시트명 31자 제한
        ws.cell(1, 1, config.SELDOC_SHEET_TITLE)
        self._date_col[biz] = {}
        self._date_rows[biz] = []
        return ws

    def _update_kind_label(self, biz: str, product: str, kind: str) -> None:
        """기존 블록의 **판매방식(구분)** 최신화 — 레이아웃 v4에서 구분은 A열이 아니라 **메타 col11**에 저장하고
        `_style_metric_rows`가 헤더 '판매방식' 줄(pos3 C:F)에 렌더한다. 구분 변경(로켓그로스→둘 다)·문구
        마이그레이션 반영. 재고행 유무 등 구조는 그대로(기존 로켓그로스/둘 다는 이미 재고행 보유)."""
        self.set_product_kind(biz, product, kind)

    def _render_block_name(self, biz: str, product: str) -> None:
        """블록 헤더 C셀을 표시값(순수명 + 'VID :' 꼬리)으로 **즉시 렌더**(멱등).

        vid 출처(A)가 헤더 C셀이므로, set_product_vids 가 apply_style(맨 끝 1회)을 기다리지 않고 즉시
        렌더해야 상품별 중간저장·재개·②③ 로드에서 vid 가 유실되지 않는다. 헤더행은 _date_rows 로 찾는다."""
        if biz not in self.wb.sheetnames:
            return
        ws = self.wb[biz]
        for r in self._date_rows.get(biz, []):
            if _key(ws.cell(r, _COL_NAME).value) == product:
                ws.cell(r, _COL_NAME, self._display_name(biz, product))
                return

    def _add_metric_row(self, biz: str, product: str, metric: str) -> None:
        """기존 블록에 빠진 지표행(예: 재고현황)을 상품 **지표행 맨 아래**(키워드 소헤더 위)에 끼워 넣는다.

        구분이 개인→로켓그로스/둘다로 바뀌었는데 재고행이 없던 블록을 보정한다. insert_rows 는 병합셀이
        있으면 데이터를 손상시키므로 삽입 전 병합을 모두 해제(호출부가 이후 apply_style 로 재병합)하고,
        삽입 후 전체 재인덱스로 아래 행·블록 위치를 정확히 반영한다. 멱등(이미 있으면 호출부 가드로 미진입)."""
        if biz not in self.wb.sheetnames:
            return
        metric_rows = [self._metric_row[(biz, product, m)] for m in _ALL_METRICS
                       if (biz, product, m) in self._metric_row]
        if not metric_rows:
            return
        ws = self.wb[biz]
        _unmerge_all(ws)                       # insert_rows 전 병합 해제(데이터 손상 방지)
        at = max(metric_rows) + 1              # 마지막 지표행 다음(키워드 소헤더 직전)
        ws.insert_rows(at, amount=1)
        ws.cell(at, _COL_METRIC, metric)
        self._reindex()                        # 행 이동 반영 전체 재인덱스

    def ensure_product_block(self, biz: str, product: str, kind: str, keywords: list[str],
                             *, rank_rows: bool = True, registered: str | None = None) -> None:
        """상품 블록이 없으면 생성(로켓그로스·둘다=CONTRACT_METRICS[재고 포함]/판매자배송=PERSONAL_METRICS +
        키워드 순위행). 이미 있으면 **구분 라벨만 최신화**(문구 마이그레이션·구분 변경 반영).

        - rank_rows=False: **키워드 소헤더·순위행을 생략**(판매지표행만). 다중옵션 상품의 2번째 이후 옵션
          블록용 — 순위는 리스팅 단위라 옵션 공통이므로 대표 옵션 블록만 순위행을 갖는다(소유자 확정).
        - registered: 등록상품명(대장 원본명) 기준값. 다중옵션 2차 블록은 이름이 '등록명 (라벨)' 이지만
          등록상품명은 **라벨 없는 기준명**을 보존해야 대장 매칭이 유지된다(기본=product)."""
        if self.has_product(biz, product):
            self._update_kind_label(biz, product, kind)
            # 구분이 개인→로켓그로스/둘다로 바뀐 블록이 **재고현황 행 없이** 남아 재고가 기록될 자리가
            # 없던 문제 보정: 로켓그로스 파트가 있는데 재고행이 없으면 지표행 맨 아래에 끼워 넣는다
            # (이게 관리대장 '그로스 재고' 역기록이 일부 상품에서 공란이던 근본 원인, 2026-09-17).
            if (kind in config.KINDS_WITH_INVENTORY
                    and (biz, product, config.M_INVENTORY) not in self._metric_row):
                self._add_metric_row(biz, product, config.M_INVENTORY)
            # 판매가·판매상태 지표행(실행일마다 기록, 소유자 2026-09-24) — 옛 마스터 블록엔 없어 자동 추가
            # (모든 구분 공통·개인상품 포함). 멱등(이미 있으면 미진입). 판매가=재고현황 아래, 판매상태=그 아래.
            if (biz, product, config.M_SALE_PRICE) not in self._metric_row:
                self._add_metric_row(biz, product, config.M_SALE_PRICE)
            if (biz, product, config.M_SALE_STATUS) not in self._metric_row:
                self._add_metric_row(biz, product, config.M_SALE_STATUS)
            return
        ws = self.ensure_account(biz)
        metrics = (config.CONTRACT_METRICS if kind in config.KINDS_WITH_INVENTORY
                   else config.PERSONAL_METRICS)
        r = (ws.max_row + 2) if ws.max_row > 1 else 3      # 블록 사이 빈 줄
        # 상품 헤더행(pos0): C=상품명(블록 KEY), G=날짜, H~=기존 일자 라벨.
        # 판매방식(구분)은 레이아웃 v4에서 A열이 아니라 **메타 col11**에 저장(헤더 pos3 렌더). A열 kind 쓰기 폐지.
        self.set_product_kind(biz, product, kind)
        ws.cell(r, _COL_NAME, product)
        ws.cell(r, _COL_METRIC, _LABEL_DATE)
        for d, c in self._date_col.get(biz, {}).items():
            ws.cell(r, c, d)
        self._date_rows.setdefault(biz, []).append(r)
        # 상품 지표행
        for m in metrics:
            r += 1
            ws.cell(r, _COL_METRIC, m)
            self._metric_row[(biz, product, m)] = r
        if rank_rows:            # 다중옵션 2차 블록(rank_rows=False)은 키워드·순위행 없음(판매지표만)
            # 키워드 소헤더 — 키워드명은 A열(v4 좌측확장 A~E 앵커). 사업자명(A) 표기 폐지.
            r += 1
            ws.cell(r, _COL_KW, _LABEL_KEYWORD)
            ws.cell(r, _COL_SEARCH, _LABEL_SEARCH)
            ws.cell(r, _COL_METRIC, _LABEL_NOTE)
            # 키워드 순위행
            kws = list(dict.fromkeys(keywords))
            for kw in kws:
                r += 1
                ws.cell(r, _COL_KW, kw)
                ws.cell(r, _COL_METRIC, config.M_RANK)
                self._kw_row[(biz, product, kw)] = r
            # 키워드가 KW_TRACK_N(=4) 미만이면 **빈 순위행**으로 채워 블록의 키워드행 구조를 항상 유지한다
            # (키워드 없어도 4행 유지·공란 OK — 사용자 요구 2026-09-15). 이름 공란 + M_RANK 인 빈 행은
            # _kw_row 에 안 잡혀 '키워드 없음'으로 판정되므로, ② 키워드선정이 그 상품을 선정하고
            # add_product_keywords 가 새 행을 만들기 전에 이 빈 행부터 채운다(블록 팽창 방지).
            for _ in range(config.KW_TRACK_N - len(kws)):
                r += 1
                ws.cell(r, _COL_METRIC, config.M_RANK)   # 이름 공란 + M_RANK = 빈 키워드 순위행
        # 생성 시점의 이름 = 등록상품명(이후 노출명으로 바뀌어도 보존). 다중옵션 2차 블록은 라벨 없는 기준명 저장.
        self.set_registered_name(biz, product, registered or product)

    def _kw_block_rows(self, biz: str, product: str) -> list[tuple[int, str]]:
        """이 상품 블록의 **모든 키워드 순위행**(M_RANK 라벨) → [(행번호, 이름), …] 오름차순.

        이름이 빈 항목 = ensure_product_block 이 4행 유지용으로 채운 **빈 순위행**.
        블록 범위 = 이 상품의 마지막 지표행 다음 ~ 다음 블록 헤더 직전(없으면 시트 끝).
        """
        ws = self.wb[biz]
        metric_rows = [self._metric_row[(biz, product, m)] for m in _ALL_METRICS
                       if (biz, product, m) in self._metric_row]
        if not metric_rows:
            return []
        start = max(metric_rows) + 1
        headers = sorted(r for r in self._date_rows.get(biz, []) if r > start)
        end = (headers[0] - 1) if headers else ws.max_row
        rows: list[tuple[int, str]] = []
        for r in range(start, end + 1):
            if _norm(ws.cell(r, _COL_METRIC).value) == config.M_RANK:
                rows.append((r, _key(ws.cell(r, _COL_KW).value)))   # 키워드명=A열(v4)
        return rows

    def has_keyword_section(self, biz: str, product: str) -> bool:
        """이 블록에 **키워드 소헤더**('키워드' 행)가 있는가(대표·단일옵션=True, **다중옵션 2차 블록=False**).

        2차 옵션 블록은 판매정보만이라 키워드 소헤더·순위행이 없다(rank_rows=False). ② 키워드선정·
        pad_keyword_rows 가 2차 블록을 건너뛰는 판정에 쓴다(잘못된 키워드 삽입·행 팽창 방지). 소헤더 유무로
        보므로 순위행이 0개인 옛 블록(소헤더는 있음)은 True(정상적으로 채워짐)와 구분된다."""
        if biz not in self.wb.sheetnames:
            return False
        ws = self.wb[biz]
        metric_rows = [self._metric_row[(biz, product, m)] for m in _ALL_METRICS
                       if (biz, product, m) in self._metric_row]
        if not metric_rows:
            return False
        start = max(metric_rows) + 1
        headers = sorted(r for r in self._date_rows.get(biz, []) if r > start)
        end = (headers[0] - 1) if headers else ws.max_row
        for r in range(start, end + 1):
            if (_key(ws.cell(r, _COL_KW).value) == _LABEL_KEYWORD   # 소헤더 '키워드'=A열(v4)
                    and _norm(ws.cell(r, _COL_METRIC).value) == _LABEL_NOTE):
                return True
        return False

    def add_product_keywords(self, biz: str, product: str, keywords: list[str]) -> list[str]:
        """상품 블록에 새 키워드 추가. **빈 순위행부터 채우고**, 모자라면 새 행 삽입. 반환: 실제 추가분.

        ensure_product_block 이 4행 유지용으로 만든 빈 순위행(이름 공란)을 먼저 재사용해 블록이
        4행을 넘겨 팽창하는 것을 막는다. 빈 행보다 키워드가 많으면 마지막 순위행 아래에 insert_rows 로
        끼워 넣는다. 없던 키워드만 추가.
        """
        # 띄어쓰기·대소문자는 **유의미**(2026-09-17 정책 되돌림): 쿠팡에서 '캠핑타프'와 '캠핑 타프'의
        # 노출순위가 달라 별개 키워드로 추적한다 → **완전 동일한 표기(strip 후 문자열 일치)만** 중복 제거.
        # 그래야 직원이 결과 시트에 넣은 띄어쓰기 변형도 무시되지 않고 그대로 추가·추적된다.
        def _sp(s) -> str:
            return str(s).strip()
        seen = {_sp(e) for e in self.product_keywords(biz, product)}
        add = []
        for kw in dict.fromkeys(keywords):
            if not kw or _sp(kw) in seen:
                continue
            seen.add(_sp(kw))
            add.append(kw)
        if not add:
            return []
        ws = self.wb[biz]
        # ⚠ insert_rows 는 병합셀이 있으면 데이터(상품명·키워드)를 손상시킨다 → 삽입 전 병합 전부 해제
        # (호출부가 이후 apply_style 로 표준 재병합). 이게 run1 계정 이름/키워드 유실의 근본 원인이었음.
        _unmerge_all(ws)
        block = self._kw_block_rows(biz, product)          # (행, 이름) — 이름 빈 것 = 빈 순위행
        blanks = [r for r, name in block if not name]
        i = 0
        for row in blanks:                                 # ① 빈 순위행부터 채움(행 삽입 없음)
            if i >= len(add):
                break
            ws.cell(row, _COL_KW, add[i])                  # 키워드명=A열(v4)
            ws.cell(row, _COL_METRIC, config.M_RANK)
            i += 1
        remaining = add[i:]
        if remaining:                                      # ② 빈 행보다 많으면 마지막 순위행 아래 삽입
            last_kw_row = max((r for r, _ in block), default=None)
            if last_kw_row is None:                        # 순위행이 아예 없던 옛 블록 → 소헤더행(지표행+1) 아래
                last_kw_row = max(self._metric_row[(biz, product, m)] for m in _ALL_METRICS
                                  if (biz, product, m) in self._metric_row) + 1
            ws.insert_rows(last_kw_row + 1, amount=len(remaining))
            for j, kw in enumerate(remaining, 1):
                ws.cell(last_kw_row + j, _COL_KW, kw)      # 키워드명=A열(v4)
                ws.cell(last_kw_row + j, _COL_METRIC, config.M_RANK)
        self._reindex()   # 행 채움·이동 반영 전체 재인덱스(정확성 우선)
        return add

    def pad_keyword_rows(self, biz: str, product: str, min_rows: int | None = None) -> int:
        """이 상품의 키워드 순위행이 `min_rows`(기본 KW_TRACK_N=4) 미만이면 **빈 순위행**으로 채운다.

        키워드 없어도(또는 4개 미만이어도) 블록 키워드행을 항상 4행 유지(공란 OK — 사용자 요구 2026-09-15).
        ② 키워드선정으로도 키워드가 안 나온 상품(브랜드명뿐이라 앵커 추출 실패 등)·옛 0행 블록에 쓴다.
        추가한 빈 행 수 반환(0이면 변경 없음).
        """
        min_rows = config.KW_TRACK_N if min_rows is None else min_rows
        if not self.has_keyword_section(biz, product):   # 다중옵션 2차 블록(판매정보만) → 순위행 없음, 건너뜀
            return 0
        block = self._kw_block_rows(biz, product)
        need = min_rows - len(block)
        if need <= 0:
            return 0
        ws = self.wb[biz]
        _unmerge_all(ws)   # insert_rows 전 병합 해제(데이터 손상 방지, 이후 apply_style 재병합)
        last_kw_row = max((r for r, _ in block), default=None)
        if last_kw_row is None:                            # 순위행이 아예 없던 옛 블록 → 소헤더행(지표행+1) 아래
            last_kw_row = max(self._metric_row[(biz, product, m)] for m in _ALL_METRICS
                              if (biz, product, m) in self._metric_row) + 1
        ws.insert_rows(last_kw_row + 1, amount=need)
        for j in range(1, need + 1):
            ws.cell(last_kw_row + j, _COL_METRIC, config.M_RANK)   # 이름 공란 + M_RANK = 빈 키워드 순위행
        self._reindex()
        return need

    # ── 일자 컬럼 ────────────────────────────────────────────
    def _append_date_col(self, biz: str, date_iso: str) -> int:
        """일자 라벨 하나를 그 사업자 시트의 맨 오른쪽에 새 컬럼으로 추가(헤더행 전부에 라벨 기록).
        ⚠물리적으론 오른쪽 끝에 붙지만, 저장 시 normalize_date_columns 가 **최신=맨 왼쪽(H)** 내림차순으로
        재정렬한다(값은 날짜로 매칭 이식). 즉 최종 파일은 항상 최신 날짜가 H열."""
        cols = self._date_col.setdefault(biz, {})
        col = max(cols.values(), default=_FIRST_DATE - 1) + 1
        cols[date_iso] = col
        ws = self.wb[biz]
        for r in self._date_rows.get(biz, []):    # 모든 날짜 헤더행에 라벨 기록(블록마다 헤더 반복)
            ws.cell(r, col, date_iso)
        return col

    def ensure_date(self, biz: str, date_iso: str) -> int:
        """일자 컬럼 확보. 새 컬럼이 **직전 최신일보다 하루 넘게 뒤**면 그 사이 **빠진 달력일을 빈 컬럼으로**
        먼저 채운 뒤(실행 안 한 날도 날짜만 있고 값은 공란) 요청 일자 컬럼을 만든다 — 시계열이 일자별로
        끊기지 않게 한다(§'미실행 날짜=날짜 표기+공란'). 단일일(yy.mm.dd) 라벨에만 적용, 범위 라벨은 그대로 추가."""
        cols = self._date_col.setdefault(biz, {})
        if date_iso in cols:
            return cols[date_iso]
        new_d = _parse_date(date_iso)
        if new_d is not None:
            prior = [d for d in (_parse_date(k) for k in cols) if d is not None]
            latest = max(prior) if prior else None
            if latest is not None and new_d > latest:   # 앞으로 진행 → 그 사이 빠진 날 빈 컬럼으로 채움
                gap = latest + _td(days=1)
                while gap < new_d:
                    lbl = gap.strftime("%m.%d")   # 빠진 날 빈 컬럼 = 년도 없는 '월.일'
                    if lbl not in cols:
                        self._append_date_col(biz, lbl)
                    gap += _td(days=1)
        return self._append_date_col(biz, date_iso)

    def normalize_date_columns(self, log=None) -> dict[str, list[str]]:
        """모든 계정 시트의 일자 컬럼을 **시트별 첫 날~마지막 날 사이 모든 달력일**로 채우고 **날짜순 정렬**하며,
        라벨을 **년도 없는 '월.일'(예 09.16)** 로 통일한다(사용자 요청·당분간).

        - 실행 안 하거나 중단돼 빠진 날(예: 09.11)이 있으면 그 날짜 컬럼을 만들되 값은 **공란**으로 둔다.
        - 신규 계정은 그 시트가 실제로 추적한 첫 날 이전으로 소급하지 않는다(시트별 min~max 내부 공백만).
        - 물리 컬럼을 재배치 없이 안전하게 재구성(값을 (행,**날짜**)로 스냅샷 → H열부터 정렬 순서로 재기록).
          라벨을 재포맷해도 값은 날짜로 매칭돼 유실·이동 없음. A~G(상품명·키워드·지표)는 손대지 않는다.
        - 파싱 불가 라벨(범위 등)이 있는 시트는 **건드리지 않고 건너뛴다**(안전).
        반환: {사업자: [새로 삽입된 날짜 라벨...]} — 소급 정리 요약. 정렬·재라벨만 바뀌고 삽입이 없어도 재구성한다.
        서식은 이 함수가 손대지 않으므로 호출부가 이후 apply_style() 로 표준 서식을 재적용해야 한다.
        """
        _log = log or (lambda m: None)
        added: dict[str, list[str]] = {}
        for biz, cols in list(self._date_col.items()):
            if biz not in self.wb.sheetnames or not cols:
                continue
            res = self._normalize_sheet_dates(biz, cols, _log)
            if res is not None:   # None=파싱불가로 건너뜀(added 미기록) · []=멱등 · [라벨]=재구성
                added[biz] = res
        return added

    def _normalize_sheet_dates(self, biz: str, cols: dict, log) -> list[str] | None:
        """한 시트의 일자 컬럼을 첫날~마지막날 연속·'월.일' 정렬로 재구성(값은 날짜로 매칭 이식).

        반환: None=파싱 불가 라벨 있어 건너뜀 · []=이미 정렬·연속(멱등, 변경 없음) · [라벨…]=새로 채운 날짜."""
        parsed = {lbl: _parse_date(lbl) for lbl in cols}
        if any(d is None for d in parsed.values()):
            log(f"  [날짜정렬] {biz}: 파싱 불가 라벨 있음 → 건너뜀 {sorted(cols)}")
            return None
        # 날짜→기존 열 **전부**(같은 날이 옛/신 라벨 2컬럼으로 공존 가능). 라벨을 '월.일'로 재포맷하므로
        # 값은 **날짜**로 스냅샷해 매칭한다. 컬럼은 오름차순(기록 순 — 뒤가 최신)으로 모은다.
        date2cols: dict = {}
        for lbl, dd in sorted(parsed.items(), key=lambda kv: kv[1]):
            date2cols.setdefault(dd, []).append(cols[lbl])
        days = sorted(date2cols)
        first, last = days[0], days[-1]
        target_days: list = []          # 첫날~마지막날 연속(먼저 오름차순으로 빠짐없이 모음)
        d = first
        while d <= last:
            target_days.append(d)
            d += _td(days=1)
        target_days.reverse()           # **내림차순**: 최신(last)이 맨 앞 → H열(맨 왼쪽)에 기록(소유자 2026-09-23)
        target = [dd.strftime("%m.%d") for dd in target_days]   # 년도 없는 '월.일'·내림차순 라벨
        old_labels_desc = [lbl for lbl, _dd in sorted(parsed.items(), key=lambda kv: kv[1], reverse=True)]
        old_cols_desc = [cols[lbl] for lbl in old_labels_desc]
        # 이미 '월.일' 연속·**내림차순**이고 물리 순서도 H부터(최신) 오름차순이면 변경 없음(멱등)
        if target == old_labels_desc \
           and old_cols_desc == list(range(_FIRST_DATE, _FIRST_DATE + len(old_cols_desc))):
            return []
        self._rebuild_date_grid(biz, date2cols, target_days, set(cols.values()))
        old_days = set(days)
        return [dd.strftime("%m.%d") for dd in target_days if dd not in old_days]

    def _rebuild_date_grid(self, biz: str, date2cols: dict, target_days: list, used_cols: set) -> None:
        """일자 컬럼 물리 재기록 — 기존 값을 (행,날짜)로 스냅샷 → 일자 영역 비움 → 첫날~마지막날 연속·
        정렬 순서로 H열부터 재기록(헤더=라벨, 값=날짜 매칭 이식·없으면 공란). _date_col[biz] 갱신.

        같은 날짜가 두 컬럼(옛/신 라벨)으로 있으면 **가장 최근(높은 컬럼) 비어있지 않은 값**을 보존한다
        (첫 컬럼만 보던 옛 로직은 오늘 새로 쓴 둘째 컬럼 값을 유실했음)."""
        ws = self.wb[biz]
        max_row = ws.max_row
        # 스냅샷: 같은 날짜의 여러 컬럼 중 오름차순으로 훑어 마지막(최신) 비어있지 않은 값을 (행,날짜)로 보존
        snap: dict[tuple[int, object], object] = {}
        for r in range(1, max_row + 1):
            for dd, cs in date2cols.items():
                for c in sorted(cs):
                    v = ws.cell(r, c).value
                    if v not in (None, ""):
                        snap[(r, dd)] = v
        header_rows = set(self._date_rows.get(biz, []))
        # 기존 일자 영역 전부 비움(A~G= _FIRST_DATE 미만은 불변)
        for r in range(1, max_row + 1):
            for c in used_cols:
                ws.cell(r, c).value = None
        # 정렬·연속 순서로 재기록(라벨=월.일)
        new_map: dict[str, int] = {}
        for i, dd in enumerate(target_days):
            col = _FIRST_DATE + i
            lbl = dd.strftime("%m.%d")
            new_map[lbl] = col
            for r in range(1, max_row + 1):
                if r in header_rows:
                    ws.cell(r, col).value = lbl          # 헤더행 = 날짜 라벨(빠진 날도 표기)
                elif (r, dd) in snap:
                    ws.cell(r, col).value = snap[(r, dd)]  # 기존 값 이식(없으면 공란)
        self._date_col[biz] = new_map

    # ── 값 기록 ──────────────────────────────────────────────
    def set_product_metric(self, biz: str, product: str, metric: str, date_iso: str, value) -> bool:
        row = self._metric_row.get((biz, product, metric))
        if row is None:
            return False
        self.wb[biz].cell(row=row, column=self.ensure_date(biz, date_iso), value=value)
        return True

    def _meta_ws(self):
        """상품ID 숨김 시트(없으면 생성)."""
        if _META_SHEET in self.wb.sheetnames:
            return self.wb[_META_SHEET]
        ws = self.wb.create_sheet(title=_META_SHEET)
        ws.sheet_state = "hidden"
        ws.cell(1, 1, "사업자"); ws.cell(1, 2, "상품명"); ws.cell(1, 3, "상품ID(vid)")   # vid 목록('/' 조인) — 레이아웃 v4서 vid 출처(A안, 헤더 이름칸 꼬리→여기로 이전)
        ws.cell(1, 4, "키워드서명"); ws.cell(1, 5, "권고제목")   # ⑤ 제목 캐시(동결 상품 AI 재호출 생략)
        ws.cell(1, 6, "등록상품명")   # 대장 원본명(노출명으로 바뀌어도 불변) — 계정목록 안정키·3c 마케팅 매칭 기준
        ws.cell(1, 7, "판매상태(쿠팡)")   # 쿠팡 재고 판매상태(판매중/부분판매중/판매중지) — 대장 판매중지와 대조해 경고 표시
        ws.cell(1, 8, "상품판매가(미사용)")   # 판매가는 '판매가' 지표행으로 이관(2026-09-24)
        ws.cell(1, 9, "로켓그로스판매일")   # saleStartedAt(판매일 근사) — 헤더 표시용, 판매자배송은 공란
        ws.cell(1, 10, "최근입고요약")   # 관리대장 입고 요약(요청/작업/박스/파레트/완료/출고) — 헤더 로켓그로스 묶음
        ws.cell(1, 11, "판매방식")   # 구분(로켓그로스/판매자배송/둘다) — 레이아웃 v4 헤더 '판매방식' 줄 표시용(표시 전용·인덱스 아님)
        return ws

    def set_product_extra(self, biz: str, product: str, sale_price=None, inbound_date=None,
                          inbound_summary=None) -> None:
        """헤더 표시용 로켓그로스 부가정보를 숨김시트에 저장(소유자 2026-09-24).

        inbound_date=로켓그로스 판매일(판매시작일 근사, 9열)·inbound_summary=관리대장 최근입고 요약(10열).
        **로켓그로스/둘다만** 넘어옴(판매자배송 None→공란). 값 None이면 그 칸 미접촉(기존 보존). 판매가(sale_price)는
        '판매가' 지표행으로 이관해 8열은 미사용(호환 위해 인자만 유지). _display_name 이 9·10열을 읽어 헤더 렌더."""
        biz, product = _norm(biz), _key(product)
        if not (biz and product):
            return
        ws = self._meta_ws()
        row = self._vid_row.get((biz, product))
        if row is None:
            row = ws.max_row + 1
            ws.cell(row, 1, biz); ws.cell(row, 2, product)
            self._vid_row[(biz, product)] = row
        if inbound_date:
            ws.cell(row, 9, str(inbound_date))
        if inbound_summary:
            ws.cell(row, 10, str(inbound_summary))

    def _product_extra(self, biz: str, product: str) -> tuple:
        """(상품판매가[미사용], 로켓그로스판매일, 최근입고요약) — 헤더 렌더용. 없으면 (None, '', '')."""
        row = self._vid_row.get((_norm(biz), _key(product)))
        if row is None or _META_SHEET not in self.wb.sheetnames:
            return None, "", ""
        ws = self.wb[_META_SHEET]
        return ws.cell(row, 8).value, _norm(ws.cell(row, 9).value), _norm(ws.cell(row, 10).value)

    def set_product_kind(self, biz: str, product: str, kind: str) -> None:
        """상품 **판매방식(구분)**을 숨김 메타시트 11열에 저장(레이아웃 v4 헤더 '판매방식' 줄 표시용).

        런타임에 파이프라인이 매번 넘기는 표시 전용 값 — 인덱스가 아니라 헤더 렌더에만 쓴다(kind A열 쓰기 대체).
        빈값이면 no-op(기존 보존 — 로그인 못한 실행이 지우지 않게)."""
        biz, product, kind = _norm(biz), _key(product), _norm(kind)
        if not (biz and product and kind):
            return
        ws = self._meta_ws()
        row = self._vid_row.get((biz, product))
        if row is None:
            row = ws.max_row + 1
            ws.cell(row, 1, biz); ws.cell(row, 2, product)
            self._vid_row[(biz, product)] = row
        ws.cell(row, 11, kind)

    def product_kind(self, biz: str, product: str) -> str:
        """저장된 판매방식(없으면 '' — 옛 마스터·미로그인). 레이아웃 v4 헤더 '판매방식' 줄 값."""
        row = self._vid_row.get((_norm(biz), _key(product)))
        if row is None or _META_SHEET not in self.wb.sheetnames:
            return ""
        return _norm(self.wb[_META_SHEET].cell(row, 11).value)

    def set_product_vids(self, biz: str, product: str, vids) -> None:
        """상품의 고유ID(vendorItemId) 목록을 저장(③ 순위조회의 상품 매칭용).

        vid 출처(A안, 레이아웃 v4)=숨김 메타시트 `_상품ID` col3. 인메모리 인덱스(_block_vids)를 갱신하고
        메타 col3에 '/' 조인 저장해 영속한다(옛 마스터 폴백=헤더 이름칸 꼬리는 _reindex 가 처리). 헤더 C셀도
        즉시 렌더(현행 _display_name 의 'VID :' 꼬리 — 레이아웃 v4 렌더 전까지 표시 병행). 빈 목록이면 no-op."""
        vids = [str(v) for v in dict.fromkeys(vids) if v]
        if not vids:
            return
        biz, product = _norm(biz), _key(product)
        self._block_vids[(biz, product)] = vids
        ws = self._meta_ws()                    # 메타 col3 영속(vid 출처 = 여기)
        row = self._vid_row.get((biz, product))
        if row is None:
            row = ws.max_row + 1
            ws.cell(row, 1, biz); ws.cell(row, 2, product)
            self._vid_row[(biz, product)] = row
        ws.cell(row, 3, " / ".join(vids))
        self._render_block_name(biz, product)   # 헤더 C셀 렌더(중간저장/재개/②③ 유실 방지)

    def product_vids(self, biz: str, product: str) -> list[str]:
        """저장된 상품 고유ID 목록(없으면 빈 리스트). 출처=헤더 이름칸(_reindex 가 복원한 _block_vids)."""
        return list(self._block_vids.get((_norm(biz), _key(product)), []))

    def sibling_vids(self, biz: str, product: str) -> list[str]:
        """이 블록과 **같은 등록상품명(리스팅)** 을 공유하는 모든 옵션 블록의 vid **합집합**.

        다중옵션 상품은 옵션(vid)마다 블록이 갈리지만, 검색 노출순위는 **리스팅 단위**(옵션 공통)라 검색결과의
        아이템위너가 어느 옵션이든 잡아야 순위를 놓치지 않는다. ③ 순위조회는 대표 블록에만 순위를 달지만
        매칭은 이 합집합으로 한다(정확 순위 매일 = 최우선 요구). 단일옵션은 자기 vid 만 반환."""
        biz = _norm(biz)
        reg = self.registered_name(biz, product) or _key(product)
        out: list[str] = []
        for (b, p), vids in self._block_vids.items():
            if b != biz:
                continue
            if (self.registered_name(b, p) or p) != reg:
                continue
            for v in vids:
                if v not in out:
                    out.append(v)
        return out

    def set_registered_name(self, biz: str, product: str, name: str | None = None) -> None:
        """상품 블록의 **등록상품명**(대장 원본명)을 숨김시트에 최초 1회 보존(노출명으로 바뀌어도 불변).

        계정목록(구글시트) 안정키 `marketing_key(계정ID+등록상품명)`·3c 마케팅 역머지 매칭의 기준(§7).
        이미 값이 있으면 덮지 않는다(이름 변경·재호출에도 최초 등록명 유지). name 을 주면 그 값을 저장하고
        (다중옵션 2차 블록=라벨 없는 기준명), 없으면 블록명(product)을 저장한다."""
        biz, product = _norm(biz), _key(product)
        if not (biz and product):
            return
        name = _key(name) if name else product
        ws = self._meta_ws()
        row = self._vid_row.get((biz, product))
        if row is None:
            row = ws.max_row + 1
            ws.cell(row, 1, biz); ws.cell(row, 2, product)
            self._vid_row[(biz, product)] = row
        if not _norm(ws.cell(row, 6).value):
            ws.cell(row, 6, name)

    def registered_name(self, biz: str, product: str) -> str:
        """저장된 등록상품명(없으면 '' — 옛 마스터엔 없을 수 있음, 호출부가 노출명으로 폴백)."""
        row = self._vid_row.get((biz, product))
        if row is None or _META_SHEET not in self.wb.sheetnames:
            return ""
        return _norm(self.wb[_META_SHEET].cell(row, 6).value)

    def set_sale_status(self, biz: str, product: str, status: str) -> None:
        """상품의 **쿠팡 실제 판매상태**(판매중/부분판매중/판매중지)를 숨김시트 7열에 저장.

        status 가 빈값이면(미상) 저장하지 않는다(옛 값 유지 — 로그인 못한 실행이 기존 상태를 지우지 않게)."""
        biz, product = _norm(biz), _key(product)
        status = _norm(status)
        if not (biz and product and status):
            return
        ws = self._meta_ws()
        row = self._vid_row.get((biz, product))
        if row is None:
            row = ws.max_row + 1
            ws.cell(row, 1, biz); ws.cell(row, 2, product)
            self._vid_row[(biz, product)] = row
        ws.cell(row, 7, status)

    def sale_status(self, biz: str, product: str) -> str:
        """저장된 쿠팡 판매상태(없으면 '' — 미상). 개인상품·미로그인 실행 등은 미상."""
        row = self._vid_row.get((_norm(biz), _key(product)))
        if row is None or _META_SHEET not in self.wb.sheetnames:
            return ""
        return _norm(self.wb[_META_SHEET].cell(row, 7).value)

    def sale_active(self, biz: str, product: str) -> bool:
        """쿠팡에서 **판매 가능 상태**(판매중 또는 부분판매중)면 True. 판매중지·미상은 False."""
        return self.sale_status(biz, product) in ("판매중", "부분판매중")

    def rank_suppressed(self, biz: str, product: str) -> bool:
        """③ 노출순위 조회 대상이 **아닌** 상품 — 대장 취소선(판매중지)이거나 쿠팡 상태가 판매중이 아님.

        소유자 요구(2026-09-22): 쿠팡에서 **판매중/부분판매중** 인 상품만 순위검색(판매중지·임시저장·승인반려는
        검색 안 함 → 차단 예산 절약·정확). **미상('')은 억제하지 않는다**(판매자배송·미로그인 등 legit 상품
        누락 방지 — 확정 미판매만 제외). 대장에서 빠진 상품(is_discontinued)도 순위 제외."""
        return (self.is_discontinued(biz, product)
                or self.sale_status(biz, product) in _NOT_SELLING_STATUSES)

    def apply_sale_status(self, biz: str, status_by_vid: dict) -> int:
        """쿠팡 판매상태맵을 그 사업자 **마스터 전체 상품(블록)** 에 vid로 대조해 저장.

        status_by_vid 값 = **bool**(True=판매중지·RFM 재고 API `isSaleSuspended`) 또는 **문자열**('판매중'/
        '부분판매중'/'판매중지'·상품조회/수정 `productStatus`, 판매자배송 포함 전 상품). bool 은 문자열로
        정규화한다(True→판매중지·False→판매중). 상품 정체성은 vendorItemId 앵커라, 대장에서 빠져 '판매중지'
        표기된 상품도 쿠팡에 살아있으면 그 vid 로 잡혀 실제 판매상태가 채워진다(대장↔쿠팡 불일치 경고 근거).
        블록의 옵션(vid) 중 상태맵에 있는 것들만 보고: **모두 같은 상태면 그대로**(판매중/부분판매중/판매중지/
        임시저장/승인반려 — 소유자 요구 2026-09-22: 임시저장·승인반려도 정확히 표기)·**섞이면 부분판매중**·
        하나도 없음=미상(생략). 옵션 분리 후엔 블록당 vid 1개라 보통 단일 상태다. 반환=상태를 채운 상품 수."""
        if not status_by_vid:
            return 0

        def _st(v) -> str:
            if isinstance(v, bool):
                return "판매중지" if v else "판매중"
            return _norm(v)

        biz = _norm(biz)
        n = 0
        for p in self.products_of(biz):
            known = [_st(status_by_vid[v]) for v in self.product_vids(biz, p) if v in status_by_vid]
            known = [s for s in known if s]   # 빈값(미상) 제외
            if not known:                     # 이 상품 옵션이 상태맵에 없음 → 미상(기존 값 보존)
                continue
            uniq = set(known)
            st = next(iter(uniq)) if len(uniq) == 1 else "부분판매중"   # 단일=그대로·섞임=부분판매중
            self.set_sale_status(biz, p, st)
            n += 1
        return n

    def product_inventory(self, biz: str, product: str):
        """이 상품의 **최신 일자 재고현황**(로켓그로스). 재고행 없거나(개인상품)·값 없으면 None. 관리대장 역기록용."""
        date = self.latest_date(biz)
        row = self._metric_row.get((biz, product, config.M_INVENTORY))
        col = self._date_col.get(biz, {}).get(date) if date else None
        if row is None or col is None:
            return None
        v = self.wb[biz].cell(row, col).value
        # 관리대장 '그로스 재고' 역기록은 **숫자 재고만** — '미입고'(문자열)·공란은 대상 아님(대장값 보존).
        return v if isinstance(v, (int, float)) else None

    def inventory_by_biz(self) -> dict:
        """{사업자norm: [(상품명, 재고), …]} — 재고 있는 상품만. 관리대장 역기록 **유사도 매칭**용.

        상품명 = 등록상품명(있으면·대장 원본명) 우선, 없으면 현재(노출)명. 대장 상품명과 노출명이 달라도
        (예: 대장 '…30포' vs 노출 '…') 호출부가 사업자 안에서 유사도로 최적 매칭한다."""
        out: dict = {}
        for biz in self.account_sheets():
            items = []
            for p in self.products_of(biz):
                inv = self.product_inventory(biz, p)
                if inv is None:
                    continue
                items.append((self.registered_name(biz, p) or p, inv))
            if items:
                out[_norm(biz)] = items
        return out

    def inventory_by_registered_name(self) -> dict:
        """{(사업자norm, 등록상품명key): 최신 재고} — 관리대장 '그로스 재고' 역기록 매칭용.

        정체성은 vendorItemId 앵커라 ③이 노출명으로 바꿔도, **등록상품명(대장 원본명)** 으로 되돌려
        대장의 상품명(AA)과 매칭한다(등록명 없으면 현재 블록명으로 폴백). 재고 있는 상품만 포함."""
        out: dict = {}
        for biz in self.account_sheets():
            for p in self.products_of(biz):
                inv = self.product_inventory(biz, p)
                if inv is None:
                    continue
                reg = self.registered_name(biz, p) or p
                out[(_norm(biz), _norm(reg))] = inv
        return out

    def _display_name(self, biz: str, name: str) -> str:
        """헤더 C셀(pos0) 표시값 = **순수 상품명만**(레이아웃 v4·소유자 확정 2026-09-24).

        v4에서 VID/판매방식/로켓그로스 판매일·최근입고는 좌측 라벨 칸(A:B)+값(C:F)의 **별도 줄**로 이동했다
        (`_style_metric_rows`가 pos2~6에 렌더). vid 저장은 숨김 메타시트 `_상품ID` col3(A안). 따라서 이 함수는
        상품명(블록 KEY)만 반환한다 — C(hr)=상품명이라 `_key`/reindex 매칭 불변. (biz 인자는 시그니처 호환 유지.)"""
        return name

    def resolve_block_name(self, biz: str, vids) -> str | None:
        """이 사업자에서 주어진 vid(옵션ID)와 교집합이 있는 **기존 상품 블록의 이름**을 반환(없으면 None).

        상품 정체성을 vendorItemId 에 앵커한다 — ①판매수집이 매일 넘기는 이름(복원명)이 달라도, ③이
        검색결과 정확명으로 바꿔둔 블록을 vid 로 찾아 재사용하기 위함(중복 블록 생성·시계열 단절 방지).
        """
        want = {str(v) for v in vids if v}
        if not want:
            return None
        biz = _norm(biz)
        for (b, p), pv in list(self._block_vids.items()):
            if b == biz and want & set(pv):
                return p
        return None

    def set_display_name(self, biz: str, product: str, new_name: str) -> bool:
        """상품 블록의 표시명(계약상품명)을 검색결과의 **정확한 노출명**으로 교체(시계열 키 안전 이동).

        헤더행 C셀 값만 바꾸고(행 삽입/삭제·병합 변경 없음 → 서식 손상 없음), 인메모리 키
        (_metric_row/_kw_row/_vid_row)와 숨김시트 상품명을 (biz, product)→(biz, new_name)로 원자적 이동.
        같은 이름·빈값·헤더 못 찾음·이름 충돌(다른 블록이 이미 그 이름)일 땐 no-op(데이터 보존).
        """
        new_name = _norm(new_name)
        if not new_name or new_name == product or biz not in self.wb.sheetnames:
            return False
        ws = self.wb[biz]
        header = next((r for r in self._date_rows.get(biz, [])
                       if _key(ws.cell(r, _COL_NAME).value) == product), None)
        if header is None:
            return False
        if any(k[0] == biz and k[1] == new_name for k in self._metric_row):
            return False   # 새 이름이 이미 다른 상품 블록 → 병합 방지, 갱신 생략
        self._metric_row = _rekey_block(self._metric_row, biz, product, new_name)
        self._kw_row = _rekey_block(self._kw_row, biz, product, new_name)
        # vid 인덱스도 키 이동(출처=헤더 C셀이므로, 이동 후 표시값에 'VID :' 꼬리를 다시 붙여 렌더)
        self._block_vids = _rekey_block(self._block_vids, biz, product, new_name)
        ws.cell(header, _COL_NAME, self._display_name(biz, new_name))
        row = self._vid_row.pop((biz, product), None)
        if row is not None:
            if _META_SHEET in self.wb.sheetnames:
                self.wb[_META_SHEET].cell(row, 2, new_name)
            self._vid_row[(biz, new_name)] = row
        return True

    def title_cache(self, biz: str, product: str) -> tuple[str, str]:
        """(키워드서명, 권고제목) — 없으면 ('', ''). 서명이 현재 키워드와 같으면 AI 재호출 없이 재사용(⑤)."""
        row = self._vid_row.get((biz, product))
        if row is None or _META_SHEET not in self.wb.sheetnames:
            return "", ""
        ws = self.wb[_META_SHEET]
        return _norm(ws.cell(row, 4).value), _norm(ws.cell(row, 5).value)

    def set_title_cache(self, biz: str, product: str, sig: str, title: str) -> None:
        """권고제목을 키워드서명과 함께 숨김 시트에 캐시(동결 상품은 매일 재생성하지 않도록)."""
        ws = self._meta_ws()
        row = self._vid_row.get((biz, product))
        if row is None:
            row = ws.max_row + 1
            ws.cell(row, 1, biz); ws.cell(row, 2, product)
            self._vid_row[(biz, product)] = row
        ws.cell(row, 4, sig); ws.cell(row, 5, title)

    def set_keyword_search(self, biz: str, product: str, keyword: str, volume) -> bool:
        row = self._kw_row.get((biz, product, keyword))
        if row is None:
            return False
        self.wb[biz].cell(row=row, column=_COL_SEARCH, value=volume)
        return True

    def keyword_search(self, biz: str, product: str, keyword: str):
        """저장된 키워드 월검색량(F열) — 없으면 None(미측정). 동결 키워드 중 **검색량 공란**을
        네이버로 채울지 판정하는 데 쓴다(직원이 결과 시트에 직접 넣은 키워드는 검색량이 공란)."""
        row = self._kw_row.get((biz, product, keyword))
        if row is None:
            return None
        return self.wb[biz].cell(row=row, column=_COL_SEARCH).value

    def set_keyword_rank(self, biz: str, product: str, keyword: str, date_iso: str,
                         rank: int | None, scanned: int | None = None) -> bool:
        row = self._kw_row.get((biz, product, keyword))
        if row is None:
            return False
        # 찾았으면 그 순위, 못 찾았으면 **그 페이지에서 실제로 센 개수 '위밖'**(예 '44위밖'·'59위밖' —
        # 소유자 2026-09-23). scanned 미지정이면 스캔 상한으로 폴백('50위밖'). ⚠차단/미측정은 여기 안 옴
        # (그건 공란=재측정, _semi_on_miss 가 처리). 미발견=측정 완료라 재검색 안 하게 '위밖'으로 채운다.
        val = f"{rank}위" if rank else f"{scanned if scanned is not None else config.RANK_SCAN_MAX}위밖"
        self.wb[biz].cell(row=row, column=self.ensure_date(biz, date_iso), value=val)
        return True

    # ── 서식(셀독 서식 파일 재현: 병합·팔레트·테두리) ────────────
    # 사용자 `셀독 판매 데이터_서식.xlsx`(한컴 셀) 시각 서식을 재현한다. 행 스캔 방식이라
    # 계정(시트)·상품(블록)이 늘어도 자동 적용된다.
    _FN = "맑은 고딕"
    _FILL_PROD = "FBE2D5"     # 상품명·라벨칸(살구) — 상품군 교대색 A(진한 톤)
    _FILL_PROD2 = "E2EFDA"    # 상품명·라벨칸(민트) — 상품군 교대색 B(같은 등록상품명=한 군, 인접 군을 시각 구분)
    _FILL_PROD_LT = "FDF1EA"  # 값칸·키워드 옅은 살구 — 상품군 전체를 은은히 통일(소유자 2026-09-25)
    _FILL_PROD2_LT = "F0F6EB"  # 값칸·키워드 옅은 민트
    _FILL_LABEL = "D9E9FA"    # G열 지표 라벨/순위(연파랑)
    _FILL_KWHEAD = "E8E8E8"   # 키워드 소헤더행(회색)
    _FILL_KIND = "FFFFFF"     # 구분(계약/개인)·사업자명(흰)
    _FILL_MKT = "FCE4D6"      # 마케팅 기간 일자 컬럼 배경(연주황 — 캠페인 구간 구분)

    def _migrate_vids_to_meta(self) -> None:
        """옛 마스터(vid=헤더 이름칸 꼬리)의 vid 를 숨김 메타 col3 에 영속(레이아웃 v4 렌더 전 유실 방지).

        v4에서 `_display_name`이 상품명만 반환하므로, 아직 메타 col3 에 없는 인메모리 vid(이름칸 꼬리에서
        복원된 것)를 렌더 전에 col3 로 옮긴다. 이미 col3 값이 있으면 미접촉(멱등). set_product_vids/pipeline
        경로는 이미 col3 를 쓰므로 이 마이그레이션은 load+style+save(무 파이프라인, 예: normalize_dates)만 커버."""
        if not self._block_vids:
            return
        ws = self._meta_ws()
        for (biz, prod), vids in self._block_vids.items():
            row = self._vid_row.get((biz, prod))
            if row is None:
                row = ws.max_row + 1
                ws.cell(row, 1, biz); ws.cell(row, 2, prod)
                self._vid_row[(biz, prod)] = row
            if not _norm(ws.cell(row, 3).value):
                ws.cell(row, 3, " / ".join(vids))

    def _migrate_keyword_col(self) -> None:
        """옛 마스터(v3) 키워드 C→A 이전 + **손상된 키워드 소헤더 자가복원**(레이아웃 v4·유실 방지·재발 방지).

        (a) v3는 키워드명·소헤더 '키워드'를 C열(_COL_NAME)에, 사업자명을 A열에 뒀다. v4는 키워드명을 A열
            (병합 앵커)에서 읽으므로 옛 마스터를 그대로 저장하면 A:E 병합의 비앵커 C값이 버려져 키워드·순위가
            유실된다 → 저장 전 C→A 로 옮긴다.
        (b) **자가복원(2026-09-25 유실 사고 재발 방지):** 키워드행(M_RANK)은 있는데 소헤더의 A='키워드'가
            사라진 블록(마이그레이션 누락 빌드가 저장한 손상 마스터)은 `_find_kw_head`가 키워드 구역을 못 찾아
            v4 서식이 키워드행을 지표행으로 오인·뭉갠다 → 소헤더행(첫 M_RANK 직전, F='검색량' 또는 G∈비고류로
            검증)의 A를 '키워드'로 되살린다.
        멱등(이미 A열/소헤더 정상이면 no-op). 변경 시 재인덱스. 저장 때마다 돌아 손상 마스터를 자동 치유한다."""
        sub_g = {_LABEL_NOTE, "⛔ 판매중지", "🔴 체험단중"}
        moved = False
        for ws in self.wb.worksheets:
            if ws.title in _SPECIAL_SHEETS:
                continue
            targets: list[tuple[int, str]] = []   # (행, A에 쓸 값)
            # (a) 옛 포맷 키워드행/소헤더 C→A (병합 셀도 앵커값은 읽힘)
            for r in range(1, ws.max_row + 1):
                g = _norm(ws.cell(r, _COL_METRIC).value)
                c = _norm(ws.cell(r, _COL_NAME).value)
                a = _norm(ws.cell(r, _COL_KW).value)
                if c == _LABEL_KEYWORD and a != _LABEL_KEYWORD:
                    targets.append((r, _LABEL_KEYWORD))           # 옛 소헤더: C='키워드'·A=사업자
                elif g == config.M_RANK and c and not a:
                    targets.append((r, c))                        # 옛 키워드행: C=키워드명·A 공란
            # (b) 손상된 소헤더 자가복원 — 블록별 첫 M_RANK 직전 소헤더에 A='키워드' 없으면 복원
            headers = [r for r in range(1, ws.max_row + 1)
                       if _norm(ws.cell(r, _COL_METRIC).value) == _LABEL_DATE]
            for hi, hr in enumerate(headers):
                end = (headers[hi + 1] - 1) if hi + 1 < len(headers) else ws.max_row
                first_kw = next((r for r in range(hr, end + 1)
                                 if _norm(ws.cell(r, _COL_METRIC).value) == config.M_RANK), None)
                if not first_kw or first_kw <= hr:
                    continue
                sh = first_kw - 1
                is_sub = (_norm(ws.cell(sh, _COL_SEARCH).value) == _LABEL_SEARCH
                          or _norm(ws.cell(sh, _COL_METRIC).value) in sub_g)
                if is_sub and _norm(ws.cell(sh, _COL_KW).value) != _LABEL_KEYWORD:
                    targets.append((sh, _LABEL_KEYWORD))          # 소헤더 마커 복원
            if not targets:
                continue
            _unmerge_all(ws)                                       # 병합 해제 후 쓰기(apply_style 재병합)
            for r, val in targets:
                ws.cell(r, _COL_KW, val)                          # A ← 키워드명/'키워드'
                if val == _LABEL_KEYWORD and not _norm(ws.cell(r, _COL_SEARCH).value):
                    ws.cell(r, _COL_SEARCH, _LABEL_SEARCH)        # 소헤더 '검색량' 제목 복원(F열 공란 방지)
                if val != _LABEL_KEYWORD or _norm(ws.cell(r, _COL_NAME).value) == _LABEL_KEYWORD:
                    ws.cell(r, _COL_NAME).value = None            # 옛 C값(키워드명/'키워드') 비움(v4는 A가 앵커)
            moved = True
        if moved:
            self._reindex()

    def _group_sibling_blocks(self) -> None:
        """같은 등록상품명(기본+옵션) 블록을 **인접**하게 정렬(분산 치유·소유자 2026-09-25).

        옵션이 나중 실행에서 뒤늦게 발견되면 블록이 시트 끝에 붙어 형제(같은 등록상품명)와 떨어져 분산된다
        (그룹 배경색·경계선이 한 블록으로 안 묶임). 저장(apply_style)마다 형제끼리 붙여 정렬해 치유한다.
        이미 인접이면 no-op(흔한 경우). 재정렬한 시트가 있으면 1회 재인덱스."""
        changed = False
        for ws in self.wb.worksheets:
            if ws.title in _SPECIAL_SHEETS:
                continue
            if self._regroup_sheet_blocks(ws):
                changed = True
        if changed:
            self._reindex()

    def _regroup_sheet_blocks(self, ws) -> bool:
        """한 시트의 상품 블록을 등록상품명 **첫 등장 순서로 그룹핑**해 형제끼리 인접하게 재배치(값만 이동).

        행 insert 없이 블록 값을 스냅샷 → 비우기 → 새 순서로 재기록한다(병합은 apply_style 이 뒤에서 재생성,
        서식도 재계산되므로 값만 옮기면 안전). 이미 형제끼리 인접(desired==현재)이면 no-op. 재배치했으면 True."""
        headers = sorted(self._date_rows.get(ws.title, []))
        if len(headers) < 2:
            return False
        regs = [self.registered_name(ws.title, _key(ws.cell(h, _COL_NAME).value))
                or _key(ws.cell(h, _COL_NAME).value) for h in headers]
        first_idx: dict[str, int] = {}
        for i, rg in enumerate(regs):
            first_idx.setdefault(rg, i)
        desired = sorted(range(len(headers)), key=lambda i: (first_idx[regs[i]], i))
        if desired == list(range(len(headers))):
            return False   # 이미 형제끼리 인접(흔한 경우)
        maxc = ws.max_column
        last_data = max((r for r in range(1, ws.max_row + 1)
                         if any(ws.cell(r, c).value not in (None, "") for c in range(1, maxc + 1))),
                        default=headers[0])
        snaps = []                                   # 블록별 값 스냅샷(꼬리 빈 행 제거)
        for i, h in enumerate(headers):
            stop = headers[i + 1] if i + 1 < len(headers) else last_data + 1
            rows = list(range(h, stop))
            while len(rows) > 1 and all(_norm(ws.cell(rows[-1], c).value) == "" for c in range(1, maxc + 1)):
                rows.pop()
            snaps.append([[ws.cell(r, c).value for c in range(1, maxc + 1)] for r in rows])
        _unmerge_all(ws)                             # 값 이동 전 병합 해제(쓰기 안전, apply_style 재병합)
        for r in range(headers[0], last_data + 1):   # 블록 영역 비우기
            for c in range(1, maxc + 1):
                ws.cell(r, c).value = None
        w = headers[0]                               # 새 순서로 재기록(블록 사이 빈 줄 1)
        for oi in desired:
            for rowvals in snaps[oi]:
                for c, v in enumerate(rowvals, 1):
                    if v is not None:
                        ws.cell(w, c, v)
                w += 1
            w += 1
        return True

    def _v4_layout(self, hr: int, m_end: int) -> dict:
        """레이아웃 v4 헤더 라벨/값 칸 배치(소유자 확정 2026-09-24). 우측 지표 N줄과 정렬되도록 좌측
        A:B(라벨)·C:F(값)를 pos별로 매핑한다. 로켓그로스(재고 포함, 7줄)만 판매일/입고 3줄, 판매자배송(6줄)은 생략.

        반환: {rows, ab:[(앵커행, 세로칸수, 라벨)], cf:[(앵커행, 세로칸수, 값키)]}.
        A:B 라벨=상품명2·VID1·판매방식1·로켓그로스3, C:F 값=상품명2 + pos2~6 단일(판매일/요청·출고/수량)."""
        rows = list(range(hr, m_end + 1))
        n = len(rows)
        ab: list[tuple[int, int, str]] = []
        cf: list[tuple[int, int, str]] = []
        name_span = 2 if n >= 2 else 1
        ab.append((rows[0], name_span, "상품명")); cf.append((rows[0], name_span, "name"))
        covered = name_span
        if n >= 3:
            ab.append((rows[2], 1, "VID")); cf.append((rows[2], 1, "vid")); covered = 3
        if n >= 4:
            ab.append((rows[3], 1, "판매방식")); cf.append((rows[3], 1, "kind")); covered = 4
        if n >= 7:   # 로켓그로스(재고 포함) — A:B 3행 세로병합·C:F 3 단일값
            ab.append((rows[4], 3, "로켓그로스"))
            cf.append((rows[4], 1, "sale_date"))
            cf.append((rows[5], 1, "req_ship"))
            cf.append((rows[6], 1, "qty"))
            covered = 7
        for r in rows[covered:]:   # 남은 행(판매자배송 pos4~ 공란, 잉여) = 빈 라벨/값 단일행
            ab.append((r, 1, "")); cf.append((r, 1, ""))
        return {"rows": rows, "ab": ab, "cf": cf}

    def _v4_values(self, biz: str, nm: str, ws, hr: int) -> dict:
        """레이아웃 v4 헤더 값(C:F) — 상품명·VID·판매방식·로켓그로스 판매일/요청·출고/수량. 데이터는 메타시트에서.

        판매방식(kind)이 메타 col11 에 없으면(옛 마스터) 헤더 A열의 옛 구분 라벨을 회수해 메타에 1회 영속(마이그레이션)."""
        vids = self.product_vids(biz, nm)
        kind = self.product_kind(biz, nm)
        if not kind:   # 옛 마스터: A열의 옛 구분 라벨(알려진 kind만) 회수 → 메타 영속(A열 덮어쓰기 전에)
            old = _norm(ws.cell(hr, _COL_KIND).value)
            if old in (config.KIND_CONTRACT, config.KIND_PERSONAL, config.KIND_BOTH):
                kind = old
                self.set_product_kind(biz, nm, kind)
        _price, inbound, summary = self._product_extra(biz, nm)
        lines = summary.split("\n") if summary else []
        return {
            "name": nm,
            "vid": " / ".join(vids),
            "kind": kind,
            "sale_date": (f"쿠팡 등록 로켓그로스 판매일 : {inbound}" if inbound else ""),
            "req_ship": (lines[0] if len(lines) >= 1 else ""),
            "qty": (lines[1] if len(lines) >= 2 else ""),
        }

    def apply_style(self) -> None:
        # 서식 재적용 전에 일자 컬럼을 **시트별 첫날~마지막날 연속·날짜순**으로 정규화(빠진 날=날짜만 표기·값 공란).
        # 멱등·값 보존이라 결과파일 저장 때마다 시계열이 일자별로 끊기지 않게 유지된다(§'미실행 날짜=공란').
        self.normalize_date_columns()
        self._migrate_vids_to_meta()   # 옛 마스터 vid(이름칸 꼬리) → 메타 col3(v4 name-only 렌더 전 유실 방지)
        self._migrate_keyword_col()    # 옛 마스터 키워드·소헤더 C열 → A열(v4 좌측확장·유실 방지)
        self._group_sibling_blocks()   # 같은 등록상품명(기본+옵션) 블록 인접 정렬(분산 치유)
        thin = Side(style="thin", color="BFBFBF")
        sty = _StyleCtx(
            font=Font(name=self._FN, size=11),
            bold=Font(name=self._FN, size=11, bold=True),
            title_font=Font(name=self._FN, size=14, bold=True),
            f_prod=PatternFill("solid", fgColor=self._FILL_PROD),
            f_prod2=PatternFill("solid", fgColor=self._FILL_PROD2),
            f_prod_lt=PatternFill("solid", fgColor=self._FILL_PROD_LT),
            f_prod2_lt=PatternFill("solid", fgColor=self._FILL_PROD2_LT),
            f_label=PatternFill("solid", fgColor=self._FILL_LABEL),
            f_kwhead=PatternFill("solid", fgColor=self._FILL_KWHEAD),
            f_kind=PatternFill("solid", fgColor=self._FILL_KIND),
            mkt_fill=PatternFill("solid", fgColor=self._FILL_MKT),   # 마케팅 기간 일자 컬럼 배경
            box=Border(left=thin, right=thin, top=thin, bottom=thin),
            center=Alignment(horizontal="center", vertical="center"),
            wrap=Alignment(horizontal="center", vertical="center", wrap_text=True),
            thick=Side(style="thick"),
            thin=thin,
            mid=Side(style="medium", color="808080"),   # 기본↔옵션 구분선(진한 회색·medium)
        )
        for ws in self.wb.worksheets:
            if ws.title in _SPECIAL_SHEETS:              # 숨김 매핑·목차·계정정보 시트는 블록 서식 대상 아님
                continue
            self._style_sheet(ws, sty)
        self._build_index()   # 전 계정 요약·점프 링크의 '목차' 시트를 맨 앞에 재생성(멱등)

    def _style_sheet(self, ws, sty: _StyleCtx) -> None:
        """한 계정(사업자) 시트 서식 — 병합 초기화·꼬리행 정리·제목/틀고정/열너비 + 블록별 서식."""
        # 멱등화: 기존 병합을 모두 해제한 뒤 아래에서 표준대로 다시 병합한다.
        # (②/③/반영 등이 서식 없이 셀을 추가해 병합·테두리가 시트마다 섞이는 것을 원천 제거 →
        #  apply_style 을 몇 번 돌려도 항상 '첫 시트 표준' 하나로 고정됨.)
        _unmerge_all(ws)
        # 꼬리 공백행 제거(멱등): 값이 있는 마지막 행 아래를 모두 삭제해 max_row 를 실제 데이터에 맞춘다.
        # 구 버그(마지막 블록 하단선을 end+1 빈 행에 그리던 시절)가 남긴 '스타일만 있는 빈 행'이 통계
        # 이어쓰기로 시트마다 누적돼(상품 1·2·5개 무관 5행씩) 마지막 상품 아래 공백으로 보였다. →
        # 아래에서 마지막 블록 하단선을 end(=이제 실제 마지막 데이터행)에 그리면 공백 없이 딱 닫힌다.
        mc0 = ws.max_column
        last_data = max((r for r in range(1, ws.max_row + 1)
                         if any(ws.cell(r, c).value not in (None, "") for c in range(1, mc0 + 1))),
                        default=1)
        if ws.max_row > last_data:
            ws.delete_rows(last_data + 1, ws.max_row - last_data)
        maxc = ws.max_column
        t = ws.cell(1, 1)
        # 제목에 계정명(계정ID, 없으면 사업자명) 표기 — 어느 시트인지 한눈에(소유자 2026-09-25)
        _aid = self.account_id_of(ws.title) or ws.title
        t.value = f"{config.SELDOC_SHEET_TITLE}(계정명 : {_aid})"
        t.font = sty.title_font
        t.alignment = sty.center
        t.border = Border(bottom=Side(style="medium"))
        _sty_merge(ws, 1, 1, 1, _COL_SEARCH - 1)       # 제목 A~E (F·G 는 목차 복귀 링크 자리)
        # ◀ 목차 복귀 링크(F1:G1) — 1행+A~G열은 틀고정이라 **어느 시트·어디로 스크롤해도 항상 보임**.
        # 탭이 많아 목차 탭이 탭바에서 밀려 안 보일 때, 여기 클릭 한 번으로 목차로 돌아간다(사용자 요청).
        back = ws.cell(1, _COL_SEARCH, "👈 계정목록으로 이동")   # 손가락(뒤로) + 명확한 문구(링크 대상=_INDEX_SHEET)
        back.hyperlink = Hyperlink(ref=back.coordinate, location=f"'{_INDEX_SHEET}'!A1")
        back.font = Font(name=self._FN, size=12, bold=True, color="FF0000")  # 빨간색 진하게(눈에 띄게)
        back.alignment = Alignment(horizontal="center", vertical="center")
        back.fill = PatternFill("solid", fgColor="FFF2CC")   # 옅은 노랑 강조 배경
        back.border = Border(bottom=Side(style="medium"))
        _sty_merge(ws, 1, _COL_SEARCH, 1, _COL_METRIC)  # F1:G1
        ws.row_dimensions[1].height = 21          # 제목행 높이(샘플 서식 고정값)
        ws.freeze_panes = "H2"                     # A~G열·1행 고정, H~ 일자만 스크롤
        # 표준 열너비(레이아웃 v4): 좌측 라벨 칸 A:B 합(7+7=14) = 우측 지표 라벨 칸 G(14) 동일(소유자 #3).
        # C:F(값 칸)는 상품명·VID·로켓그로스 요약이 들어가 넓게 재배분(C18 D16 E16 F13.75).
        for c, w in {1: 7, 2: 7, 3: 18, 4: 16, 5: 16, 6: 13.75, 7: 14}.items():
            ws.column_dimensions[get_column_letter(c)].width = w
        for c in range(_FIRST_DATE, maxc + 1):
            ws.column_dimensions[get_column_letter(c)].width = 11
        headers = sorted(self._date_rows.get(ws.title, []))
        # fix ④: 같은 등록상품명(변형/옵션) 블록을 한 그룹으로 묶어 그룹 바깥만 굵은 선. 옵션 블록은
        # 생성 순서상 시트에서 인접하므로 **연속된 같은 등록명 = 한 그룹**으로 본다.
        regs = []
        for hr in headers:
            _rnm = _key(ws.cell(hr, _COL_NAME).value)
            regs.append(self.registered_name(ws.title, _rnm) or _rnm)
        # 상품군(등록상품명) 교대 배경색: 같은 등록명 변형/옵션 = 한 군(연속) → 인접 상품군을 두 색으로
        # 교대해 시각적으로 구분(소유자 2026-09-23). 그룹 경계 판정은 _style_block_edges 와 동일(regs 연속).
        g = 0
        for i, hr in enumerate(headers):
            if i > 0 and regs[i] != regs[i - 1]:
                g += 1
            prod_fill = sty.f_prod if g % 2 == 0 else sty.f_prod2
            self._style_block(ws, sty, i, hr, headers, regs, maxc, prod_fill)

    def _style_block(self, ws, sty: _StyleCtx, i: int, hr: int, headers, regs, maxc: int,
                     prod_fill: PatternFill) -> None:
        """상품 블록 1개 서식 — 이름 렌더·마케팅 배경·지표/키워드 색·판매중지 불일치 경고·그룹 경계·병합.
        prod_fill = 이 블록의 상품군 배경색(같은 등록상품명끼리 같은 색, 인접 군은 교대)."""
        end = (headers[i + 1] - 2) if i + 1 < len(headers) else ws.max_row
        # 이름칸 렌더링(멱등): 헤더 C = 1줄 상품제목 + (보이지 않는 구분자) + 2줄 vendorItemId.
        # 키는 항상 구분자 앞부분이므로 _key 로 순수명 복원 후 vid 를 다시 붙여 표준화한다.
        nm = _key(ws.cell(hr, _COL_NAME).value)
        if nm:
            ws.cell(hr, _COL_NAME).value = self._display_name(ws.title, nm)
        # 마케팅: 이 상품의 기간·상태 + 마케팅기간(시작~종료)에 해당하는 일자 컬럼 집합(배경색용)
        mstart, mend, _mmon = self.marketing_of(ws.title, nm)
        is_mkt = self._mkt_status(mstart, mend, _mmon) == "체험단중"
        is_disc = self.is_discontinued(ws.title, nm)   # 대장에서 사라짐 = 판매중지 표기
        mcols = self._mkt_cols(ws, mstart, mend)
        promo_cols = self._promo_cols(ws, mstart)   # 체험단 시작일~+1개월 → 노출순위 배경색(소유자 2026-09-24)
        kh = self._find_kw_head(ws, hr, end)   # 키워드 소헤더행(C='키워드')·없으면 None(2차 옵션 블록)
        m_end = (kh - 1) if kh else end
        # 이 상품군의 옅은 톤(값칸·키워드 배경) — 상품군 전체를 은은히 통일(소유자 2026-09-25)
        prod_fill_lt = sty.f_prod_lt if prod_fill is sty.f_prod else sty.f_prod2_lt
        self._style_metric_rows(ws, sty, hr, m_end, mcols, maxc, prod_fill, prod_fill_lt)
        if kh:
            self._style_keyword_rows(ws, sty, kh, end, promo_cols, maxc, is_disc, is_mkt, prod_fill_lt)
            self._flag_sale_mismatch(ws, sty, kh, nm, is_disc)
        self._style_block_edges(ws, sty, i, hr, end, m_end, kh, headers, regs, maxc)

    def _mkt_cols(self, ws, mstart, mend) -> set[int]:
        """마케팅 기간(시작~종료)에 해당하는 일자 컬럼번호 집합(배경색용). 시작 없으면 빈 집합."""
        mcols: set[int] = set()
        _s, _e = _parse_date(mstart), _parse_date(mend)
        if _s:
            for _lbl, _cc in self._date_col.get(ws.title, {}).items():
                _d = _parse_date(_lbl)
                if _d and _d >= _s and (not _e or _d <= _e):
                    mcols.add(_cc)
        return mcols

    def _promo_cols(self, ws, mstart) -> set[int]:
        """체험단 **시작일부터 1개월** 에 해당하는 일자 컬럼번호 집합 — 노출순위 행 배경색용(소유자 2026-09-24).

        마케팅 종료일(mend)과 무관하게 '시작일 + 1개월'(같은 날, 월말 보정) 창으로 계산한다. 시작 없으면 빈 집합."""
        s = _parse_date(mstart)
        if not s:
            return set()
        y, mo = (s.year + 1, 1) if s.month == 12 else (s.year, s.month + 1)
        import calendar
        e = _date(y, mo, min(s.day, calendar.monthrange(y, mo)[1]))   # 시작일 +1개월(월말 보정)
        out: set[int] = set()
        for _lbl, _cc in self._date_col.get(ws.title, {}).items():
            _d = _parse_date(_lbl)
            if _d and s <= _d <= e:
                out.add(_cc)
        return out

    def _find_kw_head(self, ws, hr: int, end: int):
        """블록(hr~end) 안 키워드 소헤더행(A='키워드'·v4 좌측확장). 없으면 None(2차 옵션 블록=판매정보만)."""
        for r in range(hr, end + 1):
            if _norm(ws.cell(r, _COL_KW).value) == _LABEL_KEYWORD:
                return r
        return None

    def _style_metric_rows(self, ws, sty: _StyleCtx, hr: int, m_end: int, mcols: set, maxc: int,
                           prod_fill: PatternFill, prod_fill_lt: PatternFill) -> None:
        """상품 헤더블록(레이아웃 v4·소유자 확정 2026-09-24): 좌측 A:B=라벨 칸(상품군색·굵게)·C:F=값 칸(흰) /
        우측 G=지표 라벨(연파랑)·H~=값(마케팅기간 배경). 좌측 라벨 7줄(상품명2·VID·판매방식·로켓그로스3)이
        우측 지표 7줄과 정렬(판매자배송 6줄은 로켓그로스 생략). prod_fill = 이 상품군의 교대 배경색.

        라벨/값 텍스트는 `_v4_layout`의 pos 앵커행에만 쓰고, 세로병합은 `_style_block_edges`가 처리한다."""
        biz = ws.title
        nm = _key(ws.cell(hr, _COL_NAME).value)
        layout = self._v4_layout(hr, m_end)
        values = self._v4_values(biz, nm, ws, hr)
        label_at = {a: lab for (a, _s, lab) in layout["ab"]}
        value_at = {a: key for (a, _s, key) in layout["cf"]}
        # 상품명 값 칸(pos0 C:F)=**진한 상품군색**(강조)·나머지 값 칸(VID/판매방식/로켓그로스)=**옅은 상품군색**
        # → 상품군 전체가 은은한 한 색으로 통일(동일 상품군=같은 스타일·소유자 2026-09-25). name_rows=상품명 세로칸.
        name_rows = {a + j for (a, span, key) in layout["cf"] if key == "name" for j in range(span)}
        for r in range(hr, m_end + 1):
            _sty_cell(ws, r, 1, sty, fill=prod_fill, fnt=sty.bold, align=sty.wrap)   # A:B 라벨 칸(진한 상품군색)
            _sty_cell(ws, r, 2, sty, fill=prod_fill, fnt=sty.bold, align=sty.wrap)
            in_name = r in name_rows
            cf_fill = prod_fill if in_name else prod_fill_lt                         # 상품명=진한·나머지=옅은 상품군색
            cf_fnt = sty.bold if in_name else sty.font                               # 상품명=굵게(강조)
            for c in range(_COL_NAME, _COL_SEARCH + 1):
                _sty_cell(ws, r, c, sty, fill=cf_fill, fnt=cf_fnt, align=sty.wrap)
            _sty_cell(ws, r, _COL_METRIC, sty, fill=sty.f_label, fnt=sty.bold)        # G 지표 라벨(연파랑·굵게=제목)
            is_hdr = (r == hr)                                                        # 날짜 헤더행(H~=날짜라벨=굵게)
            for c in range(_FIRST_DATE, maxc + 1):                                   # H~ 값(마케팅기간 배경)
                _sty_cell(ws, r, c, sty, num=True, fnt=(sty.bold if is_hdr else None),
                          fill=(sty.mkt_fill if c in mcols else None))
            if r in label_at:                        # 좌측 라벨(A) — 앵커행에만(세로병합 top-left)
                ws.cell(r, 1, label_at[r])
            if r in value_at:                        # 좌측 값(C) — 앵커행에만
                ws.cell(r, _COL_NAME, values.get(value_at[r], ""))

    def _style_keyword_rows(self, ws, sty: _StyleCtx, kh: int, end: int, mcols: set, maxc: int,
                            is_disc: bool, is_mkt: bool, prod_fill_lt: PatternFill) -> None:
        """키워드블록(레이아웃 v4): A~E 키워드명(가로 병합·좌측확장) · F 검색량 · G(소헤더 비고/순위라벨) · H~ 순위.
        사업자명(A:B) 표기 폐지 — 키워드가 A~E 로 좌측 확장(소유자 확정 2026-09-24). 키워드명 앵커=A.
        소헤더=회색·키워드행 A~F=**옅은 상품군색**(상품군 전체 통일·소유자 2026-09-25)."""
        for r in range(kh, end + 1):
            head = (r == kh)
            kw_fill = sty.f_kwhead if head else prod_fill_lt   # 소헤더=회색·키워드행=옅은 상품군색
            kw_fnt = sty.bold if head else sty.font            # 소헤더 '키워드'=굵게(제목)·키워드명=일반
            for c in range(_COL_KW, _COL_SEARCH):       # A~E 키워드명(앵커=A)
                _sty_cell(ws, r, c, sty, fill=kw_fill, fnt=kw_fnt, align=sty.wrap)
            _sty_cell(ws, r, _COL_SEARCH, sty, fill=kw_fill, fnt=(sty.bold if head else None), num=not head)
            _sty_cell(ws, r, _COL_METRIC, sty, fill=(sty.f_kwhead if head else sty.f_label), fnt=sty.bold)
            if head:   # 비고 자리(소헤더 G): 판매중지 > 체험단중 > 비고 (멱등 재계산)
                gm = ws.cell(r, _COL_METRIC)
                if is_disc:
                    gm.value = "⛔ 판매중지"
                    gm.font = Font(name=self._FN, size=11, bold=True, color="808080")
                elif is_mkt:
                    gm.value = "🔴 체험단중"
                    gm.font = Font(name=self._FN, size=11, bold=True, color="C00000")
                else:
                    gm.value = _LABEL_NOTE
            for c in range(_FIRST_DATE, maxc + 1):
                _sty_cell(ws, r, c, sty, fill=(sty.mkt_fill if c in mcols else None))

    def _flag_sale_mismatch(self, ws, sty: _StyleCtx, kh: int, nm: str, is_disc: bool) -> None:
        """판매상태 불일치 경고: 대장=판매중지인데 쿠팡 실제=판매중/부분판매중이면 판매중지 소헤더행(kh)의
        **최신(맨 왼쪽 H) 날짜칸**에만 "판매중"을 진한 적색·굵게(담당자 확인용·latest_date=날짜기준). 값+서식이 마스터에
        들어가면 구글시트 미러링(worksheet_to_requests)으로 결과시트에도 그대로 반영.

        ⚠ 매 실행 최신 칸에만 표기(원칙) — 과거 실행이 남긴 '판매중'을 먼저 **모두 지워** 여러 날짜 칸에
        누적되던 문제 방지(2026-09-25 실측: 여러 칸 번짐). 불일치가 해소돼도 과거 '판매중'이 남지 않게 항상 청소."""
        cols = self._date_col.get(ws.title, {})
        for c in cols.values():                        # 과거 '판매중' 경고 전부 제거(최신 칸에만 원칙·누적 방지)
            if _norm(ws.cell(kh, c).value) == "판매중":
                ws.cell(kh, c).value = None
        if not (is_disc and self.sale_active(ws.title, nm)):
            return
        _ld = self.latest_date(ws.title)
        _lc = cols.get(_ld) if _ld else None
        if _lc:
            wc = ws.cell(kh, _lc)
            wc.value = "판매중"
            wc.font = Font(name=self._FN, size=11, bold=True, color="C00000")
            wc.alignment = sty.center

    def _style_block_edges(self, ws, sty: _StyleCtx, i: int, hr: int, end: int, m_end: int,
                           kh, headers, regs, maxc: int) -> None:
        """블록 경계선(그룹 바깥=굵은선·변형 사이=얇은선, fix ④) + 세로/가로 병합 + 마지막 블록 하단선."""
        # 상단=블록 첫 행 top(병합 top-left라 정상). 하단=다음(빈) 구분행의 top(시각적으로 마지막 행 하단선).
        # ⚠ 마지막 블록은 end+1 행이 없어서 거기 테두리를 그리면 **빈 행이 새로 생긴다** → end 행 자체 bottom.
        group_start = (i == 0) or (regs[i] != regs[i - 1])
        group_end = (i + 1 >= len(headers)) or (regs[i + 1] != regs[i])
        # 그룹 바깥=굵은선(thick)·같은 상품군 내부(기본↔옵션)=진한 회색 medium(격자 thin 과 확실히 구분·소유자 2026-09-25)
        _sty_edge(ws, maxc, hr, "top", sty.thick if group_start else sty.mid)
        if i + 1 < len(headers):
            # 사이 블록 하단선(=구분 빈 행 상단선): 그룹 끝이면 굵게, 같은 상품군 기본↔옵션 사이면 medium
            _sty_edge(ws, maxc, end + 1, "top", sty.thick if group_end else sty.mid)
        # 병합(마지막) — 세로/가로 병합은 서식·경계선 적용 뒤에.
        # 레이아웃 v4 헤더: A:B 라벨 칸(상품명2·VID1·판매방식1·로켓그로스3)·C:F 값 칸(상품명2 + pos2~ 단일)을
        # pos별로 병합(전체 세로병합 폐지 — 우측 지표 7줄과 정렬). _v4_layout 이 앵커·칸수를 준다.
        layout = self._v4_layout(hr, m_end)
        for a, span, _lab in layout["ab"]:
            _sty_merge(ws, a, 1, a + span - 1, 2)                          # A:B 라벨 칸
        for a, span, _key in layout["cf"]:
            _sty_merge(ws, a, _COL_NAME, a + span - 1, _COL_SEARCH)        # C:F 값 칸
        if kh:   # 키워드 구역: 사업자(A:B) 세로병합 폐지 → 키워드명 A~E 가로병합(좌측확장, 앵커=A·행별)
            for r in range(kh, end + 1):
                _sty_merge(ws, r, _COL_KW, r, _COL_SEARCH - 1)
        # 마지막 블록 하단 굵은선(새 행 안 만듦). ⚠ openpyxl 은 **세로 병합의 하단 테두리를
        # '앵커(top-left) 셀'의 border 로 렌더**한다 → 마지막행 셀에 그려도 세로병합 col1·2 는 얇게 남는다.
        # 그래서 단일셀·가로병합은 마지막행 _sty_edge 로 닫히지만, **헤더 지표구역이 블록 하단(키워드 없는
        # 2차 블록)** 이면 m_end 를 포함하는 A:B 세로병합의 앵커에 굵은 하단선을 별도 지정한다.
        if i + 1 >= len(headers):
            _sty_edge(ws, maxc, end, "bottom", sty.thick)   # 단일셀 + 가로병합(앵커=마지막행) 하단
            if not kh:                          # 키워드 없는 블록: 하단=헤더 지표구역(m_end 포함 A:B 병합의 앵커)
                ab_anchor = next((a for a, span, _l in layout["ab"]
                                  if a <= m_end <= a + span - 1), hr)
                ab = ws.cell(ab_anchor, 1).border
                ws.cell(ab_anchor, 1).border = Border(left=ab.left, right=ab.right,
                                                      top=ab.top, bottom=sty.thick)

    def _roster(self) -> list[tuple[str, bool]]:
        """목차에 실을 계정 로스터 — (사업자, 데이터시트有無). 수집된 계정(시트 있음) 먼저, 그 뒤에
        입력 로스터(`_계정정보`)엔 있으나 아직 시트가 없는 **미수집 계정**을 잇는다(전체 현황 파악)."""
        out = [(b, True) for b in self.account_sheets()]
        have = {b for b, _ in out}
        if _ACCT_SHEET in self.wb.sheetnames:
            ws = self.wb[_ACCT_SHEET]
            for r in range(2, ws.max_row + 1):
                b = _norm(ws.cell(r, 1).value)
                if b and b not in have:
                    out.append((b, False)); have.add(b)
        return out

    # ── 마케팅 기간(계정 목록에서 입력 → 숨김시트 보존) ──────────
    def _mkt_ws(self, create: bool = False):
        if _MKT_SHEET in self.wb.sheetnames:
            return self.wb[_MKT_SHEET]
        if not create:
            return None
        ws = self.wb.create_sheet(_MKT_SHEET)
        ws.sheet_state = "hidden"
        ws.cell(1, 1, "사업자"); ws.cell(1, 2, "상품"); ws.cell(1, 3, "시작")
        ws.cell(1, 4, "종료"); ws.cell(1, 5, "모니터링종료")
        return ws

    def set_marketing(self, biz: str, product: str, start, end, mon) -> None:
        """마케팅 기간 저장(숨김 _마케팅). 셋 다 비면 기존 항목 비움. 상품 없는 계정행은 product=''."""
        biz, product = _norm(biz), _key(product)
        start, end, mon = _norm(start), _norm(end), _norm(mon)
        ws = self._mkt_ws(create=bool(start or end or mon))
        if ws is None:
            return
        for r in range(2, ws.max_row + 1):
            if _norm(ws.cell(r, 1).value) == biz and _key(ws.cell(r, 2).value) == product:
                ws.cell(r, 3).value = start or None   # ⚠ cell(r,c,None) 은 클리어 안 됨 → .value 대입
                ws.cell(r, 4).value = end or None
                ws.cell(r, 5).value = mon or None
                return
        if start or end or mon:
            r = ws.max_row + 1
            ws.cell(r, 1, biz); ws.cell(r, 2, product)
            ws.cell(r, 3).value = start or None
            ws.cell(r, 4).value = end or None
            ws.cell(r, 5).value = mon or None

    def marketing_of(self, biz: str, product: str) -> tuple[str, str, str]:
        """(시작, 종료, 모니터링종료) 문자열 — 없으면 ('','','')."""
        ws = self._mkt_ws()
        biz, product = _norm(biz), _key(product)
        if ws:
            for r in range(2, ws.max_row + 1):
                if _norm(ws.cell(r, 1).value) == biz and _key(ws.cell(r, 2).value) == product:
                    return (_norm(ws.cell(r, 3).value), _norm(ws.cell(r, 4).value), _norm(ws.cell(r, 5).value))
        return ("", "", "")

    # ── 체험단 효과(계정목록 자동열) — 시작일 직전값 → 최신값 점 비교 ──────────
    @staticmethod
    def _cell_num(ws, row: int | None, col: int):
        """(행,열) 셀을 숫자로(int/float/숫자문자열) — 아니면 None."""
        if not row:
            return None
        v = ws.cell(row=row, column=col).value
        if isinstance(v, (int, float)):
            return v
        s = _norm(v)
        try:
            return int(s) if s and s.lstrip("-").isdigit() else (float(s) if s else None)
        except ValueError:
            return None

    @staticmethod
    def _rank_num(v):
        """순위 셀 → 정수 순위. '32위'=32, 정수=그대로. **'44위밖'(미발견)·공란·차단은 None**(정확 순위만)."""
        if isinstance(v, (int, float)):
            return int(v) if v > 0 else None
        s = _norm(v)
        if not s or "위밖" in s:      # 미발견(센 개수 위밖)은 정확 순위 아님 → 제외
            return None
        s = s.replace("위", "").strip()
        return int(s) if s.isdigit() and int(s) > 0 else None

    def _best_rank_at(self, biz: str, product: str, col: int):
        """그 일자 컬럼에서 이 상품 **모든 키워드 중 최고 순위(숫자 최소)** — 정확 순위만, 없으면 None."""
        ws = self.wb[biz]
        best = None
        for kw in self.product_keywords(biz, product):
            r = self._kw_row.get((biz, product, kw))
            if not r:
                continue
            n = self._rank_num(ws.cell(row=r, column=col).value)
            if n is not None and (best is None or n < best):
                best = n
        return best

    def promo_effect(self, biz: str, product: str) -> tuple[str, str]:
        """계정목록 '체험단효과' 열 값 — (표시문자열, 판정) 반환. 판정 ∈ {'up','down',''}.

        소유자 2026-09-24: **체험단 시작일 직전 마지막 측정치 → 가장 최신 측정치**(점 비교).
        판매=판매량 지표행 % 변화, 순위=모든 키워드 **최고 순위(숫자 최소)** before→after(예 32→18 ↑).
        개선(판매↑·순위↑=숫자↓)=up(초록)·악화=down(적색)·데이터 부족(시작 전/후 값 없음)=('', '')=공란."""
        biz, product = _norm(biz), _key(product)
        start_d = _parse_date(self.marketing_of(biz, product)[0])
        if start_d is None or biz not in self.wb.sheetnames:
            return "", ""                                   # 체험단 시작일 없음 → 공란
        cols = self._date_col.get(biz) or {}
        dated = sorted(((d, c) for k, c in cols.items()
                        if (d := _parse_date(k)) is not None), key=lambda t: t[0])
        if not dated:
            return "", ""
        ws = self.wb[biz]

        def _series_ba(getter):
            """계열의 (직전값, 최신값) — 값이 있는 컬럼만: before=시작 직전 마지막 측정치, after=시작 후 최신치.
            gap-fill 빈 컬럼(값 None)은 건너뛰어 실제 측정된 값끼리 비교한다."""
            before = after = None
            for d, c in dated:
                v = getter(c)
                if v is None:
                    continue
                if d < start_d:
                    before = v
                else:
                    after = v
            return before, after

        parts: list[str] = []
        score = 0
        srow = self._metric_row.get((biz, product, config.M_SALES))
        sb, sa = _series_ba(lambda c: self._cell_num(ws, srow, c)) if srow else (None, None)
        if sb is not None and sa is not None and sb > 0:
            pct = round((sa - sb) / sb * 100)
            parts.append(f"판매 {pct:+d}%")
            score += (1 if pct > 0 else -1 if pct < 0 else 0)
        rb, ra = _series_ba(lambda c: self._best_rank_at(biz, product, c))
        if rb is not None and ra is not None:
            arrow = "↑" if ra < rb else ("↓" if ra > rb else "→")   # 순위 숫자↓ = 상위 노출 = 개선
            parts.append(f"순위 {rb}→{ra} {arrow}")
            score += (1 if ra < rb else -1 if ra > rb else 0)
        if not parts:
            return "", ""                                   # 판매·순위 둘 다 데이터 부족 → 공란
        return " · ".join(parts), ("up" if score > 0 else "down" if score < 0 else "")

    # ── 판매중지/삭제(대장에서 사라짐) 표기 — 데이터는 보존, 표시만 구분 ──────
    def set_discontinued(self, biz: str, product: str, flag: bool) -> None:
        """(사업자,상품) 판매중지 여부 기록. flag=False면 해제(대장에 다시 나타나면 복귀)."""
        biz, product = _norm(biz), _key(product)
        if _DISC_SHEET in self.wb.sheetnames:
            ws = self.wb[_DISC_SHEET]
        elif not flag:
            return
        else:
            ws = self.wb.create_sheet(_DISC_SHEET); ws.sheet_state = "hidden"
            ws.cell(1, 1, "사업자"); ws.cell(1, 2, "상품")
        for r in range(2, ws.max_row + 1):
            if _norm(ws.cell(r, 1).value) == biz and _key(ws.cell(r, 2).value) == product:
                ws.cell(r, 3).value = "Y" if flag else None   # ⚠ cell(r,c,None) 은 클리어 안 됨 → .value 대입
                return
        if flag:
            r = ws.max_row + 1
            ws.cell(r, 1, biz); ws.cell(r, 2, product); ws.cell(r, 3, "Y")

    def is_discontinued(self, biz: str, product: str) -> bool:
        if _DISC_SHEET not in self.wb.sheetnames:
            return False
        ws = self.wb[_DISC_SHEET]
        biz, product = _norm(biz), _key(product)
        for r in range(2, ws.max_row + 1):
            if (_norm(ws.cell(r, 1).value) == biz and _key(ws.cell(r, 2).value) == product
                    and _norm(ws.cell(r, 3).value) == "Y"):
                return True
        return False

    def reconcile_account(self, biz: str, seen_products) -> list[str]:
        """대장 대조: 그 계정의 마스터 블록 중 이번 대장에 **없는** 상품 = 판매중지 표기, 있는 것은 해제.
        seen_products = 이번 실행에서 대장에 존재한 상품(블록명, vid 앵커로 해석된 pname) 집합. 반환=새로 중지된 상품."""
        seen = {_key(p) for p in seen_products}
        newly: list[str] = []
        for p in self.products_of(biz):
            gone = p not in seen
            if gone and not self.is_discontinued(biz, p):
                newly.append(p)
            self.set_discontinued(biz, p, gone)
        return newly

    def delete_account(self, biz: str) -> bool:
        """관리대장에서 **줄이 완전히 사라진 계정**을 결과에서 완전 삭제 — 시트(시계열 이력)+모든 메타행.

        ⚠ **되돌릴 수 없음**(그 사업자 통계 이력 소멸). 관리대장에 '상태=판매중지'로 **남아있는** 것과는 다르다
        (그건 유지+경고). 호출부(pipeline)가 '관리대장에 계정ID가 아예 없음'을 확인한 뒤에만 호출한다.
        지운 게 있으면 True. `_계정정보`·`_상품ID`·`_중단`·`_마케팅`의 해당 사업자 행도 모두 제거한다."""
        biz = _norm(biz)
        if not biz:
            return False
        removed = False
        if biz in self.wb.sheetnames and biz not in _SPECIAL_SHEETS:
            del self.wb[biz]
            removed = True
        for meta in (_META_SHEET, _DISC_SHEET, _MKT_SHEET, _ACCT_SHEET):
            if meta not in self.wb.sheetnames:
                continue
            ws = self.wb[meta]
            for r in range(ws.max_row, 1, -1):          # 아래→위(삭제 시 인덱스 안정)
                if _norm(ws.cell(r, 1).value) == biz:
                    ws.delete_rows(r)
                    removed = True
        if removed:
            self._reindex()
        return removed

    def blocks_with_registered_name(self, biz: str, reg: str) -> list[str]:
        """이 사업자에서 **등록상품명(reg)** 에 해당하는 기존 블록 이름들(블록명==reg 또는 registered_name==reg).

        vid 출처가 바뀌어 vid 값이 달라졌을 때, 같은 등록상품명의 옛 블록을 찾아 정리(삭제)하는 데 쓴다."""
        biz, reg = _norm(biz), _key(reg)
        if not reg:
            return []
        out: list[str] = []
        for p in self.products_of(biz):
            if p == reg or self.registered_name(biz, p) == reg:
                out.append(p)
        return out

    def delete_product_block(self, biz: str, product: str) -> bool:
        """상품 블록 **하나**를 그 사업자 시트에서 완전 삭제(시계열 이력 포함)+메타행 제거. 시트 자체는 유지.

        ⚠ **되돌릴 수 없음**(그 블록 이력 소멸). vid 출처 변경 첫 적용 시 **vid 가 바뀐**(정체성이 달라진) 옛
        블록을 지우고 새로 시작할 때 쓴다(잘못된 이력 승계 방지, 소유자 2026-09-20). 블록 범위=헤더행~다음
        블록 헤더 직전(마지막이면 시트 끝). insert/delete 는 병합셀 손상 방지로 _unmerge_all 후 수행·전체 재인덱스."""
        biz, product = _norm(biz), _key(product)
        if biz not in self.wb.sheetnames:
            return False
        ws = self.wb[biz]
        headers = sorted(self._date_rows.get(biz, []))
        hr = next((r for r in headers if _key(ws.cell(r, _COL_NAME).value) == product), None)
        if hr is None:
            return False
        later = [r for r in headers if r > hr]
        end = (min(later) - 1) if later else ws.max_row   # 다음 블록 헤더 직전(사이 빈 줄 포함) 또는 시트 끝
        _unmerge_all(ws)                                   # 병합 해제 후 삭제(데이터 손상 방지, 이후 apply_style 재병합)
        ws.delete_rows(hr, end - hr + 1)
        for meta in (_META_SHEET, _DISC_SHEET, _MKT_SHEET):   # (biz, product) 메타행 제거
            if meta not in self.wb.sheetnames:
                continue
            mws = self.wb[meta]
            for r in range(mws.max_row, 1, -1):
                if _norm(mws.cell(r, 1).value) == biz and _key(mws.cell(r, 2).value) == product:
                    mws.delete_rows(r)
        self._reindex()
        return True

    @staticmethod
    def _mkt_status(start: str, end: str, mon: str) -> str:
        """오늘 기준 체험단 상태: 예정/체험단중/모니터링/종료/''(미설정)."""
        s, e, m = _parse_date(start), _parse_date(end), _parse_date(mon)
        today = _date.today()
        if s and today < s:
            return "예정"
        if s and e and s <= today <= e:
            return "체험단중"
        if e and m and e < today <= m:
            return "모니터링"
        if m and today > m:
            return "종료"
        if (s or e or m):
            return "체험단중" if (s and e and s <= today <= e) else ""
        return ""

    # ── 수집 주기(마케팅 기반) ────────────────────────────────
    def has_marketing(self) -> bool:
        """마케팅 기간이 한 건이라도 설정돼 있는가(수집 주기 게이팅 활성 조건). 미설정이면 현행대로 매일."""
        ws = self._mkt_ws()
        if ws is None:
            return False
        for r in range(2, ws.max_row + 1):
            if any(_norm(ws.cell(r, c).value) for c in (3, 4, 5)):
                return True
        return False

    def product_latest_date(self, biz: str, product: str) -> str:
        """그 상품이 값을 가진 가장 최근 **날짜** 일자 라벨(없으면 ''). 상품별 3일주기 판정용.
        물리 컬럼 위치가 아니라 **날짜값 기준**(내림차순 정렬이라 최신=맨 왼쪽 칸)."""
        cols = self._date_col.get(biz, {})
        if not cols or biz not in self.wb.sheetnames:
            return ""
        ws = self.wb[biz]
        best, best_d = "", None
        for m in _ALL_METRICS:
            row = self._metric_row.get((biz, product, m))
            if row is None:
                continue
            for lbl, c in cols.items():
                if ws.cell(row, c).value in (None, ""):
                    continue
                dd = _parse_date(lbl)
                if dd is not None and (best_d is None or dd > best_d):
                    best, best_d = lbl, dd
        return best

    def product_cadence(self, biz: str, product: str, target_iso: str) -> str:
        """그 상품의 오늘(target) 수집 주기: 'daily'·'every3'·'stop'(상품별 마케팅 기준)."""
        target = _parse_date(target_iso)
        s, e, m = (_parse_date(x) for x in self.marketing_of(biz, product))
        if not (s or e or m):
            return "every3"                                 # 마케팅 미설정 = 기본 3일주기
        if m and target and target > m:
            return "stop"                                   # 모니터링 종료일 이후 = 중단
        if s and target and s <= target <= s + _td(days=30):
            return "daily"                                  # 마케팅 시작~1개월 = 매일
        return "every3"

    def product_due(self, biz: str, product: str, target_iso: str) -> tuple[bool, str]:
        """오늘(target) 이 **상품**을 수집할지 (여부, 사유). every3는 그 상품 최근수집과 3일 이상일 때만."""
        cad = self.product_cadence(biz, product, target_iso)
        if cad == "stop":
            return False, "모니터링 종료(중단)"
        if cad == "daily":
            return True, "마케팅(매일)"
        last, target = _parse_date(self.product_latest_date(biz, product)), _parse_date(target_iso)
        if last and target and (target - last).days < 3:
            return False, f"3일 주기(최근 {self.product_latest_date(biz, product)})"
        return True, "3일 주기 도래"

    def account_due(self, biz: str, target_iso: str) -> tuple[bool, str]:
        """오늘 이 **계정**에 로그인할지(=상품이 하나라도 수집 대상). 로그인은 계정 단위라 OR 로 집계."""
        prods = self.products_of(biz)
        if not prods:
            return True, "신규/상품없음(수집 시도)"
        for p in prods:
            if self.product_due(biz, p, target_iso)[0]:
                return True, "수집 대상 상품 있음"
        return False, "모든 상품 오늘 수집 대상 아님"

    def product_roster(self) -> list[tuple[str, str, int | None, bool]]:
        """계정목록(구글시트) 동기화용 상품 로스터 — (사업자, 상품(노출명), 블록 헤더행|None, 데이터시트有無).
        openpyxl `계정 목록`(_build_index)과 동일 순서·집합(수집 계정→상품, 그 뒤 미수집 계정)."""
        return self._product_rows()

    def status_of(self, biz: str, product: str, has_sheet: bool = True) -> str:
        """계정목록 상태 열 값 — **관리대장 상태만**(소유자 2026-09-24 확정): 대장 판매중지 > (미수집) > 체험단 상태.

        ⚠소유자 결정(2026-09-24): 계정목록엔 **관리대장 상태**만 표기한다. 쿠팡 상품조회 판매상태(임시저장·
        승인반려 등)는 **날짜별 '판매상태' 지표행**에서 이미 보여주므로 계정목록에선 뺀다(2026-09-22의
        productStatus 폴백 되돌림 — 실측 근거=소유자 지시, 상태는 소스별로 위치 분리해 표기)."""
        if has_sheet and product and self.is_discontinued(biz, product):
            return "⛔ 판매중지"          # 관리대장 상태(대장에서 빠짐)
        if not has_sheet:
            return "미수집"
        s, e, m = self.marketing_of(biz, product)
        return self._mkt_status(s, e, m)   # 체험단중 / 공란

    def _is_secondary_option(self, biz: str, product: str) -> bool:
        """다중옵션 상품의 **2차(비대표) 옵션 블록**인가 — 계정목록(상품별 로스터)에서 제외 대상.

        2차 옵션 블록은 판매정보만이라 **키워드 소헤더가 없고**(rank_rows=False로 생성) 이름이
        '등록상품명 (옵션라벨)'이다. 대표(첫 옵션)·단일옵션은 키워드 소헤더가 있어 제외되지 않는다.
        소유자 확정(2026-09-20): 계정목록은 **상품별 1줄**(대표 옵션만), 옵션 분리는 통계 시트 안에서만."""
        if self.has_keyword_section(biz, product):
            return False
        reg = self.registered_name(biz, product)
        return bool(reg and product != reg)

    def _product_rows(self) -> list[tuple[str, str, int | None, bool]]:
        """계정 목록에 실을 상품 로스터 — (사업자, 상품, 그 상품 블록 헤더행|None, 데이터시트有無).
        수집된 계정의 상품들 먼저(계정→상품 순), 그 뒤 미수집 계정(상품='').
        **다중옵션 2차 블록은 제외**(상품별 1줄=대표 옵션만, 소유자 2026-09-20)."""
        rows: list[tuple[str, str, int | None, bool]] = []
        for biz in self.account_sheets():
            hdr: dict[str, int] = {}
            for r in self._date_rows.get(biz, []):
                nm = _key(self.wb[biz].cell(r, _COL_NAME).value)
                if nm:
                    hdr.setdefault(nm, r)
            prods = [p for p in self.products_of(biz) if not self._is_secondary_option(biz, p)]
            if prods:
                for p in prods:
                    rows.append((biz, p, hdr.get(p), True))
            else:
                rows.append((biz, "", None, True))
        have = set(self.account_sheets())
        if _ACCT_SHEET in self.wb.sheetnames:
            aws = self.wb[_ACCT_SHEET]
            for r in range(2, aws.max_row + 1):
                b = _norm(aws.cell(r, 1).value)
                if b and b not in have:
                    rows.append((b, "", None, False)); have.add(b)
        return rows

    def _sync_marketing_from_index(self) -> None:
        """재생성 전에 **현재 계정목록(가시)의 마케팅 입력을 숨김시트로 회수**(사용자 입력 보존).

        열 위치를 **헤더(2행)로 탐지**한다 → 대표자 컬럼 추가로 열이 밀린 신규 레이아웃과, 대표자 없던 옛
        레이아웃 모두에서 사업자/상품/체험단 열을 정확히 찾아 회수한다(전환 시 사용자 입력 유실 방지)."""
        if _INDEX_SHEET not in self.wb.sheetnames:
            return
        ws = self.wb[_INDEX_SHEET]
        # 헤더행(2행)에서 각 컬럼 위치 파악(1-based). 라벨이 있어야 그 열을 읽는다.
        hdr = {_norm(ws.cell(2, c).value): c for c in range(1, ws.max_column + 1)}
        c_biz = hdr.get("사업자")
        c_prod = next((hdr[h] for h in hdr if h.startswith("상품명")), None)
        c_start = hdr.get(_MKT_COLS[0]) or hdr.get(_MKT_COLS_LEGACY0)
        c_end = hdr.get(_MKT_COLS[1])
        c_mon = hdr.get(_MKT_COLS[2])
        if not (c_biz and c_prod and c_start):   # 마케팅 레이아웃이 아니면 회수 생략
            return
        for r in range(3, ws.max_row + 1):
            biz = _norm(ws.cell(r, c_biz).value)
            prod = _key(ws.cell(r, c_prod).value)
            if not biz:
                continue
            start = _norm(ws.cell(r, c_start).value)
            end = _norm(ws.cell(r, c_end).value) if c_end else ""
            mon = _norm(ws.cell(r, c_mon).value) if c_mon else ""
            if start or end or mon:
                self.set_marketing(biz, prod, start, end, mon)

    def _build_index(self) -> None:
        """첫 시트 '계정 목록' 재생성 — 상품 단위 로스터 + 마케팅 기간 입력열 + 점프 링크 + 상태.

        계정이 100개여도 한눈에 보고 클릭 한 번으로 이동하도록. 데이터 시트는 안 건드리고 목차만 추가(멱등:
        매번 지우고 다시 만든다). 순위 공란수 = 최근 일자 컬럼에서 아직 못 잰(공란) 키워드 수(재측정 대상).
        """
        # 마케팅 입력 원본 = 관리대장 + **마스터 계정목록 직접 입력** 둘 다 지원.
        # 재생성 전에 사용자가 계정목록에 넣은 마케팅 값을 숨김시트로 회수(대장값은 파이프라인이 별도 반영).
        self._sync_marketing_from_index()
        for legacy in (_INDEX_SHEET, "목차"):   # 새 이름 + 레거시('목차') 모두 제거(옛 시트가 계정으로 오인 방지)
            if legacy in self.wb.sheetnames:
                del self.wb[legacy]
        rows = self._product_rows()   # (사업자, 상품, 헤더행|None, 시트有無) — 상품 단위
        ws = self.wb.create_sheet(_INDEX_SHEET, 0)       # 맨 앞
        bold = Font(name=self._FN, size=11, bold=True)
        title_font = Font(name=self._FN, size=14, bold=True)
        thin = Side(style="thin", color="BFBFBF")
        box = Border(left=thin, right=thin, top=thin, bottom=thin)
        center = Alignment(horizontal="center", vertical="center")
        head_fill = PatternFill("solid", fgColor=self._FILL_LABEL)
        mkt_fill = PatternFill("solid", fgColor="FFF2CC")   # 마케팅 입력열 강조(입력 자리 안내)
        sty = _IdxStyle(
            font=Font(name=self._FN, size=11),
            gray_font=Font(name=self._FN, size=11, color="9AA7B6"),   # 미수집(옅게)
            link_font=Font(name=self._FN, size=11, color="0563C1", underline="single"),
            red_bold=Font(name=self._FN, size=11, bold=True, color="C00000"),   # 체험단중 상태
            box=box, center=center,
            left=Alignment(horizontal="left", vertical="center"),
            mkt_fill=mkt_fill)
        n_prod = sum(1 for _b, p, _h, hs in rows if hs and p)

        ws.cell(1, 1, f"{_INDEX_SHEET} · 상품 {n_prod}개").font = title_font
        ws.merge_cells("A1:I1")                            # 대표자+체험단효과로 9열(A~I)
        ws.cell(1, 1).alignment = center
        # 열: 1 대표자 · 2 사업자 · 3 상품명 · 4 계정ID · 5~7 체험단(관리대장 입력·표시) · 8 상태 · 9 체험단효과.
        heads = ["대표자", "사업자", "상품명(클릭 이동)", "계정ID",
                 _MKT_COLS[0], _MKT_COLS[1], _MKT_COLS[2], "상태", "체험단효과"]
        for c, h in enumerate(heads, 1):
            x = ws.cell(2, c, h)
            x.font = bold; x.alignment = center; x.border = box
            x.fill = mkt_fill if 5 <= c <= 7 else head_fill   # 5~7열=마케팅(관리대장 값 표시)
        for r, (biz, prod, hdr, has_sheet) in enumerate(rows, start=3):
            self._index_row(ws, r, biz, prod, hdr, has_sheet, sty)
        for c, w in {1: 16, 2: 22, 3: 40, 4: 15, 5: 13, 6: 13, 7: 14, 8: 10, 9: 26}.items():
            ws.column_dimensions[get_column_letter(c)].width = w
        ws.row_dimensions[1].height = 21
        ws.freeze_panes = "E3"                            # 제목·헤더 + 대표자/사업자/상품/계정ID 고정(가로 스크롤 시)
        # '항상 고정': 첫 탭(index 0) + **파일 열면 항상 목차가 선택된 채로 열리게** 활성 시트로 지정.
        try:
            self.wb.active = self.wb.index(ws)
            for other in self.wb.worksheets:             # 다른 시트 탭 선택 해제(목차만 활성)
                other.sheet_view.tabSelected = (other is ws)
        except Exception:
            pass

    def _index_row(self, ws, r: int, biz: str, prod: str, hdr, has_sheet: bool, sty: _IdxStyle) -> None:
        """목차 한 행 렌더 — 대표자·사업자·상품(점프 링크)·계정ID·마케팅 입력열·상태(판매중지/체험단중/미수집)."""
        ws.cell(r, 1, self.representative_of(biz)).font = sty.font if has_sheet else sty.gray_font
        ws.cell(r, 2, biz).font = sty.font if has_sheet else sty.gray_font
        pcell = ws.cell(r, 3, prod if prod else ("(미수집)" if not has_sheet else "(상품없음)"))
        if has_sheet and prod and hdr:      # 상품 블록으로 점프(헤더행)
            pcell.hyperlink = Hyperlink(ref=pcell.coordinate,
                                        location=f"'{biz.replace(chr(39), chr(39) * 2)}'!A{hdr}")
            pcell.font = sty.link_font
        else:
            pcell.font = sty.gray_font
        ws.cell(r, 4, self.account_id_of(biz)).font = sty.font if has_sheet else sty.gray_font
        start, end, mon = self.marketing_of(biz, prod)
        if has_sheet and prod and self.is_discontinued(biz, prod):
            status = "⛔ 판매중지"
        else:
            status = self._mkt_status(start, end, mon) if has_sheet else "미수집"
        for c, v in ((5, start), (6, end), (7, mon)):   # 마케팅(관리대장 값 표시)
            x = ws.cell(r, c, v)
            x.font = sty.font; x.alignment = sty.center; x.border = sty.box; x.fill = sty.mkt_fill
        st = ws.cell(r, 8, status); st.alignment = sty.center; st.border = sty.box
        _gray = ("미수집", "종료", "⛔ 판매중지", "판매중지", "임시저장", "승인반려")   # 미판매/비활성 = 옅게
        st.font = sty.red_bold if status == "체험단중" else (sty.gray_font if status in _gray else sty.font)
        eff, verdict = self.promo_effect(biz, prod) if has_sheet else ("", "")   # 9열 체험단효과(시작일 직전→최신)
        pe = ws.cell(r, 9, eff); pe.alignment = sty.center; pe.border = sty.box; pe.font = sty.font
        if verdict == "up":
            pe.fill = PatternFill("solid", fgColor="C9E6C9")   # 개선=연초록
        elif verdict == "down":
            pe.fill = PatternFill("solid", fgColor="F4CCCC")   # 악화=연적색
        for c in (1, 2, 3, 4):
            ws.cell(r, c).alignment = sty.left if c == 3 else sty.center
            ws.cell(r, c).border = sty.box
