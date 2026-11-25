"""위탁정산서 정산 예정분 관리 몫 나누기 시험(오프라인 · 결정적 · 실 API·네트워크 없음) — T-63 · T-73 · D-262 · D-266 · D-267 · D-269 · D-279 · D-281 · D-282.

기대값 = 결정 규칙에서 손으로 계산한 금액(원 · 코드에서 뽑지 않음 · 판정 = 금액 일치 D-281):
  ① 윙 주문별매출 실제값(D-262 ①) — 정산 파일 기간 밖 구매확정 줄 합(판매 = productGmv + deliveryGmv · 정산 = apAmount)이
     쿠팡 예정과 원 단위 같으면 그 줄의 상품(배송비 줄 = 같은 주문 상품)으로 나눔.
  ② 윙 B8+환산(D-266 ① · D-267) — 판매분석 일별 윙 순액 결제일 [그 달 1일−30일, E−8일 = 기준일−9일] − 이미 구매확정된 판매 · 옵션 합 뒤 음수 0.
  ③ 윙 B8 이 '확인 필요' 조건이면 빼지 않고 ⓒ2 = 저장해 둔 결제→구매확정 지연 분포 + 윙 정산 파일 환산(이미 확정 주문 빼기 없음)으로 채움(D-269 ①) ·
     지연 분포는 계산할 때마다 저장(검증자료/결제확정_지연분포.json). ⓒ2 도 안 되면 ⓑo(D-282 · 기준일 전에 받은 자료만 · 시나리오 a·b·c)
     → 그것도 안 되면 그 금액만 '확인 필요'. B8·ⓒ2 도 기준일에 앱이 가진 자료만(T-84 · 시나리오 d·e·f·g).
  ④ 로켓그로스 = 그 달 판매분석 판매 비율(D-269 ② · T-63 이전 방식 · 기준일 뒤 주도 같음) · 주가 달을 걸치면 날짜의 달로 나눔(D-266 ③) ·
     그 달 판매분석 판매 없음·0~100% 밖 = 그 금액만 '확인 필요'.
  ⑤ 쿠팡 예정 줄 금액은 그대로(D-279 ①) — 나눈 조각의 판매·정산 합 = 쿠팡 예정 줄 금액(원 단위).
  윙 예정분 판매·정산 = 같은 기간(매출내역) · 음수 예정(환불 구매확정)도 남김.
  ⑥ 새 형식 위탁자 정산서(T-178)도 같은 순서·같은 값 — 상품 줄 합 = 옛 엑셀 관리 몫 · ① 은 쿠폰·수수료도 실제값(D-261 ② E2) ·
     ②는 옵션 합 뒤 음수 0(D-266 ①) → 윙 상품 줄 예정 판매 ≥ 0(E1) · 로켓그로스 = M: 달 전체(그 달에 시작한 주 W: 아님 D-269 ②) ·
     못 나눈 금액만 빼고 정산서 발행(D-262 ③ · 상태·지급 줄 검산 안 막음).
  재현 근거 = output\\_검증_261117_정산끝난달\\판정_보고.md 6절(scripts\\b2_wing.py C2 · b5_fill.py).

    python tools/verify_settlement_pending_offline.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coupang_analytics import settlement_consignor_month as CM  # noqa: E402
from coupang_analytics import settlement_consignor_month_calc as CALC  # noqa: E402
from coupang_analytics import settlement_consignor_month_dep as DEP  # noqa: E402
from coupang_analytics import settlement_consignor_month_out as OUT  # noqa: E402
from coupang_analytics import settlement_files as SF  # noqa: E402
from coupang_analytics import settlement_statement_pending as PEND  # noqa: E402
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


def _file(ch: str, s: date, e: date, rows: list, settle: date | None = None) -> SF.SettleFile:
    f = SF.SettleFile(channel=ch, account=ACCT, period_start=s, period_end=e, kind="주정산" if ch == "윙" else "판매수수료",
                      settle_date=settle or e + timedelta(days=7))
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
        test_wing_ops(base)
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


def _wing_daily(extra: dict | None, only: dict | None = None) -> dict:
    """윙 판매분석 일별 — only 가 있으면 그것만 · 아니면 _daily() 에 extra({날짜: (옵션, 금액)}) 더함."""
    d = {k: {"옵션": {}} for k in only} if only is not None else _daily()
    for day, (vid, amt) in (only or extra or {}).items():
        d.setdefault(day, {"옵션": {}})["옵션"][vid] = {"구분": "윙", "판매금액": amt}
    return d


def test_wing_ops(base: Path) -> None:
    """D-282 ⓑo — B8·ⓒ2 둘 다 '확인 필요'일 때 판매분석 일별 [그 달 1일−30일, 판매 끝] − 이미 확정(기준일 전에 받은 자료만)의 관리 비율 × 쿠팡 예정.

    손 계산(옵션 1 = 관리 · 2 = 관리 밖 · 지연 분포 = 202610 주문 2줄 모두 8일):
    a 기준일 11-15 · 11월 예정 판매 100·정산 80 · 일별에 11-12 옵션2 600 더함. B8(결제 10-02~11-06) 남은 판매 400 · ⓒ2 1,550 = 둘 다 검산(1.5배) 걸림.
      ⓑo 결제 10-02~11-14 · 202610 주문별매출(10-31+15 = 11-15 ≤ 기준일 → 받음) 옵션1 1,000·옵션2 200 빼고 · 윙 정산 파일(정산일 11-15 ≤ 기준일)
      주문 9 옵션2 50 을 11-03−8일 = 10-26 에서 뺌 → 옵션1 1,000+300+100+999−1,000 = 1,399 · 옵션2 200+50−50+600−200−50 = 550
      → 관리 비율 1,399/1,949 → 관리 판매 71.78 · 관리 정산 57.42.
    b 기준일 11-10 · 11월 예정 판매 200·정산 160. 202610 주문별매출은 아직 안 받음(11-15 > 11-10) · 정산 파일 정산일 11-15 > 기준일 → 둘 다 빼기에 안 씀.
      B8·ⓒ2 도 같은 자르기(T-84) → 빼기 0 · 결제 10-02~11-01 남은 판매 1,650(검산 300 이상 = 둘 다 걸림). ⓑo 결제 10-02~11-09 = 옵션1 1,400 · 옵션2 200 → 0.875 → 관리 175 · 140
      (받기 전 자료를 섞으면 옵션2 가 0 → 200·160 이 되어 틀림).
    c 기준일 11-15 · 일별 = 10-05 옵션1 1,000 뿐(202610 주문 3 으로 이미 확정) → ⓑo 남은 판매 0원 = 확인 필요(사유 금액 표시 D-281) · 관리 몫 0.
    """
    a = _stub(base, [("윙", "2026-11", 100, 80, "쿠팡 계산", "조회", []), ("윙", "2026-09", -50, -45, "쿠팡 계산", "조회", [])])
    a.ctx.daily = {AID: _wing_daily({"2026-11-12": ("2", 600)})}
    a._unsettled_share()
    why = {c[1]: c[4] for c in a.ucheck}
    assert "2026-11" not in why, f"a ⓑo 로 채움 = 11월 확인 필요 0: {why}"
    w = _sum(a)[("윙", "2026-11")]
    assert _near(w[2], 100 * 1399 / 1949) and _near(w[3], 80 * 1399 / 1949), f"a ⓑo 관리 판매·정산 = 71.78·57.42: {w}"
    assert "ⓑo" in next(x[7] for x in a.ushare if x[1] == "2026-11"), f"a 근거 문구 = ⓑo: {a.ushare}"
    assert "나눌 판매 없음" in why.get("2026-09", "") and "ⓑo" in why.get("2026-09", ""), f"a 음수 예정·지연 자료 없음 = 확인 필요: {why}"
    b = _stub(base, [("윙", "2026-11", 200, 160, "쿠팡 계산", "조회", [])])
    b.ctx.basis = "2026-11-10"
    b._unsettled_share()
    assert not b.ucheck, f"b ⓑo 로 채움 = 확인 필요 0: {b.ucheck}"
    w = _sum(b)[("윙", "2026-11")]
    assert _near(w[2], 175) and _near(w[3], 140), f"b 기준일 전에 안 받은 지난달 주문별매출·정산 파일은 안 뺌 → 관리 175·140: {w}"
    c = _stub(base, [("윙", "2026-11", 100, 80, "쿠팡 계산", "조회", [])])
    c.ctx.daily = {AID: _wing_daily(None, only={"2026-10-05": ("1", 1000)})}
    c._unsettled_share()
    why = {x[1]: x[4] for x in c.ucheck}
    assert "ⓑo: 나눌 판매 없음" in why.get("2026-11", "") and "쿠팡 예정 판매 100원" in why.get("2026-11", ""), f"c ⓑo 남은 판매 0 = 확인 필요(금액): {why}"
    assert _near(c.um_sales, 0) and _near(c.um_settle, 0), f"c 확인 필요 금액 = 관리 몫 0: {c.um_sales} {c.um_settle}"


def _cut_run(base: Path, files: list, u: list, basis: str = "2026-11-10") -> tuple:
    """기준일(기본 11-10) · 일별 = 10-10 옵션1 600 · 10-20 옵션2 400 → (나눈 조각 금액, 확인 필요 (판매 방식, 달, 정산대상), 근거·사유)."""
    a = _stub(base, u)
    a.ctx.basis = basis
    a.ctx.daily = {AID: _wing_daily(None, only={"2026-10-10": ("1", 600), "2026-10-20": ("2", 400)})}
    a.files = files
    a._unsettled_share()
    return ([tuple(round(x, 2) for x in (s_, e_, ms, me)) for _ch, _ym, s_, e_, _r, ms, me, _h in a.ushare],
            [(c[0], c[1], c[3]) for c in a.ucheck], [x[7] for x in a.ushare])


def _later_orders(base: Path) -> None:
    """기준일(11-10) 뒤에 받는 202610 주문별매출(10-31+15 = 11-15) — 주문 40 옵션1 600 결제 10-10 · 구매확정 10-18(지연 8일)."""
    d = base / "검증자료" / "월자료" / ACCT
    d.mkdir(parents=True, exist_ok=True)
    (d / "주문별매출_202610.json").write_text(json.dumps({"줄": [_row(40, 1, 600, 500, "2026-10-10", "2026-10-18")]}), encoding="utf-8")


def _store(base: Path, ym: str, pmf: list) -> None:
    (base / "검증자료").mkdir(parents=True, exist_ok=True)
    (base / "검증자료" / "결제확정_지연분포.json").write_text(json.dumps({"기준 달": ym, "분포": pmf}), encoding="utf-8")


def test_cut_basis() -> None:
    """T-84 — B8·ⓒ2 도 ⓑo(D-282)처럼 기준일에 앱이 가진 자료만: 기준일 뒤에 받은 주문별매출 달 · 기준일 뒤 정산된 윙 정산 파일 ·
    기준일 뒤 달 저장 분포를 넣어도 결과 = 그것들이 없을 때 · 정산일 모르는 윙 정산 파일 = 확인 필요.

    손 계산(기준일 11-10 · 11월 예정 · 결제 [10-02, 11-09−8일 = 11-01] · 받은 달 끝 = (11-10−14일)의 달 = 10월 → 주문별매출·지연 분포 = 10월 앞 달만):
    d B8 — 자료 없음(빼기 0 · 환산 = 판매 그대로) → 남은 판매 옵션1 600 · 옵션2 400 · 쿠팡 판매 800·정산 640 → 관리 480·384.
      (기준일 뒤 202610 주문별매출 옵션1 600 · 정산일 11-15 윙 파일 옵션2 400 을 섞으면 옵션1 0 → 관리 0 이 되어 틀림)
    e ⓒ2 — 정산일 11-01 윙 파일 주문 30 옵션2 100(정산 90 · 구매확정 10-25) → B8 = 지연 자료 없음 → 저장 분포(기준 달 2026-09 · 5일)로
      10-20 옵션2 100 뺌 → 옵션1 600 · 옵션2 300 · 환산 = 파일 비율 0.9(옵션1 = 계정 비율 0.9) → 관리 800×600/900 = 533.33 · 640×540/810 = 426.67.
    f 저장 분포 기준 달 2026-12(기준일 뒤 자료) = 쓰지 않음 → e 에서 저장 분포 없는 때와 같이 확인 필요.
    g 정산일 모르는 윙 정산 파일(줄 = 결제 시작 전 · d 처럼 B8 은 될 자료) = 확인 필요(ⓑo 와 같은 사유 · 기준일 전 자료인지 모름).
    """
    u: list = [("윙", "2026-11", 800, 640, "쿠팡 계산", "조회", [])]
    f30 = _file("윙", date(2026, 10, 19), date(2026, 10, 25), [(30, "2", 100, 90, date(2026, 10, 25))], settle=date(2026, 11, 1))
    f41 = _file("윙", date(2026, 11, 2), date(2026, 11, 8), [(41, "2", 400, 360, date(2026, 10, 28))], settle=date(2026, 11, 15))
    with tempfile.TemporaryDirectory() as t0, tempfile.TemporaryDirectory() as t1:
        alone = _cut_run(Path(t0), [], u)
        assert alone[0] == [(800, 640, 480, 384)] and not alone[1], f"d B8 자료 없음 = 관리 480·384: {alone}"
        _later_orders(Path(t1))
        mixed = _cut_run(Path(t1), [f41], u)
        assert mixed[:2] == alone[:2], f"d 기준일 뒤 받은 주문별매출·기준일 뒤 정산된 윙 파일은 B8 에 안 씀 → 없을 때와 같음: {mixed} ≠ {alone}"
    with tempfile.TemporaryDirectory() as t0, tempfile.TemporaryDirectory() as t1:
        _store(Path(t0), "2026-09", [[5, 1.0]])
        alone = _cut_run(Path(t0), [f30], u)
        assert alone[0] == [(800, 640, 533.33, 426.67)] and not alone[1] and "ⓒ2" in alone[2][0], f"e ⓒ2 = 관리 533.33·426.67: {alone}"
        _store(Path(t1), "2026-09", [[5, 1.0]])
        _later_orders(Path(t1))
        f42 = _file("윙", date(2026, 11, 2), date(2026, 11, 8), [(42, "1", 200, 150, date(2026, 11, 3))], settle=date(2026, 11, 15))
        mixed = _cut_run(Path(t1), [f30, f42], u)
        assert mixed[:2] == alone[:2], f"e 기준일 뒤 자료를 넣어도 ⓒ2 = 없을 때와 같음: {mixed} ≠ {alone}"
    with tempfile.TemporaryDirectory() as t0, tempfile.TemporaryDirectory() as t1:
        alone = _cut_run(Path(t0), [f30], u)
        assert alone[1] == [("윙", "2026-11", 640)], f"f 저장 분포 없음 = 확인 필요: {alone}"
        _store(Path(t1), "2026-12", [[5, 1.0]])
        mixed = _cut_run(Path(t1), [f30], u)
        assert mixed[:2] == alone[:2], f"f 기준일 뒤 달(2026-12) 저장 분포는 ⓒ2 에 안 씀: {mixed} ≠ {alone}"
    with tempfile.TemporaryDirectory() as t0:
        nod = _file("윙", date(2026, 9, 14), date(2026, 9, 20), [(43, "2", 10, 9, date(2026, 9, 20))])   # 결제 시작 전 줄 = 빼기에 안 씀(B8 은 됨)
        nod.settle_date = None
        got = _cut_run(Path(t0), [nod], u)
        assert got[1] == [("윙", "2026-11", 640)] and "정산일 모르는 윙 정산 파일 1개" in got[2][0], f"g 정산일 모르는 윙 파일 = 확인 필요: {got}"


def test_actual_cut() -> None:
    """D-292 — ① 주문별매출 실제값도 기준일에 앱이 가진 자료만(B8·ⓒ2·ⓑo 와 같은 자르기):
    h 기준일 11-10 · 10월 예정 600·500 · 202610 주문별매출(받는 날 11-15 = 기준일 뒤)이 쿠팡 예정과 원 단위 같아도 ① 에 안 씀 → 그 파일이 없을 때와 같음.
    i 기준일 11-15(202610 은 받은 달) · 정산일 11-20 윙 파일(기준일 뒤)이 주문 44 를 덮어 ① 이 맞아 보여도 그 파일 기간은 안 뺌 → 그 파일이 없을 때와 같음.
    (E2 = 기준일 11-15 · 받은 202610 · 기준일 전 파일 → ① 그대로 = test_pending_split)"""
    u: list = [("윙", "2026-10", 600, 500, "쿠팡 계산", "조회", [])]
    with tempfile.TemporaryDirectory() as t0, tempfile.TemporaryDirectory() as t1:
        alone = _cut_run(Path(t0), [], u)
        _later_orders(Path(t1))
        mixed = _cut_run(Path(t1), [], u)
        assert not any("주문별매출 실제값" in h for h in mixed[2]), f"h 기준일 뒤 받는 주문별매출은 ① 에 안 씀: {mixed}"
        assert mixed[:2] == alone[:2], f"h 기준일 뒤 받는 주문별매출을 넣어도 = 없을 때와 같음: {mixed} ≠ {alone}"
    rows = [_row(40, 1, 600, 500, "2026-10-10", "2026-10-18"), _row(44, 2, 400, 360, "2026-10-20", "2026-10-28")]
    f45 = _file("윙", date(2026, 10, 26), date(2026, 11, 1), [(44, "2", 400, 360, date(2026, 10, 28))], settle=date(2026, 11, 20))
    with tempfile.TemporaryDirectory() as t0, tempfile.TemporaryDirectory() as t1:
        for t in (t0, t1):
            d = Path(t) / "검증자료" / "월자료" / ACCT
            d.mkdir(parents=True)
            (d / "주문별매출_202610.json").write_text(json.dumps({"줄": rows}), encoding="utf-8")
        alone = _cut_run(Path(t0), [], u, "2026-11-15")
        mixed = _cut_run(Path(t1), [f45], u, "2026-11-15")
        assert not any("주문별매출 실제값" in h for h in mixed[2]), f"i 기준일 뒤 정산된 윙 파일 기간은 ① 에서 안 뺌: {mixed}"
        assert mixed[:2] == alone[:2], f"i 기준일 뒤 정산된 윙 파일을 넣어도 = 없을 때와 같음: {mixed} ≠ {alone}"


def _new_form(a: Account, month: str, judge: CM.ConsignorJudge | None = None) -> CALC.MonthState:
    """옛 엑셀과 같은 계정 자료(_stub)로 새 형식 한 달 — 옵션 n 의 등록상품 = 'Pn' · 관리 판정 = 옛 코드 is_mv."""
    vids = ("1", "2", "3", "4")
    src = {"acct": a.acct, "aid": a.aid, "base": str(a.ctx.base), "basis": a.ctx.basis, "cdate": a.cdate,
           "mpids": {f"P{v}" for v in vids if a.is_mv(v)}, "opt2pid": {v: f"P{v}" for v in vids}, "is_mv": {v: a.is_mv(v) for v in vids},
           "inventory": {}, "prows": [], "file_rows": [], "lines": [], "line_info": [], "L_gen": {}, "v": {},
           "files_meta": [(i, f.channel, f.kind, str(f.period_start), str(f.period_end)) for i, f in enumerate(a.files)],
           "periods": a.ctx.periods[a.aid], "daily": a.ctx.daily[a.aid], "orders": PEND.order_months(a.ctx.base, a.acct), "files": a.files,
           "u": [tuple(x) for x in a.u]}
    st = CALC.MonthState(src, month, judge or CM.ConsignorJudge())
    CALC.pending_sales(st)
    return st


def _c(st: CALC.MonthState, pid: str) -> list:
    return [round(x, 2) for x in st.pend[pid][1:5]] if pid in st.pend else [0.0] * 4


def test_new_form_wing() -> None:
    """⑥ 윙 — 11월 B8: 옵션 1·2 모두 관리 · 판매분석 주별(W) 순액 옵션2 = −50(환불) → 옛 새 형식(주별 원값 비율)은 옵션2 예정 판매 음수(E1 걸림).
    B8 남은 판매(E1 손 계산 = test_pending_split) = 옵션1 만 400 · 옵션2 음수 → 0 → 상품 줄 P1 판매 400 · 정산 320, P2 = 0.
    10월 ①: 주문 3 옵션1 판매 1,000·쿠폰 150·수수료 50·정산 800 + 배송비 100·수수료 3·정산 97 → P1 = 1,100 · −150 · −53 · 4 = 897 − (1,100−150−53) = 0.
    주문 2 줄(옵션 2 · 200·180·쿠폰 0·수수료 20) → P2(관리 밖) = 계정 판매에만."""
    with tempfile.TemporaryDirectory() as td:
        base = _base(Path(td))
        f = base / "검증자료" / "월자료" / ACCT / "주문별매출_202610.json"
        rows = json.loads(f.read_text(encoding="utf-8"))["줄"]
        for r, (cp, fee) in zip(rows, ((0, 20), (150, 50), (0, 3))):
            r.update(sfcAmount=cp, trAmountIncVat=fee)
        f.write_text(json.dumps({"줄": rows}), encoding="utf-8")
        a = _stub(base, [("윙", "2026-11", 400, 320, "쿠팡 계산", "조회", []), ("윙", "2026-10", 1300, 1077, "쿠팡 계산", "조회", [])])
        a.vids = {"1", "2"}
        a.ctx.periods[AID]["W:2026-11-02"] = {"옵션": {"1": {"구분": "윙", "판매금액": 999}, "2": {"구분": "윙", "판매금액": -50}}}
        st = _new_form(a, "2026-11")
        assert _c(st, "P1") == [400, 0, -80, 0] and _c(st, "P2") == [0, 0, 0, 0], f"⑥ 윙 B8 상품 줄 = P1 400·320 · P2 0: {dict(st.pend)}"
        assert {k: round(v) for k, v in st.pend_wing.items() if v} == {"P1": 400}, st.pend_wing
        assert st.settle_by_ch["윙"] == Counter({"P1": 320}) and not st.pend_check, f"⑥ 윙 정산 나누기 = 320: {st.settle_by_ch}"
        a.vids = set(MV)
        st = _new_form(a, "2026-10")
        assert _c(st, "P1") == [1100, -150, -53, 0], f"⑥ 윙 ① 실제값 쿠폰·수수료(D-261 ②): {dict(st.pend)}"
        assert "P2" not in st.pend and round(st.allsales["P2"]) == 200, f"⑥ 관리 밖 상품 = 계정 판매에만: {dict(st.allsales)}"
        assert st.pend_info[0]["추정"] is False and "주문별매출 실제값" in st.pend_info[0]["상품 나눈 기준"], st.pend_info
        a._unsettled_share()
        assert _near(a.um_settle, 320 + 897), f"옛 엑셀 관리 몫(같은 자료) = 1,217: {a.um_settle}"


def test_new_form_rg_and_excluded() -> None:
    """⑥ 로켓그로스 10월 = M:2026-10 판매 비율 60%(W: 주별 = 옵션3 −50 은 안 씀) → P3 판매 600·정산 420 = 옛 엑셀 관리 몫.
    9월 = 그 달 판매분석 없음 → 그 금액(50·35)만 빼고 발행: 상품 줄 0 · '확인 필요' 문장 1줄 · 지급 줄 검산(정산 35 = 상품 0 + 뺀 35) 차이 0 ·
    상태 = 다른 예정분 없으면 '확인 필요'(사유에 뺀 금액)."""
    with tempfile.TemporaryDirectory() as td:
        base = _base(Path(td))
        a = _stub(base, [("로켓그로스", "2026-10", 1000, 700, "쿠팡 계산", "조회", [("2026-10-05", "2026-10-11", 1000, 700)]),
                         ("로켓그로스", "2026-09", 50, 35, "쿠팡 계산", "조회", [("2026-09-07", "2026-09-13", 50, 35)])])
        a.ctx.periods[AID]["W:2026-10-05"] = {"옵션": {"3": {"구분": "로켓그로스", "판매금액": -50}, "4": {"구분": "로켓그로스", "판매금액": 500}}}
        st = _new_form(a, "2026-10")
        assert _c(st, "P3")[0] == 600 and _near(sum(st.pend["P3"][1:5]), 420), f"⑥ RG = M: 달 판매 비율 60%: {dict(st.pend)}"
        assert st.rgsales == Counter({"P3": 600, "P4": 400}), st.rgsales
        assert not st.pend_wing, f"⑥ 로켓그로스 예정 = 윙 예정 판매 아님(E1 D-405): {st.pend_wing}"
        a._unsettled_share()
        assert _near(a.um_sales, 600) and _near(a.um_settle, 420), f"옛 엑셀 관리 몫 = 600·420: {a.um_sales} {a.um_settle}"
        st = _new_form(a, "2026-09")
        assert not st.pend and not st.pend_info and [(x["판매"], x["정산"]) for x in st.pend_check] == [(50, 35)], (dict(st.pend), st.pend_check)
        assert sum("확인 필요" in j and "나눌 판매 없음" in j for j in st.j) == 1, st.j
        st.d["line_info"] = [("예정", "로켓그로스", "2026-09", 35.0, 0.0, Counter(), ["", "", "2026-10-30", "2026-09-07", "2026-09-13", "70", "예정"])]
        items = DEP._pay_items(st, {"윙": 0.0, "로켓그로스": 0.0})
        assert [c["차이"] for c in st.chk if c["검사"].startswith("로켓그로스 이 달 판매 기간 지급 줄")] == [0], (items, st.chk)
        out = {"status": OUT.month_status(False, OUT.check_lists(st))}
        assert out["status"] == "확인 필요" and "정산 35" in OUT._judge_status(st, out), OUT._judge_status(st, out)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    test_wing_unsettled()
    test_pending_split()
    test_cut_basis()
    test_actual_cut()
    test_new_form_wing()
    test_new_form_rg_and_excluded()
    print("✅ 정산 예정분 관리 몫 나누기 시험(D-262 ① 실제값 · 윙 B8 → ⓒ2 → ⓑo 채움(D-282)·지연 분포 저장 D-269 ① · 로켓그로스 그 달 판매 비율 D-269 ② · 쿠팡 예정 금액 그대로 D-279 · 금액 판정 D-281 · 새 형식 = 같은 순서·같은 값·못 나눈 금액만 뺌 T-178) 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
