---
name: handoff-session-260927
description: "세션 인계(2026-09-27): Cause C·상품명깨짐 수정+output(8) 3+4이슈 분석 완료·전부 커밋/푸시. 다음=운용PC 재배포+fresh 수집·wellbing 판매정지 WING 확인"
metadata:
  node_type: memory
  type: project
  originSessionId: 3588291b-3435-4968-8471-8410129d1b69
  modified: 2026-09-27T14:28:51.109Z
---

**세션 상태(2026-09-27): 전부 커밋·푸시 완료(미푸시 0·tracked 변경 없음)·배포 zip 재빌드 완료. 남은 실행 작업 = 운용 PC 재배포 하나.**

## 이번 세션에 한 것(전부 origin/master 반영, HEAD=4e484d0)
1. **Cause C — 여러 줄 대장 상품명(커밋 5cc64a6·2d02b7c)**: 담당자가 상품명 칸에 `상품명\n\n(노출명)`처럼 여러 줄 입력→중복 블록·관리대장↔결과 계정목록 미정합. `input_list._parse_grid`가 개행 있으면 첫 줄만 채택. 부수로 사문화된 옵션파싱(opt/vids/pids/prod_cancelled/_split_ids) 물리삭제(F821 잠재 제거). 핀 verify_offline[C].
2. **상품명 깨짐 — 비-헤더 C셀 URL 잔재(커밋 a6055e4)**: 옛 배포가 판매상태/판매가/빈 행 C셀에 검색URL을 값으로 남겨 상품명이 URL로 보임. `workbook_render._clear_stray_url_cells`(헤더 아닌 C셀 http값·링크 삭제)를 apply_style에 배선. 실측 웰빙곳간 8→0·정상 상품명/링크 보존. 핀 pin_apply_style[S10].
3. **output(8) 정밀 분석(커밋 4e484d0·코드변경 없음)**: 메모 [[analysis-output8-260927]] 참조.

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
