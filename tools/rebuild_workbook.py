"""손상된 통계 워크북을 여러 소스에서 **깨끗한 새 워크북으로 재구성**하는 복구 도구.

insert_rows 버그로 run1 계정의 상품명·키워드가 유실된 파일을 복구한다. 데이터 출처:
- 상품명: 숨김 `_상품ID` 시트(생성 순서) — 블록 순서와 1:1(교차검증 후 사용).
- 지표(판매/방문/노출/전체판매/전체노출/재고)·kind(계약/개인): 현재 워크북 블록(행 정렬 보존).
- 키워드: ② 러너 로그(`[사업자] 상품 → 키워드 [...]`, run1) + 현재 워크북 키워드행(resume).
- 검색량: 현재 워크북 F열(있으면) 아니면 네이버 검색광고 API 재조회(로그인 불필요).
- 순위: 전체실행 로그(`[순위] 'kw': 값`, 50위밖→50) — reflect_log_to_excel.parse_log 재사용.

새 OutputWorkbook 에 표준 순서로 다시 쓰고 apply_style(서식 100% 고정). 로그인 없음.

사용: python tools/rebuild_workbook.py [현재.xlsx] [전체실행로그] [②로그]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from coupang_analytics import config  # noqa: E402
from coupang_analytics.workbook import OutputWorkbook  # noqa: E402
from reflect_log_to_excel import parse_log as parse_ranks  # noqa: E402

_CUR = "output/쿠팡데이타분석_통계.xlsx"
_RUNLOG = "output/run_log_260909_190216.log"
_KWLOG = "output/run_stage23.log"
_META = "_상품ID"
_CONTRACT = set(config.CONTRACT_METRICS)   # 판매량·방문자·노출량·재고현황
_PERSONAL = set(config.PERSONAL_METRICS)   # 전체판매량·전체노출량
_ALLM = _CONTRACT | _PERSONAL
_RE_KWLOG = re.compile(r"\[(.+?)\]\s*(.+?)\s*→\s*키워드\s*\[(.*)\]")


def productid_map(wb) -> dict[str, list[tuple[str, str]]]:
    """{사업자: [(상품명, vids문자열)...]} 생성순서."""
    m: dict[str, list[tuple[str, str]]] = {}
    if _META not in wb.wb.sheetnames:
        return m
    ws = wb.wb[_META]
    for r in range(2, ws.max_row + 1):
        b, n, v = ws.cell(r, 1).value, ws.cell(r, 2).value, ws.cell(r, 3).value
        if b and n:
            m.setdefault(b, []).append((n, str(v or "")))
    return m


def parse_blocks(wb, biz):
    """현재 워크북 한 시트 → [{'kind','metrics':{label:val},'kws':[(name,vol)]}] (블록 순서)."""
    ws = wb.wb[biz]
    blocks = []
    cur = None
    in_kw = False
    for r in range(1, ws.max_row + 1):
        c, f, g, h = (ws.cell(r, 3).value, ws.cell(r, 6).value,
                      ws.cell(r, 7).value, ws.cell(r, 8).value)
        if g == "날짜":
            cur = {"metrics": {}, "kws": []}
            blocks.append(cur)
            in_kw = False
        elif cur is not None and g in _ALLM:
            cur["metrics"][g] = h
        elif cur is not None and c == "키워드":
            in_kw = True
        elif cur is not None and in_kw and g == config.M_RANK and c:
            cur["kws"].append((str(c), f))
    return blocks


def parse_kwlog(path):
    """② 로그 → {(사업자, 상품): [키워드...]}."""
    out: dict[tuple[str, str], list[str]] = {}
    if not Path(path).exists():
        return out
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        m = _RE_KWLOG.search(line)
        if m:
            biz, prod, kws = m.group(1).strip(), m.group(2).strip(), m.group(3)
            kw = [x.strip().strip("'\"") for x in kws.split(",") if x.strip()]
            if kw:
                out[(biz, prod)] = kw
    return out


def naver_volumes(keywords):
    """네이버로 키워드 검색량 재조회 → {키워드: 검색량}. 실패/미발견은 생략."""
    if not keywords:
        return {}
    import json
    from coupang_analytics.credstore import CredStore
    from coupang_analytics.kw_volume import NaverAdApi, NaverCredentials
    nj = CredStore().get_password("__naver__")
    if not nj:
        print("[복구] ⚠ 네이버 키 없음 — 검색량 재조회 생략")
        return {}
    d = json.loads(nj)
    api = NaverAdApi(NaverCredentials(d["customer_id"], d["api_key"], d["secret_key"]))
    vol: dict[str, int] = {}
    hints = list(dict.fromkeys(keywords))
    for i in range(0, len(hints), 5):     # 5개씩 힌트로 던져 연관+자신 검색량 회수
        batch = hints[i:i + 5]
        try:
            for kv in api.related_keywords_multi(batch):
                vol.setdefault(kv.keyword.replace(" ", ""), kv.total)
        except Exception as exc:
            print(f"[복구] 네이버 조회 실패(계속) {batch[:2]}… {exc.__class__.__name__}")
    return {k: vol.get(k.replace(" ", "")) for k in keywords}


def main():
    args = sys.argv[1:]
    cur = args[0] if len(args) > 0 else _CUR
    runlog = args[1] if len(args) > 1 else _RUNLOG
    kwlog = args[2] if len(args) > 2 else _KWLOG

    src = OutputWorkbook.load(cur)
    idmap = productid_map(src)
    ranks = {}   # (biz, prod, kw) -> rank
    for biz, prod, kw, rank in parse_ranks(runlog):
        ranks[(biz, prod, kw)] = rank
    kwlog_map = parse_kwlog(kwlog)

    # 1) 모든 계정·상품 데이터 수집(현재 순서), 교차검증
    plan = []   # [(biz, name, kind, metrics, [(kw, vol)], vids)]
    need_vol = []
    mism = []
    for biz in src.account_sheets():
        blocks = parse_blocks(src, biz)
        entries = idmap.get(biz, [])
        for i, b in enumerate(blocks):
            name = entries[i][0] if i < len(entries) else None
            vids = entries[i][1] if i < len(entries) else ""
            if name is None:
                mism.append((biz, i, "상품ID없음"))
                continue
            kind = config.KIND_CONTRACT if (set(b["metrics"]) & _CONTRACT) else config.KIND_PERSONAL
            # 키워드: ②로그 우선(run1), 없으면 현재 워크북 키워드행(resume)
            kws = kwlog_map.get((biz, name)) or [k for k, _v in b["kws"]]
            wbvol = {k: v for k, v in b["kws"]}
            kv = []
            for k in dict.fromkeys(kws):
                v = wbvol.get(k)
                if v in (None, "", 0):
                    need_vol.append(k)
                kv.append([k, v])
            plan.append((biz, name, kind, b["metrics"], kv, vids))
    if mism:
        print(f"[복구] ⚠ 상품ID 매칭 실패 {len(mism)}건: {mism[:5]}")

    # 2) 검색량 없는 키워드만 네이버 재조회
    print(f"[복구] 검색량 재조회 대상 키워드 {len(set(need_vol))}개(네이버)…")
    got = naver_volumes(list(set(need_vol)))
    for _b, _n, _k, _m, kv, _v in plan:
        for pair in kv:
            if pair[1] in (None, "", 0) and got.get(pair[0]):
                pair[1] = got[pair[0]]

    # 3) 새 워크북 생성(표준 순서·서식)
    date = None
    for biz in src.account_sheets():
        date = src.latest_date(biz)
        if date:
            break
    out = OutputWorkbook.empty()
    for biz in src.account_sheets():   # 빈 계정 시트도 보존(상품 0개여도 계정 유지)
        out.ensure_account(biz)
    for biz, name, kind, metrics, kv, vids in plan:
        out.ensure_account(biz)
        out.ensure_product_block(biz, name, kind, [k for k, _v in kv])
        if vids:
            out.set_product_vids(biz, name, [x for x in vids.split("|") if x])
        for label, val in metrics.items():
            if val not in (None, ""):
                out.set_product_metric(biz, name, label, date, val)
        for k, v in kv:
            if v not in (None, "", 0):
                out.set_keyword_search(biz, name, k, v)
            r = ranks.get((biz, name, k))
            if r is not None:
                out.set_keyword_rank(biz, name, k, date, r)
    out.apply_style()
    out.save(cur)
    snap = Path(cur).with_name(f"{config.OUTPUT_FILE_PREFIX}_통계_260909.xlsx")
    out.save(str(snap))
    print(f"[복구] 완료 — 계정 {len(out.account_sheets())} · 상품 {len(plan)} · 순위 {sum(1 for p in plan for k,_ in p[4] if (p[0],p[1],k) in ranks)}개 반영")
    print(f"[복구] 저장: {cur} + {snap.name}")


if __name__ == "__main__":
    main()
