---
name: fingerprint-consistency
description: 지문 1·2단계(2026-09-14 소유자 승인) — UA/CH 정합(하드코딩 Chrome/150 지뢰 제거) + 자동화 흔적 점검(이미 깨끗). 고위험 3단계(TLS/_abck)는 미착수
metadata:
  node_type: memory
  type: project
  originSessionId: 3a577ce1-852a-4bb4-b64f-e6d46ce615f6
  modified: 2026-09-14T08:07:55.700Z
---

지문 대응 **1·2단계**(낮은위험, 2026-09-14 소유자 승인 — 정책은 [[rank-antiblock-circuit-breaker]]). 원칙=**정합(진짜 브라우저에 맞추기)**, 가짜 위조 아님.

**실측 지문(2026-09-14, 로컬 프로브·쿠팡 무접촉):** 실제 Chrome **153**. `navigator.userAgent`=Chrome/153·`webdriver`=**false**·`window.chrome`=있음·`plugins`=5·`languages`=[ko-KR,ko,en-US,en]·`platform`=Win32·`hardwareConcurrency`=22. **전부 진짜·정합**(browser.py가 실제 Chrome을 CDP로 붙여 자동화 흔적 없음).

**★ 발견(중요)**: `rank._set_mobile`이 **하드코딩 `_PC_UA`=Chrome/150**(실제 153과 불일치)을 `Emulation.setUserAgentOverride`로 덮었으나, **새 CDP 세션에서 override 후 즉시 `cdp.detach()` → override가 해제**돼 실제론 네이티브(153) UA가 쓰임(=우연히 정합). 즉 하드코딩 UA는 **죽은 코드지만, 적용되면 UA↔클라이언트힌트 불일치를 유발할 지뢰**. (부수: 이 detach 때문에 모바일 에뮬레이션도 실제론 미적용 — 단 `config.RANK_INCLUDE_MOBILE=False`라 무영향.)

**① UA/CH 정합 — 구현(커밋 이 세션)**: `rank._set_mobile` 수정 + `_chrome_major(page)`(실제 UA에서 메이저 추출) 추가.
- **PC(Off)=UA 오버라이드 제거** → 네이티브(실제) UA·userAgentData 그대로 = 완전 정합(하드코딩 150 지뢰 삭제).
- **모바일(On)=실제 크롬 버전으로 UA 생성 + `userAgentMetadata`(sec-ch-ua) 동반 설정** → UA↔CH 정합(켜질 때 대비). `_PC_UA`/`_MOBILE_UA` 상수 삭제.

**② 자동화 흔적 정리 — 정직한 결론: 정리할 것 없음.** 이미 webdriver=false·chrome 있음·plugins/languages/platform 실제값. **불필요한 위조 init 스크립트는 안 넣음**(오히려 어설픈 패치가 tell 될 수 있음). 실제 Chrome+CDP 방식이 이미 최선.

**③ 숙제(보류·향후 과제, 2026-09-14 소유자 결정)**: TLS/JA3 조작·Akamai `_abck` 재생. **당장 안 함** — 1·2단계를 핫스팟 A/B로 돌려보고 **그래도 차단이 남을 때만** 검토. 밴 위험 최대라 착수 전 반드시 소유자와 재협의. (섣불리 제안·구현 금지, 남겨둔 숙제.)

⚠ **실효성 미검증**: 1·2는 "불일치 지뢰 제거"라 안전하지만, 차단이 실제 줄어드는지는 **깨끗한 IP(핫스팟) A/B**로 확인 필요([[fix-from-real-evidence]]). 관련 [[coupang-blocks-paste-requires-typing]] [[shopmine-architecture]].
