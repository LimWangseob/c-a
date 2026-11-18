"""자료 출처 목록대로 매일 확인(T-78 · D-280 · D-291 · D-296) — 등록표 · 변경 이력 · S1 원문 대조(M-E) · S3 공개 웹(M-D).

설계 = `docs/plans/T78-source-list-daily-fetch-design-2026-11-17.md`(git 밖) 3·6절. 저장 = output/정산/자료출처/
  {출처ID}/{YYYY-MM-DD}.json(그날 본 값·글자) · 변경이력.csv(출처ID·항목·이전 값·새 값·처음 본 날·근거 — 추가만) ·
  원문관측.json(M-E 가 읽은 파일 이름·값별 처음 본 날).
- M-E(접속 없음): 이미 받은 정산 원문에서 로켓그로스 카테고리ID·카테고리명·판매수수료율, 윙 옵션별 서비스이용율을 모아
  처음 나온 카테고리ID·새 비율 값을 이력에 남김(설계 4절 10·14·15행 · 적용 시작일 = 원문 첫 날 D-291 ⑤).
  처음 실행(기준 없음)은 기준만 만들고 이력 줄을 쓰지 않음(수천 줄 방지) — 기준 완성 뒤부터 변경만.
- M-D(로그인 없음): 공개 페이지 글자를 쿠키·프록시 없는 일반 연결로 읽어 날짜 글자·글자 지문을 지난 값과 비교(D-291 ② ·
  비공식 웹은 받지 않음 ③). 글자가 비거나 날짜가 하나도 없으면 SiteChangedError(조용히 넘기지 않음).
- M-A(fee-details 화면 · S4)·M-B(공지 · S5)·M-G(계정 정산현황 글자 · S6)는 등록만(라이브 시험 전 · D-296 ②).
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import urllib.request
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path

from . import settlement_files as SF
from .settlement_wing_api import SiteChangedError

HISTORY_COLUMNS = ("기록일", "출처ID", "항목", "이전 값", "새 값", "처음 본 날", "근거")
WEEK = 7
# 출처ID → 설계서 4절 순번(자료출처_목록 '안 받음' 순서) · 방법 · 주기 · 단계 · (M-D) 주소. 단계 S4 이상 = 등록만(구현 전).
SOURCES: dict = {
    "ME-RG-CATEGORY": {"순번": (10, 14), "방법": "M-E", "주기": "매일", "단계": "S1",
                       "설명": "로켓그로스 판매수수료 원문 카테고리ID·카테고리명·판매수수료율(새 ID·새 비율)"},
    "ME-WING-RATE": {"순번": (14, 15), "방법": "M-E", "주기": "매일", "단계": "S1",
                     "설명": "윙 주문상세 원문 옵션별 서비스이용율(새 비율)"},
    "MD-FEE-TABLE": {"순번": (13,), "방법": "M-D", "주기": "매일", "단계": "S3",
                     "주소": "https://cloud.mkt.coupang.com/Fee-Table", "설명": "판매수수료율 공개표 기준일"},
    "MD-RG-ZEROCOST": {"순번": (27,), "방법": "M-D", "주기": "매주", "단계": "S3",
                       "주소": "https://marketplace.coupang.com/rocketgrowth-fee-after-zerocostpromotion",
                       "설명": "로켓그로스 비용 제로 이후 요금(웹 판 · 화면 값 우선)"},
    "MD-RG-MAIN": {"순번": (55, 57), "방법": "M-D", "주기": "매주", "단계": "S3",
                   "주소": "https://marketplace.coupang.com/rocket-growth",
                   "설명": "로켓그로스 소개(회수비 월 무료·반출 배송 서비스비 무료 문구)"},
    "MA-FEE-DETAILS": {"순번": (*range(1, 10), *range(22, 27), *range(28, 49), 52), "방법": "M-A", "주기": "매일 머리·매주 전체",
                       "단계": "S4", "설명": "윙 로켓그로스 비용/수수료 화면(탭·카테고리 보기 전환 + 화면 응답 기록 · D-296 ①)"},
    "MB-NOTICES": {"순번": (11, 12, 20), "방법": "M-B", "주기": "매일 제목·매주", "단계": "S5", "설명": "윙 공지사항 목록·본문"},
    "MC-HELP": {"순번": (15, 16, 58), "방법": "M-C", "주기": "매주", "단계": "보류",
                "설명": "도움말 수정일 — 앱 호출 보류(D-296 ④) · 하위 세션 화면 확인"},
    "MG-RG-STATUS": {"순번": (51,), "방법": "M-G", "주기": "매일(계정별)", "단계": "S6", "설명": "계정 로켓그로스 정산현황 '무료 체험 종료일'"},
    "ME-AD-DAILY": {"순번": (17,), "방법": "광고센터 기존 경로", "주기": "매일", "단계": "S2",
                    "설명": "광고 이번 달 1일~어제 일별(settlement_ads PROGRESS) · 옛 달 subtotals = T-90 필요분만"},
    "ME-RG-FEE-TABLE": {"순번": (*range(28, 50),), "방법": "M-E", "주기": "매일", "단계": "S4",
                        "설명": "할인표(M-A 로 받은 표) ↔ 원문 유료 줄 — 처음 어긋난 날 = 변경 후보(표가 있어야 함 · S4 뒤)"},
}
# 자료출처_목록 '안 받음' 중 받을 출처가 없는 행(설계 4절 · D-291 ⑦⑧ · D-296 ③) — 순번 → 사유.
NOT_SOURCED: dict = {18: "이미 받음(목록 정정 · settlement_ads summary.rocketGrowth)", 19: "이미 받음(목록 정정 · 보류목록 매일)",
                     21: "받을 수 없음 — 교환관리 화면 확인(T-80) 뒤 다시 설계(D-291 ⑧)",
                     50: "받을 수 없음 — 상품 수량·categoryId 보관 = 레인 A 별도(T-100 · D-296 ③)",
                     53: "자동 수집 안 함 — 비공식 웹(D-291 ③)", 54: "받을 필요 없음 — 원문 줄 검산이 우선",
                     56: "자동 수집 안 함 — 비공식 웹(D-291 ③)"}
ROWS = 58                                                # 자료출처_목록.csv '안 받음' 행 수(설계 0절)


def implemented(step: str) -> bool:
    return step in ("S1", "S2", "S3")


# ── 저장 ──────────────────────────────────────────────────────────
def folder(base: Path) -> Path:
    return Path(base) / "자료출처"


def append_history(base: Path, rows: list[dict], today: date) -> int:
    """변경이력.csv 에 줄 추가(추가만 · 지우지 않음). 반환 = 추가한 줄 수."""
    if not rows:
        return 0
    p = folder(base) / "변경이력.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.exists()
    with p.open("a", newline="", encoding="utf-8-sig" if new else "utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=HISTORY_COLUMNS)
        if new:
            w.writeheader()
        w.writerows({"기록일": f"{today}", **r} for r in rows)
    return len(rows)


def _hist(sid: str, item: str, old, new, first: str, why: str) -> dict:
    return {"출처ID": sid, "항목": item, "이전 값": old, "새 값": new, "처음 본 날": first, "근거": why}


def last_snapshot(base: Path, sid: str, before: date) -> tuple[str, dict] | None:
    """before 날 앞의 가장 최근 스냅숏 (날짜, 내용)."""
    d = folder(base) / sid
    days = sorted(p.stem for p in d.glob("*.json") if p.stem < f"{before}") if d.exists() else []
    return (days[-1], json.loads((d / f"{days[-1]}.json").read_text(encoding="utf-8"))) if days else None


def save_snapshot(base: Path, sid: str, today: date, data: dict) -> Path:
    p = folder(base) / sid / f"{today}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    _write_json(p, data)
    return p


def _write_json(p: Path, data) -> None:
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


# ── S1 원문 대조(M-E) ─────────────────────────────────────────────
_RG_CAT, _RG_NAME, _RG_RATE, _RG_DISC = "카테고리ID", "카테고리명", "판매수수료율(%,VAT별도)", "할인적용 판매수수료율(%,VAT별도)"
_RG_DAY, _WING_OPT, _WING_RATE, _WING_DAY = "매출인식일", "옵션 ID", "서비스이용율(%,VAT별도)", "구매확정일"


def _head(grid: list, must: tuple, where: str) -> tuple[int, dict]:
    for i, r in enumerate(grid[:5]):
        cells = [SF._norm(c) for c in r]
        if all(SF._norm(m) in cells for m in must):
            return i, {m: cells.index(SF._norm(m)) for m in must}
    raise SiteChangedError(f"{where}: 머리글 {must} 없음 — 원문 칸이 바뀜")


def _day(v) -> str:
    s = str(v or "").strip()[:10]
    return s if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) else ""


def _rate(v) -> str:
    s = str(v if v is not None else "").strip()
    return f"{float(s):g}" if re.fullmatch(r"-?\d+(\.\d+)?", s) else s


def observe_file(path: Path) -> dict:
    """원문 파일 1개 → {출처ID: {항목: {값: 처음 본 날}}} (로켓그로스 판매수수료 · 윙 주문상세만 · 그 밖 = {})."""
    meta = SF.parse_file_name(path.name)
    out: dict = {}

    def put(sid: str, item: str, val: str, day: str) -> None:
        cur = out.setdefault(sid, {}).setdefault(item, {})
        if val not in cur or (day and (not cur[val] or day < cur[val])):
            cur[val] = day
    grid = SF.read_grid(path)
    if meta["channel"] == SF.CH_RG and meta["report"] == "판매수수료":
        hi, ix = _head(grid, (_RG_CAT, _RG_NAME, _RG_RATE, _RG_DISC, _RG_DAY), path.name)
        for r in grid[hi + 1:]:
            cat = str(r[ix[_RG_CAT]] or "").strip() if ix[_RG_CAT] < len(r) else ""
            if not cat:
                continue
            day = _day(r[ix[_RG_DAY]])
            put("ME-RG-CATEGORY", f"{cat} 카테고리명", str(r[ix[_RG_NAME]] or "").strip(), day)
            put("ME-RG-CATEGORY", f"{cat} 판매수수료율", _rate(r[ix[_RG_RATE]]), day)
            put("ME-RG-CATEGORY", f"{cat} 할인적용 판매수수료율", _rate(r[ix[_RG_DISC]]), day)
    elif meta["channel"] == SF.CH_WING:
        hi, ix = _head(grid, (_WING_OPT, _WING_RATE, _WING_DAY), path.name)
        for r in grid[hi + 1:]:
            opt = str(r[ix[_WING_OPT]] or "").strip() if ix[_WING_OPT] < len(r) else ""
            if not re.fullmatch(r"\d+", opt) or opt == "0":
                continue                                       # 배송비 보조줄(<기본배송료>) 등
            put("ME-WING-RATE", f"{opt} 서비스이용율", _rate(r[ix[_WING_RATE]]), _day(r[ix[_WING_DAY]]))
    return out


def merge_observed(state: dict, obs: dict, name: str, track: bool) -> list[dict]:
    """관측을 상태에 합침 · track = 기준 완성 뒤(새 항목·새 값 → 이력 줄)."""
    hist = []
    vals = state.setdefault("값", {})
    for sid, items in obs.items():
        known = vals.setdefault(sid, {})
        for item, seen in items.items():
            cur = known.get(item)
            for val, day in sorted(seen.items(), key=lambda kv: kv[1]):
                if cur is None:
                    known[item] = cur = {}
                    if track:
                        hist.append(_hist(sid, item, "", val, day, f"원문에 처음 나온 항목 · {name}"))
                elif val not in cur and track:
                    old = max(cur.items(), key=lambda kv: kv[1])[0]
                    hist.append(_hist(sid, item, old, val, day, f"원문 새 값 · {name}"))
                if val not in cur or (day and (not cur[val] or day < cur[val])):
                    cur[val] = day
    return hist


def compare_originals(base: Path, files_dir: Path, today: date, max_files: int = 400) -> dict:
    """새로 받은 원문만 읽어 관측 상태를 갱신 · 기준 완성 뒤 바뀐 것은 변경이력에. 반환 = {읽음, 남음, 이력, 기준, 오류}.
    칸이 바뀌어 못 읽은 파일 = 오류 목록(호출부가 실패 기록 · 읽은 표시 안 해 다음 실행에 다시) — 나머지 파일은 계속."""
    sp = folder(base) / "원문관측.json"
    state = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {"파일": [], "값": {}, "기준": ""}
    done = set(state["파일"])
    todo = [p for p in sorted(files_dir.glob("*.xlsx")) if p.name not in done
            and ("_윙_" in p.name or "_판매수수료_" in p.name)]
    hist, errors = [], []
    for p in todo[:max_files]:
        try:
            obs = observe_file(p)
        except (SiteChangedError, SF.SettlementParseError, ValueError) as exc:   # 그 파일만 · 다음 실행에 다시(읽은 표시 안 함)
            errors.append(f"{p.name}: {exc}")
            continue
        hist += merge_observed(state, obs, p.name, bool(state["기준"]))
        done.add(p.name)
    left = len(todo) - min(len(todo), max_files)
    if not left and not state["기준"]:
        state["기준"] = f"{today}"
    state["파일"] = sorted(done)
    sp.parent.mkdir(parents=True, exist_ok=True)
    _write_json(sp, state)
    return {"읽음": min(len(todo), max_files) - len(errors), "남음": left, "이력": append_history(base, hist, today),
            "기준": state["기준"], "오류": errors}


# ── S3 공개 웹(M-D) ───────────────────────────────────────────────
class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        self._skip += tag in ("script", "style", "noscript")

    def handle_endtag(self, tag):
        self._skip -= tag in ("script", "style", "noscript") and self._skip > 0

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def page_text(html: str) -> str:
    t = _Text()
    t.feed(html)
    return re.sub(r"\s+", " ", " ".join(t.parts)).strip()


_DATE = re.compile(r"20\d{2}\s*[.\-/년]\s*\d{1,2}\s*[.\-/월]\s*\d{1,2}\s*일?")


def page_marks(text: str) -> dict:
    """비교할 값 = 날짜 글자(중복 없이 순서대로) · 글자 지문(sha256 앞 16)."""
    dates = list(dict.fromkeys(re.sub(r"\s+", "", d) for d in _DATE.findall(text)))
    return {"날짜": dates, "지문": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], "글자 수": len(text)}


def fetch_public(url: str, timeout: int = 20) -> str:
    """로그인 없는 일반 연결 — 프록시 없음(ProxyHandler 빈 값 · 환경변수 프록시도 안 씀) · 쿠키 저장소 없음(D-291 ②)."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR"})
    with opener.open(req, timeout=timeout) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")


def due_public(base: Path, today: date) -> list[str]:
    """오늘 읽을 공개 페이지 — 매일 = 오늘 스냅숏 없을 때 · 매주 = 마지막 스냅숏이 7일 넘었을 때."""
    out = []
    for sid, s in SOURCES.items():
        if s["방법"] != "M-D" or (folder(base) / sid / f"{today}.json").exists():
            continue
        last = last_snapshot(base, sid, today)
        if s["주기"] == "매일" or last is None or date.fromisoformat(last[0]) <= today - timedelta(days=WEEK):
            out.append(sid)
    return out


def check_public(base: Path, sid: str, today: date, fetch=fetch_public) -> list[dict]:
    """공개 페이지 1개 읽기 → 스냅숏 저장 · 지난 스냅숏과 날짜·지문 비교 → 이력 줄(저장까지 함)."""
    url = SOURCES[sid]["주소"]
    text = page_text(fetch(url))
    marks = page_marks(text)
    if marks["글자 수"] < 200 or not marks["날짜"]:
        raise SiteChangedError(f"{sid} {url}: 글자 {marks['글자 수']}자 · 날짜 {len(marks['날짜'])}개 — 화면 글자를 못 읽음"
                               "(스크립트로 그리는 페이지일 수 있음 · 확인 필요)")
    prev = last_snapshot(base, sid, today)
    save_snapshot(base, sid, today, {"주소": url, **marks, "글자": text})
    hist = []
    if prev and prev[1].get("지문") != marks["지문"]:
        gone = [d for d in prev[1].get("날짜", []) if d not in marks["날짜"]]
        new = [d for d in marks["날짜"] if d not in prev[1].get("날짜", [])]
        hist.append(_hist(sid, "페이지 글자", f"{prev[0]} 지문 {prev[1].get('지문')} · 빠진 날짜 {','.join(gone) or '-'}",
                          f"지문 {marks['지문']} · 새 날짜 {','.join(new) or '-'}", f"{today}",
                          f"{url} 글자 바뀜(적용 시작일 = 화면 문구 날짜 → 원문 첫 어긋남 → 감지한 날 D-291 ⑤)"))
    append_history(base, hist, today)
    return hist
