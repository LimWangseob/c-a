---
name: feature-product-coupang-link
description: "✅통계 시트 상품명→쿠팡 노출상품 하이퍼링크(항목3, 2026-09-26·라이브 남음)+소유자 6요구 정밀분석 반영. productId(순위 SERP)로 정확페이지·없으면 노출명 검색 폴백. gsheet 외부링크 미러 확장. 제목 순서 대표자·사업자·계정ID."
metadata:
  node_type: memory
  type: project
  originSessionId: c16f3da3-27f9-41ca-bf1d-0a9ab5b96704
  modified: 2026-09-26T02:28:10.952Z
---

**소유자 2026-09-26 6개 요구 정밀분석+반영**(항목3 신규). 게이트 6종+복잡도 초록. ⚠라이브·재배포 남음.

- **①gsheet 서식 분석**: 통계 시트=`gsheet_stats.worksheet_to_requests`가 openpyxl 시트를 **셀 단위 그대로 미러링**(값·채움·테두리·폰트·병합·폭)이라 apply_style 변경 자동 반영 → **구조 변경 불필요**. 계정목록은 ④(열순서·폭·밴드)에서 이미 반영. 유일 필요=항목3 외부링크 미러(아래).
- **②계정목록 링크 정상**: `_product_cell`=`=HYPERLINK("#gid={통계}&range=A{헤더행}")`, ④ 스왑 후 D열 정상. verify_gsheet[6].
- **③(신규) 노출상품명→쿠팡 링크 — ⚠2026-09-26 vendorItemId 기반으로 최종화([[handoff-9issues-images-260926]])**: 통계 시트 상품명 헤더 C셀 클릭→쿠팡 새 창. **⭐라이브 실증**: `/vp/products/0?vendorItemId={vid}` 가 vid 만으로 상품 페이지 열림(productId 자리 0 자리표시). `workbook.product_url`= **vid 있으면 `/vp/products/{pid or 0}?vendorItemId={첫vid}`**(pid 있으면 정규·없으면 0)·**vid 없으면 `np/search?q={노출명}`**. ⚠**productId 는 URL 필수 아님**·상품조회 응답엔 공개 pid 없음(20계정 _raw 0/20)이라 pid_by_vid(판매분석 `vendorItemDetails.productId` ∪ 재고 `listingDetails.productId`·`_apply_pid`·`fetch_inventory` 4튜플)는 **정규 URL 용만**. vendorItemId 는 상품조회 전 상품·전 옵션 항상 존재 → **미입고 RFM·판매자배송 커버**(기존 마스터 링크 88→109). `apply_style` 헤더 C셀 Hyperlink 멱등. **gsheet**: `_cell_value`가 외부 http 링크도 `=HYPERLINK` 변환(통계 자동 미러). 핀 pin_apply_style[S9]·verify_offline[14 (d)]·verify_render[항목2]·verify_gsheet[t5].
- **④동일상품군 바탕색**: 구현됨(pin_apply_style S8: 같은 등록명 옵션=같은 색·인접군 살구↔민트 교대). 바탕색 다르면 다른 상품군.
- **⑤상단 제목**: (계정ID,대표자,사업자)→**(대표자,사업자,계정ID)** 순·다계정ID 모두(account_ids_of). `apply_style`. 핀 verify_offline[17].
- **⑥4키워드 공란시 선정**: 구현됨. `_resolve_keywords`: `product_keywords` 비면(공란=이름 있는 순위행 0) AI 선정 실시·1건이라도 있으면 동결. 공란 순위행은 product_keywords 미반환→선정 트리거. 핀 verify_offline[23](공란→select_keywords_light 호출·동결→미호출).

**부수**: pin_apply_style 마케팅 픽스처를 **오늘 기준 상대날짜**로 안정화(날짜 롤오버로 '체험단중'→'모니터링' 되던 취약성 제거).

관련: [[feature-business-name-grouping]] [[handoff-9items-spec-260925]] [[seldoc-output-format]] [[gsheet-unified-spec]] [[semi-auto-rank-and-exposed-name]].
