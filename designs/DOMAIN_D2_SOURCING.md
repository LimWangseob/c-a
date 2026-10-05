# D2 소싱(Sourcing) 도메인 설계 (DOMAIN_D2_SOURCING)

> 작성 2026-10-05 · D2 소싱 레인(설계 단계·**구현 보류**).
> 상위 지도=`docs/DOMAIN_DESIGN.md §2 D2`·계층=`docs/ARCHITECTURE.md`·L1 계약=`docs/L1_CONTRACT.md`·입출력=`designs/IO_DEFINITION.md`·운영=`docs/PARALLEL_DEV.md`.
> ⚠ 이 문서는 **설계만** — 코드 변경·신규 모듈 생성·게이트/핀 추가는 소유자 착수 지시 후. 여기 적힌 모듈·함수·메뉴·계층변경은 전부 **제안**이다.
> 근거: `docs/DOMAIN_DESIGN.md`(D2 제안)·`docs/L1_CONTRACT.md`(rank·collector 프리미티브)·`src/coupang_analytics/kw_recommend.py`·`kw_ai.py`·`kw_volume.py`·`kw_suggest.py`·`kw_metrics.py`·`rank.py`·`product_match.py`(실측 2026-10-05)·[[naver-shopping-api-terminated]]·[[keyword-methodology-ai-anchor]].

---

## 0. 실측 요약 (설계 근거)

- **D2 소싱 = 코드 전무**(확정): `src` 전수 grep에서 `sourcing`/`소싱` 소스 파일 없음(매치 3건=`settlement_amount.py`의 margin·`input_list.py`·`product_match.py` 우연 일치, 소싱 아님).
- **재사용 기반은 완비**(아래 전부 기존 구현·실측):
  - `kw_volume.NaverAdApi` — 네이버 검색광고 키워드도구(월검색량·클릭·경쟁지수·광고깊이). **활성 API**. `related_keywords(seed)`.
  - `kw_suggest.collect_suggestions(browser, seeds, log=None)` / `fetch_suggestions(browser, prefix)` — 쿠팡 자동완성=연관검색어(비로그인 rank 세션 same-origin fetch).
  - `kw_ai.*`(OpenAI) — `analyze_product`·`generate_keywords`·`judge_keywords`(핵심/연관/탈락)·`select_keywords`·`recommend_title`·`match_products`.
  - `kw_recommend.recommend_from_title(title, naver, browser, ai_key, top_n)`·`recommend(seed, ...)`·`select_keywords_light(...)` — 후보 4소스 수집→판정→스코어→추천.
  - **`kw_metrics.page1_competition(browser, keyword) -> KeywordCompetition`** — 쿠팡 1페이지 경쟁 신호(오가닉수·광고수·로켓수·로켓비율). **경쟁강도 대안이 이미 구현됨**. rank 인프라 재사용(1요청·저부하).
  - `rank`·`collector` = **L1 조회 프리미티브**(DOMAIN_DESIGN §5.3·R4·2026-09-28 확정).
- **계층 규칙(불변)**: L2 도메인은 L0/L1만 의존·**도메인끼리 직접 import 금지**(`docs/ARCHITECTURE.md §2`). 이게 D2 설계의 가장 큰 제약(§2·§8 미결).
- **네이버쇼핑 검색 API 종료**(2026-07-31·대체 없음·[[naver-shopping-api-terminated]]) → 네이버 쪽 경쟁강도(총 상품수) 소스 소멸. 쿠팡 SERP도 **총 상품수를 노출하지 않음**(`kw_metrics.py` docstring 명시).

---

## 1. 역할·범위

### 하는 것 (D2 소싱)
- **신규 판매 상품 발굴**: 키워드/카테고리/시드에서 "팔 만한 후보"를 모은다(수요·경쟁·노출 관점).
- **시장/경쟁 분석**: 후보 키워드의 검색량(수요)·쿠팡 1페이지 경쟁 신호(로켓비율·광고수)·대략 노출난이도.
- **후보 스코어링**: 수요·경쟁·마진(사람 입력) 종합 점수로 후보 랭킹.
- **의사결정 지원**: 사람이 "소싱할지" 판단할 근거표 제시(엑셀/화면). 선택적으로 후보 결정 이력 기록(§3).
- **성격**: **읽기 전용 도메인**(쿠팡/네이버에 쓰기 없음). 저위험 → 로드맵 §8-4 (a) **1순위**.

### 안 하는 것 (경계)
- **D1 상품 분석과의 경계**: D1=**이미 등록·관리 중인 상품**의 추적 키워드 선정·순위·판매지표. D2=**아직 안 파는 신규 후보**의 발굴·판단. → 대상이 다르다(기존 상품 vs 미래 상품). **도구(키워드/순위/검색량)는 공유**하되 소유 로직은 분리.
- 상품 **등록**(D3·쓰기)·가격/재고 **변경**(D4·쓰기)은 D2 아님. D2는 "무엇을 팔지" 결정까지, 등록 실행은 D3로 넘긴다(후보→등록 연계는 백본 경유·§4).
- 원가/공급처 협상·발주는 앱 밖(사람). D2는 마진 **입력값**만 받아 스코어에 반영.

---

## 2. 재사용 기반 (L1 프리미티브 호출 — 직접 도메인 import 금지 준수)

D2가 호출할 수 있는 것은 **L1 프리미티브**뿐이다(L2 도메인 kw_* 직접 import 금지). 현재 계층 분류상:

| 필요 기능 | 현재 모듈 | 현재 계층 | D2가 바로 쓸 수 있나 |
|---|---|---|---|
| 오가닉 순위·SERP 파싱 | `rank` | **L1 프리미티브**(R4) | ✅ 가능 |
| 로그인 세션 수집(상품·재고) | `collector` | **L1 프리미티브** | ✅ 가능(단 로그인 필요·D2엔 거의 불필요) |
| 쿠팡 1P 경쟁 신호 | `kw_metrics.page1_competition` | **L2 도메인(D1)** | ⛔ 규칙상 불가(§8 미결) |
| 네이버 검색량 | `kw_volume.NaverAdApi` | **L2 도메인(D1)** | ⛔ 〃 |
| 쿠팡 자동완성(연관어) | `kw_suggest.collect_suggestions` | **L2 도메인(D1)** | ⛔ 〃 |
| AI 후보 생성·판정 | `kw_ai.*` | **L2 도메인(D1)** | ⛔ 〃 |
| 후보 수집·스코어 파이프라인 | `kw_recommend.*` | **L2 도메인(D1)** | ⛔ 〃(D1 비즈니스 로직) |

### 2.1 핵심 결정 필요 — kw 조회 프리미티브 L1 재분류 (제안·미결 M1)
위 표의 ⛔는 **D2가 신규 상품 발굴에 꼭 필요한데 규칙상 못 부르는** 모순이다. 두 길:

- **(권장·제안) rank 재분류 선례(R4) 동형 적용**: `kw_volume.NaverAdApi`·`kw_suggest`·`kw_metrics.page1_competition` 은 **"데이터를 가져오는 순수 조회 수단"**(비즈니스 로직 아님)이므로 `rank`·`collector` 와 함께 **L1 조회 프리미티브**로 재분류. 그러면 `D2→kw_volume/kw_suggest/kw_metrics` 가 "도메인→L1" 이 되어 합법. **코드 이동 없음**(rank 때처럼 문서+계약핀만).
  - 반면 `kw_ai.judge_keywords/select_keywords`(핵심/연관 판정·최종 선정)와 `kw_recommend`(선정 파이프라인)는 **D1 고유 비즈니스 로직** → L1로 올리지 않음. D2는 이들을 **직접 안 부르고**, 필요하면 §2.2처럼 **자체 스코어링**을 두거나 조립(L3)이 중재.
- **(대안) 조립 중재**: D2는 조회 프리미티브(rank)만 직접 쓰고, 키워드 발굴은 L3 조립이 kw_* 를 호출해 결과를 D2에 넘김. → 조립 비대화·D2가 반쪽. 비권장.

⚠ 이 재분류는 **계층·계약 변경**(공유 자원)이라 **통합 세션 결정사항**(PARALLEL_DEV §공유). D2 레인이 단독 확정 금지 → **M1 미결**로 소유자/통합 세션에 올림.

### 2.2 D2가 직접 소유할 로직 (D1과 구분되는 신규)
- **마진/원가 입력 반영 스코어**(D1에 없음): 수요·경쟁 + 사람 입력 원가/판매가 추정 → 기대마진·소싱 점수.
- **후보 랭킹·필터**(발굴 관점): "신규 진입 가능성"(경쟁 낮고 수요 있는 틈새) 규칙. D1의 `_keyword_score`(기존 상품 추적용 100점)와 **목적이 다름** → 재사용 않고 신규(단 네이밍·구조는 kw_recommend 패턴 따름).

---

## 3. 데이터 모델 (후보 원장 vs 일회성 조회)

D2는 읽기 전용 도메인이라 쿠팡/네이버 쓰기는 없다. 산출물 저장은 두 선택지:

| 구분 | 성격 | 저장 위치 | 권장 |
|---|---|---|---|
| **A. 일회성 조회(기본)** | 발굴·분석 1회 실행 → 표로 보고 끝 | 화면 표 + 엑셀 내보내기(workbook 패턴 재사용 or 단순 xlsx) | ✅ 1단계 기본 |
| **B. 후보 원장(선택·2단계)** | 발굴 후보·판단 이력을 쌓음(채택/보류/기각·사유) | 구글시트(R2 저장소 규칙) — `registry` append 패턴 | ⏳ 가치 검증 후 |

- **B를 둘 때 규칙**(R2·2026-10-02): ①앱(서비스계정)만 추가·사람 보기전용 ②정정은 줄+사유(append) ③저장계층 단일화 ④쓰기 PC 하나. D8 `registry_*` append 원장 패턴을 **그대로** 따른다(새 거래 도메인의 백본 표준·DOMAIN_DESIGN §5.2).
- **민감값 없음**: 소싱 후보는 공개 시장 데이터+내부 마진 추정뿐(비밀번호·계좌 없음) → 가림 불필요. 단 원가/마진은 내부 경영정보이므로 결과 공유 범위는 소유자 판단(미결 M4).
- **정체성 키**: 소싱 후보는 아직 vid/productId 없음(미등록) → **키워드+(채택 시)후보 상품명**이 임시 키. 채택→D3 등록 후 vid 부여되면 D1/D9 백본과 연결(§4).

---

## 4. 화면 매핑 (IO_DEFINITION 기준 — 신규 화면 제안)

`designs/IO_DEFINITION.md` 에 **소싱 전용 메뉴 없음**(07-6 키워드 분석은 D1 상품 분석). 메뉴 번호 체계상 01=상품·03=재고·04=정산·06=마케팅·07=분석/키워드·08=판매처·11=계약·12=채권자·13=설정이고 **02번대가 비어 있음** → 소싱을 **02-x**로 제안(상품 01 "다음 단계"로 자연스러움).

### 신규 화면 제안 (메뉴 ID)
| 메뉴 ID(제안) | 화면 | 입력/출력 | 비고 |
|---|---|---|---|
| **02-1 소싱 후보 발굴** | 시드 키워드/카테고리 입력 → 후보 표 | 입력(시드·필터) / 출력(후보 랭킹표) | 일회성 조회(모델 A) |
| **02-2 경쟁·수요 분석** | 후보/키워드별 검색량·1P 경쟁 신호 | 출력 표 | `kw_metrics`·`kw_volume` 재사용 |
| **02-3 소싱 후보 원장**(선택·2단계) | 채택/보류/기각·사유·마진 입력 | 입력(판단·마진) / 출력(원장) | 모델 B·구현 보류 |
| **02-9 소싱 설정**(선택) | 마진 기본값·밴드·스코어 가중치 | 설정 | config 키 or 13-x 편입 |

- IO_DEFINITION 표에 추가할 행(제안·구현 시 H_ui 레인이 반영): 도메인 "D2 소싱"·구분 입력/출력·메뉴 02-x. 현재 IO_DEFINITION §3 "D10 문의/CS 0(향후)"처럼 **D2도 칸 수 0(향후)**로 선등재 가능.
- UI 탭 패턴은 기존 app_qt 탭(키워드추천·순위조회)과 동형(백엔드 호출→시그널로 GUI).

---

## 5. 신규 모듈 제안 (단일책임·CC≤15·≤600줄)

DOMAIN_DESIGN §2 D2 제안(`sourcing.py`·`sourcing_store.py`)과 정합. PARALLEL_DEV에 **레인 I(소싱)** 신설 제안(편집 소유=`sourcing*`).

| 파일(제안) | 책임(단일) | 의존(아래로만) | 규모 가이드 |
|---|---|---|---|
| `sourcing.py` | 후보 발굴·수집·스코어링(일회성 조회). L1 프리미티브 호출·마진 스코어 자체 로직 | L0(browser)·L1(rank·§2.1 재분류 후 kw_volume/suggest/metrics) | ≤600줄·함수 CC≤15 |
| `sourcing_store.py`(2단계) | 후보 원장 append/replay(모델 B) | L1(gsheet_api·registry 패턴) | 〃·구현 보류 |
| `sourcing_score.py`(선택) | 소싱 점수 공식 분리(수요·경쟁·마진 가중) | 순수 함수(의존 0) | 공식만·테스트 쉬움 |

- **재사용 우선**(삭제>통합>수정>추가): 새 "후보 수집" 루프를 짜기 전에 `kw_recommend._assemble_candidates`/`recommend_from_title` 흐름을 **그대로 호출**(재분류 후). `product_match`의 이름 정규화(`_base_name` 등)는 후보 중복제거에 재사용 가능(단 밑줄=L1 누수 정리 후·§8).
- **쓰기 도메인 아님** → §5.4 쓰기 안전 규약(dry-run·승인 게이트) 불필요. 단 모델 B 원장 쓰기는 R2 단일 작성자 규칙 적용.

---

## 6. 공개 인터페이스 계약 초안 (제안 시그니처)

착수 시 `docs/L1_CONTRACT.md` 에 D2 섹션으로 핀 추가(아래는 초안·확정 아님).

```python
# sourcing.py (일회성 조회 — 읽기 전용)

@dataclass
class SourcingCandidate:
    keyword: str
    volume: int                 # 네이버 월검색량(수요)
    clicks: float               # 네이버 월평균클릭
    comp_idx: str | None        # 네이버 경쟁지수(있으면)
    organic_count: int          # 쿠팡 1P 오가닉 수(kw_metrics)
    ad_count: int               # 쿠팡 1P 광고 수
    rocket_ratio: float         # 오가닉 중 로켓 비율(판매자배송 진입 난이도)
    est_margin: float | None    # 사람 입력 원가/판매가 추정 기반 기대마진(없으면 None)
    score: float                # 소싱 종합 점수(수요·경쟁·마진)
    note: str                   # '차단됨'·'결과없음' 등

def discover_candidates(
    seed: str, naver, browser, ai_key: str | None,
    *, top_n: int | None = None, log=None,
) -> list[SourcingCandidate]:
    """시드 키워드/제목 → 후보 수집(자동완성·AI·네이버 확장) → 쿠팡 1P 경쟁 수집 → 소싱 점수 랭킹.
    AI 없으면 KeywordAIError(폴백 없음·[[no-silent-fallback-principle]])."""

def analyze_keyword(keyword: str, naver, browser) -> SourcingCandidate:
    """단일 키워드 수요·경쟁 신호만(마진/AI 없이)."""

# sourcing_score.py (순수 함수)
def sourcing_score(volume: int, rocket_ratio: float, ad_count: int,
                   est_margin: float | None) -> float: ...
```

- 반환은 **값 객체(dataclass)만**(부작용 없음). 예외는 명시(`KeywordAIError`·`RankBlocked` 전파). `log` 콜백은 기존 모듈 관례(`log=None`) 따름.
- `naver`·`browser`·`ai_key` 는 **조립(L3)이 생성·주입**(도메인은 세션 안 엶·단일 브라우저 원칙·DOMAIN_DESIGN §4.1).

---

## 7. 경쟁강도 대안 조사 (네이버쇼핑 종료 후)

네이버쇼핑 API(총 상품수) 종료로 경쟁강도 소스가 사라졌다([[naver-shopping-api-terminated]]). 대안 실현가능성·리스크:

| 대안 | 내용 | 실현가능성 | 리스크 |
|---|---|---|---|
| **① `kw_metrics.page1_competition`(이미 구현·권장)** | 쿠팡 1P 오가닉수·광고수·로켓비율 = 경쟁 "신호"(총 상품수 대용) | ✅ 높음(코드 있음·1요청·rank 피기백=추가부하 0) | 밑줄 `rank._load_results` 의존(L1 누수·§8 정리)·IP 부담은 순위 스캔과 동일 |
| **② 쿠팡 "총 상품수" 파싱** | SERP에서 총 건수 숫자 | ⛔ **쿠팡 SERP는 총 상품수를 노출 안 함**(kw_metrics docstring) → **실현 불확실**. 전수 페이지네이션 스캔으로 근사만 가능 | 다수 페이지 요청=IP 태움(순위 차단 패턴)·근사치 신뢰도 낮음 |
| **③ 네이버 Shopping Insight** | 이관 후 생존 API | ⛔ "상품 클릭 추이"만·상품수/목록/가격 없음 | 경쟁강도로 부적합 |
| **④ 로켓비율 기반 진입난이도**(①의 해석) | rocket_ratio↑=판매자배송 진입 어려움 | ✅ ①에서 파생 | 해석 규칙은 소유자 검증 필요 |

- **결론(제안)**: 경쟁강도 = **①(page1_competition) 채택**. "총 상품수"(②)는 쿠팡이 값을 안 주므로 포기하고, 1P 경쟁 신호(오가닉수·광고수·로켓비율)를 경쟁강도 지표로 삼는다. CLAUDE.md HANDOFF §4-1 "쿠팡 총상품수"(보류)는 ②에 해당 → ①로 대체 제안.
- 착수 전 `verify_rank_live`로 1P 셀렉터(광고/로켓 판별) 실측 재확인([[naver-shopping-api-terminated]] 경고).

---

## 8. 갭·리스크·미결

- **M1 kw 조회 프리미티브 L1 재분류**(최우선): §2.1. 통합 세션/소유자 결정 전엔 D2가 키워드 발굴을 합법적으로 못 함. **이 결정 없이는 D2 착수 불가**(또는 조립 중재로 반쪽).
- **M2 경쟁강도 지표 확정**: ①page1_competition 채택 제안(§7). 소유자 승인 + rocket_ratio 해석 규칙 검증 필요.
- **M3 후보 원장(모델 B) 도입 여부·시점**: 1단계=일회성 조회만, 원장은 가치 검증 후(R1 "조회 먼저" 원칙·DOMAIN_DESIGN §9).
- **M4 마진/원가 입력·내부정보 노출 범위**: 원가·기대마진은 경영정보 → 결과 공유/저장 범위 소유자 판단.
- **M5 메뉴 ID 02-x 확정**: IO_DEFINITION 편입은 H_ui 레인·통합 세션 조율(공유 문서).
- **누수**: `kw_metrics`·`kw_recommend`→`rank._load_results`(밑줄)·`product_match._base_name`(밑줄) = L1 계약 누수(L1_CONTRACT §9). 재분류 시 공개화 동반 권장.
- **라이브 미검증**: 본 설계 전부 오프라인 근거. 쿠팡 1P 셀렉터·차단 패턴은 사무실 라이브 1회 확인 필요(순위와 동일 IP 리스크).

---

## 9. 로드맵 단계·게이트/핀 계획

- **로드맵 위치**: `docs/DOMAIN_DESIGN.md §8-4 (a) D2 소싱 — 분석 재사용·읽기·저위험 = 1순위.** 선행 조건 = §8-2(경계 위반 정리·rank 재분류 완료, M1은 그 연장).
- **착수 순서(제안)**: ①M1 재분류 결정(통합 세션) → ②`sourcing.py` 스캐폴딩(일회성 조회·레인 I worktree) → ③오프라인 핀 추가 → ④사무실 라이브 1P 셀렉터 검증 → ⑤UI 02-x 탭(H_ui) → (가치 검증 후) ⑥모델 B 원장.
- **게이트/핀(오프라인·결정적·실 API 금지)**:
  - `verify_sourcing_offline.py`(신규 제안): 모킹된 네이버/쿠팡/AI 응답으로 `discover_candidates`·`sourcing_score` 가 결정적으로 돌고 스코어 랭킹이 기대순인지(경계=빈 후보·차단·마진 None). 실 API는 `VERIFY_REAL_API=1` 옵트인(기존 verify_offline 관례).
  - `pin_l1_contract.py`에 D2 공개 API(§6) 핀 1건 추가(시그니처 파괴 감시). M1 재분류 시 kw_volume/suggest/metrics 를 L1 섹션으로 이동.
  - `check_complexity.py`: `sourcing*` 신규 파일 D+(CC≥21) 경고·MI C 추락 차단(기존 게이트가 자동 적용).
  - `run_checks.py` 러너에 1줄 등록(PARALLEL_DEV 충돌 핫스팟=append 친화).
- **되돌림/정책 변경은 실측 근거 필수**([[fix-from-real-evidence]]): 경쟁강도 소스(①vs②)는 왕복 이력 위험 → ②가 안 되는 근거(쿠팡 총상품수 미노출)를 명문화해 재논쟁 차단.

---

SSOT = 이 문서(D2 소싱 상세) · `docs/DOMAIN_DESIGN.md §2 D2`(도메인 지도) · `docs/L1_CONTRACT.md`(계약) · `designs/IO_DEFINITION.md`(입출력). 구현 착수는 소유자 지시 + M1 결정 후.
