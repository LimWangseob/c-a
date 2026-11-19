"""셀독 계약자별 상품 현황 — 판정 3단 중 ③ AI 판정 + 판정표 파일(설계안 3절 · 전역 AI 매칭 규칙 · D-358).

- 프로그램은 **후보만** 뽑는다: ①VID 고정 ②같은 상품명에 안 걸린 개인 상품 중 대장 상품과 모델코드가 겹치거나
  낱말이 2개 이상 겹치는 것. 판정은 AI(product_match_ai.openai_ask 경로 재사용)가 하고 근거 원문을 남긴다.
- 판정표 = `output/_계약자시트_판정.json` {계정: {VID: [판정 기록 …]}} — **덧붙이기만**(옛 판정을 지우지 않음).
  같은 VID 는 다시 묻지 않는다(AI 판정 기록이 있으면 그 판정 · 같은 상품의 새 VID 는 그 상품 기존 판정을 이어 적음).
  규칙 판정(VID 고정·같은 상품명·후보 아님)도 바뀔 때만 한 줄 덧붙인다(매일 같은 줄을 쌓지 않음).
- 애매(확신 낮음·셀독 여부 없음) = '확인 필요'로 판정표에만 남기고 시트에는 바탕색 없는 '개인'(사람 승인 대기열 아님 D-070).
- AI 실패(키 없음·호출 실패·답 빠짐) = ⚠ 로그 · 그날은 '개인'으로 표시하고 기록하지 않음(다음 실행이 다시 물음 — 조용한 폴백 아님).
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Callable

from .contractor_sheet import Prod

JUDGE_FILE = "_계약자시트_판정.json"
SELDOC, PERSONAL, UNSURE = "셀독", "개인", "확인 필요"
STEP_AI, STEP_RULE, STEP_NOCAND = "AI", "규칙", "후보 아님"
SURE = ("high", "medium")
_WORD = re.compile(r"[0-9A-Za-z가-힣]+")
_CODE = re.compile(r"[A-Za-z]{1,5}-?\d{2,}[A-Za-z0-9]*")

# 예시는 가상 상품(실제 계정·상품명이 지시문에 있으면 판단이 그쪽으로 기울 수 있음 — product_match_ai 와 같은 원칙).
SYSTEM = (
    "너는 쿠팡 판매자 계정에 올라 있는 상품이 '셀독 관리대장 상품'과 같은 상품인지 판정한다.\n"
    "배경: 이 계정에는 셀독이 관리하는 상품(관리대장 목록)과 계정 주인이 따로 올린 개인 상품이 섞여 있다. "
    "관리대장 상품은 이미 VID·같은 상품명으로 찾았고, 여기 후보는 거기에 안 걸린 상품이라 대부분 개인 상품이다.\n"
    "판단:\n"
    "1. 후보가 관리대장의 어느 한 상품과 **같은 상품**(용도·종류·모델이 같음 — 수량·옵션·판매방식만 다른 재등록 포함)이면 셀독.\n"
    "2. 글자가 겹쳐도 다른 상품이면 개인 — 예: '접이식 캠핑의자 CH100' ≠ '캠핑 테이블 CH200', '요가매트' ≠ '요가 양말'.\n"
    "3. 브랜드·회사 이름만 같은 것은 같은 상품이 아니다. 띄어쓰기·꾸밈말(프리미엄·MAX·신형)은 의미에 영향 없음.\n"
    "confidence: high=분명함 · medium=근거 충분 · low=확신 부족.\n"
    '반드시 JSON 객체로만 답한다: {"judgments":[{"line":줄번호,"seldoc":true 또는 false,'
    '"ledger":"같은 대장 상품 번호(예 대장2) 또는 null","confidence":"high|medium|low","reason":"30자 이내"}]}'
    " — 받은 모든 줄에 답한다."
)


def tokens(text: str) -> tuple[set[str], set[str]]:
    """(모델코드, 낱말) — 낱말 = 두 글자 이상(숫자만은 뺌) · 소문자."""
    s = str(text or "")
    codes = {m.lower() for m in _CODE.findall(s)}
    words = {w.lower() for w in _WORD.findall(s) if len(w) >= 2 and not w.isdigit()}
    return codes, words


def is_candidate(name: str, ledger_tokens: list[tuple[set[str], set[str]]]) -> bool:
    codes, words = tokens(name)
    return any(codes & lc or len(words & lw) >= 2 for lc, lw in ledger_tokens)


# ── 판정표 파일 ───────────────────────────────────────────────
def load(path: Path) -> dict:
    """판정표 읽기. 손상 = 예외 그대로(덮어써서 옛 판정을 잃지 않게 호출부가 멈춤)."""
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def save(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _latest(data: dict, acc: str, vid: str, step: str | None = None) -> dict | None:
    rows = [r for r in (data.get(acc) or {}).get(vid) or [] if step is None or r.get("단계") == step]
    return rows[-1] if rows else None


def append(data: dict, acc: str, vid: str, entry: dict) -> bool:
    """판정 기록 덧붙이기 — 그 VID 마지막 기록과 판정·단계·근거가 같으면 안 붙임(매일 같은 줄 쌓지 않음)."""
    last = _latest(data, acc, vid)
    if last and all(last.get(k) == entry.get(k) for k in ("판정", "단계", "근거")):
        return False
    data.setdefault(acc, {}).setdefault(vid, []).append(entry)
    return True


def _entry(verdict: str, step: str, reason: str, p: Prod, now: str, **extra) -> dict:
    return {"판정": verdict, "단계": step, "근거": reason, "상품명": p.name, "시각": now, **extra}


# ── AI 판정 ───────────────────────────────────────────────
def build_user(ledger: list[str], cands: list[Prod]) -> str:
    """후보 줄 = 'L번호'(openai_ask 가 'L' 줄 수로 답 길이를 잡음) · 대장 = '대장번호'."""
    lines = ["관리대장 상품:"] + [f"대장{i}. {n}" for i, n in enumerate(ledger, 1)]
    lines += ["", "판정할 후보(상품명 | 판매방식 | 판매상태):"]
    lines += [f"L{i}. {p.name} | {p.method} | {p.status}" for i, p in enumerate(cands, 1)]
    return "\n".join(lines)


def parse(obj: dict, n: int, ledger: list[str]) -> dict[int, tuple[str, str, str]]:
    """AI 답 → {줄번호: (판정, 근거, 대장 상품명)}. 줄 번호가 범위 밖이거나 빠진 줄은 없음(다음 실행이 다시 물음)."""
    out: dict[int, tuple[str, str, str]] = {}
    for j in (obj or {}).get("judgments") or []:
        try:
            line = int(j.get("line"))
        except (TypeError, ValueError):
            continue
        if not 1 <= line <= n:
            continue
        conf = str(j.get("confidence") or "").lower()
        sd = j.get("seldoc")
        verdict = (SELDOC if sd is True else PERSONAL) if conf in SURE and isinstance(sd, bool) else UNSURE
        ref = re.sub(r"\D", "", str(j.get("ledger") or ""))
        lname = ledger[int(ref) - 1] if ref and 1 <= int(ref) <= len(ledger) else ""
        out[line] = (verdict, f"AI({conf or '확신 없음'}): {str(j.get('reason') or '').strip()}", lname)
    return out


def _known(data: dict, p: Prod) -> dict | None:
    """그 상품 VID 들의 AI 판정 중 가장 최근 것(같은 상품의 새 VID 는 이 판정을 이음)."""
    rows = [r for v in p.vids if (r := _latest(data, p.acc, v, STEP_AI))]
    return max(rows, key=lambda r: r.get("시각") or "") if rows else None


def _apply(p: Prod, verdict: str, reason: str) -> None:
    p.sel = verdict == SELDOC
    p.basis = f"AI 판정({verdict}) — {reason}"


def _triage(acc: str, prods: list[Prod], ledger: list[str], data: dict, now: str) -> list[Prod]:
    """규칙 판정·기존 AI 판정·후보 아님을 적용·기록하고, AI 에 물을 후보만 돌려줌."""
    lt = [tokens(n) for n in ledger]
    ask_list: list[Prod] = []
    for p in prods:
        if p.sel:
            for v in p.vids:
                append(data, acc, v, _entry(SELDOC, STEP_RULE, p.basis, p, now))
            continue
        known = _known(data, p)
        if known is not None:
            _apply(p, known["판정"], known["근거"])
            for v in p.vids:
                if _latest(data, acc, v, STEP_AI) is None:
                    append(data, acc, v, {**known, "근거": f"같은 상품 기존 판정 이음 — {known['근거']}", "시각": now})
        elif ledger and is_candidate(p.name, lt):
            ask_list.append(p)
        else:
            for v in p.vids:
                append(data, acc, v, _entry(PERSONAL, STEP_NOCAND, "대장 상품과 겹치는 모델코드·낱말 없음", p, now))
    return ask_list


def judge_account(acc: str, prods: list[Prod], ledger: list[str], data: dict,
                  ask: Callable[[str, str], dict] | None, log, now: str | None = None) -> int:
    """한 계정 — 개인 상품(prods 중 sel False)에 ③ 단계를 적용하고 판정표에 덧붙인다. AI 호출 수 반환(0 또는 1)."""
    now = now or datetime.now().isoformat(timespec="seconds")
    ask_list = _triage(acc, prods, ledger, data, now)
    if not ask_list:
        return 0
    if ask is None:
        log(f"  [계약자별 현황] ⚠ {acc}: AI 판정 후보 {len(ask_list)}개 — OpenAI 키 없음 → 오늘은 '개인'으로 표시(기록 안 함)")
        return 0
    try:
        got = parse(ask(SYSTEM, build_user(ledger, ask_list)), len(ask_list), ledger)
    except Exception as exc:                # AI 경로의 모든 실패(키·네트워크·JSON) — 명시하고 그날만 개인
        log(f"  [계약자별 현황] ⚠ {acc}: AI 판정 실패({exc.__class__.__name__}: {str(exc)[:80]}) — "
            f"후보 {len(ask_list)}개 오늘은 '개인'으로 표시 · 다음 실행이 다시 물음")
        return 1
    _record_ai(acc, ask_list, got, ledger, data, log, now)
    return 1


def _record_ai(acc: str, ask_list: list[Prod], got: dict, ledger: list[str], data: dict, log, now: str) -> None:
    for i, p in enumerate(ask_list, 1):
        if i not in got:
            log(f"  [계약자별 현황] ⚠ {acc}: AI 답에 후보 L{i} '{p.name[:30]}' 없음 — 오늘은 '개인' · 다음 실행이 다시 물음")
            continue
        verdict, reason, lname = got[i]
        _apply(p, verdict, reason)
        for v in p.vids:
            append(data, acc, v, _entry(verdict, STEP_AI, reason, p, now, 대장=lname, 대장후보=ledger))
    n_sel = sum(1 for i in got if got[i][0] == SELDOC)
    n_unsure = sum(1 for i in got if got[i][0] == UNSURE)
    log(f"  [계약자별 현황] {acc}: AI 판정 {len(got)}/{len(ask_list)}개 — 셀독 {n_sel} · 확인 필요 {n_unsure}(판정표에만)")


__all__ = ["JUDGE_FILE", "SELDOC", "PERSONAL", "UNSURE", "append", "build_user", "is_candidate", "judge_account",
           "load", "parse", "save", "tokens"]
