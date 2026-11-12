"""체험단 비용(관리대장 두 번째 시트 '체험단') — 사업자별 고객(계약자) 부담·디프픽(우리) 부담 구분 · 정산금액에서 차감하지 않고 표시만.

소유자 2026-10-19: "판매가 부담·리뷰/택배 부담 — 고객 = 계약자, 디프픽 = 우리 부담 · 정산 시 구분해 정산 내역으로 포함" ·
답 '둘 다 표시만'·'완료만 반영(빈칸 = 진행 전 따로 표시)'·'정산 대상 아닌 상호 = 별도 목록'.
부담 칸이 '고객10 디프픽20' 처럼 나뉘면 그 줄 금액을 건수 비율로 나눔(끝전은 디프픽 몫).
읽기: 관리대장 구글시트(서비스계정·읽기만 — 비밀번호가 있는 첫 시트는 열지 않음) → 출력 폴더 `체험단_명단.json` 사본.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

SHEET = "체험단"
BURDEN_ME, BURDEN_CUST = "디프픽", "고객"
_NORM = re.compile(r"\(주\)|㈜|주식회사|[\s\-()·.,]")


def norm(s: str) -> str:
    return _NORM.sub("", str(s or ""))


def _int(v) -> int:
    t = str(v or "").replace(",", "").strip()
    return int(t) if re.fullmatch(r"-?\d+", t) else 0


def load(out: Path, input_url: str | None, supplement: Path) -> list[dict]:
    """체험단 줄 목록 = 관리대장 시트(출력 폴더 사본이 있으면 그것) + 보충 목록(supplement = 입력 폴더 `체험단_보충.json` —
    관리대장 시트에 없는 체험단·견적서·이체 확인증 근거 · '출처'=보충)."""
    return _sheet(out, input_url) + [{**r, "출처": "보충(견적서·이체)"} for r in
                                     (json.loads(supplement.read_text(encoding="utf-8")) if supplement.is_file() else [])]


def _sheet(out: Path, input_url: str | None) -> list[dict]:
    cache = out / "체험단_명단.json"
    if cache.is_file():
        return json.loads(cache.read_text(encoding="utf-8"))
    if not input_url:
        return []
    from coupang_analytics.gsheet_api import GSheetClient
    rows = GSheetClient(input_url).read_values(SHEET)
    hi = next(i for i, r in enumerate(rows) if any("판매가 부담" in str(x) for x in r))
    hdr = rows[hi]
    data = [dict(zip(hdr, r + [""] * (len(hdr) - len(r)))) for r in rows[hi + 1:] if len(r) > 3 and str(r[2]).strip()]
    cache.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def _split(burden: str, amount: int, count: int) -> dict:
    """부담 칸 → {고객: 금액, 디프픽: 금액}. '고객10 디프픽20' = 건수 비율(끝전 디프픽)."""
    b = str(burden or "").strip()
    if b in (BURDEN_CUST, BURDEN_ME):
        return {b: amount}
    m = dict((k, int(n)) for k, n in re.findall(r"(고객|디프픽)\s*(\d+)", b))
    total = sum(m.values()) or count or 1
    if m:
        cust = round(amount * m.get(BURDEN_CUST, 0) / total)
        return {BURDEN_CUST: cust, BURDEN_ME: amount - cust}
    return {"부담 미기재": amount}


def assign(rows: list[dict], businesses: list[tuple[str, str]]) -> tuple[dict, list]:
    """businesses = [(사업자, 대표자)] → ({사업자: [줄…]}, 정산 대상 아닌 줄). 상호(정규화) 일치 → 대표자 이름 일치 순."""
    by_biz = {norm(b): b for b, _ in businesses}
    by_rep: dict = defaultdict(set)
    for b, rep in businesses:
        if rep:
            by_rep[rep].add(b)
    out: dict = defaultdict(list)
    other = []
    for r in rows:
        biz = by_biz.get(norm(r.get("상호")))
        if not biz:
            cands = by_rep.get(str(r.get("고객") or "").strip(), set())
            biz = next(iter(cands)) if len(cands) == 1 else None
        (out[biz].append(r) if biz else other.append(r))
    return dict(out), other


def lines(rows: list[dict]) -> list[dict]:
    """정산서 줄 — 요청일·제품·건수·판매가 금액(부담별)·리뷰/택배 금액(부담별)·진행 여부·완료 여부."""
    out = []
    for r in rows:
        cnt = _int(r.get("건수"))
        sale = _split(r.get("판매가 부담"), _int(r.get("판매가 금액")), cnt)
        rev = _split(r.get("리뷰/택배 부담"), _int(r.get("리뷰/택배 금액")), cnt)
        status = str(r.get("진행 여부") or "").strip()
        out.append({"요청일": r.get("요청일"), "상호": r.get("상호"), "고객": r.get("고객"), "제품명": r.get("제품명"),
                    "건수": cnt, "판매가": _int(r.get("판매가")), "판매가 부담": r.get("판매가 부담"),
                    "판매가 금액": _int(r.get("판매가 금액")), "리뷰/택배 부담": r.get("리뷰/택배 부담"),
                    "리뷰/택배 금액": _int(r.get("리뷰/택배 금액")),
                    "고객 부담": sale.get(BURDEN_CUST, 0) + rev.get(BURDEN_CUST, 0),
                    "우리 부담": sale.get(BURDEN_ME, 0) + rev.get(BURDEN_ME, 0),
                    "부담 미기재": sale.get("부담 미기재", 0) + rev.get("부담 미기재", 0),
                    "진행 여부": status or "진행 전", "완료": "완료" in status,
                    "비고": str(r.get("비고") or ""), "출처": r.get("출처", "관리대장 체험단 시트")})
    return out


def totals(ls: list[dict]) -> Counter:
    c: Counter = Counter()
    for x in ls:
        k = "완료" if x["완료"] else "진행 전"
        c[f"{k} 고객 부담"] += x["고객 부담"]
        c[f"{k} 우리 부담"] += x["우리 부담"]
        c[f"{k} 부담 미기재"] += x["부담 미기재"]
        c[f"{k} 줄"] += 1
    return c
