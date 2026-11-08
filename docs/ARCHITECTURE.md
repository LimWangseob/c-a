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
      session_state·gsheet_api·gsheet
L1 데이터 백본(공통): 조회 프리미티브(collector·rank ← 2026-09-28·§DOMAIN_DESIGN 5.3 · kw_volume·kw_suggest·kw_metrics ← 2026-10-05 U2 편입)·출력저장(workbook*)·입력/원장(input_list·registry_*)·시트동기(gsheet_index·gsheet_stats·pipeline_gsheet)
L2 도메인(개별·병렬 개발 단위):
     · 상품분석(키워드·노출): kw_ai·kw_recommend·keyword_store·product_match·report  (rank·collector·kw_volume·kw_suggest·kw_metrics=L1 조회 프리미티브·호출)
     · 이미지: detail_images
     · 정산/원장: registry_* 상위·input_list 역기록
     · (신규) 소싱 · 등록 · 주문 : 아직 없음 → L0/L1 위에 새 모듈로 추가
L3 조립·표현: pipeline(+_sales/_ranks/_process/_paths/_gsheet) · ui/app_qt·ui/app
```

**의존 방향 규칙(재사용·융합의 핵심)**: L2 도메인은 **아래(L0/L1)로만** 의존. **도메인끼리 직접 import 금지** —
융합은 **데이터 백본(workbook/registry/gsheet) 또는 정의된 인터페이스** 경유. 이래야 도메인 추가·교체가 서로를 안 깬다.

> **멀티플랫폼 확장(소유자 2026-10-05·설계만·구현 보류)**: 커머스 판로 = 멀티플랫폼 통합앱(v1 쿠팡+스마트스토어). **플랫폼 어댑터**(공통 인터페이스·플랫폼 중립 DTO·capabilities)를 **L1 공유 파사드**로 둔다(도메인 아님 — 여러 도메인이 공유). 쿠팡 어댑터=기존 browser(L0)+collector/rank(L1) 얇은 파사드, 스마트스토어 어댑터=네이버 커머스 API(접근성 미확인). **배치 수집 레이어**(ingest)가 판매·정산·문의를 당겨 백본에 저장→도메인은 수집본 조회. 쓰기(상품 CRUD·CS 답변)는 §DOMAIN_DESIGN 5.4 규약. SSOT=`designs/PLATFORM_INTEGRATION.md`·`designs/PROCESS_OVERVIEW.md`·`designs/SETTLEMENT_MODEL.md`.

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

## 아키텍처 (핵심 모듈)
> 📦 2026-11-05 `CLAUDE.md` 에서 **원문 그대로** 옮김(D-151·대조표=`docs/decisions/claudemd-move-2026-11-05.md`). ⛔세션에 자동으로 안 읽힘 — 해당 작업 전에 직접 읽는다. 상시 규칙 한 줄 요약은 `CLAUDE.md` '상시 규칙' 절. 결정이 어긋나면 `docs/DECISIONS.md` 가 기준(뒤 항목 우선)이고, 어긋남은 작업 전에 보고한다.

- `src/coupang_analytics/browser.py` — **실제 Chrome + CDP** 제어(`WingBrowser`). Akamai 봇탐지 통과 핵심.
- `pipeline.py` — `run_full`=①판매수집(계정마다 로그인→판매분석발견·지표, 통합엑셀 1개 누적+**계정마다 중간저장**, 한 계정 실패해도 다음 진행·키워드/순위 없음). **재부팅 복구**: `write_run_stage`/`read_run_stage`가 `_실행단계.json`에 오늘 단계(sales=①완료·ranks=②완료·done) 기록 → 앱 `--resume`(로그온 트리거)가 이 마커+`resumable_progress`(①진행중)로 **판매수집 건너뛰고 순위부터** 이어서(중단분 없으면 즉시 종료). **전체실행은 단계별**: `run_full(sales_semi)`[①판매] → `select_keywords_stage(grow)`[②] → `track_ranks_stage`[③반자동] — 조립은 전체실행·`--auto`·`--resume` 공통 **`pipeline_stages.run_stages`**(D-024) (인라인 키워드·순위·자동 순위 분기는 D-022 B5 삭제)(§현재 상태). 종료 시 `push_ledger_inventory`(그로스 재고 역기록)·`_push_gsheet`(구글시트). **매일 통계(cross-day)**: `carry_forward=True`면 단일 마스터(`쿠팡데이타분석_통계.xlsx`)를 이어써 **키워드 동결+날짜 컬럼 누적**, ② `select_keywords_stage(grow=True)`면 상한(`KW_MAX_TRACK=10`)·하루(`KW_ADD_PER_DAY=2`) 내 새 키워드만 발굴(기존 제거 안 함). `resume`·`redo_today`=실행모드. **날짜 컬럼(2026-09-16 확정)**: 라벨=**작업 실행날짜**(`run_full(date_label=)`, `_run_dates()`가 D-1판매조회와 분리 반환)·형식=**년도 없는 '월.일'**(예 09.16, 당분간·`%m.%d`), 순위=실행날짜·판매=전일(D-1) 데이터를 **같은 컬럼**에. 새벽 넘겨도 진행중 파일의 `date_label`로 시작일 기준 고정. **미실행/중단 날짜=날짜만 표기·값 공란**(`workbook.normalize_date_columns`+`ensure_date` 갭필로 시트별 첫날~마지막일 연속 유지·`apply_style`마다 멱등). 과거 D-1 라벨은 재라벨 안 함(앞으로만·경계에 빈 하루 정상). SSOT=`designs/DESIGN.md §일자 컬럼`.
- `input_list.py` — 입력 파싱(`parse_input_list`/`parse_input_rows`, 구글대장 `read_ledger_rows`, 비번 `parse_password_file`) + **그로스 재고 역기록**(`write_ledger_inventory`: 관리대장 AD열에 재고 씀, 매칭 = ① AI 매칭 결과 `output/_매칭결과.json` — 현행 = `docs/CURRENT_RULES.md` §5 · D-047·D-048 · 옛 유사도 `_best_inventory_match` 삭제).
- `collector.py`(판매분석 **데이터 API 직접조회** `fetch_sales_details`=`vi-detail-search` POST 주경로, `x-xsrf-token` 필요; 실패 시 엑셀 다운로드 폴백) · `report.py`(엑셀 폴백 파서 `parse_by_option` + `OptionMetric`) · `workbook.py`(통합 출력·등록상품명 보존·재고매칭 공급).
- `detail_images.py` — **상세페이지 이미지 추출(A안 CDP attach·ad-hoc)**: 앱이 브라우저를 안 띄우고, 사용자가 디버그포트(9222)로 띄운 **자기 warm·로그인 Chrome에 `extract_via_cdp`로 붙어**(connect_over_cdp) 현재 상품 탭 DOM만 읽어 **대표/갤러리+상세설명 이미지만** 저장(pw.stop()=연결만 해제·Chrome 유지). ⚠추천/리뷰도 같은 `vendor_inventory` URL이라 **DOM 컨테이너 스코핑**(상세=`.product-detail-content,.vendor-item`·대표=`div.product-image`)이 정밀도 핵심. 순수 로직 `extract_from_page(page,…)`. ⛔새 프로필로 코팡 접근=사무실 IP Akamai Access Denied(그래서 사용자 세션에 붙는 A안). SSOT=`designs/DESIGN.md §5.3`.
- `rank.py`(비로그인 오가닉 순위) · `kw_*`(키워드: AI 앵커·판정·선정=**OpenAI ChatGPT** + 네이버 검색광고 API 검색량 + 쿠팡 자동완성 `kw_suggest`; ⛔`kw_shopping.py`=네이버쇼핑 API 종료로 죽은 엔드포인트) · `human_typing/human_mouse`(사람같은 입력) · `credstore.py`(DPAPI 암호화).
- **노출순위 프록시**(비로그인 공개검색 전부 — ③순위·② 자동완성·키워드/순위 탭 D-031 · config.json `proxy/enabled` 키 없으면 ON D-034): `proxy_manager.py`(스레드세이프 풀·URL 정규화·로드/중복제거) · `proxy_pool.py`(`rank_proxy_or_skip`=fail-closed, OFF=None·오류=순위 스킵·직접연결 안 함 · `pick_rank_proxy`=egress 회전선택) · `proxy_blocklist.py`(차단 egress IP 목록·72h TTL·`resolve_egress_ip` 브라우저 IP에코) · `pipeline_ranks.drive_rank`(순위 브라우저 수명+egress 회전+차단이력 선제skip·신호 `_RANK_HALT["rotate"]`) · `config.apply_proxy_override`/`apply_rank_images_override`(config.json `proxy/*`·`rank/block_images` 런타임 토글) · `browser.WingBrowser(proxy=,block_images=)`(`--proxy-server`+CDP Fetch 인증 source=="Proxy"만·`--blink-settings=imagesEnabled=false`). URL=`proxies.txt`(gitignore·sessid 여러 줄=고정 sticky IP 풀).
- **구글 시트 통합**(입력=관리대장 구글시트·출력=결과 구글시트, SSOT=`designs/GSHEET_UNIFIED.md`): `gsheet_api.py`(서비스계정 Sheets API v4 클라이언트 `GSheetClient` read/write/`ensure_sheet(s)`/`batch_update`/`read_grid`, SA키=credstore `__gsheet_sa__`·DPAPI, 403/404/429 한국어) · `gsheet.py`(URL→시트ID 파싱만·공개 export 는 E2 에서 삭제) · `input_list`에 `read_ledger_rows`/`parse_input_rows`(관리대장 직접 파싱, **삭제/판매중지=취소선(`read_strike_grid`로 Sheets API 취소선 조회) 또는 대장 '상태' 컬럼** — 파일 경로와 동일 OR 판정) · `gsheet_index.py`(결과 **`계정목록`**(공백 없음) 증분 동기화 `sync_index`·`plan_sync`: **자동열 A(대표자)·B(사업자)·C(계정ID)·D(상품)·E(상태)·F(회사보유재고)·G(그로스재고)·H(체험단 시작일)·I(체험단효과)**(D-106·D-109 9열·직원 입력 열 없음) — ⚠**항목④(2026-09-26): 계정ID를 상품 왼쪽(C)으로 스왑**·밴드는 사업자명 기준(다계정ID=한 밴드)·셀폭 내용길이 자동맞춤·신규는 계정그룹 끝 insertDimension·안정키=B열(사업자) note(계정ID+등록명)·옛 시트 자동 마이그레이션: `_ensure_rep_column`(7→8열 대표자 삽입)+`_ensure_column_order`(옛 상품C·계정ID D → moveDimension으로 계정ID를 C로); **계정 삭제(2026-09-17)**: 관리대장에서 **줄이 사라진 계정=완전 삭제**(`delete_accounts`가 계정목록 행+통계 시트 제거·워크북은 `delete_account`), 대장에 **판매중지로 남은 건 유지+경고**(줄 존재 판정=`InputList.ledger_account_ids`); **마케팅 역머지** `read_marketing`(헤더기반 열탐지)/`apply_marketing`; `roster_from_workbook`) · `gsheet_stats.py`(사업자별 **통계 시트 = openpyxl 마스터 미러링**: `worksheet_to_requests`로 각 시트를 batchUpdate 번역·**전체 교체**, `push_statistics`; **직원 입력 키워드 역머지** `read_staff_keywords`/`merge_staff_keywords`). 파이프라인 `run_full(gsheet_output_url=)` → 시작 시 `_pull_gsheet_keywords`(직원 키워드 역머지), 최종 저장 직후 `_push_gsheet`(통계 미러링 + 계정목록 동기화). **①②③ 개별 실행도 모두 반영**(`select_keywords_stage`·`track_ranks_stage`도 `gsheet_output_url=` 받아 저장 후 `_push_gsheet`). **그로스 재고 역기록**=`push_ledger_inventory`가 입력 관리대장 AD열에 씀(입력 URL=`gsheet/input_url`). gsheet 실패는 로그로 명시·xlsx는 보존·비치명적. UI는 `gsheet/output_url`(app_qt=QSettings·config.json) 전달.
- `ui/app_qt.py` — **PySide6(Qt) GUI + Windows 11 Fluent 스타일(QSS)** — 기본 UI(설정/키워드추천/순위조회/**상세이미지**/전체실행 탭). "상세 이미지" 탭=CDP attach 이미지 추출([쿠팡용 크롬 실행]=디버그포트 전용 영속 프로필 `data/chrome-images`→사용자가 그 Chrome서 로그인·상품 열기→[이미지 추출]=run_bg로 CDP attach→탐색→추출→폴더 열기). 설정 탭 "구글 시트 연동" 카드(SA키·입출력 링크·연결확인·관리대장에서 불러오기·**기본 입력 소스 라디오**=구글시트(기본)/PC엑셀(선택), QSettings `input/source`; 무인 자동로드 `_auto_load_input`가 이 값을 따름, **구글 대장 실패=오류·실행 중단·PC 엑셀 폴백 없음 D-134**)·**💾 설정값 저장 버튼**(명시 저장). 백엔드 로직은 그대로 호출, 로그/완료는 시그널로 GUI 스레드 전달.
