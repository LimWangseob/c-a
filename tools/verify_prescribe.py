"""제목처방·진단 로직 실증(네트워크 없음, 실제 실행).

- 전체 노출제목 복원(_display_title): 잘린 상품명 대신 옵션명에서 '테이블' 복원
- keyword_in_title / diagnose_exposure / attack_priority 순수 함수 검증
- 워크북 상품메타(현재/권고 제목·커버리지·태그) + 진단 지표 왕복
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from coupang_analytics import config                                  # noqa: E402
from coupang_analytics.collector import _display_title, _parse_vendor_items  # noqa: E402
from coupang_analytics.kw_recommend import (_grade, _keyword_score,   # noqa: E402
                                            _score_exposure, attack_priority, comp_from_idx,
                                            diagnose_exposure, keyword_in_title, rank_label)
from coupang_analytics.kw_volume import KeywordVolume                 # noqa: E402
from coupang_analytics.report import OptionMetric                     # noqa: E402
from coupang_analytics.workbook import OutputWorkbook                 # noqa: E402

_ok = 0
_fail = 0


def check(cond, msg):
    global _ok, _fail
    if cond:
        _ok += 1
        print(f"    [통과] {msg}")
    else:
        _fail += 1
        print(f"    [실패] {msg}")


def _om(product_name, option_name):
    return OptionMetric(option_id="1", product_name=product_name, option_name=option_name,
                        item_id="1", views=0, sales=0, visitors=0)


print("[1] 전체 노출제목 복원(잘린 상품명 → 옵션명에서 복원)")
opts = [_om("디프 원형 바베큐 그릴 캠핑 화로", "디프 원형 바베큐 그릴 캠핑 화로 테이블, 우드, 48cm"),
        _om("디프 원형 바베큐 그릴 캠핑 화로", "디프 원형 바베큐 그릴 캠핑 화로 테이블, 블랙, 48cm")]
title = _display_title("디프 원형 바베큐 그릴 캠핑 화로", opts)
check(title == "디프 원형 바베큐 그릴 캠핑 화로 테이블", f"복원된 제목='{title}' (테이블 복원)")

print("[1b] 데이터 API 응답 파싱(_parse_vendor_items) — vi-detail-search 실측 스키마 매핑")
_sample = [{"vendorItemDetails": {"vendorItemId": 93006508332, "productName": "안전화상품",
            "itemName": "안전화상품, 250", "itemId": 24960783162},
            "businessInsightsMetricsResponse": {"totalPageViews": 3.0, "totalUnitsSold": 0.0,
            "totalUniqueVisitor": 2.0}},
           {"vendorItemDetails": {"vendorItemId": 0}, "businessInsightsMetricsResponse": {}}]  # 옵션ID 없음→스킵
_mm = _parse_vendor_items(_sample)
check(list(_mm) == ["93006508332"], "옵션ID=vendorItemId(문자열), ID 없는 항목은 스킵")
_o = _mm["93006508332"]
check(_o.views == 3 and _o.sales == 0 and _o.visitors == 2,
      "지표 매핑: 노출=totalPageViews·판매=totalUnitsSold·방문=totalUniqueVisitor")
check(_o.product_name == "안전화상품" and _o.option_name == "안전화상품, 250" and _o.item_id == "24960783162",
      "이름·등록ID 매핑(productName·itemName·itemId)")

print("[2] keyword_in_title (띄어쓰기 무시·구성단어 포함)")
check(keyword_in_title("화로테이블", "디프 원형 화로 테이블 우드"), "'화로테이블' 제목에 포함(공백무시)")
check(not keyword_in_title("캠핑웨건", "디프 원형 화로 테이블"), "'캠핑웨건' 제목에 없음")

print("[3] diagnose_exposure (제목포함 × 순위)")
check(diagnose_exposure(False, None, None) == "노출불가(제목미포함)", "제목없음+스캔밖 → 노출불가(진짜 미노출)")
check(diagnose_exposure(True, None, None) == f"마케팅필요({config.RANK_SCAN_MAX}위 밖)",
      "제목있음+스캔밖 → 마케팅필요(N위 밖, 미노출 아님)")
check(diagnose_exposure(True, 5, 8) == "양호", "제목있음+상위 → 양호")
check(diagnose_exposure(True, 50, None) == "마케팅필요(하위)", "제목있음+하위 → 마케팅필요")
check(diagnose_exposure(False, 30, None).startswith("노출됨(제목미포함"), "제목없는데 노출 → 제목추가권장")
check(rank_label(7) == "7" and rank_label(None) == f"{config.RANK_SCAN_MAX}위 밖",
      "rank_label: 스캔안=순위 · 스캔밖(None)='N위 밖'(미노출 아님)")

print("[4] attack_priority (검색량 ÷ 경쟁강도)")
check(attack_priority(3000, 1.5) == 2000, "3000÷1.5=2000")
check(attack_priority(3000, None) == 3000, "경쟁강도 없으면 검색량")

print("[6] Keyword Score (관련성·구매의도·검색량·쿠팡노출 종합 + 등급)")
check(comp_from_idx("높음") == 3.0 and comp_from_idx("낮음") == 1.0 and comp_from_idx("") is None,
      "comp_from_idx: 높음=3·낮음=1·미상=None")
check(_score_exposure(1) == config.KW_SCORE_W_EXPOSURE, "노출점수: 1위 → 만점(15)")
check(_score_exposure(None) == 0.0 and _score_exposure(config.RANK_SCAN_MAX + 1) == 0.0,
      "노출점수: 미노출·스캔밖 → 0")
check(_score_exposure(2) > _score_exposure(15) > _score_exposure(40) > 0,
      "노출점수: 순위 좋을수록 높음(단조)")


def _kv(keyword, total, clicks, comp="중간"):
    return KeywordVolume(keyword=keyword, pc=total // 2, mobile=total - total // 2,
                         comp_idx=comp, pc_clicks=clicks / 2, mobile_clicks=clicks - clicks / 2)


core_kv = _kv("화로테이블", 3000, 120)
core_exposed = _keyword_score(core_kv, "핵심", 2)
core_hidden = _keyword_score(core_kv, "핵심", None)
rel_exposed = _keyword_score(_kv("캠핑용테이블", 3000, 120), "연관", 2)
check(core_exposed > core_hidden, "같은 키워드: 쿠팡 노출되면 점수↑ (실노출 승격)")
check(core_exposed > rel_exposed, "같은 조건: 핵심 > 연관 (관련성 반영)")
check(_grade(core_exposed) in ("A", "B") and _grade(_keyword_score(_kv("불멍", 40, 1), "연관", None)) == "D",
      f"등급: 핵심+노출={_grade(core_exposed)}(A/B) · 약한연관 미노출=D")

print("[5] 셀독 새 서식 워크북 왕복(시트=사업자, 계약/개인 블록, 키워드 순위·검색량, 재로드)")
wb = OutputWorkbook.empty()
wb.ensure_product_block("안재영", "신형 타프 R008", config.KIND_CONTRACT, ["타프", "방수타프"])
wb.ensure_product_block("안재영", "무지외반증", config.KIND_PERSONAL, ["무지외반증 교정기"])
wb.set_product_metric("안재영", "신형 타프 R008", config.M_SALES, "26.09.07", 5)
wb.set_product_metric("안재영", "신형 타프 R008", config.M_INVENTORY, "26.09.07", 15)
wb.set_product_metric("안재영", "무지외반증", config.M_TOTAL_SALES, "26.09.07", 3)
wb.set_keyword_search("안재영", "신형 타프 R008", "타프", 35290)
wb.set_keyword_rank("안재영", "신형 타프 R008", "타프", "26.09.07", 22)
wb.set_keyword_rank("안재영", "신형 타프 R008", "방수타프", "26.09.07", None)   # 스캔밖 → '-'
out = Path("output/_verify_prescribe.xlsx")
out.parent.mkdir(exist_ok=True)
wb.save(out)
w2 = OutputWorkbook.load(out)
check(set(w2.wb.sheetnames) == {"안재영"}, "시트=사업자명")
check(w2.product_keywords("안재영", "신형 타프 R008") == ["타프", "방수타프"], "상품 키워드 동결 읽기")
ws = w2.wb["안재영"]
c7 = w2._date_col["안재영"]["26.09.07"]
rr = w2._metric_row[("안재영", "신형 타프 R008", config.M_INVENTORY)]
check(ws.cell(rr, c7).value == 15, "재고현황(판매가능 수량) 왕복")
kr = w2._kw_row[("안재영", "신형 타프 R008", "타프")]
check(ws.cell(kr, 6).value == 35290 and ws.cell(kr, c7).value == "22위", "키워드 검색량·순위(22위) 왕복")
kr2 = w2._kw_row[("안재영", "신형 타프 R008", "방수타프")]
check(ws.cell(kr2, c7).value == "-", "스캔밖 순위 '-' 왕복")
check(("안재영", "무지외반증", config.M_TOTAL_SALES) in w2._metric_row, "개인 상품: 전체 판매량 지표행")
out.unlink()

print("=" * 50)
print(f"  결과: 통과 {_ok} · 실패 {_fail}")
sys.exit(1 if _fail else 0)
