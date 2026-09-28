# 도메인 분리·연계·통제 설계 (DOMAIN_DESIGN)

> 목적: **이커머스 통합 관리/운영 앱**(로그인/세션관리 · 상품 분석 · 소싱 · 상품 등록 · 상품 관리 ·
> 주문 · 배송 · 통계)을 기존 소스코드 위에 **점진 확장**하기 위한 도메인 지도·역할·상호 연계/통제/공유 설계.
> 계층 골격=`docs/ARCHITECTURE.md`, L1 계약=`docs/L1_CONTRACT.md`, 세션 운영=`docs/PARALLEL_DEV.md`, 게이트=`designs/CODE_HEALTH_PLAN.md`.
> ⚠ **전체 재작성 금지** — 신규 도메인은 기존 계층 위에 얹고, 기존은 제자리 정리(측정 기반).

이 문서는 **전수 실측(2026-09-28)** 을 근거로 한다: src 43개 모듈 13,377 LOC 의존 그래프, UI 탭 구성,
WING API 호출 패턴, 세션/크리덴셜 기반. "전체 분석"이 아니라 아래에 커버리지를 명시한 실측이다.

---

## 0. 실측 요약 (설계의 근거)

**의존 그래프 (src 내부 import·43모듈·13,377 LOC)** — `←N`=피참조수, 대표만:
- **최하층(고피참조·leaf)**: `config`(←22) · `credstore`·`gsheet`(←2) · `apppaths`·`wing_session`·`keyword_store`(leaf).
- **저수준 플랫폼**: `browser`(←6→config·human_typing) · `human_typing/mouse` · `session_state/store` · `gsheet_api`(←3→credstore·gsheet).
- **데이터 백본**: `input_list`(←7) · `workbook`(←6→common/render/index) · `collector`(→config·input_list·report) · `registry_*` · `gsheet_index/stats` · `product_match`.
- **도메인**: `kw_*`(recommend←4·ai·volume·suggest·metrics) · `rank`(←6) · `detail_images`(leaf·고립) · `registry_gsheet`(원장 진입).
- **조립/표현**: `pipeline`(←0·13개 의존) + `pipeline_sales/ranks/process/gsheet/paths` · `ui/app_qt`·`ui/app`.

**계층은 이미 잠재**(config/browser/세션=밑, collector/workbook/input_list/registry=백본, kw/rank/이미지=도메인, pipeline=조립).

**경계 위반 실측 2건** (도메인끼리 직접 import — ARCHITECTURE 규칙 위반):
- `kw_recommend` → `rank` (순위 진단에 순위 조회 직접 호출)
- `kw_metrics` → `rank`
→ 해소책은 §5.3(rank 를 "조회 프리미티브"로 재분류).

**신규 도메인(소싱·등록·상품관리 일부·주문·배송) = 코드 전무.** 재사용 기반은 완비(§4).

---

## 1. 도메인 지도 (기존 + 신규)

계층은 4단(L0 플랫폼 / L1 데이터 백본 / L2 도메인 / L3 조립·표현). **도메인은 L2**이며, 각 도메인이
"세션 분리 단위(레인)"가 된다. 아래 표에서 **상태**: ✅기존 구현 · 🟡부분 · 🆕신규 구축.

| # | 도메인(레인) | 상태 | 한 줄 역할 |
|---|---|---|---|
| — | **L0 로그인/세션관리** | ✅ | 모든 도메인이 공유하는 로그인된 WING 세션·크리덴셜·세션영속(플랫폼) |
| D1 | **상품 분석**(키워드·순위·노출) | ✅ | 키워드 발굴·AI 선정·오가닉 순위·노출/판매/방문 지표 |
| D2 | **소싱** | 🆕 | 판매 상품 발굴·경쟁 분석·후보 선별(분석 재사용) |
| D3 | **상품 등록** | 🆕 | WING 상품 등록/수정(쓰기)·옵션·이미지 연계 |
| D4 | **상품 관리**(재고·가격·판매상태) | 🟡 | 재고현황·가격·판매상태 조회는 있음, 변경(쓰기)은 신규 |
| D5 | **주문** | 🆕 | 주문 조회·상태 추적·처리(확인/취소) |
| D6 | **배송** | 🆕 | 발주/입고(로켓그로스)·출고·송장·배송상태 |
| D7 | **이미지** | ✅ | 상세페이지 대표/상세 이미지 추출(CDP attach) |
| D8 | **정산/원장** | 🟡 | 관리·계정·상품·거래 이력 원장(등록원장 1단계 구현·앱 미연동) |
| D9 | **통계/출력** | ✅ | 전 도메인 결과를 워크북·구글시트로 집계·시각화 |

> 정합: ARCHITECTURE §2의 L2 "상품분석·이미지·정산·(신규)소싱/등록/주문"을 **배송·상품관리·통계까지 구체화**한 것.

---

## 2. 도메인별 역할·모듈·갭

### L0 로그인/세션관리 (공유 플랫폼 — 도메인 아님, 전 도메인이 호출)
- **모듈**: `browser.WingBrowser`(로그인 세션·CDP·표시제어)·`wing_session`(생존·vendorId·세션3요소 회수)·`session_store`(계정별 세션 blob DPAPI 영속)·`session_state`(관측 SQLite)·`credstore`(비번·API키 DPAPI).
- **재사용 규약**: 신규 도메인은 `with WingBrowser(profile_dir=...) as wb:` 로 열고 `wb.page` 에 same-origin fetch → 로그인 세션·XSRF 그대로 사용(실측 §4). **런타임 브라우저는 항상 1개**(rank_browser·로그인 동시 금지·CLAUDE.md).
- **갭**: 세션 blob 복원 소비(load→주입 재로그인 생략)는 미구현(현재 `profile_dir` 재사용 의존). 신규 도메인 확장 전 사무실 라이브 1회 검증 필요(wing_session 자체 명시).

### D1 상품 분석 ✅
- **모듈**: `kw_*`(ai·recommend·volume·suggest·metrics)·`rank`·`collector`(수집)·`product_match`·`report`.
- **역할**: AI 앵커 키워드 선정 + 네이버 검색량 + 쿠팡 자동완성 → 순위 진단·권고제목 / 오가닉 순위(최대 300위) / 판매지표·재고 수집.
- **갭 없음**(핵심 완성). 단 경계위반(kw→rank) §5.3.

### D2 소싱 🆕
- **역할**: 신규 판매 상품 발굴·시장/경쟁 분석·후보 스코어링·의사결정 지원.
- **재사용**: D1(키워드·순위·검색량)·쿠팡 자동완성(`kw_suggest`)·네이버 API(`kw_volume`). 신규=경쟁강도(쿠팡 검색결과 총 상품수·CLAUDE.md HANDOFF §4-1 보류 항목)·마진/원가 입력.
- **신규 모듈(제안)**: `sourcing.py`(후보 수집·스코어)·`sourcing_store.py`(후보 원장). L1 재사용, D1과는 백본 경유(직접 import 금지).

### D3 상품 등록 🆕 (쓰기 도메인 — 고위험)
- **역할**: WING 상품 등록/수정(제목·옵션·가격·이미지·배송정보) 자동화.
- **재사용**: `WingBrowser` 세션 + collector의 `_POST_JSON_JS`(x-xsrf-token) 패턴. 신규 엔드포인트(상품등록 API)·이미지(D7 연계).
- **⚠쓰기 안전 필수**(§5.4): dry-run 미리보기 → 사람 승인 → 실행 → 원장 기록. 위탁계정이라 오작동=실운영 사고.
- **신규 모듈(제안)**: `register.py`(등록/수정 요청 빌더·검증)·`register_store.py`(변경 이력).

### D4 상품 관리 🟡
- **역할**: 재고·가격·판매상태 조회(있음) + 변경(신규). 재고 역기록(관리대장 AD열)은 D8/입력 연계로 존재.
- **재사용**: collector(`fetch_inventory`·`fetch_vendor_inventory`·`sale_status_by_vid`)·workbook(지표행). 신규=가격/재고 변경(쓰기).
- **갭**: 변경은 쓰기 도메인(§5.4 규약). 조회는 D1 수집과 공유(collector 프리미티브).

### D5 주문 🆕 (조회→처리)
- **역할**: 주문 목록·상세·상태 추적, 처리(발주확인·취소·문의). 
- **재사용**: `WingBrowser` 세션 + fetch 패턴. 신규 엔드포인트(주문조회 API·경로 미확인).
- **데이터 성격**: 상태가 계속 바뀌는 거래 → **원장(append+상태 replay) 백본**이 적합(§5.2). workbook(셀 시계열)엔 부적합.
- **신규 모듈(제안)**: `order.py`(조회·처리)·`order_ledger.py`(주문 상태 이력, registry 패턴 확장).

### D6 배송 🆕
- **역할**: 로켓그로스 발주/입고(관리대장에 입고 요약 존재)·판매자배송 출고·송장·배송상태.
- **실마리**: `wing_session._DELIVERY_URL = /tenants/sfl-portal/delivery/management`(현재 vendorId 추출용 HTML만·API 호출 없음).
- **재사용**: 세션·fetch 패턴·D8 원장(입고 이력). 신규=배송/출고 엔드포인트.
- **신규 모듈(제안)**: `shipping.py`·`shipping_ledger.py`.

### D7 이미지 ✅
- **모듈**: `detail_images`(CDP attach·완전 고립). **가장 깨끗한 도메인**(의존 0). 등록(D3)이 이미지 재사용.

### D8 정산/원장 🟡
- **모듈**: `registry_*`(model·core·apply·history·rename·registry·gsheet)·`input_list` 역기록.
- **역할**: 관리·계정·상품·거래 이력을 **지우지 않고 쌓고, 이력 replay로 현재 상태 계산**(등록원장 1단계·SSOT=`designs/LEDGER_REGISTRY.md`).
- **핵심 가치**: 이 "append 원장" 패턴이 신규 거래 도메인(주문 D5·배송 D6·등록 변경 D3)의 **데이터 백본 표준**이 된다(§5.2). 정산은 이 원장을 소비.
- **갭**: 앱 연계(2단계) 미완·live 미연동.

### D9 통계/출력 ✅
- **모듈**: `workbook*`·`gsheet_index/stats`·`pipeline_gsheet`.
- **역할**: 전 도메인 결과를 사업자별 시트·계정목록·통계 마스터·구글시트로 집계. 분석(D1) 중심이나 향후 소싱/주문/배송 지표도 여기로 융합.

---

## 3. 계층 재확정 (경계 규칙의 기준)

```
L0 플랫폼(공유·가장 안정): config·appconfig·apppaths·credstore·browser(+human_*)·
        session_store·session_state·wing_session·gsheet_api·gsheet
L1 데이터 백본(공유): 
   · 조회 프리미티브: collector(WING 데이터 API)  [·rank(오가닉 순위)=편입 여부 §5.3 재검토 중]
   · 저장/출력: workbook*·gsheet_index·gsheet_stats·pipeline_gsheet
   · 입력/원장: input_list·registry_*·product_match·report·keyword_store
L2 도메인(개별·레인): D1 분석(kw_*)·D2 소싱·D3 등록·D4 상품관리·D5 주문·D6 배송·D7 이미지·D8 정산상위·D9 통계상위
L3 조립·표현: pipeline(+_sales/_ranks/_process/_paths/_gsheet)·ui/app_qt·ui/app
```

**의존 방향(불변)**: L2는 **아래(L0/L1)로만** 의존. **도메인끼리 직접 import 금지.** 융합은 L1 백본 경유(§5).

---

## 4. 상호 연계 — 융합 메커니즘 (재사용 + 결합)

도메인이 서로를 직접 부르지 않고도 협력하는 두 축:

### 4.1 공유 세션(수집·쓰기의 관문)
- 모든 WING 접근은 **하나의 로그인 세션**(`WingBrowser`+`profile_dir`)을 통과. `wb.page` 에 same-origin fetch.
- 공통 호출 템플릿(실측): collector `_POST_JSON_JS`/`_GET_JSON_JS`(cookie의 `XSRF-TOKEN`→`x-xsrf-token` 헤더·`credentials:include`). **신규 도메인은 새 엔드포인트 상수 + 파서만 추가.**
- 규약: 세션 관문은 L0. 도메인은 세션을 **열지 않고**(단일 브라우저 원칙) 조립(L3 pipeline)이 연 세션 페이지를 받아 쓴다.

### 4.2 공유 데이터 백본 — **이원화**(핵심 설계 결정)
현재 백본은 엑셀 워크북+구글시트 하나. 분석·통계 집계엔 맞으나 거래(주문/배송)엔 부적합. → 두 종류로:

| 백본 | 성격 | 담는 것 | 모듈 |
|---|---|---|---|
| **분석/통계 출력** | 상품×키워드×날짜 셀 시계열 | 노출/판매/방문/순위/재고 지표, 계정목록, 통계 | `workbook*`·`gsheet_*` |
| **거래/상태 원장** | append + 이력 replay로 현재상태 | 계정·상품 관리이력, 주문·배송·등록 변경 이력 | `registry_*` 확장(D5/D6/D3 원장) |

- **잇는 정체성 키(이미 확립)**: `vendorItemId`(vid·불변 앵커)·`productId`(노출상품)·계정ID·사업자명. 도메인은 이 키로 서로의 데이터를 참조(직접 호출 아님).
- 예) 주문(D5)이 상품명을 알려면 workbook/원장에서 vid로 조회, 등록(D3)이 이미지가 필요하면 D7 산출물을 경로/키로 참조.

### 4.3 조립 계층이 오케스트레이션
- 도메인 간 순서·전달은 **L3 pipeline**이 담당(도메인은 서로 모른 채 백본에만 읽고 씀). 현재 `run_full`이 판매수집→키워드→순위를 잇는 방식을 신규 도메인 스테이지로 확장.

---

## 5. 상호 통제

### 5.1 통제 4축 (ARCHITECTURE §3 확장)
1. **의존 방향 규칙**: L2는 아래로만·도메인 직접 import 금지 → `check_complexity`/리뷰로 감시(향후 import 린트 추가 가능).
2. **공유 자원 단일 작성자**: 공유 파일은 **통합(플랫폼) 세션만** 수정. 도메인 세션은 호출만·필요 시 요청(PARALLEL_DEV §공유).
3. **계약 핀 + 게이트**: L1 공개 API=`pin_l1_contract` 로 고정(시그니처 파괴 즉시 빨감). 커밋/푸시 전 `run_checks` 9종+`check_complexity` 초록.
4. **직렬 병합**: 도메인 레인은 자기 worktree/브랜치, master 병합은 통합 세션이 한 브랜치씩(게이트 재실행).

### 5.2 거래 원장 통제(신규 쓰기 도메인의 무결성)
- 주문·배송·등록 변경은 **원장에 먼저 기록(append)** → 상태는 이력 replay로 계산(registry 패턴). 되돌림·감사추적·중복방지 확보.
- 무결성 규칙 재사용: 번호 연속·이력 전부 되돌리면 빈 원장(손수정 검출)·실행마다 로컬 백업(registry 기설계).

### 5.3 경계 위반 해소 — `rank` 재분류 (⚠소유자 재검토 중·보류, 2026-09-28)
- 실측: `kw_recommend`·`kw_metrics`(D1 도메인)가 `rank` 직접 import. `rank`는 browser 기반 **순위 조회 프리미티브**로 collector 와 동급(WING/공개 SERP 조회).
- **제안(보류)**: `rank`·`collector` 를 **L1 조회 프리미티브**로 규정 → "도메인→L1" 이 되어 규칙 합치(재분류만·물리 이동 없음·최소 diff). 향후 여러 도메인(소싱 D2도 순위 필요)이 안전하게 공유.
- **대안**: (a) rank 를 L1 로 재분류(위 제안) · (b) rank 는 D1(분석) 내부에 두고, 다른 도메인은 D1 이 제공하는 인터페이스 경유(직접 import 금지 유지) · (c) 현행 유지(위반 허용). 소유자 재검토 후 확정 → 그때 §3 계층도·이 절 갱신.

### 5.4 쓰기 도메인 안전 규약 (D3 등록·D4 변경·D5 주문처리·D6 배송)
현재 전 코드가 **읽기 전용**. 쓰기 도입 시 강제:
1. **dry-run 미리보기**(무엇이 바뀌는지 산출) → 2. **사람 승인 게이트**(UI 확인) → 3. **실행** → 4. **원장 기록**.
- 위탁계정·Akamai·실운영 사고 위험 → 자동 무인 쓰기 금지(초기엔 반자동·사람 확인). 폴백 최소화 원칙([[no-silent-fallback-principle]]).

---

## 6. 공유 자원 (직렬화 — 통합 세션 단독 작성)
- 코드: `config`·`pipeline`(오케스트레이션)·`browser`·`credstore`·`apppaths`·`appconfig`·`session_*`·`wing_session`·`gsheet_api`.
- 계약/게이트: `docs/L1_CONTRACT.md`·`tools/pin_l1_contract.py`·`tools/verify_*`·`simulate_pipeline`·`pin_*`.
- 문서/정책: `CLAUDE.md`·`designs/`·`docs/`(이 문서 포함)·`docs/DECISIONS.md`.

---

## 7. 세션(레인) 배치

| 세션 | 담당 | 권한 |
|---|---|---|
| **통합(플랫폼)** | L0·L1 계약·`config`·`pipeline`·병합 | 공유 단독 수정·계약 버전관리·직렬 병합 |
| **D1 분석** | `kw_*`·`rank`(호출)·`collector`·`product_match`·`report` | 자기 레인·L0/L1 호출만 |
| **D2 소싱** 🆕 | `sourcing*`(신규) | 〃 |
| **D3 등록** 🆕 | `register*`(신규)+D7 연계 | 〃·쓰기 안전 규약 |
| **D5 주문 / D6 배송** 🆕 | `order*`·`shipping*`(신규) | 〃·거래 원장 |
| **D7 이미지** | `detail_images` | 고립·가장 안전 |
| **D8 정산/원장** | `registry_*`·`input_list` 역기록 | 〃 |
| **D9 통계/출력** | `workbook*`·`gsheet_*` | 전 모듈이 읽되 편집은 여기만 |
| **H UI** | `ui/*` | 〃 |

- **런타임은 병렬화 금지**(단일 브라우저·위탁계정·Akamai·단일 시트) → 실행은 야간 단일 순차·라이브 한 번에 한 세션. **개발만 병렬**(2~3레인 권장).
- 신규 도메인 착수 시 그 도메인 모듈 파일집합을 소유한 레인 추가 → 자연 확장.

---

## 8. 점진 이행 로드맵 (big-bang 금지·측정 기반)

1. **경계·계약 고정 ✅**(완료): 계층 문서·L1 계약 핀(`docs/L1_CONTRACT.md`).
2. **경계 위반 정리**: `rank` L1 재분류 명문화(§5.3)·import 방향 감시(선택: 린트).
3. **거래 원장 백본 확립**: registry 패턴을 주문/배송/등록 변경 이력용으로 일반화(공용 원장 프레임)→ D8 확장.
4. **신규 도메인은 규칙대로 신설**: 우선순위 예시 — (a) D2 소싱(분석 재사용·읽기·저위험) → (b) D5 주문 조회(읽기) → (c) D6 배송 조회 → (d) D3 등록·D4 변경·주문 처리(쓰기·안전 규약 필수).
5. **UI·조립 확장**: 각 신규 도메인마다 UI 탭 + pipeline 스테이지(현 패턴 재사용).
6. **기존 강결합 완화**: 측정(죽은코드·복잡도·중복)으로 제자리 점진(급한 재배치 금지).

---

## 9. 리스크·결정 사항 (소유자 판단)

상태: ✅확정 · ⏳보류(구현/재검토 시 결정) — 2026-09-28 소유자 1차 판단 반영.

- **R1 쓰기 도메인 범위·시점** ⏳: 등록/주문처리/배송/가격변경은 실운영 사고 위험이 큼. 초기엔 **조회만**(소싱·주문/배송 조회)으로 가치 검증 후 쓰기 도입 권장 — 구현 착수 시 확정.
- **R2 거래 원장 저장소** ⏳미정: 주문/배송 이력을 registry식 **구글시트/원장 파일**로 갈지, **로컬 SQLite**(대량·트랜잭션 유리)로 갈지 — **해당 도메인 구현 착수 시 결정**(소유자). 참고: registry=시트+로컬백업, session_state=SQLite(관측).
- **R3 신규 도메인 착수 순서** ⏳: 로드맵 §8-4 우선순위(소싱→주문조회→배송조회→쓰기)는 **제안**. **구현은 별도 세션에서**(이번엔 설계만 확정·소유자 결정).
- **R4 rank 재분류** ⏳재검토: L1 조회 프리미티브 편입은 **보류**(§5.3 대안 a/b/c 중 소유자 재검토 후 확정).

**이번 확정(✅)**: 도메인 지도(§1)·계층 규칙(§3, rank 편입만 보류)·연계 메커니즘(§4, 세션 공유+백본 이원화)·
통제 4축(§5.1)·쓰기 안전 규약(§5.4)·세션 레인 배치(§7). 구현 착수는 소유자 지시 시.

SSOT = 이 문서(도메인 상세) · `docs/ARCHITECTURE.md`(계층 골격) · `docs/L1_CONTRACT.md`(계약) · `docs/PARALLEL_DEV.md`(운영).
