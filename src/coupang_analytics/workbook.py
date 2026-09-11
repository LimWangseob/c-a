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

from pathlib import Path

import openpyxl
from openpyxl.cell.cell import Cell
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

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


def _norm(v) -> str:
    return str(v).strip() if v is not None else ""


def _key(v) -> str:
    """이름칸 셀 값 → **상품 키**(순수 상품명). 표시용으로 붙은 `⟨SEP⟩<vendorItemId>` 꼬리를 떼어낸다.

    상품 정체성(시계열 키)은 항상 구분자(`config.NAME_ID_SEP`) 앞부분이다. 구분자가 없으면(순수 이름·
    키워드 셀) `_norm` 과 동일하게 동작해 기존 키를 그대로 보존한다. 상품명 내부 개행은 손대지 않는다."""
    return _norm(v).split(config.NAME_ID_SEP, 1)[0]


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
        """계정(사업자) 시트명 목록 — 상품ID 숨김 시트는 제외."""
        return [s for s in self.wb.sheetnames if s != _META_SHEET]

    def is_rank_filled(self, biz: str, product: str, keyword: str, date_iso: str) -> bool:
        row = self._kw_row.get((biz, product, keyword))
        col = self._date_col.get(biz, {}).get(date_iso)
        if row is None or col is None:
            return False
        # '-'(구 미측정/스캔밖 placeholder)는 미채움으로 봐 ③ 재실행이 다시 측정하게 한다
        # (새 규칙에선 스캔밖=50위로 기록하므로 '-'는 측정 안 된 잔재).
        return self.wb[biz].cell(row=row, column=col).value not in (None, "", "-")

    # ── 생성 ─────────────────────────────────────────────────
    def ensure_account(self, biz: str):
        if biz in self.wb.sheetnames:
            return self.wb[biz]
        ws = self.wb.create_sheet(title=biz[:31])   # 엑셀 시트명 31자 제한
        ws.cell(1, 1, config.SELDOC_SHEET_TITLE)
        self._date_col[biz] = {}
        self._date_rows[biz] = []
        return ws

    def ensure_product_block(self, biz: str, product: str, kind: str, keywords: list[str]) -> None:
        """상품 블록이 없으면 생성(계약=CONTRACT_METRICS/개인=PERSONAL_METRICS + 키워드 순위행)."""
        if self.has_product(biz, product):
            return
        ws = self.ensure_account(biz)
        metrics = config.CONTRACT_METRICS if kind == config.KIND_CONTRACT else config.PERSONAL_METRICS
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
        for kw in dict.fromkeys(keywords):
            r += 1
            ws.cell(r, _COL_NAME, kw)
            ws.cell(r, _COL_METRIC, config.M_RANK)
            self._kw_row[(biz, product, kw)] = r

    def add_product_keywords(self, biz: str, product: str, keywords: list[str]) -> list[str]:
        """기존 상품 블록에 새 키워드 순위행 추가(통계 유지 중 발굴 추가). 반환: 실제 추가분.

        블록 끝(다음 상품 헤더 직전)에 삽입하기 어려우므로, 순위행을 그 상품의 마지막 키워드행 아래에
        openpyxl insert_rows 로 끼워 넣고 인덱스를 재구성한다. 없던 키워드만 추가.
        """
        have = set(self.product_keywords(biz, product))
        add = [kw for kw in dict.fromkeys(keywords) if kw and kw not in have]
        if not add:
            return []
        ws = self.wb[biz]
        # ⚠ insert_rows 는 병합셀이 있으면 데이터(상품명·키워드)를 손상시킨다 → 삽입 전 병합 전부 해제
        # (호출부가 이후 apply_style 로 표준 재병합). 이게 run1 계정 이름/키워드 유실의 근본 원인이었음.
        _unmerge_all(ws)
        # 기존 키워드 있으면 그 마지막 행 아래, 없으면(② 단계로 처음 채움) 소헤더행(마지막 지표행+1) 아래
        last_kw_row = max(self._kw_row[(biz, product, kw)] for kw in have) if have else \
            (max(self._metric_row[(biz, product, m)] for m in _ALL_METRICS
                 if (biz, product, m) in self._metric_row) + 1)
        ws.insert_rows(last_kw_row + 1, amount=len(add))
        for i, kw in enumerate(add, 1):
            row = last_kw_row + i
            ws.cell(row, _COL_NAME, kw)
            ws.cell(row, _COL_METRIC, config.M_RANK)
        self._reindex()   # 행 이동됐으니 전체 재인덱스(정확성 우선)
        return add

    # ── 일자 컬럼 ────────────────────────────────────────────
    def ensure_date(self, biz: str, date_iso: str) -> int:
        cols = self._date_col.setdefault(biz, {})
        if date_iso in cols:
            return cols[date_iso]
        col = max(cols.values(), default=_FIRST_DATE - 1) + 1
        cols[date_iso] = col
        ws = self.wb[biz]
        for r in self._date_rows.get(biz, []):    # 모든 날짜 헤더행에 라벨 기록(블록마다 헤더 반복)
            ws.cell(r, col, date_iso)
        return col

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

    def _display_name(self, biz: str, name: str) -> str:
        """이름칸 표시값 = **1줄 상품제목 + (보이지 않는 구분자) + 2줄 상품 인식코드(vendorItemId)**.

        키(순수 상품명 `name`)는 건드리지 않고 표시용 꼬리만 만든다. vid 없으면 이름만(1줄). 여러 옵션이면
        vid 를 '/' 로 이어 붙인다. `apply_style` 이 저장 직전 이 값으로 헤더 C셀을 렌더링(멱등)."""
        vids = self.product_vids(biz, name)
        if not vids:
            return name
        return f"{name}{config.NAME_ID_SEP}\n{' / '.join(vids)}"

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

    def apply_style(self) -> None:
        font = Font(name=self._FN, size=11)
        bold = Font(name=self._FN, size=11, bold=True)
        title_font = Font(name=self._FN, size=14, bold=True)
        f_prod = PatternFill("solid", fgColor=self._FILL_PROD)
        f_label = PatternFill("solid", fgColor=self._FILL_LABEL)
        f_kwhead = PatternFill("solid", fgColor=self._FILL_KWHEAD)
        f_kind = PatternFill("solid", fgColor=self._FILL_KIND)
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
            if ws.title == _META_SHEET:                 # 상품ID 숨김 시트는 서식 대상 아님
                continue
            # 멱등화: 기존 병합을 모두 해제한 뒤 아래에서 표준대로 다시 병합한다.
            # (②/③/반영 등이 서식 없이 셀을 추가해 병합·테두리가 시트마다 섞이는 것을 원천 제거 →
            #  apply_style 을 몇 번 돌려도 항상 '첫 시트 표준' 하나로 고정됨.)
            _unmerge_all(ws)
            maxc = ws.max_column
            t = ws.cell(1, 1)
            t.font = title_font
            t.alignment = center
            t.border = Border(bottom=Side(style="medium"))
            merge(ws, 1, 1, 1, _COL_METRIC)           # 제목은 고정영역(A~G)만, H~ 일자 제외
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
                kh = None                                   # 키워드 소헤더행
                for r in range(hr, end + 1):
                    if (_norm(ws.cell(r, _COL_NAME).value) == _LABEL_KEYWORD
                            and _norm(ws.cell(r, _COL_METRIC).value) == _LABEL_NOTE):
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
                        cell(ws, r, c, num=True)
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
                        for c in range(_FIRST_DATE, maxc + 1):
                            cell(ws, r, c)
                # 상품 1개 구분 — 굵은 선. 상단=블록 첫 행 top(병합 top-left라 정상).
                # 하단=다음(빈) 구분행의 top(시각적으로 마지막 행 하단선). ⚠ 마지막 블록은 end+1 행이
                # 없어서 거기 테두리를 그리면 **빈 행이 새로 생긴다**(2상품 시트의 2번째 블록 하단 공백줄 버그).
                # → 마지막 블록은 end 행 자체의 bottom 에 그려 새 행을 만들지 않는다.
                edge(ws, maxc, hr, "top")
                if i + 1 < len(headers):
                    edge(ws, maxc, end + 1, "top")     # 사이 블록: 기존 구분 빈 행 상단선
                else:
                    edge(ws, maxc, end, "bottom")       # 마지막 블록: 마지막 행 하단선(새 행 안 만듦)
                # 병합(마지막) — 세로/가로 병합은 서식·경계선 적용 뒤에
                merge(ws, hr, 1, m_end, 2)
                merge(ws, hr, _COL_NAME, m_end, _COL_SEARCH)
                if kh:
                    merge(ws, kh, 1, end, 2)
                    for r in range(kh, end + 1):
                        merge(ws, r, _COL_NAME, r, _COL_SEARCH - 1)
