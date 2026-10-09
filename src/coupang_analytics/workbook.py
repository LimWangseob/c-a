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

# 상수·헬퍼·서식 dataclass·openpyxl 재노출은 leaf 모듈 workbook_common 으로 분리(순환 방지).
from .workbook_render import _RenderMixin  # 렌더링 mixin(apply_style·서식)
from .workbook_index import _IndexMixin    # 목차·체험단효과 mixin
from .workbook_meta import _MetaMixin      # 숨김 메타시트(상품 속성) mixin
from .workbook_dates import _DateMixin     # 날짜 칸·수집 이력·측정 주기 mixin
from .workbook_common import *  # noqa: F401,F403
from .workbook_common import (  # 명시 재확인(정적검사 가독성)
    _COL_KW, _COL_METRIC, _COL_NAME, _COL_SEARCH, _FIRST_DATE, _META_SHEET, _SPECIAL_SHEETS,
    _norm, _key)


class OutputWorkbook(_RenderMixin, _IndexMixin, _MetaMixin, _DateMixin):
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
        # 회사보유재고(판매자배송 자체재고) — 매 실행 재고현황 시트에서 주입(company_stock.apply_to_workbook).
        # 계정목록 렌더 전용·마스터에 저장 안 함(재로드 시 비고, 다음 실행이 재주입). {(사업자,상품): '창고 , 수량개'}.
        self._company_stock: dict[tuple[str, str], str] = {}
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
        self._block_vids.clear(); self._company_stock.clear()
        # vid 출처(A안, 레이아웃 v4)=숨김 메타시트 `_상품ID` col3. 헤더 이름칸 꼬리는 옛 마스터 폴백용.
        # 메타시트가 계정시트 뒤에 올 수 있어 **먼저 한 번** 스캔해 {(사업자,상품): [vid…]} 를 만든다.
        meta_vids = self._scan_meta_vids()
        for ws in self.wb.worksheets:
            if ws.title in (_INDEX_SHEET, _ACCT_SHEET, _STAMP_SHEET, _MKT_SHEET, _DISC_SHEET):  # 특수시트 = 데이터 아님
                continue
            if ws.title == _META_SHEET:                 # 상품ID 매핑 시트 → 행 인덱스만 복원
                self._reindex_meta_rows(ws)
                continue
            self._reindex_sheet(ws, meta_vids)

    def _scan_meta_vids(self) -> dict[tuple[str, str], list[str]]:
        """숨김 메타시트(_상품ID) col3 을 먼저 스캔 → {(사업자,상품): [vid…]}."""
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
        return meta_vids

    def _reindex_meta_rows(self, ws) -> None:
        """메타시트(_상품ID) 행 인덱스(_vid_row) 복원."""
        for r in range(2, ws.max_row + 1):
            b = _norm(ws.cell(r, 1).value); p = _norm(ws.cell(r, 2).value)
            if b and p:
                self._vid_row[(b, p)] = r

    def _reindex_sheet(self, ws, meta_vids: dict[tuple[str, str], list[str]]) -> None:
        """한 사업자 시트를 스캔해 날짜/지표/키워드/블록vid 인덱스를 복원."""
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
        """(사업자)→계정ID **집합**에 누적(항목5: 한 사업자 다계정ID 허용, 소유자 2026-09-25). 목차 표시용.

        ⚠ 예전엔 사업자당 계정ID 1개를 **덮어썼다**(다계정ID면 마지막 것만 남음). 이제 같은 사업자명에 여러
        계정ID가 오면 col2 에 ' / ' 로 **집합 누적**한다(중복 제거·등장 순서 보존). 비밀번호는 저장하지 않는다."""
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
                cur = [x.strip() for x in _norm(ws.cell(r, 2).value).split("/") if x.strip()]
                if aid not in cur:
                    cur.append(aid)
                ws.cell(r, 2, " / ".join(cur)); return
        row = ws.max_row + 1
        ws.cell(row, 1, biz); ws.cell(row, 2, aid)

    def account_ids_of(self, biz: str) -> list[str]:
        """그 사업자에 저장된 계정ID **목록**(등장 순서, 없으면 빈 리스트). 항목5 다계정ID 지원."""
        if _ACCT_SHEET not in self.wb.sheetnames:
            return []
        ws = self.wb[_ACCT_SHEET]
        for r in range(2, ws.max_row + 1):
            if _norm(ws.cell(r, 1).value) == biz:
                return [x.strip() for x in _norm(ws.cell(r, 2).value).split("/") if x.strip()]
        return []

    def account_id_of(self, biz: str) -> str:
        """저장된 **첫** 계정ID(없으면 ''). 다계정ID 사업자는 `account_ids_of` 로 전체를 얻는다(후방호환=첫 개)."""
        ids = self.account_ids_of(biz)
        return ids[0] if ids else ""

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
            # 소헤더 판정 = **A열 '키워드'만**(`_find_kw_head`와 동일 기준). G(비고 자리)는 항목3(2026-09-26)에서
            # 관리대장 판매상태(판매중/판매중지/체험단중)로 용도 전환돼 '비고'가 아닐 수 있으므로 G로 판정하지 않는다.
            if _key(ws.cell(r, _COL_KW).value) == _LABEL_KEYWORD:   # 소헤더 '키워드'=A열(v4)
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

    # ── 값 기록 ──────────────────────────────────────────────
    def set_product_metric(self, biz: str, product: str, metric: str, date_iso: str, value) -> bool:
        row = self._metric_row.get((biz, product, metric))
        if row is None:
            return False
        self.wb[biz].cell(row=row, column=self.ensure_date(biz, date_iso), value=value)
        return True

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

    def reconcile_account(self, biz: str, seen_products, ledger_products=None,
                          delete_missing: bool = False, account_id: str = "") -> tuple[list[str], list[str]]:
        """대장 대조: 그 계정의 마스터 블록을 관리대장과 맞춘다. 반환=(새로 판매중지된 상품, 완전삭제된 상품).

        ⚠ **항목5(다계정ID) 스코핑(2026-09-26)**: `account_id` 를 주면 그 사업자 시트에서 **그 계정ID 소속 상품**
        (`product_account_id`==account_id, 또는 미태깅 '')만 대조한다. 한 사업자 시트에 여러 계정ID 상품이 섞일 수
        있어(다계정ID), 계정 B 처리 시 계정 A 상품을 판매중지/삭제하는 사고를 막는다. account_id='' 면 전체(후방호환).

        - seen_products = 이번 대장에 **활성**으로 존재한 상품(블록명·vid 앵커로 해석). 여기 있으면 판매중지 해제.
        - **항목⑥(소유자 2026-09-25)**: `delete_missing=True`면 **관리대장에서 줄이 완전히 사라진 상품**(활성도
          아니고 `ledger_products`(줄 존재 전체=활성+판매중지/취소선)에도 없음) = **이력 포함 완전삭제**(백업이
          안전망). 대장에 **판매중지/취소선으로 남은(줄 존재)** 상품은 삭제하지 않고 **판매중지 표기 유지**.
          ⚠ `ledger_products` 가 비면(데이터 미전달) 완전삭제를 **건너뛴다**(대량 오삭제 방지 — 무결성 안전장치,
          소유자가 거부한 '수집 실패 가드'와는 별개). delete_missing=False(기본)는 옛 동작=전부 판매중지 표기."""
        seen = {_key(p) for p in seen_products}
        ledger = {_key(p) for p in (ledger_products or [])}
        acct = _norm(account_id)
        newly: list[str] = []
        deleted: list[str] = []
        for p in list(self.products_of(biz)):
            if acct and self.product_account_id(biz, p) not in ("", acct):
                continue                                           # 다른 계정ID 소속 상품 → 이 계정 대조서 제외(항목5)
            if p in seen:
                self.set_discontinued(biz, p, False)               # 대장에 활성 → 판매중지 해제
                continue
            base = self.registered_name(biz, p) or p                # 옵션 블록('등록명 (옵션)')은 등록명으로도 대조
            in_ledger = bool(ledger) and (p in ledger or base in ledger)
            if delete_missing and ledger and not in_ledger:        # 줄이 사라짐 → 완전삭제(⑥)
                if self.delete_product_block(biz, p):
                    deleted.append(p)
            else:                                                   # 줄 존재하나 비활성 → 판매중지 표기(유지)
                if not self.is_discontinued(biz, p):
                    newly.append(p)
                self.set_discontinued(biz, p, True)
        return newly, deleted

    def sync_discontinued_from_ledger(self, biz: str, active_products, discontinued_products,
                                      account_id: str = "") -> list[str]:
        """관리대장 기준으로 판매중지 플래그(_중단)를 **매 실행 동기화**한다(수집 여부 무관·2026-09-27).

        배경: `_중단` "Y"는 수집·대조(`reconcile_account`)할 때만 갱신돼, **이어쓰기(resume)로 ①판매수집을
        건너뛰거나 로그인 실패(미수집)면 낡은 "Y"가 남아** 정상 상품이 계정목록에 '판매중지'로 뜬다(실측
        커스텀존 이큐나라·하성진). 이 메서드는 대장이 **아는 상품만** 손대 안전하게 교정한다:
        - 대장 활성(active) 상품 → 판매중지 해제(False) — **낡은 오표기 제거(핵심)**.
        - 대장 판매중지(discontinued) 상품 → 판매중지 표기(True).
        - 대장에 **없는** 블록(노출명 매칭분·완전삭제 대상 등) → **건드리지 않음**(다른 경로가 처리).

        블록명이 '등록명 (옵션)' 이어도 등록명(base)으로 대조한다. `account_id` 주면 그 계정ID 상품만(다계정ID
        스코핑, [[fix-multiaccount-reconcile-scope]]). 반환=새로 판매중지로 바뀐 블록명 목록."""
        active = {_key(p) for p in active_products}
        disc = {_key(p) for p in discontinued_products}
        acct = _norm(account_id)
        newly: list[str] = []
        for p in list(self.products_of(biz)):
            if acct and self.product_account_id(biz, p) not in ("", acct):
                continue                                       # 다른 계정ID 소속 → 제외(다계정ID 교차오염 방지)
            base = self.registered_name(biz, p) or p           # 옵션 블록은 등록명으로도 대조
            if p in active or base in active:
                self.set_discontinued(biz, p, False)           # 대장 활성 → 낡은 '판매중지' 해제
            elif p in disc or base in disc:
                if not self.is_discontinued(biz, p):
                    newly.append(p)
                self.set_discontinued(biz, p, True)            # 대장 판매중지 → 표기
            # else: 대장에 없는 블록 → 불변(완전삭제/노출명 매칭 등은 다른 경로가 처리)
        return newly

    def data_quality_summary(self) -> dict:
        """실행 종료 데이터 품질 자가점검(2026-09-28) — 로그의 '✅ 완료'가 가리는 **불완전**을 수치화한다.

        소유자 원칙([[verify-by-data-not-status]]): 완료 표시가 아니라 **데이터**로 정상 판정. 읽기만(값·구조 불변).
        반환 {products, search_link, miss_vid, active_blank_rank}:
        - search_link = 상품링크가 검색폴백(pid 미확보) 수(정상상품인데 검색링크면 productId 미확보 신호)
        - miss_vid = vid 없는(미매칭) 상품 수
        - active_blank_rank = **판매중(비억제) 상품인데 최신 일자 순위가 전부 공란**(=미측정/차단 의심·핵심 이상치)"""
        search_link = miss_vid = active_blank = total = 0
        for biz in self.wb.sheetnames:
            if biz in _SPECIAL_SHEETS or biz.startswith("_") or "계정" in biz or "목차" in biz:
                continue
            ws = self.wb[biz]
            latest = min(self._date_col.get(biz, {}).values(), default=None)   # 최신=가장 왼쪽 일자칸
            for p in self.products_of(biz):
                total += 1
                if "np/search" in self.product_url(biz, p):
                    search_link += 1
                if not self.product_vids(biz, p):
                    miss_vid += 1
                if latest and not self.rank_suppressed(biz, p):
                    named = [(r, nm) for (r, nm) in self._kw_block_rows(biz, p) if nm]
                    if named and all(_norm(ws.cell(r, latest).value) == "" for (r, _nm) in named):
                        active_blank += 1
        return {"products": total, "search_link": search_link, "miss_vid": miss_vid,
                "active_blank_rank": active_blank}

    def delete_account(self, biz: str) -> bool:
        """관리대장에서 **줄이 완전히 사라진 계정**을 결과에서 완전 삭제 — 시트(시계열 이력)+모든 메타행.

        ⚠ **되돌릴 수 없음**(그 사업자 통계 이력 소멸). 관리대장에 '상태=판매중지'로 **남아있는** 것과는 다르다
        (그건 유지+경고). 호출부(pipeline)가 '관리대장에 계정ID가 아예 없음'을 확인한 뒤에만 호출한다.
        지운 게 있으면 True. `_계정정보`·`_상품ID`·`_중단`·`_마케팅`의 해당 사업자 행 + `_수집스탬프`의 그
        사업자 계정ID 행도 모두 제거한다."""
        biz = _norm(biz)
        if not biz:
            return False
        acct_ids = set(self.account_ids_of(biz))    # 스탬프(계정ID 키) 정리용 — 사업자행 삭제 전에 확보
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
        if acct_ids and _STAMP_SHEET in self.wb.sheetnames:   # 계정 단위 수집 스탬프(계정ID 키) 정리
            sws = self.wb[_STAMP_SHEET]
            for r in range(sws.max_row, 1, -1):
                if _norm(sws.cell(r, 1).value) in acct_ids:
                    sws.delete_rows(r)
                    removed = True
        if removed:
            self._reindex()
        return removed

    def _copy_product_block(self, src: str, product: str, dst: str) -> None:
        """src 시트의 상품 블록 하나를 dst 로 복제(이력·키워드·순위·검색량·메타 전부·일자 라벨로 정렬)."""
        kind = self.product_kind(src, product) or config.KIND_PERSONAL
        keywords = self.product_keywords(src, product)
        reg = self.registered_name(src, product) or product
        self.ensure_product_block(dst, product, kind, keywords, registered=reg)
        self.set_product_vids(dst, product, self.product_vids(src, product))
        self.set_product_kind(dst, product, kind)
        self.set_product_account_id(dst, product, self.product_account_id(src, product))   # 항목5 상품별 계정ID 이관
        self.set_sale_status(dst, product, self.sale_status(src, product))
        self.set_discontinued(dst, product, self.is_discontinued(src, product))
        ms, me, mm = self.marketing_of(src, product)
        if ms or me or mm:
            self.set_marketing(dst, product, ms, me, mm)
        _price, inbound, summ = self._product_extra(src, product)
        if inbound or summ:
            self.set_product_extra(dst, product, inbound_date=inbound or None, inbound_summary=summ or None)
        dates = dict(self._date_col.get(src, {}))
        for metric in _ALL_METRICS:                        # 지표값 일자별 이관
            srow = self._metric_row.get((src, product, metric))
            if srow is None:
                continue
            for dlabel, dcol in dates.items():
                v = self.wb[src].cell(srow, dcol).value
                if v not in (None, ""):
                    self.set_product_metric(dst, product, metric, dlabel, v)
        for kw in keywords:                                # 키워드 검색량+순위값 일자별 이관
            self.set_keyword_search(dst, product, kw, self.keyword_search(src, product, kw))
            srow = self._kw_row.get((src, product, kw))
            drow = self._kw_row.get((dst, product, kw))
            if srow is None or drow is None:
                continue
            for dlabel, dcol in dates.items():
                v = self.wb[src].cell(srow, dcol).value
                if v not in (None, ""):
                    self.wb[dst].cell(drow, self.ensure_date(dst, dlabel), v)

    def merge_account(self, src: str, dst: str) -> int:
        """같은 계정(계정ID 동일)이 **시트명 변경**(대표자명→사업자명 등)으로 둘로 쪼개졌을 때 **일원화**.

        관리대장은 담당자가 사업자명·대표자 등을 수시로 바꾸므로, 계정ID는 그대로인데 시트명만 달라져 옛 시트가
        고아(전부 판매중지)가 되는 사고를 막는다. dst 없으면 src 를 dst 로 **rename**(시트+메타 이관). dst 있으면
        src 의 상품 중 **dst 에 없는 것만** 이력 보존하며 이관(dst 상품=더 최신, 유지) 후 src 삭제. 이관 상품 수 반환."""
        src, dst = _norm(src), _norm(dst)
        if not src or not dst or src == dst or src in _SPECIAL_SHEETS or dst in _SPECIAL_SHEETS:
            return 0
        if src not in self.wb.sheetnames:
            return 0
        if dst not in self.wb.sheetnames:                  # dst 없음 → 단순 rename(시트+메타 biz 컬럼 이관)
            self.wb[src].title = dst[:31]
            for meta in (_META_SHEET, _DISC_SHEET, _MKT_SHEET, _ACCT_SHEET):
                if meta in self.wb.sheetnames:
                    mws = self.wb[meta]
                    for r in range(2, mws.max_row + 1):
                        if _norm(mws.cell(r, 1).value) == src:
                            mws.cell(r, 1, dst)
            self._reindex()
            return len(self.products_of(dst))
        self.ensure_account(dst)                           # dst 존재 → 병합(없는 상품만)
        dst_products = set(self.products_of(dst))
        aid, rep = self.account_id_of(src), self.representative_of(src)
        moved = 0
        for product in self.products_of(src):
            if product in dst_products:
                continue                                   # dst 에 이미 있음(더 최신) → 스킵
            self._copy_product_block(src, product, dst)
            moved += 1
        if aid and not self.account_id_of(dst):
            self.set_account_id(dst, aid)
        if rep and not self.representative_of(dst):
            self.set_representative(dst, rep)
        self.delete_account(src)                           # src 시트+메타 제거(reindex 포함)
        return moved

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
