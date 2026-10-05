---
name: io-definition-spec
description: 입출력 정의서 v1(designs/IO_DEFINITION.md) — 앱이 읽고/쓰는 모든 파일 칸(128)을 화면 칸과 1:1로 맞춘 기준표. 구현 시 SSOT·현재는 정의/시안만(구현 보류)
metadata:
  node_type: memory
  type: reference
  originSessionId: a80d140c-c122-4f9a-8be2-cc678f6e0aa9
  modified: 2026-10-05T10:38:43.653Z
---

**입출력 정의서 v1 = 파일 칸 ↔ 화면 칸 1:1 기준표** (SSOT=`designs/IO_DEFINITION.md`, 2026-10-05 H_ui 작성→통합 세션 레포 반영, 커밋 `3b8d3c6`·CLAUDE.md SSOT 목록 등재).

- **목적**: 앱이 읽고/쓰는 모든 파일(관리대장→운영대장 개편안·재고현황·판매분석 xlsx·결과시트·셀독등록원장·config.json·credstore·proxies.txt)의 **칸 128개**를 화면(메뉴 ID)·필수/자동/직원·형식·검사 규칙·쓰는 주체·민감도와 1:1로 묶음. **실제 앱 구현 시 기준**. 같은 내용=시안 'F. 입출력 정의서' 보드 + 엑셀 `커머스판로_입출력정의서_v1_20261005.xlsx`.
- **상태**: 정의·시안만 — **앱은 아직 구글시트 파일을 읽고 씀(구현 보류)**. 앱 코드 변경 없음. 입력 화면 구조는 운영대장 개편안([[handoff-operation-data-model-261001]]) 기준(예: 그로스 입고=1건 1줄).
- **핵심 규칙 예**(기존 정책과 정합): 작업수량 ≤ 요청수량·완료일 ≥ 요청일 · 셀독+당근+자사 = 현재고(불일치=저장 거부) · 기호만 상품명('--') 제외 · 키워드 띄어쓰기 다르면 별개 · 비밀번호/키 원문은 화면·결과·로그 금지 · 판매처 비번 1회 오류 재시도 금지.
- **민감 처리**: 비밀(화면·결과·로그 원문 금지=비번·API/SA 키·proxies.txt)·민감가림(권한자만=사업자번호·계좌·채권자 이름/연락처). 정의서엔 **칸·규칙만, 비밀값 원문 없음**.
- **5영역 도메인 배정 ✅확정(소유자 2026-10-05·DOMAIN_DESIGN §9 R5)**: 계약·사업(업무일지)·채권자 → **D8 정산/원장 흡수** · 마케팅(체험단·광고) → **D1 상품 분석 흡수** · 문의(CS) → **신규 D10**(앱 포함). ⚠문의(CS)=app-scope 수정(주문 D5·배송 D6은 범위밖 유지·[[app-scope-no-orders-shopmine]]). 채권자=파일 분리·권한 제한([[business-context-consignment-creditors]]). 칸수 재배분: D8 42·D1 21·D4 39·D9 16·L0 10·D10 0(향후).

[[decision-storage-gsheet-4rules]] · [[handoff-operation-data-model-261001]] · [[gsheet-unified-spec]]
