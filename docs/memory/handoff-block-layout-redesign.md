---
name: handoff-block-layout-redesign
description: "✅상품 블록 레이아웃 v4 구현 완료(2026-09-25·오프라인 검증 통과·라이브 남음). 좌측 A:B=라벨 칸(상품명2·VID·판매방식·로켓그로스3)·C:F=값. vid=메타 col3·판매방식=메타 col11·키워드명 A열 좌측확장. 3단계 커밋."
metadata:
  node_type: memory
  type: project
  originSessionId: 21b94b1b-9360-410e-958f-e9680c3d75d1
  modified: 2026-09-24T22:50:20.945Z
---

**✅구현 완료(2026-09-25)**. 소유자 확정 시안 v4(4회 반복 승인) 3단계 커밋으로 구현·게이트 6종+복잡도 초록. ⚠**라이브(재배포+재실행) 확인 남음**.

## 구현 결과(커밋)
- **1/3 `ed313fc`**: vid 저장 → 숨김 메타 `_상품ID` **col3**(A안). `_reindex` 메타 우선·헤더 'VID :' 꼬리 폴백. `set_product_kind`/`product_kind`(**col11**) 신설·pipeline `_apply_vid_meta` 배선. 행동 불변.
- **2/3 `79d7290`**: 헤더 v4 렌더. `_display_name`=상품명만. `_style_metric_rows`/`_style_block_edges` 재작성(`_v4_layout`/`_v4_values` 헬퍼). 판매방식 A열→메타 col11 렌더. 열너비 A7·B7(=G14)·C:F 재배분. `input_list._inbound_summary` **2줄**. `apply_style`에 `_migrate_vids_to_meta`(옛 마스터 vid 유실 방지).
- **3/3(키워드)**: 키워드명 **C→A열(병합 앵커)** 이전·A~E 좌측확장·사업자명 폐지. `_COL_KW=1`. reindex(M_RANK)·clear_keyword_row·ensure_product_block·add_product_keywords·_kw_block_rows·has_keyword_section·_find_kw_head·_style_keyword_rows·_style_block_edges 전부 A열 통일(비앵커 C는 저장 시 유실되므로 앵커=A 필수).

## ⚠⚠키워드 대량 유실 사고+복구+재발방지(2026-09-25, 운용PC output 포렌식)
**사고**: 09-25 01:23 실행이 키워드 450→24 유실(포렌식: 직전 01:27 백업 C열 450 온전→실행 후 A열 24). 원인=키워드 C→A 이전(9cbdf71)은 있고 마이그레이션(b68b301)은 없던 빌드(내가 "재빌드완료"로 준 3fe9c4b)가 마스터 저장 시 A:E 병합 비앵커 C값 폐기→키워드명 소멸(순위·판매·vid 보존, "이름없는 순위행"). 부차=read_staff_keywords가 C열 읽어 v4 구글시트 키워드 미반영.
**복구**: `tools/recover_keywords.py`로 output/백업 직전 온전본(통계_260924, C열 450)→현재 마스터 병합(--force-backup=원래 동결키워드). 447/450·113/114상품 완전·09-25데이터(재고84·판매상태106·판매가106) 보존. 사과초모식초(다중옵션 3블록) 1건 3키워드 부족→구글시트 직원입력 보완.
**재발방지(커밋)**: (1) `read_staff_keywords` A열+C폴백(6555e8d) (2) `_migrate_keyword_col` 손상 소헤더('키워드'@A 소실) 자가복원(31f6577) (3) verify_offline v3→v4+소헤더복원 시나리오 (4) tests/test_regression_gate.py(pytest exit5 오탐 해소). **교훈=포맷 이전은 마이그레이션+회귀테스트를 같은 커밋에 동반**(뒤늦은 커밋 사이 빌드가 사고).
**남은일**: 운용PC에 복구본 덮어쓰기 + 수정본(read_staff_keywords 포함) 재배포.

## ⚠치명 수정(정밀분석 2026-09-25) — 옛 마스터→v4 키워드/순위 유실
소유자 "서식 포맷 정말 바뀌나 정밀분석" 요청 → **옛 코드(985cb02 워크트리)로 옛-포맷 마스터 생성 → v4 로드+저장 실측**. 발견: v3는 키워드/소헤더=**C열**, v4는 **A열**(병합 앵커). 그대로 저장 시 A:E 병합 비앵커 C값이 버려져 **키워드·순위 전멸**(판매지표·vid는 보존). 수정=`_reindex(M_RANK)` C 폴백 + `apply_style._migrate_keyword_col`(C→A 물리이전·병합해제 후). vid(헤더꼬리→col3)·판매방식(A→col11)은 기존 마이그레이션이 커버. 커밋 b68b301. **교훈: 마이그레이션 핀은 옛 포맷을 합성해 검증(신규 마스터만으론 회귀 못 잡음)** — verify_offline에 옛→v4 무손실 시나리오 추가. 배포 zip 재빌드 필요(버그본 교체).

## 후속 2건(소유자 최종점검 피드백, 2026-09-25)
- **상품명 셀 강조**: 상품명 값 칸(pos0 C:F)을 흰→상품군 색(살구↔민트 교대)·굵게. 동일 상품군을 시각적으로 묶음. 나머지 값 칸(VID/판매방식/로켓그로스)=흰 유지. 핀 S2 갱신.
- **블록 인접 정렬(분산 치유)**: 옵션이 나중 실행서 뒤늦게 발견→시트 끝에 붙어 형제와 분산(그룹 색/경계 안 묶임)되던 문제. `apply_style`에 `_group_sibling_blocks`/`_regroup_sheet_blocks` 추가 — 등록상품명 첫 등장 순서로 그룹핑해 형제끼리 인접 재배치. **행 insert 없이 값만 스냅샷→비우기→재기록**(병합·서식 apply_style 재생성이라 안전)·이미 인접이면 no-op·기존 분산 마스터도 저장 시 자동 치유. verify_offline에 값 무손실 시나리오 추가. 커밋 0a1c3e9.

## 핀/검증
pin_apply_style **S1**(A7·B7·G14·C18)·**S2**(A:B 라벨·C:F 값·pos별 텍스트·A:E 키워드 병합)·verify_offline **[7]**(판매방식=product_kind)·**[12]**(vid=메타 col3·헤더 렌더 셀). simulate `_keywords_in`=A열. 실제 덤프로 배치 눈확인(로켓그로스 3줄 병합·판매자배송 생략·키워드 A~E).

## 원래 계획(참고·전부 반영됨)

## 목표 레이아웃 (좌측 라벨 7줄 = 우측 지표 7줄과 정렬)
좌측 A:B = **라벨 칸**(지금 G열이 지표 라벨인 것과 대칭), C:F = **값**, G = 지표 라벨(기존), H~ = 값(기존).
- pos0~1: `상품명`(A:B 2줄 세로병합) · 값 C:F 2줄 세로병합 = 등록/노출상품명(노출명 괄호)
- pos2: `VID` · 값 = vid 목록('/')
- pos3: `판매방식` · 값 = 구분(로켓그로스/판매자배송/로켓그로스+판매자배송)
- pos4~6: `로켓그로스`(A:B 3줄 세로병합) · 값:
  - pos4: `쿠팡 등록 로켓그로스 판매일 : 2026-08-26`
  - pos5: `그로스요청일자 : 26.09.07 · 출고일 : 26.09.07`
  - pos6: `요청수량 : 100 · 작업수량 : 128 · 박스 : 32 · 파레트 : 2`
- 판매자배송(개인·PERSONAL 6줄)=로켓그로스 3줄 생략(pos4~ 공란), 상품명/VID/판매방식만.
- **배경색(소유자 #4 해법)**: 좌측 라벨 칸 A:B = **상품군 색(살구 f_prod↔민트 f_prod2 교대)** = 라벨+상품군 구분 겸용. 값 C:F=흰색. G 지표 라벨=연파랑(기존). 제목·계정목록 칸=기존 색. → 배경색 규칙과 충돌 없음.
- **셀 폭(소유자 #3)**: 좌측 라벨 칸(A+B 합) 폭 = 지표 라벨 칸(G) 폭 동일 → 값 칸(C:F) 자동 균형.
- 키워드 소헤더/행: 유라이프(A열 사업자명) 제거, 키워드+후보가 A~E로 좌측 확장. **키워드/검색량/비고 행 높이 = 다른 행과 동일**(#소유자).
- 계정목록 복귀 링크 문구=`👈 계정목록으로 이동`(✅이미 반영 dfd48fa).

## VID 처리 = A안 확정(소유자)
VID를 상품명과 **분리된 줄**로. → vid 저장을 **헤더 이름칸(C 'VID :' 꼬리) → 숨김 메타시트(_META_SHEET='_상품ID' col3, 옛 미사용 vid열 재활성)** 로 이전. **2026-09-20 "vid=헤더셀" 결정의 되돌림**(근거=소유자 A안 확정·레이아웃 요구). 위험=vid 저장은 과거 함정 → **핀(verify_offline 헤더/vid save-reload·pin_login_ranks) 먼저 확인 후** 구현. 옛 마스터 마이그레이션=_reindex가 meta col3 비면 헤더 'VID :' 꼬리서 폴백 읽기(무손실).

## 구현 change points (조사 완료·11곳)
1. `_meta_ws`: col3="상품ID(vid)" 재활성, col11="구분(판매방식)" 추가.
2. `set_product_vids`→ _block_vids + meta col3 기록. `product_vids` 유지.
3. `set_product_kind`/`product_kind`(meta col11) 신설. `_update_kind_label`·`ensure_product_block`→ meta col11 기록, **A(hr) kind 쓰기 제거**(line 552).
4. `_reindex`: vid를 meta col3서 복원(폴백=헤더 'VID :' 꼬리 `_vids_from_cell`). kind는 런타임 파라미터라 인덱스 불필요(표시용만).
5. `_display_name`→ **상품명만** 반환(VID/판매일/입고 꼬리 제거).
6. `input_list._inbound_summary`→ **2줄** 구조: L1 `그로스요청일자 : {요청일자} · 출고일 : {출고일자}` / L2 `요청수량 : {요청수량} · 작업수량 : {작업수량} · 박스 : {박스} · 파레트 : {파레트}`. (완료일자 미표기.) 메타 col10에 '\n' join 저장. 판매일=col9(기존).
7. `_style_metric_rows` 전면 재작성: block rows(hr..m_end)를 순서 리스트로 → pos별 A:B 라벨+C:F 값 렌더(상품군 색 A:B, 흰 C:F). 세로병합=상품명 pos0-1, 로켓그로스 pos4-6. G/H 기존.
8. `_style_block_edges`: 기존 `_sty_merge(hr,1,m_end,2)`·`_sty_merge(hr,C,m_end,F)` 전체 병합 제거 → pos별 세로병합(A:B: 상품명2·판매방식1·VID1·로켓그로스3; C:F: 상품명2 + pos2~6 단일). 마지막 블록 하단 굵은선 앵커 재조정(세로병합 앵커=openpyxl top-left border 렌더 주의, 기존 주석 참고).
9. 열너비: A+B 합 = G(14). 예: A7 B7. C~F 재배분.
10. 키워드 행 높이 통일(row_dimensions 명시).
11. 핀 갱신: pin_apply_style(헤더 라벨 셀·병합·색), verify_offline(헤더 vid save-reload=meta 경로·상품명만·라벨/값 렌더·inbound 2줄), verify_gsheet(미러링 자동 추종). simulate 영향 점검.

## 주의(회귀 함정)
- 블록 KEY=헤더행(metric=_LABEL_DATE) C셀=상품명. pos0 C=상품명 유지(=key). 다른 코드의 `_key(ws.cell(hr,_COL_NAME))` 매칭 불변.
- 지표행 C:F에 값 쓰기=_reindex는 지표행 C 안 읽음(안전)·apply_style 멱등 재생성.
- PERSONAL(6줄) vs CONTRACT(7줄) pos 정렬 분기.
- 게이트 6종+복잡도 초록·커밋 작게·[[code-health-regression-gate]] 준수.

## 이미 반영(이 세션)
- 계정목록 복귀 링크 문구(dfd48fa). 나머지=미구현.

관련: [[handoff-3decisions-260924]] [[feature-vid-source-from-product-list]] [[seldoc-output-format]] [[code-health-regression-gate]] [[fix-from-real-evidence]].
