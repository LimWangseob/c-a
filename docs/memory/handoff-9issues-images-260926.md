---
name: handoff-9issues-images-260926
description: ✅결과파일 이미지 9이슈 정밀분석+조치 구현 완료(2026-09-26·라이브 남음) — 상품군 그룹키=블록명 base(레몬버베나/식기건조대 드리프트)·판매가/판매상태 자가치유·빈 키워드행 낡은순위 삭제·비고=대장 판매상태·상품명 하이퍼링크 productId 출처=판매분석∪재고. 게이트 7종+복잡도 초록.
metadata:
  node_type: memory
  type: project
  originSessionId: c16f3da3-27f9-41ca-bf1d-0a9ab5b96704
  modified: 2026-09-26T05:54:27.778Z
---

소유자가 결과 구글시트 5개 이미지 + 9개 이슈로 전수조사/원인분석/조치 요청. 전부 구현·게이트 통과, **라이브 확인·재배포 남음**.

**조치 5묶음:**
1. **항목7/8/9 상품군 그룹키 = 블록명 base**(`workbook._group_key`): 옵션 접미 `" (라벨)"` 제거+공백정규화. 등록상품명 드리프트(레몬버베나 "…정" vs "…정 60정"·식기건조대 twin '' vs 세트)로 같은 상품군이 다른 색·분산되던 문제 → `_regroup_sheet_blocks`·`_style_sheet` 그룹핑을 등록상품명 대신 블록명 base 로. 실측 run6: 레몬버베나 3블록 FBE2D5 통일·연속 확인.
2. **항목4/6 판매가·판매상태 지표행 자가치유**(`_backfill_metric_rows`, apply_style): 2026-09-24 신설 이전 옛 블록(대장서 빠진 판매중지·미로그인 계정=파이프라인 미방문)엔 두 행 없음(실측 13블록) → 저장마다 없는 행만 삽입(순서 재고<판매가<판매상태·재고는 KINDS_WITH_INVENTORY만·kind='' 미상은 재고 강제 안 함).
3. **항목5 빈 키워드행 낡은순위 삭제**(`_clear_blank_keyword_ranks`): 이름 공란 M_RANK 행(KW_TRACK_N 유지용)에 남은 옛 '50위'(실측 43행)="키워드 없는데 순위 표기" → 저장마다 이름 공란 행 일자칸 값 삭제(이름 있는 행 불변).
4. **항목3 비고 소헤더 = 관리대장 판매상태**(⛔판매중지 > 🔴체험단중 > 판매중): 옛 '비고' 라벨 폐지. 대장서 빠짐=판매중지·존재=판매중. ⚠**부작용 수정**: `has_keyword_section` 소헤더 판정을 G('비고')+A('키워드') → **A('키워드')만**(항목3로 G 용도전환돼 깨지던 것·`_find_kw_head`와 일관). `_migrate_keyword_col` sub_g 에 '판매중' 추가.
5. **항목2 상품명 하이퍼링크 = vendorItemId 기반(라이브 실증 후 최종)**: ⚠상품조회(vendor-inventory) 응답엔 공개 productId **없음이 20계정 _raw 전수 확정**(0/20·vendorInventoryId·vendorItemId·skuId만). productId 는 판매분석·재고에만 → **미입고 RFM·무활동 판매자배송 확보 불가**(화면 노출상품ID는 WING 화면의 별도 4번째 API·우리 3 API·로그엔 없음·9557485279 전수 0). **⭐라이브 실증(내장 브라우저 2026-09-26)**: `https://www.coupang.com/vp/products/0?vendorItemId={vid}` 가 productId 자리 `0` 이어도 **정확한 상품 페이지로 열림**(벅스 보냉백·쿠팡상품번호 9557485279 로드). 판매중지 vid(95546377159)는 '상품없음'(실제 판매중지라 정상). → `workbook.product_url` = **vid 있으면 `/vp/products/{pid or 0}?vendorItemId={vid}`**(pid 있으면 정규·없으면 0 자리표시)·**vid 없으면 검색 폴백.** vendorItemId 는 상품조회 전 상품·전 옵션 항상 존재 → 미입고·판매자배송 커버(실측 기존 마스터 상품페이지 링크 88→109·검색폴백은 vid없는 미매칭 20만). pid_by_vid(판매분석∪재고=collector `OptionMetric.product_id`+`_parse_inventory_pids`·`fetch_inventory` 3→4튜플·pipeline `_apply_pid` 배선)는 정규 URL 용으로 유지. 핀 pin_apply_style[S9]·verify_offline[14 (d)]·verify_render[항목2].

**검증**: 게이트 7종+`check_complexity`(exit 0·경고는 기존 타 파일 괴물함수). 핀 pin_apply_style[S1 비고=판매중]·verify_offline[14 자가치유 3종]·verify_render_precision[항목2 링크·상품군색]·페이크 4튜플화(pin_login_ranks·simulate·verify_render). run6 실측 치유 0/0/0.

**항목5 후속(소유자 2026-09-26 확정)**: '50위 삭제'(`_clear_blank_keyword_ranks`)는 판매중지 상품 청소용으로만 맞음(소유자 동의·유지). 활성 공란의 실제 원인=①하성진=로그인 실패로 수집 안 됨(버그 아님·OK) ②벅스 '--'=대장 상품명이 자리표시. → **상품명 아닌 대장 행 파싱 제외 구현**: `input_list._is_real_product_name`(글자[한글·영문·숫자] 하나라도 있어야 True)로 `_parse_grid` 상품행 맨 앞에서 걸러 추적/블록/시트/계정목록 생성 제외·ledger_products 미포함(기존 '--' 잔재는 reconcile 완전삭제 유도). 핀 verify_offline[15].

---

## 📋 오늘(2026-09-26) 수정 종합 — 전부 커밋·푸시 완료(origin/master `2d0c7c0`, 미푸시 0)

**커밋 3개**(각각 코드+DESIGN+DECISIONS+CLAUDE+메모리 동시 반영):
1. `bf8b334` — 9이슈 조치: ①상품군 그룹키=블록명 base(항목7/8/9) ②판매가/판매상태 지표행 자가치유(항목4/6) ③빈 키워드행 낡은순위 삭제(항목5) ④비고=대장 판매상태(항목3) ⑤초기 productId(판매분석∪재고)
2. `903b594` — 항목2 상품명 하이퍼링크=**vendorItemId 기반**(라이브 실증). `product_url`= vid 있으면 `/vp/products/{pid or 0}?vendorItemId={vid}`·vid 없으면 검색 폴백. 미입고 RFM·판매자배송 커버(상품조회 응답엔 productId 없음 0/20 확정).
3. `2d0c7c0` — 상품명 아닌 대장 행('--'·기호/공백만) 파싱 제외(`_is_real_product_name`·`_parse_grid`) → 추적/블록/시트/계정목록 생성 제외·ledger_products 미포함(기존 '--' 잔재 reconcile 삭제 유도).

**검증(오프라인)**: 시뮬 14 + 게이트 7종 + `check_complexity`(exit 0) 초록. 핀 pin_apply_style[S1·S9]·verify_offline[14·15]·verify_render_precision[항목2].
**배포**: `dist/쿠팡애널리틱스_배포.zip` 재빌드 완료(2026-09-26 12:00·exit 0).

## ✅ 라이브 확인 요구 체크리스트(운용 PC 재배포 → **"오늘 것만 다시 수집"(redo_today)** 실행 후 대조)
> ⚠ **실행옵션=GUI 전체실행 탭 "오늘 것만 다시 수집" 체크**(새벽에 1회 돌아서 "이어서 하기"는 완료계정 건너뛰어 반영 안 됨). ①판매수집=로그인 필요(사무실). 로그에 `오늘 처음(다시) 하기 … 오늘 컬럼 초기화 후 재수집` 뜨면 정상.
- [ ] **상품명 링크**: 통계 시트 상품명 클릭 → 쿠팡 상품 페이지 열림(**미입고/판매자배송·품절 포함**). URL=`/vp/products/{pid or 0}?vendorItemId=`.
- [ ] **'--' 제외**: 벅스(bux1004) 계정에 `'--'` 블록·계정목록 행 사라짐. 로그에 `상품명 아님 '--' … 제외`.
- [ ] **상품군 색**: 레몬버베나·식기건조대 등 같은 상품군=같은 배경색·인접(살구↔민트 교대).
- [ ] **비고 소헤더**: 키워드 소헤더에 `판매중`/`⛔ 판매중지`(옛 '비고' 라벨 없음).
- [ ] **판매가·판매상태 지표행**: 모든 상품 블록에 존재(옛 13블록 자가치유).
- [ ] **빈 키워드행**: 낡은 `50위` 없음(판매중지 블록 포함).
- [ ] (참고) 하성진(lslfgh)=로그인 실패면 여전히 공란=정상(버그 아님).

## ▶ 다음 세션 이어가기
- **상태**: 코드/문서/메모리 전부 origin/master 반영·미푸시 0·zip 재빌드 완료. **남은 유일 작업=운용 PC 라이브 검증**(위 체크리스트).
- **라이브에서 문제 발견 시**: output.zip(로그+_raw+마스터) 받아 분석 → [[fix-from-real-evidence]] 원칙(진단 후 수정)·핀 먼저·게이트 7종 유지.
- **미해결/보류 항목**(이번 세션 밖):
  - [[analysis-gsheet-dup-listing-260924]] A안(중복 리스팅 상품단위 합침)·B안(sale_status vendor∪rfm 병합)=소유자 분석만 지시·수정 보류.
  - [[handoff-block-layout-redesign]] 레이아웃 v4=구현됨(라이브 확인 남음).
  - RFM+RFM 재등록 유령 판별(니코에이블 R601_)=그 계정 _raw 필요(다음 실행 자동 생성).
- **핀·게이트**: `python tools/run_checks.py`(7종)·`tools/check_complexity.py`(exit 0). 새 클론이면 `python tools/install_hooks.py` 1회.

관련: [[analysis-gsheet-dup-listing-260924]] [[handoff-inventory-blank-260924]] [[handoff-3decisions-260924]] [[handoff-block-layout-redesign]] [[fix-from-real-evidence]] [[sales-data-api-vi-detail-search]] [[inventory-api-rfm-search]] [[feature-product-coupang-link]] [[feature-business-name-grouping]].
