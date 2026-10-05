---
name: io-definition-spec
description: 입출력 정의서 v1(designs/IO_DEFINITION.md) — 앱이 읽고/쓰는 모든 파일 칸(128)을 화면 칸과 1:1로 맞춘 기준표. 구현 시 SSOT·현재는 정의/시안만(구현 보류)
metadata:
  node_type: memory
  type: reference
  originSessionId: a80d140c-c122-4f9a-8be2-cc678f6e0aa9
  modified: 2026-10-05T07:38:11.616Z
---

**입출력 정의서 v1 = 파일 칸 ↔ 화면 칸 1:1 기준표** (SSOT=`designs/IO_DEFINITION.md`, 2026-10-05 H_ui 작성→통합 세션 레포 반영, 커밋 `3b8d3c6`·CLAUDE.md SSOT 목록 등재).

- **목적**: 앱이 읽고/쓰는 모든 파일(관리대장→운영대장 개편안·재고현황·판매분석 xlsx·결과시트·셀독등록원장·config.json·credstore·proxies.txt)의 **칸 128개**를 화면(메뉴 ID)·필수/자동/직원·형식·검사 규칙·쓰는 주체·민감도와 1:1로 묶음. **실제 앱 구현 시 기준**. 같은 내용=시안 'F. 입출력 정의서' 보드 + 엑셀 `커머스판로_입출력정의서_v1_20261005.xlsx`.
- **상태**: 정의·시안만 — **앱은 아직 구글시트 파일을 읽고 씀(구현 보류)**. 앱 코드 변경 없음. 입력 화면 구조는 운영대장 개편안([[handoff-operation-data-model-261001]]) 기준(예: 그로스 입고=1건 1줄).
- **핵심 규칙 예**(기존 정책과 정합): 작업수량 ≤ 요청수량·완료일 ≥ 요청일 · 셀독+당근+자사 = 현재고(불일치=저장 거부) · 기호만 상품명('--') 제외 · 키워드 띄어쓰기 다르면 별개 · 비밀번호/키 원문은 화면·결과·로그 금지 · 판매처 비번 1회 오류 재시도 금지.
- **민감 처리**: 비밀(화면·결과·로그 원문 금지=비번·API/SA 키·proxies.txt)·민감가림(권한자만=사업자번호·계좌·채권자 이름/연락처). 정의서엔 **칸·규칙만, 비밀값 원문 없음**.
- **미배정(소유자 판단 대기·DOMAIN_DESIGN §1 주석·§9 R5)**: **사업·계약·마케팅(체험단·광고)·문의(CS)·채권자** 5영역(31칸)이 D1~D9에 자리 없음. 계약은 D8 흡수 가능·문의는 샵마인 범위밖 가능([[app-scope-no-orders-shopmine]])·채권자는 파일 분리 규칙([[business-context-consignment-creditors]]).

[[decision-storage-gsheet-4rules]] · [[handoff-operation-data-model-261001]] · [[gsheet-unified-spec]]
