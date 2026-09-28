---
name: handoff-session-260927
description: "세션 인계(2026-09-27): Cause C·상품명깨짐 수정+output(8) 3+4이슈 분석 완료·전부 커밋/푸시. 다음=운용PC 재배포+fresh 수집·wellbing 판매정지 WING 확인"
metadata:
  node_type: memory
  type: project
  originSessionId: 3588291b-3435-4968-8471-8410129d1b69
  modified: 2026-09-28T08:40:27.828Z
---

**세션 상태(2026-09-27): 전부 커밋·푸시 완료(미푸시 0·tracked 변경 없음)·배포 zip 재빌드 완료. 남은 실행 작업 = 운용 PC 재배포 하나.**

## 이번 세션에 한 것(전부 origin/master 반영, HEAD=4e484d0)
1. **Cause C — 여러 줄 대장 상품명(커밋 5cc64a6·2d02b7c)**: 담당자가 상품명 칸에 `상품명\n\n(노출명)`처럼 여러 줄 입력→중복 블록·관리대장↔결과 계정목록 미정합. `input_list._parse_grid`가 개행 있으면 첫 줄만 채택. 부수로 사문화된 옵션파싱(opt/vids/pids/prod_cancelled/_split_ids) 물리삭제(F821 잠재 제거). 핀 verify_offline[C].
2. **상품명 깨짐 — 비-헤더 C셀 URL 잔재(커밋 a6055e4)**: 옛 배포가 판매상태/판매가/빈 행 C셀에 검색URL을 값으로 남겨 상품명이 URL로 보임. `workbook_render._clear_stray_url_cells`(헤더 아닌 C셀 http값·링크 삭제)를 apply_style에 배선. 실측 웰빙곳간 8→0·정상 상품명/링크 보존. 핀 pin_apply_style[S10].
3. **output(8) 정밀 분석(커밋 4e484d0·코드변경 없음)**: 메모 [[analysis-output8-260927]] 참조.
4. **계정목록 상태 낡은 판매중지 교정(커밋 7f0a7e7)**: 소유자 지적(대장 정상인데 계정목록 판매중지). `_중단`이 수집·대조 시에만 갱신돼 이어쓰기/미수집/이름드리프트 시 낡은 "Y" 잔존→정상 상품이 판매중지로 뜸(실측 커스텀존 이큐나라·하성진 등 5건). `workbook.sync_discontinued_from_ledger`(대장 활성→해제·판매중지→표기·미상 불변·옵션 등록명 대조) 신설 + `pipeline._reconcile_ledger_accounts`가 매 실행 대장 기준 전 계정 동기화. 핀 verify_offline[25]. ⚠**코드 변경 있음→배포 zip 재빌드 완료.**
5. **output(9) 분석 + 구글시트 계정목록 400 근본수정(커밋 f625227)**: 운용 output(9) 로그 실측 — 계정목록 동기화가 매 실행 400(`Invalid requests[1].mergeCells`)으로 실패(통계 25시트 성공·계정목록만 미갱신). 원인=`gsheet_index._ensure_column_order` 배치2 `[moveDimension, mergeCells]`의 제목 재병합 실패 → batchUpdate atomic이라 계정ID 열이동(#3)까지 롤백 → 무한 재시도. 수정=**3배치 분리**(unmerge+열확장 / moveDimension 단독 확정 / mergeCells 단독·**실패해도 비치명 로그만**·제목병합=장식) + `pipeline_gsheet` 에러 로그 잘림 수정(Google 사유 온전히 기록·다음 실행서 재병합 400 정확 사유 확정). 핀 verify_gsheet[11 갱신·11b 신설]. ⚠재병합 400 정확 사유 미확정(로그 잘림으로)—다음 실행서 확인. **배포 zip 재빌드 완료(09-28 11:22).**
   - **output(9) 기타 로그(확정)**: 로그인 비번오류 2계정(커스텀존=unipang·반달컴퍼니=mrc098, 실제 비번오류·대장 수정 필요)·하성진 로그인미완료(Akamai)·하성진 토탈사이언스 키워드 AI 실패 1건·③순위 04:00 이후 Akamai 차단 당일중단. [[analysis-output8-260927]]·[[verify-by-data-not-status]].
6. **노출상품ID(productId) 전 상품 확보(커밋 febb20f)**: 라이브 실측(소유자 DevTools)으로 productId 소스 API 확정 — `GET vendor-inventory/vendor-inventory-items-with-vendorItems/{vendorInventoryId}`(옵션별 productId·판매방식/판매여부 무관). `collector.fetch_product_ids`+`pipeline_sales`(상품조회 vendor_inventory_id 전량 호출→`_pid_by_vid` 병합 전상품>재고>판매분석). "노출상품 조회" 버튼 URL=`/vp/products/{pid}?vendorItemId={vid}`(라이브 로드 확인)=`workbook.product_url`과 동일. 순수 판매자배송·무판매까지 정상 상품링크. 핀 verify_offline[26]. SSOT=[[api-productid-source-vendor-items-with-vendoritems]].
7. **개선 A·B·C(커밋 8bcf8e9)**: **A** 순위간격 config `RANK_NAV_DELAY 35~55→45~75`(output(9) 차단·당일중단 실측). **B** 실행종료 데이터 품질 자가점검(`workbook.data_quality_summary`+`pipeline_ranks._log_quality_summary`, ③ track_ranks_stage 반자동·자동 양경로 run_log 이상치 요약: 판매중인데 순위 공란·pid미확보·미매칭 → '완료'가 가리는 불완전 가시화). **C** productId 트래픽 옵션 config `PRODUCT_ID_FETCH_ALL`(기본 True=전상품·False=미확보만). 핀 verify_offline[27]. 게이트 8종+복잡도 초록.
   - **✅배포 zip 재빌드·검증 완료(09-28 17:36)**: `dist\쿠팡애널리틱스_배포.zip` 151.7MB·exe 17:33빌드(A·B·C 포함)·1754엔트리·필수파일 전부. ⚠build.bat [5/5] 압축단계가 한 번 걸러져(원인 미상·zip 잠금 추정) **압축만 수동 재실행**해 생성(exe onedir은 정상). **운용 PC 재배포만 남음.**

## output(8) 분석 결론 — 소유자 보고 4이슈 (SSOT=[[analysis-output8-260927]])
- **#1 검색링크→상품링크**: "둘다"(NORMAL+RFM 같은 옵션) 상품에서 옛 배포가 pid 없는 NORMAL vid 저장→검색폴백. **현재 코드 `collector._tracked_listing_options`는 RFM vid(pid 있음) 정확 선택=이미 수정됨**(실측 파미젠: RFM vid 96075356358→pid 8359540267). 순수 판매자배송(RFM 형제 없음)은 3 API 어디에도 공개 pid 없어 검색링크 불가피(상품조회 pid 0/20 전수 확정).
- **#2 "상품 없음"**: 정상 상품은 pid 링크 정상 열림(DW커머스 7/8). wellbing만 판매정지라 페이지 없음.
- **#3 계정ID 위치**: 로컬 마스터 이미 정상(C=계정ID·D=상품명). 구글시트만 옛 코드 moveDimension 400 실패→재배포로 해결.
- **#4 노출순위 공란**: 정상 계정 순위 수집됨(로그 (DW)커머스 24회 검색). wellbing만 전량 판매정지(오늘 11:45 원본 실측 51상품 SUSPENDED 47·DRAFT 3·REJECTED 1·재고는 있음)→rank_suppressed(정책 유지).

## 다음 세션이 할 일(우선순위)
1. **운용 PC 재배포**(최우선): `dist\쿠팡애널리틱스_배포.zip`의 `coupang-analytics\` 폴더를 운용 PC 같은 자리에 덮어쓰기(output·data·config.json 보존). 현 실행=옛 코드라 위 수정 미반영.
2. **다음 정규 실행(fresh ①판매수집) 결과 확인**: #1 NORMAL→RFM vid 자동치유(소유자 "자동치유" 선택·일회성 도구 안 만듦)·#3 구글시트 계정ID 왼쪽 이동·상품명깨짐 청소·Cause C 중복블록 정리가 실제 반영됐는지 output 재확인. ⚠오늘은 이어쓰기(resume)라 ① 건너뜀→다음 정규 실행에서 반영.
3. **wellbing1107 판매정지 확인(소유자 몫)**: 쿠팡 WING에서 실제 판매상태 확인 요청함. 정상 판매중이어야 하는데 API가 정지로 주면 데이터/판정 재점검 필요. 현재는 쿠팡 응답 그대로 반영(도구 버그 아님).

## 상태 사실
- 게이트 7종+복잡도 초록·핀 verify_offline[C]·pin_apply_style[S10] 추가.
- 배포 zip=이번 세션 빌드(a6055e4 포함)·추가 코드변경 없어 재빌드 불필요.
- 미해결 코드 이슈 없음(모두 새 빌드 반영 or 쿠팡/데이터 한계).

관련: [[analysis-output8-260927]] [[input-ledger-format]] [[fix-from-real-evidence]] [[no-silent-fallback-principle]] [[feature-vid-source-from-product-list]]
