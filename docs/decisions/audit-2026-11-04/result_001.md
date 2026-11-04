# D-001~D-030 결정 기록 감사 결과

커버리지: docs/DECISIONS.md 12~229행 전체 열람(1~235행 실제 읽음) · 판정 블록 30개 · 코드 대조는 Grep/Read만(radon·테스트 등 실행 없음) · 경로 기준 D:\coupang-analytics · S = src/coupang_analytics

분류별 개수: OK 20 · MARK_MISSING 8 · STALE 1 · OWNER_POLICY 1 · STATUS_MISSING 0 · MISMATCH 0 (합 30)

## 1. OK 표

| D번호 | 태그 | 근거(파일:행 또는 식별자) |
|---|---|---|
| D-001 | SESSION_KIT | 운영 규칙 기록·모순 없음. STATE.md 54줄·CLAUDE.md 152줄·docs/memory/MEMORY.md 48줄·최근 커밋 `[R87]` 형식·`~/.claude/skills/session-close/SKILL.md` 존재. 비고: 아래 '확인 필요' 1번(HANDOFF.md) |
| D-002 | SETTLE_ERRORS | S/settlement_wing_api.py:279-282(ServerBusy / 403·429·HTML=ApiBlocked), tools/settlement_download.py:255 `SERVER_BUSY_RETRY = (15, 2)`, :458·:671 '대기' 처리 |
| D-003 | SETTLE_VERIFY | S/settlement_verify.py:40-51 `rg_formula`("H−I−J+K+매출조정"), :84 "최종−보상 ↔ 월렛 입금" |
| D-004 | SETTLE_RG_PAYDATE | S/payout.py:83-99 `rg_payout_date`(70·100%=+20영업일, 30% 월걸침=+25영업일, 그 밖=익익월 첫 영업일). 비고: 아래 '확인 필요' 2번(운영 공휴일 집합) |
| D-005 | SETTLE_COMPENSATION | S/settlement_verify.py:93 "대표 정산 계좌로 정산일 별도 입금(월렛 아님)"·판정 CONFIRMED, :6. 비고: :70 독스트링의 "(지급 경로 미확인)"은 옛 표현이 남은 것(동작 영향 없음) |
| D-006 | SETTLE_INFLOW | S/settlement_verify.py:323-324(대표계좌 입금 합계=윙+월렛 인출+보상+환급), :290-294 `_refund_day` 익월 21일, :337, S/settlement_stats.py:309 `계좌 입금` 시트 |
| D-008 | NO_VIDLESS_BLOCK | S/product_match.py:171 `_paren_agrees`, S/pipeline_process.py:333 `_skip_unmatched`, :346 `_purge_vidless_blocks`(live_vids 없으면 건너뜀·다른 계정ID 미접촉). D-040은 미수집 계정용 보완으로 충돌 없음 |
| D-011 | MATCH_ORDER | S/product_match_ai.py:27-30(15·5·150·text-embedding-3-small), :34 `MATCH_SYSTEM`, :217-223 4자 미만 제외, :230 `_apply_exact`, :357 `_candidate_ids`, :411 `openai_embed`. 비고: D-046이 입력 문구를 칸 전체로 넓혔으나 판단 순서는 유지(보완) |
| D-013 | EXPOSED_NAME | 상태 줄 `SUPERSEDED by D-015` 정상, D-015 "D-013 을 대체". 대체 후 동작은 S/pipeline_process.py:182 `_block_names` |
| D-014 | RANK_NOTE | S/config.py:8-9, S/workbook_render.py:357-358. 비고: D-084·D-114 이후 조사 범위가 미세하게 달라졌으나 안내문 핵심은 맞음(대표 판매중지여도 옵션 판매중이면 조사). 문구 변경 여부는 소유자 선택 사항 |
| D-017 | WORKBOOK_SPLIT | S/workbook.py:18-20·:27(mixin 3개), tools/check_complexity.py:27 `KNOWN_BAD = {"pipeline.py", "app_qt.py"}`. workbook.py 현재 621줄. MI 등급은 실행 금지로 재측정 안 함 |
| D-018 | LEDGER_PW_TRIM | S/input_list.py:222·:240-252(`trimmed`·strip), ui/app_qt.py:1169-1171 경고. 비고: 본문 'Tk 폴백'은 D-022 B1로 사라진 경로를 가리키는 곁말. D-123이 범위 확장(대체 아님, D-123 상태 줄에 명시) |
| D-019 | DESIGNATED_SKIP_FILLED | S/pipeline.py:485 `ctx.designated and wb.sales_filled`, S/workbook_dates.py:69, ui/app_qt.py:1603 |
| D-020 | SETTLE_STOP_WITH_APP | S/app_process.py:102·109·117·135, tools/settlement_download.py:731 `_watch_app`·:827 `--parent`, ui/app_qt.py:1687-1688 `_auto_quit`, ui/settlement_status_panel_qt.py:258-260 |
| D-023 | CLEANUP_KEEP_SETTLE2 | S/payout.py:136 `estimate`, S/registry_history.py:101 `managed_between`(지금은 S/settlement_accounts.py:129·139에서 운영 사용). `scope_to_ledger`·`parse_password_rows`·`active_count` 검색 0건 |
| D-025 | FIX_E1_E7 | S/pipeline.py:738 `pull_gsheet_keywords`, S/pipeline_gsheet.py:35·:86, S/gsheet_api.py:285, deploy/install.ps1:202·install_schedule_py.ps1:19 `-Hours 23 -Minutes 50`, deploy/정산_상태확인.bat '18:00 야간 무인' 문구. `16종|게이트 N` 검색(run_checks·install_hooks·CLAUDE.md) 0건 |
| D-026 | CLEANUP_B7_DEAD | 삭제 식별자 전부 src·ui·tools 검색 0건. rank.py 274줄, proxy_manager.py:158-161 `__init__`(인자 proxy_list만), `def do_track_ranks(self)` ui/app_qt.py:1764, designs/DESIGN.md:351. 비고: DESIGN.md:211 '세션 킵얼라이브(선택)' 문구 잔존(문서 정리 후보) |
| D-027 | CLEANUP_B8_HELD_TOOLS | tools/test_rank_images_live.py 없음, 유지 대상 7종·deploy/install_schedule_py.bat/.ps1 모두 존재, S/config.py:281-291 `rank/block_images` |
| D-028 | FIX_RANK_KW_LOSS | S/pipeline.py:565 `_resume_source`·:180 `_column_label`, S/pipeline_paths.py:43 `column_label`, S/pipeline_ranks.py:243 `_rank_date`, S/workbook.py:411·S/pipeline_process.py:173 `ensure_keyword_section`. 비고: 아래 '확인 필요' 3번(원문 훼손) |
| D-029 | LOGIN_NO_SKIP | S/pipeline.py:461 `_not_done`·:515 `_collect_with_login(pace_first)`·:775-779 즉시 1회 재시도, S/config.py:160-161 45~120초. `LOGIN_BLOCK_CIRCUIT|LOGIN_NIGHT_RESUME|night_resume` 검색 0건 |

## 2. OK 외 항목

### D-007 [SETTLE_CALENDAR]
- 판정: OWNER_POLICY (핵심 결정은 코드와 일치, 딸린 미결 건만 소유자 확인)
- 원문 인용(58행): "⚠연관: designs/coupang_golden_cases.json PAYOUT_MP_WEEKLY_FINAL 기준 미수정(통제 판단 대기)"
- 코드 근거: 캘린더 대조는 구현됨 — S/settlement_verify.py:216-229 `paydates`, S/settlement_verify_collect.py:41. 그러나 골든은 그대로다 — designs/coupang_golden_cases.json:16 `"expected": "2025-03-01", "why": "익익월 1일, 토요일이어도 보정 없음"`, S/payout.py:16·:25·:80 `month_final_calendar`(보정 없음). D-007 근거의 실측(8/1 토→08-03, 11/1 일→11-02)과 반대. 이 규칙의 날짜 계산은 운영 src에서 윙 대조에 쓰이지 않음(`WEEKLY_FINAL` 검색 결과 src의 바깥 사용은 settlement_stats.py:229·:251 `payout_amount` 금액뿐).
- 미결 추적: `골든|PAYOUT_MP_WEEKLY_FINAL` 검색 결과 STATE.md 0건, DECISIONS.md는 57·58행뿐 — 판단 대기 건이 어디서도 추적되지 않음.
- 물어볼 것: 골든·`month_final_calendar` 규칙을 '다음 영업일 보정'으로 고칠지, 캘린더 정본이므로 규칙 자체를 지울지, 그대로 둘지.
- 제안: 소유자 답을 받아 새 D항목. 그 전까지 STATE 미해결에 등록.
- 확신도: 중간(결정 자체 OK는 높음)

### D-009 [AI_MATCH_ANCHOR]
- 판정: MARK_MISSING (부분, D-011) + 소유자 확인 1건
- 원문 인용(69행 D-009): "③**AI 선택**(줄마다 후보 추림·등록명/노출명/옵션/판매상태·글자 규칙 결과는 참고 후보·같은 종류 없을 때만 null)"
- 원문 인용(83·85행 D-011): "글자 규칙 결과는 AI 에 **보여 주지 않음**", 버린 대안 "(a) 글자 규칙 결과를 '규칙 후보'로 AI 에 표시(D-009 초안 — 글자 쏠림)"
- 참고: D-011 86행은 "D-009 의 ③ 세부를 보완(D-009 는 ACTIVE 유지)"라고 적었다. 그러나 위 두 세부(글자 결과 표시·줄마다 추림)는 뒤집힌 것이다.
- 코드 근거: S/product_match_ai.py:357-371 `_candidate_ids` 150개 이하 전부 전송·독스트링 "규칙 결과(놓침 방지·표시 안 함)", tools/verify_offline.py:743 `"규칙 후보" not in calls[-1]`. 그 밖의 D-009 핵심은 현행: :192 `_apply_anchors`(사라짐·판매중지 재매칭·스냅샷), :31 `ANCHOR_CONF`, :293 `_resolve_conflicts`, S/product_match.py:337 `build_tracked`. 삭제 대상 `augment_unmatched|augment_ai|_augment_vids|_augment_ai_match|kw_ai.match_products` 검색 0건.
- 제안: D-009 상태 줄을 `ACTIVE (부분 SUPERSEDED by D-011 — ③의 글자 규칙 후보 표시·줄마다 추림)` 으로.
- 소유자 확인: D-009 ④(AI 장애 시 글자 규칙 대체, :290-291)·D-011 ①(이름 동일이면 AI 없이 확정, :230)은 전역 규칙 '매칭 기본 = AI 매칭(2026-10-27)'의 "결과를 그대로 확정하지 않는다"보다 앞선 소유자 결정이다. 전역 규칙이 앱 런타임 매칭에도 적용되는지 물어야 한다. 앱 런타임은 범위 밖일 수도 있어 어긋남으로 판정하지 않음.
- 확신도: 중간
- 비고(FALSE_POSITIVE): `output/_매칭고정.json`=실행 중 생성(S/match_anchor.py:17 `ANCHOR_FILE`). `woolins_vendor_inventory`=근거 문장의 원문 파일명. 69·72행 `scope_to_ledger`는 D-023이 지운 이름이 영향 범위 곁말로 남은 것.

### D-010 [SETTLE_LIFECYCLE]
- 판정: MARK_MISSING (상태 줄 보강, D-075)
- 원문 인용(80행 상태 줄): "SUPERSEDED by D-021(기동 시점·종료 규칙 — 18:00 이전 앱·정산 종료·예약작업 제거·HTTP 500·윙 'M' 처리는 D-021 에서 유지)"
- 원문 인용(D-075 결정): "'M'·'MONTHLY' 를 건너뛰고 '확인 필요'로 남기던 D-010/D-052 의 해당 부분을 대체."
- 코드 근거: S/settlement_wing_api.py:36 `_WING_KIND = {"W": "주정산", "R": "최종액", "M": "월정산"}` — M은 이제 받는다. :39 `_WING_UNSUPPORTED = {"B": "추가정산"}`. D-052는 같은 대체를 상태 줄에 표기했는데 D-010만 빠짐.
- 제안: D-010 상태 줄 끝에 `· 윙 'M' 건너뜀 부분은 SUPERSEDED by D-075(월정산도 받음)` 추가.
- 확신도: 높음
- 비고(FALSE_POSITIVE): `output/정산/로그/_완료.json`=실행 중 생성(tools/settlement_download.py:688 `DONE_FILE`).

### D-012 [LEDGER_PW_CANDIDATES]
- 판정: STALE (의도적 변경, 대체 결정 있음 — D-022 B1·D-023)
- 원문 인용(90행): "단일 값 API(`parse_password_rows`·`parse_password_file`)는 마지막 줄 → 첫 후보로 변경."
- 원문 인용(D-022 168행): "B1(ui/app.py·parse_password_file)·B2(tools 일회성 10개) 완료" / (D-023 172행) "나머지 B4(`scope_to_ledger`·`parse_password_rows`·`proxy_manager` 미사용 메서드 12개+`active_count`)는 삭제."
- 코드 근거: `parse_password_rows|parse_password_file` 검색(src·ui·tools·deploy) 0건. 핵심 동작은 현행 — S/input_list.py:225, S/pipeline_sales.py:192 `PW_MAX_TRIES = 2`·:195 `_pw_list`·:203 `_login_with_candidates`, ui/app_qt.py:1254 `_account_pw`. D-068·D-123은 거부 값 건너뛰기·공백 정리를 더한 보완이고 D-012를 뒤집지 않음.
- 제안: D-012 상태 줄을 `ACTIVE (부분 SUPERSEDED by D-022·D-023 — 단일 값 API 삭제)` 로. 핵심은 ACTIVE 유지.
- 확신도: 높음(사실), 낮음(표기 필요성 — 곁가지 문장이라 표기 생략도 가능)

### D-015 [EXPOSED_NAME_STRICT]
- 판정: MARK_MISSING (부분, D-051)
- 원문 인용(111·114행 D-015): "출처 순서: ①당일 판매분석 → ①최근 30일 판매분석 보충 → **③순위 검색결과…", "⚠ 판매중지(순위 제외)이면서 30일 판매·조회도 없는 상품은 노출명을 얻을 경로가 없어 오류 기록만 남음."
- 원문 인용(D-051): "D-015 출처 순서 = 당일 판매분석 → 최근 30일 판매분석 → **윙 상품수정 화면 `displayProductName`** … → 그래도 없으면 ❌ + ③ 검색 노출명."
- 코드 근거: S/pipeline_sales.py:498-520 `_fill_exposed_names` → `_fill_from_roster` → `_fill_from_modify_page` → ❌ 기록. S/pipeline_ranks.py:766 `rename_to_exposed`는 유지.
- 제안: D-015 상태 줄을 `ACTIVE (부분 SUPERSEDED by D-051 — 출처 순서에 윙 상품수정 화면 추가·⚠ '경로 없음' 문장 무효)` 로.
- 확신도: 중간(D-051이 '추가'로 표현하므로 보완으로 볼 수도 있음)

### D-016 [DESIGNATED_DATE]
- 판정: MARK_MISSING (부분, D-032)
- 원문 인용(118행 D-016): "오늘 다른 날짜로 진행하던 작업은 이어받지 않음(`plan_run_mode(designated=True)`). '오늘'·무인·재개 실행은 기존 동작 그대로"
- 원문 인용(D-032): "**날짜 칸(date_label)이 이번 실행 칸과 다르면 이어받지 않는다** — 날짜 지정뿐 아니라 '당일' 전체실행·18:00 무인(`start_auto`)도 공통."
- 코드 근거: S/pipeline.py:111-112 독스트링 "날짜 지정·당일·무인 공통 … designated=True … 는 안내 문구만", :123 분기가 designated와 무관, :129는 문구 선택뿐. 재부팅 복구는 D-032도 '변경 없음'. 그 밖의 D-016 핵심은 현행: :149 `column_dates`, S/pipeline_ranks.py:243 `_rank_date`, S/workbook_dates.py:22·:53, ui/app_qt.py:878·:1525.
- 제안: D-016 상태 줄을 `ACTIVE (부분 SUPERSEDED by D-032 — 다른 칸 진행분 불이음은 designated 전용 아님·당일·무인도 공통)` 로.
- 확신도: 높음

### D-021 [SETTLE_CYCLE]
- 판정: MARK_MISSING (부분, D-075)
- 원문 인용(158행): "HTTP 500=서버 일시 오류·윙 'M' 건너뜀 등 D-010 의 처리 규칙은 그대로."
- 원문 인용(D-075): "'M'·'MONTHLY' 를 건너뛰고 '확인 필요'로 남기던 D-010/D-052 의 해당 부분을 대체."
- 코드 근거: S/settlement_wing_api.py:36 M=월정산. 나머지 핵심 현행: S/settlement_watch.py:34-46, tools/settlement_download.py:747·:772, ui/app_qt.py:2066-2067. D-055(`--since`)·D-091(`already_done`)은 보완이고 D-021을 뒤집지 않음.
- 제안: D-021 상태 줄을 `ACTIVE (부분 SUPERSEDED by D-075 — 윙 'M' 건너뜀 문구)` 로.
- 확신도: 높음
- 비고: S/settlement_watch.py:9-14 독스트링에 D-010의 '①이 끝나면 앱이 정산을 띄운다'·'중단되면 종료'가 그대로 남음(동작은 :112 'later'로 D-031 반영). tools/settlement_download.py:761 설명도 같음. 주석 정리 후보.
- 비고(FALSE_POSITIVE): `_실행단계.json`=실행 중 생성.

### D-022 [CLEANUP_SCOPE]
- 판정: MARK_MISSING (부분, D-035·D-037·D-038)
- 원문 인용(165행 D-022): "유지 = 수동 탭 4개…·신규 도메인(통합앱 셸·계약·채권자·업무일지·CS·소싱 — 나중 연결)"
- 원문 인용(D-037): "HQ D0 가 이전을 마친 통합앱 자산을 R0 에서 물리 삭제한다 — `ui/app_integrated.py`·… `contract_store.py`·`worklog_store.py`·`cs_model.py`·`cs_store.py`·`cs_gsheet.py`·`creditor_store.py`"
- 코드 근거: 위 파일들 ui/·src에 없음(`ls`). designs/FEATURE_INVENTORY.md:107 "HQ(`D:\commerce-hq`)로 이전·R0 에서 물리 삭제(D-037)". 소싱만 남음(S/sourcing.py). D-022 168행의 'reusable_coupang 소유자 확인 대상'도 D-038에서 해소.
- 제안: D-022 상태 줄을 `ACTIVE (부분 SUPERSEDED by D-037·D-038 — 통합앱·계약·채권자·업무일지·CS 유지 → HQ 이전 후 삭제·reusable_coupang 삭제)` 로.
- 확신도: 높음
- 비고: D-022의 '로컬 사본 폴더(git 밖)'는 저장소 루트에 `src - 복사본`·`login_source_260904`가 남아 있음. 소유자 확인 건이 끝났는지는 미확인.

### D-024 [CLEANUP_B6_MERGE]
- 판정: MARK_MISSING (부분, D-091)
- 원문 인용(179행 D-024): "④18:00 마다 옛 정산 예약작업을 지우던 코드 삭제(install.ps1·자동실행_삭제가 계속 지움)."
- 원문 인용(D-091): "`app_process.prepare_auto_start`(18:00 무인 시작)가 `remove_legacy_settlement_task` 로 인자 'watch' 예약작업을 지운다"
- 코드 근거: S/app_process.py:186 `remove_legacy_settlement_task`·:205 호출 — D-024가 지운 함수가 D-091로 되살아남. 이유(D-091 근거): 폴더 덮어쓰기 업데이트로는 옛 작업이 남아 매일 08:00 정산이 돌았다. 나머지 현행: S/pipeline_stages.py:40 `run_stages`, S/power.py:29, S/app_process.py:168 `stop_settlement`, deploy/정산_지금실행.bat 없음.
- 제안: D-024 상태 줄을 `ACTIVE (부분 SUPERSEDED by D-091 — ④ 18:00 옛 예약작업 제거 복원)` 으로.
- 확신도: 높음
- 비고(FALSE_POSITIVE): `deploy/정산_지금실행.bat`·`정산_지금실행.bat`=D-024가 지운 파일(없는 게 정상). `deploy/첫실행_설정안내.txt`=실제 존재(`git ls-files deploy` 확인, 프로그램의 한글 경로 오탐으로 보임).

### D-030 [RANK_NO_HALT_VID_REQUIRED]
- 판정: MARK_MISSING (기존 부분 표기에 범위 추가, D-053·D-057·D-090)
- 원문 인용(223행 D-030): "`drive_rank` — 회전 횟수 제한 없음·풀 한 바퀴 뒤엔 차단 이력 IP 도 재사용·끝=남은 키워드 없음·중지 요청·프록시 설정 오류", "프록시 OFF/회전 불가면 **쉬지 않고 다음 키워드**(막힌 칸 공란 → 다음 실행이 채움)"
- 원문 인용(D-057): "차단 판정(차단 페이지) 난 (주소, egress IP)는 그 주소가 아직 같은 IP 를 주는 동안 **검색하지 않고 건너뜀**", "한 바퀴 동안 검색한 주소가 하나도 없으면 … 5분 대기"
- 원문 인용(D-053): "**남은 빈 칸만 다시 도는 바퀴**를 빈 칸 0 또는 중지 요청까지 반복", "남은 칸을 ❌ 로 기록하고 마침" / (D-090) "성공 없이 IP 불량이 15번 이어지면 … ③ 마침"
- 코드 근거: S/pipeline_ranks.py:169-171 `skip_blocked=prog["round"] == 1`·`skip_pairs=prog["pairs"]`(72시간 이력 IP는 2바퀴째 재사용 유지, 이번 실행에 막힌 주소·IP는 금지), :193-201 `_next_round` 5분 대기, :628-644 `_semi_next_pass`(프록시 없어도 다음 바퀴), :803 `_DEAD_STREAK_STOP`. 그대로인 핵심: `_rank_matcher` :219, VID 없음 ❌ :724-729, 쿨다운 상수 3종 검색 0건.
- 제안: D-030 상태 줄 범위를 `ACTIVE (부분 SUPERSEDED by D-053·D-057·D-090 — 막힌 키워드부터 → 다음 키워드·이번 실행에 막힌 (주소,IP) 재사용 금지·프록시 없을 때 공란 방치 → 바퀴 반복·끝 조건 추가)` 로 넓힘.
- 확신도: 중간(현재 표기가 D-053 일부만 다룸)
- 비고(주석 잔재, 동작 무관): S/config.py:55 '쿨다운/회전', :336-337 "회전 소진/무효일 때만 기존 쿨다운→당일중단", S/config.py:108 `RANK_BACKFILL_COOLDOWN_SEC` 정의만 있고 사용처 0건, S/pipeline_stages.py:66, ui/app_qt.py:1636·:1649, S/pipeline_ranks.py:504 '쿨다운 대기 중'(지금은 5분 대기에 쓰는 문구). 현행화 후보.

## 3. 확인 필요(판정에는 영향 없음)

1. D-001 — 저장소 루트 HANDOFF.md가 남아 있다. 마지막 커밋 2026-09-14로 D-001 이전이며 "새 세션 읽기 순서: 이 문서"라는 안내를 그대로 담고 있다. CLAUDE.md:5는 STATE.md 한 곳이라 적었다. 동결 자료로 둘지 지울지 소유자 확인 필요. 확신도 중간.
2. D-004 — 운영 공휴일 집합에 2026-05-01·07-17이 들어가는지 코드로 판정 불가. S/settlement_store.py:151 `load_holidays`는 특일정보 API+캐시만 쓰고 `extra`를 넘기지 않는다(`extra=` 검색 결과 호출 0건). tools/verify_settlement_runtime_offline.py:559-560은 시험용 주입이다. 이 PC에는 `output/_holidays_2026.json`이 없어 운영 값 미확인. 운용 PC 캐시 파일 확인 필요. 확신도 낮음.
3. D-028 — 208~209행 원문이 "`output" 와 "un_log_*.log`)" 로 끊겨 있다. 추정 원인은 `output\run_log`의 `\r`이 줄바꿈으로 들어간 것. 추가 전용 규칙상 본문 수정 대상 아님. 색인·블록 파서가 이 줄을 잘못 읽지 않는지만 확인 권장.

## 4. 프로그램 후보 오탐 정리

- D-020 `output/정산/로그/_앱정상종료.json`: 실행 중 생성(S/app_process.py:97).
- D-025 `정산_상태확인.bat`·`첫실행_설정안내.txt`: deploy/ 아래 실제 존재.
- D-026 `missing_idents` 12개: 결정이 지운 이름. `_index`는 지워진 ProxyManager 필드이며 S/workbook_index.py:196 `_index_row`와 무관.
- D-027 `tools/test_rank_images_live.py`: 결정이 지운 파일. `deploy/install_schedule_py.bat/.ps1`: 두 파일 묶음 표기를 경로로 오인.
- D-029 `_night_resume`·`night_resume`: 결정이 지운 이름.
- D-008·D-016 `mentioned_by`(D-040·D-084): 인용일 뿐 대체 아님.
