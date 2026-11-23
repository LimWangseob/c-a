"""옵션이 나뉠 때 다른 옵션 블록으로 잘못 옮겨진 지난 이력을 제 VID 블록으로 되돌린다 — 로그인·쿠팡 조회 없음(T-162 ·
소유자 2026-11-23 'LED 스탠드의 잘못 옮겨진 기록을 바로잡을까요?' → '보완해줘.').

원인(T-162 · 고침 = pipeline_process._migrate_product_blocks): 단일옵션 블록(VID A)이 다음 날 옵션 [B(첫), A] 로 나뉘면
옛 코드가 A 이력 블록을 대표(B) 이름으로 바꿔, 분리 전 A 이력이 B 블록에 붙고 A 블록은 빈 칸으로 새로 시작했다.

찾기(같은 사업자 시트 · 같은 계정 · 이름 앞부분(옵션 괄호 앞) 또는 등록상품명이 같은 두 블록 · VID 안 겹침):
  받을 블록 C(제 VID 이력이 늦게 시작) · 옮길 블록 B — C 첫 값 날짜보다 앞 날짜에 B 만 값이 있음.
판정(날짜 칸마다 · 앱 ① 규칙 = 블록 VID 중 그날 기록에 있는 첫 VID 판매수량 · 기록은 있는데 VID 없으면 0):
  - 판매분석 근거 = 그날 B 판매량 == C VID 판매수량 != B VID 판매수량 → 옮김
  - 판매분석으로 못 가림(둘 다 같음·그날 기록 없음) → 분리 전 백업·스냅샷에 'C VID 만 가진 블록'이 있고 그 블록 값
    (판매량·노출량)이 B 와 다르지 않으면 옮김(백업 근거) · 아니면 '확인 필요'(안 옮김)
  - 판매분석과 안 맞는 날이 한 칸이라도 있는 쌍 = 쌍 전체 '확인 필요'(안 옮김)
옮김 = 그 날짜 칸의 지표행(판매량·방문자·노출량·재고현황·판매가·판매상태)만 B → C · B 칸은 비움 · 키워드(순위)행은 그대로
(순위는 리스팅 단위·대표 블록). 대상 계정·상품은 코드에 없음(D-229) — 찾은 결과 = 판정표(JSON) · 적용은 판정표 또는 --biz.

    python tools/fix_option_split_history.py --output output                                  # 찾기·미리보기(쓰기 없음)
    python tools/fix_option_split_history.py --output output --plan-out 판정표.json            # 판정표 저장
    python tools/fix_option_split_history.py --output output --apply --plan 판정표.json        # 판정표 칸만 적용
    python tools/fix_option_split_history.py --output output --apply --biz "(사업자 시트 이름)"  # 그 사업자 '옮김' 전부

--apply = 마스터를 output/백업/ 에 복사한 뒤 저장 · 앱·무인 실행이 파이프라인 잠금을 쥐고 있으면 멈춤(exit 3).
⚠ 결과 구글시트에는 옛(잘못된) 칸이 남아 있어, 고친 마스터로 시트를 반영하기 전에 앱이 돌면 실행 시작 빈 칸 채움(D-384)이
비운 B 칸을 시트 값으로 다시 채운다 → 적용 뒤 첫 실행 전에 ①고친 마스터를 운용 PC output 에 두고 ②결과 시트 반영(통제 세션).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8")   # type: ignore[union-attr]
except AttributeError:
    pass

from coupang_analytics import config, sales_history  # noqa: E402
from coupang_analytics.date_basis import has_mark  # noqa: E402
from coupang_analytics.pipeline_paths import _master_path  # noqa: E402
from coupang_analytics.registry_lock import RegistryLockError, registry_lock  # noqa: E402
from coupang_analytics.workbook import OutputWorkbook  # noqa: E402
from fill_sales_day_from_output import expected  # noqa: E402  (앱 ① 판매량 규칙 — T-155 도구와 같은 식)

MOVE, CHECK = "옮김 후보", "확인 필요"
_SNAP = re.compile(r"_통계_(\d{6})\.xlsx$")
_BAK = re.compile(r"^통계마스터_(\d{6})_(\d{6})\.xlsx$")
MAX_BACKUPS = 4   # 쌍마다 분리 전 상태를 찾아 볼 백업·스냅샷 수(최신부터)


# ── 마스터 읽기 ────────────────────────────────────────────────────────────────
def label_day(label: str, ref: date, marked: bool) -> str | None:
    """날짜 칸 글자('MM.DD' · 저장 전 메모리 'YYYY-MM-DD') → 판매일 ISO. 년도 = ref(파일 날짜) 기준 가장 가까운 과거 ·
    표시 없는(옛 기준) 파일 = 칸 −1일. 날짜 아님 = None."""
    try:
        if "-" in str(label):
            day = date.fromisoformat(str(label))
        else:
            m, d = (int(x) for x in str(label).split("."))
            day = date(ref.year, m, d)
            if day > ref + timedelta(days=1):
                day = date(ref.year - 1, m, d)
    except ValueError:
        return None
    return (day if marked else day - timedelta(days=1)).isoformat()


def blocks(wb, biz: str) -> list[dict]:
    """사업자 시트의 블록 — 이름·VID·계정·묶음 키·지표행·값 있는 날짜 열."""
    ws, cols = wb.wb[biz], list(wb._date_col.get(biz, {}).values())
    out = []
    for prod in wb.products_of(biz):
        rows = {m: r for (b, p, m), r in wb._metric_row.items() if b == biz and p == prod}
        if config.M_SALES not in rows:
            continue
        filled = {c for c in cols if any(ws.cell(r, c).value not in (None, "") for r in rows.values())}
        out.append({"name": prod, "vids": [str(v) for v in wb.product_vids(biz, prod)], "rows": rows,
                    "aid": wb.product_account_id(biz, prod) or wb.account_id_of(biz) or "", "filled": filled,
                    "keys": {prod.rsplit(" (", 1)[0], wb.registered_name(biz, prod) or prod}})
    return out


def _cells(wb, biz: str, blk: dict, col: int) -> dict:
    ws = wb.wb[biz]
    return {m: ws.cell(r, col).value for m, r in blk["rows"].items()}


def _filled(vals: dict) -> bool:
    return any(v not in (None, "") for v in vals.values())


def _related(b: dict, c: dict) -> bool:
    vb, vc = set(b["vids"]), set(c["vids"])
    return bool(vb and vc and not (vb & vc) and b["aid"] == c["aid"] and (b["keys"] & c["keys"]))


# ── 판정 ─────────────────────────────────────────────────────────────────────
def judge_day(rec: dict | None, v, vb: list[str], vc: list[str]) -> tuple[str, str]:
    """그 날짜 칸 하나 → (판매분석|못 가림|안 맞음, 사유)."""
    if rec is None:
        return "못 가림", "그날 판매분석 기록 없음"
    sb, sc = expected(rec, vb), expected(rec, vc)
    if v is None or v == "":
        return "못 가림", f"판매량 칸 빈 칸(기록 {vc[0]} {sc} · {vb[0]} {sb})"
    if v == sc and v != sb:
        return "판매분석", f"판매량 {v} = VID {'/'.join(vc)} 판매 {sc} ≠ VID {'/'.join(vb)} 판매 {sb}"
    if v == sc == sb:
        return "못 가림", f"판매량 {v} = 두 VID 판매 같음({sc})"
    return "안 맞음", f"판매량 {v} ≠ VID {'/'.join(vc)} 판매 {sc}(VID {'/'.join(vb)} {sb})"


def pair_plan(wb, biz: str, b: dict, c: dict, days: dict, recs: dict) -> dict | None:
    """두 블록 쌍 → 판정(쌍 아님 = None). days = {열: (칸 글자, 판매일)} · recs = 그 계정 판매분석 일별."""
    c_days = [days[col][1] for col in c["filled"] if days.get(col, ("", None))[1]]
    if not c_days:
        return None
    split = min(c_days)                     # C 제 이력의 첫 판매일
    rng = sorted(((days[col][0], col, days[col][1]) for col in b["filled"]
                  if days.get(col, ("", None))[1] and days[col][1] < split), key=lambda x: x[2], reverse=True)
    if not rng:
        return None
    cells = []
    for lab, col, day in rng:
        vals = _cells(wb, biz, b, col)
        kind, why = judge_day(recs.get(day), vals.get(config.M_SALES), b["vids"], c["vids"])
        cells.append({"날짜": lab, "판매일": day, "열": col, "판정": kind, "근거": why,
                      "값": {m: v for m, v in vals.items() if v not in (None, "")}})
    if not any(x["판정"] == "판매분석" for x in cells):
        return None                         # 판매분석으로 가린 날이 없음 = 이 모양 아님(제 이력 그대로인 정상 쌍 포함)
    return {"사업자": biz, "계정": b["aid"], "옮길_블록": b["name"], "옮길_VID": b["vids"], "받을_블록": c["name"],
            "받을_VID": c["vids"], "받을_블록_첫칸": split,
            "판정": CHECK if any(x["판정"] == "안 맞음" for x in cells) else MOVE, "칸": cells}


def _snapshot_files(out: Path, until: str) -> list[tuple[str, Path]]:
    """분리 전 상태를 볼 파일(스냅샷·실행 전 백업) — 날짜 ≤ until 인 것 최신 순."""
    found = []
    for p in out.glob("*_통계_*.xlsx"):
        m = _SNAP.search(p.name)
        if m:
            found.append((f"{m.group(1)}_235959", p))
    for p in (out / "백업").glob("통계마스터_*.xlsx"):
        m = _BAK.match(p.name)
        if m:
            found.append((f"{m.group(1)}_{m.group(2)}", p))
    lim = datetime.strptime(until, "%Y-%m-%d").strftime("%y%m%d")
    return sorted((x for x in found if x[0][:6] <= lim), reverse=True)[:MAX_BACKUPS]


def _by_day(wb, biz: str, blk: dict, ref: date) -> dict:
    marked = has_mark(wb)
    ws = wb.wb[biz]
    out = {}
    for lab, col in wb._date_col[biz].items():
        day = label_day(lab, ref, marked)
        vals = {m: ws.cell(blk["rows"][m], col).value for m in (config.M_SALES, config.M_VIEWS) if m in blk["rows"]}
        if day and _filled(vals):
            out[day] = vals
    return out


def _split_state(wb, biz: str, vb: set, vc: set) -> tuple[str, dict | None]:
    """백업 하나 → ('분리 전', C VID 만 가진 블록) · ('분리 뒤', None)(B VID 블록 있음·C 블록 여럿) · ('더 옛날', None)(둘 다 없음)."""
    if biz not in wb.wb.sheetnames:
        return "더 옛날", None
    bl = blocks(wb, biz)
    xs = [x for x in bl if set(x["vids"]) & vc]
    if any(set(x["vids"]) & vb for x in bl) or len(xs) > 1:
        return "분리 뒤", None
    return ("분리 전", xs[0]) if xs else ("더 옛날", None)


def _same_values(theirs: dict, mine: dict) -> bool:
    """겹치는 판매일이 있고 그날 값(판매량·노출량)이 모두 같음."""
    same = [d for d in theirs if d in mine]
    return bool(same) and all(theirs[d] == {k: v for k, v in mine[d].items() if k in theirs[d]} for d in same)


def backup_evidence(out: Path, pair: dict, mine: dict, cache: dict) -> tuple[set, str]:
    """분리 전 백업·스냅샷에서 'C VID 만 가진 블록'(B VID 블록 없음)의 값이 B 와 다르지 않으면 → (그 블록 값 있는 판매일, 파일 이름)."""
    days = [x["판매일"] for x in pair["칸"] if x["판매일"]]
    if not days:
        return set(), ""
    vb, vc = set(pair["옮길_VID"]), set(pair["받을_VID"])
    for stamp, path in _snapshot_files(out, (date.fromisoformat(max(days)) + timedelta(days=2)).isoformat()):
        if path not in cache:
            cache[path] = OutputWorkbook.load(path)
        state, blk = _split_state(cache[path], pair["사업자"], vb, vc)
        if state == "분리 뒤":
            continue                          # 더 옛 파일로
        if state == "더 옛날" or blk is None:
            break                             # 근거 없음
        theirs = _by_day(cache[path], pair["사업자"], blk, datetime.strptime(stamp[:6], "%y%m%d").date())
        return (set(theirs), path.name) if _same_values(theirs, mine) else (set(), "")
    return set(), ""


def plan_all(out: Path, wb, ref: date, only_biz: str | None = None) -> list[dict]:
    marked = has_mark(wb)
    plans: list[dict] = []
    recs: dict = {}
    cache: dict = {}
    for biz in wb.account_sheets():
        if only_biz and biz != only_biz:
            continue
        days = {col: (lab, label_day(lab, ref, marked)) for lab, col in wb._date_col.get(biz, {}).items()}
        bl = blocks(wb, biz)
        for b in bl:
            for c in bl:
                if b is c or not _related(b, c):
                    continue
                if b["aid"] not in recs:
                    recs[b["aid"]] = sales_history.load_account(out, b["aid"]) if b["aid"] else {}
                p = pair_plan(wb, biz, b, c, days, recs[b["aid"]])
                if p:
                    _settle(out, wb, b, p, ref, cache)
                    plans.append(p)
    return plans


def _settle(out: Path, wb, b: dict, p: dict, ref: date, cache: dict) -> None:
    """칸마다 최종 판정 — 판매분석 = 옮김 · 못 가림 = 백업 근거 있으면 옮김 · 그 밖 = 확인 필요."""
    ev: set = set()
    src = ""
    if p["판정"] == MOVE and any(x["판정"] == "못 가림" for x in p["칸"]):
        ev, src = backup_evidence(out, p, _by_day(wb, p["사업자"], b, ref), cache)
    for x in p["칸"]:
        if p["판정"] == MOVE and x["판정"] == "판매분석":
            x["결정"] = "옮김"
        elif p["판정"] == MOVE and x["판정"] == "못 가림" and x["판매일"] in ev:
            x["결정"], x["근거"] = "옮김", f"{x['근거']} · 백업 {src} 분리 전 VID {'/'.join(p['받을_VID'])} 블록에 같은 값"
        else:
            x["결정"] = "확인 필요"


# ── 출력·적용 ────────────────────────────────────────────────────────────────
def report(plans: list[dict]) -> None:
    moves = sum(1 for p in plans for x in p["칸"] if x["결정"] == "옮김")
    print(f"[옵션 분리 이력] 찾은 쌍 {len(plans)} · 옮길 날짜 칸 {moves} · 확인 필요 칸 "
          f"{sum(1 for p in plans for x in p['칸'] if x['결정'] != '옮김')}")
    for p in plans:
        mv = [x for x in p["칸"] if x["결정"] == "옮김"]
        ck = [x for x in p["칸"] if x["결정"] != "옮김"]
        print(f"  [{p['판정']}] {p['사업자']} ({p['계정']}) '{p['옮길_블록'][:40]}' VID {p['옮길_VID']} → "
              f"'{p['받을_블록'][:40]}' VID {p['받을_VID']} · 받을 블록 첫 칸 {p['받을_블록_첫칸']} · 옮김 {len(mv)}칸"
              + (f"({mv[-1]['날짜']}~{mv[0]['날짜']})" if mv else "") + f" · 확인 필요 {len(ck)}칸")
        for x in ck[:5]:
            print(f"      확인 필요 {x['날짜']}: {x['근거']}")


def select(plans: list[dict], plan_file: Path | None, only_biz: str | None) -> list[tuple[dict, list[dict]]]:
    """적용할 칸 — 판정표(그 쌍·그 날짜 '옮김'만 · 지금 마스터와 다르면 멈춤) 또는 --biz 의 '옮김' 전부."""
    if plan_file is None:
        return [(p, [x for x in p["칸"] if x["결정"] == "옮김"]) for p in plans if p["사업자"] == only_biz]
    now = {(p["사업자"], p["옮길_블록"], p["받을_블록"]): p for p in plans}
    picked = [_pick(now, w) for w in json.loads(plan_file.read_text(encoding="utf-8"))]
    return [x for x in picked if x[1]]


def _pick(now: dict, w: dict) -> tuple[dict, list[dict]]:
    """판정표 쌍 하나 → 지금 마스터로 다시 판정한 같은 쌍의 같은 날짜 '옮김' 칸(하나라도 없으면 멈춤 — 그 사이 마스터가 바뀜)."""
    p = now.get((w["사업자"], w["옮길_블록"], w["받을_블록"])) or {"칸": []}
    labs = {x["날짜"] for x in w["칸"] if x.get("결정") == "옮김"}
    cur = {x["날짜"]: x for x in p["칸"] if x["결정"] == "옮김"}
    if not labs <= set(cur):
        raise ValueError(f"판정표와 지금 마스터가 다름: {w['사업자']} '{w['옮길_블록'][:30]}' {sorted(labs - set(cur))}")
    return p, [cur[lab] for lab in sorted(labs)]


def apply_moves(wb, picked: list[tuple[dict, list[dict]]]) -> int:
    n = 0
    for p, cells in picked:
        biz = p["사업자"]
        ws = wb.wb[biz]
        rows_b = {m: r for (b, pr, m), r in wb._metric_row.items() if b == biz and pr == p["옮길_블록"]}
        rows_c = {m: r for (b, pr, m), r in wb._metric_row.items() if b == biz and pr == p["받을_블록"]}
        for x in cells:
            col = x["열"]
            if any(ws.cell(rows_c[m], col).value not in (None, "") for m in rows_c) or not set(x["값"]) <= set(rows_c):
                raise ValueError(f"받을 칸이 비어 있지 않거나 지표행이 다름: {biz} {p['받을_블록'][:30]} {x['날짜']}")
            for m, r in rows_b.items():
                v = ws.cell(r, col).value
                if v not in (None, ""):
                    ws.cell(rows_c[m], col).value = v
                    ws.cell(r, col).value = None
                    n += 1
    return n


def run(out: Path, a) -> int:
    master = _master_path(out)
    wb = OutputWorkbook.load(master)
    plans = plan_all(out, wb, datetime.fromtimestamp(master.stat().st_mtime).date(), a.biz)
    report(plans)
    if a.plan_out:
        Path(a.plan_out).write_text(json.dumps(plans, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  판정표 저장: {Path(a.plan_out).resolve()}")
    if not a.apply:
        print("  (미리보기 — 마스터 쓰지 않음. 적용하려면 --apply 와 --plan 또는 --biz)")
        return 0
    picked = select(plans, Path(a.plan) if a.plan else None, a.biz)
    if not any(cells for _, cells in picked):
        print("  옮길 칸 없음 — 저장 안 함")
        return 0
    n = apply_moves(wb, picked)
    bak = out / "백업" / f"쿠팡데이타분석_통계_옵션분리이력바로잡기전_{datetime.now():%y%m%d_%H%M%S}.xlsx"
    bak.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(master, bak)
    wb.save(master)
    print(f"  ✅ 옮긴 값 {n}개({sum(len(c) for _, c in picked)}개 날짜 칸) · 저장 {master.resolve()} · 저장 전 백업 {bak.resolve()}")
    print("  다음: ① 고친 마스터를 운용 PC output 에 둠(앱 꺼진 때) ② 첫 실행 전에 결과 구글시트 반영(통제 세션) — "
          "안 하면 실행 시작 빈 칸 채움(D-384)이 시트의 옛 값을 비운 칸에 다시 넣음")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--output", default="output")
    ap.add_argument("--biz", help="이 사업자 시트만(적용 대상 지정)")
    ap.add_argument("--plan", help="적용할 판정표(JSON · --plan-out 으로 만든 것)")
    ap.add_argument("--plan-out", help="찾은 결과 판정표 저장 경로(JSON)")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    if a.apply and not (a.plan or a.biz):
        print("❌ --apply 는 --plan 판정표 또는 --biz 사업자 지정이 필요합니다(대상 지정 없이 전부 적용 안 함)")
        return 2
    out = Path(a.output)
    if not _master_path(out).is_file():
        print(f"❌ 마스터 없음: {_master_path(out)}")
        return 1
    try:
        with registry_lock(out / "_잠금" / "파이프라인.lock", wait_sec=0):
            return run(out, a)
    except RegistryLockError:
        print("⏸ 앱·무인 실행이 도는 중(파이프라인 잠금) — 끝난 뒤 다시 실행하세요")
        return 3
    except ValueError as exc:
        print(f"❌ {exc} — 저장 안 함")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
