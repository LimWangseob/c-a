"""AI 기반 키워드 앵커 추출 + 관련성·쇼핑성 판정 (OpenAI ChatGPT).

방법론(메모리 keyword-methodology-ai-anchor):
- `analyze_product(title)` — 제목에서 **①용도(use) ②대표 상품유형(core, 한 단어) ③정체성(identities)
  ④실제 속성(attributes) ⑤앵커(anchors)**를 함께 뽑는다. 정체성은 이 상품이 '바로 그것'이라 부를 수 있는
  상품유형 동의어들(화로테이블=바베큐테이블=숯불테이블=그릴테이블)로, 판정/생성/선정의 핵심 기준이 된다.
- `generate_keywords(...)` — 정체성·속성·용도로 고객 검색어 조합(롱테일)을 생성.
- `judge_keywords(...)` — 후보를 **CORE/RELATED/DROP** 판정 + 적합도(match) → {키워드:(티어,match)} 반환.
- `select_keywords(...)` — 지표 종합해 추적 키워드 N개를 **역할(REP/SALES/GROWTH/DEFENSE)**과 함께 확정.
- `recommend_title(...)` — **쿠팡 공식 상품명 기준**(옵션 분리·나열 금지·판촉어 금지)으로 권고 제목.

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


# ── ① 분석 ────────────────────────────────────────────────────────
_ANALYZE_SYSTEM = (
    "상품 제목을 분석해 검색 기준이 되는 상품 정체성을 추출한다. "
    "core=이 상품 자체를 가리키는 대표 상품유형(성분/대상+종류가 결합된 구매 검색어). "
    "**형태·단위어 단독 금지**: 환·정·캡슐·진액·분말·세트·팩·포 같은 형태/포장 단어는 그 자체가 상품유형이 아니므로 "
    "반드시 핵심 대상과 결합한다(예 '맥문동환'·'홍삼정' — '환'·'정' 단독 금지). use=실제 사용목적(한 문장). "
    "identities=이 상품을 '바로 그것'이라 부를 수 있는 상품유형 동의어들(고객이 그 단어로 검색하면 이 상품을 "
    "기대하는 것들 — 예 화로테이블=바베큐테이블=숯불테이블=그릴테이블). 단 **구성부품·다른 형태·형태단독어·"
    "거대 일반어는 제외**(화로테이블의 '바베큐그릴'·'화로대 스탠드', 맥문동환의 '환'·'건강환'·'건강식품'은 identities 아님). "
    "attributes=형태·재질·기능·장소 등 실제 속성(원형·접이식·숯불·캠핑). **핵심 성분/대상(core 구성어)·브랜드·"
    "수식어(프리미엄·리얼)·수량(30포·48cm)은 attributes가 아니다.** "
    "anchors=고객이 구매하려 검색할 핵심 명사형 키워드(네이버 연관확장 씨앗). "
    "브랜드·판촉어·수량/옵션·모델명은 제외하고, 없는 속성은 추측하지 않는다."
)


def _analyze_prompt(title: str, n: int) -> str:
    return (
        f"상품 제목: {title}\n\n"
        "아래 JSON 객체로만 답하세요.\n"
        '{"core":"","use":"","identities":[],"attributes":[],"anchors":[]}\n'
        "- core: 성분/대상+종류가 결합된 상품유형(형태·단위어 단독 금지 — '환'·'정'·'세트' 아님, '맥문동환' 형태).\n"
        "- identities: 정체성(동의어 상품유형)들. 형태단독어·거대 일반어('건강환'·'건강식품') 제외.\n"
        f"- anchors: 최대 {n}개(정체성과 그 핵심 세부).\n"
        "- attributes: 실제 속성만. 핵심 성분(=core 구성어)·수식어·수량은 넣지 말 것.\n"
        "- 없는 속성 추측 금지. 브랜드·수식어·수량·거대 일반어('캠핑용품') 제외.\n"
        '- 예1: {"core":"화로테이블","use":"야외에서 둘러앉아 고기 굽는 원형 화로 테이블",'
        '"identities":["화로테이블","바베큐테이블","숯불테이블","그릴테이블"],'
        '"attributes":["원형","숯불","캠핑","불멍"],"anchors":["화로테이블","바베큐테이블","불멍테이블"]}\n'
        '- 예2: {"core":"맥문동환","use":"건강 증진을 위해 섭취하는 볶은 맥문동 환",'
        '"identities":["맥문동환","볶은맥문동환"],'
        '"attributes":["볶은","환"],"anchors":["맥문동환","볶은맥문동","맥문동"]}'
    )


def analyze_product(title: str, api_key: str | None = None, model: str | None = None,
                    n: int | None = None) -> tuple[str, str, list[str], list[str], list[str]]:
    """상품 제목 → (용도, 대표 core, 정체성 identities, 속성 attributes, 앵커 anchors). 앵커 없으면 KeywordAIError.

    identities = 이 상품이 '바로 그것'인 상품유형들 → 판정/생성/선정의 핵심 기준. core = 대표(=head).
    attributes = 형태·재질·장소 등 실제 속성(조합생성 씨앗). 없는 속성은 추측하지 않는다.
    """
    n = n or config.KW_AI_ANCHOR_N
    client = _client(api_key)
    text = _ask(client, model or config.KW_AI_MODEL, _ANALYZE_SYSTEM, _analyze_prompt(title, n))
    obj = _json_object(text)
    use = str(obj.get("use", "")).strip()
    core = str(obj.get("core", "")).strip()
    identities = [str(a).strip() for a in obj.get("identities", []) if str(a).strip()]
    attributes = [str(a).strip() for a in obj.get("attributes", []) if str(a).strip()]
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
    return use, core, identities, attributes, seen[:max(n, len(identities))]


# ── ② 후보 생성 ───────────────────────────────────────────────────
_GEN_SYSTEM = (
    "core/use/identities/attributes를 이용해 실제 구매자가 검색할 키워드 후보를 생성한다. "
    "조합 기준: 상품유형 × 형태 × 재질/방식 × 장소 × 용도. "
    "포함: 각 정체성(그 자체), 대표 상품유형, 용도형·속성형·장소형, 구매의도 있는 롱테일. "
    "제외: 형제/다른 상품군, 거대 일반어, 타사 브랜드, 판촉·정보성 검색어, 없는 속성, "
    "의미가 같은 단순 어순변경(중복)."
)


def _gen_prompt(title: str, use: str, identities: list[str], attributes: list[str], n: int) -> str:
    ids = ", ".join(identities) or "(미상)"
    attrs = ", ".join(attributes) or "(없음)"
    return (
        f"상품 제목: {title}\n정체성(identities): {ids}\n속성(attributes): {attrs}\n용도: {use}\n\n"
        f"이 상품을 사려는 고객이 검색할 구체적 검색어를 최대 {n}개 생성하세요.\n"
        "- 실제 사람이 칠 자연스러운 검색어(띄어쓰기 없는 붙임말 위주), 구매의도 있는 것\n"
        "- 제목/속성에 없는 물리적 형태는 함부로 붙이지 말 것(있는 속성만)\n"
        "- 형제 상품군·구성부품·거대 일반어·타사 브랜드·판촉어·단순 어순변경 제외\n"
        '아래 JSON 객체로만: {"candidates":["화로테이블","캠핑화로테이블","숯불테이블"]}'
    )


def generate_keywords(title: str, use: str, identities: list[str], attributes: list[str] | None = None,
                      api_key: str | None = None, model: str | None = None,
                      n: int | None = None) -> list[str]:
    """정체성·속성·용도 기반으로 고객 검색어를 조합 생성(네이버 연관에 없는 롱테일까지).

    생성만 하고 검색량 검증은 호출부가 네이버로 한다(0/극소량은 거기서 제외). 실패 시 KeywordAIError.
    """
    n = n or config.KW_GEN_N
    client = _client(api_key)
    text = _ask(client, model or config.KW_AI_MODEL, _GEN_SYSTEM,
                _gen_prompt(title, use, identities or [], attributes or [], n), max_tokens=2048)
    obj = _json_object(text)
    arr = obj.get("candidates", [])
    if not isinstance(arr, list):
        raise KeywordAIError(f"AI 키워드 생성 응답 candidates가 배열이 아님: {text[:120]!r}")
    out: list[str] = []
    for k in arr:
        s = str(k).strip()
        if s and s not in out:
            out.append(s)
    return out[:n]


# ── ③ 판정 ────────────────────────────────────────────────────────
_JUDGE_SYSTEM = (
    "각 키워드를 현재 상품 기준으로 CORE/RELATED/DROP 판정한다. "
    "**대전제: 반드시 구매의도(쇼핑성)가 있어야 CORE/RELATED다.** 사람이 이 상품을 '사려고' 칠 검색어인지로 가른다. "
    "CORE=상품 자체를 찾는 구매검색어(이 상품의 정체성 중 하나를 기대하는 것). "
    "RELATED=관련 있으나 범위가 넓거나 일부 다른 상품을 포함(다른 형태 포함 — 예 정체성이 '화로테이블'류면 "
    "받침대/스탠드형 '화로대'류는 RELATED). "
    "DROP(반드시 탈락): ①**정보성·증상성 검색어** — 효능·효과·부작용·성분·뜻·유래·먹는법·복용법·"
    "'~에좋은음식'·'~에좋은'·'~증상'·'~통증' 등 사려는 게 아니라 알아보려는 검색어(예 맥문동효능·폐에좋은음식·"
    "위에좋은음식은 상품이 아니라 정보 검색 → DROP). ②다른 상품군 ③거대 일반 카테고리어('캠핑용품'·'건강식품') "
    "④**형태·단위어 단독**('환'·'정'·'세트') ⑤**타사 브랜드**(제목의 자사 브랜드가 아니면) ⑥없는 속성. "
    "match(0~100)=이 상품과의 적합도. 검색량은 고려하지 말고 상품 적합성·구매의도만 판단한다."
)


def _judge_prompt(title: str, use: str, core: str, identities: list[str], candidates: list[str]) -> str:
    ids = ", ".join(identities) if identities else (core or "(미상)")
    return (
        f"상품 제목: {title}\n정체성(identities): {ids}\n용도: {use or '(미상)'}\n\n"
        f"후보 키워드: {json.dumps(candidates, ensure_ascii=False)}\n\n"
        "각 후보를 CORE/RELATED/DROP 판정해 **CORE·RELATED만** 아래 JSON으로 답하세요(DROP은 제외).\n"
        '{"judged":[{"k":"화로테이블","label":"CORE","match":95},{"k":"캠핑화로대","label":"RELATED","match":60}]}\n'
        "- 반드시 주어진 후보 안에서만, 원문 그대로 k로 사용\n"
        "- **구매의도 없는 정보성·증상성 검색어(효능·~에좋은음식·~증상 등)와 형태단독어('환'·'정')는 DROP(제외)**\n"
        "- CORE/RELATED가 하나도 없으면 {\"judged\":[]}. 반드시 JSON 객체로만."
    )


_LABEL_TIER = {"CORE": "핵심", "RELATED": "연관"}


def judge_keywords(title: str, candidates: list[str], api_key: str | None = None,
                   model: str | None = None, use: str = "", core: str = "",
                   identities: list[str] | None = None) -> dict[str, tuple[str, float]]:
    """후보를 CORE/RELATED/DROP 판정 → **{키워드: (티어, match)}**(입력 순서 보존, DROP 제외).

    티어 = '핵심'|'연관'(CORE/RELATED 매핑). match = 0~1(상품 적합도, 티어 내 미세 조정용).
    후보가 많으면 배치로 나눠 판정한다. AI가 후보 밖 키워드를 지어내면 무시한다.
    identities(정체성)·use(용도)를 기준으로 형제 상품군·거대 일반어를 걸러 밀착도를 높인다.
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
        obj = _json_object(text)
        picked: dict[str, tuple[str, float]] = {}
        for row in obj.get("judged", []):
            if not isinstance(row, dict):
                continue
            k = str(row.get("k", "")).strip()
            tier = _LABEL_TIER.get(str(row.get("label", "")).strip().upper())
            if not k or not tier:
                continue
            try:
                match = max(0.0, min(float(row.get("match", 0)) / 100.0, 1.0))
            except (TypeError, ValueError):
                match = 0.0
            picked[k] = (tier, match)
        return batch, picked

    # 판정은 출력토큰 바운드라 모델 교체론 안 빨라짐 → **배치를 동시 실행**(품질 무손실).
    kept: dict[str, tuple[str, float]] = {}
    with ThreadPoolExecutor(max_workers=min(4, len(batches))) as ex:
        for batch, picked in ex.map(_judge_batch, batches):   # 배치 순서 보존
            for k in batch:                                   # 후보 밖 응답은 배제, 원래 순서 유지
                if k in picked:
                    kept[k] = picked[k]
    return kept


# ── ④ 최종 선정 ───────────────────────────────────────────────────
_SELECT_SYSTEM = (
    "상품 적합성과 검색 데이터를 이용해 추적 키워드 N개를 우선순위대로 선정한다. "
    "우선순위: 상품일치도 > 검색수요 > 구매의도 > 쿠팡순위 > 성장가능성 > 경쟁도/점수. "
    "역할: REP=대표 핵심어, SALES=검색수요·구매가능성 높은 키워드, "
    "GROWTH=검색수요는 있으나 현재 순위가 낮은 성장 키워드, DEFENSE=현재 순위가 좋아 유지·감시할 키워드. "
    "첫 번째는 대표 core 키워드로 한다. 검색의도가 같은 키워드는 중복 선정하지 않는다. "
    "**정보성·증상성 검색어(효능·~에좋은음식·~증상 등)와 형태단독어('환'·'정')는 검색량이 아무리 커도 선정 금지** "
    "— 사람이 상품을 사려고 치는 검색어만 고른다. 현재 순위가 낮아도 검색수요가 크면 GROWTH로 적극 검토한다."
)


def _select_prompt(title: str, use: str, core: str, identities: list[str],
                   items: list[dict], n: int) -> str:
    ids = ", ".join(identities) if identities else (core or "(미상)")
    return (
        f"상품 제목: {title}\n정체성(identities): {ids}\n대표유형(core): {core or '(미상)'}\n용도: {use or '(미상)'}\n\n"
        f"후보 키워드(지표 포함 — score=키워드점수100, grade=등급, exposure=쿠팡 오가닉 최상위순위/미노출):\n"
        f"{json.dumps(items, ensure_ascii=False)}\n\n"
        f"위 후보 중 이 상품 추적에 가장 가치 있는 {n}개를 우선순위대로 골라 아래 JSON으로만 답하세요.\n"
        '{"selected":[{"k":"화로테이블","role":"REP","priority":1},{"k":"숯불테이블","role":"SALES","priority":2}]}\n'
        "- 첫 항목은 대표유형(core) 키워드(role=REP)\n"
        "- 반드시 주어진 후보 안에서만, 원문 그대로 k로 사용\n"
        "- 거대 일반어·형제 상품군은 검색량이 커도 제외, 밀착도·구매의도 우선\n"
        "- 검색의도 같은 키워드 중복 금지"
    )


def select_keywords(title: str, candidates_info: list[dict], use: str = "", core: str = "",
                    identities: list[str] | None = None, n: int | None = None,
                    api_key: str | None = None, model: str | None = None) -> list[tuple[str, str]]:
    """후보군+지표를 AI가 종합 분석해 최종 추적 키워드 n개를 **역할과 함께 우선순위대로** 확정.

    반환: [(키워드, 역할)] — 역할 ∈ REP/SALES/GROWTH/DEFENSE. 첫 항목=core(REP).
    AI가 후보 밖 키워드를 지어내면 무시한다. 실패 시 KeywordAIError.
    """
    n = n or config.KW_TRACK_N
    if not candidates_info:
        return []
    identities = identities or ([core] if core else [])
    client = _client(api_key)
    text = _ask(client, model or config.KW_AI_MODEL, _SELECT_SYSTEM,
                _select_prompt(title, use, core, identities, candidates_info, n), max_tokens=1024)
    obj = _json_object(text)
    rows = obj.get("selected", [])
    if not isinstance(rows, list):
        raise KeywordAIError(f"AI 키워드 선정 응답 selected가 배열이 아님: {text[:120]!r}")
    rows = sorted([r for r in rows if isinstance(r, dict)],
                  key=lambda r: r.get("priority", 999))
    valid = {c["keyword"] for c in candidates_info}
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for r in rows:                                       # 후보 밖 응답 배제, 우선순위(priority) 보존
        k = str(r.get("k", "")).strip()
        role = str(r.get("role", "")).strip().upper() or "SALES"
        if k in valid and k not in seen:
            out.append((k, role))
            seen.add(k)
    return out[:n]


# ── ⑤ 제목 처방 ───────────────────────────────────────────────────
_TITLE_SYSTEM = (
    "현재 상품정보와 선정 키워드로 쿠팡 상품명을 개선한다. 구성 = [브랜드] + [상품유형] + [중요 실제속성]. "
    "브랜드는 맨 앞에 유지(제목 맨 앞이 자사 브랜드면 그대로, 없으면 상품유형부터). "
    "대표키워드는 자연스럽게 반영하되 동일 의미 키워드 반복 금지, 키워드 나열식(스팸) 금지. "
    "옵션(색상·사이즈·수량·용량)·판촉/과장어(무료배송·최저가·1+1·사은품·정품·최고)·특수문자·이모지·"
    "타사 브랜드·없는 속성 제외. 100자 이내(간결할수록 좋음)."
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
        "위 규칙을 지켜 상품명 1개를 제시하세요. 아래 JSON 객체로만 답하세요.\n"
        '{"title":"권고 상품명","primary_keyword":"대표 키워드"}'
    )
    text = _ask(client, model or config.KW_AI_MODEL, _TITLE_SYSTEM, user, max_tokens=256)
    obj = _json_object(text)
    return str(obj.get("title", "")).strip()


# ── 공통 헬퍼 ─────────────────────────────────────────────────────
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
