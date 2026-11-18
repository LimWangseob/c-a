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


def t7_bi_expect():
    print("[T7] 74 남은 청구 예상(T-121) = 그 달 청구(D-325) − 이미 뺀 조각 · 플랜·유료 시작일 없으면 금액 없음 + '입력 없음 → 예상값 미확정'")
    amt, note = FR.bi_expect("2026-10", [20_228])
    assert amt is None and FR.NO_INPUT in note and "SV-BI-SUB" in note, (amt, note)
    assert FR.bi_expect("2026-10", [20_228, 44_154], "스탠다드", D("2026-10-08"))[0] == 12_866      # nicoable 77,248 − 64,382
    assert FR.bi_expect("2026-11", [], "프리미엄", D("2026-11-09"))[0] == 298_356                    # 271,233(화면) × 1.1 사사오입
    assert FR.bi_expect("2026-11", [100_000], "프리미엄", D("2025-11-03"))[0] == 312_500             # 앞 달 시작 = 그 달 1일부터 월정액 412,500
    assert FR.bi_expect("2026-09", [], "스탠다드", D("2026-10-08")) == (0, "유료 시작 전(2026-10-08) — 청구 없음")
    amt, note = FR.bi_expect("2026-12", [], "프리미엄", D("2025-11-03"))                            # 12-01 신규 요금제 = 표 없음
    assert amt is None and "확인 필요" in note, note
    amt, note = FR.bi_expect("2026-10", [80_000], "스탠다드", D("2026-10-08"))                     # 청구보다 더 빠짐 = 규칙 밖
    assert amt is None and "확인 필요" in note and "2,752" in note, note
    ok("입력 없음 = None+비고 · 남은 12,866 · 298,356 · 앞 달 시작 312,500 · 시작 전 0 · 표 없음·더 빠짐 = 확인 필요")


def t8_saver():
    print("[T8] 45·76 세이버 무료 체험 = 계정 시작 창 끝 다음 날부터 270일(D-332 ① · 윙 홈 띠 6/6) · 끝날 입력 없으면 미확정")
    cases = [("2026-05-01", "2027-01-27"),     # sg0141n 창 05-01 → 화면 2027-01-27
             ("2026-05-20", "2027-02-15"),     # oopean 창 05-18~20 → 2027-02-15
             ("2026-06-03", "2027-03-01"),     # 91white 시작 06-04 → 2027-03-01
             ("2026-08-12", "2027-05-10"),     # mrc098 시작 08-13 → 2027-05-10
             ("2026-08-06", "2027-05-04")]     # nicoable 시작 08-07 → 2027-05-04
    for wend, want in cases:
        s, e = FR.saver_trial(D(wend))
        assert s == D(wend) + timedelta(days=1) and e == D(want), (wend, s, e)
    assert FR.saver_expect(D("2026-05-01"), D("2027-01-27"))[0] is True                           # 끝날 당일 = 체험 안(31~60일 보관 무료)
    assert FR.saver_expect(D("2026-05-01"), D("2027-01-28"))[0] is False                          # 다음 날 = 유료(구독료 D-298)
    assert FR.saver_expect(D("2026-05-01"), D("2026-05-01"))[0] is False                          # 시작 창 날 = 체험 전(시작 창 보관 B=A 따로)
    amt, note = FR.saver_expect(None, D("2026-11-10"))
    assert amt is None and FR.NO_INPUT in note and "S6" in note, note
    ok("270일 끝날 5계정 원 화면값 · 끝날 당일 무료·다음 날 유료·시작 창 날 체험 전 · 입력 없음 = 미확정")


def t9_return():
    print("[T9] 4 반품배송비 예상(D-333) = 판매자접수 → 편도 · 주문자·쿠팡CS → R1 · 접수채널 없으면 R1 + '판매자 접수면 편도일 수 있음'")
    assert FR.return_expect(7_000, 3_000, "판매자접수") == (3_000, "판매자접수 = 편도(등록 반품배송비 1회 · D-333 ②)")
    assert FR.return_expect(7_000, 3_000, "주문자접수")[0] == 7_000
    assert FR.return_expect(7_000, 3_000, "쿠팡CS")[0] == 7_000
    amt, note = FR.return_expect(7_000, 3_000, None)
    assert amt == 7_000 and "판매자 접수면 편도일 수 있음" in note and FR.NO_INPUT in note and "T-118" in note, note
    amt, note = FR.return_expect(None, None, None)                                                # R1 도 모름 = 금액 없음
    assert amt is None and "판매자 접수면 편도일 수 있음" in note, note
    amt, note = FR.return_expect(7_000, 3_000, "택배사접수")                                         # 모르는 채널 = 확인 필요(조용히 R1 아님)
    assert amt is None and "확인 필요" in note, note
    ok("편도 3,000 · R1 7,000 · 채널 없음 = R1 + 표시 · R1 없음 = None · 모르는 채널 = 확인 필요")


def t10_discount():
    print("[T10] 신규-03 할인표 칸(D-331 ①) = 화면 표 먼저 · 화면과 원문이 다른 칸 = 원문 값 · 화면 표 없으면 미확정(S4)")
    assert FR.discount_cell(600, 650) == (650, "원문 값(화면 600 ≠ 원문 · D-331 ①)")             # 휴대폰/액세서리 극소형 입출고
    assert FR.discount_cell(800, None) == (800, "화면 표(D-331 ①)")
    assert FR.discount_cell(800, 800) == (800, "화면 표(D-331 ①)")
    amt, note = FR.discount_cell(None, 650)
    assert amt is None and FR.NO_INPUT in note and "S4" in note, note
    ok("원문 650 우선 · 화면 800 · 화면 없음 = 미확정")


def main():
    t1_bi_supply()
    t2_bi_charge()
    t3_bi_left()
    t4_bi_table()
    t5_newfree_window()
    t6_newfree_expect()
    t7_bi_expect()
    t8_saver()
    t9_return()
    t10_discount()
    print("정산 지급 전 예상 규칙값(비즈니스 인사이트·신상품 무료·세이버·반품·할인표) 오프라인 검증 통과")


if __name__ == "__main__":
    main()
