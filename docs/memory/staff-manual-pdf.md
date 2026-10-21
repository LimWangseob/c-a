---
name: staff-manual-pdf
description: 결과 구글시트 활용 매뉴얼(직원용 PDF) — 위치·생성 스크립트·소유자 문구 규칙(2026-10-21)
metadata:
  node_type: memory
  type: project
  originSessionId: 7da243e3-c003-4a1b-a07c-cb3ea7d34058
  modified: 2026-10-21T13:46:55.359Z
---

직원용 **[쿠팡] 데이터 분석 통계 구글 파일 — 활용 매뉴얼** PDF(A4 가로 9쪽).
- 결과물·캡처 = `output/직원매뉴얼/`(git 밖·판매 금액 그대로) · 생성 = `python tools/build_staff_manual.py`(HTML+빨간 번호 상자 → Chrome headless PDF).
- 캡처는 **판로 프로필 Chrome**(커머스 판로 계정·Claude in Chrome 연결)에서 — limws0652 프로필은 결과 시트 권한 없음(액세스 거부).
- 소유자 문구 규칙: 파일·시트·칸 이름은 **화면 표기 그대로**('탭' 아님 '시트', '관리대장' 아님 '[셀독] 관리 대장') · '직원 사용' 문구 없음 · 1쪽 = 요약(꼭 지킬 것 4가지: 상품명=쿠팡 노출·등록상품명이어야 AI 매칭 / 대장 수정 18시 전 / 키워드 추가·변경·삭제 최대 10개 / 계정 줄 삭제·전부 숨김=이력 삭제) · 쪽마다 위아래 여백 균형·설명은 짧게.
- 남은 일: 새 버전 설치 뒤 계정목록(9열 D-109)·사업자명 시트(순위 채워진 화면) 재캡처.

**Why:** 직원이 결과 파일을 쉽게 쓰도록(소유자 2026-10-21). **How to apply:** 매뉴얼 수정은 스크립트를 고쳐 다시 생성 — PDF 직접 편집 금지. 관련 [[gsheet-unified-spec]] · [[feature-sales-summary-first-sheet]].
