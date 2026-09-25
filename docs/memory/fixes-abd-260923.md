---
name: fixes-abd-260923
description: A·B·D 진행(2026-09-23). A-1 재링크 도구·B-1 순위요약 로그 완료·D는 라이브 불가로 진단도구만(수정 보류). 설계서=designs/FIX_ABD_260923.md. pytest Stop훅 오탐 주의.
metadata:
  node_type: memory
  type: project
  originSessionId: dc7fcb2b-acc9-4522-a5a2-32fe7a65b849
  modified: 2026-09-23T12:55:36.061Z
---

소유자 지시 "A,B,D 진행, 먼저 설계서 작성" → 설계서 [designs/FIX_ABD_260923.md] 승인 후 A-1·B-1·D 구현.

## 완료 (게이트 run_checks 6종+check_complexity 초록)
- **A-1 완료 — `tools/relink_index.py` 신설**: 전체 실행(로그인·수집·순위·통계 미러링) 없이 **gsheet만 접근**해 결과 구글시트 `계정목록` 링크(C열)만 재작성. 존재하는 사업자 통계 시트 gid만 `client.sheet_id`로 조회(빈 시트 생성 안 함)→`roster_from_workbook`→`sync_index`. 마케팅 E~G·직원 키워드 미접촉(sync_index 보장). 옛 코드가 남긴 자기참조 링크(`#gid=계정목록&range=A1`) 복구용. 실행: `python tools/relink_index.py [출력URL] [마스터.xlsx]`(URL 없으면 appconfig gsheet/output_url).
- **B-1 완료 — 순위 종료 요약+되돌림 권고**: `pipeline._SemiState`에 누적 카운터(searched·cooldown_total·blocked_total, 진전 리셋 안 함) + `_semi_summary_log`. ③순위 종료 시 `[순위요약] 측정N·쿨다운C·차단K·간격35~55` 출력, 차단/쿨다운>0이면 `RANK_NAV_DELAY 45~75 되돌림 권고`(로그 grep 없이 판단). 핀 pin_login_ranks J(무차단)·K(권고) 추가. 소유자가 35~55로 낮춘 뒤 차단 감시용([[semi-auto-rank-and-exposed-name]]).
- **D 진단만 — `tools/diag_inv_hidden.py` 확장**: '둘다'(RFM+NORMAL) 리스팅에서 **고유 NORMAL(RFM 이름짝 없음) 개수 + 이름 일치 여부** 자동 판정(`_diag_both_normal`). collector.py의 '둘다 NORMAL 전부 제외'가 RFM 짝 없는 NORMAL 고유옵션 지표를 잃는지 확인용. **안전판 코드 수정은 라이브 확인 전까지 보류**(집=라이브 불가·근거 없는 수정=이중집계 회귀). 사무실/핫스팟서 `python tools/diag_inv_hidden.py <계정ID>` → 고유 NORMAL>0이면 수정(이름 겹치는 NORMAL만 제외)·0이면 헛수정 확정. [[fix-from-real-evidence]].

## ⚠ A-1 실행은 **현재 마스터가 있는 PC(운용)에서만**
- 커밋 b33f5c7·73d82fb(레지스트리 폴백). 실행 시도했으나 **이 노트북 마스터는 낡음**(9/18·사업자 23·최신 09.17) vs **라이브 구글시트 ~25 사업자·9/22~23**. `sync_index`는 증분(갱신+삽입+**판매중지 표기**)이라 낡은 마스터로 돌리면 라이브에만 있는 계정을 **판매중지 오표기**+링크행 어긋남 → **노트북에서 실행 안 함**(read-only 대조만). CLAUDE.md 함정#9(낡은 상태→gsheet 오염)와 동일.
- 안전 실행 경로: (1) **운용 PC에서** `python tools/relink_index.py`(현재 마스터+레지스트리 URL) 또는 (2) 다음 야간 실행의 `_push_gsheet`가 링크 자동 재작성(A-2 폴백·기다리면 됨). 노트북서 하려면 운용 PC 현재 마스터를 먼저 복사.

## A 재조사 — 계정목록 링크 (라이브 직접 확인, 2026-09-23)
- 라이브 결과 구글시트(SA 읽기) 직접 확인: **C열 상품 링크 123개 전부 자기참조**(`#gid=1095977957`=계정목록 자기&range=A1)·정상 링크 0·E/F/G(직원 마케팅) **전부 공란**(재작성해도 잃을 것 없음).
- 원인: 계정목록이 **옛 노출명**으로 만들어짐. 현재는 옵션라벨(`(1개 120정)`)·이름변경·상품제외로 이름이 바뀜(현재 노출명=통계시트/마스터). 증분 sync 는 등록명 키 불일치로 **그리드(177) 초과 insertDimension 400** 실패 → 비치명적 삼켜져 계정목록 방치. **상품명 규약**=[[product-name-convention-ledger-vs-result]](결과=쿠팡 노출명).
- **링크만 제자리 수리 도구 `tools/relink_index_inplace.py`**(드라이런 기본·--write 적용·C열만·이름/데이터/E~G 미접촉): 라이브 통계 시트에서 블록헤더행(G열=='날짜')로 {노출명:행} 맵→계정목록 C열 링크 재작성. **드라이런 실측: 정확매칭 54/123뿐**(접두35·포함15·전혀못찾음19) — 계정목록 이름도 낡아 링크만으로는 54~89만 고쳐지고 억지 추정매칭은 잘못된 링크 위험.
- **✅해결 완료(소유자 승인 "전체 재작성")**: `tools/rebuild_index.py`(드라이런 기본·--write 적용)로 계정목록 **데이터행만** 현재 마스터 로스터로 재작성(제목/헤더/틀고정/열너비 미접촉·직원 E~G 값 미접촉). 옛 잔재 데이터행 deleteDimension. **검증(라이브 재조회): 자기참조 123→0·사업자링크 114·데이터 128→116행·E/F/G=0 유지·헤더 정상·제목 '상품 76개'.** 운용 마스터=`.../62f4eccc.../scratchpad/run260922/쿠팡데이타분석_통계.xlsx`(오늘06:52·26계정). 앞서 "이름 정상이니 링크만"은 오판(이름도 낡음→relink_index_inplace 드라이런서 54/123만 매칭 확인→전체재작성으로 전환).
- 도구 3개: relink_index(sync기반)·relink_index_inplace(링크만·부분)·rebuild_index(전체재작성=A 해결).

## ✅ 현행화 버그 수정(그리드 자동확장 + 로그 강화, 2026-09-23)
소유자 질문 "계정목록 매 작업시 대장 기준 현행화되나?" → 확인 결과: **설계상 YES**(①에서 계정 추가/삭제/상품 추가·삭제[삭제=판매중지 표기]/수정 대조 → _push_gsheet→sync_index), **실제론 방치**(sync_index 증분 삽입이 그리드 끝 넘으면 insertDimension 400 → _push_gsheet 비치명적으로 삼킴). **수정 완료**:
- `gsheet_api.grid_row_count()`(meta에 gridProperties.rowCount) + `gsheet_index._grid_grow_requests`(삽입 전 헤더2+데이터+여유50 미만이면 appendDimension으로 행 확장·전체빌드/증분 양쪽). insertDimension은 startIndex<rowCount라야 400 안 남. **다음 운용 실행이 자동 치유**(현재 그리드 118 부족→append).
- `_push_gsheet` except 로그 강화(❌❌ 계정목록/통계 최신 아닐 수 있음 3줄). 테스트 `verify_gsheet_offline t3d`. 게이트 6종 초록.
- ⚠참고: ②키워드·③순위 개별 실행은 대장 재대조 안 함(현재 상태만 push)=①의 역할. 상품 삭제=행 제거 아니라 판매중지 표기(이력 보존).

## 재고 공란 재분석(운용 output 260923 실측) — 묶음변형이 원인
- 운용 18:00 실행 로그: **[재고오류] 108건** = `상품조회 옵션 vid ≠ 재고 API vid`. 마스터 재고행 **값 80·공란 130**(웰빙곳간 값16·공란78 최다).
- 패턴 확정(웰빙곳간): 값=**1개/기본/30개(단일단위)**, 공란=**2·3·4·5·6개·60~180개(묶음/수량 변형)**. **모든 공란 블록 block_vid=1개**(RFM vid 제대로 저장됨·혼동 아님).
- 결론: 코드는 **이미 RFM vid exact 매칭**(소유자 제안 #1=현재 동작). 100% 안 되는 건 **묶음변형은 로켓그로스 재고 API에 별도 기록이 없어서**(기본 단위 재고에서 차감되는 구성품). vid 저장 버그 아님. 해결 지점은 #2(변형 표시 방식)=묶음변형을 개별 행 말고 로켓 대표 1개만 표기할지 **소유자 결정 대기**(2026-09-20 옵션분리 결정 되돌림이라 근거 필요).
- **진단을 파이프라인 본체에 직접 반영**(소유자 "별도 도구로 하지 말고 소스에 직접" — exe 재빌드해 운용 PC서 정상 실행에 로그로 남김): `config.DIAG_VID_LOG=True`(임시·분석후 False) + `pipeline._log_vid_compare`(a,listings,inventory,log)를 `_discover_products` 재고조회 직후 호출. 실행 로그에 `[vid대조 계정]` [A]옵션별(vid|로켓그로스/판매자|valid|상품상태|재고|이름) [B]재고 API 전체 vid [C]RFM인데재고없음/재고인데RFM없음. 진단 로깅은 try/except로 수집 절대 안 깸(건너뜀 명시). 스모크 검증: 1개vid=재고,2개묶음vid=재고없음 정확 판정. 앞서 도구(fd93231)판 `_diag_vid_compare`는 제거(중복). ⚠운용 PC에 최신 exe 재배포 후 야간 실행하면 로그 생성 → 그 로그로 확정.

## ⚠ 함정 — pytest Stop 훅 오탐
- 전역 Stop 훅 `~/.claude/hooks/on-stop.sh`가 커밋 안 된 .py 변경 시 `pytest -q`를 돌리는데, **이 저장소엔 pytest 테스트가 0개**(회귀망=`tools/run_checks.py`)라 pytest가 **exit 5(no tests ran)**를 내고 훅이 이를 실패로 차단함. 실제 회귀 아님.
- 근본 해결=훅 22~23줄 아래 `[ "$rc" -eq 5 ] && exit 0` 한 줄 추가(exit5=수집0=회귀 아님·수집에러는 2/3). **이 훅 수정은 Self-Modification로 Claude 자동거부됨 → 소유자가 직접 적용해야 함**(2026-09-23 미적용). 커밋 후엔 .py 미변경이라 훅이 안 돌아 차단 안 됨(우회 아님·정상).

관련: [[session-handoff-260923]] [[bugfixes-260923-source-review]] [[commit-with-design-and-memory]] [[fix-from-real-evidence]].
