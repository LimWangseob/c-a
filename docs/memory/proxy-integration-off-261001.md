---
name: proxy-integration-off-261001
description: 계정별 고정 프록시(a-모델) 통합 — 소유자 보안하드닝본 적용·기본 OFF·게이트 초록·미커밋
metadata:
  node_type: memory
  type: project
  originSessionId: b9af6ec6-eafc-49f0-94ea-0dd7e7402bbb
  modified: 2026-10-01T13:17:53.625Z
---

**프록시(계정별 고정·a-모델) 통합 — 기본 OFF·미커밋 (2026-10-01)**

소유자가 다운로드 `proxy_manager.py`를 (a) "계정별 고정 residential(한 계정=한 IP·회전 없음)"로 연동 요청 → 구현 완료하되 **기본 OFF**(켜지 않으면 기존 동작 100% 동일). 소유자 결정=**2번(OFF 보존)+3번(직접 진행)**, 변경 소스 ZIP 전달받아 직접 마무리.

## 변경/신규 (5+핀)
- 신규 `src/coupang_analytics/proxy_manager.py`(이식)·`proxy_pool.py`(계정별 고정 배정=명시맵 우선·없으면 sorted 풀 sha256(account_id)%N 안정 해시·런타임 외부호출 없음).
- `config.py` 끝: `PROXY_ENABLED=False`·`PROXY_FILE="proxies.txt"`·`PROXY_ACCOUNT_MAP={}`·`PROXY_ALLOW_AUTH=False`.
- `browser.py`: `WingBrowser(proxy=)` → Chrome `--proxy-server={scheme://host:port}`(자격증명 분리)·`_maybe_setup_proxy_auth`(user:pass면 CDP Fetch continueWithAuth·PROXY_ALLOW_AUTH 명시 허용 때만·요청내용 미변경)·`_redacted_proxy`(로그 가림)·__exit__ cdp detach.
- `pipeline_sales.py`: 두 로그인 지점(try_login_once·_login_and_discover)에 `_account_proxy()` 배선(매 실행 1회 로드·캐시).
- **핵심 원리**: collector가 `page.evaluate(fetch)`로 브라우저 안에서 API 호출 → `--proxy-server` 한 곳이면 로그인·수집·순위 전부 그 IP. collector 무수정.

## 미완/주의
- **게이트 핀 `t1_proxy_pool()`는 verify_offline.py에 함수로 존재하나 main() 등록 1줄이 안전분류기에 "Security Weaken"으로 차단** → 소유자가 직접 등록(main 안 `t1_coupang_check_compute()` 다음에 `t1_proxy_pool()`). 우회 안 함.
- 독립 오프라인 검증은 통과(OFF 기본 보존·계정별 결정적 배정·자격증명 분리·로그 평문 금지).
- **엔지니어 권고**(Claude·소유자에 전달): 프록시는 Akamai 제약을 못 풀고 **위탁계정 밴 위험만 추가**. 회전 금지·residential+IP화이트리스트만. 켤지는 소유자 판단.
- ZIP=`proxy_integration_changed_src.zip`(저장소 상대경로+README). **미커밋**.

## 2026-10-01 소유자 보안하드닝본 적용(저장소 반영)
소유자가 제 원본을 보안 강화해 ZIP 회신 → 분석 후 **저장소에 적용**(LF 정규화)·2점 보완:
- **적용된 하드닝**: fail-closed(ON인데 프록시 없으면 직접연결 우회 금지·예외)·**CDP 인증은 challenge source=="Proxy"일 때만 자격증명 전달**(웹사이트 Server 401에 프록시 비번 누출하던 내 원본 결함 수정=핵심)·SOCKS5 user:pass 거부·socks5h→socks5 정규화·IPv6 브래킷·명시맵 전용 풀 제외·비활성 노드 제외·**rendezvous hashing(HRW)**(modulo보다 재배정↓)·reload_proxy_manager()·예외 로깅.
- **보완2(내가)**: ①config.py 315 중복주석 정리 ②`pipeline_sales._resolve_proxy(account_id, log)`=프록시 설정오류를 **그 계정만 스킵(직접연결 안 함)**·전체 실행 중단 방지(try_login_once·_login_and_discover 두 지점). 핀=test_proxy_patch.test_resolve_proxy_skips_per_account.
- **검증**: run_checks 10종+check_complexity 초록 · test_proxy_patch **5/5** · verify_offline t1_proxy_pool(소유자 확장·main 등록됨) 포함. 신규 tools/test_proxy_patch.py.
- **pytest 호환 수정(Stop 훅 실패 해소)**: `tools/test_proxy_patch.py`가 `test_*` 패턴이라 pytest가 자동수집하는데 PYTHONPATH=src 없이 import 실패했음 → 상단에 `sys.path.insert(0, <repo>/src)` 부트스트랩 추가(verify_offline:18 동일 패턴). 전체 pytest **6 passed**(기존 test_regression_gate 1 + proxy 5)·수집에러 0. ⚠`test_*.py` 네이밍 도구는 pytest가 수집하니 src 경로 부트스트랩 필수.
- ⚠여전히 **미커밋**·라이브 미검증·밴 위험 상존(소유자 판단). 커밋 시 코드+DECISIONS(기록됨)+메모리 동시.

[[login-policy-real-browser-only]]·[[login-block-session-first-circuit-breaker]]·[[fingerprint-consistency]]·[[no-silent-fallback-principle]]
