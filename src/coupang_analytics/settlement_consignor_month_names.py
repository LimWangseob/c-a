"""위탁자 정산서 3차 형식 — 2쪽 상품 줄 묶기(AI 판정표 `상품이름_판정.json` · D-241 ③). T-38 S2(샘플 `s03_compute.py`
_name_groups·_candidate). 판정표에 이 계정이 없거나 등록상품ID 가 없으면 그 상품은 혼자 한 줄 + judgments + 판정 후보 원문(_근거).
프로그램 글자 비교로 묶지 않음(판정은 AI · 판정표 파일만 따름).
"""
from __future__ import annotations

from coupang_analytics.settlement_consignor_month_calc import MonthState


def _single(st: MonthState, p: str) -> str:
    return st.names.get(p, p) + f" [{p}]"


def _table_index(st: MonthState, tbl: list) -> dict:
    shown = [x["표시 이름"] for x in tbl]
    dup = sorted({n for n in shown if shown.count(n) > 1})
    if dup:
        raise ValueError(f"{st.aid} 상품이름 판정표에 같은 '표시 이름'이 둘 이상: {dup}")
    return {str(p): x for x in tbl for p in x["등록상품ID"]}


def name_groups(st: MonthState, active: list) -> dict:
    """{표시 이름: [등록상품ID]} — 판정표대로 묶음."""
    tbl = st.judge.names.get(st.aid)
    if tbl is None:
        st.j.append(f"상품명 묶기 판정 없음 — 상품이름 판정표({st.judge.names_path or '없음'})에 이 계정이 없어 등록상품마다 한 줄")
        st.missing = {p: candidate(st, p) for p in active}
        return {_single(st, p): [p] for p in active}
    pid2 = _table_index(st, tbl)
    miss = [p for p in active if p not in pid2]
    if miss:
        st.j.append(f"상품명 묶기 판정 없음 — 등록상품ID {', '.join(miss)} 이(가) 상품이름 판정표에 없어 혼자 한 줄(후보 = _근거 '상품명 판정 후보')")
        st.missing = {p: candidate(st, p) for p in miss}
    groups: dict = {}
    for p in active:
        groups.setdefault(pid2[p]["표시 이름"] if p in pid2 else _single(st, p), []).append(p)
    st.name_used = [x for x in tbl if any(str(p) in active for p in x["등록상품ID"])]
    return groups


def _period_vids(st: MonthState, pid: str, vids: set) -> None:
    for rec in st.d["periods"].values():
        for v, o in (rec.get("옵션") or {}).items():
            if str(o.get("등록상품ID") or "") == pid:
                vids.add(str(v))


def _candidate_opts(st: MonthState, pid: str, vids: set) -> list:
    periods = st.d["periods"]
    uniq: dict = {}
    for k in sorted(periods):
        for v, o in (periods[k].get("옵션") or {}).items():
            if str(v) in vids and (o.get("판매금액") or str(o.get("등록상품ID") or "") == pid):
                uniq.setdefault((str(v), o.get("구분"), o.get("상품"), o.get("옵션")),
                                {"기간": k, "VID": str(v), "구분": o.get("구분"), "상품": o.get("상품"), "옵션": o.get("옵션"),
                                 "판매금액": o.get("판매금액"), "등록상품ID 표시": o.get("등록상품ID")})
    return list(uniq.values())


def _known_names(st: MonthState, pid: str, inv: dict | None) -> dict:
    return {"정산집계 상품별 월별": sorted({str(p["상품명"]) for p in st.d["prows"] if str(p["등록상품ID"]) == pid and p["상품명"]}),
            "상품조회": inv["name"] if inv else None}


def candidate(st: MonthState, pid: str) -> dict:
    """AI 상품명 판정 근거 원문(정산집계 상품명·상품조회 이름·VID·판매분석 옵션 이름·금액)."""
    d = st.d
    vids = {v for v, p in st.opt2pid.items() if str(p) == pid}
    inv = d["inventory"].get(pid) or d["inventory"].get(int(pid) if pid.isdigit() else pid)
    types = (inv or {}).get("types", {})
    vids |= {str(v) for v in types}
    _period_vids(st, pid, vids)
    return {"등록상품ID": pid, "관리": st.is_m(pid), "알려진 이름": _known_names(st, pid, inv),
            "VID": {v: {"opt2pid": st.opt2pid.get(v), "상품조회": types.get(v) if inv else None, "관리 옵션": st.is_mv.get(v)}
                    for v in sorted(vids)},
            "판매분석 옵션(VID·구분·상품·옵션 이름)": _candidate_opts(st, pid, vids),
            "금액": {f"c{k}": round(st.cols[pid][k]) for k in range(1, 9)},
            "그중 확정 전": {f"c{k}": round(st.pend[pid][k]) for k in range(1, 9)}}
