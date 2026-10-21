"""셀독계정상품이력관리원장 — 정산 전용 계정(관리대장에 없는 위탁·우리 사업자 계정) 시트와 그 변경이력(D-103).

관리대장에 없어 원장(셀독원장)에 들어오지 않는 정산 대상 계정(정산만 하는 위탁계정·우리 사업자 디프·디프픽)을 같은 원장
파일의 '정산전용계정' 시트에 둔다. 이 시트는 **사람이 편집**하고, 앱은 매 동기화 때 시트를 직전 상태(이력 재생)와 비교해
바뀐 점을 '정산전용이력'에 **추가만** 한다(셀독원장 무결성 점검과는 분리 — 옛 원장도 그대로 동작).
비밀번호 원문은 원장 파일 예외(LEDGER_REGISTRY §9)와 같은 수준 — 로그에는 값 대신 '(값 생략)'.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .registry_model import ST_ACTIVE, ST_STOPPED, canon, canon_pw, valid_account_id

SHEET_SETTLE = "정산전용계정"
SHEET_SETTLE_HIST = "정산전용이력"
SETTLE_SHEETS = (SHEET_SETTLE, SHEET_SETTLE_HIST)
SETTLE_HEADER = ("관리상태", "시작일", "중단일", "구분", "대표자명", "사업자명", "계정아이디", "비밀번호", "비고")
SETTLE_FIELDS = ("관리상태", "시작일", "중단일", "구분", "대표자명", "사업자명", "비밀번호", "비고")
SETTLE_HIST_HEADER = ("번호", "일시", "효력일", "계정아이디", "사업자명", "변동유형", "항목", "이전값", "변경값", "비고")
KINDS = ("위탁", "우리사업자")
K_NEW, K_EDIT, K_GONE = "신규계정", "수정", "목록에서 삭제"


class SettleSheetError(Exception):
    """정산전용계정 시트를 쓸 수 없음(같은 계정ID 두 줄 등) — 동기화·정산 계정 구성 중단."""


@dataclass
class SettleRow:
    account_id: str
    fields: dict = field(default_factory=dict)      # SETTLE_FIELDS → 값(문자열)

    @property
    def active(self) -> bool:
        return self.fields.get("관리상태", "") != ST_STOPPED

    @property
    def label(self) -> str:
        return "-".join(x for x in (self.fields.get("대표자명", ""), self.fields.get("사업자명", "")) if x)


def parse_settle(values: list) -> tuple[dict, list]:
    """'정산전용계정' 값 격자 → ({계정아이디: SettleRow}, 경고). 빈 줄 무시 · 형식 오류 계정ID 는 빼고 경고(값은 안 씀) ·
    같은 계정ID 두 줄 = SettleSheetError(어느 줄이 맞는지 사람이 정함)."""
    if not values:
        return {}, []
    head = [canon(h) for h in values[0]]
    missing = [h for h in SETTLE_HEADER if h not in head]
    if missing:
        raise SettleSheetError(f"'{SHEET_SETTLE}' 머리줄에 칸이 없음: {missing}")
    out, warns = {}, []
    for n, row in enumerate(values[1:], start=2):
        cell = {h: (canon_pw(row[i]) if h == "비밀번호" else canon(row[i])) if i < len(row) else ""
                for h, i in ((h, head.index(h)) for h in SETTLE_HEADER)}
        aid = cell.pop("계정아이디")
        if not aid:
            continue
        if not valid_account_id(aid):
            warns.append(f"{SHEET_SETTLE} {n}행 계정아이디 형식 오류(영문·숫자 아님) → 제외")
            continue
        if aid in out:
            raise SettleSheetError(f"{SHEET_SETTLE}: 계정아이디 {aid} 가 두 줄 — 하나만 남겨 주세요")
        if cell["관리상태"] not in ("", ST_ACTIVE, ST_STOPPED):
            warns.append(f"{SHEET_SETTLE} {n}행 {aid} 관리상태 '{cell['관리상태']}' — 관리중/관리중단만(관리중으로 봄)")
        out[aid] = SettleRow(aid, cell)
    return out, warns


def replay(history_values: list) -> dict:
    """'정산전용이력' 값 격자(최신이 위) → 이력을 오래된 것부터 적용한 직전 상태 {계정아이디: {항목: 값}}."""
    if len(history_values) < 2:
        return {}
    head = [canon(h) for h in history_values[0]]
    ix = {h: head.index(h) for h in SETTLE_HIST_HEADER if h in head}
    rows = [r for r in history_values[1:] if r and len(r) > ix["번호"] and str(r[ix["번호"]]).strip()]
    rows.sort(key=lambda r: int(str(r[ix["번호"]]).strip()))
    state: dict = {}

    def get(r, h):
        return str(r[ix[h]]) if ix[h] < len(r) else ""
    for r in rows:
        aid, kind = get(r, "계정아이디"), get(r, "변동유형")
        if kind == K_NEW:
            state[aid] = {}
        elif kind == K_EDIT:
            state.setdefault(aid, {})[get(r, "항목")] = get(r, "변경값")
        elif kind == K_GONE:
            state.pop(aid, None)
    return state


def diff(prev: dict, cur: dict) -> list[tuple]:
    """직전 상태 vs 지금 시트 → 이력 줄 재료 [(계정아이디, 사업자명, 변동유형, 항목, 이전값, 변경값)]."""
    out = []
    for aid, row in cur.items():
        old = prev.get(aid)
        if old is None:
            out.append((aid, row.fields.get("사업자명", ""), K_NEW, "", "", ""))
            old = {}
        for f in SETTLE_FIELDS:
            if old.get(f, "") != row.fields.get(f, ""):
                out.append((aid, row.fields.get("사업자명", ""), K_EDIT, f, old.get(f, ""), row.fields.get(f, "")))
    for aid, old in prev.items():
        if aid not in cur:
            out.append((aid, old.get("사업자명", ""), K_GONE, "", "", ""))
    return out


def ensure_sheets(client, log=None) -> bool:
    """두 시트가 없으면 만들고 머리줄·드롭다운(관리상태·구분)을 건다. 새로 만들었으면 True."""
    titles = client.sheet_titles()
    if all(s in titles for s in SETTLE_SHEETS):
        return False
    ids = client.ensure_sheets(list(SETTLE_SHEETS))
    for s, head in ((SHEET_SETTLE, SETTLE_HEADER), (SHEET_SETTLE_HIST, SETTLE_HIST_HEADER)):
        if not client.read_values(s):
            client.write_values(s, [list(head)], raw=True)
    reqs = [{"updateSheetProperties": {"properties": {"sheetId": ids[s], "gridProperties": {"frozenRowCount": 1}},
                                       "fields": "gridProperties.frozenRowCount"}} for s in SETTLE_SHEETS]
    for col, values in ((0, (ST_ACTIVE, ST_STOPPED)), (3, KINDS)):
        reqs.append({"setDataValidation": {
            "range": {"sheetId": ids[SHEET_SETTLE], "startRowIndex": 1, "startColumnIndex": col, "endColumnIndex": col + 1},
            "rule": {"condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": v} for v in values]},
                     "strict": False, "showCustomUi": True}}})
    reqs.append({"addProtectedRange": {"protectedRange": {
        "range": {"sheetId": ids[SHEET_SETTLE_HIST]}, "warningOnly": True,
        "description": "앱이 쌓는 정산 전용 계정 변경이력 — 직접 수정하지 마세요"}}})
    client.batch_update(reqs)
    if log:
        log(f"== [원장] '{SHEET_SETTLE}'·'{SHEET_SETTLE_HIST}' 시트 생성(정산만 하는 계정 — 사람이 편집·앱이 이력) ==")
    return True


def _hist_lines(changes: list, start_no: int, now: datetime) -> list[list[str]]:
    ts, eff = now.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d")
    lines = [[str(start_no + i), ts, eff, aid, biz, kind, item, old, new, ""]
             for i, (aid, biz, kind, item, old, new) in enumerate(changes)]
    return list(reversed(lines))                      # 최신이 위(다른 이력 시트와 같은 순서)


def sync_settle(client, now: datetime | None = None, log=None, dry_run: bool = False) -> list[tuple]:
    """'정산전용계정' 시트를 직전 이력 상태와 비교해 바뀐 점을 '정산전용이력' 맨 위에 추가. 변경 목록 반환(비번 값은 로그 생략).
    시트가 없으면 만든다(빈 목록). SettleSheetError 는 그대로 올림(쓰기 없음)."""
    log = log or (lambda m: None)
    now = now or datetime.now()
    if not dry_run:
        ensure_sheets(client, log)
    elif SHEET_SETTLE not in client.sheet_titles():
        return []
    cur, warns = parse_settle(client.read_values(SHEET_SETTLE))
    hist = client.read_values(SHEET_SETTLE_HIST)
    changes = diff(replay(hist), cur)
    for w in warns:
        log(f"  [원장] ⚠ {w}")
    for aid, _biz, kind, item, old, new in changes:
        vals = "(값 생략)" if item == "비밀번호" else f"'{old}' → '{new}'" if (old or new) else ""
        log(f"  [{SHEET_SETTLE_HIST}] {kind} {aid} {item} {vals}".rstrip())
    if changes and not dry_run:
        start = max((int(str(r[0]).strip()) for r in hist[1:] if r and str(r[0]).strip().isdigit()), default=0) + 1
        gid = client.sheet_id(SHEET_SETTLE_HIST)
        client.batch_update([{"insertDimension": {"range": {"sheetId": gid, "dimension": "ROWS", "startIndex": 1,
                                                            "endIndex": 1 + len(changes)}, "inheritFromBefore": False}}])
        client.write_values(SHEET_SETTLE_HIST, _hist_lines(changes, start, now), start="A2", raw=True)
    log(f"== [원장] 정산 전용 계정 {len(cur)}개(관리중 {sum(r.active for r in cur.values())}) · 변경 {len(changes)}건"
        f"{' (미리보기)' if dry_run else ''} ==")
    return changes


def import_rows(client, accounts, skip_ids: set, own_ids: set, today: str) -> list[str]:
    """정산 계정 파일 계정(SettleAccount) 중 skip_ids(셀독원장에 있는 계정)에 없는 것을 '정산전용계정'에 한 번 추가 —
    이미 시트에 있는 계정ID 는 건너뜀. own_ids = 우리 사업자(구분=우리사업자). 추가한 계정ID 목록 반환(비번은 반환·로그 안 함)."""
    ensure_sheets(client)
    cur, _w = parse_settle(client.read_values(SHEET_SETTLE))
    add = [a for a in accounts if a.account_id not in skip_ids and a.account_id not in cur]
    if not add:
        return []
    n = len(client.read_values(SHEET_SETTLE))
    rows = []
    for a in add:
        name = "" if a.label == a.account_id else a.label
        rep, _, biz = name.partition("-") if "-" in name else ("", "", name)   # 한 단어 이름 = 사업자명(표시 이름 그대로)
        rows.append([ST_ACTIVE, today, "", "우리사업자" if a.account_id in own_ids else "위탁", rep, biz,
                     a.account_id, a.password, "정산 계정 파일에서 옮김"])
    client.write_values(SHEET_SETTLE, rows, start=f"A{n + 1}", raw=True)
    return [a.account_id for a in add]
