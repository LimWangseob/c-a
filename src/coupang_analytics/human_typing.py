"""사람처럼 한 글자씩 실제 키보드로 입력 — 붙여넣기(비신뢰 input) 대신 **신뢰 키이벤트**.

⚠️ 실측(사용자, 2026-09-13): 쿠팡 Akamai는 **붙여넣기/즉시 채움**(value setter·fill = isTrusted=false input,
keydown 없음)을 짧은 쿼리로 감지해 차단하고, **실제 키보드로 한 글자씩** 친 입력만 통과시킨다.
그래서 검색어·로그인 입력을 여기로 통일한다:
- **한글** = CDP IME **자모 단위 조합**(자모마다 keyCode 229(Process) keydown + `Input.imeSetComposition`
  으로 조합 텍스트 갱신(compositionupdate) → 음절 완성 시 `Input.insertText` 로 커밋(compositionend)).
  실제 IME 타이핑과 같은 이벤트열(keydown 229 · compositionstart/update/end · input)을 낸다.
- **영문/숫자/기호** = `page.keyboard.type(ch)`(ASCII는 keydown/keypress/keyup 발생).
- 글자(자모)마다 **미세 랜덤 간격**(사람 타이핑 리듬). CDP/조합 실패는 조용히 무시(호출부가 값 검증·폴백).
"""
from __future__ import annotations

import random
import time

from . import config

# 2벌식 자모 → 물리 키 code(+shift 여부). 조합 keydown 에 실어 진짜 IME keydown(code=물리키)처럼 보이게 한다.
_JAMO_KEY = {
    "ㅂ": ("KeyQ", False), "ㅈ": ("KeyW", False), "ㄷ": ("KeyE", False), "ㄱ": ("KeyR", False),
    "ㅅ": ("KeyT", False), "ㅛ": ("KeyY", False), "ㅕ": ("KeyU", False), "ㅑ": ("KeyI", False),
    "ㅐ": ("KeyO", False), "ㅔ": ("KeyP", False), "ㅁ": ("KeyA", False), "ㄴ": ("KeyS", False),
    "ㅇ": ("KeyD", False), "ㄹ": ("KeyF", False), "ㅎ": ("KeyG", False), "ㅗ": ("KeyH", False),
    "ㅓ": ("KeyJ", False), "ㅏ": ("KeyK", False), "ㅣ": ("KeyL", False), "ㅋ": ("KeyZ", False),
    "ㅌ": ("KeyX", False), "ㅊ": ("KeyC", False), "ㅍ": ("KeyV", False), "ㅠ": ("KeyB", False),
    "ㅜ": ("KeyN", False), "ㅡ": ("KeyM", False),
    "ㅃ": ("KeyQ", True), "ㅉ": ("KeyW", True), "ㄸ": ("KeyE", True), "ㄲ": ("KeyR", True),
    "ㅆ": ("KeyT", True), "ㅒ": ("KeyO", True), "ㅖ": ("KeyP", True),
}

# 한글 조합 테이블(유니코드 한글 음절 = 0xAC00 + 초성*588 + 중성*28 + 종성)
_CHO = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")                       # 19
_JUNG = list("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")                  # 21
_JONG = [""] + list("ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ")   # 28(0=받침없음)
# 복합 자모 → 기본 자모 키 2개(2벌식에서 두 번 눌러 만든다)
_JUNG_PARTS = {"ㅘ": ("ㅗ", "ㅏ"), "ㅙ": ("ㅗ", "ㅐ"), "ㅚ": ("ㅗ", "ㅣ"), "ㅝ": ("ㅜ", "ㅓ"),
               "ㅞ": ("ㅜ", "ㅔ"), "ㅟ": ("ㅜ", "ㅣ"), "ㅢ": ("ㅡ", "ㅣ")}
_JONG_PARTS = {"ㄳ": ("ㄱ", "ㅅ"), "ㄵ": ("ㄴ", "ㅈ"), "ㄶ": ("ㄴ", "ㅎ"), "ㄺ": ("ㄹ", "ㄱ"),
               "ㄻ": ("ㄹ", "ㅁ"), "ㄼ": ("ㄹ", "ㅂ"), "ㄽ": ("ㄹ", "ㅅ"), "ㄾ": ("ㄹ", "ㅌ"),
               "ㄿ": ("ㄹ", "ㅍ"), "ㅀ": ("ㄹ", "ㅎ"), "ㅄ": ("ㅂ", "ㅅ")}
_JUNG_COMBINE = {v: k for k, v in _JUNG_PARTS.items()}   # ('ㅗ','ㅏ') → 'ㅘ'
_JONG_COMBINE = {v: k for k, v in _JONG_PARTS.items()}


def human_key_delay() -> float:
    """한 자모/글자 친 뒤 다음까지 간격(초) — **초중급자 타이핑 속도**(느리고 불규칙). config 로 조절.

    기본 타건 간격 + 가끔 '망설임'(키 찾기) + 드물게 '긴 멈춤'(생각). 붙여넣기(즉시)와 확연히 다른 사람 리듬.
    """
    d = random.uniform(config.TYPE_KEY_DELAY_MIN, config.TYPE_KEY_DELAY_MAX)
    r = random.random()
    if r < config.TYPE_LONGPAUSE_PROB:              # 드물게 긴 멈춤(생각·다음 글자 떠올림)
        d += random.uniform(config.TYPE_LONGPAUSE_MIN, config.TYPE_LONGPAUSE_MAX)
    elif r < config.TYPE_LONGPAUSE_PROB + config.TYPE_HESITATE_PROB:   # 가끔 망설임(키 찾기)
        d += random.uniform(config.TYPE_HESITATE_MIN, config.TYPE_HESITATE_MAX)
    return d


def _is_hangul_syllable(ch: str) -> bool:
    return 0xAC00 <= ord(ch) <= 0xD7A3


def _decompose(syllable: str):
    """한글 음절 → (초성, 중성, 종성|'')."""
    code = ord(syllable) - 0xAC00
    if not (0 <= code < 11172):
        return None
    return _CHO[code // 588], _JUNG[(code % 588) // 28], _JONG[code % 28]


def _compose(cho: str, jung, jong) -> str:
    """(초성, 중성|None, 종성|'') → 조합 문자(중성 없으면 초성 호환자모만)."""
    if jung is None:
        return cho                                   # 초성만 = 호환 자모(ㅁ 등)
    ci, ji = _CHO.index(cho), _JUNG.index(jung)
    ki = _JONG.index(jong) if jong else 0
    return chr(0xAC00 + ci * 588 + ji * 28 + ki)


def _syllable_steps(syllable: str):
    """음절을 자모 키 순서로 조합 — 각 키입력의 **(누른 자모, 그 후 조합 텍스트)** 리스트(마지막=완성 음절)."""
    d = _decompose(syllable)
    if not d:
        return None
    cho, jung, jong = d
    steps = [(cho, _compose(cho, None, None))]       # 초성 키
    acc = []
    for p in _JUNG_PARTS.get(jung, (jung,)):         # 중성(복합이면 2키)
        acc.append(p)
        jnow = acc[0] if len(acc) == 1 else _JUNG_COMBINE[tuple(acc)]
        steps.append((p, _compose(cho, jnow, None)))
    if jong:
        gacc = []
        for p in _JONG_PARTS.get(jong, (jong,)):     # 종성(복합이면 2키)
            gacc.append(p)
            gnow = gacc[0] if len(gacc) == 1 else _JONG_COMBINE[tuple(gacc)]
            steps.append((p, _compose(cho, jung, gnow)))
    return steps


def _cdp(page):
    try:
        return page.context.new_cdp_session(page)
    except Exception:
        return None


def _ime_run(cdp, syllables: list, delay) -> None:
    """연속 한글 음절(**어절**)을 **하나의 조합 세션**으로 자모 단위 입력 후 **커밋 1회**.

    각 자모마다 keydown(keyCode 229 Process + 물리키 code) + imeSetComposition(조합 텍스트) + keyup.
    조합 텍스트 = 이미 친 음절들 + 현재 음절의 부분조합(예 맥→맥무→맥문…) → 어절 끝에 insertText 1회로 커밋.
    ⇒ `compositionend`(isTrusted=false, CDP 한계)가 **음절마다(N개) → 어절당 1개**로 축소(탐지 스코어 누적 완화).
    """
    committed = ""                                   # 이 어절에서 지금까지 완성된 음절들(아직 커밋 전, 조합 접두)
    for syl in syllables:
        steps = _syllable_steps(syl)
        if steps is None:                            # 음절 아님(방어) — 그대로 이어붙임
            committed += syl
            continue
        for jamo, partial in steps:                  # 자모 하나씩: 조합 텍스트(접두+부분) 갱신
            code, shift = _JAMO_KEY.get(jamo, ("", False))
            mod = 8 if shift else 0                   # 8 = Shift(CDP modifiers 비트)
            comp = committed + partial
            try:
                cdp.send("Input.dispatchKeyEvent",
                         {"type": "rawKeyDown", "windowsVirtualKeyCode": 229, "code": code,
                          "key": "Process", "modifiers": mod})
                cdp.send("Input.imeSetComposition",
                         {"text": comp, "selectionStart": len(comp), "selectionEnd": len(comp)})
                cdp.send("Input.dispatchKeyEvent",
                         {"type": "keyUp", "windowsVirtualKeyCode": 229, "code": code,
                          "key": "Process", "modifiers": mod})
            except Exception:
                pass
            time.sleep(delay())
        committed += syl                             # 이 음절 완성 → 접두에 누적(조합은 계속 이어감)
    try:
        cdp.send("Input.insertText", {"text": committed})   # 어절 전체 커밋 1회(compositionend 1개)
    except Exception:
        pass


def type_focused(page, text: str, *, jamo: bool = True, delay=None) -> None:
    """**이미 포커스된** 입력요소에 text 를 한 글자씩 친다(한글=CDP IME 조합, ASCII=키입력, 글자마다 미세 랜덤 간격).

    요소 포커스·기존값 삭제는 호출부 책임. 값 검증/폴백도 호출부가(여기선 예외를 삼키고 최대한 입력만).
    """
    delay = delay or human_key_delay
    need_ime = jamo and any(_is_hangul_syllable(c) for c in text)
    cdp = _cdp(page) if need_ime else None
    try:
        run: list = []                               # 연속 한글 음절(어절) 버퍼 — 한 조합 세션으로 처리
        for ch in text:
            if cdp is not None and _is_hangul_syllable(ch):
                run.append(ch)
                continue
            if run:                                  # 어절 끝(공백/영문/기호) → 지금까지 한글을 한 번에 조합·커밋
                _ime_run(cdp, run, delay)
                run = []
            try:
                page.keyboard.type(ch)               # 비한글(ASCII/공백/기호)은 실제 키입력
            except Exception:
                pass
            time.sleep(delay())
        if run:                                      # 마지막 어절 커밋
            _ime_run(cdp, run, delay)
    finally:
        if cdp is not None:
            try:
                cdp.detach()
            except Exception:
                pass
