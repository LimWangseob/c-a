"""샵마인 서버에서 쿠팡 위탁 계정 '현재 비밀번호'를 하루 1회 받아 관리대장(구글시트)과 대조·갱신(D-195).

배경: 사장님은 계정 비밀번호를 ①구글 관리대장과 ②샵마인 서버 양쪽에 이중 관리하는데, 담당 직원이 샵마인만 고쳐
관리대장 값이 어긋난다. 샵마인에 저장된 값 = 실제 쿠팡에 로그인되는 **현재 비밀번호**(진실 소스)이므로, 샵마인에서
받은 현재값이 관리대장과 다르면 **관리대장을 그 값으로 갱신**한다(소유자 2026-11-10 '리포트+관리대장 자동반영').

경로(샵마인 앱과 동일): `POST /sm/api/login`(비번 평문 JSON http) → AuthenticationKey →
`POST /sm/api/read/market_account`(계정 목록·비번 포함). 샵마인은 시스템 프록시를 무시하고 서버 IP(16개)에 직접
http 접속하므로 스크립트도 같은 방식(ProxyHandler({}))으로 서버 순회(failover)한다.

정책(⛔불변):
- 비번 평문은 로그·커밋·화면·대화·리포트 어디에도 출력하지 않는다. 리포트는 **계정ID·상태만**(값 없음).
- 샵마인 로그인 자격은 이 PC credstore(DPAPI·사용자 전용)에 `__shopmine_login__` 로 저장. git·공유 금지.
  입력은 사용자가 직접(getpass·tools/shopmine_sync.py setup) — 설정 밖에서 비번을 받거나 입력하지 않는다.
- 호출은 하루 1회 저빈도(앱이 평소 하는 수준). 본인 계정·본인 데이터. 샵마인 약관상 비공식 접근 제한 가능성(1회 안내함).
- 관리대장 = 마스터(D-134). 쓰기는 비밀번호 열의 해당 계정 행에 RAW(값 그대로)로, 샵마인 현재값이 **비어 있지 않을
  때만**(빈 값으로 덮지 않음) · 샵마인에만 있는 계정은 행을 자동 추가하지 않고 리포트만 한다(대장은 상품별 구조).

게이트: `tools/verify_shopmine_sync_offline.py`(DPAPI 왕복·필드 탐색·대조 분류·되쓰기·credstore 갱신 — 실 API·실
자격 없이 결정적). 실서버 discover/sync 는 사용자 자격으로 1회 확인(tools/shopmine_sync.py).
"""
from __future__ import annotations

import csv
import gzip
import json
import urllib.error
import urllib.request
import zlib
from datetime import datetime
from pathlib import Path

# 정적 분석(D:\rea\evidence\shopmine)으로 확인한 /sm/ 서버 16개. 순서대로 시도(실패 시 다음 IP).
SERVERS = [
    "115.71.236.40", "115.71.237.39", "115.71.237.52", "115.71.237.59",
    "115.71.237.205", "115.71.237.214", "115.71.237.215", "115.71.238.74",
    "115.71.238.129", "115.71.238.175", "115.71.238.240", "115.71.239.36",
    "115.71.239.80", "115.71.239.162", "115.71.239.163", "115.71.239.173",
]

COMMON_HEADERS = {
    "Content-Type": "application/json;charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Encoding": "gzip, deflate",
}

SHOPMINE_KEY = "__shopmine_login__"     # credstore(DPAPI) 안 샵마인 로그인 자격 블록 키
AUTHKEY_NAMES = frozenset({"authenticationkey", "authkey", "auth_key"})
ID_KEY_DEFAULT = "MarketId"             # 계정 레코드의 계정ID 필드(정적분석 추정 · discover 로 확정)
PW_KEY_DEFAULT = "MarketPassword"       # 계정 레코드의 비번 필드(정적분석 추정 · discover 로 확정)
PAGE_SIZE_DEFAULT = 100
START_PAGE_DEFAULT = 1                  # CurrentPageNumber 시작값(서버가 0-based 면 0 · discover 로 확정)
REPORT_DIR = "output/샵마인동기화"

# 대조 상태(리포트·요약용 · 비번 값 없음)
ST_MATCH = "같음"
ST_DIFF = "다름→대장갱신"
ST_SM_ONLY = "샵마인에만(대장 없음)"
ST_LED_ONLY = "대장에만(샵마인 없음)"
ST_SM_EMPTY = "샵마인 비번 없음"


class ShopmineError(Exception):
    """샵마인 동기화를 할 수 없음(자격 없음·로그인 실패·필드 미확인 등). 호출부(앱)는 비치명으로 로그만 남긴다."""


# ─────────────────────────────────────────────── 로그인 자격(credstore·DPAPI)
def store_login(creds: dict, store=None) -> None:
    """샵마인 로그인 블록을 credstore(DPAPI)에 저장. creds = {CompanyId, UserId, UserPassword, OsVersion,
    ShopmineVersion, (선택) IdKey, PwKey, StartPage, PageSize}. 비번 평문은 DPAPI 로만 남고 화면에 안 보인다."""
    if store is None:
        from .credstore import CredStore
        store = CredStore()
    store.set_password(SHOPMINE_KEY, json.dumps(creds, ensure_ascii=False))


def load_login(store=None) -> dict | None:
    """저장된 샵마인 로그인 블록(dict) · 없으면 None(= 아직 setup 안 함)."""
    if store is None:
        from .credstore import CredStore
        store = CredStore()
    raw = store.get_password(SHOPMINE_KEY)
    return json.loads(raw) if raw else None


# ─────────────────────────────────────────────── HTTP(서버 순회)
def _opener():
    """시스템/환경 프록시 무시 — 샵마인과 동일하게 서버 IP 에 직접 접속."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _decode(resp) -> bytes:
    """gzip/deflate 수동 디코드(헤더대로). 아니면 원문."""
    raw = resp.read()
    enc = (resp.headers.get("Content-Encoding") or "").lower()
    if "gzip" in enc:
        try:
            return gzip.decompress(raw)
        except OSError:
            pass
    if "deflate" in enc:
        for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
            try:
                return zlib.decompress(raw, wbits)
            except zlib.error:
                continue
    return raw


def post_json(server: str, path: str, body: dict, timeout: int = 20):
    url = f"http://{server}/sm/{path}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=COMMON_HEADERS, method="POST")
    with _opener().open(req, timeout=timeout) as resp:
        return json.loads(_decode(resp).decode("utf-8-sig"))


def post_failover(path: str, body: dict, log=lambda m: None):
    """서버 목록을 순서대로 시도 — 성공한 (서버, 응답). 전부 실패하면 ShopmineError(마지막 사유)."""
    last = ""
    for srv in SERVERS:
        try:
            return srv, post_json(srv, path, body)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            last = f"{srv}: {exc}"
        except json.JSONDecodeError as exc:
            last = f"{srv}: 응답이 JSON 아님({exc})"
    raise ShopmineError(f"샵마인 서버 전부 실패 — 마지막 오류 {last}")


# ─────────────────────────────────────────────── 응답 탐색(필드명 확정용)
def find_value_by_keyname(obj, names_lower: frozenset):
    """중첩 구조에서 키 이름이 names_lower 중 하나와(대소문자 무시) 같은 첫 스칼라 값."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in names_lower and not isinstance(v, (dict, list)):
                return v
        for v in obj.values():
            r = find_value_by_keyname(v, names_lower)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_value_by_keyname(v, names_lower)
            if r is not None:
                return r
    return None


def first_record_list(obj) -> list:
    """dict 레코드들의 첫 리스트(없으면 obj 가 리스트면 그대로·아니면 [])."""
    if isinstance(obj, list):
        return obj if (not obj or isinstance(obj[0], dict)) else []
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
    return []


def masked_keys(records: list) -> list:
    """첫 레코드의 필드명(정렬) — discover 가 값 없이 필드만 보여줄 때."""
    return sorted(records[0].keys()) if records else []


# ─────────────────────────────────────────────── 로그인·계정 조회
def do_login(creds: dict, log=lambda m: None):
    """api/login → (서버, AuthenticationKey, 응답). 인증키 못 찾으면 ShopmineError(값은 안 보임·키만)."""
    body = {
        "CompanyId": creds.get("CompanyId", ""),
        "UserId": creds.get("UserId", ""),
        "UserPassword": creds.get("UserPassword", ""),
        "OsVersion": creds.get("OsVersion", "Windows"),
        "ShopmineVersion": creds.get("ShopmineVersion", ""),
    }
    srv, resp = post_failover("api/login", body, log)
    authkey = find_value_by_keyname(resp, AUTHKEY_NAMES)
    if not authkey:
        keys = sorted(resp.keys()) if isinstance(resp, dict) else "(리스트 응답)"
        raise ShopmineError(f"로그인 응답에 AuthenticationKey 없음(서버 {srv}·최상위 키 {keys}) — "
                            "ShopmineVersion/필드명 확인(discover)")
    return srv, authkey, resp


def fetch_accounts(creds: dict, authkey, page_size: int, start_page: int,
                   max_pages: int = 200, log=lambda m: None) -> tuple[list, dict | None]:
    """api/read/market_account 페이지 순회 → (전체 레코드, 첫 응답). PageSize 미만이면 마지막 페이지."""
    base = {
        "AuthenticationKey": authkey, "CompanyId": creds.get("CompanyId", ""),
        "UserId": creds.get("UserId", ""), "PageSize": page_size,
        "FilterJArray": [], "Key": "", "Value": "",
    }
    recs: list = []
    first = None
    page = start_page
    while page < start_page + max_pages:
        _, resp = post_failover("api/read/market_account", dict(base, CurrentPageNumber=page), log)
        if first is None:
            first = resp
        got = first_record_list(resp)
        recs.extend(got)
        if len(got) < page_size:
            break
        page += 1
    return recs, first


def extract_passwords(records: list, id_key: str, pw_key: str) -> dict[str, str]:
    """계정 레코드 리스트 → {계정ID: 비번}. 빈 계정ID 는 건너뜀."""
    out: dict[str, str] = {}
    for r in records:
        aid = str(r.get(id_key, "")).strip()
        if aid:
            out[aid] = str(r.get(pw_key, ""))
    return out


def fetch_shopmine_passwords(store=None, log=lambda m: None) -> dict[str, str]:
    """저장된 자격으로 로그인→계정 전체 수신→{계정ID: 현재비번}. 자격 없으면 ShopmineError."""
    creds = load_login(store)
    if creds is None:
        raise ShopmineError("샵마인 로그인 자격이 없음 — tools/shopmine_sync.py setup 으로 1회 저장하세요")
    _, authkey, _ = do_login(creds, log)
    recs, _ = fetch_accounts(creds, authkey, int(creds.get("PageSize", PAGE_SIZE_DEFAULT)),
                             int(creds.get("StartPage", START_PAGE_DEFAULT)), log=log)
    return extract_passwords(recs, creds.get("IdKey", ID_KEY_DEFAULT), creds.get("PwKey", PW_KEY_DEFAULT))


# ─────────────────────────────────────────────── 관리대장 비번 열·대조
def _col_letter(idx0: int) -> str:
    """0-based 열 인덱스 → A1 열 문자(0→A, 26→AA)."""
    s = ""
    n = idx0 + 1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        s = chr(65 + rem) + s
    return s


def ledger_password_map(rows: list):
    """관리대장 값 격자 → ({계정ID: [PwCandidate…]}, 비번 열 문자|None). 앱과 같은 파서로 계정별 비번 후보·행을 얻는다."""
    from .input_list import parse_password_candidates, password_column
    cands = parse_password_candidates(rows)
    idx = password_column(rows)
    return cands, (_col_letter(idx) if idx is not None else None)


def classify(shopmine: dict[str, str], ledger_cands: dict[str, list]) -> list[tuple[str, str]]:
    """계정별 대조 상태(계정ID·상태만·비번 값 없음). 샵마인 현재값이 관리대장 후보 중 하나와 같으면 '같음'."""
    led_pw = {aid: {c.password for c in cs} for aid, cs in ledger_cands.items()}
    out: list[tuple[str, str]] = []
    for aid in sorted(set(shopmine) | set(led_pw)):
        sm = (shopmine.get(aid) or "").strip()
        if aid not in led_pw:
            st = ST_SM_ONLY
        elif aid not in shopmine:
            st = ST_LED_ONLY
        elif not sm:
            st = ST_SM_EMPTY
        elif sm in led_pw[aid]:
            st = ST_MATCH
        else:
            st = ST_DIFF
        out.append((aid, st))
    return out


def updates_to_apply(shopmine: dict[str, str], ledger_cands: dict[str, list]) -> list[tuple[str, str, list[int]]]:
    """갱신할 계정 목록 [(계정ID, 샵마인현재값, 되쓸 대장 행들)]. 조건 = 대장에 있고 · 샵마인값이 비어있지 않고 ·
    대장 어느 후보와도 다름. 되쓸 행 = 그 계정 비번이 적힌 모든 대장 행(여러 줄 값 통일)."""
    led_pw = {aid: {c.password for c in cs} for aid, cs in ledger_cands.items()}
    plan: list[tuple[str, str, list[int]]] = []
    for aid, cs in ledger_cands.items():
        sm = (shopmine.get(aid) or "").strip()
        if sm and aid in shopmine and sm not in led_pw[aid]:
            plan.append((aid, sm, sorted({r for c in cs for r in c.rows})))
    return plan


def apply_updates(client, sheet: str, pw_col: str, plan: list, store, log=lambda m: None) -> int:
    """갱신 계획을 관리대장(구글시트) 비번 열에 RAW 로 되쓰고, 그날 로그인·정산이 바로 새 값을 쓰도록 credstore 갱신.
    줄마다 값이 달랐던 계정의 둘째 값(D-190)은 한 값으로 통일됐으므로 비운다. 반환 = 쓴 셀 수."""
    from . import settlement_accounts
    n_cell = 0
    for aid, pw, rows in plan:
        for r in rows:
            client.write_values(sheet, [[pw]], start=f"{pw_col}{r}", raw=True)
            n_cell += 1
        store.set_password(aid, pw)                       # 대장값1 = credstore(앱·정산 로그인 소스)
        if store.get_password(settlement_accounts.alt_key(aid)):
            store.set_password(settlement_accounts.alt_key(aid), "")   # 값2 비움(한 값 통일)
        log(f"[샵마인] {aid}: 관리대장 비밀번호 {len(rows)}행 갱신(샵마인 현재값) · 로그인 후보도 갱신")
    return n_cell


def write_report(classified: list[tuple[str, str]], out_dir: str, now: datetime) -> Path:
    """대조 리포트 CSV(계정ID·상태만·비번 값 없음) 저장 → 경로."""
    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)
    f = p / f"대조_{now:%Y%m%d_%H%M%S}.csv"
    with f.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["계정ID", "상태"])
        w.writerows(classified)
    return f


def _summary_line(classified: list, n_cell: int, report: Path) -> str:
    counts: dict[str, int] = {}
    for _, st in classified:
        counts[st] = counts.get(st, 0) + 1
    parts = " · ".join(f"{st} {n}" for st, n in counts.items())
    return f"[샵마인] 대조 완료 — {parts} · 대장 갱신 {n_cell}셀 · 리포트 {report}"


def _gsheet_client(url: str, store):
    from . import gsheet_api
    return gsheet_api.GSheetClient(url, store=store)


def run_daily_sync(url: str, sheet: str, rows: list, *, store, client=None, fetch=None,
                   log=print, now: datetime | None = None, out_dir: str = REPORT_DIR) -> dict:
    """하루 1회 동기화 본체 — 샵마인 현재 비번 수신 → 관리대장 대조 → 리포트 + 불일치 자동 갱신.

    fetch: 테스트/주입용 `fetch(store, log) -> {계정ID: 비번}`(None 이면 실 서버). client: 구글시트 클라이언트
    (None 이면 url 로 생성). 반환 = 요약 숫자(비번 값 없음). 실패는 예외로 올림(호출부가 비치명 처리)."""
    now = now or datetime.now()
    shopmine = (fetch or fetch_shopmine_passwords)(store, log)
    cands, pw_col = ledger_password_map(rows)
    if pw_col is None:
        log("[샵마인] 관리대장에서 비밀번호 열을 찾지 못해 대조 건너뜀")
        return {"skipped": "no_pw_col"}
    classified = classify(shopmine, cands)
    report = write_report(classified, out_dir, now)
    plan = updates_to_apply(shopmine, cands)
    n_cell = 0
    if plan:
        n_cell = apply_updates(client or _gsheet_client(url, store), sheet, pw_col, plan, store, log)
    log(_summary_line(classified, n_cell, report))
    return {"accounts": len(classified), "updated": len(plan), "cells": n_cell, "report": str(report)}
