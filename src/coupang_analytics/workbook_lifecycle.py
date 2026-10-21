"""워크북 계정·블록 정리 mixin — workbook.py 에서 분리(대형 파일 정비, 행동 불변).

관리대장 대조(reconcile)·판매중지 동기화·계정 완전삭제·시트명 변경 계정 병합·상품 블록 복사/삭제.
`class OutputWorkbook(_RenderMixin, _IndexMixin, _MetaMixin, _DateMixin, _LifecycleMixin)` 로 합쳐져
self 로 접근. workbook_common 재노출 사용.
"""
from __future__ import annotations

from .workbook_common import *  # noqa: F401,F403


def _ledger_vids(vids_of: dict | None, names) -> set:
    """{대장명: [VID…]} 에서 names(대장명들)의 VID 합집합 — 공백·줄바꿈 차이는 같은 대장명(match_anchor.key_of 와 동일)."""
    if not vids_of:
        return set()
    by_key = {" ".join(str(k).split()): v for k, v in vids_of.items()}
    return {v for n in names for v in by_key.get(" ".join(str(n).split()), [])}


class _LifecycleMixin:
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
                                      account_id: str = "", vids_of: dict | None = None) -> list[str]:
        """관리대장 기준으로 판매중지 플래그(_중단)를 **매 실행 동기화**한다(수집 여부 무관·2026-09-27).

        배경: `_중단` "Y"는 수집·대조(`reconcile_account`)할 때만 갱신돼, **이어쓰기(resume)로 ①판매수집을
        건너뛰거나 로그인 실패(미수집)면 낡은 "Y"가 남아** 정상 상품이 계정목록에 '판매중지'로 뜬다(실측
        커스텀존 이큐나라·하성진). 이 메서드는 대장이 **아는 상품만** 손대 안전하게 교정한다:
        - 대장 활성(active) 상품 → 판매중지 해제(False) — **낡은 오표기 제거(핵심)**.
        - 대장 판매중지(discontinued) 상품 → 판매중지 표기(True).
        - 대장에 **없는** 블록(노출명 매칭분·완전삭제 대상 등) → **건드리지 않음**(다른 경로가 처리).

        블록명이 '등록명 (옵션)' 이어도 등록명(base)으로 대조한다. `account_id` 주면 그 계정ID 상품만(다계정ID
        스코핑, [[fix-multiaccount-reconcile-scope]]). 반환=새로 판매중지로 바뀐 블록명 목록.
        `vids_of`={대장명: [VID…]}(① 매칭 결과) 주면 이름으로 못 찾은 블록도 VID 로 대조한다(D-082 — 블록 등록명=쿠팡
        이름이라 대장명과 달라 취소선이 반영 안 되던 실측 10-19 '맛있는 마시는 알부민')."""
        active = {_key(p) for p in active_products}
        disc = {_key(p) for p in discontinued_products}
        act_v, dis_v = _ledger_vids(vids_of, active), _ledger_vids(vids_of, disc)
        acct = _norm(account_id)
        newly: list[str] = []
        for p in list(self.products_of(biz)):
            if acct and self.product_account_id(biz, p) not in ("", acct):
                continue                                       # 다른 계정ID 소속 → 제외(다계정ID 교차오염 방지)
            base = self.registered_name(biz, p) or p           # 옵션 블록은 등록명으로도 대조
            named = p in active or base in active or p in disc or base in disc
            vids = set() if named else set(self.product_vids(biz, p))
            if p in active or base in active or vids & act_v:
                self.set_discontinued(biz, p, False)           # 대장 활성 → 낡은 '판매중지' 해제
            elif p in disc or base in disc or vids & dis_v:
                if not self.is_discontinued(biz, p):
                    newly.append(p)
                self.set_discontinued(biz, p, True)            # 대장 판매중지 → 표기
            # else: 대장에 없는 블록 → 불변(완전삭제/노출명 매칭 등은 다른 경로가 처리)
        return newly

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

    def prune_account_ids(self, biz: str, ledger_ids) -> int:
        """그 사업자에 저장된 계정ID 중 **관리대장에 없고 어느 상품에도 태그되지 않은** 것을 지운다(D-093) — `_계정정보`
        목록과 `_수집스탬프` 그 계정ID 행. 남은 개수가 0 이 되면 지우지 않는다(이름 변경·삭제 판정은 다른 경로).
        실측 10-20 유라이프: 대장 계정아이디 칸에 비밀번호 값이 하루 들어가 계정ID로 쌓였고(set_account_id 는 누적만),
        대장을 고친 뒤에도 시트 제목·통합판매현황에 그 값이 계속 보였다. 반환 = 지운 개수(값은 호출부도 로그에 안 남김)."""
        ids = self.account_ids_of(biz)
        tagged = {self.product_account_id(biz, p) for p in self.products_of(biz)}
        drop = [a for a in ids if a not in ledger_ids and a not in tagged]
        keep = [a for a in ids if a not in drop]
        if not drop or not keep:
            return 0
        ws = self.wb[_ACCT_SHEET]
        for r in range(2, ws.max_row + 1):
            if _norm(ws.cell(r, 1).value) == biz:
                ws.cell(r, 2, " / ".join(keep))
        if _STAMP_SHEET in self.wb.sheetnames:
            sws = self.wb[_STAMP_SHEET]
            for r in range(sws.max_row, 1, -1):
                if _norm(sws.cell(r, 1).value) in drop:
                    sws.delete_rows(r)
        return len(drop)

    def _copy_product_block(self, src: str, product: str, dst: str, other=None) -> None:
        """other(기본=이 워크북)의 src 시트 상품 블록 하나를 dst 로 복제(이력·키워드·순위·검색량·메타 전부·일자 라벨로 정렬)."""
        o = other or self
        kind = o.product_kind(src, product) or config.KIND_PERSONAL
        reg = o.registered_name(src, product) or product
        self.ensure_product_block(dst, product, kind, o.product_keywords(src, product), registered=reg)
        self.set_product_vids(dst, product, o.product_vids(src, product))
        self.set_product_kind(dst, product, kind)
        self.set_product_account_id(dst, product, o.product_account_id(src, product))   # 항목5 상품별 계정ID 이관
        self.set_sale_status(dst, product, o.sale_status(src, product))
        self.set_discontinued(dst, product, o.is_discontinued(src, product))
        ms, me, mm = o.marketing_of(src, product)
        if ms or me or mm:
            self.set_marketing(dst, product, ms, me, mm)
        _price, inbound, summ = o._product_extra(src, product)
        if inbound or summ:
            self.set_product_extra(dst, product, inbound_date=inbound or None, inbound_summary=summ or None)
        self._fill_block_history(o, src, product, dst, product)

    def _fill_block_history(self, o, src: str, product: str, dst: str, target: str) -> None:
        """o 의 src/product 이력(지표·키워드 순위·검색량)을 dst/target 블록의 **빈 칸에만** 채운다(dst 값 우선).
        옛 키워드는 target 에 추가(동결 키워드 복원·제거 없음)."""
        keywords = o.product_keywords(src, product)
        self.add_product_keywords(dst, target, keywords)
        dates, ws_src = dict(o._date_col.get(src, {})), o.wb[src]
        for metric in _ALL_METRICS:                        # 지표값 일자별 이관
            srow, drow = o._metric_row.get((src, product, metric)), self._metric_row.get((dst, target, metric))
            if srow is not None and drow is not None:
                self._fill_row(ws_src, srow, dates, dst, drow)
        for kw in keywords:                                # 키워드 검색량+순위값 일자별 이관
            srow, drow = o._kw_row.get((src, product, kw)), self._kw_row.get((dst, target, kw))
            if srow is None or drow is None:
                continue
            if self.keyword_search(dst, target, kw) in (None, ""):
                self.set_keyword_search(dst, target, kw, o.keyword_search(src, product, kw))
            self._fill_row(ws_src, srow, dates, dst, drow)

    def _fill_row(self, ws_src, srow: int, dates: dict, dst: str, drow: int) -> None:
        for dlabel, dcol in dates.items():
            v = ws_src.cell(srow, dcol).value
            if v in (None, ""):
                continue
            col = self.ensure_date(dst, dlabel)
            if self.wb[dst].cell(drow, col).value in (None, ""):
                self.wb[dst].cell(drow, col, v)

    def _merge_target(self, o, src: str, product: str, dst: str) -> str | None:
        """dst 에서 o 의 src/product 와 **같은 상품** — 이름이 같거나 VID 가 겹치는 블록(없으면 None)."""
        if product in self.products_of(dst):
            return product
        vids = set(o.product_vids(src, product))
        return next((p for p in self.products_of(dst) if vids & set(self.product_vids(dst, p))), None) if vids else None

    def merge_history_from(self, other, src: str, dst: str, only_existing: bool = False) -> int:
        """other(다른 워크북도 됨 — 옛 결과 파일 복구)의 src 시트 상품 이력을 dst 시트로 합친다(D-080).
        같은 상품(이름 같음 또는 VID 겹침)은 dst 빈 칸만 채우고 옛 키워드를 추가, dst 에 없는 상품은 블록째 복제
        (only_existing=True 면 건너뜀 — 복구 때 지금 없는 옛 상품을 되살리지 않음). 합친 상품 수 반환."""
        self.ensure_account(dst)
        n = 0
        for product in other.products_of(src):
            target = self._merge_target(other, src, product, dst)
            if target is None and only_existing:
                continue
            if target is None:
                self._copy_product_block(src, product, dst, other)
            else:
                self._fill_block_history(other, src, product, dst, target)
            n += 1
        return n

    def merge_account(self, src: str, dst: str) -> int:
        """같은 계정(계정ID 동일)이 **시트명 변경**(대표자명→사업자명 등)으로 둘로 쪼개졌을 때 **일원화**.

        관리대장은 담당자가 사업자명·대표자 등을 수시로 바꾸므로, 계정ID는 그대로인데 시트명만 달라져 옛 시트가
        고아(전부 판매중지)가 되는 사고를 막는다. dst 없으면 src 를 dst 로 **rename**(시트+메타 이관). dst 있으면
        src 의 상품 이력을 dst 로 합친 뒤(`merge_history_from` — 같은 상품은 dst 빈 칸만·옛 키워드 추가) src 삭제.
        합친 상품 수 반환. ⚠예전엔 dst 에 같은 상품이 있으면 건너뛰어 옛 이력·동결 키워드가 통째로 지워졌다(D-080)."""
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
        aid, rep = self.account_id_of(src), self.representative_of(src)
        moved = self.merge_history_from(self, src, dst)    # dst 존재 → 이력 합침
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

    def move_keywords(self, biz: str, src: str, dst: str) -> list[str]:
        """같은 상품의 **옛 대표 옵션 블록(src)** 키워드·검색량·일자별 순위를 **새 대표(dst)** 로 옮기고 src 의 키워드
        칸(소헤더·순위행)을 지운다 → src 는 판매정보만 남는 2차 옵션 블록(③ 중복 검색 방지·계정목록 1줄).
        쿠팡 옵션 순서가 바뀌어 대표가 바뀐 경우(C1, 소유자 2026-10-12 '새 대표로 키워드 복사'). dst 에 이미 키워드가
        있으면 **합친다**(dst 에 없는 키워드만 추가·같은 키워드는 dst 의 빈 날짜 칸만 src 값으로 — 실측 CL01·팜픽 두 블록 모두
        키워드). dst 에 키워드 칸이 없으면 무변경. 반환=dst 에 새로 더한 키워드."""
        biz, src, dst = _norm(biz), _key(src), _key(dst)
        if not self.has_keyword_section(biz, src) or not self.has_keyword_section(biz, dst):
            return []
        kws = self.product_keywords(biz, src)
        vols = {kw: self.keyword_search(biz, src, kw) for kw in kws}
        added = self.add_product_keywords(biz, dst, kws)   # dst 에 없는 것만·재인덱스 포함(src 행 번호도 갱신됨)
        ws = self.wb[biz]
        for kw in kws:
            if kw in added or self.keyword_search(biz, dst, kw) in (None, ""):
                self.set_keyword_search(biz, dst, kw, vols[kw])
            srow, drow = self._kw_row.get((biz, src, kw)), self._kw_row.get((biz, dst, kw))
            if srow is None or drow is None:
                continue
            for dcol in self._date_col.get(biz, {}).values():   # 같은 시트 = 같은 날짜 칸
                v = ws.cell(srow, dcol).value
                if v not in (None, "") and ws.cell(drow, dcol).value in (None, ""):
                    ws.cell(drow, dcol, v)
        self._drop_keyword_section(biz, src)
        return added

    def _drop_keyword_section(self, biz: str, product: str) -> None:
        """블록의 키워드 소헤더~마지막 순위행을 삭제(지표행은 유지). move_keywords 전용."""
        metric_rows = [self._metric_row[(biz, product, m)] for m in _ALL_METRICS
                       if (biz, product, m) in self._metric_row]
        if not metric_rows:
            return
        ws = self.wb[biz]
        sub = max(metric_rows) + 1
        if _key(ws.cell(sub, _COL_KW).value) != _LABEL_KEYWORD:   # 소헤더는 지표행 바로 아래(ensure_* 공통)
            return
        last = max((r for r, _ in self._kw_block_rows(biz, product)), default=sub)
        _unmerge_all(ws)                                   # 병합 해제 후 삭제(데이터 손상 방지, 이후 apply_style 재병합)
        ws.delete_rows(sub, last - sub + 1)
        self._reindex()
