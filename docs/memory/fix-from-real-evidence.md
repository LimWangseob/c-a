---
name: fix-from-real-evidence
description: 오류 수정은 추측 금지 — 로그·처리상태를 점검하는 코드로 실제 오류를 확인 후 수정
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 4ca6f1ec-575b-4e8e-8476-c3c67cf979b3
  modified: 2026-09-06T00:20:21.968Z
---

버그 수정 시 **추측으로 고치지 말 것.** 로그와 처리 상태를 점검하는 코드를 먼저 보완해
**실제 오류(에러 메시지·파일 내용·이벤트)에 근거**해 수정한다. 사용자가 반복 강조함.

**Why:** 추측 수정은 헛발질을 낳음. 실례로 리포트 다운로드 실패를 "크롬 파일명 충돌"로 추정했으나,
진단 로그를 넣자 진짜 원인은 `PermissionError`(openpyxl read_only 핸들 미close로 파일 잠금)였음.

**How to apply:** ①진단 로그를 단계마다 남기고(타임스탬프 `[YYYYMMDD_HHMMSS]` 포함, 싱크는 `ui/app_qt.py` `_append_log` 한 곳) ②실패 시 파일/이벤트/페이지상태를 직접 열어 확인 ③확인된 사실에만 근거해 수정 ④응답은 "확정 사실 → 수정" 순으로. 관련 [[respond-in-korean]].
