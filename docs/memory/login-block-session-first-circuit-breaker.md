---
name: login-block-session-first-circuit-breaker
description: Akamai 로그인 차단은 로그인 POST에서만 발생 → 세션우선 2패스 + 서킷브레이커로 대응(반복 자동로그인이 IP 태움)
metadata: 
  node_type: memory
  type: project
  originSessionId: 769928de-55b1-4f20-8d55-96b5e259654c
  modified: 2026-09-15T07:26:42.807Z
---

2026-09-09 라이브(28계정)에서 관측·구현. **관측상 Akamai 차단은 로그인 폼 제출(`xauth/login-actions/authenticate` POST) 단계에서 표면화** — 데이터 API(vi-detail-search·재고)와 세션 재사용(authenticated GET)에선 동일 현상 미관측. ⚠️ 단정 주의(2026-09-09 사용자 지적): "POST에서만/POST 자체가 원인"이라 단정 금지 — 원인이 누적 빈도·IP평판·인증실패횟수일 수도(관측=표면화 지점까지만). 실무 함의는 동일 = **인증 요청 총량을 줄인다**. 세션 만료 계정을 자동로그인하다 **~14회째부터 Access Denied**, 이후에도 자동제출해 IP를 더 태웠음. 지문위조 금지라 "위장 통과"는 불가.

**구현(pipeline.run_full)**:
- **세션우선 2패스**: 1차 = 세션 살아있는 계정 먼저 전부 수집(로그인 없음 → 차단 위험 0), 세션 만료는 `NeedLogin`으로 대기열. 2차 = 로그인 필요분만 처리.
- **로그인 서킷브레이커**(`config.LOGIN_BLOCK_CIRCUIT=3`): 2차에서 연속 Akamai 차단(`classify_login()=='blocked'` → `LoginBlocked`) 3회면 이후 로그인 생략(IP 그만 태움). 못 딴 계정은 로그 안내 → 쉰 IP 재실행 시 수집.
- `_login_and_discover(login=False/True)`, `_finish` 헬퍼(1·2차 공통), `NeedLogin`/`LoginBlocked` 예외. simulate_pipeline 시나리오7·8.

**⭐무인 로그인 + 날짜인식 재개(2026-09-11 사용자 요청·구현)**: 라이브(28계정)에서 **~15계정 자동로그인 성공 후 (DW)커머스에서 Akamai 차단** 관측 → 완전 무인 로그인은 불가 확정(정책상 우회 금지, 사람 클릭/2차인증만 통과). 대응 구현: (1) **무인 모드**(`config.LOGIN_UNATTENDED=True`, `LOGIN_UNATTENDED_WAIT_SEC=45`, `LOGIN_BLOCK_GRACE_SEC=8`): 자동입력·자동제출로 되는 계정만 수집하고, 사람 필요분(차단·2차인증·비번없음·폼지속)은 **창 안 띄우고 즉시 건너뜀**(과거엔 차단 시 창 띄우고 대기 → 자리 비우면 방치·(DW)커머스에서 정지했음). `_login_and_discover`에 unattended 분기, `wait_for_login(timeout/blocked_grace)` 축소. (2) **재작업=미완료분만**: 같은 날 진행분은 done 계정 건너뛰고 이어서(app_qt `do_run_full` 팝업 없이 자동 결정). (3) **날짜 변경 시 처음부터**: `resumable_progress`가 `started_at`의 달력날짜==오늘일 때만 재개 인정(어제 잔재 무시 → 새 오늘 컬럼). 건너뛴 계정 vid는 나중에 [[semi-auto-rank-and-exposed-name]] 반자동/수동 로그인으로 확보. ⚠️로그인은 순위(③)와 달리 무인 자동화에 한계(차단=사람 필요).

**차단 시 가시창 앱-자동 1회 재시도(2026-09-12 `5adb1c0`, 사용자 선택=옵션C)**: ① 무인 오프스크린 자동입력이 **소프트 차단/폼정체**로 실패하면, 창을 화면에 띄우고 앱이 자동입력·클릭으로 **딱 1회** 더 시도(무인 유지). `config.LOGIN_SEMI_ON_BLOCK=True`·`LOGIN_SEMI_WAIT_SEC=90`. **계정당·실행당 정확히 1회**(루프 없음, 최초1+재시도1=제출 최대 2회). 재시도도 실패하면 기존대로 `LoginBlocked`→서킷브레이커. 지문위조 없어 Akamai IP 접근차단은 대부분 못 뚫음(소프트=폼 되돌아옴에만 기대).

**⭐비밀번호 1회 오류 = 재시도 완전 금지(2026-09-15 사용자 지시, 계정잠금 방지)**: `classify_login()='error'`(#input-error=비번오류·계정잠금·휴면·OTP5회잠금 = **확정 자격 실패**)이면 위 반자동 1회 재시도를 **건너뛴다**(비번 재제출 안 함 → 제출 딱 1회로 끝). 또 `_login_and_discover`가 `LoginCredentialError`를 던져 run_full이 그 계정을 **`done` 처리** → 야간 재개(`LOGIN_NIGHT_RESUME`)·같은 날 자동 재개가 **다시 제출하지 않음**(누적 5회=계정잠금 원천차단). **소프트 차단(폼정체·Akamai blocked)만** 위 반자동 1회 재시도 유지. 비번 수정(관리대장) 후 새 실행(다음 날/진행분 초기화)에서 재시도. `cred_fail=(not ok) and classify_login()[0]=='error'`로 게이팅. 단위검증=비번오류 제출1회·소프트차단 제출2회·성공1회. ⚠️③반자동(비로그인·잠금위험0)과 달리 로그인은 잠금 위험 실재라 이 게이팅이 핵심.

**Why**: 반복 자동로그인 = 봇 패턴 = IP 플래그. 세션우선이면 쉬운 데이터는 무조건 확보, 서킷브레이커면 차단 시 피해 최소화.
**How to apply**: 근본 목표는 "로그인 0회"가 아니라 **불필요한 재인증 제거 + 정상 재인증 최소화**(Max 세션은 keep-warm으로 못 넘음). 방향 = **측정 먼저** → 세션 재사용 강화 → 검증되면 keep-warm(상세 [[login-block-session-first-circuit-breaker]]). 서킷브레이커는 피해 차단(damage control)이지 무제한 수집 아님. 관련=[[login-policy-real-browser-only]] · [[coupang-session-short-lived]] · [[coupang-openapi-not-available-consignment]] · [[wing-keyword-data-subscription-gated]].
