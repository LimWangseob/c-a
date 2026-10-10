# 병렬 개발 가이드 (PARALLEL_DEV)

> 목적: **1개 세션의 응답 대기시간**을 줄이기 위해 여러 Claude 세션이 **코드 편집만** 병렬로 진행한다.
> ⚠ **런타임은 병렬화하지 않는다** — 로그인/순위/이미지 브라우저(sync playwright 스레드당 1개)·단일
> 위탁계정 세션·Akamai·단일 통계 마스터/구글시트 때문에 **실행은 여전히 야간 단일 순차(①→②③)**다.
> 라이브 테스트도 **한 번에 한 세션**. (배경 분석: 2026-09-28)
>
> 🔒 **정책(고정·소유자 2026-10-06)**: **도메인별 작업은 각 도메인 전용 세션(아래 레인)에 배정해 진행한다.**
> 한 세션에 여러 도메인을 몰아서 구현하지 않는다. 통제(통합) 세션이 **공유 파일·master 병합을 직렬**로 담당하고,
> 준비된(오프라인·비겹침) 도메인을 레인 세션(worktree)에 배정→레인이 구현·게이트 초록·커밋→통제가 리뷰 후 병합.
> 선행 미결(`docs/IMPL_PLAN.md §3`) 있는 도메인(쓰기·라이브)은 해소 전 배정하지 않는다. (메모리 policy-per-domain-sessions)

## 원리
1. **격리 = worktree + 브랜치**: 세션마다 `D:\coupang-analytics`(master)가 아니라 **자기 worktree**(별도 폴더)의
   **자기 브랜치**에서 편집한다. master 직접 편집 금지. (데스크톱 앱이 세션 worktree 생성 지원)
2. **비겹침 레인 = 충돌 0**: 서로 **다른 파일 집합**만 편집하면 `git merge`가 거의 항상 깨끗하다.
3. **게이트가 통합 안전망**: 비겹침이어도 함수 시그니처 변경 등 통합 깨짐은 `tools/run_checks.py`가 잡는다.

## 도메인 세션 착수 체크리스트 (⚠ 메모리는 세션별로 분리됨)

각 worktree 세션은 **자기 폴더 경로의 별도 메모리**(`~/.claude/projects/<경로>/memory/`)를 쓴다 = 본체(`D:\coupang-analytics`)의
`MEMORY.md`·`handoff-*` 가 **자동 주입되지 않는다**(worktree 세션은 빈 메모리로 시작). 전역 정책(`~/.claude/CLAUDE.md`)과
git 추적 파일(프로젝트 `CLAUDE.md`·`designs/`·`docs/`·`docs/memory/`)은 사본으로 따라오지만 **읽어야** 맥락이 잡힌다.
그래서 세션 간 공유가 필요한 인계·맥락은 **git 문서(`docs/`·`designs/`)에 남긴다**(메모리 아님).

**도메인 세션은 착수 시 먼저:**
1. `docs/ARCHITECTURE.md`·이 파일(`docs/PARALLEL_DEV.md`)·`docs/DOMAIN_DESIGN.md`·`docs/L1_CONTRACT.md` 읽기(계층·레인·계약).
2. `docs/memory/`(본체 메모리의 git 미러)와 자기 도메인 관련 `designs/*.md` 읽기(과거 맥락·인계).
3. base 최신화: 통제 세션이 새 커밋을 올렸으면 `git merge --ff-only master`(또는 ccd_host sync_with_base_branch)로 자기 브랜치를 맞춤.
4. 게이트 준비 확인: 새 클론/worktree면 `python tools/install_hooks.py` 1회(훅은 공유 `.git` 이라 보통 1회면 충분).
5. 인계·결정은 커밋 시 `docs/`(+DECISIONS)에 남긴다 — 자기 로컬 메모리에만 쓰면 다른 세션·본체가 못 본다.

## 레인 (편집 소유 파일 — 비겹침)

| 레인 | 편집 소유 파일 | 비고 |
|---|---|---|
| **A 수집/판매** | `collector.py`·`pipeline_sales.py`·`pipeline_process.py`·`product_match.py`·`report.py` | |
| **B 키워드** | `kw_*.py`·`keyword_store.py` | |
| **C 순위** | `rank.py`·`pipeline_ranks.py` | |
| **D 이미지** | `detail_images.py`(+해당 UI 탭 로직) | 거의 고립 |
| **E 원장/정산** | `registry_*.py`(registry·_apply·_core·_gsheet·_history·_model·_rename)·`input_list.py` | |
| **F 구글시트** | `gsheet.py`·`gsheet_api.py`·`gsheet_index.py`·`gsheet_stats.py`·`pipeline_gsheet.py` | |
| **G 출력/워크북** | `workbook.py`·`workbook_common.py`·`workbook_render.py`·`workbook_index.py` | 전 모듈이 **import(읽기)**하나 **편집은 G만** |
| **H UI** | `ui/app_qt.py`·`ui/app.py`(+`ui/theme_qt.py`·`ui/*_panel_qt.py`) | 시안(Design 캔버스)=H_ui 소유 |
| **I 소싱** 🆕 | `sourcing.py`·`sourcing_store.py`·`sourcing_score.py` | D2·읽기·kw L1 재사용(구현계획=IMPL_PLAN) |
| **J 수집(ingest)** 🆕 | `ingest/*.py`(runner·store·freshness) | 배치 수집·어댑터 호출 |
| **P 어댑터** 🆕 | `platform/*.py`(base·coupang·smartstore) | ⚠browser/collector/rank 공유 접점=**통제 세션 동반** |
| **K CS** 🆕 | `cs_model.py`·`cs_store.py`·`cs_gsheet.py`·`ui/cs_panel_qt.py` | D10·1단계 수동 트래커 |
| **D3 등록** 🆕 | `register.py`·`register_validate.py`·`register_store.py` | 쓰기·§5.4·선행=쿠팡 등록 엔드포인트 캡처 |
| **D4 변경** 🆕 | `product_manage.py`·`product_change_store.py` | 쓰기·§5.4·선행=변경/삭제 엔드포인트 |

> 🆕 레인(2026-10-05·구현 착수)=`docs/IMPL_PLAN.md` 기준. E 레인은 D8 흡수 원장(`contract_store`·`worklog_store`·`creditor_store`)까지 포함(registry 패밀리 확장). 신규 모듈은 전부 **설계서(designs/DOMAIN_*·PLATFORM_INTEGRATION·SETTLEMENT_MODEL) 제안**을 따른다.

## 공유 자원 = 직렬화 (한 번에 한 세션 · 또는 통제/통합 세션)
- 코드: `config.py` · `pipeline.py`(오케스트레이션) · `browser.py` · `credstore.py` · `apppaths.py` · `appconfig.py` ·
  `session_state.py`
- 문서/정책: `CLAUDE.md` · `designs/` · `docs/DECISIONS.md` · 이 파일
- **레인이 config 값·공유 함수가 필요하면** 직접 편집하지 말고 **통제 세션에 요청**(작고 빠름) → 단일 작성자 유지.

## ⚠ 실제 충돌 핫스팟 3개 + 처리
1. **게이트/핀 파일**(`tools/verify_offline.py`·`tools/simulate_pipeline.py`·`tools/pin_*.py`·`tools/verify_gsheet_offline.py`):
   모든 레인이 회귀 핀을 여기 추가 → **최대 충돌 지점**. 처리: 핀 **함수는 파일 끝쪽에 append**(병합 친화)·러너 등록은
   **1줄**만 충돌 → 쉽게 해소. (개선 여지: 레인별 핀을 별도 파일로 두고 러너가 자동 수집)
2. **`docs/DECISIONS.md`**: 모두 append-only → 충돌 나도 양쪽 다 살리면 됨.
3. **메모리 미러**(pre-commit 훅 `docs/memory/`): append성이라 경미.

## 병합 프로토콜 (직렬)
1. 각 레인: 자기 worktree에서 `python tools/run_checks.py` **초록** + `python tools/check_complexity.py` 확인 후 push.
2. **master 병합은 직렬**(소유자 또는 지정 통합 세션이 **한 브랜치씩**): merge → 게이트 재실행 → 다음 브랜치.
   pre-push 훅이 이미 게이트를 강제하므로 안전망이 이중이다.
3. 비겹침 레인이라 대부분 fast merge. 깨지면 그 레인만 재조정(다른 레인 무영향).

## 규모·운영
- **2~3레인 동시**가 최적(대기시간 해소 vs 조율비). **7레인식 통제 관료제 불필요**.
- **통제/통합 세션은 선택**: 2~3레인이면 소유자가 병합 조율로 충분. 4레인↑·잦은 공유파일 변경이면 그때 **통합 세션 1개**
  (병합·공유파일 전담)만 둔다.
- 가장 독립적인 후보: **D(이미지)·E(원장/정산)·B(키워드)·C(순위)**. 지금 할 일 2~3개를 레인에 배정.

## 불변 규칙 (병렬이어도 유지)
- 커밋/푸시 전 게이트 초록(응급 우회 `--no-verify` 상시 금지) · 되돌림은 실측 근거 · 최소 diff · 행동 불변 분해.
- 로그인/수집/순위 **라이브 테스트는 동시 금지**(단일 브라우저·계정·시트). 개발만 병렬.

SSOT = 이 파일. 관련: `designs/CODE_HEALTH_PLAN.md`(게이트)·`CLAUDE.md`(코드 건강 규칙).
