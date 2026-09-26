"""워크북 목차(_build_index)·체험단효과(promo_effect) mixin — 렌더링에서 다시 분리.

`class OutputWorkbook(_RenderMixin, _IndexMixin)` 로 합쳐져 self 로 접근. workbook_common 재노출 사용.
"""
from __future__ import annotations

from .workbook_common import *  # noqa: F401,F403


class _IndexMixin:
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

        parts: list[str] = []
        score = 0
        srow = self._metric_row.get((biz, product, config.M_SALES))
        s_part, s_score = self._promo_sales_part(ws, srow, dated, start_d)
        if s_part:
            parts.append(s_part); score += s_score
        r_part, r_score = self._promo_rank_part(biz, product, dated, start_d)
        if r_part:
            parts.append(r_part); score += r_score
        if not parts:
            return "", ""                                   # 판매·순위 둘 다 데이터 부족 → 공란
        return " · ".join(parts), ("up" if score > 0 else "down" if score < 0 else "")

    @staticmethod
    def _promo_series_ba(dated: list[tuple], start_d, getter) -> tuple:
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

    def _promo_sales_part(self, ws, srow, dated: list[tuple], start_d) -> tuple[str, int]:
        """체험단 효과 판매 부분 — (표시문자열 또는 '', 점수증분)."""
        if not srow:
            return "", 0
        sb, sa = self._promo_series_ba(dated, start_d, lambda c: self._cell_num(ws, srow, c))
        if sb is not None and sa is not None and sb > 0:
            pct = round((sa - sb) / sb * 100)
            return f"판매 {pct:+d}%", (1 if pct > 0 else -1 if pct < 0 else 0)
        return "", 0

    def _promo_rank_part(self, biz: str, product: str, dated: list[tuple], start_d) -> tuple[str, int]:
        """체험단 효과 순위 부분 — 모든 키워드 최고 순위(숫자 최소) before→after. (표시문자열 또는 '', 점수증분)."""
        rb, ra = self._promo_series_ba(dated, start_d, lambda c: self._best_rank_at(biz, product, c))
        if rb is not None and ra is not None:
            arrow = "↑" if ra < rb else ("↓" if ra > rb else "→")   # 순위 숫자↓ = 상위 노출 = 개선
            return f"순위 {rb}→{ra} {arrow}", (1 if ra < rb else -1 if ra > rb else 0)
        return "", 0

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
        # 열(항목④): 1 대표자 · 2 사업자 · 3 계정ID · 4 상품명 · 5~7 체험단(관리대장 입력·표시) · 8 상태 · 9 체험단효과.
        heads = ["대표자", "사업자", "계정ID", "상품명(클릭 이동)",
                 _MKT_COLS[0], _MKT_COLS[1], _MKT_COLS[2], "상태", "체험단효과"]
        for c, h in enumerate(heads, 1):
            x = ws.cell(2, c, h)
            x.font = bold; x.alignment = center; x.border = box
            x.fill = mkt_fill if 5 <= c <= 7 else head_fill   # 5~7열=마케팅(관리대장 값 표시)
        for r, (biz, prod, hdr, has_sheet) in enumerate(rows, start=3):
            self._index_row(ws, r, biz, prod, hdr, has_sheet, sty)
        # 항목④: 셀 폭 **내용 길이 기반 자동맞춤**(구글 패리티). 헤더+데이터 최장 길이(한글=2폭)로 열별
        # min~max 클램프. 마케팅 5~7(직원 입력)은 고정. 3=계정ID·4=상품명(스왑 반영).
        def _dl(v) -> int:
            return sum(2 if ord(ch) > 0x2000 else 1 for ch in str(v)) if v is not None else 0
        _wmin = {1: 10, 2: 12, 3: 10, 4: 16, 8: 8, 9: 14}
        _wmax = {1: 20, 2: 30, 3: 20, 4: 55, 8: 16, 9: 32}
        _wfix = {5: 13, 6: 13, 7: 14}
        for c in range(1, 10):
            if c in _wfix:
                ws.column_dimensions[get_column_letter(c)].width = _wfix[c]
                continue
            longest = max((_dl(ws.cell(r, c).value) for r in range(2, ws.max_row + 1)), default=0)
            ws.column_dimensions[get_column_letter(c)].width = min(_wmax[c], max(_wmin[c], longest + 2))
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
        base = sty.font if has_sheet else sty.gray_font
        ws.cell(r, 1, self.representative_of(biz)).font = base
        ws.cell(r, 2, biz).font = base
        # 항목④: C=계정ID(상품명 왼쪽) · D=상품명(점프 링크). 항목5: 계정ID=상품별(다계정ID)·없으면 첫 계정ID 폴백.
        acct = (self.product_account_id(biz, prod) if prod else "") or self.account_id_of(biz)
        ws.cell(r, 3, acct).font = base
        self._idx_name_cell(ws, r, biz, prod, hdr, has_sheet, sty)
        start, end, mon = self.marketing_of(biz, prod)
        status = self._idx_status(biz, prod, has_sheet, start, end, mon)
        for c, v in ((5, start), (6, end), (7, mon)):   # 마케팅(관리대장 값 표시)
            x = ws.cell(r, c, v)
            x.font = sty.font; x.alignment = sty.center; x.border = sty.box; x.fill = sty.mkt_fill
        st = ws.cell(r, 8, status); st.alignment = sty.center; st.border = sty.box
        _gray = ("미수집", "종료", "⛔ 판매중지", "판매중지", "임시저장", "승인반려")   # 미판매/비활성 = 옅게
        st.font = sty.red_bold if status == "체험단중" else (sty.gray_font if status in _gray else sty.font)
        self._idx_promo_cell(ws, r, biz, prod, has_sheet, sty)
        for c in (1, 2, 3, 4):
            ws.cell(r, c).alignment = sty.left if c == 3 else sty.center
            ws.cell(r, c).border = sty.box

    def _idx_name_cell(self, ws, r: int, biz: str, prod: str, hdr, has_sheet: bool, sty: _IdxStyle) -> None:
        """D열 상품명 셀 — 있으면 상품 블록 헤더로 점프 링크, 없으면 (미수집)/(상품없음)."""
        pcell = ws.cell(r, 4, prod if prod else ("(미수집)" if not has_sheet else "(상품없음)"))
        if has_sheet and prod and hdr:      # 상품 블록으로 점프(헤더행)
            pcell.hyperlink = Hyperlink(ref=pcell.coordinate,
                                        location=f"'{biz.replace(chr(39), chr(39) * 2)}'!A{hdr}")
            pcell.font = sty.link_font
        else:
            pcell.font = sty.gray_font

    def _idx_status(self, biz: str, prod: str, has_sheet: bool, start, end, mon) -> str:
        """H열 상태 — 판매중지(대장) > 마케팅 상태 > 미수집."""
        if has_sheet and prod and self.is_discontinued(biz, prod):
            return "⛔ 판매중지"
        return self._mkt_status(start, end, mon) if has_sheet else "미수집"

    def _idx_promo_cell(self, ws, r: int, biz: str, prod: str, has_sheet: bool, sty: _IdxStyle) -> None:
        """I열 체험단효과 — 시작일 직전→최신 비교, 개선=연초록·악화=연적색."""
        eff, verdict = self.promo_effect(biz, prod) if has_sheet else ("", "")   # 9열 체험단효과(시작일 직전→최신)
        pe = ws.cell(r, 9, eff); pe.alignment = sty.center; pe.border = sty.box; pe.font = sty.font
        if verdict == "up":
            pe.fill = PatternFill("solid", fgColor="C9E6C9")   # 개선=연초록
        elif verdict == "down":
            pe.fill = PatternFill("solid", fgColor="F4CCCC")   # 악화=연적색
