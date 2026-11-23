"""윙 화면 보기 + 화면 응답 기록 틀(T-122 · D-340 · D-296) 오프라인 검증 — 가짜 화면(로그인·쿠팡 호출 없음).

기대값 출처 = 소유자 선택 D-340(11-18) "조회 버튼 허용 (추천)" 적용 문구 · D-296 ①(화면 응답 기록 · 페이지 안 직접 호출 금지) ·
T-122 지시(실제 화면 응답 칸이 없는 것은 구조까지 + '라이브 첫 시험 필요') · 근거표 `T122_자료16종_화면근거_1118.md`(주소·버튼 글자):
① 조회 전용 버튼만 누름 · 동의·신청·저장·보고서 만들기 등 금지 · 애매하면 누르지 않음 ② 페이지 안 스크립트 0 ③ 칸 기록 없는 응답 =
칸 이름·형만(값·개인정보 저장 안 함) ④ 화면·응답 기록 없는 출처 = NeedLive(지어내지 않음) ⑤ 등록표에 'S7 라이브 필요'로 올라감.

    python tools/verify_settlement_screen_view_offline.py
"""
from __future__ import annotations

import gzip
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics import settlement_screen_view as SV  # noqa: E402
from coupang_analytics import settlement_sources as SRC  # noqa: E402


def ok(msg: str) -> None:
    print(f"  OK {msg}")


class Resp:
    def __init__(self, url, body, status=200):
        self.url, self.status, self._b = url, status, body

    def json(self):
        if isinstance(self._b, str):
            raise ValueError("not json")
        return self._b


class Btn:
    def __init__(self, page, name):
        self.page, self.name = page, name

    def count(self):
        return self.page.buttons.get(self.name, 0)

    def click(self):
        if any(d.open for d in self.page.dialogs):
            raise Blocked(f"'{self.name}' — 팝업이 화면을 덮어 눌리지 않음")
        self.page.clicked.append(self.name)
        self.page.buttons.update(self.page.reveal.get(self.name, {}))
        for r in self.page.on_click.get(self.name, ()):
            self.page.fire(r)


class Blocked(Exception):
    """팝업이 덮은 화면의 버튼을 누름(실제 Playwright = 클릭 시간 초과)."""


class Dialog:
    """화면을 덮는 팝업 — text = 팝업 안 글자 전부(버튼 글자 포함) · buttons = 팝업 안 버튼 · closes = 닫기 누르면 닫힘."""

    def __init__(self, text, buttons, closes=True):
        self.text, self.buttons, self.closes, self.open = text, dict(buttons), closes, True


class DialogLoc:
    def __init__(self, page, pred=lambda d: True):
        self.page, self.pred = page, pred

    def _hits(self):
        return [d for d in self.page.dialogs if d.open and self.pred(d)]

    def filter(self, has_text):
        return DialogLoc(self.page, lambda d, p=self.pred: p(d) and has_text in d.text)

    def count(self):
        return len(self._hits())

    def get_by_role(self, role, name, exact):
        assert role == "button" and exact is True
        return DialogBtn(self, name)


class DialogBtn:
    def __init__(self, loc, name):
        self.loc, self.name = loc, name

    def count(self):
        return sum(d.buttons.get(self.name, 0) for d in self.loc._hits())

    def click(self):
        self.loc.page.clicked.append(f"팝업:{self.name}")
        for d in self.loc._hits():
            d.open = not d.closes


class TextLoc:
    def __init__(self, page, text):
        self.page, self.text = page, text

    def count(self):
        return sum(1 for d in self.page.dialogs if d.open and self.text in d.text)


class FakePage:
    """화면 열기·버튼 누르기 때 응답을 '스스로' 받는 가짜(Playwright 쪽 이름만 같음) · dialogs = 화면을 덮는 팝업 ·
    reveal = 버튼을 누르면 새로 보이는 버튼(예: '검색 열기' → '검색')."""

    def __init__(self, buttons=None, on_goto=(), on_click=None, dialogs=(), reveal=None):
        self.buttons, self.on_goto, self.on_click = buttons or {}, list(on_goto), on_click or {}
        self.dialogs, self.reveal = list(dialogs), reveal or {}
        self.listeners: list = []
        self.visited: list = []
        self.clicked: list = []

    def on(self, evt, fn):
        assert evt == "response"
        self.listeners.append(fn)

    def remove_listener(self, evt, fn):
        self.listeners.remove(fn)

    def fire(self, r):
        for fn in list(self.listeners):
            fn(r)

    def goto(self, url):
        self.visited.append(url)
        for r in self.on_goto:
            self.fire(r)

    def wait_for_timeout(self, ms):
        pass

    def get_by_role(self, role, name=None, exact=None):
        if role == "dialog":
            return DialogLoc(self)
        assert role == "button" and exact is True
        return Btn(self, name)

    def get_by_text(self, text):
        return TextLoc(self, text)

    def evaluate(self, *a, **k):
        raise AssertionError("페이지 안 스크립트 금지(D-296)")

    def request(self, *a, **k):
        raise AssertionError("API 직접 호출 금지(D-340)")


def v1_buttons():
    print("[V1] 조회 전용 버튼만 — 금지 낱말·목록 밖(애매) = 누르지 않음")
    for t in ("검색", "조회", "구독 관리", "구독 내역 보기", "검색 열기"):
        SV.check_button(t)
    for t in ("보고서 만들기", "구독 해지하기", "다시 구독하기", "카테고리 변경", "반출 신청", "동의", "저장", "이용권 관리", "지금 가입",
              "확인", "엑셀 다운로드", "상세"):
        try:
            SV.check_button(t)
            raise AssertionError(f"'{t}' 가 눌릴 수 있음")
        except SV.NotViewOnly:
            pass
    ok("조회 5종만 허용(검색 열기 = nicoable 11-23) · 보고서 만들기·해지·변경·신청·동의·저장·가입·확인·다운로드·목록 밖('이용권 관리'·'상세') = 거부")


def v2_return_channel():
    print("[V2] 반품 접수채널(②7) — 화면 열기 → '검색' → 화면이 받은 search 응답 = 칸 이름·형만(구매자 값 없음) · 쿼리 안 남김")
    body = {"data": {"content": [{"receiptChannel": "SELLER", "customerName": "홍길동", "orderId": 1}], "total": 1}}
    page = FakePage(buttons={"검색 열기": 1, "검색": 1},
                    on_goto=[Resp("https://wing.coupang.com/tenants/sfl-portal/return-delivery/dashboard", {})],
                    on_click={"검색": [Resp("https://wing.coupang.com/tenants/sfl-portal/return-delivery/search?from=1", body),
                                      Resp("https://wing.coupang.com/tenants/other/x", {"a": 1})]})
    rec = SV.capture(page, SV.SPECS["SV-RETURN-CHANNEL"])
    assert page.visited == ["https://wing.coupang.com/tenants/sfl-portal/return-delivery/list"] and page.clicked == ["검색 열기", "검색"]
    assert [e["주소"] for e in rec["응답"]] == ["/tenants/sfl-portal/return-delivery/search"], rec
    e = rec["응답"][0]
    assert "data.content[].receiptChannel:str" in e["칸"] and "data.content[].customerName:str" in e["칸"], e
    assert "홍길동" not in json.dumps(rec, ensure_ascii=False) and "값" not in e, "값(개인정보) 저장 안 함"
    assert not page.listeners, "기록 끝나면 듣기 해제"
    with tempfile.TemporaryDirectory() as td:
        p = SV.save(Path(td), "SV-RETURN-CHANNEL", "acc1", rec)
        assert p.parent == Path(td) / "자료출처" / SV.DIRNAME / "SV-RETURN-CHANNEL" / "acc1", p
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            assert json.load(fh)["응답"][0]["칸"] == e["칸"]
    ok("주소 이동 1 · 검색 열기 1 · 검색 1 · search 응답만 · 칸 목록(접수채널·구매자명 칸 이름) · 값·쿼리 없음 · 날짜별 파일")


def v3_bi_two_buttons_and_keep():
    print("[V3] BI 구독(②17) — 조회 버튼 2개 차례로 · 저장칸 정하면 그 칸 값만 · JSON 아닌 응답 = 형만")
    sub = {"plan": "BASIC", "paidStartDate": "2026-03-01", "card": "1234"}
    page = FakePage(buttons={"구독 관리": 1, "구독 내역 보기": 1},
                    on_click={"구독 관리": [Resp("https://wing.coupang.com/tenants/rfm-ss/api/subscription/current", sub)],
                              "구독 내역 보기": [Resp("https://wing.coupang.com/tenants/rfm-ss/api/subscription/v2/history", "<html>")]})
    spec = dict(SV.SPECS["SV-BI-SUB"], 저장칸=("plan", "paidStartDate"))
    rec = SV.capture(page, spec)
    assert page.clicked == ["구독 관리", "구독 내역 보기"], page.clicked
    assert rec["응답"][0]["값"] == {"plan": "BASIC", "paidStartDate": "2026-03-01"} and rec["응답"][1]["JSON 아님"] == "ValueError", rec
    assert "1234" not in json.dumps(rec)
    ok("버튼 순서대로 · 저장칸 값만(그 밖 칸 값 없음) · HTML 응답 = JSON 아님 표시")


def v4_need_live():
    print("[V4] 기록 없는 출처 = NeedLive(화면 안 열고 사유) · 버튼이 1개가 아님 = 누르지 않음 · 응답 0 = NeedLive")
    for sid in ("SV-RETURN-BOX", "SV-SALES-F", "SV-REVIEW-DETAIL", "SV-AD-UNPAID", "SV-EXCHANGE"):
        page = FakePage()
        try:
            SV.capture(page, SV.SPECS[sid])
            raise AssertionError(sid)
        except SV.NeedLive as exc:
            assert page.visited == [] and str(exc), sid
    page = FakePage(buttons={"검색 열기": 2})
    try:
        SV.capture(page, SV.SPECS["SV-RETURN-CHANNEL"])
        raise AssertionError("버튼 2개인데 누름")
    except SV.NeedLive:
        assert page.clicked == [] and not page.listeners
    try:
        SV.capture(FakePage(), SV.SPECS["SV-RG-HOME"])
        raise AssertionError("응답 0 이 조용히 지나감")
    except SV.NeedLive:
        pass
    bad = dict(SV.SPECS["SV-RETURN-CHANNEL"], 버튼=("보고서 만들기",))
    page = FakePage(buttons={"보고서 만들기": 1})
    try:
        SV.capture(page, bad)
        raise AssertionError("금지 버튼")
    except SV.NotViewOnly:
        assert page.visited == [] and page.clicked == [], "금지 버튼이 있으면 화면도 안 엶"
    ok("기록 없는 5종 = 화면 안 엶 · 버튼 2개 = 안 누름 · 응답 0 = NeedLive · 금지 버튼 = 화면도 안 엶")


def v5_registry():
    print("[V5] 등록표 — 화면 출처 9종이 SOURCES 에 'S7 라이브 필요'(구현 단계 아님) · ②번 그대로")
    sv = {sid: s for sid, s in SRC.SOURCES.items() if sid.startswith("SV-")}
    assert set(sv) == set(SV.SPECS), sorted(set(sv) ^ set(SV.SPECS))
    assert all(s["단계"] == "S7 라이브 필요" and not SRC.implemented(s["단계"]) for s in sv.values()), sv
    assert sorted(s["②"] for s in SV.SPECS.values()) == [5, 6, 7, 12, 13, 15, 16, 17, 18]
    ok("SV 9종 = S7 라이브 필요 · ②번 5·6·7·12·13·15·16·17·18")


def v6_cli():
    print("[V6] 첫 시험 명령 `view --source` — 저장·처리기록 · 기록 없는 출처 = 확인 필요 줄(화면 안 엶) · 모르는 출처 = 실패 줄")
    sys.path.insert(0, str(ROOT / "tools"))
    from types import SimpleNamespace
    import settlement_download as TD
    recs: list = []
    log = SimpleNamespace(record=lambda *a, **k: recs.append(a), saved=lambda *a, **k: recs.append(("saved",) + a))
    page = FakePage(on_goto=[Resp("https://wing.coupang.com/tenants/rfm/v2/home/banner", {"endDate": "2026-12-01"})])
    acct = SimpleNamespace(account_id="acc1")
    saved = (TD.BASE, TD.LOG, TD.name_of)
    with tempfile.TemporaryDirectory() as td:
        try:
            TD.BASE, TD.LOG, TD.name_of = Path(td), log, (lambda a: "A")
            for src in ("SV-RG-HOME", "SV-SALES-F", "없는출처"):
                TD.cmd_view(acct, SimpleNamespace(page=page), SimpleNamespace(source=src), [])
        finally:
            TD.BASE, TD.LOG, TD.name_of = saved
        assert list((Path(td) / "자료출처" / SV.DIRNAME / "SV-RG-HOME" / "acc1").glob("*.json.gz")), "저장"
    kinds = [(r[2], r[3].split(" ")[0]) for r in recs if r[0] != "saved"]
    assert kinds == [(TD.RL.OK, "SV-RG-HOME"), (TD.RL.WAIT, "SV-SALES-F"), (TD.RL.FAIL, "모르는")], kinds
    assert len(page.visited) == 1, "기록 없는 출처는 화면을 안 엶"
    ok("SV-RG-HOME 칸 목록 저장 · SV-SALES-F = 확인 필요(화면 안 엶) · 모르는 출처 = 실패 줄")


# ── nicoable 실측(2026-11-23 · output/_분석_261123_윙화면_nicoable/nicoable_화면4종.md) — 기대값 = 그 문서 줄(코드에서 뽑지 않음) ──
NICO_NOTICE = ("베타 버전 출시 무료로 구매 고객 통계를 이용할 수 있어요! 이용 기간 11월 16일~11월 30일 12월 1일부터 신규 요금제 "
               "'프로' 이상 필요 다시 보지 않기 확인")                # 문서 43줄 공지 팝업 글자(버튼 = '다시 보지 않기' 체크박스 · '확인')
W = "https://wing.coupang.com"


def _bi_page(dialogs):
    """문서 74~77줄: 처음 열 때 = 화면 문서(HTML)·vendor-summary · '구독 관리' = 카테고리 2개 · '구독 내역 보기' = 구독 내역."""
    return FakePage(buttons={"구독 관리": 1, "구독 내역 보기": 1}, dialogs=dialogs,
                    on_goto=[Resp(f"{W}/tenants/business-insight/sales-analysis?start_date=2026-11-17", "<html>"),
                             Resp(f"{W}/tenants/rfm-ss/api/business-insight/vendor-summary", {"a": 1})],
                    on_click={"구독 관리": [Resp(f"{W}/tenants/rfm-ss/api/category-insight/vendor/categories", []),
                                         Resp(f"{W}/tenants/rfm-ss/api/info/categories", [])],
                              "구독 내역 보기": [Resp(f"{W}/tenants/rfm-ss/api/subscription/v2/subscription-change-history",
                                                 {"content": [{"type": "해지 예약", "plan": "스탠다드"}]})]})


def v7_bi_fragment_nicoable():
    print("[V7] BI 구독(②17) 응답 조각 = nicoable 실측 — 구독 내역 = /tenants/rfm-ss/api/subscription/… · 화면 문서(HTML) 안 잡음")
    frags = SV.SPECS["SV-BI-SUB"]["응답"]
    hist = "/tenants/rfm-ss/api/subscription/v2/subscription-change-history"   # 문서 74줄 '(확실 · 누를 때마다 부름)'
    assert any(f in hist for f in frags), f"구독 내역 응답을 못 잡음 — 지금 조각 {frags}"
    assert not any(f in "/tenants/business-insight/sales-analysis" for f in frags), f"화면 문서(HTML)를 잡음 — {frags}"
    page = _bi_page([Dialog(NICO_NOTICE, {"확인": 1})])
    rec = SV.capture(page, SV.SPECS["SV-BI-SUB"])
    assert [e["주소"] for e in rec["응답"]] == [hist], rec
    assert "content[].type:str" in rec["응답"][0]["칸"] and "값" not in rec["응답"][0], rec
    ok("구독 내역 응답 1개만(카테고리·vendor-summary·HTML 안 잡음) · 칸 이름만")


def v8_bi_notice_popup():
    print("[V8] BI 공지 팝업 — 표지 글자가 다 든 팝업 안 '확인' 1개만 닫기로 누름 · 금지 낱말 '확인'은 그대로(일반 버튼 = 거부)")
    assert "확인" in SV.FORBIDDEN, "금지 낱말 약화 금지"
    try:
        SV.check_button("확인")
        raise AssertionError("일반 버튼 '확인' 이 눌릴 수 있음")
    except SV.NotViewOnly:
        pass
    page = _bi_page([Dialog(NICO_NOTICE, {"확인": 1})])
    rec = SV.capture(page, SV.SPECS["SV-BI-SUB"])
    assert page.clicked == ["팝업:확인", "구독 관리", "구독 내역 보기"], page.clicked      # 문서 5줄 '다시 보지 않기' 안 누름
    assert rec["팝업"] == "닫음", rec
    page = _bi_page([])                                                                    # 팝업이 안 뜬 날 = 그대로 진행
    assert SV.capture(page, SV.SPECS["SV-BI-SUB"])["팝업"] == "없음" and page.clicked == ["구독 관리", "구독 내역 보기"]
    # 표지가 없는 다른 팝업(예: 해지 확인 창)의 '확인' = 누르지 않음 → 그 팝업이 화면을 덮으면 진행 못 함(조용히 넘어가지 않음)
    page = _bi_page([Dialog("구독을 해지하시겠습니까? 취소 확인", {"확인": 1, "취소": 1})])
    try:
        SV.capture(page, SV.SPECS["SV-BI-SUB"])
        raise AssertionError("표지 없는 팝업이 덮었는데 지나감")
    except Blocked:
        assert "팝업:확인" not in page.clicked, page.clicked
    # 표지는 다 있는데 금지 낱말이 섞인 팝업 = 누르지 않음(NotViewOnly)
    page = _bi_page([Dialog(NICO_NOTICE + " 약관에 동의", {"확인": 1})])
    try:
        SV.capture(page, SV.SPECS["SV-BI-SUB"])
        raise AssertionError("금지 낱말 든 팝업의 '확인' 을 누름")
    except SV.NotViewOnly:
        assert page.clicked == [], page.clicked
    # 표지 글자는 보이는데 팝업 구조가 아님 · '확인' 2개 · 눌러도 안 닫힘 = NeedLive(확인 필요)
    for dlg in ([Dialog(NICO_NOTICE, {"확인": 1}), Dialog(NICO_NOTICE, {"확인": 1})],
                [Dialog(NICO_NOTICE, {"확인": 2})], [Dialog(NICO_NOTICE, {"확인": 1}, closes=False)]):
        page = _bi_page(dlg)
        try:
            SV.capture(page, SV.SPECS["SV-BI-SUB"])
            raise AssertionError(dlg)
        except SV.NeedLive:
            assert "구독 관리" not in page.clicked and not page.listeners, page.clicked
    # 출처 정의 자체가 위험하면 화면도 안 엶(닫기 글자 = 허용 목록 밖 · 표지에 금지 낱말 · 표지 없음)
    for pop in ({"표지": ("베타 버전 출시",), "닫기": "동의"}, {"표지": ("신청 안내",), "닫기": "확인"}, {"표지": (), "닫기": "확인"}):
        page = _bi_page([Dialog(NICO_NOTICE, {"확인": 1})])
        try:
            SV.capture(page, dict(SV.SPECS["SV-BI-SUB"], 팝업=pop))
            raise AssertionError(pop)
        except SV.NotViewOnly:
            assert page.visited == [] and page.clicked == [], pop
    ok("공지 팝업 '확인'만 닫음('다시 보지 않기' 안 누름) · 일반 '확인' 거부 그대로 · 다른 팝업·금지 낱말 팝업 안 누름 · 애매 = NeedLive")


def v9_return_open_search():
    print("[V9] 반품(②7) — 검색 조건 접힘 → '검색 열기' → '검색' 차례(문서 83·84줄) · 접힌 채 '검색' 0개")
    SV.check_button("검색 열기")
    body = {"data": {"content": [{"receiptChannel": "SELLER"}]}}
    page = FakePage(buttons={"검색 열기": 1}, reveal={"검색 열기": {"검색": 1}},
                    on_goto=[Resp(f"{W}/tenants/sfl-portal/return-delivery/dashboard?to=2026-11-23", {})],
                    on_click={"검색": [Resp(f"{W}/tenants/sfl-portal/return-delivery/search", body)]})
    rec = SV.capture(page, SV.SPECS["SV-RETURN-CHANNEL"])
    assert page.clicked == ["검색 열기", "검색"], page.clicked
    assert [e["주소"] for e in rec["응답"]] == ["/tenants/sfl-portal/return-delivery/search"], rec
    ok("'검색 열기' → '검색' · search 응답만")


def main() -> int:
    v1_buttons()
    v2_return_channel()
    v3_bi_two_buttons_and_keep()
    v4_need_live()
    v5_registry()
    v6_cli()
    v7_bi_fragment_nicoable()
    v8_bi_notice_popup()
    v9_return_open_search()
    print("윙 화면 보기·응답 기록 틀 — 전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
