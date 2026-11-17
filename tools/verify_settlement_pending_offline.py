"""위탁정산서 정산 예정분 관리 몫 나누기 시험(오프라인 · 결정적 · 실 API·네트워크 없음) — T-63 · T-73 · D-262 · D-266 · D-267 · D-269 · D-279 · D-281.

기대값 = 결정 규칙에서 손으로 계산한 금액(원 · 코드에서 뽑지 않음 · 판정 = 금액 일치 D-281):
  ① 윙 주문별매출 실제값(D-262 ①) — 정산 파일 기간 밖 구매확정 줄 합(판매 = productGmv + deliveryGmv · 정산 = apAmount)이
     쿠팡 예정과 원 단위 같으면 그 줄의 상품(배송비 줄 = 같은 주문 상품)으로 나눔.
  ② 윙 B8+환산(D-266 ① · D-267) — 판매분석 일별 윙 순액 결제일 [그 달 1일−30일, E−8일 = 기준일−9일] − 이미 구매확정된 판매 · 옵션 합 뒤 음수 0.
  ③ 윙 B8 이 '확인 필요' 조건이면 빼지 않고 ⓒ2 = 저장해 둔 결제→구매확정 지연 분포 + 윙 정산 파일 환산(이미 확정 주문 빼기 없음)으로 채움(D-269 ①) ·
     지연 분포는 계산할 때마다 저장(검증자료/결제확정_지연분포.json). ⓒ2 도 안 되면 그 금액만 '확인 필요'.
  ④ 로켓그로스 = 그 달 판매분석 판매 비율(D-269 ② · T-63 이전 방식 · 기준일 뒤 주도 같음) · 주가 달을 걸치면 날짜의 달로 나눔(D-266 ③) ·
     그 달 판매분석 판매 없음·0~100% 밖 = 그 금액만 '확인 필요'.
  ⑤ 쿠팡 예정 줄 금액은 그대로(D-279 ①) — 나눈 조각의 판매·정산 합 = 쿠팡 예정 줄 금액(원 단위).
  윙 예정분 판매·정산 = 같은 기간(매출내역) · 음수 예정(환불 구매확정)도 남김.
  재현 근거 = output\\_검증_261117_정산끝난달\\판정_보고.md 6절(scripts\\b2_wing.py C2 · b5_fill.py).

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

ACCT, AID, MV = "대표-사업-aid1", "aid1", {"1", "3"}     # 옵션 1·3 = 관리 · 옵션 2·4 = 관리 밖(3·4 = 로켓그로스 판매분석 기간)


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
    rg = {"구분": "로켓그로스"}
    periods = {"M:2026-11": {"옵션": {"1": {"구분": "윙", "판매금액": -100}, "2": {"구분": "윙", "판매금액": 300},
                                    "3": {**rg, "판매금액": 100}, "4": {**rg, "판매금액": 300}}},
               "M:2026-10": {"옵션": {"1": {"구분": "윙", "판매금액": 500}, "2": {"구분": "윙", "판매금액": 500},
                                    "3": {**rg, "판매금액": 600}, "4": {**rg, "판매금액": 400}}}}
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


def _sum(a: Account) -> dict:
    """(판매 방식, 달) → [판매, 정산대상, 관리 판매, 관리 정산] — '확인 필요' 조각 뺌."""
    out: dict = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    chk = Counter((c[0], c[1], c[3]) for c in a.ucheck)
    for ch, ym, s_, e_, _r, ms, me, _how in a.ushare:
        if chk[(ch, ym, e_)]:
            chk[(ch, ym, e_)] -= 1
            continue
        g = out[(ch, ym)]
        g[0], g[1], g[2], g[3] = g[0] + s_, g[1] + e_, g[2] + ms, g[3] + me
    return out


def _all(a: Account) -> dict:
    """(판매 방식, 달) → [판매, 정산대상] — 확인 필요 포함 전부(D-279 ① 쿠팡 금액 그대로 검사)."""
    out: dict = defaultdict(lambda: [0.0, 0.0])
    for ch, ym, s_, e_, *_x in a.ushare:
        out[(ch, ym)][0] += s_
        out[(ch, ym)][1] += e_
    return out


def test_pending_split() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = _base(Path(td))
        rgw = [("2026-10-27", "2026-11-02", 1000, 700)]
        nov = [("2026-11-03", "2026-11-09", 100, 70), ("2026-11-17", "2026-11-23", 200, 140)]   # 두 번째 = 기준일(11-15) 뒤 주
        u = [("윙", "2026-11", 400, 320, "쿠팡 계산", "조회", []), ("윙", "2026-10", 1300, 1077, "쿠팡 계산", "조회", []),
             ("로켓그로스", "2026-10", 1000, 700, "쿠팡 계산", "조회", rgw), ("로켓그로스", "2026-11", 300, 210, "쿠팡 계산", "조회", nov),
             ("로켓그로스", "2026-09", 50, 35, "쿠팡 계산", "조회", [("2026-09-07", "2026-09-13", 50, 35)])]
        a = _stub(base, u)
        a._unsettled_share()
        sh = _sum(a)
        w11, w10 = sh[("윙", "2026-11")], sh[("윙", "2026-10")]
        assert _near(w11[2], 400) and _near(w11[3], 320), f"E1 윙 11월(B8) 관리 판매·정산 = 400·320 이어야: {w11}"
        assert _near(w10[2], 1100) and _near(w10[3], 897), f"E2 윙 10월(주문별매출 실제값) 관리 = 1,100·897 이어야: {w10}"
        r10, r11 = sh[("로켓그로스", "2026-10")], sh[("로켓그로스", "2026-11")]
        assert _near(r10[0], 500) and _near(r10[2], 300) and _near(r10[3], 210), f"E3 RG 10월 몫(날짜 달 · 10월 판매 비율 60%) = 판매 500 · 관리 300·210: {r10}"
        assert _near(r11[0], 800) and _near(r11[2], 200) and _near(r11[3], 140), \
            f"E4 RG 11월 몫(11월 판매 비율 25% · 기준일 뒤 주 포함 D-269 ②) = 판매 800 · 관리 200·140: {r11}"
        assert [(c[0], c[1], c[3]) for c in a.ucheck] == [("로켓그로스", "2026-09", 35)], f"E5 그 달 판매분석 없음 = 확인 필요 1건: {a.ucheck}"
        tot = _all(a)
        assert [round(sum(tot[k][i] for k in tot if k[0] == "로켓그로스")) for i in (0, 1)] == [1350, 945], \
            f"E6 RG 나눈 조각 합 = 쿠팡 예정 줄 금액 그대로(D-279 ①): {dict(tot)}"
        assert _near(a.um_settle, 320 + 897 + 210 + 140), f"E7 확인 필요 금액은 관리 몫에 안 넣음: {a.um_settle}"
        assert _near(a.mset[("로켓그로스", "2026-11")][1], 350 + 70 + 140), f"확인 필요 아닌 금액만 달 비율 분모: {a.mset[('로켓그로스', '2026-11')]}"
        a.msales = {("윙", "2026-11"): (0.0, 500.0)}
        a.pur, a.wconf, a.S = {"2026-11": 5000.0}, {"2026-11": [500.0, 0.0, 0.0]}, 0.5
        assert a.svc_month("2026-11") == (400.0, 900.0), f"이용료 덜 온 달 = 정산 파일 + 예정분 관리 판매: {a.svc_month('2026-11')}"
        saved = json.loads((base / "검증자료" / "결제확정_지연분포.json").read_text(encoding="utf-8"))
        assert saved["분포"] == [[8, 1.0]], f"E8 결제→구매확정 지연 분포 저장(D-269 ①): {saved}"
        b = _stub(base, [("윙", "2026-11", 100, 80, "쿠팡 계산", "조회", []), ("윙", "2026-09", -50, -45, "쿠팡 계산", "조회", [])])
        b._unsettled_share()
        why = {c[1]: c[4] for c in b.ucheck}
        assert "검산" in why.get("2026-11", "") and "원" in why.get("2026-11", "") and "나눌 판매 없음" in why.get("2026-09", ""), \
            f"E9 B8·ⓒ2 둘 다 검산 걸림(금액으로 표시 D-281)·음수 예정 = 확인 필요: {why}"
        assert _near(b.um_sales, 0) and _near(b.um_settle, 0), f"확인 필요 금액 = 관리 몫 0: {b.um_sales} {b.um_settle}"
        with tempfile.TemporaryDirectory() as td2:                  # 주문별매출 하나도 없음 + 저장한 지연 분포 → ⓒ2 로 채움(D-269 ①)
            (Path(td2) / "검증자료").mkdir()
            (Path(td2) / "검증자료" / "결제확정_지연분포.json").write_text(json.dumps(saved), encoding="utf-8")
            c = _stub(Path(td2), [("윙", "2026-11", 1600, 1280, "쿠팡 계산", "조회", [])])
            c.files = [_file("윙", date(2026, 11, 2), date(2026, 11, 8), [(9, "2", 50, 45, date(2026, 11, 3)), (10, "1", 100, 70, date(2026, 11, 4))])]
            c._unsettled_share()
            assert not c.ucheck, f"E10 ⓒ2 로 채움 = 확인 필요 0: {c.ucheck}"
            w = _sum(c)[("윙", "2026-11")]
            assert _near(w[2], 1600 * 1300 / 1450) and _near(w[3], 1280 * 910 / 1045), \
                f"E10 ⓒ2 관리 판매·정산 = 1,434.48·1,114.64(남은 판매 옵션1 1,300·옵션2 150 · 환산 0.7·0.9): {w}"
            assert "ⓒ2" in c.ushare[0][7], f"근거 문구 = ⓒ2: {c.ushare[0][7]}"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    test_wing_unsettled()
    test_pending_split()
    print("✅ 정산 예정분 관리 몫 나누기 시험(D-262 ① 실제값 · 윙 B8 → ⓒ2 채움·지연 분포 저장 D-269 ① · 로켓그로스 그 달 판매 비율 D-269 ② · 쿠팡 예정 금액 그대로 D-279 · 금액 판정 D-281) 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
