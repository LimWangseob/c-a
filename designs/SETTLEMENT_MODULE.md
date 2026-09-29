# 설계: 정산 계산 모듈 (지급일·금액·정산 집계)

> 상태: **설계 초안(2026-09-29) · 미구현.** 이 문서는 정산 **계산** 기능의 SSOT다.
> 도메인 지식(무엇을 계산하는가)의 근거 = `designs/COUPANG_SETTLEMENT_DOMAIN.md`(SSOT).
> 완료 조건 = `designs/coupang_golden_cases.json` **100% 통과**.
> 작성=통합 세션(정석 분리: 설계는 여기, 구현은 D8_ledger 레인). 소유자 확정 사항은 "(확정)" 표기.
> 형제 문서: `designs/LEDGER_REGISTRY.md`(원장=계약금·비번·상품이력 보관, 정산이 소비).

---

## 0. 목적·범위·비범위

- **목적**: 쿠팡 정산·매출 데이터에서 **지급일**과 **금액**을 규칙대로 계산하고, 판매분석 파일을 **불변식 검증**하며 적재한다. 최종적으로 §7 운영위탁 계약 대비 달성률을 산출한다.
- **범위(이 설계)**: (1) 공휴일/영업일, (2) 지급일 6종(POLICY `PAYOUT_*`), (3) 금액 식 3종, (4) 파싱·불변식(POLICY `PARSE_COUPANG_XLSX`), (5) 골든 게이트 편입, (6) 계약 대비 정산 집계 골격.
- **비범위(별도)**: UI 표시(H_ui 레인), 실제 계약 조건 확정(계약서 수령 후·§7), 쿠팡 정산 API의 `[미확인]` 경로 확정(라이브 실측 필요).
- **D8 위치**: `docs/DOMAIN_DESIGN.md §D8`(정산/원장). 원장(`registry_*`)은 **이력 보관**, 이 모듈은 **계산**. 정산은 원장을 소비(§7).

## 1. 모듈 구성 (신규 · greenfield · D8_ledger 레인 소유)

기존 파일 수정 없이 **신규 모듈만** 추가한다(비겹침 레인 = 병합 충돌 0). 순수 계산·파싱은 전부 오프라인·결정적.

| 신규 모듈 | 책임 | POLICY | 특성 |
|---|---|---|---|
| `holiday_kr.py` | 한국 공휴일·대체공휴일 집합, 영업일 판정·가감 | `HOLIDAY_KR` | 외부 소스 조회+연 단위 캐시. 조회 실패=ERROR raise |
| `payout.py` | 지급일 6종 계산(마감일→지급일) | `PAYOUT_MP_*`·`PAYOUT_RG_*` | 순수(공휴일셋 주입)·결정적 |
| `settlement_amount.py` | 금액 식 3종(정산대상액·실지급·홈이익) | `MP_REVENUE_REPORT`·`RG_HOME_PROFIT`·RG 실지급 | 순수 산술 |
| `settlement_parse.py` | 정산·판매분석 파일 파싱, 헤더 매핑, 불변식 검증 | `PARSE_COUPANG_XLSX` | 파일 입력·silent 0 금지 |
| `settlement.py` | 위 모듈 조립: 정산건 집계·계약 대비 달성률(§7) | — | 도메인 조립(퍼사드) |

- **레인 소유(확정)**: 위 5개 신규 모듈 = **E(원장/정산) 레인 = D8_ledger worktree** 편집 소유(`docs/PARALLEL_DEV.md` §레인). registry 계열과 같은 레인.
- **공유 파일 수정은 통합 세션에만 요청**(레인 직접 금지): `config.py`(§8 설정키), `docs/L1_CONTRACT.md`+`tools/pin_l1_contract.py`(§6 계약), `tools/run_checks.py`(§5 게이트 1줄 등록).
- **live 수집은 이 설계 범위 밖(2단계)**: 정산 리포트 fetch(WING 세션·API `[미확인]`)는 L1 `collector` 확장이 필요하고 런타임 직렬이라 별도(§9). **1단계는 담당자가 내려받은 파일 적재**로 시작 → 골든 케이스 전부 오프라인 커버.

## 2. 공휴일·영업일 (`holiday_kr.py` · POLICY `HOLIDAY_KR`)

- **소스(확정)**: 하드코딩 금지. 한국천문연구원 특일정보 API(data.go.kr) **연 단위 조회 → 로컬 캐시**(`output/_holidays_{year}.json` 등) + **임시공휴일 수동 추가 경로**.
- **대체공휴일 규칙**: 국경일(삼일절·광복절·개천절·한글날)·어린이날·성탄절·부처님오신날 = 토·일 겹침 시 대체 / **설·추석 = 일요일(또는 다른 공휴일) 겹침만 대체, 토요일 겹침은 대체 없음**.
  - 실측 앵커: 2026-08-15(토)→08-17 대체 / 2026 추석 09-24~26(목~토)→09-28 영업일.
- **실패 정책(확정)**: 공휴일 소스 조회 실패 시 지급일 계산 **ERROR raise**. "0일 가정" 금지(xlsb의 "평일공휴일 수동입력 0" 결함 재현 금지 — `docs`·`no-silent-fallback-principle`).
- **공개 함수(안)**:
  - `holidays(year) -> set[date]` (캐시·API·대체공휴일 반영. 실패=raise)
  - `is_business_day(d, holidays) -> bool` (토·일·공휴일 제외)
  - `add_business_days(start, n, holidays) -> date` (start **다음** 영업일부터 n영업일 가산)
  - `next_business_day(d, holidays) -> date` (d 포함, 이후 첫 영업일)
- **테스트 주입(확정)**: 골든 케이스 `_meta.holidays_used`를 공휴일 집합으로 주입해 API 없이 검증(게이트 오프라인·`code-health-regression-gate`). 라이브만 실제 API.
- **구현 확정(2026-09-29 D8)**: `holidays(year, *, fetch=None, cache_dir, extra=())`가 **fetch 결과(대체공휴일 포함 가정)를 그대로 사용**·연 캐시·`extra`로 임시공휴일 수동 추가·실패=`HolidaySourceError`(빈 결과·조회 예외·다른 해 포함). 대체공휴일 **규칙**은 `substitute_holidays(entries)`로 **별도 제공**(광복절 토→8/17·추석 토 무대체·겹침→다음날·추석 일요일·설 토일 검증됨). ⚠**2단계에 특일정보 API 실응답을 보고** 대체공휴일을 API가 이미 주는지/`substitute_holidays`로 계산할지 확정.
- **2단계 실 소스 구현(2026-09-30 D8·`holiday_source.py`)**: 한국천문연구원 특일정보 `getRestDeInfo`(data.go.kr)를 `make_fetch(key)`로 감싸 `holidays(fetch=)` 주입. `isHoliday=='Y'`만·서비스키=credstore `__holiday_kr__`(키 미로그)·공공데이터 특이점(1건 dict·0건 ""·인증오류 XML) 처리·전 실패 `HolidayApiError`→`HolidaySourceError`(계산 중단). 검증 P5=녹화 응답 13종·실 API 미호출. **라이브 남음**: 키 발급→UI 등록(H_ui)→1회 조회 확인.

## 3. 지급일 (`payout.py` · POLICY `PAYOUT_*`)

정산 주 = 월~일. 주가 월 경계를 넘으면 **월별로 행 분할**하되 **지급일은 주 마감일(일) 기준으로 동일**(골든: `["2026-08-31","2026-08-31"]`·`["2026-09-01","2026-09-06"]` 두 행 모두 9/29).

| POLICY | 채널 | 비율 | 지급일 규칙 | 골든 앵커 |
|---|---|---|---|---|
| `PAYOUT_MP_WEEKLY_1ST` | 윙 | 70% | 주 마감일(일) + **15영업일** | 08/17~08/23 → 09/11 |
| `PAYOUT_MP_WEEKLY_FINAL` | 윙 | 30% | 매출인식월 **익익월 1일**(달력일·영업일 보정 없음) | 2025-01 → 2025-03-01(토) |
| `PAYOUT_MP_MONTHLY` | 윙 | 100% | 월 마감일 + 15영업일 | (골든 없음·규칙만) |
| `PAYOUT_RG_WEEKLY_1ST` | 로켓그로스 | 70% | 주 마감일(일) + **20영업일** | 08/24~08/30 → 09/29 |
| `PAYOUT_RG_WEEKLY_FINAL` | 로켓그로스 | 30% | 월 판매마감일 **익익월 첫 영업일** | (골든 없음·규칙만) |
| `PAYOUT_RG_MONTHLY` | 로켓그로스 | 100% | 월 마감일 + 20영업일 | (골든 없음·규칙만) |

- **알고리즘(확정, 골든 검산됨)**:
  - `_1ST`/`_MONTHLY` = `add_business_days(마감일_일요일, 15 또는 20, holidays)`. (마감일 다음 영업일부터 카운트)
  - `MP_WEEKLY_FINAL` = 매출인식월 +2개월의 **1일 그대로**(요일 무관·보정 없음). 실측 2025-03-01(토) 지급.
  - `RG_WEEKLY_FINAL` = 판매마감월 +2개월 1일의 `next_business_day`.
- **공개 함수(안)**: `payout_date(policy, *, week_end=None, revenue_month=None, holidays) -> date`. policy별 필요 인자 검증(누락=ERROR).
- **구현 확정(2026-09-29 D8)**: 주정산은 넘겨받은 `week_end`를 **그 주 일요일로 정규화**(`week_sunday(d)=d+(6−weekday)`) 후 영업일 가산. 골든의 월 경계 분할 행(`2026-08-31(월) 단독`)도 원래 주 일요일(9/6) 기준이 되어 09-01~09-06 행과 **같은 지급일**(9/29)로 수렴 — §3 "지급일은 주 마감일 기준 동일"의 코드 구현.
- **금액 반올림(확정)**: 70/30 금액은 **행 단위 반올림 후 합산**(xlsb 동작). 계산값=예측용, **실지급은 API/파일 값이 정본**(원 단위 차이 허용). → 계산 결과에 `is_estimate=True` 표기.
- **빠른정산(셀러월렛)**: 전일 구매확정분 90% 익일 — `[미확인: 수수료·조건]`. 1단계 제외.

## 4. 금액 (`settlement_amount.py`)

### 4.1 윙 매출내역 `MP_REVENUE_REPORT`
```
정산대상액 E = 매출금액 A − 판매자할인쿠폰 B(즉시+다운로드) − 판매수수료 C − 마이샵수수료 D
최종지급예정액 = E − 정산차감 F
```
- 골든: A=6,601,500 − B=2,422,100 − C=414,947 − D=0 = **E=3,764,453** = final(F=0).
- 판매수수료 C는 **쿠폰 차감 후 금액 기준**(실효율 ≈ 9.9% VAT 포함). 카테고리 요율은 **데이터에서 읽음**(하드코딩 금지) — C는 파일값 사용, 앱이 재계산하지 않음.

### 4.2 로켓그로스 실지급
```
실지급 = 판매수수료리포트.정산대상액 − 밀크런 이용액 − 광고비 − CFS 요금
```
- 밀크런·광고비·CFS는 판매수수료 리포트에 **없음** → **별도 리포트 조인 필수**(광고비/밀크런/입출고·배송요금/창고요금/재고손실보상). 조인키·리포트 API=`[미확인]`(§9). 조인 대상 누락 시 이익 과대(함정 5).

### 4.3 로켓그로스 홈 "이익"(VAT 포함)
```
이익 = 매출 − (판매자할인쿠폰 + 판매수수료 + 풀필먼트서비스비 + 광고비 + 리뷰이벤트) + 재고손실보상
마진% = round(이익 / 매출 × 100, 1)
```
- 골든: cost=1,583,840+185,391+132,844+89,732+2,220−0=**1,994,027**, 이익=3,591,960−1,994,027=**1,597,933**, 마진=**44.5%**.
- **상품원가 미포함** → 앱의 순이익 = 이 값 − 원가 − 외부비용(원가는 원장/입력, 별도 산출).
- **구현 확정(2026-09-29 D8)**: 마진% = **매출 0이면 `None`**(0%로 꾸미지 않음·정의 불가 명시)·비 0이면 사사오입 반올림(12.25→12.3·은행가 아님). 금액 입력이 정수 아니면 `TypeError`(silent 변환 금지). `mp_revenue`/`rg_payout`/`rg_home_profit` 전부 keyword-only.

## 5. 파싱·불변식 (`settlement_parse.py` · POLICY `PARSE_COUPANG_XLSX`)

- **파싱 규칙**: 판매분석 파일은 전 셀 텍스트(숫자·`"7.55%"`). 숫자 변환 실패 = **ERROR**(silent 0 금지). 옵션ID(11자리)·등록상품ID·주문번호 = **문자열 유지**(float 정밀도 손실 방지). 헤더 기반 매핑(열 위치 의존 금지)·필수 헤더 누락 = ERROR + 누락 목록 로그. 엑셀 날짜 시리얼(1899-12-30) / 문자열 날짜 둘 다 처리.
- **메타 강제(확정)**: 판매분석 파일 내부에 기간 정보 없음 → 적재 시 `period_start`/`period_end`/`account_id`를 **메타로 강제**. 메타 없는 파일 **적재 거부**.
- **불변식(검증됨)**:
  ```
  매출 = 총매출 + 총취소금액(음수)
  판매량 = 총판매수 + 총취소상품수(음수)
  구매전환율 = round(주문 ÷ 조회 × 100, 2)   (방문자 아님·views>0)
  주문(건) ≠ 판매량(개)
  ```
  - 이전 기간분 취소로 **음수 정상**(골든 판매자배송 -35000 행) → 필터링 금지.
  - 불변식 위반 행 = **WARNING + 행 로그**(쿠팡 포맷 변경 감지용·중단 아님).
- **함정 재현 금지**(명세 §7): ①70%·30% 행 동시 수집(이중집계) → **주정산은 70% 행만** ②공휴일 0일 가정 ③피벗 위치 의존 요약(집계는 쿼리로) ④미구매확정 누락(익월 중순 이후 확정·"미확정 구간" 표시) ⑤RG 부가 차감 누락.

### 5.1 실측 검증 (2026-09-29 · 실계정 판매현황 xlsx 1건 · 스크린샷 3장)
소유자 제공 실파일·화면으로 §2~§6 규칙을 실측 확인(추상 사실만 기록·실 수치/이름 제외).
- **판매현황 파일 스키마 확정**: 시트명 `vendor item metrics`(단일)·**19열 A~S**(옵션ID·옵션명·상품명·등록상품ID·카테고리·판매방식·매출·주문·판매량·방문자·조회·장바구니·구매전환율·아이템위너비율(%)·총매출·총판매수·총취소금액·총취소상품수·즉시취소상품수 = 명세 §4.1과 정확히 일치)·**전 셀 `str` 타입**(숫자·ID·`"2.90%"`·아이템위너 `"1.10000000000000008881"` 같은 float 정밀도 문자열 포함) → §5 "전 셀 텍스트·숫자변환 실패 ERROR·ID 문자열 유지·아이템위너 반올림" 필수임을 확증. 파일 내부 기간정보 없음 확인(메타 강제 근거).
- **불변식 실증**: 16 데이터행 전부 `매출=총매출+총취소` **16/16**·`판매량=총판매수+총취소상품수` **16/16**·`구매전환율=round(주문/조회×100,2)` **16/16**(방문자 아님을 실데이터로 확인·주문/조회로만 일치)·위반 0. 판매자배송 3·로켓그로스 13행. 총취소 음수·매출 0 행(이전기간 취소분) 정상 통과.
- **지급일·금액 골든의 라이브 출처 확정**: 정산현황 화면 7건(주정산 70% 5·최종액정산 30% 1·… 총 1,935,796)이 `coupang_golden_cases.json` payout_date 12케이스와 정확 일치(마감일+15영업일·MP FINAL 익익월 1일·다음 예정 2026-10-01 예상 190,079). 매출내역 화면의 정산대상액 `(A−B−C−D)=E`·최종지급 `(E−F)`이 amount_formula `MP_REVENUE_REPORT`와 일치. 로켓그로스 홈 수익현황(매출−비용 5종+재고손실보상=이익·마진%)이 `RG_HOME_PROFIT`과 일치·RG 주정산 예정(8월 5주차 70% → 2026-09-29)이 `PAYOUT_RG_WEEKLY_1ST`와 일치. → **지급일 알고리즘·금액식·파싱·불변식 전부 실측 근거 확보**(설계 1단계 착수 준비 완료).

## 6. 게이트 편입 (완료 조건)

- **신규 검증 스크립트**: `tools/verify_settlement_offline.py`(오프라인·결정적·실 API 미호출). `designs/coupang_golden_cases.json` 로드 → `_meta.holidays_used` 주입 →
  - `payout_date[]` 12케이스 → `payout.payout_date(...)` 대조(날짜 정확)
  - `amount_formula[]` 2케이스 → `settlement_amount` E·final·cost·profit·margin 대조
  - `insights_row_invariants[]` 4행 + `invariant_rules[]` 3식 → `settlement_parse` 불변식 검증(음수 행 통과)
- **러너 등록(통합 세션)**: `tools/run_checks.py` `CHECKS`에 1줄 append(형제 `verify_registry_offline.py` 옆). 전체 9종 → **10종**.
- **L1 계약**: `settlement.py` 퍼사드 공개 함수를 pipeline/ui가 부르게 되면 `docs/L1_CONTRACT.md`에 절 추가 + `tools/pin_l1_contract.py` 골든 등록(통합 세션·계약 변경은 명시적으로).
- 규율: 테스트에서 실 API 금지(`code-health-regression-gate`)·새 함수 CC≤15·파일≤~600줄.

## 7. 운영위탁 계약 대비 정산 (`settlement.py` · 계약서 수령 후 확정)

명세 §8. **원장(`registry_*`)이 계약 조건을 보관**(원장 열: 계약금 Y·비번 등), 이 모듈이 **누적 실지급 vs 목표**를 계산.

- **계약 입력(계정별·계약서 필요)**: 계약금(금액·VAT·납부일·분할·반환), 수수료(요율/정액 + 산정기준: 매출/정산대상액/실지급/순이익 택1), 약정이익금(정액/정률·월/전체·미달 시 보전/연장/소멸), 계약기간 + 귀속 기준일(결제일/구매확정일/지급일 택1), 비용 부담 주체(원가·광고·쿠폰·CFS·밀크런·반품), 분배 주기·지급일, 세금계산서 주체.
- **산출**: 계정별 **누적 실지급 vs (계약금 + 약정이익금)** 달성률·잔액·**예상 달성일**(지급 예정분 포함).
- ⚠ **소유자 확인 필요**: 계약 조건 스키마는 **실제 계약서 수령 후** 확정(지금은 입력 요구 목록만). 원장의 "계약금 Y" 외 수수료·약정이익금 열은 원장에 아직 없음 → 원장 확장 여부는 `LEDGER_REGISTRY.md` 소유와 협의.

## 8. 설정키 (통합 세션이 `config.py`/`appconfig`에 정의)

| 키(안) | 용도 | 비고 |
|---|---|---|
| `settlement/source_dir` | 정산·판매분석 파일 적재 폴더(1단계) | 담당자 다운로드 위치 |
| `settlement/holiday_source` | 공휴일 API 엔드포인트·키 | 실패=ERROR |
| `settlement/output_url` | (선택) 정산 결과 시트 | 2단계 |
- 비밀 아닌 값=`appconfig`(config.json), 비밀=credstore. 레인은 값 필요 시 통합에 요청(직접 편집 금지).

## 9. 수집 주기·런타임 경계·미확인 (`[미확인]` = 라이브 실측 필요)

### 9.0 수집 주기 (확정 · 소유자 2026-09-29)
소스측 갱신(실측): 정산현황=매일 D-1 갱신·**주 단위(월~일 마감) 확정**·지급일에 금액 확정 / 매출현황=구매확정 발생분·미구매확정은 익월 중순 확정 / 판매현황(판매분석)=매일 D-1까지.

| 데이터 | 앱 수집 주기(확정) | 실행 슬롯 |
|---|---|---|
| **판매현황(판매분석)** | **매일** (현행 유지·변경 없음) | 기존 ①판매수집 야간 18:00 배치·`vi-detail-search` API |
| **정산현황·매출현황** | **주 1회 = 주 마감 다음날(월요일)** | 야간 배치 직렬 슬롯(WING 세션 필요) |

- 근거(확정): 정산은 주 단위 확정이라 매일 볼 실익 낮음 → 확정분만·트래픽/차단 최소. 판매분석과 **주기 분리**(판매=매일·정산=주1회).
- ⚠ 정산 예상금액은 고객보상·매출회수 차감으로 **실지급과 다를 수 있음**(화면 경고=명세 "계산값=예측용·실지급=파일/API가 정본"). 주 1회 수집이 **확정(정산확정 status)** 우선.
- 미구매확정 구간(함정 4)은 익월 중순까지 미확정 → 출력에 "미확정 구간" 표시(주 1회여도 월 집계는 익월 중순 이후 안정).

### 9.1 런타임 경계

- **오프라인(아무 세션·병렬 가능)**: §2~§6 전부. 파일 적재 → 계산 → 골든 검증. **1단계 = 여기까지.**
- **라이브·직렬(런타임 병렬 금지·`docs/PARALLEL_DEV.md`)**: 정산 리포트 **자동 수집**. WING 세션 필요·`collector`(L1 공유) 확장. API 경로 `[미확인]`:
  - 윙 정산내역 = Open API `GET /v2/providers/marketplace_openapi/apis/api/v1/settlement-histories?revenueRecognitionYearMonth=YYYY-MM`(settlementType·status·finalAmount 등) — **확인됨**.
  - 윙 매출내역·로켓그로스 판매수수료 리포트·부가 리포트(밀크런·광고·CFS)·판매분석 = API `[미확인]`(화면 엑셀 다운로드로 우회 가능).
  - ⛔ 위탁계정=판매자 OpenAPI 키 발급 불가(`coupang-openapi-not-available-consignment`) → settlement-histories도 **WING 세션 경유**만 가능한지 라이브 확인 필요.
  - **실측 도구(2026-09-30 D8·`tools/diag_settlement_endpoints.py <계정ID>`)**: 사무실에서 사람이 정산 메뉴를 누르는 동안 xhr/fetch를 **관찰만**(스스로 요청 안 보냄)해 방식·경로·질의 이름·요청/응답 **구조**를 기록(금액·이름·주문번호 등 **값 비저장**·숫자ID/날짜 키도 자리표시로 마스킹·엑셀은 파일명만). 결과 `output/_diag/`. **이 결과가 나와야 collector 확장(통합 계약) 설계 가능.** 검증 P6=값 비노출.
- **미구매확정 구간(함정 4)**: 결제일 기준 월 집계는 익월 중순 이후 확정 → 화면/출력에 "미확정 구간" 표시.

## 10. 구현 단계 (D8_ledger 레인 인계)

정석 분리: 아래를 **D8_ledger worktree**에서 구현, 각 단계 `python tools/run_checks.py` 초록 유지·작게 커밋·push → **통합이 직렬 병합**.

- **1단계(오프라인·골든 100%)**: `holiday_kr`(테스트 주입) → `payout` → `settlement_amount` → `settlement_parse` → `tools/verify_settlement_offline.py` 작성 → 통합에 게이트 1줄 등록 요청. **완료 판정 = 골든 전 케이스 통과.**
- **2단계(라이브 수집)**: 공휴일 실 API 연동 → 정산 리포트 수집(collector 확장=통합 계약 추가) → 부가 리포트 조인. 런타임 직렬·사무실 실측.
- **3단계(계약 대비 정산)**: 계약서 수령 후 §7 스키마 확정 → 원장 확장(협의) → `settlement.py` 달성률 산출 → H_ui 표시(UI 레인).

## 11. 근거·참조

- 도메인 지식 SSOT: `designs/COUPANG_SETTLEMENT_DOMAIN.md`. 완료 조건: `designs/coupang_golden_cases.json`.
- 상위: `docs/DOMAIN_DESIGN.md §D8`·`docs/ARCHITECTURE.md`. 운영: `docs/PARALLEL_DEV.md`. 계약: `docs/L1_CONTRACT.md`.
- 형제: `designs/LEDGER_REGISTRY.md`(원장). 정책: `docs/DECISIONS.md`(2026-09-29 정산 도메인 아카이브)·메모리 `settlement-domain-knowledge`.
- 규율: `no-silent-fallback-principle`(폴백 금지·실패 raise)·`code-health-regression-gate`(게이트·실 API 금지·CC/파일 상한)·`fix-from-real-evidence`.

---

## 12. D8_ledger 레인 인계 브리핑 (2026-09-29 · 통합 세션 → D8 레인)

> D8_ledger worktree(`D:\ca-worktree\D8_ledger`·브랜치 `domain/d8-ledger`)에서 새 세션을 열어 **1단계**를 구현한다.
> 이 문서가 구현 SSOT. 아래 순서대로 하면 된다. **설계 변경 아님 — 설계대로 코드만 작성.**

### 시작 절차
1. **설계 확보(로컬)**: worktree는 로컬 `.git`을 공유하므로 push 없이 master의 설계를 가져온다:
   ```
   cd D:\ca-worktree\D8_ledger
   git merge master          # SETTLEMENT_MODULE.md·COUPANG_SETTLEMENT_DOMAIN.md·golden json 확보(비겹침=클린)
   python tools/install_hooks.py   # 새 클론/worktree면 1회
   ```
2. **읽기**: `designs/SETTLEMENT_MODULE.md`(이 문서 전체)·`designs/COUPANG_SETTLEMENT_DOMAIN.md`(도메인 지식)·`designs/coupang_golden_cases.json`(완료 조건)·`docs/PARALLEL_DEV.md`(레인 규칙)·`docs/L1_CONTRACT.md`(계약).
3. **베이스라인 초록 확인**: `python tools/run_checks.py`.

### 구현 순서 (1단계 = 오프라인·골든 100%)
각 모듈 완성마다 **게이트 초록 유지·작게 자주 커밋**. 순서:
1. `holiday_kr.py` — §2. 함수 `holidays/is_business_day/add_business_days/next_business_day`. **테스트는 골든 `_meta.holidays_used` 주입**(실 API 금지). 대체공휴일 규칙(설·추석 토요일 겹침 대체 없음) 주의.
2. `payout.py` — §3. `payout_date(policy, *, week_end, revenue_month, holidays)`. 골든 payout_date 12케이스가 정답(마감일+15/20영업일·MP FINAL 익익월 1일 무보정). `is_estimate` 표기.
3. `settlement_amount.py` — §4. 윙 E=A−B−C−D·final=E−F / RG 실지급 / RG 홈이익·마진%. 골든 amount_formula 2케이스.
4. `settlement_parse.py` — §5. 헤더 기반 매핑·전 셀 str·숫자변환 실패 ERROR·ID 문자열 유지·불변식 검증(§5.1 실측: 19열 `vendor item metrics`·불변식 16/16). 메타(period/account) 강제.
5. `tools/verify_settlement_offline.py` — §6. golden json 로드 → payout/amount/invariant 3영역 대조. **결정적·실 API 미호출.**
6. **완료 판정 = 골든 전 케이스 통과.** 이후 통합에 §아래 "통합 요청" 전달.

### ⛔ 레인 경계 (직접 편집 금지 — 통합 세션에 요청)
공유 파일이라 D8 레인이 **직접 못 고친다**. 아래는 **통합 세션에 요청**(작고 빠름):
- `tools/run_checks.py` `CHECKS`에 `verify_settlement_offline.py` **1줄 등록**(9→10종).
- `config.py`/`appconfig` **설정키**(§8: `settlement/source_dir` 등).
- `docs/L1_CONTRACT.md` + `tools/pin_l1_contract.py` **계약 등록**(settlement.py 퍼사드를 pipeline/ui가 부르게 될 때만·1단계엔 불필요).
- `pipeline.py`·`collector.py` 배선(2단계 라이브 수집 때).

### 규율 (게이트가 강제)
- 새 함수 **CC ≤ 15**·파일 **≤ ~600줄**·`check_complexity.py` 초록.
- **테스트에 실 API 금지**(공휴일·정산 API 미호출·골든 주입만).
- **silent 폴백 금지**(변환 실패·소스 실패 = ERROR raise, `no-silent-fallback-principle`).
- 응급 우회(`--no-verify`) 금지.

### 병합
- 1단계 완료 후 `run_checks`(가능하면 10종)+`check_complexity` 초록 → `domain/d8-ledger` push → **통합이 직렬 병합**(master merge → 게이트 재실행). 신규 모듈이라 충돌 없음.

### 범위 밖 (D8 레인 하지 말 것)
- 2단계 라이브 수집·3단계 계약 정산(별도)·UI(H_ui 레인)·공유 파일 직접 편집.
