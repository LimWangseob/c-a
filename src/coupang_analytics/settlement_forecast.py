"""정산 예정 기록·정확도 — D-078(소유자 2026-10-16 "로켓그로스 예정액 개선 — 정확한 금액인지 분석 후 적용·광고비·물류비 등
차감까지 반영해 정산되어야 할 금액이 최대한 100% 맞도록").

쿠팡 정산현황(윙·로켓그로스)을 오늘 이후까지 조회하면 쿠팡이 미리 만든 **앞으로의 정산 줄**(정산대상·공제·예정 최종지급액)이
온다(노바네스트 화면 실측: 정산일 2026-11-03 '월정' 줄 463원). 이 줄은 지급 내역(쿠팡지급내역/*.json — 지난 정산만)과 섞지 않고
수집일마다 `정산예정기록/YYYY-MM.jsonl`(수집일 달 · D-243 ③ — 지난 달 파일은 다시 안 씀) 에 쌓는다. 정산일이 지나면 실제 지급 내역과 맞대 **며칠 전 예정이 원 단위로 맞았는지**(정산대상·
공제 항목·최종지급액)를 '예정 정확도' 시트로 낸다. 정산서 ④ 정산 예정(로켓그로스)은 이 기록의 예정 줄을 쓴다(D-081 — 계정별 마지막 수집일).
"""
from __future__ import annotations

import json
import shutil
import time
from collections import Counter
from datetime import date
from pathlib import Path

FORECAST_FILE = "정산예정기록.jsonl"
AHEAD_DAYS = 70                    # 정산현황을 오늘 뒤 며칠까지 조회할지(윙 최종액 = 익익월 1일까지 덮음)
_KEEP = ("정산일", "기간 시작", "기간 끝", "지급비율", "최종지급액", "지급상태",
         # 윙
         "targetAmount", "totalDeductionAmount", "paidAmount", "pendingAmount", "차감 사유",
         # 로켓그로스
         "totalPayableAmount", "totalAdSalesDeductionAmount", "totalMilkRunDeductionAmount",
         "totalArFactoringDeductionAmount", "totalAdditionalDeductionAmount", "totalFinalCfsFeeDeductionAmount",
         "totalNegativeDeductionAmount", "totalCarryOverSettlementDeductionAmount", "totalCfsInventoryCompensationAmount",
         "totalSalesAdjustment", "totalFinalSettlementAmount",
         # 로켓그로스 정산대상 100% 를 쿠팡 칸 그대로 만드는 칸(D-081 — 70% 줄만 있어도 ÷0.7 없이)
         "totalSalesAmount", "totalRefundedAmount", "totalTakeRateAmountWithVat", "totalSellerDiscount")
_RG_TARGET = ("totalSalesAmount", "totalRefundedAmount", "totalTakeRateAmountWithVat", "totalSellerDiscount")
# 정확도 비교 칸: (보여 줄 이름, 쿠팡 칸) — 채널마다 있는 칸만
COMPARE = (("정산대상(윙)", "targetAmount"), ("공제(윙)", "totalDeductionAmount"),
           ("지급대상(RG)", "totalPayableAmount"), ("광고비(RG)", "totalAdSalesDeductionAmount"),
           ("밀크런(RG)", "totalMilkRunDeductionAmount"), ("빠른정산(RG)", "totalArFactoringDeductionAmount"),
           ("물류비(RG)", "totalFinalCfsFeeDeductionAmount"), ("보상(RG)", "totalCfsInventoryCompensationAmount"),
           ("판매조정(RG)", "totalSalesAdjustment"), ("최종지급액", "최종지급액"))


def rg_target(r: dict) -> int | None:
    """로켓그로스 정산 줄의 그 판매 기간 정산대상 100% = 판매액 + 환불액(음수) − 판매수수료(VAT 포함) − 판매자할인.
    쿠팡 칸만 더하고 뺀다(실측: 정산 파일 있는 70% 줄 737/737 원 단위 = 판매수수료 리포트 정산대상). 칸이 없으면 None."""
    if not all(k in r for k in _RG_TARGET):
        return None
    s, rf, t, d = (_num(r[k]) for k in _RG_TARGET)
    return int(round(s + rf - t - d))


def rg_sales(r: dict) -> int | None:
    """로켓그로스 정산 줄의 판매액 − 환불(쿠팡 칸). 칸이 없으면 None."""
    if "totalSalesAmount" not in r or "totalRefundedAmount" not in r:
        return None
    return int(round(_num(r["totalSalesAmount"]) + _num(r["totalRefundedAmount"])))


def split_future(rows: list, today: date) -> tuple[list, list]:
    """정산현황 금액 줄 → (오늘까지 = 지급 내역에 저장, 오늘 뒤 = 예정 기록)."""
    t = today.isoformat()
    past = [r for r in rows if str(r["정산일"])[:10] <= t]
    return past, [r for r in rows if str(r["정산일"])[:10] > t]


def _key(acct: str, ch: str, r: dict) -> tuple:
    return acct, ch, str(r["정산일"])[:10], str(r["기간 시작"])[:10], str(r["기간 끝"])[:10], float(r["지급비율"] or 0)


_last_batch = 0


def _next_batch() -> str:
    """묶음 번호 = 조회 시각(ns) — 단 이 프로세스 안에서는 **항상 앞 번호보다 큼**. Windows 시계는 연달아 부르면 같은
    값을 줄 수 있어(10-21 게이트 간헐 실패 실측: 두 조회가 같은 번호 → '마지막 묶음'이 둘을 합침) 같으면 1 올린다."""
    global _last_batch
    _last_batch = max(time.time_ns(), _last_batch + 1)
    return str(_last_batch)


def month_dir(path) -> Path:
    """달 파일 폴더 — 옛 한 파일 경로(…/정산예정기록.jsonl) 옆 같은 이름 폴더(…/정산예정기록/YYYY-MM.jsonl · D-243 ③)."""
    return Path(path).with_suffix("")


def _split_legacy(p: Path, today: date) -> None:
    """옛 한 파일 → 수집일 달 파일로 나눠 씀(이미 있는 같은 줄은 그 개수만큼 빼서 중복 없음) → 옛 파일은 보관/YYYY-MM/ 로 이동(삭제 없음).
    달 폴더가 없으면 임시 폴더에 다 쓴 뒤 이름 바꿈(중간에 끊겨도 반쪽 폴더를 읽지 않게)."""
    d = month_dir(p)
    by_month: dict = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            by_month.setdefault(json.loads(line)["수집일"][:7], []).append(line)
    work = d if d.is_dir() else d.with_name(d.name + ".tmp")
    keep = p.parent / "보관" / f"{today:%Y-%m}"
    if work != d and work.exists():                       # 지난번에 끊긴 임시 폴더(옛 파일은 그대로 있음) → 보관(삭제 없음)
        _move_free(work, keep)
    work.mkdir(parents=True, exist_ok=True)
    for month, lines in sorted(by_month.items()):
        mp = work / f"{month}.jsonl"
        have = Counter(mp.read_text(encoding="utf-8").splitlines()) if mp.exists() else Counter()
        new = []
        for ln in lines:                                  # 같은 줄이 여러 번(보류 해제 100% 같은 값 줄)이어도 개수대로
            if have[ln]:
                have[ln] -= 1
            else:
                new.append(ln)
        if new:
            with mp.open("a", encoding="utf-8") as f:
                f.write("".join(ln + "\n" for ln in new))
    if work != d:
        work.rename(d)
    _move_free(p, keep)


def _move_free(src: Path, folder: Path) -> None:
    """src → folder/ 같은 이름(이미 있으면 번호를 붙임 · 덮어쓰기·삭제 없음)."""
    folder.mkdir(parents=True, exist_ok=True)
    dst, n = folder / src.name, 1
    while dst.exists():
        dst, n = folder / f"{src.stem}.{n}{src.suffix}", n + 1
    shutil.move(str(src), str(dst))


def record(path, acct: str, ch: str, rows: list, today: date) -> int:
    """오늘 본 예정 줄을 추가 — 한 번 조회의 줄 묶음에 같은 '묶음' 번호. 같은 날 다시 조회하면 읽을 때 정산일마다 마지막
    묶음만 남음(같은 정산 줄 키가 여러 개인 보류 해제 100% 줄도 전부 · D-085). 저장 = 수집일 달 파일만(D-243 ③ · 옛 한 파일이
    있으면 먼저 달 파일로 나눔). 반환 = 기록한 줄 수."""
    if not rows:
        return 0
    if Path(path).is_file():
        _split_legacy(Path(path), today)
    p = month_dir(path) / f"{today:%Y-%m}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    batch = _next_batch()
    with p.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({"수집일": today.isoformat(), "계정": acct, "채널": ch, "묶음": batch,
                                **{k: r[k] for k in _KEEP if k in r}}, ensure_ascii=False) + "\n")
    return len(rows)


def load(path) -> list[dict]:
    """예정 기록 — (수집일·계정·채널·정산일) 마다 마지막 조회 묶음의 줄 전부. 묶음 없는 옛 기록 = 정산 줄마다 마지막 값.
    읽는 곳 = 달 폴더(정산예정기록/*.jsonl)가 있으면 그것만 · 없으면 옛 한 파일(옮겨 온 분석 사본 · D-243 ③)."""
    d = month_dir(path)
    files = sorted(d.glob("*.jsonl")) if d.is_dir() else [Path(path)] if Path(path).is_file() else []
    lines = [ln for f in files for ln in f.read_text(encoding="utf-8").splitlines()]
    groups: dict = {}
    for line in lines:
        if line.strip():
            r = json.loads(line)
            g = groups.setdefault((r["수집일"], r["계정"], r["채널"], str(r["정산일"])[:10]), {})
            g.setdefault(r.get("묶음", ""), {"old": {}, "rows": []})
            b = g[r.get("묶음", "")]
            if r.get("묶음"):
                b["rows"].append(r)
            else:
                b["old"][_key(r["계정"], r["채널"], r)] = r
    out: list = []
    for g in groups.values():
        newest = max(g)                                   # 묶음 번호 = 조회 시각(ns) · 옛 기록('') 보다 큼
        out += g[newest]["rows"] or list(g[newest]["old"].values())
    return out


def _num(v) -> float:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def accuracy(forecasts: list, amounts: list, today: date) -> list[dict]:
    """정산일이 지난 예정 줄 ↔ 실제 지급 내역(amounts: {'계정','채널', 정산 줄…}) — 칸마다 예정·실제·차이와 판정.
    실제 줄이 아직 없으면(로그인 실패 등) '실제 없음'."""
    actual = {_key(a["계정"], a["채널"], a): a for a in amounts}
    out = []
    for f in sorted(forecasts, key=lambda r: (r["계정"], r["채널"], r["정산일"], r["수집일"])):
        if str(f["정산일"])[:10] > today.isoformat():
            continue
        a = actual.get(_key(f["계정"], f["채널"], f))
        row = {"계정": f["계정"], "채널": f["채널"], "정산일": f["정산일"], "기간": f"{f['기간 시작']}~{f['기간 끝']}",
               "지급비율": f["지급비율"], "수집일": f["수집일"],
               "미리 본 일수": (date.fromisoformat(str(f["정산일"])[:10]) - date.fromisoformat(f["수집일"])).days}
        if a is None:
            out.append({**row, "판정": "실제 없음"})
            continue
        diffs = []
        for label, k in COMPARE:
            if k in f or k in a:
                pv, av = _num(f.get(k)), _num(a.get(k))
                row[f"예정 {label}"], row[f"실제 {label}"] = pv, av
                if round(pv) != round(av):
                    diffs.append(f"{label} {av - pv:+,.0f}")
        row["판정"] = "일치" if not diffs else "다름"
        row["차이(실제−예정)"] = " · ".join(diffs)
        out.append(row)
    return out


def summary(rows: list) -> list[dict]:
    """미리 본 일수 구간별 최종지급액·정산대상 일치율."""
    buckets = ((0, 3), (4, 7), (8, 14), (15, 30), (31, 999))
    out = []
    for ch in sorted({r["채널"] for r in rows}):
        for lo, hi in buckets:
            g = [r for r in rows if r["채널"] == ch and r["판정"] != "실제 없음" and lo <= r["미리 본 일수"] <= hi]
            if not g:
                continue
            fin = sum(1 for r in g if round(r.get("예정 최종지급액", 0)) == round(r.get("실제 최종지급액", 0)))
            out.append({"채널": ch, "미리 본 일수": f"{lo}~{hi}일" if hi < 999 else f"{lo}일 이상", "비교 줄": len(g),
                        "최종지급액 일치": fin, "최종 일치율": f"{fin / len(g):.0%}", "모든 칸 일치": sum(r["판정"] == "일치" for r in g)})
    return out
