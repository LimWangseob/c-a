---
name: domain-design-elaboration-261005
description: 커머스 판로 통합앱 — 도메인 상세 설계 4건(D2 소싱·D8 정산2·3+흡수·D10 문의CS·H UI 화면) 작성(2026-10-05·설계 심화·구현 보류). 착수 선행 결정 5개 소유자/통합 대기
metadata:
  node_type: memory
  type: project
  originSessionId: a80d140c-c122-4f9a-8be2-cc678f6e0aa9
  modified: 2026-10-05T12:48:16.035Z
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

## 2차 — 멀티플랫폼 대확장 + 설계서 6건 (2026-10-05 같은 날 오후)
소유자 2차 지시: 커머스 판로 = **멀티플랫폼 통합 관리 앱**. **샵마인=주문·배송만**, 상품·판매·정산·문의(CS)는 통합앱 직접. v1=쿠팡+스마트스토어. 배치 수집(문의·판매·정산→저장→조회)·쓰기 반영(상품 CRUD·CS 답변)·정산 3층. 파1(기반 2)+파2(도메인 3) 병렬 에이전트로 설계서 6건 추가(전부 설계만·구현 보류).
- **PLATFORM_INTEGRATION.md**: 플랫폼 어댑터=L1 공유 파사드(쿠팡=browser/collector 재사용·스마트스토어=네이버 커머스 API 접근성 미확인)·배치 수집 레이어(ingest)·쓰기 §5.4·레인 P(어댑터)·J(수집) 제안. 저장=기존 백본 이원화 계승(판매/순위/재고=workbook 시계열·정산/매출/문의=registry append). 런타임 병렬 금지 불변.
- **SETTLEMENT_MODEL.md**: 정산 3층 ①플랫폼(위탁계정↔쿠팡/스마트스토어·**기구현 1단계 payout/settlement_amount=여기 소속**)→②계약(판로↔위탁자)→③채권자. 단방향·역방향 금지. 멀티플랫폼 정규화는 ①에만. 신규 제안 2모듈(platform_settlement·creditor_settlement). D8 설계와 직교(단계축=구현순서·3층축=지급흐름).
- **DOMAIN_D3_REGISTER.md**: 등록 쓰기 §5.4 7단계(빌드→검증→dry-run→승인→실행→원장 PENDING/COMMITTED→vid 재확보)·멱등·무인 금지. register/register_validate/register_store.
- **DOMAIN_D4_PRODUCT_MANAGE.md**: 조회=수집본 소비(밴↓)·변경/삭제=§5.4·소프트삭제(판매중지) 우선·하드삭제 2중확인+스냅샷·**역기록(우리 대장 쓰기)≠플랫폼 실제변경 구분**·ProductChangeDTO·approved=False→예외. product_manage/product_change_store.
- **PROCESS_OVERVIEW.md**: E2E(계정등록→상품등록→배치수집→분석/소싱→상품관리→CS→정산3층→통계)·기능목록·자동(읽기 무인)/수동(쓰기 §5.4) 경계·로드맵·미결 **U1~U20** 우선순위화.

## ⭐ 최우선 선행 미결 (소유자/라이브 — 착수 전 필수)
- ~~U1 스마트스토어 커머스 API 위탁계정 접근성~~ 🔒**보류(소유자 2026-10-05)** — 지금 추진 안 함. v1 실질 타깃=쿠팡, 스마트스토어 어댑터는 자리만. 재개 시 위탁주 협의·라이브로 접근성 확인부터.
- **U2(=M1) kw_volume·kw_suggest·kw_metrics → L1 재분류** — D2 소싱 착수 선행(통합 세션·rank R4 동형).
- **U3 WING 정산 API 세션 호출 가능 여부** — 정산 ②단계 라이브 수집 전제·사무실 diag 라이브.
- **U4 샵마인 CS 경계** — 샵마인이 이미 CS 관리하면 D10 범위 갈림([[app-scope-no-orders-shopmine]]).
- **쿠팡 쓰기 엔드포인트(등록·변경·삭제·CS답변) 라이브 캡처** — D3·D4·D10 쓰기 착수 전제(현 코드 전부 읽기전용).
- (선행) 계약 수익식 스키마(실 계약서)·채권자 배분 기준(법률 후 소유자)·분류코드→플랫폼 카테고리 매핑.

## 상태
master 반영(커밋)·게이트 10종 초록. **구현 착수 안 함**(도메인 자리·모듈·화면·인터페이스 초안만). 다음=위 선행 미결 해소 후 저위험 읽기/수집부터(§8·PROCESS_OVERVIEW 로드맵). SSOT=[[io-definition-spec]]·designs/PROCESS_OVERVIEW.md·DOMAIN_DESIGN §2/§7/§9 R5·ARCHITECTURE §2.
