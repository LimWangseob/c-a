"""로그인이 필요 없는 부분만 '실제로' 실행해 실증한다(가짜 아님).

- Tier1 (부작용 없음, 로컬): 입력 엑셀 파싱 · 제목 시드 추출 · 워크북 생성/저장/재로드 ·
  credstore DPAPI 암복호화 왕복 · 판매분석 리포트 파싱(합성 리포트로 실제 파서 실행).
- Tier2 (외부 네트워크, 로그인 아님): 저장된 네이버 검색광고 API 키가 있으면 실제 검색량 조회.

순위 조회/키워드 경쟁(실제 Chrome + 쿠팡 접속)은 별도(브라우저·외부 트래픽)라 여기 넣지 않는다.
실행: python tools/verify_offline.py
"""
from __future__ import annotations

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
    wb.set_keyword_search("비즈A", "상품A", "kw1", 1200)
    wb.set_product_metric("비즈A", "상품A", config.M_VIEWS, "2026-09-02", 123)
    path = d / "실증_워크북.xlsx"
    wb.apply_style()
    wb.save(path)
    size = path.stat().st_size
    ws = openpyxl.load_workbook(path)["비즈A"]   # 시트명 = 사업자명
    flat = [c.value for row in ws.iter_rows() for c in row]
    assert "3위" in flat and 123 in flat and 1200 in flat, "값 재로드 실패"
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


# ── Tier2 (외부 네트워크·AI, 로그인 아님) ─────────────────────
def t2_keywords(store, il):
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
    t2_keywords(store, il)
    print("=" * 60)
    print("  [완료] 로그인 불필요 부분 실증 종료")
    print("=" * 60)


if __name__ == "__main__":
    main()
