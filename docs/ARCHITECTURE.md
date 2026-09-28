# 아키텍처 & 세션 분리 설계 (ARCHITECTURE)

> 궁극 목표: **상품 분석 → 소싱 → 등록 → 주문 → 정산 → 통계** 전 과정을 관리·운영하는 커머스 앱.
> 현재는 초기 단계(분석·통계·정산 원장 일부 구축). 기능을 **공통 모듈 / 개별(도메인) 모듈**로 체계 분할해
> **재사용**(도메인이 공통을 호출)과 **융합**(도메인끼리 데이터 백본 경유로 결합)을 가능케 한다.
> ⚠ **전체 재작성 금지** — 아래는 **점진 이행** 설계다(신규 도메인은 이 계층 위에 얹고, 기존은 제자리 정리).
> 운영 규칙(worktree·레인·병합)=`docs/PARALLEL_DEV.md`. 게이트=`designs/CODE_HEALTH_PLAN.md`.

## 1. 현재 소스 실측 (import in-degree = 결합도, 2026-09-28)
- **공통 코어(피참조↑)**: `config`(←22) · `input_list`(←7) · `workbook`(←6) · `browser`(←6) · `rank`(←6) ·
  `registry_model`(←6) · `registry_core`(←5) · `kw_ai`/`kw_recommend`/`kw_volume`(←4) · `gsheet_api`(←3).
- **고립 leaf(피참조 0)**: `detail_images`(deps 0·최고 고립) · `keyword_store` · `pipeline`(최상위 오케스트레이터·deps 13) ·
  `registry_gsheet`(원장 시트 진입).
- 결론: 이미 **계층 형태**가 잠재. config/browser/workbook/input_list/registry 가 밑단, kw_*/rank/detail 이 도메인, pipeline 이 조립.

## 2. 목표 계층 (공통 ↔ 개별)

```
L0 플랫폼(공통·가장 안정·변경=계약): config·appconfig·apppaths·credstore·browser(+human_typing/mouse)·
      session_store/state·wing_session·gsheet_api·gsheet
L1 데이터 백본(공통): 조회 프리미티브(collector·rank ← 2026-09-28 rank 편입·§DOMAIN_DESIGN 5.3)·출력저장(workbook*)·입력/원장(input_list·registry_*)·시트동기(gsheet_index·gsheet_stats·pipeline_gsheet)
L2 도메인(개별·병렬 개발 단위):
     · 상품분석(키워드·노출): kw_*·keyword_store·product_match·report  (rank·collector=L1 조회 프리미티브·호출)
     · 이미지: detail_images
     · 정산/원장: registry_* 상위·input_list 역기록
     · (신규) 소싱 · 등록 · 주문 : 아직 없음 → L0/L1 위에 새 모듈로 추가
L3 조립·표현: pipeline(+_sales/_ranks/_process/_paths/_gsheet) · ui/app_qt·ui/app
```

**의존 방향 규칙(재사용·융합의 핵심)**: L2 도메인은 **아래(L0/L1)로만** 의존. **도메인끼리 직접 import 금지** —
융합은 **데이터 백본(workbook/registry/gsheet) 또는 정의된 인터페이스** 경유. 이래야 도메인 추가·교체가 서로를 안 깬다.

## 3. 세션 분리 & 상호 통제

| 세션 | 담당 계층/도메인 | 권한 |
|---|---|---|
| **통합(플랫폼) 세션** | L0·L1 계약 + `config`·`pipeline` 오케스트레이션 + 병합 | 공유 자원 **단독 수정**·도메인 병합 직렬화·계약(인터페이스) 버전관리 |
| **도메인 세션(병렬)** | L2 개별 모듈(레인 A~H, `docs/PARALLEL_DEV.md`) | 자기 레인 파일만 편집·L0/L1 은 **호출만**(변경 필요 시 통합 세션에 요청) |

- **상호 통제 = 의존 방향 + 공유 단일작성자 + 게이트 + 직렬 병합**. 도메인은 자기 worktree/브랜치, 통합 세션이 master 병합.
- 신규 도메인(소싱/등록/주문)은 **새 레인**으로 추가(그 도메인 모듈 파일 집합을 소유) → 자연히 병렬 확장.

## 4. 점진 이행 로드맵 (big-bang 금지)
1. **경계 명문화(문서만·지금)**: 이 문서로 L0/L1/L2 경계·의존 규칙 확정. 코드 이동 없음.
2. **계약 지점 식별 ✅(2026-09-28 완료)**: 도메인이 L1을 부르는 실제 진입함수(collector `discover`/`fetch_*`, workbook 기록 API, input_list/gsheet/registry read/write)를 실측 목록화 → "공개 API"로 고정. SSOT=`docs/L1_CONTRACT.md`, 핀=`tools/pin_l1_contract.py`(run_checks 편입). 부수로 밑줄 진입점 3건(`push_gsheet`·`pull_gsheet_keywords`·`build_idf`) 공개화.
3. **신규 도메인은 규칙대로**: 소싱/등록/주문은 처음부터 L2 규칙(아래로만 의존·백본 경유 융합)으로 신설.
4. **기존 강결합 완화는 측정 기반**(죽은코드·복잡도·중복)으로 제자리 점진 — 급하게 재배치 금지.

## 5. 다음 세션 착수점 (이 문서의 목적)
- 새 세션은 이 문서 + `docs/PARALLEL_DEV.md` + `MEMORY.md` 를 먼저 읽는다.
- **1차 작업 후보**(병렬 가능·독립도순): ① L1 "공개 API 계약" 목록화(통합 세션) **✅완료(`docs/L1_CONTRACT.md`)** ② 신규 도메인 스캐폴딩(소싱 등) ③ 기존 도메인(이미지·정산·키워드) 개선을 각 레인 병렬.
- 병합·공유파일은 통합 세션 경유. 2~3레인부터 시작(§PARALLEL_DEV).

SSOT = 이 문서(아키텍처·계층·세션모델) · `docs/PARALLEL_DEV.md`(운영 how-to) · `docs/DECISIONS.md`(확정 결정).
