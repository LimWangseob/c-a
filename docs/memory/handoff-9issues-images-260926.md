---
name: handoff-9issues-images-260926
description: ✅결과파일 이미지 9이슈 정밀분석+조치 구현 완료(2026-09-26·라이브 남음) — 상품군 그룹키=블록명 base(레몬버베나/식기건조대 드리프트)·판매가/판매상태 자가치유·빈 키워드행 낡은순위 삭제·비고=대장 판매상태·상품명 하이퍼링크 productId 출처=판매분석∪재고. 게이트 7종+복잡도 초록.
metadata:
  node_type: memory
  type: project
  originSessionId: c16f3da3-27f9-41ca-bf1d-0a9ab5b96704
  modified: 2026-09-26T02:27:36.690Z
---

소유자가 결과 구글시트 5개 이미지 + 9개 이슈로 전수조사/원인분석/조치 요청. 전부 구현·게이트 통과, **라이브 확인·재배포 남음**.

**조치 5묶음:**
1. **항목7/8/9 상품군 그룹키 = 블록명 base**(`workbook._group_key`): 옵션 접미 `" (라벨)"` 제거+공백정규화. 등록상품명 드리프트(레몬버베나 "…정" vs "…정 60정"·식기건조대 twin '' vs 세트)로 같은 상품군이 다른 색·분산되던 문제 → `_regroup_sheet_blocks`·`_style_sheet` 그룹핑을 등록상품명 대신 블록명 base 로. 실측 run6: 레몬버베나 3블록 FBE2D5 통일·연속 확인.
2. **항목4/6 판매가·판매상태 지표행 자가치유**(`_backfill_metric_rows`, apply_style): 2026-09-24 신설 이전 옛 블록(대장서 빠진 판매중지·미로그인 계정=파이프라인 미방문)엔 두 행 없음(실측 13블록) → 저장마다 없는 행만 삽입(순서 재고<판매가<판매상태·재고는 KINDS_WITH_INVENTORY만·kind='' 미상은 재고 강제 안 함).
3. **항목5 빈 키워드행 낡은순위 삭제**(`_clear_blank_keyword_ranks`): 이름 공란 M_RANK 행(KW_TRACK_N 유지용)에 남은 옛 '50위'(실측 43행)="키워드 없는데 순위 표기" → 저장마다 이름 공란 행 일자칸 값 삭제(이름 있는 행 불변).
4. **항목3 비고 소헤더 = 관리대장 판매상태**(⛔판매중지 > 🔴체험단중 > 판매중): 옛 '비고' 라벨 폐지. 대장서 빠짐=판매중지·존재=판매중. ⚠**부작용 수정**: `has_keyword_section` 소헤더 판정을 G('비고')+A('키워드') → **A('키워드')만**(항목3로 G 용도전환돼 깨지던 것·`_find_kw_head`와 일관). `_migrate_keyword_col` sub_g 에 '판매중' 추가.
5. **항목2 상품명 하이퍼링크 = vendorItemId 기반(라이브 실증 후 최종)**: ⚠상품조회(vendor-inventory) 응답엔 공개 productId **없음이 20계정 _raw 전수 확정**(0/20·vendorInventoryId·vendorItemId·skuId만). productId 는 판매분석·재고에만 → **미입고 RFM·무활동 판매자배송 확보 불가**(화면 노출상품ID는 WING 화면의 별도 4번째 API·우리 3 API·로그엔 없음·9557485279 전수 0). **⭐라이브 실증(내장 브라우저 2026-09-26)**: `https://www.coupang.com/vp/products/0?vendorItemId={vid}` 가 productId 자리 `0` 이어도 **정확한 상품 페이지로 열림**(벅스 보냉백·쿠팡상품번호 9557485279 로드). 판매중지 vid(95546377159)는 '상품없음'(실제 판매중지라 정상). → `workbook.product_url` = **vid 있으면 `/vp/products/{pid or 0}?vendorItemId={vid}`**(pid 있으면 정규·없으면 0 자리표시)·**vid 없으면 검색 폴백.** vendorItemId 는 상품조회 전 상품·전 옵션 항상 존재 → 미입고·판매자배송 커버(실측 기존 마스터 상품페이지 링크 88→109·검색폴백은 vid없는 미매칭 20만). pid_by_vid(판매분석∪재고=collector `OptionMetric.product_id`+`_parse_inventory_pids`·`fetch_inventory` 3→4튜플·pipeline `_apply_pid` 배선)는 정규 URL 용으로 유지. 핀 pin_apply_style[S9]·verify_offline[14 (d)]·verify_render[항목2].

**검증**: 게이트 7종+`check_complexity`(exit 0·경고는 기존 타 파일 괴물함수). 핀 pin_apply_style[S1 비고=판매중]·verify_offline[14 자가치유 3종]·verify_render_precision[항목2 링크·상품군색]·페이크 4튜플화(pin_login_ranks·simulate·verify_render). run6 실측 치유 0/0/0.

⚠**남은 것**: 라이브 재수집으로 실렌더 확인 + 운용 PC 재배포 + 커밋/푸시/zip 재빌드.

관련: [[analysis-gsheet-dup-listing-260924]] [[handoff-inventory-blank-260924]] [[handoff-3decisions-260924]] [[handoff-block-layout-redesign]] [[fix-from-real-evidence]] [[sales-data-api-vi-detail-search]] [[inventory-api-rfm-search]].
