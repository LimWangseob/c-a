"""정산 지급 전 예상 규칙값(T-116) 오프라인 검증 — 비즈니스 인사이트 일할 청구(D-325) · 로켓그로스 신상품 무료 창(D-326).

기대값 = D-325·D-326 근거 숫자(윙 화면·매입세금계산서 원 단위 · 코드에서 뽑지 않음). 접속·파일 없음. 실패 시 AssertionError → exit 1.

    python tools/verify_settlement_fee_rules_offline.py
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from coupang_analytics import settlement_fee_rules as FR  # noqa: E402

D = date.fromisoformat


def ok(msg: str) -> None:
    print(f"  OK {msg}")


def t1_bi_supply():
    print("[T1] 비즈니스 인사이트 공급가 = 월정액 × 12 ÷ 365 × 유료 이용일수(시작일~말일) 사사오입(D-325 근거)")
    cases = [(375_000, "2026-11-09", 22, 271_233),     # tellace83 화면 '일할 계산된 금액'
             (99_000, "2025-09-07", 24, 78_115),       # BI_RG 2025-09
             (375_000, "2025-11-03", 28, 345_205),     # BI_RG 2025-11
             (89_000, "2026-10-08", 24, 70_225)]       # nicoable 무료 체험 종료 10-07 다음 날부터 · 세금계산서 공급가액
    for monthly, start, days, want in cases:
        assert FR.bi_paid_days(D(start)) == days, (start, FR.bi_paid_days(D(start)))
        assert FR.bi_supply(monthly, D(start)) == want, (monthly, start, FR.bi_supply(monthly, D(start)))
    assert FR.bi_supply(89_000, D("2026-10-07")) == 73_151                         # 25일이면 73,151 = 화면과 불일치(버린 대안)
    assert FR.bi_supply(375_000, D("2025-12-01")) == 375_000                       # 달 첫날 시작 = 월정액 그대로
    ok("271,233 · 78,115 · 345,205 · 70,225 원 단위 · 첫날 시작 = 월정액")


def t2_bi_charge():
    print("[T2] 청구액(VAT 포함) = 공급가 × 1.1 사사오입(0.5 올림 — 은행가 반올림이면 85,926·379,725·77,247 로 틀림)")
    cases = [(89_000, "2026-10-08", 77_248),           # nicoable 세금계산서 합계 77,248
             (99_000, "2025-09-07", 85_927),           # gyi0101·tellace83 RG 공제 85,927
             (375_000, "2025-11-03", 379_726),         # tellace83 2025-11 379,726
             (89_000, "2026-08-03", 93_341),           # gyi0101 2026-08 505,841 = 412,500 + 93,341(29일)
             (50_000, "2026-10-30", 3_617),            # ski1121 3,617(2일)
             (50_000, "2026-10-09", 41_589),           # ljung0622 41,589(23일)
             (375_000, "2025-12-01", 412_500)]         # 달 첫날 시작·월말 갱신 = 월정액 × 1.1
    for monthly, start, want in cases:
        assert FR.bi_charge(monthly, D(start)) == want, (monthly, start, FR.bi_charge(monthly, D(start)))
    ok("77,248 · 85,927 · 379,726 · 93,341 · 3,617 · 41,589 · 412,500")


def t3_bi_left():
    print("[T3] 회차 예상 = 청구액 − 이미 뺀 조각(지급액 한도까지 나뉨 · nicoable 20,228 + 44,154 → 남은 12,866)")
    assert FR.bi_left(77_248, [20_228, 44_154]) == {"남은 청구": 12_866, "규칙 밖": 0}
    assert FR.bi_left(77_248, [77_248]) == {"남은 청구": 0, "규칙 밖": 0}
    assert FR.bi_left(77_248, [80_000]) == {"남은 청구": 0, "규칙 밖": 2_752}      # 청구보다 더 빠짐 = 규칙 밖(조용히 0 아님)
    ok("남은 12,866 · 다 빠짐 0 · 더 빠짐 = 규칙 밖 2,752")


def t4_bi_table():
    print("[T4] 월정액 표 = 한곳(화면 확인값·유효 기간) — 12-01 신규 요금제 뒤·모르는 플랜 = None(호출부 '확인 필요')")
    assert FR.bi_monthly("프리미엄", D("2026-11-09")) == 375_000
    assert FR.bi_monthly("스탠다드", D("2026-10-08")) == 89_000
    assert FR.bi_monthly("프리미엄", D("2026-12-01")) is None                      # 신규 요금제('프로' 이상) — 표 다시 확인
    assert FR.bi_monthly("베이직", D("2026-10-08")) is None
    assert all(len(v) == 5 and "윙 화면" in v[4] for v in FR.BI_MONTHLY), "표 줄마다 출처"
    ok("프리미엄 375,000 · 스탠다드 89,000 · 12-01 뒤·모르는 플랜 = None · 줄마다 출처")


def t5_newfree_window():
    print("[T5] 신상품 무료 창 = 첫 진열일(첫 입고완료일 + 1) 포함 45일 · k ≤ 43 = 0 · k = 44 = 경계 · k ≥ 45 = 유료(D-326)")
    disp = FR.newfree_display(D("2026-07-01"))
    assert disp == D("2026-07-02")                                                 # 바코드 8옵션: 입고완료 = 진열 − 1
    at = lambda k: disp + timedelta(days=k)  # noqa: E731
    for kind in ("입출고", "배송"):
        assert [FR.newfree_state(disp, at(k), kind) for k in (0, 43, 44, 45, 60)] == \
            [FR.NF_FREE, FR.NF_FREE, FR.NF_EDGE, FR.NF_PAID, FR.NF_PAID], kind
    assert [FR.newfree_state(disp, at(k), "보관31_45") for k in (43, 44, 45)] == [FR.NF_FREE, FR.NF_FREE, FR.NF_PAID]
    aug = D("2026-08-10")                                                          # 8월 공지 '30일' ↔ 실제 45일(327줄 0원)
    assert FR.newfree_state(aug, aug + timedelta(days=35), "배송") == FR.NF_FREE
    for d in ("2026-03-31", "2026-09-01"):                                         # 첫 진열 2026-04-01~08-31 밖 = 대상 아님
        assert FR.newfree_state(D(d), D(d) + timedelta(days=3), "입출고") == FR.NF_OUT, d
    assert FR.newfree_state(D("2026-04-01"), D("2026-04-02"), "입출고") == FR.NF_FREE
    assert FR.newfree_state(D("2026-08-31"), D("2026-09-02"), "입출고") == FR.NF_FREE
    for bad in ((disp, disp - timedelta(days=1), "배송"), (disp, disp, "반출비")):
        try:
            FR.newfree_state(*bad)
        except ValueError:
            continue
        raise AssertionError(f"오류여야 함 {bad}")
    ok("0·43 무료 · 44 경계 · 45 유료 · 보관 44까지 무료 · 8월 시작도 45일 · 범위 밖 = 대상 아님 · 진열 전 발생·모르는 항목 = 오류")


def t6_newfree_expect():
    print("[T6] 예상값 = 쿠팡 줄 값 우선 · 대상 = 그 옵션 첫 정산 줄 0원 · 경계·첫 줄 없음 = 금액 없음(확인 필요)")
    disp = D("2026-07-02")
    at = lambda k: disp + timedelta(days=k)  # noqa: E731
    assert FR.newfree_expect("입출고", disp, at(10), 1_650, first_line=0) == (0, FR.NF_FREE)
    assert FR.newfree_expect("입출고", disp, at(44), 1_650, first_line=0) == (None, FR.NF_EDGE)
    assert FR.newfree_expect("입출고", disp, at(44), 1_650, first_line=0, coupang=1_650) == (1_650, FR.NF_COUPANG)
    assert FR.newfree_expect("배송", disp, at(45), 2_200, first_line=0) == (2_200, FR.NF_PAID)
    assert FR.newfree_expect("배송", disp, at(10), 2_200, first_line=2_200) == (2_200, FR.NF_NOT)    # 첫 줄 유료 = 대상 아님
    assert FR.newfree_expect("배송", disp, at(10), 2_200, first_line=None) == (None, FR.NF_UNKNOWN)  # 첫 정산 줄 아직 없음
    assert FR.newfree_expect("배송", D("2026-09-05"), D("2026-09-10"), 2_200, first_line=0) == (2_200, FR.NF_OUT)
    assert FR.newfree_expect("배송", disp, at(10), 2_200, first_line=0, coupang=0) == (0, FR.NF_COUPANG)
    ok("무료 0 · 경계 None · 쿠팡 값 우선 · 유료 · 첫 줄 유료 = 대상 아님 · 첫 줄 없음 = None · 범위 밖 = 유료값")


def main():
    t1_bi_supply()
    t2_bi_charge()
    t3_bi_left()
    t4_bi_table()
    t5_newfree_window()
    t6_newfree_expect()
    print("정산 지급 전 예상 규칙값(비즈니스 인사이트·신상품 무료) 오프라인 검증 통과")


if __name__ == "__main__":
    main()
