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
        self.page.clicked.append(self.name)
        for r in self.page.on_click.get(self.name, ()):
            self.page.fire(r)


class FakePage:
    """화면 열기·버튼 누르기 때 응답을 '스스로' 받는 가짜(Playwright 쪽 이름만 같음)."""

    def __init__(self, buttons=None, on_goto=(), on_click=None):
        self.buttons, self.on_goto, self.on_click = buttons or {}, list(on_goto), on_click or {}
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

    def get_by_role(self, role, name, exact):
        assert role == "button" and exact is True
        return Btn(self, name)

    def evaluate(self, *a, **k):
        raise AssertionError("페이지 안 스크립트 금지(D-296)")

    def request(self, *a, **k):
        raise AssertionError("API 직접 호출 금지(D-340)")


def v1_buttons():
    print("[V1] 조회 전용 버튼만 — 금지 낱말·목록 밖(애매) = 누르지 않음")
    for t in ("검색", "조회", "구독 관리", "구독 내역 보기"):
        SV.check_button(t)
    for t in ("보고서 만들기", "구독 해지하기", "다시 구독하기", "카테고리 변경", "반출 신청", "동의", "저장", "이용권 관리", "지금 가입",
              "확인", "엑셀 다운로드", "상세"):
        try:
            SV.check_button(t)
            raise AssertionError(f"'{t}' 가 눌릴 수 있음")
        except SV.NotViewOnly:
            pass
    ok("조회 4종만 허용 · 보고서 만들기·해지·변경·신청·동의·저장·가입·확인·다운로드·목록 밖('이용권 관리'·'상세') = 거부")


def v2_return_channel():
    print("[V2] 반품 접수채널(②7) — 화면 열기 → '검색' → 화면이 받은 search 응답 = 칸 이름·형만(구매자 값 없음) · 쿼리 안 남김")
    body = {"data": {"content": [{"receiptChannel": "SELLER", "customerName": "홍길동", "orderId": 1}], "total": 1}}
    page = FakePage(buttons={"검색": 1}, on_goto=[Resp("https://wing.coupang.com/tenants/sfl-portal/return-delivery/dashboard", {})],
                    on_click={"검색": [Resp("https://wing.coupang.com/tenants/sfl-portal/return-delivery/search?from=1", body),
                                      Resp("https://wing.coupang.com/tenants/other/x", {"a": 1})]})
    rec = SV.capture(page, SV.SPECS["SV-RETURN-CHANNEL"])
    assert page.visited == ["https://wing.coupang.com/tenants/sfl-portal/return-delivery/list"] and page.clicked == ["검색"]
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
    ok("주소 이동 1 · 검색 1 · search 응답만 · 칸 목록(접수채널·구매자명 칸 이름) · 값·쿼리 없음 · 날짜별 파일")


def v3_bi_two_buttons_and_keep():
    print("[V3] BI 구독(②17) — 조회 버튼 2개 차례로 · 저장칸 정하면 그 칸 값만 · JSON 아닌 응답 = 형만")
    sub = {"plan": "BASIC", "paidStartDate": "2026-03-01", "card": "1234"}
    page = FakePage(buttons={"구독 관리": 1, "구독 내역 보기": 1},
                    on_click={"구독 관리": [Resp("https://wing.coupang.com/tenants/business-insight/api/subscription", sub)],
                              "구독 내역 보기": [Resp("https://wing.coupang.com/tenants/business-insight/history", "<html>")]})
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
    page = FakePage(buttons={"검색": 2})
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


def main() -> int:
    v1_buttons()
    v2_return_channel()
    v3_bi_two_buttons_and_keep()
    v4_need_live()
    v5_registry()
    v6_cli()
    print("윙 화면 보기·응답 기록 틀 — 전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
