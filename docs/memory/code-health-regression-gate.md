---
name: code-health-regression-gate
description: "회귀 방지 규칙 — 커밋/푸시 전 tools/run_checks.py 게이트 통과 필수, 테스트서 실 API 금지, 되돌림은 근거 메모, 건강 파일 미접촉."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f52eddd4-0df1-43c9-85b6-f727c8e7d5a7
  modified: 2026-09-22T01:19:05.471Z
---

**코드 건강 규칙(2026-09-22 구축, CLAUDE.md "코드 건강 규칙" 섹션·SSOT=`designs/CODE_HEALTH_PLAN.md`).**

**Why:** 잦은 수정으로 4파일(pipeline·workbook·app_qt·app)이 비대·괴물함수화되고 "과거 정상→오류" 회귀가 반복됨(판매상태 RFM↔productStatus 3회 왕복 등). 막을 게이트가 없어 회귀가 계속 유입됐다.

**How to apply:**
- 커밋/푸시 전 `python tools/run_checks.py`(전체 3종·오프라인·결정적) 초록 필수. git 훅 자동(pre-commit=`--quick`[시뮬+구글시트], pre-push=전체+`tools/check_complexity.py`). 새 PC는 `python tools/install_hooks.py` 1회. `--no-verify` 상시 금지.
- **테스트서 실 API 금지**: 검증 3종은 로그인·OpenAI·네이버 호출 없이 돈다. `verify_offline` [6] 키워드 선정은 기본 결정적 모킹(`_ask`/`_client`/네이버 경계만 페이크), 실 API는 `VERIFY_REAL_API=1` 옵트인.
- **품질 게이트**: `check_complexity.py`가 4파일 밖 새 D+(CC≥21) 괴물함수 경고 + 건강하던 파일 MI C 추락 시 차단. 새 함수 CC≤15·파일≤~600줄 지향.
- **A등급(건강) 파일 미접촉**(불필요 변경=새 회귀). 4파일 수정 시 핀 테스트 먼저.
- **되돌림/정책 변경은 실측 근거 메모 필수**([[fix-from-real-evidence]], 플립플롭 방지). 분해는 행동 불변(위치만 이동, 커밋 작게·자주 [[commit-with-design-and-memory]]).

관련: [[handoff-code-health]] [[fix-from-real-evidence]] [[commit-with-design-and-memory]].
