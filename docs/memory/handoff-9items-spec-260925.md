---
name: handoff-9items-spec-260925
description: 소유자 9개 요구(2026-09-25) 정밀분석+계획. 시작 프리플라이트 싱크체크·백업·계정목록 열순서/폭·⑤사업자명 그룹핑(아키텍처)·⑥이력무관 삭제(정책전환)·상태싱크·이중비고·키워드동결. 진행순서=⑤부터. 미구현(새 세션·핀 먼저).
metadata:
  node_type: memory
  type: project
  originSessionId: d8c440ae-0a9a-47f8-a6d2-d96209afecc7
  modified: 2026-09-25T13:58:20.391Z
---

**소유자 요구(2026-09-25, 이미지=로움컨설팅 2계정ID 예시) 9건**. 정밀분석+적용방안 확정, **구현은 미착수**(항목5=아키텍처라 새 세션·핀 먼저). 진행순서 소유자 확정=**⑤(그룹핑) 먼저**, 그룹키=**사업자명만 같으면 한 그룹**.

## 현행 정체성 모델(항목5 변경 표면·근거)
- `input_list.Account`=**계정ID 단위**(`by_id[acct]`), `label=business_name or representative or account_id`. 같은 사업자명=같은 label.
- `workbook._계정정보`(_ACCT_SHEET)=**사업자→계정ID 1행**(`set_account_id` overwrite·`account_id_of` 1개 반환). 3열=판매수집일·4열=대표자.
- 계정ID 1:1 가정이 박힌 곳: `set_account_id`/`account_id_of`(overwrite·단일), gsheet `roster_from_workbook` band=계정ID, `gsheet_index.delete_accounts`=**계정ID 매칭**, `mark_sales_collected`(사업자 시트 단위), **오늘(9/25) 만든 일원화**(`_consolidate_renamed_accounts`·`merge_account`·`delete_renamed_accounts`)가 전부 계정ID 기준.
- ⇒ 다계정ID 사업자에서 계정ID 메타 유실·별도 처리. **원리상 같은 label이면 한 시트여야** 하나 메타/gsheet가 계정ID 1:1이라 어긋남.

## ✅ ⑤ 구현 완료(2026-09-25·라이브 남음) — [[feature-business-name-grouping]]
S1~S5 커밋(master)·핀 verify_offline[17·18·19]·verify_gsheet[6b]·게이트6+복잡도 초록. 착수 전 소유자 확정=검증 완화(허용+[SYNC] 경고)·계정마다 따로 로그인·수집. 계정ID=상품 속성(메타 col12)·스탬프 계정 단위(`_수집스탬프`)·밴드 사업자명 기준·일원화 다계정 인지(발산=보류+경고). ⚠라이브·재배포 남음. **다음=①②③(프리플라이트) 또는 ⑥⑦⑧⑨④**. 아래는 원 분석(참고).

## ⑤ 적용방안(그룹키=사업자명)
- **시트=사업자명 1개**, 계정ID를 **상품(줄) 속성**으로 이전: `_상품ID` 메타에 상품별 계정ID 열 추가(또는 새 메타), `set_account_id`→사업자별 **계정ID 집합** 보관.
- 로그인·수집은 여전히 **계정ID 단위**(Account)지만 결과 기록 대상 시트=사업자명. `_process_account`/`_finish`가 계정ID→사업자시트로 상품 적재(계정ID를 상품 메타로 태깅).
- gsheet 계정목록: 한 사업자=밴드 1색, 각 상품 줄에 그 상품의 계정ID(항목4 열순서와 함께). `delete_accounts`/`delete_renamed_accounts`/band를 **사업자 기준**으로 재설계(계정ID는 상품속성).
- ⚠**오늘 만든 일원화와 충돌 조정 필요**: 사업자명 기준이 되면 "시트명 변경(계정ID 동일)" 일원화 로직과 겹침 → 재정의(사업자명=키라 rename 개념 달라짐).
- **핀 먼저**: pin_apply_style·verify_offline·verify_gsheet에 "다계정ID 사업자=한 시트·상품별 계정ID·목록 한 밴드" 시나리오 추가 후 분해.

## 나머지 8건 현행/방안(요약)
- **①②③ 시작 프리플라이트**: 앱 시작 첫 루틴에 (a)2파일 백업[`backup_sources` 이미 있음·호출시점을 앱시작으로] (b)관리대장↔결과 싱크체크(계정·사업자·취소선·상품명 유사도[product_match 이미 있음]) `[SYNC]` 로그. 불일치=관리대장 기준(⑥·⑦).
- **④ 계정목록**: 계정ID를 상품명 **왼쪽**으로(현행 대표자·사업자·상품·계정ID → 대표자·사업자·계정ID·상품). 안정키 메모=B(사업자) 재배선 주의(`_ensure_rep_column`·`_auto_cells_request`). 셀 폭 자동맞춤(엑셀 column_dimensions + 구글 updateDimensionProperties pixelSize, 내용 길이 기반). 엑셀·구글 패리티.
- **⑥ 이력무관 삭제(정책 전환)**: 관리대장에 없으면 이력 무관 완전삭제(백업이 안전망). ⚠**되돌림**=기존 "판매중지 유지+경고"·`_sweep_dead_duplicates` blanket금지·판매상태 불일치경고(⑧ 일부)를 폐기/축소. 근거=소유자 명시(백업으로 과거 확인). [[fix-from-real-evidence]] 메모 남길 것.
- **⑦ 계정목록 상태=대장 상태 싱크**: 9/24 "계정목록 상태=대장만"(`status_of`) 반영됨. 소유자 "지금도 다르게 표기" → **실측 재검증**(대장 상태컬럼/취소선→status_of 경로 어디서 어긋나는지) `[STATUS]` 로그.
- **⑧ 이중 비고**: 비고(고정)=**대장 상태**, 날짜칸 비고=**그날 쿠팡 상품조회 상태**(대조용). 현행 `M_SALE_STATUS`(판매상태 지표행=쿠팡, 실행일마다)+불일치경고 존재 → **배치가 이 요구와 정확히 맞는지 재검증**. `[SALESTATUS]` 로그.
- **⑨ 키워드**: 1건이라도 입력=담당자 입력 간주→채워진 것만 검색량·순위. 가변개수(4 초과/미만·일부 공란). 현행 동결(`product_keywords` 비지않으면 AI생략)+`_pull_gsheet_keywords`+검색량공란채움 존재 → 규칙 명시 재검증+경계 테스트 `[KEYWORD]` 로그.

## 공통
- 각 항목 **오류추적 로그**(`[SYNC]/[STATUS]/[SALESTATUS]/[KEYWORD]` 등) 심을 것.
- 매 단계 게이트 6종+복잡도 초록·핀 먼저(감시파일)·커밋 작게·4묶음(코드+DESIGN+DECISIONS+메모리).
- 제안 순서(소유자=⑤부터): ⑤ → ①②③ → ⑥⑦⑧ → ⑨ → ④.

관련: [[feature-account-consolidation]] [[handoff-3decisions-260924]] [[seldoc-output-format]] [[gsheet-unified-spec]] [[code-health-regression-gate]] [[fix-from-real-evidence]].
