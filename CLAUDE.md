# coupang-analytics

> ⛔**불변 정책 — 모든 도메인·세션·worktree·향후 세션에 영구 적용**(소유자 2026-10-07·08·session-kit 전역 일원화):
> ①**메모리(MEMORY.md 색인) 30~50줄**·초과분 CLAUDE.md 이관. ②**CLAUDE.md 200줄 미만**·초과 시 색인만+상세 별도 파일.
> ③**핸드오프 = `STATE.md` 한 곳**(repo 루트·100줄 이하·세션마다 전체 덮어쓰기·새 handoff 문서 난립 금지). ④**DECISIONS =
> `docs/DECISIONS.md` D-번호 블록·추가 전용**(기존 수정·삭제 금지·뒤집으면 새 항목+`SUPERSEDED by D-xxx`·대체 없는 폐기는 `RETIRED by D-xxx`·전환 전 한 줄은 `docs/decisions/` 동결 아카이브).
> ⑤**세션 시작** = STATE.md+`docs/DECISIONS_INDEX.md`(자동 생성·직접 수정 금지) 읽고 `git log/status` 대조 3줄 요약 후 착수. DECISIONS.md 전체는 읽지 않고 작업 관련 D번호·태그 원문만 읽으며 현재 코드와 어긋나면 작업 전에 보고. ⑥**세션 종료 = `/session-close`**·커밋 =
> `[R{n}] 요약`. 되돌림·완화 금지. 전역 SSOT = `~/.claude/CLAUDE.md` "결정 기록·핸드오프·세션 종료" 절.

관리 쿠팡 판매자 계정들의 **상품별×일자별** 지표(노출순위·노출건수·판매건수·방문자)를 수집해
통합 엑셀(`쿠팡데이타분석_yymmdd_시분초.xlsx`)을 생성하는 **Windows 데스크톱 GUI(.exe, PyInstaller)**.

## 실행
```
cd D:\coupang-analytics
python ui/app_qt.py     # 기본 UI = PySide6(Qt) + Windows 11 Fluent 스타일
```
설계 SSOT: `designs/DESIGN.md`, `designs/KEYWORD_SELECTION.md`, `designs/GSHEET_UNIFIED.md`, `designs/IO_DEFINITION.md`(입출력 정의서 v1 — 파일 칸↔화면 칸 1:1·128칸·구현 시 기준·2026-10-05).

## 문서 지도 (⛔자동으로 안 읽힘 — 해당 작업 전에 먼저 읽는다)
> 20KB 상한(소유자 2026-11-05)에 맞춰 상세를 원문 그대로 옮겼다(삭제 0·D-151·대조표=`docs/decisions/claudemd-move-2026-11-05.md`). 다른 문서의 "CLAUDE.md 제약·함정·운영 정책·현재 상태" 참조 = 아래 문서.

| 작업 | 먼저 읽을 문서 |
|---|---|
| 로그인·브라우저·비밀번호·지문·프록시·순위 정책 | `docs/CONSTRAINTS.md` + `docs/PITFALLS.md` |
| 경로·폴더·배포·zip·Defender·콘솔창 | `docs/PITFALLS.md` 8~10번 |
| 모듈 구조·파이프라인·구글 시트 구현·날짜 컬럼 | `docs/ARCHITECTURE.md` '아키텍처 (핵심 모듈)' 절 |
| 대장 읽기·매칭·재고·키워드·순위 운영·체험단·통합판매현황·정산 기동·날짜 지정·재부팅 복구·검증도구 | `docs/OPERATIONS_POLICY.md` |
| 언제·왜 바뀌었나(~2026-10-27 경위·동결) | `docs/STATUS_HISTORY.md` |

- **기록 위치**: 진행 상황 = `STATE.md`·결정 = `docs/DECISIONS.md` — ⛔이 파일에 '현재 상태' 줄을 다시 쌓지 말 것. 새 상시 정책 = `docs/OPERATIONS_POLICY.md`(또는 `docs/CONSTRAINTS.md`)에 적고, 모든 작업에 적용되는 것만 아래에 한 줄.
- **크기**: 이 파일 200줄 미만·20KB 미만. 넘으면 이동만 허용(대조표로 유실 0 확인).

## 상시 규칙 (한 줄 요약 — 원문·예외는 위 문서)
**계정·보안**
- ⛔로그인 = **실제 Chrome + CDP 자동입력만**. HTTP 폼-POST 위장 로그인 도입 금지(변경 금지). 완료 판정 = 윙 대시보드 URL **AND** `KEYCLOAK_IDENTITY` 쿠키 둘 다(`seller-uid`·URL 단독 판정 금지).
- ⛔비밀번호: 거부된 값은 **24시간 다시 넣지 않음**(위탁계정 5회 오류=잠금·앱 재실행·정산 포함) · 매 실행 현재 대장 값 · 앞뒤 공백 떼고 입력 · 줄마다 값이 다를 때만 최대 2회(D-012·D-068·D-123).
- ⛔비밀번호 평문 = 공유 파일·git·출력물 금지(DPAPI `credstore`) · 관리대장은 평문 비밀번호가 있어 로컬 백업 안 함.
- ⛔프록시 = **비로그인 공개검색만**. 로그인·판매수집·정산 절대 미적용(위탁계정 밴 위험) · fail-closed(유효 프록시 없으면 직접연결 우회 금지) · IP 정책은 맥락별 반대(로그인=고정·순위=sticky 회전).
- ⛔쿠팡 순위 = **반자동만**(보이는 창·앱이 타이핑+Enter·화면만 읽음) · offscreen 자동 순위검색 폐기 · 검색 간격 45~75초(35~55 IP 태움·한 번에 낮추지 말 것).
- ⛔`rank_browser` 와 로그인 브라우저 동시 개방 금지 · 수집은 사람이 로그인한 세션/프로필 재사용에서만(쿠키 주입 새 브라우저 = Akamai 차단) · 2차인증/CAPTCHA 는 사람이 처리.
- 지문/TLS 위조 = 하드 금지 아님·**소유자 판단**(Claude 가 일방적으로 금지하지 말 것) · 단 위탁계정 밴 위험 최대 — 정합 위주·고위험(TLS/JA3·`_abck` 재생)은 별도 협의.

**실행·데이터**
- 로그인/판매수집 라이브 = 사무실만 · 전체실행·무인 `--auto` = ①반자동 → ②키워드선정 → ③반자동(offscreen 전무) · ⛔무인 강제종료 금지(①②③+재고 역기록 완주 후 종료).
- ⛔`output/`·`data/`·`config.json` 삭제 금지 · 개발·운용 폴더 구조 동일(상대경로).
- ⛔구글 관리대장 실패 = ❌ 실행 중단(PC 엑셀 폴백 없음·D-134) · 사람이 PC 엑셀을 고른 실행은 삭제·판매중지 표기 안 함.
- ⚠계정 삭제는 **되돌릴 수 없음**: 대장에서 줄이 사라지면 결과 이력 완전 삭제(계정 줄 전부 숨김도 같음·계정 정지는 계정아이디 칸 취소선) · 판매중지로 남으면 유지.
- ⛔사람 승인 대기열 금지 — 근거 남기는 자동 판단(글자 규칙→쿠팡 데이터→AI).
- 매칭 = AI 중심+VID 고정 · 결과 상품명 = 현행 노출상품명(못 찾으면 ❌오류) · 순위 VID 없으면 ❌오류(상품명 폴백 없음).
- ⛔체험단 자동값을 마케팅 칸(`set_marketing`)에 넣지 말 것 · 원장 링크에 관리대장 주소 금지(D-095) · 키워드 있으면 동결(추가만·제거 없음).
- fallback 금지(try/except pass, silent None) · 판매데이터 없음 = 정상 처리(오류 아님) · 응답 한국어.

## 코드 건강 규칙 (회귀 방지 — 2026-09-22, SSOT=`designs/CODE_HEALTH_PLAN.md`)
> 배경: 잦은 수정으로 4파일(`pipeline.py`·`workbook.py`·`app_qt.py`·`app.py`)이 비대·괴물함수화되고
> "과거 정상→오류" 회귀가 반복됨. 이를 막는 게이트를 뒀다. **아래는 매 작업에서 지킨다.**
> ✅ **정비 완료(2026-09-22)**: 4파일의 **D/E/F 괴물함수 전멸(전부 C 이하·헬퍼 분해·행동 불변)**, 핀 3종
> 신설(pin_login_ranks·pin_apply_style·pin_run_plan). 남은=**모듈 분리로 MI C→B**(대형파일 포화·별도 단계)·**라이브 검증**. 상세=`designs/CODE_HEALTH_PLAN.md`.
- **커밋/푸시 전 게이트 통과 필수**: `python tools/run_checks.py`(전체·오프라인·결정적 — 목록=`run_checks.CHECKS`, 개수는 실행 요약에 표시)가 초록이어야 함.
  git 훅이 자동 검사(pre-commit=`--quick`[시뮬+핀3+구글시트+**정밀렌더검증**], pre-push=전체+`check_complexity.py`).
  구성 = 시뮬레이션·핀4(로그인발견/apply_style/실행모드+단계조립/L1계약)·구글시트오프라인·정밀렌더검증·셀독계정상품이력관리원장·소싱 원장(업무일지·계약·채권자·CS 원장 4종은 HQ 로 이전·R0 삭제 D-037)·정산2·오프라인실증.
  **새 PC/클론 후 `python tools/install_hooks.py` 1회**. 응급 우회(`--no-verify`)는 **상시 금지**(회귀 유입).
- **테스트에서 실 API 금지**: 검증 3종은 로그인·OpenAI·네이버 **호출 없이** 돈다. `verify_offline`의 [6]
  키워드 선정도 **기본은 결정적 모킹**(경계만 페이크). 실 API 실증이 필요하면 `VERIFY_REAL_API=1`로 옵트인.
- **새 함수 CC ≤ 15 지향 · 파일 ≤ ~600줄 지향**: `check_complexity.py`가 4파일 밖에서 새 D+(CC≥21)
  괴물함수를 경고하고, 건강하던 파일이 MI **C로 떨어지면 차단**(exit 1). 건강(A/B) 파일은 그대로 유지.
- **A등급(건강) 파일은 건드리지 말 것**: 불필요 변경=새 회귀. 4개 썩은 파일 수정 시 **핀 테스트 먼저**
  (그 행동을 `simulate_pipeline`/`verify_offline`이 덮는지 확인, 얇으면 시나리오 추가 후 분해).
- **되돌림/정책 변경은 실측 근거 메모 필수**(플립플롭 방지, [[fix-from-real-evidence]]). 판매상태 소스·키워드
  로직처럼 왕복(A→B→A)한 이력이 있음 — 근거 없는 되돌림 금지.
- **분해는 행동 불변**(로직 바꾸지 말고 위치만): 정책·엣지케이스(로그인 판정·Akamai·날짜라벨·옵션분리·매칭
  게이트) 보존. 매 추출 후 게이트 초록 유지, 커밋은 작게·자주.

## 병렬 개발 (응답 대기 단축 — SSOT=`docs/PARALLEL_DEV.md`)
> 🧭 **2026-10-11 분리(D-035·D-036)**: 이 저장소 = **R0(쿠팡 분석 앱 + 정산 다운로드) 전용·독립 세션**. **HQ(`D:\commerce-hq`)가 R0 기능 전부+정산을 '필요한 기능만 이관'해 새로 구축 중 → 전환(cutover) 뒤 R0 은퇴. 이관 기간 R0 = 운영 유지·새 기능 개발 가능('치명 오류 수정만'은 적용 안 함 D-144)**. 본부 앱(메인 화면·위탁계정·위탁상품·계정 정산·CS·채권자)도 **HQ** 로 이전 — 관계는 HQ `docs/R0_DATA_CONTRACT.md`·`docs/COUPANG_ACCESS.md`(쿠팡 동시 접속 공유 잠금·프로필 공유)로만.
> 여러 세션이 **코드 편집만** 병렬. ⚠**런타임은 병렬화 금지**(단일 브라우저·위탁계정·Akamai·단일 마스터/시트 → 실행은
> 야간 단일 순차·라이브 테스트도 한 번에 한 세션). 상세·레인표·병합 프로토콜=`docs/PARALLEL_DEV.md`.
- **격리**: 세션마다 **자기 worktree+브랜치**에서 편집(master 직접 편집 금지). **비겹침 레인**(다른 파일집합)이라 merge 깨끗.
- **레인(편집 소유)**: A 수집/판매(`collector`·`pipeline_sales`·`pipeline_process`·`product_match`·`report`) · B 키워드(`kw_*`·`keyword_store`) · C 순위(`rank`·`pipeline_ranks`) · D 이미지(`detail_images`) · E 원장/정산(`registry_*`·`input_list`) · F 구글시트(`gsheet*`·`pipeline_gsheet`) · G 워크북(`workbook*`) · H UI(`ui/*`).
- **공유=직렬화**(한 번에 한 세션 or 통합 세션): `config.py`·`pipeline.py`·`browser.py`·`credstore.py`·`CLAUDE.md`·`designs/`·`docs/DECISIONS.md`. 레인이 config 값 필요하면 통제 세션에 요청(직접 편집 금지).
- **충돌 핫스팟**: 게이트/핀 파일(`tools/verify_offline.py` 등)=핀 함수 append+등록 1줄만 충돌 · DECISIONS/메모리=append-only.
- **병합**: 각 레인 `run_checks` 초록 후 push → **master 병합은 직렬**(한 브랜치씩·게이트 재실행). **2~3레인이 최적**(7레인 통제 관료제 불필요).
- **⛔배포 zip 생성·결과 구글시트 반영 = 통제 세션('Coupang Analytics')만**(소유자 2026-10-21 '일원화'): 다른 세션은 코드→게이트→master 푸시→통제 세션 알림까지·제안도 금지. 근거 = 10-21 사이드 세션 사본 반영 때 오입력 계정ID 3칸 노출([[feedback-control-session-only]]).

## 환경
- Windows, Python, Playwright(sync) + 실제 Google Chrome. 키(설정 탭에서 1회 입력→credstore 자동 로드): **필수** 네이버 검색광고 API + **OpenAI(ChatGPT) API**(키워드 AI 필수, 없으면 실행 중단).
- ⛔ **네이버쇼핑 검색 API(shop.json)는 2026-07-31자로 완전 종료**(대체 없음) — 경쟁강도 소스 소멸. 설정 탭 "(선택) 네이버쇼핑 키"는 무의미(발급 불필요), `kw_shopping.py`는 죽은 엔드포인트. 경쟁강도 대안=쿠팡 검색결과 총 상품수(구현 보류, HANDOFF §4-1).
