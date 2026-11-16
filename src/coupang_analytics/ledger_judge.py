"""장부 DB 판정(D-265) — 규칙 파일(판정표)을 읽어 검증 결과(check_result) 줄에 원인을 붙인다.

- 규칙 = Claude 가 유형별로 판정해 판정표 파일 `판정/규칙_*.json` 에 근거·원문과 함께 적은 것. 코드는 일반 조건 함수만 갖고,
  어떤 조건을 어느 검사에 쓸지는 규칙 파일이 정한다(계정·상품·금액 조건 금지 D-229 — 규칙 파라미터에 그런 칸이 있으면 중단).
- 순서: 규칙 파일 차례·규칙 차례대로, 아직 원인 없는 줄에만 조건을 적용 → 맞으면 cause = 'R-xx 적용'.
- 규칙마다 표본(20줄 · 20줄 미만이면 전부)을 `판정/표본_R-xx.json` 에 근거 값과 함께 쓴다 → Claude 가 다시 확인해 규칙 파일
  `recheck` 칸에 기록(프로그램 결과를 그대로 확정하지 않음). 규칙 밖 줄 = `판정/규칙밖.json` → Claude 직접 판정 파일
  `판정/직접판정_*.json` 이 있으면 그 판정을 옮긴다(cause = 'AI 판정: …'). 판정은 judgment 표에도 남긴다.
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Callable

from .ledger_verify import CFS_REF, rg_line_pay

SAMPLE_N = 20
_RULE_KEYS = ("id", "applies", "condition", "verdict", "basis", "quote", "judged_by", "date")
# D-229: 규칙은 자료 조건(칸 값·금액 관계)만 — 특정 계정·상품·주문·금액을 지목하는 파라미터 금지.
_FORBIDDEN_PARAMS = {"account", "account_id", "accounts", "option_id", "option_ids", "product_id", "order_no",
                     "vendor_id", "amount", "amounts", "subject", "subjects"}
_COST_NOT_RG = "kind NOT LIKE '윙%' AND kind != '라이브 수수료'"
_COMP = "totalCfsInventoryCompensationAmount"

Row = tuple   # check_result 줄: (check_name, account_id, subject, expected, actual, diff, bucket, cause)
Cond = Callable[[sqlite3.Connection, list, dict], dict]


def _pk(r: Row) -> tuple[str, str, str]:
    return r[0], r[1], r[2]


# ── 공용 조회 ──
def _round(con, acc: str, subj: str) -> tuple | None:
    """V4 subject('윙 {rk}' · '로켓그로스 {rk}') → (sale_type, round_key, period_start, period_end, ratio, payable, final)."""
    st, _, rk = subj.partition(" ")
    return con.execute("SELECT sale_type, round_key, period_start, period_end, ratio, payable, final FROM pay_round "
                       "WHERE account_id=? AND sale_type=? AND round_key=?", (acc, st, rk)).fetchone()


def _line_range(con) -> dict[tuple[str, str], tuple[str, str, int]]:
    """(계정, 정산 파일 종류) → (첫 줄 날짜, 마지막 줄 날짜, 줄 수)."""
    return {(a, s): (lo, hi, n) for a, s, lo, hi, n in con.execute(
        "SELECT account_id, src, MIN(recognized), MAX(recognized), COUNT(*) FROM order_line "
        "WHERE src IN ('주문상세','판매수수료') AND recognized != '' GROUP BY account_id, src")}


def _src_of(sale_type: str) -> str:
    return "주문상세" if sale_type == "윙" else "판매수수료"


def _ref_entries(con, acc: str, rk: str) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for item, amt in con.execute("SELECT item, amount FROM account_entry WHERE account_id=? AND round_key=? "
                                 "AND role='대조용'", (acc, rk)):
        out[item] += amt
    return out


# ── 조건 함수(일반 조건만) — 맞는 줄의 KEY → 근거 값 ──
def c_before_first_line(con, rows: list, params: dict) -> dict:
    """회차 기간 끝 < 그 계정 같은 판매방식 정산 파일 첫 줄 날짜, 또는 그 계정 정산 파일 줄 0 · 그리고 계산값 0."""
    rng = _line_range(con)
    out = {}
    for r in rows:
        rd = _round(con, r[1], r[2])
        if rd is None or r[4] not in (0, None):
            continue
        first = rng.get((r[1], _src_of(rd[0])))
        if first is None or rd[3] < first[0]:
            out[_pk(r)] = {"기간": f"{rd[2]}~{rd[3]}", "정산 파일 첫 줄": first[0] if first else "줄 0",
                           "쿠팡 값": r[3], "계산값": r[4]}
    return out


def _cycle_cost_rows(con, acc: str, pe: str) -> int:
    n = con.execute(f"SELECT COUNT(*) FROM product_cost WHERE account_id=? AND cycle_end=? AND {_COST_NOT_RG}",
                    (acc, pe)).fetchone()[0]
    return n + con.execute("SELECT COUNT(*) FROM account_entry WHERE account_id=? AND round_key=?",
                           (acc, f"cycle:{pe}")).fetchone()[0]


def c_cost_report_missing(con, rows: list, params: dict) -> dict:
    """로켓그로스 회차: 그 정산주기 비용 리포트 줄 0개(상품 비용·세액 모두) · 주기 끝 < 그 계정 비용 리포트 첫 주기(받기 전 ·
    중간에 빠진 주기는 해당 없음) · 차 = ⑮ 비용 칸 합 − 재고 보상(원 단위)."""
    first = dict(con.execute(f"SELECT account_id, MIN(cycle_end) FROM product_cost WHERE {_COST_NOT_RG} "
                             f"GROUP BY account_id"))
    out = {}
    for r in rows:
        rd = _round(con, r[1], r[2])
        if rd is None or rd[0] != "로켓그로스" or r[5] is None:
            continue
        if _cycle_cost_rows(con, r[1], rd[3]) or (first.get(r[1]) or "9999") <= rd[3]:
            continue
        ref = _ref_entries(con, r[1], rd[1])
        cfs = sum(ref.get(k, 0) for k in CFS_REF if k != _COMP)
        comp = ref.get(_COMP, 0)
        if cfs and r[5] == cfs - comp:
            out[_pk(r)] = {"정산주기 끝": rd[3], "비용 리포트 줄": 0, "⑮ 비용 칸 합": cfs, "재고 보상": comp, "차": r[5]}
    return out


def c_rounding_within_lines(con, rows: list, params: dict) -> dict:
    """차이(원) ≤ 회차 기간 정산 줄 수 — 줄마다 반올림이 최대 1원이라 생길 수 있는 범위(방식 확정 아님)."""
    out = {}
    for r in rows:
        rd = _round(con, r[1], r[2])
        if rd is None or r[5] is None:
            continue
        n = con.execute("SELECT COUNT(*) FROM order_line WHERE account_id=? AND src=? AND recognized BETWEEN ? AND ?",
                        (r[1], _src_of(rd[0]), rd[2], rd[3])).fetchone()[0]
        if 0 < abs(r[5]) <= n:
            out[_pk(r)] = {"기간": f"{rd[2]}~{rd[3]}", "지급비율": rd[4], "정산 줄 수": n, "차": r[5]}
    return out


def _cost_groups(con) -> dict[tuple, tuple]:
    """겹친 비용 KEY 묶음 → (줄 수, 파일 수, 시트 수, 파일ID, 시트, 행 수)."""
    q = (f"SELECT account_id, kind, cycle_end, file_stage, nat_key, COUNT(*), COUNT(DISTINCT file_id), "
         f"COUNT(DISTINCT sheet), MIN(file_id), MIN(sheet), COUNT(DISTINCT src_row) FROM product_cost "
         f"WHERE {_COST_NOT_RG} GROUP BY account_id, kind, nat_key, cycle_end, file_stage HAVING COUNT(*) > 1")
    return {(a, f"{k}|{c}|{s}|{n}"): rest for a, k, c, s, n, *rest in con.execute(q)}


def _sheet_sums(con) -> dict[tuple[int, str], tuple[int, int | None, int]]:
    """(파일, 시트) → (상세 줄 합, 요약 최종비용, 요약 세액)."""
    det = {(f, s): a for f, s, a in con.execute(
        f"SELECT file_id, sheet, SUM(amount) FROM product_cost WHERE {_COST_NOT_RG} GROUP BY file_id, sheet")}
    summ: dict[tuple, list] = defaultdict(lambda: [None, 0])
    for fid, pos, item, amt in con.execute("SELECT file_id, src_pos, item, amount FROM account_entry "
                                           "WHERE item LIKE '비용 요약 최종비용%' OR item LIKE '비용 세액%'"):
        k = (fid, pos.split("!")[0])
        if item.startswith("비용 요약"):
            summ[k][0] = amt
        else:
            summ[k][1] += amt
    return {k: (v, summ[k][0] if k in summ else None, summ[k][1] if k in summ else 0) for k, v in det.items()}


def _same_sheet(groups: dict, r: Row) -> tuple | None:
    """겹친 줄이 모두 같은 파일·같은 시트의 서로 다른 행이면 그 묶음, 아니면 None."""
    g = groups.get((r[1], r[2]))
    return g if g is not None and g[1] == 1 and g[2] == 1 and g[5] == g[0] else None


def c_cost_overlap_summary_match(con, rows: list, params: dict) -> dict:
    """겹친 비용 KEY 줄이 모두 같은 파일·같은 시트의 다른 행 · 그 시트 상세 줄 합(겹친 줄 포함) = 요약 최종비용 − 세액."""
    groups, sums = _cost_groups(con), _sheet_sums(con)
    out = {}
    for r in rows:
        g = _same_sheet(groups, r)
        if g is None or (g[3], g[4]) not in sums:
            continue
        det, fin, tax = sums[(g[3], g[4])]
        if fin is not None and det == fin - tax:
            out[_pk(r)] = {"파일ID": g[3], "시트": g[4], "겹친 줄": g[0], "상세 합": det, "요약 최종비용": fin, "세액": tax}
    return out


def c_cost_overlap_cycle_zero(con, rows: list, params: dict) -> dict:
    """겹친 비용 KEY 줄이 모두 같은 파일·시트의 다른 행 · 그 시트 요약 없음 · 그 정산주기 'V4 RG 비용 = ⑮' 검사가 전부 차 0."""
    groups, sums = _cost_groups(con), _sheet_sums(con)
    out = {}
    for r in rows:
        g = _same_sheet(groups, r)
        if g is None or (g[3], g[4]) not in sums or sums[(g[3], g[4])][1] is not None:
            continue
        cyc = r[2].split("|", 3)[1]
        bs = [b for (b,) in con.execute(
            "SELECT c.bucket FROM check_result c JOIN pay_round p ON p.account_id=c.account_id "
            "AND c.subject = p.sale_type || ' ' || p.round_key WHERE c.check_name='V4 RG 비용 = ⑮ 비용 칸' "
            "AND c.account_id=? AND p.period_end=?", (r[1], cyc))]
        if bs and all(b == "0" for b in bs):
            out[_pk(r)] = {"파일ID": g[3], "시트": g[4], "겹친 줄": g[0], "정산주기 끝": cyc, "⑮ 대조 회차": len(bs)}
    return out


def c_sales_after_last_round(con, rows: list, params: dict) -> dict:
    """주문별매출 줄의 구매확정일이 모두 그 계정 윙 정산 회차(보류 해제 뺌) 마지막 기간 끝보다 뒤, 또는 그 계정 윙 회차 0."""
    last = dict(con.execute("SELECT account_id, MAX(period_end) FROM pay_round WHERE sale_type='윙' AND release=0 "
                            "GROUP BY account_id"))
    out = {}
    for r in rows:
        order, item, tt = r[2].split("|", 2)
        ds = [d for (d,) in con.execute("SELECT recognized FROM order_line WHERE src='주문별매출' AND account_id=? "
                                        "AND order_no=? AND item_key=? AND txn_type=?", (r[1], order, item, tt))]
        end = last.get(r[1])
        if ds and all(d for d in ds) and (end is None or min(ds) > end):
            out[_pk(r)] = {"구매확정일": min(ds), "윙 마지막 회차 기간 끝": end or "회차 0", "줄": len(ds)}
    return out


def c_option_one_inventory(con, rows: list, params: dict) -> dict:
    """노출상품ID 가 2개 이상인 옵션의 등록상품ID 가 정확히 1개(옵션ID·등록상품ID 같음 = 같은 상품)."""
    out = {}
    for r in rows:
        inv = [i for (i,) in con.execute("SELECT DISTINCT inventory_id FROM option_attr WHERE account_id=? "
                                         "AND option_id=? AND inventory_id != ''", (r[1], r[2]))]
        if len(inv) == 1:
            n = con.execute("SELECT COUNT(DISTINCT product_id) FROM option_attr WHERE account_id=? AND option_id=? "
                            "AND product_id != ''", (r[1], r[2])).fetchone()[0]
            out[_pk(r)] = {"등록상품ID 수": 1, "노출상품ID 수": n}
    return out


def c_labels_end_with_account(con, rows: list, params: dict) -> dict:
    """계정 표기가 여럿이어도 모두 마지막 '-' 뒤 = 계정ID · vendorId 1개 이하(같은 계정)."""
    out = {}
    for r in rows:
        a = con.execute("SELECT names, vendor_ids FROM account WHERE account_id=?", (r[1],)).fetchone()
        if a is None:
            continue
        names, vids = json.loads(a[0] or "[]"), [v for v in a[1].split(",") if v]
        if names and all(n.rsplit("-", 1)[-1] == r[1] for n in names) and len(vids) <= 1:
            out[_pk(r)] = {"표기 수": len(names), "모두 끝 = 계정ID": True, "vendorId 수": len(vids)}
    return out


CONDITIONS: dict[str, Cond] = {
    "before_first_line": c_before_first_line,
    "cost_report_missing": c_cost_report_missing,
    "rounding_within_lines": c_rounding_within_lines,
    "cost_overlap_summary_match": c_cost_overlap_summary_match,
    "cost_overlap_cycle_zero": c_cost_overlap_cycle_zero,
    "sales_after_last_round": c_sales_after_last_round,
    "option_one_inventory": c_option_one_inventory,
    "labels_end_with_account": c_labels_end_with_account,
}


# ── 규칙 파일 ──
def _check_rule(rule: dict, src: str) -> None:
    miss = [k for k in _RULE_KEYS if not rule.get(k)]
    if miss:
        raise ValueError(f"{src} {rule.get('id')}: 빠진 칸 {miss}")
    if not re.fullmatch(r"R-J\d-\d{2}", rule["id"]):
        raise ValueError(f"{src}: 규칙 번호 형식 'R-J숫자-두자리' 아님 {rule['id']}")
    cond = rule["condition"]
    if cond.get("name") not in CONDITIONS:
        raise ValueError(f"{src} {rule['id']}: 모르는 조건 {cond.get('name')}")
    bad = _FORBIDDEN_PARAMS & set(cond.get("params") or {})
    if bad:
        raise ValueError(f"{src} {rule['id']}: 계정·상품·금액 조건 금지(D-229) {sorted(bad)}")
    ap = rule["applies"]
    if not ap.get("check_names") or not ap.get("buckets"):
        raise ValueError(f"{src} {rule['id']}: applies 에 check_names·buckets 필요")


def load_rules(folder: Path) -> list[dict]:
    rules, seen = [], set()
    for p in sorted(Path(folder).glob("규칙_*.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        for rule in doc.get("rules", []):
            _check_rule(rule, p.name)
            if rule["id"] in seen:
                raise ValueError(f"{p.name}: 규칙 번호 중복 {rule['id']}")
            seen.add(rule["id"])
            rules.append({**rule, "_file": p.name})
    if not rules:
        raise FileNotFoundError(f"규칙 파일 없음: {folder}\\규칙_*.json")
    return rules


def _candidates(con, rule: dict) -> list:
    ap = rule["applies"]
    qn, qb = ",".join("?" * len(ap["check_names"])), ",".join("?" * len(ap["buckets"]))
    return con.execute(f"SELECT * FROM check_result WHERE check_name IN ({qn}) AND bucket IN ({qb}) "
                       f"AND (cause = '' OR cause = '확인 필요') ORDER BY check_name, account_id, subject",
                       (*ap["check_names"], *ap["buckets"])).fetchall()


def _sample(keys: list) -> list:
    if len(keys) <= SAMPLE_N:
        return keys
    step = len(keys) / SAMPLE_N
    return [keys[int(i * step)] for i in range(SAMPLE_N)]


def _write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def _apply_rule(con, rule: dict, folder: Path) -> dict:
    rows = _candidates(con, rule)
    hit = CONDITIONS[rule["condition"]["name"]](con, rows, rule["condition"].get("params") or {})
    cause = f"{rule['id']} 적용"
    con.executemany("UPDATE check_result SET cause=? WHERE check_name=? AND account_id=? AND subject=?",
                    [(cause, *k) for k in hit])
    con.execute("INSERT OR REPLACE INTO judgment VALUES ('규칙', ?, ?, ?, ?, ?, ?)",
                (rule["id"], rule["verdict"], rule["basis"], rule["quote"], rule["judged_by"], rule["_file"]))
    by_row = {_pk(r): r for r in rows}
    sample = [{"check_name": k[0], "account_id": k[1], "subject": k[2], "expected": by_row[k][3],
               "actual": by_row[k][4], "diff": by_row[k][5], "근거": hit[k]} for k in _sample(sorted(hit))]
    _write_json(folder / f"표본_{rule['id']}.json", {"rule": rule["id"], "verdict": rule["verdict"],
                                                    "적용 줄": len(hit), "표본": sample})
    rc = rule.get("recheck") or {}
    return {"id": rule["id"], "file": rule["_file"], "후보": len(rows), "적용": len(hit), "표본": len(sample),
            "재확인": f"{rc.get('ok', '?')}/{rc.get('n', '?')} 맞음 · 틀림 {rc.get('wrong', '?')}" if rc else "재확인 전"}


def _direct(con, folder: Path) -> int:
    """Claude 직접 판정 파일(직접판정_*.json · items[check_name, account_id, subject, verdict, reason, quote])을 옮긴다."""
    n = 0
    for p in sorted(folder.glob("직접판정_*.json")):
        for it in json.loads(p.read_text(encoding="utf-8")).get("items", []):
            for k in ("check_name", "account_id", "subject", "verdict", "reason"):
                if k not in it:
                    raise ValueError(f"{p.name}: 빠진 칸 {k}")
            cur = con.execute("UPDATE check_result SET cause=? WHERE check_name=? AND account_id=? AND subject=? "
                              "AND (cause = '' OR cause = '확인 필요')",
                              (f"AI 판정: {it['verdict']}", it["check_name"], it["account_id"], it["subject"]))
            if cur.rowcount != 1:
                raise ValueError(f"{p.name}: 판정 대상 줄 없음 또는 이미 판정됨 {it['check_name']} · {it['subject']}")
            con.execute("INSERT OR REPLACE INTO judgment VALUES (?,?,?,?,?,?,?)",
                        (it.get("kind", "직접"), f"{it['check_name']}|{it['account_id']}|{it['subject']}",
                         it["verdict"], it["reason"], it.get("quote", ""), "Claude", p.name))
            n += 1
    return n


def _leftover(con, rules: list[dict], folder: Path) -> list:
    scope = sorted({(c, b) for r in rules for c in r["applies"]["check_names"] for b in r["applies"]["buckets"]})
    left = []
    for c, b in scope:
        left += con.execute("SELECT * FROM check_result WHERE check_name=? AND bucket=? AND (cause = '' OR "
                            "cause = '확인 필요') ORDER BY account_id, subject", (c, b)).fetchall()
    _write_json(folder / "규칙밖.json", [dict(zip(("check_name", "account_id", "subject", "expected", "actual", "diff",
                                                  "bucket", "cause"), r)) for r in left])
    return left


def run(con: sqlite3.Connection, folder: Path) -> list[str]:
    folder = Path(folder)
    rules = load_rules(folder)
    con.execute("UPDATE check_result SET cause='' WHERE cause LIKE 'R-%' OR cause LIKE 'AI 판정:%'")
    con.execute("DELETE FROM judgment")
    stats = [_apply_rule(con, r, folder) for r in rules]
    direct = _direct(con, folder)
    left = _leftover(con, rules, folder)
    con.commit()
    out = [f"판정: 규칙 {len(rules)}개 · 규칙 적용 줄 {sum(s['적용'] for s in stats):,} · AI 직접 판정 줄 {direct} · "
           f"규칙 밖(남음) {len(left)} → {folder / '규칙밖.json'}"]
    out += [f"  {s['id']}({s['file']}): 후보 {s['후보']:,} · 적용 {s['적용']:,} · 표본 {s['표본']} · {s['재확인']}"
            for s in stats]
    left_by: dict[tuple, int] = defaultdict(int)
    for r in left:
        left_by[(r[0], r[6])] += 1
    out += [f"  남음 {c} · {b}: {n}" for (c, b), n in sorted(left_by.items())]
    return out


__all__ = ["CONDITIONS", "load_rules", "run", "rg_line_pay"]
