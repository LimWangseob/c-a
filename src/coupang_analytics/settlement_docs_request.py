"""정산 요청형 월자료(D-171 N8 · D-170 회차 예산) — 부가세 신고 상세(윙·로켓그로스)를 '요청 → 생성 대기 → 받기'로.

designs/SETTLEMENT_MODULE.md §16-2 N8. 요청·목록·받기는 정산 파일과 같은 주소·같은 기록(`_요청기록.json` · 유형 '월자료').
소급 단계(cmd_backfill)가 계획·요청하고, 다음 바퀴 정기 단계의 받기(cmd_download)가 완료분을 받아 여기 `keep` 으로 판정·저장.
실측(gyi0101 2026-11-08 · 소유자 로그인 Chrome · 조회만 — 요청 버튼 안 누름):
| 종류 | 요청(화면 JS) | 목록 | 파일 |
|---|---|---|---|
| 윙부가세상세 | POST …/excel/revenue-detail/request `{excelType:"MSF_PAYMENT_METHOD_DETAIL", recognitionDateRange·searchDateRange(그 달), searchDateType:"CONFIRM_DATE"}` | 윙 목록 excelType 같음·조건 '구매확정일:YYYY-MM-01 - 말일' | 시트 1·머리글 1행 11칸(2번째 머리글 빈칸)·환불 **양수** |
| RG부가세상세 | POST /tenants/rfm/v2/settlements/request-download/api(화면 `requestSellerReport` = excel-store) `{sellerReportType:"VAT", requestTime, recognitionDateFrom:전달 말일T15:00:00.000Z, recognitionDateTo:말일T14:59:59.999Z, locale}` | RG 목록 requestId 로 짝 | 시트 '부가세 신고자료'·머리글 2행째·환불 **음수**·빈 금액 '-' |
- 화면 월 합계(검증 원자료 wing_vat·rg_vat) = 판매 + 환불(파일 부호 그대로) [사실: 2026-01 카드·현금·기타 일치] · RG '기타' 는 판매자 쿠폰을 더한 값.
- 상품별 사이즈 리포트(N11)는 여기 없음 — 목록 완료본에 기간·정산 키가 없고(실측 3건) 요청 화면을 RG 화면 JS 257개에서 못 찾음 → 미확인.
"""
from __future__ import annotations

import io
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

from .settlement_docs import months_after
from .settlement_jobs import DOC_KIND, MAX_ATTEMPTS, ST_DONE, ST_FAILED, Job, _due, mark_requested
from .settlement_wing_api import (RG_REQUEST, WING_REQUEST, RequestThrottled, SiteChangedError, rg_request_id,
                                  wing_request_id)

WING_VAT, RG_VAT = "윙부가세상세", "RG부가세상세"
CHANNEL = {WING_VAT: "윙", RG_VAT: "로켓그로스"}
VAT_BUDGET = 4                    # 회차(18:00~) 계정당 부가세 상세 요청 수(D-170)
LAG_DAYS = 15                     # 말일 + 며칠 뒤부터 요청 [추정 — 세금계산서와 같은 값]
WING_HEAD = ("주문번호", "", "매출인식일", "항목유형", "과세유형", "신용카드(판매)", "현금(판매)", "기타(판매)", "신용카드(환불)",
             "현금(환불)", "기타(환불)")
RG_HEAD = ("주문번호", "옵션ID", "결제완료일", "매출인식월", "과세유형", "신용/체크카드(판매)", "현금(판매)", "기타(판매)",
           "신용/체크카드(환불)", "현금(환불)", "기타(환불)")
RG_SHEET = "부가세 신고자료"
PAY = ("카드", "현금", "기타")


# ── 계획·요청 ─────────────────────────────────────────────────────
def plan(jobs: list[Job], account: str, today: date, now: datetime, since: str, rg: bool) -> list[Job]:
    """이번에 요청할 부가세 상세(최근 달부터 · 회차 since 이후 이미 요청한 수를 빼고 VAT_BUDGET 까지). jobs 를 제자리 갱신
    (새 달 추가·MAX_ATTEMPTS 넘은 것 실패 처리). RG 는 로켓그로스 계정(업체코드 있음)만. 받음·실패·생성 대기 중(3일 안)은 안 고름."""
    reports = [WING_VAT] + ([RG_VAT] if rg else [])
    known = {j.key for j in jobs}
    for rep in reports:
        for _ym, f, t in months_after(LAG_DAYS, today):
            j = Job(account, CHANNEL[rep], DOC_KIND, rep, f.isoformat(), t.isoformat(), t.isoformat())
            if j.key not in known:
                known.add(j.key)
                jobs.append(j)
    mine = [j for j in jobs if j.account == account and j.kind == DOC_KIND and j.report in reports]
    left = VAT_BUDGET - sum(1 for j in mine if since and j.requested_at >= since)
    picked: list[Job] = []
    for j in sorted(mine, key=lambda j: (j.period_start, j.report), reverse=True):
        if j.status in (ST_DONE, ST_FAILED) or not _due(j, now):
            continue
        if j.attempts >= MAX_ATTEMPTS:
            j.status, j.note = ST_FAILED, f"{MAX_ATTEMPTS}회 요청해도 완료되지 않음 — 확인 필요"
            continue
        if len(picked) < left:
            picked.append(j)
    return picked


def wing_body(j: Job) -> dict:
    rng = {"start": j.period_start, "end": j.period_end}
    return {"excelType": "MSF_PAYMENT_METHOD_DETAIL", "recognitionDateRange": rng, "searchDateType": "CONFIRM_DATE",
            "searchDateRange": dict(rng)}


def rg_body(j: Job, now_ms: int) -> dict:
    """화면과 같은 모양 — 한국 그 달 1일 0시 ~ 말일 24시를 UTC 로(1일 0시 KST = 전날 15시 UTC)."""
    f = date.fromisoformat(j.period_start)
    return {"sellerReportType": "VAT", "requestTime": str(now_ms), "recognitionDateFrom": f"{f - timedelta(days=1)}T15:00:00.000Z",
            "recognitionDateTo": f"{j.period_end}T14:59:59.999Z", "locale": "ko"}


def request(picked: list[Job], post, *, save, record, gap=lambda: None, now=datetime.now) -> int:
    """picked 를 차례로 요청 → 요청 수. post(method, path, body) = 페이지 안 호출(JSON). record(job, 결과, 사유) =
    처리기록('정상'·'대기'·'실패'). 쿠팡 '잠시 후' = 이 계정 이번 회차 멈춤 · 거절·응답 모양 다름 = 기록하고 멈춤(근거 자료라
    정산 전체를 막지 않음 — D-120 격리) · 차단은 호출부 예외 그대로 올라감."""
    n = 0
    for k, j in enumerate(picked):
        if k:
            gap()
        try:
            if j.channel == "윙":
                rid = wing_request_id(post("POST", WING_REQUEST, wing_body(j)))
            else:
                rid = rg_request_id(post("POST", RG_REQUEST, rg_body(j, int(now().timestamp() * 1000))))
        except RequestThrottled as exc:
            record(j, "대기", f"{exc} — 남은 월자료 요청은 다음 회차에")
            break
        except SiteChangedError as exc:
            record(j, "실패", f"월자료 요청 실패: {str(exc)[:150]}")
            break
        mark_requested(j, now(), rid)
        save()
        record(j, "정상", f"월자료 요청함(요청번호 {rid})")
        n += 1
    return n


# ── 받은 파일 판정·저장 ───────────────────────────────────────────
def _num(v) -> float:
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _rows(body: bytes, sheet: str | None, head: tuple) -> list[tuple]:
    """시트(없으면 첫 시트)에서 머리글 줄(head 와 같음)을 찾아 그 아래 빈 줄 아닌 줄들. 열리지 않거나 머리글이 다르면 SiteChangedError."""
    import openpyxl
    try:
        wb = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 — 열리지 않으면 받은 게 아님(어떤 형식 오류든 같은 판정)
        raise SiteChangedError(f"부가세 상세 엑셀이 열리지 않음: {exc.__class__.__name__}") from exc
    try:
        name = sheet or wb.sheetnames[0]
        if name not in wb.sheetnames:
            raise SiteChangedError(f"부가세 상세 시트 '{name}' 없음: {wb.sheetnames}")
        grid = [tuple("" if c is None else c for c in r) for r in wb[name].iter_rows(values_only=True)]
    finally:
        wb.close()
    at = next((i for i, r in enumerate(grid[:5]) if tuple(str(c).strip() for c in r[:len(head)]) == head), None)
    if at is None:
        raise SiteChangedError(f"부가세 상세 머리글이 예상과 다름: {[r[:6] for r in grid[:3]]}")
    return [r for r in grid[at + 1:] if any(c != "" for c in r)]


def check(report: str, body: bytes, f: date, t: date) -> dict:
    """부가세 상세 파일 → {줄, 판매·환불·합계(카드·현금·기타)}. 머리글·기간(윙 매출인식일·RG 매출인식월)이 그 달 아니면 SiteChangedError.
    합계 = 판매 + 환불(파일 부호 그대로 — 윙 환불 양수·RG 환불 음수) = 화면 월 합계(실측)."""
    if report == WING_VAT:
        rows, when, ok = _rows(body, None, WING_HEAD), 2, (lambda v: f.isoformat() <= str(v)[:10] <= t.isoformat())
    elif report == RG_VAT:
        rows, when, ok = _rows(body, RG_SHEET, RG_HEAD), 3, (lambda v: str(v)[:7] == f"{f:%Y-%m}")
    else:
        raise SiteChangedError(f"모르는 월자료 종류: {report}")
    bad = [r[when] for r in rows if not ok(r[when])]
    if bad:
        raise SiteChangedError(f"{report} {f:%Y%m} 파일에 다른 달 줄 {len(bad)}개(예: {bad[0]!r})")
    sale = {p: round(sum(_num(r[5 + i]) for r in rows)) for i, p in enumerate(PAY)}
    refund = {p: round(sum(_num(r[8 + i]) for r in rows)) for i, p in enumerate(PAY)}
    return {"줄": len(rows), "판매": sale, "환불": refund, "합계": {p: sale[p] + refund[p] for p in PAY}}


def reference(report: str, verify: dict, ym: str) -> dict | None:
    """검증 원자료(하루 1번 화면 월 합계) → 그 달 {카드·현금·기타}. RG 기타 = 화면 기타 − 판매자 쿠폰. 없으면 None."""
    if report == WING_VAT:
        for r in (verify.get("wing_vat") or {}).get("paymentMethodReports") or []:
            if str(r.get("yearMonth")) == ym:
                return {"카드": round(r["card"]), "현금": round(r["cash"]), "기타": round(r["etc"])}
        return None
    for r in (verify.get("rg_vat") or {}).get("vatResponseAggregatedDtos") or []:
        if str(r.get("yearMonth")) == f"{ym[:4]}-{ym[4:]}":
            return {"카드": round(r["creditCardPaymentAmountAgg"]), "현금": round(r["cashPaymentAmountAgg"]),
                    "기타": round(r["otherPaymentAmountAgg"] - (r.get("sellerFundedCouponAggAmount") or 0))}
    return None


def keep(body: bytes, j: Job, folder: Path, verify_path: Path) -> tuple[bool, str]:
    """받은 부가세 상세 → 판정(check) → `{folder}/{종류}_{YYYYMM}.xlsx` 저장 · 작업 '받음' · 화면 월 합계와 대조.
    반환 (합계가 맞거나 대조 자료가 없음, 기록 문구). 칸·기간이 다르면 SiteChangedError(저장 안 함 — 호출부가 그 파일만 실패 기록).
    합계가 다르면 파일은 남기고(원인 확인용) False — 호출부가 '실패'로 기록."""
    f, t = date.fromisoformat(j.period_start), date.fromisoformat(j.period_end)
    ym = f"{f:%Y%m}"
    got = check(j.report, body, f, t)
    verify = json.loads(verify_path.read_text(encoding="utf-8")) if verify_path.exists() else {}
    ref = reference(j.report, verify, ym)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{j.report}_{ym}.xlsx"
    tmp = folder / (name + ".tmp")
    tmp.write_bytes(body)
    os.replace(tmp, folder / name)
    j.status, j.file = ST_DONE, f"월자료/{folder.name}/{name}"
    sums = " · ".join(f"{p} {got['합계'][p]:,}" for p in PAY)
    if ref is None:
        j.note = "화면 월 합계 없음 — 대조 못 함"
        return True, f"{name} · 줄 {got['줄']} · {sums} · {j.note}"
    diff = {p: got["합계"][p] - ref[p] for p in PAY if got["합계"][p] != ref[p]}
    j.note = "화면 월 합계와 일치" if not diff else f"화면 월 합계와 다름 {diff} — 확인 필요"
    return not diff, f"{name} · 줄 {got['줄']} · {sums} · {j.note}"
