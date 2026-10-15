"""정산 증빙 원본 전체 받기 — 순수 계산 부분(D-067). 브라우저 단계는 settlement_evidence_web.

계정마다 증빙 폴더 `<상위>/증빙_{사업자}_쿠팡원본/` 아래 세 갈래(쿠팡에서 받은 원본·쿠팡 화면 인쇄만 — 가공 파일 없음):
- 정산원본_앱수집   = 윙 주문상세·로켓그로스 판매수수료·비용 리포트(정산다운로드 run --originals 와 같은 파일)
- 판매분석원본_월별 = 판매분석 '기간별 판매'·'상품별 판매' 달마다
- 지급증빙_메뉴원본 = 우대수수료 환급 엑셀 · 윙 지급 명세 PDF · 월렛 거래내역 PDF · 로켓그로스 광고비·밀크런 PDF ·
                      광고센터 월별 광고비 정산 보고서 PDF (+ 정산 줄 없는 주의 비용 리포트는 정산원본_앱수집 에)
결과 기록 = 폴더의 `_증빙목록.csv`(파일·크기·sha256) + `_수집결과.json`(단계별 정상/실패/없음) — 모든 단계 정상이면
`_수집완료.json`(다시 실행하면 그 계정 건너뜀). 근거 = 2026-10-15 니코에이블 통장 26,139,506 원 단위 대사(D-065).
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

ORIG, SALES, MENU = "정산원본_앱수집", "판매분석원본_월별", "지급증빙_메뉴원본"
DONE, RESULT, LISTING = "_수집완료.json", "_수집결과.json", "_증빙목록.csv"
OK, FAIL, NONE = "정상", "실패", "없음"


def business_of(label: str) -> str:
    """정산 계정 표시명 '대표자-사업자-계정ID' → 사업자(사업자 이름 안의 '-' 보존). 형식이 아니면 표시명 그대로."""
    parts = label.split("-")
    return "-".join(parts[1:-1]) if len(parts) >= 3 else label


def account_folder(base: Path, label: str) -> Path:
    return base / f"증빙_{re.sub(r'[\\/:*?\"<>|]', '_', business_of(label)).strip()}_쿠팡원본"


def month_windows(start: date, end: date) -> list[tuple[str, date, date]]:
    """[(YYYYMM, 그 달 첫날(시작 이후), 그 달 끝(끝 이전))]."""
    out, d = [], date(start.year, start.month, 1)
    while d <= end:
        nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        out.append((f"{d:%Y%m}", max(d, start), min(nxt - timedelta(days=1), end)))
        d = nxt
    return out


def _kst(s: str) -> date:
    return (datetime.fromisoformat(s.replace("Z", "+00:00")) + timedelta(hours=9)).date()


def missing_cost_weeks(reports: list[dict]) -> list[str]:
    """로켓그로스 정산 줄(정산현황 조회 응답 settlementStatusReports)에서 '미납 CFS'로만 보이는 주(정산 줄이 없는 주 —
    예: 판매 전 첫 입고 주의 바코드 비용) → 비용 리포트 요청용 묶음 키 목록. 실측: 니코에이블 5/11~17 13,200(D-065)."""
    have = {r.get("settlementGroupKey") for r in reports}
    want = set()
    for r in reports:
        key = r.get("settlementGroupKey") or ""
        vendor = key.split("-")[0]
        for d in (r.get("settlementStatusReportDetail") or {}).get("cfsDeductionDetails") or []:
            s, e = _kst(d["settlementPeriodStartDate"]), _kst(d["settlementPeriodEndDate"])
            want.add(f"{vendor}-{s}-{e}")
    return sorted(k for k in want - have if k.split("-")[0])


def _num(v) -> int:
    s = str(v if v is not None else "").replace(",", "").strip()
    return int(float(s)) if s not in ("", "-") else 0


def check_daily(rows: list[list], ws: date, we: date) -> tuple[bool, str, int, int]:
    """판매분석 '기간별 판매' 누락 검사 — 창의 모든 날짜 한 번씩·날짜 합 = 합계 줄. 반환 (정상, 설명, 판매량, 매출)."""
    head = [str(c).strip() for c in rows[0]]
    i_d, i_q, i_m = head.index("날짜"), head.index("판매량"), head.index("매출(원)")
    days = [r for r in rows[1:] if str(r[i_d] or "").strip()]
    total = [r for r in rows[1:] if not str(r[i_d] or "").strip()]
    want = [(ws + timedelta(days=k)).isoformat() for k in range((we - ws).days + 1)]
    got = [str(r[i_d]).strip()[:10] for r in days]
    q, m = sum(_num(r[i_q]) for r in days), sum(_num(r[i_m]) for r in days)
    probs = []
    if got != want:
        probs.append(f"날짜 {len(got)}/{len(want)}일·빠짐 {sorted(set(want) - set(got))[:5]}")
    if len(total) != 1:
        probs.append(f"합계 줄 {len(total)}개")
    elif (_num(total[0][i_q]), _num(total[0][i_m])) != (q, m):
        probs.append(f"날짜 합 {q}개·{m:,} ≠ 합계 줄 {_num(total[0][i_q])}개·{_num(total[0][i_m]):,}")
    return not probs, " · ".join(probs) or f"{len(got)}일 전부", q, m


def check_items(rows: list[list], q: int, m: int) -> tuple[bool, str]:
    """'상품별 판매' 합 = 기간별 합계."""
    head = [str(c).strip() for c in rows[0]]
    i_q, i_m = head.index("판매량"), head.index("매출(원)")
    iq, im = sum(_num(r[i_q]) for r in rows[1:]), sum(_num(r[i_m]) for r in rows[1:])
    ok = (iq, im) == (q, m)
    return ok, f"상품 {len(rows) - 1}줄" + ("" if ok else f" · 합 {iq}개·{im:,} ≠ 기간별 {q}개·{m:,}")


def refund_file_name(json_items: str, started: str) -> str:
    """정산관리 엑셀 다운로드 목록 줄(우대수수료 환급) → 저장 이름(조회 기간 그대로)."""
    cond = "_".join(str(x.get("value")) for x in json.loads(json_items or "[]")).replace(" ", "")
    tag = re.sub(r'[\\/:*?"<>|~]', "-", cond)[:40] or started[:19].replace(":", "")
    return f"쿠팡_우대수수료환급_{tag}.xlsx"


def listing_rows(folder: Path) -> list[dict]:
    """증빙 폴더의 쿠팡 원본 목록(작업 파일 '_'·엑셀 잠금 '~$' 제외)."""
    out = []
    for p in sorted(folder.rglob("*")):
        if p.is_file() and not p.name.startswith(("_", "~$")) and "_받는중" not in p.parts:
            out.append({"구분": p.parent.name, "파일": p.name, "크기": p.stat().st_size,
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    return out


def previous_steps(folder: Path) -> dict:
    """지난 실행의 단계 결과 중 정상/없음만(다시 실행할 때 건너뛸 단계). 결과 파일이 없으면 빈 dict(깨졌으면 오류)."""
    p = folder / RESULT
    if not p.exists():
        return {}
    steps = json.loads(p.read_text(encoding="utf-8")).get("단계") or {}
    return {k: v for k, v in steps.items() if v.get("결과") in (OK, NONE)}


def write_results(folder: Path, steps: dict) -> bool:
    """단계 결과 + 증빙 목록 저장. 모든 단계가 정상/없음이면 완료 표시를 쓰고 True."""
    folder.mkdir(parents=True, exist_ok=True)
    rows = listing_rows(folder)
    with open(folder / LISTING, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["구분", "파일", "크기", "sha256"])
        w.writeheader()
        w.writerows(rows)
    done = all(v.get("결과") in (OK, NONE) for v in steps.values())
    body = {"시각": f"{datetime.now():%Y-%m-%d %H:%M}", "단계": steps, "파일 수": len(rows), "완료": done}
    (folder / RESULT).write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
    if done:
        (folder / DONE).write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
    return done
