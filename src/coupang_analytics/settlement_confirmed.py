"""쿠팡 확정 장부 만들기 — 계정ID × 판매 달(D-419 ② · T-188). 읽는 쪽 = `settlement_confirmed_read` · 월별 엑셀 = `settlement_confirmed_month`.

장부 `output/정산확정/`(지우지 않음 · 보존):
  건별/{계정ID}/{YYYY-MM}.json.gz = 지급 줄 전 칸 · 판매 줄(정산 파일 칸) · 비용 줄(비용 리포트 칸) · 광고 청구(광고정산 json) — 쿠팡 원문 값 그대로
  월별/{YYYY-MM}.xlsx · 보관/{계정ID}/ = 다시 열린 달의 옛 본문 · _장부.json = 상태·관찰·이력·원본 지문
판매 달 = 지급 줄·파일의 기간 시작 달(2025 판매 달 = 넣지 않음 D-328).
닫는 조건(모두): 달 끝남 · 정산일 지남 · 보류 0 · 예정 줄 0 · 이월 물류비 0 · 정산 파일 합 = 지급 줄 · 서로 다른 수집일 2번 같은 값.
수집일 = 그 계정 정산현황을 실제로 받은 날(`정산현황_원문/{계정}/{날짜}` · D-164 하루 1번) — 배치 날이 아님(로그인 못 한 날은 관찰이 아님).
닫힌 뒤 = 회차마다 원본과 대조 · 다르면 다시 엶(옛 본문 보관 + '확인 필요' — 다시 닫힐 때까지 매 배치).
값이 같고 칸만 더해진 것(쿠팡이 엑셀에 새 칸을 끼움 · 저장 칸 추가)은 옛 본문을 보관하고 새 원문으로 바꿈(닫힘 유지).
정산서 금액(관리 몫·산식 결과)은 넣지 않음(D-419 ③).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from calendar import monthrange
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from coupang_analytics import settlement_confirmed_month as MONTH
from coupang_analytics import settlement_confirmed_read as CR
from coupang_analytics import settlement_files as SF
from coupang_analytics import settlement_forecast as FC
from coupang_analytics import settlement_ledger as SL
from coupang_analytics import settlement_read_files as RF
from coupang_analytics import settlement_statement_cfs as CFS
from coupang_analytics import settlement_stats as SS
from coupang_analytics.settlement_store import RG_RAW_DIRNAME

WATCH, OPEN = "관찰", "못 닫음"            # 닫힘 = CR.CLOSED
REOPENED, WIDENED = "다시 열림", "칸 더해짐"    # 이력 종류
FINAL = "최종지급액"
CARRY = "totalCarryOverSettlementDeductionAmount"
CHANNELS = (SF.CH_WING, SF.CH_RG)


@dataclass
class Month:
    """계정×판매 달 하나 — 원본에서 모은 것(지급 줄 · 파일 경로 · 예정 줄)."""
    aid: str
    ym: str
    acct: str = ""
    rows: dict = field(default_factory=lambda: {ch: [] for ch in CHANNELS})
    paths: dict = field(default_factory=lambda: {k: {} for k in (CR.SALE, CR.COST, CR.AD)})
    coming: int = 0

    def all_rows(self) -> list:
        return [r for ch in CHANNELS for r in self.rows[ch]]

    def settle_files(self) -> list:
        return [RF.settle_file(p) for _t, p in sorted(self.paths[CR.SALE].items())]


# ── 원본 모으기 ───────────────────────────────────────────────
def collected_days(base: Path) -> dict:
    """계정ID → 정산현황을 마지막으로 받은 날(원문 파일 이름 · 부분본 제외)."""
    out: dict = {}
    for p in (base / RG_RAW_DIRNAME).glob("*/*.json.gz"):
        if "_부분" not in p.name:
            aid = p.parent.name.rsplit("-", 1)[-1]
            out[aid] = max(out.get(aid, ""), p.name[:10])
    return out


def _coming(base: Path, days: dict) -> Counter:
    """(계정ID, 판매 달) → 쿠팡 예정 줄 수 — 계정별 마지막 예정 기록 중 정산일이 수집일 이후인 줄."""
    fc = FC.load(base / FC.FORECAST_FILE)
    last: dict = defaultdict(str)
    for r in fc:
        a = SL._aid(r["계정"])
        last[a] = max(last[a], r["수집일"])
    out: Counter = Counter()
    for r in fc:
        a = SL._aid(r["계정"])
        if r["수집일"] == last[a] and str(r["정산일"])[:10] >= days.get(a, ""):
            out[a, str(r["기간 시작"])[:7]] += 1
    return out


def _files(base: Path):
    """(본문 칸, 판매 달, 경로) — 정산 파일·비용 리포트 = 이름의 기간 시작 달 · 광고 = 이름의 달. 이름 규칙 밖 파일은 정산서도 안 읽음."""
    for kind, d in ((CR.SALE, base / "파일"), (CR.COST, base / "파일" / "비용")):
        for p in sorted(d.glob("*.xlsx")):
            try:
                yield kind, f"{SF.parse_file_name(p.name)['period_start']:%Y-%m}", p
            except ValueError:
                continue
    for p in sorted((base / "검증자료" / "광고").glob("*_광고정산_*.json")):
        ym = p.stem.rsplit("_", 1)[-1]
        yield CR.AD, f"{ym[:4]}-{ym[4:]}", p


def gather(base: Path, today: date, days: dict) -> dict:
    """{(계정ID, 판매 달): Month} — 지급 줄이나 정산 파일이 있는 달만(비용·광고만 있는 달 = 확정할 지급이 없음)."""
    out: dict = {}

    def month(aid: str, ym: str) -> Month:
        return out.setdefault((aid, ym), Month(aid, ym))
    led = SL.Ledger(base, None, {}, today)
    for (aid, ch), g in led.past.items():
        for rows in g.values():
            for r in rows:
                if not SL.sold_2025(str(r["기간 시작"])[:7]):
                    month(aid, str(r["기간 시작"])[:7]).rows[ch].append(r)
    for kind, ym, p in _files(base):
        if not SL.sold_2025(ym):
            aid, tail = CR.file_key(p)
            month(aid, ym).paths[kind][tail] = p
    names = {SL._aid(p.stem.rsplit("_", 1)[0]): p.stem.rsplit("_", 1)[0] for p in (base / "쿠팡지급내역").glob("*.json")}
    coming = _coming(base, days)
    for (aid, ym), m in out.items():
        for ch in CHANNELS:
            m.rows[ch].sort(key=lambda r: (str(r["정산일"]), str(r["기간 시작"])))        # 저장 파일과 같은 순서
        m.coming = coming[aid, ym]
        m.acct = names.get(aid, aid)
    return {k: m for k, m in out.items() if m.all_rows() or m.paths[CR.SALE]}


# ── 닫는 조건 ─────────────────────────────────────────────────
def _file_gaps(m: Month) -> list[str]:
    """정산 파일 합 ≠ 지급 줄 — 로켓그로스 = 판매 주마다 정산대상 = 지급대상 합 · 윙 = 그 달 정산금액(집계 줄 고르기) = 지급대상 합."""
    rg: dict = {}
    wing = []
    for f in m.settle_files():
        if f.channel == SF.CH_RG:
            rg[str(f.period_start), str(f.period_end)] = f.settle_total
        else:
            wing.append(f)
    pay: Counter = Counter()
    for r in m.rows[SF.CH_RG]:
        pay[SL._key(r)[1:3]] += SL._num(r.get("totalPayableAmount"))
    out = [f"정산 파일 합 ≠ 지급 줄(로켓그로스 {s}~{e} 파일 {rg.get((s, e), 0):,.0f} · 지급 줄 {pay[s, e]:,.0f})"
           for s, e in sorted(set(rg) | set(pay)) if round(rg.get((s, e), 0)) != round(pay[s, e])]
    got = sum(r.settle for _f, r in SS._order_rows(wing, []))
    want = sum(SL._num(r.get("paidAmount")) for r in m.rows[SF.CH_WING] if not SL.extra_round(r))
    if round(got) != round(want):
        out.append(f"정산 파일 합 ≠ 지급 줄(윙 파일 {got:,.0f} · 지급 줄 {want:,.0f})")
    return out


def reasons(m: Month, day: str) -> list[str]:
    """지금 못 닫는 사유([] = 관찰 가능) — day = 그 계정 수집일."""
    rows = m.all_rows()
    if not day:
        return ["수집 기록 없음(정산현황 원문)"]
    last_day = f"{m.ym}-{monthrange(int(m.ym[:4]), int(m.ym[5:]))[1]:02d}"
    late = sum(str(r["정산일"])[:10] >= day for r in rows)
    held = sum(r.get("지급상태") not in (None, "DONE") for r in rows)
    carry = sum(SL._num(r.get(CARRY)) for r in rows)
    out = [w for bad, w in ((not rows, "지급 줄 없음"), (last_day >= day, "판매 달이 안 끝남"), (late, f"정산일 안 지난 줄 {late}"),
                            (held, f"보류 줄 {held}"), (m.coming, f"예정 줄 {m.coming}"),
                            (round(carry), f"이월 물류비 {carry:,.0f}")) if bad]
    return out + _file_gaps(m)


# ── 본문(원문 값) ─────────────────────────────────────────────
def _sha(p: Path) -> str:
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _cells(kind: str, p: Path) -> dict:
    if kind == CR.AD:
        return json.loads(p.read_text(encoding="utf-8"))
    sheets = SF.read_sheets(p)
    SF.assert_no_pii(sheets)                     # 구매자명 칸이 있으면 넣지 않음(그 달 못 닫음)
    return sheets


def build_body(m: Month, day: str) -> tuple[bytes, dict]:
    """(본문 바이트, {칸: {파일: 원본 sha}}) — 다시 풀어 원문과 같은지 확인하고 돌려줌(다르면 오류 = 그 달 못 닫음)."""
    body: dict = {"계정ID": m.aid, "계정명": m.acct, "판매달": m.ym, "수집일": day, CR.PAY: {ch: m.rows[ch] for ch in CHANNELS}}
    shas: dict = {}
    for kind, files in m.paths.items():
        body[kind], shas[kind] = {}, {}
        for tail, p in sorted(files.items()):
            shas[kind][tail] = _sha(p)
            body[kind][tail] = {"원본지문": shas[kind][tail], "칸": _cells(kind, p)}
            if _sha(p) != shas[kind][tail]:
                raise ValueError(f"읽는 사이 원본이 바뀜 — {p.name}")
    data = CR.encode(body)
    if CR.decode(data) != body:
        raise ValueError("장부 본문을 다시 풀면 원문과 다름")
    return data, shas


# ── 대조 ──────────────────────────────────────────────────────
def _norm(o):
    """비교용 — 수 = 실수 · '차감 사유' 목록은 순서 무시(쿠팡이 순서만 바꿔 줌)."""
    if isinstance(o, bool) or o is None or isinstance(o, str):
        return o
    if isinstance(o, (int, float)):
        return float(o)
    if isinstance(o, dict):
        return {k: (sorted(map(_norm, v), key=_text) if k == "차감 사유" and isinstance(v, list) else _norm(v)) for k, v in o.items()}
    return [_norm(x) for x in o] if isinstance(o, (list, tuple)) else o


def _text(o) -> str:
    return json.dumps(o, ensure_ascii=False, sort_keys=True, default=str)


def rows_digest(rows: dict) -> str:
    return hashlib.sha256(_text({ch: sorted(map(_text, map(_norm, rows[ch]))) for ch in CHANNELS}).encode()).hexdigest()


def order_digest(rows: dict) -> str:
    """받은 그대로(줄·목록 순서·수 모양까지) 지문 — 값이 같아도 다르면 본문을 새 원문으로 바꿔 두 길의 계산 순서까지 같게 함."""
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()


def covers(old, new) -> bool:
    """옛 값이 새 값 안에 그대로 있음(사전 = 새 칸이 더 있어도 됨 · 목록 = 길이·값 같음). 둘 다 `_norm` 을 거친 값."""
    if isinstance(old, dict):
        return isinstance(new, dict) and all(k in new and covers(v, new[k]) for k, v in old.items())
    if isinstance(old, list):
        return isinstance(new, list) and len(old) == len(new) and all(map(covers, old, new))
    return old == new


def _row_changes(ch: str, old: list, new: list) -> list[str]:
    """지급 줄 바뀜 설명([] = 값 같음 · 최종지급액이 바뀐 줄 먼저) — 같은 줄끼리 짝지은 뒤 남은 줄."""
    left = [(r, _norm(r)) for r in new]
    gone = []
    for r in old:
        n = _norm(r)
        hit = next((i for i, (_x, y) in enumerate(left) if covers(n, y)), None)
        if hit is None:
            gone.append(r)
        else:
            left.pop(hit)
    out = []
    for r in gone:
        i = next((i for i, (x, _y) in enumerate(left) if SL._key(x) == SL._key(r)), None)
        label = f"{ch} 정산일 {SL._key(r)[0]}({SL._key(r)[1]}~{SL._key(r)[2]} {SL._key(r)[3]}%)"
        if i is None:
            out.append(f"{label} 줄 사라짐(최종 {SL._num(r['최종지급액']):,.0f})")
            continue
        x = left.pop(i)[0]
        names = [k for k in r if not covers(_norm({k: r[k]}), _norm(x))]
        if FINAL in names:
            out.insert(0, f"{label} {FINAL} {SL._num(r[FINAL]):,.0f}→{SL._num(x[FINAL]):,.0f} · 바뀐 칸 {len(names)}개")
        else:
            out.append(f"{label} 바뀐 칸 {len(names)}개({', '.join(names[:3])} · {FINAL} 그대로)")
    return out + [f"{ch} 정산일 {SL._key(x)[0]}({SL._key(x)[1]}~{SL._key(x)[2]} {SL._key(x)[3]}%) 새 줄(최종 {SL._num(x['최종지급액']):,.0f})"
                  for x, _y in left]


def _parsed(kind: str, p: Path, sheets: dict):
    """정산서가 그 파일에서 읽는 값(지금 코드) — 칸 배치만 다른 다시 받은 파일을 같은 값으로 봄. 못 읽는 형식 = 칸 그대로."""
    meta = SF.parse_file_name(p.name)
    try:
        if kind == CR.SALE:
            grid = next(iter(sheets.values()))
            return SF.load_settle_file(p, grid), RF.rates_of(grid)
        lines = SF.rg_cost_lines(sheets, meta["account"], meta["period_end"])
        return lines, [] if meta["report"].startswith(("재고", "리뷰")) else CFS.day_lines(sheets)
    except SF.SettlementParseError:
        return "못 읽음", sheets


def _file_changes(kind: str, old: dict, files: dict, shas: dict) -> list[str]:
    """파일 바뀜 설명([] = 값 같음) — old = 본문의 그 칸 · shas = 장부에 적힌 원본 지문."""
    out = [f"{kind} 파일 사라짐 {t}" for t in sorted(set(old) - set(files))]
    out += [f"{kind} 새 파일 {t}" for t in sorted(set(files) - set(old))]
    for t in sorted(set(old) & set(files)):
        if _sha(files[t]) == shas.get(t):
            continue
        was, now = old[t]["칸"], _cells(kind, files[t])
        same = covers(_norm(was), _norm(now)) if kind == CR.AD else _parsed(kind, files[t], was) == _parsed(kind, files[t], now)
        if not same:
            out.append(f"{kind} 파일 값 바뀜 {t}")
    return out


def _untouched(m: Month, e: dict) -> bool:
    """본문을 풀지 않고 알 수 있는 '그대로' — 지급 줄 지문·파일 목록·파일 지문이 모두 장부와 같음."""
    return rows_digest(m.rows) == e["줄지문"] and all(
        set(m.paths[k]) == set(e["파일"][k]) and all(_sha(p) == e["파일"][k][t] for t, p in m.paths[k].items()) for k in m.paths)


def compare(m: Month, e: dict, root: Path) -> tuple[list[str], float, bool]:
    """(바뀐 것, 최종지급액 차이, 칸만 더해짐) — 장부 본문 ↔ 지금 원본."""
    p = CR.case_path(root, m.aid, m.ym)
    data = p.read_bytes() if p.is_file() else b""
    if CR.digest(data) != e["본문"]:
        return ["장부 본문 파일이 없거나 깨짐"], 0.0, False
    if _untouched(m, e):
        return [], 0.0, False
    body = CR.decode(data)
    out: list = []
    for ch in CHANNELS:
        out += _row_changes(ch, body[CR.PAY][ch], m.rows[ch])
    for kind in m.paths:
        out += _file_changes(kind, body[kind], m.paths[kind], e["파일"][kind])
    final = [sum(SL._num(r["최종지급액"]) for ch in CHANNELS for r in rs[ch]) for rs in (m.rows, body[CR.PAY])]
    return out, final[0] - final[1], not out


# ── 상태 바꾸기 ───────────────────────────────────────────────
def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def _keep_old(m: Month, root: Path, mark: str) -> str:
    """지금 본문을 보관 폴더로(덮어쓰지 않음) → 보관 파일 이름('' = 본문이 없음)."""
    src, d = CR.case_path(root, m.aid, m.ym), root / CR.OLD / m.aid
    if not src.is_file():
        return ""
    d.mkdir(parents=True, exist_ok=True)
    dst, n = d / f"{m.ym}_{mark}.json.gz", 1
    while dst.exists():
        dst, n = d / f"{m.ym}_{mark}_{n}.json.gz", n + 1
    os.replace(src, dst)
    return f"{CR.OLD}/{m.aid}/{dst.name}"


def _put(m: Month, e: dict, data: bytes, shas: dict, root: Path) -> None:
    _write(CR.case_path(root, m.aid, m.ym), data)
    e.update({"본문": CR.digest(data), "줄지문": rows_digest(m.rows), "순서지문": order_digest(m.rows), "파일": shas})


def _observe(m: Month, e: dict, day: str, root: Path) -> None:
    """지금 값을 본문으로 쓰고 첫 관찰로 — 못 쓰는 사유(개인정보 칸·형식)는 못 닫는 사유로 남김."""
    try:
        data, shas = build_body(m, day)
    except (SF.SettlementParseError, ValueError, TypeError) as exc:
        return _not_closable(m, e, [f"장부에 못 넣음 — {exc}"], root)
    _put(m, e, data, shas, root)
    e.update({"상태": WATCH, "사유": ["같은 값 1번(다른 날 한 번 더 같으면 닫음)"], "첫수집일": day, "수집일": day, "확정일": ""})


def _not_closable(m: Month, e: dict, why: list, root: Path) -> None:
    for k in ("본문", "줄지문", "순서지문", "파일", "첫수집일"):
        e.pop(k, None)
    CR.case_path(root, m.aid, m.ym).unlink(missing_ok=True)       # 관찰 중이던 본문(확정 아님 · 원본에서 다시 만들어짐)
    e.update({"상태": OPEN, "사유": why, "확정일": ""})


def _reopen(m: Month, e: dict, why: list, diff: float, root: Path, today: str) -> None:
    e["이력"].append({"종류": REOPENED, "날": today, "확정일": e["확정일"], "바뀐 것": why, "최종지급액 차이": round(diff),
                    "보관": _keep_old(m, root, e["확정일"])})


def _widen(m: Month, e: dict, day: str, root: Path, today: str) -> None:
    """값은 같고 칸만 더해짐 — 옛 본문 보관 + 새 원문으로(닫힘 유지). 새 원문을 못 넣으면 예외(`safe_step` 이 그 달을 다시 엶)."""
    data, shas = build_body(m, day)
    kept = _keep_old(m, root, f"{e['확정일']}_칸더해짐")
    _put(m, e, data, shas, root)
    e["이력"].append({"종류": WIDENED, "날": today, "보관": kept})


def _same_values(m: Month, e: dict, day: str, root: Path, wider: bool = False) -> None:
    """값이 그대로인 달 — 마지막 확인일 · 순서·수 모양(관찰 중이면 더해진 칸도 wider)만 다르면 본문을 이번 원문으로(보관 안 함)."""
    if wider or order_digest(m.rows) != e["순서지문"]:
        _put(m, e, *build_body(m, day), root)
    e["수집일"] = max(e["수집일"], day)


def step(m: Month, e: dict, day: str, root: Path, today: str) -> None:
    """계정×달 하나 — 장부 기록 e 를 이번 원본으로 갱신(제자리)."""
    e["계정명"] = m.acct
    why = reasons(m, day)
    changed, diff, wider = compare(m, e, root) if e.get("본문") else ([], 0.0, False)
    if e["상태"] == CR.CLOSED:
        if not changed and not (why and day):
            if wider:
                _widen(m, e, day, root, today)
            return _same_values(m, e, day, root)
        _reopen(m, e, changed or why, diff, root, today)
    elif e["상태"] == WATCH and not changed and not why:
        if day > e["첫수집일"]:
            e.update({"상태": CR.CLOSED, "사유": [], "확정일": day})
        return _same_values(m, e, day, root, wider)
    if why:
        _not_closable(m, e, why, root)
    else:
        _observe(m, e, day, root)


def safe_step(m: Month, e: dict, day: str, root: Path, today: str) -> None:
    """step 하나를 격리 — 원본을 못 읽는 달은 그 달만 못 닫음(닫혀 있었으면 다시 엶 = 장부를 쓰지 않음)."""
    try:
        step(m, e, day, root, today)
    except MemoryError:
        raise
    except Exception as exc:  # noqa: BLE001 — 사유를 그 달 기록·월별 엑셀·'확인 필요'에 남김(조용히 넘기지 않음)
        why = [f"{MONTH.UNREAD} — {exc.__class__.__name__}: {exc}"]
        if e["상태"] == CR.CLOSED:
            _reopen(m, e, why, 0.0, root, today)
        _not_closable(m, e, why, root)


# ── 갱신 ──────────────────────────────────────────────────────
def load_index(root: Path) -> dict:
    """장부 기록 — 없으면 빈 기록 · 깨졌으면 예외 그대로(새로 덮지 않음)."""
    p = root / CR.INDEX
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"계정": {}, "월별": {}}


def save_index(root: Path, idx: dict) -> None:
    _write(root / CR.INDEX, json.dumps(idx, ensure_ascii=False, indent=1).encode("utf-8"))


def reopened(e: dict) -> dict | None:
    """다시 열려 아직 안 닫힌 달의 마지막 '다시 열림' 기록(없으면 None)."""
    if e["상태"] == CR.CLOSED:
        return None
    return next((h for h in reversed(e["이력"]) if h["종류"] == REOPENED), None)


def check_lines(idx: dict) -> list[dict]:
    """'확인 필요' 줄(D-399 skipped 꼴) — 다시 열려 아직 안 닫힌 달 전부."""
    out = []
    for aid, months in sorted(idx["계정"].items()):
        for ym, e in sorted(months.items()):
            h = reopened(e)
            if h:
                what = " / ".join(h["바뀐 것"][:3]) + (f" 외 {len(h['바뀐 것']) - 3}건" if len(h["바뀐 것"]) > 3 else "")
                out.append({"id": aid, "account": e["계정명"], "amount": h["최종지급액 차이"],
                            "reason": f"{ym} 확정했던 쿠팡 값이 바뀜({h['날']} 다시 엶 · 옛 확정일 {h['확정일']}) — {what}"
                                      f" · 옛 값 = {h['보관'] or '없음'} · 이 달은 원본으로 계산"})
    return out


def update(base: Path, root: Path, today: date, on_log) -> dict:
    """장부 갱신 한 번 → 장부 기록. 원본은 읽기만 · 계정 하나 끝날 때마다 기록 저장(중간에 끊겨도 앞 계정은 남음)."""
    idx = load_index(root)
    days = collected_days(base)
    months = gather(base, today, days)
    for aid in sorted({a for a, _ym in months} | set(idx["계정"])):
        book = idx["계정"].setdefault(aid, {})
        for ym in sorted({y for a, y in months if a == aid} | set(book)):
            m = months.get((aid, ym)) or Month(aid, ym, book[ym]["계정명"])       # 원본이 통째로 사라진 달 = 빈 달과 대조
            e = book.setdefault(ym, {"상태": OPEN, "사유": [], "확정일": "", "수집일": "", "이력": []})
            safe_step(m, e, days.get(aid, ""), root, today.isoformat())
        save_index(root, idx)
    n = Counter(e["상태"] for b in idx["계정"].values() for e in b.values())
    on_log(f"확정 장부 — 닫힘 {n[CR.CLOSED]} · 관찰 {n[WATCH]} · 못 닫음 {n[OPEN]}(계정×판매 달) · 다시 열림 {len(check_lines(idx))}")
    for ym in sorted({y for _a, y in months}):
        MONTH.write(root, idx, ym, [(m, idx["계정"][a][ym]) for (a, y), m in sorted(months.items()) if y == ym], on_log)
    save_index(root, idx)
    return idx


def run_job(opts: dict, on_log) -> dict:
    """정산서 배치 단계(D-399 일 함수 꼴) — skipped = 다시 열린 달('확인 필요' 목록·탭·상태 카드로 나감)."""
    root = Path(opts["out"])
    idx = update(Path(opts["settle_dir"]), root, date.fromisoformat(opts["basis"]), on_log)
    by: dict = defaultdict(Counter)
    for book in idx["계정"].values():
        for ym, e in book.items():
            by[ym][e["상태"]] += 1
    return {"ok": [f"{ym} 닫힘 {c[CR.CLOSED]}/{sum(c.values())}" for ym, c in sorted(by.items())], "skipped": check_lines(idx),
            "files": [str(p) for p in sorted((root / CR.MONTHS).glob("*.xlsx"))], "abort": None,
            "note": f"장부 {root} · 만든 시각 {datetime.now():%Y-%m-%d %H:%M}"}
