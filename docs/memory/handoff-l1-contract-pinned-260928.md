---
name: handoff-l1-contract-pinned-260928
description: L1 데이터 백본 공개 API 계약 목록화+핀 고정 완료(통합/플랫폼 세션·2026-09-28). 밑줄 진입점 3건 공개화. 다음=도메인 레인 병렬 or 신규 도메인 스캐폴딩.
metadata:
  node_type: memory
  type: project
  originSessionId: 36f26e1a-466b-4e04-9814-a4e46aceddf1
  modified: 2026-09-28T11:14:16.682Z
---

**통합(플랫폼) 세션이 아키텍처 이행 §4.2 "L1 공개 API 계약 고정"을 완료(2026-09-28).**
SSOT=`docs/L1_CONTRACT.md`, 핀=`tools/pin_l1_contract.py`(run_checks 5번째·전체 9종·quick 8종).

## 무엇을 했나
- **실측 기반 계약 확정**: Explore 서브에이전트로 호출처 grep → 도메인(L2)/조립(L3)이 **실제 부르는** L1 진입점만 계약화(정직한 최소 표면). 안 부르는 함수는 내부용.
- **핀 비교 방식(견고)**: 시그니처 전체 문자열이 아니라 각 파라미터의 **(종류 P/K/A/W/O, 이름, 기본값 유무)** 만 비교 → 파라미터 추가·삭제·이름변경·필수화·함수삭제는 잡되, 타입힌트 정리 같은 무해한 변경엔 안 깨짐. 골든값은 `inspect`로 뽑아 박제.
- **계약 범위**: collector(discover·fetch_sales_roster·fetch_vendor_inventory·fetch_inventory·fetch_product_ids·products_from_vendor_inventory·sale_status_by_vid·save_discovered·reset_raw·raw_dumps + 데이터클래스/예외. ⛔`fetch_sales_details`=내부전용·계약 아님) · input_list(parse_*·read_ledger_rows·write_ledger_inventory·validate_input_list·build_idf + Account/Product/Option/InputList) · workbook.OutputWorkbook(핵심12 파라미터구조 + 실사용55 존재) · gsheet_index(roster_from_workbook·sync_index·delete_accounts·delete_renamed_accounts·read_marketing·apply_marketing) · gsheet_stats(push_statistics·merge_staff_keywords) · pipeline_gsheet(push_gsheet·pull_gsheet_keywords·backup_sources·restore_master_from_gsheet·push_ledger_inventory) · registry(sync·Registry·run_sync·run_backfill·parse_ledger).
- **registry 포함**(소유자 결정): live(pipeline·ui) 미연동·tools 전용이지만 L1 백본 설계 확정이라 2단계(앱 연계) 대비 선고정.

## 밑줄 진입점 3건 공개화(소유자 결정 B·행동 불변)
"내부용(밑줄) 문패인데 프로덕션이 부르던" 계약 누수 3건을 정식 이름으로 리네이밍:
- `pipeline_gsheet._push_gsheet` → **`push_gsheet`** (호출처 pipeline.py·pipeline_ranks.py + pipeline 재수출)
- `pipeline_gsheet._pull_gsheet_keywords` → **`pull_gsheet_keywords`** (pipeline.py + 재수출)
- `input_list._build_idf` → **`build_idf`** (product_match.py)
편집 5파일(pipeline_gsheet·pipeline·pipeline_ranks·input_list·product_match)·이름만 변경. 도구/테스트엔 이 3이름 참조 없어 게이트 수정 불필요.

## 검증
게이트 **9종 전부 초록**(리네이밍 행동 불변 확증)+복잡도 exit0. 복잡도 경고 7개는 전부 기존 괴물함수(무관). ⚠라이브 무관(순수 인터페이스 고정·런타임 로직 미변경).

## 남은 계약 누수(정리 후보·별도 사이클, L1_CONTRACT §9)
- `gsheet_stats` ↞ `workbook`(=workbook_common) 내부 상수/함수(`_COL_KW`·`_key` 등) import.
- `registry_model` ↞ `input_list` 내부 밑줄 심볼 import(registry 패밀리 내부).
- 도구: `collector._raw_add`·`OutputWorkbook._FILL_*`·`gsheet_index._auto_cells_request` 등 pin/verify 참조.

## 다음 착수점
아키텍처 §5: **②신규 도메인 스캐폴딩(소싱/등록/주문)** 또는 **③기존 도메인(이미지·정산·키워드) 개선을 레인 병렬**. L1 계약이 고정됐으니 도메인 세션이 L1 시그니처를 깨면 핀이 잡음. 관련=[[handoff-architecture-parallel-260928]]·[[code-health-regression-gate]]·[[no-silent-fallback-principle]].
