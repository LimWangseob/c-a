---
name: input-ledger-format
description: "입력 기준=셀독 관리대장(구글시트, 헤더 2행, vid/pid 없음). 그로스 재고 역기록(유사도 매칭)"
metadata:
  node_type: memory
  type: project
  originSessionId: e9438a2f-e201-48d4-bf71-5cdf2500b598
  modified: 2026-09-20T01:55:12.106Z
---

입력 기준 파일 = **셀독 관리대장**(구글시트 원본, 본체시트=`셀독리스트`). 규모 ~22계정·65상품(취소선 7건 제외 후).

**구조**: 헤더 2행(행1=잔여 예시값, 행2=헤더). **가져오는 값=사업자·계정아이디·상품명(필수 3개)**(대표자명 선택). **옵션/vendorItemId/productId 미파싱**(대장에 없음·미사용, vid는 판매분석 API가 라이브 발견). 계정식별열이 상품행에 세로병합 → 다운로드/API 모두 상단행에만 값 → 파서 '빈 계정칸=상속' 그룹핑(정상). 헤더 1~8행 자동감지(`_find_header_row`, 파일=헤더1행 하위호환).

**대장 중복 상품 정책(2026-09-20 소유자)**: 한 계정에 **같은 상품명 2줄 이상**=담당자 오입력 → **첫 줄만 추적**, 나머지 중복 줄 제거(공백정리 후 동일 판정·대소문자 유지·`struck` 경고). `_parse_grid` 말미 계정별 dedup(파일·구글시트 공용). 계기=알부민이 대장 2줄이라 쿠팡 1개를 1줄만 매칭·나머지 미매칭이던 문제. 검증 verify_offline[13].

**연동**: 원본 구글시트를 **서비스계정 Sheets API 직접** 읽음(`read_ledger_rows`→`(title, rows, strike_grid)`, `parse_input_rows`). 무인 실행이 매번 최신 시트 fetch(URL=QSettings `gsheet/input_url`). ⚠ 내려받은 값에 평문 비번 → 파싱 직후 DPAPI 저장·임시삭제(평문 금지).

**삭제/판매중지 제외**: **취소선**(Sheets API `read_grid_struck`가 `effectiveFormat.textFormat.strikethrough`+`textFormatRuns`로 읽음 — 옛 전제 '못읽는다'는 틀림) **OR 상태 컬럼**(config.IN_STATUS_DISCONTINUED). 파일경로와 OR 판정 일치.

**그로스 재고 역기록**(전체실행·무인 종료 시 입력 대장에 쓰기, `pipeline.push_ledger_inventory`→`input_list.write_ledger_inventory`): 수집 재고를 **셀독리스트 `AD` "그로스 재고 (…기준/자동갱신)" 컬럼**에 써넣음. **대상=AD(‘기준’), BW ‘그로스재고’ 아님(사용자확정)**. 헤더 재탐지=‘그로스’+‘재고’+(‘기준’|‘갱신’). **매칭키=계정(사업자)+등록상품명 유사도**(`_best_inventory_match`: ①공백제거 완전일치 → ②IDF 가중 재현율, corpus=전체 대장+워크북 상품명이라 규격·브랜드어[120정·프리미엄·MAX]는 눌리고 핵심어[베타글루칸·알부민]는 부각, 핵심토큰 덮는 후보만 후보군, 임계0.55·2등마진 미달 미매칭). **미매칭·개인상품·미수집·비상품행은 기존값 보존**(직원 다른 컬럼 미접촉). ⚠ SA에 관리대장 편집권한 필요(없으면 403→로그·비치명). 실측 교훈: 단순 토큰겹침은 브랜드·규격 공통토큰 때문에 베타글루칸→알부민(0.79) 오매칭 → IDF+핵심토큰 게이팅으로 해결(라이브 75행·19매칭·오매칭0).

**Why/How:** 사용자 실제 관리대장이라 서식·헤더 위치 가변. 관련 [[seldoc-output-format]] [[runtime-ui-and-always-on]] [[fix-from-real-evidence]].
