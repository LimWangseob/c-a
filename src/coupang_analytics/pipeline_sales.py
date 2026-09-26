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
from . import wing_session
from .browser import WING_URL, WingBrowser
from .input_list import Account
from .kw_ai import KeywordAIError, recommend_title
from .kw_recommend import (attack_priority, comp_from_idx, diagnose_exposure,
                           keyword_in_title, rank_label, select_keywords_light)
from .kw_volume import NaverAdApi
from .rank import make_matcher
from .session_store import SessionStore
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


def _login_and_discover(a: Account, date_from, date_to, get_password, log, login: bool = True,
                        semi: bool = False):
    """계정 하나: (필요시) 로그인 → **같은 신선한 세션**에서 즉시 판매분석 발견 + 지표.

    반환: (report_account[활동 상품만] | None, {옵션ID: OptionMetric}, {옵션ID: 재고수량},
    {옵션ID: 판매상태}, {업번들 vid 집합}, {상품조회 전체 vid 집합}). 4번째 판매상태맵 = 상품조회 productStatus
    문자열(판매자배송 포함 전 상품) 또는 폴백 RFM isSaleSuspended(bool). 5번째 = 업번들 vid(잔재 자동삭제용). 6번째 =
    이번 상품조회에 존재하는 전체 vid(죽은 중복 블록 정리 기준). 로그인 미완료면 (None,{},{},{},set(),set()) → 다음 계정으로.
    login=False(세션우선 1차): 세션 없으면 자동제출하지 않고 **NeedLogin** 을 던져 뒤로 미룬다
    (반복 자동로그인 = IP 차단 유발이라, 세션 살아있는 계정을 먼저 다 수집). Akamai 차단 시 LoginBlocked.
    semi=True(**반자동 판매수집**): 창을 **처음부터 보이게**(offscreen=False) 띄우고 **무인 아님**(사람이
    2차인증/직접로그인 처리)으로 로그인 → 그 신뢰 창에서 수집. ③ 반자동과 같은 '보이는 신뢰 세션' 방식.
    """
    from . import collector
    from .collector import save_discovered   # 지연 import
    pw = get_password(a.account_id) if get_password else None
    # 기본은 **창 숨김**(offscreen). 반자동(semi)이면 처음부터 보이게 띄운다(사람이 2차인증 처리).
    with WingBrowser(profile_dir=account_profile(a.account_id), offscreen=not semi) as b:
        if not _ensure_login(b, a, pw, log, login=login, semi=semi):
            return None, {}, {}, {}, set(), set(), {}, {}   # 이 계정 건너뜀(무인 비번없음·otp·로그인 미완료)
        collector.reset_raw()                # 계정별 응답 원문 버퍼 초기화(파일 분리)
        found = _discover_products(b, a, date_from, date_to, log)
        _dump_raw(a.account_id, log)         # 3 API 응답 원문 저장(가공 없음·분석용). found None(데이터없음)이어도 남김
        if found is None:                    # 판매분석·상품조회 모두 데이터 없음 → 건너뜀
            return None, {}, {}, {}, set(), set(), {}, {}
        (products, tracked, metrics, inventory, sale_status, upbundle_vids, live_all_vids,
         vid_meta, pid_by_vid) = found
        _persist_session(a, b, log)                                 # 세션 3요소+쿠키 영속(부가)
        session_state.observe_collection_done(a.account_id)         # 관측: 이 계정 수집 완료 시각
    save_discovered(a.account_id, products)   # (요약 로그는 위 with 블록에서 계정 단위로 남김)
    report = Account(a.account_id, a.representative, a.business_name, tracked)
    report.ledger_products = set(a.ledger_products)   # ⑥: 줄 존재 전체(활성+판매중지/취소선) 전파 — 완전삭제 판정용
    return (report, metrics, inventory, sale_status, upbundle_vids, live_all_vids, vid_meta, pid_by_vid)


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
    _wait_to = config.LOGIN_UNATTENDED_WAIT_SEC if unattended else 300
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


def _discover_products(b, a: Account, date_from, date_to, log):
    """발견 국면 — 상품조회/수정(vid 출처)·판매분석(지표)·재고현황·대장 스코핑/보강.

    반환: (products, tracked, metrics, inventory, sale_status, upbundle_vids). 판매분석·상품조회 **모두
    데이터 없음**이면 None(호출부가 (None,{},{},{},set()) 로 이 계정 건너뜀). upbundle_vids = 이번 상품조회의
    업번들(자동번들) 옵션 vid 집합(마스터 잔재 블록 자동삭제용, 소유자 2026-09-24). 제어흐름은 분해 전과 동일하다."""
    from .collector import (fetch_vendor_inventory, products_from_vendor_inventory,
                            VendorInventoryFetchError, sale_status_by_vid, vid_meta_of)
    from .product_match import scope_to_ledger
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
    pid_by_vid = _pid_by_vid(inv_pids, metrics)
    # 추적 범위 = 입력 대장 상품(위탁 관리분)만. 당일 발견을 매칭해 노출제목·vid·구분 부여(지표는 당일 것).
    tracked, n_match = scope_to_ledger(a.products, products)
    tracked, n_match = _augment_vids(b, a, tracked, n_match, inv_names, date_to, log)
    _log_discover_summary(a, products, metrics, inventory, sale_status, tracked, n_match, log)
    return (products, tracked, metrics, inventory, sale_status, upbundle_vids, live_all_vids,
            vid_meta, pid_by_vid)


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


def _pid_by_vid(inv_pids: dict, metrics: dict) -> dict[str, str]:
    """{vid: 노출상품ID(productId)} — 상품명 하이퍼링크(항목2). 재고 API(판매 0 상품 커버) ∪ 판매분석(활동 상품).
    상품조회(vendor-inventory)엔 공개 productId 가 없어 이 두 소스로만 확보(실측 2026-09-26)."""
    pid_by_vid: dict[str, str] = dict(inv_pids)
    for oid, om in metrics.items():
        pid = getattr(om, "product_id", "")
        if pid and oid not in pid_by_vid:
            pid_by_vid[oid] = pid
    return pid_by_vid


def _log_discover_summary(a: Account, products, metrics, inventory, sale_status, tracked, n_match, log) -> None:
    """계정 요약(진행경과·오류추적): 소스별 개수 + 대장 매칭/미매칭(vid 없는 상품은 등록명으로 추적)."""
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


def _augment_vids(b, a: Account, tracked, n_match: int, inv_names: dict, date_to, log):
    """대장에 있는데 당일 판매·방문 0이라 미매칭(vid 없음)인 상품 → 그로스 재고 vid + 최근 N일 판매분석
    vid 로 **정체(vid)만** 보강(지표는 당일 것만 기록 — 넓은기간 합계 미반영, 사용자 정책 2026-09-13).

    반환: (tracked, n_match). 미매칭이 없으면 그대로 반환(no-op)."""
    from .collector import fetch_sales_roster, SalesFetchError
    from .product_match import augment_unmatched
    if not any(not any(o.vendor_item_ids for o in tp.options) for tp in tracked):
        return tracked, n_match
    extra = _roster_from_names(inv_names, config.KIND_CONTRACT)   # 그로스 재고 roster(판매 무관 vid)
    try:
        d0 = (date.fromisoformat(date_to) - timedelta(days=config.SALES_VID_WINDOW_DAYS)).isoformat()
        extra += fetch_sales_roster(b.page, d0, date_to, log)     # 최근 N일 vid+이름(지표 미반영)
    except SalesFetchError as exc:   # 보강 실패는 비치명적 — 재고 roster 만으로 진행
        log(f"  [{a.label}] ⚠ vid 보강 {config.SALES_VID_WINDOW_DAYS}일 조회 실패(계속) — {str(exc)[:100]}")
    tracked, added = augment_unmatched(a.products, tracked, extra)
    n_match += added
    if added:
        log(f"  [{a.label}] 당일 미매칭 {added}개 vid 보강(그로스 재고/최근 {config.SALES_VID_WINDOW_DAYS}일 · 지표는 당일 유지)")
    return tracked, n_match


def _persist_session(a: Account, b, log) -> None:
    """로그인 성공 세션(3요소+쿠키[_abck 포함])을 영속 — 재사용·생존검증·데이터 HTTP 호출용.

    수집이 이미 끝난 뒤의 **부가 작업**이라, 실패해도 수집 결과엔 영향이 없다(사유를 명시 로그).
    ⚠️ is_alive/extract_vendor_id 의 엔드포인트는 사무실 라이브에서 최종 검증 대상.
    """
    try:
        alive = wing_session.is_alive(b.page)
        vid = wing_session.extract_vendor_id(b.page)
        SessionStore().save(a.account_id, wing_session.capture(b.context, vid))
        log(f"  [세션] 저장됨 (생존검증={alive}, vendorId={'추출' if vid else '미확인'})")
    except Exception as exc:
        log(f"  [세션] 영속 스킵 — {exc.__class__.__name__}: {str(exc)[:60]}")


def _roster_from_names(names_by_vid: dict, kind: str) -> list:
    """{옵션ID(vid): 등록상품명} → 매칭 후보 Product 목록(상품명으로 그룹, 옵션=vid).

    그로스 재고에서 얻은 **판매 무관 vid·상품명**을 scope_to_ledger/augment_unmatched 후보로 만든다
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

