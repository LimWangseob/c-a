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
  입력은 사용자가 직접 — 앱 **설정 탭 '샵마인 로그인 입력'**(D-389) 또는 CLI `tools/shopmine_sync.py setup`(getpass).
  둘 다 `make_login`→`store_login` 같은 함수 · 설정 밖에서 비번을 받거나 입력하지 않는다.
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
SUCCESS_NAMES = frozenset({"issuccess", "success", "result"})   # 로그인 성공 플래그(실측 응답 키 = IsSuccess)
ID_KEY_DEFAULT = "MarketId"             # 계정 레코드의 계정ID 필드(D-196 실서버 discover 확정)
PW_KEY_DEFAULT = "MarketPassword"       # 계정 레코드의 비번 필드(D-196 실서버 discover 확정)
OS_VERSION_DEFAULT = ""                 # D-196 pktmon 캡처 = 샵마인 앱의 실제 성공 로그인 본문 값
SHOPMINE_VERSION_DEFAULT = "26.8.24.866"   # D-196 캡처 값(개발 PC 에서 discover 성공한 저장 블록과 같음)
PAGE_SIZE_DEFAULT = 100
START_PAGE_DEFAULT = 1                  # CurrentPageNumber 시작값(서버가 0-based 면 0 · discover 로 확정)
REPORT_DIR = "output/샵마인동기화"

# 대조 상태(리포트·요약용 · 비번 값 없음)
ST_MATCH = "같음"
ST_DIFF = "다름→대장갱신"
ST_SM_ONLY = "샵마인에만(대장 없음)"
ST_LED_ONLY = "대장에만(샵마인 없음)"
ST_SM_EMPTY = "샵마인 비번 없음"
ST_SM_REFUSED = "샵마인값=24시간 안 쿠팡 거부값(대장 안 덮음)"   # T-160 안전장치 ②
ST_LED_PROVEN = "대장값=지난 로그인 성공값(대장 안 덮음)"      # D-389 안전장치 ⑤ — 쿠팡에서 맞다고 확인된 값을 지키기

# 앱 하루 1회 훅 판정(T-160 안전장치 ① — 자격 없음을 조용히 건너뛰지 않음)
GATE_RUN = "run"
GATE_DONE = "done_today"
GATE_NOCRED_LOG = "nocred_log"
GATE_NOCRED_QUIET = "nocred_quiet"
GATE_REJECTED_LOG = "rejected_log"     # 저장된 자격을 샵마인이 거부 — 다시 입력할 때까지 로그인 안 함(잠금 방지)
NOCRED_MSG = "[샵마인] 자격 없음 — 동기화 안 함(앱 설정 탭 '샵마인 로그인 입력'에 한 번 입력하면 매일 자동)"
REJECTED_MSG = ("[샵마인] 저장된 로그인 정보를 샵마인이 거부함 — 동기화 안 함(샵마인 계정 잠금 방지로 다시 시도하지 않음 · "
                "앱 설정 탭 '샵마인 로그인 입력'에서 다시 입력)")
NOTICE_MSG = {GATE_NOCRED_LOG: NOCRED_MSG, GATE_REJECTED_LOG: REJECTED_MSG}
REJECTED_FLAG = "LoginRejected"        # 로그인 블록 안 표식(값 아님) — 거부된 자격으로 매일 다시 로그인하지 않게
# 앱 상태 키(QSettings·config.json) — 마지막 동기화일 · 자격 알림일 · 첫 대조 리포트일(첫날 = 리포트만 D-389)
K_LAST_SYNC = "shopmine/last_sync_date"
K_NOTICE = "shopmine/nocred_log_date"
K_FIRST_REPORT = "shopmine/first_report_date"


class ShopmineError(Exception):
    """샵마인 동기화를 할 수 없음(자격 없음·로그인 실패·필드 미확인 등). 호출부(앱)는 비치명으로 로그만 남긴다."""


class ShopmineLoginRejected(ShopmineError):
    """샵마인 서버가 응답은 했으나 로그인 거부(IsSuccess=False) — 자격 값이 틀림(다시 입력 전까지 재시도 금지)."""


# ─────────────────────────────────────────────── 로그인 자격(credstore·DPAPI)
def make_login(company_id: str, user_id: str, password: str, **over) -> dict:
    """설정 탭·CLI setup 공용 로그인 블록. 기본값 = D-196 실서버 성공 로그인과 같은 OsVersion·ShopmineVersion·필드명.
    over = CLI 가 바꿔 줄 때만(OsVersion·ShopmineVersion·IdKey·PwKey·StartPage·PageSize · None 은 기본값 유지)."""
    creds = {"CompanyId": company_id.strip(), "UserId": user_id.strip(), "UserPassword": password,
             "OsVersion": OS_VERSION_DEFAULT, "ShopmineVersion": SHOPMINE_VERSION_DEFAULT,
             "IdKey": ID_KEY_DEFAULT, "PwKey": PW_KEY_DEFAULT,
             "StartPage": START_PAGE_DEFAULT, "PageSize": PAGE_SIZE_DEFAULT}
    creds.update({k: v for k, v in over.items() if v is not None})
    return creds


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


def mark_rejected(store) -> None:
    """저장된 자격이 샵마인에서 거부됨을 블록에 표시(값은 그대로) — 다시 입력(store_login 새 블록)하면 사라진다."""
    creds = load_login(store)
    if creds is not None:
        store_login(dict(creds, **{REJECTED_FLAG: True}), store)


def daily_gate(store, today: str, last_sync: str, nocred_logged: str) -> str:
    """앱 훅(하루 1회)의 할 일 — 자격 없음 / 거부된 자격이면 **하루 1번 로그**(NOTICE_MSG · 그날 이미 알렸으면 조용히) ·
    오늘 이미 동기화했으면 안 함 · 아니면 실행. last_sync·nocred_logged = 마지막 날짜(YYYY-MM-DD · 없으면 '')."""
    creds = load_login(store)
    if creds is None or creds.get(REJECTED_FLAG):
        if nocred_logged == today:
            return GATE_NOCRED_QUIET
        return GATE_NOCRED_LOG if creds is None else GATE_REJECTED_LOG
    return GATE_DONE if last_sync == today else GATE_RUN


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
    """api/login → (서버, AuthenticationKey, 응답). 인증키 못 찾으면 ShopmineError(값은 안 보임·키만).

    업체ID·사용자ID·비번은 **앞뒤 공백을 떼고** 보낸다 — 샵마인 앱이 입력칸을 .Trim() 한 뒤 평문 그대로 전송하기
    때문(REA IL 정적 추적 확정: 해시·AES·salt·prefix 없음, 변형은 Trim 뿐 · D-195)."""
    body = {
        "CompanyId": creds.get("CompanyId", "").strip(),
        "UserId": creds.get("UserId", "").strip(),
        "UserPassword": creds.get("UserPassword", "").strip(),
        "OsVersion": creds.get("OsVersion", "Windows"),
        "ShopmineVersion": creds.get("ShopmineVersion", ""),
    }
    srv, resp = post_failover("api/login", body, log)
    authkey = find_value_by_keyname(resp, AUTHKEY_NAMES)
    if not authkey:
        keys = sorted(resp.keys()) if isinstance(resp, dict) else "(리스트 응답)"
        success = find_value_by_keyname(resp, SUCCESS_NAMES)
        if success is not None and not success:   # 응답은 왔으나 서버가 로그인 거부(IsSuccess=False·인증키 빈 값)
            raise ShopmineLoginRejected(
                f"샵마인 로그인 거부(서버 {srv}·IsSuccess={success}·인증키 빈 값). 필드명은 맞음(최상위 키 {keys}). "
                "업체ID·비번이 맞는지 · 대표(업체) 계정이면 UserId 를 비워야 하는지 · ShopmineVersion 이 필요한지 "
                "확인해 setup 다시. ⚠ 거듭 틀리면 샵마인 계정이 잠길 수 있으니 2~3회만 시도.")
        raise ShopmineError(f"로그인 응답에 AuthenticationKey 없음(서버 {srv}·최상위 키 {keys}·IsSuccess={success}) — "
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


def resolve_fields(records: list, id_key: str, pw_key: str) -> tuple[str, str]:
    """discover 자동(D-389) — 받은 계정 레코드에서 계정ID·비번 필드의 실제 이름(대소문자 무시 일치)을 찾는다.
    레코드 0건이거나 필드가 없으면 ShopmineError(필드명만 · 값 없음) — 대장을 엉뚱한 값으로 대조하지 않게."""
    if not records:
        raise ShopmineError("샵마인 계정 목록이 0건 — 대조 안 함(로그인은 됐으나 계정이 안 옴 · 서버 응답 확인 필요)")
    names = {k.lower(): k for r in records[:5] for k in r}
    got = names.get(id_key.lower()), names.get(pw_key.lower())
    if None in got:
        raise ShopmineError(f"샵마인 계정 응답에 계정ID/비번 필드({id_key}/{pw_key})가 없음 — 대조 안 함 · "
                            f"받은 필드명 {sorted(names.values())}(값 없음)")
    return got


def fetch_shopmine_passwords(store=None, log=lambda m: None) -> dict[str, str]:
    """저장된 자격으로 로그인→계정 전체 수신→필드 확인(discover 자동)→{계정ID: 현재비번}.
    자격 없으면 ShopmineError · 샵마인이 로그인 거부하면 거부 표시(mark_rejected — 다시 입력 전까지 재시도 안 함) 후 올림.
    필드 이름이 저장값과 대소문자만 다르면 실제 이름을 블록에 저장(다음부터 그대로)."""
    creds = load_login(store)
    if creds is None:
        raise ShopmineError("샵마인 로그인 자격이 없음 — 앱 설정 탭 '샵마인 로그인 입력'에 한 번 입력하세요")
    try:
        _, authkey, _ = do_login(creds, log)
    except ShopmineLoginRejected:
        mark_rejected(store)
        raise
    recs, _ = fetch_accounts(creds, authkey, int(creds.get("PageSize", PAGE_SIZE_DEFAULT)),
                             int(creds.get("StartPage", START_PAGE_DEFAULT)), log=log)
    id_key, pw_key = resolve_fields(recs, creds.get("IdKey", ID_KEY_DEFAULT), creds.get("PwKey", PW_KEY_DEFAULT))
    if (id_key, pw_key) != (creds.get("IdKey"), creds.get("PwKey")):
        store_login(dict(creds, IdKey=id_key, PwKey=pw_key), store)
    log(f"[샵마인] 샵마인 계정 {len(recs)}건 받음(필드 {id_key}/{pw_key} 확인 · 값은 안 보임)")
    return extract_passwords(recs, id_key, pw_key)


def check_login(store, log=lambda m: None) -> tuple[bool, str]:
    """설정 탭 입력 직후 연결 확인(로그인 1회 + 계정 목록·필드 확인 · 관리대장은 안 건드림) → (성공?, 한 줄 안내).
    실패 사유는 숨기지 않고 안내 문구로 돌려준다(거부면 거부 표시까지 — 매일 재시도 안 함)."""
    try:
        n = len(fetch_shopmine_passwords(store, log))
    except ShopmineError as exc:
        return False, str(exc)
    return True, f"연결됨 — 샵마인 계정 {n}건(비밀번호 값은 안 보임)"


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


def _kept_status(aid: str, sm: str, ledger_pws: set, refused, proven) -> str | None:
    """대장을 덮으면 안 되는 경우의 상태(아니면 None). ② 샵마인 값 = 24시간 안 쿠팡 거부값 ·
    ⑤ 대장 값 중 하나가 지난 자동입력 로그인 성공값(그 뒤 거부 없음)인데 샵마인 값은 그 값이 아님(D-389)."""
    if refused and refused(aid, sm):
        return ST_SM_REFUSED
    if proven and not proven(aid, sm) and any(proven(aid, p) for p in ledger_pws):
        return ST_LED_PROVEN
    return None


def classify(shopmine: dict[str, str], ledger_cands: dict[str, list], refused=None,
             proven=None) -> list[tuple[str, str]]:
    """계정별 대조 상태(계정ID·상태만·비번 값 없음).

    '같음' = **그 계정의 모든 대장 줄이 이미 샵마인 현재값**일 때만. 한 계정이 여러 줄에 걸쳐 있고 일부 줄만
    현재값이면(담당자가 한 줄만 고친 경우·D-012·D-190) '다름→대장갱신'으로 봐서 **모든 줄을 현재값으로 통일**한다
    (옛값 줄이 남아 로그인이 옛값을 집는 것을 막음). refused(계정ID, 값) = 그 값이 최근 24시간 안에 쿠팡에서
    거부됐나(T-160 안전장치 ②) — 그러면 '다름' 대신 ST_SM_REFUSED(대장 안 덮음). proven(계정ID, 값) = 그 값이
    지난 자동입력 로그인 성공값인가(D-389 ⑤) — 대장에 성공값이 있고 샵마인 값은 아니면 ST_LED_PROVEN(대장 안 덮음)."""
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
        elif led_pw[aid] == {sm}:          # 모든 줄이 이미 현재값일 때만 '같음'
            st = ST_MATCH
        else:                               # 일부 줄만 맞거나 전부 다름 → 모든 줄 통일(안전장치 ②⑤ 걸리면 안 덮음)
            st = _kept_status(aid, sm, led_pw[aid], refused, proven) or ST_DIFF
        out.append((aid, st))
    return out


def updates_to_apply(shopmine: dict[str, str], ledger_cands: dict[str, list],
                     refused=None, proven=None) -> list[tuple[str, str, list[int]]]:
    """갱신할 계정 목록 [(계정ID, 샵마인현재값, 되쓸 대장 행들)] = classify 가 '다름→대장갱신'으로 본 계정 — 대장에 있고 ·
    샵마인값이 비어있지 않고 · **대장의 모든 줄이 현재값인 것은 아님** · 안전장치(② 거부값 · ⑤ 대장 성공값)에 안 걸림.
    되쓸 행 = 그 계정 비번이 적힌 **모든 대장 행**(일부만 고쳐져 있어도 전부 현재값으로 통일 — '모두 변경')."""
    return [(aid, shopmine[aid].strip(), sorted({r for c in ledger_cands[aid] for r in c.rows}))
            for aid, st in classify(shopmine, ledger_cands, refused, proven) if st == ST_DIFF]


def ledger_value_label(shopmine: dict[str, str], ledger_cands: dict[str, list]) -> dict[str, str]:
    """{계정ID: 샵마인 값이 대장 후보 중 어느 것과 같은가} — '값1'·'값2'(시작 로그 '[비번] … 값N=행' 과 같은 번호) ·
    '대장 값과 다름' · 대장/샵마인 한쪽에만 있거나 샵마인 값이 비면 '-'. 값 자체는 없음(T-160 안전장치 ③)."""
    out: dict[str, str] = {}
    for aid in set(shopmine) | set(ledger_cands):
        sm = (shopmine.get(aid) or "").strip()
        cs = ledger_cands.get(aid) or []
        if not sm or not cs:
            out[aid] = "-"
            continue
        hit = [k for k, c in enumerate(cs) if c.password == sm]
        out[aid] = f"값{hit[0] + 1}" if hit else "대장 값과 다름"
    return out


def rows_with_plan(rows: list, plan: list) -> list:
    """되쓰기 뒤 관리대장 값 격자(메모리 사본) — 앱이 비밀번호 후보를 바로 다시 반영하게(T-160 안전장치 ④).
    ⚠ 비밀번호 값이 들어 있음 — 로그·파일에 쓰지 말 것."""
    from .input_list import password_column
    idx = password_column(rows)
    out = [list(r) if r is not None else [] for r in rows]
    for _aid, pw, rs in plan:
        for r in rs:
            row = out[r - 1]
            row.extend([None] * (idx + 1 - len(row)))
            row[idx] = pw
    return out


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


def backup_ledger(client, sheet: str, now: datetime, log=lambda m: None) -> str:
    """비번 되쓰기 **직전에** 관리대장(비번 포함) 탭을 **구글시트 안에서** 복제해 백업 탭을 만든다.

    로컬 파일 백업은 금지(평문 비번 유출·CLAUDE.md)라 구글 안에서만 백업한다 — 비번이 구글 밖으로 안 나간다.
    되돌리려면 이 백업 탭의 비번 열을 원래 탭에 되쓰면 된다. 변경이 있을 때만 호출(apply·plan 있을 때). 반환 = 백업 탭 이름."""
    name = f"백업_비번동기화_{now:%Y%m%d_%H%M%S}"
    client.duplicate_sheet(sheet, name)
    log(f"[샵마인] 변경 전 관리대장 백업 탭 생성: '{name}'(구글시트 안·로컬 저장 없음)")
    return name


def write_report(classified: list[tuple[str, str]], out_dir: str, now: datetime,
                 which: dict[str, str] | None = None) -> Path:
    """대조 리포트 CSV(계정ID·상태·샵마인=대장 어느 값[값1/값2/다름 — T-160 ③]·비번 값 없음) 저장 → 경로."""
    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)
    f = p / f"대조_{now:%Y%m%d_%H%M%S}.csv"
    with f.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["계정ID", "상태", "샵마인=대장"])
        w.writerows((aid, st, (which or {}).get(aid, "-")) for aid, st in classified)
    return f


def _summary_line(classified: list, n_cell: int, report: Path) -> str:
    counts: dict[str, int] = {}
    for _, st in classified:
        counts[st] = counts.get(st, 0) + 1
    parts = " · ".join(f"{st} {n}" for st, n in counts.items())
    return f"[샵마인] 대조 완료 — {parts} · 대장 갱신 {n_cell}셀 · 리포트 {report}"


_KEPT_LOG = {ST_SM_REFUSED: "샵마인 값이 최근 24시간 안에 쿠팡 로그인에서 거부된 값",
             ST_LED_PROVEN: "대장 값이 지난 로그인에 성공한 값인데 샵마인 값은 그 값과 다름"}


def _gsheet_client(url: str, store):
    from . import gsheet_api
    return gsheet_api.GSheetClient(url, store=store)


def run_daily_sync(url: str, sheet: str, rows: list, *, store, client=None, fetch=None,
                   log=print, now: datetime | None = None, out_dir: str = REPORT_DIR,
                   apply: bool = True, refused=None, proven=None, on_applied=None) -> dict:
    """하루 1회 동기화 본체 — 샵마인 현재 비번 수신 → 관리대장 대조 → 리포트 + 불일치 자동 갱신.

    fetch: 테스트/주입용 `fetch(store, log) -> {계정ID: 비번}`(None 이면 실 서버). client: 구글시트 클라이언트
    (None 이면 url 로 생성). apply=False 면 **대조·리포트만** 하고 관리대장·credstore 에 쓰지 않는다(미리보기·dry-run —
    첫 수동 실행 때 몇 계정이 바뀔지 먼저 확인용). 반환 = 요약 숫자(비번 값 없음). 실패는 예외로 올림(호출부가 비치명 처리).
    T-160 안전장치: refused(계정ID, 값)(기본 = 쿠팡 로그인 24시간 거부 지문 login_today.refused_today)가 참인 샵마인 값은
    대장을 덮지 않고 ⚠ 로그 · 리포트에 샵마인 값 = 대장 값1/값2/다름 · on_applied(되쓴 뒤 값 격자) = 앱이 비밀번호 후보를
    그 자리에서 다시 반영(되쓴 게 있을 때만 부름). D-389 ⑤: proven(계정ID, 값)(기본 = 지난 자동입력 로그인 성공값
    login_today.proven_ok) — 대장에 성공값이 있고 샵마인 값이 그 값이 아니면 대장을 덮지 않고 ⚠ 로그."""
    now = now or datetime.now()
    if refused is None or proven is None:
        from . import login_today
        refused = refused or login_today.refused_today
        proven = proven or login_today.proven_ok
    shopmine = (fetch or fetch_shopmine_passwords)(store, log)
    cands, pw_col = ledger_password_map(rows)
    if pw_col is None:
        log("[샵마인] 관리대장에서 비밀번호 열을 찾지 못해 대조 건너뜀")
        return {"skipped": "no_pw_col"}
    classified = classify(shopmine, cands, refused, proven)
    report = write_report(classified, out_dir, now, ledger_value_label(shopmine, cands))
    for aid, st in classified:
        if st in _KEPT_LOG:
            log(f"[샵마인] ⚠ {aid}: {_KEPT_LOG[st]} — 관리대장을 덮지 않음(샵마인 값을 확인해 주세요)")
    plan = updates_to_apply(shopmine, cands, refused, proven)
    n_cell = 0
    if plan and apply:
        cl = client or _gsheet_client(url, store)
        backup_ledger(cl, sheet, now, log)                 # 되쓰기 전 관리대장 백업(구글시트 안)
        n_cell = apply_updates(cl, sheet, pw_col, plan, store, log)
        if on_applied is not None:
            on_applied(rows_with_plan(rows, plan))
    note = "" if apply else f"  ※ 미리보기(dry-run) — 관리대장에 쓰지 않음(갱신 예정 {len(plan)}건)"
    log(_summary_line(classified, n_cell, report) + note)
    return {"accounts": len(classified), "updated": len(plan), "cells": n_cell, "report": str(report)}


def app_daily_hook(url: str, sheet: str, rows: list, *, store, today: str, get_state, set_state, log,
                   on_applied=None, **sync_kw) -> str:
    """앱 훅 본체(관리대장 읽은 직후 · 하루 1회 · D-389) — 소유자 추가 작업 없이 도는 순서:
    ① 자격 없음/거부된 자격 = 그날 1번 안내(NOTICE_MSG) 뒤 끝 ② 오늘 이미 함 = 끝 ③ **첫 동기화 날 = 대조 리포트만**
    (관리대장 안 고침 — 그날 쿠팡 로그인이 '성공값' 기억을 남겨 다음 날 안전장치 ⑤가 맞는 대장 값을 지킬 수 있게) ·
    ④ 다음 날부터 = 자동 반영(안전장치 ②⑤). get_state/set_state = 앱 상태(QSettings·config.json) 읽기/쓰기.
    sync_kw = 시험 주입(fetch·client·now·out_dir·refused·proven). 반환 = daily_gate 결과. 실패는 예외로 올림(앱이 비치명 처리)."""
    gate = daily_gate(store, today, get_state(K_LAST_SYNC), get_state(K_NOTICE))
    if gate in NOTICE_MSG:
        log(NOTICE_MSG[gate])
        set_state(K_NOTICE, today)
    if gate != GATE_RUN:
        return gate
    first = get_state(K_FIRST_REPORT)
    apply = bool(first) and first != today
    log("[샵마인] 서버에서 현재 비밀번호를 받아 관리대장과 대조 중…(하루 1회·값은 화면에 안 보임)" + (
        "" if apply else " · 첫 동기화 = 오늘은 대조 리포트만(관리대장 안 고침) · 다음 날부터 자동 반영"))
    run_daily_sync(url, sheet, rows, store=store, log=log, apply=apply, on_applied=on_applied, **sync_kw)
    if not first:
        set_state(K_FIRST_REPORT, today)
    set_state(K_LAST_SYNC, today)
    return gate
