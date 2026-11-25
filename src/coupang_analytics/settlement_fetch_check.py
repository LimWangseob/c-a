"""받기 의심 감지(T-82 · D-302) — 이미 받아 둔 정산 자료끼리 대조해 '받았는데 내용이 빠진' 파일을 찾고 다시 받을 대상을 남긴다.

접속 없음(파일만 읽음). 조용히 넘기지 않는다(오류 정의 = 목표 자료가 안 나옴):
- 비용 리포트(로켓그로스) — 시트 최종비용 합 ↔ 같은 정산 줄(정산일·기간)의 대응 공제 칸 합(`settlement_wing_api._COST_FIELDS`).
  리포트 0원(머리줄만)인데 공제 있음 = 받기 의심. 단 리뷰 이벤트 리포트는 0줄이어도 공제가 있음(D-324 ④ · 윙 화면 재받기도 0줄)
  → 대조 안 하고 아래 계정 누계로 검산.
- 리뷰 이벤트 계정 누계(D-324 ②) — 지급 내역 공제 합(로켓그로스 totalPostPurchaseDeductionAmount + 윙 차감 사유 '리뷰 이벤트') ↔
  검증자료 리뷰 캠페인 사용 리뷰 × 1건 금액(2,220 = 2,000 + 200×1.1 · D-302 ⑤). 공제가 더 많음·캠페인 자료 없음 = 받기 의심 ·
  공제가 모자람 = 아직 회차에 안 붙은 리뷰(쿠팡 배정 · 회차 미확정 · 확인 필요 · D-324 ③).
- 라이브정산 월자료 — 요약 totalAmount ↔ 라이브 공제 줄(로켓그로스 totalCoupangLiveDeductionAmount · 윙 차감 사유 '라이브')을
  계산일(calculationDate) 뒤 첫 같은 금액으로 짝짓고, 짝 없는 공제 줄의 해당 달 json 이 비었으면 받기 의심
  (실측 D-302: freewin7777 라이브정산_202602.json 빈데 2026-03-30 공제 347).
- 광고정산 json — 날짜×배송유형 subtotals 칸 없음 = 옛 질의로 받은 달(다시 받기는 T-90 이 필요한 계정·달만 · D-291 ⑥).
- 밀크런 엑셀 — 원문 칸 검산: 총 합계금액 = 발생금액 + 조정액 + 추가금 + 세액(output38 663줄 실측 · 추가금 9줄 포함) ·
  통행료 ≠ 0 은 아직 본 적 없어 확인 필요(합에 드는지 모름 · 추측 안 함).
결과 = 줄 목록(dict) → `write()` 가 받기의심.csv(전체) · 다시받을목록.csv(다시 받기 '예' 줄만)를 매번 통째로 다시 씀(현재 상태 목록).
"""
from __future__ import annotations

import csv
import json
import re
from datetime import date
from pathlib import Path

from . import daily_snapshot as DS
from . import settlement_files as SF
from .settlement_wing_api import _COST_FIELDS, CFS_KINDS

SUSPECT, CHECK, EXCLUDED = "받기 의심", "확인 필요", "제외"   # 제외 = 정산 대상 아님(받지 않음 · D-389)
YES, NO, T90 = "예", "아니오", "T-90 필요분만"
COLUMNS = ("판정", "종류", "계정", "정산일", "기간", "항목", "받은 값", "대조 값", "다시 받기", "근거 파일", "설명")
LIVE_FIELD = "totalCoupangLiveDeductionAmount"
REVIEW_REPORT = SF._token(_COST_FIELDS[SF.REVIEW_FIELD], "리포트")   # 파일 이름의 리뷰 이벤트 리포트 표기
WING_REVIEW = "리뷰 이벤트"                                           # 윙 차감 사유(실측 91white 11-13 4,440)
MILK_SUM = ("발생금액", "조정액", "추가금", "세액")      # 총 합계금액 = 이 칸들의 합(실측)
MILK_UNSEEN = ("통행료",)                              # 실측 값 전부 0 — 0 아니면 확인 필요


def _row(verdict, kind, acct, settle, period, item, got, want, again, src, why) -> dict:
    return dict(zip(COLUMNS, (verdict, kind, acct, settle, period, item, got, want, again, str(src), why)))


def report_fields() -> dict:
    """비용 리포트 이름(파일 이름 표기 = _token) → 대응 공제 칸들."""
    out: dict = {}
    for field, rep in _COST_FIELDS.items():
        out.setdefault(SF._token(rep, "리포트"), []).append(field)
    return out


def _payout(amounts: Path, acct: str, ch: str) -> list:
    p = amounts / f"{acct}_{ch}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def _num(v) -> int:
    return round(float(v or 0))


MAX_NEW = 400                                         # 한 실행에 새로 읽는 엑셀 수 상한(첫 실행 output38 규모 ≈2,100+546개 → 며칠에 나눔)


class _Later(Exception):
    """이번 실행 새 파일 상한을 다 씀 — 다음 실행에 읽음(남음 수로 보고)."""


def _memo(p: Path, memo: dict, budget: dict, compute):
    """파일 크기·수정 시각이 같으면 지난 결과 · 아니면 compute(p) (상한 넘으면 _Later)."""
    st = p.stat()
    sig = [st.st_size, st.st_mtime_ns]
    hit = memo.get(p.name)
    if hit and hit[:2] == sig:
        return hit[2]
    if budget["새 파일"] <= 0:
        budget["남음"] += 1
        raise _Later(p.name)
    budget["새 파일"] -= 1
    v = compute(p)
    memo[p.name] = [*sig, v]
    return v


def _cost_total(p: Path, end: date):
    """리포트 시트 합(int) 또는 읽기 실패 사유(str)."""
    try:
        return sum(SF.rg_cost_totals(SF.read_sheets(p), end).values())
    except SF.SettlementParseError as exc:
        return str(exc)[:200]


def new_budget(max_new: int = MAX_NEW) -> dict:
    return {"새 파일": max_new, "남음": 0}


def _load(path: Path | None) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path and path.exists() else {}


def _save(path: Path | None, memo: dict) -> None:
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(memo, ensure_ascii=False), encoding="utf-8")


def cost_checks(costs: Path, amounts: Path, memo_path: Path | None = None, budget: dict | None = None) -> list[dict]:
    """비용 리포트마다 시트 합 ↔ 그 정산 줄 대응 공제 칸 합 · memo_path = 파일별 시트 합 기억(없으면 매번 다 읽음).
    같은 정산 줄이 없는 물류비(CFS_KINDS) = 미납 CFS 주에 받는 리포트(D-065)라 건너뜀 · 그 밖 리포트는 확인 필요."""
    fields, out, cache = report_fields(), [], {}
    cfs_weeks = {SF._token(k, "리포트") for k in CFS_KINDS}
    memo, budget = _load(memo_path), budget if budget is not None else new_budget(10 ** 9)
    for p in sorted(costs.glob("*.xlsx")):
        m = SF.parse_file_name(p.name)
        acct, settle = m["account"], f"{m['settle_date']}"
        period = f"{m['period_start']}~{m['period_end']}"
        want_f = fields.get(m["report"])
        if want_f is None:
            out.append(_row(CHECK, "비용 리포트", acct, settle, period, m["report"], "", "", NO, p,
                            "대응 공제 칸을 모르는 리포트"))
            continue
        try:
            got = _memo(p, memo, budget, lambda f, end=m["period_end"]: _cost_total(f, end))
        except _Later:
            continue
        if isinstance(got, str):
            out.append(_row(SUSPECT, "비용 리포트", acct, settle, period, m["report"], "읽기 실패", "", YES, p, got))
            continue
        rows = cache.setdefault(acct, _payout(amounts, acct, "로켓그로스"))
        hit = [r for r in rows if (r.get("정산일"), r.get("기간 시작"), r.get("기간 끝")) ==
               (settle, f"{m['period_start']}", f"{m['period_end']}")]
        if not hit:
            if m["report"] in cfs_weeks:                      # 정산 줄 없는 주에 일부러 받는 물류비 리포트(미납 CFS · D-065) — 대조 대상 아님
                continue
            out.append(_row(CHECK, "비용 리포트", acct, settle, period, m["report"], got, "", NO, p, "대조할 지급 내역 줄 없음"))
            continue
        want = sum(_num(r.get(f)) for r in hit for f in want_f)
        if got == want or (got == 0 and m["report"] == REVIEW_REPORT):   # 리뷰 0줄 + 공제 = 쿠팡이 빈 리포트를 줌(D-324 ④ · review_checks)
            continue
        why = (f"리포트 자료 줄 0(머리줄만)인데 공제 {want:,}원" if got == 0
               else f"리포트 합 {got:,} ≠ 공제 {want:,}({'+'.join(want_f)})")
        out.append(_row(SUSPECT, "비용 리포트", acct, settle, period, m["report"], got, want, YES, p, why))
    _save(memo_path, memo)
    return out


def _calc(ym: str, summary: list) -> str:
    """그 달 라이브 계산일 'YYYY-MM-DD' — 요약 calculationDate, 없으면 다음 달 25일(실측 2026-01 → 02-25 · settlement_docs)."""
    for s in summary:
        cd = str(s.get("calculationDate") or "")
        if re.fullmatch(r"\d{8}", cd):
            return f"{cd[:4]}-{cd[4:6]}-{cd[6:]}"
    y, m = int(ym[:4]), int(ym[4:])
    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return f"{y}-{m:02d}-25"


def _live_deductions(amounts: Path, acct: str) -> list[list]:
    """[정산일, 금액, 채널, 짝 지음] — 로켓그로스 라이브 공제 칸 · 윙 차감 사유 '라이브'."""
    out = [[r["정산일"], _num(r.get(LIVE_FIELD)), "로켓그로스", False]
           for r in _payout(amounts, acct, "로켓그로스") if _num(r.get(LIVE_FIELD))]
    for r in _payout(amounts, acct, "윙"):
        out += [[r["정산일"], _num(x.get("금액")), "윙", False] for x in r.get("차감 사유") or []
                if "라이브" in str(x.get("사유") or "") and _num(x.get("금액"))]
    return sorted(out)


def live_checks(months_root: Path, amounts: Path) -> list[dict]:
    """계정 월자료 폴더마다 라이브정산 요약 ↔ 공제 줄."""
    out = []
    for d in sorted(x for x in months_root.iterdir() if x.is_dir()) if months_root.exists() else ():
        files = {p.stem.rsplit("_", 1)[-1]: p for p in d.glob("라이브정산_*.json")}
        if not files:
            continue
        summ = {ym: json.loads(p.read_text(encoding="utf-8")).get("요약") or [] for ym, p in files.items()}
        months = sorted((_calc(ym, s), ym) for ym, s in summ.items())
        ded = _live_deductions(amounts, d.name)
        for cd, ym in months:
            tot = sum(_num(s.get("totalAmount")) for s in summ[ym])
            for x in ded:
                if tot and not x[3] and x[1] == tot and x[0] > cd:
                    x[3] = True
                    break
        for settle, amt, ch, paired in ded:
            if paired:
                continue
            cand = [ym for cd, ym in months if cd < settle]
            if not cand:
                continue                                      # 받는 시작 달(settlement_docs.FROM) 앞 공제 — 범위 밖
            ym = cand[-1]
            empty = not summ[ym]
            out.append(_row(SUSPECT if empty else CHECK, "라이브정산", d.name, settle, ym, f"라이브 공제({ch})",
                            0 if empty else sum(_num(s.get("totalAmount")) for s in summ[ym]), amt,
                            YES if empty else NO, files[ym],
                            f"라이브정산_{ym}.json 비었는데 공제 {amt:,}원" if empty
                            else f"같은 금액 요약 달 없음(가장 가까운 달 {ym})"))
    return out


def ad_checks(ad_dir: Path) -> list[dict]:
    """광고정산 json 중 날짜×배송유형 subtotals 칸이 없는(옛 질의) 달."""
    out = []
    for p in sorted(ad_dir.glob("*_광고정산_*.json")) if ad_dir.exists() else ():
        acct, ym = p.stem.rsplit("_광고정산_", 1)
        if "subtotals" not in json.loads(p.read_text(encoding="utf-8")):
            out.append(_row(SUSPECT, "광고정산", acct, "", ym, "subtotals(날짜×배송유형 부가세)", "칸 없음", "", T90, p,
                            "옛 질의로 받은 달 — 다시 받기는 T-90 이 필요한 계정·달만(D-291 ⑥ · _광고_다시받기.json)"))
    return out


def _milk_num(v, where: str) -> int:
    s = str(v if v is not None else "").replace(",", "").strip()
    if not s:
        return 0
    if not re.fullmatch(r"-?\d+(\.0+)?", s):
        raise SF.SettlementParseError(f"{where}: 숫자 아님 {v!r}")
    return int(float(s))


def milk_checks(ad_dir: Path, memo_path: Path | None = None, budget: dict | None = None) -> list[dict]:
    """밀크런 엑셀 원문 칸 검산(조정액·추가금 포함 여부 · 처음 보는 칸 값) · 파일별 결과 기억(비용 리포트와 같은 방식)."""
    out, memo = [], _load(memo_path)
    budget = budget if budget is not None else new_budget(10 ** 9)
    for p in sorted(ad_dir.glob("*_밀크런_*.xlsx")) if ad_dir.exists() else ():
        try:
            out += _memo(p, memo, budget, _milk_file)
        except _Later:
            continue
    _save(memo_path, memo)
    return out


def _milk_file(p: Path) -> list[dict]:
    acct, ym = p.stem.rsplit("_밀크런_", 1)
    try:
        return _milk_rows(p, acct, ym)
    except SF.SettlementParseError as exc:                # 숫자 아닌 금액 칸 = 그 파일 받기 의심(조용히 0 으로 안 바꿈)
        return [_row(SUSPECT, "밀크런", acct, "", ym, "금액 칸", "읽기 실패", "", YES, p, str(exc)[:200])]


def _milk_rows(p: Path, acct: str, ym: str) -> list[dict]:
    out: list[dict] = []
    grid = SF.read_grid(p)
    head = [str(c or "").strip() for c in (grid[0] if grid else [])]
    need = {"밀크런번호", "총 합계금액", *MILK_SUM, *MILK_UNSEEN}
    if not need <= set(head):
        return [_row(SUSPECT, "밀크런", acct, "", ym, "머리글", "", "", YES, p, f"칸 없음 {sorted(need - set(head))}")]
    for i, raw in enumerate(grid[1:], start=2):
        r = dict(zip(head, raw))
        if not str(r.get("밀크런번호") or "").strip():
            continue
        where = f"{p.name} {i}행"
        tot, parts = _milk_num(r["총 합계금액"], where), sum(_milk_num(r[k], where) for k in MILK_SUM)
        unseen = {k: _milk_num(r[k], where) for k in MILK_UNSEEN if _milk_num(r[k], where)}
        if tot != parts:
            out.append(_row(CHECK, "밀크런", acct, "", ym, f"{r['밀크런번호']} 총 합계금액", tot, parts, NO, p,
                            f"{i}행 총 합계금액 ≠ {'+'.join(MILK_SUM)}"))
        if unseen:
            out.append(_row(CHECK, "밀크런", acct, "", ym, f"{r['밀크런번호']} {','.join(unseen)}", tot, parts, NO, p,
                            f"{i}행 처음 보는 값 {unseen} — 총 합계금액에 드는지 확인"))
    return out


def review_per(c: dict) -> int:
    """리뷰 1건 공제 = 리뷰 보상 + 사사오입(서비스 수수료 × 1.1) — 캠페인 칸(2,000 + 220 = 2,220 · D-302 ⑤ · D-324 ②)."""
    return int(c["incentivePerReview"]) + (int(c["serviceFeePerReview"]) * 11 + 5) // 10


def _review_taken(amounts: Path, acct: str) -> int:
    """지급 내역 리뷰 이벤트 공제 누계 — 로켓그로스 칸 + 윙 차감 사유 '리뷰 이벤트'."""
    rg = sum(_num(r.get(SF.REVIEW_FIELD)) for r in _payout(amounts, acct, "로켓그로스"))
    return rg + sum(_num(x.get("금액")) for r in _payout(amounts, acct, "윙") for x in r.get("차감 사유") or []
                    if WING_REVIEW in str(x.get("사유") or ""))


def _review_want(rc: dict) -> tuple[int, int, set]:
    """(사용 리뷰 수, 사용 리뷰 × 1건 금액 합, 1건 금액 종류) — 취소된 캠페인도 이미 쓴 리뷰는 공제(실측 91white fe9e2d01 2건)."""
    used = [(int((c.get("sellerContribution") or {}).get("consumedReviews") or 0), c) for c in rc.get("campaigns") or []]
    used = [(n, c) for n, c in used if n]
    return sum(n for n, _ in used), sum(n * review_per(c) for n, c in used), {review_per(c) for _, c in used}


def _review_one(acct: str, p: Path, rc: dict | None, got: int) -> dict | None:
    """rc = 검증자료 review_campaigns(없거나 조회 실패 = None) · got = 지급 내역 공제 누계."""
    if not rc:
        return None if not got else _row(SUSPECT, "리뷰 이벤트", acct, "", "누계", "리뷰 캠페인", got, 0, YES, p,
                                         f"공제 누계 {got:,}원인데 검증자료 리뷰 캠페인 자료 없음")
    try:
        n_used, want, per = _review_want(rc)
    except (KeyError, TypeError, ValueError) as exc:     # 1건 금액 칸이 없거나 숫자 아님 — 추측하지 않음
        return _row(CHECK, "리뷰 이벤트", acct, "", "누계", "1건 금액 칸", got, "", NO, p, f"캠페인 1건 금액 칸 읽기 실패 {exc!r}"[:200])
    if rc.get("hasMore"):
        return _row(SUSPECT, "리뷰 이벤트", acct, "", "누계", "리뷰 캠페인", got, want, YES, p,
                    f"캠페인 100개 넘음 — 다 못 받아 검산 못 함(받은 사용 리뷰 {n_used}건)")
    if got == want:
        return None
    if got > want:
        return _row(SUSPECT, "리뷰 이벤트", acct, "", "누계", "사용 리뷰 × 1건 금액", got, want, YES, p,
                    f"공제 누계 {got:,} > 사용 리뷰 {n_used}건 {want:,} — 캠페인 자료 빠짐 의심")
    one = next(iter(per)) if len(per) == 1 else 0
    cnt = f"{(want - got) // one}건 " if one and (want - got) % one == 0 else ""
    return _row(CHECK, "리뷰 이벤트", acct, "", "누계", "사용 리뷰 × 1건 금액", got, want, NO, p,
                f"아직 공제 안 된 리뷰 {cnt}{want - got:,}원 — 회차 미확정(쿠팡 배정 · 지급 전 경고값 · D-324 ③)")


def review_checks(ver: Path, amounts: Path) -> list[dict]:
    """계정마다 리뷰 이벤트 공제 누계 ↔ 사용 리뷰 × 1건 금액(D-324 ②) · 대상 = 공제가 있거나 캠페인 자료가 있는 계정."""
    camps = {}
    for p in sorted(ver.glob("*.json")) if ver.exists() else ():
        d = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(d, dict) and "review_campaigns" in d:
            camps[p.stem] = d["review_campaigns"]
    accts = set(camps) | ({p.stem.rsplit("_", 1)[0] for p in amounts.glob("*.json")} if amounts.exists() else set())
    out = []
    for acct in sorted(accts):
        r = _review_one(acct, ver / f"{acct}.json", camps.get(acct), _review_taken(amounts, acct))
        out += [r] if r else []
    return out


def scan(base: Path, max_new: int = MAX_NEW) -> tuple[list[dict], int]:
    """정산 기록 폴더(output/정산) 전체 대조 → (줄, 상한으로 이번에 못 읽어 다음 실행에 읽을 엑셀 수)."""
    base, budget = Path(base), new_budget(max_new)
    ver, memo = base / "검증자료", base / "자료출처"
    rows = (cost_checks(base / "파일" / "비용", base / "쿠팡지급내역", memo / "_비용리포트합.json", budget)
            + live_checks(ver / "월자료", base / "쿠팡지급내역") + ad_checks(ver / "광고")
            + milk_checks(ver / "광고", memo / "_밀크런검산.json", budget) + review_checks(ver, base / "쿠팡지급내역"))
    return rows, budget["남음"]


def write(folder: Path, rows: list[dict], today: date) -> tuple[Path, Path]:
    """받기의심.csv(전체) · 다시받을목록.csv(다시 받기 = 예 · T-90 필요분만) — 매번 통째로(지금 상태)."""
    folder.mkdir(parents=True, exist_ok=True)
    paths = (folder / "받기의심.csv", folder / "다시받을목록.csv")
    for path, rs in zip(paths, (rows, [r for r in rows if r["다시 받기"] != NO])):
        DS.keep_before_overwrite(path, today)                 # 전날 목록(D-335)
        with path.open("w", newline="", encoding="utf-8-sig") as fo:
            w = csv.DictWriter(fo, fieldnames=("확인일", *COLUMNS))
            w.writeheader()
            w.writerows({"확인일": f"{today}", **r} for r in rs)
    return paths


def summary(rows: list[dict]) -> str:
    """처리기록 한 줄 — 판정·종류별 개수."""
    from collections import Counter
    c = Counter((r["판정"], r["종류"]) for r in rows)
    return " · ".join(f"{v} {k} {n}" for (v, k), n in sorted(c.items())) or "없음"
