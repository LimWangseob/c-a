---
name: detail-image-extraction
description: "상품 상세페이지 이미지 추출(A안 CDP attach) — 사용자 실제 Chrome에 붙어 대표+상세 이미지만 DOM 스코핑 추출. src/detail_images.py, 앱통합 완료"
metadata: 
  node_type: memory
  type: project
  originSessionId: 5f5772f7-fc22-427b-91e7-3a1e2d3bf916
  modified: 2026-09-15T09:17:22.843Z
---

**기능**: 쿠팡 상세페이지에서 **대표/갤러리 + 상세설명 이미지만** 골라 저장(`src/coupang_analytics/detail_images.py`). 순수 로직 `extract_from_page(page,…)`. 라이브 검증(2026-09-15, 광동 써큐알파 204847249): 대표 2(1000x1000)+상세 14(폭 778~780 원본), 실패 0, 추천/리뷰/광고 누출 0.

**⭐방식=A안 CDP attach(사용자 확정 2026-09-15)**: 앱이 **새 프로필로 코팡 접근 시 사무실 IP Akamai가 홈조차 Access Denied**(라이브 실증, 워밍업도 이 IP선 막힘). → 유일하게 안 막히는 경로 = **사용자의 warm·로그인된 실제 Chrome**. 앱은 브라우저 안 띄움. 사용자가 디버그포트(9222)로 자기 Chrome 실행→상품 열기→`extract_via_cdp(cdp_url)`가 connect_over_cdp로 붙어 상품 탭 자동탐색(`_pick_product_page`=보이는 탭 우선)+추출. `pw.stop()`=연결만 해제(Chrome 유지·안 죽임, 검증됨). ⛔폐기: 앱이 WingBrowser 띄우고 홈 워밍업(사무실 IP Access Denied).

**실측 셀렉터(2026-09-15, 쿠팡이 클래스 자주 바꿈 — 깨지면 재진단)**:
- 상세설명 컨테이너 = `.product-detail-content, .vendor-item`(각 이미지 `.subType-IMAGE.with-width-780`). URL=`thumbnail.coupangcdn.com/thumbnails/remote/q89/image/vendor_inventory/{hash}.jpg`(q89=원본폭).
- 대표/갤러리 컨테이너 = `div.product-image`(48x48썸네일+492x492메인이 같은 원본 → canonical `vendor_inventory/{hash}` dedup, 크기토큰만 1000x1000ex로 키워 고해상도).
- ⚠ **추천상품·리뷰 사진도 같은 vendor_inventory URL** → URL 필터 불가, **DOM 컨테이너 스코핑 필수**.
- 상세 영역은 "상품정보 더보기" 버튼으로 펼친 뒤 끝까지 스크롤해야 지연로딩 이미지가 다 붙음.

**앱 통합 완료(app_qt "상세 이미지" 탭)**: [쿠팡용 크롬 실행](디버그포트 9222·전용 영속 프로필 `data/chrome-images`, 이미 떠있으면 안내만·포트체크) → 사용자가 그 Chrome서 1회 로그인 후 상품 열기 → [이미지 추출](run_bg 1회: CDP attach→탐색→추출→폴더 자동열기·여러 번 반복). 저장 `output/상세이미지/{상품ID}/`(설정가능·gallery_NN·detail_NN·meta.json). 1건씩 ad-hoc(배치 아님). ⛔app.py(Tkinter 폴백)엔 미추가(주 UI=app_qt). 검증도구 `tools/verify_detail_images_live.py`(단독=WingBrowser 워밍업). SSOT=DESIGN §5.3. [[runtime-ui-and-always-on]]
