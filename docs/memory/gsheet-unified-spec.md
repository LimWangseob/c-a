---
name: gsheet-unified-spec
description: 구글 시트 통합(입력=관리대장·출력=결과시트) 모델·함정. 상세 SSOT=designs/GSHEET_UNIFIED.md
metadata:
  node_type: memory
  type: project
  originSessionId: 4c9cd574-1676-4798-ba82-659441c10186
  modified: 2026-09-17T09:00:13.966Z
---

구글 시트 통합 = **파일 2개**(2026-09-13 확정, 구현·라이브 검증 완료). 상세 SSOT=`designs/GSHEET_UNIFIED.md`, 설정=`docs/GSHEET_SETUP.md`.

**모델**:
- **입력 = 관리대장 구글시트**(「토탈셀러_셀독 관리 대장」). 계정 추가·삭제가 여기서 일어남. 비번도 여기에만(출력엔 없음). 읽기=서비스계정 API 직접(`gsheet_api.GSheetClient`, SA키=credstore `__gsheet_sa__`·DPAPI).
- **출력 = 결과 구글시트**. ①`계정목록` 시트=관리대장 미러링(`gsheet_index.sync_index`). **8열(2026-09-17 대표자 추가)**: A대표자·B사업자·C상품명·D계정ID·E~G체험단(직원입력·**절대 미접촉**)·H상태. 자동열=A·B·C·D·H, 안정키 메모=B(사업자)셀, 신규=계정그룹 끝 insertDimension. **계정 삭제(2026-09-17)**: 관리대장에서 **줄이 사라진 계정=완전 삭제**(`delete_accounts`=계정목록 행+통계시트 제거, 워크북 `delete_account`=시트·이력·메타). 판정=계정ID가 `InputList.ledger_account_ids`(줄 존재·판매중지 포함)에 없음. **판매중지로 남은 건 유지+경고**(삭제 아님)·로그인 실패도 삭제 아님. run_full→`_push_gsheet(removed_accounts=)`. ⚠비가역. **밴드색=계정ID별(2026-09-17, 사업자→계정ID)**: `roster_from_workbook` band_by_acct(계정ID 등장순), 같은 대표자라도 계정 다르면 다른 색. **판매중지 행도 계정 밴드색+대표자 채움**(`_rep_cell_request`, 공란 방지·기존엔 판매중지 행 대표자 비어있던 문제). **옛 7열 시트는 sync 시 `_ensure_rep_column`이 A에 빈 열 자동 삽입해 마이그레이션**(값·메모·서식·마케팅 우측 이동), `read_marketing`은 헤더 라벨로 열 탐지(옛/새 안전). 대표자=관리대장 대표자명(`wb.representative_of`, `_계정정보` 4열). 엑셀 `계정 목록`도 동일 8열. ②사업자별 통계 시트=openpyxl 마스터 **전체 미러링**(`gsheet_stats.push_statistics`·`worksheet_to_requests`).
- **역머지(출력→워크북)**: 직원이 시트에 직접 넣은 마케팅일자(`read_marketing`/`apply_marketing`)와 키워드(`read_staff_keywords`/`merge_staff_keywords`)를 실행 시작 시 워크북에 병합(추가만·제거없음) → 종료 미러링(전체교체)에도 보존. 안정키=계정ID+등록상품명(노출명 바뀌어도 안정, [[seldoc-output-format]] 등록상품명 보존).
- 배선: `pipeline.run_full(gsheet_output_url=)` 최종저장직후 `_push_gsheet`(push_statistics→sync_index), ①②③ 개별실행도 반영. 실패=로그명시·xlsx 보존·비치명. app_qt=QSettings·app.py=winreg 공유.

**함정(라이브가 잡음)**: ①설정 UI에서 결과 URL은 **'결과(출력) 링크' 칸**에 넣어야 함(입력칸 아님 — 파이프라인은 output_url을 봄). ②mergeType='MERGE_ALL'(MERGE_ROW 무효→400). ③계정목록 틀고정 frozenColumnCount=0(제목 A1:H1 병합을 열고정이 부분절단→400). xlsx 병행 유지(오프라인 백업), rclone 제거. 검증=verify_gsheet_offline(7종)+시뮬(라이브는 사무실).

관련: [[seldoc-output-format]] [[input-ledger-format]] [[daily-stats-keyword-freeze]] [[keyword-methodology-ai-anchor]] [[login-policy-real-browser-only]]
