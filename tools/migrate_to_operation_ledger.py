"""2단계 데이터 전환(초안) — 현 관리대장(109열)+재고현황 → 운영대장 시트.

designs/OPERATION_DATA_MODEL.md 구조로 best-effort 이관. 결과는 **사람 검토용 초안(DRAFT)**:
- 상품코드 발번: 분류(재고 '구분' G건기식/P공산품/E기타) + 입고YYMM(날짜 우선순위: 출고>완료>재고갱신월>전환월 2610) + 순번.
- 재고↔상품 자동 매칭은 best-effort(띄어쓰기 무시 비교) → 불확실분은 '매핑검토' 시트로.
- 빈 틀은 build_operation_template 로 만들고 헤더명 기준으로 값 채움(컬럼 순서 일치 보장).

    python tools/migrate_to_operation_ledger.py [관리대장.xlsx] [재고현황.xlsx] [출력.xlsx]
기본 경로 = Downloads 의 현재 파일.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_operation_template as T  # noqa: E402  (빈 틀·헤더 정의 재사용)

_DL = Path.home() / "Downloads"
DEF_LEDGER = _DL / "토탈셀러_셀독 관리 대장 (7).xlsx"
DEF_STOCK = _DL / "재고 현황 (1).xlsx"
DEF_OUT = _DL / "운영대장_전환초안.xlsx"

# 셀독리스트 컬럼(1-based·실측 2026-10-01)
C_MEMO = list(range(3, 21))          # 3~20 관리내용(3~18 날짜·19 기존·20 최근)
C_REP, C_BIZ, C_AID, C_PW, C_DEPOSIT, C_PROMO = 21, 22, 23, 24, 25, 26
C_PNAME, C_COSTOCK, C_GSTOCK, C_URL, C_HIST, C_UNIT, C_PRICE, C_NOTE = 27, 28, 29, 30, 31, 32, 33, 34
C_GREQDATE, C_GREQQTY, C_GWORKQTY, C_GBOX, C_GPAL, C_GDONE, C_GSHIP = 35, 36, 37, 38, 39, 40, 41
_CLASS = {"건기식": "G", "공산품": "P"}


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def _norm(name: str) -> str:
    return re.sub(r"\s+", "", name or "").lower()


def _ym(v) -> str:
    """날짜값 → 'YYMM'. '26.08.28'·'2026-08-28'·엑셀 날짜 등. 실패 시 ''."""
    if isinstance(v, datetime):
        return f"{v.year % 100:02d}{v.month:02d}"
    s = _s(v)
    m = re.search(r"(?:20)?(\d{2})[.\-/](\d{1,2})", s)
    return f"{int(m.group(1)):02d}{int(m.group(2)):02d}" if m else ""


def read_stock(path: Path):
    """재고현황 Sheet1 → (norm상품명 → dict), 재고 갱신월(YYMM)."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Sheet1"]
    ym = _ym(ws.cell(1, 1).value) or ""      # A1 '재고현황 26.08.20 기준'
    idx: dict[str, dict] = {}
    for r in range(3, (ws.max_row or 0) + 1):
        nm = _s(ws.cell(r, 4).value)
        if not nm:
            continue
        ch = "/".join(x for x in (_s(ws.cell(r, 6).value), _s(ws.cell(r, 7).value),
                                  _s(ws.cell(r, 8).value)) if x)
        idx.setdefault(_norm(nm), {"창고": _s(ws.cell(r, 1).value), "구분": _s(ws.cell(r, 2).value),
                                   "바코드": _s(ws.cell(r, 3).value), "현재고": _s(ws.cell(r, 5).value),
                                   "채널": ch, "물류명": nm})
    return idx, ym


def read_ledger(path: Path):
    """셀독리스트 → [account dict]. 계정아이디(23) 채워진 행=새 계정, 그 외 상품명(27) 행=그 계정 상품."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["셀독리스트"]
    memo_hdr = [_s(ws.cell(2, c).value) for c in C_MEMO]
    accts: list[dict] = []
    cur: dict | None = None
    for r in range(3, (ws.max_row or 0) + 1):
        aid = _s(ws.cell(r, C_AID).value)
        if aid:
            cur = {"계정아이디": aid, "대표자명": _s(ws.cell(r, C_REP).value),
                   "사업자명": _s(ws.cell(r, C_BIZ).value), "비밀번호": _s(ws.cell(r, C_PW).value),
                   "계약금": _s(ws.cell(r, C_DEPOSIT).value), "체험단주체": _s(ws.cell(r, C_PROMO).value),
                   "담당자": _s(ws.cell(r, 2).value), "products": [], "memos": []}
            accts.append(cur)
            # 계정 행의 관리내용(계정 단위 업무일지)
            for h, c in zip(memo_hdr, C_MEMO):
                txt = _s(ws.cell(r, c).value)
                if txt:
                    cur["memos"].append((h, txt))
        if cur is None:
            continue
        pname = _s(ws.cell(r, C_PNAME).value)
        if pname:
            lines = [ln.strip() for ln in pname.splitlines() if ln.strip()]
            inner = lines[0] if lines else pname
            expose = " ".join(lines[1:]).strip("() ") if len(lines) > 1 else ""
            cur["products"].append({
                "상품명": inner, "노출상품명": expose,
                "회사보유재고": _s(ws.cell(r, C_COSTOCK).value), "그로스재고": _s(ws.cell(r, C_GSTOCK).value),
                "상품url": _s(ws.cell(r, C_URL).value), "계약단가": _s(ws.cell(r, C_UNIT).value),
                "판매가": _s(ws.cell(r, C_PRICE).value), "비고": _s(ws.cell(r, C_NOTE).value),
                "히스토리": _s(ws.cell(r, C_HIST).value),
                "그로스": {"요청일자": _s(ws.cell(r, C_GREQDATE).value), "요청수량": _s(ws.cell(r, C_GREQQTY).value),
                          "작업수량": _s(ws.cell(r, C_GWORKQTY).value), "박스": _s(ws.cell(r, C_GBOX).value),
                          "파레트": _s(ws.cell(r, C_GPAL).value), "완료일자": _s(ws.cell(r, C_GDONE).value),
                          "출고일자": _s(ws.cell(r, C_GSHIP).value)},
            })
    return accts


def read_promo(path: Path):
    """관리대장 '체험단' 시트 → [row dict] (헤더 3행·데이터 4행~)."""
    wb = openpyxl.load_workbook(path, data_only=True)
    if "체험단" not in wb.sheetnames:
        return []
    ws = wb["체험단"]
    hdr = {_s(ws.cell(3, c).value): c for c in range(1, (ws.max_column or 0) + 1) if _s(ws.cell(3, c).value)}
    out = []
    for r in range(4, (ws.max_row or 0) + 1):
        def g(name, _r=r):
            return _s(ws.cell(_r, hdr[name]).value) if name in hdr else ""
        if not (g("상호") or g("제품명")):
            continue
        out.append({"사업자명": g("상호"), "상품명": g("제품명"), "요청일": g("요청일"), "키워드": g("키워드"),
                    "판매가": g("판매가"), "리뷰/택배": g("리뷰/택배"), "건수": g("건수"),
                    "신규/추가": g("체험단 신규/추가"), "견적서판매가": g("견적서 판매가"),
                    "견적서리뷰/택배": g("견적서 리뷰/택배"), "밑작업": g("밑작업"),
                    "포토/텍스트": g("포토/텍스트"), "진행여부": g("진행 여부"), "비고": g("비고")})
    return out


def assign_code(classc: str, ym: str, seq: dict) -> str:
    key = (classc, ym)
    seq[key] = seq.get(key, 0) + 1
    return f"{classc}{ym}-{seq[key]:03d}"


def _row(ws, hmap: dict, values: dict) -> None:
    r = ws.max_row + 1
    for name, col in hmap.items():
        if name in values:
            ws.cell(r, col, values[name])


def _hmap(ws) -> dict:
    return {_s(ws.cell(1, c).value): c for c in range(1, (ws.max_column or 0) + 1) if _s(ws.cell(1, c).value)}


def migrate(ledger: Path, stock: Path, out: Path) -> dict:
    stock_idx, stock_ym = read_stock(stock)
    accts = read_ledger(ledger)
    promos = read_promo(ledger)
    T.build(out)                                   # 빈 틀 생성
    wb = openpyxl.load_workbook(out)
    hm = {sn: _hmap(wb[sn]) for sn in ("계정", "관리상품", "그로스입고", "체험단", "업무일지")}
    review = wb.create_sheet("매핑검토")
    review.sheet_properties.tabColor = "FF0000"
    for c, h in enumerate(["상품코드", "사업자명", "상품명", "사유"], 1):
        review.cell(1, c, h)
    review.freeze_panes = "A2"

    seq: dict = {}
    stats = {"계정": 0, "상품": 0, "그로스입고": 0, "체험단": 0, "업무일지": 0, "매핑검토": 0}
    name2code: dict[tuple, str] = {}

    for a in accts:
        _row(wb["계정"], hm["계정"], {"대표자명": a["대표자명"], "사업자명": a["사업자명"],
             "비밀번호": a["비밀번호"], "위탁상태": "관리중", "체험단주체": a["체험단주체"],
             "계정아이디": a["계정아이디"]})
        stats["계정"] += 1
        for h, txt in a["memos"]:
            _row(wb["업무일지"], hm["업무일지"], {"일자": h.replace("관리내용", ""), "대상": "계정",
                 "사업자명": a["사업자명"], "작성자": a["담당자"], "내용": txt, "계정아이디": a["계정아이디"]})
            stats["업무일지"] += 1
        for p in a["products"]:
            st = stock_idx.get(_norm(p["상품명"]))
            classc = _CLASS.get(st["구분"], "E") if st else "E"
            g = p["그로스"]
            ym = _ym(g["출고일자"]) or _ym(g["완료일자"]) or stock_ym or "2610"
            code = assign_code(classc, ym, seq)
            name2code[(a["사업자명"], p["상품명"])] = code
            kind = "그로스판매" if p["그로스재고"] not in ("", "0", "0.0") else ""
            _row(wb["관리상품"], hm["관리상품"], {
                "사업자명": a["사업자명"], "상품명": p["상품명"], "노출상품명": p["노출상품명"],
                "물류상품명": st["물류명"] if st else "", "카테고리": st["구분"] if st else "",
                "판매방식": kind, "상품url": p["상품url"], "계약단가": p["계약단가"], "판매가": p["판매가"],
                "관리상태": "판매중", "비고": p["비고"], "계정아이디": a["계정아이디"],
                "상품코드": code, "바코드": st["바코드"] if st else ""})
            stats["상품"] += 1
            if any(g.values()):
                _row(wb["그로스입고"], hm["그로스입고"], {"사업자명": a["사업자명"], "상품명": p["상품명"],
                     "요청일자": g["요청일자"], "요청수량": g["요청수량"], "작업수량": g["작업수량"],
                     "박스": g["박스"], "파레트": g["파레트"], "완료일자": g["완료일자"],
                     "출고일자": g["출고일자"], "상품코드": code})
                stats["그로스입고"] += 1
            if p["히스토리"]:
                _row(wb["업무일지"], hm["업무일지"], {"일자": "", "대상": "상품", "사업자명": a["사업자명"],
                     "상품명": p["상품명"], "작성자": a["담당자"], "내용": p["히스토리"],
                     "계정아이디": a["계정아이디"], "상품코드": code})
                stats["업무일지"] += 1
            if not st:
                rr = review.max_row + 1
                for cc, val in enumerate((code, a["사업자명"], p["상품명"],
                                          "재고 매칭 실패(분류 E·입고월 기본) — 수동 매핑 필요"), 1):
                    review.cell(rr, cc, val)
                stats["매핑검토"] += 1

    for pr in promos:
        code = name2code.get((pr["사업자명"], pr["상품명"]), "")
        _row(wb["체험단"], hm["체험단"], {"사업자명": pr["사업자명"], "상품명": pr["상품명"], "요청일": pr["요청일"],
             "키워드": pr["키워드"], "판매가": pr["판매가"], "리뷰/택배": pr["리뷰/택배"], "건수": pr["건수"],
             "신규/추가": pr["신규/추가"], "견적서판매가": pr["견적서판매가"],
             "견적서리뷰/택배": pr["견적서리뷰/택배"], "밑작업": pr["밑작업"], "포토/텍스트": pr["포토/텍스트"],
             "진행여부": pr["진행여부"], "비고": pr["비고"], "상품코드": code})
        stats["체험단"] += 1

    wb.save(out)
    return stats


def main() -> int:
    a = sys.argv
    ledger = Path(a[1]) if len(a) > 1 else DEF_LEDGER
    stock = Path(a[2]) if len(a) > 2 else DEF_STOCK
    out = Path(a[3]) if len(a) > 3 else DEF_OUT
    stats = migrate(ledger, stock, out)
    print(f"[전환 초안] {out}")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print("  [주의] 초안 — '매핑검토' 시트 확인 후 수동 보정 필요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
