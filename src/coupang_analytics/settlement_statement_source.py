"""위탁정산서 입력 읽기 — 정산집계(확정분) · 계정→사업자 · 미정산(정산 예정). T-25 이관(옛 `business_statements.py` 54~394줄 · 행동 불변).

- ①②③ = 정산집계 엑셀(settlement_download stats 결과) 값 그대로(settlement_stats 가 단일 계산원).
  ② = 판매수수료 + 판매자할인쿠폰 + 쿠팡 지원 할인(가산 — 판매−쿠폰−수수료−정산 차액·음수=가산) + 로켓그로스 물류비 − 재고 손실 보상.
- ④ 미정산 = 판매됐지만 아직 정산 파일에 없는 몫 — **쿠팡이 계산한 숫자만**(D-081·추정 없음·소유자 2026-10-19):
  윙 = 검증자료 매출내역(purchase) 월별 정산대상액(apAmount) − 정산 파일 윙 정산금액(구매확정분·87/87 원 단위 일치 → '확정').
  로켓그로스 = 쿠팡 정산현황 예정 줄(정산예정기록.jsonl·D-078) — 정산 파일이 없는 판매 주마다 정산 줄의 판매액+환불−수수료−할인
  (737/737 원 단위) 또는 70%+30% 지급대상 합(20/20). 70% 줄만 있으면 70% 금액만(나머지는 '30% 줄 아직 없음'). 예정 줄이 없는
  계정·빈 주 = 금액 없이 '자료 없음'·'확인 필요'. 구매확정(윙)·매출인식(로켓그로스) 전 판매는 쿠팡이 아직 계산하지 않아 넣지 않음.
- 계정 → 사업자: 대응표 CSV > 관리대장 스냅샷(ledger.json, 비밀번호 없음) > 정산 계정명. 정산 계정 파일은 읽지 않음.
경로는 모두 인자(base = output/정산 폴더 · supp = 보충 조회 폴더 또는 None).
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import openpyxl

from coupang_analytics import settlement_files as SF
from coupang_analytics import settlement_forecast as FC
from coupang_analytics.settlement_ledger import wing_month_targets

OWN_BUSINESSES = {"디프", "디프픽"}       # 우리(소유자) 사업자 — 위탁 통보 대상 아님(소유자 2026-10-19): 계산은 같게·파일은 따로
OWN_DIR = "_우리사업자(통보 제외)"
SINCE = "2026-01"
DETAIL = (("월별 정산(매출월)", "계정별 월별"), ("계좌 입금(지급월별)", "계좌 입금"),
          ("상품별 월별", "상품별 월별"), ("로켓그로스 물류비 상품별", "로켓그로스 비용 상품별"))


def extras(path: Path) -> dict:
    """계정ID → [별도 보상 줄]. 쿠팡 정산 자료(정산현황·재고 손실 보상·월렛)에 없는 쿠팡 입금(화재 보상금 등·통장 근거).
    path = 입력 폴더 `쿠팡_별도보상.json`(없으면 빈 사전)."""
    out: dict = defaultdict(list)
    for r in (json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []):
        out[r["계정ID"]].append(r)
    return out


# ── 계정 → 사업자 ──────────────────────────────────────────────────
def aid_of(name: str) -> str:
    return name.rsplit("-", 1)[-1]


def _from_name(acct: str) -> tuple[str, str, str]:
    parts = acct.split("-")
    if len(parts) >= 3:
        return parts[0], "-".join(parts[1:-1]), parts[-1]
    if len(parts) == 2 and parts[0] != parts[1]:
        return "", parts[0], parts[1]
    return "", "", parts[-1]


def _guess(a: str, stale: dict) -> dict:
    """대응표·관리대장에 없는 계정 = 정산 계정명(또는 예전 정산 계정명)에서."""
    rep, biz, aid = _from_name(a)
    src = "정산 계정명"
    if not biz:
        for old, now in stale.items():
            if now == a and _from_name(old)[1]:
                rep, biz, _ = _from_name(old)
                src = f"예전 정산 계정명({old})"
    return {"대표자": rep, "사업자": biz or f"{aid} (사업자명 미확인)", "계정ID": aid,
            "출처": src if biz else "미확인(계정 파일에 이름 없음)"}


def build_map(accts: list, led: list, stale: dict, map_in: Path, map_out: Path) -> dict:
    """map_in = 입력 폴더 `사업자_대응표.csv`(없으면 대응표 없음) · map_out = 출력 폴더에 새로 씀(옛 동작과 같은 내용)."""
    fixed = {}
    if map_in.exists():
        with map_in.open(encoding="utf-8-sig", newline="") as f:
            fixed = {r["정산 계정명"]: r for r in csv.DictReader(f)}
    out = {}
    for a in accts:
        if a in fixed:
            r = fixed[a]
            out[a] = {"대표자": r["대표자"], "사업자": r["사업자"], "계정ID": r["계정ID"], "출처": r["출처"]}
            continue
        hit = next((row for row in led if a.endswith("-" + SF._token(row["id"], "계정명"))), None)
        if hit:
            out[a] = {"대표자": hit["rep"], "사업자": hit["label"], "계정ID": hit["id"], "출처": "관리대장(10/12)"}
            continue
        out[a] = _guess(a, stale)
    with map_out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["정산 계정명", "대표자", "사업자", "계정ID", "출처"])
        for a, v in sorted(out.items(), key=lambda kv: (kv[1]["사업자"], kv[0])):
            w.writerow([a, v["대표자"], v["사업자"], v["계정ID"], v["출처"]])
    return out


# ── 정산집계 읽기(확정분) ──────────────────────────────────────────
def _stale_names(wb, data: dict) -> tuple[set, dict]:
    """(지금 계정명, 예전 이름 → 지금 이름) — 검증 자료에만 남은 예전 이름(D-054 이전 집계 대비)."""
    cur = {r[0] for sh in ("계정별 월별", "쿠팡 지급 내역") for r in wb[sh].iter_rows(min_row=2, values_only=True)
           if r and r[0]}
    by_id = {aid_of(n): n for n in cur}
    names = {r[0] for r in data["계좌 입금"][1]} | {r[0] for r in wb["검증"].iter_rows(min_row=2, values_only=True)
                                                 if r and r[0]}
    return cur, {n: by_id[aid_of(n)] for n in names if n not in cur and aid_of(n) in by_id}


def _verify_counts(wb, stale: dict) -> dict:
    verify: dict = defaultdict(Counter)
    for r in wb["검증"].iter_rows(min_row=2, values_only=True):
        if r and r[0] and r[0] not in stale and r[7] in ("다름", "확인 필요"):
            verify[r[0]][r[7]] += 1
    return verify


def _pay_row(r: tuple, ph: list, ref: dict, fastm: dict) -> None:
    """쿠팡 지급 내역 한 줄 → 광고비·빠른정산 참고 합."""
    for k, key in (("totalAdSalesDeductionAmount", "ad"), ("totalArFactoringDeductionAmount", "ar")):
        if isinstance(r[ph.index(k)], (int, float)):
            ref[r[0]][key] += r[ph.index(k)]
    ym = str(r[ph.index("정산일")])[:7]
    if r[ph.index("채널")] == "윙":
        w = sum(x["금액"] or 0 for x in json.loads(r[ph.index("차감 사유")] or "[]")
                if x["사유"] == "빠른정산 계좌인출액")
        ref[r[0]]["fast_w"] += w
        fastm[(r[0], ym)][0] += w
    elif isinstance(r[ph.index("totalArFactoringDeductionAmount")], (int, float)):
        fastm[(r[0], ym)][1] += r[ph.index("totalArFactoringDeductionAmount")]


def _pay_refs(wb, cur: set, data: dict) -> tuple[dict, dict]:
    prow = list(wb["쿠팡 지급 내역"].iter_rows(values_only=True))
    ph = list(prow[0])
    ref: dict = defaultdict(Counter)
    fastm: dict = defaultdict(lambda: [0, 0])          # (계정, 정산월) → [윙 빠른정산, 로켓그로스 빠른정산]
    for r in prow[1:]:
        if r and r[0] in cur and str(r[ph.index("정산일")]) >= SINCE:
            _pay_row(r, ph, ref, fastm)
    for c in ref.values():
        c["fast"] = c["fast_w"] + c["ar"]
    ih, irows = data["계좌 입금"]
    for r in irows:
        if str(r[1]) >= SINCE:
            ref[r[0]]["paid"] += r[ih.index("쿠팡 지급 합계")] or 0
    return ref, fastm


def read_stats(stats: Path) -> dict:
    """시트 데이터 + 예전 이름(검증 자료에만 남은) 줄 제거(D-054 이전 집계 대비) + 검증 건수 + 지급 참고."""
    wb = openpyxl.load_workbook(stats, read_only=True)
    data = {}
    for _, src in DETAIL:
        rows = list(wb[src].iter_rows(values_only=True))
        data[src] = (list(rows[0]), [list(r) for r in rows[1:] if r and r[0]])
    cur, stale = _stale_names(wb, data)
    hdr, rows = data["계좌 입금"]
    data["계좌 입금"] = (hdr, [r for r in rows if r[0] not in stale])
    verify = _verify_counts(wb, stale)
    ref, fastm = _pay_refs(wb, cur, data)
    return {"data": data, "stale": stale, "verify": verify, "ref": ref, "fastm": fastm}


def confirmed(data: dict) -> tuple[dict, dict]:
    """계정별 확정 합계(①②③) + 계정·월별 정산 파일 몫(미정산 계산용)."""
    h, rows = data["상품별 월별"]
    ix = {c: h.index(c) for c in h}
    tot: dict = defaultdict(Counter)
    per: dict = defaultdict(Counter)
    for r in rows:
        a, m = r[0], str(r[1]).replace("-", "")

        def g(c: str, r=r) -> int:
            return r[ix[c]] or 0
        t = tot[a]
        t["sales"] += g("윙 판매액") + g("로켓그로스 매출금액")
        t["fee"] += g("판매수수료(VAT포함)")
        t["coupon"] += g("판매자할인쿠폰")
        t["settle"] += g("쿠팡 정산금액 합계(부가비용 차감 전)")
        t["logi"] += g("로켓그로스 물류비(VAT포함)")
        t["comp"] += g("재고 손실 보상")
        t["final"] += g("물류비·보상 반영 후(광고비 등 계정 차감 전)")
        for c, k in (("윙 판매액", "w_sales"), ("윙 정산금액", "w_settle"), ("로켓그로스 매출금액", "r_sales"),
                     ("로켓그로스 정산대상액", "r_settle"), ("윙 수량", "w_q"), ("로켓그로스 수량", "r_q")):
            per[(a, m)][k] += g(c)
    for t in tot.values():
        t["other"] = t["sales"] - t["coupon"] - t["fee"] - t["settle"]
        t["cost"] = t["fee"] + t["coupon"] + t["other"] + t["logi"] - t["comp"]
    return tot, per


def per_dict(per) -> dict:
    """confirmed() 의 per(Counter 값) → (계정, YYYYMM) → {키: 값} 사전(장부 E1 입력)."""
    return {k: dict(v) for k, v in per.items()}


# ── 미정산(정산 예정) — 쿠팡이 계산한 숫자만(D-081) · 예정 금액 포함(소유자 2026-10-19) ──────────
def _purchase(base: Path, a: str, snap: dict | None) -> dict:
    """매출내역 {YYYYMM: 응답} — 검증자료 + 스냅샷(같은 달은 스냅샷)."""
    p = base / "검증자료" / f"{a}.json"
    d = (json.loads(p.read_text(encoding="utf-8")).get("purchase") or {}) if p.exists() else {}
    return {**d, **((snap or {}).get("purchase") or {})}


def purchase_ap(pur: dict) -> dict:
    """{YYYY-MM: 매출내역 정산대상(apAmount) 합} — 장부의 끝난 달 독립 대조용."""
    return {f"{m[:4]}-{m[4:]}": sum(x["apAmount"] for x in ((v or {}).get("purchaseReports") or [])) for m, v in pur.items()}


def _wing_unsettled(a: str, pur: dict, per: dict, t30: dict, src: str, today: str) -> list:
    """윙 = 달 정산대상 − 정산 파일 몫. 달 정산대상 = 쿠팡 30%(최종액)·월정산 줄의 정산대상(지급됐든 예정이든 — 조회 시점
    구매확정분까지) / 그 줄이 아직 없으면 매출내역 정산대상."""
    out = []
    filed = {m for (aa, m), v in per.items() if aa == a and round(v.get("w_settle", 0))}
    for m in sorted(set(pur) | ({mm.replace("-", "") for mm in t30} & filed)):     # 범위 = 매출내역 달 + 정산 파일 있는 달
        mm = f"{m[:4]}-{m[4:]}"
        rs = (pur.get(m) or {}).get("purchaseReports") or []
        rev, ap = sum(x["revenueAmount"] for x in rs), sum(x["apAmount"] for x in rs)
        f = per[(a, m)]
        if mm in t30:
            tgt, kind, note = t30[mm], "쿠팡 계산(윙 최종액 줄 정산대상)", src
            if mm >= today[:7] and round(tgt) != round(ap):
                note += f" · 매출내역(어제까지) {ap:,.0f}보다 {tgt - ap:+,.0f} = 조회 시점까지 추가 구매확정분"
        else:
            tgt, kind, note = ap, "확정(매출내역)", src
        if round(tgt - f["w_settle"]) > 0:
            out.append(("윙", mm, int(rev - f["w_sales"]), int(round(tgt - f["w_settle"])), kind, note))
    return out


def rg_file_targets(base: Path) -> dict:
    """계정ID → {(기간 시작, 기간 끝): 정산대상} — 로켓그로스 판매수수료 정산 파일(장부 E1 '30% 줄 생성 전' 계산용)."""
    out: dict = defaultdict(dict)
    for p in (base / "파일").glob("*_로켓그로스_*판매수수료_*.xlsx"):
        m = SF.parse_file_name(p.name)
        out[aid_of(m["account"])][(str(m["period_start"]), str(m["period_end"]))] = SF.load_settle_file(p).settle_total
    return out


def _settled_weeks(base: Path) -> set:
    """(계정ID, 기간 시작, 기간 끝) — 로켓그로스 판매수수료 정산 파일이 있는 판매 기간(그 몫은 ③ 확정에 들어 있음)."""
    out = set()
    for p in (base / "파일").glob("*_로켓그로스_*판매수수료_*.xlsx"):
        m = SF.parse_file_name(p.name)
        out.add((aid_of(m["account"]), str(m["period_start"]), str(m["period_end"])))
    return out


def _rg_week(ls: list) -> tuple:
    """한 판매 주의 예정 줄들 → (구분, 정산대상, 판매금액 또는 None) — 쿠팡 칸만 더하고 뺌(D-081)."""
    for x in ls:
        tgt = FC.rg_target(x)
        if tgt is not None:
            return "쿠팡 계산(정산 줄 정산대상)", tgt, FC.rg_sales(x)
    pay = {int(float(x["지급비율"])): int(x.get("totalPayableAmount") or 0) for x in ls}
    if 100 in pay:
        return "쿠팡 계산(100% 지급대상)", pay[100], None
    if 70 in pay and 30 in pay:
        return "쿠팡 계산(70%+30% 지급대상)", pay[70] + pay[30], None
    return "쿠팡 계산(70% 몫만 — 30% 줄 아직 없음)", sum(pay.values()), None


def _rg_week_sales(base: Path, supp: Path | None, aid: str, gs: date, ge: date) -> int | None:
    """쿠팡 판매분석 주별(월~일) 로켓그로스 판매액·수량 절댓값 합 — 빈 기간이 걸친 주 전부. 그 주 자료가 하나라도 없으면 None."""
    p = base.parent / "판매분석_기간" / f"{aid}.json"
    d = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    sp = supp / f"{aid}_판매분석주별.json" if supp else None     # 판매분석 기록 없는 계정 = 보충 조회(같은 쿠팡 데이터 주소)
    if sp and sp.is_file():
        d = {**d, **json.loads(sp.read_text(encoding="utf-8"))}
    if not d:
        return None
    total, mon = 0, gs - timedelta(days=gs.weekday())
    while mon <= ge:
        w = d.get(f"W:{mon}")
        if w is None:
            return None
        total += sum(abs(o.get("판매금액") or 0) + abs(o.get("판매수량") or 0)
                     for o in w.get("옵션", {}).values() if o.get("구분") == "로켓그로스")
        mon += timedelta(days=7)
    return total


def _rg_gap(base: Path, supp: Path | None, aid: str, had: list, first: str) -> list:
    """정산 파일 끝 ~ 예정 줄 시작 사이 빈 판매 기간. 쿠팡 판매분석 주별 로켓그로스 판매·수량이 모두 0 = 판매 없음(쿠팡이 정산 줄을
    만들지 않음)이라 표시 안 함. 그 밖(판매 있음·판매분석 주별 자료 없음) = 금액 없이 '확인 필요'."""
    if not (had and first and had[-1] < first):
        return []
    gs, ge = date.fromisoformat(had[-1]) + timedelta(days=1), date.fromisoformat(first) - timedelta(days=1)
    if gs > ge:
        return []
    sold = _rg_week_sales(base, supp, aid, gs, ge)
    if sold == 0:
        return []
    why = "판매분석 주별 자료 없음" if sold is None else "판매분석에 판매 있음"
    return [("로켓그로스", str(gs)[:7], 0, 0, "확인 필요",
             f"{gs}~{ge} 판매 기간은 정산 파일·쿠팡 예정 줄 둘 다 없음({why}) — 금액 넣지 않음")]


def _last_login(base: Path) -> dict:
    """계정ID → 정산 프로그램이 마지막으로 로그인에 성공한 날(처리기록) — 예정 줄을 조회했는지 판단."""
    out: dict = {}
    p = base / "로그" / "처리기록_누적.csv"
    if p.is_file():
        with p.open(encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                if r["단계"] == "로그인" and r["결과"] == "정상":
                    a = aid_of(r["계정"])
                    out[a] = max(out.get(a, ""), r["시각"][:10])
    return out


def _rg_weeks(aid: str, rows: list, settled: set) -> dict:
    """(월, 구분) → [판매금액, 정산대상, 기간들, 판매액 빠짐] + 판매 주 시작일 목록 — 정산 파일 없는 2026 판매 주만."""
    weeks: dict = defaultdict(list)
    for r in rows:
        if (aid, str(r["기간 시작"])[:10], str(r["기간 끝"])[:10]) not in settled and str(r["기간 시작"])[:10] >= "2026-01-01":
            weeks[(str(r["기간 시작"])[:10], str(r["기간 끝"])[:10])].append(r)
    acc: dict = defaultdict(lambda: [0, 0, [], False])
    for (s0, e0), ls in sorted(weeks.items()):
        kind, amt, sales = _rg_week(ls)
        if not amt and not sales:
            continue
        g = acc[(s0[:7], kind)]
        g[0] += sales or 0
        g[1] += amt
        g[2].append(f"{s0[5:]}~{e0[5:]}")
        g[3] = g[3] or sales is None
    return {"acc": acc, "first": min((s0 for s0, _ in weeks), default="")}


def _rg_unsettled(base: Path, supp: Path | None, aid: str, rows: list, settled: set, src: str, collected: bool) -> list:
    """정산 파일 없는 로켓그로스 판매 주의 정산대상 = 쿠팡 정산 줄(지난 줄·예정 줄) — 쿠팡 숫자만(D-081)."""
    had = sorted(e for (a, _, e) in settled if a == aid)
    if not rows:
        return [] if (not had or collected) else [("로켓그로스", "-", 0, 0, "자료 없음",
                                                     "쿠팡 정산 줄 조회 없음(로그인 실패 등) — 금액 넣지 않음")]
    wk = _rg_weeks(aid, rows, settled)
    out = _rg_gap(base, supp, aid, had, wk["first"])
    for (m, kind), (sales, amt, per_, miss) in sorted(wk["acc"].items()):
        note = f"{src} · 판매 주 {len(per_)}개 {', '.join(per_)}"
        if miss:
            note += " · 판매금액 = 정산 줄 판매액 칸 저장 전 기록이라 비움"
        out.append(("로켓그로스", m, int(sales), int(amt), kind, note))
    return out


def unsettled(base: Path, supp: Path | None, accts: list, per: dict, led, snaps: dict) -> tuple[dict, dict]:
    """계정 → [(채널, 월, 미정산 판매금액, 정산 예정액, 구분, 비고)] + 계정 → 매출내역 달별 정산대상(장부 대조용)."""
    settled, login = _settled_weeks(base), _last_login(base)
    first_day = min((r["수집일"] for r in FC.load(base / FC.FORECAST_FILE)), default="")
    out, aps = {}, {}
    for a in accts:
        aid = aid_of(a)
        snap = snaps.get(aid)
        src = f"쿠팡 정산현황·매출내역 조회 {led.src_day.get(aid) or '-'}"
        pur = _purchase(base, a, snap)
        aps[a] = purchase_ap(pur)
        wing = ([("윙", "-", 0, 0, "자료 없음", "매출내역 없음 — 금액 넣지 않음")] if not pur
                else _wing_unsettled(a, pur, per, wing_month_targets(led.wing_rows(aid)), src, led.today))
        collected = aid in snaps or login.get(aid, "") >= first_day
        out[a] = wing + _rg_unsettled(base, supp, aid, led.rg_rows(aid), settled, src, collected)
    return out, aps
