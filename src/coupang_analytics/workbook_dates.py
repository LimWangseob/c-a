"""워크북 날짜 칸·수집 이력·측정 주기 mixin — workbook.py 에서 분리(대형 파일 정비, 행동 불변).

판매수집 스탬프(_수집스탬프)·날짜 칸 추가/정규화/갭필·날짜 지정 칸 리셋·상품/계정 측정 주기(due).
`class OutputWorkbook(_RenderMixin, _IndexMixin, _MetaMixin, _DateMixin, _LifecycleMixin)` 로 합쳐져
self 로 접근. workbook_common 재노출 사용.
"""
from __future__ import annotations

from .workbook_common import *  # noqa: F401,F403


class _DateMixin:
    def _stamp_ws(self):
        """판매수집 스탬프 숨김 시트(없으면 생성). (계정ID)→판매수집일 — **계정 단위**(항목5)."""
        if _STAMP_SHEET in self.wb.sheetnames:
            return self.wb[_STAMP_SHEET]
        ws = self.wb.create_sheet(_STAMP_SHEET)
        ws.sheet_state = "hidden"
        ws.cell(1, 1, "계정ID"); ws.cell(1, 2, "판매수집일"); ws.cell(1, 3, "수집일 이력")
        return ws

    def mark_sales_collected(self, account_id: str, date_label: str) -> None:
        """이 **계정(계정ID)** 의 '판매수집 완료(오늘=date_label 컬럼)' 스탬프를 숨김 `_수집스탬프` 시트에 기록.

        판매지표는 0/공란도 정상(판매데이터 없음)이라 값으로 '수집됨'을 판정할 수 없으므로, **명시적 스탬프**로
        기록한다. 같은 날 재실행이 이 스탬프를 보고 그 계정의 로그인·수집을 생략한다(진행파일이 지워져도 마스터에
        영속). **항목5(소유자 2026-09-25): 스탬프 키=계정ID**(사업자 아님) — 한 사업자 다계정ID면 계정마다
        따로 수집 판정(예전 사업자 단위는 둘째 계정이 '이미 완료'로 스킵되던 버그). date_label 은 워크북 일자
        컬럼 라벨(yy.mm.dd 또는 from~to)과 동일 문자열."""
        aid, label = _norm(account_id), _norm(date_label)
        if not (aid and label):
            return
        ws = self._stamp_ws()
        row = next((r for r in range(2, ws.max_row + 1) if _norm(ws.cell(r, 1).value) == aid), ws.max_row + 1)
        ws.cell(row, 1, aid)
        last = _norm(ws.cell(row, 2).value)
        ws.cell(row, 2, max(last, label) if last else label)   # 판매수집일 = 가장 최근 칸(날짜 지정으로 옛 칸 채워도 유지)
        # 칸별 이력(2026-10-10 날짜 지정): 옛 칸을 채울 때 이미 수집한 계정을 날짜별로 건너뛰는 근거(최근 30칸).
        hist = {h for h in _norm(ws.cell(row, 3).value).split(",") if h} | {label}
        ws.cell(row, 3, ",".join(sorted(hist)[-30:]))

    def sales_collected_on(self, account_id: str) -> str:
        """그 **계정(계정ID)** 에 마지막으로 기록된 판매수집일 라벨(없으면 '')."""
        aid = _norm(account_id)
        if not aid or _STAMP_SHEET not in self.wb.sheetnames:
            return ""
        ws = self.wb[_STAMP_SHEET]
        for r in range(2, ws.max_row + 1):
            if _norm(ws.cell(r, 1).value) == aid:
                return _norm(ws.cell(r, 2).value)
        return ""

    def has_sales(self, account_id: str, date_label: str) -> bool:
        """그 **계정(계정ID)** 의 판매수집이 date_label(오늘 컬럼) 기준으로 이미 완료됐는가(재실행 스킵 근거).

        다른 날 라벨이면 False(자동으로 그날 새로 수집) → 날짜가 바뀌면 스탬프가 달라 재수집된다. 날짜 지정으로
        옛 칸을 채울 때는 **칸별 이력**(3열)도 본다 — 그 칸을 이미 수집한 계정은 건너뜀(2026-10-10)."""
        label = _norm(date_label)
        if not label:
            return False
        if self.sales_collected_on(account_id) == label:
            return True
        if _STAMP_SHEET not in self.wb.sheetnames:
            return False
        ws, aid = self.wb[_STAMP_SHEET], _norm(account_id)
        return any(_norm(ws.cell(r, 1).value) == aid and label in _norm(ws.cell(r, 3).value).split(",")
                   for r in range(2, ws.max_row + 1))

    def is_rank_filled(self, biz: str, product: str, keyword: str, date_iso: str) -> bool:
        row = self._kw_row.get((biz, product, keyword))
        col = self._date_col.get(biz, {}).get(date_iso)
        if row is None or col is None:
            return False
        # '-'(구 미측정/스캔밖 placeholder)는 미채움으로 봐 ③ 재실행이 다시 측정하게 한다
        # (새 규칙에선 스캔밖=50위로 기록하므로 '-'는 측정 안 된 잔재).
        return self.wb[biz].cell(row=row, column=col).value not in (None, "", "-")

    def clear_sales_stamps(self) -> int:
        """모든 계정의 '판매수집 완료' 스탬프(`_수집스탬프` 시트)를 해제 → '오늘 처음(다시)' 재수집 시
        오늘 이미 완료한 계정도 다시 수집(has_sales 가 False 가 됨). 해제한 계정 수 반환."""
        if _STAMP_SHEET not in self.wb.sheetnames:
            return 0
        ws = self.wb[_STAMP_SHEET]
        n = 0
        for r in range(2, ws.max_row + 1):
            if _norm(ws.cell(r, 2).value) or _norm(ws.cell(r, 3).value):
                ws.cell(r, 2).value = None
                ws.cell(r, 3).value = None      # 칸별 이력도 해제(다시 수집 = 전부 재수집)
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

    def account_due(self, biz: str, target_iso: str, account_id: str = "") -> tuple[bool, str]:
        """오늘 이 **계정**에 로그인할지(=상품이 하나라도 수집 대상). 로그인은 계정 단위라 OR 로 집계.

        account_id 를 주면(항목5 다계정ID) 그 사업자 시트 상품 중 **그 계정ID 소속 상품만**으로 판정한다
        (상품별 계정ID 태깅=`product_account_id`). 미태깅 상품(옛 마스터·판매자배송)은 포함(보수적으로 수집).
        account_id 없으면 사업자 전체 상품(후방호환)."""
        aid = _norm(account_id)
        prods = self.products_of(biz)
        if aid:
            prods = [p for p in prods if self.product_account_id(biz, p) in ("", aid)]
        if not prods:
            return True, "신규/상품없음(수집 시도)"
        for p in prods:
            if self.product_due(biz, p, target_iso)[0]:
                return True, "수집 대상 상품 있음"
        return False, "모든 상품 오늘 수집 대상 아님"
