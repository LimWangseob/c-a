---
name: handoff-gsheet-inventory-followup
description: ✅재고칸 규칙 개정 2건 **구현 완료**(2026-09-24). ①재고=판매상태 무관 재고현황 있으면 값·없으면 미입고(옛 판매중지→공란 폐기·_block_sellable 제거) + 판매상태는 '판매상태' 지표행에 실행일마다 기록(쿠팡 존중) ②업번들 잔재 매 수집시 vid 기준 자동삭제. 게이트 초록·라이브 확인 남음.
metadata:
  node_type: memory
  type: project
  originSessionId: 3692dcfd-2837-435e-ad20-caae9553bb34
  modified: 2026-09-24T05:22:05.563Z
---

**✅구현 완료(2026-09-24)**: 아래 소유자 확정 2건 전부 구현·게이트 6종+복잡도 초록. **남은=라이브 확인**(재수집으로 미입고/값/판매상태 렌더 + 업번들 잔재 삭제 대조)·커밋/푸시/빌드는 소유자 확인 후.

**구현 요지**:
- **Fix A-1(재고칸)**: `_fill_product_metrics` 재고 분기 = 재고현황 있으면 값(0=품절)/없으면 항상 '미입고'. `_block_sellable` **물리 제거**(판매중지→공란 분기 폐기).
- **Fix A-2(판매상태 쿠팡 존중)**: 이미 만족(all-SUSPENDED 보정 로직 애초에 없음). 무동작.
- **Fix A-3(판매상태 표시)**: **소유자 선택=상품블록에 '판매상태' 지표행 추가(매일)**. `config.M_SALE_STATUS="판매상태"`를 CONTRACT/PERSONAL_METRICS에 추가·`_block_sale_status`가 블록 판정·`_fill_product_metrics`가 실행일 date칸에 기록·`ensure_product_block`이 옛 마스터 블록에 행 자동추가(멱등). 재고칸 아니라 별도 지표행.
- **Fix B(업번들 잔재 삭제)**: `_purge_upbundle_blocks`(vid 전부 업번들이면 삭제·변형 보존·빈집합 no-op). 업번들 vid 집합 배선=`_discover_products`(6번째 반환)→`_login_and_discover`(5번째)→`_finish`→`_process_account`(reconcile 전 sweep).
- **테스트**: verify_offline[8]=판매상태 판정·재고 미입고(판매중지 무관)·판매상태 지표행·업번들 sweep. [15]=재고 미입고 개정. pin_login_ranks=5튜플 언패킹·_LISTINGS=[]. simulate=fake 5튜플.
- **문서**: DESIGN §0-00000·CLAUDE 현재상태 갱신(구버전 표시 제거).

**[아래는 원래 인계 — 결정 근거 보존]**
**맥락**: 9/24 재수집 결과(구글시트 웰빙곳간) 실측 분석에서 재고칸 문제 발견 → 소유자가 규칙 개정 확정.

## 소유자 확정 결정 (2건 — 그대로 구현)

### Fix A — 재고칸 규칙 개정 + 판매상태 비고 표시 (쿠팡 존중)
- **재고칸 = 판매중지 여부와 무관하게**: 재고현황 API(inventory-health-dashboard `orderableQuantity`)에 vid **있으면 그 값(0=품절)·없으면 항상 "미입고"**(`config.INV_NOT_INBOUND`).
  - 옛 "재고현황 없음 + 판매중지 → 공란" 분기 **폐기** → `pipeline._block_sellable` 제거, `_fill_product_metrics`의 재고 분기를 "matched→값 / else→미입고"로 단순화.
  - 배경: 웰빙곳간=제한계정('신규 등록 불가')이라 상품조회 productStatus가 **상품 전부 SUSPENDED**로 나옴. 옛 규칙에선 판매중 관리상품도 재고 텅 빔(마스터 실측: 웰빙곳간 47블록 중 재고값 16·공란 31). 개정하면 공란→미입고/값으로 정상화.
- **판매상태(productStatus)는 쿠팡 그대로 존중(우선 적용)** — all-SUSPENDED "안 믿기" 보정 **안 함**(내가 처음 제안했다가 소유자가 뒤집음: 쿠팡 존중). productStatus 원문 해석(판매중/판매중지/부분판매중/임시저장/승인반려/검토중, `collector.sale_status_of`).
- **판매상태를 "실행일 비고 항목에 항상 표시"** — 재고칸이 아니라 별도 비고에 매 실행일 상태 기록. ⚠**비고 위치 확인 필요**: 결과시트 키워드 소표에 '비고' 열 있음(스크린샷 G열 "키워드|검색량|비고"). 상품(블록) 단위 판매상태를 어디(어느 셀/행)에 매일 쓸지 워크북 구조 확인 후 구현. 기존 `apply_sale_status`(대장=판매중지인데 쿠팡=판매중 경고, 최신날짜칸 적색)와 **구분**(그건 불일치 경고, 이건 상태 상시표기).
- ⛔불변: 상품조회 `stockQuantity`(재고 숫자)는 신뢰불가·안 씀(등록시 임의입력). 재고값 출처=재고현황 API만.

### Fix B — 업번들 잔재 블록 매 수집 시 자동 삭제
- 별도 정리 도구 ❌(담당자가 상품 변동시키므로 일회성 도구 부적합) → **매 수집 때 자동 삭제**.
- 현재: 업번들은 새 수집 상품목록에서 제외(`products_from_vendor_inventory`)되지만, **마스터에 이미 있던 옛 업번들 블록은 reconcile이 '판매중지'로 남겨** clutter(웰빙곳간 `(2개 180정)`·`(3개 30회분)` 등 재고 공란으로 잔존).
- 구현: `_migrate_product_blocks`(또는 reconcile 경로)에서 **이번 상품조회의 업번들 vid 집합**(`upbundlingInfo.upBundling=True`인 vid)을 threading → 마스터 블록의 vid가 업번들 vid면 **삭제**. **vid 기반**(이름패턴 "(N개)" 아님 — 색상/사이즈 변형 `블랙 4개` 등 정상옵션 오삭제 방지). 색상/사이즈 변형은 유지.

## 구현 change points (조사됨)
- `pipeline._fill_product_metrics`(재고 분기 단순화)·`_block_sellable`(제거)·`_process_option`/`_process_account`(판매상태 비고 배선, sale_status는 이미 pctx로 옴).
- 판매상태 비고: 워크북에 상태 쓰는 자리 신설/확인(`workbook`). 
- 업번들 vid 집합: `products_from_vendor_inventory`/`_tracked_listing_options`가 제외한 업번들 vid를 반환하도록 + `_process_account`→`_migrate_product_blocks`에 전달 → 삭제.
- 테스트: verify_offline[8·15] 갱신(판매중지여도 미입고·비고 표시·업번들 자동삭제), simulate_pipeline 시나리오 추가.
- ⚠[[code-health-regression-gate]] 핀 먼저·게이트 6종 초록 후 커밋·푸시·빌드.

## [현재코드] (구버전 — 개정 전, HEAD 부근)
- `_fill_product_metrics`: 재고현황 있으면 값·없고 판매중→미입고·없고 판매중지→**공란**(개정 대상). `_block_sellable` 존재(제거 대상).
- 업번들: 새 수집 제외됨(7b88fe5)·마스터 잔재 미삭제(Fix B 대상).
- 구글시트 반영 공통 재시도 적용됨(d8bd6c6, `GSheetClient._exec`).

## git/배포
- HEAD=**d8bd6c6**(구글시트 재시도)·origin 푸시됨·미푸시 0·게이트 초록. 배포 zip=2026-09-24 13:03(재시도 포함).
- 이 개정 2건은 **아직 미구현**. 새 세션이 위 결정대로 구현→게이트→푸시→빌드.

관련: [[inventory-api-rfm-search]] [[handoff-inventory-blank-260924]] [[fix-from-real-evidence]] [[plain-language-no-jargon]] [[recommend-new-session-when-degraded]] [[code-health-regression-gate]].
