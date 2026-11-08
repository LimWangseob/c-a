"""윙 할인쿠폰 목록 수집·재고현황 날짜별 보관 오프라인 검증 — 로그인·쿠팡 호출 없음(가짜 page·결정적).

기대값 출처 = 소유자 승인 사양(2026-11-06): 목록 page 0부터·응답 content·items 전체 페이지·원본 칸 보존·사용 금액 0 포함·
기간 인자 기본 빈 값·계정별 날짜별 누적·덮어쓰기 없음·조회 사이 간격·실패는 로그 후 ① 계속.

    python tools/verify_coupon_snapshot_offline.py
"""
from __future__ import annotations

import gzip
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics import collector as C  # noqa: E402
from coupang_analytics import config  # noqa: E402
from coupang_analytics import daily_snapshot as DS  # noqa: E402
from coupang_analytics import pipeline_sales as PS  # noqa: E402
from coupang_analytics import wing_coupons as WC  # noqa: E402
from coupang_analytics.input_list import Account  # noqa: E402

LIST_HEAD = ("https://wing.coupang.com/tenants/seller-promotion-platform/v2/seller-funding-coupon/coupons/list"
             "?id=&couponType=&status=&name=&requestStartAt=&requestEndAt=&badDiscount=&beforeCouponStart=&page=")
LIST_TAIL = "&contractId=-1"
ITEMS_HEAD = "https://wing.coupang.com/tenants/seller-promotion-platform/v2/seller-funding-coupon/coupons/"


def ok(msg):
    print(f"  ✔ {msg}")


def _coupon(cid, usage=0):
    return {"couponId": cid, "usageAmount": usage, "type": "RATE", "name": f"쿠폰{cid}", "status": "ACTIVE",
            "startAt": "2026-09-01T00:00:00", "endAt": "2026-09-30T23:59:00", "publishDate": "2026-08-31",
            "couponType": "INSTANCE", "appliedOptionCnt": 2, "vendorId": "A00", "wowExclusive": False,
            "policyDtos": [{"type": "x", "title": "t", "discount": 12200, "minPrice": 0, "maxDiscountPrice": 0,
                            "maxPerDaily": 9, "discountType": "PRICE"}],
            "미지의칸": {"수량별": True}}


def _item(vid):
    return {"vendorItemId": vid, "productId": 7, "vendorInventoryId": 8, "vendorInventoryName": "상품",
            "vendorItemName": "옵션", "salePrice": 39000, "clearingPrice": 26800, "미지의칸": 1}


def _page_of(rows, n, size, *, envelope=True):
    body = {"content": rows[n * size:(n + 1) * size]}
    if envelope:
        body.update(totalElements=len(rows), totalPages=(len(rows) + size - 1) // size, number=n)
    return body


class FakePage:
    """주소 → 응답 라우팅. 호출 기록 · fail={주소 조각: (status, body) 또는 Exception}."""

    def __init__(self, coupons, items_by_id, fail=None, size=10, item_size=2, envelope=True):
        self.coupons, self.items, self.fail = coupons, items_by_id, fail or {}
        self.size, self.item_size, self.envelope = size, item_size, envelope
        self.calls: list[str] = []
        self.scripts: set[str] = set()

    def evaluate(self, script, url):
        self.calls.append(url)
        self.scripts.add(script)
        for frag, out in self.fail.items():
            if frag in url:
                if isinstance(out, Exception):
                    raise out
                return {"status": out[0], "body": out[1], "hasToken": True}
        n = int(url.split("page=")[1].split("&")[0])
        if "/list?" in url:
            body = _page_of(self.coupons, n, self.size, envelope=self.envelope)
        else:
            cid = int(url.split("/coupons/")[1].split("/")[0])
            body = _page_of(self.items[cid], n, self.item_size, envelope=self.envelope)
        return {"status": 200, "body": json.dumps(body, ensure_ascii=False), "hasToken": True}


def _sample():
    """23쿠폰(사용 금액 0 포함)·쿠폰 1번만 옵션 5개(items 3페이지)."""
    coupons = [_coupon(100 + i, usage=0 if i % 2 else 1000 * (i + 1)) for i in range(23)]
    items = {c["couponId"]: [_item(c["couponId"] * 10)] for c in coupons}
    items[100] = [_item(9000 + i) for i in range(5)]
    return coupons, items


def _read(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def _freeze(ts: str):
    DS._now = lambda: datetime.fromisoformat(ts)


def _files(root, dirname, acc="acc1"):
    d = Path(root) / dirname / acc
    return sorted(p.name for p in d.iterdir()) if d.is_dir() else []


def _coupon_file(root, name, acc="acc1") -> Path:
    return Path(root) / DS.COUPON_DIRNAME / acc / name


def _refuse_save(*a, **k):
    raise PermissionError("잠김")


def s1_pages():
    print("[S1] 페이지 순회 — 목록 page 0~2·쿠폰별 items 전체·주소 그대로·GET 만·원본 칸 보존·사용 금액 0 포함")
    coupons, items = _sample()
    page = FakePage(coupons, items)
    rec = WC.collect(page)
    assert rec["오류"] == "", rec["오류"]
    assert page.scripts == {C._GET_JSON_JS}, "GET fetch 한 종류만(POST 없음)"
    assert page.calls[:3] == [f"{LIST_HEAD}{n}{LIST_TAIL}" for n in range(3)], page.calls[:3]
    assert f"{ITEMS_HEAD}100/items?page=0&badDiscount=" in page.calls
    assert sum("/100/items" in u for u in page.calls) == 3, "옵션 5개·페이지당 2개 = items 3페이지"
    assert len(page.calls) == 3 + 3 + 22, len(page.calls)
    assert rec["쿠폰수"] == 23 and rec["호출수"] == 28
    got = [r for p in rec["목록"] for r in p["content"]]
    assert got == coupons, "쿠폰 줄이 칸 그대로(미지의칸·policyDtos·사용 금액 0 포함)"
    assert sum(r["usageAmount"] == 0 for r in got) == 11
    assert [r for p in rec["옵션"]["100"] for r in p["content"]] == items[100], "옵션 줄 칸 그대로"
    assert rec["목록"][0]["totalElements"] == 23, "응답의 다른 칸도 남김"
    assert set(rec["옵션"]) == {str(c["couponId"]) for c in coupons}
    ok("0→2 순회·items 3페이지·28회 호출·원본 칸·봉투 칸·0원 쿠폰 전부")


class _StuckPage(FakePage):
    """서버가 page 를 무시해 1페이지를 다시 주는 경우."""

    def evaluate(self, script, url):
        return super().evaluate(script, url.replace("page=1", "page=0"))


def s2_end_detection():
    print("[S2] 끝을 안 알려 주는 응답 = 빈 페이지까지 · 서버가 page 무시 = 같은 줄에서 멈춤 · 건수 모자람 = 실패")
    coupons = [_coupon(100 + i) for i in range(3)]
    items = {c["couponId"]: [_item(1)] for c in coupons}
    page = FakePage(coupons, items, size=2, item_size=2, envelope=False)
    rec = WC.collect(page)
    assert rec["오류"] == "" and rec["쿠폰수"] == 3
    assert sum("/list?" in u for u in page.calls) == 3, "2+1+빈 페이지"
    page = _StuckPage(coupons, items, size=2, envelope=False)
    rec = WC.collect(page)
    assert rec["쿠폰수"] == 2 and sum("/list?" in u for u in page.calls) == 2, "무한 반복 없음"
    page = _StuckPage(coupons, items, size=2)   # totalElements=3 인데 2건만 → 조용히 넘어가지 않음
    rec = WC.collect(page)
    assert "3건 중 2건" in rec["오류"], rec["오류"]
    ok("빈 페이지 끝·page 무시 정지·건수 부족은 오류")


def s3_gap_and_period():
    print("[S3] 조회 사이 간격(첫 조회 전 없음·매 조회 사이) · 기간 인자가 주소로 · 기본은 빈 값")
    coupons, items = _sample()
    rests = []
    rec = WC.collect(FakePage(coupons, items), rest=lambda: rests.append(1))
    assert len(rests) == rec["호출수"] - 1
    page = FakePage(coupons, items)
    WC.collect(page, start="2026-01-01 00:00", end="2026-11-06")
    assert "requestStartAt=2026-01-01%2000%3A00&requestEndAt=2026-11-06&" in page.calls[0], page.calls[0]
    assert all("requestStartAt" not in u for u in page.calls if "/items" in u)
    slept = []
    orig = WC.time.sleep
    WC.time.sleep = slept.append
    try:
        with tempfile.TemporaryDirectory() as tmp:
            _freeze("2026-11-06T09:00:00")
            WC.record_day(FakePage(coupons, items), "acc1", tmp, lambda m: None, gap=PS._PERIOD_GAP_SEC)
    finally:
        WC.time.sleep = orig
    lo, hi = PS._PERIOD_GAP_SEC
    assert len(slept) == 27 and all(lo <= s <= hi for s in slept), "기존 부가 조회와 같은 간격"
    ok("호출-1회 쉼·기존 간격 범위·기간 인코딩")


def s4_save_and_accumulate():
    print("[S4] 저장 형식·계정별·날짜별 누적·앞 파일 불변·같은 날 재실행은 쿠팡 호출 0")
    coupons, items = _sample()
    logs = []
    with tempfile.TemporaryDirectory() as tmp:
        _freeze("2026-11-06T09:00:00")
        WC.record_day(FakePage(coupons, items), "acc1", tmp, logs.append)
        p1 = _coupon_file(tmp, "2026-11-06.json.gz")
        assert p1.exists(), _files(tmp, DS.COUPON_DIRNAME)
        rec = _read(p1)
        assert rec["계정"] == "acc1" and rec["날짜"] == "2026-11-06" and rec["수집"] == "2026-11-06T09:00:00"
        assert rec["오류"] == "" and rec["쿠폰수"] == 23
        assert rec["조회기간"] == {"requestStartAt": "", "requestEndAt": ""}
        assert [r for p in rec["목록"] for r in p["content"]] == coupons, "파일에서 다시 읽어도 칸 그대로"
        assert any("23건" in m for m in logs), logs
        before = p1.read_bytes()

        again = FakePage(coupons, items)
        WC.record_day(again, "acc1", tmp, logs.append)
        assert again.calls == [], "같은 날 완료본 있으면 쿠팡을 다시 부르지 않음"
        assert _files(tmp, DS.COUPON_DIRNAME) == ["2026-11-06.json.gz"] and p1.read_bytes() == before

        _freeze("2026-11-07T09:00:00")
        WC.record_day(FakePage(coupons[:1], items), "acc1", tmp, logs.append)
        WC.record_day(FakePage(coupons[:2], items), "acc2", tmp, logs.append)
        assert _files(tmp, DS.COUPON_DIRNAME) == ["2026-11-06.json.gz", "2026-11-07.json.gz"]
        assert p1.read_bytes() == before, "다음 날 저장이 앞 날 파일을 안 건드림"
        assert _read(_coupon_file(tmp, "2026-11-07.json.gz", "acc2"))["쿠폰수"] == 2, "계정 분리"

        _freeze("2026-11-08T09:00:00")
        WC.record_day(FakePage([], {}), "acc1", tmp, logs.append)
        assert _read(_coupon_file(tmp, "2026-11-08.json.gz"))["쿠폰수"] == 0, "쿠폰 0건인 날도 기록"
        assert not list(Path(tmp).rglob("*.tmp")), "반쯤 쓴 파일 없음"
    ok("gzip JSON·머리 칸·날짜 누적·같은 날 건너뜀·계정 분리·0건 날 기록")


def s5_failures():
    print("[S5] 실패 — raise 없음·로그 남김·받은 만큼 부분본·남은 조회 멈춤·다음 실행이 완료본을 새로 쓰고 부분본 유지")
    coupons, items = _sample()
    with tempfile.TemporaryDirectory() as tmp:
        _freeze("2026-11-06T09:00:00")
        logs = []
        for out, why in (((403, "Access Denied"), "status=403"), ((200, "<html>"), "파싱 실패"),
                         (RuntimeError("Target closed"), "Target closed")):
            page = FakePage(coupons, items, fail={"/list?": out})
            WC.record_day(page, "acc1", tmp, logs.append)
            assert len(page.calls) == 1 and any("⚠" in m and why in m for m in logs), (why, logs)
        assert _files(tmp, DS.COUPON_DIRNAME) == [], "받은 게 없으면 파일 없음"

        logs.clear()
        page = FakePage(coupons, items, fail={"/103/items": (429, "too many")})
        WC.record_day(page, "acc1", tmp, logs.append)
        assert not any("/104/items" in u for u in page.calls), "첫 실패에서 이 계정 조회 멈춤(차단 위험 안 늘림)"
        assert any("⚠" in m and "status=429" in m for m in logs), logs
        assert _files(tmp, DS.COUPON_DIRNAME) == ["2026-11-06_부분.json.gz"]
        part = _coupon_file(tmp, "2026-11-06_부분.json.gz")
        rec, before = _read(part), part.read_bytes()
        assert "status=429" in rec["오류"] and rec["쿠폰수"] == 23 and "102" in rec["옵션"], rec["오류"]
        assert rec["옵션"]["103"] == [], "실패한 쿠폰은 빈 칸(있는 척 안 함)"

        again = FakePage(coupons, items)
        WC.record_day(again, "acc1", tmp, logs.append)
        assert again.calls, "부분본만 있으면 다시 받음"
        assert _files(tmp, DS.COUPON_DIRNAME) == ["2026-11-06.json.gz", "2026-11-06_부분.json.gz"]
        assert part.read_bytes() == before and _read(part.with_name("2026-11-06.json.gz"))["오류"] == ""

        _freeze("2026-11-07T09:00:00")
        WC.record_day(FakePage(coupons[:1], items, fail={"/items": (200, '{"data":{"items":[]}}')}),
                      "acc1", tmp, logs.append)
        rec = _read(_coupon_file(tmp, "2026-11-07_부분.json.gz"))
        assert "content 칸 없음" in rec["오류"] and rec["옵션"]["100"] == [{"data": {"items": []}}], "모양이 달라도 원본 보존"

        orig = DS.save
        DS.save = _refuse_save
        try:
            _freeze("2026-11-08T09:00:00")
            logs.clear()
            WC.record_day(FakePage(coupons[:1], items), "acc1", tmp, logs.append)
        finally:
            DS.save = orig
        assert any("⚠" in m and "저장 실패" in m for m in logs), logs
    ok("비200·JSON 아님·브라우저 오류·중간 실패·모양 다름·저장 실패 모두 비치명+로그")


def _dump_inventory(tmp, bodies) -> list:
    C.reset_raw()
    C._raw_add("vendor_inventory", "{}")
    C._raw_add("sales", "{}")
    for x in bodies:
        C._raw_add("inventory", x)
    logs: list = []
    PS._dump_raw("acc1", logs.append, out_dir=tmp)
    return logs


def s6_inventory():
    print("[S6] 재고현황 원문 — _raw 는 덮어써도 날짜별은 쌓임·원문 그대로·같은 날 재수집은 파일 추가")
    a = json.dumps({"viProperties": [{"vendorItemId": 1, "pricing": {"salesPrice": 100, "allMemberInstantDiscount": 10},
                                      "settlementStatistics": {"fulfillmentFee": 2200}}]}, ensure_ascii=False)
    b = a.replace("100", "200")
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / DS.INVENTORY_DIRNAME / "acc1"
        _freeze("2026-11-06T09:00:00")
        _dump_inventory(tmp, [a, a])
        first = (d / "2026-11-06.json.gz").read_bytes()
        rec = _read(d / "2026-11-06.json.gz")
        assert rec["응답"] == [a, a] and rec["계정"] == "acc1" and rec["날짜"] == "2026-11-06", "페이지별 원문 그대로"

        _freeze("2026-11-07T09:00:00")
        logs = _dump_inventory(tmp, [b])
        assert _files(tmp, DS.INVENTORY_DIRNAME) == ["2026-11-06.json.gz", "2026-11-07.json.gz"]
        assert (d / "2026-11-06.json.gz").read_bytes() == first, "앞 날 파일 불변"
        with gzip.open(Path(tmp) / "_raw" / "acc1_inventory_p1.json.gz", "rt", encoding="utf-8") as fh:
            assert fh.read() == b, "기존 _raw 동작(덮어쓰기) 그대로"
        assert any("[재고 보관]" in m for m in logs), logs

        _freeze("2026-11-07T15:30:12")
        _dump_inventory(tmp, [a])
        assert _files(tmp, DS.INVENTORY_DIRNAME)[-1] == "2026-11-07_153012.json.gz", _files(tmp, DS.INVENTORY_DIRNAME)
        assert _read(d / "2026-11-07.json.gz")["응답"] == [b], "같은 날 앞 파일 유지"

        n = len(_files(tmp, DS.INVENTORY_DIRNAME))
        logs = _dump_inventory(tmp, [])
        assert len(_files(tmp, DS.INVENTORY_DIRNAME)) == n and not any("재고 보관" in m for m in logs), "재고 없는 계정 no-op"

        orig = DS.save
        DS.save = _refuse_save
        try:
            logs = _dump_inventory(tmp, [a])
        finally:
            DS.save = orig
        assert any("[재고 보관] ⚠" in m for m in logs), logs
        assert (Path(tmp) / "_raw" / "acc1_inventory_p1.json.gz").exists()
    C.reset_raw()
    ok("날짜별 누적·_raw 불변·같은 날 시각 파일·재고 없음 no-op·저장 실패 비치명")


def s7_wiring():
    print("[S7] ① 수집 연결 — 로그인된 세션 페이지로·판매 기록 뒤·쿠폰 실패해도 계정 결과 그대로·데이터 없는 계정도 조회")
    order: list = []

    class FakeWing:
        def __init__(self, *a, **k):
            self.page = FakePage([], {}, fail={"/list?": (500, "busy")})

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            order.append("close")
            return False

    saved = {k: getattr(PS, k) for k in ("WingBrowser", "_login_with_candidates", "_discover_products", "_dump_raw",
                                         "_record_sales_periods", "_record_sales_history", "_record_sales_backfill")}
    PS.WingBrowser = FakeWing
    PS._login_with_candidates = lambda *a, **k: True
    PS._dump_raw = lambda *a, **k: None
    PS._record_sales_periods = lambda *a, **k: order.append("periods")
    PS._record_sales_history = lambda *a, **k: order.append("history")
    PS._record_sales_backfill = lambda *a, **k: order.append("backfill")
    orig_rec = WC.record_day

    def spy(page, account_id, out_dir, log, gap=(0, 0), **kw):
        order.append(("coupon", account_id, out_dir, gap))
        orig_rec(page, account_id, out_dir, log, gap=gap, **kw)
    WC.record_day = spy
    logs: list = []
    found = ([], [], {}, {}, {}, set(), {}, {}, {})
    try:
        for ret in (found, None):
            order.clear()
            PS._discover_products = lambda *a, r=ret, **k: r
            out = PS._login_and_discover(Account("acc1", "대표", "사업자"), "2026-11-05", "2026-11-05",
                                         None, logs.append)
            assert len(out) == 8, "반환 모양 그대로"
            assert (out[0] is not None) == (ret is not None), "쿠폰 실패가 계정 결과를 안 바꿈"
            names = [x[0] if isinstance(x, tuple) else x for x in order]
            assert names.index("backfill") < names.index("coupon") < names.index("close"), order
            assert ("coupon", "acc1", "output", PS._PERIOD_GAP_SEC) in order, order
    finally:
        WC.record_day = orig_rec
        for k, v in saved.items():
            setattr(PS, k, v)
    assert any("[쿠폰] ⚠" in m and "status=500" in m for m in logs), logs
    ok("브라우저 닫기 전·부가 조회 뒤·실패 비치명·반환 그대로")


def _stat(p: Path):
    return (p.stat().st_size, p.stat().st_mtime_ns) if p.exists() else None


def main():
    orig_now = DS._now
    real_db, orig_db = Path(config.SESSION_STATE_DB), config.SESSION_STATE_DB
    before = _stat(real_db)
    with tempfile.TemporaryDirectory() as tmp:
        config.SESSION_STATE_DB = str(Path(tmp) / "coupon_session_state.db")   # S7 로그인 관측을 임시 DB로
        try:
            s1_pages()
            s2_end_detection()
            s3_gap_and_period()
            s4_save_and_accumulate()
            s5_failures()
            s6_inventory()
            s7_wiring()
        finally:
            DS._now = orig_now
            config.SESSION_STATE_DB = orig_db
    assert _stat(real_db) == before, f"실 세션 상태 DB({real_db})를 건드림 — 검사는 임시 DB만 써야 함"
    print("쿠폰 목록·재고현황 날짜별 보관 오프라인 검증 통과")


if __name__ == "__main__":
    main()
