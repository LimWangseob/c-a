"""워크북 렌더링 mixin — apply_style·서식·목차(_build_index)·체험단효과·마이그레이션.

workbook.py(OutputWorkbook)에서 분리(대형 파일 정비, 행동 불변). `class OutputWorkbook(_RenderMixin)` 로
합쳐져 self(데이터/인덱스 상태·메서드)에 접근한다. 상수·헬퍼·서식 dataclass·openpyxl 은 workbook_common 재노출.
tools 는 OutputWorkbook 을 블랙박스로만 쓰므로 monkeypatch 재배선 없음(핀 pin_apply_style·verify_render 가 렌더 oracle).
"""
from __future__ import annotations

from .workbook_common import *  # noqa: F401,F403


class _RenderMixin:
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
        sub_g = {_LABEL_NOTE, "판매중", "⛔ 판매중지", "🔴 체험단중"}   # 비고 자리=관리대장 판매상태(항목3) 포함
        moved = False
        for ws in self.wb.worksheets:
            if ws.title in _SPECIAL_SHEETS:
                continue
            targets = self._kw_migrate_targets(ws, sub_g)
            if not targets:
                continue
            self._apply_kw_migrate(ws, targets)
            moved = True
        if moved:
            self._reindex()

    def _kw_migrate_targets(self, ws, sub_g: set) -> list[tuple[int, str]]:
        """(a) 옛 C→A 키워드행/소헤더 + (b) 손상 소헤더 자가복원 대상 (행, A에 쓸 값) 수집."""
        targets: list[tuple[int, str]] = []
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
        return targets

    def _apply_kw_migrate(self, ws, targets: list[tuple[int, str]]) -> None:
        """수집된 (행, A값) 을 A열에 쓰고 옛 C값을 정리(병합 해제 후·apply_style 재병합)."""
        _unmerge_all(ws)                                       # 병합 해제 후 쓰기(apply_style 재병합)
        for r, val in targets:
            ws.cell(r, _COL_KW, val)                          # A ← 키워드명/'키워드'
            if val == _LABEL_KEYWORD and not _norm(ws.cell(r, _COL_SEARCH).value):
                ws.cell(r, _COL_SEARCH, _LABEL_SEARCH)        # 소헤더 '검색량' 제목 복원(F열 공란 방지)
            if val != _LABEL_KEYWORD or _norm(ws.cell(r, _COL_NAME).value) == _LABEL_KEYWORD:
                ws.cell(r, _COL_NAME).value = None            # 옛 C값(키워드명/'키워드') 비움(v4는 A가 앵커)

    def _clear_blank_keyword_ranks(self) -> None:
        """빈(이름 공란) 키워드 순위행에 남은 낡은 순위값을 지운다(항목5·2026-09-26·소유자·실측 43행).

        ensure_product_block 이 KW_TRACK_N 유지용으로 만든 **이름 공란 M_RANK 행**에, 과거 실행이 잘못
        기록했거나 키워드가 나중에 삭제돼 비워진 뒤에도 옛 순위값('50위' 등)이 일자칸에 남아 '키워드 없는데
        노출순위 표기'로 보이던 문제를 치유한다. 이름 있는 키워드행은 건드리지 않는다.
        멱등(이미 공란이면 no-op)·값만 삭제(구조·행수 불변)라 재인덱스 불필요."""
        for ws in self.wb.worksheets:
            if ws.title in _SPECIAL_SHEETS:
                continue
            biz = ws.title
            mc = ws.max_column
            for p in self.products_of(biz):
                for r, name in self._kw_block_rows(biz, p):
                    if name:                                  # 이름 있는 키워드행 = 보존
                        continue
                    for c in range(_FIRST_DATE, mc + 1):      # 일자칸(H~)만 비움(A~G 라벨 불변)
                        if ws.cell(r, c).value not in (None, ""):
                            ws.cell(r, c).value = None

    def _backfill_metric_rows(self) -> None:
        """옛 블록에 빠진 **판매가·판매상태**(+로켓그로스면 재고현황) 지표행을 보정한다(항목4/6·2026-09-26).

        판매가·판매상태는 2026-09-24 신설이라 그 이전 마스터 블록엔 없다. 파이프라인이 방문하는 상품은
        ensure_product_block 이 이미 보정하지만, 대장에서 빠진(판매중지)·미로그인 계정처럼 **파이프라인이
        방문하지 않는 옛 블록**은 지표행이 계속 비어(실측 13블록) 담당자가 판매가·판매상태를 볼 수 없었다.
        저장(apply_style)마다 전 블록을 훑어 없는 행만 끼워 넣어(순서=재고<판매가<판매상태) 자동 치유한다.
        재고는 판매방식이 로켓그로스/둘다(KINDS_WITH_INVENTORY)일 때만(옛 kind='' 미상 블록엔 강제 안 함).
        멱등(_add_metric_row 가 이미 있으면 미진입·행 삽입 시 재인덱스)."""
        for biz in self.account_sheets():
            for p in self.products_of(biz):
                kind = self.product_kind(biz, p)
                if (kind in config.KINDS_WITH_INVENTORY
                        and (biz, p, config.M_INVENTORY) not in self._metric_row):
                    self._add_metric_row(biz, p, config.M_INVENTORY)
                if (biz, p, config.M_SALE_PRICE) not in self._metric_row:
                    self._add_metric_row(biz, p, config.M_SALE_PRICE)
                if (biz, p, config.M_SALE_STATUS) not in self._metric_row:
                    self._add_metric_row(biz, p, config.M_SALE_STATUS)

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
        regs = [self._group_key(ws.cell(h, _COL_NAME).value) for h in headers]   # 상품군=블록명 base(2026-09-26)
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
        snaps = self._snapshot_blocks(ws, headers, last_data, maxc)
        self._rewrite_blocks(ws, headers, last_data, desired, snaps, maxc)
        return True

    def _snapshot_blocks(self, ws, headers: list[int], last_data: int, maxc: int) -> list[list[list]]:
        """블록별 값 스냅샷(꼬리 빈 행 제거) — 재배치 전에 값을 떠 둔다."""
        snaps: list[list[list]] = []
        for i, h in enumerate(headers):
            stop = headers[i + 1] if i + 1 < len(headers) else last_data + 1
            rows = list(range(h, stop))
            while len(rows) > 1 and all(_norm(ws.cell(rows[-1], c).value) == "" for c in range(1, maxc + 1)):
                rows.pop()
            snaps.append([[ws.cell(r, c).value for c in range(1, maxc + 1)] for r in rows])
        return snaps

    def _rewrite_blocks(self, ws, headers: list[int], last_data: int,
                        desired: list[int], snaps: list[list[list]], maxc: int) -> None:
        """블록 영역을 비우고 desired 순서로 재기록(블록 사이 빈 줄 1). 병합은 apply_style 이 뒤에서 재생성."""
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
        self._backfill_metric_rows()   # 옛 블록에 빠진 판매가·판매상태(+로켓그로스 재고) 지표행 보정(항목4/6)
        self._clear_blank_keyword_ranks()  # 빈 키워드행에 남은 낡은 순위값 삭제(항목5)
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
        # 엑셀 하단 시트 탭 표시 보장(일부 파일서 탭이 숨겨져 보이던 문제)·목차를 활성 시트로
        for _v in self.wb.views:
            _v.showSheetTabs = True
            _v.visibility = "visible"
            _v.activeTab = 0

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
        # 제목에 (대표자, 사업자, 계정ID) — **값만** 표기(라벨 제외·소유자 2026-09-26 순서 확정). 빈 항목은 생략.
        # 다계정ID 사업자(항목5)는 계정ID를 ' / ' 로 모두 표기(account_ids_of).
        _accts = " / ".join(self.account_ids_of(ws.title))
        _parts = [x for x in (self.representative_of(ws.title), ws.title, _accts) if x]
        t.value = f"{config.SELDOC_SHEET_TITLE}({', '.join(_parts)})"
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
        regs = [self._group_key(ws.cell(hr, _COL_NAME).value) for hr in headers]   # 상품군=블록명 base(2026-09-26)
        # 상품군(블록명 base) 교대 배경색: 같은 base(기본+옵션·수량 1/2/3개·판매방식 twin) = 한 군(연속) → 인접 상품군을 두 색으로
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
            c_name = ws.cell(hr, _COL_NAME)
            c_name.value = self._display_name(ws.title, nm)
            # 항목3(2026-09-26): 상품명 클릭 → **쿠팡 노출상품** 새 창(하이퍼링크). productId 있으면 정확 페이지,
            # 없으면 노출명 검색 폴백. 멱등(매 apply_style 재설정). 서식은 _style_metric_rows 가 이어서 입힌다.
            url = self.product_url(ws.title, nm)
            c_name.hyperlink = Hyperlink(ref=c_name.coordinate, target=url)
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
            if head:   # 비고 자리(소헤더 G)=관리대장 판매상태(항목3·소유자 2026-09-26): 판매중지 > 체험단중 > 판매중
                # 대장에서 빠짐=판매중지, 아니면 판매중(대장에 존재). 체험단중은 판매중의 마케팅 오버레이라
                # 그대로 유지(체험단=판매중 상태). 옛 '비고' 라벨은 폐지(담당자가 한눈에 판매상태 파악).
                gm = ws.cell(r, _COL_METRIC)
                if is_disc:
                    gm.value = "⛔ 판매중지"
                    gm.font = Font(name=self._FN, size=11, bold=True, color="808080")
                elif is_mkt:
                    gm.value = "🔴 체험단중"
                    gm.font = Font(name=self._FN, size=11, bold=True, color="C00000")
                else:
                    gm.value = "판매중"
                    gm.font = sty.bold
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
