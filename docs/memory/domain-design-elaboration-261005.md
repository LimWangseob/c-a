---
name: domain-design-elaboration-261005
description: 커머스 판로 통합앱 — 도메인 상세 설계 4건(D2 소싱·D8 정산2·3+흡수·D10 문의CS·H UI 화면) 작성(2026-10-05·설계 심화·구현 보류). 착수 선행 결정 5개 소유자/통합 대기
metadata:
  node_type: memory
  type: project
  originSessionId: a80d140c-c122-4f9a-8be2-cc678f6e0aa9
  modified: 2026-10-05T11:57:46.669Z
---

**커머스 판로(이커머스 통합 관리 앱) 도메인 설계 심화 — 1차(2026-10-05)**. 소유자 지시: 설계 심화(구현 보류 유지)·병렬 도메인 에이전트. 통합 세션이 4개 에이전트를 worktree 없이 각자 설계서 1개씩 쓰게 띄우고 교차연결·커밋(코드 변경 0).

## 산출 설계서 4건 (SSOT·designs/)
- **D2 소싱**: `designs/DOMAIN_D2_SOURCING.md` — 읽기 전용·저위험. 재사용=kw_volume/suggest/metrics·rank·collector. 경쟁강도=네이버쇼핑 종료→`kw_metrics.page1_competition`(1페이지 신호) 채택 제안. 신규 모듈 제안=sourcing/sourcing_store/sourcing_score·레인 I·화면 02-x 제안.
- **D8 정산 2·3단계 + 흡수**: `designs/DOMAIN_D8_SETTLEMENT_PHASE23.md` — 1단계(오프라인 계산) 이미 구현됨. 2단계=collector 확장(안a·XSRF 패턴 재사용)·3단계=계약 수익식. 흡수 3영역(계약·사업·채권자)=contract_store/worklog_store/creditor_store 독립 모듈(registry 패턴 모방·공용 프레임은 중복 측정 후). 채권자=R2② 파일분리·가림·무인 쓰기 금지.
- **D10 문의/CS**: `designs/DOMAIN_D10_CS.md` — 신규 도메인. 문의 건 append 원장+상태 replay(cs_model/cs_store/cs_gsheet). 화면 09-x 제안. 1단계=수동 트래커(수집 0·저위험).
- **H UI 화면**: `designs/UI_SCREENS.md` — IO_DEFINITION 메뉴 ID 25개→왼쪽 사이드바+QStackedWidget 셸(현 app_qt 7탭 **내용 0변경**으로 페이지 승격=1단계 저위험). 디자인 컨셉(보라·흰 카드)·민감도 2단계 UI·주문/배송 화면 배제(샵마인).

## ⭐ 착수 선행 결정 (소유자/통합 세션 대기 — 아직 미결)
1. **M1(D2 선행)**: `kw_volume·kw_suggest·kw_metrics`를 L1 조회 프리미티브로 재분류할지([[fingerprint-consistency]] 아님 — rank R4 선례 동형·코드 이동 없음·문서+핀). 공유 자원이라 D2 레인 단독 불가. 이 결정 없이는 D2 반쪽.
2. **D10 샵마인 CS 경계(최우선)**: 샵마인이 이미 고객 문의 관리하면 D10 범위가 통계추적/수동트래커/수집 중 어디인지. 2026-10-02 "중복 개발 방지"와 충돌 가능([[app-scope-no-orders-shopmine]]).
3. **UI 권한모델**: 역할(대표·정산담당·일반)·채권자 숨김·열람 기록 저장 위치(단일 PC라 "설정 로컬 플래그로 시작" 제안).
4. **디자인 컨셉 전면 적용 시점**([[decision-design-concept-261003]] "앱 적용 보류" 상태) — QSS 토큰화만 vs 전면 리스타일.
5. **WING 정산 API**: 위탁계정은 판매자 OpenAPI 키 불가 → WING 세션 쿠키로 settlement-histories 호출 가능한지 사무실 라이브 실측 선행(diag 제안).

## 상태
master 반영(커밋)·게이트 10종 초록. **구현 착수 안 함**(도메인 자리·모듈·화면 구조·인터페이스 초안만). 다음=위 5개 선행 결정 후 단계별 구현(저위험 읽기부터·§8 로드맵). SSOT=[[io-definition-spec]]·DOMAIN_DESIGN §2/§7/§8/§9 R5.
