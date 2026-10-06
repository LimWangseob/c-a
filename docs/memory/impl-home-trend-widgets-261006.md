---
name: impl-home-trend-widgets-261006
description: "시안 세부 승격 1차(2026-10-06, H_ui) — 기간 알약·▲% 비교 배지·알약 막대를 공용 위젯으로, 통합앱 홈 '변동 추이' 카드에 실데이터(통계 마스터)로 적용"
metadata:
  node_type: memory
  type: project
  originSessionId: 79abfabd-474e-43dd-b9c0-fa674af4113c
  modified: 2026-10-06T07:14:48.557Z
---

**시안 세부 승격 1차 완료(2026-10-06, domain/h-ui)** — 소유자가 첫 적용 화면으로 "홈 대시보드 변동 추이" 선택.

- `ui/widgets_qt.py`(UI_SCREENS §5 제안 파일): PeriodPills(알약 묶음·dim=회색 '준비 중')·DeltaBadge(▲초록/▼빨강/비교불가=숨김)·KpiTile·PillBarChart(paintEvent·트랙+둥근 막대·선택만 진보라+말풍선·클릭 선택). 모양은 `ui/theme_qt.py` 토큰+QSS(objectName pill·pillDim·badge[tone]·card·kpiValue).
- `ui/home_trend.py`(Qt 없음): 통계 마스터 → 날짜별 집계. 탭=노출순위(1페이지 안 키워드 수+평균 순위)·판매현황·방문자·검색량(=노출량). **빈 날=None(공란)**. 비교=지난주 같은 요일.
- `ui/home_page_qt.py`: 홈 = 화면 머리(경로·제목·마지막 데이터일·새로고침·기간 알약 최근7일/14일/이번달)+변동 추이 카드. 매출·수익 탭=준비 중. 파일 없음/읽기 실패는 카드에 이유 표시.
- 검증: `tools/verify_home_trend_offline.py`(18항목·offscreen 스모크 포함). **run_checks 미등록**(공유파일=통제 세션에 등록 요청).
- ⚠ 시안 문구 "1페이지(36위 안)"와 달리 **실측 상수 `config.RANK_ORGANIC_PER_PAGE`=60** 사용 — 소유자 확인 대상.
- 기존 app_qt 미접촉([[keep-existing-app-running-until-integrated]]).

**Why:** 시안 컨셉(④⑤⑥)을 앱 부품으로 한 번 만들어 이후 화면(상품 상세 01-6 등)에서 재사용.
**How to apply:** 다음 승격은 같은 위젯 재사용(새로 만들지 말 것). 남은 홈 요소=경영 요약 KPI·노출순위 변화 목록·계정별/상품별 표. [[handoff-design-mockup-261006]] · [[decision-design-concept-261003]] · [[impl-integrated-app-shell-261005]]
