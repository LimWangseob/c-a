"""위탁정산서 엑셀 — 계정 정산서 1개(1쪽 A~G·참고·부속 시트) + 전체 요약. T-25 이관(옛 `statement_managed.py` 683~912줄 ·
행동 불변 · 발행일은 ctx.issued(옛 = 실행 날짜)).
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from pathlib import Path

import openpyxl

from coupang_analytics import settlement_additional_pay as AP
from coupang_analytics import settlement_experience as XP
from coupang_analytics import settlement_statement_source as SRC
from coupang_analytics.settlement_statement_account import FAST, STS, SVC
from coupang_analytics.settlement_statement_sheets import (
    NOTES, PCT, PENDING_NOTE, PLAIN, SHIP_LABEL, SIGNED, cell, flow, managed_lines, merge, section, shown, table)


def _head(ws, ctx, a: dict) -> int:
    info = a["info"]
    for col, w in zip("ABCDEF", (2, 40, 20, 20, 20, 38)):
        ws.column_dimensions[col].width = w
    ws.sheet_view.showGridLines = False
    months = sorted(m for m, (s, _e) in a["mmon"].items() if round(s))
    merge(ws, 1, 2, 6, f"{info['사업자']} (대표 {info['대표자']})님 쿠팡 판매 정산내역서", bold=True, size=20, fill="title", align="center")
    ws.row_dimensions[1].height = 38
    period = f"{months[0][:4]}-{months[0][4:]} ~ {ctx.basis}" if months else "-"
    r = 2
    for k, val in (("사업자", f"{info['사업자']} (대표 {info['대표자']})"), ("쿠팡 계정", a["aid"]), ("판매 기간", period),
                   ("기준일", f"{ctx.basis}  (발행 {ctx.issued})")):     # 진하게·항목마다 줄(소유자 2026-10-27)
        cell(ws, r, 2, k, bold=True, fill="soft")
        note = k == "판매 기간" and a["start_note"]           # D-185 — 다르거나 계약 없음 = 확인 필요(줄 위치는 그대로·칸 안 둘째 줄)
        merge(ws, r, 3, 6, f"{val}\n{a['start_note']}" if note else val, bold=True, wrap=bool(note))
        if note:
            ws.row_dimensions[r].height = 34
        r += 1
    return r - 1                             # 범위 줄 삭제(소유자 2026-10-28) — 제외 상품은 '제외한 상품' 시트


def _neg_note(v: dict) -> tuple[list, str]:
    # 입금 완료·예정 칸이 마이너스 = 비용과 판매대금이 다른 지급 회차에 들어감 — 그 칸일 때만 사유(소유자 2026-10-28 1안)
    neg = [k for k, x in (("입금 완료", v["지급 완료"]), ("입금 예정", v["예정"] + v["보류"])) if round(x) < 0]
    note = (f"※ {'·'.join(neg)} 마이너스 = 광고비·물류비 등 비용이 그 지급에서 먼저 빠지고, 관리 상품 판매대금은 "
            f"{'다른' if len(neg) > 1 else ('다음' if neg[0] == '입금 완료' else '앞선')} 지급에 들어감 — "
            "계정 통장 입금은 다른 상품 대금에서 빠져 마이너스 아님 · 최종 지급액 G 기준") if neg else ""
    return neg, note


def _cards(ws, r: int, v: dict, neg: list) -> int:
    # 1쪽 = 쿠팡 매출내역과 같은 기호 흐름(소유자 2026-10-28): 큰 숫자마다 바로 아래에 '그 숫자 자체의 내역' 묶음.
    # A 판매금액 = 판매액 + 배송비 − 취소 · E 정산대상액 = A − B 쿠폰 − C 수수료 + D 쿠팡 지원 할인 · F 쿠팡 공제 · G 최종 지급액 = E − F
    cards = (("A 판매금액", v["sales"]), ("E 정산대상액", v["settle"]), ("F 쿠팡 공제", -v["cost"]), ("G 최종 지급액", v["pay"]))
    r += 2
    for i, (x, val) in enumerate(cards):
        cell(ws, r, 2 + i, x, bold=True, fill="card", align="center")
        cell(ws, r + 1, 2 + i, val, bold=True, size=16, fill="card", fmt=PLAIN, align="center")
    cell(ws, r, 6, "비고 (참고)", bold=True, fill="soft", align="center")         # G 의 입금 완료·예정 — 참고(소유자 2026-10-28)
    cell(ws, r + 1, 6, f"입금 완료 {v['지급 완료']:,}\n입금 예정 {v['예정'] + v['보류']:,}"
         + (f"(보류 {v['보류']:,})" if v["보류"] else "") + (f"\n(입금 완료 중 빠른정산 {v['fast']:,})" if v["fast"] else "")
         + ("\n※ 마이너스 사유는 아래 G 설명" if neg else ""), fill="soft", align="center", wrap=True)
    ws.row_dimensions[r + 1].height = max(34, 16 * (str(ws.cell(r + 1, 6).value).count("\n") + 1))   # 비고 줄 수만큼
    merge(ws, r + 2, 2, 6, "흐름:  A 판매금액 − B 판매자 할인쿠폰 − C 판매수수료 + D 쿠팡 지원 할인 = E 정산대상액 − F 쿠팡 공제 = G 최종 지급액",
          bold=True, fill="scope", align="center")
    return r


def block(ws, r, title, heads, rows):
    """제목 + 머리줄 + 줄들. rows = (항목, 칸1, 칸2, 합계, 설명, 종류) — 종류 'end' = 결과 줄(진하게·바탕)."""
    r = section(ws, r, title)
    for j, h in enumerate(("",) + heads + ("설명",)):
        cell(ws, r, 2 + j, h, bold=True, fill="sec", align="center")
    r += 1
    for label, c1, c2, tot, note, kind in rows:
        fill, bold = ("big", True) if kind == "end" else (None, kind == "start")
        cell(ws, r, 2, label, bold=bold, fill=fill)
        for j, x in enumerate((c1, c2, tot)):
            cell(ws, r, 3 + j, x, bold=bold, fill=fill, fmt=PLAIN if bold else SIGNED, align="right")
        cell(ws, r, 6, note, fill=fill, wrap=True)
        r += 1
    return r


def _blocks_ae(ws, r: int, a: dict, v: dict) -> int:
    tm, u_ = a["tm"], v["u_sales"]
    r = block(ws, r + 4, "A 판매금액 내역 — 고객이 결제한 금액", ("정산 확정", "정산 예정", "합계"), (
        ("a 상품 판매액", v["gross"], None, v["gross"], "관리 상품 판매(쿠팡 정산 자료 주문 줄)", None),
        ("b 배송비", v["ship"], None, v["ship"], "고객이 낸 배송비(같은 주문·반품 상품 기준)", None),
        ("c 취소·반품", v["refund"], None, v["refund"], "판매 뒤 취소·반품된 금액", None),
        ("정산 예정 판매 (취소 반영 합계)", None, u_, u_, PENDING_NOTE,
         None),
        ("A 판매금액", v["c_sales"], u_, v["sales"], "✔ a + b + c (+ 정산 예정) · 위 A", "end")))
    return block(ws, r + 1, "E 정산대상액 = A − B − C + D", ("정산 확정", "정산 예정", "합계"), (
        ("A 판매금액", v["c_sales"], u_, v["sales"], "위 A 판매금액 내역", "start"),
        ("B 판매자 할인쿠폰", -round(tm["coupon"]), None, -round(tm["coupon"]), "우리가 부담한 쿠폰 할인", None),
        ("C 판매수수료", -round(tm["fee"]), None, -round(tm["fee"]), "카테고리별 수수료(부가세 포함)", None),
        ("D 쿠팡 지원 할인", -round(tm["other"]), None, -round(tm["other"]), "쿠팡이 부담한 할인 — 우리 몫에 더해짐", None),
        ("B·C·D 정산 예정분 합계", None, -v["u_cost"], -v["u_cost"], PENDING_NOTE, None),
        ("E 정산대상액", v["c_settle"], v["u_settle"], v["settle"], "✔ 칸마다 위 줄 합계 · 위 E", "end")))


def _blocks_fg(ws, r: int, a: dict, v: dict, neg: list, neg_note: str) -> int:
    D, share = a["D"], a["share"]
    frows = []
    fast_row = next(((c, total) for label, c, total in v["tbl"][1:] if label == FAST), None)
    for label, c, total in v["tbl"][1:]:
        if label == FAST:
            continue
        sr = share[label]
        frows.append((label, c["지급 완료"], c["예정"] + c["보류"], total,
                      f"{NOTES.get(label, '')} · 계정 전체 {abs(D[label]):,.0f}원 중 {sr[0]:.1%} ({sr[2]})", None))
    f_done = sum(x[1] for x in frows)
    f_next = sum(x[2] for x in frows)
    r = block(ws, r + 1, "F 쿠팡 공제 내역 — 쿠팡이 지급할 때 뺀 돈", ("공제 완료분", "공제 예정분", "합계"), tuple(frows) + (
        ("F 쿠팡 공제", f_done, f_next, -v["cost"], "✔ 칸마다 위 줄 합계 · 위 F", "end"),))
    e = v["tbl"][0][1]
    fast_rows = ((
        ("빠른정산 상환", fast_row[0]["지급 완료"], fast_row[0]["예정"] + fast_row[0]["보류"], fast_row[1],
         "셀러월렛 빠른정산으로 먼저 받은 돈을 쿠팡이 정산에서 돌려받음", None),
        ("빠른정산으로 먼저 받은 돈", v["fast"], 0, v["fast"], "셀러월렛(하나은행 계좌)으로 이미 받은 돈 → 입금 완료", None)) if fast_row else ())
    return block(ws, r + 1, "G 최종 지급액 = E − F (입금 완료 + 입금 예정)", ("입금 완료", "입금 예정" + ("(보류 포함)" if v["보류"] else ""), "합계"), (
        ("E 정산대상액", e["지급 완료"], e["예정"] + e["보류"], v["settle"], "쿠팡 지급 줄마다 그 판매 달의 관리 상품 비율로 나눔", "start"),
        ("F 쿠팡 공제", f_done, f_next, -v["cost"], "위 F 쿠팡 공제 내역", None)) + fast_rows + (
        ("G 최종 지급액", v["지급 완료"], v["예정"] + v["보류"], v["pay"], "✔ 위 G · 입금 완료 = 통장에 들어온 돈 · 입금 예정 = 쿠팡이 정해 둔 "
         "다음 지급(바뀔 수 있음)" + (f" · 그중 보류 {v['보류']:,}" if v["보류"] else "") + ("\n" + neg_note if neg else ""), "end"),))


def _refs(ws, r: int, ctx, a: dict) -> tuple[int, list]:
    info = a["info"]
    r += 2                                   # 정산내역과 참고 사이 간격·구분 줄(소유자 2026-10-28)
    merge(ws, r, 2, 6, "▼ 아래는 참고 자료입니다 — 위 정산 금액(A~G)에 들어가지 않습니다", bold=True, fill="ref", align="center")
    ws.row_dimensions[r].height = 26
    r += 1
    fav, add = a["fav"], a["add"]                     # 별도 입금 = 있을 때만 표시(소유자 2026-10-28)
    extra_in = [("우대수수료 환급", round(fav[0]), f"쿠팡페이가 대표계좌로 직접 · 주문 → 상품 · 계정 전체 {fav[1]:,.0f}원"
                 + (f" · {fav[2]}" if fav[2] else "")) for _ in [0] if fav and round(fav[0])]
    if add["상태"] == "있음" and round(a["addm"][0]):
        extra_in.append(("추가지급", round(a["addm"][0]), f"{add['메모']} · 계정 전체 {a['addm'][1]:,.0f}원"))
    if extra_in:
        r = section(ws, r + 1, "참고. 쿠팡 정산 밖 별도 입금 (관리 상품 몫 · 위 G 와 별도)")
        for label, amt, note in extra_in:
            r = flow(ws, r, label, amt, note)
    xby, _ = XP.assign(ctx.xrows, [(info["사업자"], info["대표자"])])
    xs = [x for x in XP.lines(xby.get(info["사업자"], [])) if x["고객 부담"] or x["우리 부담"]]
    if xs:
        xt = XP.totals(xs)
        r = section(ws, r + 1, "참고. 외부 마케팅 대행비 (위 금액에서 빼지 않음)")
        r = flow(ws, r, "고객(계약자) 부담", xt["완료 고객 부담"], "완료된 외부 마케팅 대행(리뷰비·택배대행비·상품금액) · 상세는 '외부 마케팅 대행비' 시트")
        r = flow(ws, r, "회사 부담", xt["완료 우리 부담"], "")
    fin = a["fin"]
    r = section(ws, r + 1, "참고. 쿠팡 계정 전체 (관리 밖 상품 포함 · 통장과 맞춰 볼 때)", fill="ref")
    r = flow(ws, r, "계정 전체 판매금액", a["t"]["sales"] + a["u_sales"], "", fill="ref")
    r = flow(ws, r, "계정 전체 쿠팡 정산금액", a["settle_all"], "", fill="ref")
    r = flow(ws, r, "계정 전체 입금 완료", fin["지급 완료"], "", fill="ref")
    r = flow(ws, r, "계정 전체 입금 예정", fin["예정"], "", fill="ref")
    for x in a["extras"]:
        r = flow(ws, r, f"쿠팡 별도 보상 — {x['내용']}", x["금액"], f"{x['일자']} 대표계좌 입금 · 정산과 별도 · 상품 구분 정보 없음",
                 fill="ref")
    return r - 1, xs


def _sale_sheets(wb, a: dict, xs: list) -> None:
    months = sorted(m for m, (s, _e) in a["mmon"].items() if round(s))
    sh, add = a["ship"], a["add"]
    um = {x[1].replace("-", "") for x in a["ushare"]}
    table(wb, "월별 판매", ["판매 월", "판매금액", "쿠팡 정산금액", "상태"],
          [[f"{m[:4]}-{m[4:]}", a["mmon"][m][0], a["mmon"][m][1], "정산 중(일부 비율 배분)" if m in um else "끝남"] for m in months],
          (12, 18, 18, 22), note="관리 상품만(배송비 제외) · 판매한 달 기준. '정산 중' 달은 쿠팡이 계정 합계로만 알려 준 몫을 관리 상품 판매 비율로 나눔.")
    prods = [[e[0], e[1], e[2], e[3]] for e in a["prod"].values() if e[4]]
    if round(sh["관리"][1] + a["ship_u"][1]):
        prods.append([SHIP_LABEL, 0, sh["관리"][0] + a["ship_u"][0], sh["관리"][1] + a["ship_u"][1]])
    table(wb, "상품별 판매", ["상품명", "수량", "판매금액", "쿠팡 정산금액"], sorted(prods, key=lambda e: -e[2]), (50, 10, 16, 16),
          note="관리 상품 · 정산이 끝난 판매만(정산 중인 판매는 쿠팡이 상품별로 아직 알려 주지 않음).")
    table(wb, "제외한 상품", ["상품명", "수량", "판매금액", "쿠팡 정산금액"],
          sorted(([e[0], e[1], e[2], e[3]] for e in a["prod"].values() if not e[4]), key=lambda e: -e[2]), (50, 10, 16, 16),
          note="관리 상품이 아니어서 정산서에서 뺀 상품(위탁자 본인 상품 등) · 정산이 끝난 판매만.")
    if xs:
        table(wb, "외부 마케팅 대행비", ["요청일", "제품", "건수", "고객 부담", "회사 부담", "진행"],
              [[x["요청일"], x["제품명"], x["건수"], x["고객 부담"], x["우리 부담"], "완료" if x["완료"] else "진행 전"] for x in xs],
              (11, 52, 8, 14, 14, 9), money_from=3, note="정산금액에서 빼지 않고 참고로만 표시.")
    if add["줄"]:
        table(wb, "추가지급", [k for k, _ in AP.FIELDS], [[x[k] for k, _ in AP.FIELDS] for x in add["줄"]], [14] * len(AP.FIELDS),
              money_from=99, total=False)


def _pay_sheets(wb, a: dict, v: dict) -> None:
    pm: dict = defaultdict(lambda: [0.0, 0.0, 0.0])
    for x in a["rows_out"]:
        pm[x[0][:7]][{"지급 완료": 0, "예정": 1, "보류": 2}[x[5]]] += x[8]
    table(wb, "계정 전체 입금", ["입금 월", "입금 완료", "입금 예정", "보류"], [[m, *x] for m, x in sorted(pm.items())], (12, 18, 18, 14),
          note="참고 · 쿠팡 계정 전체(관리 밖 상품 포함) 실제 지급 · 지급일 기준(판매 후 약 2~6주 뒤 70%, 다음 달에 30%).")
    table(wb, "관리 상품 입금 내역", ["쿠팡 지급일", "판매 기간 시작", "판매 기간 끝", "판매 방식", "지급 비율(%)", "상태", "정산금액",
                               "쿠팡 공제", "입금액"], managed_lines(a, v), (12, 13, 13, 11, 11, 10, 14, 14, 14), money_from=6,
          note="관리 상품 몫 · 쿠팡 지급 줄마다 나눈 금액(1쪽 2번 표의 세부). 상태별 합계 = 1쪽 입금 완료·입금 예정·보류 · 원 단위 끝전은 상태마다 마지막 줄에.")
    table(wb, "계정 전체 입금 내역", ["쿠팡 지급일", "판매 기간 시작", "판매 기간 끝", "판매 방식", "지급 비율(%)", "상태", "정산금액",
                                "쿠팡 공제", "입금액"], sorted(a["rows_out"]), (12, 13, 13, 11, 11, 10, 14, 14, 14), money_from=6,
          note="참고 · 쿠팡 정산현황의 지급 줄 그대로(계정 전체). 입금액 = 정산금액 − 쿠팡 공제.")


def _basis_sheet(wb, a: dict, v: dict) -> None:
    t, tm, D, Dm, share, fin = a["t"], a["tm"], a["D"], a["Dm"], a["share"], a["fin"]
    basis = [["정산금액(끝난 판매)", t["settle"], tm["settle"] / t["settle"] if t["settle"] else 0, tm["settle"],
              "정확 — 상품별 쿠팡 정산 자료에서 관리 상품만 더함(배송비 = 같은 주문·반품 상품)"]]
    for ch, ym, s, e, shr, ms, me in a["ushare"]:
        _r, mm, aa = a["month_share"](ch, ym)
        basis.append([f"정산 중 {ym} {ch}", e, shr, me, f"{PENDING_NOTE} — " + (f"판매분석 {ym} {ch} 관리 상품 판매 {mm:,.0f} / 전체 {aa:,.0f}" if aa
                                                                             else "상품별 확정 정산금의 관리 비율")])
    for k, x in {**D, **({SVC: D[SVC]} if SVC in Dm else {})}.items():
        if round(x) or k == SVC and k in Dm:
            shr, why, kind = share[k]
            basis.append([k, x, shr, Dm[k], f"{kind} — {why}"])
    for k in STS:
        basis.append([f"입금 {k}", fin[k], v[k] / fin[k] if fin[k] else 0, v[k],
                      "쿠팡 지급 줄마다: 관리 정산금액(② × 줄 지급대상·판매 달 관리 비율 가중) − 그 줄 공제 × 항목 관리 비율 · 칸 끝전은 입금 예정에"])
    table(wb, "계산 근거", ["항목", "계정 전체", "관리 상품 비율", "관리 상품 몫", "나누는 기준"], basis, (26, 16, 14, 16, 70),
          total=False, fmts={3: PCT}, note=f"관리 상품 = {a['scope']} · 정산 원본 옵션ID로 상품을 찾음 · 쿠팡 대조(계정 전체): 줄마다 입금액 공식 "
          f"어긋남 {a['bad']}줄 · 보류 {a['L']['e3'][0]:,}={a['L']['e3'][1]:,}"
          + (f" · 쿠팡 조회에서 같은 지급 줄이 두 번 나온 {len(a['dup'])}줄은 한 번만 셈" if a["dup"] else ""))


def book(ctx, a: dict, dest: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "정산서"
    r = _head(ws, ctx, a)
    v = shown(a)
    neg, neg_note = _neg_note(v)
    r = _cards(ws, r, v, neg)
    r = _blocks_ae(ws, r, a, v)
    r = _blocks_fg(ws, r, a, v, neg, neg_note)
    r, xs = _refs(ws, r, ctx, a)
    ws.print_area = f"A1:F{r}"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    _sale_sheets(wb, a, xs)
    _pay_sheets(wb, a, v)
    _basis_sheet(wb, a, v)
    dest.parent.mkdir(parents=True, exist_ok=True)
    wb.save(dest)


def safe_name(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", s).strip("_")[:60]


SUM_HDR = ["사업자", "대표자", "계정ID", "관리 상품 범위", "관리 판매금액", "관리 쿠팡 정산금액", "관리 지급액", "입금 완료", "입금 예정", "보류",
           "상품 모르는 배송비", "우대수수료 환급", "추가지급", "계정 전체 정산금액", "정산 100% 일치(계정)", "불일치 사유"]


def summary_row(a: dict, v: dict) -> list:
    info = a["info"]
    return [info["사업자"], info["대표자"], a["aid"], a["scope"], v["sales"], v["settle"],
            v["pay"], v["지급 완료"], v["예정"], v["보류"],
            round(a["ship"]["확인 필요"][1]), round(a["fav"][0]) if a["fav"] else "자료 없음",
            round(a["addm"][0]) if a["add"]["상태"] == "있음" else a["add"]["상태"], round(a["settle_all"]),
            "일치" if a["ok"] else "불일치", " · ".join(a["why"])]


def summary_book(ctx, res: list, skipped: list) -> Path:
    """전체 요약(위탁 계정 + '(정산서 없음)') · 우리 사업자 시트 — 파일 이름 날짜 = 발행일."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "전체 요약"
    rows = [r for r, own in res if not own]
    table_rows = rows + [["(정산서 없음)", *r[1:]] for r in skipped if r[0] not in SRC.OWN_BUSINESSES]
    wb.remove(ws)
    table(wb, "전체 요약", SUM_HDR, table_rows, (22, 10, 14, 26, 14, 14, 14, 14, 14, 10, 30, 12, 12, 12, 16, 12, 60), money_from=4,
          note=f"위탁 계정 · 관리 상품만 · 장부 기준일 {ctx.basis} · '(정산서 없음)' = 관리 상품을 정할 자료가 없거나 판정 대기 · "
          f"정산 100% 일치 = 계정 전체 금액이 쿠팡 정산 리포트·지급 내역·보류 목록과 원 단위로 맞음(D-083).")
    table(wb, "우리 사업자(통보 제외)", SUM_HDR, [r for r, own in res if own], [14] * len(SUM_HDR), money_from=4)
    dest = ctx.out / f"전체_위탁정산서_관리상품_{date.fromisoformat(ctx.issued):%y%m%d}.xlsx"
    wb.save(dest)
    return dest
