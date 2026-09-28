---
name: handoff-domain-design-260928
description: 이커머스 통합 앱 도메인 분리·연계·통제 설계 확정(2026-09-28·구현은 나중). SSOT=docs/DOMAIN_DESIGN.md. rank재분류·저장소·착수순서·쓰기범위 보류.
metadata:
  node_type: memory
  type: project
  originSessionId: 36f26e1a-466b-4e04-9814-a4e46aceddf1
  modified: 2026-09-28T13:06:59.175Z
---

**이커머스 통합 앱(로그인/세션·분석·소싱·등록·상품관리·주문·배송·통계) 도메인 설계 확정(2026-09-28).**
SSOT=`docs/DOMAIN_DESIGN.md`(ARCHITECTURE 계층골격 + L1_CONTRACT 계약을 잇는 도메인 상세판).
근거=전수 실측: src 43모듈 13,377 LOC 의존그래프 + UI 탭 + WING API 패턴 + 세션/크리덴셜 기반.

## 도메인 지도 (9 + 공유 세션층)
- L0 로그인/세션(공유·도메인 아님): browser.WingBrowser·wing_session·session_store·session_state·credstore.
- ✅기존: **D1 분석**(kw_*·rank·collector·product_match·report)·**D7 이미지**(detail_images·완전고립)·**D9 통계/출력**(workbook*·gsheet_*).
- 🟡부분: **D4 상품관리**(재고/가격/상태 조회 있음·변경 신규)·**D8 정산/원장**(registry_* 1단계·앱 미연동).
- 🆕전무: **D2 소싱**·**D3 등록**·**D5 주문**·**D6 배송**(코드에 없음·배송URL 실마리 /tenants/sfl-portal/delivery/…만).

## 확정된 설계 핵심
1. **연계=공유 세션 + 백본 이원화**: 신규 도메인은 `with WingBrowser(profile_dir=) as wb:`+`wb.page`에 collector식 same-origin fetch(cookie XSRF-TOKEN→x-xsrf-token 헤더) 재사용("새 엔드포인트 상수+파서+스테이지+UI탭"만 추가). 데이터 백본 2종=(분석/통계=workbook·gsheet) + (거래/상태=registry식 append 원장·이력 replay로 상태계산). 잇는 정체성키=vid·productId·계정ID·사업자명. 도메인끼리 직접 import 금지·백본 경유 융합.
2. **통제 4축**: 의존방향(L2는 아래로만)+공유 단일작성자(통합세션)+계약핀/게이트(run_checks 9종+pin_l1_contract+복잡도)+직렬병합.
3. **쓰기 안전 규약**(D3등록·D4변경·D5주문처리·D6배송): 현재 전 코드 읽기전용 → 쓰기는 dry-run→사람승인→실행→원장기록. 위탁계정·Akamai 사고방지·무인 쓰기 금지.
4. **세션 레인**: 통합(L0/L1·config·pipeline·병합)+도메인 레인 병렬(개발만·런타임은 단일 순차).

## ✅R4 확정(2026-09-28) — rank = L1 조회 프리미티브(a안)
kw_recommend·kw_metrics가 rank 직접 import한 경계위반을, rank를 collector와 함께 **L1 조회 프리미티브**로 재분류해 해소(도메인→L1 합법). rank는 순위 가져오는 순수 조회 수단·6곳(도메인2+조립4) 공유. **코드 이동 없음**·문서(DOMAIN_DESIGN §3·§5.3·ARCHITECTURE §2·L1_CONTRACT §7-b)+핀(pin_l1_contract rank 섹션)만. 기각=(b)조립도 rank 직접사용이라 우회 인위적·(c)규칙 무력화. 규율=rank 순수 조회만(순위 도메인 로직은 pipeline_ranks=조립). 남은 누수=kw_metrics↞rank._load_results(공개화 후보). 게이트 9종+복잡도 초록.

## ⏳보류(소유자 결정 대기 — 아직 확정 아님)
- **R2 거래 저장소**: 주문/배송 이력=구글시트/원장파일 vs 로컬 SQLite → 해당 도메인 구현 착수 시 결정.
- **R3 착수 순서**: 제안=소싱→주문조회→배송조회→쓰기(저위험 조회 먼저). **구현은 별도 세션**(소유자: 이번엔 설계만 확정).
- **R1 쓰기 범위·시점**: 초기 조회만 검증 후 쓰기 도입 권장.

## 다음
소유자 지시 시 구현 착수. 착수 전 R2~R4 확정 필요. 관련=[[handoff-l1-contract-pinned-260928]]·[[handoff-architecture-parallel-260928]]·[[no-silent-fallback-principle]]·[[login-policy-real-browser-only]].
