---
name: handoff-architecture-parallel-260928
description: "인계(2026-09-28): 커머스 전과정 앱 목표·계층 아키텍처(공통/도메인)·세션분리/통제 설계 완료→새 세션서 병렬개발 시작"
metadata:
  node_type: memory
  type: project
  originSessionId: 3588291b-3435-4968-8471-8410129d1b69
  modified: 2026-09-28T09:11:38.706Z
---

**새 세션 착수용 인계.** 소유자 궁극목표=**상품 분석→소싱→등록→주문→정산→통계 전과정 관리·운영 앱**(현재 초기·분석/통계/정산원장 일부). 요구=기능을 **공통 모듈/개별(도메인) 모듈**로 체계 분할해 **재사용+융합** 가능케. 병렬 개발은 **새 세션에서 시작**(이 세션은 설계·준비까지).

## 이번 세션이 준비한 것 (전부 커밋·푸시)
- **`docs/ARCHITECTURE.md`(신규)**: 계층 설계 SSOT — 실측 import in-degree(config←22·input_list←7·workbook←6·browser←6·registry←5~6·detail_images=고립leaf) 위에 **L0 플랫폼 / L1 데이터백본 / L2 도메인 / L3 조립·UI** 4계층 + **의존 방향 규칙(도메인은 아래로만·도메인끼리 직접 import 금지·융합은 백본 경유)** + 세션분리(통합세션=L0/L1·config·병합 단독 / 도메인세션=L2 레인 병렬) + **점진 이행 로드맵(전체 재작성 금지)**.
- **`docs/PARALLEL_DEV.md`(기존)**: 운영 how-to — worktree+브랜치·레인 A~H(편집소유파일)·공유 직렬화·충돌핫스팟(게이트/핀)·병합 직렬·2~3레인 권장. ⚠**런타임 병렬화 금지**(단일 브라우저/위탁계정/Akamai/단일 마스터·시트 → 실행은 야간 단일 순차·라이브 테스트 한 번에 한 세션).
- **CLAUDE.md** '병렬 개발' 섹션·**DECISIONS** 기록.

## 배경 결론 (왜 이 방식)
- CA0~CA6(wc-pipeline식 7세션·artifacts 결합) 제안은 분석 결과 **병렬 실행이 CA에 구조적 불가**(단일 브라우저/계정/시트)라 **과설계**. 실익은 **병렬 개발**뿐 → 가벼운 레인/worktree + 계층 아키텍처만 채택. artifacts/lib 는 CA에 없음(wc-pipeline 개념).

## 새 세션 착수점(권장 순서)
1. `docs/ARCHITECTURE.md`·`docs/PARALLEL_DEV.md`·`MEMORY.md` 먼저 읽기.
2. **통합(플랫폼) 세션 1개 지정** → L1 "공개 API 계약" 목록화(collector fetch_*·workbook 기록 API·registry read/write 등 도메인이 부르는 진입함수를 고정·핀 보호).
3. **도메인 2~3레인 병렬**(독립도순 D 이미지·E 정산/원장·B 키워드·C 순위) 또는 **신규 도메인 스캐폴딩**(소싱/등록/주문은 처음부터 L2 규칙대로 신설).
4. 각 레인 worktree/브랜치·`run_checks` 초록 후 push → **master 병합은 통합 세션이 직렬**.

## 미결(운영·이전 세션서 이월)
- 운용 PC **재배포**(zip 09-28 17:36·이번 세션 전 수정 포함) → 다음 실행에 반영. 커스텀존/반달컴퍼니 대장 비번수정·wellbing 판매정지 WING 확인·재병합 400 정확사유(다음 로그).

관련: [[handoff-session-260927]]·[[api-productid-source-vendor-items-with-vendoritems]]·[[code-health-regression-gate]]·[[verify-by-data-not-status]].
