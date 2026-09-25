---
name: analysis-gsheet-dup-listing-260924
description: "⭐분석(2026-09-24, 수정 보류) — 출력 구글시트 정밀 분석 결과 동일상품 분리·판매상태 공란·판매정보 공란의 근본원인=중복/재등록 리스팅(한 상품이 여러 vid). 고칠 것 2건(A=상품단위 합침 설계결정·B=판매상태 소스 all-or-nothing 병합 코드갭). 소유자 지시=분석만·수정 보류."
metadata:
  node_type: memory
  type: project
  originSessionId: 21b94b1b-9360-410e-958f-e9680c3d75d1
  modified: 2026-09-24T10:22:16.084Z
---

**맥락**: 재고칸 규칙 개정(판매중지 무관 미입고·판매상태 지표행·업번들 잔재삭제, 커밋 03e0394) 배포·재수집 후 소유자가 출력 구글시트에서 ①동일상품 분리 ②판매상태 공란 ③판매정보 공란 발견 → 전체 시트 SA API 정밀 분석. **소유자 지시=분석만, 수정 보류.**

## 실측 (URL=15u3k7c5uYfWPGWM4qt-wOMGtwymmAMPPm8kEwLKFGno, SA 읽기)
- 26계정 183블록 · **판매상태 공란 28** · **판매정보(판매/방문/노출) 공란 42** · 셋다공란 0(죽은 중복은 '0'으로 채워져 공란 아님).
- ⚠자동 "중복군" 카운터 0 = 집계기준 한계(옵션라벨 꼬리까지 포함 full-name 미세차로 그룹 안 묶임). 실데이터엔 중복 명백.

## 근본원인 (하나로 수렴) = 중복/재등록 리스팅 + vid 파편화
같은 실제 상품이 쿠팡에 여러 번 등록돼 리스팅마다 vendorInventoryId·vid 새로 생김 → `products_from_vendor_inventory`가 리스팅 1개=블록 1개로 만들어 **한 상품이 4~5블록**. 활성 vid 1개만 완전, 나머지 죽은 리스팅은 (미입고/0·상태공란·판매정보 0/공란). 세 API(상품조회·재고·vi-detail)가 서로 다른 vid 부분집합만 반환.
- 실례(니코에이블): 대상승 운동기구 **5블록**(활성 95322420769 재고9·판매중·판매1 + 죽은 4), 디프 청소기 **4블록**(활성 95861044689 재고185), 기저귀가방 **4블록**(활성 95468098380 재고259). 에벤에셀 BabyKoa 4블록·(DW)커머스 수영장 3블록·유라이프 식기건조대 등 동일.
- [[handoff-inventory-blank-260924]]에서 확정된 현상(①중복/재등록 ②가상번들). VID는 유일하나 한 상품이 여러 VID.

## ✅ _raw 원본 실측(2026-09-24, output(5).zip 6계정 120 중복그룹) — 판별 결론
- **상품조회에 productId 없음 확정**(응답 전체 문자열·리스팅·옵션 어디에도). productId는 재고 API에만. 코드 주석 맞음.
- **유령 vs 실제 = registrationType으로 100% 갈림**: 유령=`NORMAL`(판매자배송 유령짝)·실제=`RFM`(로켓그로스). 동반 마커 `qcOperationStatus`(RG_APPROVED)·`rocketMerchantVersion`(v2.0)·`skuId`·`barcode`도 RFM에만(=100%·65%·65%). `viUnitSoldAgg`>0=28%·valid=VALID=18%(약함).
- **이 6계정 중복 120그룹 전부 = RFM 1 + NORMAL 유령** → 기존 "둘다=RFM만 채택"(`_tracked_listing_options`)이 **이미 제외 중**. 9/24 마스터 검증: 유령 NORMAL vid(92236372068 등) 결과에서 제외됨·실제 RFM만 블록.
- **API 배열 순서 함정**: [0]=옛 유령(sku없음), [1]=재등록 실제(sku있음). "API 순서 첫 번째=대표"는 유령을 고름 → 화면 표시순서는 API에 없음.
- **RFM+RFM 재등록(니코에이블 R601_)은 이 6계정 _raw에 0건** → RFM끼리 판별자 실측 불가. 그 계정 _raw 필요(재고API/viUnitSoldAgg/qc 후보·추정). ⚠니코에이블 대상승=KIND_BOTH라 NORMAL 걸러도 RFM 여러 개 남으면 R601_ 생성 가능.
- **✅응답 원문 상시 보관 구현(사용자 요청)**: `config.SAVE_RAW_RESPONSES`·collector `reset_raw`/`raw_dumps`/`_raw_add`(3 fetch)·pipeline `_dump_raw`→`output/_raw/{계정}_{api}_p{n}.json.gz`. 다음 실행부터 전 계정 원문 자동 생성(니코에이블 포함) → RFM+RFM 판별 실측 가능. 게이트 초록·verify_offline[8]에 핀.

## ✅ 죽은 중복 정리 구현 완료(2026-09-24, 안전 sweep)
- **원인 확정(실데이터)**: 니코에이블 R601 등 유령은 **RFM+NORMAL**(RFM+RFM 아님)·유령 vid는 상품조회에 **0회**(코팡서 삭제된 옛 재등록). `_migrate_product_blocks`가 런타임에 못 지운 이유=**이름 드리프트**(scope_to_ledger가 상품명을 코팡 발견명[짧음]으로 쓰는데 마스터 잔재는 옛 긴 이름 → 등록상품명 매칭 실패). 격리 테스트는 지웠으나 런타임 미발동.
- **해결 = vid 앵커 안전 sweep** `_sweep_dead_duplicates(wb,biz,live_vids,log)`: **마스터 블록명 접두**로 그룹 → 그룹에 live vid(상품조회에 있는 vid) 형제 존재 AND 블록 vid **전부** live_vids에 없으면 삭제. 이름 드리프트 무관(블록명 접두)·live 판정=vid. `live_vids`(상품조회 전체 vid) 배선 `_discover_products`→`_login_and_discover`(6번째)→`_finish`→`_process_account`. reconcile 전 실행.
- **엣지케이스 안전(소유자 확인)**: blanket("vid 없으면 삭제")은 **판매중지 데이터 유실 위험**(취소선 미운영 상품/담당자 대장삭제분 vid 소멸 시 삭제됨)이라 폐기. 안전 sweep은 신규 계정/상품·취소선 미운영 계정/상품·대장삭제(판매중지 단독=live 형제 없음)·색상/사이즈 변형·판매자배송 twin(vid 코팡 잔존)·상품조회 실패(live 빔) **전부 보존**. 소유자 선택=안전 sweep.
- **실측**: 니코에이블 13→6블록(죽은 유령 7 삭제·real 3+NORMAL twin 3 보존). verify_offline[8]에 엣지 5종 핀. 게이트6+복잡도 초록.
- ⚠**NORMAL twin 잔여**(코팡 잔존 vid라 vid 소멸 아님→유지, 판매중지 표기): 완전 제거하려면 registrationType 배선 필요(별도 후속·현 안전규칙 밖).

## 고칠 것(과거 분석 — 상당수 위에서 해결)
- **A(설계 결정·미결)**: 중복 리스팅 블록을 **상품 단위로 합칠지**. Q1 재고=합산 vs 대표, Q2 표시=합침 vs 옵션분리 유지. [[handoff-inventory-blank-260924]] #2와 동일 미결. 죽은 중복 자동정리(업번들 sweep처럼)도 옵션. **행동 변경이라 소유자 결정 필요.**
- **B(명확한 코드 갭·소규모)**: `pipeline.py` `_discover_products` (HEAD 03e0394 기준 692줄 부근) `sale_status = vendor_status if vendor_status else rfm_status` = **전부-아니면-전무**. vendor_status(상품조회 productStatus) 비어있지 않으면 **RFM 재고 API 상태(isSaleSuspended) 통째 무시** → **재고 API엔 있는데 상품조회엔 없는 vid는 판매상태 공란**((DW)커머스 수영장 3·니코에이블 재고0 중복분·유라이프 2 등). **`vendor_status ∪ rfm_status`(상품조회 우선) 병합**으로 바꾸면 상당수 채워짐. (수정 시 pin/게이트 먼저 [[code-health-regression-gate]].)

## 판매상태 공란 28 세부
- (a) vid有+재고값有+상태공란 = 위 B 갭(RFM엔 있고 상품조회 없음).
- (b) vid無(미매칭)+상태공란 = 대장엔 있으나 쿠팡 매칭 안 된 판매자배송 단독(안전화 Y011·신형타프 R008·목견인기·보냉백·구강세정기 등). vid 없어 상태소스 없음(정상·한계).

## 판매정보 공란 42 = 스테일/고아 블록
이번 실행에서 그 블록 vid가 추적대상 아님(최신 날짜칸 미기록). 예: **휴라엘 캠핑타프 2블록**(95893113451·95893113448) 재고·상태·판매정보 전부 공란=완전 미처리 스테일 → 정체성 마이그레이션이 왜 안 잡는지 별도 점검 후보.

## 상태
- 배포 개정(미입고·판매상태 지표행·업번들 sweep)은 **라이브 정상 동작 확인**(활성 vid 판매중/부분판매중 표기·미입고 표기 OK). 문제는 그 아래 **중복 리스팅 블록 자체**.
- 수정 보류(소유자 2026-09-24). 재개 시 B(병합) 먼저 소규모 수정, A(합침)는 설계결정 후.

관련: [[handoff-inventory-blank-260924]] [[handoff-gsheet-inventory-followup]] [[feature-vid-source-from-product-list]] [[analysis-request-no-code-change]] [[fix-from-real-evidence]] [[code-health-regression-gate]].
