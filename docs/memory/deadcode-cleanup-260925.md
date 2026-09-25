---
name: deadcode-cleanup-260925
description: 죽은 코드 물리 삭제(2026-09-25). kw_shopping.py 모듈+app.py 네이버쇼핑키 흐름(죽은 기능)·참조0 메서드 3개(clear_values·inventory_by_registered_name·_roster) 제거. _backfill_ranks/_measure_unfilled_once는 가드호출+모킹 있어 보류.
metadata:
  node_type: memory
  type: project
  originSessionId: d8c440ae-0a9a-47f8-a6d2-d96209afecc7
  modified: 2026-09-25T12:10:03.854Z
---

**정밀 분석 방법**: `vulture src ui tools tests`(신뢰도 100/90/60) + 전 모듈 import 스캔 + 후보별 전수 참조 grep. 코드베이스는 이미 정비돼(2026-09-22 코드건강) 죽은 코드가 거의 없음 — vulture 60% 기준 3건뿐.

**물리 삭제(순 66줄·근거=참조 0건/죽은 기능)**:
- **모듈 `kw_shopping.py`** — 네이버쇼핑 검색 API(shop.json) 2026-07-31 종료. `NaverShoppingApi`는 이미 삭제됐고 `NaverShopCredentials` dataclass만 잔존했는데, 그걸 쓰는 `app.py`(Tkinter 폴백 UI)의 "(선택) 네이버쇼핑 키" 흐름이 **UI에서 수집·credstore 저장만 하고 run_full/select_keywords/recommend 로 전혀 전달 안 됨**(그 함수들에 shop 인자 없음)=죽은 기능. → 모듈+app.py 흐름(import·`self.naver_shop`·`shop_var`·버튼·`load_naver_shop`·`__naver_shop__` 로드/저장) 전부 제거. app_qt(기본 UI)는 원래 쇼핑 참조 0.
- **메서드 3개(참조 0)**: `gsheet_api.clear_values`·`workbook.inventory_by_registered_name`(역기록은 `inventory_by_biz`로 대체돼 고아)·`workbook._roster`.

**보류(임의 삭제 안 함·정책/동작 결정 필요)**:
- `pipeline._backfill_ranks`/`_measure_unfilled_once` — CLAUDE.md상 사문화(offscreen 노출측정 폐기)지만 **가드된 실제 호출부**(pipeline `if not skip_ranks and not keywords_off`)+**simulate_pipeline 모킹**이 존재 → 삭제 시 동작·테스트 변경. 정책 결정(가드 자체를 없앨지)으로 별도 처리.
- 지역변수 잔재(ruff F841: pipeline 의 grow/date_iso/naver/opened 등)·빈 f-string(F541) — 함수·모듈 아니라 이번 범위 밖·비게이트. 별도 미세정리.
- 스트레이 백업 폴더(`login_source_260904/`·`src - 복사본/`)는 패키지 아님(미import)·삭제는 파괴적이라 소유자 확인 후.

**검증**: 게이트 6종+복잡도 초록(건강 파일 A/B 유지)·전 UI py_compile OK·`git diff --stat`=66 deletions(0 insert). 커밋 후 [[code-health-regression-gate]] 준수.

관련: [[handoff-code-health]] [[naver-shopping-api-terminated]] [[code-health-regression-gate]].
