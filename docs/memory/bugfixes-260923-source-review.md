---
name: bugfixes-260923-source-review
description: ⭐세션 인계(2026-09-23) 소스 점검+수정 전부 origin 푸시 완료(HEAD=1c2330a)·배포 zip 재빌드 완료. 소유자가 어제분 수동 재배포/실행 완료. 남은=A-2(NORMAL 라이브 확인)·기타 deploy 스크립트 인코딩(다음에).
metadata:
  node_type: memory
  type: project
  originSessionId: 62f4eccc-1971-4875-8bf8-d6b18239f39a
  modified: 2026-09-23T05:06:30.215Z
---

소유자 "전체 소스코드 점검해줘"(누더기·오류 빈번) 요청 → 4개 병렬 리뷰 에이전트(pipeline / workbook·collector / gsheet·input·match / UI·rank·kw)로 정적 정확성 리뷰.

**큰 그림**: 컴파일 0오류·임포트 0오류·게이트 6/6 초록. 구조 누더기는 이미 정리됨(괴물함수 전멸, `_semi_track_product`만 P2가드로 C20→D21 nit). "오류 빈번"의 상당수는 **운용 PC 옛 코드** 탓(재배포로 해소, [[session-handoff-260923]]). 그래도 현재 코드에 진짜 로직 버그 존재.

## 상태 스냅샷 — **전부 origin/master 푸시 완료(HEAD=1c2330a)·미푸시 0·작업트리 깨끗·게이트 6종 초록**
오늘 커밋: 7038ef9(A-4)·bbf5b2b(A-3)·0999c35(B-1)·4f498d2(B-2)·8a679f6(설계)·1d18c72(A-1)·de5fec6(날짜 내림차순)·817874c(재고오류로그+_ilog)·2e78b49(상품군 색교대)·15db9f4(build.bat 괄호수정)·1c2330a(보안제외 bat CP949).
- **소유자가 어제분(9/22) 재배포/실행을 수동으로 완료함**(2026-09-23 대화 말미). 위 최신 코드는 다음 실행부터 반영.

## 배포(재빌드 완료·소유자 수동 재배포 완료)
- **배포 zip 재빌드 완료**: `dist\쿠팡애널리틱스_배포.zip`(151.6MB·2026-09-23·exe=오늘 코드). zip 루트+폴더에 `0_먼저실행_보안제외.bat`. build.bat [4.5] 씨앗동봉 echo 괄호가 cmd if 블록 조기종료시키던 버그 수정(^( ^)·커밋 15db9f4).
- **보안제외 bat 인코딩 수정(1c2330a)**: 운용 PC(한글 Windows·콘솔 949)에서 `0_먼저실행_보안제외.bat` 실행 시 한글 줄이 명령으로 깨짐(UTF-8 파일+chcp 65001 이 949 콘솔서 파싱 전 안 먹힘). **CP949(ANSI 한글)로 재인코딩+chcp 949**. 설치.bat=비ASCII0(안전)·install.ps1=UTF-8 BOM(정상). ⚠ 이 파일은 이제 CP949라 Read 툴엔 깨져 보임(정상). 즉시우회=관리자 PS `Add-MpPreference -ExclusionPath 'C:\coupang-analytics'`.
- **재배포 순서**(참고): ①zip 복사 → ②**압축 전** 보안제외 bat 관리자 실행(또는 위 PS 한 줄)=Defender 폴더제외 → ③풀고 `설치.bat`(업데이트=덮어쓰기·output/data/config.json 보존). ⚠_설정값.json 평문키 외부공유 금지.
- 최신 코드 반영 효과: 순위 "50위"→"위밖"(어제 81% 가짜50위)·날짜 최신-왼쪽·재고오류 로그·상품군 색교대·재고 공란 대부분 해결.

## ✅ 소스 점검+수정 완료
### 코드 버그 5건(4개 병렬 리뷰 에이전트로 발굴)
- **A-1 순위 미발견 표기 '50위'→'{센 개수}위밖'**(1d18c72): `workbook.py:1063`이 못 찾음(rank=None)을 "50위"로 써 값 역전. DESIGN §5·config 주석엔 원래 "50위밖"인데 구현이 '밖' 빠뜨림. **소유자 결정(2026-09-23): 고정 50 아니라 그 페이지에서 실제로 센 오가닉 개수**(반자동=로드된 1페이지만 읽음)로 '44위밖'·'59위밖' 표기. 구현=`parse_serp_rank`가 `(result, scanned)` 반환→`_semi_record`가 `set_keyword_rank(scanned=)`→`f"{scanned}위밖"`(scanned 없으면 '50위밖' 폴백·자동경로도 정정). 미발견='위밖'으로 채워 같은 날 재검색 안 함(차단/미측정만 공란=재측정). 핀 pin_login_ranks[J2]·verify_offline[3]. **깊이 100 확장은 소유자가 안 함**(반자동 안전=1페이지만·다중페이지=차단위험). [[rank-blocked-placeholder-50]] [[semi-auto-rank-and-exposed-name]].
- **A-4 연말/연초 날짜 컬럼 폭발**(7038ef9): `workbook._parse_date`가 '월.일'을 무조건 올해로 해석 → 1월에 '12.30'을 올해12월로 오인 → 정규화가 1~12월 ~363칸 폭발. 수정=`_nearest_year(month,day)`(작년/올해/내년 중 오늘과 최근). 핀 verify_offline[14]-A.
- **A-3 같은날 라벨 2형식 값 유실**(bbf5b2b): 정규화가 같은 날짜 **첫 컬럼만** 스냅샷 → 옛('26.09.14')+신('09.14') 2컬럼 공존 시 오늘값 유실. 수정=`_rebuild_date_grid`가 date2cols(전 컬럼)에서 **최신 비어있지 않은 값** 보존. 핀 verify_offline[14]-B.
- **B-1 재개 날짜라벨 복원 백엔드 공통화**(0999c35): app.py엔 있고 app_qt엔 없던 `dlabel=meta.date_label` 복원 → `plan_run_mode`로 이관(RunPlan.date_label). 당일·기간모드 재개 시 app_qt가 판매데이터를 오늘 컬럼으로 어긋나 넣던 버그 해소. 핀 pin_run_plan P1·P4.
- **B-2 동시실행 가드+중지버튼 스코핑**(4f498d2·app_qt만): `_on_finish`가 아무 작업 종료에도 track_stop_btn 무조건 끔(파이프라인 못 멈춤) + 브라우저 실행 중 순위/키워드 버튼 미잠금(WingBrowser 동시 개방=프로필충돌). 수정=`run_bg(exclusive=True)`+`_guard_busy()`(5핸들러)+`_on_finish`는 `btn is _active_btn`일 때만 종료처리. app.py는 이미 정상이라 미변경.
- 설계 반영(8a679f6): DESIGN §일자 컬럼에 A-4·A-3 명시.
- **일자 컬럼 내림차순=최신 왼쪽 H열**(de5fec6·소유자 요청·버그 아닌 기능변경): 최신 날짜가 항상 H(맨 왼쪽)에 와 틀고정(H2)으로 스크롤 없이 보임. normalize가 연속일 만든 뒤 reverse. `latest_date`·`product_latest_date`를 **날짜값 기준**으로(물리 컬럼 아님) — 안 고치면 순위/재고가 오래된 칸에 기록됨. 구글시트·틀고정 자동반영. 핀 verify_offline[14]-C. [[date-column-run-date-rule]].

## 어제(9/22) 실행 로그 분석 결과 (run_log_260922_195324.zip)
- **18:00 무인 크래시 원인 = Windows Defender 오탐 자동격리(확정적)**: 로그에 `OSError [Errno 22] Invalid argument: 'C:\coupang-analytics\쿠팡애널리틱스.exe'`. **앱 코드는 exe 를 절대 안 엶**(`sys.executable`은 apppaths 폴더경로용 1곳뿐) → 이 OSError 는 런타임이 exe 를 읽으려다 실패=외부가 exe 를 격리/삭제했을 때만. CLAUDE.md 함정#10(미서명 PyInstaller=Defender Wacatac !ml 오탐) + 소유자가 어제 보안설정 변경 + 실행 8초 만에 크래시(로컬복사 성공·HTTPS백업 실패=exe 속 모듈 읽어야) → **Defender 실시간검사가 실행 중 exe 격리**가 원인. 코드 버그 아님. 해결=**설치폴더 전체 Defender 폴더제외**(재배포 시 압축 풀기 전에). 19:53 수동 재실행은 정상 완주(제외 먹힘). ⇒ 오래된 "18:00 즉시닫힘" 미스터리 규명 완료.
- **본 실행(19:53) 정상 완주**: 27계정 중 26 수집·1(하성진) 로그인실패(세션+Akamai)·재고역기록 41개·06:53 완료. **순위셀 2170개 중 "50위" 1755개(81%)=옛코드 A-1 버그**(재배포로 "위밖"화). 날짜=오름차순(옛)·재배포로 최신-왼쪽.

## ✅ 추가 구현 (817874c) — 재고 공란=오류 로그 + 공통 로그함수
- 소유자: 로켓그로스는 재고 필수존재 → 로켓그로스/둘다인데 재고 공란=**vid 잘못 잡은 오류**(조용한 공란 금지). `_fill_product_metrics`가 매칭 vid 0개면 `[재고오류] vid=.. 상품명 [kind] 재고맵(Nvid)에 vid 없음`. 재고 0=정상기록·개인(판매자배송)은 오류 아님. **로그 전용**(결과파일 미변경).
- 공통 로그함수 `_ilog(log, tag, vids, name, msg, kind=)` — vid 항상 포함(`grep vid=<값>`로 전 과정 추적), [지표]·[키워드]·[오류]·[순위]·[노출명] 통일. 핀 verify_offline[15]. [[inventory-api-rfm-search]].
- **상품군 배경색 교대**(2e78b49): 같은 등록상품명(대표+옵션 변형)=한 상품군=한 색, 인접 군은 살구↔민트 교대로 시각 구분. `_StyleCtx.f_prod2`·`_style_metric_rows(prod_fill)`·그룹판정=regs 연속. 핀 pin_apply_style[S8]. [[seldoc-output-format]].

## ⏳ 남은 것 (새 세션이 이어갈 것)
- **기타 deploy 스크립트 인코딩 점검(소유자: "다음에")**: `install_schedule_py.bat`도 chcp 65001+한글이라 0_먼저실행과 같은 949 콘솔 깨짐 가능(2차 경로·미검증). 필요 시 CP949로 통일. 설치.bat=ASCII·install.ps1=BOM 안전.
- **A-2 '둘다' 리스팅 NORMAL 고유옵션 손실** = **실데이터 확인 후**. (재고 공란 근본원인=상품조회 옵션 vid ≠ 재고 API vid·현재코드 RFM vid 채택으로 대부분 해결, `collector.py:328-332` 주석·라이브 확인 남음.) `collector.py:715-718`이 item_name 대조 없이 BOTH 리스팅 NORMAL 전부 제외 → RFM전용+NORMAL전용 혼재 시 NORMAL전용 지표 누락. 안전판=RFM item_name 겹치는 NORMAL만 제외. 진단=`tools/diag_inv_hidden.py`·라이브. 혼합 리스팅 실재 확인 전엔 미수정(헛수정=회귀).

## 리뷰서 "문제없음" 확인(안심 근거)
- 구글시트 직원 마케팅 E~G·직원 키워드 보존(파괴경로 0) · 무인 종료(06:00 강제종료 잔재 0·완주후만) · 서킷브레이커·예외전파·브라우저 수명 · rank_suppressed 판정 · 키워드 dedup(띄어쓰기 별개) · product_match 게이트 방향.
- 경미 미수정: rank.py `jitterMinMs` 미정의(RANK_NAV_SERIAL=True라 휴면·구 병렬경로 복원 시 수정) · write_ledger_inventory 하드코딩 시트명 · product_match 괄호 부분일치(짧은 괄호값) · _flag_sale_mismatch 마커 미해소 · 엑셀 계정목록 status 미반영.

관련: [[session-handoff-260923]] [[followups-260921-run]] [[fix-from-real-evidence]] [[commit-with-design-and-memory]] [[analysis-request-no-code-change]].
