"""정산 파일 '요청 → 다음날 받기' 작업 기록·계획·목록 대조(순수 로직·오프라인). SSOT=designs/SETTLEMENT_MODULE.md.

쿠팡 정산 엑셀은 바로 받아지지 않고 **요청 후 생성 대기**(실측 2026-10-06: 윙 목록 WAIT→FINISHED, 로켓그로스 목록
'진행중'). 그래서 N일 = 정산 일정(정산캘린더·정산현황 목록) 중 아직 없는 것을 **요청**, N+1일 = 다운로드 목록에서
완료분만 **받기**(파일 이름=계정명·정산일 포함). 차단 위험 완화 규칙(소유자 검토):
- **같은 기간은 한 번만**: 로켓그로스는 같은 매출 주가 70%·30% 두 지급 줄에 나오지만 파일 내용이 같다(실측) →
  키 = (계정, 채널, 리포트, 기간). 윙 최종액(30%)은 기간이 달라(주 묶음) 별도 키.
- **로켓그로스 비용 리포트는 금액이 있는 것만**(판매수수료는 늘): 상세보기에서 0원인 항목은 요청하지 않음.
- **계정당 하루 요청 상한**·오래된 것부터·대기 너무 길면 재요청(최대 횟수 넘으면 실패 — 무한 재시도 금지).
- **윙 월별(최종액) 파일이 나온 달은 그 기간의 주정산 파일을 요청하지 않음**(소유자 2026-10-06). 실측: 8월 주정산 4개를
  이어 붙인 것 = 8월 월별 파일(74줄·25칸·순서까지 동일). 월별 파일만으로 주문 집계·주별 70% 계산이 된다(집계는
  최종액 파일의 '주정산 없는 주' 채움). 과거분 요청 수 약 1/5. 월별이 아직 안 나온 달(정산일 미도래)만 주정산을 받는다.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

ST_PLANNED = "요청예정"
ST_REQUESTED = "요청됨"
ST_DONE = "받음"
ST_FAILED = "실패"
ST_SKIPPED = "생략(월별로 대체)"
RG_ALWAYS = ("판매수수료",)
REQUEST_EXPIRE_DAYS = 3          # 요청 후 이만큼 지나도 완료 안 되면 재요청
MAX_ATTEMPTS = 3
RG_MATCH_WINDOW = timedelta(minutes=10)
_FINISHED = ("FINISHED", "완료", "다운로드가능")


@dataclass(frozen=True)
class SettleEvent:
    """정산 일정 1건(정산캘린더/정산현황 목록 한 줄). reports = 로켓그로스 비용 리포트 중 금액이 0이 아닌 것."""
    account: str
    channel: str
    kind: str                     # 주정산 · 최종액 · 월정산
    settle_date: date
    period_start: date
    period_end: date
    reports: tuple = ()


@dataclass
class Job:
    account: str
    channel: str
    kind: str
    report: str
    period_start: str             # ISO(JSON 저장)
    period_end: str
    settle_date: str
    status: str = ST_PLANNED
    requested_at: str = ""
    attempts: int = 0
    file: str = ""
    note: str = ""

    @property
    def key(self) -> tuple:
        return (self.account, self.channel, self.report, self.period_start, self.period_end)


@dataclass
class DownloadRow:
    """쿠팡 '정산관리 엑셀 다운로드 목록' 한 줄. 윙=메뉴명+검색조건 기간, 로켓그로스=리포트 종류(기간 표시 없음)."""
    channel: str
    requested_at: datetime
    status: str
    report: str = ""
    period_start: date | None = None
    period_end: date | None = None
    handle: object = field(default=None, compare=False)   # 라이브 단계에서 받기 버튼/주소를 들고 다님


def reports_for(ev: SettleEvent) -> list[str]:
    if ev.channel == "윙":
        return ["주문상세"]
    return list(dict.fromkeys([*RG_ALWAYS, *ev.reports]))


def _due(j: Job, now: datetime) -> bool:
    if j.status == ST_PLANNED:
        return True
    return bool(j.status == ST_REQUESTED and j.requested_at
                and now - datetime.fromisoformat(j.requested_at) > timedelta(days=REQUEST_EXPIRE_DAYS))


def plan_requests(events, jobs: list[Job], *, today: date, now: datetime, per_account_cap: int) -> list[Job]:
    """이번에 요청할 작업(오래된 정산일부터·계정당 상한). jobs 를 제자리 갱신(새 작업 추가·만료 재요청·실패 처리)."""
    if per_account_cap < 1:
        raise ValueError("계정당 하루 요청 상한은 1 이상")
    known = {j.key: j for j in jobs}
    finals = _wing_finals(events, today)
    for ev in sorted(events, key=lambda e: (e.settle_date, e.account)):
        if ev.settle_date > today:
            continue                                   # 아직 정산 전 — 파일 없음
        if _covered_by_final(ev.account, ev.channel, ev.kind, ev.period_start, ev.period_end, finals):
            continue                                   # 월별 파일로 대체
        for rep in reports_for(ev):
            j = Job(ev.account, ev.channel, ev.kind, rep, ev.period_start.isoformat(), ev.period_end.isoformat(),
                    ev.settle_date.isoformat())
            if j.key not in known:
                known[j.key] = j
                jobs.append(j)
    picked: list[Job] = []
    used: dict[str, int] = {}
    for j in sorted(jobs, key=lambda j: (j.settle_date, j.account, j.channel, j.report)):
        if j.status == ST_PLANNED and _covered_by_final(
                j.account, j.channel, j.kind, date.fromisoformat(j.period_start), date.fromisoformat(j.period_end),
                finals):
            j.status, j.note = ST_SKIPPED, "그 달 윙 월별(최종액) 파일로 대체 — 요청 안 함"
            continue
        if not _due(j, now):
            continue
        if j.attempts >= MAX_ATTEMPTS:
            j.status, j.note = ST_FAILED, f"{MAX_ATTEMPTS}회 요청해도 완료되지 않음 — 확인 필요"
            continue
        if used.get(j.account, 0) >= per_account_cap:
            continue
        used[j.account] = used.get(j.account, 0) + 1
        picked.append(j)
    return picked


def _wing_finals(events, today: date) -> list[tuple]:
    """받을 수 있는(정산일이 지난) 윙 최종액 일정의 (계정, 기간 시작, 기간 끝)."""
    return [(e.account, e.period_start, e.period_end) for e in events
            if e.channel == "윙" and e.kind == "최종액" and e.settle_date <= today]


def _covered_by_final(account: str, channel: str, kind: str, ps: date, pe: date, finals: list) -> bool:
    """윙 주정산 기간이 같은 계정의 받을 수 있는 월별(최종액) 기간 안에 완전히 들어가면 True."""
    return channel == "윙" and kind != "최종액" and any(
        a == account and fs <= ps and pe <= fe for a, fs, fe in finals)


def mark_requested(j: Job, now: datetime) -> None:
    j.status, j.requested_at, j.attempts = ST_REQUESTED, now.isoformat(timespec="seconds"), j.attempts + 1


_COND = re.compile(r"(\d{4}-\d{2}-\d{2})\s*-\s*(\d{4}-\d{2}-\d{2})")


def parse_condition(text: str) -> tuple[date, date]:
    """윙 목록 검색조건 '구매확정일:2026-08-24 - 2026-08-30' → (시작, 끝). 형식이 다르면 ValueError."""
    m = _COND.search(str(text))
    if not m:
        raise ValueError(f"다운로드 목록 검색조건에서 기간을 못 찾음: {text!r}")
    return date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))


def _match_one(j: Job, rows: list[DownloadRow]) -> tuple[DownloadRow | None, str]:
    req = datetime.fromisoformat(j.requested_at)
    if j.channel == "윙":
        want = (date.fromisoformat(j.period_start), date.fromisoformat(j.period_end))
        cands = [r for r in rows if r.channel == "윙" and (r.period_start, r.period_end) == want
                 and r.requested_at >= req - RG_MATCH_WINDOW]
    else:
        cands = [r for r in rows if r.channel != "윙" and r.report == j.report
                 and req - RG_MATCH_WINDOW <= r.requested_at <= req + RG_MATCH_WINDOW]
    if not cands:
        return None, "목록에 없음"
    if j.channel != "윙" and len(cands) > 1:
        return None, f"같은 리포트 요청이 {len(cands)}건이라 구분 불가 — 건너뜀"
    best = max(cands, key=lambda r: r.requested_at)                   # 같은 기간 여러 번 요청했으면 가장 최근
    return (best, "") if best.status.strip().upper() in _FINISHED else (None, f"아직 {best.status}")


def match_downloads(rows: list[DownloadRow], jobs: list[Job]) -> tuple[list[tuple[Job, DownloadRow]], list[str]]:
    """요청됨 작업 ↔ 다운로드 목록 완료 줄. 반환 (받을 쌍, 사유 로그). 로켓그로스는 목록에 기간이 없어 같은 리포트를
    요청시각 근처에 1건만 요청한 경우에만 짝을 짓는다(받은 뒤 파일 안 정산주기로 한 번 더 확인)."""
    out, notes = [], []
    for j in jobs:
        if j.status != ST_REQUESTED:
            continue
        row, why = _match_one(j, rows)
        if row is None:
            notes.append(f"{j.account} {j.channel} {j.report} {j.period_start}~{j.period_end}: {why}")
        else:
            out.append((j, row))
    return out, notes


# ── 기록 파일 ─────────────────────────────────────────────────────
def load_jobs(path) -> list[Job]:
    p = Path(path)
    if not p.exists():
        return []
    return [Job(**d) for d in json.loads(p.read_text(encoding="utf-8"))]


def save_jobs(path, jobs: list[Job]) -> None:
    """원자적 저장(임시 파일 → 교체) — 중간에 끊겨도 기록이 반쯤 깨지지 않게."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps([asdict(j) for j in jobs], ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)
