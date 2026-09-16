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

_COL_KIND = 1      # A: 상품구분 / 사업자명
_COL_NAME = 3      # C: 상품명 / 키워드
_COL_SEARCH = 6    # F: 검색량
_COL_METRIC = 7    # G: 지표 라벨
_FIRST_DATE = 8    # H~: 일자
_LABEL_DATE = "날짜"
_LABEL_KEYWORD = "키워드"
_LABEL_SEARCH = "검색량"
_LABEL_NOTE = "비고"
_ALL_METRICS = frozenset(config.CONTRACT_METRICS + config.PERSONAL_METRICS)
_META_SHEET = "_상품ID"   # 숨김 시트: (사업자,상품)→고유ID(vendorItemId) 매핑. ③ 순위조회가 상품 매칭에 사용
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


def _parse_date(s):
    """날짜 문자열 → date(못 읽으면 None). YYYY-MM-DD·YY.MM.DD·**MM.DD(년도 없음·올해)**·YYYY/MM/DD·MM/DD 등 허용.

    ⚠ 일자 컬럼 라벨은 2026-09-16부터 **년도 없는 '월.일'(예 09.16)** 로 적는다(사용자 요청·당분간).
    '월.일'은 올해로 해석(연말/연초 경계는 당분간 미고려 — 필요 시 년도 복원)."""
    s = _norm(s)
    if not s:
        return None
    if isinstance(s, (_dt, _date)):
        return s.date() if isinstance(s, _dt) else s
    no_year = ("%m/%d", "%m-%d", "%m.%d")   # 년도 없는 표기 → 올해로 보정
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%y.%m.%d", "%Y/%m/%d", "%y/%m/%d", "%m.%d", "%m/%d", "%m-%d"):
        try:
            d = _dt.strptime(s, fmt).date()
            return d.replace(year=_date.today().year) if fmt in no_year else d
        except ValueError:
            continue
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
        self._vid_row: dict[tuple[str, str], int] = {}          # {(사업자,상품): _상품ID 시트 행}
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
                name = _key(ws.cell(r, _COL_NAME).value)
                metric = _norm(ws.cell(r, _COL_METRIC).value)
                if metric == _LABEL_DATE:                       # 상품 헤더행 → 새 상품
                    cur_prod = name
                    self._date_rows[biz].append(r)
                    for c in range(_FIRST_DATE, ws.max_column + 1):
                        d = _norm(ws.cell(r, c).value)
                        if d:
                            self._date_col[biz].setdefault(d, c)
                elif metric in _ALL_METRICS:                    # 상품 지표행
                    if cur_prod:
                        self._metric_row[(biz, cur_prod, metric)] = r
                elif metric == config.M_RANK and name:          # 키워드 순위행
                    if cur_prod:
                        self._kw_row[(biz, cur_prod, name)] = r

    # ── 재개(이어서)용 조회 ──────────────────────────────────
    def has_product(self, biz: str, product: str) -> bool:
        return any(k[0] == biz and k[1] == product for k in self._metric_row)

    def product_keywords(self, biz: str, product: str) -> list[str]:
        """이 상품에 이미 기록된 키워드 목록(있으면 AI 선정 건너뛰고 순위만 — 키워드 동결)."""
        out: list[str] = []
        for (b, p, kw) in self._kw_row:
            if b == biz and p == product and kw not in out:
                out.append(kw)
        return out

    def products_of(self, biz: str) -> list[str]:
        """그 사업자 시트의 상품명 목록(블록 등장 순서). ②③ 단계가 상품을 순회하는 데 쓴다."""
        out: list[str] = []
        for (b, p, _m) in self._metric_row:
            if b == biz and p not in out:
                out.append(p)
        return out

    def latest_date(self, biz: str) -> str | None:
        """그 사업자의 가장 최근(맨 오른쪽) 일자 컬럼 라벨(③ 순위 기록 날짜)."""
        cols = self._date_col.get(biz, {})
        return max(cols, key=lambda d: cols[d]) if cols else None

    def account_sheets(self) -> list[str]:
        """계정(사업자) 시트명 목록 — 특수 시트(상품ID·목차·계정정보)는 제외."""
        return [s for s in self.wb.sheetnames if s not in _SPECIAL_SHEETS]

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
        """기존 블록의 **구분 라벨(A열)만** 최신화(구조 변경 없음). 라벨 문구 변경(마이그레이션: '계약 상품'→
        '로켓그로스' 등)·구분 변경(로켓그로스→둘 다) 반영. 재고행 유무 등 구조는 그대로(기존 로켓그로스/둘 다는
        이미 재고행 보유). 헤더행을 찾아 A셀 값만 바꾼다(A:B 세로병합 앵커=헤더행 A셀이라 표시 갱신됨)."""
        kind = _norm(kind)
        if not kind or biz not in self.wb.sheetnames:
            return
        ws = self.wb[biz]
        for r in self._date_rows.get(biz, []):
            if _key(ws.cell(r, _COL_NAME).value) == product:
                if _norm(ws.cell(r, _COL_KIND).value) != kind:
                    ws.cell(r, _COL_KIND, kind)
                return

    def ensure_product_block(self, biz: str, product: str, kind: str, keywords: list[str]) -> None:
        """상품 블록이 없으면 생성(로켓그로스·둘다=CONTRACT_METRICS[재고 포함]/판매자배송=PERSONAL_METRICS +
        키워드 순위행). 이미 있으면 **구분 라벨만 최신화**(문구 마이그레이션·구분 변경 반영)."""
        if self.has_product(biz, product):
            self._update_kind_label(biz, product, kind)
            return
        ws = self.ensure_account(biz)
        metrics = (config.CONTRACT_METRICS if kind in config.KINDS_WITH_INVENTORY
                   else config.PERSONAL_METRICS)
        r = (ws.max_row + 2) if ws.max_row > 1 else 3      # 블록 사이 빈 줄
        # 상품 헤더행: A=구분, C=상품명, G=날짜, H~=기존 일자 라벨
        ws.cell(r, _COL_KIND, kind)
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
        # 키워드 소헤더
        r += 1
        ws.cell(r, _COL_KIND, biz)
        ws.cell(r, _COL_NAME, _LABEL_KEYWORD)
        ws.cell(r, _COL_SEARCH, _LABEL_SEARCH)
        ws.cell(r, _COL_METRIC, _LABEL_NOTE)
        # 키워드 순위행
        kws = list(dict.fromkeys(keywords))
        for kw in kws:
            r += 1
            ws.cell(r, _COL_NAME, kw)
            ws.cell(r, _COL_METRIC, config.M_RANK)
            self._kw_row[(biz, product, kw)] = r
        # 키워드가 KW_TRACK_N(=4) 미만이면 **빈 순위행**으로 채워 블록의 키워드행 구조를 항상 유지한다
        # (키워드 없어도 4행 유지·공란 OK — 사용자 요구 2026-09-15). 이름 공란 + M_RANK 인 빈 행은
        # _kw_row 에 안 잡혀 '키워드 없음'으로 판정되므로, ② 키워드선정이 그 상품을 선정하고
        # add_product_keywords 가 새 행을 만들기 전에 이 빈 행부터 채운다(블록 팽창 방지).
        for _ in range(config.KW_TRACK_N - len(kws)):
            r += 1
            ws.cell(r, _COL_METRIC, config.M_RANK)   # 이름 공란 + M_RANK = 빈 키워드 순위행
        self.set_registered_name(biz, product)   # 생성 시점의 이름 = 등록상품명(이후 노출명으로 바뀌어도 보존)

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
                rows.append((r, _key(ws.cell(r, _COL_NAME).value)))
        return rows

    def add_product_keywords(self, biz: str, product: str, keywords: list[str]) -> list[str]:
        """상품 블록에 새 키워드 추가. **빈 순위행부터 채우고**, 모자라면 새 행 삽입. 반환: 실제 추가분.

        ensure_product_block 이 4행 유지용으로 만든 빈 순위행(이름 공란)을 먼저 재사용해 블록이
        4행을 넘겨 팽창하는 것을 막는다. 빈 행보다 키워드가 많으면 마지막 순위행 아래에 insert_rows 로
        끼워 넣는다. 없던 키워드만 추가.
        """
        # 띄어쓰기·대소문자 무시 dedup — **쿠팡은 띄어쓰기 유무를 동일 검색어로 취급**하므로 이미 추적 중인
        # 키워드의 다른 표기('캠핑타프'↔'캠핑 타프')는 추가하지 않는다(선정 단계와 동일 원칙, 시트 미러링에도
        # 변형 중복이 재유입되지 않게). 들어온 표기는 **그대로** 적재(선정된 띄어쓰기 형태가 시트에 반영됨).
        def _sp(s) -> str:
            return str(s).replace(" ", "").casefold()
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
            ws.cell(row, _COL_NAME, add[i])
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
                ws.cell(last_kw_row + j, _COL_NAME, kw)
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
        """일자 라벨 하나를 그 사업자 시트의 **맨 오른쪽**에 새 컬럼으로 추가(헤더행 전부에 라벨 기록)."""
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
            parsed = {lbl: _parse_date(lbl) for lbl in cols}
            if any(d is None for d in parsed.values()):
                _log(f"  [날짜정렬] {biz}: 파싱 불가 라벨 있음 → 건너뜀 {sorted(cols)}")
                continue
            # 날짜→기존 열(첫 등장). 라벨을 '월.일'로 재포맷하므로 값은 **날짜**로 스냅샷해 매칭한다.
            date2col: dict = {}
            for lbl, dd in sorted(parsed.items(), key=lambda kv: kv[1]):
                date2col.setdefault(dd, cols[lbl])
            days = sorted(date2col)
            first, last = days[0], days[-1]
            target_days: list = []
            d = first
            while d <= last:
                target_days.append(d)
                d += _td(days=1)
            target = [dd.strftime("%m.%d") for dd in target_days]   # 년도 없는 '월.일'로 통일
            old_labels_sorted = [lbl for lbl, _dd in sorted(parsed.items(), key=lambda kv: kv[1])]
            old_cols_sorted = [cols[lbl] for lbl in old_labels_sorted]
            # 이미 '월.일' 연속·정렬이고 물리 순서도 H부터 오름차순이면 변경 없음(멱등)
            if target == old_labels_sorted \
               and old_cols_sorted == list(range(_FIRST_DATE, _FIRST_DATE + len(old_cols_sorted))):
                added[biz] = []
                continue
            ws = self.wb[biz]
            max_row = ws.max_row
            # 스냅샷: 기존 일자 컬럼의 모든 셀 값을 (행, 날짜)로 보존
            snap: dict[tuple[int, object], object] = {}
            used_cols = set(cols.values())
            for r in range(1, max_row + 1):
                for dd, c in date2col.items():
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
            old_days = set(days)
            added[biz] = [dd.strftime("%m.%d") for dd in target_days if dd not in old_days]
        return added

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
        ws.cell(1, 1, "사업자"); ws.cell(1, 2, "상품명"); ws.cell(1, 3, "상품ID(|구분)")
        ws.cell(1, 4, "키워드서명"); ws.cell(1, 5, "권고제목")   # ⑤ 제목 캐시(동결 상품 AI 재호출 생략)
        ws.cell(1, 6, "등록상품명")   # 대장 원본명(노출명으로 바뀌어도 불변) — 계정목록 안정키·3c 마케팅 매칭 기준
        return ws

    def set_product_vids(self, biz: str, product: str, vids) -> None:
        """상품의 고유ID(vendorItemId) 목록을 숨김 시트에 저장(③ 순위조회의 상품 매칭용)."""
        vids = [str(v) for v in dict.fromkeys(vids) if v]
        if not vids:
            return
        ws = self._meta_ws()
        row = self._vid_row.get((biz, product))
        if row is None:
            row = ws.max_row + 1
            ws.cell(row, 1, biz); ws.cell(row, 2, product)
            self._vid_row[(biz, product)] = row
        ws.cell(row, 3, "|".join(vids))

    def product_vids(self, biz: str, product: str) -> list[str]:
        """저장된 상품 고유ID 목록(없으면 빈 리스트)."""
        row = self._vid_row.get((biz, product))
        if row is None or _META_SHEET not in self.wb.sheetnames:
            return []
        v = self.wb[_META_SHEET].cell(row, 3).value
        return [x for x in str(v).split("|") if x] if v else []

    def set_registered_name(self, biz: str, product: str) -> None:
        """상품 블록의 **등록상품명**(대장 원본명)을 숨김시트에 최초 1회 보존(노출명으로 바뀌어도 불변).

        계정목록(구글시트) 안정키 `marketing_key(계정ID+등록상품명)`·3c 마케팅 역머지 매칭의 기준(§7).
        이미 값이 있으면 덮지 않는다(이름 변경·재호출에도 최초 등록명 유지)."""
        biz, product = _norm(biz), _key(product)
        if not (biz and product):
            return
        ws = self._meta_ws()
        row = self._vid_row.get((biz, product))
        if row is None:
            row = ws.max_row + 1
            ws.cell(row, 1, biz); ws.cell(row, 2, product)
            self._vid_row[(biz, product)] = row
        if not _norm(ws.cell(row, 6).value):
            ws.cell(row, 6, product)

    def registered_name(self, biz: str, product: str) -> str:
        """저장된 등록상품명(없으면 '' — 옛 마스터엔 없을 수 있음, 호출부가 노출명으로 폴백)."""
        row = self._vid_row.get((biz, product))
        if row is None or _META_SHEET not in self.wb.sheetnames:
            return ""
        return _norm(self.wb[_META_SHEET].cell(row, 6).value)

    def product_inventory(self, biz: str, product: str):
        """이 상품의 **최신 일자 재고현황**(로켓그로스). 재고행 없거나(개인상품)·값 없으면 None. 관리대장 역기록용."""
        date = self.latest_date(biz)
        row = self._metric_row.get((biz, product, config.M_INVENTORY))
        col = self._date_col.get(biz, {}).get(date) if date else None
        if row is None or col is None:
            return None
        v = self.wb[biz].cell(row, col).value
        return v if v not in (None, "") else None

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
        """이름칸 표시값 = **1줄 상품제목 + (보이지 않는 구분자) + 2줄 상품 인식코드(vendorItemId)**.

        키(순수 상품명 `name`)는 건드리지 않고 표시용 꼬리만 만든다. vid 없으면 이름만(1줄). 여러 옵션이면
        vid 를 '/' 로 이어 붙인다. `apply_style` 이 저장 직전 이 값으로 헤더 C셀을 렌더링(멱등)."""
        vids = self.product_vids(biz, name)
        if not vids:
            return name
        return f"{name}{config.NAME_ID_SEP}\nVID : {' / '.join(vids)}"

    def resolve_block_name(self, biz: str, vids) -> str | None:
        """이 사업자에서 주어진 vid(옵션ID)와 교집합이 있는 **기존 상품 블록의 이름**을 반환(없으면 None).

        상품 정체성을 vendorItemId 에 앵커한다 — ①판매수집이 매일 넘기는 이름(복원명)이 달라도, ③이
        검색결과 정확명으로 바꿔둔 블록을 vid 로 찾아 재사용하기 위함(중복 블록 생성·시계열 단절 방지).
        """
        want = {str(v) for v in vids if v}
        if not want:
            return None
        for (b, p) in list(self._vid_row):
            if b == biz and want & set(self.product_vids(b, p)):
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
        ws.cell(header, _COL_NAME, new_name)
        self._metric_row = {((b, new_name, m) if (b == biz and p == product) else (b, p, m)): v
                            for (b, p, m), v in self._metric_row.items()}
        self._kw_row = {((b, new_name, kw) if (b == biz and p == product) else (b, p, kw)): v
                        for (b, p, kw), v in self._kw_row.items()}
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

    def set_keyword_rank(self, biz: str, product: str, keyword: str, date_iso: str,
                         rank: int | None) -> bool:
        row = self._kw_row.get((biz, product, keyword))
        if row is None:
            return False
        # 스캔 상한(RANK_SCAN_MAX) 안이면 그 순위, 밖(None)이면 상한값으로 고정(요청: 50위밖→50).
        val = f"{rank}위" if rank else f"{config.RANK_SCAN_MAX}위"
        self.wb[biz].cell(row=row, column=self.ensure_date(biz, date_iso), value=val)
        return True

    # ── 서식(셀독 서식 파일 재현: 병합·팔레트·테두리) ────────────
    # 사용자 `셀독 판매 데이터_서식.xlsx`(한컴 셀) 시각 서식을 재현한다. 행 스캔 방식이라
    # 계정(시트)·상품(블록)이 늘어도 자동 적용된다.
    _FN = "맑은 고딕"
    _FILL_PROD = "FBE2D5"     # 상품명(살구)
    _FILL_LABEL = "D9E9FA"    # G열 지표 라벨/순위(연파랑)
    _FILL_KWHEAD = "E8E8E8"   # 키워드 소헤더행(회색)
    _FILL_KIND = "FFFFFF"     # 구분(계약/개인)·사업자명(흰)
    _FILL_MKT = "FCE4D6"      # 마케팅 기간 일자 컬럼 배경(연주황 — 캠페인 구간 구분)

    def apply_style(self) -> None:
        # 서식 재적용 전에 일자 컬럼을 **시트별 첫날~마지막날 연속·날짜순**으로 정규화(빠진 날=날짜만 표기·값 공란).
        # 멱등·값 보존이라 결과파일 저장 때마다 시계열이 일자별로 끊기지 않게 유지된다(§'미실행 날짜=공란').
        self.normalize_date_columns()
        font = Font(name=self._FN, size=11)
        bold = Font(name=self._FN, size=11, bold=True)
        title_font = Font(name=self._FN, size=14, bold=True)
        f_prod = PatternFill("solid", fgColor=self._FILL_PROD)
        f_label = PatternFill("solid", fgColor=self._FILL_LABEL)
        f_kwhead = PatternFill("solid", fgColor=self._FILL_KWHEAD)
        f_kind = PatternFill("solid", fgColor=self._FILL_KIND)
        mkt_fill = PatternFill("solid", fgColor=self._FILL_MKT)   # 마케팅 기간(시작~종료) 일자 컬럼 배경
        thin = Side(style="thin", color="BFBFBF")
        box = Border(left=thin, right=thin, top=thin, bottom=thin)
        center = Alignment(horizontal="center", vertical="center")
        wrap = Alignment(horizontal="center", vertical="center", wrap_text=True)

        def cell(ws, r, c, *, fill=None, fnt=font, align=center, num=False):
            x = ws.cell(r, c)
            x.font = fnt
            x.alignment = align
            x.border = box
            if fill:
                x.fill = fill
            if num and isinstance(x.value, (int, float)):
                x.number_format = "#,##0"

        def merge(ws, r1, c1, r2, c2):
            if r2 > r1 or c2 > c1:
                ws.merge_cells(start_row=r1, start_column=c1, end_row=r2, end_column=c2)

        thick = Side(style="thick")

        def edge(ws, maxc, row, side):
            """상품 블록 경계(첫 행 상단/마지막 행 하단)에 굵은 선 — 상품 1개를 구분."""
            for c in range(1, maxc + 1):
                b = ws.cell(row, c).border
                ws.cell(row, c).border = Border(
                    left=b.left, right=b.right,
                    top=thick if side == "top" else b.top,
                    bottom=thick if side == "bottom" else b.bottom)

        for ws in self.wb.worksheets:
            if ws.title in _SPECIAL_SHEETS:              # 숨김 매핑·목차·계정정보 시트는 블록 서식 대상 아님
                continue
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
            t.font = title_font
            t.alignment = center
            t.border = Border(bottom=Side(style="medium"))
            merge(ws, 1, 1, 1, _COL_SEARCH - 1)       # 제목 A~E (F·G 는 목차 복귀 링크 자리)
            # ◀ 목차 복귀 링크(F1:G1) — 1행+A~G열은 틀고정이라 **어느 시트·어디로 스크롤해도 항상 보임**.
            # 탭이 많아 목차 탭이 탭바에서 밀려 안 보일 때, 여기 클릭 한 번으로 목차로 돌아간다(사용자 요청).
            back = ws.cell(1, _COL_SEARCH, f"👈 {_INDEX_SHEET}")   # 손가락(뒤로) + 명확한 문구
            back.hyperlink = Hyperlink(ref=back.coordinate, location=f"'{_INDEX_SHEET}'!A1")
            back.font = Font(name=self._FN, size=12, bold=True, color="FF0000")  # 빨간색 진하게(눈에 띄게)
            back.alignment = Alignment(horizontal="center", vertical="center")
            back.fill = PatternFill("solid", fgColor="FFF2CC")   # 옅은 노랑 강조 배경
            back.border = Border(bottom=Side(style="medium"))
            merge(ws, 1, _COL_SEARCH, 1, _COL_METRIC)  # F1:G1
            ws.row_dimensions[1].height = 21          # 제목행 높이(샘플 서식 고정값)
            ws.freeze_panes = "H2"                     # A~G열·1행 고정, H~ 일자만 스크롤
            # 표준 열너비: A11 B6 D9 E9 F13.75 G14. **C(상품명/키워드)만 full 제목이 보이도록 넓힘**
            # (사용자 요청: 이름칸 1줄=제목·2줄=vid, 제목 폭을 제목에 맞추기 — 기존 C10은 너무 좁았음).
            for c, w in {1: 11, 2: 6, 3: 36, 4: 9, 5: 9, 6: 13.75, 7: 14}.items():
                ws.column_dimensions[get_column_letter(c)].width = w
            for c in range(_FIRST_DATE, maxc + 1):
                ws.column_dimensions[get_column_letter(c)].width = 11
            headers = sorted(self._date_rows.get(ws.title, []))
            for i, hr in enumerate(headers):
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
                mcols: set[int] = set()
                _s, _e = _parse_date(mstart), _parse_date(mend)
                if _s:
                    for _lbl, _cc in self._date_col.get(ws.title, {}).items():
                        _d = _parse_date(_lbl)
                        if _d and _d >= _s and (not _e or _d <= _e):
                            mcols.add(_cc)
                kh = None                                   # 키워드 소헤더행(C='키워드'로 식별 — G는 비고/마케팅 표기에 씀)
                for r in range(hr, end + 1):
                    if _norm(ws.cell(r, _COL_NAME).value) == _LABEL_KEYWORD:
                        kh = r
                        break
                m_end = (kh - 1) if kh else end
                # 상품 지표블록: A:B 구분(살구=상품명색) · C:F 상품명(세로) · G 라벨 · H~ 값
                for r in range(hr, m_end + 1):
                    cell(ws, r, 1, fill=f_prod)
                    cell(ws, r, 2, fill=f_prod)
                    for c in range(_COL_NAME, _COL_SEARCH + 1):
                        cell(ws, r, c, fill=f_prod, fnt=bold, align=wrap)
                    cell(ws, r, _COL_METRIC, fill=f_label)
                    for c in range(_FIRST_DATE, maxc + 1):
                        cell(ws, r, c, num=True, fill=(mkt_fill if c in mcols else None))
                # 키워드블록: A:B 사업자(세로) · C:E 키워드명(가로) · F 검색량 · G(소헤더 비고=회색/순위라벨=연파랑) · H~ 순위
                if kh:
                    for r in range(kh, end + 1):
                        head = (r == kh)
                        cell(ws, r, 1, fill=f_kind)
                        cell(ws, r, 2, fill=f_kind)
                        for c in range(_COL_NAME, _COL_SEARCH):     # C~E 키워드명(항상 bold)
                            cell(ws, r, c, fill=(f_kwhead if head else None), fnt=bold, align=wrap)
                        cell(ws, r, _COL_SEARCH, fill=(f_kwhead if head else None), num=not head)
                        cell(ws, r, _COL_METRIC, fill=(f_kwhead if head else f_label))
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
                            cell(ws, r, c, fill=(mkt_fill if c in mcols else None))
                # 상품 1개 구분 — 굵은 선. 상단=블록 첫 행 top(병합 top-left라 정상).
                # 하단=다음(빈) 구분행의 top(시각적으로 마지막 행 하단선). ⚠ 마지막 블록은 end+1 행이
                # 없어서 거기 테두리를 그리면 **빈 행이 새로 생긴다**(2상품 시트의 2번째 블록 하단 공백줄 버그).
                # → 마지막 블록은 end 행 자체의 bottom 에 그려 새 행을 만들지 않는다.
                edge(ws, maxc, hr, "top")
                if i + 1 < len(headers):
                    edge(ws, maxc, end + 1, "top")     # 사이 블록: 기존 구분 빈 행 상단선(비병합 행이라 정상)
                # 병합(마지막) — 세로/가로 병합은 서식·경계선 적용 뒤에
                merge(ws, hr, 1, m_end, 2)
                merge(ws, hr, _COL_NAME, m_end, _COL_SEARCH)
                if kh:
                    merge(ws, kh, 1, end, 2)
                    for r in range(kh, end + 1):
                        merge(ws, r, _COL_NAME, r, _COL_SEARCH - 1)
                # 마지막 블록 하단 굵은선(새 행 안 만듦). ⚠ openpyxl 은 **세로 병합의 하단 테두리를
                # '앵커(top-left) 셀'의 border 로 렌더**한다 → 마지막행 셀에 그려도 A:B 세로병합(col1·2)은
                # 얇게 남던 버그(사용자 관찰). 그래서 단일셀·가로병합은 마지막행에, A:B 세로병합은 그 앵커
                # (kh 또는 hr, col1)에 굵은 하단선을 지정한다.
                if i + 1 >= len(headers):
                    edge(ws, maxc, end, "bottom")       # 단일셀 + 가로병합(C:E, 앵커=마지막행) 하단
                    ab_row = kh if kh else hr           # A:B 세로병합 앵커 행
                    ab = ws.cell(ab_row, 1).border
                    ws.cell(ab_row, 1).border = Border(left=ab.left, right=ab.right,
                                                       top=ab.top, bottom=thick)
                    if not kh:                          # 키워드 없는 블록: C:F 세로병합 앵커도
                        cf = ws.cell(hr, _COL_NAME).border
                        ws.cell(hr, _COL_NAME).border = Border(left=cf.left, right=cf.right,
                                                               top=cf.top, bottom=thick)
        self._build_index()   # 전 계정 요약·점프 링크의 '목차' 시트를 맨 앞에 재생성(멱등)

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
        """그 상품이 값을 가진 가장 최근(오른쪽) 일자 라벨(없으면 ''). 상품별 3일주기 판정용."""
        cols = self._date_col.get(biz, {})
        if not cols or biz not in self.wb.sheetnames:
            return ""
        ws = self.wb[biz]
        best, best_c = "", -1
        for m in _ALL_METRICS:
            row = self._metric_row.get((biz, product, m))
            if row is None:
                continue
            for lbl, c in cols.items():
                if c > best_c and ws.cell(row, c).value not in (None, ""):
                    best, best_c = lbl, c
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
        """계정목록 상태 열(G) 값 — openpyxl `_build_index` 규칙과 동일:
        판매중지 > (미수집) > 체험단 상태(예정/체험단중/모니터링/종료/'')."""
        if has_sheet and product and self.is_discontinued(biz, product):
            return "⛔ 판매중지"
        if not has_sheet:
            return "미수집"
        s, e, m = self.marketing_of(biz, product)
        return self._mkt_status(s, e, m)

    def _product_rows(self) -> list[tuple[str, str, int | None, bool]]:
        """계정 목록에 실을 상품 로스터 — (사업자, 상품, 그 상품 블록 헤더행|None, 데이터시트有無).
        수집된 계정의 상품들 먼저(계정→상품 순), 그 뒤 미수집 계정(상품='')."""
        rows: list[tuple[str, str, int | None, bool]] = []
        for biz in self.account_sheets():
            hdr: dict[str, int] = {}
            for r in self._date_rows.get(biz, []):
                nm = _key(self.wb[biz].cell(r, _COL_NAME).value)
                if nm:
                    hdr.setdefault(nm, r)
            prods = self.products_of(biz)
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
        레이아웃 고정: 3행부터 A=사업자 B=상품 D=시작 E=종료 F=모니터링종료."""
        if _INDEX_SHEET not in self.wb.sheetnames:
            return
        ws = self.wb[_INDEX_SHEET]
        if _norm(ws.cell(2, 4).value) not in (_MKT_COLS[0], _MKT_COLS_LEGACY0):   # 현재/옛 라벨 레이아웃만 회수
            return
        for r in range(3, ws.max_row + 1):
            biz = _norm(ws.cell(r, 1).value)
            prod = _key(ws.cell(r, 2).value)
            if not biz:
                continue
            start, end, mon = (_norm(ws.cell(r, 4).value), _norm(ws.cell(r, 5).value),
                               _norm(ws.cell(r, 6).value))
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
        font = Font(name=self._FN, size=11)
        bold = Font(name=self._FN, size=11, bold=True)
        link_font = Font(name=self._FN, size=11, color="0563C1", underline="single")
        gray_font = Font(name=self._FN, size=11, color="9AA7B6")   # 미수집(옅게)
        red_bold = Font(name=self._FN, size=11, bold=True, color="C00000")   # 체험단중 상태
        title_font = Font(name=self._FN, size=14, bold=True)
        thin = Side(style="thin", color="BFBFBF")
        box = Border(left=thin, right=thin, top=thin, bottom=thin)
        center = Alignment(horizontal="center", vertical="center")
        left = Alignment(horizontal="left", vertical="center")
        head_fill = PatternFill("solid", fgColor=self._FILL_LABEL)
        mkt_fill = PatternFill("solid", fgColor="FFF2CC")   # 마케팅 입력열 강조(입력 자리 안내)
        n_prod = sum(1 for _b, p, _h, hs in rows if hs and p)

        ws.cell(1, 1, f"{_INDEX_SHEET} · 상품 {n_prod}개").font = title_font
        ws.merge_cells("A1:G1")
        ws.cell(1, 1).alignment = center
        # 마케팅 3열은 **관리대장에서 입력**(원본) → 여기선 표시. 헤더 안내로 (관리대장) 표기.
        heads = ["사업자", "상품명(클릭 이동)", "계정ID",
                 _MKT_COLS[0], _MKT_COLS[1], _MKT_COLS[2], "상태"]
        for c, h in enumerate(heads, 1):
            x = ws.cell(2, c, h)
            x.font = bold; x.alignment = center; x.border = box
            x.fill = mkt_fill if 4 <= c <= 6 else head_fill   # 4~6열=마케팅(관리대장 값 표시)
        for r, (biz, prod, hdr, has_sheet) in enumerate(rows, start=3):
            ws.cell(r, 1, biz).font = font if has_sheet else gray_font
            pcell = ws.cell(r, 2, prod if prod else ("(미수집)" if not has_sheet else "(상품없음)"))
            if has_sheet and prod and hdr:      # 상품 블록으로 점프(헤더행)
                pcell.hyperlink = Hyperlink(ref=pcell.coordinate,
                                            location=f"'{biz.replace(chr(39), chr(39) * 2)}'!A{hdr}")
                pcell.font = link_font
            else:
                pcell.font = gray_font
            ws.cell(r, 3, self.account_id_of(biz)).font = font if has_sheet else gray_font
            start, end, mon = self.marketing_of(biz, prod)
            if has_sheet and prod and self.is_discontinued(biz, prod):
                status = "⛔ 판매중지"
            else:
                status = self._mkt_status(start, end, mon) if has_sheet else "미수집"
            for c, v in ((4, start), (5, end), (6, mon)):   # 마케팅(관리대장 값 표시)
                x = ws.cell(r, c, v); x.font = font; x.alignment = center; x.border = box; x.fill = mkt_fill
            st = ws.cell(r, 7, status); st.alignment = center; st.border = box
            st.font = (red_bold if status == "체험단중"
                       else (gray_font if status in ("미수집", "종료", "⛔ 판매중지") else font))
            for c in (1, 2, 3):
                ws.cell(r, c).alignment = left if c == 2 else center
                ws.cell(r, c).border = box
        for c, w in {1: 22, 2: 40, 3: 15, 4: 13, 5: 13, 6: 14, 7: 10}.items():
            ws.column_dimensions[get_column_letter(c)].width = w
        ws.row_dimensions[1].height = 21
        ws.freeze_panes = "D3"                            # 제목·헤더 + 사업자/상품/계정ID 고정(가로 스크롤 시)
        # '항상 고정': 첫 탭(index 0) + **파일 열면 항상 목차가 선택된 채로 열리게** 활성 시트로 지정.
        try:
            self.wb.active = self.wb.index(ws)
            for other in self.wb.worksheets:             # 다른 시트 탭 선택 해제(목차만 활성)
                other.sheet_view.tabSelected = (other is ws)
        except Exception:
            pass
