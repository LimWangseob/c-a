---
name: date-column-run-date-rule
description: "날짜 컬럼 규칙(2026-09-16 확정) — 라벨=작업 실행날짜·년도없는 '월.일'(당분간), 순위=실행일·판매=전일(D-1) 같은 컬럼, 미실행/중단일=날짜만+공란(연속 유지)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 2e84ec15-ec5e-47e8-a0f5-e93a370e0385
  modified: 2026-09-23T03:21:59.525Z
---

**확정(2026-09-16 소유자)**: 결과파일(통계 마스터) 날짜 컬럼 규칙.

- **정렬 = 내림차순·최신 날짜 = 맨 왼쪽 H열(소유자 2026-09-23 변경).** 틀고정 H2라 최신은 스크롤 없이 항상 보임, 오래된 것만 오른쪽 스크롤. `normalize_date_columns`가 first~last 연속일 만든 뒤 **reverse**로 H부터. `latest_date`·`product_latest_date`는 **날짜값 기준**(물리 컬럼 아님)으로 최신 선택(정렬 반전에도 순위/재고/판매중경고가 올바른 최신 칸에). 기존 오름차순 마스터는 다음 저장 때 자동 재정렬(값 유실0). 커밋 de5fec6·핀 verify_offline[14]-C.
- **연말/연초 경계 처리(2026-09-23)**: `_parse_date`가 '월.일'을 **오늘과 가장 가까운 해**로 해석(`_nearest_year` — 1월의 '12.30'=작년)해 363칸 폭발 방지. 같은 날 옛/신 라벨 2컬럼 공존 시 `_rebuild_date_grid`가 **최신 비어있지 않은 값** 보존. 커밋 7038ef9·bbf5b2b·핀 verify_offline[14]-A/B.
- **라벨 형식 = 년도 없는 '월.일'(예 09.16), 당분간**(사용자 요청). `col_label`·`ensure_date` 갭필·`normalize_date_columns`가 전부 `strftime("%m.%d")`. `_parse_date`에 `%m.%d`(nearest-year 해석). 기존 `26.09.xx`도 normalize가 **날짜로 매칭해 재포맷**(값을 (행,날짜)로 스냅샷 → 유실0). 실제 마스터 적용 완료(전부 09.xx·값 2194셀 유실0).

- **컬럼 라벨 = 작업 실행날짜**(그날 실제 돌린 날, 예 9/16 실행→`26.09.16`). 이전엔 판매확정일 D-1로 라벨해 "9/16 실행인데 09.15로 적힘" 혼란 → 실행날짜로 변경.
- **한 컬럼에 = 오늘 순위 + 전일 판매**(방식 ㉮). 순위는 실행일 측정이라 라벨과 일치. **판매(쿠팡 통계)는 전일 D-1에서 조회**해 같은 컬럼에(쿠팡이 당일 판매를 익일 확정). `run_full(date_label=)`로 판매조회일(date_from~to=D-1)과 **분리**. UI `_run_dates()`=(D-1, D-1, 실행날짜) 반환.
- **새벽 넘겨도 시작일 기준**: `date_label`은 실행 시작 때 1회 확정·진행중 파일(`date_label`)에 저장 → 자정 넘겨 이어서/재부팅 재개해도 원래 실행날짜 유지(`_save_progress`/resume 복원, `start_resume`·`start_auto`·`do_run_full` 모두 배선).
- **미실행/중단 날짜 = 날짜만 표기·값 공란**: 시트별 **첫 추적일~마지막일 사이 모든 달력일 연속** 유지. `workbook.normalize_date_columns()`(값을 (행,날짜)로 스냅샷→정렬·재기록, 멱등·유실0)가 `apply_style` 저장마다 자동 적용. 앞으로 실행 시 `ensure_date` 갭필(직전 최신일+1~새날 사이 빈 컬럼 자동). 소급 정리 도구 `tools/normalize_dates.py`(백업 후).
- **과거 D-1 라벨 컬럼은 재라벨 안 함**(소유자: 그대로 두기·앞으로만). → 전환 경계에 **빈 하루**가 생길 수 있음(정상, 예: 09.14 다음 09.15 공란 후 09.16). 신규 계정은 첫 추적일 이전 소급 안 함(시트별 min~max만).

라이브 검증(마스터 복사본): 09.11 등 25칸 소급 삽입·순위+지표 2194셀 유실0·변경0·연속성 위반0. 실제 마스터에 소급 적용 완료(백업 `…통계_보관_날짜정렬전_260916_181634.xlsx`).

SSOT=`designs/DESIGN.md §일자 컬럼`. 관련 [[daily-stats-keyword-freeze]] [[coupang-sales-data-lag]] [[semi-auto-rank-and-exposed-name]] [[seldoc-output-format]]
