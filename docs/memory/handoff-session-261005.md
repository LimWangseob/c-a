---
name: handoff-session-261005
description: 새 세션 진입점(2026-10-05 최신) — 안정성 수정·배포본·결과시트 복구 + 커머스 판로 멀티플랫폼 통합앱 설계(도메인 10건·정산3층·U2 완료·전부 구현 보류)
metadata:
  node_type: memory
  type: project
  originSessionId: a80d140c-c122-4f9a-8be2-cc678f6e0aa9
  modified: 2026-10-05T13:46:59.631Z
---

**새 세션 진입점 — 현재 상태 SSOT (2026-10-05)**. master HEAD=`3b7a0ae`·게이트 10종(L1 핀 포함)+복잡도 초록·origin 동기화.

## 이 세션에서 한 일 (전부 커밋·푸시)
### A. 운영·안정성·배포 (코드/배포)
1. **설정 st.sync 재발방지**: `_cfg_save_shared`에 QSettings `st.sync()`(저장 즉시 flush). config.json이 권위·시작 시 QSettings 교정([[handoff-session-261004]]).
2. **배포 config 씨앗 전환**: 옛 `_설정값.json` qsettings 재생성이 **프록시 키 누락** 결함 → 검증 `config.json`·`proxies.txt`를 `_씨앗\`로 통째 동봉·install.ps1 첫 설치만 복사(업데이트 보존). **배포 zip 빌드·검증 완료**([[exe-packaging-deploy]]).
3. **결과시트 수동 복구**: 10-03·10-04 무인이 옛 URL로 gsheet 반영 실패(원장404·재고400) → z14 output 스냅샷의 통계 마스터에서 `push_gsheet`로 **결과시트 복구**(10.03·10.04 데이터 반영 확인·웰빙곳간 등). SA=`sheet-bot@totalseller-sheets`. ⚠**운용 PC 설정 URL 4개 교정(설정 탭 저장)은 사람 조치 대기** — 안 하면 다음 무인도 실패(올바른 URL 4개는 [[handoff-session-261004]]).

### B. 커머스 판로 설계 (⛔전부 설계만·구현 보류·코드 변경 0)
소유자 방향: 커머스 판로 = **멀티플랫폼 이커머스 통합 관리 앱**. 병렬 도메인 설계 에이전트로 설계서 다수 작성([[domain-design-elaboration-261005]]).
4. **입출력 정의서 v1**: 파일 칸↔화면 칸 1:1(128칸)·구현 SSOT=designs/IO_DEFINITION.md([[io-definition-spec]]).
5. **5영역 도메인 배정**: 계약·사업·채권자→D8 · 마케팅→D1 · 문의(CS)→신규 D10. DOMAIN_DESIGN §9 R5.
6. **범위 확장**: 상품·판매·정산·문의(CS)=통합앱 / **샵마인=주문·배송만**([[app-scope-no-orders-shopmine]]). v1 플랫폼=**쿠팡 우선·스마트스토어 API 위탁접근 보류**(어댑터 자리만·U1).
7. **설계서 10건**: PLATFORM_INTEGRATION(어댑터 L1 파사드·배치 수집·쓰기 §5.4)·SETTLEMENT_MODEL(정산 3층 ①플랫폼→②계약→③채권자)·PROCESS_OVERVIEW(E2E·기능목록·미결 U1~U20)·DOMAIN_D2_SOURCING·D3_REGISTER·D4_PRODUCT_MANAGE·D8_SETTLEMENT_PHASE23·D10_CS·UI_SCREENS. 전부 기존 코드/계층 재사용 우선·신규 모듈 제안만.
8. **✅U2=kw 조회 프리미티브 L1 재분류**: kw_volume·kw_suggest·kw_metrics를 rank R4 동형으로 L1화(코드 이동 없음·핀 pin_l1_contract §7-d/L1-5·L1_CONTRACT·ARCHITECTURE·DOMAIN_DESIGN §5.3-b). kw_ai·kw_recommend는 L2 유지. D2 선행 M1 해소.
9. **🎨시안(디자인) 반영 = H_ui 레인 위임**: 소유자 "디자인에도 모두 반영". 시안 '커머스 판로 화면 시안'(claude.ai Design 캔버스·114파일·H_ui 소유·현재 오프라인)은 통합 세션이 직접 편집 안 함(블라인드 대규모 편집=충돌·일관성 위험). **반영 명세를 designs/UI_SCREENS.md '시안 반영 지시' 절에 작성**(멀티플랫폼·스마트스토어 보류 배지·샵마인 범위밖 유지·D3/D4/D10 화면·정산 3층·사이드바 네비·민감도 UI·디자인 컨셉) → **H_ui 재가동 시 적용 대기**. 전달 메시지는 H_ui 오프라인이라 미도달(재가동 시 UI_SCREENS에서 픽업).

## ⭐ 다음 — 구현 착수 전 선행(소유자/라이브)
- **U3 WING 정산 API 세션 호출 가능 여부**(diag 사무실 라이브) — 정산 ②단계 수집 전제.
- **U4 샵마인 CS 경계**(소유자) — D10 범위(통계/수동트래커/수집).
- **쿠팡 쓰기 엔드포인트(등록·변경·삭제·CS답변) 라이브 캡처** — D3·D4·D10 쓰기 전제(현 코드 전부 읽기전용).
- (선행) 계약 수익식 스키마(실 계약서)·채권자 배분 기준(법률 후 소유자)·분류코드→플랫폼 카테고리 매핑.
- U1(스마트스토어 API)·U2(kw→L1)는 각각 보류·완료.

## ⭐⭐ 구현 착수 준비 (2026-10-05 말·소유자 "설계서 기준 실제 구현")
**설계 단계 종료 → 구현 착수.** 단 소유자 지시로 **그리기(구현) 전 세션 정리→새 세션/병렬 도메인 세션에서 진행**. 구현 SSOT=**`docs/IMPL_PLAN.md`**(도메인별 모듈·순서·게이트·블로커·레인). 레인=`docs/PARALLEL_DEV.md`(신규 I 소싱·J 수집·P 어댑터·K CS·D3·D4 추가).
- **오프라인·읽기 우선**. 각 도메인 `tools/verify_*_offline.py` 게이트 먼저/동시(실 API 금지). 기존 L0/L1 재사용·최소 diff·CC≤15·파일≤600·건강파일 미접촉.
- **추천 1차 착수(오프라인·비겹침·저위험)**: ①D8 흡수 원장(E·contract/worklog/creditor_store·registry 패턴) ②D10 CS 수동 트래커(K·cs_model/store/gsheet) ③D2 소싱(I·kw L1 재사용·U2 완료). 셋 병렬 가능(worktree·게이트 초록 후 push·master 병합 직렬).
- **플랫폼 어댑터(P)·수집(J)** = browser/collector 공유 접점 → **통제 세션 동반**으로 그다음.
- **쓰기(D3 등록·D4 변경/삭제·D10 응대)·라이브 수집(D8 2단계)** = Wave 2·**선행 미결 해소 후**(U3 WING 정산 API·쿠팡 쓰기 엔드포인트 라이브 캡처·U4 샵마인 CS 경계). 🔒U1 스마트스토어 보류.
- **UI(H_ui)**: v3.3 네비 셸·theme_qt·화면(현 7탭 보존 승격). 시안=H_ui 소유.
- ⚠worktree 세션은 메모리 자동주입 안 됨 → 착수 시 `docs/IMPL_PLAN.md`·`designs/DOMAIN_*`·`docs/PARALLEL_DEV.md` **읽기**가 출발점(PARALLEL_DEV 체크리스트). 새 worktree=`python tools/install_hooks.py` 1회.

## 게이트/규칙
커밋 전 `python tools/run_checks.py`(10종) 초록. 공유파일(CLAUDE.md·DECISIONS·designs)·master 병합=통합 세션 직렬. 설계만·구현 보류 유지.

[[domain-design-elaboration-261005]] · [[io-definition-spec]] · [[app-scope-no-orders-shopmine]] · [[exe-packaging-deploy]] · [[handoff-session-261004]]
