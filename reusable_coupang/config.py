"""reusable_coupang 설정값 — 사람 타이핑 리듬·순위 스캔·상호작용 스위치.

다른 프로젝트로 **폴더째 복사**해 쓰는 것을 전제로, 원본 프로젝트의 거대한 config.py 에서
이 두 모듈(auto_login·rank_search)과 그 의존(human_typing·human_mouse)이 실제로 참조하는
상수만 발췌했다. 값의 근거는 각 주석 참고(대부분 라이브 실측으로 튜닝된 값).

⚠️ 튜닝 원칙: 사람 타이핑/간격은 **너무 빠르면(로봇 티) Akamai 봇탐지에 불리**하다.
   기본값은 "초중급자 타이핑 + 사람 간격"으로 실측 튜닝된 값이니, 급하게 낮추지 말 것.
"""
from __future__ import annotations

# ── 순위 스캔 ────────────────────────────────────────────────────────────────
RANK_SCAN_MAX = 50            # 오가닉 몇 위까지 셀지(광고 제외). 이 밖이면 순위 None(=상한 밖). 50=속도·저부하.
RANK_INCLUDE_MOBILE = False   # 모바일 순위도 조회할지(모바일 UA 에뮬레이션). 기본 False(PC만).

RANK_PAGE_DELAY_MIN = 2.0     # 검색 결과 '페이지 간' 최소 지연(초). 스캔50=1페이지라 거의 미발동(2페이지+ 시 여유).
RANK_PAGE_DELAY_MAX = 5.0     # 검색 결과 '페이지 간' 최대 지연(초).

# ── 사람 마우스/스크롤 상호작용(human_mouse) ──────────────────────────────────
# 검색창으로 커서를 곡선 이동, 결과를 읽는 듯 호버·스크롤(클릭은 절대 안 함). 실제 브라우저 Input 이벤트(위조 아님).
RANK_HUMAN_INTERACT = True    # False 면 마우스/스크롤 재현을 전부 끔(순위 조회 자체엔 영향 없음).

# ── 사람 타이핑 리듬(human_typing) ────────────────────────────────────────────
TYPE_JAMO_IME = True          # 한글을 CDP IME '자모 단위 조합'으로 칠지(가장 사람같음). False면 음절 단위 신뢰 키입력.
TYPE_JAMO_COMMIT_MODE = "eojeol"   # 한글 조합 커밋 단위: "eojeol"(어절 1회·기본) / "syllable"(음절마다). A/B용 스위치.

TYPE_KEY_DELAY_MIN = 0.14     # 한 자모/글자 친 뒤 다음까지 기본 간격 하한(초).
TYPE_KEY_DELAY_MAX = 0.38     # 기본 간격 상한 — 평균 ~0.26s/키 = 초중급 ~3~4타/초(붙여넣기와 확연히 다른 사람 리듬).
TYPE_HESITATE_PROB = 0.22     # 가끔 '망설임'(키 찾기) 발생 확률.
TYPE_HESITATE_MIN = 0.25      # 망설임 시 추가 지연 하한(초).
TYPE_HESITATE_MAX = 0.75      # 망설임 시 추가 지연 상한(초).
TYPE_LONGPAUSE_PROB = 0.05    # 드물게 '긴 멈춤'(생각) 발생 확률.
TYPE_LONGPAUSE_MIN = 0.8      # 긴 멈춤 추가 지연 하한(초).
TYPE_LONGPAUSE_MAX = 1.6      # 긴 멈춤 추가 지연 상한(초).
