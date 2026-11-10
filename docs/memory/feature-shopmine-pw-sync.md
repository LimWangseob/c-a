---
name: feature-shopmine-pw-sync
description: 샵마인 서버 비번을 하루 1회 받아 관리대장과 대조·자동 갱신하는 기능의 현행 규칙 위치
metadata:
  node_type: memory
  type: project
  originSessionId: 10a1299d-23ca-4c80-9194-125bb6a08ef3
  modified: 2026-11-10T09:03:25.307Z
---

현행 = **D-195**(docs/DECISIONS.md) · 현행 규칙 요약 = `docs/CURRENT_RULES.md` 1절(비밀번호·로그인).

핵심(본문은 D-195·CURRENT_RULES 참조): 담당자가 샵마인만 고쳐 어긋난 대장 비번을, 샵마인 서버 API(앱과 동일한
`api/login`→`api/read/market_account`·서버 16개 failover·시스템 프록시 무시 직접 http)로 받은 **현재값(진실 소스)**과
대조해 다르면 **관리대장(구글시트) 비밀번호 열을 자동 갱신**. 비번 평문 비노출(리포트=계정ID·상태만). 자격 =
credstore `__shopmine_login__`(사용자 getpass·Claude 비번 안 봄). 하루 1회·앱 관리대장 로드 직후·실패 비치명.

코드: `src/coupang_analytics/shopmine_sync.py`(코어) · `tools/shopmine_sync.py`(CLI setup/discover/sync) ·
`input_list.password_column` · `ui/app_qt.py` `_maybe_shopmine_sync` · 게이트 `tools/verify_shopmine_sync_offline.py`.
참조 분석 = `D:\rea\evidence\shopmine`. 남은 = 사용자 1회 실서버 discover/sync(필드명·ShopmineVersion 확정).

관련: [[shopmine-architecture]] · [[feature-ledger-registry]] · [[input-ledger-format]] · [[settlement-domain-knowledge]].
