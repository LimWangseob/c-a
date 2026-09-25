---
name: reboot-recovery
description: 재부팅 자동복구 — 야간 Windows 업데이트 재부팅 시 중단분을 --resume으로 순위부터 이어서. 앱통합 완료
metadata: 
  node_type: memory
  type: project
  originSessionId: 5f5772f7-fc22-427b-91e7-3a1e2d3bf916
  modified: 2026-09-16T05:16:34.401Z
---

**계기**: 2026-09-16 01:29 **Windows 업데이트(TrustedInstaller) 자동 재부팅**으로 전체실행이 중단(③순위 59% 지점, 이벤트로그 확정). 앱 종료가 아니라 OS 재부팅이 원인.

**구현(2026-09-16, 완료·검증)**:
- **단계 마커** `pipeline.write_run_stage/read_run_stage` → `output/쿠팡데이타분석_실행단계.json`(오늘 날짜+stage). stage=`sales`(①판매 완료·다음②)·`ranks`(②키워드 완료·다음③)·`done`. ②③은 마스터에 직접 써서 진행중 파일을 안 남기므로 별도 마커 필요.
- **`--resume` 복구 모드** `app_qt.start_resume`: 마커+`resumable_progress`(①진행중 파일)로 판단 — 진행중있음→①부터, 마커`sales`→②③, `ranks`→③만, `done`/없음→즉시 종료. **판매수집(재로그인) 스킵**이 핵심(위탁계정 재로그인 부담 회피). ③은 이미 채워진 순위 건너뜀(멱등).
- 마커 기록: `do_run_full`(전체실행)·`start_auto`(무인)·`start_resume` 모두 ①후sales·②후ranks·③+재고후done.
- **작업 스케줄러 '로그온 시' 트리거**=`--resume`(`deploy/install_schedule.ps1`에 `쿠팡애널리틱스_재부팅복구` 추가, 로그온 2분 지연). 야간무인(18:00)은 그대로.
- ⚠ **선결: Windows "업데이트/재시작 후 로그인 정보로 자동 로그인 완료" 켜야** 재부팅 후 세션 복원돼 앱이 뜸(반자동은 잠긴 세션도 CDP로 동작). 안 켜면 잠금화면서 대기→복구 불가.

**예방(사용자 설정함)**: Windows 업데이트 활성시간 **17:00~10:00 수동**(그 시간 자동재시작 억제, 최대 18h). 100%는 아니라 복구가 근본책.

**⏭ 남은 조치**: ①사용자가 install_schedule.bat 재실행(새 작업 등록)·Windows 자동로그인 켜기. ②**어제(09-15) 중단분은 마커 없어 자동복구 안 됨** → 앱 "③순위(반자동)"로 수동 마무리(순위 41%+재고+구글시트). ③이 세션 작업 전체 커밋 필요(상세이미지·창크기·재부팅복구). [[commit-with-design-and-memory]] [[login-block-session-first-circuit-breaker]] [[session-current-state]]
