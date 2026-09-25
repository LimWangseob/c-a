---
name: handoff-inventory-blank-260924
description: "⭐⭐새 세션 인계(2026-09-24) — 재고 공란 조사 진행중. 원인=상품조회↔재고 vid 불일치(추정 반증 끝·소유자 방향 확정). 막힌 곳=상품 단위 매칭율 확정에 [A]로그 상품구분자 필요. 미푸시 2개."
metadata:
  node_type: memory
  type: project
  originSessionId: dc7fcb2b-acc9-4522-a5a2-32fe7a65b849
  modified: 2026-09-24T01:31:43.763Z
---

**이 세션 흐름**: A·B·D 구현 → 계정목록 링크 라이브 복구(전체재작성) → 계정목록 sync 그리드 자동확장 버그수정 → **재고 공란 심층조사**(진행중, 아래가 핵심).

## 🔴 현재 진행중 = 재고 공란 원인 조사 (운용 260923 로그 실측)
소유자 요청: 상품별 재고가 공란인 게 있음. 원인 규명 후 수정.

### 확정 사실 (추정 없음·로그 실값·grep 확인)
- 마스터(운용 260923): 재고행 **값 80·공란 130** (웰빙곳간 값16·공란78 최다).
- 진단 실행 로그(`[vid대조]`): **상품조회 로켓그로스(RFM)옵션 785 → 재고매칭 436·재고없음(공란) 349 = 44%**(옵션 단위).
- 재고없음 349의 valid·상태: **INVALID·판매중지 240**(69%)·**VALID·판매중 51**·VALID·부분판매중 39·INVALID·부분 18·INVALID·반려 1.
- **반증 완료**(중요): "공란=묶음/판매중지"는 **틀림** — VALID·판매중인데 공란 51개, INVALID·판매중지인데 매칭된 것 152개. valid·상태로 공란 여부 안 갈림.
- 재고 vid인데 상품조회에 없음 = **669개, 전부 상품조회에 아예 없음**(vendorItemId 기준·95030300320 grep 확인). 둘 다 vendorItemId 필드(collector.py:276·405)·필드 불일치 아님·로그 완전(wellbing [A] 320줄=옵션수·gyi 369줄).
- 핵심 그림: **상품조회(vendor-inventory/search)와 재고 API(inventory-health-dashboard)가 같은 로켓 상품에 서로 다른 vid를 쓰거나 서로 안 주는 게 상당수.** 예: 맥문동 — 재고엔 92401359500(30개)+95030300320(기본) 둘 다, 상품조회엔 30개만 주고 95030300320 안 줌.

### 소유자 확정 방향 (되돌림 방지 근거로 기록)
- **상품명 규약**: 대장=담당자명, 결과=쿠팡 노출명 [[product-name-convention-ledger-vs-result]].
- **수집 순서(소유자 지정)**: ①상품조회(계정 전 상품) ②대장 상품명 매칭→상품상태(판매중/중지)·로켓그로스/판매자 판별 ③로켓그로스면 vid 임시저장 ④재고조회해서 그 vid 비교→맞으면 재고저장·없으면 [재고오류] 로그 ⑤판매분석(이벤트 있는 상품)에서 vid로 판매정보. **재고를 먼저 하지 말 것**(재고엔 판매중지 상품도 있음).
- **매칭 방향 = 상품조회 로켓그로스 → 재고** (재고→상품조회 아님). 재고=로켓그로스만(단 판매중지 포함).
- **변형(2개·60개…)은 결과파일에 개별행 말고 로켓 상품 단위로 표기**(#2). ⚠2026-09-20 "옵션(vid)별 블록 분리" 결정을 되돌리는 것 → 실측 근거 남기고 확정 필요.

### ✅ 근본원인 확정(2026-09-24 로그+캡처 실측) — "VID는 유일하나 한 상품이 여러 VID"
- **VID(vendorItemId)는 (리스팅×옵션)마다 유일**하지만, **같은 실제 상품이 여러 vid로 쪼개짐**. 원인 2:
  ① **중복/재등록 리스팅** — 같은 옵션을 로켓그로스에 여러 번 등록하면 vendorInventoryId·vendorItemId 새로 생김. 재고는 활성 리스팅에만. **캡처 실증(bf0621 화로테이블 R023)**: 같은 "블랙 one size 48cm"이 `pid=9004991148` 동일한데 vid 3개(95739245147/95829514620/95922871804)·vInvId 3개, 재고 13/0/0.
  ② **가상번들(묶음)** — 2·3개 묶음 옵션은 자체 재고 없음(기본 단위서 끌어씀). 재고 API 필드 `virtualBundleType`·`hasVirtualBundles`·`salesThroughVirtualBundles`가 구분.
- **식별자 비교**: 두 API 공통키=`vendorItemId`·`vendorInventoryId`뿐. **`productId`(노출상품ID=진짜 상품단위)는 재고 API에만 있고 상품조회엔 없음**(collector 주석 line 126). 재고 viProperty: vendorItemId·listingDetails{vendorInventoryId·productId·itemId·virtualBundleType·hasVirtualBundles·isSaleSuspended·badgeGrade}·inventoryDetails.orderableQuantity·creturnConfigViewDto{productId·productName·onSale}·skuDetails.
- **결과파일 관점 재고공란**: 상품조회 전옵션 349공란이 아니라, **추적(대장) vid 188개 중 재고오류 108개**가 실제 대상([지표]/[재고오류] 줄만 등록상품명 있음). 그 중 판매자배송 단독 4=오탐(재고개념 없음)·나머지=중복/번들 vid.
- Q1 실측: "부분판매중+둘다면 다 공란"은 **틀림**(29건 중 재고있음 15·공란 14). 상태 무관, 순전히 vid 단위 현상.

### ✅ 원본(_raw) 분석 완료(2026-09-24) — 재고 소스 확정
- 6계정 원본 분석: 상품조회 `upbundlingInfo`가 묶음을 명시(`upBundling`·`upBundlingSize`·`upBundlingOriginalVendorItemId`). 묶음 재고=기본÷수량.
- **🔒 재고 소스 규칙(소유자 확정 2026-09-24)**: 재고=**로켓그로스만**·**재고현황 API `orderableQuantity`에서만**. ⛔상품조회 `stockQuantity`=등록시 임의입력값→**신뢰불가·쓰지말 것**(내 stockQuantity 제안은 폐기). 상세=[[inventory-api-rfm-search]].
- **✅최종 확정 수정 방향(소유자 2026-09-24, 업번들 계산 폐기→제외 선택)**: ①**업번들(upbundlingInfo.upBundling=True) 옵션 = 결과파일 완전 제외**(상품/옵션/순위/재고 전부). ②로켓그로스 원상품(RFM·비업번들) 재고 = **재고현황 API 존재 여부로 판정** — 있으면 orderableQuantity(0이면 "0"=입고됐지만 품절), 없으면+VALID="미입고", 없으면+INVALID=판매중지 처리. ③판매자배송=재고 없음(공란·[재고오류] 오탐 제거). 재고값 출처=재고현황만(stockQuantity 금지). 상세·근거=[[inventory-api-rfm-search]] 🔒규칙. **구현 대상**: products_from_vendor_inventory(업번들 제외) + _inventory 매칭(재고현황 존재/부재→입고/미입고). ⚠[[code-health-regression-gate]] 핀 먼저.

### 🚧 다음 단계 (진단 보강 완료 → 재수집 대기)
- **✅ 진단 로그 보강 완료(이번 세션)**: [A]에 vInvId 추가 · [B] 재고 API 리치덤프(pid·vInvId·번들·재고) · [D] **productId 그룹핑**(같은 pid의 vid·재고 분포로 중복/번들 상품 확정). **재빌드 → 운용 PC redo_today → 새 로그로 상품단위 확정**.
- 그 후 수정 방향(소유자 확정 필요): **재고 API productId(또는 vendorInventoryId)로 상품 묶어** 비-번들·활성 vid의 orderableQuantity를 대표재고로. Q1 재고=합산 vs 대표, Q2 표시=합침 vs 옵션분리 유지. 판매자배송단독 [재고오류] 오탐 제거도 부수.
- 로그 파싱 포맷(신): `[A] vid|vInvId|종류|valid|상태|재고|이름` · `[B] vid|pid=..|vInv=..|번들|hasVB|재고|susp|이름` · `[C]` 집합대조 · `[D] pid=.. vidN개 [이름]: vid(재고n·vInv..)…`. 260923 로그(옛 포맷)는 다운로드 `output (1).zip`.

## 코드 상태 (이 세션 커밋·게이트 초록)
- **✅원본(raw) 통째 보관 추가(2026-09-24, 소유자 요청)**: 가공 없이 3개 API 응답 원본 저장 → **재빌드 없이 무엇이든 오프라인 분석**. collector `_LAST_RAW`+`reset_raw_dumps()`/`last_raw_dumps()`/`_raw_add(key,body)`(DIAG일 때만·3 fetch 지점[sales 258·inventory 391·vendor 489]서 body 원문 append). pipeline `_dump_raw(a,log)` = `output/_raw/{계정}_{api}_p{n}.json.gz`(gzip·바이트 완전일치 실측). `_discover_products` top에서 reset·끝에서 dump. **run_log는 요약만**([A]/[B] verbose 제거·[C]집합대조·[D]productId그룹핑만 유지). 재고 vid당 ~7.5KB→전계정 gzip ~1.5~2MB. api=vendor_inventory|inventory|sales.
- **진단 보강(2026-09-24)**: `config.DIAG_VID_LOG=True`. collector `_parse_inventory_diag`(재고 viProperty→{vid:pid/vInvId/번들/재고/…}) + `last_inventory_diag()`(fetch_inventory 반환 불변·핀 무손상·계정마다 clear·스테일방지=inventory 키 교집합). pipeline `_log_vid_compare`(요약)+`_diag_pid_groups`[D]. 게이트 6종+복잡도 초록. **분석 끝나면 DIAG_VID_LOG=False + 진단/원본코드 제거**.
- **직전 진단(옛)**: `_log_vid_compare(a,listings,inventory,log)` [A]평면·[B]vid목록·[C]집합대조. 커밋 524d518.
- 이번 세션 다른 완료: A-1 재링크 도구·B-1 순위 종료요약·계정목록 전체재작성(rebuild_index, 라이브 자기참조 123→0 복구)·**계정목록 sync 그리드 자동확장+실패로그강화**(b40cc30, gsheet_api.grid_row_count+gsheet_index._grid_grow_requests, verify_gsheet t3d). 상세 [[fixes-abd-260923]].

## ✅ 구현 완료(2026-09-24, 소유자 승인 "현재 근거로 진행")
- **Phase 1(7b88fe5)**: 업번들(자동번들) 옵션 결과파일 완전 제외 — collector `VendorInventoryOption.is_upbundle`·`_parse_vendor_inventory` upbundlingInfo 파싱·`_tracked_listing_options`(옵션선별 분해)·`products_from_vendor_inventory` 업번들 제외. 실측 wellbing 73개 제외·고아 0.
- **Phase 2(7e6e0d0)**: 재고 표기 — `config.INV_NOT_INBOUND="미입고"`·pipeline `_block_sellable`+`_fill_product_metrics`(재고현황 값/0=품절/미입고/판매중지공란·재고오류로그 폐지)·sale_status 배선(_finish→_process_account→_ProcCtx→_fill)·workbook `product_inventory` 숫자가드(역기록 보존). 미입고 신호=재고현황 존재여부.
- 웹 근거: 업번들=2025-05 로켓그로스 자동번들·원상품 재고공유(장사왕 블로그). 미입고=등록→입고→판매 라이프사이클·재고는 입고로 결정(windly/쿠팡 가이드). SSOT=[[inventory-api-rfm-search]] 🔒규칙·DESIGN §0-00000.
- 게이트 6종+복잡도 초록(건강 파일 A/B). ⚠**라이브 확인 남음**(재수집으로 미입고/0/값 실제 렌더 대조).
- **✅정리+정책반영(2026-09-24 추가)**: 진단 apparatus(DIAG_VID_LOG·_log_vid_compare·raw덤프·_parse_inventory_diag·last_inventory_diag·_LAST_RAW 등) **전부 물리삭제**(조사완료). 결과파일 '미입고' 저장후 유지 검증(verify_offline[8] save+reload 추가). 정책 CLAUDE.md 현재상태 §재고규칙 반영·DESIGN §0-00000. 로그=진행/오류추적 공통([계정]요약·[지표] 재고/미입고/공란) 유지.

## git/배포 상태
- HEAD=**98b538a**(업번들제외+재고표기+진단제거+정책반영). **origin 푸시 완료·미푸시 0**. 작업트리 코드 깨끗(untracked=소유자 메모 3개). 게이트 6종+복잡도 초록.
- **✅재빌드 완료(2026-09-24 10:31)**: `dist/쿠팡애널리틱스_배포.zip`(155MB·exe mtime>소스 확인·진단 제거된 클린 exe). **다음=운용PC 재배포→재수집→라이브 확인**(미입고/0/값 실제 렌더 + 업번들 제외 결과 대조). ⚠재고 규칙은 오프라인 검증만 됨(라이브 미확인).
- **✅재빌드 완료(2026-09-24 07:44·원본보관 exe)**: `dist/쿠팡애널리틱스_배포.zip`(155MB·exe mtime>소스 확인). **⚠다음 필수 = 소유자가 운용 PC 재배포 → redo_today** → `output/_raw/{계정}_{api}_p*.json.gz` 원본 3API 생성 + run_log 요약([C]/[D]).
- 재수집 후 소유자가 output zip(_raw 포함) 주면 → productId 그룹핑으로 상품단위 재고 매칭율 확정 → 수정 설계(재고=합산vs대표, 표시=합침vs분리).
- 260923 옛 로그(옛 포맷)=다운로드 `output (1).zip`의 `run_log_260923_223434.log`(분석 완료분).
- ⚠**pytest Stop훅 오탐**: 커밋 안 된 .py 있으면 pytest exit5(테스트 0)로 차단. 훅 `~/.claude/hooks/on-stop.sh` 22줄 아래 `[ "$rc" -eq 5 ] && exit 0` 추가는 **소유자 직접**(Claude Self-Modify 거부됨).

관련: [[fixes-abd-260923]] [[product-name-convention-ledger-vs-result]] [[feature-vid-source-from-product-list]] [[inventory-api-rfm-search]] [[fix-from-real-evidence]] [[analysis-request-no-code-change]].
