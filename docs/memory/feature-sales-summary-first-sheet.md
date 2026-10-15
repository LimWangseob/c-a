---
name: feature-sales-summary-first-sheet
description: 통합 판매현황(D-064) — 결과 파일 첫 시트·계정→상품 수량/금액·윙/로켓그로스·전일/주/월 세로 3구역·원천=판매분석 기간 합계 조회
metadata:
  type: project
---
결과 파일(통계 마스터 + 결과 구글시트) **첫 시트 `통합판매현황`** = 위탁계정 계정→상품(옵션 합산) 판매수량·판매금액, 윙/로켓그로스 줄 나눔, 세로 3구역(전일 → 주간 월~일 최근 8주 → 월별 1월~). 미수집(기간 자료 못 받음)은 0 과 구분 표시. SSOT = `designs/SALES_SUMMARY.md`·DECISIONS D-064.

**Why**: 소유자 2026-10-15 — 월·주·전일 통합 판매현황을 결과 파일 첫 시트로, 매일 배치. 일별 기록(D-056)은 10-12 부터라 과거·로그인 실패일 구멍 → 주·월은 쿠팡 판매분석 **기간 합계를 그대로 조회**해 `output/판매분석_기간/{계정}.json`(키 `M:YYYY-MM`·`W:월요일`)에 저장.

**How to apply**:
- 시트 순서 관련 수정 시: 새 특수 시트는 `_SPECIAL_SHEETS` + `workbook._reindex` 건너뜀 목록 + 시험 도우미(`simulate_pipeline._sheets`·`verify_render_precision`)의 특수 시트 목록 3곳 모두 등록해야 함. `_build_index` 는 통합판매현황이 있으면 index 1 에 '계정 목록'을 만든다.
- 기간 조회(`pipeline_sales._record_sales_periods`)는 부가 기능 — 모든 예외 비치명(핀 A 가 브라우저 오류로 ① 수집이 깨지던 결함을 잡음).
- 남은 단계: 비대장 위탁계정(정산 watch 같은 조회)·앱 조회 탭·정산 파일 전수 조사 — 정산은 R13 정산 세션과 순서 조율. 진행 위치 = R0(HQ 포팅 대상).
- 관련: [[sales-data-api-vi-detail-search]] · [[settlement-batch-download-decisions]] · [[project-hq-split-261011]]
