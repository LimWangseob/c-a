"""셀독 정산서 배치 작업(D-399 레인 D · T-25 4단계) — 상품군 위탁정산서(groups) → 셀독 정산서(make) 를 한 번에.

`run_job(opts, on_log) -> {"ok": [id], "skipped": [건너뜀], "files": [경로], "group_files": [경로], "abort": str|None}`
- 건너뜀 = {"id", "reason", "kind"(건너뜀|확인 필요), "aid", "doc_id", "product_id", "상품명", "금액", "사유"} — 로그를 읽지 않아도
  운용자가 알 수 있게(소유자 11-24 '확인필요는 로그를 분석해야 만 인식됨') · 관리대장에 없는 상품 등 = 상품 단위 줄(id = 계정ID:상품:등록상품ID).
- 계약별 격리: 판정 없음·규칙 밖 유형·DB 에 없음·위탁정산서 1개 아님·같은 이름 파일·투자형 남은 지급 근거 없음(판정표 '남은지급확인')
  = 그 계약만 skipped · 나머지 계약은 만든다(고객용 정산서에 '확인 필요' 같은 내부 글자를 쓰지 않음 · D-221 ②).
  미확정 계약이 있는 계정의 나머지 계약 = 상품군 정산서로만(계정 전체 숫자를 한 계약에 몰지 않음 · `SS.Skip.held`).
- abort = 입력 자체가 없을 때만(셀독 입력 폴더의 판정표·사업자 대응표·계약 DB 사본 없음 · DB '관리대상' 칸 없음 · 날짜 틀림).
- strict(손 실행 기본) = 예전처럼 막는 사유가 하나라도 있으면 아무 파일도 만들지 않고 abort.
- 입력 위치 기본 = `<root>\\output\\정산서\\입력_셀독\\`(판정표·대응표·계약 DB 사본 `계약서_정밀분석_DB*.xlsx` 1개) · `seldoc_inputs`·`db` = 덮어쓰기용.
숫자 계산 없음 — 쿠팡 숫자 = 위탁정산서 결과 파일(D-225 ①) · 개별 판정 = 판정표 파일(D-229).

opts: root · seldoc_inputs · db · accounts(없으면 `SS.auto_accounts`) · statements(위탁정산서 결과 폴더) · out · basis · issued ·
      group_statements(상품군 정산서 폴더 · 기본 out\\상품군) · groups(dict = 위탁정산서 인자 managed_output·settle_dir·stats·inputs·
      settle_only·supp·snap·account_history·only → 주면 상품군 정산서를 이번에 만듦) · steps(("groups", "make") 기본) · strict(False) ·
      skip_accounts({계정명 '대표자-사업자-계정ID': 사유} = 정산 받기 실패 → 그 계정은 안 만들고 skipped)
배치 꼴(레인 A `statement_batch._job_opts` · 칸 consignor = 위탁 단계 결과): statements = consignor.out · groups = 배치 칸 managed_output·
settle_dir·stats·inputs(원장 계정이력·정산전용상품 = 구글 실시간 읽기 · 사본 안 만듦 D-399) · 위탁이 중단이면 abort.
"""
from __future__ import annotations

import filecmp
import shutil
import traceback
from datetime import date, datetime
from pathlib import Path

from coupang_analytics import settlement_seldoc_groups as G
from coupang_analytics import settlement_seldoc_sheet as SH
from coupang_analytics import settlement_seldoc_source as SS
from coupang_analytics import settlement_statement_context as CTX
from coupang_analytics.settlement_statement_book import safe_name
from coupang_analytics.statement_jobs_consignor import skip_ids

INPUT_DIR = ("output", "정산서", "입력_셀독")
DB_GLOB = "계약서_정밀분석_DB*.xlsx"
GROUP_DIR = "상품군"
PREFIX = "시작 전 중단 — "
GROUP_KEYS = ("managed_output", "settle_dir", "stats", "inputs", "settle_only", "supp", "snap", "account_history", "only")
BATCH_GROUP_KEYS = ("managed_output", "settle_dir", "stats", "inputs")      # 배치(_job_opts)가 넘기는 상품군 인자


def default_inputs(root: Path) -> Path:
    return Path(root).joinpath(*INPUT_DIR)


def find_db(inputs: Path) -> Path:
    """셀독 입력 폴더의 계약 DB 사본 — 정확히 1개(없거나 여럿 = 시작 전 중단)."""
    found = sorted(p for p in inputs.glob(DB_GLOB) if p.is_file())
    if len(found) != 1:
        raise SS.SeldocInputError(f"{PREFIX}{inputs} 계약 DB 사본({DB_GLOB}) {len(found)}개(1개여야 함)")
    return found[0]


def resolve_inputs(opts: dict) -> tuple[Path, Path]:
    """(셀독 입력 폴더, 계약 DB) — 덮어쓰기 인자 > 기본 위치(root)."""
    inp = opts.get("seldoc_inputs")
    if inp is None:
        if opts.get("root") is None:
            raise SS.SeldocInputError(f"{PREFIX}셀독 입력 폴더를 모름(root 또는 seldoc_inputs 필요)")
        inp = default_inputs(opts["root"])
    inp = Path(inp)
    db = Path(opts["db"]) if opts.get("db") is not None else find_db(inp)
    if not db.is_file():
        raise SS.SeldocInputError(f"{PREFIX}계약 DB {db} 없음")
    return inp, db


def _why(exc: Exception) -> str:
    msg = str(exc)
    return msg.removeprefix(PREFIX) if isinstance(exc, SS.SeldocInputError) else f"{type(exc).__name__}: {msg}"


def _sid(aid: str, doc: str) -> str:
    return f"{aid}:{doc}" if doc else aid


class _Result:
    def __init__(self) -> None:
        self.ok: list[str] = []
        self.skipped: list[dict] = []
        self.files: list[str] = []
        self.group_files: list[str] = []
        self.blocked: list[str] = []          # 막는 사유(strict = 이게 있으면 아무것도 안 씀) — 원래 문장

    def skip(self, aid: str, doc: str, reason: str, *, blocking: bool = True, wait: str = "", product: tuple = (),
             unsure: bool = False) -> None:
        if wait:
            shown, kind = f"확인 필요 — 소유자 결정 대기({wait}) · {reason}", "확인 필요"
        elif blocking and not unsure:
            shown, kind = reason, "건너뜀"
        else:
            shown, kind = f"확인 필요 — {reason}", "확인 필요"
        pid, name, amount = (product + (None, None, None))[:3]
        if pid:
            kind = "확인 필요"
        row = {"id": f"{aid}:상품:{pid}" if pid else _sid(aid, doc), "reason": shown, "kind": kind, "aid": aid,
               "doc_id": doc or None, "product_id": pid, "상품명": name, "금액": amount, "사유": shown}
        row.update(account=aid, contract=doc or "", product=name or "", amount="" if amount is None else amount)   # 확인 필요 탭 칸(레인 A)
        self.skipped.append(row)
        if blocking:
            self.blocked.append(reason)

    def out(self, abort: str | None = None) -> dict:
        return {"ok": self.ok, "skipped": self.skipped, "files": self.files, "group_files": self.group_files, "abort": abort}


def _batch(opts: dict) -> dict:
    """배치 꼴(레인 A 약속 · 칸 consignor 있음) → 이 모듈 칸. 손 실행(consignor 없음) = 그대로. 위탁 중단·결과 없음 = SeldocInputError."""
    if "consignor" not in opts:
        return opts
    cons = opts["consignor"] or {}
    if cons.get("abort") or cons.get("state") == "중단" or not cons.get("out"):
        raise SS.SeldocInputError(f"{PREFIX}위탁정산서 단계 중단 — {cons.get('abort') or '위탁 결과 폴더 없음'}")
    groups = {k: opts[k] for k in BATCH_GROUP_KEYS if opts.get(k)}
    return {**opts, "statements": cons["out"], "groups": groups}


def _load(opts: dict):
    inp, db = resolve_inputs(opts)
    judge, people, contracts = SS.load_judge(inp), SS.load_people(inp), SS.load_contracts(db)
    judge["유형"] = SS.load_types(inp)
    basis = opts["basis"]
    date.fromisoformat(basis)
    issued = opts.get("issued") or f"{date.today():%Y-%m-%d}"
    date.fromisoformat(issued)
    return judge, people, contracts, basis, issued


def _group_args(opts: dict, out: Path, basis: str, issued: str) -> CTX.StatementArgs:
    g = dict(opts["groups"])
    unknown = set(g) - set(GROUP_KEYS)
    if unknown:
        raise SS.SeldocInputError(f"{PREFIX}상품군 인자 모름 {sorted(unknown)}")
    g["only"] = tuple(g.get("only") or ())
    g.update({k: Path(v) for k, v in g.items() if k != "only" and v is not None})      # 배치 = 글자 경로
    return CTX.StatementArgs(out=out, basis=basis, issued=issued, **g)


def _groups(opts: dict, jobs: list, judge: dict, held: dict, res: _Result, on_log, basis: str, issued: str) -> dict | None:
    """상품군 정산서를 이번에 만듦 → {(계정ID, 문서ID): 경로} · 못 만든 계정 = 그 계정 split 계약 전부 skipped. groups 인자 없음 = None."""
    if not opts.get("groups") or not any(j.split for j in jobs):
        return None
    gdir = Path(opts.get("group_statements") or Path(opts["out"]) / GROUP_DIR)
    made, failed, notes = G.run(_group_args(opts, gdir, basis, issued), jobs, judge, gdir, held, on_log)
    for aid, items in notes.items():                                  # 판정표 확인 필요(판매 0 · 판정표 갱신 필요) = 한 줄 · 계정 안 막음
        for pid, why, name, amount in items:
            res.skip(aid, "", f"{aid} 관리 상품 {pid} {name or ''} — {why}", blocking=False, product=(pid, name, amount))
    for aid, doc, p, g in made:
        res.group_files.append(str(p))
        on_log(f"  {aid} {doc[:8]} G {g:,} → {p}")
    for aid, f in failed.items():
        for pid, why, name, amount in f["products"]:
            res.skip(aid, "", f"{aid} 관리 상품 {pid} {name or ''} — {why}", product=(pid, name, amount))
    for j in jobs:
        if j.split and j.aid in failed:
            res.skip(j.aid, j.contract.doc_id, f"{j.aid} 계약 {j.contract.doc_id} 상품군 정산서 못 만듦 — {failed[j.aid]['reason']}",
                     unsure=failed[j.aid]["wait"])
    return {(aid, doc): p for aid, doc, p, _ in made}


def _statement(opts: dict, job, made: dict | None) -> Path:
    if job.split:
        if made is not None:
            p = made.get((job.aid, job.contract.doc_id))
            if p is None:
                raise SS.SeldocInputError(f"{PREFIX}{job.aid} 계약 {job.contract.doc_id} 상품군 정산서 이번에 못 만듦")
            return p
        if opts.get("group_statements") is None:
            raise SS.SeldocInputError(f"{PREFIX}{job.aid} 계약이 {job.contract.doc_id} 등 여럿 — --group-statements 필요")
        p = G.group_path(Path(opts["group_statements"]), job.aid, job.contract.doc_id)
        if not p.is_file():
            raise SS.SeldocInputError(f"{PREFIX}{job.aid} 계약 {job.contract.doc_id} 상품군 정산서 없음 {p}")
        return p
    st = Path(opts["statements"])
    found = sorted(st.glob(f"정산서_*_{job.aid}_관리상품.xlsx"))
    if len(found) != 1:
        raise SS.SeldocInputError(f"{PREFIX}{job.aid} 위탁정산서 {len(found)}개(1개여야 함) · {st}")
    return found[0]


def _perf(opts: dict, job, made: dict | None):
    if job.form == SS.INVEST and job.paid is None:
        raise SS.SeldocInputError(f"{PREFIX}{job.aid} 계약 {job.contract.doc_id} 투자형인데 판정표 '지급완료' 금액 없음")
    if job.form not in ("", SS.INVEST):
        raise SS.SeldocInputError(f"{PREFIX}{job.aid} 계약 {job.contract.doc_id} 판정표 '양식' {job.form!r} 모름")
    pf = SS.read_statement(_statement(opts, job, made))
    if pf.aid != job.aid:
        raise SS.SeldocInputError(f"{PREFIX}{job.aid} 위탁정산서의 쿠팡 계정이 {pf.aid}")
    if job.split and any(x for _, x in pf.extras):
        raise SS.SeldocInputError(f"{PREFIX}{job.aid} 쿠팡 별도 보상(상품 구분 없음)은 계약별로 나눌 수 없음")
    return pf


def file_name(job, basis: str, stamp: str) -> str:
    """셀독정산서_{계약자}_{계약일 yymmdd}_{첫 품목}[외N]_{기준일}기준_{stamp}.xlsx (이름 규칙 그대로)."""
    c = job.contract
    first = safe_name(c.items[0][0])[:14] if c.items else "품목없음"
    tag = f"{c.signed[2:].replace('-', '')}_{first}" + (f"외{len(c.items) - 1}" if len(c.items) > 1 else "")
    who = safe_name(job.people[1] or job.people[0])
    return f"셀독정산서_{who}_{tag}_{basis.replace('-', '')}기준_{stamp}.xlsx"


def _names(ready: list, out: Path, basis: str, stamp: str, res: _Result) -> list:
    """같은 이름이 되는 계약 = 모두 skipped(이름 규칙 그대로 · 어느 쪽이 그 이름인지 모름) · 이미 있는 파일 = skipped(덮지 않음)."""
    by: dict = {}
    for j, pf in ready:
        by.setdefault(file_name(j, basis, stamp), []).append((j, pf))
    keep = []
    for name, group in by.items():
        if len(group) > 1:
            docs = ", ".join(j.contract.doc_id[:8] for j, _ in group)
            for j, _ in group:
                res.skip(j.aid, j.contract.doc_id, f"{j.aid} 계약 {j.contract.doc_id} 셀독 정산서 이름이 계약 {len(group)}건({docs})과 같음 — {name}")
        elif (out / name).exists():
            j = group[0][0]
            res.skip(j.aid, j.contract.doc_id, f"{j.aid} 계약 {j.contract.doc_id} 같은 이름 파일 있음(덮지 않음) — {out / name}")
        else:
            keep.append((name,) + group[0])
    return keep


def _plan(opts: dict, people: dict, contracts: dict, judge: dict, res: _Result) -> tuple[list, dict]:
    bad = skip_ids(opts)
    aids = list(opts.get("accounts") or SS.auto_accounts(people, contracts, judge))
    for aid in [a for a in aids if a in bad]:
        res.skip(aid, "", f"{aid} 정산 받기 실패로 끝난 계정 — 정산서 안 만듦{' — ' + bad[aid] if bad[aid] else ''}")
    aids = [a for a in aids if a not in bad]
    jobs, skips = SS.plan_isolated(people, contracts, judge, aids)
    held: dict = {}
    for s in skips:
        res.skip(s.aid, s.doc, s.reason, blocking=s.blocking, wait=s.wait, unsure=s.unsure)
        if s.held and s.doc:
            held.setdefault(s.aid, []).append(s.doc)
    return jobs, held


def _write(ready: list, out: Path, basis: str, issued: str, res: _Result, on_log) -> None:
    for name, j, pf in ready:
        try:
            p = SH.write(out / name, j.contract, pf, basis, issued, note=j.note, paid=j.paid if j.form == SS.INVEST else None)
        except FileExistsError as exc:
            res.skip(j.aid, j.contract.doc_id, f"{j.aid} 계약 {j.contract.doc_id} 같은 이름 파일 있음(덮지 않음) — {exc}")
            continue
        c = j.contract
        target = SS.goal_total(c.amount, c.profit)
        on_log(f"{j.aid} {c.doc_id[:8]} {c.signed} 목표 {target:,} · 실적 {pf.result:,} · 도달율 {SS.reach(pf.result, c.amount, c.profit):.1%}"
               f" · 남은 {max(target - pf.result, 0):,} → {p}")
        res.ok.append(_sid(j.aid, c.doc_id))
        res.files.append(str(p))


def _read_all(opts: dict, jobs: list, made: dict | None, res: _Result, on_log) -> list:
    """skipped 아닌 계약마다 위탁정산서(또는 상품군 정산서) 읽기 → [(Job, Perf)] · 읽기 오류 = 그 계약만 skipped(사유 보고)."""
    done = {s["id"] for s in res.skipped}
    ready = []
    for j in jobs:
        if _sid(j.aid, j.contract.doc_id) in done:
            continue
        if j.form == SS.INVEST and j.left_check:                     # 고객용 정산서에 내부 글자를 쓰지 않음(D-221 ②) = 만들지 않고 확인 필요 탭
            res.skip(j.aid, j.contract.doc_id, f"{j.aid} 투자형 계약 {j.contract.doc_id} 남은 지급 근거 없음 — {j.left_check}"
                     " (판정표 '남은지급확인' · 정산서 안 만듦)", unsure=True)
            continue
        try:
            ready.append((j, _perf(opts, j, made)))
        except Exception as exc:                                     # 계약 하나의 읽기 오류 = 그 계약만 skipped(삼키지 않음)
            if not isinstance(exc, SS.SeldocInputError):
                on_log(traceback.format_exc().rstrip())
            res.skip(j.aid, j.contract.doc_id, _why(exc))
    return ready


def run_job(opts: dict, on_log=print) -> dict:
    """셀독 정산서 배치 1회(위 docstring). 예외를 밖으로 내지 않고 결과 dict 로 돌려준다(abort = 입력 없음)."""
    res = _Result()
    steps = tuple(opts.get("steps") or ("groups", "make"))
    strict = bool(opts.get("strict"))

    def stop() -> dict | None:                                       # strict = 막는 사유가 하나라도 있으면 아무것도 안 씀
        return res.out(PREFIX + res.blocked[0]) if strict and res.blocked else None

    try:
        opts = _batch(opts)
        judge, people, contracts, basis, issued = _load(opts)
    except (SS.SeldocInputError, ValueError, KeyError) as exc:
        return res.out(str(exc) if str(exc).startswith(PREFIX) else f"{PREFIX}{_why(exc)}")
    jobs, held = _plan(opts, people, contracts, judge, res)
    made = None
    if (s := stop()) is None and "groups" in steps:
        try:
            made = _groups(opts, jobs, judge, held, res, on_log, basis, issued)
        except SS.SeldocInputError as exc:
            return res.out(str(exc))
        s = stop()
    if s is not None or "make" not in steps:
        return s or res.out()
    out = Path(opts["out"])
    ready = _names(_read_all(opts, jobs, made, res, on_log), out, basis, datetime.now().strftime("%y%m%d_%H%M%S"), res)
    if (s := stop()) is not None:                                     # 모두 읽고 맞는지 본 뒤에만 파일을 씀
        return s
    _write(ready, out, basis, issued, res, on_log)
    on_log(f"셀독 정산서 {len(res.files)}개 → {out} · 건너뜀 {len(res.skipped)}건")
    return res.out()


def install_inputs(dest: Path, judge_dir: Path, db: Path) -> list[str]:
    """셀독 입력(판정표·사업자 대응표·계약 DB 사본 · 있으면 유형 판정표)을 dest 에 복사(1회 준비 · 원본 그대로 · 덮어쓰기 없음).
    이미 같은 내용 = 그대로 · 다른 내용·다른 이름의 DB 사본이 이미 있음 = SeldocInputError(손으로 옮긴 뒤 다시)."""
    types = [SS.TYPES] if (Path(judge_dir) / SS.TYPES).is_file() else []      # 선택 파일(없음 = 규칙 밖 유형은 그 계약만 건너뜀 · load_types)
    pairs = [(Path(judge_dir) / n, n) for n in (SS.JUDGE, CTX.MAP_CSV, *types)] + [(Path(db), Path(db).name)]
    for src, _ in pairs:
        if not src.is_file():
            raise SS.SeldocInputError(f"{PREFIX}{src} 없음")
    if not Path(db).match(DB_GLOB):
        raise SS.SeldocInputError(f"{PREFIX}계약 DB 이름이 {DB_GLOB} 꼴이 아님 — {db}")
    dest = Path(dest)
    other = [p for p in dest.glob(DB_GLOB) if p.name != Path(db).name]
    if other:
        raise SS.SeldocInputError(f"{PREFIX}{dest} 에 다른 계약 DB 사본 {[p.name for p in other]} 있음(덮지 않음 · 옮긴 뒤 다시)")
    done = []
    for src, name in pairs:
        to = dest / name
        if to.exists():
            if not filecmp.cmp(src, to, shallow=False):
                raise SS.SeldocInputError(f"{PREFIX}{to} 이미 있고 내용이 다름(덮지 않음)")
            done.append(f"같음 {to}")
            continue
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, to)
        done.append(f"복사 {src} → {to}")
    return done
