"""상품 정보 날짜별 보관(product_info · T-100) 오프라인 검증 — 로그인·쿠팡 호출 없음(결정적).

기대값 출처 = T-100 지시(2026-11-18 통제 세션) · D-296 ③ · D-316 ②④ · D-318 ④:
상품조회 응답에 있는 칸만 옵션(vid)별로 날짜별 보관 · 없는 칸은 지어내지 않고 '응답에 없음' · 기존 날짜별 보관 구조(daily_snapshot) ·
깨진 응답은 부분본 · 정산 쪽 조회 함수 하나(그 옵션이 마지막으로 보인 날 값) · 저장 실패 비치명.
가짜 응답의 칸 이름·모양 = 저장된 실제 응답(output/_raw/*_vendor_inventory_p*.json.gz)과 같다.

    python tools/verify_product_info_offline.py                 # 게이트(가짜 응답)
    python tools/verify_product_info_offline.py --raw <_raw 폴더>  # 받아 둔 실제 응답으로 칸 확인(게이트 밖 · 읽기만)
"""
from __future__ import annotations

import argparse
import glob
import gzip
import json
import os
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics import collector as C  # noqa: E402
from coupang_analytics import daily_snapshot as DS  # noqa: E402
from coupang_analytics import pipeline_sales as PS  # noqa: E402
from coupang_analytics import product_info as PI  # noqa: E402


def ok(msg):
    print(f"  ✔ {msg}")


def _listing(vinv, cat, options, **extra):
    """실제 응답 리스팅 모양(칸 일부) — 정산과 무관한 칸(brand 등)도 섞어 둔다(보관하지 않아야 함)."""
    d = {"vendorInventoryId": vinv, "vendorId": "A00", "productName": f"상품{vinv}", "registrationType": "NORMAL",
         "categoryName": f"분류{cat}", "displayCategoryCode": cat * 10, "categoryId": cat, "brand": "B",
         "productStatus": "ON_SALE", "deliveryChargeType": "FREE", "deliveryCharge": 0, "freeShipOverAmount": 0,
         "returnCharge": 4000, "vendorInventoryItems": options}
    d.update(extra)
    return d


def _option(vid, price=17900):
    return {"vendorInventoryItemId": vid + 1, "itemName": f"옵션{vid}", "registrationType": "RFM", "vendorItemId": vid,
            "salePrice": price, "stockQuantity": 5, "barcode": ""}


def _body(listings, page=1, total_pages=1):
    return json.dumps({"success": True, "data": {"productList": listings,
                                                 "pagination": {"totalPages": total_pages, "page": page}},
                       "message": None}, ensure_ascii=False)


def _freeze(ts: str):
    DS._now = lambda: datetime.fromisoformat(ts)


def _read(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def _names(root, acc="acc1"):
    d = Path(root) / PI.DIRNAME / acc
    return sorted(p.name for p in d.iterdir()) if d.is_dir() else []


def s1_extract():
    print("[S1] 뽑기 — 쪽 여러 개·옵션별 줄·있는 칸만·vid 문자열·vid 없는 옵션 제외·초도반품비 '응답에 없음'")
    p1 = _body([_listing(11, 5986, [_option(101), _option(102)]), _listing(12, 2584, [_option(103)])], 1, 2)
    p2 = _body([_listing(13, 2621, [_option(104), {"itemName": "승인 전", "vendorItemId": None}])], 2, 2)
    got = PI.extract([p1, p2])
    rows = {r["vendorItemId"]: r for r in got["상품"]}
    assert list(rows) == ["101", "102", "103", "104"], rows.keys()
    r = rows["101"]
    assert r["categoryId"] == 5986 and r["displayCategoryCode"] == 59860 and r["categoryName"] == "분류5986"
    assert r["returnCharge"] == 4000 and r["deliveryChargeType"] == "FREE" and r["vendorInventoryId"] == 11
    assert r["itemName"] == "옵션101" and r["salePrice"] == 17900 and r["registrationType"] == "RFM"
    assert "brand" not in r and "stockQuantity" not in r and "barcode" not in r, "정산과 무관한 칸은 담지 않음"
    assert "deliveryChargeOnReturn" not in r, "없는 칸을 지어내지 않음(0·빈값 채우기 없음)"
    assert got["응답에_없는_칸"] == ["deliveryChargeOnReturn"] and got["쪽"] == 2 and got["완전"] is True, got
    ok("옵션 4줄·categoryId 말단 값 그대로·무관 칸 제외·초도반품비 없음 표기·완전")


def s2_field_appears():
    print("[S2] 초도반품비 칸이 응답에 생기면 그대로 담음(코드 변경 없이)")
    got = PI.extract([_body([_listing(11, 1, [_option(101)], deliveryChargeOnReturn=5000)])])
    assert got["상품"][0]["deliveryChargeOnReturn"] == 5000 and got["응답에_없는_칸"] == [], got
    assert PI.extract([_body([])])["응답에_없는_칸"] == [], "상품 0개 계정 = 없는 칸 판정 안 함"
    ok("deliveryChargeOnReturn 5000 보관·없는 칸 목록 비움·빈 계정은 판정 안 함")


def s3_broken():
    print("[S3] 깨진 응답 — 비200 본문·success=false·쪽 모자람 = 완전 아님")
    good = _body([_listing(11, 1, [_option(101)])], 1, 1)
    for bad, why in (("<html>Access Denied</html>", "JSON 아님"),
                     (json.dumps({"success": False, "message": "x"}), "success=false"),
                     (json.dumps({"success": True, "data": {"pagination": {}}}), "productList 없음")):
        got = PI.extract([good, bad])
        assert got["완전"] is False and len(got["상품"]) == 1, (why, got)
    got = PI.extract([_body([_listing(11, 1, [_option(101)])], 1, 3)])
    assert got["완전"] is False, "3쪽 중 1쪽만"
    ok("JSON 아님·success=false·productList 없음·쪽 모자람 → 완전 아님(받은 줄은 남김)")


def _dump(tmp, bodies, acc="acc1"):
    C.reset_raw()
    for b in bodies:
        C._raw_add("vendor_inventory", b)
    logs: list[str] = []
    PS._dump_raw(acc, logs.append, out_dir=tmp)
    return logs


def s4_wiring_and_files():
    print("[S4] 수집 연결 — _dump_raw 가 상품조회 원문에서 날짜별 파일·같은 날 시각 파일·부분본·응답 없음 no-op·_raw 그대로")
    with tempfile.TemporaryDirectory() as tmp:
        _freeze("2026-11-18T09:00:00")
        logs = _dump(tmp, [_body([_listing(11, 5986, [_option(101)])])])
        assert _names(tmp) == ["2026-11-18.json.gz"], _names(tmp)
        rec = _read(Path(tmp) / PI.DIRNAME / "acc1" / "2026-11-18.json.gz")
        assert rec["계정"] == "acc1" and rec["날짜"] == "2026-11-18" and rec["상품"][0]["categoryId"] == 5986, rec
        assert any("[상품정보 보관] acc1: 옵션 1줄" in m for m in logs), logs
        assert (Path(tmp) / "_raw" / "acc1_vendor_inventory_p1.json.gz").exists(), "기존 원문 저장 그대로"

        _freeze("2026-11-18T15:30:12")
        _dump(tmp, [_body([_listing(11, 2584, [_option(101)])])])
        assert _names(tmp) == ["2026-11-18.json.gz", "2026-11-18_153012.json.gz"], _names(tmp)

        _freeze("2026-11-19T09:00:00")
        logs = _dump(tmp, ["<html>blocked</html>"])
        assert "2026-11-19_부분.json.gz" in _names(tmp) and any("부분본" in m for m in logs), (_names(tmp), logs)

        n = len(_names(tmp))
        C.reset_raw()
        C._raw_add("inventory", "{}")
        logs = []
        PS._dump_raw("acc1", logs.append, out_dir=tmp)
        assert len(_names(tmp)) == n and not any("상품정보" in m for m in logs), "상품조회 응답 없는 실행 = no-op"
    C.reset_raw()
    ok("날짜 파일·같은 날 시각 파일·깨진 날 부분본·no-op·_raw 불변")


def s5_lookup():
    print("[S5] 조회 함수 — 옵션이 마지막으로 보인 날 값·on 날짜 이하만·같은 날 뒤 파일 우선·부분본 무시·자료 없음 {}")
    with tempfile.TemporaryDirectory() as tmp:
        assert PI.lookup(tmp, "acc1") == {}, "보관 없음"
        _freeze("2026-11-10T09:00:00")
        _dump(tmp, [_body([_listing(11, 100, [_option(101), _option(102)])])])
        _freeze("2026-11-11T09:00:00")
        _dump(tmp, [_body([_listing(11, 200, [_option(101)])])])                    # 102 = 지워진 상품
        _freeze("2026-11-11T20:00:00")
        _dump(tmp, [_body([_listing(11, 300, [_option(101)])])])                    # 같은 날 다시 수집
        _freeze("2026-11-12T09:00:00")
        _dump(tmp, [_body([_listing(11, 999, [_option(101)])], 1, 2)])              # 부분본(쪽 모자람)
        got = PI.lookup(tmp, "acc1")
        assert got["101"]["categoryId"] == 300 and got["101"]["날짜"] == "2026-11-11", got["101"]
        assert got["102"]["categoryId"] == 100 and got["102"]["날짜"] == "2026-11-10", "지워진 옵션 = 마지막으로 보인 날"
        old = PI.lookup(tmp, "acc1", on="2026-11-10")
        assert old["101"]["categoryId"] == 100 and set(old) == {"101", "102"}, old
        assert PI.lookup(tmp, "acc2") == {}, "다른 계정 섞임 없음"
    C.reset_raw()
    ok("마지막으로 보인 날·on 이하·같은 날 뒤 파일·부분본 무시·계정 분리")


def s6_save_failure():
    print("[S6] 저장 실패 = 비치명(로그 ⚠·수집 계속)")
    orig = DS.save

    def refuse(*a, **k):
        raise PermissionError("잠김")
    DS.save = refuse
    try:
        with tempfile.TemporaryDirectory() as tmp:
            logs: list[str] = []
            assert PI.archive(tmp, "acc1", [_body([_listing(11, 1, [_option(101)])])], logs.append) is None
    finally:
        DS.save = orig
    assert any("[상품정보 보관] ⚠ acc1 저장 실패" in m for m in logs), logs
    ok("PermissionError → 로그만")


def _age(p: Path, day: str) -> None:
    t = datetime.fromisoformat(f"{day}T12:00:00").timestamp()
    os.utime(p, (t, t))


def s7_raw_keep():
    print("[S7] 상품조회 원문 통째 수집일별 보관(D-341) — _raw 덮어쓰기 전 옛 원문 · 같은 내용 생략 · 같은 날 다시 = 안 남김 · 읽는 쪽 그대로")
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "_raw"
        a1, a2 = _body([_listing(11, 1, [_option(101)])], 1, 2), _body([_listing(12, 2, [_option(102)])], 2, 2)
        b1 = _body([_listing(11, 9, [_option(101)])], 1, 2)
        _freeze("2026-11-17T09:00:00")
        _dump(tmp, [a1, a2])
        for i in (1, 2):
            _age(raw / f"acc1_vendor_inventory_p{i}.json.gz", "2026-11-17")
        _freeze("2026-11-18T09:00:00")
        _dump(tmp, [b1, a2])
        keep = raw / DS.KEEP_DIRNAME
        k1 = keep / "acc1_vendor_inventory_p1.json.gz"
        assert [p.name for p in k1.iterdir()] == ["2026-11-17.json.gz"], list(k1.iterdir())
        assert gzip.decompress((k1 / "2026-11-17.json.gz").read_bytes()).decode("utf-8") == a1, "옛 원문 통째(가공 없음)"
        assert not (keep / "acc1_vendor_inventory_p2.json.gz").exists(), "같은 내용 = 보관 생략"
        with gzip.open(raw / "acc1_vendor_inventory_p1.json.gz", "rt", encoding="utf-8") as fh:
            assert fh.read() == b1, "_raw = 새 원문(읽는 쪽 이름 그대로)"
        assert sorted(p.name for p in raw.glob("*_vendor_inventory_p*.json.gz")) == [
            "acc1_vendor_inventory_p1.json.gz", "acc1_vendor_inventory_p2.json.gz"], "읽는 쪽 glob 에 보관본 안 걸림"
        _age(raw / "acc1_vendor_inventory_p1.json.gz", "2026-11-18")
        _dump(tmp, [a1, a2])                                                         # 같은 날 다시 수집
        assert [p.name for p in k1.iterdir()] == ["2026-11-17.json.gz"], "같은 날 덮어쓰기 = 안 남김(그날 마지막 값은 다음날)"
        C.reset_raw()
        C._raw_add("inventory", "{}")
        PS._dump_raw("acc1", [].append, out_dir=tmp)
        assert not (keep / "acc1_inventory_p1.json.gz").exists(), "재고현황 = 이미 날짜별(재고현황_일별) — 대상 아님"
    C.reset_raw()
    ok("11-17 원문 = _raw\\수집일별보관\\acc1_vendor_inventory_p1.json.gz\\2026-11-17.json.gz · 같은 내용·같은 날 = 생략 · glob 그대로")


def real_raw(root: str) -> None:
    """받아 둔 실제 응답으로 칸 확인(게이트 밖 · 읽기만 · 결과는 화면에만)."""
    by_acc = defaultdict(list)
    for f in sorted(glob.glob(os.path.join(root, "*_vendor_inventory_p*.json.gz"))):
        acc = os.path.basename(f).rsplit("_vendor_inventory_p", 1)[0]
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            by_acc[acc].append(fh.read())
    tot = cat = 0
    missing: dict[str, int] = defaultdict(int)
    for acc, bodies in sorted(by_acc.items()):
        got = PI.extract(bodies)
        n = len(got["상품"])
        c = sum(r.get("categoryId") not in (None, "") for r in got["상품"])
        tot, cat = tot + n, cat + c
        for k in got["응답에_없는_칸"]:
            missing[k] += 1
        print(f"  {acc}: 쪽 {got['쪽']} · 옵션 {n} · categoryId {c} · 완전 {got['완전']} · 없는 칸 {got['응답에_없는_칸']}")
    print(f"  합계: 계정 {len(by_acc)} · 옵션 {tot} · categoryId 있는 옵션 {cat} · 없는 칸(계정 수) {dict(missing)}")


def s8_base_day():
    print("[S8] 기준일(D-362 · 통제 세션 11-19) — ① 이 넘긴 판매 조회 끝 날(date_to)을 상품정보·재고현황 파일 안 '기준일' 칸에 · "
          "파일 이름·'날짜'·'수집' 은 그대로(저장 시각) · 안 넘기면 칸 없음")
    from coupang_analytics import daily_snapshot as DSN
    with tempfile.TemporaryDirectory() as tmp:
        _freeze("2026-11-20T01:42:05")                       # 00:10 무인 ① = 다음 날 새벽 저장 · 판매 = 전날(11-19)
        C.reset_raw()
        C._raw_add("vendor_inventory", _body([_listing(11, 5986, [_option(101)])]))
        C._raw_add("inventory", json.dumps({"viProperties": [{"vendorItemId": 101}]}))
        logs: list[str] = []
        PS._dump_raw("acc1", logs.append, out_dir=tmp, base_day="2026-11-19")
        info = _read(Path(tmp) / PI.DIRNAME / "acc1" / "2026-11-20.json.gz")
        inv = _read(Path(tmp) / DSN.INVENTORY_DIRNAME / "acc1" / "2026-11-20.json.gz")
        for name, rec in (("상품정보", info), ("재고현황", inv)):
            assert rec["기준일"] == "2026-11-19" and rec["날짜"] == "2026-11-20" and rec["수집"] == "2026-11-20T01:42:05", \
                (name, {k: rec[k] for k in ("기준일", "날짜", "수집") if k in rec})
        assert PI.lookup(tmp, "acc1")["101"]["날짜"] == "2026-11-20", "정산 조회(lookup) 날짜 = 파일 날짜 그대로"
        _freeze("2026-11-20T14:00:00")
        _dump(tmp, [_body([_listing(11, 5986, [_option(101)])])])
        later = sorted((Path(tmp) / PI.DIRNAME / "acc1").glob("2026-11-20_*.json.gz"))
        assert later and "기준일" not in _read(later[-1]), "기준일 안 넘기면 칸 없음(정산 쪽·옛 호출)"
    ok("상품정보·재고현황 = 기준일 2026-11-19 + 날짜·수집 2026-11-20 01:42 · 파일 이름 그대로 · 안 넘기면 칸 없음")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", help="받아 둔 output/_raw 폴더(실제 응답 칸 확인 · 게이트 밖)")
    args = ap.parse_args()
    if args.raw:
        real_raw(args.raw)
        return 0
    saved_now = DS._now
    try:
        for s in (s1_extract, s2_field_appears, s3_broken, s4_wiring_and_files, s5_lookup, s6_save_failure, s7_raw_keep, s8_base_day):
            s()
    finally:
        DS._now = saved_now
    print("\n✅ 상품 정보 날짜별 보관 오프라인 검증 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
