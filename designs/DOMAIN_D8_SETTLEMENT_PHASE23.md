# 설계: D8 정산/원장 도메인 — 2·3단계 + 흡수 3영역(계약·사업·채권자)

> 상태: **설계 초안(2026-10-05) · 전면 구현 보류.** 이 문서는 D8 정산/원장의 **2단계(라이브 수집)·3단계(계약 대비 정산)**
> 와, 2026-10-05 소유자 결정(DOMAIN_DESIGN §9 R5)으로 D8에 **흡수된 계약·사업(업무일지)·채권자** 영역의 설계 SSOT다.
> 상위: `docs/DOMAIN_DESIGN.md §2 D8`·`designs/SETTLEMENT_MODULE.md`(1단계 계산 SSOT)·`designs/LEDGER_REGISTRY.md`(원장 패턴 SSOT).
> 근거: `designs/COUPANG_SETTLEMENT_DOMAIN.md`(도메인 지식)·`designs/coupang_golden_cases.json`(완료 조건)·`designs/IO_DEFINITION.md`(화면 칸)·
> 실측 코드(`registry_*`·`holiday_*`·`payout`·`settlement_*`·`collector`).
> 소유자 확정은 "(확정)", 제안·미결은 "(제안)"/"(미결)"로 표기. **전체 재작성 금지·최소·재사용 우선(registry 패턴 그대로).**

---

## 0. 왜 이 문서인가 (1단계와의 경계 — 이미 된 것·남은 것)

### 0.1 이미 구현 완료(1단계 = 오프라인 정산 계산 · D8_ledger 레인 · 골든 100%)
실측(2026-10-05, `src/coupang_analytics/`):
- `holiday_kr.py` — 영업일·대체공휴일(순수)·`holidays(year,*,fetch,cache_dir,extra)` 캐시+소스 주입·실패=`HolidaySourceError`.
- `holiday_source.py` — **2단계용 실 소스 어댑터 이미 작성됨**(천문연 `getRestDeInfo` `make_fetch(key)`·키=credstore `__holiday_kr__`). ⚠**라이브 1회 조회만 남음**.
- `payout.py` — 지급일 6종 `payout_date(policy,*,week_end,revenue_month,holidays)`·`payout_amount`·`estimate`(`is_estimate=True`).
- `settlement_amount.py` — `mp_revenue`·`rg_payout`·`rg_home_profit`(전부 keyword-only·정수 아니면 `TypeError`).
- `settlement_parse.py` — 판매분석 19열 파서·불변식 `check_invariants`·메타 강제·`SettlementParseError`.
- `tools/verify_settlement_offline.py` — 게이트 **이미 등록됨**(`run_checks.py` CHECKS 6번째·전체 10종째).

→ **지급일·금액·파싱·불변식은 전부 오프라인·결정적으로 완성**. 라이브 근거도 확보됨(`SETTLEMENT_MODULE.md §5.1`: 실계정 화면·판매현황 xlsx 16/16 불변식).

### 0.2 남은 것(이 문서의 범위)
| 단계 | 한 줄 | 선행 조건 | 런타임 |
|---|---|---|---|
| **2단계 라이브 수집** | 정산·매출현황을 주 1회 자동 수집해 1단계 계산에 투입 | WING 정산 API 경로 `[미확인]` → `diag` 실측 필요 | 라이브·직렬(야간 슬롯) |
| **3단계 계약 대비 정산** | 계약서 입력 → 수익 계산식 → 계정별 달성률 산출 | 실제 계약서 수령 → 조건 스키마 확정 | 오프라인(계산·골든) |
| **흡수 계약** | 계약서 원장(11-3)·수익 계산식 = 3단계의 직접 입력 | 계약서 수령 | 오프라인 |
| **흡수 사업/업무일지** | 위탁 운영 기록(11-4) append 원장 | — | 오프라인 |
| **흡수 채권자** | 채권/상환 원장(12-x)·파일 분리·권한·가림 | 상환 배분 기준=법률 검토 후 소유자 | 오프라인 |

### 0.3 공통 원칙(이 문서 전체에 적용)
- **재사용 우선(변경 우선순위 삭제>통합>수정>추가)**: 새 원장 3종은 `registry_*`의 **패턴·헬퍼를 그대로** 쓴다(아래 §4.0).
- **폴백 금지**([[no-silent-fallback-principle]]): 수집 실패·소스 실패·값 변환 실패는 **ERROR raise 또는 명시 로그**, silent 0/None 금지.
- **쓰기 안전 규약**(DOMAIN_DESIGN §5.4): 라이브 쓰기(2단계는 **읽기만**이라 해당 없음·3단계 원장 쓰기는 dry-run→승인→실행→기록).
- **게이트 강제**: 새 함수 CC≤15·파일 ≤~600줄·테스트 실 API 금지·`run_checks` 초록(§9).
- **비밀·개인정보 원문 금지**: 채권자 이름·연락처·계좌, 정산 계좌는 화면·결과·로그·git 평문 금지(원장 파일 예외는 §4.3에 한정).

---

## 1. 2·3단계 범위·전제

### 1.1 레인·소유
- **D8_ledger 레인**(= `registry_*`·`holiday_*`·`payout`·`settlement_*` 소유, `docs/PARALLEL_DEV.md` E 레인)이 신규 도메인 모듈을 **greenfield**로 추가 → 비겹침·병합 충돌 0.
- **공유 파일 수정은 통합 세션에만 요청**(레인 직접 금지): `config.py`/`appconfig`(§8 설정키)·`collector.py`(§2 수집 프리미티브 — L1 공유)·`pipeline.py`(배선)·`docs/L1_CONTRACT.md`+`tools/pin_l1_contract.py`·`tools/run_checks.py`(게이트 1줄).
- **UI = H_ui 레인**(`ui/*`). 화면 매핑은 §5, 배선은 H_ui.

### 1.2 전제(선행 조건)
- **2단계**: WING 세션(L0 `WingBrowser`)·정산 API 경로 확정(현재 `[미확인]` — §2.3 diag 먼저). 런타임 직렬(단일 브라우저·위탁계정·Akamai).
- **3단계**: 실제 계약서 수령 → §3.1 조건 스키마 확정(지금은 입력 요구 목록만, `COUPANG_SETTLEMENT_DOMAIN.md §8`).
- **채권자**: 상환 **배분 기준은 법률 검토 후 소유자**가 정함 — 앱은 **계산·기록·감사만**(법률 판단 금지·[[business-context-consignment-creditors]]).

---

## 2. 2단계 — 라이브 수집 설계

> 목적: 1단계 계산기(payout·settlement_amount·settlement_parse)가 쓰는 **원시 데이터**(정산내역·매출내역·판매수수료·부가 리포트)를
> 사람 다운로드 대신 **앱이 주 1회 자동 수집**한다. **읽기 전용**(쓰기 도메인 아님) — 쓰기 안전 규약 비해당.

### 2.1 무엇을·언제 (수집 대상·주기, 확정분은 SETTLEMENT_MODULE §9.0)
| 데이터 | 주기(확정) | 실행 슬롯 | 1단계 투입처 |
|---|---|---|---|
| 판매현황(판매분석 vi-detail-search) | **매일**(현행 유지·변경 없음) | 기존 ①판매수집 야간 18:00 | `settlement_parse`(이미 적재 경로 있음) |
| 윙 정산내역(settlement-histories) | **주 1회**(주 마감 다음날=월) | 야간 배치 직렬 슬롯 | `payout`(지급일 대조)·실지급 정본 |
| 윙 매출내역 | 주 1회 | 〃 | `settlement_amount.mp_revenue`(E=A−B−C−D) |
| 로켓그로스 판매수수료 리포트 | 주 1회 | 〃 | `settlement_amount.rg_payout`·`rg_home_profit` |
| 로켓그로스 부가 리포트(밀크런·광고·CFS·창고·재고손실) | 주 1회 | 〃 | `rg_payout` 조인(누락=이익 과대·함정 5) |

- **근거(확정)**: 정산은 주 단위 확정이라 매일 볼 실익 낮음 → 확정분만·트래픽/차단 최소. 판매분석과 주기 분리(판매=매일·정산=주1회).
- **미구매확정 구간(함정 4)**: 결제일 기준 월 집계는 익월 중순까지 미확정 → 출력에 "미확정 구간" 표시(주 1회여도 월 집계는 익월 중순 이후 안정).

### 2.2 어떻게 (collector 확장점 — 재사용)
collector의 **same-origin fetch 프리미티브를 그대로 재사용**한다(실측 `collector.py`):
- `_POST_JSON_JS`/`_GET_JSON_JS` = 로그인 세션 쿠키 `XSRF-TOKEN`→`x-xsrf-token` 헤더·`credentials:include`. **신규 도메인은 새 엔드포인트 상수 + 파서만 추가**(DOMAIN_DESIGN §4.1).
- `_raw_add(api, body)` = 응답 원문 gzip 보관(분석·비200도). 정산 수집도 동일하게 `_raw_add("settlement", …)`.
- 페이지네이션 패턴 = `fetch_sales_details`의 `paginationDetails.totalPages` 루프 복제.
- 비200·JSON 파싱 실패 = **`SalesFetchError` 류 예외**(silent 금지).

**(제안) 확장 방식 2안**:
- **(a) collector에 `fetch_settlement_histories(page, ym, *, log)` 등 신규 함수 추가** — L1 공유 프리미티브. 통합 세션이 `collector.py`에 엔드포인트 상수 + 파서 추가(레인은 요청). **권장**(기존 fetch_* 와 같은 자리·같은 패턴·L1 계약 한 곳).
- (b) D8 레인 전용 `settlement_collect.py` 신규 — collector 프리미티브(`_POST_JSON_JS`)를 import해 정산 전용 fetch. collector를 건드리지 않아 레인 독립성↑, 단 밑줄 프리미티브 교차 import = L1 누수(`kw_metrics→rank._load_results`와 같은 안티패턴) → **비권장**.
- → **결론(제안)**: (a). 단 API 경로 확정(§2.3) 전까지는 **엑셀 다운로드 폴백**(아래)만 배선.

**엑셀 다운로드 폴백(API 미확인 구간의 1차 경로)**: 정산 화면 엑셀 다운로드는 `collector`에 이미 다운로드 대기 패턴(`_fresh_download_dir`·`_wait_new_xlsx`·CDP 다운로드 이벤트)이 있다 → **그 패턴 재사용**해 사람이 누르던 "엑셀 다운로드"를 세션에서 트리거하거나, 담당자 다운로드 파일을 폴더 적재(1단계 경로)로 흡수. `settlement_parse`가 이미 xlsx 파서를 가지므로 **매출내역·판매수수료 리포트용 파서만 신규**(헤더 매핑·`COUPANG_SETTLEMENT_DOMAIN §4.1` 스키마).

### 2.3 API 미확인 플래그 (`[미확인]` = 라이브 실측 필요)
| 경로 | 상태 | 비고 |
|---|---|---|
| 윙 정산내역 Open API `GET …/settlement-histories?revenueRecognitionYearMonth=YYYY-MM` | **경로 확인됨·접근 미확인** | ⛔위탁계정=판매자 OpenAPI 키 발급 불가([[coupang-openapi-not-available-consignment]]) → **WING 세션 쿠키로 호출 가능한지 라이브 확인 필요** |
| 윙 매출내역 조회 API | `[미확인]` | 화면 엑셀 다운로드로 우회 |
| 로켓그로스 판매수수료 리포트 API | `[미확인]` | 〃 |
| 부가 리포트(밀크런·광고·CFS·창고·재고손실) API | `[미확인]` | 〃·조인키도 미확인 |
| 판매분석 vi-detail-search | **확인됨**(기존 수집) | 변경 없음 |

- **선행 도구(이미 작성됨)**: `tools/diag_settlement_endpoints.py <계정ID>` — 사무실에서 사람이 정산 메뉴를 누르는 동안 xhr/fetch를 **관찰만**(스스로 요청 안 함·금액/이름/주문번호 **값 비저장**·ID·날짜 자리표시 마스킹·엑셀은 파일명만). 결과 `output/_diag/`. **이 결과가 나와야 (a) collector 확장(엔드포인트·질의·응답 구조)을 설계할 수 있다.**
- (미결) diag 실측 전까지 2단계는 **엑셀 다운로드/폴더 적재 경로만** 배선하고, API 직접 조회는 diag 결과 확정 후 추가.

### 2.4 실패 처리 (폴백 최소화)
- **수집 실패(비200·네트워크·세션 만료)** = 그 계정·그 주 수집 **건너뜀 + 명시 로그**, 다음 계정 진행(기존 `run_full` "한 계정 실패해도 다음 진행"과 동일). 전체 중단 아님.
- **공휴일 소스 실패** = `HolidaySourceError`(지급일 계산 중단·0일 가정 금지·이미 구현).
- **부가 리포트 조인 누락** = 이익 과대(함정 5) → `rg_payout`가 0 대입 금지·**호출부가 조인 누락을 먼저 확인**(이미 `settlement_amount.rg_payout` docstring에 명문). 누락 시 "조인 불완전" 플래그 출력.
- **계산값 vs 실지급** = 계산은 예측(`is_estimate=True`)·**실지급은 API/파일 값이 정본**(화면 경고). 주 1회 수집이 확정분(정산확정 status) 우선.

### 2.5 런타임 경계
- 정산 수집 = 라이브·**직렬**(런타임 병렬 금지·단일 브라우저·`docs/PARALLEL_DEV.md`). 야간 배치의 **별도 슬롯**(판매수집 ① 다음·로그인 세션 재사용).
- 무인 `--auto`와의 관계(제안): 정산 수집은 **읽기 전용**이라 무인 허용 가능(그로스 재고 역기록·쿠팡확인과 동급). 단 주 1회만 → 요일 가드(월요일만 실행). 최종 결정은 소유자.

---

## 3. 3단계 — 계약 대비 정산

> 목적: 계약서의 **수익 계산식·약정이익금·계약금**을 입력받아, 1·2단계 실지급 누적과 대조해 **계정별 달성률·잔액·예상 달성일**을 산출.
> SSOT 선행: `SETTLEMENT_MODULE.md §7`·`COUPANG_SETTLEMENT_DOMAIN.md §8`. **실제 계약서 수령 후 스키마 확정**(지금은 입력 요구 목록).

### 3.1 계약서 입력 → 수익 계산식 (계정/상품별·계약서 필요)
`COUPANG_SETTLEMENT_DOMAIN §8` + IO_DEFINITION 계약서(11-3) 칸 기준 입력 요구:
- **계약금**(금액·VAT·납부일·분할·반환조건)
- **수수료**(요율/정액 + 산정기준: 매출 / 정산대상액 / 실지급 / 순이익 **택1**)
- **약정이익금**(정액/정률·월/전체·미달 시 보전/연장/소멸)
- **계약기간 + 귀속 기준일**(결제일 / 구매확정일 / 지급일 택1)
- **비용 부담 주체**(원가·광고·쿠폰·CFS·밀크런·반품 = 계약자/회사)
- **분배 주기·지급일·세금계산서 주체**
- **수익 계산식**(IO 11-3 "수익 계산식" 칸 = 계약 정산 04-6이 그대로 씀)
- **셀독 상품이 고객 계정에서 판매될 때**: 계정 주인 몫 = 판매액의 일정 비율(소유자 2026-10-02 확정·[[business-context-consignment-creditors]]) → 사업 꼬리표(상품 단위)별 수익 규칙.

(제안) **수익 계산식 표현**: 자유 수식 문자열은 파싱·보안·검증이 어려움 → **구조화된 규칙 객체**(산정기준 enum + 요율/정액 + 비용부담 플래그 집합)로 모델링하고, 계약서의 자연어 식은 비고로 보존. 계약서 실물 수령 후 어떤 조합이 실제로 나오는지 보고 enum 확정(미결).

### 3.2 산출 (`settlement.py` 퍼사드 — 신규·greenfield)
- 계정별 **누적 실지급 vs (계약금 + 약정이익금)** 달성률·잔액·**예상 달성일**(지급 예정분 포함·`payout.estimate`로 미래 지급일 추정).
- 입력: (계약 조건 = §4.1 계약 원장) + (실지급 누적 = 2단계 수집 or 1단계 파일 적재) + (관리 기간 = 원장 `managed_between`).
- 원장(`registry_*`)이 **이력 보관**, `settlement.py`는 **계산**(SETTLEMENT_MODULE §0 분담 유지).

### 3.3 골든케이스 확장 방법 (완료 조건)
- 현재 `coupang_golden_cases.json` = `payout_date[12]`·`amount_formula[2]`·`insights_row_invariants[4]`·`invariant_rules[3]`(실측 확인).
- 3단계 추가(제안): **`contract_achievement[]`** 섹션 — 케이스마다 {계약조건, 실지급 누적 입력, 기대 달성률·잔액·예상 달성일}. `_meta.holidays_used`는 예상 달성일 계산에 재사용.
- 검증: `tools/verify_settlement_offline.py`에 `contract_achievement` 대조 블록 **append**(기존 payout/amount/invariant 3블록 옆). **실 계약서 1건 이상 수령 후** 소유자 확인값으로 골든 작성(실측 근거·[[fix-from-real-evidence]]).
- 완료 판정 = 추가 골든 100% 통과.

---

## 4. 흡수 3영역 데이터 모델 (계약·사업/업무일지·채권자)

### 4.0 공통 — registry 패턴 재사용 (핵심 재사용 결정)
세 영역 모두 **"지우지 않고 쌓는 append 원장 + 상태는 이력 replay"**가 적합(DOMAIN_DESIGN §5.2가 이미 "registry 패턴을 신규 원장의 백본 표준"으로 규정). `registry_*`의 아래 **구성·헬퍼를 그대로 재사용**(제안):

| 재사용 자산(실측) | 어디서 | 신규 원장에 적용 |
|---|---|---|
| append-only·최신 위·**번호 연속 무결성**·전체 되돌리면 빈 원장 | `registry_history.check_integrity`·`_rewind` | 동일 불변식 |
| **상태 = 이력 replay**(`_replay_status`) | `registry_core` | 계약 유효/만료·채권 잔액 = 이력 계산 |
| **과거 시점 복원**(`as_of`)·관리기간(`managed_between`) | `registry_history` | 계약 as_of·채권 잔액 as_of |
| **동시 쓰기 잠금**(`registry_lock`·OS 파일락·크래시 자동해제) | `registry_lock` | 원장 쓰기 PC 하나(R2④)·같은 PC 내 직렬 |
| **구글시트 시트 생성·서식·보호**(`addProtectedRange warningOnly`·확인상태만 unprotected·헤더 고정·필터·RAW 쓰기) | `registry_gsheet.init_sheets`·`_format_requests` | 사람 보기전용·앱만 쓰기(R2①) |
| **로컬 백업**(`backup_local` xlsx) | `registry_gsheet` | 실행마다 백업(채권자는 §4.3 예외) |
| **값 정규화**(`canon`·천단위/날짜 통일·`canon_pw` 원문 보존) | `registry_model` | 가짜 '수정' 방지 |
| **헤더 이름 탐지**(열 이동 내성·`config.IN_ALIASES_*`) | `registry_model._ledger_columns` | 동일 |

- (제안) **공용 원장 프레임 추출 여부는 측정 후 결정**(미결): 당장은 세 원장을 `registry_*` 패턴을 **모방한 독립 모듈**로 짓고, 3개가 실제로 중복(죽은코드·복잡도·중복 측정)으로 확인되면 그때 공용 프레임으로 통합(삭제>통합). **선제 추상화 금지**(전체 재작성 금지·측정 기반). `registry_core.Registry`/`RegRow`는 셀독원장 열에 특화돼 그대로 재사용은 부적합 → 패턴·헬퍼 재사용에 한정.

### 4.1 계약 — 계약서 원장 (`contract_store.py` 신규·제안)
- **엔티티**: 계약(사업자/대표자/위탁계정 × 사업 꼬리표). IO 11-3의 13칸(계약일자·기간·수익 배분/기준/계산식·계약금/단가/수량/금액·비용부담·정산시점·귀속기준일·정산계좌·수탁자·해지/특약/계약서 위치).
- **원장 성격**: 계약은 개정될 수 있음 → **버전 이력**(계약 변경 = 새 이력 줄·`as_of(날짜)`로 그 시점 유효 계약). 기존 `registry_history.as_of` 패턴 재사용.
- **상태 replay**: 유효/만료/해지 = 이력에서 계산(계약기간·해지 이력). "30일 전부터 만료 예정"(IO 검사규칙)은 렌더 시 계산.
- **민감**: **정산 계좌·수탁자 사업자번호 = 민감(가림)** — 대표·정산 담당만 원문(§4.3 권한 모델 공유). 계약서 파일 위치 = 링크만.
- **3단계 연결**: 이 원장이 §3.1 계약 조건의 **저장소**, `settlement.py`가 소비(SETTLEMENT_MODULE §7 "원장이 계약 조건 보관"의 구현처). ⚠기존 셀독원장 "계약금 Y" 외 수수료·약정이익금 열은 **셀독등록원장에 넣지 않고 계약 원장(신규)에** 둔다(원장 책임 분리·LEDGER_REGISTRY 소유와 협의 불필요해짐).

### 4.2 사업/업무일지 — 운영 기록 원장 (`worklog_store.py` 신규·제안)
- **엔티티**: 업무일지(일자·작성자·위탁계정·상품·내용·후속조치·상태). IO 11-4의 6칸. = 위탁 **운영 기록**(관리대장 C~T 날짜별 관리내용 흡수).
- **원장 성격**: 순수 append 로그(개정·replay 거의 없음) → registry 패턴 중 **이력 3종 공통 형식**(번호 연속·최신 위·추가만)만 차용, `as_of` 복원은 불필요(제안).
- **상태**: 진행/완료/보류 = 줄 자체의 상태 칸(이력 replay 불필요). "7일 넘은 진행 표시"(IO 검사) = 렌더 계산.
- **D10 문의(CS)와 경계**: 업무일지=**내부 운영 기록**(D8) · 문의(CS)=위탁처/고객 응대(D10 신규). 혼동 금지(DOMAIN_DESIGN §2 D10 명문).
- **사업 꼬리표**: 사업 유형(셀독관리·위탁관리·광고대행·상품위탁판매…)은 **상품 단위 꼬리표**(계정 단위 아님·소유자 2026-10-02) → 업무일지·계약·정산이 이 꼬리표로 분류. 코드 수정 없이 유형+수익규칙 등록으로 확장(미결: 꼬리표 저장 위치 = 분류코드 13-7과 통합 여부).

### 4.3 채권자 — 채권/상환 원장 (`creditor_store.py` 신규·제안·R2② 규칙)
> ⚠ **법률 민감**: 파산 전 특정 채권자 우선 변제는 취소될 수 있음(채권자 평등). **배분 기준은 소유자가 법률 전문가와 정하고, 앱은 계산·기록·감사만**. Claude는 법률 판단 금지([[business-context-consignment-creditors]]).

- **엔티티**: 채권자(약 370명)·채권 확정·상환 기록·응대 기록. IO 12-x의 5칸(번호 C-0000·이름/연락처·상환계좌·채권확정/상환 기록·응대 기록).
- **원장 성격**: **돈 원장** → append-only·정정은 **반대 기록**(지우지 않음·IO 검사규칙)·잔액 = 이력 replay(채권확정 − 상환 누적). `registry_core._replay_status` 패턴을 **금액 누적**으로 변형.
- **파일 분리(R2②·확정)**: 채권자 원장은 **별도 스프레드시트**(결과/대장/셀독원장과 분리)·**공유 최소**(소유자·대표·정산담당·서비스계정만, 창고/직원 공유 금지).
- **권한·가림(확정)**:
  - **이름·연락처·상환계좌 = 민감(가림)** — 화면 기본 가림(마스킹)·**원문은 대표/정산담당만**·상환계좌는 **대표만**(IO 12-x).
  - **열람 기록**(access log): 누가 언제 원문을 봤는지 별도 이력(감사). (제안) 열람 이력도 append 원장 1줄.
  - 앱 로그·결과시트·git·백업에 **원문 금지**. 로컬 백업(§4.0)은 채권자 원장 **제외 또는 가림본만**(관리대장이 평문 비번 때문에 로컬 백업 생략하는 선례와 동일·[[gsheet-unified-spec]] 작업 전 백업 401 수정 맥락).
- **상환 배분**: 앱은 (배분 규칙이 소유자/법률로 확정되면) 그 규칙대로 **계산·기록·감사만**. 규칙 자체는 하드코딩 금지·설정/입력으로 받음. **미확정 상태에선 기록(채권확정·수동 상환 입력)만** 구현.

---

## 5. 화면 매핑 (IO_DEFINITION ↔ 모듈 ↔ 단계)

| 화면(메뉴 ID) | 내용 | 데이터 소스·모듈 | 단계 |
|---|---|---|---|
| **04-1 정산 현황** | 판매분석 xlsx [파일 올리기]·정산건·지급일 | `settlement_parse`+`payout`+`settlement_amount`(1단계) · 2단계 자동 수집으로 대체 | 1·2 |
| **04-6 계약 정산** | 계약 수익 계산식 적용·달성률 | `settlement.py`(3단계)+`contract_store` | 3 |
| **08-1 판매처·계정** | 계정·비번(가림)·위탁상태·계약금 | 셀독원장(`registry_*`·기존) | — |
| **08-3 변경 이력** | 원장 이력·확인상태 승인/반려 | `registry_gsheet`(기존) | — |
| **11-3 계약** | 계약서 13칸(정산계좌 가림) | `contract_store`(신규) | 흡수 |
| **11-4 업무일지** | 운영 기록 6칸(새 중분류) | `worklog_store`(신규) | 흡수 |
| **12-1~12-4 채권자** | 채권자·채권확정·상환·응대(가림) | `creditor_store`(신규·별도 파일) | 흡수 |
| **13-8 정산 규칙** | 지급일 규칙·공휴일·끝수 처리 | `config`(정산 설정·§8) | 2·3 |

- UI 배선 = **H_ui 레인**(`ui/*`). D8은 데이터·계산 함수만 제공(직접 import 금지·인터페이스 연결·LEDGER_REGISTRY §10-1 분담 선례).

---

## 6. 신규 모듈 제안 (단일 책임·CC≤15·≤600줄·greenfield)

| 신규 모듈 | 책임 | 재사용 | 단계 |
|---|---|---|---|
| `settlement.py` | 1단계 모듈 조립 퍼사드 + 3단계 계약 대비 달성률 산출 | `payout`·`settlement_amount`·`settlement_parse`·`contract_store` | 3 |
| `settlement_collect.py` **또는** collector 확장 | 정산·매출·부가 리포트 수집(fetch·파서) | `collector._POST_JSON_JS`·`_raw_add`·다운로드 패턴 | 2 |
| `settlement_report_parse.py` | 매출내역·판매수수료·부가 리포트 xlsx 파서(판매분석과 별도 스키마) | `settlement_parse` 변환 헬퍼(`parse_int`·`parse_id`·`parse_date`) | 2 |
| `contract_store.py` | 계약서 원장(버전 이력·as_of·유효/만료 replay) | `registry_history`·`registry_gsheet` 서식·`registry_lock` | 흡수/3 |
| `worklog_store.py` | 업무일지 append 원장(번호 연속·상태 칸) | `registry_model` 이력 형식·`registry_gsheet` | 흡수 |
| `creditor_store.py` | 채권/상환 원장(금액 누적 replay·정정=반대기록·가림·열람 로그) | `registry_core` replay 변형·별도 파일·권한 | 흡수 |

- **분해 지침**: 수집·파서·계산을 한 함수에 섞지 말 것(SETTLEMENT_MODULE 1단계 분리 선례). 수집=fetch만·파서=파일/격자→객체·계산=순수.
- **greenfield = 병합 충돌 0**(기존 파일 미수정). 공유 파일(§1.1)만 통합 세션 요청.

---

## 7. 공개 인터페이스 계약 초안 (제안 — 확정은 구현·소유자 승인 시)

> L1 계약에 올릴 후보. pipeline/ui가 부르게 될 때 `docs/L1_CONTRACT.md` 절 추가 + `tools/pin_l1_contract.py` 골든 등록(통합 세션).

**2단계 수집(collector 확장·L1 프리미티브)**
```
collector.fetch_settlement_histories(page, *, revenue_month: str, log=None) -> list[SettlementRecord]
    # settlement-histories (API 확인 후). 비200/파싱실패=SettlementFetchError. _raw_add 보관.
collector.fetch_revenue_report(page, *, period, log=None) -> ...        # [미확인] — diag 후 확정
settlement_report_parse.parse_revenue_xlsx(path, *, meta, on_log=None) -> RevenueFile
settlement_report_parse.parse_rg_fee_xlsx(path, *, meta, on_log=None) -> RgFeeFile
```
**3단계 계약 대비 정산(settlement.py 퍼사드)**
```
settlement.achievement(contract, payouts, *, holidays, as_of=None) -> Achievement
    # Achievement(달성률, 잔액, 예상_달성일, is_estimate=True)
```
**계약 원장(contract_store)**
```
contract_store.load(client) -> ContractLedger
contract_store.as_of(ledger, account_id, at) -> Contract | None        # registry as_of 패턴
contract_store.run_sync(client, read_contracts, *, now, log, dry_run, backup_dir) -> SyncResult
```
**채권자 원장(creditor_store·가림·권한)**
```
creditor_store.load(client, *, viewer_role) -> CreditorLedger           # role 에 따라 가림본/원문
creditor_store.balance(ledger, creditor_id, *, as_of=None) -> int       # 채권확정 − 상환 누적
creditor_store.record_repayment(client, entry, *, actor, dry_run, lock_path) -> int  # append·열람/쓰기 로그
```
- 전부 **keyword-only·실패 raise·dry_run 지원**(registry 함수 시그니처 관례와 일치).

---

## 8. 설정키 (통합 세션이 `config.py`/`appconfig`에 정의 — 현재 미존재·실측 확인)

실측: `config.py`에 `settlement/*` 키 **아직 없음**(SETTLEMENT_MODULE §8은 제안 상태). IO_DEFINITION 13-8 "정산 규칙"도 계획.

| 키(제안) | 용도 | 비밀? |
|---|---|---|
| `settlement/source_dir` | 정산·판매분석 파일 적재 폴더(1단계·엑셀 폴백) | 아니오(appconfig) |
| `settlement/output_url` | (선택) 정산 결과 시트 | 아니오 |
| `settlement/payout_rules` | 지급일/끝수 처리 규칙 토글(13-8) | 아니오 |
| `__holiday_kr__` | 공휴일 API 서비스키 | **예(credstore·이미 사용)** |
| `contract/url` | 계약 원장 시트 | 아니오 |
| `creditor/url` | **채권자 원장 시트(별도·공유 최소)** | 아니오(URL)·내용은 가림 |

- 비밀 아닌 값=`appconfig`(config.json)·비밀=credstore. 레인은 값 필요 시 통합에 요청(직접 편집 금지).

---

## 9. 갭·리스크·미결

- **G1 WING 정산 API 미확인(최우선)**: settlement-histories가 WING 세션 쿠키로 호출되는지, 매출/판매수수료/부가 리포트 API 경로 — 전부 `[미확인]`. **`diag_settlement_endpoints.py` 라이브 실측(사무실)이 선행**. 그 전엔 엑셀 폴백만.
- **G2 부가 리포트 조인키 미확인**: 밀크런·광고·CFS를 판매수수료 리포트와 잇는 키 미확인(함정 5 = 이익 과대). 조인 불완전 시 플래그 필수.
- **G3 계약 조건 스키마 미확정**: 실제 계약서 수령 전 §3.1은 입력 요구 목록. 수익 계산식 표현(자유식 vs 구조화 규칙) = 계약서 보고 확정(미결).
- **R1 채권자 법률 리스크**: 상환 배분 기준 = 법률 검토 후 소유자. 앱은 계산·기록·감사만. **배분 규칙 미확정 중엔 기록만 구현**. 개인정보 370명 = 파일 분리·가림·열람 로그·백업 제외(§4.3).
- **R2 무인 쓰기 범위**: 2단계 수집=읽기(무인 가능·제안)·3단계 계약 원장 쓰기=쓰기 안전 규약(dry-run→승인·무인 금지). 채권자 상환 기록 = **무인 절대 금지**(사람 승인·감사).
- **R3 공용 원장 프레임 추출**: 세 원장 중복이 측정으로 확인되면 통합(지금은 선제 추상화 금지·§4.0).
- **미결**: 사업 꼬리표 저장 위치(분류코드 13-7 통합 여부)·판매처 확대(스마트스토어·토스·G마켓·당근) 정산 수집 방법·빠른정산(셀러월렛) 수수료/조건.

---

## 10. 로드맵 단계 · 게이트/핀 계획

점진 이행(big-bang 금지·측정 기반·작게 자주 커밋·게이트 초록 유지):

1. **2단계-a (선행 실측)**: `diag_settlement_endpoints.py` 사무실 라이브 → `output/_diag/` 로 API/엑셀 경로·질의·응답 구조 확정. **코드 추가 없음**(관찰만).
2. **2단계-b (엑셀 폴백 파서)**: `settlement_report_parse.py`(매출내역·판매수수료·부가 리포트 xlsx) — 오프라인·결정적. 게이트: `verify_settlement_offline.py`에 리포트 파서 불변식 블록 **append**.
3. **2단계-c (라이브 수집)**: diag 확정 후 `collector.fetch_settlement_*` 추가(통합 세션·L1 계약+핀) → 야간 직렬 슬롯 배선(pipeline). 라이브 실측(사무실).
4. **3단계 (계약 대비)**: 실 계약서 수령 → §3.1 스키마 확정 → `contract_store.py` + `settlement.py` 달성률 → `coupang_golden_cases.json`에 `contract_achievement[]` 추가 → `verify_settlement_offline` 대조 블록 append. H_ui 04-6 표시.
5. **흡수 원장 (병행 가능·오프라인)**: `contract_store`→`worklog_store`→`creditor_store` 순(독립성 높은 것부터). 각각 **신규 오프라인 검증 스크립트** 신설·게이트 등록.
   - ✅ **1단계 구현 완료(2026-10-05·E 레인 worktree `d8-ledger-absorb`)**: `worklog_store`(append·상태·'7일 지연' 렌더)·`contract_store`(버전 이력·`as_of`·유효/만료/해지 replay·만료예정·민감 가림)·`creditor_store`(돈 원장 append·정정=반대기록·잔액 replay·2단계 가림·열람 로그·**로컬 백업 없음**·배분 계산은 R1 보류로 미구현). 전부 **greenfield**(기존 파일 미수정)·`registry_lock` 재사용·**config.py 미접촉**(클라이언트·인자 주입식). 게이트 `verify_{worklog,contract,creditor}_offline.py` 신규·`run_checks` 13종 초록·복잡도/건강 초록(신규 3파일 A/B).
   - 남은(2·3단계·배선): 계약 수익식 스키마 확정 후 `settlement.py` 3단계 달성률·`contract_achievement[]` 골든 · 채권자 배분 규칙(법률→소유자) 확정 후 `creditor_settlement` · **UI(H_ui) 배선**·`config` 설정키(`contract/url`·`creditor/url`·§8)·L1/핀 등재는 **통합 세션**.

**게이트/핀 계획(제안)**:
- `tools/verify_settlement_offline.py` **확장**(신규 블록 append·실 API 금지·골든 주입): 리포트 파서 불변식·계약 달성률 `contract_achievement`.
- **`tools/verify_creditor_offline.py` 신규**(제안): 채권 잔액 replay·정정=반대기록·가림(원문 비노출)·열람 로그·번호 연속. `verify_registry_offline` 패턴 복제. `run_checks` CHECKS에 1줄 등록(통합 세션·현재 10종 → 11종).
- **`tools/verify_contract_offline.py` 신규**(제안): 계약 as_of·유효/만료 replay·버전 이력 무결성.
- **핀**(통합 세션): `settlement.py`·`contract_store`·`creditor_store` 퍼사드가 pipeline/ui에 노출될 때 `pin_l1_contract` 골든 등록. 분해·배선 전 **핀 먼저**(핀이 행동을 덮는지 확인 후 추출·CODE_HEALTH_PLAN 규율).
- 규율: 새 함수 CC≤15·파일 ≤~600줄·`check_complexity` 초록·`--no-verify` 금지·되돌림은 실측 근거 메모.

---

## 11. 근거·참조
- 상위: `docs/DOMAIN_DESIGN.md §2 D8·§9 R5`·`docs/ARCHITECTURE.md`. 운영: `docs/PARALLEL_DEV.md`. 계약: `docs/L1_CONTRACT.md`.
- 1단계 SSOT: `designs/SETTLEMENT_MODULE.md`·도메인 지식 `designs/COUPANG_SETTLEMENT_DOMAIN.md`·완료 조건 `designs/coupang_golden_cases.json`.
- 원장 패턴 SSOT: `designs/LEDGER_REGISTRY.md`(재사용 원천). 화면 칸: `designs/IO_DEFINITION.md`.
- 정책/메모리: [[business-context-consignment-creditors]](채권자·법률·사업 꼬리표)·[[settlement-domain-knowledge]]·[[feature-ledger-registry]]·[[no-silent-fallback-principle]]·[[fix-from-real-evidence]]·[[code-health-regression-gate]]·[[coupang-openapi-not-available-consignment]].

SSOT = 이 문서(D8 2·3단계 + 흡수 3영역 설계) · `SETTLEMENT_MODULE.md`(1단계 계산) · `LEDGER_REGISTRY.md`(원장 패턴). **구현 착수는 소유자 지시 시.**
