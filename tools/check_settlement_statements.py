# -*- coding: utf-8 -*-
"""위탁정산서 결과 검증(실제 출력 폴더용 · 게이트 밖): 독립 검산 · 추정 문구 전수 · 계정별 금액 차이. T-25 이관(옛 check_statements.py 그대로).
사용: python tools/check_settlement_statements.py <새 폴더> <이전 폴더>"""
import glob
import os
import re
import sys
import warnings

import openpyxl

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
NEW, OLD = sys.argv[1].replace("\\", "/"), sys.argv[2].replace("\\", "/")   # 새 출력 폴더 · 비교할 이전 출력 폴더


def n(x):
    return x if isinstance(x, (int, float)) else 0


def grid(f):
    ws = openpyxl.load_workbook(f, data_only=True).worksheets[0]
    return [[c.value for c in r] for r in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=8)]


def find(g, label, start=0):
    for i in range(start, len(g)):
        if isinstance(g[i][1], str) and g[i][1].strip() == label:
            return i
    raise KeyError(label)


ok = bad = 0
for f in sorted(glob.glob(NEW + "/정산서_*.xlsx")):
    g = grid(f)
    errs = []

    def blk(head, total):
        h = find(g, head)
        t = find(g, total, h + 1)
        hdr = next(i for i in range(h, t) if g[i][2] in ("정산 확정", "공제 완료분", "입금 완료"))
        rows = g[hdr + 1:t]
        for col in (2, 3, 4):
            s = sum(n(r[col]) for r in rows if isinstance(r[1], str))
            if round(s) != round(n(g[t][col])):
                errs.append(f"{total} 칸{col} {s}≠{g[t][col]}")
        for r in rows + [g[t]]:
            if isinstance(r[1], str) and round(n(r[2]) + n(r[3])) != round(n(r[4])):
                errs.append(f"{r[1]} 가로합")
        return g[t]
    hd = lambda p: next(r[1] for r in g if isinstance(r[1], str) and r[1].startswith(p))  # noqa: E731
    hA, hE, hF, hG = hd("A 판매금액 내역"), hd("E 정산대상액 ="), hd("F 쿠팡 공제 내역"), hd("G 최종 지급액 =")
    A, E, F, G = blk(hA, "A 판매금액"), blk(hE, "E 정산대상액"), blk(hF, "F 쿠팡 공제"), blk(hG, "G 최종 지급액")
    iG = find(g, hG)
    card = g[7]
    for k, (cv, tv) in {"A": (card[1], A[4]), "E": (card[2], E[4]), "F": (card[3], F[4]), "G": (card[4], G[4])}.items():
        if round(n(cv)) != round(n(tv)):
            errs.append(f"카드{k}")
    gF, gE = find(g, "F 쿠팡 공제", iG), find(g, "E 정산대상액", iG)
    if [round(n(x)) for x in g[gF][2:5]] != [round(n(x)) for x in F[2:5]]:
        errs.append("G표 F줄≠F")
    if round(n(g[gE][4])) != round(n(E[4])):
        errs.append("G표 E줄≠E")
    if round(E[4] + F[4]) != round(G[4]):
        errs.append("G≠E+F")
    t = str(card[5])
    m = lambda p: int(re.search(p + r" ([-\d,]+)", t).group(1).replace(",", "")) if re.search(p, t) else 0  # noqa: E731
    if m("입금 완료") != round(G[2]) or m("입금 예정") != round(G[3]):
        errs.append("비고 입금≠G표")
    ok += not errs
    bad += bool(errs)
    if errs:
        print("✘", os.path.basename(f), errs)
print(f"독립 검산 {ok}/{ok + bad}")

hits = 0
files = glob.glob(NEW + "/*.xlsx") + glob.glob(NEW + "/*/*.xlsx")
for f in files:
    for ws in openpyxl.load_workbook(f, data_only=True).worksheets:
        for row in ws.iter_rows(values_only=True):
            for c in row:
                if isinstance(c, str) and "추정" in c:
                    hits += 1
                    print("추정:", os.path.basename(f), ws.title, c[:80])
print(f"'추정' 문구 {hits}건 · 파일 {len(files)}개")


def summ(d):
    out = {}
    wb = openpyxl.load_workbook(glob.glob(d + "/전체_위탁*.xlsx")[0], data_only=True)
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        for r in rows[4:]:
            if r[2]:
                out[r[2]] = dict(zip(rows[3], r))
    return out


o, w = summ(OLD), summ(NEW)
K = ["관리 판매금액", "관리 쿠팡 정산금액", "관리 지급액", "입금 완료", "입금 예정", "보류"]
print("합계 전→후", {k: (sum(n(x[k]) for x in o.values()), sum(n(x[k]) for x in w.values())) for k in K})
print("사업자 | G 전→후(차이) | 입금 완료 전→후 | 입금 예정 전→후")
for a, x in sorted(w.items(), key=lambda t: -abs(n(t[1]["관리 지급액"]) - n(o[t[0]]["관리 지급액"]))):
    y = o[a]
    if all(x[k] == y[k] for k in K):
        continue
    print(x["사업자"], a, f"{y['관리 지급액']:,}→{x['관리 지급액']:,}({n(x['관리 지급액']) - n(y['관리 지급액']):+,})",
          f"완료 {y['입금 완료']:,}→{x['입금 완료']:,}", f"예정 {y['입금 예정']:,}→{x['입금 예정']:,}",
          f"A차 {n(x['관리 판매금액']) - n(y['관리 판매금액']):+,} E차 {n(x['관리 쿠팡 정산금액']) - n(y['관리 쿠팡 정산금액']):+,}")
print("계정 수", len(o), len(w), "일치", sum(x["정산 100% 일치(계정)"] == "일치" for x in w.values()))
