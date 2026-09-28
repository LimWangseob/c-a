---
name: handoff-ledger-stage2-260928
description: "셀독등록원장 2단계(앱 연계) 인계 — \"쿠팡 정산 기능 개발\" 세션(삭제됨) 승계. D8_ledger 주도·H_ui/통합 협력. 착수 전 SSOT=designs/LEDGER_REGISTRY.md §10."
metadata:
  node_type: memory
  type: project
  originSessionId: 36f26e1a-466b-4e04-9814-a4e46aceddf1
  modified: 2026-09-28T13:50:40.027Z
---

**"쿠팡 정산 기능 개발" 세션(2026-09-28·삭제됨)이 진행하던 셀독등록원장 2단계(앱 연계) 계획을 인계한다.**
그 세션은 **2단계 코드 미착수**(계획만 세우고 idle)였다. **1단계 결과물은 이미 master 커밋**(registry_*.py 7모듈·registry_sync·registry_backfill)이라 삭제해도 코드 손실 없음. 2단계 계획도 `designs/LEDGER_REGISTRY.md §10·§4-1·§203`에 문서화됨.

## 2단계 = D8_ledger 주도 + 협력(공유 파일 조율)
정산 2단계는 한 도메인이 아니라 여러 도메인에 걸친다. **주도=D8_ledger**, 협력=H_ui(UI)·통합 세션(pipeline 조립).

| 작업 | 로직 위치 | 담당 |
|---|---|---|
| 2-1 원장 자동 반영(실행 시작 시 동기화 1회·실패해도 진행+로그) | registry_gsheet + 실행 시작 배선 + 설정탭 원장카드·[미리보기]·[반영] | 주 D8 / 배선 통합(pipeline) / UI H_ui |
| 2-2 쿠팡확인 채우기(로그인·매칭 결과를 원장 쿠팡확인·확인일 열에: 확인됨/미등록/판매중(불일치)/판매중지/로그인실패/비밀번호불일치) | 수집 결과→원장 쓰기 | 주 D8(registry_gsheet) / 수집 배선 통합(pipeline_sales·pipeline_process) |
| 2-3 이전 비밀번호 1회 시도(비번불일치 목록+버튼·사람이 누를 때만 계정이력 직전 비번으로 1회) | 로그인 재사용+원장 이력+버튼 | UI H_ui / 로그인 통합(pipeline_sales) / 이력 D8 |
| 2-4 입력 소스를 원장으로(설정 입력소스에 '원장' 추가·관리중만·대장/PC엑셀 되돌림 스위치 유지) | input_list/새 모듈 + 설정 스위치 | 주 D8 / UI H_ui |

권장 순서(그 세션 결론): 2-1→2-2→2-3 먼저, **2-4는 원장이 며칠 정상으로 쌓인 뒤**(§10 단계적 전환).

## 규약·주의
- **쓰기 도메인 안전규약**(DOMAIN_DESIGN §5.4): dry-run 미리보기→사람 승인→실행→원장 기록. 위탁계정·Akamai 사고방지·무인 쓰기 금지.
- 2-2·2-3은 **로그인 필요=사무실에서만 라이브 확인**. 개발 세션은 오프라인 테스트로 검증하고 사무실 확인 남김으로 보고.
- 공유 파일(pipeline_*·app_qt·config·designs·DECISIONS)은 통합/H_ui 소유 → D8은 직접 편집 말고 조율(PARALLEL_DEV 공유 직렬화). 원장 쓰기 잠금 필요(동시 registry_sync 이력번호 겹침 방지).
- 쿠팡확인은 매일 바뀌어 **이력에 기록 안 함**(그로스 재고와 동일·§4-1).

## 착수 방법
D8_ledger 세션(D:\ca-worktree\D8_ledger)에서 `designs/LEDGER_REGISTRY.md §10`부터 읽고 2-1 착수. 핀 먼저(registry 게이트 verify_registry_offline). 관련=[[feature-ledger-registry]]·[[handoff-domain-design-260928]]·[[no-silent-fallback-principle]]·[[login-policy-real-browser-only]].
