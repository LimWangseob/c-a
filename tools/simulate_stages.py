"""정밀 시뮬레이션(3단계 분리) — 실제 운영 흐름을 처음부터 재현·검증.

앱 시작 → ① 판매수집(run_full keywords_off) → ② 키워드 선정(select_keywords_stage)
→ ③ 노출순위(track_ranks_stage)를, 가짜 브라우저/로그인/네이버/AI로 대체하되 **실제 pipeline
로직**을 그대로 돌려 각 단계 후 워크북 상태를 항목별로 검증한다. 재실행 동결/스킵, ③ 예외격리,
사람이 키워드 미리 입력, 최종 서식까지 커버. simulate_pipeline.py 의 가짜 의존성을 재사용한다.

실행: python tools/simulate_stages.py   (실패 시 exit 1)
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

import simulate_pipeline as S           # noqa: E402
from coupang_analytics import pipeline as P, config  # noqa: E402
from coupang_analytics.workbook import OutputWorkbook  # noqa: E402
from coupang_analytics.kw_volume import NaverAdApi  # noqa: E402

S._install_fakes()
_PASS = {"ok": 0, "fail": 0}


def check(cond, msg):
    print(f"    {'PASS' if cond else 'FAIL'} {msg}")
    _PASS["ok" if cond else "fail"] += 1


def _wb(d):
    return OutputWorkbook.load(Path(d) / "쿠팡데이타분석_통계.xlsx")


def _rows(wb, biz):
    """상품별 (지표{라벨:H값}, 키워드[(kw,검색량F,순위H)]) 요약."""
    ws = wb.wb[biz]
    out, cur = {}, None
    for r in range(1, ws.max_row + 1):
        g, name = ws.cell(r, 7).value, ws.cell(r, 3).value
        if g == "날짜":
            cur = name
            out[cur] = {"metrics": {}, "kw": []}
        elif g in (config.CONTRACT_METRICS + config.PERSONAL_METRICS) and cur:
            out[cur]["metrics"][g] = ws.cell(r, 8).value
        elif g == config.M_RANK and cur:
            out[cur]["kw"].append((name, ws.cell(r, 6).value, ws.cell(r, 8).value))
    return out


def main():
    d = tempfile.mkdtemp()
    naver = NaverAdApi.__new__(NaverAdApi)   # 가짜라 실제로 안 쓰임
    print("=" * 64)
    print("  정밀 시뮬레이션(3단계) — 계정 a1=계약, b1=개인")
    print("=" * 64)

    il = S._accounts(["a1", "b1"])
    print(f"\n[1] 입력 로드 — 계정 {len(il.accounts)}, 상품 {sum(len(a.products) for a in il.accounts)}")

    print("\n[2] ① 판매수집 (로그인, keywords_off) — 상품·상품ID·판매지표·재고만")
    P.run_full(il, naver, out_dir=d, ai_key="sim", date_from="2026-09-07", date_to="2026-09-07",
               keywords_off=True, on_log=lambda m: None)
    wb = _wb(d); a1 = _rows(wb, "비즈-a1"); b1 = _rows(wb, "비즈-b1")
    check("상품-a1" in a1 and "상품-b1" in b1, "두 계정 시트·상품 블록 생성")
    check(a1["상품-a1"]["metrics"].get(config.M_SALES) == 7, "a1 계약 판매량=7")
    check(a1["상품-a1"]["metrics"].get(config.M_INVENTORY) == 42, "a1 재고현황=42")
    check(config.M_SALES in b1["상품-b1"]["metrics"] and config.M_INVENTORY not in b1["상품-b1"]["metrics"],
          "b1 개인 판매량 지표행(재고현황 없음)")
    check(wb.product_vids("비즈-a1", "상품-a1") == ["vid-a1"], "a1 상품ID(vid) 저장")
    check(a1["상품-a1"]["kw"] == [], "① 단계엔 키워드 없음")

    print("\n[3] ② 키워드 선정 (로그인 불필요, 순위 조회 없음)")
    P.select_keywords_stage(naver, "sim", out_dir=d, on_log=lambda m: None)
    wb = _wb(d); a1 = _rows(wb, "비즈-a1")
    check([k for k, _v, _r in a1["상품-a1"]["kw"]] == ["kw1", "kw2"], "a1 키워드 추가")
    check(a1["상품-a1"]["kw"][0][1] == 1000, "kw1 검색량=1000")
    check(all(r in (None, "") for _k, _v, r in a1["상품-a1"]["kw"]), "② 단계엔 순위 아직 공란")

    print("\n[4] ③ 노출순위 조회 (로그인 불필요, 상품ID 매칭)")
    P.track_ranks_stage(out_dir=d, on_log=lambda m: None)
    wb = _wb(d); a1 = _rows(wb, "비즈-a1")
    check([r for _k, _v, r in a1["상품-a1"]["kw"]] == ["3위", "3위"], "a1 키워드 순위 기록")

    print("\n[5] ② 재실행 — 기존 키워드 동결(추가 안 됨)")
    P.select_keywords_stage(naver, "sim", out_dir=d, on_log=lambda m: None)
    a1 = _rows(_wb(d), "비즈-a1")
    check([k for k, _v, _r in a1["상품-a1"]["kw"]] == ["kw1", "kw2"], "재실행해도 키워드 그대로(동결)")

    print("\n[6] ③ 재실행 — 이미 채운 순위 스킵")
    P.track_ranks_stage(out_dir=d, on_log=lambda m: None)
    a1 = _rows(_wb(d), "비즈-a1")
    check([r for _k, _v, r in a1["상품-a1"]["kw"]] == ["3위", "3위"], "순위 유지(재조회 없이 스킵)")

    print("\n[7] ③ 예외격리 — 순위조회가 예외를 던져도 완주·공란(재시도 가능)")
    d2 = tempfile.mkdtemp()
    P.run_full(S._accounts(["a1"]), naver, out_dir=d2, ai_key="sim", date_from="2026-09-07",
               date_to="2026-09-07", keywords_off=True, on_log=lambda m: None)
    P.select_keywords_stage(naver, "sim", out_dir=d2, on_log=lambda m: None)
    _orig = P.organic_ranks_batch, P.organic_ranks
    P.organic_ranks_batch = P.organic_ranks = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("TargetClosedError 모사"))
    res = P.track_ranks_stage(out_dir=d2, on_log=lambda m: None)
    P.organic_ranks_batch, P.organic_ranks = _orig
    a1b = _rows(_wb(d2), "비즈-a1")
    check(res is not None, "예외에도 ③ 완주(결과 반환)")
    check(all(r in (None, "") for _k, _v, r in a1b["상품-a1"]["kw"]),
          "예외 시 순위 공란(‘-’ 아님 → 재시도 가능)")
    check(a1b["상품-a1"]["metrics"].get(config.M_SALES) == 7, "예외에도 판매지표 보존")

    print("\n[8] 사람이 키워드 미리 입력 → ② 가 건너뜀(수동 우선)")
    d3 = tempfile.mkdtemp()
    P.run_full(S._accounts(["a1"]), naver, out_dir=d3, ai_key="sim", date_from="2026-09-07",
               date_to="2026-09-07", keywords_off=True, on_log=lambda m: None)
    wb3 = _wb(d3)
    wb3.add_product_keywords("비즈-a1", "상품-a1", ["수동키워드"])
    wb3.save(Path(d3) / "쿠팡데이타분석_통계.xlsx")
    P.select_keywords_stage(naver, "sim", out_dir=d3, on_log=lambda m: None)
    a1c = _rows(_wb(d3), "비즈-a1")
    check([k for k, _v, _r in a1c["상품-a1"]["kw"]] == ["수동키워드"], "수동 키워드 유지·AI 미실행")

    print("\n[9] 최종 서식 apply_style — 병합·숨김시트")
    wb = _wb(d); wb.apply_style()
    ws = wb.wb["비즈-a1"]
    merges = [str(m) for m in ws.merged_cells.ranges]
    check(any(m.startswith("A1:") for m in merges), "제목 병합(A1:G1)")
    check("_상품ID" in wb.wb.sheetnames and wb.wb["_상품ID"].sheet_state == "hidden", "상품ID 숨김시트 유지")

    print("\n" + "=" * 64)
    print(f"  결과: 통과 {_PASS['ok']} / 실패 {_PASS['fail']}")
    print("=" * 64)
    sys.exit(1 if _PASS["fail"] else 0)


if __name__ == "__main__":
    main()
