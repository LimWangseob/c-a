---
name: followups-260921-run
description: 어제(2026-09-21) 실행 보완사항 7건 분석·수정(P1~P4 적용 완료). 재고 숨김옵션·판매중지 순위제외·임시저장 표기·구글시트 링크. P1 재고는 라이브 확인 남음.
metadata: 
  node_type: memory
  type: project
  originSessionId: 8d66ea21-b061-4f75-bc82-b5718c630fa8
  modified: 2026-09-22T09:52:23.691Z
---

**어제(2026-09-21) 실행 분석 후 보완 7건 → P1~P4 수정 적용(커밋 83a057d·4ec65a1·48f41f9·41683c8, 미푸시).**
근거=업로드된 output.zip(9/21 실행·stage=done·25계정·컬럼 09.20)의 실측.

## 실측 근거(어제 마스터)
- **순위**: 채움 113/공란 325. 판매중 28채움·**176공란**, **판매중지에 69채움(낭비)**. → 사무실 IP 차단 + 판매중지가 검색예산 잠식.
- **판매상태 분포**: 판매중지 93·판매중 72·부분판매중 39·미상 41. 임시저장/승인반려 **없음**(collector가 판매중지로 뭉갬).
- **옵션 재고**: 판매중 다중옵션(코골이)도 전 옵션 재고=None·부분판매중은 일부만. 원인=재고 조회 `hiddenStatus:"VISIBLE"` 이 숨김/판매중지 옵션 제외.
- **계정목록 링크**: 엑셀 마스터=정상(`'사업자'!A헤더행`), **구글시트만 전부 `계정목록!A1`**(자기탭).

## 적용한 수정
- **P2(83a057d)** 판매중지 순위 제외: `workbook.rank_suppressed`(is_discontinued OR sale_status∈{판매중지,임시저장,승인반려}, **미상은 억제 안 함**) → 자동/반자동 순위 헬퍼가 스킵. 핀 pin_login_ranks P2.
- **P3(4ec65a1)** 임시저장·승인반려 정확표기: `collector.sale_status_of` DRAFT→임시저장·REJECTED→승인반려 분리(기존=판매중지). `workbook.apply_sale_status` 단일상태 보존(uniq==1→그대로). `status_of`(계정목록 상태)에 미판매 상태 표기. 핀 pin_apply_style S7.
- **P4(48f41f9)** 구글시트 링크: **현재 코드는 정상**(`_product_cell`=HYPERLINK("#gid={사업자통계시트}&range=A{헤더행}"), plan_sync 매 동기화 C열 재기록) → 어제 `계정목록!A1`은 **실행 PC 옛 코드** 탓·**재실행 자동복구**. verify_gsheet t6 회귀핀 추가.
- **P1 재고 — 원인 확정·현재 코드 이미 해결(41683c8→12778ac→2998c16)**: hiddenStatus 가설 **오답**(라이브: VISIBLE=필드생략=21vid·HIDDEN=0·hiddenStatus 무관) → 되돌림(VISIBLE만). **진짜 원인 = '둘다'(로켓그로스+판매자배송) 상품은 같은 옵션이 NORMAL+RFM 2 vid 로 존재**하고 **RFM(로켓그로스)만 재고 있음**(NORMAL 쌍은 재고 공란). 라이브 nicoable 리스팅 구조로 확정: 기저귀가방 ON_SALE=[베이지 NORMAL(공란)+베이지 RFM(재고266)] 등. **현재 `products_from_vendor_inventory`는 이 NORMAL 중복을 정확히 제외**(오프라인 재현 증명·로그 '둘다 상품 판매자배송 옵션 제외') → 어제 '베이지_' 공란 블록은 **운용 PC 옛 코드** 탓·**재실행 자동해결**. 순수 판매자배송(히카마 등)은 재고행 자체 없음(정상). verify_offline [8]에 NORMAL 중복 제외 회귀핀. 진단=tools/diag_inv_hidden.py(hiddenStatus 실험+리스팅 구조 덤프)·verify_login_discover_live [재고대조]. [[fix-from-real-evidence]].
- **P3+ 검토중(UNDER_REVIEW) 표기(2998c16)**: nicoable 에 productStatus=UNDER_REVIEW(검토중) 상품 발견 → sale_status_of UNDER_REVIEW→검토중 추가(기존=판매중지로 뭉갬)·_NOT_SELLING_STATUSES(순위제외)에 검토중 포함. 전체 enum: ON_SALE/PARTIAL_ON_SALE/SUSPENDED/DRAFT/REJECTED/UNDER_REVIEW.

## 소유자 결정/정합
- 옵션: **분리 유지**(대표1+나머지 옵션 나열, 옵션별 재고·판매량 표기). 통합 안 함.
- 순위: 쿠팡 판매중/부분판매중만(판매중지·임시저장·승인반려·대장취소선 제외, 미상은 유지).
- 처리순서 7번: 판매분석 없을 때 zero 기록=현재도 일치. 매칭을 판매중 상품으로 제한=순위 쪽 rank_suppressed로 반영(수집은 전상품 유지).

## 남은 것(라이브)
- **P1 재고**: 다음 사무실 라이브에서 `verify_login_discover_live.py <계정ID> --semi` 로 **옵션 vid ↔ 재고 vid 대조**해 숨김옵션 재고가 잡히는지·HIDDEN enum 유효한지 확정.
- **순위(P2 효과)**: 핫스팟에서 ③ 순위 1회 — 판매중지 제외로 판매중 채움률↑ 확인.
- 관련: [[handoff-code-health]] [[fix-from-real-evidence]] [[feature-vid-source-from-product-list]] [[feature-sale-status-mismatch-flag]].
