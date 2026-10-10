"""워크북 숨김 메타시트(상품 속성) mixin — workbook.py 에서 분리(대형 파일 정비, 행동 불변).

VID·productId·등록명·판매방식·계정ID·판매상태·재고·노출명/블록명·제목 캐시·마케팅·판매중지 기록/조회.
`class OutputWorkbook(_RenderMixin, _IndexMixin, _MetaMixin, _DateMixin, _LifecycleMixin)` 로 합쳐져
self 로 접근. workbook_common 재노출 사용.
"""
from __future__ import annotations

from .workbook_common import *  # noqa: F401,F403


class _MetaMixin:
    def _meta_ws(self):
        """상품ID 숨김 시트(없으면 생성)."""
        if _META_SHEET in self.wb.sheetnames:
            return self.wb[_META_SHEET]
        ws = self.wb.create_sheet(title=_META_SHEET)
        ws.sheet_state = "hidden"
        ws.cell(1, 1, "사업자"); ws.cell(1, 2, "상품명"); ws.cell(1, 3, "상품ID(vid)")   # vid 목록('/' 조인) — 레이아웃 v4서 vid 출처(A안, 헤더 이름칸 꼬리→여기로 이전)
        ws.cell(1, 4, "키워드서명(미사용)"); ws.cell(1, 5, "권고제목(미사용)")   # 옛 ⑤ 제목 캐시 — 인라인 키워드 경로 삭제(D-022 B5)로 쓰기 중단·열 위치만 유지
        ws.cell(1, 6, "등록상품명")   # 대장 원본명(노출명으로 바뀌어도 불변) — 계정목록 안정키·3c 마케팅 매칭 기준
        ws.cell(1, 7, "판매상태(쿠팡)")   # 쿠팡 재고 판매상태(판매중/부분판매중/판매중지) — 대장 판매중지와 대조해 경고 표시
        ws.cell(1, 8, "상품판매가(미사용)")   # 판매가는 '판매가' 지표행으로 이관(2026-09-24)
        ws.cell(1, 9, "로켓그로스판매일")   # saleStartedAt(판매일 근사) — 헤더 표시용, 판매자배송은 공란
        ws.cell(1, 10, "최근입고요약")   # 관리대장 입고 요약(요청/작업/박스/파레트/완료/출고) — 헤더 로켓그로스 묶음
        ws.cell(1, 11, "판매방식")   # 구분(로켓그로스/판매자배송/둘다) — 레이아웃 v4 헤더 '판매방식' 줄 표시용(표시 전용·인덱스 아님)
        ws.cell(1, 12, "계정ID")   # 상품 소속 계정ID(항목5: 시트=사업자명, 다계정ID면 상품마다 어느 계정인지 태깅)
        ws.cell(1, 13, "노출productId")   # 쿠팡 공개 상품ID(항목3: 순위매칭 SERP href에서 확보) — 상품명 하이퍼링크용
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

    def set_product_account_id(self, biz: str, product: str, account_id: str) -> None:
        """상품(줄)의 **소속 계정ID**를 숨김 메타시트 12열에 저장(항목5 소유자 2026-09-25).

        시트는 사업자명 단위인데 한 사업자에 계정ID가 여럿일 수 있어(다계정ID), **어느 계정에서 온 상품인지**를
        상품 속성으로 태깅한다. 계정목록(구글시트/엑셀) 계정ID 열·안정키가 이 값을 읽는다. 빈값이면 no-op(기존 보존)."""
        biz, product, aid = _norm(biz), _key(product), _norm(account_id)
        if not (biz and product and aid):
            return
        ws = self._meta_ws()
        row = self._vid_row.get((biz, product))
        if row is None:
            row = ws.max_row + 1
            ws.cell(row, 1, biz); ws.cell(row, 2, product)
            self._vid_row[(biz, product)] = row
        ws.cell(row, 12, aid)

    def product_account_id(self, biz: str, product: str) -> str:
        """저장된 상품 소속 계정ID(없으면 '' — 옛 마스터·미태깅). 계정목록 계정ID 열의 상품별 소스."""
        row = self._vid_row.get((_norm(biz), _key(product)))
        if row is None or _META_SHEET not in self.wb.sheetnames:
            return ""
        return _norm(self.wb[_META_SHEET].cell(row, 12).value)

    def set_product_pid(self, biz: str, product: str, product_id: str) -> None:
        """상품의 **쿠팡 공개 상품ID(productId)** 를 숨김 메타 13열에 저장(항목2, 소유자 2026-09-26).

        출처=**판매분석(vi-detail) ∪ 재고 API**(수집 시 vid→productId, 판매 0 상품까지 커버) 우선, 폴백=③
        순위조회 검색결과(SERP) href `/vp/products/{productId}`. ⚠상품조회(vendor-inventory)엔 공개 productId
        없음(실측 2026-09-26). 통계 시트 상품명 하이퍼링크(쿠팡 노출상품 페이지)용. 빈값이면 no-op(기존 보존)."""
        biz, product, pid = _norm(biz), _key(product), _norm(product_id)
        if not (biz and product and pid):
            return
        ws = self._meta_ws()
        row = self._vid_row.get((biz, product))
        if row is None:
            row = ws.max_row + 1
            ws.cell(row, 1, biz); ws.cell(row, 2, product)
            self._vid_row[(biz, product)] = row
        ws.cell(row, 13, pid)

    def product_pid(self, biz: str, product: str) -> str:
        """저장된 쿠팡 공개 상품ID(없으면 '' — 미매칭). 상품명 하이퍼링크 대상 URL 생성용."""
        row = self._vid_row.get((_norm(biz), _key(product)))
        if row is None or _META_SHEET not in self.wb.sheetnames:
            return ""
        return _norm(self.wb[_META_SHEET].cell(row, 13).value)

    def product_url(self, biz: str, product: str) -> str:
        """상품명 클릭 시 열 **쿠팡 노출상품 URL**(항목2). productId(정규 상품ID)가 있으면
        `/vp/products/{productId}?vendorItemId={vid}` 로 **정확한 상품 페이지**를 연다(정규).

        ⚠**vid-only URL 은 실측상 불가**(2026-09-27 내장 브라우저: `/vp/products/0?vendorItemId={vid}`=서버오류·
        `/vp/products?vendorItemId={vid}`=301). 옛 `productId=0` 자리표시 트릭은 **폐기**. productId 는 재고 API·
        판매분석 응답에만 있으므로, **판매중지·미입고 상품도 수집하면(#8) 재고 API 로 pid 를 확보**해 정규 링크가 된다.
        pid 가 정말 없는(완전 미매칭/미수집) 경우에만 **불가피하게** 노출명 검색으로 조건부 폴백한다([[no-silent-fallback-principle]])."""
        pid = self.product_pid(biz, product)
        vids = self.product_vids(biz, product)
        if pid and vids:
            return f"https://www.coupang.com/vp/products/{pid}?vendorItemId={vids[0]}"
        return "https://www.coupang.com/np/search?q=" + _quote(_key(product))   # pid 없음(불가피)=노출명 검색

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

    def index_display_name(self, biz: str, product: str) -> str:
        """계정목록(엑셀·구글) **표시 상품명** — 대표 옵션 블록의 수량/옵션 접미('(1개 120정)')를 정리(소유자 2026-09-29).

        같은 상품군(블록명 base)의 수량 옵션(1개/2개/3개)은 `_is_secondary_option` 이 2차를 빼 **대표 1줄**만
        남는데, 그 대표 이름(노출명)에 '(1개 …)' 접미가 붙어 지저분했다. 그룹 안에 **대표가 유일**하면(수량
        옵션뿐) 접미를 떼 깔끔히, **여럿**이면(색상 등 별도 상품 대표가 공존) 구분 위해 원래 이름 유지. 블록
        정체성(매칭키·하이퍼링크)은 안 바뀐다(표시만). ⚠계정목록은 **노출명 표시**(대장명으로 치환하지 않음)."""
        if " (" not in product:
            return product
        gk = self._group_key(product)
        sibs = [p for p in self.products_of(biz)
                if not self._is_secondary_option(biz, p) and self._group_key(p) == gk]
        return product.rsplit(" (", 1)[0].rstrip() if len(sibs) <= 1 else product

    @staticmethod
    def _group_key(product: str) -> str:
        """상품군 그룹 키(소유자 2026-09-26 확정: 블록명 base) — 같은 상품군(기본+옵션·수량 1/2/3개·
        로켓그로스+판매자배송 twin)이 **등록명 드리프트**(공란·'60정' 유무 등)로 다른 색·분리되던 문제 해소.

        블록명에서 **마지막 ' (' 이후(옵션/수량 라벨: '(1개 60정)'·'(베이지)' 등)를 제거**한 base 를 공백
        정규화해 반환. 같은 base = 한 상품군(연속·같은 색). registered_name 대신 이 키로 정렬·색·경계를 묶는다."""
        p = _key(product)
        base = p.rsplit(" (", 1)[0] if " (" in p else p
        return " ".join(base.split())

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

    def set_company_stock(self, biz: str, product: str, text: str) -> None:
        """계정목록 표기용 **회사보유재고**(판매자배송 자체재고) 텍스트 저장 — 매 실행 재고현황에서 주입.

        값 = 관리대장 역기록과 동일한 '창고 , 수량개' 문자열(company_stock.stock_text). 인메모리(마스터 미저장)."""
        self._company_stock[(biz, product)] = text

    def company_stock_of(self, biz: str, product: str) -> str:
        """이 상품의 회사보유재고 표기 문자열(없으면 공란) — 계정목록 5열."""
        return self._company_stock.get((biz, product), "")

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
