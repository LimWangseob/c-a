---
name: handoff-3decisions-260924
description: "✅3대 최종결정 구현·커밋 완료(2026-09-24). ①계정목록=대장상태만(productStatus 폴백 제거) ②계정목록 I열 '체험단효과' 신설(직전→최신 점비교) ③관리대장 로켓그로스 입고 7컬럼→헤더 '최근입고' 요약. 게이트 6종+복잡도 초록. 라이브 확인·재배포 남음."
metadata:
  node_type: memory
  type: project
  originSessionId: 21b94b1b-9360-410e-958f-e9680c3d75d1
  modified: 2026-09-24T13:15:11.607Z
---

**맥락**: [[handoff-gsheet-inventory-followup]](Fix A/B 재고칸) 이후 소유자가 3대 최종결정 확정 → 이 세션에서 전부 구현·커밋.

**커밋**: e06c944(①③)·(②는 후속 커밋). 게이트 6종+`check_complexity.py`(exit 0) 초록. **미푸시/라이브 확인 상태는 세션 끝 확인.**

## ①계정목록 상태 = 대장 상태만 (되돌림)
- `workbook.status_of`: **productStatus 폴백 제거** → 대장 판매중지(⛔) > 미수집 > 체험단 상태만.
- 2026-09-22의 "계정목록에 임시저장·승인반려 등 productStatus 표기" 되돌림. 쿠팡 판매상태는 **날짜별 '판매상태' 지표행**에 이미 있어 계정목록에선 뺌(소스별 위치 분리). 핀 pin_apply_style S7 갱신(계정목록 productStatus 미표기).

## ②계정목록 '체험단효과' 자동열(I열) 신설
- `wb.promo_effect(biz,product)` → (표시문자열, 판정). **체험단 시작일 직전 마지막 측정치→가장 최신 측정치** 점 비교(gap-fill 빈 컬럼 건너뜀).
- 판매=`M_SALES` %변화·순위=**모든 키워드 최고순위(숫자 최소)** before→after. 예 "판매 +38% · 순위 32→18 ↑".
- 판정 up(판매↑·순위 숫자↓=개선)=연초록·down=연적색·데이터부족=공란. 순위 `'N위밖'`(미발견)=제외(`_rank_num`).
- 배선: gsheet `COL_PROMO=8`·`N_COLS 8→9`(직원 마케팅 E~G **뒤 끝**에 추가·미접촉)·`_HEADS`+`_auto_cells_request` col8 값/색·`roster_from_workbook`이 `IndexRow.promo_effect/promo_verdict` 채움. 엑셀 `_build_index`/`_index_row` 9열(A~I). 끝열이라 기존 8열 시트 자동 확장(마이그레이션 불필요). 핀 verify_offline[13]·verify_gsheet t6.
- **소유자 확정 계산방식**: 직전값→최신값(점 비교)·최고순위(숫자 최소). (평균/전체구간 아님.)

## ③관리대장 로켓그로스 입고 7컬럼 → 헤더 '최근입고' 요약
- 관리대장 컬럼(요청일자·요청수량·작업수량·박스·파레트·완료일자·출고일자) → `input_list._inbound_summary`가 한 줄 요약, `Product.inbound_summary`로 전파(`product_match` 3곳).
- `pipeline._apply_vid_meta(...,inbound_summary)` → `wb.set_product_extra(inbound_summary=)` → 헤더 로켓그로스 묶음(판매일+최근입고). 판매가는 별도 '판매가' 지표행(재고현황 아래) 유지. config alias `IN_ALIASES_INB_*`.

## ⚠라이브 400 수정(2026-09-24 운용PC 로그)
- 첫 라이브 실행에서 통계 26시트 미러링 성공 후 **'계정목록 동기화' HTTP 400**(Invalid requests[0].updateCells). 원인=체험단효과로 열 8→9인데 **옛 계정목록 그리드 폭이 9보다 좁아** 9번째 열 기록이 그리드 초과. 수정=`GSheetClient.grid_col_count`(meta columnCount)+`_grid_grow_requests`가 기록 전 COLUMNS appendDimension으로 확장(행 확장과 동일). 커밋 d6fda8d·핀 verify_gsheet[3d]. xlsx 마스터는 그때도 정상 저장됨(유실 없음)·재배포+재실행하면 계정목록 반영.

## 남은 일
- **재배포(400 수정 포함) 후 재실행** → 계정목록 I열 체험단효과 렌더·헤더 최근입고·계정목록 대장상태만·계정목록 동기화 성공 확인. [[code-health-regression-gate]] 준수.

관련: [[handoff-gsheet-inventory-followup]] [[gsheet-unified-spec]] [[date-column-run-date-rule]] [[fix-from-real-evidence]].
