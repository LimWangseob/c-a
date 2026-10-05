# D3 상품 등록(Register) 도메인 설계 (DOMAIN_D3_REGISTER)

> 작성 2026-10-05 · D3 상품 등록 레인(설계 단계·**구현 보류**·쓰기 도메인=고위험).
> 상위 지도=`docs/DOMAIN_DESIGN.md §2 D3·§5.4`·계층=`docs/ARCHITECTURE.md`·L1 계약=`docs/L1_CONTRACT.md`·입출력=`designs/IO_DEFINITION.md`(01-2 상품 등록)·운영=`docs/PARALLEL_DEV.md`.
> ⭐ **토대=`designs/PLATFORM_INTEGRATION.md`**(어댑터 추상화·capabilities·쓰기 §5·`register_product`/DTO). D3는 그 어댑터 **쓰기 인터페이스 위에 올라탄다**(중복 설계 금지·어댑터 재사용).
> ⚠ 이 문서는 **설계만** — 코드 변경·신규 모듈 생성·게이트/핀 추가는 소유자 착수 지시 후. 여기 적힌 모듈·함수·메뉴·엔드포인트·계층변경은 전부 **제안**이며, 쿠팡/스마트스토어 등록 **쓰기 엔드포인트는 미확인(라이브 캡처 선행)**이다.
> 근거: `designs/PLATFORM_INTEGRATION.md`(§2.2 쓰기 메서드·§5 쓰기 안전·§5.3 플랫폼차이)·`docs/DOMAIN_DESIGN.md §2 D3·§5.4`·`designs/IO_DEFINITION.md`(관리상품 16칸)·`src/coupang_analytics/collector.py`(`_POST_JSON_JS`·XSRF·`VendorInventoryListing`)·`detail_images.py`(D7 `extract_via_cdp`/`extract_from_page`)·`product_match.py`(이름 정규화)·[[coupang-openapi-not-available-consignment]]·[[feature-vid-source-from-product-list]]·[[api-productid-source-vendor-items-with-vendoritems]]·[[coupang-official-reference]].

---

## 0. 실측 요약 (설계 근거)

- **D3 상품 등록 = 코드 전무**(확정): `src` 전수에 `register`/상품등록 쓰기 모듈 없음. 현재 **전 코드가 읽기 전용**(`collector`·`rank`·`workbook`·`registry`)이며 WING 에 쓰는 경로는 없다(그로스 재고·회사재고 역기록은 입력 **구글시트** 쓰기이지 쿠팡 플랫폼 쓰기가 아님).
- **재사용 기반(읽기·세션·DTO)은 완비**:
  - **세션 관문(L0)**: `with WingBrowser(profile_dir=...) as wb:` → `wb.page` same-origin fetch. `authenticated()`(윙 대시보드 URL + `KEYCLOAK_IDENTITY` 쿠키)·단일 브라우저 원칙([[login-policy-real-browser-only]]).
  - **쓰기 호출 템플릿(L1)**: collector `_POST_JSON_JS`(cookie `XSRF-TOKEN`→`x-xsrf-token`·`credentials:include`) — 등록도 **같은 인증 패턴**(새 엔드포인트 상수+본문 빌더만 추가). GET=`_GET_JSON_JS`.
  - **등록 결과 재조회(VID/productId 확보)**: `collector.fetch_vendor_inventory`(등록상품명 매칭으로 vid·`vendorInventoryId` 확보·[[feature-vid-source-from-product-list]])·`fetch_product_ids`(노출상품ID=productId·[[api-productid-source-vendor-items-with-vendoritems]]). **등록 직후 정체성 키 확보 경로가 이미 있음**.
  - **이미지(D7)**: `detail_images.extract_from_page`/`extract_via_cdp`(대표/상세 이미지 추출). 등록이 이미지 **참조**(경로/키)로 재사용·직접 import 금지(백본 경유).
  - **이름 정규화**: `product_match`(대장↔리스팅 정밀 매칭·`build_idf`) — 등록 후 대장 매칭에 재사용.
- **⚠위탁계정 = 판매자 OpenAPI 키 발급 불가**([[coupang-openapi-not-available-consignment]]) → 쿠팡 등록도 **API 키가 아니라 WING 세션(브라우저)이 유일 경로**. 공식문서상 "Open API 스키마=골격·**위탁은 UI 경로**"([[coupang-official-reference]])와 일치.
- **쿠팡 상품등록 규격(배경·[[coupang-official-reference]])**: WING **14단계**·상품명 100자·옵션 200·이미지 500×500 흰배경·검색태그(searchTags) 20개·판매불가 품목 존재·엑셀 일괄등록 가능. → 등록 요청 **필수칸·검증이 많음**(§3.1).

---

## 1. 역할·범위

### 하는 것 (D3 상품 등록)
- **신규 상품을 플랫폼에 실제 등록(쓰기)**: 운영대장 입력(01-2)과 D7 이미지를 모아 **플랫폼 등록 요청**을 빌드·검증·미리보기·사람 승인·실행·원장 기록(§3).
- **등록 결과 확정·정체성 연결**: 등록 성공 응답(또는 직후 재조회)에서 **vid·productId** 를 확보해 백본(D9 통계·D8 원장)과 연결(§4.3).
- **멀티플랫폼**: v1=쿠팡(WING)+스마트스토어(커머스 API). 플랫폼별 차이는 **어댑터 뒤**로(§2·§5).
- **성격**: **쓰기 도메인 = 고위험**(위탁계정·Akamai·실운영 사고). → 로드맵 §8-4 (d)·**쓰기 그룹 중 후순위**. §5.4 쓰기 안전 규약 **강제**·무인 자동 등록 **금지**(반자동·사람 승인).

### 안 하는 것 (경계)
- **변경·삭제는 D4**: 가격·옵션·판매상태·재고 변경과 상품 삭제/판매중지는 **D4 상품 관리**(`update_product`·`DOMAIN_DESIGN §2 D4`). D3는 **"신규 등록"만**. (등록 직후 1차 가격/재고 설정이 등록 요청에 포함되면 등록의 일부, 사후 변경은 D4로 넘김.)
- **이미지 추출·가공은 D7**: D3는 D7 산출물(대표/상세 이미지 경로)을 **참조**만. 이미지 추출 로직은 `detail_images`(D7 소유).
- **소싱 판단은 D2**: "무엇을 팔지" 결정은 D2 소싱. D3는 그 결정(후보→등록) 결과를 받아 **등록 실행**만(후보→등록 연계는 백본 경유·§4.3).
- **주문·배송·CS = 범위밖/타도메인**: D5·D6=샵마인, D10=문의(CS). D3 등록 요청에 주문/배송 엔드포인트 **넣지 않음**.

### ⚠01-2 "상품 등록" 입력 칸과 플랫폼 등록의 구분 (중요)
`IO_DEFINITION` 01-2(운영대장 관리상품 16칸)은 **우리 운영대장에 상품을 기록하는 입력**이다. 쿠팡 WING 신규 등록은 그보다 **훨씬 많은 필수 정보**(상품명 100자·카테고리·고시정보·옵션 구조·이미지·배송정보·검색태그 등 14단계)를 요구한다. 따라서 D3는:
- **(a) 운영대장 등록(기록)** — 16칸 입력(이미 정의) + 앱 자동칸(상품코드·VID·링크).
- **(b) 플랫폼 실제 등록(쓰기)** — 등록 **전용 상세 입력**(01-2를 확장한 등록 폼·§4.2 미결 G-R2)을 빌드해 어댑터로 전송.
- 두 흐름의 관계는 **미결(G-R1)**: ①대장에만 기록(수동 WING 등록은 사람)하고 D3는 (a)만 하는가, ②D3가 (b)까지 자동화하는가. 소유자 결정 전엔 **(b)를 전제하지 않는다**(저위험 (a)부터·§8).

---

## 2. 어댑터 사용 (PLATFORM_INTEGRATION 쓰기 인터페이스 — 직접 import 금지·L1 경유)

D3는 플랫폼 SDK/엔드포인트를 **직접 부르지 않는다.** `PLATFORM_INTEGRATION §2` 의 **`PlatformAdapter` 쓰기 메서드**만 호출한다(어댑터=L0/L1 경계 공유 파사드).

| D3가 쓰는 어댑터 메서드 | 의미 | 쿠팡 매핑(미확인) | 스마트스토어 매핑(미결) |
|---|---|---|---|
| `register_product(session, spec) -> RegisterResult` | 신규 상품 등록(쓰기) | WING 등록 API + `_POST_JSON_JS`(엔드포인트 **미확인**·G1) | 커머스 상품 등록 API(권한·엔드포인트 **미결**·G2) |
| `fetch_products(session)` | 등록 직후 재조회(vid/productId 확보·미리보기 현재값) | `fetch_vendor_inventory`+`fetch_product_ids`(이미 구현) | 커머스 상품 목록 API |
| `capabilities()` | 플랫폼이 등록 쓰기를 지원·허용하는지 | `WRITE_REGISTER` 가능 여부 | API/위탁권한 따라(미결) |

- **capabilities 차이(fail-closed·폴백 금지 [[no-silent-fallback-principle]])**: 어댑터가 `register_product` 를 **지원하지 않으면** `capabilities()` 에서 빼고 호출 시 `NotSupported` 예외(조용한 폴백·수동우회 금지). 예: 스마트스토어 위탁 API 키 불가로 판명(G2)되면 등록 쓰기 capability 미제공 → D3는 그 플랫폼 등록을 **막고 로그로 안내**(사람이 플랫폼 UI에서 등록).
- **세션은 조립(L3)이 주입**: D3는 **브라우저를 열지 않는다**(단일 브라우저 원칙·`DOMAIN_DESIGN §4.1`). 조립(pipeline)이 연 `session`(쿠팡=WingBrowser 페이지·스마트스토어=토큰)을 `register_product(session, spec)` 로 받아 쓴다.
- **DTO만 주고받음**: 등록 입력은 플랫폼 중립 `RegisterSpec`(DTO), 결과는 `RegisterResult`(DTO). 어댑터가 플랫폼별 요청 바디로 변환·응답 정규화(§5). D3는 플랫폼 스키마를 **모른다**.
- **중복 금지**: 어댑터 추상화·capabilities·DTO 정규화는 `PLATFORM_INTEGRATION` 소유. D3는 **등록 도메인 로직**(spec 빌더·검증·미리보기·승인 게이트·원장)만 소유(§6).

---

## 3. 쓰기 안전 설계 (§5.4 규약 — 전 플랫폼 공통·강제)

`PLATFORM_INTEGRATION §5.1`·`DOMAIN_DESIGN §5.4` 의 4단계를 D3 등록에 구체화한다. **무인 자동 등록 금지**(반자동·사람 승인 필수).

```
[입력(01-2 + 등록 상세 + D7 이미지)]
      │ ① 빌드
      ▼
RegisterSpec(DTO)  ──② 검증(필수칸·옵션·가격·분류코드·규격)──▶ 실패=차단+사유(등록 안 함)
      │ 통과
      ▼
③ dry-run 미리보기  ── 어댑터 fetch_products 로 중복/현재값 재조회(stale 방지)
      │   (무엇이 등록되나·중복 상품 경고·규격 위반 경고)
      ▼
④ 사람 승인 게이트(UI)  ── 승인 안 하면 종료(PENDING 폐기)
      │ 승인
      ▼
⑤ 실행: register_product(session, spec)
      │
      ▼
⑥ 원장 기록: register_store append (PENDING→COMMITTED/FAILED·전/후·실행자·시각·응답)
      │
      ▼
⑦ 결과 확정: 성공 응답(또는 직후 fetch_products)에서 vid·productId 확보 → 백본 연결(§4.3)
```

### 3.1 ① 등록 요청 빌더 + ② 검증 (등록 전용 로직·D3 핵심)
- **빌더(`register.py`)**: 운영대장 입력 + 등록 상세 + D7 이미지 경로 → `RegisterSpec`(DTO). 플랫폼 중립 형태(어댑터가 플랫폼 바디로 변환).
- **검증(순수 함수·`register_validate.py` 제안)** — 등록 전 **차단형 게이트**(폴백 없음·실패=등록 안 함):
  - **필수칸**: 상품명·카테고리·판매방식·판매가·옵션(최소 1)·대표이미지. (플랫폼별 필수칸 차이=§5·capabilities.)
  - **옵션**: 옵션 구조 유효(옵션명·옵션별 가격/재고)·중복 옵션명 금지·옵션 수 상한(쿠팡 200).
  - **가격**: `판매가 > 0`·숫자. 계약단가(선택)와 정합.
  - **분류코드**: 운영대장 분류코드(13-7 G/P/E…)·플랫폼 카테고리 매핑 존재(미결 G-R3).
  - **규격(쿠팡)**: 상품명 ≤100자·검색태그 ≤20·이미지 규격(500×500 권장)([[coupang-official-reference]]). 위반=경고/차단은 소유자 정책(미결).
  - **중복 방지**: 같은 계정·같은 등록상품명 중복 등록 경고(③ 미리보기에서 `fetch_products` 로 실측 교차확인).

### 3.2 ③ dry-run 미리보기
- 무엇이 등록되는지(요약 spec)·**중복 상품 경고**(어댑터 `fetch_products` 재조회로 동명 상품 존재 확인·stale 수집본 아님)·규격/필수칸 위반 경고를 **UI에 산출**. 이때만 어댑터 읽기 1회(`PLATFORM_INTEGRATION §4` 실시간 재확인 예외).
- **쓰기 전에 아무것도 바꾸지 않음**(순수 계산). 미리보기 산출물은 승인 UI 입력.

### 3.3 ④ 사람 승인 게이트
- UI에서 사람이 미리보기를 확인·승인(무인 금지). 승인 없으면 `register_product` **호출 안 함**.
- 위탁계정 오등록=실운영 사고 → **초기엔 1건씩 반자동**(일괄 등록은 가치·안전 검증 후·§8).

### 3.4 ⑤ 실행 + ⑥ 원장 (멱등·실패/부분성공 복구)
- **멱등 키**: 요청마다 클라이언트 요청ID 부여 → 재시도가 중복 등록을 안 만들게. 플랫폼이 멱등 토큰을 받으면 사용, 아니면 **"실행 전 원장 PENDING → 실행 → COMMITTED/FAILED"**(원장 replay 가 PENDING 잔여=중복 의심 검출·`PLATFORM_INTEGRATION §5.2` 동형).
- **부분 성공**(여러 상품 일괄 등록 중 일부 실패): 성공분=COMMITTED·실패분=FAILED+사유. **전체 롤백 안 함**(플랫폼이 트랜잭션 없음)·사람에게 실패분 재시도 제시.
- **실패 복구**: 실행 중 끊김(세션 만료·Akamai·타임아웃) → PENDING 으로 남음 → 다음 실행에서 **`fetch_products` 재조회로 실제 등록 여부 확인** 후 COMMITTED/재시도 결정(응답 못 받았다고 맹목 재등록 금지=중복 위험).
- **원장(`register_store.py`)**: registry append 패턴(지우지 않고 쌓고 이력 replay·`DOMAIN_DESIGN §5.2`). 저장소=구글시트(R2·`DOMAIN_DESIGN §9 R2`: 앱[서비스계정]만 추가·사람 보기전용·정정 줄+사유·쓰기 PC 하나·`registry_lock` 같은 PC 내). 민감값(비밀번호·계좌) 없음.

---

## 4. 데이터 모델·화면 매핑

### 4.1 데이터 모델 (등록 요청·결과·정체성 연계)
```python
@dataclass
class RegisterOption:
    name: str                 # 옵션명(색상/사이즈/등급)
    sale_price: int           # 옵션 판매가
    stock: int | None = None  # 초기 재고(로켓그로스=입고 흐름 별도·판매자배송=선택)
    barcode: str = ""         # 바코드 13자리(선택)

@dataclass
class RegisterSpec:            # 플랫폼 중립 등록 요청(어댑터가 플랫폼 바디로 변환)
    account_id: str           # 위탁 계정(08-1)
    platform_id: str          # "coupang" / "smartstore"
    product_name: str         # 상품(노출)명 ≤100자(쿠팡)
    category: str             # 플랫폼 카테고리(분류코드→매핑·G-R3)
    sale_method: str          # 로켓그로스/판매자배송/둘다
    options: list[RegisterOption]
    images_rep: list[str]     # 대표 이미지 경로/키(D7 산출물 참조)
    images_detail: list[str]  # 상세설명 이미지(D7)
    search_tags: list[str]    # 검색태그 ≤20(쿠팡)
    notice: dict              # 상품고시정보(플랫폼 필수·플랫폼별 키 다름)
    delivery: dict            # 배송정보(출고지·출고소요일 등·플랫폼별)
    request_id: str           # 멱등 키(클라이언트 생성)
    ledger_code: str = ""     # 운영대장 상품코드(A0000-000·있으면)

@dataclass
class RegisterResult:          # 어댑터가 플랫폼 응답을 정규화
    ok: bool
    platform_product_id: str = ""   # 쿠팡=productId(노출상품ID)·스마트스토어=그쪽 상품ID
    vendor_item_ids: list[str] = field(default_factory=list)  # 쿠팡 vid(옵션별·정체성 앵커)
    vendor_inventory_id: str = ""   # 쿠팡 등록상품ID(그룹키)
    message: str = ""               # 실패 사유·경고
    raw_ref: str = ""               # _raw 원문 사이드카 경로(감사)
```
- **정체성 연계(핵심)**: 등록 성공 후 `RegisterResult` 의 **vid**(쿠팡 옵션 정체성 앵커·불변)·**productId**(노출·가변)를 확보 → 운영대장 자동칸(옵션ID VID·쿠팡 상품 링크 `/vp/products/{pid|0}?vendorItemId={vid}`) 채움·D9 통계 블록 생성·D8 원장 기록. 쿠팡은 응답에 vid 가 바로 없을 수 있어 **직후 `fetch_vendor_inventory`+`fetch_product_ids` 재조회**(이미 구현된 경로)로 확정(G-R4).
- **D7 이미지**: `images_rep`/`images_detail` 는 D7(`detail_images`) 산출 경로/키를 **참조**(D3가 추출 안 함). 등록 시 플랫폼 업로드는 어댑터 책임(플랫폼별 이미지 업로드 API·미확인).

### 4.2 화면 매핑 (`IO_DEFINITION` 01-2 상품 등록 기준)
- **01-2 상품 등록**(운영대장 관리상품 16칸)이 D3 입력의 **기본 폼**: 위탁계정·상품(물류)명·노출상품명·카테고리·분류코드·상품코드(자동)·바코드·판매방식·판매가·계약단가·옵션ID VID(자동)·상품등록일·관리상태·대체상품코드·쿠팡 상품 링크(자동)·비고.
- **등록 상세 폼(제안·01-2 확장·미결 G-R2)**: 플랫폼 실제 등록(§1 (b))에 필요한 추가 입력 — 옵션 구조·대표/상세 이미지 선택(D7)·검색태그·상품고시정보·배송정보. **01-2 16칸으로는 부족** → 등록 상세 하위 화면 필요(IO_DEFINITION 편입은 H_ui 레인·통합 세션 조율).
- **승인 UI**: 미리보기(③)→승인(④) 단계 화면(신규). 기존 app_qt 탭 패턴(백엔드 호출→시그널로 GUI) 동형.
- **자동칸 되쓰기**: 등록 성공 후 상품코드·VID·쿠팡 링크(자동칸)를 **운영대장에 역기록**(구글시트 쓰기·기존 `push_ledger_inventory`/`run_company_stock` 역기록 패턴과 동형·R2 규칙).

---

## 5. 멀티플랫폼 차이 (공통 DTO·플랫폼별 필수칸)

`PLATFORM_INTEGRATION §5.3` 플랫폼 차이표를 등록에 구체화. **공통 DTO(`RegisterSpec`)는 하나**, 어댑터가 플랫폼 바디로 변환·필수칸 차이는 `capabilities()`+검증으로 흡수.

| 항목 | 쿠팡(WING) | 스마트스토어(커머스 API) |
|---|---|---|
| 등록 경로 | WING 세션 same-origin `_POST_JSON_JS`(등록 엔드포인트 **미확인**·G1)·14단계 폼 상응 | 커머스 상품 등록 API(엔드포인트·권한 **미결**·G2) |
| 인증 | 브라우저 세션(위탁·API키 불가·[[coupang-openapi-not-available-consignment]]) | OAuth2 토큰(위탁 발급 가능 여부 **미결**·불가면 등록 capability 미제공) |
| 정체성 결과 | vid(옵션·불변)·productId(노출·가변)·vendorInventoryId(그룹) | 플랫폼 상품ID(`platform_product_id`) |
| 필수칸 특이 | 상품명 100자·검색태그 20·이미지 500×500·상품고시정보·카테고리 메타·옵션 200 | 네이버 카테고리·네이버 상품고시·배송속성(스키마 상이·조사 필요) |
| 밴 위험 | 높음(Akamai·위탁계정)·§5.4 반자동 필수 | 상대적 낮음 추정(공식 API면)·단 미검증 |
| 이미지 업로드 | WING 이미지 업로드 경로(미확인) | 커머스 이미지 업로드 API(미확인) |

- **플랫폼별 필수칸 = 어댑터 검증 + capabilities**: 공통 검증(§3.1)은 D3, **플랫폼 고유 필수칸·규격**(카테고리 코드 체계·고시정보 키·이미지 규격)은 **어댑터가 추가 검증**하고 미충족 시 `register_product` 가 실패 반환(조용한 폴백 금지). D3는 플랫폼 스키마를 모른 채 공통 DTO만 만든다.
- **분류코드→플랫폼 카테고리 매핑**(G-R3): 운영대장 분류코드(13-7)와 쿠팡/네이버 카테고리는 별개 체계 → 매핑 테이블 필요(미결·플랫폼 카테고리 API 조사 선행).

---

## 6. 신규 모듈 제안 (단일책임·CC≤15·≤600줄)

`DOMAIN_DESIGN §2 D3` 제안(`register.py`·`register_store.py`)과 정합. PARALLEL_DEV 에 **레인 D3(등록)** = 편집 소유 `register*`(+D7 연계·읽기만). 어댑터(`platform/*`)는 **레인 P(통합 세션 통제)** 소유 — D3는 **계약(§7)으로만** 호출.

| 파일(제안) | 책임(단일) | 의존(아래로만) | 규모 가이드 |
|---|---|---|---|
| `register.py` | 등록 spec 빌더·미리보기 조립·승인→실행 오케스트레이션(어댑터 `register_product` 호출) | L1(platform 어댑터·`fetch_products`)·L0(session 주입받음) | ≤600줄·CC≤15 |
| `register_validate.py` | 등록 요청 검증(필수칸·옵션·가격·분류코드·규격)=순수 함수 | 의존 0(값만) | 공식만·테스트 쉬움 |
| `register_store.py` | 등록 원장 append/replay(PENDING→COMMITTED/FAILED·멱등) | L1(gsheet_api·registry 패턴) | 〃·R2 규칙 |

- **재사용 우선**(삭제>통합>수정>추가): 새 HTTP 호출을 D3에 짜지 않는다 — 쓰기는 **어댑터 `register_product`**(쿠팡 어댑터가 `_POST_JSON_JS`+XSRF 재사용)·등록 후 재조회는 **기존 `fetch_vendor_inventory`/`fetch_product_ids`**·이미지는 **D7 `detail_images`**·이름 정규화는 **`product_match`**·원장은 **`registry` append 프레임**. D3 신규는 **spec 빌더·검증 규칙·승인 흐름·등록 원장**뿐.
- **쓰기 도메인 = §5.4 강제**: `register.py` 는 반드시 ③미리보기→④승인 게이트를 거친 뒤에만 `register_product` 호출(승인 없이 실행하는 경로 없음·게이트가 검증·§9).

---

## 7. 공개 인터페이스 계약 초안 (제안 시그니처)

착수 시 `docs/L1_CONTRACT.md` 에 D3 섹션으로 핀 추가(아래는 초안·확정 아님). 어댑터 쓰기 메서드 핀은 `PLATFORM_INTEGRATION §9.2`(platform.base) 소관.

```python
# register.py — 등록 오케스트레이션(세션·어댑터는 조립 L3 가 주입)
def build_spec(account_id, platform_id, form: dict, images: dict,
               *, request_id: str | None = None) -> RegisterSpec:
    """01-2 입력 + 등록 상세 + D7 이미지 경로 → 플랫폼 중립 RegisterSpec. 순수 변환(부작용 없음)."""

def preview_register(adapter, session, spec: RegisterSpec,
                     *, log=None) -> RegisterPreview:
    """③ dry-run: 검증(register_validate) + 어댑터 fetch_products 로 중복/현재값 재조회 →
    무엇이 등록되나·경고·차단사유. 쓰기 없음. 검증 실패=차단(RegisterValidationError·폴백 없음)."""

def execute_register(adapter, session, spec: RegisterSpec, store,
                     *, approved: bool, on_log=None) -> RegisterResult:
    """④승인(approved=True 필수·아니면 거부) → ⑤register_product → ⑥원장 append
    (PENDING→COMMITTED/FAILED) → ⑦vid/productId 확보. 무인 자동 금지."""

# register_validate.py — 순수 검증(차단 게이트)
def validate_spec(spec: RegisterSpec) -> list[ValidationIssue]:
    """필수칸·옵션·가격·분류코드·규격 위반 목록(빈 리스트=통과). 플랫폼 고유 필수칸은 어댑터가 추가 검증."""

# register_store.py — 등록 원장(append + replay)
def append_pending(store, spec: RegisterSpec, *, now) -> str: ...   # 멱등: 요청ID 기록
def commit(store, request_id: str, result: RegisterResult, *, now) -> None: ...
def fail(store, request_id: str, reason: str, *, now) -> None: ...
def pending_requests(store) -> list[str]: ...   # 복구: 미확정 요청(실제 등록 여부 재확인 대상)
```
- 반환은 **값 객체(dataclass)만**. 예외 명시(`RegisterValidationError`·어댑터 `NotSupported`·`RankBlocked` 류 전파). `log`/`on_log` 는 기존 관례(`=None`).
- `adapter`·`session` 은 **조립(L3)이 생성·주입**(D3는 브라우저 안 엶·단일 브라우저 원칙·어댑터는 레인 P 소유·직접 import 금지).

---

## 8. 갭·리스크·미결

| # | 항목 | 상태 | 비고 |
|---|---|---|---|
| **G1** | **쿠팡 WING 상품등록 쓰기 엔드포인트·요청 바디** | ⚠**미확인(최우선)** | 현재 전 코드 읽기 전용. 14단계 UI 뒤 데이터 API 경로·이미지 업로드 경로 **라이브 캡처(사무실 DevTools) 선행**. 캡처 전 `register_product` 쿠팡 구현 불가 |
| **G2** | **스마트스토어 커머스 API 위탁 등록 접근성·엔드포인트** | ⚠미결 | 쿠팡 OpenAPI 불가 동형 리스크([[coupang-openapi-not-available-consignment]]). 위탁 API 키 발급 가능?·불가면 등록 capability 미제공(PLATFORM_INTEGRATION G1/G2) |
| **G-R1** | 01-2 입력이 **대장 기록만**인가 **플랫폼 자동 등록**까지인가 | ⚠미결(소유자) | §1 (a)/(b). 저위험 (a)부터 권장. (b) 전엔 D3 쓰기 전제 안 함 |
| **G-R2** | 등록 상세 폼(옵션·고시정보·배송·검색태그) 화면·칸 | ⚠미결 | 01-2 16칸으로 부족. IO_DEFINITION 편입=H_ui·통합 세션 |
| **G-R3** | 분류코드(13-7)→플랫폼 카테고리 매핑 | ⚠미결 | 쿠팡/네이버 카테고리 체계 조사·매핑 테이블 |
| **G-R4** | 등록 응답에 vid 즉시 포함 여부 | ⚠미확인 | 없으면 직후 `fetch_vendor_inventory`+`fetch_product_ids` 재조회로 확정(경로는 이미 있음) |
| **G4** | 밴 위험(쿠팡 쓰기) | 높음 | 위탁계정·Akamai. §5.4 반자동·사람 승인·야간 아닌 **주간 사람 입회** 권장(등록은 수집보다 더 신중) |
| **G-R5** | 멱등·중복 등록 검출 신뢰성 | 미결 | 플랫폼 멱등 토큰 유무 미확인 → PENDING+재조회 방식 기본(§3.4) |
| **G-R6** | 일괄(엑셀) 등록 | 미결 | 쿠팡 엑셀 일괄등록 존재([[coupang-official-reference]])·초기엔 1건 반자동, 일괄은 안전 검증 후 |

- **라이브 미검증**: 본 설계 전부 오프라인 근거. **쿠팡 등록 쓰기는 라이브 캡처(G1) 없이는 구현 불가** — D2(읽기)·D8 2단계와 달리 D3는 조사 의존도가 가장 큼.

---

## 9. 로드맵 단계·게이트/핀 계획 (쓰기라 후순위·오프라인 모킹·dry-run)

### 9.1 로드맵 위치 (`DOMAIN_DESIGN §8-4`)
- **§8-4 (d) 쓰기 그룹 = 마지막**: 소싱(a)→주문/배송 조회(b/c·범위밖이라 생략)→**등록·변경·쓰기(d)**. 선행=`PLATFORM_INTEGRATION §9` 2~3단계(쿠팡 어댑터 파사드·ingest)로 **읽기 경로가 어댑터 뒤로 정리된 후**, G1(쿠팡 등록 엔드포인트 캡처) 해소 후 착수.
- **착수 순서(제안)**: ①G-R1 소유자 결정((a)만 vs (b)까지) → ②G1 라이브 캡처(쿠팡 등록 API) → ③`register_validate.py`+`register.py` 스캐폴딩(미리보기까지·**쓰기 없음**·레인 D3 worktree) → ④오프라인 핀(페이크 어댑터) → ⑤사무실 라이브 **1건 반자동** 등록 실증(사람 입회) → ⑥`register_store` 원장·자동칸 역기록 → ⑦스마트스토어(G2 해소 후).

### 9.2 게이트/핀 (실 쓰기 금지·오프라인 결정적)
- **`verify_register_offline.py`(신규 제안)**: **페이크 어댑터**(`PlatformAdapter` 결정적 구현·브라우저/네트워크 없음)로 `build_spec`→`validate_spec`→`preview_register`→`execute_register` 의 **순서와 게이트**를 검증 — ①검증 실패 시 `register_product` **미호출**(차단) ②`approved=False` 면 실행 안 함 ③원장 PENDING→COMMITTED/FAILED 전이·멱등(같은 request_id 재실행=중복 등록 안 함) ④부분 실패 시 성공분 COMMITTED·실패분 FAILED. **실제 쓰기 절대 금지**(`PLATFORM_INTEGRATION §9.2` "쓰기 테스트=미리보기→승인→원장 순서만" 정합). 실 API 실증은 `VERIFY_REAL_API=1` 옵트인·사무실만.
- **`pin_l1_contract.py`**: D3 공개 API(§7) 핀 1건 추가. 어댑터 `register_product` 시그니처 핀은 `platform.base`(레인 P).
- **`check_complexity.py`**: `register*` 신규 파일 D+(CC≥21) 경고·MI C 추락 차단(기존 게이트 자동 적용).
- **`run_checks.py`** 러너에 1줄 등록(append 친화·PARALLEL_DEV 충돌 핫스팟).
- **되돌림/정책 변경은 실측 근거 필수**([[fix-from-real-evidence]]): 등록 엔드포인트·필수칸은 라이브 캡처 결과를 명문화(추측 금지).

---

SSOT = 이 문서(D3 상품 등록 상세) · `designs/PLATFORM_INTEGRATION.md`(어댑터 쓰기 인터페이스·토대) · `docs/DOMAIN_DESIGN.md §2 D3·§5.4`(도메인 지도·쓰기 안전) · `docs/L1_CONTRACT.md`(계약) · `designs/IO_DEFINITION.md`(01-2 입력 칸). 구현 착수는 소유자 지시 + G-R1 결정 + G1(쿠팡 등록 엔드포인트) 라이브 캡처 후.
