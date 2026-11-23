"""다시받을목록 자동 재받기(D-339 · T-82 · T-90) — 접속 없음. 받기 의심 줄 중 '다시 받기' 줄을 **다음 실행의 평소 받기 흐름**이
다시 받도록 표시만 바꾼다(한 회차 개수 상한·차단 간격·로그인 규칙 = 그 흐름 그대로 · D-321 부분 대체).

종류별 길(근거 파일 = 받기 의심 줄의 '근거 파일'):
- 월자료(라이브정산 등 · 검증자료/월자료/{계정}/{종류}_{YYYYMM}.json) → 그 폴더 `_받은기록.json` 에서 그 달만 뺌 → collect_docs 가
  회차 예산(BUDGET_MONTHS)으로 다시 받음 · 옛 파일 = `_Run.save` 의 수집일별 보관(D-335). 받은 기록에 올라 영원히 안 받던 빈 파일 대상.
- 광고정산 subtotals 없음 → `광고/_광고_다시받기.json`({계정: [YYYYMM]})에 추가 → settlement_ads.collect 가 옛 파일을 보관_옛질의/ 로
  옮기고 다시(계정당 하루 MAX_MONTHS). 2025 달 = 정산 대상 아님(D-328) → 제외·받지 않음(AD.SETTLE_FROM · D-389).
- 비용 리포트(로켓그로스) → 요청 기록(`_요청기록.json`) 그 줄을 '요청예정'·시도 0 → 다음 정기 단계가 계정당 요청 상한 안에서 요청·받기.
- 밀크런(읽기 실패·머리글 칸 없음) → 파일을 `광고/보관_다시받기/` 로 옮김(삭제 없음) → 다음 광고 단계가 그 달을 없는 달로 보고 받음.
- 리뷰 이벤트 = 검증자료가 매일 다시 받음(collect_verify) → 할 일 없음.

같은 결과면 반복 안 함(D-339 · D-321 버린 대안의 무한 반복 우려): 표시할 때 근거 파일 지문(sha256)·수정 시각을
`자료출처/_다시받기기록.json` 에 남긴다. 다음 확인 때 ① 수정 시각 그대로(또는 옮겨서 없음) = 아직 안 받음 → 대기 ② 바뀌었는데 지문이
전에 본 것 = 같은 결과 → 그 줄 '확인 필요'·다시 받기 '아니오'(광고는 다시받기 목록에서도 뺌) ③ 새 지문 = 한 번 더(지문 추가).
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from . import daily_snapshot as DS
from . import settlement_ads as AD
from . import settlement_docs as DOC
from . import settlement_fetch_check as FC
from . import settlement_files as SF
from . import settlement_jobs as SJ

MEMO = "_다시받기기록.json"
JOBS = "_요청기록.json"              # settlement_store.JOBS 와 같은 이름(정산 기록 폴더 바로 아래)
MILK_KEEP = "보관_다시받기"           # 다시 받기 전 밀크런 파일을 옮기는 하위 폴더(광고 폴더 glob 에 안 걸림)
COUNTS = ("표시", "대기", "같은 결과", "대상 아님", "매일 받음", "길 없음")


def _key(r: dict) -> str:
    return "|".join(str(r[k]) for k in ("종류", "계정", "정산일", "기간", "항목"))


def _sig(p: Path) -> tuple[str, int]:
    return hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns


def _note(r: dict, why: str) -> None:
    """그 줄을 확인 필요로(다시받을목록에서 빠짐 · 받기의심.csv 엔 남음)."""
    r["판정"], r["다시 받기"], r["설명"] = FC.CHECK, FC.NO, f"{r['설명']} · {why}"


def _write_json(p: Path, data, today: date) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    DS.keep_before_overwrite(p, today)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _mark_doc(r: dict, p: Path, today: date) -> bool:
    lp = p.parent / DOC.LEDGER
    led = json.loads(lp.read_text(encoding="utf-8")) if lp.exists() else {}
    (led.get(r["종류"]) or {}).pop(str(r["기간"]), None)
    _write_json(lp, led, today)
    return True


def _mark_ad(r: dict, p: Path, today: date) -> bool:
    rp = p.parent / AD.REFETCH
    want = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else {}
    want[r["계정"]] = sorted({*(want.get(r["계정"]) or []), str(r["기간"])})
    _write_json(rp, want, today)
    return True


def _unmark_ad(r: dict, p: Path, today: date) -> None:
    rp = p.parent / AD.REFETCH
    want = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else {}
    left = [ym for ym in want.get(r["계정"]) or [] if ym != str(r["기간"])]
    if left:
        want[r["계정"]] = left
    else:
        want.pop(r["계정"], None)
    _write_json(rp, want, today)


def _mark_cost(base: Path, r: dict) -> bool:
    jp = base / JOBS
    jobs = SJ.load_jobs(jp)
    ps, pe = str(r["기간"]).split("~")
    hit = [j for j in jobs if j.channel == "로켓그로스" and (j.period_start, j.period_end) == (ps, pe)
           and SF._token(j.account, "계정명") == r["계정"] and SF._token(j.report, "리포트") == r["항목"]]
    if not hit:
        return False
    for j in hit:
        if j.status != SJ.ST_REQUESTED:
            j.status, j.attempts, j.note = SJ.ST_PLANNED, 0, "받기 의심 — 자동 다시 받기(D-339)"
    SJ.save_jobs(jp, jobs)
    return True


def _mark_milk(p: Path, today: date) -> bool:
    d = p.parent / MILK_KEEP
    d.mkdir(exist_ok=True)
    dst, n = d / p.name, 1
    while dst.exists():
        dst = d / f"{p.stem}_{today}{f'_{n}' if n > 1 else ''}{p.suffix}"
        n += 1
    p.replace(dst)
    return True


def _mark(base: Path, r: dict, p: Path, today: date) -> bool:
    """종류별 다시 받기 표시 → 길이 있으면 True."""
    kind = r["종류"]
    if kind in DOC.KINDS:
        return _mark_doc(r, p, today)
    if kind == "광고정산":
        return _mark_ad(r, p, today)
    if kind == "비용 리포트":
        return _mark_cost(base, r)
    if kind == "밀크런":
        return _mark_milk(p, today)
    return False


def _one(base: Path, r: dict, memo: dict, today: date) -> str:
    """한 줄 처리 → COUNTS 중 하나."""
    if r["종류"] == "리뷰 이벤트":
        return "매일 받음"
    if r["종류"] == "광고정산" and str(r["기간"]) < AD.SETTLE_FROM:
        r["판정"], r["다시 받기"] = FC.EXCLUDED, FC.NO
        r["설명"] = f"{r['설명']} · 2025 달 — 정산 대상 아님(D-328) · 받지 않음(D-389)"
        return "대상 아님"
    p, rec = Path(r["근거 파일"]), memo.get(_key(r))
    if not p.exists():
        if rec:
            return "대기"                                  # 옮겨 둔 밀크런 = 아직 다시 안 받음
        _note(r, "근거 파일 없음 — 자동 다시 받기 못 함")
        return "길 없음"
    sha, mtime = _sig(p)
    if rec and mtime == rec["수정"]:
        return "대기"
    if rec and sha in rec["지문"]:
        if r["종류"] == "광고정산":
            _unmark_ad(r, p, today)
        _note(r, f"자동 다시 받기({rec['표시일']}) 뒤에도 같은 결과 — 확인 필요(D-339)")
        return "같은 결과"
    if not _mark(base, r, p, today):
        _note(r, "요청 기록에 그 줄 없음 — 자동 다시 받기 못 함" if r["종류"] == "비용 리포트" else "자동 다시 받을 길 없음")
        return "길 없음"
    memo[_key(r)] = {"지문": [*(rec or {}).get("지문", []), sha], "수정": mtime, "표시일": f"{today}"}
    return "표시"


def plan(base: Path, rows: list[dict], today: date) -> dict:
    """받기 의심 줄(scan 결과) 중 다시 받기 줄을 표시 · rows 제자리 갱신(같은 결과·길 없음 = 확인 필요) → 개수 {COUNTS}."""
    base = Path(base)
    mp = base / "자료출처" / MEMO
    memo = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
    out = dict.fromkeys(COUNTS, 0)
    for r in rows:
        if r["다시 받기"] != FC.NO:
            out[_one(base, r, memo, today)] += 1
    _write_json(mp, memo, today)
    return out


def summary(counts: dict) -> str:
    return " · ".join(f"{k} {v}" for k, v in counts.items() if v) or "없음"
