---
name: analysis-output8-260927
description: 운용 output(8) 실측 3이슈 분석 — 상품명깨짐(C셀 URL잔재)=수정·순위공란/링크오류=웰빙곳간 SUSPENDED 정상결과
metadata:
  node_type: memory
  type: project
  originSessionId: 3588291b-3435-4968-8471-8410129d1b69
  modified: 2026-09-27T13:25:21.571Z
---

운용 PC output(8).zip(2026-09-27 18:00 이어쓰기 실행 중) 실측 분석. 소유자 보고 3이슈:

**① 노출순위 값 모두 공란(웰빙곳간)** = **정상(코드변경 없음)**. wellbing1107=쿠팡 all-SUSPENDED 제한계정 → 전 상품 판매상태=판매중지 → `workbook.rank_suppressed=True` → ③순위 검색 제외. 로그 실측: ③에서 `🔎 [(주)웰빙곳간]` 0건(다른 26계정은 정상 검색됨). #8 정책(판매중지=수집하되 순위만 제외)의 의도된 결과. ⚠대장엔 active(is_discontinued=False)여도 쿠팡 suspended면 억제됨(rank_suppressed 는 판매상태도 봄). 과거 컬럼의 '50위'는 옛 placeholder 잔재.

**② 상품링크 "상품을 찾을 수 없습니다"(pid+vid 정상 URL도)** = **정상(불가피)**. suspended 상품은 쿠팡이 상품 페이지를 내려 `/vp/products/{pid}?vendorItemId={vid}` 정규 URL도, 검색 폴백도 실패. 코드 링크 생성은 올바름·상품이 실제로 안 보이는 상태.

**③ 상품명 깨짐(상품명 칸에 URL 텍스트)** = **실제 버그·수정함**(커밋 a6055e4). 실측: 웰빙곳간 시트 C열(_COL_NAME) **비-헤더 8셀**(판매상태/판매가/블록 사이 빈 행)이 상품명이 아니라 쿠팡 검색URL을 **값**으로 담음(옛 배포 코드 잔재). 현재 apply_style 이 그 칸을 안 건드려 재렌더해도 8→8 잔존. 상품명+링크는 상품명 헤더행 C에만 정상 존재하므로 `workbook_render._clear_stray_url_cells`(헤더(_date_rows) 아닌 C셀 값이 http 로 시작하면 값·하이퍼링크 삭제) 추가·apply_style 배선. 실측 8→0·정상 보존. 핀 pin_apply_style[S10].

**소유자 결정 대기**: suspended/판매중지 상품에 대해 (a)상품명 링크 자체를 걸지 말지(어차피 페이지 없음) (b)순위 억제 유지할지. **운용 PC 재배포 필요**(현 실행=옛 코드·③ 청소 미반영).

[[fix-from-real-evidence]] [[input-ledger-format]] [[no-silent-fallback-principle]]
