---
name: deadcode-cleanup-260925
description: 죽은 코드 물리 삭제(2026-09-25). kw_shopping.py 모듈+app.py 네이버쇼핑키 흐름(죽은 기능)·참조0 메서드 3개(clear_values·inventory_by_registered_name·_roster) 제거. _backfill_ranks/_measure_unfilled_once는 가드호출+모킹 있어 보류.
metadata:
  node_type: memory
  type: project
  originSessionId: d8c440ae-0a9a-47f8-a6d2-d96209afecc7
  modified: 2026-09-26T13:11:31.418Z
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

---
## 2026-09-26 재조사 추가(소유자 "전수조사·물리 삭제" 재요청·커밋 842d0e4)
- ⚠**`workbook._roster` 는 2026-09-25 에 "삭제"로 기록됐으나 실제로는 잔존**했음(파일에 그대로 있었음) → 2026-09-26 실제 삭제. 교훈=[[fix-from-real-evidence]](삭제 주장은 `git diff --stat`·순 LOC 로 검증). `clear_values`·`inventory_by_registered_name` 은 실제 삭제 확인됨.
- 추가 삭제(전수 참조 카운트·고아 스캔 근거): `rank._SEARCH_BOX_SEL`(미사용 상수)·`pipeline_ranks` 죽은 대입 `opened`(위 F841 잔재)·`ui/app.py` 저장후 미사용 속성 `_bar_bg`(형제 _sel/_sel_fg/_unsel_fg/_hover 는 사용).
- 유지: `recent_events`(tools/session_state_report 사용)·고아 모듈 0·vulture 80%=0건(코드베이스 이미 정비됨).
- ✅ **offscreen 순위백필 물리 삭제(소유자 승인 2026-09-26)**: `_backfill_ranks`/`_measure_unfilled_once`/`_count_unfilled_ranks`(pipeline_ranks) + pipeline.py 가드 호출부(`if not skip_ranks and not keywords_off`) + 재수출 + simulate scenario_full_composition 의 백필 목킹/검증 2건까지 함께 제거. 정책(offscreen 폐기·반자동만)은 불변 — 문구를 "사문화(코드 잔존)"→"폐기·삭제"로 CLAUDE.md·DESIGN §5.2/§0-0/재실행멱등·CODE_HEALTH_PLAN·[[rank-antiblock-circuit-breaker]]·[[session-current-state]] 동기화. 게이트 7종+복잡도 초록.
- **여전히 보류(소유자 유지 결정 2026-09-26)**: **스트레이 백업 `login_source_260904/`·`login_source_260904.zip`·`src - 복사본/`** — git 미추적(삭제 시 복구 불가)·미import. 소유자가 **유지** 선택(보존).

관련: [[handoff-code-health]] [[naver-shopping-api-terminated]] [[code-health-regression-gate]] [[fix-from-real-evidence]].
