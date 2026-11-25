"""위탁정산서 배치 실행 경로(레인 B · D-399 계획 설계 3·5·6) — 옛 위탁정산서 xlsx → 새 형식 위탁자정산서 json + 검산 → 검산 통과분만 구글시트.

정산 프로그램 `statements` 명령(레인 A `statement_batch`)이 자식 프로세스에서 `run_job(opts, on_log)` 을 부른다. exe 에는 tools 가 안 들어가므로
도구 본체(옛 `tools/settlement_consignor.py` 의 고르기·검산·저장·시트 쓰기)를 여기로 옮겼다(위치만 · 계산 바꾸지 않음). 도구 2개는 얇은 껍데기.

- 계정별 격리: 계정 하나가 예외를 내면 그 계정만 skipped(사유) · 나머지는 계속(소유자 11-24 '성공 계정만 생성').
- 계약 종료 계정(D-427 · 지금 관리대장에 계정 없음 = 옛 형식 '정산서 없음') = 새 형식도 안 만들고 실패·'확인 필요'로도 안 올림(로그 한 줄).
- 입력 자동 선택(`pick_inputs`): 정산집계 = 정산 폴더의 최신 `정산집계_*.xlsx` · 관리기준 = output 루트 · 기준일·발행일 = 실행일 ·
  손 입력 = `output/정산서/입력/`(고정 이름 없으면 abort).
- 시트: 판매 달마다 파일 1개(D-241 ⑥) · 주소 = opts['sheets'] 또는 입력 폴더 `위탁자정산서_시트.json` {"YYYY-MM": 주소} ·
  그 달 시트가 없으면 '확인 필요 — 시트 없음(T-43)'(새 달 파일 만들기 = 소유자 OAuth 1회 뒤 · 발송 없음).

반환 꼴(레인 사이 약속): {"ok": [계정ID], "skipped": [issue], "files": [경로], "abort": str | None, "sheet": 주소 | None, "sheets": {달: 주소}} ·
issue = {"id", "account", "contract", "month", "product", "amount", "reason"}(건마다 1줄 · 한 계정이 여러 줄일 수 있음 · 통제 세션 11-24 요구).
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path

from coupang_analytics import settlement_consignor_gsheet as GS
from coupang_analytics import settlement_consignor_month as CM
from coupang_analytics import settlement_statement_context as CTX
from coupang_analytics import settlement_statement_source as SRC

OUT_DIR = "위탁자정산서"
SHEETS_FILE = "위탁자정산서_시트.json"
STATS_GLOB = "정산집계_*.xlsx"
NO_SHEET = "확인 필요 — 시트 없음(T-43)"
SKIP_REASON = "정산 받기 실패 계정 — 건너뜀"


# ── 옛 tools/settlement_consignor.py 본체(위치만 옮김) ─────────────────
def pick_accounts(accts: list[str], wanted: list[str]) -> list[str]:
    """정산집계 계정 이름 목록에서 계정ID 로 고름(비면 전부) · 못 찾은 ID 가 있으면 중단(조용히 빼지 않음)."""
    if not wanted:
        return list(accts)
    by_id = {SRC.aid_of(a): a for a in accts}
    missing = [w for w in wanted if w not in by_id]
    if missing:
        raise ValueError(f"정산집계에 없는 계정ID: {missing}")
    return [by_id[w] for w in wanted]


def statement_failures(data: dict) -> list[str]:
    """숫자 쪽 검산(1원 이상 차이) + 그리기 쪽 검산(합계) — 빈 목록 = 통과."""
    out = [f"{c['검사']} 차이 {c.get('차이', c.get('검산(실제 = 정산금액 − 공제 − 판매 조정)'))}" for c in CM.failed_checks(data)]
    return out + GS.check(data)


def account_months(src: dict, month: str) -> list[str]:
    months = CM.sale_months(src)
    return [month] if month else months


def _why(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {exc}"


def build_all(ctx, accts: list[str], month: str, judge: CM.ConsignorJudge, log=print) -> tuple[list[dict], list[tuple]]:
    """계정 × 판매 달 → ([{account, month, data, failures}], [(계정ID, 달 또는 '', 사유)]) — 계정마다 기존 계산 1번.
    계정(또는 그 달) 하나의 예외 = 그 계정(달)만 실패 목록에 · 나머지는 계속(계정별 격리)."""
    out, failed = [], []
    for acct in accts:
        try:
            src = CM.account_source(ctx, acct)
            months = account_months(src, month)
        except Exception as exc:  # noqa: BLE001 — 계정 하나의 오류 = 그 계정만 실패(사유 보고) · 다른 계정은 계속
            failed.append((SRC.aid_of(acct), "", _why(exc)))
            log(f"❌ {SRC.aid_of(acct)} 위탁자정산서 못 만듦 — {_why(exc)}")
            continue
        for m in months:
            try:
                data = CM.build_month(None, src, m, judge)
                fails = statement_failures(data)
            except Exception as exc:  # noqa: BLE001 — 그 달만 실패(사유 보고)
                failed.append((src["aid"], m, _why(exc)))
                log(f"❌ {src['aid']} {m} 위탁자정산서 못 만듦 — {_why(exc)}")
                continue
            out.append({"account": src["aid"], "month": m, "data": data, "failures": fails})
            log(f"{'✅' if not fails else '❌'} {src['aid']} {m} 정산 {data['settle_amount']:,} · 확정 전 {data['pending_total']:,}"
                + (f" · 검산 실패 {len(fails)}" if fails else ""))
    return out, failed


def summary_row(r: dict) -> dict:
    d = r["data"]
    return {"계정": r["account"], "달": r["month"], "상태": d["status"], "판매 금액": d["lines"][0]["amount"],
            "상품 정산액": d["product_subtotal"], "9 반영": d["common"]["total_applied"],
            "10 별도": sum(x["amount"] for x in d["separate"]), "이번 정산 금액": d["settle_amount"],
            "확정 전": d["pending_total"], "검산 실패": r["failures"]}


def json_path(out: Path, r: dict) -> Path:
    return out / OUT_DIR / f"{r['account']}_{r['month'].replace('-', '')}.json"


def save(results: list[dict], out: Path) -> Path:
    folder = out / OUT_DIR
    folder.mkdir(parents=True, exist_ok=True)
    for r in results:
        json_path(out, r).write_text(json.dumps(r["data"], ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (folder / "_요약.json").write_text(json.dumps([summary_row(r) for r in results], ensure_ascii=False, indent=1, default=str),
                                     encoding="utf-8")
    return folder


def write_sheet(sheet: str, results: list[dict], issued: str, log=print, client=None) -> None:
    if client is None:
        from coupang_analytics.gsheet_api import GSheetClient   # 시트를 쓸 때만(오프라인 실행은 구글 모듈 안 읽음)
        client = GSheetClient(sheet, on_log=log)
    plan = GS.write_statement(client, [r["data"] for r in results], issued, log=log)
    log(f"✅ 시트 반영 — 탭 {len(plan.tabs)}개")


# ── 입력 자동 선택 ───────────────────────────────────────────
def latest_file(folder: Path, pattern: str) -> Path | None:
    """이름 순 마지막(파일 이름의 yymmdd_hhmmss 순서 = 만든 순서)."""
    got = sorted(p for p in folder.glob(pattern) if p.is_file()) if folder.is_dir() else []
    return got[-1] if got else None


def _opt_path(opts: dict, key: str) -> Path | None:
    v = opts.get(key)
    return Path(v) if v else None


def _path(opts: dict, key: str, default: Path) -> Path:
    return _opt_path(opts, key) or default


def pick_inputs(opts: dict) -> tuple[CTX.StatementArgs | None, list[str], str | None]:
    """opts → (StatementArgs, 안내 줄, abort 사유). 빠진 입력(손 입력·정산집계·정산 폴더) = abort 에 이름."""
    output = Path(opts.get("output") or opts["managed_output"])
    today = f"{date.today():%Y-%m-%d}"
    basis, issued = opts.get("basis") or today, opts.get("issued") or today
    settle_dir = _path(opts, "settle_dir", output / "정산")
    inputs = _path(opts, "inputs", output / "정산서" / "입력")
    stats = _opt_path(opts, "stats") or latest_file(settle_dir, STATS_GLOB)
    out = _path(opts, "out", output / "정산서" / f"위탁정산서_{date.fromisoformat(issued):%y%m%d}")
    miss = [f"정산 폴더 {settle_dir}"] if not settle_dir.is_dir() else []
    miss += [f"입력 {n}" for n in CTX.missing_inputs(inputs)]
    if stats is None or not stats.is_file():
        miss.append(f"정산집계 파일({settle_dir / STATS_GLOB})")
    if miss:
        return None, [], f"입력 없음 — {', '.join(miss)}"
    notes = [f"정산집계 = {stats.name} · 기준일 {basis} · 발행 {issued} · 입력 = {inputs}"]
    so = _opt_path(opts, "settle_only")
    notes.append(f"정산전용상품 = {'사본 ' + so.name if so else '구글 실시간 읽기'}")
    args = CTX.StatementArgs(out=out, managed_output=_path(opts, "managed_output", output), settle_dir=settle_dir, stats=stats,
                             basis=basis, inputs=inputs, issued=issued, settle_only=so,
                             only=tuple(opts.get("only") or ()))
    return args, notes, None


def sheet_map(opts: dict, inputs: Path) -> dict:
    """{판매 달 YYYY-MM: 시트 주소·ID} — opts['sheets'] 우선 · 없으면 입력 폴더의 선택 파일 · 둘 다 없으면 빈 표."""
    if opts.get("sheets") is not None:
        return dict(opts["sheets"])
    p = inputs / SHEETS_FILE
    if not p.is_file():
        return {}
    return {k: v for k, v in json.loads(p.read_text(encoding="utf-8")).items() if not k.startswith("_") and v}


# ── 실행 ────────────────────────────────────────────────────
class _Lines(io.TextIOBase):
    """print 출력을 줄마다 on_log 로(옛 도구의 print 를 그대로 보고에 남김). on_log 를 부를 땐 원래 stdout 으로 되돌림
    (on_log 가 print 여도 되돌아 들어오지 않음)."""

    def __init__(self, on_log: Callable[[str], None]):
        self.on_log, self.buf, self.orig = on_log, "", sys.stdout

    def _emit(self, line: str) -> None:
        with contextlib.redirect_stdout(self.orig):
            self.on_log(line)

    def write(self, s: str) -> int:
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            self._emit(line)
        return len(s)

    def flush(self) -> None:
        if self.buf:
            self._emit(self.buf)
            self.buf = ""


def _xlsx(args: CTX.StatementArgs, skip: tuple, on_log) -> tuple[dict | None, str | None]:
    from coupang_analytics import settlement_statements as ST
    w = _Lines(on_log)
    try:
        with contextlib.redirect_stdout(w):
            return ST.run(args, skip=skip), None
    except Exception as exc:  # noqa: BLE001 — 공통 자료를 못 읽음(정산집계 옛 형식 등) = 이 작업 전체 중단(사유 보고)
        return None, f"위탁정산서 공통 자료 못 읽음 — {_why(exc)}"
    finally:
        w.flush()


def _consignor(args: CTX.StatementArgs, skip: tuple, on_log) -> tuple[list, list, dict, str | None]:
    """(결과, 실패, {계정ID: 정산집계 계정 이름}, abort) — skip = 정산 받기 실패 계정 + 계약 종료 계정(옛 형식 '정산서 없음' · D-427)."""
    try:
        ctx = CTX.load(args)
    except Exception as exc:  # noqa: BLE001 — 공통 자료를 못 읽음 = 새 형식 전체 중단(사유 보고)
        return [], [], {}, f"위탁자정산서 공통 자료 못 읽음 — {_why(exc)}"
    accts = [a for a in ctx.accts if (not args.only or SRC.aid_of(a) in args.only) and SRC.aid_of(a) not in skip]
    results, failed = build_all(ctx, accts, "", CM.load_judge(inputs=args.inputs), log=on_log)
    return results, failed, {SRC.aid_of(a): a for a in ctx.accts}, None


def _sheets(opts: dict, args: CTX.StatementArgs, good: list[dict], skipped: list, on_log, client_for) -> dict:
    """검산 통과 + 성공 계정 자료만 판매 달마다 그 달 시트에(시트 없으면 '확인 필요 — 시트 없음') → {달: 그린 시트 주소}."""
    sheets, drawn = sheet_map(opts, args.inputs), {}
    for m in sorted({r["month"] for r in good}):
        rs = [r for r in good if r["month"] == m]
        if not sheets.get(m):
            skipped.append(issue(f"시트 {m}", f"{NO_SHEET} · 반영 못 한 계정 {len(rs)}곳", month=m,
                                 amount=sum(r["data"]["settle_amount"] for r in rs)))
            continue
        try:
            write_sheet(sheets[m], rs, args.issued, log=on_log, client=client_for(sheets[m]) if client_for else None)
        except Exception as exc:  # noqa: BLE001 — 그 달 시트만 실패(사유 보고) · 다른 달은 계속
            skipped.append(issue(f"시트 {m}", f"시트 쓰기 실패 — {_why(exc)}", month=m))
            continue
        drawn[m] = sheets[m]
    return drawn


def issue(id_: str, reason: str, *, account: str = "", month: str = "", product: str = "", amount=None) -> dict:
    """확인 필요 1건(운용자가 로그 없이 보게 · 레인 A 가 '확인 필요' 탭·상태 카드에 씀) — id = 계정ID 또는 '시트 YYYY-MM' ·
    account = 정산집계 계정 이름 · contract = 계약(위탁정산서는 계정 단위라 늘 빈 칸) · product = 상품명(있으면) · amount = 금액(있으면 · 원) ·
    month = 판매 달(있으면) · reason = 사유."""
    return {"id": id_, "account": account, "contract": "", "month": month, "product": product, "amount": amount, "reason": reason}


def _excluded(results: list, names: dict) -> list:
    """못 나눠 금액에서 뺀 정산 예정분(D-262 ③ · 정산서는 발행 = 계정 성공 그대로) → 확인 필요 줄."""
    return [issue(r["account"], f"정산 예정분을 상품으로 못 나눔(그 금액만 빼고 정산서는 발행 · D-262 ③) — {x['판매 방식']} 판매 {x['판매']:,} — {x['사유']}",
                  account=names.get(r["account"], r["account"]), month=r["month"], amount=x["정산"])
            for r in results for x in r["data"].get("pending_excluded") or []]


def _merge(st: dict, results: list, failed: list, skip: dict, names: dict) -> tuple[list, list, set]:
    """계정별 결과 합치기 → (ok 계정ID, skipped = 건마다 issue 1줄, 시트에 넣을 수 있는 계정ID).
    시트 대상 = 옛 정산서를 만든 위탁 계정(우리 사업자 = 통보 제외) 중 새 형식 계정 단위 실패가 없는 곳 — 그 안에서도 검산 통과한 달만 씀."""
    out = [issue(aid, f"{SKIP_REASON}{' — ' + why if why else ''}") for aid, why in skip.items()]
    out += [issue(aid, f"위탁정산서 못 만듦 — {reason}") for aid, reason in st["failed"]]
    out += [issue(aid, f"위탁자정산서 못 만듦 — {reason}", month=m) for aid, m, reason in failed]
    out += [issue(r["account"], f"검산 실패(그 달 시트 반영 안 함) — {' / '.join(r['failures'])}", month=r["month"],
                  amount=r["data"]["settle_amount"]) for r in results if r["failures"]]
    for x in out:
        x["account"] = names.get(x["id"], x["id"])
    bad = {x["id"] for x in out}
    ok = [aid for aid in st["made_ids"] if aid not in bad]
    out += _excluded(results, names)
    sheet_ok = set(st["made_ids"]) - set(st.get("own_ids") or ()) - {aid for aid, m, _ in failed if not m}
    return ok, out, sheet_ok


def skip_ids(opts: dict) -> dict:
    """건너뛸 계정 → {계정ID: 사유} — skip_accounts {계정명('대표자-사업자-계정ID'): 사유}(레인 A) · skip [계정ID]."""
    out = {SRC.aid_of(str(name)): str(why or "") for name, why in (opts.get("skip_accounts") or {}).items()}
    out.update({str(aid): out.get(str(aid), "") for aid in opts.get("skip") or ()})
    return out


def run_job(opts: dict, on_log: Callable[[str], None], *, client_for=None) -> dict:
    """위탁정산서 배치 1회. opts = output(루트 · 없으면 managed_output) · managed_output · settle_dir · inputs · stats · basis · issued ·
    out · skip_accounts({계정명: 사유}) · skip([계정ID]) · only(시험용) · settle_only(정산전용상품 사본) · sheet / write_sheet(bool · 시트 반영) · sheets({달: 주소}) · 그 밖의 칸(cycle·run_id·log 등)은 안 씀.
    결과 = 약속 4칸 + sheet(이번에 그린 가장 최근 판매 달 시트 주소 · 없으면 None) + sheets({달: 그린 주소}).
    client_for = 시험용(주소 → 가짜 시트 클라이언트)."""
    args, notes, abort = pick_inputs(opts)
    skip = skip_ids(opts)
    if abort:
        on_log(f"❌ 시작 전 중단 — {abort}")
        return _result([], [], [], abort)
    assert args is not None
    for n in notes:
        on_log(n)
    st, abort = _xlsx(args, tuple(skip), on_log)
    if abort:
        return _result([], [], [], abort)
    assert st is not None
    ended = tuple(aid for aid, _why in st["none"])     # 계약 종료(D-427) = 옛 형식과 같은 판정 · 새 형식도 안 만듦(확인 필요 아님)
    results, failed, names, abort = _consignor(args, tuple(skip) + ended, on_log)
    if abort:
        return _result([], [], st["files"], abort)
    folder = save(results, args.out)
    files = st["files"] + [str(json_path(args.out, r)) for r in results] + [str(folder / "_요약.json")]
    ok, skipped, sheet_ok = _merge(st, results, failed, skip, names)
    drawn: dict = {}
    if opts.get("sheet") is True or opts.get("write_sheet"):
        good = [r for r in results if r["account"] in sheet_ok and not r["failures"]]
        drawn = _sheets(opts, args, good, skipped, on_log, client_for)
    on_log(f"위탁정산서 배치 — 성공 {len(ok)}곳 · 확인 필요 {len(skipped)}건 · 파일 {len(files)}개 · 그린 시트 {len(drawn)}개")
    return _result(ok, skipped, files, None, drawn)


def _result(ok: list, skipped: list, files: list, abort: str | None, drawn: dict | None = None) -> dict:
    drawn = drawn or {}
    return {"ok": ok, "skipped": skipped, "files": files, "abort": abort,
            "sheet": drawn[max(drawn)] if drawn else None, "sheets": dict(drawn)}
