"""전역 상수·정책값 (SSOT: designs/DESIGN.md)."""
from __future__ import annotations

# ── 셀독 출력 서식(신규) — 시트=사업자, 상품블록(계약/개인)+키워드 노출순위, 일자 가로 ──
SELDOC_SHEET_TITLE = "셀독 상품 데이터"       # 워크북 A1 제목
M_SALES = "판매량"        # 계약(로켓그로스) 상품 일자별 판매량
M_VISITORS = "방문자"     # 계약 방문자수
M_VIEWS = "노출량"        # 계약 노출량(조회수)
M_INVENTORY = "재고현황"   # 계약 판매가능 재고수량(로켓그로스, rfm-inventory)
M_TOTAL_SALES = "전체 판매량"  # 개인(판매자배송) 상품 판매량
M_TOTAL_VIEWS = "전체 노출량"  # 개인 노출량
M_RANK = "노출 순위"      # 키워드별 오가닉 순위(PC)
CONTRACT_METRICS = (M_SALES, M_VISITORS, M_VIEWS, M_INVENTORY)  # 계약=로켓그로스
PERSONAL_METRICS = (M_TOTAL_SALES, M_TOTAL_VIEWS)               # 개인=판매자배송
KIND_CONTRACT = "계약 상품"
KIND_PERSONAL = "개인 상품"

# 모바일 노출순위 포함 여부 — 기본 제외(요청). rank._set_mobile/organic_ranks(mobile=) 모듈은 보존(재사용).
RANK_INCLUDE_MOBILE = False

# (구 서식 지표 상수 제거 — 셀독 새 서식은 위 SELDOC_*/M_*/CONTRACT·PERSONAL_METRICS 사용)
RANK_GOOD_THRESHOLD = 20      # 이 순위 이내면 '양호'(상위 노출), 밖이면 마케팅 필요(diagnose_exposure)

# ── 검색 순위 추적 정책 ─────────────────────────────────────────
RANK_SCAN_MAX = 50           # 오가닉 50위까지 탐색(속도). 밖이면 '{RANK_SCAN_MAX}위 밖'(미노출 아님 — 뒤쪽 순위)
RANK_PAGE_DELAY_MIN = 1.0     # 페이지 간 최소 지연(초) — 순차(폴백) 방식에서만. 병렬 fetch는 지연 없음
RANK_PAGE_DELAY_MAX = 2.5     # 페이지 간 최대 지연(초)
# 병렬 fetch 순위조회(기본) — 검색 1회 네비로 Akamai 프라임 후 여러 키워드를 same-origin fetch로 동시에 받아
# 렌더 없이 파싱(실측: 프라임 후 3키워드 병렬 ~1.3초, 현행 네비 15초/키워드 대비 대폭 가속).
RANK_ORGANIC_PER_PAGE = 60   # 검색 1페이지 상품수(실측 60) → 스캔 50은 1페이지로 충분(페이지네이션 불필요)
RANK_FETCH_CONCURRENCY = 2   # 병렬 fetch 동시 개수 상한(버스트=봇신호 → 2로 낮춰 차단 회피, 여전히 충분히 빠름)
RANK_FETCH_JITTER_MS = 800   # 각 fetch 전 무작위 지연 상한(ms) — 사람처럼 간격 두어 차단 회피(버스트 완화)
# 차단(Akamai) 감지 시: 즉시 공란 대신 잠시 쉬었다가 재시도한다(플래그가 수십 초~분 내 완화되는 특성 활용).
RANK_BLOCK_BACKOFF_SEC = 30  # 차단 감지 후 재시도까지 대기(초)
RANK_BLOCK_RETRIES = 1       # 차단 시 백오프 후 재시도 횟수(0이면 즉시 공란)


# ── 키워드 추천 정책 (황금키워드) ───────────────────────────────
KW_MIN_VOLUME = 500        # '키워드 추천' 탭 전용 하한(밴드 하한). 배치 추적엔 KW_TRACK_MIN_VOLUME 사용
KW_MAX_VOLUME = 50000      # 상한 — '키워드 추천' 탭 전용(추적 선정에는 미적용)
KW_TRACK_MIN_VOLUME = 30   # 배치 추적 하한 — 저경쟁 롱테일(월검색량 수십)이 오히려 노릴 값이라 낮게. 0~극소량만 제외
KW_GEN_N = 40              # AI가 조합 생성할 고객검색어 후보 수(핵심×속성×형태×장소×용도)
KW_EXPAND2_N = 6           # 네이버 2단계 확장: 1차 후보 중 검색량 상위 몇 개를 재시드로 다시 연관조회할지(요청 폭주 방지 상한)
KW_CANDIDATE_LIMIT = 15    # 쿠팡 1P 경쟁까지 수집할 후보 수 (요청 수 제한)
KW_TOP_N = 8               # 추천 상위 개수 (사용자가 이 중 3~5개 확정)
KW_TRACK_N = 4             # 첫날(새 통계) 상품당 자동 추적할 키워드 수(AI 최종선정 개수)

# ── 통계 유지(cross-day) — 키워드 동결 + 상한 내 발굴 추가 ──────
# 한번 통계를 시작하면 키워드를 종료까지 동결(시계열 의미 유지). 기존 키워드는 어떤 경우도 제거하지 않는다.
KW_MAX_TRACK = 7           # 통계 유지 중 상품당 추적 키워드 상한(첫날 KW_TRACK_N, 이후 이만큼까지만 발굴 추가)
KW_ADD_PER_DAY = 2         # '새 키워드 발굴 추가' 켠 날, 상품당 하루 최대 추가 개수(상한 KW_MAX_TRACK 초과 금지)

# ── Keyword Score(페이즈 B — 선정 지능화) ──────────────────────
# 후보를 부분점수(노출 제외)로 압축 → 압축분만 쿠팡 실노출 측정 → 전체 100점·등급 → AI가 종합해 최종선정.
KW_SCORE_POOL_N = 6        # 부분점수 상위 몇 개만 쿠팡 실노출 측정(요청량·IP차단 제어, 6~7 권장)
KW_SCORE_W_RELEVANCE = 35  # 관련성: AI 핵심/연관 판정(핵심=만점, 연관=55%)
KW_SCORE_W_INTENT = 25     # 구매의도: 월클릭수(로그)72% + 롱테일성(키워드 길이)28%
KW_SCORE_W_VOLUME = 20     # 검색량: log10(월검색량) 정규화
KW_SCORE_W_EXPOSURE = 15   # 쿠팡 실노출: 오가닉 최상위 순위(1~3=만점, 미노출=0)
KW_SCORE_W_TREND = 5       # 추세: 네이버 검색광고가 시계열 미제공 → 데이터 소스 확보 전까지 0점(만점 95 운영)
KW_GRADE_A = 72            # 이 점수 이상 A(총점 95 만점 기준)
KW_GRADE_B = 54            # B
KW_GRADE_C = 36            # C, 미만 D

KW_W_VOLUME = 1.0          # 검색량 가중(클수록 좋음)
KW_W_ROCKET = 1.5          # 로켓비율 패널티(높을수록 판매자배송 진입 어려움)
KW_W_AD = 0.5              # 광고수 패널티(경쟁 과열)
KW_QUERY_DELAY_MIN = 1.5   # 키워드 간 쿠팡 조회 지연 — 속도 위해 축소
KW_QUERY_DELAY_MAX = 3.0

# ── AI 키워드 (OpenAI ChatGPT) — 앵커 추출 + 관련성·쇼핑성 판정 ──
KW_AI_MODEL = "gpt-4o"         # 키워드 AI 전 단계 공통. 설정 탭에서 변경 가능(mini는 judge 속도 이득 없어 미사용)
KW_AI_ANCHOR_N = 4              # 제목에서 뽑을 핵심 앵커 최대 개수(다중 허용)
KW_JUDGE_BATCH = 20            # 판정 1회 최대 후보 수 — 작게 나눠 **배치 병렬**로 처리(judge 30s→~10s)

# ── 세션 유지(킵얼라이브) ──────────────────────────────────────
SESSION_KEEPALIVE_MIN = 25   # 이 분마다 로그인된 세션을 살려둠(재로그인·2차인증 빈도↓). 로그인 아님

# ── 출력 파일 ──────────────────────────────────────────────────
OUTPUT_FILE_PREFIX = "쿠팡데이타분석"   # {prefix}_통계.xlsx / _통계_yymmdd.xlsx(스냅샷)

# ── 입력 분석용 엑셀 헤더 (필수) ────────────────────────────────
IN_COL_REPRESENTATIVE = "대표자명"
IN_COL_BUSINESS = "사업자명"
IN_COL_ACCOUNT_ID = "계정아이디"
IN_COL_PRODUCT = "상품명"
# 선택 컬럼. 옵션별 추적: '옵션' 행마다 옵션명 + vendorItemId. 한 옵션에 vid 여러 개면 콤마 구분.
IN_ALIASES_OPTION = ("옵션", "옵션명", "option")
IN_ALIASES_VENDOR_ITEM_ID = ("vendoritemid", "vendoritemids", "벤더아이템id", "옵션id")
IN_ALIASES_PRODUCT_ID = ("productid", "productids", "상품id")

# ── 상품별 판매 리포트 헤더 (필수 매칭 대상) ────────────────────
RP_COL_PRODUCT = "상품명"
RP_COL_ITEM_ID = "등록상품ID"
RP_COL_OPTION_ID = "옵션 ID"
RP_COL_VIEWS = "조회"        # → 노출건수
RP_COL_SALES = "판매량"      # → 판매건수
RP_COL_VISITORS = "방문자"   # → 방문자건수
