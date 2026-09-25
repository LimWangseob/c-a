---
name: session-handoff-260923
description: ⭐⭐새 세션 인계(2026-09-23). 어제 9/21 실행 보완 P1~P4 + 배포 Defender대응 + 무인 06:00 강제종료 폐지 + 순위 간격 35~55 완료·전부 푸시. **최우선=운용 PC 재배포**(지금 도는 건 옛 코드). 배포 zip 준비됨.
metadata: 
  node_type: memory
  type: project
  originSessionId: 8d66ea21-b061-4f75-bc82-b5718c630fa8
  modified: 2026-09-23T01:13:06.658Z
---

**새 세션은 이 노트 → [[followups-260921-run]] → designs 순으로.** 모든 변경 **커밋·푸시 완료**(origin/master, 최신 커밋 8e89b95, 미푸시 0, 작업트리 깨끗). 게이트=run_checks 6종 초록.

## ⭐⭐ 최우선 (막힌 것) — 운용 PC 재배포
- 오늘 고친 것(재고·링크·판매상태·순위제외·간격·강제종료폐지)은 **전부 현재 코드에 있음**. 그런데 **운용 PC는 아직 옛 코드**(소유자 "아직 배포 안했음"). 그래서 어제/지금 실행 결과엔 옛 버그가 그대로.
- **배포 zip 준비됨**: `dist\쿠팡애널리틱스_배포.zip`(158MB, 2026-09-22 19:49 빌드·오늘 코드). zip 루트+폴더에 `0_먼저실행_보안제외.bat` 동봉.
- ⚠**Defender 오탐**(미서명 PyInstaller exe=Wacatac `!ml` 자동삭제·실측): 대상 PC에서 **압축 풀기 전에** `0_먼저실행_보안제외.bat` **관리자 실행**(제외 추가) → 그다음 zip 풀고 `설치.bat`. (CLAUDE.md 함정10)

## 오늘(9/23·일부 9/22 밤) 완료 — 커밋 41683c8~8e89b95
- **P1 재고 공란 = 원인 확정·현재코드 이미 해결**: hiddenStatus 가설 **오답**(라이브 nicoable: VISIBLE=필드생략=21vid·HIDDEN=0). 진짜 원인=**'둘다'(로켓그로스+판매자배송) 상품은 같은 옵션이 NORMAL+RFM 2 vid**, RFM만 재고. **현재 `products_from_vendor_inventory`가 NORMAL 중복 제외**(오프라인 재현 증명·verify_offline[8] 핀). 어제 '베이지_' 공란=운용 PC 옛 코드·재배포+재실행 자동복구. 순수 판매자배송(히카마)은 재고행 없음(정상). 진단도구=`tools/diag_inv_hidden.py`(hiddenStatus 실험+리스팅 구조), `verify_login_discover_live.py --semi`([재고대조]).
- **P2 순위=판매중만**(`workbook.rank_suppressed`): 판매중지·임시저장·승인반려·검토중·대장취소선 ③순위 제외(미상''유지). 핀 pin_login_ranks P2.
- **P3 판매상태 정확표기**(`collector.sale_status_of`): DRAFT→임시저장·REJECTED→승인반려·**UNDER_REVIEW→검토중**(기존 판매중지 뭉갬). apply_sale_status 단일상태 보존·status_of 표기. 핀 verify_offline[8]·pin_apply_style S7.
- **P4 계정목록 링크=현재코드 정상**(`#gid={사업자통계시트}&range=A{헤더행}`). **실제 gsheet 읽어 확정**: 지금 시트엔 옛 코드가 쓴 `#gid={계정목록gid=1095977957}&range=A1`(자기탭)뿐 → 재실행하면 plan_sync가 C열 다시 써서 복구. 현재코드 검증=실제 사업자 gid로 `#gid=1470813641&range=A3` 나옴(정상). 핀 verify_gsheet t6.
- **배포 Defender 오탐 대응**: `deploy/0_먼저실행_보안제외.bat` 신설·build.bat 항상 zip 루트+폴더 동봉·install.ps1 0.4단계 `$root` 제외·첫실행_설정안내 0)단계. CLAUDE.md 함정10·[[exe-packaging-deploy]].
- **무인 06:00 강제종료 폐지**(소유자 지시): `_schedule_auto_stop`/`_auto_stop` 삭제(start_auto·start_resume 호출 제거). **어떤 경우에도 강제종료 금지 — ①②③+재고역기록 완주 후 `_auto_done`만.** 서킷브레이커로 무한대기 없음. CLAUDE.md §현재상태.
- **순위 검색 간격 45~75 → 35~55초**(소유자·시간단축): `config.py RANK_NAV_DELAY_MIN/MAX_SEC`. ⚠첫 실행 로그에 `쿨다운`/`차단` 뜨면 45~75로 되돌릴 것. 추가 하향은 단계적.

## 남은 것 / 다음
- **(A) 계정목록 링크 즉시 재작성**(소유자 "실행 끝나면"): 실행 종료 후 요청 오면, 최신 코드로 `계정목록` 링크만 재작성 가능(sync_index=그 탭만·직원 마케팅 E~G 보존). 또는 재배포+재실행이면 자동. **⚠지금 다른 PC서 실행 중 → gsheet 동시접근 금지**.
- **순위 간격 35~55 실측 확인**: 첫 최신-코드 실행 로그에서 차단/쿨다운 0이면 유지.
- **③순위 라이브(핫스팟)**·**4파일 MI C→B 모듈분리**(코드건강 잔여, [[handoff-code-health]]).
- 18:00 무인 창 즉시닫힘(어제): 로직상 start_auto 조기종료 2조건(입력 None/키 미설정)뿐 — 운용 PC 로그로 확정 필요(이 저장소엔 로그 없음=다른 PC).

## 상태 스냅샷
- 커밋 8e89b95(HEAD=origin/master)·미푸시 0·작업트리 깨끗. 배포 zip 준비. 게이트 6종+품질 초록.
- 관련: [[followups-260921-run]] [[handoff-code-health]] [[exe-packaging-deploy]] [[fix-from-real-evidence]] [[commit-with-design-and-memory]].
