---
name: rank-blocked-placeholder-50
description: "결과파일 노출순위 \"50위\"는 실제 50위밖과 차단/미측정을 구분 못하는 placeholder. 차단은 첫 계정부터 실행전체 순위중단 + is_rank_filled 고착"
metadata: 
  node_type: memory
  type: project
  originSessionId: 5de72db9-7e02-4d7c-8021-a6f0939dde64
  modified: 2026-09-10T06:08:06.785Z
---

**2026-09-10 실측 확인.** 결과파일(`쿠팡데이타분석_통계.xlsx`)의 **노출순위 "50위"는 대부분 실제 순위가 아니라 차단/미측정 placeholder**다.

**메커니즘(코드 실측):**
- `workbook.set_keyword_rank`(303행): `val = f"{rank}위" if rank else f"{RANK_SCAN_MAX}위"` → rank=None이면 **"50위"** 기록. **문제: None의 두 원인(①실제 50위밖 미노출 ②검색 차단/미측정)을 똑같이 "50위"로 기록** → 파일만 보면 구분 불가.
- `pipeline._RANK_HALT`(112·156행): 순위 차단(RankBlocked) 한 번 감지되면 **그 실행의 이후 모든 순위조회가 즉시 빈결과(None)**. 2026-09-10 run(115629)은 **첫 계정 웰빙곳간(11:58:43)에서 차단** → 이후 전 계정 순위가 전부 None→"50위"로 기록됨(화면 균일 "50위"의 진짜 이유). 132009 재개도 유라이프(13:22)에서 재차단.
- **고착 이슈**: `is_rank_filled`(144행)는 값이 None/""/"-"가 아니면 채움으로 판정 → **"50위"(차단 placeholder)도 "채움"** → **`이어서(resume)`가 재측정 안 함**. 즉 차단으로 잘못 박힌 "50위"는 재실행해도 자동 교정 안 됨.

**영향 구분:**
- ✅ **판매지표(판매량·방문자·노출량·재고현황)는 실제값**(판매분석 API=계정별 세션, 차단 안 됨). 단 D-1(09-09)은 대부분 0/저조가 정상([[coupang-sales-data-lag]]).
- ❌ **노출순위는 이 실행에서 사실상 전부 무효**(첫 계정부터 차단). 실제 순위 아님.

**✅ 수정됨(2026-09-10):** `pipeline._process_account` 순위 기록 루프에 `blocked=_RANK_HALT["stop"]` 가드 추가 — **차단된 실행에서 미측정(None)은 "50위" 위장 대신 공란**으로 남긴다(is_rank_filled=False 유지 → 다음 쉰 IP 실행이 그 순위만 재측정). 차단 아닌 실 미노출(None)만 RANK_SCAN_MAX="50위" 기록. **단, 이 픽스는 새 실행부터 적용** — 기존 통계.xlsx의 "50위" 고착은 안 풀리므로 **새 통계(fresh)로 재실행해야** 깨끗해짐.
**남은 대책:** 순위는 **쉰 IP/다른 시간에 순위만 재조회**(판매수집과 분리 [[pipeline-3stage-separation]] [[login-block-session-first-circuit-breaker]]). 순위매칭은 vendorItemId 기준([[coupang-official-reference]]).
