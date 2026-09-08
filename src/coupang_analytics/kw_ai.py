"""AI 기반 키워드 앵커 추출 + 관련성·쇼핑성 판정 (OpenAI ChatGPT).

방법론(메모리 keyword-methodology-ai-anchor):
- `analyze_product(title)` — 제목에서 **①용도 ②핵심 상품유형(core, 한 단어) ③핵심 앵커**를 함께 뽑는다.
  제목이 잘렸어도 용도로 본질을 파악해 core·앵커를 복원. 이 앵커에서만 네이버 연관어를 확장.
- `judge_keywords(title, candidates, use, core)` — 후보를 **핵심/연관/탈락**으로 분류해 {키워드:티어} 반환.
  형제 상품군(화로테이블에 '바베큐그릴')·거대 일반어('캠핑용품')·용도무관·정보성·타사 브랜드는 탈락.
- `recommend_title(...)` — **쿠팡 공식 상품명 기준**(옵션 분리·키워드 나열 금지·판촉어 금지)으로 권고 제목.

AI 없이는 키워드 도출이 불가능하다(토큰 폴백 폐지). 키가 없거나 호출·파싱이 실패하면
`KeywordAIError`를 올려 **상위에서 사유를 출력하고 중단**한다(조용한 폴백·None 금지).

공식 openai SDK 사용. API 키는 OPENAI_API_KEY 환경변수 또는 인자로 전달.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

from . import config


class KeywordAIError(RuntimeError):
    """AI 키워드 단계 실패(키 미설정·호출 실패·응답 파싱 실패). 폴백 없이 상위에서 중단."""


_ANALYZE_SYSTEM = (
    "당신은 쿠팡·네이버 쇼핑 검색 키워드 전문가입니다. 상품 제목을 보고 ①이 상품의 실제 용도를 한 문장으로 "
    "정의하고 ②이 상품을 찾는 한국 소비자가 검색창에 실제로 칠 '핵심 앵커 키워드'를 뽑습니다. "
    "앵커는 상품의 종류·용도·핵심 속성을 나타내는 본질 명사이며, 소비자 상황·필요를 담은 검색어도 포함할 수 "
    "있습니다. 브랜드명, 마케팅 수식어(프리미엄·리얼 등), 수량/단위(30포·48cm 등)는 앵커가 아닙니다."
)


def _analyze_prompt(title: str, n: int) -> str:
    return (
        f"상품 제목: {title}\n\n"
        "다음을 JSON 객체로만 답하세요.\n"
        '{"use":"용도 한 문장","core":"대표 상품유형 한 단어","identities":["정체성1","정체성2"],"anchors":["앵커1"]}\n'
        "- **core** = 이 상품의 대표 정체 **한 단어**(예: '화로테이블').\n"
        "- **identities** = 이 상품이 '바로 그것'이라 할 수 있는 **정체성(상품유형)들** — 고객이 그 단어로 검색하면\n"
        "  이 상품을 기대할 것들(예 이 상품은 화로테이블이자 바베큐테이블·숯불테이블·그릴테이블이기도 함).\n"
        "  단 **구성부품·다른 형태는 제외**(바베큐'그릴'·화로'대'(스탠드)는 identities 아님).\n"
        f"- anchors 는 최대 {n}개, identities 와 그 핵심 세부(네이버 확장용 씨앗).\n"
        "- 제목이 잘렸거나 애매해도 use 로 본질 파악. 브랜드·수식어·수량·거대 일반어('캠핑용품') 제외\n"
        '- 예: {"use":"야외에서 둘러앉아 고기 굽는 원형 화로 테이블","core":"화로테이블",'
        '"identities":["화로테이블","바베큐테이블","숯불테이블","그릴테이블"],"anchors":["화로테이블","바베큐테이블","불멍테이블"]}'
    )


_GEN_SYSTEM = (
    "당신은 쿠팡·네이버 쇼핑에서 고객이 실제로 검색창에 치는 '고객 검색어'를 만드는 전문가입니다. "
    "핵심 상품유형(core)과 용도를 보고, 이 상품을 사려는 고객이 칠 법한 **구체적 검색어(세부/롱테일)** 를 "
    "조합으로 폭넓게 만듭니다: 핵심 × 형태(원형·접이식·좌식) × 소재/방식(숯불·그릴·화로대) × 장소(캠핑·야외·펜션) "
    "× 용도(고기구이·바베큐·불멍) 등. 네이버가 연관어로 잘 안 주는 조합형까지 적극 생성합니다. "
    "단, 형제 상품군(화로테이블에 순수 '바베큐그릴')·거대 일반어('캠핑용품')·타사 브랜드·판촉어는 넣지 않습니다."
)


def _gen_prompt(title: str, use: str, identities: list[str], n: int) -> str:
    ids = ", ".join(identities)
    return (
        f"상품 제목: {title}\n이 상품의 정체성(identities): {ids}\n용도: {use}\n\n"
        f"이 상품을 사려는 고객이 검색할 법한 구체적 검색어를 최대 {n}개 생성하세요.\n"
        "- **각 정체성(그 자체)** 과, 거기에 형태·소재·방식·장소·용도를 붙인 조합형을 폭넓게\n"
        "  (예 화로테이블·바베큐테이블·숯불테이블·그릴테이블 + 캠핑○○·야외○○·고기굽는테이블·불멍테이블 등)\n"
        "- 실제 사람이 칠 자연스러운 검색어(띄어쓰기 없는 붙임말 위주), 구매의도 있는 것\n"
        "- 제목에 없는 물리적 형태(접이식·좌식 등)는 함부로 붙이지 말 것(있는 속성만)\n"
        "- 형제 상품군·구성부품(바베큐그릴·화로대 스탠드)·거대 일반어·타사 브랜드·판촉어 제외\n"
        '- 반드시 JSON 배열(문자열)로만. 예: ["화로테이블","바베큐테이블","캠핑화로테이블","숯불테이블","그릴테이블"]'
    )


def generate_keywords(title: str, use: str, identities: list[str], api_key: str | None = None,
                      model: str | None = None, n: int | None = None) -> list[str]:
    """정체성(identities)·용도 기반으로 고객 검색어를 조합 생성(네이버 연관에 없는 롱테일까지).

    생성만 하고 검색량 검증은 호출부가 네이버로 한다(0/극소량은 거기서 제외). 실패 시 KeywordAIError.
    """
    n = n or config.KW_GEN_N
    client = _client(api_key)
    text = _ask(client, model or config.KW_AI_MODEL, _GEN_SYSTEM,
                _gen_prompt(title, use, identities or [], n), max_tokens=2048)
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        raise KeywordAIError(f"AI 키워드 생성 응답에서 배열을 찾지 못함: {text[:120]!r}")
    try:
        arr = json.loads(m.group(0))
    except ValueError as exc:
        raise KeywordAIError(f"AI 키워드 생성 JSON 파싱 실패: {exc}") from exc
    out: list[str] = []
    for k in arr:
        s = str(k).strip()
        if s and s not in out:
            out.append(s)
    return out[:n]


_JUDGE_SYSTEM = (
    "당신은 쿠팡·네이버 쇼핑 검색 키워드 심사자입니다. 상품(핵심 상품유형·용도)과 네이버 연관 키워드 후보가 "
    "주어지면, 각 후보를 **핵심 / 연관 / 탈락** 3분류합니다. "
    "핵심 = 이 검색을 한 고객이 **이 상품의 정체성(identities) 중 하나**를 기대하는 키워드. "
    "연관 = 관련은 있으나 정확히 이 상품은 아닌 것(같은 상황·상위 용도, **다른 형태**). "
    "형태가 다르면 연관(예: 정체성이 '화로테이블'류면 받침대/스탠드형 '화로대'류는 핵심 아님·연관). "
    "탈락 = ①형제/다른 상품군(화로테이블에 '바베큐그릴'·'전기그릴') ②거대 일반 카테고리어('캠핑용품'·'주방용품') "
    "③용도 무관·정보성(효능·뜻 등) ④**브랜드가 붙은 키워드**(제목의 자사 브랜드가 아니면, 예 '프로스펙스안전화'·"
    "'몽크로스안전화' — 남의 브랜드엔 우리 상품이 노출 안 됨). 반드시 구매의도(쇼핑성)가 있어야 핵심/연관."
)


def _judge_prompt(title: str, use: str, core: str, identities: list[str], candidates: list[str]) -> str:
    ids = ", ".join(identities) if identities else (core or "(미상)")
    return (
        f"상품 제목: {title}\n"
        f"이 상품의 정체성(identities): {ids}\n"
        f"상품 용도: {use or '(미상)'}\n\n"
        f"후보 키워드: {json.dumps(candidates, ensure_ascii=False)}\n\n"
        "각 후보를 핵심/연관/탈락으로 분류해, **핵심·연관만** JSON 객체로 답하세요.\n"
        '  예: {"화로테이블":"핵심","불멍테이블":"핵심","캠핑화로대":"연관"}\n'
        "- 반드시 주어진 후보 안에서만, 원문 그대로 키로 사용\n"
        "- 형제 상품군·거대 일반어·용도무관·정보성·타사 브랜드는 **탈락(객체에서 제외)**\n"
        "- 핵심/연관이 하나도 없으면 빈 객체 {}. 반드시 JSON 객체로만 답하세요."
    )


def _client(api_key: str | None) -> OpenAI:
    try:
        return OpenAI(api_key=api_key) if api_key else OpenAI()
    except Exception as exc:   # 키 미설정 등
        raise KeywordAIError(f"OpenAI 클라이언트 생성 실패: {exc}") from exc


def _ask(client: OpenAI, model: str, system: str, user: str, max_tokens: int = 1024,
         temperature: float = 0.0) -> str:
    try:
        resp = client.chat.completions.create(
            model=model, max_tokens=max_tokens, temperature=temperature,  # 0=결정적(재현성)
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}])
    except Exception as exc:
        raise KeywordAIError(f"OpenAI 호출 실패: {exc}") from exc
    choice = resp.choices[0]
    if choice.finish_reason == "length":   # 잘린 응답은 JSON이 깨지므로 명시적으로 실패
        raise KeywordAIError(f"AI 응답이 토큰 한도로 잘림(max_tokens={max_tokens}) — 배치 크기/한도 조정 필요")
    return choice.message.content or ""


def _json_object(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise KeywordAIError(f"AI 응답에서 JSON 객체를 찾지 못함: {text[:120]!r}")
    try:
        return json.loads(m.group(0))
    except ValueError as exc:
        raise KeywordAIError(f"AI 응답 JSON 파싱 실패: {exc}") from exc


def analyze_product(title: str, api_key: str | None = None, model: str | None = None,
                    n: int | None = None) -> tuple[str, str, list[str], list[str]]:
    """상품 제목 → (용도, 대표 core, 정체성 목록 identities, 앵커 목록). 앵커 없으면 KeywordAIError.

    identities = 이 상품이 '바로 그것'인 상품유형들(화로테이블=바베큐테이블=숯불테이블=그릴테이블).
    이 중 어느 것으로 검색해도 이 상품을 기대하므로 판정에서 핵심 기준이 된다. core 는 대표(=head).
    """
    n = n or config.KW_AI_ANCHOR_N
    client = _client(api_key)
    text = _ask(client, model or config.KW_AI_MODEL, _ANALYZE_SYSTEM, _analyze_prompt(title, n))
    obj = _json_object(text)
    use = str(obj.get("use", "")).strip()
    core = str(obj.get("core", "")).strip()
    identities = [str(a).strip() for a in obj.get("identities", []) if str(a).strip()]
    if core and core not in identities:
        identities = [core] + identities
    if not core and identities:
        core = identities[0]
    anchors = [str(a).strip() for a in obj.get("anchors", []) if str(a).strip()]
    if not anchors:
        raise KeywordAIError(f"AI가 제목에서 앵커를 추출하지 못함: {title!r}")
    for idv in reversed(identities):          # 정체성도 확장 씨앗에 포함
        if idv not in anchors:
            anchors = [idv] + anchors
    seen: list[str] = []                      # 순서 유지 중복 제거
    for a in anchors:
        if a not in seen:
            seen.append(a)
    return use, core, identities, seen[:max(n, len(identities))]


_TITLE_SYSTEM = (
    "당신은 쿠팡 상품명(등록명) 작성 전문가입니다. **쿠팡 공식 상품명 등록 가이드**에 맞춰 상품명을 다시 씁니다. "
    "쿠팡 가이드(반드시 준수): "
    "①표준 구성 순서 = **[브랜드/제조사] + [제품명] + [상품유형(대표 핵심 키워드)] + [핵심 속성/소재/형태]**. "
    "②**브랜드 규칙**: 현재 제목 맨 앞이 브랜드/제조사(자사)면 **그대로 맨 앞에 유지**한다(임의로 빼지 말 것). "
    "브랜드가 없으면 상품유형부터 시작. ③옵션(색상·사이즈·수량·용량)은 상품명에 넣지 않는다(옵션으로 분리). "
    "④**키워드 나열식(스팸) 절대 금지**, 같은 단어 반복 금지 — 사람이 읽는 자연스러운 상품명 한 줄. "
    "⑤판촉·과장 문구 금지(무료배송·최저가·1+1·사은품·정품·최고·인기·이벤트), 특수문자·이모지·불필요한 공백 금지. "
    "⑥타사 브랜드·상표명 금지(상표권). ⑦대표(수요 큰) 핵심 키워드를 상품유형 자리에 자연스럽게 녹인다. "
    "⑧100자 이내(간결할수록 좋음)."
)


def recommend_title(current_title: str, keywords: list[str], brand: str = "",
                    api_key: str | None = None, model: str | None = None) -> str:
    """현재 제목 + 추적 키워드(수요 높은 순) → **쿠팡 상품명 가이드** 기준 권고 상품명 1개. 실패 시 KeywordAIError.

    브랜드는 현재 제목에서 유지하고, 키워드를 욱여넣지 않고 대표 키워드를 상품유형으로 삼아 자연스럽게 만든다.
    """
    client = _client(api_key)
    user = (
        f"현재 노출제목(원문): {current_title}\n"
        f"브랜드/스토어(있으면): {brand or '(현재 제목에서 판단)'}\n"
        f"활용할 키워드(수요 높은 순): {json.dumps(keywords, ensure_ascii=False)}\n\n"
        "위 쿠팡 상품명 가이드를 지켜 상품명 1개만 제시하세요. 규칙 요약: **현재 제목의 브랜드(맨 앞)를 그대로 "
        "유지**, 키워드를 나열하지 말고 대표 키워드를 상품유형으로 자연스럽게, 옵션·판촉어·특수문자 제외. "
        "설명 없이 상품명 문자열만 한 줄로 답하세요."
    )
    text = _ask(client, model or config.KW_AI_MODEL, _TITLE_SYSTEM, user, max_tokens=256)
    return text.strip().strip('"').splitlines()[0].strip() if text.strip() else ""


def judge_keywords(title: str, candidates: list[str], api_key: str | None = None,
                   model: str | None = None, use: str = "", core: str = "",
                   identities: list[str] | None = None) -> dict[str, str]:
    """네이버 연관 후보를 핵심/연관/탈락 판정 → **{키워드: '핵심'|'연관'}**(입력 순서 보존, 탈락 제외).

    후보가 많으면 배치로 나눠 판정한다. AI가 후보 밖 키워드를 지어내면 무시한다.
    identities(이 상품의 여러 정체성)·use(용도)를 기준으로 형제 상품군·거대 일반어를 걸러 밀착도를 높인다.
    """
    if not candidates:
        return {}
    identities = identities or ([core] if core else [])
    client = _client(api_key)
    model = model or config.KW_AI_MODEL
    batches = [candidates[i:i + config.KW_JUDGE_BATCH]
               for i in range(0, len(candidates), config.KW_JUDGE_BATCH)]

    def _judge_batch(batch: list[str]) -> tuple[list[str], dict]:
        text = _ask(client, model, _JUDGE_SYSTEM, _judge_prompt(title, use, core, identities, batch),
                    max_tokens=4096)
        return batch, _json_object(text)

    # 판정은 출력토큰 바운드라 모델 교체론 안 빨라짐 → **배치를 동시 실행**(gpt-4o 유지, 품질 무손실).
    kept: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(4, len(batches))) as ex:
        for batch, picked in ex.map(_judge_batch, batches):   # 배치 순서 보존
            for k in batch:                                   # 후보 밖 응답은 배제, 원래 순서 유지
                tier = str(picked.get(k, "")).strip()
                if tier in ("핵심", "연관"):
                    kept[k] = tier
    return kept


_SELECT_SYSTEM = (
    "당신은 쿠팡 판매 키워드 전략가입니다. 한 상품에 대해 수집된 '후보 키워드'와 각 지표"
    "(월검색량·모바일비중·월클릭수·네이버 경쟁정도·관련도·**키워드점수(100점)·등급·쿠팡 실노출 순위**)를 "
    "종합 분석해, 이 상품을 쿠팡에서 노출·판매로 이어갈 **추적 키워드 N개**를 우선순위대로 확정합니다. "
    "선정 원칙: ①상품 정체성에 밀착(핵심>연관) ②실제 구매의도가 큰 구체 검색어 우선(거대 일반어는 검색량이 커도 "
    "배제) ③**쿠팡 실노출 순위가 이미 좋은(상위) 키워드는 곧 매출로 이어지므로 우대** ④종합 점수·등급이 높은 쪽 "
    "우선. 첫 번째는 이 상품의 대표 상품유형(core)을 반드시 포함합니다."
)


def _select_prompt(title: str, use: str, core: str, identities: list[str],
                   items: list[dict], n: int) -> str:
    ids = ", ".join(identities) if identities else (core or "(미상)")
    return (
        f"상품 제목: {title}\n"
        f"정체성(identities): {ids}\n용도: {use or '(미상)'}\n대표유형(core): {core or '(미상)'}\n\n"
        f"후보 키워드(지표 포함 — score=키워드점수100, grade=등급, exposure=쿠팡 오가닉 최상위순위/미노출):\n"
        f"{json.dumps(items, ensure_ascii=False)}\n\n"
        f"위 후보 중 이 상품 추적에 가장 가치 있는 {n}개를 우선순위대로 골라 JSON 배열(키워드 문자열)로만 답하세요.\n"
        "- 첫 항목은 대표유형(core) 키워드\n"
        "- 반드시 주어진 후보 안에서만, 원문 그대로\n"
        "- 거대 일반어·형제 상품군은 검색량이 커도 제외, 밀착도·구매의도 우선\n"
        "- 점수·등급·쿠팡 실노출을 종합하되, 노출이 이미 좋은(상위 순위) 밀착 키워드를 특히 우대\n"
        '- 예: ["화로테이블","캠핑화로테이블","숯불테이블","바베큐테이블","불멍테이블"]'
    )


def select_keywords(title: str, candidates_info: list[dict], use: str = "", core: str = "",
                    identities: list[str] | None = None, n: int | None = None,
                    api_key: str | None = None, model: str | None = None) -> list[str]:
    """후보군+지표를 AI가 종합 분석해 최종 추적 키워드 n개를 **우선순위대로** 확정.

    candidates_info = [{"keyword","volume","mobile","clicks","comp","relevance"}, ...].
    AI가 후보 밖 키워드를 지어내면 무시한다. 실패 시 KeywordAIError.
    """
    n = n or config.KW_TRACK_N
    if not candidates_info:
        return []
    identities = identities or ([core] if core else [])
    client = _client(api_key)
    text = _ask(client, model or config.KW_AI_MODEL, _SELECT_SYSTEM,
                _select_prompt(title, use, core, identities, candidates_info, n), max_tokens=1024)
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        raise KeywordAIError(f"AI 키워드 선정 응답에서 배열을 찾지 못함: {text[:120]!r}")
    try:
        arr = json.loads(m.group(0))
    except ValueError as exc:
        raise KeywordAIError(f"AI 키워드 선정 JSON 파싱 실패: {exc}") from exc
    valid = {c["keyword"] for c in candidates_info}
    out: list[str] = []
    for k in arr:                                        # 후보 밖 응답 배제, 우선순위(순서) 보존
        s = str(k).strip()
        if s in valid and s not in out:
            out.append(s)
    return out[:n]
