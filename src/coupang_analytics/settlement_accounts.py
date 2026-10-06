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
    """계정 파일 글자 → (계정 목록, 경고). 빈 줄 무시. 2열(비번) 없는 줄·중복 계정ID = AccountsFileError."""
    out: list[SettleAccount] = []
    warns: list[str] = []
    seen: dict[str, int] = {}
    for n, line in enumerate(text.splitlines(), start=1):
        tok = line.split()
        if not tok:
            continue
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
