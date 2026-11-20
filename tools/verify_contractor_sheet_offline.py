"""셀독 계약자별 상품 현황 오프라인 검증(T-132 · D-357·D-358 · 설계안 8절) — 로그인·OpenAI·구글 호출 없음.

기대값은 결정 문구·설계안에서 뽑았다(코드에서 뽑지 않음):
- D-357 ② 10건 규칙 = 쿠팡 계정 단위 · 상품 10개 이상이면 7일 판매 0건 개인 상품을 뺌(9 남김 · 10·11 뺌 · 뺀 수 요약 표시)
- D-358 양식: 요약 + 사업자 시트만 · A1 '◀ 요약으로' · 날짜 최근이 왼쪽 · 7일 합계 오른쪽 끝 · 셀독 행만 바탕색 · 칸 폭 표
  (사업자 9·15·50·19·11·13·14·10 · 날짜 9 · 합계 13 / 요약 7·28·16·26·12·9·11·11·13·13·14·11) · 구글 = 같은 폭 픽셀(9 → 68)
- D-358 ② 개인 상품 = 판매중만(셀독은 판매중지도) · ③ 판매가 + 즉시할인 후 · ④ 그로스 재고만(판매자배송 '－')
- D-358 ⑦ 자료 없는 계정 = 요약 이름 옆 '(로그인 실패)' 같은 표시 · 옛 값 안 씀 · ⑧ 무판매 개인 상품만 링크 추가 조회
- 설계안 3절 판정 3단(VID 고정 → 같은 상품명 → AI 후보) · 판정표 덧붙이기 · 다시 실행 = AI 0회 · 애매 = 판정표에만
- D-358 ⑩ 구글시트 = 주소 없음 ⚠ · 403/404 ❌ 후 계속 · 임시 탭 → 교체 · 대장에서 사라진 탭 지움
실행: python tools/verify_contractor_sheet_offline.py
"""
from __future__ import annotations

import gzip
import json
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass


from coupang_analytics import contractor_sheet as CS  # noqa: E402
from coupang_analytics import contractor_sheet_judge as CJ  # noqa: E402
from coupang_analytics import contractor_stage as ST  # noqa: E402
from coupang_analytics import gsheet_contractor as GC  # noqa: E402
from coupang_analytics import product_info as PI  # noqa: E402
from coupang_analytics.input_list import Account, Product  # noqa: E402

RUN = date(2026, 11, 17)
DATE_TO = "2026-11-16"
DAYS = [f"2026-11-{d:02d}" for d in range(10, 17)]   # 11-10 ~ 11-16(옛 → 최근)
FAILS: list[str] = []


def check(cond, msg):
    print(("  ✔ " if cond else "  ✘ ") + msg)
    if not cond:
        FAILS.append(msg)


# ── 가짜 저장 자료(가상 상품명 · 개인정보 없음) ─────────────────────────
def _gz(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False)


def put_products(out: Path, acc: str, rows: list[dict], day: str = "2026-11-17") -> None:
    """rows = [{vid, name, opt, reg(NORMAL|RFM), price, st(ON_SALE…)}]"""
    got = [{"vendorInventoryId": r.get("vinv", 1), "productName": r["name"], "productStatus": r.get("st", "ON_SALE"),
            "vendorItemId": r["vid"], "itemName": r.get("opt", ""), "registrationType": r.get("reg", "NORMAL"),
            "salePrice": r.get("price", 10000)} for r in rows]
    _gz(out / "상품정보_일별" / acc / f"{day}.json.gz", {"계정": acc, "날짜": day, "상품": got})


def put_inventory(out: Path, acc: str, props: list[dict], day: str = "2026-11-17") -> None:
    body = json.dumps({"viProperties": [{
        "vendorItemId": p["vid"], "listingDetails": {"vendorInventoryName": p["name"], "productId": p.get("pid", ""),
                                                     "isSaleSuspended": p.get("off", False)},
        "pricing": {"salesPrice": {"amount": p["price"]}, "allMemberInstantDiscount": {"amount": p.get("disc", 0)}},
        "inventoryDetails": {"orderableQuantity": p.get("stock", 5)}} for p in props]}, ensure_ascii=False)
    _gz(out / "재고현황_일별" / acc / f"{day}.json.gz", {"응답": [body]})


def put_sales(out: Path, acc: str, by_vid: dict[str, list[int]]) -> None:
    """by_vid = {vid: [7일 판매(옛 → 최근)]}"""
    rec = {d: {"옵션": {v: {"판매수량": q[i]} for v, q in by_vid.items()}} for i, d in enumerate(DAYS)}
    p = out / "판매분석_일별" / acc / "2026-11.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")


def put_match(out: Path, mapping: dict) -> None:
    (out / "_매칭결과.json").write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")


def acct(acc: str, biz: str, rep: str = "대표", ledger=()) -> Account:
    return Account(acc, rep, biz, products=[Product(name=n) for n in ledger])


def _logs():
    lines: list[str] = []
    return lines, lines.append


def _est(text: str) -> float:
    """머리글 한 줄 너비 어림(엑셀 칸 폭 단위 · 넉넉하게 한글 2.2 · 그 밖 1.2) — 구글 글꼴이 조금 넓어도 안 넘치게."""
    return sum(2.2 if "가" <= ch <= "힣" else 1.2 for ch in text)


def no_ai(system, user):
    raise AssertionError("AI 를 부르면 안 되는 시험에서 불림")


# ── 시험 ───────────────────────────────────────────────
def t1_ten_rule():
    print("[T1] 10건 규칙 = 쿠팡 계정 단위(9 남김 · 10·11 뺌 · 뺀 수 표시 · 셀독은 0건도 남음) — D-357 ②")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        accs = []
        for n in (9, 10, 11):
            acc = f"acc{n}"
            rows = [{"vid": f"{n}0{i}", "name": f"개인상품{n}-{i}"} for i in range(n - 1)] + [{"vid": f"{n}99", "name": "관리상품"}]
            put_products(out, acc, rows)
            put_sales(out, acc, {f"{n}00": [0, 0, 0, 0, 0, 0, 3]})   # 개인 1개만 판매 · 나머지 개인 0건 · 관리상품 0건
            accs.append(acct(acc, f"사업자{n}"))
        put_match(out, {f"acc{n}": {"관리상품": [f"{n}99"]} for n in (9, 10, 11)})
        logs, log = _logs()
        rep = ST.build_report(accs, out, run_day=RUN, date_to=DATE_TO, ask=no_ai, log=log)
        by = {b.name: b for b in rep.bizs}
        check(len(by["사업자9"].rows) == 9 and by["사업자9"].dropped == 0, "9개 계정 = 0건 개인 상품도 남김(9줄 · 뺌 0)")
        check(len(by["사업자10"].rows) == 2 and by["사업자10"].dropped == 8, "10개 계정 = 판매 1개 + 셀독 1개만(뺌 8)")
        check(len(by["사업자11"].rows) == 2 and by["사업자11"].dropped == 9, "11개 계정 = 뺌 9")
        check(all(any(r.sel and r.s7 == 0 for r in b.rows) for b in rep.bizs), "셀독 상품은 7일 0건이어도 남음")
        check(by["사업자10"].total == 10, "요약 '전체 상품' = 그 계정 등록상품 수(10)")
    # 한 사업자 2계정 = 계정마다 따로 셈(합치면 10 이상이어도 각 계정 9개면 안 뺌)
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        for acc in ("x1", "x2"):
            put_products(out, acc, [{"vid": f"{acc}{i}", "name": f"{acc}상품{i}"} for i in range(9)])
        put_match(out, {})
        rep = ST.build_report([acct("x1", "합친사업자"), acct("x2", "합친사업자")], out, run_day=RUN, date_to=DATE_TO,
                              ask=no_ai, log=lambda m: None)
        b = rep.bizs[0]
        check(len(rep.bizs) == 1 and b.accs == ["x1", "x2"] and len(b.rows) == 18 and b.dropped == 0,
              "같은 사업자 2계정 = 시트 1개 · 계정마다 9개라 0건도 남음(합 18 · 뺌 0)")


def t2_values_and_tiers():
    print("[T2] 판정 1·2단(VID 고정 → 같은 상품명) · 옵션 합산 · 판매가/즉시할인 · 그로스 재고 · 판매중지 규칙 — 설계안 3절·D-358 ②③④")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        put_products(out, "a1", [
            {"vid": "1", "name": "테스트 의자 CH100", "reg": "RFM", "st": "SUSPENDED"},   # 대장 VID · 판매중지 → 그래도 표시
            {"vid": "2", "name": "테스트 의자  CH100", "opt": "2개", "reg": "NORMAL", "price": 9000},   # 같은 상품명(공백만 다름)
            {"vid": "3", "name": "테스트 의자 CH100", "opt": "3개", "reg": "NORMAL", "st": "SUSPENDED"},   # 같은 상품명·판매중지 = 뺌
            {"vid": "4", "name": "개인 컵", "st": "SUSPENDED"},                              # 개인·판매중지 = 뺌
            {"vid": "5", "name": "개인 접시", "price": 5000},                                # 개인·판매중
        ])
        put_inventory(out, "a1", [{"vid": "1", "name": "테스트 의자 CH100", "price": 20000, "disc": 3000, "stock": 0,
                                   "pid": "P1"}])
        put_sales(out, "a1", {"1": [1, 0, 0, 0, 0, 2, 4], "2": [0, 0, 0, 0, 0, 1, -1], "5": [0, 0, 0, 0, 0, 0, 0]})
        put_match(out, {"a1": {"테스트 의자 CH100": ["1"]}})
        rep = ST.build_report([acct("a1", "사업자A")], out, run_day=RUN, date_to=DATE_TO, ask=no_ai, log=lambda m: None)
        rows = {r.name.split()[0]: r for r in rep.bizs[0].rows}
        chair = next(r for r in rep.bizs[0].rows if "의자" in r.name)
        check(chair.sel and chair.vids[:2] == ["1", "2"] and "3" not in chair.vids, "VID 고정 + 같은 상품명 옵션 합산 · 같은 상품명 판매중지 옵션 뺌")
        check(chair.d7 == [1, 0, 0, 0, 0, 3, 3] and chair.s7 == 7, "7일 판매 = 옵션 합(취소 음수 그대로)")
        check(chair.price == 9000 and chair.real == 9000, "판매가(최저)·실구매가(최저) = 옵션 중 최저")
        check(chair.growth == 0 and chair.method == CS.BOTH and chair.status == "판매중", "그로스 재고 = 그로스 옵션만 · 판매방식 둘 다")
        check(chair.pid == "P1" and chair.vid == "1", "링크 = productId 가 있는 옵션(대표 VID)")
        check("개인" in rows and rows["개인"].name == "개인 접시" and not rows["개인"].sel, "개인 = 판매중만(판매중지 컵 뺌)")
        check(rows["개인"].growth is None, "판매자배송 그로스 재고 = 없음(엑셀 '－')")
    # 즉시할인 = 그로스만(D-358 ③)
    it = CS.build_items([], [{"vendorItemId": 9, "listingDetails": {"vendorInventoryName": "g"},
                              "pricing": {"salesPrice": {"amount": 15000}, "allMemberInstantDiscount": {"amount": 1500}},
                              "inventoryDetails": {"orderableQuantity": 7}}], {})["9"]
    check(it.price == 15000 and it.real == 13500 and it.growth == 7, "그로스 = 판매가 15,000 · 즉시할인 후 13,500 · 재고 7")


def t3_ai_judge():
    print("[T3] 판정 3단 AI(후보만) · 확인 필요 = 판정표에만 · 덧붙이기 · 다시 실행 AI 0회 — 설계안 3절")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        put_products(out, "a1", [
            {"vid": "1", "name": "브랜드 무선 청소기 Q808"},
            {"vid": "2", "name": "차량용 청소기 Q808 재등록"},          # 모델코드 겹침 → 후보
            {"vid": "3", "name": "무선 청소기 브랜드 필터 세트"},         # 낱말 2개 겹침 → 후보
            {"vid": "4", "name": "등산 양말"},                           # 겹침 없음 → AI 안 물음
        ])
        put_match(out, {"a1": {"브랜드 무선 청소기 Q808": ["1"]}})
        calls: list[str] = []

        def ask(system, user):
            calls.append(user)
            return {"judgments": [{"line": 1, "seldoc": True, "ledger": "대장1", "confidence": "high", "reason": "같은 모델"},
                                  {"line": 2, "seldoc": True, "ledger": "대장1", "confidence": "low", "reason": "애매"}]}
        a = acct("a1", "사업자A", ledger=["브랜드 무선 청소기 Q808"])
        rep = ST.build_report([a], out, run_day=RUN, date_to=DATE_TO, ask=ask, log=lambda m: None, now="2026-11-17T20:00:00")
        rows = {r.vids[0]: r for r in rep.bizs[0].rows}
        check(len(calls) == 1 and "Q808 재등록" in calls[0] and "필터 세트" in calls[0] and "등산 양말" not in calls[0],
              "AI 1회 · 후보 2개만 보냄(겹침 없는 상품은 안 보냄)")
        check(rows["2"].sel and not rows["3"].sel and not rows["4"].sel, "확신 high = 셀독 · low = 확인 필요(시트는 개인)")
        j = json.loads((out / CJ.JUDGE_FILE).read_text(encoding="utf-8"))["a1"]
        check(j["3"][-1]["판정"] == CJ.UNSURE and "애매" in j["3"][-1]["근거"], "확인 필요 + 근거 원문 = 판정표 파일에")
        check(j["4"][-1]["단계"] == CJ.STEP_NOCAND and j["1"][-1]["단계"] == CJ.STEP_RULE, "규칙·후보 아님 판정도 근거 남김")
        calls.clear()
        rep2 = ST.build_report([a], out, run_day=RUN, date_to=DATE_TO, ask=ask, log=lambda m: None, now="2026-11-18T20:00:00")
        check(not calls and rep2.ai_calls == 0, "다시 실행 = AI 0회(판정표 고정)")
        check({r.vids[0]: r.sel for r in rep2.bizs[0].rows} == {"1": True, "2": True, "3": False, "4": False}, "다시 실행 결과 같음")
        j2 = json.loads((out / CJ.JUDGE_FILE).read_text(encoding="utf-8"))["a1"]
        check(all(len(j2[v]) == len(j[v]) for v in j), "같은 판정은 다시 덧붙이지 않음(줄 수 그대로)")
        # 같은 상품에 새 VID 가 생기면 기존 판정을 이음 · 옛 기록 안 지움
        put_products(out, "a1", [{"vid": "1", "name": "브랜드 무선 청소기 Q808"},
                                 {"vid": "2", "name": "차량용 청소기 Q808 재등록"},
                                 {"vid": "22", "name": "차량용 청소기 Q808 재등록", "opt": "2개"},
                                 {"vid": "3", "name": "무선 청소기 브랜드 필터 세트"}, {"vid": "4", "name": "등산 양말"}],
                     day="2026-11-18")
        rep3 = ST.build_report([a], out, run_day=date(2026, 11, 18), date_to="2026-11-17", ask=ask, log=lambda m: None)
        j3 = json.loads((out / CJ.JUDGE_FILE).read_text(encoding="utf-8"))["a1"]
        check(not calls and "22" in j3 and "이음" in j3["22"][-1]["근거"] and len(j3["2"]) >= len(j["2"]),
              "새 VID = 같은 상품 기존 판정 이음(AI 0회) · 옛 기록 그대로")
        check(any(r.sel and "22" in r.vids for r in rep3.bizs[0].rows), "새 VID 가 든 상품도 셀독")
    # AI 실패 = ⚠ · 그날 개인 · 기록 안 함(다음 실행이 다시 물음)
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        put_products(out, "a1", [{"vid": "1", "name": "브랜드 무선 청소기 Q808"}, {"vid": "2", "name": "차량용 청소기 Q808"}])
        put_match(out, {"a1": {"x": ["1"]}})

        def boom(system, user):
            raise RuntimeError("network")
        logs, log = _logs()
        rep = ST.build_report([acct("a1", "A", ledger=["브랜드 무선 청소기 Q808"])], out, run_day=RUN, date_to=DATE_TO,
                              ask=boom, log=log)
        j = json.loads((out / CJ.JUDGE_FILE).read_text(encoding="utf-8"))["a1"]
        check(any("⚠" in x and "AI 판정 실패" in x for x in logs) and not any(e["단계"] == CJ.STEP_AI for e in j.get("2", [])),
              "AI 실패 = ⚠ 로그 · AI 판정 기록 없음(다음 실행이 다시 물음)")
        check(not [r for r in rep.bizs[0].rows if r.vids == ["2"]][0].sel, "AI 실패한 날 = 개인으로 표시")


def _report_for_layout(out: Path):
    put_products(out, "a/1", [{"vid": "1", "name": "관리 상품"}, {"vid": "2", "name": "개인 상품"},
                              {"vid": "3", "name": "링크 없는 개인"}])
    put_inventory(out, "a/1", [{"vid": "1", "name": "관리 상품", "price": 10000, "pid": "P1"}])
    (out / CS.PID_STORE).write_text(json.dumps({"a/1": {"2": "P2"}}), encoding="utf-8")
    put_sales(out, "a/1", {"1": [1, 2, 3, 4, 5, 6, 7], "2": [0, 0, 0, 0, 0, 0, 9]})
    put_match(out, {"a/1": {"관리 상품": ["1"]}})
    accs = [acct("a/1", "사업[자]/1", "홍길동"), acct("fail1", "실패사업자"), acct("nodata", "자료없는사업자"),
            acct("m1", "두계정"), acct("m2", "두계정"), acct("dup", "사업[자]/1 ")]
    put_products(out, "m1", [{"vid": "m", "name": "m상품"}])
    put_products(out, "fail1", [{"vid": "f", "name": "어제 상품"}], day="2026-11-16")   # 어제 자료 = 쓰지 않아야 함
    (out / "_로그인실패.json").write_text(json.dumps({"fail1": {"date": "2026-11-17", "reason": "로그인 비밀번호 오류"},
                                                    "m2": {"date": "2026-11-17", "reason": "2단계 인증 필요"}},
                                                   ensure_ascii=False), encoding="utf-8")
    return ST.build_report(accs, out, run_day=RUN, date_to=DATE_TO, ask=no_ai, log=lambda m: None)


def t4_layout_xlsx():
    print("[T4] 엑셀 양식 — 시트 구성·링크·바탕색·날짜 순서·7일 합계·칸 폭·자료 없음 표시 — D-358 양식·칸 폭·⑦")
    from coupang_analytics.contractor_sheet_xlsx import build_workbook
    with tempfile.TemporaryDirectory() as d:
        rep = _report_for_layout(Path(d))
        wb = build_workbook(rep)
        names = wb.sheetnames
        check(names[0] == "요약" and len(names) == 1 + len(rep.bizs), f"시트 = 요약 + 사업자만 {names}")
        check(names[1] == "사업_자__1" and names[-1].startswith("사업_자__1") and names[-1] != names[1],
              "시트 이름 금지문자 → '_' · 겹치면 구분")
        check(all(len(n) <= 31 for n in names), "시트 이름 31자 이하")
        s = wb["요약"]
        links = {s.cell(r, 2).hyperlink.target for r in range(4, 4 + len(rep.bizs))}
        check(all(t.startswith("#'") and t[2:t.index("'!")].replace("''", "'") in names for t in links), "요약 링크 대상 시트가 모두 있음")
        titles = [s.cell(r, 2).value for r in range(4, 4 + len(rep.bizs))]
        check("실패사업자 (로그인 실패)" in titles and "자료없는사업자 (오늘 자료 없음)" in titles, f"자료 없음 표시 {titles}")
        check(any(t == "두계정 (m2 로그인 실패)" for t in titles), "2계정 사업자 = 어느 계정인지 함께")
        fail = next(b for b in rep.bizs if b.name == "실패사업자")
        check(not fail.rows and fail.total == 0, "로그인 실패 계정 = 어제 값을 쓰지 않음(줄 0)")
        sh = [c.value for c in s[3]]
        check(len(sh) == 12 and sh[4] == "전체 상품", "요약 머리글 12칸 · '전체 상품(등록상품)' → '전체 상품'(소유자 11-19)")
        sw = [s.column_dimensions[chr(65 + i)].width for i in range(12)]
        check(all(h.count("\n") <= 1 and all(_est(x) + 1 <= wd for x in h.split("\n")) for h, wd in zip(sh, sw)),
              "요약 머리글 = 1~2줄 · 줄마다 칸 폭 안(넘쳐서 3줄로 접히지 않음 · 소유자 11-19)")
        check(sw == [7, 28, 16, 26, 12, 9, 12, 12, 13, 13, 14, 11], "요약 칸 폭 = D-358 표 + 개인 상품·개인 0건 11→12")
        w = wb[names[1]]
        check(w["A1"].value == "◀ 요약으로" and w["A1"].hyperlink.target == "#'요약'!A1", "A1 = 요약으로 가는 링크")
        check(w["A2"].value.startswith("사업[자]/1") and "홍길동" in w["A2"].value, "제목 = 사업자 + 대표자")
        heads = [c.value for c in w[3]]
        check(heads[:8] == ["구분", "계정ID", "상품명 (클릭 → 쿠팡 상품 페이지)", "판매방식", "판매상태", "판매가\n(최저)",
                            "실구매가\n(즉시할인 후)", "그로스\n재고"], "사업자 머리글 8칸")
        check(heads[8:15] == ["11.16일", "11.15일", "11.14일", "11.13일", "11.12일", "11.11일", "11.10일"]
              and heads[15] == "7일\n합계", "날짜 = '11.16일' 꼴(소유자 11-19) · 최근이 왼쪽 7칸 · 7일 합계 = 오른쪽 끝")
        check([w.column_dimensions[chr(65 + i)].width for i in range(16)] == [9, 15, 50, 19, 11, 13, 14, 10] + [9] * 7 + [13],
              "사업자 칸 폭 = D-358 표(날짜 9 · 합계 13 · 상품명 50)")
        r4 = [w.cell(4, k).value for k in range(1, 17)]
        check(r4[0] == "셀독" and r4[8:15] == [7, 6, 5, 4, 3, 2, 1] and r4[15] == 28, "셀독 행 · 최근 판매가 왼쪽 · 합계 28")
        check(all(w.cell(4, k).fill.fgColor.rgb.endswith("EEE8FA") for k in range(1, 17)), "셀독 행 16칸 모두 바탕색")
        check(all(w.cell(r, k).fill.patternType is None for r in (5, 6) for k in range(1, 17)), "개인 행 바탕색 없음")
        check(w.cell(4, 3).hyperlink.target == "https://www.coupang.com/vp/products/P1?vendorItemId=1", "상품 링크 = productId + VID")
        check(w.cell(5, 3).hyperlink.target.endswith("/P2?vendorItemId=2"), "누적 상품ID 파일(N1)로 개인 상품 링크")
        check(w.cell(6, 3).hyperlink is None and w.cell(6, 3).value.endswith("(링크 없음 · 상품ID 미수집)"),
              "productId 없음 = 검색 링크 대신 '링크 없음' 표시(조용한 대체 없음)")
        check(w.cell(5, 8).value == "－", "판매자배송 그로스 재고 '－'")
        check(w.freeze_panes == "D4" and s.freeze_panes == "C4", "틀 고정 3행·C열(요약 B열)")
        kinds = [r.type for ws_ in wb.worksheets for cf in ws_.conditional_formatting for r in cf.rules]
        check(kinds and set(kinds) == {"cellIs"} and set(kinds) <= GC.SUPPORTED_CF,
              f"조건부 서식 = 재고 0 빨강(값 비교)만 · 데이터 막대·색 농도 없음(소유자 11-19 '7일합계항목 … 동일하게 해줘' · "
              f"'요약 시트도 다른 항목과 동일하게 해줘' = 바탕은 줄 색 그대로) {sorted(set(kinds))}")
        check(w.row_dimensions[3].height == 40 and w.row_dimensions[4].height == 20 and s.row_dimensions[4].height == 20,
              "줄 간격 = 데이터 줄 20pt(소유자 11-19 '줄간격 조금 넓혀줘' · 사업자·요약 둘 다) · 머리글 40pt(2줄)")
        check(all(h.count(chr(10)) <= 1 for h in heads), "사업자 머리글도 2줄 이하")


def t5_stage_and_gsheet():
    print("[T5] 단계 — 파일 위치·날짜 지정 생략·실패해도 계속 · 구글 ⚠/❌/교체·폭 픽셀·탭 링크 — D-358 ⑤⑥⑩")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        put_products(out, "a1", [{"vid": "1", "name": "관리 상품"}])
        put_match(out, {"a1": {"관리 상품": ["1"]}})
        il = type("IL", (), {"accounts": [acct("a1", "사업자A")]})()
        logs, log = _logs()
        p = ST.run_stage(il, date_to=DATE_TO, run_day=RUN, out_dir=out, on_log=log, gsheet_url="", ask=no_ai)
        check(p == out / "계약자별상품현황" / "셀독_계약자별상품현황_261117.xlsx" and p.is_file(), f"파일 = {p}")
        check(any("⚠" in x and "링크 미설정" in x for x in logs), "구글 주소 없음 = ⚠ 생략 · PC 파일은 만듦")
        logs, log = _logs()
        check(ST.run_stage(il, date_to=DATE_TO, run_day=RUN, out_dir=out, on_log=log, designated=True) is None
              and any("날짜 지정" in x for x in logs), "날짜 지정 실행 = 만들지 않음")
        (out / CJ.JUDGE_FILE).write_text("{깨짐", encoding="utf-8")
        logs, log = _logs()
        check(ST.run_stage(il, date_to=DATE_TO, run_day=RUN, out_dir=out, on_log=log, gsheet_url="") is None
              and any("❌" in x and "만들기 실패" in x for x in logs), "판정표 손상 = ❌ 줄 · 예외 안 올림(②③ 계속) · 판정표 안 덮어씀")
        check((out / CJ.JUDGE_FILE).read_text(encoding="utf-8") == "{깨짐", "손상 판정표 그대로(옛 판정 안 잃음)")
        check(ST.run_stage(type("IL", (), {"accounts": []})(), date_to=DATE_TO, out_dir=out, on_log=lambda m: None) is None,
              "계정 없음 = 만들지 않음")
    from coupang_analytics.contractor_sheet_xlsx import build_workbook
    from coupang_analytics.gsheet_api import GSheetError
    with tempfile.TemporaryDirectory() as d:
        wb = build_workbook(_report_for_layout(Path(d)))

    class Fake:
        spreadsheet_id = "DOC"

        def __init__(self, url, fail=None):
            self.batches, self.fail = [], fail

        def meta(self, refresh=False):
            if self.fail:
                raise GSheetError(self.fail)
            return {"sheets": [{"properties": {"sheetId": 0, "title": "요약"}},
                               {"properties": {"sheetId": 7, "title": "대장에서 사라진 사업자"}}]}

        def batch_update(self, reqs):
            self.batches.append(reqs)
    made: list = []

    def factory(url):
        made.append(Fake(url))
        return made[-1]
    logs, log = _logs()
    check(ST.push_gsheet(wb, "https://docs.google.com/spreadsheets/d/DOC/edit", log, factory), "정상 반영 = True")
    f = made[0]
    adds = [r for r in f.batches[0] if "addSheet" in r]
    check(len(adds) == len(wb.sheetnames) and all(r["addSheet"]["properties"]["title"].startswith(GC.TMP_PREFIX) for r in adds),
          "새 탭은 임시 이름으로 먼저 만듦")
    swap = f.batches[-1]
    dels = [r["deleteSheet"]["sheetId"] for r in swap if "deleteSheet" in r]
    ren = [r["updateSheetProperties"]["properties"]["title"] for r in swap if "updateSheetProperties" in r]
    check(dels == [0, 7] and ren == wb.sheetnames, "마지막 한 번에 옛 탭 전부 지우고(사라진 사업자 포함) 새 탭 이름으로 교체")
    check(swap is f.batches[-1] and len(f.batches) == 2 + len(wb.sheetnames), "내용은 교체 전에 모두 씀(끊겨도 옛 탭 유지)")
    summ = f.batches[1]
    px = [r["updateDimensionProperties"]["properties"]["pixelSize"] for r in summ if "updateDimensionProperties" in r
          and r["updateDimensionProperties"]["range"]["dimension"] == "COLUMNS"]
    check(px == [w * 7 + 5 for w in [7, 28, 16, 26, 12, 9, 12, 12, 13, 13, 14, 11]], f"요약 칸 폭 픽셀 = 엑셀 폭 × 7 + 5 {px[:4]}")
    biz = f.batches[2]
    bpx = [r["updateDimensionProperties"]["properties"]["pixelSize"] for r in biz if "updateDimensionProperties" in r
           and r["updateDimensionProperties"]["range"]["dimension"] == "COLUMNS"]
    check(bpx[8] == 68 and bpx[15] == 96 and bpx[2] == 355, "날짜 칸 9 → 68픽셀 · 합계 13 → 96 · 상품명 50 → 355")
    gids = {t: r["addSheet"]["properties"]["sheetId"] for t, r in zip(wb.sheetnames, adds)}
    a1 = next(r for r in biz if "updateCells" in r)["updateCells"]["rows"][0]["values"][0]["userEnteredValue"]["formulaValue"]
    check(f"gid={gids['요약']}" in a1 and "DOC" in a1, f"A1 '◀ 요약으로' = 요약 탭 링크(파일 전체 주소) {a1[:60]}")
    b4 = next(r for r in summ if "updateCells" in r)["updateCells"]["rows"][3]["values"][1]["userEnteredValue"]["formulaValue"]
    check(f"gid={gids[wb.sheetnames[1]]}" in b4, "요약 사업자 이름 = 그 사업자 탭 링크")
    check(min(gids.values()) > 7, "새 gid 는 옛 탭과 겹치지 않음")
    rules = [r["addConditionalFormatRule"]["rule"] for r in summ + biz if "addConditionalFormatRule" in r]
    check(any(g.get("booleanRule", {}).get("condition", {}).get("type") == "NUMBER_EQ" for g in rules)
          and not any("gradientRule" in g for g in rules),
          "구글 = 같은 규칙을 API 로 직접(재고 0 빨강 booleanRule · 색 농도 gradientRule 없음)")
    rows = {r["updateDimensionProperties"]["range"]["startIndex"]: r["updateDimensionProperties"]["properties"]["pixelSize"]
            for r in biz if "updateDimensionProperties" in r and r["updateDimensionProperties"]["range"]["dimension"] == "ROWS"}
    check(rows.get(2) == 53 and rows.get(3) == 26, f"구글 줄 높이 = 머리글 40pt → 53px(2줄 안 잘림) · 데이터 20pt → 26px {rows}")
    from openpyxl.formatting.rule import DataBarRule
    wb["요약"].conditional_formatting.add("K4:K5", DataBarRule(start_type="min", end_type="max", color="9C7FD6"))
    logs, log = _logs()
    check(not ST.push_gsheet(wb, "u", log, factory) and any("❌" in x and "dataBar" in x for x in logs),
          "구글이 지원 안 하는 서식(데이터 막대)이 다시 들어오면 = ❌ 로 멈춤(조용히 빼지 않음)")
    logs, log = _logs()
    check(not ST.push_gsheet(wb, "u", log, lambda url: Fake(url, fail="HTTP 403 권한 없음")) and
          any("❌" in x and "403" in x for x in logs), "403 = ❌ 로그 · False(실행 계속)")


def t6_links_n1_n2_n3():
    print("[T6] N1 상품ID 누적 · N2 링크 추가 조회 대상 · N3 판매상태 보관 — 설계안 5절 · D-358 ⑧")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        check(CS.merge_pid_store(out, "a", {"1": "P1"}) == 1 and CS.merge_pid_store(out, "a", {"2": "P2"}) == 1,
              "VID 새로 생기면 덧붙임")
        CS.merge_pid_store(out, "b", {"9": "P9"})
        check(CS.load_pid_store(out) == {"a": {"1": "P1", "2": "P2"}, "b": {"9": "P9"}}, "옛 VID·다른 계정 안 지움")
        check(CS.merge_pid_store(out, "a", {"1": "P1"}) == 0, "같은 값 = 다시 안 씀")
    small = [(f"L{i}", f"상품{i}", "ON_SALE", [f"v{i}"]) for i in range(5)] + [("Lx", "판매중지", "SUSPENDED", ["vx"])]
    check(CS.link_targets(small, {"v0"}, set()) == ["L1", "L2", "L3", "L4"],
          "10개 미만 계정 = productId 모르는 판매중 상품 전부(아는 것·판매중지 개인 뺌)")
    big = [(f"L{i}", f"상품{i}", "ON_SALE", [f"v{i}"]) for i in range(12)] + [("Ls", "관리", "SUSPENDED", ["vs"])]
    check(CS.link_targets(big, set(), {"vs"}) == ["Ls"], "10개 이상 계정 = 대장 VID 가 든 상품만(0건 개인은 안 나오므로 조회 안 함)")
    body = json.dumps({"success": True, "data": {"pagination": {"totalPages": 1}, "productList": [
        {"vendorInventoryId": 1, "productName": "x", "productStatus": "SUSPENDED",
         "vendorInventoryItems": [{"vendorItemId": 5, "itemName": "o", "registrationType": "NORMAL", "salePrice": 1}]}]}})
    check(PI.extract([body])["상품"][0].get("productStatus") == "SUSPENDED", "상품정보 보관에 판매상태(productStatus) 칸")
    # ① 같은 세션 안 조회(pipeline_sales._contractor_pids) — 가짜 page · 새 로그인 없음
    from types import SimpleNamespace as NS
    from coupang_analytics import collector, pipeline_sales
    asked: list = []
    orig = collector.fetch_product_ids
    collector.fetch_product_ids = lambda page, ids, log=None: (asked.append(list(ids)), {"v2": "P2"})[1]
    try:
        with tempfile.TemporaryDirectory() as d:
            lst = [NS(vendor_inventory_id=f"L{i}", product_name=f"상품{i}", product_status="ON_SALE",
                      options=[NS(vendor_item_id=f"v{i}")]) for i in range(3)]
            a = acct("acc", "사업자")
            pipeline_sales._contractor_pids(NS(page="PAGE"), a, lst, {"v0": "P0"}, set(), Path(d) / "_매칭고정.json",
                                            lambda m: None)
            check(asked == [["L1", "L2"]], f"모르는 등록상품만 같은 세션 page 로 GET {asked}")
            check(CS.load_pid_store(d) == {"acc": {"v0": "P0", "v2": "P2"}}, "오늘 아는 것 + 받은 것 누적")
            asked.clear()
            pipeline_sales._contractor_pids(NS(page="PAGE"), a, lst, {}, set(), None, lambda m: None)
            check(not asked, "도구·핀(anchor_file 없음) = 조회·저장 안 함")
    finally:
        collector.fetch_product_ids = orig


def t7_stage_order():
    print("[T7] ① 판매수집 직후 실행은 없앰(①→②→③ 사이에 현황 없음) — D-361 ①(D-358 ⑥ 대체)")
    import coupang_analytics.pipeline_stages as stg
    check(not hasattr(stg, "contractor_report_stage"), "단계 조립에 계약자 현황 호출 없음")
    keep = {k: getattr(stg, k) for k in ("run_full", "select_keywords_stage", "track_ranks_stage", "push_ledger_inventory",
                                        "push_company_stock", "write_run_stage", "mark_run_day", "read_last_run_stage")}
    calls: list = []
    real_run_stage = ST.run_stage
    try:
        stg.run_full = lambda il, **k: calls.append("①")
        stg.select_keywords_stage = lambda *a, **k: calls.append("②")
        stg.track_ranks_stage = lambda **k: calls.append("③")
        stg.push_ledger_inventory = stg.push_company_stock = lambda *a: None
        stg.write_run_stage = lambda s, **k: None
        stg.mark_run_day = lambda *a, **k: None
        stg.read_last_run_stage = lambda: None
        ST.run_stage = lambda *a, **k: calls.append("현황")
        kw = dict(ai_key="k", naver=None, date_from=DATE_TO, date_to=DATE_TO, date_label=DATE_TO,
                  get_password=lambda a: None, carry=True, on_log=lambda m: None)
        stg.run_stages(None, stg.StagePlan(), **kw)
        check(calls[:3] == ["①", "②", "③"] and "현황" not in calls, f"①→②→③ · 현황 없음 {calls}")
        calls.clear()
        stg.run_stages(None, stg.StagePlan(keywords=False, ranks=False), **kw)
        check(calls == ["①"], f"① 단독 실행도 현황 안 만듦 {calls}")
    finally:
        ST.run_stage = real_run_stage
        for k, v in keep.items():
            setattr(stg, k, v)


def _put_sales_days(out: Path, acc: str, days: dict[str, dict[str, int]]) -> None:
    """days = {날짜: {vid: 판매수량}} — 빈 dict = 그날 0건 기록 · 키 없는 날 = 판매 기록 없음."""
    rec = {d: {"옵션": {v: {"판매수량": q} for v, q in by.items()}} for d, by in days.items()}
    p = out / "판매분석_일별" / acc / "2026-11.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")


def t9_daily_0600():
    print("[T9] 실행 = 매일 06:00 한 번 · 06:00 뒤 켜면 그날 몫 없을 때 한 번 · 최근 7일 = 실행일 전날까지 — D-361 ①②")
    from datetime import datetime
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        # 11-20 00:10 ① 판매수집이 남긴 자료(파일 날짜 = 수집한 날 11-20 · D-362) → 11-20 06:00 실행이 읽어야 함
        put_products(out, "a1", [{"vid": "1", "name": "관리 상품"}], day="2026-11-19")   # 전날 회차 자료 = 안 읽음
        put_products(out, "a1", [{"vid": "1", "name": "관리 상품"}], day="2026-11-20")
        put_match(out, {"a1": {"관리 상품": ["1"]}})
        _put_sales_days(out, "a1", {f"2026-11-{x:02d}": {"1": x - 12} for x in range(13, 20)})
        il = type("IL", (), {"accounts": [acct("a1", "사업자A")]})()
        check(not ST.daily_due(datetime(2026, 11, 20, 5, 59), out), "05:59 = 아직 아님")
        check(ST.daily_due(datetime(2026, 11, 20, 6, 0), out), "06:00 = 실행할 때")
        logs, log = _logs()
        p = ST.run_daily(il, now=datetime(2026, 11, 20, 6, 0), out_dir=out, on_log=log, gsheet_url="", ask=no_ai)
        check(p == out / "계약자별상품현황" / "셀독_계약자별상품현황_261120.xlsx" and p.is_file(), f"파일 이름 = 실행일 {p}")
        check(any("11.13~11.19" in x for x in logs), f"7일 = 11-13~11-19(실행일 전날까지) {[x for x in logs if '기간' in x]}")
        check(any("셀독 1" in x and "자료 없음 표시 0" in x for x in logs),
              "그날 00:10 ① 자료(파일 날짜 11-20)를 읽음 — '자료 없음' 아님")
        from openpyxl import load_workbook
        w = load_workbook(p).worksheets[1]
        check([w.cell(4, k).value for k in range(9, 17)] == [7, 6, 5, 4, 3, 2, 1, 28], "최근(11-19)이 왼쪽 · 합계 28")
        check(not ST.daily_due(datetime(2026, 11, 20, 6, 1), out) and not ST.daily_due(datetime(2026, 11, 20, 23, 0), out),
              "같은 날 두 번 안 돎")
        check(ST.daily_due(datetime(2026, 11, 21, 6, 0), out), "다음 날 06:00 = 다시")
        check(ST.daily_due(datetime(2026, 11, 22, 14, 30), out), "06:00 에 앱이 꺼져 있었으면 켠 뒤 그날 한 번")
        # 06:00 을 놓쳐 낮에 켜도 = 그날 00:10 ① 자료(06:00 과 같은 회차) · 전날 자료만 있으면 '자료 없음'
        logs, log = _logs()
        pushed = []

        def fake_client(url):              # 올리려 하면 기록만(실제 구글 호출 없음 · push_gsheet 는 ValueError 를 ❌ 로그로 받음)
            pushed.append(url)
            raise ValueError("시험 — 올리지 않음")
        p21 = ST.run_daily(il, now=datetime(2026, 11, 21, 14, 0, 5), out_dir=out, on_log=log, gsheet_url="URL", ask=no_ai,
                           client_factory=fake_client)
        check(not any("자료 없음 표시 0" in x for x in logs), f"그날 00:10 자료 없음 = 전날 자료로 안 채움 {logs[-2:]}")
        # 소유자 11-20: 운용 PC 새 판 설치 첫날 낮 — 모든 계정이 자료 없음인 빈 표가 구글시트를 덮어씀 → 덮어쓰지 않음
        check(p21 is None and not pushed and not (out / "계약자별상품현황" / "셀독_계약자별상품현황_261121.xlsx").exists()
              and any("❌" in x and "모든 계정" in x for x in logs),
              f"모든 계정 자료 없음 = PC 파일·구글시트 안 만듦(전날 내용 그대로) · ❌ 로그 {p21} {pushed} {logs[-2:]}")
        put_products(out, "a1", [{"vid": "1", "name": "관리 상품"}], day="2026-11-23")
        logs, log = _logs()
        ST.run_daily(il, now=datetime(2026, 11, 23, 14, 0, 5), out_dir=out, on_log=log, gsheet_url="", ask=no_ai)
        check(any("셀독 1" in x and "자료 없음 표시 0" in x for x in logs), f"놓친 날 낮 = 그날 00:10 ① 자료 {logs[-2:]}")
        logs, log = _logs()
        check(ST.run_daily(type("IL", (), {"accounts": []})(), now=datetime(2026, 11, 22, 14, 30), out_dir=out,
                           on_log=log) is None and not ST.daily_due(datetime(2026, 11, 22, 15, 0), out),
              "만들지 못한 날도 기록 — 같은 날 되풀이 안 함")


def t9b_wait_sales():
    print("[T9b] 06:00 에 ① 판매수집이 아직 돌면 = 끝날 때까지 미룸(기준일 섞임 방지) · 안 돌면 바로 — 통제 세션 11-19 ④")
    import os
    import time as _time
    from datetime import datetime
    from datetime import timedelta
    from coupang_analytics.pipeline_paths import _progress_path, _run_stage_path
    from coupang_analytics.settlement_watch import cycle_window
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        now = datetime.now()
        start = cycle_window(now)[0]
        # 소유자 11-20: 이번 회차 ① 완료 기록이 없으면(설치 첫날 낮·00:10 실패·밤새 꺼짐) 지난 회차 자료뿐 → 미룸
        why = ST.wait_reason(now, out)
        check("완료 기록 없음" in why, f"단계 기록 없음 = 이번 회차 ① 안 끝남 → 미룸 {why!r}")
        stage = _run_stage_path(out)
        stage.write_text(json.dumps({"stage": "done", "at": (start - timedelta(hours=1)).isoformat()}), encoding="utf-8")
        check("완료 기록 없음" in ST.wait_reason(now, out), "지난 회차 ① 완료 = 미룸")
        stage.write_text(json.dumps({"stage": "sales", "at": start.isoformat()}), encoding="utf-8")
        check(ST.wait_reason(now, out) == "", "이번 회차 ① 완료 + 진행 파일 없음 = 기다리지 않음")
        prog = _progress_path(out)
        prog.parent.mkdir(parents=True, exist_ok=True)
        prog.write_text("{}", encoding="utf-8")
        why = ST.wait_reason(now, out)
        check("판매수집" in why, f"방금 갱신된 진행 파일 = ① 도는 중 → 미룸 {why!r}")
        old = _time.time() - 3600
        os.utime(prog, (old, old))
        check(ST.wait_reason(now, out) == "", "1시간 갱신 없음 = ① 멈춘 것(미완료 남김) → 기다리지 않음")


def t10_blank_days():
    print("[T10] 판매 기록이 아예 없는 날 = 그 날 칸만 공란 · 0건 기록 = '-' · 합계는 있는 날만 · 엑셀·구글 같게 — D-361 ③")
    from coupang_analytics.contractor_sheet_xlsx import build_workbook
    from coupang_analytics.gsheet_stats import worksheet_to_requests
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        put_products(out, "a1", [{"vid": "1", "name": "관리 상품"}, {"vid": "2", "name": "개인 상품"}])
        put_products(out, "a2", [{"vid": "5", "name": "다른 계정 상품"}])
        put_match(out, {"a1": {"관리 상품": ["1"]}})
        days = {x: {"1": 2, "2": 1} for x in DAYS}
        days["2026-11-15"] = {}                    # 0건 기록
        del days["2026-11-16"]                     # 기록 없음(그날 정산 받기 늦음·실패)
        _put_sales_days(out, "a1", days)
        _put_sales_days(out, "a2", {x: {"5": 1} for x in DAYS})
        rep = ST.build_report([acct("a1", "사업자A"), acct("a2", "사업자A")], out, run_day=RUN, date_to=DATE_TO,
                              ask=no_ai, log=lambda m: None)
        rows = {r.name: r for r in rep.bizs[0].rows}
        sel, own, other = rows["관리 상품"], rows["개인 상품"], rows["다른 계정 상품"]
        check(sel.d7 == [2, 2, 2, 2, 2, 0, None] and sel.s7 == 10, f"셀독: 빈 날 None · 0건 0 · 합계 = 있는 날만 {sel.d7}")
        check(own.d7 == [1, 1, 1, 1, 1, 0, None] and own.s7 == 5, f"개인도 같음 {own.d7}")
        check(other.d7 == [1] * 7 and other.s7 == 7, "다른 계정(같은 사업자)은 그 날도 그대로")
        wb = build_workbook(rep)
        w = wb.worksheets[1]
        r = next(i for i in range(4, 8) if str(w.cell(i, 3).value).startswith("관리 상품"))
        check(w.cell(r, 9).value is None and w.cell(r, 10).value == 0 and w.cell(r, 16).value == 10,
              "엑셀: 11.16일 칸 공란 · 11.15일 = 0('-' 서식) · 합계 10")
        check(w.cell(r, 10).number_format.endswith('"-"'), "0건 = '-' 서식 그대로")
        s = wb["요약"]
        check(s.cell(4, 9).value == 10 and s.cell(4, 10).value == 12, "요약 7일 판매 = 있는 날만 합(셀독 10 · 개인 12)")
        upd = next(x for x in worksheet_to_requests(w, 1) if "updateCells" in x)["updateCells"]["rows"][r - 1]["values"]
        check("userEnteredValue" not in upd[8] and upd[9]["userEnteredValue"] == {"numberValue": 0},
              "구글: 빈 날 = 값 없음 · 0건 = 0(같은 서식)")


def t8_speed():
    print("[T8] 성능 — 큰 계정(상품 9,600개) 포함 1분 이내 — 설계안 8절 7")
    from coupang_analytics.contractor_sheet_xlsx import build_workbook
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        put_products(out, "big", [{"vid": str(i), "name": f"대량 상품 {i}"} for i in range(9600)])
        put_sales(out, "big", {str(i): [0, 0, 0, 0, 0, 0, i % 3] for i in range(9600)})
        put_match(out, {"big": {"대량 상품 1": ["1"]}})
        t = time.time()
        rep = ST.build_report([acct("big", "큰사업자")], out, run_day=RUN, date_to=DATE_TO, ask=no_ai, log=lambda m: None)
        build_workbook(rep).save(out / "x.xlsx")
        sec = time.time() - t
        check(sec < 60 and rep.bizs[0].total == 9600, f"{sec:.1f}초 · 전체 9,600 · 표시 {len(rep.bizs[0].rows)}")


def main() -> int:
    for t in (t1_ten_rule, t2_values_and_tiers, t3_ai_judge, t4_layout_xlsx, t5_stage_and_gsheet, t6_links_n1_n2_n3,
              t7_stage_order, t8_speed, t9_daily_0600, t9b_wait_sales, t10_blank_days):
        t()
    print(f"\n결과: {'통과' if not FAILS else f'실패 {len(FAILS)}건'}")
    for f in FAILS:
        print("  ✘", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
