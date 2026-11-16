"""위탁정산서 정산 예정분 관리 몫 나누기 시험(오프라인 · 결정적 · 실 API·네트워크 없음) — T-63 · D-261 · D-262 · D-264 · D-266 · D-267.

기대값 = 결정 규칙에서 손으로 계산한 값(코드에서 뽑지 않음):
  ① 윙 주문별매출 실제값(D-261 ② · D-262 ①) — 정산 파일 기간 밖 구매확정 줄 합(판매 = productGmv + deliveryGmv · 정산 = apAmount)이
     쿠팡 예정과 원 단위 같으면 그 줄의 상품(배송비 줄 = 같은 주문 상품)으로 나눔.
  ② 윙 B8+환산(D-266 ① · D-267) — 판매분석 일별 윙 순액 결제일 [그 달 1일−30일, E−8일 = 기준일−9일] − 이미 구매확정된 판매(앞 달 주문별매출 · 그 주문 밖 정산 파일 줄은
     결제→구매확정 지연 분포로 결제일에) · 옵션 합 뒤 음수 0 · 정산 = 옵션별 정산대상/판매 환산.
     로켓그로스 B+환산 — 예정 판매 주마다 같은 날짜 일별 순액 · 정산 = 판매수수료 정산 파일 옵션별 정산대상/판매 환산 · 달 = 날짜의 달(D-266 ③).
  ③ 관리 비율 0~100% 밖 · 나눌 판매 없음 · 검산(남은 판매 ÷ 쿠팡 판매) 1.5 이상 = 그 금액만 관리 몫에 넣지 않고 '확인 필요'(D-262 ③ · D-266 ②).
  윙 예정분 판매·정산 = 같은 기간(매출내역 · 실측 oopean 11월 판매 어제까지 · 정산 30% 줄 11-08 까지 어긋남) · 음수 예정(환불 구매확정)도 남김.
  재현 근거 = output\\_정산서_261116_안재영\\_scripts\\t63_repro.py(sg0141n 11월 관리 판매 −270,499 · 10월 4,481,505 대 실제 4,537,200).

    python tools/verify_settlement_pending_offline.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coupang_analytics import settlement_files as SF  # noqa: E402
from coupang_analytics import settlement_statement_source as SRC  # noqa: E402
from coupang_analytics.settlement_statement_deduct import Account  # noqa: E402

ACCT, AID, MV = "대표-사업-aid1", "aid1", {"1"}          # 옵션 1 = 관리 · 옵션 2 = 관리 밖


def _near(got, want, tol=0.01) -> bool:
    return abs(got - want) <= tol


def test_wing_unsettled() -> None:
    """윙 예정분 판매·정산 기간을 맞춤 · 음수 예정 남김."""
    pur = {"202611": {"purchaseReports": [{"revenueAmount": 1000, "apAmount": 800}]},
           "202610": {"purchaseReports": [{"revenueAmount": -10600, "apAmount": -9364}]}}
    per = defaultdict(Counter)
    out = SRC._wing_unsettled(ACCT, pur, per, {"2026-11": 300, "2026-10": -9364}, "조회", "2026-11-15")
    got = {x[1]: (x[2], x[3]) for x in out}
    assert got.get("2026-11") == (1000, 800), f"진행 중 달 판매·정산 기간 어긋남(정산 = 30% 줄 기간만): {got}"
    assert got.get("2026-10") == (-10600, -9364), f"음수 예정(환불 구매확정)을 버림: {got}"


def _row(o, vid, gmv, ap, paid, conf, dlv=0, kind="ORDER") -> dict:
    return {"orderId": o, "transactionType": kind, "vendorItemId": vid, "productGmv": gmv, "deliveryGmv": dlv, "apAmount": ap,
            "paidDate": paid, "confirmDate": conf}


def _file(ch: str, s: date, e: date, rows: list) -> SF.SettleFile:
    f = SF.SettleFile(channel=ch, account=ACCT, period_start=s, period_end=e, kind="주정산" if ch == "윙" else "판매수수료")
    f.rows = [SF.SettleRow(ch, ACCT, s, e, str(o), "P" + v, v, "상품", "옵션", 1, sl, 0, 0, st, rec, "판매")
              for o, v, sl, st, rec in rows]
    return f


def _daily() -> dict:
    d: dict = {}

    def put(day, ch, vid, amt):
        d.setdefault(day, {"옵션": {}})["옵션"][vid] = {"구분": ch, "판매금액": amt}
    for x in range(27, 32):
        d[f"2026-10-{x:02d}"] = {"옵션": {}}
    for x in range(1, 15):
        d[f"2026-11-{x:02d}"] = {"옵션": {}}
    for day, vid, amt in (("2026-10-05", "1", 1000), ("2026-10-20", "1", 300), ("2026-10-20", "2", 200), ("2026-10-26", "2", 50),
                          ("2026-10-28", "1", 100), ("2026-11-03", "2", -50), ("2026-11-10", "1", 999)):
        put(day, "윙", vid, amt)
    for day, vid, amt in (("2026-10-27", "1", 300), ("2026-10-30", "2", 200), ("2026-11-01", "1", 400), ("2026-11-02", "2", 100),
                          ("2026-11-04", "1", -50), ("2026-11-05", "2", 150)):
        put(day, "로켓그로스", vid, amt)
    return d


def _stub(base: Path, u: list) -> Account:
    a = Account.__new__(Account)
    periods = {"M:2026-11": {"옵션": {"1": {"구분": "윙", "판매금액": -100}, "2": {"구분": "윙", "판매금액": 300}}},
               "M:2026-10": {"옵션": {"1": {"구분": "윙", "판매금액": 500}, "2": {"구분": "윙", "판매금액": 500}}}}
    a.ctx = SimpleNamespace(base=base, basis="2026-11-15", daily={AID: _daily()}, periods={AID: periods})
    a.acct, a.aid, a.cdate, a.u = ACCT, AID, None, u
    a.t, a.tm, a.settle_all = Counter(settle=1000), Counter(settle=500), 1000.0
    a.mset, a.mmon = defaultdict(lambda: [0.0, 0.0]), defaultdict(lambda: [0.0, 0.0])
    a.files = [_file("윙", date(2026, 11, 2), date(2026, 11, 8), [(9, "2", 50, 45, date(2026, 11, 3))]),
               _file("로켓그로스", date(2026, 10, 13), date(2026, 10, 19), [(7, "1", 1000, 500, date(2026, 10, 15)),
                                                                        (8, "2", 1000, 1000, date(2026, 10, 15))])]
    a.vids, a.vid_name, a.mnames, a.marks, a.opt2pid = set(MV), {}, set(), {}, {}
    return a


def _base(tmp: Path) -> Path:
    d = tmp / "검증자료" / "월자료" / ACCT
    d.mkdir(parents=True)
    rows = [_row(1, 2, 200, 180, "2026-10-20", "2026-10-28"), _row(3, 1, 1000, 800, "2026-10-05", "2026-10-13"),
            _row(3, None, 0, 97, "2026-10-05", "2026-10-13", dlv=100)]
    (d / "주문별매출_202610.json").write_text(json.dumps({"줄": rows}), encoding="utf-8")
    return tmp


def _shares(a: Account) -> dict:
    return {(x[0], x[1]): x for x in a.ushare if not any(c[0] == x[0] and c[1] == x[1] and c[3] == x[3] for c in a.ucheck)}


def test_pending_split() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = _base(Path(td))
        rgw = [("2026-10-27", "2026-11-02", 1000, 700)]
        bad = [("2026-11-03", "2026-11-09", 100, 70)]
        u = [("윙", "2026-11", 400, 320, "쿠팡 계산", "조회", []), ("윙", "2026-10", 1300, 1077, "쿠팡 계산", "조회", []),
             ("로켓그로스", "2026-10", 1000, 700, "쿠팡 계산", "조회", rgw), ("로켓그로스", "2026-11", 100, 70, "쿠팡 계산", "조회", bad)]
        a = _stub(base, u)
        a._unsettled_share()
        sh = _shares(a)
        w11, w10 = sh[("윙", "2026-11")], sh[("윙", "2026-10")]
        assert _near(w11[5], 400) and _near(w11[6], 320), f"E1 윙 11월(B8) 관리 판매·정산 = 400·320 이어야: {w11}"
        assert _near(w10[5], 1100) and _near(w10[6], 897), f"E2 윙 10월(주문별매출 실제값) 관리 = 1,100·897 이어야: {w10}"
        r10, r11 = sh[("로켓그로스", "2026-10")], sh[("로켓그로스", "2026-11")]
        assert _near(r10[2], 500) and _near(r10[5], 300) and _near(r10[6], 150), f"로켓그로스 10월 몫(날짜 달 · 환산) = 판매 500 · 관리 300·150: {r10}"
        assert _near(r11[2], 500) and _near(r11[5], 400) and _near(r11[6], 700 / 3), f"로켓그로스 11월 몫 = 판매 500 · 관리 400·233.33: {r11}"
        assert [(c[0], c[1], c[3]) for c in a.ucheck] == [("로켓그로스", "2026-11", 70)], f"0~100% 밖 주 = 확인 필요 1건: {a.ucheck}"
        assert _near(a.um_settle, 320 + 897 + 150 + 700 / 3), f"확인 필요 금액은 관리 몫에 안 넣음: {a.um_settle}"
        assert _near(a.mset[("로켓그로스", "2026-11")][1], 350), f"확인 필요 금액은 달 비율 분모에도 안 넣음: {a.mset[('로켓그로스', '2026-11')]}"
        a.msales = {("윙", "2026-11"): (0.0, 500.0)}
        a.pur, a.wconf, a.S = {"2026-11": 5000.0}, {"2026-11": [500.0, 0.0, 0.0]}, 0.5
        assert a.svc_month("2026-11") == (400.0, 900.0), f"이용료 덜 온 달 = 정산 파일 + 예정분 관리 판매: {a.svc_month('2026-11')}"
        b = _stub(base, [("윙", "2026-11", 100, 80, "쿠팡 계산", "조회", []), ("윙", "2026-09", -50, -45, "쿠팡 계산", "조회", [])])
        b._unsettled_share()
        why = {c[1]: c[4] for c in b.ucheck}
        assert "검산" in why.get("2026-11", "") and "나눌 판매 없음" in why.get("2026-09", ""), f"검산 1.5 이상·음수 예정 = 확인 필요: {why}"
        assert _near(b.um_sales, 0) and _near(b.um_settle, 0), f"확인 필요 금액 = 관리 몫 0: {b.um_sales} {b.um_settle}"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    test_wing_unsettled()
    test_pending_split()
    print("✅ 정산 예정분 관리 몫 나누기 시험(D-262 ① 실제값 · ② 윙 B8·로켓그로스 B+환산 · ③ 확인 필요 · 기간 맞춤·음수 예정) 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
