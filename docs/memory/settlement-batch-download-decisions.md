---
name: settlement-batch-download-decisions
description: 정산(D8) 다운로드·집계·검증 현재 상태 SSOT — 다음 세션 시작점·확정 사실(API·규칙·운용)·미해결·다음 작업 (2026-10-08 정리)
metadata:
  node_type: memory
  type: project
  originSessionId: c665ec52-2651-4681-8b09-70e3558090cb
  modified: 2026-10-08T05:18:03.190Z
---

## 다음 세션 시작점 (2026-10-08 D8_ledger 세션 종료 시점)
- worktree `D:\ca-worktree\D8_ledger` · 브랜치 `domain/d8-ledger` HEAD=**9eb8df3**(작업트리 깨끗). master=cc3cbe2 까지 병합됨.
  **9eb8df3(정산캘린더)만 병합 대기** — 통합 세션에 병합·재배포 요청함(소유자 지시). 재배포는 18:00 정산 라이브 확인 후 통합 판단.
- 시작 시: `git fetch` 없이 로컬 `git log master..HEAD`·`git merge --ff-only master`(또는 master 합치기)로 기준 맞춘 뒤 착수.
- 운용 PC 자료 분석은 소유자가 zip(`output\정산\`)·`_요청기록.json` 을 Downloads 로 가져다 줌 → 스크래치에 풀어 분석.
- 라이브 확인용 계정 = **nicoable**(운용 PC 처리 완료·노트북 프로필 warm·앱 credstore 비번). 노트북에서 요청/받기 `run` 금지(운용 PC가 받는 중 → 중복 요청), 조회만.

## 요구·운용 (소유자 확정)
- 위탁 계정 전부(계정 파일 43개 `data\정산_계정목록.txt`)의 윙 정산현황 + 로켓그로스 정산현황(판매수수료+비용 리포트 8종) 2026-01~ 받기 → 파일명=`대표자-사업자-계정ID_정산일_채널_유형_리포트_기간`.
- 계약자 정산금액 = 계약금액 − 쿠팡 정산금(사업자 계좌로 직접 입금된 몫) — **계약(②층) 단계는 보류**(약정 총액 정의 등 소유자 확인 대기).
- 운용 = 운용 PC `정산다운로드.exe watch`(설치 시 자동 등록) · 24시간 감시·①판매수집 중만 일시정지(통합 02374f8) · 소급 끝나면 ①완료마다 하루 1회. 요청 간격 45~75초.
- 비번 오류 3계정(bandu11·bongfarm2003·globalline) = 재시도 안 함 → 소유자가 계정 파일 비번 확인 필요.

## 쿠팡 주소(API) 실측 — 전부 로그인 세션 페이지 안 same-origin fetch(XSRF 헤더) · 자세한 표=`settlement_wing_api.py`·`settlement_verify_collect.py` 모듈 독스트링
- 윙: 일정 `payment-report/list` · 요청 `common/excel/revenue-detail/request` · 목록 `common/excel/list` · 정산캘린더 `payout-date-calendar/payout-dates`(폼 본문).
- 로켓그로스: 일정 `rfm/v2/settlements/status/api`(UTC→+9h) · 요청 `request-download/api`(requestId로 목록과 짝) · 목록 `download-list/api` · 받기 `download/api/v2`→S3.
- 검증 자료(조회만): 월렛 입출금·잔액 · 매출내역 · 윙/RG 부가세 · 보류·추가지급 · 정산캘린더. ⚠ 메뉴 화면을 연 뒤 조회해야 함(아니면 504)·오늘 이후 날짜 넣으면 504.
- 쿠팡 502·503·504 = 일시 오류(재시도·'대기') · 차단 = 403·429·차단 화면만.

## 확정 규칙 (실측·공식 근거)
- 금액: 윙 70%=주합계×0.7 사사오입 · 윙 최종 30%=월합계−Σ주별70% · RG 70%=줄별 70% 합·30%=나머지. RG 최종지급액 = H(지급액)−I(추가상계)−J(이번 정산 물류비)+K(재고손실보상)+매출조정 (629/629).
- 돈의 흐름(쿠팡 도움말 「로켓그로스 상품의 정산은 어떻게 되나요?」): RG 최종지급액−재고손실보상 = 월렛 입금(19/19) · **재고 손실 보상 = 대표 정산 계좌로 정산일 별도 입금** · 마이너스 물류비 = 익월 21일 대표계좌 환급. 집계 '계좌 입금' 시트 = 쿠팡 지급 합계/대표계좌 입금 합계(차이=월렛 잔액).
- 지급일: **윙 = 쿠팡 정산캘린더가 정본**(30% 최종액=익익월 1일·휴일이면 다음 영업일 — 골든 '보정 없음'은 틀림, 통제에 보고) · **RG = `payout.rg_payout_date`**(70·100%=주마감+20영업일 · 30% 월걸침 주=+25 · 30% 일반=익익월 첫 영업일, 629/629). 2026 노동절(5/1)·제헌절(7/17) 법정공휴일·쿠팡도 비영업일.
- 파일 읽기: 윙 배송비 줄 빈 금액=0 · RG 정산대상액=판매액(A×B)−쿠폰−수수료−VAT · 반출비 '쿠팡귀책' 시트=수량 안내(제외) · 비용 상세 합=요약 합계(679시트) · 반출 배송 박스 여러 상품='(여러 상품)' 묶음.

## 미해결 (사실/미확인 구분)
- (대기) 9eb8df3 병합·재배포 — 통합 세션.
- (대기) 운용 PC 공휴일 API 키(특일정보) 등록 여부 — 없으면 RG 지급일 대조만 '자료 없음'. 키 발급=소유자(data.go.kr).
- (대기) 골든 `PAYOUT_MP_WEEKLY_FINAL` 수정·`payout.py` 윙 30% 규칙 — 통제 판단(검증은 캘린더라 급하지 않음).
- (미확인) 윙 1원 차이 1건(12-15~21 63,175 vs 63,174)·윙 2025-11 최종액 30% 차이 55,001(wellbing) — 원인 미상.
- (정리 후보) `tools/settlement_download.py` 668줄(지침 600)·`tools/verify_settlement_offline.py` 1,100줄 → 분할.

## 다음 작업 후보
1. 재배포 후 운용 PC 집계 `정산집계_*.xlsx` '검증'·'계좌 입금' 시트 확인(43계정 다름·확인 필요 0 목표).
2. 계약 정산(②층) — 소유자 결정 후. 3. 위 파일 분할(테스트 보호 아래).

[[settlement-domain-knowledge]] · [[feedback-accuracy-over-speed-and-lane-handoff]] · [[policy-per-domain-sessions]]
