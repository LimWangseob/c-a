---
name: feature-product-coupang-link
description: "✅통계 시트 상품명→쿠팡 노출상품 하이퍼링크(항목3, 2026-09-26·라이브 남음)+소유자 6요구 정밀분석 반영. productId(순위 SERP)로 정확페이지·없으면 노출명 검색 폴백. gsheet 외부링크 미러 확장. 제목 순서 대표자·사업자·계정ID."
metadata:
  node_type: memory
  type: project
  originSessionId: c16f3da3-27f9-41ca-bf1d-0a9ab5b96704
  modified: 2026-09-25T15:25:28.601Z
---

**소유자 2026-09-26 6개 요구 정밀분석+반영**(항목3 신규). 게이트 6종+복잡도 초록. ⚠라이브·재배포 남음.

- **①gsheet 서식 분석**: 통계 시트=`gsheet_stats.worksheet_to_requests`가 openpyxl 시트를 **셀 단위 그대로 미러링**(값·채움·테두리·폰트·병합·폭)이라 apply_style 변경 자동 반영 → **구조 변경 불필요**. 계정목록은 ④(열순서·폭·밴드)에서 이미 반영. 유일 필요=항목3 외부링크 미러(아래).
- **②계정목록 링크 정상**: `_product_cell`=`=HYPERLINK("#gid={통계}&range=A{헤더행}")`, ④ 스왑 후 D열 정상. verify_gsheet[6].
- **③(신규) 노출상품명→쿠팡 링크**: 통계 시트 상품명 헤더 C셀 클릭→쿠팡 새 창. `workbook.product_url`=productId(메타 col13) 있으면 `/vp/products/{pid}?vendorItemId={첫vid}`(정확)·없으면 `np/search?q={노출명}`(폴백). productId=순위 SERP href(`rank.SearchItem.product_id`, `mi=cap.get("제품")`서 그동안 버리던 값)를 `set_product_pid`로 저장(pipeline 4개 순위기록 지점: 1134·1437·2150·2611). `apply_style`이 헤더 C셀에 `Hyperlink(target=url)` 멱등 부여. **gsheet**: `gsheet_stats._cell_value`가 외부 http 링크도 `=HYPERLINK` 변환(내부 #gid만 하던 것 확장·통계 자동 미러). 핀 pin_apply_style[S9]·verify_gsheet[t5].
- **④동일상품군 바탕색**: 구현됨(pin_apply_style S8: 같은 등록명 옵션=같은 색·인접군 살구↔민트 교대). 바탕색 다르면 다른 상품군.
- **⑤상단 제목**: (계정ID,대표자,사업자)→**(대표자,사업자,계정ID)** 순·다계정ID 모두(account_ids_of). `apply_style`. 핀 verify_offline[17].
- **⑥4키워드 공란시 선정**: 구현됨. `_resolve_keywords`: `product_keywords` 비면(공란=이름 있는 순위행 0) AI 선정 실시·1건이라도 있으면 동결. 공란 순위행은 product_keywords 미반환→선정 트리거. 핀 verify_offline[23](공란→select_keywords_light 호출·동결→미호출).

**부수**: pin_apply_style 마케팅 픽스처를 **오늘 기준 상대날짜**로 안정화(날짜 롤오버로 '체험단중'→'모니터링' 되던 취약성 제거).

관련: [[feature-business-name-grouping]] [[handoff-9items-spec-260925]] [[seldoc-output-format]] [[gsheet-unified-spec]] [[semi-auto-rank-and-exposed-name]].
