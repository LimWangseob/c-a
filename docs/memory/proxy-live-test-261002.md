---
name: proxy-live-test-261002
description: "노출순위 프록시 라이브 실측(2026-10-02) — DataImpulse 한국 주거용=통과, Decodo 고정ISP=번아웃, 코드 무결"
metadata:
  node_type: memory
  type: project
  originSessionId: b9af6ec6-eafc-49f0-94ea-0dd7e7402bbb
  modified: 2026-10-02T04:48:18.579Z
---

**노출순위(③) 프록시 라이브 실측 (2026-10-02)**

사무실 IP는 쿠팡 Akamai에 ③순위가 차단되므로, 순위 검색만 프록시 뒤로 보냄(로그인·수집은 사무실 IP 유지=2차인증 통과·위탁계정 안전). 이날 두 업체를 실제 "타프" 등 검색으로 테스트한 결론.

## 결과 (실측)
- **Decodo 전용 ISP(고정 IP) = 번아웃 → 못 씀.** 서울 KR IP(84.37.2.35 등)가 처음엔 통과(5/5)했지만 **~7검색 뒤 영구 차단**(1시간 뒤에도 Access Denied). 고정 IP는 자동검색 행동이 누적되면 그 IP가 플래그됨. 3개 중 2개는 첫 시도부터 차단.
- **DataImpulse 한국 주거용(회전 sticky) = 통과 → 채택.** 게이트웨이 `74.81.81.81:10000`, 아이디 `..._cr.kr`(한국 라우팅). 실제 한국 ISP IP(LG DACOM·교육망)로 egress. **하드차단 0건·최근 3회 연속 발견율 100%**(타프 등 12/12). **스티키 IP가 몇 분마다 회전**해서 한 IP가 번아웃되기 전에 바뀜 = 고정 IP의 약점을 구조적으로 회피.

## 핵심 통찰
- **차단 원인 = 순수 IP 평판**(코드 아님). 소유자가 "코드 문제인지 정밀분석" 요청 → browser.py의 CDP `Fetch` 전역 가로채기(인증용)를 의심했으나, **같은 코드로 DataImpulse는 100% 통과** → 코드 무결 확정. Fetch 에러 로그는 차단 후 브라우저 종료 시의 정리 노이즈(원인 아님). ⛔ browser.py 프록시 인증 코드 수정 불필요.
- **"새벽 차단 vs 지금 정상"의 원인도 IP**: 로그상 새벽 자동실행은 측정 0건(차단 아님·돌릴 것 없었음). 사용자가 본 Access Denied는 그때 proxies.txt의 플래그된 프록시(모바일/Decodo)로 수동검색한 결과. 시간대 무관.
- 소프트 차단(그림자 차단) 의심 → `rank.extract_items`로 상품수 세어보니 50개 꽉 참(정상). 한 번 패치(2/5 None)는 초기 일시현상이었고 이후 안정.

## 운용 세팅 (현재 상태)
- `proxies.txt`(gitignore·평문 자격증명) = DataImpulse 한국 주거용 URL 1줄. `config.json proxy/enabled=true`·`proxy/allow_auth=true`.
- 운용 경로 검증됨: `config.apply_proxy_override`→`proxy_pool.rank_proxy_or_skip`→egress 한국 IP→통과.
- 아키텍처 확정: **사무실 PC 1대로 ①②(무프록시·사무실 IP)+③(프록시·한국 주거용)**. 집 IP/홈 프록시 불필요(DataImpulse가 해결).

## 남은 일
- **첫 밤샘 271개 규모 1회 검증**(지금까지 ~35검색만 테스트, 회전 덕에 번아웃 없을 것으로 기대). 중간 차단도 서킷브레이커+공란+다음날 재측정이 보완.
- **GB 데이터 요금 확인**(DataImpulse 대시보드 USED TRAFFIC). 순위=이미지 포함 풀페이지라 트래픽 큼. ⛔이미지 끄기=봇 신호라 금지.
- 드물게 나쁜 회전 IP에 걸리면 그 순간 검색 몇 개가 공란 가능(허용 범위).

[[proxy-integration-off-261001]] · [[login-2fa-location-based]] · [[rank-antiblock-circuit-breaker]] · [[fix-from-real-evidence]]
