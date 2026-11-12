"""위탁정산서 엑셀 공통 — 칸 쓰기·표 시트·1쪽 원 단위 숫자(검산)·관리 상품 입금 내역 줄. T-25 이관(옛 `statement_managed.py` 530~680줄 · 행동 불변)."""
from __future__ import annotations

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from coupang_analytics.settlement_statement_account import AD, COMP, ETC, FAST, LOGI, MILK, REL, STS, SVC

LINE = Side(style="thin", color="CFD8DC")
BOX = Border(left=LINE, right=LINE, top=LINE, bottom=LINE)
FILL = {k: PatternFill("solid", fgColor=c) for k, c in
        {"title": "C5CAE9", "sec": "E8EAF6", "scope": "E3F2FD", "ok": "C8E6C9", "card": "F5F7FF", "sum": "E8F5E9", "big": "C8E6C9", "soft": "FAFAFA",
         "ref": "FFF8E1", "warn": "FFEBEE"}.items()}
SIGNED, PLAIN, PCT = '+#,##0;[Red]-#,##0;0', '#,##0;[Red]-#,##0;0', '0.0%'
PENDING_NOTE = "정산 예정 — 쿠팡 상품별 자료 전, 판매 비율로 배분 · 정산 파일이 나오면 바뀜"
SHIP_LABEL = "배송비(고객이 낸 배송료 — 쿠팡 정산 파일에 상품 없이 따로 들어오는 줄)"
NOTES = {AD: "쿠팡 광고 사용료", LOGI: "로켓그로스 창고·배송 비용", MILK: "쿠팡 창고로 보내는 운송 서비스",
         SVC: "월 매출 100만 원 이상이면 월 5만 원+부가세", ETC: "위 항목 외 쿠팡 공제", COMP: "쿠팡 창고에서 잃어버린 재고 보상",
         FAST: "셀러월렛으로 미리 받은 돈 상환", REL: "쿠팡이 멈췄다가 다시 보낸 돈"}
ORDER = [AD, LOGI, MILK, SVC, FAST, ETC, COMP, REL]


def cell(ws, r, c, v=None, *, bold=False, size=11, fill=None, fmt=None, align=None, wrap=False, box=True):
    x = ws.cell(row=r, column=c, value=v)
    if isinstance(v, str) and v.startswith("="):      # '=' 로 시작하면 엑셀이 수식으로 읽음(#NAME?) — 글자로 고정
        x.data_type = "s"
    x.font = Font(name="맑은 고딕", bold=bold, size=size, color="000000")   # 글씨는 검정 · 구분은 바탕색 · 음수만 [Red] 서식(소유자 2026-10-27)
    if fill:
        x.fill = FILL[fill]
    if fmt:
        x.number_format = fmt
    x.alignment = Alignment(horizontal=align, vertical="center", wrap_text=wrap)
    if box:
        x.border = BOX
    return x


def merge(ws, r, c1, c2, v=None, **kw):
    for c in range(c1, c2 + 1):
        cell(ws, r, c, None, fill=kw.get("fill"), box=kw.get("box", True))
    ws.merge_cells(start_row=r, start_column=c1, end_row=r, end_column=c2)
    return cell(ws, r, c1, v, **kw)


def section(ws, r, text, fill="sec"):
    merge(ws, r, 2, 6, text, bold=True, size=12, fill=fill)
    ws.row_dimensions[r].height = 22
    return r + 1


def flow(ws, r, label, amount, note="", *, kind=None, fill=None):
    fill = {"sum": "sum", "big": "big"}.get(kind, fill)
    cell(ws, r, 2, label, bold=bool(kind), fill=fill)
    cell(ws, r, 3, amount, bold=bool(kind), fill=fill, fmt=PLAIN if kind else SIGNED, align="right")
    merge(ws, r, 4, 6, note, fill=fill, wrap=True)
    return r + 1


def _total_row(s, rows, hdr, money_from, fmts) -> None:
    n = 5 + len(rows)
    cell(s, n, 1, "합계", bold=True, fill="sum")
    for j in range(2, len(hdr) + 1):
        vals = [row[j - 1] for row in rows if isinstance(row[j - 1], (int, float))]
        ok = vals and j > money_from and j not in (fmts or {})
        cell(s, n, j, round(sum(vals)) if ok else None, bold=True, fill="sum", fmt=PLAIN)


def table(wb, title, hdr, rows, widths, money_from=1, total=True, note="", fmts=None):
    s = wb.create_sheet(title)
    s.sheet_view.showGridLines = False
    for i, w in enumerate(widths, 1):
        s.column_dimensions[get_column_letter(i)].width = round(w * 1.1)   # 글씨 11pt 기준 폭
    merge(s, 1, 1, len(hdr), title, bold=True, size=15, fill="title")
    if note:
        merge(s, 2, 1, len(hdr), note, wrap=True, box=False)
        s.row_dimensions[2].height = 30
    for j, hd in enumerate(hdr, 1):
        cell(s, 4, j, hd, bold=True, fill="sec", align="center", wrap=True)
    for i, row in enumerate(rows, 5):
        for j, v in enumerate(row, 1):
            f = (fmts or {}).get(j) or (PLAIN if j > money_from and isinstance(v, (int, float)) else None)
            cell(s, i, j, round(v) if isinstance(v, float) and f == PLAIN else v, fmt=f)
    if total and rows:
        _total_row(s, rows, hdr, money_from, fmts)
    s.freeze_panes = "A5"
    return s


class SumMismatch(Exception):
    """정산서 금액 칸의 줄 합계가 위 큰 숫자와 1원이라도 다름 — 그 정산서는 만들지 않는다."""


def _status_table(a: dict, settle: int, ded: list) -> list:
    """(항목, {상태: 원}, 합계) — 공제는 음수. 합계로는 0이어도 입금 완료·예정 사이에서 오간 항목(예: 판매 조정)도 줄로 보여 줌."""
    Dm, tbl, dmap = a["Dm"], [], dict(ded)
    keys = [k for k in ORDER + sorted((set(Dm) | {k for st in STS for k in a["st_ded"][st]}) - set(ORDER))
            if k in dmap or any(round(a["st_ded"][st].get(k, 0.0)) for st in STS)]
    for label, total, f in [("② 쿠팡 정산 총액", settle, a["st_settle"])] + [
            (k, -dmap.get(k, 0), {st: -a["st_ded"][st].get(k, 0.0) for st in STS}) for k in keys]:
        done, hold = round(f["지급 완료"]), round(f["보류"])
        tbl.append((label, {"지급 완료": done, "보류": hold, "예정": total - done - hold}, total))
    return tbl


def _check(a: dict, v: dict, col: dict, bank_col: dict) -> None:
    tm, sales, settle, ded, bank, pay = a["tm"], v["sales"], v["settle"], v["ded"], v["bank"], v["pay"]
    if v["gross"] + v["refund"] + v["ship"] != v["c_sales"]:
        raise SumMismatch(f"{a['aid']}: 판매액 {v['gross']:,} + 취소 {v['refund']:,} + 배송비 {v['ship']:,} ≠ 판매금액(확정) {v['c_sales']:,}")
    s1 = sales - round(tm["coupon"]) - round(tm["fee"]) - round(tm["other"]) - v["u_cost"]
    bad = [f"①→② 줄 합계 {s1:,} ≠ ② {settle:,}"] if s1 != settle else []
    c1 = v["c_sales"] - round(tm["coupon"]) - round(tm["fee"]) - round(tm["other"])
    if c1 != v["c_settle"] or v["c_settle"] + v["u_settle"] != settle:
        bad.append(f"정산 확정 칸 {c1:,} ≠ {v['c_settle']:,} 또는 확정+예정 ≠ ②")
    if abs(bank - round(a["pay_m"])) > len(ded):                   # 줄마다 반올림한 끝전 이상 차이 = 계산 오류
        bad.append(f"통장 지급액 {bank:,} ≠ 계산값 {a['pay_m']:,.0f}")
    fdone = a["st_settle"]["지급 완료"] - sum(a["st_ded"]["지급 완료"].values())
    if sum(col.values()) != pay or sum(bank_col.values()) != bank or abs(bank_col["지급 완료"] - fdone) > len(v["tbl"]):
        bad.append(f"입금 칸 합 {sum(col.values()):,} ≠ G {pay:,} 또는 입금 완료 {bank_col['지급 완료']:,} ≠ 계산값 {fdone:,.0f}")
    if bad:
        raise SumMismatch(f"{a['aid']}: " + " · ".join(bad))


def shown(a: dict) -> dict:
    """정산서 1쪽에 쓰는 원 단위 숫자 — 표의 칸·줄 합계가 큰 숫자 ①~④와 정확히 맞도록 한 번에 정한다.
    끝전: 정산금액·공제 줄의 합계 = 각각 반올림 · 입금 완료·보류 칸 = 반올림 · 입금 예정 칸 = 합계 − 완료 − 보류(줄마다)."""
    tm, Dm = a["tm"], a["Dm"]
    u_sales, u_settle = round(a["um_sales"]), round(a["um_settle"])
    sales = round(tm["sales"]) + u_sales
    settle = round(tm["settle"]) + u_settle
    ded = [(k, round(Dm[k])) for k in ORDER + sorted(set(Dm) - set(ORDER)) if k in Dm and round(Dm[k])]
    bank = settle - sum(x for _, x in ded)                     # 쿠팡이 통장(대표계좌)으로 보내는 몫
    fast = dict(ded).get(FAST, 0)                              # 빠른정산 상환 = 셀러월렛으로 이미 받은 돈 → 공제 아님·입금 완료(소유자 2026-10-28)
    pay = bank + fast
    tbl = _status_table(a, settle, ded)
    col = {st: sum(c[st] for _, c, _ in tbl) for st in STS}   # 통장 기준(빠른정산 상환 뺀 뒤)
    bank_col = dict(col)
    col["지급 완료"] += fast
    ship_m = round(a["ship"]["관리"][0] + a["ship_u"][0])
    v = {"gross": round(a["gross"]), "refund": round(a["refund"]), "ship": ship_m, "sales": sales,
         "c_sales": round(tm["sales"]), "c_settle": round(tm["settle"]), "u_sales": u_sales, "u_settle": u_settle,
         "u_cost": u_sales - u_settle, "settle": settle, "ded": ded, "cost": settle - pay, "pay": pay, "bank": bank, "fast": fast, "bank_col": bank_col,
         "tbl": tbl, **col}
    _check(a, v, col, bank_col)
    return v


def _cum_round(xs: list, target: int) -> list:
    """소수 금액 목록 → 누적 반올림 정수 목록, 합계 = target(끝전은 마지막 줄)."""
    out, acc, prev = [], 0.0, 0
    for x in xs:
        acc += x
        out.append(round(acc) - prev)
        prev = round(acc)
    if out:
        out[-1] += target - sum(out)
    return out


def managed_lines(a: dict, v: dict) -> list:
    """관리 상품 입금 내역 줄 — 상태별 정산금액·공제 합계가 1쪽 2번 표 칸과 원 단위로 같게."""
    rows = []
    for st in STS:
        ls = sorted((x for x in a["line_m"] if x[1] == st), key=lambda x: tuple(str(t) for t in x[0][2:5]) if x[0] else ("9999",))
        if not ls:
            continue
        t_settle = v["tbl"][0][1][st]
        t_ded = -sum(c[st] for _, c, _ in v["tbl"][1:])
        ss, dd = _cum_round([x[2] for x in ls], t_settle), _cum_round([x[3] for x in ls], t_ded)
        for (row, _st, _s, _d), s_, d_ in zip(ls, ss, dd):
            head = [row[2], row[3], row[4], row[1], row[5]] if row else ["(지급일 미정)", "", "", "", ""]
            rows.append([*head, st, s_, -d_, s_ - d_])
    return rows
