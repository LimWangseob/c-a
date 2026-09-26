- [✅결과파일 이미지 9이슈 정밀분석+조치(2026-09-26·라이브 남음)](handoff-9issues-images-260926.md) — 상품군 그룹키=**블록명 base**(레몬버베나/식기건조대 등록명 드리프트→같은색·인접)·판매가/판매상태 지표행 **자가치유**(옛 블록 13개)·빈 키워드행 **낡은순위 삭제**(43행)·비고 소헤더=**대장 판매상태**(판매중/판매중지·has_keyword_section 판정 A열만으로 수정)·**상품명 하이퍼링크=vendorItemId 기반**(⭐라이브 실증: `/vp/products/0?vendorItemId={vid}` 가 vid만으로 상품페이지 열림·productId 불필요·상품조회 응답엔 공개 pid 0/20계정·pid는 정규 URL용만 판매분석∪재고서 유지→**미입고 RFM·판매자배송까지 커버**·기존마스터 링크 88→109). 게이트 7종+복잡도 초록. 핀 pin_apply_style[S9]·verify_offline[14]·verify_render[항목2].
- [✅라이브 400 버그수정: 계정목록 열이동↔제목병합(2026-09-26)](fix-gsheet-movedimension-merge-400.md) — 운용PC 새코드 첫실행서 계정목록 동기화 400(Invalid requests[0].moveDimension): ④열이동이 제목병합(A1:I1) 가로질러 Google 거부. 수정=`_ensure_column_order` 병합해제→이동→재병합 한 배치(+옛8열 N_COLS 확장). FakeClient에 병합제약 모델링해 재현·핀 verify_gsheet[11]. 로컬/통계는 정상·계정목록만 미갱신이었음(무손실). 우회=계정목록 탭 삭제→full_build 재생성.
- [✅다계정ID reconcile 교차오염 버그수정 + 정밀렌더검증(2026-09-26)](fix-multiaccount-reconcile-scope.md) — 정밀 시뮬(verify_render_precision.py·셀단위 29항목 end-to-end)이 실제 버그 포착: 한 사업자 다계정ID에서 계정B 처리가 계정A 상품 판매중지/삭제(실운용=데이터유실)→`reconcile_account(account_id=)` 스코핑(product_account_id 그 계정만 대조). 핀 verify_offline[24]·run_checks 7번째 게이트 편입. 교훈=다계정ID 시트단위 순회는 계정ID 스코핑 필수.
- [✅통계 상품명→쿠팡 링크 + 6요구 정밀분석(2026-09-26·라이브 남음)](feature-product-coupang-link.md) — ③신규: 통계 시트 상품명 클릭→쿠팡 노출상품 새 창(productId 정확/없으면 노출명 검색 폴백·순위 SERP서 productId 캐치·메타 col13·gsheet 외부링크 =HYPERLINK 미러). ⑤제목 순서 대표자·사업자·계정ID+다계정 모두. ①통계 gsheet=셀단위 자동미러라 구조변경 불필요. ②④⑥ 구현확인+핀. pin_apply_style[S9]·verify_gsheet[t5]·verify_offline[17·23]. 마케팅 픽스처 날짜롤오버 안정화.
- [✅항목5 사업자명 기준 그룹핑 구현(2026-09-25·라이브 남음)](feature-business-name-grouping.md) — 같은 사업자명 다계정ID=한 시트·계정ID를 상품(줄) 속성(_상품ID col12)·판매수집 스탬프 계정 단위화(_수집스탬프, 둘째 계정 스킵 버그 해결)·검증 완화([SYNC] 경고)·계정목록 밴드 사업자명 기준·일원화 다계정 인지(발산=보류+경고). 커밋 S1~S5·핀 verify_offline[17·18·19]·verify_gsheet[6b]·게이트6+복잡도 초록. 소유자 확정=그룹키 사업자명만·계정마다 따로 수집.
- [✅시트명 변경 계정 자동 일원화+구글시트 계정목록 연동(2026-09-25·라이브 남음)](feature-account-consolidation.md) — 대장에서 담당자가 사업자명 바꾸면 계정ID 동일·시트만 옛 이름=고아(판매중지 오분류·키워드 공란). `merge_account`(rename or 이력보존 병합)+`_consolidate_renamed_accounts`가 `_reconcile_ledger_accounts` 맨 앞에서 대장 계정ID 기준 **전 계정 매 실행 자동 병합**(이종훈→원더폴리 등). **구글시트 계정목록·통계 시트도 연동**: `delete_renamed_accounts`가 옛 이름 행+옛 통계 시트 제거(⚠매칭키=사업자명B+계정ID D 동시일치, 공유 계정ID로 지우면 새 이름·직원마케팅 E~G까지 삭제됨). 일회성 수술 불필요·다음 실행 자동. verify_offline[16]·verify_gsheet[3e]·게이트6+복잡도 초록.
- [✅상품 블록 레이아웃 v4 구현 완료(2026-09-25·라이브 남음)](handoff-block-layout-redesign.md) — 좌측 A:B=라벨 칸(상품명2·VID·판매방식·로켓그로스3)·C:F=값·상품군 색을 라벨 칸에. **vid=메타 col3**(A안·옛 마스터 헤더꼬리 폴백)·**판매방식=메타 col11**(product_kind)·`_display_name`=상품명만·**키워드명 C→A열 좌측확장(A~E)**. 3단계 커밋(ed313fc·79d7290·+키워드)·게이트6+복잡도 초록. 핀 S1·S2·verify_offline[7][12]·simulate _keywords_in 갱신. ⚠**재배포+재실행 라이브 확인 남음**.
- [✅3대 최종결정 구현·커밋(2026-09-24)](handoff-3decisions-260924.md) — ①계정목록=**대장상태만**(productStatus 폴백 제거·2026-09-22 되돌림) ②계정목록 **I열 '체험단효과'** 신설(체험단 시작일 **직전값→최신값 점비교**·판매%·최고순위 32→18↑·개선초록/악화적색/부족공란·E~G 미접촉) ③관리대장 **로켓그로스 입고 7컬럼→헤더 '최근입고' 요약**. 게이트 6종+복잡도 초록. 핀 verify_offline[13]·verify_gsheet t6·pin_apply_style S7. ⚠라이브 확인·재배포 남음.
- [⭐분석: 구글시트 중복리스팅 분리·판매상태/판매정보 공란(2026-09-24·수정보류)](analysis-gsheet-dup-listing-260924.md) — 26계정 183블록 정밀분석. 근본원인=중복/재등록 리스팅(한 상품이 4~5 vid로 쪼개짐). **판매상태 공란 28·판매정보 공란 42.** 고칠 것 2건: **A**=중복 블록 상품단위 합침(설계결정·미결) / **B**=`pipeline.py` `sale_status=vendor if vendor else rfm` all-or-nothing 갭→`vendor∪rfm` 병합(재고엔 있고 상품조회 없는 vid 상태 공란·명확 코드갭). 소유자 지시=**분석만·수정 보류**. 배포 개정(미입고·판매상태행·업번들sweep)은 라이브 정상.
- [✅재고칸 규칙 개정 2건 구현 완료(2026-09-24)](handoff-gsheet-inventory-followup.md) — **Fix A**: 재고=판매중지 무관 재고현황 있으면 값·**없으면 항상 미입고**(`_block_sellable` 물리제거) + **판매상태=상품블록 '판매상태' 지표행에 실행일마다 기록**(소유자 선택·쿠팡 존중·`M_SALE_STATUS`·`_block_sale_status`). **Fix B**: 업번들 잔재 **매 수집시 vid 기준 자동삭제**(`_purge_upbundle_blocks`·배선 _discover→_finish→_process_account). 게이트 6종+복잡도 초록. ⚠**라이브 확인·커밋/푸시/빌드 남음**. 배경=웰빙곳간 제한계정 all-SUSPENDED로 재고 텅빔.
- [⭐⭐재고 공란 조사(2026-09-24) 근본원인 확정·진단 보강 커밋](handoff-inventory-blank-260924.md) — 원인 확정: **VID(vendorItemId)는 유일하나 같은 실제 상품이 여러 vid로 쪼개짐**(①중복/재등록 리스팅 ②가상번들). 캡처 실증(bf0621: 같은 pid 9004991148에 vid 3개·재고 13/0/0). **productId(진짜 상품단위)는 재고 API에만·상품조회엔 없음**. 결과파일 재고공란=추적 vid 188중 108(판매자단독 4=오탐). **✅진단 보강+원본(raw)통째보관 푸시(c269ae3)+재빌드**(dist zip 2026-09-24 07:44): 3API(상품조회·재고·판매분석) 응답 원본을 가공없이 `output/_raw/{계정}_{api}_p*.json.gz` 저장(재빌드없이 오프라인 분석)·run_log는 [C]집합·[D]productId그룹핑 요약만. **다음=소유자 운용PC 재배포→redo_today→_raw 원본으로 상품단위 확정→수정(재고=합산vs대표·표시=합침vs분리, 소유자 결정).** 미푸시 0.
- [상품명 규약: 대장=담당자명·결과=노출명](product-name-convention-ledger-vs-result.md) — 오래전 확정. 결과파일(계정목록/통계)의 긴 이름=쿠팡 노출상품명(정상). "짧은 대장명과 달라서 낡았다"고 오판 금지. 소유자 2026-09-23 재확인.
- [A·B·D 진행(2026-09-23)](fixes-abd-260923.md) — A-1 재링크 도구(tools/relink_index.py·전체실행 없이 계정목록 링크만 재작성)·B-1 순위 종료 요약+45~75 되돌림 권고(핀 J·K)·D는 라이브 불가로 diag_inv_hidden.py 진단만(안전판 수정 보류). 설계서=designs/FIX_ABD_260923.md. ⚠pytest Stop훅 오탐(테스트0=exit5=차단)·훅 exit5 통과 한줄 추가는 소유자 직접(Self-Modify 거부).
- [⭐⭐인수인계: 코드 건강 정비(2026-09-22)](handoff-code-health.md) — 소스 누더기·회귀반복 진단 완료. 썩음=4파일 집중(pipeline·workbook·app_qt·app, radon MI C)·괴물함수·죽은코드 아님. **✅단계1·2 완료**(회귀 게이트 훅+결정적 모킹+규칙). **🔄단계4 pipeline.py: run_full F75→C15·_process_account F72→C18·✅_login_and_discover F54·_track_ranks_semi F45 분해 완료**(커밋 05ac18b~5e6185e). **⭐⭐마일스톤(2026-09-22): 4개 나쁜 파일(pipeline·workbook·app_qt·app)의 D/E/F 괴물함수 전멸(전부 C 이하·`radon cc -n D`=빈결과).** pipeline(run_full·_process_account·_login_and_discover·_track_ranks_semi·track_ranks_stage·select_keywords_stage)·workbook(apply_style F52·_build_index·normalize_date_columns·set_display_name)·app_qt/app(do_run_full E33/34→C, 실행모드 로직 plan_run_mode/run_title/run_log_labels 백엔드 공통화). 핀 3개 신설(pin_login_ranks 16시나리오·pin_apply_style S1~6·pin_run_plan P1~7). **게이트=run_checks 6종**(quick 5종). 커밋 3479c50~8f5e810. **✅라이브 ①(로그인·발견) 통과(2026-09-22 사무실 nicoable)** — 분해 코드 프로덕션 정상(로그인·상품조회7·판매분석23옵션·재고21·판매상태15[판매중9/중지4/부분2]·미매칭3보강·대장3전건). 도구=verify_login_discover_live.py <계정ID> --semi. **남은=(1)4파일 MI C→B 모듈 분리(대형파일 포화·가로채기 재배선 위험) (2)③순위 라이브(핫스팟)**. ✅별도 발견 해결: 구글시트 입력 관리대장 403(SA 미공유)이었으나 SA 편집자 공유로 정상('셀독리스트' 27계정 gsheet 직접 로드 확인). 결과 통계 시트와 입력 대장은 별개 스프레드시트. 새 세션은 designs/CODE_HEALTH_PLAN.md 먼저.
- [⭐⭐세션 인계(2026-09-23) 소스점검+수정 전부 푸시·zip 재빌드·소유자 수동재배포](bugfixes-260923-source-review.md) — **전부 origin 푸시(HEAD=1c2330a)·미푸시0·게이트초록·배포zip 재빌드완료·소유자 어제분 수동 재배포 완료**. ✅A-1(순위 미발견='{센개수}위밖')·A-4(연말 날짜폭발)·A-3(중복라벨 값유실)·B-1(재개 라벨복원 공통화)·B-2(동시실행 가드)·일자컬럼 내림차순(최신=H열)·재고공란=오류로그+공통함수 _ilog(vid필수)·상품군 배경색교대(살구↔민트)·build.bat 괄호버그·보안제외 bat CP949(한글Windows 깨짐). ⏳남음=A-2(NORMAL 고유옵션·라이브 확인후)·기타 deploy bat 인코딩(다음에). **어제 9/22 분석**: 18:00 무인크래시=Defender 오탐 exe격리(코드버그아님·폴더제외로해결·"18:00즉시닫힘" 규명)·19:53 정상완주(순위 81% 옛"50위"버그).
- [⭐⭐새 세션 인계(2026-09-23)](session-handoff-260923.md) — 오늘 완료(P1재고=현재코드해결·P2순위=판매중만·P3판매상태 검토중까지·P4링크 현재코드정상·배포 Defender대응·무인 06:00 강제종료 폐지·순위간격 35~55)·전부 푸시(8e89b95·미푸시0). **최우선=운용 PC 재배포**(지금 도는 건 옛 코드·배포 zip 준비됨). 남은=계정목록 링크 재작성(실행 끝난 뒤)·35~55 차단 모니터·③순위 핫스팟.
- [⭐보완 7건 수정(2026-09-21 실행 분석)](followups-260921-run.md) — 어제 output.zip 실측 분석 후 P1~P4 적용(미푸시 83a057d·4ec65a1·48f41f9·41683c8). P1 재고=숨김옵션 포함(hiddenStatus VISIBLE+HIDDEN·라이브 확인 남음)·P2 판매중지 순위제외(rank_suppressed)·P3 임시저장/승인반려 정확표기·P4 구글시트 링크(현재코드 정상·재실행 자동복구). 옵션=분리유지·순위=판매중만. 남은=P1 재고 라이브 대조·③순위 핫스팟.
- [⭐인계: 소유자 9개 요구 정밀분석+계획(2026-09-25·미구현)](handoff-9items-spec-260925.md) — 시작 프리플라이트(싱크체크+백업)·계정목록 열순서(계정ID를 상품명 왼쪽)/폭·⑤**사업자명 기준 그룹핑**(다계정ID 사업자=한 시트, 계정ID=상품속성·아키텍처·오늘 일원화와 충돌조정)·⑥**이력무관 삭제**(정책전환·백업이 안전망)·⑦⑧상태싱크/이중비고(대장 vs 쿠팡)·⑨키워드 동결(1건이라도=담당자·가변개수). 진행순서 소유자확정=⑤부터. **새 세션·핀 먼저 구현**. 각 항목 오류추적 로그.
- [죽은 코드 물리 삭제(2026-09-25)](deadcode-cleanup-260925.md) — kw_shopping.py 모듈+app.py 네이버쇼핑키 흐름(수집만·백엔드 미전달=죽은 기능)·참조0 메서드 3개(clear_values·inventory_by_registered_name·_roster) 삭제(순66줄). vulture+전수참조 근거. **보류**: _backfill_ranks/_measure_unfilled_once=가드호출+모킹 있어 정책 결정 필요·백업폴더는 소유자 확인 후.
- [코드 건강 규칙(회귀 방지)](code-health-regression-gate.md) — 커밋/푸시 전 tools/run_checks.py 초록 필수(훅 자동·새PC install_hooks 1회)·테스트서 실API 금지(모킹, VERIFY_REAL_API=1 옵트인)·CC≤15/파일≤600·건강파일 미접촉·되돌림은 근거 메모.
- [⭐⭐인수인계: 18:00 실행 분석·버그2개(2026-09-20 밤)](handoff-260920-run-analysis.md) — 새 세션이 정밀 재분석+수정. **①fix③ 복원이 '계정목록'(공백없음) 탭 오염→계정목록 sync 400 ②복원+옵션분리 중복잔재(웰빙곳간 16상품→97블록·판매중지54)**. 근원=마스터가 없어 복원됨(작업폴더 변경 의심). ③순위=사무실IP 차단(핫스팟 필요·13/441만). 실파일=`output/_인수인계_260920/`. 오늘 커밋 8개 미푸시.
- [⭐현재상태(2026-09-20)](session-current-state.md) — 최신(2026-09-20-11): 옵션분리 후속 5건 + **키워드=구글시트 셀 값 기준**(이력보존 폐기·삭제=하드삭제·톱업없음·상한10) + **작업 전 자동 백업**(마스터+결과시트+관리대장→output/백업/). 커밋 ac12649·53174ef·7f6511d(미푸시). 실측: 시트에 담당자 키워드 편집 2건 대기(휴라엘)→18시 실행 반영. // 이전: VID출처 변경 **라이브 검증 완료**(사무실 다계정). vid출처=(A)헤더 이름칸·옵션분리·블록명=등록명+옵션라벨·set_display_name 중단·③=sibling_vids·vid변경시 이전데이터 삭제. **판매상태=productStatus**(ON_SALE→판매중·SUSPENDED→판매중지 등·화면 일치·판매자배송 커버·RFM 폴백)—처음 wellbing1107만 보고 되돌렸다가 다계정으로 재적용. 미매칭 3건 해결(알부민=대장 중복정책·퀘르세틴/루바브=규격 타이브레이커)→wellbing1107 14/17→16/16 전건매칭. 설치 스크립트 1개 통합. 다음=마스터 백업 후 앱 ① 라이브 실행(빌드 보류중).
- [날짜컬럼=실행날짜 규칙](date-column-run-date-rule.md) — 라벨=작업실행일, 순위=실행일·판매=전일(D-1) 같은컬럼, 미실행/중단일=날짜만+공란(연속유지), 과거는 그대로. date_label 배선·normalize_date_columns·tools/normalize_dates.py.
- [⭐핵심요구: 정확등수 매일](session-handoff-exact-rank-required.md) — 상품×키워드 정확 N위 매일(근사 불가). 거부됨=키워드중복제거·Wing노출신호. 해법=반자동.
- [✅대기 코드수정 5건 구현 완료(2026-09-20)](pending-code-fixes-next-session.md) — ①계정목록=상품별 1줄(`_is_secondary_option`+`_product_rows` 필터) ②동결키워드 검색량 네이버채움(`keyword_search`+`_fill_frozen_search_volumes`) ③마스터없으면 gsheet복원(`restore_master_from_gsheet`, UI가 master_exists 전 호출) ④변형상품 서식 그룹화(apply_style edge thick/thin) ⑤실행모드 용어. 오프라인 검증 통과·커밋 대기·라이브 확인 남음.
- [⭐VID 출처=상품조회/수정(1~7단계 구현 완료·라이브 확인 남음)](feature-vid-source-from-product-list.md) — vid를 POST vendor-inventory/search에서 상품명매칭. **vid 출처=(A)헤더 이름칸 'VID :'꼬리**(숨김 _상품ID vid 3열 폐지·인메모리 _block_vids). 옵션분리(다중옵션만·대표=첫옵션 키워드+순위·과거이력 승계·2차=지표만)·블록명=등록명+옵션라벨·③=sibling_vids(옵션 vid 합집합)·set_display_name 중단·둘다=RFM만·재고=RFM API·**판매상태=productStatus**(화면일치·판매자배송 커버·라이브 다계정 검증). 오프라인+라이브 검증 통과.
- [⭐판매상태 불일치 경고(구현완료)](feature-sale-status-mismatch-flag.md) — 대장=판매중지인데 쿠팡=판매중/부분판매중이면 실행날짜칸에 "판매중" 적색. **판매상태 소스=상품조회 productStatus**(ON_SALE→판매중·SUSPENDED→판매중지 등·화면 일치·판매자배송 커버·RFM 폴백). ⚠한 계정만 보고 되돌렸다가 다계정 검증으로 재적용(교훈=한 계정 판단 금지). 오프라인·라이브 검증 통과. 2026-09-17.

## 실행·운영
- [재부팅 자동복구](reboot-recovery.md) — 야간 Windows업데이트 재부팅 시 --resume(로그온 트리거)로 판매수집 스킵·순위부터 이어서. 단계마커 _실행단계.json. Windows 자동로그인 켜야 동작. 앱통합 완료.

## 작업 원칙(피드백)
- [분석 요청=코드 수정 금지](analysis-request-no-code-change.md) — "분석해줘"면 분석만, 명시 수정요청 전까지 파일 편집·커밋 금지.
- [진단명령=사용자PC 콘솔창 뜸](diagnostic-commands-pop-consoles.md) — 확인 명령 최소화, PowerShell은 bash로 감싸지 말고 직접(따옴표·한글 깨짐 방지).
- [쉬운 말·전문용어 금지](plain-language-no-jargon.md) — 군사·조어(재무장 등) 싫어함, 평범한 한국어로.
- [커밋=코드+설계서+메모리 동시](commit-with-design-and-memory.md) — 코드 커밋 시 DESIGN/HANDOFF·메모리 같이 갱신(누락 방지).
- [커밋마다 4묶음 자동화(무손실 인계)](commit-4bundle-automation.md) — pre-commit 훅이 외부 .claude 메모리를 `docs/memory/`로 미러링·스테이징(git 백업·세션/PC 바뀌어도 무손실)+코드 변경인데 DECISIONS.md 없으면 경고. SSOT=tools/install_hooks.py·sync_memory.py. 새 클론은 `python tools/install_hooks.py` 1회.
- [실측 근거 수정](fix-from-real-evidence.md) — 추측 금지, 진단로그+파일/이벤트 확인 후 실오류에 근거해 수정.
- [한글 일원화](respond-in-korean.md) — 모든 응답·산출물 한글.
- [판단 흐려지면 새 세션 권고](recommend-new-session-when-degraded.md) — 긴 세션 조짐 시 능동적으로 /clear 권고.

## 로그인·세션(정책)
- [로그인 정책 고정](login-policy-real-browser-only.md) — 실제 Chrome+CDP 자동입력만, HTTP 위장로그인 금지, 창 기본숨김.
- [로그인 2차인증=위치기반](login-2fa-location-based.md) — 사무실만 OTP 없이 통과, 집=2차인증(5회오류 계정잠금).
- [로그인 차단=세션우선+서킷브레이커](login-block-session-first-circuit-breaker.md) — Akamai 차단은 로그인 POST서 표면화, 세션있는 계정 먼저·연속3회 차단면 로그인 생략·무인로그인 한계.
- [쿠팡 세션 하루내 만료](coupang-session-short-lived.md) — 세션 재사용 무인수집 전제 깨짐, 매 실행 재로그인(사무실).
- [OpenAPI 불가(위탁운영)](coupang-openapi-not-available-consignment.md) — 위탁계정이라 판매자 API키 발급불가 → WING 세션이 유일 경로.
- [샵마인 아키텍처 실증](shopmine-architecture.md) — .NET+WebView2(실제 Chromium)+SQLite, 지문위조 아님, 세션영속+쿠키 HTTP 재사용.

## 입력·수집·데이터
- [입력=셀독 관리대장](input-ledger-format.md) — 헤더 2행·vid/pid 없음, 구글시트 원본, 취소선·상태컬럼으로 제외. 그로스재고 역기록(AD열·계정+등록명 유사도매칭).
- [대장 스코핑 추적](ledger-scoped-tracking.md) — 추적범위=대장 상품만, product_match.scope_to_ledger로 대장↔발견 매칭.
- [판매데이터 API 직접조회](sales-data-api-vi-detail-search.md) — vi-detail-search POST(x-xsrf-token), 지표매핑 확정, 당일 무활동 상품 vid 보강(라이브 검증됨).
- [재고현황 API(로켓그로스)](inventory-api-rfm-search.md) — inventory-health-dashboard/search POST, orderableQuantity=판매가능재고, 계약계정전용.
- [쿠팡 판매데이터 익일반영](coupang-sales-data-lag.md) — 당일 리포트 0행은 정상, 수집은 D-1 이전.

## 키워드
- [키워드 방법론(AI 앵커)](keyword-methodology-ai-anchor.md) — 4소스(네이버앵커+쿠팡자동완성+AI조합+2단계확장)→핵심/연관판정→Score→AI종합선정→순위진단→권고제목. AI=OpenAI. 형태단독어·정보성 배제. 띄어쓰기 변형 dedup(쿠팡 동일취급).
- [매일 통계·키워드 동결](daily-stats-keyword-freeze.md) — 첫날 동결(마스터 이어쓰기), 상한7·하루2 발굴추가, 직원입력 키워드도 동결.
- [네이버쇼핑 API 종료](naver-shopping-api-terminated.md) — shop.json 2026-07-31 종료·NaverShoppingApi 클래스 삭제 → 경쟁강도 소스 소멸.
- [Wing 키워드데이터 구독게이팅](wing-keyword-data-subscription-gated.md) — 순위(N위)는 Wing에 없음, 키워드별은 유료구독, 오가닉노출은 무료 1차데이터.

## 순위(노출조회)
- [파이프라인 3단계 분리](pipeline-3stage-separation.md) — ①판매수집(로그인) ②키워드선정 ③순위조회(②③ 로그인불필요·순위 예외격리).
- [순위 안티차단=서킷브레이커](rank-antiblock-circuit-breaker.md) — 트래픽최소화+서킷브레이커(cooldown 900s·MAX2), 검색간격 45~75s(config.py만). 2026-09-14 정책변경=마우스/스크롤 실제입력 허용. 지문/TLS 위조는 하드금지 아님·소유자 판단(밴위험 주의).
- [반자동 순위+정확 노출명](semi-auto-rank-and-exposed-name.md) — 앱이 자동입력+Enter·화면만 읽음(차단회피), 차단=쿨다운재개(1800×4), 간격 45~75s. 계약명=검색결과 정확명(vid 앵커).
- [순위 프라임 후 fetch](coupang-search-prime-then-fetch.md) — 콜드fetch 403, 검색1회 프라임 후 fetch(기본은 직렬 네비게이션).
- [쿠팡=붙여넣기 차단·타이핑만](coupang-blocks-paste-requires-typing.md) — 검색어 붙여넣기=차단, 한 글자씩 타이핑=통과(CDP IME 자모조합). type_dwell(글자수+2초).
- [순위 차단=50위 placeholder](rank-blocked-placeholder-50.md) — "50위"는 실제 50위밖과 차단/미측정 혼동 placeholder, 차단시 공란화(재측정).
- [지문 정합(1·2단계)](fingerprint-consistency.md) — 실제 Chrome153·webdriver false·전부 정합. 하드코딩 UA(150) 지뢰 제거·PC 네이티브 유지. 자동화흔적 이미 깨끗. **TLS/JA3·_abck 재생(3단계)=숙제로 보류**(A/B로 부족할 때만·재협의).

## 출력·구글시트·배포
- [상세페이지 이미지 추출(A안 CDP attach)](detail-image-extraction.md) — 사용자 실제 Chrome에 붙어 대표+상세 이미지만 DOM 스코핑 추출(새 프로필=사무실 IP 차단). src/detail_images.py, 라이브검증·앱통합 완료.
- [출력=셀독 서식](seldoc-output-format.md) — 시트=사업자, 계약/개인 상품블록, 키워드 노출순위(PC), 재고, 일자 가로, apply_style 서식고정, 제목 2줄(vid), 목차/마케팅 시트.
- [구글시트 통합 스펙](gsheet-unified-spec.md) — 입력=관리대장·출력=결과시트(계정목록 미러+통계). 계정목록 서식 개편됨(제목줄 단색·밴드 8색·판매중지색). SSOT=designs/GSHEET_UNIFIED.md.
- [exe 배포(다른 PC)](exe-packaging-deploy.md) — build.bat→PyInstaller onedir→**쿠팡애널리틱스_배포.zip**(폴더째). **무설정 설치**: 설정(구글시트 링크+네이버/OpenAI/구글SA 키) 자동 이식(export/import·평문 삭제). Chrome 필수. **자동실행 삭제 파일**=자동실행_삭제.bat(관리자)·remove_autorun.ps1.
- [실행 UI=app_qt·상시가동](runtime-ui-and-always-on.md) — app.py 아님, 설정탭=파일/API키+구글시트 카드만(순위 세부값 UI 없음·config.py만), 무인 --auto 야간모드.

## 참조
- [쿠팡 공식 운영지식](coupang-official-reference.md) — 상품등록·주문·배송반품·수수료·SEO/ID(productId 가변/vendorItemId 불변).
