"""핀 테스트 — `_login_and_discover` / `_track_ranks_semi` 를 **실제 코드로** 오프라인 구동.

배경: `tools/simulate_pipeline.py` 는 이 두 함수를 **통째로 페이크**(`_fake_login_and_discover`·
`_fake_track_ranks_semi`)해서 돌린다 → 실제 함수 본문이 오프라인 검증에서 **0% 실행**된다. 그래서
이 두 괴물함수를 분해(리팩터링)할 때 회귀를 못 잡는다. 이 파일은 **경계만** 페이크하고(브라우저=
`WingBrowser`, 수집=collector 함수, 순위=rank 헬퍼) **실제 함수 본문을 그대로 돌려** 로그인 국면·
발견 국면·반자동 순위 상태기계의 **제어흐름(이른 return·예외·재시도·쿨다운/중단)** 을 고정한다.

분해 전/후로 이 파일이 초록이면 **행동 불변**이 보증된다(§CODE_HEALTH_PLAN 단계4 착수 레시피).
실행: python tools/pin_login_ranks.py   (로그인·네이버·OpenAI·실 브라우저 호출 없음, 결정적)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics import config  # noqa: E402
from coupang_analytics import collector as C  # noqa: E402
from coupang_analytics import pipeline as P  # noqa: E402
from coupang_analytics import rank as R  # noqa: E402
from coupang_analytics.input_list import Account, Option, Product  # noqa: E402
from coupang_analytics.report import OptionMetric  # noqa: E402
from coupang_analytics.workbook import OutputWorkbook  # noqa: E402
from playwright.sync_api import TimeoutError as PWTimeout  # noqa: E402


def _check(cond: bool, msg: str) -> None:
    print(f"    {'[통과]' if cond else '[실패]'} {msg}")
    if not cond:
        raise AssertionError(msg)


# ── 가짜 브라우저(WingBrowser 경계) ─────────────────────────────
# 로그인 국면이 부르는 것만 구현: goto/show/hide/to_front/authenticated/autofill_login/
# wait_for_login/classify_login + page(wait_for_timeout/url/add_init_script/evaluate/keyboard).
# 동작은 모듈 전역 _SPEC(딕셔너리)로 시험마다 지정한다. 시퀀스 값은 호출 순서대로 소비(마지막 값 유지).
_SPEC: dict = {}
_COUNT: dict = {}


def _seq(name: str, calls: int, default):
    seq = _SPEC.get(name, [default])
    return seq[min(calls - 1, len(seq) - 1)]


class _FakeKeyboard:
    def press(self, *a, **k):
        pass


class _FakePage:
    def __init__(self, url: str):
        self.url = url
        self.keyboard = _FakeKeyboard()

    def wait_for_timeout(self, ms):
        pass

    def add_init_script(self, script):
        pass

    def evaluate(self, script):
        return None


class _FakeWing:
    def __init__(self, *a, **k):
        self.page = _FakePage(_SPEC.get("url", "https://wing.coupang.com/"))
        self.context = SimpleNamespace(browser=None, pages=[self.page])
        self._auth = 0
        self._wait = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def show(self):
        _COUNT["show"] = _COUNT.get("show", 0) + 1

    def hide(self):
        pass

    def to_front(self):
        pass

    def goto(self, url):
        pass

    def authenticated(self) -> bool:
        self._auth += 1
        return bool(_seq("authenticated", self._auth, False))

    def autofill_login(self, account_id, pw, on_log=None) -> bool:
        _COUNT["autofill"] = _COUNT.get("autofill", 0) + 1
        return bool(_SPEC.get("autofill", True))

    def wait_for_login(self, **kwargs) -> bool:
        self._wait += 1
        _COUNT["wait_for_login"] = _COUNT.get("wait_for_login", 0) + 1
        return bool(_seq("wait_for_login", self._wait, False))

    def classify_login(self):
        return tuple(_SPEC.get("classify", ("timeout", "")))


# ── 발견 국면(collector 경계) 가짜 ─────────────────────────────
_LEDGER_NAME = "핀상품"
_VID = "vidPIN"
_LISTINGS = object()   # fetch_vendor_inventory 반환(불투명) — 아래 두 함수에 전달


def _install_collector_fakes(*, vendor_ok=True, discover_behavior="ok"):
    """collector 함수를 시험용으로 교체. discover_behavior: ok|pwtimeout|failed_then_ok."""
    _dstate = {"n": 0}

    def fake_fetch_vendor_inventory(page, log):
        if not vendor_ok:
            raise C.VendorInventoryFetchError("가짜 상품조회 실패")
        return _LISTINGS

    def fake_products_from_vendor_inventory(listings, log):
        opt = Option(label="", vendor_item_ids=[_VID], product_ids=[])
        return [Product(name=_LEDGER_NAME, options=[opt], kind=config.KIND_CONTRACT)]

    def fake_sale_status_by_vid(listings, log):
        return {_VID: "판매중"}

    def fake_discover(page, date_from, date_to, log):
        _dstate["n"] += 1
        if discover_behavior == "pwtimeout":
            raise PWTimeout("가짜 판매분석 데이터 없음")
        if discover_behavior == "failed_then_ok" and _dstate["n"] == 1:
            raise Exception("Failed to fetch")   # 신선 로그인 직후 페이지 미안착 프록시
        metrics = {_VID: OptionMetric(option_id=_VID, product_name=_LEDGER_NAME, option_name="",
                                      item_id="item1", views=100, sales=7, visitors=50,
                                      registration_type="RFM")}
        opt = Option(label="", vendor_item_ids=[_VID], product_ids=[])
        return [Product(name=_LEDGER_NAME, options=[opt], kind=config.KIND_CONTRACT)], metrics

    def fake_fetch_inventory(page, log):
        return {_VID: 42}, {_VID: _LEDGER_NAME}, {_VID: False}

    def fake_fetch_sales_roster(page, d0, d1, log):
        return []

    C.fetch_vendor_inventory = fake_fetch_vendor_inventory
    C.products_from_vendor_inventory = fake_products_from_vendor_inventory
    C.sale_status_by_vid = fake_sale_status_by_vid
    C.discover = fake_discover
    C.fetch_inventory = fake_fetch_inventory
    C.fetch_sales_roster = fake_fetch_sales_roster
    C.save_discovered = lambda account_id, products: None
    return _dstate


def _ledger_account() -> Account:
    opt = Option(label="", vendor_item_ids=[_VID], product_ids=[])
    prod = Product(name=_LEDGER_NAME, options=[opt], kind=config.KIND_CONTRACT)
    return Account("pin1", "대표", "비즈핀", [prod])


def _run_login(*, login=True, semi=False):
    return P._login_and_discover(_ledger_account(), "2026-09-19", "2026-09-20",
                                 lambda aid: "pw", lambda m: None, login=login, semi=semi)


# ── 로그인/발견 국면 핀 시나리오 ───────────────────────────────
def pin_session_reuse():
    print("[핀 A] 세션 재사용(authenticated=True) → 로그인 안 하고 즉시 발견·수집")
    _SPEC.clear(); _COUNT.clear()
    _SPEC["authenticated"] = [True]
    _install_collector_fakes()
    acct, metrics, inventory, sale_status = _run_login()
    _check(acct is not None and len(acct.products) == 1, "발견·매칭된 계정 반환(상품 1)")
    _check(metrics.get(_VID) is not None, "판매분석 지표(vi-detail) 전달됨")
    _check(inventory.get(_VID) == 42, "로켓그로스 재고 조회됨")
    _check(sale_status.get(_VID) == "판매중", "판매상태=상품조회 productStatus 우선")
    _check(_COUNT.get("autofill", 0) == 0, "세션 있으면 자동입력 안 함(로그인 생략)")


def pin_need_login():
    print("[핀 B] 세션우선 1차 패스 — 세션 없으면 NeedLogin(자동제출 안 함)")
    _SPEC.clear(); _COUNT.clear()
    _SPEC["authenticated"] = [False]
    _install_collector_fakes()
    raised = False
    try:
        _run_login(login=False)
    except P.NeedLogin:
        raised = True
    _check(raised, "NeedLogin 예외로 로그인 대기열에 미룸")
    _check(_COUNT.get("autofill", 0) == 0, "1차 패스는 자동입력·제출 안 함")


def pin_login_blocked():
    print("[핀 C] Akamai 로그인 차단(classify 'blocked') → LoginBlocked(서킷브레이커)")
    _SPEC.clear(); _COUNT.clear()
    _SPEC["authenticated"] = [False]
    _SPEC["wait_for_login"] = [False]
    _SPEC["classify"] = ("blocked", "Access Denied")
    _install_collector_fakes()
    raised = False
    try:
        _run_login()
    except P.LoginBlocked:
        raised = True
    _check(raised, "LoginBlocked 예외 발생(차단 계정 건너뜀)")


def pin_credential_error():
    print("[핀 D] 비번오류/계정잠금(classify 'error') → LoginCredentialError, **재시도 안 함**")
    _SPEC.clear(); _COUNT.clear()
    _SPEC["authenticated"] = [False]
    _SPEC["wait_for_login"] = [False]
    _SPEC["classify"] = ("error", "비밀번호가 올바르지 않습니다")
    _install_collector_fakes()
    raised = False
    try:
        _run_login()
    except P.LoginCredentialError:
        raised = True
    _check(raised, "LoginCredentialError 예외(확정 자격 실패)")
    _check(_COUNT.get("wait_for_login", 0) == 1, "로그인 대기 1회뿐 — 재제출 안 함(계정잠금 방지)")


def pin_otp_skip():
    print("[핀 E] 2차 인증(classify 'otp') → 대기 없이 건너뜀(None 반환)")
    _SPEC.clear(); _COUNT.clear()
    _SPEC["authenticated"] = [False]
    _SPEC["wait_for_login"] = [False]
    _SPEC["classify"] = ("otp", "인증번호를 입력하세요")
    _install_collector_fakes()
    acct, metrics, inv, status = _run_login()
    _check(acct is None and metrics == {} and inv == {} and status == {},
           "(None,{},{},{}) 반환 — 다음 계정 진행(다음 실행에서 재시도)")
    _check(_COUNT.get("wait_for_login", 0) == 1, "otp는 재시도 없이 1회 후 건너뜀")


def pin_semi_retry_recover():
    print("[핀 F] 무인 소프트차단 → 반자동 1회 재시도로 로그인 성공 → 발견·수집")
    _SPEC.clear(); _COUNT.clear()
    # 초기 미인증 → 자동입력·대기 실패(soft) → 재시도에서 authenticated True 로 회복
    _SPEC["authenticated"] = [False, True]
    _SPEC["wait_for_login"] = [False]
    _SPEC["classify"] = ("timeout", "")
    _install_collector_fakes()
    acct, metrics, inventory, sale_status = _run_login()
    _check(acct is not None and len(acct.products) == 1, "반자동 재시도 후 수집 성공(상품 1)")
    _check(_COUNT.get("autofill", 0) == 1, "자동입력 1회(재시도는 authenticated로 회복 — 재제출 없음)")


def pin_discover_empty_uses_vendor():
    print("[핀 G] 판매분석 데이터 없음(PWTimeout) → 상품조회 vid로 계속(지표 0)")
    _SPEC.clear(); _COUNT.clear()
    _SPEC["authenticated"] = [True]
    _install_collector_fakes(discover_behavior="pwtimeout")
    acct, metrics, inventory, sale_status = _run_login()
    _check(acct is not None and len(acct.products) == 1, "상품조회 vid로 상품 추적(건너뛰지 않음)")
    _check(metrics == {}, "판매분석 지표는 비어 있음(당일 판매 0)")
    _check(sale_status.get(_VID) == "판매중", "판매상태는 상품조회에서 확보")


def pin_discover_failed_then_ok():
    print("[핀 H] discover 'Failed to fetch' → wing 재안착 후 1회 재시도 성공")
    _SPEC.clear(); _COUNT.clear()
    _SPEC["authenticated"] = [True]
    dstate = _install_collector_fakes(discover_behavior="failed_then_ok")
    acct, metrics, inventory, sale_status = _run_login()
    _check(acct is not None and metrics.get(_VID) is not None, "재시도로 지표 수집 성공")
    _check(dstate["n"] == 2, "discover 정확히 2회 호출(첫 실패→재시도)")


def pin_vendor_fallback_to_discover():
    print("[핀 I] 상품조회 실패(VendorInventoryFetchError) → 판매분석 발견으로 폴백")
    _SPEC.clear(); _COUNT.clear()
    _SPEC["authenticated"] = [True]
    _install_collector_fakes(vendor_ok=False, discover_behavior="ok")
    acct, metrics, inventory, sale_status = _run_login()
    _check(acct is not None and len(acct.products) == 1, "폴백(판매분석 발견)으로 상품 확보")
    _check(metrics.get(_VID) is not None, "판매분석 지표 전달됨")
    _check(sale_status.get(_VID) is False, "상품조회 실패 → 판매상태 RFM(isSaleSuspended=False) 폴백")


# ── 반자동 순위 상태기계 핀 ────────────────────────────────────
def _rank_wb(path: Path, *, keywords=("kw1", "kw2"), second_optionless=False) -> OutputWorkbook:
    """반자동 순위 구동용 최소 워크북 — 계정1·상품1(vid·키워드·최신 일자)."""
    wb = OutputWorkbook.empty()
    biz = "비즈R"
    wb.ensure_account(biz)
    wb.ensure_product_block(biz, "상품R", config.KIND_CONTRACT, list(keywords), registered="상품R")
    wb.set_product_vids(biz, "상품R", ["vidR"])
    if second_optionless:   # 다중옵션 2차 블록(키워드 없음) → 순위 대상 아님(건너뜀 검증)
        wb.ensure_product_block(biz, "상품R (그레이)", config.KIND_CONTRACT, [],
                                rank_rows=False, registered="상품R")
        wb.set_product_vids(biz, "상품R (그레이)", ["vidGray"])
    wb.ensure_date(biz, "2026-09-20")
    wb.save(path)
    return wb


def _install_rank_fakes(wait_results, serp=None):
    """반자동 순위 헬퍼 경계 페이크. wait_results=키워드마다 (page, blocked) 반환할 리스트(순서 소비).
    serp=(parse_serp_rank 반환 result, scanned) — 기본은 3위 발견. 미발견은 ({'제품':(None,None)}, 개수)."""
    state = {"i": 0}

    def fake_wait(browser, kw, should_stop, timeout):
        i = state["i"]
        state["i"] += 1
        return wait_results[min(i, len(wait_results) - 1)]

    serp = serp if serp is not None else ({"제품": (3, None)}, 3)
    P._prefill_search = lambda browser, kw: True
    P._submit_search = lambda browser: None
    P._wait_results_loaded = fake_wait
    P.human_mouse = SimpleNamespace(browse_serp=lambda pg: None)
    P.random = SimpleNamespace(uniform=lambda a, b: 0.0)   # 타이핑 후 '짧게 멈춤' pause 를 0으로(시험 단축)
    R.parse_serp_rank = lambda pg, matcher, max_rank=None: serp   # (result, scanned) 튜플
    return state


def pin_rank_success():
    print("[핀 J] 반자동 순위 정상 — 자동검색·결과로드·파싱으로 순위 기록")
    _SPEC.clear(); _COUNT.clear()
    config.RANK_SEMI_AUTOSUBMIT = True
    d = Path(tempfile.mkdtemp()); path = d / "m.xlsx"
    wb = _rank_wb(path)
    pg = object()
    _install_rank_fakes([(pg, False), (pg, False)])
    logs: list[str] = []
    P._track_ranks_semi(wb, path, logs.append, lambda: False)
    joined = "\n".join(logs)
    dt = wb.latest_date("비즈R")   # apply_style 이 ISO→'월.일'로 재라벨 → 실행 후 라벨로 검증
    _check(wb.is_rank_filled("비즈R", "상품R", "kw1", dt), "kw1 순위 기록됨")
    _check(wb.is_rank_filled("비즈R", "상품R", "kw2", dt), "kw2 순위 기록됨")
    # B-1 종료 요약: 무차단이면 유지 판단·되돌림 권고 없음
    _check("[순위요약]" in joined and "차단/쿨다운 0" in joined, "무차단 종료 요약(측정·쿨다운·차단 집계)")
    _check("되돌리는 것을 권고" not in joined, "무차단 시 간격 되돌림 권고 없음")


def pin_rank_not_found():
    print("[핀 J2] 반자동 순위 미발견 → '센 개수 위밖' 기록(예 '44위밖', 공란 아님=재측정 안 함)")
    _SPEC.clear(); _COUNT.clear()
    config.RANK_SEMI_AUTOSUBMIT = True
    config.RANK_SEMI_AUTO_MAX_MISS = 3
    config.RANK_SEMI_COOLDOWN_MAX = 4
    d = Path(tempfile.mkdtemp()); path = d / "m.xlsx"
    wb = _rank_wb(path)
    pg = object()
    # 페이지는 정상 로드(차단 아님)인데 상품이 그 페이지에 없음 → scanned=44 개까지 셈
    _install_rank_fakes([(pg, False), (pg, False)], serp=({"제품": (None, None)}, 44))
    P._track_ranks_semi(wb, path, lambda m: None, lambda: False)
    dt = wb.latest_date("비즈R")
    _check(wb.is_rank_filled("비즈R", "상품R", "kw1", dt), "미발견도 '기록됨'(공란 아님=같은 날 재측정 안 함)")
    row = wb._kw_row[("비즈R", "상품R", "kw1")]
    col = wb._date_col["비즈R"][dt]
    val = wb.wb["비즈R"].cell(row, col).value
    _check(val == "44위밖", f"미발견 = 센 개수 위밖('44위밖') — 실제 {val!r}")


def pin_rank_block_then_recover():
    print("[핀 K] 차단 감지 → 쿨다운 후 자동 재개(하드중단 아님) → 다음 키워드 측정")
    _SPEC.clear(); _COUNT.clear()
    config.RANK_SEMI_AUTOSUBMIT = True
    config.RANK_SEMI_AUTO_MAX_MISS = 1     # 1회 미로딩이면 곧장 쿨다운 판정(빠른 시험)
    config.RANK_SEMI_COOLDOWN_SEC = 0      # 쿨다운 즉시 종료
    config.RANK_SEMI_COOLDOWN_MAX = 2      # 2회까지는 재개(초과 시 중단)
    d = Path(tempfile.mkdtemp()); path = d / "m.xlsx"
    wb = _rank_wb(path)
    pg = object()
    logs: list[str] = []
    _install_rank_fakes([(None, True), (pg, False)])   # kw1 차단, kw2 성공
    P._track_ranks_semi(wb, path, logs.append, lambda: False)
    joined = "\n".join(logs)
    dt = wb.latest_date("비즈R")
    _check(not wb.is_rank_filled("비즈R", "상품R", "kw1", dt), "kw1 차단 → 공란(재측정 대상)")
    _check(wb.is_rank_filled("비즈R", "상품R", "kw2", dt), "kw2 재개 후 측정됨")
    _check("쿨다운 후 자동 재개" in joined and "IP 회복 불가" not in joined, "쿨다운 재개(하드중단 아님)")
    # B-1 종료 요약: 차단/쿨다운 발생 → 간격 되돌림 권고
    _check("[순위요약]" in joined and "쿨다운 1회" in joined and "차단감지 1회" in joined, "요약에 쿨다운·차단 누적 집계")
    _check("RANK_NAV_DELAY 를 45~75" in joined, "차단/쿨다운 발생 시 간격 되돌림 권고 출력")


def pin_rank_halt():
    print("[핀 L] 쿨다운 최대 초과 = IP 회복 불가 → 당일 중단(halt), 남은 키워드 공란")
    _SPEC.clear(); _COUNT.clear()
    config.RANK_SEMI_AUTOSUBMIT = True
    config.RANK_SEMI_AUTO_MAX_MISS = 1
    config.RANK_SEMI_COOLDOWN_SEC = 0
    config.RANK_SEMI_COOLDOWN_MAX = 1      # 쿨다운 1회 후에도 차단이면 중단
    d = Path(tempfile.mkdtemp()); path = d / "m.xlsx"
    wb = _rank_wb(path)
    logs: list[str] = []
    _install_rank_fakes([(None, True), (None, True)])   # 연속 차단
    P._track_ranks_semi(wb, path, logs.append, lambda: False)
    joined = "\n".join(logs)
    dt = wb.latest_date("비즈R")
    _check("IP 회복 불가" in joined, "쿨다운 초과 → 당일 중단(IP 회복 불가) 로그")
    _check(not wb.is_rank_filled("비즈R", "상품R", "kw1", dt), "kw1 공란")
    _check(not wb.is_rank_filled("비즈R", "상품R", "kw2", dt), "kw2 공란(중단으로 미측정)")


def pin_rank_skip_optionless():
    print("[핀 M] 키워드 없는 2차 옵션 블록은 순위 대상 아님(건너뜀·크래시 없음)")
    _SPEC.clear(); _COUNT.clear()
    config.RANK_SEMI_AUTOSUBMIT = True
    config.RANK_SEMI_AUTO_MAX_MISS = 3
    config.RANK_SEMI_COOLDOWN_MAX = 4
    d = Path(tempfile.mkdtemp()); path = d / "m.xlsx"
    wb = _rank_wb(path, second_optionless=True)
    pg = object()
    _install_rank_fakes([(pg, False), (pg, False)])
    P._track_ranks_semi(wb, path, lambda m: None, lambda: False)
    dt = wb.latest_date("비즈R")
    _check(wb.is_rank_filled("비즈R", "상품R", "kw1", dt), "대표 블록 순위 기록됨")
    _check(not wb.has_keyword_section("비즈R", "상품R (그레이)"), "2차 블록=키워드 구역 없음(건너뜀)")


def _rank_master(d: Path):
    """track_ranks_stage(out_dir) 가 로드하도록 마스터에 저장한 워크북(계정1·상품1·키워드2·vid·최신일자)."""
    path = P._master_path(d)
    _rank_wb(path)   # 같은 픽스처를 마스터 경로에 저장
    return path


def pin_rank_auto_success():
    print("[핀 O] 자동 순위(track_ranks_stage semi=False) — _measure 측정→기록")
    _SPEC.clear(); _COUNT.clear()
    d = Path(tempfile.mkdtemp())
    _rank_master(d)
    P.WingBrowser = _FakeWing
    P.warmup = lambda browser: None
    P._best = lambda v: v
    P._measure = lambda browser, todo, matcher, log, matched_out=None: {kw: 3 for kw in todo}
    P.track_ranks_stage(out_dir=str(d), semi=False, on_log=lambda m: None)
    from coupang_analytics.workbook import OutputWorkbook
    wb = OutputWorkbook.load(P._master_path(d))
    dt = wb.latest_date("비즈R")
    _check(wb.is_rank_filled("비즈R", "상품R", "kw1", dt), "kw1 자동 순위 기록")
    _check(wb.is_rank_filled("비즈R", "상품R", "kw2", dt), "kw2 자동 순위 기록")


def pin_rank_auto_halt():
    print("[핀 O2] 자동 순위 차단(RankHalt) — 부분결과만 기록·나머지 공란·중단")
    _SPEC.clear(); _COUNT.clear()
    d = Path(tempfile.mkdtemp())
    _rank_master(d)
    P.WingBrowser = _FakeWing
    P.warmup = lambda browser: None
    P._best = lambda v: v

    def fake_measure(browser, todo, matcher, log, matched_out=None):
        raise P.RankHalt(partial={todo[0]: 7})   # 첫 키워드만 측정하고 차단 감지

    P._measure = fake_measure
    P.track_ranks_stage(out_dir=str(d), semi=False, on_log=lambda m: None)
    from coupang_analytics.workbook import OutputWorkbook
    wb = OutputWorkbook.load(P._master_path(d))
    dt = wb.latest_date("비즈R")
    _check(wb.is_rank_filled("비즈R", "상품R", "kw1", dt), "차단 전 부분결과(kw1) 기록")
    _check(not wb.is_rank_filled("비즈R", "상품R", "kw2", dt), "차단 후 kw2 공란(다음에 이어서)")


def pin_rank_skip_suspended():
    print("[핀 P2] 판매중지 상품은 순위 검색 제외(rank_suppressed)")
    _SPEC.clear(); _COUNT.clear()
    config.RANK_SEMI_AUTOSUBMIT = True
    config.RANK_SEMI_AUTO_MAX_MISS = 3
    config.RANK_SEMI_COOLDOWN_MAX = 4
    d = Path(tempfile.mkdtemp()); path = d / "m.xlsx"
    wb = _rank_wb(path)                                  # 상품R · kw1/kw2 · vid vidR
    wb.apply_sale_status("비즈R", {"vidR": True})        # True → 판매중지
    wb.save(path)
    _check(wb.rank_suppressed("비즈R", "상품R"), "판매중지 → rank_suppressed True")
    pg = object()
    _install_rank_fakes([(pg, False), (pg, False)])
    P._track_ranks_semi(wb, path, lambda m: None, lambda: False)
    dt = wb.latest_date("비즈R")
    _check(not wb.is_rank_filled("비즈R", "상품R", "kw1", dt), "판매중지 상품 kw1 순위 미기록(건너뜀)")
    _check(not wb.is_rank_filled("비즈R", "상품R", "kw2", dt), "판매중지 상품 kw2 순위 미기록(건너뜀)")


def pin_rank_manual_mode():
    print("[핀 N] 반자동(비자동제출) — 사람이 Enter, 감지된 페이지만 기록·미감지는 공란(중단 없음)")
    _SPEC.clear(); _COUNT.clear()
    config.RANK_SEMI_AUTOSUBMIT = False
    config.RANK_SEMI_AUTO_MAX_MISS = 3
    config.RANK_SEMI_COOLDOWN_MAX = 4
    d = Path(tempfile.mkdtemp()); path = d / "m.xlsx"
    wb = _rank_wb(path)
    pg = object()
    _install_rank_fakes([(pg, False)])   # 자동제출 경로 아님 → _wait_user_search 로 감지
    detected = {"i": 0, "seq": [pg, None]}   # kw1 감지, kw2 미감지(사람이 검색 안 함)

    def fake_user_search(browser, kw, log, should_stop):
        i = detected["i"]; detected["i"] += 1
        return detected["seq"][min(i, len(detected["seq"]) - 1)]

    P._wait_user_search = fake_user_search
    logs: list[str] = []
    P._track_ranks_semi(wb, path, logs.append, lambda: False)
    joined = "\n".join(logs)
    dt = wb.latest_date("비즈R")
    _check(wb.is_rank_filled("비즈R", "상품R", "kw1", dt), "kw1 감지 → 순위 기록")
    _check(not wb.is_rank_filled("비즈R", "상품R", "kw2", dt), "kw2 미감지 → 공란(다음에 이어서)")
    _check("미감지/시간초과" in joined and "IP 회복 불가" not in joined,
           "반자동은 미감지 공란(서킷브레이커·중단 없음)")


def main() -> int:
    config.SESSION_STATE_DB = os.path.join(tempfile.gettempdir(), "pin_session_state.db")
    config.LOGIN_PACE_MIN_SEC = 0
    config.LOGIN_PACE_MAX_SEC = 0
    config.RANK_NAV_DELAY_MIN_SEC = 0
    config.RANK_NAV_DELAY_MAX_SEC = 0
    # 경계 교체(브라우저) — collector/rank 는 각 시나리오에서 개별 설치
    P.WingBrowser = _FakeWing
    _orig_random = P.random   # 순위 핀에서 pause=0 으로 바꾸므로 종료 시 원복
    saved = {k: getattr(config, k, None) for k in (
        "RANK_SEMI_AUTOSUBMIT", "RANK_SEMI_AUTO_MAX_MISS", "RANK_SEMI_COOLDOWN_SEC",
        "RANK_SEMI_COOLDOWN_MAX")}
    print("=" * 60)
    print("  핀 테스트 — _login_and_discover / _track_ranks_semi (실제 코드)")
    print("=" * 60)
    try:
        pin_session_reuse()
        pin_need_login()
        pin_login_blocked()
        pin_credential_error()
        pin_otp_skip()
        pin_semi_retry_recover()
        pin_discover_empty_uses_vendor()
        pin_discover_failed_then_ok()
        pin_vendor_fallback_to_discover()
        pin_rank_success()
        pin_rank_not_found()
        pin_rank_block_then_recover()
        pin_rank_halt()
        pin_rank_skip_optionless()
        pin_rank_manual_mode()
        pin_rank_auto_success()
        pin_rank_auto_halt()
        pin_rank_skip_suspended()
    finally:
        for k, v in saved.items():   # 순위 config 원복(다른 검증 오염 방지 — 별 프로세스지만 방어적)
            setattr(config, k, v)
        P.random = _orig_random
    print("=" * 60)
    print("  [완료] 핀 테스트 모두 통과")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
