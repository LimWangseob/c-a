"""셀독등록원장 — 상품명 변경 의심 쌍 자동 판단(D-070·소유자 2026-10-16 "AI 가 판단해서 보정하고 자동 진행").

대장 상품명이 바뀌면 원장엔 '옛 이름 삭제 + 새 이름 추가'로 보인다. 사람 승인(확인필요) 대신 아래 순서로 판단한다.
  1) 글자 규칙 — 띄어쓰기·대소문자·괄호·문장부호만 다름 = 같은 상품(예 '코골이 방지 기구' ↔ '코골이 방지 기구(')
  2) 쿠팡 상품번호(VID) — 앱 매칭 고정 기록(output/_매칭고정.json)에 두 이름이 다 있으면 VID 가 겹침 = 같은 상품 ·
     하나도 안 겹침 = 다른 상품
  3) AI(OpenAI) — 이름·쿠팡 상품명으로 같은 상품인지 판단(모델명·설명 덧붙임 = 같음, 색상·용량·모델 다름 = 다름)
판단 = same(이름 변경 자동 승인) · different(다른 상품 — 옛 줄 관리중단·새 줄 신규) · unsure(AI 장애·애매 — 확인필요로
남겨 다음 실행에서 다시 판단). 판단 근거는 이력 비고에 남는다.
"""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

SAME, DIFFERENT, UNSURE = "same", "different", "unsure"

_SYSTEM = (
    "너는 쿠팡 위탁판매 상품 관리대장 검수자다. 담당자가 관리대장의 상품명을 고쳤을 때, 옛 이름과 새 이름이 "
    "같은 상품(이름만 고침: 오타·괄호·띄어쓰기 수정, 모델명·설명·노출명 덧붙임)인지, 다른 상품(색상·용량·수량·모델이 "
    "다른 별도 상품 — 관리대장은 색상·옵션별 줄을 별도 상품으로 관리)인지 판단한다. 확실하지 않으면 unsure. "
    'JSON 으로만 답: {"items":[{"id":번호,"verdict":"same|different|unsure","reason":"한 줄 근거"}]}'
)


def loose_key(name: str) -> str:
    """글자 규칙 키 — 띄어쓰기·대소문자·괄호·문장부호를 뺀 글자만(한글·영문·숫자)."""
    return "".join(re.findall(r"[0-9a-z가-힣]+", str(name or "").lower()))


def _anchor_vids(anchors: dict, aid: str, name: str) -> tuple[set, str]:
    rec = (anchors.get(aid) or {}).get(" ".join(str(name).split())) or {}
    return set(rec.get("vids") or []), str(rec.get("title") or "")


def load_anchor_file(path) -> dict:
    """앱 매칭 고정 기록 {계정: {대장명: {vids, title…}}} — 없으면 빈 dict(판단 2 생략)."""
    p = Path(path)
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def make_judge(ask=None, anchors: dict | None = None, log=None):
    """judge(aid, pairs[(옛, 새)]) → {(옛, 새): (판단, 근거)}. ask = AI 호출(system, user)→dict(없으면 3단계 생략=unsure)."""
    anchors = anchors or {}
    log = log or (lambda m: None)

    def judge(aid: str, pairs: list) -> dict:
        out, ai = {}, []
        for old, new in pairs:
            if loose_key(old) == loose_key(new):
                out[(old, new)] = (SAME, "글자 규칙 — 띄어쓰기·괄호·문장부호만 다름")
                continue
            ov, ot = _anchor_vids(anchors, aid, old)
            nv, nt = _anchor_vids(anchors, aid, new)
            if ov and nv:
                out[(old, new)] = ((SAME, f"쿠팡 상품번호 같음 {sorted(ov & nv)[:2]}") if ov & nv else
                                   (DIFFERENT, "쿠팡 상품번호 다름"))
                continue
            ai.append((old, new, ot, nt))
        if ai:
            out.update(_ask_ai(ask, aid, ai, log))
        return out
    return judge


def _ask_ai(ask, aid: str, items: list, log) -> dict:
    keys = [(o, n) for o, n, _ot, _nt in items]
    if ask is None:
        return {k: (UNSURE, "AI 판단 불가(키 없음)") for k in keys}
    lines = [f"{i}. 옛 이름: {o} → 새 이름: {n}" + (f" · 쿠팡 상품명(새 이름 매칭): {nt}" if nt else "")
             + (f" · 쿠팡 상품명(옛 이름 매칭): {ot}" if ot else "") for i, (o, n, ot, nt) in enumerate(items, 1)]
    try:
        res = ask(_SYSTEM, f"계정 {aid}\n" + "\n".join(lines))
        got = {int(x["id"]): x for x in (res or {}).get("items") or []}
    except Exception as exc:   # AI 장애 = 이번엔 판단 보류(확인필요로 남김·다음 실행에서 다시) — 로그로 명시
        log(f"  [원장] ⚠ 상품명 변경 AI 판단 실패({exc.__class__.__name__}) — 다음 실행에서 다시 판단")
        return {k: (UNSURE, "AI 판단 실패") for k in keys}
    out = {}
    for i, k in enumerate(keys, 1):
        x = got.get(i) or {}
        v = x.get("verdict") if x.get("verdict") in (SAME, DIFFERENT, UNSURE) else UNSURE
        out[k] = (v, "AI — " + str(x.get("reason") or "근거 없음")[:80])
    return out


def judge_account(reg, snap, old: str, new: str) -> tuple[str, str]:
    """계정아이디 변경 의심 쌍(사업자명·대표자명이 같은 1:1) 판단 — 원장·대장 자료만(AI 재료 없음·D-071).
    ① 대소문자·기호만 다름 = 같은 계정 ② 두 쪽 상품이 절반 이상 같음 = 같은 계정·상품이 다름 = 다른 계정
    ③ 한 쪽이 상품 없음 → 비밀번호 같고 아이디가 비슷(오타 수정) = 같은 계정, 아니면 다른 계정(같은 사업자의 새 계정).
    다른 계정 = 옛 계정 관리중단 + 새 계정 신규(이력 섞이지 않음 — 근거가 부족할 때의 안전한 쪽)."""
    if loose_key(old) == loose_key(new):
        return SAME, "계정아이디 대소문자·기호만 다름"
    olds = {loose_key(r.product) for r in reg.account_rows(old) if r.product}
    news = {loose_key(p) for p in snap.accounts[new].products}
    if olds and news:
        both = olds & news
        if len(both) * 2 >= min(len(olds), len(news)):
            return SAME, f"상품 {len(both)}개 같음"
        return DIFFERENT, "상품이 다름 — 같은 사업자의 다른 계정"
    rows = reg.account_rows(old)
    same_pw = bool(rows) and str(rows[0].acct.get("비밀번호", "")).strip() ==         str(snap.accounts[new].fields.get("비밀번호", "")).strip() != ""
    if same_pw and SequenceMatcher(None, old.lower(), new.lower()).ratio() >= 0.75:
        return SAME, "비밀번호 같고 아이디 비슷(오타 수정)"
    return DIFFERENT, "같은 계정이라는 근거 부족 — 같은 사업자의 다른 계정으로 처리"
