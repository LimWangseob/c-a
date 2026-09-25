---
name: pending-code-fixes-next-session
description: 2026-09-20 소유자 요청 — 새 세션에서 이어서 구현할 코드 수정 5건(계정목록 단위·검색량 채움·마스터 gsheet 복원·변형상품 서식·용어). 각 항목 파일·라인·결정사항 포함
metadata: 
  node_type: memory
  type: project
  originSessionId: caa98cbb-30ab-492e-8a76-b5e4771c38ac
  modified: 2026-09-20T04:17:11.961Z
---

**✅2026-09-20 새 세션에서 5건 전부 구현 완료·오프라인 검증 통과(verify_offline·simulate·verify_gsheet + 표적 테스트).** ⚠라이브(실제 마스터·구글시트 복원) 1회 확인만 남음. 커밋은 아직(소유자 결정 대기). 아래는 각 항목 구현 위치 기록.

VID 출처 변경(옵션 분리) 1~7단계는 이미 커밋됨([[feature-vid-source-from-product-list]]) — 아래는 그 위에 얹는 후속.

## ✅구현 요약(2026-09-20 완료)
- **①** `workbook._is_secondary_option`(has_keyword_section False AND 이름=등록명+옵션라벨)로 2차 옵션 판정 → `_product_rows`가 제외(대표+단일만). 계정목록=상품별 1줄. `roster_from_workbook`도 자동 반영(같은 로스터).
- **②** `workbook.keyword_search`(F열 getter) 추가 + `pipeline._fill_frozen_search_volumes`(공란만 네이버 `related_keywords_multi`·공백/대소문자 무시 매칭). `run_full` 동결분기(pipeline:716 근처)·`select_keywords_stage`(②) 둘 다 배선.
- **③** `pipeline.restore_master_from_gsheet(out_dir,url,on_log)` 추가(`gsheet.download_xlsx`→마스터 저장·OutputWorkbook.load 검증·실패 시 사유 로그+파일 정리). UI가 `master_exists()` 판정 **전에** 호출: app_qt `do_run_full`·`start_auto`, app.py `do_run_full`(newall/resume 제외). ⚠가시 시트만 미러라 숨김 메타는 다음 ①이 재구성.
- **④** `apply_style`의 `edge()`에 선 스타일 인자 추가·헤더 루프 앞 `regs` 선계산 → `group_start`/`group_end`로 같은 등록명 그룹 바깥=thick·내부=thin.
- **⑤** app_qt·app.py 라벨: "오늘 것만 다시 수집"·"통계 전체 초기화(백업 후)", 첫 실행 로그에 구글시트 복원 불가 명시.

## ① 계정목록 단위 결정 + 구글시트 반영
- 증상: 마스터 계정목록이 옵션 분리로 76→186줄, 구글시트는 아직 76줄(옵션분리 후 push 미실행).
- `roster_from_workbook`([gsheet_index.py:401](src/coupang_analytics/gsheet_index.py:401))이 `wb.product_roster()`(블록마다 1줄)를 그대로 씀 → 옵션마다 별도 줄.
- **✅소유자 결정(2026-09-20): (나) 상품별 76줄**. 계정목록에는 **대표 옵션 블록만** 담고, 옵션 분리는 통계 시트 안에서만. 구현: `roster_from_workbook`([gsheet_index.py:401](src/coupang_analytics/gsheet_index.py:401))/`product_roster`가 **2차(비대표) 옵션 블록을 건너뛰게** — 판정키=블록명이 등록명 뒤에 "(옵션라벨)"이 붙은 형태(2차) 또는 `has_keyword_section`=False(2차는 키워드·순위행 없음). 대표(첫 옵션)=등록상품명 그대로라 목록에 1줄만. 엑셀 `계정 목록` 시트(`wb`)도 동일 단위로. ⚠통계 시트 자체는 옵션별 유지(목록만 상품별).
- 옛 "개인 상품" 라벨 잔재: 라벨 변경(로켓그로스/판매자배송) 전 블록이 마스터에 "개인 상품"으로 남음 → 다음 ①수집이 덮어씀(코드수정 불요, 확인만).

## ② 동결 키워드 검색량 채움 (OpenAI 불필요·네이버만)
- 증상: 동결 키워드는 검색량이 항상 공란/0. [pipeline.py:716](src/coupang_analytics/pipeline.py:716) `track_info = [(kw, 0, "", ranks.get(kw)) for kw in keywords]` — 검색량 미측정.
- 소유자 규칙: 키워드가 있으면 생성 생략(동결)하되 **검색량 칸이 비어 있으면 네이버 검색광고 API로 채운다**. AI(OpenAI) 불필요.
- 구현: [pipeline.py:695-717](src/coupang_analytics/pipeline.py:695) 동결 분기에서, 검색량 셀이 빈 키워드만 `NaverAdApi`로 조회 → `wb.set_keyword_search`. 키워드 개수 4개 미만/초과는 순위검색이 이미 "채워진 것만" 처리하므로 검색량 채움도 동일 적용.

## ③ 마스터 없으면 구글시트에서 불러오기
- 증상: 마스터 파일 없는 PC에서 "새 통계 시작(첫 실행)"로 오판 → 과거 날짜(09.18/09.19 등) 유실.
- 경로: 출력 구글시트는 마스터의 전체 미러 → `gsheet.download_xlsx(출력URL)`([gsheet.py:29](src/coupang_analytics/gsheet.py:29))로 통째로 xlsx 복원 가능.
- 구현: `master_exists()`가 False이고 gsheet 출력URL 있으면 download_xlsx→마스터로 저장 후 이어쓰기. 실패 시 로그 명시(fallback 금지) 후 정상 "첫 실행"으로.

## ④ 변형(옵션) 상품 서식 그룹화
- 증상: 옵션 분리로 한 상품이 블록 여러 개 → `apply_style`이 블록마다 굵은 테두리(`edge`, [workbook.py:995](src/coupang_analytics/workbook.py:995)·[:1115](src/coupang_analytics/workbook.py:1115)) → 변형이 다 따로따로 보임. 서식 코드 자체는 이번 세션에 안 바뀜(옵션 분리로 블록 수만 증가).
- 구현: 같은 등록상품명(`registered_name`/`blocks_with_registered_name`)을 공유하는 블록들을 한 그룹으로 → **그룹 바깥만 굵은 선, 그룹 내 변형 사이는 얇은 선**. apply_style의 블록 루프를 그룹 경계 인식으로 개편(멱등 유지·구글시트 미러링 자동 반영).

## ⑤ 실행모드 용어 개선(선택)
- "오늘 처음(다시) 하기"→"오늘 것만 다시 수집", "전체 새로 시작"→"통계 전체 초기화(백업 후)", "새 통계 시작(첫 실행)" 로그에 "⚠ 마스터 없음 — 구글시트에서 불러올까요?" 경고(③과 연계). [app_qt.py:496-504](ui/app_qt.py:496).

## 이미 완료(구현됨·라이브 확인만)
- 판매중지 실제 확인 = 판매상태=productStatus + 불일치 경고([[feature-sale-status-mismatch-flag.md]]) 이미 커밋. 남은 건 라이브 1회.

## 상품 구분(참고, 코드 확정)
- `kind_of`([collector.py:136](src/coupang_analytics/collector.py:136)): RFM=로켓그로스·NORMAL=판매자배송. 전부RFM=로켓그로스·RFM없음=판매자배송·섞임=둘다. "개인상품"="판매자배송"(옛 라벨). 재고는 로켓그로스·둘다만.
