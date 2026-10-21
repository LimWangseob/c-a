---
name: feedback-control-session-only
description: "배포 zip 생성·결과 구글시트 반영 = 통제 세션(Coupang Analytics)만 — 다른 세션은 코드 커밋·푸시까지만·제안도 하지 말 것(소유자 2026-10-21 '일원화')"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 6be20ba8-d756-4d15-a875-d3f0c3ae7a08
  modified: 2026-10-21T14:38:13.500Z
---

**배포 버전(zip) 생성과 결과 구글시트 반영은 통제 세션에서만 한다.** 기능 세션(worktree)·사이드 세션은 코드 수정 → 게이트 → master 푸시 → 통제 세션에 알림까지만. "zip 만들까요?"·"구글에 반영할까요?" 같은 제안도 하지 않는다.

**Why:** 소유자 2026-10-21 "배포는 너의 세션에서 하는데 아님. 배포 버전 생성은 통제 세션에서만 가능해. 일원화 해야지." 같은 날 실측 사고 — 사이드 세션이 운용 PC 사본 마스터로 통합판매현황을 다시 그려 구글에 올리면서 D-093 정리(`prune_account_ids`) 전 오입력 계정ID(비밀번호 같은 값)가 3칸 노출(직후 통제 세션 반영으로 덮였지만 버전 기록에 남음)·두 세션이 같은 분에 반영.

**How to apply:**
- 끝맺음 보고 = 커밋 해시·D-번호·시험 결과 + "통제 세션에 알림". 배포·반영은 "통제 세션 담당"으로만 언급.
- 통제 세션 = 세션 목록의 'Coupang Analytics'(이 저장소 상위 세션). 그 세션이 계정ID 정리 후 반영·빌드.
- 부득이 사본으로 그려야 할 때(통제 세션 지시가 있을 때만)는 `prune_account_ids` 적용 + 올리기 전 대장에 없는 계정ID 라벨 개수 검사(값 출력 금지).
- 관련: [[exe-packaging-deploy]] · [[feature-sales-summary-first-sheet]]
