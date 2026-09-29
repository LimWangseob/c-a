---
name: settlement-domain-knowledge
description: 쿠팡 정산·매출·판매 도메인 명세 + 골든 케이스 저장 위치(D8 정산 계산 구현 입력용 지식·미구현). 정산 모듈 착수 시 근거 문서.
metadata:
  node_type: memory
  type: reference
  originSessionId: bf49ca7e-f45c-4a4c-8790-7c4955b64170
  modified: 2026-09-29T09:40:08.976Z
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

**모듈 설계서**: `designs/SETTLEMENT_MODULE.md`(2026-09-29 작성·미구현). 신규 5모듈(holiday_kr·payout·settlement_amount·settlement_parse·settlement·greenfield·E 원장/정산 레인 소유). 3단계: ①오프라인 골든100%→`tools/verify_settlement_offline.py` 게이트(9→10종) ②라이브 수집(collector 확장·API 미확인·직렬) ③계약 대비 정산(계약서 수령 후·원장 소비·H_ui). 공유파일(config·L1_CONTRACT·run_checks) 수정은 통합 세션에만 요청.

**실측 검증 완료(2026-09-29·실계정 화면3+판매현황 xlsx1)**: 판매현황 파일=시트 `vendor item metrics` 19열 A~S·전 셀 str(명세 §4.1 일치)·불변식 16/16 무위반(매출=총매출+총취소·전환율=주문/조회). 정산현황/매출내역/RG홈 화면이 golden_cases payout·MP_REVENUE_REPORT·RG_HOME_PROFIT과 정확 일치 → 지급일 알고리즘·금액식 라이브 근거 확보. 1단계 착수 준비 완료. 상세=`designs/SETTLEMENT_MODULE.md §5.1`.

**착수 시**: 위 설계서 근거로 구현 → 골든을 `tools/verify_settlement_offline.py`로 로드(테스트는 `_meta.holidays_used` 주입·실 API 금지)해 `run_checks.py` 게이트 연결. 근거=`docs/DOMAIN_DESIGN.md §D8`·`docs/DECISIONS.md`(2026-09-29 줄).

관련=[[feature-ledger-registry]]·[[handoff-domain-design-260928]]·[[handoff-session-260929-continued]].
