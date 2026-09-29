---
name: settlement-domain-knowledge
description: 쿠팡 정산·매출·판매 도메인 명세 + 골든 케이스 저장 위치(D8 정산 계산 구현 입력용 지식·미구현). 정산 모듈 착수 시 근거 문서.
metadata:
  node_type: memory
  type: reference
  originSessionId: bf49ca7e-f45c-4a4c-8790-7c4955b64170
  modified: 2026-09-29T09:21:14.065Z
---

쿠팡 **정산 계산 도메인**(지급일·금액·판매분석)의 구현 입력용 지식 명세와 검증 벡터가 리포에 저장됨. **코드 아님·미구현** — D8(정산/원장) 계산 모듈 착수 시 이 문서를 근거로 설계서 작성.

**저장 위치**:
- `designs/COUPANG_SETTLEMENT_DOMAIN.md` — 도메인 명세 SSOT (D8 형제, [[feature-ledger-registry]]·`designs/LEDGER_REGISTRY.md` 옆)
- `designs/coupang_golden_cases.json` — 검증 골든 케이스. **100% 통과 = 구현 완료 조건**

**명세 핵심**:
- 지급일 규칙 6종(POLICY): 윙 70%(주마감+15영업일)·30%(익익월 1일·영업일 보정 없음)·월정산 / 로켓그로스 70%(+20영업일)·30%(익익월 첫 영업일)·월정산.
- 영업일=토·일·한국 공휴일·대체공휴일 제외. 공휴일=하드코딩 금지·천문연 특일정보 API 캐시·조회 실패 시 ERROR raise(0일 가정 금지). 대체공휴일: 설·추석은 일요일 겹침만 대체(토요일 겹침 대체 없음).
- 금액 식 3종: 윙 정산대상액 E = A−쿠폰B−수수료C−마이샵D / 로켓그로스 실지급 = 정산대상액−밀크런−광고비−CFS / RG 홈 이익.
- 파싱 규칙(`PARSE_COUPANG_XLSX`)·판매분석 불변식(매출=총매출+총취소)·함정 5종(70/30 이중집계 등)·§8 운영위탁 계약 모듈 입력 요구.

**착수 시**: 명세 근거로 정산 계산 모듈 설계 → 골든 케이스를 검증 스크립트(예 `tools/verify_settlement_offline.py`)로 로드해 `tools/run_checks.py` 게이트에 연결. 근거=`docs/DOMAIN_DESIGN.md §D8`·`docs/DECISIONS.md`(2026-09-29 정산 도메인 지식 아카이브 줄).

관련=[[feature-ledger-registry]]·[[handoff-domain-design-260928]]·[[handoff-session-260929-continued]].
