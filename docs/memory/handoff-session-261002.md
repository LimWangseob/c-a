---
name: handoff-session-261002
description: "새 세션 진입점(2026-10-02 최신) — 노출순위 프록시 egress 회전+차단IP목록+이미지OFF실험 구현·커밋·푸시 완료, 다음=밤샘 규모검증"
metadata:
  node_type: memory
  type: project
  modified: 2026-10-02T07:53:25.172Z
  originSessionId: 202b4f12-0f1f-42a1-a7eb-39526738003d
---

**새 세션 진입점 — 현재 상태 SSOT (2026-10-02 최신)**

master HEAD=`7d27720`(origin 동기화됨·clean). 게이트 10종+복잡도(경고0)+프록시 핀 11종 초록.

## 이 세션에서 한 일 (전부 커밋·푸시 완료)
1. **분석**: 새벽 차단 원인=egress IP 평판(코드 무결·홈 GET까지 Access Denied로 증명). "고정=신뢰"는 로그인에만·순위는 회전(맥락 분리, [[proxy-ip-policy-by-context]]).
2. **egress 재회전 + 차단 egress IP 목록 구현**([[proxy-rotation-design-261002]]): 차단 시 쿨다운 전 새 egress 회전(`RANK_PROXY_ROTATE_MAX`)·차단당한 실제 egress IP(브라우저 IP에코)를 `rank_blocked_ips.json`(gitignore·72h TTL)에 기록→(재)기동 시 이력 IP 선제 skip. **순위 3경로 전부**(자동·반자동 stage·전체실행 site3). 신규 `proxy_blocklist.py`·`drive_rank`·`pick_rank_proxy`·신호 `_RANK_HALT["rotate"]`. 커밋 b299523→0267133→7d27720.
3. **이미지 OFF 실험 플래그**: `config.json rank/block_images`(기본 OFF=이미지 켬)·`--blink-settings=imagesEnabled=false`.
4. **proxies.txt = sessid 8줄**(DataImpulse `;sessid.sNN`=서로 다른 고정 sticky IP 풀). 진단도구 `tools/test_rank_images_live.py`·`probe_proxy_pool.py`.
5. 설계서(DESIGN §0-0000000000)·정책(CLAUDE.md 모듈·제약🔌·현재상태)·DECISIONS·메모리 반영.

## ⭐ 최우선 다음 작업
1. **첫 밤샘 전체실행 규모검증**(사무실 PC·271키워드): ①회전 실효(차단 시 새 IP로 넘어가 완주하는지) ②**이미지 ON/OFF A/B**로 ~60% 절감 안전성 판정. run_log 2개(차단감지 수)+DataImpulse USED TRAFFIC 비교→제가 판정. **단발 테스트는 IP 평판 변동으로 불가**(규모/대수의 법칙으로만).
2. **운용 PC 재배포**: 이 세션분 + 누적분([[handoff-session-260929-continued]]). proxies.txt sessid 여러 줄 + config.json proxy/enabled·allow_auth + rank/block_images(원하면). ⚠exe 재빌드 필요(코드 변경).
3. teardown Fetch 노이즈 가드(비치명): browser.py `_on_paused` 가 닫힌 세션에 continueRequest→TargetClosedError 로그.

## 핵심 실측 통찰 (잊지 말 것)
- **egress IP 평판이 수분 단위로 clean↔blocked 변동**(풀 9개 중 3개만 순간 clean·깨끗IP가 이미지ON인데도 차단). → 회전+차단목록이 필수이자 유효·이미지 변수는 단발로 분리 불가.
- 이미지≈SERP **60%**(절감 잠재력 실측)·"99% 절감"은 OFF 차단 시 에러페이지라 생긴 허수.
- **프록시 자격증명은 차단과 무관**(브라우저↔프록시 사이·쿠팡 못 봄). sessid 줄마다 id+비번 반복은 정상.

## 게이트/커밋 규칙
- 커밋 전 `python tools/run_checks.py`(10종) 초록. 새 클론=`python tools/install_hooks.py` 1회.
- 커밋=코드+설계서+메모리+DECISIONS 동시. proxies.txt·rank_blocked_ips.json·config.json=gitignore(커밋 금지).
- ⚠bash 에서 commit -m 멀티라인=`-F 파일` 사용(PowerShell `@'...'@` 금지 — 제목에 @ 붙음).

[[proxy-rotation-design-261002]] · [[proxy-ip-policy-by-context]] · [[proxy-live-test-261002]] · [[handoff-session-260929-continued]] · [[code-health-regression-gate]]
