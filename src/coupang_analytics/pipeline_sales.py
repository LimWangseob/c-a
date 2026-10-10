"""① 판매수집 엔진 — 로그인·발견(상품조회/판매분석/재고)·계정별 처리(_process_account).

pipeline.py 에서 분리(대형 파일 정비, 행동 불변). run_full(=pipeline 잔류)이 _login_and_discover·
_process_account 를 호출하고 NeedLogin/LoginBlocked/LoginCredentialError 를 잡으므로, 이 심볼들은
pipeline.py 로 다시 import 해 `pipeline.X` 공개 API(run_full·도구·핀)를 그대로 유지한다(재수출).
로그인은 이 모듈의 WingBrowser 로 열리므로, 로그인 핀 monkeypatch 는 pipeline_sales.WingBrowser 를 교체해야 한다.
collector/product_match 는 기존처럼 함수 내부 지연 import(교체 시 collector 모듈을 patch → 이동 무관).
의존 방향: pipeline_paths ← pipeline_ranks ← pipeline_sales(단방향·순환 없음).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from . import config
from . import session_state
from .browser import WING_URL, WingBrowser
from .input_list import Account
from .kw_ai import KeywordAIError, recommend_title
from .kw_recommend import (attack_priority, comp_from_idx, diagnose_exposure,
                           keyword_in_title, rank_label, select_keywords_light)
from .kw_volume import NaverAdApi
from .rank import make_matcher
from .workbook import OutputWorkbook
from .pipeline_paths import _PROFILES_DIR
from .pipeline_ranks import _RANK_HALT, _best, _measure_safe


def account_profile(account_id: str) -> str:
    """계정별 로그인 프로필 경로 (한 번 로그인하면 재사용)."""
    return f"{_PROFILES_DIR}/{account_id}"


class NeedLogin(Exception):
    """세션이 없어 로그인이 필요한 계정(세션우선 1차 패스에서 뒤로 미룸)."""


class LoginBlocked(Exception):
    """Akamai 로그인 차단(Access Denied) — 서킷브레이커 카운트 대상."""


class LoginCredentialError(Exception):
    """비밀번호 오류·계정잠금·휴면 등 **확정 자격 실패**(#input-error). 재시도·재제출 금지
    (재제출이 5회 오류 계정잠금을 유발 — 위탁계정). 호출부는 이 계정을 '처리됨'으로 표시해
    같은 실행·야간 재개가 다시 제출하지 않게 한다. 사용자 지시(2026-09-15): 비번 1회 오류면 재시도 안 함."""


def _dump_raw(account_id: str, log, out_dir: str = "output") -> None:
    """수집한 3개 데이터 API 응답 **원문(가공 없음)** 을 계정별 gzip 사이드카로 저장 — 다양한 오프라인 분석용.

    파싱/요약이 아니라 **쿠팡이 준 응답 바디 그대로**(F12 네트워크와 동일)를 남긴다. 재수집·재빌드 없이
    중복 판별·필드 탐색 등에 쓴다. 저장 위치=output/_raw/{계정}_{api}_p{n}.json.gz, run_log 엔 위치만(원문이
    커서 run_log 오염 방지). 설정(config.SAVE_RAW_RESPONSES) 끄면 no-op·버퍼 비면 no-op. 저장 실패는
    비치명(로그만·수집은 계속). api = vendor_inventory | inventory | sales(각 페이지 p1·p2…)."""
    if not config.SAVE_RAW_RESPONSES:
        return
    import gzip
    from .collector import raw_dumps
    dumps = raw_dumps()
    if not dumps:
        return
    try:
        d = Path(out_dir) / "_raw"
        d.mkdir(parents=True, exist_ok=True)
        n = 0
        for api, bodies in dumps.items():
            for i, body in enumerate(bodies, 1):
                with gzip.open(d / f"{account_id}_{api}_p{i}.json.gz", "wt", encoding="utf-8") as fh:
                    fh.write(body)
                n += 1
        if n:
            log(f"  [원본저장] {account_id}: 응답 원문 {n}개 → output/_raw/{account_id}_*.json.gz (가공 없음·분석용)")
    except Exception as exc:   # 저장 실패해도 수집은 계속(비치명)
        log(f"  [원본저장] ⚠ {account_id} 응답 원문 저장 실패(비치명) — {exc.__class__.__name__}: {str(exc)[:80]}")


def try_login_once(account_id: str, password: str, *, on_log=None) -> bool:
    """2-3(§10-1): 한 계정을 지정 비밀번호로 **반자동 1회** 로그인(A안·자동 재시도 없음).

    UI([이전 비밀번호로 1회 시도])가 밑줄 함수(_login_and_discover/_ensure_login)를 직접 부르지 않게 하는
    공개 진입점. 발견·수집은 하지 않고 로그인 성공 여부만 반환한다(쿠팡확인='확인됨' 기록은 호출부 UI 몫).
    반환 True=로그인 성공 · False=비번오류(LoginCredentialError)·차단(LoginBlocked)·미완료. 비밀번호는 로그에
    남기지 않으며(_ensure_login 규약), 브라우저는 with 종료 시 정리된다. semi=True(보이는 창·사람이 2차인증)."""
    log = on_log or (lambda m: None)
    a = Account(account_id, "", "")
    with WingBrowser(profile_dir=account_profile(account_id), offscreen=False) as b:
        try:
            return _ensure_login(b, a, password, log, login=True, semi=True)
        except (LoginBlocked, LoginCredentialError):
            return False


def _login_and_discover(a: Account, date_from, date_to, get_password, log, login: bool = True,
                        semi: bool = False, ai_key: str | None = None, anchor_file=None):
    """계정 하나: (필요시) 로그인 → **같은 신선한 세션**에서 즉시 판매분석 발견 + 지표.

    반환: (report_account[활동 상품만] | None, {옵션ID: OptionMetric}, {옵션ID: 재고수량},
    {옵션ID: 판매상태}, {업번들 vid 집합}, {상품조회 전체 vid 집합}). 4번째 판매상태맵 = 상품조회 productStatus
    문자열(판매자배송 포함 전 상품) 또는 폴백 RFM isSaleSuspended(bool). 5번째 = 업번들 vid(잔재 자동삭제용). 6번째 =
    이번 상품조회에 존재하는 전체 vid(죽은 중복 블록 정리 기준). 로그인 미완료면 (None,{},{},{},set(),set()) → 다음 계정으로.
    login=False(세션우선 1차): 세션 없으면 자동제출하지 않고 **NeedLogin** 을 던져 뒤로 미룬다
    (반복 자동로그인 = IP 차단 유발이라, 세션 살아있는 계정을 먼저 다 수집). Akamai 차단 시 LoginBlocked.
    semi=True(**반자동 판매수집**): 창을 **처음부터 보이게**(offscreen=False) 띄우고 **무인 아님**(사람이
    2차인증/직접로그인 처리)으로 로그인 → 그 신뢰 창에서 수집. ③ 반자동과 같은 '보이는 신뢰 세션' 방식.
    anchor_file = 매칭 고정 파일(D-009·run_full 이 output 기준으로 넘김). None 이면 고정 읽기/쓰기 안 함(도구·핀).
    """
    from . import collector
    pws = _pw_list(get_password(a.account_id) if get_password else None)
    # 기본은 **창 숨김**(offscreen). 반자동(semi)이면 처음부터 보이게 띄운다(사람이 2차인증 처리).
    with WingBrowser(profile_dir=account_profile(a.account_id), offscreen=not semi) as b:
        if not _login_with_candidates(b, a, pws, log, login=login, semi=semi):
            return None, {}, {}, {}, set(), set(), {}, {}   # 이 계정 건너뜀(무인 비번없음·otp·로그인 미완료)
        collector.reset_raw()                # 계정별 응답 원문 버퍼 초기화(파일 분리)
        found = _discover_products(b, a, date_from, date_to, log, ai_key=ai_key, anchor_file=anchor_file)
        _dump_raw(a.account_id, log)         # 3 API 응답 원문 저장(가공 없음·분석용). found None(데이터없음)이어도 남김
        if found is None:                    # 판매분석·상품조회 모두 데이터 없음 → 건너뜀
            return None, {}, {}, {}, set(), set(), {}, {}
        (products, tracked, metrics, inventory, sale_status, upbundle_vids, live_all_vids,
         vid_meta, pid_by_vid) = found
        session_state.observe_collection_done(a.account_id)         # 관측: 이 계정 수집 완료 시각
    report = Account(a.account_id, a.representative, a.business_name, tracked)
    report.ledger_products = set(a.ledger_products)   # ⑥: 줄 존재 전체(활성+판매중지/취소선) 전파 — 완전삭제 판정용
    return (report, metrics, inventory, sale_status, upbundle_vids, live_all_vids, vid_meta, pid_by_vid)


PW_MAX_TRIES = 2   # 관리대장 한 계정 여러 줄의 비번이 서로 다를 때 실행당 시도할 최대 값 수(D-012·잠금 5회 대비)


def _pw_list(v) -> list:
    """get_password 반환 → 후보 목록. str=1개, list=대장 줄마다 다른 값(앞 것부터), None/빈 값=[None](비번 없음)."""
    if isinstance(v, (list, tuple)):
        vals = [x for x in v if x]
        return vals[:PW_MAX_TRIES] or [None]
    return [v or None]


def _login_with_candidates(b, a: Account, pws: list, log, *, login: bool, semi: bool) -> bool:
    """관리대장 비번 후보를 차례로 — 첫 값은 평소 로그인(_ensure_login), **'비밀번호가 다릅니다'(LoginCredentialError)
    일 때만** 다음 값으로 1회 더(소유자 2026-10-09 D-012). 후보가 1개면 지금과 똑같다(재시도 없음). 모두 거부면 그대로 raise."""
    for k, pw in enumerate(pws):
        try:
            if k == 0:
                return _ensure_login(b, a, pw, log, login=login, semi=semi)
            log(f"  [{a.label}] ⚠ 관리대장 비밀번호 {k}번째 값 거부 → 같은 계정 다른 줄의 {k + 1}번째 값으로 다시 시도"
                f"({k + 1}/{len(pws)}) — 대장의 이 계정 비밀번호를 한 값으로 맞춰 주세요")
            b.goto(WING_URL)
            b.page.wait_for_timeout(1500)
            ok = _fresh_login(b, a, pw, log, config.LOGIN_UNATTENDED and not semi)
            if ok:
                log(f"  [{a.label}] ✅ {k + 1}번째 비밀번호 값으로 로그인 성공(시작 로그의 '[비번] … 값{k + 1}=행 …' 이 맞는 값)")
            return ok
        except LoginCredentialError:
            if k + 1 >= len(pws):
                raise
    return False


def _ensure_login(b, a: Account, pw, log, *, login: bool = True, semi: bool = False) -> bool:
    """로그인 국면 — 세션 판정·(필요시)자동입력·대기·분류·반자동 1회 재시도.

    반환: **True**=로그인됨(호출부가 발견 진행) / **False**=이 계정 건너뜀(호출부가 (None,{},{},{}) 반환:
    무인 비번없음·2차인증(otp)·로그인 미완료). **예외**: NeedLogin(세션우선 1차 미제출)·LoginBlocked(Akamai)·
    LoginCredentialError(비번오류/계정잠금·재시도 금지). 제어흐름은 분해 전과 완전히 동일하다."""
    if semi:
        b.show()
    b.goto(WING_URL)
    b.page.wait_for_timeout(1500)
    if b.authenticated():
        log(f"  [{a.label}] 세션 재사용 → 이미 로그인됨" + (" (보이는 창)" if semi else " (창 안 뜸)"))
        session_state.observe_session_ok(a.account_id, final_url=b.page.url)   # 관측(제어흐름 불변)
        return True
    if not login:                  # 세션우선 1차 패스 — 자동제출 안 하고 로그인 대기열로 미룸
        session_state.observe_reauth_required(a.account_id, final_url=b.page.url)
        raise NeedLogin()
    unattended = config.LOGIN_UNATTENDED and not semi   # 반자동이면 사람 대기(무인 아님)
    return _fresh_login(b, a, pw, log, unattended)


def _fresh_login(b, a: Account, pw, log, unattended: bool) -> bool:
    """신선 로그인(세션 없음) — 자동입력·대기·반자동 1회 재시도·실패분류·성공 안착.

    반환 True/False, 예외 LoginBlocked/LoginCredentialError 는 _ensure_login 규약과 동일."""
    shown = {"v": False}

    def _need_user():   # 2차인증·봇챌린지 등 사람이 꼭 필요할 때
        if unattended:  # 무인: 창 안 띄움 — 사람 필요분은 건너뛰고 나중에 반자동/수동으로
            return
        if not shown["v"]:
            shown["v"] = True
            log(f"  [{a.label}] ⚠ 로그인 창을 잠시 띄웁니다(2차인증/직접로그인 필요). 놀라지 마세요")
            b.show()

    if pw and b.autofill_login(a.account_id, pw, on_log=log):
        log(f"  [{a.label}] ID/비번 자동입력·제출 — 창 숨긴 채 로그인 확인 중"
            + (" (무인: 사람 필요 시 건너뜀)" if unattended else " (2차인증 필요할 때만 창 표시)"))
    elif unattended:
        # 무인 + 비번없음/자동입력실패 → 사람 개입 불가 → 건너뜀(창 안 띄움)
        log(f"  [{a.label}] 무인 로그인 불가(비번 없음/자동입력 실패) — 건너뜀(나중에 반자동/수동)")
        session_state.observe_reauth_required(a.account_id, final_url=b.page.url)
        return False
    else:
        _need_user()   # 비번 없음/자동입력 실패 → 직접 로그인해야 하니 창 표시
        log(f"  [{a.label}] 직접 로그인이 필요해 창을 띄웠습니다")
    _wait_to = config.LOGIN_UNATTENDED_WAIT_SEC if unattended else config.LOGIN_ATTENDED_WAIT_SEC
    _grace = config.LOGIN_BLOCK_GRACE_SEC if unattended else 60.0
    # skip_on_otp=True: 2차 인증(인증번호) 화면이 뜨면 **대기하지 않고 이 계정 건너뜀**(다음 계정 진행).
    ok = b.wait_for_login(timeout=_wait_to, on_log=log, tag=a.account_id,
                          on_need_user=_need_user, blocked_grace=_grace, skip_on_otp=True)
    # 비밀번호 오류·계정잠금·휴면(#input-error=classify_login 'error') = **확정 자격 실패**.
    # 사용자 지시(2026-09-15): 비번 1회 오류면 **재시도·재제출 금지**(재제출이 5회 오류 계정잠금 유발).
    cred_fail = (not ok) and b.classify_login()[0] == "error"
    otp_seen = (not ok) and b.classify_login()[0] == "otp"   # 2차인증 → 재시도 없이 건너뜀
    if not ok and not cred_fail and not otp_seen and unattended and pw and config.LOGIN_SEMI_ON_BLOCK:
        ok, cred_fail = _semi_retry_login(b, a, pw, log, _grace)
    if not ok:
        return _resolve_login_failure(b, a, log, cred_fail)   # False 반환 또는 LoginBlocked/CredentialError raise
    session_state.observe_auth_success(a.account_id, final_url=b.page.url)
    b.goto(WING_URL)                     # 신선 로그인 후 wing 안착(인증 리다이렉트 완료 대기)
    b.page.wait_for_timeout(1500)        # 페이지 안정 — discover fetch 가 진행중 네비에 중단(Failed to fetch)되는 것 방지
    b.hide()   # 로그인 끝나면 다시 숨김
    return True


def _semi_retry_login(b, a: Account, pw, log, grace) -> tuple[bool, bool]:
    """반자동(무인) **1회** 재시도 — 무인 오프스크린 자동입력이 소프트 차단/폼 정체로 실패했을 때만.

    (비번오류는 호출부 cred_fail 로 이미 배제.) 창을 띄우고 앱이 자동입력·클릭으로 딱 1번 더 시도한다.
    ⚠ 제출이 1회 추가되므로 **계정당·실행당 정확히 1회**. Akamai IP 차단은 이걸로도 대부분 못 뚫음.
    반환: (ok, cred_fail) — cred_fail 은 재시도가 비번오류를 드러냈을 때도 재큐 금지용."""
    log(f"  [{a.label}] 로그인 차단/미완료 → 반자동 1회 재시도(창 표시, 앱이 자동입력·클릭)")
    b.show()
    b.goto(WING_URL)                      # 신선 로그인 폼으로 리다이렉트 유도
    b.page.wait_for_timeout(1200)
    ok = False
    if b.authenticated():                 # 그새 로그인 완료됐을 수도
        ok = True
    elif b.autofill_login(a.account_id, pw, on_log=log):
        ok = b.wait_for_login(timeout=config.LOGIN_SEMI_WAIT_SEC, on_log=log,
                              tag=a.account_id, on_need_user=lambda: None,
                              blocked_grace=grace, skip_on_otp=True)
    log(f"  [{a.label}] 반자동 재시도 {'성공' if ok else '실패 — 이 계정 건너뜀'}")
    b.hide()
    cred_fail = (not ok) and b.classify_login()[0] == "error"   # 재시도가 비번오류를 드러냈을 때도 재큐 금지
    return ok, cred_fail


def _resolve_login_failure(b, a: Account, log, cred_fail: bool) -> bool:
    """로그인 미완료(not ok) 뒤처리 — 실패 유형 관측 후 제어흐름 분기(분해 전과 동일).

    반환 False(otp·일반 미완료=이 계정 건너뜀). raise LoginBlocked(Akamai)·LoginCredentialError(비번오류)."""
    code, detail = b.classify_login()
    ftype = session_state.failure_type_of(code, detail)   # 세분 실패분류(탐지코드는 불변)
    session_state.observe_auth_failure(a.account_id, ftype, final_url=b.page.url)
    if code == "blocked":   # Akamai 차단 → 서킷브레이커가 세도록 신호
        log(f"  [{a.label}] Akamai 로그인 차단 — 이 계정 건너뜀")
        raise LoginBlocked()
    if cred_fail:           # 비번오류/계정잠금/휴면 → 재시도 금지(계정잠금 방지), 이번 주기 완료처리
        log(f"  [{a.label}] 로그인 거부(비밀번호 오류/계정 상태: {detail[:60]}) — "
            "재시도 안 함(계정잠금 방지), 이 계정 건너뜀")
        raise LoginCredentialError(a.account_id)
    if code == "otp":       # 2차 인증(인증번호) 화면 → 대기 없이 건너뜀(다음 계정 진행, 다음 실행에서 재시도)
        log(f"  [{a.label}] ⚠ 2차 인증(인증번호) 필요 — 대기하지 않고 이 계정 건너뜀"
            " (다음 계정 진행 · 미완료로 남겨 다음 실행에서 재시도)")
        return False
    log(f"  [{a.label}] 로그인 미완료 — 이 계정 건너뜀")
    return False


def _discover_products(b, a: Account, date_from, date_to, log, ai_key: str | None = None, anchor_file=None):
    """발견 국면 — 상품조회/수정(vid 출처)·판매분석(지표)·재고현황·대장 스코핑/보강.

    반환: (products, tracked, metrics, inventory, sale_status, upbundle_vids). 판매분석·상품조회 **모두
    데이터 없음**이면 None(호출부가 (None,{},{},{},set()) 로 이 계정 건너뜀). upbundle_vids = 이번 상품조회의
    업번들(자동번들) 옵션 vid 집합(마스터 잔재 블록 자동삭제용, 소유자 2026-09-24). 제어흐름은 분해 전과 동일하다."""
    from .collector import (fetch_vendor_inventory, fetch_product_ids, products_from_vendor_inventory,
                            VendorInventoryFetchError, sale_status_by_vid, vid_meta_of)
    # ── vid·옵션·상품 = 상품조회/수정(전 상품·전 옵션 나열, 당일 판매 0 상품도 포함). 폴백=판매분석 발견 ──
    # (vi-detail-search 는 당일 판매활동 상품만 잡혀 판매 0 상품 vid 누락 → 상품조회/수정으로 vid 출처 교체)
    vendor_products = None
    vendor_status: dict[str, str] = {}   # {vid: 판매상태} — 상품조회 productStatus(전 상품·판매자배송 포함)
    listings: list = []                  # 진단(vid 대조)용 — 실패 시 빈 목록
    try:
        listings = fetch_vendor_inventory(b.page, log)
        vendor_products = products_from_vendor_inventory(listings, log)
        vendor_status = sale_status_by_vid(listings, log)   # 판매상태 출처(화면과 일치·판매자배송까지 커버)
    except VendorInventoryFetchError as exc:
        log(f"  [{a.label}] ⚠ 상품조회/수정(vid 출처) 실패 → 판매분석 발견으로 폴백 — {str(exc)[:120]}")
    # ── 지표(노출/판매/방문자) = 판매분석(vi-detail-search). 상품은 위 vendor_products 로 대체 ──
    got = _run_discover(b, a, date_from, date_to, vendor_products is not None, log)
    if got is None:        # 판매분석·상품조회 모두 데이터 없음 → 이 계정 건너뜀(관측은 _run_discover 가 남김)
        return None
    products, metrics = got
    if vendor_products is not None:
        products = vendor_products   # vid 출처 = 상품조회/수정(전 상품·전 옵션). 지표는 metrics(vi-detail)로 조인
    inventory, inv_names, rfm_status, inv_pids = _discover_inventory(b, a, products, log)
    # 판매상태 출처(§2.3 대장↔쿠팡 불일치 경고) = **상품조회 productStatus(전 상품·판매자배송 포함)** 우선,
    # 없으면(상품조회 실패) RFM isSaleSuspended(로켓그로스만) 폴백. 라이브 실측(2026-09-20 nicoable/sg0141n)에서
    # productStatus 가 ON_SALE/PARTIAL_ON_SALE/SUSPENDED 로 정상 변동·**화면 판매/승인상태와 일치** 확인.
    # (wellbing1107 은 '신규 등록 불가' 제한 계정이라 전부 SUSPENDED 였을 뿐 — 필드 자체는 정상.)
    sale_status = vendor_status if vendor_status else rfm_status
    # 이번 상품조회의 **업번들(자동번들) 옵션 vid 집합** — 마스터에 남은 옛 업번들 잔재 블록을 vid 기준으로
    # 자동삭제하는 데 쓴다(소유자 2026-09-24, _purge_upbundle_blocks). 상품조회 실패(listings=[])면 빈 집합.
    upbundle_vids = {o.vendor_item_id for lst in listings for o in lst.options
                     if getattr(o, "is_upbundle", False) and o.vendor_item_id}
    # 이번 상품조회에 **실제로 존재하는 전체 vid**(NORMAL·RFM·업번들 모두 = 코팡 현재 보유분). 죽은 중복 블록
    # 정리(_sweep_dead_duplicates)의 기준 — 이 집합에 없는 vid = 코팡서 사라짐. 상품조회 실패면 빈 집합(정리 skip).
    live_all_vids = {o.vendor_item_id for lst in listings for o in lst.options if o.vendor_item_id}
    vid_meta = vid_meta_of(listings)   # {vid: (판매가, 판매시작일)} — 헤더 표시(상품판매가·입고일 근사)
    # 추적 범위 = 입력 대장 상품(위탁 관리분)만. 대장 ↔ 쿠팡 = AI 중심 매칭 + VID 고정(D-009·지표는 당일 것).
    tracked, n_match = _match_to_ledger(b, a, products, metrics, inv_names, date_to, ai_key,
                                        vendor_products is not None, anchor_file, log)
    # 노출상품ID(productId) = vendor-inventory-items-with-vendorItems GET(판매방식·판매여부 무관·라이브 실측 2026-09-28)
    # — **추적(대장 매칭) 상품이 든 등록상품만** 조회(2026-10-09: 전 상품 조회가 와이에이치 3,146건·55마켓 2,236건에
    # 하루 약 58분·추적 상품은 계정당 1~3개). 재고/판매분석 pid 보다 완전 → 우선 병합.
    tracked_vids = {v for tp in tracked for o in tp.options for v in o.vendor_item_ids}
    vinv_ids = _vinv_ids_for_pid(listings, inv_pids, metrics, tracked_vids)
    item_pids = fetch_product_ids(b.page, vinv_ids, log) if vinv_ids else {}
    pid_by_vid = _pid_by_vid(inv_pids, metrics, item_pids)
    _log_discover_summary(a, products, metrics, inventory, sale_status, tracked, n_match, log)
    return (products, tracked, metrics, inventory, sale_status, upbundle_vids, live_all_vids,
            vid_meta, pid_by_vid)


def _match_to_ledger(b, a: Account, products, metrics, inv_names: dict, date_to, ai_key,
                     vendor_ok: bool, anchor_file, log):
    """대장 ↔ 쿠팡 매칭(D-009·소유자 2026-10-09) → (tracked, n_match).

    ①VID 고정 ②상품명 동일 ③의미 매칭(AI·후보 많으면 임베딩으로 추림) ④AI 실패 시 규칙 대체 → 색상 필터 공통 적용
    (product_match_ai). 상품조회 실패일(vendor_ok=False)은 당일 판매분석뿐이라 그로스 재고·최근 N일 roster 로 후보를
    보강하고, 고정 VID 는 스냅샷으로 유지한다. anchor_file=None 이면 고정 읽기/쓰기 안 함(도구·핀)."""
    from collections import Counter
    from . import product_match_ai as PMA
    from .match_anchor import AnchorFileError, load_anchors, save_anchors
    from .product_match import build_tracked
    cands = list(products)
    if not vendor_ok:
        cands += _roster_candidates(b, a, cands, inv_names, date_to, log)
    anchors: dict = {}
    if anchor_file is not None:
        try:
            anchors = load_anchors(a.account_id, anchor_file)
        except AnchorFileError as exc:
            log(f"  [{a.label}] ⚠ {exc} — 이번 실행은 고정 없이 매칭")
    expo = {vid: m.product_name for vid, m in (metrics or {}).items()}
    out = PMA.match_ledger(a.products, cands, anchors=anchors, vendor_ok=vendor_ok,
                           ask=PMA.openai_ask(ai_key) if ai_key else _no_ai, expo=expo,
                           embed=PMA.openai_embed(ai_key) if ai_key else None)
    for note in out.notes:
        log(f"  [{a.label}] {note}")
    tracked, n_match = build_tracked(a.products, PMA.resolved(out))
    _fill_exposed_names(b, a, tracked, metrics, date_to, log)   # 결과 블록 이름 = 현행 노출상품명(D-013)
    if anchor_file is not None:
        try:
            save_anchors(a.account_id, out.anchors, anchor_file)
        except OSError as exc:                          # 고정 저장 실패 = 다음 실행이 다시 매칭(비치명·명시)
            log(f"  [{a.label}] ⚠ 매칭 고정 저장 실패: {exc}")
    hows = Counter(pk.how for pk in out.picks.values())
    log(f"  [{a.label}] 매칭 경로: " + " · ".join(f"{k} {v}" for k, v in sorted(hows.items())) + f" (고정 {len(out.anchors)}줄)")
    return tracked, n_match


def _fill_exposed_names(b, a: Account, tracked, metrics, date_to, log) -> None:
    """추적 상품마다 **현행 쿠팡 노출상품명**을 `exposed_name` 에 채운다(상품명 현행화·D-013).
    출처 = 당일 판매분석(productName 이 잘려 오면 옵션명 앞부분으로 복원 `_display_title`) → 없으면 최근 N일 판매분석
    roster 1회 보충. 그래도 없으면 **오류(❌)로 기록**하고 ③순위 검색 노출명으로 그날 현행화(product_naming)한다
    (소유자 2026-10-09 "노출명이 매칭 안 되면 오류·반드시 현행화")."""
    from .collector import _display_title
    names = {vid: " ".join(_display_title(m.product_name, [m]).split())
             for vid, m in (metrics or {}).items() if m.product_name}

    def _pick(tp):
        return next((names[v] for o in tp.options for v in o.vendor_item_ids if v in names), "")
    want = [tp for tp in tracked if any(o.vendor_item_ids for o in tp.options)]
    if any(not _pick(tp) for tp in want):
        from .collector import fetch_sales_roster, SalesFetchError
        try:
            d0 = (date.fromisoformat(date_to) - timedelta(days=config.SALES_VID_WINDOW_DAYS)).isoformat()
            for p in fetch_sales_roster(b.page, d0, date_to, log):
                for o in p.options:
                    for v in o.vendor_item_ids:
                        names.setdefault(v, " ".join((p.title or p.name).split()))
        except SalesFetchError as exc:
            log(f"  [{a.label}] ❌ 노출상품명 보충({config.SALES_VID_WINDOW_DAYS}일) 조회 실패 — {str(exc)[:100]}")
    for tp in want:
        tp.exposed_name = _pick(tp)
        if not tp.exposed_name:
            vids = [v for o in tp.options for v in o.vendor_item_ids][:3]
            log(f"  [{a.label}] ❌ [상품명] 노출명 확인 실패: '{tp.ledger_name or tp.name}' VID {vids} — "
                f"최근 {config.SALES_VID_WINDOW_DAYS}일 판매분석에 없음 → ③순위 검색 노출명으로 현행화 예정"
                "(판매중지·검색 미노출이면 현행화 불가)")


def _no_ai(system: str, user: str) -> dict:
    """OpenAI 키 없음 — 예외로 알려 match_ledger 가 글자 규칙으로 대체(로그 명시)."""
    raise KeywordAIError("OpenAI 키 없음(설정 탭에서 입력)")


def _discover_inventory(b, a: Account, products, log):
    """로켓그로스/둘다 상품이 있으면 재고현황(RFM) 직접조회 — (inventory, inv_names, rfm_status, inv_pids).
    판매자배송 전용 계정은 재고 없어 생략. 실패해도 수집 전체는 진행(부가지표·사유 명시)."""
    from .collector import fetch_inventory, InventoryFetchError
    inventory: dict[str, int] = {}
    inv_names: dict[str, str] = {}
    rfm_status: dict[str, bool] = {}   # {vid: isSaleSuspended} — RFM 재고 API(로켓그로스만)
    inv_pids: dict[str, str] = {}      # {vid: productId} — 재고 API 노출상품ID(판매 0 상품 커버, 항목2)
    if any(p.kind in config.KINDS_WITH_INVENTORY for p in products):
        try:
            inventory, inv_names, rfm_status, inv_pids = fetch_inventory(b.page, log)   # 재고 수량 + roster + 판매상태 + productId
            log(f"  [{a.label}] 재고현황 {len(inventory)}개 옵션 조회")
        except InventoryFetchError as exc:   # 부가지표 — 실패해도 수집 전체는 진행(사유 명시)
            log(f"  [{a.label}] ⚠ 재고현황 조회 실패(계속) — {str(exc)[:120]}")
    return inventory, inv_names, rfm_status, inv_pids


def _vinv_ids_for_pid(listings: list, inv_pids: dict, metrics: dict, want_vids: set) -> list[str]:
    """노출상품ID GET 대상 등록상품ID(vendor_inventory_id) 목록 — **추적 상품 vid(want_vids)가 든 리스팅만**.

    `config.PRODUCT_ID_FETCH_ALL` True=그 리스팅 전부(판매자배송·무판매까지 완전 커버). False=그중 재고/판매분석에서
    pid 못 얻은 옵션을 가진 것만. 상품조회 실패(listings=[])·추적 vid 없음이면 빈 목록."""
    mine = [l for l in listings if l.vendor_inventory_id
            and any(o.vendor_item_id in want_vids for o in l.options)]
    if config.PRODUCT_ID_FETCH_ALL:
        return [l.vendor_inventory_id for l in mine]
    known = set(inv_pids) | {oid for oid, om in metrics.items() if getattr(om, "product_id", "")}
    return [l.vendor_inventory_id for l in mine if any(o.vendor_item_id not in known for o in l.options)]


def _pid_by_vid(inv_pids: dict, metrics: dict, item_pids: dict | None = None) -> dict[str, str]:
    """{vid: 노출상품ID(productId)} — 상품명 하이퍼링크(항목2).

    소스 3종 병합: ①**전 상품** vendor-inventory-items-with-vendorItems(`item_pids`·판매방식/판매여부 무관·가장 완전,
    2026-09-28) ② 재고 API(로켓그로스 재고 상품) ③ 판매분석(활동 상품). ①을 우선(전 상품 커버)하고, ①에 없는
    vid 만 ②③으로 보강(①실패·부분실패 대비). 상품조회(search) 응답엔 공개 productId 가 없음(실측 2026-09-26)."""
    pid_by_vid: dict[str, str] = dict(item_pids or {})     # ① 전 상품(가장 완전) 우선
    for oid, pid in dict(inv_pids).items():                 # ② 재고 보강(①에 없을 때만)
        if pid and oid not in pid_by_vid:
            pid_by_vid[oid] = pid
    for oid, om in metrics.items():                         # ③ 판매분석 보강(①②에 없을 때만)
        pid = getattr(om, "product_id", "")
        if pid and oid not in pid_by_vid:
            pid_by_vid[oid] = pid
    return pid_by_vid


def _log_discover_summary(a: Account, products, metrics, inventory, sale_status, tracked, n_match, log) -> None:
    """계정 요약(진행경과·오류추적): 소스별 개수 + 대장 매칭/미매칭(vid 없는 상품=미매칭·블록 미생성 D-008)."""
    unmatched = [tp.name for tp in tracked if not any(o.vendor_item_ids for o in tp.options)]
    vid_count = sum(len(o.vendor_item_ids) for tp in tracked for o in tp.options)
    log(f"  [계정 {a.account_id}/{a.label}] 소스: 상품조회 {len(products)}상품 · 판매분석 {len(metrics)}옵션"
        f" · 재고 {len(inventory)}vid · 판매상태 {len(sale_status)}vid")
    log(f"  [계정 {a.account_id}/{a.label}] 대장 {len(a.products)} → 추적 {len(tracked)}"
        f"(매칭 {n_match}·vid {vid_count}) · 미매칭(vid없음) {len(unmatched)}"
        + (f": {[_short(n, 22) for n in unmatched[:10]]}{'…' if len(unmatched) > 10 else ''}" if unmatched else ""))


def _run_discover(b, a: Account, date_from, date_to, has_vendor: bool, log):
    """판매분석(vi-detail-search) 지표 수집 — PWTimeout(데이터없음)·Failed to fetch(1회 재시도) 처리.

    반환: (products, metrics). 당일 데이터 없어도 상품조회 상품이 있으면 ([], {}) 로 계속. 판매분석·상품조회
    **모두 없음**(has_vendor=False + PWTimeout)이면 collection_empty 관측 후 None(호출부가 이 계정 건너뜀)."""
    from .collector import discover
    from playwright.sync_api import TimeoutError as PWTimeout   # 판매데이터 없음 판별용

    def _empty_or_skip():   # '엑셀 다운로드'/데이터 미표시 = 당일 판매 상품 없음
        if not has_vendor:
            log(f"  [{a.label}] 판매분석·상품조회 모두 데이터 없음 — 건너뜀")
            session_state.observe_collection_empty(a.account_id)
            return None
        log(f"  [{a.label}] 판매분석 당일 데이터 없음 — 상품조회/수정 상품만 추적(vid 확보, 지표 0)")
        return [], {}

    try:
        return discover(b.page, date_from, date_to, log)   # 같은 세션에서 즉시 수집(지표)
    except PWTimeout:
        return _empty_or_skip()
    except Exception as exc:   # 신선 로그인 직후 페이지 미안착 → fetch 중단(Failed to fetch). wing 재안착 후 1회 재시도
        if "Failed to fetch" not in str(exc):
            raise
        log(f"  [{a.label}] discover fetch 중단(Failed to fetch) — wing 재안착 후 1회 재시도")
        b.goto(WING_URL)
        b.page.wait_for_timeout(2500)
        try:
            return discover(b.page, date_from, date_to, log)
        except PWTimeout:
            return _empty_or_skip()


def _roster_candidates(b, a: Account, cands, inv_names: dict, date_to, log) -> list:
    """상품조회 실패일 후보 보강 — 그로스 재고 roster + 최근 N일 판매분석 roster 중 **아직 후보에 없는 vid** 상품만.
    (당일 판매·방문 0 상품도 대장과 맞출 수 있게. 지표는 당일 것만 기록 — 넓은기간 합계 미반영, 2026-09-13)"""
    from .collector import fetch_sales_roster, SalesFetchError
    extra = _roster_from_names(inv_names, config.KIND_CONTRACT)   # 그로스 재고 roster(판매 무관 vid)
    try:
        d0 = (date.fromisoformat(date_to) - timedelta(days=config.SALES_VID_WINDOW_DAYS)).isoformat()
        extra += fetch_sales_roster(b.page, d0, date_to, log)     # 최근 N일 vid+이름(지표 미반영)
    except SalesFetchError as exc:   # 보강 실패는 비치명적 — 재고 roster 만으로 진행
        log(f"  [{a.label}] ⚠ vid 보강 {config.SALES_VID_WINDOW_DAYS}일 조회 실패(계속) — {str(exc)[:100]}")
    seen = {v for p in cands for o in p.options for v in o.vendor_item_ids}
    out = [p for p in extra if not ({v for o in p.options for v in o.vendor_item_ids} & seen)]
    if out:
        log(f"  [{a.label}] 상품조회 실패 → 재고/최근 {config.SALES_VID_WINDOW_DAYS}일 후보 {len(out)}개 보강")
    return out


def _roster_from_names(names_by_vid: dict, kind: str) -> list:
    """{옵션ID(vid): 등록상품명} → 매칭 후보 Product 목록(상품명으로 그룹, 옵션=vid).

    그로스 재고에서 얻은 **판매 무관 vid·상품명**을 AI 매칭 후보(상품조회 실패일)로 만든다
    (당일 판매 0인 그로스 상품의 vid 보강용). 지표는 없다 — 정체(vid) 보강 전용."""
    from .input_list import Option, Product
    by_name: dict[str, list[str]] = {}
    for vid, nm in (names_by_vid or {}).items():
        nm = (nm or "").strip()
        if nm and vid:
            by_name.setdefault(nm, []).append(str(vid))
    return [Product(name=nm, title=nm, kind=kind,
                    options=[Option("", [v]) for v in vids]) for nm, vids in by_name.items()]


def _vtag(vids) -> str:
    """로그용 **vid 태그**(오류·진행 추적 키). 여러 개면 '/'로 잇고, 없으면 '없음'.

    모든 상품/옵션 단위 로그 앞에 붙여 `grep vid=<값>` 으로 한 상품의 전 과정(수집→지표→키워드→순위→
    오류)을 추적할 수 있게 한다. vid 없는(미매칭) 상품은 vid=없음 → 등록상품명으로 추적한다."""
    vs = [str(v) for v in (vids or []) if v]
    return "vid=" + ("/".join(vs) if vs else "없음")


def _short(name: str, n: int = 30) -> str:
    """로그용 상품명 축약(길면 …). 내부 개행 제거."""
    s = " ".join(str(name or "").split())
    return s if len(s) <= n else s[:n] + "…"


def _ilog(log, tag: str, vids, name: str = "", msg: str = "", *, kind: str = "") -> None:
    """상품/옵션 단위 로그 **공통 포맷**(진행상황·디버깅용) — vid 를 **항상** 포함한다.

    형식: `  [{tag}] vid=.. [{상품명}][ [{kind}]][ {msg}]`. `grep "vid=<값>"` 한 번으로 그 상품의
    전 과정(발견→지표→재고→키워드→순위→오류)을 이어서 볼 수 있게 태그·vid 를 앞에 고정한다.
    name/kind/msg 는 있을 때만 붙는다. log 가 None 이면 무시(호출부 가드 불필요)."""
    if log is None:
        return
    parts = [f"[{tag}]", _vtag(vids)]
    if name:
        parts.append(_short(name))
    if kind:
        parts.append(f"[{kind}]")
    if msg:
        parts.append(msg)
    log("  " + " ".join(parts))

