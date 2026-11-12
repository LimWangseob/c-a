"""쿠팡 정산 장부 — 정산금액 = 지급 완료 + 보류 + 지급 예정 + 쿠팡 줄 생성 전 (+ 공제). 쿠팡 숫자만(D-083·D-085).

근거: 도움말 FAQ 132(매출 인식·주정산 70/30·최종액 30% = 그 달 − 70%)·223(정산상태 확정/예정/보류)·238(보류목록·사유)·333(로켓그로스 70/30).
자료(계정마다 우선순위): 스냅샷({계정ID}.json — 같은 시각대에 조회한 지급 줄·매출내역·보류목록) > 보충({계정ID}.json 2025-11~12 줄·
{계정ID}_윙2026.json) > <output/정산> 쿠팡지급내역·정산예정기록·검증자료. 지급 줄 = 정산일 단위 묶음(같은 키 여러 줄 전부).
쿠팡 예정 줄은 조회 시점 그대로 전부 넣음(소유자 2026-10-19 '예정 금액 포함해 전체 정산금액에 반영') — 바뀔 수 있는 사유는 정산서에 표기.
판정(계정마다·원 단위):
  E1 정산금액 = 지급대상 — 로켓그로스 = 정산 파일 있는 판매 주마다 70%+30%(·월정산 100%) / 지급된 주인데 파일 없음 = 받기 누락 ·
     윙 = 달마다 정산대상(쿠팡 30%·월정산 줄 정산대상, 그 줄 없으면 정산 파일 + ④ 매출내역) = 지급대상(70·30·월정산),
     30% 줄 전인 달 = 나머지를 '줄 생성 전'(정산대상 − 70%) · 끝난 달은 30% 줄 정산대상 = 매출내역(독립 대조).
  E2 줄마다 최종지급액 = 윙 지급대상 + 보류해제 − 공제 / 로켓그로스 지급대상 − 추가공제 − 물류비 + 보상 + 판매조정.
  E3 정산현황 보류 줄(지급일 지남·PENDING) 최종 합 = 보류목록 P 중 지급일 지난 것 · 보류 예정 = 지급일이 앞.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from coupang_analytics import settlement_forecast as FC


def _num(v) -> float:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _aid(s: str) -> str:
    return s.rsplit("-", 1)[-1]


def _key(r: dict) -> tuple:
    return str(r["정산일"])[:10], str(r["기간 시작"])[:10], str(r["기간 끝"])[:10], int(_num(r["지급비율"]))


def release(r: dict) -> bool:
    """윙 보류 해제 지급 줄(100%·지급대상 0·보류해제액)."""
    return int(_num(r["지급비율"])) == 100 and not _num(r.get("targetAmount"))


def rg_window_overlap(rows: list) -> list:
    """스냅샷 로켓그로스 줄 = 지급일 달마다 조회(month_windows)를 이어 붙인 것 — 조회 끝이 다음 달 1일 0시(한국)까지라 1일 지급
    줄이 앞 달 조회에도 한 벌 더 옴(앱 read_events 는 ws<=지급일<=we 로 거름). 실측 기준일 조회 261018: 21계정 12-01 줄이 키마다
    정확히 2벌(ljung0622 10-19~25 30% 는 두 조회 사이 금액이 바뀜 66,692→90,131). 첫 달이 아닌 1일 줄이 같은 키로 짝수 벌이면
    뒤(그 달 조회) 절반만 — 같은 조회 안 같은 키 여러 줄(D-085)은 그대로."""
    first = min((str(r["정산일"])[:7] for r in rows), default="")
    idx: dict = defaultdict(list)
    for i, r in enumerate(rows):
        k = _key(r)
        if k[0][8:] == "01" and k[0][:7] > first:
            idx[k].append(i)
    drop = {i for ix in idx.values() if len(ix) % 2 == 0 for i in ix[: len(ix) // 2]}
    return [r for i, r in enumerate(rows) if i not in drop]


def load_snapshots(snap: Path | None) -> dict:
    if not (snap and snap.is_dir()):
        return {}
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in snap.glob("*.json")}


def wing_month_targets(rows: list) -> dict:
    """윙 30%(최종액)·월정산 줄 → {YYYY-MM: 그 달 정산대상(쿠팡 targetAmount)}. 판매 기간 = 그 달 첫 구매확정일 ~ 말일(진행 중인
    달은 조회 시점까지 — 실측 에벤에셀 10월 '10-05~10-18' 30% 예정 줄). 같은 달 줄이 여럿이면 마지막 정산일 값."""
    out: dict = {}
    for r in sorted(rows, key=lambda x: str(x["정산일"])):
        k = _key(r)
        if k[3] in (30, 100) and not release(r) and k[1][:7] == k[2][:7]:
            if k[0] >= "2026-01-01":                    # 2025 에 지급된 30% 줄 = 정산서 범위 밖
                out[k[1][:7]] = _num(r.get("targetAmount"))
    return out


class Ledger:
    def __init__(self, base: Path, supp: Path | None, snaps: dict, today: date):
        self.today, self.base, self.snaps = today.isoformat(), base, snaps
        self.past: dict = defaultdict(dict)          # (계정ID, 채널) → {정산일: [줄…]}
        self.future: dict = defaultdict(list)        # (계정ID, 채널) → [줄…]
        self.supp_data: dict = {}
        for p in (base / "쿠팡지급내역").glob("*.json"):
            acct, ch = p.stem.rsplit("_", 1)
            self._put(_aid(acct), ch, json.loads(p.read_text(encoding="utf-8")), True)
        if supp and supp.is_dir():
            for p in supp.glob("*.json"):
                if p.stem.endswith("_판매분석주별"):
                    continue
                if p.stem.endswith("_윙2026"):
                    self._put(p.stem[: -len("_윙2026")], "윙", json.loads(p.read_text(encoding="utf-8")), True)
                    continue
                d = json.loads(p.read_text(encoding="utf-8"))
                self.supp_data[d["계정ID"]] = d
                for ch in ("윙", "로켓그로스"):
                    self._put(d["계정ID"], ch, d.get(ch) or [], False)
        fc = FC.load(base / FC.FORECAST_FILE)
        last: dict = defaultdict(str)
        for r in fc:
            last[_aid(r["계정"])] = max(last[_aid(r["계정"])], r["수집일"])
        for r in fc:
            a = _aid(r["계정"])
            if a not in snaps and r["수집일"] == last[a] and str(r["정산일"])[:10] > self.today:
                self.future[(a, r["채널"])].append(r)
        self.src_day = dict(last)
        for a, s in snaps.items():                    # 스냅샷 = 그 계정 지급 줄의 정본(같은 시각대)
            for ch in ("윙", "로켓그로스"):
                rows = s.get(ch) or []
                if ch == "로켓그로스":
                    rows = rg_window_overlap(rows)
                self._put(a, ch, rows, True)
                self.future[(a, ch)] = [r for r in rows if str(r["정산일"])[:10] > self.today]
            self.src_day[a] = str(s.get("수집 끝", ""))[:16].replace("T", " ")

    def _put(self, a: str, ch: str, rows: list, replace: bool) -> None:
        g: dict = defaultdict(list)
        for r in rows:
            if str(r["정산일"])[:10] <= self.today:
                g[str(r["정산일"])[:10]].append(r)
        for d, rs in g.items():
            if replace or d not in self.past[(a, ch)]:
                self.past[(a, ch)][d] = rs

    def wing_rows(self, a: str) -> list:
        return [r for g in self.past[(a, "윙")].values() for r in g] + list(self.future[(a, "윙")])

    def rg_rows(self, a: str) -> list:
        return [r for g in self.past[(a, "로켓그로스")].values() for r in g] + list(self.future[(a, "로켓그로스")])

    def holds(self, acct_name: str) -> list:
        a = _aid(acct_name)
        if a in self.snaps:
            rows = (self.snaps[a].get("pending") or {}).get("pendingReports") or []
        elif a in self.supp_data:
            rows = (self.supp_data[a].get("pending") or {}).get("pendingReports") or []
        else:
            p = self.base / "검증자료" / f"{acct_name}.json"
            v = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
            rows = [x for m in (v.get("pending") or {}).values() for x in ((m or {}).get("pendingReports") or [])]
        seen, out = set(), []
        for x in rows:
            k = tuple(x.get(f) for f in ("pendingDate", "revenueRecognitionDateFrom", "revenueRecognitionDateTo", "paymentDate",
                                         "pendingReason", "finalPaymentAmount", "paymentStatus", "pendingAmount"))
            if k not in seen:
                seen.add(k)
                out.append(x)
        return out

    def _lines(self, a: str, acct_name: str, per: dict, unsettled: list, rg_files: dict) -> tuple[Counter, set, list]:
        """(윙 미정산 달별 정산 예정액, 윙 대상 달, 대상 지급 줄) — 로켓그로스 = 정산 파일 있는 주·2026 주 · 윙 보류 해제 = 2026 · 윙 = 대상 달."""
        un_w: Counter = Counter()
        for u in unsettled:
            if u[0] == "윙" and u[1] != "-" and not str(u[4]).startswith(("자료", "확인")):
                un_w[u[1]] += u[3]
        wing_months = {f"{m[:4]}-{m[4:]}" for (aa, m), v in per.items() if aa == acct_name and round(v.get("w_settle", 0))}
        wing_months |= set(un_w)
        raw = ([{**r, "채널": "윙", "구분": "지난" if str(r["정산일"])[:10] <= self.today else "예정"} for r in self.wing_rows(a)]
               + [{**r, "채널": "로켓그로스", "구분": "지난" if str(r["정산일"])[:10] <= self.today else "예정"}
                  for r in self.rg_rows(a)])
        rg2026 = {_key(r)[1:3] for r in raw if r["채널"] == "로켓그로스" and _key(r)[0] >= "2026-01-01"}

        def keep(r) -> bool:
            k = _key(r)
            if r["채널"] == "로켓그로스":
                return k[1:3] in rg_files or k[1:3] in rg2026
            if release(r):
                return k[0] >= "2026-01-01"
            return k[1][:7] in wing_months
        return un_w, wing_months, [r for r in raw if keep(r)]

    @staticmethod
    def _line_calc(r: dict) -> tuple[float, float, float, float]:
        """지급 줄 1개 → (지급대상, 보류 해제액, 공제, 공식 최종지급액) — E2 줄 공식."""
        if r["채널"] == "윙":
            pay, rel, ded = _num(r.get("paidAmount")), _num(r.get("pendingAmount")), _num(r.get("totalDeductionAmount"))
            return pay, rel, ded, pay + rel - ded
        pay = _num(r.get("totalPayableAmount"))
        plus = _num(r.get("totalCfsInventoryCompensationAmount")) + _num(r.get("totalSalesAdjustment"))
        ded = _num(r.get("totalAdditionalDeductionAmount")) + _num(r.get("totalFinalCfsFeeDeductionAmount")) - plus
        return pay, 0.0, ded, pay - ded

    def _rows(self, a: str, lines: list) -> tuple[Counter, list, list]:
        """(상태별 지급대상·최종·공제 합, E2 어긋난 줄, 장부 줄)."""
        b: Counter = Counter()
        e2_bad, rows = [], []
        for r in lines:
            ch, fin = r["채널"], _num(r["최종지급액"])
            pay, rel, ded, calc = self._line_calc(r)
            if round(calc) != round(fin):
                e2_bad.append((ch, *_key(r), round(calc), round(fin)))
            status = ("예정" if r["구분"] == "예정" else
                      "보류" if ch == "윙" and r.get("지급상태") not in (None, "DONE") else "지급 완료")
            if not (ch == "윙" and release(r)):
                b[f"지급대상 {status}"] += pay
            b[f"최종 {status}"] += fin
            b["공제"] += ded
            rows.append([a, ch, *_key(r), status + (" · 보류 해제 지급" if ch == "윙" and release(r) else ""), pay + rel, ded, fin])
        return b, e2_bad, rows

    @staticmethod
    def _weeks(lines: list) -> tuple[dict, dict, dict]:
        """(로켓그로스 판매 주 → {지급비율: 지급대상}, 윙 달 → 지급대상, 윙 달 → 30%·월정산 줄 있음)."""
        rg_week: dict = defaultdict(dict)
        wing_m: dict = defaultdict(float)
        has30: dict = defaultdict(bool)
        for r in lines:
            k = _key(r)
            if r["채널"] == "로켓그로스":
                rg_week[k[1:3]][k[3]] = rg_week[k[1:3]].get(k[3], 0.0) + _num(r.get("totalPayableAmount"))
            elif not release(r):
                wing_m[k[1][:7]] += _num(r.get("paidAmount"))
                has30[k[1][:7]] = has30[k[1][:7]] or k[3] in (30, 100)
        return rg_week, wing_m, has30

    def _e1_rg(self, lines: list, rg_week: dict, rg_files: dict, gen: Counter, e1: list) -> None:
        for (s, e), t in sorted(rg_files.items()):          # E1 로켓그로스 — 정산 파일 있는 판매 주
            p = rg_week.get((s, e), {})
            if 70 in p and 30 not in p and 100 not in p:
                gen[("로켓그로스", s[:7])] += t - p[70]
                e1.append(("로켓그로스", f"{s}~{e} 30% 줄 생성 전", round(t), round(p[70]), 0))
                continue
            got = sum(p.values())
            e1.append(("로켓그로스", f"{s}~{e}", round(t), round(got), round(t - got)))
        last_file = max((k[0] for k in rg_files), default="")
        paid_wk = {_key(r)[1:3] for r in lines if r["채널"] == "로켓그로스" and r["구분"] == "지난"}
        for (s, e), p in sorted(rg_week.items()):           # 지급된 판매 주인데 정산 파일 없음 = 받기 누락
            if (s, e) in paid_wk and (s, e) not in rg_files and round(sum(p.values())) and s <= last_file:
                e1.append(("로켓그로스", f"{s}~{e} 정산 파일 없음", 0, round(sum(p.values())), -round(sum(p.values()))))
        for (s, e), p in sorted(rg_week.items()):           # 70:30 검산 — 끝난 판매 주 30% 지급대상 ≈ 70% × 3/7(같은 줄 2벌 = 2배)
            if 70 in p and 30 in p and e <= self.today:      # 실측 기준일 조회 261018 167주: 차 최대 11원
                want = p[70] * 3 / 7
                if abs(p[30] - want) > max(100.0, abs(want) * 0.01):
                    e1.append(("로켓그로스", f"{s}~{e} 30% 줄 ↔ 70% 줄×3/7", round(want), round(p[30]), round(want - p[30])))

    def _e1_wing(self, a: str, acct_name: str, per: dict, un_w: Counter, wing_months: set, weeks: tuple, purchase_ap: dict,
                 gen: Counter, e1: list) -> None:
        _rg_week, wing_m, has30 = weeks
        for m in sorted(wing_months):                       # E1 윙 — 달
            tgt = per.get((acct_name, m.replace("-", "")), {}).get("w_settle", 0) + un_w[m]
            got = wing_m[m]
            if (not has30[m] or m >= self.today[:7]) and tgt - got > 0:
                gen[("윙", m)] += tgt - got
                why = "30% 줄 생성 전(= 정산대상 − 70%)" if not has30[m] else "이번 주 70% 줄 생성 전(= 정산대상 − 지급 줄)"
                e1.append(("윙", f"{m} {why}", round(tgt), round(got), 0))
                got = tgt
            if round(tgt) or round(got):
                e1.append(("윙", m, round(tgt), round(got), round(tgt - got)))
        for m, t30 in sorted(wing_month_targets(self.wing_rows(a)).items()):     # 끝난 달: 30% 줄 정산대상 = 매출내역
            if m in wing_months and m < self.today[:7] and m in purchase_ap:
                e1.append(("윙", f"{m} 30% 줄 정산대상 ↔ 매출내역", round(purchase_ap[m]), round(t30),
                           round(purchase_ap[m] - t30)))

    def account(self, acct_name: str, per: dict, unsettled: list, rg_files: dict, purchase_ap: dict) -> dict:
        """purchase_ap = {YYYY-MM: 매출내역 정산대상(apAmount)} — 끝난 달 독립 대조용."""
        a = _aid(acct_name)
        un_w, wing_months, lines = self._lines(a, acct_name, per, unsettled, rg_files)
        b, e2_bad, rows = self._rows(a, lines)
        weeks = self._weeks(lines)
        e1: list = []
        gen: Counter = Counter()
        self._e1_rg(lines, weeks[0], rg_files, gen, e1)
        self._e1_wing(a, acct_name, per, un_w, wing_months, weeks, purchase_ap, gen, e1)
        b["줄 생성 전"] = sum(gen.values())
        held_p = [x for x in self.holds(acct_name) if x.get("paymentStatus") == "P"]
        held_now = sum(_num(x.get("finalPaymentAmount")) for x in held_p if str(x.get("paymentDate")) <= self.today)
        held_next = sum(_num(x.get("finalPaymentAmount")) for x in held_p if str(x.get("paymentDate")) > self.today)
        e3 = (round(b["최종 보류"]), round(held_now))
        e1_bad = [x for x in e1 if x[4]]
        ok = not e1_bad and not e2_bad and e3[0] == e3[1] and not any(u[4] in ("자료 없음", "확인 필요") for u in unsettled)
        return {"계정ID": a, "gen": dict(gen), "buckets": b, "e1": e1, "e1_bad": e1_bad, "e2_bad": e2_bad, "e3": e3,
                "held_next": held_next, "reasons": dict(Counter(x.get("pendingReason") for x in held_p)), "rows": rows,
                "ok": ok, "fc_day": self.src_day.get(a, "")}
