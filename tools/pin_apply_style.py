"""핀 테스트 — OutputWorkbook.apply_style 의 **서식 출력**을 고정(분해 전 회귀 방어).

배경: verify_offline/simulate 는 apply_style 을 호출하지만 **값(순위·노출·키워드)만** assert 하고
서식(색·병합·틀고정·판매중지 적색·마케팅 배경·그룹 굵은선/얇은선·꼬리행 정리)은 하나도 검증하지
않는다 → apply_style(F52)을 분해하면 서식이 틀어져도 게이트가 초록으로 통과(회귀 못 잡음). 이 파일이
그 서식 불변식을 골든값으로 고정한다. 분해 전/후로 초록이면 **서식 행동 불변** 보증.

실행: python tools/pin_apply_style.py   (로그인·API 없음·결정적, openpyxl 만)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics import config  # noqa: E402
from coupang_analytics.workbook import OutputWorkbook  # noqa: E402

BIZ = "비즈S"


def _check(cond: bool, msg: str) -> None:
    print(f"    {'[통과]' if cond else '[실패]'} {msg}")
    if not cond:
        raise AssertionError(msg)


def _n(v) -> str:
    return str(v).strip() if v is not None else ""


def _base(v) -> str:
    """헤더 C셀의 표시명에서 순수 상품명(vid 꼬리 앞부분)만."""
    return _n(v).split(config.NAME_ID_SEP, 1)[0]


def _hdr_row(ws, base: str) -> int:
    """그 상품 블록의 헤더행(G='날짜'이고 C의 순수명이 base)."""
    for r in range(1, ws.max_row + 1):
        if _n(ws.cell(r, 7).value) == "날짜" and _base(ws.cell(r, 3).value) == base:
            return r
    raise AssertionError(f"헤더행 못 찾음: {base}")


def _kw_head_row(ws, hr: int) -> int | None:
    """hr 아래 첫 키워드 소헤더행(A='키워드'·v4 좌측확장). 없으면 None(2차 옵션 블록)."""
    for r in range(hr, ws.max_row + 1):
        if _n(ws.cell(r, 1).value) == "키워드":
            return r
    return None


def _fill(ws, r, c) -> str:
    fg = ws.cell(r, c).fill.fgColor
    return _n(getattr(fg, "rgb", "")) or ""


def _build() -> OutputWorkbook:
    """서식 전 경로를 밟는 픽스처 — 단일옵션·다중옵션(그룹)·판매중지(불일치)·마케팅 상품."""
    wb = OutputWorkbook.empty()
    wb.ensure_account(BIZ)
    # ① 단일옵션 로켓그로스(지표+키워드 블록)
    wb.ensure_product_block(BIZ, "상품S", config.KIND_CONTRACT, ["kw1", "kw2"], registered="상품S")
    wb.set_product_vids(BIZ, "상품S", ["vidS"])
    # ② 다중옵션(같은 등록명 '타프') — 대표+2차 → 그룹 경계(굵은선 바깥/얇은선 사이) 검증용
    wb.ensure_product_block(BIZ, "타프 (베이지)", config.KIND_CONTRACT, ["kwA"], registered="타프")
    wb.set_product_vids(BIZ, "타프 (베이지)", ["vidB"])
    wb.ensure_product_block(BIZ, "타프 (그레이)", config.KIND_CONTRACT, [], rank_rows=False, registered="타프")
    wb.set_product_vids(BIZ, "타프 (그레이)", ["vidG"])
    # ③ 판매중지(대장에서 빠짐)인데 쿠팡=판매중 → 불일치 적색 경고 검증용
    wb.ensure_product_block(BIZ, "중지상품", config.KIND_PERSONAL, ["kwD"], registered="중지상품")
    wb.set_product_vids(BIZ, "중지상품", ["vidD"])
    wb.set_discontinued(BIZ, "중지상품", True)
    wb.apply_sale_status(BIZ, {"vidD": "판매중"})
    # ④ 마케팅(체험단) 기간 상품 → 일자 컬럼 배경(연주황) + 소헤더 '🔴 체험단중' 검증용
    wb.ensure_product_block(BIZ, "체험상품", config.KIND_PERSONAL, ["kwM"], registered="체험상품")
    wb.set_product_vids(BIZ, "체험상품", ["vidM"])
    wb.set_marketing(BIZ, "체험상품", "2026-09-19", "2026-09-25", "2026-09-30")
    wb.ensure_date(BIZ, "2026-09-20")
    wb.set_product_metric(BIZ, "상품S", config.M_SALES, "2026-09-20", 7)
    return wb


def pin_title_and_frame():
    print("[핀 S1] 제목행·틀고정·열너비·목차 복귀 링크")
    wb = _build()
    wb.apply_style()
    ws = wb.wb[BIZ]
    _check(ws.freeze_panes == "H2", "틀고정 H2(A~G·1행 고정)")
    _check(ws.cell(1, 1).font.size == 14 and ws.cell(1, 1).font.bold, "제목 폰트 14pt 굵게")
    merged = {str(m) for m in ws.merged_cells.ranges}
    _check("A1:E1" in merged, "제목 A1:E1 병합")
    _check("F1:G1" in merged, "목차 복귀 링크 F1:G1 병합")
    # 레이아웃 v4: 좌측 라벨 칸 A:B 합(7+7=14) = 우측 지표 라벨 칸 G(14)·값 칸 C:F 재배분
    _check(ws.column_dimensions["A"].width == 7 and ws.column_dimensions["B"].width == 7,
           "좌측 라벨 칸 A7·B7(합 14)")
    _check(ws.column_dimensions["G"].width == 14, "지표 라벨 칸 G14 = 좌측 라벨 칸 합")
    _check(ws.column_dimensions["C"].width == 18, "C열(값 칸) 너비 18")


def pin_block_fills():
    print("[핀 S2] 레이아웃 v4 헤더 — A:B 라벨 칸(상품군색)·C:F 값 칸(흰)·G 지표 라벨(연파랑)")
    wb = _build()
    wb.apply_style()
    ws = wb.wb[BIZ]
    hr = _hdr_row(ws, "상품S")   # KIND_CONTRACT → 7줄(상품명2·VID·판매방식·로켓그로스3)
    kh = _kw_head_row(ws, hr)
    # 좌측 A:B = 라벨 칸(상품군색), C:F = 값 칸. **상품명 칸(pos0 C:F)=상품군색**(강조), 나머지 값 칸=흰
    _check(_fill(ws, hr, 1).endswith(OutputWorkbook._FILL_PROD), "좌측 라벨 칸 A열 살구색(FBE2D5)")
    _check(_fill(ws, hr, 3).endswith(OutputWorkbook._FILL_PROD), "상품명 값 칸 C열 상품군색(FBE2D5)")
    _check(_fill(ws, hr + 2, 3).endswith(OutputWorkbook._FILL_KIND), "VID 값 칸 C열 흰색(FFFFFF)")
    _check(_fill(ws, hr + 1, 7).endswith(OutputWorkbook._FILL_LABEL), "지표 라벨 G열 연파랑(D9E9FA)")
    # 라벨/값 텍스트(pos0 상품명·pos2 VID·pos3 판매방식·pos4 로켓그로스)
    _check(_n(ws.cell(hr, 1).value) == "상품명", "pos0 라벨 A='상품명'")
    _check(_base(ws.cell(hr, 3).value) == "상품S", "pos0 값 C=상품명(블록 KEY)")
    _check(_n(ws.cell(hr + 2, 1).value) == "VID", "pos2 라벨 A='VID'")
    _check(_n(ws.cell(hr + 2, 3).value) == "vidS", "pos2 값 C=vid 목록")
    _check(_n(ws.cell(hr + 3, 1).value) == "판매방식", "pos3 라벨 A='판매방식'")
    _check(_n(ws.cell(hr + 3, 3).value) == config.KIND_CONTRACT, "pos3 값 C=판매방식(로켓그로스)")
    _check(_n(ws.cell(hr + 4, 1).value) == "로켓그로스", "pos4 라벨 A='로켓그로스'(3줄 세로병합 앵커)")
    # A:B 라벨 세로병합(상품명 2줄·로켓그로스 3줄)
    merged = {str(m) for m in ws.merged_cells.ranges}
    _check(f"A{hr}:B{hr + 1}" in merged, "상품명 라벨 A:B 2줄 세로병합")
    _check(f"A{hr + 4}:B{hr + 6}" in merged, "로켓그로스 라벨 A:B 3줄 세로병합")
    _check(f"C{hr}:F{hr + 1}" in merged, "상품명 값 C:F 2줄 세로병합")
    # 키워드 구역(v4 좌측확장): 소헤더 A='키워드'·A~E 가로병합·회색(사업자명 A:B 폐지)
    _check(kh is not None and _n(ws.cell(kh, 1).value) == "키워드", "키워드 소헤더 A='키워드'(좌측확장)")
    _check(_fill(ws, kh, 1).endswith(OutputWorkbook._FILL_KWHEAD), "키워드 소헤더 회색(E8E8E8·앵커=A)")
    _check(f"A{kh}:E{kh}" in merged, "키워드 소헤더 A~E 가로병합(좌측확장)")
    _check(_n(ws.cell(kh + 1, 1).value) == "kw1", "키워드명=A열(v4)")
    _check(f"A{kh + 1}:E{kh + 1}" in merged, "키워드 순위행 A~E 가로병합")
    _check(_n(ws.cell(kh, 7).value) == "비고", "정상 상품 소헤더 G='비고'")


def pin_sale_status_mismatch():
    print("[핀 S3] 판매중지(대장)↔판매중(쿠팡) 불일치 → 최신칸 '판매중' 적색")
    wb = _build()
    wb.apply_style()
    ws = wb.wb[BIZ]
    hr = _hdr_row(ws, "중지상품")
    kh = _kw_head_row(ws, hr)
    _check(_n(ws.cell(kh, 7).value) == "⛔ 판매중지", "판매중지 상품 소헤더 G='⛔ 판매중지'")
    # 최신(맨 오른쪽) 일자 컬럼 = 가장 큰 날짜 열번호
    cols = wb._date_col.get(BIZ, {})
    last_col = max(cols.values())
    wc = ws.cell(kh, last_col)
    _check(_n(wc.value) == "판매중", "불일치 경고 '판매중' 기록")
    _check(_n(getattr(wc.font.color, "rgb", "")).endswith("C00000"), "'판매중' 진한 적색(C00000)")
    # 누적 방지(2026-09-25): 과거 실행이 남긴 '판매중'은 최신 칸만 남기고 청소돼야(여러 칸 번짐 방지)
    wb.ensure_date(BIZ, "2026-09-19")            # 더 과거 날짜 추가(최신=09-20 유지)
    cols2 = wb._date_col.get(BIZ, {})
    old_col = cols2["2026-09-19"]
    ws.cell(kh, old_col, "판매중")                # 과거 칸에 옛 '판매중' 심기(누적 재현)
    wb.apply_style()
    cols3 = wb._date_col.get(BIZ, {})
    latest = cols3[max(cols3, key=lambda d: d)]   # 문자열 최대(2026-09-20 > 09-19)
    n_pandae = sum(1 for c in cols3.values() if _n(ws.cell(kh, c).value) == "판매중")
    _check(n_pandae == 1, f"'판매중'은 최신 칸 1개만(누적 청소) — 실제 {n_pandae}칸")
    _check(_n(ws.cell(kh, latest).value) == "판매중", "'판매중'이 최신 칸에 남음")


def pin_marketing_fill():
    print("[핀 S4] 마케팅 기간 일자 컬럼 배경(연주황) + 소헤더 '🔴 체험단중'")
    wb = _build()
    wb.apply_style()
    ws = wb.wb[BIZ]
    hr = _hdr_row(ws, "체험상품")
    kh = _kw_head_row(ws, hr)
    cols = wb._date_col.get(BIZ, {})
    last_col = max(cols.values())
    _check(_fill(ws, hr + 1, last_col).endswith(OutputWorkbook._FILL_MKT),
           "마케팅 기간 일자 컬럼 배경 연주황(FCE4D6)")
    _check(_n(ws.cell(kh, 7).value) == "🔴 체험단중", "마케팅 상품 소헤더 G='🔴 체험단중'")


def pin_group_edges():
    print("[핀 S5] 같은 등록명 변형(옵션) 그룹 — 바깥=굵은선·사이=얇은선(fix ④)")
    wb = _build()
    wb.apply_style()
    ws = wb.wb[BIZ]
    beige = _hdr_row(ws, "타프 (베이지)")   # 그룹 시작(직전=상품S, 다른 등록명) → 상단 굵은선
    gray = _hdr_row(ws, "타프 (그레이)")    # 같은 그룹(직전=베이지) → 상단 얇은선
    _check(ws.cell(beige, 1).border.top.style == "thick", "그룹 시작 블록 상단=굵은선")
    _check(ws.cell(gray, 1).border.top.style == "medium", "그룹 내부(기본↔옵션) 구분선=medium(진하게)")


def pin_trailing_trim():
    print("[핀 S6] 꼬리 공백행 정리(멱등) — max_row=실제 마지막 데이터행")
    wb = _build()
    wb.apply_style()
    wb.apply_style()   # 두 번 돌려도(멱등) 공백행이 누적되지 않아야 함
    ws = wb.wb[BIZ]
    last_data = max((r for r in range(1, ws.max_row + 1)
                     if any(_n(ws.cell(r, c).value) for c in range(1, ws.max_column + 1))),
                    default=1)
    _check(ws.max_row == last_data, f"꼬리 공백행 없음(max_row={ws.max_row}=데이터끝)")


def pin_sale_status_accurate():
    print("[핀 S7] 판매상태 정확 표기 — 임시저장·승인반려를 판매중지로 안 뭉갬")
    from coupang_analytics.collector import sale_status_of
    # collector 원문 enum → 해석
    _check(sale_status_of("ON_SALE") == "판매중", "ON_SALE→판매중")
    _check(sale_status_of("PARTIAL_ON_SALE") == "부분판매중", "PARTIAL_ON_SALE→부분판매중")
    _check(sale_status_of("SUSPENDED") == "판매중지", "SUSPENDED→판매중지")
    _check(sale_status_of("DRAFT") == "임시저장", "DRAFT→임시저장")
    _check(sale_status_of("REJECTED") == "승인반려", "REJECTED→승인반려")
    _check(sale_status_of("") == "", "빈값→미상('')")
    # apply_sale_status 는 단일 상태를 그대로 보존(임시저장이 부분판매중으로 안 바뀜)
    wb = OutputWorkbook.empty()
    wb.ensure_account(BIZ)
    wb.ensure_product_block(BIZ, "임시상품", config.KIND_PERSONAL, ["kw"], registered="임시상품")
    wb.set_product_vids(BIZ, "임시상품", ["vidT"])
    wb.apply_sale_status(BIZ, {"vidT": "임시저장"})
    _check(wb.sale_status(BIZ, "임시상품") == "임시저장", "apply_sale_status: 임시저장 보존(부분판매중 아님)")
    # 계정목록 status_of = 대장 상태만(소유자 2026-09-24 결정). productStatus(임시저장 등)는
    # 계정목록이 아니라 상품블록 '판매상태' 지표행(sale_status)에만 표기 → status_of 는 productStatus 미반영.
    _check(wb.status_of(BIZ, "임시상품") != "임시저장", "status_of(계정목록)=대장상태만(productStatus 미표기)")
    _check(wb.rank_suppressed(BIZ, "임시상품"), "임시저장 → 순위 제외(rank_suppressed)")


def pin_group_fill_alternation():
    print("[핀 S8] 상품군 배경색 교대 — 같은 등록명(옵션)=같은 색·인접 상품군=다른 색")
    wb = _build()
    wb.apply_style()
    ws = wb.wb[BIZ]
    c_s = _fill(ws, _hdr_row(ws, "상품S"), 1)          # 군0
    c_beige = _fill(ws, _hdr_row(ws, "타프 (베이지)"), 1)   # 군1
    c_gray = _fill(ws, _hdr_row(ws, "타프 (그레이)"), 1)    # 군1(같은 등록명)
    c_disc = _fill(ws, _hdr_row(ws, "중지상품"), 1)      # 군2
    _check(c_s.endswith(OutputWorkbook._FILL_PROD), "상품S(군0) 살구 FBE2D5")
    _check(c_beige.endswith(OutputWorkbook._FILL_PROD2), "타프(군1) 민트 E2EFDA — 인접 군과 다른 색")
    _check(c_beige == c_gray, "같은 등록명 옵션(베이지·그레이) = 같은 배경색(한 상품군)")
    _check(c_disc.endswith(OutputWorkbook._FILL_PROD), "중지상품(군2) 다시 살구 — 직전(타프)과 다른 색")
    _check(c_s != c_beige, "인접 상품군은 배경색이 다름(시각적 구분)")


def main() -> int:
    print("=" * 60)
    print("  핀 테스트 — OutputWorkbook.apply_style 서식 출력")
    print("=" * 60)
    pin_sale_status_accurate()
    pin_title_and_frame()
    pin_block_fills()
    pin_sale_status_mismatch()
    pin_marketing_fill()
    pin_group_edges()
    pin_group_fill_alternation()
    pin_trailing_trim()
    print("=" * 60)
    print("  [완료] 서식 핀 모두 통과")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
