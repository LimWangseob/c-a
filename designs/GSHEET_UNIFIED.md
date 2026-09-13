# 스펙: 구글 시트 완전 통합 (입력=관리대장 구글시트 · 출력=결과 구글시트)

> 상태: **구현 착수(Phase 1 진행).** 이 문서는 그 착수용 SSOT다.
> 작성: 2026-09-13. 대상 저장소: `D:\coupang-analytics` (branch: master).

---

## ★ 확정 모델 (2026-09-13 사용자 확정 — §0의 '1개 시트'를 정정)

**파일은 2개**다(원래 '구글시트 1개' 초안을 사용자가 아래로 정정):

1. **입력 = 「토탈셀러_셀독 관리 대장」(구글시트 원본).**
   - 이게 **원본**이다. 지금은 이걸 PC로 내려받아 xlsx 입력으로 쓰고 있었다.
   - **계정 추가·삭제가 여기서 일어난다**(사람이 대장에서 계정/상품을 등록·제거).
   - 프로그램은 이 대장에서 계정/상품 로스터 + **비밀번호**를 읽는다.
2. **출력 = 결과 구글시트**(통계 + `계정목록` 시트).
   - `계정목록` 시트 = **관리대장의 계정/상품을 미러링**(추가→행 추가, 삭제→⛔판매중지 표기·데이터 보존) +
     **직원이 마케팅 시작일·종료일·모니터링 종료일을 직접 입력**하는 편집 영역.
   - 사업자별 통계 시트 = 프로그램 자동 생성/갱신.

### 확정 결정 (Phase 0 + 모델 정정)
- **비밀번호 = 관리대장(입력)에만.** 결과 구글시트(출력물)에는 비번을 두지 않는다 → "출력물 평문 금지" 원칙 부합.
  프로그램은 관리대장에서 읽는 즉시 DPAPI 저장·메모리 폐기.
- **관리대장 읽기 = 서비스계정 Sheets API 직접 조회.** 결과 쓰기와 **동일 서비스계정 1개**. 다운로드 불필요.
  관리대장을 서비스계정에만 '편집자/뷰어'로 공유하면 '링크가 있는 모든 사용자'를 꺼 비번 노출을 줄일 수 있다.
- **입력 소스는 병존**: (구)PC 파일 입력 **기존 유지** + (신)구글드라이브 등록(관리대장 링크). 설정 탭에서 등록.
- **xlsx 출력 = 병행 유지**(오프라인 백업). 결과 구글시트가 주 출력.
- **rclone 구글드라이브 업로드 = 제거**(결과가 이미 구글시트).

### `계정목록`(출력) 동기화 규칙
- 관리대장에 **새 계정/상품** → `계정목록`에 행 추가(마케팅 열은 빈칸 → 직원이 채움).
- 관리대장에서 **삭제/판매중지** → `계정목록` 해당 행 **⛔판매중지 표기(데이터 보존, 옵션 B)**, 재등장 시 해제.
- **직원 입력 열(마케팅 3열)은 프로그램이 절대 덮어쓰지 않는다** — 미러링은 로스터/상태 열만.

---

## 0. 한 줄 요약

지금은 **입력=관리대장(PC/구글 xlsx 다운로드)**, **출력=`쿠팡데이타분석_통계.xlsx`(openpyxl)** 로 파일이 사실상 2개다.
이걸 **구글 시트 1개**로 합친다:

- **하나의 구글 스프레드시트** 안에
  - `계정 목록` 시트 = **편집 영역**(사람이 온라인에서 계정 등록/삭제·마케팅 일자 등록) — 기존 관리대장 대체
  - 사업자별 통계 시트들 = **자동 생성 영역**(프로그램이 Sheets API로 수집 결과를 씀)
- 프로그램은 이 시트의 `계정 목록`을 **읽어** 수집하고, 통계 시트를 **써서** 갱신한다.
- 팀은 링크 1개만 공유. 다운로드/업로드 없음. 내부 링크(시트 간 이동)도 네이티브로 작동.

---

## 1. 왜 이 방향인가 (배경·결정 근거)

- **핵심 이점**: 현재 xlsx 마스터는 사람이 한셀/MS엑셀로 열어 저장하면 openpyxl 재로드가 깨졌다
  (`_cell_styles IndexError`). 구글 시트는 **온라인 편집 + Sheets API 읽기/쓰기**라 이 문제가 원천적으로 없다.
- 파일이 1개 → 직원 공유·버전 혼란 제거(사용자 반복 요청: "파일 여러개면 관리 어려워, 직원 공유 혼란").
- 시트 간 하이퍼링크가 구글 네이티브에서 정상 작동(xlsx→구글 변환 시 링크 깨지던 문제 해소).

### 앞선 세션에서 확정된 관련 결정 (뒤집지 말 것)
- 결과 서식: `계정 목록` 시트(상품 단위 행, 계정ID 표시, 첫 탭 고정, 각 시트에 "👈 계정 목록" 빨간 복귀 링크),
  하단 테두리 통일, **"순위 공란" 열 삭제**.
- 마케팅: `계정 목록`/관리대장에 **마케팅 시작일·종료일·모니터링 종료일** 입력 → 상품별 수집주기
  (마케팅+1개월 매일 / 그 외 3일 1회 / 모니터링 종료 후 중단), 비고 🔴체험단중, 마케팅 기간 통계 컬럼 배경색.
- 삭제/판매중지 상품·계정 → **"⛔ 판매중지" 표기(데이터 보존)**, 다시 나타나면 해제 (옵션 B).
- 순위 자동 버튼 삭제, **반자동만 유지**.
- 이 통합은 **A안(입력=관리대장, 출력=통계)** 을 부분적으로 되돌린다 → 통합 후엔 입력·출력이 한 구글 시트.

---

## 2. ⚠️ 반드시 지킬 제약 (보안·정책)

1. **🔒 비밀번호는 공유 시트에 넣지 않는다(원칙).** 코드베이스/사용자 확정 규칙:
   "비번은 출력에 넣지 않고 관리대장에만", "공유 파일·git·출력물에 평문 금지, DPAPI 암호화만".
   - ⚠️ **모순 지점(반드시 사용자와 먼저 합의):** `계정 목록`이 관리대장을 **대체**하면 비번도 그 시트에
     들어가야 로그인이 된다. 현재 관리대장(공유 구글시트)에 이미 비번 평문이 있는 것과 **동일 모델**이라
     "새로운 노출"은 아니다. 그러나 "출력물에 평문 금지" 원칙과는 충돌한다.
   - **해결 옵션(새 세션 첫 결정 사항):**
     - (a) 비번 열을 그 시트에 두되(현행 관리대장과 동일), 프로그램은 읽는 즉시 DPAPI 저장하고 메모리에서 폐기.
       → 가장 단순하지만 "공유 시트에 평문 비번" 상태가 유지됨(현행과 동일).
     - (b) 비번은 **별도 비공개 시트/파일**로 분리하고, 공유 `계정 목록`엔 비번 열 없음.
       → 원칙 부합. 단 입력 소스가 다시 2개가 됨(통합 취지 약화).
     - (c) 비번을 각 PC에 1회 등록(credstore)하고 시트엔 아예 두지 않음.
       → 가장 안전. 단 PC마다 최초 1회 수동 등록 필요, 계정 추가 시 재등록.
   - **기본 권고 = (a)** (현행 관리대장과 동일 모델, 통합 취지 유지). 단 사용자 명시 승인 필요.
2. **로그인 = 실제 Chrome 자동입력만.** 지문위조/HTTP 위장로그인 금지(DESIGN §4 고정). 이 스펙은 로그인 경로를
   전혀 건드리지 않는다.
3. **위탁(consignment) 계정** — 5회 오류 시 계정잠김. 로그인 재시도는 계정당 실행당 1회로 엄격 제한(기존 유지).
4. 응답·산출물 한국어.

---

## 3. 현재 코드 자산 (재사용 가능한 것)

- `src/coupang_analytics/gsheet.py` — 공개 구글 시트 **읽기(export?format=xlsx)** 구현됨. 인증 불필요.
  - ⚠️ **한계: 읽기 전용.** 쓰기(통계 시트 갱신)는 불가능 → **Sheets API + 인증 필요**(§4).
  - `sheet_id_from_url`, `download_xlsx` 재사용 가능(읽기 폴백/오프라인용으로 남길 수 있음).
- `src/coupang_analytics/input_list.py` — `parse_input_list`. 헤더 1~8행 자동감지, 마케팅 3열 별칭 처리
  (`mkt_start/mkt_end/mkt_mon`), 필수열=사업자·계정아이디·상품명. **구글 시트에서 읽은 행 데이터도 이 파서로
  재사용** 가능하도록 구조 맞추면 됨.
- `src/coupang_analytics/workbook.py` — 현재 **openpyxl 출력 전체 서식 로직**(병합·색·테두리·틀고정·상품블록·
  마케팅 배경색·상태·하이퍼링크·`계정 목록` 인덱스). **이 서식을 Sheets API로 재현하는 것이 최대 작업량.**
  - 재사용할 핵심 로직: `_key`(vid 앵커 키), `_display_name`, `_parse_date`, `product_cadence`/`product_due`/
    `account_due`(수집주기), `set_marketing`/`marketing_of`/`_mkt_status`, `set_discontinued`/`reconcile_account`,
    `_build_index`(계정 목록 구성), 마케팅 배경색/상태/테두리 규칙.
  - 이 로직들은 **서식 렌더러와 분리**되어 있으면 그대로 재사용 가능 → 리팩터링 시 "데이터 모델/규칙"과
    "openpyxl 렌더링"을 명확히 갈라두는 게 관건.
- `src/coupang_analytics/pipeline.py` — `run_full`, `_process_account` 등. 입력 로드부와 출력 저장부만
  구글 시트 백엔드로 교체하면 파이프라인 몸통은 유지 가능.
- `ui/app_qt.py` — 설정 탭에 이미 **"결과 파일을 구글드라이브로 공유하기"**(rclone) 있음. 통합되면 이 rclone
  업로드는 **불필요**해질 수 있음(결과가 이미 구글 시트) → 제거/유지 결정 필요.

---

## 4. 구현 계획 (단계별 — 새 세션에서 이 순서로)

### Phase 0 — 결정 확정 (✅ 완료 2026-09-13)
- [x] 비번 = **관리대장(입력)에만**. 결과 구글시트엔 비번 없음(모델 정정으로 (a)보다 안전한 해법 확정).
- [x] xlsx 출력 = **병행 유지**(오프라인 백업).
- [x] rclone 구글드라이브 업로드 = **제거**.

### Phase 1 — 인증 + Sheets API 기반 (✅ 완료 2026-09-13)
- [x] 서비스계정 발급·공유 가이드 문서화 → `docs/GSHEET_SETUP.md`.
- [x] 서비스계정 키 저장 = credstore(DPAPI) 키 `__gsheet_sa__`(JSON 본문). `gsheet_api.store_sa_json`.
- [x] 라이브러리 `google-api-python-client`+`google-auth` requirements/spec 추가. PyInstaller: `googleapiclient`
      collect_all + **static_discovery=True**(번들 sheets.v4.json 확인) + `google.auth/oauth2` submodules.
- [x] `src/coupang_analytics/gsheet_api.py` 신규: `GSheetClient`(read_values/write_values/clear_values/
      ensure_sheet/batch_update/meta/sheet_id) + `check_access`(연결확인) + SA 키 로드/저장 + 403/404/429 한국어 매핑.
- [x] `ui/app_qt.py` 설정 탭: "구글 시트 연동" 카드(서비스계정 키 등록 · 관리대장(입력) 링크 · 결과(출력) 링크 +
      각 '연결 확인'). rclone "구글드라이브 공유" 항목·`_upload_to_gdrive` 제거. **PC 엑셀 입력은 병존 유지.**
- 남은 것(Phase 2에서): 등록한 관리대장 링크를 실제로 **읽어 파싱**(현재는 링크 저장·연결확인까지).

### Phase 2 — 입력(관리대장) 읽기 → 파이프라인 연결 (✅ 코어 완료 2026-09-13)
- [x] `input_list.py` 리팩터: 공용 코어 `_parse_grid`(파일·API rows 공용) + `parse_input_rows(rows)` +
      `parse_password_rows(rows)` + `read_ledger_rows(url)`(서비스계정으로 본체 시트 자동선택·값 읽기).
- [x] **삭제/판매중지 감지 = 취소선 또는 관리대장 '상태' 컬럼**(둘 중 하나면 제외). `IN_ALIASES_STATUS`/`IN_STATUS_DISCONTINUED`.
      구글시트도 취소선을 **읽는다**(`GSheetClient.read_grid_struck` → Sheets API `effectiveFormat.textFormat.strikethrough`
      + `textFormatRuns`). 파일·구글시트 양쪽 다 **취소선+상태 병행**(동작 일치). 상태값=판매중지·삭제·해지·중지 등 부분일치.
      '판매중'·'판매부진'·'정상'은 제외 아님(검증됨). 계정행 상태=계정 전체 제외, 상품행 상태=그 상품 제외.
- [x] UI: 설정 탭 "관리대장에서 불러오기" 버튼(등록 링크를 서비스계정으로 읽어 입력 적용, 비번 즉시 DPAPI).
      `input/source=gsheet` 표시 → 무인 자동로드가 구글시트 우선(실패 시 PC 엑셀 폴백). PC 입력 병존 유지.
- ⚠ **마케팅 3열의 권위 출처 = 출력 `계정목록`(직원 입력), 관리대장 아님.** 파서가 대장의 마케팅 열도 읽지만
      대장엔 보통 비어 있음 → **Phase 3에서 출력 `계정목록`의 마케팅 값을 읽어 상품 모델에 머지**(직원 입력이 우선).
- 라이브 검증은 사무실에서만 가능(서비스계정+실제 대장 링크). 오프라인 파싱·상태감지·회귀는 검증됨.

### Phase 3 — 출력 쓰기: openpyxl 서식 → Sheets API 재현

**확정 스키마 = 기존 openpyxl `계정 목록` 7열 그대로**(사용자 확정 2026-09-13):
`A 사업자 | B 상품명(클릭 이동·노출명·통계시트 하이퍼링크) | C 계정ID | D 마케팅시작 | E 마케팅종료 |
F 모니터링종료 | G 상태`. **자동열=A·B·C·G**(프로그램), **직원 입력열=D·E·F**(온라인 편집, 프로그램 미접촉).

#### Phase 3a — `계정목록` 동기화 (✅ 완료 2026-09-13)
- [x] `src/coupang_analytics/gsheet_index.py` 신규: `IndexRow`(자동열 데이터+안정키+링크) / `plan_sync`(순수·
      테스트됨) / `sync_index`(빈 시트=전체빌드, 아니면 증분).
- [x] **쓰기 규칙(사용자 확정)**: 자동열만 갱신 · **신규 상품은 계정별 그룹 맨 마지막**에 `insertDimension`으로
      빈 행 삽입(기존 마케팅 행이 통째로 밀려 D~F 보존) · 새 계정은 맨 아래 · 삭제/판매중지=**상태만 ⛔**(행·마케팅 보존).
- [x] **행 매칭 = 안정 키**(계정ID+vid 앵커, 노출명 바뀌어도 불변)를 A열 셀 **메모(note)** 에 저장/조회.
- [x] **마케팅 D~F 값은 어떤 경로에서도 안 씀**(단위테스트로 불변식 검증). 동시편집 안전.
- [x] 서식: 제목 병합·헤더색·마케팅 안내색(FFF2CC)·틀고정(2행·A~C 3열)·열너비·B열 HYPERLINK.

#### Phase 3b — 통계 시트 쓰기 (✅ 완료 2026-09-13 — **openpyxl 시트 미러링** 방식, 사용자 확정)
- [x] **방식 = openpyxl 마스터 미러링**(규칙 재구현·이중 렌더러 대신, 이미 완성된 openpyxl 시트를 그대로 번역).
      `src/coupang_analytics/gsheet_stats.py`: `worksheet_to_requests(ws, sheet_id, index_gid)`(순수·테스트) —
      openpyxl 사업자 시트 1개 → Sheets `batchUpdate`(병합해제→그리드/틀고정→값+서식 updateCells→병합 재적용→
      열너비/행높이). 색(ARGB→0~1)·글꼴·정렬·줄바꿈·테두리·숫자서식 번역. "👈 계정 목록" 복귀 링크는 구글
      `계정목록` gid 로 `=HYPERLINK("#gid=..&range=A1", …)` 재연결. `push_statistics(client, wb)` — 사업자 시트만
      **전체 교체**(프로그램 전용이라 안전), 특수시트 제외. `GSheetClient.ensure_sheets([...])` 로 대량 최초 생성 429 회피.
- [x] **시계열 이어쓰기** = openpyxl 마스터가 이미 날짜 컬럼을 누적(키워드 동결)하므로 그 시트를 미러링하면 그대로 재현.
- [x] **파이프라인 배선**: `run_full(..., gsheet_output_url=)`(UI가 `gsheet/output_url` 전달·수동/무인 3개 호출부).
      최종 저장(마스터·스냅샷) 직후 `_push_gsheet`: `push_statistics` → `gsheet_index.roster_from_workbook(wb, gids)`
      → `sync_index`(계정목록 증분, 마케팅 D~F 보존). 실패는 **로그로 명시**하되 xlsx는 이미 저장(비치명적).
- [x] **안정키 규약 통일(§7)**: 블록 생성 시 **등록상품명 보존**(`workbook.set_registered_name`/`registered_name`,
      `_상품ID` 숨김시트 6열, `set_display_name` 후에도 불변). `IndexRow.key = marketing_key(계정ID+등록상품명)`
      → 노출명이 바뀌어도 3c 마케팅 머지·행 매칭 안정. `OutputWorkbook.product_roster()`/`status_of()` 공개.
- 검증: `tools/verify_gsheet_offline.py` [5][6] 추가(미러링 요청·등록명 보존·로스터 안정키). 라이브(서비스계정+실제 시트)는 사무실.

#### Phase 3b+ — 키워드 출처 이원화(AI ↔ 직원 입력) (✅ 완료 2026-09-13)
상품별 키워드는 **①AI 자동 선정** 또는 **②직원이 결과 통계 시트에 직접 입력** 둘 중 하나로 결정. 규칙 =
`workbook.product_keywords`가 **비지 않으면 AI 선정 생략·동결**(사람 입력 포함), 비면 AI 선정 실행 — 이 게이팅은
이미 파이프라인에 있었고(`_process_account` 520~548), 빠졌던 것은 **직원이 구글 결과 시트에 넣은 키워드를 워크북으로
되읽는 경로**(미러링이 전체 교체라 역머지 없으면 다음 실행 때 지워짐). 구현:
- `gsheet_stats.read_staff_keywords(client, wb)` — 통계 시트를 push 레이아웃대로 되읽어 {(사업자,상품): [키워드]}.
  상품 헤더(G='날짜') / 키워드 소헤더(C='키워드') / 그 아래 C값 = 키워드(**위치 기반** — 직원 행에 G='노출 순위'가
  없어도 잡음). `merge_staff_keywords` = 워크북에 **없던 키워드만** 추가(`add_product_keywords`, 기존 보존·제거 없음).
- `pipeline._pull_gsheet_keywords` = **실행 시작 시**(키워드 단계 전) 역머지 → 그 상품은 AI 선정 생략. 시작에
  들어가므로 종료 시 미러링(전체 교체)돼도 직원 입력 보존. `keywords_off`(①판매수집 전용)엔 미적용.
- 제약: **추가만·제거 없음**(동결 원칙 일관). 첫 실행엔 통계 시트가 없어 no-op(시트 생성 후부터 입력 가능).
- 검증: `verify_gsheet_offline.py` [7](위치기반 파싱·1개 추가·기존 보존·재실행 idempotent).

#### Phase 3c — 마케팅 역방향 머지 (✅ 완료 2026-09-13)
- [x] `gsheet_index.read_marketing(client)` — 출력 `계정목록`의 직원 입력 D~F를 {안정키:(시작,종료,모니터링)}로
      읽음(값 없는 행 스킵, 시트 없으면 빈 dict). `marketing_key`=계정ID+등록상품명(=Phase 3a note 규약).
- [x] `gsheet_index.apply_marketing(accounts, map)` — InputList 상품에 병합(직원 입력이 대장/기존값보다 우선).
- [x] UI: `_merge_output_marketing(il)` — 입력 로드(파일/구글시트 공용) 후 출력 링크+서비스계정 있으면 자동 병합.
      → 이후 수집주기(account_due)·마케팅 표기가 **직원 입력 마케팅**으로 구동. 실패해도 입력 로드 안 막음.
- 검증: read/apply/빈시트 오프라인 테스트 통과(값매칭·직원우선·미입력행 스킵).

### Phase 4 — 마무리
- [ ] 동시성: 프로그램 쓰기 중 사람이 편집 → 마지막 쓰기 승리 위험. `계정 목록`은 읽기만/통계는 쓰기만으로
      물리 분리해 충돌 최소화. 필요 시 수집 시작 시점 스냅샷.
- [ ] 오류 처리: 인증 실패·권한 없음·쿼터 초과(429) 명확한 한국어 메시지(fallback 금지 원칙).
- [x] `ui/app_qt.py` 설정 탭: "구글 시트 연동" 카드(입·출력 링크 + 서비스계정 키 + 연결확인). rclone 정리(Phase 1).
- [x] `ui/app.py`(Tkinter 폴백) 동기화 — PySide6 없이 `_shared_setting`(winreg)로 app_qt의 `gsheet/output_url`
      읽어 `run_full(gsheet_output_url=)` 전달(ba0a444). SA키는 credstore 공유라 별도 불필요.
- [ ] `tools/simulate_pipeline.py` 및 검증도구를 Sheets API 모킹으로 갱신(라이브 쿼터 소모 없이).
- [ ] CLAUDE.md·DESIGN.md·memory 갱신.

---

## 5. 데이터 모델 / 시트 스키마 (✅ 확정 — 출력 `계정목록` 7열)

**출력** 결과 구글시트의 `계정목록` 시트(=기존 openpyxl `계정 목록` 그대로). **입력(관리대장)과 별개 파일.**

| 열 | 성격 | 내용 |
|---|---|---|
| A 사업자 | **자동** | 계정 로스터(관리대장 미러) |
| B 상품명(클릭 이동) | **자동** | 매칭된 실제 노출명 + 통계시트 HYPERLINK(노출명·블록링크가 이 한 열에 접힘) |
| C 계정ID | **자동** | |
| D 마케팅 시작일 | **직원 입력** | 온라인 편집 — 프로그램 미접촉 |
| E 마케팅 종료일 | **직원 입력** | |
| F 모니터링 종료일 | **직원 입력** | |
| G 상태 | **자동** | 예정/체험단중/모니터링/종료/미수집/⛔ 판매중지 |

> 계정 추가·삭제는 **입력 관리대장**에서, 마케팅 등록은 **출력 `계정목록` D~F**에서. 비번 열 없음(관리대장에만).
> 행 안정 키(계정ID+등록상품명)는 A열 셀 **메모**에 저장(노출명이 바뀌어도 행 매칭 안정).
> 구현: `gsheet_index.py`(IndexRow/plan_sync/sync_index/read_marketing/apply_marketing).

---

## 6. 리스크 / 미해결

- **작업량**: Phase 3b(통계 시트 서식 재현)가 가장 큼. openpyxl 서식이 Sheets API `batchUpdate`로 1:1
  대응되지 않는 부분(특정 병합·조건부 서식) 검증 필요. → 수 커밋 규모.
- **PyInstaller**: `google-api-python-client`/`google-auth` 번들. spec에 collect_all(googleapiclient) +
  static_discovery 반영 완료 — 실제 빌드로 sheets.v4.json 포함·용량 증가 확인 필요(현재 278MB).
- **API 쿼터**: Sheets API 분당 한도(기본 ~60/분/사용자). 상품(79)×계정(35) 대량 쓰기는 batchUpdate로 묶어 최소화.
- **오프라인**: 사무실에서 구글 접속 불가 시 수집 자체가 막힘 → xlsx 병행 백업 유지(결정됨).
- **동시성(Phase 3b/4)**: 통계 쓰기 중 직원이 계정목록 편집. `계정목록`은 자동열만/마케팅열 미접촉으로 물리 분리해
  이미 안전(Phase 3a). 통계 시트는 프로그램 전용이라 충돌 낮음.

---

## 7. 새 세션 시작 — Phase 3b (복붙용)

```
designs/GSHEET_UNIFIED.md §4 Phase 3b 를 이어서 구현한다("★ 확정 모델"·§5 스키마 먼저 숙지).
Phase 1·2·3a·3c 는 이미 완료(아래 '착수 전 필독' 참고). 이제 통계 시트 쓰기를 Sheets API로 재현한다:
workbook.py 상품블록 서식 → batchUpdate(일자 가로누적·키워드 순위·재고·마케팅 배경색·테두리·틀고정·
"👈 계정 목록" 복귀 링크) + 시계열 이어쓰기 + 데이터모델/렌더러 분리 리팩터.
제약: 실제 Chrome 로그인만·위탁계정 로그인 1회·비번은 관리대장(입력)에만·한국어. 검증: python tools/verify_gsheet_offline.py.
```

### 착수 전 필독 (현재 상태 · 2026-09-13)

**완료(오프라인 검증됨, 라이브는 사무실 필요):**
- Phase 1 — `src/coupang_analytics/gsheet_api.py`(서비스계정 인증·GSheetClient read/write/ensure_sheet/
  batch_update/read_grid·check_access·403/404/429 한국어). SA키=credstore `__gsheet_sa__`. 설정 가이드=`docs/GSHEET_SETUP.md`.
- Phase 2 — `input_list.py`: `_parse_grid`(공용)·`parse_input_rows(rows, strike_grid=)`·`parse_password_rows`·`read_ledger_rows`.
  **삭제/판매중지=취소선(`read_grid_struck`) 또는 관리대장 '상태' 컬럼**(`config.IN_ALIASES_STATUS`/`IN_STATUS_DISCONTINUED`).
- Phase 3a — `src/coupang_analytics/gsheet_index.py`: `계정목록` 동기화(IndexRow/plan_sync/sync_index).
  자동열(A·B·C·G)만·신규는 계정그룹 맨끝 insertDimension·삭제=상태만 ⛔·**마케팅 D~F 값 미접촉**·안정키 A열 note.
- Phase 3c — `gsheet_index.read_marketing`/`apply_marketing` + UI `_merge_output_marketing`(입력 로드 후 자동 병합).
- UI(`ui/app_qt.py`) 설정 탭: "구글 시트 연동" 카드(SA키·입력/출력 링크·연결확인·"관리대장에서 불러오기"). rclone 제거.
- 의존성(requirements.txt·spec) 추가. QSettings 키: `gsheet/input_url`·`gsheet/output_url`·`input/source`.

**Phase 3b 완료(2026-09-13) — 위에서 미해결이던 항목 전부 처리됨:**
- ✅ `sync_index` 파이프라인 배선 완료(`_push_gsheet` → `roster_from_workbook` → `sync_index`).
- ✅ 통계 시트 구글 쓰기 완료(`gsheet_stats.push_statistics`, openpyxl 미러링).
- ✅ 안정키 규약 통일(등록상품명 보존 → `IndexRow.key = marketing_key(계정ID+등록상품명)`).

**남은 것(Phase 4 — 마무리):** 라이브 검증(사무실), Tkinter 폴백(`ui/app.py`) 동기화, 동시성/쿼터 실측,
CLAUDE.md·DESIGN.md 반영. 첫 실행 시 시트 대량 생성 + 사업자별 batchUpdate 버스트의 실제 429 여부 라이브 확인 필요.

**리팩터 지침(3b 핵심):** `workbook.py`의 "데이터 모델/규칙"(`_key`·`_display_name`·`marketing_of`·`_mkt_status`·
`reconcile_account`·`_product_rows`·수집주기)과 "openpyxl 렌더링"을 분리 → 두 렌더러(openpyxl·Sheets)가 규칙 공유.
⚠ 기존에 잘 도는 openpyxl 출력을 깨지 말 것(seldoc-output-format 서식 영구고정 원칙). 먼저 규칙만 추출하고 렌더러는 그대로 둘 것.

### 미커밋 변경(이 세션 산출)
`git status`: 신규 `gsheet_api.py`·`gsheet_index.py`·`docs/GSHEET_SETUP.md`·`tools/verify_gsheet_offline.py`,
수정 `input_list.py`·`config.py`·`ui/app_qt.py`·`requirements.txt`(×2)·`coupang_analytics.spec`. **아직 커밋 안 함**(사용자 지시 대기).
