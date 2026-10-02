---
name: proxy-rotation-design-261002
description: 노출순위 egress 재회전 + 차단 IP 목록(이력 skip) 구현(2026-10-02) — 브랜치 proxy-egress-rotation·게이트 초록·미커밋·라이브 미검증
metadata:
  node_type: memory
  type: project
  originSessionId: 202b4f12-0f1f-42a1-a7eb-39526738003d
  modified: 2026-10-02T07:12:48.793Z
---

**노출순위(③) egress 재회전 + 차단 egress 목록 — 구현 (2026-10-02)**

소유자 요구: ③순위 차단 시 ①새 egress 로 재회전 ②차단당한 **실제 egress IP** 를 보관했다가 업체가 그 IP 를
다시 주면 skip 하고 다른 IP 로 처리 ③진행 로그. 회전 소스 = **Model A(sticky 세션 여러 개)**.

## 핵심 설계
- **egress 판정은 게이트웨이 URL 이 아니라 "브라우저가 실제로 나가는 공인 IP"** 로 한다(IP 에코, coupang 아님).
  proxies.txt 각 줄은 DataImpulse `;sessid.sNN` 로 구분되는 독립 sticky IP(공식 문법 확인).
- **프록시는 launch 시 `--proxy-server` 로 고정** → egress 교체 = **브라우저 재기동**(핫스왑 불가).
- 에스컬레이션: 차단 → (쿨다운보다 싼) **새 egress 로 즉시 회전**(RANK_PROXY_ROTATE_MAX=3) → 소진 시 기존
  쿨다운→당일중단(그대로). 기존 서킷브레이커·fail-closed 보존.

## 구현 (브랜치 `proxy-egress-rotation`, 미커밋)
- `config.py`: `RANK_PROXY_ROTATE_ON_BLOCK=True`·`ROTATE_MAX=3`·`LAUNCH_MAX_ATTEMPTS=5`·`PRECHECK_EGRESS=True`·
  `BLOCKLIST_FILE=rank_blocked_ips.json`·`BLOCKLIST_TTL_SEC=259200`(72h)·`EGRESS_ECHO_URLS`.
- 신규 `proxy_blocklist.py`: load/save(원자적)·TTL 만료·record/is_blocked/entry/count·`resolve_egress_ip(browser)`.
- `proxy_pool.py`: `pick_rank_proxy(tried)`(off/ok/exhausted/error)·`rank_proxy_pool_urls` 추가. 기존 함수·핀 불변.
- `pipeline_ranks.py`: `drive_rank(offscreen,run_once,log,should_stop)` 드라이버(+`_run_on_egress`·`_rank_single_open`)
  + `rotation_can_rotate()`. 두 stage 경로(auto `track_ranks`·semi `_track_ranks_semi`)를 `run_once` 클로저로 감쌈.
  `_rank_cooldown`·`_semi_on_miss`에 "회전 가능하면 쿨다운 생략, 새 IP 전환" 분기 삽입.
- 핀: `tools/test_proxy_patch.py` 9종(회전·차단목록TTL·drive_rank 선제skip/재회전). `.gitignore`+=rank_blocked_ips.json.
- **검증**: run_checks 10종 + check_complexity(경고0·drive_rank CC≤15) + test_proxy_patch 9/9 초록. 플래그/프록시 OFF면
  기존 단일 open 과 100% 동일(핀 로그인·발견·반자동순위 통과로 확증=회귀0).

## 이미지 OFF 실험(트래픽/비용 절감 — 2026-10-02 추가)
- `WingBrowser(block_images=)` → Chrome `--blink-settings=imagesEnabled=false`. rank 3경로(auto·semi stage·site3)에 배선.
- 토글: `config.RANK_BLOCK_IMAGES`(기본 False) · config.json `rank/block_images`(apply_rank_images_override). 핀=test_rank_block_images.
- **목적**: 순위 SERP 는 이미지가 트래픽 대부분 → 끄면 DataImpulse GB 요금↓. 단 메모리 [[proxy-live-test-261002]] 의
  "이미지 끄기=봇 신호라 금지"는 **추정**이라, 기본 OFF 로 두고 **A/B 실측**으로 차단 관련성 검증 후 결정(플립플롭 방지).
- **A/B 절차**: 같은 조건에서 ①images-on 1회 ②`rank/block_images=on` 으로 1회 → 각 종료 요약의 `차단감지/쿨다운`
  수 + DataImpulse 대시보드 USED TRAFFIC 비교. 차단 0 유지 + 트래픽 큰 폭 감소면 채택(DECISIONS 갱신).
- **라이브 실측 결과(2026-10-02) = 판정 불가**: 단발 A/B 3회(s04 ON 통과·s05 OFF 차단·s06 ON·OFF 둘다 차단).
  **egress IP 평판이 수분 단위로 clean↔blocked 변동**(깨끗했던 s06이 이미지 ON인데도 차단) → 이미지 변수가 IP
  노이즈에 묻혀 분리 불가. **확실한 것**: 이미지 = SERP 트래픽 **≈60%**(s04 실측 749/1251KB·검색별 26~79%)
  = 절감 잠재력 큼. "99% 절감"은 OFF가 에러페이지(3KB)라 생긴 허수. **결론**: block_images 기본 OFF(이미지 켬)
  **유지**('이미지끄기=봇신호' 추정 반증 못함·잘못 켜면 순위 전멸 리스크). 올바른 재검증 = **밤샘 규모 N일 ON vs
  N일 OFF 차단율 비교**(대수의 법칙으로 IP 노이즈 상쇄). 도구=tools/test_rank_images_live.py·probe_proxy_pool.py.
- **부수 발견**: 풀 9개 중 3개만 순간 clean(혼합·변동) → 회전+차단목록 설계의 필요성 재확인. ⚠teardown 시
  browser.py _on_paused(Fetch) 가 닫힌 세션에 continueRequest → TargetClosedError 로그 노이즈(비치명·후속 가드).

## ⚠ 남은 일
1. **proxies.txt 를 sessid 여러 줄로**: `http://<id>__cr.kr;sessid.s01:<pw>@74.81.81.81:10000` …s02,s03(5~10줄). 안 그러면
   풀 1개라 회전이 "egress 소진"으로 바로 끝남(로그로 드러남). SSOT 문법=[[proxy-ip-policy-by-context]] 세션.
2. **site 3 egress 회전 미배선**: `pipeline.py:435`(전체실행 ranks-on·비semi·비skip)은 이미지 플래그만 적용·회전은 아직
   `rank_proxy_or_skip`. _process_account 가 차단신호를 안 돌려줘 회전 불가 → 후속(드문 경로). auto/semi stage 는 회전 배선됨.
3. **라이브 미검증**: 밤샘 규모검증으로 회전 실효(한 sticky 번아웃 vs 풀 품질) + 이미지OFF 차단관련성 확인.
4. 커밋=코드+DECISIONS+메모리 동시([[commit-with-design-and-memory]]). pytest 는 이 개발환경 미설치(운용 PC 훅이 수행).

[[proxy-ip-policy-by-context]] · [[proxy-live-test-261002]] · [[fix-from-real-evidence]] · [[code-health-regression-gate]]
