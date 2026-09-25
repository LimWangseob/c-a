---
name: keyword-methodology-ai-anchor
description: 키워드 도출·제목처방 방법론(구현완료) — AI 앵커+4소스 후보→핵심/연관판정→Score→AI종합선정→순위진단→권고제목
metadata:
  node_type: memory
  type: project
  originSessionId: 4ca6f1ec-575b-4e8e-8476-c3c67cf979b3
  modified: 2026-09-17T08:02:00.392Z
---

상품 제목→추적 키워드 도출 방법론(구현완료). **AI 제공자=OpenAI ChatGPT**(config.KW_AI_MODEL, credstore `__openai__`, 없으면 실행중단·폴백없음). 구현=`kw_recommend._assemble_candidates`/`select_keywords_light`, `kw_ai`(analyze_product/generate_keywords/judge_keywords/select_keywords/recommend_title), `kw_suggest`.

**파이프라인**: ①**후보 4소스** = 네이버 앵커연관(≥KW_MIN_VOLUME=500) + **쿠팡 자동완성=연관검색어**(`kw_suggest.collect_suggestions`, browser 있을 때만, 시드=core+identities, 엔드포인트 `www.coupang.com/n-api/web-adapter/search?keyword=` rank_browser 세션 same-origin fetch) + AI 조합생성(정체성×속성, ≥30) + 네이버 2단계확장(상위 KW_EXPAND2_N=6 재시드). ②`judge_keywords` AI 핵심/연관/탈락({kw:(tier,match)}). ③Score(관련성35+구매의도25+검색량20+쿠팡노출15+추세5)로 압축→쿠팡 실노출 측정→등급. ④`select_keywords` AI 종합 최종선정(역할 REP/SALES/GROWTH/DEFENSE).

**핵심 규칙(실증으로 굳음)**:
- **정체성 보호**: core·identities에 형태/단위 단독어(환·정·세트·진액) 금지 → 반드시 성분+형태('맥문동환'). 상품 자기 정체성(core+identities+anchors)은 **검색량 하한 무관 항상 후보 포함**(니치 상품 자기이름 보호, 네이버가 값 준 것만).
- **구매의도(쇼핑성) 대전제**: judge는 쇼핑성 있어야 CORE/RELATED, 정보성·증상성(효능·~에좋은음식·~증상·먹는법)·타사브랜드 DROP. select도 정보성·형태단독어는 검색량 커도 배제.
- **띄어쓰기 = 유의미(2026-09-17, 09-15 병합 되돌림)**: 라이브서 쿠팡 '캠핑타프'≠'캠핑 타프'(노출순위 다름) 확인 → 별개 키워드로 취급(합치지 않음). `_assemble_candidates`의 by_norm 병합 블록 **제거**(pool은 정확표기 키잉=완전 동일만 중복제거), `exclude`·`workbook.add_product_keywords` dedup을 **strip 후 정확일치**로 완화 → 직원이 시트에 넣은 띄어쓰기 변형도 추가·추적됨. 순위 검색 타이핑은 원래부터 공백 그대로. 관련성 매칭(keyword_in_title·인접어)만 여전히 공백무시(매칭이지 dedup 아님). 앞으로만 적용. `_norm`(공백+casefold)은 매칭용으로 잔존.

**제목처방**(`_prescribe_title`): keyword_in_title(띄어쓰기무시)·diagnose_exposure(제목포함×순위→노출불가/마케팅필요/양호, RANK_GOOD_THRESHOLD=20)·recommend_title(쿠팡 공식 상품명 기준·검색량순)·권고검색태그(제목 못담은 키워드). 워크북 상품메타 행.

**경쟁강도 소스 소멸**: 네이버쇼핑 API 2026-07-31 종료 → 현재 수요순만(공란), 대안=쿠팡 총상품수 보류. [[naver-shopping-api-terminated]]. 상세 SSOT=`designs/KEYWORD_SELECTION.md`. 관련=[[daily-stats-keyword-freeze]] [[wing-keyword-data-subscription-gated]] [[fix-from-real-evidence]] [[respond-in-korean]].
