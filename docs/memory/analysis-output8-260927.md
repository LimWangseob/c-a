---
name: analysis-output8-260927
description: 운용 output(8) 실측 3이슈 분석 — 상품명깨짐(C셀 URL잔재)=수정·순위공란/링크오류=웰빙곳간 SUSPENDED 정상결과
metadata:
  node_type: memory
  type: project
  originSessionId: 3588291b-3435-4968-8471-8410129d1b69
  modified: 2026-09-27T14:17:32.349Z
---

운용 PC output(8).zip(2026-09-27 18:00 이어쓰기 실행 중) 실측 분석. 소유자 보고 3이슈:

**① 노출순위 값 모두 공란(웰빙곳간)** = **정상(코드변경 없음)**. wellbing1107=쿠팡 all-SUSPENDED 제한계정 → 전 상품 판매상태=판매중지 → `workbook.rank_suppressed=True` → ③순위 검색 제외. 로그 실측: ③에서 `🔎 [(주)웰빙곳간]` 0건(다른 26계정은 정상 검색됨). #8 정책(판매중지=수집하되 순위만 제외)의 의도된 결과. ⚠대장엔 active(is_discontinued=False)여도 쿠팡 suspended면 억제됨(rank_suppressed 는 판매상태도 봄). 과거 컬럼의 '50위'는 옛 placeholder 잔재.

**② 상품링크 "상품을 찾을 수 없습니다"(pid+vid 정상 URL도)** = **정상(불가피)**. suspended 상품은 쿠팡이 상품 페이지를 내려 `/vp/products/{pid}?vendorItemId={vid}` 정규 URL도, 검색 폴백도 실패. 코드 링크 생성은 올바름·상품이 실제로 안 보이는 상태.

**③ 상품명 깨짐(상품명 칸에 URL 텍스트)** = **실제 버그·수정함**(커밋 a6055e4). 실측: 웰빙곳간 시트 C열(_COL_NAME) **비-헤더 8셀**(판매상태/판매가/블록 사이 빈 행)이 상품명이 아니라 쿠팡 검색URL을 **값**으로 담음(옛 배포 코드 잔재). 현재 apply_style 이 그 칸을 안 건드려 재렌더해도 8→8 잔존. 상품명+링크는 상품명 헤더행 C에만 정상 존재하므로 `workbook_render._clear_stray_url_cells`(헤더(_date_rows) 아닌 C셀 값이 http 로 시작하면 값·하이퍼링크 삭제) 추가·apply_style 배선. 실측 8→0·정상 보존. 핀 pin_apply_style[S10].

**2차 분석(소유자 "정상 계정 상품 찾아 분석" 지시)**: (DW)커머스(서달원·dalbong1849) 8상품 중 7개는 이미 정상 상품링크(`/vp/products/{pid}?vid`), 1개("파미젠 스트레스 엔 테아닌"·ON_SALE)만 검색링크. **#1 진짜 버그**: 같은 옵션 "1개 60정"이 vid 2개(NORMAL 96075356361=pid없음 + RFM 96075356358=재고API pid 8359540267)인데 **옛 배포 코드가 pid 없는 NORMAL vid를 저장** → 검색링크. **현재 코드 `_tracked_listing_options`는 "둘다=RFM만" 규칙대로 RFM vid를 정확히 선택**(실측: 추적 vid=['96075356358'])→pid→정상 상품링크. 즉 **새 코드에 이미 수정됨**. 순수 판매자배송(RFM 형제 없음)·무판매 상품은 3개 API 어디에도 공개 pid 없어(상품조회 0/20 확정) 검색링크 불가피.

**결론·소유자 결정(2026-09-27)**: 4이슈 전부 새 빌드에 이미 반영(#1 RFM vid 선택·#3 moveDimension 2배치·상품명깨짐 `_clear_stray_url_cells` a6055e4)이거나 쿠팡/데이터 한계(wellbing 판매정지·판매자배송 무pid). **추가 코드 변경 없음** — 소유자 "재배포 후 다음 수집으로 자동치유(권장)" 선택. 마스터의 잘못된 NORMAL vid 블록은 재배포+**fresh ①판매수집**(resume 아닌 정규 실행)에서 RFM vid로 자동 갱신. **#4 노출순위**: 정상 계정은 수집됨(로그 (DW)커머스 24회 검색)·wellbing만 판매정지로 rank_suppressed(현행 정책 유지). **#2**: 정상 상품 pid 링크 정상 열림·wellbing만 페이지 없음(쿠팡 WING 재개 필요). **운용 PC 재배포 필수**(현 실행=옛 코드).

[[fix-from-real-evidence]] [[input-ledger-format]] [[no-silent-fallback-principle]]
