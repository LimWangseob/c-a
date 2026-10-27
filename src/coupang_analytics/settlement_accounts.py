"""정산 다운로드 입력 = 소유자가 주는 계정 파일(텍스트: 계정ID · 비번 · 대표자-사업자) — 관리대장 대신(2026-10-06).

정산은 관리대장(추적 상품) 계정보다 넓은 **위탁 계정 전부**가 대상이라 소유자 파일을 입력으로 쓴다.
파일 모양(실측 '샵마인 계정리스크.txt'): 한 줄 = `계정ID <공백/탭> 비번 <공백/탭> 대표자-사업자`. 구분 공백·탭이 섞이고
뒤 공백이 있으며, 3열이 비어 있거나 **비번이 한 번 더 적힌 줄**이 있다.
- 3열이 비번과 같으면 이름 없음으로 처리 — 비번이 파일 이름·기록에 섞이지 않게(가장 중요).
- 이름 없으면 표시명 = 계정ID. 같은 계정ID 가 두 줄이면 오류(어느 비번이 맞는지 추측하지 않음).
- 경고·오류 글에는 **비번 값을 절대 넣지 않는다**(줄 번호·계정ID 만).
비번은 읽은 즉시 이 PC 의 암호 저장소(credstore·DPAPI)에 넣고, 로그인은 거기서 꺼낸다(파일은 소유자가 관리).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PATH = "data/정산_계정목록.txt"     # 운용 PC: coupang-analytics\data\ (업데이트 덮어쓰기에도 보존·git 제외)
CONFIG_KEY = "settlement/accounts_file"


class AccountsFileError(Exception):
    """계정 파일을 쓸 수 없음(없음·형식·중복) — 정산 실행 중단."""


@dataclass
class SettleAccount:
    account_id: str
    label: str                                   # 대표자-사업자(없으면 계정ID) — 파일 이름·기록에 씀
    password: str = field(repr=False)            # repr 에 안 나오게(로그 실수 방지)


def parse_accounts_text(text: str) -> tuple[list[SettleAccount], list[str]]:
    """계정 파일 글자 → (계정 목록, 경고). 빈 줄·'#'으로 시작하는 주석 줄 무시. 2열(비번) 없는 줄·중복 계정ID = AccountsFileError."""
    out: list[SettleAccount] = []
    warns: list[str] = []
    seen: dict[str, int] = {}
    for n, line in enumerate(text.splitlines(), start=1):
        tok = line.split()
        if not tok or tok[0].startswith("#"):
            continue                                 # 빈 줄·'#' 주석 줄(사용 안 함 계정 막아 두기·2026-10-12)
        if len(tok) < 2:
            raise AccountsFileError(f"{n}번째 줄({tok[0]}): 비밀번호 칸이 없음")
        aid, pw, name = tok[0], tok[1], " ".join(tok[2:])
        if aid in seen:
            raise AccountsFileError(f"계정ID {aid} 가 {seen[aid]}·{n}번째 줄에 두 번 있음 — 어느 줄이 맞는지 정해 주세요")
        seen[aid] = n
        if name == pw or pw in name:
            warns.append(f"{n}번째 줄({aid}): 3열이 비밀번호와 같아 이름 없음으로 처리(표시명=계정ID)")
            name = ""
        elif not name:
            warns.append(f"{n}번째 줄({aid}): 대표자-사업자 칸 비어 있음(표시명=계정ID)")
        out.append(SettleAccount(aid, name or aid, pw))
    if not out:
        raise AccountsFileError("계정이 한 줄도 없음")
    return out, warns


def read_accounts_file(path) -> tuple[list[SettleAccount], list[str]]:
    p = Path(path)
    if not p.exists():
        raise AccountsFileError(f"정산 계정 파일이 없음: {p} — 계정ID·비번·대표자-사업자 파일을 여기에 두세요")
    try:
        text = p.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AccountsFileError(f"{p.name}: UTF-8 이 아님 — 메모장 '다른 이름으로 저장 → 인코딩 UTF-8' 로 저장해 주세요") from exc
    return parse_accounts_text(text)


def login_passwords(a: SettleAccount, store=None) -> tuple[list[str], str]:
    """정산 로그인에 넣을 비밀번호 후보·출처 설명(값은 설명에 안 씀). 소유자 2026-10-16: **앱처럼 관리대장 비밀번호로** —
    앱이 관리대장을 읽을 때마다 이 PC 암호 저장소(credstore·DPAPI)에 계정ID별로 저장한 값을 먼저 쓴다. 관리대장에 없는
    계정(정산만 하는 계정)은 원장 값(D-103 — 옛 정산 계정 파일 대신). 두 값이 다르면 대장 → 원장 순서로 최대 2개(D-012 와
    같은 상한·거부된 값은 24시간 다시 넣지 않음 D-068·D-123). 앞뒤 공백은 떼고 비교(원장 = 대장 원문 그대로 — D-123)."""
    if store is None:
        from .credstore import CredStore
        store = CredStore()
    ledger, file_pw = (store.get_password(a.account_id) or "").strip(), (a.password or "").strip()
    pws = list(dict.fromkeys(p for p in (ledger, file_pw) if p))
    if not pws:
        return [], "비밀번호 없음"
    if not ledger:
        return pws, "관리대장에 없음 — 원장 값"
    if file_pw and file_pw != ledger:
        return pws, "관리대장·원장 값이 다름 — 관리대장 먼저(거부되면 원장 값 1회)"
    return pws, "관리대장"


def display_name(a: SettleAccount) -> str:
    """파일 이름·기록의 계정명 = '대표자-사업자-계정ID'(계정ID 로 끝나 이름이 바뀌어도 같은 계정을 찾을 수 있음)."""
    return f"{a.label}-{a.account_id}"


def renames(old_names, accounts: list[SettleAccount], tok=lambda s: s) -> dict:
    """예전 계정명(관리대장 기준 '(주)웰빙곳간-wellbing1107' 등) → 지금 계정명. 끝이 '-계정ID' 인 것만(가장 긴 ID 우선).
    tok = 파일 이름 글자 규칙(settlement_files._token)을 같이 적용할 때."""
    out = {}
    by_len = sorted(accounts, key=lambda a: -len(a.account_id))
    for old in set(old_names):
        a = next((a for a in by_len if old.endswith("-" + tok(a.account_id))), None)
        if a is not None and old != tok(display_name(a)):
            out[old] = tok(display_name(a))
    return out


# ── 정산 계정 출처 = 셀독계정상품이력관리원장(D-103) ─────────────────────────────
KEEP_DAYS = 90        # 관리중단 뒤에도 남은 정산(로켓그로스 월정산·지급 보류 등)을 받는 기간
SYNC_MAX_AGE_H = 26   # 원장 마지막 동기화가 이보다 오래면 정산 계정 구성 중단(18:00 실행이 하루 한 번 동기화)


class AccountSourceError(Exception):
    """원장에서 정산 계정을 만들 수 없음(동기화 오래됨·링크 오류 등) — 옛 계정 파일로 대신하지 않고 정산 중단."""


def last_sync_time(sync_values: list) -> str:
    """'동기화기록' 값 격자(최신이 위) → 가장 최근 실행일시('YYYY-MM-DD HH:MM:SS'·없으면 '')."""
    if len(sync_values) < 2:
        return ""
    head = [str(h).strip() for h in sync_values[0]]
    i = head.index("실행일시") if "실행일시" in head else 1
    times = [str(r[i]).strip() for r in sync_values[1:] if len(r) > i and str(r[i]).strip()]
    return max(times, default="")


def accounts_from_registry(reg, settle_rows: dict, last_sync: str, now, keep_days: int = KEEP_DAYS,
                           max_age_h: int = SYNC_MAX_AGE_H) -> tuple[list[SettleAccount], dict]:
    """원장 → 정산 계정 [SettleAccount] + 구성 요약. 대상 = (셀독원장) 최근 keep_days 일 안에 하루라도 관리한 계정
    (관리중 + 관리중단 뒤 keep_days 일 이내) − 오입력 + (정산전용계정) 관리중 또는 중단일이 keep_days 일 이내.
    비밀번호 = 원장 값(셀독원장 = 매일 관리대장에서 반영). 원장 동기화가 max_age_h 시간보다 오래면 AccountSourceError."""
    from datetime import datetime as _dt, timedelta
    from .registry_history import managed_between
    from .registry_model import valid_account_id
    if not last_sync:
        raise AccountSourceError("원장 동기화 기록이 없음 — 설정 탭 원장 링크·18:00 실행 확인(옛 정산 계정 파일로 대신하지 않음)")
    age = now - _dt.fromisoformat(last_sync)
    if age > timedelta(hours=max_age_h):
        raise AccountSourceError(f"원장 마지막 동기화 {last_sync} — {max_age_h}시간이 넘음(원장 링크가 바뀌었거나 18:00 실행이 "
                                 "안 됨). 설정 탭 원장 링크 확인 후 다시 실행(옛 정산 계정 파일로 대신하지 않음)")
    start = (now - timedelta(days=keep_days)).strftime("%Y-%m-%d")
    mistaken = reg.mistaken_ids()
    picked = [a for a in managed_between(reg, start, now.strftime("%Y-%m-%d")) if a not in mistaken and valid_account_id(a)]
    out = []
    for aid in picked:
        acct = reg.account_rows(aid)[0].acct
        name = "-".join(x for x in (acct.get("대표자명", ""), acct.get("사업자명", "")) if x)
        out.append(SettleAccount(aid, name or aid, acct.get("비밀번호", "")))
    dup, settle_n = [], 0
    for aid, row in settle_rows.items():
        if aid in picked:
            dup.append(aid)
            continue
        if row.active or (row.fields.get("중단일", "") or "9999") >= start:
            out.append(SettleAccount(aid, row.label or aid, row.fields.get("비밀번호", "")))
            settle_n += 1
    info = {"원장 동기화": last_sync, "셀독원장": len(picked), "정산전용": settle_n,
            "오입력 제외": len(mistaken), "중복(셀독원장 우선)": dup}
    return out, info
