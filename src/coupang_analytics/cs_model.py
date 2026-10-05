"""문의/CS 원장 — 열·채널·상태·이벤트 kind 상수, 데이터클래스, 값 정규화·검증·가림. SSOT=designs/DOMAIN_D10_CS.md·IO 05-1.

D10 1단계(수동 트래커). registry_model 평행 — 문의(Inquiry) 1건 + 그에 대한 append 이벤트(진행/보류/재개/완료/
재개방/응대). 상태(접수/진행/보류/완료)는 이벤트 replay(cs_store)로 계산한다('접수'는 문의 존재만으로 기본 상태).
고객 이름·연락처는 개인정보 → 화면·로그 가림(권한자만 원문·열람 기록). 업무일지(D8 11-4)와 혼동 금지(외부 고객 문의만).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .registry_model import canon

SHEET_INQUIRY = "문의"
SHEET_EVENT = "문의이력"
SHEET_ACCESS = "열람기록"
ALL_SHEETS = (SHEET_INQUIRY, SHEET_EVENT, SHEET_ACCESS)

# 문의 유형(IO 05-1)
TYPE_PRODUCT = "상품문의"
TYPE_DELIVERY = "배송"
TYPE_EXCHANGE = "교환반품"
TYPE_ETC = "기타"
INQUIRY_TYPES = (TYPE_PRODUCT, TYPE_DELIVERY, TYPE_EXCHANGE, TYPE_ETC)

# 상태(이벤트 replay 결과) — '접수'는 문의 존재만으로 기본
ST_RECEIVED = "접수"
ST_PROGRESS = "진행"
ST_HOLD = "보류"
ST_DONE = "완료"

# 이벤트 변동유형(append). 응대=상태 안 바꾸고 기록만.
EV_PROGRESS = "진행"
EV_HOLD = "보류"
EV_RESUME = "재개"
EV_DONE = "완료"
EV_REOPEN = "재개방"
EV_REPLY = "응대"
EVENT_KINDS = (EV_PROGRESS, EV_HOLD, EV_RESUME, EV_DONE, EV_REOPEN, EV_REPLY)

# 이벤트 kind → 상태(응대는 없음=상태 유지). cs_store 가 replay 에 사용.
STATE_MAP = {EV_PROGRESS: ST_PROGRESS, EV_HOLD: ST_HOLD, EV_RESUME: ST_PROGRESS,
             EV_DONE: ST_DONE, EV_REOPEN: ST_PROGRESS}

# 개인정보(가림) — 원문은 권한자만. 로그·결과에 원문 금지(IO 05-1 '가려서 표시·열람 기록').
MASKED_INQUIRY = ("고객이름", "연락처")
CS_RAW_ROLES = ("대표", "CS담당")        # (제안) 원문 열람 역할 — 소유자 확정 전 기본값
MASK = "●●●●"

HEADER_INQUIRY = ("문의ID", "접수일시", "판매처", "위탁계정", "상품", "문의유형", "고객이름", "연락처", "문의내용")
HEADER_EVENT = ("번호", "문의ID", "일시", "작성자", "변동유형", "응대내용")
HEADER_ACCESS = ("번호", "일시", "열람자", "문의ID", "항목")
HEADERS = {SHEET_INQUIRY: HEADER_INQUIRY, SHEET_EVENT: HEADER_EVENT, SHEET_ACCESS: HEADER_ACCESS}


class CSError(Exception):
    """문의/CS 입력·원장이 규칙에 맞지 않음(아무것도 쓰지 않음)."""


@dataclass
class Inquiry:
    """문의 1건. 상품·고객이름·연락처는 선택(비우면 계정 전체·익명). 상태는 이벤트 replay(cs_store)."""
    id: str                 # Q-0000
    received: str           # 접수일시 YYYY-MM-DD HH:MM:SS
    marketplace: str        # 판매처
    account_id: str         # 위탁계정
    product: str            # 상품(vid 또는 이름·선택)
    type: str               # 문의유형
    asker_name: str         # 고객이름(가림)
    contact: str            # 연락처(가림)
    content: str            # 문의내용


@dataclass
class Event:
    """문의에 대한 append 이벤트(진행/보류/재개/완료/재개방/응대)."""
    no: int
    inquiry_id: str
    ts: str
    author: str
    kind: str
    note: str = ""          # 응대내용·보류사유 등


@dataclass
class CSLog:
    inquiries: list = field(default_factory=list)   # Inquiry (최신이 위)
    events: list = field(default_factory=list)       # Event

    def inquiry_ids(self) -> set:
        return {q.id for q in self.inquiries}

    def next_event_no(self) -> int:
        return max((e.no for e in self.events), default=0) + 1


# ── 검증 ─────────────────────────────────────────────────────────
def validate_inquiry(marketplace: str, account_id: str, type_: str, content: str) -> None:
    """판매처·위탁계정·문의유형·문의내용 필수(IO 05-1). 상품·이름·연락처는 선택(D10 §1.1·§3.1)."""
    if not str(marketplace).strip():
        raise CSError("문의 '판매처'는 필수입니다")
    if not str(account_id).strip():
        raise CSError("문의 '위탁계정'은 필수입니다")
    if type_ not in INQUIRY_TYPES:
        raise CSError(f"문의 '유형' 값 '{type_}' 은 허용값 아님 — {', '.join(INQUIRY_TYPES)}")
    if not str(content).strip():
        raise CSError("문의 '내용'은 필수입니다")


def validate_event(kind: str, note: str) -> None:
    """변동유형 허용값·보류는 사유 필수(§3.2)."""
    if kind not in EVENT_KINDS:
        raise CSError(f"이벤트 '변동유형' 값 '{kind}' 은 허용값 아님 — {', '.join(EVENT_KINDS)}")
    if kind == EV_HOLD and not str(note).strip():
        raise CSError("보류에는 사유(응대내용)가 필요합니다")


# ── 가림(개인정보) ────────────────────────────────────────────────
def mask_inquiry(inquiry: Inquiry | dict, *, role: str) -> dict:
    """고객이름·연락처를 역할에 맞게 가린다 — CS_RAW_ROLES 만 원문, 그 외 ●●●●(값 있을 때만).
    순수 함수(I/O 없음) — 원문 열람 시 열람 기록은 호출부(cs_gsheet.record_access) 책임."""
    d = inquiry if isinstance(inquiry, dict) else {
        "문의ID": inquiry.id, "접수일시": inquiry.received, "판매처": inquiry.marketplace,
        "위탁계정": inquiry.account_id, "상품": inquiry.product, "문의유형": inquiry.type,
        "고객이름": inquiry.asker_name, "연락처": inquiry.contact, "문의내용": inquiry.content}
    out = dict(d)
    if role not in CS_RAW_ROLES:
        for f in MASKED_INQUIRY:
            if str(out.get(f, "")).strip():
                out[f] = MASK
    return out


def canon_value(v) -> str:
    """표기 정규화(날짜·숫자) — 저장 비교 안정. 문의내용 등 글자는 공백만 정리."""
    return canon(v)
