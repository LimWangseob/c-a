# 구현 계획 (IMPL_PLAN) — 설계 → 실제 구현 전환 (2026-10-05 착수 준비)

> 소유자 지시(2026-10-05): "설계서 기준 실제 구현." **설계 단계 종료·구현 착수**. 단 **그리기(구현) 전 세션 정리→새 세션/병렬 도메인 세션에서 진행**. 이 문서 = 각 구현 세션의 **착수 SSOT**(무엇을·어떤 순서로·어디까지·어느 레인).
> ⚠ 여전히 **런타임 병렬 금지**(단일 위탁 세션·Akamai·단일 마스터/시트) · **최소 diff·재사용 우선·전체 재작성 금지** · **커밋 전 `python tools/run_checks.py` 초록** · 새 모듈 CC≤15·파일≤600 지향 · 건강(A/B) 파일 미접촉.

## 0. 구현 원칙
- **오프라인·읽기 우선(risk-ascending)**: 실 API/쓰기 없는 모듈부터. 각 도메인은 **오프라인 게이트(`tools/verify_*_offline.py`) 먼저 or 동시** 추가(실 API·로그인 금지·모킹).
- **쓰기(플랫폼 반영)·라이브 수집은 선행 미결 해소 후**(§3). 그 전까지 설계·오프라인 스캐폴딩·dry-run 경로만.
- **기존 자산 재사용**: 신규 모듈은 L0/L1(browser·collector·rank·registry·workbook·gsheet)·L1 계약(`docs/L1_CONTRACT.md`)만 호출. 도메인끼리 직접 import 금지.
- **착수 전 핀**: 건드리는 기존 동작은 `simulate_pipeline`/`verify_offline`/`pin_*`이 덮는지 먼저 확인(얇으면 시나리오 추가 후).

## 1. 구현 웨이브 (순서)

### Wave 1 — 오프라인·읽기 (선행 미결 불필요·지금 착수 가능)
| 도메인 | 신규 모듈(설계 제안) | 오프라인 게이트 | 레인 |
|---|---|---|---|
| **D2 소싱** | `sourcing.py`·`sourcing_store.py`·`sourcing_score.py`(순수) | `verify_sourcing_offline.py`(페이크 어댑터) | **I 소싱** |
| **D8 흡수 원장** | `contract_store.py`·`worklog_store.py`·`creditor_store.py`(registry 패턴 모방·독립) | `verify_contract_offline.py`·`verify_creditor_offline.py` | **E 원장/정산** |
| **D10 CS 1단계(수동 트래커)** | `cs_model.py`·`cs_store.py`·`cs_gsheet.py` | `verify_cs_offline.py`(실 API 0) | **K CS** |
| **플랫폼 어댑터 골격** | `platform/base.py`(PlatformAdapter 프로토콜·DTO·capabilities)·`platform/coupang.py`(기존 browser/collector/rank **읽기** 래핑·얇은 파사드) | `verify_platform_offline.py`(페이크 어댑터·capabilities) | **P 어댑터**(통제 경유=browser/collector 공유) |
| **배치 수집 골격** | `ingest/runner.py`·`ingest/store.py`·`ingest/freshness.py`(저장·신선도·실패/재시도·저장만·수집 로직은 어댑터 호출) | `verify_ingest_offline.py` | **J 수집** |

### Wave 2 — 라이브 수집·쓰기 (선행 미결 해소 후 §3)
| 도메인 | 모듈 | 선행 |
|---|---|---|
| **D8 2단계 라이브 수집** | `settlement_collect`(collector 확장·XSRF 패턴) | U3 WING 정산 API 세션 호출 확인 |
| **D8 3단계 계약 정산** | `settlement.py`(수익식)·`platform_settlement.py`(① 정규화)·`creditor_settlement.py`(③ 배분) | 실 계약서 스키마·채권자 배분(법률) |
| **D3 상품 등록(쓰기)** | `register.py`·`register_validate.py`·`register_store.py` | 쿠팡 등록 엔드포인트 **라이브 캡처**·§5.4 |
| **D4 변경/삭제(쓰기)** | `product_manage.py`·`product_change_store.py` | 변경/삭제 엔드포인트 캡처·§5.4 |
| **D10 2단계 수집·응대 쓰기** | 어댑터 CS 읽기·답변 쓰기 | 쿠팡 문의 경로·§5.4 |
| **스마트스토어 어댑터** | `platform/smartstore.py` | 🔒 U1 보류(위탁 API 접근성) |

### UI (H_ui 레인·병행)
- `ui/theme_qt.py`(QSS 토큰·디자인 컨셉)·네비 셸(사이드바+QStackedWidget·현 app_qt 7탭 **내용 보존 승격**)·v3.3 메뉴(대13·중84·`designs/UI_SCREENS.md`). ⚠입력 화면(08-1·11-x·01-x·03-x·06-x·05-1 등)은 `input_list` 다중시트 확장(OPERATION_DATA_MODEL 3단계)에 의존 → 통제 세션 동반. **시안(Design 캔버스)=H_ui 소유**.

## 2. 도메인별 구현 카드 (설계 SSOT)
- **D2 소싱**: `designs/DOMAIN_D2_SOURCING.md` · 읽기 전용·저위험. kw 조회 프리미티브(L1·U2 완료) 호출. 경쟁강도=`kw_metrics.page1_competition`.
- **D3 상품 등록**: `designs/DOMAIN_D3_REGISTER.md` · 쓰기 §5.4 7단계·멱등·무인 금지.
- **D4 변경/삭제**: `designs/DOMAIN_D4_PRODUCT_MANAGE.md` · 조회=수집본·소프트삭제 기본·역기록≠플랫폼쓰기.
- **D8 정산**: `designs/DOMAIN_D8_SETTLEMENT_PHASE23.md`+`designs/SETTLEMENT_MODEL.md`(3층)+1단계 기구현(payout·settlement_amount·settlement_parse·holiday_kr).
- **D10 CS**: `designs/DOMAIN_D10_CS.md` · 1단계 수동 트래커·메뉴 05(문의/리뷰관리).
- **플랫폼·수집**: `designs/PLATFORM_INTEGRATION.md`(어댑터 L1 파사드·배치 수집).
- **전체 흐름/기능**: `designs/PROCESS_OVERVIEW.md`(E2E·미결 U1~U20) · **입출력 1:1**: `designs/IO_DEFINITION.md`(137칸) · **화면/메뉴**: `designs/UI_SCREENS.md`(v3.3 대13·중84).

## 3. 선행 미결(블로커) — Wave 2 전 해소 필요
- **U3 WING 정산 API 세션 호출 가능 여부** — 사무실 라이브 diag(정산 2단계).
- **쿠팡 쓰기 엔드포인트(등록·변경·삭제·CS답변) 라이브 캡처** — D3·D4·D10 쓰기(현 코드 전부 읽기 전용).
- **U4 샵마인 CS 경계** — D10 수집/응대 범위(수동 트래커 1단계는 무관).
- **계약 수익식 스키마**(실 계약서)·**채권자 배분 기준**(법률 후 소유자).
- 🔒 **U1 스마트스토어 API 위탁접근 = 보류**(v1=쿠팡).
- ✅ **U2 kw→L1 재분류 = 완료**(D2 착수 가능).

## 4. 레인·세션 배치 (PARALLEL_DEV 확장)
- 신규 레인: **I 소싱**(`sourcing*`)·**J 수집**(`ingest/*`)·**P 어댑터**(`platform/*`·⚠browser/collector 공유=통제 경유)·**K CS**(`cs_*`·`ui/cs_panel_qt`). D3=register*·D4=product_manage*·D8 흡수=E 레인 확장(contract/worklog/creditor_store).
- **병렬 2~3 레인 권장**·비겹침·worktree+브랜치·master 병합 직렬·게이트 이중.
- **런타임(라이브) 테스트=한 번에 한 세션·사무실**.

## 추천 1차 착수 순번 (오프라인·독립·저위험)
1. **D8 흡수 원장**(E) — registry 패턴 재사용·오프라인 게이트 명확.
2. **D10 CS 수동 트래커**(K) — 독립·오프라인.
3. **D2 소싱**(I) — kw L1 재사용·읽기.
→ 셋은 서로 비겹침·오프라인 게이트로 안전. 플랫폼/수집 골격(P·J)은 공유자원(browser/collector) 접점이라 **통제 세션 동반**으로 그 다음. 쓰기(D3·D4)·라이브 수집은 §3 선행 후.

SSOT = 이 문서 + 각 `designs/DOMAIN_*.md`·`PLATFORM_INTEGRATION.md`·`SETTLEMENT_MODEL.md`·`PROCESS_OVERVIEW.md`·`UI_SCREENS.md`·`IO_DEFINITION.md` · 레인/병합=`docs/PARALLEL_DEV.md` · 계층=`docs/ARCHITECTURE.md`·`docs/DOMAIN_DESIGN.md`·`docs/L1_CONTRACT.md`.
