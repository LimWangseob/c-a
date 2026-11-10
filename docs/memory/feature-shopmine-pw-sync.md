---
name: feature-shopmine-pw-sync
description: 샵마인 서버 비번을 하루 1회 받아 관리대장과 대조·자동 갱신하는 기능의 현행 규칙 위치
metadata:
  node_type: memory
  type: project
  originSessionId: 10a1299d-23ca-4c80-9194-125bb6a08ef3
  modified: 2026-11-10T15:31:33.496Z
---

현행 = **D-195 + D-196 + D-197 + D-198**(docs/DECISIONS.md) · 현행 규칙 요약 = `docs/CURRENT_RULES.md` 1절(비밀번호·로그인).

여러 줄 통일(D-198·R128): 한 계정이 여러 줄이면 **모든 줄을 샵마인 현재값으로 통일** — '같음'은 전 줄이 현재값일 때만, 한 줄만 맞고 나머지 다르면 전부 갱신(옛값 줄 잔존→로그인 거부 방지·D-012·D-190). 제약 = 계속 줄 계정ID가 비면(병합) 못 잡음(현재 대장은 줄마다 반복).

백업(D-197·R127): 비번 되쓰기 직전 관리대장 탭을 **구글시트 안**에서 복제(`백업_비번동기화_날짜시각`) — ⛔로컬 백업 금지(평문 비번)와 양립. 변경 있을 때만·dry-run 제외. `GSheetClient.duplicate_sheet`·`shopmine_sync.backup_ledger`.

실서버 검증 완료(D-196·R126): 로그인·계정조회·필드명(MarketId/MarketPassword·59건) 전부 실서버 확인, 코드 변경 0.
거부 원인 = 비번 '값' 오차 하나(캡처한 성공 로그인 본문 = 우리 코드와 완전 일치). sync `--dry-run`(미리보기·안 씀) 추가.
⛔마스터 관리대장 실 쓰기 = 사이드 세션 안 함 — 배포 후 앱 훅 자동 또는 소유자/통제 세션(첫 확인은 `sync --dry-run`).

핵심(본문은 D-195·CURRENT_RULES 참조): 담당자가 샵마인만 고쳐 어긋난 대장 비번을, 샵마인 서버 API(앱과 동일한
`api/login`→`api/read/market_account`·서버 16개 failover·시스템 프록시 무시 직접 http)로 받은 **현재값(진실 소스)**과
대조해 다르면 **관리대장(구글시트) 비밀번호 열을 자동 갱신**. 비번 평문 비노출(리포트=계정ID·상태만). 자격 =
credstore `__shopmine_login__`(사용자 getpass·Claude 비번 안 봄). 하루 1회·앱 관리대장 로드 직후·실패 비치명.

코드: `src/coupang_analytics/shopmine_sync.py`(코어) · `tools/shopmine_sync.py`(CLI setup/discover/sync) ·
`input_list.password_column` · `ui/app_qt.py` `_maybe_shopmine_sync` · 게이트 `tools/verify_shopmine_sync_offline.py`.
참조 분석 = `D:\rea\evidence\shopmine`(pktmon 캡처 파서 `parse_capture.py`).

관련: [[shopmine-architecture]] · [[feature-ledger-registry]] · [[input-ledger-format]] · [[settlement-domain-knowledge]].
