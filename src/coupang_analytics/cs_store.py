"""문의/CS 원장 — 자료구조 파싱·상태 replay·통계·무결성(순수 로직). SSOT=designs/DOMAIN_D10_CS.md §3.

registry_core+history 평행. I/O 없음(구글시트 입출력은 cs_gsheet). 상태는 이벤트를 시간순 replay 해 계산하고
('접수'가 기본·응대는 상태를 바꾸지 않음), 번호 연속·문의ID 참조 무결성을 점검한다.
"""
from __future__ import annotations

import re

from .cs_model import (SHEET_EVENT, SHEET_INQUIRY, ST_DONE, ST_RECEIVED, STATE_MAP, CSError, CSLog, Event,
                       Inquiry)

_QID = re.compile(r"Q-(\d+)")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


# ── 파싱(격자 → 자료구조) ────────────────────────────────────────
def _cellmap(header: list, row: list) -> dict:
    return {h: (row[i] if i < len(row) else "") for i, h in enumerate(header)}


def _inquiry_from(d: dict) -> Inquiry:
    return Inquiry(id=str(d.get("문의ID", "")), received=str(d.get("접수일시", "")),
                   marketplace=str(d.get("판매처", "")), account_id=str(d.get("위탁계정", "")),
                   product=str(d.get("상품", "")), type=str(d.get("문의유형", "")),
                   asker_name=str(d.get("고객이름", "")), contact=str(d.get("연락처", "")),
                   content=str(d.get("문의내용", "")))


def _event_from(d: dict) -> Event:
    raw_no = str(d.get("번호", "")).strip()
    try:
        no = int(raw_no)
    except ValueError as exc:
        raise CSError(f"문의이력 '번호' 칸이 숫자가 아님: '{raw_no}'") from exc
    return Event(no=no, inquiry_id=str(d.get("문의ID", "")), ts=str(d.get("일시", "")),
                 author=str(d.get("작성자", "")), kind=str(d.get("변동유형", "")), note=str(d.get("응대내용", "")))


def parse_log(grids: dict) -> CSLog:
    """{시트명: 값격자} → CSLog. 헤더는 이름으로 찾는다(열 순서 변경 내성). 빈 줄 건너뜀."""
    log = CSLog()
    iq = grids.get(SHEET_INQUIRY) or []
    for row in iq[1:]:
        d = _cellmap([str(h) for h in iq[0]], row)
        if str(d.get("문의ID", "")).strip():
            log.inquiries.append(_inquiry_from(d))
    ev = grids.get(SHEET_EVENT) or []
    for row in ev[1:]:
        if any(str(c).strip() for c in row):
            log.events.append(_event_from(_cellmap([str(h) for h in ev[0]], row)))
    return log


# ── 상태 replay ──────────────────────────────────────────────────
def _events_of(log: CSLog, inquiry_id: str) -> list[Event]:
    return sorted((e for e in log.events if e.inquiry_id == inquiry_id), key=lambda e: (e.ts, e.no))


def status_of(log: CSLog, inquiry_id: str) -> str:
    """문의 현재 상태 — '접수'에서 시작해 상태 이벤트(진행/보류/재개/완료/재개방)를 시간순 적용(응대는 무시)."""
    st = ST_RECEIVED
    for e in _events_of(log, inquiry_id):
        st = STATE_MAP.get(e.kind, st)
    return st


def open_inquiries(log: CSLog, *, account_id: str | None = None) -> list[Inquiry]:
    """미완료(완료 아님) 문의 — 방치 조망용. account_id 주면 그 계정만."""
    return [q for q in log.inquiries
            if status_of(log, q.id) != ST_DONE and (account_id is None or q.account_id == account_id)]


# ── 통계 ─────────────────────────────────────────────────────────
def _done_ts(log: CSLog, inquiry_id: str) -> str | None:
    done = [e for e in _events_of(log, inquiry_id) if STATE_MAP.get(e.kind) == ST_DONE]
    return done[-1].ts if done else None


def _days(a: str, b: str) -> int | None:
    from datetime import date
    if not (_ISO_DATE.match(a) and _ISO_DATE.match(b)):
        return None
    da = date.fromisoformat(a[:10])
    db = date.fromisoformat(b[:10])
    return (db - da).days


def stats(log: CSLog, start: str, end: str) -> dict:
    """기간(접수일 기준 start~end 포함) CS 지표 — 접수/완료/보류 건수·평균 처리일·보류율·계정별 건수."""
    sel = [q for q in log.inquiries if start <= q.received[:10] <= end]
    received = len(sel)
    done = [q for q in sel if status_of(log, q.id) == ST_DONE]
    held = sum(1 for q in sel if status_of(log, q.id) == "보류")
    spans = [d for q in done if (dt := _done_ts(log, q.id)) and (d := _days(q.received, dt)) is not None]
    by_account: dict[str, int] = {}
    for q in sel:
        by_account[q.account_id] = by_account.get(q.account_id, 0) + 1
    return {"접수": received, "완료": len(done), "보류": held,
            "평균처리일": round(sum(spans) / len(spans), 1) if spans else None,
            "보류율": round(held / received, 3) if received else 0.0,
            "계정별": by_account}


# ── 무결성 ───────────────────────────────────────────────────────
def check_integrity(log: CSLog) -> None:
    """이력 번호 1..n 연속 · 모든 이벤트의 문의ID 가 문의 명부에 존재(지우지 않고 추가만)."""
    nos = sorted(e.no for e in log.events)
    if nos != list(range(1, len(nos) + 1)):
        raise CSError(f"문의이력 번호가 1..n 연속이 아님(누락/중복): {nos[:10]}")
    ids = log.inquiry_ids()
    orphan = sorted({e.inquiry_id for e in log.events} - ids)
    if orphan:
        raise CSError(f"문의이력에 명부에 없는 문의ID: {orphan[:10]}")


# ── ID 할당 ──────────────────────────────────────────────────────
def next_inquiry_id(log: CSLog) -> str:
    nums = [int(m.group(1)) for q in log.inquiries if (m := _QID.fullmatch(q.id))]
    return f"Q-{max(nums, default=0) + 1:04d}"
