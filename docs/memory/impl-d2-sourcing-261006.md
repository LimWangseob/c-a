---
name: impl-d2-sourcing-261006
description: 구현 Wave1 — D2 소싱 1단계(sourcing·sourcing_score·verify_sourcing_offline) 오프라인·읽기전용·master 병합됨. 도메인 전용 세션(Agent worktree)이 첫 배정으로 수행
metadata:
  node_type: memory
  type: project
  originSessionId: c48bfd01-5750-43b7-bf3c-9d574e709d12
  modified: 2026-10-06T00:28:31.573Z
---

**구현 Wave1 네 번째 — D2 소싱 1단계(오프라인·읽기전용·모델 A 일회성 조회)**. **도메인 전용 세션 정책([[policy-per-domain-sessions]])의 첫 배정** — 통제 세션이 Agent(worktree 격리)로 D2 배정→레인 구현·게이트 초록·커밋→통제 리뷰 후 직렬 병합(master). SSOT=`designs/DOMAIN_D2_SOURCING.md`.

## 무엇을 (greenfield 3 + run_checks 1줄·기존 모듈 미수정·config 미접촉)
- `src/coupang_analytics/sourcing_score.py` — 순수 함수(의존 0): `sourcing_score(volume, rocket_ratio, ad_count, est_margin)`=수요(volume/1000) − 경쟁(rocket_ratio×40+ad_count×2) + 마진(est_margin×30). est_margin None=기여 0.
- `src/coupang_analytics/sourcing.py` — `SourcingCandidate`(keyword·volume·clicks·comp_idx·organic_count·ad_count·rocket_ratio·est_margin·score·note) + `discover_candidates(seed, naver, browser, ai_key=None, *, top_n, log)` + `analyze_keyword(keyword, naver, browser)`. 값 객체만. **L1만 호출**: kw_suggest(자동완성 후보)+kw_volume(검색량)+kw_metrics.page1_competition(1P 경쟁). 폴백 금지(결과없음·검색량 미확인=note 명시).
- `tools/verify_sourcing_offline.py` — 실 API 0(L1 조회지점 모킹). 6시나리오: 중복제거·검색량 매칭·점수 내림차순·경계(빈 시드·결과없음·마진 None)·top_n·단일·공식 단조성.
- `tools/run_checks.py` CHECKS 1줄 append(10→15종째).

## 계층·설계 편차(중요)
- **계층 준수**: sourcing.py는 L0/L1(kw_metrics·kw_suggest·kw_volume·sourcing_score)만 import — **kw_ai·kw_recommend(L2 D1) 미import**(ARCHITECTURE §2). 통제가 diff로 확인.
- **AI 범위 제외**: 설계 §6 초안의 `ai_key`/AI 후보생성은 kw_ai=L2라 계층상 D2가 직접 못 부름 → 1단계 후보발굴=쿠팡 자동완성+시드 변형만. `ai_key`는 자리만(미사용)·향후 L3 조립이 AI 후보 주입. [[naver-shopping-api-terminated]] 영향으로 경쟁강도=kw_metrics.page1_competition(쿠팡 총상품수 미노출이라 포기).
- **M1(=U2) 확인**: kw 조회 프리미티브 L1 재분류는 U2로 완료(IMPL_PLAN §3·L1_CONTRACT §7-d)라 D2 착수 합법. DOMAIN_D2 §2.1·§8 "M1 미결"은 stale.

## 검증
게이트 **15종 전부 초록**·복잡도/건강 초록(신규 A/B). master 병합(HEAD 41c34e4).

## 남은 것(통제/사무실)
- **L1_CONTRACT 핀**(통제): §6 시그니처(discover_candidates·analyze_keyword·SourcingCandidate) pin_l1_contract 등재 — 미등재(D8/D10 핀과 함께 통제 몫).
- 라이브 1P 셀렉터 검증(사무실·verify_rank_live) · UI 02-x 탭(H_ui) · 모델 B 후보 원장(sourcing_store·2단계·가치검증 후).

[[policy-per-domain-sessions]] · [[impl-d8-absorb-ledger-261005]] · [[impl-d10-cs-tracker-261005]] · [[keyword-methodology-ai-anchor]]
