"""로그인이 필요 없는 부분만 '실제로' 실행해 실증한다(가짜 아님).

- Tier1 (부작용 없음, 로컬): 입력 엑셀 파싱 · 제목 시드 추출 · 워크북 생성/저장/재로드 ·
  credstore DPAPI 암복호화 왕복 · 판매분석 리포트 파싱(합성 리포트로 실제 파서 실행).
- Tier2 (외부 네트워크, 로그인 아님): 저장된 네이버 검색광고 API 키가 있으면 실제 검색량 조회.

순위 조회/키워드 경쟁(실제 Chrome + 쿠팡 접속)은 별도(브라우저·외부 트래픽)라 여기 넣지 않는다.
실행: python tools/verify_offline.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

import openpyxl  # noqa: E402

from coupang_analytics import config  # noqa: E402
from coupang_analytics.collector import kind_of  # noqa: E402
from coupang_analytics.credstore import CredStore  # noqa: E402
from coupang_analytics.input_list import parse_input_list  # noqa: E402
from coupang_analytics.kw_recommend import select_keywords_light  # noqa: E402
from coupang_analytics.kw_volume import NaverAdApi, NaverCredentials  # noqa: E402
from coupang_analytics.report import parse_by_option  # noqa: E402
from coupang_analytics.workbook import OutputWorkbook  # noqa: E402

_REAL_INPUT = Path(r"D:\토탈셀러\셀독\토탈셀러_셀독 관리 대장 (3).xlsx")


def _ok(msg: str) -> None:
    print(f"    [실증] {msg}")


def _skip(msg: str) -> None:
    print(f"    [건너뜀] {msg}")


# ── Tier1 ─────────────────────────────────────────────────────
def t1_parse_input():
    print("[1] 입력 엑셀 파싱 (input_list.parse_input_list)")
    if not _REAL_INPUT.exists():
        _skip(f"입력 파일 없음: {_REAL_INPUT}")
        return None
    il = parse_input_list(str(_REAL_INPUT))
    n_prod = sum(len(a.products) for a in il.accounts)
    n_opt = sum(len(p.options) for a in il.accounts for p in a.products)
    n_vid = sum(len(o.vendor_item_ids) for a in il.accounts for p in a.products for o in p.options)
    _ok(f"계정 {len(il.accounts)}개 · 상품 {n_prod}개 · 옵션 {n_opt}개 · vendorItemId {n_vid}개 파싱")
    if il.errors:
        _ok(f"파싱 경고 {len(il.errors)}건(첫 항목: {il.errors[0][:40]})")
    if il.accounts:
        a0 = il.accounts[0]
        title = a0.products[0].name if a0.products else "(상품 없음)"
        _ok(f"예시 계정 '{a0.business_name}' 첫 상품: {title[:40]}")
    return il


def t1_workbook():
    print("[3] 워크북 생성/저장/재로드 (workbook, 셀독 서식 실제 xlsx I/O)")
    d = Path(tempfile.mkdtemp())
    wb = OutputWorkbook.empty()
    wb.ensure_product_block("비즈A", "상품A", config.KIND_CONTRACT, ["kw1", "kw2"])
    wb.set_keyword_rank("비즈A", "상품A", "kw1", "2026-09-02", 3)
    wb.set_keyword_rank("비즈A", "상품A", "kw2", "2026-09-02", None, scanned=44)   # 못찾음=센 개수 위밖
    wb.set_keyword_search("비즈A", "상품A", "kw1", 1200)
    wb.set_product_metric("비즈A", "상품A", config.M_VIEWS, "2026-09-02", 123)
    path = d / "실증_워크북.xlsx"
    wb.apply_style()
    wb.save(path)
    size = path.stat().st_size
    ws = openpyxl.load_workbook(path)["비즈A"]   # 시트명 = 사업자명
    flat = [c.value for row in ws.iter_rows() for c in row]
    assert "3위" in flat and 123 in flat and 1200 in flat, "값 재로드 실패"
    assert "44위밖" in flat, "미발견 순위 '44위밖'(센 개수) 미기록/유실"
    # 재로드 후 재개 조회(_reindex)도 실제로 동작하는지
    wb2 = OutputWorkbook.load(path)
    # 저장 시 apply_style→normalize_date_columns 가 라벨을 년도 없는 '월.일'(09.02)로 통일 → 그 라벨로 조회.
    assert wb2.is_rank_filled("비즈A", "상품A", "kw1", "09.02")
    assert wb2.product_keywords("비즈A", "상품A") == ["kw1", "kw2"]
    _ok(f"셀독 워크북 생성({size} bytes) → 재로드 → 값(순위3위·노출123·검색량1200)·재개조회 정상")


def t1_credstore():
    print("[4] credstore DPAPI 암복호화 왕복 (credstore, 실제 Windows DPAPI)")
    d = Path(tempfile.mkdtemp())
    store = CredStore(path=d / "creds_test.json")   # 실제 저장소는 안 건드림(임시 경로)
    secret = "비밀-테스트-!@#123"
    store.set_password("__probe__", secret)
    got = CredStore(path=d / "creds_test.json").get_password("__probe__")  # 새 인스턴스로 재로드
    assert got == secret, "DPAPI 왕복 불일치"
    raw = (d / "creds_test.json").read_text(encoding="utf-8")
    assert secret not in raw, "평문이 파일에 노출됨(암호화 실패)"
    _ok("임시 저장소에 set→저장→재로드→복호화 일치, 파일엔 평문 없음(암호화 확인)")
    # 실제 저장소의 키 '존재 여부'만 확인(값은 절대 출력 안 함)
    real = CredStore()
    present = [name for name in ("__naver__", "__openai__") if real.get_password(name)]
    _ok(f"실제 저장소에 보관된 키: {present if present else '없음'} (값은 표시 안 함)")
    return real


def t1_report_parse():
    print("[5] 판매분석 리포트 파싱 (report.parse_by_option, 합성 리포트로 실제 파서 실행)")
    d = Path(tempfile.mkdtemp())
    path = d / "합성리포트.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([config.RP_COL_PRODUCT, config.RP_COL_ITEM_ID, config.RP_COL_OPTION_ID,
               "옵션명", config.RP_COL_VIEWS, config.RP_COL_SALES, config.RP_COL_VISITORS])
    ws.append(["테스트상품", "ITEM1", "OPT100", "옵-그린", 111, 9, 55])
    ws.append(["테스트상품", "ITEM1", "OPT200", "옵-레드", 222, 4, 88])
    wb.save(path)
    metrics = parse_by_option(path)
    assert set(metrics) == {"OPT100", "OPT200"}, "옵션ID 파싱 실패"
    m = metrics["OPT100"]
    assert (m.views, m.sales, m.visitors) == (111, 9, 55), "지표 파싱 실패"
    _ok("리포트 2옵션 파싱 정상 (OPT100 노출111/판매9/방문55, OPT200 노출222/판매4/방문88)")


def t1_kind():
    print("[7] 상품 구분(로켓그로스/판매자배송/둘 다) 판별 + 워크북 재고행·라벨 마이그레이션")
    # kind_of 3분기(API registration_type)
    assert kind_of(["RFM", "RFM"]) == config.KIND_CONTRACT           # 전부 RFM=로켓그로스
    assert kind_of(["NORMAL"]) == config.KIND_PERSONAL               # RFM 없음=판매자배송
    assert kind_of([""]) == config.KIND_PERSONAL                     # 빈값=판매자배송
    assert kind_of(["RFM", "NORMAL"]) == config.KIND_BOTH            # 섞임=둘 다
    _ok(f"kind_of: RFM→{config.KIND_CONTRACT} · NORMAL→{config.KIND_PERSONAL} · 섞임→{config.KIND_BOTH}")
    # 둘 다(로켓그로스+판매자배송) 블록은 재고현황 행 포함(로켓그로스 파트)
    wb = OutputWorkbook.empty()
    wb.ensure_product_block("가게A", "상품B", config.KIND_BOTH, ["키워드1"])
    assert wb.has_product("가게A", "상품B")
    assert (wb._metric_row.get(("가게A", "상품B", config.M_INVENTORY)) is not None), "둘 다=재고행 있어야"
    # 라벨 마이그레이션: 기존 블록에 구분이 바뀌면 A열 라벨만 최신화(구조 불변)
    ws = wb.wb["가게A"]
    hdr = next(r for r in wb._date_rows["가게A"])
    assert ws.cell(hdr, 1).value == config.KIND_BOTH
    wb.ensure_product_block("가게A", "상품B", config.KIND_CONTRACT, ["키워드1"])   # 재호출=라벨만 갱신
    assert ws.cell(hdr, 1).value == config.KIND_CONTRACT, "구분 라벨 최신화 실패"
    _ok("둘 다 블록=재고행 포함 · 재호출 시 구분 라벨 최신화(마이그레이션)")
    # 개인→로켓그로스 마이그레이션 = **재고행 자동 추가**(역기록 공란 근본원인 수정, 2026-09-17)
    wb.ensure_product_block("가게A", "상품P", config.KIND_PERSONAL, ["kwP"])
    assert ("가게A", "상품P", config.M_INVENTORY) not in wb._metric_row, "개인은 재고행 없어야"
    wb.ensure_product_block("가게A", "상품P", config.KIND_CONTRACT, ["kwP"])   # 구분 변경
    assert ("가게A", "상품P", config.M_INVENTORY) in wb._metric_row, "개인→로켓그로스=재고행 추가돼야"
    assert wb.set_product_metric("가게A", "상품P", config.M_INVENTORY, "2026-09-16", 99)
    assert wb.product_inventory("가게A", "상품P") == 99, "추가된 재고행에 값 기록 실패"
    wb.ensure_product_block("가게A", "상품P", config.KIND_CONTRACT, ["kwP"])   # 멱등(중복 안 생김)
    assert sum(1 for k in wb._metric_row
               if k[:2] == ("가게A", "상품P") and k[2] == config.M_INVENTORY) == 1, "재고행 중복"
    _ok("개인→로켓그로스 재호출 시 재고행 자동 추가·값 기록·멱등(공란 역기록 수정)")


def t1_sale_status_flag():
    print("[8] 판매상태 불일치 경고 (collector 상태파서 + workbook 판정·렌더, 실제 xlsx I/O)")
    from coupang_analytics.collector import _parse_inventory_status
    # 상태 파서: listingDetails.isSaleSuspended(bool)만 채택, 필드없음·vid없음은 제외(미상)
    props = [{"vendorItemId": "V1", "listingDetails": {"isSaleSuspended": False}},
             {"vendorItemId": "V2", "listingDetails": {"isSaleSuspended": True}},
             {"vendorItemId": "V3", "listingDetails": {}},          # 필드 없음 → 제외
             {"listingDetails": {"isSaleSuspended": False}}]        # vid 없음 → 제외
    assert _parse_inventory_status(props) == {"V1": False, "V2": True}, "상태 파서 오류"
    # 상품단위 판정: 전부중지=판매중지·전부아님=판매중·섞임=부분판매중·맵에없음=미상
    wb = OutputWorkbook.empty()
    biz = "비즈판정"
    for nm, vids in [("판매중품", ["A1", "A2"]), ("부분품", ["B1", "B2"]),
                     ("중지품", ["C1"]), ("미상품", ["D1"])]:
        wb.ensure_product_block(biz, nm, config.KIND_CONTRACT, ["kw"])
        wb.set_product_vids(biz, nm, vids)
    wb.apply_sale_status(biz, {"A1": False, "A2": False, "B1": False, "B2": True, "C1": True})
    assert wb.sale_status(biz, "판매중품") == "판매중"
    assert wb.sale_status(biz, "부분품") == "부분판매중"
    assert wb.sale_status(biz, "중지품") == "판매중지"
    assert wb.sale_status(biz, "미상품") == ""            # 맵에 vid 없음 → 미상(빈값·기존 보존)
    _ok("상태파서·상품단위 판정(판매중/부분판매중/판매중지/미상) 정상")
    # 상품조회/수정 productStatus → 판매상태 매핑(판매자배송 포함 전 상품·방어적 해석)
    from coupang_analytics.collector import (sale_status_of, sale_status_by_vid,
                                             VendorInventoryListing, VendorInventoryOption)
    assert sale_status_of("ON_SALE") == "판매중"
    assert sale_status_of("PARTIAL_ON_SALE") == "부분판매중"
    assert sale_status_of("판매중") == "판매중"
    assert sale_status_of("DRAFT") == "임시저장"            # 소유자 2026-09-22: 판매중지로 안 뭉갬
    assert sale_status_of("REJECTED") == "승인반려"
    assert sale_status_of("UNDER_REVIEW") == "검토중"       # 라이브 nicoable 확인
    assert sale_status_of("SALE_STOP") == "판매중지"        # 미지 enum → 판매중지(안전한 실패=경보 누락)
    assert sale_status_of("") == ""                          # 빈값=미상
    # ── '둘다' 상품의 판매자배송(NORMAL) 중복 옵션 제외 = RFM(로켓그로스) vid 만 채택(재고 공란 방지) ──
    from coupang_analytics.collector import products_from_vendor_inventory

    def _opt(vid, rt, valid="VALID", up=False):
        return VendorInventoryOption(vendor_item_id=vid, item_name="베이지", registration_type=rt,
                                     valid=valid, is_upbundle=up)
    both = VendorInventoryListing(product_name="기저귀가방", vendor_inventory_id="g1",
                                  registration_type="", product_status="ON_SALE",
                                  options=[_opt("N_dup", "NORMAL"), _opt("R_real", "RFM")])
    prods = products_from_vendor_inventory([both])
    vids = [v for p in prods for o in p.options for v in o.vendor_item_ids]
    assert vids == ["R_real"], f"둘다 상품 NORMAL 중복 미제외(재고 공란 원인): {vids}"
    assert prods[0].kind == config.KIND_BOTH, "구분은 둘다 보존"
    # ── 업번들(자동번들) 옵션 제외 = 실입고 원상품만 추적(소유자 2026-09-24) ──
    ub = VendorInventoryListing(product_name="비타민", vendor_inventory_id="g2",
                                registration_type="RFM", product_status="ON_SALE",
                                options=[_opt("R_base", "RFM"), _opt("R_2pack", "RFM", up=True),
                                         _opt("R_3pack", "RFM", up=True)])
    ubv = [v for p in products_from_vendor_inventory([ub]) for o in p.options for v in o.vendor_item_ids]
    assert ubv == ["R_base"], f"업번들 옵션 미제외(원상품만 남아야): {ubv}"
    # 업번들만 있는 리스팅(원상품 없음·이론상 없음)은 제외돼 상품 0
    only_ub = VendorInventoryListing(product_name="번들만", vendor_inventory_id="g3",
                                     registration_type="RFM", product_status="ON_SALE",
                                     options=[_opt("R_only2", "RFM", up=True)])
    assert products_from_vendor_inventory([only_ub]) == [], "업번들만 있는 리스팅은 제외"
    # ── 재고 표기(소유자 2026-09-24 개정): 재고현황 있으면 값(0=품절)·**없으면 판매중지 무관 미입고** ──
    from coupang_analytics.pipeline import (_fill_product_metrics, _block_sale_status,
                                            _purge_upbundle_blocks)
    from coupang_analytics.workbook import _norm, _key
    # 판매상태 블록 판정: 모두 같으면 그 상태·섞이면 부분판매중·없으면 ''(미상)·bool 폴백 지원
    assert _block_sale_status(None, ["x"]) == ""
    assert _block_sale_status({"x": "판매중"}, ["x"]) == "판매중"
    assert _block_sale_status({"x": "판매중지"}, ["x"]) == "판매중지"
    assert _block_sale_status({"a": "판매중", "b": "판매중지"}, ["a", "b"]) == "부분판매중"
    assert _block_sale_status({"x": False}, ["x"]) == "판매중" and _block_sale_status({"x": True}, ["x"]) == "판매중지"
    assert _block_sale_status({"y": "판매중지"}, ["x"]) == ""     # 이 블록 vid 상태 없음 → 미상
    wbI = OutputWorkbook.empty()
    bzI = "재고비즈"
    for nm in ("입고품", "품절품", "미입고품", "중지품"):
        wbI.ensure_product_block(bzI, nm, config.KIND_CONTRACT, ["kw"])
        wbI.set_keyword_rank(bzI, nm, "kw", "2026-09-24", 1)     # 날짜 컬럼 생성

    def _raw_metric(nm, metric):
        row = wbI._metric_row.get((_norm(bzI), _key(nm), metric))
        dt = wbI.latest_date(bzI)
        col = wbI._date_col.get(bzI, {}).get(dt)
        return wbI.wb[bzI].cell(row, col).value if (row and col) else None

    def _raw_inv(nm):
        return _raw_metric(nm, config.M_INVENTORY)
    _fill_product_metrics(wbI, bzI, "입고품", ["V1"], config.KIND_CONTRACT, {}, {"V1": 7}, "2026-09-24",
                          sale_status={"V1": "판매중"})
    _fill_product_metrics(wbI, bzI, "품절품", ["V2"], config.KIND_CONTRACT, {}, {"V2": 0}, "2026-09-24")
    _fill_product_metrics(wbI, bzI, "미입고품", ["V3"], config.KIND_CONTRACT, {}, {}, "2026-09-24",
                          sale_status={"V3": "판매중"})
    _fill_product_metrics(wbI, bzI, "중지품", ["V4"], config.KIND_CONTRACT, {}, {}, "2026-09-24",
                          sale_status={"V4": "판매중지"})
    assert _raw_inv("입고품") == 7, "입고=재고현황 값"
    assert _raw_inv("품절품") == 0, "입고됐지만 품절=0(공란 아님)"
    assert _raw_inv("미입고품") == config.INV_NOT_INBOUND, f"미입고 표기: {_raw_inv('미입고품')!r}"
    # 개정: 판매중지여도 재고현황 없으면 **미입고**(옛 공란 폐기 — 소유자 2026-09-24)
    assert _raw_inv("중지품") == config.INV_NOT_INBOUND, f"판매중지+재고없음=미입고: {_raw_inv('중지품')!r}"
    # 판매상태 지표행(실행일마다 쿠팡 판매상태 기록·쿠팡 존중·재고칸과 별도) — 소유자 2026-09-24
    assert _raw_metric("입고품", config.M_SALE_STATUS) == "판매중", "판매상태행=판매중"
    assert _raw_metric("중지품", config.M_SALE_STATUS) == "판매중지", "판매상태행=판매중지(쿠팡 존중)"
    assert _raw_metric("품절품", config.M_SALE_STATUS) in (None, ""), "상태맵 없으면 판매상태 공란(미상)"
    # 역기록 가드: product_inventory 는 숫자만 반환('미입고' 문자열은 None → 대장 미접촉)
    assert wbI.product_inventory(bzI, "미입고품") is None, "'미입고' 문자열은 역기록 대상 아님"
    assert wbI.product_inventory(bzI, "품절품") == 0 and wbI.product_inventory(bzI, "입고품") == 7
    # 결과파일 표기 보장: apply_style + 저장 + 재로드 후에도 '미입고'·판매상태 문자열이 유지
    _dtmp = Path(tempfile.mkdtemp())
    wbI.apply_style()
    wbI.save(_dtmp / "재고표기.xlsx")
    wbR = OutputWorkbook.load(_dtmp / "재고표기.xlsx")
    _rowI = wbR._metric_row.get((_norm(bzI), _key("미입고품"), config.M_INVENTORY))
    _colI = wbR._date_col.get(bzI, {}).get(wbR.latest_date(bzI))
    assert wbR.wb[bzI].cell(_rowI, _colI).value == config.INV_NOT_INBOUND, "결과파일 저장 후 '미입고' 유실"
    _rowS = wbR._metric_row.get((_norm(bzI), _key("중지품"), config.M_SALE_STATUS))
    assert wbR.wb[bzI].cell(_rowS, _colI).value == "판매중지", "결과파일 저장 후 판매상태 유실"
    _ok("재고 표기(입고 값/품절 0/판매중지 무관 미입고)·판매상태 지표행(쿠팡 존중)·역기록 숫자가드·저장 후 유지")
    # ── 업번들 잔재 블록 매 수집 자동삭제(vid 기준·소유자 2026-09-24) ──
    wbU = OutputWorkbook.empty()
    bzU = "업번들비즈"
    wbU.ensure_product_block(bzU, "원상품", config.KIND_CONTRACT, ["kw"]); wbU.set_product_vids(bzU, "원상품", ["R_base"])
    wbU.ensure_product_block(bzU, "묶음잔재 (2개)", config.KIND_CONTRACT, [], rank_rows=False)
    wbU.set_product_vids(bzU, "묶음잔재 (2개)", ["R_2pack"])
    wbU.ensure_product_block(bzU, "블랙변형", config.KIND_CONTRACT, [], rank_rows=False); wbU.set_product_vids(bzU, "블랙변형", ["R_black"])
    _purge_upbundle_blocks(wbU, bzU, {"R_2pack"}, lambda m: None)   # 이번 상품조회 업번들 = R_2pack
    _left = set(wbU.products_of(bzU))
    assert "묶음잔재 (2개)" not in _left, "업번들 vid 블록 미삭제"
    assert "원상품" in _left and "블랙변형" in _left, "실vid 블록(원상품·변형)은 보존돼야"
    _purge_upbundle_blocks(wbU, bzU, set(), lambda m: None)         # 빈 집합(상품조회 실패) → no-op
    assert set(wbU.products_of(bzU)) == _left, "업번들 집합 비면 삭제 안 함(잘못된 삭제 방지)"
    _ok("업번들 잔재 블록 vid 기준 자동삭제(변형·실vid 보존)·빈 집합=no-op")
    # ── 죽은 중복 블록 sweep(안전 규칙·소유자 2026-09-24): live 형제 + vid 소멸 둘 다일 때만 삭제 ──
    from coupang_analytics.pipeline import _sweep_dead_duplicates
    wbS = OutputWorkbook.empty(); bzS = "죽은중복비즈"

    def _mk(nm, vid, reg):
        wbS.ensure_product_block(bzS, nm, config.KIND_CONTRACT, [], rank_rows=False, registered=reg)
        wbS.set_product_vids(bzS, nm, [vid])
    _mk("운동기구 (R601)", "V_live", "운동기구")       # 이번 추적된 대표(live)
    _mk("운동기구 (R601_)", "V_dead", "운동기구")      # 죽은 중복(같은 등록명·vid 소멸)
    _mk("운동기구 (블랙)", "V_variant", "운동기구")    # 변형(같은 등록명·vid 코팡에 남음)
    _mk("단종상품", "V_gone", "단종상품")             # 판매중지 단독(live 형제 없음·vid 소멸)
    live_vids = {"V_live", "V_variant"}   # 이번 상품조회 존재 vid(대표+변형만)
    _sweep_dead_duplicates(wbS, bzS, live_vids, lambda m: None)
    _rem = set(wbS.products_of(bzS))
    assert "운동기구 (R601_)" not in _rem, "죽은 중복(live 형제+vid 소멸) 미삭제"
    assert "운동기구 (R601)" in _rem and "운동기구 (블랙)" in _rem, "대표·변형(코팡 잔존 vid) 보존 실패"
    assert "단종상품" in _rem, "판매중지 단독(live 형제 없음)은 보존해야(데이터 유실 방지)"
    # 상품조회 실패(live_vids 비면) → no-op(오삭제 방지)
    wbS.ensure_product_block(bzS, "운동기구 (R601__)", config.KIND_CONTRACT, [], rank_rows=False, registered="운동기구")
    wbS.set_product_vids(bzS, "운동기구 (R601__)", ["V_dead2"])
    _sweep_dead_duplicates(wbS, bzS, set(), lambda m: None)
    assert "운동기구 (R601__)" in set(wbS.products_of(bzS)), "live_vids 비면 삭제 안 함(상품조회 실패 보호)"
    _ok("죽은 중복 sweep: live형제+vid소멸만 삭제 · 판매중지단독·변형·신규 보존 · 상품조회실패 no-op(엣지 5종)")
    # ── 응답 원문 보관(가공 없음·분석용, 소유자 2026-09-24): collector 버퍼 + pipeline gzip 사이드카 ──
    import gzip as _gz
    from coupang_analytics import collector as _col
    from coupang_analytics.pipeline import _dump_raw
    _col.reset_raw()
    _col._raw_add("vendor_inventory", '{"success":true,"data":{"x":1}}')
    _col._raw_add("inventory", '{"viProperties":[]}')
    _col._raw_add("sales", '{"vendorItems":[]}')
    dumps = _col.raw_dumps()
    assert set(dumps) == {"vendor_inventory", "inventory", "sales"}, f"원문 버퍼 키 오류: {list(dumps)}"
    assert dumps["vendor_inventory"] == ['{"success":true,"data":{"x":1}}'], "원문이 가공됨(그대로 보관 아님)"
    _draw = Path(tempfile.mkdtemp())
    _dump_raw("acctX", lambda m: None, out_dir=str(_draw))
    _f = _draw / "_raw" / "acctX_vendor_inventory_p1.json.gz"
    assert _f.exists(), "원문 gzip 파일 미생성"
    assert _gz.open(_f, "rt", encoding="utf-8").read() == '{"success":true,"data":{"x":1}}', "저장 원문이 원본과 불일치"
    _col.reset_raw()
    assert _col.raw_dumps() == {}, "reset_raw 후 버퍼 비어야"
    # 설정 끄면 no-op(파일 안 만듦)
    _sv = config.SAVE_RAW_RESPONSES
    config.SAVE_RAW_RESPONSES = False
    _col._raw_add("sales", "x"); assert _col.raw_dumps() == {}, "설정 끄면 원문 수집 안 함"
    config.SAVE_RAW_RESPONSES = _sv
    _ok("응답 원문 보관: 3 API 원문 그대로 버퍼→gzip 사이드카 저장·재로드 일치·reset·설정 off no-op")
    # ── 헤더 표시: 상품판매가·로켓그로스 입고일(근사) + vid 파싱 안전(줄 추가해도 vid 안 깨짐) ──
    from coupang_analytics.workbook import _vids_from_cell
    wbH = OutputWorkbook.empty(); bzH = "헤더비즈"
    wbH.ensure_product_block(bzH, "운동기구", config.KIND_CONTRACT, ["kw"])
    wbH.set_product_vids(bzH, "운동기구", ["V1", "V2"])
    wbH.set_product_extra(bzH, "운동기구", inbound_date="2026-06-25", inbound_summary="최근입고 : 09.11 요청200·출고08.07")
    from coupang_analytics.pipeline import _apply_vid_meta
    _apply_vid_meta(wbH, bzH, "운동기구", config.KIND_CONTRACT, ["V1"], {"V1": (35700, "2026-06-25")}, "2026-09-24")
    wbH.set_keyword_rank(bzH, "운동기구", "kw", "2026-09-24", 1)   # 날짜칸 확보
    _disp = wbH._display_name(bzH, "운동기구")
    assert "VID : V1 / V2" in _disp, f"VID 줄 없음: {_disp!r}"
    assert "로켓그로스 판매일 : 2026-06-25" in _disp, f"판매일 줄 없음(입고일→판매일): {_disp!r}"
    assert "최근입고 : 09.11 요청200·출고08.07" in _disp, f"최근입고 묶음 줄 없음: {_disp!r}"
    assert "상품판매가" not in _disp, f"판매가는 헤더 아니라 지표행이어야: {_disp!r}"
    # 판매가는 '판매가' 지표행(재고현황 아래)에 일자별
    _pr = wbH._metric_row.get((_norm(bzH), _key("운동기구"), config.M_SALE_PRICE))
    _pc = wbH._date_col.get(bzH, {}).get(wbH.latest_date(bzH))
    assert _pr and wbH.wb[bzH].cell(_pr, _pc).value == 35700, "판매가 지표행 일자별 기록 실패"
    # 🔒 vid 파싱 안전: 줄이 추가돼도 vid 는 'VID :' 줄만 정확히 파싱(오염 없음)
    assert _vids_from_cell(_disp) == ["V1", "V2"], f"vid 파싱 오염(치명): {_vids_from_cell(_disp)}"
    assert wbH.product_vids(bzH, "운동기구") == ["V1", "V2"], "product_vids 오염"
    # 저장→재로드 후에도 vid·판매일·최근입고 유지(라운드트립)
    _dh = Path(tempfile.mkdtemp()); wbH.apply_style(); wbH.save(_dh / "헤더.xlsx")
    wbH2 = OutputWorkbook.load(_dh / "헤더.xlsx")
    assert wbH2.product_vids(bzH, "운동기구") == ["V1", "V2"], "재로드 후 vid 유실"
    assert "로켓그로스 판매일 : 2026-06-25" in wbH2._display_name(bzH, "운동기구"), "재로드 후 판매일 유실"
    # 판매자배송(개인) → 로켓그로스 판매일 줄 생략(inbound_date=None)
    wbP = OutputWorkbook.empty()
    wbP.ensure_product_block("개인비즈", "개인상품", config.KIND_PERSONAL, ["kw"])
    wbP.set_product_vids("개인비즈", "개인상품", ["P1"])
    _apply_vid_meta(wbP, "개인비즈", "개인상품", config.KIND_PERSONAL, ["P1"], {"P1": (9900, "2026-06-25")}, "2026-09-24")
    _dp = wbP._display_name("개인비즈", "개인상품")
    assert "로켓그로스 판매일" not in _dp, f"판매자배송 판매일 줄 오출력: {_dp!r}"
    assert wbP._metric_row.get((_norm("개인비즈"), _key("개인상품"), config.M_SALE_PRICE)), "개인상품도 판매가 지표행 있어야"
    _ok("헤더 로켓그로스 묶음(판매일·최근입고)·판매가 지표행(일자별)·vid 파싱 안전·재로드 유지·판매자배송 판매일 생략")
    # vid별 전개 + apply_sale_status 문자열 경로(판매자배송 NORMAL 상품도 상태 커버)
    def _li(name, vid, status, rt="NORMAL"):
        return VendorInventoryListing(product_name=name, vendor_inventory_id="g_" + vid,
                                      registration_type=rt, product_status=status,
                                      options=[VendorInventoryOption(vendor_item_id=vid, item_name="",
                                                                     registration_type=rt)])
    listings = [_li("판매자배송중지품", "N1", "판매중지", "NORMAL"),   # 개인상품도 판정됨(옛 한계 해소)
                _li("판매자배송판매품", "N2", "ON_SALE", "NORMAL")]
    smap = sale_status_by_vid(listings)
    assert smap == {"N1": "판매중지", "N2": "판매중"}, f"vid별 전개 오류: {smap}"
    wb2 = OutputWorkbook.empty()
    for nm, vid in [("판매자배송중지품", "N1"), ("판매자배송판매품", "N2")]:
        wb2.ensure_product_block("개인가게", nm, config.KIND_PERSONAL, ["kw"])
        wb2.set_product_vids("개인가게", nm, [vid])
    wb2.apply_sale_status("개인가게", smap)                  # 문자열 맵(productStatus)
    assert wb2.sale_status("개인가게", "판매자배송중지품") == "판매중지"
    assert wb2.sale_status("개인가게", "판매자배송판매품") == "판매중", "판매자배송 상품 판매상태 미커버(옛 한계)"
    _ok("productStatus → 판매상태(판매자배송 포함 전 상품 커버)·apply_sale_status 문자열 경로 정상")
    # 렌더 왕복: 대장=판매중지 + 쿠팡=판매중 → 최신 날짜칸에 '판매중' 적색·굵게 (멱등)
    d = Path(tempfile.mkdtemp())
    wb2 = OutputWorkbook.empty()
    bz, nm = "비즈렌더", "손세정기"
    wb2.ensure_product_block(bz, nm, config.KIND_CONTRACT, ["소독"])
    wb2.set_product_vids(bz, nm, ["Z1"])
    wb2.set_keyword_rank(bz, nm, "소독", "2026-09-16", 5)   # 날짜 컬럼 생성
    wb2.set_discontinued(bz, nm, True)                       # 대장에서 빠짐 = 판매중지
    wb2.apply_sale_status(bz, {"Z1": False})                 # 쿠팡 실제 = 판매중
    path = d / "판매상태.xlsx"
    wb2.apply_style(); wb2.save(path)
    ws = openpyxl.load_workbook(path)[bz]
    kh = next(r for r in range(1, ws.max_row + 1)
              if str(ws.cell(r, 7).value or "").strip() == "⛔ 판매중지")
    warn = ws.cell(kh, ws.max_column)
    assert warn.value == "판매중", f"경고셀 값={warn.value!r}"
    rgb = warn.font.color.rgb if warn.font and warn.font.color else None
    assert warn.font.bold and str(rgb).endswith("C00000"), f"서식 미적용(rgb={rgb})"
    # 멱등: 재로드→apply_style 재적용에도 유지
    wb3 = OutputWorkbook.load(path); wb3.apply_style(); wb3.save(path)
    ws3 = openpyxl.load_workbook(path)[bz]
    kh3 = next(r for r in range(1, ws3.max_row + 1)
               if str(ws3.cell(r, 7).value or "").strip() == "⛔ 판매중지")
    assert ws3.cell(kh3, ws3.max_column).value == "판매중", "멱등 재적용 실패"
    _ok(f"대장=판매중지+쿠팡=판매중 → 최신 날짜칸 '판매중'(적색 {rgb}·굵게) 렌더·멱등 확인")


def t1_representative_column():
    print("[9] 계정목록 대표자 컬럼 (workbook set/representative_of + _build_index A열, 실제 xlsx I/O)")
    wb = OutputWorkbook.empty()
    wb.set_account_id("가게A", "idA")
    wb.set_representative("가게A", "홍길동")
    wb.mark_sales_collected("가게A", "09.17")   # 3열=판매수집일과 4열=대표자 충돌 없어야
    assert wb.representative_of("가게A") == "홍길동", "대표자 저장/조회 실패(3열 판매수집일과 충돌?)"
    assert wb.has_sales("가게A", "09.17"), "판매수집일(3열) 손상"
    wb.ensure_product_block("가게A", "텀블러", config.KIND_CONTRACT, ["텀블러"])
    wb.set_keyword_rank("가게A", "텀블러", "텀블러", "2026-09-17", 3)
    d = Path(tempfile.mkdtemp()); path = d / "대표자.xlsx"
    wb.apply_style(); wb.save(path)
    ws = openpyxl.load_workbook(path)["계정 목록"]
    heads = [ws.cell(2, c).value for c in range(1, 9)]
    assert heads[0] == "대표자" and heads[1] == "사업자" and heads[3] == "계정ID" and heads[7] == "상태", heads
    assert ws.cell(3, 1).value == "홍길동" and ws.cell(3, 2).value == "가게A" and ws.cell(3, 4).value == "idA"
    wb2 = OutputWorkbook.load(path)
    assert wb2.representative_of("가게A") == "홍길동" and wb2.has_sales("가게A", "09.17")
    _ok("계정목록 헤더 8열(A=대표자)·데이터행 대표자 렌더·판매수집일(3열)과 무충돌·재로드 보존")


def t1_product_match_precision():
    print("[11] 대장↔쿠팡 정밀 매칭 (product_match — 오매칭 차단·미달=미매칭 공란)")
    from coupang_analytics.input_list import Option, Product
    from coupang_analytics.product_match import scope_to_ledger

    def disc(title, vid, kind=config.KIND_CONTRACT):
        return Product(name=title, title=title, kind=kind, options=[Option("", [vid], [])])

    # 발견(쿠팡) = 관리 상품 + 비관리(직접판매) 상품 섞임
    discovered = [
        disc("웰빙곳간 활력 볶은 맥문동 환 프리미엄 30포 국산", "v_maek"),      # 관리(맥문동)
        disc("웰빙곳간 프리미엄 사과초모식초 애플사이다비니거 600mg", "v_sacho"),  # 비관리(사과초모식초)
        disc("웰빙곳간 프리미엄 베타글루칸 MAX 4개월분 베타글루칸분말 88%", "v_beta"),  # 관리(베타글루칸)
        disc("블루투스 이어폰 프로", "v_ear1"),                                # 애매쌍 A
        disc("블루투스 이어폰 라이트", "v_ear2"),                              # 애매쌍 B
    ]
    ledger = [
        Product(name="웰빙곳간 활력 볶은 맥문동 환 프리미엄 30포"),   # → v_maek (핵심어 맥문동)
        Product(name="웰빙곳간 베타글루칸 프리미엄 MAX 120정"),       # → v_beta (핵심어 베타글루칸)
        Product(name="웰빙곳간 동결건조 로얄제리 120정"),            # 핵심어(로얄제리) 발견에 없음 → 미매칭
        Product(name="블루투스 이어폰"),                            # A·B 동점 → 애매 → 미매칭
    ]
    tracked, n = scope_to_ledger(ledger, discovered)
    vids = [sorted(v for o in tp.options for v in o.vendor_item_ids) for tp in tracked]
    assert vids[0] == ["v_maek"], f"맥문동 매칭 실패: {vids[0]}"
    assert vids[1] == ["v_beta"], f"베타글루칸 매칭 실패: {vids[1]}"
    assert vids[2] == [], "핵심어 없는 상품이 매칭됨(오매칭)"
    assert vids[3] == [], "애매쌍이 매칭됨(마진 미달인데 매칭)"
    # 비관리 상품(사과초모식초)은 어떤 대장 행에도 안 붙음
    assert not any("v_sacho" in vs for vs in vids), "비관리 상품이 대장에 붙음(오매칭)"
    assert n == 2, f"매칭 수 {n} (기대 2)"
    # 미매칭 행은 대장명으로 추적(공란 통계) — 이름 보존
    assert tracked[2].name == "웰빙곳간 동결건조 로얄제리 120정"
    assert tracked[3].name == "블루투스 이어폰"
    _ok("핵심어 게이트·마진으로 오매칭 차단(비관리·애매 미매칭=공란)·정매칭 2건·미매칭은 대장명 유지")
    # 규격 타이브레이커: 핵심어 동점(변형)일 때 규격(120정/30포)으로 vid 확정 — 규격 다르면 각 변형에 정확 배정
    disc2 = [
        disc("웰빙곳간 루바브 치커리 뿌리 추출물 정 120정", "v_120"),   # 변형 A(120정)
        disc("웰빙곳간 루바브 치커리 뿌리 추출물 정", "v_none"),        # 변형 B(규격 없음)
        disc("웰빙곳간 퀘르세틴 브로멜라인 MAX 120정", "v_q120"),      # 퀘르세틴 120정
        disc("웰빙곳간 퀘르세틴 브로멜라인 로얄 30포", "v_q30"),       # 퀘르세틴 30포
    ]
    led2 = [
        Product(name="웰빙곳간 루바브 치커리 뿌리 추출물 정 120정"),   # → v_120 (규격 120정)
        Product(name="웰빙곳간 퀘르세틴 브로멜라인 MAX 120정"),        # → v_q120 (규격 120정)
        Product(name="웰빙곳간 퀘르세틴 브로멜라인 로얄 30포"),        # → v_q30  (규격 30포)
    ]
    t2, n2 = scope_to_ledger(led2, disc2)
    v2 = [sorted(v for o in tp.options for v in o.vendor_item_ids) for tp in t2]
    assert v2[0] == ["v_120"], f"루바브 규격 타이브레이커 실패: {v2[0]}"
    assert v2[1] == ["v_q120"], f"퀘르세틴 120정 타이브레이커 실패: {v2[1]}"
    assert v2[2] == ["v_q30"], f"퀘르세틴 30포 타이브레이커 실패: {v2[2]}"
    # 규격이 서로를 못 가르면(둘 다 120정) 여전히 미매칭(오매칭 방지)
    disc3 = [disc("웰빙곳간 진세노사이드 홍삼 120정", "v_h1"), disc("웰빙곳간 진세노사이드 홍삼정 120정", "v_h2")]
    t3, _ = scope_to_ledger([Product(name="웰빙곳간 진세노사이드 홍삼 120정")], disc3)
    assert not any(o.vendor_item_ids for o in t3[0].options), "규격 동일 애매쌍이 매칭됨(오매칭)"
    _ok("규격 타이브레이커: 변형(120정/30포) vid 정확 확정·규격 동일 애매쌍은 미매칭 유지")


def t1_vid_source_option_split():
    print("[12] VID 출처=이름칸 + 옵션 분리 블록 + 마이그레이션 (workbook, 실제 xlsx I/O)")
    d = Path(tempfile.mkdtemp())
    biz = "옵션가게"
    base = "캠핑 타프 그늘막"
    rep, sec = base, f"{base} (그레이)"
    wb = OutputWorkbook.empty()
    # 대표(첫 옵션)=키워드+순위행 / 2차 옵션=판매정보만(rank_rows=False)·등록상품명 기준명 공유
    wb.ensure_product_block(biz, rep, config.KIND_CONTRACT, ["타프"], rank_rows=True, registered=base)
    wb.set_product_vids(biz, rep, ["v_beige"])
    wb.ensure_product_block(biz, sec, config.KIND_CONTRACT, [], rank_rows=False, registered=base)
    wb.set_product_vids(biz, sec, ["v_gray"])
    assert wb.has_keyword_section(biz, rep), "대표 블록에 키워드 구역 없음"
    assert not wb.has_keyword_section(biz, sec), "2차 옵션 블록에 키워드 구역이 생김(순위행 없어야)"
    # ③ 리스팅 순위 매칭 = 같은 등록상품명 두 블록의 vid 합집합
    assert sorted(wb.sibling_vids(biz, rep)) == ["v_beige", "v_gray"], f"sibling_vids 합집합 오류: {wb.sibling_vids(biz, rep)}"
    assert sorted(wb.sibling_vids(biz, sec)) == ["v_beige", "v_gray"], "2차 블록 sibling_vids 오류"
    # vid 출처=이름칸 → 숨김시트 3열 미사용 + 재로드 왕복 복원
    path = d / "옵션.xlsx"
    wb.apply_style(); wb.save(path)
    meta = openpyxl.load_workbook(path)["_상품ID"]
    col3 = [meta.cell(r, 3).value for r in range(2, meta.max_row + 1)]
    assert all(not v for v in col3), f"숨김시트 3열에 vid 잔존(폐지 대상): {col3}"
    wb2 = OutputWorkbook.load(path)
    assert wb2.product_vids(biz, rep) == ["v_beige"], f"대표 vid 이름칸 복원 실패: {wb2.product_vids(biz, rep)}"
    assert wb2.product_vids(biz, sec) == ["v_gray"], "2차 vid 이름칸 복원 실패"
    assert sorted(wb2.sibling_vids(biz, rep)) == ["v_beige", "v_gray"], "재로드 후 sibling_vids 오류"
    _ok("옵션 분리(대표=키워드+순위·2차=판매정보만)·sibling_vids 합집합·vid 출처=이름칸(숨김3열 폐지) 재로드 왕복")
    # 마이그레이션: 옛 블록(옛 이름·전 옵션 vid·키워드·과거 순위) → 대표 등록상품명으로 정규화(이력 승계)
    wb3 = OutputWorkbook.empty()
    old = "옛노출명 캠핑타프"
    wb3.ensure_product_block(biz, old, config.KIND_CONTRACT, ["타프", "그늘막"], registered=base)
    wb3.set_product_vids(biz, old, ["v_beige", "v_gray"])
    wb3.set_keyword_rank(biz, old, "타프", "09.01", 5)          # 과거 이력
    assert wb3.set_display_name(biz, old, base), "마이그레이션 리네임 실패"
    assert wb3.product_vids(biz, base) == ["v_beige", "v_gray"], f"리네임 후 vid 이동 실패: {wb3.product_vids(biz, base)}"
    assert wb3.product_keywords(biz, base) == ["타프", "그늘막"], "리네임에 키워드(이력) 보존 실패"
    assert old not in wb3.products_of(biz), "옛 블록명 잔존(중복)"
    p2 = d / "마이그.xlsx"; wb3.apply_style(); wb3.save(p2)
    wb4 = OutputWorkbook.load(p2)
    assert wb4.product_vids(biz, base) == ["v_beige", "v_gray"], "재로드 후 이관 vid 유실"
    _ok("마이그레이션: 옛 블록 → 등록상품명 정규화(vid·키워드·과거 순위 승계)·재로드 보존")
    # 단일 블록 삭제(vid 변경 시 이전 데이터 리셋용) — 대상만 삭제·나머지 블록 온전·재로드 보존
    wb5 = OutputWorkbook.empty()
    bz2 = "리셋가게"
    for nm, vid in [("유지품", "K1"), ("삭제품", "K2")]:
        wb5.ensure_product_block(bz2, nm, config.KIND_CONTRACT, ["kw"], registered=nm)
        wb5.set_product_vids(bz2, nm, [vid])
        wb5.set_keyword_rank(bz2, nm, "kw", "09.01", 4)
    assert wb5.blocks_with_registered_name(bz2, "삭제품") == ["삭제품"], "등록명 매칭 조회 오류"
    assert wb5.delete_product_block(bz2, "삭제품"), "블록 삭제 실패"
    assert "삭제품" not in wb5.products_of(bz2), "삭제 블록 잔존"
    assert wb5.product_vids(bz2, "삭제품") == [], "삭제 블록 vid 잔존(메타)"
    assert "유지품" in wb5.products_of(bz2) and wb5.product_vids(bz2, "유지품") == ["K1"], "다른 블록 손상"
    p3 = d / "리셋.xlsx"; wb5.apply_style(); wb5.save(p3)
    wb6 = OutputWorkbook.load(p3)
    assert wb6.products_of(bz2) == ["유지품"] and wb6.product_vids(bz2, "유지품") == ["K1"], "재로드 후 삭제/유지 불일치"
    _ok("단일 블록 삭제(delete_product_block): 대상만 제거·나머지 온전·메타 정리·재로드 보존")


def t1_ledger_dedup():
    print("[13] 대장 중복 상품 제거 (같은 상품명 2줄 이상 = 담당자 오입력 → 첫 줄만 추적)")
    from coupang_analytics.input_list import parse_input_rows
    rows = [
        ["대표자명", "사업자명", "계정아이디", "상품명"],
        ["홍길동", "테스트샵", "acctA", "웰빙 알부민 120정"],
        ["", "", "", "웰빙 알부민 120정"],       # 중복(오입력) 2줄째
        ["", "", "", "웰빙  알부민  120정"],     # 공백만 다른 중복(3줄째) — 공백정리 후 동일
        ["", "", "", "웰빙 베타글루칸"],
    ]
    il = parse_input_rows(rows)
    a = next(x for x in il.accounts if x.account_id == "acctA")
    names = [p.name for p in a.products]
    assert names == ["웰빙 알부민 120정", "웰빙 베타글루칸"], f"중복 제거 실패: {names}"
    assert any("중복" in s for s in il.struck), "중복 경고 로그 없음"
    _ok(f"같은 상품명 3줄(공백차이 포함) → 1개만 추적 {names}·중복 경고 남김")


def t1_date_columns():
    print("[14] 일자 컬럼 — 연말/연초 경계 보정 (workbook _parse_date nearest-year·정규화 폭발 방지)")
    import coupang_analytics.workbook as wbmod
    from datetime import date as _rdate

    class _FakeJan(_rdate):
        @classmethod
        def today(cls):
            return cls(2027, 1, 5)   # '오늘'을 1월로 고정(연초)

    orig = wbmod._date
    wbmod._date = _FakeJan
    try:
        wb = OutputWorkbook.empty()
        wb.ensure_product_block("경계", "상품", config.KIND_CONTRACT, ["kw"])
        wb.set_keyword_rank("경계", "상품", "kw", "12.30", 3)   # 작년 12/30 → 오늘(1/5)과 가까운 연도=2026
        wb.set_keyword_rank("경계", "상품", "kw", "01.02", 4)   # 올해 1/2 → 2027
        wb.normalize_date_columns()
        cols = wb._date_col.get("경계", {})
    finally:
        wbmod._date = orig
    # 12/30~1/2 = 연속 4일. 버그(월.일=무조건 올해)면 1/2~12/30 = 363칸 폭발.
    assert len(cols) <= 8, f"연말/연초 경계에서 일자 컬럼 폭발: {len(cols)}개(기대 ≤8)"
    _ok(f"연말/연초 경계: 12월+1월 라벨 → 일자 컬럼 {len(cols)}개(폭발 없음)")

    # (B) 같은 날짜가 옛 라벨('26.09.14')+신 라벨('09.14') 두 컬럼으로 공존 → 정규화가 하나로
    #     합칠 때 나중(오늘 새로 쓴) 값이 유실되면 안 됨(버그: 첫 컬럼만 스냅샷).
    wb2 = OutputWorkbook.empty()
    wb2.ensure_product_block("중복", "상품", config.KIND_CONTRACT, ["kw"])
    wb2.set_keyword_rank("중복", "상품", "kw", "26.09.14", 3)   # 옛 라벨 컬럼(과거값 3위)
    wb2.set_keyword_rank("중복", "상품", "kw", "09.14", 5)      # 신 라벨 컬럼(오늘 새로 쓴 5위)
    assert len(wb2._date_col.get("중복", {})) == 2, "같은 날 두 라벨이 두 컬럼으로 안 만들어짐(전제 실패)"
    wb2.normalize_date_columns()
    cols2 = wb2._date_col.get("중복", {})
    assert list(cols2) == ["09.14"], f"같은 날 두 컬럼이 하나로 안 합쳐짐: {list(cols2)}"
    row = wb2._kw_row[("중복", "상품", "kw")]
    val = wb2.wb["중복"].cell(row, cols2["09.14"]).value
    assert val == "5위", f"합칠 때 오늘 값(5위) 유실 — 남은 값: {val!r}"
    _ok("같은 날 옛/신 라벨 2컬럼 → 하나로 합치되 최신(오늘) 값 보존")

    # (C) 최신 날짜가 항상 맨 왼쪽 날짜칸(H열)·오래된 날짜는 오른쪽 = 내림차순(소유자 2026-09-23)
    wb3 = OutputWorkbook.empty()
    wb3.ensure_product_block("정렬", "상품", config.KIND_CONTRACT, ["kw"])
    wb3.set_keyword_rank("정렬", "상품", "kw", "09.01", 1)
    wb3.set_keyword_rank("정렬", "상품", "kw", "09.02", 2)
    wb3.set_keyword_rank("정렬", "상품", "kw", "09.03", 3)   # 최신
    wb3.set_product_metric("정렬", "상품", config.M_VIEWS, "09.01", 50)
    wb3.set_product_metric("정렬", "상품", config.M_VIEWS, "09.03", 100)   # 지표 최신
    wb3.normalize_date_columns()
    cols3 = wb3._date_col["정렬"]
    assert cols3["09.03"] == min(cols3.values()), f"최신(09.03)이 맨 왼쪽 칸 아님: {cols3}"
    assert cols3["09.03"] < cols3["09.02"] < cols3["09.01"], f"내림차순(최신←오래된→오른쪽) 아님: {cols3}"
    assert wb3.latest_date("정렬") == "09.03", f"latest_date 날짜기준 아님: {wb3.latest_date('정렬')}"
    assert wb3.product_latest_date("정렬", "상품") == "09.03", "product_latest_date 날짜기준 아님"
    _ok("최신 날짜=맨 왼쪽(H열)·오래된=오른쪽(내림차순)·latest_date/product_latest_date 날짜기준")


def t1_inventory_missing_error():
    print("[15] 재고 표기 규칙 (재고현황 값/0=품절/**판매중지 무관 미입고**·재고=재고현황 API만·소유자 2026-09-24 개정)")
    from coupang_analytics.pipeline import _fill_product_metrics
    from coupang_analytics.workbook import _norm, _key
    wb = OutputWorkbook.empty()
    for nm in ("로켓상품", "품절상품", "중지상품", "개인상품"):
        kd = config.KIND_PERSONAL if nm == "개인상품" else config.KIND_CONTRACT
        wb.ensure_product_block("재고샵", nm, kd, ["kw"])
        wb.set_keyword_rank("재고샵", nm, "kw", "09.21", 1)   # 날짜 컬럼 생성(재고 셀 대상)

    def _inv(nm):
        row = wb._metric_row.get((_norm("재고샵"), _key(nm), config.M_INVENTORY))
        col = wb._date_col.get("재고샵", {}).get(wb.latest_date("재고샵"))
        return wb.wb["재고샵"].cell(row, col).value if (row and col) else None
    logs: list[str] = []
    # (A) 로켓그로스인데 재고현황에 vid 없음 + 판매중(기본) → '미입고'(실입고 안 됨). [재고오류] 아님.
    _fill_product_metrics(wb, "재고샵", "로켓상품", ["v1"], config.KIND_CONTRACT, {}, {}, "09.21", log=logs.append)
    assert _inv("로켓상품") == config.INV_NOT_INBOUND, f"미입고 표기 아님: {_inv('로켓상품')!r}"
    assert not any("[재고오류]" in m for m in logs), f"미입고인데 재고오류 뜸: {logs}"
    # (B) 재고현황에 vid 있음 → 값 기록(0=품절도 기록)
    logs.clear()
    _fill_product_metrics(wb, "재고샵", "로켓상품", ["v1"], config.KIND_CONTRACT, {}, {"v1": 5}, "09.21", log=logs.append)
    assert _inv("로켓상품") == 5 and any("재고 5" in m for m in logs), f"재고 값 기록 실패: {logs}"
    _fill_product_metrics(wb, "재고샵", "품절상품", ["v2"], config.KIND_CONTRACT, {}, {"v2": 0}, "09.21")
    assert _inv("품절상품") == 0, "입고됐지만 품절=0(공란·미입고 아님)"
    # (C) 판매중지 + 재고현황 없음 → **미입고**(소유자 2026-09-24 개정: 옛 공란 폐기·판매상태 무관). 판매상태는 별도 지표행에.
    _fill_product_metrics(wb, "재고샵", "중지상품", ["v3"], config.KIND_CONTRACT, {}, {}, "09.21",
                          sale_status={"v3": "판매중지"})
    assert _inv("중지상품") == config.INV_NOT_INBOUND, f"판매중지+재고없음=미입고 아님: {_inv('중지상품')!r}"
    _srow = wb._metric_row.get((_norm("재고샵"), _key("중지상품"), config.M_SALE_STATUS))
    _scol = wb._date_col.get("재고샵", {}).get(wb.latest_date("재고샵"))
    assert wb.wb["재고샵"].cell(_srow, _scol).value == "판매중지", "판매상태는 별도 지표행에 판매중지 기록"
    # (D) 판매자배송(개인)=재고 개념 없음 → 미입고/재고 표기 안 함
    logs.clear()
    _fill_product_metrics(wb, "재고샵", "개인상품", ["v4"], config.KIND_PERSONAL, {}, {}, "09.21", log=logs.append)
    assert _inv("개인상품") in (None, ""), "개인상품 재고칸 표기 오탐"
    assert all("vid=" in m for m in logs), f"항목 로그에 vid 누락(공통함수 _ilog): {logs}"
    _ok("재고=재고현황(값/0=품절)·없으면 판매중지 무관 미입고·판매상태는 별도 지표행·개인상품 미표기·항목로그 vid 필수")


def t1_delete_account():
    print("[10] 삭제된 계정 완전 제거 (workbook.delete_account — 시트+메타 삭제)")
    wb = OutputWorkbook.empty()
    for biz, aid in (("가게A", "idA"), ("가게B", "idB")):
        wb.set_account_id(biz, aid)
        wb.set_representative(biz, "대표" + biz[-1])
        wb.ensure_product_block(biz, "상품" + biz[-1], config.KIND_CONTRACT, ["kw"])
        wb.set_product_vids(biz, "상품" + biz[-1], ["1" + biz[-1]])
        wb.set_keyword_rank(biz, "상품" + biz[-1], "kw", "2026-09-17", 3)
        wb.set_marketing(biz, "상품" + biz[-1], "2026-09-01", "", "")
    assert "가게A" in wb.account_sheets() and "가게B" in wb.account_sheets()
    # 가게A 완전 삭제
    assert wb.delete_account("가게A") is True
    assert "가게A" not in wb.account_sheets(), "시트 삭제 실패"
    assert wb.account_id_of("가게A") == "" and wb.representative_of("가게A") == "", "계정정보 메타 잔존"
    assert wb.product_vids("가게A", "상품A") == [], "상품ID 메타 잔존"
    assert not wb.marketing_of("가게A", "상품A")[0], "마케팅 메타 잔존"
    # 가게B는 온전
    assert "가게B" in wb.account_sheets() and wb.account_id_of("가게B") == "idB"
    assert wb.product_keywords("가게B", "상품B") == ["kw"]
    # 저장/재로드 왕복(구조 정합)
    d = Path(tempfile.mkdtemp()); path = d / "삭제.xlsx"
    wb.apply_style(); wb.save(path)
    wb2 = OutputWorkbook.load(path)
    assert "가게A" not in wb2.account_sheets() and "가게B" in wb2.account_sheets()
    idx = openpyxl.load_workbook(path)["계정 목록"]
    bizs = {idx.cell(r, 2).value for r in range(3, idx.max_row + 1)}   # B열=사업자
    assert "가게A" not in bizs and "가게B" in bizs, bizs
    _ok("가게A 시트·이력·메타(계정정보/상품ID/마케팅) 완전 삭제·가게B 온전·계정목록에서도 사라짐")


def t1_promo_effect():
    print("[13] 체험단효과(promo_effect) — 시작일 직전값→최신값 점 비교·최고순위·판정색")
    wb = OutputWorkbook.empty()
    wb.ensure_product_block("가게P", "상품P", config.KIND_CONTRACT, ["kw1", "kw2"])
    wb.set_marketing("가게P", "상품P", "2026-09-10", "", "")          # 체험단 시작일
    # 판매량: 시작 직전(09.05)=100 → 최신(09.20)=138  → +38%
    wb.set_product_metric("가게P", "상품P", config.M_SALES, "2026-09-05", 100)
    wb.set_product_metric("가게P", "상품P", config.M_SALES, "2026-09-20", 138)
    # 순위(최고=숫자 최소): 09.05 kw1=32·kw2=40 → 32, 09.20 kw1=18·kw2=25 → 18  → 32→18 ↑(개선)
    wb.set_keyword_rank("가게P", "상품P", "kw1", "2026-09-05", 32)
    wb.set_keyword_rank("가게P", "상품P", "kw2", "2026-09-05", 40)
    wb.set_keyword_rank("가게P", "상품P", "kw1", "2026-09-20", 18)
    wb.set_keyword_rank("가게P", "상품P", "kw2", "2026-09-20", 25)
    eff, verdict = wb.promo_effect("가게P", "상품P")
    assert eff == "판매 +38% · 순위 32→18 ↑", eff
    assert verdict == "up", verdict
    # 체험단 시작일 없음 → 공란(해당없음)
    wb.ensure_product_block("가게P", "상품Q", config.KIND_CONTRACT, ["kw"])
    wb.set_product_metric("가게P", "상품Q", config.M_SALES, "2026-09-05", 10)
    assert wb.promo_effect("가게P", "상품Q") == ("", ""), "체험단 없으면 공란"
    # 시작 전 데이터 없음 → 공란(after만 있음)
    wb.ensure_product_block("가게P", "상품R", config.KIND_CONTRACT, ["kw"])
    wb.set_marketing("가게P", "상품R", "2026-09-01", "", "")
    wb.set_product_metric("가게P", "상품R", config.M_SALES, "2026-09-20", 50)
    assert wb.promo_effect("가게P", "상품R") == ("", ""), "시작 전 데이터 없으면 공란"
    # 악화(판매↓·순위↓=숫자↑) → verdict down
    wb.ensure_product_block("가게P", "상품S", config.KIND_CONTRACT, ["kw"])
    wb.set_marketing("가게P", "상품S", "2026-09-10", "", "")
    wb.set_product_metric("가게P", "상품S", config.M_SALES, "2026-09-05", 100)
    wb.set_product_metric("가게P", "상품S", config.M_SALES, "2026-09-20", 60)
    wb.set_keyword_rank("가게P", "상품S", "kw", "2026-09-05", 10)
    wb.set_keyword_rank("가게P", "상품S", "kw", "2026-09-20", 40)
    eff_s, verdict_s = wb.promo_effect("가게P", "상품S")
    assert eff_s == "판매 -40% · 순위 10→40 ↓" and verdict_s == "down", (eff_s, verdict_s)
    # '위밖'(미발견)은 정확 순위 아님 → 순위부분 제외(판매만 표기)
    wb.ensure_product_block("가게P", "상품T", config.KIND_CONTRACT, ["kw"])
    wb.set_marketing("가게P", "상품T", "2026-09-10", "", "")
    wb.set_product_metric("가게P", "상품T", config.M_SALES, "2026-09-05", 100)
    wb.set_product_metric("가게P", "상품T", config.M_SALES, "2026-09-20", 110)
    wb.set_keyword_rank("가게P", "상품T", "kw", "2026-09-05", None, scanned=50)   # 50위밖
    wb.set_keyword_rank("가게P", "상품T", "kw", "2026-09-20", None, scanned=50)
    eff_t, _ = wb.promo_effect("가게P", "상품T")
    assert eff_t == "판매 +10%", eff_t
    _ok("체험단효과: +38%·32→18↑=개선 / 데이터부족=공란 / 악화=down / 위밖=순위 제외")


# ── [6] 키워드 Phase B 선정 로직 ───────────────────────────────
# 기본 = **결정적 모킹**(네이버·OpenAI 경계만 페이크, 실제 select_keywords_light 로직 그대로 실행).
#        회귀 게이트가 빠르고(<2s) 결정적이려면 실 API 호출 금지(비용·네트워크·비결정성 제거).
# 실 API 실증이 필요하면 VERIFY_REAL_API=1 로 실행하면 저장된 키로 진짜 호출(옵트인).
class _FakeNaver:
    """NaverAdApi 대역 — related_keywords_multi 만 쓰인다. 모든 힌트를 고검색량으로 되돌려
    후보 하한(≥500/≥30)을 전부 통과시켜 선정 파이프라인 전 구간이 도는지 검증한다."""

    def related_keywords_multi(self, hints):
        from coupang_analytics.kw_volume import KeywordVolume
        out = []
        for h in hints:
            h = str(h).strip()
            if h:
                out.append(KeywordVolume(keyword=h, pc=900, mobile=900, comp_idx="중간",
                                         pc_clicks=10.0, mobile_clicks=20.0, pl_avg_depth=3))
        return out

    def related_keywords(self, hint):
        return self.related_keywords_multi([hint])


def _fake_ask(_client, _model, system, user, *_a, **_kw):
    """kw_ai._ask 대역 — system 프롬프트로 호출 지점을 식별해 유효 JSON을 되돌린다.
    판정/선정은 프롬프트 안의 후보를 되받아(echo) 후보 집합과 항상 일관되게 만든다."""
    import re as _re

    from coupang_analytics import kw_ai
    if system == kw_ai._ANALYZE_SYSTEM:
        return json.dumps({"core": "테스트상품", "use": "테스트 용도",
                           "identities": ["테스트상품", "테스트제품"],
                           "attributes": ["소형"],
                           "anchors": ["테스트상품", "테스트키워드"]}, ensure_ascii=False)
    if system == kw_ai._GEN_SYSTEM:
        return json.dumps({"candidates": ["테스트상품", "테스트키워드", "테스트상품추천"]},
                          ensure_ascii=False)
    if system == kw_ai._JUDGE_SYSTEM:      # user 안 '후보 키워드: [...]' 를 되받아 CORE/RELATED 판정
        m = _re.search(r"후보 키워드:\s*(\[[^\]]*\])", user)
        cands = json.loads(m.group(1)) if m else []
        judged = [{"k": k, "label": ("CORE" if i == 0 else "RELATED"), "match": max(50, 90 - i)}
                  for i, k in enumerate(cands)]
        return json.dumps({"judged": judged}, ensure_ascii=False)
    if system == kw_ai._SELECT_SYSTEM:     # items 의 "keyword" 값을 되받아 우선순위대로 선정
        kws = _re.findall(r'"keyword":\s*"([^"]+)"', user)
        selected = [{"k": k, "role": ("REP" if i == 0 else "SALES"), "priority": i + 1}
                    for i, k in enumerate(kws)]
        return json.dumps({"selected": selected}, ensure_ascii=False)
    return "{}"


def _t2_keywords_mocked():
    print("[6] 키워드 Phase B 선정 로직 (결정적 모킹 — 네이버·OpenAI 경계만 페이크, 실 API 호출 없음)")
    from coupang_analytics import kw_ai
    orig_ask, orig_client = kw_ai._ask, kw_ai._client
    kw_ai._ask = _fake_ask
    kw_ai._client = lambda _key=None: object()   # OpenAI 인스턴스 생성 회피(오프라인)
    try:
        lines: list[str] = []
        picked = select_keywords_light("테스트상품 프리미엄 소형 30개입", _FakeNaver(),
                                       ai_key="__mock__", n=config.KW_MAX_TRACK,
                                       browser=None, measure_ranks=None,
                                       log=lambda m: lines.append(m))
    finally:
        kw_ai._ask, kw_ai._client = orig_ask, orig_client
    assert picked, "선정 결과가 비었음(파이프라인 어딘가에서 후보가 전멸)"
    assert len(picked) <= config.KW_MAX_TRACK, f"선정 개수 초과: {len(picked)} > {config.KW_MAX_TRACK}"
    assert picked[0].role == "REP", f"첫 키워드 역할이 REP가 아님: {picked[0].role}"
    assert all(k.keyword.strip() for k in picked), "빈 키워드 포함"
    _ok(f"선정 로직 완주(후보조립→판정→점수압축→AI종합선정) → {len(picked)}개")
    _ok("최종: " + ", ".join(f"[{k.relevance or '?'}]{k.keyword}({k.role})" for k in picked))


# ── Tier2 (외부 네트워크·AI, 로그인 아님) — VERIFY_REAL_API=1 옵트인 ─────────────
def t2_keywords(store, il):
    if os.environ.get("VERIFY_REAL_API") != "1":
        _t2_keywords_mocked()
        return
    print("[6] 키워드 Phase B 실제 실행 (AI 앵커→네이버확장→AI판정→점수압축→AI종합선정, 브라우저 없이)")
    nj = store.get_password("__naver__")
    if not nj:
        _skip("저장된 네이버 API 키 없음 → 앱 설정 탭에서 키 넣으면 이 항목도 실증됨")
        return
    ak = store.get_password("__openai__")
    if not ak:
        _skip("저장된 OpenAI 키 없음 → AI 앵커/판정 실증 생략(AI 필수 정책)")
        return
    d = json.loads(nj)
    api = NaverAdApi(NaverCredentials(d["customer_id"], d["api_key"], d["secret_key"]))
    title = next((p.name for a in (il.accounts if il else []) for p in a.products), None)
    if not title:
        _skip("입력 상품이 없어 키워드 실증 생략")
        return
    lines: list[str] = []
    try:
        # browser=None → 쿠팡 자동완성/실노출 측정 건너뜀(순수 오프라인: 네이버+OpenAI만). Phase B 선정 경로 그대로 실행.
        picked = select_keywords_light(title, api, ak, n=config.KW_MAX_TRACK,
                                       browser=None, measure_ranks=None,
                                       log=lambda m: lines.append(m))
    except Exception as exc:
        _skip(f"키워드 실행 실패({exc.__class__.__name__}: {str(exc)[:60]})")
        return
    _ok(f"제목 '{title[:40]}'")
    for m in lines:
        _ok(m.strip())
    _ok(f"최종 추적 키워드({len(picked)}): " +
        ", ".join(f"[{k.relevance or '?'}]{k.keyword}(월{k.volume},{k.grade})" for k in picked))


def main():
    print("=" * 60)
    print("  로그인 불필요 부분 실증 (실제 실행 — 가짜 아님)")
    print("=" * 60)
    il = t1_parse_input()
    t1_workbook()
    store = t1_credstore()
    t1_report_parse()
    t1_kind()
    t1_sale_status_flag()
    t1_representative_column()
    t1_delete_account()
    t1_product_match_precision()
    t1_vid_source_option_split()
    t1_ledger_dedup()
    t1_date_columns()
    t1_inventory_missing_error()
    t1_promo_effect()
    t2_keywords(store, il)
    print("=" * 60)
    print("  [완료] 로그인 불필요 부분 실증 종료")
    print("=" * 60)


if __name__ == "__main__":
    main()
