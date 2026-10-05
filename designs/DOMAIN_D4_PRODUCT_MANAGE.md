# D4 상품 관리(변경/삭제·가격·재고·판매상태) 도메인 설계 (DOMAIN_D4_PRODUCT_MANAGE)

> 작성 2026-10-05 · D4 상품 관리 레인(설계 단계·**구현 보류**).
> 상위 지도=`docs/DOMAIN_DESIGN.md §2 D4`·계층=`docs/ARCHITECTURE.md`·L1 계약=`docs/L1_CONTRACT.md`·입출력=`designs/IO_DEFINITION.md`(01-1 조회/수정·01-2 등록·03-x 재고)·운영=`docs/PARALLEL_DEV.md`.
> ⭐**토대=`designs/PLATFORM_INTEGRATION.md`**(플랫폼 어댑터·배치 수집·읽기/쓰기 반영·§5.4 쓰기 안전). 이 문서는 그 어댑터 위에 **D4 상품 관리 도메인**을 얹는 설계다(재사용 우선·중복 금지).
> ⚠ 이 문서는 **설계만** — 코드 변경·신규 모듈 생성·게이트/핀 추가는 소유자 착수 지시 후. 여기 적힌 모듈·함수·메뉴·계층변경·엔드포인트는 전부 **제안/미결**이다.
> 근거: `docs/DOMAIN_DESIGN.md`(D4 §2·§5.4·§4.2)·`docs/L1_CONTRACT.md`(collector·workbook 계약)·`src/coupang_analytics/collector.py`·`product_match.py`·`input_list.py`(실측 2026-10-05)·[[inventory-api-rfm-search]]·[[feature-sale-status-mismatch-flag]]·[[feature-vid-source-from-product-list]].

---

## 0. 실측 요약 (설계 근거)

- **D4 = 🟡부분 구현**(DOMAIN_DESIGN §2 D4): **조회(수집)는 완비, 변경(쓰기)은 코드 전무.**
  - **조회 프리미티브(기존·D1과 공유·L1 계약)**: `collector.fetch_vendor_inventory`(전 상품·전 옵션·vid·판매상태 productStatus)·`fetch_inventory`(로켓그로스 재고 `orderableQuantity`·판매중지여부 `isSaleSuspended`·productId)·`sale_status_by_vid`/`sale_status_of`(판매상태 문자열화)·`vid_meta_of`(판매가 `salePrice`·판매시작일). 전부 **읽기 전용**.
  - **역기록(기존·D4 영역)**: `input_list.write_ledger_inventory`(관리대장 AD열 그로스 재고 역기록·매칭키=계정+상품명 유사도 `_best_inventory_match`)·`company_stock.run_company_stock`(회사보유재고 역기록). ⚠이는 **우리 원장(관리대장)에 쓰는 것**이지 쿠팡/스마트스토어 **플랫폼에 쓰는 것이 아님**(혼동 금지).
  - **쓰기(플랫폼 반영)=전무**: 현재 전 코드가 읽기 전용(DOMAIN_DESIGN §5.4). 가격/재고/판매상태를 쿠팡·스마트스토어에 **실제 변경**하는 경로는 **엔드포인트 미확인**(PLATFORM_INTEGRATION §8 G3).
- **매칭(기존)**: `product_match.scope_to_ledger`·`augment_unmatched`·`augment_ai`(대장↔쿠팡 상품 정밀매칭·vid 앵커·[[ledger-scoped-tracking]]) — D4 조회·쓰기 대상 식별에 그대로 재사용.
- **판매상태 enum(라이브 실측 확정)**: `ON_SALE`=판매중·`PARTIAL_ON_SALE`=부분판매중·`SUSPENDED`=판매중지·`DRAFT`=임시저장·`REJECTED`=승인반려·`UNDER_REVIEW`=검토중([[feature-sale-status-mismatch-flag]]). 관리대장 관리상태(판매중/판매중지/대체/삭제)와 **별개 축** → 불일치 경고(기구현).
- **계층 규칙(불변)**: L2 도메인은 L0/L1만 의존·**도메인끼리·도메인→어댑터 직접 import 금지**(PLATFORM_INTEGRATION §7). D4는 어댑터(§2·§3 경유)·collector·workbook·product_match(L1)만 호출.

---

## 1. 역할·범위

### 하는 것 (D4 상품 관리)
- **온라인 조회(요청 시 수집해 표시)**: 계정별 상품·옵션·가격·재고·판매상태를 어댑터로 수집 → 통합앱이 표시(§2). 기본은 **수집본 조회**, 쓰기 직전엔 **현재값 실시간 재조회**(§3).
- **변경(쓰기·§5.4)**: **가격 변경**·**재고(로켓그로스 입고요청/판매자배송 재고)**·**판매상태 변경**(판매중↔판매중지·판매재개). 미리보기→승인→실행→원장(§3).
- **삭제(쓰기·고위험)**: 상품/옵션 **판매중지(소프트)** 및 **완전 삭제(하드·복구 불가)** — 안전장치 강화(§3.4).
- **역기록(기존 유지)**: 그로스 재고(관리대장 AD열)·회사보유재고 역기록은 이미 D4 영역(쿠팡에서 **읽어** 관리대장에 쓰기). 플랫폼 쓰기와 구분(§3.5).

### 안 하는 것 (경계)
- **상품 등록 = D3**(신규 등록/최초 생성). D4는 **이미 등록된 상품**의 변경/삭제만. 어댑터 `register_product`=D3, `update_product`=D4(PLATFORM_INTEGRATION §2.2). 등록과 변경이 같은 WING 폼/API를 쓰더라도 **도메인 책임은 분리**(D3=생성·D4=변경).
- **조회 수집 프리미티브(collector·어댑터 읽기)는 D1과 공유** — D4가 소유하지 않는다(L1). D4는 그것을 **호출**해 관리 화면/쓰기 미리보기에 쓸 뿐.
- **주문(D5)·배송(D6)=⛔범위밖(샵마인)**. 로켓그로스 **입고요청**은 재고 관리(D4)로 보되, 실제 출고·송장·배송추적은 D6(샵마인). 경계=입고요청 생성/상태조회까지만(발주 실행이 플랫폼 쓰기면 §5.4·미결 M5).
- **정산·매출 = D8** / **키워드·순위·마케팅 = D1** / **통계 출력 = D9**. D4는 상품 **상태를 바꾸는** 책임만.

---

## 2. 온라인 조회 (요청 시 수집해 표시)

> 소유자 2026-10-05 새 방향: 계정별 상품·판매 정보 요청 시 **온라인으로 수집해 통합앱이 표시**. PLATFORM_INTEGRATION §4 읽기 모델을 D4 상품 관리 화면 관점으로 구체화.

### 2.1 두 조회 경로 (신선도로 구분)
| 경로 | 언제 | 무엇을 | 근거 |
|---|---|---|---|
| **A. 수집본 조회(기본)** | 관리 화면 일반 열람 | 야간 배치(ingest)가 당겨 백본에 저장한 상품·재고·판매상태를 **읽기**(workbook `products_of`/`product_roster`·`status_of`·`inventory_by_biz`) | 빠름·위탁계정에 트래픽 0(밴 위험↓)·PLATFORM_INTEGRATION §4 원칙 T4 |
| **B. 즉시 조회(수동 새로고침·쓰기 직전)** | 사람이 "지금 최신값" 요청 / 변경 미리보기 | 어댑터 읽기 1회(쿠팡=`collector.fetch_vendor_inventory`+`fetch_inventory`, 스마트스토어=커머스 읽기 API)로 **현재값 재조회** | stale 방지·§3.1 미리보기의 "현재값" 신뢰성 |

- **원칙**: 일반 조회는 **수집본**(어댑터를 조회 시 직접 안 부름). 즉시 조회는 **좁은 경우에만**(수동 새로고침 버튼·쓰기 미리보기) — 트래픽 최소화(PLATFORM_INTEGRATION §4).
- **신선도 표시**: 화면에 "마지막 수집 OO시간 전"·플랫폼별 수집 상태(성공/부분/실패)를 노출(ingest 가 남긴 `fetched_at`·08-7 수집 기록). 오래됐으면 사람이 B(수동 새로고침) 선택.

### 2.2 D4가 조회로 표시할 필드 (상품 관리 화면 = 01-1)
- 상품(리스팅): 등록상품명·노출상품명·판매방식(로켓그로스/판매자배송/둘다)·**판매상태**(ON_SALE/…·`sale_status_of`)·쿠팡 상품 링크(`/vp/products/{pid|0}?vendorItemId={vid}`).
- 옵션(vid): 옵션명(itemName)·**판매가**(salePrice·`vid_meta_of`)·**재고**(로켓그로스 orderableQuantity·판매자배송은 재고개념 없음→공란·[[inventory-api-rfm-search]])·옵션 판매상태.
- 대장 대비: 관리대장 관리상태(판매중/판매중지/대체/삭제)와 쿠팡 실제 판매상태 **불일치 경고**(기구현·[[feature-sale-status-mismatch-flag]]) — 변경 대상 후보를 사람에게 환기.

### 2.3 수집은 ingest, D4는 소비 (책임 분리)
- **수집 자체는 ingest 레이어**(PLATFORM_INTEGRATION §3)가 야간 ① 흐름에서 수행 → 백본 저장. D4는 그 수집본을 읽는 화면/로직만 소유(수집 루프를 D4가 새로 짜지 않음·재사용).
- **즉시 조회(B)도 어댑터 경유**: D4는 `collector`를 직접 부를 수도 있으나(L1 프리미티브라 합법), **멀티플랫폼 일관성**을 위해 **어댑터 읽기 메서드**(`fetch_products`/`fetch_inventory`)를 통해 공통 DTO로 받는 것을 권장(§4). 쿠팡만 쓰는 1단계에선 collector 직접 호출도 허용(어댑터가 얇은 파사드라 동형).

---

## 3. 변경/삭제 쓰기 (§5.4 쓰기 안전 규약)

> DOMAIN_DESIGN §5.4·PLATFORM_INTEGRATION §5 = 전 플랫폼 공통 4단계. D4는 그 규약의 **가격/재고/판매상태/삭제** 구체화다. **쓰기 엔드포인트는 미확인**(G1)이라 아래는 규약·흐름 설계이며 실제 호출은 라이브 캡처 후.

### 3.1 쓰기 4단계 (D4 모든 변경·삭제에 강제)
1. **dry-run 미리보기**: 무엇이 바뀌는지 산출(현재값 vs 변경값·영향 상품/옵션 수). 이때 **어댑터로 현재값 실시간 재조회**(§2.1 B·수집본이 stale일 수 있으므로). 예: "가격 12,000→9,900 (옵션 3개 중 2개)".
2. **사람 승인 게이트**: UI에서 사람이 확인·승인(**무인 자동 쓰기 절대 금지**·위탁계정 사고 위험). 야간 무인 `--auto`는 쓰기를 **하지 않는다**(수집·순위만).
3. **실행**: 어댑터 쓰기 호출(`update_product`/`delete_product`). 쿠팡=WING 세션 same-origin `_POST_JSON_JS`/신규 엔드포인트, 스마트스토어=커머스 쓰기 API.
4. **원장 기록**: 변경 전/후·실행자·시각·플랫폼 응답을 **변경 이력 원장**에 append(§5·registry 패턴). 되돌림 근거·감사추적.

### 3.2 가격 변경
- 대상: 옵션(vid) 단위 판매가(salePrice). 미리보기에 현재가(`vid_meta_of`)·신규가·할인율 표시.
- 규칙(제안): 하한/상한 가드(예: 현재가 대비 ±N% 초과 시 추가 확인)·계약단가(관리상품 01-2 계약단가) 미만 경고·0 이하 거부. 일괄 변경 시 옵션별 미리보기 테이블.
- 멱등: 요청ID 부여(§3.6)·"현재가가 미리보기 시점과 다르면 중단하고 재미리보기"(낙관적 동시성·사람이 보는 값과 실제가 어긋난 채 덮어쓰기 방지).

### 3.3 재고·판매상태 변경
- **로켓그로스 재고**: 재고 숫자는 **입고로만 늘고 판매로 준다**(직접 "재고 설정"은 보통 불가) → D4의 재고 쓰기 = **입고요청 생성/수량 조정**(물류 흐름). ⚠입고요청이 배송(D6) 성격이면 **범위 경계 재확인**(미결 M5). 조회(orderableQuantity)는 이미 가능.
- **판매자배송 재고**: 재고 수량 직접 수정 가능 추정(엔드포인트 미확인 G1).
- **판매상태 변경**: 판매중↔판매중지(일시중지)·판매재개. `productStatus` 전이. 미리보기에 현재 상태·전이 후 상태·영향(노출 중단 등) 명시. **판매중지는 소프트**(복구 가능)—§3.4 삭제와 구분.

### 3.4 삭제의 안전 (소프트 vs 하드·복구 불가 경고)
| 단계 | 의미 | 복구 | 안전장치(제안) |
|---|---|---|---|
| **소프트=판매중지(SUSPENDED)** | 노출만 내림·데이터 유지 | ✅ 판매재개 가능 | 일반 승인 게이트(§3.1) |
| **하드=완전 삭제** | 플랫폼에서 상품/옵션 영구 제거 | ⛔ **복구 불가**(플랫폼이 되돌림 미제공 전제) | ①2중 확인(상품명 타이핑 확인 등) ②"복구 불가" 명시 경고 ③**소프트 우선 권장**(먼저 판매중지 제안) ④원장에 삭제 전 **전체 스냅샷** 보관(우리 쪽 재등록 근거) ⑤일괄 삭제 금지(건별) |
- **기본 정책 제안**: D4 삭제는 **소프트(판매중지)를 기본**으로, 하드 삭제는 **별도 명시 요청 + 2중 확인**일 때만. 쿠팡 요청 파라미터 `displayDeletedProduct=false`가 보여주듯 플랫폼에 "삭제" 개념이 있으나 **복구 API는 전제하지 않음**(미확인 G1) → 되돌릴 수 없다고 간주.
- **관리대장 관리상태 '삭제'와 다름**: 대장 '삭제'(01-2 관리상태)는 **우리 추적 중단**(계정 삭제=`delete_accounts`/`delete_product_block`·되돌릴 수 없음·CLAUDE.md)이고, 여기 하드 삭제는 **플랫폼에서 상품 제거**. 둘은 별개 — 대장에서 '삭제'로 바꿔도 쿠팡 상품은 그대로(불일치 경고로 환기).

### 3.5 역기록(우리 원장 쓰기)과 플랫폼 쓰기 구분 (혼동 방지)
- **역기록(기존·안전)**: 쿠팡에서 **읽은** 재고를 **관리대장(우리 구글시트)에 쓰기**(`write_ledger_inventory` AD열·`run_company_stock` 회사보유재고). 플랫폼에 트래픽 없음·밴 위험 없음·§5.4 불필요(우리 저장소 쓰기는 R2 단일 작성자 규칙만).
- **플랫폼 쓰기(신규·고위험)**: 쿠팡/스마트스토어에 가격·상태 **실제 변경**. §5.4 전면 적용. **이 둘을 같은 "쓰기"로 묶지 말 것** — 위험도·규약이 다르다.

### 3.6 멱등·부분 실패 (PLATFORM_INTEGRATION §5.2 계승)
- **멱등 키**: 변경 요청마다 클라이언트 요청ID → 재시도 중복 반영 차단. 플랫폼 멱등 토큰 있으면 사용, 없으면 "원장에 PENDING 기록 → 실행 → COMMITTED/FAILED 갱신"(replay가 PENDING 잔여 검출).
- **부분 실패**: 여러 옵션 일괄 변경 중 일부 실패 → 성공분 COMMITTED·실패분 FAILED+사유, 전체 롤백 안 함(플랫폼 트랜잭션 없음)·사람에게 실패분 재시도 제시.

---

## 4. 멀티플랫폼 차이·공통 DTO

> PLATFORM_INTEGRATION §2.2 `PlatformAdapter` 위에 올라탄다. D4는 어댑터의 **읽기(`fetch_products`·`fetch_inventory`)+쓰기(`update_product`·삭제)** 메서드를 공통 DTO로 쓴다.

### 4.1 플랫폼별 차이
| 항목 | 쿠팡(WING) | 스마트스토어(커머스 API) |
|---|---|---|
| 조회 | `collector.fetch_vendor_inventory`+`fetch_inventory`(세션 same-origin) | 커머스 상품/재고 조회 API(**미확인** G2) |
| 쓰기 경로 | WING 세션 same-origin fetch·엔드포인트 **미확인**(G1) | 커머스 상품 수정 API·권한 **미확인**(G1·위탁 접근성) |
| 인증 | 브라우저 세션(위탁·API키 불가·[[coupang-openapi-not-available-consignment]]) | OAuth2 토큰(위탁 발급 가능 여부 **미결**) |
| 재고 모델 | 로켓그로스=orderableQuantity(입고 흐름)·판매자배송=재고개념 약함 | 플랫폼 재고 모델 상이(미확인) |
| 판매상태 | productStatus enum 6종(기구현 매핑) | 상태 enum 상이 → 어댑터가 공통 상태로 정규화 |
| 밴 위험 | 높음(Akamai·위탁) | 상대적 낮음 추정(공식 API면)·미검증 |

### 4.2 공통 DTO (제안 — 어댑터가 정규화·D4는 DTO만 봄)
- **읽기**: `ProductDTO`(PLATFORM_INTEGRATION §2.2) 재사용 — 플랫폼 중립 상품·옵션·vid·가격·재고·판매상태. 쿠팡 `VendorInventoryListing`→`ProductDTO` 매핑은 어댑터 `coupang/dto.py`(기존 collector 데이터클래스 변환).
- **쓰기(신규 제안)**: `ProductChangeDTO` — 플랫폼 중립 **변경 명령**.
  ```python
  @dataclass
  class ProductChangeDTO:
      platform_id: str                 # "coupang"·"smartstore"
      account_id: str
      vendor_item_id: str | None       # 옵션(vid) 단위 변경(가격·상태). 리스팅 단위면 None+listing 키
      listing_id: str | None           # 등록상품ID(리스팅 단위 변경·삭제)
      kind: str                        # "price"·"stock"·"sale_state"·"delete_soft"·"delete_hard"
      before: dict                     # 현재값(미리보기 재조회 결과)
      after: dict                      # 변경값(사람 입력)
      request_id: str                  # 멱등 키(§3.6)
  ```
  - 어댑터가 `ProductChangeDTO`를 플랫폼 요청으로 번역(쿠팡 WING 바디·스마트스토어 커머스 바디). D4는 플랫폼을 모른 채 변경 명령만 만든다.
  - **정체성 키**: vid(불변 앵커)·listing_id·계정ID·사업자명(DOMAIN_DESIGN §4.2 기존 키) — 스마트스토어는 그쪽 상품ID를 `platform_product_id`로.

---

## 5. 데이터 모델 (변경 이력 원장)·화면 매핑

### 5.1 변경 이력 원장 (append + replay·D8 registry 패턴 재사용)
- **성격**: 가격/재고/상태/삭제 변경은 **상태가 바뀌는 거래** → **셀 시계열(workbook) 부적합·append 원장 적합**(DOMAIN_DESIGN §4.2·§5.2). D8 `registry_*` 패턴(지우지 않고 쌓고 replay로 현재상태 계산)을 **그대로** 따른다(새 거래 도메인 백본 표준).
- **한 변경 = 한 줄**: `platform_id·계정ID·vid/listing·kind·before·after·request_id·실행자·시각·상태(PENDING/COMMITTED/FAILED)·플랫폼 응답 요약`.
- **무결성 규칙 재사용**: 번호 연속·전부 되돌리면 빈 원장(손수정 검출)·실행마다 로컬 백업·동시 쓰기 잠금(`registry_lock`·같은 PC 내)·R2 ①앱만 추가 ②정정은 줄+사유 ④쓰기 PC 하나.
- **저장소**: R2 확정(구글시트로 시작·[[decision-storage-gsheet-4rules]]). 변경 이력 전용 시트(또는 셀독등록원장 08-3 변경 이력 탭 확장) — H_ui·통합 세션 조율.
- **D8 원장과 관계**: D8 셀독등록원장은 **계정·상품 등록/관리 이력**(관리상태·비번 등), D4 변경 이력은 **플랫폼 반영 이력**(가격/재고/상태 실제 변경) — **다른 원장**. 공용 append 프레임 추출은 중복 측정 후(DOMAIN_D8 §흡수 동형).

### 5.2 화면 매핑 (IO_DEFINITION 01-1 조회/수정·03-x 재고)
| 메뉴 ID(기존 IO_DEFINITION) | 화면 | D4 역할 |
|---|---|---|
| **01-1 조회/수정** | 상품 조회·가격/상태 수정 | **D4 핵심 화면**. 수집본 조회(§2.1 A)+수동 새로고침(B)+변경 미리보기·승인(§3) |
| 01-2 상품 등록 | 신규 등록 | ⛔ **D3**(D4 아님·경계) — 단 관리상태/가격 입력 칸은 D4 변경과 연계 |
| 03-1 창고 재고·03-3 입고·03-4 로켓그로스 입고·03-8 실사 | 재고 입력/입고 | 재고 조회·입고요청(§3.3)·역기록(§3.5) |
| 홈 계정목록·01-6 상품 상세 | 상태 표시 | 판매상태·재고·불일치 경고 표시(§2.2·D9 출력 소비) |
- **쓰기 UI(신규 제안)**: 01-1에 **[가격 변경]·[판매중지/재개]·[삭제]** 액션 → 각각 미리보기 다이얼로그(현재값 vs 변경값·영향 옵션)→[승인]→실행→결과·원장 1줄. 삭제는 2중 확인(§3.4).
- IO_DEFINITION 표에 D4 상품 관리 입력 칸은 이미 등재(01-1 조회/수정·03-x) — 쓰기 액션·변경 이력 원장 칸은 구현 시 H_ui 레인이 추가(현재 "향후"처럼 선등재 가능).

---

## 6. 신규 모듈 제안·레인 (단일책임·CC≤15·≤600줄)

| 파일(제안) | 책임(단일) | 의존(아래로만) | 규모 가이드 |
|---|---|---|---|
| `product_manage.py` | 변경 명령 빌더·검증·미리보기 산출(현재값 재조회 조립)·쓰기 4단계 오케스트레이션(승인 전까지). `ProductChangeDTO` 생성·가드(가격 하한·삭제 2중확인 규칙) | L1(어댑터 읽기·`product_match`)·L0(세션은 조립 주입) | ≤600줄·CC≤15 |
| `product_change_store.py` | 변경 이력 원장 append/replay(모델=registry 패턴)·PENDING/COMMITTED/FAILED 상태 | L1(`gsheet_api`·registry 패턴) | 〃 |
| (어댑터 쓰기 메서드) | `update_product`/`delete_product` = **어댑터(P 레인)** 소유(`platform/*`) — D4가 만드는 게 아니라 **호출** | — | PLATFORM_INTEGRATION §6 |
- **재사용 우선**(삭제>통합>수정>추가): 조회·매칭은 전부 기존(collector·product_match·workbook) **호출**. 재고 역기록은 `input_list.write_ledger_inventory`·`company_stock.run_company_stock` **그대로**. 원장은 D8 registry 패턴 **그대로**(복붙 아닌 패턴 준수·가능하면 공용 프레임).
- **레인(PARALLEL_DEV 제안)**: D4 레인 = 편집 소유 `product_manage*`·`product_change_store*`. 어댑터 쓰기(`platform/*`)는 **P 레인(통합 세션 통제)** — D4는 어댑터 계약(L1_CONTRACT 등재·핀)을 **호출**만(직접 편집 금지). 쓰기 안전 규약 준수 레인.

---

## 7. 공개 인터페이스 계약 초안 (제안 시그니처)

착수 시 `docs/L1_CONTRACT.md`에 D4 섹션으로 핀 추가(아래는 초안·확정 아님). 어댑터 쓰기 계약은 PLATFORM_INTEGRATION §6(P 레인)에.

```python
# product_manage.py — 변경 명령·미리보기(승인 전까지 부작용 없음)

@dataclass
class ChangePreview:
    change: ProductChangeDTO
    current: dict            # 재조회한 현재값(§2.1 B)
    warnings: list[str]      # '계약단가 미만'·'현재가 변동'·'복구 불가' 등
    affected: int            # 영향 옵션/상품 수

def preview_change(adapter, account_id: str, change_spec: dict, *, log=None) -> ChangePreview:
    """변경 요청 → 현재값 재조회(어댑터 읽기) → 차이·경고 산출. **쓰기 안 함**(승인 전 단계).
    삭제(delete_hard)면 warnings 에 복구 불가·소프트 우선 권장 포함."""

def apply_change(adapter, preview: ChangePreview, *, approved: bool, store, on_log=None) -> dict:
    """승인된 변경을 실행(어댑터 쓰기)+원장 기록. approved=False 면 ValueError(사람 승인 게이트·무인 금지).
    낙관적 동시성: 실행 직전 현재값이 preview.current 와 다르면 중단(ChangeConflict)·재미리보기 유도."""

# product_change_store.py — 변경 이력 원장(append + replay)
def record_pending(store, change: ProductChangeDTO, *, now, actor) -> str: ...   # 실행 전 PENDING
def commit(store, request_id: str, platform_resp: dict, *, now) -> None: ...     # 성공 COMMITTED
def fail(store, request_id: str, reason: str, *, now) -> None: ...               # 실패 FAILED
def current_state(store, vid: str) -> dict | None: ...                           # replay 현재값
```

- 반환은 값 객체(dataclass)·dict. 부작용은 `apply_change`(쓰기)·store(원장)만. 예외 명시(`ChangeConflict`·`NotSupported`[어댑터 미지원]·`RegistryLockError`). 폴백 최소화([[no-silent-fallback-principle]]).
- `adapter`·세션은 **조립(L3)이 생성·주입**(도메인은 세션 안 엶·단일 브라우저 원칙·로그인·rank 동시 금지). 무인 자동 쓰기 경로 **없음**(approved 게이트가 코드로 강제).

---

## 8. 갭·리스크·미결

| # | 항목 | 상태 | 비고 |
|---|---|---|---|
| G1 | **쿠팡/스마트스토어 변경·삭제 쓰기 엔드포인트** | ⚠미확인(최우선) | 현재 전 코드 읽기 전용. WING 가격/상태/삭제 API 경로·바디 **라이브 캡처 필요**(PLATFORM_INTEGRATION §8 G3). 캡처 전엔 쓰기 착수 불가 |
| G2 | 스마트스토어 커머스 상품 조회/수정 API·위탁 접근성 | ⚠미결 | PLATFORM_INTEGRATION §8 G1·G2 동일. API 경로 확정 전 어댑터 쓰기 설계 불가 |
| G3 | **밴 위험(쿠팡 쓰기)** | 높음 | 위탁계정·Akamai. §3.1 반자동·사람 승인·야간 단일 순차로 완화. 쓰기 빈도·패턴이 수집보다 더 민감할 수 있음(실측 필요) |
| G4 | **하드 삭제 복구 가능성** | ⚠미확인 | 플랫폼 삭제 후 복구 API 유무 불명 → **복구 불가로 간주**(§3.4). 소프트(판매중지) 우선 정책 권장 |
| G5 | 로켓그로스 입고요청의 범위 경계 | 미결 M5 | 재고(D4)인지 배송/발주(D6=샵마인 범위밖)인지 소유자 확인. 조회(orderableQuantity)는 D4 확정 |
| G6 | 재고 직접 설정 가능 여부 | ⚠미확인 | 로켓그로스 재고는 입고로만 변동 추정·판매자배송 재고 직접수정 여부 미확인(G1 캡처 시 확인) |
| G7 | 변경 이력 원장 vs 셀독등록원장(D8) 통합 | 미결 | 별도 원장 유지(§5.1)·공용 프레임 추출은 중복 측정 후. 저장 시트 위치 H_ui 조율 |
| G8 | 낙관적 동시성 충돌 빈도 | 미결 | 수집본·실제값 괴리(ChangeConflict) 실측 전 미지 — 재미리보기 UX 설계 영향 |

---

## 9. 로드맵 단계·게이트/핀 계획 (오프라인·dry-run·실 API 금지)

### 9.1 단계 (DOMAIN_DESIGN §8-4·PLATFORM_INTEGRATION §9 정합·big-bang 금지)
1. **경계·계약 고정(이 문서·지금)**: 조회/쓰기 경계·DTO·원장 모델 확정. 코드 없음.
2. **조회(수집본+즉시) 소비 배선**: ingest 수집본을 01-1 화면이 읽고 신선도 표시(§2)·수동 새로고침(B). **읽기 전용·저위험** → 먼저. 어댑터 조회 재사용(쿠팡 1단계는 collector 직접 호출 허용).
3. **쿠팡 쓰기 엔드포인트 라이브 캡처(G1)**: 가격/상태/삭제 WING API 경로·바디 확인(사무실 라이브). **미결 해소 전 쓰기 구현 착수 금지**.
4. **쓰기 — 저위험부터(§5.4)**: **가격 변경 → 판매상태(소프트 중지/재개) → 하드 삭제** 순(위험 오름차순). 각각 미리보기→승인→실행→원장. 어댑터 `update_product`/`delete_product`(P 레인) 계약 선고정+핀.
5. **스마트스토어 어댑터(G2 조사 후)**: 커머스 쓰기 API 접근성·엔드포인트 확인 후. 미결 해소 전 착수 금지(쿠팡과 비대칭).
6. **UI·조립 확장**: 01-1 쓰기 액션 다이얼로그·변경 이력 뷰(H_ui)·pipeline 스테이지(무인 쓰기 없음).

### 9.2 게이트/핀 (실 API·실 쓰기 금지·오프라인 결정적)
- **`verify_product_manage_offline.py`(신규 제안)**: **페이크 어댑터**로 `preview_change`·`apply_change`·원장 replay를 **실 로그인/실 쓰기 없이** 검증. 핵심 시나리오:
  - 미리보기 차이·경고 산출(가격 하한·계약단가 미만·삭제 복구불가 경고).
  - **쓰기 안전 순서 핀**: approved=False면 `ValueError`(승인 게이트)·무인 경로에서 쓰기 호출 0건·실행 전 PENDING→실행→COMMITTED 순서·실패 시 FAILED+롤백 없음.
  - 낙관적 동시성: 실행 직전 현재값 불일치면 `ChangeConflict`(쓰기 안 함).
  - 삭제: delete_hard는 2중 확인 플래그 없으면 거부.
- **`pin_l1_contract.py`**: D4 공개 API(§7) + 어댑터 쓰기 메서드(P 레인·PLATFORM_INTEGRATION §6) 시그니처 핀.
- **`check_complexity.py`**: `product_manage*`·`product_change_store*` 신규 파일 D+(CC≥21) 경고·MI C 추락 차단(기존 게이트 자동 적용).
- `run_checks.py` 러너에 1줄 등록(append 친화·PARALLEL_DEV 충돌 핫스팟 회피). 건강(A/B) 파일 미접촉(CLAUDE.md 코드 건강 규칙).
- **되돌림/정책 변경은 실측 근거 필수**([[fix-from-real-evidence]]): 삭제 정책(소프트 우선)·가격 가드 임계는 라이브 캡처(G1) 후 실데이터로 확정·근거 메모.

---

SSOT = 이 문서(D4 상품 관리 상세) · `designs/PLATFORM_INTEGRATION.md`(어댑터·쓰기 안전 토대) · `docs/DOMAIN_DESIGN.md §2 D4·§5.4`(도메인 지도) · `docs/L1_CONTRACT.md`(계약) · `designs/IO_DEFINITION.md`(01-1 조회/수정·03-x 재고). 구현 착수는 소유자 지시 + G1(쿠팡 쓰기 엔드포인트) 해소 후.
