---
name: impl-integrated-app-shell-261005
description: 통합 앱 실행 셸 1차 — ui/app_integrated.py(v3.3 사이드바+신규 도메인 작동 패널·로컬 JSON 저장·기존 app_qt 미접촉)
metadata:
  node_type: memory
  type: project
  originSessionId: c48bfd01-5750-43b7-bf3c-9d574e709d12
  modified: 2026-10-05T14:52:54.644Z
---

**통합 앱을 실제로 실행해볼 수 있게 만든 1차 셸**(소유자 "통합앱 실행해볼 수 있게"). H_ui 레인, worktree `integrated-app-shell`. **기존 운영 앱(ui/app_qt.py) 미접촉**([[keep-existing-app-running-until-integrated]]) — 별도 진입점.

## 실행
```
python ui/app_integrated.py
```
(기존 앱은 그대로 `python ui/app_qt.py`. 둘은 완전 별개.)

## 무엇을 (전부 greenfield·ui/)
- `ui/app_integrated.py` — 실행 셸. 헤더(회사명+🏠홈) + **v3.3 사이드바 대분류 13** + QStackedWidget(홈 + 13페이지). 기존 app_qt QSS(teal Fluent) 축소판 재사용.
- 신규 도메인 **실제 작동 패널**(내가 구현한 store 연결):
  - `ui/cs_panel_qt.py` — 05 문의/CS: 접수·상태변경/응대 이벤트·목록(상태 replay)·가림·통계. (cs_gsheet/cs_store/cs_model)
  - `ui/contract_panel_qt.py` — 11 계약: 등록/개정·해지·as_of 목록·역할별 민감 가림·만료예정 빨강. (contract_store)
  - `ui/worklog_panel_qt.py` — 11 업무일지: 작성·목록·진행 7일경과 빨강. (worklog_store)
  - `ui/creditor_panel_qt.py` — 12 채권자: 등록·채권/상환 기록(정정=반대기록)·잔액·2단계 가림. (creditor_store)
  - `ui/panel_kit.py` — 공용 헬퍼(카드·표·폼·버튼·오류 QMessageBox).
- 나머지 9 대분류(상품·가격·재고·정산·마케팅·통계·판매처·셀독·당근·설정) = "기존 앱에서 운영 중·통합 예정" placeholder.
- `ui/local_sheet_client.py` — **로컬 JSON 백엔드**(구글 자격증명 불필요). store들이 쓰는 구글시트 클라이언트 인터페이스를 덕타이핑으로 구현(sheet_titles·ensure_sheets·read_values·write_values·batch_update[insertDimension]). 데이터=`output/통합앱_data/*.json`. **나중에 실 GSheetClient 로 인자만 교체**해 끼움.

## 검증
offscreen 스모크(`QT_QPA_PLATFORM=offscreen`): 창 구성 14페이지(홈+13) + 4도메인 데이터 경로(worklog append·contract 가림·creditor 잔액 70만·cs 완료·재로드) 통과. 게이트 14종·복잡도/건강 초록. **버그 수정**: 계약 패널에 필수칸 '계약일자'가 빠져 항상 검증 실패하던 것 발견·추가(스모크가 잡음).
- ⚠ headless 환경은 한글 글리프를 못 그려 스크린샷이 □로 나옴 — **실제 PC(맑은 고딕)에선 정상**(app_qt와 동일 폰트 경로). UI는 run_checks 게이트 대상 아님(기존 app_qt도 미포함).

## 남은 것
- `ui/theme_qt.py`(QSS 토큰화·디자인 컨셉 [[decision-design-concept-261003]])·기존 app_qt 7탭 **승격**(내용 보존)·실 GSheet 배선(config URL)·v3.3 중분류 84·시안(Design 캔버스) 반영(H_ui 소유).
- 로컬 JSON은 **실험/미리보기용** — 운영 데이터는 통합 완성 시 구글시트/실 저장소로.

[[handoff-session-261005]] · [[impl-d8-absorb-ledger-261005]] · [[impl-d10-cs-tracker-261005]] · [[runtime-ui-and-always-on]]
