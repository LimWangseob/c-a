# 설계: 플랫폼 통합 + 배치 수집 레이어 (PLATFORM_INTEGRATION)

> 상태: **설계 초안(2026-10-05) · 구현 보류.** 소유자 2026-10-05 새 방향("커머스 판로 = 멀티플랫폼 통합 관리 앱")을 전제로 한
> 플랫폼 어댑터·배치 수집 레이어 설계. 이 문서가 **플랫폼 추상화·수집·읽기/쓰기 반영**의 SSOT다.
> 상위 설계=`docs/ARCHITECTURE.md`(4계층) · `docs/DOMAIN_DESIGN.md`(§4 연계·§5 통제·§5.4 쓰기 안전·§7 레인) · L1 계약=`docs/L1_CONTRACT.md` · 입출력=`designs/IO_DEFINITION.md`(판매처·수집 자료 칸).
> ⚠ **전체 재작성 금지** — 기존 L0/L1 계층(WingBrowser·collector·rank·workbook·registry·gsheet) **위에 얹는다**. 재사용 우선, 복붙 아님.
> 소유자 확정은 "(확정)", 그 외는 "(제안)"/"(미결)"로 표기한다. **구현은 소유자 지시 시 착수.**

---

## 0. 전제 (소유자 2026-10-05 · 이 설계의 토대)

| # | 전제 | 확정도 |
|---|---|---|
| T1 | 커머스 판로 = **멀티플랫폼 통합 관리 앱**. v1 플랫폼 = **쿠팡(WING) + 스마트스토어(네이버 커머스 API)** | (확정) |
| T2 | 나머지(토스쇼핑·G마켓·당근)는 **어댑터 확장 지점만** 열어둠(이번 구현 안 함) | (확정) |
| T3 | **샵마인 = 주문·배송만**. 상품·판매·정산·문의(CS)는 통합앱이 직접 담당 | (확정) |
| T4 | **배치 수집 레이어**: 각 플랫폼의 **문의·판매·정산** 자료를 주기적으로 당겨 저장 → 앱은 **조회**(수집본 조회 기본·실시간 호출 아님) | (확정) |
| T5 | **쓰기(온라인 반영)**: 상품 등록/변경/삭제 + CS 답변을 플랫폼에 실제 반영 — §5.4 쓰기 안전 규약 준수, 위탁계정 밴 위험이라 고위험 | (확정) |

- 정합: 입출력 정의서(`IO_DEFINITION §1`)의 **「판매처」 선택값**이 이미 `쿠팡/스마트스토어/토스쇼핑/G마켓/당근`으로 정의돼 있어 데이터 모델은 멀티플랫폼을 이미 수용(계정관리 08-1). 이 문서는 그 데이터 모델에 **플랫폼별 수집·쓰기 경로**를 붙이는 설계다.

---

## 1. 목표·범위

### 1.1 목표
- 플랫폼마다 다른 인증/API/DOM을 **공통 인터페이스(어댑터)** 뒤로 숨겨, 도메인(D1 분석·D4 관리·D8 정산·D10 CS)이 **플랫폼을 모른 채** 데이터를 읽고 쓰게 한다.
- **배치 수집 레이어**가 문의·판매·정산을 주기적으로 당겨 백본에 저장 → 앱 화면은 그 **수집본을 조회**(빠르고 안전·실시간 호출 아님).
- 쓰기(상품 CRUD·CS 답변)는 **미리보기→승인→실행→원장 기록**(§5.4)으로만.

### 1.2 범위 (명확한 선)
| 영역 | 범위 | 담당 |
|---|---|---|
| 상품(조회·등록·변경·삭제) | **범위 안** | 통합앱 D3/D4 (어댑터 쓰기) |
| 판매·노출·순위 지표 수집 | **범위 안** | 통합앱 D1 (어댑터 읽기) |
| 정산·매출 자료 수집 | **범위 안** | 통합앱 D8 (어댑터 읽기) |
| 문의(CS) 수집·응대 | **범위 안**(소유자 2026-10-05) | 통합앱 D10 (어댑터 읽기/쓰기) |
| **주문**(발주·취소·구매고객 응대) | ⛔ **범위 밖** | 샵마인(상용) |
| **배송**(출고·송장·배송상태) | ⛔ **범위 밖** | 샵마인(상용) |
| **클레임**(반품·교환·환불 처리) | ⛔ **범위 밖** | 샵마인(상용) |

> 근거=`DOMAIN_DESIGN §2`(D5·D6 범위밖)·[[app-scope-no-orders-shopmine]]. 수집·쓰기 어댑터에 **주문/배송 엔드포인트를 넣지 않는다**(문의 수집이 주문·배송 성격이면 접수·상태만 기록, 처리는 샵마인으로 넘김 — `DOMAIN_D10_CS §1.3`).

---

## 2. 플랫폼 어댑터 추상화

### 2.1 핵심 결정 — 어댑터는 **L1 경계의 공유 파사드**(제안)
- 어댑터는 **여러 도메인(D1·D4·D8·D10)이 공유**하는 조회/쓰기 수단이다. 공유 자원이므로 **도메인(L2)이 아니라 L0/L1**에 둔다.
  - **인증/세션 관문 = L0**(기존 `browser`·`wing_session`·`session_*`·`credstore`와 동급). 스마트스토어 토큰 관리도 L0.
  - **읽기/쓰기 호출(=조회 프리미티브 + 쓰기 빌더) = L1**(기존 `collector`·`rank`가 L1 조회 프리미티브인 것과 동형 — `DOMAIN_DESIGN §5.3`·R4 선례).
- 이렇게 두면 `D1→어댑터`, `D4→어댑터`가 "도메인→L1" 이 되어 **의존 방향 규칙**(L2는 아래로만·도메인끼리 import 금지)과 합치한다.

### 2.2 공통 인터페이스 (제안 — `PlatformAdapter` 프로토콜)
> 파이썬 `typing.Protocol`(또는 ABC). **능력 선언(capabilities)** 으로 플랫폼마다 지원 범위 차이를 표현(미지원은 `NotSupported` 예외·fail-closed, 폴백 금지 [[no-silent-fallback-principle]]).

| 분류 | 메서드(제안) | 의미 | 쿠팡 매핑 | 스마트스토어 매핑 |
|---|---|---|---|---|
| 식별 | `platform_id` | `"coupang"`·`"smartstore"` | 상수 | 상수 |
| 능력 | `capabilities()` | 지원 기능 집합(읽기/쓰기별) | 읽기 전부·쓰기 일부 | API 가능 여부 따라 (미결) |
| 인증 | `session(account) -> Session` | 로그인/토큰 확보·생존 | `WingBrowser`+`wing_session.is_alive` | OAuth2 토큰(커머스 API) |
| 읽기 | `fetch_products(session)` | 상품·옵션·vid | `collector.fetch_vendor_inventory`+`products_from_vendor_inventory` | 커머스 상품 목록 API |
| 읽기 | `fetch_sales(session, d_from, d_to)` | 판매·방문·노출 | `collector.discover`/`fetch_sales_roster` | 커머스 통계/정산 API |
| 읽기 | `fetch_inventory(session)` | 재고 | `collector.fetch_inventory` | 커머스 재고 API |
| 읽기 | `fetch_settlement(session, period)` | 정산·매출 | (2단계·collector 확장·`DOMAIN_D8 §2`) | 커머스 정산 API |
| 읽기 | `fetch_inquiries(session, since)` | 문의(CS) | (미확인·`DOMAIN_D10 §2`) | 커머스 문의 API |
| 읽기 | `organic_rank(...)` | 오가닉 순위 | `rank.organic_ranks`(비로그인·프록시) | 플랫폼 공개 검색(별도·미결) |
| 쓰기 | `register_product(session, spec)` | 상품 등록 | WING 등록 API(미확인)+`_POST_JSON_JS` | 커머스 상품 등록 API |
| 쓰기 | `update_product(session, change)` | 가격·옵션·상태 변경 | WING 수정 API(미확인) | 커머스 상품 수정 API |
| 쓰기 | `reply_inquiry(session, reply)` | CS 답변 | (미확인) | 커머스 문의 답변 API |

- **반환 타입 = 플랫폼 중립 DTO**(제안): `ProductDTO`·`SalesRowDTO`·`SettlementRowDTO`·`InquiryDTO`. 어댑터가 플랫폼 응답을 이 DTO로 **정규화**(쿠팡 `VendorInventoryListing`→`ProductDTO`). 도메인은 DTO만 본다. 정체성 키(`vendorItemId`/`productId`/계정ID/사업자명)는 `DOMAIN_DESIGN §4.2`의 기존 키 체계를 그대로 DTO에 실어 **플랫폼 교차 참조**를 가능케 한다(스마트스토어는 그쪽 상품ID를 `platform_product_id`로).

### 2.3 쿠팡 어댑터 — 기존 자산 100% 재사용 매핑 (확정 가능·코드 이동 없음)
- `CoupangAdapter`는 **새 로직을 거의 안 만든다.** 기존 L0/L1을 조립·정규화하는 **얇은 파사드**다.
- 세션 관문: `with WingBrowser(profile_dir=...) as wb:` → `wb.page`(로그인 세션 same-origin). `authenticated()`(윙 대시보드 URL + `KEYCLOAK_IDENTITY` 쿠키 둘 다)·`wing_session.is_alive`로 생존 확인. **런타임 브라우저는 항상 1개**(로그인·rank 동시 금지, [[login-policy-real-browser-only]]).
- 읽기: `collector`의 `discover`·`fetch_sales_roster`·`fetch_vendor_inventory`·`fetch_inventory`·`fetch_product_ids`·`sale_status_by_vid`를 그대로 호출(L1 계약 §1). 호출 템플릿=`_POST_JSON_JS`/`_GET_JSON_JS`(cookie `XSRF-TOKEN`→`x-xsrf-token`·`credentials:include`). 순위=`rank.organic_ranks`(L1 계약 §7-b, 비로그인·프록시 뒤).
- 원문 보관: collector의 `_raw`(gzip 사이드카 `output/_raw/`·`SAVE_RAW_RESPONSES`) 패턴 유지(§3.4).
- ⚠ **위탁계정 = 판매자 OpenAPI 키 발급 불가**([[coupang-openapi-not-available-consignment]]) → 쿠팡은 **WING 세션이 유일 경로**. 어댑터의 쿠팡 인증은 API 키가 아니라 브라우저 세션이다(스마트스토어와 비대칭).

### 2.4 스마트스토어 어댑터 — 네이버 커머스 API (대부분 미결·조사 선행)
- **인증(조사 필요)**: 네이버 커머스 API는 일반적으로 **OAuth2 client credentials(판매자 애플리케이션 등록 → client_id/secret → 서명 토큰)** 방식(추정·실측 전 미확정). 토큰은 credstore(DPAPI)에 저장(`__smartstore_sa__` 류 키·제안).
- ⚠ **최우선 미결 = 위탁계정 키 발급 가능 여부**: 쿠팡처럼 "타인(위탁주) 계정의 API 자격증명을 우리가 보유·발급할 권한이 없다"면 커머스 API도 **불가**일 수 있다([[coupang-openapi-not-available-consignment]] 동형 리스크). 이 경우 스마트스토어도 **세션 기반(브라우저)** 으로 가야 하며 어댑터 설계가 크게 달라진다 → **사무실 라이브/위탁주 협의로 1차 확인 전엔 API 경로를 전제하지 않는다**.
- **능력 범위(미결)**: 상품 CRUD·판매/정산 통계·문의 API가 커머스 API에 실제 있는지·위탁권한으로 쓸 수 있는지 엔드포인트별 조사 필요. 미확인 능력은 `capabilities()`에서 빼고 호출 시 `NotSupported`.
- **DTO 정규화만 공통**: 응답 스키마가 쿠팡과 전혀 다르므로 어댑터가 커머스 응답→공통 DTO로 변환(여기가 스마트스토어 어댑터의 실제 작업량).

### 2.5 확장 지점(토스쇼핑·G마켓·당근) — 자리만
- `PlatformAdapter` 프로토콜 + `platform/registry`(어댑터 레지스트리, 아래 §6)만 열어두면, 새 플랫폼은 **새 어댑터 모듈 1개 + DTO 정규화**만 추가하면 됨. 이번엔 구현 안 함(T2).

---

## 3. 배치 수집 레이어

### 3.1 무엇을·주기·트리거
| 자료 | 주기(제안) | 트리거 | 저장 백본 |
|---|---|---|---|
| **판매·방문·노출 지표** | 매일(D-1 확정분) | 야간 무인 `--auto`(기존 ①판매수집 흐름에 편입) | 분석/통계 **셀 시계열**(workbook·gsheet) |
| **정산·매출 자료** | 주 1회(제안·`DOMAIN_D8 §2`) | 야간 또는 수동(04-1 파일 올리기 병행) | 거래 **append 원장**(registry 패턴) |
| **문의(CS)** | 매일 또는 수 시간(제안·`DOMAIN_D10 §2`) | 야간 무인 + 수동 새로고침 | CS **append 원장**(`cs_store`) |
| 상품·재고(수집) | 매일(판매수집과 동반) | 야간 ① | 셀 시계열 + vid 앵커 |

- **야간 무인과의 관계(확정 규율)**: 기존 전체실행 = ①판매수집(로그인)→②키워드선정→③순위(반자동). **수집 레이어는 이 흐름에 스테이지로 얹는다**(새 병렬 실행 아님). 쿠팡 수집은 로그인 세션을 여는 ① 안에서 같은 세션으로 문의·정산까지 당겨오는 게 효율적(추가 로그인 불필요).

### 3.2 런타임 병렬 금지 준수 (핵심 제약)
- **쿠팡**: 단일 브라우저(sync playwright 스레드당 1개)·단일 위탁계정·Akamai → **계정 순차**. 로그인·rank 동시 open 금지.
- **스마트스토어**: API(HTTP)라 브라우저 충돌은 없으나, **단일 통계 마스터/구글시트 쓰기**와 **운용 PC 1대 쓰기**(R2 ④) 때문에 **여전히 야간 단일 순차**로 둔다(쓰기 경합·레이트리밋 회피). 플랫폼 간 동시 실행도 금지(안전 우선·`PARALLEL_DEV` 런타임 규율).
- 즉 **개발은 병렬(레인), 실행은 야간 단일 순차**는 멀티플랫폼에서도 불변.

### 3.3 저장 모델 — 자료 성격별 백본 선택 (기존 §4.2 이원화 계승)
| 자료 성격 | 백본 | 이유 |
|---|---|---|
| 상품×키워드×날짜 지표(판매·방문·노출·순위·재고) | **셀 시계열**(`workbook*`·`gsheet_*`) | 날짜 가로 누적·집계·시각화에 맞음(기존 D9) |
| 정산·매출·문의처럼 건별로 쌓이고 상태가 바뀌는 자료 | **append 원장 + 이력 replay**(registry 패턴) | 되돌림·감사추적·중복방지(`DOMAIN_DESIGN §5.2`) |
| 플랫폼별 분리 | **계정·DTO에 `platform_id` 차원 추가** | 한 사업자 다플랫폼 계정을 한 묶음으로 보되 플랫폼 구분 보존(IO_DEFINITION 계정관리 「판매처」) |

- 저장 계층 단일화(R2 ③·[[decision-storage-gsheet-4rules]]): 수집본도 **구글시트/워크북 한 곳**으로 쓰고, 나중 DB 교체 시 이 한 지점만 바꾼다. 수집 레이어는 백본의 **공개 API(L1 계약)만** 호출(workbook `set_product_metric` 등·registry `sync`/`run_sync` 등)·내부 심볼 금지.

### 3.4 실패/재시도·원문 보관
- **원문 보관(_raw 패턴 확대)**: 플랫폼·API별로 가공 전 응답을 `output/_raw/{plat}_{계정}_{api}_p{n}.json.gz`로 상시 보관(기존 쿠팡 `SAVE_RAW_RESPONSES` 확장). 재수집 없이 오프라인 재분석·감사추적(DECISIONS 2026-09-24).
- **재시도**: 일시오류(timeout·429·5xx)=지수 백오프 재시도(구글시트 `GSheetClient._exec` MAX4와 동형)·영구오류(403/404/권한)=즉시 실패+로그. **폴백 최소화**([[no-silent-fallback-principle]]): 수집 실패 계정은 그 자료만 건너뛰고 로그 명시, 다음 계정 진행(기존 `run_full` "한 계정 실패해도 다음 진행"과 동형). 판매데이터 없음은 **정상 처리**(오류 아님).
- **부분 성공 기록**: 계정별 중간저장(기존 `run_full` 누적 패턴)·수집 단계 마커(`_실행단계.json` 확장 가능)로 재부팅 복구와 정합.
- **신선도 메타**: 수집 1건마다 `fetched_at`·`platform`·`source_api`를 저장(§4 신선도 표시의 근거).

---

## 4. 읽기 모델 (조회)

- **원칙(T4)**: 앱 화면은 **수집본을 조회**한다 — 플랫폼 실시간 호출 아님. 화면 응답이 빠르고, 위탁계정에 트래픽을 안 준다(밴 위험↓).
- **조회 경로**: 도메인이 L1 백본의 읽기 API로 수집본을 읽음(계정별 상품=workbook `products_of`/`product_roster`·판매 시계열=통계 시트·정산/문의=원장 replay). 어댑터를 **조회 시 직접 부르지 않는다**(수집 때만 부름).
- **신선도 표시(제안)**: 화면에 "마지막 수집 OO시간 전"·플랫폼별 수집 상태(성공/부분/실패)를 노출(수집 레이어가 남긴 `fetched_at`·실행 기록 08-7). 오래됐거나 실패면 사람이 인지하고 수동 새로고침(=수집 재실행 트리거)할 수 있게.
- **실시간이 꼭 필요한 좁은 경우**(예: 쓰기 직전 현재값 재확인) → 그때만 어댑터 읽기 1회(§5 쓰기 전 미리보기 단계). 일반 조회는 수집본.

---

## 5. 쓰기 반영 (상품 CRUD · CS 답변)

### 5.1 §5.4 쓰기 안전 규약 (확정·전 플랫폼 공통)
1. **dry-run 미리보기**: 무엇이 바뀌는지 산출(현재값 vs 변경값·영향 상품/옵션). 이때만 어댑터로 **현재값 실시간 재조회**(수집본이 stale일 수 있으므로).
2. **사람 승인 게이트**: UI에서 사람이 확인·승인(무인 자동 쓰기 금지).
3. **실행**: 어댑터 쓰기 호출(쿠팡=WING 세션·`_POST_JSON_JS` 패턴 / 스마트스토어=커머스 API).
4. **원장 기록**: 변경 전/후·실행자·시각·플랫폼 응답을 거래 원장에 append(registry 패턴·`register_store`/`cs_store`). 되돌림·감사추적.

- 위탁계정·Akamai·실운영 사고 위험 → **초기엔 반자동(사람 확인 필수)**. 폴백 최소화.

### 5.2 멱등·실패 복구 (제안)
- **멱등 키**: 요청마다 클라이언트 측 요청ID 부여 → 재시도가 중복 반영을 안 만들게. 플랫폼이 멱등 토큰을 받으면 사용, 아니면 "실행 전 원장에 PENDING 기록 → 실행 → 결과로 COMMITTED/FAILED 갱신"으로 중복 방지(원장 replay가 PENDING 잔여를 검출).
- **부분 실패**: 여러 상품 일괄 변경 중 일부 실패 → 성공분은 원장 COMMITTED·실패분은 FAILED+사유, 전체 롤백은 하지 않음(플랫폼이 트랜잭션을 안 줌)·사람에게 실패분 재시도 제시.

### 5.3 플랫폼별 차이 (미결 多)
| 항목 | 쿠팡 | 스마트스토어 |
|---|---|---|
| 쓰기 경로 | WING 세션 same-origin fetch(엔드포인트 **미확인**) | 커머스 API(엔드포인트·권한 **미확인**) |
| 인증 | 브라우저 세션(위탁·API키 불가) | OAuth2 토큰(위탁 발급 가능 여부 **미결**) |
| 밴 위험 | 높음(Akamai·위탁계정) | 상대적 낮음 추정(공식 API면)·단 미검증 |
| 미리보기 재조회 | collector 읽기 재사용 | 커머스 읽기 API |

---

## 6. 신규 모듈·레인 제안

### 6.1 모듈 (단일 책임·CC≤15·≤600줄·제안)
```
platform/                      # L0/L1 경계 — 플랫폼 파사드(공유)
  base.py          PlatformAdapter 프로토콜·공통 DTO·NotSupported·capabilities 상수
  registry.py      platform_id -> 어댑터 팩토리 조회(확장 지점)
  coupang/
    adapter.py     CoupangAdapter(WingBrowser+collector+rank 조립·정규화·얇음)
    dto.py         VendorInventoryListing 등 -> 공통 DTO 매핑
  smartstore/
    auth.py        네이버 커머스 OAuth2 토큰 관리(credstore 연계)  ※조사 후
    client.py      커머스 API 호출(HTTP·재시도)                   ※조사 후
    adapter.py     SmartStoreAdapter(client -> 공통 DTO)           ※조사 후
    dto.py
ingest/                        # 배치 수집 오케스트레이션(L2/L3 경계)
  runner.py        계정×플랫폼 순차 수집 루프(야간 흐름에 편입·실패격리)
  store.py         DTO -> 백본 기록(workbook/registry/gsheet 공개 API만 호출)
  freshness.py     fetched_at·수집 상태 메타
```
- **재사용 우선**: 쿠팡 어댑터는 새 수집 로직을 만들지 않고 기존 `collector`/`rank`/`WingBrowser`를 조립(§2.3). `ingest/store.py`는 workbook·registry·gsheet의 **L1 계약 API만** 부른다(내부 심볼 금지).
- 쓰기 모듈(상품 등록/변경·CS 답변)은 기존 도메인 설계와 정합: `register*`(D3)·`cs_store`(D10)가 **어댑터의 쓰기 메서드**를 호출(직접 import 금지·어댑터 경유).

### 6.2 레인 추가 제안 (`PARALLEL_DEV §레인`)
| 레인(제안) | 편집 소유 파일 | 비고 |
|---|---|---|
| **P 플랫폼 어댑터** | `platform/base.py`·`platform/registry.py`·`platform/coupang/*`·`platform/smartstore/*` | base·registry·coupang는 L0/L1 세션을 건드려 **통합 세션 통제**(공유), smartstore는 신규·고립이라 병렬 가능 |
| **J 수집(ingest)** | `ingest/*` | 백본 읽기만·비겹침 |
- ⚠ base/registry/coupang 어댑터는 `browser`·`collector`·`wing_session`(공유 자원·`PARALLEL_DEV §공유`)에 밀접 → **통합 세션이 계약을 먼저 고정**(L1_CONTRACT에 어댑터 공개 API 등재·핀)한 뒤 도메인 레인이 호출. smartstore 어댑터와 ingest는 신규 고립이라 레인으로 병렬 안전.

---

## 7. 다른 도메인과의 경계 (L1 경유·직접 import 금지)

- **의존 방향 불변**(`ARCHITECTURE §2`·`DOMAIN_DESIGN §3`): L2 도메인은 L0/L1로만 의존, **도메인끼리·도메인→어댑터 직접 import 금지**. 융합은 **L1 백본(어댑터·workbook·registry·gsheet) 경유**.
- 호출 방향:

| 도메인 | 이 레이어를 어떻게 쓰나 |
|---|---|
| **D1 분석**(+마케팅 흡수) | 수집본(판매·순위·노출) **조회**. 수집 자체는 ingest가·D1은 결과를 workbook/통계에서 읽음. 순위 조회는 `rank`(L1 프리미티브) |
| **D2 소싱** | D1 재사용(키워드·검색량)·경쟁강도. 어댑터 읽기는 ingest 경유 수집본 조회 |
| **D3 등록**(쓰기) | 어댑터 **쓰기**(`register_product`/`update_product`)를 §5.4 규약으로 호출·D7 이미지 산출물 참조 |
| **D4 상품관리** | 수집본(재고·가격·판매상태) 조회 + 변경(쓰기)=어댑터 쓰기(§5) |
| **D8 정산/원장** | 정산·매출 **수집본**을 원장 replay로 소비(2단계 라이브 수집=어댑터 `fetch_settlement`·`DOMAIN_D8 §2`) |
| **D10 문의/CS** | 문의 **수집**(어댑터 `fetch_inquiries`)·응대(어댑터 `reply_inquiry`)·상태/이력=`cs_store` 원장 |

- **조립(L3 pipeline)이 오케스트레이션**: 도메인 간 순서·전달은 pipeline이 담당(기존 `run_full` 스테이지 패턴을 멀티플랫폼 수집 스테이지로 확장). 도메인은 서로 모른 채 백본에만 읽고 씀.

---

## 8. 갭·리스크·미결

| # | 항목 | 상태 | 비고 |
|---|---|---|---|
| G1 | **스마트스토어 커머스 API 위탁계정 접근성** | ⚠미결(최우선) | 쿠팡 OpenAPI 불가([[coupang-openapi-not-available-consignment]])와 동형 리스크 — 위탁주 계정의 API 자격증명을 우리가 보유·발급 가능한가? 불가면 세션 기반으로 재설계 |
| G2 | 스마트스토어 인증 방식·엔드포인트(상품/판매/정산/문의 CRUD) | ⚠미결 | OAuth2 추정·실측 전 미확정. 능력별 조사 필요 |
| G3 | **쿠팡 쓰기 엔드포인트**(상품 등록/수정·CS 답변) | ⚠미확인 | 현재 전 코드 읽기 전용. WING 쓰기 API 경로 라이브 캡처 필요 |
| G4 | 밴 위험(쿠팡 쓰기·잦은 수집) | 높음 | 위탁계정·Akamai. §5.4 반자동·사람 승인·야간 단일 순차로 완화 |
| G5 | 쿠팡 문의(CS) 수집 경로 | ⚠미확인 | `DOMAIN_D10 §2`·샵마인 중복 여부 소유자 확인 |
| G6 | 정산 자료 수집(2단계) 세션 호출 가능 여부 | ⚠미결 | `DOMAIN_D8 §2`·사무실 라이브 실측 선행 |
| G7 | 스마트스토어 순위(오가닉) 측정 | 미결 | 쿠팡 반자동 방식과 다를 수 있음·비핵심 |
| G8 | 스마트스토어 세션 1개 제약 유무 | 미결 | API면 동시성 여유 있으나 쓰기 경합/레이트리밋은 여전히 순차 권장(§3.2) |

---

## 9. 로드맵 단계·게이트/핀 계획 (오프라인 모킹 검증)

### 9.1 단계 (big-bang 금지·측정 기반·`DOMAIN_DESIGN §8` 정합)
1. **경계·계약 고정(문서·지금)**: 이 문서로 어댑터 경계·DTO·수집 모델 확정. 코드 없음.
2. **쿠팡 어댑터 파사드 스캐폴딩**: 기존 collector/rank/WingBrowser를 공통 인터페이스로 감싸는 얇은 어댑터(행동 불변·코드 이동 없음). L1 계약에 어댑터 공개 API 등재+핀.
3. **ingest 레이어(쿠팡만)**: 기존 야간 ① 흐름을 ingest.runner로 정리(스테이지 패턴)·_raw/신선도 메타. 판매수집부터(이미 검증된 경로).
4. **스마트스토어 어댑터 — 조사 먼저(G1·G2)**: 위탁 API 접근성·인증·엔드포인트 확인 후 설계 확정 → auth/client/adapter/dto. 미결 해소 전엔 착수 금지.
5. **읽기 모델(조회+신선도)**: 화면이 수집본을 읽고 신선도 표시(H UI 연계).
6. **쓰기(§5.4)**: 쿠팡 상품 변경(저위험 항목)부터 미리보기→승인→실행→원장. 엔드포인트 확인(G3) 후.
7. **확장 플랫폼**: 토스쇼핑 등은 어댑터만 추가(T2).

### 9.2 게이트/핀 (실 API 금지·오프라인 결정적)
- **어댑터 계약 핀**(제안): `pin_l1_contract.py`에 `platform.base`·`CoupangAdapter` 공개 메서드 시그니처 추가(기존 collector/rank 핀과 동형). 시그니처 파괴 즉시 빨강.
- **수집 오프라인 검증**(제안·`verify_platform_ingest_offline.py`): 저장한 `_raw` 픽스처(또는 페이크 어댑터)로 DTO 정규화·백본 기록을 **실 로그인/실 API 없이** 검증(기존 `verify_offline`/`verify_gsheet_offline` 패턴). 실 API 실증은 `VERIFY_REAL_API=1` 옵트인(기존 규율).
- **페이크 어댑터**: 테스트는 `PlatformAdapter`의 결정적 페이크 구현으로 돈다(브라우저·네트워크 없음). 쓰기 테스트는 미리보기→승인→원장 기록 순서만 검증(실제 쓰기 금지).
- 커밋/푸시 전 `tools/run_checks.py` 초록·`check_complexity.py`(새 모듈 CC≤15·≤600줄)·건강(A/B) 파일 미접촉(`CLAUDE.md` 코드 건강 규칙).

---

SSOT = 이 문서(플랫폼 통합·수집·읽기/쓰기) · `docs/ARCHITECTURE.md`(계층) · `docs/DOMAIN_DESIGN.md`(도메인·연계·통제) · `docs/L1_CONTRACT.md`(계약) · `designs/IO_DEFINITION.md`(입출력 칸). 구현 착수는 소유자 지시 시.
