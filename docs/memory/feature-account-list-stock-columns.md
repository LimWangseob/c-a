---
name: feature-account-list-stock-columns
description: 계정목록에 회사보유재고·그로스재고 2열 표기(상품명 오른쪽)·구현 완료·라이브 남음
metadata:
  node_type: memory
  type: project
  originSessionId: 93970391-cf4e-47e6-aacd-5dc2d38dfb72
  modified: 2026-09-29T04:56:32.201Z
---

**소유자 요청(2026-09-29)**: 결과파일 계정목록에 관리대장 역기록 값 "회사보유재고"·"그로스재고(자동갱신일자)"를 **상품명 오른쪽**에 표기.

**최종 열(엑셀 `계정 목록`·구글 `계정목록` 공통·11열)**: A 대표자·B 사업자·C 계정ID·D 상품명·**E 회사보유재고·F 그로스재고(자동갱신 MM.DD)**·G~I 체험단(직원입력·미접촉)·J 상태·K 체험단효과.

**데이터 출처**:
- 그로스재고(F) = 워크북 `wb.product_inventory(biz,prod)` (로켓그로스 최신 재고, 이미 보유). 숫자만·헤더에 갱신일자 1번(`wb.growth_asof()`=최신 일자 컬럼 '월.일'). 없으면 공란.
- 회사보유재고(E) = 판매자배송 자체재고 '창고 , 수량개'. **워크북에 원래 없음** → 매 실행 재고현황 시트를 읽어 `company_stock.apply_to_workbook(wb, stock)`로 워크북 인메모리(`_company_stock`)에 주입(마스터 미저장·다음 실행 재주입·미매칭/링크없음=공란). 매칭=등록명 `name_key`.

**주입 시점**: apply_style(계정목록 렌더) **전**. 공통 헬퍼 `pipeline_gsheet.inject_company_stock(wb, stock_url, log)`(재고현황 read→apply_to_workbook·비치명 no-op)을 3 stage에서 호출: run_full(`_finalize_run`)·select_keywords_stage·track_ranks_stage. 각 stage에 `stock_url` 파라미터 추가·UI app_qt 전 호출부가 `self._stock_url()` 전달(무인·재개·전체실행·개별 ②③ 버튼 전부). push_company_stock(관리대장 역기록)은 별개로 유지(실행 끝·apply_style 뒤라 계정목록 표기엔 못 씀 → 그래서 파이프라인 내부 주입 필요).

**gsheet 마이그레이션**: `_ensure_stock_columns`가 상품명 오른쪽(COL_STOCK=4)에 빈 열 2개 삽입. 순서=rep→order→stock. 제목 병합(A1:K1) 가로지르면 Google 400 → 병합 해제 선커밋→삽입→재병합 다배치(기존 `_ensure_column_order` 패턴 재사용). N_COLS 9→11.

**⚠라이브 400 후속 수정(2026-09-29·D8 세션 보고)**: 제목 재병합 A1:K1(11열)이 **고정 열 경계**를 가로질러 400("You can't merge frozen and non-frozen columns"). 옛 제목 A1:I1(9열)은 라이브 `frozenColumnCount=9` 안에 딱 맞았지만 새 A1:K1은 고정 9를 넘음. 비치명(제목만 병합 해제 상태)이나 고정 열 있는 다른 시트/새 설치서 재발. **수정=`_unfreeze_cols_request`(frozenColumnCount=0)를 두 마이그레이션(`_ensure_column_order`·`_ensure_stock_columns`)의 batch1(선커밋)에 추가** → 재병합 시점엔 고정 없음(전체생성이 이미 열 고정 0인 설계 의도와 일치·행 고정 2는 유지). 핀=verify_gsheet[11c](FakeClient에 `frozen_cols` 모델+병합 경계 400 재현). D8이 라이브 계정목록엔 이미 새 코드 마이그레이션 함수로 E·F열 삽입+회사재고 76/122줄 채움(그로스는 첫 실행서). ⚠운용PC 재배포 전 옛 코드 실행 금지(마케팅 칸 덮음).

**app.py(Tkinter 폴백)**: 회사재고 미지원(app_qt 전용 기능)·그로스재고는 워크북서 나오므로 폴백에서도 표기. 기존과 동일.

**검증**: 게이트9종+복잡도 초록. verify_render_precision(그로스값=45·헤더·상품명 오른쪽), verify_gsheet_offline(bg_cols {0,1,2,3,4,5,9,10}), verify_offline(대표자 컬럼 열위치), pin_l1_contract(sync_index growth_asof 추가). ⚠**라이브(회사재고 실주입·구글 마이그레이션 400 없이 수렴)·운용PC 재배포 남음**.

SSOT=designs/GSHEET_UNIFIED.md §계정목록 스키마·DECISIONS 2026-09-29. 관련=[[input-ledger-format]]·[[feature-business-name-grouping]].
