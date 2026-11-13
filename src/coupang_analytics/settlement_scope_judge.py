"""정산 대상 상품 출처 AI 판정 — 후보 추출(프로그램) → AI 판정(프롬프트 PROMPT) → 결과 검사·판정표(프로그램) (D-230 · D-231).

소유자 2026-11-13: "상품 판정은 AI가 최종 확정하고 그 이후부터는 프로그램이 처리, AI 판정시 프롬프트를 잘 설계해야 함."
- 프로그램은 후보와 근거 자료를 모아 계정마다 요청 묶음(packet)을 만들 뿐 같은 상품인지 정하지 않는다(코드에 계정·상품 조건 없음 D-229).
- AI 답은 `check_answer` 가 검사한다: 판정 대상 등록상품ID·허용 출처·판정만 · 근거 비면 안 됨 · '원문'은 묶음 자료 글에 그대로 있어야 함.
- 통과한 답만 입력 폴더 `관리상품_출처판정.json`(settlement_statement_scope.SOURCE)이 되고, 그 뒤 정산서는 프로그램이 처리한다.

근거 자료(순위 = D-230): ① 옛 PC 관리대장 엑셀(계정·상품 칸만 · 비밀번호·연락처 칸은 읽지 않음) ② 원장 '상품이력' 시트
③ 계약 DB '품목' 시트(계약자 ↔ 계정 = 대응표의 사업자·대표자 이름이 계약 당사자 이름과 같은 계약만 후보 · 같은 사람인지는 AI 판정).
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import openpyxl

from coupang_analytics import settlement_statement_scope as SCOPE

ACCT_COLS = ("아이디", "계정아이디", "계정 아이디", "계정명", "계정ID")
PROD_COLS = ("상품명", "상품")
CTX_COLS = ("사업자명", "계약여부", "계약수량", "계약일", "시작일", "계약종료일", "비고")
VERDICTS = (SCOPE.KEEP[0], SCOPE.CHECK)

PROMPT = """너는 위탁 판매 정산에서 '정산 대상 상품'을 판정한다. 결과는 위탁자에게 보내는 정산서 금액이 되므로 추측하지 않는다.

[입력] 계정 하나의 묶음(JSON):
- 계정: 계정ID · 사업자 · 대표자
- 판정대상: 이 계정에 쿠팡 등록된 상품 중 지금 관리대장(VID·같은 상품명)에 없는 상품 — 등록상품ID · 상품명(등록명) · 노출명(고객용 제목) · 등록일 · 판매방식(RFM=로켓그로스, NORMAL=판매자배송)
- 근거자료(순위 순서): ① 옛대장(옛 PC 관리대장 엑셀 줄) ② 이력원장(원장 '상품이력' 줄) ③ 계약서(계약 품목 줄 · 계약자 이름 · 계약일)

[할 일] 판정대상 상품마다, 근거자료 줄 중 '같은 상품'을 가리키는 줄이 있는지 ①→②→③ 순서로 찾는다.
- 찾으면 처음 찾은 순위의 출처 하나만 적는다(① 에서 찾으면 ②③ 은 보지 않아도 됨).
- 어느 근거자료에도 없는 상품은 답에 넣지 않는다(다음 단계 규칙이 따로 처리함).

[같은 상품 기준 — 앱의 관리대장↔쿠팡 상품 AI 매칭(product_match_ai.MATCH_SYSTEM)과 같은 방식]
배경: 계약서 품목명·관리대장 상품명은 담당자가 쓴 일반 이름(약칭)이다(예: '보호대', '목마사지기', '전자제품'). 쿠팡 등록명·노출명은
길고 꾸밈말이 많다(예: '디프 4헤드 9단 저주파 목마사지기 …'). 같은 상품을 여러 번 다시 등록해 등록상품ID 가 여럿일 수 있다.
1. 이름이 같은지 먼저 본다 — 근거 줄 이름이 판정대상 상품명과 띄어쓰기·대소문자만 다르면 같은 상품.
2. 같은 이름이 없으면 글자 모양이 아니라 문구 전체의 의미로 판단한다 — '무엇을 하는, 어떤 종류의 상품'인지(용도·대상·형태)가 같으면
   같은 상품. 글자가 겹쳐도 의미가 다르면 다른 상품('요가매트' ≠ '요가 양말'), 글자가 달라도 의미가 같으면 같은 상품
   ('목마사지기' = '디프 4헤드 9단 저주파 목마사지기', '수면 안대' = '숙면 아이마스크 빛 차단 수면안대').
3. 오타·띄어쓰기·브랜드 유무·꾸밈말(프리미엄·MAX·신형)·색상·사이즈·수량(1개/2개 묶음)은 의미에 영향 없음.
4. 모델 코드(영문+숫자)는 보조 근거일 뿐이다. 판정대상 상품명에 모델 코드가 없어도 의미가 같으면 같은 상품이다.
   단 근거 줄과 판정대상 둘 다 모델 코드가 있고 서로 다르면(예: TTGW02 · TTGW03) 다른 상품으로 본다.
5. 한 근거 줄의 의미에 맞는 판정대상이 여럿이면(다시 등록한 같은 상품) 모두 같은 출처로 적는다.
6. ③ 계약서는 계약자 이름(상호·대표)이 이 계정의 사업자·대표자와 같은 사람·사업자일 때만 근거가 된다.
7. '확인 필요'는 의미로도 같은 종류인지 정할 수 없을 때만 쓴다(예: 근거 이름이 '전자제품'처럼 상품 종류를 알 수 없는 말뿐 ·
   계약자가 이 계정과 같은 사람인지 묶음으로 알 수 없음). 모델 코드가 없다는 이유만으로 '확인 필요'로 두지 않는다.
8. 묶음에 없는 정보(기억·상식으로 아는 브랜드 등)는 근거로 쓰지 않는다. 위탁자 본인 상품인지는 이 단계에서 판정하지 않는다.

[답 형식] JSON 하나만(설명 글 없이):
{"계정ID": "<계정ID>", "판정": [{"등록상품ID": "<판정대상의 ID>", "상품명": "<판정대상 상품명>", "출처": "옛 대장|이력원장|계약서",
  "판정": "관리|확인 필요", "근거": "<어느 줄인지(파일·시트·행 또는 문서ID) + 왜 같은 상품인지 · 확인 필요면 무엇이 모자란지>",
  "원문": "<근거자료 줄의 글 일부를 그대로 복사(고치지 말 것)>"}]}
- '관리' = 같은 상품이 확실함. '확인 필요' = 같은 상품일 수 있으나 기준 1~5로 확정 못 함.
- 등록상품ID 는 판정대상에 있는 것만 · 한 상품은 한 번만 적는다.
"""


# ── ① 옛 PC 관리대장 ──
def _header(rows: list, known: set) -> tuple[int, int, int, dict] | None:
    """(머리 줄 번호, 계정 칸, 상품 칸, {참고 칸 이름: 칸}) — 계정 칸 후보가 여럿이면 값이 아는 계정ID 와 가장 많이 맞는 칸."""
    for hi, r in enumerate(rows[:10]):
        names = {str(c).strip(): k for k, c in enumerate(r) if c is not None}
        accts = [names[n] for n in ACCT_COLS if n in names]
        prod = next((names[n] for n in PROD_COLS if n in names), None)
        if accts and prod is not None:
            body = rows[hi + 1:]
            best = max(accts, key=lambda k: sum(str(x[k]).strip() in known for x in body if k < len(x) and x[k]))
            return hi, best, prod, {n: names[n] for n in CTX_COLS if n in names}
    return None


def old_ledger_rows(paths: list[Path], known: set) -> dict:
    """{계정ID: [{"파일", "시트", "행", "상품", 참고 칸…}]} — 계정·상품·참고 칸만 읽음(비밀번호·연락처 칸은 꺼내지 않음)."""
    out: dict = defaultdict(list)
    for p in paths:
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        for ws in wb.worksheets:
            rows = [list(r) for r in ws.iter_rows(values_only=True)]
            h = _header(rows, known)
            if h is None:
                continue
            hi, ac, pc, ctx = h
            for i, r in enumerate(rows[hi + 1:], start=hi + 2):
                aid = str(r[ac]).strip() if ac < len(r) and r[ac] else ""
                prod = str(r[pc]).strip() if pc < len(r) and r[pc] else ""
                if aid in known and prod:
                    out[aid].append({"파일": p.name, "시트": ws.title, "행": i, "상품": prod,
                                     **{n: str(r[k]).strip() for n, k in ctx.items() if k < len(r) and r[k] not in (None, "")}})
        wb.close()
    return dict(out)


# ── ② 이력원장 '상품이력' ──
def history_rows(rows: list) -> dict:
    """원장 '상품이력' 줄(머리줄 + 줄) → {계정ID: [{"번호", "효력일", "상품명", "변동유형", "이전값", "변경값", "출처"}]}."""
    if not rows:
        return {}
    h = {str(c): k for k, c in enumerate(rows[0])}
    keep = ("번호", "효력일", "상품명", "변동유형", "이전값", "변경값", "출처")
    out: dict = defaultdict(list)
    for r in rows[1:]:
        r = list(r) + [""] * len(h)
        aid = str(r[h["계정아이디"]]).strip()
        if aid and r[h["상품명"]]:
            out[aid].append({k: str(r[h[k]]) for k in keep if k in h and r[h[k]] not in (None, "")})
    return dict(out)


# ── ③ 계약 DB ──
def _norm(s) -> str:
    return re.sub(r"\(주\)|㈜|주식회사|\s", "", str(s or ""))


def contract_rows(db: Path, people: dict) -> dict:
    """계약 DB v4 → {계정ID: [{"문서ID", "파일명", "계약자", "계약자 대표", "계약일", "품목명", "모델", "수량"}]}.
    people = {계정ID: (사업자, 대표자)} · 계약 '계약자측' 당사자의 명칭·대표 중 하나가 이름 글자로 같으면 후보(같은 사람인지는 AI)."""
    wb = openpyxl.load_workbook(db, read_only=True, data_only=True)
    sheets = {n: _sheet(wb, n) for n in ("당사자", "계약 통합", "품목")}
    wb.close()
    party, cdate = _parties(*sheets["당사자"]), _dates(*sheets["계약 통합"])
    keys = {aid: {_norm(x) for x in pair if _norm(x)} for aid, pair in people.items()}
    ih, irow = sheets["품목"]
    out: dict = defaultdict(list)
    for r in irow:
        doc = r[ih["문서ID"]]
        for name, rep in party.get(doc, []):
            for aid in (a for a, ks in keys.items() if ks & ({_norm(name), _norm(rep)} - {""})):
                out[aid].append({"문서ID": str(doc), "파일명": str(r[ih["파일명"]] or ""), "계약자": name, "계약자 대표": rep,
                                 "계약일": cdate.get(doc, ""), "품목명": str(r[ih["품목명(원문)"]] or ""),
                                 "모델": str(r[ih["모델"]] or ""), "수량": str(r[ih["수량"]] or "")})
    return {aid: [dict(t) for t in {tuple(sorted(x.items())) for x in v}] for aid, v in out.items()}


def _sheet(wb, name: str) -> tuple[dict, list]:
    rows = list(wb[name].iter_rows(values_only=True))
    return {str(c): k for k, c in enumerate(rows[0])}, rows[1:]


def _parties(h: dict, rows: list) -> dict:
    """{문서ID: [(계약자측 명칭, 대표)]}."""
    out: dict = defaultdict(list)
    for r in rows:
        if r[h["구분"]] == "계약자측":
            out[r[h["문서ID"]]].append((str(r[h["명칭"]] or ""), str(r[h["대표"]] or "")))
    return out


def _dates(h: dict, rows: list) -> dict:
    return {r[h["문서ID(누르면 원문 PDF)"]]: str(r[h["계약일(서명일)"]] or "")[:10] for r in rows}


# ── 판정대상 ──
def targets(aid: str, inv_all: dict, groups: dict, is_mv, vname: dict) -> list:
    """쿠팡 등록 상품(상품조회 + 판매분석) 중 1순위(대장 VID·같은 상품명)에 없는 것 — 판매 방식 안 가림(③ 계약서 = D-231).
    상품명 = 등록명 · 노출명 = 판매 기록의 고객용 제목(VID 별 · vname = settlement_statement_scope.vid_names)."""
    out = {}
    for pid, e in (inv_all.get(aid) or {}).items():
        if not any(is_mv(v) for v in e["types"]):
            out[pid] = {"등록상품ID": pid, "상품명": e["name"], "노출명": sorted({vname[v] for v in e["types"] if vname.get(v)}),
                        "등록일": e["created"], "판매방식": sorted(set(e["types"].values()) - {None})}
    for g, e in groups.items():
        if g not in out and g not in (inv_all.get(aid) or {}) and not any(is_mv(v) for v in e["vids"]):
            out[g] = {"등록상품ID": g, "상품명": e["name"], "노출명": sorted({vname[v] for v in e["vids"] if vname.get(v)}),
                      "등록일": "", "판매방식": ["RFM"] if e["rg"] else ["NORMAL"]}
    return [out[k] for k in sorted(out)]


def packet(aid: str, person: tuple, tg: list, old: list, hist: list, cons: list) -> dict:
    return {"계정": {"계정ID": aid, "사업자": person[0], "대표자": person[1]}, "판정대상": tg,
            "근거자료": {"① 옛대장": old, "② 이력원장": hist, "③ 계약서": cons}}


# ── AI 답 검사 → 판정표 ──
def _texts(pk: dict) -> str:
    return "\n".join(json.dumps(r, ensure_ascii=False) for rows in pk["근거자료"].values() for r in rows)


def check_answer(pk: dict, ans: dict) -> tuple[dict, list]:
    """(받은 판정 {등록상품ID: 항목}, 오류 글 목록) — 오류가 하나라도 있으면 그 계정 답은 판정표에 넣지 않는다."""
    errs, got = [], {}
    aid = pk["계정"]["계정ID"]
    ids = {t["등록상품ID"] for t in pk["판정대상"]}
    texts = _texts(pk)
    if ans.get("계정ID") != aid:
        errs.append(f"계정ID 다름: {ans.get('계정ID')!r} ≠ {aid!r}")
    for e in ans.get("판정") or []:
        pid = str(e.get("등록상품ID") or "")
        bad = [m for m, ok in (("판정대상에 없는 등록상품ID", pid in ids), ("한 상품 두 번", pid not in got),
                               ("허용 안 된 출처", e.get("출처") in (SCOPE.OLD, SCOPE.HIST, SCOPE.CONTRACT)),
                               ("허용 안 된 판정", e.get("판정") in VERDICTS), ("근거 없음", bool(str(e.get("근거") or "").strip())),
                               ("원문이 근거자료에 없음", bool(str(e.get("원문") or "").strip()) and str(e.get("원문")).strip() in texts)) if not ok]
        if bad:
            errs.append(f"{pid}: {' · '.join(bad)}")
            continue
        got[pid] = {k: e[k] for k in ("출처", "판정", "상품명", "근거", "원문") if k in e}
    return got, errs
